"""Preguntas por voz (docs/agente.md, «Preguntas por voz»): el audio que graba el panel (`web/js/dictado.js`) se
transcribe con la cuenta de Mnemo conectada, por la herramienta MCP `mnemo_transcribe` (alcance `mnemo:model`, la
hermana de `mnemo_model_complete`). Lo usa `POST /api/agente/transcribir` (`api/agente.py`).

Contrato con Mnemo (`apps/api/src/agent-api/catalog/transcribe.ts`, `docs/agentes-externos.md` §5.6):

* Entrada: `{audio: base64, mime: "audio/webm" | "audio/ogg" | "audio/mp4" | "audio/mpeg" | "audio/wav", language}`.
  Aquí siempre `language: "es"`: las preguntas son en español.
* Salida en `structuredContent`: `{text ("" si no se oyó nada), language?, duration_s?, model, usage?}`. Solo se usa
  `text`.
* Errores: `isError` con `{error: {code, message, details?}}`: `NO_TRANSCRIBER` (el código propio: la cuenta no tiene
  quien transcriba audio; con `details.reason: "no_transcriber"`, que también se acepta suelto), `INVALID_ARGUMENT`
  (`details.reason`: `undecodable`, `empty`, `too_long` o `rejected`), `PLAN_REQUIRED`, `CREDITS_EXHAUSTED`,
  `RATE_LIMITED`, `UNAVAILABLE` (con `details.reason: "transcriber"` si el modelo que transcribe no puede atender; sin
  él, el proveedor caído), `TIMEOUT` e `INTERNAL`.

Por qué está hecho así:

* El audio llega crudo en el cuerpo (no en JSON ni en un formulario): hasta `MAX_AUDIO` (2 MB; un minuto de voz en opus
  pesa menos de 200 kB), con uno de los tipos de `TIPOS` (de la cabecera `Content-Type`, sin sus parámetros). Se lee
  por partes y se corta al pasar del tope.
* Un tope de frecuencia por persona (`FRECUENCIA_MAX` por minuto, en memoria, por proceso): cada transcripción gasta
  créditos de la cuenta de Mnemo conectada, y nadie hace más de una pregunta cada tres segundos.
* Lo que no deja transcribir por Mnemo responde 409 `sin_transcriptor`, y el panel pasa al reconocimiento de voz del
  navegador: Mnemo sin conectar o con la conexión caída, la conexión sin `mnemo:model`, un Mnemo que todavía no ofrece
  `mnemo_transcribe`, un plan que no lo incluye, una cuenta sin un modelo que transcriba (`NO_TRANSCRIBER`) o cuyo
  modelo no puede atender (`UNAVAILABLE` con `reason: "transcriber"`). Los cuatro últimos se recuerdan `OLVIDO_S` (por
  conexión): mientras tanto `GET /api/agente/estado` dice `dictado: false` y el panel va directo al navegador, sin
  grabar una pregunta que habría que repetir. La ruta no deja de intentarlo por eso: si ya se puede, el recuerdo se
  borra.
* Una grabación en la que Mnemo no oye nada (`INVALID_ARGUMENT` con `reason: "empty"`) no es un error: responde el
  texto vacío, como cuando el modelo no transcribe nada, y el panel dice «No oí nada».
* Los demás errores: 402 `mnemo_creditos` (se acabaron los créditos), 429 `frecuencia` (el tope de aquí o el de Mnemo),
  422 `audio` (Mnemo no pudo leer la grabación) y 502 (Mnemo no respondió, falló o respondió algo ilegible). Los
  mensajes son propios: nunca el texto de Mnemo ni el del proveedor.
* Nada se guarda ni se registra: ni el audio, ni el texto, ni cuánto duró. Al registro solo van códigos.
"""
from __future__ import annotations

import base64
import logging
import math
import re
import threading
import time
from collections import deque
from typing import Any

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool

from . import mnemo_cliente as mc
from . import mnemo_conexion
from .herramientas.base import ErrorHerramienta

log = logging.getLogger("panel")

HERRAMIENTA = "mnemo_transcribe"
TIPOS = ("audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav")
# Otros nombres de los mismos contenedores (lo que dicen algunos navegadores y programas)
ALIAS = {"audio/x-wav": "audio/wav", "audio/wave": "audio/wav", "audio/vnd.wave": "audio/wav",
         "audio/mp3": "audio/mpeg", "audio/x-m4a": "audio/mp4", "audio/m4a": "audio/mp4"}
