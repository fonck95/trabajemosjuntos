"""Cliente del servidor MCP remoto de Mnemo (`<base>/mcp`): Streamable HTTP sin estado, revisión 2025-11-25.

Lo usa el asistente para ofrecer las herramientas de Mnemo (`herramientas/mnemo.py`). Por qué está hecho así (el
protocolo se verificó contra el montaje de `/mcp` de Mnemo, `apps/api/src/agent-api/mcp.ts`, con su SDK MCP v2, y
contra Mnemo levantado en local):

* Todo es un POST de JSON-RPC a la misma dirección, con `Authorization: Bearer <token>`, `Content-Type:
  application/json`, `Accept: application/json, text/event-stream` (sin los dos valores Mnemo responde 406, y httpx
  manda `*/*` si no se le dice otra cosa) y `MCP-Protocol-Version`. Se usa la revisión 2025-11-25: es la que Mnemo
  prueba con clientes reales y la que manda `: keepalive` mientras una herramienta trabaja.
* La respuesta llega como SSE (un evento `message` con el JSON-RPC, quizá en varias líneas `data:`, y comentarios de
  keepalive cada 15 s) o como JSON plano (los rechazos previos: 400, 405, 406, 413, 415). Se decide por Content-Type
  y se lee con un tope de tamaño: una imagen grande cabe, un servidor desbocado no llena la memoria.
* El token: en el panel, una `mnemo_conexion.FuenteTokens` (la conexión OAuth que el administrador hizo en Ajustes →
  Asistente), que se pide en CADA envío (así una renovación vale al instante) diciéndole adónde va: la fuente solo
  lo entrega para la dirección atada a los tokens (la que va cifrada con ellos), así que cambiar la dirección en la
  base no desvía el access. Ante un 401 se le avisa (`invalidar(usado)`: renueva si el guardado sigue siendo ese) y
  el envío se repite UNA vez; si vuelve el 401, la conexión venció o se revocó y hay que volver a conectarla. Las
  pruebas (y un token personal de Mnemo) pasan un texto fijo, que no se renueva.
* `initialize` y `notifications/initialized` van una vez por cliente: el modo sin estado no los exige, pero traen las
  instrucciones del servidor (van al `system` del asistente) y la versión acordada. `tools/list` se pide con el bucle
  de `nextCursor` (Mnemo hoy lo da todo de una vez) y se guarda 10 minutos: depende de la conexión (alcances y plan),
  cambia poco y cada conversación nueva lo pide. Al vencer la caché se vuelve a iniciar, por si cambió el servidor.
* Plazos: el de lectura de httpx solo detecta una conexión muerta (el keepalive lo renueva cada 15 s), así que cada
  llamada lleva además un tope total. Al vencer se cierra la conexión, y Mnemo cancela lo que estaba haciendo. Con
  `al_progreso`, la llamada pide avance (`_meta.progressToken`): cada `notifications/progress` que llega por el SSE
  va al callback y renueva el plazo (que pasa a ser de inactividad), sin pasar de un tope total.
* El token solo viaja en la cabecera. No aparece en mensajes, registros ni en el `repr`: los errores lo dicen con
  palabras propias, lo que viene del servidor se limpia de los tokens usados y de cualquier cosa con forma de token,
  y al registro va el estado HTTP o el tipo de la excepción, nunca la petición (las excepciones de httpx la llevan,
  con sus cabeceras).
* `trust_env` queda encendido (en producción la salida puede ir por un proxy) y no se siguen redirecciones: `/mcp` no
  redirige, y una redirección pide revisar la dirección de la conexión, no llevar el token a otra parte.
* Un cliente por aplicación (`cliente_de`, en `app.state`), armado con la conexión guardada y rehecho cuando cambia
  su `version`, con un `httpx2.AsyncClient` por bucle de eventos: sus conexiones son del bucle que las abrió.
"""
from __future__ import annotations

import asyncio
import copy
import inspect
import itertools
import json
import logging
import math
import re
import secrets
import threading
import time
from collections import deque
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Union
from urllib.parse import urlsplit

import httpx2

from .herramientas.base import ErrorHerramienta

if TYPE_CHECKING:  # solo para los tipos: la conexión importa este módulo
    from .mnemo_conexion import FuenteTokens

log = logging.getLogger("panel")

PROTOCOLO = "2025-11-25"
# Las versiones con que este cliente sabe trabajar (Mnemo devuelve la pedida si está entre las suyas)
PROTOCOLOS = ("2025-11-25", "2025-06-18", "2025-03-26")
CLIENTE = {"name": "trabajemosjuntos-panel", "title": "Panel Trabajemos juntos", "version": "1.0.0"}
ACEPTA = "application/json, text/event-stream"

