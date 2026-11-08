"""El bucle del asistente (app/agente/bucle.py) de punta a punta por la API, con la Messages API simulada (el SDK de
verdad sobre un transporte falso: nunca se llama a Anthropic) y herramientas inventadas. Solo datos inventados.

Qué se prueba: la secuencia de eventos de un turno, lo que se le manda al modelo (betas, pensamiento, respaldo,
herramientas y `system` congelados, contexto del panel), lo que se guarda, las confirmaciones, los rechazos, los
reintentos, los topes y los errores. Las reglas sueltas (`reenviable`, `para_peticion`, `reintentable`, el contexto
del panel) tienen sus pruebas unitarias al final."""
import json
from datetime import datetime, timezone

import httpx2
import pytest

from ayudas_agente import (TH, TU, Corte, T, con_herramientas, decidir, encender, encender_lento, enviar,
                           herramientas_falsas, sse, texto_de, tipos)
from ayudas_g3 import persona

from app.agente import bucle, llm, sistema
from app.agente import conversaciones as conv_db

BETAS = "server-side-fallback-2026-07-01,thinking-display-updates-2026-08-18,thinking-binding-controls-2026-08-01"


async def _sin_espera(segundos):  # las rondas que fallan de paso se repiten sin esperar de verdad
    return None


@pytest.fixture
def falsas(monkeypatch):
    """El catálogo fijo del asistente con las herramientas inventadas; sin esperas entre reintentos."""
    lista, registro = herramientas_falsas()
    con_herramientas(monkeypatch, lista)
    monkeypatch.setattr(bucle, "dormir", _sin_espera)
    return registro


def _mensajes(sesion, cid):
    return list(sesion.app.state.db[conv_db.MENSAJES].find({"conversacion": cid}).sort("seq", 1))


def _conv(sesion, cid):
    return sesion.app.state.db[conv_db.CONVERSACIONES].find_one({"_id": cid})


# ───────────────────────────── Un turno ─────────────────────────────

def test_turno_con_progreso_texto_herramienta_y_respuesta(sesion, falsas):
    api = encender(sesion.app,
                   sse(TH("Busco en la base."), T("Consulto la base."), TU("toolu_1", "contar_falsa", {"lugar": "Casco"}),
                       stop="tool_use"),
                   sse(T("En el casco hay 3 personas.")))
    r, ev = enviar(sesion, "¿Cuántas personas hay en el casco?")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/x-ndjson")
    assert tipos(ev) == ["inicio", "progreso", "texto", "herramienta", "herramienta", "accion", "texto", "fin"]
    assert ev[0] == {"tipo": "inicio", "conversacion": ev[0]["conversacion"], "titulo": "¿Cuántas personas hay en el casco?"}
    assert texto_de(ev, "progreso") == "Busco en la base."
    assert texto_de(ev) == "Consulto la base.En el casco hay 3 personas."
    h = [e for e in ev if e["tipo"] == "herramienta"]
    assert h[0] == {"tipo": "herramienta", "id": "toolu_1", "nombre": "contar_falsa", "etiqueta": "Contando personas",
                    "estado": "inicio"}
    assert h[1] == {**h[0], "estado": "ok", "resumen": "3 personas"}
    assert next(e for e in ev if e["tipo"] == "accion")["accion"] == {
        "tipo": "mapa", "acciones": [{"tipo": "volar", "lat": 7.0, "lon": -73.9}]}
    assert ev[-1] == {"tipo": "fin", "motivo": "listo", "limite": {"usados": 1, "maximo": 300}}
    assert falsas == [("contar_falsa", {"lugar": "Casco", "persona_id": None}, ev[0]["conversacion"], "toolu_1")]
    # La segunda petición reenvía el turno del asistente tal cual y el resultado de la herramienta
    segunda = api.peticiones[1]["json"]["messages"]
    assert [m["role"] for m in segunda] == ["user", "assistant", "user"]
    assert [b["type"] for b in segunda[1]["content"]] == ["thinking", "text", "tool_use"]
    assert segunda[2]["content"] == [{"type": "tool_result", "tool_use_id": "toolu_1",
                                      "content": json.dumps({"total": 3, "lugar": "Casco"}, ensure_ascii=False)}]


def test_lo_que_se_le_manda_al_modelo(sesion, falsas):
    api = encender(sesion.app, sse(T("Hola.")), sse(T("Otra vez.")))
    contexto = {"ruta": "/personas/12", "vista": "personas", "persona_id": 12, "filtros": {"lugar": "7"},
                "mapa": {"centro": [-73.91, 7.0], "zoom": 13.4}}
    _, ev = enviar(sesion, "Hola", contexto=contexto)
    cid = ev[0]["conversacion"]
    p = api.peticiones[0]
    assert p["url"] == "https://api.anthropic.com/v1/messages"
    assert p["cabeceras"]["anthropic-beta"] == BETAS
    j = p["json"]
    assert j["model"] == "claude-opus-5-5" and j["max_tokens"] == 32000 and j["stream"] is True
    assert j["thinking"] == {"type": "adaptive", "display": "updates",
                             "block_binding": {"prefix_mismatch_behavior": "drop_block"}}
    assert j["output_config"] == {"effort": "medium"} and j["fallbacks"] == "default"
    assert j["cache_control"] == {"type": "ephemeral"}
    assert j["system"][0]["cache_control"] == {"type": "ephemeral"} and len(j["system"]) == 1
    assert "Trabajemos juntos" in j["system"][0]["text"] and "admin (administrador)" in j["system"][0]["text"]
    assert [t["name"] for t in j["tools"]] == ["contar_falsa", "nota_falsa", "falla_falsa"]
    assert all(t["eager_input_streaming"] is True and "strict" not in t for t in j["tools"])
    primero = j["messages"][0]["content"]
    assert primero[1] == {"type": "text", "text": "Hola"}
    ctx = primero[0]["text"]
    assert ctx.startswith("<contexto_del_panel>\nFecha y hora en Colombia: ") and ctx.endswith("</contexto_del_panel>")
    assert "Vista abierta: personas (/personas/12)" in ctx and "Ficha abierta: persona 12" in ctx
    assert 'Filtros de la URL: {"lugar": "7"}' in ctx and "Mapa: centro lat 7.0, lon -73.91, zoom 13.4" in ctx
    # Segundo turno: el mismo system y las mismas herramientas, y el prefijo de mensajes idéntico (append-only)
    _, ev2 = enviar(sesion, "Sigue", conversacion=cid)
    assert ev2[-1]["motivo"] == "listo"
    j2 = api.peticiones[1]["json"]
    assert j2["system"] == j["system"] and j2["tools"] == j["tools"]
    assert j2["messages"][:1] == j["messages"] and j2["messages"][1]["role"] == "assistant"
    assert j2["messages"][2]["content"][1] == {"type": "text", "text": "Sigue"}


