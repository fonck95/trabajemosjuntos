"""Importación: de los Excel a la base única en MongoDB, cruzada y georreferenciada.

Se puede correr las veces que haga falta con archivos nuevos o actualizados:
* los trámites se identifican por su ID (o, si no traen ID, por ficha, fecha, tipo y nombre) y no se duplican;
* las personas de trámites por su nombre agrupado (también los nombres de las fichas que se unieron), y las de la
  base con cédula por la cédula;
* la importación solo completa campos vacíos: nunca pisa lo que se corrigió o enriqueció en el panel, tampoco lo que
  se edite mientras corre (escribe solo sus cambios sobre el documento actual, no el documento entero);
* las personas suprimidas (Ley 1581) no se vuelven a crear: sus filas se saltan y se cuentan en el resumen.

Para que sea rápida aun contra un MongoDB remoto, carga las personas en memoria, aplica todo y escribe por lotes.
"""
from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median

from pymongo import InsertOne, UpdateOne
from pymongo.database import Database
from pymongo.errors import BulkWriteError
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
    suprimidas_omitidas: int = 0
    no_guardadas: int = 0
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


def clave_contenido(ficha: str | None, fecha: str | None, tipo: str | None, nombre: str | None) -> str:
    """Identifica un trámite sin ID por su contenido (ficha, fecha, tipo y nombre normalizado) sin guardar el nombre."""
    return hashlib.sha1("|".join(x or "" for x in (ficha, fecha, tipo, nombre)).encode()).hexdigest()[:24]


