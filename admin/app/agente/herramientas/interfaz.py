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
* La presentación es pública y es la técnica (web/propuesta.html?modo=tecnica: lo que se construye, sin costos): el
  modelo recibe el guion del paso al que la lleva (`guion.py`, lo mismo que se ve en pantalla) para explicarlo con datos
  reales, y el navegador, el capítulo y el paso exactos. Con `visual` cambia lo que se ve sin cambiar de paso (la cámara,
  la obra enfocada, hoy o con el proyecto, la ficha técnica de un componente, un modelo del atlas y el tema): los
  componentes y las inmersiones se resuelven aquí contra el guion (por id o por nombre) y al modelo le vuelve la ficha
  técnica de lo que se muestra. Lo único que guarda es la
  pantalla en off de la persona (`app/pantalla.py`: capítulo, paso, explicación y lo que se ve, sin datos de nadie), que
  manejan este asistente y un agente por MCP (`app/api/mcp.py`) con la misma herramienta (`presentacion_en_pantalla`). Lo que el
  modelo escribe para la pantalla (`explicacion`) se proyecta ante otras personas: se rechaza con caracteres que no se
  ven o que cambian cómo se ve el resto, con números largos o con «@» (una cédula, un teléfono o un correo no llegan
  ahí ni por descuido).
