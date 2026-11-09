"""Un servidor MCP falso que imita al `/mcp` de Mnemo, y su servidor de autorización OAuth, para probar
`mnemo_cliente.py`, `mnemo_conexion.py` y `herramientas/mnemo.py` sin red y sin Mnemo. Solo datos inventados.

* `MnemoFalso` es una aplicación ASGI: `transporte()` da el `httpx2.ASGITransport` que recibe `ClienteMnemo` (sin
  red), y `EnHilo(app)` la sirve con uvicorn en 127.0.0.1 para probar el flujo SSE de verdad (keepalive y plazos).
* `OAuthFalso` (más abajo) envuelve un `MnemoFalso` con el OAuth de Mnemo: descubrimiento, registro dinámico,
  autorización que aprueba con un 302 a la vuelta, tokens con PKCE y refresh que rota, revocación y el Bearer de
  `/mcp` contra los tokens vigentes.
* Herramientas falsas nuevas: se agrega su definición a `falso.herramientas` (con `herramienta(...)`) y su manejador
  a `falso.manejadores[nombre]`: `async def h(args) -> dict` (un `result` de MCP: `correcto(datos)` o
  `fallo(codigo, mensaje, detalles)`), o `async def h(args, avisar)` para mandar avance: `await avisar(progreso,
  mensaje, total=None)` emite un `notifications/progress` por el SSE si la petición trajo `_meta.progressToken` (si
  no, o con `formato="json"`, no hace nada). Los avisos emitidos quedan en `falso.avisos`.
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
* `ModeloFalso` (al final) agrega a un `MnemoFalso` la herramienta del modelo, `mnemo_model_complete`, con respuestas
  en cola (`respuesta_modelo`, o errores de Mnemo con `fallo`), el texto a trozos por `notifications/progress` y los
  argumentos de cada llamada en `pedidos`.
"""
from __future__ import annotations

import asyncio
import base64
import copy
import hashlib
import inspect
import json
import secrets
import threading
import time
from collections import deque
from typing import Any, Awaitable, Callable, Iterable
from urllib.parse import parse_qs, urlencode, urlsplit

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
PNG_1x1 = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9aw"
                           "AAAABJRU5ErkJggg==")
JPEG_2x3 = (b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
            b"\xff\xc0\x00\x11\x08\x00\x03\x00\x02\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01\xff\xd9")


def b64(datos: bytes) -> str:
    return base64.b64encode(datos).decode()


def png(ancho: int, alto: int) -> bytes:
    """Una cabecera PNG con esas dimensiones (no es una imagen completa: basta para leer el tamaño)."""
    return (b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + ancho.to_bytes(4, "big") + alto.to_bytes(4, "big")
            + b"\x08\x06")


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
        # Sin `autorizar`, vale solo `Bearer <token>`; con ella (OAuthFalso), decide con el token recibido
        self.autorizar: Callable[[str], bool] | None = None
        self.prm = "http://mnemo.invalid/.well-known/oauth-protected-resource/mcp"  # el `resource_metadata` del 401
        self.avisos: list[dict] = []  # los `notifications/progress` emitidos (sus `params`)

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

    def _autorizado(self, cab: dict) -> bool:
        bearer = cab.get("authorization", "")
        if self.autorizar is not None:
            return bearer.startswith("Bearer ") and self.autorizar(bearer[7:])
        return bearer == f"Bearer {self.token}"

    async def _atender(self, scope: dict, cab: dict, datos: Any, send: Callable, receive: Callable) -> None:
        if not self._autorizado(cab):
            desc = "Missing Authorization header" if "authorization" not in cab else \
                "The token is not valid, was revoked or expired."
            reto = f'Bearer error="invalid_token", error_description="{desc}", resource_metadata="{self.prm}"'
            return await self._json(send, 401, {"error": "invalid_token", "error_description": desc},
                                    {"www-authenticate": reto})
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

    async def _resultado(self, metodo: str, params: dict, avisar: Callable | None = None) -> dict:
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
            manejador = self.manejadores[nombre]
            try:
                if len(inspect.signature(manejador).parameters) >= 2:  # quiere mandar avance
                    return {"result": await manejador(args, avisar or _sin_avance)}
                return {"result": await manejador(args)}
            except asyncio.CancelledError:
                self.cancelaciones += 1
                raise
        return {"error": {"code": -32601, "message": "Method not found"}}

    async def _responder(self, send: Callable, receive: Callable, rid: Any, metodo: str, params: dict) -> None:
        extra = [(b"mcp-session-id", self.sesion.encode())] if self.sesion and metodo == "initialize" else []
        meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
        token = meta.get("progressToken")

        async def avisar(progreso: float, mensaje: str | None = None, total: float | None = None) -> None:
            if token is None or self.formato == "json":
                return
            p: dict[str, Any] = {"progressToken": token, "progress": progreso}
            if total is not None:
                p["total"] = total
            if mensaje is not None:
                p["message"] = mensaje
            self.avisos.append(p)
            n = json.dumps({"jsonrpc": "2.0", "method": "notifications/progress", "params": p}, ensure_ascii=False)
            await send({"type": "http.response.body", "body": f"event: message\ndata: {n}\n\n".encode(),
                        "more_body": True})

        if self.formato == "json":
            m = {"jsonrpc": "2.0", "id": rid, **(await self._resultado(metodo, params, avisar))}
            crudo = json.dumps(m, ensure_ascii=False).encode()
            await send({"type": "http.response.start", "status": 200,
                        "headers": [(b"content-type", b"application/json"), *extra]})
            await send({"type": "http.response.body", "body": crudo})
            return
        await send({"type": "http.response.start", "status": 200, "headers": [
            (b"content-type", b"text/event-stream"), (b"cache-control", b"no-cache"), *extra]})
        for _ in range(self.keepalives):
            await send({"type": "http.response.body", "body": b": keepalive\n\n", "more_body": True})
        tarea = asyncio.ensure_future(self._resultado(metodo, params, avisar))
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