class _Almacen:
    """Personas activas en memoria con índices por clave de trámites, cédula y trámite.

    Las fichas nuevas se insertan completas. De las que ya existían se anota solo lo que la importación cambia, y eso
    se escribe sobre el documento actual de la base y solo si sigue activa: lo editado en el panel mientras corre la
    importación no se pierde y una ficha suprimida o unida no revive."""

    LISTAS = ("fuentes", "listas", "claves_tramites")

    def __init__(self, db: Database):
        self.db = db
        self.docs: dict[int, dict] = {d["_id"]: d for d in db.personas.find(bd.ACTIVA)}
        self.por_clave: dict[str, int] = {}
        for i, d in self.docs.items():
            for c in d.get("claves_tramites") or []:
                self.por_clave.setdefault(c, i)
        self.por_clave.update({d["clave_tramites"]: i for i, d in self.docs.items() if d.get("clave_tramites")})
        self.por_cedula = {d["cedula"]: i for i, d in self.docs.items() if d.get("cedula")}
        self.por_tramite = {t["id_externo"]: i for i, d in self.docs.items() for t in d.get("tramites", []) if t.get("id_externo")}
        self.por_contenido = {t.get("clave") or clave_contenido(t.get("ficha"), t.get("fecha"), t.get("tipo"),
                                                                  d.get("clave_tramites") or d.get("nombre_norm")): i
                              for i, d in self.docs.items() for t in d.get("tramites", []) if not t.get("id_externo")}
        self.nuevas: set[int] = set()
        self.cambios: dict[int, dict] = {}
        self.coincidencias: list[dict] = []
        self.ids_libres: list[int] = []
        self.secreto = bd.clave_supresion(db)
        self.suprimidos = {x["_id"] for x in db.suprimidos.find({}, {"_id": 1})}

    # ── Personas suprimidas ──
    def suprimida(self, tipo: str, valor) -> bool:
        h = bd.huella(self.secreto, tipo, valor)
        return h is not None and h in self.suprimidos

    def bloquear(self, pares) -> None:
        self.suprimidos |= bd.registrar_huellas(self.db, pares, self.secreto)

    # ── Cambios ──
    def nueva(self, datos: dict, fuente: str) -> dict:
        if not self.ids_libres:  # reserva identificadores de a 500 para no pedir uno por persona
            primero = bd.siguiente_id(self.db, "personas", 500)
            self.ids_libres = list(range(primero, primero + 500))
        d = bd.nueva_persona(self.db, {**datos, "_id": self.ids_libres.pop(0)}, fuente)
        self.docs[d["_id"]] = d
        self.nuevas.add(d["_id"])
        if d.get("clave_tramites"):
            self.por_clave[d["clave_tramites"]] = d["_id"]
        if d.get("cedula"):
            self.por_cedula[d["cedula"]] = d["_id"]
        return d

    def _cambio(self, d: dict) -> dict | None:
        if d["_id"] in self.nuevas:
            return None
        return self.cambios.setdefault(d["_id"], {"set": {}, "tramites": [], "origen": {}, "contacto": None,
                                                  **{k: [] for k in self.LISTAS}})

    def completar(self, d: dict, datos: dict) -> list[str]:
        cambios = bd.completar_doc(d, datos)
        c = self._cambio(d)
        if c is not None:
            c["set"].update({k: d[k] for k in cambios})
        return cambios

    def fijar(self, d: dict, campo: str, valor) -> None:
        d[campo] = valor
        c = self._cambio(d)
        if c is not None:
            c["set"][campo] = valor

    def agregar(self, d: dict, campo: str, valor) -> bool:
        lista = d.setdefault(campo, [])
        if valor in lista:
            return False
        lista.append(valor)
        c = self._cambio(d)
        if c is not None:
            c[campo].append(valor)
        return True

    def tramite(self, d: dict, t: dict) -> None:
        d["tramites"].append(t)
        c = self._cambio(d)
        if c is not None:
            c["tramites"].append(t)

    def origen(self, d: dict, entrada: dict) -> bool:
        previa = next((o for o in d.get("origen", []) if o["fuente"] == entrada["fuente"] and o["clave"] == entrada["clave"]), None)
        if previa is not None and previa.get("datos") == entrada["datos"]:
            return False
        d["origen"] = [o for o in d.get("origen", []) if o is not previa] + [entrada]
        c = self._cambio(d)
        if c is not None:
            c["origen"][entrada["clave"]] = entrada
        return True

    def contacto(self, d: dict, fecha: str | None) -> bool:
        if not fecha or fecha <= (d.get("ultimo_contacto") or ""):
            return False
        d["ultimo_contacto"] = fecha
        c = self._cambio(d)
        if c is not None:
            c["contacto"] = fecha
        return True

    def guardar(self) -> int:
        """Escribe todo y devuelve cuántas fichas no se pudieron guardar (p. ej. porque en el panel se asignó la misma
        cédula a otra persona mientras corría la importación)."""
        ops = []
        for i in self.nuevas:
            d = self.docs[i]
            d["completitud"] = bd.completitud(d)
            ops.append(InsertOne(d))
        for i, c in self.cambios.items():
            if any(c[k] for k in ("set", "tramites", "origen", "contacto", *self.LISTAS)):
                ops.append(UpdateOne({"_id": i, **bd.ACTIVA}, _actualizacion(c)))
        fallidas = 0
        for k in range(0, len(ops), 1000):
            try:
                self.db.personas.bulk_write(ops[k:k + 1000], ordered=False)
            except BulkWriteError as e:
                errores = e.details.get("writeErrors", [])
                if any(x.get("code") != 11000 for x in errores):
                    raise
                fallidas += len(errores)
        self.nuevas.clear()
        self.cambios.clear()
        return fallidas

    def guardar_coincidencias(self) -> None:
        if not self.coincidencias:
            return
        primero = bd.siguiente_id(self.db, "coincidencias", len(self.coincidencias))
        for i, c in enumerate(self.coincidencias):
            self.db.coincidencias.update_one({"persona_id": c["persona_id"], "candidato_id": c["candidato_id"]},
                                             {"$setOnInsert": {"_id": primero + i, **c}}, upsert=True)
        self.coincidencias.clear()


