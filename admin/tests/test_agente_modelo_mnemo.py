"""El modelo del asistente puesto por Mnemo (`app/agente/modelo_mnemo.py` y `proveedores.py`), de punta a punta por la
API: la conexión OAuth falsa con `mnemo:model` y `mnemo_model_complete` guionizada (`ayudas_agente.encender_mnemo` y
`R`). Nunca se llama a Mnemo ni a Anthropic de verdad; solo datos inventados.

Qué se prueba: la forma de lo que se manda (`system` y herramientas sin `eager_input_streaming`, las imágenes fuera del
`tool_result`, sin los bloques que Mnemo no conoce, el esfuerzo y `MNEMO_MODELO`), el texto en vivo por avance y
`texto_ronda` cuando no coincide, las herramientas del panel y las confirmaciones con Mnemo como modelo, los ids de
`tool_use` repetidos (entre rondas o en la misma respuesta), los cortes (`other` y `max_tokens`), los créditos en el
uso, el razonamiento reenviado tal cual y no mostrado, el tope de 4 MB, los reintentos (con un reloj falso: nadie
espera de verdad; `UNAVAILABLE` una vez), la renovación tras un 401, cada código de fin (el plan sin el modelo de
frontera elegido, aparte), una conexión alterada a mitad, el proveedor congelado en la conversación (409
`proveedor`), Mnemo antes que `ANTHROPIC_API_KEY` y el estado."""
import asyncio
import json
import time
from dataclasses import replace
from types import SimpleNamespace

import httpx2
import pytest

from ayudas_agente import (TH, TU, R, T, con_herramientas, conectar_mnemo, decidir, encender, encender_mnemo, enviar,
                           herramientas_falsas, sse, texto_de, tipos)
from ayudas_g3 import coordinador, persona
from ayudas_mcp import correcto, fallo
from ayudas_mcp import texto as texto_mcp

from app.agente import bucle, mnemo_conexion, modelo_mnemo, proveedores
from app.agente import conversaciones as conv_db
from app.agente import mnemo_cliente as mc
from app.agente.herramientas.base import ErrorHerramienta, Herramienta, Resultado

PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="


@pytest.fixture
def reloj(monkeypatch):
    """El reloj de los topes del turno, falso: `dormir` no espera, anota cuánto se pidió y adelanta el reloj."""
    r = {"ahora": 1_000.0, "esperas": []}

    async def dormir(segundos):
        r["esperas"].append(segundos)
        r["ahora"] += segundos

    monkeypatch.setattr(bucle, "ahora_s", lambda: r["ahora"])
    monkeypatch.setattr(bucle, "dormir", dormir)
    return r


@pytest.fixture
def falsas(monkeypatch, reloj):
    """El catálogo fijo del asistente con las herramientas inventadas, y el reloj falso."""
    lista, registro = herramientas_falsas()
    con_herramientas(monkeypatch, lista)
    return registro


def _herramienta_imagen(*datos: str) -> Herramienta:
    """`imagen_falsa` (lectura): devuelve `{"ok": true}` y una imagen PNG por cada texto base64 de `datos`."""
    from pydantic import BaseModel

    class Nada(BaseModel):
        pass

    async def ejecutar(ctx, a):
        return Resultado({"ok": True}, "Imágenes", imagenes=[
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": d}}
            for d in (datos or (PNG,))])
    return Herramienta("imagen_falsa", "Devuelve imágenes (prueba).", Nada, "lectura", ("personas.buscar",),
                       "Mirando una imagen", ejecutar)


def _conv(sesion, cid):
    return sesion.app.state.db[conv_db.CONVERSACIONES].find_one({"_id": cid})


def _mensajes(sesion, cid):
    return list(sesion.app.state.db[conv_db.MENSAJES].find({"conversacion": cid}).sort("seq", 1))


# ───────────────────────────── Un turno ─────────────────────────────

def test_un_turno_completo_con_el_modelo_de_mnemo(sesion, falsas):
    modelo = encender_mnemo(sesion.app,
                            R(T("Consulto la base."), TU("toolu_1", "contar_falsa", {"lugar": "Casco"}),
                              stop="tool_use"),
                            R(T("En el casco hay 3 personas.")))
    r, ev = enviar(sesion, "¿Cuántas personas hay en el casco?")
    assert r.status_code == 200, r.text
    assert tipos(ev) == ["inicio", "texto", "herramienta", "herramienta", "accion", "texto", "fin"]
    assert texto_de(ev) == "Consulto la base.En el casco hay 3 personas."
    h = [e for e in ev if e["tipo"] == "herramienta"]
    assert h[0] == {"tipo": "herramienta", "id": "toolu_1", "nombre": "contar_falsa", "etiqueta": "Contando personas",
                    "estado": "inicio"}
    assert h[1] == {**h[0], "estado": "ok", "resumen": "3 personas"}
    assert ev[-1] == {"tipo": "fin", "motivo": "listo", "limite": {"usados": 1, "maximo": 300}}
    cid = ev[0]["conversacion"]
    assert falsas == [("contar_falsa", {"lugar": "Casco", "persona_id": None}, cid, "toolu_1")]
    # La segunda ronda lleva el mensaje del asistente tal cual lo devolvió Mnemo y el resultado como texto
    segunda = modelo.pedidos[1]["messages"]
    assert [m["role"] for m in segunda] == ["user", "assistant", "user"]
    assert segunda[1]["content"] == [{"type": "text", "text": "Consulto la base."},
                                     {"type": "tool_use", "id": "toolu_1", "name": "contar_falsa",
                                      "input": {"lugar": "Casco"}}]
    assert segunda[2]["content"] == [{"type": "tool_result", "tool_use_id": "toolu_1",
                                      "content": json.dumps({"total": 3, "lugar": "Casco"}, ensure_ascii=False)}]
    c = _conv(sesion, cid)
    assert c["proveedor"] == "mnemo" and c["modelo"] == "principal"
    asistente = _mensajes(sesion, cid)[1]
    assert asistente["modelo"] == "proveedor-falso/modelo-inventado" and asistente["fin"] == "tool_use"
    assert len(modelo.tokens_de_avance()) == 2 and all(modelo.tokens_de_avance())  # cada ronda pidió avance


def test_lo_que_se_le_manda_a_mnemo(sesion, falsas, monkeypatch):
    lista, _ = herramientas_falsas()
    con_herramientas(monkeypatch, [*lista, _herramienta_imagen()])
    modelo = encender_mnemo(sesion.app, R(TU("toolu_i", "imagen_falsa", {}), stop="tool_use"), R(T("Es un punto.")))
    r, ev = enviar(sesion, "Muéstrame la foto", contexto={"ruta": "/personas/12", "vista": "personas"})
    assert r.status_code == 200 and ev[-1]["motivo"] == "listo", r.text
    conv = _conv(sesion, ev[0]["conversacion"])
    primera, segunda = modelo.pedidos
    assert primera["system"] == conv["sistema"] and "Trabajemos juntos" in primera["system"]
    assert primera["max_tokens"] == 16_000 and primera["reasoning"] == "medium"
    assert "model" not in primera and "tool_choice" not in primera and "temperature" not in primera
    nombres = [t["name"] for t in primera["tools"]]
    assert nombres[:4] == ["contar_falsa", "nota_falsa", "falla_falsa", "imagen_falsa"]
    assert "mnemo_search" in nombres and "mnemo_model_complete" not in nombres  # el modelo no es una herramienta
    assert all(set(t) == {"name", "description", "input_schema"} for t in primera["tools"])  # sin eager_input_streaming
    assert primera["tools"] == [{k: d[k] for k in ("name", "description", "input_schema")}
                                for d in json.loads(conv["herramientas"])]
    # El prefijo no cambia entre rondas (la caché del proveedor de la cuenta)
    assert segunda["system"] == primera["system"] and segunda["tools"] == primera["tools"]
    assert segunda["messages"][:1] == primera["messages"]
    usuario = primera["messages"][0]["content"]
    assert usuario[0]["text"].startswith("<contexto_del_panel>") and usuario[1] == {"type": "text",
                                                                                     "text": "Muéstrame la foto"}
    # La imagen va suelta después del tool_result, que queda como texto con una nota
    assert segunda["messages"][-1]["content"] == [
        {"type": "tool_result", "tool_use_id": "toolu_i",
         "content": '{"ok": true}\n[1 imagen(es) de este resultado van aparte, después de los resultados.]'},
        {"type": "image", "media_type": "image/png", "data": PNG}]
    # Lo guardado sigue en la forma del panel (la imagen dentro del resultado)
    guardado = json.loads(_mensajes(sesion, conv["_id"])[2]["contenido"])
    assert guardado[0]["content"][1] == {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                                     "data": PNG}}


