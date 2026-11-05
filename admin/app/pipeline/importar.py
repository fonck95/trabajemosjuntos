"""Importación: de los Excel a la base única en MongoDB, cruzada y georreferenciada.

Se puede correr las veces que haga falta con archivos nuevos o actualizados:
* los trámites se identifican por su ID (o, si no traen ID, por ficha, fecha, tipo y nombre) y no se duplican;
* las personas de trámites por su nombre agrupado (también los nombres de las fichas que se unieron); las de las
  fuentes con cédula (base unificada, planilla de campo) por la cascada de identidad de 2.3, con la cédula como
  identificador definitivo: dos cédulas distintas nunca se unen y una cédula que ya existe nunca cambia;
* cada campo guarda su procedencia: un campo vacío se llena; uno con otro valor solo lo reemplaza una fuente de más
  confianza que no sea una persona, y el valor que no queda pasa a `alternos` (nada se pierde). Todo se decide en la
  escritura, con condiciones sobre lo guardado: lo que se edite en el panel mientras corre no se pisa;
* los teléfonos de todas las fuentes se suman a la lista `telefonos` (un número ya presente no cambia de estado);
* las personas suprimidas (Ley 1581) no se vuelven a crear, y a quien no autorizó no se le agrega nada;
* una sola importación a la vez (turno con dueño en `meta.importando`).

Para que sea rápida aun contra un MongoDB remoto, carga las personas en memoria, aplica todo y escribe por lotes.
"""
from __future__ import annotations

import copy
import hashlib
import json
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from types import SimpleNamespace

from fastapi import HTTPException
from pymongo import InsertOne, UpdateOne
from pymongo.database import Database
from pymongo.errors import BulkWriteError, DuplicateKeyError
from rapidfuzz import fuzz, process

from .. import db as bd
from .. import modelo
from . import cruce, lectores
from . import texto as tx
from .direcciones import Nomenclator, leer
from .fuentes import Registro
from .geocodificador import Geocodificador, GrillaCasco

TURNO_MIN = 15
UMBRAL_MISMA = 0.70          # cédula exacta: mismo nombre (o 0,60 con teléfono o correo en común)
UMBRAL_MISMA_EVIDENCIA = 0.60
UMBRAL_DIGITACION = 0.93     # otra ficha con una cédula a un dígito y casi el mismo nombre


class ImportacionEnCurso(HTTPException):
    """Otra importación tiene el turno: 409 `importando` (la API lo responde tal cual)."""

    def __init__(self):
        super().__init__(409, {"mensaje": "Ya hay una importación en curso. Intente de nuevo cuando termine.",
                               "codigo": "importando"})


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
    registros_por_fuente: dict = field(default_factory=dict)
    registros_unidos_auto: int = 0
    registros_en_revision: int = 0
    telefonos_agregados: int = 0
    alternos_agregados: int = 0
    conflictos_cedula: int = 0
    omitidas_sin_autorizacion: int = 0
    votacion_por_confirmar: int = 0
    autorizaciones_por_confirmar: int = 0
    planilleros_desconocidos: list = field(default_factory=list)

    def dict(self) -> dict:
        return copy.deepcopy(self.__dict__)


@dataclass
class _Cand:
    id: int
    nombre: str
    telefonos: set
    correos: set
    cedula: str | None = None


def _base(clave: str) -> str:
    """«JOSE GARCIA#0589300000002» → «JOSE GARCIA»: la clave de un homónimo separado lleva su ficha."""
    return clave.split("#", 1)[0]


def clave_contenido(ficha: str | None, fecha: str | None, tipo: str | None, nombre: str | None) -> str:
    """Identifica un trámite sin ID por su contenido (ficha, fecha, tipo y nombre normalizado) sin guardar el nombre."""
    return hashlib.sha1("|".join(x or "" for x in (ficha, fecha, tipo, nombre)).encode()).hexdigest()[:24]


def _lit(v) -> dict:
    return {"$literal": v}


# Campo de la ficha → clave canónica de la auditoría (indicadores)
CANONICOS = {"votacion": "puesto", "fecha_nacimiento": "edad", "telefonos": "telefono", "tipo_documento": "cedula"}
# Lo que se fotografía de una ficha antes de cambiarla: sirve para las condiciones de la escritura y los completados
_FOTO = (*modelo.CAMPOS_PROCEDENCIA, "procedencia", "puesto_votacion", "mesa", "edad_ref", "telefonos", "telefono",
         "telefono2", "lugar_id", "punto", "lat", "lon", "consentimiento", "personas_hogar", "jefe_hogar", "estrato",
         *modelo.CAMPOS_AVANCE)