async def _sin_avance(progreso: float, mensaje: str | None = None, total: float | None = None) -> None:
    return None


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


# ───────────────────────────── El OAuth de Mnemo, falso ─────────────────────────────

BASE = "https://mnemo.example.org"
ALCANCES_MNEMO = ("mnemo:read", "mnemo:study.write", "mnemo:memory.write", "mnemo:workspace.write",
                  "mnemo:business.write", "mnemo:forms.responses", "mnemo:share", "mnemo:publish", "mnemo:delete",
                  "mnemo:model")
OIDC = ("openid", "email", "profile")
CUENTA = {"sub": "usr_ana_inventada", "name": "Ana Inventada", "email": "ana.inventada@example.org"}
OTRA_CUENTA = {"sub": "usr_beto_inventado", "name": "Beto Inventado", "email": "beto.inventado@example.org"}
INVALIDO = {"error": "invalid_grant", "error_description": "grant request is invalid"}


def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).rstrip(b"=").decode()


class OAuthFalso:
    """El servidor de autorización de Mnemo y su `/mcp` (un `MnemoFalso` en `self.mcp`), como aplicación ASGI.
    Imita lo verificado contra Mnemo (`mapa2/mnemo-oauth.md`):

    * `GET /.well-known/oauth-protected-resource[/mcp]` (PRM: `resource` = `<base>/mcp`, `authorization_servers` =
      [`<base>`]; `prm_extra` lo cambia) y `GET /.well-known/oauth-authorization-server` u `openid-configuration`
      (los metadatos, con `mnemo:model` en `scopes_supported`; `metadatos_extra` los cambia). El 401 de `/mcp`
      anuncia `ruta_prm` en `resource_metadata`. `anuncia_modelo=False` es un Mnemo anterior a `mnemo:model`: no lo
      anuncia en sus metadatos y, si se pide, lo descarta sin avisar.
    * `POST /oauth/register` (JSON, RFC 7591): 201 con un `client_id` nuevo. `solo_loopback_http=True` rechaza una
      vuelta http que no sea de loopback, como Mnemo.
    * `GET /oauth/authorize`: cliente y vuelta registrados (si no, 400 con una página HTML que no vuelve); exige
      `response_type=code`, PKCE S256 y `resource` exacto; con `decision="allow"` (y los alcances de `marcar`, o
      todos los pedidos) responde 302 a la vuelta con `code`, `state` e `iss`; si no, con `error=access_denied`.
      La cuenta es `cuenta` (cámbiela para «otra cuenta»). Una concesión por cliente y cuenta: reconectar la misma
      reutiliza la misma, como Mnemo.
    * `POST /oauth/token` (solo form-urlencoded; JSON da 400): `authorization_code` con PKCE, `redirect_uri` y
      `resource` (reusar un `code` revoca la concesión); `refresh_token` que rota en cada uso (reusar uno ya usado
      revoca la concesión entera y da `invalid_grant`); un `client_id` desconocido da 401 `invalid_client`. `demora`
      espera antes de atender un refresh, sin cancelarse si el cliente se va (lo remoto sigue aunque se corte).
    * `POST /oauth/revoke`: con un refresh revoca la concesión; con un access lo mata a él y a los refresh de su
      concesión, pero la deja «zombi» (como Mnemo). Siempre 200. Quedan en `revocaciones`.
    * `/mcp`: el Bearer tiene que ser un access vigente (no vencido, no revocado, de una concesión viva).

    Para mirar y mover: `peticiones` (cada una, con `form`/`json` y `consulta`), `registros` y `renovaciones`
    (cuántos registros y cuántos refresh de tokens conocidos atendió), `forzar[ruta] = (estado, cuerpo)`, `sin_red`
    (rutas que fallan con un error de conexión en `transporte()`), `vencer_accesos()`, `olvidar_clientes()` (Mnemo
    en memoria tras reiniciar), `seguir(url_autorizar)` (lo que haría el navegador: la query de la vuelta) y, sin
    pasar por el flujo, `registrar(redirect_uri)` y `conceder(client_id, alcances, cuenta)`. `EnHilo(falso)` lo sirve
    por red: después, `falso.base = servidor.url[:-4]` (o `http://localhost:<puerto>` si el panel corre en 127.0.0.1:
    así la vuelta al panel viene de otro sitio, como en producción, y la cookie SameSite=Strict no viaja)."""

    def __init__(self, base: str = BASE, *, mcp: MnemoFalso | None = None, cuenta: dict | None = None,
                 vida: int = 3600):
        self.base = base.rstrip("/")
        self.mcp = mcp or MnemoFalso()
        self.mcp.autorizar = self.vigente
        self.cuenta = dict(cuenta or CUENTA)
        self.vida = vida
        self.decision = "allow"
        self.marcar: set[str] | None = None
        self.demora = 0.0
        self.solo_loopback_http = False
        self.anuncia_modelo = True
        self.prm_extra: dict = {}
        self.ruta_prm = "/.well-known/oauth-protected-resource/mcp"  # la que anuncia el 401 de /mcp
        self.metadatos_extra: dict = {}
        self.forzar: dict[str, tuple[int, Any]] = {}
        self.sin_red: set[str] = set()
        self.clientes: dict[str, dict] = {}
        self.codigos: dict[str, dict] = {}
        self.concesiones: dict[str, dict] = {}
        self.accesos: dict[str, dict] = {}
        self.refrescos: dict[str, dict] = {}
        self.peticiones: list[dict] = []
        self.revocaciones: list[dict] = []
        self.registros = 0
        self.renovaciones = 0

    # ── Lo que se ve de afuera ──
    @property
    def recurso(self) -> str:
        return f"{self.base}/mcp"

    def endpoints(self) -> dict:
        return {"authorize": f"{self.base}/oauth/authorize", "token": f"{self.base}/oauth/token",
                "register": f"{self.base}/oauth/register", "revoke": f"{self.base}/oauth/revoke"}

    def prm(self) -> dict:
        return {"resource": self.recurso, "authorization_servers": [self.base],
                "scopes_supported": [a for a in ALCANCES_MNEMO if a != "mnemo:model"],
                "bearer_methods_supported": ["header"], "resource_name": "Mnemo", **self.prm_extra}

    def ofrecidos(self) -> tuple[str, ...]:
        """Los alcances de Mnemo que ofrece este servidor (sin `mnemo:model` si es uno anterior: `anuncia_modelo`)."""
        return tuple(a for a in ALCANCES_MNEMO if self.anuncia_modelo or a != "mnemo:model")

    def metadatos(self) -> dict:
        e = self.endpoints()
        return {"issuer": self.base, "authorization_endpoint": e["authorize"], "token_endpoint": e["token"],
                "registration_endpoint": e["register"], "revocation_endpoint": e["revoke"],
                "userinfo_endpoint": f"{self.base}/oauth/userinfo", "jwks_uri": f"{self.base}/oauth/jwks",
                "code_challenge_methods_supported": ["S256"],
                "token_endpoint_auth_methods_supported": ["none", "client_secret_post"],
                "grant_types_supported": ["authorization_code", "refresh_token"], "response_types_supported": ["code"],
                "response_modes_supported": ["query"], "authorization_response_iss_parameter_supported": True,
                "client_id_metadata_document_supported": True, "scopes_supported": [*self.ofrecidos(), *OIDC],
                "id_token_signing_alg_values_supported": ["ES256"], **self.metadatos_extra}

    def transporte(self) -> httpx2.AsyncBaseTransport:
        return _TransporteOAuth(self)

    # ── Estado de las concesiones ──
    def vigente(self, token: str) -> bool:
        """¿Vale este access para `/mcp`?"""
        a = self.accesos.get(token)
        return bool(a) and not a["revocado"] and a["expira"] > time.time() and \
            not self.concesiones[a["gid"]]["revocada"]

    def concesion_de(self, token: str) -> dict | None:
        """La concesión de un access o un refresh (con `revocada`, `zombi`, `cuenta`, `alcances`, `client_id`)."""
        t = self.accesos.get(token) or self.refrescos.get(token)
        return self.concesiones.get(t["gid"]) if t else None

    def revocar_concesion(self, gid: str) -> None:
        self.concesiones[gid]["revocada"] = True

    def vencer_accesos(self) -> None:
        """Todos los access emitidos hasta ahora dejan de valer (como si vencieran); los refresh siguen vivos."""
        for a in self.accesos.values():
            a["expira"] = 0.0

    def olvidar_clientes(self) -> None:
        self.clientes.clear()

    def registrar(self, redirect_uri: str, nombre: str = "Panel Trabajemos juntos") -> str:
        cid = secrets.token_urlsafe(32)[:43]
        self.clientes[cid] = {"redirect_uris": [redirect_uri], "client_name": nombre}
        return cid

    def conceder(self, client_id: str, alcances: Iterable[str], cuenta: dict | None = None,
                 oidc: Iterable[str] = OIDC) -> dict:
        """Una concesión ya consentida y sus tokens (la respuesta de `/oauth/token`, con `id_token`), sin pasar por la
        autorización."""
        gid = self._concesion(client_id, dict(cuenta or self.cuenta), list(alcances), list(oidc))
        return self._emitir(gid, con_id_token=True)

    def _concesion(self, client_id: str, cuenta: dict, alcances: list[str], oidc: list[str]) -> str:
        for gid, g in self.concesiones.items():
            if g["client_id"] == client_id and g["cuenta"]["sub"] == cuenta["sub"] and not g["revocada"]:
                g.update(alcances=alcances, oidc=oidc, cuenta=cuenta, zombi=False)
                return gid
        gid = "grant_" + secrets.token_hex(6)
        self.concesiones[gid] = {"client_id": client_id, "cuenta": cuenta, "alcances": alcances, "oidc": oidc,
                                 "revocada": False, "zombi": False}
        return gid

    def _emitir(self, gid: str, *, con_id_token: bool) -> dict:
        g = self.concesiones[gid]
        access, refresh = "at_" + secrets.token_urlsafe(32), "rt_" + secrets.token_urlsafe(32)
        self.accesos[access] = {"gid": gid, "expira": time.time() + self.vida, "revocado": False}
        self.refrescos[refresh] = {"gid": gid, "usado": False, "muerto": False}
        out = {"access_token": access, "token_type": "Bearer", "expires_in": self.vida, "refresh_token": refresh,
               "scope": " ".join(g["alcances"])}
        if con_id_token and "openid" in g["oidc"]:
            out["id_token"] = self._id_token(g)
        return out

    def _id_token(self, g: dict) -> str:
        ahora = int(time.time())
        carga: dict[str, Any] = {"iss": self.base, "sub": g["cuenta"]["sub"], "aud": g["client_id"], "iat": ahora,
                                 "exp": ahora + 3600}
        if "profile" in g["oidc"] and g["cuenta"].get("name"):
            carga["name"] = g["cuenta"]["name"]
        if "email" in g["oidc"] and g["cuenta"].get("email"):
            carga.update(email=g["cuenta"]["email"], email_verified=True)
        cabeza = {"alg": "ES256", "typ": "JWT", "kid": "inventada"}
        return ".".join((_b64(json.dumps(cabeza).encode()), _b64(json.dumps(carga).encode()),
                         _b64(secrets.token_bytes(64))))

    # ── La autorización (lo que haría el navegador en la página de Mnemo) ──
    def autorizar(self, consulta: dict) -> tuple[int, str]:
        """(302, la vuelta con su query) o (400, una página HTML de error que no vuelve al panel)."""
        cid, vuelta = consulta.get("client_id"), consulta.get("redirect_uri")
        cliente = self.clientes.get(cid)
        if cliente is None:
            return 400, "<!doctype html><p>invalid_client</p>"
        if vuelta not in cliente["redirect_uris"]:
            return 400, "<!doctype html><p>invalid_redirect_uri</p>"

        def volver(**q: str) -> tuple[int, str]:
            q = {**q, **({"state": consulta["state"]} if consulta.get("state") else {}), "iss": self.base}
            return 302, vuelta + ("&" if "?" in vuelta else "?") + urlencode(q)

        if consulta.get("response_type") != "code":
            return volver(error="unsupported_response_type")
        if consulta.get("code_challenge_method") != "S256" or not consulta.get("code_challenge"):
            return volver(error="invalid_request", error_description="PKCE S256 is required")
        recurso = consulta.get("resource")
        if recurso is not None and recurso != self.recurso:
            return volver(error="invalid_target")
        pedidos = (consulta.get("scope") or "").split()
        # Lo que este servidor no ofrece se descarta sin avisar (un Mnemo anterior, con `mnemo:model`)
        ofrecidos = self.ofrecidos()
        mnemo = [a for a in pedidos if a in ofrecidos] or [a for a in ofrecidos if a != "mnemo:model"]
        elegidos = [a for a in mnemo if self.marcar is None or a in self.marcar]
        if self.decision != "allow" or not elegidos:
            return volver(error="access_denied")
        gid = self._concesion(cid, dict(self.cuenta), elegidos, [a for a in pedidos if a in OIDC])
        code = secrets.token_urlsafe(32)
        self.codigos[code] = {"client_id": cid, "redirect_uri": vuelta, "reto": consulta["code_challenge"],
                              "recurso": recurso or self.recurso, "gid": gid, "usado": False}
        return volver(code=code)

    def seguir(self, url: str) -> dict:
        """Lo que trae la vuelta al panel tras `url` (la de autorización que devolvió `conectar`): `{code, state,
        iss}` o `{error, state, iss}`."""
        partes = urlsplit(url)
        assert f"{partes.scheme}://{partes.netloc}{partes.path}" == self.endpoints()["authorize"], url
        estado, destino = self.autorizar({k: v[0] for k, v in parse_qs(partes.query).items()})
        assert estado == 302, destino
        return {k: v[0] for k, v in parse_qs(urlsplit(destino).query).items()}

    # ── ASGI ──
    def url(self, ruta: str) -> str:
        return self.base + ruta

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] == "lifespan":
            while (await receive())["type"] != "lifespan.shutdown":
                pass
            await send({"type": "lifespan.shutdown.complete"})
            return
        ruta = scope["path"]
        if ruta.rstrip("/") == "/mcp":  # el cuerpo lo lee (y lo guarda en sus `peticiones`) el MnemoFalso
            self.peticiones.append({"metodo_http": scope["method"], "ruta": ruta, "consulta": {}, "form": None,
                                    "json": None, "tipo": ""})
            self.mcp.prm = self.url(self.ruta_prm)
            return await self.mcp(scope, receive, send)
        cab = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
        cuerpo = b""
        while True:
            m = await receive()
            cuerpo += m.get("body", b"")
            if not m.get("more_body"):
                break
        tipo = cab.get("content-type", "")
        form = {k: v[0] for k, v in parse_qs(cuerpo.decode()).items()} if tipo.startswith(
            "application/x-www-form-urlencoded") else None
        try:
            datos = json.loads(cuerpo) if cuerpo and tipo.startswith("application/json") else None
        except ValueError:
            datos = None
        consulta = {k: v[0] for k, v in parse_qs(scope.get("query_string", b"").decode()).items()}
        self.peticiones.append({"metodo_http": scope["method"], "ruta": ruta, "consulta": consulta, "form": form,
                                "json": datos, "tipo": tipo})
        if ruta in self.forzar:
            estado, respuesta = self.forzar[ruta]
            return await _responder_json(send, estado, respuesta)
        metodo = scope["method"]
        if metodo == "GET" and ruta in ("/.well-known/oauth-protected-resource/mcp",
                                        "/.well-known/oauth-protected-resource"):
            return await _responder_json(send, 200, self.prm())
        if metodo == "GET" and ruta in ("/.well-known/oauth-authorization-server", "/.well-known/openid-configuration"):
            return await _responder_json(send, 200, self.metadatos())
        if metodo == "POST" and ruta == "/oauth/register":
            return await _responder_json(send, *self._registro(datos))
        if metodo == "GET" and ruta == "/oauth/authorize":
            estado, destino = self.autorizar(consulta)
            if estado == 302:
                await send({"type": "http.response.start", "status": 302, "headers": [(b"location", destino.encode()),
                                                                                       (b"content-length", b"0")]})
                await send({"type": "http.response.body", "body": b""})
                return
            return await _responder_json(send, estado, destino)
        if metodo == "POST" and ruta == "/oauth/token":
            # Lo remoto no se cancela porque el cliente se vaya: Mnemo rota aunque nadie lea la respuesta
            estado, respuesta = await asyncio.shield(asyncio.ensure_future(self._token(form, tipo)))
            return await _responder_json(send, estado, respuesta, {"cache-control": "no-store"})
        if metodo == "POST" and ruta == "/oauth/revoke":
            self._revocar(form or {})
            return await _responder_json(send, 200, "")
        return await _responder_json(send, 404, {"error": "not_found"})

    def _registro(self, datos: Any) -> tuple[int, dict]:
        self.registros += 1
        uris = datos.get("redirect_uris") if isinstance(datos, dict) else None
        if not isinstance(uris, list) or not uris or not all(isinstance(u, str) for u in uris):
            return 400, {"error": "invalid_client_metadata", "error_description": "redirect_uris is mandatory"}
        for u in uris:
            p = urlsplit(u)
            if p.fragment or "#" in u:
                return 400, {"error": "invalid_redirect_uri", "error_description": "redirect_uris must not contain "
                                                                                    "fragments"}
            if p.scheme not in ("http", "https"):
                return 400, {"error": "invalid_redirect_uri", "error_description": "redirect_uris must only contain "
                                                                                    "web uris"}
            if self.solo_loopback_http and p.scheme == "http" and p.hostname not in ("127.0.0.1", "localhost", "::1"):
                return 400, {"error": "invalid_redirect_uri", "error_description": "redirect_uris may only use http "
                             "with a loopback host (localhost, 127.0.0.1 or [::1])"}
        cid = self.registrar(uris[0], str(datos.get("client_name") or ""))
        self.clientes[cid]["redirect_uris"] = list(uris)
        return 201, {"client_id": cid, "client_id_issued_at": int(time.time()), "client_name": datos.get("client_name"),
                     "redirect_uris": uris, "token_endpoint_auth_method": "none", "application_type": "web",
                     "response_modes": ["query"], "grant_types": ["authorization_code", "refresh_token"],
                     "response_types": ["code"]}

    async def _token(self, form: dict | None, tipo: str) -> tuple[int, dict]:
        if form is None:
            return 400, {"error": "invalid_request", "error_description": "only application/x-www-form-urlencoded "
                                                                          "content-type bodies are supported on POST "
                                                                          "/oauth/token"}
        cid = form.get("client_id")
        if cid not in self.clientes:
            return 401, {"error": "invalid_client", "error_description": "client authentication failed"}
        if form.get("grant_type") == "authorization_code":
            c = self.codigos.get(form.get("code") or "")
            if c is None or c["client_id"] != cid:
                return 400, dict(INVALIDO)
            if c["usado"]:  # reusar el code revoca la conexión entera
                self.revocar_concesion(c["gid"])
                return 400, dict(INVALIDO)
            reto = _b64(hashlib.sha256((form.get("code_verifier") or "").encode()).digest())
            if form.get("redirect_uri") != c["redirect_uri"] or reto != c["reto"]:
                return 400, dict(INVALIDO)  # un PKCE o una vuelta erróneos no gastan el code
            c["usado"] = True
            if form.get("resource") not in (None, c["recurso"]):
                return 400, {"error": "invalid_target"}  # un resource erróneo sí lo gasta
            return 200, self._emitir(c["gid"], con_id_token=True)
        if form.get("grant_type") == "refresh_token":
            r = self.refrescos.get(form.get("refresh_token") or "")
            if r is None or self.concesiones[r["gid"]]["client_id"] != cid:
                return 400, dict(INVALIDO)
            self.renovaciones += 1
            if self.demora:
                await asyncio.sleep(self.demora)
            g = self.concesiones[r["gid"]]
            if r["usado"]:  # reusar un refresh ya rotado revoca la concesión entera
                self.revocar_concesion(r["gid"])
                return 400, dict(INVALIDO)
            if g["revocada"] or r["muerto"]:
                return 400, dict(INVALIDO)
            r["usado"] = True
            return 200, self._emitir(r["gid"], con_id_token=False)
        return 400, {"error": "unsupported_grant_type"}

    def _revocar(self, form: dict) -> None:
        token, cid = form.get("token") or "", form.get("client_id")
        tipo = "refresh" if token in self.refrescos else "access" if token in self.accesos else None
        self.revocaciones.append({"token": token, "token_type_hint": form.get("token_type_hint"), "client_id": cid,
                                  "tipo": tipo})
        g = self.concesion_de(token)
        if g is None or g["client_id"] != cid:
            return
        if tipo == "refresh":
            g["revocada"] = True
        else:  # con el access: muere él y los refresh de su concesión, pero la concesión queda viva («zombi»)
            gid = self.accesos[token]["gid"]
            self.accesos[token]["revocado"] = True
            for r in self.refrescos.values():
                if r["gid"] == gid:
                    r["muerto"] = True
            g["zombi"] = True