def _actualizacion(c: dict) -> list[dict]:
    """Actualización (pipeline) con los cambios de la importación sobre el documento tal como está en la base: completa
    solo los campos que sigan vacíos y agrega trámites, fuentes, listas y el registro de origen."""
    s: dict = {"actualizado_en": {"$literal": bd.ahora()}}
    for k, v in c["set"].items():
        s[k] = {"$cond": [{"$in": [{"$ifNull": [f"${k}", None]}, [None, ""]]}, {"$literal": v}, f"${k}"]}
    for k in _Almacen.LISTAS:
        if c[k]:
            actual = {"$ifNull": [f"${k}", []]}
            s[k] = {"$concatArrays": [actual, {"$filter": {"input": {"$literal": c[k]}, "as": "x",
                                                           "cond": {"$not": [{"$in": ["$$x", actual]}]}}}]}
    if c["tramites"]:
        s["tramites"] = {"$concatArrays": [{"$ifNull": ["$tramites", []]}, {"$literal": c["tramites"]}]}
    if c["origen"]:
        quitar = {"$and": [{"$eq": ["$$o.fuente", "cedulas"]}, {"$in": ["$$o.clave", {"$literal": list(c["origen"])}]}]}
        s["origen"] = {"$concatArrays": [
            {"$filter": {"input": {"$ifNull": ["$origen", []]}, "as": "o", "cond": {"$not": [quitar]}}},
            {"$literal": list(c["origen"].values())}]}
    if c["contacto"]:
        s["ultimo_contacto"] = {"$max": ["$ultimo_contacto", {"$literal": c["contacto"]}]}
    return [{"$set": s}]


def importar(db: Database, rutas: list[Path], usuario: str | None = "sistema", nombres: list[str] | None = None) -> Resumen:
    res = Resumen()
    tramites: list[lectores.FilaTramite] = []
    cedulas: list[lectores.FilaCedula] = []
    for i, ruta in enumerate(rutas):
        nombre = (nombres or [])[i] if nombres and i < len(nombres) else Path(ruta).name
        try:  # en el servidor los archivos se llaman 0.xlsx, 1.xlsx…: el error debe decir cuál de los subidos falló
            tipo = lectores.tipo_de_archivo(ruta)
            if tipo == "tramites":
                filas = list(lectores.leer_tramites(ruta))
            elif tipo == "cedulas":
                filas = list(lectores.leer_cedulas(ruta))
            else:
                raise ValueError("faltan las columnas esperadas")
        except ValueError as e:
            raise ValueError(f"{nombre}: {e}") from e
        (tramites if tipo == "tramites" else cedulas).extend(filas)
        res.archivos.append({"archivo": nombre, "tipo": tipo, "filas": len(filas)})

    imp_id = bd.siguiente_id(db, "importaciones")
    alm = _Almacen(db)
    if tramites:
        _importar_tramites(alm, tramites, res)
    if cedulas:
        _importar_cedulas(alm, cedulas, imp_id, res)
    res.no_guardadas = alm.guardar()
    alm.guardar_coincidencias()
    bd.cerrar_coincidencias_imposibles(db)
    res.lugares_nuevos = registrar_lugares_de_datos(db)
    res.geo = georreferenciar(db)
    bd.recalcular_completitud(db)
    db.importaciones.insert_one({"_id": imp_id, "ts": bd.ahora(), "usuario": usuario,
                                 "archivo": ", ".join(a["archivo"] for a in res.archivos),
                                 "tipo": ", ".join(sorted({a["tipo"] for a in res.archivos})), "resumen": res.dict()})
    bd.auditar(db, usuario, "importar", "importacion", imp_id, res.dict())
    return res


