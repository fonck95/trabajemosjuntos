"""Mnemo en el asistente: el cliente MCP (`app/agente/mnemo_cliente.py`) y sus herramientas
(`app/agente/herramientas/mnemo.py`), contra un servidor MCP falso que imita al `/mcp` de Mnemo (`ayudas_mcp.py`).
Nunca se llama a Mnemo ni a Anthropic de verdad; solo datos inventados.

Qué se prueba: el protocolo (cabeceras, `initialize` una vez, SSE con keepalive y JSON en varias líneas, JSON plano,
paginación, caché, sesión, plazos de verdad por red), los errores (401, 406, -32602, `isError`, validación en texto
plano, HTTP, red) sin el token en ningún mensaje ni registro, las definiciones (lista blanca, limpieza, nombres,
tipos, esquemas), la tarjeta de las escrituras, quién las usa, los resultados (imágenes, enlaces, aprobaciones con
enlace absoluto, recortes) y un turno completo del asistente con Mnemo. Al final, una prueba de punta a punta contra
el Mnemo real levantado en local, que se salta si no hay un checkout preparado (`MNEMO_E2E_DIR`)."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import time
from dataclasses import replace
from types import SimpleNamespace

import httpx2
import pytest
from pydantic import ValidationError
from starlette.datastructures import State

from ayudas_mcp import JPEG_2x3, PNG_1x1, TOKEN, EnHilo, MnemoFalso, b64

from app import acceso
from app.agente import mnemo_cliente as mc
from app.agente.herramientas import mnemo
from app.agente.herramientas.base import MAX_CONTENIDO, Contexto, ErrorHerramienta, Resultado
from app.config import Config

URL = "https://mnemo.example.org/mcp"
ORIGEN = "https://mnemo.example.org"
SECRETO = TOKEN.rsplit("_", 1)[1]
CON_MNEMO = SimpleNamespace(llamar=lambda *a, **k: None)  # un cliente cualquiera: la tarjeta no llama a Mnemo


def correr(coro):
    return asyncio.run(coro)


def _cfg(**kw) -> Config:
    base = dict(usuario="admin", clave="clave-de-prueba-larga", mongodb_uri="mongodb://127.0.0.1:27017",
                mongodb_db="prueba_mnemo", horas_sesion=1, cookie_segura=False, max_subida_mb=5, mnemo_url=URL,
                mnemo_token=TOKEN)
    return Config(**{**base, **kw})


def _cliente(falso: MnemoFalso, **kw) -> mc.ClienteMnemo:
    return mc.ClienteMnemo(URL, kw.pop("token", TOKEN), transporte=falso.transporte(), **kw)


def _ctx(cliente, cfg: Config | None = None) -> Contexto:
    """El contexto de una herramienta de Mnemo: solo usan `mnemo` y `cfg` (no tocan la base ni la API del panel)."""
    return Contexto(quien=None, db=None, cfg=cfg or _cfg(), app=None, api=None, ajustes={}, conversacion_id=1,
                    tool_use_id="toolu_mnemo", mnemo=cliente)


async def _herramientas(falso: MnemoFalso, filtro: str = "*") -> tuple[mc.ClienteMnemo, dict]:
    cliente = _cliente(falso)
    defs = await mnemo.definiciones(cliente, filtro)
    return cliente, {h.nombre: h for h in mnemo.desde_definiciones(defs)}


async def _fallo(coro) -> ErrorHerramienta:
    with pytest.raises(ErrorHerramienta) as e:
        await coro
    return e.value


# ───────────────────────────── Protocolo ─────────────────────────────

def test_inicio_una_vez_con_las_cabeceras_de_mnemo():
    falso = MnemoFalso()

    async def prueba():
        c = _cliente(falso)
        lista = await c.herramientas()
        await c.herramientas()
        await c.llamar("search", {"query": "acta"})
        await c.llamar("search", {"query": "otra"})
        return c, lista

    c, lista = correr(prueba())
    assert [t["name"] for t in lista][:3] == ["search", "fetch", "mnemo_get_briefing"]
    assert [p["json"].get("method") for p in falso.peticiones] == [
        "initialize", "notifications/initialized", "tools/list", "tools/call", "tools/call"]
    for p in falso.peticiones:
        assert p["metodo_http"] == "POST" and p["ruta"] == "/mcp"
        cab = p["cabeceras"]
        assert cab["authorization"] == f"Bearer {TOKEN}" and cab["content-type"] == "application/json"
        assert cab["accept"] == "application/json, text/event-stream"
        assert cab["mcp-protocol-version"] == "2025-11-25"
    inicio = falso.peticiones[0]["json"]
    assert inicio["params"]["protocolVersion"] == "2025-11-25" and inicio["params"]["capabilities"] == {}
    assert inicio["params"]["clientInfo"]["name"] == "trabajemosjuntos-panel"
    assert "id" not in falso.peticiones[1]["json"]  # una notificación
    assert c.instrucciones.startswith("Mnemo is the person's personal AI workspace")
    assert c.servidor == {"name": "mnemo", "title": "Mnemo", "version": "1.0.0"} and c.version == "2025-11-25"


def test_sse_con_keepalive_y_json_en_varias_lineas_data():
    falso = MnemoFalso(keepalives=3, multilinea=True)
    res = correr(_cliente(falso).llamar("search", {"query": "agua"}))
    assert res["structuredContent"]["results"][0]["title"] == "Acta inventada: agua"
    assert res.get("isError") is None


def test_respuesta_en_json_plano():
    falso = MnemoFalso(formato="json")
    res = correr(_cliente(falso).llamar("fetch", {"id": "doc_1"}))
    assert res["structuredContent"]["title"] == "Acta inventada"


def test_sse_troceado_con_crlf_notificaciones_y_otros_eventos():
    """El flujo llega en trozos que parten un «\\r\\n», con un comentario, una notificación, un evento de otro tipo y la
    respuesta en dos líneas `data:` (un servidor cualquiera, no solo Mnemo)."""
    respuesta = json.dumps({"jsonrpc": "2.0", "id": 2, "result": {"content": [{"type": "text", "text": "ok"}]}},
                           indent=1)
    flujo = (": keepalive\r\n\r\n"
             "event: message\r\ndata: {\"jsonrpc\": \"2.0\", \"method\": \"notifications/progress\"}\r\n\r\n"
             "event: otro\r\ndata: {\"jsonrpc\": \"2.0\", \"id\": 2, \"result\": {\"falso\": true}}\r\n\r\n"
             "event: message\r\n" + "".join(f"data: {x}\r\n" for x in respuesta.split("\n")) + "\r\n").encode()

    def atender(req: httpx2.Request) -> httpx2.Response:
        cuerpo = json.loads(req.content)
        if cuerpo.get("method") == "initialize":
            return httpx2.Response(200, json={"jsonrpc": "2.0", "id": cuerpo["id"], "result": {
                "protocolVersion": "2025-11-25", "capabilities": {}, "serverInfo": {"name": "x"}}})
        if "id" not in cuerpo:
            return httpx2.Response(202)

        async def trozos():
            for i in range(0, len(flujo), 7):  # 7 bytes: parte los «\r\n» por la mitad más de una vez
                yield flujo[i:i + 7]

        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=trozos())

    c = mc.ClienteMnemo(URL, TOKEN, transporte=httpx2.MockTransport(atender))
    res = correr(c.llamar("lo_que_sea", {}))
    assert res == {"content": [{"type": "text", "text": "ok"}]}


def test_paginacion_con_next_cursor():
    falso = MnemoFalso(por_pagina=4)
    lista = correr(_cliente(falso).herramientas())
    assert [t["name"] for t in lista] == [t["name"] for t in falso.herramientas]
    pedidos = [p["json"].get("params") for p in falso.peticiones if p["json"].get("method") == "tools/list"]
    assert pedidos == [None, {"cursor": "4"}, {"cursor": "8"}, {"cursor": "12"}]


def test_un_cursor_repetido_no_deja_al_cliente_en_un_bucle():
    def atender(req: httpx2.Request) -> httpx2.Response:
        cuerpo = json.loads(req.content)
        if "id" not in cuerpo:
            return httpx2.Response(202)
        res = ({"protocolVersion": "2025-11-25", "capabilities": {}} if cuerpo["method"] == "initialize" else
               {"tools": [{"name": "search", "inputSchema": {"type": "object"}}], "nextCursor": "siempre"})
        return httpx2.Response(200, json={"jsonrpc": "2.0", "id": cuerpo["id"], "result": res})

    lista = correr(mc.ClienteMnemo(URL, TOKEN, transporte=httpx2.MockTransport(atender)).herramientas())
    assert len(lista) == 2  # la primera página y la del cursor; el cursor repetido corta


def test_la_lista_se_guarda_diez_minutos():
    falso = MnemoFalso()
    ahora = [1000.0]
    c = _cliente(falso, reloj=lambda: ahora[0])

    async def prueba():
        await c.herramientas()
        ahora[0] += mc.CACHE_S - 1
        await c.herramientas()
        assert falso.contar("tools/list") == 1 and falso.contar("initialize") == 1
        ahora[0] += 2  # vencida: se vuelve a iniciar (instrucciones al día) y a listar
        await c.herramientas()
        assert falso.contar("tools/list") == 2 and falso.contar("initialize") == 2
        await c.herramientas(forzar=True)
        assert falso.contar("tools/list") == 3

    correr(prueba())


def test_lo_que_devuelve_no_toca_la_cache():
    falso = MnemoFalso()

    async def prueba():
        c = _cliente(falso)
        lista = await c.herramientas()
        lista[0]["name"] = "cambiado"
        lista.clear()
        return await c.herramientas()

    assert correr(prueba())[0]["name"] == "search"


def test_sesion_mcp_de_un_servidor_con_estado():
    """Mnemo no usa `Mcp-Session-Id`, pero un servidor con estado sí: se manda y, si la olvida, se inicia otra vez."""
    falso = MnemoFalso(sesion="sesion-inventada-1")

    async def prueba():
        c = _cliente(falso)
        await c.llamar("search", {"query": "a"})
        falso.olvidar_sesion = True
        return await c.llamar("search", {"query": "b"})

    assert correr(prueba())["structuredContent"]["results"]
    metodos = [p["json"].get("method") for p in falso.peticiones]
    assert metodos == ["initialize", "notifications/initialized", "tools/call", "tools/call", "initialize",
                       "notifications/initialized", "tools/call"]
    assert all(p["cabeceras"].get("mcp-session-id") == "sesion-inventada-1" for p in falso.peticiones[1:]
               if p["json"].get("method") != "initialize")


def test_version_del_protocolo_desconocida():
    falso = MnemoFalso()
    falso.version = "2030-01-01"
    e = correr(_fallo(_cliente(falso).herramientas()))
    assert e.codigo == mc.COD_MNEMO and "versión del protocolo" in e.mensaje


# ───────────────────────────── Errores ─────────────────────────────

def test_401_el_token_no_es_valido_o_vencio():
    falso = MnemoFalso(token="mnemo_pat_ffffffffffffffffffffffff_" + "x" * 43)
    e = correr(_fallo(_cliente(falso).herramientas()))
    assert e.codigo == mc.COD_TOKEN and e.estado == 401 and not e.fatal
    assert "no es válido o venció" in e.mensaje and "MNEMO_TOKEN" in e.mensaje


def test_406_si_falta_accept(monkeypatch):
    """Si el cliente no mandara los dos tipos en `Accept` (httpx manda `*/*`), Mnemo diría 406: se cita su motivo."""
    monkeypatch.setattr(mc, "ACEPTA", "*/*")
    e = correr(_fallo(_cliente(MnemoFalso()).herramientas()))
    assert e.codigo == mc.COD_MNEMO and e.estado == 406 and "Not Acceptable" in e.mensaje


def test_herramienta_inexistente_32602_y_se_olvida_la_lista():
    falso = MnemoFalso()

    async def prueba():
        c = _cliente(falso)
        await c.herramientas()
        e = await _fallo(c.llamar("mnemo_no_existe", {}))
        await c.herramientas()
        return e

    e = correr(prueba())
    assert e.codigo == mc.COD_NO_DISPONIBLE and "mnemo_no_existe" in e.mensaje and "conversación nueva" in e.mensaje
    assert falso.contar("tools/list") == 2  # la lista se pidió otra vez


def test_is_error_con_codigo_y_detalles_de_mnemo():
    falso = MnemoFalso()

    async def prueba():
        c = _cliente(falso)
        return await _fallo(c.llamar("fetch", {"id": "doc_no"})), await _fallo(c.llamar("fetch", {"id": "doc_plan"}))

    no, plan = correr(prueba())
    assert no.codigo == "mnemo" and no.detalle == {"code": "NOT_FOUND"}
    assert no.mensaje.startswith("Mnemo no encontró eso") and "No item with that id." in no.mensaje
    assert plan.detalle == {"code": "PLAN_REQUIRED", "details": {"feature": "documents"}}
    assert json.loads(plan.para_modelo())["error"]["detalle"]["code"] == "PLAN_REQUIRED"


def test_error_de_validacion_en_texto_plano():
    e = correr(_fallo(_cliente(MnemoFalso()).llamar("fetch", {"id": 7})))
    assert e.codigo == "mnemo" and e.detalle == {"code": "INVALID_ARGUMENT"}
    assert "Input validation error" in e.mensaje and "expected string" in e.mensaje


def test_plazo_vencido_corta_y_mnemo_cancela():
    falso = MnemoFalso()

    async def prueba():
        c = _cliente(falso)
        await c.iniciar()
        t0 = time.monotonic()
        e = await _fallo(c.llamar("lento", {"s": 5}, plazo=0.3))
        return e, time.monotonic() - t0

    e, dt = correr(prueba())
    assert e.codigo == mc.COD_PLAZO and "no respondió en 0.3 segundos" in e.mensaje and dt < 2
    assert falso.cancelaciones == 1


def test_por_red_el_keepalive_no_alarga_el_plazo():
    """Con uvicorn de verdad: el keepalive llega cada 0,1 s (el plazo de lectura de httpx nunca vence), pero el tope
    total sí; y cuando la herramienta termina a tiempo, la respuesta llega bien entre los keepalives."""
    falso = MnemoFalso(intervalo=0.1, keepalives=0)
    with EnHilo(falso) as servidor:
        async def prueba():
            c = mc.ClienteMnemo(servidor.url, TOKEN, transporte=httpx2.AsyncHTTPTransport())
            bien = await c.llamar("lento", {"s": 0.5}, plazo=5)
            t0 = time.monotonic()
            e = await _fallo(c.llamar("lento", {"s": 4}, plazo=0.8))
            dt = time.monotonic() - t0
            await c.cerrar()
            return bien, e, dt

        bien, e, dt = correr(prueba())
        limite = time.monotonic() + 3
        while falso.cancelaciones == 0 and time.monotonic() < limite:
            time.sleep(0.05)
    assert bien["structuredContent"] == {"slept": 0.5}
    assert e.codigo == mc.COD_PLAZO and 0.7 < dt < 2.5
    assert falso.cancelaciones == 1  # el servidor vio cerrarse la conexión y canceló la herramienta


@pytest.mark.parametrize("estado, cuerpo, cabeceras, esperado", [
    (500, {"error": "boom"}, {}, "falló al atender la petición (HTTP 500)"),
    (413, {"jsonrpc": "2.0", "error": {"code": -32000, "message": "Payload too large"}, "id": None}, {},
     "demasiado grande"),
    (429, {"error": "slow down"}, {}, "demasiadas peticiones"),
    (302, "", {"location": "https://otro.example.org/mcp"}, "redirección"),
    (200, "<html>proxy</html>", {}, "no es una respuesta MCP"),
    (400, {"jsonrpc": "2.0", "error": {"code": -32000, "message": "Bad Request: Unsupported protocol version"},
           "id": None}, {}, "Unsupported protocol version"),
])
def test_errores_http(estado, cuerpo, cabeceras, esperado):
    falso = MnemoFalso()
    falso.forzar["initialize"] = (estado, cuerpo, cabeceras)
    e = correr(_fallo(_cliente(falso).herramientas()))
    assert esperado in e.mensaje and e.estado == estado
    assert len(falso.peticiones) == 1  # no siguió la redirección


def test_ruta_que_no_es_mcp():
    falso = MnemoFalso()
    c = mc.ClienteMnemo(URL.replace("/mcp", "/mcp/otra"), TOKEN, transporte=falso.transporte())
    e = correr(_fallo(c.herramientas()))
    assert e.estado == 404 and "MNEMO_MCP_URL" in e.mensaje


def test_sin_red():
    def caido(req: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("conexión rechazada", request=req)

    e = correr(_fallo(mc.ClienteMnemo(URL, TOKEN, transporte=httpx2.MockTransport(caido)).herramientas()))
    assert e.codigo == mc.COD_RED and "No se pudo conectar con Mnemo" in e.mensaje


def test_respuesta_demasiado_grande(monkeypatch):
    monkeypatch.setattr(mc, "MAX_RESPUESTA", 2_000)
    e = correr(_fallo(_cliente(MnemoFalso()).llamar("fetch", {"id": "doc_largo"})))
    assert e.codigo == mc.COD_MNEMO and "demasiado grande" in e.mensaje


def test_token_con_saltos_de_linea_no_sale():
    falso = MnemoFalso()
    e = correr(_fallo(mc.ClienteMnemo(URL, "mnemo_pat_x\ny", transporte=falso.transporte()).herramientas()))
    assert e.codigo == mc.COD_TOKEN and falso.peticiones == []


def test_direcciones_que_no_sirven():
    for url in ("ftp://mnemo.example.org/mcp", "https://usuario:clave@mnemo.example.org/mcp", "mnemo", ""):
        with pytest.raises(ValueError):
            mc.ClienteMnemo(url, TOKEN)


def test_el_token_no_aparece_en_ningun_error_ni_registro(caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    panel = logging.getLogger("panel")
    panel.addHandler(caplog.handler)  # por si el registro del panel no propaga a la raíz
    errores: list[ErrorHerramienta] = []

    async def junta(coro):
        try:
            await coro
        except ErrorHerramienta as e:
            errores.append(e)

    async def prueba():
        falso = MnemoFalso()
        c = _cliente(falso)
        await junta(c.llamar("fetch", {"id": "doc_eco"}))       # el servidor cita el token
        await junta(c.llamar("fetch", {"id": 7}))               # validación en texto plano
        await junta(c.llamar("no_existe", {}))                  # -32602
        await junta(c.llamar("lento", {"s": 3}, plazo=0.2))     # plazo
        falso.forzar["tools/call"] = (500, {"error": f"Bearer {TOKEN}"}, {})
        await junta(c.llamar("search", {"query": "x"}))         # HTTP 500 con el token en el cuerpo
        del falso.forzar["tools/call"]
        falso.token = "mnemo_pat_ffffffffffffffffffffffff_" + "y" * 43
        await junta(c.herramientas(forzar=True))                # 401
        caido = mc.ClienteMnemo(URL, TOKEN, transporte=httpx2.MockTransport(
            lambda req: (_ for _ in ()).throw(httpx2.ConnectError(f"sin red {req.headers['authorization']}",
                                                                  request=req))))
        await junta(caido.herramientas())                       # red, con el token en el texto de la excepción
        acepta = mc.ACEPTA
        monkeypatch.setattr(mc, "ACEPTA", "*/*")
        await junta(_cliente(MnemoFalso()).herramientas())      # 406
        monkeypatch.setattr(mc, "ACEPTA", acepta)
        cliente_ok, hs = await _herramientas(MnemoFalso())
        await junta(hs["mnemo_fetch"].ejecutar(_ctx(cliente_ok), hs["mnemo_fetch"].validar({"id": "doc_eco"})))
        return c

    try:
        c = correr(prueba())
    finally:
        panel.removeHandler(caplog.handler)
    assert len(errores) == 9
    for e in errores:
        for texto in (e.mensaje, str(e), repr(e), e.para_modelo(), json.dumps(e.detalle, default=str)):
            assert TOKEN not in texto and SECRETO not in texto
        assert e.__cause__ is None or SECRETO not in repr(e.__cause__)
    assert "[token]" in errores[0].mensaje
    assert TOKEN not in caplog.text and SECRETO not in caplog.text and "Mnemo:" in caplog.text
    assert SECRETO not in repr(c) and SECRETO not in repr(vars(c).get("_http"))


# ───────────────────────────── Un cliente por aplicación ─────────────────────────────

def test_cliente_de_uno_por_aplicacion():
    app = SimpleNamespace(state=State())
    assert mc.cliente_de(app, _cfg(mnemo_url="", mnemo_token="")) is None
    assert mc.cliente_de(app, _cfg(mnemo_token="")) is None
    c = mc.cliente_de(app, _cfg())
    assert isinstance(c, mc.ClienteMnemo) and mc.cliente_de(app, _cfg()) is c and app.state.mnemo_cliente is c
    otro = mc.cliente_de(app, _cfg(mnemo_token=TOKEN + "z"))
    assert otro is not c and app.state.mnemo_cliente is otro
    assert c.origen == ORIGEN and SECRETO not in repr(c)


# ───────────────────────────── Definiciones ─────────────────────────────

def test_lista_blanca_por_defecto_todas_o_las_pedidas():
    falso = MnemoFalso()

    async def nombres(filtro):
        return [d["name"] for d in await mnemo.definiciones(_cliente(falso), filtro)]

    por_defecto = correr(nombres(""))
    assert por_defecto == [t["name"] for t in falso.herramientas if t["name"] in mnemo.POR_DEFECTO]
    assert "mnemo_generate_deck" not in por_defecto and "mnemo_query_business" not in por_defecto
    assert correr(nombres(None)) == por_defecto and correr(nombres(" , ")) == por_defecto
    assert correr(nombres("*")) == [t["name"] for t in falso.herramientas]
    # En el orden del servidor, con nombres remotos o del panel, y sin las que Mnemo no ofrece
    assert correr(nombres(" mnemo_get_job, mnemo_search ,no_existe")) == ["search", "mnemo_get_job"]
    assert correr(mnemo.definiciones(None, "")) == []


def test_definiciones_limpias_y_json():
    defs = correr(mnemo.definiciones(_cliente(MnemoFalso()), "*"))
    json.dumps(defs)  # se guardan con la conversación
    for d in defs:
        assert set(d) <= {"name", "title", "description", "inputSchema", "annotations"}
        assert d["inputSchema"]["type"] == "object" and "$schema" not in d["inputSchema"]
        assert set(d["annotations"]) <= set(mnemo.PISTAS)
    fetch = next(d for d in defs if d["name"] == "fetch")
    assert fetch["annotations"] == {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True,
                                    "openWorldHint": False}
    assert fetch["title"] == "Read a Mnemo item" and "_meta" not in fetch and "outputSchema" not in fetch


def test_desde_definiciones_tipos_nombres_y_esquemas():
    defs = correr(mnemo.definiciones(_cliente(MnemoFalso()), ""))
    hs = mnemo.desde_definiciones(defs)
    assert [h.nombre for h in hs] == ["mnemo_search", "mnemo_fetch", "mnemo_get_briefing", "mnemo_view_image",
                                      "mnemo_list_events", "mnemo_create_event", "mnemo_update_event",
                                      "mnemo_export_document", "mnemo_request_share", "mnemo_check_approval",
                                      "mnemo_get_job"]
    por = {h.nombre: h for h in hs}
    assert por["mnemo_search"].tipo == "lectura" and por["mnemo_search"].confirmar is None
    assert por["mnemo_create_event"].tipo == "escritura" and por["mnemo_create_event"].confirmar is not None
    assert por["mnemo_request_share"].tipo == "escritura"
    assert por["mnemo_search"].nombre_remoto == "search" and por["mnemo_get_job"].nombre_remoto == "mnemo_get_job"
    assert por["mnemo_search"].etiqueta == "Buscando en Mnemo"
    assert por["mnemo_search"].permisos == ("agente.usar",) and por["mnemo_search"].disponible is mnemo.disponible_para
    d = por["mnemo_search"].definicion()
    assert d["name"] == "mnemo_search" and d["eager_input_streaming"] is True and "strict" not in d
    assert d["description"].startswith("Herramienta de Mnemo (allá se llama `search`). Search the person's Mnemo.")
    assert d["input_schema"] == {"type": "object", "properties": {"query": {
        "type": "string", "description": "What to look for", "minLength": 1, "maxLength": 300}}, "required": ["query"]}
    assert por["mnemo_get_job"].definicion()["description"].startswith("Herramienta de Mnemo. Get job status")
    assert por["mnemo_create_event"].definicion()["description"].endswith("la aprueba en una tarjeta del panel.")
    # Determinista: lo guardado da lo mismo cada vez (la lista congelada de la conversación no cambia)
    assert [h.definicion() for h in mnemo.desde_definiciones(json.loads(json.dumps(defs)))] == [
        h.definicion() for h in hs]


def test_nombres_sin_chocar_y_con_los_caracteres_de_la_api():
    defs = [{"name": n, "inputSchema": {"type": "object"}} for n in (
        "search", "mnemo_search", "mnemo_search_2", "a.b/c", "x" * 120)]
    nombres = [h.nombre for h in mnemo.desde_definiciones(defs)]
    assert nombres[:4] == ["mnemo_search", "mnemo_search_2", "mnemo_search_2_2", "mnemo_a_b_c"]
    assert len(set(nombres)) == 5 and all(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", n) for n in nombres)


def test_definiciones_que_no_sirven_se_descartan():
    buenas = {"name": "buena", "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}}}
    malas = [
        "no es un objeto", {"name": 7}, {"name": "con espacio", "inputSchema": {"type": "object"}},
        {"name": "lista", "inputSchema": {"type": "array"}}, {"name": "props", "inputSchema": {"properties": [1]}},
        {"name": "req", "inputSchema": {"type": "object", "required": "q"}},
        {"name": "enorme", "inputSchema": {"type": "object", "description": "x" * 40_000}},
        {"name": "nan", "inputSchema": {"type": "object", "default": float("nan")}},
    ]
    hs = mnemo.desde_definiciones([*malas, buenas, {"name": "sin_esquema"}])
    assert [h.nombre for h in hs] == ["mnemo_buena", "mnemo_sin_esquema"]
    assert hs[1].definicion()["input_schema"] == {"type": "object", "properties": {}}
    assert hs[0].tipo == "escritura"  # sin `readOnlyHint` no se supone que solo lee
    assert mnemo.desde_definiciones("no es una lista") == [] and mnemo.desde_definiciones(None) == []


def test_una_escritura_conocida_no_pasa_por_lectura_aunque_lo_diga_la_pista():
    """Las pistas de MCP las pone el servidor: una que se equivoque no le quita la tarjeta a una escritura de Mnemo."""
    hs = mnemo.desde_definiciones([
        {"name": "mnemo_create_event", "inputSchema": {"type": "object"}, "annotations": {"readOnlyHint": True}},
        {"name": "mnemo_request_delete", "inputSchema": {"type": "object"}, "annotations": {"readOnlyHint": True}},
        {"name": "mnemo_lee_algo", "inputSchema": {"type": "object"}, "annotations": {"readOnlyHint": True}}])
    assert [(h.tipo, h.confirmar is not None) for h in hs] == [("escritura", True), ("escritura", True),
                                                              ("lectura", False)]


def test_json_anidado_sin_fin_no_rompe_al_cliente():
    def atender(req: httpx2.Request) -> httpx2.Response:
        cuerpo = json.loads(req.content)
        if "id" not in cuerpo:
            return httpx2.Response(202)
        if cuerpo["method"] == "initialize":
            return httpx2.Response(200, json={"jsonrpc": "2.0", "id": cuerpo["id"], "result": {
                "protocolVersion": "2025-11-25", "capabilities": {}}})
        return httpx2.Response(200, headers={"content-type": "text/event-stream"},
                               content=("event: message\ndata: " + "[" * 200_000 + "\n\n").encode())

    e = correr(_fallo(mc.ClienteMnemo(URL, TOKEN, transporte=httpx2.MockTransport(atender)).llamar("search", {})))
    assert e.codigo == mc.COD_MNEMO and "sin contestar" in e.mensaje


def test_codigos_raros_de_mnemo_no_llegan_al_registro(caplog):
    caplog.set_level(logging.INFO)
    falso = MnemoFalso()

    async def raro(a):
        return {"content": [{"type": "text", "text": json.dumps({"error": {
            "code": "Ana Inventada 3001234567", "message": "x"}})}], "isError": True}

    falso.manejadores["search"] = raro
    e = correr(_fallo(_cliente(falso).llamar("search", {"query": "x"})))
    assert e.detalle == {"code": "FAILED"} and "3001234567" not in caplog.text


def test_la_entrada_es_un_objeto_que_cabe():
    h = mnemo.desde_definiciones([{"name": "search", "inputSchema": {"type": "object"}}])[0]
    assert h.validar({"query": "acta", "n": [1, 2]}).root == {"query": "acta", "n": [1, 2]}
    for malo in ([1], "acta", None, 3, {"x": float("nan")}, {"x": "y" * (mnemo.MAX_ENTRADA + 1)}):
        with pytest.raises(ValidationError):
            h.validar(malo)


# ───────────────────────────── Escrituras: la tarjeta ─────────────────────────────

def test_la_tarjeta_muestra_el_titulo_y_los_argumentos():
    _, hs = correr(_herramientas(MnemoFalso()))
    h = hs["mnemo_create_event"]
    args = {"zeta": True, "notes": "n" * 2000, "start": "2026-11-09T09:00:00-05:00", "title": "Reunión inventada",
            "extra": {"a": [1, 2]}, "vacio": None}
    conf = correr(h.confirmar(_ctx(CON_MNEMO), h.validar(args)))
    assert conf.titulo == "Crear un evento en el calendario de Mnemo"
    claves = [k for k, _ in conf.detalle]
    assert claves == ["title", "start", "notes", "extra", "vacio", "zeta"]  # el orden del esquema, luego el resto
    valores = dict(conf.detalle)
    assert valores["title"] == "Reunión inventada" and valores["zeta"] == "sí" and valores["vacio"] == "(vacío)"
    assert valores["extra"] == '{"a": [1, 2]}' and valores["notes"].endswith("(2000 caracteres en total)")
    assert conf.aviso == "Lo hace Mnemo con el token del administrador."
    assert conf.para_interfaz()["detalle"][0] == ["title", "Reunión inventada"]
    pedido = correr(hs["mnemo_request_share"].confirmar(_ctx(CON_MNEMO), hs["mnemo_request_share"].validar(
        {"id": "doc_acta1", "with": "equipo@example.org"})))
    assert pedido.titulo == "Pedir en Mnemo que se comparta"
    assert pedido.detalle == [("id", "doc_acta1"), ("with", "equipo@example.org")]
    assert "Aquí solo se pide" in pedido.aviso and "a la vista de otras personas" in pedido.aviso
    cambio = correr(hs["mnemo_update_event"].confirmar(_ctx(CON_MNEMO), hs["mnemo_update_event"].validar(
        {"id": "event_1", "changes": {"title": "Otra"}})))
    assert "Puede cambiar o reemplazar" in cambio.aviso
    vacia = mnemo.confirmacion({"name": "x_y", "inputSchema": {"type": "object"}, "annotations": {}}, {})
    assert vacia.titulo == "Mnemo: x_y" and vacia.detalle == [("Argumentos", "(ninguno)")]


def test_la_tarjeta_y_la_llamada_acotan_wait_seconds():
    falso = MnemoFalso()

    async def prueba():
        c, hs = await _herramientas(falso)
        gen = hs["mnemo_generate_deck"]
        conf = await gen.confirmar(_ctx(c), gen.validar({"topic": "Historia inventada"}))
        await gen.ejecutar(_ctx(c), gen.validar({"topic": "Historia inventada"}))
        job = hs["mnemo_get_job"]
        for espera in (50, 10, None):
            args = {"job_id": "job_1", **({"wait_seconds": espera} if espera else {})}
            await job.ejecutar(_ctx(c), job.validar(args))
        return conf

    conf = correr(prueba())
    assert ("wait_seconds", "40") in conf.detalle  # lo que se mandará, aunque el modelo no lo pidió
    assert [args for _, args in falso.llamadas] == [
        {"topic": "Historia inventada", "wait_seconds": 40}, {"job_id": "job_1", "wait_seconds": 40},
        {"job_id": "job_1", "wait_seconds": 10}, {"job_id": "job_1"}]


# ───────────────────────────── Quién las usa ─────────────────────────────

def test_disponible_para_por_rol_y_ajuste():
    cfg = _cfg()
    admin = acceso.quien_admin(cfg)
    coord = acceso.Quien(uid=7, usuario="k", rol="coordinador", permisos=acceso.PERMISOS["coordinador"])
    plan = acceso.Quien(uid=8, usuario="p", rol="planillero", permisos=acceso.PERMISOS["planillero"])
    cons = acceso.Quien(uid=9, usuario="c", rol="consultor", permisos=acceso.PERMISOS["consultor"])
    otro_admin = acceso.Quien(uid=3, usuario="a", rol="admin", permisos=acceso.PERMISOS["admin"])
    no, si = {"mnemo_coordinadores": False}, {"mnemo_coordinadores": True}
    assert mnemo.disponible_para(admin, no, cfg) is True
    assert mnemo.disponible_para(coord, no, cfg) is False and mnemo.disponible_para(coord, si, cfg) is True
    assert mnemo.disponible_para(coord, {"mnemo_coordinadores": "true"}, cfg) is False
    assert mnemo.disponible_para(coord, None, cfg) is False
    for q in (plan, cons, otro_admin):
        assert mnemo.disponible_para(q, si, cfg) is False
    sin = _cfg(mnemo_token="")
    assert mnemo.disponible_para(admin, si, sin) is False and mnemo.disponible_para(coord, si, sin) is False


# ───────────────────────────── Resultados ─────────────────────────────

def test_lectura_devuelve_los_datos_y_un_resumen():
    async def prueba():
        c, hs = await _herramientas(MnemoFalso())
        h = hs["mnemo_search"]
        return await h.ejecutar(_ctx(c), h.validar({"query": "agua"}))

    r = correr(prueba())
    assert isinstance(r, Resultado) and r.resumen == "2 resultados" and r.personas == set() and r.imagenes == []
    assert json.loads(r.texto_para_modelo())["results"][0]["title"] == "Acta inventada: agua"


def test_aprobacion_pendiente_con_enlace_absoluto():
    async def prueba():
        c, hs = await _herramientas(MnemoFalso())
        h = hs["mnemo_request_share"]
        return await h.ejecutar(_ctx(c), h.validar({"id": "doc_acta1", "with": "equipo@example.org"}))

    r = correr(prueba())
    assert r.resumen == "Aprobación pendiente en Mnemo"
    datos = json.loads(r.texto_para_modelo())
    assert datos["approval_url"] == f"{ORIGEN}/aprobar/apr_InventadoParaPruebas00"
    assert datos["status"] == "needs_approval" and datos["approval_id"] == "apr_InventadoParaPruebas00"


def test_imagen_como_bloque_base64():
    async def prueba():
        c, hs = await _herramientas(MnemoFalso())
        h = hs["mnemo_view_image"]
        return [await h.ejecutar(_ctx(c), h.validar({"id": i})) for i in (
            "doc_png", "doc_jpeg_como_png", "doc_enorme", "doc_gigante", "doc_basura", "doc_mal_b64")]

    png, jpeg, enorme, gigante, basura, mal = correr(prueba())
    assert png.imagenes == [{"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                         "data": b64(PNG_1x1)}}]
    assert png.resumen == "Imagen de Mnemo" and png.texto_para_modelo().endswith("[Imagen adjunta]")
    # El tipo sale de la firma de los bytes: la API rechaza un `media_type` que no coincide
    assert jpeg.imagenes[0]["source"] == {"type": "base64", "media_type": "image/jpeg", "data": b64(JPEG_2x3)}
    for r, motivo in ((enorme, "demasiado pesada"), (gigante, "8000 píxeles"), (basura, "formato"),
                      (mal, "bien codificada")):
        assert r.imagenes == [] and motivo in r.texto_para_modelo() and "[No se adjuntó" in r.texto_para_modelo()


def test_resource_link_como_texto_y_url_absoluta():
    async def prueba():
        c, hs = await _herramientas(MnemoFalso())
        h = hs["mnemo_export_document"]
        return await h.ejecutar(_ctx(c), h.validar({"document_id": "canvas_1"}))

    t = correr(prueba()).texto_para_modelo()
    datos = json.loads(t.split("\n", 1)[0])
    assert datos["url"] == f"{ORIGEN}/api/agent-exports/tokInventado"
    assert (f"Enlace: acta.pdf (application/pdf): {ORIGEN}/api/agent-exports/tokInventado — Signed download link"
            in t)
    assert "javascript:" not in t and "Se omitió un enlace" in t


def test_texto_largo_se_recorta_sin_romper_la_estructura():
    async def prueba():
        c, hs = await _herramientas(MnemoFalso())
        h = hs["mnemo_fetch"]
        return await h.ejecutar(_ctx(c), h.validar({"id": "doc_largo"}))

    t = correr(prueba()).texto_para_modelo()
    assert len(t) <= MAX_CONTENIDO
    datos = json.loads(t)  # sigue siendo JSON: el recorte fue dentro del texto
    assert datos["metadata"]["next_offset"] == 90000 and "[recortado: 96000 caracteres en total]" in datos["text"]


def test_escritura_cortada_avisa_que_pudo_hacerse(monkeypatch):
    falso = MnemoFalso()

    async def lento(a):
        await asyncio.sleep(3)
        return {"content": []}

    falso.manejadores["mnemo_create_event"] = lento
    monkeypatch.setattr(mc, "PLAZO_ESCRITURA_S", 0.2)

    async def prueba():
        c, hs = await _herramientas(falso)
        h = hs["mnemo_create_event"]
        return await _fallo(h.ejecutar(_ctx(c), h.validar({"title": "x", "start": "2026-11-09"})))

    e = correr(prueba())
    assert e.codigo == mc.COD_PLAZO and "No se sabe si alcanzó a hacerse en Mnemo" in e.mensaje


def test_sin_cliente_de_mnemo_en_el_turno():
    _, hs = correr(_herramientas(MnemoFalso()))
    for h, args in ((hs["mnemo_search"], {"query": "x"}), (hs["mnemo_create_event"], {"title": "x"})):
        e = correr(_fallo(h.ejecutar(_ctx(None), h.validar(args))))
        assert e.codigo == mc.COD_NO_DISPONIBLE
    e = correr(_fallo(hs["mnemo_create_event"].confirmar(_ctx(None), hs["mnemo_create_event"].validar({}))))
    assert e.codigo == mc.COD_NO_DISPONIBLE


def test_resultado_en_texto_plano_y_contenido_desconocido():
    r = mnemo.resultado_de({"content": [
        {"type": "text", "text": 'Aprobar en /aprobar/apr_abc123 o {"approval_url": "/aprobar/apr_x"}'},
        {"type": "audio", "data": "AAAA", "mimeType": "audio/wav"},
        {"type": "resource", "resource": {"uri": "mnemo://documents/1", "text": "Texto embebido"}}]}, ORIGEN)
    t = r.texto_para_modelo()
    assert f"{ORIGEN}/aprobar/apr_abc123" in t and f'"approval_url": "{ORIGEN}/aprobar/apr_x"' in t
    assert "Texto embebido" in t and "[Se omitió contenido de tipo audio]" in t and r.resumen == "Respuesta de Mnemo"
    assert mnemo.resultado_de({"content": []}, None).texto_para_modelo() == "(Mnemo no devolvió texto)"
    # Sin origen conocido los enlaces quedan como vienen
    assert mnemo.resultado_de({"structuredContent": {"approval_url": "/aprobar/apr_1"}}, None).texto_para_modelo() \
        == '{"approval_url": "/aprobar/apr_1"}'
    # Una URL relativa a otro host («//») no se toca
    assert "//otro" in mnemo.resultado_de({"structuredContent": {"url": "//otro/x"}}, ORIGEN).texto_para_modelo()


@pytest.mark.parametrize("estado, resumen", [
    ("needs_approval", "Aprobación pendiente en Mnemo"), ("pending", "Aprobación pendiente en Mnemo"),
    ("approved", "Aprobada en Mnemo"), ("rejected", "Rechazada en Mnemo"), ("expired", "La aprobación venció en Mnemo"),
    ("running", "Trabajo en curso en Mnemo"), ("done", "Hecho en Mnemo"), ("failed", "Falló en Mnemo"),
    ("interrupted", "Trabajo interrumpido en Mnemo"), ("raro", "Respuesta de Mnemo")])
def test_resumen_por_estado(estado, resumen):
    assert mnemo.resultado_de({"structuredContent": {"status": estado}}, ORIGEN).resumen == resumen


# ───────────────────────────── Un turno del asistente con Mnemo (núcleo + Mnemo) ─────────────────────────────

@pytest.fixture
def con_mnemo(sesion, monkeypatch):
    """El asistente encendido con Mnemo configurado y su cliente sobre el servidor falso; sin herramientas fijas (así
    se prueba solo lo de Mnemo, con el bucle de verdad)."""
    from ayudas_agente import con_herramientas
    falso = MnemoFalso()
    con_herramientas(monkeypatch, [])
    sesion.app.state.cfg = replace(sesion.app.state.cfg, mnemo_url=URL, mnemo_token=TOKEN)
    sesion.app.state.mnemo_cliente = mc.ClienteMnemo(URL, TOKEN, transporte=falso.transporte())
    return falso


def test_turno_con_una_lectura_de_mnemo(sesion, con_mnemo):
    from ayudas_agente import TU, T, encender, enviar, sse
    api = encender(sesion.app, sse(TU("toolu_m1", "mnemo_search", {"query": "acta"}), stop="tool_use"),
                   sse(T("Encontré el acta.")))
    r, ev = enviar(sesion, "Busca el acta en Mnemo")
    assert r.status_code == 200, r.text
    primera = api.peticiones[0]["json"]
    nombres = [t["name"] for t in primera["tools"]]
    assert nombres == [mnemo._nombre_panel(t["name"]) for t in con_mnemo.herramientas  # en el orden del servidor
                       if t["name"] in mnemo.POR_DEFECTO]
    assert "Mnemo: también tienes herramientas" in primera["system"][0]["text"]
    assert "Mnemo is the person's personal AI workspace" in primera["system"][0]["text"]
    h = [e for e in ev if e["tipo"] == "herramienta"]
    assert [(x["estado"], x["etiqueta"], x.get("resumen")) for x in h] == [
        ("inicio", "Buscando en Mnemo", None), ("ok", "Buscando en Mnemo", "2 resultados")]
    resultado = api.peticiones[1]["json"]["messages"][-1]["content"][0]
    assert resultado["type"] == "tool_result" and resultado["tool_use_id"] == "toolu_m1"
    assert "Acta inventada: acta" in json.dumps(resultado, ensure_ascii=False)
    assert con_mnemo.llamadas == [("search", {"query": "acta"})] and ev[-1]["motivo"] == "listo"
    assert SECRETO not in json.dumps(api.peticiones) and SECRETO not in r.text


def test_turno_con_una_escritura_de_mnemo_aprobada(sesion, con_mnemo):
    from ayudas_agente import TU, T, decidir, encender, enviar, sse
    api = encender(sesion.app, sse(TU("toolu_m2", "mnemo_request_share", {"id": "doc_acta1",
                                                                           "with": "equipo@example.org"}),
                                   stop="tool_use"),
                   sse(T("Pedí compartirla: apruébela en Mnemo.")))
    r, ev = enviar(sesion, "Comparte el acta con el equipo")
    assert r.status_code == 200, r.text
    conf = next(e for e in ev if e["tipo"] == "confirmar")
    assert conf["titulo"] == "Pedir en Mnemo que se comparta" and conf["etiqueta"] == "Pidiendo compartir en Mnemo"
    assert conf["detalle"] == [["id", "doc_acta1"], ["with", "equipo@example.org"]]
    assert ev[-1]["motivo"] == "confirmacion" and con_mnemo.llamadas == []  # nada se hizo todavía
    r, ev = decidir(sesion, ev[0]["conversacion"], toolu_m2=True)
    assert r.status_code == 200, r.text
    assert [(e["estado"], e.get("resumen")) for e in ev if e["tipo"] == "herramienta"] == [
        ("aprobada", None), ("ok", "Aprobación pendiente en Mnemo")]
    assert con_mnemo.llamadas == [("mnemo_request_share", {"id": "doc_acta1", "with": "equipo@example.org"})]
    resultado = json.dumps(api.peticiones[1]["json"]["messages"][-1]["content"][0], ensure_ascii=False)
    assert f"{ORIGEN}/aprobar/apr_InventadoParaPruebas00" in resultado and ev[-1]["motivo"] == "listo"


def test_estado_dice_si_mnemo_esta_activo_por_rol_y_ajuste(sesion, con_mnemo):
    from ayudas_g3 import coordinador
    assert sesion.get("/api/agente/estado").json()["mnemo"] == {"activo": True, "origen": ORIGEN}
    k = coordinador(sesion.app, sesion.app.state.db)
    assert k.get("/api/agente/estado").json()["mnemo"]["activo"] is False
    sesion.app.state.db.meta.update_one({"_id": "ajustes"}, {"$set": {"agente": {
        "roles": ["admin", "coordinador"], "escritura": True, "mnemo_coordinadores": True, "retencion_dias": 30}}},
        upsert=True)
    assert k.get("/api/agente/estado").json()["mnemo"]["activo"] is True


# ───────────────────────────── De punta a punta contra Mnemo real (opcional) ─────────────────────────────

GUION_MNEMO = """
import { createServer } from "node:http";
import { createTestApp } from "%(raiz)s/apps/api/test/helpers.ts";
import { createPat } from "%(raiz)s/apps/api/src/agent-api/pat.ts";
const t = await createTestApp();
const admin = await t.users.ensureAdmin();
const { secret } = await createPat(t.agentApi.grants, { userId: admin.id, name: "panel-e2e", scopes: ["mnemo:read",
  "mnemo:study.write", "mnemo:memory.write", "mnemo:workspace.write", "mnemo:business.write", "mnemo:forms.responses",
  "mnemo:share", "mnemo:publish", "mnemo:delete"] });
