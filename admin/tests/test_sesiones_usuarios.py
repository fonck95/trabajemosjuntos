"""Sesiones atadas al usuario (3.3): limpieza al arrancar, credencial de .env, sesiones viejas sin uid, inactividad,
máximo de sesiones, duración, relleno de uid en la auditoría y el arranque con una migración fallida."""
import logging
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pymongo
import pytest
from fastapi.testclient import TestClient

from app import db as bd
from app import migraciones
from app import seguridad as seg
from conftest import CLAVE_USUARIO, MONGO, URI


def _entrar(app, usuario, clave=CLAVE_USUARIO):
    c = TestClient(app)
    r = c.post("/api/login", json={"usuario": usuario, "clave": clave})
    assert r.status_code == 200, r.text
    c.headers["X-CSRF-Token"] = r.json()["csrf"]
    return c


def _ahora():
    return datetime.now(timezone.utc)


def test_limpieza_al_iniciar(sesion, como, cfg):
    db = sesion.app.state.db
    p, k = como("planillero"), como("consultor")
    db.usuarios.update_one({"_id": k.uid}, {"$set": {"activo": False}})
    futuro = _ahora() + timedelta(hours=1)
    db.sesiones.insert_many([
        {"_id": "de-un-uid-que-no-existe", "uid": 999, "huella": "x", "expira": futuro},
        {"_id": "de-otra-version", "uid": p.uid, "huella": seg.huella_usuario(cfg, {"_id": p.uid, "version": 0}), "expira": futuro},
        {"_id": "admin-de-otra-credencial", "uid": 0, "huella": "otra", "expira": futuro},
        {"_id": "admin-vieja-sin-uid", "huella": "otra", "expira": futuro},
    ])
    seg.limpiar_al_iniciar(db, cfg)
    assert db.sesiones.count_documents({"uid": k.uid}) == 0  # inactivo: todas
    assert not db.sesiones.find_one({"_id": {"$in": ["de-un-uid-que-no-existe", "de-otra-version",
                                                     "admin-de-otra-credencial", "admin-vieja-sin-uid"]}})
    assert p.get("/api/yo").status_code == 200 and sesion.get("/api/yo").status_code == 200  # las vigentes siguen


def test_cambiar_la_credencial_de_env_cierra_las_sesiones_de_usuarios(sesion, como, cfg):
    from app.main import crear_app
    db = sesion.app.state.db
    p = como("planillero")
    cookie = {"Cookie": f"{seg.COOKIE}={p.cookies.get(seg.COOKIE)}"}
    otra = crear_app(replace(cfg, clave="otra-clave-totalmente-distinta"))
    try:
        assert TestClient(otra).get("/api/yo", headers=cookie).status_code == 401
        assert TestClient(otra).get("/api/catalogos", headers=cookie).status_code == 401
        with TestClient(otra):  # al arrancar con la credencial nueva se borran
            pass
        assert db.sesiones.count_documents({"uid": p.uid}) == 0
    finally:
        otra.state.cliente.close()
    # Con la credencial nueva, el usuario vuelve a entrar con su clave (la suya no cambió)
    otra = crear_app(replace(cfg, clave="otra-clave-totalmente-distinta"))
    try:
        assert TestClient(otra).post("/api/login", json={"usuario": p.usuario, "clave": CLAVE_USUARIO}).status_code == 200
    finally:
        otra.state.cliente.close()


def test_sesiones_viejas_sin_uid_son_del_administrador(sesion, cfg):
    db = sesion.app.state.db
    ahora = _ahora()
    db.sesiones.insert_many([
        {"_id": seg._hash("token-viejo-inventado"), "usuario": cfg.usuario, "csrf": "csrf-viejo", "huella": seg.huella(cfg),
         "creada": ahora, "expira": ahora + timedelta(hours=1)},
        {"_id": seg._hash("token-viejo-de-otra-clave"), "usuario": cfg.usuario, "csrf": "c", "huella": "otra",
         "creada": ahora, "expira": ahora + timedelta(hours=1)},
    ])
    c = TestClient(sesion.app)
    h = {"Cookie": f"{seg.COOKIE}=token-viejo-inventado"}
    yo = c.get("/api/yo", headers=h).json()
    assert (yo["uid"], yo["rol"], yo["usuario"]) == (0, "admin", cfg.usuario) and yo["permisos"] == ["*"]
    assert c.get("/api/usuarios", headers=h).status_code == 200
    assert c.post("/api/etiquetas", json={"nombre": "Etiqueta inventada"}, headers={**h, "X-CSRF-Token": "csrf-viejo"}).status_code == 201
    assert c.get("/api/yo", headers={"Cookie": f"{seg.COOKIE}=token-viejo-de-otra-clave"}).status_code == 401


