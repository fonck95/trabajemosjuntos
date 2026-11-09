"""El asistente del panel en un navegador de verdad (Chromium con Playwright): escritorio (1400 × 900), celular
(390 × 844, táctil) y celular chico (320 × 568). Datos inventados; nunca se llama a Anthropic ni a Mnemo.

* `test_widget_sigue_el_protocolo`: las rutas /api/agente/* se contestan desde el navegador (`route.fulfill`) con un
  turno que trae cada tipo de evento (inicio, progreso, texto con Markdown, enlaces permitidos y no permitidos, un
  `<img onerror>`, herramienta, descartar, latido, una línea rota, un evento desconocido, navegar a una ruta del panel
  y a otra que no es, confirmar y fin). Se revisa lo pintado, la aprobación (POST /confirmaciones con la decisión),
  recargar e insignias, el contexto que se manda, el historial (abrir y borrar), Escape y el foco, Mayús+Enter,
  «Reintentar» tras un 503 (reusa la burbuja), la sesión vencida (el diálogo de ingreso del panel y el reintento solo),
  lo guardado en la pestaña (y que vuelve al recargar) y que cerrar sesión lo borra. En el celular: que se pliega al
  navegar, que el botón no tapa la barra de la ficha ni el título de la barra y que «Cerrar sesión» se alcanza con el
  menú abierto. En todos: sin XSS, sin errores de consola, sin violaciones de CSP, sin desborde horizontal y el panel
  dentro de la ventana. Además:
  - `sin_modelo`: el administrador sin modelo (Mnemo sin conectar, con la conexión caída o sin permiso para usar sus
    modelos) ve el botón y adentro qué hacer, sin nombres de variables y con un enlace a Ajustes, que muestra la
    conexión con sus botones.
  - `mnemo`: con Mnemo como modelo, `texto_ronda` reemplaza el texto que llegó por partes; la conexión caída vuelve a
    leer el estado; `proveedor` (409) ofrece «Nueva conversación» con el mensaje escrito; `mnemo_creditos` no ofrece
    «Reintentar»; `llm_peticion` ofrece «Nueva conversación». Quien no es el administrador y se queda sin modelo a
    mitad ve qué pasó, sin que el panel se cierre de golpe. El contexto no lleva `code`, `state` ni `iss`.
* `test_flujo_real_por_partes_y_detener`: contra el núcleo de verdad (uvicorn, el panel en /panel y la Messages API
  simulada con pausas): el texto llega y se pinta por partes (el primer párrafo conserva su nodo mientras llega el
  resto), «Detener» corta el turno y el siguiente mensaje funciona (el servidor soltó el candado).
* `test_flujo_real_con_el_modelo_de_mnemo`: contra el núcleo de verdad con Mnemo como modelo (falso, sin red): el texto
  adelantado que no es el comienzo del final se reemplaza (`texto_ronda`) y la herramienta queda entre las rondas.
* `test_conectar_mnemo_desde_ajustes`: el flujo OAuth entero contra un Mnemo falso servido por red en otro sitio
  (`OAuthFalso` de ayudas_mcp.py en `http://localhost`, el panel en `127.0.0.1`), con una página de permisos como la de
  Mnemo: «Conectar con Mnemo» va a Mnemo con `location.assign`; «Cancelar» vuelve con `error` y no conecta nada;
  «Permitir» vuelve a `/panel/ajustes?code=…&state=…&iss=…` SIN la cookie de sesión (SameSite=Strict, navegación de
  otro sitio), la página quita eso de la dirección antes del POST a /volver (que sí lleva la cookie) y muestra
  «Conectado como …». El coordinador ve el estado sin botones; volver a conectar sin el permiso de los modelos lo
  avisa; «Desconectar» (con confirmación) revoca con el token de renovación.

Corre con uvicorn de verdad (el TestClient junta toda la respuesta) y un guion de Node, como test_servidor.py. Se
salta si no hay Node con Playwright, salvo en el CI (allí falla en vez de pasar en silencio).
"""
import html
import json
import os
import shutil
import socket
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, urlsplit

import pymongo
import pytest
import uvicorn

from conftest import CLAVE_USUARIO, MONGO, URI, crear_usuario, insertar_personas, personas_inventadas


def _hay_playwright() -> bool:
    return bool(shutil.which("node")) and subprocess.run(
        ["node", "-e", "require(process.env.PLAYWRIGHT_MODULE || 'playwright')"], capture_output=True).returncode == 0


requiere_navegador = pytest.mark.skipif(not _hay_playwright() and not os.environ.get("CI"),
                                        reason="Sin Node con Playwright (PLAYWRIGHT_MODULE o NODE_PATH)")


@contextmanager
def _servir(cfg, tmp_path, envolver=None):
    """El servidor único de verdad (uvicorn h11, el panel en /panel, como en Railway) en un puerto libre de 127.0.0.1,
    con tres personas inventadas. `envolver(app)` pone algo delante (un registro de las peticiones). Da (base del
    panel, app del panel, ids de las personas, lo que devolvió `envolver` o None)."""
    if not MONGO:
        pytest.skip("No hay MongoDB para las pruebas con navegador")
    import servidor
    sitio = tmp_path / "site"
    sitio.mkdir()
    (sitio / "index.html").write_text("<!doctype html><title>Inicio</title>INICIO", encoding="utf-8")
    app = servidor.crear_servidor(cfg, sitio)
    delante = envolver(app) if envolver else None
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    srv = uvicorn.Server(uvicorn.Config(delante or app, http="h11", lifespan="on", log_level="warning",
                                        access_log=False, server_header=False, timeout_graceful_shutdown=2))
    hilo = threading.Thread(target=srv.run, kwargs={"sockets": [sock]}, daemon=True)
    hilo.start()
    try:
        fin = time.time() + 20
        while time.time() < fin and not (srv.started and app.state.panel is not None and app.state.panel.state.listo):
            time.sleep(0.05)
        assert srv.started and app.state.panel is not None, "el servidor no arrancó"
        ids = insertar_personas(app.state.panel.state.db, personas_inventadas(3, semilla=41))
        yield f"http://127.0.0.1:{sock.getsockname()[1]}/panel", app.state.panel, ids, delante
    finally:
        srv.should_exit = True
        hilo.join(15)
        sock.close()
        with pymongo.MongoClient(URI) as m:
            m.drop_database(cfg.mongodb_db)


@pytest.fixture
def panel_vivo(cfg, tmp_path):
    """El panel de verdad (`_servir`): (base del panel, app del panel, ids de las personas)."""
    with _servir(cfg, tmp_path) as (base, panel, ids, _):
        yield base, panel, ids


def _correr(guion: str, tmp_path, *args: str) -> dict:
    (tmp_path / "agente.cjs").write_text(guion, encoding="utf-8")
    capturas = os.environ.get("CAPTURAS_AGENTE") or str(tmp_path)  # para mirarlas a mano
    r = subprocess.run(["node", str(tmp_path / "agente.cjs"), *args, capturas], capture_output=True, text=True,
                       timeout=300)
    assert r.returncode == 0, (r.stdout[-3000:], r.stderr[-3000:])
    res = json.loads(r.stdout.strip().splitlines()[-1])
    if os.environ.get("CAPTURAS_AGENTE"):
        (Path(capturas) / f"resultado-{args[3]}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1),
                                                                   encoding="utf-8")
    return res


def _revisar(caso: dict) -> None:
    malas = {k: v for k, v in caso["revisiones"].items() if v is not True}
    assert not malas, (caso["nombre"], malas, caso.get("datos"))
    assert caso["errores"] == [], (caso["nombre"], caso["errores"])
    assert caso["csp"] == [], (caso["nombre"], caso["csp"])


@requiere_navegador
def test_widget_sigue_el_protocolo(panel_vivo, cfg, tmp_path):
    base, _, ids = panel_vivo
    res = _correr(GUION, tmp_path, base, cfg.usuario, cfg.clave, "protocolo", str(ids[1]))
    assert [c["nombre"] for c in res["casos"]] == ["escritorio", "movil", "chico", "sin_modelo", "mnemo"]
    for caso in res["casos"]:
        _revisar(caso)
        if caso["nombre"] == "sin_modelo":
            # El estado lo leyeron la vista y el widget, tres veces; ningún mensaje
            assert caso["mensajes"] == [] and caso["lecturas"] >= 6, caso["lecturas"]
            continue
        if caso["nombre"] == "mnemo":
            mensajes = caso["mensajes"]
            assert len(mensajes) == 6 and all(m["csrf"] for m in mensajes)
            # El contexto solo lleva los filtros conocidos: nada de lo que trae la vuelta de Mnemo
            ctx = mensajes[0]["cuerpo"]["contexto"]
            assert ctx["ruta"] == "/reuniones" and ctx["filtros"] == {"zona": "rural"}, ctx
            assert [m["cuerpo"]["conversacion"] for m in mensajes] == [None, 51, 51, None, 52, 52]
            # «Nueva conversación» trajo escrito el mensaje que no llegó (409 proveedor)
            assert mensajes[3]["cuerpo"]["texto"] == mensajes[2]["cuerpo"]["texto"] == "¿Y las reuniones de mañana?"
            assert caso["lecturas"] >= 4  # al cargar dos veces y tras cada mnemo_conexion
            continue
        # Lo que el navegador le mandó al servidor
        primero, segundo = caso["mensajes"][:2]
        assert len(caso["mensajes"]) == (6 if caso["nombre"] == "escritorio" else 2)  # + reintento y reingreso
        assert primero["cuerpo"]["conversacion"] is None and primero["cuerpo"]["texto"] == TEXTO_XSS
        assert primero["cuerpo"]["contexto"]["ruta"] == "/" and primero["cuerpo"]["contexto"]["vista"] == "panel"
        assert primero["csrf"], "el flujo manda el token CSRF"
        assert segundo["cuerpo"]["conversacion"] == 41
        ctx = segundo["cuerpo"]["contexto"]
        assert ctx["ruta"] == "/personas" and ctx["vista"] == "personas" and ctx["filtros"]["zona"] == "rural", ctx
        assert caso["confirmaciones"] == [{"conversacion": 41, "decisiones": [{"id": "toolu_2", "aprobar": True}]}]