MAX_AUDIO = 2 * 1024 * 1024    # Mnemo recibe hasta 3 000 000 caracteres de base64 (unos 2,2 MB)
IDIOMA = "es"
# Nombres propios y siglas de la propuesta, para que el modelo que transcribe los escriba bien (la pista de
# `mnemo_transcribe`, hasta 500 caracteres). No lleva datos de personas
VOCABULARIO = ("Yondó, Antioquia, Trabajemos juntos, Casabe, Barrancabermeja, Kilómetro Cinco, San Miguel del Tigre, "
               "PTAR, PTAP, EBAR, ECA, telesalud, sóftbol, relleno sanitario, agroindustria, Sisbén, hospital Héctor Abad "
               "Gómez, parque lineal, alameda, matadero, trilladora")
PLAZO_S = 60.0                 # un minuto de audio se transcribe en segundos
MAX_TEXTO = 4_000              # el tope de un mensaje al asistente (`MensajeIn.texto`)
FRECUENCIA_MAX, FRECUENCIA_S = 20, 60
OLVIDO_S = 3600.0              # lo que se recuerda que este Mnemo no transcribe

SIN_TRANSCRIPTOR = "sin_transcriptor"
MENSAJE_SIN_CONEXION = ("El panel no puede transcribir la voz: Mnemo no está conectado (lo conecta el administrador en "
                        "Ajustes → Asistente).")
MENSAJE_SIN_PERMISO = ("El panel no puede transcribir la voz: la conexión con Mnemo no tiene permiso para usar sus "
                       "modelos (el administrador la vuelve a conectar en Ajustes → Asistente).")
MENSAJE_SIN_HERRAMIENTA = ("El panel no puede transcribir la voz: el Mnemo conectado todavía no transcribe audio para "
                           "otras aplicaciones (hay que actualizarlo).")
MENSAJE_SIN_PLAN = "El panel no puede transcribir la voz: el plan de la cuenta de Mnemo conectada no lo incluye."
MENSAJE_SIN_MODELO = ("El panel no puede transcribir la voz: la cuenta de Mnemo conectada no tiene un modelo que "
                      "transcriba audio (se elige en Mnemo, en los ajustes de modelos).")
MENSAJE_MODELO_CAIDO = ("El panel no puede transcribir la voz: el modelo de la cuenta de Mnemo conectada que transcribe "
                        "audio no puede atender (se revisa en Mnemo, en los ajustes de modelos).")
MENSAJE_CREDITOS = ("Se acabaron los créditos de Mnemo de esta semana de la cuenta conectada: no se pudo transcribir. "
                    "Escriba su pregunta.")
MENSAJE_FRECUENCIA = "Demasiadas preguntas por voz seguidas. Espere un momento o escriba su pregunta."
MENSAJE_FRECUENCIA_MNEMO = "Mnemo está recibiendo demasiadas peticiones. Espere un momento o escriba su pregunta."
MENSAJE_TIPO = "El panel no reconoce ese tipo de audio: tiene que ser webm, ogg, mp4, mp3 o wav."
MENSAJE_GRANDE = "La grabación es demasiado grande (más de 2 MB). Haga una pregunta más corta."
MENSAJE_VACIO = "La grabación llegó vacía."
MENSAJE_AUDIO = "No se pudo leer la grabación. Intente de nuevo o escriba su pregunta."
MENSAJE_RED = "No se pudo transcribir: Mnemo no respondió. Intente de nuevo o escriba su pregunta."
MENSAJE_FALLO = "No se pudo transcribir. Intente de nuevo o escriba su pregunta."

_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")
_ESPACIOS = re.compile(r"\s+")


class ErrorDictado(HTTPException):
    """Lo que impide transcribir, como lo responde la ruta: `detail` es `{codigo, mensaje}`."""

    def __init__(self, estado: int, codigo: str, mensaje: str, *, espera: int | None = None):
        super().__init__(estado, {"codigo": codigo, "mensaje": mensaje},
                         headers={"Retry-After": str(espera)} if espera else None)
        self.codigo, self.mensaje = codigo, mensaje


# ───────────────────────────── La petición ─────────────────────────────

def tipo_de(cabecera: Any) -> str | None:
    """El tipo del audio (uno de `TIPOS`) según el `Content-Type` de la petición, sin sus parámetros
    («audio/webm;codecs=opus» → «audio/webm»); None si no es uno que Mnemo transcriba."""
    if not isinstance(cabecera, str):
        return None
    tipo = cabecera.split(";", 1)[0].strip().lower()
    tipo = ALIAS.get(tipo, tipo)
    return tipo if tipo in TIPOS else None