def _importar_tramites(alm: _Almacen, filas, res: Resumen) -> None:
    grupos = cruce.agrupar_tramites(filas)
    pids: dict[str, int] = {}
    for g in grupos:
        ids = [f.id_externo for f in g.filas if f.id_externo]
        nombres = {g.clave, *(tx.nombre_norm(n) for n in g.nombres)}
        if any(alm.suprimida("clave", n) for n in nombres) or any(alm.suprimida("tramite", i) for i in ids):
            # Persona suprimida: no se vuelve a crear, y sus otras escrituras e IDs quedan bloqueados también
            alm.bloquear([*(("clave", n) for n in nombres), *(("tramite", i) for i in ids)])
            res.suprimidas_omitidas += len(g.filas)
            continue
        u = g.ultima
        contenido = {id(f): clave_contenido(f.ficha, f.fecha, f.tramite, tx.nombre_norm(f.nombre))
                     for f in g.filas if not f.id_externo}
        pid = alm.por_clave.get(g.clave)
        if pid is None:  # ¿alguno de sus trámites ya está en la base (p. ej. tras una fusión)?
            pid = next((alm.por_tramite[i] for i in ids if i in alm.por_tramite), None)
        if pid is None:
            pid = next((alm.por_contenido[k] for k in contenido.values() if k in alm.por_contenido), None)
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
            if g.clave not in alm.por_clave:  # otra escritura del nombre (de una ficha unida): se recuerda
                alm.agregar(d, "claves_tramites", g.clave)
                alm.por_clave[g.clave] = pid
        alm.completar(d, datos)
        alm.agregar(d, "fuentes", "tramites")
        nuevos = 0
        for f in g.filas:
            k = contenido.get(id(f))
            if (f.id_externo in alm.por_tramite) if f.id_externo else (k in alm.por_contenido):
                continue
            t = {"id_externo": f.id_externo or None, "ficha": f.ficha, "fecha": f.fecha, "tipo": f.tramite,
                 "direccion": f.direccion, "telefono": ";".join(f.telefonos), "correo": f.correo, "paquete": f.paquete}
            if f.id_externo:
                alm.por_tramite[f.id_externo] = d["_id"]
            else:
                t["clave"] = k
                alm.por_contenido[k] = d["_id"]
            alm.tramite(d, t)
            nuevos += 1
        res.tramites_nuevos += nuevos
        alm.contacto(d, max((f.fecha for f in g.filas if f.fecha), default=None))
        pids[g.clave] = d["_id"]
    # Mismo nombre con fichas y teléfonos distintos quedó como dos personas: que el administrador lo confirme
    for g in grupos:
        a, b = pids.get(g.clave), pids.get(g.separado_de) if g.separado_de else None
        if a and b and a != b:
            alm.coincidencias.append({"persona_id": a, "candidato_id": b, "puntaje": 1.0, "estado": "pendiente",
                                      "detalle": {"homonimo": True, "puntaje_nombre": 1.0, "palabras": len(g.tokens()),
                                                  "telefono": False, "correo": False}})


def _importar_cedulas(alm: _Almacen, filas, imp_id: int, res: Resumen) -> None:
    db = alm.db
    nuevas, repetidas, vistas = [], [], set()
    for f in filas:
        if alm.suprimida("cedula", f.cedula) or alm.suprimida("clave", f.nombre):
            res.suprimidas_omitidas += 1
            continue
        pid = alm.por_cedula.get(f.cedula)
        if pid is not None:
            _completar_desde_cedula(alm, alm.docs[pid], f, imp_id)
            res.cedulas_ya_existian += 1
        elif f.cedula in vistas:  # la misma cédula otra vez en esta importación: completa la ficha que resulte
            repetidas.append(f)
        else:
            vistas.add(f.cedula)
            nuevas.append(f)
    if nuevas:
        _cruzar_cedulas(alm, nuevas, imp_id, res)
    for f in repetidas:
        _completar_desde_cedula(alm, alm.docs[alm.por_cedula[f.cedula]], f, imp_id)
        res.cedulas_ya_existian += 1