@requiere_navegador
def test_flujo_real_por_partes_y_detener(panel_vivo, cfg, tmp_path, monkeypatch):
    from ayudas_agente import T, con_herramientas, encender_lento, herramientas_falsas, sse
    base, panel, ids = panel_vivo
    con_herramientas(monkeypatch, herramientas_falsas()[0])
    encender_lento(panel,
                   sse(T("Primer párrafo de la respuesta."), T("\n\nSegundo párrafo, que llega después."),
                       T(" Y un final.")),
                   sse(*[T(f"Parte {i}. ") for i in range(30)]),
                   sse(T("De nada.")), pausa=0.15)
    res = _correr(GUION, tmp_path, base, cfg.usuario, cfg.clave, "real", str(ids[1]))
    (caso,) = res["casos"]
    _revisar(caso)
    d = caso["datos"]
    assert d["respuesta"] == "Primer párrafo de la respuesta.\n\nSegundo párrafo, que llega después. Y un final."
    # Por partes: el primer texto se ve mucho antes del final, y el primer párrafo no se rehízo al llegar el resto
    assert d["primero_ms"] < d["total_ms"] - 600, d


@requiere_navegador
def test_flujo_real_con_el_modelo_de_mnemo(panel_vivo, cfg, tmp_path, monkeypatch):
    """Contra el núcleo de verdad con Mnemo como modelo (`encender_mnemo`: la conexión y `mnemo_model_complete`
    falsas, sin red): lo adelantado por `notifications/progress` que no es el comienzo del texto final se reemplaza
    (`texto_ronda`), lo que sí lo es se completa, y la herramienta del panel queda entre las dos rondas."""
    from pydantic import BaseModel, Field

    from ayudas_agente import R, T, TU, con_herramientas, encender_mnemo
    from app.agente.herramientas.base import Herramienta, Resultado

    class Lugar(BaseModel):
        lugar: str = Field(..., min_length=1, max_length=80)

    async def contar(ctx, a: Lugar):
        return Resultado({"total": 3, "lugar": a.lugar}, resumen="3 personas")

    base, panel, ids = panel_vivo
    con_herramientas(monkeypatch, [Herramienta("contar_simple", "Cuenta personas de un lugar (prueba).", Lugar,
                                               "lectura", ("personas.buscar",), "Contando personas", contar)])
    modelo = encender_mnemo(panel,
                            R(T("Hola, mundo."), avance=["Hola, mundi"]),
                            R(T("Voy a contar."), TU("toolu_m1", "contar_simple", {"lugar": "La Paz"}), stop="tool_use",
                              avance=["Voy a contr"]),
                            R(T("Hay 3 personas en La Paz."), avance=[]))
    res = _correr(GUION, tmp_path, base, cfg.usuario, cfg.clave, "real_mnemo", str(ids[1]))
    (caso,) = res["casos"]
    _revisar(caso)
    assert len(modelo.pedidos) == 3, modelo.pedidos


TEXTO_XSS = '<img src=x onerror="window.__xss=1"> ¿Quiénes viven en Tres de Octubre?'

