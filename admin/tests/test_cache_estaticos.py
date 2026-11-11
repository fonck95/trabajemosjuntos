"""Los archivos del panel (/static/) se revalidan en cada carga. Sin Cache-Control el navegador reusaba sin preguntar los
módulos que tenía guardados: tras un despliegue juntaba un ui.js viejo con un vistas/personas.js nuevo y la vista no
cargaba («The requested module '../ui.js' does not provide an export named 'fuentesVisibles'»). No usa MongoDB."""
import re

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


@pytest.mark.parametrize("prefijo", ["", "/panel"])
def test_la_pagina_pide_sus_archivos_bajo_la_version(panel, prefijo):
    """Los módulos se importan con rutas relativas: si app.js va bajo /static/<versión>/, ui.js y las vistas también.
    Tras un despliegue las rutas son otras y ninguna caché (del navegador o de un proxy) tiene un ui.js viejo."""
    from app.main import VERSION
    c = TestClient(Starlette(routes=[Mount(prefijo, app=panel)]) if prefijo else panel)
    pagina = c.get(f"{prefijo}/personas").text
    assert f'<script type="module" src="{prefijo}/static/{VERSION}/js/app.js"></script>' in pagina
    # Todo lo que la página pide de /static/ (estilos, ícono, app.js) va bajo la versión
    pedidos = re.findall(r'(?:src|href)="([^"]*/static/[^"]+)"', pagina)
    assert len(pedidos) >= 5 and all(u.startswith(f"{prefijo}/static/{VERSION}/") for u in pedidos), pedidos
    for archivo in ("js/ui.js", "js/vistas/personas.js", "css/app.css", "img/icono.svg"):
        actual = c.get(f"{prefijo}/static/{archivo}")
        versionado = c.get(f"{prefijo}/static/{VERSION}/{archivo}")
        assert versionado.status_code == 200 and versionado.content == actual.content, archivo
        assert versionado.headers["cache-control"] == "no-cache", archivo
    # Una pestaña abierta antes del despliegue pide sus vistas con la versión anterior: recibe las de ahora, no un 404
    vieja = c.get(f"{prefijo}/static/v-000000000000/js/vistas/personas.js")
    assert vieja.status_code == 200 and vieja.content == c.get(f"{prefijo}/static/js/vistas/personas.js").content
    for ruta in ("v-000000000000/", "v-123/js/ui.js", "V-000000000000/js/ui.js", "otra/js/ui.js"):
        assert c.get(f"{prefijo}/static/{ruta}").status_code == 404, ruta


def test_la_version_sigue_al_contenido(tmp_path):
    from app.main import huella_web
    (tmp_path / "js").mkdir()
    (tmp_path / "js" / "ui.js").write_text("export const a = 1;", encoding="utf-8")
    (tmp_path / "index.html").write_text("<!doctype html>", encoding="utf-8")
    v = huella_web(tmp_path)
    assert v.startswith("v-") and len(v) == 14 and v == huella_web(tmp_path)
    (tmp_path / "js" / "ui.js").write_text("export const b = 1;", encoding="utf-8")  # mismo tamaño, otro contenido
    assert huella_web(tmp_path) != v
