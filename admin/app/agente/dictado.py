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
  por partes y se corta al pasar del tope. Leerlo tiene plazo (el servidor web no corta un cuerpo que deja de llegar):
  `PLAZO_SUBIDA_S` en total y `SUBIDA_CALLADA_S` sin que llegue nada (el celular perdió la señal sin cerrar la
  conexión); si no, 400 `lenta`.
* Un tope de frecuencia por persona (`FRECUENCIA_MAX` por minuto, en memoria, por proceso): cada transcripción gasta
  créditos de la cuenta de Mnemo conectada, y nadie hace más de una pregunta cada tres segundos. Cuenta después del
  `turno`: un reintento rechazado porque la anterior sigue en camino no gasta.
* Dos topes de cuántas van a la vez, separados. `turno`: una por persona, desde que llega la petición hasta que se
  responde (leer el audio incluido). `cupo`: `A_LA_VEZ` llamadas a Mnemo en todo el proceso, solo mientras Mnemo
  transcribe (leer el audio no usa sus modelos: una subida lenta o estancada no deja sin voz al resto del panel). Mnemo
  atiende a lo sumo 4 llamadas a sus modelos a la vez por conexión, compartidas entre `mnemo_transcribe` y
  `mnemo_model_complete` (el modelo del asistente): las transcripciones nunca ocupan más de dos y el asistente sigue
  respondiendo. Sin cupo, la grabación ya recibida espera hasta `ESPERA_CUPO_S` a que se libere uno (transcribir tarda
  segundos) y después responde 429 `frecuencia`.
* Si la persona se va mientras se transcribe (canceló, cerró la página: la conexión se cierra), se deja de esperar a
  Mnemo (`mientras_siga`): la llamada se cancela, el turno y el cupo quedan libres en el acto (la pregunta que repite
  enseguida no rebota) y se responde 400 `cortada`, que nadie lee.
* Un tope diario por persona (`diarias`: `DIARIAS_POR_MENSAJE` veces sus mensajes del día, en memoria, por proceso)
  y nada con los mensajes del día agotados (la pregunta transcrita rebotaría en `/api/agente/mensajes`). El tamaño no
  acota lo que dura (quien graba elige la calidad: 2 MB en opus a 8 kbps son más de media hora; Mnemo corta a los 10
  minutos): lo que se acota es cuántas.
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
  429 `volumen` (el tope diario), 422 `audio` (Mnemo no pudo leer la grabación), 400 `cortada` (la subida se cortó a
  mitad: el celular perdió la señal, se cerró la pestaña; o la persona se fue mientras se transcribía), 400 `lenta`
  (la grabación no terminó de llegar a tiempo; no 408, que Chromium repite solo, con el audio entero, si llega por una
  conexión reusada) y 502 (Mnemo no respondió, falló o respondió algo ilegible). Los mensajes son propios: nunca el
  texto de Mnemo ni el del proveedor.
* Nada se guarda ni se registra: ni el audio, ni el texto, ni cuánto duró. Al registro solo van códigos.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import math
import re
import threading
import time
from collections import deque
from contextlib import asynccontextmanager, contextmanager
from typing import Any, AsyncIterator, Awaitable, Iterator, TypeVar

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect

from .. import modelo
from . import conversaciones as conv_db
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
# Lo que puede tardar en llegar la grabación: en total (un minuto de voz pesa unos 200 kB: llega en 30 s aun por una
# red de 60 kbps) y sin que llegue nada (la subida se estancó)
PLAZO_SUBIDA_S = 30.0
SUBIDA_CALLADA_S = 10.0
MAX_TEXTO = 4_000              # el tope de un mensaje al asistente (`MensajeIn.texto`)
FRECUENCIA_MAX, FRECUENCIA_S = 20, 60
# Cuántas transcripciones van a la vez en el proceso (una por persona): Mnemo deja 4 llamadas a sus modelos a la vez
# por conexión, y las otras dos quedan para el modelo del asistente
A_LA_VEZ = 2
ESPERA_TURNO_S = 3
ESPERA_CUPO_S = 10.0           # lo que una grabación ya recibida espera un cupo libre
VIGILA_S = 0.25                # cada cuánto se mira si se liberó un cupo
# Cuántas transcripciones por día puede pedir una persona: este número por sus mensajes del día
# (`politica.mensajes_diarios`). Cada pregunta por voz es un mensaje; el doble deja repetir las que no se oyeron
DIARIAS_POR_MENSAJE = 2
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
MENSAJE_A_LA_VEZ = "Todavía se está atendiendo su pregunta anterior por voz. Espere un momento o escriba su pregunta."
MENSAJE_OCUPADO = ("El panel está transcribiendo otras preguntas por voz. Espere un momento y repítala, o escriba su "
                   "pregunta.")