def test_modelo_sin_capacidades_va_sin_betas_ni_respaldo(sesion, falsas):
    api = encender(sesion.app, sse(T("Hola.")), modelo="claude-haiku-4-5")
    _, ev = enviar(sesion, "Hola")
    assert ev[-1]["motivo"] == "listo"
    p = api.peticiones[0]
    assert "anthropic-beta" not in p["cabeceras"]
    assert p["json"]["thinking"] == {"type": "adaptive"} and "fallbacks" not in p["json"]
    assert p["json"]["model"] == "claude-haiku-4-5"


def test_opus_5_lleva_respaldo_pero_no_notas_de_progreso(sesion, falsas):
    api = encender(sesion.app, sse(T("Hola."), model="claude-opus-5"), modelo="claude-opus-5")
    enviar(sesion, "Hola")
    p = api.peticiones[0]
    assert p["cabeceras"]["anthropic-beta"] == "server-side-fallback-2026-07-01,thinking-binding-controls-2026-08-01"
    assert p["json"]["thinking"] == {"type": "adaptive", "block_binding": {"prefix_mismatch_behavior": "drop_block"}}
    assert p["json"]["fallbacks"] == "default"


def test_se_guarda_append_only_con_uso_y_retencion(sesion, falsas):
    encender(sesion.app, sse(T("Uno."), uso={"input_tokens": 1000, "cache_read_input_tokens": 200}),
             sse(T("Dos.")))
    _, ev = enviar(sesion, "Primero")
    cid = ev[0]["conversacion"]
    antes = _mensajes(sesion, cid)
    _, ev = enviar(sesion, "Segundo", conversacion=cid)
    despues = _mensajes(sesion, cid)
    assert [m["seq"] for m in despues] == [1, 2, 3, 4] and [m["rol"] for m in despues] == ["user", "assistant"] * 2
    for a, d in zip(antes, despues):  # lo guardado no se toca (salvo la fecha de vencimiento, que se renueva)
        assert {k: v for k, v in a.items() if k != "expira"} == {k: v for k, v in d.items() if k != "expira"}
    assert despues[0]["texto"] == "Primero" and json.loads(despues[0]["contenido"])[1]["text"] == "Primero"
    assert despues[1]["uso"] == {"entrada": 1000, "salida": 50, "cache_lectura": 200, "cache_escritura": 800}
    c = _conv(sesion, cid)
    assert c["uid"] == 0 and c["n_mensajes"] == 4 and c["titulo"] == "Primero" and c["pendiente"] is None
    assert c["ocupada_hasta"] is None and c["turno"] is None
    assert (c["expira"] - datetime.now(timezone.utc)).days in (29, 30)
    assert all(m["expira"] == c["expira"] for m in despues)
    uso = sesion.app.state.db[conv_db.USO].find_one({"uid": 0})
    assert uso["mensajes"] == 2 and uso["entrada"] == 1900 and uso["salida"] == 100 and uso["cache_lectura"] == 200


def test_notas_de_progreso_sin_el_centinela(sesion, falsas):
    encender(sesion.app, sse(TH(llm.CENTINELA), TH("Reviso la base."), TH(""), T("Hola.")))
    _, ev = enviar(sesion, "Hola")
    assert [e["texto"] for e in ev if e["tipo"] == "progreso"] == ["Reviso la base."]


# ───────────────────────────── Confirmaciones ─────────────────────────────

def _con_pendiente(sesion, api_guion, pid, texto="Llamar el lunes"):
    encender(sesion.app, sse(T("Propongo la nota."), TU("toolu_n", "nota_falsa", {"persona_id": pid, "texto": texto}),
                             stop="tool_use"), *api_guion)
    r, ev = enviar(sesion, "Agrega una nota")
    assert r.status_code == 200, r.text
    return ev


def test_confirmacion_aprobada_ejecuta_una_vez(sesion, falsas):
    from ayudas_agente import contexto, correr, ejecutar
    db = sesion.app.state.db
    pid = persona(db, nombre="ANA INVENTADA DE PRUEBA", consentimiento="si")
    ev = _con_pendiente(sesion, [sse(T("Listo, quedó la nota."))], pid)
    cid = ev[0]["conversacion"]
    assert tipos(ev)[-4:] == ["herramienta", "herramienta", "confirmar", "fin"]
    assert [e["estado"] for e in ev if e["tipo"] == "herramienta"] == ["inicio", "pendiente"]
    conf = next(e for e in ev if e["tipo"] == "confirmar")
    assert conf == {"tipo": "confirmar", "id": "toolu_n", "nombre": "nota_falsa", "etiqueta": "Agregando la nota",
                    "titulo": "Agregar una nota", "detalle": [["Persona", f"#{pid}"], ["Nota", "Llamar el lunes"]],
                    "aviso": "Queda en la ficha"}
    assert ev[-1]["motivo"] == "confirmacion" and falsas == []  # nada se escribió todavía
    assert db.personas.find_one({"_id": pid}).get("notas") in (None, [])
    assert pid in _conv(sesion, cid)["personas"]
    vista = sesion.get(f"/api/agente/conversaciones/{cid}").json()
    assert vista["pendientes"] == [{"id": "toolu_n", "nombre": "nota_falsa", "etiqueta": "Agregando la nota",
                                    "titulo": "Agregar una nota", "detalle": conf["detalle"], "aviso": conf["aviso"]}]
    assert sesion.get("/api/agente/conversaciones").json()["conversaciones"][0]["pendiente"] is True
    # Aprueba: se ejecuta con la clave de idempotencia y el modelo sigue
    r, ev = decidir(sesion, cid, toolu_n=True)
    assert r.status_code == 200, r.text
    assert [(e["estado"], e.get("resumen")) for e in ev if e["tipo"] == "herramienta"] == [
        ("aprobada", None), ("ok", "Nota guardada")]
    assert {"tipo": "accion", "accion": {"tipo": "recargar"}} in ev
    assert texto_de(ev) == "Listo, quedó la nota." and ev[-1]["motivo"] == "listo"
    assert ev[-1]["limite"] == {"usados": 1, "maximo": 300}  # confirmar no cuenta como mensaje
    assert falsas == [("nota_falsa", {"persona_id": pid, "texto": "Llamar el lunes"}, cid, "toolu_n")]
    assert len(db.personas.find_one({"_id": pid})["notas"]) == 1
    assert _conv(sesion, cid)["pendiente"] is None
    # Otra vez la misma decisión: ya no hay nada pendiente
    r, _ = decidir(sesion, cid, toolu_n=True)
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "sin_pendientes"
    # Y si la herramienta se repitiera con la misma clave (un turno cortado que se reintenta), la API no la duplica
    lista, _ = herramientas_falsas()
    ctx = contexto(sesion.app, sesion, conversacion_id=cid, tool_use_id="toolu_n")
    correr(sesion, ejecutar, lista[1], ctx, {"persona_id": pid, "texto": "Llamar el lunes"})
    correr(sesion, ctx.api.cerrar)
    assert len(db.personas.find_one({"_id": pid})["notas"]) == 1