const srv = createServer(t.app);
srv.listen(0, "127.0.0.1", () => console.log("LISTO http://127.0.0.1:" + srv.address().port + "/mcp " + secret));
"""


@pytest.fixture
def mnemo_real(tmp_path):
    """Mnemo de verdad, en memoria (`createTestApp` de sus pruebas: repositorios en memoria y un modelo de guion),
    servido en un puerto libre de 127.0.0.1 con un token personal recién creado. Necesita `MNEMO_E2E_DIR`: un checkout
    de Mnemo con `npm ci` y `npm run build:shared` hechos (no se toca el repositorio original). Corre en su propio grupo
    de procesos (npx → tsx → node) para poder apagarlo entero."""
    import queue
    import signal
    import threading
    raiz = os.environ.get("MNEMO_E2E_DIR", "")
    npx = shutil.which("npx")
    if not raiz or not os.path.isdir(os.path.join(raiz, "node_modules")) or not npx:
        pytest.skip("Sin MNEMO_E2E_DIR (un checkout de Mnemo con node_modules) o sin npx")
    guion = tmp_path / "mnemo_e2e.mts"
    guion.write_text(GUION_MNEMO % {"raiz": raiz.rstrip("/")}, encoding="utf-8")
    proc = subprocess.Popen([npx, "tsx", str(guion)], cwd=os.path.join(raiz, "apps", "api"), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, env={**os.environ, "NODE_ENV": "test"},
                            start_new_session=True)
    lineas: queue.Queue = queue.Queue()
    threading.Thread(target=lambda: [lineas.put(x) for x in proc.stdout], daemon=True).start()
    try:
        limite, linea = time.monotonic() + 120, ""
        while time.monotonic() < limite and not linea.startswith("LISTO "):
            try:
                linea = lineas.get(timeout=1)
            except queue.Empty:
                if proc.poll() is not None:
                    break
        if not linea.startswith("LISTO "):
            pytest.skip("Mnemo no arrancó en local")
        _, url, token = linea.split()
        yield url, token
    finally:
        for senal in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(proc.pid, senal)
                proc.wait(10)
                break
            except (ProcessLookupError, subprocess.TimeoutExpired):
                continue


def test_punta_a_punta_con_mnemo_real(mnemo_real):
    """Contra el `/mcp` de Mnemo de verdad: inicio, catálogo, lista blanca, lecturas, una escritura, el pedido de
    borrarla (aprobación en Mnemo, con su enlace vuelto absoluto) y los errores de Mnemo y del SDK."""
    url, token = mnemo_real
    cfg = _cfg(mnemo_url=url, mnemo_token=token)
    origen = url.rsplit("/mcp", 1)[0]

    async def prueba():
        c = mc.ClienteMnemo(url, token, transporte=httpx2.AsyncHTTPTransport())
        todas = await c.herramientas()
        defs = await mnemo.definiciones(c, "")
        hs = {h.nombre: h for h in mnemo.desde_definiciones(await mnemo.definiciones(c, "*"))}
        ctx = _ctx(c, cfg)

        async def usar(nombre, args):
            return await hs[nombre].ejecutar(ctx, hs[nombre].validar(args))

        out = {"briefing": await usar("mnemo_get_briefing", {}),
               "evento": await usar("mnemo_create_event", {"events": [{"title": "Reunión inventada de prueba",
                                                                       "start": "2026-11-10T09:00:00-05:00"}]})}
        evento = json.loads(out["evento"].texto_para_modelo())["created"][0]["id"]
        out["tarjeta"] = await hs["mnemo_request_delete"].confirmar(ctx, hs["mnemo_request_delete"].validar(
            {"ids": [evento]}))
        out["borrar"] = await usar("mnemo_request_delete", {"ids": [evento], "note": "Prueba inventada"})
        out["eventos"] = await usar("mnemo_list_events", {})
        out["no"] = await _fallo(usar("mnemo_fetch", {"id": "doc_000000000000000000000000"}))
        out["invalido"] = await _fallo(usar("mnemo_fetch", {"id": 7}))
        out["inexistente"] = await _fallo(c.llamar("mnemo_no_existe", {}))
        await c.cerrar()
        return c, todas, defs, hs, out

    c, todas, defs, hs, out = correr(prueba())
    assert c.servidor.get("name") == "mnemo" and c.version == "2025-11-25" and "mnemo_get_briefing" in c.instrucciones
    assert len(todas) == 30 and len(hs) == 30
    assert [d["name"] for d in defs] == [t["name"] for t in todas if t["name"] in mnemo.POR_DEFECTO]
    assert len(defs) == len(mnemo.POR_DEFECTO)  # todas las de la lista blanca existen en Mnemo
    json.dumps([h.definicion() for h in hs.values()])
    assert all(re.fullmatch(r"mnemo_[A-Za-z0-9_-]{1,58}", n) for n in hs)
    assert all("$schema" not in h.definicion()["input_schema"] for h in hs.values())
    assert hs["mnemo_search"].tipo == "lectura" and hs["mnemo_fetch"].tipo == "lectura"
    assert {hs[n].tipo for n in ("mnemo_create_event", "mnemo_request_delete", "mnemo_save_memory")} == {"escritura"}
    assert out["evento"].resumen == "Creado en Mnemo"
    assert out["tarjeta"].titulo == "Pedir en Mnemo que se borre" and "Aquí solo se pide" in out["tarjeta"].aviso
    borrar = json.loads(out["borrar"].texto_para_modelo())
    assert out["borrar"].resumen == "Aprobación pendiente en Mnemo" and borrar["status"] == "needs_approval"
    assert borrar["approval_url"].startswith(f"{origen}/aprobar/apr_")  # sin PUBLIC_BASE_URL Mnemo la da relativa
    assert "Reunión inventada de prueba" in out["eventos"].texto_para_modelo()
    assert out["no"].codigo == "mnemo" and out["no"].detalle["code"] == "NOT_FOUND"
    assert out["invalido"].codigo == "mnemo" and "Input validation error" in out["invalido"].mensaje
    assert out["inexistente"].codigo == mc.COD_NO_DISPONIBLE
