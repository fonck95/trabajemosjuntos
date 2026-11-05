"""MongoDB: conexión, índices, nomenclátor inicial y operaciones comunes sobre personas.

Colecciones (todas con `_id` entero para que las direcciones del panel sean cortas, salvo sesiones y auditoría):

* `personas`: una por habitante. Lleva adentro sus trámites, notas, listas, etiquetas, asistencias, teléfonos de todas
  las fuentes y el registro original de cada fuente, así una ficha se lee de una sola vez.
* `lugares`, `puestos`, `reuniones`, `coincidencias`, `conflictos_cedula`, `etiquetas`, `campos`, `importaciones`.
* `autorizaciones` y `acercamientos` (de solo inserción), `solicitudes` de los titulares y `usuarios`.
* `sesiones`, `intentos`, `lecturas` e `idempotencia` (con caducidad automática), `auditoria`, `contadores`.
* `meta` (marcas, turnos, ajustes, la versión del esquema y la clave secreta de las huellas) y `suprimidos` (huellas
  HMAC de quienes pidieron la supresión, sin ningún dato en claro, para que una importación no los vuelva a crear).
"""
from __future__ import annotations

import copy
import hashlib
import hmac
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from fastapi import HTTPException
from pymongo import ASCENDING, DESCENDING, IndexModel, MongoClient, ReturnDocument, UpdateOne
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from . import modelo
from .pipeline import texto as tx
from .pipeline.direcciones import Lugar

GAZETTEER = Path(__file__).resolve().parents[1] / "geo" / "gazetteer.json"
PUESTOS = Path(__file__).resolve().parents[1] / "geo" / "puestos_yondo.json"
ACTIVA = {"eliminado": {"$ne": True}, "fusionada_en": None}
log = logging.getLogger("panel.migracion")

ETIQUETAS_INICIALES = [
    ("Vivienda", "necesidad"), ("Agua potable", "necesidad"), ("Saneamiento", "necesidad"), ("Salud", "necesidad"),
    ("Empleo", "necesidad"), ("Educación", "necesidad"), ("Vías", "necesidad"), ("Energía", "necesidad"),
    ("Conectividad", "necesidad"), ("Seguridad", "necesidad"), ("Adulto mayor", "necesidad"),
    ("Discapacidad", "necesidad"), ("Primera infancia", "necesidad"), ("Proyecto productivo", "necesidad"),
    ("Víctima del conflicto", "interes"), ("Campesino", "interes"), ("Pescador", "interes"), ("Joven", "interes"),
    ("Mujer cabeza de hogar", "interes"), ("Líder comunitario", "rol"), ("JAC", "rol"), ("Voluntario", "rol"),
]
# Etiquetas que revelan datos sensibles (Ley 1581, art. 5): P y C no las ven
ETIQUETAS_SENSIBLES = ("Discapacidad", "Víctima del conflicto", "JAC", "Líder comunitario")

# Campos de la ficha con su valor inicial: así toda persona tiene la misma forma (1.1)
PERSONA_VACIA: dict[str, Any] = {
    "nombre": None, "nombre_norm": None, "cedula": None, "sexo": None, "edad": None, "fecha_nacimiento": None,
    "telefono": None, "telefono2": None, "correo": None, "direccion": None, "direccion_norm": None, "lugar_id": None,
    "lugar_texto": None, "zona": None, "lat": None, "lon": None, "geo_precision": None, "geo_manual": False,
    "ficha": None, "puesto_votacion": None, "mesa": None, "ocupacion": None, "nivel_educativo": None,
    "personas_hogar": None, "lider": False, "consentimiento": "pendiente", "consentimiento_fecha": None,
    "observaciones": None, "extra": {}, "fuentes": [], "clave_tramites": None, "completitud": 0, "ultimo_contacto": None,
    "fusionada_en": None, "eliminado": False, "listas": [], "etiquetas": [], "tramites": [], "notas": [], "origen": [],
    "asistencias": [], "claves_tramites": [], "reunion_origen": None,
    # Identidad
    "tipo_documento": None, "cedula_verificada": False, "cedula_origen": None, "cedulas_anteriores": [],
    # Demografía (la edad declarada vale desde edad_ref; nac_* se derivan)
    "edad_ref": None, "nac_aprox": None, "nac_exacta": False, "nac_base": {}, "estado_civil": None,
    "situacion_laboral": None, "jefe_hogar": None, "tenencia_vivienda": None, "estrato": None, "regimen_salud": None,
    "sensibles": {}, "sensibles_autorizados": [],
    # Teléfonos de todas las fuentes (telefono y telefono2 se derivan) y votación (puesto_votacion y mesa se derivan)
    "telefonos": [], "votacion": None,
    # Autorización del titular (derivada de `autorizaciones`)
    "consentimiento_medio": None, "consentimiento_canales": [], "contacto_habilitado": False,
    "mayor_declarado": False, "autorizacion_ultima": None, "reclamo_en_tramite": False,
    # Seguimiento
    "abordaje": None, "abordaje_seq": 0, "requiere_actualizacion": None, "en_curso": None, "situacion": None,
    "no_disponible": {},
    # Búsqueda, autoría, procedencia y avance
    "nombre_fon": [], "creado_por": None, "actualizado_por": None, "procedencia": {}, "alternos": [], "avance": {},
    # Punto (GeoJSON) y ubicación por GPS
    "punto": None, "geo_fuente": None, "precision_m": None,
}
# geo_manual: False (automática), "lugar" (barrio o vereda elegido a mano: la persona sigue el punto de ese lugar) o
# "punto" (puesto a mano en el mapa: no se mueve). Las fichas viejas con True se tratan como "punto".
PUNTO_MANUAL = (True, "punto")
# Campos de la ubicación: al unir fichas se toman en bloque de una sola de ellas
GEO = ("lat", "lon", "geo_precision", "lugar_id", "lugar_texto", "zona", "direccion_norm", "geo_manual", "punto",
       "geo_fuente", "precision_m")
# Fuente de un teléfono según la fuente con que se crea la ficha
FUENTE_TELEFONO = {"manual": "panel", "panel": "panel", "reunion": "reunion", "tramites": "tramites",
                   "cedulas": "cedulas", "planilla": "planilla", "consultor": "consultor"}


def ahora() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# Tiempos de espera con MongoDB: si se cae o se cuelga, una petición del panel no retiene su hilo más de unos segundos
# (los hilos los comparte el sitio público). connectTimeoutMS también limita la consulta DNS de una URI mongodb+srv://
# y lo que tarda en notarse un servidor colgado. Con ~12 000 filas inventadas, el comando más lento de importar,
# recalcular ubicaciones o exportar tarda 0,3 s en local: 20 s por operación dejan margen para un MongoDB lento.
# Una opción escrita en la URI (?socketTimeoutMS=…) manda sobre estos valores.
TIEMPOS_MS = {"serverSelectionTimeoutMS": 2500, "connectTimeoutMS": 5000, "socketTimeoutMS": 20000}


def conectar(uri: str, nombre: str | None = None) -> tuple[MongoClient, Database]:
    en_uri = uri.lower()
    tiempos = {k: v for k, v in TIEMPOS_MS.items() if f"{k.lower()}=" not in en_uri}
    cliente = MongoClient(uri, tz_aware=True, appname="panel-yondo", **tiempos)
    try:
        db = cliente.get_default_database()
    except Exception:  # la URI no trae base de datos (Railway)
        db = None
    if nombre or db is None:
        db = cliente[nombre or "panel_yondo"]
    return cliente, db


def siguiente_id(db: Database, coleccion: str, cuantos: int = 1) -> int:
    """Reserva `cuantos` identificadores consecutivos y devuelve el primero."""
    c = db.contadores.find_one_and_update({"_id": coleccion}, {"$inc": {"n": cuantos}}, upsert=True,
                                          return_document=ReturnDocument.AFTER)
    return c["n"] - cuantos + 1


INDICES_PERSONAS = (
    "telefonos.numero", "cedulas_anteriores", "nombre_fon", "nac_aprox", "tipo_documento", "votacion.puesto_id",
    "votacion.estado", "votacion.eleccion", "abordaje.ultimo_ts", "abordaje.estado", "abordaje.proximo",
    "consentimiento", "contacto_habilitado", "creado_por.uid", "actualizado_por.uid", "actualizado_en",
    "ultimo_contacto", "fusionada_en", "requiere_actualizacion.ts", "situacion.estado", "sexo", "en_curso.uid",
)
_SOLO_TEXTO = {"clave_migracion": {"$type": "string"}}


