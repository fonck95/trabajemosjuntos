"""Alias de un barrio o vereda (`POST /api/lugares/{lid}/alias`, app/api/calidad.py) y la herramienta
`agregar_alias_lugar`: agrega sin reemplazar la lista (`$addToSet`), reubica solo a las personas sin barrio o vereda
con ese lugar escrito, es idempotente, rechaza un alias que volvería ambiguo el nomenclátor y es solo de A y K. Solo
datos inventados."""
from __future__ import annotations

import pytest

from ayudas_calidad import escribe_una_vez, falla_tarjeta, leer, modelo, tarjeta
from ayudas_calidad import ctx_de  # noqa: F401 (fixture)
from ayudas_g3 import coordinador, persona


def _lugar(db, nombre="TRES DE OCTUBRE", tipo="barrio") -> dict:
    return db.lugares.find_one({"nombre": nombre, "tipo": tipo})


def _sin_lugar(db, nombre: str, texto: str, **extra) -> int:
    return persona(db, nombre=nombre, direccion=f"BARRIO {texto}", lugar_id=None, lugar_texto=texto, **extra)


@pytest.fixture
def espia(monkeypatch):
    """Los ids con que la ruta vuelve a ubicar: nunca toda la base."""
    from app.api import calidad as api
    llamadas = []
    original = api.georreferenciar

    def georreferenciar(db, solo_ids=None):
        llamadas.append(None if solo_ids is None else sorted(solo_ids))
        return original(db, solo_ids)

    monkeypatch.setattr(api, "georreferenciar", georreferenciar)
    return llamadas