class _Almacen:
    """Personas activas en memoria con índices por clave de trámites, cédula, cédula anterior, llave de fila y trámite.

    Las fichas nuevas se insertan completas. De las que ya existían se anota solo lo que la importación cambia y una
    foto de lo que había, y eso se escribe sobre el documento actual de la base, con condiciones sobre lo guardado y
    solo si sigue activa: lo editado en el panel mientras corre la importación no se pierde, una ficha suprimida o
    unida no revive y a quien dijo que no autoriza no se le agregan datos."""

    LISTAS = ("fuentes", "listas", "claves_tramites")

    def __init__(self, db: Database, ids=None, *, actor: dict | None = None):
        self.db = db
        filtro = dict(bd.ACTIVA) if ids is None else {"_id": {"$in": list(ids)}, **bd.ACTIVA}
        self.docs: dict[int, dict] = {d["_id"]: d for d in db.personas.find(filtro)}
        self.por_clave: dict[str, int] = {}
        for i, d in self.docs.items():
            for c in d.get("claves_tramites") or []:
                self.por_clave.setdefault(c, i)
        self.por_clave.update({d["clave_tramites"]: i for i, d in self.docs.items() if d.get("clave_tramites")})
        # Personas por el nombre de su grupo de trámites sin el «#ficha» de los homónimos separados
        self.por_base: dict[str, set[int]] = defaultdict(set)
        for c, i in self.por_clave.items():
            self.por_base[_base(c)].add(i)
        self.por_cedula = {d["cedula"]: i for i, d in self.docs.items() if d.get("cedula")}
        self.por_anterior = {c: i for i, d in self.docs.items() for c in d.get("cedulas_anteriores") or []}
        self.por_llave: dict[tuple, int] = {}
        for i, d in self.docs.items():
            for o in d.get("origen") or []:
                if o.get("clave"):
                    self.por_llave.setdefault((o.get("fuente"), o["clave"]), i)
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
        self.ts = bd.ahora()
        self.hoy = modelo.hoy_local().isoformat()
        self.actor = actor or {"uid": 0, "usuario": "sistema", "rol": "admin"}
        ajustes = modelo.leer_ajustes(db)
        self.vigente = ajustes["eleccion_vigente"]
        self.texto_version = (ajustes.get("aviso_privacidad") or {}).get("version")
        self.puestos = bd.puestos_vigentes(db, self.vigente)
        self.res = Resumen()
        self.conflictos: list[dict] = []
        self._claves_conflicto: set[str] = set()
        self.eventos: list[tuple] = []          # autorizaciones de la planilla, se insertan después de guardar
        self.auditorias: dict[int, dict] = {}  # personas de la planilla: {capturado_por, accion, campos, completados}
        self.cruces: list[tuple] = []          # auditorías de cruce automático, después de guardar
        self.cedulas_escritas: dict[int, tuple] = {}  # pid → (cédula, registro, fuente): se verifican al guardar
        self.digitacion: list[tuple] = []
        self.fallidas: set[int] = set()
        self._comparador = None
        self._planilleros: dict | None = None

    # ── Personas suprimidas ──
    def suprimida(self, tipo: str, valor) -> bool:
        h = bd.huella(self.secreto, tipo, valor)
        return h is not None and h in self.suprimidos

    def bloquear(self, pares) -> None:
        self.suprimidos |= bd.registrar_huellas(self.db, pares, self.secreto)

    # ── Altas ──
    def creador(self, capturado_por: int | None = None) -> dict:
        c = {"uid": self.actor["uid"], "usuario": self.actor["usuario"], "rol": self.actor["rol"]}
        if capturado_por is not None:
            c["capturado_por"] = capturado_por
        return c

    def nueva(self, datos: dict, fuente: str) -> dict:
        if not self.ids_libres:  # reserva identificadores de a 500 para no pedir uno por persona
            primero = bd.siguiente_id(self.db, "personas", 500)
            self.ids_libres = list(range(primero, primero + 500))
        d = bd.nueva_persona(self.db, {**datos, "_id": self.ids_libres.pop(0)}, fuente)
        self.docs[d["_id"]] = d
        self.nuevas.add(d["_id"])
        if d.get("clave_tramites"):
            self.por_clave[d["clave_tramites"]] = d["_id"]
            self.por_base[_base(d["clave_tramites"])].add(d["_id"])
        if d.get("cedula"):
            self.por_cedula[d["cedula"]] = d["_id"]
        return d

    def por_evidencia(self, base: str, g: cruce.PersonaTramites, ids: list[str], contenido) -> int | None:
        """Entre homónimos, la ficha a la que pertenece el grupo `g` por sus datos y no por su nombre: la que ya tiene
        alguno de sus trámites o, si no, la que más fichas y teléfonos comparte con él entre las del mismo nombre."""
        votos = Counter(self.por_tramite[i] for i in ids if i in self.por_tramite)
        votos.update(self.por_contenido[k] for k in contenido if k in self.por_contenido)
        if votos:
            return votos.most_common(1)[0][0]
        fichas, tels = set(g.fichas), set(g.telefonos)
        comunes = []
        for pid in self.por_base.get(base, ()):
            d = self.docs[pid]
            sus_fichas = {d.get("ficha"), *(t.get("ficha") for t in d.get("tramites", []))}
            n = len(fichas & sus_fichas) + len(tels & self.numeros(d))
            if n:
                comunes.append((n, pid))
        comunes.sort(reverse=True)
        if comunes and (len(comunes) == 1 or comunes[0][0] > comunes[1][0]):
            return comunes[0][1]
        return None

    def proponer(self, a: int, b: int, puntaje: float, detalle: dict, motivo: str) -> None:
        """Coincidencia pendiente entre dos fichas, si el par no se propuso ya (en cualquier orden): uno rechazado no
        vuelve a revisión al reimportar."""
        if any({c["persona_id"], c["candidato_id"]} == {a, b} for c in self.coincidencias):
            return
        if self.db.coincidencias.find_one({"$or": [{"persona_id": a, "candidato_id": b},
                                                   {"persona_id": b, "candidato_id": a}]}, {"_id": 1}):
            return
        self.coincidencias.append({"persona_id": a, "candidato_id": b, "puntaje": puntaje, "estado": "pendiente",
                                   "detalle": detalle, "motivo": motivo})

    # ── Lectura de una ficha ──
    def numeros(self, d: dict) -> set:
        """Todos sus números: la lista, los heredados y los de los trámites."""
        tels = {t.get("numero") for t in modelo.telefonos_de(d)} | {d.get("telefono"), d.get("telefono2")}
        tels |= {t for tr in d.get("tramites", []) for t in (tr.get("telefono") or "").split(";") if t}
        return tels - {None, ""}

    def comparador(self) -> cruce.ComparadorNombres:
        if self._comparador is None:
            self._comparador = cruce.ComparadorNombres([tx.tokens_nombre(d.get("nombre")) for d in self.docs.values()])
        return self._comparador

    def puntaje(self, r: Registro, d: dict) -> tuple[float, bool]:
        """(mejor puntaje del nombre de la fila contra los nombres de la ficha, ¿comparten teléfono o correo?)."""
        toks = tx.tokens_nombre(r.nombre)
        nombres = [d.get("nombre"), d.get("clave_tramites"), *(d.get("claves_tramites") or []),
                   *((o.get("datos") or {}).get("nombre") for o in d.get("origen") or [])]
        comp = self.comparador()
        mejor = max((comp.puntaje(toks, tx.tokens_nombre(n))[0] for n in nombres if n), default=0.0)
        evidencia = bool(set(r.telefonos) & self.numeros(d)) or bool(r.correo and r.correo == d.get("correo"))
        return mejor, evidencia

    @staticmethod
    def es_no(d: dict) -> bool:
        return d.get("consentimiento") == "no"

    # ── Cambios ──
    def _cambio(self, d: dict) -> dict | None:
        if d["_id"] in self.nuevas:
            return None
        c = self.cambios.get(d["_id"])
        if c is None:
            c = self.cambios[d["_id"]] = {
                "foto": {k: copy.deepcopy(d.get(k)) for k in _FOTO}, "proc": set(), "simples": {}, "tramites": [],
                "origen": {}, "contacto": None, "telefonos": [], "alternos": [], "cedula": None, "cedula_origen": None,
                "datos": False, "campos": set(), **{k: [] for k in self.LISTAS}}
        return c

    def _alterno(self, campo: str, valor, fuente: str | None) -> dict:
        return {"campo": campo, "valor": modelo.comparable(campo, valor), "fuente": fuente or "panel", "ts": self.ts,
                "uid": self.actor["uid"]}

    def _agregar_alterno(self, d: dict, entrada: dict, c: dict | None) -> None:
        actuales = d.get("alternos") if isinstance(d.get("alternos"), list) else []
        if any(a.get("campo") == entrada["campo"] and a.get("valor") == entrada["valor"] for a in actuales):
            return
        d["alternos"] = [*actuales, entrada][-100:]
        if c is not None:
            c["alternos"].append(entrada)
            c["datos"] = True
        self.res.alternos_agregados += 1

    def _poner(self, d: dict, c: dict | None, campo: str, valor, fuente: str) -> None:
        d[campo] = copy.deepcopy(valor)
        if not isinstance(d.get("procedencia"), dict):
            d["procedencia"] = {}
        d["procedencia"][campo] = {"fuente": fuente, "ts": self.ts, "uid": self.actor["uid"]}
        if campo == "votacion":
            d.update(modelo.derivar_votacion(valor))
        if campo == "edad":
            d["edad_ref"] = self.hoy
        if campo in ("edad", "fecha_nacimiento"):
            d.update(modelo.calcular_nac(d))
        if c is not None:
            c["proc"].add(campo)
            c["campos"].add(CANONICOS.get(campo, campo))
            c["datos"] = True

    def aplicar(self, d: dict, campo: str, valor, fuente: str) -> None:
        """Reglas de 1.5 para un campo con procedencia (gemelo en memoria de la escritura condicional)."""
        if modelo.vacio(valor):
            return
        c = self._cambio(d)
        actual = modelo.valor_campo(d, campo)
        if modelo.vacio(actual):
            self._poner(d, c, campo, valor, fuente)
            return
        if modelo.comparable(campo, actual) == modelo.comparable(campo, valor):
            return
        guardada = modelo.fuente_de(d, campo)
        if modelo.puede_reemplazar(guardada, fuente):
            # El anterior va a alternos; si era el de la base, lo escribe la condición de la escritura
            self._agregar_alterno(d, self._alterno(campo, actual, guardada),
                                  c if (c is not None and campo in c["proc"]) else None)
            self._poner(d, c, campo, valor, fuente)
        else:
            self._agregar_alterno(d, self._alterno(campo, valor, fuente), c)

    def simple(self, d: dict, campo: str, valor) -> None:
        """Campo sin procedencia: solo se llena si está vacío."""
        if modelo.vacio(valor) or not modelo.vacio(d.get(campo)):
            return
        d[campo] = valor
        c = self._cambio(d)
        if c is not None:
            c["simples"][campo] = valor
            c["campos"].add(campo)
            c["datos"] = True

    def fijar_cedula(self, d: dict, cedula: str, origen: str, fuente: str, r: Registro | None = None) -> None:
        """La cédula solo completa una ficha sin cédula, con una escritura condicional (`cedula: null`)."""
        if d.get("cedula") or self.por_cedula.get(cedula, d["_id"]) != d["_id"]:
            return
        c = self._cambio(d)
        d["cedula"], d["cedula_origen"] = cedula, origen
        if not isinstance(d.get("procedencia"), dict):
            d["procedencia"] = {}
        d["procedencia"]["cedula"] = {"fuente": fuente, "ts": self.ts, "uid": self.actor["uid"]}
        self.por_cedula[cedula] = d["_id"]
        if c is not None:
            c.update(cedula=cedula, cedula_origen=origen, datos=True)
            c["campos"].add("cedula")
            self.cedulas_escritas[d["_id"]] = (cedula, r, fuente)

    def agregar(self, d: dict, campo: str, valor) -> bool:
        lista = d.setdefault(campo, [])
        if valor in lista:
            return False
        lista.append(valor)
        c = self._cambio(d)
        if c is not None:
            c[campo].append(valor)
            c["datos"] = True
            if campo == "listas":
                c["campos"].add("listas")
        return True

    def telefonos(self, d: dict, nuevos: list[dict]) -> None:
        """Suma los números a la lista (un número ya presente solo gana fuentes y última vez: su estado no cambia)."""
        nuevos = [n for n in nuevos if n.get("numero")]
        if not nuevos:
            return
        c = self._cambio(d)
        actual = modelo.reconciliar_telefonos(d) if c is not None else modelo.telefonos_de(d)
        unidos = modelo.unir_telefonos(actual, nuevos)
        if unidos == actual:
            return
        presentes = {t.get("numero") for t in actual}
        agregados = {n["numero"] for n in nuevos} - presentes
        self.res.telefonos_agregados += len(agregados)
        d["telefonos"] = unidos
        d.update(modelo.derivar_telefonos(unidos))
        if c is not None:
            c["telefonos"].extend(nuevos)
            c["datos"] = True
            if agregados:
                c["campos"].add("telefono")

    def tramite(self, d: dict, t: dict) -> None:
        d["tramites"].append(t)
        c = self._cambio(d)
        if c is not None:
            c["tramites"].append(t)
            c["datos"] = True

    def origen(self, d: dict, entrada: dict) -> bool:
        clave = (entrada["fuente"], entrada["clave"])
        previa = next((o for o in d.get("origen", []) if (o.get("fuente"), o.get("clave")) == clave), None)
        self.por_llave[clave] = d["_id"]
        if previa is not None and previa.get("datos") == entrada["datos"]:
            return False
        d["origen"] = [o for o in d.get("origen", []) if o is not previa] + [entrada]
        c = self._cambio(d)
        if c is not None:
            c["origen"][clave] = entrada
        return True

    def origen_minimo(self, d: dict, fuente: str, clave: str, imp_id: int, contar: bool = True) -> None:
        """A quien no autorizó solo se le anota de dónde viene la fila (sin datos), para no duplicarlo."""
        if contar:
            self.res.omitidas_sin_autorizacion += 1
        if any((o.get("fuente"), o.get("clave")) == (fuente, clave) for o in d.get("origen", [])):
            self.por_llave[(fuente, clave)] = d["_id"]
            return
        self.origen(d, {"fuente": fuente, "clave": clave, "importacion_id": imp_id, "datos": {}})

    def contacto(self, d: dict, fecha: str | None) -> bool:
        if not fecha or fecha <= (d.get("ultimo_contacto") or ""):
            return False
        d["ultimo_contacto"] = fecha
        c = self._cambio(d)
        if c is not None:
            c["contacto"] = fecha
            c["datos"] = True
        return True

    # ── Filas de las fuentes con cédula ──
    def capturador(self, r: Registro, capturado_por: int | None) -> int | None:
        """El planillero de la fila si existe y está activo; si no, el «Capturado por» del formulario (y el nombre
        desconocido queda en el resumen)."""
        if self._planilleros is None:
            self._planilleros = {u["usuario"]: u["_id"] for u in self.db.usuarios.find(
                {"rol": "planillero", "activo": True}, {"usuario": 1})}
        if r.planillero:
            uid = self._planilleros.get(r.planillero)
            if uid is not None:
                return uid
            if r.planillero not in self.res.planilleros_desconocidos:
                self.res.planilleros_desconocidos.append(r.planillero)
        return capturado_por

    def completar_registro(self, d: dict, r: Registro, ctx: tuple) -> None:
        """Completa la ficha con la fila según 1.5 (a quien no autorizó, solo el origen mínimo)."""
        fuente, imp_id, cap = ctx[:3]
        if self.es_no(d):
            self.origen_minimo(d, fuente, r.clave_fila, imp_id)
            return
        if r.autorizacion == "no":  # «No autoriza»: solo nombre y cédula, y el evento «no»
            if r.cedula:
                self.fijar_cedula(d, r.cedula, fuente, fuente, r)
            self.origen_minimo(d, fuente, r.clave_fila, imp_id, contar=False)
            self.anotar(d, r, ctx)
            return
        if r.cedula:
            self.fijar_cedula(d, r.cedula, fuente, fuente, r)
        if r.cedula and d.get("cedula") == r.cedula:
            self.aplicar(d, "tipo_documento", r.tipo_documento, fuente)
        for campo in ("sexo", "edad", "fecha_nacimiento", "correo", "direccion"):
            self.aplicar(d, campo, getattr(r, campo), fuente)
        planilla = fuente == "planilla"
        v = modelo.armar_votacion(r.puesto_texto, r.mesa_texto, self.puestos, fuente=fuente,
                                  eleccion=self.vigente if planilla else None,
                                  estado="sin_verificar" if planilla else "por_confirmar",
                                  municipio=r.datos.get("municipio"),
                                  registrado_por=cap if cap is not None else self.actor["uid"], registrado_en=self.ts)
        if v:
            self.aplicar(d, "votacion", v, fuente)
            if v["estado"] == "por_confirmar":
                self.res.votacion_por_confirmar += 1
        fecha = r.fecha or self.hoy
        self.telefonos(d, [modelo.telefono_nuevo(n, bd.FUENTE_TELEFONO.get(fuente, fuente), fecha, agregado_por=cap)
                           for n in r.telefonos])
        for lista in r.listas:
            self.agregar(d, "listas", lista)
        self.simple(d, "observaciones", r.observaciones)
        self.agregar(d, "fuentes", fuente)
        self.origen(d, {"fuente": fuente, "clave": r.clave_fila, "cedula": r.cedula, "datos": r.datos,
                        "importacion_id": imp_id})
        if "cedula_repetida" in r.datos or "cedula_digitada" in r.datos:
            self.conflicto("posible_digitacion", r, d["_id"], ctx,
                           cedula=r.datos.get("cedula_digitada") or r.datos.get("cedula_repetida"))
        self.anotar(d, r, ctx)

    def anotar(self, d: dict, r: Registro, ctx: tuple) -> None:
        """Planilla: la persona va a la auditoría por persona y, si la fila trae autorización, al evento."""
        fuente, imp_id, cap, archivo, sha = ctx
        if fuente != "planilla":
            return
        self.auditorias.setdefault(d["_id"], {})["capturado_por"] = cap
        if r.autorizacion in ("si", "no") and (r.autorizacion == "no" or not self.es_no(d)):
            self.eventos.append((d["_id"], r, cap, archivo, sha, imp_id))

    def nueva_desde(self, r: Registro, ctx: tuple) -> dict:
        fuente, imp_id, cap = ctx[:3]
        d = self.nueva({"nombre": r.nombre, "creado_por": self.creador(cap if fuente == "planilla" else None)}, fuente)
        self.completar_registro(d, r, ctx)
        return d

    def conflicto(self, motivo: str, r: Registro, pid: int, ctx: tuple, cedula: str | None = None,
                  puntaje: float | None = None, otra: int | None = None) -> None:
        """Conflicto de cédula para que el administrador decida (nunca se mezcla nada). La clave evita duplicarlo al
        reimportar, y uno descartado no vuelve."""
        fuente, imp_id = ctx[0], ctx[1]
        ced = cedula or r.cedula
        clave = hashlib.sha1(f"{motivo}|{ced}|{pid}|{fuente}|{r.clave_fila}".encode()).hexdigest()
        if clave in self._claves_conflicto:
            return
        self._claves_conflicto.add(clave)
        self.conflictos.append({
            "clave": clave, "cedula": ced, "persona_id": pid, "motivo": motivo, "fuente": fuente,
            "importacion_id": imp_id, "registro": r.dict(), "puntaje_nombre": round(puntaje, 4) if puntaje is not None else None,
            "otra_persona": otra, "estado": "pendiente", "creado_por": self.actor["uid"], "creado_en": self.ts,
            "resuelto_por": None, "resuelto_en": None, "resolucion": None})

    # ── Escritura ──
    def _escritura(self, i: int, c: dict) -> tuple[list | None, dict | None]:
        """Actualización (pipeline) y filtro con los cambios de la importación sobre el documento tal como está en la
        base. Cada campo se escribe con una condición sobre lo guardado (1.5)."""
        d = self.docs[i]
        if not (c["datos"] or c["origen"]):
            return None, None
        foto = c["foto"]
        s: dict = {"actualizado_en": _lit(self.ts)}
        proc: list = []
        alt: list = [_lit(c["alternos"])] if c["alternos"] else []
        conds: dict = {}
        for campo in sorted(c["proc"]):
            antes = modelo.valor_campo(foto, campo)
            final, prov = d.get(campo), d["procedencia"][campo]
            if not modelo.vacio(antes) and modelo.comparable(campo, antes) == modelo.comparable(campo, final):
                continue
            if modelo.vacio(antes):
                cond, previo = modelo.expr_vacio(campo), []
            else:
                fte = modelo.fuente_de(foto, campo)
                cond = {"$and": [{"$eq": [modelo.expr_comparable(campo), _lit(modelo.comparable(campo, antes))]},
                                 {"$eq": [{"$ifNull": [f"$procedencia.{campo}.fuente", "panel"]}, _lit(fte)]}]}
                previo = [self._alterno(campo, antes, fte)]
            conds[campo] = cond
            s[campo] = {"$cond": [cond, _lit(final), f"${campo}"]}
            proc.append({"$cond": [cond, {campo: _lit(prov)}, {}]})
            otro = {"$and": [{"$not": [modelo.expr_vacio(campo)]},
                             {"$ne": [modelo.expr_comparable(campo), _lit(modelo.comparable(campo, final))]}]}
            alt.append({"$cond": [cond, _lit(previo), {"$cond": [otro, [_lit(self._alterno(campo, final, prov["fuente"]))],
                                                                   []]}]})
        edad = [conds[k] for k in ("edad", "fecha_nacimiento") if k in conds]
        if edad:
            una = {"$or": edad}
            for k in ("nac_aprox", "nac_exacta", "nac_base"):
                s[k] = {"$cond": [una, _lit(d.get(k)), f"${k}"]}
            if "edad" in conds:
                s["edad_ref"] = {"$cond": [conds["edad"], _lit(d.get("edad_ref")), "$edad_ref"]}
        filtro = {"_id": i, **bd.ACTIVA}
        if c["cedula"]:
            libre = modelo.expr_vacio("cedula")
            s["cedula"] = {"$cond": [libre, _lit(c["cedula"]), "$cedula"]}
            s["cedula_origen"] = {"$cond": [libre, _lit(c["cedula_origen"]), "$cedula_origen"]}
            proc.append({"$cond": [libre, {"cedula": _lit(d["procedencia"]["cedula"])}, {}]})
            filtro["cedula"] = {"$in": [None, c["cedula"]]}
        if proc:
            s["procedencia"] = {"$mergeObjects": [{"$ifNull": ["$procedencia", {}]}, *proc]}
        for k, v in c["simples"].items():
            s[k] = {"$cond": [modelo.expr_vacio(k), _lit(v), f"${k}"]}
        for k in self.LISTAS:
            if c[k]:
                s[k] = modelo._expr_union(f"${k}", _lit(c[k]))
        if c["tramites"]:
            s["tramites"] = {"$concatArrays": [{"$ifNull": ["$tramites", []]}, _lit(c["tramites"])]}
        if c["origen"]:
            claves = [{"f": f, "c": k} for f, k in c["origen"]]
            s["origen"] = {"$concatArrays": [
                {"$filter": {"input": {"$ifNull": ["$origen", []]}, "as": "o",
                             "cond": {"$not": [{"$in": [{"f": "$$o.fuente", "c": "$$o.clave"}, _lit(claves)]}]}}},
                _lit(list(c["origen"].values()))]}
        if c["contacto"]:
            s["ultimo_contacto"] = {"$max": ["$ultimo_contacto", _lit(c["contacto"])]}
        etapas: list = []
        if c["telefonos"]:
            etapas.append(modelo.ETAPA_RECONCILIAR_TELEFONOS)
        if alt:
            s["__alt"] = {"$concatArrays": alt}
        etapas.append({"$set": s})
        if alt:
            pares = {"$map": {"input": {"$ifNull": ["$alternos", []]}, "as": "x", "in": {"c": "$$x.campo", "v": "$$x.valor"}}}
            etapas += [{"$set": {"alternos": {"$slice": [{"$concatArrays": [{"$ifNull": ["$alternos", []]}, {"$filter": {
                "input": "$__alt", "as": "y", "cond": {"$not": [{"$in": [{"c": "$$y.campo", "v": "$$y.valor"}, pares]}]}}}]},
                -100]}}}, {"$unset": "__alt"}]
        if c["telefonos"]:
            etapas += modelo.expr_unir_telefonos(c["telefonos"])
        if "votacion" in conds:
            etapas.append(modelo.ETAPA_DERIVAR_VOTACION)
        if c["datos"]:  # a quien dijo que no autoriza (aun mientras corría la importación) no se le agregan datos
            filtro["consentimiento"] = {"$ne": "no"}
        return etapas, filtro

    def guardar(self) -> int:
        """Escribe todo y devuelve cuántas fichas no se pudieron guardar (p. ej. porque en el panel se asignó la misma
        cédula a otra persona mientras corría la importación)."""
        ops, pids = [], []
        necesidades = None
        for i in self.nuevas:
            d = self.docs[i]
            d["completitud"] = bd.completitud(d, necesidades)
            ops.append(InsertOne(d))
            pids.append(i)
            if i in self.auditorias:
                completados = modelo.completados(None, d)
                self.auditorias[i].update(accion="crear", campos=["nombre", *completados], completados=completados)
        for i, c in self.cambios.items():
            etapas, filtro = self._escritura(i, c)
            if etapas is None:
                continue
            ops.append(UpdateOne(filtro, etapas))
            pids.append(i)
            if i in self.auditorias:
                self.auditorias[i].update(accion="editar", campos=sorted(c["campos"]),
                                          completados=modelo.completados(c["foto"], self.docs[i]))
        fallidas = 0
        for k in range(0, len(ops), 1000):
            try:
                self.db.personas.bulk_write(ops[k:k + 1000], ordered=False)
            except BulkWriteError as e:
                errores = e.details.get("writeErrors", [])
                if any(x.get("code") != 11000 for x in errores):
                    raise
                fallidas += len(errores)
                self.fallidas |= {pids[k + x["index"]] for x in errores}
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

    def despues_de_guardar(self, imp_id: int | None, usuario: str | None) -> None:
        """Lo que va después de escribir las fichas: verificación de las cédulas escritas, conflictos, autorizaciones
        de la planilla, auditoría por persona y auditoría de los cruces automáticos (sin las fichas que fallaron)."""
        db = self.db
        if self.cedulas_escritas:
            reales = {p["_id"]: p for p in db.personas.find({"_id": {"$in": list(self.cedulas_escritas)}},
                                                          {"cedula": 1, "eliminado": 1, "fusionada_en": 1})}
            for pid, (ced, r, fuente) in self.cedulas_escritas.items():
                p = reales.get(pid)
                if p and not p.get("eliminado") and p.get("fusionada_en") is None and p.get("cedula") != ced:
                    self.fallidas.add(pid)  # en el panel le pusieron otra cédula: la fila no escribió nada
                    if r is not None:
                        self.conflicto("nombre_distinto", r, pid, (fuente, imp_id))
            self.cedulas_escritas.clear()
        if self.conflictos:
            primero = bd.siguiente_id(db, "conflictos_cedula", len(self.conflictos))
            for k, c in enumerate(self.conflictos):
                r = db.conflictos_cedula.update_one({"clave": c["clave"]}, {"$setOnInsert": {"_id": primero + k, **c}},
                                                    upsert=True)
                if r.upserted_id is not None:
                    self.res.conflictos_cedula += 1
            self.conflictos.clear()
        self._guardar_eventos(usuario)
        auditoria = []
        for pid, a in self.auditorias.items():
            if pid in self.fallidas or not a.get("campos"):
                continue
            auditoria.append({"ts": bd.ahora(), "usuario": usuario, "accion": a["accion"], "entidad": "persona",
                              "entidad_id": pid, "detalle": json.dumps({"via": "planilla", "importacion_id": imp_id}),
                              "ip": None, "uid": self.actor["uid"], "rol": self.actor["rol"],
                              "capturado_por": a.get("capturado_por"), "campos": a["campos"],
                              "completados": a.get("completados") or []})
        if auditoria:
            db.auditoria.insert_many(auditoria)
        self.auditorias.clear()
        for pid, detalle in self.cruces:
            if pid not in self.fallidas:
                bd.auditar(db, "sistema", "cruce_automatico", "persona", pid, detalle)
        self.cruces.clear()

    def _guardar_eventos(self, usuario: str | None) -> None:
        """Autorizaciones de la planilla (1.6): «si» con el medio de la columna si es de los del planillero (si no,
        «declarado en planilla», que no habilita la cola hasta que el administrador lo confirme) y «no»; siempre con la
        evidencia del archivo y la fila."""
        eventos = [e for e in self.eventos if e[0] not in self.fallidas]
        self.eventos.clear()
        if not eventos:
            return
        pids = list(dict.fromkeys(e[0] for e in eventos))
        bd.reconciliar_consentimiento(self.db, pids)  # lo que escribió el código viejo queda antes
        for pid, r, cap, archivo, sha, imp_id in eventos:
            estado = r.autorizacion
            if estado == "si":
                medio = r.autorizacion_medio if r.autorizacion_medio in modelo.MEDIOS_POR_ROL["planillero"] \
                    else "declarado_planilla"
                canales = list(r.canales)
            else:
                medio, canales = r.autorizacion_medio or "declarado_planilla", []
            clave = f"planilla:{pid}:{estado}:{medio}:{','.join(canales)}:{r.fecha or ''}"
            ev = bd.autorizacion_doc(
                self.db, pid, estado, medio, canales=canales, mayor_declarado=r.datos.get("mayor_de_18") is True,
                evidencia=f"{archivo or 'planilla'}, fila {r.fila}", evidencia_sha256=sha, evidencia_fila=r.datos,
                texto_version=self.texto_version, fecha_declarada=r.fecha, uid=self.actor["uid"], usuario=usuario,
                rol=self.actor["rol"], capturado_por=cap, clave_migracion=clave, importacion_id=imp_id)
            try:
                self.db.autorizaciones.insert_one(ev)
            except DuplicateKeyError:  # la misma declaración ya estaba (reimportación)
                continue
            if estado == "si" and medio == "declarado_planilla":
                self.res.autorizaciones_por_confirmar += 1
        bd.derivar(self.db, pids, reconciliar=False)


