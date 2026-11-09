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
  - `sin_modelo`: el administrador sin modelo (Mnemo sin conectar, con la conexión caída, sin permiso para usar sus
    modelos o con un Mnemo que todavía no los ofrece) ve el botón y adentro qué hacer, sin nombres de variables, sin
    mandar a marcar una casilla que puede no estar y con un enlace a Ajustes, que muestra la conexión con sus botones.
    «Conectar con Mnemo» contra un Mnemo sin actualizar (400 `sin_modelo`: no ofrece «Usar tus modelos…») lo dice en
    el bloque y en un aviso, sin ir a ninguna parte.
  - `mnemo`: con Mnemo como modelo, `texto_ronda` reemplaza el texto que llegó por partes; un solo trozo de más de
    4 000 caracteres llega entero; la conexión caída vuelve a leer el estado; `proveedor` (409) ofrece «Nueva
    conversación» con el mensaje escrito; `mnemo_creditos` no ofrece «Reintentar»; `llm_peticion` ofrece «Reintentar»
    (que repite el mensaje) y «Nueva conversación»; `mnemo_sin_modelo` ofrece «Reintentar» y vuelve a leer el estado.
    Quien no es el administrador y se queda sin modelo a mitad ve qué pasó, sin que el panel se cierre de golpe. El
    contexto no lleva `code`, `state` ni `iss`.
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
  «Conectado como …». El asistente se entera sin recargar la página: el abierto a medio conectar pasa solo de «no está
  conectado» a «Nueva conversación», el de otra pestaña al abrirlo, y tras volver a conectar sin el permiso de los
  modelos (o desconectar) dice qué falta (el POST a /volver se retiene hasta que el asistente leyó su estado, como pasa
  en producción). El coordinador ve el estado sin botones; volver a conectar sin el permiso de los modelos lo avisa;
  «Desconectar» (con confirmación) revoca con el token de renovación.