def test_la_ruta_agrega_sin_reemplazar_y_reubica_solo_a_esas_personas(sesion, espia):
    db = sesion.app.state.db
    lg = _lugar(db)
    db.lugares.update_one({"_id": lg["_id"]}, {"$set": {"alias": ["TRES OCTUBRE"]}})
    a = _sin_lugar(db, "VECINA INVENTADA UNO", "VILLA INVENTADA")
    b = _sin_lugar(db, "VECINA INVENTADA DOS", "VILLA INVENTADA", consentimiento="no")
    otra = _sin_lugar(db, "VECINA INVENTADA TRES", "OTRO SITIO INVENTADO")
    r = sesion.post(f"/api/lugares/{lg['_id']}/alias", json={"alias": "Villa  inventada"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["nuevo"] is True and d["alias"] == ["TRES OCTUBRE", "VILLA INVENTADA"]
    assert d["personas"] == 2 and d["reconocidas"] == 2 and d["reconocidas_tratables"] == 1
    assert espia == [sorted([a, b])]
    assert db.personas.find_one({"_id": a})["lugar_id"] == lg["_id"]
    assert db.personas.find_one({"_id": otra})["lugar_id"] is None
    assert db.auditoria.count_documents({"accion": "agregar_alias", "entidad_id": lg["_id"]}) == 1
    # Repetirlo no cambia el lugar ni se audita otra vez
    r = sesion.post(f"/api/lugares/{lg['_id']}/alias", json={"alias": "VILLA INVENTADA"})
    assert r.status_code == 200 and r.json()["nuevo"] is False
    assert r.json()["alias"] == ["TRES OCTUBRE", "VILLA INVENTADA"]
    assert db.auditoria.count_documents({"accion": "agregar_alias", "entidad_id": lg["_id"]}) == 1


def test_la_ruta_con_lugar_sin_lista_ambiguo_inexistente_y_permisos(sesion, como):
    db = sesion.app.state.db
    lg = _lugar(db)
    db.lugares.update_one({"_id": lg["_id"]}, {"$unset": {"alias": 1}})
    r = sesion.post(f"/api/lugares/{lg['_id']}/alias", json={"alias": "OCTUBRE TRES"})
    assert r.status_code == 200 and r.json()["alias"] == ["OCTUBRE TRES"]
    otro = db.lugares.find_one({"_id": {"$ne": lg["_id"]}, "tipo": "vereda"})
    r = sesion.post(f"/api/lugares/{lg['_id']}/alias", json={"alias": otro["nombre"].lower()})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "ambiguo"
    assert sesion.post("/api/lugares/999999/alias", json={"alias": "NADA INVENTADO"}).status_code == 404
    assert sesion.post(f"/api/lugares/{lg['_id']}/alias", json={"alias": "--"}).status_code == 422
    k = coordinador(sesion.app, db)
    assert k.post(f"/api/lugares/{lg['_id']}/alias", json={"alias": "TRES DE OCT"}).status_code == 200
    for rol in ("planillero", "consultor"):
        r = como(rol).post(f"/api/lugares/{lg['_id']}/alias", json={"alias": "OTRO INVENTADO"})
        assert r.status_code == 403 and r.json()["detail"]["codigo"] == "permiso", rol


def test_la_herramienta_muestra_el_lugar_y_reubica_una_sola_vez(sesion, ctx_de):
    db = sesion.app.state.db
    lg = _lugar(db)
    a = _sin_lugar(db, "VECINA INVENTADA UNO", "VILLA INVENTADA")
    _sin_lugar(db, "VECINA INVENTADA DOS", "VILLA INVENTADA")
    _sin_lugar(db, "VECINA INVENTADA NO", "VILLA INVENTADA", consentimiento="no")
    sin = modelo(leer(sesion, ctx_de(sesion), "lugares_sin_reconocer", {}))
    assert {"texto": "VILLA INVENTADA", "personas": 2} in [{k: x[k] for k in ("texto", "personas")}
                                                           for x in sin["textos"]]

    def cambia(db):
        assert "VILLA INVENTADA" in db.lugares.find_one({"_id": lg["_id"]})["alias"]
        assert db.personas.find_one({"_id": a})["lugar_id"] == lg["_id"]

    conf, r1, r2 = escribe_una_vez(sesion, ctx_de(sesion), "agregar_alias_lugar",
                                   {"lugar_id": lg["_id"], "texto": "Villa Inventada"}, cambia)
    detalle = dict(conf.detalle)
    assert detalle["Alias nuevo"] == "VILLA INVENTADA" and detalle[
        "Personas con ese lugar escrito y sin barrio o vereda"] == "3"
    out = modelo(r1)
    assert out["reubicadas"] == 2 and out["ya_estaba"] is False and out["lugar"]["id"] == lg["_id"]
    assert modelo(r2)["ya_estaba"] is True and r1.personas == set()
    # Ya está: la tarjeta no se arma otra vez
    assert falla_tarjeta(sesion, ctx_de(sesion), "agregar_alias_lugar",
                         {"lugar_id": lg["_id"], "texto": "VILLA INVENTADA"}).codigo == "sin_cambios"


def test_la_herramienta_rechaza_lo_ambiguo_y_a_planilleros_y_consultores(sesion, como, ctx_de):
    db = sesion.app.state.db
    lg = _lugar(db)
    otro = db.lugares.find_one({"_id": {"$ne": lg["_id"]}, "tipo": "vereda"})
    e = falla_tarjeta(sesion, ctx_de(sesion), "agregar_alias_lugar", {"lugar_id": lg["_id"], "texto": otro["nombre"]})
    assert e.codigo == "ambiguo"
    assert falla_tarjeta(sesion, ctx_de(sesion), "agregar_alias_lugar",
                         {"lugar_id": 999999, "texto": "NADA INVENTADO"}).codigo == "no_existe"
    conf, _ = tarjeta(sesion, ctx_de(coordinador(sesion.app, db)), "agregar_alias_lugar",
                      {"lugar_id": lg["_id"], "texto": "OCTUBRE INVENTADO"})
    assert conf.titulo == f"Agregar un alias a {lg['nombre']}"
    for rol in ("planillero", "consultor"):
        e = falla_tarjeta(sesion, ctx_de(como(rol)), "agregar_alias_lugar",
                          {"lugar_id": lg["_id"], "texto": "OCTUBRE INVENTADO"})
        assert (e.codigo, e.estado) == ("permiso", 403), rol
