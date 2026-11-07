"""Un servidor MCP falso que imita al `/mcp` de Mnemo, para probar `mnemo_cliente.py` y `herramientas/mnemo.py` sin
red y sin Mnemo. Solo datos inventados.

* `MnemoFalso` es una aplicación ASGI: `transporte()` da el `httpx2.ASGITransport` que recibe `ClienteMnemo` (sin
  red), y `EnHilo(app)` la sirve con uvicorn en 127.0.0.1 para probar el flujo SSE de verdad (keepalive y plazos).
* Imita lo verificado contra Mnemo (su montaje de `/mcp` con el SDK MCP v2 en modo «legacy stateless»):
  - solo POST a `/mcp`; GET y DELETE dan 405 (JSON-RPC -32000); otra ruta, 404 `{"error": "not_found"}` (después del
    Bearer: sin token es 401);
  - sin el token esperado: 401 con `WWW-Authenticate: Bearer error="invalid_token", …` y
    `{"error": "invalid_token", "error_description": …}`;
  - `Accept` sin los dos tipos: 406; `Content-Type` que no es JSON: 415; una `MCP-Protocol-Version` desconocida: 400;
  - `initialize` (serverInfo, capabilities, instructions), `notifications/initialized` (202), `tools/list` (con
    `nextCursor` si `por_pagina`), `tools/call` (o -32602 «Tool X not found»);
  - la respuesta por SSE (`event: message`, con keepalives antes y, si se pide, el JSON en varias líneas `data:`) o
    JSON plano (`formato="json"`). Mientras una herramienta tarda, `: keepalive` cada `intervalo` segundos.
* `peticiones` guarda cada petición (método HTTP, ruta, cabeceras y JSON) y `cancelaciones` cuenta las herramientas
  cortadas porque el cliente se fue (Mnemo cancela la llamada al cerrarse la conexión).
"""
from __future__ import annotations

import asyncio
import base64
import json
import threading
import time
from typing import Any, Awaitable, Callable

import httpx2

TOKEN = "mnemo_pat_0123456789abcdef01234567_" + "S3cr3tInventadoParaPruebas-0123456789abcdef"[:43]
VERSIONES = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05", "2024-10-07")
INSTRUCCIONES = ("Mnemo is the person's personal AI workspace (inventado para pruebas). Start with mnemo_get_briefing, "
                 "then use search and fetch.")