* `test_punta_a_punta_con_mnemo_de_verdad` (opcional: se salta sin `MNEMO_E2E_DIR`): lo mismo contra un Mnemo de verdad
  en local (su API, su OAuth y su página de permisos, con un modelo con guion): conectar, conversar con el modelo de
  Mnemo usando una herramienta del panel (el texto llega por partes), volver a conectar sin y con el permiso de los
  modelos, seguir la conversación y desconectar (la conexión queda revocada en Mnemo).

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
            # El estado lo leyeron la vista y el widget, cuatro veces (y el widget otra vez al abrirlo sin modelo);
            # ningún mensaje. «Conectar con Mnemo» pidió la autorización una vez (y el panel respondió que ese Mnemo no
            # ofrece sus modelos)
            assert caso["mensajes"] == [] and caso["lecturas"] >= 8, caso["lecturas"]
            assert caso["conectar"] == [{}], caso["conectar"]
            continue
        if caso["nombre"] == "mnemo":
            mensajes = caso["mensajes"]
            assert len(mensajes) == 9 and all(m["csrf"] for m in mensajes)
            # El contexto solo lleva los filtros conocidos: nada de lo que trae la vuelta de Mnemo
            ctx = mensajes[0]["cuerpo"]["contexto"]
            assert ctx["ruta"] == "/reuniones" and ctx["filtros"] == {"zona": "rural"}, ctx
            assert [m["cuerpo"]["conversacion"] for m in mensajes] == [None, 51, 51, 51, None, 52, 52, 52, 52]
            # «Nueva conversación» trajo escrito el mensaje que no llegó (409 proveedor)
            assert mensajes[4]["cuerpo"]["texto"] == mensajes[3]["cuerpo"]["texto"] == "¿Y las reuniones de mañana?"
            # «Reintentar» tras `llm_peticion` repite el mismo mensaje en la misma conversación
            assert mensajes[6]["cuerpo"]["texto"] == mensajes[5]["cuerpo"]["texto"] == "Último"
            assert caso["lecturas"] >= 5  # al cargar dos veces, tras cada mnemo_conexion y tras mnemo_sin_modelo
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
// Lo que responde POST /api/agente/mnemo/conectar (400 `sin_modelo`, `mnemo_conexion.MENSAJE_SIN_MODELO`) con un Mnemo que
// no ofrece «Usar tus modelos…»
const SIN_MODELO_EN_MNEMO = 'Este Mnemo todavía no ofrece «Usar tus modelos de IA y tus créditos», que es lo que usa el asistente: hay que actualizar Mnemo (desplegar su última versión) y volver a conectar.';
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
// Un texto de 6 799 caracteres en un solo trozo: con Mnemo llega así si el proveedor de la cuenta no responde por partes
const LARGO = Array.from({ length: 200 }, (_, i) => `Línea ${String(i).padStart(4, '0')} de la respuesta larga.`).join('\n');
const MENSAJES_MNEMO = [
  // Tres rondas: los trozos de texto son un adelanto y el texto final de cada ronda (`texto_ronda`) lo reemplaza; en la
  // segunda no llegó ningún trozo y su texto va antes de su herramienta
  [{ tipo: 'inicio', conversacion: 51, titulo: 'Reuniones' },
    { tipo: 'texto', texto: 'Hola, mund' }, { tipo: 'texto', texto: 'o. Voy a busc' },
    { tipo: 'texto_ronda', texto: 'Hola, mundo. Voy a buscar a **Ana**.' }, HM('toolu_m1', 'inicio'), HM('toolu_m1', 'ok', '1 persona'),
    HM('toolu_m2', 'inicio'), { tipo: 'texto_ronda', texto: 'Encontré a Ana Inventada.' }, HM('toolu_m2', 'ok', '1 persona'),
    { tipo: 'texto', texto: 'Listo, ya est' }, { tipo: 'texto_ronda', texto: 'Listo.' },
    { tipo: 'fin', motivo: 'listo', limite: { usados: 4, maximo: 300 } }],
  // Todo el texto de la ronda en un solo trozo, sin `texto_ronda` (coincide con lo emitido): llega entero
  [{ tipo: 'inicio', conversacion: 51, titulo: 'Reuniones' }, { tipo: 'texto', texto: LARGO },
    { tipo: 'fin', motivo: 'listo', limite: { usados: 5, maximo: 300 } }],
  errorDe(51, 'mnemo_conexion', 'La conexión con Mnemo venció o se revocó: el administrador tiene que volver a conectarla en Ajustes → Asistente.'),
  { estado: 409, detail: { codigo: 'proveedor', mensaje: 'Esta conversación se empezó con un modelo que ya no está disponible: empiece una nueva.' } },
  errorDe(52, 'mnemo_creditos', 'A la cuenta de Mnemo se le acabaron los créditos.'),
  // Rechazada (con Mnemo, también una sobrecarga del proveedor a mitad de la respuesta): «Reintentar» la repite y sale
  errorDe(52, 'llm_peticion', 'El modelo rechazó la petición. Si se repite, empiece otra conversación.'),
  [{ tipo: 'inicio', conversacion: 52, titulo: 'Reuniones' }, { tipo: 'texto', texto: 'Esta vez sí respondió.' },
    { tipo: 'fin', motivo: 'listo', limite: { usados: 10, maximo: 300 } }],
  errorDe(52, 'mnemo_sin_modelo', 'La cuenta de Mnemo conectada no tiene un modelo disponible ahora (sin un modelo configurado, con su clave rechazada o con el proveedor caído). Si se repite, avise al administrador.'),
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
    // «Conectar con Mnemo» contra un Mnemo sin actualizar: no ofrece «Usar tus modelos…» y el panel no sigue
    if (metodo === 'POST' && ruta === '/api/agente/mnemo/conectar') {
      reg.conectar.push(req.postDataJSON());
      return route.fulfill({ status: 400, contentType: 'application/json', headers: { 'x-prueba': 'esperado' },
        body: JSON.stringify({ detail: { codigo: 'sin_modelo', mensaje: SIN_MODELO_EN_MNEMO } }) });
    }
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
  // «Conectar con Mnemo» contra un Mnemo sin actualizar: el panel responde 400 `sin_modelo` y la página lo dice en el
  // bloque (con el mensaje tal cual) y en un aviso, sin ir a ninguna parte; el botón sirve otra vez. El panel del
  // asistente se cierra para no tapar nada y se vuelve a abrir después (así vuelve abierto al recargar)
  await page.click('#agente-cerrar');
  await page.click('#mnemo-conectar');
  await page.waitForSelector('#mnemo-conexion .mnemo-nota.resultado.error', espera);
  const n = await page.evaluate(() => {
    const nota = document.querySelector('#mnemo-conexion .mnemo-nota.resultado.error');
    const r = nota.getBoundingClientRect();
    const caja = document.querySelector('#mnemo-conexion').getBoundingClientRect();
    const boton = document.querySelector('#mnemo-conectar');
    return { nota: nota.textContent, rol: nota.getAttribute('role'), visible: r.width > 0 && r.height > 0 && r.left >= caja.left && r.right <= caja.right,
      avisos: [...document.querySelectorAll('#avisos .aviso.error')].map((x) => x.textContent), boton: boton.textContent.trim(), habilitado: !boton.disabled,
      ruta: location.pathname, desborde: document.documentElement.scrollWidth > innerWidth };
  });
  caso.datos.conectar_sin_modelo = n;
  v.conectar_sin_modelo_en_mnemo = n.nota === SIN_MODELO_EN_MNEMO && n.rol === 'alert' && n.visible && n.avisos.includes(SIN_MODELO_EN_MNEMO)
    && n.boton === 'Conectar con Mnemo' && n.habilitado && n.ruta === pref + '/ajustes' && !n.desborde;
  await page.locator('#mnemo-conexion').screenshot({ path: `${capturas}/ajustes-mnemo-sin-modelo-en-mnemo.png` });
  await page.click('#agente-boton');
  await page.waitForSelector('#agente-panel:not([hidden]) .agente-explicacion', espera);
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
  // Volver a conectar dejándolo marcado; si ese Mnemo no lo muestra, actualizarlo (nunca «marque la casilla» a secas)
  const sinCasilla = (t) => !/marque|marcar la casilla/i.test(t) && t.includes('Si Mnemo no muestra esa casilla, hay que actualizar Mnemo.');
  v.explica_sin_permiso = e.titulo === 'Mnemo está conectado sin permiso para usar sus modelos' && e.sub === 'Sin permiso para usar los modelos'
    && e.texto.includes('Vuelva a conectar en Ajustes → Asistente, dejando marcado «Usar tus modelos de IA y tus créditos» en la página de permisos de Mnemo.')
    && sinCasilla(e.texto) && sinVariables(e.texto) && enlaceBueno(e);
  v.ajustes_sin_permiso = b.estado === 'conectada' && b.texto.includes('Conectado como Ana Inventada (ana.inventada@example.org)')
    && b.texto.includes('Mnemo se conectó sin permiso para usar sus modelos: vuelva a conectar dejando marcado «Usar tus modelos de IA y tus créditos».')
    && sinCasilla(b.texto) && !b.texto.includes('Usar sus modelos de IA y sus créditos') && JSON.stringify(b.botones) === '["Volver a conectar","Desconectar"]';
  await page.locator('#mnemo-conexion').screenshot({ path: `${capturas}/ajustes-mnemo-sin-permiso.png` });
  // 4. Conectado con un Mnemo que todavía no ofrece usar sus modelos (se conectó así para sus herramientas, en modo
  // directo, y la clave ya no está): no hay casilla que marcar, hay que actualizar Mnemo
  caso.estado = SIN_MODELO({ ...SIN_PERMISO, ofrece_modelo: false });
  await page.reload({ waitUntil: 'domcontentloaded' });
  e = await explicacion();
  b = await bloque();
  caso.datos.no_ofrece = { e, b };
  v.explica_que_mnemo_no_ofrece = e.titulo === 'Mnemo todavía no ofrece sus modelos' && e.sub === 'Mnemo sin actualizar'
    && e.texto.includes('hay que actualizar Mnemo y volver a conectar en Ajustes → Asistente.') && sinVariables(e.texto) && enlaceBueno(e);
  v.ajustes_no_ofrece = b.texto.includes('Este Mnemo todavía no ofrece «Usar tus modelos de IA y tus créditos»: el asistente usa sus '
    + 'herramientas, pero no sus modelos. Para usarlos hay que actualizar Mnemo y volver a conectar.') && !b.texto.includes('dejando marcado');
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
  // 1b. Un solo trozo de más de 4 000 caracteres (todo el texto de la ronda) se pinta entero: nada lo corrige después
  await enviar(page, 'Dame el informe completo');
  await page.waitForFunction(() => document.querySelectorAll('.agente-msj.agente-respuesta').length === 2
    && document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);
  const largo = await page.evaluate(() => {
    const md = [...document.querySelectorAll('.agente-msj.agente-respuesta')].pop().querySelector('.agente-md');
    return md && { lineas: md.querySelectorAll('br').length + 1, principio: md.textContent.slice(0, 33), final: md.textContent.slice(-33),
      largo: md.textContent.length };
  });
  caso.datos.largo = largo;
  v.trozo_largo_entero = !!largo && largo.lineas === 200 && largo.principio === 'Línea 0000 de la respuesta larga.'
    && largo.final === 'Línea 0199 de la respuesta larga.' && largo.largo === LARGO.length - 199;
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
  // 5. Petición rechazada (puede ser pasajera): «Reintentar», que repite el mensaje, y «Nueva conversación»
  await enviar(page, 'Último');
  await page.waitForFunction(() => document.querySelectorAll('.agente-error').length === 2 && document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);
  err = await ultimoError();
  caso.datos.peticion = err;
  v.peticion_ofrece_reintentar_y_otra = JSON.stringify(err.botones) === '["Reintentar","Nueva conversación"]';
  await page.screenshot({ path: `${capturas}/agente-mnemo.png` });
  await page.locator('.agente-error').last().locator('button', { hasText: 'Reintentar' }).click();
  await page.waitForFunction(() => [...document.querySelectorAll('.agente-md')].pop()?.textContent === 'Esta vez sí respondió.'
    && document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);
  v.reintentar_repite_el_mensaje = await page.evaluate(() => document.querySelectorAll('.agente-error').length === 1
    && [...document.querySelectorAll('.agente-msj.agente-persona p')].filter((p) => p.textContent === 'Último').length === 2);
  // 6. Sin un modelo disponible ahora en la cuenta (también si su proveedor se cayó un momento): «Reintentar», y el
  // estado se vuelve a leer
  const antesSinModelo = caso.lecturas;
  await enviar(page, '¿Y mañana?');
  await page.waitForFunction(() => document.querySelectorAll('.agente-error').length === 2 && document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);
  for (let i = 0; i < 100 && caso.lecturas === antesSinModelo; i++) await page.waitForTimeout(50);
  err = await ultimoError();
  caso.datos.sin_modelo = err;
  v.sin_modelo_ofrece_reintentar = err.texto.includes('no tiene un modelo disponible ahora') && JSON.stringify(err.botones) === '["Reintentar"]'
    && caso.lecturas === antesSinModelo + 1;
  // 7. Quien no es el administrador se queda sin modelo a mitad (la conexión se cayó y no hay otro): el panel no se
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
      const caso = { nombre, revisiones: {}, errores: [], csp: [], mensajes: [], confirmaciones: [], borradas: [], conectar: [],
        insignias: 0, lecturas: 0, estado: estado || (mnemo ? ESTADO_MNEMO : ESTADO), respuestas: mnemo ? MENSAJES_MNEMO : MENSAJES };
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

// Lo que muestra el asistente (abierto o no) y si llega a mostrar algo antes del plazo
const asistente = (page) => page.evaluate(() => {
  const ex = document.querySelector('#agente-mensajes .agente-explicacion');
  return { abierto: !document.querySelector('#agente-panel').hidden, sub: document.querySelector('#agente-sub').textContent,
    titulo: ex?.querySelector('h3')?.textContent ?? null, texto: ex?.textContent ?? null,
    bienvenida: !!document.querySelector('#agente-mensajes .agente-bienvenida'), compositor: !document.querySelector('#agente-form').hidden };
});
const llega = (page, fn) => page.waitForFunction(fn, null, espera).then(() => true, () => false);

// «Conectar con Mnemo» (o «Volver a conectar»): la página de permisos de Mnemo, la decisión y la vuelta a Ajustes. Al
// volver, el asistente lee su estado a la vez que la página canjea el código y, en producción, esa lectura suele
// responderse antes, con el estado de antes de conectar. Aquí siempre: el POST a /volver sale recién cuando el servidor
// respondió esa lectura. Por defecto la lectura llega al asistente antes del POST (y la prueba hace `durante` con la
// página a medio conectar); con `enVuelo`, llega después de que Ajustes le avisó que se conectó: el asistente tiene que
// esperarla y pedir otra
async function conectar(page, caso, decision, { sinModelos = false, durante = null, enVuelo = false } = {}) {
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
  // Solo la primera de cada una (el resto pasa sin más). Sin `times`: al vencer una ruta con otra retenida, Playwright
  // soltaría la retenida
  let soltarVolver, soltarLectura, leida;
  const volverSuelto = new Promise((listo) => { soltarVolver = listo; });
  const lecturaSuelta = new Promise((listo) => { soltarLectura = listo; });
  const respondida = new Promise((listo) => { leida = listo; });
  const esVolver = (u) => u.pathname === pref + '/api/agente/mnemo/volver';
  const esEstado = (u) => u.pathname === pref + '/api/agente/estado';
  let volverVisto = false, estadoVisto = false;
  const alVolver = async (r) => {
    if (volverVisto) return r.fallback();
    volverVisto = true;
    await volverSuelto;
    await r.continue();
  };
  const alEstado = async (r) => {
    if (estadoVisto) return r.fallback();
    estadoVisto = true;
    const respuesta = await r.fetch(); // la responde el servidor con lo de antes: el POST a /volver todavía no salió
    leida();
    await lecturaSuelta;
    await r.fulfill({ response: respuesta });
  };
  await page.route(esVolver, alVolver);
  await page.route(esEstado, alEstado);
  const recibida = page.waitForResponse((x) => esEstado(new URL(x.url())), espera);
  recibida.catch(() => {}); // con `enVuelo` no se espera: que un plazo vencido no tumbe el guion
  await page.click(decision === 'permitir' ? '#permitir' : '#cancelar');
  // De vuelta en Ajustes: la página quitó la vuelta de la dirección y, después del POST a /volver, pintó la conexión
  await page.waitForURL((u) => u.origin === origen && u.pathname === pref + '/ajustes', espera);
  try {
    await respondida;
    if (enVuelo) {
      await page.evaluate(() => { window.__avisado = new Promise((listo) => addEventListener('agente:estado', () => listo(true), { once: true })); });
      soltarVolver();
      caso.datos.avisado = await Promise.race([page.evaluate(() => window.__avisado), new Promise((listo) => setTimeout(() => listo(false), 15000))]);
    } else {
      soltarLectura();
      await recibida;
      if (durante) await durante();
    }
  } finally {
    soltarLectura();
    soltarVolver();
  }
  await page.waitForSelector('#mnemo-conexion', espera);
  await page.unroute(esVolver, alVolver);
  await page.unroute(esEstado, alEstado);
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

    // Otra pestaña del administrador, abierta antes de conectar: su asistente dice que no está conectado y no se entera
    // del aviso de esta (es otra página)
    const otra = await ctx.newPage();
    otra.on('pageerror', (e) => caso.errores.push(`otra pestaña: ${e}`));
    otra.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) caso.errores.push(`otra pestaña: ${m.text()}`); });
    await otra.goto(base + '/', { waitUntil: 'domcontentloaded' });
    await otra.waitForSelector('#agente-boton:not([hidden])', espera);
    await otra.evaluate(() => { window.__sinRecargar = true; });

    // 2. «Permitir»: «Conectado como …», con los permisos y los botones del administrador. Con la página a medio
    // conectar, el asistente (que ya leyó su estado: sin conectar) se abre y lo explica; cuando termina de conectar, pasa
    // solo a «Nueva conversación», sin recargar la página
    r = await conectar(page, caso, 'permitir', { durante: async () => {
      await page.click('#agente-boton');
      await page.waitForSelector('#agente-panel:not([hidden]) .agente-explicacion', espera);
      caso.datos.asistente_conectando = await asistente(page);
    } });
    b = await bloque(page);
    caso.datos.permitir = { ...r, bloque: b };
    v.conectado = r.vuelta_quitada_antes && b.estado === 'conectada' && b.texto.includes('Conectado como Ana Inventada (ana.inventada@example.org) desde')
      && b.texto.includes(`Dirección: ${mcp}`) && b.permisos.includes('Usar sus modelos de IA y sus créditos') && b.sinModelos === null
      && b.resultado === null && JSON.stringify(b.botones) === '["Volver a conectar","Desconectar"]' && b.campo === mcp;
    const conectando = caso.datos.asistente_conectando;
    const nueva = await llega(page, () => document.querySelector('#agente-sub').textContent === 'Nueva conversación'
      && !document.querySelector('#agente-form').hidden && !!document.querySelector('#agente-panel:not([hidden]) .agente-bienvenida'));
    caso.datos.asistente_conectado = await asistente(page);
    v.asistente_se_entera_al_conectar = conectando.titulo === 'El asistente no está conectado' && conectando.sub === 'Sin conectar'
      && !conectando.compositor && nueva;
    await page.screenshot({ path: `${capturas}/ajustes-mnemo-asistente-conectado.png` });
    await page.click('#agente-cerrar');
    // La otra pestaña, al abrir su asistente sin modelo, vuelve a preguntar: ya está conectado
    await otra.click('#agente-boton');
    const enLaOtra = await llega(otra, () => document.querySelector('#agente-sub').textContent === 'Nueva conversación'
      && !document.querySelector('#agente-form').hidden && !!document.querySelector('#agente-panel:not([hidden]) .agente-bienvenida'));
    caso.datos.otra_pestana = await asistente(otra);
    v.otra_pestana_al_abrir = enLaOtra && await otra.evaluate(() => window.__sinRecargar === true);
    await otra.close();
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

    // 3. El coordinador ve el estado, sin la dirección ni los botones, y sin la cuenta: el nombre y el correo son del
    // administrador (no le llegan, y el bloque dice «una cuenta de Mnemo»)
    const k = await abrir(nav, caso, 'coordinador');
    await ingresar(k.page, coordUsuario, coordClave);
    const bk = await bloque(k.page);
    caso.datos.coordinador = bk;
    v.coordinador_solo_ve = bk.estado === 'conectada' && bk.texto.includes('Conectado como una cuenta de Mnemo desde')
      && !bk.texto.includes('Ana Inventada') && !bk.texto.includes('ana.inventada@example.org') && bk.sinModelos === null
      && bk.botones.length === 0 && bk.campo === null && bk.texto.includes('Solo el administrador conecta o desconecta Mnemo.');
    await k.page.locator('#mnemo-conexion').screenshot({ path: `${capturas}/ajustes-mnemo-coordinador.png` });
    await k.ctx.close();

    // 4. «Volver a conectar» sin marcar el permiso de los modelos: Ajustes lo avisa (sin mandar a marcar una casilla que
    // puede no estar). El asistente leyó su estado con la conexión anterior (con los modelos), y esa lectura le llega
    // después del aviso de Ajustes: la espera, pide otra y, sin recargar, al abrirlo explica qué falta
    r = await conectar(page, caso, 'permitir', { sinModelos: true, enVuelo: true });
    b = await bloque(page);
    caso.datos.sin_modelos = { ...r, bloque: b };
    v.aviso_con_la_lectura_en_vuelo = caso.datos.avisado === true;
    v.avisa_sin_modelos = r.vuelta_quitada_antes && b.estado === 'conectada' && !b.permisos.includes('Usar sus modelos de IA y sus créditos')
      && b.sinModelos === 'Mnemo se conectó sin permiso para usar sus modelos: vuelva a conectar dejando marcado «Usar tus modelos de IA y '
        + 'tus créditos». Si Mnemo no muestra esa casilla, hay que actualizar Mnemo.';
    await page.click('#agente-boton');
    const sinPermiso = await llega(page, () => document.querySelector('#agente-sub').textContent === 'Sin permiso para usar los modelos'
      && !!document.querySelector('#agente-panel:not([hidden]) .agente-explicacion'));
    caso.datos.asistente_sin_modelos = await asistente(page);
    v.asistente_se_entera_sin_modelos = sinPermiso
      && (caso.datos.asistente_sin_modelos.texto || '').includes('Si Mnemo no muestra esa casilla, hay que actualizar Mnemo.');
    await page.click('#agente-cerrar');

    // 5. «Desconectar», con confirmación; el asistente dice que no está conectado
    await page.click('#mnemo-desconectar');
    await page.waitForSelector('dialog[open] [data-si]', espera);
    v.pide_confirmacion = (await page.textContent('dialog[open]')).includes('¿Desconectar Mnemo?');
    await page.click('dialog[open] [data-si]');
    await page.waitForFunction(() => document.querySelector('#mnemo-conexion')?.dataset.estado === 'sin_conectar', null, espera);
    b = await bloque(page);
    caso.datos.desconectado = b;
    v.desconectado = JSON.stringify(b.botones) === '["Conectar con Mnemo"]' && b.campo === mcp && b.resultado === null;
    await page.click('#agente-boton');
    v.asistente_se_entera_al_desconectar = await llega(page, () => document.querySelector('#agente-sub').textContent === 'Sin conectar'
      && document.querySelector('#agente-panel:not([hidden]) .agente-explicacion h3')?.textContent === 'El asistente no está conectado');
    caso.datos.asistente_desconectado = await asistente(page);
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


