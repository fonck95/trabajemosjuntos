"""Los archivos del panel (/static/) se revalidan en cada carga. Sin Cache-Control el navegador reusaba sin preguntar los
módulos que tenía guardados: tras un despliegue juntaba un ui.js viejo con un vistas/personas.js nuevo y la vista no
cargaba («The requested module '../ui.js' does not provide an export named 'fuentesVisibles'»). No usa MongoDB."""
import pytest
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.routing import Mount

from app.config import Config
from app.main import crear_app

CAIDO = "mongodb://127.0.0.1:1/?serverSelectionTimeoutMS=500&connectTimeoutMS=300"


@pytest.fixture
def panel():
    cfg = Config(usuario="admin", clave="clave-de-prueba-larga", mongodb_uri=CAIDO, mongodb_db="prueba_cache",
                 horas_sesion=1, cookie_segura=False, max_subida_mb=5)
    app = crear_app(cfg)
    try:
        yield app
    finally:
        app.state.cliente.close()


@pytest.mark.parametrize("prefijo", ["", "/panel"])
def test_los_modulos_se_revalidan_con_su_etag(panel, prefijo):
    # Solo («») y montado bajo /panel dentro del sitio, como en Railway
    c = TestClient(Starlette(routes=[Mount(prefijo, app=panel)]) if prefijo else panel)
    for archivo in ("js/ui.js", "js/vistas/personas.js", "js/app.js", "css/app.css"):
        r = c.get(f"{prefijo}/static/{archivo}")
        assert r.status_code == 200, archivo
        assert r.headers["cache-control"] == "no-cache", archivo
        etag = r.headers["etag"]
        # Sin cambios, la revalidación es un 304 sin cuerpo que sigue pidiendo revalidar la próxima vez
        r = c.get(f"{prefijo}/static/{archivo}", headers={"If-None-Match": etag})
        assert r.status_code == 304 and not r.content, archivo
        assert r.headers["cache-control"] == "no-cache", archivo


def test_la_api_y_la_pagina_mantienen_su_cache(panel):
    c = TestClient(panel)
    assert c.get("/api/yo").headers["cache-control"] == "no-store"
    assert c.get("/personas").headers["cache-control"] == "no-cache"