GUION = r"""// El asistente del panel en Chromium. Uso: node <guion> <base del panel> <usuario> <clave> <modo> <persona> <capturas>
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const [base, usuario, clave, modo, persona, capturas] = process.argv.slice(2);
const origen = new URL(base).origin;
const pref = new URL(base).pathname.replace(/\/+$/, '');
const TEXTO_XSS = '<img src=x onerror="window.__xss=1"> ¿Quiénes viven en Tres de Octubre?';
// La conexión con Mnemo como la da GET /api/agente/estado (mnemo.conexion) al administrador
const CONEXION = { estado: 'conectada', motivo: null, url: 'https://mnemo.example.org/mcp', cuenta: 'Ana Inventada (ana.inventada@example.org)',
  alcances: ['mnemo:model', 'mnemo:read', 'mnemo:workspace.write'], modelo: true, desde: '2026-11-08T10:00:00+00:00', url_sugerida: 'https://mnemo.example.org/mcp' };
const SIN_CONECTAR = { estado: 'sin_conectar', motivo: null, url: null, cuenta: null, alcances: [], modelo: false, desde: null, url_sugerida: null };
const CAIDA = { ...CONEXION, estado: 'caida', motivo: 'revocada', modelo: false };
const SIN_PERMISO = { ...CONEXION, alcances: ['mnemo:read', 'mnemo:workspace.write'], modelo: false };
// Sin modelo (ni Mnemo con permiso para usar sus modelos ni clave de Anthropic): el administrador ve el botón
const SIN_MODELO = (conexion) => ({ disponible: false, motivo: 'sin_configurar', configurado: false, proveedor: null, es_admin: true,
  escritura: true, limite: { usados: 0, maximo: 300 }, mnemo: { activo: conexion.estado === 'conectada', origen: null, conexion },
  sugerencias: [] });
const CASOS = {
  protocolo: [
    { nombre: 'escritorio', viewport: { width: 1400, height: 900 } },
    { nombre: 'movil', viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 },
    { nombre: 'chico', viewport: { width: 320, height: 568 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 },
    // El administrador sin modelo ve el botón, y adentro qué hacer (sin nombres de variables); Ajustes, la conexión
    { nombre: 'sin_modelo', viewport: { width: 1280, height: 800 }, estado: SIN_MODELO(SIN_CONECTAR) },
    // Mnemo como modelo: `texto_ronda` y los códigos nuevos del proveedor del modelo
    { nombre: 'mnemo', viewport: { width: 1280, height: 800 }, mnemo: true },
  ],
  real: [{ nombre: 'real', viewport: { width: 1280, height: 800 } }],
  real_mnemo: [{ nombre: 'real_mnemo', viewport: { width: 1280, height: 800 } }],
}[modo];

// ── Lo que contesta el «servidor» en el modo protocolo ──
const ESTADO = {
  disponible: true, motivo: null, configurado: true, es_admin: true, escritura: true, limite: { usados: 3, maximo: 300 },
  mnemo: { activo: true, origen: 'https://mnemo.example.org' },
  sugerencias: ['¿Cómo va la base? Dame los indicadores principales.', 'Muéstrame en el mapa a las personas que faltan por ubicar.'],
};
const H = (id, estado, resumen) => ({ tipo: 'herramienta', id, nombre: id === 'toolu_1' ? 'buscar_personas' : 'agregar_nota',
  etiqueta: id === 'toolu_1' ? 'Buscando habitantes' : 'Agregando la nota', estado, ...(resumen ? { resumen } : {}) });
const TURNO_1 = [
  { tipo: 'inicio', conversacion: 41, titulo: '¿Quiénes viven en Tres de Octubre?' },
  { tipo: 'progreso', texto: 'Lo que pinta una ronda ' }, { tipo: 'texto', texto: 'Esto se descarta.' }, { tipo: 'descartar' },
  { tipo: 'progreso', texto: 'Busco a las personas ' }, { tipo: 'progreso', texto: 'del barrio.' },
  H('toolu_1', 'inicio'), { tipo: 'latido' }, H('toolu_1', 'ok', '2 personas'),
  { tipo: 'accion', accion: { tipo: 'navegar', ruta: '/personas?zona=rural' } },
  { tipo: 'accion', accion: { tipo: 'navegar', ruta: 'https://malo.example/robar' } },
  'esto no es JSON', { tipo: 'futuro', dato: 1 },
  { tipo: 'texto', texto: 'Encontré **dos personas impor' },
  { tipo: 'texto', texto: 'tantes** en Tres de Octubre:\n\n- [Ana Inventada](/personas/1)\n- Beto <img src=x onerror="window.__xss=1"> Inventado\n\n' },
  { tipo: 'texto', texto: '| Barrio | Personas |\n|---|---:|\n| Tres de Octubre | 1.234 |\n\n' },
  { tipo: 'texto', texto: 'Más en [aquí](https://malo.example/robar), [esto](javascript:alert(1)) o [Aprobar en Mnemo](https://mnemo.example.org/aprobar/abc). Use `buscar_personas`.' },
  H('toolu_2', 'inicio'), H('toolu_2', 'pendiente'),
  { tipo: 'confirmar', id: 'toolu_2', nombre: 'agregar_nota', etiqueta: 'Agregando la nota', titulo: 'Agregar una nota',
    detalle: [['Persona', 'Ana Inventada (#1)'], ['Nota', 'Llamar el lunes <b>sin falta</b>']], aviso: 'Queda en la ficha y la ve el equipo.' },
  { tipo: 'fin', motivo: 'confirmacion', limite: { usados: 4, maximo: 300 } },
];
const TURNO_CONFIRMAR = [
  { tipo: 'inicio', conversacion: 41, titulo: '¿Quiénes viven en Tres de Octubre?' },
  H('toolu_2', 'aprobada'), H('toolu_2', 'ok', 'Nota guardada'),
  { tipo: 'accion', accion: { tipo: 'recargar' } }, { tipo: 'accion', accion: { tipo: 'insignias' } },
  { tipo: 'texto', texto: 'Listo: la nota quedó en la ficha.' }, { tipo: 'fin', motivo: 'listo', limite: { usados: 4, maximo: 300 } },
];
const corto = (texto, usados) => [
  { tipo: 'inicio', conversacion: 41, titulo: '¿Quiénes viven en Tres de Octubre?' },
  { tipo: 'texto', texto }, { tipo: 'fin', motivo: 'listo', limite: { usados, maximo: 300 } },
];
// Lo que contesta POST /mensajes, en orden: un error antes del flujo es {estado, detail}
const MENSAJES = [
  TURNO_1, corto('Claro que sí.', 5),
  { estado: 503, detail: { codigo: 'saturado', mensaje: 'El asistente está atendiendo muchas conversaciones a la vez. Intente de nuevo en unos segundos.' } },
  corto('Ahora sí.', 6),
  { estado: 401, detail: 'Inicie sesión' },
  corto('Sesión renovada.', 7),
];
const LISTA = { conversaciones: [
  { id: 41, titulo: '¿Quiénes viven en Tres de Octubre?', actualizada: '2026-11-07T15:00:00+00:00', pendiente: false },
  { id: 7, titulo: 'Reunión <b>inventada</b>', actualizada: '2026-11-01T10:00:00+00:00', pendiente: true },
] };
const CONV = {
  41: { id: 41, titulo: '¿Quiénes viven en Tres de Octubre?', pendientes: [], mensajes: [
    { rol: 'usuario', texto: '¿Quiénes viven en Tres de Octubre?' },
    { rol: 'asistente', partes: [{ tipo: 'progreso', texto: 'Busco.' }, H('toolu_1', 'ok', '2 personas'), { tipo: 'texto', texto: 'Encontré **dos**.' }] },
  ] },
  7: { id: 7, titulo: 'Reunión <b>inventada</b>', mensajes: [
    { rol: 'usuario', texto: 'Prepara la reunión' },
    { rol: 'asistente', partes: [{ tipo: 'texto', texto: 'La reunión tiene *12* asistentes.' }, { tipo: 'aviso', texto: 'Mnemo no respondió.', nivel: 'alerta' }] },
  ], pendientes: [{ id: 'toolu_9', nombre: 'crear_reunion', etiqueta: 'Creando la reunión', titulo: 'Crear la reunión', detalle: [['Fecha', '2026-11-20']], aviso: null }] },
};
const nd = (evs) => evs.map((e) => (typeof e === 'string' ? e : JSON.stringify(e))).join('\n') + '\n';

// Con Mnemo como modelo (caso «mnemo»): el estado y lo que contesta POST /mensajes, en orden
const ESTADO_MNEMO = { ...ESTADO, proveedor: 'mnemo', mnemo: { activo: true, origen: 'https://mnemo.example.org', conexion: CONEXION } };
// Tras la caída: las conversaciones nuevas irían en modo directo (hay clave), así que sigue disponible
const ESTADO_TRAS_CAIDA = { ...ESTADO, proveedor: 'anthropic', mnemo: { activo: false, origen: null, conexion: CAIDA } };
const HM = (id, estado, resumen) => ({ tipo: 'herramienta', id, nombre: 'buscar_personas', etiqueta: 'Buscando habitantes', estado, ...(resumen ? { resumen } : {}) });
const errorDe = (conversacion, codigo, mensaje) => [{ tipo: 'inicio', conversacion, titulo: 'Reuniones' }, { tipo: 'texto', texto: 'Un momen' },
  { tipo: 'error', codigo, mensaje }, { tipo: 'fin', motivo: 'error', limite: { usados: 9, maximo: 300 } }];
const MENSAJES_MNEMO = [
  // Tres rondas: los trozos de texto son un adelanto y el texto final de cada ronda (`texto_ronda`) lo reemplaza; en la
  // segunda no llegó ningún trozo y su texto va antes de su herramienta
  [{ tipo: 'inicio', conversacion: 51, titulo: 'Reuniones' },
    { tipo: 'texto', texto: 'Hola, mund' }, { tipo: 'texto', texto: 'o. Voy a busc' },
    { tipo: 'texto_ronda', texto: 'Hola, mundo. Voy a buscar a **Ana**.' }, HM('toolu_m1', 'inicio'), HM('toolu_m1', 'ok', '1 persona'),
    HM('toolu_m2', 'inicio'), { tipo: 'texto_ronda', texto: 'Encontré a Ana Inventada.' }, HM('toolu_m2', 'ok', '1 persona'),
    { tipo: 'texto', texto: 'Listo, ya est' }, { tipo: 'texto_ronda', texto: 'Listo.' },
    { tipo: 'fin', motivo: 'listo', limite: { usados: 4, maximo: 300 } }],
  errorDe(51, 'mnemo_conexion', 'La conexión con Mnemo venció o se revocó: el administrador tiene que volver a conectarla en Ajustes → Asistente.'),
  { estado: 409, detail: { codigo: 'proveedor', mensaje: 'Esta conversación se empezó con un modelo que ya no está disponible: empiece una nueva.' } },
  errorDe(52, 'mnemo_creditos', 'A la cuenta de Mnemo se le acabaron los créditos.'),
  errorDe(52, 'llm_peticion', 'El servicio del modelo rechazó la petición. Si se repite, empiece otra conversación.'),
  errorDe(52, 'mnemo_conexion', 'La conexión con Mnemo venció o se revocó: el administrador tiene que volver a conectarla en Ajustes → Asistente.'),
];

// Lo que contesta el «servidor»: el estado vigente (`reg.estado`, que la prueba puede cambiar) y, para POST
// /mensajes, `reg.respuestas` en orden (un error antes del flujo es {estado, detail})
async function servirAgente(ctx, reg) {
  await ctx.route((u) => u.pathname.startsWith(pref + '/api/agente/'), async (route) => {
    const req = route.request();
    const ruta = new URL(req.url()).pathname.slice(pref.length);
    const metodo = req.method();
    const json = (d, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(d) });
    const flujo = (evs) => route.fulfill({ status: 200, contentType: 'application/x-ndjson', headers: { 'cache-control': 'no-store' }, body: nd(evs) });
    if (metodo === 'GET' && ruta === '/api/agente/estado') { reg.lecturas++; return json(reg.estado); }
    if (metodo === 'GET' && ruta === '/api/agente/conversaciones') return json(LISTA);
    const c = /^\/api\/agente\/conversaciones\/(\d+)$/.exec(ruta);
    if (c && metodo === 'GET') return json(CONV[c[1]] || { detail: { codigo: 'no_existe', mensaje: 'No existe esa conversación.' } }, CONV[c[1]] ? 200 : 404);
    if (c && metodo === 'DELETE') { reg.borradas.push(+c[1]); return json({ ok: true }); }
    if (metodo === 'POST' && ruta === '/api/agente/mensajes') {
      reg.mensajes.push({ cuerpo: req.postDataJSON(), csrf: req.headers()['x-csrf-token'] || '' });
      const r = reg.respuestas[reg.mensajes.length - 1];
      // Los errores a propósito llevan una marca para no contarlos como errores de la página
      if (!Array.isArray(r)) return route.fulfill({ status: r.estado, contentType: 'application/json', headers: { 'x-prueba': 'esperado' }, body: JSON.stringify({ detail: r.detail }) });
      return flujo(r);
    }
    if (metodo === 'POST' && ruta === '/api/agente/confirmaciones') { reg.confirmaciones.push(req.postDataJSON()); return flujo(TURNO_CONFIRMAR); }
    return json({ detail: 'No existe' }, 404);
  });
}

// ── Ayudas ──
const espera = { timeout: 15000 };
async function geometria(page, caso, cuando) {
  // Se mide sin la animación de entrada del panel (se desliza unos píxeles al abrirse)
  await page.waitForFunction(() => document.getAnimations().every((a) => a.playState !== 'running' || a.effect?.getComputedTiming().iterations === Infinity));
  const g = await page.evaluate(() => {
    const caja = (s) => { const e = document.querySelector(s); if (!e || e.hidden || !e.getClientRects().length) return null; const r = e.getBoundingClientRect(); return { x: r.left, y: r.top, d: r.right, a: r.bottom }; };
    const dentro = (r) => !!r && r.x >= -0.5 && r.y >= -0.5 && r.d <= innerWidth + 0.5 && r.a <= innerHeight + 0.5;
    const log = document.querySelector('#agente-mensajes');
    return { boton: caja('#agente-boton'), panel: caja('#agente-panel'), panelDentro: dentro(caja('#agente-panel')),
      botonDentro: dentro(caja('#agente-boton')), desborde: document.documentElement.scrollWidth > innerWidth,
      desbordeLog: !!log && log.scrollWidth > log.clientWidth + 1, ventana: [innerWidth, innerHeight],
      ancho: document.documentElement.scrollWidth, anchos: [...document.querySelectorAll('body *')].filter((e) => e.getBoundingClientRect().right > innerWidth + 0.5 && getComputedStyle(e).position !== 'fixed').slice(0, 5).map((e) => `${e.tagName}.${e.className}#${e.id} ${Math.round(e.getBoundingClientRect().right)}`) };
  });
  // En el celular un contenido más ancho que la pantalla no da barra de desplazamiento: el navegador agranda la ventana
  // de diseño (innerWidth) para que quepa. Se compara con el ancho pedido
  g.desborde ||= g.ventana[0] !== page.viewportSize().width;
  caso.geo = caso.geo || {};
  caso.geo[cuando] = g;
  return g;
}
const cruzan = (a, b) => !!a && !!b && a.x < b.d && b.x < a.d && a.y < b.a && b.y < a.a;

async function salirAlcanzable(page, tocar) {
  await tocar('#abrir-menu');
  await page.waitForFunction(() => document.querySelector('#app').classList.contains('menu-abierto'));
  await page.waitForTimeout(400); // la transición del menú (.25 s)
  await page.locator('#salir').scrollIntoViewIfNeeded(); // en una pantalla baja el menú se desplaza solo él
  const ok = await page.evaluate(() => {
    const s = document.querySelector('#salir');
    const r = s.getBoundingClientRect();
    const e = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return r.top >= 0 && r.bottom <= innerHeight && r.right <= innerWidth && !!e && s.contains(e);
  });
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => !document.querySelector('#app').classList.contains('menu-abierto'));
  return ok;
}

async function ingresar(page) {
  await page.goto(base + '/', { waitUntil: 'domcontentloaded' });
  await page.fill('#f-login [name=usuario]', usuario);
  await page.fill('#f-login [name=clave]', clave);
  await page.click('#f-login button[type=submit]');
  await page.waitForSelector('#app #vista > .vista', espera);
  await page.waitForSelector('#agente-boton:not([hidden])', espera);
}

async function enviar(page, texto) {
  await page.fill('#agente-texto', texto);
  await page.press('#agente-texto', 'Enter');
}

const listo = (page) => page.waitForFunction(() => document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);

async function protocolo(page, op, caso) {
  const v = caso.revisiones;
  const movil = !!op.isMobile;
  const tocar = (s) => (op.hasTouch ? page.tap(s) : page.click(s));
  await ingresar(page);
  let g = await geometria(page, caso, 'inicio');
  v.boton_visible = g.botonDentro;
  // En el mapa (render() pone #vista.lleno): en el celular el botón va a la barra de arriba, a la derecha y sin tapar
  // el título; en escritorio, a la izquierda de los controles de MapLibre (abajo a la derecha, 39 px de ancho)
  const enMapa = await page.evaluate(() => {
    const vista = document.querySelector('#vista');
    vista.classList.add('lleno');
    const r = (s) => { const b = document.querySelector(s).getBoundingClientRect(); return { x: b.left, y: b.top, d: b.right, a: b.bottom }; };
    const out = { boton: r('#agente-boton'), titulo: r('.barra-movil b'), ancho: innerWidth, alto: innerHeight };
    vista.classList.remove('lleno');
    return out;
  });
  caso.geo.mapa = enMapa;
  v.boton_en_el_mapa = movil ? enMapa.boton.a <= 60 && enMapa.boton.d <= enMapa.ancho && enMapa.ancho - enMapa.boton.d < 20 && !cruzan(enMapa.boton, enMapa.titulo)
    : enMapa.boton.d <= enMapa.ancho - 60 && enMapa.boton.a > enMapa.alto - 100;
  if (movil) v.salir_con_el_menu = await salirAlcanzable(page, tocar);

  await tocar('#agente-boton');
  await page.waitForSelector('#agente-panel:not([hidden])');
  v.boton_oculto_con_el_panel = await page.evaluate(() => document.querySelector('#agente-boton').hidden
    && document.querySelector('#agente-boton').getAttribute('aria-expanded') === 'true');
  if (!movil) v.foco_en_el_cuadro = await page.evaluate(() => document.activeElement?.id === 'agente-texto');
  await page.waitForSelector('.agente-sugerencia');
  v.bienvenida = await page.evaluate(() => document.querySelectorAll('.agente-sugerencia').length === 2
    && document.querySelector('#agente-restantes').textContent === 'Le quedan 297 mensajes hoy'
    && document.querySelector('#agente-mensajes').getAttribute('role') === 'log'
    && document.querySelector('#agente-mensajes').getAttribute('aria-live') === 'polite');
  g = await geometria(page, caso, 'abierto');
  v.panel_dentro = g.panelDentro && !g.desborde;
  if (movil) v.salir_con_el_panel_abierto = await salirAlcanzable(page, tocar);
  await page.screenshot({ path: `${capturas}/agente-${caso.nombre}-bienvenida.png` });

  // ── El turno con todos los eventos ──
  await enviar(page, TEXTO_XSS);
  await page.waitForFunction(() => document.querySelector('.agente-tarjeta') && document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);
  await page.waitForFunction(() => (window.__vistas || []).includes('/personas'), null, espera);
  await page.waitForTimeout(150);
  const d = await page.evaluate(() => {
    const msjs = [...document.querySelectorAll('.agente-msj.agente-respuesta')];
    const a = msjs[msjs.length - 1];
    const enlaces = [...a.querySelectorAll('a')].map((x) => ({ texto: x.textContent, href: x.getAttribute('href'), ruta: x.hasAttribute('data-ruta'), target: x.target, rel: x.rel }));
    const chip = (id) => [...document.querySelectorAll('.agente-herr')].find((c) => c.textContent.includes(id === 1 ? 'Buscando' : 'Agregando'));
    const t = document.querySelector('.agente-tarjeta');
    return {
      usuario: document.querySelector('.agente-msj.agente-persona p').textContent,
      texto: a.querySelector('.agente-md').textContent, html: a.querySelector('.agente-md').innerHTML,
      negrita: [...a.querySelectorAll('strong')].map((x) => x.textContent), items: a.querySelectorAll('.agente-md li').length,
      tabla: [...a.querySelectorAll('.md-tabla th, .md-tabla td')].map((x) => x.textContent), der: !!a.querySelector('.md-tabla td.der'),
      codigo: [...a.querySelectorAll('.agente-md code')].map((x) => x.textContent), enlaces,
      progreso: a.querySelector('.agente-progreso')?.textContent, progresos: [...document.querySelectorAll('.agente-progreso')].map((x) => x.textContent), notas: [...a.querySelectorAll('.agente-nota')].map((x) => x.textContent),
      chip1: chip(1)?.dataset.estado + '|' + chip(1)?.textContent, chip2: chip(2)?.dataset.estado,
      tarjeta: t && { titulo: t.querySelector('h3').textContent, dt: [...t.querySelectorAll('dt')].map((x) => x.textContent), dd: [...t.querySelectorAll('dd')].map((x) => x.textContent), aviso: t.querySelector('.agente-tarjeta-aviso')?.textContent, botones: [...t.querySelectorAll('button')].map((x) => x.textContent) },
      imgs: document.querySelectorAll('#agente-panel img, #agente-panel [onerror]').length, xss: window.__xss === undefined,
      ruta: location.pathname + location.search, restantes: document.querySelector('#agente-restantes').textContent,
      guardado: sessionStorage.getItem('yj_agente'), local: Object.keys(localStorage), abierto: !document.querySelector('#agente-panel').hidden,
      senal: document.querySelector('#agente-boton').dataset.senal, foco: document.activeElement?.id, sub: document.querySelector('#agente-sub').textContent,
      notaPendiente: !document.querySelector('#agente-nota-pendiente').hidden,
    };
  });
  caso.datos = d;
  v.texto_del_usuario_como_texto = d.usuario === TEXTO_XSS;
  v.sin_xss = d.imgs === 0 && d.xss && !d.html.includes('<img') && d.texto.includes('<img src=x onerror="window.__xss=1">');
  v.descartado = !d.texto.includes('Esto se descarta') && !d.progresos.some((p) => p.includes('Lo que pinta'));
  v.markdown = d.negrita.includes('dos personas importantes') && d.items === 2 && d.der && d.codigo.includes('buscar_personas')
    && JSON.stringify(d.tabla) === JSON.stringify(['Barrio', 'Personas', 'Tres de Octubre', '1.234']);
  v.enlace_interno = d.enlaces.some((e) => e.texto === 'Ana Inventada' && e.href === pref + '/personas/1' && e.ruta && !e.target);
  v.enlace_mnemo = d.enlaces.some((e) => e.texto === 'Aprobar en Mnemo' && e.href === 'https://mnemo.example.org/aprobar/abc' && e.target === '_blank' && e.rel === 'noopener noreferrer');
  v.enlaces_no_permitidos_como_texto = d.enlaces.length === 2 && d.texto.includes('Más en aquí, esto o') && !d.html.includes('malo.example') && !d.html.includes('javascript');
  v.progreso = d.progreso === 'Busco a las personas del barrio.';
  v.chips = d.chip1.startsWith('ok|') && d.chip1.includes('Buscando habitantes · 2 personas') && d.chip2 === 'pendiente';
  v.tarjeta = !!d.tarjeta && d.tarjeta.titulo === 'Agregar una nota' && JSON.stringify(d.tarjeta.dt) === '["Persona","Nota"]'
    && d.tarjeta.dd[1] === 'Llamar el lunes <b>sin falta</b>' && d.tarjeta.aviso === 'Queda en la ficha y la ve el equipo.'
    && JSON.stringify(d.tarjeta.botones) === '["Aprobar","Rechazar"]' && d.notaPendiente;
  v.navego = d.ruta.startsWith(pref + '/personas?zona=rural'); // la vista agrega su orden a la URL
  v.navegar_fuera_rechazado = d.notas.some((n) => n.includes('no es una vista del panel'));
  v.restantes = d.restantes === 'Le quedan 296 mensajes hoy';
  v.titulo = d.sub === '¿Quiénes viven en Tres de Octubre?';
  v.guardado_en_la_pestana = JSON.parse(d.guardado || '{}').conversacion === 41 && d.local.every((k) => k === 'tema');
  if (movil) {
    // En el celular se plegó al navegar: el botón avisa que hay algo esperando su aprobación
    v.plegado_al_navegar = !d.abierto && d.senal === 'pendiente';
    await page.screenshot({ path: `${capturas}/agente-${caso.nombre}-plegado.png` });
    await tocar('#agente-boton');
    await page.waitForSelector('#agente-panel:not([hidden])');
  } else {
    v.foco_vuelve_tras_navegar = d.abierto && d.foco === 'agente-texto';
  }
  g = await geometria(page, caso, 'respuesta');
  v.sin_desborde_con_la_respuesta = !g.desborde && !g.desbordeLog && g.panelDentro;
  await page.screenshot({ path: `${capturas}/agente-${caso.nombre}-respuesta.png` });

  // ── Aprobar ──
  const vistas = await page.evaluate(() => window.__vistas.length);
  const insignias = caso.insignias;
  await page.locator('.agente-tarjeta .btn.primario').scrollIntoViewIfNeeded();
  await tocar('.agente-tarjeta .btn.primario');
  await page.waitForFunction(() => document.querySelector('.agente-tarjeta').dataset.estado === 'ok' && document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);
  await page.waitForFunction((n) => window.__vistas.length > n, vistas, espera);
  await page.waitForTimeout(150);
  const c = await page.evaluate(() => ({ estado: document.querySelector('.agente-tarjeta-estado').textContent,
    botones: document.querySelector('.agente-tarjeta-botones').hidden, chip: [...document.querySelectorAll('.agente-herr')].find((x) => x.textContent.includes('Agregando'))?.dataset.estado,
    final: [...document.querySelectorAll('.agente-msj.agente-respuesta .agente-md')].pop().textContent, abierto: !document.querySelector('#agente-panel').hidden,
    ruta: location.pathname + location.search, notaPendiente: !document.querySelector('#agente-nota-pendiente').hidden }));
  v.aprobada = c.estado === 'Hecho · Nota guardada' && c.botones && c.chip === 'ok' && c.final === 'Listo: la nota quedó en la ficha.' && !c.notaPendiente;
  v.recargo_sin_plegarse = c.abierto && c.ruta.startsWith(pref + '/personas?zona=rural');
  v.insignias = caso.insignias > insignias;

  // ── Otro mensaje en la misma conversación ──
  await enviar(page, '¿Y cuántas faltan por ubicar?');
  await page.waitForFunction(() => [...document.querySelectorAll('.agente-md')].pop()?.textContent === 'Claro que sí.' && document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);

  if (!movil) {
    // Mayús+Enter es otra línea (no envía)
    await page.fill('#agente-texto', 'uno');
    await page.press('#agente-texto', 'Shift+Enter');
    await page.type('#agente-texto', 'dos');
    v.mayus_enter = await page.evaluate(() => document.querySelector('#agente-texto').value === 'uno\ndos') && caso.mensajes.length === 2;
    // Un error antes del flujo (503): la burbuja queda «No se envió» y «Reintentar» la reusa
    await enviar(page, 'Tercero');
    await page.waitForSelector('.agente-error .agente-reintentar', espera);
    const fallo = await page.evaluate(() => ({ error: document.querySelector('.agente-error').textContent,
      sinEnviar: [...document.querySelectorAll('.agente-msj.agente-persona')].pop().textContent }));
    await page.click('.agente-error .agente-reintentar');
    await page.waitForFunction(() => [...document.querySelectorAll('.agente-md')].pop()?.textContent === 'Ahora sí.' && document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);
    v.reintentar = fallo.error.includes('atendiendo muchas conversaciones') && fallo.sinEnviar.includes('No se envió')
      && await page.evaluate(() => !document.querySelector('.agente-error') && !document.querySelector('.sin-enviar')
        && [...document.querySelectorAll('.agente-msj.agente-persona p')].filter((p) => p.textContent === 'Tercero').length === 1);
    // La sesión venció: se abre el ingreso del panel en un diálogo y el mensaje se reintenta solo
    await enviar(page, 'Cuarto');
    await page.waitForSelector('dialog[open] #f-reingreso', espera);
    await page.fill('dialog[open] [name=clave]', clave);
    await page.click('dialog[open] button[type=submit]');
    await page.waitForFunction(() => [...document.querySelectorAll('.agente-md')].pop()?.textContent === 'Sesión renovada.' && document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);
    v.reingreso = caso.mensajes.length === 6 && !await page.$('dialog[open]') && caso.mensajes[5].csrf && caso.mensajes[5].csrf !== caso.mensajes[4].csrf;
    // Escape cierra el panel (el foco está dentro) y el foco vuelve al botón
    await page.focus('#agente-texto');
    await page.keyboard.press('Escape');
    v.escape_cierra = await page.evaluate(() => document.querySelector('#agente-panel').hidden && document.activeElement?.id === 'agente-boton');
    // Al recargar la página vuelve abierto con la conversación guardada (pedida de nuevo al servidor)
    await page.click('#agente-boton');
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.waitForSelector('#agente-panel:not([hidden]) .agente-md', espera);
    v.restaura_la_conversacion = await page.evaluate(() => document.querySelector('.agente-md').textContent === 'Encontré dos.'
      && document.querySelector('.agente-herr').dataset.estado === 'ok' && document.querySelector('#agente-sub').textContent.startsWith('¿Quiénes'));
    // Tema oscuro, para mirar
    await page.click('#cambiar-tema');
    await page.screenshot({ path: `${capturas}/agente-${caso.nombre}-oscuro.png` });
    await page.click('#cambiar-tema');
  }

  // ── Historial: abrir una conversación con algo pendiente y borrarla ──
  await tocar('#agente-ver-historial');
  await page.waitForSelector('.agente-item .agente-abrir', espera);
  const lista = await page.evaluate(() => [...document.querySelectorAll('.agente-item b')].map((x) => x.textContent));
  v.historial = JSON.stringify(lista) === JSON.stringify(['¿Quiénes viven en Tres de Octubre?', 'Reunión <b>inventada</b>'])
    && await page.evaluate(() => document.querySelector('#agente-ver-historial').getAttribute('aria-expanded') === 'true' && document.querySelector('#agente-cuerpo').hidden);
  await page.screenshot({ path: `${capturas}/agente-${caso.nombre}-historial.png` });
  await tocar('.agente-item:nth-child(2) .agente-abrir');
  await page.waitForSelector('.agente-tarjeta', espera);
  v.abre_del_historial = await page.evaluate(() => document.querySelector('.agente-md em')?.textContent === '12'
    && document.querySelector('.agente-tarjeta h3').textContent === 'Crear la reunión' && !document.querySelector('.agente-tarjeta .btn.primario').disabled
    && document.querySelector('.agente-nota.alerta')?.textContent === 'Mnemo no respondió.' && document.querySelector('#agente-sub').textContent === 'Reunión <b>inventada</b>');
  await tocar('#agente-ver-historial');
  await page.waitForSelector('.agente-item:nth-child(2) .agente-borrar', espera);
  await tocar('.agente-item:nth-child(2) .agente-borrar');
  await page.waitForSelector('dialog[open] [data-si]');
  await tocar('dialog[open] [data-si]');
  await page.waitForFunction(() => document.querySelectorAll('.agente-item').length === 1, null, espera);
  v.borra = caso.borradas.length === 1 && caso.borradas[0] === 7;
  await tocar('#agente-volver');
  v.vuelve_a_la_bienvenida = await page.evaluate(() => !!document.querySelector('.agente-bienvenida') && document.querySelector('#agente-sub').textContent === 'Nueva conversación');

  if (movil) {
    // En la ficha, abajo está su barra de acciones: el botón va arriba y no la tapa
    await tocar('#agente-cerrar');
    await page.evaluate((r) => { history.pushState({}, '', r); dispatchEvent(new PopStateEvent('popstate')); }, `${pref}/personas/${persona}`);
    await page.waitForSelector('#vista .barra-acciones', espera);
    await page.waitForTimeout(150);
    const f = await page.evaluate(() => {
      const r = (s) => { const e = document.querySelector(s); const b = e?.getBoundingClientRect(); return b && { x: b.left, y: b.top, d: b.right, a: b.bottom }; };
      return { boton: r('#agente-boton'), barra: r('#vista .barra-acciones'), guardar: r('#vista .guardar-ficha'), titulo: r('.barra-movil b') };
    });
    caso.geo.ficha_boton = f;
    v.boton_no_tapa_la_ficha = !!f.boton && f.boton.a <= 60 && !cruzan(f.boton, f.barra) && !cruzan(f.boton, f.guardar) && !cruzan(f.boton, f.titulo);
    await page.screenshot({ path: `${capturas}/agente-${caso.nombre}-ficha.png` });
    await tocar('#agente-boton');
    await page.waitForSelector('#agente-panel:not([hidden])');
    g = await geometria(page, caso, 'ficha');
    v.panel_en_la_ficha = g.panelDentro && !g.desborde && await page.evaluate(() => getComputedStyle(document.querySelector('#vista .barra-acciones')).display === 'none');
    v.salir_en_la_ficha = await salirAlcanzable(page, tocar);
  }

  // Cerrar sesión borra lo guardado del asistente en la pestaña
  if (!movil) {
    await tocar('#agente-cerrar');
    await page.click('#salir');
    await page.waitForSelector('#f-login', espera);
    v.cerrar_sesion_olvida = await page.evaluate(() => sessionStorage.getItem('yj_agente') === null);
  }
}

// Sin modelo: el administrador ve el botón y adentro qué hacer según la conexión con Mnemo, sin nombres de variables y
// con un enlace a Ajustes, donde está la conexión con sus botones. Se cambia el estado y se recarga para cada caso
async function sinModelo(page, caso) {
  const v = caso.revisiones;
  const sinVariables = (t) => !/ANTHROPIC|MNEMO_|AGENTE_|token|variable/i.test(t);
  const explicacion = async () => {
    // Tras recargar, el widget se monta después de la vista y vuelve abierto si lo estaba (lo guarda la pestaña)
    await page.waitForFunction(() => [...document.querySelectorAll('#agente-panel, #agente-boton')].some((x) => !x.hidden), null, espera);
    if (await page.evaluate(() => document.querySelector('#agente-panel').hidden)) await page.click('#agente-boton');
    await page.waitForSelector('#agente-panel:not([hidden]) .agente-explicacion', espera);
    return page.evaluate(() => {
      const e = document.querySelector('.agente-explicacion');
      const a = e.querySelector('a');
      return { titulo: e.querySelector('h3').textContent, texto: e.textContent, sub: document.querySelector('#agente-sub').textContent,
        enlace: a && { texto: a.textContent, href: a.getAttribute('href'), ruta: a.hasAttribute('data-ruta') },
        sinCompositor: document.querySelector('#agente-form').hidden && document.querySelector('#agente-nueva').hidden
          && document.querySelector('#agente-ver-historial').hidden };
    });
  };
  const bloque = async () => {
    await page.waitForSelector('#mnemo-conexion', espera);
    return page.evaluate(() => {
      const b = document.querySelector('#mnemo-conexion');
      return { estado: b.dataset.estado, texto: b.textContent.replace(/\s+/g, ' '), botones: [...b.querySelectorAll('button')].map((x) => x.textContent.trim()),
        rige: document.querySelector('.asistente-cabeza').textContent.replace(/\s+/g, ' '), ruta: location.pathname };
    });
  };
  const enlaceBueno = (e) => !!e.enlace && e.enlace.texto === 'Ajustes → Asistente' && e.enlace.href === pref + '/ajustes' && e.enlace.ruta;
  caso.datos = {};
  await ingresar(page);
  // 1. Sin conectar
  let e = await explicacion();
  caso.datos.sin_conectar = e;
  v.explica_sin_conectar = e.titulo === 'El asistente no está conectado' && e.sub === 'Sin conectar' && e.sinCompositor
    && e.texto.includes('El asistente usa los modelos de su cuenta de Mnemo. El administrador lo conecta en Ajustes → Asistente: inicia sesión en Mnemo y da permiso; no hay que copiar claves.')
    && sinVariables(e.texto) && enlaceBueno(e);
  v.foco_en_cerrar = await page.evaluate(() => document.activeElement?.id === 'agente-cerrar');
  await page.waitForFunction(() => document.querySelector('#agente-panel').getAnimations().length === 0);
  await page.screenshot({ path: `${capturas}/agente-sin-modelo.png` });
  // El enlace abre Ajustes (sin recargar): la conexión, con «Conectar con Mnemo»
  await page.click('.agente-explicacion a');
  let b = await bloque();
  caso.datos.ajustes_sin_conectar = b;
  v.ajustes_sin_conectar = b.ruta === pref + '/ajustes' && b.estado === 'sin_conectar' && JSON.stringify(b.botones) === '["Conectar con Mnemo"]'
    && b.texto.includes('no hay que copiar claves') && b.rige.includes('El asistente está apagado: no tiene un modelo que usar.') && sinVariables(b.texto);
  // 2. La conexión se cayó (Mnemo la revocó)
  caso.estado = SIN_MODELO(CAIDA);
  await page.reload({ waitUntil: 'domcontentloaded' });
  e = await explicacion();
  b = await bloque();
  caso.datos.caida = { e, b };
  v.explica_la_caida = e.titulo === 'Se cortó la conexión con Mnemo' && e.sub === 'Conexión caída' && e.texto.includes('se revocó en Mnemo')
    && e.texto.includes('El administrador la vuelve a conectar en Ajustes → Asistente') && sinVariables(e.texto) && enlaceBueno(e);
  v.ajustes_caida = b.estado === 'caida' && JSON.stringify(b.botones) === '["Volver a conectar","Desconectar"]' && b.texto.includes('Conexión caída')
    && b.texto.includes('se revocó en Mnemo');
  // 3. Conectado sin permiso para usar los modelos
  caso.estado = SIN_MODELO(SIN_PERMISO);
  await page.reload({ waitUntil: 'domcontentloaded' });
  e = await explicacion();
  b = await bloque();
  caso.datos.sin_permiso = { e, b };
  v.explica_sin_permiso = e.titulo === 'Mnemo está conectado sin permiso para usar sus modelos' && e.texto.includes('«Usar tus modelos de IA y tus créditos»')
    && sinVariables(e.texto) && enlaceBueno(e);
  v.ajustes_sin_permiso = b.estado === 'conectada' && b.texto.includes('Conectado como Ana Inventada (ana.inventada@example.org)')
    && b.texto.includes('Mnemo se conectó sin permiso para usar sus modelos: vuelva a conectar y marque esa casilla')
    && !b.texto.includes('Usar sus modelos de IA y sus créditos') && JSON.stringify(b.botones) === '["Volver a conectar","Desconectar"]';
  await page.locator('#mnemo-conexion').screenshot({ path: `${capturas}/ajustes-mnemo-sin-permiso.png` });
  await page.focus('#agente-cerrar'); // volvió abierto tras recargar, sin tomar el foco: Escape vale con el foco adentro
  await page.keyboard.press('Escape');
  v.cierra = await page.evaluate(() => document.querySelector('#agente-panel').hidden && !document.querySelector('#agente-boton').hidden);
}

// Contra el núcleo de verdad con el modelo de Mnemo (falso): lo que quedó pintado de cada ronda es su texto final
async function realMnemo(page, caso) {
  const v = caso.revisiones;
  const respuesta = () => page.evaluate(() => [...[...document.querySelectorAll('.agente-msj.agente-respuesta')].pop().children]
    .filter((x) => !x.classList.contains('sr'))
    .map((x) => (x.classList.contains('agente-md') ? `md:${x.textContent}` : x.classList.contains('agente-herr') ? `herr:${x.dataset.estado}` : x.className)));
  await ingresar(page);
  await page.click('#agente-boton');
  await page.waitForSelector('#agente-panel:not([hidden]) .agente-sugerencia', espera);
  // 1. El adelanto («Hola, mundi») no es el comienzo del texto final: `texto_ronda` lo reemplaza
  await enviar(page, 'Hola');
  await page.waitForFunction(() => [...document.querySelectorAll('.agente-md')].pop()?.textContent === 'Hola, mundo.'
    && document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);
  const uno = await respuesta();
  // 2. Dos rondas: texto y una herramienta del panel; después, el texto sin adelanto
  await enviar(page, '¿Cuántas personas hay en La Paz?');
  await page.waitForFunction(() => [...document.querySelectorAll('.agente-md')].pop()?.textContent === 'Hay 3 personas en La Paz.'
    && document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);
  const dos = await respuesta();
  caso.datos = { uno, dos };
  v.texto_final = JSON.stringify(uno) === JSON.stringify(['md:Hola, mundo.']);
  v.rondas_en_orden = JSON.stringify(dos) === JSON.stringify(['md:Voy a contar.', 'herr:ok', 'md:Hay 3 personas en La Paz.']);
  v.sin_errores_en_el_turno = await page.evaluate(() => !document.querySelector('.agente-error'));
  await page.screenshot({ path: `${capturas}/agente-real-mnemo.png` });
}

// Mnemo como modelo, desde una vista cuya dirección trae lo de una vuelta de Mnemo (que no debe ir al modelo)
async function conMnemo(page, caso) {
  const v = caso.revisiones;
  await ingresar(page);
  await page.goto(`${base}/reuniones?zona=rural&code=c0de&state=st4te&iss=${encodeURIComponent('https://mnemo.example.org')}&error=x&error_description=y`,
    { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#app #vista > .vista', espera);
  await page.click('#agente-boton');
  await page.waitForSelector('#agente-panel:not([hidden]) .agente-sugerencia', espera);
  const ultimoError = () => page.evaluate(() => {
    const e = [...document.querySelectorAll('.agente-error')].pop();
    return e && { texto: e.textContent, botones: [...e.querySelectorAll('button')].map((x) => x.textContent) };
  });
  // 1. `texto_ronda`: queda el texto final de cada ronda, en su lugar (antes de las herramientas que pidió)
  await enviar(page, '¿Quién es Ana?');
  await page.waitForFunction(() => document.querySelector('#agente-sub').textContent === 'Reuniones' && document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);
  await page.waitForTimeout(100);
  const partes = await page.evaluate(() => [...[...document.querySelectorAll('.agente-msj.agente-respuesta')].pop().children]
    .filter((x) => !x.classList.contains('sr'))
    .map((x) => (x.classList.contains('agente-md') ? `md:${x.textContent}` : x.classList.contains('agente-herr') ? `herr:${x.dataset.estado}` : x.className)));
  caso.datos = { partes };
  v.texto_ronda = JSON.stringify(partes) === JSON.stringify(['md:Hola, mundo. Voy a buscar a Ana.', 'herr:ok', 'md:Encontré a Ana Inventada.', 'herr:ok', 'md:Listo.'])
    && await page.evaluate(() => [...document.querySelectorAll('.agente-md strong')].some((x) => x.textContent === 'Ana'));
  // 2. La conexión se cayó: el error sin «Reintentar» y el estado se vuelve a leer
  caso.estado = ESTADO_TRAS_CAIDA;
  const lecturas = caso.lecturas;
  await enviar(page, '¿Y su teléfono?');
  await page.waitForFunction(() => document.querySelectorAll('.agente-error').length === 1 && document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);
  for (let i = 0; i < 100 && caso.lecturas === lecturas; i++) await page.waitForTimeout(50);
  let err = await ultimoError();
  caso.datos.caida = err;
  v.conexion_caida = err.texto.includes('volver a conectarla en Ajustes → Asistente') && err.botones.length === 0 && caso.lecturas === lecturas + 1;
  // 3. La conversación es de un proveedor que ya no está (409): «Nueva conversación», con el mensaje escrito
  await enviar(page, '¿Y las reuniones de mañana?');
  await page.waitForFunction(() => document.querySelectorAll('.agente-error').length === 2 && document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);
  err = await ultimoError();
  caso.datos.proveedor = err;
  v.proveedor_ofrece_otra = err.texto.includes('empiece una nueva') && JSON.stringify(err.botones) === '["Nueva conversación"]'
    && await page.evaluate(() => [...document.querySelectorAll('.agente-msj.agente-persona')].pop().textContent.includes('No se envió'));
  await page.click('.agente-error .agente-reintentar');
  await page.waitForSelector('.agente-bienvenida', espera);
  v.nueva_con_el_mensaje = await page.evaluate(() => document.querySelector('#agente-texto').value === '¿Y las reuniones de mañana?'
    && document.querySelector('#agente-sub').textContent === 'Nueva conversación');
  // 4. Sin créditos: no se reintenta (el mensaje escrito se envía en la conversación nueva)
  await page.press('#agente-texto', 'Enter');
  await page.waitForFunction(() => document.querySelectorAll('.agente-error').length === 1 && document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);
  err = await ultimoError();
  v.creditos_sin_reintento = err.texto.includes('se le acabaron los créditos') && err.botones.length === 0;
  // 5. Petición rechazada: «Nueva conversación»
  await enviar(page, 'Último');
  await page.waitForFunction(() => document.querySelectorAll('.agente-error').length === 2 && document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);
  err = await ultimoError();
  v.peticion_ofrece_otra = JSON.stringify(err.botones) === '["Nueva conversación"]';
  await page.screenshot({ path: `${capturas}/agente-mnemo.png` });
  // 6. Quien no es el administrador se queda sin modelo a mitad (la conexión se cayó y no hay otro): el panel no se
  // cierra de golpe, dice qué pasó (sin enlace a Ajustes) y, al cerrarlo, el botón ya no vuelve
  caso.estado = { ...SIN_MODELO(CAIDA), es_admin: false };
  await enviar(page, '¿Sigues ahí?');
  await page.waitForSelector('.agente-explicacion', espera);
  const ex = await page.evaluate(() => ({ abierto: !document.querySelector('#agente-panel').hidden,
    boton: document.querySelector('#agente-boton').hidden, titulo: document.querySelector('.agente-explicacion h3').textContent,
    texto: document.querySelector('.agente-explicacion').textContent, enlace: !!document.querySelector('.agente-explicacion a'),
    compositor: document.querySelector('#agente-form').hidden, nueva: document.querySelector('#agente-nueva').hidden }));
  caso.datos.sin_modelo_a_mitad = ex;
  v.sin_modelo_a_mitad = ex.abierto && ex.boton && ex.titulo === 'Se cortó la conexión con Mnemo' && !ex.enlace && ex.compositor && ex.nueva
    && ex.texto.includes('El administrador la vuelve a conectar en Ajustes → Asistente');
  await page.screenshot({ path: `${capturas}/agente-mnemo-sin-modelo-a-mitad.png` });
  await page.focus('#agente-cerrar');
  await page.keyboard.press('Escape');
  v.al_cerrar_no_vuelve = await page.evaluate(() => document.querySelector('#agente-panel').hidden && document.querySelector('#agente-boton').hidden);
}

async function real(page, caso) {
  const v = caso.revisiones;
  await ingresar(page);
  await page.click('#agente-boton');
  await page.waitForSelector('#agente-panel:not([hidden]) .agente-sugerencia', espera);
  const t0 = Date.now();
  await enviar(page, 'Hola');
  await page.waitForFunction(() => document.querySelector('.agente-md p'), null, espera);
  const primero = Date.now() - t0;
  // Cuando ya hay un segundo párrafo, el primero está completo: se marca su nodo
  await page.waitForFunction(() => { const ps = document.querySelectorAll('.agente-md p'); if (ps.length < 2) return false; window.__p1 = ps[0]; return true; }, null, espera);
  await listo(page);
  const total = Date.now() - t0;
  const d = await page.evaluate(() => ({ respuesta: [...document.querySelectorAll('.agente-md p')].map((p) => p.textContent).join('\n\n'),
    mismo: document.querySelector('.agente-md p') === window.__p1, sub: document.querySelector('#agente-sub').textContent,
    restantes: document.querySelector('#agente-restantes').textContent }));
  caso.datos = { ...d, primero_ms: primero, total_ms: total };
  v.primer_parrafo_no_se_rehace = d.mismo;
  v.titulo = d.sub === 'Hola';
  v.restantes = /^Le quedan \d+ mensajes hoy$/.test(d.restantes);
  // «Detener» corta el turno y el siguiente mensaje funciona
  await enviar(page, 'Cuéntame más');
  await page.waitForFunction(() => document.querySelectorAll('.agente-md').length === 2, null, espera);
  await page.click('#agente-detener');
  await listo(page);
  const det = await page.evaluate(() => ({ notas: [...document.querySelectorAll('.agente-nota')].map((n) => n.textContent),
    parcial: [...document.querySelectorAll('.agente-md')][1]?.textContent || '' }));
  caso.datos.detenido = det;
  // Lo que alcanzó a llegar se queda (empieza por «Part…») y no llegó todo
  v.detenido = det.notas.includes('Detuvo la respuesta.') && det.parcial.startsWith('Part') && !det.parcial.includes('Parte 29');
  await enviar(page, 'Gracias');
  await page.waitForFunction(() => [...document.querySelectorAll('.agente-md')].pop()?.textContent === 'De nada.' && document.querySelector('#agente-panel').dataset.estado === 'listo', null, { timeout: 30000 });
  v.siguiente_mensaje = await page.evaluate(() => !document.querySelector('.agente-error'));
  await page.screenshot({ path: `${capturas}/agente-real.png` });
}

(async () => {
  const nav = await chromium.launch();
  const res = { casos: [] };
  try {
    for (const { nombre, estado, mnemo, ...op } of CASOS) {
      const ctx = await nav.newContext(op);
      const caso = { nombre, revisiones: {}, errores: [], csp: [], mensajes: [], confirmaciones: [], borradas: [], insignias: 0,
        lecturas: 0, estado: estado || (mnemo ? ESTADO_MNEMO : ESTADO), respuestas: mnemo ? MENSAJES_MNEMO : MENSAJES };
      await ctx.route((u) => u.origin !== origen, (r) => r.abort()); // sin red: fuentes de Google, teselas
      if (modo === 'protocolo') await servirAgente(ctx, caso);
      await ctx.exposeBinding('__csp', (_, x) => caso.csp.push(x));
      await ctx.addInitScript(() => {
        addEventListener('securitypolicyviolation', (e) => window.__csp(`${e.effectiveDirective} ${e.blockedURI}`), true);
        window.__vistas = [];
        addEventListener('vista', (e) => window.__vistas.push(e.detail.ruta));
      });
      const page = await ctx.newPage();
      page.on('pageerror', (e) => caso.errores.push(String(e)));
      page.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) caso.errores.push(m.text()); });
      // El 401 de GET /api/yo antes de ingresar es la pregunta del arranque («¿hay sesión?»): no es un error
      page.on('response', (x) => {
        if (x.status() >= 400 && !(x.status() === 401 && x.url().endsWith('/api/yo')) && x.headers()['x-prueba'] !== 'esperado') caso.errores.push(`${x.status()} ${x.url()}`);
      });
      page.on('request', (x) => { if (new URL(x.url()).pathname === pref + '/api/insignias') caso.insignias++; });
      try {
        if (nombre === 'sin_modelo') await sinModelo(page, caso);
        else if (nombre === 'mnemo') await conMnemo(page, caso);
        else if (modo === 'protocolo') await protocolo(page, op, caso);
        else if (modo === 'real_mnemo') await realMnemo(page, caso);
        else await real(page, caso);
      } catch (e) {
        caso.revisiones.sin_excepcion = String(e.stack || e).slice(0, 1500);
        try { await page.screenshot({ path: `${capturas}/agente-${nombre}-fallo.png` }); } catch { /* nada */ }
      }
      delete caso.estado;
      delete caso.respuestas;
      res.casos.push(caso);
      await ctx.close();
    }
  } finally { await nav.close(); }
  console.log(JSON.stringify(res));
})().catch((e) => { console.error(e); process.exit(1); });
"""


