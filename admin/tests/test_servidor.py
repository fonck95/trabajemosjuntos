"""Servidor único de Railway: sitio público en la raíz, panel en /panel/ y el sitio en línea aunque el panel falle.

Solo datos inventados."""
import time

import pytest
from fastapi.testclient import TestClient

from conftest import MONGO

import servidor


@pytest.fixture
def sitio(tmp_path):
    d = tmp_path / "site"
    (d / "js").mkdir(parents=True)
    (d / "index.html").write_text("<!doctype html><title>Home</title><p>HOME-PUBLICO</p>" + "x" * 3000, encoding="utf-8")
    (d / "atlas.html").write_text("<!doctype html><title>Atlas</title>ATLAS-PUBLICO", encoding="utf-8")
    (d / "js" / "a.js").write_text("console.log(1)", encoding="utf-8")
    return d


def _esperar_panel(app, segundos=15):
    fin = time.time() + segundos
    while time.time() < fin and not getattr(app.state.panel.state, "listo", False):
        time.sleep(0.05)
    assert app.state.panel.state.listo


@pytest.fixture
def servido(cfg, sitio):
    if not MONGO:
        pytest.skip("No hay MongoDB para las pruebas del servidor")
    app = servidor.crear_servidor(cfg, sitio)
    try:
        with TestClient(app) as c:
            _esperar_panel(app)
            yield c
    finally:
        import pymongo
        from conftest import URI
        with pymongo.MongoClient(URI) as m:
            m.drop_database(cfg.mongodb_db)


def test_sitio_publico_como_caddy(servido):
    c = servido
    r = c.get("/")
    assert r.status_code == 200 and "HOME-PUBLICO" in r.text
    assert "content-security-policy" not in r.headers  # el visor 3D carga texturas blob:
    assert r.headers["x-content-type-options"] == "nosniff" and "server" not in r.headers
    assert c.get("/atlas").text.endswith("ATLAS-PUBLICO") and c.get("/atlas.html").status_code == 200
    assert c.get("/js/a.js").status_code == 200
    assert c.get("/no-existe").status_code == 404
    assert c.get("/", headers={"Accept-Encoding": "gzip"}).headers.get("content-encoding") == "gzip"
    assert c.get("/health").text == "ok"


def test_panel_bajo_el_prefijo(servido, cfg):
    c = servido
    r = c.get("/panel", follow_redirects=False)
    assert r.status_code == 308 and r.headers["location"] == "/panel/"
    r = c.get("/panel/personas/12")  # rutas del navegador: devuelven la aplicación con el prefijo
    assert r.status_code == 200 and '<meta name="panel-base" content="/panel">' in r.text
    assert '"/panel/static/js/app.js"' in r.text and '"/static/' not in r.text
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert c.get("/panel/static/js/base.js").status_code == 200
    assert c.get("/panel/api/yo").status_code == 401
    # Sin sesión, la API se corta antes de leer el cuerpo, también bajo el prefijo
    assert c.post("/panel/api/importar", content=b"x" * 2048, headers={"Content-Type": "application/octet-stream"}).status_code == 401
    r = c.post("/panel/api/login", json={"usuario": cfg.usuario, "clave": cfg.clave})
    assert r.status_code == 200
    assert "path=/panel/api/login" in r.headers["set-cookie"].lower().replace("; ", ";").replace(";", "; ")
    assert c.get("/panel/api/personas").headers["cache-control"] == "no-store"
    assert c.post("/panel/api/reuniones", json={"titulo": "Prueba", "fecha": "2026-11-01"}).status_code == 403  # sin CSRF
    c.headers["X-CSRF-Token"] = r.json()["csrf"]
    assert c.post("/panel/api/reuniones", json={"titulo": "Prueba", "fecha": "2026-11-01"}).status_code == 201


def test_sitio_en_linea_aunque_mongodb_no_responda(cfg, sitio):
    from dataclasses import replace
    caido = replace(cfg, mongodb_uri="mongodb://127.0.0.1:1/?serverSelectionTimeoutMS=200&connectTimeoutMS=200")
    app = servidor.crear_servidor(caido, sitio)
    with TestClient(app) as c:
        assert c.get("/").status_code == 200 and c.get("/health").status_code == 200
        r = c.get("/panel/api/yo")
        assert r.status_code == 503 and r.headers["retry-after"] == "5"
        assert c.get("/panel/").status_code == 200  # la página carga y muestra el aviso al intentar ingresar


def test_sitio_en_linea_aunque_falte_la_configuracion_del_panel(sitio, monkeypatch):
    from app import config

    def sin_uri():
        raise RuntimeError("Falta la variable MONGODB_URI en el servicio del panel")
    monkeypatch.setattr(config, "cargar", sin_uri)
    app = servidor.crear_servidor(None, sitio)
    with TestClient(app) as c:
        assert c.get("/").status_code == 200 and c.get("/health").status_code == 200
        r = c.get("/panel/")
        assert r.status_code == 503 and "MONGODB_URI" in r.text and "Volver al sitio" in r.text