def _indices() -> dict[str, list[IndexModel]]:
    """Índices de cada colección (1.10). Se crean juntos, un comando por colección."""
    i = IndexModel
    personas = [i("nombre_norm"), i("cedula", unique=True, partialFilterExpression={"cedula": {"$type": "string"}}),
                i("clave_tramites", unique=True, partialFilterExpression={"clave_tramites": {"$type": "string"}}),
                *(i(c) for c in ("telefono", "lugar_id", "asistencias.reunion_id", "tramites.id_externo", "etiquetas",
                                 "listas", "fuentes", "completitud")),
                i([("eliminado", ASCENDING), ("fusionada_en", ASCENDING)]),
                *(i(c) for c in INDICES_PERSONAS), i([("punto", "2dsphere")])]
    por_persona_ts = [i([("persona_id", ASCENDING), ("ts", ASCENDING)]),
                      i("clave_migracion", unique=True, partialFilterExpression=_SOLO_TEXTO)]
    return {
        "personas": personas,
        "lugares": [i([("nombre", ASCENDING), ("tipo", ASCENDING)], unique=True)],
        "coincidencias": [i([("persona_id", ASCENDING), ("candidato_id", ASCENDING)], unique=True), i("estado")],
        "reuniones": [i([("fecha", DESCENDING)])],
        "etiquetas": [i("nombre", unique=True)],
        "campos": [i("clave", unique=True)],
        "auditoria": [i([("entidad", ASCENDING), ("entidad_id", ASCENDING)]),
                      *(i([(c, ASCENDING), ("ts", ASCENDING)]) for c in ("uid", "capturado_por", "accion"))],
        "sesiones": [i("expira", expireAfterSeconds=0), i("uid")],
        "intentos": [i("ts", expireAfterSeconds=24 * 3600), i([("ip", ASCENDING), ("ts", ASCENDING)]),
                     i([("nombre_h", ASCENDING), ("ts", ASCENDING)]),
                     i([("ip", ASCENDING), ("marca_h", ASCENDING), ("ts", ASCENDING)])],
        "usuarios": [i("usuario", unique=True)],
        "acercamientos": [*por_persona_ts, i([("uid", ASCENDING), ("ts", ASCENDING)]), i("ts")],
        "autorizaciones": por_persona_ts,
        "puestos": [i([("eleccion", ASCENDING), ("codigo", ASCENDING)], unique=True)],
        "areas": [i("nombre", unique=True), i("asignada_a")],
        "conflictos_cedula": [i("clave", unique=True), i("estado"), i("persona_id"), i("cedula")],
        "solicitudes": [i("estado"), i("persona_id")],
        "lecturas": [i([("uid", ASCENDING), ("dia", ASCENDING)]), i("ts", expireAfterSeconds=90 * 24 * 3600)],
        "idempotencia": [i("ts", expireAfterSeconds=24 * 3600), i("persona_id")],
    }


def inicializar(db: Database) -> None:
    """Índices, catálogos iniciales y migración del esquema (con la reconciliación de cada arranque). Solo se crean
    índices nuevos: ninguno existente cambia de opciones (un create_index con otras opciones falla en cada arranque)."""
    p = db.personas
    for coleccion, indices in _indices().items():
        db[coleccion].create_indexes(indices)
    # El catálogo inicial se siembra una sola vez (en una base nueva): si el administrador lo borra, no vuelve
    if db.meta.find_one({"_id": "etiquetas_sembradas"}) is None:
        if db.etiquetas.count_documents({}) == 0 and db.contadores.find_one({"_id": "etiquetas"}) is None:
            primero = siguiente_id(db, "etiquetas", len(ETIQUETAS_INICIALES))
            db.etiquetas.insert_many([{"_id": primero + i, "nombre": n, "grupo": g, "orden": i,
                                       "sensible": n in ETIQUETAS_SENSIBLES}
                                      for i, (n, g) in enumerate(ETIQUETAS_INICIALES)])
        db.meta.update_one({"_id": "etiquetas_sembradas"}, {"$set": {"ts": ahora()}}, upsert=True)
    # Fichas viejas: geo_manual=True por un barrio o vereda elegido a mano (el punto puesto en el mapa es «manual»)
    p.update_many({"geo_manual": True, "geo_precision": {"$ne": "manual"}, "lugar_id": {"$ne": None}},
                  {"$set": {"geo_manual": "lugar"}})
    sembrar_lugares(db)
    sembrar_puestos(db)
    from . import migraciones  # aquí: migraciones usa este módulo
    migraciones.migrar(db)


def sembrar_lugares(db: Database, ruta: Path = GAZETTEER) -> int:
    """Carga el nomenclátor público (geo/gazetteer.json). No pisa los lugares editados a mano.

    En las veredas se prefiere el `nucleo` (caserío, escuela o centro poblado) al centroide del polígono: ahí vive
    la gente."""
    if not ruta.exists():
        return 0
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    nuevos = 0
    for lg in datos.get("lugares", []):
        nombre = tx.limpiar(lg["nombre"])
        punto = lg.get("nucleo") or {}
        lat = punto.get("lat", lg.get("lat"))
        lon = punto.get("lon", lg.get("lon"))
        alias = sorted({tx.limpiar(a) for a in [*lg.get("alias", []), *lg.get("alias_ambiguos", [])]} - {nombre})
        campos = {
            "zona": lg.get("zona") or ("urbana" if lg["tipo"] == "barrio" else "rural"), "lat": lat, "lon": lon,
            "alias": alias, "padre": tx.limpiar(lg.get("padre")) or None, "fuente": lg.get("fuente"),
            "precision": "nucleo" if punto else lg.get("precision"), "geom": lg.get("geom"),
            "codigo_dane": lg.get("codigo_dane"), "nota": lg.get("nota"),
        }
        actual = db.lugares.find_one({"nombre": nombre, "tipo": lg["tipo"]}, {"editado": 1})
        if actual is None:
            db.lugares.insert_one({"_id": siguiente_id(db, "lugares"), "nombre": nombre, "tipo": lg["tipo"],
                                   "editado": False, "creado_en": ahora(), **campos})
            nuevos += 1
        elif not actual.get("editado"):
            db.lugares.update_one({"_id": actual["_id"]}, {"$set": campos})
    return nuevos


def sembrar_puestos(db: Database, ruta: Path = PUESTOS) -> int:
    """Siembra una sola vez el catálogo de puestos de votación (geo/puestos_yondo.json, DIVIPOLE). Para otra elección,
    el administrador crea los puestos nuevos y cambia la elección vigente en Ajustes."""
    if db.meta.find_one({"_id": "puestos_sembrados"}) is not None or not ruta.exists():
        return 0
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    nuevos = 0
    for pu in datos.get("puestos", []):
        if db.puestos.find_one({"eleccion": pu["eleccion"], "codigo": pu["codigo"]}, {"_id": 1}):
            continue
        try:
            db.puestos.insert_one({"_id": siguiente_id(db, "puestos"), **pu, "editado": False, "creado_en": ahora()})
            nuevos += 1
        except DuplicateKeyError:  # otro proceso lo sembró al mismo tiempo
            pass
    db.meta.update_one({"_id": "puestos_sembrados"}, {"$set": {"ts": ahora(), "fuente": ruta.name}}, upsert=True)
    return nuevos


def puestos_vigentes(db: Database, eleccion: str | None = None) -> list[dict]:
    """Puestos activos de la elección vigente (o de la pedida)."""
    eleccion = eleccion or modelo.leer_ajustes(db)["eleccion_vigente"]
    return list(db.puestos.find({"eleccion": eleccion, "activo": {"$ne": False}}).sort("codigo", 1))


def lugares(db: Database) -> list[Lugar]:
    return [Lugar(l["_id"], l["nombre"], l["tipo"], l["zona"], l.get("lat"), l.get("lon"), tuple(l.get("alias") or ()),
                  l.get("padre")) for l in db.lugares.find({}, {"geom": 0})]


def subir_catalogos_version(db: Database) -> int:
    """`meta.catalogos_version`: sube al editar campos, etiquetas, lugares, puestos o ajustes (ETag de los catálogos)."""
    m = db.meta.find_one_and_update({"_id": "catalogos_version"}, {"$inc": {"valor": 1}}, upsert=True,
                                    return_document=ReturnDocument.AFTER)
    return m["valor"]


def catalogos_version(db: Database) -> int:
    return (db.meta.find_one({"_id": "catalogos_version"}) or {}).get("valor", 0)


# ───────────────────────────── Turnos con dueño (migración e importación) ─────────────────────────────

def _instante() -> datetime:
    return datetime.now(timezone.utc)


def tomar_turno(db: Database, nombre: str, dueño: str, minutos: int) -> bool:
    """Toma el turno `meta.<nombre>` si está libre (vencido) o ya es de `dueño`. False si lo tiene otro."""
    ya = _instante()
    try:
        db.meta.find_one_and_update({"_id": nombre, "$or": [{"hasta": {"$lt": ya}}, {"dueño": dueño}]},
                                    {"$set": {"dueño": dueño, "hasta": ya + timedelta(minutes=minutos), "desde": ya}},
                                    upsert=True)
        return True
    except DuplicateKeyError:
        return False


def renovar_turno(db: Database, nombre: str, dueño: str, minutos: int) -> bool:
    r = db.meta.update_one({"_id": nombre, "dueño": dueño}, {"$set": {"hasta": _instante() + timedelta(minutes=minutos)}})
    return r.matched_count == 1