# ───────────────────────────── De punta a punta con un Mnemo de verdad (opcional) ─────────────────────────────

# El Mnemo de verdad, en local: su API (`createTestApp` de sus pruebas: almacenes en memoria, el catálogo, OAuth y
# `mnemo_model_complete` reales) con PUBLIC_BASE_URL en `http://localhost:<puerto>` (otro sitio que el panel en
# 127.0.0.1, como en producción) y un modelo con guion en vez de un proveedor: contesta a trozos; si la petición trae la
# herramienta del panel que dice MNEMO_GUION, la pide (`tool_use`), y con su resultado responde con lo que encontró (un
# enlace a la ficha de cada persona). GET /__guion dice qué le llegó al modelo. Escucha antes de crear la app: la
# dirección pública tiene que llevar el puerto.
SERVIDOR_MNEMO = r"""
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";

const { createTestApp } = await import("{RAIZ}/apps/api/test/helpers.ts");
const { noteUsage, purposeOf } = await import("{RAIZ}/apps/api/src/llm/attribution.ts");

type Bloque = { type: string; text?: string; content?: unknown; id?: string; name?: string; input?: unknown };
type Peticion = { system: unknown; messages: Array<{ role: string; content: string | Bloque[] }>; tools?: Array<{ name: string }>; purpose?: string };
const guion = JSON.parse(process.env.MNEMO_GUION || "{}");
const dormir = (ms: number) => new Promise((r) => setTimeout(r, ms));
const recibidas: Peticion[] = [];
let usos = 0;

function responder(p: Peticion) {
  const ultimo = p.messages.at(-1);
  const bloques = Array.isArray(ultimo?.content) ? ultimo.content : [];
  const resultado = bloques.find((b) => b.type === "tool_result");
  if (resultado) {
    const visto = typeof resultado.content === "string" ? resultado.content : JSON.stringify(resultado.content);
    let encontrado = visto.slice(0, 400);
    try {
      const filas = JSON.parse(visto).filas ?? [];
      if (filas.length) encontrado = filas.map((f: { id: number; nombre: string; consentimiento: string }) => `[${f.nombre}](/personas/${f.id}), con la autorización ${f.consentimiento}`).join("; ") + ".";
    } catch { /* no es JSON: se cita tal cual */ }
    return { content: [{ type: "text", text: `${guion.final} ${encontrado}` }], stopReason: "end_turn" };
  }
  if (guion.herramienta && p.tools?.some((t) => t.name === guion.herramienta)) {
    usos += 1;
    return { content: [{ type: "text", text: guion.texto }, { type: "tool_use", id: `toolu_guion_${usos}`, name: guion.herramienta, input: guion.entrada ?? {} }], stopReason: "tool_use" };
  }
  return { content: [{ type: "text", text: "Hola, soy el modelo de prueba de Mnemo." }], stopReason: "end_turn" };
}

const llm = {
  model: "modelo-de-prueba",
  async complete(p: Peticion) { return this.stream(p, () => undefined); },
  async stream(p: Peticion, alEvento: (e: { type: "text_delta"; text: string }) => void) {
    recibidas.push(p);
    const r = { provider: "guion", model: "modelo-de-prueba", usage: { inputTokens: 1200, outputTokens: 60 }, ...responder(p) };
    for (const b of r.content) {
      if (b.type !== "text" || !b.text) continue;
      for (const trozo of b.text.match(/.{1,8}/gsu) ?? []) {
        alEvento({ type: "text_delta", text: trozo });
        await dormir(guion.retraso_ms ?? 30);
      }
    }
    noteUsage({ provider: r.provider, model: r.model, purpose: purposeOf(p.purpose), usage: r.usage, at: new Date() });
    return r;
  },
};

const servidor = createServer();
await new Promise<void>((resolve) => servidor.listen(0, "127.0.0.1", resolve));
const base = `http://localhost:${(servidor.address() as AddressInfo).port}`;
const t = await createTestApp({ llm, env: { publicBaseUrl: base } });
servidor.on("request", (peticion, respuesta) => {
  if (peticion.url === "/__guion") {
    respuesta.setHeader("content-type", "application/json");
    respuesta.end(JSON.stringify({ peticiones: recibidas.length, recibidas }));
    return;
  }
  t.app(peticion, respuesta);
});
console.log(`LISTO ${base} ${t.agentApi.oauth ? "oauth" : "sin-oauth"}`);
process.on("SIGTERM", () => process.exit(0));
"""


