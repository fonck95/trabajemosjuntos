"""Ayudas para las pruebas del asistente. Solo datos inventados: nunca llaman a Anthropic ni a Mnemo reales.

* `quien_de(app, uid)` y `contexto(app, cliente_rol)`: el `Quien` y el `Contexto` de una herramienta con la sesión de
  un cliente de prueba (el de `sesion`, el de `como(rol)` o el de `ayudas_g3.coordinador`).
* `correr(cliente, fn, *args)`: corre una corrutina en el bucle de la app (el portal del TestClient de `cliente`). Las
  herramientas llaman a la API por ASGI y tienen que correr en el mismo bucle que la aplicación.
* `FakeAPI`, `cliente_falso` y `sse`: la Messages API simulada con `httpx2.MockTransport` (el SDK de verdad, sin red),
  con turnos SSE realistas. `T`, `TH` y `TU` arman bloques de texto, de razonamiento o progreso y de `tool_use`.
"""
from __future__ import annotations

import json
from collections import deque
from typing import Any, Callable

import anthropic
import httpx2

from app import acceso
from app.agente.herramientas.base import Contexto
from app.agente.interno import ApiInterna
from app.seguridad import COOKIE


# ───────────────────────────── Identidad y contexto ─────────────────────────────

def quien_de(app, uid: int | None) -> acceso.Quien:
    """El `Quien` que armaría `requiere` para ese usuario (0 o None: el administrador de `.env`)."""
    if uid in (0, None):
        return acceso.quien_admin(app.state.cfg)
    u = app.state.db.usuarios.find_one({"_id": uid}, {"clave": 0})
    rol = u["rol"]
    asig = u.get("asignacion") or {}
    return acceso.Quien(uid=uid, usuario=u["usuario"], nombre=u.get("nombre"), rol=rol,
                        permisos=acceso.PERMISOS.get(rol, frozenset()),
                        asignacion=None if rol in ("admin", "coordinador") else {
                            "lugares": list(asig.get("lugares") or []), "areas": list(asig.get("areas") or [])})


def contexto(app, cliente_rol, *, uid: int | None = None, conversacion_id: int = 1, ajustes: dict | None = None,
             mnemo: Any = None, tool_use_id: str = "toolu_prueba") -> Contexto:
    """El contexto de una herramienta con la sesión (cookie y CSRF) de `cliente_rol`. `uid` por defecto: el del
    cliente (`.uid` de `como`), o 0 si no lo trae (el administrador de `sesion`)."""
    uid = getattr(cliente_rol, "uid", 0) if uid is None else uid
    cookie = cliente_rol.cookies.get(COOKIE)
    csrf = cliente_rol.headers.get("X-CSRF-Token", "")
    api = ApiInterna(app, cookie or "", csrf, "203.0.113.7")
    return Contexto(quien=quien_de(app, uid), db=app.state.db, cfg=app.state.cfg, app=app, api=api,
                    ajustes=ajustes or {}, conversacion_id=conversacion_id, tool_use_id=tool_use_id, mnemo=mnemo)


def correr(cliente, fn: Callable[..., Any], *args: Any) -> Any:
    """Corre `await fn(*args)` en el bucle de la aplicación de `cliente` (el TestClient del fixture `cliente`)."""
    return cliente.portal.call(fn, *args)


async def ejecutar(herramienta, ctx: Contexto, entrada: dict):
    """Valida `entrada` como lo haría el bucle y ejecuta la herramienta."""
    return await herramienta.ejecutar(ctx, herramienta.validar(entrada))


async def confirmar(herramienta, ctx: Contexto, entrada: dict):
    return await herramienta.confirmar(ctx, herramienta.validar(entrada))


# ───────────────────────────── Anthropic simulado ─────────────────────────────