def _cruzar_cedulas(alm: _Almacen, nuevas, imp_id: int, res: Resumen) -> None:
    cands = []
    for d in alm.docs.values():
        if d.get("cedula"):
            continue
        tels = {d.get("telefono"), d.get("telefono2")} - {None, ""}
        tels |= {t for tr in d.get("tramites", []) for t in (tr.get("telefono") or "").split(";") if t}
        cands.append(_Cand(d["_id"], d["nombre"], tels, {d["correo"]} if d.get("correo") else set()))
    resultados = cruce.cruzar(cands, nuevas)
    # Varias cédulas que se unirían solas con la misma ficha: gana la de mayor puntaje, sin importar el orden del
    # archivo. Si empatan del todo, ninguna se une sola y todas van a revisión.
    por_cand: dict[int, list] = defaultdict(list)
    for r in resultados:
        if r.estado == "auto" and r.mejor:
            por_cand[cands[r.mejor.indice].id].append(r)
    ganadoras, tomados = set(), set()
    def puntos(r: cruce.ResultadoCruce) -> tuple[float, float]:
        return r.mejor.puntaje, r.mejor.puntaje_nombre

    for cid, rs in por_cand.items():
        rs.sort(key=puntos, reverse=True)
        if len(rs) == 1 or puntos(rs[0]) > puntos(rs[1]):
            ganadoras.add(id(rs[0]))
            tomados.add(cid)
    for r in resultados:
        f, m = r.fila, r.mejor
        if id(r) in ganadoras:
            d = alm.docs[cands[m.indice].id]
            alm.fijar(d, "cedula", f.cedula)
            alm.por_cedula[f.cedula] = d["_id"]
            _completar_desde_cedula(alm, d, f, imp_id)
            bd.auditar(alm.db, "sistema", "cruce_automatico", "persona", d["_id"],
                       {"cedula": f.cedula, "nombre_base_cedulas": f.nombre, "puntaje": m.puntaje,
                        "telefono": m.telefono, "correo": m.correo})
            res.cedulas_unidas_auto += 1
            continue
        d = alm.nueva({"nombre": f.nombre, "cedula": f.cedula}, "cedulas")
        _completar_desde_cedula(alm, d, f, imp_id)
        res.personas_nuevas += 1
        # A revisión contra los candidatos que siguen libres: una ficha que ya recibió otra cédula no se podría unir
        props = [c for c in r.candidatos if c.puntaje >= cruce.UMBRAL_REVISION and cands[c.indice].id not in tomados]
        if r.estado in ("auto", "revision") and props:
            res.cedulas_en_revision += 1
            alm.coincidencias += [{"persona_id": d["_id"], "candidato_id": cands[c.indice].id, "puntaje": c.puntaje,
                                   "detalle": {"puntaje_nombre": c.puntaje_nombre, "palabras": c.palabras,
                                               "telefono": c.telefono, "correo": c.correo}, "estado": "pendiente"}
                                  for c in props]
        else:
            res.cedulas_sin_coincidencia += 1


def _completar_desde_cedula(alm: _Almacen, d: dict, f: lectores.FilaCedula, imp_id: int) -> None:
    tels = f.telefonos
    alm.completar(d, {
        "telefono": tels[0] if tels else None, "telefono2": tels[1] if len(tels) > 1 else None, "correo": f.correo or None,
        "sexo": f.sexo or None, "edad": f.edad, "direccion": f.direccion or None,
        "puesto_votacion": f.puesto or None, "mesa": f.mesa or None,
    })
    alm.agregar(d, "fuentes", "cedulas")
    for lista in f.listas:
        alm.agregar(d, "listas", lista)
    datos = {k: v for k, v in f.__dict__.items() if v not in (None, "", [], {})}
    alm.origen(d, {"fuente": "cedulas", "clave": f.cedula, "datos": datos, "importacion_id": imp_id})


# ───────────────────────────── Lugares y georreferenciación ─────────────────────────────

