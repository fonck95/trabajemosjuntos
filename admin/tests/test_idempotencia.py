"""Idempotencia (3.6): con `Idempotency-Key`, un POST repetido devuelve la respuesta guardada sin repetir efectos;
mientras la primera sigue en curso responde 409 `en_proceso`; si la primera falla, la clave se libera.

El mecanismo se prueba sobre una aplicación mínima con `requiere` e `idempotencia_*`; el acercamiento repetido, cuando
existe la ruta del grupo 3."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import acceso


def _mini(app_real):
    mini = FastAPI()
    db = app_real.state.db
    mini.state.cfg, mini.state.db = app_real.state.cfg, db

    @mini.post("/sumar", status_code=201)
    def sumar(request: Request, falla: int = 0, guardar: int = 1,
              q: acceso.Quien = Depends(acceso.requiere("personas.telefonos"))):
        previa = acceso.idempotencia_previa(db, q, request)
        if previa is not None:
            return previa
        n = db.contadores.find_one_and_update({"_id": "prueba_sumas"}, {"$inc": {"n": 1}}, upsert=True,
                                              return_document=True)["n"]
        if falla:
            raise HTTPException(422, "Falla inventada")
        cuerpo = {"n": n, "quien": q.uid}
        if guardar:
            acceso.idempotencia_guardar(db, q, request, 201, cuerpo, persona_id=77)
        return cuerpo

    @mini.post("/otra")
    def otra(request: Request, q: acceso.Quien = Depends(acceso.requiere("personas.telefonos"))):
        return acceso.idempotencia_previa(db, q, request) or {"ok": True}

    return mini


def _sumas(db):
    return (db.contadores.find_one({"_id": "prueba_sumas"}) or {}).get("n", 0)


def _cliente(app_real, c):
    m = TestClient(_mini(app_real), cookies=dict(c.cookies))
    m.headers["X-CSRF-Token"] = c.headers["X-CSRF-Token"]
    return m


def test_la_misma_clave_no_repite_efectos(sesion, como):
    db = sesion.app.state.db
    c = como("consultor")
    m = _cliente(sesion.app, c)
    clave = {"Idempotency-Key": "clave-inventada-0001"}
    a = m.post("/sumar", headers=clave)
    b = m.post("/sumar", headers=clave)
    assert a.status_code == b.status_code == 201 and a.json() == b.json() == {"n": 1, "quien": c.uid}
    assert b.headers.get("idempotency-replayed") == "true" and _sumas(db) == 1
    doc = db.idempotencia.find_one({"_id": f"{c.uid}:clave-inventada-0001"})
    assert (doc["estado"], doc["codigo"], doc["persona_id"], doc["ruta"]) == ("hecho", 201, 77, "POST /sumar")
    assert isinstance(doc["ts"], datetime)
    # Sin la cabecera se comporta como siempre; otra clave es otra acción
    assert m.post("/sumar").json()["n"] == 2 and m.post("/sumar").json()["n"] == 3
    assert m.post("/sumar", headers={"Idempotency-Key": "clave-inventada-0002"}).json()["n"] == 4
    # La clave es de cada usuario: otro usuario con la misma clave hace lo suyo
    assert _cliente(sesion.app, como("consultor")).post("/sumar", headers=clave).json()["n"] == 5
    # Usada en otra acción, o mal formada: 422
    assert m.post("/otra", headers=clave).status_code == 422
    assert m.post("/sumar", headers={"Idempotency-Key": "corta"}).status_code == 422
    assert m.post("/sumar", headers={"Idempotency-Key": "con espacios no vale"}).status_code == 422


def test_en_curso_responde_409(sesion, como):
    db = sesion.app.state.db
    c = como("planillero")
    m = _cliente(sesion.app, c)
    ahora = datetime.now(timezone.utc)
    db.idempotencia.insert_one({"_id": f"{c.uid}:clave-en-curso-01", "ruta": "POST /sumar", "estado": "en_curso",
                                "codigo": None, "respuesta": None, "persona_id": None, "ts": ahora})
    r = m.post("/sumar", headers={"Idempotency-Key": "clave-en-curso-01"})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "en_proceso" and _sumas(db) == 0
    # Una «en curso» de hace minutos quedó perdida (el proceso se cayó): se procesa
    db.idempotencia.update_one({"_id": f"{c.uid}:clave-en-curso-01"}, {"$set": {"ts": ahora - timedelta(minutes=5)}})
    r = m.post("/sumar", headers={"Idempotency-Key": "clave-en-curso-01"})
    assert r.status_code == 201 and _sumas(db) == 1


def test_si_la_primera_falla_la_clave_se_libera(sesion, como):
    db = sesion.app.state.db
    m = _cliente(sesion.app, como("planillero"))
    clave = {"Idempotency-Key": "clave-que-falla-01"}
    assert m.post("/sumar", headers=clave, params={"falla": 1}).status_code == 422
    assert db.idempotencia.count_documents({}) == 0
    r = m.post("/sumar", headers=clave)
    assert r.status_code == 201 and r.json()["n"] == 2
    # Una ruta que responde sin guardar tampoco deja la clave tomada
    clave = {"Idempotency-Key": "clave-sin-guardar-1"}
    assert m.post("/sumar", headers=clave, params={"guardar": 0}).status_code == 201
    assert m.post("/sumar", headers=clave, params={"guardar": 0}).json()["n"] == 4
    assert db.idempotencia.count_documents({"estado": "en_curso"}) == 0


def test_el_administrador_tambien(sesion):
    db = sesion.app.state.db
    m = _cliente(sesion.app, sesion)
    clave = {"Idempotency-Key": "clave-de-admin-001"}
    assert m.post("/sumar", headers=clave).json() == m.post("/sumar", headers=clave).json() == {"n": 1, "quien": 0}
    assert db.idempotencia.find_one({"_id": "0:clave-de-admin-001"})["estado"] == "hecho"


def test_acercamiento_repetido_deja_un_documento(sesion, como):
    if not any(isinstance(r, APIRoute) and r.path == "/api/personas/{pid}/acercamientos" and "POST" in r.methods
               for r in sesion.app.routes):
        pytest.skip("requiere el grupo 3 (acercamientos)")
    from conftest import insertar_personas
    db = sesion.app.state.db
    pid = insertar_personas(db, [{"nombre": "ZOILA INVENTADA PEREZ", "telefono": "3001112233", "consentimiento": "si"}])[0]
    clave = {"Idempotency-Key": "acercamiento-inventado-1"}
    cuerpo = {"canal": "visita", "resultado": "no_contesto"}
    a = sesion.post(f"/api/personas/{pid}/acercamientos", json=cuerpo, headers=clave)
    b = sesion.post(f"/api/personas/{pid}/acercamientos", json=cuerpo, headers=clave)
    assert a.status_code == b.status_code and a.status_code < 300, a.text
    assert db.acercamientos.count_documents({"persona_id": pid}) == 1
    assert (db.personas.find_one({"_id": pid}).get("abordaje") or {}).get("intentos_sin_exito") == 1
    db.idempotencia.insert_one({"_id": "0:acercamiento-en-curso", "ruta": f"POST /api/personas/{pid}/acercamientos",
                                "estado": "en_curso", "ts": datetime.now(timezone.utc)})
    r = sesion.post(f"/api/personas/{pid}/acercamientos", json=cuerpo, headers={"Idempotency-Key": "acercamiento-en-curso"})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "en_proceso"