def soltar_turno(db: Database, nombre: str, dueño: str) -> None:
    # Un segundo atrás: la siguiente llamada (aun en el mismo instante) lo encuentra vencido
    db.meta.update_one({"_id": nombre, "dueño": dueño}, {"$set": {"hasta": _instante() - timedelta(seconds=1)}})


# ───────────────────────────── Auditoría ─────────────────────────────

CLAVES_AUDITORIA = frozenset({"ts", "usuario", "accion", "entidad", "entidad_id", "detalle", "ip", "uid", "rol", "campos",
                              "completados"})
OCULTO = "(oculto)"
# Claves de `detalle` que llevan una cédula: quedan solo sus 3 últimos dígitos, para todos los roles
CLAVES_CEDULA = frozenset({"cedula", "cedulas_anteriores", "cedula_en_traspaso", "cedula_correcta", "cedula_digitada",
                           "cedula_repetida", "cedula_fila", "cedula_anterior"})


def _mascara_cedula(v: Any) -> Any:
    if isinstance(v, list):
        return [_mascara_cedula(x) for x in v]
    if isinstance(v, dict):
        return {k: _mascara_cedula(x) for k, x in v.items()}
    if isinstance(v, (str, int)) and not isinstance(v, bool):
        s = str(v).strip()
        return f"···{s[-3:]}" if s else v
    return v


def enmascarar(db: Database, detalle: Any) -> Any:
    """`detalle` sin datos sensibles ni cédulas en claro (1.9): `sensibles`, `lider`, las etiquetas sensibles y los
    campos propios sensibles quedan «(oculto)»; las cédulas, con sus 3 últimos dígitos."""
    cache: dict[str, set] = {}

    def sensibles(col: str, clave: str) -> set:
        if col not in cache:
            cache[col] = {x[clave] for x in db[col].find({"sensible": True}, {clave: 1})}
        return cache[col]

    def etiquetas(v: Any) -> Any:
        if isinstance(v, list):
            return [OCULTO if e in sensibles("etiquetas", "_id") else e for e in v]
        if isinstance(v, dict):
            return {k: etiquetas(x) for k, x in v.items()}
        return v

    def extra(v: Any) -> Any:
        if not isinstance(v, dict):
            return v
        if v and set(v) <= {"antes", "despues"}:
            return {k: extra(x) for k, x in v.items()}
        return {k: OCULTO if k in sensibles("campos", "clave") else ir(x) for k, x in v.items()}

    def ir(v: Any) -> Any:
        if isinstance(v, list):
            return [ir(x) for x in v]
        if not isinstance(v, dict):
            return v
        out = {}
        for k, x in v.items():
            k = str(k)
            if k in CLAVES_CEDULA:
                out[k] = _mascara_cedula(x)
            elif k in ("lider", "sensibles") or k.startswith("sensibles."):
                out[k] = OCULTO
            elif k == "etiquetas":
                out[k] = etiquetas(x)
            elif k == "extra":
                out[k] = extra(x)
            else:
                out[k] = ir(x)
        return out

    return ir(detalle)


def auditar(db: Database, quien: Any, accion: str, entidad: str | None = None, entidad_id: int | None = None,
            detalle: Any = None, ip: str | None = None, campos: list[str] | None = None,
            completados: list[str] | None = None, **extra) -> None:
    """Una entrada de la auditoría.

    `quien` es el nombre de usuario (texto, como siempre) o un `acceso.Quien`: con él la entrada lleva además `uid`
    (0 para el administrador) y `rol`, y su IP si no se pasa otra. `campos` y `completados` son solo nombres canónicos.
    `extra` va al nivel superior: campos no personales que los indicadores necesitan aun después de una supresión
    (`capturado_por`, `canal`, `resultado`, `estado`…). El detalle se enmascara (`enmascarar`). Toda entrada sobre una
    persona usa entidad «persona» y su id: así la supresión limpia todo su rastro."""
    choque = CLAVES_AUDITORIA & set(extra)
    if choque:
        raise ValueError(f"auditar: {sorted(choque)} no van en extra")
    doc = {"ts": ahora(), "usuario": quien, "accion": accion, "entidad": entidad, "entidad_id": entidad_id,
           "detalle": json.dumps(enmascarar(db, detalle), ensure_ascii=False, default=str) if detalle is not None else None,
           "ip": ip}
    if quien is not None and not isinstance(quien, str):
        doc.update(usuario=quien.usuario, uid=quien.uid, rol=quien.rol, ip=ip if ip is not None else quien.ip)
    if campos is not None:
        doc["campos"] = list(campos)
    if completados is not None:
        doc["completados"] = list(completados)
    doc.update(extra)
    db.auditoria.insert_one(doc)


def _nombre_de(quien: Any) -> str | None:
    return quien if quien is None or isinstance(quien, str) else quien.usuario


def _uid_de(quien: Any) -> int | None:
    if quien is None or isinstance(quien, str):
        return 0 if quien not in (None, "sistema") else None
    return quien.uid


# ───────────────────────────── Completitud del perfil (1.11) ─────────────────────────────

PESOS = [  # (campo, puntos) — suma 100
    ("cedula", 18), ("telefono", 14), ("direccion", 6), ("ubicacion", 12), ("sexo", 5), ("edad", 6), ("correo", 3),
    ("ocupacion", 4), ("nivel_educativo", 4), ("personas_hogar", 3), ("puesto", 6), ("mesa", 4), ("necesidades", 8),
    ("autorizacion", 7),
]
CAMPOS_COMPLETITUD = {"cedula": 1, "telefono": 1, "telefono2": 1, "telefonos": 1, "direccion": 1, "geo_precision": 1,
                      "sexo": 1, "edad": 1, "fecha_nacimiento": 1, "correo": 1, "ocupacion": 1, "situacion_laboral": 1,
                      "nivel_educativo": 1, "personas_hogar": 1, "votacion": 1, "puesto_votacion": 1, "mesa": 1,
                      "etiquetas": 1, "consentimiento": 1, "completitud": 1}


def _puntos_puesto(p: dict, peso: int) -> int:
    v = p.get("votacion")
    if not isinstance(v, dict):
        return peso // 2 if not modelo.vacio(p.get("puesto_votacion")) else 0
    if v.get("puesto_id") is not None or v.get("donde") == "no_inscrito":
        return peso
    if not modelo.vacio(v.get("puesto_texto")) or v.get("donde") == "otro_municipio":
        return peso // 2
    return 0