async def _responder_json(send: Callable, estado: int, cuerpo: Any, extra: dict | None = None) -> None:
    crudo = json.dumps(cuerpo).encode() if not isinstance(cuerpo, str) else cuerpo.encode()
    tipo = b"text/html" if isinstance(cuerpo, str) and cuerpo else b"application/json"
    cab = [(b"content-type", tipo), (b"content-length", str(len(crudo)).encode())]
    cab += [(k.encode(), v.encode()) for k, v in (extra or {}).items()]
    await send({"type": "http.response.start", "status": estado, "headers": cab})
    await send({"type": "http.response.body", "body": crudo})


class _TransporteOAuth(httpx2.AsyncBaseTransport):
    """El transporte ASGI del `OAuthFalso`, con las rutas de `sin_red` cayendo como una conexión rechazada."""

    def __init__(self, falso: OAuthFalso):
        self.falso, self.asgi = falso, httpx2.ASGITransport(app=falso)

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        if any(request.url.path.startswith(r) for r in self.falso.sin_red):
            raise httpx2.ConnectError("conexión rechazada (prueba)", request=request)
        return await self.asgi.handle_async_request(request)

    async def aclose(self) -> None:
        return None


# ───────────────────────────── El modelo de Mnemo, falso ─────────────────────────────

