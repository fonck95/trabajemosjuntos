"""El panel cuando MongoDB falla (cortacircuitos, guardia, límite de concurrencia, reintentos al crear el panel) y la
ruta de la cookie de sesión. Solo datos inventados."""
import asyncio
import logging
import time
from dataclasses import replace

import anyio
import httpx
import pymongo
import pytest
from fastapi.testclient import TestClient
from pymongo.errors import ConfigurationError

from conftest import MONGO, URI

import servidor
from app import config
from app import db as bd
from app import seguridad as seg

CAIDO = "mongodb://127.0.0.1:1/?serverSelectionTimeoutMS=1500&connectTimeoutMS=300"
SRV = "mongodb+srv://usuario-falso:clave-secreta-falsa@cluster0.noexiste.invalid/?connectTimeoutMS=1000"


@pytest.fixture
def sitio(tmp_path):
    d = tmp_path / "site"
    d.mkdir()
    (d / "index.html").write_text("<!doctype html><title>Home</title>HOME-PUBLICO", encoding="utf-8")
    (d / "atlas.html").write_text("<!doctype html><title>Atlas</title>ATLAS-PUBLICO", encoding="utf-8")
    return d


def _esperar(condicion, segundos=15):
    fin = time.time() + segundos
    while time.time() < fin and not condicion():
        time.sleep(0.05)
    assert condicion()


def _avisos(caplog):
    return [x for x in caplog.records if x.name == "panel" and x.levelno >= logging.WARNING]


# ───────────────────────────── Cortacircuitos y guardia ─────────────────────────────

def test_mongodb_caido_responde_503_sin_traza_y_se_cura_solo(sesion, cfg, caplog):
    c, app = sesion, sesion.app
    cc = app.state.cortacircuitos
    cc.pausa_s = 0.5
    buena = app.state.db
    caido = pymongo.MongoClient(CAIDO)
    caplog.set_level(logging.INFO)
    try:
        assert c.get("/api/personas").status_code == 200
        app.state.db = caido[cfg.mongodb_db]
        # En un endpoint (/api/yo: la guardia no consulta la base): el manejador responde 503, no 500
        r = c.get("/api/yo")
        assert r.status_code == 503 and r.headers["retry-after"] == "5" and r.json() == {"detail": seg.SIN_BASE}
        assert r.headers["cache-control"] == "no-store" and "default-src 'self'" in r.headers["content-security-policy"]
        # Durante la pausa, la guardia responde 503 sin tocar MongoDB (tocarlo tardaría 1,5 s por petición)
        t = time.perf_counter()
        for ruta in ("/api/personas", "/api/yo", "/salud"):
            r = c.get(ruta)
            assert r.status_code == 503 and r.headers["retry-after"] == "5", ruta
        assert c.post("/api/login", json={"usuario": "admin", "clave": "x"}).status_code == 503
        assert time.perf_counter() - t < 1.0
        assert c.get("/salud").json()["ok"] is False
        assert c.get("/personas/3").status_code == 200  # la página del panel no depende de MongoDB
        # Pasada la pausa, una sola petición prueba con un ping: sigue caído y empieza otra pausa
        time.sleep(0.6)
        assert c.get("/api/personas").status_code == 503
        assert cc.caido and cc.hasta > time.monotonic()
        # Una línea en el registro por caída: sin traza y sin la dirección de MongoDB
        avisos = _avisos(caplog)
        assert len(avisos) == 1 and "ServerSelectionTimeoutError" in avisos[0].getMessage()
        assert not any(x.exc_info for x in caplog.records) and "127.0.0.1:1" not in caplog.text
        # MongoDB vuelve: pasada la pausa, el panel se cura solo
        app.state.db = buena
        time.sleep(0.6)
        assert c.get("/api/personas").status_code == 200 and not cc.caido
        assert "volvió a responder" in caplog.text
        # Otra caída, ahora en la consulta de la sesión que hace la propia guardia (por fuera del manejador de
        # FastAPI): también 503, no una excepción
        app.state.db = caido[cfg.mongodb_db]
        r = c.get("/api/personas")
        assert r.status_code == 503 and r.headers["retry-after"] == "5"
        assert len(_avisos(caplog)) == 2 and not any(x.exc_info for x in caplog.records)
    finally:
        app.state.db = buena
        caido.close()


def test_salud_y_api_responden_503_al_instante_mientras_conecta(cfg):
    from app.main import crear_app
    app = crear_app(replace(cfg, mongodb_uri="mongodb://127.0.0.1:1/?serverSelectionTimeoutMS=3000"))
    app.state.listo = False  # como dentro del sitio, antes de conectar
    try:
        c = TestClient(app)
        t = time.perf_counter()
        r = c.get("/salud")
        assert r.status_code == 503 and r.headers["retry-after"] == "5" and r.json()["ok"] is False
        assert c.get("/api/personas", headers={"Cookie": f"{seg.COOKIE}=x"}).status_code == 503
        assert time.perf_counter() - t < 1.0  # no esperó a MongoDB
    finally:
        app.state.cliente.close()