MENSAJE_DIARIAS = "Llegó al tope de preguntas por voz por hoy. Escriba su pregunta o siga mañana."
MENSAJE_SIN_MENSAJES = "Llegó al tope de {maximo} mensajes al asistente por hoy. Podrá seguir mañana."
MENSAJE_CORTADA = "La grabación no llegó completa. Intente de nuevo."
MENSAJE_LENTA = "La grabación tardó demasiado en llegar. Intente de nuevo o escriba su pregunta."
MENSAJE_FRECUENCIA_MNEMO = "Mnemo está recibiendo demasiadas peticiones. Espere un momento o escriba su pregunta."
MENSAJE_TIPO = "El panel no reconoce ese tipo de audio: tiene que ser webm, ogg, mp4, mp3 o wav."
MENSAJE_GRANDE = "La grabación es demasiado grande (más de 2 MB). Haga una pregunta más corta."
MENSAJE_VACIO = "La grabación llegó vacía."
MENSAJE_AUDIO = "No se pudo leer la grabación. Intente de nuevo o escriba su pregunta."
MENSAJE_RED = "No se pudo transcribir: Mnemo no respondió. Intente de nuevo o escriba su pregunta."
MENSAJE_FALLO = "No se pudo transcribir. Intente de nuevo o escriba su pregunta."

_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")
_ESPACIOS = re.compile(r"\s+")
T = TypeVar("T")


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


_en_curso: set[tuple[str, Any]] = set()       # las personas con una pregunta por voz en camino (`turno`)
_transcribiendo: set[object] = set()          # las llamadas a Mnemo en curso (`cupo`)
_diarias: dict[tuple[str, Any], tuple[str, int]] = {}


@contextmanager
def turno(base: str, uid: Any) -> Iterator[None]:
    """La pregunta por voz de una persona (y base) mientras dura el bloque: llegar el audio, esperar el cupo y
    transcribirlo. Una a la vez por persona: si ya tiene una en camino, 429 `frecuencia` con `Retry-After`. Al salir
    del bloque, pase lo que pase, queda libre. No acota a las demás personas: eso es `cupo`, solo mientras Mnemo
    transcribe."""
    clave = (base, uid)
    with _candado:
        if clave in _en_curso:
            raise ErrorDictado(429, "frecuencia", MENSAJE_A_LA_VEZ, espera=ESPERA_TURNO_S)
        _en_curso.add(clave)
    try:
        yield
    finally:
        with _candado:
            _en_curso.discard(clave)


@asynccontextmanager
async def cupo() -> AsyncIterator[None]:
    """Uno de los `A_LA_VEZ` cupos del proceso para llamar a Mnemo, mientras dura el bloque (las transcripciones nunca
    ocupan más de dos de las cuatro llamadas a sus modelos que Mnemo deja a la vez). Si no hay, espera hasta
    `ESPERA_CUPO_S` a que se libere uno (la grabación ya llegó y transcribir tarda segundos) y si no, 429 `frecuencia`
    con `Retry-After`. Al salir del bloque, pase lo que pase (también si se cancela), queda libre."""
    ficha = object()
    hasta = time.monotonic() + ESPERA_CUPO_S
    while True:
        with _candado:
            if len(_transcribiendo) < A_LA_VEZ:
                _transcribiendo.add(ficha)
                break
        if time.monotonic() >= hasta:
            raise ErrorDictado(429, "frecuencia", MENSAJE_OCUPADO, espera=ESPERA_TURNO_S)
        await asyncio.sleep(VIGILA_S)
    try:
        yield
    finally:
        with _candado:
            _transcribiendo.discard(ficha)


def diarias(base: str, uid: Any, maximo: int) -> None:
    """Cuenta una transcripción en el día de la persona (hora de Colombia, como sus mensajes): a lo sumo `maximo`; si
    no, 429 `volumen`. En memoria y por proceso, como `frecuencia`."""
    dia = modelo.hoy_local().isoformat()
    with _candado:
        if len(_diarias) > 5000:  # se olvidan los días que ya pasaron
            for k in [k for k, v in _diarias.items() if v[0] != dia]:
                del _diarias[k]
        d, n = _diarias.get((base, uid), (dia, 0))
        n = n if d == dia else 0
        if n >= maximo:
            raise ErrorDictado(429, "volumen", MENSAJE_DIARIAS)
        _diarias[(base, uid)] = (dia, n + 1)