def test_confirmacion_rechazada_no_ejecuta(sesion, falsas):
    pid = persona(sesion.app.state.db, nombre="BETO INVENTADO DE PRUEBA")
    api_ev = _con_pendiente(sesion, [sse(T("Entendido."))], pid)
    cid = api_ev[0]["conversacion"]
    r, ev = decidir(sesion, cid, toolu_n=False)
    assert r.status_code == 200
    assert [(e["estado"], e.get("resumen")) for e in ev if e["tipo"] == "herramienta"] == [("rechazada", "Rechazada")]
    assert falsas == [] and ev[-1]["motivo"] == "listo"
    msgs = _mensajes(sesion, cid)
    resultado = json.loads(msgs[2]["contenido"])
    assert resultado == [{"type": "tool_result", "tool_use_id": "toolu_n", "content": bucle.RECHAZADA, "is_error": True}]
    assert msgs[2]["herramientas"] == [{"id": "toolu_n", "estado": "rechazada", "resumen": "Rechazada"}]


def test_lectura_y_escrituras_en_la_misma_ronda(sesion, falsas):
    pid = persona(sesion.app.state.db, nombre="CARLA INVENTADA DE PRUEBA")
    api = encender(sesion.app,
                   sse(TU("toolu_a", "contar_falsa", {"lugar": "Casco"}),
                       TU("toolu_b", "nota_falsa", {"persona_id": pid, "texto": "Uno"}),
                       TU("toolu_c", "contar_falsa", {"lugar": "Tigre"}),
                       TU("toolu_d", "nota_falsa", {"persona_id": pid, "texto": "Dos"}), stop="tool_use"),
                   sse(T("Hecho.")))
    _, ev = enviar(sesion, "Varias cosas")
    cid = ev[0]["conversacion"]
    assert [e["id"] for e in ev if e["tipo"] == "confirmar"] == ["toolu_b", "toolu_d"]
    assert [x[0] for x in falsas] == ["contar_falsa", "contar_falsa"]  # las lecturas corren en el acto
    assert len(_mensajes(sesion, cid)) == 2  # sus resultados esperan la decisión: un solo mensaje con todos
    # Solo se decide una: la otra cuenta como rechazada
    _, ev = decidir(sesion, cid, toolu_b=True)
    assert [(e["id"], e["estado"]) for e in ev if e["tipo"] == "herramienta"] == [
        ("toolu_b", "aprobada"), ("toolu_b", "ok"), ("toolu_d", "rechazada")]
    resultados = api.peticiones[1]["json"]["messages"][-1]["content"]
    assert [x["tool_use_id"] for x in resultados] == ["toolu_a", "toolu_b", "toolu_c", "toolu_d"]
    assert [x.get("is_error", False) for x in resultados] == [False, False, False, True]
    assert len(sesion.app.state.db.personas.find_one({"_id": pid})["notas"]) == 1


def test_mensaje_nuevo_con_algo_pendiente_lo_rechaza(sesion, falsas):
    pid = persona(sesion.app.state.db, nombre="DORA INVENTADA DE PRUEBA")
    ev = _con_pendiente(sesion, [sse(T("Bueno, otra cosa."))], pid)
    cid = ev[0]["conversacion"]
    r, ev = enviar(sesion, "Mejor no, dime otra cosa", conversacion=cid)
    assert r.status_code == 200
    assert [(e["id"], e["estado"]) for e in ev if e["tipo"] == "herramienta"] == [("toolu_n", "rechazada")]
    assert ev[-1]["motivo"] == "listo" and falsas == [] and _conv(sesion, cid)["pendiente"] is None
    ultimo = json.loads(_mensajes(sesion, cid)[2]["contenido"])
    assert ultimo[0] == {"type": "tool_result", "tool_use_id": "toolu_n", "content": bucle.NO_APROBADA,
                         "is_error": True}
    assert ultimo[1]["text"].startswith("<contexto_del_panel>") and ultimo[2] == {
        "type": "text", "text": "Mejor no, dime otra cosa"}


