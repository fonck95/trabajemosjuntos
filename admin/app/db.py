"""MongoDB: conexión, índices, nomenclátor inicial y operaciones comunes sobre personas.

Colecciones (todas con `_id` entero para que las direcciones del panel sean cortas, salvo sesiones y auditoría):

* `personas`: una por habitante. Lleva adentro sus trámites, notas, listas, etiquetas, asistencias y el registro
  original de cada fuente, así una ficha se lee de una sola vez.
* `lugares`, `reuniones`, `coincidencias`, `etiquetas`, `campos`, `importaciones`.
* `sesiones` e `intentos` (con caducidad automática), `auditoria`, `contadores`.
* `meta` (marcas y la clave secreta de las huellas) y `suprimidos` (huellas HMAC de quienes pidieron la supresión,
  sin ningún dato en claro, para que una importación no los vuelva a crear).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument, UpdateOne
from pymongo.database import Database

from .pipeline import texto as tx
from .pipeline.direcciones import Lugar

GAZETTEER = Path(__file__).resolve().parents[1] / "geo" / "gazetteer.json"
ACTIVA = {"eliminado": {"$ne": True}, "fusionada_en": None}

ETIQUETAS_INICIALES = [
    ("Vivienda", "necesidad"), ("Agua potable", "necesidad"), ("Saneamiento", "necesidad"), ("Salud", "necesidad"),
    ("Empleo", "necesidad"), ("Educación", "necesidad"), ("Vías", "necesidad"), ("Energía", "necesidad"),
    ("Conectividad", "necesidad"), ("Seguridad", "necesidad"), ("Adulto mayor", "necesidad"),
    ("Discapacidad", "necesidad"), ("Primera infancia", "necesidad"), ("Proyecto productivo", "necesidad"),
    ("Víctima del conflicto", "interes"), ("Campesino", "interes"), ("Pescador", "interes"), ("Joven", "interes"),
    ("Mujer cabeza de hogar", "interes"), ("Líder comunitario", "rol"), ("JAC", "rol"), ("Voluntario", "rol"),
]

# Campos de la ficha con su valor inicial: así toda persona tiene la misma forma
PERSONA_VACIA: dict[str, Any] = {
    "nombre": None, "nombre_norm": None, "cedula": None, "sexo": None, "edad": None, "fecha_nacimiento": None,
    "telefono": None, "telefono2": None, "correo": None, "direccion": None, "direccion_norm": None, "lugar_id": None,
    "lugar_texto": None, "zona": None, "lat": None, "lon": None, "geo_precision": None, "geo_manual": False,
    "ficha": None, "puesto_votacion": None, "mesa": None, "ocupacion": None, "nivel_educativo": None,
    "personas_hogar": None, "lider": False, "consentimiento": "pendiente", "consentimiento_fecha": None,
    "observaciones": None, "extra": {}, "fuentes": [], "clave_tramites": None, "completitud": 0, "ultimo_contacto": None,
    "fusionada_en": None, "eliminado": False, "listas": [], "etiquetas": [], "tramites": [], "notas": [], "origen": [],
    "asistencias": [], "claves_tramites": [], "reunion_origen": None,
}
# geo_manual: False (automática), "lugar" (barrio o vereda elegido a mano: la persona sigue el punto de ese lugar) o
# "punto" (puesto a mano en el mapa: no se mueve). Las fichas viejas con True se tratan como "punto".
PUNTO_MANUAL = (True, "punto")
# Campos de la ubicación: al unir fichas se toman en bloque de una sola de ellas
GEO = ("lat", "lon", "geo_precision", "lugar_id", "lugar_texto", "zona", "direccion_norm", "geo_manual")


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


def inicializar(db: Database) -> None:
    p = db.personas
    p.create_index("nombre_norm")
    p.create_index("cedula", unique=True, partialFilterExpression={"cedula": {"$type": "string"}})
    p.create_index("clave_tramites", unique=True, partialFilterExpression={"clave_tramites": {"$type": "string"}})
    for campo in ("telefono", "lugar_id", "asistencias.reunion_id", "tramites.id_externo", "etiquetas", "listas",
                  "fuentes", "completitud"):
        p.create_index(campo)
    p.create_index([("eliminado", ASCENDING), ("fusionada_en", ASCENDING)])
    db.lugares.create_index([("nombre", ASCENDING), ("tipo", ASCENDING)], unique=True)
    db.coincidencias.create_index([("persona_id", ASCENDING), ("candidato_id", ASCENDING)], unique=True)
    db.coincidencias.create_index("estado")
    db.reuniones.create_index([("fecha", DESCENDING)])
    db.etiquetas.create_index("nombre", unique=True)
    db.campos.create_index("clave", unique=True)
    db.auditoria.create_index([("entidad", ASCENDING), ("entidad_id", ASCENDING)])
    db.sesiones.create_index("expira", expireAfterSeconds=0)
    db.intentos.create_index("ts", expireAfterSeconds=24 * 3600)
    db.intentos.create_index([("ip", ASCENDING), ("ts", ASCENDING)])
    # El catálogo inicial se siembra una sola vez (en una base nueva): si el administrador lo borra, no vuelve
    if db.meta.find_one({"_id": "etiquetas_sembradas"}) is None:
        if db.etiquetas.count_documents({}) == 0 and db.contadores.find_one({"_id": "etiquetas"}) is None:
            primero = siguiente_id(db, "etiquetas", len(ETIQUETAS_INICIALES))
            db.etiquetas.insert_many([{"_id": primero + i, "nombre": n, "grupo": g, "orden": i}
                                      for i, (n, g) in enumerate(ETIQUETAS_INICIALES)])
        db.meta.update_one({"_id": "etiquetas_sembradas"}, {"$set": {"ts": ahora()}}, upsert=True)
    # Fichas viejas: geo_manual=True por un barrio o vereda elegido a mano (el punto puesto en el mapa es «manual»)
    p.update_many({"geo_manual": True, "geo_precision": {"$ne": "manual"}, "lugar_id": {"$ne": None}},
                  {"$set": {"geo_manual": "lugar"}})
    sembrar_lugares(db)


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


def lugares(db: Database) -> list[Lugar]:
    return [Lugar(l["_id"], l["nombre"], l["tipo"], l["zona"], l.get("lat"), l.get("lon"), tuple(l.get("alias") or ()),
                  l.get("padre")) for l in db.lugares.find({}, {"geom": 0})]


def auditar(db: Database, usuario: str | None, accion: str, entidad: str | None = None,
            entidad_id: int | None = None, detalle: Any = None, ip: str | None = None) -> None:
    db.auditoria.insert_one({
        "ts": ahora(), "usuario": usuario, "accion": accion, "entidad": entidad, "entidad_id": entidad_id,
        "detalle": json.dumps(detalle, ensure_ascii=False, default=str) if detalle is not None else None, "ip": ip,
    })


# ───────────────────────────── Completitud del perfil ─────────────────────────────

PESOS = [  # (campo, puntos) — suma 100
    ("cedula", 15), ("telefono", 15), ("direccion", 8), ("ubicacion", 15), ("sexo", 5), ("edad", 5), ("correo", 5),
    ("ocupacion", 6), ("nivel_educativo", 5), ("personas_hogar", 5), ("necesidades", 10), ("consentimiento", 6),
]


def completitud(p: dict) -> int:
    pts = 0
    for campo, peso in PESOS:
        if campo == "ubicacion":
            prec = p.get("geo_precision")
            pts += peso if prec in ("direccion", "manual") else (peso // 2 if prec else 0)
        elif campo == "edad":
            pts += peso if (p.get("edad") or p.get("fecha_nacimiento")) else 0
        elif campo == "necesidades":
            pts += peso if p.get("etiquetas") else 0
        elif campo == "consentimiento":
            pts += peso if p.get("consentimiento") == "si" else 0
        else:
            pts += peso if p.get(campo) not in (None, "", 0) else 0
    return pts


def recalcular_completitud(db: Database, ids: Iterable[int] | None = None) -> None:
    filtro = dict(ACTIVA) if ids is None else {"_id": {"$in": list(ids)}}
    campos = {c: 1 for c, _ in PESOS if c not in ("ubicacion", "necesidades")}
    campos |= {"geo_precision": 1, "fecha_nacimiento": 1, "etiquetas": 1, "completitud": 1}
    ops = []
    for p in db.personas.find(filtro, campos):
        c = completitud(p)
        if c != p.get("completitud"):
            ops.append(UpdateOne({"_id": p["_id"]}, {"$set": {"completitud": c}}))
    if ops:
        db.personas.bulk_write(ops, ordered=False)


# ───────────────────────────── Personas ─────────────────────────────

def nueva_persona(db: Database, datos: dict, fuente: str) -> dict:
    doc = {**PERSONA_VACIA, "extra": {}, "fuentes": [fuente], "listas": [], "etiquetas": [], "tramites": [], "notas": [],
           "origen": [], "asistencias": [], "claves_tramites": [], **datos}
    if "_id" not in datos:
        doc["_id"] = siguiente_id(db, "personas")
    doc["nombre_norm"] = tx.nombre_norm(doc["nombre"])
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


def fusionar(db: Database, destino: int, origen: int, usuario: str | None, ip: str | None = None) -> None:
    """Une `origen` en `destino`: completa vacíos y junta trámites, listas, etiquetas, reuniones, notas y fuentes.

    El origen queda solo como enlace (`fusionada_en`), sin datos personales: no se duplican en la base."""
    if destino == origen:
        return
    d = db.personas.find_one({"_id": destino})
    o = db.personas.find_one({"_id": origen})
    if d is None or o is None:
        return
    # Libera primero las claves únicas del origen
    db.personas.update_one({"_id": origen}, {"$set": {"cedula": None, "clave_tramites": None}})
    if o.get("telefono") and d.get("telefono") and o["telefono"] != d["telefono"] and not d.get("telefono2"):
        d["telefono2"] = o["telefono"]
    # La ubicación pasa en bloque (no mezclar el barrio de una con las coordenadas de la otra). Gana la puesta a mano
    # y, si ninguna lo es, la del destino salvo que no tenga punto.
    if _rango_ubicacion(o) > _rango_ubicacion(d):
        d.update({k: o.get(k, PERSONA_VACIA[k]) for k in GEO})
    escalares = [k for k in PERSONA_VACIA if not isinstance(PERSONA_VACIA[k], (list, dict, bool))
                 and k not in ("nombre", "nombre_norm", "fusionada_en", "completitud", "consentimiento", *GEO)]
    completar_doc(d, {k: o.get(k) for k in escalares})
    if d.get("consentimiento") == "pendiente" and o.get("consentimiento") in ("si", "no"):
        d["consentimiento"], d["consentimiento_fecha"] = o["consentimiento"], o.get("consentimiento_fecha")
    d["lider"] = bool(d.get("lider") or o.get("lider"))
    d["extra"] = {**(o.get("extra") or {}), **(d.get("extra") or {})}
    for k in ("fuentes", "listas", "etiquetas"):
        d[k] = list(dict.fromkeys([*(d.get(k) or []), *(o.get(k) or [])]))
    # Trámites: por su ID; los que no tienen ID, por su contenido completo
    ya = {t["id_externo"] for t in d.get("tramites", []) if t.get("id_externo")}
    d["tramites"] = list(d.get("tramites", []))
    for t in o.get("tramites", []):
        if (t["id_externo"] in ya) if t.get("id_externo") else (t in d["tramites"]):
            continue
        d["tramites"].append(t)
    # Las claves de nombre de los dos grupos de trámites: así una importación posterior encuentra la ficha unida
    claves = [d.get("clave_tramites"), *(d.get("claves_tramites") or []), o.get("clave_tramites"),
              *(o.get("claves_tramites") or [])]
    d["claves_tramites"] = list(dict.fromkeys(c for c in claves if c))
    d["notas"] = [*d.get("notas", []), *o.get("notas", [])]
    d["origen"] = [*d.get("origen", []), *o.get("origen", [])]
    reus = {a["reunion_id"] for a in d.get("asistencias", [])}
    d["asistencias"] = [*d.get("asistencias", []), *[a for a in o.get("asistencias", []) if a["reunion_id"] not in reus]]
    d["ultimo_contacto"] = max(filter(None, [d.get("ultimo_contacto"), o.get("ultimo_contacto")]), default=None)
    d["actualizado_en"] = ahora()
    d["completitud"] = completitud(d)
    db.personas.replace_one({"_id": destino}, d)
    db.personas.replace_one({"_id": origen}, {**PERSONA_VACIA, "_id": origen, "nombre": "FUSIONADA", "fusionada_en": destino,
                                              "eliminado": False, "actualizado_en": ahora()})
    db.personas.update_many({"fusionada_en": origen}, {"$set": {"fusionada_en": destino}})
    par = {"$or": [{"persona_id": origen, "candidato_id": destino}, {"persona_id": destino, "candidato_id": origen}]}
    db.coincidencias.update_many({**par, "estado": "pendiente"}, {"$set": {"estado": "aceptada"}})
    db.coincidencias.delete_many({"estado": "pendiente", "$or": [{"persona_id": origen}, {"candidato_id": origen}]})
    cerrar_coincidencias_imposibles(db, [destino])
    auditar(db, usuario, "fusionar", "persona", destino, {"origen": origen}, ip)


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


def suprimir(db: Database, pid: int, usuario: str | None, ip: str | None = None) -> list[int]:
    """Borra los datos personales de la ficha y de todas las unidas con ella, limpia su rastro en la auditoría y
    deja las huellas (HMAC, sin datos en claro) para que una importación no la vuelva a crear."""
    ids = grupo_fusion(db, pid)
    pares: set[tuple[str, Any]] = set()
    for p in db.personas.find({"_id": {"$in": ids}}):
        pares.add(("cedula", p.get("cedula")))
        pares.update(("cedula", o.get("clave")) for o in p.get("origen") or [] if o.get("fuente") == "cedulas")
        tramites = p.get("tramites") or []
        pares.update(("tramite", t.get("id_externo")) for t in tramites)
        pares.update(("contenido", t.get("clave")) for t in tramites if not t.get("id_externo"))
        nombres = [p.get("nombre_norm"), p.get("clave_tramites"), *(p.get("claves_tramites") or [])]
        fichas = [p.get("ficha"), *(t.get("ficha") for t in tramites)]
        tels = [p.get("telefono"), p.get("telefono2"), *(x for t in tramites for x in (t.get("telefono") or "").split(";"))]
        pares.update(pares_identidad(nombres, fichas, tels))
    registrar_huellas(db, pares)
    for i in ids:
        db.personas.replace_one({"_id": i}, {**PERSONA_VACIA, "_id": i, "nombre": "SUPRIMIDO", "nombre_norm": "",
                                             "eliminado": True, "actualizado_en": ahora()})
    db.coincidencias.delete_many({"$or": [{"persona_id": {"$in": ids}}, {"candidato_id": {"$in": ids}}]})
    db.auditoria.update_many({"entidad": "persona", "entidad_id": {"$in": ids}}, {"$set": {"detalle": None}})
    auditar(db, usuario, "suprimir", "persona", pid, {"fichas": len(ids)}, ip)
    return ids