MODELO = "mnemo_model_complete"
MODELO_FALSO = {"provider": "proveedor-falso", "model": "modelo-inventado"}
FINES_MODELO = ["end_turn", "tool_use", "max_tokens", "refusal", "other"]
# Gastar modelo es una lectura (no escribe nada en Mnemo) que no es idempotente
ANOTACIONES_MODELO = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False}


def herramienta_modelo() -> dict:
    """`mnemo_model_complete` como la lista Mnemo (`catalog/model.ts`): el esquema de la entrada, resumido, y el de la
    salida (`structuredContent`)."""
    d = herramienta(MODELO, "Get a model response", {
        "system": {"type": "string", "maxLength": 400000},
        "messages": {"type": "array", "minItems": 1, "maxItems": 2000, "items": {"type": "object"}},
        "tools": {"type": "array", "maxItems": 128, "items": {"type": "object"}},
        "tool_choice": {"anyOf": [{"type": "string", "enum": ["auto", "none"]}, {"type": "object"}]},
        "model": {"type": "object", "properties": {"provider": {"type": "string"}, "model": {"type": "string"}}},
        "max_tokens": {"type": "integer", "minimum": 1, "maximum": 32000},
        "temperature": {"type": "number", "minimum": 0, "maximum": 2},
        "reasoning": {"type": "string", "enum": ["off", "low", "medium", "high"]},
    }, ["messages"], ANOTACIONES_MODELO,
        "Runs ONE step of your own agent loop on the person's Mnemo models and credits (inventada para pruebas).")
    d["outputSchema"] = {"$schema": ESQUEMA, "type": "object", "required": ["content", "stop_reason", "model"],
                         "properties": {"content": {"type": "array"},
                                        "stop_reason": {"type": "string", "enum": FINES_MODELO},
                                        "model": {"type": "object"}, "usage": {"type": "object"}}}
    return d


