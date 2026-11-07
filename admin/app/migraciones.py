"""Migración idempotente del esquema (versión 2) y reconciliación de lo que escriba el código viejo (1.12).

`db.inicializar` la llama al final, antes de que el panel quede listo (`app/main.py`), en la consola
(`python -m app.cli migrar`) y en las pruebas.

* **Turno con dueño** (`meta.migracion`): un solo proceso migra; se renueva en cada lote y se libera en un `finally`,
  así una segunda llamada en el mismo proceso entra de inmediato. Si lo tiene otro proceso, se espera (consultando
  `meta.esquema.version` cada 2 s, hasta 5 min) y al agotarse se lanza `ErrorMigracion`.
* **Pasos de la versión 2** (solo si la base está en una versión anterior): en lotes de 500, cada escritura filtra por
  su marca de pendiente, así repetirla no hace daño. Un error en un documento se anota (`meta.migracion.errores`) y
  la migración sigue; solo un error estructural la corta.
* **Reconciliación** (en cada arranque, con consultas baratas): lo que un código viejo pudo escribir durante un
  despliegue o una vuelta atrás (teléfono, puesto, autorización, coordenadas o edad escritos directamente, fichas
  suprimidas con datos ligados, uniones cortadas a mitad) se corrige.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Callable, Iterator

from pymongo import UpdateOne
from pymongo.database import Database
from pymongo.errors import BulkWriteError, ConnectionFailure, PyMongoError

from . import db as bd
from . import modelo

VERSION = 2
LOTE = 500
TURNO_MIN = 10
ESPERA_S = 300
PAUSA_S = 2
MAX_ERRORES = 200
log = logging.getLogger("panel.migracion")


class ErrorMigracion(RuntimeError):
    """Error estructural de la migración (índice, conexión, turno ocupado demasiado tiempo): el arranque se corta con su
    propio mensaje en el registro. Un error en un documento no la lanza: se anota y la migración sigue."""


def version(db: Database) -> int:
    return (db.meta.find_one({"_id": "esquema"}) or {}).get("version", 0)


def migrar(db: Database, *, espera_s: float = ESPERA_S, pausa_s: float = PAUSA_S) -> dict:
    """Lleva la base a la versión de esquema vigente y reconcilia lo que haya escrito el código viejo. Se puede repetir
    sin daño. Devuelve lo hecho en cada paso."""
    dueño = uuid.uuid4().hex
    limite = time.monotonic() + espera_s
    while not bd.tomar_turno(db, "migracion", dueño, TURNO_MIN):
        if version(db) >= VERSION:  # el otro proceso ya migró: la reconciliación la hace él
            return {}
        if time.monotonic() >= limite:
            log.error("Falló la migración, paso %s: %s", "turno", "otro proceso tiene el turno")
            raise ErrorMigracion("Otro proceso tiene el turno de la migración desde hace demasiado tiempo")
        time.sleep(pausa_s)
    m = _Migracion(db, dueño)
    try:
        if version(db) < VERSION:
            m.pasos()
        m.reconciliar()
        return m.hechos
    except (ErrorMigracion, ConnectionFailure):
        raise
    except PyMongoError as e:
        log.error("Falló la migración, paso %s: %s", m.paso, e)
        raise ErrorMigracion(f"Falló la migración, paso {m.paso}: {e}") from e
    finally:
        bd.soltar_turno(db, "migracion", dueño)


def _sin_vacio(v: Any) -> Any:
    return None if modelo.vacio(v) else v


class _Migracion:
    def __init__(self, db: Database, dueño: str):
        self.db, self.dueño = db, dueño
        self.paso: Any = None
        self.hechos: dict = {}
        self.ts = bd.ahora()
        self.hoy = modelo.hoy_local().isoformat()
        self._fechas_imp: dict | None = None
        self._antes_tel: dict | None = None

    # ── Infraestructura ──
    def renovar(self) -> None:
        if not bd.renovar_turno(self.db, "migracion", self.dueño, TURNO_MIN):
            log.error("Falló la migración, paso %s: %s", self.paso, "se perdió el turno")
            raise ErrorMigracion("Se perdió el turno de la migración")

    def error(self, pid: Any, e: Exception) -> None:
        log.warning("Migración, paso %s: la ficha %s no se pudo migrar: %s", self.paso, pid, e)
        self.db.meta.update_one({"_id": "migracion"}, {"$push": {"errores": {
            "$each": [{"id": pid, "paso": self.paso, "error": str(e)[:200], "ts": self.ts}], "$slice": -MAX_ERRORES}}})

    def lotes(self, filtro: dict, proy: dict | None = None, coleccion: str = "personas") -> Iterator[list[dict]]:
        """Documentos que cumplen el filtro, de a LOTE y por _id (lo ya procesado no se vuelve a leer)."""
        ultimo = None
        while True:
            q = filtro if ultimo is None else {"$and": [filtro, {"_id": {"$gt": ultimo}}]}
            docs = list(self.db[coleccion].find(q, proy).sort("_id", 1).limit(LOTE))
            if not docs:
                return
            ultimo = docs[-1]["_id"]
            self.renovar()
            yield docs

    def escribir(self, ops: list, coleccion: str = "personas") -> int:
        if not ops:
            return 0
        try:
            r = self.db[coleccion].bulk_write(ops, ordered=False)
            return r.modified_count + r.upserted_count
        except BulkWriteError as e:
            for x in e.details.get("writeErrors", []):
                self.error(getattr(ops[x["index"]], "_filter", {}).get("_id"), Exception(x.get("errmsg")))
            return e.details.get("nModified", 0)

    def por_documento(self, docs: list[dict], hacer: Callable[[dict], Any]) -> list:
        ops = []
        for d in docs:
            try:
                r = hacer(d)
            except (ConnectionFailure, ErrorMigracion):
                raise
            except Exception as e:  # noqa: BLE001 — un documento raro no corta la migración
                self.error(d.get("_id"), e)
                continue
            if r is not None:
                ops.extend(r if isinstance(r, list) else [r])
        return ops

    @property
    def fechas_imp(self) -> dict:
        if self._fechas_imp is None:
            self._fechas_imp = {i["_id"]: (i.get("ts") or "")[:10] or None
                                for i in self.db.importaciones.find({}, {"ts": 1})}
        return self._fechas_imp

    # ── Pasos de la versión 2 ──
    def pasos(self) -> None:
        for n, nombre, paso in [
            (0, "listas", self.p0_listas), (1, "puestos", self.p1_puestos), (2, "telefonos", self.p2_telefonos),
            (3, "retirados", self.p3_retirados), (4, "procedencia", self.p4_procedencia), (5, "punto", self.p5_punto),
            (6, "edad", self.p6_edad), (7, "votacion", self.p7_votacion), (8, "autorizaciones", self.p8_autorizaciones),
            (9, "reuniones", self.p9_reuniones), (10, "nombre_fon", self.p10_nombre_fon),
            (11, "catalogos", self.p11_catalogos), (12, "auditoria", self.p12_auditoria),
            (13, "completitud", self.p13_completitud),
        ]:
            self.paso = n
            self.renovar()
            self.hechos[nombre] = paso()
        self.paso = 14
        self.db.meta.update_one({"_id": "esquema"}, {"$set": {"version": VERSION, "ts": bd.ahora(), "pasos": self.hechos}},
                                upsert=True)

    def p0_listas(self) -> int:
        """Cada lista u objeto nuevo de PERSONA_VACIA (salvo `telefonos`, que arma el paso 2) donde falte."""
        claves = {k: v for k, v in bd.PERSONA_VACIA.items() if isinstance(v, (list, dict)) and k != "telefonos"}
        r = self.db.personas.update_many(
            {"$or": [{k: {"$exists": False}} for k in claves]},
            [{"$set": {k: {"$cond": [{"$eq": [{"$type": f"${k}"}, "missing"]}, {"$literal": v}, f"${k}"]}
                       for k, v in claves.items()}}])
        return r.modified_count

    def p1_puestos(self) -> int:
        return bd.sembrar_puestos(self.db)

    def p2_telefonos(self) -> int:
        """`telefonos` de las fichas que no la tienen: el teléfono tal cual, los de los trámites y los de la base con
        cédula, con sus fuentes y fechas; luego se derivan telefono y telefono2."""
        n = 0
        proy = {"telefono": 1, "telefono2": 1, "tramites.telefono": 1, "tramites.fecha": 1, "origen": 1}

        def hacer(p: dict):
            lista = modelo.telefonos_iniciales(p, self.fechas_imp)
            # Los números que el administrador reemplazó o quitó (y ya no estaban en uso) entran como retirados
            en_uso = {p.get("telefono"), p.get("telefono2")}
            for num, ts in self.antes_tel().get(p["_id"], {}).items():
                if num not in en_uso:
                    lista = modelo.cambiar_telefono(lista, num, {"estado": "retirado", "estado_por": 0, "estado_en": ts})
            return UpdateOne({"_id": p["_id"], "telefonos": {"$exists": False}},
                             [{"$set": {"telefonos": {"$literal": lista}}}, modelo.ETAPA_DERIVAR_TELEFONOS])

        for docs in self.lotes({"telefonos": {"$exists": False}}, proy):
            n += self.escribir(self.por_documento(docs, hacer))
        return n

    def antes_tel(self) -> dict[int, dict[str, str]]:
        """{ficha: {número reemplazado o quitado en el panel: cuándo}}, según las ediciones de la auditoría."""
        if self._antes_tel is None:
            antes: dict[int, dict[str, str]] = {}
            for a in self.db.auditoria.find({"accion": "editar", "entidad": "persona", "detalle": {"$regex": "telefono"}},
                                            {"entidad_id": 1, "detalle": 1, "ts": 1}):
                try:
                    det = json.loads(a["detalle"])
                except (TypeError, ValueError):
                    continue
                for k in ("telefono", "telefono2"):
                    x = det.get(k) if isinstance(det, dict) else None
                    if isinstance(x, dict) and not modelo.vacio(x.get("antes")) and x.get("antes") != x.get("despues"):
                        ts = antes.setdefault(a["entidad_id"], {}).get(x["antes"])
                        antes[a["entidad_id"]][x["antes"]] = max(filter(None, [ts, a.get("ts")]), default=None)
            self._antes_tel = antes
        return self._antes_tel

    def p3_retirados(self) -> int:
        """Los números que el administrador reemplazó o quitó en el panel (según la auditoría) y ya no están en uso
        quedan «retirado»: una importación no los vuelve a poner como principales. Las fichas que armó el paso 2 ya los
        traen marcados; aquí quedan las que ya tenían la lista."""
        antes = self.antes_tel()
        n = 0
        ids = sorted(antes)
        for k in range(0, len(ids), LOTE):
            self.renovar()
            docs = list(self.db.personas.find({"_id": {"$in": ids[k:k + LOTE]}}, {"telefono": 1, "telefono2": 1,
                                                                                  "telefonos": 1}))

            def hacer(p: dict):
                en_uso = {p.get("telefono"), p.get("telefono2")}
                estados = {t.get("numero"): t.get("estado") for t in p.get("telefonos") or []}
                etapas = [modelo.expr_estado_telefono(num, {"estado": "retirado", "estado_por": 0, "estado_en": ts})[0]
                          for num, ts in sorted(antes[p["_id"]].items())
                          if num not in en_uso and num in estados and estados[num] != "retirado"]
                if not etapas:
                    return None
                return UpdateOne({"_id": p["_id"]}, [*etapas, modelo.ETAPA_DERIVAR_TELEFONOS])

            n += self.escribir(self.por_documento(docs, hacer))
        return n

    def p4_procedencia(self) -> int:
        """`procedencia` de lo que ya tiene valor: igual al de la base con cédula → cedulas; al de los trámites →
        tramites; si no, panel (nunca lo reemplaza una importación)."""
        campos = [c for c in modelo.CAMPOS_PROCEDENCIA if c != "votacion"]
        proy = {**{c: 1 for c in campos}, "procedencia": 1, "origen.fuente": 1, "origen.datos": 1,
                "tramites.correo": 1, "tramites.direccion": 1}
        n = 0

        def hacer(p: dict):
            ya = p.get("procedencia") or {}
            datos = [o.get("datos") or {} for o in p.get("origen") or [] if o.get("fuente") == "cedulas"]
            nuevos = {}
            for campo in campos:
                v = p.get(campo)
                if modelo.vacio(v) or campo in ya:
                    continue
                if any(d.get(campo) == v for d in datos):
                    fuente = "cedulas"
                elif campo in ("correo", "direccion") and any(t.get(campo) == v for t in p.get("tramites") or []):
                    fuente = "tramites"
                else:
                    fuente = "panel"
                nuevos[campo] = {"fuente": fuente, "ts": self.ts, "uid": None}
            if not nuevos:
                return None
            return UpdateOne({"_id": p["_id"]}, [{"$set": {"procedencia": {"$mergeObjects": [
                {"$literal": nuevos}, {"$ifNull": ["$procedencia", {}]}]}}}])

        for docs in self.lotes({}, proy):
            n += self.escribir(self.por_documento(docs, hacer))
        return n

    def p5_punto(self) -> int:
        n = 0

        def hacer(p: dict):
            pt = modelo.punto(p.get("lat"), p.get("lon"))
            if pt is None:
                return None
            return UpdateOne({"_id": p["_id"], "lat": p.get("lat"), "lon": p.get("lon"), "punto": None},
                             {"$set": {"punto": pt}})

        for docs in self.lotes({"lat": {"$ne": None}, "lon": {"$ne": None}, "punto": None}, {"lat": 1, "lon": 1}):
            n += self.escribir(self.por_documento(docs, hacer))
        return n

    def _edad_ref(self, p: dict) -> str | None:
        """Fecha en que se declaró la edad: la de la importación que la trajo o la de creación de la ficha."""
        for o in p.get("origen") or []:
            if o.get("fuente") == "cedulas" and (o.get("datos") or {}).get("edad") == p.get("edad"):
                f = self.fechas_imp.get(o.get("importacion_id"))
                if f:
                    return f
        return (p.get("creado_en") or "")[:10] or None

    def p6_edad(self) -> int:
        n = 0
        filtro = {"$or": [{"edad": {"$ne": None}}, {"fecha_nacimiento": {"$nin": [None, ""]}}],
                  "nac_base": {"$in": [{}, None]}}

        def hacer(p: dict):
            s = {}
            if p.get("edad") is not None and not p.get("edad_ref"):
                s["edad_ref"] = self._edad_ref(p)
            s.update(modelo.calcular_nac({**p, **s}))
            return UpdateOne({"_id": p["_id"], "edad": p.get("edad"), "fecha_nacimiento": p.get("fecha_nacimiento")},
                             {"$set": s})

        proy = {"edad": 1, "fecha_nacimiento": 1, "edad_ref": 1, "creado_en": 1, "origen.fuente": 1,
                "origen.datos.edad": 1, "origen.importacion_id": 1}
        for docs in self.lotes(filtro, proy):
            n += self.escribir(self.por_documento(docs, hacer))
        return n

    def _votacion_de_texto(self, p: dict, puestos: list[dict]) -> dict | None:
        datos = [o.get("datos") or {} for o in p.get("origen") or [] if o.get("fuente") == "cedulas"]
        pv, mesa = _sin_vacio(p.get("puesto_votacion")), _sin_vacio(p.get("mesa"))
        de_base = any((pv and d.get("puesto") == pv) or (mesa and d.get("mesa") == mesa) for d in datos)
        return modelo.armar_votacion(pv, mesa, puestos, fuente="cedulas" if de_base else "panel", eleccion=None,
                                     estado="por_confirmar", conservar_texto=True)

    def p7_votacion(self) -> int:
        """`votacion` desde el puesto y la mesa escritos, con elección desconocida y «por confirmar». El texto original
        queda en `puesto_texto` y `mesa_texto`; `mesa` sigue igual al texto original."""
        puestos = bd.puestos_vigentes(self.db)
        n = 0
        filtro = {"votacion": None, "$or": [{"puesto_votacion": {"$nin": [None, ""]}}, {"mesa": {"$nin": [None, ""]}}]}

        def hacer(p: dict):
            v = self._votacion_de_texto(p, puestos)
            if v is None:
                return None
            return UpdateOne({"_id": p["_id"], "votacion": None, "puesto_votacion": p.get("puesto_votacion"),
                              "mesa": p.get("mesa")},
                             [{"$set": {"votacion": {"$literal": v}, "procedencia": {"$mergeObjects": [
                                 {"$ifNull": ["$procedencia", {}]},
                                 {"votacion": {"$literal": {"fuente": v["fuente"], "ts": self.ts, "uid": None}}}]}}},
                              modelo.ETAPA_DERIVAR_VOTACION])

        for docs in self.lotes(filtro, {"puesto_votacion": 1, "mesa": 1, "origen.fuente": 1, "origen.datos.puesto": 1,
                                        "origen.datos.mesa": 1}):
            n += self.escribir(self.por_documento(docs, hacer))
        return n

    def _derivar_autorizacion(self, ids: list[int]) -> int:
        eventos: dict[int, list] = {}
        for e in self.db.autorizaciones.find({"persona_id": {"$in": ids}}):
            eventos.setdefault(e["persona_id"], []).append(e)
        ops = []
        for p in self.db.personas.find({"_id": {"$in": ids}}, {"consentimiento": 1}):
            if p["_id"] not in eventos:
                continue
            vig = modelo.consentimiento_vigente(eventos[p["_id"]])
            ops.append(UpdateOne({"_id": p["_id"], "consentimiento": p.get("consentimiento")}, {"$set": vig}))
        return self.escribir(ops)

    def p8_autorizaciones(self) -> int:
        """Un evento «migrado» (canales implícitos) por cada ficha con «si» o «no»; la hora es la de la migración y la
        fecha que tenía la ficha queda como declarada."""
        ya = set(self.db.autorizaciones.distinct("persona_id", {"clave_migracion": {"$regex": "^consent:"}}))
        n = 0
        for docs in self.lotes({"consentimiento": {"$in": ["si", "no"]}}, {"consentimiento": 1,
                                                                          "consentimiento_fecha": 1}):
            nuevos = [p for p in docs if p["_id"] not in ya]
            if not nuevos:
                continue
            primero = bd.siguiente_id(self.db, "autorizaciones", len(nuevos))
            eventos = [bd.autorizacion_doc(self.db, p["_id"], p["consentimiento"], "migrado", _id=primero + i,
                                           canales_implicitos=p["consentimiento"] == "si",
                                           fecha_declarada=p.get("consentimiento_fecha"), usuario="migración",
                                           clave_migracion=f"consent:{p['_id']}", ts=self.ts)
                       for i, p in enumerate(nuevos)]
            try:
                self.db.autorizaciones.insert_many(eventos, ordered=False)
            except BulkWriteError as e:
                if any(x.get("code") != 11000 for x in e.details.get("writeErrors", [])):
                    raise
            n += self._derivar_autorizacion([p["_id"] for p in nuevos])
        return n

    def p9_reuniones(self) -> int:
        """Un acercamiento automático («reunion», contestó) por cada asistencia; luego el resumen de abordaje."""
        ya = set(self.db.acercamientos.distinct("clave_migracion", {"clave_migracion": {"$regex": "^reunion:"}}))
        fechas = {r["_id"]: r.get("fecha") for r in self.db.reuniones.find({}, {"fecha": 1})}
        tocadas: set[int] = set()
        for docs in self.lotes({"asistencias.0": {"$exists": True}}, {"asistencias": 1}):
            nuevos = []
            for p in docs:
                for a in p.get("asistencias") or []:
                    clave = f"reunion:{p['_id']}:{a.get('reunion_id')}"
                    if clave in ya or a.get("reunion_id") not in fechas:
                        continue
                    ya.add(clave)
                    nuevos.append(acercamiento_migrado(p["_id"], a, fechas[a["reunion_id"]], clave))
            if nuevos:
                primero = bd.siguiente_id(self.db, "acercamientos", len(nuevos))
                for i, a in enumerate(nuevos):
                    a["_id"] = primero + i
                try:
                    self.db.acercamientos.insert_many(nuevos, ordered=False)
                except BulkWriteError as e:
                    if any(x.get("code") != 11000 for x in e.details.get("writeErrors", [])):
                        raise
                tocadas |= {a["persona_id"] for a in nuevos}
        tocadas |= {p["_id"] for p in self.db.personas.find({"consentimiento": "no", "abordaje": None}, {"_id": 1})}
        return self.abordaje(sorted(tocadas))

    def abordaje(self, ids: list[int]) -> int:
        n = 0
        for k in range(0, len(ids), LOTE):
            self.renovar()
            parte = ids[k:k + LOTE]
            acerc: dict[int, list] = {}
            for a in self.db.acercamientos.find({"persona_id": {"$in": parte}, "anulado": {"$ne": True}}):
                acerc.setdefault(a["persona_id"], []).append(a)
            ops = []
            for p in self.db.personas.find({"_id": {"$in": parte}}, {"consentimiento": 1, "abordaje": 1,
                                                                    "abordaje_seq": 1}):
                ab = modelo.resumen_abordaje(acerc.get(p["_id"]), p.get("consentimiento"))
                if ab != p.get("abordaje"):
                    ops.append(UpdateOne({"_id": p["_id"], "abordaje_seq": p.get("abordaje_seq")}, {"$set": {"abordaje": ab}}))
            n += self.escribir(ops)
        return n

    def p10_nombre_fon(self) -> int:
        n = 0
        filtro = {"nombre_norm": {"$nin": [None, ""]}, "$or": [{"nombre_fon": {"$exists": False}},
                                                              {"nombre_fon": {"$size": 0}}]}

        def hacer(p: dict):
            claves = modelo.claves_foneticas(p.get("nombre"))
            return UpdateOne({"_id": p["_id"]}, {"$set": {"nombre_fon": claves}}) if claves else None

        for docs in self.lotes(filtro, {"nombre": 1}):
            n += self.escribir(self.por_documento(docs, hacer))
        return n

    def p11_catalogos(self) -> int:
        db = self.db
        n = db.etiquetas.update_many({"sensible": {"$exists": False}, "nombre": {"$in": list(bd.ETIQUETAS_SENSIBLES)}},
                                     {"$set": {"sensible": True}}).modified_count
        n += db.etiquetas.update_many({"sensible": {"$exists": False}}, {"$set": {"sensible": False}}).modified_count
        n += db.campos.update_many({"sensible": {"$exists": False}}, {"$set": {"sensible": False}}).modified_count
        n += db.coincidencias.update_many({"motivo": {"$exists": False}, "detalle.homonimo": True},
                                          {"$set": {"motivo": "homonimo"}}).modified_count
        n += db.coincidencias.update_many({"motivo": {"$exists": False}, "detalle.variante": True},
                                          {"$set": {"motivo": "variante"}}).modified_count
        n += db.coincidencias.update_many({"motivo": {"$exists": False}}, {"$set": {"motivo": "cruce_cedula"}}).modified_count
        return n

    def p12_auditoria(self) -> int:
        """`campos` y `completados` (nombres canónicos) de las ediciones y altas de personas que no los tienen."""
        n = 0

        def hacer(a: dict):
            campos, completados = campos_de_detalle(a.get("accion"), a.get("detalle"))
            return UpdateOne({"_id": a["_id"], "campos": {"$exists": False}},
                             {"$set": {"campos": campos, "completados": completados}})

        filtro = {"entidad": "persona", "accion": {"$in": ["editar", "crear"]}, "campos": {"$exists": False}}
        for docs in self.lotes(filtro, {"accion": 1, "detalle": 1}, "auditoria"):
            n += self.escribir(self.por_documento(docs, hacer), "auditoria")
        return n

    def p13_completitud(self) -> int:
        bd.recalcular_completitud(self.db)
        return 1

    # ── Reconciliación (en cada arranque) ──
    def reconciliar(self) -> None:
        self.paso = "reconciliacion"
        r = {"listas": self.p0_listas(), "sin_telefonos": self.p2_telefonos(), "telefonos": self.r_telefonos(),
             "votacion": self.r_votacion(), "autorizacion": self.r_autorizacion(), "punto": self.r_punto(),
             "edad": self.r_edad(), "suprimidas": self.r_suprimidas(), "fusiones": bd.reparar_fusiones(self.db),
             "nombre_fon": self.p10_nombre_fon()}
        self.hechos["reconciliacion"] = r
        if any(r.values()):
            log.info("Reconciliación: %s", {k: v for k, v in r.items() if v})

    def r_telefonos(self) -> int:
        """`telefono` o `telefono2` escritos directamente y ausentes de `telefonos`: entran en la posición 0 o 1."""
        lista = {"$map": {"input": modelo.TELS_ACTUALES, "as": "t", "in": "$$t.numero"}}
        falta = lambda c: {"$and": [{"$not": [{"$in": [{"$ifNull": [f"${c}", None]}, [None, ""]]}]},  # noqa: E731
                                    {"$not": [{"$in": [f"${c}", lista]}]}]}
        q = {"telefonos": {"$exists": True}, "$expr": {"$or": [falta("telefono"), falta("telefono2")]}}
        ids = [p["_id"] for p in self.db.personas.find(q, {"_id": 1})]
        if not ids:
            return 0
        r = self.db.personas.update_many({"_id": {"$in": ids}, **q}, [modelo.ETAPA_RECONCILIAR_TELEFONOS,
                                                                      modelo.ETAPA_DERIVAR_TELEFONOS])
        bd.recalcular_completitud(self.db, ids)
        return r.modified_count

    def r_votacion(self) -> int:
        """Puesto o mesa escritos directamente, distintos de lo que se deriva de `votacion`: se rehace la votación
        («panel», por confirmar) y la anterior pasa a `alternos`."""
        derivada = modelo.ETAPA_DERIVAR_VOTACION["$set"]
        nulo = lambda x: {"$cond": [{"$in": [{"$ifNull": [x, None]}, [None, ""]]}, None, x]}  # noqa: E731
        es_obj = {"$eq": [{"$type": "$votacion"}, "object"]}
        q = {"$expr": {"$or": [
            {"$and": [es_obj, {"$or": [{"$ne": [nulo("$puesto_votacion"), nulo(derivada["puesto_votacion"])]},
                                       {"$ne": [nulo("$mesa"), nulo(derivada["mesa"])]}]}]},
            {"$and": [{"$not": [es_obj]}, {"$or": [{"$ne": [nulo("$puesto_votacion"), None]},
                                                   {"$ne": [nulo("$mesa"), None]}]}]}]}}
        docs = list(self.db.personas.find(q, {"puesto_votacion": 1, "mesa": 1, "votacion": 1, "origen.fuente": 1,
                                              "origen.datos.puesto": 1, "origen.datos.mesa": 1}))
        if not docs:
            return 0
        puestos = bd.puestos_vigentes(self.db)

        def hacer(p: dict):
            v = modelo.armar_votacion(_sin_vacio(p.get("puesto_votacion")), _sin_vacio(p.get("mesa")), puestos,
                                      fuente="panel", eleccion=None, estado="por_confirmar", conservar_texto=True)
            s: dict = {"votacion": {"$literal": v},
                       "procedencia": {"$mergeObjects": [{"$ifNull": ["$procedencia", {}]}, {"votacion": {"$literal": {
                           "fuente": "panel", "ts": self.ts, "uid": None}}}]}}
            antes = p.get("votacion")
            if isinstance(antes, dict):
                alt = {"campo": "votacion", "valor": modelo.comparable("votacion", antes),
                       "fuente": antes.get("fuente") or "panel", "ts": self.ts, "uid": None}
                s["alternos"] = {"$slice": [{"$concatArrays": [{"$ifNull": ["$alternos", []]}, [{"$literal": alt}]]}, -100]}
            return UpdateOne({"_id": p["_id"], "puesto_votacion": p.get("puesto_votacion"), "mesa": p.get("mesa")},
                             [{"$set": s}, modelo.ETAPA_DERIVAR_VOTACION])

        n = self.escribir(self.por_documento(docs, hacer))
        bd.recalcular_completitud(self.db, [p["_id"] for p in docs])
        return n

    def r_autorizacion(self) -> int:
        ids = bd.reconciliar_consentimiento(self.db)
        if ids:
            bd.derivar(self.db, ids, reconciliar=False)
        return len(ids)

    def r_punto(self) -> int:
        ops = []
        for p in self.db.personas.find({"$or": [{"lat": {"$ne": None}}, {"lon": {"$ne": None}}, {"punto": {"$ne": None}}]},
                                       {"lat": 1, "lon": 1, "punto": 1}):
            pt = modelo.punto(p.get("lat"), p.get("lon"))
            if pt != p.get("punto"):
                ops.append(UpdateOne({"_id": p["_id"], "lat": p.get("lat"), "lon": p.get("lon")}, {"$set": {"punto": pt}}))
        return self.escribir(ops)

    def r_edad(self) -> int:
        """Edad o fecha de nacimiento distintas de las que produjeron `nac_aprox` (`nac_base`): se recalcula; una edad
        cambiada se toma como declarada hoy."""
        nulo = lambda x: {"$ifNull": [x, None]}  # noqa: E731
        q = {"$expr": {"$or": [{"$ne": [nulo("$edad"), nulo("$nac_base.edad")]},
                               {"$ne": [nulo("$fecha_nacimiento"), nulo("$nac_base.fecha")]}]}}
        docs = list(self.db.personas.find(q, {"edad": 1, "fecha_nacimiento": 1, "edad_ref": 1, "nac_base": 1,
                                              "creado_en": 1}))

        def hacer(p: dict):
            s = {}
            if p.get("edad") is not None and p.get("edad") != (p.get("nac_base") or {}).get("edad"):
                s["edad_ref"] = self.hoy
            s.update(modelo.calcular_nac({**p, **s}))
            return UpdateOne({"_id": p["_id"], "edad": p.get("edad"), "fecha_nacimiento": p.get("fecha_nacimiento")},
                             {"$set": s})

        return self.escribir(self.por_documento(docs, hacer))

    def r_suprimidas(self) -> int:
        """Fichas suprimidas que todavía tienen acercamientos, autorizaciones, conflictos, idempotencia o
        conversaciones del asistente con datos."""
        ids = [p["_id"] for p in self.db.personas.find({"eliminado": True}, {"_id": 1})]
        if not ids:
            return 0
        con_datos: set = set()
        for col in ("acercamientos", "autorizaciones", "conflictos_cedula", "idempotencia", "coincidencias"):
            con_datos |= set(self.db[col].distinct("persona_id", {"persona_id": {"$in": ids}}))
        con_datos |= set(self.db.solicitudes.distinct("persona_id", {"persona_id": {"$in": ids},
                                                                     "suprimido": {"$ne": True}}))
        # `personas` es una lista: `distinct` trae también a las demás personas de esas conversaciones, que no están
        # suprimidas y no se deben tocar
        con_datos |= set(self.db.agente_conversaciones.distinct("personas", {"personas": {"$in": ids}})) & set(ids)
        con_datos.discard(None)
        if con_datos:
            bd.limpiar_ligados(self.db, sorted(con_datos))
        return len(con_datos)


def acercamiento_migrado(pid: int, asistencia: dict, fecha: str | None, clave: str) -> dict:
    """Acercamiento automático de una asistencia a una reunión registrada antes de la versión 2."""
    return {"_id": None, "persona_id": pid, "ts": asistencia.get("creado_en") or bd.ahora(), "fecha": fecha,
            "uid": None, "usuario": "migración", "rol": None, "canal": "reunion", "telefono": None,
            "resultado": "contesto", "efectivo": True, "nota": None, "proximo": None, "proximo_franja": None,
            "confirma_numero": False, "reunion_id": asistencia.get("reunion_id"), "autorizacion_id": None,
            "datos_dictados": [], "efectos": [], "fuera_de_horario": False, "auto": True, "anulado": False,
            "anulado_por": None, "anulado_en": None, "motivo_anulacion": None, "suprimido": False,
            "clave_migracion": clave}


# Nombre del detalle de la auditoría → clave canónica (las demás quedan con su nombre)
CANONICOS = {"puesto_votacion": "puesto", "lugar_id": "lugar", "fecha_nacimiento": "edad", "telefono2": "telefono",
             "consentimiento": "autorizacion", "consentimiento_fecha": "autorizacion"}


def campos_de_detalle(accion: str | None, detalle: Any) -> tuple[list[str], list[str]]:
    """(campos, completados) de una entrada vieja de la auditoría: en «editar», las claves del detalle (completados solo
    las que tienen antes y después: extra y etiquetas no); en «crear», las no vacías salvo la fuente."""
    if detalle is None:
        return [], []
    try:
        det = json.loads(detalle) if isinstance(detalle, str) else detalle
    except (TypeError, ValueError):
        return [], []
    if not isinstance(det, dict):
        return [], []
    if accion == "crear":
        datos = {k: v for k, v in det.items() if k != "fuente" and not modelo.vacio(v)}
        antes, despues = {}, datos
    else:
        datos = det
        par = {k: v for k, v in det.items() if isinstance(v, dict) and {"antes", "despues"} <= set(v)}
        antes = {k: v["antes"] for k, v in par.items()}
        despues = {k: v["despues"] for k, v in par.items()}
    campos = list(dict.fromkeys(CANONICOS.get(k, k) for k in datos))
    return campos, modelo.completados(antes, despues)