@pytest.mark.parametrize("esfuerzo, mnemo_modelo, reasoning, model", [
    ("low", "", "low", None),
    ("medium", "principal", "medium", {"model": "principal"}),
    ("high", "ligero", "high", {"model": "ligero"}),
    ("xhigh", "proveedor-falso/modelo-inventado", "high", {"provider": "proveedor-falso", "model": "modelo-inventado"}),
    ("max", "enrutador-falso/familia/modelo-inventado", "high",
     {"provider": "enrutador-falso", "model": "familia/modelo-inventado"}),
])
def test_esfuerzo_equivalente_y_modelo_pedido(sesion, falsas, esfuerzo, mnemo_modelo, reasoning, model):
    sesion.app.state.cfg = replace(sesion.app.state.cfg, agente_esfuerzo=esfuerzo, mnemo_modelo=mnemo_modelo)
    modelo = encender_mnemo(sesion.app, R(T("Hola.")))
    _, ev = enviar(sesion, "Hola")
    assert ev[-1]["motivo"] == "listo"
    assert modelo.pedidos[0]["reasoning"] == reasoning and modelo.pedidos[0].get("model") == model
    assert _conv(sesion, ev[0]["conversacion"])["modelo"] == (mnemo_modelo or "principal")


def test_para_mnemo_quita_lo_que_mnemo_no_conoce_y_junta_los_mensajes():
    img = {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": PNG}}
    historial = [
        {"role": "user", "content": [{"type": "text", "text": "contexto"}, {"type": "text", "text": "Hola"}]},
        {"role": "assistant", "content": [
            {"type": "thinking", "thinking": "con otra forma", "signature": "s"},
            {"type": "thinking", "text": "de Mnemo", "signature": "firma-inventada"},
            {"type": "fallback", "from": {"model": "a"}, "to": {"model": "b"}},
            {"type": "server_tool_use", "id": "srv_1", "name": "web_search", "input": {}},
            {"type": "web_search_tool_result", "tool_use_id": "srv_1", "content": []},
            {"type": "redacted_thinking", "data": "x"},
            {"type": "text", "text": "Miro."},
            {"type": "tool_use", "id": "toolu_1", "name": "ver", "input": {"a": 1}}]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "toolu_1", "content": [
                {"type": "text", "text": '{"ok": true}'}, img,
                {"type": "image", "source": {"type": "url", "url": "https://mnemo.example.org/x.png"}}]},
            {"type": "text", "text": "contexto 2"}, {"type": "text", "text": "Sigue"}]},
        {"role": "assistant", "content": []},  # vacío (un modelo que no dijo nada): no viaja
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "toolu_2", "content": "x", "is_error": True}]},
    ]
    out = modelo_mnemo.para_mnemo(historial)
    assert [m["role"] for m in out] == ["user", "assistant", "user"]
    assert out[1]["content"] == [{"type": "thinking", "text": "de Mnemo", "signature": "firma-inventada"},
                                 {"type": "text", "text": "Miro."},
                                 {"type": "tool_use", "id": "toolu_1", "name": "ver", "input": {"a": 1}}]
    assert out[2]["content"] == [
        {"type": "tool_result", "tool_use_id": "toolu_1",
         "content": '{"ok": true}\n[2 imagen(es) de este resultado van aparte, después de los resultados.]'},
        {"type": "image", "media_type": "image/png", "data": PNG},
        {"type": "text", "text": modelo_mnemo.IMAGEN_ROTA},
        {"type": "text", "text": "contexto 2"}, {"type": "text", "text": "Sigue"},
        {"type": "tool_result", "tool_use_id": "toolu_2", "content": "x", "is_error": True}]
    assert historial[2]["content"][0]["content"][1] is img  # no toca el historial
    assert modelo_mnemo.para_mnemo(historial) == out  # una función pura: el prefijo es el mismo en cada ronda


def test_lo_que_devuelve_mnemo_se_guarda_en_una_forma_que_se_pueda_reenviar():
    out = modelo_mnemo.contenido_de([
        {"type": "text", "text": ""}, {"type": "text", "text": "Hola", "citations": []},
        {"type": "tool_use", "id": "toolu_1", "name": "contar_falsa", "input": {"lugar": "Casco"}},
        {"type": "tool_use", "id": "", "name": "no.vale/aqui", "input": "texto"},
        {"type": "thinking", "text": "x", "signature": ""},
        {"type": "image", "media_type": "image/png", "data": "x"}, "basura"])
    assert out[0] == {"type": "text", "text": "Hola"}
    assert out[1] == {"type": "tool_use", "id": "toolu_1", "name": "contar_falsa", "input": {"lugar": "Casco"}}
    assert out[2]["name"] == "no_vale_aqui" and out[2]["id"].startswith("toolu_mnemo_") and out[2]["input"] == {}
    assert out[3] == {"type": "thinking", "text": "x"} and len(out) == 4
    assert modelo_mnemo.uso_de({"input_tokens": 5, "output_tokens": True, "credits": float("nan")}) == proveedores.Uso(
        entrada=5)
    assert modelo_mnemo.modelo_de({"provider": "p", "model": "m"}) == "p/m" and modelo_mnemo.modelo_de(None) == "mnemo"
    assert modelo_mnemo.modelo_pedido("") is None and modelo_mnemo.modelo_pedido("ligero") == {"model": "ligero"}
    assert modelo_mnemo.modelo_pedido("sin-barra") is None