PLAZO_LECTURA_S = 60.0      # una herramienta de lectura (la interna de Mnemo tiene 60 s)
PLAZO_ESCRITURA_S = 120.0   # una escritura: algunas gastan modelo en Mnemo (update_document)
PLAZO_CATALOGO_S = 15.0     # initialize y cada página de tools/list: el bucle espera la lista 20 s
PLAZO_CONEXION_S = 10.0
TOPE_PROGRESO_S = 600.0     # con avance, el plazo es de inactividad: la llamada entera no pasa de esto (por defecto)
CACHE_S = 600.0
MAX_PETICION = 3_900_000    # Mnemo lee cuerpos de hasta 4 MB (`express.json({limit: "4mb"})`)
MAX_RESPUESTA = 12_000_000  # ~100 000 caracteres de texto y una imagen de hasta ~7 MB en base64
MAX_PAGINAS = 20
MAX_HERRAMIENTAS = 200
MAX_INSTRUCCIONES = 8_000   # Mnemo manda menos de 4 096; el `system` usa 2 500
MAX_TEXTO_REMOTO = 1_000    # lo que se cita de un mensaje de error del servidor

# Códigos estables de `ErrorHerramienta` (el modelo y la interfaz los distinguen)
COD_MNEMO = "mnemo"                         # Mnemo devolvió un error o algo que no es MCP
COD_TOKEN = "mnemo_token"                   # 401/403: la conexión venció, se revocó, no existe o le falta alcance
COD_PLAZO = "mnemo_plazo"                   # no respondió a tiempo
COD_RED = "mnemo_red"                       # no se pudo conectar
COD_NO_DISPONIBLE = "mnemo_no_disponible"   # la herramienta ya no está para esta conexión

MENSAJE_TOKEN = ("La conexión con Mnemo venció o se revocó: el administrador tiene que volver a conectarla en Ajustes "
                 "→ Asistente.")
MENSAJE_ALCANCE = ("La conexión con Mnemo no tiene permiso para esto (falta un permiso). El administrador puede "
                   "volver a conectarla en Ajustes → Asistente y marcarlo en Mnemo.")
MENSAJE_RED = ("No se pudo conectar con Mnemo. Puede estar caído, o la dirección MCP de la conexión no es la de su "
               "servidor (https://…/mcp).")
MENSAJE_PROTOCOLO = "Mnemo respondió algo que no es una respuesta MCP válida."
MENSAJE_GRANDE = "La respuesta de Mnemo es demasiado grande."
MENSAJE_PETICION_GRANDE = "La petición es demasiado grande para Mnemo (más de 4 MB). Mande menos de una vez."

# Cómo se le explica al modelo (y a la persona) cada código de error de Mnemo (`@mnemo/shared`, `agent-api.ts`)
EXPLICACIONES = {
    "PLAN_REQUIRED": "El plan de Mnemo de esta cuenta no incluye esto",
    "CREDITS_EXHAUSTED": "Se acabaron los créditos de Mnemo de esta cuenta",
    "STORAGE_FULL": "El almacenamiento de Mnemo está lleno: no se guardó nada",
    "NOT_FOUND": "Mnemo no encontró eso (no existe, no es de esta cuenta o es sensible)",
    "INVALID_ARGUMENT": "Mnemo rechazó los argumentos",
    "RATE_LIMITED": "Demasiadas llamadas a Mnemo en el último minuto: hay que esperar un momento",
    "FORBIDDEN": "Mnemo no permite esto con esta conexión",
    "UNAVAILABLE": "Eso no está disponible en este Mnemo",
    "TIMEOUT": "Mnemo tardó demasiado en hacerlo",
    "FAILED": "Mnemo no pudo completarlo",
    "INTERNAL": "Mnemo falló por un error interno",
}

# Lo que tiene forma de token y pudiera venir en un texto del servidor (nunca debería: es una defensa más)
_PARECE_TOKEN = re.compile(r"mnemo_pat_[A-Za-z0-9_-]+|(?i:bearer)\s+[A-Za-z0-9._~+/=-]{8,}")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_CABECERA_SEGURA = re.compile(r"[\x21-\x7e]+")
_SESION = re.compile(r"[\x21-\x7e]{1,200}")
_NO_ENCONTRADA = re.compile(r"\btool\b.*\bnot found\b", re.IGNORECASE)
_CODIGO_MNEMO = re.compile(r"[A-Z][A-Z0-9_]{0,39}")


def _plano(v: Any, tope: int) -> str | None:
    """Un texto corto del servidor (nombre, versión): solo si es texto, sin caracteres de control y acotado."""
    return _CONTROL.sub("", v)[:tope] if isinstance(v, str) else None


def _es_respuesta(m: Any, rid: Any) -> bool:
    """¿Es la respuesta (resultado o error) a la petición `rid`? Las notificaciones y las peticiones del servidor no;
    un error con `id` nulo sí (es el rechazo previo de la petición)."""
    return (isinstance(m, dict) and "method" not in m and ("result" in m or "error" in m)
            and (m.get("id") == rid or (m.get("id") is None and "error" in m)))