def test_inactividad(sesion, como):
    db = sesion.app.state.db
    c = como("consultor")
    assert c.get("/api/catalogos").status_code == 200
    db.sesiones.update_many({"uid": c.uid}, {"$set": {"ultima_actividad": _ahora() - timedelta(minutes=61)}})
    assert c.get("/api/catalogos").status_code == 401
    assert db.sesiones.count_documents({"uid": c.uid}) == 0
    # Con 120 minutos en Ajustes, 61 minutos sin uso no la cierran
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"sesion.inactividad_min": 120}}, upsert=True)
    d = _entrar(sesion.app, c.usuario)
    db.sesiones.update_many({"uid": c.uid}, {"$set": {"ultima_actividad": _ahora() - timedelta(minutes=61)}})
    assert d.get("/api/catalogos").status_code == 200
    # El uso la renueva, como mucho una vez por minuto
    s = db.sesiones.find_one({"uid": c.uid})
    assert _ahora() - s["ultima_actividad"] < timedelta(seconds=30)
    marca = s["ultima_actividad"]
    assert d.get("/api/yo").status_code == 200
    assert db.sesiones.find_one({"uid": c.uid})["ultima_actividad"] == marca
    # La del administrador no tiene inactividad
    db.sesiones.update_many({"uid": 0}, {"$set": {"ultima_actividad": _ahora() - timedelta(hours=5)}})
    assert sesion.get("/api/yo").status_code == 200


def test_maximo_dos_sesiones_por_usuario(sesion, como):
    db = sesion.app.state.db
    c1 = como("planillero")
    c2 = _entrar(sesion.app, c1.usuario)
    c3 = _entrar(sesion.app, c1.usuario)
    assert db.sesiones.count_documents({"uid": c1.uid}) == 2
    assert c1.get("/api/yo").status_code == 401  # la más vieja se cerró
    assert c2.get("/api/yo").status_code == 200 and c3.get("/api/yo").status_code == 200
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"sesion.max_por_usuario": 1}}, upsert=True)
    c4 = _entrar(sesion.app, c1.usuario)
    assert db.sesiones.count_documents({"uid": c1.uid}) == 1 and c4.get("/api/yo").status_code == 200
    # Las del administrador no tienen tope
    _entrar(sesion.app, "admin", sesion.app.state.cfg.clave)
    _entrar(sesion.app, "admin", sesion.app.state.cfg.clave)
    assert db.sesiones.count_documents({"uid": 0}) >= 3


def test_las_sesiones_de_usuarios_duran_10_horas(cfg):
    if not MONGO:
        pytest.skip("No hay MongoDB para las pruebas de la API")
    from app.main import crear_app
    from conftest import crear_usuario
    app = crear_app(replace(cfg, horas_sesion=24))
    try:
        with TestClient(app) as c:
            u = crear_usuario(app.state.db, "consultor")
            r = c.post("/api/login", json={"usuario": u["usuario"], "clave": CLAVE_USUARIO}).json()
            duracion = datetime.fromisoformat(r["expira"]) - _ahora()
            assert timedelta(hours=9, minutes=59) < duracion <= timedelta(hours=10)
            r = c.post("/api/login", json={"usuario": cfg.usuario, "clave": cfg.clave}).json()
            assert datetime.fromisoformat(r["expira"]) - _ahora() > timedelta(hours=23)  # el administrador: .env
            # Con un tope menor en Ajustes manda el menor
            app.state.db.meta.update_one({"_id": "ajustes"}, {"$set": {"sesion.horas_max": 2}}, upsert=True)
            r = c.post("/api/login", json={"usuario": u["usuario"], "clave": CLAVE_USUARIO}).json()
            assert datetime.fromisoformat(r["expira"]) - _ahora() <= timedelta(hours=2)
    finally:
        with pymongo.MongoClient(URI) as m:
            m.drop_database(cfg.mongodb_db)


def test_relleno_de_uid_en_la_auditoria(sesion, cfg):
    db = sesion.app.state.db
    db.auditoria.insert_many([
        {"ts": bd.ahora(), "usuario": cfg.usuario, "accion": "editar_viejo"},
        {"ts": bd.ahora(), "usuario": "sistema", "accion": "importar_viejo"},
        {"ts": bd.ahora(), "usuario": cfg.usuario, "uid": 7, "rol": "planillero", "accion": "ya_tenia_uid"},
    ])
    seg.limpiar_al_iniciar(db, cfg)
    a = db.auditoria.find_one({"accion": "editar_viejo"})
    assert (a["uid"], a["rol"]) == (0, "admin")
    assert "uid" not in db.auditoria.find_one({"accion": "importar_viejo"})
    assert db.auditoria.find_one({"accion": "ya_tenia_uid"})["uid"] == 7
    # El ingreso de hoy ya va con uid y rol
    i = db.auditoria.find_one({"accion": "ingreso"})
    assert (i["uid"], i["rol"]) == (0, "admin")


def test_arranque_con_la_migracion_fallida(cfg, monkeypatch, caplog):
    if not MONGO:
        pytest.skip("No hay MongoDB para las pruebas de la API")
    from app import main

    def falla(db):
        raise migraciones.ErrorMigracion("paso 2: índice inventado")
    monkeypatch.setattr(main.db, "inicializar", falla)
    app = main.crear_app(cfg)
    try:
        with caplog.at_level(logging.ERROR, logger="panel"), pytest.raises(migraciones.ErrorMigracion):
            main.preparar(app)
        assert "No se pudo migrar la base de datos: paso 2: índice inventado" in caplog.text
        assert "MONGODB_URI" not in caplog.text and not getattr(app.state, "listo", False)
    finally:
        app.state.cliente.close()
