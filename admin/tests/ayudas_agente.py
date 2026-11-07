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


# ───────────────────────────── El turno completo por la API (núcleo) ─────────────────────────────

def encender(app, *guion, modelo: str | None = None) -> FakeAPI:
    """Enciende el asistente en `app` con una clave inventada y la Messages API simulada (`guion` como en
    `cliente_falso`). Devuelve el `FakeAPI` para mirar lo que se le mandó al modelo y agregar respuestas."""
    import dataclasses
    cambios = {"anthropic_api_key": "clave-falsa", **({"agente_modelo": modelo} if modelo else {})}
    app.state.cfg = dataclasses.replace(app.state.cfg, **cambios)
    app.state.agente_cliente, api = cliente_falso(*guion)
    return api


def ndjson(texto: str) -> list[dict]:
    """Los eventos de una respuesta NDJSON (una línea JSON por evento; nunca líneas vacías)."""
    lineas = texto.split("\n")
    assert lineas[-1] == "", "el flujo termina con un salto de línea"
    assert all(lineas[:-1]), "el flujo no tiene líneas vacías"
    return [json.loads(x) for x in lineas[:-1]]


def enviar(c, texto: str = "¿Cuántas personas hay?", conversacion: int | None = None, contexto: dict | None = None):
    """POST /api/agente/mensajes: (respuesta, eventos). Sin flujo (4xx/5xx), los eventos son []."""
    r = c.post("/api/agente/mensajes", json={"conversacion": conversacion, "texto": texto, "contexto": contexto})
    return r, (ndjson(r.text) if r.status_code == 200 else [])


def decidir(c, conversacion: int, **decisiones: bool):
    """POST /api/agente/confirmaciones con {id: aprobar}: (respuesta, eventos)."""
    r = c.post("/api/agente/confirmaciones", json={"conversacion": conversacion, "decisiones": [
        {"id": k, "aprobar": v} for k, v in decisiones.items()]})
    return r, (ndjson(r.text) if r.status_code == 200 else [])


def tipos(eventos: list[dict]) -> list[str]:
    """Los tipos de evento en orden, juntando los deltas seguidos del mismo tipo (texto, progreso)."""
    out: list[str] = []
    for e in eventos:
        if e["tipo"] in ("texto", "progreso") and out and out[-1] == e["tipo"]:
            continue
        out.append(e["tipo"])
    return out


def texto_de(eventos: list[dict], tipo: str = "texto") -> str:
    return "".join(e["texto"] for e in eventos if e["tipo"] == tipo)