@pytest.fixture
def mnemo_de_verdad(tmp_path):
    """Mnemo de verdad en local (`SERVIDOR_MNEMO`): necesita `MNEMO_E2E_DIR`, un checkout de Mnemo con
    `mnemo_model_complete`, `npm ci` y `npm run build:shared` hechos (no se toca el repositorio). Corre en su propio
    grupo de procesos (npx → tsx → node) para apagarlo entero. Da (base de Mnemo, nombre de la persona que el modelo
    busca con `buscar_personas`: una de las que `_servir` inserta)."""
    import queue
    import signal
    raiz = os.environ.get("MNEMO_E2E_DIR", "").rstrip("/")
    npx = shutil.which("npx")
    if not raiz or not os.path.isdir(os.path.join(raiz, "node_modules")) or not npx:
        pytest.skip("Sin MNEMO_E2E_DIR (un checkout de Mnemo con node_modules) o sin npx")
    if not os.path.isfile(os.path.join(raiz, "apps", "api", "src", "agent-api", "catalog", "model.ts")):
        pytest.skip("Ese Mnemo no tiene mnemo_model_complete")
    buscada = personas_inventadas(3, semilla=41)[1]["nombre"]
    guion = tmp_path / "mnemo_modelo.mts"
    guion.write_text(SERVIDOR_MNEMO.replace("{RAIZ}", raiz), encoding="utf-8")
    entorno = {**os.environ, "NODE_ENV": "test", "NODE_OPTIONS": "--experimental-async-context-frame",
               "MNEMO_GUION": json.dumps({
                   "herramienta": "buscar_personas", "entrada": {"q": buscada}, "retraso_ms": 50,
                   "texto": "Voy a buscarla en la base del panel.",
                   "final": "Sí, está en la base. La busqué con la herramienta del panel y encontré a"})}
    proc = subprocess.Popen([npx, "tsx", str(guion)], cwd=os.path.join(raiz, "apps", "api"), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, env=entorno, start_new_session=True)
    lineas: queue.Queue = queue.Queue()
    threading.Thread(target=lambda: [lineas.put(x) for x in proc.stdout], daemon=True).start()
    try:
        limite, linea, salida = time.monotonic() + 120, "", []
        while time.monotonic() < limite and not linea.startswith("LISTO "):
            try:
                linea = lineas.get(timeout=1)
                salida.append(linea)
            except queue.Empty:
                if proc.poll() is not None:
                    break
        assert linea.startswith("LISTO "), "Mnemo no arrancó en local:\n" + "".join(salida)[-3000:]
        _, url, oauth = linea.split()
        assert oauth == "oauth", "Mnemo arrancó sin OAuth (PUBLIC_BASE_URL)"
        yield url, buscada
    finally:
        for senal in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(proc.pid, senal)
                proc.wait(10)
                break
            except (ProcessLookupError, subprocess.TimeoutExpired):
                continue