# ───────────────────────────── Conectar Mnemo desde Ajustes (OAuth de punta a punta) ─────────────────────────────

class _Registro:
    """Delante del panel: anota de cada petición el método, la ruta, si traía la vuelta de Mnemo en la consulta (sin
    guardar sus valores), si traía la cookie de sesión (sin su valor) y `Sec-Fetch-Site`/`Sec-Fetch-Mode`."""

    def __init__(self, app):
        self.app = app
        self.peticiones: list[dict] = []

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            cab = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
            consulta = parse_qs(scope.get("query_string", b"").decode("latin-1"))
            self.peticiones.append({"metodo": scope["method"], "ruta": scope["path"],
                                    "vuelta": "state" in consulta and ("code" in consulta or "error" in consulta),
                                    "sesion": "yj_sesion=" in cab.get("cookie", ""),
                                    "sitio": cab.get("sec-fetch-site"), "modo": cab.get("sec-fetch-mode")})
        return await self.app(scope, receive, send)


class _ConPermisos:
    """El `OAuthFalso` (ayudas_mcp.py) con una página de permisos en el origen de Mnemo, como la de verdad: GET
    /oauth/authorize muestra los permisos pedidos (casillas, todas marcadas) con «Permitir» y «Cancelar», y el
    formulario (un POST al mismo origen) responde 303 a la vuelta que arma `OAuthFalso.autorizar` (con `code`, `state`
    e `iss`, o con `error=access_denied`). Así la vuelta al panel la empieza una página de Mnemo, como en producción:
    es una navegación de otro sitio y la cookie SameSite=Strict del panel no viaja en ella."""

    def __init__(self, falso):
        self.falso = falso
        self.paginas = 0

    @staticmethod
    async def _responder(send, estado: int, cuerpo: str = "", cabeceras: list | None = None) -> None:
        crudo = cuerpo.encode()
        await send({"type": "http.response.start", "status": estado, "headers": [
            (b"content-type", b"text/html; charset=utf-8"), (b"content-length", str(len(crudo)).encode()),
            *(cabeceras or [])]})
        await send({"type": "http.response.body", "body": crudo})

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] == "/oauth/authorize" and scope["method"] == "GET":
            consulta = dict(parse_qsl(scope.get("query_string", b"").decode()))
            self.paginas += 1
            pedidos = [a for a in (consulta.get("scope") or "").split() if a.startswith("mnemo:")]
            casillas = "".join(f'<label><input type="checkbox" name="scope" value="{html.escape(a)}" checked> '
                               f'{html.escape(a)}</label><br>' for a in pedidos)
            pagina = (f'<!doctype html><meta charset="utf-8"><title>Mnemo</title>'
                      f'<h1>{html.escape(self.falso.base)} quiere usar tu Mnemo</h1>'
                      f'<form method="post" action="/oauth/permitir">'
                      f'<input type="hidden" name="consulta" value="{html.escape(json.dumps(consulta))}">{casillas}'
                      f'<button id="permitir" name="decision" value="allow">Permitir</button> '
                      f'<button id="cancelar" name="decision" value="deny">Cancelar</button></form>')
            return await self._responder(send, 200, pagina)
        if scope["type"] == "http" and scope["path"] == "/oauth/permitir" and scope["method"] == "POST":
            cuerpo = b""
            while True:
                m = await receive()
                cuerpo += m.get("body", b"")
                if not m.get("more_body"):
                    break
            form = parse_qs(cuerpo.decode())
            self.falso.decision = "allow" if form.get("decision") == ["allow"] else "deny"
            self.falso.marcar = set(form.get("scope", []))
            try:
                estado, destino = self.falso.autorizar(json.loads(form["consulta"][0]))
            finally:
                self.falso.decision, self.falso.marcar = "allow", None
            if estado != 302:
                return await self._responder(send, estado, destino)
            return await self._responder(send, 303, "", [(b"location", destino.encode())])
        return await self.falso(scope, receive, send)