def importar(db: Database, rutas: list[Path], usuario: str | None = "sistema", nombres: list[str] | None = None, *,
             quien=None, capturado_por: int | None = None) -> Resumen:
    """Importa los Excel de `rutas` (`nombres`: los nombres originales, para los mensajes de error).

    `quien` (un `acceso.Quien`) es quien importa (el administrador) y `capturado_por` el uid del planillero que llenó
    la planilla; la columna «Planillero (usuario)» de cada fila manda sobre él si es un planillero activo. Una sola
    importación a la vez: con otra en curso, `ImportacionEnCurso` (409 `importando`)."""
    if quien is not None:
        usuario = quien.usuario
    actor = {"uid": quien.uid if quien is not None else 0, "usuario": usuario,
             "rol": quien.rol if quien is not None else "admin"}
    dueño = uuid.uuid4().hex
    if not bd.tomar_turno(db, "importando", dueño, TURNO_MIN):
        raise ImportacionEnCurso()
    try:
        return _importar(db, rutas, usuario, nombres, actor, capturado_por, dueño)
    finally:
        bd.soltar_turno(db, "importando", dueño)


def _importar(db: Database, rutas: list[Path], usuario: str | None, nombres: list[str] | None, actor: dict,
              capturado_por: int | None, dueño: str) -> Resumen:
    res = Resumen()
    tramites: list[lectores.FilaTramite] = []
    registros: dict[str, list] = {"cedulas": [], "planilla": []}
    huellas: dict[str, str] = {}
    for i, ruta in enumerate(rutas):
        nombre = (nombres or [])[i] if nombres and i < len(nombres) else Path(ruta).name
        try:  # en el servidor los archivos se llaman 0.xlsx, 1.xlsx…: el error debe decir cuál de los subidos falló
            tipo = lectores.tipo_de_archivo(ruta)
            if tipo == "tramites":
                filas = list(lectores.leer_tramites(ruta))
            elif tipo in registros:
                filas = list(lectores.leer_registros(ruta, tipo))
            else:
                raise ValueError("faltan las columnas esperadas")
        except ValueError as e:
            raise ValueError(f"{nombre}: {e}") from e
        sha = hashlib.sha256(Path(ruta).read_bytes()).hexdigest()
        huellas[nombre] = sha
        if tipo == "tramites":
            tramites.extend(filas)
        else:
            registros[tipo].append((nombre, sha, filas))
        res.archivos.append({"archivo": nombre, "tipo": tipo, "filas": len(filas)})
        res.registros_por_fuente[tipo] = res.registros_por_fuente.get(tipo, 0) + len(filas)
    bd.renovar_turno(db, "importando", dueño, TURNO_MIN)

    imp_id = bd.siguiente_id(db, "importaciones")
    alm = _Almacen(db, actor=actor)
    alm.res = res
    if tramites:
        _importar_tramites(alm, tramites, res)
    for fuente in ("cedulas", "planilla"):  # de menos a más confianza
        for archivo, sha, filas in registros[fuente]:
            _importar_registros(alm, fuente, filas, imp_id, res, capturado_por, archivo=archivo, sha=sha)
    bd.renovar_turno(db, "importando", dueño, TURNO_MIN)
    res.no_guardadas = alm.guardar()
    alm.guardar_coincidencias()
    alm.despues_de_guardar(imp_id, usuario)
    bd.renovar_turno(db, "importando", dueño, TURNO_MIN)
    bd.cerrar_coincidencias_imposibles(db)
    res.lugares_nuevos = registrar_lugares_de_datos(db)
    res.geo = georreferenciar(db)
    bd.recalcular_completitud(db)
    db.importaciones.insert_one({"_id": imp_id, "ts": bd.ahora(), "usuario": usuario, "uid": actor["uid"],
                                 "capturado_por": capturado_por,
                                 "archivo": ", ".join(a["archivo"] for a in res.archivos),
                                 "tipo": ", ".join(sorted({a["tipo"] for a in res.archivos})),
                                 "evidencia_sha256": huellas, "resumen": res.dict()})
    bd.auditar(db, SimpleNamespace(**actor, ip=None), "importar", "importacion", imp_id, res.dict(),
               capturado_por=capturado_por)
    return res


