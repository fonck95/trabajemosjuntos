"""Lecturas y frecuencia (3.6): ya no hay tope de personas consultadas por día (un `presupuesto_diario` guardado de
antes no se aplica): P y C consultan sin 429 `volumen` y cada persona queda registrada en `lecturas`. Sigue el 429
`frecuencia` con más de 120 consultas por minuto; A queda registrado y exento.

El mecanismo se prueba sobre una aplicación mínima con `requiere` y `registrar_lecturas`; el recorrido de Habitantes,
el PATCH vacío y `?resumen=1` se prueban cuando existen las rutas del grupo 3."""
import pytest
from fastapi import Depends, FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import acceso, modelo

TOPE = 30


def _mini(app_real):
    mini = FastAPI()
    mini.state.cfg, mini.state.db = app_real.state.cfg, app_real.state.db

    @mini.get("/leer")
    def leer(desde: int, n: int, ficha: bool = False, q: acceso.Quien = Depends(acceso.requiere("personas.buscar"))):
        ids = list(range(desde, desde + n))
        acceso.registrar_lecturas(mini.state.db, q, ids, ficha=ficha)
        return {"ids": ids}

    @mini.get("/limitada")
    def limitada(q: acceso.Quien = Depends(acceso.requiere("personas.buscar", limitar=True))):
        return {"ok": True}

    return mini


def _cliente(app_real, c):
    return TestClient(_mini(app_real), cookies=dict(c.cookies))


def _tope(db, n=TOPE):
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"presupuesto_diario.planillero": n, "presupuesto_diario.consultor": n}},
                       upsert=True)


@pytest.mark.parametrize("rol", ["planillero", "consultor"])
def test_sin_tope_diario_de_personas_distintas(sesion, como, rol):
    db = sesion.app.state.db
    _tope(db)  # un presupuesto guardado de antes: ya no se aplica
    assert acceso.presupuesto(db, rol) is None
    c = como(rol)
    m = _cliente(sesion.app, c)
    dia = modelo.hoy_local().isoformat()
    assert m.get("/leer", params={"desde": 1, "n": 25}).status_code == 200
    assert m.get("/leer", params={"desde": 1, "n": 25, "ficha": True}).status_code == 200  # las mismas no suman
    assert db.lecturas.count_documents({"uid": c.uid, "dia": dia}) == 25
    assert db.lecturas.count_documents({"uid": c.uid, "dia": dia, "ficha": True}) == 25
    # Mucho más allá del tope de antes: todo se sirve y todo queda registrado
    for desde in range(100, 400, 50):
        assert m.get("/leer", params={"desde": desde, "n": 50}).status_code == 200
    assert db.lecturas.count_documents({"uid": c.uid, "dia": dia}) == 25 + 300 > TOPE
    assert db.auditoria.count_documents({"accion": "alerta_volumen", "uid": c.uid}) == 0
    fila = next(u for u in sesion.get("/api/usuarios").json() if u["id"] == c.uid)
    assert "volumen" not in fila["alertas"]
    # Sus sesiones siguen abiertas
    assert c.get("/api/yo").status_code == 200


def test_el_administrador_queda_registrado_sin_tope(sesion):
    db = sesion.app.state.db
    _tope(db, 5)
    m = _cliente(sesion.app, sesion)
    assert m.get("/leer", params={"desde": 1, "n": 50}).status_code == 200
    assert db.lecturas.count_documents({"uid": 0}) == 50
    doc = db.lecturas.find_one({"uid": 0, "pid": 7})
    assert doc["_id"] == f"0|7|{modelo.hoy_local().isoformat()}" and doc["ficha"] is False and doc["ts"]


def test_frecuencia_por_usuario(sesion, como):
    c = como("consultor")
    m = _cliente(sesion.app, c)
    for _ in range(acceso.FRECUENCIA_MAX):
        assert m.get("/limitada").status_code == 200
    r = m.get("/limitada")
    assert r.status_code == 429 and r.json()["detail"]["codigo"] == "frecuencia" and int(r.headers["retry-after"]) >= 1
    # Lo que no está limitado sigue
    assert m.get("/leer", params={"desde": 1, "n": 1}).status_code == 200
    # Otro usuario y el administrador no comparten la ventana; A queda exento
    assert _cliente(sesion.app, como("consultor")).get("/limitada").status_code == 200
    a = _cliente(sesion.app, sesion)
    for _ in range(acceso.FRECUENCIA_MAX + 5):
        assert a.get("/limitada").status_code == 200


def _hay(app, metodo, ruta):
    return any(isinstance(r, APIRoute) and r.path == ruta and metodo in r.methods for r in app.routes)


def test_habitantes_ficha_y_resumen_cuentan(sesion, como):
    """P recorre Habitantes por barrio sin tope diario; un PATCH sin cambios y ?resumen=1 también quedan registrados."""
    if not _hay(sesion.app, "GET", "/api/trabajo"):
        pytest.skip("requiere el grupo 3 (lecturas en Habitantes y la ficha)")
    from conftest import insertar_personas, personas_inventadas
    db = sesion.app.state.db
    _tope(db, 20)
    lugares = [x["_id"] for x in db.lugares.find({}, {"_id": 1}).limit(3)]
    datos = personas_inventadas(45)
    for i, d in enumerate(datos):
        d["lugar_id"] = lugares[i % 3]
        d["consentimiento"] = "si"
    ids = insertar_personas(db, datos)
    p = como("planillero")
    estados = [p.get("/api/personas", params={"lugar_id": l}).status_code for l in lugares]
    assert estados == [200, 200, 200]  # con un presupuesto de 20 guardado de antes: ya no se aplica
    assert p.get("/api/personas", params={"lugar_id": lugares[0]}).status_code == 200
    assert db.lecturas.count_documents({"uid": p.uid}) > 20  # todo lo servido queda registrado
    q = como("planillero")
    for pid in ids[:25]:
        assert q.patch(f"/api/personas/{pid}", json={}).status_code == 200
    assert db.lecturas.count_documents({"uid": q.uid, "ficha": True}) == 25
    a = sesion.get(f"/api/personas/{ids[21]}", params={"resumen": 1})
    assert a.status_code == 200  # A: sin tope
    assert db.lecturas.find_one({"uid": 0, "pid": ids[21]})