def respuesta_modelo(*bloques: dict, stop: str = "end_turn", uso: dict | None = None, modelo: dict | None = None,
                     avance: list[str] | None = None) -> dict:
    """Una respuesta guionizada de `mnemo_model_complete` para `ModeloFalso`: `{"datos": structuredContent, "avance":
    trozos}`. `datos` lleva los bloques (`text`, `tool_use`, `thinking`; un `thinking` de la Messages API, con la clave
    `thinking`, se pasa a la forma de Mnemo, con `text`), `stop_reason`, `model` (por defecto `MODELO_FALSO`) y `usage`
    (por defecto 900 de entrada y 50 de salida; `uso` los cambia o agrega `credits`). `avance` son los trozos de texto
    que llegan antes del resultado por `notifications/progress`: None, el texto de cada bloque en dos mitades; [],
    ninguno."""
    contenido = []
    for b in bloques:
        if b.get("type") == "thinking" and "thinking" in b:
            b = {"type": "thinking", "text": b["thinking"], **({"signature": b["signature"]} if b.get("signature")
                                                                else {})}
        contenido.append(copy.deepcopy(b))
    datos = {"content": contenido, "stop_reason": stop, "model": dict(modelo or MODELO_FALSO),
             "usage": {"input_tokens": 900, "output_tokens": 50, **(uso or {})}}
    return {"datos": datos, "avance": None if avance is None else list(avance)}