def _importar_tramites(alm: _Almacen, filas, res: Resumen) -> None:
    alm.res = res
    grupos = cruce.agrupar_tramites(filas)
    pids: dict[str, int] = {}
    ids_de = {g.clave: [f.id_externo for f in g.filas if f.id_externo] for g in grupos}
    contenido_de = {g.clave: {id(f): clave_contenido(f.ficha, f.fecha, f.tramite, tx.nombre_norm(f.nombre))
                              for f in g.filas if not f.id_externo} for g in grupos}
    # Homónimos (el mismo nombre en varias fichas de la base o en varias partes de este archivo): cada parte va a la
    # ficha que ya tiene sus trámites, su ficha o su teléfono, no a la de la clave sin «#ficha». Un archivo con solo
    # uno de los dos, o en el que el otro tiene el trámite más antiguo, no los mezcla
    partes = Counter(_base(g.clave) for g in grupos)
    evidencia: dict[str, int] = {}
    for g in grupos:
        base = _base(g.clave)
        if partes[base] > 1 or len(alm.por_base.get(base, ())) > 1:
            pid = alm.por_evidencia(base, g, ids_de[g.clave], contenido_de[g.clave].values())
            if pid is not None:
                evidencia[g.clave] = pid
    tomadas = defaultdict(set)  # ficha que ya le corresponde a otra parte de este archivo
    for c, pid in evidencia.items():
        tomadas[_base(c)].add(pid)
    for g in grupos:
        ids = ids_de[g.clave]
        nombres = {g.clave, *(tx.nombre_norm(n) for n in g.nombres)}
        contenido = contenido_de[g.clave]
        # Una persona suprimida se reconoce por sus trámites o por ficha/teléfono + nombre, nunca por el nombre solo
        identidad = [*(("tramite", i) for i in ids), *(("contenido", k) for k in contenido.values()),
                     *bd.pares_identidad(nombres, (f.ficha for f in g.filas), g.telefonos)]
        if any(alm.suprimida(t, v) for t, v in identidad):
            alm.bloquear(identidad)  # sus trámites y datos nuevos quedan bloqueados también
            res.suprimidas_omitidas += len(g.filas)
            continue
        u = g.ultima
        base = _base(g.clave)
        clave = g.clave
        pid = evidencia.get(g.clave)
        if pid is None:
            pid = alm.por_clave.get(g.clave)
            if pid is not None and pid in tomadas[base]:
                # La ficha de esta clave es la de otra parte del archivo: esta es otra persona con el mismo nombre
                pid = None
                clave = f"{base}#{min(g.fichas)}" if g.fichas else g.clave
        if pid is None:  # ¿alguno de sus trámites ya está en la base (p. ej. tras una fusión)?
            pid = next((alm.por_tramite[i] for i in ids if i in alm.por_tramite), None)
        if pid is None:
            pid = next((alm.por_contenido[k] for k in contenido.values() if k in alm.por_contenido), None)
        if pid is None and clave in alm.por_clave:  # la clave ya es de otra ficha (no se puede repetir)
            pid = alm.por_clave[clave]
        if pid is None:
            d = alm.nueva({"nombre": g.nombre, "clave_tramites": clave, "creado_por": alm.creador()}, "tramites")
            res.personas_nuevas += 1
        else:
            d = alm.docs[pid]
            if alm.es_no(d):  # no autorizó: no se le agrega nada
                res.omitidas_sin_autorizacion += len(g.filas)
                pids[g.clave] = pid
                continue
            res.personas_actualizadas += 1
            # Otra escritura del nombre (de una ficha unida): se recuerda. No el «#ficha» que tocó a un homónimo ya
            # conocido solo por el orden de las fechas de este archivo: a ese se lo encuentra por sus datos
            if clave not in alm.por_clave and not ("#" in clave and pid in alm.por_base.get(base, ())):
                alm.agregar(d, "claves_tramites", clave)
                alm.por_clave[clave] = pid
                alm.por_base[base].add(pid)
        # Todos los números del grupo, del más frecuente al menos frecuente, con la primera y la última vez
        fechas: dict[str, list[str]] = defaultdict(list)
        for f in g.filas:
            for t in f.telefonos:
                if f.fecha:
                    fechas[t].append(f.fecha)
        alm.telefonos(d, [modelo.telefono_nuevo(t, "tramites", primera_vez=min(fechas[t], default=None),
                                                ultima_vez=max(fechas[t], default=None))
                          for t, _ in g.telefonos.most_common()])
        alm.aplicar(d, "correo", g.correos.most_common(1)[0][0] if g.correos else None, "tramites")
        direccion = u.direccion or next((f.direccion for f in sorted(g.filas, key=lambda f: f.fecha or "", reverse=True)
                                         if f.direccion), None)
        alm.aplicar(d, "direccion", direccion, "tramites")
        alm.simple(d, "ficha", u.ficha or None)
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
    # Mismo nombre con fichas y teléfonos distintos quedó como dos personas, y un nombre de pila casi igual con la
    # misma ficha y el mismo teléfono («ROSALBA»/«OSALBA», ¿errata o hermanos?) también: que el administrador lo confirme
    grupo_de = {g.clave: g for g in grupos}
    for g in grupos:
        a, b = pids.get(g.clave), pids.get(g.separado_de) if g.separado_de else None
        if a and b and a != b:
            alm.proponer(a, b, 1.0, {"homonimo": True, "puntaje_nombre": 1.0, "palabras": len(g.tokens()),
                                     "telefono": False, "correo": False}, "homonimo")
        for c in g.parecidos:
            b = pids.get(c)
            if a and b and a != b:
                otro = grupo_de[c]
                parecido = round(fuzz.ratio(tx.nombre_norm(g.nombre), tx.nombre_norm(otro.nombre)) / 100, 4)
                alm.proponer(a, b, parecido, {"variante": True, "puntaje_nombre": parecido, "palabras": len(g.tokens()),
                                              "telefono": bool(set(g.telefonos) & set(otro.telefonos)),
                                              "correo": bool(set(g.correos) & set(otro.correos))}, "variante")


