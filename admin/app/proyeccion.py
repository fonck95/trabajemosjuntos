"""Qué ve cada rol de una persona: las respuestas se arman solo con los campos permitidos, nunca copiando el documento
y quitando campos.

* `CAMPOS_FICHA[rol]` y `CAMPOS_FILA[rol]`: claves de primer nivel de la ficha y de las filas que puede recibir cada
  rol. `sensibles` y `cedula_en_traspaso` no están en ninguna lista, tampoco en la de A.
* Algunos campos llevan además un recorte por dentro, que aplica quien arma la respuesta (3.8): teléfonos solo usables
  para C, sin teléfonos para P si es menor (tampoco el número de sus acercamientos), acercamientos sin `nota` para P,
  trámites con `fecha`, `tipo` y `ficha` para P, `situacion.estado` para C, `en_curso` propio, `abordaje` con solo
  `estado` en `CAMPOS_NO_AUTORIZO`.
* Para P y C la fuente «cedulas» se muestra como «otra_base» (`neutralizar_fuente`).
* `exigir_tratable` va en toda escritura sobre una persona: a quien no autorizó, P y C no lo tratan.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable

from fastapi import HTTPException
from pymongo.database import Database

from . import acceso, modelo
from .db import ACTIVA, cerrar_coincidencias_imposibles

# ───────────────────────────── Ficha ─────────────────────────────

_IDENTIDAD_A = {"id", "nombre", "nombre_norm", "tipo_documento", "cedula", "cedula_verificada", "cedula_origen",
                "cedulas_anteriores"}
_DEMOGRAFIA = {"sexo", "edad", "edad_ref", "fecha_nacimiento", "nac_aprox", "nac_exacta", "edad_efectiva", "rango_edad",
               "menor", "estado_civil", "nivel_educativo", "situacion_laboral", "ocupacion", "personas_hogar",
               "jefe_hogar", "tenencia_vivienda", "estrato", "regimen_salud"}
_UBICACION = {"correo", "direccion", "direccion_norm", "lugar_id", "lugar_nombre", "lugar_tipo", "lugar_texto", "zona",
              "lat", "lon", "geo_precision", "geo_manual", "geo_fuente", "precision_m", "ficha"}
_VOTACION = {"votacion", "puesto_votacion", "mesa"}
_AUTORIZACION = {"consentimiento", "consentimiento_fecha", "consentimiento_medio", "consentimiento_canales",
                 "contacto_habilitado", "mayor_declarado"}
_SEGUIMIENTO = {"requiere_actualizacion", "situacion", "no_disponible", "faltan", "editables", "avisos"}

CAMPOS_FICHA: dict[str, frozenset[str]] = {
    "admin": frozenset(
        _IDENTIDAD_A | _DEMOGRAFIA | _UBICACION | _VOTACION | _AUTORIZACION | _SEGUIMIENTO
        | {"sensibles_registrados", "sensibles_autorizados", "telefonos", "telefono", "telefono2", "autorizacion",
           "autorizacion_ultima", "reclamo_en_tramite", "abordaje", "abordaje_seq", "acercamientos", "ultimo_contacto",
           "en_curso", "notas", "listas", "lider", "etiquetas", "extra", "observaciones", "origen", "procedencia",
           "tramites", "alternos", "avance", "historial", "coincidencias", "reuniones", "reunion_origen", "fuentes",
           "completitud", "clave_tramites", "claves_tramites", "creado_por", "actualizado_por", "creado_en",
           "actualizado_en", "fusionada_en", "eliminado", "punto", "nombre_fon"}),
    "planillero": frozenset(
        {"id", "nombre", "tipo_documento", "cedula", "cedula_verificada", "cedula_origen"} | _DEMOGRAFIA | _UBICACION
        | _VOTACION | _AUTORIZACION | _SEGUIMIENTO
        | {"sensibles_registrados", "telefonos", "telefono", "telefono2", "abordaje", "acercamientos", "ultimo_contacto",
           "notas", "etiquetas", "extra", "observaciones", "tramites", "alternos", "reuniones", "completitud"}),
    "consultor": frozenset(
        {"id", "nombre", "cedula_ult3", "rango_edad", "sexo", "telefonos", "lugar_nombre", "zona", "puesto_nombre",
         "consentimiento", "consentimiento_canales", "contacto_habilitado", "abordaje", "acercamientos",
         "requiere_actualizacion", "situacion", "faltan", "en_curso", "editables", "avisos"}),
}
# El coordinador maneja los datos como A (adenda 1)
CAMPOS_FICHA["coordinador"] = CAMPOS_FICHA["admin"]

# ───────────────────────────── Filas ─────────────────────────────

CAMPOS_FILA: dict[str, frozenset[str]] = {
    # Las de hoy (app/api/personas.py:53-58) más las nuevas de 8.1
    "admin": frozenset({
        "id", "nombre", "cedula", "telefono", "lugar", "lugar_tipo", "zona", "precision", "completitud", "fuentes",
        "reuniones", "lider", "consentimiento", "ultimo_contacto", "tiene_cedula", "telefonos_n", "sexo", "rango_edad",
        "menor", "puesto", "mesa", "votacion_estado", "abordaje", "faltan", "requiere_actualizacion", "situacion"}),
    "planillero": frozenset({
        "id", "nombre", "tiene_cedula", "cedula_ult3", "telefono_mascara", "telefonos_n", "lugar", "zona", "rango_edad",
        "sexo", "puesto", "mesa", "votacion_estado", "abordaje", "consentimiento", "faltan", "requiere_actualizacion",
        "menor", "situacion", "completitud"}),
    # La búsqueda del consultor
    "consultor": frozenset({"id", "nombre", "lugar", "abordaje_estado", "contactable"}),
}
CAMPOS_FILA["coordinador"] = CAMPOS_FILA["admin"]
# Fila de la cola del consultor (4.5)
CAMPOS_COLA = frozenset({"id", "nombre", "lugar", "zona", "rango_edad", "telefono_indice", "telefono", "whatsapp",
                         "canales_permitidos", "consentimiento", "abordaje"})
# Persona que no autorizó, para P y C, en filas y ficha (`abordaje` lleva solo su `estado`)
CAMPOS_NO_AUTORIZO = frozenset({"id", "nombre", "cedula_ult3", "lugar", "consentimiento", "abordaje"})
# Nadie los recibe
NUNCA = frozenset({"sensibles", "cedula_en_traspaso"})


def neutralizar_fuente(fuente: Any) -> Any:
    """Para P y C: «cedulas» se muestra como «otra_base» (en `telefonos[].fuentes`, `alternos[].fuente`,
    `votacion.fuente` y `cedula_origen`). Acepta un texto o una lista; una lista no repite valores."""
    if isinstance(fuente, (list, tuple)):
        return list(dict.fromkeys(neutralizar_fuente(f) for f in fuente))
    return "otra_base" if fuente == "cedulas" else fuente


# Lo único que P y C pueden hacer con quien no autorizó: registrar su «sí» (con evidencia, 1.6) y una solicitud
ACCIONES_SIN_AUTORIZACION = frozenset({"autorizacion", "solicitud"})
NO_AUTORIZO = {"mensaje": "Esta persona no autorizó el tratamiento de sus datos", "codigo": "no_contactable",
               "motivo": "no_autorizo"}


def exigir_tratable(p: dict, quien: Any, accion: str) -> None:
    """409 `{codigo: "no_contactable", motivo: "no_autorizo"}` si P o C intentan `accion` sobre una persona con
    `consentimiento == "no"` (PATCH, teléfonos, notas, ubicación, asistencia, acercamientos, duplicado, situación,
    no-disponible…). Solo se permiten `autorizacion` y `solicitud`. A y K pueden todo. Sin `quien` se trata como P y
    C."""
    if administra(quien):
        return
    if (p or {}).get("consentimiento") == "no" and accion not in ACCIONES_SIN_AUTORIZACION:
        raise HTTPException(409, dict(NO_AUTORIZO))




# ───────────────────────────── Quién y contexto ─────────────────────────────

def administra(quien: Any) -> bool:
    """¿Maneja los datos sin recorte (A o K)? Sin `quien`, no (falla cerrada)."""
    if quien is None:
        return False
    v = getattr(quien, "administra", None)
    return bool(v) if v is not None else bool(getattr(quien, "es_admin", False))


def rol_de(quien: Any) -> str:
    """Clave de `CAMPOS_FICHA` y `CAMPOS_FILA` para `quien`. Un rol desconocido recibe lo del consultor."""
    if administra(quien):
        return "coordinador" if getattr(quien, "rol", None) == "coordinador" else "admin"
    rol = getattr(quien, "rol", None)
    return rol if rol in ("planillero", "consultor") else "consultor"


# Etiquetas que la migración marca como sensibles (1.3). Mientras una no tenga la marca `sensible`, el nombre basta
NOMBRES_SENSIBLES = frozenset({"Discapacidad", "Víctima del conflicto", "JAC", "Líder comunitario"})


def etiqueta_sensible(e: dict) -> bool:
    if "sensible" in e and e["sensible"] is not None:
        return bool(e["sensible"])
    return e.get("nombre") in NOMBRES_SENSIBLES


def etiquetas_sensibles(db: Database) -> set[int]:
    return {e["_id"] for e in db.etiquetas.find({}, {"nombre": 1, "sensible": 1}) if etiqueta_sensible(e)}


def campos_sensibles(db: Database) -> set[str]:
    return {c["clave"] for c in db.campos.find({"sensible": True}, {"clave": 1})}


@dataclass
class Contexto:
    """Lo que las filas y las fichas necesitan de la base, leído una vez por respuesta."""
    hoy: date
    ajustes: dict
    lugares: dict = field(default_factory=dict)
    puestos: dict = field(default_factory=dict)
    etiquetas: dict = field(default_factory=dict)
    sensibles_et: set = field(default_factory=set)
    sensibles_campos: set = field(default_factory=set)

    @property
    def eleccion(self) -> str | None:
        return self.ajustes.get("eleccion_vigente")

    @property
    def dias_dato(self) -> int:
        return int(self.ajustes.get("dias_reintento_dato") or modelo.AJUSTES_POR_DEFECTO["dias_reintento_dato"])

    def lugar(self, lid: Any) -> dict:
        return self.lugares.get(lid) or {}


def contexto(db: Database) -> Contexto:
    ets = {e["_id"]: e for e in db.etiquetas.find({}, {"nombre": 1, "grupo": 1, "orden": 1, "sensible": 1})}
    return Contexto(
        hoy=modelo.hoy_local(), ajustes=modelo.leer_ajustes(db),
        lugares={l["_id"]: l for l in db.lugares.find({}, {"nombre": 1, "tipo": 1, "zona": 1})},
        puestos={x["_id"]: x for x in db.puestos.find({}, {"codigo": 1, "nombre": 1, "mesas": 1})},
        etiquetas=ets, sensibles_et={i for i, e in ets.items() if etiqueta_sensible(e)},
        sensibles_campos=campos_sensibles(db))


# ───────────────────────────── Contactable (4.2, 4.5) ─────────────────────────────

CANALES_TELEFONO = ("llamada", "whatsapp", "sms")


def motivo_no_contactable(p: dict, ajustes: dict, hoy: date | None = None, canal: str | None = None) -> str | None:
    """Gemelo en Python de las condiciones de la persona en `BASE_COLA` (sin el teléfono, el alcance ni `en_curso`):
    None si el consultor puede contactarla (por `canal`, si se da), o el motivo del 409 `no_contactable`."""
    hoy = hoy or modelo.hoy_local()
    ab = p.get("abordaje") if isinstance(p.get("abordaje"), dict) else {}
    if p.get("consentimiento") == "no" or ab.get("estado") == "no_contactar":
        return "no_autorizo"
    if (p.get("situacion") or {}).get("estado") in ("fallecida", "no_reside"):
        return "situacion"
    if modelo.es_menor(p, hoy):
        return "menor"
    if not modelo.es_adulto_conocido(p, hoy):
        return "edad_desconocida"
    if p.get("reclamo_en_tramite") is True:
        return "reclamo"
    if p.get("consentimiento") == "si":
        if p.get("contacto_habilitado") is not True:
            return "no_habilitado"
        canales = list(p.get("consentimiento_canales") or [])
        if canal is not None and canal not in canales:
            return "canal"
        if canal is None and not set(canales) & set(CANALES_TELEFONO):
            return "canal"
        return None
    # Pendiente: solo con la política encendida y nunca a quien solo viene de la base de trámites
    if not ajustes.get("contactar_pendientes"):
        return "pendiente"
    if not [f for f in p.get("fuentes") or [] if f != "tramites"]:
        return "pendiente"
    if canal is not None and canal not in CANALES_TELEFONO:
        return "canal"
    return None


def canales_permitidos(p: dict, ajustes: dict) -> list[str]:
    """Canales de teléfono con que el consultor puede contactarla (los autorizados, o los tres para pedir la
    autorización a un pendiente con la política encendida)."""
    if p.get("consentimiento") == "si":
        return [c for c in CANALES_TELEFONO if c in (p.get("consentimiento_canales") or [])]
    return list(CANALES_TELEFONO) if motivo_no_contactable(p, ajustes) is None else []


# ───────────────────────────── Filas ─────────────────────────────

def _abordaje(p: dict) -> dict | None:
    return p.get("abordaje") if isinstance(p.get("abordaje"), dict) else None


def puesto_codigo(p: dict, ctx: Contexto) -> str | None:
    v = p.get("votacion") if isinstance(p.get("votacion"), dict) else None
    if v is None:
        return None
    if v.get("puesto_id") is not None:
        return (ctx.puestos.get(v["puesto_id"]) or {}).get("codigo") or str(v["puesto_id"])
    if v.get("donde") in ("otro_municipio", "no_inscrito"):
        return v["donde"]
    return None


def fila_completa(p: dict, ctx: Contexto) -> dict:
    """Todos los valores que una fila puede llevar, calculados de la ficha. Nunca se envía tal cual: `filas_para`
    toma de aquí solo los campos del rol."""
    lg = ctx.lugar(p.get("lugar_id"))
    us = modelo.usables(modelo.telefonos_de(p))
    v = p.get("votacion") if isinstance(p.get("votacion"), dict) else None
    ab = _abordaje(p)
    return {
        "id": p["_id"], "nombre": p.get("nombre"), "cedula": p.get("cedula"),
        "cedula_ult3": acceso.enmascarar_cedula(p.get("cedula")), "tiene_cedula": bool(p.get("cedula")),
        "telefono": p.get("telefono"), "telefono_mascara": acceso.enmascarar_telefono(us[0]["numero"]) if us else None,
        "telefonos_n": len(us), "lugar": lg.get("nombre") or p.get("lugar_texto"), "lugar_tipo": lg.get("tipo"),
        "zona": p.get("zona"), "precision": p.get("geo_precision"), "completitud": p.get("completitud", 0),
        "fuentes": list(p.get("fuentes") or []), "reuniones": len(p.get("asistencias") or []),
        "lider": bool(p.get("lider")), "consentimiento": p.get("consentimiento"),
        "ultimo_contacto": p.get("ultimo_contacto"), "sexo": p.get("sexo"),
        "rango_edad": modelo.rango_edad(modelo.edad_efectiva(p, ctx.hoy)), "menor": modelo.es_menor(p, ctx.hoy),
        "puesto": puesto_codigo(p, ctx) if v else p.get("puesto_votacion"),
        "mesa": (v or {}).get("mesa") if v else p.get("mesa"),
        "votacion_estado": modelo.estado_votacion_efectivo(v, ctx.eleccion), "abordaje": ab,
        "abordaje_estado": (ab or {}).get("estado") or "sin_abordar",
        "faltan": modelo.faltan(p, ctx.hoy, ctx.dias_dato), "requiere_actualizacion": p.get("requiere_actualizacion"),
        "situacion": p.get("situacion"),
        "contactable": motivo_no_contactable(p, ctx.ajustes, ctx.hoy) is None,
    }


# Lo que una fila de Habitantes, la búsqueda y las parecidas necesitan de cada ficha
CAMPOS_PARA_FILA = {k: 1 for k in (
    "nombre", "nombre_norm", "cedula", "telefono", "telefono2", "telefonos", "lugar_id", "lugar_texto", "zona",
    "geo_precision", "completitud", "fuentes", "asistencias.reunion_id", "lider", "consentimiento", "ultimo_contacto",
    "sexo", "edad", "edad_ref", "fecha_nacimiento", "nac_aprox", "tipo_documento", "creado_en", "votacion",
    "puesto_votacion", "mesa", "abordaje", "requiere_actualizacion", "situacion", "no_disponible", "lat", "lon", "punto",
    "direccion", "mayor_declarado", "contacto_habilitado", "consentimiento_canales", "reclamo_en_tramite")}


def _no_autorizo(d: dict) -> dict:
    ab = d.get("abordaje") if isinstance(d.get("abordaje"), dict) else {}
    return {"id": d.get("id"), "nombre": d.get("nombre"), "cedula_ult3": d.get("cedula_ult3"), "lugar": d.get("lugar"),
            "consentimiento": d.get("consentimiento"), "abordaje": {"estado": ab.get("estado") or "no_contactar"}}


def filas_para(quien: Any, docs: Iterable[dict]) -> list[dict]:
    """Las filas de `docs` (hechas con `fila_completa`) con los campos de `CAMPOS_FILA[rol]`; para P y C, la de quien
    no autorizó con `CAMPOS_NO_AUTORIZO`. Para P, sin los teléfonos de un menor y con `abordaje` resumido."""
    rol, adm = rol_de(quien), administra(quien)
    permitidos = CAMPOS_FILA[rol]
    out = []
    for d in docs:
        if not adm and d.get("consentimiento") == "no":
            out.append(_no_autorizo(d))
            continue
        f = {k: d.get(k) for k in permitidos}
        if rol == "planillero":
            ab = d.get("abordaje") if isinstance(d.get("abordaje"), dict) else {}
            f["abordaje"] = {"estado": ab.get("estado") or "sin_abordar", "n": ab.get("n") or 0,
                             "ultimo_fecha": ab.get("ultimo_fecha")}
            if d.get("menor"):
                f["telefono_mascara"], f["telefonos_n"] = None, 0
        out.append(f)
    return out


def fila_cola(p: dict, ctx: Contexto) -> dict:
    """Fila de la cola del consultor (4.5): el número es el primero usable por un canal permitido. En «Hoy» puede
    salir alguien que ya no se contacta: de quien no autorizó o de un menor no va ningún número, y de quien no
    autorizó, solo lo de su fila mínima."""
    no_autorizo = p.get("consentimiento") == "no"
    us = [] if (no_autorizo or modelo.es_menor(p, ctx.hoy)) else modelo.usables(modelo.telefonos_de(p))
    lg = ctx.lugar(p.get("lugar_id"))
    ab = _abordaje(p) or {}
    if no_autorizo:
        d = {"id": p["_id"], "nombre": p.get("nombre"), "lugar": lg.get("nombre") or p.get("lugar_texto"), "zona": None,
             "rango_edad": None, "telefono_indice": None, "telefono": None, "whatsapp": None, "canales_permitidos": [],
             "consentimiento": "no", "abordaje": {"estado": ab.get("estado") or "no_contactar", "n": None,
                                                  "ultimo_fecha": None, "ultimo_resultado": None}}
        return {k: d[k] for k in CAMPOS_COLA}
    t = us[0] if us else {}
    d = {"id": p["_id"], "nombre": p.get("nombre"), "lugar": lg.get("nombre") or p.get("lugar_texto"),
         "zona": p.get("zona"), "rango_edad": modelo.rango_edad(modelo.edad_efectiva(p, ctx.hoy)),
         "telefono_indice": 0 if us else None, "telefono": t.get("numero"), "whatsapp": t.get("whatsapp"),
         "canales_permitidos": canales_permitidos(p, ctx.ajustes), "consentimiento": p.get("consentimiento"),
         "abordaje": {"estado": ab.get("estado") or "sin_abordar", "n": ab.get("n") or 0,
                      "ultimo_fecha": ab.get("ultimo_fecha"), "ultimo_resultado": ab.get("ultimo_resultado")}}
    return {k: d[k] for k in CAMPOS_COLA}


# ───────────────────────────── Ficha ─────────────────────────────

CAMPOS_VOTACION = ("puesto_id", "puesto_nombre", "puesto_texto", "mesa", "mesa_texto", "donde", "municipio", "eleccion",
                   "estado", "fuente", "registrado_por", "registrado_en")
CAMPOS_AUTORIZACION = ("estado", "medio", "canales", "canales_implicitos", "sensibles", "mayor_declarado", "evidencia",
                       "fecha_declarada", "nota", "reunion_id", "acercamiento_id", "uid", "usuario", "rol",
                       "capturado_por", "confirmada_por", "ts")
CAMPOS_ACERCAMIENTO = ("ts", "fecha", "uid", "usuario", "rol", "canal", "telefono", "resultado", "efectivo", "nota",
                       "proximo", "proximo_franja", "confirma_numero", "reunion_id", "auto", "fuera_de_horario",
                       "anulado", "anulado_por", "anulado_en", "motivo_anulacion", "alcance")
# Campos que cada rol escribe con PATCH (3.8). C no usa PATCH: sus «editables» son los datos que puede dictar (4.2)
EDITABLES_P = ("nombre", "cedula", "tipo_documento", "cedula_verificada", "sexo", "edad", "fecha_nacimiento",
               "estado_civil", "nivel_educativo", "situacion_laboral", "ocupacion", "personas_hogar", "jefe_hogar",
               "tenencia_vivienda", "estrato", "regimen_salud", "correo", "direccion", "lugar_id", "telefono",
               "telefono2", "puesto_id", "puesto_texto", "mesa", "donde", "municipio", "votacion_verificada",
               "consentimiento", "etiquetas", "extra", "sensibles", "observaciones")
EDITABLES_A = EDITABLES_P + ("lider", "consentimiento_fecha", "puesto_votacion", "motivo_cambio_cedula")


def editables(p: dict, quien: Any) -> list[str]:
    if administra(quien):
        return list(EDITABLES_A)
    if rol_de(quien) == "planillero":
        fuera = {"cedula", "tipo_documento"} if p.get("cedula") else set()
        return [k for k in EDITABLES_P if k not in fuera]
    faltan = modelo.faltan(p)
    return [k for k, f in (("cedula", "cedula"), ("puesto_id", "puesto"), ("mesa", "mesa")) if f in faltan]


def avisos(p: dict, hoy: date | None = None, adm: bool = False) -> list[str]:
    """Avisos de coherencia que no bloquean el guardado (1.3, 2.4)."""
    hoy = hoy or modelo.hoy_local()
    out = []
    nac = modelo.fecha_valida(p.get("fecha_nacimiento"))
    edad_decl = p.get("edad") if isinstance(p.get("edad"), int) and not isinstance(p.get("edad"), bool) else None
    if nac is not None and edad_decl is not None:
        por_fecha = modelo.edad_efectiva({"fecha_nacimiento": p["fecha_nacimiento"]}, hoy)
        por_edad = modelo.edad_efectiva({"edad": edad_decl, "edad_ref": p.get("edad_ref"),
                                         "creado_en": p.get("creado_en")}, hoy)
        if por_fecha is not None and por_edad is not None and abs(por_fecha - por_edad) > 1:
            out.append("La edad declarada no coincide con la fecha de nacimiento")
    edad = modelo.edad_efectiva(p, hoy)
    if p.get("tipo_documento") == "TI" and edad is not None and edad >= 18:
        out.append("Tiene tarjeta de identidad y 18 años o más: revise el tipo de documento")
    if p.get("tipo_documento") == "CC" and edad is not None and edad < 18:
        out.append("Tiene cédula de ciudadanía y menos de 18 años: revise la edad o el documento")
    ced = str(p.get("cedula") or "")
    if ced and p.get("tipo_documento") in (None, "CC") and ced.isdigit() and not 6 <= len(ced) <= 10:
        out.append("Una cédula de ciudadanía suele tener entre 6 y 10 dígitos: revísela")
    if adm and modelo.es_menor(p, hoy):
        out.append("Menor de edad: sus datos tienen protección reforzada")
    return out


def _telefonos(p: dict, rol: str, adm: bool, menor: bool) -> list[dict]:
    tels = modelo.telefonos_de(p)
    out, i = [], 0
    for t in tels:
        usable = modelo.es_usable(t)
        indice = i if usable else None
        i += usable
        if rol == "consultor" and not adm:
            if usable:
                out.append({"numero": t.get("numero"), "tipo": t.get("tipo") or modelo.tipo_telefono(t.get("numero")),
                            "whatsapp": t.get("whatsapp"), "estado": t.get("estado") or "sin_verificar",
                            "indice": indice})
            continue
        x = {k: t.get(k) for k in modelo.CAMPOS_TELEFONO}
        x["tipo"] = x["tipo"] or modelo.tipo_telefono(x["numero"])
        x["estado"] = x["estado"] or "sin_verificar"
        x["fuentes"] = list(x["fuentes"] or [])
        x["indice"] = indice
        if not adm:
            x["fuentes"] = neutralizar_fuente(x["fuentes"])
        out.append(x)
    if rol == "planillero" and not adm and menor:
        return []
    return out


def _votacion(p: dict, ctx: Contexto, adm: bool) -> dict | None:
    v = p.get("votacion") if isinstance(p.get("votacion"), dict) else None
    if v is None:
        return None
    d = {k: v.get(k) for k in CAMPOS_VOTACION}
    d["estado_efectivo"] = modelo.estado_votacion_efectivo(v, ctx.eleccion)
    if d.get("puesto_id") is not None:
        d["puesto_codigo"] = (ctx.puestos.get(d["puesto_id"]) or {}).get("codigo")
    if not adm:
        d["fuente"] = neutralizar_fuente(d["fuente"])
    return d


def acercamiento_para(a: dict, rol: str, adm: bool, menor: bool) -> dict:
    """Un acercamiento con los campos de `CAMPOS_ACERCAMIENTO` y los recortes del rol: P, sin `nota` y, si la persona
    es menor, sin el número (P no ve sus teléfonos, tampoco por aquí); C, con el número enmascarado y ninguno de un
    menor."""
    d = {"id": a["_id"], **{k: a.get(k) for k in CAMPOS_ACERCAMIENTO}}
    d["datos_dictados"] = list(a.get("datos_dictados") or [])
    if not adm and rol == "planillero":
        d.pop("nota")
        if menor:
            d["telefono"] = None
    if not adm and rol == "consultor":
        d["telefono"] = None if menor else acceso.enmascarar_telefono(d["telefono"])
    return d


def _acercamientos(db: Database, pid: int, rol: str, adm: bool, menor: bool) -> list[dict]:
    return [acercamiento_para(a, rol, adm, menor) for a in db.acercamientos.find(
        {"persona_id": pid, "suprimido": {"$ne": True}}).sort([("ts", -1), ("_id", -1)]).limit(50)]


def _reuniones(db: Database, p: dict, adm: bool) -> tuple[list, dict]:
    rids = {a["reunion_id"] for a in p.get("asistencias") or []} | \
           {n.get("reunion_id") for n in p.get("notas") or [] if n.get("reunion_id")}
    reus = {x["_id"]: x for x in db.reuniones.find({"_id": {"$in": list(rids)}}, {"titulo": 1, "fecha": 1, "lugar_texto": 1})}
    lista = []
    for a in p.get("asistencias") or []:
        x = reus.get(a.get("reunion_id"))
        if x is None:
            continue
        d = {"id": a["reunion_id"], "titulo": x["titulo"], "fecha": x["fecha"], "lugar_texto": x.get("lugar_texto"),
             "rol": a.get("rol")}
        if adm:
            d["nota"] = a.get("nota")
        lista.append(d)
    lista.sort(key=lambda x: x["fecha"] or "", reverse=True)
    return lista, reus


def _notas(p: dict, reus: dict) -> list[dict]:
    orden = {n.get("id"): i for i, n in enumerate(p.get("notas") or [])}
    notas = [{"id": n.get("id"), "texto": n.get("texto"), "autor": n.get("autor"), "autor_uid": n.get("autor_uid"),
              "creado_en": n.get("creado_en"), "reunion_id": n.get("reunion_id"),
              "reunion": (reus.get(n.get("reunion_id")) or {}).get("titulo")} for n in p.get("notas") or []]
    # Notas del mismo segundo: la más reciente primero (se agregan al final de la lista)
    notas.sort(key=lambda n: (n["creado_en"] or "", orden.get(n["id"], 0)), reverse=True)
    return notas


def _etiquetas(p: dict, ctx: Contexto, adm: bool) -> list[dict]:
    ets = [ctx.etiquetas[e] for e in p.get("etiquetas") or [] if e in ctx.etiquetas
           and (adm or e not in ctx.sensibles_et)]
    return [{"id": e["_id"], "nombre": e["nombre"], "grupo": e.get("grupo")}
            for e in sorted(ets, key=lambda e: (e.get("grupo") or "", e.get("orden", 0)))]


def _coincidencias(db: Database, pid: int) -> list[dict]:
    cerrar_coincidencias_imposibles(db, [pid])
    out = []
    for c in db.coincidencias.find({"estado": "pendiente", "$or": [{"persona_id": pid}, {"candidato_id": pid}]}):
        otro = c["candidato_id"] if c["persona_id"] == pid else c["persona_id"]
        o = db.personas.find_one({"_id": otro}, {"nombre": 1})
        if o:
            out.append({"id": c["_id"], "puntaje": c.get("puntaje"), "estado": c["estado"], "otro_id": otro,
                        "otro_nombre": o["nombre"], "motivo": c.get("motivo")})
    return out


def _historial_autorizacion(db: Database, pid: int) -> list[dict]:
    return [{"id": e["_id"], **{k: e.get(k) for k in CAMPOS_AUTORIZACION}}
            for e in db.autorizaciones.find({"persona_id": pid}).sort([("ts", -1), ("_id", -1)]).limit(50)]


def ficha_de(db: Database, p: dict, quien: Any, ctx: Contexto | None = None) -> dict:
    """La ficha de `p` con los campos de `CAMPOS_FICHA[rol]` y sus recortes por dentro (3.8). Cada valor se calcula
    solo si el rol lo puede ver: lo demás no se lee."""
    ctx = ctx or contexto(db)
    adm, rol = administra(quien), rol_de(quien)
    pid = p["_id"]
    lg = ctx.lugar(p.get("lugar_id"))
    if not adm and p.get("consentimiento") == "no":
        return _no_autorizo({"id": pid, "nombre": p.get("nombre"), "cedula_ult3": acceso.enmascarar_cedula(p.get("cedula")),
                             "lugar": lg.get("nombre") or p.get("lugar_texto"), "consentimiento": "no",
                             "abordaje": _abordaje(p)})
    permitidos = CAMPOS_FICHA[rol]
    hoy = ctx.hoy
    menor = modelo.es_menor(p, hoy)
    edad = modelo.edad_efectiva(p, hoy)
    v = p.get("votacion") if isinstance(p.get("votacion"), dict) else None
    sit = p.get("situacion") if isinstance(p.get("situacion"), dict) else None
    ec = p.get("en_curso") if isinstance(p.get("en_curso"), dict) else None
    cache: dict = {}

    def reuniones():
        if "r" not in cache:
            cache["r"] = _reuniones(db, p, adm)
        return cache["r"]

    def sin_sensibles(extra: Any) -> dict:
        return {k: x for k, x in (extra or {}).items() if adm or k not in ctx.sensibles_campos}

    valores = {
        "id": lambda: pid, "nombre": lambda: p.get("nombre"), "nombre_norm": lambda: p.get("nombre_norm"),
        "tipo_documento": lambda: p.get("tipo_documento"), "cedula": lambda: p.get("cedula"),
        "cedula_verificada": lambda: bool(p.get("cedula_verificada")),
        "cedula_origen": lambda: p.get("cedula_origen") if adm else neutralizar_fuente(p.get("cedula_origen")),
        "cedulas_anteriores": lambda: list(p.get("cedulas_anteriores") or []),
        "cedula_ult3": lambda: acceso.enmascarar_cedula(p.get("cedula")),
        "edad_efectiva": lambda: edad, "rango_edad": lambda: modelo.rango_edad(edad), "menor": lambda: menor,
        "nac_exacta": lambda: bool(p.get("nac_exacta")),
        "sensibles_registrados": lambda: [c for c in modelo.SENSIBLES
                                          if (p.get("sensibles") or {}).get(c) not in (None, "")],
        "sensibles_autorizados": lambda: list(p.get("sensibles_autorizados") or []),
        "telefonos": lambda: _telefonos(p, rol, adm, menor),
        "telefono": lambda: None if (menor and not adm) else p.get("telefono"),
        "telefono2": lambda: None if (menor and not adm) else p.get("telefono2"),
        "lugar_nombre": lambda: lg.get("nombre"), "lugar_tipo": lambda: lg.get("tipo"),
        "geo_manual": lambda: p.get("geo_manual", False),
        "votacion": lambda: _votacion(p, ctx, adm),
        "puesto_nombre": lambda: (v or {}).get("puesto_nombre") or (v or {}).get("puesto_texto") or p.get("puesto_votacion"),
        "consentimiento": lambda: p.get("consentimiento") or "pendiente",
        "consentimiento_canales": lambda: list(p.get("consentimiento_canales") or []),
        "contacto_habilitado": lambda: p.get("contacto_habilitado") is True,
        "mayor_declarado": lambda: p.get("mayor_declarado") is True,
        "autorizacion": lambda: _historial_autorizacion(db, pid),
        "reclamo_en_tramite": lambda: p.get("reclamo_en_tramite") is True,
        "abordaje": lambda: _abordaje(p), "abordaje_seq": lambda: p.get("abordaje_seq") or 0,
        "acercamientos": lambda: _acercamientos(db, pid, rol, adm, menor),
        "en_curso": lambda: ec if (adm or (ec and ec.get("uid") == getattr(quien, "uid", None))) else None,
        "notas": lambda: _notas(p, reuniones()[1]),
        "listas": lambda: list(p.get("listas") or []), "lider": lambda: bool(p.get("lider")),
        "etiquetas": lambda: _etiquetas(p, ctx, adm), "extra": lambda: sin_sensibles(p.get("extra")),
        "origen": lambda: [{"fuente": o.get("fuente"), "datos": o.get("datos")} for o in p.get("origen") or []],
        "procedencia": lambda: dict(p.get("procedencia") or {}),
        "tramites": lambda: sorted(({k: t.get(k) for k in (("fecha", "tipo", "ficha", "direccion", "telefono", "correo")
                                                            if adm else ("fecha", "tipo", "ficha"))}
                                    for t in p.get("tramites") or []), key=lambda t: t["fecha"] or "", reverse=True),
        "alternos": lambda: [{"campo": a.get("campo"), "valor": a.get("valor"),
                              "fuente": a.get("fuente") if adm else neutralizar_fuente(a.get("fuente")),
                              "ts": a.get("ts"), **({"uid": a.get("uid")} if adm else {})}
                             for a in p.get("alternos") or []],
        "avance": lambda: dict(p.get("avance") or {}),
        "historial": lambda: [{"ts": h.get("ts"), "usuario": h.get("usuario"), "uid": h.get("uid"), "rol": h.get("rol"),
                               "accion": h.get("accion"), "detalle": h.get("detalle")}
                              for h in db.auditoria.find({"entidad": "persona", "entidad_id": pid}).sort("_id", -1).limit(40)],
        "coincidencias": lambda: _coincidencias(db, pid),
        "reuniones": lambda: reuniones()[0],
        "fuentes": lambda: list(p.get("fuentes") or []), "completitud": lambda: p.get("completitud", 0),
        "claves_tramites": lambda: list(p.get("claves_tramites") or []),
        "situacion": lambda: ({"estado": sit.get("estado")} if sit else None) if (rol == "consultor" and not adm) else sit,
        "no_disponible": lambda: dict(p.get("no_disponible") or {}),
        "faltan": lambda: [f for f in modelo.faltan(p, hoy, ctx.dias_dato)
                           if adm or rol != "consultor" or f in ("cedula", "puesto", "mesa")],
        "editables": lambda: editables(p, quien), "avisos": lambda: avisos(p, hoy, adm),
    }
    return {k: (valores[k]() if k in valores else p.get(k)) for k in sorted(permitidos)}


def cargar(db: Database, pid: int) -> dict:
    """La ficha activa `pid`: 404 si no existe o se suprimió; 409 (con el id de destino) si se unió con otra."""
    p = db.personas.find_one({"_id": pid})
    if p is None or p.get("eliminado"):
        raise HTTPException(404, "No existe")
    if p.get("fusionada_en"):
        raise HTTPException(409, {"mensaje": "Esta ficha se unió con otra", "id": p["fusionada_en"]})
    return p


def ficha_para(db: Database, quien: Any, pid: int) -> dict:
    """La ficha de `pid` con los campos de `CAMPOS_FICHA[quien.rol]`, `editables`, `avisos` y `faltan`; registra la
    lectura (cuenta en el presupuesto diario de P y C)."""
    p = cargar(db, pid)
    acceso.registrar_lecturas(db, quien, [pid], ficha=True)
    return ficha_de(db, p, quien)


def persona_activa(db: Database, pid: int, proyeccion: dict | None = None) -> dict:
    """Para las escrituras: 404 si no existe; 409 «La ficha se unió o se suprimió» si ya no está activa."""
    p = db.personas.find_one({"_id": pid}, proyeccion)
    if p is None:
        raise HTTPException(404, "No existe")
    if db.personas.count_documents({"_id": pid, **ACTIVA}, limit=1) == 0:
        raise HTTPException(409, "La ficha se unió o se suprimió")
    return p