def exigir_mensajes(db: Any, uid: Any, maximo: int) -> None:
    """429 `volumen` si la persona ya gastó sus `maximo` mensajes del día: la pregunta transcrita no se podría enviar
    (`/api/agente/mensajes` la rechazaría) y transcribirla gastaría créditos para nada. Lee MongoDB: desde código
    asíncrono, con `run_in_threadpool`. Si el uso no se puede leer, no frena: los demás topes siguen."""
    try:
        usados = conv_db.uso_de(db, uid)
    except Exception as e:  # noqa: BLE001 - es un tope de cortesía: el de cada mensaje lo cuenta `bucle._contar`
        log.warning("Dictado: no se pudo leer el uso del día (%s)", type(e).__name__)
        return
    if usados >= maximo:
        raise ErrorDictado(429, "volumen", MENSAJE_SIN_MENSAJES.format(maximo=maximo))


async def leer_audio(request: Any) -> bytes:
    """El cuerpo de la petición, leído por partes: 413 si pasa de `MAX_AUDIO` (por su `Content-Length` o contando lo
    que llega), 400 `cortada` si la subida se corta a mitad (sin la traza de una excepción sin atrapar en el registro),
    400 `lenta` si no termina de llegar en `PLAZO_SUBIDA_S` o deja de llegar durante `SUBIDA_CALLADA_S` (el servidor
    web espera para siempre un cuerpo estancado), y 422 si viene vacío."""
    largo = request.headers.get("content-length", "")
    if largo.isdigit() and int(largo) > MAX_AUDIO:
        raise ErrorDictado(413, "grande", MENSAJE_GRANDE)
    partes, total = [], 0
    trozos = request.stream().__aiter__()
    try:
        async with asyncio.timeout(PLAZO_SUBIDA_S):
            while True:
                try:
                    trozo = await asyncio.wait_for(anext(trozos), SUBIDA_CALLADA_S)
                except StopAsyncIteration:
                    break
                total += len(trozo)
                if total > MAX_AUDIO:
                    raise ErrorDictado(413, "grande", MENSAJE_GRANDE)
                partes.append(trozo)
    except ClientDisconnect:
        raise ErrorDictado(400, "cortada", MENSAJE_CORTADA) from None
    except TimeoutError:
        log.info("Dictado: no se transcribió (lenta)")
        raise ErrorDictado(400, "lenta", MENSAJE_LENTA) from None
    if not total:
        raise ErrorDictado(422, "vacio", MENSAJE_VACIO)
    return b"".join(partes)


async def _se_fue(request: Any) -> bool:
    """Espera a que la persona se vaya (cierre la conexión) y responde True. Con el cuerpo ya leído, lo único que puede
    llegar es `http.disconnect` (al irse o al terminar la respuesta). False si este servidor no lo sabe decir."""
    try:
        mensaje = await request.receive()
    except Exception:  # noqa: BLE001 - sin ese aviso, se espera a Mnemo como siempre
        return False
    return isinstance(mensaje, dict) and mensaje.get("type") == "http.disconnect"


async def mientras_siga(request: Any, trabajo: Awaitable[T]) -> T:
    """El resultado de `trabajo` (esperar el cupo y transcribir), si la persona sigue ahí para recibirlo. Si se va
    antes (canceló, cerró la página), lo cancela, espera a que suelte lo que tenga tomado (el cupo) y responde 400
    `cortada`, que nadie lee: así su turno queda libre en el acto, y la pregunta que repite enseguida no rebota.
    Con el cuerpo de la petición ya leído."""
    tarea = asyncio.ensure_future(trabajo)
    vigia = asyncio.ensure_future(_se_fue(request))
    try:
        await asyncio.wait({tarea, vigia}, return_when=asyncio.FIRST_COMPLETED)
        if not tarea.done() and vigia.result():
            log.info("Dictado: no se transcribió (cortada)")
            raise ErrorDictado(400, "cortada", MENSAJE_CORTADA)
        return await tarea
    finally:
        for t in (tarea, vigia):
            if not t.done():
                t.cancel()
        await asyncio.gather(tarea, vigia, return_exceptions=True)


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


async def transcribir_con_cupo(app: Any, audio: bytes, mime: str) -> str:
    """`transcribir` con uno de los cupos del proceso tomado (`cupo`): lo que la ruta le pasa a `mientras_siga`."""
    async with cupo():
        return await transcribir(app, audio, mime)