# ───────────────────────────── Fuentes con cédula: cascada de identidad (2.3) ─────────────────────────────

def _importar_cedulas(alm: _Almacen, filas, imp_id: int, res: Resumen) -> None:
    """Filas de la base con cédula (`lectores.FilaCedula`): se convierten en registros y siguen la cascada."""
    _importar_registros(alm, "cedulas", [lectores.a_registro(f, i) for i, f in enumerate(filas, 1)], imp_id, res)


def _importar_registros(alm: _Almacen, fuente: str, registros, imp_id: int, res: Resumen,
                        capturado_por: int | None = None, *, archivo: str | None = None, sha: str | None = None) -> None:
    """Cascada de identidad para cada registro: 0) supresión; 1) llave ya vinculada; 2) cédula exacta (con el
    nombre); 3) cédula anterior; 4) cruce en lote de todas las demás; 5) ficha nueva. Las filas repetidas (misma cédula
    o misma llave) esperan y completan la ficha que resulte."""
    alm.res = res
    pendientes, repetidas, vistas = [], [], set()
    for r in registros:
        cap = alm.capturador(r, capturado_por) if fuente == "planilla" else None
        ctx = (fuente, imp_id, cap, archivo, sha)
        identidad = bd.pares_identidad([r.nombre], [], r.telefonos)
        cedulas = [c for c in (r.cedula, r.datos.get("cedula_digitada"), r.datos.get("cedula_repetida")) if c]
        if any(alm.suprimida("cedula", c) for c in cedulas) or any(alm.suprimida(t, v) for t, v in identidad):
            alm.bloquear([*(("cedula", c) for c in cedulas), *identidad])
            res.suprimidas_omitidas += 1
            continue
        if _por_identidad(alm, r, ctx, res):
            continue
        if r.clave_fila in vistas:  # la misma cédula (o la misma llave) otra vez en esta importación
            repetidas.append((r, ctx))
            continue
        vistas.add(r.clave_fila)
        pendientes.append((r, ctx))
    if pendientes:
        _cruzar_registros(alm, pendientes, res)
    for r, ctx in repetidas:
        if not _por_identidad(alm, r, ctx, res):
            _cruzar_registros(alm, [(r, ctx)], res)
    _posible_digitacion(alm)


