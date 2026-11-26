"""Importar y exportar → Planillas por foto, sin navegador (web/js/vistas/importar.js, web/css/planillas.css, el enlace
de index.html y la insignia de «Mi cuenta» en web/js/app.js): la vista llama solo a rutas que existen y con su método;
la foto vive en un canvas (nunca en una URL ni en el almacenamiento del navegador); todo se arma con `html`; sus
columnas, largos, topes, estados y motivos son los del servidor; los estilos solo usan los tokens del tema; y cada
insignia del menú es una clave de /api/insignias. El recorrido entero, con la API de verdad, está en
tests/test_planillas_vista_web.py."""
import re
from pathlib import Path

from app import planillas as pl
from app.agente import lector_planillas as lector
from app.pipeline import importar as imp
from test_responsivo import _fuera_de_hover
from test_web_rutas_api import LITERALES, _existe

WEB = Path(__file__).resolve().parents[1] / "web"
VISTA = (WEB / "js" / "vistas" / "importar.js").read_text(encoding="utf-8")
CSS = WEB / "css" / "planillas.css"
APP = (WEB / "js" / "app.js").read_text(encoding="utf-8")


def _objeto(nombre: str, texto: str = VISTA) -> str:
    m = re.search(rf"const {nombre} = \{{(.*?)\n?\}};", texto, flags=re.S)
    assert m, nombre
    return m.group(1)


def _claves(nombre: str, texto: str = VISTA) -> list[str]:
    return re.findall(r"(?:^|[\s{,])(\w+):", _objeto(nombre, texto))


def _constante(nombre: str) -> str:
    m = re.search(rf"\b{nombre} = ([^;,\n]+)", VISTA)
    assert m, nombre
    return m.group(1).strip()