def test_tool_use_interrumpido_recibe_un_error_antes_del_mensaje_nuevo(sesion, falsas):
    api = encender(sesion.app, sse(T("Hola.")), sse(T("Sigo.")))
    _, ev = enviar(sesion, "Hola")
    cid = ev[0]["conversacion"]
    c = _conv(sesion, cid)
    # Un turno cortado: el asistente pidió una herramienta y no alcanzó a guardarse el resultado
    conv_db.guardar(sesion.app.state.db, cid, 0, c["expira"], "assistant",
                    [{"type": "tool_use", "id": "toolu_cortada", "name": "contar_falsa", "input": {"lugar": "X"}}])
    _, ev = enviar(sesion, "¿Sigues?", conversacion=cid)
    assert ev[-1]["motivo"] == "listo"
    ultimo = api.peticiones[1]["json"]["messages"][-1]
    assert ultimo["role"] == "user" and ultimo["content"][0] == {
        "type": "tool_result", "tool_use_id": "toolu_cortada", "content": bucle.INTERRUMPIDA, "is_error": True}
    assert ultimo["content"][2] == {"type": "text", "text": "¿Sigues?"}
    vista = sesion.get(f"/api/agente/conversaciones/{cid}").json()
    parte = next(p for m in vista["mensajes"] if m["rol"] == "asistente" for p in m["partes"] if p["tipo"] == "herramienta")
    assert parte["estado"] == "error" and parte["resumen"] == "Interrumpida"


def test_escritura_apagada_despues_de_crear_la_conversacion(sesion, falsas):
    pid = persona(sesion.app.state.db, nombre="ELSA INVENTADA DE PRUEBA")
    encender(sesion.app, sse(T("Hola.")),
             sse(TU("toolu_w", "nota_falsa", {"persona_id": pid, "texto": "x"}), stop="tool_use"),
             sse(T("No se pudo.")))
    _, ev = enviar(sesion, "Hola")
    cid = ev[0]["conversacion"]
    sesion.app.state.db.meta.update_one({"_id": "ajustes"}, {"$set": {"agente": {
        "roles": ["admin", "coordinador"], "escritura": False, "mnemo_coordinadores": False, "retencion_dias": 30}}},
        upsert=True)
    _, ev = enviar(sesion, "Agrega una nota", conversacion=cid)
    h = [e for e in ev if e["tipo"] == "herramienta"]
    assert [x["estado"] for x in h] == ["inicio", "error"] and "no permiten" in h[1]["resumen"]
    assert not [e for e in ev if e["tipo"] == "confirmar"] and ev[-1]["motivo"] == "listo"


# ───────────────────────────── Rechazo, respaldo, reintentos ─────────────────────────────

def test_rechazo_del_modelo(sesion, falsas):
    api = encender(sesion.app, sse(T("Empiezo a "), stop="refusal", stop_details={"type": "refusal", "category": "cyber"}),
                   sse(T("Claro.")))
    _, ev = enviar(sesion, "Algo raro")
    cid = ev[0]["conversacion"]
    assert tipos(ev) == ["inicio", "texto", "descartar", "aviso", "fin"]
    assert ev[-2] == {"tipo": "aviso", "texto": bucle.AVISO_RECHAZO, "nivel": "alerta"}
    assert ev[-1]["motivo"] == "rechazo"
    msgs = _mensajes(sesion, cid)
    assert [(m["rol"], m["replay"]) for m in msgs] == [("user", True), ("assistant", False), ("aviso", False)]
    # El siguiente mensaje va unido al anterior: la API exige que se alternen
    _, ev = enviar(sesion, "Otra cosa", conversacion=cid)
    enviados = api.peticiones[1]["json"]["messages"]
    assert len(enviados) == 1 and enviados[0]["role"] == "user"
    assert [b["text"] for b in enviados[0]["content"] if not b["text"].startswith("<contexto")] == ["Algo raro",
                                                                                                    "Otra cosa"]
    vista = sesion.get(f"/api/agente/conversaciones/{cid}").json()
    assert vista["mensajes"][1] == {"rol": "asistente", "partes": [
        {"tipo": "aviso", "texto": bucle.AVISO_RECHAZO, "nivel": "alerta"}]}


def test_respaldo_a_mitad_de_la_respuesta(sesion, falsas):
    fb = {"type": "fallback", "from": {"model": "claude-opus-5-5"}, "to": {"model": "claude-opus-5"},
          "trigger": {"type": "refusal", "category": "cyber"}}
    api = encender(sesion.app,
                   sse(TH("", "s1"), T("Parcial "), TU("toolu_x", "contar_falsa", {"lugar": "No"}), fb,
                       TH("Sigo.", "s2"), TU("toolu_3", "contar_falsa", {"lugar": "Casco"}), stop="tool_use",
                       model="claude-opus-5"),
                   sse(T("Listo.")))
    _, ev = enviar(sesion, "Hola")
    cid = ev[0]["conversacion"]
    avisos = [e for e in ev if e["tipo"] == "aviso"]
    assert len(avisos) == 1 and avisos[0]["nivel"] == "info" and "claude-opus-5" in avisos[0]["texto"]
    assert ("toolu_x", "error", "Descartada") in [(e["id"], e["estado"], e.get("resumen")) for e in ev
                                                   if e["tipo"] == "herramienta"]
    assert [x[1]["lugar"] for x in falsas] == ["Casco"]  # lo de antes del cambio de modelo no se ejecuta
    asistente = _mensajes(sesion, cid)[1]
    assert [b["type"] for b in json.loads(asistente["contenido"])] == ["text", "fallback", "thinking", "tool_use"]
    assert asistente["modelo"] == "claude-opus-5"
    assert [r["tool_use_id"] for r in api.peticiones[1]["json"]["messages"][-1]["content"]] == ["toolu_3"]
    assert ev[-1]["motivo"] == "listo"


def test_json_roto_de_una_herramienta_repite_la_ronda(sesion, falsas):
    api = encender(sesion.app, sse(TU("toolu_4", "contar_falsa", "no es json"), stop="tool_use"), sse(T("Bien.")))
    _, ev = enviar(sesion, "Hola")
    assert "descartar" in tipos(ev) and texto_de(ev) == "Bien." and ev[-1]["motivo"] == "listo"
    assert len(api.peticiones) == 2 and falsas == []
    cid = ev[0]["conversacion"]
    assert [m["rol"] for m in _mensajes(sesion, cid)] == ["user", "assistant"]