def _por_identidad(alm: _Almacen, r: Registro, ctx: tuple, res: Resumen) -> bool:
    """Pasos 1 a 3 de la cascada. False si la fila sigue al cruce en lote."""
    fuente = ctx[0]
    pid = alm.por_llave.get((fuente, r.clave_fila))
    if pid in alm.docs:  # 1. llave ya vinculada: se actualiza sin comparar nombres
        d = alm.docs[pid]
        if r.cedula and d.get("cedula") and d["cedula"] != r.cedula \
                and r.cedula not in (d.get("cedulas_anteriores") or []):
            alm.conflicto("cedula_anterior", r, pid, ctx)
            return True
        alm.completar_registro(d, r, ctx)
        if r.cedula:
            res.cedulas_ya_existian += 1
        return True
    if r.cedula and r.cedula in alm.por_cedula:  # 2. cédula exacta
        d = alm.docs[alm.por_cedula[r.cedula]]
        p, evidencia = alm.puntaje(r, d)
        if p >= UMBRAL_MISMA or (p >= UMBRAL_MISMA_EVIDENCIA and evidencia):
            alm.completar_registro(d, r, ctx)
            res.cedulas_ya_existian += 1
        else:  # otro nombre con esa cédula: no se mezcla nada
            alm.conflicto("nombre_distinto", r, d["_id"], ctx, puntaje=p)
        return True
    if r.cedula and r.cedula in alm.por_anterior:  # 3. cédula anterior de una ficha
        alm.conflicto("cedula_anterior", r, alm.por_anterior[r.cedula], ctx)
        return True
    return False