"""
from __future__ import annotations

import json
import re
import secrets
import time
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, Union
from urllib.parse import urlencode

from pydantic import AfterValidator, BeforeValidator, Field, StrictBool, field_validator, model_validator
from starlette.concurrency import run_in_threadpool

from ... import pantalla as pantalla_off
from ... import recorrido as rec
from ...proyectable import DIGITOS_MAX, MAX_EXPLICACION, numero_largo, texto_proyectable  # noqa: F401
from .. import conversaciones as conv_db
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

OPS_PRESENTACION = ("indice", "guion", "ir", "siguiente", "anterior", "explicar", "quitar_explicacion", "vista",
                    "visual", "recorrido", "control_recorrido", "pantalla_completa", "estado")
# Lo que arma un recorrido narrado (`recorrido`) y lo que lo maneja (`control_recorrido`)
PARTES_RECORRIDO = ("titulo", "escenas", "cierre", "sugerencias")
# Las ops que cambian lo que se ve: con un recorrido sonando, parten de la escena en curso (la que la sala ve) y, ya
# resueltas, lo colapsan (lo cierran con esa escena como base) justo antes de guardarse
COLAPSAN = ("ir", "siguiente", "anterior", "explicar", "quitar_explicacion", "vista", "visual")
# Lo que dice cada operación del estado de la pantalla en off (las demás no lo cambian): `vista` y `pantalla_completa`
PARTES_VISTA = ("panel", "indice", "fichas")
# Lo que cambia `visual` (pantalla_off.VISUAL; `VISUAL` de mando.js y de agente-presentacion.js con los mismos valores)
PARTES_VISUAL = pantalla_off.VISUAL
CAMARAS = pantalla_off.CAMARAS
NOMBRE_CAMARA = {"paso": "el encuadre del paso", "aerea": "vista aérea", "oblicua": "vista oblicua",
                 "rasante": "vista rasante, casi a ras del suelo", "cerca": "más cerca", "lejos": "más lejos"}
MAX_PASO = guion_presentacion.MAX_PASOS
# Las reglas de lo que se proyecta viven en app/proyectable.py (también las usan el recorrido y la pantalla en off): la
# presentación que se maneja es siempre la técnica, así que la explicación tampoco lleva costos
_explicacion_visible = texto_proyectable


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
Rumbo = Annotated[int, Field(ge=0, le=359), BeforeValidator(_paso_no_booleano)]


def _con_tope(maximo: int):
    """Un texto del recorrido: las reglas de lo que se proyecta (sin costos, como la explicación), con su tope."""
    return lambda v: texto_proyectable(v, maximo)


Narracion = Annotated[str, Field(min_length=1, max_length=rec.MAX_NARRACION),
                      AfterValidator(_con_tope(rec.MAX_NARRACION))]
TituloRecorrido = Annotated[str, Field(min_length=3, max_length=rec.MAX_TITULO), AfterValidator(_con_tope(rec.MAX_TITULO))]
PuntoCierre = Annotated[str, Field(min_length=3, max_length=rec.MAX_PUNTO), AfterValidator(_con_tope(rec.MAX_PUNTO))]
Sugerencia = Annotated[str, Field(min_length=3, max_length=rec.MAX_SUGERENCIA),
                       AfterValidator(_con_tope(rec.MAX_SUGERENCIA))]


def _volver_al_paso(v: Any, campo: str) -> Any:
    """«paso» (enfoque, inmersion) y «cerrar» (detalle) vuelven a lo del paso: quedan en None, pero la clave llegó."""
    palabras = ("cerrar", "ninguna", "ninguno") if campo == "detalle" else ("paso",)
    return None if isinstance(v, str) and guion_presentacion.clave(v) in palabras else v


class ResaltarEntrada(_Entrada):
    """Lo que una escena señala en pantalla mientras lo nombra: exactamente uno."""
    cifra: Annotated[int, Field(ge=1, le=rec.RESALTAR["cifra"]), BeforeValidator(_paso_no_booleano)] | None = Field(
        None, description="La cifra grande n del panel (desde 1, en el orden del paso)")
    punto: Annotated[int, Field(ge=1, le=rec.RESALTAR["punto"]), BeforeValidator(_paso_no_booleano)] | None = Field(
        None, description="El punto n de la lista del panel (en el paso de metas, la meta n)")
    leyenda: Annotated[int, Field(ge=1, le=rec.RESALTAR["leyenda"]), BeforeValidator(_paso_no_booleano)] | None = Field(
        None, description="La fila n de la leyenda de la maqueta")
    especificacion: Annotated[int, Field(ge=1, le=rec.RESALTAR["especificacion"]),
                              BeforeValidator(_paso_no_booleano)] | str | None = Field(None, description=(
        "La especificación por su nombre («Estructura») o número: de la ficha abierta (detalle) o, sin ficha, de la hoja "
        "del panel en un paso de componente"))
    componente: str | None = Field(None, min_length=1, max_length=80, description=(
        "La tarjeta de un componente (id o nombre), en el paso de componentes"))

    @model_validator(mode="after")
    def _uno(self):
        if len(self.model_fields_set) != 1 or any(getattr(self, k) is None for k in self.model_fields_set):
            raise ValueError("resaltar lleva exactamente una de: cifra, punto, leyenda, especificacion o componente")
        return self


class EscenaEntrada(_Entrada):
    """Una escena del recorrido: una idea, lo que se dice y lo que se ve mientras se dice (un cambio sobre la escena
    anterior; al cambiar de paso lo visual vuelve a lo del paso)."""
    narracion: Narracion = Field(..., description=(
        "Lo que se dice mientras se ve esta escena: se proyecta y se lee en voz alta. Una o dos frases habladas (hasta "
        "220 caracteres), sobre lo que la escena muestra; sin costos, «@» ni números de 7 o más dígitos"))
    capitulo: str | None = Field(None, min_length=2, max_length=60, description=(
        "Id o nombre del capítulo (obligatorio en la primera escena; las demás siguen en el de la anterior)"))
    paso: PasoNumero | PasoId | None = Field(None, description="Número del paso desde 1 o su id; sin él, el mismo paso")
    panel: StrictBool | None = Field(None, description="false deja solo la maqueta 3D («Solo 3D»); se hereda")
    enfoque: str | None = Field(None, min_length=1, max_length=80, description=(
        "La cámara va a un componente con lugar en la maqueta (id o nombre); paso vuelve al encuadre del paso"))
    detalle: str | None = Field(None, min_length=1, max_length=80, description=(
        "Abre la ficha técnica de un componente (id o nombre); cerrar la cierra"))
    comparar: Literal["hoy", "proyecto"] | None = Field(None, description=(
        "hoy: el sitio como está, sin el proyecto, en el mismo encuadre; proyecto lo devuelve"))
    camara: Literal[CAMARAS] | None = Field(None, description="paso, aerea, oblicua, rasante, cerca o lejos")
    rumbo: Rumbo | None = Field(None, description="Desde dónde se mira, en grados desde el norte (180: el norte arriba)")
    girar: StrictBool | None = Field(None, description="true: la cámara gira despacio")
    inmersion: str | None = Field(None, min_length=1, max_length=80, description=(
        "Un modelo 3D del atlas del catálogo (id o nombre); maqueta lo cierra; paso, lo que diga el paso"))
    resaltar: ResaltarEntrada | None = Field(None, description="Señala en pantalla lo que la narración nombra")
    sostener: float | None = Field(None, ge=0, le=8, description=(
        "Segundos que la imagen se queda después de narrar (por omisión 1,1, o 2,7 si hay algo que mirar)"))

    @field_validator("enfoque", "inmersion", "detalle", mode="before")
    @classmethod
    def _volver(cls, v, info):
        return _volver_al_paso(v, info.field_name)


class CierreEntrada(_Entrada):
    puntos: list[PuntoCierre] = Field(..., min_length=1, max_length=rec.MAX_PUNTOS, description=(
        "Dos o tres ideas que quedan en la sala al final (hasta 80 caracteres cada una)"))

    @model_validator(mode="after")
    def _largo(self):
        if sum(len(x) for x in self.puntos) > rec.MAX_CIERRE:
            raise ValueError(f"Los puntos del cierre juntos pasan de {rec.MAX_CIERRE} caracteres: acórtelos")
        return self


class PresentacionEntrada(_Entrada):
    op: Literal[OPS_PRESENTACION] = Field(..., description=(
        "indice: los capítulos y los títulos de sus pasos; ir: a un capítulo y paso (devuelve lo que muestra ese paso); "
        "siguiente o anterior: un paso (con capitulo y paso de partida, los del contexto del panel, devuelve el paso "
        "de destino); explicar: muestra una o dos frases cortas en pantalla; quitar_explicacion: la quita; vista: lo "
        "que se ve sin cambiar de paso (panel, indice, fichas); pantalla_completa: la presentación llena la ventana "
        "(activar) o vuelve a la vista con el menú; estado: qué muestra la pantalla en off y si está abierta"))
    capitulo: str | None = Field(None, min_length=2, max_length=60, description=(
        "Id o nombre del capítulo (del índice o del contexto del panel)"))
    paso: PasoNumero | PasoId | None = Field(None, description="Número del paso desde 1, o su id (del índice)")
    explicacion: Explicacion | None = Field(None, description=(
        "Una o dos frases cortas para la pantalla (se proyecta; hasta 220 caracteres): sin datos de habitantes, costos, "
        "«@» ni números de 7 o más dígitos"))
    panel: StrictBool | None = Field(None, description=(
        "vista: true muestra el panel de texto del paso; false deja solo la maqueta 3D («Solo 3D»)"))
    indice: StrictBool | None = Field(None, description="vista: true abre el índice de capítulos; false lo cierra")
    fichas: StrictBool | None = Field(None, description=(
        "vista: true abre las fichas de los proyectos (costos, financiación y metas de cada módulo); false las cierra"))
    activar: StrictBool | None = Field(None, description=(
        "pantalla_completa: true, la presentación llena la ventana, sin el menú ni las barras del panel; false, vuelve"))
    # visual: «paso» (enfoque, inmersion) y «cerrar» (detalle) vuelven a lo del paso: quedan en None, pero la clave llegó
    # (por eso se mira qué claves llegaron). El esquema para el modelo no tiene null
    enfoque: str | None = Field(None, min_length=1, max_length=80, description=(
        "visual: la cámara va a un componente del capítulo (su id o su nombre; los que tienen lugar en la maqueta, del "
        "indice o de ir); paso vuelve al encuadre del paso"))
    camara: Literal[CAMARAS] | None = Field(None, description=(
        "visual: paso (el encuadre del paso, también su rumbo), aerea (desde arriba), oblicua, rasante (casi a ras del "
        "suelo), cerca o lejos"))
    rumbo: Annotated[int, Field(ge=0, le=359), BeforeValidator(_paso_no_booleano)] | None = Field(None, description=(
        "visual: desde dónde mira la cámara, en grados desde el norte en sentido horario (0 desde el norte, 90 desde el "
        "oriente, 180 desde el sur: el norte queda arriba)"))
    girar: StrictBool | None = Field(None, description="visual: true, la cámara gira despacio alrededor de lo que muestra")
    comparar: Literal["hoy", "proyecto"] | None = Field(None, description=(
        "visual: hoy muestra el sitio como está, sin el proyecto, en el mismo encuadre; proyecto lo devuelve"))
    detalle: str | None = Field(None, min_length=1, max_length=80, description=(
        "visual: abre la ficha técnica de un componente del capítulo (id o nombre); cerrar la cierra"))
    inmersion: str | None = Field(None, min_length=1, max_length=80, description=(
        "visual: abre un modelo 3D del atlas (id o nombre del catálogo de indice: la torre del hospital en su sitio, por "
        "pisos, por dentro, el laboratorio, el simulador sísmico, el modelo BIM, el relleno hoy y el parque); maqueta "
        "vuelve a la maqueta en un paso que muestra un modelo; paso, lo que diga el paso"))
    tema: Literal["claro", "oscuro"] | None = Field(None, description="visual: el tema de la pantalla (para el proyector)")
    titulo: TituloRecorrido | None = Field(None, description="recorrido: el título que se ve en la sala (3 a 80)")
    escenas: list[EscenaEntrada] | None = Field(None, min_length=1, max_length=rec.MAX_ESCENAS, description=(
        "recorrido: de 3 a 6 escenas (hasta 8), una idea cada una"))
    cierre: CierreEntrada | None = Field(None, description="recorrido: dos o tres ideas que quedan en la sala")
    sugerencias: list[Sugerencia] | None = Field(None, max_length=rec.MAX_SUGERENCIAS, description=(
        "recorrido: hasta 3 próximos pasos, solo para el chat (no se proyectan)"))
    accion: Literal[rec.CONTROLES] | None = Field(None, description=(
        "control_recorrido: pausar, continuar, siguiente, anterior, repetir, reproducir (otra vez, desde el comienzo) o "
        "detener"))

    @field_validator("enfoque", "inmersion", "detalle", mode="before")
    @classmethod
    def _volver_al_paso(cls, v, info):
        return _volver_al_paso(v, info.field_name)

    def partes_visuales(self) -> dict:
        """Las partes de `visual` que llegaron (también las que llegaron en null: vuelven a lo del paso)."""
        return {k: getattr(self, k) for k in PARTES_VISUAL if k in self.model_fields_set}

    @model_validator(mode="after")
    def _segun_op(self):
        vista, completa, visual = PARTES_VISTA, ("activar",), PARTES_VISUAL
        propias = {"recorrido": PARTES_RECORRIDO, "control_recorrido": ("accion",)}.get(self.op, ())
        ajenas = [k for k in (*PARTES_RECORRIDO, "accion") if k not in propias and getattr(self, k) is not None]
        if ajenas:
            raise ValueError(f"La operación {self.op} no usa: {', '.join(ajenas)}")
        sobran = {"indice": ("capitulo", "paso", "explicacion", *vista, *completa),
                  "guion": ("explicacion", *vista, *completa),
                  "recorrido": ("capitulo", "paso", "explicacion", *vista, *completa),
                  "control_recorrido": ("capitulo", "paso", "explicacion", *vista, *completa),
                  "quitar_explicacion": ("capitulo", "paso", "explicacion", *vista, *completa),
                  "estado": ("capitulo", "paso", "explicacion", *vista, *completa),
                  "explicar": ("capitulo", "paso", *vista, *completa),
                  "vista": ("capitulo", "paso", "explicacion", *completa),
                  "visual": ("paso", "explicacion", *vista, *completa),
                  "pantalla_completa": ("capitulo", "paso", "explicacion", *vista)}.get(self.op, (*vista, *completa))
        malos = [k for k in sobran if getattr(self, k) is not None]
        if self.op != "visual":
            malos += [k for k in visual if k in self.model_fields_set]
        if malos:
            raise ValueError(f"La operación {self.op} no usa: {', '.join(malos)}")
        if self.op == "visual":
            partes = self.partes_visuales()
            if not partes:
                raise ValueError("Para visual, diga qué cambiar: enfoque, camara, rumbo, girar, comparar, detalle, "
                                 "inmersion o tema")
            nulos = [k for k in ("camara", "rumbo", "girar", "comparar", "tema") if k in partes and partes[k] is None]
            if nulos:
                raise ValueError(f"En visual, {', '.join(nulos)} no va vacío: diga el valor (camara: paso vuelve al "
                                 "encuadre y al rumbo del paso; comparar: proyecto)")
        if self.op == "vista":
            if all(getattr(self, k) is None for k in PARTES_VISTA):
                raise ValueError("Para vista, diga qué mostrar: panel, indice o fichas (true o false)")
            if self.indice is True and self.fichas is True:
                raise ValueError("El índice y las fichas tapan la presentación: no se abren a la vez")
        if self.op == "pantalla_completa" and self.activar is None:
            raise ValueError("Para pantalla_completa, diga activar: true (llenar la ventana) o false (volver)")
        if self.op == "ir" and self.capitulo is None:
            raise ValueError("Para ir, indique el capítulo (id o nombre, del índice)")
        if self.op in ("siguiente", "anterior") and (self.capitulo is None) != (self.paso is None):
            raise ValueError("Para avanzar desde un paso, indique capitulo y paso de partida (los del contexto del "
                             "panel), o ninguno de los dos")
        if self.op == "explicar" and self.explicacion is None:
            raise ValueError("Para explicar, escriba la explicacion")
        if self.op == "guion" and self.capitulo is None:
            raise ValueError("Para guion, indique el capítulo (id o nombre, del índice)")
        if self.op == "recorrido" and (self.titulo is None or not self.escenas):
            raise ValueError("Para recorrido, escriba el titulo y las escenas (de 3 a 6, una idea cada una)")
        if self.op == "recorrido" and self.escenas[0].capitulo is None:
            raise ValueError("La primera escena del recorrido dice su capitulo")
        if self.op == "control_recorrido" and self.accion is None:
            raise ValueError("Para control_recorrido, diga la accion: pausar, continuar, siguiente, anterior, repetir, "
                             "reproducir o detener")
        return self


def _esquema_presentacion() -> dict:
    """El esquema de la entrada sin la rama «null» del paso (número o id): el modelo simplemente omite la clave."""
    s = esquema(PresentacionEntrada)
    escena = s["properties"]["escenas"].get("items") or {}
    for paso in (s["properties"]["paso"], (escena.get("properties") or {}).get("paso") or {}):
        if "anyOf" in paso:
            paso["anyOf"] = [r for r in paso["anyOf"] if r != {"type": "null"}]
            paso.pop("default", None)
    return s


def _cap_para_modelo(c: dict) -> dict:
    return {"id": c["id"], "nombre": c["nombre"]}


def _componente_para_modelo(x: dict) -> dict:
    """La ficha técnica de un componente del guion (sin plata), para que el modelo la explique."""
    return {k: v for k, v in x.items() if k != "enfoque"} | {"lugar_en_la_maqueta": bool(x.get("enfoque"))}


def _resolver_componente(g: guion_presentacion.Guion, ci: int, texto: str, con_lugar: bool) -> dict:
    x = g.componente(ci, texto)
    c = g.capitulos[ci]
    candidatos = [{"id": k["id"], "nombre": k["nombre"]} for k in g.componentes(ci) if not con_lugar or k.get("enfoque")]
    if x is None:
        raise ErrorHerramienta(f"El capítulo {c['nombre']} no tiene el componente «{texto}».", "no_existe", estado=404,
                               detalle={"capitulo": c["id"], "componentes": candidatos})
    if con_lugar and not x.get("enfoque"):
        raise ErrorHerramienta(f"«{x['nombre']}» no tiene un lugar propio en la maqueta: muestre su ficha (detalle).",
                               "invalido", estado=422, detalle={"capitulo": c["id"], "con_lugar": candidatos})
    return x


def _resolver_inmersion(g: guion_presentacion.Guion, texto: str) -> dict | None:
    if guion_presentacion.clave(texto) == "maqueta":
        return None
    i = g.inmersion(texto)
    if i is None:
        raise ErrorHerramienta(f"La presentación no tiene la inmersión «{texto}».", "no_existe", estado=404,
                               detalle={"inmersiones": [{"id": k["id"], "nombre": k.get("nombre")}
                                                        for k in g.inmersiones]})
    return i


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


async def cargar_guion() -> guion_presentacion.Guion:
    try:
        g = await run_in_threadpool(guion_presentacion.cargar)
    except ValueError:
        g = None
    if g is None:
        raise ErrorHerramienta("La presentación de la propuesta no está disponible en este servidor.", "no_existe",
                               estado=404)
    return g


def _paso_para_modelo(g: guion_presentacion.Guion, ci: int, pi: int) -> dict:
    c = g.capitulos[ci]
    n = len(c["pasos"])
    out = {"capitulo": _cap_para_modelo(c), "paso": pi + 1, "de": n,
           "posicion": f"Paso {pi + 1} de {n} del capítulo {c['nombre']}", "guion": c["pasos"][pi]}
    if c.get("componentes"):
        # lo que se puede mostrar con visual en este capítulo (enfoque solo los que tienen lugar en la maqueta)
        out["componentes"] = [{"id": x["id"], "nombre": x["nombre"], "lugar_en_la_maqueta": bool(x.get("enfoque"))}
                              for x in c["componentes"]]
    return out


def _estado_para_modelo(doc: dict | None, e: dict, g: guion_presentacion.Guion, abierta: bool) -> dict:
    ci = g.por_id(e["capitulo"])
    out = {"abierta": abierta, "muestra": pantalla_off.describir(e, g), "capitulo": e["capitulo"], "paso": e["paso"],
           "de": len(g.capitulos[ci]["pasos"]), "explicacion": e["explicacion"], "panel": e["panel"],
           "indice": e["indice"], "fichas": e["fichas"], "llena_la_ventana": e["completa"],
           "visual": {k: e[k] for k in PARTES_VISUAL}}
    if doc and doc.get("por") in pantalla_off.ORIGENES:
        out["cambiada_por"] = {"asistente": "el asistente del panel", "mcp": "un agente por MCP",
                               "panel": "los controles del panel"}[doc["por"]]
    r = pantalla_off.resumen_recorrido(doc, g)
    if r:
        out["recorrido"] = {**r, "muestra": pantalla_off.describir_recorrido(r)}
    return out


NOTA_PANTALLA_ABIERTA = ("Se ve en la pantalla en off de la persona (la vista Presentación en modo en off, abierta en el "
                         "proyector o en otra pantalla).")
NOTA_SIN_PANTALLA = ("No hay ninguna pantalla en off abierta: queda guardado y se verá cuando la persona abra la vista "
                     "Presentación en modo en off (botón «Pantalla en off» de la vista, en el proyector o en otra "
                     "pantalla).")


async def presentacion_en_pantalla(db: Any, uid: int, a: PresentacionEntrada, por: str) -> Resultado:
    """La herramienta `presentacion` del asistente del panel (`por` = asistente) y del servidor MCP (`por` = mcp).

    Cambia la pantalla en off de la persona (`app/pantalla.py`) y devuelve lo que el modelo necesita para explicarla. Con
    el asistente, además, la acción para la vista Presentación de la pestaña del chat, como siempre, salvo que haya una
    pantalla en off abierta: entonces la que cambia es esa y la pestaña del chat no se mueve (la persona puede estar
    escribiendo desde el celular). Sin pantalla abierta, «siguiente» y «anterior» sin punto de partida los calcula la
    vista de la pestaña del chat (no se sabe desde dónde): la pantalla en off no cambia. Con MCP, o con una pantalla
    abierta, se calculan desde la pantalla en off.

    Con un recorrido sonando, todo parte de la escena que la sala está viendo (no de la base guardada, que es su última
    escena), y una orden que cambia lo que se ve lo cierra recién cuando ya no puede fallar: un capítulo que no existe o
    un componente mal escrito vuelve con su error y la narración sigue."""
    g = await cargar_guion()
    if a.op == "indice":
        return Resultado({**g.indice(), "nota": (
            "Para mostrar un paso, op ir con su capitulo (id) y paso (número desde 1). Lo que se ve en cada paso le "
            "llega al ir.")}, f"Índice de la presentación ({len(g)} capítulos)")
    if a.op == "guion":
        ci = _resolver_capitulo(g, a.capitulo)
        c = g.capitulos[ci]
        return Resultado({**g.capitulo_para_leer(ci), "nota": NOTA_GUION},
                         f"Guion de {c['nombre']} · {len(c['pasos'])} pasos, {len(c.get('componentes') or [])} componentes")
    doc = await run_in_threadpool(pantalla_off.leer, db, uid)
    abierta = pantalla_off.conectada(doc)
    desde_pantalla = abierta or por == "mcp"
    if a.op == "recorrido":
        return await _recorrido(db, uid, g, a, por, abierta, doc)
    if a.op == "control_recorrido":
        return await _control_recorrido(db, uid, g, a, por, abierta)
    e = pantalla_off.estado(pantalla_off.a_la_vista(doc, g), g)
    if a.op == "estado":
        return Resultado({"pantalla": _estado_para_modelo(doc, e, g, abierta), "nota": (
            NOTA_PANTALLA_ABIERTA if abierta else NOTA_SIN_PANTALLA)},
            "La pantalla en off está abierta" if abierta else "No hay una pantalla en off abierta")
    extra = {"explicacion": a.explicacion} if a.explicacion else {}
    accion: dict | None = None
    cambios: dict = {}
    if a.op == "explicar":
        contenido: dict[str, Any] = {"en_pantalla": a.explicacion, "nota": (
            "Se muestra sobre la presentación, en el paso que esté abierto. Explique en el chat con más detalle.")}
        resumen = "Mostré una explicación en la presentación"
        accion, cambios = {"tipo": "presentacion", "op": "explicar", **extra}, {"explicacion": a.explicacion}
    elif a.op == "quitar_explicacion":
        contenido, resumen = {"nota": "Se quitó la explicación de la pantalla."}, "Quité la explicación de la presentación"
        accion, cambios = {"tipo": "presentacion", "op": "quitar_explicacion"}, {"explicacion": None}
    elif a.op == "vista":
        cambios = {k: getattr(a, k) for k in PARTES_VISTA if getattr(a, k) is not None}
        if cambios.get("indice"):
            cambios["fichas"] = False
        if cambios.get("fichas"):
            cambios["indice"] = False
        pedido = {k: getattr(a, k) for k in PARTES_VISTA if getattr(a, k) is not None}
        # (con false, con true)
        nombres = {"panel": ("solo la maqueta 3D", "el panel de texto"), "indice": ("sin el índice", "el índice"),
                   "fichas": ("sin las fichas", "las fichas")}
        lo_que = ", ".join(nombres[k][int(v)] for k, v in pedido.items())
        contenido = {"vista": pedido, "nota": "La presentación sigue en el mismo paso; solo cambia lo que se ve."}
        resumen = f"La presentación muestra {lo_que}"
        accion = {"tipo": "presentacion", "op": "vista", **pedido}
    elif a.op == "visual":
        contenido, resumen, cambios = _visual(g, e, a, desde_pantalla)
        accion = {"tipo": "presentacion", "op": "visual", **cambios}
    elif a.op == "pantalla_completa":
        cambios = {"completa": a.activar, "orden_completa": time.time_ns() // 1_000_000}
        contenido = {"llena_la_ventana": a.activar, "nota": (
            "La presentación llena la ventana, sin el menú ni las barras del panel (la tecla Escape la devuelve en esa "
            "pantalla). Para la pantalla completa del navegador, F11 en ese equipo." if a.activar else
            "La presentación vuelve a la vista del panel, con el menú y su barra.")}
        resumen = "La presentación llena la ventana" if a.activar else "La presentación volvió a la vista del panel"
        accion = {"tipo": "presentacion", "op": "pantalla_completa", "activar": a.activar}
    elif a.op in ("siguiente", "anterior") and a.capitulo is None and not desde_pantalla:
        # Sin el punto de partida la presentación calcula el paso; el modelo lo ve en el contexto del próximo mensaje. La
        # pantalla en off no cambia, pero el recorrido que suena se detiene igual
        detener = await _colapsar(db, uid, g, doc, por)
        return Resultado({"nota": (
            f"La presentación pasa al paso {'siguiente' if a.op == 'siguiente' else 'anterior'} desde donde esté. Para "
            "saber cuál es (y recibir lo que muestra), use ir o indique capitulo y paso de partida.")},
            f"Pasé al paso {'siguiente' if a.op == 'siguiente' else 'anterior'} de la presentación",
            acciones=[*detener, {"tipo": "presentacion", "op": a.op, **extra}])
    else:
        if a.op in ("siguiente", "anterior") and a.capitulo is None:
            ci, pi = g.por_id(e["capitulo"]), e["paso"] - 1   # desde donde está la pantalla en off
        else:
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
        contenido = {**_paso_para_modelo(g, ci, pi), "nota": (
            "Es lo que muestra la presentación en ese paso: explíquelo en el chat con esos datos (no invente otros). En "
            "pantalla, si hace falta, solo una o dos frases cortas (explicar, hasta 220 caracteres).")}
        if aviso:
            contenido["aviso"] = aviso
        resumen = f"Mostré {c['nombre']} · paso {pi + 1} de {len(c['pasos'])}"
        accion = {"tipo": "presentacion", "op": "ir", "capitulo": c["id"], "paso": pi + 1, **extra}
        # Cambiar de paso quita la explicación anterior, cierra el índice y las fichas y deja lo visual como lo dice el
        # paso, salvo el tema (como mando.js y visual.js)
        cambios = {"capitulo": c["id"], "paso": pi + 1, "explicacion": a.explicacion or None, "indice": False,
                   "fichas": False, **pantalla_off.VISUAL_INICIAL}
    # Ya resuelta (nada más puede fallar): cierra el recorrido que sonaba, con la escena en curso como base, y encima
    # guarda lo pedido
    detener = await _colapsar(db, uid, g, doc, por) if a.op in COLAPSAN else []
    await run_in_threadpool(pantalla_off.guardar, db, uid, cambios, por)
    if desde_pantalla:
        contenido["pantalla"] = NOTA_PANTALLA_ABIERTA if abierta else NOTA_SIN_PANTALLA
    return Resultado(contenido, resumen,
                     acciones=[*detener, *([accion] if accion and not abierta and por == "asistente" else [])])


async def _colapsar(db: Any, uid: int, g: guion_presentacion.Guion, doc: dict | None, por: str) -> list[dict]:
    """Cierra el recorrido que sonaba cuando se leyó `doc` (si sigue siendo ese: uno que llegó entretanto no se toca),
    con la escena en curso como base. Si sonaba en la pestaña o el proyector del asistente, devuelve la acción que lo
    detiene allá, haya o no una pantalla en off abierta (la orden misma no siempre va al navegador, y un avance sin
    recorrido vigente solo lo detiene en la próxima frase). La pantalla en off se entera sola: le llega sin recorrido."""
    r = pantalla_off.recorrido_de(doc, g)
    if not r or r["cerrado"]:
        return []
    cerrado = await run_in_threadpool(pantalla_off.colapsar, db, uid, g, por, r["id"])
    if cerrado is None or r["destino"] != "vista" or por != "asistente":
        return []
    return [{"tipo": "presentacion", "op": "control_recorrido", "rid": r["id"], "accion": "detener", "motivo": "otra_orden"}]


def _visual(g: guion_presentacion.Guion, e: dict, a: PresentacionEntrada, desde_pantalla: bool) -> tuple[dict, str, dict]:
    """La op `visual`: resuelve contra el guion lo que se pidió (los componentes del capítulo, por id o por nombre, y la
    inmersión del catálogo) y devuelve (lo que recibe el modelo, el resumen, los cambios exactos para la pantalla y el
    navegador). El capítulo es el que se indicó (el del contexto del panel) o el de la pantalla en off."""
    partes = a.partes_visuales()
    ci = g.por_id(e["capitulo"])
    if a.capitulo is not None:
        pedido = _resolver_capitulo(g, a.capitulo)
        # la pantalla en off (o la que maneja un agente por MCP) muestra su capítulo: lo visual va sobre ese
        if desde_pantalla and pedido != ci:
            raise ErrorHerramienta(
                f"La pantalla muestra el capítulo {g.capitulos[ci]['nombre']} ({g.capitulos[ci]['id']}), no "
                f"{g.capitulos[pedido]['nombre']}: vaya primero a ese capítulo con ir.", "invalido", estado=409,
                detalle={"en_pantalla": _cap_para_modelo(g.capitulos[ci])})
        ci = pedido
    c = g.capitulos[ci]
    contenido: dict[str, Any] = {"capitulo": _cap_para_modelo(c)}
    cambios: dict[str, Any] = {}
    dicho: list[str] = []
    for k in ("enfoque", "detalle"):
        if k not in partes:
            continue
        if partes[k] is None:
            cambios[k] = None
            dicho.append("la cámara vuelve al encuadre del paso" if k == "enfoque" else "cerré la ficha técnica")
            continue
        x = _resolver_componente(g, ci, partes[k], con_lugar=k == "enfoque")
        cambios[k] = x["id"]
        contenido["componente"] = _componente_para_modelo(x)
        dicho.append(f"la cámara en «{x['nombre']}»" if k == "enfoque" else f"la ficha técnica de «{x['nombre']}»")
    if "inmersion" in partes:
        if partes["inmersion"] is None:
            cambios["inmersion"] = None
            dicho.append("lo que muestra el paso (maqueta o modelo del atlas)")
        else:
            i = _resolver_inmersion(g, partes["inmersion"])
            cambios["inmersion"] = i["id"] if i else "maqueta"
            if i:
                contenido["inmersion"] = i
                dicho.append(f"el modelo del atlas «{i.get('nombre')}»")
            else:
                dicho.append("la maqueta 3D del territorio")
    for k in ("camara", "rumbo", "girar", "comparar", "tema"):
        if k in partes:
            cambios[k] = partes[k]
    if cambios.get("camara") == "paso" and "rumbo" not in partes:
        cambios["rumbo"] = None   # el encuadre del paso es también su rumbo
    if "camara" in cambios:
        dicho.append(NOMBRE_CAMARA[cambios["camara"]])
    if "rumbo" in cambios:
        dicho.append("el rumbo del paso" if cambios["rumbo"] is None else f"mirando desde el rumbo {cambios['rumbo']}°")
    if "girar" in cambios:
        dicho.append("la cámara gira" if cambios["girar"] else "la cámara quieta")
    if "comparar" in cambios:
        dicho.append("el sitio como está hoy" if cambios["comparar"] == "hoy" else "con el proyecto")
    if "tema" in cambios:
        dicho.append(f"tema {cambios['tema']}")
    contenido["nota"] = (
        "Cambia lo que se ve sin cambiar de paso; al pasar a otro paso vuelve a lo del paso (salvo el tema). Explique "
        "en el chat con los datos de la ficha (no invente otros)." + (
            "" if desde_pantalla or a.capitulo is not None else
            " Sin el capítulo de partida se tomó el de la pantalla en off: si la presentación de la pestaña está en "
            "otro capítulo, indique capitulo (el del contexto del panel)."))
    return contenido, "La presentación muestra " + ", ".join(dicho), cambios


# ───────────────────────────── el recorrido narrado ─────────────────────────────

NOTA_GUION = (
    "Para presentar, arme UN recorrido (op recorrido) de 3 a 6 escenas con este arco, omitiendo lo que no aplique: "
    "1) ubicar (el paso, cámara aerea u oblicua); 2) cómo está hoy (comparar hoy o la inmersión de hoy); 3) qué se "
    "construye (comparar proyecto, enfoque, resaltar la leyenda); 4) cómo funciona o el dato clave (detalle con la "
    "especificación resaltada, una inmersión, un punto de la lista); 5) qué cambia y cuándo (la meta o la cifra "
    "resaltada); y un cierre de 2 o 3 ideas. Cada escena: una idea, una o dos frases habladas que nombran lo que se ve "
    "en ese momento, con las cifras tal como vienen aquí y sin costos. Lo que se puede resaltar en cada paso está en "
    "«resaltable». Ejemplo: {\"op\":\"recorrido\",\"titulo\":\"La torre del hospital\",\"escenas\":[{\"capitulo\":"
    "\"salud\",\"paso\":\"torre\",\"camara\":\"oblicua\",\"narracion\":\"…\"},{\"detalle\":\"torre\",\"resaltar\":"
    "{\"especificacion\":\"Estructura\"},\"narracion\":\"…\"}],\"cierre\":{\"puntos\":[\"…\",\"…\"]}}")
NOTA_RECORRIDO = (
    "La sala ya lo está viendo y oyendo, escena por escena. En el chat no repita la narración: complemente en 3 a 6 líneas "
    "con datos del guion que no se dijeron y termine con una pregunta. Si la persona escribe, el recorrido se pausa: "
    "responda breve y siga con control_recorrido (continuar) o arme otro recorrido.")
HACE = {"paso": "cambia de paso", "camara": "mueve la cámara", "enfoque": "enfoca una obra", "ficha": "abre una ficha",
        "hoy": "muestra hoy", "proyecto": "muestra el proyecto", "modelo": "abre un modelo del atlas",
        "resaltar": "resalta", "solo3d": "solo 3D", "girar": "gira"}
_NUMERO = re.compile(r"\d[\d.,]*\d|\d")


def _con_escena(e: ErrorHerramienta, n: int) -> ErrorHerramienta:
    """El error de una escena, con su número al comienzo y en el detalle (el modelo corrige esa)."""
    return ErrorHerramienta(f"Escena {n}: {e}", e.codigo, estado=e.estado, detalle={"escena": n, **(e.detalle or {})})


def _resolver_resaltar(g: guion_presentacion.Guion, ci: int, pi: int, visual: dict, panel: bool,
                       r: ResaltarEntrada | None) -> dict | None:
    """El resaltado absoluto de una escena (`recorrido.RESALTAR_TIPOS`), contra lo que muestra el paso o la ficha."""
    if r is None:
        return None
    tipo = next(iter(r.model_fields_set))
    valor = getattr(r, tipo)
    hay = g.resaltable(ci, pi)
    titulo = g.capitulos[ci]["pasos"][pi]["titulo"]
    if not panel and tipo not in ("leyenda", "especificacion"):
        raise ErrorHerramienta("Con «Solo 3D» (panel false) solo se resalta la leyenda o la ficha técnica.", "invalido",
                               estado=422)
    if tipo == "componente":
        x = g.componente(ci, valor)
        if x is None or x["id"] not in hay.get("componentes", []):
            raise ErrorHerramienta("Las tarjetas de componentes solo están en el paso «componentes» del capítulo: "
                                   "para señalar una obra en otro paso use enfoque o detalle.", "invalido", estado=422,
                                   detalle={"componentes": hay.get("componentes", [])})
        return {"tipo": "componente", "id": x["id"]}
    if tipo == "especificacion":
        en = "ficha" if visual["detalle"] else "panel"
        nombres = g.especificaciones(ci, visual["detalle"]) if en == "ficha" else hay["especificaciones"]
        if not panel and en == "panel":
            raise ErrorHerramienta("Con «Solo 3D» la hoja del panel no se ve: abra la ficha (detalle).", "invalido",
                                   estado=422)
        if isinstance(valor, int):
            n = valor if valor <= len(nombres) else None
        else:
            n = next((i + 1 for i, x in enumerate(nombres) if guion_presentacion.clave(x) == guion_presentacion.clave(valor)),
                     None)
        if n is None:
            donde = "la ficha abierta" if en == "ficha" else f"el panel del paso «{titulo}»"
            raise ErrorHerramienta(f"{donde[0].upper()}{donde[1:]} no tiene la especificación «{valor}»; tiene "
                                   f"{', '.join(nombres) or 'ninguna (abra una ficha con detalle)'}.", "invalido",
                                   estado=422, detalle={"especificaciones": nombres})
        return {"tipo": "especificacion", "n": n, "en": en}
    cuantos = {"cifra": hay["cifras"], "punto": hay["puntos"], "leyenda": hay["leyenda"]}[tipo]
    if valor > cuantos:
        raise ErrorHerramienta(f"El paso «{titulo}» tiene {cuantos} {tipo}{'s' if cuantos != 1 else ''} para resaltar, "
                               f"no la {valor}.", "invalido", estado=422, detalle={"resaltable": hay})
    return {"tipo": tipo, "n": valor}


def _componer(g: guion_presentacion.Guion, a: PresentacionEntrada) -> dict:
    """Las escenas del modelo (cada una un cambio sobre la anterior) como recorrido absoluto, resueltas contra el guion
    con los mismos resolutores de ir y visual. Todo o nada: el primer error, con su número de escena."""
    escenas: list[dict] = []
    ci = pi = None
    panel, visual = True, dict(rec.VISUAL_INICIAL)
    for n, x in enumerate(a.escenas, 1):
        try:
            if x.capitulo is not None:
                nci = _resolver_capitulo(g, x.capitulo)
                # el modelo suele repetir el capítulo en cada escena: sin paso, en el mismo capítulo sigue en el mismo
                # paso (como promete el esquema); en otro capítulo, o en la primera escena, va al primero
                npi = pi if x.paso is None and nci == ci else _resolver_paso(g, nci, x.paso)
            elif x.paso is not None:
                nci, npi = ci, _resolver_paso(g, ci, x.paso)
            else:
                nci, npi = ci, pi
            if (nci, npi) != (ci, pi):
                visual = dict(rec.VISUAL_INICIAL)   # otro paso: lo visual vuelve a lo del paso (visual.js, pantalla)
            ci, pi = nci, npi
            partes = {k: getattr(x, k) for k in rec.VISUAL if k in x.model_fields_set}
            for k in ("enfoque", "detalle"):
                if partes.get(k) is not None:
                    partes[k] = _resolver_componente(g, ci, partes[k], con_lugar=k == "enfoque")["id"]
            if partes.get("inmersion") is not None:
                i = _resolver_inmersion(g, partes["inmersion"])
                partes["inmersion"] = i["id"] if i else "maqueta"
            nulos = [k for k in ("camara", "rumbo", "girar", "comparar") if k in partes and partes[k] is None]
            if nulos:
                raise ErrorHerramienta(f"{', '.join(nulos)} no va vacío: diga el valor.", "invalido", estado=422)
            if partes.get("camara") == "paso" and "rumbo" not in partes:
                partes["rumbo"] = None
            visual = {**visual, **partes}
            if x.panel is not None:
                panel = x.panel
            resaltar = _resolver_resaltar(g, ci, pi, visual, panel, x.resaltar)
        except ErrorHerramienta as e:
            raise _con_escena(e, n) from None
        esc = {"capitulo": g.capitulos[ci]["id"], "paso": pi + 1, "panel": panel, "visual": dict(visual),
               "resaltar": resaltar, "frases": rec.partir_frases(x.narracion), "sostener_ms": 0}
        esc["sostener_ms"] = int(round(x.sostener * 1000)) if x.sostener is not None else \
            rec.sostener_por_omision(esc, escenas[-1] if escenas else None, g)
        escenas.append(esc)
    return {"id": secrets.token_hex(6), "titulo": a.titulo, "escenas": escenas,
            "cierre": {"puntos": list(a.cierre.puntos)} if a.cierre else None}


def _digitos(t: str) -> str:
    return re.sub(r"\D", "", t)


def _avisos(g: guion_presentacion.Guion, r: dict) -> list[str]:
    """Lo que no impide el recorrido pero conviene corregir la próxima vez (no bloquea)."""
    out = []
    usados = {e["capitulo"] for e in r["escenas"]}
    texto_guion = json.dumps([c for c in g.capitulos if c["id"] in usados], ensure_ascii=False)
    del_guion = {_digitos(m) for m in _NUMERO.findall(texto_guion)}
    for n, e in enumerate(r["escenas"], 1):
        narracion = " ".join(e["frases"])
        fuera = [m for m in _NUMERO.findall(narracion) if len(_digitos(m)) >= 2 and _digitos(m) not in del_guion]
        if fuera:
            out.append(f"escena {n}: {', '.join(dict.fromkeys(fuera))} no está en el guion de lo que muestra: las cifras, "
                       "tal como las trae el guion")
        if len(narracion) > 200:
            out.append(f"escena {n}: la narración pasa de 200 caracteres (mejor una idea más corta)")
    quieta = 1
    for a, b in zip(r["escenas"], r["escenas"][1:]):
        igual = all(a[k] == b[k] for k in ("capitulo", "paso", "panel", "visual")) and not b["resaltar"]
        quieta = quieta + 1 if igual else 1
        if quieta == 3:
            out.append("la pantalla no cambia en tres escenas seguidas: cada escena debería mostrar algo")
    if len(r["escenas"]) >= 4 and not r["cierre"]:
        out.append("un recorrido de 4 escenas o más sin cierre: dos o tres ideas que queden en la sala")
    return out


def _hace(g: guion_presentacion.Guion, esc: dict, anterior: dict | None) -> list[str]:
    """Lo que hace una escena, de la lista fija `HACE` (los chips de la tarjeta del chat)."""
    v, a = esc["visual"], (anterior or {}).get("visual") or rec.VISUAL_INICIAL
    out = []
    if not anterior or (anterior["capitulo"], anterior["paso"]) != (esc["capitulo"], esc["paso"]):
        out.append("paso")
    if v["camara"] != a["camara"] or v["rumbo"] != a["rumbo"]:
        out.append("camara")
    if v["enfoque"] and v["enfoque"] != a["enfoque"]:
        out.append("enfoque")
    if v["detalle"] and v["detalle"] != a["detalle"]:
        out.append("ficha")
    if v["comparar"] != a["comparar"]:
        out.append(v["comparar"])
    if rec.abre_atlas(esc, anterior, g):
        out.append("modelo")
    if esc["resaltar"]:
        out.append("resaltar")
    if not esc["panel"] and (not anterior or anterior["panel"]):
        out.append("solo3d")
    if v["girar"] and not a["girar"]:
        out.append("girar")
    return out


def _donde(g: guion_presentacion.Guion, esc: dict) -> str:
    c = g.capitulos[g.por_id(esc["capitulo"])]
    return f"{c['nombre']} · {c['pasos'][esc['paso'] - 1]['titulo']}"


def _muestra(g: guion_presentacion.Guion, esc: dict) -> str:
    """Lo que ve la sala en una escena, para el modelo: «Salud · paso 3 de 10 (Una torre…) · vista oblicua · ficha de…»."""
    c = g.capitulos[g.por_id(esc["capitulo"])]
    v = esc["visual"]
    nombres = {x["id"]: x["nombre"] for x in c.get("componentes") or []}
    inm = {i["id"]: i.get("nombre") for i in g.inmersiones}
    partes = [f"{c['nombre']} · paso {esc['paso']} de {len(c['pasos'])} ({c['pasos'][esc['paso'] - 1]['titulo']})"]
    if not esc["panel"]:
        partes.append("solo 3D")
    if v["camara"] != "paso":
        partes.append(NOMBRE_CAMARA[v["camara"]])
    if v["rumbo"] is not None:
        partes.append(f"rumbo {v['rumbo']}°")
    if v["girar"]:
        partes.append("girando")
    if v["enfoque"]:
        partes.append(f"cámara en {nombres.get(v['enfoque'], v['enfoque'])}")
    if v["detalle"]:
        partes.append(f"ficha de {nombres.get(v['detalle'], v['detalle'])}")
    if v["comparar"] == "hoy":
        partes.append("el sitio hoy")
    i = rec.inmersion_de(esc, g)
    if i:
        partes.append(f"modelo del atlas: {inm.get(i, i)}")
    if esc["resaltar"]:
        r = esc["resaltar"]
        partes.append(f"resalta {r['tipo']} {r.get('n') or nombres.get(r.get('id'), r.get('id'))}")
    return " · ".join(partes)


DONDE_SUENA = {"vista": "la vista Presentación de la pestaña del chat (o el proyector, si hay uno abierto)",
               "pantalla_off": "la pantalla en off"}


async def _recorrido(db: Any, uid: int, g: guion_presentacion.Guion, a: PresentacionEntrada, por: str,
                     abierta: bool, doc: dict | None = None) -> Resultado:
    """La op `recorrido`: compone, valida todo o nada, guarda y devuelve lo que el modelo necesita (compacto) y, al
    asistente, las acciones (la de la presentación si suena en la pestaña o el proyector, y la de la tarjeta del chat).
    Por MCP hace falta una pantalla en off abierta: no hay otra pantalla donde suene. Si el nuevo va a la pantalla en off
    y en la pestaña o el proyector sonaba otro (`doc`, la pantalla antes de guardarlo), también lo detiene allá: si no,
    las dos voces se pisaban hasta su próximo avance, y uno en pausa no se enteraba nunca."""
    if por == "mcp" and not abierta:
        raise ErrorHerramienta("Abra la pantalla en off antes de un recorrido (la vista Presentación en modo en off, en el "
                               "proyector): por MCP no hay otra pantalla donde se vea y se oiga. ir y visual sí quedan "
                               "guardados.", "sin_pantalla", estado=409)
    r = _componer(g, a)
    problemas = rec.validar(r, g)
    if problemas:   # no debería: _componer valida lo mismo; si pasa, mejor no reproducir nada
        raise ErrorHerramienta("El recorrido no se puede reproducir: " + "; ".join(problemas[:4]), "invalido", estado=422)
    ms = rec.duracion_ms(r, g)
    if ms > rec.MAX_DURACION_MS:
        raise ErrorHerramienta(f"El recorrido dura unos {round(ms / 1000)} s y el tope es {rec.MAX_DURACION_MS // 1000}: "
                               "divídalo en dos (menos escenas o narraciones más cortas).", "invalido", estado=422)
    destino = "pantalla_off" if abierta or por == "mcp" else "vista"
    previo = pantalla_off.recorrido_de(doc, g)
    await run_in_threadpool(pantalla_off.guardar_recorrido, db, uid, r, destino, por)
    avisos = _avisos(g, r)
    minutos, segundos = divmod(round(ms / 1000), 60)
    dura = f"{minutos} min {segundos} s" if minutos else f"{segundos} s"
    contenido = {"recorrido": {"id": r["id"], "titulo": r["titulo"], "escenas": len(r["escenas"]),
                               "cierre": bool(r["cierre"]), "duracion_estimada_s": round(ms / 1000),
                               "se_reproduce_en": DONDE_SUENA[destino]},
                 "escenas": [{"n": n, "muestra": _muestra(g, e), "narracion": " ".join(e["frases"])}
                             for n, e in enumerate(r["escenas"], 1)],
                 "nota": NOTA_RECORRIDO}
    if avisos:
        contenido["avisos"] = avisos
    acciones: list[dict] = []
    if por == "asistente":
        if destino == "pantalla_off" and previo and not previo["cerrado"] and previo["destino"] == "vista":
            acciones.append({"tipo": "presentacion", "op": "control_recorrido", "rid": previo["id"], "accion": "detener",
                             "motivo": "otra_orden"})
        if destino == "vista":
            acciones.append({"tipo": "presentacion", "op": "recorrido", "recorrido": r})
        acciones.append(_tarjeta(g, r, destino, ms, list(a.sugerencias or [])))
    return Resultado(contenido, f"Recorrido «{r['titulo']}» · {len(r['escenas'])} escenas · ≈{dura}", acciones=acciones)


def _tarjeta(g: guion_presentacion.Guion, r: dict, destino: str, ms: int, sugerencias: list[str]) -> dict:
    """La acción de la tarjeta del recorrido en el chat (agente-recorrido.js): dónde, qué hace y qué dice cada escena,
    la duración, el cierre y las sugerencias. Sigue el avance del recorrido con este id."""
    return {"tipo": "recorrido", "id": r["id"], "titulo": r["titulo"], "destino": destino, "duracion_ms": ms,
            "cierre": r["cierre"]["puntos"] if r["cierre"] else None, "sugerencias": sugerencias,
            "escenas": [{"narracion": " ".join(e["frases"]), "donde": _donde(g, e),
                         "hace": _hace(g, e, r["escenas"][n - 1] if n else None)} for n, e in enumerate(r["escenas"])]}


async def _control_recorrido(db: Any, uid: int, g: guion_presentacion.Guion, a: PresentacionEntrada, por: str,
                             abierta: bool) -> Resultado:
    """La op `control_recorrido`: queda guardado (la pantalla en off lo aplica una vez) y, si el recorrido suena en la
    pestaña o el proyector, va como acción al navegador del asistente. «reproducir» lo vuelve a empezar con otro id: al
    asistente le vuelve también la tarjeta del nuevo (la del anterior sigue el avance de su id, y el nuevo quedaría sin
    avance, sin barra en el chat y sin pausa al escribir). Por MCP, uno que suena en la pestaña o el proyector del panel
    no se controla: solo la pantalla en off lee los controles guardados, y la pestaña no sabría nada."""
    sin_recorrido = ErrorHerramienta("No hay un recorrido sonando: arme uno con la op recorrido.", "sin_recorrido",
                                     estado=409)
    if por == "mcp":
        actual = pantalla_off.recorrido_de(await run_in_threadpool(pantalla_off.leer, db, uid), g)
        if actual and actual["destino"] == "vista":
            if actual["cerrado"]:
                raise sin_recorrido
            raise ErrorHerramienta(
                f"El recorrido «{actual['titulo']}» suena en la pestaña del panel de la persona (o en su proyector), no "
                "en la pantalla en off: se controla desde ahí. Para manejar uno, arme otro con la pantalla en off "
                "abierta.", "en_el_panel", estado=409)
    try:
        res = await run_in_threadpool(pantalla_off.controlar, db, uid, g, a.accion, por)
    except ValueError:
        raise sin_recorrido from None
    r, doc = res["recorrido"], res["doc"]
    estado = pantalla_off.resumen_recorrido(doc, g) or {}
    acciones: list[dict] = []
    if por == "asistente" and r:
        if a.accion == "reproducir":
            if r["destino"] == "vista":
                acciones.append({"tipo": "presentacion", "op": "recorrido",
                                 "recorrido": {k: r[k] for k in ("id", "titulo", "escenas", "cierre")}})
            acciones.append(_tarjeta(g, r, r["destino"], rec.duracion_ms(r, g), []))
        elif r["destino"] == "vista":
            acciones.append({"tipo": "presentacion", "op": "control_recorrido", "rid": r["id"], "accion": a.accion})
    nombres = {"pausar": "Pausé", "continuar": "Seguí con", "siguiente": "Pasé a la escena siguiente de",
               "anterior": "Volví a la escena anterior de", "repetir": "Repetí la escena de", "reproducir": "Volví a empezar",
               "detener": "Detuve"}
    contenido = {"recorrido": {k: estado.get(k) for k in ("id", "titulo", "escena", "de", "fase")}, "accion": a.accion,
                 "nota": "Se aplica en la pantalla donde suena el recorrido; el avance llega en estado y en el contexto."}
    return Resultado(contenido, f"{nombres[a.accion]} el recorrido «{(r or {}).get('titulo', '')}»", acciones=acciones)


# Las ops que proyectan texto escrito por el modelo: en una conversación que ya trae datos de habitantes no van
PROYECTAN_TEXTO = ("recorrido", "explicar")


async def _presentacion(ctx: Contexto, a: PresentacionEntrada) -> Resultado:
    exigir_permiso(ctx, "presentacion.ver", "Su rol no abre la presentación en el panel.")
    if a.op in PROYECTAN_TEXTO or a.explicacion is not None:
        tiene = await run_in_threadpool(conv_db.tiene_personas, ctx.db, ctx.conversacion_id)
        if tiene:
            raise ErrorHerramienta(
                "Esta conversación ya trae datos de habitantes: lo que se proyecta ante la sala no puede llevar texto "
                "escrito aquí. Para presentar con narración, abra una conversación nueva; ir y visual sí funcionan.",
                "con_personas", estado=409)
    return await presentacion_en_pantalla(ctx.db, ctx.quien.uid, a, "asistente")


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
    "Presenta la propuesta Yondó 2028–2031 en su versión técnica (lo que se construye, sin costos, sobre la maqueta 3D "
    "del territorio y con modelos del atlas) en el panel de la persona o en su pantalla en off (un proyector sin "
    "controles). PARA EXPLICAR, UN RECORRIDO: guion (los datos de un capítulo: pasos, lo resaltable, fichas, "
    "inmersiones; no mueve nada) y luego recorrido, en UNA llamada: titulo, de 3 a 6 escenas y cierre {puntos}. Cada "
    "escena es una idea: narracion (una o dos frases que se proyectan y se dicen en voz alta) y lo que se ve mientras "
    "tanto (capitulo, paso, panel, enfoque, detalle, comparar, camara, rumbo, girar, inmersion, resaltar lo que nombra; "
    "lo que no cambia sigue de la anterior). La pantalla lo reproduce sola, a ritmo humano. Ejemplo de escenas: "
    "[{\"capitulo\":\"salud\",\"paso\":\"torre\",\"camara\":\"oblicua\",\"narracion\":\"…\"},{\"detalle\":\"torre\","
    "\"resaltar\":{\"especificacion\":\"Estructura\"},\"narracion\":\"…\"}]. control_recorrido: pausar, continuar, "
    "siguiente, anterior, repetir, reproducir, detener. Pedidos puntuales (detienen el recorrido): indice; ir (devuelve "
    "lo que muestra el paso); siguiente/anterior; explicar (una frase en pantalla, hasta 220 caracteres) y "
    "quitar_explicacion; vista (panel, indice, fichas); visual (enfoque, detalle, comparar, camara, rumbo, girar, "
    "inmersion, tema); pantalla_completa; estado (qué muestra y en qué escena va). Lo que no existe vuelve con "
    "candidatos. La sala lo ve: nunca datos de habitantes, costos, «@» ni números de 7 o más dígitos.")

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