def test_sobrecarga_a_mitad_del_flujo_repite_la_ronda(sesion, falsas):
    api = encender(sesion.app, sse(T("Hola a me"), error="overloaded_error"), sse(T("Hola a medias no: hola.")))
    _, ev = enviar(sesion, "Hola")
    assert tipos(ev) == ["inicio", "texto", "descartar", "texto", "fin"] and ev[-1]["motivo"] == "listo"
    assert len(api.peticiones) == 2
    cid = ev[0]["conversacion"]
    guardado = json.loads(_mensajes(sesion, cid)[1]["contenido"])
    assert guardado == [{"type": "text", "text": "Hola a medias no: hola."}]


def test_sobrecarga_que_no_cede_termina_con_error(sesion, falsas):
    api = encender(sesion.app, *[sse(T("x"), error="overloaded_error") for _ in range(3)])
    _, ev = enviar(sesion, "Hola")
    assert tipos(ev)[-4:] == ["descartar", "texto", "error", "fin"] and ev.count({"tipo": "descartar"}) == 2
    assert ev[-2] == {"tipo": "error", "codigo": "llm_no_disponible",
                      "mensaje": "El modelo no está disponible en este momento. Intente de nuevo en un rato."}
    assert ev[-1]["motivo"] == "error" and len(api.peticiones) == 3
    assert [m["rol"] for m in _mensajes(sesion, ev[0]["conversacion"])] == ["user"]


@pytest.mark.parametrize("estado,tipo,codigo", [(529, "overloaded_error", "llm_no_disponible"),
                                                (401, "authentication_error", "llm_clave"),
                                                (400, "invalid_request_error", "llm_peticion")])
def test_error_http_del_modelo(sesion, falsas, estado, tipo, codigo):
    encender(sesion.app, (estado, {"type": "error", "error": {"type": tipo, "message": "inventado"}}))
    _, ev = enviar(sesion, "Hola")
    assert tipos(ev) == ["inicio", "error", "fin"] and ev[1]["codigo"] == codigo and ev[2]["motivo"] == "error"
    assert "inventado" not in ev[1]["mensaje"]


def test_fallo_de_conexion_al_abrir(sesion, falsas):
    # Un fallo al abrir el flujo lo reintenta el SDK (aquí sin reintentos), no el bucle: llega como error de conexión
    api = encender(sesion.app, httpx2.ConnectError("cortado"), sse(T("Hola.")))
    _, ev = enviar(sesion, "Hola")
    assert ev[-2]["codigo"] == "llm_conexion" and len(api.peticiones) == 1


def test_corte_de_transporte_a_mitad_del_cuerpo_repite_la_ronda(sesion, falsas):
    api = encender_lento(sesion.app, Corte(sse(T("Hola, voy a con"), T("tar")), httpx2.ReadError("cortado")),
                         sse(T("Hola.")), pausa=0)
    _, ev = enviar(sesion, "Hola")
    assert "descartar" in tipos(ev) and ev[-1]["motivo"] == "listo" and len(api.peticiones) == 2
    assert json.loads(_mensajes(sesion, ev[0]["conversacion"])[1]["contenido"]) == [{"type": "text", "text": "Hola."}]


# ───────────────────────────── Entradas del modelo ─────────────────────────────

def test_entrada_que_no_valida_vuelve_como_invalid_json(sesion, falsas):
    api = encender(sesion.app, sse(TU("toolu_5", "contar_falsa", '{"persona_id": 5'), stop="tool_use"),
                   sse(T("Perdón.")))
    _, ev = enviar(sesion, "Hola")
    r = api.peticiones[1]["json"]["messages"][-1]["content"][0]
    assert r["is_error"] is True and json.loads(r["content"])["error"]["codigo"] == "INVALID_JSON"
    assert any("lugar" in x for x in json.loads(r["content"])["error"]["detalle"]["errores"])
    assert falsas == [] and ev[-1]["motivo"] == "listo"


def test_herramienta_desconocida(sesion, falsas):
    api = encender(sesion.app, sse(TU("toolu_6", "borrar_todo", {}), stop="tool_use"), sse(T("No puedo.")))
    _, ev = enviar(sesion, "Hola")
    h = [e for e in ev if e["tipo"] == "herramienta"]
    assert h[0]["etiqueta"] == "borrar_todo" and h[1]["estado"] == "error"
    r = api.peticiones[1]["json"]["messages"][-1]["content"][0]
    assert r["is_error"] and json.loads(r["content"])["error"]["codigo"] == "no_existe"


def test_entrada_cortada_por_max_tokens_no_se_ejecuta(sesion, falsas):
    api = encender(sesion.app, sse(TU("toolu_2", "contar_falsa", '{"lugar": "Ca'), stop="max_tokens"),
                   sse(T("Reintento.")))
    _, ev = enviar(sesion, "Hola")
    r = api.peticiones[1]["json"]["messages"][-1]["content"][0]
    assert r == {"type": "tool_result", "tool_use_id": "toolu_2", "content": bucle.CORTADA, "is_error": True}
    assert falsas == [] and ev[-1]["motivo"] == "listo"


def test_respuesta_cortada_por_max_tokens_avisa(sesion, falsas):
    encender(sesion.app, sse(T("Una respuesta muy lar"), stop="max_tokens"))
    _, ev = enviar(sesion, "Hola")
    assert tipos(ev) == ["inicio", "texto", "aviso", "fin"] and ev[-1]["motivo"] == "listo"


# ───────────────────────────── Errores de herramientas ─────────────────────────────

def test_error_fatal_de_herramienta_termina_el_turno(sesion, falsas):
    api = encender(sesion.app, sse(TU("toolu_f", "falla_falsa", {"modo": "fatal"}),
                                   TU("toolu_g", "contar_falsa", {"lugar": "Casco"}), stop="tool_use"))
    _, ev = enviar(sesion, "Hola")
    assert ev[-2] == {"tipo": "error", "mensaje": "Llegó al tope de personas consultadas hoy.", "codigo": "volumen"}
    assert ev[-1]["motivo"] == "error" and len(api.peticiones) == 1
    assert [x[0] for x in falsas] == ["falla_falsa"]  # lo que seguía no se ejecuta
    resultados = json.loads(_mensajes(sesion, ev[0]["conversacion"])[2]["contenido"])
    assert [(x["tool_use_id"], x["is_error"]) for x in resultados] == [("toolu_f", True), ("toolu_g", True)]