def _cruzar_registros(alm: _Almacen, pendientes: list[tuple], res: Resumen) -> None:
    """Paso 4: todas las filas restantes a la vez con `cruce.cruzar` (umbrales y márgenes de siempre). Una fila con
    cédula busca entre las fichas sin cédula; una sin cédula, entre todas, pero con una ficha que tiene cédula solo se
    une sola con teléfono o correo en común. Regla colectiva: si varias filas se unirían solas con la misma ficha, todas
    van a revisión."""
    def candidatas(con_cedula: bool) -> list[_Cand]:
        return [_Cand(d["_id"], d["nombre"], alm.numeros(d), {d["correo"]} if d.get("correo") else set(), d.get("cedula"))
                for d in alm.docs.values() if con_cedula or not d.get("cedula")]

    con = [(r, ctx) for r, ctx in pendientes if r.cedula]
    sin = [(r, ctx) for r, ctx in pendientes if not r.cedula]
    resultados = []
    if con:
        cands = candidatas(False)
        resultados += [(x, cands, ctx) for x, (_, ctx) in zip(cruce.cruzar(cands, [r for r, _ in con]), con)]
    if sin:
        cands = candidatas(True)
        for x, (_, ctx) in zip(cruce.cruzar(cands, [r for r, _ in sin]), sin):
            m = x.mejor
            if x.estado == "auto" and cands[m.indice].cedula and not (m.telefono or m.correo):
                x.estado = "revision"
            resultados.append((x, cands, ctx))
    por_cand: dict[int, list] = defaultdict(list)
    for x, cands, _ in resultados:
        if x.estado == "auto" and x.mejor:
            por_cand[cands[x.mejor.indice].id].append(x)
    ganadoras = {id(rs[0]) for rs in por_cand.values() if len(rs) == 1}
    tomados = {cid for cid, rs in por_cand.items() if len(rs) == 1}
    for x, cands, ctx in resultados:
        r, m = x.fila, x.mejor
        fuente, imp_id = ctx[0], ctx[1]
        if id(x) in ganadoras:
            d = alm.docs[cands[m.indice].id]
            if alm.es_no(d):
                alm.origen_minimo(d, fuente, r.clave_fila, imp_id)
                continue
            if r.cedula:
                alm.fijar_cedula(d, r.cedula, "cruce", fuente, r)
            alm.completar_registro(d, r, ctx)
            alm.cruces.append((d["_id"], {"fuente": fuente, "cedula": r.cedula, "nombre_fila": r.nombre,
                                          "puntaje": m.puntaje, "telefono": m.telefono, "correo": m.correo}))
            if r.cedula:
                res.cedulas_unidas_auto += 1
            else:
                res.registros_unidos_auto += 1
            continue
        d = alm.nueva_desde(r, ctx)
        res.personas_nuevas += 1
        # A revisión contra los candidatos que siguen libres: una ficha que ya recibió otra fila no se podría unir
        props = [c for c in x.candidatos if c.puntaje >= cruce.UMBRAL_REVISION and cands[c.indice].id not in tomados]
        if x.estado in ("auto", "revision") and props:
            if r.cedula:
                res.cedulas_en_revision += 1
            else:
                res.registros_en_revision += 1
            alm.coincidencias += [{"persona_id": d["_id"], "candidato_id": cands[c.indice].id, "puntaje": c.puntaje,
                                   "detalle": {"puntaje_nombre": c.puntaje_nombre, "palabras": c.palabras,
                                               "telefono": c.telefono, "correo": c.correo},
                                   "motivo": "cruce_cedula" if r.cedula else "nombre_telefono", "estado": "pendiente"}
                                  for c in props]
        elif r.cedula:
            res.cedulas_sin_coincidencia += 1
        if r.cedula:
            alm.digitacion.append((r, d, ctx))