@requiere_navegador
def test_punta_a_punta_con_mnemo_de_verdad(mnemo_de_verdad, panel_vivo, cfg, tmp_path):
    """La punta a punta con Mnemo de verdad (se salta sin `MNEMO_E2E_DIR`), en dos sesiones del navegador. Ya con
    sesión en Mnemo, el administrador:

    1. conecta el panel desde Ajustes → Asistente con la dirección MCP escrita: la página de permisos de Mnemo, con
       «Usar tus modelos» marcado; vuelve conectado y el asistente se enciende con el modelo de Mnemo;
    2. conversa: el modelo de Mnemo pide una herramienta del panel (`buscar_personas`), la recibe y responde con lo que
       encontró, con el texto llegando por partes.

    Entre las dos sesiones, el acceso vence y el panel lo renueva contra Mnemo (el token de renovación rota). Después:

    3. sigue la conversación con el acceso renovado;
    4. vuelve a conectar desmarcando «Usar tus modelos»: Ajustes lo avisa, el asistente se apaga y lo explica (Mnemo
       actualiza la misma conexión, no deja otra suelta); vuelve a conectar marcándolo y sigue la conversación;
    5. desconecta: en Mnemo la conexión queda revocada (con el token de renovación vigente, el que dio la renovación).

    Con `CAPTURAS_AGENTE`, las capturas (`mnemo-*.png`) quedan ahí."""
    import asyncio
    from datetime import datetime, timedelta, timezone

    import httpx

    from app import seguridad
    from app.agente import cifrado, mnemo_conexion

    mnemo, buscada = mnemo_de_verdad
    base, panel, ids = panel_vivo
    db = panel.state.db
    datos = (base, cfg.usuario, cfg.clave)
    (caso,) = _correr(GUION_PUNTA_A_PUNTA, tmp_path, *datos, "conectar", mnemo, buscada, str(ids[1]))["casos"]
    _revisar(caso)

    # El acceso «vence»: el panel lo renueva contra Mnemo con el token de renovación, guarda los nuevos y la conexión
    # sigue (lo que sigue en el navegador ya usa los renovados)
    def tokens(doc):
        return cifrado.descifrar(seguridad.llave_mnemo(cfg), doc["cifrado"],
                                 f"mnemo_conexion|{doc['emisor']}|{doc['client_id']}")

    antes = db.meta.find_one({"_id": "mnemo_conexion"})
    viejos = tokens(antes)
    db.meta.update_one({"_id": "mnemo_conexion"}, {"$set": {"vence": datetime.now(timezone.utc) - timedelta(minutes=1)},
                                                   "$inc": {"version": 1}})
    fuente = mnemo_conexion.FuenteTokens(panel)
    acceso = asyncio.run(fuente.token())
    despues = db.meta.find_one({"_id": "mnemo_conexion"})
    nuevos = tokens(despues)
    assert fuente.renovaciones == 1 and acceso == nuevos["access"] != viejos["access"]
    assert nuevos["refresh"] != viejos["refresh"]  # Mnemo lo rota en cada uso
    assert despues["estado"] == "conectada" and despues["renovada_en"] is not None
    assert despues["vence"].replace(tzinfo=timezone.utc) > datetime.now(timezone.utc) + timedelta(minutes=50)

    (caso,) = _correr(GUION_PUNTA_A_PUNTA, tmp_path, *datos, "seguir", mnemo, buscada, str(ids[1]))["casos"]
    _revisar(caso)
    # Lo que le llegó al modelo de Mnemo: las herramientas del panel y, en la segunda ronda de cada mensaje, el
    # resultado de la búsqueda (la persona, con su nombre)
    guion = httpx.get(f"{mnemo}/__guion", timeout=10).json()
    assert guion["peticiones"] == 6, guion["peticiones"]
    for pedido in guion["recibidas"]:
        assert "buscar_personas" in [t["name"] for t in pedido["tools"]]
    for pedido in guion["recibidas"][1::2]:
        resultados = [b for b in pedido["messages"][-1]["content"] if b["type"] == "tool_result"]
        assert len(resultados) == 1 and buscada in json.dumps(resultados[0]["content"], ensure_ascii=False)
    # En el panel: una conversación, de Mnemo; sus rondas las respondió el modelo de la cuenta; la conexión se borró
    (conv,) = list(db.agente_conversaciones.find())
    assert conv["proveedor"] == "mnemo"
    modelos = [m.get("modelo") for m in db.agente_mensajes.find({"conversacion": conv["_id"], "rol": "assistant"})]
    assert modelos == ["guion/modelo-de-prueba"] * 6
    assert not (db.meta.find_one({"_id": "mnemo_conexion"}) or {}).get("estado")
    acciones = [a["accion"] for a in db.auditoria.find({"accion": {"$regex": "^mnemo_"}}, sort=[("_id", 1)])]
    assert acciones == ["mnemo_conectar"] * 3 + ["mnemo_desconectar"], acciones


