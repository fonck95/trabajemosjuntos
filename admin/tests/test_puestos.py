"""Catálogo de puestos de votación (1.4): semilla verificada (DIVIPOL presidencial 2026), reconocimiento desde la base
y API. Solo datos públicos del catálogo y personas inventadas."""
import json

import pytest

from app import db as bd
from app import modelo


def test_semilla_verificada(bases):
    db = bases()
    datos = json.loads(bd.PUESTOS.read_text(encoding="utf-8"))
    assert datos["meta"]["eleccion"] == "2026-presidencial" and datos["meta"]["nombre_registraduria"] == "YONDO-CASABE"
    assert all(f["consultado"] == "2026-11-04" and f["url"].startswith("https://") for f in datos["meta"]["fuentes"])
    ps = list(db.puestos.find({"eleccion": "2026-presidencial"}).sort("codigo", 1))
    assert [p["codigo"] for p in ps] == ["00-01", "00-02", "99-25", "99-32", "99-50", "99-60", "99-65"]
    assert sum(p["mesas"] for p in ps) == 50 and sum(p["habilitados"]["total"] for p in ps) == 16121
    por = {p["codigo"]: p for p in ps}
    assert (por["00-01"]["mesas"], por["00-01"]["habilitados"]) == (35, {"mujeres": 5800, "hombres": 6364, "total": 12164})
    assert por["99-60"]["coord_dudosa"] is True and por["00-02"]["lat"] is None
    assert por["99-65"]["lat"] == 7.08815 and por["99-65"]["lon"] == -73.946147
    assert "EL PORVENIR" not in por["99-50"]["alias"]
    assert por["00-01"]["alias_ambiguos"] == ["CABECERA MUNICIPAL", "PUESTO CABECERA MUNICIPAL"]
    assert db.meta.find_one({"_id": "puestos_sembrados"})


def test_reconocer_contra_el_catalogo_sembrado(bases):
    db = bases()
    ps = bd.puestos_vigentes(db)
    ids = {p["codigo"]: p["_id"] for p in ps}
    assert modelo.reconocer_puesto("SAN MIGUEL DEL TIGRE", ps) == (ids["99-65"], False)
    assert modelo.reconocer_puesto("I.E.R. San Miguel del Tigre", ps) == (ids["99-65"], False)
    assert modelo.reconocer_puesto("CABECERA MUNICIPAL", ps) == (None, True)
    assert modelo.reconocer_puesto("LUIS", ps) == (None, False) and modelo.reconocer_puesto("SAN", ps) == (None, False)
    assert modelo.reconocer_puesto("C.E.R ALTO CIMITARRA", ps) == (ids["99-32"], False)
    assert modelo.reconocer_puesto("SAN FRANCISCO", ps) == (ids["99-32"], False)
    v = modelo.armar_votacion("COLISEO BENITO ARIAS", "Mesa # 5", ps, fuente="planilla", eleccion="2026-presidencial")
    assert v["puesto_id"] == ids["00-02"] and v["mesa"] is None and v["mesa_texto"] == "Mesa # 5"
    assert v["estado"] == "por_confirmar"  # el coliseo tiene 4 mesas
    v = modelo.armar_votacion(None, "Mesa # 9", ps, fuente="cedulas", eleccion=None, estado="por_confirmar")
    assert (v["puesto_id"], v["mesa"], v["mesa_texto"]) == (None, 9, "Mesa # 9")
    assert modelo.derivar_votacion(v) == {"puesto_votacion": None, "mesa": "Mesa # 9"}
    v = modelo.armar_votacion("ESCUELA DE OTRO PUEBLO", 3, ps, fuente="planilla", eleccion="x", municipio="PUERTO BERRIO")
    assert v["donde"] == "otro_municipio" and v["municipio"] == "PUERTO BERRIO" and v["puesto_texto"]
    assert modelo.armar_votacion(None, None, ps, fuente="planilla", eleccion="x") is None


def test_la_semilla_no_pisa_lo_editado_ni_se_repite(bases):
    db = bases()
    db.puestos.update_one({"codigo": "99-25"}, {"$set": {"nombre": "EDITADO A MANO", "editado": True}})
    db.puestos.delete_one({"codigo": "99-50"})
    bd.inicializar(db)
    assert db.puestos.find_one({"codigo": "99-25"})["nombre"] == "EDITADO A MANO"
    assert db.puestos.find_one({"codigo": "99-50"}) is None  # la semilla corre una sola vez


def test_api_de_puestos(sesion):
    c = sesion
    ps = c.get("/api/puestos").json()
    assert len(ps) == 7 and ps[0]["codigo"] == "00-01" and ps[0]["habilitados"]["total"] == 12164
    v0 = c.get("/api/ajustes").json()["catalogos_version"]
    r = c.post("/api/puestos", json={"eleccion": "2027-territoriales", "codigo": "00-01", "nombre": "Puesto inventado",
                                     "mesas": 3, "alias": ["inventado"], "lat": 7.0, "lon": -73.9,
                                     "habilitados": {"mujeres": 10, "hombres": 12}})
    assert r.status_code == 201, r.text
    nuevo = r.json()
    assert nuevo["nombre"] == "PUESTO INVENTADO" and nuevo["alias"] == ["INVENTADO"] and nuevo["habilitados"]["total"] == 22
    assert c.post("/api/puestos", json={"eleccion": "2027-territoriales", "codigo": "00-01", "nombre": "Otro",
                                        "mesas": 1}).status_code == 409
    assert c.post("/api/puestos", json={"codigo": "1-1", "nombre": "Malo", "mesas": 1}).status_code == 422
    assert c.post("/api/puestos", json={"codigo": "00-09", "nombre": "Sin lon", "mesas": 1, "lat": 7.0}).status_code == 422
    r = c.patch(f"/api/puestos/{nuevo['id']}", json={"mesas": 4, "activo": False})
    assert r.status_code == 200 and r.json()["mesas"] == 4 and r.json()["activo"] is False and r.json()["editado"]
    assert c.get("/api/puestos", params={"eleccion": "2027-territoriales"}).json() == []
    assert len(c.get("/api/puestos", params={"eleccion": "2027-territoriales", "todos": 1}).json()) == 1
    assert c.patch("/api/puestos/9999", json={"mesas": 2}).status_code == 404
    assert c.get("/api/ajustes").json()["catalogos_version"] == v0 + 2
    db = c.app.state.db
    assert db.auditoria.count_documents({"accion": {"$in": ["crear_puesto", "editar_puesto"]}}) == 2


def test_consultor_ve_codigo_y_nombre(cliente, como):
    c = como("consultor")
    ps = c.get("/api/puestos").json()
    assert ps and set(ps[0]) == {"id", "codigo", "nombre"}
    assert c.post("/api/puestos", json={"codigo": "00-09", "nombre": "No puede", "mesas": 1}).status_code == 403
    p = como("planillero")
    assert "mesas" in p.get("/api/puestos").json()[0]


@pytest.mark.parametrize("cuerpo", [{"codigo": "00-10", "nombre": "Ab", "mesas": 1},
                                     {"codigo": "00-10", "nombre": "Puesto", "mesas": 0},
                                     {"codigo": "00-10", "nombre": "Puesto", "mesas": 1, "area": "urbana"},
                                     {"codigo": "00-10", "nombre": "Puesto", "mesas": 1, "eleccion": "2027"},
                                     {"codigo": "00-10", "nombre": "Puesto", "mesas": 1, "lugar_id": 99999}])
def test_puesto_invalido(sesion, cuerpo):
    assert sesion.post("/api/puestos", json=cuerpo).status_code == 422