def variantes_cedula(c: str) -> list[str]:
    """Cédulas a un error de digitación: un dígito cambiado o dos vecinos intercambiados."""
    out = []
    for i, ch in enumerate(c):
        out += [c[:i] + x + c[i + 1:] for x in "0123456789" if x != ch]
    out += [c[:i] + c[i + 1] + c[i] + c[i + 2:] for i in range(len(c) - 1) if c[i] != c[i + 1]]
    return out


def _posible_digitacion(alm: _Almacen) -> None:
    """Cada fila con cédula que creó ficha o fue a revisión se compara con las fichas cuya cédula difiere en un dígito
    o en una transposición: con casi el mismo nombre, un aviso para el administrador (nunca se une)."""
    for r, d, ctx in alm.digitacion:
        for v in variantes_cedula(r.cedula):
            otra = alm.por_cedula.get(v)
            if otra is None or otra == d["_id"] or otra not in alm.docs:
                continue
            p, _ = alm.puntaje(r, alm.docs[otra])
            if p >= UMBRAL_DIGITACION:
                alm.conflicto("posible_digitacion", r, d["_id"], ctx, cedula=v, puntaje=p, otra=otra)
    alm.digitacion.clear()


def aplicar_registro(db: Database, pid: int, registro: dict, quien=None) -> bool:
    """«Aplicar» un conflicto: la fila guardada se toma como de esta persona y la completa con las reglas de 1.5 (sin
    cambiar su cédula). False si la ficha ya no está activa."""
    actor = {"uid": getattr(quien, "uid", 0), "usuario": getattr(quien, "usuario", None) or (quien or "sistema"),
             "rol": getattr(quien, "rol", "admin")}
    alm = _Almacen(db, ids=[pid], actor=actor)
    d = alm.docs.get(pid)
    if d is None:
        return False
    campos = {k: v for k, v in registro.items() if k in Registro.__dataclass_fields__}
    r = Registro(**campos)
    if d.get("cedula") and r.cedula != d["cedula"]:
        r.cedula = None
    alm.completar_registro(d, r, (r.fuente, None, None, None, None))
    alm.guardar()
    alm.despues_de_guardar(None, actor["usuario"])
    bd.derivar(db, [pid])
    georreferenciar(db, [pid])
    return True


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
    """Normaliza la dirección y ubica a cada persona (también su `punto` GeoJSON). Respeta lo puesto a mano: un punto
    en el mapa no se toca, y un barrio o vereda elegido a mano se conserva (la persona sigue el punto de ese lugar, o el
    de su placa si es urbano)."""
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
            cambios["punto"] = modelo.punto(cambios["lat"], cambios["lon"])
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
