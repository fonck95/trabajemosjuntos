"""Modelo de la ficha ampliada: catálogos, predicados y funciones puras que comparten la API, la importación y la
migración.

* Nada aquí escribe en la base; `leer_ajustes` es la única que la lee.
* Las funciones no modifican lo que reciben: devuelven datos nuevos.
* Lectura tolerante: los campos nuevos se leen con `.get()` y valores por defecto, así una ficha que escribió el código
  viejo no rompe nada.
* Las expresiones de MongoDB (`TELS_ACTUALES`, `ETAPA_*`, `expr_*`) tienen su gemelo en Python con el mismo resultado:
  `telefonos_de`, `derivar_telefonos`, `unir_telefonos`, `cambiar_telefono`, `hacer_principal`, `derivar_votacion`.
  Los valores que vienen de fuera van siempre dentro de `$literal`: un texto que empieza por «$» no se lee como campo.
* Los filtros (`filtro_*`) devuelven un dict nuevo en cada llamada. Los que usan `$or` o `$and` se combinan con otros
  filtros dentro de un `$and`, nunca con `{**a, **b}`.
"""
from __future__ import annotations

import copy
import math
import re
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Iterable

from rapidfuzz import fuzz

from .pipeline import texto as tx

# Hora de Colombia (sin horario de verano): días de acercamientos, periodos, edades y fechas de negocio
ZONA = timezone(timedelta(hours=-5))


def hoy_local() -> date:
    return datetime.now(ZONA).date()


# ───────────────────────────── Catálogos (1.3) ─────────────────────────────

SEXOS = {"F": "Mujer", "M": "Hombre", "N": "Prefiere no decir"}
TIPOS_DOCUMENTO = {
    "CC": "Cédula de ciudadanía", "TI": "Tarjeta de identidad", "CE": "Cédula de extranjería",
    "PPT": "Permiso por protección temporal", "PEP": "Permiso especial de permanencia", "PA": "Pasaporte",
}
NIVELES = ["Ninguno", "Primaria", "Secundaria", "Técnico", "Tecnólogo", "Universitario", "Posgrado"]
ESTADOS_CIVILES = ["Soltero(a)", "Casado(a)", "Unión libre", "Separado(a) o divorciado(a)", "Viudo(a)"]
SITUACIONES_LABORALES = ["Empleado(a)", "Independiente", "Agricultor(a) o pescador(a)", "Desempleado(a)", "Estudiante",
                         "Oficios del hogar", "Pensionado(a)", "Otra"]
TENENCIAS = ["Propia", "Arriendo", "Familiar", "Posesión", "Otra"]
REGIMENES_SALUD = ["Contributivo", "Subsidiado", "Especial", "Ninguno"]
RANGOS_EDAD = ["<18", "18-24", "25-34", "35-44", "45-54", "55-64", "65+"]
# Datos sensibles (Ley 1581, art. 5): solo con autorización explícita por categoría, y apagados por defecto
SENSIBLES = {
    "etnia": {"etiqueta": "Pertenencia étnica",
              "valores": ["Indígena", "Negro o afrocolombiano", "Raizal", "Palenquero", "Rrom", "Ninguno",
                          "Prefiere no decir"]},
    "discapacidad": {"etiqueta": "Discapacidad",
                     "valores": ["Física", "Visual", "Auditiva", "Intelectual", "Psicosocial", "Múltiple", "Ninguna",
                                 "Prefiere no decir"]},
    "victima": {"etiqueta": "Víctima del conflicto", "valores": ["Sí", "No", "Prefiere no decir"]},
}
NOMBRES_ROL = {"admin": "Administrador", "planillero": "Planillero", "consultor": "Consultor"}

# ───────────────────────────── Autorización del titular (1.6) ─────────────────────────────

ESTADOS_AUTORIZACION = {"si": "Sí autoriza", "no": "No autoriza", "revocada": "Revocada", "pendiente": "Pendiente"}
MEDIOS_AUTORIZACION = {
    "escrito": "Escrito", "verbal_presencial": "Verbal presencial", "verbal_telefono": "Verbal por teléfono",
    "mensaje": "Mensaje (WhatsApp o SMS)", "formulario": "Formulario", "panel": "Registrado en el panel",
    "migrado": "Dato anterior", "declarado_planilla": "Declarado en planilla", "fusion": "Unión de fichas",
}
# Medios con que P y C pueden registrar un «sí» (A puede cualquiera)
MEDIOS_POR_ROL = {"planillero": ["escrito", "verbal_presencial", "formulario"], "consultor": ["verbal_telefono", "mensaje"]}
CANALES_AUTORIZACION = {"llamada": "Llamada", "whatsapp": "WhatsApp", "sms": "SMS", "correo": "Correo",
                        "visita": "Visita", "grupos": "Listas o grupos de difusión"}
# Lo que vale un «sí» con canales_implicitos (migrado o PATCH heredado de A). Nunca grupos, visita ni correo
CANALES_IMPLICITOS = ("llamada", "whatsapp", "sms")

# ───────────────────────────── Acercamientos (4.1) ─────────────────────────────

CANALES = {"llamada": "Llamada", "whatsapp": "WhatsApp", "sms": "SMS", "visita": "Visita", "reunion": "Reunión",
           "correo": "Correo", "otro": "Otro"}
# Valores neutrales (sin intención de voto ni simpatía). La etiqueta cambia según el canal: `etiqueta_visita` vale para
# visita y reunión, `etiqueta` para los demás
RESULTADOS = {
    "contesto": {"etiqueta": "Contestó", "etiqueta_visita": "Atendió", "efectivo": True},
    "no_contesto": {"etiqueta": "No contestó", "etiqueta_visita": "No estaba", "efectivo": False},
    "buzon": {"etiqueta": "Buzón o mensaje dejado", "etiqueta_visita": "Buzón o mensaje dejado", "efectivo": False},
    "volver_llamar": {"etiqueta": "Pidió volver a llamar", "etiqueta_visita": "Pidió volver a visitar", "efectivo": True},
    "numero_equivocado": {"etiqueta": "Número equivocado", "etiqueta_visita": "Número equivocado", "efectivo": False},
    "numero_inexistente": {"etiqueta": "Número no existe", "etiqueta_visita": "Número no existe", "efectivo": False},
    "actualizo_datos": {"etiqueta": "Actualizó datos", "etiqueta_visita": "Actualizó datos", "efectivo": True},
    "pidio_informacion": {"etiqueta": "Pidió información", "etiqueta_visita": "Pidió información", "efectivo": True},
    "solicitud_derechos": {"etiqueta": "Pidió consultar, corregir o borrar sus datos",
                           "etiqueta_visita": "Pidió consultar, corregir o borrar sus datos", "efectivo": True},
    "no_contactar": {"etiqueta": "Pidió no ser contactado", "etiqueta_visita": "Rechazó", "efectivo": True},
    "no_vive_aqui": {"etiqueta": "No vive aquí", "etiqueta_visita": "No vive aquí", "efectivo": False},
    "fallecio": {"etiqueta": "Falleció", "etiqueta_visita": "Falleció", "efectivo": False},
}
EFECTIVOS = frozenset(k for k, v in RESULTADOS.items() if v["efectivo"])
# Suman a intentos_sin_exito (y un acercamiento efectivo los vuelve a cero)
SIN_EXITO = ("no_contesto", "buzon")
FRANJAS = {"manana": "Mañana", "tarde": "Tarde", "noche": "Noche"}
ESTADOS_ABORDAJE = {"sin_abordar": "Sin abordar", "intentado": "Intentado", "contactado": "Contactado",
                    "no_contactar": "No contactar"}


def etiqueta_resultado(resultado: str, canal: str | None = None) -> str:
    r = RESULTADOS.get(resultado)
    if r is None:
        return resultado
    return r["etiqueta_visita"] if canal in ("visita", "reunion") else r["etiqueta"]