def test_tiempos_de_espera_de_mongodb():
    cli, _ = bd.conectar("mongodb://127.0.0.1:1/?socketTimeoutMS=1234", "x")
    try:
        assert cli.options.server_selection_timeout == 2.5
        assert cli.options.pool_options.connect_timeout == 5
        assert cli.options.pool_options.socket_timeout == 1.234  # lo que diga la URI manda
    finally:
        cli.close()
    assert config.sin_credenciales("x mongodb://ana:secreta@h:1/b y ana:secreta@otro") == "x mongodb://h:1/b y otro"


# ───────────────────────────── Límite de concurrencia del panel ─────────────────────────────

def _app_lenta(segundos):
    async def app(scope, receive, send):
        await asyncio.sleep(segundos)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})
    return app


def test_limite_del_panel_responde_503_sin_cupo():
    async def probar():
        limite = servidor.LimitePanel(_app_lenta(0.5), cupos=2, espera_s=0.2)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=limite), base_url="http://t") as c:
            rs = await asyncio.gather(*(c.get("/api/x") for _ in range(3)))
            assert sorted(r.status_code for r in rs) == [200, 200, 503]
            r = next(r for r in rs if r.status_code == 503)
            assert r.headers["retry-after"] == "2" and r.text == servidor.OCUPADO
            # Al terminar, los cupos se devuelven
            assert (await c.get("/api/x")).status_code == 200
    asyncio.run(probar())


def test_el_panel_no_acapara_los_hilos_del_sitio(cfg, sitio, monkeypatch):
    """MongoDB colgado: cada petición del panel retiene un hilo. El sitio público, que usa el mismo grupo de hilos
    para sus archivos, debe seguir respondiendo al instante."""
    monkeypatch.setattr(servidor, "CUPOS_PANEL", 3)
    monkeypatch.setattr(servidor, "ESPERA_CUPO_S", 0.3)

    def colgada(db, request):
        time.sleep(1.5)
        return None
    monkeypatch.setattr(seg, "sesion_actual", colgada)
    app = servidor.crear_servidor(cfg, sitio)
    app.state.panel.state.listo = True

    async def probar():
        anyio.to_thread.current_default_thread_limiter().total_tokens = 6  # en vez de 40, para no esperar tanto
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            panel = [asyncio.create_task(c.get("/panel/api/personas", headers={"Cookie": f"{seg.COOKIE}=x"}))
                     for _ in range(15)]
            await asyncio.sleep(0.1)
            t = time.perf_counter()
            assert (await c.get("/")).status_code == 200 and (await c.get("/atlas")).status_code == 200
            sitio_s = time.perf_counter() - t
            estados = sorted(r.status_code for r in await asyncio.gather(*panel))
        return sitio_s, estados

    try:
        sitio_s, estados = asyncio.run(probar())
    finally:
        app.state.panel.state.cliente.close()
    assert sitio_s < 0.5, sitio_s
    assert estados == [401] * 3 + [503] * 12


# ───────────────────────────── Reintentos al crear el panel ─────────────────────────────

def test_srv_sin_dns_reintenta_sin_mostrar_la_uri(cfg, sitio, monkeypatch, caplog):
    monkeypatch.setattr(servidor, "ESPERA_S", (0.05, 0.1))
    llamadas = []
    original = servidor.cargar_panel

    def contar(c=None):
        llamadas.append(1)
        return original(c)
    monkeypatch.setattr(servidor, "cargar_panel", contar)
    app = servidor.crear_servidor(replace(cfg, mongodb_uri=SRV), sitio)
    assert app.state.panel is None
    with TestClient(app) as c:
        _esperar(lambda: len(llamadas) >= 3)
        assert c.get("/").status_code == 200 and c.get("/health").status_code == 200
        r = c.get("/panel/")
        assert r.status_code == 503 and r.headers["retry-after"] == "60" and "Volver al sitio" in r.text
        assert "clave-secreta" not in r.text and "usuario-falso" not in r.text and "noexiste" not in r.text
        assert c.get("/panel/api/yo").status_code == 503
    assert "clave-secreta" not in caplog.text and "usuario-falso" not in caplog.text
    assert app.state.panel is None


def test_falta_de_configuracion_no_se_reintenta(sitio, monkeypatch):
    monkeypatch.setattr(servidor, "ESPERA_S", (0.05, 0.1))
    llamadas = []

    def sin_uri():
        llamadas.append(1)
        raise RuntimeError("Falta la variable MONGODB_URI en el servicio del panel")
    monkeypatch.setattr(config, "cargar", sin_uri)
    app = servidor.crear_servidor(None, sitio)
    with TestClient(app) as c:
        time.sleep(0.4)
        r = c.get("/panel/")
        assert r.status_code == 503 and "MONGODB_URI" in r.text and "retry-after" not in r.headers
    assert len(llamadas) == 1