def registrar_lugares_de_datos(db: Database, minimo: int = 3) -> int:
    """Barrios y veredas que aparecen escritos varias veces y no están en el nomenclátor: se agregan sin punto
    (el punto sale de las direcciones con placa o lo ubica el administrador en el mapa). Un sector cuyas direcciones
    son casi todas placas del casco urbano queda urbano (con padre YONDO), como los barrios."""
    nom = Nomenclator(bd.lugares(db))
    grilla = GrillaCasco.desde_archivo()
    conteo: Counter = Counter()
    en_casco: Counter = Counter()
    for p in db.personas.find({**bd.ACTIVA, "direccion": {"$ne": None}}, {"direccion": 1}):
        d = leer(p["direccion"])
        if not d.lugar_texto or d.tipo_lugar not in ("BARRIO", "VEREDA", "URBANIZACION", "SECTOR", "CASERIO"):
            continue
        r = grilla.ubicar_direccion(d) if d.tiene_placa else None
        placa_casco = bool(r and r[2] <= 2.5)
        lugar, _, _ = nom.reconocer(d, casco=placa_casco)
        if lugar is None and len(d.lugar_texto) >= 3:
            conteo[(d.lugar_texto, d.tipo_lugar)] += 1
            en_casco[(d.lugar_texto, d.tipo_lugar)] += placa_casco
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
        urbano = tipo == "barrio" or (tipo == "sector" and en_casco[(nombre, palabra)] * 3 >= n * 2)
        db.lugares.insert_one({"_id": bd.siguiente_id(db, "lugares"), "nombre": nombre, "tipo": tipo,
                               "zona": "urbana" if urbano else "rural", "lat": None, "lon": None, "alias": [],
                               "padre": "YONDO" if urbano else None, "fuente": "datos", "precision": None,
                               "geom": None, "editado": False, "creado_en": bd.ahora()})
        existentes.append(nombre)
        nuevos += 1
    return nuevos


def georreferenciar(db: Database, solo_ids: list[int] | None = None) -> dict:
    """Normaliza la dirección y ubica a cada persona. Respeta lo puesto a mano: un punto en el mapa no se toca, y un
    barrio o vereda elegido a mano se conserva (la persona sigue el punto de ese lugar, o el de su placa si es urbano)."""
    grilla = GrillaCasco.desde_archivo()
    filtro = {**bd.ACTIVA, "geo_manual": {"$nin": list(bd.PUNTO_MANUAL)}}
    if solo_ids:
        filtro["_id"] = {"$in": solo_ids}

    def pasada() -> None:
        lugares = bd.lugares(db)
        por_id = {l.id: l for l in lugares}
        geo = Geocodificador(Nomenclator(lugares), grilla)
        ops = []
        for p in db.personas.find(filtro, {"direccion": 1, "geo_manual": 1, "lugar_id": 1}):
            d, u = geo.ubicar(p.get("direccion") or "")
            lg = por_id.get(p.get("lugar_id")) if p.get("geo_manual") == "lugar" else None
            if lg is not None:
                cambios = {"direccion_norm": d.normalizada(lg.nombre, lg.tipo) or None, "lugar_id": lg.id,
                           "lugar_texto": d.lugar_texto, "zona": lg.zona}
                if u.precision == "direccion" and lg.zona == "urbana":
                    cambios.update({"lat": u.lat, "lon": u.lon, "geo_precision": u.precision})
                else:
                    cambios.update({"lat": lg.lat, "lon": lg.lon, "geo_precision": lg.tipo if lg.lat is not None else None})
            else:
                lg = u.lugar
                cambios = {"direccion_norm": d.normalizada(lg.nombre if lg else None, lg.tipo if lg else None) or None,
                           "lugar_id": lg.id if lg else None, "lugar_texto": d.lugar_texto, "zona": u.zona,
                           "lat": u.lat, "lon": u.lon, "geo_precision": u.precision}
            ops.append(UpdateOne({"_id": p["_id"]}, {"$set": cambios}))
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