def _sin_comentarios(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


# ───────────────────────────── Rutas ─────────────────────────────

def test_la_vista_llama_a_las_rutas_de_la_bandeja_con_su_metodo():
    usadas = {(f, m) for a, f, m in LITERALES if a == "vistas/importar.js"}
    esperadas = {
        ("/api/planillas/fotos", None),                 # la subida: api.subir con la consulta armada aparte
        ("/api/planillas", "GET"), ("/api/planillas/X", "GET"), ("/api/planillas/X", "PATCH"),
        ("/api/planillas/X", "DELETE"), ("/api/planillas/X/foto", None),  # la foto: fetch con la sesión, a un canvas
        ("/api/planillas/X/leer", "POST"), ("/api/planillas/X/simular", "POST"), ("/api/planillas/X/cargar", "POST"),
        ("/api/agente/estado", "GET"), ("/api/ajustes", "GET"),
        ("/api/importaciones/X/confirmar-autorizaciones", "POST"),
    }
    assert esperadas <= usadas, esperadas - usadas
    faltan = [(f, m) for f, m in usadas if not _existe(f, m)]
    assert not faltan, faltan
    # La subida es el cuerpo crudo (api.subir), con tiempo límite, y la carga lleva su Idempotency-Key
    assert "api.subir(ruta, prep.blob, { timeout: SUBIDA_MS" in VISTA
    assert re.search(r"/cargar`, cuerpo, \{ \.\.\.op, clave: claveCarga", VISTA)


def test_los_ids_de_planilla_se_validan_antes_de_ir_a_la_ruta():
    assert _constante("ID_PLANILLA") == "/^[0-9a-f]{32}$/"
    assert pl.ID.pattern == "[0-9a-f]{32}"
    for funcion in ("async function abrir(id", "async function releer(id", "async function borrar(id"):
        cuerpo = VISTA[VISTA.index(funcion):VISTA.index(funcion) + 200]
        assert "if (!ID_PLANILLA.test(id)) return;" in cuerpo, funcion


# ───────────────────────────── Privacidad de la foto ─────────────────────────────

def test_la_foto_solo_vive_en_un_canvas_y_en_memoria():
    for vedado in (".src =", ".src=", "createObjectURL", "localStorage", "sessionStorage", "indexedDB", "caches.",
                   "console.log", "FileReader", "toDataURL"):
        assert vedado not in VISTA, vedado
    # La foto se pide con la sesión, sin caché, y se dibuja con createImageBitmap en un canvas; se suelta al salir
    pedido = VISTA[VISTA.index("async function cargarFoto"):VISTA.index("function dibujarFoto")]
    assert "credentials: 'same-origin'" in pedido and "cache: 'no-store'" in pedido and "createImageBitmap" in pedido
    soltar = VISTA[VISTA.index("function soltarFoto"):VISTA.index("async function cargarFoto")]
    assert "foto?.close()" in soltar and "pedidoFoto?.abort()" in soltar and "c.width = c.height = 0" in soltar
    limpieza = VISTA[VISTA.rindex("return () => {"):]
    for paso in ("vivo = false", "clearTimeout(reloj)", "control.abort()", "soltarFoto()", "quitarPendiente()",
                 "removeEventListener('visibilitychange'"):
        assert paso in limpieza, paso


def test_la_foto_se_vuelve_a_codificar_en_el_navegador():
    # Se abre derecha según su EXIF, se dibuja en un canvas y sale como JPEG nuevo: sin EXIF, GPS ni modelo del teléfono
    inicio = VISTA.index("async function prepararFoto")
    prep = VISTA[inicio:VISTA.index("// ───", inicio)]
    assert "abrirImagen(archivo)" in prep and "pintarEn(c, bmp)" in prep and "codificar(c, lim)" in prep
    assert "bmp.close()" in prep
    assert "imageOrientation: 'from-image'" in VISTA and "c.toBlob(listo, 'image/jpeg', calidad)" in VISTA


def test_camara_galeria_y_aviso_fijo():
    assert re.search(r'<input type="file" id="pf-camara-in" accept="image/\*" capture="environment"', VISTA)
    assert re.search(r'<input type="file" id="pf-galeria-in" accept="image/jpeg,image/png,image/\*" multiple', VISTA)
    aviso = re.search(r"const AVISO_FOTOS = ('[^']*'\s*\+\s*'[^']*');", VISTA).group(1)
    widget = re.search(r"const AVISO_FOTOS = ('[^']*'\s*\+\s*'[^']*');",
                       (WEB / "js" / "agente.js").read_text(encoding="utf-8")).group(1)
    assert aviso == widget  # el mismo texto que junto a la cámara del chat
    assert "No fotografíe cédulas" in aviso


def test_todo_se_arma_con_html():
    assert not re.search(r"import\s*\{[^}]*\bcrudo\b[^}]*\}", VISTA)
    assert "innerHTML" not in VISTA and "insertAdjacentHTML" not in VISTA and "new Crudo(" not in VISTA


# ───────────────────────────── El mismo vocabulario que el servidor ─────────────────────────────

def test_columnas_y_largos_como_el_lector():
    assert _claves("COLUMNAS") == list(lector.COLUMNAS)
    largos = dict(re.findall(r"(\w+): (\d+)", _objeto("LARGOS")))
    assert {k: int(v) for k, v in largos.items()} == lector.LARGOS


def test_topes_como_el_servidor():
    assert int(_constante("MAX_BYTES")) == pl.MAX_BYTES
    assert int(_constante("LADO_MIN")) == pl.LADO_MIN and int(_constante("LADO_SERVIDOR")) == pl.LADO_MAX
    assert re.search(rf"const LADO_DIRECTO = {pl.LADO_DIRECTO}, LADO_MNEMO = {pl.LADO_MNEMO};", VISTA)
    assert re.search(rf"const NOTA_MAX = {pl.NOTA_MAX}, FOLIO_MAX = {pl.FOLIO_MAX},", VISTA)
    assert int(_constante("LECTURAS_MAX")) == pl.LECTURAS_MAX
    assert _claves("FORMATOS") == list(lector.PEDIDOS)
    assert re.search(r"const FIRMAS = \{[^}]*\}", VISTA) and set(_claves("FIRMAS")) == set(lector.FIRMAS)


def test_los_avisos_de_la_lectura_y_la_descripcion():
    """Lo que avisa una lectura guardada (`lector_planillas.AVISOS`) se dice con el mismo texto; la descripción (que
    escribió el modelo) se pinta solo con `html`, que la escapa, y una foto sin filas no ofrece cotejar ni cargar. El
    formato de la subida se elige siempre (el ajuste `otros_formatos` se retiró)."""
    avisos = dict(re.findall(r"(\w+): '([^']*)'", _objeto("AVISOS_LECTURA")))
    assert avisos == lector.AVISOS == pl.AVISOS
    assert "otros_formatos" not in "\n".join(l for l in VISTA.splitlines() if not l.lstrip().startswith("//"))
    assert '<select id="pf-formato">' in VISTA and "ap?.otros_formatos" not in VISTA
    pintar = VISTA[VISTA.index("function pintarAbierta() {"):VISTA.index("function actualizarAcciones() {")]
    assert "const descripcion = typeof d.descripcion === 'string' ? d.descripcion.trim() : '';" in pintar
    assert '<p class="pf-descripcion-texto">${descripcion}</p>' in pintar  # dentro de un html`…`: escapada
    assert "const puedeCargar = d.estado === 'leida' && filas.length > 0;" in pintar
    css = _sin_comentarios(CSS.read_text(encoding="utf-8"))
    assert re.search(r"\.pf-descripcion-texto \{[^}]*white-space: pre-line", css)


def test_cada_estado_y_motivo_tiene_su_texto():
    # El estado de cada fila (`planillas._estado_fila`), la vista previa, lo cargado y los motivos del importador
    assert set(_claves("ESTADOS_FILA")) == {"pendiente", "no_autoriza", "no_se_carga", "descartada", "cargada"}
    simulados = {*imp.ESTADOS_SIMULACION, "sin_nombre", "ya_cargada", "descartada"}
    assert simulados <= set(_claves("COTEJO")), simulados - set(_claves("COTEJO"))
    cargados = {imp.ESTADO_CARGADO.get(e, e) for e in simulados} | {"no_guardada"}
    assert cargados <= set(_claves("CARGADO")), cargados - set(_claves("CARGADO"))
    motivos = {*imp.MOTIVOS_CONFLICTO, "posible_duplicado", "posible_digitacion", "puesto_de_otra_eleccion",
               "cruce_automatico"}
    fuente = (Path(imp.__file__)).read_text(encoding="utf-8")
    for m in motivos - set(imp.MOTIVOS_CONFLICTO):
        assert f'"{m}"' in fuente, m  # los motivos que la vista conoce existen en el importador
    assert motivos <= set(_claves("MOTIVOS"))
    assert {"leyendo", "leida", "fallida", "rechazada", "cargada"} == set(pl.ESTADOS)
    for estado in pl.ESTADOS:
        assert f"case '{estado}':" in VISTA, estado


# ───────────────────────────── Estilos ─────────────────────────────

def test_index_enlaza_los_estilos_de_planillas():
    index = (WEB / "index.html").read_text(encoding="utf-8")
    assert '<link rel="stylesheet" href="/static/css/planillas.css">' in index and CSS.is_file()
    assert index.index("app.css") < index.index("planillas.css")


def test_los_estilos_solo_usan_tokens_y_respetan_el_tema():
    css = _sin_comentarios(CSS.read_text(encoding="utf-8"))
    # Ningún color propio: los tokens de app.css siguen el tema claro y oscuro
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", css)
    assert not re.search(r"\b(rgb|rgba|hsl|hsla|oklch|lab)\(\s*\d", css)
    assert ":root" not in css and "prefers-color-scheme" not in css and "!important" not in css
    # Las capas, debajo del velo (29) y del menú (30) del celular
    assert all(int(z) < 29 for z in re.findall(r"z-index:\s*(\d+)", css))
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert _fuera_de_hover(css) == []  # `:hover` solo con ratón
    # Lo dudoso, lo ilegible y lo corregido llevan un signo además del color
    for marca, signo in (("dudoso", "?"), ("ilegible", "✕"), ("corregido", "✓")):
        assert re.search(rf'\.pf-celda\[data-marca="{marca}"\]::before \{{ content: "{re.escape(signo)}"', css), marca
    # Todas las clases que usa la vista están en la hoja (o en app.css)
    usadas = set(re.findall(r"\bpf-[a-z-]+", VISTA)) - {"pf-camara-in", "pf-galeria-in"}
    definidas = set(re.findall(r"\.(pf-[a-z-]+)", css)) | set(re.findall(r"#(pf-[a-z-]+)", css))
    ids = set(re.findall(r'id="(pf-[a-z-]+)"', VISTA)) | set(re.findall(r"'#(pf-[a-z-]+)'", VISTA))
    sin_estilo = usadas - definidas - ids - {"pf-titulo", "pf-cuenta", "pf-abierta-titulo", "pf-resultado-titulo"}
    assert not sin_estilo, sin_estilo


# ───────────────────────────── Insignias del menú ─────────────────────────────

def test_la_insignia_de_mi_cuenta_cuenta_las_propuestas_mcp(sesion):
    insignias = dict(re.findall(r"(\w+): '(\w+)'", _objeto("INSIGNIAS", APP)))
    titulos = _claves("TITULOS_INSIGNIA", APP)
    assert insignias["cuenta"] == "propuestas_mcp" and set(titulos) == set(insignias)
    # Cada nav del menú con insignia existe y cada clave la responde /api/insignias
    navs = set(re.findall(r"\['(\w+)', '[^']+', '/[^']*', '[\w.]+'\]", APP))
    assert set(insignias) <= navs
    r = sesion.get("/api/insignias")
    assert r.status_code == 200 and set(insignias.values()) <= set(r.json())