ESQUEMA = "https://json-schema.org/draft/2020-12/schema"
LECTURA = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
ESCRITURA = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}
CAMBIO = {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": False}
PEDIDO = {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True}

# Una imagen PNG de 1×1 de verdad y una JPEG mínima (solo la firma y un SOF de 2×3)
PNG_1x1 = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
JPEG_2x3 = (b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
            b"\xff\xc0\x00\x11\x08\x00\x03\x00\x02\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01\xff\xd9")


def b64(datos: bytes) -> str:
    return base64.b64encode(datos).decode()


def png(ancho: int, alto: int) -> bytes:
    """Una cabecera PNG con esas dimensiones (no es una imagen completa: basta para leer el tamaño)."""
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + ancho.to_bytes(4, "big") + alto.to_bytes(4, "big") + b"\x08\x06"


def texto(datos: Any) -> dict:
    return {"type": "text", "text": datos if isinstance(datos, str) else json.dumps(datos, ensure_ascii=False)}


def correcto(datos: dict, *extra: dict) -> dict:
    """Un resultado correcto como lo arma Mnemo (`projection.ts`): el JSON en texto y `structuredContent`."""
    return {"content": [texto(datos), *extra], "structuredContent": datos}


def fallo(codigo: str, mensaje: str, detalles: Any = None) -> dict:
    cuerpo = {"error": {"code": codigo, "message": mensaje, **({"details": detalles} if detalles is not None else {})}}
    return {"content": [texto(cuerpo)], "isError": True}


def herramienta(nombre: str, titulo: str, propiedades: dict, requeridas: list[str], anotaciones: dict,
                descripcion: str | None = None) -> dict:
    """Una definición de `tools/list` con la forma de Mnemo (JSON Schema 2020-12 de zod, `title` repetido en
    `annotations`, `outputSchema`)."""
    return {"name": nombre, "title": titulo, "description": descripcion or f"{titulo} (inventada para pruebas).",
            "inputSchema": {"type": "object", "$schema": ESQUEMA, "properties": propiedades, "required": requeridas},
            "annotations": {"title": titulo, **anotaciones},
            "outputSchema": {"$schema": ESQUEMA, "type": "object", "properties": {}, "additionalProperties": True}}


def _s(desc: str, **kw: Any) -> dict:
    return {"type": "string", "description": desc, **kw}


def catalogo() -> list[dict]:
    """Un catálogo parecido al de Mnemo (las de la lista blanca del panel y algunas que no están en ella)."""
    entero = {"type": "integer", "minimum": -9007199254740991, "maximum": 9007199254740991}
    fetch = herramienta("fetch", "Read a Mnemo item", {"id": _s("Typed id", minLength=3, maxLength=160),
                                                      "offset": {**entero, "minimum": 0}}, ["id"], LECTURA)
    fetch["_meta"] = {"anthropic/maxResultSizeChars": 100000}
    return [
        herramienta("search", "Search Mnemo", {"query": _s("What to look for", minLength=1, maxLength=300)},
                    ["query"], LECTURA, "Search the person's Mnemo. Use fetch to read a result."),
        fetch,
        herramienta("mnemo_get_briefing", "Get the briefing",
                    {"response_format": {"type": "string", "enum": ["concise", "detailed"], "default": "concise"}},
                    [], LECTURA),
        herramienta("mnemo_view_image", "View a Mnemo image", {"id": _s("The doc_ id of an image")}, ["id"],
                    LECTURA),
        herramienta("mnemo_list_events", "List calendar events", {"from": _s("Start"), "to": _s("End")}, [], LECTURA),
        herramienta("mnemo_create_event", "Create calendar events",
                    {"title": _s("Title"), "start": _s("Start, ISO 8601"), "notes": _s("Notes")}, ["title", "start"],
                    ESCRITURA),
        herramienta("mnemo_update_event", "Update a calendar event", {"id": _s("event_ id"), "changes": {
            "type": "object", "properties": {"title": _s("Title")}}}, ["id", "changes"], CAMBIO),
        herramienta("mnemo_export_document", "Export a document", {"document_id": _s("canvas_ id")},
                    ["document_id"], LECTURA),
        herramienta("mnemo_request_share", "Request to share", {"id": _s("Typed id"), "with": _s("Email")},
                    ["id", "with"], PEDIDO),
        herramienta("mnemo_check_approval", "Check an approval", {"approval_id": _s("apr_ id")}, ["approval_id"],
                    LECTURA),
        herramienta("mnemo_get_job", "Get job status", {"job_id": _s("Job id"), "wait_seconds": {
            **entero, "minimum": 0, "maximum": 50, "default": 25}}, ["job_id"], LECTURA),
        herramienta("mnemo_generate_deck", "Generate a deck", {"topic": _s("Topic"), "wait_seconds": {
            **entero, "minimum": 0, "maximum": 200, "default": 200}}, ["topic"], ESCRITURA),
        herramienta("mnemo_query_business", "Query the business", {"view": _s("Which view")}, [], LECTURA),
        herramienta("lento", "Slow tool", {"s": {"type": "number"}}, ["s"], LECTURA),
    ]


Manejador = Callable[[dict], Awaitable[dict]]


class MnemoFalso:
    """El servidor MCP falso (ASGI). Los atributos se pueden cambiar en cada prueba."""

    def __init__(self, *, token: str = TOKEN, formato: str = "sse", keepalives: int = 1, multilinea: bool = False,
                 intervalo: float = 15.0, por_pagina: int | None = None, instrucciones: str | None = INSTRUCCIONES,
                 sesion: str | None = None):
        self.token, self.formato, self.keepalives, self.multilinea = token, formato, keepalives, multilinea
        self.intervalo, self.por_pagina, self.instrucciones, self.sesion = intervalo, por_pagina, instrucciones, sesion
        self.version: str | None = None  # la protocolVersion que contesta initialize (None: la pedida)
        self.herramientas = catalogo()
        self.manejadores: dict[str, Manejador] = dict(_MANEJADORES)
        self.peticiones: list[dict] = []
        self.llamadas: list[tuple[str, dict]] = []
        self.cancelaciones = 0
        self.forzar: dict[str, tuple[int, dict | str, dict]] = {}  # método → (estado, cuerpo, cabeceras)
        self.olvidar_sesion = False

    def transporte(self) -> httpx2.ASGITransport:
        return httpx2.ASGITransport(app=self)

    def contar(self, metodo: str) -> int:
        return sum(1 for p in self.peticiones if isinstance(p["json"], dict) and p["json"].get("method") == metodo)

    # ── ASGI ──
    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] == "lifespan":
            while (await receive())["type"] != "lifespan.shutdown":
                pass
            await send({"type": "lifespan.shutdown.complete"})
            return
        cabeceras = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
        cuerpo = b""
        while True:
            m = await receive()
            cuerpo += m.get("body", b"")
            if not m.get("more_body"):
                break
        try:
            datos = json.loads(cuerpo) if cuerpo else None
        except ValueError:
            datos = None
        self.peticiones.append({"metodo_http": scope["method"], "ruta": scope["path"], "cabeceras": cabeceras,
                                "json": datos})
        await self._atender(scope, cabeceras, datos, send, receive)

    async def _json(self, send: Callable, estado: int, cuerpo: Any, extra: dict | None = None) -> None:
        crudo = json.dumps(cuerpo).encode() if not isinstance(cuerpo, str) else cuerpo.encode()
        tipo = "application/json" if not isinstance(cuerpo, str) else "text/html"
        cab = [(b"content-type", tipo.encode()), (b"content-length", str(len(crudo)).encode())]
        cab += [(k.encode(), v.encode()) for k, v in (extra or {}).items()]
        await send({"type": "http.response.start", "status": estado, "headers": cab})
        await send({"type": "http.response.body", "body": crudo})

    async def _rpc_error(self, send: Callable, estado: int, codigo: int, mensaje: str) -> None:
        await self._json(send, estado, {"jsonrpc": "2.0", "error": {"code": codigo, "message": mensaje}, "id": None})

    async def _atender(self, scope: dict, cab: dict, datos: Any, send: Callable, receive: Callable) -> None:
        if cab.get("authorization") != f"Bearer {self.token}":
            desc = "Missing Authorization header" if "authorization" not in cab else \
                "The token is not valid, was revoked or expired."
            return await self._json(send, 401, {"error": "invalid_token", "error_description": desc}, {
                "www-authenticate": f'Bearer error="invalid_token", error_description="{desc}", '
                                    'resource_metadata="http://mnemo.invalid/.well-known/oauth-protected-resource/mcp"'})
        if scope["path"].rstrip("/") != "/mcp":
            return await self._json(send, 404, {"error": "not_found"})
        if scope["method"] != "POST":
            return await self._rpc_error(send, 405, -32000, "Method not allowed.")
        acepta = cab.get("accept", "")
        if "application/json" not in acepta or "text/event-stream" not in acepta:
            return await self._rpc_error(send, 406, -32000, "Not Acceptable: Client must accept both "
                                                            "application/json and text/event-stream")
        if not cab.get("content-type", "").startswith("application/json"):
            return await self._rpc_error(send, 415, -32000, "Unsupported Media Type: Content-Type must be "
                                                            "application/json")
        version = cab.get("mcp-protocol-version")
        if version is not None and version not in VERSIONES:
            return await self._rpc_error(send, 400, -32000, f"Bad Request: Unsupported protocol version: {version}")
        if not isinstance(datos, dict) or datos.get("jsonrpc") != "2.0" or not isinstance(datos.get("method"), str):
            return await self._rpc_error(send, 400, -32700, "Parse error: Invalid JSON-RPC message")
        metodo, rid = datos["method"], datos.get("id")
        if metodo in self.forzar:
            estado, cuerpo, extra = self.forzar[metodo]
            return await self._json(send, estado, cuerpo, extra)
        if self.sesion and metodo != "initialize" and (self.olvidar_sesion or cab.get("mcp-session-id") != self.sesion):
            self.olvidar_sesion = False
            return await self._rpc_error(send, 404, -32001, "Session not found")
        if rid is None:  # una notificación
            await send({"type": "http.response.start", "status": 202, "headers": []})
            await send({"type": "http.response.body", "body": b""})
            return
        params = datos.get("params") if isinstance(datos.get("params"), dict) else {}
        await self._responder(send, receive, rid, metodo, params)

    async def _resultado(self, metodo: str, params: dict) -> dict:
        """El mensaje JSON-RPC (sin `id`) para un método."""
        if metodo == "initialize":
            pedida = params.get("protocolVersion")
            res = {"protocolVersion": self.version or (pedida if pedida in VERSIONES else "2025-11-25"),
                   "capabilities": {"tools": {"listChanged": True}, "resources": {}, "prompts": {}},
                   "serverInfo": {"name": "mnemo", "title": "Mnemo", "version": "1.0.0"}}
            if self.instrucciones is not None:
                res["instructions"] = self.instrucciones
            return {"result": res}
        if metodo == "tools/list":
            inicio = int(params.get("cursor") or 0)
            n = self.por_pagina or len(self.herramientas)
            pagina = self.herramientas[inicio:inicio + n]
            res: dict[str, Any] = {"tools": pagina}
            if inicio + n < len(self.herramientas):
                res["nextCursor"] = str(inicio + n)
            return {"result": res}
        if metodo == "tools/call":
            nombre, args = params.get("name"), params.get("arguments") or {}
            if nombre not in {h["name"] for h in self.herramientas} or nombre not in self.manejadores:
                return {"error": {"code": -32602, "message": f"MCP error -32602: Tool {nombre} not found"}}
            self.llamadas.append((nombre, args))
            try:
                return {"result": await self.manejadores[nombre](args)}
            except asyncio.CancelledError:
                self.cancelaciones += 1
                raise
        return {"error": {"code": -32601, "message": "Method not found"}}

    async def _responder(self, send: Callable, receive: Callable, rid: Any, metodo: str, params: dict) -> None:
        extra = [(b"mcp-session-id", self.sesion.encode())] if self.sesion and metodo == "initialize" else []
        if self.formato == "json":
            m = {"jsonrpc": "2.0", "id": rid, **(await self._resultado(metodo, params))}
            crudo = json.dumps(m, ensure_ascii=False).encode()
            await send({"type": "http.response.start", "status": 200,
                        "headers": [(b"content-type", b"application/json"), *extra]})
            await send({"type": "http.response.body", "body": crudo})
            return
        await send({"type": "http.response.start", "status": 200, "headers": [
            (b"content-type", b"text/event-stream"), (b"cache-control", b"no-cache"), *extra]})
        for _ in range(self.keepalives):
            await send({"type": "http.response.body", "body": b": keepalive\n\n", "more_body": True})
        tarea = asyncio.ensure_future(self._resultado(metodo, params))
        vigia = asyncio.ensure_future(_desconexion(receive))
        try:
            while True:
                hecho, _ = await asyncio.wait({tarea, vigia}, timeout=self.intervalo,
                                              return_when=asyncio.FIRST_COMPLETED)
                if tarea in hecho:
                    break
                if vigia in hecho:  # el cliente se fue: como Mnemo, se cancela la herramienta
                    await _cancelar(tarea)
                    return
                await send({"type": "http.response.body", "body": b": keepalive\n\n", "more_body": True})
        except BaseException:
            await _cancelar(tarea)
            raise
        finally:
            vigia.cancel()
        m = {"jsonrpc": "2.0", "id": rid, **tarea.result()}
        crudo = json.dumps(m, ensure_ascii=False, indent=2 if self.multilinea else None)
        cuerpo = "event: message\n" + "".join(f"data: {linea}\n" for linea in crudo.split("\n")) + "\n"
        await send({"type": "http.response.body", "body": cuerpo.encode(), "more_body": False})


