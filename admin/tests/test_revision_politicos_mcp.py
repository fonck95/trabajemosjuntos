"""Revisión adversarial de los datos políticos por MCP (regresiones). Solo datos inventados.

* Una clave sin `lectura` (el coordinador nunca la tiene: leer personas por MCP es sacarlas del panel, como exportar)
  no recibe personas por la analítica: la tabla por `lider` nombra a cada líder (su nombre y si es líder o concejal),
  y eso es entregar personas a un cliente externo. Lo agregado (por tipo, por lista) sí le llega.
* El detalle de una propuesta hecha con `agente_politicos.mcp` encendido no se entrega por `estado_propuesta` si el
  administrador lo apagó después: llevaría el tipo y el «Liderado por» por MCP con el ajuste apagado.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import ayudas_analitica as ya
from ayudas_g3 import autorizada, coordinador, persona
from app.api import mcp


def _ajuste(db, asistente: bool, mcp_: bool) -> None:
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"agente_politicos": {"asistente": asistente, "mcp": mcp_}}},
                       upsert=True)


def _mcp_para_k(db) -> None:
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"agente_mcp": {
        "roles": ["admin", "coordinador"], "escritura": True, "llamadas_diarias": 2000, "personas_diarias": 300}}},
        upsert=True)


def _clave(cli, *alcances) -> str:
    r = cli.post("/api/pantalla/clave", json={"tipo": "datos", "alcances": list(alcances)})
    assert r.status_code == 200, r.text
    return r.json()["clave"]


def _llamar(agente, clave, nombre, argumentos) -> dict:
    r = agente.post("/api/mcp", headers={"Authorization": f"Bearer {clave}"},
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                          "params": {"name": nombre, "arguments": argumentos}})
    assert r.status_code == 200, r.text
    return r.json()["result"]


def _asignado(*ids: int) -> list[dict]:
    return [{"id": i, "asignado_en": "2026-11-01T00:00:00+00:00", "asignado_por": "admin", "asignado_por_uid": 0}
            for i in ids]


@pytest.fixture
def lideres(sesion):
    """Un líder que autorizó con 14 personas traídas (que autorizaron) y 6 personas sin líder."""
    db = sesion.app.state.db
    l1 = ya.persona(db, nombre="LIDER INVENTADO REVISION", lider=True, consentimiento="si", sexo="M")
    ya.personas(db, [{"nombre": f"VOTANTE INVENTADA REVISION {i}", "votante": True, "lideres": _asignado(l1),
                      "consentimiento": "si", "sexo": "F" if i % 2 else "M"} for i in range(14)])
    ya.personas(db, [{"nombre": f"SUELTA INVENTADA REVISION {i}", "consentimiento": "si", "sexo": "F"}
                     for i in range(6)])
    return {"db": db, "l1": l1, "agente": TestClient(sesion.app)}


def test_clave_de_analitica_sin_lectura_no_recibe_lideres_por_nombre(sesion, lideres):
    db, l1, agente = lideres["db"], lideres["l1"], lideres["agente"]
    _mcp_para_k(db)
    k = coordinador(sesion.app, db)
    assert k.post("/api/pantalla/clave", json={"tipo": "datos", "alcances": ["lectura"]}).status_code != 200
    for cli in (k, sesion):  # el coordinador y una clave del administrador sin lectura
        clave = _clave(cli, "analitica")
        res = _llamar(agente, clave, "analizar", {"tipo": "tabla", "dimensiones": ["lider"]})
        texto = res["content"][0]["text"]
        assert res["isError"] is True and json.loads(texto)["error"]["codigo"] == "permiso", texto
        assert "LIDER INVENTADO REVISION" not in texto and str(l1) not in texto
        assert not db.mcp_entregas.find_one({"herramienta": "analizar", "personas": l1})
        # Lo agregado, sin personas, sí le llega
        res = _llamar(agente, clave, "analizar", {"tipo": "tabla", "dimensiones": ["tipo"]})
        assert res["isError"] is False, res
    # Con lectura (solo el administrador), la tabla por líder sí le llega, y el líder cuenta en sus entregas
    clave = _clave(sesion, "analitica", "lectura")
    res = _llamar(agente, clave, "analizar", {"tipo": "tabla", "dimensiones": ["lider"]})
    assert res["isError"] is False, res
    assert l1 in {f["valor"] for f in json.loads(res["content"][0]["text"])["filas"]}
    assert db.mcp_entregas.find_one({"herramienta": "analizar", "personas": l1})


def test_estado_propuesta_no_entrega_lo_politico_con_el_ajuste_mcp_apagado(sesion):
    db = sesion.app.state.db
    l1 = persona(db, nombre="LIDER INVENTADO PROPUESTA", lider=True)
    autorizada(db, l1)
    l2 = persona(db, nombre="CONCEJAL INVENTADO PROPUESTA", concejal=True)
    autorizada(db, l2)
    y = persona(db, nombre="YOLANDA INVENTADA PROPUESTA", votante=True, lideres=_asignado(l2))
    autorizada(db, y)
    agente = TestClient(sesion.app)
    clave = _clave(sesion, "lectura", "escritura")
    _ajuste(db, False, True)
    res = _llamar(agente, clave, "asignar_lider", {"persona_id": y, "lider_id": l1,
                                                    mcp.CAMPO_MOTIVO: "Lo dijo en la reunión del barrio"})
    assert res["isError"] is False, res
    pid = json.loads(res["content"][0]["text"])["propuesta"]
    r = sesion.post(f"/api/mcp/propuestas/{pid}", json={"aprobar": True})
    assert r.status_code == 200 and r.json()["estado"] == "hecha", r.text
    # Con el ajuste encendido, el detalle llega (el tipo y el «Liderado por» de la persona)
    res = _llamar(agente, clave, "estado_propuesta", {"propuesta": pid})
    out = json.loads(res["content"][0]["text"])
    assert out["estado"] == "hecha" and "CONCEJAL INVENTADO PROPUESTA" in out["resultado"], out
    # El administrador apaga los datos políticos por MCP: el detalle guardado ya no sale
    _ajuste(db, True, False)
    res = _llamar(agente, clave, "estado_propuesta", {"propuesta": pid})
    texto = res["content"][0]["text"]
    out = json.loads(texto)
    assert out["estado"] == "hecha" and "resultado" not in out, out
    for vedado in ("CONCEJAL INVENTADO PROPUESTA", "LIDER INVENTADO PROPUESTA", "votante", "lideres"):
        assert vedado not in texto, vedado
    # Encendido otra vez, vuelve a salir
    _ajuste(db, True, True)
    out = json.loads(_llamar(agente, clave, "estado_propuesta", {"propuesta": pid})["content"][0]["text"])
    assert "resultado" in out
