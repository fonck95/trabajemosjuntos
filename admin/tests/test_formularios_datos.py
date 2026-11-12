"""Llenar los datos de una persona sin pasos de más: la edad sale de la fecha de nacimiento (solo se escribe si no se
sabe la fecha) y la cédula se escribe una vez. Sin MongoDB: el navegador abre los formularios del panel sin sesión."""
import json
import re
import shutil
import socket
import subprocess
import threading
import time
from datetime import date
from pathlib import Path

import pytest
import uvicorn

from test_agente_mapa import requiere_navegador

RAIZ = Path(__file__).resolve().parents[1]
VISTAS = RAIZ / "web" / "js" / "vistas"

# (fecha de nacimiento, hoy): años cumplidos, 29 de febrero, el día antes del cumpleaños, fechas que no existen o futuras
CASOS_EDAD = [
    ("1990-06-15", "2026-06-14"), ("1990-06-15", "2026-06-15"), ("1990-06-15", "2026-11-11"), ("2000-02-29", "2025-02-28"),
    ("2000-02-29", "2025-03-01"), ("2008-11-12", "2026-11-11"), ("2008-11-11", "2026-11-11"), ("1985-02-30", "2026-01-01"),
    ("1990-13-01", "2026-01-01"), ("2027-01-01", "2026-11-11"), ("", "2026-11-11"), ("15/06/1990", "2026-11-11"),
]


def _edad_servidor(nac: str, hoy: str):
    """Lo que calcula el servidor (`modelo.edad_efectiva` con fecha de nacimiento)."""
    from app import modelo
    return modelo.edad_efectiva({"fecha_nacimiento": nac}, date.fromisoformat(hoy)) if modelo.fecha_valida(nac) else None