@pytest.mark.parametrize("modo,codigo", [("interno", "error"), ("error", "no_existe")])
def test_herramienta_que_falla_vuelve_al_modelo(sesion, falsas, modo, codigo):
    api = encender(sesion.app, sse(TU("toolu_e", "falla_falsa", {"modo": modo}), stop="tool_use"), sse(T("Perdón.")))
    _, ev = enviar(sesion, "Hola")
    r = api.peticiones[1]["json"]["messages"][-1]["content"][0]
    assert r["is_error"] and json.loads(r["content"])["error"]["codigo"] == codigo
    assert "inventado" not in r["content"]  # el detalle de una excepción interna no sale
    assert ev[-1]["motivo"] == "listo"


# ───────────────────────────── Topes ─────────────────────────────

def test_tope_de_rondas(sesion, falsas, monkeypatch):
    monkeypatch.setattr(bucle, "MAX_RONDAS", 2)
    api = encender(sesion.app, *[sse(TU(f"toolu_{i}", "contar_falsa", {"lugar": "Casco"}), stop="tool_use")
                                 for i in range(2)])
    _, ev = enviar(sesion, "Hola")
    assert ev[-1]["motivo"] == "pasos" and len(api.peticiones) == 2 and len(falsas) == 2


def test_tope_de_tiempo(sesion, falsas, monkeypatch):
    monkeypatch.setattr(bucle, "TOPE_TURNO_S", 0)
    api = encender(sesion.app, sse(TU("toolu_t", "contar_falsa", {"lugar": "Casco"}), stop="tool_use"))
    _, ev = enviar(sesion, "Hola")
    assert ev[-1]["motivo"] == "pasos" and len(api.peticiones) == 1


def test_tope_de_tokens_en_el_turno(sesion, falsas):
    api = encender(sesion.app, sse(TU("toolu_k", "contar_falsa", {"lugar": "Casco"}), stop="tool_use",
                                   uso={"input_tokens": 299_500, "cache_read_input_tokens": 1000}))
    _, ev = enviar(sesion, "Hola")
    assert ev[-2] == {"tipo": "aviso", "texto": bucle.AVISO_LARGA, "nivel": "alerta"} and ev[-1]["motivo"] == "pasos"
    assert len(api.peticiones) == 1
    r, _ = enviar(sesion, "Más", conversacion=ev[0]["conversacion"])
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "larga"


# ───────────────────────────── Herramientas congeladas ─────────────────────────────

def test_herramientas_congeladas_aunque_cambie_el_catalogo(sesion, falsas, monkeypatch):
    lista, _ = herramientas_falsas()
    api = encender(sesion.app, sse(T("Hola.")),
                   sse(TU("toolu_z", "falla_falsa", {"modo": "error"}), stop="tool_use"), sse(T("Ya no está.")))
    _, ev = enviar(sesion, "Hola")
    cid = ev[0]["conversacion"]
    # El código cambia: «falla_falsa» desaparece y aparece otra herramienta
    from pydantic import BaseModel

    from app.agente.herramientas.base import Herramienta, Resultado

    class Nada(BaseModel):
        pass

    async def nada(ctx, a):
        return Resultado("nada")
    nueva = Herramienta("nueva_falsa", "Nueva (prueba).", Nada, "lectura", ("cuenta",), "Probando", nada)
    con_herramientas(monkeypatch, [lista[0], lista[1], nueva])
    _, ev = enviar(sesion, "Sigue", conversacion=cid)
    primera, segunda = api.peticiones[0]["json"], api.peticiones[1]["json"]
    assert segunda["tools"] == primera["tools"] and segunda["system"] == primera["system"]
    assert "nueva_falsa" not in [t["name"] for t in segunda["tools"]]
    r = api.peticiones[2]["json"]["messages"][-1]["content"][0]
    assert r["is_error"] and json.loads(r["content"])["error"]["codigo"] == "no_existe"


def test_herramientas_reales_se_congelan_en_la_conversacion(sesion, monkeypatch):
    """Con el catálogo de verdad (si ya existe): lo que se ofrece es `herramientas.para` y se repite idéntico."""
    from app import acceso
    from app.agente import herramientas, politica
    if not herramientas.fijas():
        pytest.skip("las herramientas del panel todavía no están")
    api = encender(sesion.app, sse(T("Hola.")), sse(T("Hola otra vez.")))
    _, ev = enviar(sesion, "Hola")
    cid = ev[0]["conversacion"]
    agente = politica.leer(sesion.app.state.db)[1]
    esperadas = [h.definicion() for h in herramientas.para(acceso.quien_admin(sesion.app.state.cfg), agente,
                                                           sesion.app.state.cfg)]
    assert api.peticiones[0]["json"]["tools"] == json.loads(json.dumps(esperadas))
    enviar(sesion, "Otra", conversacion=cid)
    assert api.peticiones[1]["json"]["tools"] == api.peticiones[0]["json"]["tools"]


def test_buscar_personas_de_verdad(sesion):
    """Una herramienta real, si ya existe: el turno corre entero y su resultado vuelve al modelo."""
    from app.agente import herramientas
    if "buscar_personas" not in herramientas.por_nombre():
        pytest.skip("buscar_personas todavía no está")
    persona(sesion.app.state.db, nombre="FABIO INVENTADO DE PRUEBA")
    api = encender(sesion.app, sse(TU("toolu_r", "buscar_personas", {"q": "FABIO INVENTADO"}), stop="tool_use"),
                   sse(T("Encontré a Fabio.")))
    _, ev = enviar(sesion, "Busca a Fabio")
    assert ev[-1]["motivo"] == "listo"
    r = api.peticiones[1]["json"]["messages"][-1]["content"][0]
    assert r["tool_use_id"] == "toolu_r" and not r.get("is_error"), r
    assert [e["estado"] for e in ev if e["tipo"] == "herramienta"] == ["inicio", "ok"]


# ───────────────────────────── Reglas sueltas ─────────────────────────────