GUION_PUNTA_A_PUNTA = r"""// La punta a punta del asistente con un Mnemo de verdad (en local, con un modelo con guion), en Chromium.
// Uso: node <guion> <base del panel> <usuario> <clave> <fase> <base de Mnemo> <persona buscada> <su id> <capturas>
// Fases: «conectar» (conectar y conversar) y «seguir» (seguir la conversación, volver a conectar sin y con el permiso
// de los modelos y desconectar), cada una en una sesión nueva del navegador.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const [base, usuario, clave, fase, mnemo, buscada, personaId, capturas] = process.argv.slice(2);
const origen = new URL(base).origin;
const origenMnemo = new URL(mnemo).origin;
const pref = new URL(base).pathname.replace(/\/+$/, '');
const espera = { timeout: 30000 };
const ADMIN_MNEMO = { username: 'admin', password: 'correct horse battery staple' }; // `testEnv` de las pruebas de Mnemo
const USAR_MODELOS = 'Usar sus modelos de IA y sus créditos';

const bloque = (page) => page.evaluate(() => {
  const b = document.querySelector('#mnemo-conexion');
  return b && { estado: b.dataset.estado, texto: b.textContent.replace(/\s+/g, ' ').trim(),
    botones: [...b.querySelectorAll('button')].map((x) => x.textContent.trim()),
    permisos: [...b.querySelectorAll('.chips .chip')].map((x) => x.textContent.trim()),
    sinModelos: b.querySelector('.mnemo-nota.alerta:not(.resultado)')?.textContent ?? null,
    resultado: b.querySelector('.mnemo-nota.resultado')?.textContent ?? null };
});
const cabeza = (page) => page.textContent('.asistente-cabeza');

// La última respuesta del asistente: sus partes en orden (texto, herramientas con su estado y su etiqueta)
const respuesta = (page) => page.evaluate(() => {
  const r = [...document.querySelectorAll('.agente-msj.agente-respuesta')].pop();
  return r ? [...r.children].filter((x) => !x.classList.contains('sr')).map((x) => (x.classList.contains('agente-md')
    ? `md:${x.textContent}` : x.classList.contains('agente-herr') ? `herr:${x.dataset.estado}:${x.querySelector('.et')?.textContent}`
      : x.className)) : [];
});

// En Mnemo, con la sesión de la cuenta: las conexiones (concesiones) y el registro de llamadas
const deMnemo = async (page, ruta, clave) => (await (await page.request.get(`${mnemo}${ruta}`)).json())[clave] || [];
const concesiones = async (page) => (await deMnemo(page, '/api/me/agent-grants', 'grants'))
  .map((g) => ({ cliente: g.client, alcances: g.scopes, revocada: !!g.revokedAt }));
const respuestasDeMnemo = async (page) => (await deMnemo(page, '/api/me/agent-calls', 'calls'))
  .filter((x) => x.tool === 'mnemo_model_complete' && x.outcome === 'ok').length;

async function sinAvisos(page) {
  await page.waitForFunction(() => !document.querySelector('#avisos .aviso'), null, espera);
}

// «Conectar con Mnemo» o «Volver a conectar»: la página de permisos de Mnemo, la decisión y la vuelta a Ajustes
async function conectar(page, { modelos = true, captura = null } = {}) {
  await page.fill('#f-mnemo [name=url]', `${mnemo}/mcp`);
  await page.click('#mnemo-conectar');
  await page.waitForURL((u) => u.origin === origenMnemo, espera);
  await page.waitForSelector('button[name=decision][value=allow]', espera);
  const permisos = await page.evaluate(() => [...document.querySelectorAll('input[name=scope]')].map((x) => [x.value, x.checked]));
  if (captura) await page.screenshot({ path: `${capturas}/${captura}`, fullPage: true });
  if (!modelos) await page.uncheck('input[name=scope][value="mnemo:model"]');
  await page.click('button[name=decision][value=allow]');
  await page.waitForURL((u) => u.origin === origen && u.pathname === pref + '/ajustes', espera);
  await page.waitForFunction(() => document.querySelector('#mnemo-conexion')?.dataset.estado === 'conectada', null, espera);
  return { permisos, direccion: page.url(), bloque: await bloque(page), cabeza: await cabeza(page) };
}

// Abre el asistente y, de «Conversaciones», la única que hay (una sesión nueva del navegador, o un rato sin modelo,
// empiezan sin conversación abierta; si la pestaña la tenía guardada, el asistente ya la trae)
async function abrirLaConversacion(page, caso) {
  await sinAvisos(page);
  await page.click('#agente-boton');
  await page.waitForSelector('#agente-panel:not([hidden]) :is(.agente-sugerencia, .agente-msj)', espera);
  await page.click('#agente-ver-historial');
  await page.waitForSelector('.agente-item .agente-abrir', espera);
  caso.datos.historial = await page.evaluate(() => [...document.querySelectorAll('.agente-item b')].map((x) => x.textContent));
  await page.click('.agente-item:first-child .agente-abrir');
  await page.waitForFunction(() => document.querySelectorAll('.agente-msj.agente-respuesta').length > 0
    && document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);
  return caso.datos.historial.length === 1;
}

// Un mensaje al asistente; espera a que termine. `captura`: una de la respuesta a mitad (la herramienta ya respondió y
// el texto final va llegando). Devuelve las partes de la respuesta y cuánto cambió el texto mientras llegaba.
async function conversar(page, texto, captura = null) {
  await page.evaluate(() => {
    window.__largos = [];
    const log = document.querySelector('#agente-mensajes');
    window.__mirando?.disconnect();
    window.__mirando = new MutationObserver(() => {
      const r = [...log.querySelectorAll('.agente-msj.agente-respuesta')].pop();
      const largo = r ? [...r.querySelectorAll('.agente-md')].reduce((n, x) => n + x.textContent.length, 0) : 0;
      if (window.__largos.at(-1)?.[1] !== largo) window.__largos.push([Math.round(performance.now()), largo]);
    });
    window.__mirando.observe(log, { subtree: true, childList: true, characterData: true });
  });
  const antes = await page.evaluate(() => document.querySelectorAll('.agente-msj.agente-respuesta').length);
  await page.fill('#agente-texto', texto);
  await page.press('#agente-texto', 'Enter');
  if (captura) {
    await page.waitForFunction((n) => {
      const rs = document.querySelectorAll('.agente-msj.agente-respuesta');
      const md = rs.length > n ? [...rs[rs.length - 1].querySelectorAll('.agente-md')] : [];
      return md.length >= 2 && md.at(-1).textContent.length > 30 && document.querySelector('#agente-panel').dataset.estado !== 'listo';
    }, antes, espera);
    await page.screenshot({ path: `${capturas}/${captura}` });
  }
  await page.waitForFunction((n) => document.querySelectorAll('.agente-msj.agente-respuesta').length > n
    && document.querySelector('#agente-panel').dataset.estado === 'listo', antes, { timeout: 60000 });
  const largos = (await page.evaluate(() => window.__largos)).filter(([, n]) => n > 0);
  const enlaces = await page.evaluate(() => [...[...document.querySelectorAll('.agente-msj.agente-respuesta')].pop()
    .querySelectorAll('.agente-md a')].map((a) => a.getAttribute('href')));
  return { partes: await respuesta(page), cambios: largos.length, ms: largos.length ? largos.at(-1)[0] - largos[0][0] : 0, enlaces,
    respuestas: await page.evaluate(() => document.querySelectorAll('.agente-msj.agente-respuesta').length),
    error: await page.evaluate(() => [...document.querySelectorAll('.agente-error')].map((e) => e.textContent)) };
}

// La respuesta esperada: el texto de la primera ronda, la herramienta del panel y la respuesta con lo que encontró (con
// el enlace a la ficha), llegada por partes
const respondio = (r) => r.partes.length === 3 && r.partes[0] === 'md:Voy a buscarla en la base del panel.'
  && r.partes[1].startsWith('herr:ok:Buscando habitantes')
  && r.partes[2] === `md:Sí, está en la base. La busqué con la herramienta del panel y encontré a ${buscada}, con la autorización pendiente.`
  && r.enlaces.length === 1 && r.enlaces[0].endsWith(`/personas/${personaId}`) && r.cambios >= 10 && r.ms > 500 && !r.error.length;

// Fase 1: conectar desde Ajustes y conversar con el modelo de Mnemo
async function conectarYConversar(page, caso) {
  const v = caso.revisiones;
  let b = await bloque(page);
  caso.datos.inicio = b;
  v.empieza_sin_conectar = b.estado === 'sin_conectar' && JSON.stringify(b.botones) === '["Conectar con Mnemo"]'
    && (await cabeza(page)).includes('El asistente está apagado: no tiene un modelo que usar');
  await page.locator('.asistente-cabeza').scrollIntoViewIfNeeded();
  await page.locator('.asistente-cabeza').screenshot({ path: `${capturas}/mnemo-ajustes-sin-conectar.png` });

  // «Conectar con Mnemo»: en la página de permisos de Mnemo viene marcado «Usar tus modelos»; de vuelta, conectado
  const c = await conectar(page, { captura: 'mnemo-consentimiento.png' });
  caso.datos.conectar = c;
  v.usar_modelos_marcado = c.permisos.some(([a, marcado]) => a === 'mnemo:model' && marcado);
  v.conectado = c.direccion === `${base}/ajustes` && c.bloque.texto.includes('Conectado como admin (admin@example.com)')
    && c.bloque.texto.includes(`Dirección: ${mnemo}/mcp`) && c.bloque.permisos.includes(USAR_MODELOS) && c.bloque.sinModelos === null
    && JSON.stringify(c.bloque.botones) === '["Volver a conectar","Desconectar"]'
    && c.cabeza.includes('El asistente está encendido y usa los modelos de la cuenta de Mnemo conectada');
  await sinAvisos(page);
  await page.locator('.asistente-cabeza').screenshot({ path: `${capturas}/mnemo-ajustes-conectado.png` });

  // El asistente con el modelo de Mnemo: pide una herramienta del panel, la recibe y responde, por partes
  await page.click('#agente-boton');
  await page.waitForSelector('#agente-panel:not([hidden]) .agente-sugerencia', espera);
  const r = await conversar(page, `¿Está ${buscada} en la base?`, 'mnemo-widget-respondiendo.png');
  caso.datos.respuesta = r;
  v.respondio_con_la_herramienta_del_panel = respondio(r);
  await page.screenshot({ path: `${capturas}/mnemo-widget-respuesta.png` });
  v.respondio_el_modelo_de_mnemo = (await respuestasDeMnemo(page)) === 2;
}

// Fase 2: seguir la conversación (con el acceso renovado), volver a conectar sin y con el permiso de los modelos,
// seguirla otra vez y desconectar
async function seguirYDesconectar(page, caso) {
  const v = caso.revisiones;
  v.sigue_conectado = (await bloque(page)).estado === 'conectada';
  v.abre_la_conversacion = await abrirLaConversacion(page, caso);
  let r = await conversar(page, `¿Y ${buscada} sigue ahí?`);
  caso.datos.respuesta_renovada = r;
  v.sigue_con_el_acceso_renovado = respondio(r) && r.respuestas === 2 && (await respuestasDeMnemo(page)) === 4;
  await page.click('#agente-cerrar');

  // «Volver a conectar» sin «Usar tus modelos»: Ajustes lo avisa y el asistente se apaga (y lo explica); Mnemo
  // actualiza la misma conexión
  let c = await conectar(page, { modelos: false });
  caso.datos.sin_modelos = c;
  v.avisa_sin_modelos = c.bloque.estado === 'conectada' && !c.bloque.permisos.includes(USAR_MODELOS)
    && (c.bloque.sinModelos || '').startsWith('Mnemo se conectó sin permiso para usar sus modelos: vuelva a conectar dejando marcado')
    && c.cabeza.includes('El asistente está apagado: no tiene un modelo que usar');
  let g = await concesiones(page);
  caso.datos.concesiones_sin_modelos = g;
  v.mnemo_actualizo_la_misma = g.length === 1 && !g[0].revocada && !g[0].alcances.includes('mnemo:model');
  await sinAvisos(page);
  await page.locator('.asistente-cabeza').screenshot({ path: `${capturas}/mnemo-ajustes-sin-permiso-de-modelos.png` });
  await page.click('#agente-boton');
  await page.waitForSelector('.agente-explicacion', espera);
  const ex = await page.evaluate(() => ({ titulo: document.querySelector('.agente-explicacion h3')?.textContent,
    enlace: document.querySelector('.agente-explicacion a')?.getAttribute('href') }));
  caso.datos.explicacion = ex;
  v.explica_sin_modelos = ex.titulo === 'Mnemo está conectado sin permiso para usar sus modelos' && (ex.enlace || '').endsWith('/ajustes');
  await page.click('#agente-cerrar');

  // Otra vez con la casilla: la misma conexión, con los modelos, y la conversación sigue
  c = await conectar(page);
  caso.datos.reconectar = c;
  g = await concesiones(page);
  v.vuelve_con_modelos = c.bloque.permisos.includes(USAR_MODELOS) && c.bloque.sinModelos === null
    && g.length === 1 && !g[0].revocada && g[0].alcances.includes('mnemo:model');
  v.abre_la_conversacion_otra_vez = await abrirLaConversacion(page, caso);
  r = await conversar(page, `¿Me confirmas si ${buscada} está?`);
  caso.datos.respuesta_reconectada = r;
  v.sigue_tras_volver_a_conectar = respondio(r) && r.respuestas === 3 && (await respuestasDeMnemo(page)) === 6;
  await page.click('#agente-cerrar');

  // «Desconectar», con confirmación: el panel revoca la conexión en Mnemo
  await page.click('#mnemo-desconectar');
  await page.waitForSelector('dialog[open] [data-si]', espera);
  await page.click('dialog[open] [data-si]');
  await page.waitForFunction(() => document.querySelector('#mnemo-conexion')?.dataset.estado === 'sin_conectar', null, espera);
  const b = await bloque(page);
  caso.datos.desconectado = b;
  v.desconectado = JSON.stringify(b.botones) === '["Conectar con Mnemo"]' && b.resultado === null
    && (await cabeza(page)).includes('El asistente está apagado');
  g = await concesiones(page);
  caso.datos.concesiones = g;
  v.revocada_en_mnemo = g.length === 1 && g[0].revocada && g[0].alcances.includes('mnemo:model');
  await sinAvisos(page);
  await page.locator('.asistente-cabeza').screenshot({ path: `${capturas}/mnemo-ajustes-desconectado.png` });
}

(async () => {
  const nav = await chromium.launch();
  const caso = { nombre: `mnemo_${fase}`, revisiones: {}, errores: [], csp: [], datos: {} };
  const v = caso.revisiones;
  try {
    const ctx = await nav.newContext({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 2 });
    await ctx.route((u) => u.origin !== origen && u.origin !== origenMnemo, (r) => r.abort()); // sin red: fuentes, teselas
    await ctx.exposeBinding('__csp', (_, x) => caso.csp.push(x));
    await ctx.addInitScript(() => {
      addEventListener('securitypolicyviolation', (e) => window.__csp(`${location.origin} ${e.effectiveDirective} ${e.blockedURI}`), true);
    });
    const page = await ctx.newPage();
    page.on('pageerror', (e) => caso.errores.push(String(e)));
    page.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) caso.errores.push(m.text()); });
    page.on('response', (x) => {
      const u = new URL(x.url());
      if (u.origin !== origen || x.status() < 400) return;
      if (x.status() === 401 && u.pathname === pref + '/api/yo') return; // la pregunta del arranque («¿hay sesión?»)
      caso.errores.push(`${x.status()} ${u.pathname}`);
    });
    // La sesión en Mnemo, como quien ya entró en Mnemo en este navegador; y el panel, como administrador, en Ajustes
    v.sesion_en_mnemo = (await page.request.post(`${mnemo}/api/auth/login`, { data: ADMIN_MNEMO, headers: { Origin: origenMnemo } })).ok();
    await page.goto(base + '/', { waitUntil: 'domcontentloaded' });
    await page.fill('#f-login [name=usuario]', usuario);
    await page.fill('#f-login [name=clave]', clave);
    await page.click('#f-login button[type=submit]');
    await page.waitForSelector('#app #vista > .vista', espera);
    await page.click('#nav a[data-nav="ajustes"]');
    await page.waitForSelector('#mnemo-conexion', espera);
    if (fase === 'conectar') await conectarYConversar(page, caso);
    else await seguirYDesconectar(page, caso);
    await ctx.close();
  } catch (e) {
    v.sin_excepcion = String(e.stack || e).slice(0, 1500);
  } finally {
    await nav.close();
  }
  console.log(JSON.stringify({ casos: [caso] }));
})().catch((e) => { console.error(e); process.exit(1); });
"""