async def _desconexion(receive: Callable) -> None:
    while (await receive())["type"] != "http.disconnect":
        pass


async def _cancelar(tarea: asyncio.Future) -> None:
    tarea.cancel()
    try:
        await tarea
    except BaseException:  # noqa: BLE001 - solo se espera a que termine de cancelarse
        pass


# ───────────────────────────── Las herramientas falsas ─────────────────────────────

async def _search(a: dict) -> dict:
    q = a.get("query")
    if not isinstance(q, str) or not q.strip():
        return {"content": [texto("Input validation error: Invalid arguments for tool search: query: Too small: "
                                  "expected string to have >=1 characters")], "isError": True}
    return correcto({"results": [{"id": "doc_acta1", "title": f"Acta inventada: {q}", "url": "mnemo://documents/doc_1"},
                                 {"id": "mem_2", "title": "Recuerdo inventado", "url": "mnemo://memories/mem_2"}],
                     "withheld": {"sensitive": 0}})


async def _fetch(a: dict) -> dict:
    ident = a.get("id")
    if not isinstance(ident, str):
        return {"content": [texto("Input validation error: Invalid arguments for tool fetch: id: Invalid input: "
                                  "expected string, received number")], "isError": True}
    if ident == "doc_no":
        return fallo("NOT_FOUND", "No item with that id.")
    if ident == "doc_largo":
        return correcto({"id": ident, "title": "Documento largo inventado", "text": "palabra " * 12_000,
                         "url": "mnemo://documents/doc_largo", "metadata": {"kind": "document", "next_offset": 90000}})
    if ident == "doc_plan":
        return fallo("PLAN_REQUIRED", "The person's Mnemo plan does not include this.", {"feature": "documents"})
    if ident == "doc_eco":  # un servidor que (por error) cita el token: el cliente no debe repetirlo
        return fallo("INTERNAL", f"Something went wrong with Bearer {TOKEN}")
    return correcto({"id": ident, "title": "Acta inventada", "text": "Texto inventado del acta.",
                     "url": "mnemo://documents/" + ident, "metadata": {"kind": "document"}})