def test_reenviable():
    fb = {"type": "fallback", "from": {"model": "a"}, "to": {"model": "b"}}
    bloques = [{"type": "thinking", "thinking": "x", "signature": ""}, {"type": "text", "text": "a"},
               {"type": "tool_use", "id": "t1", "name": "n", "input": {}}, {"type": "raro"}, fb,
               {"type": "thinking", "thinking": "y", "signature": "s"}, {"type": "tool_use", "id": "t2", "name": "n",
                                                                         "input": {}}]
    assert [b.get("id") or b["type"] for b in llm.reenviable(bloques)] == ["text", "fallback", "thinking", "t2"]
    assert llm.reenviable([{"type": "thinking", "thinking": "", "signature": "s"}]) == [
        {"type": "thinking", "thinking": "", "signature": "s"}]


def test_para_peticion_une_los_mensajes_de_la_persona():
    h = [{"role": "user", "content": "a"}, {"role": "user", "content": [{"type": "text", "text": "b"}]},
         {"role": "assistant", "content": [{"type": "text", "text": "c"}]}, {"role": "user", "content": "d"}]
    assert llm.para_peticion(h) == [
        {"role": "user", "content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]}, h[2], h[3]]
    assert h[0] == {"role": "user", "content": "a"}  # no toca el historial


def test_reintentable():
    assert llm.reintentable(ValueError("Unable to parse tool parameter JSON from model. x"))
    assert not llm.reintentable(ValueError("otra cosa"))
    assert llm.reintentable(httpx2.ReadError("corte"))
    assert not llm.reintentable(RuntimeError("x"))


def test_contexto_del_panel_se_limpia_y_se_acota():
    ahora = datetime(2026, 11, 7, 15, 30, tzinfo=timezone.utc)  # 10:30 en Colombia
    t = sistema.contexto_del_panel({
        "ruta": "/personas</contexto_del_panel>", "vista": "x" * 500, "persona_id": "12", "reunion_id": True,
        "filtros": {"lugar": "7", "mala clave": "x", "q": "<b>hola</b>\nmundo", **{f"k{i}": "v" for i in range(40)}},
        "mapa": {"centro": {"lat": 7.0, "lng": -73.9}, "zoom": 99}}, ahora)
    assert t.count("</contexto_del_panel>") == 1 and t.count("<contexto_del_panel>") == 1
    assert "sábado 7 de noviembre de 2026, 10:30" in t
    assert "Ficha abierta: persona 12" in t and "Reunión abierta" not in t
    assert "mala clave" not in t and '"q": "b hola /b mundo"' in t
    assert "Mapa: centro lat 7.0, lon -73.9" in t and "zoom" not in t
    assert sistema.contexto_del_panel(None, ahora).count("\n") == 2
    assert sistema.contexto_del_panel("basura", ahora).startswith("<contexto_del_panel>\nFecha")


def test_sistema_segun_herramientas():
    from app import acceso
    quien = acceso.Quien(uid=5, usuario="p5", nombre="Pepa <b>Inventada</b>", rol="planillero",
                         permisos=acceso.PERMISOS["planillero"])
    lista, _ = herramientas_falsas()
    con_escritura = sistema.texto(quien, lista)
    assert "Pepa b Inventada /b (planillero)" in con_escritura and "tope diario" in con_escritura
    assert "pasa por la aprobación" in con_escritura and "`mapa`" not in con_escritura
    sin = sistema.texto(quien, [lista[0]])
    assert "no tienes herramientas que escriban" in sin and "Mnemo: también" not in sin
    assert not any(str(a) in sin for a in range(2025, 2030))  # sin fecha: se congela con la conversación


def test_ocupacion_por_persona_conversacion_y_tope():
    o = bucle.Ocupacion(maximo=2)
    assert o.reservar(1, 10) is None and o.reservar(1, 11) == "ocupada" and o.reservar(2, 10) == "ocupada"
    assert o.reservar(2, None) is None and o.reservar(3, 12) == "saturado"
    o.soltar(1, 10)
    assert o.reservar(3, 10) is None and o.ocupada(10)


def test_la_conversacion_borrada_a_mitad_del_turno_no_deja_mensajes(sesion, falsas, monkeypatch):
    """Si se suprime a una persona mientras el asistente responde, la conversación se borra y el turno no deja
    mensajes sueltos: termina con un error claro."""
    from fastapi.concurrency import run_in_threadpool
    from pydantic import BaseModel

    from app import db as bd
    from app.agente.herramientas.base import Herramienta, Resultado
    db = sesion.app.state.db
    pid = persona(db, nombre="JULIA INVENTADA DE PRUEBA")

    class Entrada(BaseModel):
        pass

    async def ver(ctx, a):
        await run_in_threadpool(conv_db.sumar_personas, db, ctx.conversacion_id, {pid})
        await run_in_threadpool(bd.limpiar_ligados, db, [pid])  # como DELETE /api/personas/{pid} en ese momento
        return Resultado({"nombre": "Julia"}, personas={pid})
    lista, _ = herramientas_falsas()
    con_herramientas(monkeypatch, [*lista, Herramienta("ver_falsa", "Ver (prueba).", Entrada, "lectura", ("cuenta",),
                                                       "Viendo", ver)])
    encender(sesion.app, sse(TU("toolu_v", "ver_falsa", {}), stop="tool_use"), sse(T("No debería llegar.")))
    _, ev = enviar(sesion, "¿Quién es Julia?")
    cid = ev[0]["conversacion"]
    assert ev[-2]["tipo"] == "error" and ev[-2]["codigo"] == "borrada" and ev[-1]["motivo"] == "error"
    assert db[conv_db.CONVERSACIONES].find_one({"_id": cid}) is None
    assert db[conv_db.MENSAJES].count_documents({"conversacion": cid}) == 0


def test_textos_con_sustitutos_sueltos_no_rompen_la_conversacion(sesion, falsas):
    """Un sustituto UTF-16 suelto (válido en JSON, imposible en UTF-8) no deja la conversación inservible: en el texto
    de la persona lo rechaza la validación (422); en el contexto o en lo que escribe el modelo se reemplaza."""
    from ayudas_agente import ndjson
    api = encender(sesion.app, sse(T("Hola \udc80 roto")), sse(T("Bien.")))
    r = sesion.post("/api/agente/mensajes", content=b'{"texto": "Hola \\ud800"}',
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 422
    r = sesion.post("/api/agente/mensajes", content=b'{"texto": "Hola", "contexto": {"vista": "x\\udfff"}}',
                    headers={"Content-Type": "application/json"})
    ev = ndjson(r.text)
    assert ev[-1]["motivo"] == "listo"
    _, ev = enviar(sesion, "Otra", conversacion=ev[0]["conversacion"])
    assert ev[-1]["motivo"] == "listo"
    enviado = json.dumps(api.peticiones[1]["json"], ensure_ascii=False)
    enviado.encode("utf-8")  # todo lo que se reenvía es UTF-8 válido
    assert "Hola ? roto" in enviado


# ───────────────────────────── Cliente de Anthropic y Mnemo ─────────────────────────────

def test_cliente_de_anthropic_se_crea_al_primer_uso(cfg):
    import asyncio
    from dataclasses import replace

    import anthropic

    from app.main import crear_app
    app = crear_app(replace(cfg, anthropic_api_key="clave-falsa"))
    try:
        assert getattr(app.state, "agente_cliente", None) is None  # crear_app no lo crea (ni toca la red)
        c = llm.cliente(app, app.state.cfg)
        assert isinstance(c, anthropic.AsyncAnthropic) and c.api_key == "clave-falsa" and c.max_retries == 2
        assert llm.cliente(app, app.state.cfg) is c
        asyncio.run(llm.cerrar(app))
        assert app.state.agente_cliente is None
        inyectado = object()
        app.state.agente_cliente = inyectado
        assert llm.cliente(app, app.state.cfg) is inyectado
        asyncio.run(llm.cerrar(app))  # uno inyectado no lo cierra este módulo
        assert app.state.agente_cliente is inyectado
    finally:
        app.state.cliente.close()


class _MnemoFalso:
    instrucciones = "Use search before fetch. " + "x" * 3000


@pytest.fixture
def mnemo_falso(monkeypatch):
    """Lo que el bucle usa de Mnemo (herramientas/mnemo.py y mnemo_cliente.py), inventado: así se prueba el núcleo sin
    depender de esos módulos ni de un servidor MCP."""
    from pydantic import BaseModel

    from app.agente import mnemo_cliente
    from app.agente.herramientas import mnemo
    from app.agente.herramientas.base import Herramienta, Resultado
    cliente, llamadas, falla = _MnemoFalso(), [], {"definiciones": False}

    class Buscar(BaseModel):
        query: str

    async def buscar(ctx, a):
        llamadas.append((ctx.mnemo, a.query))
        return Resultado({"results": [{"id": "doc_1", "title": "Acta inventada"}]}, resumen="1 documento")

    async def definiciones(c, filtro):
        if falla["definiciones"]:
            raise RuntimeError("Mnemo caído")
        assert c is cliente
        return [{"name": "search", "description": "Search Mnemo", "inputSchema": {"type": "object"}}]

    def desde_definiciones(defs):
        return [Herramienta("mnemo_search", d["description"], Buscar, "lectura", ("cuenta",), "Buscando en Mnemo",
                            buscar, esquema={"type": "object", "properties": {"query": {"type": "string"}}},
                            nombre_remoto=d["name"]) for d in defs]

    monkeypatch.setattr(mnemo, "disponible_para", lambda quien, ajustes, cfg: quien.es_admin)
    monkeypatch.setattr(mnemo, "definiciones", definiciones)
    monkeypatch.setattr(mnemo, "desde_definiciones", desde_definiciones)
    monkeypatch.setattr(mnemo_cliente, "cliente_de", lambda app: cliente)
    return cliente, llamadas, falla


def test_mnemo_va_despues_de_las_fijas_y_con_sus_instrucciones(sesion, falsas, mnemo_falso):
    cliente, llamadas, _ = mnemo_falso
    api = encender(sesion.app, sse(TU("toolu_m", "mnemo_search", {"query": "acta"}), stop="tool_use"),
                   sse(T("Encontré el acta.")))
    _, ev = enviar(sesion, "Busca el acta en Mnemo")
    j = api.peticiones[0]["json"]
    assert [t["name"] for t in j["tools"]] == ["contar_falsa", "nota_falsa", "falla_falsa", "mnemo_search"]
    assert "Mnemo: también tienes herramientas" in j["system"][0]["text"]
    assert "Use search before fetch." in j["system"][0]["text"]
    assert len(j["system"][0]["text"]) < len(cliente.instrucciones) + 4000  # recortadas a 2 500 caracteres
    assert llamadas == [(cliente, "acta")] and ev[-1]["motivo"] == "listo"
    conv = sesion.app.state.db[conv_db.CONVERSACIONES].find_one({"_id": ev[0]["conversacion"]})
    assert json.loads(conv["mnemo"])[0]["name"] == "search"


def test_si_mnemo_falla_la_conversacion_sigue_sin_el(sesion, falsas, mnemo_falso):
    _, _, falla = mnemo_falso
    falla["definiciones"] = True
    api = encender(sesion.app, sse(T("Hola.")))
    _, ev = enviar(sesion, "Hola")
    assert {"tipo": "aviso", "texto": "Mnemo no respondió: esta conversación sigue sin sus herramientas.",
            "nivel": "alerta"} in ev and ev[-1]["motivo"] == "listo"
    j = api.peticiones[0]["json"]
    assert "mnemo_search" not in [t["name"] for t in j["tools"]] and "Mnemo: también" not in j["system"][0]["text"]


def test_mnemo_no_se_le_ofrece_al_coordinador(sesion, falsas, mnemo_falso):
    from ayudas_g3 import coordinador
    api = encender(sesion.app, sse(T("Hola.")))
    k = coordinador(sesion.app, sesion.app.state.db)
    r, ev = enviar(k, "Hola")
    assert r.status_code == 200 and ev[-1]["motivo"] == "listo"
    assert "mnemo_search" not in [t["name"] for t in api.peticiones[0]["json"]["tools"]]
    assert "(coordinador)" in api.peticiones[0]["json"]["system"][0]["text"]