def completitud(p: dict, necesidades: set | None = None) -> int:
    """Puntos (0-100) de lo que tiene la ficha. `necesidades`: ids de las etiquetas del grupo «necesidad» (sin él,
    cualquier etiqueta cuenta). Lectura tolerante: una ficha sin `telefonos` o sin `votacion` usa los heredados."""
    pts = 0
    for campo, peso in PESOS:
        if campo == "telefono":
            ok = bool(modelo.usables(modelo.telefonos_de(p))) or not modelo.vacio(p.get("telefono"))
        elif campo == "ubicacion":
            prec = p.get("geo_precision")
            pts += peso if prec in ("direccion", "manual") else (peso // 2 if prec else 0)
            continue
        elif campo == "edad":
            ok = modelo.tiene_dato(p, "edad")
        elif campo == "ocupacion":
            ok = not modelo.vacio(p.get("ocupacion")) or not modelo.vacio(p.get("situacion_laboral"))
        elif campo == "puesto":
            pts += _puntos_puesto(p, peso)
            continue
        elif campo == "mesa":
            v = p.get("votacion")
            ok = v.get("mesa") is not None if isinstance(v, dict) else not modelo.vacio(p.get("mesa"))
        elif campo == "necesidades":
            et = p.get("etiquetas") or []
            ok = bool(et) if necesidades is None else any(e in necesidades for e in et)
        elif campo == "autorizacion":
            ok = p.get("consentimiento") == "si"
        elif campo == "personas_hogar":
            ok = p.get("personas_hogar") not in (None, "", 0)
        else:
            ok = not modelo.vacio(p.get(campo))
        pts += peso if ok else 0
    return pts


def ids_necesidad(db: Database) -> set:
    return {e["_id"] for e in db.etiquetas.find({"grupo": "necesidad"}, {"_id": 1})}


def recalcular_completitud(db: Database, ids: Iterable[int] | None = None) -> None:
    filtro = dict(ACTIVA) if ids is None else {"_id": {"$in": list(ids)}}
    necesidades = ids_necesidad(db)
    ops = []
    for p in db.personas.find(filtro, CAMPOS_COMPLETITUD):
        c = completitud(p, necesidades)
        if c != p.get("completitud"):
            ops.append(UpdateOne({"_id": p["_id"]}, {"$set": {"completitud": c}}))
    for k in range(0, len(ops), 1000):
        db.personas.bulk_write(ops[k:k + 1000], ordered=False)


# ───────────────────────────── Personas ─────────────────────────────

def persona_vacia() -> dict:
    """Copia independiente de PERSONA_VACIA: sus listas y objetos no se comparten con otras fichas."""
    return copy.deepcopy(PERSONA_VACIA)


def nueva_persona(db: Database, datos: dict, fuente: str) -> dict:
    """Ficha nueva con todos los campos de PERSONA_VACIA (copias propias) y los derivados: nombre normalizado y
    fonético, tipo de documento, teléfonos (de `telefono` y `telefono2` si no viene la lista), punto y edad."""
    doc = persona_vacia()
    doc["fuentes"] = [fuente]
    doc.update(datos)
    if "_id" not in datos:
        doc["_id"] = siguiente_id(db, "personas")
    doc["nombre_norm"] = tx.nombre_norm(doc["nombre"])
    if not datos.get("nombre_fon"):
        doc["nombre_fon"] = modelo.claves_foneticas(doc["nombre"])
    if doc.get("cedula") and not doc.get("tipo_documento"):
        doc["tipo_documento"] = "CC"
    if "telefonos" not in datos:
        fte = FUENTE_TELEFONO.get(fuente, "panel")
        doc["telefonos"] = modelo.unir_telefonos([], [modelo.telefono_nuevo(doc[k], fte)
                                                      for k in ("telefono", "telefono2") if doc.get(k) not in (None, "")])
    doc.update(modelo.derivar_telefonos(doc["telefonos"]))
    if doc.get("punto") is None:
        doc["punto"] = modelo.punto(doc.get("lat"), doc.get("lon"))
    if doc.get("edad") is not None and not doc.get("edad_ref"):
        doc["edad_ref"] = modelo.hoy_local().isoformat()
    if doc.get("edad") is not None or not modelo.vacio(doc.get("fecha_nacimiento")):
        doc.update(modelo.calcular_nac(doc))
    doc["creado_en"] = doc["actualizado_en"] = ahora()
    return doc


def completar_doc(doc: dict, datos: dict) -> list[str]:
    """Llena en el documento solo los campos vacíos. La importación nunca pisa lo editado en el panel."""
    cambios = []
    for k, v in datos.items():
        if v in (None, "") or doc.get(k) not in (None, ""):
            continue
        if k == "telefono" and v == doc.get("telefono2"):
            continue
        if k == "telefono2" and v == doc.get("telefono"):
            continue
        doc[k] = v
        cambios.append(k)
    return cambios


def _rango_ubicacion(p: dict) -> int:
    """Qué tan confiable es la ubicación de una ficha, para quedarse con la mejor al unir dos."""
    if p.get("geo_manual") in ("punto", True):
        return 4
    if p.get("geo_precision") == "direccion":
        return 3
    if p.get("geo_manual") == "lugar":
        return 2
    return 1 if p.get("lat") is not None else 0


# Gemelo de _rango_ubicacion sobre la ficha guardada (expresión)
_EXPR_RANGO = {"$switch": {"branches": [
    {"case": {"$in": [{"$ifNull": ["$geo_manual", False]}, ["punto", True]]}, "then": 4},
    {"case": {"$eq": ["$geo_precision", "direccion"]}, "then": 3},
    {"case": {"$eq": ["$geo_manual", "lugar"]}, "then": 2},
    {"case": {"$ne": [{"$ifNull": ["$lat", None]}, None]}, "then": 1}], "default": 0}}


# ───────────────────────────── Autorizaciones ─────────────────────────────

ESTADO_EFECTIVO = {"si": "si", "no": "no", "revocada": "no", "pendiente": "pendiente", None: "pendiente"}


def autorizacion_doc(db: Database, persona_id: int | None, estado: str, medio: str, **campos) -> dict:
    """Un evento de `autorizaciones` (1.6) con todos sus campos; `campos` pisa los valores por defecto."""
    doc = {"_id": None, "persona_id": persona_id, "estado": estado, "medio": medio, "canales": [],
           "canales_implicitos": False, "sensibles": [], "mayor_declarado": False, "evidencia": None,
           "evidencia_sha256": None, "evidencia_fila": None, "texto_version": None, "fecha_declarada": None,
           "nota": None, "reunion_id": None, "acercamiento_id": None, "uid": None, "usuario": None, "rol": None,
           "capturado_por": None, "confirmada_por": None, "clave_migracion": None, "importacion_id": None,
           "ts": ahora()}
    doc.update(campos)
    if doc["_id"] is None:
        doc["_id"] = siguiente_id(db, "autorizaciones")
    return doc


def _canales_vigentes(p: dict) -> list[str]:
    """Canales del «sí» de una ficha; una ficha vieja sin eventos con «si» vale con los implícitos."""
    if p.get("consentimiento") != "si":
        return []
    if p.get("autorizacion_ultima"):
        return list(p.get("consentimiento_canales") or [])
    return list(modelo.CANALES_IMPLICITOS)


def reconciliar_consentimiento(db: Database, ids: Iterable[int] | None = None) -> list[int]:
    """Si el código viejo cambió `consentimiento` sin pasar por `autorizaciones`, inserta un evento «migrado» con el
    valor actual (la clave evita duplicarlo). Devuelve las fichas corregidas."""
    q: dict = {**ACTIVA, "$expr": {"$ne": [
        {"$ifNull": ["$consentimiento", "pendiente"]},
        {"$switch": {"branches": [{"case": {"$in": ["$autorizacion_ultima.estado", ["no", "revocada"]]}, "then": "no"},
                                  {"case": {"$eq": ["$autorizacion_ultima.estado", "si"]}, "then": "si"}],
                     "default": "pendiente"}}]}}
    if ids is not None:
        q["_id"] = {"$in": list(ids)}
    hechos = []
    for p in db.personas.find(q, {"consentimiento": 1, "consentimiento_fecha": 1, "autorizacion_ultima": 1}):
        estado = p.get("consentimiento") or "pendiente"
        if estado not in ESTADO_EFECTIVO:
            continue
        ultima = (p.get("autorizacion_ultima") or {}).get("id")
        clave = f"consent:{p['_id']}" if ultima is None else f"reconc:{p['_id']}:{ultima}:{estado}"
        ev = autorizacion_doc(db, p["_id"], estado, "migrado", canales_implicitos=estado == "si",
                              fecha_declarada=p.get("consentimiento_fecha"), usuario="migración", clave_migracion=clave)
        try:
            db.autorizaciones.insert_one(ev)
        except DuplicateKeyError:
            pass
        hechos.append(p["_id"])
    return hechos


def _eventos_de(db: Database, ids: list[int]) -> set[tuple]:
    return {(e["_id"], e["persona_id"]) for e in db.autorizaciones.find({"persona_id": {"$in": ids}}, {"persona_id": 1})}


def derivar(db: Database, ids: Iterable[int], reconciliar: bool = True, _intentos: int = 3) -> None:
    """Recalcula lo derivado de cada ficha: nacimiento aproximado, autorización (de sus eventos), abordaje (de sus
    acercamientos no anulados), claves fonéticas y completitud. Solo escribe lo que cambió.

    Si mientras tanto llegó (o se fue) un evento de autorización de una ficha, esa ficha se vuelve a derivar: así una
    lectura vieja no deja escrita una autorización vencida encima de otra más nueva (un «no» que se dijo mientras se
    derivaba)."""
    ids = list(dict.fromkeys(ids))
    if not ids:
        return
    if reconciliar:
        reconciliar_consentimiento(db, ids)
    eventos: dict[int, list] = {}
    leidos: set[tuple] = set()
    for e in db.autorizaciones.find({"persona_id": {"$in": ids}}):
        eventos.setdefault(e["persona_id"], []).append(e)
        leidos.add((e["_id"], e["persona_id"]))
    acerc: dict[int, list] = {}
    for a in db.acercamientos.find({"persona_id": {"$in": ids}, "anulado": {"$ne": True}}):
        acerc.setdefault(a["persona_id"], []).append(a)
    necesidades = ids_necesidad(db)
    ops = []
    for p in db.personas.find({"_id": {"$in": ids}, **ACTIVA}):
        nuevo: dict = {}
        if p.get("edad") is not None or not modelo.vacio(p.get("fecha_nacimiento")) or p.get("nac_aprox"):
            base = p.get("nac_base") or {}
            if p.get("edad") is not None and (not p.get("edad_ref") or (base and p["edad"] != base.get("edad"))):
                nuevo["edad_ref"] = modelo.hoy_local().isoformat()  # una edad nueva se toma como declarada hoy
            nuevo.update(modelo.calcular_nac({**p, **nuevo}))
        if p["_id"] in eventos:
            nuevo.update(modelo.consentimiento_vigente(eventos[p["_id"]]))
            if nuevo["consentimiento"] == "no":
                nuevo.update(sensibles={}, sensibles_autorizados=[])
        nuevo["nombre_fon"] = modelo.claves_foneticas(p.get("nombre"))
        nuevo["completitud"] = completitud({**p, **nuevo}, necesidades)
        cambios = {k: v for k, v in nuevo.items() if p.get(k) != v}
        if cambios:
            ops.append(UpdateOne({"_id": p["_id"], **ACTIVA}, {"$set": cambios}))
        consentimiento = nuevo.get("consentimiento", p.get("consentimiento"))
        ab = modelo.resumen_abordaje(acerc.get(p["_id"]), consentimiento)
        if ab != p.get("abordaje"):
            ops.append(UpdateOne({"_id": p["_id"], "abordaje_seq": p.get("abordaje_seq")}, {"$set": {"abordaje": ab}}))
    for k in range(0, len(ops), 1000):
        db.personas.bulk_write(ops[k:k + 1000], ordered=False)
    if _intentos > 1:
        cambiaron = {pid for _, pid in leidos ^ _eventos_de(db, ids)}
        if cambiaron:
            derivar(db, [i for i in ids if i in cambiaron], reconciliar=False, _intentos=_intentos - 1)


# ───────────────────────────── Unión de fichas (2.6) ─────────────────────────────

class FusionImposible(HTTPException):
    """La unión no se puede hacer (409): una ficha ya no está activa o tienen cédulas distintas."""

    def __init__(self, mensaje: str):
        super().__init__(409, mensaje)


class CedulasDistintas(FusionImposible):
    """Las dos fichas tienen (o acaban de recibir) cédulas distintas: son personas diferentes."""

    def __init__(self):
        super().__init__("Las dos fichas tienen cédulas distintas: son personas diferentes")


# Campos que se llenan desde el origen si el destino no los tiene, sin alternos (los que no tienen procedencia)
FUSION_SIMPLES = ("ficha", "personas_hogar", "observaciones", "tenencia_vivienda", "estrato", "regimen_salud",
                  "reunion_origen")
_LISTAS_UNION = ("fuentes", "listas", "etiquetas", "claves_tramites", "cedulas_anteriores")


def _lit(v: Any) -> dict:
    return {"$literal": v}


def _no_esta(lista: str, valor: str) -> dict:
    return {"$not": [{"$in": [valor, {"$ifNull": [lista, []]}]}]}


def _expr_telefonos_fusion(o_tels: list[dict]) -> dict:
    """Une los teléfonos del origen a los del destino: el orden del destino primero; en los repetidos se suman fuentes
    y fechas y gana el estado con `estado_en` más reciente."""
    lit = _lit(o_tels)
    cambios = {k: f"$$n.{k}" for k in modelo.CAMBIOS_TELEFONO}
    existentes = {"$map": {"input": "$$a", "as": "t", "in": {"$let": {
        "vars": {"n": {"$arrayElemAt": [{"$filter": {"input": lit, "as": "x",
                                                      "cond": {"$eq": ["$$x.numero", "$$t.numero"]}}}, 0]}},
        "in": {"$cond": [{"$eq": [{"$type": "$$n"}, "missing"]}, "$$t", {"$mergeObjects": [
            "$$t",
            {"$cond": [{"$gt": [{"$ifNull": ["$$n.estado_en", ""]}, {"$ifNull": ["$$t.estado_en", ""]}]}, cambios, {}]},
            {"fuentes": modelo._expr_union("$$t.fuentes", "$$n.fuentes"),
             "ultima_vez": {"$max": ["$$t.ultima_vez", "$$n.ultima_vez"]},
             "primera_vez": {"$min": ["$$t.primera_vez", "$$n.primera_vez"]}}]}]}}}}}
    agregados = {"$filter": {"input": lit, "as": "x", "cond": {"$not": [{"$in": [
        "$$x.numero", {"$map": {"input": "$$a", "as": "t", "in": "$$t.numero"}}]}]}}}
    return {"$let": {"vars": {"a": modelo.TELS_ACTUALES}, "in": {"$concatArrays": [existentes, agregados]}}}


def _pipeline_fusion(o: dict, origen: int, uid: Any) -> list[dict]:
    """Actualización (pipeline) del destino con los datos del origen `o` (pasos 3 de 2.6): parcial, sobre lo guardado,
    y que se puede repetir sin daño."""
    ts = ahora()
    fuente = f"fusion:{origen}"
    s: dict = {"actualizado_en": _lit(ts)}
    alt: list = []
    cedula_o = o.get("cedula") or o.get("cedula_en_traspaso")
    valores = {**o, "cedula": cedula_o}
    for campo in modelo.CAMPOS_PROCEDENCIA:
        v = valores.get(campo)
        if campo == "votacion" and not isinstance(v, dict):  # ficha vieja: el puesto y la mesa escritos
            v = modelo.armar_votacion(o.get("puesto_votacion"), o.get("mesa"), [], fuente="panel", eleccion=None,
                                      estado="por_confirmar", conservar_texto=True)
        if modelo.vacio(v):
            continue
        vacio = modelo.expr_vacio(campo)
        s[campo] = {"$cond": [vacio, _lit(v), f"${campo}"]}
        if campo != "cedula":
            alt.append({"$cond": [{"$and": [{"$not": [vacio]}, {"$ne": [modelo.expr_comparable(campo),
                                                                         _lit(modelo.comparable(campo, v))]}]},
                                  [{"campo": campo, "valor": _lit(modelo.comparable(campo, v)), "fuente": fuente,
                                    "ts": ts, "uid": uid}], []]})
    if "cedula" in s:
        s["cedula_origen"] = {"$cond": [modelo.expr_vacio("cedula"), _lit(o.get("cedula_origen")), "$cedula_origen"]}
        s["cedula_verificada"] = {"$cond": [modelo.expr_vacio("cedula"), _lit(bool(o.get("cedula_verificada"))),
                                            {"$or": ["$cedula_verificada", {"$and": [
                                                {"$eq": ["$cedula", _lit(cedula_o)]}, _lit(bool(o.get("cedula_verificada")))]}]}]}
    if o.get("edad") is not None:
        s["edad_ref"] = {"$cond": [modelo.expr_vacio("edad"), _lit(o.get("edad_ref")), "$edad_ref"]}
    if o.get("jefe_hogar") is not None:
        s["jefe_hogar"] = {"$ifNull": ["$jefe_hogar", _lit(o["jefe_hogar"])]}
    for campo in FUSION_SIMPLES:
        if not modelo.vacio(o.get(campo)):
            s[campo] = {"$cond": [modelo.expr_vacio(campo), _lit(o[campo]), f"${campo}"]}
    # La ubicación pasa en bloque (no mezclar el barrio de una con las coordenadas de la otra)
    rango_o = _rango_ubicacion(o)
    geo_o = {k: o.get(k, PERSONA_VACIA.get(k)) for k in GEO}
    geo_o["punto"] = modelo.punto(o.get("lat"), o.get("lon"))
    for campo in GEO:
        s[campo] = {"$cond": [{"$gt": [rango_o, _EXPR_RANGO]}, _lit(geo_o[campo]), f"${campo}"]}
    # Listas sin repetir
    claves = [c for c in [o.get("clave_tramites"), *(o.get("claves_tramites") or [])] if c]
    listas = {k: list(o.get(k) or []) for k in _LISTAS_UNION}
    listas["claves_tramites"] = list(dict.fromkeys(claves))
    for k, vals in listas.items():
        if vals:
            s[k] = modelo._expr_union(f"${k}", _lit(vals))
    tramites = o.get("tramites") or []
    con_id = [t for t in tramites if t.get("id_externo")]
    sin_id = [t for t in tramites if not t.get("id_externo")]
    if tramites:
        actuales = {"$ifNull": ["$tramites", []]}
        s["tramites"] = {"$concatArrays": [
            actuales,
            {"$filter": {"input": _lit(con_id), "as": "x", "cond": {"$not": [{"$in": [
                "$$x.id_externo", {"$map": {"input": actuales, "as": "t", "in": "$$t.id_externo"}}]}]}}},
            {"$filter": {"input": _lit(sin_id), "as": "x", "cond": {"$not": [{"$in": ["$$x", actuales]}]}}}]}
    for k, llave in (("notas", "id"), ("asistencias", "reunion_id")):
        if o.get(k):
            actuales = {"$ifNull": [f"${k}", []]}
            s[k] = {"$concatArrays": [actuales, {"$filter": {"input": _lit(o[k]), "as": "x", "cond": {"$not": [{"$in": [
                f"$$x.{llave}", {"$map": {"input": actuales, "as": "t", "in": f"$$t.{llave}"}}]}]}}}]}
    if o.get("origen"):
        actuales = {"$ifNull": ["$origen", []]}
        par = lambda v: {"f": f"{v}.fuente", "c": f"{v}.clave"}  # noqa: E731
        s["origen"] = {"$concatArrays": [actuales, {"$filter": {"input": _lit(o["origen"]), "as": "x", "cond": {
            "$not": [{"$in": [par("$$x"), {"$map": {"input": actuales, "as": "t", "in": par("$$t")}}]}]}}}]}
    for k in ("procedencia", "extra", "no_disponible", "sensibles", "avance"):
        if o.get(k):
            s[k] = {"$mergeObjects": [_lit(o[k]), {"$ifNull": [f"${k}", {}]}]}
    if o.get("requiere_actualizacion"):
        s["requiere_actualizacion"] = {"$ifNull": ["$requiere_actualizacion", _lit(o["requiere_actualizacion"])]}
    for k in ("reclamo_en_tramite", "lider"):
        if o.get(k):
            s[k] = True
    if o.get("ultimo_contacto"):
        s["ultimo_contacto"] = {"$max": ["$ultimo_contacto", _lit(o["ultimo_contacto"])]}
    if o.get("creado_en"):
        mas_viejo = {"$lt": [_lit(o["creado_en"]), {"$ifNull": ["$creado_en", "9999"]}]}
        s["creado_por"] = {"$cond": [mas_viejo, _lit(o.get("creado_por")), "$creado_por"]}
        s["creado_en"] = {"$cond": [mas_viejo, _lit(o["creado_en"]), "$creado_en"]}
    s["telefonos"] = _expr_telefonos_fusion([{**modelo.telefono_nuevo(t.get("numero")), **t}
                                             for t in modelo.telefonos_de(o) if t.get("numero") not in (None, "")])
    o_alt = [a for a in o.get("alternos") or [] if isinstance(a, dict)]
    s["__alt"] = {"$concatArrays": [_lit(o_alt), *alt]}
    existentes = {"$map": {"input": {"$ifNull": ["$alternos", []]}, "as": "x", "in": {"c": "$$x.campo", "v": "$$x.valor"}}}
    return [modelo.ETAPA_RECONCILIAR_TELEFONOS, {"$set": s},
            {"$set": {"alternos": {"$slice": [{"$concatArrays": [{"$ifNull": ["$alternos", []]}, {"$filter": {
                "input": "$__alt", "as": "y",
                "cond": {"$not": [{"$in": [{"c": "$$y.campo", "v": "$$y.valor"}, existentes]}]}}}]}, -100]}}},
            {"$unset": "__alt"}, modelo.ETAPA_DERIVAR_TELEFONOS, modelo.ETAPA_DERIVAR_VOTACION]


def _consentimiento_unido(d: dict, o: dict) -> tuple[str, list[str], bool, str | None]:
    """(estado, canales, habilita, fecha) que resulta de unir dos fichas: «no» gana; con dos «si», los canales comunes;
    con uno, los suyos."""
    a, b = ESTADO_EFECTIVO.get(d.get("consentimiento")), ESTADO_EFECTIVO.get(o.get("consentimiento"))
    habilita = bool(d.get("contacto_habilitado") or o.get("contacto_habilitado"))
    if "no" in (a, b):
        fecha = d.get("consentimiento_fecha") if a == "no" else o.get("consentimiento_fecha")
        return "no", [], False, fecha
    if a == b == "si":
        cb = _canales_vigentes(o)
        return "si", [c for c in _canales_vigentes(d) if c in cb], habilita, d.get("consentimiento_fecha")
    if "si" in (a, b):
        x = d if a == "si" else o
        return "si", _canales_vigentes(x), bool(x.get("contacto_habilitado")) or x.get("autorizacion_ultima") is None, \
            x.get("consentimiento_fecha")
    return "pendiente", [], False, None


def _reapuntar_coincidencias(db: Database, origen: int, destino: int, marca: dict) -> None:
    par = {"$or": [{"persona_id": origen, "candidato_id": destino}, {"persona_id": destino, "candidato_id": origen}]}
    db.coincidencias.update_many({**par, "estado": "pendiente"}, {"$set": {"estado": "aceptada", **marca}})
    cerrar = {"$set": {"estado": "cerrada", "resuelto_por": "sistema", "resuelto_en": ahora()}}
    for c in db.coincidencias.find({"estado": "pendiente", "$or": [{"persona_id": origen}, {"candidato_id": origen}]}):
        a = destino if c["persona_id"] == origen else c["persona_id"]
        b = destino if c["candidato_id"] == origen else c["candidato_id"]
        if a == b:
            db.coincidencias.update_one({"_id": c["_id"]}, cerrar)
            continue
        try:
            db.coincidencias.update_one({"_id": c["_id"], "estado": "pendiente"},
                                        {"$set": {"persona_id": a, "candidato_id": b}})
        except DuplicateKeyError:  # ese par ya existía con la otra ficha
            db.coincidencias.update_one({"_id": c["_id"]}, cerrar)


LIGADOS = ("acercamientos", "autorizaciones", "solicitudes", "conflictos_cedula")


def _mover_ligados(db: Database, origen: int, destino: int) -> int:
    """Paso 4 de 2.6: lo ligado al origen pasa al destino. Devuelve cuántos documentos movió."""
    return sum(db[col].update_many({"persona_id": origen}, {"$set": {"persona_id": destino}}).modified_count
               for col in LIGADOS)


def fin_de_cadena(db: Database, pid: int) -> int | None:
    """La ficha activa en la que terminó la cadena de uniones de `pid` (None si se suprimió o hay un ciclo)."""
    destino, vistos = pid, set()
    while True:
        if destino in vistos:
            return None
        vistos.add(destino)
        d = db.personas.find_one({"_id": destino}, {"fusionada_en": 1, "eliminado": 1})
        if d is None or d.get("eliminado"):
            return None
        if d.get("fusionada_en") is None:
            return destino
        destino = d["fusionada_en"]


def _union_terminada(o: dict) -> bool:
    return "cedula_en_traspaso" not in o and o.get("nombre") == "FUSIONADA"


def recoger_tardios(db: Database, pid: int) -> int | None:
    """Una escritura que pasó la comprobación de ficha activa antes de una unión y llegó después (una autorización, un
    acercamiento) quedó ligada al origen ya vacío: pasa a la ficha activa en que terminó la cadena, que se vuelve a
    derivar. Devuelve esa ficha, o None si `pid` sigue activa o su unión todavía no termina (la unión, al terminar,
    mueve lo que haya llegado)."""
    o = db.personas.find_one({"_id": pid}, {"fusionada_en": 1, "eliminado": 1, "nombre": 1, "cedula_en_traspaso": 1})
    if o is None or o.get("eliminado") or o.get("fusionada_en") is None or not _union_terminada(o):
        return None
    fin = fin_de_cadena(db, pid)
    if fin is not None and _mover_ligados(db, pid, fin):
        derivar(db, [fin], reconciliar=False)
    return fin


def _lado(ficha: dict, eventos: list[dict]) -> dict:
    """Autorización de un lado de la unión: la de sus eventos o, si no tiene (ficha vieja), la de la ficha. Un «no» en
    cualquiera de los dos manda."""
    if not eventos:
        return ficha
    vig = modelo.consentimiento_vigente(eventos)
    if vig["consentimiento"] != "no" and ESTADO_EFECTIVO.get(ficha.get("consentimiento")) == "no":
        return ficha
    return {**ficha, **vig}


def _unir_autorizaciones(db: Database, destino: int, o: dict, quien: Any, del_origen: set) -> str:
    """Paso 5 de 2.6, sobre los eventos releídos después de moverlos (no sobre lo que se leyó al empezar la unión: un
    «no» que el destino dijo mientras tanto cuenta). Cada lado se mira por separado: el destino con sus eventos y su
    ficha de ahora, el origen con los eventos que traía y su ficha. «No» gana; si el resultado difiere de lo que dicen
    los eventos unidos, un evento «fusion» que anota los que combinó (`considerados`): un «no» que no vio le gana
    (`modelo.consentimiento_vigente`). Si al escribirlo ya llegó uno, queda además un «no» final. Devuelve el estado."""
    uid = _uid_de(quien)
    eventos = list(db.autorizaciones.find({"persona_id": destino}))
    d = db.personas.find_one({"_id": destino}) or {}
    lado_d = _lado(d, [e for e in eventos if e["_id"] not in del_origen])
    lado_o = _lado(o, [e for e in eventos if e["_id"] in del_origen])
    estado, canales, habilita, fecha = _consentimiento_unido(lado_d, lado_o)
    vig = modelo.consentimiento_vigente(eventos)
    vistos = [e["_id"] for e in eventos]

    def evento(estado_: str, canales_: list[str], habilita_: bool, fecha_: str | None, considerados: list,
               nota: str) -> None:
        db.autorizaciones.insert_one(autorizacion_doc(
            db, destino, estado_, "fusion", canales=canales_, habilita=habilita_, fecha_declarada=fecha_,
            mayor_declarado=bool(d.get("mayor_declarado") or o.get("mayor_declarado")), uid=uid,
            usuario=_nombre_de(quien), rol=getattr(quien, "rol", None) or ("admin" if uid == 0 else None),
            nota=nota, considerados=considerados))

    if (estado, sorted(canales)) != (vig["consentimiento"], sorted(vig["consentimiento_canales"])) \
            and not (estado == "pendiente" and vig["consentimiento"] == "pendiente"):
        evento(estado, canales, habilita, fecha, vistos, f"Unión con la ficha {o['_id']}")
    if estado != "no":
        despues = list(db.autorizaciones.find({"persona_id": destino, "_id": {"$nin": vistos},
                                               "estado": {"$in": ["no", "revocada"]}}))
        if despues:
            estado = "no"
            evento("no", [], False, None, [*vistos, *(e["_id"] for e in despues)],
                   f"Unión con la ficha {o['_id']}: dijo «no» mientras se unían")
    if estado == "no":
        db.personas.update_one({"_id": destino}, {"$set": {"sensibles": {}, "sensibles_autorizados": []}})
    return estado


def _unir_en(db: Database, destino: int, o: dict, quien: Any, d_antes: dict | None = None) -> None:
    """Pasos 3 a 7 de la unión: se pueden repetir sin daño (la reparación al arrancar los repite). `d_antes` queda por
    compatibilidad: la autorización se calcula con el destino releído (`_unir_autorizaciones`)."""
    origen = o["_id"]
    uid = _uid_de(quien)
    # La cédula manda (principio 2): el destino se escribe solo si su cédula sigue siendo compatible con la del origen.
    # Quien leyó el destino sin cédula pudo perder la carrera con alguien que se la llenó con otra (PATCH del
    # planillero entre la lectura y esta escritura): entonces son dos personas y la unión no se hace
    cedula_o = o.get("cedula") or o.get("cedula_en_traspaso")
    filtro: dict = {"_id": destino, **ACTIVA}
    if cedula_o:
        filtro["cedula"] = {"$in": [None, "", cedula_o]}
    try:
        r = db.personas.update_one(filtro, _pipeline_fusion(o, origen, uid))
    except DuplicateKeyError:
        # Otra ficha tomó la cédula del origen mientras estaba en traspaso (no pasó por `cedula_ocupada`): son dos
        # fichas con la misma cédula y el destino no la puede recibir. Nada se escribió: no se une
        raise CedulasDistintas() from None
    if r.matched_count == 0:
        if cedula_o and db.personas.count_documents({"_id": destino, **ACTIVA}, limit=1):
            raise CedulasDistintas()
        raise FusionImposible("La ficha de destino ya se unió o se suprimió")
    del_origen = {e["_id"] for e in db.autorizaciones.find({"persona_id": origen}, {"_id": 1})}
    _mover_ligados(db, origen, destino)
    _reapuntar_coincidencias(db, origen, destino, {"resuelto_por": _nombre_de(quien), "resuelto_en": ahora()})
    _unir_autorizaciones(db, destino, o, quien, del_origen)
    derivar(db, [destino], reconciliar=False)
    from .pipeline.importar import georreferenciar  # aquí: el pipeline usa este módulo
    georreferenciar(db, [destino])
    cerrar_coincidencias_imposibles(db, [destino])
    db.personas.replace_one({"_id": origen, "fusionada_en": destino},
                            {**persona_vacia(), "_id": origen, "nombre": "FUSIONADA", "fusionada_en": destino,
                             "eliminado": False, "actualizado_en": ahora()})
    db.personas.update_many({"fusionada_en": origen}, {"$set": {"fusionada_en": destino}})
    # Lo que llegó al origen después de moverlo (pasó la comprobación de ficha activa antes de la unión): también al
    # destino. Lo que llegue desde ahora lo mueve quien lo escribe (`recoger_tardios`)
    if _mover_ligados(db, origen, destino):
        derivar(db, [destino], reconciliar=False)


def _devolver_origen(db: Database, o: dict, destino: int, quien: Any) -> None:
    """La unión no se hace: el origen vuelve a quedar activo con su cédula. Si otra ficha la tomó mientras estaba en
    traspaso, vuelve sin ella y la cédula queda como conflicto a la vista de A (Calidad → Conflictos de cédula:
    «Reportar duplicado» con la ficha que la tiene, o «Aplicar» si se libera)."""
    pid = o["_id"]
    cedula = o.get("cedula") or o.get("cedula_en_traspaso")
    q = {"_id": pid, "fusionada_en": destino}
    try:
        db.personas.update_one(q, {"$set": {"fusionada_en": None, "cedula": cedula},
                                   "$unset": {"cedula_en_traspaso": ""}})
        return
    except DuplicateKeyError:
        pass
    r = db.personas.update_one(q, {"$set": {"fusionada_en": None, "cedula": None}, "$unset": {"cedula_en_traspaso": ""}})
    if not r.matched_count:
        return
    clave = hashlib.sha1(f"dictada|{cedula}|{pid}|fusion|{destino}".encode()).hexdigest()
    db.conflictos_cedula.update_one({"clave": clave}, {"$setOnInsert": {
        "_id": siguiente_id(db, "conflictos_cedula"), "clave": clave, "cedula": cedula, "persona_id": pid,
        "motivo": "dictada", "fuente": "fusion", "importacion_id": None,
        "registro": {"nombre": o.get("nombre"), "cedula": cedula, "tipo_documento": o.get("tipo_documento"),
                     "fuente": "fusion", "union_con": destino},
        "puntaje_nombre": None, "estado": "pendiente", "creado_por": _nombre_de(quien), "creado_en": ahora(),
        "resuelto_por": None, "resuelto_en": None, "resolucion": None}}, upsert=True)
    auditar(db, quien, "conflicto_cedula", "persona", pid, {"cedula": cedula, "motivo": "union_sin_cedula",
                                                            "union_con": destino})


def fusionar(db: Database, destino: int, origen: int, quien: Any, ip: str | None = None) -> None:
    """Une `origen` en `destino` (2.6): completa vacíos (lo distinto va a `alternos`), junta trámites, teléfonos,
    listas, etiquetas, reuniones, notas y fuentes, reasigna lo ligado y combina la autorización («no» gana).

    El origen se marca primero como unido (una sola operación) y queda solo como enlace, sin datos personales. Sin
    transacciones: si se corta a mitad, la reparación al arrancar repite los pasos que faltan. 409 si una de las dos
    ya no está activa o tienen cédulas distintas: dos cédulas distintas nunca se unen."""
    if destino == origen:
        return
    reconciliar_consentimiento(db, [destino, origen])
    d = db.personas.find_one({"_id": destino, **ACTIVA})
    if d is None:
        raise FusionImposible("La ficha de destino ya se unió o se suprimió")
    filtro: dict = {"_id": origen, **ACTIVA}
    if d.get("cedula"):
        filtro["cedula"] = {"$in": [None, d["cedula"]]}
    o = db.personas.find_one_and_update(filtro, [{"$set": {
        "fusionada_en": destino, "cedula_en_traspaso": "$cedula", "cedula": None, "clave_tramites": None,
        "claves_tramites": {"$concatArrays": [{"$ifNull": ["$claves_tramites", []]}, {"$cond": [
            {"$and": [{"$ne": [{"$ifNull": ["$clave_tramites", None]}, None]},
                      _no_esta("$claves_tramites", "$clave_tramites")]}, ["$clave_tramites"], []]}]}}}],
        return_document=ReturnDocument.BEFORE)
    if o is None:
        otro = db.personas.find_one({"_id": origen}, {"cedula": 1, "fusionada_en": 1, "eliminado": 1})
        if otro and not otro.get("eliminado") and otro.get("fusionada_en") is None:
            raise FusionImposible("Las dos fichas tienen cédulas distintas: son personas diferentes")
        raise FusionImposible("La ficha ya se unió o se suprimió")
    try:
        _unir_en(db, destino, o, quien, d)
    except FusionImposible:
        # El destino dejó de estar activo, o recibió otra cédula, entre la lectura y la escritura: el origen vuelve a
        # quedar como estaba (con su cédula, si nadie la tomó) y no se une nada
        _devolver_origen(db, o, destino, quien)
        raise
    auditar(db, quien, "fusionar", "persona", destino, {"origen": origen}, ip)


def reparar_fusiones(db: Database) -> int:
    """Orígenes de uniones cortadas a mitad (todavía con datos o con `cedula_en_traspaso`): repite los pasos 3 a 7 sobre
    la ficha activa en la que terminó la cadena de uniones. Corre en cada arranque y nunca lo aborta: un error en una
    ficha queda en el registro y esa ficha se reintenta en el próximo arranque."""
    n = 0
    for o in db.personas.find({"fusionada_en": {"$ne": None}, "eliminado": {"$ne": True},
                               "$or": [{"cedula_en_traspaso": {"$exists": True}}, {"nombre": {"$ne": "FUSIONADA"}}]}):
        try:
            destino = fin_de_cadena(db, o["fusionada_en"])
            if destino is None:
                continue
            try:
                _unir_en(db, destino, o, "sistema")
                n += 1
            except CedulasDistintas:
                # El destino recibió otra cédula, u otra ficha tomó la del origen, mientras la unión estaba cortada:
                # son dos personas. El origen vuelve a quedar activo (con su cédula, o sin ella y con un conflicto)
                _devolver_origen(db, o, o["fusionada_en"], "sistema")
            except FusionImposible:
                continue
        except Exception as e:  # noqa: BLE001 (una ficha no detiene el arranque del panel)
            log.warning("Reparación de uniones: la ficha %s no se pudo reparar (se reintenta al arrancar): %s",
                        o["_id"], e)
    return n


def cerrar_coincidencias_imposibles(db: Database, ids: Iterable[int] | None = None) -> int:
    """Cierra las coincidencias pendientes que ya no se pueden aceptar: una de las dos fichas ya no está activa (se
    unió con otra o se suprimió) o las dos tienen cédulas distintas. Quedan con estado «cerrada» (no se borran, así
    una importación no las vuelve a proponer)."""
    q: dict = {"estado": "pendiente"}
    if ids is not None:
        ids = list(ids)
        q["$or"] = [{"persona_id": {"$in": ids}}, {"candidato_id": {"$in": ids}}]
    pendientes = list(db.coincidencias.find(q, {"persona_id": 1, "candidato_id": 1}))
    if not pendientes:
        return 0
    pids = list({c["persona_id"] for c in pendientes} | {c["candidato_id"] for c in pendientes})
    cedulas = {p["_id"]: p.get("cedula") for p in db.personas.find({"_id": {"$in": pids}, **ACTIVA}, {"cedula": 1})}

    def imposible(c: dict) -> bool:
        if c["persona_id"] not in cedulas or c["candidato_id"] not in cedulas:
            return True
        a, b = cedulas[c["persona_id"]], cedulas[c["candidato_id"]]
        return bool(a and b and a != b)

    cerrar = [c["_id"] for c in pendientes if imposible(c)]
    if cerrar:
        db.coincidencias.update_many({"_id": {"$in": cerrar}, "estado": "pendiente"},
                                     {"$set": {"estado": "cerrada", "resuelto_por": "sistema", "resuelto_en": ahora()}})
    return len(cerrar)


# ───────────────────────────── Supresión (Ley 1581) ─────────────────────────────

def clave_supresion(db: Database) -> bytes:
    """Clave secreta (aleatoria, creada la primera vez) de las huellas de personas suprimidas."""
    m = db.meta.find_one_and_update({"_id": "clave_supresion"}, {"$setOnInsert": {"valor": secrets.token_hex(32)}},
                                    upsert=True, return_document=ReturnDocument.AFTER)
    return bytes.fromhex(m["valor"])


def _normalizar_huella(tipo: str, valor: Any) -> str:
    if tipo == "cedula":
        return tx.cedula(valor) or str(valor).strip()
    if tipo == "clave":
        return tx.nombre_norm(valor)
    if tipo in ("ficha_nombre", "nombre_tel"):  # (ficha o teléfono, nombre): identifican a la persona, no al nombre
        dato, nombre = valor
        dato, nombre = str(dato or "").strip(), tx.nombre_norm(nombre)
        return f"{dato}|{nombre}" if dato and nombre else ""
    return str(valor).strip()


def huella(clave: bytes, tipo: str, valor: Any) -> str | None:
    """HMAC-SHA256 de un dato de identidad ya normalizado: cédula, ID o contenido de un trámite, ficha+nombre o
    teléfono+nombre. Nunca el nombre solo, que bloquearía a los homónimos. None si está vacío."""
    if valor in (None, "", ()):
        return None
    v = _normalizar_huella(tipo, valor)
    return hmac.new(clave, f"{tipo}:{v}".encode(), hashlib.sha256).hexdigest() if v else None


def pares_identidad(nombres: Iterable[str], fichas: Iterable[str], telefonos: Iterable[str]) -> list[tuple[str, Any]]:
    """Pares (tipo, valor) que identifican a una persona por ficha+nombre y teléfono+nombre."""
    nombres = {n for n in nombres if n}
    return [("ficha_nombre", (f, n)) for f in set(fichas) if f for n in nombres] + \
           [("nombre_tel", (t, n)) for t in set(telefonos) if t for n in nombres]


def registrar_huellas(db: Database, pares: Iterable[tuple[str, Any]], clave: bytes | None = None) -> set[str]:
    """Guarda en `suprimidos` las huellas de los pares (tipo, valor) y las devuelve."""
    clave = clave or clave_supresion(db)
    hs = {h for tipo, v in pares if (h := huella(clave, tipo, v))}
    if hs:
        db.suprimidos.bulk_write([UpdateOne({"_id": h}, {"$setOnInsert": {"creado_en": ahora()}}, upsert=True) for h in hs],
                                 ordered=False)
    return hs


def grupo_fusion(db: Database, pid: int) -> list[int]:
    """La ficha y todas las unidas con ella: sube por `fusionada_en` hasta la raíz y baja por todas sus ramas."""
    raiz, vistos = pid, {pid}
    while True:
        p = db.personas.find_one({"_id": raiz}, {"fusionada_en": 1})
        if not p or not p.get("fusionada_en") or p["fusionada_en"] in vistos:
            break
        raiz = p["fusionada_en"]
        vistos.add(raiz)
    ids, frontera = set(vistos), [raiz]
    while frontera:
        hijos = [x["_id"] for x in db.personas.find({"fusionada_en": {"$in": frontera}}, {"_id": 1})]
        frontera = [h for h in hijos if h not in ids]
        ids.update(frontera)
    return sorted(ids)


FUENTES_CON_CEDULA = ("cedulas", "planilla")


def cedula_en_traspaso(db: Database, c: str | None) -> bool:
    """¿Una unión en curso (o cortada, hasta que la reparación la termine) está moviendo esa cédula? Mientras tanto
    ninguna ficha activa la muestra, pero está ocupada: un alta o un cambio con ella chocaría al escribir el destino."""
    return bool(c) and db.personas.count_documents(
        {"cedula_en_traspaso": c, "fusionada_en": {"$ne": None}, "eliminado": {"$ne": True}}, limit=1) > 0


def cedulas_de(p: dict) -> set[str]:
    """Todas las cédulas de una ficha: la actual, las anteriores, la que está en traspaso y la de cada registro de una
    fuente con cédula."""
    out = {p.get("cedula"), p.get("cedula_en_traspaso"), *(p.get("cedulas_anteriores") or [])}
    for o in p.get("origen") or []:
        out.add(o.get("cedula") or (o.get("clave") if o.get("fuente") == "cedulas" else None))
    return {c for c in out if c}


def limpiar_ligados(db: Database, ids: list[int], cedulas: Iterable[str] = ()) -> None:
    """Lo ligado a fichas suprimidas: borra coincidencias, conflictos e idempotencia; anonimiza acercamientos y
    autorizaciones (conservan uid, canal, resultado, efectivo y fecha para los indicadores) y deja las solicitudes
    como constancia, sin su texto."""
    cedulas = [c for c in cedulas if c]
    db.coincidencias.delete_many({"$or": [{"persona_id": {"$in": ids}}, {"candidato_id": {"$in": ids}}]})
    db.conflictos_cedula.delete_many({"$or": [{"persona_id": {"$in": ids}}, {"cedula": {"$in": cedulas}}]})
    db.idempotencia.delete_many({"persona_id": {"$in": ids}})
    db.acercamientos.update_many({"persona_id": {"$in": ids}}, {"$set": {
        "persona_id": None, "telefono": None, "nota": None, "datos_dictados": [], "suprimido": True}})
    db.autorizaciones.update_many({"persona_id": {"$in": ids}}, {"$set": {
        "persona_id": None, "evidencia": None, "evidencia_fila": None, "nota": None, "suprimido": True}})
    db.solicitudes.update_many({"persona_id": {"$in": ids}, "suprimido": {"$ne": True}},
                               {"$set": {"descripcion": None, "respuesta": None, "suprimido": True}})


def suprimir(db: Database, pid: int, quien: Any, ip: str | None = None) -> list[int]:
    """Borra los datos personales de la ficha y de todas las unidas con ella, limpia su rastro en la auditoría y en lo
    ligado (2.6) y deja las huellas (HMAC, sin datos en claro) para que una importación no la vuelva a crear."""
    ids = grupo_fusion(db, pid)
    pares: set[tuple[str, Any]] = set()
    cedulas: set[str] = set()
    for p in db.personas.find({"_id": {"$in": ids}}):
        cedulas |= cedulas_de(p)
        tramites = p.get("tramites") or []
        pares.update(("tramite", t.get("id_externo")) for t in tramites)
        pares.update(("contenido", t.get("clave")) for t in tramites if not t.get("id_externo"))
        nombres = [p.get("nombre_norm"), p.get("clave_tramites"), *(p.get("claves_tramites") or [])]
        fichas = [p.get("ficha"), *(t.get("ficha") for t in tramites)]
        tels = [p.get("telefono"), p.get("telefono2"), *(t.get("numero") for t in p.get("telefonos") or []),
                *(x for t in tramites for x in (t.get("telefono") or "").split(";"))]
        pares.update(pares_identidad(nombres, fichas, tels))
    pares.update(("cedula", c) for c in cedulas)
    registrar_huellas(db, pares)
    for i in ids:
        db.personas.replace_one({"_id": i}, {**persona_vacia(), "_id": i, "nombre": "SUPRIMIDO", "nombre_norm": "",
                                             "eliminado": True, "actualizado_en": ahora()})
    limpiar_ligados(db, ids, cedulas)
    db.auditoria.update_many({"entidad": "persona", "entidad_id": {"$in": ids}}, {"$set": {"detalle": None}})
    auditar(db, quien, "suprimir", "persona", pid, {"fichas": len(ids)}, ip)
    return ids