async def _briefing(a: dict) -> dict:
    return correcto({"profile": "Perfil inventado para pruebas.", "memories": [], "agenda": []})


async def _ver_imagen(a: dict) -> dict:
    ident = a.get("id")
    datos = {"id": ident, "title": "Foto inventada", "url": "mnemo://documents/" + str(ident), "visible": True}
    imagenes = {
        "doc_png": {"type": "image", "data": b64(PNG_1x1), "mimeType": "image/png"},
        "doc_jpeg_como_png": {"type": "image", "data": b64(JPEG_2x3), "mimeType": "image/png"},
        "doc_enorme": {"type": "image", "data": "A" * 2_600_000, "mimeType": "image/png"},
        "doc_gigante": {"type": "image", "data": b64(png(9000, 10)), "mimeType": "image/png"},
        "doc_basura": {"type": "image", "data": b64(b"esto no es una imagen"), "mimeType": "image/png"},
        "doc_mal_b64": {"type": "image", "data": "no*es*base64", "mimeType": "image/png"},
    }
    return correcto(datos, imagenes.get(ident, imagenes["doc_png"]))


async def _eventos(a: dict) -> dict:
    return correcto({"events": [{"id": "event_1", "title": "Reunión inventada", "start": "2026-11-09T09:00:00-05:00"}],
                     "next_cursor": None})