def test_ids_unicos_cambia_los_repetidos():
    historial = [{"role": "user", "content": "Hola"},
                 {"role": "assistant", "content": [{"type": "tool_use", "id": "call_0", "name": "x", "input": {}}]},
                 {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call_9", "content": "x"}]}]
    contenido = [{"type": "text", "text": "Miro."},
                 {"type": "tool_use", "id": "call_0", "name": "x", "input": {}},
                 {"type": "tool_use", "id": "call_1", "name": "x", "input": {}},
                 {"type": "tool_use", "id": "call_1", "name": "x", "input": {"b": 2}},
                 {"type": "tool_use", "id": "call_9", "name": "x", "input": {}}]
    assert modelo_mnemo.ids_usados(historial) == {"call_0", "call_9"}
    out = modelo_mnemo.ids_unicos(contenido, modelo_mnemo.ids_usados(historial))
    ids = [b["id"] for b in out if b["type"] == "tool_use"]
    assert ids[1] == "call_1" and len(set(ids)) == 4 and not {ids[0], ids[2], ids[3]} & {"call_0", "call_1", "call_9"}
    assert out[3]["input"] == {"b": 2} and out[0] == contenido[0]
    assert contenido[1]["id"] == "call_0" and contenido[3]["id"] == "call_1"  # no toca lo que recibe
    assert modelo_mnemo.ids_unicos(contenido[2:3], set()) == contenido[2:3]  # sin repetidos, tal cual
    # Un id que el widget recortaría (más de 100 caracteres) o con caracteres que la Messages API no acepta: uno nuevo
    largo, raro = "x" * 101, "call:0 a"
    for malo in (largo, raro):
        (b,) = modelo_mnemo.contenido_de([{"type": "tool_use", "id": malo, "name": "x", "input": {}}])
        assert b["id"] != malo and b["id"].startswith("toolu_mnemo_")
    (b,) = modelo_mnemo.contenido_de([{"type": "tool_use", "id": "y" * 100, "name": "x", "input": {}}])
    assert b["id"] == "y" * 100


# ───────────────────────────── El texto en vivo ─────────────────────────────

def test_el_texto_llega_por_avance(sesion, falsas):
    modelo = encender_mnemo(sesion.app, R(T("Hola, ya miro la base."), avance=["Hola, ", "ya miro ", "la base."]))
    _, ev = enviar(sesion, "Hola")
    assert [e["texto"] for e in ev if e["tipo"] == "texto"] == ["Hola, ", "ya miro ", "la base."]
    assert "texto_ronda" not in tipos(ev) and ev[-1]["motivo"] == "listo"
    assert modelo.tokens_de_avance()[0]


def test_texto_ronda_cuando_el_texto_final_no_coincide(sesion, falsas):
    encender_mnemo(sesion.app, R(T("En el casco hay 3 personas."), avance=["En el casco hay 4"]))
    _, ev = enviar(sesion, "¿Cuántas?")
    assert [(e["tipo"], e["texto"]) for e in ev if e["tipo"] in ("texto", "texto_ronda")] == [
        ("texto", "En el casco hay 4"), ("texto_ronda", "En el casco hay 3 personas.")]
    assert ev[-1]["motivo"] == "listo"
    vista = sesion.get(f"/api/agente/conversaciones/{ev[0]['conversacion']}").json()
    assert vista["mensajes"][1]["partes"] == [{"tipo": "texto", "texto": "En el casco hay 3 personas."}]
    assert vista["proveedor"] == "mnemo"


@pytest.mark.parametrize("avance, textos", [
    (["En el casco "], ["En el casco ", "hay 3 personas."]),  # solo falta el final: llega como texto
    ([], ["En el casco hay 3 personas."]),                     # sin avance: el texto entero al llegar el resultado
])
def test_lo_que_falta_del_texto_llega_como_texto(sesion, falsas, avance, textos):
    encender_mnemo(sesion.app, R(T("En el casco hay 3 personas."), avance=avance))
    _, ev = enviar(sesion, "¿Cuántas?")
    assert [e["texto"] for e in ev if e["tipo"] == "texto"] == textos and "texto_ronda" not in tipos(ev)


def test_cada_trozo_sale_en_cuanto_llega(cliente):
    """Con un Mnemo que manda el SSE de a poco (un transporte propio: por ASGI el cuerpo llega de una vez), cada trozo
    sale como evento antes de que termine la llamada."""
    app = cliente.app
    conectar_mnemo(app)
    pausa = 0.3

    def atender(req: httpx2.Request) -> httpx2.Response:
        cuerpo = json.loads(req.content)
        if "id" not in cuerpo:
            return httpx2.Response(202)
        if cuerpo["method"] == "initialize":
            return httpx2.Response(200, json={"jsonrpc": "2.0", "id": cuerpo["id"], "result": {
                "protocolVersion": "2025-11-25", "capabilities": {}}})
        token = cuerpo["params"]["_meta"]["progressToken"]

        async def flujo():
            for i, trozo in enumerate(["Hola, ", "ya miro ", "la base."], 1):
                await asyncio.sleep(pausa)
                aviso = {"jsonrpc": "2.0", "method": "notifications/progress",
                         "params": {"progressToken": token, "progress": i, "message": trozo}}
                yield f"event: message\ndata: {json.dumps(aviso)}\n\n".encode()
            await asyncio.sleep(pausa)
            res = {"jsonrpc": "2.0", "id": cuerpo["id"], "result": {"content": [], "structuredContent": {
                "content": [{"type": "text", "text": "Hola, ya miro la base."}], "stop_reason": "end_turn",
                "model": {}}}}
            yield f"event: message\ndata: {json.dumps(res)}\n\n".encode()
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=flujo())

    app.state.mnemo_transporte = httpx2.MockTransport(atender)
    eventos: list = []

    async def prueba():
        t0 = time.monotonic()
        r = await modelo_mnemo.ProveedorMnemo(app, app.state.cfg).generar(
            "Sistema inventado.", [{"role": "user", "content": [{"type": "text", "text": "Hola"}]}], [],
            max_tokens=100, esfuerzo="medium", al_evento=lambda ev: eventos.append((time.monotonic() - t0, ev)))
        return r, time.monotonic() - t0

    r, total = asyncio.run(prueba())
    assert [ev for _, ev in eventos] == [{"tipo": "texto", "texto": t} for t in ("Hola, ", "ya miro ", "la base.")]
    tiempos = [t for t, _ in eventos]
    assert tiempos[0] < total - 2 * pausa and all(b - a > pausa / 2 for a, b in zip(tiempos, tiempos[1:]))
    assert r.contenido == [{"type": "text", "text": "Hola, ya miro la base."}] and r.fin == "end_turn"


def test_si_el_turno_se_corta_la_llamada_a_mnemo_tambien(cliente):
    """El navegador se fue a mitad de una ronda (el turno se cancela): la llamada a Mnemo se corta, y Mnemo cancela la
    del proveedor y devuelve los créditos que había apartado."""
    app = cliente.app

    async def lento(args, avisar):
        await asyncio.sleep(30)
        return correcto(R(T("No debería llegar."))["datos"])

    modelo = encender_mnemo(app, lento)

    async def prueba():
        tarea = asyncio.ensure_future(modelo_mnemo.ProveedorMnemo(app, app.state.cfg).generar(
            "Sistema inventado.", [{"role": "user", "content": [{"type": "text", "text": "Hola"}]}], [],
            max_tokens=100, esfuerzo="medium", al_evento=lambda ev: None))
        while not modelo.pedidos:
            await asyncio.sleep(0.02)
        tarea.cancel()
        with pytest.raises(asyncio.CancelledError):
            await tarea

    asyncio.run(asyncio.wait_for(prueba(), 10))
    assert modelo.mcp.cancelaciones == 1 and len(modelo.pedidos) == 1


# ───────────────────────────── Herramientas y confirmaciones ─────────────────────────────

def test_una_escritura_con_mnemo_espera_la_aprobacion(sesion, falsas):
    db = sesion.app.state.db
    pid = persona(db, nombre="ANA INVENTADA DE PRUEBA", consentimiento="si")
    modelo = encender_mnemo(sesion.app,
                            R(T("Propongo la nota."), TU("toolu_n", "nota_falsa", {"persona_id": pid,
                                                                                   "texto": "Llamar el lunes"}),
                              stop="tool_use"),
                            R(T("Listo, quedó la nota.")))
    _, ev = enviar(sesion, "Agrega una nota")
    cid = ev[0]["conversacion"]
    assert ev[-1]["motivo"] == "confirmacion" and falsas == [] and len(modelo.pedidos) == 1
    assert next(e for e in ev if e["tipo"] == "confirmar")["detalle"] == [["Persona", f"#{pid}"],
                                                                          ["Nota", "Llamar el lunes"]]
    r, ev = decidir(sesion, cid, toolu_n=True)
    assert r.status_code == 200, r.text
    assert [(e["estado"], e.get("resumen")) for e in ev if e["tipo"] == "herramienta"] == [
        ("aprobada", None), ("ok", "Nota guardada")]
    assert texto_de(ev) == "Listo, quedó la nota." and ev[-1]["motivo"] == "listo"
    assert len(db.personas.find_one({"_id": pid})["notas"]) == 1
    assert modelo.pedidos[1]["messages"][-1]["content"] == [
        {"type": "tool_result", "tool_use_id": "toolu_n", "content": json.dumps({"ok": True})}]


def test_un_id_repetido_entre_rondas_se_cambia_y_su_aprobacion_llega(sesion, falsas):
    """Sin ids del proveedor de la cuenta, Mnemo numera las llamadas en cada respuesta (`call_0`…). La segunda escritura
    traería el mismo id que la primera: el widget (que pinta la conversación por id) no le mostraría la tarjeta de
    aprobación y la clave de idempotencia de la nota sería la misma. Recibe un id nuevo antes de anunciarse y de
    guardarse, y todo sigue con ese id."""
    db = sesion.app.state.db
    pid = persona(db, nombre="ANA INVENTADA DE PRUEBA", consentimiento="si")
    modelo = encender_mnemo(sesion.app,
                            R(TU("call_0", "nota_falsa", {"persona_id": pid, "texto": "Primera"}), stop="tool_use"),
                            R(T("Listo.")),
                            R(TU("call_0", "nota_falsa", {"persona_id": pid, "texto": "Segunda"}), stop="tool_use"),
                            R(T("Listo otra vez.")))
    _, ev = enviar(sesion, "Agrega una nota")
    cid = ev[0]["conversacion"]
    assert [e["id"] for e in ev if e["tipo"] == "confirmar"] == ["call_0"]  # el primero queda tal cual
    _, ev = decidir(sesion, cid, call_0=True)
    assert ev[-1]["motivo"] == "listo"
    _, ev = enviar(sesion, "Agrega otra nota", conversacion=cid)
    (confirmar,) = [e for e in ev if e["tipo"] == "confirmar"]
    nuevo = confirmar["id"]
    assert nuevo != "call_0" and nuevo.startswith("toolu_mnemo_") and ev[-1]["motivo"] == "confirmacion"
    assert {e["id"] for e in ev if "id" in e} == {nuevo}  # la herramienta y su tarjeta, con el id nuevo
    _, ev = decidir(sesion, cid, **{nuevo: True})
    assert ev[-1]["motivo"] == "listo" and texto_de(ev) == "Listo otra vez."
    assert [n["texto"] for n in db.personas.find_one({"_id": pid})["notas"]] == ["Primera", "Segunda"]
    # Lo que vuelve a Mnemo: cada tool_use con su resultado, sin ids repetidos
    ultimo = modelo.pedidos[-1]["messages"]
    usos = [b["id"] for m in ultimo for b in m["content"] if b["type"] == "tool_use"]
    resultados = [b["tool_use_id"] for m in ultimo for b in m["content"] if b["type"] == "tool_result"]
    assert usos == resultados == ["call_0", nuevo]


def test_un_id_repetido_en_la_misma_respuesta_se_cambia(sesion, falsas):
    modelo = encender_mnemo(sesion.app,
                            R(TU("call_0", "contar_falsa", {"lugar": "Casco"}),
                              TU("call_0", "contar_falsa", {"lugar": "Tigre"}), stop="tool_use"),
                            R(T("Hay 3 en cada uno.")))
    _, ev = enviar(sesion, "¿Cuántas hay en el casco y en el Tigre?")
    assert ev[-1]["motivo"] == "listo"
    ids = [e["id"] for e in ev if e["tipo"] == "herramienta" and e["estado"] == "inicio"]
    assert ids[0] == "call_0" and len(set(ids)) == 2
    assert [(f[1]["lugar"], f[3]) for f in falsas] == [("Casco", ids[0]), ("Tigre", ids[1])]  # corren las dos
    segunda = modelo.pedidos[1]["messages"]
    assert [b["id"] for b in segunda[1]["content"] if b["type"] == "tool_use"] == ids
    assert [b["tool_use_id"] for b in segunda[2]["content"]] == ids


def test_el_coordinador_usa_los_modelos_de_la_cuenta_conectada(sesion, falsas):
    modelo = encender_mnemo(sesion.app, R(T("Hola, coordinador.")))
    k = coordinador(sesion.app, sesion.app.state.db)
    r, ev = enviar(k, "Hola")
    assert r.status_code == 200 and texto_de(ev) == "Hola, coordinador." and ev[-1]["motivo"] == "listo"
    # Las herramientas de Mnemo no son suyas (salvo que el administrador lo permita); el modelo sí
    assert [t["name"] for t in modelo.pedidos[0]["tools"]] == ["contar_falsa", "nota_falsa", "falla_falsa"]
    assert "(coordinador)" in modelo.pedidos[0]["system"]


def test_el_tope_de_imagenes_de_una_ronda_es_el_de_mnemo(sesion, falsas, monkeypatch):
    monkeypatch.setattr(modelo_mnemo.ProveedorMnemo, "tope_imagenes", 3_000)
    lista, _ = herramientas_falsas()
    con_herramientas(monkeypatch, [*lista, _herramienta_imagen("A" * 2_000, "A" * 2_000, "B" * 4_000)])
    modelo = encender_mnemo(sesion.app, R(TU("toolu_i", "imagen_falsa", {}), stop="tool_use"), R(T("Veo una.")))
    _, ev = enviar(sesion, "Muéstrame las fotos")
    assert ev[-1]["motivo"] == "listo"
    resultado = modelo.pedidos[1]["messages"][-1]["content"]
    assert [b["type"] for b in resultado] == ["tool_result", "image"]
    assert "[1 imagen(es) omitida(s): esta ronda ya llevaba demasiadas." in resultado[0]["content"]
    assert "[1 imagen(es) omitida(s): pesa(n) demasiado" in resultado[0]["content"]


# ───────────────────────────── Cómo termina una ronda ─────────────────────────────

@pytest.mark.parametrize("fin, guardado, aviso", [("max_tokens", "max_tokens", bucle.AVISO_CORTADA),
                                                  ("other", "other", bucle.AVISO_INCOMPLETA),
                                                  ("desconocido", "other", bucle.AVISO_INCOMPLETA)])
def test_other_y_max_tokens_cortan(sesion, falsas, fin, guardado, aviso):
    modelo = encender_mnemo(sesion.app, R(T("Una respuesta muy lar"), stop=fin))
    _, ev = enviar(sesion, "Hola")
    assert tipos(ev) == ["inicio", "texto", "aviso", "fin"] and ev[-1]["motivo"] == "listo"
    assert ev[-2] == {"tipo": "aviso", "texto": aviso, "nivel": "info"} and len(modelo.pedidos) == 1
    assert _mensajes(sesion, ev[0]["conversacion"])[1]["fin"] == guardado


@pytest.mark.parametrize("fin, motivo, resumen", [("max_tokens", bucle.CORTADA, "Entrada cortada"),
                                                  ("other", bucle.INCOMPLETA, "Respuesta incompleta")])
def test_una_herramienta_de_una_respuesta_cortada_no_se_ejecuta(sesion, falsas, fin, motivo, resumen):
    modelo = encender_mnemo(sesion.app, R(TU("toolu_c", "contar_falsa", {"_raw": '{"lugar": "Ca'}), stop=fin),
                            R(T("Reintento.")))
    _, ev = enviar(sesion, "Hola")
    assert falsas == [] and ev[-1]["motivo"] == "listo" and len(modelo.pedidos) == 2
    assert [(e["estado"], e.get("resumen")) for e in ev if e["tipo"] == "herramienta"] == [("inicio", None),
                                                                                          ("error", resumen)]
    assert modelo.pedidos[1]["messages"][-1]["content"] == [
        {"type": "tool_result", "tool_use_id": "toolu_c", "content": motivo, "is_error": True}]


def test_un_rechazo_del_modelo(sesion, falsas):
    encender_mnemo(sesion.app, R(T("Empiezo a "), stop="refusal"))
    _, ev = enviar(sesion, "Algo raro")
    assert tipos(ev) == ["inicio", "texto", "descartar", "aviso", "fin"] and ev[-1]["motivo"] == "rechazo"
    msgs = _mensajes(sesion, ev[0]["conversacion"])
    assert [(m["rol"], m["replay"]) for m in msgs] == [("user", True), ("assistant", False), ("aviso", False)]


def test_los_creditos_quedan_en_el_uso(sesion, falsas):
    encender_mnemo(sesion.app,
                   R(T("Uno."), uso={"input_tokens": 500, "output_tokens": 20, "cache_read_tokens": 100,
                                     "credits": 0.0125}),
                   R(T("Dos."), uso={"input_tokens": 50, "output_tokens": 10, "credits": 0.0025}),
                   R(T("Tres.")))  # sin `credits` (clave propia, cortesía o administración): no suma
    _, ev = enviar(sesion, "Primero")
    cid = ev[0]["conversacion"]
    enviar(sesion, "Segundo", conversacion=cid)
    enviar(sesion, "Tercero", conversacion=cid)
    msgs = _mensajes(sesion, cid)
    assert msgs[1]["uso"] == {"entrada": 500, "salida": 20, "cache_lectura": 100, "cache_escritura": 0,
                              "creditos": 0.0125}
    assert msgs[3]["uso"]["creditos"] == 0.0025 and "creditos" not in msgs[5]["uso"]
    uso = sesion.app.state.db[conv_db.USO].find_one({"uid": 0})
    assert uso["mensajes"] == 3 and uso["entrada"] == 1450 and uso["salida"] == 80 and uso["cache_lectura"] == 100
    assert uso["creditos"] == pytest.approx(0.015)
    assert _conv(sesion, cid)["tokens_ultima"] == 900


def test_el_razonamiento_se_reenvia_tal_cual_y_no_se_muestra(sesion, falsas):
    modelo = encender_mnemo(sesion.app,
                            R(TH("Pienso en el casco.", "firma-inventada-1"), T("Miro."),
                              TU("toolu_1", "contar_falsa", {"lugar": "Casco"}), stop="tool_use"),
                            R(TH("", "firma-inventada-2"), T("Hay 3.")), R(T("En el Tigre no sé.")))
    _, ev = enviar(sesion, "¿Cuántas hay en el casco?")
    assert "progreso" not in tipos(ev) and ev[-1]["motivo"] == "listo"
    cid = ev[0]["conversacion"]
    assert modelo.pedidos[1]["messages"][1]["content"][0] == {"type": "thinking", "text": "Pienso en el casco.",
                                                              "signature": "firma-inventada-1"}
    _, ev = enviar(sesion, "¿Y en el Tigre?", conversacion=cid)
    assert modelo.pedidos[2]["messages"][3]["content"] == [
        {"type": "thinking", "text": "", "signature": "firma-inventada-2"}, {"type": "text", "text": "Hay 3."}]
    vista = sesion.get(f"/api/agente/conversaciones/{cid}").json()
    assert all(p["tipo"] != "progreso" for m in vista["mensajes"] if m["rol"] == "asistente" for p in m["partes"])


def test_para_interfaz_muestra_el_razonamiento_solo_en_las_de_anthropic():
    docs = [{"rol": "user", "texto": "Hola"},
            {"rol": "assistant", "replay": True, "contenido": json.dumps([
                {"type": "thinking", "thinking": "Reviso la base.", "signature": "s"},
                {"type": "thinking", "text": "Resumen del modelo.", "signature": "s"},
                {"type": "text", "text": "Listo."}])}]
    anthropic = conv_db.para_interfaz({"_id": 1}, docs, {})  # sin el campo: de antes de Mnemo, de Anthropic
    mnemo = conv_db.para_interfaz({"_id": 2, "proveedor": "mnemo"}, docs, {})
    assert anthropic["proveedor"] == "anthropic" and anthropic["mensajes"][1]["partes"] == [
        {"tipo": "progreso", "texto": "Reviso la base."}, {"tipo": "texto", "texto": "Listo."}]
    assert mnemo["proveedor"] == "mnemo" and mnemo["mensajes"][1]["partes"] == [{"tipo": "texto", "texto": "Listo."}]


# ───────────────────────────── El tope de 4 MB ─────────────────────────────

def test_ajustar_cambia_las_imagenes_viejas_y_luego_es_larga():
    def img(c):
        return {"type": "image", "media_type": "image/png", "data": c * 10_000}
    args = {"system": "S", "messages": [
        {"role": "user", "content": [{"type": "text", "text": "a"}, img("A")]},
        {"role": "assistant", "content": [{"type": "text", "text": "b"}]},
        {"role": "user", "content": [img("B"), {"type": "text", "text": "c"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "d"}]},
        {"role": "user", "content": [img("C"), {"type": "text", "text": "e"}]}]}
    peso = modelo_mnemo._peso(args) + modelo_mnemo.MARGEN_SOBRE
    marcador = {"type": "text", "text": modelo_mnemo.MARCADOR_IMAGEN}
    assert modelo_mnemo.ajustar(args, tope=peso) is args  # cabe: tal cual
    una = modelo_mnemo.ajustar(args, tope=peso - 5_000)  # sobra una: la más vieja
    assert una["messages"][0]["content"][1] == marcador and una["messages"][2]["content"][0] == img("B")
    dos = modelo_mnemo.ajustar(args, tope=peso - 15_000)
    assert dos["messages"][2]["content"][0] == marcador and dos["messages"][4]["content"][0] == img("C")
    assert args["messages"][0]["content"][1] == img("A")  # no toca lo que recibe
    with pytest.raises(proveedores.ErrorProveedor) as e:  # la del último mensaje nunca se quita: no cabe
        modelo_mnemo.ajustar(args, tope=peso - 25_000)
    assert e.value.codigo == "larga"


def test_tope_de_4_mb_por_la_api(sesion, falsas, monkeypatch):
    lista, _ = herramientas_falsas()
    con_herramientas(monkeypatch, [*lista, _herramienta_imagen("A" * 50_000)])
    modelo = encender_mnemo(sesion.app, R(TU("toolu_i", "imagen_falsa", {}), stop="tool_use"), R(T("Es una foto.")),
                            R(T("Sigo sin la foto.")))
    _, ev = enviar(sesion, "Muéstrame la foto")
    cid = ev[0]["conversacion"]
    assert ev[-1]["motivo"] == "listo" and modelo.pedidos[1]["messages"][2]["content"][1]["type"] == "image"
    # El siguiente mensaje no cabe con la imagen vieja: va un aviso en su lugar
    monkeypatch.setattr(mc, "MAX_PETICION", modelo_mnemo._peso(modelo.pedidos[1]) + modelo_mnemo.MARGEN_SOBRE - 10_000)
    _, ev = enviar(sesion, "¿Y ahora?", conversacion=cid)
    assert ev[-1]["motivo"] == "listo" and texto_de(ev) == "Sigo sin la foto."
    assert modelo.pedidos[2]["messages"][2]["content"][1] == {"type": "text", "text": modelo_mnemo.MARCADOR_IMAGEN}
    # Y si ni así cabe, la conversación es larga (sin llamar a Mnemo)
    monkeypatch.setattr(mc, "MAX_PETICION", 1_000)
    _, ev = enviar(sesion, "¿Otra vez?", conversacion=cid)
    assert ev[-2] == {"tipo": "error", "codigo": "larga", "mensaje": modelo_mnemo.MENSAJE_LARGA}
    assert ev[-1]["motivo"] == "error" and len(modelo.pedidos) == 3


# ───────────────────────────── Reintentos ─────────────────────────────

RITMO = fallo("RATE_LIMITED", "Too many calls in the last minute for this connection. Wait a moment and try again.")


def test_rate_limited_espera_10_y_20_segundos(sesion, falsas, reloj):
    modelo = encender_mnemo(sesion.app, RITMO, RITMO, R(T("Ya está.")))
    _, ev = enviar(sesion, "Hola")
    assert reloj["esperas"] == [10.0, 20.0] and len(modelo.pedidos) == 3
    assert tipos(ev) == ["inicio", "descartar", "descartar", "texto", "fin"] and ev[-1]["motivo"] == "listo"
    assert [m["rol"] for m in _mensajes(sesion, ev[0]["conversacion"])] == ["user", "assistant"]


def test_rate_limited_que_no_cede_termina_con_llm_limite(sesion, falsas, reloj):
    proveedor = fallo("RATE_LIMITED", "The model provider is limiting the person's account.", {"reason": "provider"})
    modelo = encender_mnemo(sesion.app, proveedor, proveedor, proveedor)
    _, ev = enviar(sesion, "Hola")
    assert reloj["esperas"] == [10.0, 20.0] and len(modelo.pedidos) == 3
    assert ev[-2] == {"tipo": "error", "codigo": "llm_limite", "mensaje": modelo_mnemo.MENSAJE_LIMITE_PROVEEDOR}


def test_llamadas_a_la_vez_esperan_poco(sesion, falsas, reloj):
    a_la_vez = fallo("RATE_LIMITED", "This connection already has 4 model calls running.", {"reason": "concurrency"})
    encender_mnemo(sesion.app, a_la_vez, R(T("Ya.")))
    _, ev = enviar(sesion, "Hola")
    assert len(reloj["esperas"]) == 1 and 2.0 <= reloj["esperas"][0] <= 5.0 and ev[-1]["motivo"] == "listo"


def test_las_esperas_no_pasan_del_tope_del_turno(sesion, falsas, reloj, monkeypatch):
    monkeypatch.setattr(bucle, "TOPE_TURNO_S", 25)
    modelo = encender_mnemo(sesion.app, RITMO, RITMO, R(T("No llega.")))
    _, ev = enviar(sesion, "Hola")
    # 10 s caben en el turno; 10 + 20 ya no: termina con el error en vez de esperar
    assert reloj["esperas"] == [10.0] and len(modelo.pedidos) == 2
    assert ev[-2] == {"tipo": "error", "codigo": "llm_limite", "mensaje": modelo_mnemo.MENSAJE_LIMITE}


class _Fallos(httpx2.AsyncBaseTransport):
    """Delante del transporte del Mnemo falso: las primeras llamadas al modelo fallan como dice `fallos` (una excepción
    de red o un estado HTTP); lo demás pasa."""

    def __init__(self, transporte, *fallos):
        self.transporte, self.fallos = transporte, list(fallos)

    async def handle_async_request(self, req: httpx2.Request) -> httpx2.Response:
        cuerpo = json.loads(req.content) if req.url.path.endswith("/mcp") and req.content else None
        if isinstance(cuerpo, dict) and (cuerpo.get("params") or {}).get("name") == "mnemo_model_complete" \
                and self.fallos:
            f = self.fallos.pop(0)
            if isinstance(f, BaseException):
                raise f
            return httpx2.Response(f, json={"error": "inventado"})
        return await self.transporte.handle_async_request(req)


def test_un_corte_de_red_y_un_5xx_esperan_1_y_2_segundos(sesion, falsas, reloj):
    modelo = encender_mnemo(sesion.app, R(T("Ya está.")))
    sesion.app.state.mnemo_transporte = _Fallos(sesion.app.state.mnemo_transporte,
                                                httpx2.ConnectError("conexión rechazada (prueba)"), 503)
    _, ev = enviar(sesion, "Hola")
    assert reloj["esperas"] == [1.0, 2.0] and ev[-1]["motivo"] == "listo" and len(modelo.pedidos) == 1
    assert ev.count({"tipo": "descartar"}) == 2


def test_un_401_renueva_la_conexion_y_repite(sesion, falsas):
    modelo = encender_mnemo(sesion.app, R(T("Hola.")), R(T("Sigo aquí.")))
    _, ev = enviar(sesion, "Hola")
    cid = ev[0]["conversacion"]
    assert modelo.oauth.renovaciones == 0
    modelo.oauth.vencer_accesos()  # Mnemo deja de aceptar el access antes de que el panel lo dé por vencido
    _, ev = enviar(sesion, "¿Sigues?", conversacion=cid)
    assert ev[-1]["motivo"] == "listo" and texto_de(ev) == "Sigo aquí." and "descartar" not in tipos(ev)
    assert modelo.oauth.renovaciones == 1 and len(modelo.pedidos) == 2
    llamadas = [p for p in modelo.mcp.peticiones if (p["json"] or {}).get("method") == "tools/call"]
    assert llamadas[-2]["cabeceras"]["authorization"] != llamadas[-1]["cabeceras"]["authorization"]


def test_reintento_y_explicar_de_mnemo():
    p = modelo_mnemo.ProveedorMnemo(SimpleNamespace(), SimpleNamespace(mnemo_modelo=""))

    def de_mnemo(codigo=None, estado=None, detalles=None):
        detalle = {"code": codigo, **({"details": detalles} if detalles else {})} if codigo else None
        return ErrorHerramienta("x", mc.COD_MNEMO, estado=estado, detalle=detalle)

    assert p.reintento(ErrorHerramienta("x", mc.COD_RED), 0) == 1.0
    assert p.reintento(ErrorHerramienta("x", mc.COD_PLAZO), 1) == 2.0
    assert p.reintento(de_mnemo(estado=503), 0) == 1.0 and p.reintento(de_mnemo(estado=429), 1) == 20.0
    assert p.reintento(de_mnemo("RATE_LIMITED"), 0) == 10.0
    assert 2.0 <= p.reintento(de_mnemo("RATE_LIMITED", detalles={"reason": "concurrency"}), 1) <= 5.0
    assert p.reintento(ErrorHerramienta("x", mc.COD_TOKEN, detalle={"conexion": "cambio"}), 0) == 0.5
    # UNAVAILABLE (el proveedor de la cuenta falló, o no tiene modelo): una vez, tras 1 s
    assert p.reintento(de_mnemo("UNAVAILABLE"), 0) == 1.0 and p.reintento(de_mnemo("UNAVAILABLE"), 1) is None
    for e in (ErrorHerramienta("x", mc.COD_TOKEN, estado=401), ErrorHerramienta("x", mc.COD_TOKEN, detalle={
            "conexion": "revocada"}), ErrorHerramienta("x", mc.COD_TOKEN, detalle={"conexion": "alterada"}),
            ErrorHerramienta("x", mc.COD_NO_DISPONIBLE), de_mnemo("PLAN_REQUIRED"), de_mnemo("TIMEOUT"),
            de_mnemo(estado=404), de_mnemo(estado=413), ValueError("x"), proveedores.ErrorProveedor("x", "larga")):
        assert p.reintento(e, 0) is None, e
    assert p.explicar(de_mnemo("PLAN_REQUIRED", detalles={"feature": "chat"})) == (modelo_mnemo.MENSAJE_PLAN,
                                                                                    "mnemo_plan")
    assert p.explicar(de_mnemo("PLAN_REQUIRED", detalles={"feature": "frontier_models"})) == (
        modelo_mnemo.MENSAJE_PLAN_MODELO, "mnemo_plan")
    assert p.explicar(de_mnemo(estado=413)) == (modelo_mnemo.MENSAJE_LARGA, "larga")
    assert p.explicar(de_mnemo(estado=404))[1] == "mnemo_conexion" and p.explicar(de_mnemo(estado=302))[1] == (
        "mnemo_conexion")
    assert p.explicar(de_mnemo(estado=503)) == (modelo_mnemo.MENSAJE_NO_DISPONIBLE, "llm_no_disponible")
    assert p.explicar(de_mnemo(estado=429)) == (modelo_mnemo.MENSAJE_LIMITE, "llm_limite")
    assert p.explicar(ErrorHerramienta(mc.MENSAJE_TOKEN, mc.COD_TOKEN, estado=401)) == (mc.MENSAJE_TOKEN,
                                                                                         "mnemo_conexion")
    assert p.explicar(ErrorHerramienta("x", mc.COD_RED)) == (modelo_mnemo.MENSAJE_RED, "llm_conexion")
    assert p.explicar(ErrorHerramienta("x", mc.COD_PLAZO)) == (modelo_mnemo.MENSAJE_PLAZO, "llm_conexion")
    assert p.explicar(RuntimeError("datos de alguien")) == (modelo_mnemo.MENSAJE_ERROR, "error")


# ───────────────────────────── Códigos de fin ─────────────────────────────

@pytest.mark.parametrize("error, codigo, mensaje", [
    (fallo("PLAN_REQUIRED", "The person's Mnemo plan does not include using its models from here.",
           {"feature": "chat"}), "mnemo_plan", modelo_mnemo.MENSAJE_PLAN),
    # El modelo de frontera que eligió el panel (`MNEMO_MODELO`) no está en el plan: no es que no haya chat
    (fallo("PLAN_REQUIRED", "The person's Mnemo plan does not include frontier models.",
           {"feature": "frontier_models"}), "mnemo_plan", modelo_mnemo.MENSAJE_PLAN_MODELO),
    (fallo("CREDITS_EXHAUSTED", "The person has no Mnemo credits left this week.", {"reason": "credit"}),
     "mnemo_creditos", modelo_mnemo.MENSAJE_CREDITOS),
    (fallo("INVALID_ARGUMENT", "The conversation is longer than the model's context window.",
           {"reason": "context_window"}), "larga", modelo_mnemo.MENSAJE_LARGA),
    (fallo("INVALID_ARGUMENT", "x/y is not one of the person's models in Mnemo.",
           {"available": ["proveedor-falso/otro-modelo"]}), "mnemo_sin_modelo", modelo_mnemo.MENSAJE_MODELO_AJENO),
    (fallo("INVALID_ARGUMENT", "Invalid arguments: messages.0.content: Too big."), "llm_peticion",
     modelo_mnemo.MENSAJE_PETICION),
    (fallo("TIMEOUT", "The model did not answer in time."), "llm_no_disponible", modelo_mnemo.MENSAJE_PLAZO_MODELO),
    (fallo("INTERNAL", "Something went wrong in Mnemo while asking the model."), "llm_no_disponible",
     modelo_mnemo.MENSAJE_NO_DISPONIBLE),
    ({"content": [texto_mcp("una copia en texto, sin structuredContent")]}, "llm_respuesta",
     modelo_mnemo.MENSAJE_ILEGIBLE),
])
def test_cada_error_de_mnemo_tiene_su_codigo_de_fin(sesion, falsas, reloj, error, codigo, mensaje):
    modelo = encender_mnemo(sesion.app, error, R(T("No debería llegar.")))
    _, ev = enviar(sesion, "Hola")
    assert ev[-2] == {"tipo": "error", "codigo": codigo, "mensaje": mensaje} and ev[-1]["motivo"] == "error"
    assert len(modelo.pedidos) == 1 and reloj["esperas"] == []  # no se repite
    assert [m["rol"] for m in _mensajes(sesion, ev[0]["conversacion"])] == ["user"]
    assert "MNEMO_" not in mensaje and "ANTHROPIC" not in mensaje  # sin nombres de variables


def test_unavailable_a_mitad_se_repite_una_vez(sesion, falsas, reloj):
    """Mnemo da UNAVAILABLE también cuando el proveedor de la cuenta falló a mitad de la respuesta (después de sus
    propios reintentos): la ronda se repite una vez tras 1 s y lo que alcanzó a llegar se descarta."""
    async def a_medias(args, avisar):
        await avisar(1, "Estoy revisando la base y ")
        return fallo("UNAVAILABLE", "The model provider failed. Try again in a moment.")

    modelo = encender_mnemo(sesion.app, a_medias, R(T("En la base hay 3 personas.")))
    _, ev = enviar(sesion, "¿Cómo va la base?")
    assert tipos(ev) == ["inicio", "texto", "descartar", "texto", "fin"] and ev[-1]["motivo"] == "listo"
    assert reloj["esperas"] == [1.0] and len(modelo.pedidos) == 2
    assert texto_de(ev[ev.index({"tipo": "descartar"}):]) == "En la base hay 3 personas."


def test_unavailable_que_sigue_termina_con_mnemo_sin_modelo(sesion, falsas, reloj):
    """Si vuelve a fallar (la cuenta no tiene modelo: falla al instante y sin gastar), no se insiste."""
    sin_modelo = fallo("UNAVAILABLE", "The person's Mnemo has no usable model right now.")
    modelo = encender_mnemo(sesion.app, sin_modelo, sin_modelo, R(T("No debería llegar.")))
    _, ev = enviar(sesion, "Hola")
    assert ev[-2] == {"tipo": "error", "codigo": "mnemo_sin_modelo", "mensaje": modelo_mnemo.MENSAJE_SIN_MODELO}
    assert reloj["esperas"] == [1.0] and len(modelo.pedidos) == 2 and ev[-1]["motivo"] == "error"


def test_sin_la_herramienta_del_modelo_es_mnemo_sin_modelo(sesion, falsas):
    modelo = encender_mnemo(sesion.app)
    modelo.quitar()  # Mnemo ya no la ofrece con esta conexión (-32602)
    _, ev = enviar(sesion, "Hola")
    assert ev[-2] == {"tipo": "error", "codigo": "mnemo_sin_modelo", "mensaje": modelo_mnemo.MENSAJE_SIN_PERMISO}


def test_una_conexion_revocada_termina_con_mnemo_conexion(sesion, falsas):
    modelo = encender_mnemo(sesion.app, R(T("Hola.")))
    _, ev = enviar(sesion, "Hola")
    cid = ev[0]["conversacion"]
    for gid in list(modelo.oauth.concesiones):
        modelo.oauth.revocar_concesion(gid)  # el administrador la revocó en «Tu cuenta» de Mnemo
    _, ev = enviar(sesion, "¿Sigues?", conversacion=cid)
    assert ev[-2] == {"tipo": "error", "codigo": "mnemo_conexion", "mensaje": mc.MENSAJE_TOKEN}
    e = sesion.get("/api/agente/estado").json()
    assert e["mnemo"]["conexion"]["estado"] == "caida" and e["proveedor"] is None and e["motivo"] == "sin_configurar"


def test_la_conexion_se_cae_entre_dos_rondas(sesion, falsas):
    db = sesion.app.state.db

    async def y_se_cae(args, avisar):  # mientras responde, la conexión queda caída (cambió la clave del panel)
        db.meta.update_one({"_id": mnemo_conexion.ID}, {"$set": {"estado": "caida", "motivo": "clave"}})
        return correcto(R(TU("toolu_1", "contar_falsa", {"lugar": "Casco"}), stop="tool_use")["datos"])

    modelo = encender_mnemo(sesion.app, y_se_cae, R(T("No debería llegar.")))
    _, ev = enviar(sesion, "Hola")
    assert ev[-2] == {"tipo": "error", "codigo": "mnemo_conexion", "mensaje": mnemo_conexion.MENSAJE_CLAVE}
    assert len(modelo.pedidos) == 1 and len(falsas) == 1  # la herramienta de la primera ronda sí corrió


def test_una_conexion_alterada_a_mitad_no_manda_el_access(sesion, falsas):
    """Mientras responde, quien solo tiene la base cambia la dirección MCP: la ronda siguiente no sale (el access iría a
    otro host), la conexión cae («alterada») y el turno lo explica sin datos."""
    db = sesion.app.state.db

    async def y_la_cambian(args, avisar):
        db.meta.update_one({"_id": mnemo_conexion.ID}, {"$set": {"url_mcp": "https://atacante.example/mcp"}})
        return correcto(R(TU("toolu_1", "contar_falsa", {"lugar": "Casco"}), stop="tool_use")["datos"])

    modelo = encender_mnemo(sesion.app, y_la_cambian, R(T("No debería llegar.")))
    _, ev = enviar(sesion, "Hola")
    assert ev[-2] == {"tipo": "error", "codigo": "mnemo_conexion", "mensaje": mnemo_conexion.MENSAJE_ALTERADA}
    assert len(modelo.pedidos) == 1 and len(falsas) == 1
    llamadas = [p for p in modelo.mcp.peticiones if (p["json"] or {}).get("method") == "tools/call"]
    assert len(llamadas) == 1  # la segunda ronda no llegó a ninguna parte (el transporte falso no mira el host)
    e = sesion.get("/api/agente/estado").json()
    assert e["mnemo"]["conexion"]["estado"] == "caida" and e["mnemo"]["conexion"]["motivo"] == "alterada"


# ───────────────────────────── Qué proveedor rige ─────────────────────────────

def test_mnemo_va_antes_que_la_clave_de_anthropic(sesion, falsas):
    api = encender(sesion.app, sse(T("No debería.")))
    modelo = encender_mnemo(sesion.app, R(T("Respondo con Mnemo.")))
    e = sesion.get("/api/agente/estado").json()
    assert e["proveedor"] == "mnemo" and e["disponible"] is True and e["configurado"] is True
    _, ev = enviar(sesion, "Hola")
    assert texto_de(ev) == "Respondo con Mnemo." and api.peticiones == [] and len(modelo.pedidos) == 1


def test_el_estado_dice_que_proveedor_rige(sesion, falsas):
    e = sesion.get("/api/agente/estado").json()
    assert e["proveedor"] is None and e["motivo"] == "sin_configurar" and e["configurado"] is False
    # Mnemo conectado sin permiso para usar sus modelos no es un proveedor
    conectar_mnemo(sesion.app, alcances=["mnemo:read"])
    e = sesion.get("/api/agente/estado").json()
    assert e["proveedor"] is None and e["motivo"] == "sin_configurar" and e["mnemo"]["conexion"]["modelo"] is False
    r, _ = enviar(sesion, "Hola")
    assert r.status_code == 503 and r.json()["detail"]["codigo"] == "sin_configurar"
    encender_mnemo(sesion.app)  # se vuelve a conectar, ahora con mnemo:model
    e = sesion.get("/api/agente/estado").json()
    assert e["proveedor"] == "mnemo" and e["disponible"] is True
    k = coordinador(sesion.app, sesion.app.state.db)
    assert k.get("/api/agente/estado").json()["proveedor"] == "mnemo"  # lo ven todos


def test_una_conversacion_de_anthropic_sigue_con_anthropic(sesion, falsas):
    api = encender(sesion.app, sse(T("Hola desde Anthropic.")), sse(T("Sigo con Anthropic.")))
    _, ev = enviar(sesion, "Hola")
    vieja = ev[0]["conversacion"]
    assert _conv(sesion, vieja)["proveedor"] == "anthropic"
    modelo = encender_mnemo(sesion.app, R(T("Hola desde Mnemo.")))
    _, ev = enviar(sesion, "¿Sigues?", conversacion=vieja)
    assert texto_de(ev) == "Sigo con Anthropic." and len(api.peticiones) == 2 and modelo.pedidos == []
    _, ev = enviar(sesion, "Otra")  # una nueva va con Mnemo
    assert texto_de(ev) == "Hola desde Mnemo." and _conv(sesion, ev[0]["conversacion"])["proveedor"] == "mnemo"
    # Sin la clave de Anthropic, la vieja ya no puede seguir: 409 `proveedor` (el widget ofrece una nueva)
    sesion.app.state.cfg = replace(sesion.app.state.cfg, anthropic_api_key="")
    r, _ = enviar(sesion, "¿Y ahora?", conversacion=vieja)
    assert r.status_code == 409 and r.json()["detail"] == bucle.PROVEEDOR
    assert sesion.get(f"/api/agente/conversaciones/{vieja}").json()["proveedor"] == "anthropic"


def test_una_conversacion_de_mnemo_no_sigue_sin_mnemo(sesion, falsas):
    db = sesion.app.state.db
    pid = persona(db, nombre="BETO INVENTADO DE PRUEBA", consentimiento="si")
    encender_mnemo(sesion.app, R(T("Propongo la nota."), TU("toolu_n", "nota_falsa", {"persona_id": pid,
                                                                                       "texto": "Visitar"}),
                                 stop="tool_use"))
    _, ev = enviar(sesion, "Anota la visita")
    cid = ev[0]["conversacion"]
    assert ev[-1]["motivo"] == "confirmacion"
    # El administrador desconecta Mnemo y pone la clave de Anthropic: lo nuevo va con Anthropic, lo de Mnemo no sigue
    assert sesion.delete("/api/agente/mnemo").status_code == 200
    api = encender(sesion.app, sse(T("Hola desde Anthropic.")))
    r, _ = decidir(sesion, cid, toolu_n=True)
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "proveedor"
    assert not db.personas.find_one({"_id": pid}).get("notas")  # lo aprobado no se ejecutó
    r, _ = enviar(sesion, "Sigo", conversacion=cid)
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "proveedor"
    _, ev = enviar(sesion, "Una nueva")
    assert texto_de(ev) == "Hola desde Anthropic." and len(api.peticiones) == 1
    assert _conv(sesion, ev[0]["conversacion"])["proveedor"] == "anthropic"


def test_cerrar_cierra_los_clientes_de_los_dos_proveedores():
    cerrados = []

    class Cliente:
        def __init__(self, nombre):
            self.nombre = nombre

        async def close(self):
            cerrados.append(self.nombre)

        async def cerrar(self):
            cerrados.append(self.nombre)

    app = SimpleNamespace(state=SimpleNamespace(agente_cliente=Cliente("anthropic"), agente_cliente_propio=True,
                                                mnemo_cliente=Cliente("mnemo")))
    asyncio.run(proveedores.cerrar(app))
    assert cerrados == ["anthropic", "mnemo"] and app.state.agente_cliente is None
