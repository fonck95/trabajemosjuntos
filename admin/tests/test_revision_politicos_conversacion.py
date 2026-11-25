"""Una conversación creada con los datos políticos apagados no los recibe aunque el administrador los encienda después:
sus instrucciones (sin las reglas de lo político) y su lista de herramientas quedaron fijas al crearla. Hay que abrir
una conversación nueva."""
import json

import ayudas_agente as aa
from app.agente import conversaciones as conv_db
from app.agente import sistema
from test_politicos_herramientas import _asignado, mundo  # noqa: F401


def _ficha(api):
    peticion = api.peticiones[-1]["json"]
    return peticion, json.loads(peticion["messages"][-1]["content"][0]["content"])


def test_la_conversacion_creada_apagada_no_recibe_lo_politico_al_encender(sesion, mundo):
    db, x = mundo["db"], mundo["x"]
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"agente_politicos": {"asistente": False, "mcp": False}}},
                       upsert=True)
    api = aa.encender(sesion.app, aa.sse(aa.T("Hola.")),
                      aa.sse(aa.TU("toolu_v", "ver_persona", {"persona_id": x}), stop="tool_use"),
                      aa.sse(aa.T("Listo.")))
    r, ev = aa.enviar(sesion, "Hola")
    assert r.status_code == 200, r.text
    cid = ev[0]["conversacion"]
    assert sistema.SIN_POLITICOS in db[conv_db.CONVERSACIONES].find_one({"_id": cid})["sistema"]
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"agente_politicos": {"asistente": True, "mcp": False}}})
    r, ev = aa.enviar(sesion, "¿Quién la trajo?", conversacion=cid)
    assert r.status_code == 200, r.text
    peticion, ficha = _ficha(api)
    assert not {"lideres", "marcar_tipo", "asignar_lider"} & {t["name"] for t in peticion["tools"]}
    assert not {"votante", "lider", "concejal", "lideres", "listas", "fuentes", "cedula_origen"} & set(ficha), ficha


def test_una_conversacion_nueva_con_el_ajuste_encendido_si_los_recibe(sesion, mundo):
    db, x = mundo["db"], mundo["x"]
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"agente_politicos": {"asistente": True, "mcp": False}}},
                       upsert=True)
    api = aa.encender(sesion.app, aa.sse(aa.TU("toolu_v", "ver_persona", {"persona_id": x}), stop="tool_use"),
                      aa.sse(aa.T("Listo.")))
    r, ev = aa.enviar(sesion, "¿Quién la trajo?")
    assert r.status_code == 200, r.text
    peticion, ficha = _ficha(api)
    assert "lideres" in {t["name"] for t in peticion["tools"]}
    assert "lideres" in ficha or "votante" in ficha, ficha


def test_la_bienvenida_no_sugiere_lo_que_el_ajuste_apaga():
    from app.agente import politica
    encendido = {"agente_politicos": {"asistente": True, "mcp": False}}
    apagado = {"agente_politicos": {"asistente": False, "mcp": True}}
    assert politica.SUGERENCIA_POLITICA in politica.sugerencias("admin", encendido)
    assert politica.SUGERENCIA_POLITICA not in politica.sugerencias("admin", apagado)
    assert politica.SUGERENCIA_PLANILLAS not in politica.sugerencias("coordinador", encendido, planillas=False)
    assert politica.sugerencias("admin") == politica.SUGERENCIAS["admin"]