def _aprobacion(resumen: str) -> dict:
    return correcto({"status": "needs_approval", "approval_id": "apr_InventadoParaPruebas00",
                     "approval_url": "/aprobar/apr_InventadoParaPruebas00", "expires_at": "2026-11-07T15:15:00Z",
                     "summary": resumen, "message": "Nothing has been done yet. The person has to approve this in "
                                                    "Mnemo: give them approval_url."})


async def _crear_evento(a: dict) -> dict:
    if a.get("title") == "compartido":
        return _aprobacion("Crear el evento en un calendario compartido")
    return correcto({"status": "done", "created": [{"id": "event_9", "title": a.get("title")}]})


async def _cambiar_evento(a: dict) -> dict:
    return correcto({"status": "done", "updated": a.get("id")})


async def _exportar(a: dict) -> dict:
    url = "/api/agent-exports/tokInventado"
    return correcto({"document_id": a.get("document_id"), "filename": "acta.pdf", "mime_type": "application/pdf",
                     "url": url, "expires_at": "2026-11-07T15:15:00Z"},
                    {"type": "resource_link", "uri": url, "name": "acta.pdf", "mimeType": "application/pdf",
                     "description": "Signed download link, valid for about 15 minutes."},
                    {"type": "resource_link", "uri": "javascript:alert(1)", "name": "malo"})


