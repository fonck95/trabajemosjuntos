"""Integración: pendientes del seguimiento del endurecimiento que tocan al grupo 2. GET /api/yo pasa una cookie de
sesión vieja (Path=/) a la ruta del panel sin pedir la clave. Solo datos inventados."""
import time

import pymongo
import pytest
from fastapi.testclient import TestClient

import servidor
from app import seguridad as seg
from conftest import MONGO, URI


@pytest.fixture
def sitio(tmp_path):
    d = tmp_path / "site"
    d.mkdir()
    (d / "index.html").write_text("<!doctype html><title>Inicio</title>INICIO-INVENTADO", encoding="utf-8")
    (d / "atlas.html").write_text("<!doctype html><title>Atlas</title>ATLAS-INVENTADO", encoding="utf-8")
    return d


def _esperar(condicion, segundos=15):
    fin = time.time() + segundos
    while time.time() < fin and not condicion():
        time.sleep(0.05)
    assert condicion()


def _cookies_de_sesion(r):
    return [v for k, v in r.headers.multi_items() if k == "set-cookie" and v.startswith(f"{seg.COOKIE}=")]


@pytest.mark.skipif(not MONGO, reason="No hay MongoDB para las pruebas del servidor")
def test_yo_migra_la_cookie_vieja_a_la_ruta_del_panel(cfg, sitio):
    app = servidor.crear_servidor(cfg, sitio)
    try:
        with TestClient(app) as c:
            _esperar(lambda: app.state.panel.state.listo)
            r = c.post("/panel/api/login", json={"usuario": cfg.usuario, "clave": cfg.clave})
            assert r.status_code == 200
            token = c.cookies.get(seg.COOKIE)
            # El navegador tenía la sesión en una cookie de antes, con Path=/
            c.cookies.clear()
            c.cookies.set(seg.COOKIE, token, domain="testserver.local", path="/")
            assert seg.COOKIE in c.get("/atlas").request.headers.get("cookie", "")
            r = c.get("/panel/api/yo")
            assert r.status_code == 200 and r.json()["usuario"] == cfg.usuario
            vieja, = [v for v in _cookies_de_sesion(r) if "Max-Age=0" in v]
            assert "Path=/;" in vieja or vieja.endswith("Path=/")
            nueva, = [v for v in _cookies_de_sesion(r) if "Max-Age=0" not in v]
            assert nueva.startswith(f"{seg.COOKIE}={token};")  # el mismo token: no pide la clave
            assert "Path=/panel/" in nueva and "HttpOnly" in nueva and "SameSite=strict" in nueva
            edad = int(nueva.split("Max-Age=")[1].split(";")[0])
            assert 0 < edad <= cfg.horas_sesion * 3600  # no alarga la sesión
            assert [(k.name, k.path, k.value) for k in c.cookies.jar if k.name == seg.COOKIE] == \
                [(seg.COOKIE, "/panel/", token)]
            # El sitio público ya no la recibe y el panel sigue con la misma sesión
            for ruta in ("/", "/atlas"):
                assert seg.COOKIE not in c.get(ruta).request.headers.get("cookie", ""), ruta
            assert c.get("/panel/api/yo").status_code == 200
            # Sin sesión válida no se emite nada
            c.cookies.clear()
            c.cookies.set(seg.COOKIE, "inventada", domain="testserver.local", path="/")
            r = c.get("/panel/api/yo")
            assert r.status_code == 401 and not _cookies_de_sesion(r)
    finally:
        with pymongo.MongoClient(URI) as m:
            m.drop_database(cfg.mongodb_db)


def test_yo_con_el_panel_solo_no_toca_la_cookie(sesion):
    r = sesion.get("/api/yo")
    assert r.status_code == 200 and not _cookies_de_sesion(r)
