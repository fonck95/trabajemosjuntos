"""Importación: de los Excel a la base única en MongoDB, cruzada y georreferenciada.

Se puede correr las veces que haga falta con archivos nuevos o actualizados:
* los trámites se identifican por su ID y no se duplican;
* las personas de trámites por su nombre agrupado, y las de la base con cédula por la cédula;
* la importación solo completa campos vacíos: nunca pisa lo que se corrigió o enriqueció en el panel.

Para que sea rápida aun contra un MongoDB remoto, carga las personas en memoria, aplica todo y escribe por lotes.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median

from pymongo import ReplaceOne, UpdateOne
from pymongo.database import Database
from rapidfuzz import fuzz, process

from .. import db as bd
from . import cruce, lectores
from . import texto as tx
from .direcciones import Nomenclator, leer
from .geocodificador import Geocodificador, GrillaCasco


@dataclass
class Resumen:
    archivos: list[dict] = field(default_factory=list)
    personas_nuevas: int = 0
    personas_actualizadas: int = 0
    tramites_nuevos: int = 0
    cedulas_unidas_auto: int = 0
    cedulas_en_revision: int = 0
    cedulas_sin_coincidencia: int = 0
    cedulas_ya_existian: int = 0
    lugares_nuevos: int = 0
    geo: dict = field(default_factory=dict)

    def dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class _Cand:
    id: int
    nombre: str
    telefonos: set
    correos: set


class _Almacen:
    """Personas activas en memoria con índices por clave de trámites, cédula y trámite."""

    def __init__(self, db: Database):
        self.db = db
        self.docs: dict[int, dict] = {d["_id"]: d for d in db.personas.find(bd.ACTIVA)}
        self.por_clave = {d["clave_tramites"]: i for i, d in self.docs.items() if d.get("clave_tramites")}
        self.por_cedula = {d["cedula"]: i for i, d in self.docs.items() if d.get("cedula")}
        self.por_tramite = {t["id_externo"]: i for i, d in self.docs.items() for t in d.get("tramites", []) if t.get("id_externo")}
        self.sucios: set[int] = set()
        self.ids_libres: list[int] = []

    def nueva(self, datos: dict, fuente: str) -> dict:
        if not self.ids_libres:  # reserva identificadores de a 500 para no pedir uno por persona
            primero = bd.siguiente_id(self.db, "personas", 500)
            self.ids_libres = list(range(primero, primero + 500))
        d = bd.nueva_persona(self.db, {**datos, "_id": self.ids_libres.pop(0)}, fuente)
        self.docs[d["_id"]] = d
        self.sucios.add(d["_id"])
        if d.get("clave_tramites"):
            self.por_clave[d["clave_tramites"]] = d["_id"]
        if d.get("cedula"):
            self.por_cedula[d["cedula"]] = d["_id"]
        return d

    def guardar(self) -> None:
        ops = []
        for i in self.sucios:
            d = self.docs[i]
            d["completitud"] = bd.completitud(d)
            ops.append(ReplaceOne({"_id": i}, d, upsert=True))
        for k in range(0, len(ops), 1000):
            self.db.personas.bulk_write(ops[k:k + 1000], ordered=False)
        self.sucios.clear()


def _fuente(d: dict, f: str) -> None:
    if f not in d["fuentes"]:
        d["fuentes"].append(f)


def importar(db: Database, rutas: list[Path], usuario: str | None = "sistema", nombres: list[str] | None = None) -> Resumen:
    res = Resumen()
    tramites: list[lectores.FilaTramite] = []
    cedulas: list[lectores.FilaCedula] = []
    for i, ruta in enumerate(rutas):
        nombre = (nombres or [])[i] if nombres and i < len(nombres) else Path(ruta).name
        tipo = lectores.tipo_de_archivo(ruta)
        if tipo == "tramites":
            filas = list(lectores.leer_tramites(ruta))
            tramites += filas
        elif tipo == "cedulas":
            filas = list(lectores.leer_cedulas(ruta))
            cedulas += filas
        else:
            raise ValueError(f"No reconozco el formato de {nombre}: faltan las columnas esperadas")
        res.archivos.append({"archivo": nombre, "tipo": tipo, "filas": len(filas)})

    imp_id = bd.siguiente_id(db, "importaciones")
    alm = _Almacen(db)
    if tramites:
        _importar_tramites(alm, tramites, res)
    if cedulas:
        _importar_cedulas(alm, cedulas, imp_id, res)
    alm.guardar()
    res.lugares_nuevos = registrar_lugares_de_datos(db)
    res.geo = georreferenciar(db)
    bd.recalcular_completitud(db)
    db.importaciones.insert_one({"_id": imp_id, "ts": bd.ahora(), "usuario": usuario,
                                 "archivo": ", ".join(a["archivo"] for a in res.archivos),
                                 "tipo": ", ".join(sorted({a["tipo"] for a in res.archivos})), "resumen": res.dict()})
    bd.auditar(db, usuario, "importar", "importacion", imp_id, res.dict())
    return res


def _importar_tramites(alm: _Almacen, filas, res: Resumen) -> None:
    for g in cruce.agrupar_tramites(filas):
        u = g.ultima
        pid = alm.por_clave.get(g.clave)
        if pid is None:  # ¿alguno de sus trámites ya está en la base (p. ej. tras una fusión)?
            pid = next((alm.por_tramite[f.id_externo] for f in g.filas if f.id_externo in alm.por_tramite), None)
        tels = [t for t, _ in g.telefonos.most_common(2)]
        datos = {
            "telefono": tels[0] if tels else None, "telefono2": tels[1] if len(tels) > 1 else None,
            "correo": g.correos.most_common(1)[0][0] if g.correos else None,
            "direccion": u.direccion or next((f.direccion for f in sorted(g.filas, key=lambda f: f.fecha or "", reverse=True)
                                              if f.direccion), None),
            "ficha": u.ficha or None,
        }
        if pid is None:
            d = alm.nueva({"nombre": g.nombre, "clave_tramites": g.clave}, "tramites")
            res.personas_nuevas += 1
        else:
            d = alm.docs[pid]
            res.personas_actualizadas += 1
        cambios = bd.completar_doc(d, datos)
        _fuente(d, "tramites")
        nuevos = 0
        for f in g.filas:
            if f.id_externo and f.id_externo in alm.por_tramite:
                continue
            d["tramites"].append({"id_externo": f.id_externo or None, "ficha": f.ficha, "fecha": f.fecha, "tipo": f.tramite,
                                  "direccion": f.direccion, "telefono": ";".join(f.telefonos), "correo": f.correo,
                                  "paquete": f.paquete})
            if f.id_externo:
                alm.por_tramite[f.id_externo] = d["_id"]
            nuevos += 1
        res.tramites_nuevos += nuevos
        ultima = max((f.fecha for f in g.filas if f.fecha), default=None)
        if ultima and ultima > (d.get("ultimo_contacto") or ""):
            d["ultimo_contacto"] = ultima
            cambios.append("ultimo_contacto")
        if cambios or nuevos or pid is None:
            d["actualizado_en"] = bd.ahora()
            alm.sucios.add(d["_id"])


def _importar_cedulas(alm: _Almacen, filas, imp_id: int, res: Resumen) -> None:
    db = alm.db
    nuevas = []
    for f in filas:
        pid = alm.por_cedula.get(f.cedula)
        if pid is not None:
            _completar_desde_cedula(alm, alm.docs[pid], f, imp_id)
            res.cedulas_ya_existian += 1
        else:
            nuevas.append(f)
    if not nuevas:
        return
    cands = []
    for d in alm.docs.values():
        if d.get("cedula"):
            continue
        tels = {d.get("telefono"), d.get("telefono2")} - {None, ""}
        tels |= {t for tr in d.get("tramites", []) for t in (tr.get("telefono") or "").split(";") if t}
        cands.append(_Cand(d["_id"], d["nombre"], tels, {d["correo"]} if d.get("correo") else set()))
    usados: set[int] = set()
    coincidencias = []
    for r in cruce.cruzar(cands, nuevas):
        f, m = r.fila, r.mejor
        if r.estado == "auto" and m and cands[m.indice].id not in usados:
            d = alm.docs[cands[m.indice].id]
            usados.add(d["_id"])
            d["cedula"] = f.cedula
            alm.por_cedula[f.cedula] = d["_id"]
            _completar_desde_cedula(alm, d, f, imp_id)
            bd.auditar(db, "sistema", "cruce_automatico", "persona", d["_id"],
                       {"cedula": f.cedula, "nombre_base_cedulas": f.nombre, "puntaje": m.puntaje,
                        "telefono": m.telefono, "correo": m.correo})
            res.cedulas_unidas_auto += 1
            continue
        d = alm.nueva({"nombre": f.nombre, "cedula": f.cedula}, "cedulas")
        _completar_desde_cedula(alm, d, f, imp_id)
        res.personas_nuevas += 1
        if r.estado == "revision":
            res.cedulas_en_revision += 1
            for c in r.candidatos:
                if c.puntaje >= cruce.UMBRAL_REVISION:
                    coincidencias.append({"persona_id": d["_id"], "candidato_id": cands[c.indice].id, "puntaje": c.puntaje,
                                          "detalle": {"puntaje_nombre": c.puntaje_nombre, "palabras": c.palabras,
                                                      "telefono": c.telefono, "correo": c.correo}, "estado": "pendiente"})
        else:
            res.cedulas_sin_coincidencia += 1
    if coincidencias:
        primero = bd.siguiente_id(db, "coincidencias", len(coincidencias))
        for i, c in enumerate(coincidencias):
            db.coincidencias.update_one({"persona_id": c["persona_id"], "candidato_id": c["candidato_id"]},
                                        {"$setOnInsert": {"_id": primero + i, **c}}, upsert=True)


def _completar_desde_cedula(alm: _Almacen, d: dict, f: lectores.FilaCedula, imp_id: int) -> None:
    tels = f.telefonos
    bd.completar_doc(d, {
        "telefono": tels[0] if tels else None, "telefono2": tels[1] if len(tels) > 1 else None, "correo": f.correo or None,
        "sexo": f.sexo or None, "edad": f.edad, "direccion": f.direccion or None,
        "puesto_votacion": f.puesto or None, "mesa": f.mesa or None,
    })
    _fuente(d, "cedulas")
    for lista in f.listas:
        if lista not in d["listas"]:
            d["listas"].append(lista)
    datos = {k: v for k, v in f.__dict__.items() if v not in (None, "", [], {})}
    d["origen"] = [o for o in d.get("origen", []) if not (o["fuente"] == "cedulas" and o["clave"] == f.cedula)]
    d["origen"].append({"fuente": "cedulas", "clave": f.cedula, "datos": datos, "importacion_id": imp_id})
    d["actualizado_en"] = bd.ahora()
    alm.sucios.add(d["_id"])


# ───────────────────────────── Lugares y georreferenciación ─────────────────────────────

def registrar_lugares_de_datos(db: Database, minimo: int = 3) -> int:
    """Barrios y veredas que aparecen escritos varias veces y no están en el nomenclátor: se agregan sin punto
    (el punto sale de las direcciones con placa o lo ubica el administrador en el mapa)."""
    nom = Nomenclator(bd.lugares(db))
    conteo: Counter = Counter()
    for p in db.personas.find({**bd.ACTIVA, "direccion": {"$ne": None}}, {"direccion": 1}):
        d = leer(p["direccion"])
        if not d.lugar_texto or d.tipo_lugar not in ("BARRIO", "VEREDA", "URBANIZACION", "SECTOR", "CASERIO"):
            continue
        lugar, _, _ = nom.reconocer(d)
        if lugar is None and len(d.lugar_texto) >= 3:
            conteo[(d.lugar_texto, d.tipo_lugar)] += 1
    nuevos = 0
    existentes = [l["nombre"] for l in db.lugares.find({}, {"nombre": 1})] + [a for l in db.lugares.find({}, {"alias": 1}) for a in l.get("alias", [])]
    for (nombre, palabra), n in conteo.most_common():
        if n < minimo:
            break
        tipo = {"BARRIO": "barrio", "URBANIZACION": "barrio", "SECTOR": "sector", "VEREDA": "vereda", "CASERIO": "caserio"}[palabra]
        if process.extractOne(nombre, existentes, scorer=fuzz.ratio, score_cutoff=88):
            continue
        if db.lugares.find_one({"nombre": nombre, "tipo": tipo}):
            continue
        db.lugares.insert_one({"_id": bd.siguiente_id(db, "lugares"), "nombre": nombre, "tipo": tipo,
                               "zona": "urbana" if tipo == "barrio" else "rural", "lat": None, "lon": None, "alias": [],
                               "padre": "YONDO" if tipo == "barrio" else None, "fuente": "datos", "precision": None,
                               "geom": None, "editado": False, "creado_en": bd.ahora()})
        existentes.append(nombre)
        nuevos += 1
    return nuevos


def georreferenciar(db: Database, solo_ids: list[int] | None = None) -> dict:
    """Normaliza la dirección y ubica a cada persona. Respeta las ubicaciones puestas a mano."""
    grilla = GrillaCasco.desde_archivo()
    filtro = {**bd.ACTIVA, "geo_manual": {"$ne": True}}
    if solo_ids:
        filtro["_id"] = {"$in": solo_ids}

    def pasada() -> None:
        geo = Geocodificador(Nomenclator(bd.lugares(db)), grilla)
        ops = []
        for p in db.personas.find(filtro, {"direccion": 1}):
            d, u = geo.ubicar(p.get("direccion") or "")
            ops.append(UpdateOne({"_id": p["_id"]}, {"$set": {
                "direccion_norm": d.normalizada(u.lugar.nombre if u.lugar else None, u.lugar.tipo if u.lugar else None) or None,
                "lugar_id": u.lugar.id if u.lugar else None, "lugar_texto": d.lugar_texto, "zona": u.zona,
                "lat": u.lat, "lon": u.lon, "geo_precision": u.precision}}))
        for k in range(0, len(ops), 1000):
            db.personas.bulk_write(ops[k:k + 1000], ordered=False)

    pasada()
    # Barrios sin punto propio: la mediana de las direcciones con placa que caen en ellos
    sin_punto = {l["_id"] for l in db.lugares.find({"lat": None}, {"_id": 1})}
    puntos = defaultdict(list)
    for p in db.personas.find({**bd.ACTIVA, "geo_precision": "direccion", "lugar_id": {"$in": list(sin_punto)}},
                              {"lugar_id": 1, "lat": 1, "lon": 1}):
        puntos[p["lugar_id"]].append((p["lat"], p["lon"]))
    derivados = 0
    for lid, pts in puntos.items():
        if len(pts) >= 3:
            db.lugares.update_one({"_id": lid, "lat": None}, {"$set": {
                "lat": round(median(x[0] for x in pts), 6), "lon": round(median(x[1] for x in pts), 6),
                "precision": "derivado", "fuente_punto": f"mediana de {len(pts)} direcciones con placa"}})
            derivados += 1
    if derivados:
        pasada()
    c = Counter(p.get("geo_precision") or "sin_ubicar" for p in db.personas.find(bd.ACTIVA, {"geo_precision": 1}))
    return {"por_precision": dict(c), "barrios_derivados": derivados}