@pytest.mark.skipif(not MONGO, reason="No hay MongoDB para las pruebas del servidor")
def test_el_panel_se_monta_solo_cuando_el_dns_responde(cfg, sitio, monkeypatch):
    monkeypatch.setattr(servidor, "ESPERA_S", (0.05, 0.1))
    real, fallos = bd.conectar, []

    def conectar(uri, nombre=None):
        if len(fallos) < 2:  # el DNS de Atlas todavía no responde
            fallos.append(uri)
            raise ConfigurationError("The DNS query name does not exist: _mongodb._tcp.cluster0.noexiste.invalid.")
        return real(URI, nombre)
    monkeypatch.setattr(bd, "conectar", conectar)
    app = servidor.crear_servidor(replace(cfg, mongodb_uri=SRV), sitio)
    try:
        with TestClient(app) as c:
            assert c.get("/panel/").status_code == 503
            _esperar(lambda: app.state.panel is not None and app.state.panel.state.listo)
            assert len(fallos) == 2
            r = c.get("/panel/personas/1")
            assert r.status_code == 200 and '<meta name="panel-base" content="/panel">' in r.text
            assert c.get("/panel/api/yo").status_code == 401
            assert c.post("/panel/api/login", json={"usuario": cfg.usuario, "clave": cfg.clave}).status_code == 200
            assert c.get("/panel/api/yo").status_code == 200
    finally:
        with pymongo.MongoClient(URI) as m:
            m.drop_database(cfg.mongodb_db)


# ───────────────────────────── Ruta de la cookie de sesión ─────────────────────────────

def _cookies_de_sesion(r):
    return [v for k, v in r.headers.multi_items() if k == "set-cookie" and v.startswith(f"{seg.COOKIE}=")]


def test_cookie_de_sesion_en_el_panel_solo(sesion):
    c = sesion
    r = c.post("/api/login", json={"usuario": "admin", "clave": "clave-de-prueba-larga"})
    (nueva,) = _cookies_de_sesion(r)
    assert "Path=/;" in nueva or nueva.endswith("Path=/")
    c.headers["X-CSRF-Token"] = r.json()["csrf"]
    r = c.post("/api/logout")
    (borrada,) = _cookies_de_sesion(r)
    assert "Max-Age=0" in borrada and ("Path=/;" in borrada or borrada.endswith("Path=/"))
    assert c.get("/api/yo").status_code == 401


@pytest.mark.skipif(not MONGO, reason="No hay MongoDB para las pruebas del servidor")
def test_cookie_de_sesion_solo_viaja_al_panel(cfg, sitio):
    app = servidor.crear_servidor(cfg, sitio)
    try:
        with TestClient(app) as c:
            _esperar(lambda: app.state.panel.state.listo)
            # Una cookie vieja con Path=/ (de antes de este cambio) con una sesión que ya no vale
            c.cookies.set(seg.COOKIE, "vieja", domain="testserver.local", path="/")
            r = c.post("/panel/api/login", json={"usuario": cfg.usuario, "clave": cfg.clave})
            assert r.status_code == 200
            nueva, = [v for v in _cookies_de_sesion(r) if "Max-Age=0" not in v]
            assert "Path=/panel/" in nueva and "HttpOnly" in nueva and "SameSite=strict" in nueva
            vieja, = [v for v in _cookies_de_sesion(r) if "Max-Age=0" in v]
            assert "Path=/;" in vieja or vieja.endswith("Path=/")  # la vieja se borra
            assert [(k.name, k.path) for k in c.cookies.jar if k.name == seg.COOKIE] == [(seg.COOKIE, "/panel/")]
            # El sitio público no la recibe; el panel sí
            for ruta in ("/", "/atlas"):
                assert seg.COOKIE not in c.get(ruta).request.headers.get("cookie", ""), ruta
            assert c.get("/panel/api/yo").status_code == 200
            c.headers["X-CSRF-Token"] = r.json()["csrf"]
            assert c.post("/panel/api/reuniones", json={"titulo": "Prueba", "fecha": "2026-11-01"}).status_code == 201
            r = c.post("/panel/api/logout")
            assert r.status_code == 200
            assert any("Path=/panel/" in v and "Max-Age=0" in v for v in _cookies_de_sesion(r))
            assert not [k for k in c.cookies.jar if k.name == seg.COOKIE]
            assert c.get("/panel/api/yo").status_code == 401
    finally:
        with pymongo.MongoClient(URI) as m:
            m.drop_database(cfg.mongodb_db)