@pytest.mark.skipif(shutil.which("node") is None, reason="sin Node para cargar web/js/modelo.js")
def test_la_edad_del_navegador_es_la_del_servidor():
    codigo = ("import { edadDesde } from './web/js/modelo.js';"
              f"console.log(JSON.stringify({json.dumps(CASOS_EDAD)}.map(([n, h]) => edadDesde(n, h))));")
    r = subprocess.run(["node", "--input-type=module", "-e", codigo], cwd=RAIZ, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [_edad_servidor(n, h) for n, h in CASOS_EDAD]
    assert json.loads(r.stdout)[:7] == [35, 36, 36, 24, 25, 17, 18]


def test_ningun_formulario_pide_la_cedula_dos_veces():
    for f in ("comunes.js", "ficha.js", "acercamiento.js", "calidad.js"):
        texto = (VISTAS / f).read_text(encoding="utf-8")
        assert not re.search(r"cedula_confirmacion|Repita (el número|la cédula)|cédula correcta dos veces", texto), f


GUION = r"""// Uso: node <guion> <url del panel>. Abre «Nueva persona» y guarda dos veces (la API se responde aquí).
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const [base] = process.argv.slice(2);
(async () => {
  const b = await chromium.launch();
  const page = await b.newPage();
  const errores = [], altas = [];
  page.on('pageerror', (e) => errores.push(e.message));
  await page.route('**/api/personas', async (r) => {
    if (r.request().method() !== 'POST') return r.continue();
    altas.push(r.request().postDataJSON());
    await r.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ id: altas.length }) });
  });
  await page.goto(base + '/', { waitUntil: 'networkidle' });
  const abrir = () => page.evaluate(async () => {
    const m = await import(new URL('vistas/comunes.js', document.querySelector('script[type=module]').src).href);
    m.formularioNuevaPersona({ cat: { lugares: [], puestos: [], etiquetas: [] }, alCrear() {} });
  });
  const edad = () => page.$eval('#f-nueva [name=edad]', (x) => ({ valor: x.value, soloLectura: x.readOnly }));
  const guardar = async () => {
    const n = altas.length;
    await page.check('#f-nueva [name=aut_estado][value=no]', { force: true });
    await page.click('#guardar');
    await page.waitForFunction((n) => !document.querySelector('#f-nueva'), n, { timeout: 10000 });
  };
  const v = {};
  await abrir();
  v.campos_documento = await page.$$eval('#f-nueva [name^=cedula]', (xs) => xs.map((x) => x.name));
  await page.fill('#f-nueva [name=nombre]', 'Persona Inventada De Prueba');
  await page.fill('#f-nueva [name=cedula]', '1234567');
  await page.fill('#f-nueva [name=edad]', '40');
  v.escrita = await edad();
  await page.fill('#f-nueva [name=fecha_nacimiento]', '1990-06-15');
  v.con_fecha = await edad();
  await page.fill('#f-nueva [name=fecha_nacimiento]', '');
  v.sin_fecha = await edad();
  await page.fill('#f-nueva [name=fecha_nacimiento]', '1990-06-15');
  await guardar();
  // Quien solo sabe cuántos años tiene
  await abrir();
  await page.fill('#f-nueva [name=nombre]', 'Otra Persona Inventada');
  await page.fill('#f-nueva [name=edad]', '52');
  await guardar();
  v.altas = altas.map((a) => ({ cedula: a.cedula, fecha_nacimiento: a.fecha_nacimiento, edad: a.edad, claves: Object.keys(a) }));
  v.errores = errores;
  console.log(JSON.stringify(v));
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
"""


@pytest.fixture(scope="module")
def panel_sin_base():
    """El panel en un puerto libre sin MongoDB ni arranque: sirve la página y sus módulos (la API no responde)."""
    from app.config import Config
    from app.main import crear_app
    cfg = Config(usuario="admin", clave="clave-de-prueba-larga", mongodb_uri="mongodb://127.0.0.1:1/?serverSelectionTimeoutMS=300",
                 mongodb_db="prueba_formularios", horas_sesion=1, cookie_segura=False, max_subida_mb=5)
    app = crear_app(cfg)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    srv = uvicorn.Server(uvicorn.Config(app, http="h11", lifespan="off", log_level="warning", access_log=False))
    hilo = threading.Thread(target=srv.run, kwargs={"sockets": [sock]}, daemon=True)
    hilo.start()
    try:
        fin = time.time() + 15
        while time.time() < fin and not srv.started:
            time.sleep(0.05)
        assert srv.started, "el panel no arrancó"
        yield f"http://127.0.0.1:{sock.getsockname()[1]}"
    finally:
        srv.should_exit = True
        hilo.join(10)
        sock.close()
        app.state.cliente.close()


@requiere_navegador
def test_la_edad_se_calcula_y_la_cedula_va_una_vez(panel_sin_base, tmp_path):
    (tmp_path / "formulario.cjs").write_text(GUION, encoding="utf-8")
    r = subprocess.run(["node", str(tmp_path / "formulario.cjs"), panel_sin_base], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, (r.stdout[-3000:], r.stderr[-3000:])
    v = json.loads(r.stdout.strip().splitlines()[-1])
    assert v["errores"] == []
    assert v["campos_documento"] == ["cedula", "cedula_verificada"]  # un solo número, sin «Repita el número»
    # La edad escrita cede a la calculada con la fecha (de solo lectura) y vuelve al borrar la fecha
    from app.modelo import hoy_local
    hoy = hoy_local()  # la de Colombia, como `edadDesde` en el navegador
    anios = hoy.year - 1990 - ((hoy.month, hoy.day) < (6, 15))
    assert v["escrita"] == {"valor": "40", "soloLectura": False}
    assert v["con_fecha"] == {"valor": str(anios), "soloLectura": True}
    assert v["sin_fecha"] == {"valor": "40", "soloLectura": False}
    # Con fecha se envía solo la fecha (el servidor calcula la edad); sin fecha, la edad
    con_fecha, solo_edad = v["altas"]
    assert con_fecha["cedula"] == "1234567" and con_fecha["fecha_nacimiento"] == "1990-06-15" and "edad" not in con_fecha["claves"]
    assert "cedula_confirmacion" not in con_fecha["claves"]
    assert solo_edad["edad"] == 52 and "fecha_nacimiento" not in solo_edad["claves"]