_ventanas: dict[tuple[str, Any], deque] = {}
_candado = threading.Lock()


def frecuencia(base: str, uid: Any) -> None:
    """Ventana deslizante en memoria por persona (y base): `FRECUENCIA_MAX` transcripciones por minuto; si no, 429
    `frecuencia` con `Retry-After`. Vale por proceso (como `acceso._frecuencia`)."""
    ahora = time.monotonic()
    with _candado:
        if len(_ventanas) > 5000:  # se olvidan las ventanas ya vacías
            for k in [k for k, v in _ventanas.items() if not v or v[-1] <= ahora - FRECUENCIA_S]:
                del _ventanas[k]
        v = _ventanas.setdefault((base, uid), deque())
        while v and v[0] <= ahora - FRECUENCIA_S:
            v.popleft()
        if len(v) >= FRECUENCIA_MAX:
            raise ErrorDictado(429, "frecuencia", MENSAJE_FRECUENCIA,
                               espera=max(1, math.ceil(v[0] + FRECUENCIA_S - ahora)))
        v.append(ahora)


async def leer_audio(request: Any) -> bytes:
    """El cuerpo de la petición, leído por partes: 413 si pasa de `MAX_AUDIO` (por su `Content-Length` o contando lo
    que llega) y 422 si viene vacío."""
    largo = request.headers.get("content-length", "")
    if largo.isdigit() and int(largo) > MAX_AUDIO:
        raise ErrorDictado(413, "grande", MENSAJE_GRANDE)
    partes, total = [], 0
    async for trozo in request.stream():
        total += len(trozo)
        if total > MAX_AUDIO:
            raise ErrorDictado(413, "grande", MENSAJE_GRANDE)
        partes.append(trozo)
    if not total:
        raise ErrorDictado(422, "vacio", MENSAJE_VACIO)
    return b"".join(partes)


# ───────────────────────────── ¿Se puede? ─────────────────────────────

def puede(app: Any, conexion: Any) -> bool:
    """¿Esta instalación puede transcribir por Mnemo ahora? (`dictado` de `GET /api/agente/estado`). `conexion` es
    `mnemo_conexion.vista`: tiene que estar «conectada» y con `mnemo:model`, y Mnemo no tiene que haber respondido
    hace poco, con esta misma conexión, que no transcribe."""
    if not isinstance(conexion, dict) or conexion.get("estado") != "conectada" or conexion.get("modelo") is not True:
        return False
    sin = getattr(getattr(app, "state", None), "dictado_sin", None)
    return not (isinstance(sin, tuple) and len(sin) == 2 and sin[0] == conexion.get("desde")
                and time.monotonic() - sin[1] < OLVIDO_S)


def _recordar(app: Any, conexion: dict, sin: bool) -> None:
    """Anota (o borra) que Mnemo respondió, con esta conexión, que no transcribe."""
    try:
        app.state.dictado_sin = (conexion.get("desde"), time.monotonic()) if sin else None
    except Exception:  # noqa: BLE001 - es solo una pista para la interfaz
        pass


# ───────────────────────────── Mnemo ─────────────────────────────

def _de_mnemo(e: ErrorHerramienta) -> tuple[str, dict]:
    """(código de Mnemo, `details`) de un error que devolvió Mnemo (`isError`); ("", {}) si es otra cosa."""
    if e.codigo == mc.COD_MNEMO and isinstance(e.detalle, dict):
        codigo, detalles = e.detalle.get("code"), e.detalle.get("details")
        return (codigo if isinstance(codigo, str) else ""), (detalles if isinstance(detalles, dict) else {})
    return "", {}


def _sin_modelo(codigo: str, detalles: dict) -> bool:
    """¿Mnemo dijo que la cuenta no tiene un modelo que transcriba? (`no_transcriber`, como código o como razón)."""
    vistos = [codigo, detalles.get("reason"), detalles.get("code")]
    return any(isinstance(v, str) and v.strip().lower() == "no_transcriber" for v in vistos)