@pytest.fixture
def panel_y_mnemo(cfg, tmp_path):
    """El panel de verdad (con `_Registro` delante) en 127.0.0.1 y un Mnemo falso por red (`OAuthFalso` con su página
    de permisos) en `http://localhost:<puerto>`: otro sitio para el navegador, como en producción. El panel habla con
    él por red, sin transporte inyectado. Da (base del panel, app del panel, el OAuthFalso, el registro de las
    peticiones al panel, la página de permisos)."""
    from ayudas_mcp import EnHilo, OAuthFalso
    falso = OAuthFalso()
    permisos = _ConPermisos(falso)
    with EnHilo(permisos) as mnemo:
        falso.base = f"http://localhost:{urlsplit(mnemo.url).port}"
        with _servir(cfg, tmp_path, envolver=_Registro) as (base, panel, _, registro):
            yield base, panel, falso, registro, permisos


@requiere_navegador
def test_conectar_mnemo_desde_ajustes(panel_y_mnemo, cfg, tmp_path):
    base, panel, falso, registro, permisos = panel_y_mnemo
    db = panel.state.db
    coord = crear_usuario(db, "planillero")  # se pasa a coordinador en la base, como ayudas_g3.coordinador
    nombre = f"coordinador{coord['_id']}"
    db.usuarios.update_one({"_id": coord["_id"]}, {"$set": {"rol": "coordinador", "usuario": nombre}})
    res = _correr(GUION_MNEMO, tmp_path, base, cfg.usuario, cfg.clave, "mnemo", falso.recurso, nombre, CLAVE_USUARIO)
    (caso,) = res["casos"]
    _revisar(caso)
    d = caso["datos"]
    # La dirección de autorización que armó el panel: PKCE S256, el recurso, la vuelta a Ajustes y los alcances
    a = d["autorizar"]
    assert a["ruta"] == "/oauth/authorize" and a["response_type"] == "code" and a["code_challenge_method"] == "S256"
    assert a["redirect_uri"] == base + "/ajustes" and a["resource"] == falso.recurso and a["state_largo"] >= 40
    assert {"openid", "profile", "email", "mnemo:model", "mnemo:read"} <= set(a["scope"].split())
    assert "mnemo:forms.responses" not in a["scope"]
    # Tres vueltas (cancelar, permitir y permitir sin los modelos): cada navegación de vuelta llegó desde otro sitio y
    # SIN la cookie de sesión; el POST a /volver que hizo la página después, CON ella
    vueltas = [p for p in registro.peticiones if p["metodo"] == "GET" and p["ruta"] == "/panel/ajustes" and p["vuelta"]]
    assert len(vueltas) == 3, vueltas
    assert all(not p["sesion"] and p["sitio"] == "cross-site" and p["modo"] == "navigate" for p in vueltas), vueltas
    volver = [p for p in registro.peticiones if p["ruta"] == "/panel/api/agente/mnemo/volver"]
    assert len(volver) == 3
    assert all(p["metodo"] == "POST" and p["sesion"] and p["sitio"] == "same-origin" for p in volver), volver
    assert permisos.paginas == 3
    # El panel se registró una vez y reusó el cliente; canjeó cada código con PKCE; reconectar la misma cuenta no
    # revocó nada; desconectar revocó con el token de renovación (nunca con el de acceso)
    assert falso.registros == 1
    canjes = [p["form"] for p in falso.peticiones
              if p["ruta"] == "/oauth/token" and (p["form"] or {}).get("grant_type") == "authorization_code"]
    assert len(canjes) == 2 and all(c.get("code_verifier") and c["redirect_uri"] == base + "/ajustes" for c in canjes)
    assert [(r["tipo"], r["token_type_hint"]) for r in falso.revocaciones] == [("refresh", "refresh_token")]
    # En la base: sin conexión, sin tokens a la vista y la auditoría de cada paso
    doc = db.meta.find_one({"_id": "mnemo_conexion"}) or {}
    assert "estado" not in doc and "cifrado" not in doc and not doc.get("pendiente")
    acciones = [a["accion"] for a in db.auditoria.find({"accion": {"$regex": "^mnemo_"}}, sort=[("_id", 1)])]
    assert acciones == ["mnemo_conectar", "mnemo_conectar", "mnemo_desconectar"], acciones