class FakeAPI:
    """Cola de respuestas, una por petición HTTP: una lista de eventos SSE (de `sse`), una tupla (estado, cuerpo JSON)
    o una excepción para lanzar. Guarda en `peticiones` la URL, las cabeceras y el JSON de cada petición."""

    def __init__(self, guion):
        self.guion, self.peticiones = deque(guion), []

    def agregar(self, *guion) -> None:
        self.guion.extend(guion)

    def __call__(self, req: httpx2.Request) -> httpx2.Response:
        self.peticiones.append({"url": str(req.url), "cabeceras": dict(req.headers), "json": json.loads(req.content)})
        if not self.guion:
            raise AssertionError("FakeAPI: no quedan respuestas en el guion")
        item = self.guion.popleft()
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, tuple):
            return httpx2.Response(item[0], json=item[1])
        cuerpo = "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in item).encode()

        async def trozos():  # llega troceado, como por la red
            for i in range(0, len(cuerpo), 64):
                yield cuerpo[i:i + 64]

        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=trozos())


def cliente_falso(*guion) -> tuple[anthropic.AsyncAnthropic, FakeAPI]:
    api = FakeAPI(guion)
    http = httpx2.AsyncClient(transport=httpx2.MockTransport(api))
    return anthropic.AsyncAnthropic(api_key="clave-falsa", http_client=http, max_retries=0), api


def sse(*bloques: dict, stop: str = "end_turn", stop_details: dict | None = None, model: str = "claude-opus-5-5",
        error: str | None = None, uso: dict | None = None) -> list[dict]:
    """Un turno SSE realista: thinking, text y tool_use se trocean en deltas; `tool_use["input"]` puede ser un texto
    (JSON roto, para probar el analizador tolerante). `error` corta el turno con un evento SSE de error."""
    usage = {"input_tokens": 900, "output_tokens": 1, "cache_creation_input_tokens": 800,
             "cache_read_input_tokens": 0, **(uso or {})}
    ev = [{"type": "message_start", "message": {"id": "msg_prueba", "type": "message", "role": "assistant",
                                                "model": model, "content": [], "stop_reason": None,
                                                "stop_sequence": None, "usage": usage}},
          {"type": "ping"}]
    for i, b in enumerate(bloques):
        t, deltas = b["type"], []
        if t == "thinking":
            inicio = {"type": "thinking", "thinking": "", "signature": ""}
            if b["thinking"]:
                deltas.append({"type": "thinking_delta", "thinking": b["thinking"]})
            deltas.append({"type": "signature_delta", "signature": b["signature"]})
        elif t == "text":
            inicio, m = {"type": "text", "text": ""}, len(b["text"]) // 2
            deltas = [{"type": "text_delta", "text": b["text"][:m]}, {"type": "text_delta", "text": b["text"][m:]}]
        elif t == "tool_use":
            crudo = b["input"] if isinstance(b["input"], str) else json.dumps(b["input"])
            inicio, m = {**b, "input": {}}, len(crudo) // 2
            deltas = [{"type": "input_json_delta", "partial_json": p} for p in ("", crudo[:m], crudo[m:])]
        else:
            inicio = b  # redacted_thinking, fallback, server_tool_use: llegan completos, sin deltas
        ev.append({"type": "content_block_start", "index": i, "content_block": inicio})
        ev += [{"type": "content_block_delta", "index": i, "delta": d} for d in deltas]
        ev.append({"type": "content_block_stop", "index": i})
    if error:
        return ev + [{"type": "error", "error": {"type": error, "message": error}}]
    return ev + [{"type": "message_delta", "usage": {"output_tokens": 50},
                  "delta": {"stop_reason": stop, "stop_sequence": None, "stop_details": stop_details}},
                 {"type": "message_stop"}]


def T(texto: str) -> dict:
    return {"type": "text", "text": texto}


def TH(texto: str = "", firma: str = "firma") -> dict:
    """Un bloque thinking: con texto es una nota de progreso (`display: "updates"`); vacío, razonamiento oculto."""
    return {"type": "thinking", "thinking": texto, "signature": firma}


def TU(id_: str, nombre: str, entrada: Any) -> dict:
    return {"type": "tool_use", "id": id_, "name": nombre, "input": entrada}