def traducir(e: ErrorHerramienta) -> tuple[ErrorDictado, bool]:
    """Un fallo de la llamada a Mnemo como lo responde la ruta, y si hay que recordar que este Mnemo no transcribe."""
    if e.codigo == mc.COD_TOKEN:
        if isinstance(e.detalle, dict) and e.detalle.get("conexion") == "cambio":  # cambió a mitad: es pasajero
            return ErrorDictado(502, "mnemo_red", MENSAJE_RED), False
        # la conexión venció o se revocó (401), o le falta el alcance (403)
        return ErrorDictado(409, SIN_TRANSCRIPTOR, MENSAJE_SIN_PERMISO if e.estado == 403 else MENSAJE_SIN_CONEXION), False
    if e.codigo == mc.COD_NO_DISPONIBLE:  # ese Mnemo no ofrece `mnemo_transcribe` a esta conexión
        return ErrorDictado(409, SIN_TRANSCRIPTOR, MENSAJE_SIN_HERRAMIENTA), True
    if e.codigo in (mc.COD_RED, mc.COD_PLAZO):
        return ErrorDictado(502, "mnemo_red", MENSAJE_RED), False
    codigo, detalles = _de_mnemo(e)
    if _sin_modelo(codigo, detalles):
        return ErrorDictado(409, SIN_TRANSCRIPTOR, MENSAJE_SIN_MODELO), True
    if codigo == "PLAN_REQUIRED":
        return ErrorDictado(409, SIN_TRANSCRIPTOR, MENSAJE_SIN_PLAN), True
    if codigo == "UNAVAILABLE" and detalles.get("reason") == "transcriber":  # su clave fue rechazada, o no transcribe
        return ErrorDictado(409, SIN_TRANSCRIPTOR, MENSAJE_MODELO_CAIDO), True
    if codigo == "CREDITS_EXHAUSTED":
        return ErrorDictado(402, "mnemo_creditos", MENSAJE_CREDITOS), False
    if codigo == "RATE_LIMITED" or (not codigo and e.estado == 429):
        return ErrorDictado(429, "frecuencia", MENSAJE_FRECUENCIA_MNEMO, espera=30), False
    if codigo == "INVALID_ARGUMENT":
        return ErrorDictado(422, "audio", MENSAJE_AUDIO), False
    if not codigo and e.estado == 413:
        return ErrorDictado(413, "grande", MENSAJE_GRANDE), False
    return ErrorDictado(502, "mnemo", MENSAJE_FALLO), False


def texto_de(res: Any) -> str:
    """El texto transcrito de la respuesta de `mnemo_transcribe` (`structuredContent.text`), limpio: sin caracteres de
    control, con los espacios juntos y con el tope de un mensaje. 502 si la respuesta no trae un texto."""
    datos = res.get("structuredContent") if isinstance(res, dict) else None
    texto = datos.get("text") if isinstance(datos, dict) else None
    if not isinstance(texto, str):
        log.warning("Dictado: la respuesta de Mnemo no trae el texto")
        raise ErrorDictado(502, "mnemo", MENSAJE_FALLO)
    return _ESPACIOS.sub(" ", _CONTROL.sub(" ", texto)).strip()[:MAX_TEXTO].strip()


def _preparar(app: Any) -> tuple[dict, Any]:
    """(la conexión con Mnemo como la muestra `mnemo_conexion.vista`, el cliente o None). Lee MongoDB: desde código
    asíncrono, con `run_in_threadpool`."""
    return mnemo_conexion.vista(app.state.db), mc.cliente_de(app)


async def transcribir(app: Any, audio: bytes, mime: str) -> str:
    """El texto de `audio` (de tipo `mime`, uno de `TIPOS`), transcrito por la cuenta de Mnemo conectada. Puede ser ""
    (no se oyó nada). Lo que lo impide sale como `ErrorDictado` (409 `sin_transcriptor`, 402, 413, 422, 429, 502)."""
    conexion, cliente = await run_in_threadpool(_preparar, app)
    if cliente is None or conexion.get("estado") != "conectada":
        raise ErrorDictado(409, SIN_TRANSCRIPTOR, MENSAJE_SIN_CONEXION)
    if conexion.get("modelo") is not True:  # sin `mnemo:model`: ni se manda el audio
        raise ErrorDictado(409, SIN_TRANSCRIPTOR, MENSAJE_SIN_PERMISO)
    argumentos = {"audio": base64.b64encode(audio).decode("ascii"), "mime": mime, "language": IDIOMA,
                  "prompt": VOCABULARIO}
    try:
        res = await cliente.llamar(HERRAMIENTA, argumentos, PLAZO_S)
    except ErrorHerramienta as e:
        codigo, detalles = _de_mnemo(e)
        if codigo == "INVALID_ARGUMENT" and detalles.get("reason") == "empty":  # la grabación no suena: no se oyó nada
            return ""
        error, recordar = traducir(e)
        log.info("Dictado: no se transcribió (%s)", error.codigo)
        if recordar:
            _recordar(app, conexion, True)
        raise error from None
    _recordar(app, conexion, False)
    return texto_de(res)