def _numero(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


class _Aviso:
    """Un `notifications/progress` de la llamada en curso, tal como llegó en el SSE (lo atiende `_leer_sse`)."""
    __slots__ = ("params",)

    def __init__(self, params: dict):
        self.params = params


class _Avance:
    """El avance pedido en una llamada: su `progressToken`, el callback y el plazo de inactividad (`plazo`) que cada
    aviso renueva sin pasar del final de la llamada entera (`tope`)."""

    def __init__(self, token: str, al_progreso: Callable[[dict], Any], plazo: float, tope: float):
        self.token, self.al_progreso, self.plazo, self.tope = token, al_progreso, plazo, tope
        self._reloj: Any = None
        self._bucle: asyncio.AbstractEventLoop | None = None
        self._fin = math.inf

    def armar(self, reloj: Any, bucle: asyncio.AbstractEventLoop, fin: float) -> None:
        """Ata el aviso al plazo de la petición (`asyncio.timeout`) y al final de la llamada entera."""
        self._reloj, self._bucle, self._fin = reloj, bucle, fin
        reloj.reschedule(min(bucle.time() + self.plazo, fin))

    def es_suyo(self, m: Any) -> bool:
        return (isinstance(m, dict) and m.get("method") == "notifications/progress"
                and isinstance(m.get("params"), dict) and m["params"].get("progressToken") == self.token)

    async def avisar(self, params: dict) -> None:
        """Renueva el plazo y pasa el aviso al callback: `{"progress", "total", "message"}` (lo que no tenga la forma
        esperada, None)."""
        if self._reloj is not None and self._bucle is not None:
            self._reloj.reschedule(min(self._bucle.time() + self.plazo, self._fin))
        progreso, total, mensaje = params.get("progress"), params.get("total"), params.get("message")
        r = self.al_progreso({"progress": progreso if _numero(progreso) else None,
                              "total": total if _numero(total) else None,
                              "message": mensaje if isinstance(mensaje, str) else None})
        if inspect.isawaitable(r):
            await r


# Lo que recibe `llamar(..., al_progreso=…)` por cada `notifications/progress`: `{"progress": número, "total": número |
# None, "message": texto | None}` (Mnemo manda en `message` el trozo de texto nuevo del modelo). Puede ser asíncrono.
AlProgreso = Callable[[dict], Union[None, Awaitable[None]]]


class ClienteMnemo:
    """Un servidor MCP de Mnemo con su token. Asíncrono; uno por aplicación (`cliente_de`).

    * `iniciar()` — `initialize` + `notifications/initialized` (una vez). Deja `instrucciones`, `servidor`
      (`serverInfo`) y `version` (la acordada).
    * `herramientas()` — la lista cruda de `tools/list` (todas las páginas), en caché `CACHE_S` segundos.
    * `llamar(nombre, argumentos, plazo, al_progreso=None, *, tope=None)` — `tools/call`: el `result` de MCP
      (`content`, `structuredContent`) o `ErrorHerramienta` (también cuando Mnemo responde `isError`). Sin
      `al_progreso`, `plazo` es el tope total. Con `al_progreso` (función, puede ser asíncrona), la petición lleva
      `_meta.progressToken` y cada `notifications/progress` de esa llamada llega al callback, en orden y antes del
      resultado, como `{"progress", "total", "message"}`; entonces `plazo` es el máximo SIN avance (cada aviso lo
      renueva) y `tope` (por defecto `TOPE_PROGRESO_S`) el de la llamada entera. Si el callback lanza, la llamada se
      corta con esa excepción.

    `token` es un texto fijo (pruebas, un token personal) o una `mnemo_conexion.FuenteTokens` (lo del panel): se pide
    en cada envío y, ante un 401, se invalida y se repite el envío una vez. `transporte` es para las pruebas
    (`httpx2.ASGITransport` de un servidor falso); `reloj`, para mover el tiempo. `version_conexion` lo pone
    `cliente_de`: la `version` de la conexión con que se armó."""

    def __init__(self, url: str, token: "str | FuenteTokens", *, transporte: httpx2.AsyncBaseTransport | None = None,
                 reloj: Callable[[], float] = time.monotonic):
        url = (url or "").strip().rstrip("/")
        partes = urlsplit(url)
        # Con usuario o clave en la dirección httpx mandaría además una autorización básica: no se acepta
        if partes.scheme not in ("http", "https") or not partes.hostname or "@" in partes.netloc:
            raise ValueError("La dirección del servidor MCP de Mnemo no es válida")
        self.url = url
        if isinstance(token, str) or token is None:
            self._fuente, self._fijo = None, (token or "").strip()
        else:
            self._fuente, self._fijo = token, None
        self._usados: deque[str] = deque(maxlen=4)  # los últimos tokens enviados: se tapan en lo que diga el servidor
        self._transporte = transporte
        self._reloj = reloj
        self.instrucciones: str | None = None
        self.servidor: dict | None = None
        self.version: str | None = None
        self.version_conexion: int | None = None
        self._sesion: str | None = None  # `Mcp-Session-Id`: Mnemo no la usa; un servidor con estado sí
        self._iniciado = False
        self._catalogo: list[dict] | None = None
        self._vence = 0.0
        self._ids = itertools.count(1)
        self._bucle: asyncio.AbstractEventLoop | None = None
        self._http: httpx2.AsyncClient | None = None
        self._candado: asyncio.Lock | None = None
        self._en_curso = 0
        self._retirado = False

    def __repr__(self) -> str:  # sin el token: el repr sale en trazas y registros
        return f"ClienteMnemo(url={self.url!r})"

    @property
    def origen(self) -> str:
        """`scheme://host[:puerto]` del servidor: la base de los enlaces relativos que devuelve Mnemo."""
        p = urlsplit(self.url)
        return f"{p.scheme}://{p.netloc}"

    # ───────────────────────────── Conexión ─────────────────────────────

    def _conexion(self) -> tuple[httpx2.AsyncClient, asyncio.Lock]:
        """El cliente HTTP y el candado del bucle de eventos en curso (se rehacen si cambió el bucle)."""
        bucle = asyncio.get_running_loop()
        if self._http is None or self._candado is None or self._bucle is not bucle or self._http.is_closed:
            if self._candado is None or self._bucle is not bucle:  # en el mismo bucle el candado se conserva
                self._candado = asyncio.Lock()
            self._http = httpx2.AsyncClient(
                transport=self._transporte, trust_env=True, follow_redirects=False,
                timeout=httpx2.Timeout(PLAZO_LECTURA_S, connect=PLAZO_CONEXION_S),
                headers={"user-agent": f"{CLIENTE['name']}/{CLIENTE['version']}"})
            self._bucle = bucle
        return self._http, self._candado

    async def cerrar(self) -> None:
        """Cierra las conexiones (al apagar la aplicación). Solo desde el bucle que las abrió."""
        http, self._http = self._http, None
        if http is not None and self._bucle is asyncio.get_running_loop():
            await http.aclose()

    def retirar(self) -> None:
        """Ya no es el cliente de la aplicación (`cliente_de` armó otro): cierra sus conexiones en cuanto no tenga
        peticiones en curso. Si alguien lo sigue usando (un turno que ya lo tenía), las vuelve a abrir."""
        self._retirado = True
        if self._en_curso == 0 and self._http is not None:
            try:
                bucle = asyncio.get_running_loop()
            except RuntimeError:
                return  # fuera del bucle: se cierran con la próxima petición que termine (o al recogerse)
            if bucle is self._bucle:
                bucle.create_task(self._cerrar_si_libre())

    async def _cerrar_si_libre(self) -> None:
        if self._retirado and self._en_curso == 0:  # una petición pudo empezar entre `retirar` y ahora
            await self.cerrar()

    def olvidar(self) -> None:
        """Olvida la sesión y el catálogo: lo siguiente vuelve a iniciar y a listar."""
        self._iniciado, self._sesion, self._catalogo, self._vence = False, None, None, 0.0

    async def _token(self) -> str:
        """El token de este envío: el fijo, o uno vigente de la conexión (que puede renovarse en el camino) para esta
        dirección: la fuente no lo da si no es la atada a la conexión."""
        token = self._fijo if self._fuente is None else await self._fuente.token(destino=self.url)
        if not isinstance(token, str) or not _CABECERA_SEGURA.fullmatch(token):
            raise ErrorHerramienta("El token de Mnemo tiene caracteres que no pueden ir en una cabecera HTTP.",
                                   COD_TOKEN)
        if token not in self._usados:
            self._usados.append(token)
        return token

    def _cabeceras(self, token: str) -> dict[str, str]:
        cab = {"authorization": f"Bearer {token}", "content-type": "application/json", "accept": ACEPTA,
               "mcp-protocol-version": self.version or PROTOCOLO}
        if self._sesion:
            cab["mcp-session-id"] = self._sesion
        return cab

    def _remoto(self, texto: Any, tope: int = MAX_TEXTO_REMOTO) -> str:
        """Un texto que vino del servidor, para citarlo en un error: acotado y sin nada con forma de token."""
        t = texto if isinstance(texto, str) else json.dumps(texto, ensure_ascii=False, default=str)
        for token in (self._fijo, *self._usados):
            if token:
                t = t.replace(token, "[token]")
        return _CONTROL.sub(" ", _PARECE_TOKEN.sub("[token]", t)).strip()[:tope]

    # ───────────────────────────── Protocolo ─────────────────────────────

    async def iniciar(self, forzar: bool = False) -> dict:
        """`initialize` (una vez, o de nuevo con `forzar`). Devuelve lo que se supo del servidor."""
        _, candado = self._conexion()
        async with candado:
            if forzar or not self._iniciado:
                await self._iniciar()
        return {"version": self.version, "servidor": self.servidor, "instrucciones": self.instrucciones}

    async def _iniciar(self) -> None:
        """`initialize` y `notifications/initialized` (con el candado tomado)."""
        self.olvidar()
        self.version = None
        res = await self._rpc("initialize", {"protocolVersion": PROTOCOLO, "capabilities": {},
                                             "clientInfo": dict(CLIENTE)}, PLAZO_CATALOGO_S)
        version = res.get("protocolVersion")
        if version not in PROTOCOLOS:
            log.warning("Mnemo: el servidor propuso una versión de MCP que este cliente no conoce")
            raise ErrorHerramienta("Mnemo propuso una versión del protocolo MCP que el panel no conoce.", COD_MNEMO)
        info = res.get("serverInfo") if isinstance(res.get("serverInfo"), dict) else {}
        servidor = {}
        for k in ("name", "title", "version"):
            v = _plano(info.get(k), 100)
            if v:
                servidor[k] = v
        instrucciones = (_plano(res.get("instructions"), MAX_INSTRUCCIONES) or "").strip()
        self.version, self.servidor, self.instrucciones = version, servidor, instrucciones or None
        self._iniciado = True
        try:
            await self._enviar({"jsonrpc": "2.0", "method": "notifications/initialized"}, PLAZO_CATALOGO_S)
        except ErrorHerramienta as e:  # el modo sin estado no la necesita: si falla, se sigue
            log.warning("Mnemo: no se pudo avisar el fin del inicio (%s)", e.codigo)

    async def herramientas(self, forzar: bool = False) -> list[dict]:
        """Las herramientas de `tools/list` tal como las da el servidor (solo las que tienen nombre), en su orden."""
        _, candado = self._conexion()
        async with candado:
            if forzar or self._catalogo is None or self._reloj() >= self._vence:
                if forzar or not self._iniciado or self._catalogo is not None:
                    await self._iniciar()  # al vencer la caché también se renuevan las instrucciones
                self._catalogo = await self._listar()
                self._vence = self._reloj() + CACHE_S
            return copy.deepcopy(self._catalogo)

    async def _listar(self) -> list[dict]:
        lista: list[dict] = []
        cursor: str | None = None
        vistos: set[str] = set()
        for _ in range(MAX_PAGINAS):
            res = await self._rpc("tools/list", {"cursor": cursor} if cursor else None, PLAZO_CATALOGO_S)
            tools = res.get("tools")
            if not isinstance(tools, list):
                raise ErrorHerramienta(MENSAJE_PROTOCOLO, COD_MNEMO)
            lista += [t for t in tools if isinstance(t, dict) and isinstance(t.get("name"), str)]
            if len(lista) >= MAX_HERRAMIENTAS:
                return lista[:MAX_HERRAMIENTAS]
            cursor = res.get("nextCursor")
            if not isinstance(cursor, str) or not cursor or len(cursor) > 2_000 or cursor in vistos:
                return lista  # sin más páginas (o un cursor repetido: un servidor en bucle)
            vistos.add(cursor)
        return lista

    async def llamar(self, nombre: str, argumentos: dict, plazo: float = PLAZO_LECTURA_S,
                     al_progreso: AlProgreso | None = None, *, tope: float | None = None) -> dict:
        """`tools/call` con un tope de `plazo` segundos (de inactividad si hay `al_progreso`, ver la clase). Devuelve
        el `result` de MCP; un `isError` de Mnemo (y cualquier fallo) llega como `ErrorHerramienta`."""
        if not isinstance(nombre, str) or not nombre or not isinstance(argumentos, dict):
            raise ErrorHerramienta("Llamada a Mnemo sin nombre o con argumentos que no son un objeto.", COD_MNEMO)
        if not self._iniciado:
            await self.iniciar()
        params: dict[str, Any] = {"name": nombre, "arguments": argumentos}
        avance = None
        if al_progreso is not None:
            avance = _Avance(secrets.token_hex(8), al_progreso, plazo, TOPE_PROGRESO_S if tope is None else tope)
            params["_meta"] = {"progressToken": avance.token}
        try:
            res = await self._rpc("tools/call", params, plazo, avance)
        except ErrorHerramienta as e:
            if e.codigo != COD_NO_DISPONIBLE:
                raise
            self._catalogo = None  # la próxima conversación pide la lista de nuevo
            raise ErrorHerramienta(f"Mnemo ya no ofrece la herramienta «{nombre[:64]}» con esta conexión (cambió su "
                                   "catálogo o los permisos de la conexión). Empiece una conversación nueva para ver "
                                   "las de ahora.", COD_NO_DISPONIBLE, estado=e.estado) from None
        if res.get("isError") is True:
            raise self._error_de_resultado(res, nombre)
        if not isinstance(res.get("content", []), list):
            raise ErrorHerramienta(MENSAJE_PROTOCOLO, COD_MNEMO)
        return res

    def _error_de_resultado(self, res: dict, nombre: str) -> ErrorHerramienta:
        """Un `isError` de Mnemo: `{"error": {code, message, details?}}` en el texto, o texto plano (lo que no cumple el
        esquema lo rechaza el SDK así: «Input validation error: …»)."""
        texto = "".join(b["text"] for b in res.get("content") or [] if isinstance(b, dict)
                        and b.get("type") == "text" and isinstance(b.get("text"), str))
        try:
            cuerpo = json.loads(texto)
        except (ValueError, RecursionError):
            cuerpo = None
        err = cuerpo.get("error") if isinstance(cuerpo, dict) else None
        if isinstance(err, dict):
            codigo = err.get("code") if isinstance(err.get("code"), str) else ""
            codigo = codigo if _CODIGO_MNEMO.fullmatch(codigo) else "FAILED"  # va al registro: solo un código
            explicacion = EXPLICACIONES.get(codigo, "Mnemo no pudo hacerlo")
            detalle: dict[str, Any] = {"code": codigo}
            if err.get("details") is not None:
                detalle["details"] = self._acotado(err["details"])
            dice = self._remoto(err.get("message") or "")
            log.info("Mnemo: %s devolvió %s", nombre[:64], codigo)
            return ErrorHerramienta(f"{explicacion}. Mnemo dice: {dice}" if dice else f"{explicacion}.", COD_MNEMO,
                                    detalle=detalle)
        dice = self._remoto(texto, 1_500)
        return ErrorHerramienta(f"Mnemo rechazó la llamada: {dice}" if dice else "Mnemo rechazó la llamada.",
                                COD_MNEMO, detalle={"code": "INVALID_ARGUMENT"})

    def _acotado(self, valor: Any, tope: int = 2_000) -> Any:
        """Los `details` de un error de Mnemo tal cual si son pequeños; si no, su texto recortado (pueden traer el texto
        de un resultado entero, el que retuvo su control de seguridad)."""
        try:
            texto = json.dumps(valor, ensure_ascii=False)
        except (TypeError, ValueError, RecursionError):
            return None
        limpio = self._remoto(texto, tope)
        if len(texto) <= tope:
            try:
                return json.loads(limpio)
            except (ValueError, RecursionError):
                pass
        return limpio

    async def _rpc(self, metodo: str, params: dict | None, plazo: float, avance: "_Avance | None" = None) -> dict:
        """Una petición JSON-RPC: el `result` (un objeto) o `ErrorHerramienta`. Si un servidor con estado olvidó la
        sesión (404 con `Mcp-Session-Id`), se inicia otra vez y se repite una sola vez."""
        for intento in (1, 2):
            mensaje: dict[str, Any] = {"jsonrpc": "2.0", "id": next(self._ids), "method": metodo}
            if params is not None:
                mensaje["params"] = params
            con_sesion = self._sesion is not None
            try:
                res = await self._enviar(mensaje, plazo, avance)
            except ErrorHerramienta as e:
                if e.estado == 404 and con_sesion and metodo != "initialize" and intento == 1:
                    await self._iniciar()
                    continue
                raise
            if not isinstance(res, dict):
                raise ErrorHerramienta(MENSAJE_PROTOCOLO, COD_MNEMO)
            return res
        raise ErrorHerramienta(MENSAJE_PROTOCOLO, COD_MNEMO)  # pragma: no cover - el bucle siempre devuelve o lanza

    # ───────────────────────────── HTTP ─────────────────────────────

    async def _enviar(self, mensaje: dict, plazo: float, avance: "_Avance | None" = None) -> Any:
        """Manda un mensaje y devuelve el `result` de su respuesta (None para una notificación). El token se pide en
        cada envío; con una `FuenteTokens`, un 401 la invalida y el envío se repite una vez."""
        try:
            cuerpo = json.dumps(mensaje, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
        except (TypeError, ValueError):
            raise ErrorHerramienta("Los argumentos para Mnemo no son JSON válido.", COD_MNEMO) from None
        if len(cuerpo) > MAX_PETICION:
            raise ErrorHerramienta(MENSAJE_PETICION_GRANDE, COD_MNEMO, estado=413)
        metodo = mensaje.get("method")
        bucle = asyncio.get_running_loop()
        fin_total = bucle.time() + (max(plazo, avance.tope) if avance is not None else plazo)
        self._en_curso += 1
        try:
            async with asyncio.timeout(plazo) as reloj:
                if avance is not None:
                    avance.armar(reloj, bucle, fin_total)
                plazos = httpx2.Timeout(plazo, connect=min(plazo, PLAZO_CONEXION_S))
                for intento in (1, 2):
                    token = await self._token()
                    http, _ = self._conexion()
                    try:
                        async with http.stream("POST", self.url, content=cuerpo, headers=self._cabeceras(token),
                                               timeout=plazos) as r:
                            return await self._respuesta(r, mensaje.get("id"), metodo, avance)
                    except ErrorHerramienta as e:
                        if e.estado != 401:
                            raise
                        if self._fuente is None or intento == 2:
                            self.olvidar()  # lo siguiente vuelve a iniciar (con otro token, si lo hay)
                            raise
                        await self._fuente.invalidar(token)  # quizá venció antes de tiempo: se renueva y se repite
                        log.info("Mnemo: 401 con la conexión: se renueva el token y se repite una vez")
        except (TimeoutError, httpx2.TimeoutException):
            if avance is not None and bucle.time() >= fin_total - 0.05:
                log.warning("Mnemo: %s no terminó dentro del tope total", metodo)
                raise ErrorHerramienta(f"Mnemo no terminó en {max(plazo, avance.tope):g} segundos.",
                                       COD_PLAZO) from None
            log.warning("Mnemo: %s no respondió a tiempo", metodo)
            raise ErrorHerramienta(f"Mnemo no respondió en {plazo:g} segundos.", COD_PLAZO) from None
        except httpx2.HTTPError as e:  # sin el mensaje: el de httpx puede traer la petición
            log.warning("Mnemo: falló la conexión (%s)", type(e).__name__)
            raise ErrorHerramienta(MENSAJE_RED, COD_RED) from None
        finally:
            self._en_curso -= 1
            if self._retirado and self._en_curso == 0 and self._http is not None and self._bucle is bucle:
                http, self._http = self._http, None
                await http.aclose()

    async def _respuesta(self, r: httpx2.Response, rid: Any, metodo: Any, avance: "_Avance | None" = None) -> Any:
        s = r.status_code
        tipo = r.headers.get("content-type", "").split(";")[0].strip().lower()
        if rid is None and 200 <= s < 300:
            return None  # notificación aceptada (202, sin cuerpo)
        if s == 401:
            log.warning("Mnemo: el token no fue aceptado (401)")
            raise ErrorHerramienta(MENSAJE_TOKEN, COD_TOKEN, estado=s)
        if s == 403:
            log.warning("Mnemo: la conexión no tiene permiso (403)")
            raise ErrorHerramienta(MENSAJE_ALCANCE, COD_TOKEN, estado=s)
        if 300 <= s < 400:
            log.warning("Mnemo: el servidor respondió con una redirección (%s)", s)
            raise ErrorHerramienta(f"Mnemo respondió con una redirección (HTTP {s}). La dirección MCP de la conexión "
                                   "debe ser la final de su servidor (https://…/mcp).", COD_MNEMO, estado=s)
        if metodo == "initialize" and 200 <= s < 300:
            sesion = r.headers.get("mcp-session-id")
            self._sesion = sesion if isinstance(sesion, str) and _SESION.fullmatch(sesion) else None
        if s == 200 and tipo == "text/event-stream":
            return self._resultado_rpc(await self._leer_sse(r, rid, avance), rid, s)
        crudo = await self._leer(r)
        datos = None
        if tipo == "application/json" or tipo.endswith("+json"):
            try:
                datos = json.loads(crudo)
            except (ValueError, UnicodeDecodeError, RecursionError):
                datos = None
        if s >= 400:
            raise self._error_http(s, datos)
        if datos is None:
            log.warning("Mnemo: respuesta que no es MCP (HTTP %s, %s)", s, tipo[:40] or "sin tipo")
            raise ErrorHerramienta(MENSAJE_PROTOCOLO, COD_MNEMO, estado=s)
        return self._resultado_rpc(datos, rid, s)

    async def _leer(self, r: httpx2.Response) -> bytes:
        trozos, total = [], 0
        async for t in r.aiter_bytes():
            total += len(t)
            if total > MAX_RESPUESTA:
                raise ErrorHerramienta(MENSAJE_GRANDE, COD_MNEMO)
            trozos.append(t)
        return b"".join(trozos)

    async def _leer_sse(self, r: httpx2.Response, rid: Any, avance: "_Avance | None" = None) -> Any:
        """El mensaje JSON-RPC de `rid` en un flujo SSE. Los comentarios (`: keepalive`) se saltan, las líneas `data:`
        de un evento se juntan con saltos de línea y lo que no es la respuesta se ignora, salvo los avisos de avance
        de esta llamada (`notifications/progress` con su `progressToken`), que van a `avance`. Lee por bytes con un
        tope: una línea `data:` puede traer una imagen entera."""
        datos: list[str] = []
        evento = ""
        pendiente: list[bytes] = []
        total = 0

        def despachar() -> Any:
            nonlocal evento
            texto, tipo = "\n".join(datos), evento
            datos.clear()
            evento = ""
            if not texto or tipo not in ("", "message"):
                return None
            try:
                m = json.loads(texto)
            except (ValueError, RecursionError):
                return None
            if avance is not None and avance.es_suyo(m):
                return _Aviso(m["params"])
            return m if (_es_respuesta(m, rid) or isinstance(m, list)) else None

        def linea(cruda: bytes) -> Any:
            nonlocal evento
            texto = cruda.decode("utf-8", "replace")
            if texto == "":
                return despachar()
            if texto.startswith(":"):
                return None  # comentario: `: keepalive`
            campo, _, valor = texto.partition(":")
            valor = valor[1:] if valor.startswith(" ") else valor
            if campo == "data":
                datos.append(valor)
            elif campo == "event":
                evento = valor
            return None

        async for trozo in r.aiter_bytes():
            total += len(trozo)
            if total > MAX_RESPUESTA:
                raise ErrorHerramienta(MENSAJE_GRANDE, COD_MNEMO)
            pendiente.append(trozo)
            if b"\n" not in trozo and b"\r" not in trozo:
                continue  # sin fin de línea no hay nada que procesar (y no se vuelve a copiar lo acumulado)
            bloque = b"".join(pendiente)
            pendiente.clear()
            # Un «\r» al final puede ser la mitad de un «\r\n» que llega en el próximo trozo
            if bloque.endswith(b"\r"):
                bloque, guardado = bloque[:-1], b"\r"
            else:
                guardado = b""
            lineas = bloque.replace(b"\r\n", b"\n").replace(b"\r", b"\n").split(b"\n")
            pendiente.append(lineas.pop() + guardado)
            for cruda in lineas:
                m = linea(cruda)
                if isinstance(m, _Aviso):
                    await avance.avisar(m.params)
                elif m is not None:
                    return m
        final = b"".join(pendiente).rstrip(b"\r")
        if final:
            linea(final)
        m = despachar()
        if isinstance(m, _Aviso):
            await avance.avisar(m.params)
        elif m is not None:
            return m
        log.warning("Mnemo: el flujo terminó sin la respuesta")
        raise ErrorHerramienta("Mnemo cerró la respuesta sin contestar.", COD_MNEMO)

    def _resultado_rpc(self, m: Any, rid: Any, s: int) -> Any:
        if isinstance(m, list):  # un lote: se busca la respuesta propia
            m = next((x for x in m if _es_respuesta(x, rid)), None)
        if not _es_respuesta(m, rid):
            raise ErrorHerramienta(MENSAJE_PROTOCOLO, COD_MNEMO, estado=s)
        if isinstance(m.get("error"), dict):
            raise self._error_rpc(m["error"], s)
        if "error" in m:
            raise ErrorHerramienta(MENSAJE_PROTOCOLO, COD_MNEMO, estado=s)
        return m["result"]

    def _error_rpc(self, err: dict, s: int) -> ErrorHerramienta:
        codigo = err.get("code")
        codigo = codigo if isinstance(codigo, int) and not isinstance(codigo, bool) else None
        dice = self._remoto(err.get("message") or "")
        log.warning("Mnemo: error JSON-RPC %s (HTTP %s)", codigo, s)
        if codigo == -32602 and _NO_ENCONTRADA.search(dice):
            return ErrorHerramienta("Mnemo ya no ofrece esa herramienta con esta conexión.", COD_NO_DISPONIBLE,
                                    estado=s)
        return ErrorHerramienta(f"Mnemo rechazó la petición del panel: {dice or 'sin detalle'} (JSON-RPC {codigo}).",
                                COD_MNEMO, estado=s)

    def _error_http(self, s: int, datos: Any) -> ErrorHerramienta:
        """Un rechazo HTTP como `ErrorHerramienta`, con el porqué en palabras propias. Los de protocolo (400, 405, 406,
        415) traen un error JSON-RPC con la causa, que se cita."""
        if s == 404:
            log.warning("Mnemo: respondió HTTP 404")
            return ErrorHerramienta("Mnemo no tiene un servidor MCP en esa dirección: la dirección MCP de la conexión "
                                    "debe terminar en /mcp.", COD_MNEMO, estado=s)
        if s == 413:
            log.warning("Mnemo: respondió HTTP 413")
            return ErrorHerramienta(MENSAJE_PETICION_GRANDE, COD_MNEMO, estado=s)
        if s == 429:
            log.warning("Mnemo: respondió HTTP 429")
            return ErrorHerramienta("Mnemo está recibiendo demasiadas peticiones. Espere un momento y vuelva a "
                                    "intentarlo.", COD_MNEMO, estado=s)
        if s >= 500:
            log.warning("Mnemo: respondió HTTP %s", s)
            return ErrorHerramienta(f"Mnemo falló al atender la petición (HTTP {s}). Intente de nuevo en un rato.",
                                    COD_MNEMO, estado=s)
        if isinstance(datos, dict) and isinstance(datos.get("error"), dict):
            return self._error_rpc(datos["error"], s)
        log.warning("Mnemo: respondió HTTP %s", s)
        return ErrorHerramienta(f"Mnemo rechazó la petición del panel (HTTP {s}).", COD_MNEMO, estado=s)


_CANDADO = threading.Lock()


def cliente_de(app: Any) -> ClienteMnemo | None:
    """El cliente de Mnemo de la aplicación (uno, en `app.state.mnemo_cliente`), armado con la conexión guardada
    (`mnemo_conexion`): su dirección MCP y una `FuenteTokens` de esa conexión y de esa dirección (que solo da el access
    si la dirección es la atada a los tokens: una cambiada en la base deja la conexión «caida» sin mandar nada). None
    si no hay una conexión «conectada». Se rehace cuando cambia la `version` de la conexión (se conectó otra vez, se
    renovó, se cayó o se desconectó) o su dirección; el viejo se retira (cierra sus conexiones cuando termine lo que
    tenga en curso). Las pruebas inyectan el transporte en `app.state.mnemo_transporte`. Lee un documento de MongoDB
    por `_id`: desde código asíncrono, mejor con `run_in_threadpool`."""
    estado = getattr(app, "state", None)
    db = getattr(estado, "db", None) if estado is not None else None
    if db is None:
        return None
    from . import mnemo_conexion  # aquí: la conexión importa este módulo
    vigente = mnemo_conexion.conectada(db)
    if vigente is None:
        return None
    with _CANDADO:
        actual = getattr(estado, "mnemo_cliente", None)
        if (isinstance(actual, ClienteMnemo) and actual.version_conexion == vigente["version"]
                and actual.url == vigente["url_mcp"].rstrip("/")):
            return actual
        try:
            nuevo = ClienteMnemo(vigente["url_mcp"], mnemo_conexion.FuenteTokens(
                app, vigente["conexion"], vigente["url_mcp"]), transporte=mnemo_conexion.transporte_de(app))
        except ValueError:
            log.warning("Mnemo: la dirección de la conexión no es válida; el asistente sigue sin Mnemo")
            return None
        nuevo.version_conexion = vigente["version"]
        if isinstance(actual, ClienteMnemo):
            actual.retirar()
        estado.mnemo_cliente = nuevo
        return nuevo