def _mitades(texto: str) -> list[str]:
    m = len(texto) // 2
    return [t for t in (texto[:m], texto[m:]) if t]


class ModeloFalso:
    """`mnemo_model_complete` en un `MnemoFalso` (la agrega a su catálogo y a sus manejadores), con un guion.

    * `cola`: lo que contesta cada llamada, en orden: una respuesta de `respuesta_modelo` (su `structuredContent`, con
      el texto antes a trozos por `notifications/progress` si la llamada trajo `_meta.progressToken`), un error de
      Mnemo (`fallo(codigo, mensaje, detalles)`), un `result` de MCP crudo (un dict con `content`) o una función
      `async def f(args, avisar) -> result`. Sin nada en la cola contesta un error INTERNAL (la prueba lo nota).
    * `pedidos`: los argumentos de cada llamada, tal como llegaron (para mirar qué se mandó).
    * `quitar()`: Mnemo deja de ofrecerla (una conexión sin `mnemo:model`): `tools/call` da -32602.
    * `mcp` es el `MnemoFalso` y `oauth`, su `OAuthFalso` si lo hay (`ayudas_agente.encender_mnemo`)."""

    def __init__(self, mcp: MnemoFalso, *guion: Any, oauth: "OAuthFalso | None" = None):
        self.mcp, self.oauth = mcp, oauth
        self.cola: deque = deque(guion)
        self.pedidos: list[dict] = []
        if not any(h["name"] == MODELO for h in mcp.herramientas):
            mcp.herramientas.append(herramienta_modelo())
        mcp.manejadores[MODELO] = self.atender

    def agregar(self, *guion: Any) -> None:
        self.cola.extend(guion)

    def quitar(self) -> None:
        self.mcp.herramientas = [h for h in self.mcp.herramientas if h["name"] != MODELO]

    def tokens_de_avance(self) -> list[Any]:
        """El `_meta.progressToken` de cada `tools/call` del modelo que llegó (None si no lo trajo)."""
        return [((p["json"].get("params") or {}).get("_meta") or {}).get("progressToken") for p in self.mcp.peticiones
                if isinstance(p["json"], dict) and p["json"].get("method") == "tools/call"
                and (p["json"].get("params") or {}).get("name") == MODELO]

    async def atender(self, args: dict, avisar: Callable) -> dict:
        self.pedidos.append(copy.deepcopy(args))
        if not self.cola:
            return fallo("INTERNAL", "ModeloFalso: no quedan respuestas en el guion.")
        item = self.cola.popleft()
        if callable(item):
            return await item(args, avisar)
        if isinstance(item, dict) and "datos" in item:
            datos = copy.deepcopy(item["datos"])
            avance = item.get("avance")
            if avance is None:
                avance = [t for b in datos["content"] if b.get("type") == "text" for t in _mitades(b.get("text") or "")]
            for i, trozo in enumerate(avance, 1):
                await avisar(i, trozo)
            return correcto(datos)
        return copy.deepcopy(item)


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
