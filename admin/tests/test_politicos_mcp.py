"""Los datos políticos por MCP (decisión del dueño: ya no se le ocultan a un agente externo con la clave de la persona):
con `agente_politicos.mcp` encendido, las lecturas (clave `lectura`, solo A) llevan el tipo, el «Liderado por», las
listas y la lista de líderes, y las escrituras (A y K) proponen marcar un tipo o asignar un líder; apagado, como antes.
Manda el ajuste `mcp`, no el del asistente, también al aprobar una propuesta en Mi cuenta. Solo datos inventados."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from ayudas_g3 import autorizada, persona
from app.api import mcp


def _ajuste(db, asistente: bool, mcp_: bool) -> None:
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"agente_politicos": {"asistente": asistente, "mcp": mcp_}}},
                       upsert=True)


def _clave(sesion, *alcances) -> str:
    r = sesion.post("/api/pantalla/clave", json={"tipo": "datos", "alcances": list(alcances)})
    assert r.status_code == 200, r.text
    return r.json()["clave"]


def _rpc(agente, clave, metodo, params=None) -> dict:
    r = agente.post("/api/mcp", headers={"Authorization": f"Bearer {clave}"},
                    json={"jsonrpc": "2.0", "id": 1, "method": metodo, **({"params": params} if params else {})})
    assert r.status_code == 200, r.text
    return r.json()


def _llamar(agente, clave, nombre, argumentos) -> dict:
    return _rpc(agente, clave, "tools/call", {"name": nombre, "arguments": argumentos})["result"]


def _ok(res) -> dict:
    assert res["isError"] is False, res
    return json.loads(res["content"][0]["text"])


def _nombres(agente, clave) -> set[str]:
    return {h["name"] for h in _rpc(agente, clave, "tools/list")["result"]["tools"]}


def _asignado(*ids: int) -> list[dict]:
    return [{"id": i, "asignado_en": "2026-11-01T00:00:00+00:00", "asignado_por": "admin", "asignado_por_uid": 0}
            for i in ids]


@pytest.fixture
def mundo(sesion):
    db = sesion.app.state.db
    l1 = persona(db, nombre="LIDER INVENTADO MCP", lider=True)
    autorizada(db, l1)
    l2 = persona(db, nombre="CONCEJAL INVENTADO NOAUTORIZA MCP", concejal=True, consentimiento="no")
    x = persona(db, nombre="XIMENA INVENTADA MCP", votante=True, lideres=_asignado(l1, l2),
                listas=["Lista Inventada M1"], sensibles={"etnia": "Raizal"})
    autorizada(db, x)
    y = persona(db, nombre="YOLANDA INVENTADA MCP")
    autorizada(db, y)
    return {"db": db, "l1": l1, "l2": l2, "x": x, "y": y, "agente": TestClient(sesion.app)}


def test_instrucciones_y_herramientas_segun_el_ajuste_mcp(sesion, mundo):
    db, agente = mundo["db"], mundo["agente"]
    lectura = _clave(sesion, "lectura", "escritura")
    _ajuste(db, False, True)
    inicio = _rpc(agente, lectura, "initialize")["result"]["instructions"]
    assert mcp.CON_POLITICOS in inicio and mcp.SIN_POLITICOS not in inicio and "{politicos}" not in inicio
    assert {"lideres", "marcar_tipo", "asignar_lider"} <= _nombres(agente, lectura)
    _ajuste(db, True, False)
    inicio = _rpc(agente, lectura, "initialize")["result"]["instructions"]
    assert mcp.SIN_POLITICOS in inicio and mcp.CON_POLITICOS not in inicio
    assert not {"lideres", "marcar_tipo", "asignar_lider"} & _nombres(agente, lectura)
    assert _rpc(agente, lectura, "tools/call", {"name": "lideres", "arguments": {}})["error"]["code"] == -32602


def test_las_lecturas_llevan_lo_politico_solo_con_el_ajuste_mcp(sesion, mundo):
    db, agente, x, l1 = mundo["db"], mundo["agente"], mundo["x"], mundo["l1"]
    clave = _clave(sesion, "lectura")
    _ajuste(db, False, True)  # el del asistente no cuenta por MCP
    f = _ok(_llamar(agente, clave, "ver_persona", {"persona_id": x}))
    assert f["votante"] is True and f["listas"] == ["Lista Inventada M1"]
    assert f["lideres"] == [{"id": l1, "nombre": "LIDER INVENTADO MCP", "tipo": "lider", "marcado": True}]
    texto = json.dumps(f, ensure_ascii=False)
    assert "CONCEJAL" not in texto and "Raizal" not in texto
    # El líder nombrado cuenta como persona entregada a la clave
    entrega = db.mcp_entregas.find_one({"herramienta": "ver_persona"})
    assert set(entrega["personas"]) == {x, l1}
    lista = _ok(_llamar(agente, clave, "buscar_personas", {"filtros": {"tipo": "votante"}}))
    assert [r["id"] for r in lista["filas"]] == [x] and lista["filas"][0]["votante"] is True
    lideres = _ok(_llamar(agente, clave, "lideres", {}))
    assert [r["id"] for r in lideres["lideres"]] == [l1] and lideres["lideres"][0]["traidas"] == 1
    # Apagado por MCP (aunque el asistente lo tenga encendido): como antes
    _ajuste(db, True, False)
    f = _ok(_llamar(agente, clave, "ver_persona", {"persona_id": x}))
    assert not {"votante", "lider", "lideres", "listas"} & set(f)
    res = _llamar(agente, clave, "buscar_personas", {"filtros": {"tipo": "votante"}})
    assert res["isError"] is True and json.loads(res["content"][0]["text"])["error"]["codigo"] == "permiso"


def test_proponer_y_aprobar_un_lider_por_mcp_con_su_ajuste(sesion, mundo):
    db, agente, y, l1 = mundo["db"], mundo["agente"], mundo["y"], mundo["l1"]
    clave = _clave(sesion, "escritura")
    _ajuste(db, False, True)
    d = _ok(_llamar(agente, clave, "asignar_lider", {"persona_id": y, "lider_id": l1,
                                                      mcp.CAMPO_MOTIVO: "Lo dijo en la reunión del barrio"}))
    assert d["estado"] == "pendiente" and "propuesta" in d
    prop = db.mcp_propuestas.find_one({"_id": d["propuesta"]})
    assert {y, l1} <= set(prop["personas"])  # el líder de la tarjeta queda anotado (supresión)
    assert db.personas.find_one({"_id": y}).get("lideres") in (None, [])  # nada sin aprobar
    # Quien aprueba usa la sesión del navegador, pero manda el ajuste de MCP (el del asistente está apagado)
    r = sesion.post(f"/api/mcp/propuestas/{d['propuesta']}", json={"aprobar": True})
    assert r.status_code == 200 and r.json()["estado"] == "hecha", r.text
    assert [x["id"] for x in db.personas.find_one({"_id": y})["lideres"]] == [l1]
    # Con el de MCP apagado, una propuesta pendiente ya no se ejecuta
    d = _ok(_llamar(agente, clave, "marcar_tipo", {"persona_id": y, "tipos": ["votante"],
                                                    mcp.CAMPO_MOTIVO: "Dijo que vota por la campaña"}))
    _ajuste(db, True, False)
    r = sesion.post(f"/api/mcp/propuestas/{d['propuesta']}", json={"aprobar": True})
    assert r.status_code == 200 and r.json()["estado"] == "fallida" and r.json()["error"]["codigo"] == "permiso"
    assert db.personas.find_one({"_id": y}).get("votante") is not True
