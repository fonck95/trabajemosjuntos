"""Herramientas del asistente sobre personas: buscar, ver la ficha y las parecidas (lectura), y crear, editar, agregar
una nota, registrar un acercamiento o una autorización, ubicar y agregar un teléfono (escritura, con aprobación). Con
los datos políticos habilitados (`agente_politicos`), además la lista de líderes y su buscador (lectura), y marcar el
tipo de una persona y asignarle un líder (escritura).

Por qué está hecho así:

* Todo pasa por `ctx.api` (las mismas rutas que usa la interfaz, con la sesión del usuario): los permisos, el alcance
  de P y C, el presupuesto diario, las lecturas, la proyección por rol, `exigir_tratable`, la idempotencia y la
  auditoría son los del panel. Las comprobaciones previas adelantan, con un mensaje claro para el modelo, lo que la
  API rechazaría después de que la persona aprobara la tarjeta (o lo que la interfaz no ofrecería, como una reunión
  ajena), y usan las mismas reglas del panel cuando las hay.
* Lo que llega al modelo pasa por `minimizar` (sin datos sensibles, cédulas ni teléfonos completos, correos ni
  coordenadas) y cada persona servida va en `Resultado.personas` (la conversación se borra si alguna se suprime),
  también los líderes que nombra un «Liderado por». Los errores de la API también se limpian (`_seguro`): un 409 puede
  traer la cédula, el teléfono o el nombre de otra persona.
* Los datos políticos (el tipo de persona, el «Liderado por», las listas y las bases «cedulas» y «general») llegan
  solo con `agente_politicos` encendido para la vía (`Contexto.politicos`: el chat o MCP) y solo los que la API ya le
  da al rol, como en el panel: A y K, todos, con sus filtros y la lista de líderes con sus conteos; P, el tipo y el
  «Liderado por» de las personas de su zona o que registró (`proyeccion.tipo_visible`), y solo suma: marca un tipo y
  asigna un líder, nunca los quita; C, nada. De quien no autorizó, nada político: ni su tipo, ni que lidera a alguien
  (un líder que no autorizó no se nombra, no se filtra por él ni se asigna), y los conteos no lo cuentan. Con el
  ajuste apagado, todo eso queda fuera como antes y estas herramientas no se ofrecen.
* Escrituras: `confirmar` lee la ficha (nombre, autorización y los valores de antes) y arma la tarjeta, sin escribir
  nada. `ejecutar` escribe una sola vez: manda la `Idempotency-Key` del `tool_use` (las rutas POST devuelven la
  respuesta guardada si se repite) y, en las que no la tienen (PATCH, PUT, DELETE), vuelve a leer la ficha y no
  escribe si ya quedó como se pidió. Para saber si alguien cambió la ficha entre la tarjeta y la aprobación, la
  tarjeta deja en la entrada huellas (HMAC) de los valores que mostró, nunca los valores: la entrada pendiente se
  guarda con la conversación.
* De quien no autorizó el tratamiento el asistente no escribe nada salvo su autorización: sus datos no se le pasan al
  modelo, y escribirlos sería tratarlos a través de él. Se hace en la ficha del panel. Al aprobar se vuelve a leer la
  ficha (pudo dejar de autorizar después de la tarjeta), salvo en un reintento de lo ya hecho (`_ya_hecha`). Tampoco
  sale en una búsqueda con filtros o con un orden que diría algo de ella (`revela_datos`), ni por un número.
* La búsqueda libre (`q`) y las parecidas no son un oráculo: las palabras buscan solo en el nombre y un número solo
  entero (`_q_del_asistente`, `estricta=1` en la API); de quien no autorizó, las parecidas solo usan el nombre, también
  las del alta (las que salen por un número no se muestran), y una cédula ocupada por ella no dice de quién es.
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
from collections import Counter
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
from .base import Confirmacion, Contexto, ErrorHerramienta, Herramienta, Resultado, politicos_ofrecidos

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
OCULTOS = {"correo", "fecha_nacimiento", "lider", "votante", "concejal", "lideres", "sensibles", "regimen_salud",
           "consentimiento", "consentimiento_fecha", "observaciones"}


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


CEDULA_DE_QUIEN_NO_AUTORIZO = ("La cédula ya pertenece a otra ficha activa que el asistente no puede mostrar: que la "
                               "persona del equipo la revise en Habitantes del panel antes de seguir.")


def _no_autorizo(db: Any, pid: int) -> bool:
    return db.personas.find_one({"_id": pid, "consentimiento": "no"}, {"_id": 1}) is not None


async def _sin_quien_no_autorizo(ctx: Contexto, e: ErrorHerramienta) -> ErrorHerramienta:
    """`e` (ya pasado por `_seguro`) sin el número de la ficha de quien no autorizó: con él y ver_persona, el modelo
    sabría que esa cédula es de esa persona (una búsqueda por el número ya no la trae)."""
    otro = e.detalle.get("id") if e.codigo == "cedula_ocupada" and isinstance(e.detalle, dict) else None
    if isinstance(otro, int) and await run_in_threadpool(_no_autorizo, ctx.db, otro):
        return ErrorHerramienta(CEDULA_DE_QUIEN_NO_AUTORIZO, e.codigo, estado=e.estado, fatal=e.fatal)
    return e


async def _pedir(ctx: Contexto, metodo: str, ruta: str, *, params: dict | None = None, cuerpo: Any = None,
                 clave: str | None = None) -> Any:
    plazo = ctx.plazo_escritura() if metodo != "GET" else None
    try:
        return await ctx.api.pedir(metodo, ruta, params=params, json_=cuerpo, clave=clave, plazo=plazo)
    except ErrorHerramienta as e:
        raise await _sin_quien_no_autorizo(ctx, _seguro(e)) from None


def _hecha(db: Any, uid: Any, clave: str) -> bool:
    return db.idempotencia.find_one({"_id": f"{uid}:{clave}", "estado": "hecho"}, {"_id": 1}) is not None


async def _ya_hecha(ctx: Contexto, clave: str | None) -> bool:
    """¿La API ya guardó la respuesta de esta escritura (`acceso.idempotencia_previa`, la misma clave del mismo
    `tool_use`)? Entonces es un reintento (la aprobación se repitió tras un turno cortado): se manda tal cual y la API
    devuelve lo guardado, sin volver a revisar una ficha que la primera ejecución pudo cambiar."""
    return bool(clave) and await run_in_threadpool(_hecha, ctx.db, ctx.quien.uid, clave)


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


async def _lugares(ctx: Contexto) -> frozenset[str] | None:
    """Los nombres del nomenclátor (`minimizar.lugares_de`): con ellos se reconoce el barrio o vereda de quien no
    autorizó en las filas y la ficha de planilleros y consultores, que no dicen si `lugar` es del nomenclátor o el
    texto libre. Las del administrador y el coordinador lo dicen: no hacen falta."""
    return None if ctx.quien.administra else await run_in_threadpool(minimizar.lugares_de, ctx.db)


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


# ───────────────────────────── Datos políticos ─────────────────────────────

POLITICOS_APAGADOS = ("Los datos políticos (tipo de persona, «Liderado por», listas y bases de cédulas y general) no "
                      "están habilitados en Ajustes para esta vía (el asistente del panel o los agentes por MCP): el "
                      "administrador los habilita. Se consultan en el panel.")
ROL_SIN_POLITICOS = ("Su rol no filtra ni cuenta por datos políticos (tipo de persona, líderes, listas o las bases de "
                     "cédulas y general): eso es del administrador y el coordinador.")
LIDER_NO_USABLE = ("No hay un líder o concejal con ese id que el asistente pueda usar: búsquelo con lideres (los que "
                   "no autorizaron el tratamiento de sus datos no salen).")


def filtros_politicos(f: Any) -> list[str]:
    """Los filtros políticos que trae una entrada de filtros (también una fuente política)."""
    if f is None:
        return []
    datos = f.model_dump(exclude_none=True)
    usados = [k for k in FILTROS_POLITICOS if k in datos and not (k in _SOLO_SI and datos[k] is False)]
    if datos.get("fuente") in FUENTES_POLITICAS:
        usados.append("fuente")
    return usados


def _lider_usable(db: Any, lid: int) -> bool:
    """¿`lid` es una ficha activa que autorizó y que lidera (marcada como líder o concejal, o que figura como líder de
    alguien, como la lista de líderes)?"""
    l = db.personas.find_one({"_id": lid, **bd.ACTIVA, "consentimiento": {"$ne": "no"}},
                             {t: 1 for t in modelo.TIPOS_LIDERAN})
    if l is None:
        return False
    return modelo.lidera(l) or db.personas.count_documents({**bd.ACTIVA, "lideres.id": lid}, limit=1) > 0


async def exigir_politicos(ctx: Contexto) -> None:
    """403 si los datos políticos no llegan por esta vía (`agente_politicos` apagado)."""
    if not ctx.politicos():
        raise ErrorHerramienta(POLITICOS_APAGADOS, "permiso", estado=403)


async def exigir_filtros_politicos(ctx: Contexto, usados: list[str], lider_id: int | None = None) -> None:
    """Los filtros políticos, como en Habitantes: solo A y K (la API se los veda a P y C, `filtros.VEDADOS`), con
    `agente_politicos` encendido, y nunca por un líder que no autorizó (contar a quienes trajo diría que lidera; el
    mensaje es el mismo para todo id que no sirve: no dice si existe)."""
    if not usados:
        return
    await exigir_politicos(ctx)
    if not ctx.quien.administra:
        raise ErrorHerramienta(ROL_SIN_POLITICOS, "permiso", estado=403, detalle={"campos": usados})
    if lider_id is not None and not await run_in_threadpool(_lider_usable, ctx.db, lider_id):
        raise ErrorHerramienta(LIDER_NO_USABLE, "invalido", estado=422, detalle={"campo": "lider_id"})


def _no_autorizaron(db: Any, ids: set[int]) -> frozenset[int]:
    if not ids:
        return frozenset()
    return frozenset(x["_id"] for x in db.personas.find({"_id": {"$in": sorted(ids)}, "consentimiento": "no"},
                                                        {"_id": 1}))


def traidas_tratables(db: Any, pid: int) -> dict:
    """Lo que trajo el líder `pid` (`{total, compartidas}`, como `api.lideres.traidas_de`) sin quienes no autorizaron
    y sin contar como compartida a la persona cuyo otro líder no autorizó."""
    total = compartidas = 0
    filas = list(db.personas.find({**bd.ACTIVA, "lideres.id": pid, "consentimiento": {"$ne": "no"}},
                                  {"lideres.id": 1}))
    otros = {l.get("id") for x in filas for l in x.get("lideres") or [] if isinstance(l, dict)} - {pid}
    ocultos = _no_autorizaron(db, {i for i in otros if isinstance(i, int)})
    for x in filas:
        total += 1
        compartidas += len({l.get("id") for l in x.get("lideres") or [] if isinstance(l, dict)} - ocultos) > 1
    return {"total": total, "compartidas": compartidas}


async def politicos_de(ctx: Contexto, docs: list[Any], traidas: int | None = None) -> minimizar.Politicos | None:
    """El `minimizar.Politicos` de una respuesta de la API (filas o fichas), o None si los datos políticos no llegan
    por esta vía: los líderes que nombran y no autorizaron (no se nombran) y, con `traidas` (el id de una ficha que
    trae `traidas`), lo que trajo contado sin quienes no autorizaron."""
    if not ctx.politicos():
        return None
    ids = minimizar.ids_lideres(docs)
    no = await run_in_threadpool(_no_autorizaron, ctx.db, ids) if ids else frozenset()
    cuenta = await run_in_threadpool(traidas_tratables, ctx.db, traidas) if traidas is not None else None
    return minimizar.Politicos(no_autorizaron=no, traidas=cuenta)


def ids_mostrados(fs: list[Any]) -> set[int]:
    """Las personas de unas filas o fichas ya minimizadas, con los líderes que nombra su «Liderado por»."""
    return minimizar.ids_de(fs) | minimizar.ids_lideres(fs)


# ───────────────────────────── buscar_personas ─────────────────────────────

# Los filtros políticos de Habitantes (`filtros.VEDADOS` para P y C): solo A y K, con `agente_politicos` encendido
FILTROS_POLITICOS = ("tipo", "lider_id", "varios_lideres", "sin_lider", "lista")
FUENTES = ("tramites", "reunion", "manual", "planilla")
FUENTES_POLITICAS = ("cedulas", "general", "ambas")  # «ambas»: trámites y cédulas
TIPOS_FILTRO = (*modelo.TIPOS_PERSONA, "sin_tipo")
D_TIPO = ("Tipo de persona: concejal, lider, votante o sin_tipo (ninguno). Dato político: solo administrador y "
          "coordinador, si están habilitados")
D_LIDER_ID = "Las que trajo ese líder o concejal (id de lideres). Dato político: solo administrador y coordinador"
D_LISTA = "Lista de origen, con su nombre exacto (de indicadores). Dato político: solo administrador y coordinador"
D_FUENTE = ("De dónde llegó; cedulas, general y ambas (trámites y cédulas) son bases políticas: solo administrador y "
            "coordinador, si están habilitados")


class FiltrosEntrada(_Entrada):
    """Los filtros de Habitantes (`filtros.Filtros`) que el asistente puede usar, con los valores que acepta la API.
    Fuera: `poligono` e `ids` (para el mapa), `regimen_salud` (salud) y las etiquetas sensibles. Los políticos (`tipo`,
    `lider_id`, `varios_lideres`, `sin_lider`, `lista` y las fuentes «cedulas», «general» y «ambas»), solo para A y K y
    con `agente_politicos` encendido (`exigir_filtros_politicos`)."""
    zona: Literal["urbana", "rural", "sin"] | None = Field(None, description="urbana, rural o sin (sin zona)")
    lugar_id: int | None = Field(None, ge=0, le=MAX_ID, description="Barrio o vereda (id de buscar_lugar); 0 = sin "
                                                                     "barrio ni vereda reconocidos")
    area_id: Id | None = Field(None, description="Área de trabajo dibujada en el mapa (el planillero, solo las suyas)")
    fuente: Literal[(*FUENTES, *FUENTES_POLITICAS)] | None = Field(None, description=D_FUENTE)
    tipo: Literal[TIPOS_FILTRO] | None = Field(None, description=D_TIPO)
    lider_id: Id | None = Field(None, description=D_LIDER_ID)
    varios_lideres: bool | None = Field(None, description="true: las que trae más de un líder (dato político)")
    sin_lider: bool | None = Field(None, description="true: las que nadie lidera (dato político)")
    lista: str | None = Field(None, min_length=1, max_length=120, description=D_LISTA)
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
_SOLO_SI = ("tratables", "proximo_vencido", "mios", "varios_lideres", "sin_lider")


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
    q: str | None = Field(None, max_length=120, description="Nombre (o parte; varias palabras se combinan) o un número "
                                                            "entero: la cédula o el teléfono completos")
    filtros: FiltrosEntrada | None = Field(None, description="Filtros de Habitantes (no para el consultor)")
    orden: Literal[ORDENES] | None = Field(
        None, description="nombre (A-Z), completitud (más completas), -completitud (más incompletas), reciente "
                          "(actualizadas), contacto (último contacto), por_llamar (más tiempo sin acercamiento), "
                          "abordaje_reciente o lugar")
    pagina: int = Field(1, ge=1, le=10_000)
    por_pagina: int = Field(20, ge=10, le=50)


NUMERO_EN_BUSQUEDA = re.compile(r"\d{4,}")
SIN_DIGITOS_ENMASCARADOS = ("Búsqueda por número: las filas no traen los dígitos enmascarados de cédula ni teléfono "
                            "(abra la ficha si hace falta).")
NUMERO_INCOMPLETO = ("Un número se busca entero y solo: la cédula completa o el teléfono completo (10 dígitos, o 7 si "
                     "es fijo), sin letras ni partes de otro número. Para buscar por nombre, escriba solo el nombre. "
                     "La búsqueda no mira la dirección ni el sitio escrito: para un barrio o vereda, use "
                     "filtros.lugar_id (con buscar_lugar).")
# Unas palabras que no encuentran a nadie: no es que no haya nadie, es que `q` busca solo en el nombre (Habitantes del
# panel también busca en la dirección y el sitio escrito: si la vista trae esa búsqueda, ahí sí salen)
SOLO_EN_EL_NOMBRE = ("`q` busca las palabras solo en el nombre: no mira la dirección, el sitio escrito ni el correo. "
                     "Para un barrio o vereda, use filtros.lugar_id (con buscar_lugar); para una dirección, la persona "
                     "del equipo la busca en Habitantes del panel.")


def _q_del_asistente(q: str | None) -> tuple[str | None, bool]:
    """(`q` como va a la API, si es un número). La API la busca con `estricta=1` (`filtros.q_estricta`): las palabras,
    solo en el nombre, y un número, solo entero, nunca con quien no autorizó. La búsqueda libre de Habitantes compara
    además la dirección, el correo y partes de los números: desde el asistente, que una búsqueda case o no sería una
    respuesta sobre un dato que el modelo no recibe (la dirección o el correo de quien no autorizó, los dígitos
    enmascarados de una cédula o un teléfono), y unas cuantas búsquedas lo reconstruirían. Un número escrito por
    grupos o con el indicativo se junta; uno incompleto, o con letras, es un error que dice cómo buscar."""
    if not q or not re.search(r"\d", q):
        return q, False
    if re.sub(r"[\d\s.()+\-]", "", q):
        raise ErrorHerramienta(NUMERO_INCOMPLETO, "invalido", estado=422)
    telefonos = tx.telefonos(q)
    numero = telefonos[0] if len(telefonos) == 1 else tx.cedula(re.sub(r"\D", "", q))
    if not numero:
        raise ErrorHerramienta(NUMERO_INCOMPLETO, "invalido", estado=422)
    return numero, True


def _sin_digitos_enmascarados(fs: list[dict], q: str | None) -> tuple[list[dict], bool]:
    """En una búsqueda con un número las filas van sin los últimos dígitos enmascarados (`cedula_ult3`,
    `telefono_mascara`). La API ya compara el número entero (`_q_del_asistente`), así que no le suman nada al que
    escribió la persona; pero si alguna vez casara una parte, juntarla con el final reconstruiría una cédula o un
    teléfono que se enmascaró a propósito. El resultado sigue diciendo quién coincide con el número."""
    if not NUMERO_EN_BUSQUEDA.search(q or ""):
        return fs, False
    return [{k: v for k, v in f.items() if k not in ("cedula_ult3", "telefono_mascara")} for f in fs], True


def _busca_lista(a: BuscarEntrada) -> bool:
    return bool(params_filtros(a.filtros)) or a.orden is not None or a.pagina > 1 or "por_pagina" in \
        a.model_fields_set or not a.q


# De quien no autorizó al modelo le llega solo quién es y su barrio o vereda (`minimizar.no_autorizo`). Una lista con
# otro filtro (sexo, edad, una necesidad, lo que le falta…), con un orden que no sea por nombre o con un número le
# diría más: cada filtro que casa es un dato suyo, el número, que es suyo, y su puesto en la lista, cuán completa está
# su ficha o entre qué direcciones queda la suya (el orden «lugar» ordena por la dirección dentro del lugar). Por eso,
# con esos filtros, órdenes o números, la lista va sin quienes no autorizaron (`tratables`), y combinarlos con
# `consentimiento: no` no se puede. Su nombre sí: es quién es
FILTROS_SIN_DATOS = frozenset({"consentimiento", "lugar_id", "zona"})
ORDENES_SIN_DATOS = (None, "nombre")
SIN_NO_AUTORIZARON = ("Sin quienes no autorizaron el tratamiento de sus datos: con filtros, con ese orden o con un "
                      "número, el asistente no los cuenta ni los ve. En Habitantes del panel sí salen.")
NO_AUTORIZO_CON_FILTROS = ("De quien no autorizó el tratamiento de sus datos el asistente solo sabe quién es y su "
                           "barrio o vereda: con consentimiento «no» busque solo por el nombre, con lugar_id o zona, "
                           "ordenado por nombre. Para lo demás, la persona del equipo abre Habitantes en el panel.")


def revela_datos(campos: set[str], orden: str | None, sin_datos: frozenset[str] = FILTROS_SIN_DATOS) -> bool:
    """¿Esos filtros (los nombres de los que trae la entrada) o ese orden dirían algo de quien no autorizó?"""
    return bool(campos - sin_datos) or orden not in ORDENES_SIN_DATOS


def campos_de(f: Any) -> set[str]:
    """Los filtros que de verdad trae una entrada de filtros: sin los vacíos ni las banderas que solo valen con true
    (`tratables: false` no filtra nada)."""
    if f is None:
        return set()
    return {k for k, v in f.model_dump(exclude_none=True).items()
            if v not in ([], "") and not (k in _SOLO_SI and v is False)}


def _resumen_conteo(n: int, pagina: int | None = None, paginas: int | None = None) -> str:
    base = "Sin resultados" if n == 0 else "1 persona" if n == 1 else f"{_miles(n)} personas"
    return f"{base} · página {pagina} de {paginas}" if n and paginas and paginas > 1 else base


async def _buscar(ctx: Contexto, a: BuscarEntrada) -> Resultado:
    quien = ctx.quien
    q, por_numero = _q_del_asistente(a.q)
    if a.filtros is not None and a.filtros.etiqueta is not None:
        if a.filtros.etiqueta in (await _sensibles(ctx)).etiquetas:
            raise ErrorHerramienta("Esa etiqueta revela un dato sensible: el asistente no filtra por ella.", "permiso",
                                   estado=403)
    if _busca_lista(a):
        if not quien.puede("personas.listar"):
            raise ErrorHerramienta(
                "Su rol no lista ni filtra la base: busque por nombre (3 letras o más) o por el número completo de 10 "
                "dígitos, o trabaje su cola en Mi trabajo.", "permiso", estado=403)
        await exigir_filtros_politicos(ctx, filtros_politicos(a.filtros), a.filtros.lider_id if a.filtros else None)
        sin_ellos = por_numero or revela_datos(campos_de(a.filtros), a.orden)
        if sin_ellos and a.filtros is not None and a.filtros.consentimiento == "no":
            raise ErrorHerramienta(NO_AUTORIZO_CON_FILTROS, "invalido", estado=422)
        params = {"q": q, "estricta": 1 if q else None, **params_filtros(a.filtros), "orden": a.orden or "nombre",
                  "pagina": a.pagina, "por_pagina": a.por_pagina}
        if sin_ellos:
            params["tratables"] = 1
        d = await _pedir(ctx, "GET", "/api/personas", params=params)
        d = d if isinstance(d, dict) else {}
        crudas = d.get("filas") or []
        pol = await politicos_de(ctx, crudas)
        fs, numerica = _sin_digitos_enmascarados(minimizar.filas(crudas, await _lugares(ctx), pol), q)
        total, pp = int(d.get("total") or 0), int(d.get("por_pagina") or a.por_pagina)
        paginas = max(1, math.ceil(total / pp)) if pp else 1
        contenido = {"tipo": "lista", "total": total, "pagina": d.get("pagina", a.pagina), "por_pagina": pp,
                     "paginas": paginas, "filas": fs}
        if numerica:
            contenido["nota"] = SIN_DIGITOS_ENMASCARADOS
        elif q and not total:
            contenido["nota"] = SOLO_EN_EL_NOMBRE
        if sin_ellos:
            contenido["nota_autorizacion"] = SIN_NO_AUTORIZARON
        if not quien.administra:
            contenido["alcance"] = "Solo personas de su zona asignada (si tiene una)."
        return Resultado(contenido, _resumen_conteo(total, contenido["pagina"], paginas), personas=ids_mostrados(fs))
    d = await _pedir(ctx, "GET", "/api/buscar", params={"q": q, "estricta": 1})
    crudas = d if isinstance(d, list) else []
    pol = await politicos_de(ctx, crudas)
    fs, numerica = _sin_digitos_enmascarados(minimizar.filas(crudas, await _lugares(ctx), pol), q)
    contenido = {"tipo": "busqueda_rapida", "total": len(fs), "pagina": 1, "filas": fs}
    if numerica:
        contenido["nota"] = SIN_DIGITOS_ENMASCARADOS
    elif not fs and len((a.q or "").strip()) >= 2:
        contenido["nota"] = SOLO_EN_EL_NOMBRE
    if por_numero:
        contenido["nota_autorizacion"] = SIN_NO_AUTORIZARON
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
    return Resultado(contenido, _resumen_conteo(len(fs)), personas=ids_mostrados(fs))


BUSCAR = Herramienta(
    nombre="buscar_personas",
    descripcion=(
        "Busca habitantes: una persona por su nombre o por su cédula o teléfono completos, o listas y conteos con "
        "filtros (barrio o vereda, autorización, abordaje, datos que faltan, edad, votación…). No es para el detalle "
        "de una persona (ver_persona) ni para indicadores. `q` busca las palabras solo en el nombre y un "
        "número solo entero, nunca una parte.\n"
        "- Solo `q`: búsqueda rápida en toda la base; hasta 12 coincidencias (el consultor: hasta 10 por nombre de 3 "
        "letras o más, o 3 por un número completo de 10 dígitos; no usa filtros).\n"
        "- Con `filtros`, `orden`, `pagina` o `por_pagina` (administrador, coordinador y planillero): lista paginada "
        "con el `total`; el planillero solo ve su zona asignada.\n"
        "Cada fila trae id, nombre, lugar, autorización, abordaje, completitud y lo que le falta; cédula y teléfono "
        "enmascarados («···123», «···2233»): no intentes reconstruirlos. Con los datos políticos habilitados, al "
        "administrador y al coordinador les trae el tipo (lider, votante, concejal), el «Liderado por» y las fuentes, "
        "y filtran por tipo, lider_id, varios_lideres, sin_lider, lista y las fuentes cedulas, general o ambas. De "
        "quien no autorizó solo sale que no autorizó: con un número, con filtros (salvo barrio o vereda) o con un "
        "orden que no sea por nombre, la lista no lo trae ni lo cuenta; para saber quiénes no autorizaron, filtra "
        "solo por `consentimiento: no`. `por_pagina` de 10 a 50. Cada persona mostrada cuenta en el tope diario de "
        "P y C: para contar, usa el total de la primera página."),
    entrada=BuscarEntrada, tipo="lectura", permisos=("personas.buscar",), etiqueta="Buscando habitantes",
    ejecutar=_buscar, esquema=esquema(BuscarEntrada), mcp="lectura")


# ───────────────────────────── ver_persona ─────────────────────────────

class VerEntrada(_Entrada):
    persona_id: Id = Field(..., description="Id de la persona (de buscar_personas o del contexto del panel)")


async def _ver(ctx: Contexto, a: VerEntrada) -> Resultado:
    d = await _ficha(ctx, a.persona_id)
    pol = None if d.get("consentimiento") == "no" else await politicos_de(
        ctx, [d], traidas=a.persona_id if d.get("traidas") is not None else None)
    f = minimizar.ficha(d, await _sensibles(ctx), await _lugares(ctx), pol)
    resumen = f"#{f.get('id')}: no autorizó" if f.get("consentimiento") == "no" else _persona(f)
    return Resultado(f, resumen, personas={a.persona_id} | ids_mostrados([f]))


VER = Herramienta(
    nombre="ver_persona",
    descripcion=(
        "Abre la ficha de una persona por su id. Úsala cuando necesites su detalle: autorización y canales, abordaje y "
        "últimos acercamientos, notas recientes, votación, lo que le falta y qué campos se pueden editar. Devuelve la "
        "ficha reducida: sin datos sensibles, con la cédula enmascarada y cada teléfono con su estado, su "
        "número enmascarado y su `indice` (el que pide registrar_acercamiento). Si los datos políticos están "
        "habilitados trae también lo que el panel le muestra a su rol: el tipo de persona, el «Liderado por» y, al "
        "administrador y al coordinador, las listas, las fuentes y lo que trajo si es líder. De quien no autorizó solo "
        "sale que no "
        "autorizó. Cuenta en el tope diario del planillero y del consultor. El consultor solo abre fichas de su "
        "trabajo (tomadas de su cola o con un acercamiento suyo reciente), nunca de menores."),
    entrada=VerEntrada, tipo="lectura", permisos=("personas.ver",), etiqueta="Consultando la ficha", ejecutar=_ver,
    esquema=esquema(VerEntrada), mcp="lectura")


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
    # `estricta`: a quien no autorizó solo lo trae su nombre, y de ella solo se usa su nombre. Que saliera porque su
    # cédula o su teléfono coinciden con los escritos (o que otra ficha saliera porque comparte los suyos) diría que
    # ese número es suyo: con un número tras otro, el modelo los probaría
    if a.persona_id is not None:
        d = await _pedir(ctx, "GET", f"/api/personas/{a.persona_id}/parecidas", params={"estricta": 1})
    else:
        d = await _pedir(ctx, "GET", "/api/parecidas", params={"nombre": a.nombre, "cedula": a.cedula,
                                                                "telefono": a.telefono, "estricta": 1})
    crudas = d if isinstance(d, list) else []
    fs = minimizar.filas(crudas, await _lugares(ctx), await politicos_de(ctx, crudas))
    contenido = {"total": len(fs), "parecidas": fs,
                 "nota": "parecido va de 0 a 100; cedula_distinta: true quiere decir que son personas distintas."}
    n = len(fs)
    resumen = "Sin fichas parecidas" if not n else "1 ficha parecida" if n == 1 else f"{n} fichas parecidas"
    personas = ids_mostrados(fs) | ({a.persona_id} if a.persona_id else set())
    return Resultado(contenido, resumen, personas=personas)


PARECIDAS = Herramienta(
    nombre="personas_parecidas",
    descripcion=(
        "Busca fichas que podrían ser la misma persona (posibles duplicados): con `persona_id`, las parecidas a esa "
        "ficha; con `nombre` (y `cedula` y `telefono` si los tienes), antes de crear una ficha nueva. Devuelve hasta 8 "
        "filas con `parecido` (0 a 100), `tiene_cedula` y `cedula_distinta`. Quien no autorizó el tratamiento de sus "
        "datos sale solo por un nombre muy parecido, nunca por la cédula o el teléfono. Úsala antes de crear_persona "
        "si no estás seguro de que la persona no exista. Unir fichas no se hace aquí: es del administrador, en "
        "Calidad."),
    entrada=ParecidasEntrada, tipo="lectura", permisos=("personas.parecidas",), etiqueta="Buscando fichas parecidas",
    ejecutar=_parecidas, esquema=esquema(ParecidasEntrada), mcp="lectura")


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


# Desde 0,80 la API da una parecida por el nombre (`api.personas._parecidas`); `parecido` llega redondeado de 0 a 100,
# y un 80 puede ser 0,795: ante la duda, no se muestra
PARECIDO_NOMBRE = 80
PARECIDA_OCULTA = ("Hay una coincidencia que el asistente no puede mostrar (de quien no autorizó el tratamiento de sus "
                   "datos): antes de proponer forzar: true, que la persona del equipo la revise en Habitantes del "
                   "panel con los datos que dictó.")


def _por_el_nombre(c: dict) -> bool:
    p = c.get("parecido")
    return isinstance(p, (int, float)) and not isinstance(p, bool) and p > PARECIDO_NOMBRE


async def _crear(ctx: Contexto, a: CrearEntrada) -> Resultado:
    await _revisar_crear(ctx, a)
    try:
        d = await ctx.api.pedir("POST", "/api/personas", json_=_cuerpo_crear(a), clave=_clave(ctx),
                                plazo=ctx.plazo_escritura())
    except ErrorHerramienta as e:
        if e.codigo != "parecidas":
            raise await _sin_quien_no_autorizo(ctx, _seguro(e)) from None
        candidatas = e.detalle.get("parecidas") if isinstance(e.detalle, dict) else None
        candidatas = [c for c in candidatas if isinstance(c, dict)] if isinstance(candidatas, list) else []
        # La API (sin `estricta`: el alta no crea un duplicado por no mostrarlo) trae también a quien no autorizó por
        # coincidir en un número: que saliera diría que ese número es suyo. Como en personas_parecidas, de ella solo
        # cuenta un nombre muy parecido; la que salió por el número no se muestra y la persona del equipo la revisa
        ocultas = [c for c in candidatas if c.get("consentimiento") == "no" and not _por_el_nombre(c)]
        visibles = [c for c in candidatas if c not in ocultas]
        fs = minimizar.filas(visibles, await _lugares(ctx), await politicos_de(ctx, visibles))
        contenido = {"creada": False, "codigo": "parecidas", "parecidas": fs, "mensaje": (
            "No se creó: ya hay fichas parecidas. Muéstrelas y pregunte si es alguna de ellas; solo si la persona del "
            "equipo confirma que es otra persona, proponga crearla de nuevo con forzar: true." if fs else
            "No se creó: el panel encontró una ficha parecida que el asistente no puede mostrar.")}
        if ocultas:
            contenido["nota"] = PARECIDA_OCULTA
        n = len(fs)
        resumen = (f"No se creó: {n} ficha{'s' if n != 1 else ''} parecida{'s' if n != 1 else ''}" if n else
                   "No se creó: hay una ficha parecida")
        return Resultado(contenido, resumen, personas=ids_mostrados(fs))
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
    ejecutar=_crear, confirmar=_confirmar_crear, esquema=esquema(CrearEntrada), mcp="escritura")


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


def _igual(campo: str, actual: Any, nuevo: Any, exacto: bool = False) -> bool:
    """¿El cambio deja el valor como ya está? Con `exacto` (modo reemplazar, una corrección) se compara como la API
    (`poner`): el nombre como se guarda (`nombre_visible`, con sus tildes) y los demás textos tal cual, así se pueden
    corregir tildes y mayúsculas. Sin él (modo completar) una variante con otras tildes o mayúsculas no es un dato
    nuevo: ni lo llena ni queda como alterno."""
    if _vacio(actual):
        return False
    if campo == "nombre":
        if exacto:
            return tx.nombre_visible(actual) == tx.nombre_visible(nuevo)
        return tx.nombre_norm(actual) == tx.nombre_norm(nuevo)
    if campo == "cedula":
        return re.sub(r"[\W_]", "", str(actual)).upper() == re.sub(r"[\W_]", "", str(nuevo)).upper()
    if campo == "mesa":
        return str(actual).strip() == str(nuevo) or modelo.normalizar_mesa(actual) == nuevo
    if isinstance(actual, str) and isinstance(nuevo, str):
        if exacto and campo != "puesto_texto":  # el puesto escrito se reconoce contra el catálogo: no es literal
            return actual.strip() == nuevo.strip()
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
        if campo == "nombre":
            despues = tx.nombre_visible(nuevo)  # como queda guardado (`_limpiar_simple` de la API)
        antes = _mostrar(campo, actual, antes=True)
        if campo == "puesto_id" and not _vacio(actual):
            antes = _mostrar(campo, _votacion(d).get("puesto_nombre") or actual)
        if _igual(campo, actual, nuevo, exacto=a.modo == "reemplazar"):
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
    ejecutar=_editar, confirmar=_confirmar_editar, esquema=esquema(EditarEntrada), mcp="escritura")


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


async def _tratable_al_escribir(ctx: Contexto, pid: int, clave: str | None) -> dict | None:
    """La ficha recién leída, si la persona sigue tratable al aprobar (pudo decir que no autoriza después de la
    tarjeta; la API no frena a A ni a K). None si es un reintento de una escritura ya hecha (`_ya_hecha`)."""
    if await _ya_hecha(ctx, clave):
        return None
    d = await _ficha(ctx, pid)
    _exigir_tratable(d)
    return d


async def _nota(ctx: Contexto, a: NotaEntrada) -> Resultado:
    clave = _clave(ctx)
    if await _tratable_al_escribir(ctx, a.persona_id, clave) is not None:
        await _reunion_visible(ctx, a.reunion_id)  # la API guarda el id sin revisar que la reunión sea visible
    d = await _pedir(ctx, "POST", f"/api/personas/{a.persona_id}/notas",
                     cuerpo={"texto": a.texto, "reunion_id": a.reunion_id}, clave=clave)
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
    ejecutar=_nota, confirmar=_confirmar_nota, esquema=esquema(NotaEntrada), mcp="escritura")


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
        None, description="Obligatorio con solicitud_derechos: qué pidió sobre sus datos (consulta, correccion, "
                          "supresion u otro); pregúntalo si no lo dijeron")
    # La huella del número que mostró la tarjeta: la pone `confirmar` (el modelo no la ve). Al aprobar se marca ese
    # número, aunque su `indice` haya cambiado
    huellas: SkipJsonSchema[dict[str, str] | None] = None

    @field_validator("proximo")
    @classmethod
    def _p(cls, v):
        return _fecha(v, futura=True)

    @field_validator("huellas")
    @classmethod
    def _h(cls, v):
        return _huellas_validas(v, frozenset({"telefono"}))

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
        if r == "solicitud_derechos" and not self.solicitud_tipo:
            raise ValueError("Con solicitud_derechos indique solicitud_tipo (consulta, correccion, supresion u otro): "
                             "el tipo decide el plazo legal. Si no lo dijeron, pregúntelo")
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


def _usables(d: dict) -> list[dict]:
    """Los teléfonos usables de la ficha, con su `indice` (el de `_telefono_elegido` de la API)."""
    return [t for t in d.get("telefonos") or [] if isinstance(t, dict) and isinstance(t.get("indice"), int)]


MENSAJE_NUMERO_CAMBIADO = ("El número que mostró la tarjeta ya no está entre los que se pueden usar en la ficha (otra "
                           "persona lo cambió): no se registró nada. Vuelva a leer la ficha y, si hace falta, proponga "
                           "el acercamiento de nuevo.")


async def _confirmar_acercamiento(ctx: Contexto, a: AcercamientoEntrada) -> Confirmacion:
    _exigir_canal(ctx, a)
    d = await _ficha(ctx, a.persona_id)
    _exigir_tratable(d)
    detalle = [("Persona", _persona(d)), ("Canal", modelo.CANALES[a.canal])]
    if a.telefono_indice is not None:
        t = next((t for t in _usables(d) if t.get("indice") == a.telefono_indice), None)
        if t is None:
            usables = sorted(t.get("indice") for t in _usables(d))
            raise ErrorHerramienta(f"La ficha no tiene un número usable con indice {a.telefono_indice}"
                                   + (f" (los usables: {usables})." if usables else ": no tiene números usables."),
                                   "invalido", estado=422)
        detalle.append(("Número", acceso.enmascarar_telefono(t.get("numero")) or "(sin número)"))
        a.huellas = {"telefono": _huella(await _clave_huellas(ctx), "telefono", t.get("numero"))}
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
        detalle.append(("Qué pidió", f"{modelo.TIPOS_SOLICITUD[a.solicitud_tipo]} · plazo de "
                                     f"{modelo.PLAZOS_SOLICITUD[a.solicitud_tipo]} días hábiles"))
    if a.nota:
        detalle.append(("Nota", a.nota))
    return Confirmacion(f"Registrar un acercamiento con {_persona(d)}", detalle, _aviso_acercamiento(a))


async def _numero_de_la_tarjeta(ctx: Contexto, d: dict, huella: str) -> str:
    """El número usable de la ficha recién leída que mostró la tarjeta (por su huella): su `indice` pudo correrse
    entre la tarjeta y la aprobación (un número nuevo como principal, otro marcado como equivocado)."""
    clave = await _clave_huellas(ctx)
    t = next((t for t in _usables(d) if _huella(clave, "telefono", t.get("numero")) == huella), None)
    if t is None or not t.get("numero"):
        raise ErrorHerramienta(MENSAJE_NUMERO_CAMBIADO, "cambiada", estado=409, detalle={"campos": ["telefono"]})
    return str(t["numero"])


async def _acercamiento(ctx: Contexto, a: AcercamientoEntrada) -> Resultado:
    _exigir_canal(ctx, a)
    clave = _clave(ctx)
    cuerpo = a.model_dump(exclude_none=True, exclude={"persona_id", "huellas"})
    for k in ("confirma_numero", "se_fue_del_municipio"):
        if not cuerpo.get(k):
            cuerpo.pop(k, None)
    d = await _tratable_al_escribir(ctx, a.persona_id, clave)
    if d is not None and a.telefono_indice is not None and (a.huellas or {}).get("telefono"):
        # Se manda el número (la API lo acepta en `telefono`), no el índice: es el que la persona vio y aprobó
        cuerpo.pop("telefono_indice")
        cuerpo["telefono"] = await _numero_de_la_tarjeta(ctx, d, a.huellas["telefono"])
    d = await _pedir(ctx, "POST", f"/api/personas/{a.persona_id}/acercamientos", cuerpo=cuerpo, clave=clave)
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
        "exige `alcance`; `solicitud_derechos`, `solicitud_tipo` (consulta, correccion, supresion u otro: pregúntalo "
        "si no lo dijeron); `proximo` y `proximo_franja` solo van con «volver_llamar». Para una nota suelta usa "
        "agregar_nota. Devuelve el abordaje actualizado."),
    entrada=AcercamientoEntrada, tipo="escritura", permisos=("acercamientos.registrar",),
    etiqueta="Registrando el acercamiento", ejecutar=_acercamiento, confirmar=_confirmar_acercamiento,
    esquema=esquema(AcercamientoEntrada), mcp="escritura")


# ───────────────────────────── registrar_autorizacion ─────────────────────────────

class AutorizacionEntrada(_Entrada):
    persona_id: Id
    estado: Literal["si", "no", "revocada", "pendiente"] = Field(
        ..., description="si, no, revocada o pendiente (pendiente solo administrador y coordinador)")
    medio: Literal[MEDIOS] | None = Field(None, description="Cómo autorizó (obligatorio con si): planillero escrito, "
                                                            "verbal_presencial o formulario; consultor "
                                                            "verbal_telefono o mensaje")
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


def _exigir_autorizacion(ctx: Contexto, a: AutorizacionEntrada, previo: str | None = None) -> None:
    """Las reglas de `validar_autorizacion` para P y C que dependen solo de la entrada: si falta algo, el modelo lo
    pregunta en vez de proponer algo que la API rechazaría ya aprobado. A y K también dicen el medio y los canales de
    un «sí»: sin ellos la API lo registraría como «del panel» con llamada, WhatsApp y SMS implícitos, canales que nadie
    dictó ni vio en la tarjeta."""
    q = ctx.quien
    if q.administra:
        faltan = []
        if a.estado == "si" and a.medio is None:
            faltan.append("el medio (" + ", ".join(MEDIOS) + ")")
        if a.estado == "si" and not a.canales:
            faltan.append("al menos un canal autorizado")
        if faltan:
            raise ErrorHerramienta("Para registrar el «sí» falta " + "; ".join(faltan) + ". Pregúntelo; no lo "
                                   "suponga.", "invalido", estado=422)
        return
    if a.estado == "pendiente":
        raise ErrorHerramienta("Solo el administrador o el coordinador corrigen una autorización a «pendiente».",
                               "permiso", estado=403)
    if a.estado == "si":
        permitidos = modelo.MEDIOS_POR_ROL.get(q.rol, [])
        faltan = []
        if a.medio is not None and a.medio not in permitidos:
            faltan.append("el medio (" + ", ".join(permitidos) + ")")
        # El planillero registra el «sí» sin medio, evidencia, canales ni «mayor de 18» obligatorios (como en el
        # panel), salvo para quien dijo «no» (`previo`)
        if q.rol != "planillero" or previo == "no":
            if a.medio is None:
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
    if d.get("consentimiento") == "no":  # devolverle el «sí» a quien dijo «no» sigue con todos los pasos
        _exigir_autorizacion(ctx, a, "no")
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
    elif a.estado == "si" and ctx.quien.rol == "planillero" and not ctx.quien.administra:
        detalle.append(("Medio", modelo.MEDIOS_AUTORIZACION["verbal_presencial"]))  # el que registra la API
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
        "edad. El «si» del administrador, del coordinador y del consultor exige el `medio` y al menos un canal en "
        "`canales`; el del consultor, además, el medio de su rol (verbal_telefono o mensaje), `evidencia` y "
        "`mayor_declarado: true` solo si lo declaró; si falta algo, pregúntalo antes. El «si» del planillero va sin "
        "más pasos: el medio de su rol (escrito, verbal_presencial o formulario; si no lo dice, verbal_presencial), "
        "los canales, la evidencia y `mayor_declarado` son opcionales; no los preguntes, pero pon los que te dicte. "
        "Es lo único que se puede registrar de quien no autorizó (su «sí»), y ese «sí» sigue exigiendo medio, "
        "canales, evidencia y `mayor_declarado` también al planillero. Se registra solo si la persona del equipo lo "
        "aprueba."),
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
    ejecutar=_ubicar, confirmar=_confirmar_ubicar, esquema=esquema(UbicarEntrada), mcp="escritura")


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
    clave = _clave(ctx)
    await _tratable_al_escribir(ctx, a.persona_id, clave)
    cuerpo = a.model_dump(exclude_none=True, exclude={"persona_id"})
    d = await _pedir(ctx, "POST", f"/api/personas/{a.persona_id}/telefonos", cuerpo=cuerpo, clave=clave)
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
    ejecutar=_telefono, confirmar=_confirmar_telefono, esquema=esquema(TelefonoEntrada), mcp="escritura")


# ───────────────────────────── lideres ─────────────────────────────

TIPOS_LIDER = {"concejal": "Concejal", "lider": "Líder"}
NOTA_LIDERES = ("Los conteos no cuentan a quienes no autorizaron el tratamiento de sus datos, y los líderes que no "
                "autorizaron no salen: por eso pueden diferir de la lista de líderes del panel. traidas: cuántas "
                "personas trajo; votantes: cuántas de ellas son votantes; compartidas: cuántas trae también otro "
                "líder.")


class LideresEntrada(_Entrada):
    q: str | None = Field(None, min_length=3, max_length=120,
                          description="Buscar un líder o concejal por nombre (3 letras o más) o por su cédula "
                                      "completa. Sin q: la lista de líderes con sus conteos (administrador y "
                                      "coordinador)")
    pagina: int = Field(1, ge=1, le=1000)
    por_pagina: int = Field(30, ge=5, le=100)


def _conteos_lideres(db: Any, visibles: set[int]) -> tuple[Counter, Counter, Counter, int]:
    """(traidas, votantes, compartidas, personas con varios líderes) como `api.lideres.listar`, sin quienes no
    autorizaron y contando solo los líderes `visibles` (los que autorizaron)."""
    traidas, votantes, compartidas = Counter(), Counter(), Counter()
    varias = 0
    for x in db.personas.find({**bd.ACTIVA, "lideres.0": {"$exists": True}, "consentimiento": {"$ne": "no"}},
                              {"lideres.id": 1, "votante": 1}):
        ids = {l.get("id") for l in x.get("lideres") or [] if isinstance(l, dict)} & visibles
        varias += len(ids) > 1
        for i in ids:
            traidas[i] += 1
            compartidas[i] += len(ids) > 1
            votantes[i] += x.get("votante") is True
    return traidas, votantes, compartidas, varias


def _fila_lider(l: dict) -> dict:
    out = {"id": l.get("id"), "nombre": l.get("nombre"), "tipo": l.get("tipo"),
           "lugar": minimizar.texto_libre(l.get("lugar"), minimizar.LUGAR_MAX) if l.get("lugar") else None,
           "cedula_ult3": l.get("cedula_ult3") or acceso.enmascarar_cedula(l.get("cedula"))}
    if isinstance(l.get("marcado"), bool):
        out["marcado"] = l["marcado"]
    return {k: v for k, v in out.items() if v is not None}


async def _lideres(ctx: Contexto, a: LideresEntrada) -> Resultado:
    await exigir_politicos(ctx)
    if a.q:
        q, por_numero = _q_del_asistente(a.q)
        d = await _pedir(ctx, "GET", "/api/lideres/candidatos", params={"q": q})
        crudas = [x for x in (d.get("lideres") if isinstance(d, dict) else None) or [] if isinstance(x, dict)]
        # A y K reciben también a los que no autorizaron (P no): que lideran es un dato suyo
        ocultos = await run_in_threadpool(_no_autorizaron, ctx.db, {x.get("id") for x in crudas
                                                                     if isinstance(x.get("id"), int)})
        filas = [_fila_lider(x) for x in crudas if x.get("id") not in ocultos]
        if por_numero:
            filas = [{k: v for k, v in f.items() if k != "cedula_ult3"} for f in filas]
        contenido = {"tipo": "busqueda_lideres", "total": len(filas), "lideres": filas,
                     "nota": "Para asignar uno: asignar_lider con su id. Los que no autorizaron no salen."}
        if not filas:
            contenido["aviso"] = ("Ningún líder o concejal casa con eso: busque por el nombre (3 letras o más) o la "
                                  "cédula completa.")
        n = len(filas)
        return Resultado(contenido, "Sin líderes" if not n else "1 líder" if n == 1 else f"{n} líderes",
                         personas=minimizar.ids_de(filas))
    if not ctx.quien.puede("admin"):
        raise ErrorHerramienta("La lista de líderes con sus conteos es del administrador y el coordinador: busque un "
                               "líder por su nombre con q.", "permiso", estado=403)
    d = await _pedir(ctx, "GET", "/api/lideres")
    crudas = [x for x in (d.get("lideres") if isinstance(d, dict) else None) or [] if isinstance(x, dict)
              and isinstance(x.get("id"), int)]
    ocultos = await run_in_threadpool(_no_autorizaron, ctx.db, {x["id"] for x in crudas})
    visibles = [x for x in crudas if x["id"] not in ocultos]
    traidas, votantes, compartidas, varias = await run_in_threadpool(_conteos_lideres, ctx.db,
                                                                     {x["id"] for x in visibles})
    filas = [{**_fila_lider(x), "traidas": traidas[x["id"]], "votantes": votantes[x["id"]],
              "compartidas": compartidas[x["id"]]} for x in visibles]
    filas.sort(key=lambda f: (-f["traidas"], f.get("nombre") or ""))
    total = len(filas)
    paginas = max(1, math.ceil(total / a.por_pagina))
    pagina = filas[(a.pagina - 1) * a.por_pagina:a.pagina * a.por_pagina]
    contenido = {"tipo": "lideres", "total": total, "pagina": a.pagina, "paginas": paginas, "lideres": pagina,
                 "personas_con_varios": varias, "nota": NOTA_LIDERES,
                 "ruta": "/personas?varios_lideres=1"}
    resumen = "Sin líderes" if not total else "1 líder" if total == 1 else f"{_miles(total)} líderes"
    return Resultado(contenido, f"{resumen} · página {a.pagina} de {paginas}" if paginas > 1 else resumen,
                     personas=minimizar.ids_de(pagina))


LIDERES = Herramienta(
    nombre="lideres",
    descripcion=(
        "Los líderes y concejales de la campaña (dato político; solo si el administrador lo habilitó en Ajustes). "
        "Sin `q` (administrador y coordinador): la lista de líderes, cada uno con su tipo, cuántas personas trajo "
        "(`traidas`), cuántas de ellas son votantes y cuántas trae también otro líder, más cuántas personas tienen "
        "varios líderes; de a `por_pagina`. Con `q` (también el planillero): busca un líder o concejal por nombre (3 "
        "letras o más) o por la cédula completa, para asignarlo con asignar_lider. Los conteos no cuentan a quienes no "
        "autorizaron el tratamiento de sus datos y los líderes que no autorizaron no salen. Para ver a quiénes trajo "
        "uno, usa buscar_personas con filtros.lider_id. Cada líder mostrado cuenta en el tope diario del planillero."),
    entrada=LideresEntrada, tipo="lectura", permisos=("lideres.asignar",), etiqueta="Consultando los líderes",
    ejecutar=_lideres, esquema=esquema(LideresEntrada), mcp="lectura", disponible_ajustes=politicos_ofrecidos)


# ───────────────────────────── marcar_tipo ─────────────────────────────

ETIQUETAS_TIPO = dict(modelo.TIPOS_PERSONA)
SOLO_SUMA = "Su rol solo marca un tipo: quitarlo lo hace el administrador o el coordinador."
FUERA_DE_ZONA = ("Esta persona no es de su zona: su tipo y su «Liderado por» los marcan el administrador, el "
                 "coordinador o quien la tiene asignada.")


class MarcarTipoEntrada(_Entrada):
    persona_id: Id
    tipos: list[Literal[tuple(modelo.TIPOS_PERSONA)]] = Field(..., min_length=1, max_length=len(modelo.TIPOS_PERSONA),
                                                              description="concejal, lider o votante")
    quitar: bool = Field(False, description="true: quitar esos tipos (solo administrador y coordinador)")

    @field_validator("tipos")
    @classmethod
    def _t(cls, v):
        return _sin_repetidos(v)


def _exigir_tipo_visible(ctx: Contexto, d: dict) -> None:
    """La ficha de P trae el tipo solo si es de su zona o la registró él (`proyeccion.tipo_visible`): sin él, la API
    respondería 403 `fuera_de_zona` después de aprobar."""
    if not ctx.quien.administra and any(t not in d for t in modelo.TIPOS_PERSONA):
        raise ErrorHerramienta(FUERA_DE_ZONA, "fuera_de_zona", estado=403)


def _tipos_que_cambian(d: dict, a: MarcarTipoEntrada) -> list[str]:
    return [t for t in a.tipos if (d.get(t) is True) == a.quitar]


async def _revisar_tipo(ctx: Contexto, a: MarcarTipoEntrada) -> tuple[dict, list[str]]:
    await exigir_politicos(ctx)
    if a.quitar and not ctx.quien.administra:
        raise ErrorHerramienta(SOLO_SUMA, "permiso", estado=403)
    d = await _ficha(ctx, a.persona_id)
    _exigir_tratable(d)
    _exigir_tipo_visible(ctx, d)
    return d, _tipos_que_cambian(d, a)


def _nombres_tipos(tipos: list[str]) -> str:
    return ", ".join(ETIQUETAS_TIPO[t] for t in tipos)


async def _confirmar_tipo(ctx: Contexto, a: MarcarTipoEntrada) -> Confirmacion:
    d, cambian = await _revisar_tipo(ctx, a)
    if not cambian:
        raise ErrorHerramienta("La ficha ya " + ("no tiene" if a.quitar else "tiene") + " ese tipo: no hay nada que "
                               "guardar.", "sin_cambios")
    iguales = [t for t in a.tipos if t not in cambian]
    accion = "Quitar" if a.quitar else "Marcar"
    detalle = [("Persona", _persona(d)), ("Tipo", f"{'−' if a.quitar else '+'} {_nombres_tipos(cambian)}")]
    aviso = f"Sin cambio (ya {'no ' if a.quitar else ''}lo tenía): {_nombres_tipos(iguales)}." if iguales else None
    return Confirmacion(f"{accion} el tipo de {_persona(d)}", detalle, aviso)


def _politico_breve(d: dict) -> dict:
    """Lo que el modelo recibe de una ficha después de marcar un tipo o asignar un líder: quién es y su tipo."""
    out = _breve(d)
    for t in modelo.TIPOS_PERSONA:
        if t in d:
            out[t] = d[t] is True
    return out


async def _marcar_tipo(ctx: Contexto, a: MarcarTipoEntrada) -> Resultado:
    # PATCH no respeta la Idempotency-Key: se vuelve a leer y no se escribe lo que ya quedó como se pidió
    d, cambian = await _revisar_tipo(ctx, a)
    if cambian:
        d = await _pedir(ctx, "PATCH", f"/api/personas/{a.persona_id}", cuerpo={t: not a.quitar for t in cambian})
        d = d if isinstance(d, dict) else {}
    contenido = {"guardado": bool(cambian), "persona": _politico_breve(d) or {"id": a.persona_id}}
    if not cambian:
        contenido["nota"] = "Ya estaba así: no se cambió nada."
    accion = "quitado" if a.quitar else "marcado"
    return Resultado(contenido, f"Tipo {accion} en la ficha #{a.persona_id}", list(ACCIONES_ESCRITURA),
                     personas={a.persona_id})


MARCAR_TIPO = Herramienta(
    nombre="marcar_tipo",
    descripcion=(
        "Propone marcar el tipo de una persona: concejal, lider o votante (dato político; solo si el administrador lo "
        "habilitó en Ajustes). El planillero solo marca, nunca quita, y solo en las personas de su zona o que "
        "registró (las que le muestran su tipo en la ficha); el administrador y el coordinador también quitan un tipo "
        "con `quitar: true`. No se marca nada a quien no autorizó el tratamiento de sus datos. Se guarda solo si la "
        "persona del equipo lo aprueba. Marca solo lo que te dijeron: no deduzcas el tipo de nadie."),
    entrada=MarcarTipoEntrada, tipo="escritura", permisos=("personas.editar", "personas.tipo"),
    etiqueta="Marcando el tipo", ejecutar=_marcar_tipo, confirmar=_confirmar_tipo, esquema=esquema(MarcarTipoEntrada),
    mcp="escritura", disponible_ajustes=politicos_ofrecidos)


# ───────────────────────────── asignar_lider ─────────────────────────────

MAX_LIDERES = 10  # como `api.lideres.MAX_LIDERES`


class AsignarLiderEntrada(_Entrada):
    persona_id: Id = Field(..., description="La persona a la que trajo el líder")
    lider_id: Id = Field(..., description="El líder o concejal (id de lideres)")

    @model_validator(mode="after")
    def _distintos(self):
        if self.persona_id == self.lider_id:
            raise ValueError("Una persona no puede ser su propio líder")
        return self


def _lider(db: Any, lid: int) -> dict | None:
    """El líder o concejal `lid` que se puede asignar desde el asistente: activo, marcado como líder o concejal y que
    autorizó el tratamiento (a quien no autorizó, ni A ni K lo asignan desde aquí: sería tratar su dato político)."""
    l = db.personas.find_one({"_id": lid, **bd.ACTIVA, "consentimiento": {"$ne": "no"}},
                             {"nombre": 1, **{t: 1 for t in modelo.TIPOS_LIDERAN}})
    return l if l is not None and modelo.lidera(l) else None


def _ids_lideres(d: dict) -> list[int]:
    return [l.get("id") for l in d.get("lideres") or [] if isinstance(l, dict) and isinstance(l.get("id"), int)]


async def _revisar_lider(ctx: Contexto, a: AsignarLiderEntrada) -> tuple[dict, dict, bool]:
    """(ficha, líder, ya lo tenía). Lo que la API rechazaría después de aprobar, antes: la persona no autorizó, no es de
    la zona del planillero, el líder no sirve (el mismo mensaje para todo motivo: no dice si el id existe) o ya tiene
    el tope de líderes."""
    await exigir_politicos(ctx)
    d = await _ficha(ctx, a.persona_id)
    _exigir_tratable(d)
    if not ctx.quien.administra and "lideres" not in d:
        raise ErrorHerramienta(FUERA_DE_ZONA, "fuera_de_zona", estado=403)
    l = await run_in_threadpool(_lider, ctx.db, a.lider_id)
    if l is None:
        raise ErrorHerramienta(LIDER_NO_USABLE, "invalido", estado=422, detalle={"campo": "lider_id"})
    actuales = _ids_lideres(d)
    ya = a.lider_id in actuales
    if not ya and len(actuales) >= MAX_LIDERES:
        raise ErrorHerramienta(f"Una persona puede tener hasta {MAX_LIDERES} líderes.", "invalido", estado=422)
    return d, l, ya


def _lider_texto(l: dict) -> str:
    tipo = next((TIPOS_LIDER[t] for t in modelo.TIPOS_LIDERAN if l.get(t) is True), "Líder")
    return f"{l.get('nombre') or 'Persona sin nombre'} ({tipo}) #{l['_id']}"


async def _confirmar_lider(ctx: Contexto, a: AsignarLiderEntrada) -> Confirmacion:
    d, l, ya = await _revisar_lider(ctx, a)
    if ya:
        raise ErrorHerramienta("Ese líder ya figura en su «Liderado por»: no hay nada que guardar.", "sin_cambios")
    if not ctx.quien.administra:
        # El nombre del líder sale en la tarjeta: cuenta en el presupuesto del planillero, como en el buscador del panel
        await run_in_threadpool(acceso.registrar_lecturas, ctx.db, ctx.quien, [a.lider_id])
    detalle = [("Persona", _persona(d)), ("Liderado por", f"+ {_lider_texto(l)}")]
    otros = len(_ids_lideres(d))
    aviso = (f"Ya tiene {otros} líder{'es' if otros != 1 else ''}: quedará con varios (otro también la está "
             "captando)." if otros else None)
    return Confirmacion(f"Asignar un líder a {_persona(d)}", detalle, aviso, personas={a.lider_id})


async def _asignar_lider(ctx: Contexto, a: AsignarLiderEntrada) -> Resultado:
    # La ruta no respeta la Idempotency-Key, pero asignar dos veces el mismo líder no cambia nada (la API lo devuelve
    # igual): se vuelve a leer y no se escribe si ya quedó
    d, _, ya = await _revisar_lider(ctx, a)
    if not ya:
        d = await _pedir(ctx, "POST", f"/api/personas/{a.persona_id}/lideres", cuerpo={"lider_id": a.lider_id},
                         clave=_clave(ctx))
        d = d if isinstance(d, dict) else {}
    pol = await politicos_de(ctx, [d])
    f = minimizar.ficha(d, lugares=await _lugares(ctx), politicos=pol)
    contenido = {"guardado": not ya, "persona": {**_politico_breve(d), **({"lideres": f["lideres"]}
                                                                         if "lideres" in f else {})}}
    if ya:
        contenido["nota"] = "Ya lo tenía: no se cambió nada."
    return Resultado(contenido, f"Líder asignado a la ficha #{a.persona_id}", list(ACCIONES_ESCRITURA),
                     personas={a.persona_id, a.lider_id} | ids_mostrados([f]))


ASIGNAR_LIDER = Herramienta(
    nombre="asignar_lider",
    descripcion=(
        "Propone asignarle a una persona el líder o concejal que la trajo (su «Liderado por»; dato político, solo si "
        "el administrador lo habilitó en Ajustes). Busca antes el líder con lideres (con q) y usa su id. El planillero "
        "solo asigna en las personas de su zona o que registró; quitar un líder es del administrador o el "
        "coordinador, en el panel. Una persona puede tener varios líderes (hasta 10). No se asigna a quien no "
        "autorizó el tratamiento de sus datos ni un líder que no autorizó. Se guarda solo si la persona del equipo lo "
        "aprueba."),
    entrada=AsignarLiderEntrada, tipo="escritura", permisos=("lideres.asignar",), etiqueta="Asignando el líder",
    ejecutar=_asignar_lider, confirmar=_confirmar_lider, esquema=esquema(AsignarLiderEntrada), mcp="escritura",
    disponible_ajustes=politicos_ofrecidos)


HERRAMIENTAS: list[Herramienta] = [BUSCAR, VER, PARECIDAS, CREAR, EDITAR, NOTA, ACERCAMIENTO, AUTORIZACION, UBICAR,
                                   TELEFONO, LIDERES, MARCAR_TIPO, ASIGNAR_LIDER]
