"""Herramientas del asistente sobre personas: buscar, ver la ficha y las parecidas (lectura), y crear, editar, agregar
una nota, registrar un acercamiento o una autorización, ubicar y agregar un teléfono (escritura, con aprobación).

Por qué está hecho así:

* Todo pasa por `ctx.api` (las mismas rutas que usa la interfaz, con la sesión del usuario): los permisos, el alcance
  de P y C, el presupuesto diario, las lecturas, la proyección por rol, `exigir_tratable`, la idempotencia y la
  auditoría son los del panel. Las comprobaciones previas adelantan, con un mensaje claro para el modelo, lo que la
  API rechazaría después de que la persona aprobara la tarjeta (o lo que la interfaz no ofrecería, como una reunión
  ajena), y usan las mismas reglas del panel cuando las hay.
* Lo que llega al modelo pasa por `minimizar` (sin datos sensibles, listas, cédulas ni teléfonos completos, correos ni
  coordenadas) y cada persona servida va en `Resultado.personas` (la conversación se borra si alguna se suprime). Los
  errores de la API también se limpian (`_seguro`): un 409 puede traer la cédula, el teléfono o el nombre de otra
  persona.
* Escrituras: `confirmar` lee la ficha (nombre, autorización y los valores de antes) y arma la tarjeta, sin escribir
  nada. `ejecutar` escribe una sola vez: manda la `Idempotency-Key` del `tool_use` (las rutas POST devuelven la
  respuesta guardada si se repite) y, en las que no la tienen (PATCH, PUT, DELETE), vuelve a leer la ficha y no
  escribe si ya quedó como se pidió. Para saber si alguien cambió la ficha entre la tarjeta y la aprobación, la
  tarjeta deja en la entrada huellas (HMAC) de los valores que mostró, nunca los valores: la entrada pendiente se
  guarda con la conversación.
* De quien no autorizó el tratamiento el asistente no escribe nada salvo su autorización: sus datos no se le pasan al
  modelo, y escribirlos sería tratarlos a través de él. Se hace en la ficha del panel.
* Las entradas vienen de un LLM: modelos pydantic con los topes y los valores válidos de la API, `extra="forbid"` (una
  clave mal escrita es un error visible, no una búsqueda sin filtros que gasta el presupuesto) y validaciones cruzadas
  con mensajes que dicen cómo corregir.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
from dataclasses import dataclass
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema
from starlette.concurrency import run_in_threadpool

from ... import acceso, modelo
from ... import db as bd
from ...pipeline import texto as tx
from .. import minimizar
from .base import Confirmacion, Contexto, ErrorHerramienta, Herramienta, Resultado

MAX_ID = 2_000_000_000
TIPOS_DOCUMENTO = tuple(modelo.TIPOS_DOCUMENTO)
ORDENES = ("nombre", "completitud", "-completitud", "reciente", "contacto", "por_llamar", "abordaje_reciente", "lugar")
FALTAN = ("cedula", "telefono", "sexo", "edad", "lugar", "puesto", "mesa", "direccion", "puesto_mesa")
CANALES_TELEFONO = ("llamada", "whatsapp", "sms")
# Medios con que se registra una autorización desde el asistente (los del panel, la migración y la fusión no)
MEDIOS = ("escrito", "verbal_presencial", "verbal_telefono", "mensaje", "formulario")
TOPE_BUSQUEDA = 12  # GET /api/buscar: 12 filas (10 por nombre y 3 por número para el consultor)


# ───────────────────────────── Tipos y validación de la entrada ─────────────────────────────

def _no_booleano(v: Any) -> Any:
    """`True` es un `int` en Python y pydantic lo aceptaría como el id 1: con un id del modelo, mejor un error."""
    if isinstance(v, bool):
        raise ValueError("Debe ser un número entero (un id), no verdadero o falso")
    return v


# Los topes antes del validador: así el esquema dice «minimum/maximum» (después saldrían como «ge/le», que la API no
# entiende)
Id = Annotated[int, Field(ge=1, le=MAX_ID), BeforeValidator(_no_booleano)]


class _Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _fecha(v: str | None, *, pasada: bool = False, futura: bool = False) -> str | None:
    """AAAA-MM-DD de una fecha que exista; `pasada`: no después de hoy (nacimiento); `futura`: hoy o después."""
    if v is None:
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        raise ValueError("Use el formato AAAA-MM-DD")
    try:
        d = date.fromisoformat(v)
    except ValueError:
        raise ValueError(f"Fecha inexistente: {v}") from None
    hoy = modelo.hoy_local()
    if d.year < 1900:
        raise ValueError("Fecha demasiado antigua")
    if pasada and d > hoy:
        raise ValueError("La fecha no puede ser posterior a hoy")
    if futura and d < hoy:
        raise ValueError(f"La fecha no puede ser anterior a hoy ({hoy.isoformat()})")
    return v


def _documento(numero: str | None, tipo: str | None) -> str | None:
    """Como `validar_documento` de la API: CC y TI de 5 a 11 dígitos; los demás, de 4 a 15 letras o números. Más
    estricto en una cosa: una CC con letras es un error (la API se quedaría solo con los dígitos, y un pasaporte
    dictado sin su tipo perdería las letras sin que nadie lo note)."""
    if numero in (None, ""):
        return None
    if tipo in (None, "CC", "TI"):
        if re.search(r"[A-Za-z]", str(numero)):
            raise ValueError("La cédula solo lleva números; si es otro documento, indique tipo_documento")
        c = tx.cedula(numero)
        if not c:
            raise ValueError("La cédula debe tener entre 5 y 11 dígitos")
        return c
    s = re.sub(r"[\s.-]", "", str(numero)).upper()
    if not re.fullmatch(r"[A-Z0-9]{4,15}", s):
        raise ValueError("El documento debe tener de 4 a 15 letras o números")
    return s


def _un_telefono(v: str) -> str:
    nums = tx.telefonos(v)
    if len(nums) != 1:
        raise ValueError("Escriba un solo número: celular de 10 dígitos (empieza por 3) o fijo de 7 o 10 dígitos")
    return nums[0]


def _nombre(v: str | None) -> str | None:
    if v is not None and len(tx.nombre_norm(v).replace(" ", "")) < 3:
        raise ValueError("El nombre debe tener al menos 3 letras")
    return v


def _sin_repetidos(v: list) -> list:
    return list(dict.fromkeys(v or []))


# ───────────────────────────── Esquema para la Messages API ─────────────────────────────

def _aplanar(s: dict) -> dict:
    """El JSON Schema de pydantic sin `$defs` ni `$ref` (los modelos anidados quedan en línea), sin `title` y con los
    opcionales (`X | None = None`) como `X`: el modelo simplemente omite la clave. Un esquema autocontenido y corto
    sirve igual en cualquier versión de la API y gasta menos contexto."""
    defs = s.get("$defs", {})

    def resolver(x: Any) -> Any:
        if isinstance(x, list):
            return [resolver(v) for v in x]
        if not isinstance(x, dict):
            return x
        if "$ref" in x:
            nombre = str(x["$ref"]).rsplit("/", 1)[-1]
            return {**resolver(defs[nombre]), **resolver({k: v for k, v in x.items() if k != "$ref"})}
        # En `properties` las claves son nombres de campos (uno podría llamarse «title»): no se filtran
        out = {k: ({p: resolver(sub) for p, sub in v.items()} if k == "properties" and isinstance(v, dict)
                   else resolver(v)) for k, v in x.items() if k not in ("$defs", "title")}
        if "anyOf" in out and "default" in out and out["default"] is None:
            ramas = [r for r in out["anyOf"] if r != {"type": "null"}]
            if len(ramas) == 1:
                resto = {k: v for k, v in out.items() if k not in ("anyOf", "default")}
                out = {**ramas[0], **resto}
        return out

    return resolver(s)


def esquema(m: type[BaseModel]) -> dict:
    s = _aplanar(m.model_json_schema())
    s.setdefault("type", "object")
    s.setdefault("properties", {})
    return s


# ───────────────────────────── API interna y errores ─────────────────────────────

_FUERA_DE_CLAVE = re.compile(r"[^A-Za-z0-9_.:-]")
DETALLE_PERMITIDO = ("campo", "motivo", "campos")
# Valores que un 409 «cambiada» puede traer y que el modelo nunca recibe
OCULTOS = {"correo", "fecha_nacimiento", "lider", "sensibles", "regimen_salud", "consentimiento",
           "consentimiento_fecha", "observaciones"}


def _clave(ctx: Contexto) -> str | None:
    """La Idempotency-Key de la escritura: la misma para el mismo `tool_use`. Sin `tool_use_id` no se manda ninguna:
    una clave compartida devolvería la respuesta guardada de otra escritura en vez de hacer esta."""
    if not ctx.tool_use_id:
        return None
    return _FUERA_DE_CLAVE.sub("_", f"agente.{ctx.conversacion_id}.{ctx.tool_use_id}")[:100]


def _valor_seguro(campo: str, v: Any) -> Any:
    if v in (None, ""):
        return None
    if campo in ("cedula", "cedulas_anteriores"):
        return acceso.enmascarar_cedula(v)
    if campo in ("telefono", "telefono2"):
        return acceso.enmascarar_telefono(v)
    if campo in OCULTOS:
        return "(oculto)"
    if isinstance(v, (bool, int, float)):
        return v
    if isinstance(v, str):
        return minimizar.texto_libre(v, 120)
    return "(oculto)"


def _seguro(e: ErrorHerramienta) -> ErrorHerramienta:
    """El error de la API sin datos personales que el modelo no recibiría por las lecturas: el 409 de cédula ocupada
    trae el nombre y el lugar de otra persona; el de «cambiada», los valores completos actuales (con la cédula y los
    teléfonos para A y K); el de parecidas, filas sin minimizar."""
    d = e.detalle if isinstance(e.detalle, dict) else None
    mensaje, codigo, detalle = e.mensaje, e.codigo, None
    if codigo == "cedula_ocupada":
        otro = d.get("id") if d else None
        otro = otro if isinstance(otro, int) and not isinstance(otro, bool) else None
        mensaje = ("La cédula ya pertenece a otra ficha activa" + (f" (#{otro})" if otro else "")
                   + ": revise si es la misma persona antes de seguir.")
        detalle = {"id": otro} if otro else None
    elif codigo == "cambiada" and d:
        mensaje = MENSAJE_CAMBIADA
        campos = d.get("campos") if isinstance(d.get("campos"), list) else []
        valores = d.get("valores_actuales") if isinstance(d.get("valores_actuales"), dict) else {}
        detalle = {"campos": [str(c) for c in campos][:30],
                   "valores_actuales": {str(k): _valor_seguro(str(k), v) for k, v in list(valores.items())[:30]}}
    elif codigo == "parecidas" and d:
        detalle = {"n": len(d["parecidas"]) if isinstance(d.get("parecidas"), list) else 0}
    elif e.estado == 409 and d and isinstance(d.get("id"), int) and "unió" in (mensaje or ""):
        codigo, mensaje, detalle = "unida", f"Esta ficha se unió con la #{d['id']}: use esa.", {"id": d["id"]}
    elif d:
        detalle = {k: d[k] for k in DETALLE_PERMITIDO if isinstance(d.get(k), (str, int, list))} or None
    elif isinstance(e.detalle, list):  # 422 de FastAPI: la entrada era del modelo; basta el mensaje y el lugar
        detalle = [f"{x.get('msg')} en {'.'.join(map(str, x.get('loc') or []))}"
                   for x in e.detalle[:10] if isinstance(x, dict)] or None
    return ErrorHerramienta(mensaje, codigo, estado=e.estado, detalle=detalle, fatal=e.fatal)


async def _pedir(ctx: Contexto, metodo: str, ruta: str, *, params: dict | None = None, cuerpo: Any = None,
                 clave: str | None = None) -> Any:
    try:
        return await ctx.api.pedir(metodo, ruta, params=params, json_=cuerpo, clave=clave)
    except ErrorHerramienta as e:
        raise _seguro(e) from None


async def _ficha(ctx: Contexto, pid: int) -> dict:
    """La ficha del rol (cuenta como lectura: es la misma persona que se va a escribir o a mostrar)."""
    try:
        d = await _pedir(ctx, "GET", f"/api/personas/{int(pid)}")
    except ErrorHerramienta as e:
        if e.estado == 404:
            raise ErrorHerramienta(f"No existe la ficha #{pid} (o se suprimió).", "no_existe", estado=404) from None
        raise
    if not isinstance(d, dict) or "id" not in d:
        raise ErrorHerramienta("La API del panel devolvió una ficha vacía.", "error")
    return d


async def _sensibles(ctx: Contexto) -> minimizar.Sensibles:
    return await run_in_threadpool(minimizar.sensibles_de, ctx.db)


def _huella(clave: bytes, campo: str, v: Any) -> str:
    """Huella de un valor de la ficha: HMAC con una clave del servidor (la de las huellas de supresión, con otro
    prefijo), así no se puede deducir una cédula probando todas. Basta para saber si el valor cambió."""
    texto = json.dumps(None if _vacio(v) else v, ensure_ascii=False, sort_keys=True, default=str)
    return hmac.new(clave, f"agente.base|{campo}|{texto}".encode(), hashlib.sha256).hexdigest()[:24]


async def _clave_huellas(ctx: Contexto) -> bytes:
    return await run_in_threadpool(bd.clave_supresion, ctx.db)


def _huellas_validas(v: dict | None, campos: frozenset[str]) -> dict | None:
    if v is not None and (len(v) > 30 or any(k not in campos or not re.fullmatch(r"[0-9a-f]{24}", str(x))
                                             for k, x in v.items())):
        raise ValueError("huellas no válidas")
    return v


MENSAJE_CAMBIADA = ("Otra persona cambió estos datos después de que se armó la tarjeta: vuelva a leer la ficha y, si "
                    "sigue haciendo falta, proponga el cambio de nuevo.")


def _exigir_sin_cambios(d: dict, huellas: dict | None, campos: list[str], clave: bytes, valor) -> None:
    """409 «cambiada» si alguno de `campos` ya no tiene el valor que mostró la tarjeta (`valor(d, campo)` lo lee)."""
    cambiados = [c for c in campos if huellas and c in huellas and _huella(clave, c, valor(d, c)) != huellas[c]]
    if cambiados:
        raise ErrorHerramienta(MENSAJE_CAMBIADA, "cambiada", estado=409, detalle={
            "campos": cambiados, "valores_actuales": {c: _valor_seguro(c, valor(d, c)) for c in cambiados}})


def _exigir_tratable(d: dict) -> None:
    if d.get("consentimiento") == "no":
        raise ErrorHerramienta(
            "Esta persona no autorizó el tratamiento de sus datos: el asistente no escribe en su ficha. Si ahora "
            "autoriza, regístrelo con registrar_autorizacion; lo demás se hace en la ficha del panel.",
            "no_contactable", estado=409, detalle={"motivo": "no_autorizo"})


def _persona(d: dict) -> str:
    return f"{d.get('nombre') or 'Persona sin nombre'} (#{d.get('id')})"


def _breve(d: dict) -> dict:
    """Lo que el modelo necesita después de una escritura: quién, cómo quedó y los avisos de la operación."""
    f = minimizar.ficha(d)
    return {k: f[k] for k in ("id", "nombre", "consentimiento", "completitud", "faltan", "avisos") if k in f}


def _miles(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _si_no(v: Any) -> str:
    return "Sí" if v is True else "No" if v is False else "Sin dato"


ACCIONES_ESCRITURA = [{"tipo": "recargar"}]


# ───────────────────────────── Catálogos (no son personas: se leen de la base) ─────────────────────────────

def _lugar(db: Any, lid: int) -> dict | None:
    return db.lugares.find_one({"_id": lid}, {"nombre": 1, "tipo": 1, "zona": 1})


def _puesto(db: Any, pid: int) -> dict | None:
    return db.puestos.find_one({"_id": pid}, {"nombre": 1, "codigo": 1, "mesas": 1})


def _etiquetas(db: Any, ids: list[int]) -> dict[int, dict]:
    return {e["_id"]: e for e in db.etiquetas.find({"_id": {"$in": list(ids)}}, {"nombre": 1, "grupo": 1})}


def _reunion(db: Any, rid: int) -> dict | None:
    return db.reuniones.find_one({"_id": rid}, {"titulo": 1, "fecha": 1, "creado_por_uid": 1, "abierta_a_equipo": 1})


async def _reunion_visible(ctx: Contexto, rid: int | None) -> str | None:
    """«Título (fecha)» de una reunión que el rol puede usar (P: las suyas o las abiertas al equipo, como la API)."""
    if rid is None:
        return None
    from ...api.reuniones import _propia_o_abierta  # la regla de la API (aquí: el módulo de la API carga FastAPI)
    x = await run_in_threadpool(_reunion, ctx.db, rid)
    if x is None:
        raise ErrorHerramienta(f"La reunión #{rid} no existe.", "no_existe", estado=404)
    if not _propia_o_abierta(x, ctx.quien):
        raise ErrorHerramienta("Esa reunión no es suya ni está abierta al equipo.", "permiso", estado=403)
    return f"{x.get('titulo')} ({x.get('fecha')}) #{rid}"


async def _nombres_etiquetas(ctx: Contexto, ids: list[int]) -> list[str]:
    """Nombres de las etiquetas para la tarjeta; error si alguna no existe o es sensible (el asistente no registra datos
    sensibles, tampoco como etiqueta)."""
    if not ids:
        return []
    encontradas = await run_in_threadpool(_etiquetas, ctx.db, ids)
    sens = await _sensibles(ctx)
    faltan = [i for i in ids if i not in encontradas]
    if faltan:
        raise ErrorHerramienta(f"No existen las etiquetas {faltan}: consulte los catálogos.", "no_existe", estado=404)
    if any(i in sens.etiquetas for i in ids):
        raise ErrorHerramienta("Esa etiqueta revela un dato sensible: el asistente no la usa. Se marca en el panel.",
                               "permiso", estado=403)
    return [str(encontradas[i].get("nombre")) for i in ids]


# ───────────────────────────── buscar_personas ─────────────────────────────

class FiltrosEntrada(_Entrada):
    """Los filtros de Habitantes (`filtros.Filtros`) que el asistente puede usar, con los valores que acepta la API.
    Fuera: `poligono` e `ids` (para el mapa), `lista`, `lider`, la fuente «cedulas» y `regimen_salud` (revelan datos
    políticos o de salud) y las etiquetas sensibles."""
    zona: Literal["urbana", "rural", "sin"] | None = Field(None, description="urbana, rural o sin (sin zona)")
    lugar_id: int | None = Field(None, ge=0, le=MAX_ID, description="Barrio o vereda (id de buscar_lugar); 0 = sin "
                                                                     "barrio ni vereda reconocidos")
    area_id: Id | None = Field(None, description="Área de trabajo dibujada en el mapa (el planillero, solo las suyas)")
    fuente: Literal["tramites", "reunion", "manual", "planilla"] | None = Field(None, description="De dónde llegó")
    etiqueta: Id | None = Field(None, description="Necesidad, interés o rol (id de catalogos; no las sensibles)")
    con_cedula: bool | None = None
    con_telefono: bool | None = Field(None, description="Con algún teléfono usable")
    precision: Literal["exacta", "aproximada", "ubicada", "sin"] | None = Field(
        None, description="Ubicación: exacta (dirección o punto), aproximada (barrio o vereda), ubicada (cualquiera) o "
                          "sin ubicación")
    reunion_id: Id | None = Field(None, description="Asistentes de esa reunión")
    asistio: bool | None = Field(None, description="Asistió (true) o no (false) a alguna reunión")
    consentimiento: Literal["si", "no", "pendiente", "por_confirmar"] | None = Field(
        None, description="Autorización de datos; por_confirmar = «sí» de planilla sin confirmar")
    tratables: bool | None = Field(None, description="true: sin quienes no autorizaron")
    sexo: Literal["F", "M", "N", "sin"] | None = Field(None, description="F mujer, M hombre, N prefiere no decir, sin")
    edad_min: int | None = Field(None, ge=0, le=130)
    edad_max: int | None = Field(None, ge=0, le=130)
    tipo_documento: Literal[TIPOS_DOCUMENTO] | None = None
    cedula_verificada: bool | None = None
    completitud_max: int | None = Field(None, ge=0, le=100, description="Ficha completa hasta este porcentaje")
    puesto_id: int | None = Field(None, ge=0, le=MAX_ID, description="Puesto de votación (id); 0 = sin puesto")
    con_puesto: bool | None = None
    con_mesa: bool | None = None
    votacion_estado: Literal[tuple(modelo.ESTADOS_VOTACION)] | None = None
    donde: Literal[tuple(modelo.DONDE_VOTA)] | None = Field(None, description="Dónde vota")
    abordado: bool | None = Field(None, description="Con algún acercamiento registrado")
    contactado: bool | None = Field(None, description="Con algún contacto efectivo")
    abordaje_estado: Literal[tuple(modelo.ESTADOS_ABORDAJE)] | None = None
    ultimo_resultado: Literal[tuple(modelo.RESULTADOS)] | None = Field(None, description="Del último acercamiento")
    sin_acercamiento_dias: int | None = Field(None, ge=0, le=3650, description="Sin acercamiento en estos días")
    proximo_vencido: bool | None = Field(None, description="true: con un «volver a llamar» ya vencido")
    canal_autorizado: Literal[tuple(modelo.CANALES_AUTORIZACION)] | None = Field(
        None, description="Autorizó ese canal de contacto")
    situacion: Literal["todas", "vigentes", "no_vigentes", "activa", "fallecida", "no_reside"] | None = Field(
        None, description="vigentes = activas (por defecto la API trae todas)")
    requiere_actualizacion: bool | None = Field(None, description="Con un pedido de actualización pendiente (o sin él)")
    motivo_actualizacion: Literal[tuple(modelo.MOTIVOS_ACTUALIZACION)] | None = Field(
        None, description="Pedido de actualización por este motivo")
    varios_telefonos: bool | None = None
    telefono_estado: Literal[tuple(modelo.ESTADOS_TELEFONO)] | None = Field(None, description="Algún número así")
    estado_civil: Literal[(*modelo.ESTADOS_CIVILES, "sin")] | None = None
    nivel_educativo: Literal[(*modelo.NIVELES, "sin")] | None = None
    situacion_laboral: Literal[(*modelo.SITUACIONES_LABORALES, "sin")] | None = None
    tenencia_vivienda: Literal[(*modelo.TENENCIAS, "sin")] | None = None
    estrato: int | None = Field(None, ge=0, le=6)
    faltan: list[Literal[FALTAN]] = Field(default_factory=list, max_length=len(FALTAN),
                                          description="Datos que le faltan (todos los de la lista); puesto_mesa = "
                                                      "puesto o mesa")
    mios: bool | None = Field(None, description="true: las que usted registró o actualizó")
    creado_por: int | None = Field(None, ge=0, le=MAX_ID, description="Registradas por ese usuario (uid; solo "
                                                                       "administrador y coordinador)")
    actualizado_por: int | None = Field(None, ge=0, le=MAX_ID, description="Actualizadas por ese usuario (uid; solo "
                                                                             "administrador y coordinador)")
    menor: bool | None = Field(None, description="Menores de edad (true) o no (false); solo administrador y "
                                                 "coordinador")

    @field_validator("faltan")
    @classmethod
    def _f(cls, v):
        return _sin_repetidos(v)

    @model_validator(mode="after")
    def _rangos(self):
        if self.edad_min is not None and self.edad_max is not None and self.edad_min > self.edad_max:
            raise ValueError("edad_min no puede ser mayor que edad_max")
        return self


# Banderas que la API lee como 0/1 en los dos sentidos, y las que solo valen con 1
_BANDERAS = ("con_cedula", "con_telefono", "asistio", "cedula_verificada", "con_puesto", "con_mesa", "abordado",
             "contactado", "varios_telefonos", "menor")
_SOLO_SI = ("tratables", "proximo_vencido", "mios")


def params_filtros(f: FiltrosEntrada | None) -> dict[str, Any]:
    """Los filtros como parámetros de `GET /api/personas` (los mismos de `filtros_query`)."""
    if f is None:
        return {}
    out: dict[str, Any] = {}
    for k, v in f.model_dump(exclude_none=True).items():
        if k in _BANDERAS:
            out[k] = 1 if v else 0
        elif k in _SOLO_SI:
            if v:
                out[k] = 1
        elif k == "faltan":
            for campo in v:
                out[f"sin_{campo}"] = 1
        elif k == "requiere_actualizacion":
            out.setdefault(k, "1" if v else "0")
        elif k == "motivo_actualizacion":
            out["requiere_actualizacion"] = v  # un motivo es más preciso que «con pedido»
        else:
            out[k] = v
    return out


class BuscarEntrada(_Entrada):
    q: str | None = Field(None, max_length=120, description="Nombre, cédula o teléfono (o parte); varias palabras se "
                                                            "combinan")
    filtros: FiltrosEntrada | None = Field(None, description="Filtros de Habitantes (no para el consultor)")
    orden: Literal[ORDENES] | None = Field(
        None, description="nombre (A-Z), completitud (más completas), -completitud (más incompletas), reciente "
                          "(actualizadas), contacto (último contacto), por_llamar (más tiempo sin acercamiento), "
                          "abordaje_reciente o lugar")
    pagina: int = Field(1, ge=1, le=10_000)
    por_pagina: int = Field(20, ge=10, le=50)


def _busca_lista(a: BuscarEntrada) -> bool:
    return bool(params_filtros(a.filtros)) or a.orden is not None or a.pagina > 1 or "por_pagina" in \
        a.model_fields_set or not a.q


def _resumen_conteo(n: int, pagina: int | None = None, paginas: int | None = None) -> str:
    base = "Sin resultados" if n == 0 else "1 persona" if n == 1 else f"{_miles(n)} personas"
    return f"{base} · página {pagina} de {paginas}" if n and paginas and paginas > 1 else base


async def _buscar(ctx: Contexto, a: BuscarEntrada) -> Resultado:
    quien = ctx.quien
    if a.filtros is not None and a.filtros.etiqueta is not None:
        if a.filtros.etiqueta in (await _sensibles(ctx)).etiquetas:
            raise ErrorHerramienta("Esa etiqueta revela un dato sensible: el asistente no filtra por ella.", "permiso",
                                   estado=403)
    if _busca_lista(a):
        if not quien.puede("personas.listar"):
            raise ErrorHerramienta(
                "Su rol no lista ni filtra la base: busque por nombre (3 letras o más) o por el número completo de 10 "
                "dígitos, o trabaje su cola en Mi trabajo.", "permiso", estado=403)
        params = {"q": a.q, **params_filtros(a.filtros), "orden": a.orden or "nombre", "pagina": a.pagina,
                  "por_pagina": a.por_pagina}
        d = await _pedir(ctx, "GET", "/api/personas", params=params)
        d = d if isinstance(d, dict) else {}
        fs = minimizar.filas(d.get("filas") or [])
        total, pp = int(d.get("total") or 0), int(d.get("por_pagina") or a.por_pagina)
        paginas = max(1, math.ceil(total / pp)) if pp else 1
        contenido = {"tipo": "lista", "total": total, "pagina": d.get("pagina", a.pagina), "por_pagina": pp,
                     "paginas": paginas, "filas": fs}
        if not quien.administra:
            contenido["alcance"] = "Solo personas de su zona asignada (si tiene una)."
        return Resultado(contenido, _resumen_conteo(total, contenido["pagina"], paginas), personas=minimizar.ids_de(fs))
    d = await _pedir(ctx, "GET", "/api/buscar", params={"q": a.q})
    fs = minimizar.filas(d if isinstance(d, list) else [])
    contenido = {"tipo": "busqueda_rapida", "total": len(fs), "pagina": 1, "filas": fs}
    consultor = not quien.administra and quien.rol == "consultor"
    digitos = re.sub(r"\D", "", a.q or "")
    tope = (3 if digitos else 10) if consultor else TOPE_BUSQUEDA
    if len(fs) >= tope:
        contenido["aviso"] = (f"Solo se muestran las {tope} coincidencias más cercanas: puede haber más. Afine la "
                              "búsqueda" + ("." if consultor else
                                            " o use filtros y orden para contarlas y recorrerlas."))
    elif not fs and consultor and not digitos and len(re.sub(r"[^A-Za-z]", "", tx.limpiar(a.q))) < 3:
        contenido["aviso"] = "El consultor busca con 3 letras o más del nombre, o con el número completo de 10 dígitos."
    elif not fs and len((a.q or "").strip()) < 2:
        contenido["aviso"] = "Escriba al menos 2 caracteres."
    return Resultado(contenido, _resumen_conteo(len(fs)), personas=minimizar.ids_de(fs))


BUSCAR = Herramienta(
    nombre="buscar_personas",
    descripcion=(
        "Busca habitantes en la base. Úsala para encontrar a una persona por nombre, cédula o teléfono, o para listar "
        "y contar personas con filtros (barrio o vereda, autorización, abordaje, datos que faltan, edad, votación…). "
        "No la uses para ver el detalle de una persona (ver_persona) ni para indicadores generales del tablero.\n"
        "- Solo `q`: búsqueda rápida en toda la base; hasta 12 coincidencias, las más parecidas primero (el "
        "consultor: hasta 10 por nombre de 3 letras o más, o 3 por un número completo de 10 dígitos; no usa filtros).\n"
        "- Con `filtros`, `orden`, `pagina` o `por_pagina` (administrador, coordinador y planillero): lista paginada "
        "con el `total`; el planillero solo ve su zona asignada.\n"
        "Devuelve {tipo, total, pagina, filas}. Cada fila trae id, nombre, lugar, autorización, abordaje, completitud "
        "y lo que le falta; cédula y teléfono enmascarados («···123», «···2233»): no intentes reconstruirlos. De quien "
        "no autorizó solo sale que no autorizó. `por_pagina` de 10 a 50. Cada persona mostrada cuenta en el tope "
        "diario de consultas del planillero y del consultor: pide solo lo necesario y, para saber cuántas son, usa el "
        "total de la primera página en vez de recorrerlas."),
    entrada=BuscarEntrada, tipo="lectura", permisos=("personas.buscar",), etiqueta="Buscando habitantes",
    ejecutar=_buscar, esquema=esquema(BuscarEntrada))


# ───────────────────────────── ver_persona ─────────────────────────────

class VerEntrada(_Entrada):
    persona_id: Id = Field(..., description="Id de la persona (de buscar_personas o del contexto del panel)")


async def _ver(ctx: Contexto, a: VerEntrada) -> Resultado:
    d = await _ficha(ctx, a.persona_id)
    f = minimizar.ficha(d, await _sensibles(ctx))
    resumen = f"#{f.get('id')}: no autorizó" if f.get("consentimiento") == "no" else _persona(f)
    return Resultado(f, resumen, personas={a.persona_id} | minimizar.ids_de([f]))


VER = Herramienta(
    nombre="ver_persona",
    descripcion=(
        "Abre la ficha de una persona por su id. Úsala cuando necesites su detalle: autorización y canales, abordaje y "
        "últimos acercamientos, notas recientes, votación, lo que le falta y qué campos se pueden editar. Devuelve la "
        "ficha reducida: sin datos sensibles ni listas, con la cédula enmascarada y cada teléfono con su estado, su "
        "número enmascarado y su `indice` (el que pide registrar_acercamiento). De quien no autorizó solo sale que no "
        "autorizó. Cuenta en el tope diario del planillero y del consultor. El consultor solo abre fichas de su "
        "trabajo (tomadas de su cola o con un acercamiento suyo reciente), nunca de menores."),
    entrada=VerEntrada, tipo="lectura", permisos=("personas.ver",), etiqueta="Consultando la ficha", ejecutar=_ver,
    esquema=esquema(VerEntrada))


# ───────────────────────────── personas_parecidas ─────────────────────────────

class ParecidasEntrada(_Entrada):
    persona_id: Id | None = Field(None, description="Fichas parecidas a esta (posibles duplicados)")
    nombre: str | None = Field(None, min_length=3, max_length=160, description="Nombre de quien se va a registrar")
    cedula: str | None = Field(None, max_length=20, description="Opcional, con nombre")
    telefono: str | None = Field(None, max_length=60, description="Opcional, con nombre")

    @model_validator(mode="after")
    def _una_forma(self):
        if self.persona_id is None and not self.nombre:
            raise ValueError("Indique persona_id, o nombre (con cédula y teléfono opcionales)")
        if self.persona_id is not None and (self.nombre or self.cedula or self.telefono):
            raise ValueError("Use persona_id solo, o nombre con cédula y teléfono: no las dos formas")
        _nombre(self.nombre)
        return self


async def _parecidas(ctx: Contexto, a: ParecidasEntrada) -> Resultado:
    if a.persona_id is not None:
        d = await _pedir(ctx, "GET", f"/api/personas/{a.persona_id}/parecidas")
    else:
        d = await _pedir(ctx, "GET", "/api/parecidas", params={"nombre": a.nombre, "cedula": a.cedula,
                                                                "telefono": a.telefono})
    fs = minimizar.filas(d if isinstance(d, list) else [])
    contenido = {"total": len(fs), "parecidas": fs,
                 "nota": "parecido va de 0 a 100; cedula_distinta: true quiere decir que son personas distintas."}
    n = len(fs)
    resumen = "Sin fichas parecidas" if not n else "1 ficha parecida" if n == 1 else f"{n} fichas parecidas"
    personas = minimizar.ids_de(fs) | ({a.persona_id} if a.persona_id else set())
    return Resultado(contenido, resumen, personas=personas)


PARECIDAS = Herramienta(
    nombre="personas_parecidas",
    descripcion=(
        "Busca fichas que podrían ser la misma persona (posibles duplicados): con `persona_id`, las parecidas a esa "
        "ficha; con `nombre` (y `cedula` y `telefono` si los tienes), antes de crear una ficha nueva. Devuelve hasta 8 "
        "filas con `parecido` (0 a 100), `tiene_cedula` y `cedula_distinta`. Úsala antes de crear_persona si no estás "
        "seguro de que la persona no exista. Unir fichas no se hace aquí: es del administrador, en Calidad."),
    entrada=ParecidasEntrada, tipo="lectura", permisos=("personas.parecidas",), etiqueta="Buscando fichas parecidas",
    ejecutar=_parecidas, esquema=esquema(ParecidasEntrada))


# ───────────────────────────── crear_persona ─────────────────────────────

class CrearEntrada(_Entrada):
    nombre: str = Field(..., min_length=3, max_length=160, description="Nombre completo, como lo dictaron")
    tipo_documento: Literal[TIPOS_DOCUMENTO] | None = Field(None, description="CC por defecto si hay cédula")
    cedula: str | None = Field(None, max_length=20, description="Número de documento dictado")
    telefonos: list[Annotated[str, Field(min_length=7, max_length=60)]] = Field(
        default_factory=list, max_length=10, description="Números dictados, uno por elemento")
    sexo: Literal["F", "M", "N"] | None = Field(None, description="F mujer, M hombre, N prefiere no decir")
    fecha_nacimiento: str | None = Field(None, description="AAAA-MM-DD")
    edad: int | None = Field(None, ge=0, le=120, description="Edad declarada, si no hay fecha de nacimiento")
    direccion: str | None = Field(None, min_length=3, max_length=240)
    lugar_id: Id | None = Field(None, description="Barrio o vereda (id de buscar_lugar)")
    ocupacion: str | None = Field(None, min_length=2, max_length=120)
    etiquetas: list[Id] = Field(default_factory=list, max_length=30, description="Necesidades e intereses (ids de "
                                                                                  "catalogos; no las sensibles)")
    reunion_id: Id | None = Field(None, description="Reunión donde se registra (cuenta como su asistencia)")
    forzar: bool = Field(False, description="true solo si ya se revisaron las parecidas y es otra persona")

    @field_validator("nombre")
    @classmethod
    def _n(cls, v):
        return _nombre(v)

    @field_validator("telefonos")
    @classmethod
    def _t(cls, v):
        return _sin_repetidos([_un_telefono(t) for t in v])

    @field_validator("fecha_nacimiento")
    @classmethod
    def _f(cls, v):
        return _fecha(v, pasada=True)

    @field_validator("etiquetas")
    @classmethod
    def _e(cls, v):
        return _sin_repetidos(v)

    @model_validator(mode="after")
    def _doc(self):
        self.cedula = _documento(self.cedula, self.tipo_documento)
        if self.tipo_documento and not self.cedula:
            raise ValueError("Con tipo_documento hace falta el número (cedula)")
        return self


def _es_menor(a: CrearEntrada) -> bool:
    if a.tipo_documento == "TI" or (a.edad is not None and a.edad < 18):
        return True
    if a.fecha_nacimiento:
        n, hoy = date.fromisoformat(a.fecha_nacimiento), modelo.hoy_local()
        return (hoy.year - n.year - ((hoy.month, hoy.day) < (n.month, n.day))) < 18
    return False


def _cuerpo_crear(a: CrearEntrada) -> dict:
    cuerpo = a.model_dump(exclude_none=True, exclude={"forzar"})
    for k in ("telefonos", "etiquetas"):
        if not cuerpo.get(k):
            cuerpo.pop(k, None)
    cuerpo["forzar"] = a.forzar
    return cuerpo


async def _revisar_crear(ctx: Contexto, a: CrearEntrada) -> list[tuple[str, str]]:
    """Lo que depende solo de la entrada (rol, catálogos, reunión visible): lo revisan la tarjeta y la ejecución, así
    nada cambia entre las dos sin que se note. Devuelve el detalle de la tarjeta."""
    q = ctx.quien
    if not q.administra and q.rol == "planillero" and _es_menor(a):
        raise ErrorHerramienta("El planillero no registra menores de edad.", "invalido", estado=422)
    detalle: list[tuple[str, str]] = [("Nombre", tx.nombre_visible(a.nombre))]
    if a.cedula:
        detalle.append(("Documento", f"{a.tipo_documento or 'CC'} {a.cedula}"))
    if a.telefonos:
        detalle.append(("Teléfonos", ", ".join(a.telefonos)))
    if a.sexo:
        detalle.append(("Sexo", modelo.SEXOS[a.sexo]))
    if a.fecha_nacimiento:
        detalle.append(("Fecha de nacimiento", a.fecha_nacimiento))
    if a.edad is not None:
        detalle.append(("Edad", str(a.edad)))
    if a.direccion:
        detalle.append(("Dirección", a.direccion))
    if a.lugar_id is not None:
        lg = await run_in_threadpool(_lugar, ctx.db, a.lugar_id)
        if lg is None:
            raise ErrorHerramienta(f"El barrio o vereda #{a.lugar_id} no existe: búsquelo con buscar_lugar.",
                                   "no_existe", estado=404)
        detalle.append(("Barrio o vereda", f"{lg.get('nombre')} ({lg.get('tipo')})"))
    if a.ocupacion:
        detalle.append(("Ocupación", a.ocupacion))
    if a.etiquetas:
        detalle.append(("Necesidades e intereses", ", ".join(await _nombres_etiquetas(ctx, a.etiquetas))))
    reunion = await _reunion_visible(ctx, a.reunion_id)
    if reunion:
        detalle.append(("Reunión", reunion))
    return detalle


async def _confirmar_crear(ctx: Contexto, a: CrearEntrada) -> Confirmacion:
    detalle = await _revisar_crear(ctx, a)
    aviso = ("Se creará aunque haya fichas parecidas: ya se revisó que es otra persona." if a.forzar else
             "Si el panel encuentra fichas parecidas, no la crea y el asistente le muestra las candidatas.")
    return Confirmacion(f"Crear la ficha de {tx.nombre_visible(a.nombre)}", detalle, aviso)


async def _crear(ctx: Contexto, a: CrearEntrada) -> Resultado:
    await _revisar_crear(ctx, a)
    try:
        d = await ctx.api.pedir("POST", "/api/personas", json_=_cuerpo_crear(a), clave=_clave(ctx))
    except ErrorHerramienta as e:
        if e.codigo != "parecidas":
            raise _seguro(e) from None
        candidatas = e.detalle.get("parecidas") if isinstance(e.detalle, dict) else None
        fs = minimizar.filas(candidatas if isinstance(candidatas, list) else [])
        contenido = {"creada": False, "codigo": "parecidas", "parecidas": fs, "mensaje": (
            "No se creó: ya hay fichas parecidas. Muéstrelas y pregunte si es alguna de ellas; solo si la persona del "
            "equipo confirma que es otra persona, proponga crearla de nuevo con forzar: true.")}
        n = len(fs)
        return Resultado(contenido, f"No se creó: {n} ficha{'s' if n != 1 else ''} parecida{'s' if n != 1 else ''}",
                         personas=minimizar.ids_de(fs))
    if not isinstance(d, dict) or not isinstance(d.get("id"), int):
        raise ErrorHerramienta("La API del panel no devolvió la ficha creada.", "error")
    return Resultado({"creada": True, "persona": _breve(d)}, f"Ficha creada (#{d['id']})", list(ACCIONES_ESCRITURA),
                     personas={d["id"]})


CREAR = Herramienta(
    nombre="crear_persona",
    descripcion=(
        "Propone crear la ficha de una persona nueva con los datos que te dictaron. No se crea hasta que la persona "
        "del equipo la aprueba en el panel. Antes, busca si ya existe (buscar_personas o personas_parecidas). Si al "
        "aprobarla el panel encuentra fichas parecidas, no se crea y te devuelve las candidatas: muéstralas y pregunta "
        "si es alguna; solo si te confirman que es otra persona, vuelve a proponerla con `forzar: true`. No inventes "
        "cédulas, teléfonos ni otros datos. El planillero no registra menores de edad. La autorización de datos se "
        "registra después con registrar_autorizacion. Devuelve el id y lo que le falta a la ficha creada."),
    entrada=CrearEntrada, tipo="escritura", permisos=("personas.crear",), etiqueta="Creando la ficha",
    ejecutar=_crear, confirmar=_confirmar_crear, esquema=esquema(CrearEntrada))


# ───────────────────────────── editar_persona ─────────────────────────────

class CambiosPersona(_Entrada):
    """Lista blanca de lo que el asistente edita. Nunca: sensibles, líder, listas, autorización
    (registrar_autorizacion), teléfonos (agregar_telefono), correo, observaciones (agregar_nota), barrio o ubicación
    (ubicar_persona) ni campos propios. Sin valores vacíos: vaciar un dato se hace en el panel."""
    nombre: str | None = Field(None, min_length=3, max_length=160)
    tipo_documento: Literal[TIPOS_DOCUMENTO] | None = None
    cedula: str | None = Field(None, max_length=20)
    sexo: Literal["F", "M", "N"] | None = None
    fecha_nacimiento: str | None = Field(None, description="AAAA-MM-DD")
    edad: int | None = Field(None, ge=0, le=120)
    estado_civil: Literal[tuple(modelo.ESTADOS_CIVILES)] | None = None
    nivel_educativo: Literal[tuple(modelo.NIVELES)] | None = None
    situacion_laboral: Literal[tuple(modelo.SITUACIONES_LABORALES)] | None = None
    ocupacion: str | None = Field(None, min_length=2, max_length=120)
    personas_hogar: int | None = Field(None, ge=0, le=40)
    jefe_hogar: bool | None = None
    tenencia_vivienda: Literal[tuple(modelo.TENENCIAS)] | None = None
    estrato: int | None = Field(None, ge=0, le=6)
    direccion: str | None = Field(None, min_length=3, max_length=240)
    puesto_id: Id | None = Field(None, description="Puesto de votación del catálogo (id)")
    puesto_texto: str | None = Field(None, min_length=3, max_length=160, description="Puesto como lo dictaron, si no "
                                                                                     "se sabe el id")
    mesa: int | None = Field(None, ge=1, le=999)
    donde: Literal[tuple(modelo.DONDE_VOTA)] | None = Field(None, description="Dónde vota")
    municipio: str | None = Field(None, min_length=3, max_length=80, description="Si vota en otro municipio")
    etiquetas_agregar: list[Id] = Field(default_factory=list, max_length=20, description="Necesidades o intereses a "
                                                                                         "sumar (ids de catalogos)")
    etiquetas_quitar: list[Id] = Field(default_factory=list, max_length=20)

    @field_validator("nombre")
    @classmethod
    def _n(cls, v):
        return _nombre(v)

    @field_validator("fecha_nacimiento")
    @classmethod
    def _f(cls, v):
        return _fecha(v, pasada=True)

    @field_validator("etiquetas_agregar", "etiquetas_quitar")
    @classmethod
    def _e(cls, v):
        return _sin_repetidos(v)

    @model_validator(mode="after")
    def _coherente(self):
        if self.tipo_documento is not None:
            self.cedula = _documento(self.cedula, self.tipo_documento)
        elif self.cedula is not None and not re.fullmatch(r"[A-Za-z0-9 .-]{4,20}", self.cedula):
            raise ValueError("El documento debe tener de 4 a 15 letras o números")
        # Sin tipo en la entrada vale el de la ficha (un pasaporte, por ejemplo): se normaliza al leerla
        if not cambios_de(self):
            raise ValueError("No hay cambios: indique al menos un campo")
        if self.puesto_id is not None and self.puesto_texto:
            raise ValueError("Use puesto_id o puesto_texto, no los dos")
        if self.municipio and self.donde not in (None, "otro_municipio"):
            raise ValueError("municipio va con donde: otro_municipio")
        if set(self.etiquetas_agregar) & set(self.etiquetas_quitar):
            raise ValueError("Una etiqueta no puede estar en etiquetas_agregar y en etiquetas_quitar")
        return self


def cambios_de(c: CambiosPersona) -> dict:
    return {k: v for k, v in c.model_dump(exclude_none=True).items() if v not in ([], "")}


class EditarEntrada(_Entrada):
    persona_id: Id
    cambios: CambiosPersona = Field(..., description="Los campos que cambian, con su valor nuevo (al menos uno). Sin "
                                                     "valores vacíos: vaciar un dato se hace en el panel")
    modo: Literal["completar", "reemplazar"] = Field(
        "completar", description="completar: solo llena lo vacío (un valor distinto queda como alterno); reemplazar: "
                                 "corrige el valor que ya tiene")
    motivo_cambio_cedula: str | None = Field(None, min_length=3, max_length=300,
                                             description="Obligatorio para cambiar una cédula que ya existe")
    # Huellas de los valores que mostró la tarjeta: las pone `confirmar` (el modelo no las ve; ver `_huella`)
    huellas: SkipJsonSchema[dict[str, str] | None] = None

    @field_validator("huellas")
    @classmethod
    def _h(cls, v):
        return _huellas_validas(v, CAMPOS_BASE)


ETIQUETAS_CAMPO = {
    "nombre": "Nombre", "tipo_documento": "Tipo de documento", "cedula": "Cédula", "sexo": "Sexo",
    "fecha_nacimiento": "Fecha de nacimiento", "edad": "Edad", "estado_civil": "Estado civil",
    "nivel_educativo": "Nivel educativo", "situacion_laboral": "Situación laboral", "ocupacion": "Ocupación",
    "personas_hogar": "Personas en el hogar", "jefe_hogar": "Jefe de hogar", "tenencia_vivienda": "Tenencia de la "
    "vivienda", "estrato": "Estrato", "direccion": "Dirección", "puesto_id": "Puesto de votación",
    "puesto_texto": "Puesto de votación", "mesa": "Mesa", "donde": "Dónde vota", "municipio": "Municipio donde vota",
    "etiquetas": "Necesidades e intereses",
}
VOTACION = {"puesto_id": "puesto_id", "puesto_texto": "puesto_texto", "donde": "donde", "municipio": "municipio"}
# Campos cuya comparación (`base`) acepta la API (BASE_PERMITIDOS): los simples, el documento y la votación sin la mesa
CAMPOS_BASE = frozenset({"nombre", "tipo_documento", "cedula", "sexo", "fecha_nacimiento", "edad", "estado_civil",
                         "nivel_educativo", "situacion_laboral", "ocupacion", "personas_hogar", "jefe_hogar",
                         "tenencia_vivienda", "estrato", "direccion", "puesto_id", "puesto_texto", "donde",
                         "municipio", "lugar_id"})
# En modo completar, un valor distinto de estos queda como alterno (modelo.CAMPOS_PROCEDENCIA y la votación); de los
# demás no se guarda nada
CON_ALTERNO = frozenset(modelo.CAMPOS_PROCEDENCIA) | {"puesto_id", "puesto_texto", "mesa", "donde", "municipio"}


def _votacion(d: dict) -> dict:
    return d.get("votacion") if isinstance(d.get("votacion"), dict) else {}


def _actual(d: dict, campo: str) -> Any:
    """El valor de la ficha (de la API) que el cambio compara o reemplaza."""
    v = _votacion(d)
    if campo == "puesto_id":
        return v.get("puesto_id")
    if campo == "puesto_texto":
        return v.get("puesto_texto") or v.get("puesto_nombre") or d.get("puesto_votacion")
    if campo == "mesa":
        return v.get("mesa") if v.get("mesa") is not None else (v.get("mesa_texto") or d.get("mesa"))
    if campo in ("donde", "municipio"):
        return v.get(campo)
    return d.get(campo)


def _base_de(d: dict, campo: str) -> Any:
    """El valor que la API compara para `base` (la votación, dentro de `votacion`)."""
    return _votacion(d).get(VOTACION[campo]) if campo in VOTACION else d.get(campo)


def _vacio(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip()) or v in ([], {})


def _igual(campo: str, actual: Any, nuevo: Any) -> bool:
    if _vacio(actual):
        return False
    if campo == "nombre":
        return tx.nombre_norm(actual) == tx.nombre_norm(nuevo)
    if campo == "cedula":
        return re.sub(r"[\W_]", "", str(actual)).upper() == re.sub(r"[\W_]", "", str(nuevo)).upper()
    if campo == "mesa":
        return str(actual).strip() == str(nuevo) or modelo.normalizar_mesa(actual) == nuevo
    if isinstance(actual, str) and isinstance(nuevo, str):
        return tx.limpiar(actual) == tx.limpiar(nuevo)
    if isinstance(actual, bool) or isinstance(nuevo, bool):
        return actual is nuevo
    if isinstance(actual, (int, float)) and isinstance(nuevo, (int, float)):
        return actual == nuevo  # 40 y 40.0 (de una importación) son lo mismo, como en la API
    return False


def _mostrar(campo: str, v: Any, *, antes: bool = False) -> str:
    if _vacio(v):
        return "(vacío)"
    if campo == "cedula" and antes:
        return acceso.enmascarar_cedula(v) or "(vacío)"  # la de antes no se repite completa en la tarjeta guardada
    if campo == "sexo":
        return modelo.SEXOS.get(v, str(v))
    if campo == "donde":
        return modelo.DONDE_VOTA.get(v, str(v))
    if isinstance(v, bool):
        return _si_no(v)
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


@dataclass
class Paso:
    campo: str
    antes: str
    despues: str
    efecto: str  # igual | llenar | reemplazar | alterno | ignorado | agregar | quitar
    valor: Any = None


EFECTIVOS = ("llenar", "reemplazar", "alterno", "agregar", "quitar")


def _cedula_efectiva(d: dict, a: EditarEntrada) -> str | None:
    """La cédula de la entrada normalizada con el tipo de documento que va a quedar (el de la entrada o el de la ficha),
    como lo hace la API."""
    try:
        return _documento(a.cambios.cedula, a.cambios.tipo_documento or d.get("tipo_documento"))
    except ValueError as e:
        raise ErrorHerramienta(str(e), "invalido", estado=422) from None


def _plan(d: dict, a: EditarEntrada, nombres_et: dict[int, str] | None = None,
          nombre_puesto: str | None = None) -> list[Paso]:
    """Qué hace cada cambio sobre la ficha actual, con la misma regla que la API (`editar`, modo completar)."""
    pasos: list[Paso] = []
    cambios = cambios_de(a.cambios)
    if "cedula" in cambios:
        cambios["cedula"] = _cedula_efectiva(d, a)
    for campo, nuevo in cambios.items():
        if campo in ("etiquetas_agregar", "etiquetas_quitar"):
            continue
        actual = _actual(d, campo)
        despues = nombre_puesto if (campo == "puesto_id" and nombre_puesto) else _mostrar(campo, nuevo)
        antes = _mostrar(campo, actual, antes=True)
        if campo == "puesto_id" and not _vacio(actual):
            antes = _mostrar(campo, _votacion(d).get("puesto_nombre") or actual)
        if _igual(campo, actual, nuevo):
            efecto = "igual"
        elif _vacio(actual):
            efecto = "llenar"
        elif a.modo == "reemplazar":
            efecto = "reemplazar"
        else:
            efecto = "alterno" if campo in CON_ALTERNO else "ignorado"
        pasos.append(Paso(campo, antes, despues, efecto, nuevo))
    actuales = [e.get("id") for e in d.get("etiquetas") or [] if isinstance(e, dict)]
    nombres = nombres_et or {}
    for i in a.cambios.etiquetas_agregar:
        pasos.append(Paso("etiquetas", "", nombres.get(i, f"#{i}"), "igual" if i in actuales else "agregar", i))
    for i in a.cambios.etiquetas_quitar:
        pasos.append(Paso("etiquetas", nombres.get(i, f"#{i}"), "", "quitar" if i in actuales else "igual", i))
    return pasos


def _exigir_editables(d: dict, a: EditarEntrada, pasos: list[Paso]) -> None:
    """Lo que la API rechazaría (403/422) después de aprobar: se dice antes, con el porqué y qué hacer. Solo cuenta lo
    que de verdad cambia (dictar la misma cédula no es cambiarla)."""
    editables = set(d.get("editables") or [])
    for p in pasos:
        if p.efecto in EFECTIVOS and p.campo not in editables:
            raise ErrorHerramienta(f"Su rol no puede cambiar «{ETIQUETAS_CAMPO.get(p.campo, p.campo)}» en esta ficha: "
                                   "pida la corrección al administrador.", "permiso", estado=403,
                                   detalle={"campo": p.campo})
    if any(p.campo == "cedula" and p.efecto in EFECTIVOS for p in pasos) and not _vacio(d.get("cedula")):
        if a.modo == "completar":
            raise ErrorHerramienta("La cédula dictada es distinta de la de esta ficha: puede ser otra persona. Si es "
                                   "una corrección, use modo reemplazar con motivo_cambio_cedula.", "invalido",
                                   estado=422)
        if not a.motivo_cambio_cedula:
            raise ErrorHerramienta("Para cambiar una cédula que ya existe hace falta motivo_cambio_cedula: "
                                   "pregúntelo.", "invalido", estado=422)


def _detalle_edicion(pasos: list[Paso]) -> list[tuple[str, str]]:
    out = []
    for p in pasos:
        et = ETIQUETAS_CAMPO.get(p.campo, p.campo)
        if p.efecto == "agregar":
            out.append((et, f"+ {p.despues}"))
        elif p.efecto == "quitar":
            out.append((et, f"− {p.antes}"))
        elif p.efecto in ("llenar", "reemplazar"):
            out.append((et, f"{p.antes} → {p.despues}"))
        elif p.efecto == "alterno":
            out.append((et, f"{p.antes} (se conserva; «{p.despues}» queda como dato alterno)"))
        elif p.efecto == "ignorado":
            out.append((et, f"{p.antes} (se conserva; «{p.despues}» no se guarda en modo completar)"))
    return out


async def _datos_edicion(ctx: Contexto, a: EditarEntrada) -> tuple[dict[int, str], str | None]:
    ids = [*a.cambios.etiquetas_agregar, *a.cambios.etiquetas_quitar]
    nombres = dict(zip(ids, await _nombres_etiquetas(ctx, ids))) if ids else {}
    nombre_puesto = None
    if a.cambios.puesto_id is not None:
        pu = await run_in_threadpool(_puesto, ctx.db, a.cambios.puesto_id)
        if pu is None:
            raise ErrorHerramienta(f"El puesto de votación #{a.cambios.puesto_id} no existe.", "no_existe", estado=404)
        nombre_puesto = str(pu.get("nombre"))
    return nombres, nombre_puesto


def _sin_efecto(pasos: list[Paso]) -> ErrorHerramienta:
    if any(p.efecto == "ignorado" for p in pasos):
        return ErrorHerramienta("La ficha ya tiene otro valor en esos campos y el modo completar no los cambia. Si hay "
                                "que corregirlos, use modo reemplazar.", "sin_cambios")
    return ErrorHerramienta("La ficha ya tiene esos valores: no hay nada que guardar.", "sin_cambios")


async def _confirmar_editar(ctx: Contexto, a: EditarEntrada) -> Confirmacion:
    d = await _ficha(ctx, a.persona_id)
    _exigir_tratable(d)
    nombres, puesto = await _datos_edicion(ctx, a)
    pasos = _plan(d, a, nombres, puesto)
    _exigir_editables(d, a, pasos)
    if not any(p.efecto in EFECTIVOS for p in pasos):
        raise _sin_efecto(pasos)
    clave = await _clave_huellas(ctx)
    a.huellas = {p.campo: _huella(clave, p.campo, _base_de(d, p.campo)) for p in pasos
                 if p.efecto in EFECTIVOS and p.campo in CAMPOS_BASE}
    detalle = _detalle_edicion(pasos)
    if a.motivo_cambio_cedula and any(p.campo == "cedula" and p.efecto in EFECTIVOS for p in pasos):
        detalle.append(("Motivo del cambio de cédula", a.motivo_cambio_cedula))
    sin_cambio = [ETIQUETAS_CAMPO.get(p.campo, p.campo) for p in pasos if p.efecto == "igual"]
    aviso = f"Sin cambio (ya tenía ese valor): {', '.join(sin_cambio)}." if sin_cambio else None
    modo = "Completar lo que falta" if a.modo == "completar" else "Reemplazar los valores"
    return Confirmacion(f"Editar la ficha de {_persona(d)}", [("Modo", modo), *detalle], aviso)


def _cuerpo_editar(d: dict, a: EditarEntrada, pasos: list[Paso]) -> dict:
    cuerpo: dict[str, Any] = {}
    for p in pasos:
        if p.efecto in ("llenar", "reemplazar", "alterno") and p.campo != "etiquetas":
            cuerpo[p.campo] = p.valor
    if any(p.campo == "etiquetas" and p.efecto in ("agregar", "quitar") for p in pasos):
        actuales = [e.get("id") for e in d.get("etiquetas") or [] if isinstance(e, dict)]
        agregar = {p.valor for p in pasos if p.efecto == "agregar"}
        quitar = {p.valor for p in pasos if p.efecto == "quitar"}
        cuerpo["etiquetas"] = [*[e for e in actuales if e not in quitar], *sorted(agregar - set(actuales))]
        cuerpo["etiquetas_base"] = actuales
    if "cedula" in cuerpo and a.motivo_cambio_cedula and not _vacio(d.get("cedula")):
        cuerpo["motivo_cambio_cedula"] = a.motivo_cambio_cedula
    # La base son los valores recién leídos (ya comparados con las huellas de la tarjeta): la API rechaza con 409 si
    # cambian entre esta lectura y la escritura
    base = {p.campo: _base_de(d, p.campo) for p in pasos if p.efecto in EFECTIVOS and p.campo in CAMPOS_BASE}
    if base:
        cuerpo["base"] = base
    return cuerpo


async def _editar(ctx: Contexto, a: EditarEntrada) -> Resultado:
    d = await _ficha(ctx, a.persona_id)
    _exigir_tratable(d)
    nombres, puesto = await _datos_edicion(ctx, a)
    pasos = _plan(d, a, nombres, puesto)
    _exigir_editables(d, a, pasos)
    if not any(p.efecto in EFECTIVOS for p in pasos):
        if any(p.efecto == "ignorado" for p in pasos):
            raise _sin_efecto(pasos)
        # Ya quedó como se pidió (una repetición del mismo tool_use, o alguien lo hizo antes): no se escribe otra vez
        return Resultado({"guardado": True, "sin_cambios": True, "persona": _breve(d),
                          "mensaje": "La ficha ya tenía esos valores: no se escribió nada."},
                         f"Sin cambios en la ficha #{a.persona_id}", personas={a.persona_id})
    if a.huellas:  # solo lo que todavía cambia: lo que ya quedó como se pidió no es un conflicto
        _exigir_sin_cambios(d, a.huellas, [p.campo for p in pasos if p.efecto in EFECTIVOS], await _clave_huellas(ctx),
                            _base_de)
    params = {"modo": "completar"} if a.modo == "completar" else None
    r = await _pedir(ctx, "PATCH", f"/api/personas/{a.persona_id}", params=params, cuerpo=_cuerpo_editar(d, a, pasos),
                     clave=_clave(ctx))
    hechos = [p for p in pasos if p.efecto in EFECTIVOS]
    contenido = {"guardado": True, "persona": _breve(r if isinstance(r, dict) else d),
                 "cambios": [{"campo": p.campo, "efecto": p.efecto} for p in hechos]}
    n = len(hechos)
    return Resultado(contenido, f"Ficha #{a.persona_id} actualizada ({n} cambio{'s' if n != 1 else ''})",
                     list(ACCIONES_ESCRITURA), personas={a.persona_id})


EDITAR = Herramienta(
    nombre="editar_persona",
    descripcion=(
        "Propone cambiar datos de una ficha existente (`cambios`). No se guarda hasta que la persona del equipo lo "
        "aprueba en una tarjeta que muestra «antes → después». Modo `completar` (por defecto): solo llena lo vacío; "
        "si el dato ya tenía otro valor, se conserva y el nuevo queda como alterno. Modo `reemplazar`: corrige el "
        "valor que ya tiene (solo si te dictaron una corrección). No sirve para teléfonos (agregar_telefono), notas "
        "(agregar_nota), autorización (registrar_autorizacion) ni barrio o ubicación (ubicar_persona), y nunca toca "
        "datos sensibles, listas ni liderazgo. Cambiar una cédula que ya existe es solo del administrador y del "
        "coordinador, con `motivo_cambio_cedula`. Si otra persona cambió la ficha entre la tarjeta y la aprobación, "
        "falla con «cambiada»: vuelve a leerla y propón de nuevo. Usa solo valores dictados, nunca supuestos."),
    entrada=EditarEntrada, tipo="escritura", permisos=("personas.editar",), etiqueta="Editando la ficha",
    ejecutar=_editar, confirmar=_confirmar_editar, esquema=esquema(EditarEntrada))


# ───────────────────────────── agregar_nota ─────────────────────────────

class NotaEntrada(_Entrada):
    persona_id: Id
    texto: str = Field(..., min_length=1, max_length=2000)
    reunion_id: Id | None = Field(None, description="Reunión a la que se refiere la nota, si aplica")


async def _confirmar_nota(ctx: Contexto, a: NotaEntrada) -> Confirmacion:
    d = await _ficha(ctx, a.persona_id)
    _exigir_tratable(d)
    detalle = [("Persona", _persona(d)), ("Nota", a.texto)]
    reunion = await _reunion_visible(ctx, a.reunion_id)
    if reunion:
        detalle.append(("Reunión", reunion))
    return Confirmacion(f"Agregar una nota a {_persona(d)}", detalle)


async def _nota(ctx: Contexto, a: NotaEntrada) -> Resultado:
    await _reunion_visible(ctx, a.reunion_id)  # la API guarda el id sin revisar que la reunión sea visible
    d = await _pedir(ctx, "POST", f"/api/personas/{a.persona_id}/notas",
                     cuerpo={"texto": a.texto, "reunion_id": a.reunion_id}, clave=_clave(ctx))
    d = d if isinstance(d, dict) else {}
    notas = d.get("notas") if isinstance(d.get("notas"), list) else None
    contenido = {"guardada": True, "persona": _breve(d) or {"id": a.persona_id},
                 **({"notas_n": len(notas)} if notas is not None else {})}
    return Resultado(contenido, f"Nota guardada en la ficha #{a.persona_id}", list(ACCIONES_ESCRITURA),
                     personas={a.persona_id})


NOTA = Herramienta(
    nombre="agregar_nota",
    descripcion=(
        "Propone agregar una nota a la ficha de una persona (texto libre de hasta 2.000 caracteres), opcionalmente "
        "ligada a una reunión. Se guarda solo si la persona del equipo la aprueba. Escribe solo lo que te pidieron "
        "registrar; no pongas datos sensibles (salud, etnia, discapacidad, condición de víctima, afiliación política) "
        "ni cédulas o teléfonos completos. Para un contacto con la persona usa registrar_acercamiento."),
    entrada=NotaEntrada, tipo="escritura", permisos=("personas.notas",), etiqueta="Agregando una nota",
    ejecutar=_nota, confirmar=_confirmar_nota, esquema=esquema(NotaEntrada))


# ───────────────────────────── registrar_acercamiento ─────────────────────────────

class AcercamientoEntrada(_Entrada):
    persona_id: Id
    canal: Literal[tuple(modelo.CANALES)]
    resultado: Literal[tuple(modelo.RESULTADOS)] = Field(
        ..., description="volver_llamar: pidió que lo contacten después (con proximo); solicitud_derechos: pidió "
                         "consultar, corregir o borrar sus datos; no_contactar: pidió no ser contactado")
    telefono_indice: int | None = Field(None, ge=0, le=50, description="El `indice` del teléfono en ver_persona; "
                                                                       "obligatorio en llamada, WhatsApp y SMS")
    nota: str | None = Field(None, min_length=1, max_length=2000)
    confirma_numero: bool = Field(False, description="Contestó y confirmó que el número es suyo")
    alcance: Literal["numero", "persona"] | None = Field(
        None, description="Con no_contactar: numero (solo ese número) o persona (ningún contacto: revoca su "
                          "autorización)")
    proximo: str | None = Field(None, description="Con volver_llamar: fecha AAAA-MM-DD, hoy o después")
    proximo_franja: Literal[tuple(modelo.FRANJAS)] | None = Field(None, description="Con volver_llamar")
    se_fue_del_municipio: bool = Field(False, description="Con no_vive_aqui: ya no vive en Yondó")
    solicitud_tipo: Literal["consulta", "correccion", "supresion", "otro"] | None = Field(
        None, description="Con solicitud_derechos: qué pidió sobre sus datos")

    @field_validator("proximo")
    @classmethod
    def _p(cls, v):
        return _fecha(v, futura=True)

    @model_validator(mode="after")
    def _coherente(self):
        r = self.resultado
        if self.canal in CANALES_TELEFONO and self.telefono_indice is None:
            raise ValueError("En llamada, WhatsApp o SMS indique telefono_indice (el indice del teléfono en "
                             "ver_persona)")
        if r in ("numero_equivocado", "numero_inexistente") and self.telefono_indice is None:
            raise ValueError("Ese resultado necesita telefono_indice: el número que falló")
        if r == "no_contactar":
            if self.alcance is None:
                raise ValueError("Con no_contactar indique alcance: numero o persona")
            if self.alcance == "numero" and self.telefono_indice is None:
                raise ValueError("Con alcance numero indique telefono_indice")
        elif self.alcance is not None:
            raise ValueError("alcance solo va con resultado no_contactar")
        if (self.proximo or self.proximo_franja) and r != "volver_llamar":
            raise ValueError("proximo y proximo_franja solo van con resultado volver_llamar")
        if self.se_fue_del_municipio and r != "no_vive_aqui":
            raise ValueError("se_fue_del_municipio solo va con resultado no_vive_aqui")
        if self.solicitud_tipo and r != "solicitud_derechos":
            raise ValueError("solicitud_tipo solo va con resultado solicitud_derechos")
        if self.confirma_numero and (r != "contesto" or self.telefono_indice is None):
            raise ValueError("confirma_numero solo va con resultado contesto y telefono_indice")
        return self


def _aviso_acercamiento(a: AcercamientoEntrada) -> str | None:
    r = a.resultado
    if r == "no_contactar":
        return ("Ese número queda marcado para no contactar." if a.alcance == "numero" else
                "Queda en «no contactar» y se revoca su autorización (se abre una solicitud de revocatoria).")
    if r in ("numero_equivocado", "numero_inexistente"):
        return f"Ese número queda marcado como «{'equivocado' if r == 'numero_equivocado' else 'no existe'}»."
    if r == "fallecio":
        return "La persona queda reportada como fallecida y sale de las colas (el administrador lo confirma)."
    if r == "no_vive_aqui":
        return "Se pide actualizar su dirección" + (" y queda reportada como que ya no vive en Yondó."
                                                    if a.se_fue_del_municipio else ".")
    if r == "solicitud_derechos":
        return "Se abre una solicitud sobre sus datos, con plazo legal de respuesta."
    return None


def _exigir_canal(ctx: Contexto, a: AcercamientoEntrada) -> None:
    q = ctx.quien
    if not q.administra and q.rol == "planillero" and a.canal not in ("visita", "reunion"):
        raise ErrorHerramienta("El planillero registra visitas y reuniones.", "permiso", estado=403)
    if not q.administra and q.rol == "consultor" and a.canal in ("visita", "reunion"):
        raise ErrorHerramienta("El consultor registra llamadas y mensajes.", "permiso", estado=403)


async def _confirmar_acercamiento(ctx: Contexto, a: AcercamientoEntrada) -> Confirmacion:
    _exigir_canal(ctx, a)
    d = await _ficha(ctx, a.persona_id)
    _exigir_tratable(d)
    detalle = [("Persona", _persona(d)), ("Canal", modelo.CANALES[a.canal])]
    if a.telefono_indice is not None:
        t = next((t for t in d.get("telefonos") or [] if isinstance(t, dict) and t.get("indice") == a.telefono_indice),
                 None)
        if t is None:
            usables = sorted(t.get("indice") for t in d.get("telefonos") or []
                             if isinstance(t, dict) and isinstance(t.get("indice"), int))
            raise ErrorHerramienta(f"La ficha no tiene un número usable con indice {a.telefono_indice}"
                                   + (f" (los usables: {usables})." if usables else ": no tiene números usables."),
                                   "invalido", estado=422)
        detalle.append(("Número", acceso.enmascarar_telefono(t.get("numero")) or "(sin número)"))
    detalle.append(("Resultado", modelo.etiqueta_resultado(a.resultado, a.canal)))
    if a.confirma_numero:
        detalle.append(("Confirmó que el número es suyo", "Sí"))
    if a.alcance:
        detalle.append(("No contactar", "Solo ese número" if a.alcance == "numero" else "Ningún contacto"))
    if a.proximo or a.proximo_franja:
        cuando = (a.proximo, modelo.FRANJAS.get(a.proximo_franja or ""))
        detalle.append(("Próximo contacto", " · ".join(x for x in cuando if x)))
    if a.se_fue_del_municipio:
        detalle.append(("Se fue del municipio", "Sí"))
    if a.solicitud_tipo:
        detalle.append(("Qué pidió", a.solicitud_tipo))
    if a.nota:
        detalle.append(("Nota", a.nota))
    return Confirmacion(f"Registrar un acercamiento con {_persona(d)}", detalle, _aviso_acercamiento(a))


async def _acercamiento(ctx: Contexto, a: AcercamientoEntrada) -> Resultado:
    _exigir_canal(ctx, a)
    cuerpo = a.model_dump(exclude_none=True, exclude={"persona_id"})
    for k in ("confirma_numero", "se_fue_del_municipio"):
        if not cuerpo.get(k):
            cuerpo.pop(k, None)
    d = await _pedir(ctx, "POST", f"/api/personas/{a.persona_id}/acercamientos", cuerpo=cuerpo, clave=_clave(ctx))
    d = d if isinstance(d, dict) else {}
    f = minimizar.ficha(d)
    contenido = {"registrado": True, "acercamiento_id": d.get("acercamiento_id"), "persona": _breve(d),
                 **({"abordaje": f["abordaje"]} if "abordaje" in f else {})}
    return Resultado(contenido, f"Acercamiento registrado en la ficha #{a.persona_id}",
                     [*ACCIONES_ESCRITURA, {"tipo": "insignias"}], personas={a.persona_id})


ACERCAMIENTO = Herramienta(
    nombre="registrar_acercamiento",
    descripcion=(
        "Propone registrar un acercamiento (un contacto o intento de contacto) con una persona: canal, resultado y, si "
        "aplica, nota y próximo contacto. Se registra solo si la persona del equipo lo aprueba. El planillero "
        "registra visitas y reuniones; el consultor, llamadas y mensajes, solo a personas de su trabajo que se puedan "
        "contactar. "
        "En llamada, WhatsApp o SMS indica `telefono_indice` (el `indice` del teléfono en ver_persona). `no_contactar` "
        "exige `alcance`; `proximo` y `proximo_franja` solo van con «volver_llamar». Para una nota suelta usa "
        "agregar_nota. Devuelve el abordaje actualizado."),
    entrada=AcercamientoEntrada, tipo="escritura", permisos=("acercamientos.registrar",),
    etiqueta="Registrando el acercamiento", ejecutar=_acercamiento, confirmar=_confirmar_acercamiento,
    esquema=esquema(AcercamientoEntrada))


# ───────────────────────────── registrar_autorizacion ─────────────────────────────

class AutorizacionEntrada(_Entrada):
    persona_id: Id
    estado: Literal["si", "no", "revocada", "pendiente"] = Field(
        ..., description="si, no, revocada o pendiente (pendiente solo administrador y coordinador)")
    medio: Literal[MEDIOS] | None = Field(None, description="Cómo autorizó: planillero escrito, verbal_presencial o "
                                                            "formulario; consultor verbal_telefono o mensaje")
    canales: list[Literal[tuple(modelo.CANALES_AUTORIZACION)]] = Field(
        default_factory=list, max_length=len(modelo.CANALES_AUTORIZACION), description="Canales que autorizó (con si)")
    evidencia: str | None = Field(None, min_length=3, max_length=500, description="Dónde consta: planilla y folio, "
                                                                                 "formulario, grabación…")
    mayor_declarado: bool = Field(False, description="true solo si declaró ser mayor de 18 años")
    nota: str | None = Field(None, min_length=1, max_length=1000)

    @field_validator("canales")
    @classmethod
    def _c(cls, v):
        return _sin_repetidos(v)

    @model_validator(mode="after")
    def _coherente(self):
        if self.canales and self.estado != "si":
            raise ValueError("Los canales solo van con estado si")
        return self


def _exigir_autorizacion(ctx: Contexto, a: AutorizacionEntrada) -> None:
    """Las reglas de `validar_autorizacion` para P y C que dependen solo de la entrada: si falta algo, el modelo lo
    pregunta en vez de proponer algo que la API rechazaría ya aprobado."""
    q = ctx.quien
    if q.administra:
        return
    if a.estado == "pendiente":
        raise ErrorHerramienta("Solo el administrador o el coordinador corrigen una autorización a «pendiente».",
                               "permiso", estado=403)
    if a.estado == "si":
        permitidos = modelo.MEDIOS_POR_ROL.get(q.rol, [])
        faltan = []
        if a.medio not in permitidos:
            faltan.append("el medio (" + ", ".join(permitidos) + ")")
        if not a.evidencia:
            faltan.append("la evidencia (por ejemplo, planilla y folio)")
        if not a.canales:
            faltan.append("al menos un canal autorizado")
        if not a.mayor_declarado:
            faltan.append("que declaró ser mayor de 18 años (mayor_declarado)")
        if faltan:
            raise ErrorHerramienta("Para registrar el «sí» falta " + "; ".join(faltan) + ". Pregúntelo; no lo "
                                   "suponga.", "invalido", estado=422)


async def _confirmar_autorizacion(ctx: Contexto, a: AutorizacionEntrada) -> Confirmacion:
    _exigir_autorizacion(ctx, a)
    d = await _ficha(ctx, a.persona_id)
    if not ctx.quien.administra and d.get("consentimiento") == "no" and a.estado != "si":
        raise ErrorHerramienta("Esta persona ya figura como que no autorizó: su rol solo puede registrar un «sí».",
                               "no_contactable", estado=409)
    antes = d.get("consentimiento") or "pendiente"
    if a.estado == antes and a.estado != "si":
        raise ErrorHerramienta(f"La persona ya figura como «{modelo.ESTADOS_AUTORIZACION[antes]}».", "sin_cambios")
    detalle = [("Persona", _persona(d)),
               ("Autorización", f"{modelo.ESTADOS_AUTORIZACION.get(antes, antes)} → "
                                f"{modelo.ESTADOS_AUTORIZACION[a.estado]}")]
    if a.medio:
        detalle.append(("Medio", modelo.MEDIOS_AUTORIZACION[a.medio]))
    if a.canales:
        detalle.append(("Canales", ", ".join(modelo.CANALES_AUTORIZACION[c] for c in a.canales)))
    if a.evidencia:
        detalle.append(("Evidencia", a.evidencia))
    if a.estado == "si":
        detalle.append(("Declara ser mayor de 18 años", _si_no(a.mayor_declarado)))
    if a.nota:
        detalle.append(("Nota", a.nota))
    aviso = "Registre solo lo que el titular declaró: queda en su historial de autorizaciones (Ley 1581)."
    if a.estado in ("no", "revocada"):
        aviso += " Queda en «no contactar»: el equipo ya no podrá tratar sus datos ni contactarla."
    if a.estado == "revocada":
        aviso += " Se abre una solicitud de revocatoria."
    return Confirmacion(f"Registrar la autorización de {_persona(d)}", detalle, aviso)


async def _autorizacion(ctx: Contexto, a: AutorizacionEntrada) -> Resultado:
    _exigir_autorizacion(ctx, a)
    cuerpo = a.model_dump(exclude_none=True, exclude={"persona_id"})
    d = await _pedir(ctx, "POST", f"/api/personas/{a.persona_id}/autorizacion", cuerpo=cuerpo, clave=_clave(ctx))
    d = d if isinstance(d, dict) else {}
    estado = d.get("consentimiento") or a.estado
    return Resultado({"registrada": True, "consentimiento": estado, "persona": _breve(d) or {"id": a.persona_id}},
                     f"Autorización registrada: {modelo.ESTADOS_AUTORIZACION.get(a.estado, a.estado)}",
                     [*ACCIONES_ESCRITURA, {"tipo": "insignias"}], personas={a.persona_id})


AUTORIZACION = Herramienta(
    nombre="registrar_autorizacion",
    descripcion=(
        "Propone registrar la autorización de tratamiento de datos del titular (Ley 1581): «si», «no», «revocada» o "
        "«pendiente» (esta, solo administrador y coordinador). Registra SOLO lo que la persona del equipo te dicte "
        "que el titular declaró: nunca inventes ni supongas el medio, la evidencia, los canales ni que es mayor de "
        "edad. Un «si» del planillero o del consultor exige el medio de su rol (planillero: escrito, "
        "verbal_presencial o formulario; consultor: verbal_telefono o mensaje), `evidencia`, al menos un canal y "
        "`mayor_declarado: true` solo si lo declaró; si falta algo, pregúntalo antes. Es lo único que se puede "
        "registrar de quien no autorizó (su «sí»). Se registra solo si la persona del equipo lo aprueba."),
    entrada=AutorizacionEntrada, tipo="escritura", permisos=("personas.autorizacion",),
    etiqueta="Registrando la autorización", ejecutar=_autorizacion, confirmar=_confirmar_autorizacion,
    esquema=esquema(AutorizacionEntrada))


# ───────────────────────────── ubicar_persona ─────────────────────────────

class UbicarEntrada(_Entrada):
    persona_id: Id
    lugar_id: Id | None = Field(None, description="Barrio o vereda (id de buscar_lugar)")
    lat: float | None = Field(None, ge=6.3, le=7.5, description="Latitud del punto exacto (con lon)")
    lon: float | None = Field(None, ge=-74.6, le=-73.6, description="Longitud del punto exacto (con lat)")
    automatica: bool = Field(False, description="true: volver a la ubicación automática por su dirección")
    huellas: SkipJsonSchema[dict[str, str] | None] = None  # la del barrio que mostró la tarjeta (`confirmar`)

    @field_validator("huellas")
    @classmethod
    def _h(cls, v):
        return _huellas_validas(v, frozenset({"lugar_id"}))

    @model_validator(mode="after")
    def _una(self):
        if (self.lat is None) != (self.lon is None):
            raise ValueError("lat y lon van juntas")
        formas = sum((self.lugar_id is not None, self.lat is not None, self.automatica))
        if formas != 1:
            raise ValueError("Use exactamente una: lugar_id, lat y lon, o automatica: true")
        return self


def _donde_esta(d: dict) -> str:
    lugar = d.get("lugar_nombre") or d.get("lugar_texto") or "sin barrio ni vereda"
    precision = d.get("geo_precision")
    manual = {"punto": ", punto puesto a mano", "lugar": ", barrio elegido a mano"}.get(d.get("geo_manual") or "", "")
    return f"{lugar}" + (f" (ubicación: {precision}{manual})" if precision else " (sin ubicación)")


async def _confirmar_ubicar(ctx: Contexto, a: UbicarEntrada) -> Confirmacion:
    d = await _ficha(ctx, a.persona_id)
    _exigir_tratable(d)
    detalle = [("Persona", _persona(d)), ("Ahora", _donde_esta(d))]
    aviso = None
    if a.lugar_id is not None:
        if d.get("lugar_id") == a.lugar_id:
            raise ErrorHerramienta("La persona ya está en ese barrio o vereda.", "sin_cambios")
        lg = await run_in_threadpool(_lugar, ctx.db, a.lugar_id)
        if lg is None:
            raise ErrorHerramienta(f"El barrio o vereda #{a.lugar_id} no existe: búsquelo con buscar_lugar.",
                                   "no_existe", estado=404)
        detalle.append(("Barrio o vereda", f"{d.get('lugar_nombre') or '(sin barrio ni vereda)'} → "
                                           f"{lg.get('nombre')} ({lg.get('tipo')})"))
        a.huellas = {"lugar_id": _huella(await _clave_huellas(ctx), "lugar_id", d.get("lugar_id"))}
        aviso = "La persona queda en ese barrio o vereda; un punto puesto a mano en el mapa no se mueve."
    elif a.lat is not None:
        detalle.append(("Punto en el mapa", f"{a.lat:.6f}, {a.lon:.6f}"))
        aviso = "Queda con ubicación manual: un cambio de dirección o una importación no la mueven."
    else:
        if not d.get("geo_manual"):
            raise ErrorHerramienta("La persona ya usa la ubicación automática por su dirección.", "sin_cambios")
        detalle.append(("Ubicación", "manual → automática por su dirección"))
    return Confirmacion(f"Ubicar a {_persona(d)}", detalle, aviso)


async def _ubicar(ctx: Contexto, a: UbicarEntrada) -> Resultado:
    clave = _clave(ctx)
    ruta = f"/api/personas/{a.persona_id}"
    actual = await _ficha(ctx, a.persona_id)
    _exigir_tratable(actual)
    if a.lugar_id is not None:
        if actual.get("lugar_id") == a.lugar_id:  # ya quedó (una repetición): no se escribe ni se audita otra vez
            d = actual
        else:
            _exigir_sin_cambios(actual, a.huellas, ["lugar_id"], await _clave_huellas(ctx), lambda x, c: x.get(c))
            d = await _pedir(ctx, "PATCH", ruta, cuerpo={"lugar_id": a.lugar_id,
                                                         "base": {"lugar_id": actual.get("lugar_id")}}, clave=clave)
    else:
        hecho = (actual.get("geo_manual") == "punto" and actual.get("lat") is not None and actual.get("lon") is not None
                 and round(float(actual["lat"]), 6) == round(a.lat, 6) and round(float(actual["lon"]), 6) ==
                 round(a.lon, 6)) if a.lat is not None else not actual.get("geo_manual")
        if hecho:  # PUT y DELETE no tienen idempotencia en la API: una repetición no escribe ni audita otra vez
            d = actual
        elif a.lat is not None:
            d = await _pedir(ctx, "PUT", f"{ruta}/ubicacion", cuerpo={"lat": a.lat, "lon": a.lon}, clave=clave)
        else:
            d = await _pedir(ctx, "DELETE", f"{ruta}/ubicacion", clave=clave)
    d = d if isinstance(d, dict) else {}
    f = minimizar.ficha(d)
    persona = {**_breve(d), **{k: f[k] for k in ("lugar_nombre", "zona", "geo_precision", "geo_manual") if k in f}}
    return Resultado({"guardado": True, "persona": persona}, f"Ubicación guardada en la ficha #{a.persona_id}",
                     list(ACCIONES_ESCRITURA), personas={a.persona_id})


UBICAR = Herramienta(
    nombre="ubicar_persona",
    descripcion=(
        "Propone ubicar a una persona: en un barrio o vereda (`lugar_id`, el id de buscar_lugar), en un punto exacto "
        "(`lat` y `lon`, por ejemplo donde la persona del equipo la señaló en el mapa) o de vuelta en la ubicación "
        "automática por su dirección (`automatica: true`). Usa exactamente una de las tres. Se guarda solo si la "
        "persona del equipo lo aprueba. No inventes coordenadas: usa solo las que te den."),
    entrada=UbicarEntrada, tipo="escritura", permisos=("personas.ubicar",), etiqueta="Ubicando a la persona",
    ejecutar=_ubicar, confirmar=_confirmar_ubicar, esquema=esquema(UbicarEntrada))


# ───────────────────────────── agregar_telefono ─────────────────────────────

class TelefonoEntrada(_Entrada):
    persona_id: Id
    numero: str = Field(..., min_length=7, max_length=20, description="El número dictado, completo (uno solo)")
    whatsapp: bool | None = Field(None, description="Si tiene WhatsApp (omítelo si no se sabe)")
    principal: bool = Field(False, description="true: pasa a ser el primer número de la ficha")
    nota: str | None = Field(None, min_length=1, max_length=300)

    @field_validator("numero")
    @classmethod
    def _n(cls, v):
        return _un_telefono(v)


async def _confirmar_telefono(ctx: Contexto, a: TelefonoEntrada) -> Confirmacion:
    d = await _ficha(ctx, a.persona_id)
    _exigir_tratable(d)
    detalle = [("Persona", _persona(d)), ("Número", a.numero), ("WhatsApp", _si_no(a.whatsapp)),
               ("Principal", _si_no(a.principal))]
    if a.nota:
        detalle.append(("Nota", a.nota))
    avisos = []
    if any(isinstance(t, dict) and t.get("numero") == a.numero for t in d.get("telefonos") or []):
        avisos.append("Ese número ya está en la ficha: solo se actualizan sus marcas.")
    if not ctx.quien.administra and ctx.quien.rol == "consultor":
        avisos.append("Queda como confirmado: lo dictó el titular.")
    return Confirmacion(f"Agregar un teléfono a {_persona(d)}", detalle, " ".join(avisos) or None)


async def _telefono(ctx: Contexto, a: TelefonoEntrada) -> Resultado:
    cuerpo = a.model_dump(exclude_none=True, exclude={"persona_id"})
    d = await _pedir(ctx, "POST", f"/api/personas/{a.persona_id}/telefonos", cuerpo=cuerpo, clave=_clave(ctx))
    d = d if isinstance(d, dict) else {}
    f = minimizar.ficha(d)
    contenido = {"agregado": True, "persona": _breve(d) or {"id": a.persona_id},
                 **({"telefonos": f["telefonos"]} if "telefonos" in f else {})}
    return Resultado(contenido, f"Teléfono agregado a la ficha #{a.persona_id}", list(ACCIONES_ESCRITURA),
                     personas={a.persona_id})


TELEFONO = Herramienta(
    nombre="agregar_telefono",
    descripcion=(
        "Propone agregar un número de teléfono a la ficha de una persona: el que te dictaron, completo (celular de 10 "
        "dígitos o fijo de 7). Opcional: `whatsapp`, `principal` (pasa a ser el primero) y `nota`. Si el número ya "
        "estaba, solo se actualizan sus marcas. Lo que agrega el consultor queda confirmado. Se guarda solo si la "
        "persona del equipo lo aprueba. No inventes números ni los completes."),
    entrada=TelefonoEntrada, tipo="escritura", permisos=("personas.telefonos",), etiqueta="Agregando un teléfono",
    ejecutar=_telefono, confirmar=_confirmar_telefono, esquema=esquema(TelefonoEntrada))


HERRAMIENTAS: list[Herramienta] = [BUSCAR, VER, PARECIDAS, CREAR, EDITAR, NOTA, ACERCAMIENTO, AUTORIZACION, UBICAR,
                                   TELEFONO]
