"""Filtros comunes del directorio, el mapa, la exportación y el tablero (mismos parámetros en todos), traducidos a
MongoDB, y el alcance de cada usuario.

* `filtros_query` lee los parámetros y resuelve `area_id` (404 si no existe); deja en el objeto lo que `filtro()`
  necesita de la base (la geometría del área y los ajustes), así `filtro()` no consulta la base.
* `consulta(db, quien, f)` es lo que usan las rutas abiertas a P y C: rechaza los parámetros vedados (403 `permiso`),
  exige que el área esté asignada, suma el alcance obligatorio (3.6) y hace que `filtro()` mire solo lo que el rol ve
  (ningún filtro, ni la búsqueda, ni el total, sirve de oráculo de un dato oculto).
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
    _eleccion: str | None = PrivateAttr(default=modelo.AJUSTES_POR_DEFECTO["eleccion_vigente"])
    _dias_dato: int = PrivateAttr(default=modelo.AJUSTES_POR_DEFECTO["dias_reintento_dato"])
    _uid: int | None = PrivateAttr(default=None)
    # Rol sin acceso completo (P o C): la búsqueda y los filtros solo miran lo que su proyección muestra
    _rol: str | None = PrivateAttr(default=None)


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
        a = db.areas.find_one({"_id": f.area_id}, {"poligono": 1})
        if a is None:
            raise HTTPException(404, "El área no existe")
        f._area = geometria_de_area(a) or {"type": "Polygon", "coordinates": [[]]}
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


# ───────────────────────────── Lo que P y C no ven (3.8) ─────────────────────────────
# Para un rol sin acceso completo, la búsqueda y los filtros solo coinciden con lo que su proyección ya muestra: una
# condición sobre un dato oculto nunca incluye a esa persona (ni en las filas ni en el total). Si no, la pertenencia
# al resultado serviría de oráculo y reconstruiría el dato dígito a dígito.
# * De quien no autorizó, P y C ven nombre, `cedula_ult3`, lugar, autorización y el estado del abordaje.
# * De un menor, P ve todo menos los teléfonos.
TRATABLE = {"consentimiento": {"$ne": "no"}}
# Filtros sobre lo que se ve en la fila de quien no autorizó (`proyeccion.CAMPOS_NO_AUTORIZO`), más el área asignada:
# es su alcance (que ya la incluye por su punto) y P no dibuja polígonos, así que no afina ninguna ubicación
VISIBLES_NO_AUTORIZO = frozenset({"q", "lugar_id", "consentimiento", "tratables", "abordaje_estado", "con_cedula",
                                  "area_id"})
FILTROS_TELEFONO = frozenset({"con_telefono", "sin_telefono", "varios_telefonos", "telefono_estado"})


def rol_restringido(quien: Any) -> str | None:
    """None si `quien` ve todo (A y K); si no, su rol de proyección («planillero» o «consultor»)."""
    return None if proyeccion.administra(quien) else proyeccion.rol_de(quien)


def telefonos_ocultos(hoy: date | None = None) -> dict:
    """Personas cuyos teléfonos P no ve: quien no autorizó y los menores."""
    return {"$or": [{"consentimiento": "no"}, modelo.filtro_menor(hoy)]}


def expr_completitud_vista(hoy: date | None = None) -> dict:
    """Expresión (agregación o `$expr`) de la completitud que ven P y C: la de un menor, sin su teléfono. Gemela de
    `proyeccion.completitud_vista`; la usan el orden por completitud y `completitud_max`, así ni el lugar en la lista
    ni el filtro dicen si un menor tiene teléfono."""
    lim = modelo._limite_mayoria(hoy or modelo.hoy_local())
    menor = {"$or": [{"$gt": ["$nac_aprox", lim]}, {"$eq": ["$tipo_documento", "TI"]}]}  # gemelo de filtro_menor
    tel = {"$or": [{"$gt": [{"$size": modelo._USABLES}, 0]},
                   {"$not": [{"$in": [{"$ifNull": ["$telefono", None]}, [None, ""]]}]}]}
    c = {"$ifNull": ["$completitud", 0]}
    return {"$cond": [{"$and": [menor, tel]}, {"$max": [0, {"$subtract": [c, proyeccion.PESO_TELEFONO]}]}, c]}


def _numero_completo(q: str) -> str | None:
    """Los dígitos de una búsqueda que es solo un número con separadores («300 111 2233», «+57 300-111-2233»)."""
    if re.fullmatch(r"[\d\s+().-]+", q or "") and len(re.sub(r"\D", "", q)) >= 4:
        return re.sub(r"\D", "", q)
    return None


def _digitos_restringido(d: str, rol: str, hoy: date) -> dict:
    """P: un número coincide solo entero (cédula, teléfono o ficha que su ficha muestra) o con los cuatro últimos
    dígitos del teléfono que la fila ya muestra (···2233); nunca con un prefijo o una subcadena. Sin la cédula de quien
    no autorizó ni los teléfonos de un menor. C busca números solo por la llamada entrante (`_buscar_consultor`)."""
    if rol != "planillero":
        return {"_id": {"$in": []}}
    visible = {"$nor": [telefonos_ocultos(hoy)]}
    tels = sorted({d, *tx.telefonos(d)})
    alts: list[dict] = [{**TRATABLE, "cedula": {"$in": sorted({d, tx.cedula(d)} - {""})}}, {**TRATABLE, "ficha": d},
                        {"$and": [visible, {"$or": [{"telefonos.numero": {"$in": tels}}, {"telefono": {"$in": tels}},
                                                    {"telefono2": {"$in": tels}}]}]}]
    if len(d) == 4:
        alts.append({"$and": [visible, {"telefono": {"$regex": re.escape(d) + "$"}}]})
    return {"$or": alts}


def _condiciones_q(q: str, rol: str | None, hoy: date) -> list[dict]:
    """Una condición por palabra de la búsqueda (hasta 6). Sin `rol` (A y K): prefijo de la cédula y subcadena de los
    teléfonos y la ficha, y nombre, dirección, lugar o correo. Con `rol`: solo lo que ese rol ve (arriba)."""
    out: list[dict] = []
    numero = _numero_completo(q) if rol else None
    for tok in [numero] if numero else tx.limpiar(q).split()[:6]:
        digitos = re.sub(r"\D", "", tok)
        if digitos and len(digitos) >= 4 and digitos == tok:
            if rol:
                out.append(_digitos_restringido(digitos, rol, hoy))
                continue
            rx = re.escape(digitos)
            out.append({"$or": [{"cedula": {"$regex": "^" + rx}}, {"telefonos.numero": {"$regex": rx}},
                                {"telefono": {"$regex": rx}}, {"telefono2": {"$regex": rx}}, {"ficha": {"$regex": rx}}]})
            continue
        limpio = re.sub(r"[^A-Z0-9@.]", "", tok)
        if not limpio:
            continue
        rx = re.escape(limpio)
        otros = [{"direccion_norm": {"$regex": rx}}, {"lugar_texto": {"$regex": rx}},
                 {"correo": {"$regex": rx, "$options": "i"}}]
        if not rol:
            out.append({"$or": [{"nombre_norm": {"$regex": rx}}, *otros]})
            continue
        alts = [{"nombre_norm": {"$regex": rx}}]
        if rol == "planillero":  # dirección, lugar escrito y correo: los ve de quien no dijo «no»
            alts.append({**TRATABLE, "$or": otros})
        if limpio.isdigit() and len(limpio) == 3:  # los tres últimos de la cédula (···123), que la fila ya muestra
            alts.append({"cedula": {"$regex": rx + "$"}})
        out.append({"$or": alts})
    return out


def filtro(f: Filtros, hoy: date | None = None) -> dict:
    """Documento de consulta de MongoDB para los filtros dados (solo personas activas). No consulta la base.

    Con `f._rol` (P o C: lo fijan `consulta` y la búsqueda) cada condición se mira contra lo que ese rol ve: una sobre
    un dato que no ve de quien no autorizó deja fuera a quien no autorizó, y una sobre los teléfonos deja fuera además
    a los menores. Así ningún filtro, ni el total, revela un dato oculto."""
    hoy = hoy or modelo.hoy_local()
    rol = f._rol
    y: list[dict] = [dict(ACTIVA)]
    solo_tratables: list[dict] = []
    solo_telefonos: list[dict] = []

    def poner(campo: str, cond: dict) -> None:
        if not rol or campo in VISIBLES_NO_AUTORIZO:
            y.append(cond)
        elif campo in FILTROS_TELEFONO:
            solo_telefonos.append(cond)
        else:
            solo_tratables.append(cond)

    if f.q:
        for cond in _condiciones_q(f.q, rol, hoy):
            poner("q", cond)
    if f.zona in ("urbana", "rural"):
        poner("zona", {"zona": f.zona})
    elif f.zona == "sin":
        poner("zona", {"zona": None})
    if f.lugar_id is not None:  # 0 = sin barrio ni vereda reconocidos
        poner("lugar_id", {"lugar_id": f.lugar_id or None})
    if f.fuente == "ambas":
        poner("fuente", {"fuentes": {"$all": ["tramites", "cedulas"]}})
    elif f.fuente in ("tramites", "cedulas", "reunion", "manual", "planilla"):
        poner("fuente", {"fuentes": f.fuente})
    if f.lista:
        poner("lista", {"listas": f.lista})
    if f.etiqueta:
        poner("etiqueta", {"etiquetas": f.etiqueta})
    if f.con_cedula is not None:
        poner("con_cedula", _lleno("cedula") if f.con_cedula else _vacio("cedula"))
    if f.con_telefono is not None:
        poner("con_telefono", {"telefono": {"$ne": None}} if f.con_telefono else {"telefono": None})
    if f.precision == "exacta":
        poner("precision", {"geo_precision": {"$in": ["direccion", "manual"]}})
    elif f.precision == "aproximada":
        poner("precision", {"geo_precision": {"$in": APROXIMADAS}})
    elif f.precision == "ubicada":  # cualquier coordenada: lo que se ve en el mapa
        poner("precision", {"lat": {"$ne": None}})
    elif f.precision == "sin":
        poner("precision", {"lat": None})
    if f.reunion_id:
        poner("reunion_id", {"asistencias.reunion_id": f.reunion_id})
    if f.asistio is not None:
        poner("asistio", {"asistencias.0": {"$exists": bool(f.asistio)}})
    if f.consentimiento in ("si", "no", "pendiente"):
        poner("consentimiento", {"consentimiento": f.consentimiento})
    elif f.consentimiento == "por_confirmar":  # «sí» declarado en planilla que A todavía no confirma
        poner("consentimiento", {"consentimiento": "si", "contacto_habilitado": {"$ne": True}})
    if f.tratables:
        poner("tratables", dict(TRATABLE))
    if f.lider:
        poner("lider", {"lider": True})
    if f.sexo in modelo.SEXOS:
        poner("sexo", {"sexo": f.sexo})
    elif f.sexo == "sin":
        poner("sexo", _vacio("sexo"))
    if f.ids:
        poner("ids", {"_id": {"$in": [int(x) for x in re.findall(r"\d+", f.ids)[:500]]}})
    if f.completitud_max is not None:  # P y C: la que ven (la de un menor, sin teléfono)
        poner("completitud_max", {"$expr": {"$lte": [expr_completitud_vista(hoy), f.completitud_max]}} if rol
              else {"completitud": {"$lte": f.completitud_max}})
    # Edad: rango de la fecha de nacimiento (exacta con la fecha; con la edad declarada, ±1 año)
    if f.edad_min is not None:
        poner("edad_min", {"nac_aprox": {"$ne": None, "$lte": _restar_anios(hoy, f.edad_min).isoformat()}})
    if f.edad_max is not None:
        poner("edad_max", {"nac_aprox": {"$ne": None, "$gt": _restar_anios(hoy, f.edad_max + 1).isoformat()}})
    if f.tipo_documento in modelo.TIPOS_DOCUMENTO:
        poner("tipo_documento", {"tipo_documento": f.tipo_documento})
    if f.cedula_verificada is not None:
        poner("cedula_verificada",
              {"cedula_verificada": True} if f.cedula_verificada else {"cedula_verificada": {"$ne": True}})
    if f.puesto_id is not None:
        poner("puesto_id", {"votacion.puesto_id": f.puesto_id or None})
    for campo, cond in (("con_puesto", _sino(f.con_puesto, CON_PUESTO, {"$nor": [CON_PUESTO]})),
                        ("con_mesa", _sino(f.con_mesa, CON_MESA, {"$nor": [CON_MESA]}))):
        if cond:
            poner(campo, cond)
    if f.votacion_estado:
        if f.votacion_estado not in modelo.ESTADOS_VOTACION:
            raise HTTPException(422, "Estado de votación desconocido")
        poner("votacion_estado", modelo.filtro_estado_votacion(f.votacion_estado, f._eleccion))
    if f.donde in modelo.DONDE_VOTA:
        poner("donde", {"votacion.donde": f.donde})
    if f.abordado is not None:
        poner("abordado", {"abordaje.n": {"$gte": 1}} if f.abordado else {"$nor": [{"abordaje.n": {"$gte": 1}}]})
    if f.contactado is not None:
        poner("contactado", {"abordaje.efectivos": {"$gte": 1}} if f.contactado
              else {"$nor": [{"abordaje.efectivos": {"$gte": 1}}]})
    if f.abordaje_estado == "sin_abordar":
        poner("abordaje_estado", {"abordaje.estado": None})
    elif f.abordaje_estado in modelo.ESTADOS_ABORDAJE:
        poner("abordaje_estado", {"abordaje.estado": f.abordaje_estado})
    if f.ultimo_resultado in modelo.RESULTADOS:
        poner("ultimo_resultado", {"abordaje.ultimo_resultado": f.ultimo_resultado})
    if f.sin_acercamiento_dias is not None:
        limite = (hoy - timedelta(days=f.sin_acercamiento_dias)).isoformat()
        poner("sin_acercamiento_dias",
              {"$or": [{"abordaje.ultimo_fecha": None}, {"abordaje.ultimo_fecha": {"$lt": limite}}]})
    if f.proximo_vencido:
        poner("proximo_vencido", {"abordaje.proximo": {"$ne": None, "$lte": hoy.isoformat()}})
    if f.canal_autorizado in modelo.CANALES_AUTORIZACION:
        o = [{"consentimiento": "si", "consentimiento_canales": f.canal_autorizado}]
        if f.canal_autorizado in modelo.CANALES_IMPLICITOS:  # «sí» anterior a los canales: valen los implícitos
            o.append({"consentimiento": "si", "consentimiento_canales": {"$exists": False}})
        poner("canal_autorizado", {"$or": o})
    sit = filtro_situacion(f.situacion)
    if sit:
        poner("situacion", sit)
    if f.creado_por is not None:
        poner("creado_por", {"creado_por.uid": f.creado_por})
    if f.actualizado_por is not None:
        poner("actualizado_por", {"actualizado_por.uid": f.actualizado_por})
    if f.menor is not None:
        poner("menor", modelo.filtro_menor(hoy) if f.menor else {"$nor": [modelo.filtro_menor(hoy)]})
    if f.requiere_actualizacion not in (None, ""):
        v = f.requiere_actualizacion
        if v == "1":
            poner("requiere_actualizacion", {"requiere_actualizacion": {"$ne": None}})
        elif v == "0":
            poner("requiere_actualizacion", {"requiere_actualizacion": None})
        else:
            motivos = [m for m in v.split(",") if m in modelo.MOTIVOS_ACTUALIZACION]
            poner("requiere_actualizacion", {"requiere_actualizacion.motivo": {"$in": motivos}})
    if f.varios_telefonos is not None:
        poner("varios_telefonos", {"telefono2": {"$ne": None}} if f.varios_telefonos else {"telefono2": None})
    if f.telefono_estado in modelo.ESTADOS_TELEFONO:
        poner("telefono_estado", {"telefonos.estado": f.telefono_estado})
    for campo in ("estado_civil", "nivel_educativo", "situacion_laboral", "tenencia_vivienda", "regimen_salud"):
        v = getattr(f, campo)
        if v == "sin":
            poner(campo, _vacio(campo))
        elif v:
            poner(campo, {campo: v})
    if f.estrato is not None:
        poner("estrato", {"estrato": f.estrato})
    for campo in SIN_CAMPOS:
        if getattr(f, f"sin_{campo}"):
            poner(f"sin_{campo}", falta(campo, hoy, f._dias_dato))
    if f.sin_puesto_mesa:  # «Sin puesto o mesa» de Mi trabajo
        poner("sin_puesto_mesa", {"$or": [falta("puesto", hoy, f._dias_dato), falta("mesa", hoy, f._dias_dato)]})
    if f.mios and f._uid is not None:
        poner("mios", {"$or": [{"creado_por.uid": f._uid}, {"actualizado_por.uid": f._uid}]})
    if f.poligono:
        anillo = geometria.validar_anillo(geometria.decodificar(f.poligono))
        poner("poligono", {"punto": {"$geoWithin": {"$geometry": geometria.a_geojson(anillo)}}})
    if f.area_id is not None:
        poner("area_id", {"punto": {"$geoWithin": {"$geometry": f._area}}} if f._area else {"_id": {"$in": []}})
    if solo_tratables or solo_telefonos:
        y += [dict(TRATABLE), *solo_tratables]
    if solo_telefonos:
        y += [{"$nor": [telefonos_ocultos(hoy)]}, *solo_telefonos]
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
    # La asignación vale solo la del usuario (`usuarios.asignacion.areas`): `areas.asignada_a` es una copia que
    # Usuarios no actualiza, y quitarle un área debe cortar también el filtro (integración G2×G3×G5)
    if f.area_id is not None and f.area_id not in asignacion_de(quien)["areas"]:
        raise _prohibido("Esa área no le está asignada")


def consulta(db: Database, quien: Any, f: Filtros, con_alcance: bool = True, hoy: date | None = None) -> dict:
    """La consulta de una ruta abierta a P y C: parámetros permitidos, filtros y, si se pide, el alcance."""
    exigir_permitidos(db, quien, f)
    f._uid = getattr(quien, "uid", None)
    f._rol = rol_restringido(quien)
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
