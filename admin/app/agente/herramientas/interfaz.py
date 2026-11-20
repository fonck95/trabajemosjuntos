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
  técnica de lo que se muestra. Y con `recorrido` arma un PLAN guiado (hasta 12 pasos: lo que se dice y lo que ocurre
  mientras se dice: la cámara que viaja, las piezas de la maqueta que se muestran, se ocultan o se aíslan, las partes
  que se quitan, los controles de la simulación de un modelo del atlas o, sin él, de la maqueta 3D: `simular`) que la
  pantalla ejecuta sola; ahí la composición es TOLERANTE: lo opcional que no resuelve se
  descarta o se recorta con un aviso legible y el plan corre igual (`_componer`). Y con `automatica` enciende o
  apaga la presentación automática (`app/automatica.py`): la pantalla en off recorre sola toda la presentación, muy
  resumida, sin que el modelo escriba nada; un plan del asistente la interrumpe y después sigue. Lo único que guarda es la
  pantalla en off de la persona (`app/pantalla.py`: capítulo, paso, explicación y lo que se ve, sin datos de nadie), que
  manejan este asistente y un agente por MCP (`app/api/mcp.py`) con la misma herramienta (`presentacion_en_pantalla`). Lo que el
  modelo escribe para la pantalla (`explicacion`) se proyecta ante otras personas: se rechaza con caracteres que no se
  ven o que cambian cómo se ve el resto, con números largos o con «@» (una cédula, un teléfono o un correo no llegan
  ahí ni por descuido).