def herramientas_falsas():
    """Herramientas inventadas para probar el bucle sin depender de las reales: (lista, registro de llamadas).

    * `contar_falsa` (lectura, `personas.buscar`): {lugar, persona_id?} → un conteo; si trae `persona_id`, esa persona
      queda en `Resultado.personas`. Manda una acción de mapa al navegador.
    * `nota_falsa` (escritura, `personas.notas`): {persona_id, texto} → una nota de verdad por la API interna, con la
      clave de idempotencia del contrato.
    * `falla_falsa` (lectura): {modo: interno | error | fatal} → un error de cada tipo.
    Cada llamada se anota en el registro: (nombre, entrada, conversacion_id, tool_use_id)."""
    from pydantic import BaseModel, Field

    from app.agente.herramientas.base import Confirmacion, ErrorHerramienta, Herramienta, Resultado
    registro: list[tuple] = []

    class Contar(BaseModel):
        lugar: str = Field(..., min_length=1, max_length=80)
        persona_id: int | None = None

    class Nota(BaseModel):
        persona_id: int
        texto: str = Field(..., min_length=1, max_length=2000)

    class Falla(BaseModel):
        modo: str

    async def contar(ctx, a: Contar):
        registro.append(("contar_falsa", a.model_dump(), ctx.conversacion_id, ctx.tool_use_id))
        return Resultado({"total": 3, "lugar": a.lugar}, resumen="3 personas",
                         personas={a.persona_id} if a.persona_id else set(),
                         acciones=[{"tipo": "mapa", "acciones": [{"tipo": "volar", "lat": 7.0, "lon": -73.9}]}])

    async def preparar_nota(ctx, a: Nota):
        return Confirmacion("Agregar una nota", [("Persona", f"#{a.persona_id}"), ("Nota", a.texto)],
                            aviso="Queda en la ficha")

    async def nota(ctx, a: Nota):
        registro.append(("nota_falsa", a.model_dump(), ctx.conversacion_id, ctx.tool_use_id))
        await ctx.api.post(f"/api/personas/{a.persona_id}/notas", {"texto": a.texto},
                           clave=f"agente.{ctx.conversacion_id}.{ctx.tool_use_id}")
        return Resultado({"ok": True}, resumen="Nota guardada", acciones=[{"tipo": "recargar"}],
                         personas={a.persona_id})

    async def falla(ctx, a: Falla):
        registro.append(("falla_falsa", a.model_dump(), ctx.conversacion_id, ctx.tool_use_id))
        if a.modo == "fatal":
            raise ErrorHerramienta("Llegó al tope de personas consultadas hoy.", "volumen", fatal=True)
        if a.modo == "error":
            raise ErrorHerramienta("Esa persona no existe.", "no_existe")
        raise RuntimeError("fallo interno inventado")

    lista = [
        Herramienta("contar_falsa", "Cuenta personas de un lugar (prueba).", Contar, "lectura", ("personas.buscar",),
                    "Contando personas", contar),
        Herramienta("nota_falsa", "Agrega una nota a una ficha (prueba).", Nota, "escritura", ("personas.notas",),
                    "Agregando la nota", nota, confirmar=preparar_nota),
        Herramienta("falla_falsa", "Siempre falla (prueba).", Falla, "lectura", ("personas.buscar",),
                    "Probando un fallo", falla),
    ]
    return lista, registro


def con_herramientas(monkeypatch, lista) -> None:
    """Que el catálogo fijo del asistente sea `lista` (en lugar de personas + gestión + interfaz)."""
    from app.agente import herramientas
    monkeypatch.setattr(herramientas, "fijas", lambda: list(lista))


class Corte:
    """Para `FakeAPILenta`: una respuesta 200 que manda `eventos` y luego se corta con `error` (un fallo de transporte
    a mitad del cuerpo, que el SDK no reintenta)."""

    def __init__(self, eventos: list[dict], error: BaseException):
        self.eventos, self.error = eventos, error


class FakeAPILenta(FakeAPI):
    """Como `FakeAPI`, pero cada evento SSE sale `pausa` segundos después del anterior: para ver la llegada por partes,
    el latido y una desconexión a mitad de una ronda. Acepta además `Corte`."""

    def __init__(self, guion, pausa: float = 0.3):
        super().__init__(guion)
        self.pausa = pausa

    def __call__(self, req: httpx2.Request) -> httpx2.Response:
        self.peticiones.append({"url": str(req.url), "cabeceras": dict(req.headers), "json": json.loads(req.content)})
        if not self.guion:
            raise AssertionError("FakeAPILenta: no quedan respuestas en el guion")
        item = self.guion.popleft()
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, tuple):
            return httpx2.Response(item[0], json=item[1])
        corte = item.error if isinstance(item, Corte) else None
        item = item.eventos if isinstance(item, Corte) else item
        eventos = [f"event: {e['type']}\ndata: {json.dumps(e)}\n\n".encode() for e in item]
        if corte is not None:
            eventos = eventos[:len(eventos) // 2]
        pausa = self.pausa

        async def trozos():
            import asyncio
            for ev in eventos:
                await asyncio.sleep(pausa)
                yield ev
            if corte is not None:
                raise corte

        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=trozos())


def encender_lento(app, *guion, pausa: float = 0.3) -> FakeAPILenta:
    """`encender` con la Messages API lenta (`FakeAPILenta`)."""
    import dataclasses
    app.state.cfg = dataclasses.replace(app.state.cfg, anthropic_api_key="clave-falsa")
    api = FakeAPILenta(guion, pausa)
    http = httpx2.AsyncClient(transport=httpx2.MockTransport(api))
    app.state.agente_cliente = anthropic.AsyncAnthropic(api_key="clave-falsa", http_client=http, max_retries=0)
    return api
