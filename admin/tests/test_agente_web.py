"""El asistente en web/js (agente.js, agente.css y lo que agrega a api.js, app.js y ui.js), sin navegador.

* El texto del modelo nunca se pinta como HTML: agente.js no usa `crudo`, ni `insertAdjacentHTML`, ni `innerHTML +=`
  (test_web_sin_crudo.py no ve este último), y sus plantillas `html` solo llevan íconos de la tabla fija de ui.js.
* Las rutas /api/agente/* que usa existen en la API con su método, y las usa todas.
* agente.css existe y la carga agente.js (no index.html); app.js lo carga con la forma literal que pide
  test_web_imports.py y borra lo guardado en la pestaña al cerrar sesión; nada del asistente va a localStorage.
* Con Node: los enlaces que acepta (`destinoEnlace`) y cómo parte el Markdown en bloques (`partirBloques`).
* La conexión con Mnemo en Ajustes (vistas/ajustes.js): la vuelta de Mnemo sale de la dirección de forma síncrona,
  antes de cualquier espera, y recién después va a POST /api/agente/mnemo/volver; «Conectar» va a Mnemo con
  `location.assign` a una dirección https (o http de la propia máquina), nunca con un formulario ni una ventana.
* El contexto que el widget manda al modelo solo lleva las claves de filtro conocidas: nunca `code`, `state`, `iss`,
  `error` ni `error_description`. Y los códigos nuevos del proveedor del modelo (Mnemo) tienen su trato.
La prueba con un navegador de verdad está en test_agente_navegador.py.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.routing import APIRoute

RAIZ = Path(__file__).resolve().parents[1]
JS = RAIZ / "web" / "js"
AGENTE = (JS / "agente.js").read_text(encoding="utf-8")
AJUSTES = (JS / "vistas" / "ajustes.js").read_text(encoding="utf-8")
CSS = RAIZ / "web" / "css" / "agente.css"
# Lo que trae la vuelta de Mnemo (OAuth): nunca va al modelo
VUELTA = ("code", "state", "iss", "error", "error_description")


def _sin_comentarios(texto: str) -> str:
    return "\n".join("" if l.lstrip().startswith(("//", "*", "/*")) else l for l in texto.splitlines())


def _plantillas(texto: str) -> list[str]:
    """El contenido de cada plantilla html`…` (sin plantillas anidadas: agente.js no las usa)."""
    return re.findall(r"\bhtml`((?:[^`\\]|\\.)*)`", texto)


# ───────────────────────────── El texto del modelo nunca como HTML ─────────────────────────────

def test_agente_js_no_arma_html_con_datos():
    codigo = _sin_comentarios(AGENTE)
    for prohibido in ("insertAdjacentHTML", "outerHTML", "document.write", "eval(", "new Function", "srcdoc",
                      "DOMParser", "createContextualFragment", "setHTML", ".innerText"):
        assert prohibido not in AGENTE, prohibido
    assert not re.search(r"\bcrudo\b", AGENTE), "agente.js no usa crudo()"
    assert not re.search(r"(?:inner|outer)HTML\s*\+=", AGENTE)
    # El único innerHTML es el de los íconos (la tabla fija P de ui.js)
    asignaciones = re.findall(r"\.innerHTML\s*=\s*(.*)", codigo)
    assert asignaciones == ["String(html`${icono(nombre)}`);"], asignaciones
    # Las plantillas solo interpolan íconos: ningún texto del servidor ni del modelo pasa por `html`
    interpolados = [i for p in _plantillas(codigo) for i in re.findall(r"\$\{([^}]*)\}", p)]
    solo_iconos = all(re.fullmatch(r"icono\('[a-z]+'\)|icono\(nombre\)", i) for i in interpolados)
    assert interpolados and solo_iconos, interpolados


def test_ningun_modulo_usa_inner_html_mas_igual():
    # test_web_sin_crudo.py revisa `innerHTML =` pero no `innerHTML +=`: con texto del modelo sería un XSS
    malos = [(str(f.relative_to(JS)), n) for f in sorted(JS.rglob("*.js"))
             for n, l in enumerate(f.read_text(encoding="utf-8").splitlines(), 1)
             if re.search(r"\.(?:inner|outer)HTML\s*\+=", l)]
    assert not malos, malos


def test_enlaces_solo_internos_o_de_mnemo():
    # Los enlaces externos salen solo de `crearEnlace`, con target y rel; nadie más pone href, src ni target
    codigo = _sin_comentarios(AGENTE)
    assert codigo.count(".target = '_blank'") == 1 and "a.rel = 'noopener noreferrer'" in codigo
    hrefs = re.findall(r"\.href\s*=\s*([^;\n]+)", codigo)
    esperados = ["url(d.ruta)", "d.href", "new URL('../css/agente.css', import.meta.url).href"]
    assert sorted(hrefs) == sorted(esperados), hrefs
    assert not re.search(r"\.src\s*=|setAttribute\(\s*['\"](?:href|src|on\w+|style)['\"]", codigo)
    assert "u.protocol === 'https:' && u.origin === origenMnemo" in codigo


# ───────────────────────────── Rutas de la API ─────────────────────────────

def _rutas_api():
    from app.main import crear_app
    out = []
    for r in crear_app().routes:
        if isinstance(r, APIRoute) and r.path.startswith("/api/agente"):
            out.append((re.compile("^" + re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(r.path)) + "$"), r.methods))
    return out


def test_las_rutas_del_asistente_existen_y_se_usan_todas():
    rutas = _rutas_api()
    usadas = set()
    # `correr(ruta, …)` es el turno en flujo (POST con `flujo` de api.js)
    for m in re.finditer(r"""(?:api\.(get|post|del)\(|correr\()\s*(['"`])(/api/[^'"`]+)\2""", _sin_comentarios(AGENTE)):
        metodo = {"get": "GET", "post": "POST", "del": "DELETE", None: "POST"}[m.group(1)]
        forma = re.sub(r"\$\{[^}]*\}", "X", m.group(3))
        assert any(p.match(forma) and metodo in met for p, met in rutas), (metodo, forma)
        usadas.add((metodo, forma))
    assert usadas == {("GET", "/api/agente/estado"), ("GET", "/api/agente/conversaciones"),
                      ("GET", "/api/agente/conversaciones/X"), ("DELETE", "/api/agente/conversaciones/X"),
                      ("POST", "/api/agente/mensajes"), ("POST", "/api/agente/confirmaciones")}, usadas


# ───────────────────────────── Carga, estilos y almacenamiento ─────────────────────────────

def test_carga_desde_app_js_y_sus_estilos():
    app = (JS / "app.js").read_text(encoding="utf-8")
    assert "import('./agente.js').then((m) => m.montarAgente)" in app
    assert re.search(r"^export function montarAgente\(", AGENTE, re.M)
    # Se monta en render(), justo después de cerrar el menú (también en «No existe» y «Sin acceso»)
    render = app[app.index("async function render()"):]
    assert render.index("abrirMenu(false);") < render.index("asegurarAgente();") < render.index("if (!r)")
    assert "conPendientes() || !puede('agente.usar')" in app
    # agente.css existe, la carga agente.js con su ruta relativa (como zona.js) y index.html no la enlaza
    assert CSS.is_file()
    assert "new URL('../css/agente.css', import.meta.url)" in AGENTE
    assert "agente.css" not in (RAIZ / "web" / "index.html").read_text(encoding="utf-8")


def test_nada_del_asistente_en_local_storage():
    assert "localStorage" not in AGENTE
    assert "sessionStorage" in AGENTE and "'yj_agente'" in AGENTE
    olvidar = re.search(r"function olvidar\(\) \{(.*?)\n\}", (JS / "app.js").read_text(encoding="utf-8"), re.S).group(1)
    assert "sessionStorage.removeItem('yj_agente')" in olvidar


def test_api_js_flujo_y_contrato():
    api = (JS / "api.js").read_text(encoding="utf-8")
    assert re.search(r"^export async function flujo\(", api, re.M)
    assert re.search(r"^export const hayCambiosSinGuardar\b", api, re.M)
    cuerpo = api[api.index("export async function flujo("):api.index("/** Descarga un archivo")]
    for pieza in ("'X-CSRF-Token': csrf", "reingresar()", "alExpirar()", "alPendiente(e.codigo)", "AbortController",
                  "application/x-ndjson", "credentials: 'same-origin'", "url(ruta)"):
        assert pieza in cuerpo, pieza


def test_iconos_nuevos_en_ui_js():
    ui = (JS / "ui.js").read_text(encoding="utf-8")
    for nombre in ("agente", "enviar", "detener", "historial", "nueva", "cerrar", "basura", "hecho", "alerta", "reloj",
                   "abajo", "info"):
        assert re.search(rf"^\s*{nombre}:\s*'<", ui, re.M), nombre
    por_estado = re.search(r"ICONOS_ESTADO = \{([^}]*)\}", AGENTE).group(1)
    usados = set(re.findall(r"\bic(?:ono|o)\('([a-z]+)'\)", AGENTE)) | set(re.findall(r": '([a-z]+)'", por_estado))
    definidos = set(re.findall(r"^\s*([a-z]+):\s*'<", ui, re.M))
    assert usados and usados <= definidos, usados - definidos


def test_css_del_asistente():
    css = CSS.read_text(encoding="utf-8")
    # Capa 28: debajo del velo (29) y del menú lateral (30) del celular; «Cerrar sesión» nunca queda tapado
    assert set(re.findall(r"z-index:\s*(\d+)", css)) == {"28", "1"}
    assert re.search(r"\.agente-boton \{[^}]*z-index: 28", css) and re.search(r"\.agente-panel \{[^}]*z-index: 28", css)
    assert "@media (prefers-reduced-motion: reduce)" in css and "@media (max-width: 900px)" in css
    # Los colores salen de los tokens de app.css: sigue el tema claro u oscuro sin reglas propias
    assert ":root" not in css and "prefers-color-scheme" not in css and "!important" not in css
    assert not re.search(r"(?m)^\s*\.lateral\b", css), "agente.css no toca el menú lateral (test_interfaz_movil.py)"
    sin_comentarios = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    colores = set(re.findall(r"#[0-9a-fA-F]{3,8}\b", sin_comentarios))
    assert colores <= {"#fff"}, colores


# ───────────────────────────── Funciones puras con Node ─────────────────────────────

NODE = r"""
globalThis.document = { querySelector: (s) => (s === 'meta[name="panel-base"]' ? { content: process.argv[1] } : null),
  documentElement: {} };
globalThis.MutationObserver = class { observe() {} };
globalThis.window = globalThis;  // los módulos que importa (agente-mapa.js) escuchan eventos de la ventana
globalThis.addEventListener ||= () => {};
const m = await import('./web/js/agente.js');
const rutas = { '/': 'panel', '/personas': 'personas', '/usuarios': 'usuarios' };
const rutaPanel = (r) => (rutas[r] || /^\/personas\/\d+$/.test(r)
  ? { nav: rutas[r] || 'personas', permitida: r !== '/usuarios' } : null);
const op = { rutaPanel, origenMnemo: 'https://mnemo.example.org', origen: 'https://panel.example' };
const enlaces = Object.fromEntries(JSON.parse(process.argv[2]).map((d) => [d, m.destinoEnlace(d, op)]));
const bloques = Object.fromEntries(JSON.parse(process.argv[3]).map((t) => [t, m.partirBloques(t)]));
console.log(JSON.stringify({ enlaces, bloques }));
"""

ENLACES = {
    "/personas/12": {"tipo": "interno", "ruta": "/personas/12"},
    " /personas/12?zona=rural#x ": {"tipo": "interno", "ruta": "/personas/12?zona=rural"},
    "/personas/": {"tipo": "interno", "ruta": "/personas"},
    "https://panel.example/personas/3": {"tipo": "interno", "ruta": "/personas/3"},
    "/": {"tipo": "interno", "ruta": "/"},
    "https://mnemo.example.org/aprobar/abc?x=1": {"tipo": "mnemo", "href": "https://mnemo.example.org/aprobar/abc?x=1"},
    # Lo demás queda como texto
    "/usuarios": None,                      # el rol no la abre
    "/no-existe": None, "personas/12": None, "//malo.example/x": None, "/\\malo.example": None,
    "https://malo.example/robar": None, "http://mnemo.example.org/x": None,
    "https://mnemo.example.org.malo.example/x": None,
    "https://usuario:clave@mnemo.example.org/x": None, "javascript:alert(1)": None, "JaVaScRiPt:alert(1)": None,
    "data:text/html,<script>alert(1)</script>": None, "/personas/1 onmouseover=x": None, "/personas/\u0000": None,
    "": None,
}


@pytest.mark.skipif(shutil.which("node") is None, reason="sin Node para cargar web/js/agente.js")
@pytest.mark.parametrize("base", ["", "/panel"])
def test_enlaces_y_bloques_con_node(base):
    textos = [
        "Hola **mundo**.\nSegunda línea.\n\nOtro párrafo.",
        "## Título ##\n- uno\n- dos\n  - sub\n3. no es de la lista",
        "Texto:\n- a\n- b\nsigue b",
        "3) tres\n4) cuatro",
        "```py\nprint('<b>')\n```\nfin",
        "```\nabierto",
        "| A | B | C |\n|:--|:-:|--:|\n| 1 | 2 | 3 |\n| x \\| y |",
        "| solo cabecera |",
        "> cita\n> sigue\n\n---",
        "2026. Un año",
    ]
    r = subprocess.run(["node", "--input-type=module", "-e", NODE, base, json.dumps(list(ENLACES)), json.dumps(textos)],
                       cwd=RAIZ, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    salida = json.loads(r.stdout)
    assert salida["enlaces"] == ENLACES
    b = salida["bloques"]
    assert b[textos[0]] == [{"tipo": "parrafo", "texto": "Hola **mundo**.\nSegunda línea."},
                            {"tipo": "parrafo", "texto": "Otro párrafo."}]
    assert b[textos[1]] == [{"tipo": "titulo", "nivel": 2, "texto": "Título"},
                            {"tipo": "lista", "ordenada": False, "inicio": 1,
                             "items": [{"texto": "uno", "sub": None},
                                       {"texto": "dos", "sub": {"ordenada": False, "items": ["sub"]}}]},
                            {"tipo": "lista", "ordenada": True, "inicio": 3,
                             "items": [{"texto": "no es de la lista", "sub": None}]}]
    assert b[textos[2]] == [{"tipo": "parrafo", "texto": "Texto:"},
                            {"tipo": "lista", "ordenada": False, "inicio": 1,
                             "items": [{"texto": "a", "sub": None}, {"texto": "b\nsigue b", "sub": None}]}]
    assert b[textos[3]][0]["inicio"] == 3 and len(b[textos[3]][0]["items"]) == 2
    assert b[textos[4]] == [{"tipo": "codigo", "texto": "print('<b>')", "cerrado": True},
                            {"tipo": "parrafo", "texto": "fin"}]
    assert b[textos[5]] == [{"tipo": "codigo", "texto": "abierto", "cerrado": False}]  # todavía llega: se ve igual
    assert b[textos[6]] == [{"tipo": "tabla", "cab": ["A", "B", "C"], "alin": ["", "centro", "der"],
                             "filas": [["1", "2", "3"], ["x | y"]]}]
    assert b[textos[7]] == [{"tipo": "parrafo", "texto": "| solo cabecera |"}]  # sin separador todavía no es tabla
    assert b[textos[8]] == [{"tipo": "cita", "texto": "cita\nsigue"}, {"tipo": "regla"}]
    assert b[textos[9]] == [{"tipo": "parrafo", "texto": "2026. Un año"}]


# ───────────────────────────── La conexión con Mnemo en Ajustes ─────────────────────────────

def _funcion(texto: str, nombre: str) -> str:
    """El cuerpo de `function nombre(…) {…}` (o `async function`), hasta la llave que lo cierra."""
    m = re.search(rf"(?:async\s+)?function\s+{nombre}\s*\([^)]*\)\s*\{{", texto)
    assert m, nombre
    nivel, i = 1, m.end()
    while nivel:
        nivel += {"{": 1, "}": -1}.get(texto[i], 0)
        i += 1
    return texto[m.end():i - 1]


def test_ajustes_usa_las_rutas_de_la_conexion_con_mnemo():
    rutas = _rutas_api()
    usadas = set()
    for m in re.finditer(r"""api\.(get|post|del)\(\s*(['"`])(/api/agente[^'"`]*)\2""", _sin_comentarios(AJUSTES)):
        metodo = {"get": "GET", "post": "POST", "del": "DELETE"}[m.group(1)]
        assert any(p.match(m.group(3)) and metodo in met for p, met in rutas), (metodo, m.group(3))
        usadas.add((metodo, m.group(3)))
    assert usadas == {("GET", "/api/agente/estado"), ("POST", "/api/agente/mnemo/conectar"),
                      ("POST", "/api/agente/mnemo/volver"), ("DELETE", "/api/agente/mnemo")}, usadas


def test_la_vuelta_de_mnemo_sale_de_la_direccion_antes_de_cualquier_espera():
    codigo = _sin_comentarios(AJUSTES)
    vista = _funcion(codigo, "vistaAjustes")
    # Lo primero de la vista, antes del primer await: tomar la vuelta (y con ella, quitarla de la dirección)
    antes = vista[:vista.index("await ")]
    assert "const vuelta = tomarVuelta(q);" in antes, antes
    # tomarVuelta es síncrona: lee la consulta y llama a history.replaceState hacia /ajustes, sin esperar nada
    tomar = _funcion(codigo, "tomarVuelta")
    assert not re.search(r"\basync\s+function\s+tomarVuelta\b", codigo)
    assert "await" not in tomar and "then(" not in tomar
    assert "history.replaceState(history.state, '', url('/ajustes'));" in tomar
    assert all(f"'{k}'" in codigo[codigo.index("const VUELTA"):codigo.index("const LOOPBACK")] for k in VUELTA)
    # El POST a /volver sale solo de volverDeMnemo, que la vista llama con lo ya tomado
    assert codigo.count("'/api/agente/mnemo/volver'") == 1
    assert "api.post('/api/agente/mnemo/volver', v)" in _funcion(codigo, "volverDeMnemo")
    assert vista.index("tomarVuelta(q)") < vista.index("if (vuelta) await volverDeMnemo(vuelta);")
    # Y solo el administrador la manda (el coordinador no puede conectar: el servidor le respondería 403)
    assert "if (!puede('agente.conectar')) return;" in _funcion(codigo, "volverDeMnemo")
    # app.js le pasa la consulta a cada vista
    assert "const limpiar = await fn(cont, { params, q, ir });" in (JS / "app.js").read_text(encoding="utf-8")


def test_conectar_va_a_mnemo_con_location_assign_y_nunca_con_un_formulario():
    codigo = _sin_comentarios(AJUSTES)
    conectar = _funcion(codigo, "conectarMnemo")
    assert "api.post('/api/agente/mnemo/conectar'" in conectar
    # Solo a una dirección revisada (https, o http de la propia máquina) y con location.assign
    revisar, ir = "const destino = direccionDeMnemo(r?.autorizar);", "location.assign(destino);"
    assert conectar.index(revisar) < conectar.index(ir)
    assert "if (!destino) throw" in conectar
    assert codigo.count("location.assign(") == 1
    # La CSP del panel tiene form-action 'self': ningún formulario de web/js tiene `action`, nada lo envía por código ni
    # se abren ventanas (con COOP same-origin no volverían)
    for f in sorted(JS.rglob("*.js")):
        texto = _sin_comentarios(f.read_text(encoding="utf-8"))
        for malo in (r"<form\b[^>]*\baction\s*=", r"\bformaction\b", r"\.submit\(\)", r"\brequestSubmit\(",
                     r"\bwindow\.open\(", r"\bopen\(\s*['\"`]http"):
            assert not re.search(malo, texto, re.I), (f.name, malo)
    assert re.search(r'<form id="f-mnemo" class="form" novalidate>', AJUSTES)
    from app.seguridad import CSP
    assert "form-action 'self'" in CSP and "connect-src 'self'" in CSP


NODE_AJUSTES = r"""
globalThis.document = { querySelector: (s) => (s === 'meta[name="panel-base"]' ? { content: process.argv[1] } : null),
  documentElement: {} };
globalThis.MutationObserver = class { observe() {} };
globalThis.window = globalThis;
globalThis.addEventListener ||= () => {};
const llamadas = [];
globalThis.history = { state: { previo: 1 }, replaceState: (s, t, u) => llamadas.push([s, u]) };
const m = await import('./web/js/vistas/ajustes.js');
const casos = JSON.parse(process.argv[2]).map((c) => {
  const antes = llamadas.length;
  const v = m.tomarVuelta(new URLSearchParams(c));
  return [v, llamadas.slice(antes)];  // lo que hizo antes de volver: sin ninguna espera de por medio
});
const dirs = JSON.parse(process.argv[3]).map((d) => [d, m.direccionDeMnemo(d)]);
console.log(JSON.stringify({ casos, dirs }));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="sin Node para cargar web/js/vistas/ajustes.js")
@pytest.mark.parametrize("base", ["", "/panel"])
def test_tomar_la_vuelta_y_la_direccion_de_mnemo_con_node(base):
    consultas = [
        "?code=c0de&state=st4te&iss=https%3A%2F%2Fmnemo.example.org",
        "?error=access_denied&error_description=El%20usuario%20cancel%C3%B3&state=st4te"
        "&iss=https%3A%2F%2Fmnemo.example.org",
        "?error=access_denied",             # sin state: no sirve, pero igual sale de la dirección
        "?code=" + "x" * 3000 + "&state=" + "s" * 300,  # recortado a los topes de la API
        "?p=solicitudes",                   # no es una vuelta: no toca la dirección
        "",
    ]
    direcciones = [
        "https://mnemo.example.org/oauth/authorize?client_id=x&state=y",
        "http://127.0.0.1:8080/oauth/authorize?x=1", "http://localhost:8080/oauth/authorize", "http://[::1]:8080/a",
        # Lo demás no se abre
        "http://mnemo.example.org/oauth/authorize", "javascript:alert(1)", "data:text/html,<b>x</b>",
        "https://usuario:clave@mnemo.example.org/oauth/authorize", "/oauth/authorize", "//mnemo.example.org/x",
        "ftp://mnemo.example.org/x", "", "https://" + "a" * 4000 + ".example.org/",
    ]
    r = subprocess.run(["node", "--input-type=module", "-e", NODE_AJUSTES, base, json.dumps(consultas),
                        json.dumps(direcciones)], cwd=RAIZ, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    salida = json.loads(r.stdout)
    ajustes = f"{base}/ajustes"
    a, b, c, d, e, f = salida["casos"]
    assert a == [{"state": "st4te", "code": "c0de", "iss": "https://mnemo.example.org"}, [[{"previo": 1}, ajustes]]]
    assert b == [{"state": "st4te", "iss": "https://mnemo.example.org", "error": "access_denied",
                  "error_description": "El usuario canceló"}, [[{"previo": 1}, ajustes]]]
    assert c == [{}, [[{"previo": 1}, ajustes]]]
    assert d[0] == {"code": "x" * 2000, "state": "s" * 200} and d[1] == [[{"previo": 1}, ajustes]]
    assert e == [None, []] and f == [None, []]
    abiertas = {k: v for k, v in salida["dirs"] if v is not None}
    assert abiertas == {d: d for d in direcciones[:4]}, abiertas  # https o la propia máquina, tal cual


# ───────────────────────────── El contexto y los códigos del proveedor del modelo ─────────────────────────────

NODE_FILTROS = r"""
globalThis.document = { querySelector: () => null, documentElement: {} };
globalThis.MutationObserver = class { observe() {} };
globalThis.window = globalThis;
globalThis.addEventListener ||= () => {};
const m = await import('./web/js/agente.js');
const claves = JSON.parse(process.argv[1]).filter((k) => Object.keys(m.filtrosDe(`?${encodeURIComponent(k)}=1`)).length);
const consultas = JSON.parse(process.argv[2]).map((q) => m.filtrosDe(q));
console.log(JSON.stringify({ claves, consultas }));
"""
# El estado de las vistas que va en la dirección, además de los filtros de Habitantes y el mapa
CLAVES_DE_VISTA = {"ids_total", "orden", "pagina", "p", "uid", "desde", "hasta", "por", "agrupar"}


@pytest.mark.skipif(shutil.which("node") is None, reason="sin Node para cargar web/js/agente.js")
def test_el_contexto_solo_lleva_claves_de_filtro_conocidas():
    from app.api.filtros import Filtros
    filtros = set(Filtros.model_fields)
    candidatas = sorted(filtros | CLAVES_DE_VISTA | set(VUELTA) | {"session_state", "code_verifier", "token", "otra",
                                                                  "__proto__", "constructor"})
    consultas = [
        "?code=c0de&state=st4te&iss=https%3A%2F%2Fmnemo.example.org&zona=rural&q=Ana&orden=nombre&p=solicitudes",
        "?error=access_denied&error_description=No&state=x&otra=1&zona=urbana&zona=rural",
        "&".join(f"{k}=1" for k in sorted(filtros)[:40]),  # como mucho 30 claves
        "?q=" + "a" * 300,
    ]
    r = subprocess.run(["node", "--input-type=module", "-e", NODE_FILTROS, json.dumps(candidatas),
                        json.dumps(consultas)], cwd=RAIZ, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    salida = json.loads(r.stdout)
    # Pasan los filtros de Habitantes y el mapa y el estado conocido de las vistas; nada de la vuelta de Mnemo
    assert set(salida["claves"]) == filtros | CLAVES_DE_VISTA, set(salida["claves"]) ^ (filtros | CLAVES_DE_VISTA)
    a, b, c, d = salida["consultas"]
    assert a == {"zona": "rural", "q": "Ana", "orden": "nombre", "p": "solicitudes"}
    assert b == {"zona": "urbana"}  # la primera vez que aparece cada clave
    assert len(c) == 30 and d == {"q": "a" * 200}
    # contexto() usa esa lista (y no toda la consulta)
    contexto = _funcion(_sin_comentarios(AGENTE), "contexto")
    assert "filtros: filtrosDe(location.search)," in contexto and "URLSearchParams" not in contexto


def test_codigos_del_proveedor_del_modelo_en_el_widget():
    codigo = _sin_comentarios(AGENTE)

    def conjunto(nombre: str) -> set[str]:
        m = re.search(rf"const {nombre} = new Set\(\[(.*?)\]\);", codigo, re.S)
        assert m, nombre
        return set(re.findall(r"'([a-z_]+)'", m.group(1)))

    # Repetir el mismo mensaje no arregla la conexión caída, el plan, los créditos, una conversación que no cabe ni otro
    # proveedor (§4 del diseño)
    assert {"proveedor", "mnemo_conexion", "mnemo_plan", "mnemo_creditos", "larga"} <= conjunto("SIN_REINTENTO")
    # Pero sí puede arreglar una petición rechazada (Mnemo da `llm_peticion` también ante una sobrecarga del proveedor a
    # mitad de la respuesta) y una cuenta sin modelo disponible ahora (`mnemo_sin_modelo`, también con el proveedor caído
    # un momento): ofrecen «Reintentar»
    assert not {"llm_peticion", "mnemo_sin_modelo"} & conjunto("SIN_REINTENTO")
    # «Nueva conversación» cuando esta puede no servir; la conexión caída o sin modelo vuelve a leer el estado
    assert {"proveedor", "larga", "llm_peticion", "borrada", "no_existe"} <= conjunto("CON_NUEVA")
    assert {"mnemo_conexion", "mnemo_sin_modelo", "sin_configurar", "agente_apagado"} <= conjunto("RELEER_ESTADO")
    cerrar = _funcion(codigo, "cerrarTurno")
    assert "const releer = (codigo) => { if (RELEER_ESTADO.has(codigo)) releerEstado(); };" in cerrar
    assert "releer(codigo);" in cerrar and "releer(t.error.codigo);" in cerrar  # antes del flujo y en un `error`
    assert cerrar.count("CON_NUEVA.has(") == 2  # antes del flujo y en un evento `error`
    # En un evento `error`, «Reintentar» no depende de «Nueva conversación»: `llm_peticion` ofrece las dos
    en_error = cerrar[cerrar.index("} else if (t.error) {"):cerrar.index("} else if (!t.fin) {")]
    assert ("if (t.tipo === 'mensaje' && !SIN_REINTENTO.has(t.error.codigo)) acciones.push(reintento(null));\n"
            "      if (CON_NUEVA.has(t.error.codigo)) acciones.push(otra);") in en_error, en_error
    # El evento nuevo `texto_ronda` reemplaza el texto de la ronda en curso
    assert ("case 'texto_ronda': if (typeof ev.texto === 'string') textoRonda(texto(ev.texto, MAX_TEXTO_RONDA)); "
            "break;") in codigo
    ronda = _funcion(codigo, "textoRonda")
    assert "ronda.partes" in ronda and "ronda.recortes" in ronda


def test_un_trozo_de_texto_largo_no_se_corta():
    """Con Mnemo, un solo evento `texto` puede traer el texto entero de la ronda (un proveedor sin flujo, o lo que faltaba
    al final), y el servidor no manda `texto_ronda` si coincide con lo que emitió: el trozo va con el tope de
    `texto_ronda` (el de una conversación guardada), no con el de 4 000 de los demás textos."""
    codigo = _sin_comentarios(AGENTE)
    assert "const MAX_TEXTO_RONDA = 100000;" in codigo
    caso = codigo[codigo.index("case 'texto': {"):codigo.index("case 'texto_ronda':")]
    assert "const trozo = texto(ev.texto, MAX_TEXTO_RONDA);" in caso and "agregarTexto(trozo)" in caso, caso
    # Al reabrirla desde el historial se pinta con el mismo tope
    assert "texto(p.texto, 100000)" in _funcion(codigo, "pintarConversacion")


def test_el_asistente_se_entera_de_que_se_conecto_mnemo_sin_recargar():
    """«Lo vinculé y no se da»: al volver de Mnemo, el asistente lee su estado a la vez que Ajustes canjea el código y se
    queda con el de antes (sin conectar) unos minutos. Ajustes le avisa con un evento después de conectar, de desconectar
    y de guardar los ajustes del asistente; el asistente vuelve a pedir el estado esperando la lectura en curso (que es
    de antes), también con el panel abierto. Y al abrirlo sin modelo lo vuelve a pedir (otra pestaña no avisa). La
    prueba con el navegador está en test_agente_navegador.py (`test_conectar_mnemo_desde_ajustes`)."""
    agente, ajustes = _sin_comentarios(AGENTE), _sin_comentarios(AJUSTES)
    # El mismo evento en los dos lados
    assert "const EVENTO_ESTADO = 'agente:estado';" in agente and "const EVENTO_ESTADO = 'agente:estado';" in ajustes
    assert "window.addEventListener(EVENTO_ESTADO, () => { releerEstado(); });" in agente
    assert "window.dispatchEvent(new Event(EVENTO_ESTADO));" in _funcion(ajustes, "avisarAlAsistente")
    # Se vuelve a pedir esperando la lectura en curso (puede ser de antes del cambio), y se aplica si está a la vista
    releer = _funcion(agente, "releerEstado")
    assert releer.index("await listos;") < releer.index("if (leyendo) await leyendo;") < releer.index(
        "await leerEstado();") < releer.index("if (visible) aplicarEstado();"), releer
    # A mitad de un turno el panel no cambia: se aplica al terminarlo
    assert "if (turno) { estadoPendiente = true; return; }" in _funcion(agente, "aplicarEstado")
    correr = _funcion(agente, "correr")
    assert correr.index("cerrarTurno(t, terminado);") < correr.index("if (estadoPendiente) {")
    # Al abrirlo sin modelo, otra vez (salvo al restaurarlo al cargar la página, recién leído)
    assert "if (releer && !info.disponible) releerEstado();" in _funcion(agente, "abrir")
    assert "abrir({ foco: false, releer: false });" in _funcion(agente, "mostrar")
    # Ajustes avisa tras el POST a /volver que salió bien, tras desconectar y al guardar los ajustes del asistente
    volver = _funcion(ajustes, "volverDeMnemo")
    assert volver.index("await api.post('/api/agente/mnemo/volver', v);") < volver.index("avisarAlAsistente();") < \
        volver.index("} catch (err) {"), volver
    desconectar = _funcion(ajustes, "desconectarMnemo")
    assert desconectar.index("await api.del('/api/agente/mnemo')") < desconectar.index("avisarAlAsistente();") < \
        desconectar.index("await pintar();"), desconectar
    assert "if (asistente) avisarAlAsistente();" in ajustes and ajustes.count("{ asistente: true }") == 1
    agente_form = ajustes[ajustes.index("} else if (f.id === 'f-agente') {"):ajustes.index("} else if (f.id === 'f-campo') {")]
    assert "{ asistente: true }" in agente_form


def test_la_explicacion_no_nombra_variables_de_entorno():
    # Sin modelo, el widget explica qué hacer (conectar Mnemo en Ajustes): sin nombres de variables ni tokens
    variables = ("ANTHROPIC_API_KEY", "MNEMO_TOKEN", "MNEMO_MCP_URL", "MNEMO_MODELO", "MNEMO_HERRAMIENTAS",
                 "AGENTE_MODELO", "AGENTE_ESFUERZO", "mnemo_pat_")
    for nombre, texto in (("agente.js", AGENTE), ("ajustes.js", AJUSTES)):
        codigo = _sin_comentarios(texto)
        assert not [v for v in variables if v in codigo], nombre
    explicacion = _funcion(_sin_comentarios(AGENTE), "pintarExplicacion")
    assert ("El asistente usa los modelos de su cuenta de Mnemo. El administrador lo conecta en ', ajustes(),\n"
            "        ': inicia sesión en Mnemo y da permiso; no hay que copiar claves.'") in explicacion
    assert "info?.esAdmin ? destinoEnlace('/ajustes', op) : null" in explicacion
    assert "'Se cortó la conexión con Mnemo'" in explicacion
    assert "'Mnemo está conectado sin permiso para usar sus modelos'" in explicacion


def test_sin_permiso_de_modelos_no_manda_a_marcar_una_casilla_que_puede_no_estar():
    """Conectado sin `mnemo:model`: puede que en Mnemo no se dejara marcado «Usar tus modelos de IA y tus créditos», o
    que ese Mnemo todavía no lo ofrezca (uno sin actualizar no muestra la casilla, y volver a conectar daría lo mismo).
    Ajustes y el widget dicen que se vuelva a conectar dejándolo marcado y, si Mnemo no lo muestra, que hay que
    actualizar Mnemo; nunca solo «marque la casilla»."""
    explicacion = _funcion(_sin_comentarios(AGENTE), "pintarExplicacion")
    rama = explicacion[explicacion.index("falta === 'sin_modelo'"):explicacion.index("falta === 'otro'")]
    ajustes = AJUSTES[AJUSTES.index("const SIN_PERMISO_MODELO = {"):AJUSTES.index("const EVENTO_ESTADO")]
    for nombre, texto in (("agente.js", rama), ("ajustes.js", ajustes)):
        plano = re.sub(r"'\s*\+\s*'", "", texto)  # las cadenas partidas en dos líneas, juntas
        assert "dejando marcado «Usar tus modelos de IA y tus créditos»" in plano, nombre
        assert "Si Mnemo no muestra esa casilla, hay que actualizar Mnemo." in plano, nombre
        assert not re.search(r"\bmarque\b|\bmarcar la casilla\b|marque esa casilla", plano), nombre
    # Al coordinador (no conecta) se le dice que lo hace el administrador
    assert "SIN_PERMISO_MODELO[admin ? 'admin' : 'otro']" in AJUSTES
    assert "el administrador tiene que volver a conectar" in re.sub(r"'\s*\+\s*'", "", ajustes)
    # Si la vista dice que ese Mnemo no ofrece el permiso (`ofrece_modelo` false: conectado solo para sus herramientas,
    # en modo directo), no hay casilla que marcar: hay que actualizar Mnemo
    assert "c.ofrece_modelo === false ? NO_OFRECE_MODELO :" in AJUSTES
    no_ofrece = re.sub(r"'\s*\+\s*'", "", AJUSTES[AJUSTES.index("const NO_OFRECE_MODELO"):])
    assert "hay que actualizar Mnemo y volver a conectar" in no_ofrece.split(";")[0]
    widget = _funcion(_sin_comentarios(AGENTE), "faltaDeModelo")
    assert "c.modelo ? 'otro' : c.ofreceModelo ? 'sin_modelo' : 'no_ofrece'" in widget
    assert "ofreceModelo: c.ofrece_modelo !== false" in AGENTE and "falta === 'no_ofrece'" in explicacion


def test_cada_motivo_de_caida_tiene_su_explicacion():
    """La conexión queda «caida» con un motivo (`_caer` en app/agente/mnemo_conexion.py): Ajustes y el widget explican
    cada uno, también los que se agreguen (si no, solo dirían que dejó de valer)."""
    conexion = (RAIZ / "app" / "agente" / "mnemo_conexion.py").read_text(encoding="utf-8")
    motivos = set(re.findall(r"_caer,[^)\n]*\"([a-z_]+)\"\)", conexion))
    assert {"revocada", "clave", "error"} <= motivos, motivos
    for nombre, texto in (("agente.js", AGENTE), ("ajustes.js", AJUSTES)):
        tabla = re.search(r"const CAIDA_MNEMO = \{(.*?)\n\};", texto, re.S)
        assert tabla, nombre
        claves = set(re.findall(r"^\s*([a-z_]+):", tabla.group(1), re.M))
        assert motivos <= claves, (nombre, motivos - claves)