"""
from __future__ import annotations

import asyncio
import json
import math
import re
import secrets
import time
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, Union
from urllib.parse import urlencode

from pydantic import (AfterValidator, BeforeValidator, ConfigDict, Field, StrictBool, WrapValidator, field_validator,
                      model_validator)
from starlette.concurrency import run_in_threadpool

from ... import automatica
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
    "sin_lugar", "sin_puesto", "sin_mesa", "sin_direccion", "lider_id", "varios_lideres", "intervenida_en", "tipo",
    "jefe_hogar", "ocupacion", "perfil_profesional", "con_correo", "sin_correo", "sin_estado_civil", "sin_ocupacion",
    "sin_perfil_profesional", "sin_jefe_hogar", "sin_lider"})
# Filtros que la API no deja usar a planilleros y consultores (`filtros.VEDADOS`): con ellos Habitantes daría 403
VEDADOS = ("ids", "lista", "lider", "tipo", "lider_id", "varios_lideres", "sin_lider", "intervenida_en", "creado_por",
           "actualizado_por", "menor", "poligono")


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
                    "visual", "recorrido", "control_recorrido", "automatica", "pantalla_completa", "estado")
# Lo que se le pide a la presentación automática (`automatica`): encenderla (desde un capítulo, si se dice) o apagarla
ACCIONES_AUTO = ("iniciar", "detener")
# Lo que arma un plan guiado (`recorrido`: hacia el modelo y la persona, un «plan» con «pasos»; por dentro, un recorrido
# con escenas) y lo que lo maneja (`control_recorrido`). `pasos` y `escenas` son lo mismo: llega uno de los dos
PARTES_RECORRIDO = ("titulo", "pasos", "escenas", "cierre", "sugerencias")
# Las ops que cambian lo que se ve: con un recorrido sonando, parten de la escena en curso (la que la sala ve) y, ya
# resueltas, lo colapsan (lo cierran con esa escena como base) justo antes de guardarse
COLAPSAN = ("ir", "siguiente", "anterior", "explicar", "quitar_explicacion", "vista", "visual")
# Lo que dice cada operación del estado de la pantalla en off (las demás no lo cambian): `vista` y `pantalla_completa`
PARTES_VISTA = ("panel", "indice", "fichas")
# Lo que cambia `visual` (pantalla_off.VISUAL; `VISUAL` de mando.js y de agente-presentacion.js con los mismos valores) y
# sus tres acciones, que no son estado (`mover`: el viaje de la cámara; `animar`: repetir la animación del paso;
# `simular`: los controles de la simulación del modelo a la vista, el del atlas o, sin él, la maqueta 3D)
PARTES_VISUAL = pantalla_off.VISUAL
ACCIONES_VISUAL = pantalla_off.ACCIONES
CAMARAS = pantalla_off.CAMARAS
NOMBRE_CAMARA = {"paso": "el encuadre del paso", "aerea": "vista aérea", "oblicua": "vista oblicua",
                 "rasante": "vista rasante, casi a ras del suelo", "cerca": "más cerca", "lejos": "más lejos"}
# El acercamiento que implica cada encuadre con nombre (`PRESET` de visual.js): de ahí parte el `mover` por omisión
ZOOM_DE_CAMARA = {"rasante": 1.1, "cerca": 1.9, "lejos": 0.5}
# El `mover` suave de un paso del plan que no le pide nada a la cámara (que la imagen nunca quede quieta): gira unos
# grados alrededor de lo que mira, alternando el sentido, y se acerca un poco (`rec.mover_suave`)
GIROS_SUAVES = rec.GIROS_SUAVES
ZOOM_SUAVE = rec.ZOOM_SUAVE
MAX_AVISOS = 12
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
    """«paso» (enfoque, inmersion, mirar), «cerrar» (detalle) y «nada» o «todo» (aislar) vuelven a lo del paso: quedan en
    None, pero la clave llegó."""
    palabras = {"detalle": ("cerrar", "ninguna", "ninguno"),
                "aislar": ("nada", "ninguna", "ninguno", "todo", "paso")}.get(campo, ("paso",))
    return None if isinstance(v, str) and guion_presentacion.clave(v) in palabras else v


class NoVale:
    """Un valor opcional (de un paso del plan o de lo nuevo de `visual`) que llegó sin la forma. No tumba la entrada:
    queda con lo que llegó, y quien compone lo recorta, lo arregla o lo descarta con un aviso legible."""
    __slots__ = ("crudo",)

    def __init__(self, crudo: Any):
        self.crudo = crudo

    def __repr__(self) -> str:
        return f"NoVale({self.crudo!r})"


def _tolerar(v: Any, validar: Any) -> Any:
    try:
        return validar(v)
    except ValueError:   # (el ValidationError de pydantic lo es)
        return NoVale(v)


def Tol(tipo: Any) -> Any:
    """`tipo` opcional y TOLERANTE: el esquema para el modelo es el de `tipo` (con sus topes), pero un valor que no
    cumple no rechaza la llamada entera, queda como `NoVale`."""
    return Annotated[tipo | None, WrapValidator(_tolerar)]


def _una_o_varias(v: Any) -> Any:
    """Una lista de nombres también puede llegar como uno solo («torre») o separados por comas."""
    return [x.strip() for x in v.split(",") if x.strip()] if isinstance(v, str) else v


Elevacion = Annotated[int, Field(ge=rec.ELEVACION[0], le=rec.ELEVACION[1])]
Zoom = Annotated[float, Field(ge=rec.ZOOM[0], le=rec.ZOOM[1])]
Nombre = Annotated[str, Field(min_length=1, max_length=80)]
Nombres = Annotated[list[Nombre], Field(max_length=rec.MAX_LISTA), BeforeValidator(_una_o_varias)]


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


class MoverEntrada(_Entrada):
    """Cómo viaja la cámara MIENTRAS se dice el paso (no queda como estado): al menos una de las tres."""
    giro: Annotated[int, Field(ge=rec.GIRO[0], le=rec.GIRO[1])] | None = Field(None, description=(
        "Grados que gira alrededor de lo que mira mientras dura la frase (positivo: el rumbo crece)"))
    zoom: Zoom | None = Field(None, description="Acercamiento con que termina (1: el encuadre del paso; 2: el doble de cerca)")
    elevacion: Elevacion | None = Field(None, description="Grados sobre el horizonte con que termina")


def _simular_a_su_manera(v: Any) -> Any:
    """Un control de `simular` también puede llegar como su solo nombre («calcular»)."""
    return {"control": v} if isinstance(v, str) else v


def _simulares_a_su_manera(v: Any) -> Any:
    """`simular` también puede llegar como un solo control (un objeto o su nombre) en vez de la lista."""
    return [v] if isinstance(v, (dict, str)) else v


class SimularEntrada(_Entrada):
    # Un control de la simulación del modelo a la vista: el del atlas abierto (los `controles` de su inmersión, en guion
    # o al abrirlo) o, sin él, la maqueta 3D (`controles_maqueta`: la hora, el día, las luces, el partido), accionado como
    # lo haría la persona. (Sin docstring: el esquema va en cada pedido al modelo, dos veces)
    control: Annotated[str, Field(min_length=1, max_length=80)] = Field(..., description="Su id o su nombre")
    valor: StrictBool | int | float | Annotated[str, Field(max_length=80)] | None = Field(None, description=(
        "Número de su rango, opción (id o nombre) o true/false; nada si es acción"))


# Cada control es tolerante por separado (uno que no tiene la forma no tumba los demás) y lo que pasa de MAX_SIMULAR se
# recorta con un aviso (`_resolver_simular`)
Simulares = Annotated[list[Annotated[SimularEntrada | None, BeforeValidator(_simular_a_su_manera),
                                     WrapValidator(_tolerar)]],
                      BeforeValidator(_simulares_a_su_manera), Field(json_schema_extra={"maxItems": rec.MAX_SIMULAR})]


class EscenaEntrada(_Entrada):
    """Un paso del plan: UNA frase (dice) y lo que ocurre en pantalla MIENTRAS se dice. Cada paso parte del anterior (lo
    que no nombra sigue igual); al cambiar de paso del capítulo, lo visual vuelve a lo de ese paso."""
    # (El docstring va al modelo, con el esquema.) Solo `dice` es obligatorio. Lo demás es opcional y TOLERANTE: lo que
    # no tiene la forma queda como `NoVale` y `_componer` lo recorta o lo descarta con un aviso; una clave que no existe
    # tampoco tumba el plan (por eso `extra` no es «forbid», aunque el esquema para el modelo diga que no hay más)
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True,
                              json_schema_extra={"additionalProperties": False})
    dice: Tol(Annotated[str, Field(min_length=1, max_length=rec.MAX_NARRACION)]) = Field(None, description=(
        "Lo que se dice en este paso: UNA frase hablada (dos a lo sumo; hasta 220 caracteres) que se proyecta y se lee "
        "en voz alta, sobre lo que el paso muestra; sin costos, «@» ni números de 7 o más dígitos"))
    narracion: Tol(str) = Field(None, description="Lo mismo que dice")
    capitulo: Tol(Annotated[str, Field(min_length=2, max_length=60)]) = Field(None, description=(
        "Id o nombre del capítulo (obligatorio en el primer paso del plan; los demás siguen en el del anterior)"))
    paso: Tol(PasoNumero | PasoId) = Field(None, description=(
        "El paso del capítulo que se muestra: su número desde 1 o su id; sin él, el mismo"))
    panel: Tol(StrictBool) = Field(None, description="false deja solo la maqueta 3D («Solo 3D»); se hereda")
    camara: Tol(Literal[CAMARAS]) = Field(None, description=(
        "Un encuadre con nombre: paso (el del paso, también su rumbo, elevación y zoom), aerea, oblicua, rasante, cerca "
        "o lejos"))
    rumbo: Tol(Rumbo) = Field(None, description="Desde dónde se mira, en grados desde el norte (180: el norte arriba)")
    elevacion: Tol(Elevacion) = Field(None, description="Grados sobre el horizonte (80: casi desde arriba; 12: a ras)")
    zoom: Tol(Zoom) = Field(None, description="Acercamiento: 1 es el encuadre del paso; 2, el doble de cerca; 0.5, lejos")
    mirar: Tol(Nombre) = Field(None, description=(
        "A qué apunta la cámara SIN cambiar lo que se ve: una pieza de la maqueta o un componente con lugar (id o "
        "nombre); paso vuelve al encuadre del paso"))
    mover: Tol(MoverEntrada) = Field(None, description=(
        "El viaje de la cámara mientras se dice la frase. Sin nada para la cámara en el paso, hace uno suave sola"))
    enfoque: Tol(Nombre) = Field(None, description=(
        "La cámara va a un componente con lugar en la maqueta y lo destaca (id o nombre); paso lo quita"))
    aislar: Tol(Nombre) = Field(None, description=(
        "Deja ver solo una pieza de la maqueta (id o nombre, de maqueta en el guion): el resto se apaga o queda en "
        "gris; nada lo quita"))
    mostrar: Tol(Nombres) = Field(None, description="Piezas de la maqueta que se ven además de las del paso (la lista entera)")
    ocultar: Tol(Nombres) = Field(None, description="Piezas de la maqueta que se ocultan aunque el paso las muestre (la lista entera)")
    sin: Tol(Nombres) = Field(None, description=(
        "Partes que se le quitan a una pieza, como «pieza.parte» («torre.cubierta» deja ver las losas); [] las devuelve"))
    detalle: Tol(Nombre) = Field(None, description="Abre la ficha técnica de un componente (id o nombre); cerrar la cierra")
    comparar: Tol(Literal["hoy", "proyecto"]) = Field(None, description=(
        "hoy: el sitio como está, sin el proyecto, en el mismo encuadre; proyecto lo devuelve"))
    inmersion: Tol(Nombre) = Field(None, description=(
        "Un modelo 3D del atlas del catálogo (id o nombre); maqueta lo cierra; paso, lo que diga el paso"))
    animar: Tol(StrictBool) = Field(None, description="true: repite la animación propia del paso (la obra crece) mientras se dice")
    simular: Tol(Simulares) = Field(None, description=(
        "Hasta 4 controles en orden (de guion): del modelo del atlas abierto (magnitud, calcular) o de la maqueta "
        "(hora, luces)"))
    girar: Tol(StrictBool) = Field(None, description="true: la cámara gira despacio sin parar; se hereda")
    resaltar: Tol(ResaltarEntrada) = Field(None, description="Señala en pantalla lo que la frase nombra")
    gesto: Tol(Annotated[str, Field(min_length=2, max_length=40)]) = Field(None, description=(
        "El gesto del presentador mientras se dice (de «gestos» del guion)"))
    sostener: Tol(Annotated[float, Field(ge=0, le=8)]) = Field(None, description=(
        "Segundos que la imagen se queda después de la frase (por omisión 1,3, o 2,7 si hay algo que mirar)"))

    @field_validator("enfoque", "inmersion", "detalle", "mirar", "aislar", mode="before")
    @classmethod
    def _volver(cls, v, info):
        return _volver_al_paso(v, info.field_name)


def _cierre_a_su_manera(v: Any) -> Any:
    """El cierre también puede llegar como la lista de sus puntos, o como uno solo."""
    v = {"puntos": v} if isinstance(v, list) else {"puntos": [v]} if isinstance(v, str) else v
    if isinstance(v, dict) and isinstance(v.get("puntos"), list) and len(v["puntos"]) > rec.MAX_PUNTOS:
        v = {**v, "puntos": v["puntos"][:rec.MAX_PUNTOS]}   # ideas de más: quedan las primeras
    return v


def _sugerencias_a_su_manera(v: Any) -> Any:
    """Las sugerencias son solo para el chat: una sola como texto vale, y las que no sirven (muy cortas, muy largas o
    con algo que no se muestra) se descartan en vez de tumbar el plan."""
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list):
        return v
    buenas: list[str] = []
    for x in v:
        t = " ".join(x.split()) if isinstance(x, str) else ""
        if not 3 <= len(t) <= rec.MAX_SUGERENCIA:
            continue
        try:
            buenas.append(texto_proyectable(t, rec.MAX_SUGERENCIA))
        except ValueError:
            continue
    return buenas[:rec.MAX_SUGERENCIAS]


def _hasta_doce(v: Any) -> Any:
    if isinstance(v, list) and len(v) > rec.MAX_ESCENAS:
        raise ValueError(f"Un plan lleva hasta {rec.MAX_ESCENAS} pasos y llegaron {len(v)}: junte ideas o divídalo en "
                         "dos planes")
    return v


Pasos = Annotated[list[EscenaEntrada], Field(min_length=1, max_length=rec.MAX_ESCENAS), BeforeValidator(_hasta_doce)]


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
        "indice: los capítulos y los títulos de sus pasos; guion: todo lo de un capítulo para armar un plan; recorrido: "
        "el plan (titulo, pasos, cierre) que la pantalla ejecuta sola; control_recorrido: lo pausa, salta o detiene; "
        "ir: a un capítulo y paso (devuelve lo que muestra ese paso); siguiente o anterior: un paso (con capitulo y "
        "paso de partida, los del contexto del panel, devuelve el paso de destino); explicar: muestra una o dos frases "
        "cortas en pantalla; quitar_explicacion: la quita; vista: lo que se ve sin cambiar de paso (panel, indice, "
        "fichas); visual: la cámara, las piezas de la maqueta y lo demás, sin cambiar de paso; pantalla_completa: la "
        "presentación llena la ventana (activar) o vuelve a la vista con el menú; estado: qué muestra la pantalla en "
        "off, si está abierta y por qué paso va el plan; automatica: la pantalla en off recorre sola toda la "
        "presentación, muy resumida (accion iniciar o detener; capitulo: dónde empieza)"))
    capitulo: str | None = Field(None, min_length=2, max_length=60, description=(
        "Id o nombre del capítulo (del índice o del contexto del panel)"))
    paso: PasoNumero | PasoId | None = Field(None, description=(
        "Número del paso desde 1, o su id (del índice); en visual, el de partida (el del contexto del panel)"))
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
    # visual, lo que da el plan guiado: tolerantes (lo que no vale se recorta o se descarta con un aviso)
    elevacion: Tol(Elevacion) = Field(None, description="visual: grados de la cámara sobre el horizonte (80: casi desde arriba)")
    zoom: Tol(Zoom) = Field(None, description="visual: acercamiento (1: el encuadre del paso; 2: el doble de cerca)")
    mirar: Tol(Nombre) = Field(None, description=(
        "visual: a qué apunta la cámara sin cambiar lo que se ve (una pieza de la maqueta o un componente con lugar); "
        "paso vuelve al encuadre"))
    mostrar: Tol(Nombres) = Field(None, description="visual: piezas de la maqueta que se ven además de las del paso (de guion)")
    ocultar: Tol(Nombres) = Field(None, description="visual: piezas de la maqueta que se ocultan")
    aislar: Tol(Nombre) = Field(None, description="visual: solo se ve esa pieza de la maqueta; nada lo quita")
    sin: Tol(Nombres) = Field(None, description="visual: partes quitadas, como «pieza.parte» («torre.cubierta»); [] las devuelve")
    mover: Tol(MoverEntrada) = Field(None, description="visual: la cámara viaja unos segundos desde donde está")
    animar: Tol(StrictBool) = Field(None, description="visual: true repite la animación propia del paso")
    simular: Tol(Simulares) = Field(None, description=(
        "visual: hasta 4 controles en orden: del modelo del atlas abierto o, sin él, de la maqueta"))
    titulo: TituloRecorrido | None = Field(None, description="recorrido: el título del plan, que se ve en la sala (3 a 80)")
    pasos: Pasos | None = Field(None, description=(
        "recorrido: el plan, de 6 a 10 pasos (hasta 12): cada uno UNA frase y lo que ocurre en pantalla mientras se dice"))
    escenas: Pasos | None = Field(None, description="Lo mismo que pasos")
    cierre: Annotated[CierreEntrada, BeforeValidator(_cierre_a_su_manera)] | None = Field(None, description=(
        "recorrido: dos o tres ideas que quedan en la sala"))
    sugerencias: Annotated[list[Sugerencia], BeforeValidator(_sugerencias_a_su_manera)] | None = Field(
        None, max_length=rec.MAX_SUGERENCIAS, description="recorrido: hasta 3 próximos pasos, solo para el chat (no se proyectan)")
    accion: Literal[(*rec.CONTROLES, "iniciar")] | None = Field(None, description=(
        "control_recorrido: pausar, continuar, siguiente, anterior, repetir, reproducir (otra vez, desde el comienzo) o "
        "detener. automatica: iniciar o detener"))

    @field_validator("enfoque", "inmersion", "detalle", "mirar", "aislar", mode="before")
    @classmethod
    def _volver_al_paso(cls, v, info):
        return _volver_al_paso(v, info.field_name)

    def partes_visuales(self) -> dict:
        """Las partes de `visual` que llegaron (también las que llegaron en null: vuelven a lo del paso)."""
        return {k: getattr(self, k) for k in PARTES_VISUAL if k in self.model_fields_set}

    def acciones_visuales(self) -> dict:
        """Las acciones de `visual` que llegaron con algo (`mover`, `animar`, `simular`): no son estado."""
        return {k: getattr(self, k) for k in ACCIONES_VISUAL if getattr(self, k) not in (None, False)}

    def plan(self) -> list[EscenaEntrada]:
        """Los pasos del plan, hayan llegado como `pasos` o como `escenas`."""
        return self.pasos or self.escenas or []

    @model_validator(mode="after")
    def _segun_op(self):
        vista, completa, visual = PARTES_VISTA, ("activar",), PARTES_VISUAL
        propias = {"recorrido": PARTES_RECORRIDO, "control_recorrido": ("accion",),
                   "automatica": ("accion",)}.get(self.op, ())
        ajenas = [k for k in (*PARTES_RECORRIDO, "accion") if k not in propias and getattr(self, k) is not None]
        if ajenas:
            raise ValueError(f"La operación {self.op} no usa: {', '.join(ajenas)}")
        sobran = {"indice": ("capitulo", "paso", "explicacion", *vista, *completa),
                  "guion": ("explicacion", *vista, *completa),
                  "recorrido": ("capitulo", "paso", "explicacion", *vista, *completa),
                  "control_recorrido": ("capitulo", "paso", "explicacion", *vista, *completa),
                  "automatica": ("paso", "explicacion", *vista, *completa),
                  "quitar_explicacion": ("capitulo", "paso", "explicacion", *vista, *completa),
                  "estado": ("capitulo", "paso", "explicacion", *vista, *completa),
                  "explicar": ("capitulo", "paso", *vista, *completa),
                  "vista": ("capitulo", "paso", "explicacion", *completa),
                  "visual": ("explicacion", *vista, *completa),
                  "pantalla_completa": ("capitulo", "paso", "explicacion", *vista)}.get(self.op, (*vista, *completa))
        malos = [k for k in sobran if getattr(self, k) is not None]
        if self.op != "visual":
            malos += [k for k in (*visual, *ACCIONES_VISUAL) if k in self.model_fields_set]
        if malos:
            raise ValueError(f"La operación {self.op} no usa: {', '.join(malos)}")
        if self.op == "visual":
            partes = self.partes_visuales()
            if not partes and not self.acciones_visuales():
                raise ValueError("Para visual, diga qué cambiar: enfoque, camara, rumbo, elevacion, zoom, mirar, mover, "
                                 "girar, comparar, detalle, inmersion, mostrar, ocultar, aislar, sin, animar, simular o "
                                 "tema")
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
        if self.op == "recorrido" and self.pasos is not None and self.escenas is not None:
            raise ValueError("pasos y escenas son lo mismo: mande solo pasos")
        if self.op == "recorrido" and not self.plan():
            raise ValueError("Para recorrido, escriba el titulo y los pasos del plan (de 6 a 10, una frase cada uno)")
        if self.op == "control_recorrido" and self.accion not in rec.CONTROLES:
            raise ValueError("Para control_recorrido, diga la accion: pausar, continuar, siguiente, anterior, repetir, "
                             "reproducir o detener")
        if self.op == "automatica" and self.accion not in ACCIONES_AUTO:
            raise ValueError("Para automatica, diga la accion: iniciar (la pantalla en off recorre sola toda la "
                             "presentación; con capitulo, desde ese) o detener")
        return self


def _esquema_presentacion() -> dict:
    """El esquema de la entrada para el modelo: sin la rama «null» del paso (número o id; el modelo simplemente omite la
    clave), sin los nombres de antes (`escenas`, `narracion`: se siguen aceptando, pero el plan se pide con `pasos` y
    `dice`; repetirlos doblaría el esquema), con `dice` como lo único obligatorio de un paso del plan y con cada control
    de `simular` como un objeto."""
    s = esquema(PresentacionEntrada)
    s["properties"].pop("escenas", None)
    del_plan = s["properties"]["pasos"].get("items") or {}
    (del_plan.get("properties") or {}).pop("narracion", None)
    del_plan["required"] = ["dice"]
    # `simular` (en visual y en cada paso del plan): cada control es un objeto (la rama «null» de su tolerancia no le
    # dice nada al modelo) y su valor, un número, un texto o verdadero o falso
    for sim in (s["properties"].get("simular"), (del_plan.get("properties") or {}).get("simular")):
        items = (sim or {}).get("items") or {}
        objeto = next((r for r in items.get("anyOf", []) if r.get("type") == "object"), None)
        if objeto:
            valor = objeto["properties"]["valor"]
            valor["anyOf"] = [r for r in valor.get("anyOf", []) if r.get("type") not in ("null", "integer")]
            valor.pop("default", None)
            sim["items"] = objeto
    for paso in (s["properties"]["paso"], (del_plan.get("properties") or {}).get("paso") or {}):
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
    piezas = g.piezas(ci)
    if piezas:
        # lo que se puede mostrar, ocultar o aislar de la maqueta (y las partes que se quitan con sin: «pieza.parte»)
        out["maqueta"] = [{"id": x["id"], "nombre": x["nombre"],
                           **({"partes": [p["id"] for p in x["partes"]]} if x["partes"] else {})} for x in piezas]
    modelo = rec.simulable_en(c["id"], pi + 1, None, g)
    if modelo == rec.MAQUETA:
        # sin un modelo del atlas, lo que se puede accionar con simular en la maqueta 3D (su ayuda, en guion)
        maqueta = g.controles(rec.MAQUETA, c["id"])
        if maqueta:
            out["controles_maqueta"] = [{k: v for k, v in x.items() if k != "ayuda"} for x in maqueta]
    elif g.controles(modelo):
        # lo que se puede accionar con simular en el modelo del atlas de este paso
        out["controles"] = g.controles(modelo)
    return out


def _estado_para_modelo(doc: dict | None, e: dict, g: guion_presentacion.Guion, abierta: bool) -> dict:
    ci = g.por_id(e["capitulo"])
    out = {"abierta": abierta, "muestra": pantalla_off.describir(e, g), "capitulo": e["capitulo"], "paso": e["paso"],
           "de": len(g.capitulos[ci]["pasos"]), "explicacion": e["explicacion"], "panel": e["panel"],
           "indice": e["indice"], "fichas": e["fichas"], "llena_la_ventana": e["completa"],
           "visual": {k: e[k] for k in PARTES_VISUAL}}
    if doc and doc.get("por") in pantalla_off.ORIGENES:
        out["cambiada_por"] = {"asistente": "el asistente del panel", "mcp": "un agente por MCP",
                               "panel": "los controles del panel", "auto": "la presentación automática"}[doc["por"]]
    auto = pantalla_off.auto_de(doc, g)
    if auto:
        out["automatica"] = {**pantalla_off.auto_para_persona(doc, g), "vueltas": auto["vueltas"]}
    r = pantalla_off.resumen_recorrido(doc, g)
    if r:
        out["plan"] = {**_plan_para_modelo(r), **({"automatico": True} if r["auto"] else {})}
    return out


def _plan_para_modelo(r: dict) -> dict:
    """Dónde va el plan (`pantalla.resumen_recorrido`) con las palabras del modelo: un plan y sus pasos."""
    return {"id": r["id"], "titulo": r["titulo"], "destino": r["destino"], "cerrado": r["cerrado"], "paso": r["escena"],
            "de": r["de"], "fase": r["fase"], "motivo": r["motivo"], "voz": r["voz"],
            "dice_en_curso": r["narracion_en_curso"], "avisos": r["avisos"], "hace_s": r["hace_s"],
            "muestra": pantalla_off.describir_recorrido(r)}


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
        return Resultado({**g.capitulo_para_leer(ci), "gestos": dict(rec.GESTOS), "nota": NOTA_GUION},
                         f"Guion de {c['nombre']} · {len(c['pasos'])} pasos, {len(c.get('componentes') or [])} componentes")
    doc = await run_in_threadpool(pantalla_off.leer, db, uid)
    abierta = pantalla_off.conectada(doc)
    desde_pantalla = abierta or por == "mcp"
    if a.op == "recorrido":
        return await _recorrido(db, uid, g, a, por, abierta, doc)
    if a.op == "control_recorrido":
        return await _control_recorrido(db, uid, g, a, por, abierta)
    if a.op == "automatica":
        return await _automatica(db, uid, g, a, por, abierta, doc)
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
        contenido, resumen, cambios, acciones_visuales = _visual(g, e, a, desde_pantalla)
        # al navegador, lo que cambia y lo que hace una vez (`mover`, `animar`, `simular`); en la pantalla en off quedan
        # las de ESTA orden (las de la anterior, ya recibidas, se van; las que todavía no recibió se juntan con estas:
        # `_guardar_en_pantalla`): no son estado, la pantalla las hace una vez
        accion = {"tipo": "presentacion", "op": "visual", **cambios, **acciones_visuales}
        cambios = {**cambios, **pantalla_off.ACCIONES_INICIALES, **acciones_visuales}
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
                   "fichas": False, **pantalla_off.visual_inicial(), **pantalla_off.ACCIONES_INICIALES}
    # Ya resuelta (nada más puede fallar): cierra el recorrido que sonaba, con la escena en curso como base, y encima
    # guarda lo pedido
    detener = await _colapsar(db, uid, g, doc, por) if a.op in COLAPSAN else []
    if a.op != "visual":   # las acciones son de la orden `visual` que las trajo: cualquier otra las deja en nada
        cambios = {**cambios, **pantalla_off.ACCIONES_INICIALES}
    await _guardar_en_pantalla(db, uid, cambios, por)
    if desde_pantalla:
        contenido["pantalla"] = NOTA_PANTALLA_ABIERTA if abierta else NOTA_SIN_PANTALLA
    return Resultado(contenido, resumen,
                     acciones=[*detener, *([accion] if accion and not abierta and por == "asistente" else [])])


# Cuánto espera una orden a que la pantalla en off abierta reciba las acciones de la anterior cuando no caben con las
# suyas (dos viajes de la cámara, más de MAX_SIMULAR controles): la pantalla pregunta cada 1,5 s
ESPERA_ENTREGA_S = 3.0


async def _guardar_en_pantalla(db: Any, uid: int, cambios: dict, por: str) -> dict:
    """Guarda la orden en la pantalla en off (`pantalla.guardar_orden`) sin pisar las acciones que la pantalla abierta
    todavía no recibió: con otra orden que llegó entretanto (dos en paralelo) vuelve a leer y a juntar; si no caben
    juntas, espera a que la pantalla las reciba, hasta ESPERA_ENTREGA_S (después, las de antes se pierden: la pantalla
    no está preguntando)."""
    hasta = time.monotonic() + ESPERA_ENTREGA_S
    for _ in range(60):
        esperar = time.monotonic() < hasta
        doc = await run_in_threadpool(pantalla_off.guardar_orden, db, uid, cambios, por, esperar)
        if doc is not None:
            return doc
        await asyncio.sleep(0.15 if esperar else 0)
    return await run_in_threadpool(pantalla_off.guardar, db, uid, cambios, por)


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


def _ver(v: Any) -> str:
    """Un valor que llegó del modelo, para decirlo en un aviso: en un renglón y corto."""
    v = v.crudo if isinstance(v, NoVale) else v
    t = " ".join(str(v).split())
    return t if len(t) <= 40 else t[:39] + "…"


def _lista(ids: list[str], maximo: int = 14) -> str:
    """Los candidatos de un aviso: sus ids, sin pasar de `maximo`."""
    return (", ".join(ids[:maximo]) + ("…" if len(ids) > maximo else "")) or "ninguna"


def _acotar(v: Any, lo: float, hi: float, decimales: int = 0) -> tuple[Any, bool]:
    """Un número dentro de [lo, hi], entero o con `decimales`, y si hubo que tocarlo; (None, True) si no es un número
    (tampoco verdadero o falso). Un texto con un número («1,5») vale."""
    v = v.crudo if isinstance(v, NoVale) else v
    if isinstance(v, str):
        try:
            v = float(v.strip().replace(",", "."))
        except ValueError:
            return None, True
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        return None, True
    w: Any = round(min(hi, max(lo, v)), decimales) if decimales else int(round(min(hi, max(lo, v))))
    if isinstance(w, float) and w.is_integer():
        w = int(w)
    return w, abs(w - v) > 1e-9


def _nombres(v: Any) -> list[str]:
    """Los nombres de una lista que llegó a su manera (una lista, uno solo, separados por comas), cada uno un texto."""
    v = _una_o_varias(v.crudo if isinstance(v, NoVale) else v)
    return [" ".join(str(x).split())[:80] for x in (v if isinstance(v, list) else [])
            if isinstance(x, (str, int)) and not isinstance(x, bool) and str(x).strip()]


def _resolver_parte(g: guion_presentacion.Guion, ci: int, texto: str, contexto: list[str]) -> tuple[str | None, str]:
    """La parte de una pieza que se pidió quitar, como «pieza.parte», o (None, por qué no). Con el punto, esa pieza y
    esa parte (por id o por nombre). Sin él, la parte de la pieza del `contexto` (la aislada, la que mira la cámara)
    o la de la única pieza del capítulo que tiene una parte así."""
    c, piezas = g.capitulos[ci], g.piezas(ci)
    todas = [f"{x['id']}.{p['id']}" for x in piezas for p in x["partes"]]
    if "." in texto:
        de, _, parte = texto.partition(".")
        x = g.pieza(ci, de)
        if x is None:
            return None, f"la pieza «{_ver(de)}» no está en {c['nombre']}; partes que se pueden quitar: {_lista(todas)}"
        p = g.parte(ci, x["id"], parte)
        if p is None:
            suyas = [f"{x['id']}.{k['id']}" for k in x["partes"]]
            return None, (f"«{x['nombre']}» no tiene la parte «{_ver(parte)}»; "
                          + (f"tiene: {_lista(suyas)}" if suyas else f"no tiene partes que quitar; las hay en: {_lista(todas)}"))
        return f"{x['id']}.{p['id']}", ""
    candidatas = [(x["id"], p["id"]) for x in piezas for p in [guion_presentacion.parecido(x["partes"], texto)] if p]
    for pieza in contexto:
        suya = next((f"{a}.{b}" for a, b in candidatas if a == pieza), None)
        if suya:
            return suya, ""
    if len(candidatas) == 1:
        return f"{candidatas[0][0]}.{candidatas[0][1]}", ""
    if candidatas:
        return None, f"«{_ver(texto)}» puede ser {_lista([f'{a}.{b}' for a, b in candidatas])}: diga cuál (pieza.parte)"
    return None, f"«{_ver(texto)}» no es una parte de una pieza de {c['nombre']}; partes que se pueden quitar: {_lista(todas)}"


def _resolver_maqueta(g: guion_presentacion.Guion, ci: int, llegaron: dict, visual: dict, avisar: Any) -> dict:
    """Lo que el plan guiado suma a lo visual (`elevacion`, `zoom`, `mirar`, `mostrar`, `ocultar`, `aislar` y `sin`), de
    lo que `llegaron`, resuelto contra el guion del capítulo `ci` de forma TOLERANTE: un número fuera de su rango se
    recorta, y una pieza, una parte o un lugar que no resuelve se descarta, las dos cosas con un aviso legible
    (`avisar(texto)`, con los candidatos). Devuelve lo que cambia sobre `visual` (el estado del que parte): también la
    lista que deja de tener una pieza porque la otra la nombró (lo último que se pide es lo que vale)."""
    c, piezas = g.capitulos[ci], g.piezas(ci)
    ids = [x["id"] for x in piezas]
    out: dict[str, Any] = {}
    for k, (lo, hi), decimales, que in (("elevacion", rec.ELEVACION, 0, "grados sobre el horizonte"),
                                        ("zoom", rec.ZOOM, 2, "veces el encuadre del paso")):
        if k not in llegaron:
            continue
        if llegaron[k] is None:
            out[k] = None
            continue
        w, tocado = _acotar(llegaron[k], lo, hi, decimales)
        if w is None:
            avisar(f"{k} «{_ver(llegaron[k])}» no es un número ({que}, de {lo:g} a {hi:g}): se ignoró")
            continue
        out[k] = w
        if tocado:
            avisar(f"{k} {_ver(llegaron[k])} quedó en {w:g} (va de {lo:g} a {hi:g})")
    if "mirar" in llegaron:
        v = llegaron["mirar"]
        x = g.mirable(ci, v.crudo if isinstance(v, NoVale) else v) if v is not None else None
        if v is None or x:
            out["mirar"] = x["id"] if x else None
        else:
            con_lugar = [k["id"] for k in g.componentes(ci) if k.get("enfoque")]
            avisar(f"la cámara no tiene dónde apuntar con «{_ver(v)}» en {c['nombre']}; puede mirar: "
                   f"{_lista(list(dict.fromkeys([*ids, *con_lugar])))}")
    for k in ("mostrar", "ocultar"):
        if k not in llegaron:
            continue
        crudo = llegaron[k].crudo if isinstance(llegaron[k], NoVale) else llegaron[k]
        nombres = _nombres(llegaron[k])
        if crudo is not None and (not isinstance(crudo, (list, str)) or (isinstance(crudo, list) and len(nombres) < len(crudo))):
            avisar(f"{k} lleva nombres de pieza (una lista de textos): no se usó «{_ver(crudo)}»")
            if not nombres:
                continue   # la lista sigue como estaba
        lista, malos = [], []
        for t in nombres:
            x = g.pieza(ci, t)
            if x:
                lista.append(x["id"])
            else:
                malos.append(t)
        lista = list(dict.fromkeys(lista))
        if malos:
            avisar(f"la pieza {', '.join(f'«{_ver(t)}»' for t in malos[:4])} no está en {c['nombre']} ({k}); "
                   f"piezas: {_lista(ids)}")
        if len(lista) > rec.MAX_LISTA:
            avisar(f"{k} lleva hasta {rec.MAX_LISTA} piezas: quedaron las primeras")
        if lista or not malos:   # si nada de lo pedido existe, la lista queda como estaba (no se vacía por un error)
            out[k] = lista[:rec.MAX_LISTA]
    if "aislar" in llegaron:
        v = llegaron["aislar"]
        x = g.pieza(ci, v.crudo if isinstance(v, NoVale) else v) if v is not None else None
        if v is None or x:
            out["aislar"] = x["id"] if x else None
        else:
            avisar(f"la pieza «{_ver(v)}» no está en {c['nombre']} (aislar); piezas: {_lista(ids)}")
    nuevo = {**visual, **out}
    if "sin" in llegaron:
        contexto = [x for x in (nuevo["aislar"], nuevo["mirar"], nuevo["enfoque"]) if x]
        lista, malas = [], 0
        for t in _nombres(llegaron["sin"]):
            parte, motivo = _resolver_parte(g, ci, t, contexto)
            if parte:
                lista.append(parte)
            else:
                malas += 1
                avisar(f"{motivo} (sin)")
        lista = list(dict.fromkeys(lista))
        if len(lista) > rec.MAX_LISTA:
            avisar(f"sin lleva hasta {rec.MAX_LISTA} partes: quedaron las primeras")
        if lista or not malas:
            out["sin"] = lista[:rec.MAX_LISTA]
    # Lo último que se pide es lo que vale: una pieza que ahora se muestra o se aísla deja de estar oculta, y una que
    # ahora se oculta deja de estar entre las que se muestran (si llegan las dos a la vez, queda oculta)
    ocultar = [x for x in nuevo["ocultar"]
               if x != out.get("aislar") and (x not in out.get("mostrar", ()) or "ocultar" in out)]
    mostrar = [x for x in nuevo["mostrar"] if x not in ocultar]
    if "aislar" not in out and nuevo["aislar"] and "ocultar" in out and nuevo["aislar"] in ocultar:
        out["aislar"] = None   # la aislada en un paso anterior que ahora se pide ocultar: deja de estar aislada
    for k, lista in (("ocultar", ocultar), ("mostrar", mostrar)):
        if lista != nuevo[k]:
            out[k] = lista
    return out


def _resolver_mover(v: Any, avisar: Any) -> dict | None:
    """El `mover` de un paso o de `visual` ({giro?, zoom?, elevacion?}, cada parte dentro de su rango), o None si no
    pide nada. Tolerante: un número suelto es el giro, lo que se sale de su rango se recorta y lo que no es un número
    se descarta, con su aviso."""
    if isinstance(v, MoverEntrada):
        crudo: Any = v.model_dump(exclude_none=True)
    else:
        crudo = v.crudo if isinstance(v, NoVale) else v
        if isinstance(crudo, (int, float)) and not isinstance(crudo, bool):
            crudo = {"giro": crudo}
    if not isinstance(crudo, dict):
        if crudo not in (None, True, False):
            avisar("mover lleva giro, zoom o elevacion (números): se ignoró")
        return None
    de_mas = [k for k in crudo if k not in rec.MOVER]
    if de_mas:
        avisar(f"mover solo lleva giro, zoom y elevacion: no se usó {', '.join(f'«{_ver(k)}»' for k in de_mas[:3])}")
    out = {}
    for k, (lo, hi), decimales in (("giro", rec.GIRO, 0), ("zoom", rec.ZOOM, 2), ("elevacion", rec.ELEVACION, 0)):
        if crudo.get(k) is None:
            continue
        w, tocado = _acotar(crudo[k], lo, hi, decimales)
        if w is None:
            avisar(f"mover.{k} «{_ver(crudo[k])}» no es un número: se ignoró")
            continue
        out[k] = w
        if tocado:
            avisar(f"mover.{k} {_ver(crudo[k])} quedó en {w:g} (va de {lo:g} a {hi:g})")
    if out.get("giro") == 0:
        del out["giro"]   # girar cero grados no es moverse
    return out or None


def _visual(g: guion_presentacion.Guion, e: dict, a: PresentacionEntrada,
            desde_pantalla: bool) -> tuple[dict, str, dict, dict]:
    """La op `visual`: resuelve contra el guion lo que se pidió (los componentes y las piezas de la maqueta del capítulo,
    por id o por nombre, y la inmersión del catálogo) y devuelve (lo que recibe el modelo, el resumen, los cambios
    exactos de lo visual para la pantalla y el navegador, y las acciones que no son estado: `mover`, `animar` y
    `simular`, este contra los controles del modelo que queda a la vista: el del atlas o, sin él, la maqueta). El
    capítulo es el que se indicó (el del contexto del panel) o el de la pantalla en off, y el paso, el que se indicó
    (el de la pestaña: lo que la persona toca a mano en la vista del panel no mueve la pantalla en off) o el de la
    pantalla; con una pantalla en off (o por MCP) los dos tienen que ser los suyos. Un componente o una inmersión
    que no existe vuelve con su error y sus candidatos, como siempre; lo que suma el plan guiado (la elevación, el
    acercamiento, a qué apunta la cámara, las piezas, las partes, el movimiento) es tolerante: lo que no resuelve se
    descarta con un aviso y lo demás se aplica, y solo es un error si no queda nada que hacer."""
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
    # el paso de partida: el que se indicó (el de la pestaña) o, en el capítulo de la pantalla, el suyo
    paso = _resolver_paso(g, ci, a.paso) + 1 if a.paso is not None else None
    if desde_pantalla and paso is not None and paso != e["paso"]:
        raise ErrorHerramienta(
            f"La pantalla muestra el paso {e['paso']} de {c['nombre']}, no el {paso}: vaya primero a ese paso con ir.",
            "invalido", estado=409, detalle={"en_pantalla": {"capitulo": c["id"], "paso": e["paso"]}})
    mismo = ci == g.por_id(e["capitulo"]) and paso in (None, e["paso"])
    if paso is None and mismo:
        paso = e["paso"]
    contenido: dict[str, Any] = {"capitulo": _cap_para_modelo(c)}
    cambios: dict[str, Any] = {}
    dicho: list[str] = []
    avisos: list[str] = []
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
    # El capítulo o el paso pueden ser otros que los de la pantalla (los de la pestaña del chat): entonces lo visual parte
    # de lo del paso
    base = {k: e[k] for k in rec.VISUAL} if mismo else rec.visual_inicial()
    cambios.update(_resolver_maqueta(g, ci, partes, {**base, **{k: v for k, v in cambios.items() if k in rec.VISUAL}},
                                     avisos.append))
    if cambios.get("camara") == "paso":   # el encuadre del paso es también su rumbo, su elevación y su acercamiento
        for k in ("rumbo", "elevacion", "zoom"):
            if k not in partes:
                cambios[k] = None
    if "camara" in cambios:
        dicho.append(NOMBRE_CAMARA[cambios["camara"]])
    if "rumbo" in cambios and ("rumbo" in partes or cambios.get("camara") != "paso"):
        dicho.append("el rumbo del paso" if cambios["rumbo"] is None else f"mirando desde el rumbo {cambios['rumbo']}°")
    if cambios.get("elevacion") is not None:
        dicho.append(f"a {cambios['elevacion']}° sobre el horizonte")
    if cambios.get("zoom") is not None:
        dicho.append(f"zoom {cambios['zoom']:g}")
    piezas = {x["id"]: x["nombre"] for x in g.piezas(ci)}
    nombre = lambda i: piezas.get(i) or next((x["nombre"] for x in g.componentes(ci) if x["id"] == i), i)   # noqa: E731
    if "mirar" in cambios:
        dicho.append(f"la cámara apunta a «{nombre(cambios['mirar'])}»" if cambios["mirar"] else
                     "la cámara vuelve a lo que encuadra el paso")
    if "aislar" in cambios:
        dicho.append(f"solo «{nombre(cambios['aislar'])}»" if cambios["aislar"] else "todas las piezas del paso otra vez")
    for k, verbo in (("mostrar", "además"), ("ocultar", "sin")):
        if cambios.get(k):
            dicho.append(f"{verbo} {', '.join(f'«{nombre(i)}»' for i in cambios[k])}")
    if "sin" in cambios:
        dicho.append(f"sin {', '.join(cambios['sin'])}" if cambios["sin"] else "las piezas con todas sus partes")
    if "girar" in cambios:
        dicho.append("la cámara gira" if cambios["girar"] else "la cámara quieta")
    if "comparar" in cambios:
        dicho.append("el sitio como está hoy" if cambios["comparar"] == "hoy" else "con el proyecto")
    if "tema" in cambios:
        dicho.append(f"tema {cambios['tema']}")
    acciones: dict[str, Any] = {}
    mover = _resolver_mover(a.mover, avisos.append) if a.mover is not None else None
    if mover:
        acciones["mover"] = mover
        dicho.append("la cámara " + _mover_dicho(mover))
    if a.animar is True:
        acciones["animar"] = True
        dicho.append("la animación del paso otra vez")
    elif isinstance(a.animar, NoVale):
        avisos.append("animar es true o false: se ignoró")
    # La simulación: en el modelo del atlas que queda abierto (el que abre esta orden, el que había o el del paso de
    # inmersión, el de la pestaña si se indicó o el de la pantalla) o, sin uno, en la maqueta 3D (en un paso que se sabe,
    # o en un capítulo sin modelos del atlas); de otro capítulo que el de la pantalla y sin el paso, solo el que abre esta
    # orden o la maqueta de un capítulo sin modelos del atlas
    modelo = None
    if a.simular is not None:
        pedida = cambios["inmersion"] if "inmersion" in cambios else base["inmersion"]
        modelo = rec.simulable_en(c["id"], paso, pedida, g)
        if a.simular == []:
            avisos.append("simular vino vacío: diga qué controles accionar, [{control, valor}] (de «controles»)")
        # (sin pantalla en off, el modelo puede estar en la pestaña, en un paso que la persona abrió a mano)
        simular = _resolver_simular(g, modelo, a.simular, avisos.append, "" if desde_pantalla or a.paso is not None else
                                    ", o diga capitulo y paso: los del contexto del panel", capitulo=c["id"])
        if simular:
            acciones["simular"] = simular
            dicho.append(f"en «{g.nombre_modelo(modelo)}»: {_simular_dicho(g, modelo, simular, c['id'])}")
            contenido["simulacion"] = SIMULACION_MAQUETA if modelo == rec.MAQUETA else SIMULACION
    if not cambios and not acciones:
        hay = g.controles(modelo, c["id"])
        raise ErrorHerramienta("No quedó nada que mostrar: " + ("; ".join(avisos[:4]) or "lo pedido no cambia nada") + ".",
                               "no_existe", estado=404,
                               detalle={"capitulo": c["id"], "maqueta": _maqueta_para_modelo(g, ci),
                                        **({"controles": hay} if hay else {})})
    if avisos:
        contenido["avisos"] = avisos[:MAX_AVISOS]
    contenido["nota"] = (
        "Cambia lo que se ve sin cambiar de paso; al pasar a otro paso vuelve a lo del paso (salvo el tema). Explique "
        "en el chat con los datos de la ficha (no invente otros)." + (
            " Lo de «avisos» no se pudo mostrar; lo demás sí." if avisos else "") + (
            "" if desde_pantalla or (a.capitulo is not None and a.paso is not None) else
            " Sin el capítulo y el paso de partida se tomaron los de la pantalla en off: si la presentación de la "
            "pestaña está en otro, indique capitulo y paso (los del contexto del panel)."))
    return contenido, "La presentación muestra " + ", ".join(dicho or ["lo mismo"]), cambios, acciones


# Lo que el modelo recibe cuando `visual` acciona una simulación (en un modelo del atlas o en la maqueta 3D)
SIMULACION = ("Se acciona en el modelo del atlas como lo haría la persona, en orden; lo que tarda en aparecer (el modelo "
              "carga, un cálculo en curso) se espera unos segundos. Un valor cambiado no recalcula: si el control dice "
              "que cuenta en el siguiente cálculo, después la acción que calcula.")
SIMULACION_MAQUETA = ("Se acciona en la maqueta 3D en el acto y en orden. La hora, las luces y el partido quedan hasta otro "
                      "cambio y vuelven a lo del paso al cambiar de paso (el tema solo devuelve la hora): repítalos en el "
                      "paso siguiente si siguen. reproducir_dia lleva el sol de la mañana a la noche en 24 s (dele dos "
                      "pasos o sostener). El partido solo se juega con la Cancha de Sóftbol Casabe en el encuadre.")


def _mover_dicho(m: dict) -> str:
    """«gira 40°, termina con zoom 1.5 y a 60°»: lo que hace la cámara con un `mover`."""
    return ", ".join(x for x in (f"gira {m['giro']}°" if "giro" in m else "",
                                 f"termina con zoom {m['zoom']:g}" if "zoom" in m else "",
                                 f"termina a {m['elevacion']}° sobre el horizonte" if "elevacion" in m else "") if x)


def _cifra(v: float) -> str:
    """Un número como se dice en la sala: «6,5», «200»."""
    return f"{v:g}".replace(".", ",")


def _valor_de_control(c: dict, x: SimularEntrada) -> tuple[Any, str | None, bool]:
    """El valor exacto para el control `c` (del guion) a partir de lo que pidió el modelo, tolerante: (valor, aviso, si
    se acciona). Una acción va sin valor (el que traiga se ignora); sí o no acepta true/false, «sí»/«no» y, sin valor,
    es sí; un número (también «6,5») se recorta a su rango y se ajusta a su paso, como el deslizador; una opción, por su
    id o su nombre."""
    tipo, v, dado = c["tipo"], x.valor, "valor" in x.model_fields_set and x.valor is not None
    if tipo == "accion":
        return None, ("es una acción: va sin valor (se accionó igual)" if dado else None), True
    if tipo == "si_no":
        if not dado:
            return True, None, True
        w = v if isinstance(v, bool) else {"si": True, "true": True, "1": True, "no": False, "false": False,
                                            "0": False}.get(guion_presentacion.clave(str(v)))
        return (w, None, True) if w is not None else (None, f"va con true o false, no «{_ver(v)}»: se ignoró", False)
    if tipo == "numero":
        lo, hi, paso = c.get("min"), c.get("max"), c.get("paso")
        unidad = f" {c['unidad']}" if c.get("unidad") else ""
        rango = f"de {_cifra(lo)} a {_cifra(hi)}{unidad}"
        w, _ = _acotar(v, -math.inf, math.inf, 6) if dado else (None, True)
        if w is None:
            return None, f"va con un número {rango}" + (f", no «{_ver(v)}»" if dado else "") + ": se ignoró", False
        ajustado = min(hi, max(lo, w))
        if paso:
            dec = len(f"{paso:g}".split(".")[1]) if "." in f"{paso:g}" else 0
            ajustado = round(lo + round((ajustado - lo) / paso) * paso, dec)
            ajustado = min(hi, max(lo, ajustado))
        if isinstance(ajustado, float) and ajustado.is_integer():
            ajustado = int(ajustado)
        aviso = f"{_cifra(w)} quedó en {_cifra(ajustado)} (va {rango})" if not lo <= w <= hi else None
        return ajustado, aviso, True
    opciones = c.get("opciones") or []
    if dado and not isinstance(v, bool):
        texto = _cifra(v).replace(",", ".") if isinstance(v, (int, float)) else v
        o = guion_presentacion.parecido(opciones, texto)
        if o:
            return o["id"], None, True
    return None, (f"no tiene la opción «{_ver(v)}»" if dado else "le falta cuál opción") + \
        f": se ignoró; opciones: {_lista([o['id'] for o in opciones], 12)}", False


def _del_atlas(g: guion_presentacion.Guion, texto: Any, exacto: bool = False) -> dict | None:
    """La inmersión del catálogo que tiene el control `texto` (por su id o su nombre; sin `exacto`, también el único que
    tiene esas palabras), o None."""
    k = guion_presentacion.clave(texto)
    if not k:
        return None
    for i in g.inmersiones:
        lista = i.get("controles") or []
        if (any(k in (guion_presentacion.clave(x["id"]), guion_presentacion.clave(x.get("nombre"))) for x in lista)
                if exacto else guion_presentacion.parecido(lista, texto)):
            return i
    return None


def _de_la_maqueta(g: guion_presentacion.Guion, texto: Any, capitulo: Any) -> dict | None:
    """El control de la maqueta 3D en el capítulo por su id o su nombre; si no es uno de esos y sí lo es (igual) de un
    modelo del atlas, None («reproducir» es el del simulador sísmico, no el día); si no, el único que tiene esas palabras."""
    lista = g.controles(rec.MAQUETA, capitulo)
    k = guion_presentacion.clave(texto)
    igual = next((x for x in lista if k and k in (guion_presentacion.clave(x["id"]),
                                                  guion_presentacion.clave(x.get("nombre")))), None)
    if igual is not None or _del_atlas(g, texto, exacto=True):
        return igual
    return guion_presentacion.parecido(lista, texto)


def _resolver_simular(g: guion_presentacion.Guion, modelo: str | None, crudo: Any, avisar: Any,
                      abrir: str = "", capitulo: str | None = None) -> list[dict] | None:
    """`simular` (de un paso del plan o de `visual`) resuelto contra los controles del modelo que queda a la vista
    (`modelo`: una inmersión o, sin un modelo del atlas, la maqueta 3D en el `capitulo`, rec.MAQUETA): cada control por
    su id o su nombre y su valor exacto (`_valor_de_control`). TOLERANTE: lo que no resuelve se descarta con un aviso
    legible (con los controles que sí hay; uno de un modelo del atlas que no está abierto, o de la maqueta en otro
    capítulo, lo dice) y lo demás se acciona en orden; sin un modelo a la vista, o en uno sin controles, no se acciona
    nada; en la maqueta, si todo lo pedido es de un modelo del atlas, tampoco (`abrir`: qué más decir de cómo abrirlo).
    None si no queda nada."""
    if crudo is None:
        return None
    if isinstance(crudo, NoVale) or not isinstance(crudo, list):
        avisar("simular es una lista de {control, valor}: no se accionó nada")
        return None
    if not crudo:
        return None
    sin_atlas = (f"simular acciona los controles del modelo del atlas abierto y ahí no hay uno (ábralo con "
                 f"inmersion{abrir}): no se accionó nada")
    if modelo is None:
        avisar(sin_atlas)
        return None
    maqueta = modelo == rec.MAQUETA
    nombre = g.nombre_modelo(modelo)
    controles = g.controles(modelo, capitulo)
    if not controles:
        if maqueta:
            avisar(f"«{nombre}» no tiene controles en este capítulo: no se accionó nada")
        else:
            con = [i["id"] for i in g.inmersiones if i.get("controles")]
            avisar(f"«{nombre}» no tiene controles que accionar: no se accionó nada; los tienen: {_lista(con)}")
        return None
    resolver = (lambda t: _de_la_maqueta(g, t, capitulo)) if maqueta else (lambda t: g.control(modelo, t))  # noqa: E731
    pedidos = [x for x in crudo if isinstance(x, SimularEntrada)]
    if maqueta and pedidos and not any(resolver(x.control) for x in pedidos) and \
            any(_del_atlas(g, x.control) for x in pedidos):
        # lo pedido es de un modelo del atlas y no hay uno a la vista: el aviso de siempre, y lo que tiene la maqueta
        avisar(f"{sin_atlas}; la maqueta 3D tiene: {_lista([k['id'] for k in controles])}")
        return None
    if len(crudo) > rec.MAX_SIMULAR:
        avisar(f"simular lleva hasta {rec.MAX_SIMULAR} controles por orden: quedaron los primeros {rec.MAX_SIMULAR}")
        crudo = crudo[:rec.MAX_SIMULAR]
    out: list[dict] = []
    for x in crudo:
        if not isinstance(x, SimularEntrada):
            avisar(f"simular: «{_ver(x)}» no es un {{control, valor}}: se ignoró")
            continue
        c = resolver(x.control)
        if c is None:
            hay = _lista([k["id"] for k in controles], 25)
            otro = guion_presentacion.parecido((g.maqueta or {}).get("controles") or [], x.control) if maqueta else None
            atlas = _del_atlas(g, x.control) if maqueta else None
            if otro is not None and otro.get("capitulos"):
                ci = g.por_id(capitulo)
                donde = g.capitulos[ci]["nombre"] if ci is not None else "este capítulo"
                en = ", ".join(g.capitulos[k]["nombre"] for k in map(g.por_id, otro["capitulos"]) if k is not None)
                avisar(f"«{nombre}» no tiene el control «{otro['id']}» en {donde} (está en: {en}): se ignoró; "
                       f"controles: {hay}")
            elif atlas is not None:
                avisar(f"«{_ver(x.control)}» es del modelo del atlas «{atlas.get('nombre') or atlas['id']}», que no está "
                       f"abierto (ábralo con inmersion{abrir}): se ignoró")
            else:
                avisar(f"«{nombre}» no tiene el control «{_ver(x.control)}»: se ignoró; controles: {hay}")
            continue
        valor, aviso, sirve = _valor_de_control(c, x)
        if aviso:
            avisar(f"simular «{c['id']}» {aviso}")
        if sirve:
            out.append({"control": c["id"], **({"valor": valor} if c["tipo"] != "accion" else {})})
    return out or None


def _simular_dicho(g: guion_presentacion.Guion, modelo: str | None, s: list[dict], capitulo: str | None = None) -> str:
    """«Magnitud de momento (Mw) 6,5; Calcular el sismo» o «Hora del día: Noche; Luces de la maqueta: sí»: lo que
    acciona `simular`, con los nombres de sus controles."""
    partes = []
    for x in s:
        c = g.control(modelo, x["control"], capitulo) or {"nombre": x["control"], "tipo": "accion"}
        v = x.get("valor")
        if c["tipo"] == "numero":
            partes.append(f"{c['nombre']} {_cifra(v)}{' ' + c['unidad'] if c.get('unidad') else ''}")
        elif c["tipo"] == "opcion":
            partes.append(f"{c['nombre']}: {next((o['nombre'] for o in c.get('opciones') or [] if o['id'] == v), v)}")
        elif c["tipo"] == "si_no":
            partes.append(f"{c['nombre']}: {'sí' if v else 'no'}")
        else:
            partes.append(c["nombre"])
    return "; ".join(partes)


def _maqueta_para_modelo(g: guion_presentacion.Guion, ci: int) -> list[dict]:
    """Las piezas de la maqueta del capítulo, compactas: id, nombre y los ids de sus partes («pieza.parte» en `sin`)."""
    return [{"id": x["id"], "nombre": x["nombre"], **({"partes": [p["id"] for p in x["partes"]]} if x["partes"] else {})}
            for x in g.piezas(ci)]


# ───────────────────────────── el plan guiado (el recorrido narrado) ─────────────────────────────

NOTA_GUION = (
    "Con estos datos arme UN plan (op recorrido): titulo, pasos y cierre. De 6 a 10 pasos (hasta 12); cada paso es UNA "
    "frase hablada (dice) y algo que ocurre en pantalla MIENTRAS se dice: la cámara (camara, rumbo, elevacion, zoom, "
    "mirar, o un viaje con mover {giro, zoom, elevacion}), las piezas de «maqueta» (aislar una, mostrar, ocultar, o "
    "quitarle partes con sin «pieza.parte»), enfoque, detalle (la ficha) con resaltar, comparar hoy o proyecto, una "
    "inmersion y sus controles (simular [{control, valor}], de «controles» en inmersiones: la magnitud del simulador "
    "sísmico y luego calcular, que la hace temblar; sin inmersión, los de «controles_maqueta»: hora (manana a noche), "
    "reproducir_dia, luces (vivienda y urbanismo) y partido (urbanismo), que vuelven a lo del paso al cambiar de paso: "
    "repítalos), animar, y el gesto del presentador (de «gestos»: saludar al comenzar, comparar hoy y proyecto, "
    "invitar al final). "
    "Cada paso parte del anterior: lo que no nombra sigue igual, y al cambiar de paso del capítulo "
    "lo visual vuelve a lo de ese paso. Un arco que sirve: ubicar con una vista amplia; cómo está hoy; qué se construye "
    "(aislar la obra, quitarle la cubierta, rodearla con mover); el dato clave (la ficha con la especificación "
    "resaltada, un modelo del atlas); qué cambia y cuándo (la meta o la cifra resaltada); y un cierre de 2 o 3 ideas. "
    "La frase nombra lo que se ve en ese momento, con las cifras tal como vienen aquí y sin costos. Lo que se puede "
    "resaltar en cada paso está en «resaltable». Lo opcional que no exista se descarta con un aviso y el plan corre "
    "igual. Ejemplo: {\"op\":\"recorrido\",\"titulo\":\"La torre del hospital\",\"pasos\":[{\"capitulo\":\"salud\","
    "\"paso\":\"torre\",\"camara\":\"oblicua\",\"mover\":{\"giro\":40},\"dice\":\"…\"},{\"aislar\":\"torre\",\"sin\":"
    "[\"torre.cubierta\"],\"elevacion\":55,\"dice\":\"…\"},{\"detalle\":\"torre\",\"resaltar\":{\"especificacion\":"
    "\"Estructura\"},\"dice\":\"…\"}],\"cierre\":{\"puntos\":[\"…\",\"…\"]}}")
NOTA_RECORRIDO = (
    "El plan ya se está ejecutando: el chat lo muestra entero y la sala lo ve y lo oye, paso a paso. La explicación ES "
    "la narración: en el chat no la repita ni la resuma; cierre solo con una pregunta corta. Si vienen «avisos», el plan "
    "corre igual con lo que sí valía: no lo mande otra vez por eso, téngalos en cuenta en el próximo. Si la persona "
    "escribe, el plan se pausa: responda breve y siga con control_recorrido (continuar), o arme otro plan.")
HACE = {"paso": "cambia de paso", "camara": "mueve la cámara", "enfoque": "enfoca una obra", "ficha": "abre una ficha",
        "hoy": "muestra hoy", "proyecto": "muestra el proyecto", "modelo": "abre un modelo del atlas",
        "resaltar": "resalta", "solo3d": "solo 3D", "girar": "gira", "capas": "muestra u oculta piezas",
        "aislar": "aísla una obra", "partes": "quita partes", "mover": "recorre con la cámara",
        "mirar": "apunta la cámara", "animar": "anima la obra", "simular": "maneja la simulación",
        "gesto": "el presentador hace un gesto"}
_NUMERO = re.compile(r"\d[\d.,]*\d|\d")
# Lo que la cámara puede traer en un paso del plan: si nada de esto cambia (ni el paso), el paso no le pide nada
DE_LA_CAMARA = ("camara", "rumbo", "elevacion", "zoom", "mirar", "enfoque")


# `gesto` también puede llegar con tildes, en otras palabras o como lo que expresa
SINONIMOS_GESTO = {"senala": "senalar", "apuntar": "senalar", "indicar": "senalar", "saludo": "saludar",
                   "hola": "saludar", "pulgar": "aprobar", "ok": "aprobar", "contar": "enumerar", "aplauso": "aplaudir",
                   "panel": "mostrar_panel", "maqueta": "mirar_maqueta", "mirar": "mirar_maqueta", "chao": "despedirse",
                   "adios": "despedirse", "preguntas": "invitar", "bienvenida": "invitar", "duda": "preguntar",
                   "no": "negar", "si": "asentir", "importante": "destacar", "clave": "destacar",
                   "construccion": "construir", "obra": "construir", "logro": "celebrar", "union": "juntos",
                   "compromiso": "corazon", "tranquilidad": "calmar", "aumentar": "crecer", "precision": "detalle"}


def _resolver_gesto(crudo: Any, avisar: Any) -> str | None:
    """El gesto del presentador en un paso del plan: su nombre (de `recorrido.GESTOS`, sin tildes ni mayúsculas, con
    `_` o espacios) o un sinónimo; lo que no es ninguno se descarta con un aviso (el presentador elige solo)."""
    v = crudo.crudo if isinstance(crudo, NoVale) else crudo
    c = guion_presentacion.clave(v).replace(" ", "_") if isinstance(v, str) else ""
    nombre = c if c in rec.GESTOS else SINONIMOS_GESTO.get(c)
    if not nombre:
        avisar(f"el presentador no tiene el gesto «{_ver(v)}»: elige solo; gestos: {_lista(list(rec.GESTOS))}")
    return nombre


def _con_paso(e: ErrorHerramienta, n: int) -> ErrorHerramienta:
    """El error de un paso del plan, con su número al comienzo y en el detalle (el modelo corrige ese)."""
    return ErrorHerramienta(f"Paso {n}: {e}", e.codigo, estado=e.estado, detalle={"paso": n, **(e.detalle or {})})


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


def _paso_tolerante(g: guion_presentacion.Guion, ci: int, v: Any) -> int | None:
    """El índice (desde 0) del paso del capítulo `ci` que un paso del plan nombró: su número, su id, o el id o el título
    escritos a su manera («Torre», «la torre nueva»); None si no es ninguno."""
    v = v.crudo if isinstance(v, NoVale) else v
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, bool) or not isinstance(v, (int, str)):
        return None
    pi = g.paso(ci, v)
    if pi is not None or not isinstance(v, str):
        return pi
    pasos = [{"id": p["id"], "nombre": p["titulo"], "i": i} for i, p in enumerate(g.capitulos[ci]["pasos"])]
    x = guion_presentacion.parecido(pasos, v)
    return x["i"] if x else None


def _texto_del_paso(x: EscenaEntrada, extras: dict, avisar: Any) -> tuple[str | None, str]:
    """La frase de un paso del plan (`dice`; también `narracion`, o `texto` o `frase` si el modelo la llamó así), ya con
    las reglas de lo que se proyecta, o (None, por qué no vale). Estas reglas no se relajan: es lo que ve la sala."""
    dados = [v.crudo if isinstance(v, NoVale) else v for v in (x.dice, x.narracion) if v is not None]
    if len(dados) == 2 and dados[0] != dados[1]:
        avisar("trae dice y narracion: se usó dice")
    if not dados:
        otra = next((k for k in extras if guion_presentacion.clave(k) in ("dice", "narracion", "texto", "frase")
                     and isinstance(extras[k], str)), None)
        if otra is None:
            return None, "falta dice (la frase que se dice mientras se ve)"
        dados = [extras.pop(otra)]
        avisar(f"«{_ver(otra)}» se tomó como dice")
    if not isinstance(dados[0], str):
        return None, "dice tiene que ser un texto"
    try:
        return texto_proyectable(dados[0], rec.MAX_NARRACION), ""
    except ValueError as e:
        return None, str(e)


def _componer(g: guion_presentacion.Guion, a: PresentacionEntrada) -> tuple[dict, list[str], set[int]]:
    """Los pasos del plan (cada uno un cambio sobre el anterior) como recorrido absoluto, resueltos contra el guion.
    Devuelve (el recorrido, los avisos y los números de los pasos que recibieron el movimiento de cámara por omisión).

    TOLERANTE: lo opcional que no resuelve (una pieza de la maqueta, una parte, a qué apunta la cámara, un componente,
    una inmersión, lo que se resalta, un control de la simulación del modelo del atlas, el capítulo o el paso de un paso
    que no es el primero, un valor sin la forma o una clave que no existe) se descarta, y un número fuera de su rango se
    recorta; cada cosa deja un aviso legible con
    el número del paso y los candidatos, y el plan corre con lo demás. Solo es un error (y entonces no se guarda nada)
    que el primer paso no tenga un capítulo que resuelva o que un texto no se pueda proyectar: esas reglas no se
    relajan, y el error dice en qué paso. Un paso que no le pide nada a la cámara recibe un movimiento suave
    (`GIROS_SUAVES`, alternando el sentido, y `ZOOM_SUAVE`): la imagen nunca queda quieta mientras se habla. No dentro
    de un modelo del atlas ni con la cámara girando sola."""
    escenas: list[dict] = []
    avisos: list[str] = []
    textos_malos: dict[str, list[int]] = {}
    suaves: set[int] = set()
    zoom_fin: float | None = None   # el acercamiento con que terminó el último `mover` (la cámara sigue desde ahí)
    ci = pi = None
    panel, visual = True, rec.visual_inicial()
    for n, x in enumerate(a.plan(), 1):
        def avisar(t: str, n: int = n) -> None:
            avisos.append(f"Paso {n}: {t}")
        extras = dict(x.model_extra or {})
        texto, motivo = _texto_del_paso(x, extras, avisar)
        if texto is None:
            textos_malos.setdefault(motivo, []).append(n)
        if extras:
            avisar("no se usó " + ", ".join(f"«{_ver(k)}»" for k in list(extras)[:4]) + " (no es de un paso del plan)")
        # Dónde: el capítulo y su paso. Solo el capítulo del primer paso del plan es obligatorio
        nci = ci
        if x.capitulo is not None:
            pedido = x.capitulo.crudo if isinstance(x.capitulo, NoVale) else x.capitulo
            try:
                if not isinstance(pedido, str) or not pedido.strip():
                    raise ErrorHerramienta(f"«{_ver(pedido)}» no es un capítulo.", "no_existe", estado=404, detalle={
                        "capitulos": [_cap_para_modelo(k) for k in g.capitulos]})
                nci = _resolver_capitulo(g, pedido)
            except ErrorHerramienta as e:
                if ci is None:
                    raise _con_paso(e, n) from None
                avisar(f"{e} Sigue en {g.capitulos[ci]['nombre']}; capítulos: {_lista([k['id'] for k in g.capitulos])}")
        if nci is None:
            raise ErrorHerramienta(f"Paso {n}: el primer paso del plan dice su capitulo (id o nombre, del índice).",
                                   "invalido", estado=422,
                                   detalle={"paso": n, "capitulos": [_cap_para_modelo(k) for k in g.capitulos]})
        npi = pi if nci == ci else 0
        if x.paso is not None:
            pedido = _paso_tolerante(g, nci, x.paso)
            if pedido is None:
                k = g.capitulos[nci]
                avisar(f"{k['nombre']} no tiene el paso «{_ver(x.paso)}»: "
                       f"{'sigue en el mismo paso' if nci == ci else 'va a su primer paso'}; pasos: "
                       f"{_lista([p['id'] for p in k['pasos']], 20)}")
            else:
                npi = pedido
        otro = (nci, npi) != (ci, pi)
        if otro:
            visual = rec.visual_inicial()   # otro paso: lo visual vuelve a lo del paso (visual.js, pantalla)
        ci, pi = nci, npi
        c = g.capitulos[ci]
        antes = visual
        dado = {k: getattr(x, k) for k in rec.VISUAL if k in x.model_fields_set}
        partes: dict[str, Any] = {}
        # La cámara con nombre, el rumbo, girar y hoy o proyecto: un valor vacío no pide nada
        v = dado.get("camara")
        if v is not None:
            camara = guion_presentacion.clave(v.crudo) if isinstance(v, NoVale) and isinstance(v.crudo, str) else v
            if camara in CAMARAS:
                partes["camara"] = camara
                if camara == "paso":   # el encuadre del paso es también su rumbo, su elevación y su acercamiento
                    partes.update({k: None for k in ("rumbo", "elevacion", "zoom") if k not in dado})
            else:
                avisar(f"camara «{_ver(v)}» no es de la lista ({', '.join(CAMARAS)}): se ignoró")
        if "rumbo" in dado:
            w, _ = _acotar(dado["rumbo"], -3600, 3600) if dado["rumbo"] is not None else (None, False)
            if dado["rumbo"] is not None and w is None:
                avisar(f"rumbo «{_ver(dado['rumbo'])}» no es un número (grados desde el norte, de 0 a 359): se ignoró")
            else:
                partes["rumbo"] = w % 360 if w is not None else None
        for k, valores in (("girar", (True, False)), ("comparar", ("hoy", "proyecto"))):
            v = dado.get(k)
            if isinstance(v, NoVale):
                texto_k = guion_presentacion.clave(v.crudo) if isinstance(v.crudo, str) else None
                v = {"true": True, "si": True, "false": False, "no": False}.get(texto_k, texto_k) if k == "girar" else texto_k
                if v not in valores:
                    avisar(f"{k} «{_ver(dado[k])}» no vale ({'true o false' if k == 'girar' else 'hoy o proyecto'}): se ignoró")
                    continue
            if v is not None:
                partes[k] = v
        # Los componentes y el modelo del atlas
        if "enfoque" in dado:
            v = dado["enfoque"].crudo if isinstance(dado["enfoque"], NoVale) else dado["enfoque"]
            comp = guion_presentacion.parecido(g.componentes(ci), v) if v is not None else None
            if v is None or (comp and comp.get("enfoque")):
                partes["enfoque"] = comp["id"] if comp else None
            else:
                pieza = g.pieza(ci, v) if "mirar" not in dado else None
                con_lugar = [k["id"] for k in g.componentes(ci) if k.get("enfoque")]
                if pieza:   # una pieza de la maqueta que no es un componente con lugar: la cámara sí puede apuntarle
                    dado["mirar"] = pieza["id"]
                    avisar(f"«{pieza['nombre']}» no es un componente con lugar propio (enfoque): la cámara apunta a esa "
                           "pieza (mirar)")
                else:
                    avisar(f"«{_ver(v)}» no es un componente con lugar en la maqueta de {c['nombre']}: no se enfocó; "
                           f"con lugar: {_lista(con_lugar)}")
        if "detalle" in dado:
            v = dado["detalle"].crudo if isinstance(dado["detalle"], NoVale) else dado["detalle"]
            comp = guion_presentacion.parecido(g.componentes(ci), v) if v is not None else None
            if v is None or comp:
                partes["detalle"] = comp["id"] if comp else None
            else:
                avisar(f"{c['nombre']} no tiene el componente «{_ver(v)}»: no se abrió la ficha; componentes: "
                       f"{_lista([k['id'] for k in g.componentes(ci)])}")
        if "inmersion" in dado:
            v = dado["inmersion"].crudo if isinstance(dado["inmersion"], NoVale) else dado["inmersion"]
            modelo = guion_presentacion.parecido([dict(i) for i in g.inmersiones], v) if v is not None else None
            if v is None or modelo or guion_presentacion.clave(v) == "maqueta":
                partes["inmersion"] = modelo["id"] if modelo else None if v is None else "maqueta"
            else:
                avisar(f"no hay un modelo del atlas «{_ver(v)}»: no se abrió; modelos: "
                       f"{_lista([i['id'] for i in g.inmersiones])}")
        # La elevación, el acercamiento, a qué apunta la cámara, las piezas de la maqueta y sus partes
        partes.update(_resolver_maqueta(g, ci, {k: v for k, v in dado.items() if k not in partes},
                                        {**visual, **partes}, avisar))
        visual = {**visual, **partes}
        if visual["aislar"] and "aislar" not in partes and visual["mirar"] != visual["aislar"] and \
                partes.get("mirar") in {k["id"] for k in g.piezas(ci)}:
            avisar(f"la cámara apunta a «{visual['mirar']}», pero solo se ve «{visual['aislar']}» (aislar sigue de un "
                   "paso anterior; aislar: nada lo quita)")
        if isinstance(x.panel, bool):
            panel = x.panel
        elif x.panel is not None:
            avisar("panel es true o false: se ignoró")
        resaltar = None
        if isinstance(x.resaltar, NoVale):
            avisar("resaltar lleva exactamente una de: cifra, punto, leyenda, especificacion o componente; no se "
                   "resaltó nada")
        elif x.resaltar is not None:
            try:
                resaltar = _resolver_resaltar(g, ci, pi, visual, panel, x.resaltar)
            except ErrorHerramienta as e:
                avisar(f"{e} No se resaltó nada.")
        mover = _resolver_mover(x.mover, avisar) if x.mover is not None else None
        if isinstance(x.animar, NoVale):
            avisar("animar es true o false: se ignoró")
        gesto = _resolver_gesto(x.gesto, avisar) if x.gesto is not None else None
        esc = {"capitulo": c["id"], "paso": pi + 1, "panel": panel, "visual": rec.copia_visual(visual),
               "resaltar": resaltar, "mover": mover, "animar": x.animar is True, "simular": None,
               "frases": rec.partir_frases(texto) if texto else ["…"], "sostener_ms": 0}
        if gesto:
            esc["gesto"] = gesto
        # Los controles de la simulación del modelo que este paso deja a la vista (el del atlas o, sin él, la maqueta)
        if x.simular is not None:
            esc["simular"] = _resolver_simular(g, rec.simulable_de(esc, g), x.simular, avisar, capitulo=c["id"])
        # Que nunca quede quieta: sin nada para la cámara (el mismo paso, el mismo encuadre y sin `mover`), un viaje suave
        # (también el primer paso, si no trae nada para la cámara: la pantalla puede estar ya en ese paso). La cámara
        # sigue desde donde la dejó el `mover` anterior mientras ningún paso cambie la cámara pedida: ahí el viaje suave
        # solo gira (con otro acercamiento reabriría el encuadre o se acumularía de paso en paso)
        misma_camara = all(visual[k] == antes[k] for k in DE_LA_CAMARA)
        if otro or not misma_camara:
            zoom_fin = None
        quieta = (not otro or not escenas) and mover is None and misma_camara
        if quieta and not visual["girar"] and rec.inmersion_de(esc, g) is None:
            esc["mover"] = rec.mover_suave(len(suaves), None if zoom_fin is not None else
                                           visual["zoom"] or ZOOM_DE_CAMARA.get(visual["camara"], 1))
            suaves.add(n)
        if esc["mover"] and esc["mover"].get("zoom") is not None:
            zoom_fin = esc["mover"]["zoom"]
        segundos, tocado = _acotar(x.sostener, 0, rec.MAX_SOSTENER_MS / 1000, 3) if x.sostener is not None else (None, False)
        if x.sostener is not None and (segundos is None or tocado):
            avisar(f"sostener «{_ver(x.sostener)}» va de 0 a {rec.MAX_SOSTENER_MS // 1000} segundos: "
                   f"{'se ignoró' if segundos is None else f'quedó en {segundos:g}'}")
        esc["sostener_ms"] = int(round(segundos * 1000)) if segundos is not None else \
            rec.sostener_por_omision(esc, escenas[-1] if escenas else None, g)
        escenas.append(esc)
    if textos_malos:
        # Lo que se proyecta no se relaja: nada se guarda ni se muestra, y el error dice en qué paso
        partes_error = [f"{'Paso' if len(ns) == 1 else 'Pasos'} {', '.join(map(str, ns))}: {motivo}"
                        for motivo, ns in textos_malos.items()]
        raise ErrorHerramienta(" · ".join(partes_error[:3]) + " No se guardó ni se mostró nada: corrija ese texto y "
                               "mande el plan de nuevo.", "invalido", estado=422,
                               detalle={"pasos": sorted(n for ns in textos_malos.values() for n in ns)})
    return ({"id": secrets.token_hex(6), "titulo": a.titulo or g.capitulos[g.por_id(escenas[0]["capitulo"])]["nombre"],
             "escenas": escenas, "cierre": {"puntos": list(a.cierre.puntos)} if a.cierre else None}, avisos, suaves)


def _digitos(t: str) -> str:
    return re.sub(r"\D", "", t)


def _avisos(g: guion_presentacion.Guion, r: dict, suaves: set[int] | frozenset[int] = frozenset()) -> list[str]:
    """Lo que no impide el plan pero conviene corregir la próxima vez (no bloquea). `suaves`: los pasos que solo
    movieron la cámara por omisión (no mostraron nada nuevo)."""
    out = []
    usados = {e["capitulo"] for e in r["escenas"]}
    texto_guion = json.dumps([c for c in g.capitulos if c["id"] in usados], ensure_ascii=False)
    del_guion = {_digitos(m) for m in _NUMERO.findall(texto_guion)}
    for n, e in enumerate(r["escenas"], 1):
        narracion = " ".join(e["frases"])
        fuera = [m for m in _NUMERO.findall(narracion) if len(_digitos(m)) >= 2 and _digitos(m) not in del_guion]
        if fuera:
            out.append(f"Paso {n}: {', '.join(dict.fromkeys(fuera))} no está en el guion de lo que muestra: las cifras, "
                       "tal como las trae el guion")
        if len(narracion) > 200 or len(e["frases"]) > 2:
            out.append(f"Paso {n}: lo que dice es largo (mejor UNA frase por paso, y otro paso para la idea siguiente)")
    quieta = 1
    for n, (a, b) in enumerate(zip(r["escenas"], r["escenas"][1:]), 2):
        igual = all(a[k] == b[k] for k in ("capitulo", "paso", "panel", "visual")) and not b["resaltar"] and \
            not b["animar"] and not b.get("simular") and (b["mover"] is None or n in suaves)
        quieta = quieta + 1 if igual else 1
        if quieta == 3:
            out.append(f"Pasos {n - 2} a {n}: la pantalla no muestra nada nuevo en tres pasos seguidos (solo la cámara se "
                       "mueve un poco): cada paso debería mostrar algo de lo que dice")
    if len(r["escenas"]) >= 4 and not r["cierre"]:
        out.append("Un plan de 4 pasos o más sin cierre: dos o tres ideas que queden en la sala")
    return out


def _mover_notable(esc: dict) -> bool:
    """¿El `mover` de la escena es un viaje que se nota (no el suave por omisión)? Gira más que eso, cambia de
    elevación o se acerca o se aleja más de un 10 %."""
    m = esc.get("mover")
    if not m:
        return False
    desde = esc["visual"]["zoom"] or ZOOM_DE_CAMARA.get(esc["visual"]["camara"], 1)
    return abs(m.get("giro", 0)) > max(GIROS_SUAVES) or "elevacion" in m or \
        ("zoom" in m and abs(m["zoom"] / desde - 1) > 0.1)


def _hace(g: guion_presentacion.Guion, esc: dict, anterior: dict | None) -> list[str]:
    """Lo que hace una escena, de la lista fija `HACE` (los chips de la tarjeta del chat): lo que cambia sobre la
    anterior o, si cambia de paso, sobre lo que el paso trae."""
    otro = not anterior or (anterior["capitulo"], anterior["paso"]) != (esc["capitulo"], esc["paso"])
    v, a = esc["visual"], rec.VISUAL_INICIAL if otro else anterior["visual"]
    out = []
    if otro:
        out.append("paso")
    if any(v[k] != a[k] for k in ("camara", "rumbo", "elevacion", "zoom")):
        out.append("camara")
    if v["mirar"] and v["mirar"] != a["mirar"]:
        out.append("mirar")
    if _mover_notable(esc):
        out.append("mover")
    if v["enfoque"] and v["enfoque"] != a["enfoque"]:
        out.append("enfoque")
    if v["aislar"] and v["aislar"] != a["aislar"]:
        out.append("aislar")
    if (v["mostrar"] or v["ocultar"]) and (v["mostrar"], v["ocultar"]) != (a["mostrar"], a["ocultar"]):
        out.append("capas")
    if v["sin"] and v["sin"] != a["sin"]:
        out.append("partes")
    if v["detalle"] and v["detalle"] != a["detalle"]:
        out.append("ficha")
    if v["comparar"] != a["comparar"]:
        out.append(v["comparar"])
    if rec.abre_atlas(esc, anterior, g):
        out.append("modelo")
    if esc.get("animar"):
        out.append("animar")
    if esc.get("simular"):   # acciona controles del modelo a la vista (el sismo, el BIM…; o la hora, las luces de la maqueta)
        out.append("simular")
    if esc.get("gesto"):     # lo que hace el presentador (la caricatura que explica)
        out.append("gesto")
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


def _muestra(g: guion_presentacion.Guion, esc: dict, suave: bool = False, anterior: dict | None = None) -> str:
    """Lo que ve la sala en un paso del plan, para el modelo: «Salud · paso 3 de 10 (Una torre…) · vista oblicua · solo
    torre · sin torre.cubierta · la cámara gira 40°». Las piezas y las partes, con su id (como las pide el modelo). Con
    `anterior` (el paso del plan que va antes), si sigue en el mismo paso del capítulo no repite cuál es. `suave`: el
    movimiento de la cámara es el que se pone por omisión."""
    c = g.capitulos[g.por_id(esc["capitulo"])]
    v = esc["visual"]
    nombres = {x["id"]: x["nombre"] for x in c.get("componentes") or []}
    inm = {i["id"]: i.get("nombre") for i in g.inmersiones}
    mismo = bool(anterior) and (anterior["capitulo"], anterior["paso"]) == (esc["capitulo"], esc["paso"])
    partes = ["el mismo paso" if mismo else
              f"{c['nombre']} · paso {esc['paso']} de {len(c['pasos'])} ({c['pasos'][esc['paso'] - 1]['titulo']})"]
    if not esc["panel"]:
        partes.append("solo 3D")
    if v["camara"] != "paso":
        partes.append(NOMBRE_CAMARA[v["camara"]])
    if v["rumbo"] is not None:
        partes.append(f"rumbo {v['rumbo']}°")
    if v["elevacion"] is not None:
        partes.append(f"a {v['elevacion']}° sobre el horizonte")
    if v["zoom"] is not None:
        partes.append(f"zoom {v['zoom']:g}")
    if v["mirar"]:
        partes.append(f"la cámara apunta a {v['mirar']}")
    if v["girar"]:
        partes.append("girando")
    if v["enfoque"]:
        partes.append(f"cámara en {nombres.get(v['enfoque'], v['enfoque'])}")
    if v["aislar"]:
        partes.append(f"solo {v['aislar']}")
    if v["mostrar"]:
        partes.append(f"además {', '.join(v['mostrar'])}")
    if v["ocultar"]:
        partes.append(f"oculta {', '.join(v['ocultar'])}")
    if v["sin"]:
        partes.append(f"sin {', '.join(v['sin'])}")
    if v["detalle"]:
        partes.append(f"ficha de {nombres.get(v['detalle'], v['detalle'])}")
    if v["comparar"] == "hoy":
        partes.append("el sitio hoy")
    i = rec.inmersion_de(esc, g)
    if i:
        partes.append(f"modelo del atlas: {inm.get(i, i)}")
    if esc.get("mover"):
        partes.append("la cámara se mueve un poco sola" if suave else f"la cámara {_mover_dicho(esc['mover'])}")
    if esc.get("animar"):
        partes.append("anima la obra")
    if esc.get("simular"):
        partes.append(f"acciona: {_simular_dicho(g, rec.simulable_de(esc, g), esc['simular'], esc['capitulo'])}")
    if esc.get("gesto"):
        partes.append(f"el presentador: {esc['gesto']}")
    if esc["resaltar"]:
        r = esc["resaltar"]
        partes.append(f"resalta {r['tipo']} {r.get('n') or nombres.get(r.get('id'), r.get('id'))}")
    return " · ".join(partes)


DONDE_SUENA = {"vista": "la vista Presentación de la pestaña del chat (o el proyector, si hay uno abierto)",
               "pantalla_off": "la pantalla en off"}


async def _recorrido(db: Any, uid: int, g: guion_presentacion.Guion, a: PresentacionEntrada, por: str,
                     abierta: bool, doc: dict | None = None) -> Resultado:
    """La op `recorrido` (el plan guiado): lo compone de forma tolerante (`_componer`), lo valida entero, lo guarda y
    devuelve lo que el modelo necesita (compacto: lo que se ve en cada paso y los avisos de lo que se descartó) y, al
    asistente, las acciones (la de la presentación si suena en la pestaña o el proyector, y la de la tarjeta del chat,
    que es el plan a la vista). Por MCP hace falta una pantalla en off abierta: no hay otra pantalla donde suene. Si el
    nuevo va a la pantalla en off y en la pestaña o el proyector sonaba otro (`doc`, la pantalla antes de guardarlo),
    también lo detiene allá: si no, las dos voces se pisaban hasta su próximo avance, y uno en pausa no se enteraba nunca."""
    if por == "mcp" and not abierta:
        raise ErrorHerramienta("Abra la pantalla en off antes de un plan (la vista Presentación en modo en off, en el "
                               "proyector): por MCP no hay otra pantalla donde se vea y se oiga. ir y visual sí quedan "
                               "guardados.", "sin_pantalla", estado=409)
    r, descartado, suaves = _componer(g, a)
    problemas = rec.validar(r, g)
    if problemas:   # no debería: _componer deja solo lo que vale; si pasa, mejor no reproducir nada
        raise ErrorHerramienta("El plan no se puede reproducir: " + "; ".join(problemas[:4]), "invalido", estado=422)
    ms = rec.duracion_ms(r, g)
    if ms > rec.MAX_DURACION_MS:
        raise ErrorHerramienta(f"El plan dura unos {round(ms / 1000)} s y el tope es {rec.MAX_DURACION_MS // 1000}: "
                               "divídalo en dos (menos pasos o frases más cortas).", "invalido", estado=422)
    destino = "pantalla_off" if abierta or por == "mcp" else "vista"
    previo = pantalla_off.recorrido_de(doc, g)
    auto = pantalla_off.auto_de(doc, g)
    await run_in_threadpool(pantalla_off.guardar_recorrido, db, uid, r, destino, por)
    avisos = [*descartado, *_avisos(g, r, suaves)]
    minutos, segundos = divmod(round(ms / 1000), 60)
    dura = f"{minutos} min {segundos} s" if minutos else f"{segundos} s"
    contenido = {"plan": {"id": r["id"], "titulo": r["titulo"], "pasos": len(r["escenas"]),
                          "cierre": bool(r["cierre"]), "duracion_estimada_s": round(ms / 1000),
                          "se_reproduce_en": DONDE_SUENA[destino]},
                 "pasos": [{"n": n, "muestra": _muestra(g, e, n in suaves, r["escenas"][n - 2] if n > 1 else None)}
                           for n, e in enumerate(r["escenas"], 1)],
                 "nota": NOTA_RECORRIDO}
    if avisos:
        contenido["avisos"] = avisos[:MAX_AVISOS] + (
            [f"y {len(avisos) - MAX_AVISOS} avisos más"] if len(avisos) > MAX_AVISOS else [])
    if auto and auto["activa"]:
        c = g.capitulos[g.por_id(auto["capitulo"])]
        contenido["automatica"] = (
            "La presentación automática está encendida: este plan la interrumpe y, cuando termine, sigue sola en "
            f"{c['nombre']}, paso {auto['paso']} de {len(c['pasos'])}. No hace falta reiniciarla.")
    acciones: list[dict] = []
    if por == "asistente":
        if destino == "pantalla_off" and previo and not previo["cerrado"] and previo["destino"] == "vista":
            acciones.append({"tipo": "presentacion", "op": "control_recorrido", "rid": previo["id"], "accion": "detener",
                             "motivo": "otra_orden"})
        if destino == "vista":
            acciones.append({"tipo": "presentacion", "op": "recorrido", "recorrido": r})
        acciones.append(_tarjeta(g, r, destino, ms, list(a.sugerencias or [])))
    return Resultado(contenido, f"Plan «{r['titulo']}» · {len(r['escenas'])} pasos · ≈{dura}", acciones=acciones)


def _tarjeta(g: guion_presentacion.Guion, r: dict, destino: str, ms: int, sugerencias: list[str]) -> dict:
    """La acción de la tarjeta del plan en el chat (agente-recorrido.js): dónde, qué hace y qué dice cada paso, la
    duración, el cierre y las sugerencias. Sigue el avance del recorrido con este id."""
    return {"tipo": "recorrido", "id": r["id"], "titulo": r["titulo"], "destino": destino, "duracion_ms": ms,
            "cierre": r["cierre"]["puntos"] if r["cierre"] else None, "sugerencias": sugerencias,
            "escenas": [{"narracion": " ".join(e["frases"]), "donde": _donde(g, e),
                         "hace": _hace(g, e, r["escenas"][n - 1] if n else None)} for n, e in enumerate(r["escenas"])]}


async def _control_recorrido(db: Any, uid: int, g: guion_presentacion.Guion, a: PresentacionEntrada, por: str,
                             abierta: bool) -> Resultado:
    """La op `control_recorrido`: queda guardado (la pantalla en off lo aplica una vez) y, si el plan suena en la
    pestaña o el proyector, va como acción al navegador del asistente. «reproducir» lo vuelve a empezar con otro id: al
    asistente le vuelve también la tarjeta del nuevo (la del anterior sigue el avance de su id, y el nuevo quedaría sin
    avance, sin barra en el chat y sin pausa al escribir). Por MCP, uno que suena en la pestaña o el proyector del panel
    no se controla: solo la pantalla en off lee los controles guardados, y la pestaña no sabría nada. Con la
    presentación automática encendida, «detener» sobre otro plan no la apaga: el resultado lo dice (`automatica`), para
    que el modelo no le prometa silencio a la persona."""
    sin_recorrido = ErrorHerramienta("No hay un plan en curso: arme uno con la op recorrido.", "sin_recorrido",
                                     estado=409)
    if por == "mcp":
        actual = pantalla_off.recorrido_de(await run_in_threadpool(pantalla_off.leer, db, uid), g)
        if actual and actual["destino"] == "vista":
            if actual["cerrado"]:
                raise sin_recorrido
            raise ErrorHerramienta(
                f"El plan «{actual['titulo']}» suena en la pestaña del panel de la persona (o en su proyector), no "
                "en la pantalla en off: se controla desde ahí. Para manejar uno, arme otro con la pantalla en off "
                "abierta.", "en_el_panel", estado=409)
    try:
        res = await run_in_threadpool(pantalla_off.controlar, db, uid, g, a.accion, por)
    except ValueError:
        raise sin_recorrido from None
    r, doc = res["recorrido"], res["doc"]
    estado = pantalla_off.resumen_recorrido(doc, g) or {}
    acciones: list[dict] = []
    apagada = bool(r and r["auto"] and a.accion == "detener")   # era el plan de la presentación automática
    if por == "asistente" and r:
        if a.accion == "reproducir":
            if r["destino"] == "vista":
                acciones.append({"tipo": "presentacion", "op": "recorrido",
                                 "recorrido": {k: r[k] for k in ("id", "titulo", "escenas", "cierre")}})
            if not r["auto"]:   # el plan automático no tiene tarjeta en el chat
                acciones.append(_tarjeta(g, r, r["destino"], rec.duracion_ms(r, g), []))
        elif r["destino"] == "vista":
            acciones.append({"tipo": "presentacion", "op": "control_recorrido", "rid": r["id"], "accion": a.accion})
        if apagada:
            acciones.append({"tipo": "automatica", **pantalla_off.auto_para_persona(doc, g)})
    nombres = {"pausar": "Pausé", "continuar": "Seguí con", "siguiente": "Pasé al paso siguiente de",
               "anterior": "Volví al paso anterior de", "repetir": "Repetí el paso de", "reproducir": "Volví a empezar",
               "detener": "Detuve"}
    contenido = {"plan": {"id": estado.get("id"), "titulo": estado.get("titulo"), "paso": estado.get("escena"),
                          "de": estado.get("de"), "fase": estado.get("fase")}, "accion": a.accion,
                 "nota": "Se aplica en la pantalla donde suena el plan; el avance llega en estado y en el contexto."}
    if apagada:
        contenido["automatica"] = ("Era el plan de la presentación automática: quedó apagada. Vuelve con la op "
                                   "automatica (accion iniciar).")
    elif a.accion == "detener" and (pantalla_off.auto_de(doc, g) or {}).get("activa"):
        # detuvo un plan suyo (o del panel) con la automática encendida: la sala la volverá a oír sola
        x = pantalla_off.auto_para_persona(doc, g)
        cuando = "en unos segundos retoma sola" if abierta else "retoma sola cuando se abra una pantalla en off,"
        contenido["automatica"] = (f"La presentación automática sigue encendida: {cuando} en {x['nombre']}, paso "
                                   f"{x['paso']} de {x['de']}. Si la persona quiere silencio, apáguela con op "
                                   "automatica (accion detener).")
    return Resultado(contenido, f"{nombres[a.accion]} el plan «{(r or {}).get('titulo', '')}»", acciones=acciones)


NOTA_AUTOMATICA = (
    "La pantalla en off recorre sola toda la presentación: un plan por capítulo, con una frase muy resumida por paso "
    "(sale del guion: no la escribe usted), y al terminar la vuelta vuelve a empezar. No la narre ni la repita en el "
    "chat: diga en una línea que ya empezó. Si la persona pregunta algo, respóndale con un plan CORTO (recorrido de 3 a "
    "5 pasos): la interrumpe y, cuando termina, sigue sola desde el paso donde iba. Se apaga con accion detener.")
NOTA_AUTOMATICA_SIN_PANTALLA = (
    "Quedó encendida, pero no hay ninguna pantalla en off abierta: empieza sola cuando la persona abra la vista "
    "Presentación en modo en off (botón «Pantalla en off» de la vista, en el proyector o en otra pantalla). La "
    "presentación automática solo corre en la pantalla en off.")
NOTA_AUTOMATICA_APAGADA = ("La presentación automática quedó apagada: la pantalla se queda en el paso donde iba. Vuelve "
                           "con accion iniciar (desde el comienzo, o desde un capitulo).")


async def _automatica(db: Any, uid: int, g: guion_presentacion.Guion, a: PresentacionEntrada, por: str,
                      abierta: bool, doc: dict | None) -> Resultado:
    """La op `automatica`: enciende la presentación automática (desde el primer paso del capítulo que se diga o, sin
    capítulo, desde la portada) o la apaga (`app/pantalla.py`, `app/automatica.py`). La narra la pantalla en off, con
    planes que arma el servidor desde el guion: aquí no se escribe nada para la sala. Devuelve el estado y una nota y,
    al asistente, la acción para el chat ({tipo: automatica, activa, capitulo, nombre, paso, de}); si al encenderla
    con una pantalla abierta sonaba un plan en la pestaña o el proyector (`doc`, la pantalla antes), lo detiene allá."""
    acciones: list[dict] = []
    if a.accion == "iniciar":
        ci = _resolver_capitulo(g, a.capitulo) if a.capitulo else 0
        previo = pantalla_off.recorrido_de(doc, g)
        nuevo = await run_in_threadpool(pantalla_off.iniciar_auto, db, uid, g, por, ci)
        if por == "asistente" and abierta and previo and not previo["cerrado"] and previo["destino"] == "vista":
            acciones.append({"tipo": "presentacion", "op": "control_recorrido", "rid": previo["id"], "accion": "detener",
                             "motivo": "otra_orden"})
    else:
        if a.capitulo is not None:
            raise ErrorHerramienta("Para detener la presentación automática no va capitulo.", "invalido", estado=422)
        nuevo = await run_in_threadpool(pantalla_off.detener_auto, db, uid, g, por)
    x = pantalla_off.auto_para_persona(nuevo, g)
    estaba = bool((pantalla_off.auto_de(doc, g) or {}).get("activa"))
    contenido: dict[str, Any] = {"automatica": x, "pantalla_en_off_abierta": abierta}
    if a.accion == "iniciar":
        minutos = max(1, round(automatica.duracion_de_la_vuelta_ms(g) / 60000))
        contenido["recorre"] = {"capitulos": len(g), "pasos": g.total_pasos(), "vuelta_completa_min": minutos}
        contenido["nota"] = NOTA_AUTOMATICA if abierta else NOTA_AUTOMATICA_SIN_PANTALLA
        resumen = f"Presentación automática encendida · empieza en {x['nombre']}"
    else:
        contenido["nota"] = NOTA_AUTOMATICA_APAGADA if estaba else "La presentación automática no estaba encendida."
        resumen = "Presentación automática apagada"
    if por == "asistente":
        acciones.append({"tipo": "automatica", **x})
    return Resultado(contenido, resumen, acciones=acciones)


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
    "Presenta la propuesta Yondó 2028–2031 en su versión técnica (lo que se construye, sin costos, en la maqueta 3D "
    "y los modelos del atlas) en el panel de la persona o en su pantalla en off. PARA EXPLICAR, PRIMERO UN PLAN: guion "
    "(datos de un capítulo) y luego recorrido, en UNA llamada: titulo, pasos (de 6 a 10, hasta 12) "
    "y cierre {puntos}. Cada paso: dice (UNA frase de hasta 220 caracteres, proyectada y leída en voz "
    "alta) y lo que ocurre MIENTRAS se dice: capitulo, paso, la cámara (camara, rumbo, elevacion, zoom, mirar, mover "
    "{giro, zoom, elevacion}), las piezas (aislar, mostrar, ocultar, sin «pieza.parte»), enfoque, detalle, comparar, "
    "inmersion y simular [{control, valor}] (el sismo o la hora de la maqueta), animar, resaltar, gesto; lo demás sigue. La "
    "pantalla lo ejecuta sola; lo que no exista se descarta con aviso. Ejemplo de pasos: [{\"capitulo\":"
    "\"salud\",\"paso\":\"torre\",\"camara\":\"oblicua\",\"mover\":{\"giro\":40},\"dice\":\"…\"},{\"aislar\":\"torre\","
    "\"sin\":[\"torre.cubierta\"],\"dice\":\"…\"}]. control_recorrido lo pausa, salta o detiene. automatica (accion "
    "iniciar o detener): la pantalla en off recorre sola toda la presentación, muy resumida; un plan corto la "
    "interrumpe y luego sigue. Pedidos puntuales: indice, estado, pantalla_completa y, deteniendo el plan, ir "
    "(dice lo que muestra); siguiente/anterior; explicar y quitar_explicacion; vista (panel, indice, fichas); "
    "visual (lo de un paso, simular y tema). La sala lo ve: nunca datos de habitantes, costos, «@» ni números de 7 o más "
    "dígitos.")

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
