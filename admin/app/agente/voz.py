"""La voz clonada del asistente (docs/agente.md, «La voz clonada de Mnemo»): el panel narra la presentación técnica
y lee en voz alta las respuestas del asistente con una voz que el administrador clonó en Mnemo (Ajustes → Voces de
Mnemo), recibiendo el audio por partes mientras Mnemo lo genera. Lo usan `GET /api/agente/voces`, `POST
/api/agente/voz` y el campo `voz` de `GET /api/agente/estado` (`api/agente.py`), y el turno del asistente, que arma
las frases firmadas de una respuesta hablada (`Frases`, en `bucle.py`). Si la voz clonada no llega, el navegador dice
la frase con su propia voz (`web/js/voz-clonada.js`): esto nunca deja muda la presentación.

Contrato con Mnemo (`apps/api/src/agent-api/catalog/voice.ts`, `docs/agentes-externos.md` §5.7), alcance
`mnemo:voice` (`mnemo_conexion.ALCANCE_VOZ`):

* `mnemo_list_voices`, entrada `{}`. Salida en `structuredContent`: `{voices: [{voice_id, name, language, engine,
  status: "ready"}], default_voice_id}`: solo las voces que la persona marcó «Disponible para apps conectadas» y que
  están listas.
* `mnemo_speak`, entrada `{voice_id, text (1..1000), format: "pcm_s16le_24000", language: "es"}`. Con
  `_meta.progressToken` (este cliente siempre lo manda: `al_progreso`), cada `notifications/progress` lleva en
  `message` un JSON: primero `{"type": "start", "format", "mime", "sample_rate", "channels", "mode"}` y después
  `{"type": "audio", "seq", "data": base64 de un trozo}` (unos 9 600 bytes: 200 ms de PCM). La salida, al final:
  `{voice_id, format, mime, sample_rate, channels, characters, bytes, chunks, first_audio_ms, total_ms, duration_ms,
  mode, streamed, audio? (base64 entero, solo sin progressToken), usage?}`. Aquí se usan `first_audio_ms` (para decir
  cuánto tardó Mnemo) y, si no llegó nada por el avance, `audio`. Si Mnemo no pudo dar PCM (sin ffmpeg), `format` dice
  cuál dio (`mp3`, `wav`): se pasa tal cual y el navegador decodifica la frase entera.
* Errores (`isError` con `{error: {code, message, details?}}`): `NO_VOICE` (la voz no existe, no es de esa cuenta,
  no está marcada para apps o no está lista; `details.reason`), `PLAN_REQUIRED`, `CREDITS_EXHAUSTED`, `UNAVAILABLE`
  (con `details.reason: "speech"`: la cuenta no tiene con qué generar la voz), `RATE_LIMITED`, `TIMEOUT`,
  `INVALID_ARGUMENT` e `INTERNAL`.

Por qué está hecho así:

* El token de la conexión solo va a la dirección MCP atada a él (`FuenteTokens`): por eso el audio viaja DENTRO de
  MCP, en los avisos de progreso de `mnemo_speak`, y no por una ruta REST de Mnemo. La clave de fal nunca sale de
  Mnemo.
* La voz clonada solo dice lo que el sistema generó: el navegador nunca manda un texto libre. La narración se pide por
  referencia al plan guardado de esa persona (`{rid, n, frase}` o `{rid, cierre: true}`; el texto sale de
  `pantalla.recorrido_de` o de `recorrido_previo`, y si el plan ya no es ese, 409 `plan_vencido`); una frase de una
  respuesta del asistente, con la firma que le puso el servidor al emitirla (`firmar`: HMAC-SHA256 de `uid`,
  conversación y texto, con una clave derivada de la del administrador, `seguridad.llave_mnemo`); y la prueba de
  Ajustes es una frase fija (solo el administrador). Todo texto pasa además las reglas de lo que se dice en voz alta
  ante una sala (`hablable`: sin «@» ni números de 7 o más dígitos, como lo proyectado) y la tabla de pronunciación de
  `web/js/voz.js` (`para_decir`, el mismo `paraDecir`: una prueba compara las dos tablas).
* Quién la hace sonar: la voz es de la cuenta de Mnemo del administrador (un dato biométrico suyo) y gasta sus
  créditos. Solo los roles de `agente_voz.roles` (403 `voz_rol`), solo con `agente_voz.motor` en «mnemo» y una voz
  elegida con la cuenta conectada ahora (`agente_voz.cuenta`, la huella de `mnemo_conexion.huella_cuenta`), y solo
  con una conexión que tenga `mnemo:voice`. Las respuestas, además, solo con `agente_voz.respuestas` y en una
  conversación sin datos de habitantes (`conv_db.tiene_personas`: 409 `con_personas`, la misma guarda que lo
  proyectado); la presentación automática, solo con `agente_voz.automatica` (si no, 409 `voz_apagada`: esa frase va
  con la voz del navegador y las demás siguen con la clonada).
* Topes, en memoria y por proceso (como `dictado.py`): por persona, `A_LA_VEZ_PERSONA` a la vez (la frase que suena y
  la siguiente, que el navegador precarga), `FRECUENCIA_MAX` por minuto y `CARACTERES_DIA` caracteres por día (lo que
  de verdad va a Mnemo: lo que sale de la caché o se cuelga de otro vuelo no cuenta); y en el proceso, `A_LA_VEZ`
  llamadas a Mnemo a la vez (`cupo`, que espera hasta `ESPERA_CUPO_S`). Mnemo atiende hasta 4 voces a la vez por
  conexión, aparte de los modelos.
* Caché en memoria SOLO de la narración y de la prueba (texto público de la presentación, que se repite: «Volver a
  reproducir», la pausa, la presentación automática en un televisor): por `sha256(voz, formato, texto dicho)`, LRU por
  tamaño (`CACHE_BYTES`) y con vida (`CACHE_S`). Se vacía al cambiar de voz. Las respuestas del asistente nunca se
  guardan: pueden traer datos de personas.
* Un solo vuelo: dos peticiones iguales a la vez (la precarga y la reproducción, o dos ventanas) se cuelgan del mismo
  productor y reciben lo ya producido y lo que viene. Si se van todas, la llamada a Mnemo se cancela (Mnemo deja de
  generar); lo producido de una narración solo queda en la caché si llegó entero.
* El flujo: NDJSON como el del chat (`application/x-ndjson`, sin gzip: `main.RUTAS_EN_FLUJO`; con cupos propios en
  `servidor.RUTAS_VOZ`), con `inicio`, `audio` (el base64 de Mnemo tal cual) y `fin` o `error`. Lo que impide hablar
  sale antes como JSON normal (`{codigo, mensaje}`): la ruta espera el primer aviso de Mnemo antes de abrir el flujo.
  Si la respuesta no empieza a leerse en `ESPERA_ARRANQUE_S` (el navegador se fue antes), el vuelo la suelta (como el
  turno del asistente).
* Si Mnemo dice que no puede (la herramienta no está, el plan no la incluye, la voz no está para apps, no tiene con qué
  generarla), se responde 409 `sin_voz` y se recuerda `OLVIDO_S` para esa conexión y esa voz: mientras tanto `GET
  /api/agente/estado` dice `voz.disponible: false` y el panel ni lo intenta. La ruta no deja de intentarlo: un acierto
  borra el recuerdo, y elegir otra voz o volver a conectar también.
* Nada se guarda en la base ni se registra: ni el texto ni el audio. Al registro solo van códigos.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import hmac
import json
import logging
import math
import re
import threading
import time
import unicodedata
from collections import OrderedDict, deque
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Awaitable, Callable

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from .. import modelo, pantalla, seguridad
from ..proyectable import numero_largo
from . import conversaciones as conv_db
from . import guion as guion_presentacion
from . import mnemo_cliente as mc
from . import mnemo_conexion, politica
from .herramientas.base import ErrorHerramienta

log = logging.getLogger("panel")

HERRAMIENTA = "mnemo_speak"
HERRAMIENTA_VOCES = "mnemo_list_voices"
FORMATO = "pcm_s16le_24000"     # lo que se le pide a Mnemo: PCM de 16 bits, 24 kHz, mono (el navegador lo agenda con
IDIOMA = "es"                   # Web Audio a medida que llega, sin decodificar nada ni tocar la CSP)
PLAZO_S = 30.0                  # sin un aviso de Mnemo (cada trozo de audio lo renueva)
TOPE_S = 125.0                  # la llamada entera (Mnemo corta `mnemo_speak` a los 120 s)
PLAZO_VOCES_S = 20.0
# Por persona: la frase que suena y la siguiente, que el navegador precarga; por minuto (una frase dura unos segundos:
# sobra para la narración y una respuesta a la vez); y lo que va a Mnemo por día (un costo por carácter)
A_LA_VEZ_PERSONA = 2
FRECUENCIA_MAX, FRECUENCIA_S = 90, 60
CARACTERES_DIA = 30_000
# En el proceso: llamadas a Mnemo a la vez (Mnemo deja 4 voces a la vez por conexión, aparte de sus modelos)
A_LA_VEZ = 3
ESPERA_CUPO_S = 10.0
VIGILA_S = 0.25
ESPERA_TURNO_S = 3
OLVIDO_S = 3600.0               # lo que se recuerda que esta conexión no puede hablar con esa voz
CACHE_BYTES = 48 * 1024 * 1024  # lo que ocupa la caché de la narración (en base64: lo que se guarda y se manda)
CACHE_S = 12 * 3600.0
ESPERA_ARRANQUE_S = 30.0        # si la respuesta no empieza a leerse en este tiempo, el vuelo la suelta
LATIDO_S = 15.0
MAX_TEXTO = 400                 # una frase de una respuesta del asistente (`Frases` las corta en MAX_FRASE)
MAX_DICHO = 1000                # lo que Mnemo dice en una llamada
MAX_AUDIO = 10 * 1024 * 1024    # el audio de una frase (PCM: 400 caracteres duran unos 30 s, 1,4 MB)
TROZO_B64 = 12_800              # al partir un audio que llegó entero: 9 600 bytes (200 ms de PCM), múltiplo de 4 y de 2
MAX_VOCES = 50
FRASE_PRUEBA = ("Hola. Esta es la voz que usará el asistente para narrar la presentación y responder sus "
                "preguntas.")
ETIQUETA_FIRMA = b"voz-respuestas-v1"
FLUJO = {"X-Accel-Buffering": "no", "Cache-Control": "no-store"}

SIN_VOZ = "sin_voz"
MENSAJE_SIN_ELEGIR = ("El asistente usa la voz del navegador: no hay una voz clonada de Mnemo elegida (la elige el "
                      "administrador en Ajustes → Asistente).")
MENSAJE_SIN_CONEXION = ("La voz clonada no está disponible: Mnemo no está conectado (lo conecta el administrador en "
                        "Ajustes → Asistente).")
MENSAJE_SIN_PERMISO = ("La voz clonada no está disponible: la conexión con Mnemo no tiene permiso para usar sus voces "
                       "(el administrador la vuelve a conectar en Ajustes → Asistente dejando marcado «Hablar con las "
                       "voces que clonaste en Mnemo»).")
MENSAJE_OTRA_CUENTA = ("La voz elegida es de otra cuenta de Mnemo: el administrador elige una de la cuenta conectada "
                       "en Ajustes → Asistente.")
MENSAJE_SIN_HERRAMIENTA = ("La voz clonada no está disponible: el Mnemo conectado todavía no ofrece sus voces a otras "
                           "aplicaciones (hay que actualizarlo).")
MENSAJE_SIN_ESA_VOZ = ("La voz elegida ya no está disponible en Mnemo (se borró, dejó de estar marcada para las apps "
                       "conectadas o hay que volver a clonarla): el administrador elige otra en Ajustes → Asistente.")
MENSAJE_SIN_PLAN = "La voz clonada no está disponible: el plan de la cuenta de Mnemo conectada no incluye las voces."
MENSAJE_NO_HABLA = ("La voz clonada no está disponible: la cuenta de Mnemo conectada no tiene con qué generar la voz "
                    "(se revisa en Mnemo).")
MENSAJE_ROL = "Su rol no usa la voz clonada del asistente (lo decide el administrador en Ajustes → Asistente)."
MENSAJE_PRUEBA_ROL = "Solo el administrador prueba la voz del asistente."
MENSAJE_SIN_RESPUESTAS = ("La voz clonada no lee las respuestas del asistente (lo decide el administrador en Ajustes → "
                          "Asistente).")
MENSAJE_SIN_AUTOMATICA = ("La voz clonada no narra la presentación automática (lo decide el administrador en Ajustes → "
                          "Asistente).")
MENSAJE_PLAN_VENCIDO = "Ese plan ya no es el vigente: no se narra."
MENSAJE_NO_ESTA = "Esa frase no está en el plan."
MENSAJE_CON_PERSONAS = ("Esta conversación ya trae datos de habitantes: sus respuestas no se leen en voz alta con la "
                        "voz clonada.")
MENSAJE_NO_EXISTE = "No existe esa conversación."
MENSAJE_FIRMA = "Ese texto no lo escribió el asistente en esta conversación: no se dice con la voz clonada."
MENSAJE_TEXTO = ("Ese texto no se dice en voz alta: está vacío, es muy largo o trae algo que no se dice ante una sala "
                 "(una «@» o un número de 7 o más dígitos).")
MENSAJE_CREDITOS = ("Se acabaron los créditos de Mnemo de esta semana de la cuenta conectada: la voz clonada no puede "
                    "hablar.")
MENSAJE_FRECUENCIA = "Demasiadas frases seguidas con la voz clonada. Espere un momento."
MENSAJE_A_LA_VEZ = "Ya hay dos frases suyas en camino con la voz clonada. Espere a que termine una."
MENSAJE_OCUPADO = "El panel está generando otras frases con la voz clonada. Espere un momento."
MENSAJE_DIARIAS = "Llegó al tope de lo que la voz clonada dice por hoy: el panel sigue con la voz del navegador."
MENSAJE_FRECUENCIA_MNEMO = "Mnemo está recibiendo demasiadas peticiones. Espere un momento."
MENSAJE_RED = "La voz clonada no respondió: Mnemo no está disponible. Intente de nuevo."
MENSAJE_FALLO = "No se pudo generar la voz clonada. Intente de nuevo."
MENSAJE_CORTADA = "La frase se canceló."

_CODIGO_MNEMO_OK = re.compile(r"[a-z0-9]{2,12}")
_IDIOMA = re.compile(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8}){0,2}")
_MOTOR = re.compile(r"[A-Za-z0-9_.-]{1,40}")
_BASE64 = re.compile(r"[A-Za-z0-9+/]*={0,2}")
_FIRMA = re.compile(r"[A-Za-z0-9_-]{43}")


class ErrorVoz(HTTPException):
    """Lo que impide decir la frase, como lo responde la ruta: `detail` es `{codigo, mensaje}`. A mitad del flujo, el
    evento `{"tipo": "error", "codigo", "mensaje"}`."""

    def __init__(self, estado: int, codigo: str, mensaje: str, *, espera: int | None = None):
        super().__init__(estado, {"codigo": codigo, "mensaje": mensaje},
                         headers={"Retry-After": str(espera)} if espera else None)
        self.codigo, self.mensaje, self.espera = codigo, mensaje, espera

    def copia(self) -> "ErrorVoz":
        """El mismo error, nuevo (para responderlo a cada una de las peticiones de un mismo vuelo)."""
        return ErrorVoz(self.status_code, self.codigo, self.mensaje, espera=self.espera)

    def evento(self) -> dict:
        return {"tipo": "error", "codigo": self.codigo, "mensaje": self.mensaje}


def linea(ev: dict) -> bytes:
    """Un evento como una línea NDJSON (la misma forma que `bucle.linea`)."""
    return (json.dumps(ev, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8", "replace")


LATIDO = linea({"tipo": "latido"})

# ───────────────────────────── Lo que se dice ─────────────────────────────

# `paraDecir` de web/js/voz.js, en Python: lo que se dice distinto de como se escribe (las siglas y las unidades). Las
# mismas reglas, en el mismo orden y con las mismas reglas de JavaScript (una prueba corre las dos con las mismas
# frases): `\b` y `\d` de ASCII (por eso `re.ASCII`) y `\s` de JavaScript (`_S`: con los espacios de Unicode, que en
# Python con `re.ASCII` no lo serían)
_S = "[\\t\\n\\v\\f\\r \\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000\\ufeff]"
_ESPACIOS_JS = ("\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
                "\u2028\u2029\u202f\u205f\u3000\ufeff")   # lo que quita `trim()` de JavaScript
TABLA_DECIR = (
    (rf"(\d){_S}*m²", r"\1 metros cuadrados"), (rf"(\d){_S}*m³", r"\1 metros cúbicos"),
    (rf"(\d){_S}*km\b", r"\1 kilómetros"), (rf"(\d){_S}*ha\b", r"\1 hectáreas"),
    (rf"(\d){_S}*m\b(?![²³])", r"\1 metros"),
    (rf"(\d){_S}*h\b", r"\1 horas"), (rf"{_S}*%", " por ciento"),
    (r"\bNSR-10\b", "ene ese erre diez"), (r"\bRes\.", "Resolución"), (r"\bE\.S\.E\.", "e ese e"),
    (r"\bREPS\b", "reps"), (r"\bTPR\b", "te pe erre"), (r"\bBIM\b", "bim"), (r"\bIFC4\b", "i efe ce cuatro"),
    (rf"\b((?:19|20)\d\d){_S}*[–—-]{_S}*((?:19|20)\d\d)\b", r"\1 a \2"),
    (rf"≈{_S}*", "unos "), (rf"{_S}*→{_S}*", " a "),
)
_TABLA = tuple((re.compile(p, re.ASCII), por) for p, por in TABLA_DECIR)
_JUNTAR = re.compile(f"{_S}+")


def para_decir(t: Any) -> str:
    """El texto como se dice (`paraDecir` de web/js/voz.js): la pantalla muestra el original."""
    s = t if isinstance(t, str) else ("" if t is None else str(t))
    for patron, por in _TABLA:
        s = patron.sub(por, s)
    return _JUNTAR.sub(" ", s).strip(_ESPACIOS_JS)


_NO_SE_OYEN = frozenset({"Cc", "Cf", "Cs", "Co", "Cn"})
_SALTOS = frozenset("\t\n\r\v\f\u2028\u2029")


def audible(t: str) -> str:
    """El texto sin lo que no se ve ni se oye: caracteres de control, de formato (el espacio de ancho cero, las marcas
    de dirección), sustitutos sueltos, de uso privado o sin asignar; los saltos de renglón, como espacios. Es lo que se
    revisa (`hablable`) y lo que se le manda a Mnemo: un número partido por un carácter invisible se mira entero."""
    return "".join(" " if c in _SALTOS else c for c in t if c in _SALTOS
                   or unicodedata.category(c) not in _NO_SE_OYEN)


def hablable(t: Any) -> bool:
    """¿Se puede decir en voz alta ante una sala? Lo dicho es como lo proyectado (`proyectable.texto_proyectable`):
    sin «@» (un correo, un usuario) ni números de 7 o más dígitos (cédulas, teléfonos), buscados en la forma NFKC de lo
    que se oye (`audible`); y con algo que decir (una letra o un dígito). Los costos sí se pueden decir: una respuesta
    puede hablar de plata."""
    if not isinstance(t, str):
        return False
    k = " ".join(unicodedata.normalize("NFKC", audible(t)).split())
    return bool(k) and "@" not in k and numero_largo(k) is None and any(c.isalnum() for c in k)


# ───────────────────────────── La firma de las frases de una respuesta ─────────────────────────────

def llave_respuestas(cfg: Any) -> bytes:
    """La clave con que el servidor firma las frases de las respuestas habladas: derivada de la del administrador
    (`seguridad.llave_mnemo`, que no está en la base) con su propia etiqueta. La primera vez en el proceso hace la
    derivación lenta: desde código asíncrono, con `run_in_threadpool`."""
    return hmac.new(seguridad.llave_mnemo(cfg), ETIQUETA_FIRMA, hashlib.sha256).digest()


def firmar(llave: bytes, uid: Any, cid: Any, texto: str) -> str:
    """La firma de una frase de la respuesta de la conversación `cid` de `uid`: HMAC-SHA256 de `uid␟cid␟texto`, en
    base64url sin relleno (43 caracteres)."""
    mac = hmac.new(llave, f"{uid}\x1f{cid}\x1f{texto}".encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).rstrip(b"=").decode("ascii")


def firma_valida(llave: bytes, uid: Any, cid: Any, texto: str, firma: Any) -> bool:
    return isinstance(firma, str) and bool(_FIRMA.fullmatch(firma)) and hmac.compare_digest(
        firmar(llave, uid, cid, texto), firma)


# ───────────────────────────── Las frases de una respuesta hablada ─────────────────────────────

MIN_FRASE = 24       # una frase más corta sigue con la siguiente («Sí.», «Listo:»…)
MAX_FRASE = 260      # sin un punto antes, se corta en una coma o en un espacio
_TERMINA = ".?!:;…"
_CIERRES = ")]»\"'”’"
_BLANCOS = " \t\n"
_ABREVIATURA = re.compile(r"(?:^|[^\w])(?:(?:[A-ZÁÉÍÓÚÑ]\.){2,}|[A-ZÁÉÍÓÚÑ]\.|(?:Res|art|Art|núm|Núm|No|Nro|Dr|Dra|"
                          r"Sr|Sra|Srta|Ing|Lic|etc|aprox|pág|Pág|tel|Tel|Av|Cra|Cl|Mz|Ud|Uds|ej|Ej|vs)\.)$")
_FENCE = re.compile(r"^\s*(?:```|~~~)")
_REGLA = re.compile(r"^(?:[-*_]\s*){3,}$")
_ENCABEZADO = re.compile(r"^#{1,6}\s+")
_CITA = re.compile(r"^(?:>\s?)+")
_VINETA = re.compile(r"^(?:[-*+•]\s+|\d{1,3}[.)]\s+)")
_IMAGEN = re.compile(r"!\[[^\]\n]*\]\([^)\s]*\)")
_ENLACE = re.compile(r"\[([^\]\n]*)\]\([^)\s]*\)")
_CORCHETES = re.compile(r"\[([^\]\n]*)\](?=[^(]|$)")
_CODIGO = re.compile(r"`[^`\n]*`")
_ETIQUETA = re.compile(r"<[^>\n]*>")
_URL = re.compile(r"(?:https?://|www\.)\S*[^\s.,;:!?…)\]»\"'”’]", re.IGNORECASE)   # sin la puntuación que la sigue
_RUTA = re.compile(r"(?<![\w/.])/[A-Za-z_][\w-]*(?:/[\w.-]+)*/?")
_MASCARA = re.compile(r"[·•∙]{2,}\s*\d*")
_ENFASIS = re.compile(r"\*+|~~|__|(?<!\w)_+|_+(?!\w)")
_VACIOS = re.compile(r"\(\s*\)|\[\s*\]")   # los paréntesis que se quedaron sin nada (tenían una dirección)
# Dónde se quitó algo (una dirección, una ruta, un código…) mientras se limpia un renglón: si lo quitado iba justo antes
# de un signo, el espacio que lo precedía sobra («la ficha o https://…/x.» → «la ficha o.»), salvo tras el final de
# una frase (que ya pudo cortarse: lo cortado no cambia cuando llega más texto)
_QUITADO = "\x00"
_PEGADO = re.compile(r"(?<=[^\s.?!:;…])\s+\x00+(?=[.,;:!?…])")
_ABIERTO_ENLACE = re.compile(r"!?\[")


def _abierto(s: str) -> int:
    """Dónde empieza lo que todavía no se cerró en un renglón a medio llegar (un enlace o un corchete sin cerrar, un
    código entre comillas invertidas, una etiqueta): lo de ahí en adelante todavía no se sabe cómo se dice."""
    corte = len(s)
    for m in _ABIERTO_ENLACE.finditer(s):
        i = m.start()
        resto = s[i + (1 if s[i] == "!" else 0):]
        if not (_ENLACE.match(resto) or _CORCHETES.match(resto)) or (resto.find("]") == len(resto) - 1):
            corte = min(corte, i)
            break
    if s.count("`") % 2:
        corte = min(corte, s.rfind("`"))
    abre = s.rfind("<")
    if abre >= 0 and ">" not in s[abre:]:
        corte = min(corte, abre)
    return corte


def _limpiar(s: str) -> str:
    """Un renglón de Markdown como se dice: los enlaces, su texto; sin imágenes, código, etiquetas, direcciones web,
    rutas del panel («/personas/123»), datos enmascarados («···123») ni marcas de énfasis."""
    s = _IMAGEN.sub(_QUITADO, s.replace(_QUITADO, ""))
    s = _ENLACE.sub(r"\1", s)
    s = _CORCHETES.sub(r"\1", s)
    for patron in (_CODIGO, _ETIQUETA, _URL, _RUTA, _MASCARA):
        s = patron.sub(_QUITADO, s)
    s = _PEGADO.sub("", s).replace(_QUITADO, "")
    s = _VACIOS.sub("", s)
    s = _ENFASIS.sub("", s)
    return " ".join(s.split())


def _plano(texto: str, final: bool) -> str:
    """El texto de una ronda como se dice, renglón por renglón (separados por «\\n»): sin bloques de código, tablas ni
    reglas; los encabezados, las citas y las viñetas sin su marca. Sin `final`, el último renglón todavía está llegando:
    va sin su última palabra (puede crecer: «vivien» → «viviendas», o ser una dirección web) ni lo que no se cerró."""
    lineas = texto.split("\n")
    salida: list[str] = []
    en_codigo = False
    for i, cruda in enumerate(lineas):
        incompleta = not final and i == len(lineas) - 1
        s = cruda.strip()
        # (lo que no se dice deja su renglón vacío: el anterior sigue terminado en un salto de renglón, como cuando
        # llegue lo que sigue, y la frase que ya cortó no cambia)
        if _FENCE.match(s):
            en_codigo = not en_codigo
            salida.append("")
            continue
        if en_codigo or s.startswith("|") or _REGLA.fullmatch(s):
            salida.append("")
            continue
        # Lo que puede ser el comienzo de un bloque que no se dice («`», «~», «-», «*», «_»: código o una regla)
        if incompleta and (not s or set(s) <= set("`~-*_ ")):
            salida.append("")
            continue
        # Sin las marcas del comienzo (encabezado, cita, viñeta), que se reconocen por el espacio que las sigue: así
        # «1. » a medio llegar ya es una viñeta y no una frase que termina en «1.»
        t = _VINETA.sub("", _CITA.sub("", _ENCABEZADO.sub("", cruda.lstrip())))
        espacio = False   # el renglón a medio llegar termina en un espacio: lo último ya es una palabra entera
        s = t.strip()
        if incompleta and s:
            if t[-1:].isspace():
                espacio = True
            else:  # sin la última palabra, pero con el espacio que la separaba (lo de antes ya es una palabra entera)
                corte = max(s.rfind(" "), s.rfind("\t"))
                s, espacio = (s[:corte], True) if corte >= 0 else ("", False)
            abierto = _abierto(s)
            if abierto < len(s):  # (si lo abierto iba tras un espacio, lo de antes ya terminó en una palabra entera)
                s, espacio = s[:abierto], s[:abierto][-1:].isspace()
        s = _limpiar(s)
        # (el espacio del final se conserva: un punto ahí ya cierra la frase, como lo hará con lo que siga)
        salida.append(s + " " if espacio and s else s)
    return "\n".join(salida)


def _abreviatura(previo: str) -> bool:
    return bool(_ABREVIATURA.search(previo))


def _cortar(plano: str, final: bool) -> list[str]:
    """Las frases de `plano`: se corta tras «.», «?», «!», «:», «;» o «…» seguidos de un espacio o de un salto de
    renglón, y en un salto de renglón, si la frase ya tiene `MIN_FRASE` caracteres (si no, sigue con lo que viene; un
    renglón corto, como un título, se cierra con un punto); nunca tras una abreviatura o una sigla («Sr.», «E.S.E.»).
    Una frase que llega a `MAX_FRASE` sin un corte se corta en la última coma (o punto y coma) o, si no hay, en el
    último espacio. Sin `final`, lo que queda al final sin cortar todavía no es una frase. Cada decisión depende solo de
    lo anterior y del carácter que sigue: las frases ya cortadas no cambian cuando llega más texto."""
    frases: list[str] = []
    buf = ""
    i, n = 0, len(plano)
    while i < n:
        c = plano[i]
        if c == "\n":
            limpio = buf.strip()
            if len(limpio) >= MIN_FRASE:
                frases.append(buf)
                buf = ""
            elif limpio:
                buf = limpio + ("" if limpio[-1] in _TERMINA + "," else ".") + " "
            i += 1
            continue
        if c in ".,;:" and not buf.strip():   # un signo suelto al comienzo de una frase no se dice
            i += 1
            continue
        buf += c
        if c in _TERMINA:
            j = i + 1
            while j < n and plano[j] in _CIERRES:
                j += 1
            if j < n and plano[j] in _BLANCOS:
                cerrada = buf + plano[i + 1:j]
                if len(cerrada.strip()) >= MIN_FRASE and not (c == "." and _abreviatura(buf)):
                    frases.append(cerrada)
                    buf = ""
                    i = j
                    continue
        if len(buf) > MAX_FRASE:
            ventana = buf[:MAX_FRASE]
            k = max(ventana.rfind(", "), ventana.rfind("; "))
            k = k + 1 if k + 1 >= MIN_FRASE else -1
            if k < 0:
                k = ventana.rfind(" ")
                k = k if k >= MIN_FRASE else MAX_FRASE
            frases.append(buf[:k])
            buf = buf[k:]
        i += 1
    if final and buf.strip():
        frases.append(buf)
    return [" ".join(f.split()) for f in frases]


def frases_de(texto: str, final: bool = True) -> list[str]:
    """Las frases que se dicen de `texto` (el de una ronda del asistente, en Markdown): `_plano`, `_cortar` y, de lo
    que queda, solo lo que se puede decir (`hablable`); lo demás se salta."""
    return [f for f in _cortar(_plano(texto if isinstance(texto, str) else "", final), final) if hablable(f)]


class Frases:
    """Las frases de una respuesta hablada mientras el modelo escribe (`bucle.Turno`, solo si el mensaje lo pidió con
    `contexto.voz`, la voz clonada está disponible para esa persona y lee respuestas, y la conversación no trae datos de
    habitantes). Cada método devuelve los eventos que el turno emite:

    * `{"tipo": "frase", "n", "texto", "firma"}` — una frase cerrada (`n`: su número en el turno, desde 0), con la firma
      con que el navegador la pide a `POST /api/agente/voz` (`firmar`).
    * `{"tipo": "frases_descartar", "desde"}` — las frases desde la `desde` ya no valen (la ronda se descartó o su texto
      final no es el que se venía diciendo): el navegador deja de decirlas, y las que siguen vuelven a numerarse desde
      ahí.

    `agregar(trozo)` con cada `texto`; `reemplazar(texto)` con un `texto_ronda` (rehace las frases contra el texto
    final: emite solo las nuevas o, si lo ya emitido no es el comienzo, descarta desde donde cambió); `cerrar_ronda()`
    cuando la ronda terminó bien (emite lo que quedaba); `descartar()` cuando se descarta (`descartar` del turno)."""

    def __init__(self, firmar_frase: Callable[[str], str]):
        self.firmar = firmar_frase
        self.emitidas: list[str] = []
        self.inicio_ronda = 0
        self.texto = ""

    def _sincronizar(self, final: bool) -> list[dict]:
        nuevas = frases_de(self.texto, final)
        actuales = self.emitidas[self.inicio_ronda:]
        p = 0
        while p < len(actuales) and p < len(nuevas) and actuales[p] == nuevas[p]:
            p += 1
        eventos: list[dict] = []
        if p < len(actuales) and not final and p == len(nuevas):
            # Faltan frases ya dichas pero ninguna cambió: lo último a medio llegar (un código o un enlace sin cerrar)
            # las dejó sin terminar por ahora. Se espera a lo que sigue; al cerrar la ronda se decide
            return eventos
        if p < len(actuales):
            desde = self.inicio_ronda + p
            del self.emitidas[desde:]
            eventos.append({"tipo": "frases_descartar", "desde": desde})
        for f in nuevas[p:]:
            eventos.append({"tipo": "frase", "n": len(self.emitidas), "texto": f, "firma": self.firmar(f)})
            self.emitidas.append(f)
        return eventos

    def agregar(self, trozo: Any) -> list[dict]:
        if not isinstance(trozo, str) or not trozo:
            return []
        antes = len(self.texto)
        self.texto += trozo
        # Sin algo que pueda cerrar una frase (un punto, que pudo llegar en el trozo anterior y cierra con el espacio
        # de este, o un salto de renglón) ni un renglón largo, no hace falta mirar
        ventana = self.texto[max(0, antes - 4):]
        renglon = len(self.texto) - self.texto.rfind("\n") - 1
        if not any(c in ventana for c in _TERMINA + "\n") and renglon <= MAX_FRASE:
            return []
        return self._sincronizar(False)

    def reemplazar(self, texto: Any) -> list[dict]:
        self.texto = texto if isinstance(texto, str) else ""
        return self._sincronizar(False)

    def cerrar_ronda(self) -> list[dict]:
        eventos = self._sincronizar(True)
        self.inicio_ronda, self.texto = len(self.emitidas), ""
        return eventos

    def descartar(self) -> list[dict]:
        hubo = len(self.emitidas) > self.inicio_ronda
        del self.emitidas[self.inicio_ronda:]
        self.texto = ""
        return [{"tipo": "frases_descartar", "desde": self.inicio_ronda}] if hubo else []


# ───────────────────────────── Topes ─────────────────────────────

_candado = threading.Lock()
_ventanas: dict[tuple[str, Any], deque] = {}
_en_curso: dict[tuple[str, Any], int] = {}
_diarias: dict[tuple[str, Any], tuple[str, int]] = {}
_hablando: set[object] = set()      # las llamadas a Mnemo en curso (`cupo`)


def frecuencia(base: str, uid: Any) -> None:
    """Ventana deslizante por persona (y base): `FRECUENCIA_MAX` frases por minuto; si no, 429 `frecuencia` con
    `Retry-After`. En memoria y por proceso."""
    ahora = time.monotonic()
    with _candado:
        if len(_ventanas) > 5000:
            for k in [k for k, v in _ventanas.items() if not v or v[-1] <= ahora - FRECUENCIA_S]:
                del _ventanas[k]
        v = _ventanas.setdefault((base, uid), deque())
        while v and v[0] <= ahora - FRECUENCIA_S:
            v.popleft()
        if len(v) >= FRECUENCIA_MAX:
            raise ErrorVoz(429, "frecuencia", MENSAJE_FRECUENCIA, espera=max(1, math.ceil(v[0] + FRECUENCIA_S - ahora)))
        v.append(ahora)


class Ficha:
    """Uno de los `A_LA_VEZ_PERSONA` lugares de una persona (`tomar`): se suelta una sola vez, pase lo que pase."""

    def __init__(self, clave: tuple[str, Any]):
        self.clave, self.suelta = clave, False

    def soltar(self) -> None:
        with _candado:
            if self.suelta:
                return
            self.suelta = True
            n = _en_curso.get(self.clave, 0) - 1
            if n > 0:
                _en_curso[self.clave] = n
            else:
                _en_curso.pop(self.clave, None)


def tomar(base: str, uid: Any) -> Ficha:
    """Un lugar de la persona (y base) mientras dura su frase (de que llega la petición a que termina el flujo): como
    mucho `A_LA_VEZ_PERSONA`; si no, 429 `frecuencia` con `Retry-After`."""
    clave = (base, uid)
    with _candado:
        if _en_curso.get(clave, 0) >= A_LA_VEZ_PERSONA:
            raise ErrorVoz(429, "frecuencia", MENSAJE_A_LA_VEZ, espera=ESPERA_TURNO_S)
        _en_curso[clave] = _en_curso.get(clave, 0) + 1
    return Ficha(clave)


def diarias(base: str, uid: Any, caracteres: int) -> None:
    """Suma `caracteres` a lo que la persona hizo decir hoy a Mnemo (hora de Colombia): a lo sumo `CARACTERES_DIA`; si
    no, 429 `volumen` (y no se suma)."""
    dia = modelo.hoy_local().isoformat()
    with _candado:
        if len(_diarias) > 5000:
            for k in [k for k, v in _diarias.items() if v[0] != dia]:
                del _diarias[k]
        d, n = _diarias.get((base, uid), (dia, 0))
        n = n if d == dia else 0
        if n + caracteres > CARACTERES_DIA:
            raise ErrorVoz(429, "volumen", MENSAJE_DIARIAS)
        _diarias[(base, uid)] = (dia, n + caracteres)


@asynccontextmanager
async def cupo() -> AsyncIterator[None]:
    """Uno de los `A_LA_VEZ` cupos del proceso para llamar a Mnemo, mientras dura el bloque. Si no hay, espera hasta
    `ESPERA_CUPO_S` y después 429 `frecuencia`. Se suelta pase lo que pase (también si se cancela)."""
    ficha = object()
    hasta = time.monotonic() + ESPERA_CUPO_S
    while True:
        with _candado:
            if len(_hablando) < A_LA_VEZ:
                _hablando.add(ficha)
                break
        if time.monotonic() >= hasta:
            raise ErrorVoz(429, "frecuencia", MENSAJE_OCUPADO, espera=ESPERA_TURNO_S)
        await asyncio.sleep(VIGILA_S)
    try:
        yield
    finally:
        with _candado:
            _hablando.discard(ficha)


# ───────────────────────────── ¿Se puede? ─────────────────────────────

def _preparar(app: Any) -> tuple[dict, Any, str]:
    """(la conexión con Mnemo como la muestra `mnemo_conexion.vista`, el cliente o None, la huella de la cuenta
    conectada). Lee MongoDB: desde código asíncrono, con `run_in_threadpool`. Las pruebas la cambian."""
    db = app.state.db
    return mnemo_conexion.vista(db), mc.cliente_de(app), mnemo_conexion.huella_cuenta(db)


def _recordado(app: Any, conexion: dict, voz: str) -> bool:
    sin = getattr(getattr(app, "state", None), "voz_sin", None)
    return (isinstance(sin, tuple) and len(sin) == 3 and sin[0] == conexion.get("desde") and sin[1] == voz
            and time.monotonic() - sin[2] < OLVIDO_S)


def _recordar(app: Any, conexion: dict, voz: str, sin: bool) -> None:
    """Anota (o borra) que Mnemo respondió, con esta conexión y esta voz, que no puede hablar."""
    try:
        if sin:
            app.state.voz_sin = (conexion.get("desde"), voz, time.monotonic())
        elif getattr(app.state, "voz_sin", None) is not None:
            app.state.voz_sin = None
    except Exception:  # noqa: BLE001 - es solo una pista para la interfaz
        pass


def puede(app: Any, conexion: Any, ajustes_voz: dict, huella: str) -> bool:
    """¿Esta instalación puede hablar ahora con la voz clonada elegida? Motor «mnemo» con una voz elegida con la cuenta
    conectada (`huella`), una conexión «conectada» con `mnemo:voice`, y Mnemo no dijo hace poco, con esta conexión y
    esta voz, que no puede. No mira el rol: eso es `estado_de`."""
    if not isinstance(conexion, dict) or conexion.get("estado") != "conectada" or conexion.get("voz") is not True:
        return False
    if ajustes_voz.get("motor") != "mnemo" or not ajustes_voz.get("voz") or ajustes_voz.get("cuenta") != huella:
        return False
    return not _recordado(app, conexion, ajustes_voz["voz"])


def estado_de(app: Any, db: Any, quien: Any, ajustes: dict, conexion: dict) -> dict:
    """`voz` de `GET /api/agente/estado`: `{"disponible": bool (esta persona puede hacer sonar la voz clonada: `puede` y
    su rol en `agente_voz.roles`), "nombre": el de la voz | None, "respuestas": bool (la voz lee las respuestas del
    asistente: disponible y `agente_voz.respuestas`), "automatica": bool (narra también la presentación automática:
    disponible y `agente_voz.automatica`)}`. Sin la voz, todo en falso: el panel usa la del navegador. Lee MongoDB (la
    huella de la cuenta) solo si hace falta."""
    av = ajustes.get("agente_voz") if isinstance(ajustes.get("agente_voz"), dict) else politica.ajustes_voz(ajustes)
    disponible = False
    if (av["motor"] == "mnemo" and av["voz"] and getattr(quien, "rol", None) in av["roles"]
            and isinstance(conexion, dict) and conexion.get("estado") == "conectada" and conexion.get("voz") is True):
        disponible = puede(app, conexion, av, mnemo_conexion.huella_cuenta(db))
    return {"disponible": disponible, "nombre": (av["nombre"] or None) if disponible else None,
            "respuestas": disponible and av["respuestas"], "automatica": disponible and av["automatica"]}


def respuestas_para(app: Any, quien: Any, ajustes: dict) -> bool:
    """¿Las respuestas del asistente a esta persona se leen con la voz clonada? (`estado_de` disponible y
    `agente_voz.respuestas`). Lee MongoDB: desde código asíncrono, con `run_in_threadpool`."""
    db = app.state.db
    e = estado_de(app, db, quien, ajustes, mnemo_conexion.vista(db))
    return e["disponible"] and e["respuestas"]


# ───────────────────────────── Mnemo ─────────────────────────────

def _de_mnemo(e: ErrorHerramienta) -> tuple[str, dict]:
    """(código de Mnemo, `details`) de un error que devolvió Mnemo (`isError`); ("", {}) si es otra cosa."""
    if e.codigo == mc.COD_MNEMO and isinstance(e.detalle, dict):
        codigo, detalles = e.detalle.get("code"), e.detalle.get("details")
        return (codigo if isinstance(codigo, str) else ""), (detalles if isinstance(detalles, dict) else {})
    return "", {}


def traducir(e: ErrorHerramienta) -> tuple[ErrorVoz, bool]:
    """Un fallo de la llamada a Mnemo como lo responde la ruta, y si hay que recordar que esta conexión no puede hablar
    con esa voz (`OLVIDO_S`). Los mensajes son propios: nunca el texto de Mnemo."""
    if e.codigo == mc.COD_TOKEN:
        if isinstance(e.detalle, dict) and e.detalle.get("conexion") == "cambio":  # cambió a mitad: es pasajero
            return ErrorVoz(502, "mnemo_red", MENSAJE_RED), False
        # la conexión venció o se revocó (401), o le falta el alcance (403)
        return ErrorVoz(409, SIN_VOZ, MENSAJE_SIN_PERMISO if e.estado == 403 else MENSAJE_SIN_CONEXION), False
    if e.codigo == mc.COD_NO_DISPONIBLE:  # ese Mnemo no ofrece la herramienta a esta conexión
        return ErrorVoz(409, SIN_VOZ, MENSAJE_SIN_HERRAMIENTA), True
    if e.codigo in (mc.COD_RED, mc.COD_PLAZO):
        return ErrorVoz(502, "mnemo_red", MENSAJE_RED), False
    codigo, detalles = _de_mnemo(e)
    if codigo == "NO_VOICE":
        return ErrorVoz(409, SIN_VOZ, MENSAJE_SIN_ESA_VOZ), True
    if codigo == "PLAN_REQUIRED":
        return ErrorVoz(409, SIN_VOZ, MENSAJE_SIN_PLAN), True
    if codigo == "UNAVAILABLE":  # sin con qué generar la voz (`reason: "speech"`); sin razón, el proveedor caído
        return ErrorVoz(409, SIN_VOZ, MENSAJE_NO_HABLA), detalles.get("reason") == "speech"
    if codigo == "CREDITS_EXHAUSTED":
        return ErrorVoz(402, "mnemo_creditos", MENSAJE_CREDITOS), False
    if codigo == "RATE_LIMITED" or (not codigo and e.estado == 429):
        return ErrorVoz(429, "frecuencia", MENSAJE_FRECUENCIA_MNEMO, espera=30), False
    if codigo == "INVALID_ARGUMENT":
        return ErrorVoz(422, "texto", MENSAJE_TEXTO), False
    if codigo == "TIMEOUT":
        return ErrorVoz(502, "mnemo_red", MENSAJE_RED), False
    return ErrorVoz(502, "mnemo", MENSAJE_FALLO), False


def _texto_corto(v: Any, patron: re.Pattern, defecto: str | None = None) -> str | None:
    return v if isinstance(v, str) and patron.fullmatch(v) else defecto


async def listar(app: Any) -> dict:
    """`GET /api/agente/voces`: las voces de la cuenta conectada que se pueden usar desde el panel
    (`mnemo_list_voices`): `{"voces": [{"id", "nombre", "idioma", "motor"}], "elegida": la de `agente_voz` (si está
    entre ellas y es de esta cuenta) | None, "conexion": {"voz": bool, "ofrece_voz": bool}}`. Sin conexión o sin
    `mnemo:voice`, sin voces (y sin preguntarle nada a Mnemo). Lo que falla en Mnemo sale como `ErrorVoz`."""
    db = app.state.db
    conexion, cliente, huella = await run_in_threadpool(_preparar, app)
    ajustes, _ = await run_in_threadpool(politica.leer, db)
    av = ajustes["agente_voz"]
    info = {"voz": conexion.get("voz") is True, "ofrece_voz": conexion.get("ofrece_voz") is not False}
    if cliente is None or conexion.get("estado") != "conectada" or not info["voz"]:
        return {"voces": [], "elegida": None, "conexion": info}
    try:
        res = await cliente.llamar(HERRAMIENTA_VOCES, {}, PLAZO_VOCES_S)
    except ErrorHerramienta as e:
        error, recordar = traducir(e)
        log.info("Voz: no se listaron las voces (%s)", error.codigo)
        if recordar and av["voz"]:
            _recordar(app, conexion, av["voz"], True)
        raise error from None
    datos = res.get("structuredContent") if isinstance(res, dict) else None
    crudas = datos.get("voices") if isinstance(datos, dict) else None
    if not isinstance(crudas, list):
        log.warning("Voz: la respuesta de Mnemo no trae las voces")
        raise ErrorVoz(502, "mnemo", MENSAJE_FALLO)
    voces, vistas = [], set()
    for v in crudas:
        if not isinstance(v, dict) or v.get("status", "ready") != "ready":
            continue
        vid = _texto_corto(v.get("voice_id"), politica.ID_VOZ)
        if vid is None or vid in vistas:
            continue
        vistas.add(vid)
        voces.append({"id": vid, "nombre": politica.nombre_de_voz(v.get("name")) or "Voz sin nombre",
                      "idioma": _texto_corto(v.get("language"), _IDIOMA, "es"),
                      "motor": _texto_corto(v.get("engine"), _MOTOR, "")})
        if len(voces) >= MAX_VOCES:
            break
    elegida = next((v for v in voces if v["id"] == av["voz"]), None) if av["voz"] and av["cuenta"] == huella else None
    if elegida is not None:  # Mnemo la ofrece otra vez (se volvió a marcar para apps, cambió el plan): se olvida el «no»
        _recordar(app, conexion, av["voz"], False)
    return {"voces": voces, "elegida": elegida, "conexion": info}


# ───────────────────────────── La caché y los vuelos ─────────────────────────────

class _Entrada:
    __slots__ = ("inicio", "trozos", "bytes", "peso", "vence")

    def __init__(self, inicio: dict, trozos: tuple[str, ...], n_bytes: int, vence: float):
        self.inicio, self.trozos, self.bytes, self.vence = inicio, trozos, n_bytes, vence
        self.peso = sum(len(t) for t in trozos) + 200


class Cache:
    """El audio de la narración y de la prueba, en memoria: LRU por lo que ocupa (`maximo`, en caracteres de base64),
    con vida (`vida` segundos). Se vacía al cambiar de voz (`de_voz`). Nunca guarda respuestas del asistente."""

    def __init__(self, maximo: int = CACHE_BYTES, vida: float = CACHE_S, reloj: Callable[[], float] = time.monotonic):
        self.maximo, self.vida, self.reloj = maximo, vida, reloj
        self._d: OrderedDict[str, _Entrada] = OrderedDict()
        self.peso = 0
        self.voz: str | None = None
        self._candado = threading.Lock()

    def __len__(self) -> int:
        return len(self._d)

    def vaciar(self) -> None:
        with self._candado:
            self._d.clear()
            self.peso = 0

    def de_voz(self, voz: str) -> None:
        """La caché es de una sola voz: si cambió, se vacía."""
        with self._candado:
            if voz != self.voz:
                self._d.clear()
                self.peso, self.voz = 0, voz

    def leer(self, clave: str) -> _Entrada | None:
        with self._candado:
            e = self._d.get(clave)
            if e is None:
                return None
            if e.vence <= self.reloj():
                del self._d[clave]
                self.peso -= e.peso
                return None
            self._d.move_to_end(clave)
            return e

    def guardar(self, clave: str, inicio: dict, trozos: list[str], n_bytes: int) -> bool:
        e = _Entrada(dict(inicio), tuple(trozos), n_bytes, self.reloj() + self.vida)
        if e.peso > self.maximo:
            return False
        with self._candado:
            viejo = self._d.pop(clave, None)
            if viejo is not None:
                self.peso -= viejo.peso
            self._d[clave] = e
            self.peso += e.peso
            while self.peso > self.maximo and self._d:
                _, fuera = self._d.popitem(last=False)
                self.peso -= fuera.peso
        return True


_CREAR = threading.Lock()


def cache_de(app: Any) -> Cache:
    with _CREAR:
        c = getattr(app.state, "voz_cache", None)
        if c is None:
            c = app.state.voz_cache = Cache()
        return c


def vuelos_de(app: Any) -> dict:
    with _CREAR:
        v = getattr(app.state, "voz_vuelos", None)
        if v is None:
            v = app.state.voz_vuelos = {}
        return v


def clave_de(voz: str, dicho: str, de: str | None = None) -> str:
    """La clave de una frase: `sha256(voz␟formato␟texto dicho)` (la de la caché); para una respuesta (`de`: quién y de
    qué conversación) se le antepone eso, y nunca va a la caché: solo une las peticiones iguales a la vez."""
    base = f"{voz}\x1f{FORMATO}\x1f{dicho}"
    return hashlib.sha256((f"{de}\x1f{base}" if de else base).encode("utf-8")).hexdigest()


def _entero(v: Any, lo: int, hi: int) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi else None


def _inicio_de(d: Any) -> dict:
    """`{"formato", "muestreo", "canales"}` del aviso `start` de Mnemo (o de su salida final). PCM («pcm_s16le…») va
    como «pcm_s16le» con su frecuencia (por omisión, 24 000) y sus canales (1); otro formato (mp3, wav), tal cual: el
    navegador decodifica la frase entera."""
    d = d if isinstance(d, dict) else {}
    formato = d.get("format")
    muestreo, canales = _entero(d.get("sample_rate"), 8000, 192000), _entero(d.get("channels"), 1, 2)
    if not isinstance(formato, str) or formato.startswith("pcm"):
        sufijo = re.fullmatch(r"pcm_s16le_(\d{4,6})", formato or "")
        return {"formato": "pcm_s16le", "muestreo": muestreo or (int(sufijo.group(1)) if sufijo else 24000),
                "canales": canales or 1}
    return {"formato": formato if _CODIGO_MNEMO_OK.fullmatch(formato) else "desconocido", "muestreo": muestreo,
            "canales": canales}


class Vuelo:
    """Una frase en camino (o ya hecha, si sale de la caché): lo que va llegando de Mnemo, para todas las peticiones
    que la esperan (`oyentes`). Vive en el bucle de eventos que la creó."""

    def __init__(self, clave: str, guardar: bool):
        self.clave, self.guardar = clave, guardar
        self.bucle = asyncio.get_running_loop()
        self.inicio: dict | None = None
        self.trozos: list[str] = []
        self.bytes = 0
        self.ms_mnemo: int | None = None
        self.error: ErrorVoz | None = None
        self.terminado = False
        self.de_cache = False
        self.oyentes = 0
        self.tarea: asyncio.Task | None = None
        self._aviso = asyncio.Event()

    @classmethod
    def de_la_cache(cls, clave: str, e: _Entrada) -> "Vuelo":
        v = cls(clave, False)
        v.inicio, v.trozos, v.bytes, v.terminado, v.de_cache = dict(e.inicio), list(e.trozos), e.bytes, True, True
        return v

    @property
    def aviso(self) -> asyncio.Event:
        """El aviso del próximo cambio: hay que tomarlo ANTES de mirar el estado (así no se pierde ninguno)."""
        return self._aviso

    def _avisar(self) -> None:
        ev, self._aviso = self._aviso, asyncio.Event()
        ev.set()

    def empezar(self, inicio: dict) -> None:
        if self.inicio is None:
            self.inicio = inicio
            self._avisar()

    def agregar(self, datos: str, n_bytes: int) -> None:
        if self.inicio is None:
            self.inicio = _inicio_de({})
        if self.bytes + n_bytes > MAX_AUDIO:
            raise ErrorVoz(502, "mnemo", MENSAJE_FALLO)
        self.trozos.append(datos)
        self.bytes += n_bytes
        self._avisar()

    def terminar(self) -> None:
        self.terminado = True
        self._avisar()

    def fallar(self, error: ErrorVoz) -> None:
        if not self.terminado:
            self.error, self.terminado = error, True
            self._avisar()

    def al_progreso(self, p: dict) -> None:
        """Un aviso de `mnemo_speak`: `start` (el formato) o `audio` (un trozo en base64, que se pasa tal cual). Lo que
        no tiene esa forma se ignora."""
        mensaje = p.get("message") if isinstance(p, dict) else None
        if not isinstance(mensaje, str) or not mensaje.startswith("{"):
            return
        try:
            d = json.loads(mensaje)
        except (ValueError, RecursionError):
            return
        if not isinstance(d, dict):
            return
        if d.get("type") == "start":
            self.empezar(_inicio_de(d))
        elif d.get("type") == "audio":
            n = _bytes_de(d.get("data"))
            if n:
                self.agregar(d["data"], n)

    def cerrar_con(self, res: Any) -> None:
        """Lo que trae la salida final de `mnemo_speak`: el formato (si no llegó el `start`), cuánto tardó Mnemo en
        dar el primer audio y, si no llegó nada por el avance, el audio entero (partido en trozos de `TROZO_B64`)."""
        datos = res.get("structuredContent") if isinstance(res, dict) else None
        datos = datos if isinstance(datos, dict) else {}
        audio = datos.get("audio")
        if not self.trozos and isinstance(audio, str) and audio:
            if self.inicio is None:  # (sin audio no se empieza: el error sale antes del flujo, como JSON)
                self.empezar(_inicio_de(datos))
            for i in range(0, len(audio), TROZO_B64):
                trozo = audio[i:i + TROZO_B64]
                n = _bytes_de(trozo)
                if n:
                    self.agregar(trozo, n)
        self.ms_mnemo = _entero(datos.get("first_audio_ms"), 0, 600_000)


def _bytes_de(datos: Any) -> int:
    """Los bytes de un trozo en base64 (0 si no es base64 válido: no se pasa)."""
    if not isinstance(datos, str) or not datos or len(datos) % 4 or not _BASE64.fullmatch(datos):
        return 0
    try:
        return len(base64.b64decode(datos, validate=True))
    except (binascii.Error, ValueError):
        return 0


_TAREAS: set[asyncio.Task] = set()


def _en_fondo(coro: Awaitable[Any]) -> asyncio.Task:
    t = asyncio.ensure_future(coro)
    _TAREAS.add(t)
    t.add_done_callback(_TAREAS.discard)
    return t


async def _producir(app: Any, vuelo: Vuelo, cliente: Any, conexion: dict, voz: str, dicho: str) -> None:
    """La llamada a `mnemo_speak` de un vuelo, con un cupo del proceso: lo que llega va al vuelo y, si es narración y
    llegó entero, a la caché. Nunca lanza: lo que falla queda como el error del vuelo."""
    registro = vuelos_de(app)
    try:
        async with cupo():
            res = await cliente.llamar(HERRAMIENTA, {"voice_id": voz, "text": dicho, "format": FORMATO,
                                                     "language": IDIOMA}, PLAZO_S, vuelo.al_progreso, tope=TOPE_S)
        vuelo.cerrar_con(res)
        _recordar(app, conexion, voz, False)
        if not vuelo.trozos:
            log.warning("Voz: Mnemo no mandó audio")
            vuelo.fallar(ErrorVoz(502, "mnemo", MENSAJE_FALLO))
            return
        if vuelo.guardar:
            cache_de(app).guardar(vuelo.clave, vuelo.inicio or _inicio_de({}), vuelo.trozos, vuelo.bytes)
        vuelo.terminar()
    except ErrorHerramienta as e:
        error, recordar = traducir(e)
        log.info("Voz: no se dijo la frase (%s)", error.codigo)
        if recordar:
            _recordar(app, conexion, voz, True)
        vuelo.fallar(error)
    except ErrorVoz as e:   # el cupo del proceso, o un audio demasiado grande
        log.info("Voz: no se dijo la frase (%s)", e.codigo)
        vuelo.fallar(e)
    except asyncio.CancelledError:
        vuelo.fallar(ErrorVoz(400, "cortada", MENSAJE_CORTADA))
        raise
    except Exception as e:  # noqa: BLE001 - lo que falle queda como error del vuelo
        log.error("Voz: falló la frase (%s)", type(e).__name__)
        vuelo.fallar(ErrorVoz(502, "mnemo", MENSAJE_FALLO))
    finally:
        if registro.get(vuelo.clave) is vuelo:
            del registro[vuelo.clave]


class Oyente:
    """Una petición colgada de un vuelo, con el lugar de su persona (`Ficha`). `soltar` (una vez) suelta el lugar y, si
    nadie más escucha ese vuelo, lo cancela (Mnemo deja de generar)."""

    def __init__(self, app: Any, vuelo: Vuelo, ficha: Ficha):
        self.app, self.vuelo, self.ficha = app, vuelo, ficha
        self.suelto = False
        self.arrancado = False
        self._vigia: asyncio.TimerHandle | None = None
        vuelo.oyentes += 1

    def vigilar(self) -> None:
        """Si la respuesta no empieza a leerse en `ESPERA_ARRANQUE_S`, se suelta: un flujo que nunca empezó no corre su
        `finally` (el navegador se fue antes)."""
        self._vigia = asyncio.get_running_loop().call_later(ESPERA_ARRANQUE_S, self._sin_arrancar)

    def _sin_arrancar(self) -> None:
        if not self.arrancado:
            self.soltar()

    def arrancar(self) -> None:
        self.arrancado = True
        if self._vigia is not None:
            self._vigia.cancel()

    def soltar(self) -> None:
        if self.suelto:
            return
        self.suelto = True
        if self._vigia is not None:
            self._vigia.cancel()
        self.ficha.soltar()
        v = self.vuelo
        v.oyentes -= 1
        if v.oyentes <= 0 and not v.terminado and v.tarea is not None and not v.tarea.done():
            registro = vuelos_de(self.app)
            if registro.get(v.clave) is v:
                del registro[v.clave]
            v.tarea.cancel()


async def _hasta_empezar(vuelo: Vuelo) -> None:
    while vuelo.inicio is None and not vuelo.terminado:
        aviso = vuelo.aviso
        await aviso.wait()


async def _se_fue(request: Any) -> bool:
    """Espera a que la persona se vaya (cierre la conexión) y responde True; False si este servidor no lo sabe decir."""
    try:
        mensaje = await request.receive()
    except Exception:  # noqa: BLE001
        return False
    return isinstance(mensaje, dict) and mensaje.get("type") == "http.disconnect"


async def _mientras_siga(request: Any, trabajo: Awaitable[Any]) -> None:
    """Espera `trabajo` (que Mnemo empiece a responder) mientras la persona siga ahí; si se va antes, 400 `cortada`
    (que nadie lee)."""
    tarea = asyncio.ensure_future(trabajo)
    vigia = asyncio.ensure_future(_se_fue(request))
    try:
        await asyncio.wait({tarea, vigia}, return_when=asyncio.FIRST_COMPLETED)
        if not tarea.done() and vigia.result():
            raise ErrorVoz(400, "cortada", MENSAJE_CORTADA)
        await tarea
    finally:
        for t in (tarea, vigia):
            if not t.done():
                t.cancel()
        await asyncio.gather(tarea, vigia, return_exceptions=True)


async def _flujo(oyente: Oyente, t0: float, nombre: str) -> AsyncIterator[bytes]:
    """El cuerpo de la respuesta: `inicio`, el audio a medida que llega (lo ya producido primero: una petición que se
    colgó tarde de un vuelo no pierde nada), y `fin` o `error`. Al terminar (o si el navegador se va), suelta."""
    oyente.arrancar()
    v = oyente.vuelo
    primero: int | None = None
    try:
        inicio = v.inicio or _inicio_de({})
        yield linea({"tipo": "inicio", **inicio, "cache": v.de_cache, "voz": nombre})
        i = 0
        while True:
            aviso = v.aviso
            while i < len(v.trozos):
                if primero is None:
                    primero = int((time.monotonic() - t0) * 1000)
                yield linea({"tipo": "audio", "datos": v.trozos[i]})
                i += 1
            if v.terminado:
                break
            try:
                await asyncio.wait_for(aviso.wait(), LATIDO_S)
            except TimeoutError:
                yield LATIDO
        if v.error is not None:
            yield linea(v.error.evento())
        else:
            yield linea({"tipo": "fin", "ms_primer_audio": primero if primero is not None else
                         int((time.monotonic() - t0) * 1000), "ms_mnemo": v.ms_mnemo, "bytes": v.bytes})
    finally:
        oyente.soltar()


# ───────────────────────────── El texto de cada pedido ─────────────────────────────

def texto_de_narracion(db: Any, uid: Any, rid: str, n: int | None = None, frase: int | None = None,
                       cierre: bool = False) -> tuple[str, bool]:
    """(el texto de una frase del plan `rid` de esta persona, ¿es de la presentación automática?). El plan es el que
    tiene guardado su pantalla (`pantalla.recorrido_de`) o, con la presentación automática sonando, el último que no
    era suyo (`recorrido_previo`: «Volver a reproducir» de su tarjeta). Si no es ninguno, 409 `plan_vencido`; si la
    frase no está, 422 `texto`. El cierre: «En resumen. » y sus puntos, como lo dice `reproductor.js`. Lee MongoDB."""
    try:
        g = guion_presentacion.cargar()
    except ValueError:  # el guion del despliegue está dañado: no hay plan que valga
        g = None
    doc = pantalla.leer(db, uid) if g is not None else None
    candidatos = (pantalla.recorrido_de(doc, g), pantalla.recorrido_previo(doc, g)) if g is not None else ()
    r = next((x for x in candidatos if x and x.get("id") == rid), None)
    if r is None:
        raise ErrorVoz(409, "plan_vencido", MENSAJE_PLAN_VENCIDO)
    if cierre:
        puntos = (r.get("cierre") or {}).get("puntos") if isinstance(r.get("cierre"), dict) else None
        if not isinstance(puntos, list) or not puntos or not all(isinstance(p, str) for p in puntos):
            raise ErrorVoz(422, "texto", MENSAJE_NO_ESTA)
        return "En resumen. " + ". ".join(puntos), r.get("auto") is True
    escenas = r.get("escenas") or []
    if n is None or frase is None or not 1 <= n <= len(escenas):
        raise ErrorVoz(422, "texto", MENSAJE_NO_ESTA)
    frases = escenas[n - 1].get("frases") or []
    if not 0 <= frase < len(frases) or not isinstance(frases[frase], str):
        raise ErrorVoz(422, "texto", MENSAJE_NO_ESTA)
    return frases[frase], r.get("auto") is True


def _respuesta_valida(db: Any, cfg: Any, uid: Any, cid: int, texto: str, firma: str) -> None:
    """La frase de una respuesta: firmada por este servidor para esta persona y esta conversación (si no, 422
    `texto`), de una conversación suya que todavía existe (404 `no_existe`) y sin datos de habitantes (409
    `con_personas`). Lee MongoDB."""
    if not firma_valida(llave_respuestas(cfg), uid, cid, texto, firma):
        raise ErrorVoz(422, "texto", MENSAJE_FIRMA)
    if conv_db.de_usuario(db, cid, uid) is None:
        raise ErrorVoz(404, "no_existe", MENSAJE_NO_EXISTE)
    if conv_db.tiene_personas(db, cid):
        raise ErrorVoz(409, "con_personas", MENSAJE_CON_PERSONAS)


# ───────────────────────────── La ruta ─────────────────────────────

async def hablar(request: Any, quien: Any, pedido: dict) -> StreamingResponse:
    """`POST /api/agente/voz`. `pedido` es uno de: `{"rid", "n", "frase"}`, `{"rid", "cierre": True}` (narración),
    `{"conversacion", "texto", "firma"}` (una frase de una respuesta) o `{"prueba": True}` (solo el administrador). Lo
    que lo impide sale como `ErrorVoz` antes del flujo; después, el flujo NDJSON (ver el módulo)."""
    t0 = time.monotonic()
    app = request.app
    db, cfg = app.state.db, app.state.cfg
    ajustes, _ = await run_in_threadpool(politica.leer, db)
    av = ajustes["agente_voz"]
    prueba = pedido.get("prueba") is True
    respuesta = "conversacion" in pedido
    if prueba:
        if not quien.puede("agente.conectar"):
            raise ErrorVoz(403, "voz_rol", MENSAJE_PRUEBA_ROL)
    elif quien.rol not in av["roles"]:
        raise ErrorVoz(403, "voz_rol", MENSAJE_ROL)
    if av["motor"] != "mnemo" or not av["voz"]:
        raise ErrorVoz(409, SIN_VOZ, MENSAJE_SIN_ELEGIR)
    # El texto: siempre del servidor
    if prueba:
        texto = FRASE_PRUEBA
    elif respuesta:
        if not av["respuestas"]:
            raise ErrorVoz(409, "voz_apagada", MENSAJE_SIN_RESPUESTAS)
        texto = pedido["texto"]
        await run_in_threadpool(_respuesta_valida, db, cfg, quien.uid, pedido["conversacion"], texto,
                                pedido["firma"])
    else:
        texto, auto = await run_in_threadpool(texto_de_narracion, db, quien.uid, pedido["rid"], pedido.get("n"),
                                              pedido.get("frase"), pedido.get("cierre") is True)
        if auto and not av["automatica"]:
            raise ErrorVoz(409, "voz_apagada", MENSAJE_SIN_AUTOMATICA)
    dicho = para_decir(audible(texto))
    if not hablable(texto) or not dicho or len(dicho) > MAX_DICHO:
        raise ErrorVoz(422, "texto", MENSAJE_TEXTO)
    # La conexión: «conectada», con `mnemo:voice` y de la misma cuenta con que se eligió la voz
    conexion, cliente, huella = await run_in_threadpool(_preparar, app)
    if cliente is None or conexion.get("estado") != "conectada":
        raise ErrorVoz(409, SIN_VOZ, MENSAJE_SIN_CONEXION)
    if conexion.get("voz") is not True:  # sin `mnemo:voice`: ni se le pide a Mnemo
        raise ErrorVoz(409, SIN_VOZ, MENSAJE_SIN_PERMISO)
    if av["cuenta"] != huella:
        raise ErrorVoz(409, SIN_VOZ, MENSAJE_OTRA_CUENTA)
    # Los topes de la persona: su lugar abarca todo el flujo; la frecuencia cuenta cada frase; el tope diario, solo lo
    # que de verdad va a Mnemo
    voz = av["voz"]
    ficha = tomar(db.name, quien.uid)
    try:
        frecuencia(db.name, quien.uid)
        cache = cache_de(app)
        cache.de_voz(voz)
        guardar = not respuesta
        clave = clave_de(voz, dicho, None if guardar else f"respuesta\x1f{quien.uid}")
        bucle = asyncio.get_running_loop()
        registro = vuelos_de(app)
        entrada = cache.leer(clave) if guardar else None
        vuelo = Vuelo.de_la_cache(clave, entrada) if entrada is not None else None
        if vuelo is None:
            vuelo = registro.get(clave)
            if vuelo is None or vuelo.bucle is not bucle or vuelo.terminado:
                diarias(db.name, quien.uid, len(dicho))
                vuelo = Vuelo(clave, guardar)
                registro[clave] = vuelo
                vuelo.tarea = _en_fondo(_producir(app, vuelo, cliente, conexion, voz, dicho))
        oyente = Oyente(app, vuelo, ficha)
    except BaseException:
        ficha.soltar()
        raise
    try:
        await _mientras_siga(request, _hasta_empezar(vuelo))
        if vuelo.inicio is None and vuelo.error is not None:
            raise vuelo.error.copia()
    except BaseException:
        oyente.soltar()
        raise
    oyente.vigilar()
    return StreamingResponse(_flujo(oyente, t0, av["nombre"]), media_type="application/x-ndjson", headers=FLUJO)
