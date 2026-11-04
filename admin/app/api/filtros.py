"""Filtros comunes del directorio, el mapa, la exportación y el tablero (mismos parámetros en todos), traducidos a
MongoDB, y el alcance de cada usuario.

* `filtros_query` lee los parámetros y resuelve `area_id` (404 si no existe); deja en el objeto lo que `filtro()`
  necesita de la base (la geometría del área y los ajustes), así `filtro()` no consulta la base.
* `consulta(db, quien, f)` es lo que usan las rutas abiertas a P y C: rechaza los parámetros vedados (403 `permiso`),
  exige que el área esté asignada y suma el alcance obligatorio (3.6).
* `alcance_de(db, quien)`: personas de los lugares y áreas asignados a un planillero o consultor; None si no tiene
  asignación (toda la base, con el presupuesto diario).
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, PrivateAttr
from pymongo.database import Database

from .. import geometria, modelo, proyeccion
from ..db import ACTIVA
from ..pipeline import texto as tx
from ..seguridad import obtener_db

APROXIMADAS = ["barrio", "sector", "caserio", "centro_poblado", "vereda", "corregimiento", "direccion_aprox"]
SIN_CAMPOS = ("cedula", "telefono", "sexo", "edad", "lugar", "puesto", "mesa", "direccion")
# Parámetros que P y C no pueden usar (3.6): darían listas políticas, de menores o de la actividad de otros
VEDADOS = ("poligono", "ids", "lista", "lider", "creado_por", "actualizado_por", "menor")
PERMISO = {"mensaje": "Su rol no permite usar este filtro", "codigo": "permiso"}


class Filtros(BaseModel):
    q: str | None = None
    zona: str | None = None
    lugar_id: int | None = None
    fuente: str | None = None
    lista: str | None = None
    etiqueta: int | None = None
    con_cedula: int | None = None
    con_telefono: int | None = None
    precision: str | None = None
    reunion_id: int | None = None
    asistio: int | None = None
    consentimiento: str | None = None
    lider: int | None = None
    sexo: str | None = None
    completitud_max: int | None = None
    ids: str | None = None
    # 8.3
    edad_min: int | None = None
    edad_max: int | None = None
    tipo_documento: str | None = None
    cedula_verificada: int | None = None
    puesto_id: int | None = None
    con_puesto: int | None = None
    con_mesa: int | None = None
    votacion_estado: str | None = None
    donde: str | None = None
    abordado: int | None = None
    contactado: int | None = None
    abordaje_estado: str | None = None
    ultimo_resultado: str | None = None
    sin_acercamiento_dias: int | None = None
    proximo_vencido: int | None = None
    canal_autorizado: str | None = None
    situacion: str | None = None
    creado_por: int | None = None
    actualizado_por: int | None = None
    menor: int | None = None
    requiere_actualizacion: str | None = None
    varios_telefonos: int | None = None
    telefono_estado: str | None = None
    estado_civil: str | None = None
    nivel_educativo: str | None = None
    situacion_laboral: str | None = None
    estrato: int | None = None
    tenencia_vivienda: str | None = None
    regimen_salud: str | None = None
    sin_cedula: int | None = None
    sin_telefono: int | None = None
    sin_sexo: int | None = None
    sin_edad: int | None = None
    sin_lugar: int | None = None
    sin_puesto: int | None = None
    sin_mesa: int | None = None
    sin_direccion: int | None = None
    sin_puesto_mesa: int | None = None
    tratables: int | None = None
    mios: int | None = None
    poligono: str | None = None
    area_id: int | None = None
    # Lo que `filtros_query` resuelve de la base: no sale en model_dump (ni en la auditoría de la exportación)
    _area: dict | None = PrivateAttr(default=None)
    _area_asignada_a: list = PrivateAttr(default_factory=list)
    _eleccion: str | None = PrivateAttr(default=modelo.AJUSTES_POR_DEFECTO["eleccion_vigente"])
    _dias_dato: int = PrivateAttr(default=modelo.AJUSTES_POR_DEFECTO["dias_reintento_dato"])
    _uid: int | None = PrivateAttr(default=None)


def geometria_de_area(a: dict | None) -> dict | None:
    """GeoJSON del polígono de un área guardada (como anillo [[lon, lat], …] o ya como GeoJSON)."""
    pol = (a or {}).get("poligono")
    if isinstance(pol, dict) and pol.get("type") in ("Polygon", "MultiPolygon"):
        return pol
    if isinstance(pol, list) and len(pol) >= 3:
        return geometria.a_geojson(pol)
    return None


def preparar(db: Database, f: Filtros) -> Filtros:
    """Resuelve en `f` lo que `filtro()` necesita de la base: el área (404 si no existe) y los ajustes."""
    aj = modelo.leer_ajustes(db)
    f._eleccion = aj.get("eleccion_vigente")
    f._dias_dato = int(aj.get("dias_reintento_dato") or modelo.AJUSTES_POR_DEFECTO["dias_reintento_dato"])
    if f.area_id is not None:
        a = db.areas.find_one({"_id": f.area_id}, {"poligono": 1, "asignada_a": 1})
        if a is None:
            raise HTTPException(404, "El área no existe")
        f._area = geometria_de_area(a) or {"type": "Polygon", "coordinates": [[]]}
        f._area_asignada_a = list(a.get("asignada_a") or [])
    return f


def filtros_query(
    q: str | None = Query(None, max_length=120), zona: str | None = None, lugar_id: int | None = None,
    fuente: str | None = None, lista: str | None = Query(None, max_length=120), etiqueta: int | None = None,
    con_cedula: int | None = None, con_telefono: int | None = None, precision: str | None = None,
    reunion_id: int | None = None, asistio: int | None = None, consentimiento: str | None = None,
    lider: int | None = None, sexo: str | None = None, completitud_max: int | None = None,
    ids: str | None = Query(None, max_length=4000),
    edad_min: int | None = Query(None, ge=0, le=130), edad_max: int | None = Query(None, ge=0, le=130),
    tipo_documento: str | None = None, cedula_verificada: int | None = None, puesto_id: int | None = None,
    con_puesto: int | None = None, con_mesa: int | None = None, votacion_estado: str | None = None,
    donde: str | None = None, abordado: int | None = None, contactado: int | None = None,
    abordaje_estado: str | None = None, ultimo_resultado: str | None = None,
    sin_acercamiento_dias: int | None = Query(None, ge=0, le=3650), proximo_vencido: int | None = None,
    canal_autorizado: str | None = None, situacion: str | None = None, creado_por: int | None = None,
    actualizado_por: int | None = None, menor: int | None = None,
    requiere_actualizacion: str | None = Query(None, max_length=120), varios_telefonos: int | None = None,
    telefono_estado: str | None = None, estado_civil: str | None = Query(None, max_length=60),
    nivel_educativo: str | None = Query(None, max_length=60), situacion_laboral: str | None = Query(None, max_length=60),
    estrato: int | None = None, tenencia_vivienda: str | None = Query(None, max_length=60),
    regimen_salud: str | None = Query(None, max_length=60), sin_cedula: int | None = None,
    sin_telefono: int | None = None, sin_sexo: int | None = None, sin_edad: int | None = None,
    sin_lugar: int | None = None, sin_puesto: int | None = None, sin_mesa: int | None = None,
    sin_direccion: int | None = None, sin_puesto_mesa: int | None = None, tratables: int | None = None,
    mios: int | None = None,
    poligono: str | None = Query(None, max_length=4000), area_id: int | None = None,
    db: Database = Depends(obtener_db),
) -> Filtros:
    datos = {k: v for k, v in locals().items() if k != "db"}
    return preparar(db, Filtros(**datos))


# ───────────────────────────── Traducción a MongoDB ─────────────────────────────

def _restar_anios(d: date, n: int) -> date:
    try:
        return d.replace(year=d.year - n)
    except ValueError:  # 29 de febrero
        return d.replace(year=d.year - n, day=28)


def _vacio(campo: str) -> dict:
    return {campo: {"$in": [None, ""]}}


def _lleno(campo: str) -> dict:
    return {campo: {"$nin": [None, ""]}}


CON_PUESTO = {"$or": [{"votacion.puesto_id": {"$ne": None}}, _lleno("votacion.puesto_texto"),
                      {"votacion.donde": {"$in": ["otro_municipio", "no_inscrito"]}},
                      {"votacion": None, "puesto_votacion": {"$nin": [None, ""]}}]}
CON_MESA = {"$or": [{"votacion.mesa": {"$ne": None}}, {"votacion": None, "mesa": {"$nin": [None, ""]}}]}
CON_EDAD = {"$or": [{"edad": {"$ne": None}}, {"nac_aprox": {"$ne": None}}]}


def _sin(campo: str) -> dict:
    """Sin el dato (la misma regla que `modelo.tiene_dato`, en consulta)."""
    if campo == "cedula":
        return _vacio("cedula")
    if campo == "telefono":
        return {"telefono": None}
    if campo == "sexo":
        return _vacio("sexo")
    if campo == "edad":
        return {"$nor": [CON_EDAD]}
    if campo == "lugar":
        return {"lugar_id": None}
    if campo == "puesto":
        return {"$nor": [CON_PUESTO]}
    if campo == "mesa":
        return {"$nor": [CON_MESA]}
    if campo == "direccion":
        return _vacio("direccion")
    raise ValueError(campo)


def no_disponible_vencido(campo: str, hoy: date, dias: int) -> dict:
    """El campo no está marcado «No lo tiene / No sabe», o la marca tiene `dias` o más (se vuelve a pedir)."""
    limite = datetime.combine(hoy - timedelta(days=dias - 1), datetime.min.time(), modelo.ZONA)
    return {"$or": [{f"no_disponible.{campo}": None},
                    {f"no_disponible.{campo}.ts": {"$lt": limite.astimezone(timezone.utc).isoformat()}}]}


def falta(campo: str, hoy: date | None = None, dias: int = modelo.AJUSTES_POR_DEFECTO["dias_reintento_dato"]) -> dict:
    """Le falta el dato y no está marcado como no disponible (vigente)."""
    y = [_sin(campo)]
    if campo in modelo.CAMPOS_NO_DISPONIBLE:
        y.append(no_disponible_vencido(campo, hoy or modelo.hoy_local(), dias))
    return {"$and": y}


def filtro_situacion(valor: str | None) -> dict | None:
    if valor in (None, "", "todas"):
        return None
    if valor == "vigentes":
        return {"situacion.estado": {"$in": [None, "activa"]}}
    if valor == "no_vigentes":
        return {"situacion.estado": {"$in": ["fallecida", "no_reside"]}}
    if valor in modelo.SITUACIONES:
        return {"situacion.estado": valor} if valor != "activa" else {"situacion.estado": {"$in": [None, "activa"]}}
    raise HTTPException(422, "Situación desconocida")


def _sino(v: int | None, si: dict, no: dict) -> dict | None:
    if v is None:
        return None
    return si if v else no


def filtro(f: Filtros, hoy: date | None = None) -> dict:
    """Documento de consulta de MongoDB para los filtros dados (solo personas activas). No consulta la base."""
    hoy = hoy or modelo.hoy_local()
    y: list[dict] = [dict(ACTIVA)]
    if f.q:
        for tok in tx.limpiar(f.q).split()[:6]:
            digitos = re.sub(r"\D", "", tok)
            if digitos and len(digitos) >= 4 and digitos == tok:
                rx = re.escape(digitos)
                y.append({"$or": [{"cedula": {"$regex": "^" + rx}}, {"telefonos.numero": {"$regex": rx}},
                                  {"telefono": {"$regex": rx}}, {"telefono2": {"$regex": rx}}, {"ficha": {"$regex": rx}}]})
            else:
                limpio = re.sub(r"[^A-Z0-9@.]", "", tok)
                if not limpio:
                    continue
                rx = re.escape(limpio)
                y.append({"$or": [{"nombre_norm": {"$regex": rx}}, {"direccion_norm": {"$regex": rx}},
                                  {"lugar_texto": {"$regex": rx}}, {"correo": {"$regex": rx, "$options": "i"}}]})
    if f.zona in ("urbana", "rural"):
        y.append({"zona": f.zona})
    elif f.zona == "sin":
        y.append({"zona": None})
    if f.lugar_id is not None:  # 0 = sin barrio ni vereda reconocidos
        y.append({"lugar_id": f.lugar_id or None})
    if f.fuente == "ambas":
        y.append({"fuentes": {"$all": ["tramites", "cedulas"]}})
    elif f.fuente in ("tramites", "cedulas", "reunion", "manual", "planilla"):
        y.append({"fuentes": f.fuente})
    if f.lista:
        y.append({"listas": f.lista})
    if f.etiqueta:
        y.append({"etiquetas": f.etiqueta})
    if f.con_cedula is not None:
        y.append(_lleno("cedula") if f.con_cedula else _vacio("cedula"))
    if f.con_telefono is not None:
        y.append({"telefono": {"$ne": None}} if f.con_telefono else {"telefono": None})
    if f.precision == "exacta":
        y.append({"geo_precision": {"$in": ["direccion", "manual"]}})
    elif f.precision == "aproximada":
        y.append({"geo_precision": {"$in": APROXIMADAS}})
    elif f.precision == "ubicada":  # cualquier coordenada: lo que se ve en el mapa
        y.append({"lat": {"$ne": None}})
    elif f.precision == "sin":
        y.append({"lat": None})
    if f.reunion_id:
        y.append({"asistencias.reunion_id": f.reunion_id})
    if f.asistio is not None:
        y.append({"asistencias.0": {"$exists": bool(f.asistio)}})
    if f.consentimiento in ("si", "no", "pendiente"):
        y.append({"consentimiento": f.consentimiento})
    elif f.consentimiento == "por_confirmar":  # «sí» declarado en planilla que A todavía no confirma
        y.append({"consentimiento": "si", "contacto_habilitado": {"$ne": True}})
    if f.tratables:
        y.append({"consentimiento": {"$ne": "no"}})
    if f.lider:
        y.append({"lider": True})
    if f.sexo in modelo.SEXOS:
        y.append({"sexo": f.sexo})
    elif f.sexo == "sin":
        y.append(_vacio("sexo"))
    if f.ids:
        y.append({"_id": {"$in": [int(x) for x in re.findall(r"\d+", f.ids)[:500]]}})
    if f.completitud_max is not None:
        y.append({"completitud": {"$lte": f.completitud_max}})
    # Edad: rango de la fecha de nacimiento (exacta con la fecha; con la edad declarada, ±1 año)
    if f.edad_min is not None:
        y.append({"nac_aprox": {"$ne": None, "$lte": _restar_anios(hoy, f.edad_min).isoformat()}})
    if f.edad_max is not None:
        y.append({"nac_aprox": {"$ne": None, "$gt": _restar_anios(hoy, f.edad_max + 1).isoformat()}})
    if f.tipo_documento in modelo.TIPOS_DOCUMENTO:
        y.append({"tipo_documento": f.tipo_documento})
    if f.cedula_verificada is not None:
        y.append({"cedula_verificada": True} if f.cedula_verificada else {"cedula_verificada": {"$ne": True}})
    if f.puesto_id is not None:
        y.append({"votacion.puesto_id": f.puesto_id or None})
    for cond in (_sino(f.con_puesto, CON_PUESTO, {"$nor": [CON_PUESTO]}), _sino(f.con_mesa, CON_MESA, {"$nor": [CON_MESA]})):
        if cond:
            y.append(cond)
    if f.votacion_estado:
        if f.votacion_estado not in modelo.ESTADOS_VOTACION:
            raise HTTPException(422, "Estado de votación desconocido")
        y.append(modelo.filtro_estado_votacion(f.votacion_estado, f._eleccion))
    if f.donde in modelo.DONDE_VOTA:
        y.append({"votacion.donde": f.donde})
    if f.abordado is not None:
        y.append({"abordaje.n": {"$gte": 1}} if f.abordado else {"$nor": [{"abordaje.n": {"$gte": 1}}]})
    if f.contactado is not None:
        y.append({"abordaje.efectivos": {"$gte": 1}} if f.contactado else {"$nor": [{"abordaje.efectivos": {"$gte": 1}}]})
    if f.abordaje_estado == "sin_abordar":
        y.append({"abordaje.estado": None})
    elif f.abordaje_estado in modelo.ESTADOS_ABORDAJE:
        y.append({"abordaje.estado": f.abordaje_estado})
    if f.ultimo_resultado in modelo.RESULTADOS:
        y.append({"abordaje.ultimo_resultado": f.ultimo_resultado})
    if f.sin_acercamiento_dias is not None:
        limite = (hoy - timedelta(days=f.sin_acercamiento_dias)).isoformat()
        y.append({"$or": [{"abordaje.ultimo_fecha": None}, {"abordaje.ultimo_fecha": {"$lt": limite}}]})
    if f.proximo_vencido:
        y.append({"abordaje.proximo": {"$ne": None, "$lte": hoy.isoformat()}})
    if f.canal_autorizado in modelo.CANALES_AUTORIZACION:
        o = [{"consentimiento": "si", "consentimiento_canales": f.canal_autorizado}]
        if f.canal_autorizado in modelo.CANALES_IMPLICITOS:  # «sí» anterior a los canales: valen los implícitos
            o.append({"consentimiento": "si", "consentimiento_canales": {"$exists": False}})
        y.append({"$or": o})
    sit = filtro_situacion(f.situacion)
    if sit:
        y.append(sit)
    if f.creado_por is not None:
        y.append({"creado_por.uid": f.creado_por})
    if f.actualizado_por is not None:
        y.append({"actualizado_por.uid": f.actualizado_por})
    if f.menor is not None:
        y.append(modelo.filtro_menor(hoy) if f.menor else {"$nor": [modelo.filtro_menor(hoy)]})
    if f.requiere_actualizacion not in (None, ""):
        v = f.requiere_actualizacion
        if v == "1":
            y.append({"requiere_actualizacion": {"$ne": None}})
        elif v == "0":
            y.append({"requiere_actualizacion": None})
        else:
            motivos = [m for m in v.split(",") if m in modelo.MOTIVOS_ACTUALIZACION]
            y.append({"requiere_actualizacion.motivo": {"$in": motivos}})
    if f.varios_telefonos is not None:
        y.append({"telefono2": {"$ne": None}} if f.varios_telefonos else {"telefono2": None})
    if f.telefono_estado in modelo.ESTADOS_TELEFONO:
        y.append({"telefonos.estado": f.telefono_estado})
    for campo in ("estado_civil", "nivel_educativo", "situacion_laboral", "tenencia_vivienda", "regimen_salud"):
        v = getattr(f, campo)
        if v == "sin":
            y.append(_vacio(campo))
        elif v:
            y.append({campo: v})
    if f.estrato is not None:
        y.append({"estrato": f.estrato})
    for campo in SIN_CAMPOS:
        if getattr(f, f"sin_{campo}"):
            y.append(falta(campo, hoy, f._dias_dato))
    if f.sin_puesto_mesa:  # «Sin puesto o mesa» de Mi trabajo
        y.append({"$or": [falta("puesto", hoy, f._dias_dato), falta("mesa", hoy, f._dias_dato)]})
    if f.mios and f._uid is not None:
        y.append({"$or": [{"creado_por.uid": f._uid}, {"actualizado_por.uid": f._uid}]})
    if f.poligono:
        anillo = geometria.validar_anillo(geometria.decodificar(f.poligono))
        y.append({"punto": {"$geoWithin": {"$geometry": geometria.a_geojson(anillo)}}})
    if f.area_id is not None:
        y.append({"punto": {"$geoWithin": {"$geometry": f._area}}} if f._area else {"_id": {"$in": []}})
    return {"$and": y}


# ───────────────────────────── Alcance y permisos de P y C ─────────────────────────────

def _prohibido(mensaje: str | None = None) -> HTTPException:
    return HTTPException(403, {**PERMISO, **({"mensaje": mensaje} if mensaje else {})})


def asignacion_de(quien: Any) -> dict:
    a = getattr(quien, "asignacion", None) or {}
    return {"lugares": [x for x in a.get("lugares") or [] if isinstance(x, int)],
            "areas": [x for x in a.get("areas") or [] if isinstance(x, int)]}


def alcance_de(db: Database, quien: Any) -> dict | None:
    """Personas dentro de la asignación de un planillero o consultor: las de sus barrios o veredas (cubren a quien no
    tiene coordenadas) y las que caen en sus áreas. None para A y K o para quien no tiene asignación (toda la base, con
    el presupuesto). Una asignación cuyas áreas ya no existen no da acceso a nada."""
    if proyeccion.administra(quien):
        return None
    a = asignacion_de(quien)
    if not a["lugares"] and not a["areas"]:
        return None
    o: list[dict] = []
    if a["lugares"]:
        o.append({"lugar_id": {"$in": a["lugares"]}})
    for area in db.areas.find({"_id": {"$in": a["areas"]}}, {"poligono": 1}) if a["areas"] else []:
        g = geometria_de_area(area)
        if g:
            o.append({"punto": {"$geoWithin": {"$geometry": g}}})
    return {"$or": o} if o else {"_id": {"$in": []}}


def exigir_permitidos(db: Database, quien: Any, f: Filtros) -> None:
    """403 `permiso` si P o C usan un parámetro vedado (3.6) o un área que no tienen asignada."""
    if proyeccion.administra(quien):
        return
    for p in VEDADOS:
        v = getattr(f, p)
        if v is not None and v != "":
            raise _prohibido(f"Su rol no permite filtrar por «{p}»")
    if f.fuente in ("cedulas", "ambas"):
        raise _prohibido("Su rol no permite filtrar por esa fuente")
    if f.etiqueta and f.etiqueta in proyeccion.etiquetas_sensibles(db):
        raise _prohibido("Su rol no permite filtrar por esa etiqueta")
    if f.area_id is not None and f.area_id not in asignacion_de(quien)["areas"] \
            and getattr(quien, "uid", None) not in f._area_asignada_a:
        raise _prohibido("Esa área no le está asignada")


def consulta(db: Database, quien: Any, f: Filtros, con_alcance: bool = True, hoy: date | None = None) -> dict:
    """La consulta de una ruta abierta a P y C: parámetros permitidos, filtros y, si se pide, el alcance."""
    exigir_permitidos(db, quien, f)
    f._uid = getattr(quien, "uid", None)
    q = filtro(f, hoy)
    alcance = alcance_de(db, quien) if con_alcance else None
    return {"$and": [q, alcance]} if alcance else q


def en_alcance(db: Database, quien: Any, pid: int) -> bool:
    alcance = alcance_de(db, quien)
    if alcance is None:
        return True
    return db.personas.count_documents({"$and": [{"_id": pid}, alcance]}, limit=1) > 0


def en_alcance_consultor(db: Database, p: dict, quien: Any) -> bool:
    """¿El consultor puede trabajar con esta persona? Sí si la tiene tomada (y no venció) o si le hizo un
    acercamiento propio, no anulado, en los últimos 30 días. A y K siempre; P no usa esta regla."""
    if proyeccion.administra(quien) or getattr(quien, "rol", None) != "consultor":
        return True
    ec = p.get("en_curso") if isinstance(p.get("en_curso"), dict) else None
    ahora = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    if ec and ec.get("uid") == quien.uid and str(ec.get("hasta") or "") > ahora:
        return True
    desde = (datetime.now(timezone.utc) - timedelta(days=30)).replace(microsecond=0).isoformat()
    return db.acercamientos.count_documents({"persona_id": p.get("_id", p.get("id")), "uid": quien.uid,
                                             "anulado": {"$ne": True}, "ts": {"$gte": desde}}, limit=1) > 0


def exigir_alcance_consultor(db: Database, p: dict, quien: Any) -> None:
    if not en_alcance_consultor(db, p, quien):
        raise _prohibido("Esta persona no está en su trabajo. Tómela desde la cola o el buscador.")


# ───────────────────────────── Base de la cola del consultor (4.5) ─────────────────────────────

def ahora_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def libre_para(uid: int | None) -> dict:
    """Sin un `en_curso` vigente de otro usuario."""
    return {"$or": [{"en_curso": None}, {"en_curso.uid": uid}, {"en_curso.hasta": {"$lte": ahora_iso()}}]}


def base_cola(db: Database, quien: Any, hoy: date | None = None, ajustes: dict | None = None,
              con_alcance: bool = True) -> dict:
    """`BASE_COLA` (4.5): la usan todas las listas del consultor, `siguiente` y `tomar`. Gemela de
    `proyeccion.motivo_no_contactable` más el teléfono, el alcance y `en_curso`."""
    hoy = hoy or modelo.hoy_local()
    aj = ajustes or modelo.leer_ajustes(db)
    tel = list(proyeccion.CANALES_TELEFONO)
    autorizada = {"consentimiento": "si", "contacto_habilitado": True, "consentimiento_canales": {"$in": tel}}
    o = [autorizada]
    if aj.get("contactar_pendientes"):
        # Para pedirle la autorización; nunca a quien solo viene de la base de trámites (Ley 1581, art. 4 b)
        o.append({"consentimiento": "pendiente", "fuentes": {"$elemMatch": {"$ne": "tramites"}}})
    y = [modelo.filtro_vigente(), {"telefono": {"$ne": None}}, {"$or": o}, {"reclamo_en_tramite": {"$ne": True}},
         modelo.filtro_adulto_conocido(hoy), {"abordaje.estado": {"$ne": "no_contactar"}},
         libre_para(getattr(quien, "uid", None))]
    if con_alcance:
        alcance = alcance_de(db, quien)
        if alcance:
            y.append(alcance)
    return {"$and": y}