async def _compartir(a: dict) -> dict:
    return _aprobacion("Compartir el acta inventada")


async def _aprobacion_estado(a: dict) -> dict:
    return correcto({"approval_id": a.get("approval_id"), "status": "approved", "done": True,
                     "summary": "Compartir el acta inventada", "result": "Hecho."})


async def _trabajo(a: dict) -> dict:
    return correcto({"job_id": a.get("job_id"), "status": "running", "tool": "mnemo_generate_deck",
                     "waited": a.get("wait_seconds")})


async def _generar(a: dict) -> dict:
    return correcto({"status": "running", "job_id": "job_inventado", "poll_with": "mnemo_get_job",
                     "waited": a.get("wait_seconds")})


async def _negocio(a: dict) -> dict:
    return correcto({"items": [{"id": "item_1"}, {"id": "item_2"}, {"id": "item_3"}]})


async def _lento(a: dict) -> dict:
    s = float(a.get("s") or 0)
    await asyncio.sleep(s)
    return correcto({"slept": s})


_MANEJADORES: dict[str, Manejador] = {
    "search": _search, "fetch": _fetch, "mnemo_get_briefing": _briefing, "mnemo_view_image": _ver_imagen,
    "mnemo_list_events": _eventos, "mnemo_create_event": _crear_evento, "mnemo_update_event": _cambiar_evento,
    "mnemo_export_document": _exportar, "mnemo_request_share": _compartir, "mnemo_check_approval": _aprobacion_estado,
    "mnemo_get_job": _trabajo, "mnemo_generate_deck": _generar, "mnemo_query_business": _negocio, "lento": _lento,
}


# ───────────────────────────── Por red, en un hilo ─────────────────────────────

class EnHilo:
    """Sirve una aplicación ASGI con uvicorn en 127.0.0.1 (puerto libre) en un hilo: `with EnHilo(app) as s: s.url`."""

    def __init__(self, app: Any):
        import uvicorn
        self.servidor = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning",
                                                     lifespan="off", timeout_graceful_shutdown=1))
        self.hilo = threading.Thread(target=self.servidor.run, daemon=True)
        self.url = ""

    def __enter__(self) -> "EnHilo":
        self.hilo.start()
        limite = time.monotonic() + 10
        while not self.servidor.started:
            if time.monotonic() > limite or not self.hilo.is_alive():
                raise RuntimeError("uvicorn no arrancó")
            time.sleep(0.02)
        puerto = self.servidor.servers[0].sockets[0].getsockname()[1]
        self.url = f"http://127.0.0.1:{puerto}/mcp"
        return self

    def __exit__(self, *_: Any) -> None:
        self.servidor.should_exit = True
        self.hilo.join(10)
