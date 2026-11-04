"""Insignias del menú (5.4): conteos livianos por rol. Solo datos inventados."""
from ayudas_g3 import contactable, coordinador, persona, tomar


def test_insignias_por_rol(sesion, como, monkeypatch):
    from app.api import acercamientos as ac
    monkeypatch.setattr(ac, "fuera_de_horario", lambda *a, **k: False)
    db = sesion.app.state.db
    l1, l2 = [x["_id"] for x in db.lugares.find({}, {"_id": 1}).limit(2)]
    req = {"motivo": "no_contesta", "uid": None, "usuario": None, "ts": "2026-11-01T00:00:00+00:00", "nota": None}
    persona(db, nombre="VICENTA INVENTADA UNO", lugar_id=l1, requiere_actualizacion=req)
    persona(db, nombre="VICENTA INVENTADA DOS", lugar_id=l2, requiere_actualizacion=req)
    persona(db, nombre="VICENTA INVENTADA TRES", lugar_id=l1, requiere_actualizacion=req,
            situacion={"estado": "fallecida", "confirmada": False})
    db.conflictos_cedula.insert_one({"_id": 1, "estado": "pendiente", "motivo": "dictada"})
    db.solicitudes.insert_one({"_id": 1, "estado": "pendiente", "tipo": "consulta"})
    esperado = {"calidad": 0, "conflictos": 1, "solicitudes": 1, "situaciones": 1, "trabajo": 2}
    assert sesion.get("/api/insignias").json() == esperado
    assert coordinador(sesion.app, db).get("/api/insignias").json() == esperado
    p = como("planillero", asignacion={"lugares": [l1], "areas": []})
    assert p.get("/api/insignias").json() == {"calidad": 0, "conflictos": 0, "solicitudes": 0, "situaciones": 0,
                                              "trabajo": 1}
    c = como("consultor")
    assert c.get("/api/insignias").json()["trabajo"] == 0
    pid = contactable(db, "VICENTA INVENTADA CUATRO", "3008880001")
    tomar(c, pid)
    c.post(f"/api/personas/{pid}/acercamientos", json={"canal": "llamada", "telefono_indice": 0,
                                                       "resultado": "volver_llamar", "proximo": "2020-01-01"})
    assert c.get("/api/insignias").json()["trabajo"] == 1
