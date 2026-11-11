"""Herramientas de interfaz del asistente: mover el Mapa 3D (`mapa`), abrir una vista del panel (`abrir_vista`) y
presentar la propuesta 2028–2031 (`presentacion`: la presentación pública web/propuesta.html dentro del panel).

No escriben en la base: devuelven acciones para el navegador (`Resultado.acciones`, con la forma del §6 de
docs/agente.md) que el widget aplica con `accionesMapa` o con `ir`. Por qué está hecho así:

* El modelo pide «a su manera» (un lugar por nombre, personas por id, filtros con nombre) y el servidor lo convierte
  en acciones exactas, ya validadas y resueltas: el navegador no adivina ni busca nada. Lo que no se puede resolver (un
  lugar ambiguo o que no existe, una etiqueta sensible, un permiso que falta) vuelve al modelo con los candidatos y no
  se mueve nada: todo o nada, para no dejar el mapa a medias.
* Las coordenadas y los nombres de las personas que se resaltan van solo al navegador. Al modelo le vuelve un resumen
  con cifras (cuántas cumplen los filtros, cuántas están ubicadas, cuántas se resaltaron y cuáles no tienen punto),
  nunca coordenadas ni nombres de personas.
* Las cifras salen de `GET /api/mapa/puntos` por `ctx.api`, con los permisos del panel y sin quienes no autorizaron
  el tratamiento de sus datos (`tratables`): cuántas de un lugar o de un filtro tienen ubicación diría algo de ellas.
  Con `consentimiento: no` el mapa se mueve igual, pero al modelo no le llegan cifras. El navegador recibe los filtros
  tal cual: la persona del equipo ve en el mapa a todos los que su rol ve.
* Los permisos son los del panel: `mapa.ver` para el mapa, `zonas.gestionar` para abrir zonas, `presentacion.ver` para
  la presentación y el de cada vista (la tabla `RUTAS` de `web/js/app.js`) para navegar. Como varias acciones no
  consultan la API, se comprueban aquí con la misma tabla (`acceso.PERMISOS`).
* La presentación es pública y no toca la base: el modelo recibe el guion del paso al que la lleva (`guion.py`, lo mismo
  que se ve en pantalla) para explicarlo con datos reales, y el navegador, el capítulo y el paso exactos. Lo que el
  modelo escribe para la pantalla (`explicacion`) se proyecta ante otras personas: se rechaza con caracteres que no se
  ven o que cambian cómo se ve el resto, con números largos o con «@» (una cédula, un teléfono o un correo no llegan
  ahí ni por descuido).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, Union
from urllib.parse import urlencode

from pydantic import AfterValidator, BeforeValidator, Field, field_validator, model_validator
from starlette.concurrency import run_in_threadpool

from .. import guion as guion_presentacion
from .base import Contexto, ErrorHerramienta, Herramienta, Resultado
from .gestion import (FiltrosBase, Id, IdOCero, Lugar, Nomenclatura, Perezosa, TipoLugar, _Entrada, error_de_busqueda,
                      esquema, exigir_permiso, miles, orden_lugar, pedir, preparar_filtros)

# Rango de coordenadas de Yondó que acepta el servidor (`RANGO_YONDO` de mapa3d.js, `ReunionIn`)
LAT_MIN, LAT_MAX, LON_MIN, LON_MAX = 6.3, 7.5, -74.6, -73.6
MAX_RESALTAR = 500  # puntos de un resalte (`MAX_IDS` de mapa3d.js) y el tope de `ids` de la API
# Lo más largo que el widget acepta en la consulta de una ruta del panel (`destinoEnlace` de agente.js, con el «?»):
# una más larga no se abre. Una prueba lo compara con agente.js
MAX_CONSULTA = 600
LOTE_IDS = 200  # ids por consulta: `ids` de la API admite hasta 4000 caracteres
COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
NOMBRE_BASE = {"auto": "según el tema", "oscuro": "oscuro", "claro": "claro", "satelite": "satélite"}
NOMBRE_RECORRIDO = {"municipio": "todo el municipio", "casco": "el casco urbano", "tigre": "San Miguel del Tigre"}


# ───────────────────────────── Acciones del mapa (entrada del modelo) ─────────────────────────────

def _texto_de_tamano(v: Any) -> Any:
    """El modelo suele mandar 150 como número: el mapa lo usa como texto («150»)."""
    return str(int(v)) if isinstance(v, (int, float)) and not isinstance(v, bool) else v


def _exigir_lugar(lugar: str | None, lugar_id: int | None, tipo_lugar: str | None) -> None:
    if lugar is not None and lugar_id is not None:
        raise ValueError("Use lugar (nombre) o lugar_id, no los dos")
    if tipo_lugar is not None and lugar is None:
        raise ValueError("tipo_lugar acompaña a lugar (el nombre)")


class AccionVolar(_Entrada):
    """Llevar la cámara a un lugar del nomenclátor (las veredas y el corregimiento se encuadran completos) o a un
    punto."""
    tipo: Literal["volar"]
    lugar: str | None = Field(None, min_length=2, max_length=80, description="Barrio, vereda… por nombre")
    tipo_lugar: TipoLugar | None = Field(None, description="Tipo del lugar, si el nombre se repite")
    lugar_id: Id | None = Field(None, description="Id del lugar (buscar_lugar)")
    lat: float | None = Field(None, ge=LAT_MIN, le=LAT_MAX)
    lon: float | None = Field(None, ge=LON_MIN, le=LON_MAX)
    zoom: float | None = Field(None, ge=8, le=19, description="8 (municipio) a 19 (calle)")
    pitch: float | None = Field(None, ge=0, le=80, description="Inclinación en grados (0 = desde arriba)")
    bearing: float | None = Field(None, ge=-180, le=180, description="Rumbo en grados")

    @model_validator(mode="after")
    def _destino(self):
        _exigir_lugar(self.lugar, self.lugar_id, self.tipo_lugar)
        if (self.lat is None) != (self.lon is None):
            raise ValueError("lat y lon van juntas")
        if sum(x is not None for x in (self.lugar, self.lugar_id, self.lat)) != 1:
            raise ValueError("Indique un destino: lugar, lugar_id o lat y lon")
        return self


class AccionFiltros(_Entrada):
    """Los filtros de Habitantes en el mapa (y su URL)."""
    tipo: Literal["filtros"]
    valores: FiltrosBase | None = Field(None, description="Los filtros; vacío con reemplazar = quitar todos")
    reemplazar: bool = Field(True, description="true: quedan solo estos; false: se suman a los que ya tenía el mapa")


class AccionCapas(_Entrada):
    """Prender (true) o apagar (false) capas del mapa."""
    tipo: Literal["capas"]
    calor: bool | None = Field(None, description="Mapa de calor")
    columnas: bool | None = Field(None, description="Columnas 3D de hexágonos")
    puntos: bool | None = Field(None, description="Un punto por persona (de cerca)")
    veredas: bool | None = Field(None, description="Polígonos de las veredas y nombres de los lugares")
    reuniones: bool | None = None
    edificios: bool | None = Field(None, description="Edificios 3D")
    relieve: bool | None = None
    areas: bool | None = Field(None, description="Áreas de trabajo guardadas")

    @model_validator(mode="after")
    def _alguna(self):
        if not self.model_dump(exclude_none=True, exclude={"tipo"}):
            raise ValueError("Indique al menos una capa (true o false)")
        return self


class AccionBase(_Entrada):
    tipo: Literal["base"]
    base: Literal["auto", "oscuro", "claro", "satelite"] = Field(..., description="auto = según el tema del panel")


class AccionHexagono(_Entrada):
    tipo: Literal["hexagono"]
    tamano: Annotated[Literal["auto", "150", "400", "1000"], BeforeValidator(_texto_de_tamano)] = Field(
        ..., description="Radio de los hexágonos en metros, o auto (según el zoom)")


class AccionRecorrido(_Entrada):
    tipo: Literal["recorrido"]
    nombre: Literal["municipio", "casco", "tigre"] = Field(
        ..., description="municipio (todo Yondó), casco (casco urbano) o tigre (San Miguel del Tigre)")


class AccionGiro(_Entrada):
    tipo: Literal["giro"]
    activo: bool = Field(..., description="true: el mapa gira solo; false: se detiene")


class AccionResaltar(_Entrada):
    """Marcar en el mapa personas (por id) o un lugar, con su nombre como etiqueta (solo en el mapa)."""
    tipo: Literal["resaltar"]
    persona_ids: list[Id] | None = Field(None, min_length=1, max_length=MAX_RESALTAR,
                                         description="Ids de personas (de buscar_personas u otra herramienta)")
    lugar: str | None = Field(None, min_length=2, max_length=80, description="Un lugar por nombre")
    tipo_lugar: TipoLugar | None = None
    lugar_id: Id | None = None
    color: str | None = Field(None, min_length=7, max_length=7, description="Color #rrggbb (por defecto, el del "
                                                                            "panel)")
    etiquetas: bool = Field(True, description="Poner el nombre de cada persona junto a su punto (solo en el mapa)")
    sumar: bool = Field(False, description="true: se suman a lo ya resaltado")
    encuadrar: bool = Field(True, description="Mover la cámara para que se vean todos")

    @field_validator("color")
    @classmethod
    def _color(cls, v):
        if v is not None and not COLOR.fullmatch(v):
            raise ValueError("El color va como #rrggbb (por ejemplo #e3141b)")
        return v

    @field_validator("persona_ids")
    @classmethod
    def _unicos(cls, v):
        return list(dict.fromkeys(v)) if v else v

    @model_validator(mode="after")
    def _que(self):
        _exigir_lugar(self.lugar, self.lugar_id, self.tipo_lugar)
        if not self.persona_ids and self.lugar is None and self.lugar_id is None:
            raise ValueError("Indique persona_ids, lugar o lugar_id")
        return self


class AccionLimpiar(_Entrada):
    tipo: Literal["limpiar"]
    todo: bool = Field(False, description="true: además detiene el giro y cierra la zona abierta")


class AccionZona(_Entrada):
    """Abrir como zona (con su distribución) un área de trabajo guardada o una vereda, o cerrar la zona abierta."""
    tipo: Literal["zona"]
    area_id: Id | None = Field(None, description="Área de trabajo guardada")
    lugar: str | None = Field(None, min_length=2, max_length=80, description="Vereda o corregimiento por nombre")
    tipo_lugar: TipoLugar | None = None
    lugar_id: Id | None = Field(None, description="Vereda o corregimiento (con polígono)")
    cerrar: bool = Field(False, description="true: cierra la zona abierta")

    @model_validator(mode="after")
    def _una(self):
        _exigir_lugar(self.lugar, self.lugar_id, self.tipo_lugar)
        if sum(bool(x) for x in (self.area_id is not None, self.lugar is not None, self.lugar_id is not None,
                                 self.cerrar)) != 1:
            raise ValueError("Indique una sola cosa: area_id, lugar, lugar_id o cerrar")
        return self


Accion = Annotated[Union[AccionVolar, AccionFiltros, AccionCapas, AccionBase, AccionHexagono, AccionRecorrido,
                         AccionGiro, AccionResaltar, AccionLimpiar, AccionZona], Field(discriminator="tipo")]


class MapaEntrada(_Entrada):
    acciones: list[Accion] = Field(..., min_length=1, max_length=8, description="Se aplican en este orden")


# ───────────────────────────── Del pedido del modelo a las acciones del navegador ─────────────────────────────

@dataclass
class _Plan:
    """Lo que va armando cada acción: para el navegador (§6), para el modelo (sin datos de personas) y para la
    interfaz (una frase corta)."""
    navegador: list[dict] = field(default_factory=list)
    modelo: list[dict] = field(default_factory=list)
    frases: list[str] = field(default_factory=list)
    personas: set[int] = field(default_factory=set)
    # Los filtros que el mapa tendrá con seguridad (los de una acción `filtros` que reemplaza): con ellos se cuentan
    # las personas de un lugar o de una zona. Si el mapa conserva los suyos, el servidor no los conoce
    filtros: dict[str, str] = field(default_factory=dict)


SIN_CIFRAS = ("Son quienes no autorizaron el tratamiento de sus datos: el mapa del panel los muestra, pero al "
              "asistente no le llegan sus cifras.")


class _Cuentas:
    """`GET /api/mapa/puntos` (total y ubicadas) por parámetros, una vez por llamada, sin quienes no autorizaron. None
    si los filtros son justo los de quienes no autorizaron: de ellos no se dan cifras."""

    def __init__(self, ctx: Contexto):
        self.ctx, self._hechas = ctx, {}

    async def __call__(self, params: dict[str, str]) -> tuple[int, int] | None:
        if params.get("consentimiento") == "no":
            return None
        clave = tuple(sorted(params.items()))
        if clave not in self._hechas:
            d = await pedir(self.ctx, "GET", "/api/mapa/puntos", params={**params, "tratables": "1"})
            d = d if isinstance(d, dict) else {}
            self._hechas[clave] = (_entero(d.get("total")), _entero(d.get("ubicadas")))
        return self._hechas[clave]


def _entero(v: Any) -> int:
    return v if isinstance(v, int) and not isinstance(v, bool) else 0


def _lotes(ids: list[int]) -> list[list[int]]:
    return [ids[i:i + LOTE_IDS] for i in range(0, len(ids), LOTE_IDS)]


def _numero(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


async def _coordenadas(ctx: Contexto, ids: list[int]) -> dict[int, tuple[float, float]]:
    """Dónde está cada persona en el mapa (las que tienen punto). Solo para el navegador."""
    out: dict[int, tuple[float, float]] = {}
    for lote in _lotes(ids):
        d = await pedir(ctx, "GET", "/api/mapa/puntos", params={"ids": ",".join(map(str, lote))})
        for p in (d.get("puntos") if isinstance(d, dict) else None) or []:
            if isinstance(p, list) and len(p) >= 3 and isinstance(p[0], int):
                lat, lon = _numero(p[1]), _numero(p[2])
                if lat is not None and lon is not None and LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX:
                    out[p[0]] = (lat, lon)
    return out


async def _filas(ctx: Contexto, ids: list[int]) -> dict[int, dict]:
    """El nombre (para las etiquetas del mapa, solo para el navegador) y la autorización de cada persona, con la
    proyección del rol."""
    out: dict[int, dict] = {}
    for lote in _lotes(ids):
        d = await pedir(ctx, "GET", "/api/personas", params={"ids": ",".join(map(str, lote)), "por_pagina": LOTE_IDS})
        for f in (d.get("filas") if isinstance(d, dict) else None) or []:
            if isinstance(f, dict) and isinstance(f.get("id"), int):
                out[f["id"]] = {"nombre": f["nombre"][:80] if isinstance(f.get("nombre"), str) else None,
                                "no_autorizo": f.get("consentimiento") == "no"}
    return out


def _destino(lg: Lugar) -> dict:
    """El lugar como lo usa el navegador para volar: con `poligono` encuadra el polígono de la capa `veredas`; si no,
    vuela a su punto."""
    if not lg.poligono_en_mapa and not lg.tiene_punto:
        raise ErrorHerramienta(f"{lg.legible()} no tiene punto ni polígono en el nomenclátor: no se puede mostrar en "
                               "el mapa. Se ubica en Calidad de datos > Barrios y veredas.", "sin_ubicacion",
                               estado=409, detalle={"lugar": lg.para_modelo()})
    return {"id": lg.id, "nombre": lg.nombre, "tipo": lg.tipo, "lat": lg.lat, "lon": lg.lon,
            "poligono": lg.poligono_en_mapa}


def _para_modelo(lg: Lugar, otros: list[Lugar], parecido: bool) -> dict:
    out: dict[str, Any] = {"lugar": lg.para_modelo()}
    if otros:
        out["mismo_nombre"] = [o.para_modelo() for o in otros]
    if parecido:
        out["entendido_como"] = lg.nombre
    return out


async def _resolver(nom: Perezosa, lugar: str | None, lugar_id: int | None,
                    tipo: str | None) -> tuple[Lugar, list[Lugar], bool]:
    """(el lugar, los demás niveles del mismo sitio, si casó por parecido) o el error con candidatos."""
    n: Nomenclatura = await nom()
    if lugar_id is not None:
        return n.por_id_o_error(lugar_id, tipo), [], False
    b = n.buscar(lugar or "", tipo)
    if b.elegido is None:
        raise error_de_busqueda(b, n)
    return b.elegido, [c for c in b.candidatos if c.id != b.elegido.id], b.parecido


def _camara(a: AccionVolar) -> dict:
    return {k: v for k, v in (("zoom", a.zoom), ("pitch", a.pitch), ("bearing", a.bearing)) if v is not None}


def _cifras(cuentas: tuple[int, int] | None) -> str:
    if cuentas is None:
        return "sin cifras de quienes no autorizaron"
    total, ubicadas = cuentas
    return f"{miles(total)} {'persona' if total == 1 else 'personas'}, {miles(ubicadas)} con ubicación"


def _con_cifras(out: dict, cuentas: tuple[int, int] | None, total: str, ubicadas: str | None = "ubicadas") -> dict:
    """`out` con las cifras para el modelo (o la nota de que no las hay)."""
    if cuentas is None:
        return {**out, "nota_cifras": SIN_CIFRAS}
    return {**out, total: cuentas[0], **({ubicadas: cuentas[1]} if ubicadas else {})}


async def _volar(ctx: Contexto, a: AccionVolar, plan: _Plan, nom: Perezosa, cuentas: _Cuentas) -> None:
    if a.lat is not None:
        plan.navegador.append({"tipo": "volar", "lat": a.lat, "lon": a.lon, **_camara(a)})
        plan.modelo.append({"tipo": "volar", "destino": "el punto pedido"})
        plan.frases.append("Volé al punto pedido")
        return
    lg, otros, parecido = await _resolver(nom, a.lugar, a.lugar_id, a.tipo_lugar)
    plan.navegador.append({"tipo": "volar", "lugar": _destino(lg), **_camara(a)})
    c = await cuentas({**plan.filtros, "lugar_id": str(lg.id)})
    plan.modelo.append(_con_cifras({"tipo": "volar", **_para_modelo(lg, otros, parecido)}, c, "personas_del_lugar"))
    plan.frases.append(f"Volé a {lg.nombre.title()} ({_cifras(c)})")


async def _filtros(ctx: Contexto, a: AccionFiltros, plan: _Plan, nom: Perezosa, cuentas: _Cuentas) -> None:
    params, legible = await preparar_filtros(ctx, a.valores, nom)
    plan.navegador.append({"tipo": "filtros", "valores": params, "reemplazar": a.reemplazar})
    c = await cuentas(params)
    out: dict[str, Any] = _con_cifras({"tipo": "filtros", "filtros": legible, "reemplazar": a.reemplazar}, c,
                                      "personas")
    total, ubicadas = c or (0, 0)
    if total and not ubicadas:
        out["aviso"] = ("Ninguna tiene ubicación: no se verán en el mapa. Para verlas en lista, abra Habitantes con "
                        "los mismos filtros (abrir_vista).")
    if not a.reemplazar:
        out["nota"] = "Se suman a los filtros que ya tenía el mapa: en pantalla pueden quedar menos."
    else:
        plan.filtros = dict(params)
    plan.modelo.append(out)
    accion = "Quité los filtros" if not params and a.reemplazar else "Filtré"
    plan.frases.append(f"{accion}: {_cifras(c)}")


async def _capas(ctx: Contexto, a: AccionCapas, plan: _Plan, *_: Any) -> None:
    valores = a.model_dump(exclude_none=True, exclude={"tipo"})
    if "areas" in valores:
        exigir_permiso(ctx, "zonas.gestionar", "Su rol no ve las áreas de trabajo en el mapa.")
    plan.navegador.append({"tipo": "capas", "valores": valores})
    plan.modelo.append({"tipo": "capas", "capas": valores})
    plan.frases.append("Capas: " + ", ".join(f"{k} {'sí' if v else 'no'}" for k, v in valores.items()))


async def _base(ctx: Contexto, a: AccionBase, plan: _Plan, *_: Any) -> None:
    plan.navegador.append({"tipo": "base", "base": a.base})
    plan.modelo.append({"tipo": "base", "base": a.base})
    plan.frases.append(f"Mapa base {NOMBRE_BASE[a.base]}")


async def _hexagono(ctx: Contexto, a: AccionHexagono, plan: _Plan, *_: Any) -> None:
    plan.navegador.append({"tipo": "hexagono", "tamano": a.tamano})
    plan.modelo.append({"tipo": "hexagono", "tamano": a.tamano})
    plan.frases.append("Hexágonos " + ("según el zoom" if a.tamano == "auto" else f"de {a.tamano} m"))


async def _recorrido(ctx: Contexto, a: AccionRecorrido, plan: _Plan, *_: Any) -> None:
    plan.navegador.append({"tipo": "recorrido", "nombre": a.nombre})
    plan.modelo.append({"tipo": "recorrido", "nombre": a.nombre})
    plan.frases.append(f"Recorrido por {NOMBRE_RECORRIDO[a.nombre]}")


async def _giro(ctx: Contexto, a: AccionGiro, plan: _Plan, *_: Any) -> None:
    plan.navegador.append({"tipo": "giro", "activo": a.activo})
    plan.modelo.append({"tipo": "giro", "activo": a.activo})
    plan.frases.append("Giro activado" if a.activo else "Giro detenido")


async def _limpiar(ctx: Contexto, a: AccionLimpiar, plan: _Plan, *_: Any) -> None:
    plan.navegador.append({"tipo": "limpiar", "todo": a.todo})
    plan.modelo.append({"tipo": "limpiar", "todo": a.todo})
    plan.frases.append("Limpié el mapa" if a.todo else "Quité lo resaltado")


async def _resaltar(ctx: Contexto, a: AccionResaltar, plan: _Plan, nom: Perezosa, cuentas: _Cuentas) -> None:
    ids = list(a.persona_ids or [])
    puntos: list[dict] = []
    sin_ubicacion: list[int] = []
    no_autorizo: set[int] = set()
    coords: dict[int, tuple[float, float]] = {}
    if ids:
        coords = await _coordenadas(ctx, ids)
        filas = await _filas(ctx, ids)
        # De quien no autorizó, el modelo no sabe si tiene ubicación: el mapa la marca si la tiene, pero no cuenta
        no_autorizo = {i for i, f in filas.items() if f["no_autorizo"]}
        for i in ids:
            if i in coords:
                lat, lon = coords[i]
                nombre = (filas.get(i) or {}).get("nombre") if a.etiquetas else None
                puntos.append({"id": i, "lat": lat, "lon": lon, **({"etiqueta": nombre} if nombre else {})})
            elif i not in no_autorizo:
                sin_ubicacion.append(i)
        plan.personas |= set(ids)
    out: dict[str, Any] = {"tipo": "resaltar"}
    volar = None
    if a.lugar is not None or a.lugar_id is not None:
        lg, otros, parecido = await _resolver(nom, a.lugar, a.lugar_id, a.tipo_lugar)
        destino = _destino(lg)
        if lg.tiene_punto and len(puntos) < MAX_RESALTAR:
            puntos.append({"lat": lg.lat, "lon": lg.lon, "etiqueta": lg.nombre})
        elif lg.tiene_punto:  # el mapa rechaza un resalte de más de MAX_RESALTAR puntos (entero, no solo el lugar)
            out["lugar_sin_marca"] = (f"El lugar no quedó marcado: el mapa resalta como mucho {MAX_RESALTAR} puntos y "
                                      "ya eran personas. Para marcarlo, pida menos personas.")
        if lg.poligono_en_mapa and not ids:  # resaltar una vereda es encuadrarla completa, no ir a su punto
            volar = {"tipo": "volar", "lugar": destino}
        out.update(_para_modelo(lg, otros, parecido))
    if ids:
        out.update(pedidas=len(ids), resaltadas=sum(1 for i in ids if i in coords and i not in no_autorizo),
                   sin_ubicacion=sin_ubicacion[:100])
        if no_autorizo:
            out.update(no_autorizaron=len(no_autorizo), nota_autorizacion=(
                "De quienes no autorizaron el tratamiento de sus datos no se dice si tienen ubicación: el mapa del "
                "panel las marca si la tienen."))
    if not puntos and volar is None and not no_autorizo:
        raise ErrorHerramienta("Ninguna de esas personas tiene ubicación en el mapa: no hay nada que resaltar. Se "
                               "ubican desde su ficha.", "sin_ubicacion", estado=409,
                               detalle={"sin_ubicacion": sin_ubicacion[:100]})
    if volar is not None:
        plan.navegador.append(volar)
    if puntos:
        plan.navegador.append({"tipo": "resaltar", "puntos": puntos, **({"color": a.color} if a.color else {}),
                               "encuadrar": a.encuadrar and volar is None, "sumar": a.sumar})
    plan.modelo.append(out)
    marcadas = sum(1 for i in ids if i in coords)  # para la interfaz (no va al modelo): lo que de verdad se ve
    frase = f"Resalté {miles(marcadas)} de {miles(len(ids))}" if ids else "Resalté el lugar"
    plan.frases.append(frase + (f" ({miles(len(ids) - marcadas)} sin ubicación)" if len(ids) > marcadas else ""))


async def _zona(ctx: Contexto, a: AccionZona, plan: _Plan, nom: Perezosa, cuentas: _Cuentas) -> None:
    exigir_permiso(ctx, "zonas.gestionar", "Su rol no abre zonas en el mapa.")
    if a.cerrar:
        plan.navegador.append({"tipo": "zona", "cerrar": True})
        plan.modelo.append({"tipo": "zona", "cerrada": True})
        plan.frases.append("Cerré la zona")
        return
    if a.area_id is not None:
        d = await pedir(ctx, "GET", "/api/areas")
        areas = [x for x in (d.get("areas") if isinstance(d, dict) else None) or [] if isinstance(x, dict)]
        area = next((x for x in areas if x.get("id") == a.area_id), None)
        if area is None:
            raise ErrorHerramienta(f"No existe el área de trabajo #{a.area_id}.", "no_existe", estado=404, detalle={
                "areas": [{"id": x.get("id"), "nombre": x.get("nombre")} for x in areas[:20]]} if areas else None)
        plan.navegador.append({"tipo": "zona", "area_id": a.area_id})
        c = await cuentas({**plan.filtros, "area_id": str(a.area_id)})
        plan.modelo.append(_con_cifras({"tipo": "zona", "area": {"id": a.area_id, "nombre": area.get("nombre")},
                                        "nota": "Dentro del área solo cuentan las personas ubicadas."}, c,
                                       "personas_dentro", None))
        plan.frases.append(f"Abrí la zona {area.get('nombre')}" + (f" ({miles(c[0])} personas)" if c else ""))
        return
    lg, otros, parecido = await _resolver(nom, a.lugar, a.lugar_id, a.tipo_lugar)
    if not lg.poligono_en_mapa:
        # Del mismo sitio en varios niveles (el centro poblado y su vereda), una zona se abre con el que tiene polígono
        con_poligono = sorted((o for o in otros if o.poligono_en_mapa), key=orden_lugar)
        if not con_poligono or a.lugar_id is not None:
            raise ErrorHerramienta(f"{lg.legible()} no tiene polígono: solo las veredas y el corregimiento se abren "
                                   "como zona. Use volar para ir a su punto.", "invalido", estado=422)
        lg, otros = con_poligono[0], [o for o in (lg, *otros) if o.id != con_poligono[0].id]
    plan.navegador.append({"tipo": "zona", "lugar_id": lg.id})
    c = await cuentas({**plan.filtros, "lugar_id": str(lg.id)})
    plan.modelo.append(_con_cifras({"tipo": "zona", **_para_modelo(lg, otros, parecido)}, c, "personas_del_lugar"))
    plan.frases.append(f"Abrí {lg.nombre.title()} como zona ({_cifras(c)})")


MANEJADORES = {"volar": _volar, "filtros": _filtros, "capas": _capas, "base": _base, "hexagono": _hexagono,
               "recorrido": _recorrido, "giro": _giro, "resaltar": _resaltar, "limpiar": _limpiar, "zona": _zona}


def _con_numero(e: ErrorHerramienta, i: int, tipo: str) -> ErrorHerramienta:
    """El error de una acción, con cuál fue (la acción `i` de la lista): el modelo corrige esa y reenvía todas."""
    detalle: dict[str, Any] = {"accion": i, "tipo": tipo}
    if isinstance(e.detalle, dict):
        detalle.update(e.detalle)
    elif e.detalle is not None:
        detalle["errores"] = e.detalle
    return ErrorHerramienta(f"Acción {i} ({tipo}): {e.mensaje}", e.codigo, estado=e.estado, detalle=detalle,
                            fatal=e.fatal)


async def _mapa(ctx: Contexto, a: MapaEntrada) -> Resultado:
    exigir_permiso(ctx, "mapa.ver", "Su rol no usa el mapa del panel: solo el administrador y el coordinador.")
    plan, nom, cuentas = _Plan(), Perezosa(ctx), _Cuentas(ctx)
    for i, accion in enumerate(a.acciones, 1):
        try:
            await MANEJADORES[accion.tipo](ctx, accion, plan, nom, cuentas)
        except ErrorHerramienta as e:
            raise _con_numero(e, i, accion.tipo) from None
    contenido: dict[str, Any] = {"aplicadas": plan.modelo,
                                 "nota": "Se aplica en el mapa del navegador de la persona; si no estaba abierto, se "
                                         "abre. Las cifras son con los filtros enviados en esta llamada."}
    resumen = "; ".join(plan.frases)
    return Resultado(contenido, resumen[:200], acciones=[{"tipo": "mapa", "acciones": plan.navegador}],
                     personas=plan.personas)


# ───────────────────────────── abrir_vista ─────────────────────────────

@dataclass(frozen=True)
class Vista:
    ruta: str        # con «{id}» si lleva un id
    permiso: str     # el de la tabla `RUTAS` de web/js/app.js
    nombre: str
    id: str = "no"   # no | si (obligatorio) | opcional


VISTAS = {
    "panel": Vista("/", "tablero.ver", "Panel"),
    "mapa": Vista("/mapa", "mapa.ver", "Mapa 3D"),
    "habitantes": Vista("/personas", "personas.listar", "Habitantes"),
    "ficha": Vista("/personas/{id}", "personas.ver", "la ficha", "si"),
    "reuniones": Vista("/reuniones", "reuniones.ver", "Reuniones"),
    "reunion": Vista("/reuniones/{id}", "reuniones.ver", "la reunión", "si"),
    "calidad": Vista("/calidad", "calidad.ver", "Calidad de datos"),
    "trabajo": Vista("/trabajo", "trabajo.ver", "Mi trabajo"),
    "usuarios": Vista("/usuarios", "usuarios.gestionar", "Usuarios", "opcional"),
    "ajustes": Vista("/ajustes", "ajustes.gestionar", "Ajustes"),
    "importar": Vista("/importar", "importar", "Importar y exportar"),
    "cuenta": Vista("/cuenta", "cuenta", "Mi cuenta"),
    "presentacion": Vista("/presentacion", "presentacion.ver", "la presentación de la propuesta"),
}
# Copia de las rutas de la tabla `RUTAS` de web/js/app.js (una prueba las compara): el widget solo navega a estas
RUTAS_PANEL = (r"^/$", r"^/mapa$", r"^/personas$", r"^/personas/(\d+)$", r"^/reuniones$", r"^/reuniones/(\d+)$",
               r"^/calidad$", r"^/importar$", r"^/ajustes$", r"^/trabajo$", r"^/usuarios$", r"^/usuarios/(\d+)$",
               r"^/cuenta$", r"^/presentacion$")
ORDENES = ("nombre", "completitud", "-completitud", "reciente", "contacto", "por_llamar", "abordaje_reciente", "lugar")
PESTANAS = ("coincidencias", "conflictos", "solicitudes", "situaciones", "lugares", "sin")
# Los filtros que Habitantes lee de la URL (`FILTROS` de web/js/vistas/personas.js): los demás los ignoraría
DE_HABITANTES = frozenset({
    "q", "zona", "lugar_id", "fuente", "lista", "etiqueta", "con_cedula", "con_telefono", "varios_telefonos",
    "precision", "asistio", "consentimiento", "lider", "sexo", "completitud_max", "ids", "ids_total", "reunion_id",
    "edad_min", "edad_max", "puesto_id", "votacion_estado", "donde", "con_puesto", "con_mesa", "abordaje_estado",
    "abordado", "contactado", "ultimo_resultado", "sin_acercamiento_dias", "proximo_vencido", "canal_autorizado",
    "requiere_actualizacion", "situacion", "creado_por", "actualizado_por", "menor", "area_id", "poligono",
    "tipo_documento", "cedula_verificada", "telefono_estado", "estado_civil", "nivel_educativo", "situacion_laboral",
    "estrato", "tenencia_vivienda", "regimen_salud", "sin_cedula", "sin_telefono", "sin_sexo", "sin_edad",
    "sin_lugar", "sin_puesto", "sin_mesa", "sin_direccion"})
# Filtros que la API no deja usar a planilleros y consultores (`filtros.VEDADOS`): con ellos Habitantes daría 403
VEDADOS = ("ids", "lista", "lider", "creado_por", "actualizado_por", "menor", "poligono")


class AbrirVistaEntrada(_Entrada):
    vista: Literal[tuple(VISTAS)] = Field(..., description="Qué vista abrir")
    id: Id | None = Field(None, description="ficha: id de la persona; reunion: id de la reunión; usuarios: id de un "
                                            "usuario (opcional)")
    filtros: FiltrosBase | None = Field(None, description="habitantes y mapa: filtros de Habitantes")
    q: str | None = Field(None, min_length=2, max_length=120, description="habitantes: buscar por nombre, cédula o "
                                                                         "teléfono (lo ve la persona, no usted)")
    orden: Literal[ORDENES] | None = Field(None, description="habitantes: orden de la lista")
    area_id: Id | None = Field(None, description="habitantes y mapa: un área de trabajo (en el mapa se abre como zona)")
    ids: list[Id] | None = Field(None, min_length=1, max_length=500, description="habitantes: solo estas personas "
                                                                                "(administrador y coordinador; caben "
                                                                                "unas 60: para más, filtros o el mapa)")
    pestana: Literal[PESTANAS] | None = Field(None, description="calidad: la pestaña")
    uid: IdOCero | None = Field(None, description="trabajo: el de otro usuario (administrador y coordinador)")

    @field_validator("ids")
    @classmethod
    def _unicos(cls, v):
        return list(dict.fromkeys(v)) if v else v

    @model_validator(mode="after")
    def _segun_vista(self):
        v = VISTAS[self.vista]
        if v.id == "si" and self.id is None:
            raise ValueError(f"La vista {self.vista} necesita el id")
        if v.id == "no" and self.id is not None:
            raise ValueError(f"La vista {self.vista} no lleva id")
        propios = {"habitantes": {"filtros", "q", "orden", "area_id", "ids"}, "mapa": {"filtros", "area_id"},
                   "calidad": {"pestana"}, "trabajo": {"uid"}}.get(self.vista, set())
        sobran = sorted(k for k in ("filtros", "q", "orden", "area_id", "ids", "pestana", "uid")
                        if getattr(self, k) is not None and k not in propios)
        if sobran:
            raise ValueError(f"La vista {self.vista} no usa: {', '.join(sobran)}")
        return self


async def _query_habitantes(ctx: Contexto, a: AbrirVistaEntrada, nom: Perezosa) -> dict[str, str]:
    params, _ = await preparar_filtros(ctx, a.filtros, nom)
    ignorados = sorted(set(params) - DE_HABITANTES)
    if ignorados:
        raise ErrorHerramienta(f"Habitantes no tiene estos filtros en su URL: {', '.join(ignorados)}. Quítelos o use "
                               "el mapa.", "invalido", estado=422)
    if a.q:
        params["q"] = a.q
    if a.area_id is not None:
        params["area_id"] = str(a.area_id)
    if a.ids:
        params["ids"] = ",".join(map(str, a.ids))
    if not ctx.quien.administra:
        vedados = sorted(k for k in VEDADOS if k in params)
        if vedados:
            raise ErrorHerramienta(f"Su rol no puede usar estos filtros en Habitantes: {', '.join(vedados)}.",
                                   "permiso", estado=403)
        asignacion = getattr(ctx.quien, "asignacion", None) or {}
        if a.area_id is not None and a.area_id not in (asignacion.get("areas") or []):
            raise ErrorHerramienta("Esa área no le está asignada.", "permiso", estado=403)
    if a.orden:
        params["orden"] = a.orden
    return params


async def _abrir_vista(ctx: Contexto, a: AbrirVistaEntrada) -> Resultado:
    v = VISTAS[a.vista]
    exigir_permiso(ctx, v.permiso, f"Su rol no abre {v.nombre} en el panel." + (
        " Su inicio es Mi trabajo." if a.vista == "panel" else ""))
    ruta = v.ruta.replace("{id}", str(a.id)) if "{id}" in v.ruta else v.ruta
    if a.vista == "usuarios" and a.id is not None:
        ruta = f"/usuarios/{a.id}"
    params: dict[str, str] = {}
    nom = Perezosa(ctx)
    if a.vista == "habitantes":
        params = await _query_habitantes(ctx, a, nom)
    elif a.vista == "mapa":
        params, _ = await preparar_filtros(ctx, a.filtros, nom)
        if a.area_id is not None:
            exigir_permiso(ctx, "zonas.gestionar", "Su rol no abre zonas en el mapa.")
            params["area_id"] = str(a.area_id)
    elif a.vista == "calidad" and a.pestana:
        params = {"p": a.pestana}
    elif a.vista == "trabajo" and a.uid is not None and a.uid != ctx.quien.uid:
        if not ctx.quien.administra:
            raise ErrorHerramienta("Solo ve su propio trabajo.", "permiso", estado=403)
        params = {"uid": str(a.uid)}
    if not any(re.fullmatch(p, ruta) for p in RUTAS_PANEL):  # nunca debería pasar: las rutas son las de la tabla
        raise ErrorHerramienta("Esa vista no existe en el panel.", "invalido", estado=422)
    consulta = f"?{urlencode(params)}" if params else ""
    if len(consulta) > MAX_CONSULTA:  # el widget no la abriría: mejor decirlo que dar por abierta la vista
        raise ErrorHerramienta(
            "La vista no cabe en la dirección del panel (demasiadas personas en ids o una búsqueda muy larga): no se "
            "abrió nada. Use filtros en vez de la lista de ids, o el mapa con resaltar para mostrarlas.", "invalido",
            estado=422, detalle={"caracteres": len(consulta), "maximo": MAX_CONSULTA})
    completa = ruta + consulta
    contenido = {"ruta": completa, "vista": v.nombre,
                 "nota": "La vista se abre en el panel de la persona; lo que muestra no llega al asistente."}
    return Resultado(contenido, f"Abrí {v.nombre}", acciones=[{"tipo": "navegar", "ruta": completa}])


# ───────────────────────────── presentacion ─────────────────────────────

OPS_PRESENTACION = ("indice", "ir", "siguiente", "anterior", "explicar", "quitar_explicacion")
# Una o dos frases cortas: lo que el subtítulo de la presentación muestra entero en cualquier pantalla, del celular al
# proyector (web/propuesta.html no lo recorta). `MAX_EXPLICACION` de agente-presentacion.js y de mando.js: una prueba
# los compara
MAX_EXPLICACION = 220
MAX_PASO = guion_presentacion.MAX_PASOS
# Lo que la explicación no puede traer: la ve una sala entera en un proyector. Caracteres que no se ven o que cambian
# cómo se ve el resto (de control, de formato como las marcas de dirección o el espacio de ancho cero, separadores de
# línea, sustitutos sueltos, de uso privado, sin asignar, los rellenos que se ven como nada y los selectores de
# variante), más de dos acentos apilados, una «@» (un correo, un usuario) o un número de 7 o más dígitos (una cédula, un
# teléfono, un código), también escrito por grupos. Las dos últimas se buscan en la forma NFKC del texto: así la «@» de
# ancho completo (＠) o la pequeña (﹫), los dígitos de ancho completo o en superíndice y los guiones de compatibilidad
# cuentan como los comunes. Las mismas reglas, en `explicacionVisible` de agente-presentacion.js y en `textoVisible` de
# mando.js
_NO_SE_VEN = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})
_RELLENOS = frozenset("\U0000034f\U0000115f\U00001160\U000017b4\U000017b5\U00002800\U00003164\U0000ffa0")
_SELECTORES = re.compile("[\U0000180b-\U0000180f\U0000fe00-\U0000fe0f\U000e0000-\U000e0fff]")
# Una tirada de dígitos con lo que los separa al escribir un teléfono o una cédula: un espacio, un guion, una raya, el
# signo menos o una barra (con un espacio a cada lado o sin él), un paréntesis que cierra («(604) 832 12 34»), y pegados
# entre dos dígitos el punto, la coma, el «_», el punto medio o el paréntesis que abre («71.234.567», «1,023,456,789»).
# Un paréntesis que abre después de un espacio no une («en 2018 (3.383)»), ni el punto o la coma seguidos de un espacio
# («en 2031. 300 familias», «2028, 2029 y 2030»)
_GUIONES = "\\-\u2010-\u2015\u2212"
_TIRADA = re.compile(rf"\d+(?:(?:[.,_\u00b7(]|\) ?|\)? ?[{_GUIONES}/] ?\(?| )\d+)*")
DIGITOS_MAX = 6
# Lo que sí puede tener 7 dígitos o más: un periodo («2028–2031», «2028-2031», «2028/2031») y un rango de dos cifras
# como las de la propuesta («$116.294 – 210.000 M», «1.346–1.500 kWh»), de menor a mayor. Solo con dígitos ASCII
_PERIODO = re.compile(rf"((?:19|20)[0-9]{{2}}) ?[{_GUIONES}/] ?((?:19|20)[0-9]{{2}})")
_CIFRA = r"[0-9]{1,3}(?:\.[0-9]{3})?(?:,[0-9]{1,2})?"
_RANGO = re.compile(rf"({_CIFRA}) ?[{_GUIONES}] ?({_CIFRA})")


def _cifra(t: str) -> float:
    """«116.294» → 116294; «1,62» → 1.62 (el punto de miles y la coma decimal de la presentación)."""
    return float(t.replace(".", "").replace(",", "."))


def numero_largo(t: str) -> str | None:
    """La primera tirada de más de DIGITOS_MAX dígitos de `t` (ya en NFKC y con los espacios en uno) que no es un
    periodo ni un rango de cifras, o None."""
    for m in _TIRADA.finditer(t):
        tirada = m.group(0)
        if len(re.findall(r"\d", tirada)) <= DIGITOS_MAX:
            continue
        p = _PERIODO.fullmatch(tirada)
        if p and int(p.group(1)) <= int(p.group(2)):
            continue
        r = _RANGO.fullmatch(tirada)
        if r and _cifra(r.group(1)) <= _cifra(r.group(2)):
            continue
        return tirada
    return None


def _explicacion_visible(v: str) -> str:
    """La explicación para la pantalla: un solo renglón que se ve tal cual es (los espacios seguidos quedan en uno, como
    los pinta el navegador), sin datos que identifiquen a nadie. Se devuelve como la escribió el modelo (sin NFKC: «m²»
    no pasa a «m2»); la forma NFKC solo sirve para buscar la «@» y los números."""
    marcas = 0
    for c in v:
        cat = unicodedata.category(c)
        if (cat in _NO_SE_VEN and c not in "\t\n\r") or c in _RELLENOS or _SELECTORES.match(c):
            raise ValueError("La explicación trae caracteres invisibles o de control: escríbala sin ellos")
        marcas = marcas + 1 if cat in ("Mn", "Me") else 0
        if marcas > 2:
            raise ValueError("La explicación trae demasiados acentos seguidos sobre una letra")
    v = " ".join(v.split())
    if not v:
        raise ValueError("La explicación está vacía")
    k = " ".join(unicodedata.normalize("NFKC", v).split())
    if "@" in k:
        raise ValueError("La explicación se proyecta ante la sala: no puede llevar «@» (un correo o un usuario). "
                         "Escríbala sin ella y, si hace falta, dé el dato en el chat")
    if numero_largo(k):
        raise ValueError("La explicación se proyecta ante la sala: no puede llevar números de 7 o más dígitos "
                         "(cédulas, teléfonos o códigos como el BPIN), tampoco con espacios, puntos, guiones o barras. "
                         "Escriba los montos como los trae el guion («$106.271 M», «$1,2 – 1,4 billones») y un periodo "
                         "como «2028–2031», separe dos números seguidos con una palabra o una coma («en 2028, 300 "
                         "viviendas») y deje los códigos para el chat")
    return v


def _paso_id(v: str) -> str:
    if not guion_presentacion.ID_PASO.fullmatch(v):
        raise ValueError("El id del paso va en minúsculas, con números o «_» (el del índice)")
    return v


def _paso_no_booleano(v: Any) -> Any:
    """`True` es un `int` en Python: pydantic lo tomaría por el paso 1."""
    if isinstance(v, bool):
        raise ValueError("El paso es un número entero desde 1 (o el id del paso), no verdadero o falso")
    return v


# Los topes van antes del validador: así el esquema dice «minimum/maximum»
PasoNumero = Annotated[int, Field(ge=1, le=MAX_PASO), BeforeValidator(_paso_no_booleano)]
PasoId = Annotated[str, Field(min_length=1, max_length=40), AfterValidator(_paso_id)]
Explicacion = Annotated[str, Field(min_length=1, max_length=MAX_EXPLICACION), AfterValidator(_explicacion_visible)]


class PresentacionEntrada(_Entrada):
    op: Literal[OPS_PRESENTACION] = Field(..., description=(
        "indice: los capítulos y los títulos de sus pasos; ir: a un capítulo y paso (devuelve lo que muestra ese paso); "
        "siguiente o anterior: un paso (con capitulo y paso de partida, los del contexto del panel, devuelve el paso "
        "de destino); explicar: muestra una o dos frases cortas en pantalla; quitar_explicacion: la quita"))
    capitulo: str | None = Field(None, min_length=2, max_length=60, description=(
        "Id o nombre del capítulo (del índice o del contexto del panel)"))
    paso: PasoNumero | PasoId | None = Field(None, description="Número del paso desde 1, o su id (del índice)")
    explicacion: Explicacion | None = Field(None, description=(
        "Una o dos frases cortas para la pantalla (se proyecta; hasta 220 caracteres): sin datos de habitantes, «@» ni "
        "números de 7 o más dígitos"))

    @model_validator(mode="after")
    def _segun_op(self):
        sobran = {"indice": ("capitulo", "paso", "explicacion"), "quitar_explicacion": ("capitulo", "paso", "explicacion"),
                  "explicar": ("capitulo", "paso")}.get(self.op, ())
        malos = [k for k in sobran if getattr(self, k) is not None]
        if malos:
            raise ValueError(f"La operación {self.op} no usa: {', '.join(malos)}")
        if self.op == "ir" and self.capitulo is None:
            raise ValueError("Para ir, indique el capítulo (id o nombre, del índice)")
        if self.op in ("siguiente", "anterior") and (self.capitulo is None) != (self.paso is None):
            raise ValueError("Para avanzar desde un paso, indique capitulo y paso de partida (los del contexto del "
                             "panel), o ninguno de los dos")
        if self.op == "explicar" and self.explicacion is None:
            raise ValueError("Para explicar, escriba la explicacion")
        return self


def _esquema_presentacion() -> dict:
    """El esquema de la entrada sin la rama «null» del paso (número o id): el modelo simplemente omite la clave."""
    s = esquema(PresentacionEntrada)
    paso = s["properties"]["paso"]
    if "anyOf" in paso:
        paso["anyOf"] = [r for r in paso["anyOf"] if r != {"type": "null"}]
        paso.pop("default", None)
    return s


def _cap_para_modelo(c: dict) -> dict:
    return {"id": c["id"], "nombre": c["nombre"]}


def _resolver_capitulo(g: guion_presentacion.Guion, texto: str) -> int:
    r = g.buscar(texto)
    if r.indice is not None:
        return r.indice
    if r.candidatos:
        raise ErrorHerramienta(f"«{texto}» puede ser más de un capítulo: elija uno por su id.", "ambiguo", estado=422,
                               detalle={"candidatos": [_cap_para_modelo(g.capitulos[i]) for i in r.candidatos]})
    raise ErrorHerramienta(f"La presentación no tiene un capítulo «{texto}».", "no_existe", estado=404,
                           detalle={"capitulos": [_cap_para_modelo(c) for c in g.capitulos]})


def _resolver_paso(g: guion_presentacion.Guion, ci: int, paso: int | str | None) -> int:
    pi = g.paso(ci, paso)
    if pi is not None:
        return pi
    c = g.capitulos[ci]
    raise ErrorHerramienta(f"El capítulo {c['nombre']} no tiene el paso {paso}: tiene {len(c['pasos'])}.", "invalido",
                           estado=422, detalle={"capitulo": c["id"], "pasos": len(c["pasos"]),
                                                "ids": [p["id"] for p in c["pasos"]]})


async def _presentacion(ctx: Contexto, a: PresentacionEntrada) -> Resultado:
    exigir_permiso(ctx, "presentacion.ver", "Su rol no abre la presentación en el panel.")
    try:
        g = await run_in_threadpool(guion_presentacion.cargar)
    except ValueError:
        g = None
    if g is None:
        raise ErrorHerramienta("La presentación de la propuesta no está disponible en este servidor.", "no_existe",
                               estado=404)
    if a.op == "indice":
        return Resultado({**g.indice(), "nota": (
            "Para mostrar un paso, op ir con su capitulo (id) y paso (número desde 1). Lo que se ve en cada paso le "
            "llega al ir.")}, f"Índice de la presentación ({len(g)} capítulos)")
    extra = {"explicacion": a.explicacion} if a.explicacion else {}
    if a.op == "explicar":
        return Resultado({"en_pantalla": a.explicacion, "nota": (
            "Se muestra sobre la presentación, en el paso que esté abierto. Explique en el chat con más detalle.")},
            "Mostré una explicación en la presentación",
            acciones=[{"tipo": "presentacion", "op": "explicar", **extra}])
    if a.op == "quitar_explicacion":
        return Resultado({"nota": "Se quitó la explicación de la pantalla."}, "Quité la explicación de la presentación",
                         acciones=[{"tipo": "presentacion", "op": "quitar_explicacion"}])
    if a.op in ("siguiente", "anterior") and a.capitulo is None:
        # Sin el punto de partida la presentación calcula el paso; el modelo lo ve en el contexto del próximo mensaje
        return Resultado({"nota": (
            f"La presentación pasa al paso {'siguiente' if a.op == 'siguiente' else 'anterior'} desde donde esté. Para "
            "saber cuál es (y recibir lo que muestra), use ir o indique capitulo y paso de partida.")},
            f"Pasé al paso {'siguiente' if a.op == 'siguiente' else 'anterior'} de la presentación",
            acciones=[{"tipo": "presentacion", "op": a.op, **extra}])
    ci = _resolver_capitulo(g, a.capitulo or "")
    pi = _resolver_paso(g, ci, a.paso)   # sin paso, `ir` va al primero (siguiente y anterior lo traen siempre)
    aviso = None
    if a.op in ("siguiente", "anterior"):
        destino = g.vecino(ci, pi, 1 if a.op == "siguiente" else -1)
        if destino == (ci, pi):
            aviso = ("Ya era el último paso de la presentación: queda en él." if a.op == "siguiente"
                     else "Ya era el primer paso de la presentación: queda en él.")
        ci, pi = destino
    c = g.capitulos[ci]
    n = len(c["pasos"])
    contenido: dict[str, Any] = {
        "capitulo": _cap_para_modelo(c), "paso": pi + 1, "de": n,
        "posicion": f"Paso {pi + 1} de {n} del capítulo {c['nombre']}", "guion": c["pasos"][pi],
        "nota": ("Es lo que muestra la presentación en ese paso: explíquelo en el chat con esos datos (no invente "
                 "otros). En pantalla, si hace falta, solo una o dos frases cortas (explicar, hasta 220 caracteres).")}
    if aviso:
        contenido["aviso"] = aviso
    return Resultado(contenido, f"Mostré {c['nombre']} · paso {pi + 1} de {n}",
                     acciones=[{"tipo": "presentacion", "op": "ir", "capitulo": c["id"], "paso": pi + 1, **extra}])


# ───────────────────────────── Catálogo de herramientas ─────────────────────────────

D_MAPA = (
    "Maneja el Mapa 3D del panel en el navegador de la persona (si no está abierto, lo abre), con hasta 8 acciones en "
    "orden: volar (a un barrio o vereda por nombre o lugar_id, las veredas se encuadran completas, o a lat y lon); "
    "filtros (los de Habitantes: reemplazan los del mapa, o se suman con reemplazar=false); capas (calor, columnas, "
    "puntos, veredas, reuniones, edificios, relieve, areas); base (auto, oscuro, claro, satelite); hexagono (tamaño "
    "auto, 150, 400 o 1000 m); recorrido (municipio, casco, tigre); giro; resaltar personas (persona_ids, de "
    "buscar_personas) o un lugar, con un color #rrggbb; limpiar; zona (abrir un área de trabajo o una vereda como "
    "zona, o cerrarla). Devuelve qué quedó en pantalla y cuántas personas cumplen los filtros y cuántas tienen "
    "ubicación (solo esas se ven), sin contar a quienes no autorizaron el tratamiento de sus datos (de ellos no "
    "llegan cifras). Si un lugar es ambiguo o no existe no mueve nada y devuelve los candidatos. Los "
    "nombres y coordenadas de las personas van solo al mapa, nunca a usted. Solo administrador y coordinador.")
D_ABRIR_VISTA = (
    "Abre una vista del panel en el navegador de la persona: panel (indicadores), mapa (con filtros o un área), "
    "habitantes (con filtros, búsqueda `q`, orden, un área o ids de personas), ficha (id de la persona), reuniones, "
    "reunion (id), calidad (con su pestaña), trabajo (o el de otro usuario con uid, solo administrador y "
    "coordinador), usuarios (o uno con su id), ajustes, importar, cuenta o presentacion (la propuesta 2028–2031; "
    "para manejarla, la herramienta presentacion). Solo abre lo que su rol puede ver. No devuelve datos: después diga "
    "en una frase qué quedó en pantalla.")
D_PRESENTACION = (
    "Presenta la propuesta de inversión Yondó 2028–2031 (la presentación pública: portada, siete módulos, "
    "financiación, hoja de ruta y pedidos) en el panel de la persona o en su proyector, y la explica paso a paso. "
    "indice devuelve los capítulos (id y nombre) y los títulos de sus pasos; ir lleva a un capítulo y paso y devuelve "
    "lo que ese paso muestra (textos, cifras, costos, plazos y lo que se ve en la maqueta 3D) para que lo explique con "
    "esos datos; siguiente y anterior avanzan un paso (con capitulo y paso de partida, los del contexto del panel, "
    "también devuelven el destino); explicar muestra en pantalla una o dos frases cortas (hasta 220 caracteres) y "
    "quitar_explicacion la quita. Si el capítulo no existe o es ambiguo, o el paso no está, no mueve nada y devuelve "
    "los candidatos. La explicación se proyecta ante otras personas: nunca datos de habitantes, «@» ni números de 7 o "
    "más dígitos. No toca la base de datos.")

HERRAMIENTAS: list[Herramienta] = [
    Herramienta("mapa", D_MAPA, MapaEntrada, "interfaz", ("mapa.ver",), "Moviendo el mapa", _mapa,
                esquema=esquema(MapaEntrada)),
    Herramienta("abrir_vista", D_ABRIR_VISTA, AbrirVistaEntrada, "interfaz", ("cuenta",), "Abriendo la vista",
                _abrir_vista, esquema=esquema(AbrirVistaEntrada)),
    # Sin el guion (un despliegue que no lo trae) no se ofrece: no habría qué explicar
    Herramienta("presentacion", D_PRESENTACION, PresentacionEntrada, "interfaz", ("presentacion.ver",),
                "Presentando la propuesta", _presentacion,
                disponible=lambda quien, ajustes, cfg: guion_presentacion.hay_guion(),
                esquema=_esquema_presentacion()),
]