GUION_MNEMO = r"""// Conectar Mnemo desde Ajustes en Chromium, contra un Mnemo falso en otro sitio.
// Uso: node <guion> <base del panel> <usuario> <clave> mnemo <dirección MCP de Mnemo> <coordinador> <su clave> <capturas>
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const [base, usuario, clave, modo, mcp, coordUsuario, coordClave, capturas] = process.argv.slice(2);
const origen = new URL(base).origin;
const origenMnemo = new URL(mcp).origin;
const pref = new URL(base).pathname.replace(/\/+$/, '');
const espera = { timeout: 20000 };

async function abrir(nav, caso, quien) {
  const ctx = await nav.newContext({ viewport: { width: 1280, height: 900 } });
  await ctx.route((u) => u.origin !== origen && u.origin !== origenMnemo, (r) => r.abort()); // sin red: fuentes, teselas
  await ctx.exposeBinding('__csp', (_, x) => caso.csp.push(`${quien}: ${x}`));
  await ctx.addInitScript((o) => {
    if (location.origin !== o) return;
    addEventListener('securitypolicyviolation', (e) => window.__csp(`${e.effectiveDirective} ${e.blockedURI}`), true);
    // Lo que hace la página, en orden: cada history.replaceState (ruta y consulta) y cada fetch (método y ruta)
    const orden = (window.__orden = []);
    window.__llegoConVuelta = /[?&]state=/.test(location.search) && /[?&](code|error)=/.test(location.search);
    const reemplazar = history.replaceState;
    history.replaceState = function (s, t, u) {
      const d = new URL(String(u), location.href);
      orden.push(`replaceState ${d.pathname}${d.search}`);
      return reemplazar.apply(this, arguments);
    };
    const pedir = window.fetch;
    window.fetch = function (u, op) {
      orden.push(`${(op && op.method) || 'GET'} ${new URL(String(u), location.href).pathname}`);
      return pedir.apply(this, arguments);
    };
  }, origen);
  const page = await ctx.newPage();
  page.on('pageerror', (e) => caso.errores.push(`${quien}: ${e}`));
  page.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) caso.errores.push(`${quien}: ${m.text()}`); });
  page.on('response', (x) => {
    const u = new URL(x.url());
    if (u.origin !== origen || x.status() < 400) return;
    if (x.status() === 401 && u.pathname === pref + '/api/yo') return; // la pregunta del arranque («¿hay sesión?»)
    const r = `${x.status()} ${u.pathname}`;
    const i = caso.esperados.indexOf(r);
    if (i >= 0) caso.esperados.splice(i, 1);
    else caso.errores.push(`${quien}: ${r}`);
  });
  return { ctx, page };
}

async function ingresar(page, u, c) {
  await page.goto(base + '/', { waitUntil: 'domcontentloaded' });
  await page.fill('#f-login [name=usuario]', u);
  await page.fill('#f-login [name=clave]', c);
  await page.click('#f-login button[type=submit]');
  await page.waitForSelector('#app #vista > .vista', espera);
  await page.click('#nav a[data-nav="ajustes"]');
  await page.waitForSelector('#mnemo-conexion', espera);
}

const bloque = (page) => page.evaluate(() => {
  const b = document.querySelector('#mnemo-conexion');
  return b && { estado: b.dataset.estado, texto: b.textContent.replace(/\s+/g, ' ').trim(),
    botones: [...b.querySelectorAll('button')].map((x) => x.textContent.trim()),
    campo: b.querySelector('#f-mnemo [name=url]')?.value ?? null,
    permisos: [...b.querySelectorAll('.chips .chip')].map((x) => x.textContent.trim()),
    resultado: b.querySelector('.mnemo-nota.resultado')?.textContent ?? null,
    sinModelos: b.querySelector('.mnemo-nota.alerta:not(.resultado)')?.textContent ?? null };
});

// «Conectar con Mnemo» (o «Volver a conectar»): la página de permisos de Mnemo, la decisión y la vuelta a Ajustes
async function conectar(page, caso, decision, { sinModelos = false } = {}) {
  await page.fill('#f-mnemo [name=url]', mcp);
  await page.click('#mnemo-conectar');
  await page.waitForURL((u) => u.origin === origenMnemo, espera); // location.assign a la autorización de Mnemo
  if (!caso.datos.autorizar) {
    const a = new URL(page.url());
    const q = a.searchParams;
    caso.datos.autorizar = { ruta: a.pathname, response_type: q.get('response_type'), code_challenge_method: q.get('code_challenge_method'),
      con_reto: !!q.get('code_challenge'), redirect_uri: q.get('redirect_uri'), resource: q.get('resource'), scope: q.get('scope'),
      state_largo: (q.get('state') || '').length };
  }
  await page.waitForSelector('#permitir', espera);
  if (sinModelos) await page.uncheck('input[name=scope][value="mnemo:model"]');
  await page.click(decision === 'permitir' ? '#permitir' : '#cancelar');
  // De vuelta en Ajustes: la página quitó la vuelta de la dirección y, después del POST a /volver, pintó la conexión
  await page.waitForURL((u) => u.origin === origen && u.pathname === pref + '/ajustes', espera);
  await page.waitForSelector('#mnemo-conexion', espera);
  const o = await page.evaluate(() => ({ orden: window.__orden, llego: window.__llegoConVuelta, ruta: location.pathname + location.search }));
  const i = o.orden.indexOf(`replaceState ${pref}/ajustes`);
  const j = o.orden.indexOf(`POST ${pref}/api/agente/mnemo/volver`);
  return { orden: o.orden, ruta: o.ruta,
    vuelta_quitada_antes: o.llego && i >= 0 && j > i && o.ruta === pref + '/ajustes' && o.orden.filter((x) => x.includes('/mnemo/volver')).length === 1 };
}

(async () => {
  const nav = await chromium.launch();
  const caso = { nombre: 'mnemo', revisiones: {}, errores: [], csp: [], datos: {}, esperados: [] };
  const v = caso.revisiones;
  try {
    const { ctx, page } = await abrir(nav, caso, 'administrador');
    await ingresar(page, usuario, clave);
    let b = await bloque(page);
    caso.datos.inicio = b;
    v.empieza_sin_conectar = b.estado === 'sin_conectar' && JSON.stringify(b.botones) === '["Conectar con Mnemo"]' && b.campo === '';
    await page.locator('#mnemo-conexion').screenshot({ path: `${capturas}/ajustes-mnemo-sin-conectar.png` });

    // 1. «Cancelar» en Mnemo: vuelve con error=access_denied (el panel responde 400 a /volver) y no conecta nada
    caso.esperados.push(`400 ${pref}/api/agente/mnemo/volver`);
    let r = await conectar(page, caso, 'cancelar');
    b = await bloque(page);
    caso.datos.cancelar = { ...r, bloque: b };
    v.cancelar_no_conecta = r.vuelta_quitada_antes && b.estado === 'sin_conectar' && b.resultado === 'Se canceló el permiso en Mnemo: no se conectó nada.';

    // 2. «Permitir»: «Conectado como …», con los permisos y los botones del administrador
    r = await conectar(page, caso, 'permitir');
    b = await bloque(page);
    caso.datos.permitir = { ...r, bloque: b };
    v.conectado = r.vuelta_quitada_antes && b.estado === 'conectada' && b.texto.includes('Conectado como Ana Inventada (ana.inventada@example.org) desde')
      && b.texto.includes(`Dirección: ${mcp}`) && b.permisos.includes('Usar sus modelos de IA y sus créditos') && b.sinModelos === null
      && b.resultado === null && JSON.stringify(b.botones) === '["Volver a conectar","Desconectar"]' && b.campo === mcp;
    await page.locator('#mnemo-conexion').screenshot({ path: `${capturas}/ajustes-mnemo-conectado.png` });
    await page.screenshot({ path: `${capturas}/ajustes-mnemo.png`, fullPage: false });
    // En el celular el bloque cabe sin desbordar la página
    await page.setViewportSize({ width: 360, height: 780 });
    await page.waitForTimeout(400); // la transición del menú lateral al pasar al diseño del celular (.25 s)
    await page.locator('#mnemo-conexion').scrollIntoViewIfNeeded();
    v.celular_sin_desborde = await page.evaluate(() => {
      const r = document.querySelector('#mnemo-conexion').getBoundingClientRect();
      return document.documentElement.scrollWidth <= innerWidth && r.left >= 0 && r.right <= innerWidth;
    });
    await page.locator('#mnemo-conexion').screenshot({ path: `${capturas}/ajustes-mnemo-celular.png` });
    await page.setViewportSize({ width: 1280, height: 900 });

    // 3. El coordinador ve el estado, sin la dirección ni los botones
    const k = await abrir(nav, caso, 'coordinador');
    await ingresar(k.page, coordUsuario, coordClave);
    const bk = await bloque(k.page);
    caso.datos.coordinador = bk;
    v.coordinador_solo_ve = bk.estado === 'conectada' && bk.texto.includes('Conectado como Ana Inventada (ana.inventada@example.org)')
      && bk.botones.length === 0 && bk.campo === null && bk.texto.includes('Solo el administrador conecta o desconecta Mnemo.');
    await k.page.locator('#mnemo-conexion').screenshot({ path: `${capturas}/ajustes-mnemo-coordinador.png` });
    await k.ctx.close();

    // 4. «Volver a conectar» sin marcar el permiso de los modelos: Ajustes lo avisa
    r = await conectar(page, caso, 'permitir', { sinModelos: true });
    b = await bloque(page);
    caso.datos.sin_modelos = { ...r, bloque: b };
    v.avisa_sin_modelos = r.vuelta_quitada_antes && b.estado === 'conectada' && !b.permisos.includes('Usar sus modelos de IA y sus créditos')
      && (b.sinModelos || '').startsWith('Mnemo se conectó sin permiso para usar sus modelos: vuelva a conectar y marque esa casilla');

    // 5. «Desconectar», con confirmación
    await page.click('#mnemo-desconectar');
    await page.waitForSelector('dialog[open] [data-si]', espera);
    v.pide_confirmacion = (await page.textContent('dialog[open]')).includes('¿Desconectar Mnemo?');
    await page.click('dialog[open] [data-si]');
    await page.waitForFunction(() => document.querySelector('#mnemo-conexion')?.dataset.estado === 'sin_conectar', null, espera);
    b = await bloque(page);
    caso.datos.desconectado = b;
    v.desconectado = JSON.stringify(b.botones) === '["Conectar con Mnemo"]' && b.campo === mcp && b.resultado === null;
    v.respuestas_esperadas = caso.esperados.length === 0;
    await ctx.close();
  } catch (e) {
    v.sin_excepcion = String(e.stack || e).slice(0, 1500);
  } finally {
    await nav.close();
  }
  console.log(JSON.stringify({ casos: [caso] }));
})().catch((e) => { console.error(e); process.exit(1); });
"""