# ───────────────────────────── Seguimiento (1.7) ─────────────────────────────

SITUACIONES = {"activa": "Activa", "fallecida": "Fallecida", "no_reside": "Ya no vive en Yondó"}
MOTIVOS_ACTUALIZACION = {
    "pedido_consultor": "Pedido del consultor", "no_contesta": "No contesta", "sin_telefono_valido": "Sin teléfono válido",
    "direccion": "No vive en la dirección", "alta_consultor": "Alta pedida por un consultor",
    "administrador": "Pedido del administrador",
}
CAMPOS_NO_DISPONIBLE = ("cedula", "telefono", "mesa", "puesto", "edad", "sexo")
MOTIVOS_NO_DISPONIBLE = {"no_la_dio": "No la dio", "no_tiene": "No lo tiene", "no_sabe": "No sabe"}

# ───────────────────────────── Teléfonos (1.2) ─────────────────────────────

ESTADOS_TELEFONO = {"sin_verificar": "Sin verificar", "confirmado": "Confirmado", "no_usa": "Ya no lo usa",
                    "equivocado": "Equivocado", "inexistente": "No existe", "retirado": "Retirado"}
USABLES = frozenset({"sin_verificar", "confirmado"})
TIPOS_TELEFONO = {"celular": "Celular", "fijo": "Fijo"}
FUENTES_TEL = ("tramites", "cedulas", "planilla", "panel", "reunion", "consultor")
# Forma de cada elemento de `telefonos`, con sus valores iniciales
CAMPOS_TELEFONO = ("numero", "tipo", "fuentes", "primera_vez", "ultima_vez", "estado", "whatsapp", "no_contactar",
                   "agregado_por", "estado_por", "estado_en", "nota")
# Lo único que cambia `expr_estado_telefono` / `cambiar_telefono`
CAMBIOS_TELEFONO = ("estado", "whatsapp", "no_contactar", "nota", "estado_por", "estado_en")

# ───────────────────────────── Votación (1.4) ─────────────────────────────

ESTADOS_VOTACION = {"verificado": "Verificado", "sin_verificar": "Sin verificar", "por_confirmar": "Por confirmar"}
DONDE_VOTA = {"yondo": "En Yondó", "otro_municipio": "En otro municipio", "no_inscrito": "No está inscrito"}
FUENTES_VOTACION = ("cedulas", "planilla", "panel", "consultor", "titular")
MESAS_SIN_CATALOGO = 99  # tope de la mesa cuando el puesto no dice cuántas tiene

# ───────────────────────────── Procedencia, avance y auditoría (1.5, 1.9) ─────────────────────────────

CONFIANZA = {"tramites": 1, "cedulas": 2, "planilla": 3, "consultor": 3, "panel": 4, "reunion": 4, "manual": 4}
CAMPOS_PROCEDENCIA = ("cedula", "tipo_documento", "sexo", "edad", "fecha_nacimiento", "correo", "direccion", "votacion",
                      "estado_civil", "nivel_educativo", "situacion_laboral", "ocupacion")
CAMPOS_AVANCE = ("cedula", "telefono", "sexo", "edad", "direccion", "lugar", "ubicacion", "puesto", "mesa", "autorizacion",
                 "correo", "estado_civil", "nivel_educativo", "situacion_laboral", "ocupacion", "personas_hogar",
                 "jefe_hogar", "tenencia_vivienda", "estrato", "regimen_salud")
ETIQUETAS_CAMPOS = {
    "cedula": "Cédula", "telefono": "Teléfono", "sexo": "Sexo", "edad": "Edad", "direccion": "Dirección",
    "lugar": "Barrio o vereda", "ubicacion": "Ubicación", "puesto": "Puesto de votación", "mesa": "Mesa",
    "autorizacion": "Autorización", "correo": "Correo", "estado_civil": "Estado civil",
    "nivel_educativo": "Nivel educativo", "situacion_laboral": "Situación laboral", "ocupacion": "Ocupación",
    "personas_hogar": "Personas en el hogar", "jefe_hogar": "Jefe de hogar", "tenencia_vivienda": "Tenencia de la vivienda",
    "estrato": "Estrato", "regimen_salud": "Régimen de salud",
}
# «Faltan» en Habitantes, la ficha y las listas de trabajo (7.3)
CAMPOS_FALTAN = ("cedula", "telefono", "sexo", "edad", "lugar", "puesto", "mesa", "direccion", "autorizacion")
# Acciones canónicas de la auditoría que cuentan los indicadores (5.1)
ACCIONES = ("crear", "editar", "telefono_agregar", "telefono_estado", "telefono_principal", "telefono_retirar",
            "autorizacion", "ubicar", "asistencia", "acercamiento", "actualizacion_atendida", "situacion", "no_disponible")
# Las que cuentan como «actualizadas» (no la asistencia ni el acercamiento)
ACCIONES_EDICION = ("editar", "telefono_agregar", "telefono_estado", "telefono_principal", "telefono_retirar",
                    "autorizacion", "ubicar", "situacion", "no_disponible", "actualizacion_atendida")

# ───────────────────────────── Ajustes (1.8) ─────────────────────────────

AJUSTES_POR_DEFECTO: dict[str, Any] = {
    "contactar_pendientes": False, "dias_entre_intentos": 2, "max_intentos_sin_exito": 4,
    "seguimiento_activo": False, "dias_seguimiento": 60, "dias_reintento_dato": 90,
    "horario": {"semana": ["07:00", "19:00"], "sabado": ["08:00", "15:00"], "domingo": False},
    "sensibles_activos": False, "eleccion_vigente": "2026-presidencial",
    "aviso_privacidad": {"version": "2026-11-v1", "responsable": "", "contacto": "", "canal_derechos": "", "texto": ""},
    "vigencia_base": None, "compromiso_version": "2026-11-v1",
    "presupuesto_diario": {"planillero": 1000, "consultor": 300},
    "sesion": {"horas_max": 10, "inactividad_min": 60, "max_por_usuario": 2},
    "tope_cedulas_dictadas": 20,
    "enlace_consulta_puesto": "https://wsp.registraduria.gov.co/censo/consultar/",
}


def _combinar(base: dict, encima: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in encima.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _combinar(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def leer_ajustes(db) -> dict:
    """Ajustes vigentes: lo guardado en `meta` (documento «ajustes», campos en el nivel superior) sobre los valores por
    defecto, también dentro de los objetos (horario, sesion…). Devuelve una copia que se puede modificar."""
    guardado = db.meta.find_one({"_id": "ajustes"}) or {}
    return _combinar(AJUSTES_POR_DEFECTO, {k: v for k, v in guardado.items() if k != "_id"})


# ───────────────────────────── Fechas, edad y ubicación ─────────────────────────────

_FECHA = re.compile(r"\d{4}-\d{2}-\d{2}")


def fecha_valida(s: Any) -> date | None:
    """La fecha si `s` es AAAA-MM-DD y existe (1990-06-31 no); si no, None. Nunca lanza error: una fecha imposible
    guardada de antes se conserva como texto y aquí cuenta como desconocida."""
    if isinstance(s, datetime):
        return s.date()
    if isinstance(s, date):
        return s
    if not isinstance(s, str) or not _FECHA.fullmatch(s.strip()):
        return None
    try:
        return date.fromisoformat(s.strip())
    except ValueError:
        return None


def _fecha_de(v: Any) -> date | None:
    """Fecha de un valor que puede ser AAAA-MM-DD, un instante ISO («2026-11-04T15:00:00+00:00») o un datetime."""
    if isinstance(v, str):
        return fecha_valida(v[:10])
    return fecha_valida(v)


def fecha_local(ts: Any) -> str | None:
    """Fecha AAAA-MM-DD en hora de Colombia de un instante (texto ISO, como `bd.ahora()`, o datetime). Un texto sin zona
    se toma como UTC; una fecha sola queda igual."""
    if isinstance(ts, str):
        if _FECHA.fullmatch(ts.strip()):
            f = fecha_valida(ts)
            return f.isoformat() if f else None
        try:
            ts = datetime.fromisoformat(ts.strip())
        except ValueError:
            return None
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(ZONA).date().isoformat()
    if isinstance(ts, date):
        return ts.isoformat()
    return None


def _entero(v: Any) -> int | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v) if v.is_integer() else None
    if isinstance(v, str) and v.strip().isdigit():
        return int(v.strip())
    return None


def _edad(v: Any) -> int | None:
    e = _entero(v)
    return e if e is not None and 0 <= e <= 130 else None


def _restar_anios(d: date, n: int) -> date:
    try:
        return d.replace(year=d.year - n)
    except ValueError:  # 29 de febrero en un año que no es bisiesto
        return d.replace(year=d.year - n, day=28)


def _anios_entre(desde: date, hasta: date) -> int:
    return hasta.year - desde.year - ((hasta.month, hasta.day) < (desde.month, desde.day))


def edad_efectiva(p: dict, hoy: date | None = None) -> int | None:
    """Años cumplidos según la fecha de nacimiento (si es válida); si no, la edad declarada más los años completos desde
    que se declaró (`edad_ref`, o `creado_en`, o hoy). None si no hay ninguna. Con la edad declarada el error es de
    ±1 año."""
    hoy = hoy or hoy_local()
    nac = fecha_valida(p.get("fecha_nacimiento"))
    if nac is not None:
        e = _anios_entre(nac, hoy)
        return e if e >= 0 else None
    edad = _edad(p.get("edad"))
    if edad is None:
        return None
    ref = _fecha_de(p.get("edad_ref")) or _fecha_de(p.get("creado_en")) or hoy
    return edad + max(0, _anios_entre(ref, hoy))


def calcular_nac(p: dict, hoy: date | None = None) -> dict:
    """`nac_aprox`, `nac_exacta` y `nac_base` de una ficha.

    Con fecha de nacimiento válida, esa fecha (exacta). Si no, `edad_ref − edad años − 182 días` (aproximada, a mitad del
    año de nacimiento posible); `edad_ref` cae en `creado_en` o en hoy si falta. Fecha inválida y edad nula dan None.
    `nac_base` copia la edad y la fecha que se usaron: la reconciliación detecta así lo que cambió el código viejo."""
    base = {"edad": p.get("edad"), "fecha": p.get("fecha_nacimiento")}
    nac = fecha_valida(p.get("fecha_nacimiento"))
    if nac is not None:
        return {"nac_aprox": nac.isoformat(), "nac_exacta": True, "nac_base": base}
    edad = _edad(p.get("edad"))
    if edad is None:
        return {"nac_aprox": None, "nac_exacta": False, "nac_base": base}
    ref = _fecha_de(p.get("edad_ref")) or _fecha_de(p.get("creado_en")) or (hoy or hoy_local())
    aprox = _restar_anios(ref, edad) - timedelta(days=182)
    return {"nac_aprox": aprox.isoformat(), "nac_exacta": False, "nac_base": base}


def rango_edad(edad: Any) -> str | None:
    """Rango de RANGOS_EDAD de una edad en años (la de `edad_efectiva`)."""
    e = _entero(edad)
    if e is None or e < 0:
        return None
    for tope, rango in ((17, "<18"), (24, "18-24"), (34, "25-34"), (44, "35-44"), (54, "45-54"), (64, "55-64")):
        if e <= tope:
            return rango
    return "65+"


def _limite_mayoria(hoy: date) -> str:
    return _restar_anios(hoy, 18).isoformat()


def _nac_para_predicado(p: dict, hoy: date) -> str | None:
    # Con edad o fecha en la ficha se calcula (no depende de que alguien haya derivado nac_aprox antes); sin ellas, lo
    # guardado. En la base las dos coinciden: es el mismo valor que mira el filtro
    if p.get("edad") is not None or p.get("fecha_nacimiento") not in (None, ""):
        return calcular_nac(p, hoy)["nac_aprox"]
    return p.get("nac_aprox")


def es_menor(p: dict, hoy: date | None = None) -> bool:
    """Gemelo de `filtro_menor`: nac_aprox posterior a hoy − 18 años, o tarjeta de identidad."""
    if p.get("tipo_documento") == "TI":
        return True
    hoy = hoy or hoy_local()
    nac = _nac_para_predicado(p, hoy)
    return isinstance(nac, str) and nac > _limite_mayoria(hoy)


def es_adulto_conocido(p: dict, hoy: date | None = None) -> bool:
    """Gemelo de `filtro_adulto_conocido`: no es menor y se sabe que es mayor (por la edad, por tener cédula de
    ciudadanía o porque lo declaró al autorizar)."""
    hoy = hoy or hoy_local()
    if es_menor(p, hoy):
        return False
    nac = _nac_para_predicado(p, hoy)
    return (isinstance(nac, str) and nac <= _limite_mayoria(hoy)) or p.get("tipo_documento") == "CC" \
        or p.get("mayor_declarado") is True


def filtro_menor(hoy: date | None = None) -> dict:
    return {"$or": [{"nac_aprox": {"$gt": _limite_mayoria(hoy or hoy_local())}}, {"tipo_documento": "TI"}]}


def filtro_adulto_conocido(hoy: date | None = None) -> dict:
    lim = _limite_mayoria(hoy or hoy_local())
    return {"$and": [
        {"nac_aprox": {"$not": {"$gt": lim}}}, {"tipo_documento": {"$ne": "TI"}},
        {"$or": [{"nac_aprox": {"$lte": lim}}, {"tipo_documento": "CC"}, {"mayor_declarado": True}]},
    ]}


def filtro_vigente() -> dict:
    """ACTIVA y sin situación final reportada (fallecida o ya no vive en Yondó)."""
    from .db import ACTIVA  # aquí: db importa este módulo
    return {**copy.deepcopy(ACTIVA), "situacion.estado": {"$in": [None, "activa"]}}


# Rango de coordenadas que acepta el servidor ((lon, lat) mínimo, (lon, lat) máximo), como RANGO_YONDO de mapa3d.js
RANGO_YONDO = ((-74.6, 6.3), (-73.6, 7.5))


def _numero(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    v = float(v)
    return v if math.isfinite(v) else None


def punto(lat: Any, lon: Any) -> dict | None:
    """GeoJSON Point de la ficha si `lat` y `lon` son números dentro de Yondó; con uno solo, o fuera, None."""
    la, lo = _numero(lat), _numero(lon)
    if la is None or lo is None:
        return None
    (lon_min, lat_min), (lon_max, lat_max) = RANGO_YONDO
    if not (lat_min <= la <= lat_max and lon_min <= lo <= lon_max):
        return None
    return {"type": "Point", "coordinates": [lo, la]}


# ───────────────────────────── Teléfonos ─────────────────────────────

def tipo_telefono(numero: Any) -> str | None:
    """«celular» (10 dígitos que empiezan por 3) o «fijo»; None sin dígitos."""
    d = re.sub(r"\D", "", str(numero or ""))
    if not d:
        return None
    return "celular" if len(d) == 10 and d[0] == "3" else "fijo"


def telefono_nuevo(numero: Any, fuente: str | None = None, fecha: str | None = None, **campos) -> dict:
    """Un elemento de `telefonos` con sus valores iniciales. El número va tal cual (quien llama ya lo normalizó con
    `tx.telefonos`, o es un dato heredado que se conserva). `campos` pisa cualquiera de CAMPOS_TELEFONO."""
    desconocidos = set(campos) - set(CAMPOS_TELEFONO)
    if desconocidos:
        raise ValueError(f"Campos de teléfono desconocidos: {sorted(desconocidos)}")
    t = {"numero": numero, "tipo": tipo_telefono(numero), "fuentes": [fuente] if fuente else [], "primera_vez": fecha,
         "ultima_vez": fecha, "estado": "sin_verificar", "whatsapp": None, "no_contactar": False, "agregado_por": None,
         "estado_por": None, "estado_en": None, "nota": None}
    t.update(copy.deepcopy(campos))
    return t


def es_usable(t: dict) -> bool:
    estado = t.get("estado")
    return (estado if estado is not None else "sin_verificar") in USABLES and t.get("no_contactar") is not True


def usables(lista: Iterable[dict] | None) -> list[dict]:
    """Los números usables, en su orden (el primero es el principal)."""
    return [copy.deepcopy(t) for t in lista or [] if es_usable(t)]


def derivar_telefonos(lista: Iterable[dict] | None) -> dict:
    """`telefono` y `telefono2` derivados: el primer y el segundo número usable."""
    nums = [t.get("numero") for t in usables(lista)]
    return {"telefono": nums[0] if nums else None, "telefono2": nums[1] if len(nums) > 1 else None}


def telefonos_de(p: dict) -> list[dict]:
    """Gemelo de TELS_ACTUALES: la lista `telefonos` o, si una ficha vieja no la tiene, `telefono` y `telefono2`."""
    if isinstance(p.get("telefonos"), list):
        return copy.deepcopy(p["telefonos"])
    return [{"numero": p.get(k), "tipo": None, "fuentes": ["panel"], "estado": "sin_verificar", "no_contactar": False}
            for k in ("telefono", "telefono2") if p.get(k) not in (None, "")]


def _union(a: Any, b: Any) -> list:
    ea = list(a) if isinstance(a, list) else []
    return ea + [x for x in (b if isinstance(b, list) else []) if x not in ea]


def _mayor(a: Any, b: Any) -> Any:
    vals = [x for x in (a, b) if x is not None]
    return max(vals) if vals else None


def _menor(a: Any, b: Any) -> Any:
    vals = [x for x in (a, b) if x is not None]
    return min(vals) if vals else None


def _deduplicar(nuevos: Iterable[dict | str]) -> list[dict]:
    """Completa los números nuevos con los valores iniciales y junta los repetidos (fuentes, primera y última vez)."""
    out: list[dict] = []
    por_numero: dict[Any, dict] = {}
    for n in nuevos or []:
        if isinstance(n, str):
            n = {"numero": n}
        if n.get("numero") in (None, ""):
            continue
        n = {**telefono_nuevo(n["numero"]), **copy.deepcopy(n)}
        n["fuentes"] = _union([], n.get("fuentes"))
        previo = por_numero.get(n["numero"])
        if previo is None:
            por_numero[n["numero"]] = n
            out.append(n)
        else:
            previo["fuentes"] = _union(previo["fuentes"], n["fuentes"])
            previo["primera_vez"] = _menor(previo.get("primera_vez"), n.get("primera_vez"))
            previo["ultima_vez"] = _mayor(previo.get("ultima_vez"), n.get("ultima_vez"))
    return out


def unir_telefonos(lista: Iterable[dict] | None, nuevos: Iterable[dict | str], al_frente: bool = False) -> list[dict]:
    """Gemelo de `expr_unir_telefonos`. A un número ya presente solo se le suman las fuentes y la última vez mayor: su
    estado no cambia (un número retirado, equivocado o que ya no usa no se reactiva). Los que no están se agregan al
    final, o al principio con `al_frente`, en el orden dado. No modifica nada de lo que recibe."""
    nuevos = _deduplicar(nuevos)
    por_numero = {n["numero"]: n for n in nuevos}
    actuales = []
    for t in lista or []:
        t = copy.deepcopy(t)
        n = por_numero.get(t.get("numero"))
        if n is not None:
            t["fuentes"] = _union(t.get("fuentes"), n["fuentes"])
            t["ultima_vez"] = _mayor(t.get("ultima_vez"), n.get("ultima_vez"))
        actuales.append(t)
    presentes = [t.get("numero") for t in actuales]
    agregados = [n for n in nuevos if n["numero"] not in presentes]
    return agregados + actuales if al_frente else actuales + agregados


def _validar_cambios(cambios: dict) -> dict:
    desconocidos = set(cambios) - set(CAMBIOS_TELEFONO)
    if desconocidos:
        raise ValueError(f"No se pueden cambiar: {sorted(desconocidos)}")
    if "estado" in cambios and cambios["estado"] not in ESTADOS_TELEFONO:
        raise ValueError(f"Estado de teléfono desconocido: {cambios['estado']}")
    return copy.deepcopy(dict(cambios))


def cambiar_telefono(lista: Iterable[dict] | None, numero: Any, cambios: dict) -> list[dict]:
    """Gemelo de `expr_estado_telefono`: cambia estado, WhatsApp, «no contactar», nota y autoría solo en ese número."""
    cambios = _validar_cambios(cambios)
    return [{**copy.deepcopy(t), **copy.deepcopy(cambios)} if t.get("numero") == numero else copy.deepcopy(t)
            for t in lista or []]


def hacer_principal(lista: Iterable[dict] | None, numero: Any) -> list[dict]:
    """Gemelo de `expr_principal`: el número pasa a la posición 0 y los demás siguen en su orden."""
    lista = [copy.deepcopy(t) for t in lista or []]
    return [t for t in lista if t.get("numero") == numero] + [t for t in lista if t.get("numero") != numero]


def telefonos_iniciales(p: dict, fechas_imp: dict | None = None) -> list[dict]:
    """La lista `telefonos` de una ficha vieja (paso 2 de la migración), en este orden:

    1. `telefono` y `telefono2` tal cual, aunque hoy `tx.telefonos` los rechace: el `telefono` derivado no cambia y
       `telefono2` solo se llena si estaba vacío;
    2. los números de los trámites (separados por «;»), del más frecuente al menos frecuente;
    3. los de cada registro de la base con cédula (`origen`).

    Las fuentes salen de dónde aparece cada número (uno que solo está en la ficha viene del panel). La primera y la
    última vez, de las fechas de los trámites y de las importaciones (`fechas_imp`: id de importación → AAAA-MM-DD)."""
    fechas_imp = fechas_imp or {}
    orden: list[Any] = []
    fuentes: dict[Any, list[str]] = {}
    fechas: dict[Any, list[str]] = {}

    def anotar(n: Any, fuente: str | None, fecha: str | None) -> None:
        if n in (None, ""):
            return
        if n not in fuentes:
            orden.append(n)
            fuentes[n], fechas[n] = [], []
        if fuente and fuente not in fuentes[n]:
            fuentes[n].append(fuente)
        if fecha:
            fechas[n].append(fecha)

    for k in ("telefono", "telefono2"):
        anotar(p.get(k), None, None)
    conteo: dict[str, int] = {}
    en_tramites: list[tuple[str, str | None]] = []
    for t in p.get("tramites") or []:
        for n in str(t.get("telefono") or "").split(";"):
            n = n.strip()
            if n:
                conteo[n] = conteo.get(n, 0) + 1
                en_tramites.append((n, t.get("fecha")))
    primero = {n: i for i, (n, _) in reversed(list(enumerate(en_tramites)))}
    por_frecuencia = sorted(conteo, key=lambda n: (-conteo[n], primero[n]))
    for n in por_frecuencia:
        anotar(n, "tramites", None)
    for n, f in en_tramites:
        anotar(n, "tramites", f)
    for o in p.get("origen") or []:
        if o.get("fuente") != "cedulas":
            continue
        fecha = fechas_imp.get(o.get("importacion_id"))
        for n in (o.get("datos") or {}).get("telefonos") or []:
            anotar(n, "cedulas", fecha)
    return [telefono_nuevo(n, fecha=None, fuentes=fuentes[n] or ["panel"], primera_vez=min(fechas[n], default=None),
                           ultima_vez=max(fechas[n], default=None)) for n in orden]


# Expresiones de pipeline sobre los teléfonos. Toda expresión parte del valor actual con respaldo: una ficha sin
# `telefonos` (escrita por el código viejo) no pierde sus números
LEGADO = {"$filter": {"input": [
    {"numero": "$telefono", "tipo": None, "fuentes": ["panel"], "estado": "sin_verificar", "no_contactar": False},
    {"numero": "$telefono2", "tipo": None, "fuentes": ["panel"], "estado": "sin_verificar", "no_contactar": False}],
    "as": "t", "cond": {"$not": [{"$in": [{"$ifNull": ["$$t.numero", None]}, [None, ""]]}]}}}
TELS_ACTUALES = {"$ifNull": ["$telefonos", LEGADO]}
_ES_USABLE = {"$and": [{"$in": [{"$ifNull": ["$$t.estado", "sin_verificar"]}, sorted(USABLES)]},
                       {"$ne": ["$$t.no_contactar", True]}]}
_USABLES = {"$filter": {"input": TELS_ACTUALES, "as": "t", "cond": _ES_USABLE}}
# Etapa $set que deriva telefono y telefono2 (primer y segundo número usable) en la misma actualización
ETAPA_DERIVAR_TELEFONOS = {"$set": {
    "telefono": {"$ifNull": [{"$arrayElemAt": [{"$map": {"input": _USABLES, "as": "u", "in": "$$u.numero"}}, 0]}, None]},
    "telefono2": {"$ifNull": [{"$arrayElemAt": [{"$map": {"input": _USABLES, "as": "u", "in": "$$u.numero"}}, 1]}, None]},
}}


def _expr_union(a: Any, b: Any) -> dict:
    return {"$let": {"vars": {"ua": {"$ifNull": [a, []]}, "ub": {"$ifNull": [b, []]}}, "in": {"$concatArrays": [
        "$$ua", {"$filter": {"input": "$$ub", "as": "f", "cond": {"$not": [{"$in": ["$$f", "$$ua"]}]}}}]}}}


def expr_unir_telefonos(nuevos: Iterable[dict | str], al_frente: bool = False) -> list[dict]:
    """Actualización (pipeline) que une `nuevos` a la lista actual, como `unir_telefonos`, y deriva telefono y telefono2.
    Uso: `update_one({"_id": pid, **ACTIVA}, expr_unir_telefonos([...]))`. Nunca se escribe una lista calculada en
    Python: la importación puede estar agregando números al mismo tiempo."""
    lit = {"$literal": _deduplicar(nuevos)}
    existentes = {"$map": {"input": "$$a", "as": "t", "in": {"$let": {
        "vars": {"n": {"$arrayElemAt": [{"$filter": {"input": lit, "as": "x",
                                                      "cond": {"$eq": ["$$x.numero", "$$t.numero"]}}}, 0]}},
        "in": {"$cond": [{"$eq": [{"$type": "$$n"}, "missing"]}, "$$t", {"$mergeObjects": ["$$t", {
            "fuentes": _expr_union("$$t.fuentes", "$$n.fuentes"),
            "ultima_vez": {"$max": ["$$t.ultima_vez", "$$n.ultima_vez"]}}]}]}}}}}
    agregados = {"$filter": {"input": lit, "as": "x", "cond": {"$not": [{"$in": [
        "$$x.numero", {"$map": {"input": "$$a", "as": "t", "in": "$$t.numero"}}]}]}}}
    partes = [agregados, existentes] if al_frente else [existentes, agregados]
    return [{"$set": {"telefonos": {"$let": {"vars": {"a": TELS_ACTUALES}, "in": {"$concatArrays": partes}}}}},
            ETAPA_DERIVAR_TELEFONOS]


def expr_estado_telefono(numero: Any, cambios: dict) -> list[dict]:
    """Actualización (pipeline) que cambia estado, WhatsApp, «no contactar», nota y autoría solo en ese número."""
    cambios = _validar_cambios(cambios)
    return [{"$set": {"telefonos": {"$map": {"input": TELS_ACTUALES, "as": "t", "in": {"$cond": [
        {"$eq": ["$$t.numero", {"$literal": numero}]}, {"$mergeObjects": ["$$t", {"$literal": cambios}]}, "$$t"]}}}}},
        ETAPA_DERIVAR_TELEFONOS]


def expr_principal(numero: Any) -> list[dict]:
    """Actualización (pipeline) que pone el número en la posición 0 («Hacer principal»)."""
    es = {"$eq": ["$$t.numero", {"$literal": numero}]}
    return [{"$set": {"telefonos": {"$let": {"vars": {"a": TELS_ACTUALES}, "in": {"$concatArrays": [
        {"$filter": {"input": "$$a", "as": "t", "cond": es}},
        {"$filter": {"input": "$$a", "as": "t", "cond": {"$not": [es]}}}]}}}}},
        ETAPA_DERIVAR_TELEFONOS]


# ───────────────────────────── Puesto y mesa ─────────────────────────────

_MESA = re.compile(r"(?<!\d)(\d{1,3})(?!\d)")


def normalizar_mesa(v: Any) -> int | None:
    """El primer número de 1 a 3 dígitos («Mesa # 9» → 9). El rango (1 a las mesas del puesto) lo revisa quien llama."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v if 0 <= v <= 999 else None
    if isinstance(v, float):
        return int(v) if v.is_integer() and 0 <= v <= 999 else None
    m = _MESA.search(str(v))
    return int(m.group(1)) if m else None


# Palabras que no distinguen un puesto de otro. «I.E.R.» y «C.E.R» quedan como IER y CER al juntar las letras sueltas
GENERICAS_PUESTO = frozenset({"IE", "IER", "CER", "INSTITUCION", "EDUCATIVA", "CENTRO", "RURAL", "SECCION", "PRIMARIA",
                              "PUESTO", "COLEGIO", "ESCUELA", "SEDE", "DEL", "DE", "LA", "EL"})
PARECIDO_PUESTO = 90


@lru_cache(maxsize=4096)
def normalizar_puesto(s: Any) -> str:
    """Mayúsculas, sin tildes ni puntuación, letras sueltas juntas («I E R» → IER) y sin palabras genéricas."""
    palabras, sueltas = [], []
    for w in re.sub(r"[^A-Z0-9 ]+", " ", tx.limpiar(s)).split():
        if len(w) == 1 and w.isalpha():
            sueltas.append(w)
            continue
        if sueltas:
            palabras.append("".join(sueltas))
            sueltas = []
        palabras.append(w)
    if sueltas:
        palabras.append("".join(sueltas))
    return " ".join(w for w in palabras if w not in GENERICAS_PUESTO)


def _parecido_puesto(a: str, b: str) -> bool:
    return bool(a and b) and fuzz.token_sort_ratio(a, b) >= PARECIDO_PUESTO


def reconocer_puesto(texto: Any, puestos: Iterable[dict]) -> tuple[int | None, bool]:
    """(id del puesto, ambiguo) para un texto escrito a mano o importado.

    Se compara (token_sort_ratio ≥ 90) contra el nombre y los alias de cada puesto activo, normalizados igual. Hacen
    falta al menos 2 palabras distintivas («LUIS» o «SAN» solos no se reconocen). Un texto que coincide con un alias
    ambiguo («CABECERA MUNICIPAL») o con varios puestos devuelve (None, True); sin coincidencia, (None, False)."""
    t = normalizar_puesto(texto)
    if not t:
        return None, False
    puestos = [p for p in puestos if p.get("activo") is not False]
    if any(_parecido_puesto(t, normalizar_puesto(a)) for p in puestos for a in p.get("alias_ambiguos") or []):
        return None, True
    if len(t.split()) < 2:
        return None, False
    ids = {p.get("_id", p.get("id")) for p in puestos
           if any(_parecido_puesto(t, normalizar_puesto(n)) for n in [p.get("nombre"), *(p.get("alias") or [])])}
    if len(ids) == 1:
        return ids.pop(), False
    return None, len(ids) > 1


def derivar_votacion(v: Any) -> dict:
    """Gemelo de ETAPA_DERIVAR_VOTACION: `puesto_votacion` (nombre del catálogo, texto escrito u «Otro municipio: X») y
    `mesa` (el texto original o el número). Sin `votacion` no cambia nada: devuelve {}."""
    if not isinstance(v, dict):
        return {}
    if v.get("puesto_nombre") is not None:
        pv = v["puesto_nombre"]
    elif v.get("puesto_texto") is not None:
        pv = v["puesto_texto"]
    elif v.get("donde") == "otro_municipio":
        pv = "Otro municipio: " + v["municipio"] if isinstance(v.get("municipio"), str) else "Otro municipio"
    else:
        pv = None
    if v.get("mesa_texto") is not None:
        mesa = v["mesa_texto"]
    else:
        mesa = str(v["mesa"]) if v.get("mesa") is not None else None
    return {"puesto_votacion": pv, "mesa": mesa}


_ES_VOTACION = {"$eq": [{"$type": "$votacion"}, "object"]}
ETAPA_DERIVAR_VOTACION = {"$set": {
    "puesto_votacion": {"$cond": [_ES_VOTACION, {"$ifNull": ["$votacion.puesto_nombre", {"$ifNull": [
        "$votacion.puesto_texto", {"$cond": [{"$eq": ["$votacion.donde", "otro_municipio"]}, {"$cond": [
            {"$eq": [{"$type": "$votacion.municipio"}, "string"]},
            {"$concat": ["Otro municipio: ", "$votacion.municipio"]}, "Otro municipio"]}, None]}]}]}, "$puesto_votacion"]},
    "mesa": {"$cond": [_ES_VOTACION, {"$ifNull": ["$votacion.mesa_texto", {"$toString": "$votacion.mesa"}]}, "$mesa"]},
}}


def filtro_estado_votacion(estado: str, vigente: str | None) -> dict:
    """Filtro por el estado efectivo de la votación. Una votación de otra elección (o de elección desconocida) cuenta
    como «por_confirmar», sin reescribir nada. Quien no tiene votación no entra en ninguno."""
    if estado == "verificado":
        return {"votacion.eleccion": vigente, "votacion.estado": "verificado"}
    if estado == "sin_verificar":
        return {"votacion.eleccion": vigente, "votacion.estado": {"$nin": ["verificado", "por_confirmar"]}}
    if estado == "por_confirmar":
        return {"votacion": {"$type": "object"},
                "$nor": [{"votacion.eleccion": vigente, "votacion.estado": {"$ne": "por_confirmar"}}]}
    raise ValueError(f"Estado de votación desconocido: {estado}")


def estado_votacion_efectivo(v: Any, vigente: str | None) -> str | None:
    """Gemelo de `filtro_estado_votacion`. None si no hay votación."""
    if not isinstance(v, dict):
        return None
    if v.get("eleccion") != vigente or v.get("estado") == "por_confirmar":
        return "por_confirmar"
    return "verificado" if v.get("estado") == "verificado" else "sin_verificar"


# ───────────────────────────── Abordaje y autorización ─────────────────────────────

def _texto_ts(v: Any) -> str:
    return v.isoformat() if isinstance(v, datetime) else str(v or "")


def _orden_id(v: Any) -> tuple:
    return (0, v) if isinstance(v, int) and not isinstance(v, bool) else (1, str(v or ""))


def _cronologico(eventos: Iterable[dict] | None) -> list[dict]:
    return sorted(eventos or [], key=lambda e: (_texto_ts(e.get("ts")), _orden_id(e.get("_id"))))


def _efectivo(a: dict) -> bool:
    return a["efectivo"] if isinstance(a.get("efectivo"), bool) else a.get("resultado") in EFECTIVOS


def resumen_abordaje(acercamientos: Iterable[dict] | None, consentimiento: str | None = None) -> dict | None:
    """`abordaje` de una persona a partir de sus acercamientos no anulados (los anulados se ignoran igual).

    * `intentos_sin_exito`: «no contestó» y «buzón» seguidos desde el último acercamiento efectivo.
    * `ultimo_*`, `proximo` y `proximo_franja`: del último acercamiento, por (ts, _id).
    * `estado`: «no_contactar» si lo pidió (resultado no_contactar, salvo con alcance «numero») o si no autorizó
      (`consentimiento == "no"`); si no, «contactado» con algún efectivo; si no, «intentado».
    Sin acercamientos devuelve None («sin_abordar»), salvo que no haya autorizado."""
    vivos = [a for a in _cronologico(acercamientos) if not a.get("anulado")]
    pidio_no = any(a.get("resultado") == "no_contactar" and a.get("alcance") != "numero" for a in vivos)
    if not vivos:
        if consentimiento != "no":
            return None
        return {"n": 0, "efectivos": 0, "intentos_sin_exito": 0, "ultimo_ts": None, "ultimo_fecha": None,
                "ultimo_canal": None, "ultimo_resultado": None, "ultimo_uid": None, "ultimo_usuario": None,
                "proximo": None, "proximo_franja": None, "estado": "no_contactar"}
    efectivos = sin_exito = 0
    for a in vivos:
        if _efectivo(a):
            efectivos += 1
            sin_exito = 0
        elif a.get("resultado") in SIN_EXITO:
            sin_exito += 1
    u = vivos[-1]
    estado = "no_contactar" if (pidio_no or consentimiento == "no") else ("contactado" if efectivos else "intentado")
    return {"n": len(vivos), "efectivos": efectivos, "intentos_sin_exito": sin_exito, "ultimo_ts": u.get("ts"),
            "ultimo_fecha": u.get("fecha") or fecha_local(u.get("ts")), "ultimo_canal": u.get("canal"),
            "ultimo_resultado": u.get("resultado"), "ultimo_uid": u.get("uid"), "ultimo_usuario": u.get("usuario"),
            "proximo": u.get("proximo"), "proximo_franja": u.get("proximo_franja"), "estado": estado}


def canales_de(evento: dict) -> list[str]:
    """Canales que vale un evento «si»: los explícitos (vacío = ninguno) más los implícitos (llamada, WhatsApp y SMS)
    si lleva `canales_implicitos`. En el orden del catálogo."""
    pedidos = set(evento.get("canales") or [])
    if evento.get("canales_implicitos") is True:
        pedidos |= set(CANALES_IMPLICITOS)
    return [c for c in CANALES_AUTORIZACION if c in pedidos]


def _autoriza_sensibles(e: dict) -> bool:
    return e.get("medio") in ("escrito", "formulario") or bool(e.get("evidencia"))


def consentimiento_vigente(eventos: Iterable[dict] | None) -> dict:
    """Campos derivados de la autorización a partir de los eventos de `autorizaciones` (manda el último por (ts, _id)).

    * `consentimiento`: si; no (por «no» o «revocada»); pendiente (sin eventos o por corrección de A).
    * `consentimiento_fecha`: la fecha declarada o la fecha local del evento.
    * `consentimiento_canales`: `canales_de(evento)`; vacío si no es «si».
    * `contacto_habilitado`: «si» con un medio distinto de `declarado_planilla`, o confirmado por A.
    * `sensibles_autorizados`: categorías de los «si» seguidos al final con medio escrito o formulario, o con evidencia.
    * `mayor_declarado`: algún «si» con `mayor_declarado`. `autorizacion_ultima`: {id, estado} del último."""
    ev = _cronologico(eventos)
    out = {"consentimiento": "pendiente", "consentimiento_fecha": None, "consentimiento_medio": None,
           "consentimiento_canales": [], "contacto_habilitado": False, "sensibles_autorizados": [],
           "mayor_declarado": any(e.get("estado") == "si" and e.get("mayor_declarado") is True for e in ev),
           "autorizacion_ultima": None}
    if not ev:
        return out
    u = ev[-1]
    out["autorizacion_ultima"] = {"id": u.get("_id"), "estado": u.get("estado")}
    # Un evento migrado lleva la fecha que tenía la ficha (o ninguna): la de la migración no es la de la autorización
    fecha = u.get("fecha_declarada") or (None if u.get("medio") == "migrado" else fecha_local(u.get("ts")))
    if u.get("estado") == "si":
        seguidos = []
        for e in reversed(ev):
            if e.get("estado") != "si":
                break
            seguidos.append(e)
        categorias = {c for e in seguidos if _autoriza_sensibles(e) for c in e.get("sensibles") or []}
        out.update(consentimiento="si", consentimiento_fecha=fecha, consentimiento_medio=u.get("medio"),
                   consentimiento_canales=canales_de(u),
                   # `habilita: False`: un evento de fusión entre fichas que no estaban habilitadas no las habilita
                   contacto_habilitado=(u.get("medio") not in (None, "declarado_planilla")
                                        or u.get("confirmada_por") is not None) and u.get("habilita") is not False,
                   sensibles_autorizados=[c for c in SENSIBLES if c in categorias])
    elif u.get("estado") in ("no", "revocada"):
        out.update(consentimiento="no", consentimiento_fecha=fecha, consentimiento_medio=u.get("medio"))
    return out


# ───────────────────────────── Avance, faltantes y nombre ─────────────────────────────

def _lleno(v: Any) -> bool:
    if isinstance(v, str):
        return bool(v.strip())
    return v not in (None, [], {})


def tiene_dato(p: dict, clave: str) -> bool:
    """¿La ficha tiene el dato de esta clave canónica (CAMPOS_AVANCE)? Lectura tolerante: una ficha sin `votacion` o sin
    `telefonos` usa los campos heredados."""
    if clave == "telefono":
        return bool(usables(telefonos_de(p)))
    if clave == "edad":
        return _edad(p.get("edad")) is not None or fecha_valida(p.get("fecha_nacimiento")) is not None
    if clave == "lugar":
        return p.get("lugar_id") is not None
    if clave == "ubicacion":
        return p.get("punto") is not None or (_numero(p.get("lat")) is not None and _numero(p.get("lon")) is not None)
    if clave in ("puesto", "mesa"):
        v = p.get("votacion")
        if not isinstance(v, dict):
            return _lleno(p.get("puesto_votacion" if clave == "puesto" else "mesa"))
        if clave == "mesa":
            return v.get("mesa") is not None
        return v.get("puesto_id") is not None or _lleno(v.get("puesto_texto")) \
            or v.get("donde") in ("otro_municipio", "no_inscrito")
    if clave == "autorizacion":
        return p.get("consentimiento") in ("si", "no")
    if clave == "personas_hogar":
        return p.get("personas_hogar") not in (None, "", 0)
    if clave in ("jefe_hogar", "estrato"):
        return p.get(clave) is not None
    return _lleno(p.get(clave))


def completados(antes: dict | None, despues: dict | None) -> list[str]:
    """Claves canónicas de CAMPOS_AVANCE que pasaron de vacías a tener dato (puesto_id o puesto_texto → puesto,
    lugar_id → lugar, fecha_nacimiento o edad → edad, un número usable donde no había → telefono…). `antes` y
    `despues` son la ficha (o el mismo subconjunto de campos) antes y después de escribir; `antes=None` es un alta."""
    a, d = antes or {}, despues or {}
    return [k for k in CAMPOS_AVANCE if not tiene_dato(a, k) and tiene_dato(d, k)]


def _no_disponible_vigente(marca: Any, hoy: date, dias: int) -> bool:
    if not isinstance(marca, dict):
        return False
    f = _fecha_de(fecha_local(marca.get("ts")) or marca.get("ts"))
    return f is not None and (hoy - f).days < dias


def faltan(p: dict, hoy: date | None = None, dias: int = AJUSTES_POR_DEFECTO["dias_reintento_dato"]) -> list[str]:
    """CAMPOS_FALTAN sin dato, salvo los marcados «No lo tiene / No sabe» hace menos de `dias`
    (`ajustes.dias_reintento_dato`)."""
    hoy = hoy or hoy_local()
    nd = p.get("no_disponible") or {}
    return [k for k in CAMPOS_FALTAN if not tiene_dato(p, k) and not _no_disponible_vigente(nd.get(k), hoy, dias)]


def claves_foneticas(nombre: Any) -> list[str]:
    """`nombre_fon`: clave fonética de cada palabra del nombre que identifica (YESICA y JESSICA dan la misma)."""
    return list(dict.fromkeys(c for t in tx.tokens_nombre(nombre) if (c := tx.fonetico(t))))


# ───────────────────────────── Lo que escribe el código viejo (1.12) ─────────────────────────────

def _tel_legado(campo: str) -> dict:
    """Elemento de `telefonos` (expresión) para el número que el código viejo dejó en `telefono` o `telefono2`."""
    return {"numero": f"${campo}", "tipo": {"$cond": [
        {"$regexMatch": {"input": {"$toString": f"${campo}"}, "regex": "^3[0-9]{9}$"}}, "celular", "fijo"]},
        "fuentes": ["panel"], "primera_vez": None, "ultima_vez": None, "estado": "sin_verificar", "whatsapp": None,
        "no_contactar": False, "agregado_por": None, "estado_por": None, "estado_en": None, "nota": None}


def _falta_en(campo: str, lista: str) -> dict:
    return {"$and": [{"$not": [{"$in": [{"$ifNull": [f"${campo}", None]}, [None, ""]]}]},
                     {"$not": [{"$in": [f"${campo}", {"$map": {"input": lista, "as": "t", "in": "$$t.numero"}}]}]}]}


# Etapa $set que, antes de tocar los teléfonos, mete en la lista el `telefono` (posición 0) y el `telefono2` (posición 1)
# que el código viejo haya escrito directamente sin pasar por `telefonos`: así derivarlos después no los pierde
ETAPA_RECONCILIAR_TELEFONOS = {"$set": {"telefonos": {"$let": {"vars": {"a": TELS_ACTUALES}, "in": {"$let": {
    "vars": {"b": {"$concatArrays": [{"$cond": [_falta_en("telefono", "$$a"), [_tel_legado("telefono")], []]}, "$$a"]}},
    "in": {"$cond": [_falta_en("telefono2", "$$b"), {"$concatArrays": [
        {"$slice": ["$$b", 1]}, [_tel_legado("telefono2")], {"$slice": ["$$b", 1, 100000]}]}, "$$b"]}}}}}}}


def reconciliar_telefonos(p: dict) -> list[dict]:
    """Gemelo de ETAPA_RECONCILIAR_TELEFONOS."""
    lista = telefonos_de(p)
    for pos, campo in ((0, "telefono"), (1, "telefono2")):
        n = p.get(campo)
        if n not in (None, "") and n not in [t.get("numero") for t in lista]:
            lista.insert(min(pos, len(lista)), telefono_nuevo(n, "panel"))
    return lista


# ───────────────────────────── Procedencia (1.5) ─────────────────────────────

PROTEGIDAS = frozenset({"panel", "reunion", "manual"})  # lo que viene de una persona nunca lo reemplaza una importación
CLAVES_VOTACION = ("puesto_id", "puesto_texto", "mesa", "mesa_texto", "donde", "municipio")  # lo que distingue un dato


def vacio(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip()) or v == [] or v == {}


def comparable(campo: str, v: Any) -> Any:
    """Lo que se compara de un valor: de la votación, solo puesto, mesa y lugar (no quién ni cuándo la registró)."""
    if campo == "votacion":
        return {k: v.get(k) for k in CLAVES_VOTACION} if isinstance(v, dict) else None
    return v


def expr_comparable(campo: str) -> Any:
    """Gemelo de `comparable` sobre el valor guardado (expresión)."""
    if campo == "votacion":
        return {"$cond": [{"$eq": [{"$type": "$votacion"}, "object"]},
                          {k: {"$ifNull": [f"$votacion.{k}", None]} for k in CLAVES_VOTACION}, None]}
    return {"$ifNull": [f"${campo}", None]}


def expr_vacio(campo: str) -> dict:
    """¿El campo guardado está vacío? La votación cuenta como vacía solo si tampoco hay puesto ni mesa heredados."""
    if campo == "votacion":
        return {"$and": [{"$ne": [{"$type": "$votacion"}, "object"]},
                         {"$in": [{"$ifNull": ["$puesto_votacion", None]}, [None, ""]]},
                         {"$in": [{"$ifNull": ["$mesa", None]}, [None, ""]]}]}
    return {"$in": [{"$ifNull": [f"${campo}", None]}, [None, "", [], {}]]}


def valor_campo(p: dict, campo: str) -> Any:
    """Valor de un campo con procedencia, con lectura tolerante de la votación heredada."""
    if campo == "votacion" and not isinstance(p.get("votacion"), dict):
        return None if vacio(p.get("puesto_votacion")) and vacio(p.get("mesa")) else \
            {"puesto_texto": p.get("puesto_votacion"), "mesa_texto": p.get("mesa")}
    return p.get(campo)


def fuente_de(p: dict, campo: str) -> str | None:
    """Fuente del valor actual: la de `procedencia`; un valor sin procedencia cuenta como del panel."""
    if vacio(valor_campo(p, campo)):
        return None
    return ((p.get("procedencia") or {}).get(campo) or {}).get("fuente") or "panel"


def puede_reemplazar(guardada: str | None, entrante: str) -> bool:
    """¿Una fuente entrante reemplaza el valor de la guardada? Solo con más confianza y nunca lo que puso una persona."""
    return guardada is not None and guardada not in PROTEGIDAS and CONFIANZA.get(guardada, 4) < CONFIANZA.get(entrante, 0)


# ───────────────────────────── Votación desde un texto ─────────────────────────────

def armar_votacion(puesto: Any, mesa: Any, puestos: Iterable[dict], *, fuente: str, eleccion: str | None,
                   estado: str = "sin_verificar", municipio: Any = None, registrado_por: Any = None,
                   registrado_en: str | None = None, conservar_texto: bool = False) -> dict | None:
    """Subdocumento `votacion` a partir de lo escrito (planilla, base con cédula o fichas viejas).

    El puesto se reconoce en el catálogo (`reconocer_puesto`); si no se reconoce o es ambiguo queda en `puesto_texto`
    (con `conservar_texto`, siempre). La mesa debe estar entre 1 y las mesas del puesto (99 sin catálogo): fuera de
    rango no se guarda como número y el estado queda «por_confirmar», igual que con un puesto ambiguo. `mesa_texto`
    guarda el texto original. None si no hay nada."""
    texto = str(puesto).strip() if not vacio(puesto) else None
    muni = tx.limpiar(municipio) if not vacio(municipio) else ""
    otro = bool(muni) and not muni.startswith("YONDO") and "CASABE" not in muni
    if texto is None and vacio(mesa) and not otro:
        return None
    puestos = list(puestos)
    pid, ambiguo = reconocer_puesto(texto, puestos) if texto else (None, False)
    p = next((x for x in puestos if x.get("_id", x.get("id")) == pid), None) if pid is not None else None
    n = normalizar_mesa(mesa)
    tope = (p or {}).get("mesas") or MESAS_SIN_CATALOGO
    fuera = n is not None and not 1 <= n <= tope
    if isinstance(mesa, str):
        mesa_texto = mesa.strip() or None
    else:
        mesa_texto = None if (vacio(mesa) or (n is not None and not fuera)) else str(mesa)
    return {"puesto_id": pid, "puesto_nombre": (p or {}).get("nombre"),
            "puesto_texto": texto if (pid is None or conservar_texto) else None,
            "mesa": None if fuera else n, "mesa_texto": mesa_texto,
            "donde": "otro_municipio" if otro else "yondo", "municipio": str(municipio).strip() if otro else None,
            "eleccion": eleccion, "estado": "por_confirmar" if (ambiguo or fuera) else estado, "fuente": fuente,
            "registrado_por": registrado_por, "registrado_en": registrado_en}


# ───────────────────────────── Solicitudes de los titulares ─────────────────────────────

TIPOS_SOLICITUD = {"consulta": "Consulta", "correccion": "Corrección", "supresion": "Supresión",
                   "revocatoria": "Revocatoria", "otro": "Otro", "registro": "Pedido de registro"}
# Días hábiles de plazo (Ley 1581, arts. 14 y 15): 10 la consulta y 15 los reclamos; el pedido de registro de un
# consultor no tiene plazo legal
PLAZOS_SOLICITUD = {"consulta": 10, "correccion": 15, "supresion": 15, "revocatoria": 15, "otro": 15, "registro": None}
# Las que dejan la ficha con «reclamo en trámite» (sale de las colas mientras se resuelve)
RECLAMOS = ("correccion", "supresion", "revocatoria")
ESTADOS_SOLICITUD = {"pendiente": "Pendiente", "en_tramite": "En trámite", "resuelta": "Resuelta",
                     "rechazada": "Rechazada"}
ABIERTAS = ("pendiente", "en_tramite")


def sumar_dias_habiles(desde: date, dias: int) -> date:
    """`desde` más `dias` días hábiles (de lunes a viernes; los festivos no se descuentan: el plazo real es igual o
    más largo)."""
    d, n = desde, 0
    while n < dias:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return d


# ───────────────────────────── Copia para el navegador ─────────────────────────────

# web/js/modelo.js trae una copia exacta (tests/test_contrato.py las compara): las etiquetas son las mismas
CATALOGOS_WEB = {
    "SEXOS": SEXOS, "TIPOS_DOCUMENTO": TIPOS_DOCUMENTO, "NIVELES": NIVELES, "ESTADOS_CIVILES": ESTADOS_CIVILES,
    "SITUACIONES_LABORALES": SITUACIONES_LABORALES, "TENENCIAS": TENENCIAS, "REGIMENES_SALUD": REGIMENES_SALUD,
    "RANGOS_EDAD": RANGOS_EDAD, "SENSIBLES": SENSIBLES, "NOMBRES_ROL": NOMBRES_ROL,
    "ESTADOS_AUTORIZACION": ESTADOS_AUTORIZACION, "MEDIOS_AUTORIZACION": MEDIOS_AUTORIZACION,
    "MEDIOS_POR_ROL": MEDIOS_POR_ROL, "CANALES_AUTORIZACION": CANALES_AUTORIZACION,
    "CANALES_IMPLICITOS": list(CANALES_IMPLICITOS), "CANALES": CANALES, "RESULTADOS": RESULTADOS,
    "SIN_EXITO": list(SIN_EXITO), "FRANJAS": FRANJAS, "ESTADOS_ABORDAJE": ESTADOS_ABORDAJE, "SITUACIONES": SITUACIONES,
    "MOTIVOS_ACTUALIZACION": MOTIVOS_ACTUALIZACION, "CAMPOS_NO_DISPONIBLE": list(CAMPOS_NO_DISPONIBLE),
    "MOTIVOS_NO_DISPONIBLE": MOTIVOS_NO_DISPONIBLE, "ESTADOS_TELEFONO": ESTADOS_TELEFONO, "USABLES": sorted(USABLES),
    "TIPOS_TELEFONO": TIPOS_TELEFONO, "ESTADOS_VOTACION": ESTADOS_VOTACION, "DONDE_VOTA": DONDE_VOTA,
    "ETIQUETAS_CAMPOS": ETIQUETAS_CAMPOS, "CAMPOS_FALTAN": list(CAMPOS_FALTAN),
}
