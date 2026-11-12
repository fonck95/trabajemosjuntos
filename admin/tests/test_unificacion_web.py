"""Revisión en bloque de coincidencias y código de color por fuente (web/js/vistas/calidad.js, ui.js, css/fuentes.css y
css/unificacion.css; las insignias del directorio y de la ficha).

* Sin navegador: el catálogo y los ayudantes de fuentes de ui.js, en Node (son puros); los estilos nuevos usan solo los
  tokens de app.css y index.html los enlaza; calidad.js no tiene su propio catálogo de fuentes.
* En Chromium, contra el panel de verdad (uvicorn, en /panel como en Railway) con personas inventadas: las rutas
  GET /api/coincidencias/grupos y POST /api/coincidencias/lote se contestan desde el navegador (`route.fulfill`) según el
  contrato (así la prueba no depende del backend de la unión en lote), con un «servidor» en el guion que lleva el
  estado de los grupos. Se revisa el render y los conteos, la selección y la unión en bloque (el cuerpo exacto del POST),
  «Unir las N muy probables» con su progreso (sin reintentar un grupo que falló) y «Detener», los atajos de teclado,
  el celular (sin desborde de la página en 390×844 y 320×568, la grilla que se desplaza dentro de la tarjeta con los
  rótulos fijos, la barra fija abajo y blancos de 44 px), el modo oscuro y el contraste de las insignias en los dos
  temas; y, con la API real, las insignias de la ficha, el enlace «revisar» y las del directorio. También lo que la
  revisión encontró: el botón masivo respeta lo marcado en las tarjetas y el filtro de una ficha, «Siguiente» no se salta
  grupos tras resolver ni mientras se resuelve uno (los botones de página quedan quietos hasta la respuesta), la vista
  previa estimada deja el lugar de la mejor ubicada, un enlace viejo o una falla dejan
  salida, los atajos no corren fuera de la vista, «Nuevo lugar» pregunta antes de perder lo escrito y la barra de
  selección no queda bajo la franja «Llamada sin registrar». Sin violaciones de la CSP ni errores de consola.
* En Chromium, con la unión de verdad (otro panel, con su propia base y sin `route.fulfill` para los grupos), lo que la
  segunda verificación reprodujo así: la vista previa estimada al conservar otra ficha promete lo que la unión deja en
  la base (la edad declarada en otro año, una dirección con otras mayúsculas, la ubicación que pasa en bloque con su
  dirección y la edad declarada que llega a una ficha con fecha de nacimiento), los atajos no corren con el asistente
  abierto ni cuando él recarga la vista o lleva a ella, y la paginación tras resolver no dice «1 de 1» con «Siguiente».

Las capturas quedan en CAPTURAS_UNIFICACION si se define (para mirarlas a mano). Se salta si no hay Node con
Playwright, salvo en el CI (allí falla en vez de pasar en silencio).
"""
import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

import pymongo
import pytest
import uvicorn

from conftest import MONGO, URI, insertar_personas
from test_agente_mapa import requiere_navegador

RAIZ = Path(__file__).resolve().parents[1]
WEB = RAIZ / "web"
CSS_FUENTES = WEB / "css" / "fuentes.css"
CSS_UNIFICACION = WEB / "css" / "unificacion.css"

# El token de cada fuente visible (la especificación del código de color; ningún color propio)
TOKENS = {"equipo": "--s1", "reunion": "--s5", "planilla": "--s3", "consultor": "--s4", "titular": "--ok", "tramites": "--s7",
          "cedulas": "--s2", "otra_base": "--muted", "otra": "--muted", "fusion": "--axis"}


# ───────────────────────────── Sin navegador ─────────────────────────────

def test_index_enlaza_los_estilos_nuevos():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    for css in ("fuentes.css", "unificacion.css"):
        assert f'<link rel="stylesheet" href="/static/css/{css}">' in html, css
        assert (WEB / "css" / css).is_file(), css
    # Después de app.css: usan sus tokens y, donde hace falta, ganan a sus reglas de contexto
    assert html.index("app.css") < html.index("fuentes.css") < html.index("unificacion.css")


def _sin_comentarios(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


@pytest.mark.parametrize("ruta", [CSS_FUENTES, CSS_UNIFICACION], ids=lambda p: p.name)
def test_los_estilos_nuevos_solo_usan_tokens(ruta):
    css = _sin_comentarios(ruta.read_text(encoding="utf-8"))
    # Ningún color propio: los tokens de app.css ya están validados en claro y oscuro (y siguen el tema)
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", css)
    assert not re.search(r"\b(rgb|rgba|hsl|hsla|oklch|lab)\(\s*\d", css)
    assert ":root" not in css and "prefers-color-scheme" not in css and "!important" not in css
    # Las capas, debajo del velo (29) y del menú (30) del celular: «Cerrar sesión» nunca queda tapado
    assert all(int(z) < 29 for z in re.findall(r"z-index:\s*(\d+)", css))
    assert "@media (prefers-reduced-motion: reduce)" in css


def test_cada_fuente_tiene_su_token_y_su_forma():
    css = _sin_comentarios(CSS_FUENTES.read_text(encoding="utf-8"))
    for clave, token in TOKENS.items():
        regla = re.search(rf'\.fuente\[data-fuente="{clave}"\][^{{]*\{{\s*--fx:\s*var\(([^)]+)\)', css)
        assert regla and regla.group(1) == token, clave
    # La forma separa los grupos sin depender del color: rellena, solo borde o punteada
    assert re.search(r'\.fuente\[data-grupo="equipo"\]\s*\{[^}]*background:\s*color-mix\(in srgb, var\(--fx\) 16%, transparent\)', css)
    assert re.search(r'\.fuente\[data-grupo="base"\]\s*\{[^}]*border-width', css)
    assert re.search(r'\.fuente\[data-grupo="otra"\]\s*\{[^}]*border-style:\s*dashed', css)
    # La letra mezcla el color con la tinta (contraste) y el borde va con el color de la fuente
    assert "--fx-tinta: color-mix(in srgb, var(--fx) 50%, var(--ink))" in css


def test_las_vistas_usan_el_catalogo_de_ui_js():
    calidad = (WEB / "js" / "vistas" / "calidad.js").read_text(encoding="utf-8")
    assert not re.search(r"\bconst FUENTES\b", calidad), "calidad.js no tiene su propio catálogo de fuentes"
    importado = re.search(r"import \{([^}]*)\} from '\.\./ui\.js'", calidad).group(1)
    for nombre in ("insigniaFuente", "insigniasFuentes", "leyendaFuentes", "fuentesVisibles"):
        assert re.search(rf"\b{nombre}\b", importado), nombre
    for vista in ("personas.js", "ficha.js"):
        t = (WEB / "js" / "vistas" / vista).read_text(encoding="utf-8")
        assert "FUENTES[" not in t and "insigniasFuentes(" in t, vista
    # La pestaña usa las rutas del contrato de la unión en lote (y ya no la de un par)
    assert "api.get('/api/coincidencias/grupos'" in calidad and "api.post('/api/coincidencias/lote'" in calidad
    assert "api.post(`/api/coincidencias/${" not in calidad
    ficha = (WEB / "js" / "vistas" / "ficha.js").read_text(encoding="utf-8")
    assert 'href="/calidad?p=coincidencias&persona=${p.id}"' in ficha


def _llamadas_a_dialogo(js: str) -> list[str]:
    """El texto de cada `dialogo({...})` del módulo, de la llave que abre a la que cierra (las `${…}` de las plantillas
    están balanceadas)."""
    salida = []
    for m in re.finditer(r"\bdialogo\(\{", js):
        nivel, i = 0, m.end() - 1
        while True:
            nivel += {"{": 1, "}": -1}.get(js[i], 0)
            if nivel == 0:
                break
            i += 1
        salida.append(js[m.start():i + 1])
    return salida


def test_los_dialogos_con_campos_de_calidad_preguntan_antes_de_descartar():
    """Como en el resto del panel: tocar el fondo o Escape con algo escrito pregunta (`sucio`), en vez de perderlo."""
    calidad = (WEB / "js" / "vistas" / "calidad.js").read_text(encoding="utf-8")
    dialogos = _llamadas_a_dialogo(calidad)
    con_campos = [d for d in dialogos if re.search(r"<(input|textarea|select)\b", d)]
    # Corregir cédula, la solicitud, otros nombres de un lugar y nuevo lugar (el progreso de la unión no tiene campos)
    assert len(dialogos) == 5 and len(con_campos) == 4
    sin_sucio = [re.search(r"titulo:\s*([^,]+),", d).group(1) for d in con_campos if not re.search(r"\bsucio:", d)]
    assert not sin_sucio, sin_sucio
    assert re.search(r"\bhayEscrito\b", re.search(r"import \{([^}]*)\} from '\.\./ui\.js'", calidad).group(1))


@pytest.mark.skipif(shutil.which("node") is None, reason="sin Node para cargar web/js/ui.js")
def test_catalogo_y_ayudantes_de_fuentes_en_node():
    codigo = """import * as ui from './web/js/ui.js';
const sinEtiquetas = (s) => String(s);
console.log(JSON.stringify({
  claves: ['manual', 'panel', 'fusion:12', 'fusion', 'cedulas', 'otra_base', 'tramites', 'titular', 'reunion', 'planilla',
           'consultor', 'cruce', 'nueva_fuente', null, '', undefined].map(ui.claveFuente),
  info: ui.FUENTES_INFO,
  insignia: sinEtiquetas(ui.insigniaFuente('panel')),
  conNombre: sinEtiquetas(ui.insigniaFuente('cedulas', { conNombre: true })),
  vacia: sinEtiquetas(ui.insigniaFuente(null)),
  lista: sinEtiquetas(ui.insigniasFuentes(['tramites', 'manual', 'panel', 'cedulas', 'fusion:3', 'titular'])),
  listaVacia: sinEtiquetas(ui.insigniasFuentes([])), listaNula: sinEtiquetas(ui.insigniasFuentes(undefined)),
  visiblesA: ui.fuentesVisibles(true), visiblesP: ui.fuentesVisibles(false),
  leyendaP: sinEtiquetas(ui.leyendaFuentes(ui.fuentesVisibles(false))),
  leyendaA: sinEtiquetas(ui.leyendaFuentes(['cedulas', 'manual', 'panel'])),
  nombres: ['manual', 'fusion:9', 'xyz', null].map(ui.nombreFuente),
  fuentesViejas: ui.FUENTES,
}));"""
    r = subprocess.run(["node", "--input-type=module", "-e", codigo], cwd=RAIZ, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert d["claves"] == ["equipo", "equipo", "fusion", "fusion", "cedulas", "otra_base", "tramites", "titular", "reunion",
                           "planilla", "consultor", "otra", "otra", None, None, None]
    info = d["info"]
    # Las diez claves visibles, en orden de confianza, cada una con su nombre, una letra propia y su grupo
    assert list(info) == ["titular", "equipo", "reunion", "consultor", "planilla", "cedulas", "otra_base", "tramites", "fusion", "otra"]
    assert {k: v["letra"] for k, v in info.items()} == {"titular": "✓", "equipo": "E", "reunion": "R", "consultor": "C", "planilla": "P",
                                                       "cedulas": "B", "otra_base": "O", "tramites": "T", "fusion": "U", "otra": "?"}
    assert {k for k, v in info.items() if v["grupo"] == "equipo"} == {"equipo", "reunion", "planilla", "consultor", "titular"}
    assert {k for k, v in info.items() if v["grupo"] == "base"} == {"tramites", "cedulas", "otra_base"}
    assert info["equipo"]["nombre"] == "Equipo (panel)" and info["titular"]["nombre"] == "Titular en la Registraduría"
    assert info["cedulas"]["nombre"] == "Base con cédula" and info["fusion"]["nombre"] == "Ficha unida"
    assert all(v["nombre"] and v["ayuda"] for v in info.values())
    # La insignia: letra a la vista, nombre completo en title y aria-label; con el nombre, chip con la letra oculta al lector
    assert d["insignia"] == ('<span class="fuente" data-fuente="equipo" data-grupo="equipo" role="img" title="Fuente: Equipo (panel)" '
                             'aria-label="Fuente: Equipo (panel)">E</span>')
    assert 'class="fuente con-nombre" data-fuente="cedulas" data-grupo="base"' in d["conNombre"]
    assert '<span class="letra" aria-hidden="true">B</span>' in d["conNombre"] and d["conNombre"].endswith("Base con cédula</span>")
    assert d["vacia"] == "" and d["listaVacia"] == "" and d["listaNula"] == ""
    # Sin repetidos (manual y panel son una sola) y en orden de confianza
    assert re.findall(r'data-fuente="(\w+)"', d["lista"]) == ["titular", "equipo", "cedulas", "tramites", "fusion"]
    assert d["lista"].startswith('<span class="fuentes">')
    # P nunca ve «cedulas» (la recibe como «otra_base»); A y K, al revés
    assert "cedulas" not in d["visiblesP"] and "otra_base" in d["visiblesP"]
    assert "otra_base" not in d["visiblesA"] and "cedulas" in d["visiblesA"]
    assert "cedulas" not in d["leyendaP"] and "Base con cédula" not in d["leyendaP"] and "Otra base" in d["leyendaP"]
    assert "¿Qué significan los colores?" in d["leyendaA"] and d["leyendaA"].startswith('<details class="leyenda-fuentes">')
    assert re.findall(r'<li data-fuente="(\w+)"', d["leyendaA"]) == ["equipo", "cedulas"]
    assert d["nombres"] == ["Equipo (panel)", "Ficha unida", "Otra fuente", ""]
    # El catálogo viejo sigue (lo leen otras vistas y test_contrato.py)
    assert d["fuentesViejas"]["planilla"] == "Planilla de campo" and d["fuentesViejas"]["otra_base"] == "Otra base"


# ───────────────────────────── En Chromium ─────────────────────────────

def _sembrar(db) -> dict:
    """Dos personas inventadas con fuentes, procedencia, cédula por cruce, teléfonos de dos bases, un valor alterno de
    una ficha unida y un reporte de duplicado sin puntaje entre ellas (la ficha muestra «revisar»)."""
    from app import modelo
    tel = modelo.telefono_nuevo("3001234567", "tramites", fuentes=["tramites", "cedulas"])
    a, b = insertar_personas(db, [
        {"nombre": "MARIA INVENTADA DE PRUEBA", "cedula": "1098765432", "sexo": "F", "edad": 41, "correo": "maria@example.com",
         "telefonos": [tel]},
        {"nombre": "MARIA INVENTADA PRUEBA", "sexo": "F"},
    ], fuente="tramites")
    marca = {"ts": "2026-10-01T10:00:00", "uid": 0}
    db.personas.update_one({"_id": a}, {"$set": {
        "fuentes": ["tramites", "cedulas", "manual"], "cedula_origen": "cruce",
        "procedencia": {"cedula": {"fuente": "cedulas", **marca}, "correo": {"fuente": "tramites", **marca},
                        "sexo": {"fuente": "panel", **marca}, "edad": {"fuente": "cedulas", **marca}},
        "alternos": [{"campo": "correo", "valor": "otra@example.com", "fuente": "fusion:77", **marca}],
    }})
    db.coincidencias.insert_one({"_id": 900001, "persona_id": a, "candidato_id": b, "puntaje": None, "estado": "pendiente",
                                 "motivo": "reporte", "detalle": None})
    # Un conflicto de cédula con una fila de la planilla: su tarjeta lleva la insignia de esa fuente
    db.conflictos_cedula.insert_one({"_id": 900002, "persona_id": a, "motivo": "nombre_distinto", "cedula": "1098765432",
                                     "fuente": "planilla", "estado": "pendiente", "creado_en": "2026-10-02T09:00:00",
                                     "registro": {"nombre": "MARIA OTRA INVENTADA", "cedula": "1098765432", "telefonos": [],
                                                  "fila": 4}})
    return {"persona": a, "otra": b}


# Nombres de pila para los 26 grupos «muy probables» de la base de verdad (un nombre distinto por grupo)
PILAS = ["ANA", "BEATRIZ", "CARMEN", "DIANA", "ELENA", "FABIOLA", "GLORIA", "HILDA", "INES", "JUANA", "KAREN", "LUCIA",
         "MARTA", "NORA", "OLGA", "PAULA", "QUIRINA", "ROSA", "SARA", "TERESA", "URSULA", "VILMA", "WILMA", "XIMENA",
         "YOLANDA", "ZORAIDA"]


def _sembrar_reales(db) -> dict:
    """Para los casos con la unión de verdad, como los armó la verificación: 26 grupos «muy probables» (una ficha de la
    base con cédula y otra de trámites con el mismo nombre y teléfono, puntaje 0,95) y tres pares para la vista previa
    estimada, cada uno con la ficha A de la base con cédula (la que se conserva por defecto) y la B de trámites:
    40 años declarados hace diez días frente a 40 declarados diez años antes (hoy 40 y 50), 40 declarados seis años antes
    frente a 46 de hoy (hoy los dos 46) y la misma dirección con otras mayúsculas. Esos tres no tienen ninguna señal
    fuerte: no son «muy probables» y no cambian la cuenta de los 26. Y dos más de la tercera verificación (la ubicación
    con su dirección y la edad con su referencia), con `tambien`: otra fila de la celda «Quedaría» que se mira."""
    from app import modelo
    ids = iter(range(910001, 911000))
    coinc = []

    def par(a, b, puntaje):
        coinc.append({"_id": next(ids), "persona_id": a, "candidato_id": b, "estado": "pendiente", "puntaje": puntaje,
                      "motivo": "cruce_cedula", "detalle": {"puntaje_nombre": puntaje}})
        return coinc[-1]["_id"]

    for i, pila in enumerate(PILAS):
        nombre = f"{pila} INVENTADA PAGINA PRUEBA"
        x, = insertar_personas(db, [{"nombre": nombre, "cedula": str(1090000100 + i), "telefono": str(3120000000 + i),
                                     "sexo": "F"}], fuente="cedulas")
        y, = insertar_personas(db, [{"nombre": nombre, "telefono": str(3120000000 + i), "sexo": "F"}], fuente="tramites")
        par(x, y, round(0.95 - i * 0.0005, 4))
    hace10 = (modelo.hoy_local() - timedelta(days=10)).isoformat()
    antes = lambda anios: modelo._restar_anios(modelo.hoy_local() - timedelta(days=10), anios).isoformat()  # noqa: E731
    vista = []
    for i, (clave, fila, de_a, de_b) in enumerate((
        ("misma_declarada", "edad", {"edad": 40, "edad_ref": hace10}, {"edad": 40, "edad_ref": antes(10)}),
        ("misma_de_hoy", "edad", {"edad": 40, "edad_ref": antes(6)}, {"edad": 46, "edad_ref": hace10}),
        ("mayusculas", "direccion", {"direccion": "CALLE 10 # 5-20"}, {"direccion": "Calle 10 # 5-20"}),
    )):
        nombre = f"EUFEMIA {'ABC'[i]} INVENTADA VISTA PREVIA"
        a, = insertar_personas(db, [{"nombre": nombre, "cedula": str(1095000100 + i), **de_a}], fuente="cedulas")
        b, = insertar_personas(db, [{"nombre": nombre, **de_b}], fuente="tramites")
        vista.append({"clave": clave, "fila": fila, "a": a, "b": b, "par": par(b, a, 0.9), "de_b": de_b})
    # Los de la tercera verificación: la A con una placa del casco (la mejor ubicada) y la B con el barrio elegido a
    # mano y una dirección que no se ubica; la A con 50 años declarados hace diez (hoy 60) y la B con fecha de
    # nacimiento y sin edad. Tampoco son «muy probables»
    from app import db as bd
    from app.pipeline.importar import georreferenciar
    central = db.lugares.find_one({"nombre": "CENTRAL"})["_id"]
    for i, (clave, fila, tambien, de_a, de_b) in enumerate((
        ("lugar_con_su_direccion", "lugar", "direccion", {"direccion": "CL 49 # 45-12 BARRIO PUEBLO NUEVO"},
         {"direccion": "CALLE 10 # 5-20", "lugar_id": central, "geo_manual": "lugar"}),
        ("edad_con_fecha", "edad", None, {"edad": 50, "edad_ref": antes(10)}, {"fecha_nacimiento": "1966-12-31"}),
    )):
        nombre = f"CASILDA {'AB'[i]} INVENTADA VISTA PREVIA"
        a, = insertar_personas(db, [{"nombre": nombre, "cedula": str(1095000200 + i), **de_a}], fuente="cedulas")
        b, = insertar_personas(db, [{"nombre": nombre, **de_b}], fuente="tramites")
        georreferenciar(db, [a, b])
        bd.recalcular_completitud(db, [a, b])
        vista.append({"clave": clave, "fila": fila, "tambien": tambien, "a": a, "b": b, "par": par(b, a, 0.9),
                      "de_a": de_a, "de_b": {k: v for k, v in de_b.items() if k != "lugar_id"}})
    db.coincidencias.insert_many(coinc)
    return {"vista": vista}


@contextmanager
def _panel_con_guion(tmp_path_factory, sembrar, conjunto: str):
    """El panel de verdad en un puerto libre, con lo que siembra `sembrar(db)`, y el guion de Chromium con los casos de
    `conjunto` («simulado» o «real»): ({caso: resultado}, la base, lo sembrado). Cada conjunto con su propia base."""
    if not MONGO:
        pytest.skip("No hay MongoDB para las pruebas con navegador")
    import servidor
    from app.config import Config
    cfg = Config(usuario="admin", clave="clave-de-prueba-larga", mongodb_uri=URI,
                 mongodb_db=f"prueba_{uuid.uuid4().hex[:10]}", horas_sesion=1, cookie_segura=False, max_subida_mb=5)
    tmp = tmp_path_factory.mktemp(f"unificacion_web_{conjunto}")
    sitio = tmp / "site"
    sitio.mkdir()
    (sitio / "index.html").write_text("<!doctype html><title>Inicio</title>INICIO", encoding="utf-8")
    app = servidor.crear_servidor(cfg, sitio)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    srv = uvicorn.Server(uvicorn.Config(app, http="h11", lifespan="on", log_level="warning", access_log=False,
                                        server_header=False, timeout_graceful_shutdown=2))
    hilo = threading.Thread(target=srv.run, kwargs={"sockets": [sock]}, daemon=True)
    hilo.start()
    try:
        fin = time.time() + 20
        while time.time() < fin and not (srv.started and app.state.panel is not None
                                         and getattr(app.state.panel.state, "listo", False)):
            time.sleep(0.05)
        assert srv.started and app.state.panel is not None, "el servidor no arrancó"
        db = app.state.panel.state.db
        datos = sembrar(db)
        (tmp / "datos.json").write_text(json.dumps(datos), encoding="utf-8")
        (tmp / "guion.cjs").write_text(GUION, encoding="utf-8")
        capturas = os.environ.get("CAPTURAS_UNIFICACION") or str(tmp)
        base = f"http://127.0.0.1:{sock.getsockname()[1]}/panel"
        r = subprocess.run(["node", str(tmp / "guion.cjs"), base, cfg.usuario, cfg.clave, str(tmp / "datos.json"), capturas,
                            conjunto], capture_output=True, text=True, timeout=900)
        assert r.returncode == 0, (r.stdout[-3000:], r.stderr[-3000:])
        salida = json.loads(r.stdout.strip().splitlines()[-1])
        if os.environ.get("CAPTURAS_UNIFICACION"):
            nombre = "resultado.json" if conjunto == "simulado" else f"resultado-{conjunto}.json"
            (Path(capturas) / nombre).write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
        yield {c["nombre"]: c for c in salida["casos"]}, db, datos
    finally:
        srv.should_exit = True
        hilo.join(15)
        sock.close()
        with pymongo.MongoClient(URI) as m:
            m.drop_database(cfg.mongodb_db)


@pytest.fixture(scope="module")
def resultados(tmp_path_factory):
    """Los casos con las rutas de la unión en lote contestadas desde el navegador: {caso: resultado}."""
    with _panel_con_guion(tmp_path_factory, _sembrar, "simulado") as (casos, _, _):
        yield casos


@pytest.fixture(scope="module")
def reales(tmp_path_factory):
    """Los casos con la unión de verdad: ({caso: resultado}, la base, lo sembrado), para mirar en la base lo que dejó."""
    with _panel_con_guion(tmp_path_factory, _sembrar_reales, "real") as r:
        yield r


def _revisar(resultados: dict, nombre: str) -> dict:
    caso = resultados[nombre]
    assert not caso.get("fallo"), (nombre, caso["fallo"])
    malas = {k: v for k, v in caso["revisiones"].items() if v is not True}
    assert caso["revisiones"] and not malas, (nombre, malas, caso.get("datos"))
    assert caso["errores"] == [], (nombre, caso["errores"])
    assert caso["csp"] == [], (nombre, caso["csp"])
    return caso


@requiere_navegador
def test_grupos_conteos_y_comparacion(resultados):
    _revisar(resultados, "render")


@requiere_navegador
def test_excluir_desbloquea_y_cambia_la_vista_previa(resultados):
    _revisar(resultados, "excluir")


@requiere_navegador
def test_seleccion_y_union_en_bloque(resultados):
    caso = _revisar(resultados, "seleccion")
    # El cuerpo exacto del POST: los pares de cada grupo, la decisión, la ficha conservada y la excluida
    assert caso["datos"]["post"] == {"grupos": [
        {"pares": [12], "decision": "unir", "conservar": 812},
        {"pares": [30, 31], "decision": "unir", "conservar": 2001, "excluir": [2002]},
    ]}


@requiere_navegador
def test_unir_las_muy_probables_con_progreso(resultados):
    caso = _revisar(resultados, "masivo")
    assert caso["datos"]["tandas"] == [50, 10]


@requiere_navegador
def test_detener_la_union_de_las_muy_probables(resultados):
    _revisar(resultados, "detener")


@requiere_navegador
def test_atajos_de_teclado(resultados):
    caso = _revisar(resultados, "atajos")
    assert caso["datos"]["posts"] == [
        {"grupos": [{"pares": [12], "decision": "separar"}]},
        {"grupos": [{"pares": [13], "decision": "unir", "conservar": 820}]},
    ]


@requiere_navegador
@pytest.mark.parametrize("pantalla", ["820x1180", "390x844", "320x568"])
def test_celular_y_tableta_sin_desborde(resultados, pantalla):
    _revisar(resultados, f"movil-{pantalla}")


@requiere_navegador
def test_modo_oscuro_y_contraste(resultados):
    _revisar(resultados, "oscuro")


@requiere_navegador
def test_insignias_de_la_ficha_el_directorio_y_el_enlace_revisar(resultados):
    _revisar(resultados, "ficha")


@requiere_navegador
def test_unir_las_muy_probables_respeta_lo_marcado_en_las_tarjetas(resultados):
    caso = _revisar(resultados, "marcas")
    # El grupo con la «No es la misma» que lo deja de una ficha no va; el de «Conservar esta» lleva su ficha y el de tres,
    # la excluida. Los demás, con la conservada por defecto (sin `conservar`)
    assert caso["datos"]["posts"] == [{"grupos": [
        {"pares": [7001], "decision": "unir", "conservar": 5003},
        {"pares": [7002], "decision": "unir"},
        {"pares": [7003], "decision": "unir"},
        {"pares": [7100, 7101], "decision": "unir", "conservar": 6001, "excluir": [6003]},
    ]}]


@requiere_navegador
def test_unir_las_muy_probables_con_el_filtro_de_una_ficha(resultados):
    caso = _revisar(resultados, "persona")
    assert caso["datos"]["posts"] == [{"grupos": [{"pares": [7002], "decision": "unir"}]}]


@requiere_navegador
def test_la_paginacion_tras_resolver_no_se_salta_grupos(resultados):
    _revisar(resultados, "paginacion")


@requiere_navegador
def test_la_paginacion_queda_quieta_mientras_se_resuelve(resultados):
    """«Siguiente» y «Anterior» se desactivan mientras se envía un grupo: el servidor ya puede haberlo unido (la
    respuesta espera a ubicar los destinos y a la auditoría) y armar la página siguiente con la lista corrida, así que
    el grupo que pasa a esta página no se veía nunca. Con la respuesta vuelven, y «Siguiente» completa esta misma
    página."""
    _revisar(resultados, "paginacion-en-curso")


@requiere_navegador
def test_la_vista_previa_estimada_sigue_la_mejor_ubicacion(resultados):
    _revisar(resultados, "lugar")


@requiere_navegador
def test_un_enlace_viejo_o_una_falla_dejan_una_salida(resultados):
    _revisar(resultados, "url")


@requiere_navegador
def test_atajos_fuera_de_la_vista_y_con_mayuscula(resultados):
    _revisar(resultados, "atajos-fuera")


@requiere_navegador
def test_nuevo_lugar_pregunta_antes_de_perder_lo_escrito(resultados):
    _revisar(resultados, "dialogos")


@requiere_navegador
def test_la_barra_de_seleccion_no_queda_bajo_la_franja_de_llamada(resultados):
    _revisar(resultados, "franja")


# ── Con la unión de verdad ──

# Lo que dice la celda «Quedaría» de cada par de `_sembrar_reales`: con la ficha A conservada (la vista previa del
# servidor), con la B (la que calcula el navegador) y los alternos de ese campo que la unión deja en la B. `pasan` es el
# `title` de «y N valores pasan a alternos» (None: no pasa ninguno)
VISTAS = {
    "misma_declarada": ({"valor": "40 años", "fuente": "cedulas", "de": "A", "pasan": None},
                        {"valor": "50 años", "fuente": "tramites", "de": "B", "pasan": None}, []),
    "misma_de_hoy": ({"valor": "46 años", "fuente": "cedulas", "de": "A", "pasan": "46 (Trámites, ficha B)"},
                     {"valor": "46 años", "fuente": "tramites", "de": "B", "pasan": "40 (Base con cédula, ficha A)"},
                     ["40"]),
    "mayusculas": ({"valor": "CALLE 10 # 5-20", "fuente": "cedulas", "de": "A", "pasan": "Calle 10 # 5-20 (Trámites, ficha B)"},
                   {"valor": "Calle 10 # 5-20", "fuente": "tramites", "de": "B",
                    "pasan": "CALLE 10 # 5-20 (Base con cédula, ficha A)"}, ["CALLE 10 # 5-20"]),
}


@requiere_navegador
def test_la_vista_previa_estimada_promete_lo_que_la_union_deja(reales):
    """Al conservar la ficha B, la tarjeta pasa a la vista previa que calcula el navegador. Compara como la unión (la edad
    declarada y no la llevada a hoy, el texto tal cual) y no contradice la del servidor: lo que dice que queda y lo que
    pasa a alternos es lo que «Es la misma persona» deja en la base. Antes, con 40 años declarados hace diez días (A) y
    40 declarados diez años antes (B, hoy 50), prometía que el 40 de la A pasaba a alternos y la unión no dejaba ninguno;
    con 40 de hace seis años y 46 de hoy (hoy los dos 46), al revés."""
    from app import modelo
    casos, db, datos = reales
    caso = _revisar(casos, "edad")
    for x in datos["vista"]:
        if x["clave"] not in VISTAS:
            continue
        servidor, estimada, alternos = VISTAS[x["clave"]]
        c = caso["datos"]["casos"][x["clave"]]
        assert {k: c["servidor"][k] for k in servidor} == servidor, (x["clave"], c["servidor"])
        assert {k: c["estimada"][k] for k in estimada} == estimada, (x["clave"], c["estimada"])
        assert c["post"] == {"grupos": [{"pares": [x["par"]], "decision": "unir", "conservar": x["b"]}]}
        unida = db.personas.find_one({"_id": x["b"]})
        assert [str(a["valor"]) for a in unida.get("alternos") or [] if a["campo"] == x["fila"]] == alternos, \
            (x["clave"], unida.get("alternos"))
        if x["fila"] == "edad":
            # La B se queda con su edad y su referencia: la de hoy es la que la tarjeta dijo que quedaba
            assert (unida["edad"], unida["edad_ref"]) == (x["de_b"]["edad"], x["de_b"]["edad_ref"])
            assert f"{modelo.edad_efectiva(unida)} años" == c["estimada"]["valor"]
        else:
            assert unida["direccion"] == c["estimada"]["valor"]


# Los pares de la tercera verificación: lo que dice la celda «Quedaría» es igual con la A conservada (la vista previa
# del servidor) y con la B (la del navegador), y es lo que la unión deja en la B
VISTAS_UNION = {
    "lugar_con_su_direccion": {
        "lugar": {"valor": "Pueblo Nuevo", "fuente": "cedulas", "de": "A", "pasan": None},
        "direccion": {"valor": "CL 49 # 45-12 BARRIO PUEBLO NUEVO", "fuente": "cedulas", "de": "A",
                      "pasan": "CALLE 10 # 5-20 (Trámites, ficha B)"}},
    "edad_con_fecha": {"edad": {"valor": "60 años", "fuente": "cedulas", "de": "A", "pasan": None}},
}


@requiere_navegador
def test_la_vista_previa_estimada_promete_la_ubicacion_y_la_edad_que_deja_la_union(reales):
    """Al conservar la B: (1) la A está mejor ubicada (una placa del casco) y la B tiene el barrio elegido a mano y una
    dirección que no se ubica. La ubicación de la A pasa en bloque con su dirección (la de la B, a alternos): antes la
    vista previa prometía el barrio de la A con la dirección de la B, y la unión volvía a ubicar esa dirección y dejaba
    la ficha sin barrio ni punto. (2) La B tiene fecha de nacimiento y no edad; la A declaró 50 años hace diez: la
    vista previa dice 60 y la unión deja esa edad con su referencia (antes, como declarada hoy: 50)."""
    from app import unificacion as un
    casos, db, datos = reales
    caso = _revisar(casos, "edad")
    lugares = un.nombres_de_lugares(db)
    nuevos = [x for x in datos["vista"] if x["clave"] in VISTAS_UNION]
    assert len(nuevos) == len(VISTAS_UNION)
    for x in nuevos:
        c = caso["datos"]["casos"][x["clave"]]
        for fila, espera in VISTAS_UNION[x["clave"]].items():
            for cual in ("servidor", "estimada"):
                celda = c[cual] if fila == x["fila"] else c[f"{cual}_tambien"]
                assert {k: celda[k] for k in espera} == espera, (x["clave"], fila, cual, celda)
        assert c["post"] == {"grupos": [{"pares": [x["par"]], "decision": "unir", "conservar": x["b"]}]}
        unida = db.personas.find_one({"_id": x["b"]})
        if x["fila"] == "lugar":
            assert unida["direccion"] == x["de_a"]["direccion"]
            assert un._lugar(unida, lugares).title() == VISTAS_UNION[x["clave"]]["lugar"]["valor"]
            assert (unida["geo_precision"], unida["geo_manual"]) == ("direccion", False) and unida["lat"] is not None
            alternos = [a["valor"] for a in unida.get("alternos") or [] if a["campo"] == "direccion"]
            assert alternos == [x["de_b"]["direccion"]]
        else:
            assert (unida["edad"], unida["edad_ref"]) == (x["de_a"]["edad"], x["de_a"]["edad_ref"])
            assert f"{un._edad(unida)} años" == VISTAS_UNION[x["clave"]]["edad"]["valor"]


@requiere_navegador
def test_atajos_con_el_asistente_abierto_tras_recargar_o_navegar(reales):
    """Con el asistente abierto los atajos no corren, aunque un clic en un texto suyo deje el foco en <body> y él recargue
    la vista o lleve a ella (la vista se crea de nuevo con el foco en #vista): «ju» no une nada."""
    _revisar(reales[0], "atajos-recarga")


@requiere_navegador
def test_la_paginacion_tras_resolver_dice_lo_mismo_que_siguiente(reales):
    """Con 26 grupos muy probables, resolver el primero deja 25 en la cuenta y uno sin ver: «Página 1 de 2» con
    «Siguiente», que completa la página (y la paginación se va). Antes decía «Página 1 de 1» con «Siguiente» activo."""
    _revisar(reales[0], "pagina26")


GUION = r"""// Revisión en bloque de coincidencias y color por fuente, en Chromium. Uso: node <guion> <base del panel> <usuario>
// <clave> <datos.json> <capturas> [simulado|real] (los casos con las rutas de la unión contestadas aquí, o con la de verdad)
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const fs = require('fs');
const path = require('path');
const [base, usuario, clave, rutaDatos, capturas, conjunto = 'simulado'] = process.argv.slice(2);
const D = JSON.parse(fs.readFileSync(rutaDatos, 'utf8'));
const origen = new URL(base).origin;
const pref = new URL(base).pathname.replace(/\/+$/, '');
const espera = { timeout: 20000 };
const dormir = (ms) => new Promise((ok) => setTimeout(ok, ms));
const captura = (page, nombre, op = {}) => (capturas ? page.screenshot({ path: path.join(capturas, `${nombre}.png`), ...op }) : null);

// ── Grupos inventados con la forma exacta del contrato (A.2) ──
function miembro(id, nombre, extra = {}) {
  // La edad de la vista previa como la manda `unificacion.miembro`: aquí la declarada es la de hoy (sin fecha de nacimiento)
  const edad = extra.edad ?? null;
  return { id, nombre, cedula: null, telefonos: [], correo: null, direccion: null, lugar: null, edad: null, sexo: null,
    fecha_nacimiento: null, fuentes: ['tramites'], procedencia: {}, tramites: 1, listas: '', completitud: 40, consentimiento: 'pendiente',
    rango_ubicacion: 0, edad_declarada: edad == null ? null : String(edad), edad_declarada_hoy: edad, ...extra };
}
const par = (id, a, b, puntaje, motivo, nivel, a_favor = [], en_contra = [], nota = null) => ({ id, a, b, puntaje, motivo, nivel, nota,
  a_favor: a_favor.map(([clave, texto]) => ({ clave, texto })), en_contra: en_contra.map(([clave, texto]) => ({ clave, texto })) });
const ETIQUETAS = { nombre: 'Nombre', cedula: 'Cédula', telefonos: 'Teléfonos', correo: 'Correo', direccion: 'Dirección', lugar: 'Lugar',
  sexo: 'Sexo', edad: 'Edad', fecha_nacimiento: 'Fecha de nacimiento' };
// La vista previa como la arma el servidor: el valor del destino o el primero que haya; lo distinto, a «otros»
function vistaPrevia(miembros, destino) {
  const orden = [miembros.find((m) => m.id === destino), ...miembros.filter((m) => m.id !== destino)];
  const fuente = (m, c) => m.procedencia[c] || m.fuentes[0];
  // La ubicación pasa en bloque, con su dirección, de la mejor ubicada (`unificacion.ubicacion_unida`: el rango y, a igual
  // rango, tener dirección, frente a lo que la conservada ya tiene); la dirección que estaba pasa a alternos
  const llave = (m, dir) => 2 * (m.rango_ubicacion ?? 0) + (dir ? 1 : 0);
  let geo = orden[0];
  let dir = orden[0].direccion ? orden[0] : null;
  const pasan = [];
  for (const m of orden.slice(1)) {
    const pasa = llave(m, m.direccion) > llave(geo, dir?.direccion);
    if (pasa) geo = m;
    if (!m.direccion) continue;
    if (!dir || pasa) { if (dir && dir.direccion !== m.direccion) pasan.push(dir); dir = m; } else if (m.direccion !== dir.direccion) pasan.push(m);
  }
  return Object.keys(ETIQUETAS).map((campo) => {
    if (campo === 'telefonos') {
      const nums = [...new Set(orden.flatMap((m) => m.telefonos))];
      return { campo, etiqueta: ETIQUETAS[campo], valor: nums.length ? nums.join(', ') : null, fuente: null, de: destino, otros: [] };
    }
    if (campo === 'lugar') {
      return geo.lugar ? { campo, etiqueta: ETIQUETAS[campo], valor: geo.lugar, fuente: fuente(geo, campo), de: geo.id, otros: [] }
        : { campo, etiqueta: ETIQUETAS[campo], valor: null, fuente: null, de: null, otros: [] };
    }
    if (campo === 'direccion') {
      const vistos = new Set([dir?.direccion]);
      const otros = [];
      for (const m of pasan) if (!vistos.has(m.direccion)) { vistos.add(m.direccion); otros.push({ valor: m.direccion, fuente: fuente(m, campo), de: m.id }); }
      return dir ? { campo, etiqueta: ETIQUETAS[campo], valor: dir.direccion, fuente: fuente(dir, campo), de: dir.id, otros }
        : { campo, etiqueta: ETIQUETAS[campo], valor: null, fuente: null, de: null, otros: [] };
    }
    const con = orden.filter((m) => m[campo] != null && m[campo] !== '');
    if (!con.length) return { campo, etiqueta: ETIQUETAS[campo], valor: null, fuente: null, de: null, otros: [] };
    // Solo los campos con procedencia dejan alterno al unir (el nombre, la cédula y el lugar no)
    const otros = !['correo', 'direccion', 'sexo', 'edad', 'fecha_nacimiento'].includes(campo) ? [] : con.slice(1).filter((m) => String(m[campo]) !== String(con[0][campo]))
      .map((m) => ({ valor: String(m[campo]), fuente: fuente(m, campo), de: m.id }));
    return { campo, etiqueta: ETIQUETAS[campo], valor: String(con[0][campo]), fuente: fuente(con[0], campo), de: con[0].id, otros };
  });
}
function grupo({ nivel, puntaje, miembros, pares, avisos = [], destino }) {
  const clave = pares.map((p) => p.id).sort((a, b) => a - b).join('-');
  return { clave, nivel, puntaje, destino, motivos: [...new Set(pares.map((p) => p.motivo))], avisos, miembros, pares,
    vista_previa: vistaPrevia(miembros, destino) };
}
function gruposBase() {
  const g1 = grupo({ nivel: 'alta', puntaje: 0.94, destino: 812, miembros: [
    miembro(812, 'MARIA ELENA PEREZ GOMEZ', { cedula: '1098765432', telefonos: ['3001234567'], edad: 41, sexo: 'F', lugar: 'LA CONDOR',
      fuentes: ['cedulas', 'tramites'], procedencia: { cedula: 'cedulas', sexo: 'cedulas', edad: 'cedulas' }, completitud: 70, tramites: 0 }),
    miembro(940, 'MARIA PEREZ GOMEZ', { telefonos: ['3001234567', '3157654321'], correo: 'maria@example.com', edad: 40, sexo: 'F',
      direccion: 'VEREDA LA CONDOR', lugar: 'LA CONDOR', procedencia: { correo: 'tramites', direccion: 'tramites' }, completitud: 35, tramites: 2 }),
  ], pares: [par(12, 812, 940, 0.94, 'cruce_cedula', 'alta', [['mismo_telefono', 'Mismo teléfono'], ['edad_parecida', 'Edad parecida'],
    ['fuentes_complementarias', 'Fuentes complementarias']])] });
  const g4 = grupo({ nivel: 'alta', puntaje: 0.9, destino: 820, miembros: [
    miembro(820, 'PEDRO ANTONIO SUAREZ', { telefonos: ['3109998877'], fuentes: ['planilla'], procedencia: {}, completitud: 55, sexo: 'M' }),
    miembro(821, 'PEDRO SUAREZ', { telefonos: ['3109998877'], fuentes: ['tramites'], sexo: 'M' }),
  ], pares: [par(13, 820, 821, 0.9, 'nombre_telefono', 'alta', [['mismo_telefono', 'Mismo teléfono']])] });
  const g2 = grupo({ nivel: 'baja', puntaje: null, destino: 1001, avisos: ['Tiene señales en contra: revise la edad y el sexo.'], miembros: [
    miembro(1001, 'JOSE LUIS RAMIREZ', { sexo: 'M', edad: 30, fuentes: ['planilla'], completitud: 50 }),
    miembro(1002, 'JOSE LUIS RAMIREZ', { sexo: 'M', edad: 52, fuentes: ['tramites'] }),
    miembro(1003, 'LUISA RAMIREZ', { sexo: 'F', fuentes: ['reunion', 'manual'], consentimiento: 'no' }),
  ], pares: [par(20, 1001, 1002, null, 'reporte', 'baja', [['nombre_igual', 'Nombre igual']], [['edad_distinta', 'Edad distinta']], 'Parecen hermanos'),
    par(21, 1002, 1003, 0.72, 'variante', 'baja', [], [['sexo_distinto', 'Sexo distinto'], ['nombre_pila_distinto', 'Otro nombre de pila']])] });
  const g3 = grupo({ nivel: 'bloqueada', puntaje: 0.88, destino: 2001, avisos: ['Tiene dos cédulas distintas: no se puede unir entero.'], miembros: [
    miembro(2001, 'ANA MARIA TORRES', { cedula: '52111222', fuentes: ['cedulas'], procedencia: { cedula: 'cedulas' }, telefonos: ['3201112233'], completitud: 60 }),
    miembro(2002, 'ANA TORRES', { cedula: '52999888', fuentes: ['cedulas'], procedencia: { cedula: 'cedulas' }, completitud: 58 }),
    miembro(2003, 'ANA MARIA TORRES RUIZ', { telefonos: ['3201112233'], fuentes: ['tramites'] }),
  ], pares: [par(30, 2001, 2003, 0.88, 'cruce_cedula', 'alta', [['mismo_telefono', 'Mismo teléfono']]),
    par(31, 2002, 2003, 0.8, 'cruce_cedula', 'media', [['palabras', '2 palabras en común']])] });
  return [g1, g4, g2, g3];
}
function muchosAlta(n) {
  return Array.from({ length: n }, (_, i) => grupo({ nivel: 'alta', puntaje: 0.99 - i * 0.001, destino: 5000 + 2 * i, miembros: [
    miembro(5000 + 2 * i, `PERSONA ALTA ${i} INVENTADA`, { telefonos: [`300${String(1000000 + i)}`], fuentes: ['cedulas'], cedula: String(80000000 + i) }),
    miembro(5001 + 2 * i, `PERSONA ALTA ${i} INVENTADA COPIA`, { telefonos: [`300${String(1000000 + i)}`] }),
  ], pares: [par(7000 + i, 5000 + 2 * i, 5001 + 2 * i, 0.99 - i * 0.001, 'cruce_cedula', 'alta', [['mismo_telefono', 'Mismo teléfono']])] }));
}

// ── El «servidor» de las dos rutas: lleva el estado de los grupos pendientes, filtra, cuenta y pagina como A.2 ──
const ORDEN_NIVEL = { alta: 0, media: 1, baja: 2, bloqueada: 3 };
const MOTIVOS = ['cruce_cedula', 'nombre_telefono', 'homonimo', 'variante', 'reporte', 'alta_simultanea'];
async function servirGrupos(ctx, grupos, { fallar = {}, demora = 0 } = {}) {
  // `fallarGet`: cuántas lecturas siguientes contestan 500 (la red o el servidor caídos). `retener`: una promesa que la
  // respuesta del lote espera después de resolver (el servidor ya unió y la respuesta todavía no llega)
  const reg = { grupos: grupos.slice(), gets: [], posts: [], resueltos: new Set(), fallarGet: 0, retener: null };
  const json = (d, status = 200) => ({ status, contentType: 'application/json', body: JSON.stringify(d) });
  await ctx.route((u) => u.pathname === pref + '/api/coincidencias/grupos' || u.pathname === pref + '/api/coincidencias/lote', async (route) => {
    const req = route.request();
    const u = new URL(req.url());
    try {
      if (u.pathname.endsWith('/grupos')) {
        const q = Object.fromEntries(u.searchParams);
        reg.gets.push(q);
        if (reg.fallarGet > 0) { reg.fallarGet--; return await route.fulfill(json({ detail: 'Falla inventada del servidor' }, 500)); }
        // Como la API real: 422 con un motivo desconocido o una página de más
        if (q.motivo && !MOTIVOS.includes(q.motivo)) return await route.fulfill(json({ detail: `Motivo desconocido: use ${MOTIVOS.join(', ')}` }, 422));
        if (Number(q.pagina || 1) > 100000) return await route.fulfill(json({ detail: 'pagina: Input should be less than or equal to 100000' }, 422));
        let vivos = reg.grupos.filter((g) => !reg.resueltos.has(g.clave));
        if (q.persona) vivos = vivos.filter((g) => g.miembros.some((m) => String(m.id) === q.persona));
        const conMotivo = vivos.filter((g) => !q.motivo || g.motivos.includes(q.motivo));
        const conNivel = vivos.filter((g) => !q.nivel || g.nivel === q.nivel);
        const niveles = { alta: 0, media: 0, baja: 0, bloqueada: 0 };
        for (const g of conMotivo) niveles[g.nivel]++;
        const motivos = { cruce_cedula: 0, nombre_telefono: 0, homonimo: 0, variante: 0, reporte: 0, alta_simultanea: 0 };
        for (const g of conNivel) for (const m of g.motivos) motivos[m]++;
        const todos = conMotivo.filter((g) => !q.nivel || g.nivel === q.nivel)
          .sort((a, b) => ORDEN_NIVEL[a.nivel] - ORDEN_NIVEL[b.nivel] || (b.puntaje ?? -1) - (a.puntaje ?? -1) || a.clave.localeCompare(b.clave));
        const pagina = Number(q.pagina || 1), por = Math.min(100, Number(q.por_pagina || 25));
        return await route.fulfill(json({ total: todos.length, pares: todos.reduce((a, g) => a + g.pares.length, 0),
          personas: todos.reduce((a, g) => a + g.miembros.length, 0), niveles, motivos, pagina, por_pagina: por,
          grupos: todos.slice((pagina - 1) * por, pagina * por) }));
      }
      const cuerpo = req.postDataJSON();
      reg.posts.push(cuerpo);
      if (demora) await dormir(demora);
      const resultados = cuerpo.grupos.map((x) => {
        const clave = x.pares.slice().sort((a, b) => a - b).join('-');
        const g = reg.grupos.find((y) => y.clave === clave && !reg.resueltos.has(y.clave));
        if (!g) return { ok: false, decision: x.decision, codigo: 'cambio', error: 'El grupo cambió: recargue' };
        if (fallar[clave]) return { ok: false, decision: x.decision, ...fallar[clave] };
        reg.resueltos.add(clave);
        const fuera = (x.excluir || []).length;
        return x.decision === 'unir'
          ? { ok: true, decision: 'unir', conservada: x.conservar ?? g.destino, unidas: g.miembros.length - fuera - 1, separadas: fuera }
          : { ok: true, decision: 'separar', conservada: null, unidas: 0, separadas: g.pares.length };
      });
      const ok = resultados.filter((r) => r.ok);
      if (reg.retener) await reg.retener;
      return await route.fulfill(json({ resultados, unidas: ok.reduce((a, r) => a + r.unidas, 0),
        separadas: ok.reduce((a, r) => a + r.separadas, 0), errores: resultados.length - ok.length }));
    } catch { /* la página se cerró */ }
  });
  return reg;
}

// ── Contexto, ingreso y ayudas ──
async function abrir(nav, caso, op = {}) {
  const ctx = await nav.newContext({ viewport: { width: 1400, height: 900 }, ...op });
  await ctx.route((u) => u.origin !== origen, (r) => r.abort()); // aquí no hay internet (las letras de Google)
  await ctx.exposeBinding('__csp', (_, v) => caso.csp.push(v));
  await ctx.addInitScript(() => {
    addEventListener('securitypolicyviolation', (e) => window.__csp(`${e.effectiveDirective} ${e.blockedURI}`), true);
    window.__vistas = [];
    addEventListener('vista', (e) => window.__vistas.push(e.detail.ruta));
  });
  const page = await ctx.newPage();
  page.on('pageerror', (e) => caso.errores.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) caso.errores.push(m.text().slice(0, 300)); });
  const insignias = { n: 0 };
  page.on('request', (r) => { if (new URL(r.url()).pathname === pref + '/api/insignias') insignias.n++; });
  return { ctx, page, v: caso.revisiones, d: caso.datos, insignias };
}
async function ingresar(page, ruta) {
  await page.goto(base + '/', { waitUntil: 'domcontentloaded' });
  await page.fill('#f-login [name=usuario]', usuario);
  await page.fill('#f-login [name=clave]', clave);
  await page.click('#f-login button[type=submit]');
  await page.waitForSelector('#app #vista > .vista', espera);
  if (ruta) await ir(page, ruta);
}
async function ir(page, ruta) {
  const n = await page.evaluate(() => window.__vistas.length);
  await page.evaluate(async (r) => (await import(new URL('app.js', document.querySelector('script[type=module]').src).href)).ir(r), ruta);
  await page.waitForFunction((n) => window.__vistas.length > n, n, espera);
}
async function abrirCoincidencias(page, q = '') {
  await ingresar(page, `/calidad?p=coincidencias${q}`);
  await page.waitForSelector('.unificacion', espera);
}
const tarjetas = (page) => page.$$eval('.grupo-coinc:not(.resuelta)', (ts) => ts.map((t) => t.dataset.clave));
// Sin desborde: ni la página más ancha que la pantalla, ni la pantalla ensanchada (el celular agranda `innerWidth` hasta lo que
// desborda, también lo absoluto que se escapa de un contenedor con desplazamiento)
const sinDesborde = (page) => page.evaluate((w) => innerWidth <= w && document.documentElement.scrollWidth <= w + 1 && document.body.scrollWidth <= w + 1,
  page.viewportSize().width);
async function confirmarDialogo(page) {
  await page.waitForSelector('dialog[open] [data-si]', espera);
  const texto = await page.$eval('dialog[open] .cuerpo', (x) => x.textContent.trim());
  await page.click('dialog[open] [data-si]');
  return texto;
}
// Contraste de cada elemento con su fondo real (los fondos semitransparentes se componen hasta uno opaco)
const CONTRASTES = (sel) => [...document.querySelectorAll(sel)].map((el) => {
  const parse = (s) => {
    let m = /rgba?\(([^)]+)\)/.exec(s);
    if (m) { const p = m[1].split(/[\s,/]+/).filter(Boolean).map(Number); return [p[0] / 255, p[1] / 255, p[2] / 255, p[3] ?? 1]; }
    m = /color\(srgb ([^)]+)\)/.exec(s);
    if (m) { const p = m[1].split(/[\s/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p[3] ?? 1]; }
    return null;
  };
  const capas = [];
  for (let x = el; x; x = x.parentElement) {
    const c = parse(getComputedStyle(x).backgroundColor);
    if (c && c[3] > 0) { capas.push(c); if (c[3] >= 0.999) break; }
  }
  let fondo = [1, 1, 1];
  for (const c of capas.reverse()) fondo = fondo.map((v, i) => c[i] * c[3] + v * (1 - c[3]));
  const t = parse(getComputedStyle(el).color);
  const lin = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  const L = (c) => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]);
  const [a, b] = [L(t), L(fondo)].sort((x, y) => y - x);
  return { k: el.dataset.fuente || el.className, cr: Math.round(((a + 0.05) / (b + 0.05)) * 100) / 100 };
});

// ── render: grupos, conteos, comparación, insignias y vista previa (escritorio, claro) ──
async function cRender(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso);
  const reg = await servirGrupos(ctx, gruposBase());
  await abrirCoincidencias(page);
  d.get = reg.gets[0];
  v.pide_la_primera_pagina = reg.gets[0].pagina === '1' && reg.gets[0].por_pagina === '25' && !reg.gets[0].nivel;
  const r = await page.evaluate(() => {
    const chip = (k) => document.querySelector(`[data-nivel-filtro="${k}"]`);
    const t = (s, raiz = document) => raiz.querySelector(s)?.textContent.replace(/\s+/g, ' ').trim() ?? null;
    const g = (clave) => document.querySelector(`.grupo-coinc[data-clave="${clave}"]`);
    const pieza = (el) => (el ? { texto: [...el.childNodes].filter((n) => n.nodeType === 3 || n.matches?.('.igual, .igual-dato, .choca')).map((n) => n.textContent).join('').trim(),
      fuente: el.querySelector(':scope > .fuente')?.dataset.fuente ?? null, de: el.querySelector('.de-ficha')?.textContent.replace('de la ficha ', '') ?? null } : null);
    const piezas = (s, raiz) => [...raiz.querySelectorAll(s)].map(pieza);
    const g1 = g('12'), g2 = g('20-21'), g3 = g('30-31');
    return {
      chips: ['', 'alta', 'media', 'baja', 'bloqueada'].map((k) => t('b', chip(k))),
      textos: ['alta', 'media', 'baja', 'bloqueada'].map((k) => chip(k).textContent.replace(/\s+/g, ' ').trim()),
      presionado: ['', 'alta'].map((k) => chip(k).getAttribute('aria-pressed')),
      boton: t('[data-unir-alta]'), cuenta: t('#cuenta-grupos'),
      claves: [...document.querySelectorAll('.grupo-coinc')].map((x) => x.dataset.clave),
      nivel1: t('.chip.nivel', g1), puntaje1: t('.puntaje-grupo', g1), puntaje2: t('.puntaje-grupo', g2),
      motivo1: t('.motivos-grupo', g1), senales1: [...g1.querySelectorAll('.senal.a-favor')].map((x) => x.textContent.trim()),
      contra2: [...g2.querySelectorAll('.senal.en-contra')].map((x) => x.textContent.trim()), pares2: g2.querySelectorAll('.senales-pares li').length,
      nota2: t('.nota-par', g2), avisos3: t('.avisos-grupo', g3),
      columnas1: g1.querySelectorAll('.comparar thead tr:first-child > *').length,
      columnas2: g2.querySelectorAll('.comparar thead tr:first-child > *').length,
      filas: [...g1.querySelectorAll('.comparar tbody th')].map((x) => x.textContent.trim()),
      cabeza1: [...g1.querySelectorAll('.ficha-col')].map((x) => [x.querySelector('.letra-ficha').textContent, x.querySelector('a').textContent]),
      enlace1: g1.querySelector('.ficha-col a')?.getAttribute('href'),
      insigniaCedula: g1.querySelector('tr[data-fila="cedula"] td .fuente')?.getAttribute('aria-label'),
      fuentesFicha: [...g1.querySelectorAll('tr[data-fila="fuentes"] td:not(.quedaria) .fuentes')].map((x) => [...x.querySelectorAll('.fuente')].map((f) => f.dataset.fuente)),
      fuentesQuedaria: [...g1.querySelectorAll('tr[data-fila="fuentes"] td.quedaria .fuente')].map((f) => f.dataset.fuente),
      telIgual: [...g1.querySelectorAll('tr[data-fila="telefonos"] .igual-dato')].map((x) => x.textContent.trim()),
      palabrasIguales: [...g1.querySelectorAll('tr[data-fila="nombre"] .igual')].map((x) => x.textContent),
      falta: t('tr[data-fila="cedula"] td:nth-of-type(2)', g1),
      quedaCedula: pieza(g1.querySelector('tr[data-fila="cedula"] td.quedaria .pieza')), quedaCorreo: pieza(g1.querySelector('tr[data-fila="correo"] td.quedaria .pieza')),
      quedaTel: pieza(g1.querySelector('tr[data-fila="telefonos"] td.quedaria .pieza')), quedaCabeza: t('thead .quedaria', g1),
      pasan: t('tr[data-fila="edad"] td.quedaria .pasan', g1), pasanTitulo: g1.querySelector('tr[data-fila="edad"] td.quedaria .pasan')?.title,
      conservar: [...g1.querySelectorAll('[data-conservar]')].map((x) => [x.value, x.checked]),
      choca: piezas('tr[data-fila="cedula"] .pieza:has(> .choca)', g3),
      chocaEdad: piezas('tr[data-fila="edad"] .pieza:has(> .choca)', g2), igualSexo: piezas('tr[data-fila="edad"] .pieza:has(> .igual-dato)', g2),
      cedulaB: pieza(g1.querySelector('tr[data-fila="cedula"] td .pieza')),
      noAutorizo: !!g2.querySelector('.ficha-col .no-autorizo'),
      bloqueo3: t('.bloqueo', g3), unir3: g3.querySelector('[data-unir]').disabled, separar3: g3.querySelector('[data-separar]').disabled,
      unir1: g1.querySelector('[data-unir]').disabled,
      atajos: [g1.querySelector('[data-unir]').getAttribute('aria-keyshortcuts'), g1.querySelector('[data-separar]').getAttribute('aria-keyshortcuts'),
        g1.querySelector('[data-sel]').getAttribute('aria-keyshortcuts'), g1.getAttribute('aria-keyshortcuts')],
      ayuda: getComputedStyle(document.querySelector('#ayuda-atajos')).display !== 'none',
      leyenda: t('.unificacion .leyenda-fuentes summary'),
      leyendaClaves: [...document.querySelectorAll('.unificacion .leyenda-fuentes li')].map((x) => x.dataset.fuente),
      barra: t('#cuenta-sel'), barraPosicion: getComputedStyle(document.querySelector('#barra-sel')).position,
      selTodos: !document.querySelector('[data-sel-todos]').hidden, selUnir: document.querySelector('[data-sel-unir]').hidden,
    };
  });
  d.r = r;
  v.chips_con_conteos = JSON.stringify(r.chips) === JSON.stringify(['4', '2', '0', '1', '1']);
  v.rotulos_de_nivel = r.textos.join('|') === 'Muy probables 2|Probables 0|Dudosas 1|Bloqueadas 1';
  v.todos_presionado = r.presionado[0] === 'true' && r.presionado[1] === 'false';
  v.boton_unir_alta = r.boton === 'Unir las 2 muy probables';
  v.cuenta = r.cuenta.startsWith('4 grupos con 6 coincidencias entre 10 fichas.');
  v.orden_del_servidor = r.claves.join(',') === '12,13,20-21,30-31';
  v.nivel_y_puntaje = r.nivel1 === 'Muy probable' && r.puntaje1 === '94 %' && r.puntaje2 === '—';
  v.motivo = r.motivo1 === 'Cruce con la base con cédula';
  v.senales_a_favor = r.senales1.join('|') === 'A favor: Mismo teléfono|A favor: Edad parecida|A favor: Fuentes complementarias';
  v.senales_por_par = r.pares2 === 2 && r.contra2.includes('En contra: Sexo distinto') && r.nota2 === 'Parecen hermanos';
  v.avisos = r.avisos3 === 'Tiene dos cédulas distintas: no se puede unir entero.';
  v.columnas = r.columnas1 === 4 && r.columnas2 === 5; // rótulos + fichas + «Quedaría»
  v.filas = r.filas.join('|') === 'Nombre|Cédula|Teléfonos|Correo|Dirección|Barrio o vereda|Edad y sexo|Fuentes|Trámites|Completitud';
  v.cabeza_con_letra_y_nombre = JSON.stringify(r.cabeza1) === JSON.stringify([['A', 'Ficha A: MARIA ELENA PEREZ GOMEZ'], ['B', 'Ficha B: MARIA PEREZ GOMEZ']]);
  v.enlace_a_la_ficha = r.enlace1 === `${pref}/personas/812`;
  v.insignia_por_dato = r.insigniaCedula === 'Fuente: Base con cédula';
  v.fuentes_por_ficha = JSON.stringify(r.fuentesFicha) === JSON.stringify([['cedulas', 'tramites'], ['tramites']]) && r.fuentesQuedaria.join() === 'cedulas,tramites';
  v.iguales_resaltados = r.telIgual.join() === '3001234567,3001234567' && r.palabrasIguales.join(' ') === 'MARIA PEREZ GOMEZ MARIA PEREZ GOMEZ';
  v.falta_con_raya = r.falta === '—';
  v.quedaria = JSON.stringify([r.quedaCedula, r.quedaCorreo, r.quedaTel]) === JSON.stringify([
    { texto: '1098765432', fuente: 'cedulas', de: 'A' }, { texto: 'maria@example.com', fuente: 'tramites', de: 'B' },
    { texto: '3001234567, 3157654321', fuente: null, de: 'A' }]) && r.quedaCabeza === 'Quedaría Se conserva la ficha A';
  v.cedula_con_su_fuente = JSON.stringify(r.cedulaB) === JSON.stringify({ texto: '1098765432', fuente: 'cedulas', de: null });
  v.pasan_a_alternos = r.pasan === 'y 1 valor pasa a alternos' && /^40 \(Trámites, ficha B\)$/.test(r.pasanTitulo || '');
  v.conservar_preelegida = JSON.stringify(r.conservar) === JSON.stringify([['812', true], ['940', false]]);
  v.choques = JSON.stringify(r.choca) === JSON.stringify([{ texto: '52111222', fuente: 'cedulas', de: null }, { texto: '52999888', fuente: 'cedulas', de: null }])
    && JSON.stringify(r.chocaEdad.map((x) => [x.texto, x.fuente])) === JSON.stringify([['30 años', 'planilla'], ['52 años', 'tramites'], ['Mujer', 'reunion']])
    && JSON.stringify(r.igualSexo.map((x) => x.texto)) === JSON.stringify(['Hombre', 'Hombre']);
  v.no_autorizo = r.noAutorizo;
  v.bloqueada_sin_unir = r.unir3 === true && r.separar3 === false && r.bloqueo3?.startsWith('Tienen cédulas distintas');
  v.alta_se_puede_unir = r.unir1 === false;
  v.atajos_anunciados = r.atajos.join('|') === 'U|D|X|J K' && r.ayuda;
  v.leyenda = r.leyenda === '¿Qué significan los colores?' && !r.leyendaClaves.includes('otra_base') && r.leyendaClaves.includes('cedulas');
  v.barra_pegada_arriba = r.barraPosicion === 'sticky' && r.barra === 'Seleccione grupos para resolverlos juntos' && r.selTodos && r.selUnir;
  v.sin_desborde = await sinDesborde(page);
  // Contraste de las insignias, los niveles y las señales en el tema claro (sobre su fondo real)
  await page.click('.unificacion .leyenda-fuentes summary');
  const cr = await page.evaluate(CONTRASTES, '.unificacion .fuente, .unificacion .chip.nivel, .unificacion .senal');
  d.contraste = cr.filter((x) => x.cr < 4.5);
  v.contraste_claro = cr.length > 20 && !d.contraste.length;
  // Filtro por nivel: pide `nivel` y marca el chip
  await page.click('[data-nivel-filtro="baja"]');
  await page.waitForFunction(() => document.querySelector('[data-nivel-filtro="baja"]')?.getAttribute('aria-pressed') === 'true', null, espera);
  v.filtra_por_nivel = reg.gets.at(-1).nivel === 'baja' && (await tarjetas(page)).join() === '20-21'
    && (await page.evaluate(() => location.search)).includes('nivel=baja');
  await page.selectOption('[data-motivo]', 'reporte');
  await page.waitForFunction(() => new URLSearchParams(location.search).get('motivo') === 'reporte', null, espera);
  await page.waitForSelector('.grupo-coinc', espera);
  v.filtra_por_motivo = reg.gets.at(-1).motivo === 'reporte' && reg.gets.at(-1).nivel === 'baja';
  await page.click('[data-nivel-filtro=""]');
  await page.waitForFunction(() => document.querySelector('[data-nivel-filtro=""]')?.getAttribute('aria-pressed') === 'true', null, espera);
  await page.selectOption('[data-motivo]', '');
  await page.waitForFunction(() => document.querySelectorAll('.grupo-coinc').length === 4, null, espera);
  await page.mouse.move(0, 0);
  await captura(page, 'escritorio-claro', { fullPage: true });
  await ctx.close();
}

// ── excluir: «No es la misma» desbloquea, rehace la vista previa y respeta la conexión entre fichas ──
async function cExcluir(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso);
  await servirGrupos(ctx, gruposBase());
  await abrirCoincidencias(page);
  const g3 = '.grupo-coinc[data-clave="30-31"]';
  const estado = () => page.evaluate((s) => {
    const g = document.querySelector(s);
    return { unir: g.querySelector('[data-unir]').disabled, bloqueo: g.querySelector('.bloqueo')?.textContent.trim() ?? null,
      cabeza: g.querySelector('thead .quedaria').textContent.replace(/\s+/g, ' ').trim(),
      conservar: [...g.querySelectorAll('[data-conservar]')].filter((x) => x.checked).map((x) => x.value),
      cedulas: g.querySelectorAll('tr[data-fila="cedula"] .choca').length, foco: document.activeElement?.matches?.('[data-excluir][value="2002"]') };
  }, g3);
  // Sin la de la cédula que sobra: quedan dos fichas conectadas por un par y una sola cédula
  await page.check(`${g3} [data-excluir][value="2002"]`);
  const a = await estado();
  d.excluida = a;
  v.excluir_desbloquea = a.unir === false && a.bloqueo === null && a.cedulas === 0;
  v.vista_previa_estimada = a.cabeza === 'Quedaría Se conserva la ficha A · estimado con su elección';
  v.foco_vuelve_al_control = a.foco === true;
  // Sin la del medio, las dos que quedan no tienen un par directo (y además tienen cédulas distintas)
  await page.uncheck(`${g3} [data-excluir][value="2002"]`);
  await page.check(`${g3} [data-excluir][value="2003"]`);
  const b = await estado();
  d.sin_puente = b;
  v.cedulas_distintas_otra_vez = b.unir === true && b.bloqueo?.startsWith('Tienen cédulas distintas');
  await page.uncheck(`${g3} [data-excluir][value="2003"]`);
  // Excluir la conservada pasa la conservación a otra (la que elegiría el servidor entre las que quedan)
  await page.check(`${g3} [data-excluir][value="2001"]`);
  const c = await estado();
  d.sin_conservada = c;
  v.conservada_pasa_a_otra = c.conservar.join() === '2002' && c.unir === false;
  await page.uncheck(`${g3} [data-excluir][value="2001"]`);
  // Otra ficha conservada en un grupo sin exclusiones: la vista previa se recalcula con sus datos
  const g1 = '.grupo-coinc[data-clave="12"]';
  await page.check(`${g1} [data-conservar][value="940"]`);
  d.otra_conservada = await page.evaluate((s) => {
    const g = document.querySelector(s);
    const t = (x) => g.querySelector(x).textContent.replace(/\s+/g, ' ').trim();
    const pieza = (x) => { const el = g.querySelector(x); return [[...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join('').trim(),
      el.querySelector(':scope > .fuente')?.dataset.fuente ?? null, el.querySelector('.de-ficha')?.textContent.replace('de la ficha ', '') ?? null]; };
    return [t('thead .quedaria'), pieza('tr[data-fila="direccion"] td.quedaria .pieza'), pieza('tr[data-fila="edad"] td.quedaria .pieza'),
      t('tr[data-fila="edad"] td.quedaria .pasan')];
  }, g1);
  v.otra_conservada = d.otra_conservada[0] === 'Quedaría Se conserva la ficha B · estimado con su elección'
    && d.otra_conservada[1].join('|') === 'VEREDA LA CONDOR|tramites|B' && d.otra_conservada[2].join('|') === '40 años|tramites|B'
    && d.otra_conservada[3] === 'y 1 valor pasa a alternos';
  await captura(page, 'escritorio-excluir', { fullPage: true });
  await ctx.close();
}

// ── seleccion: dos grupos, «Unir» de la barra, el cuerpo exacto del POST, un error por grupo y los conteos ──
async function cSeleccion(nav, caso) {
  const { ctx, page, v, d, insignias } = await abrir(nav, caso);
  const reg = await servirGrupos(ctx, gruposBase(), { fallar: { '30-31': { codigo: 'cedulas_distintas', error: 'Tienen cédulas distintas: 52111222 y 52999888' } } });
  await abrirCoincidencias(page);
  await page.check('.grupo-coinc[data-clave="12"] [data-sel]');
  await page.check('.grupo-coinc[data-clave="30-31"] [data-excluir][value="2002"]');
  await page.check('.grupo-coinc[data-clave="30-31"] [data-sel]');
  d.barra = await page.$eval('#cuenta-sel', (x) => x.textContent);
  v.barra_cuenta = d.barra === '2 grupos seleccionados · 5 fichas';
  v.tarjetas_marcadas = await page.$$eval('.grupo-coinc.seleccionada', (x) => x.length) === 2;
  const antes = insignias.n;
  await page.click('[data-sel-unir]');
  d.confirmacion = await confirmarDialogo(page);
  v.confirma_con_numeros = d.confirmacion.startsWith('¿Unir 2 grupos? Sus 4 fichas quedarán en 2');
  await page.waitForFunction(() => !document.querySelector('.grupo-coinc[data-clave="12"]'), null, espera);
  await page.waitForSelector('.grupo-coinc[data-clave="30-31"] .error-grupo:not([hidden])', espera);
  d.post = reg.posts[0];
  v.un_solo_post = reg.posts.length === 1;
  const r = await page.evaluate(() => ({
    error: document.querySelector('.grupo-coinc[data-clave="30-31"] .error-grupo').textContent.trim(),
    alta: document.querySelector('[data-cuenta-nivel="alta"]').textContent, todos: document.querySelector('[data-cuenta-nivel=""]').textContent,
    boton: document.querySelector('[data-texto-alta]').textContent, cuenta: document.querySelector('#cuenta-grupos').textContent,
    barra: document.querySelector('#cuenta-sel').textContent, sigue: document.querySelector('.grupo-coinc[data-clave="30-31"] [data-sel]').checked,
  }));
  d.r = r;
  v.error_del_servidor_en_su_tarjeta = r.error === 'Tienen cédulas distintas: 52111222 y 52999888';
  v.conteos_al_dia = r.alta === '1' && r.todos === '3' && r.boton === 'Unir la muy probable' && r.cuenta.startsWith('3 grupos con 5 coincidencias entre 8 fichas');
  v.la_fallida_sigue_seleccionada = r.sigue && r.barra === '1 grupo seleccionado · 3 fichas';
  await dormir(300);
  v.refresca_insignias = insignias.n > antes;
  // «Seleccionar todos los de esta página» y «Quitar selección»
  await page.click('[data-sel-quitar]');
  await page.click('[data-sel-todos]');
  v.selecciona_todos = await page.$eval('#cuenta-sel', (x) => x.textContent) === '3 grupos seleccionados · 8 fichas';
  await page.click('[data-sel-quitar]');
  v.quita_seleccion = await page.$$eval('.grupo-coinc.seleccionada', (x) => x.length) === 0;
  // «Marcar distintas» de un grupo con su botón: decisión separar, sin conservar ni excluir
  await page.click('.grupo-coinc[data-clave="20-21"] [data-separar]');
  await page.waitForFunction(() => !document.querySelector('.grupo-coinc[data-clave="20-21"]'), null, espera);
  d.separar = reg.posts[1];
  v.separar = JSON.stringify(reg.posts[1]) === JSON.stringify({ grupos: [{ pares: [20, 21], decision: 'separar' }] });
  await ctx.close();
}

// ── masivo: «Unir las 60 muy probables» de a 50, un grupo que falla y no se reintenta ──
async function cMasivo(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso);
  const alta = muchosAlta(60);
  const fallida = alta[7].clave;
  const reg = await servirGrupos(ctx, [...alta, ...gruposBase().slice(2)], { fallar: { [fallida]: { codigo: 'rechazada_antes', error: 'Ya se marcaron como distintas' } } });
  await abrirCoincidencias(page);
  v.boton = await page.$eval('[data-texto-alta]', (x) => x.textContent) === 'Unir las 60 muy probables';
  await page.click('[data-unir-alta]');
  d.confirmacion = await confirmarDialogo(page);
  v.confirma_grupos_y_fichas = d.confirmacion.startsWith('Se unirán las fichas de 60 grupos muy probables: 120 fichas quedarán en 60.');
  await page.waitForSelector('dialog[open] .progreso-lote', espera);
  await page.waitForFunction(() => /^Listo/.test(document.querySelector('dialog[open] [data-estado]')?.textContent || ''), null, espera);
  const r = await page.evaluate(() => {
    const dl = document.querySelector('dialog[open]');
    const t = (s) => dl.querySelector(s).textContent.trim();
    return { estado: t('[data-estado]'), grupos: t('[data-grupos]'), unidas: t('[data-unidas]'), errores: t('[data-errores]'),
      lista: t('[data-lista-errores]'), barra: dl.querySelector('.barra-progreso').getAttribute('aria-valuenow'),
      ancho: dl.querySelector('.barra-progreso i').style.width, pie: t('.pie') };
  });
  d.r = r;
  await dormir(400); // la barra llega al final con una transición
  await captura(page, 'escritorio-progreso');
  d.tandas = reg.posts.map((p) => p.grupos.length);
  const enviadas = reg.posts.flatMap((p) => p.grupos.map((g) => g.pares.join('-')));
  v.no_reintenta_la_fallida = enviadas.filter((k) => k === fallida).length === 1;
  v.conservar_por_defecto = reg.posts.every((p) => p.grupos.every((g) => g.decision === 'unir' && !('conservar' in g) && !('excluir' in g)));
  v.pide_de_a_50 = reg.gets.filter((q) => q.nivel === 'alta' && q.por_pagina === '50').length >= 2;
  v.progreso = r.grupos === '59' && r.unidas === '59' && r.errores === '1' && r.barra === '60' && r.ancho === '100%'
    && r.lista === 'PERSONA ALTA 7 INVENTADA y PERSONA ALTA 7 INVENTADA COPIA: Ya se marcaron como distintas';
  v.resumen = r.estado === 'Listo: 59 fichas unidas en 59 grupos; 1 grupo quedó para revisar a mano.' && r.pie === 'Cerrar';
  await page.click('dialog[open] .pie [data-cerrar]');
  await page.waitForFunction(() => document.querySelectorAll('.grupo-coinc').length === 3, null, espera);
  v.recarga_al_terminar = (await tarjetas(page)).join() === `${fallida},20-21,30-31`;
  await ctx.close();
}

// ── detener: con 120 por unir, «Detener» durante la primera tanda no pide otra ──
async function cDetener(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso);
  const reg = await servirGrupos(ctx, muchosAlta(120), { demora: 1500 });
  await abrirCoincidencias(page);
  await page.click('[data-unir-alta]');
  await confirmarDialogo(page);
  await page.waitForFunction(() => /^Uniendo/.test(document.querySelector('dialog[open] [data-estado]')?.textContent || ''), null, espera);
  await page.click('dialog[open] [data-detener]');
  v.avisa_que_se_detiene = await page.$eval('dialog[open] [data-estado]', (x) => x.textContent) === 'Se detiene al terminar la tanda en curso…';
  await page.waitForFunction(() => /^Detenido/.test(document.querySelector('dialog[open] [data-estado]')?.textContent || ''), null, espera);
  d.estado = await page.$eval('dialog[open] [data-estado]', (x) => x.textContent);
  d.posts = reg.posts.length;
  v.una_sola_tanda = reg.posts.length === 1 && d.estado === 'Detenido: 50 fichas unidas en 50 grupos.';
  await page.click('dialog[open] .pie [data-cerrar]');
  await page.waitForFunction(() => document.querySelector('[data-texto-alta]')?.textContent === 'Unir las 70 muy probables', null, espera);
  // Quedan 70: de a 25 por página, como Habitantes; «Siguiente» pide la página 2 y la deja en la dirección
  v.paginacion = await page.$eval('.unificacion .paginacion > span', (x) => x.textContent) === 'Página 1 de 3'
    && (await tarjetas(page)).length === 25;
  await page.click('.unificacion [data-pagina="2"]');
  await page.waitForFunction(() => new URLSearchParams(location.search).get('pagina') === '2', null, espera);
  await page.waitForFunction(() => document.querySelector('.unificacion .paginacion > span')?.textContent === 'Página 2 de 3', null, espera);
  v.pagina_2 = reg.gets.at(-1).pagina === '2' && reg.gets.at(-1).por_pagina === '25' && (await tarjetas(page)).length === 25;
  await ctx.close();
}

// ── atajos: j/k mueven el foco, x selecciona, d y u resuelven el grupo enfocado; no dentro de un campo ──
async function cAtajos(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso);
  const reg = await servirGrupos(ctx, gruposBase());
  await abrirCoincidencias(page);
  const foco = () => page.evaluate(() => document.activeElement?.closest('.grupo-coinc')?.dataset.clave ?? null);
  await page.keyboard.press('j');
  const f1 = await foco();
  await page.keyboard.press('j');
  const f2 = await foco();
  await page.keyboard.press('k');
  const f3 = await foco();
  d.focos = [f1, f2, f3];
  v.j_y_k = f1 === '12' && f2 === '13' && f3 === '12';
  await page.keyboard.press('x');
  v.x_selecciona = await page.$eval('.grupo-coinc[data-clave="12"] [data-sel]', (x) => x.checked)
    && await page.$eval('#cuenta-sel', (x) => x.textContent) === '1 grupo seleccionado · 2 fichas';
  await page.keyboard.press('x');
  v.x_quita = !await page.$eval('.grupo-coinc[data-clave="12"] [data-sel]', (x) => x.checked);
  // En un campo, las letras son del campo
  await page.focus('[data-motivo]');
  await page.keyboard.press('j');
  v.no_en_un_campo = await page.evaluate(() => document.activeElement?.matches('[data-motivo]'));
  await page.keyboard.press('Escape');
  await page.evaluate(() => document.activeElement.blur());
  await page.keyboard.press('k');
  v.recuerda_el_grupo_actual = await foco() === '12';
  await page.keyboard.press('d');
  await page.waitForFunction(() => !document.querySelector('.grupo-coinc[data-clave="12"]'), null, espera);
  v.foco_pasa_a_la_siguiente = await foco() === '13';
  await page.keyboard.press('u');
  await page.waitForFunction(() => !document.querySelector('.grupo-coinc[data-clave="13"]'), null, espera);
  d.posts = reg.posts;
  // En la bloqueada, «u» no une: dice por qué
  await page.keyboard.press('j');
  await page.keyboard.press('j');
  d.foco_final = await foco();
  await page.keyboard.press('u');
  await page.waitForSelector('#avisos .aviso.error', espera);
  v.u_en_bloqueada_explica = (await page.$eval('#avisos .aviso.error', (x) => x.textContent)).startsWith('Tienen cédulas distintas') && reg.posts.length === 2;
  await ctx.close();
}

// ── movil y tableta: sin desborde, grilla que se desplaza dentro con rótulos fijos, barra abajo y blancos de 44 px ──
async function cMovil(nav, caso, ancho, alto) {
  const { ctx, page, v, d } = await abrir(nav, caso, { viewport: { width: ancho, height: alto }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 });
  await servirGrupos(ctx, gruposBase());
  await abrirCoincidencias(page);
  // Blancos táctiles, antes de cualquier captura de página completa (la emulación deja de ser «coarse» después)
  const medidas = await page.evaluate(() => {
    const chicos = [];
    for (const s of ['.sel-grupo', '.opcion-ficha', '.botones-grupo .btn', '.nivel-filtro', '[data-motivo]', '.leyenda-fuentes > summary', '[data-sel-todos]']) {
      for (const el of document.querySelectorAll(s)) {
        const r = el.getBoundingClientRect();
        if (r.width && (r.height < 43.5 || (s === '.sel-grupo' && r.width < 43.5))) chicos.push(`${s} ${Math.round(r.width)}×${Math.round(r.height)}`);
      }
    }
    const env = document.querySelector('.grupo-coinc[data-clave="20-21"] .comparar-envoltura');
    const rot = env.querySelector('tbody th');
    return { chicos, coarse: matchMedia('(pointer: coarse)').matches, desplaza: env.scrollWidth > env.clientWidth + 4,
      rotulo: getComputedStyle(rot).position, columna: env.querySelector('tbody td').getBoundingClientRect().width,
      fuente16: [...document.querySelectorAll('.unificacion select')].every((x) => parseFloat(getComputedStyle(x).fontSize) >= 16) };
  });
  d.medidas = medidas;
  v.blancos_de_44 = medidas.coarse && !medidas.chicos.length;
  v.selects_de_16 = ancho > 900 || medidas.fuente16;
  v.sin_desborde = await sinDesborde(page);
  if (ancho <= 640) {
    v.grilla_se_desplaza_dentro = medidas.desplaza && medidas.rotulo === 'sticky' && medidas.columna >= 128;
    // El rótulo queda fijo al desplazar la grilla de costado
    const fijo = await page.evaluate(() => {
      const env = document.querySelector('.grupo-coinc[data-clave="20-21"] .comparar-envoltura');
      const rot = env.querySelector('tbody th');
      const x0 = rot.getBoundingClientRect().left;
      env.scrollLeft = 200;
      return { x0, x1: rot.getBoundingClientRect().left, movio: env.scrollLeft > 0 };
    });
    v.rotulo_fijo = fijo.movio && Math.abs(fijo.x0 - fijo.x1) < 1;
  }
  await captura(page, `movil-${ancho}x${alto}-arriba`);
  // Con algo seleccionado, la barra va fija abajo, dentro de la pantalla
  await page.tap('.grupo-coinc[data-clave="12"] .sel-grupo');
  await page.waitForSelector('#barra-sel.con-seleccion', espera);
  const barra = await page.evaluate(() => {
    const b = document.querySelector('#barra-sel');
    const r = b.getBoundingClientRect();
    const btns = [...b.querySelectorAll('.btn:not([hidden])')].map((x) => x.getBoundingClientRect());
    return { pos: getComputedStyle(b).position, abajo: Math.round(r.bottom), alto: innerHeight, ancho: Math.round(r.width), vw: innerWidth,
      botones: btns.every((x) => x.height >= 43.5 && x.right <= innerWidth + 0.5 && x.left >= -0.5) };
  });
  d.barra = barra;
  if (ancho <= 900) v.barra_fija_abajo = barra.pos === 'fixed' && Math.abs(barra.abajo - barra.alto) <= 1 && barra.ancho === barra.vw && barra.botones;
  else v.barra_pegada = barra.pos === 'sticky' && barra.botones;
  v.sin_desborde_con_barra = await sinDesborde(page);
  await page.evaluate(() => document.querySelector('.grupo-coinc[data-clave="20-21"]').scrollIntoView());
  await captura(page, `movil-${ancho}x${alto}-grupo`);
  await captura(page, `movil-${ancho}x${alto}-completa`, { fullPage: true });
  await ctx.close();
}

// ── oscuro: el tema oscuro del sistema, el contraste de las insignias y las capturas ──
async function cOscuro(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso, { colorScheme: 'dark' });
  await servirGrupos(ctx, gruposBase());
  await abrirCoincidencias(page);
  await page.click('.unificacion .leyenda-fuentes summary');
  const r = await page.evaluate(() => ({
    fondo: getComputedStyle(document.body).backgroundColor, tarjeta: getComputedStyle(document.querySelector('.grupo-coinc')).backgroundColor,
    letra: getComputedStyle(document.querySelector('.comparar .fuente[data-fuente="cedulas"]')).color,
  }));
  d.r = r;
  v.fondo_oscuro = r.fondo === 'rgb(13, 13, 13)' && r.tarjeta === 'rgb(22, 22, 22)';
  const cr = await page.evaluate(CONTRASTES, '.unificacion .fuente, .unificacion .chip.nivel, .unificacion .senal');
  d.contraste = cr.filter((x) => x.cr < 4.5);
  v.contraste_oscuro = cr.length > 20 && !d.contraste.length;
  v.sin_desborde = await sinDesborde(page);
  await page.mouse.move(0, 0);
  await captura(page, 'escritorio-oscuro', { fullPage: true });
  await ctx.close();
  // El celular en oscuro (solo la captura y el desborde)
  const m = await abrir(nav, caso, { colorScheme: 'dark', viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 });
  await servirGrupos(m.ctx, gruposBase());
  await abrirCoincidencias(m.page);
  v.sin_desborde_movil = await sinDesborde(m.page);
  await captura(m.page, 'movil-oscuro');
  await m.ctx.close();
}

// ── ficha y directorio con la API real: insignias, «por cruce», «Otra fuente dice», teléfonos y el enlace «revisar» ──
async function cFicha(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso);
  const reg = await servirGrupos(ctx, [grupo({ nivel: 'media', puntaje: null, destino: D.persona, miembros: [
    miembro(D.persona, 'MARIA INVENTADA DE PRUEBA', { cedula: '1098765432' }), miembro(D.otra, 'MARIA INVENTADA PRUEBA') ],
    pares: [par(900001, D.persona, D.otra, null, 'reporte', 'media')] })]);
  await ingresar(page, `/personas/${D.persona}`);
  await page.waitForSelector('#f-datos', espera);
  const r = await page.evaluate(() => {
    const t = (s) => document.querySelector(s)?.textContent.replace(/\s+/g, ' ').trim() ?? null;
    return {
      cabecera: [...document.querySelectorAll('.cabecera .fuente.con-nombre')].map((x) => x.dataset.fuente),
      cabeceraTexto: (() => { const x = document.querySelector('.cabecera .fuente.con-nombre[data-fuente="cedulas"]'); return [x.title, x.lastChild.textContent, x.querySelector('.letra').textContent]; })(),
      cedula: document.querySelector('[data-campo="cedula"] > span .fuente')?.dataset.fuente, cruce: t('[data-campo="cedula"] .marca-cruce'),
      correo: document.querySelector('[data-campo="correo"] > span .fuente')?.dataset.fuente,
      sexo: document.querySelector('[data-campo="sexo"] > span .fuente')?.dataset.fuente,
      vacio: document.querySelector('[data-campo="direccion"] > span .fuente'),
      alterno: document.querySelector('[data-campo="correo"] .alterno .fuente')?.dataset.fuente, alternoTexto: t('[data-campo="correo"] .alterno b'),
      telefono: [...document.querySelectorAll('.tel .fuente')].map((x) => x.dataset.fuente),
      revisar: document.querySelector('[data-revisar-coincidencias]')?.getAttribute('href'),
      aviso: document.querySelector('[data-revisar-coincidencias]')?.closest('.aviso-legal').textContent.replace(/\s+/g, ' ').trim(),
    };
  });
  d.ficha = r;
  v.cabecera_con_nombre = r.cabecera.join() === 'equipo,cedulas,tramites' && r.cabeceraTexto.join('|') === 'Fuente: Base con cédula|Base con cédula|B';
  v.campo_con_su_fuente = r.cedula === 'cedulas' && r.cruce === 'por cruce' && r.correo === 'tramites' && r.sexo === 'equipo' && r.vacio === null;
  v.otra_fuente_dice = r.alterno === 'fusion' && r.alternoTexto === 'otra@example.com';
  v.telefono_con_insignias = r.telefono.join() === 'cedulas,tramites';
  v.revisar_enlaza_al_grupo = r.revisar === `${pref}/calidad?p=coincidencias&persona=${D.persona}` && r.aviso === 'Posible misma persona que MARIA INVENTADA PRUEBA — revisar';
  // La pestaña Origen: alternos, procedencia y títulos de cada origen con su insignia
  await page.click('[data-tab="origen"]');
  d.origen = await page.evaluate(() => ({
    alternos: [...document.querySelectorAll('[data-panel="origen"] table .fuente')].map((x) => x.dataset.fuente),
    procedencia: [...document.querySelectorAll('[data-panel="origen"] .datos .fuente')].map((x) => x.dataset.fuente),
    leyenda: !!document.querySelector('[data-panel="origen"] .leyenda-fuentes'),
  }));
  v.origen = d.origen.alternos.join() === 'fusion' && d.origen.procedencia.join() === 'cedulas,tramites,equipo,cedulas' && d.origen.leyenda;
  // La letra de la insignia no pierde su color dentro de `.datos` (que apaga los span)
  d.color_en_datos = await page.evaluate(() => {
    const f = document.querySelector('[data-panel="origen"] .datos .fuente');
    return [getComputedStyle(f).color, getComputedStyle(f.querySelector('.letra')).color, getComputedStyle(f).display];
  });
  v.color_en_datos = d.color_en_datos[0] === d.color_en_datos[1] && d.color_en_datos[2] === 'inline-flex';
  await captura(page, 'ficha-origen', { fullPage: true });
  await page.click('[data-tab="datos"]');
  await captura(page, 'ficha-datos');
  // «revisar» abre Coincidencias con solo el grupo de esta ficha
  await page.click('[data-revisar-coincidencias]');
  await page.waitForSelector('.unificacion .filtro-persona', espera);
  v.revisar_filtra = reg.gets.at(-1).persona === String(D.persona) && (await tarjetas(page)).length === 1;
  d.url = await page.evaluate(() => location.pathname + location.search);
  v.url_con_persona = d.url === `${pref}/calidad?p=coincidencias&persona=${D.persona}`;
  await page.click('[data-ver-todos]');
  await page.waitForFunction(() => !document.querySelector('.filtro-persona'), null, espera);
  v.ver_todos = !reg.gets.at(-1).persona;
  // Conflictos de cédula: la insignia de la fuente de la fila y las de la ficha
  await page.click('[data-tab="conflictos"]');
  await page.waitForSelector('[data-k="900002"]', espera);
  d.conflicto = await page.evaluate(() => {
    const t = document.querySelector('[data-k="900002"]');
    return { fila: t.querySelector('.lado .sec .fuente.con-nombre')?.dataset.fuente,
      ficha: [...t.querySelectorAll('.lado .fuentes .fuente')].map((x) => x.dataset.fuente) };
  });
  v.conflicto_con_fuentes = d.conflicto.fila === 'planilla' && d.conflicto.ficha.join() === 'equipo,cedulas,tramites';
  // El directorio: insignias en la fila (A) y la leyenda plegable sobre la tabla
  await ir(page, '/personas');
  await page.waitForSelector(`#filas tr[data-id="${D.persona}"]`, espera);
  d.directorio = await page.evaluate((id) => ({
    fila: [...document.querySelectorAll(`#filas tr[data-id="${id}"] .chips-fila .fuente`)].map((x) => x.dataset.fuente),
    gris: document.querySelectorAll(`#filas tr[data-id="${id}"] .chips-fila .chip.borde`).length,
    leyenda: document.querySelector('.leyenda-fuentes summary')?.textContent,
    antesDeLaTabla: !!document.querySelector('.leyenda-fuentes + .envoltura-tabla'),
  }), D.persona);
  v.directorio = d.directorio.fila.join() === 'equipo,cedulas,tramites' && d.directorio.gris === 0
    && d.directorio.leyenda === '¿Qué significan los colores?' && d.directorio.antesDeLaTabla;
  v.sin_desborde_directorio = await sinDesborde(page);
  await ctx.close();
}

// Mide cuando el diseño quedó quieto: la misma medida en dos cuadros seguidos (un desplazamiento suave, una transición),
// en vez de esperar un tiempo fijo
async function medirEstable(page, fn, arg) {
  let antes = null;
  for (let i = 0; i < 60; i++) {
    await page.evaluate(() => new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok))));
    const ahora = await page.evaluate(fn, arg ?? null);
    if (antes && JSON.stringify(ahora) === JSON.stringify(antes)) return ahora;
    antes = ahora;
  }
  return antes;
}
const focoGrupo = (page) => page.evaluate(() => document.activeElement?.closest('.grupo-coinc')?.dataset.clave ?? null);

// ── marcas: «Unir las N muy probables» respeta lo marcado en las tarjetas a la vista (conservar y excluir) ──
async function cMarcas(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso);
  // Un grupo de tres muy probable: sin la C, la A y la B siguen unidas por su par
  const tres = grupo({ nivel: 'alta', puntaje: 0.95, destino: 6001, miembros: [
    miembro(6001, 'ROSA INVENTADA LOPEZ', { cedula: '43555666', fuentes: ['cedulas'], completitud: 60 }),
    miembro(6002, 'ROSA LOPEZ', { telefonos: ['3005550001'] }), miembro(6003, 'ROSALBA LOPEZ', { telefonos: ['3005550002'] }),
  ], pares: [par(7100, 6001, 6002, 0.95, 'nombre_telefono', 'alta'), par(7101, 6001, 6003, 0.93, 'nombre_telefono', 'alta')] });
  const reg = await servirGrupos(ctx, [...muchosAlta(4), tres, ...gruposBase().slice(2)]);
  await abrirCoincidencias(page);
  // 7000: «No es la misma» en la B lo deja con una sola ficha (no se une); 7001: se conserva la B; el de tres, sin la C
  await page.check('.grupo-coinc[data-clave="7000"] [data-excluir][value="5001"]');
  await page.check('.grupo-coinc[data-clave="7001"] [data-conservar][value="5003"]');
  await page.check('.grupo-coinc[data-clave="7100-7101"] [data-excluir][value="6003"]');
  await page.click('[data-unir-alta]');
  await page.waitForSelector('dialog[open] [data-si]', espera);
  d.boton = await page.$eval('dialog[open] [data-si]', (x) => x.textContent.trim());
  d.confirmacion = await confirmarDialogo(page);
  v.confirma_sin_el_bloqueado = d.confirmacion.startsWith('Se unirán las fichas de 4 grupos muy probables: 8 fichas quedarán en 4.') && d.boton === 'Unir 4 grupos';
  v.dice_cuantos_llevan_lo_marcado = d.confirmacion.includes('2 se unen con lo que usted marcó en sus tarjetas')
    && d.confirmacion.includes('En los demás se conserva la ficha con cédula')
    && d.confirmacion.endsWith('Uno queda sin unir: lo que marcó en su tarjeta no deja unirlo.');
  await page.waitForFunction(() => /^Listo/.test(document.querySelector('dialog[open] [data-estado]')?.textContent || ''), null, espera);
  d.estado = await page.$eval('dialog[open] [data-estado]', (x) => x.textContent);
  v.resumen = d.estado === 'Listo: 4 fichas unidas en 4 grupos.';
  d.posts = reg.posts;
  await page.click('dialog[open] .pie [data-cerrar]');
  await page.waitForFunction(() => document.querySelectorAll('.grupo-coinc').length === 3, null, espera);
  v.el_bloqueado_sigue_pendiente = (await tarjetas(page)).join() === '7000,20-21,30-31';
  await ctx.close();
}

// ── persona: desde el enlace «revisar» de una ficha, el botón solo une el grupo de esa ficha ──
async function cPersona(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso);
  const reg = await servirGrupos(ctx, muchosAlta(30));
  await abrirCoincidencias(page, '&persona=5004');
  v.solo_su_grupo = (await tarjetas(page)).join() === '7002' && await page.$eval('[data-texto-alta]', (x) => x.textContent) === 'Unir la muy probable';
  await page.click('[data-unir-alta]');
  d.confirmacion = await confirmarDialogo(page);
  v.confirma_lo_filtrado = d.confirmacion.startsWith('Se unirán las 2 fichas del grupo muy probable en una sola.');
  await page.waitForFunction(() => /^Listo/.test(document.querySelector('dialog[open] [data-estado]')?.textContent || ''), null, espera);
  const altas = reg.gets.filter((q) => q.nivel === 'alta');
  d.gets = altas;
  v.pide_con_la_ficha = altas.length >= 2 && altas.every((q) => q.persona === '5004');
  v.las_demas_siguen = reg.resueltos.size === 1;
  d.posts = reg.posts;
  await ctx.close();
}

// ── paginacion: tras resolver en la página 1, «Siguiente» no se salta los que pasaron a ella ──
async function cPaginacion(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso);
  const reg = await servirGrupos(ctx, muchosAlta(51));
  await abrirCoincidencias(page);
  const texto = () => page.$eval('.unificacion .paginacion > span', (x) => x.textContent);
  const vistos = new Set(await tarjetas(page));
  v.primera = vistos.size === 25 && await texto() === 'Página 1 de 3';
  for (const k of ['7000', '7001', '7002']) await page.check(`.grupo-coinc[data-clave="${k}"] [data-sel]`);
  await page.click('[data-sel-unir]');
  await confirmarDialogo(page);
  await page.waitForFunction(() => document.querySelectorAll('.grupo-coinc').length === 22, null, espera);
  // Quedan 48: la cuenta de páginas se rehace y «Siguiente» sigue activo (hay grupos después de los que se ven)
  d.texto = await texto();
  v.cuenta_al_dia = d.texto === 'Página 1 de 2' && !await page.$eval('[data-siguiente]', (x) => x.disabled);
  await page.click('.unificacion [data-siguiente]');
  await page.waitForSelector('.grupo-coinc[data-clave="7025"]', espera);
  v.pide_otra_vez_la_misma = reg.gets.at(-1).pagina === '1' && !(await page.evaluate(() => location.search)).includes('pagina');
  const ahora = await tarjetas(page);
  d.nuevas = ahora.filter((k) => !vistos.has(k));
  v.completa_con_los_que_seguian = d.nuevas.join() === '7025,7026,7027' && ahora.length === 25;
  v.foco_en_el_primero_nuevo = await focoGrupo(page) === '7025';
  for (const k of ahora) vistos.add(k);
  // Ahora sí, la página 2: empieza justo después del último que se vio
  await page.click('.unificacion [data-siguiente]');
  await page.waitForFunction(() => document.querySelector('.unificacion .paginacion > span')?.textContent === 'Página 2 de 2', null, espera);
  const p2 = await tarjetas(page);
  d.p2 = [p2[0], p2.length];
  for (const k of p2) vistos.add(k);
  v.ninguno_saltado = p2[0] === '7028' && p2.length === 23 && vistos.size === 51;
  await ctx.close();
}

// ── paginacion-en-curso: mientras se resuelve un grupo, «Siguiente» y «Anterior» quedan quietos ──
// El servidor ya unió y la respuesta no llegó: la lista que arma ya corrió hacia atrás los grupos que seguían, y
// «Siguiente» pedía la página de después (el primero de ellos, que cae en esta, no se veía nunca)
async function cPaginacionEnCurso(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso);
  const reg = await servirGrupos(ctx, muchosAlta(30));
  await abrirCoincidencias(page);
  const botones = () => page.evaluate(() => ({ texto: document.querySelector('.unificacion [data-pagina-texto]')?.textContent ?? null,
    anterior: document.querySelector('.unificacion .paginacion [data-pagina]:not([data-siguiente])')?.disabled ?? null,
    siguiente: document.querySelector('.unificacion [data-siguiente]')?.disabled ?? null }));
  // «Es la misma persona» en un grupo; la respuesta se retiene hasta mirar los botones
  const resolverRetenido = async (clave) => {
    let soltar;
    reg.retener = new Promise((ok) => { soltar = ok; });
    const enviado = page.waitForRequest((r) => new URL(r.url()).pathname === pref + '/api/coincidencias/lote', espera);
    await page.click(`.grupo-coinc[data-clave="${clave}"] [data-unir]`);
    await enviado;
    await page.waitForSelector(`.grupo-coinc[data-clave="${clave}"].enviando`, espera);
    const enCurso = await botones();
    soltar();
    reg.retener = null;
    await page.waitForFunction((k) => !document.querySelector(`.grupo-coinc[data-clave="${k}"]`), clave, espera);
    return { enCurso, tras: await botones() };
  };
  const vistos = new Set(await tarjetas(page));
  d.antes = await botones();
  v.antes = vistos.size === 25 && d.antes.texto === 'Página 1 de 2' && d.antes.siguiente === false && d.antes.anterior === true;
  // El último de la primera página, justo encima de «Siguiente»
  const p1 = await resolverRetenido('7024');
  d.p1 = p1;
  v.siguiente_quieto_en_curso = p1.enCurso.siguiente === true && p1.enCurso.anterior === true;
  v.siguiente_vuelve_con_la_respuesta = p1.tras.siguiente === false && p1.tras.texto === 'Página 1 de 2';
  // Con la respuesta, «Siguiente» completa esta página con el que seguía, y luego lleva a la 2 sin saltarse ninguno
  await page.click('.unificacion [data-siguiente]');
  await page.waitForSelector('.grupo-coinc[data-clave="7025"]', espera);
  v.completa_la_misma = reg.gets.at(-1).pagina === '1';
  for (const k of await tarjetas(page)) vistos.add(k);
  await page.click('.unificacion [data-siguiente]');
  await page.waitForFunction(() => document.querySelector('.unificacion [data-pagina-texto]')?.textContent === 'Página 2 de 2', null, espera);
  const p2 = await tarjetas(page);
  for (const k of p2) vistos.add(k);
  d.p2 = p2;
  v.ninguno_saltado = p2[0] === '7026' && vistos.size === 30;
  // En la segunda, «Anterior» también queda quieto mientras se resuelve uno
  const p2r = await resolverRetenido(p2[0]);
  d.p2r = p2r;
  v.anterior_quieto_en_curso = p2r.enCurso.anterior === true && p2r.enCurso.siguiente === true;
  v.anterior_vuelve_con_la_respuesta = p2r.tras.anterior === false;
  await ctx.close();
}

// ── lugar: la vista previa estimada deja el barrio de la ficha mejor ubicada, como la unión ──
async function cLugar(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso);
  // A con cédula y un punto marcado a mano en BATALLON (rango 4); B ubicada solo por el centro de LA CONDOR (rango 1)
  const conRango = grupo({ nivel: 'alta', puntaje: 0.93, destino: 3001, miembros: [
    miembro(3001, 'CARLOS INVENTADO DIAZ', { cedula: '71222333', fuentes: ['cedulas'], lugar: 'BATALLON', rango_ubicacion: 4, completitud: 60 }),
    miembro(3002, 'CARLOS DIAZ', { lugar: 'LA CONDOR', rango_ubicacion: 1, direccion: 'VEREDA LA CONDOR CASA 9' }),
  ], pares: [par(40, 3001, 3002, 0.93, 'nombre_telefono', 'alta')] });
  // Lo mismo sin el rango (un servidor anterior): no se sabe cuál está mejor ubicada
  const ms = [miembro(3101, 'LUIS INVENTADO ROA', { cedula: '71444555', fuentes: ['cedulas'], lugar: 'BATALLON', completitud: 60 }),
    miembro(3102, 'LUIS ROA', { lugar: 'LA CONDOR' })];
  for (const m of ms) delete m.rango_ubicacion;
  const sinRango = grupo({ nivel: 'alta', puntaje: 0.9, destino: 3101, miembros: ms, pares: [par(41, 3101, 3102, 0.9, 'nombre_telefono', 'alta')] });
  await servirGrupos(ctx, [conRango, sinRango]);
  await abrirCoincidencias(page);
  const lugar = (clave) => page.evaluate((c) => {
    const t = document.querySelector(`.grupo-coinc[data-clave="${c}"]`);
    const celda = t.querySelector('tr[data-fila="lugar"] td.quedaria');
    const p = celda.querySelector('.pieza');
    return { texto: celda.textContent.replace(/\s+/g, ' ').trim(), cabeza: t.querySelector('thead .quedaria').textContent.replace(/\s+/g, ' ').trim(),
      valor: p ? [...p.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join('').trim() : null,
      de: p?.querySelector('.de-ficha')?.textContent.replace('de la ficha ', '') ?? null };
  }, clave);
  d.servidor = await lugar('40');
  v.la_del_servidor = d.servidor.valor === 'Batallon' && d.servidor.de === 'A';
  // Conservar la peor ubicada no le quita el lugar a la mejor: la ubicación pasa en bloque
  await page.check('.grupo-coinc[data-clave="40"] [data-conservar][value="3002"]');
  d.otra = await lugar('40');
  v.sigue_la_mejor_ubicada = d.otra.valor === 'Batallon' && d.otra.de === 'A'
    && d.otra.cabeza.startsWith('Quedaría Se conserva la ficha B · estimado con su elección');
  // Sin el rango no promete un barrio
  await page.check('.grupo-coinc[data-clave="41"] [data-conservar][value="3102"]');
  d.sin = await lugar('41');
  v.sin_rango_no_promete = d.sin.valor === null && d.sin.texto === 'El de la ficha mejor ubicada' && d.sin.cabeza.includes('estimado con su elección');
  await ctx.close();
}

// ── url: un motivo desconocido o una página de más en la dirección, y una carga que falla, dejan salida ──
async function cUrl(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso);
  const reg = await servirGrupos(ctx, gruposBase());
  await abrirCoincidencias(page, '&motivo=duplicado_viejo');
  await page.waitForSelector('.grupo-coinc', espera);
  v.motivo_desconocido = !reg.gets.some((q) => q.motivo) && (await tarjetas(page)).length === 4
    && !(await page.evaluate(() => location.search)).includes('motivo');
  await ir(page, '/calidad?p=coincidencias&pagina=200000');
  await page.waitForSelector('.grupo-coinc', espera);
  d.paginas = reg.gets.map((q) => q.pagina);
  v.pagina_de_mas = reg.gets.every((q) => Number(q.pagina) <= 100000) && reg.gets.at(-1).pagina === '1' && (await tarjetas(page)).length === 4
    && !(await page.evaluate(() => location.search)).includes('pagina');
  // Con un filtro, la falla ofrece volver a todos los grupos
  reg.fallarGet = 1;
  await page.click('[data-nivel-filtro="baja"]');
  await page.waitForSelector('#cuerpo .error-carga [data-salida]', espera);
  d.error = await page.$eval('#cuerpo .error-carga', (x) => x.textContent.replace(/\s+/g, ' ').trim());
  v.error_con_salida = d.error === 'Falla inventada del servidor Ver todos los grupos';
  await page.click('#cuerpo [data-salida]');
  await page.waitForFunction(() => document.querySelectorAll('.grupo-coinc').length === 4, null, espera);
  v.vuelve_a_todos = !reg.gets.at(-1).nivel && await page.$eval('[data-nivel-filtro=""]', (x) => x.getAttribute('aria-pressed')) === 'true';
  // Sin filtros, la salida es reintentar (aquí, al volver a la pestaña)
  await page.click('[data-tab="conflictos"]');
  await page.waitForSelector('[data-k]', espera);
  reg.fallarGet = 1;
  await page.click('[data-tab="coincidencias"]');
  await page.waitForSelector('#cuerpo .error-carga [data-salida]', espera);
  v.reintentar = await page.$eval('#cuerpo [data-salida]', (x) => x.textContent.trim()) === 'Reintentar';
  await page.click('#cuerpo [data-salida]');
  await page.waitForFunction(() => document.querySelectorAll('.grupo-coinc').length === 4, null, espera);
  await ctx.close();
}

// ── atajos-fuera: no con el asistente (aunque el clic caiga en un texto que no toma el foco), ni tras un clic fuera de la
// vista, ni con mayúscula; sí de vuelta en la vista ──
async function cAtajosFuera(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso);
  const reg = await servirGrupos(ctx, gruposBase());
  await abrirCoincidencias(page);
  const sel = () => page.$$eval('.grupo-coinc [data-sel]:checked', (x) => x.length);
  const actual = () => page.evaluate(() => document.querySelector('.grupo-coinc.actual')?.dataset.clave ?? null);
  // Un clic en la tarjeta la deja como la actual: desde ahí una letra la resolvería
  await page.click('.grupo-coinc[data-clave="12"] .grupo-titulo');
  await page.click('#agente-boton');
  await page.waitForSelector('#agente-panel:not([hidden])', espera);
  await page.click('#agente-panel .agente-titulos h2');
  d.foco_en_el_panel = await page.evaluate(() => document.activeElement?.tagName);
  await page.keyboard.type('jxud');
  await page.keyboard.press('Shift+U');
  v.no_con_el_asistente = reg.posts.length === 0 && await sel() === 0 && await actual() === '12';
  await page.click('#agente-cerrar');
  await page.waitForFunction(() => document.querySelector('#agente-panel')?.hidden, null, espera);
  // De vuelta en la tarjeta: con mayúscula (quien escribe «Una…») no, y una tecla que se repite tampoco
  await page.click('.grupo-coinc[data-clave="12"] .grupo-titulo');
  await page.keyboard.press('Shift+U');
  await page.keyboard.press('Shift+D');
  await page.keyboard.down('x');
  await page.keyboard.down('x'); // la segunda llega con `repeat`
  await page.keyboard.up('x');
  d.sel_repetida = await sel();
  v.no_con_mayuscula_ni_repetida = reg.posts.length === 0 && d.sel_repetida === 1;
  await page.keyboard.press('x');
  // Un clic fuera de la vista (el nombre de la sesión, en el menú) deja el foco en <body>: tampoco
  await page.click('#usuario');
  await page.keyboard.press('j');
  await page.keyboard.press('x');
  v.no_tras_un_clic_fuera = await sel() === 0 && await actual() === '12';
  // Con un diálogo abierto, tampoco
  await page.click('.grupo-coinc[data-clave="12"] .grupo-titulo');
  await page.check('.grupo-coinc[data-clave="12"] [data-sel]');
  await page.click('[data-sel-separar]');
  await page.waitForSelector('dialog[open] [data-si]', espera);
  await page.keyboard.press('u');
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => !document.querySelector('dialog[open]'), null, espera);
  v.no_con_un_dialogo = reg.posts.length === 0;
  // De vuelta en la vista, sí
  await page.click('.grupo-coinc[data-clave="13"] .grupo-titulo');
  await page.keyboard.press('x');
  v.en_la_vista_si = await page.$eval('.grupo-coinc[data-clave="13"] [data-sel]', (x) => x.checked);
  await ctx.close();
}

// ── dialogos: «Nuevo lugar» con algo escrito pregunta antes de cerrarse por Escape (sin nada, se cierra) ──
async function cDialogos(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso);
  await ingresar(page, '/calidad?p=lugares');
  await page.waitForSelector('#nuevo-lugar', espera);
  await page.click('#nuevo-lugar');
  await page.waitForSelector('dialog[open] #f-lugar', espera);
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => !document.querySelector('dialog[open]'), null, espera);
  await page.click('#nuevo-lugar');
  await page.waitForSelector('dialog[open] #f-lugar', espera);
  await page.fill('dialog[open] #f-lugar [name=nombre]', 'VEREDA INVENTADA');
  await page.keyboard.press('Escape');
  await page.waitForFunction(() => document.querySelectorAll('dialog[open]').length === 2, null, espera);
  d.titulos = await page.$$eval('dialog[open] h2', (x) => x.map((h) => h.textContent));
  v.pregunta = d.titulos.join('|') === 'Nuevo lugar|Confirmar';
  await page.getByRole('button', { name: 'Seguir escribiendo' }).click();
  await page.waitForFunction(() => document.querySelectorAll('dialog[open]').length === 1, null, espera);
  v.sigue_lo_escrito = await page.$eval('dialog[open] #f-lugar [name=nombre]', (x) => x.value) === 'VEREDA INVENTADA';
  await page.click('dialog[open] .pie [data-cerrar]');
  await page.waitForFunction(() => !document.querySelector('dialog[open]'), null, espera);
  await ctx.close();
}

// ── franja: con «Llamada sin registrar» a la vista, la barra de selección queda debajo de ella y se puede tocar ──
async function cFranja(nav, caso) {
  for (const [ancho, alto, movil] of [[1280, 600, false], [390, 844, true]]) {
    const op = movil ? { viewport: { width: ancho, height: alto }, isMobile: true, hasTouch: true, deviceScaleFactor: 2 } : { viewport: { width: ancho, height: alto } };
    const { ctx, page, v, d } = await abrir(nav, caso, op);
    await servirGrupos(ctx, gruposBase());
    await ingresar(page);
    await page.evaluate(() => sessionStorage.setItem('yj_llamada', JSON.stringify({ pid: 1, indice: 0, canal: 'llamada', t: Date.now() })));
    await ir(page, '/calidad?p=coincidencias');
    await page.waitForSelector('#franja-llamada', espera);
    await page.waitForSelector('.unificacion .grupo-coinc', espera);
    if (movil) await page.tap('.grupo-coinc[data-clave="12"] .sel-grupo');
    else await page.check('.grupo-coinc[data-clave="12"] [data-sel]');
    await page.waitForSelector('#barra-sel.con-seleccion', espera);
    // Bajar hasta el tercer grupo: la barra queda pegada arriba (escritorio) y la tarjeta, debajo de la barra
    await page.evaluate(() => document.querySelector('.grupo-coinc[data-clave="20-21"]').scrollIntoView({ block: 'start' }));
    const r = await medirEstable(page, () => {
      const caja = (s) => { const x = document.querySelector(s).getBoundingClientRect(); return { top: Math.round(x.top), bottom: Math.round(x.bottom), h: Math.round(x.height) }; };
      const unir = document.querySelector('[data-sel-unir]').getBoundingClientRect();
      const tocado = document.elementFromPoint(unir.left + unir.width / 2, unir.top + unir.height / 2);
      return { franja: caja('#franja-llamada'), barra: caja('#barra-sel'), tarjeta: caja('.grupo-coinc[data-clave="20-21"]'),
        pos: getComputedStyle(document.querySelector('#barra-sel')).position, alto: innerHeight, unir_a_la_mano: !!tocado?.closest('[data-sel-unir]') };
    });
    d[movil ? 'movil' : 'escritorio'] = r;
    if (movil) {
      // Fija abajo y de su alto (no estirada desde la franja hasta el fondo)
      v.movil_barra_abajo = r.pos === 'fixed' && Math.abs(r.barra.bottom - r.alto) <= 1 && r.barra.top > r.franja.bottom && r.barra.h < r.alto / 3 && r.unir_a_la_mano;
    } else {
      v.barra_debajo_de_la_franja = r.pos === 'sticky' && r.barra.top >= r.franja.bottom && r.barra.top <= r.franja.bottom + 40 && r.unir_a_la_mano;
      v.tarjeta_debajo_de_la_barra = r.tarjeta.top >= r.barra.bottom;
    }
    await captura(page, `franja-${ancho}x${alto}`);
    await ctx.close();
  }
}

// ══ Con la unión de verdad (conjunto «real»): sin `route.fulfill` para los grupos, como lo reprodujo la verificación ══

// ── atajos-recarga: con el asistente abierto no corren, tampoco cuando él recarga la vista o lleva a ella ──
async function cAtajosRecarga(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso);
  // Nada se une de verdad: si un atajo corriera, el lote queda anotado y se contesta como fallido
  const lotes = [];
  await ctx.route((u) => u.pathname === pref + '/api/coincidencias/lote', (route) => {
    const b = route.request().postDataJSON();
    lotes.push(b);
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ resultados: b.grupos.map(() => ({ ok: false,
      decision: b.decision, codigo: 'cambio', error: 'simulado' })), unidas: 0, separadas: 0, errores: b.grupos.length }) });
  });
  await abrirCoincidencias(page);
  // Lo que «j», «u» o «x» dejan en el acto (sus manejadores no esperan nada): un grupo actual, uno enviándose o seleccionado
  const huella = () => page.evaluate(() => ({ actual: document.querySelectorAll('.grupo-coinc.actual').length,
    enviando: document.querySelectorAll('.grupo-coinc.enviando').length, sel: document.querySelectorAll('.grupo-coinc [data-sel]:checked').length }));
  await page.click('#agente-boton');
  await page.waitForSelector('#agente-panel:not([hidden])', espera);
  // Como agente.js: recargar() es ir(rutaActual() + location.search, { reemplazar: true }) y navegar(), ir(ruta)
  const comoElAsistente = async (ruta, op) => {
    const n = await page.evaluate(() => window.__vistas.length);
    await page.evaluate(async ([r, o]) => (await import(new URL('app.js', document.querySelector('script[type=module]').src).href)).ir(r, o), [ruta, op]);
    await page.waitForFunction((n) => window.__vistas.length > n, n, espera);
  };
  d.pasos = {};
  for (const [paso, desde, op] of [['recargar', null, { reemplazar: true }], ['navegar', '/personas', {}]]) {
    if (desde) await comoElAsistente(desde, {});
    // Un clic en el título del panel: no toma el foco (queda en <body>)
    await page.click('#agente-panel .agente-titulos h2');
    const focoClic = await page.evaluate(() => document.activeElement?.tagName);
    await comoElAsistente('/calidad?p=coincidencias', op);
    await page.waitForSelector('.unificacion .grupo-coinc', espera);
    const antes = await page.evaluate(() => ({ panel: !document.querySelector('#agente-panel').hidden,
      foco: `${document.activeElement?.tagName}#${document.activeElement?.id}` }));
    // Quien sigue escribiéndole al asistente
    await page.keyboard.type('ju');
    d.pasos[paso] = { focoClic, ...antes, ...(await huella()) };
    // El caso de la verificación: el panel sigue abierto y el foco pasó a la vista
    v[`${paso}_deja_el_panel_abierto_y_el_foco_en_la_vista`] = focoClic === 'BODY' && antes.panel && antes.foco === 'MAIN#vista';
    v[`${paso}_sin_atajos`] = !d.pasos[paso].actual && !d.pasos[paso].enviando && !d.pasos[paso].sel;
  }
  // Cerrado el asistente, en la vista sí corren
  await page.click('#agente-cerrar');
  await page.waitForFunction(() => document.querySelector('#agente-panel')?.hidden, null, espera);
  await page.click('.grupo-coinc .grupo-titulo');
  await page.keyboard.press('x');
  d.cerrado = await huella();
  v.cerrado_si = d.cerrado.sel === 1;
  d.lotes = lotes;
  v.ningun_lote = lotes.length === 0;
  await ctx.close();
}

// ── pagina26: con 26 muy probables, resolver el primero deja el texto de la paginación de acuerdo con «Siguiente» ──
async function cPagina26(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso);
  await abrirCoincidencias(page, '&nivel=alta');
  const pag = () => page.evaluate(() => ({ texto: document.querySelector('.unificacion [data-pagina-texto]')?.textContent ?? null,
    siguiente: document.querySelector('.unificacion [data-siguiente]')?.disabled ?? null,
    tarjetas: document.querySelectorAll('.grupo-coinc:not(.resuelta)').length, cuenta: document.querySelector('#cuenta-grupos')?.textContent ?? null }));
  // «Página n de m» con «Siguiente» activo si y solo si m > n
  const deAcuerdo = (x) => { const m = /^Página (\d+) de (\d+)$/.exec(x.texto || ''); return !!m && (x.siguiente === false) === (Number(m[2]) > Number(m[1])); };
  d.antes = await pag();
  v.antes = d.antes.texto === 'Página 1 de 2' && d.antes.siguiente === false && d.antes.tarjetas === 25 && deAcuerdo(d.antes);
  const primero = await page.$eval('.grupo-coinc', (x) => x.dataset.clave);
  const respuesta = page.waitForResponse((r) => new URL(r.url()).pathname === pref + '/api/coincidencias/lote', espera);
  await page.click(`.grupo-coinc[data-clave="${primero}"] [data-unir]`);
  d.lote = await (await respuesta).json();
  v.unio_de_verdad = d.lote.unidas === 1;
  await page.waitForFunction(() => document.querySelectorAll('.grupo-coinc').length === 24, null, espera);
  d.tras_unir = await pag();
  v.tras_unir = d.tras_unir.texto === 'Página 1 de 2' && d.tras_unir.siguiente === false && d.tras_unir.tarjetas === 24
    && /^25 grupos /.test(d.tras_unir.cuenta) && deAcuerdo(d.tras_unir);
  // «Siguiente» completa la página: ahora caben todos en una y la paginación se va
  await page.click('.unificacion [data-siguiente]');
  await page.waitForFunction(() => document.querySelectorAll('.grupo-coinc').length === 25 && !document.querySelector('.unificacion .paginacion'), null, espera);
  d.tras_siguiente = await pag();
  v.tras_siguiente = d.tras_siguiente.texto === null && d.tras_siguiente.tarjetas === 25;
  await ctx.close();
}

// ── edad: conservar la ficha B rehace la vista previa en el navegador; «Es la misma persona» une de verdad ──
async function cEdad(nav, caso) {
  const { ctx, page, v, d } = await abrir(nav, caso);
  await ingresar(page);
  // La celda «Quedaría» de una fila: el valor que queda, su fuente, la ficha de donde sale y lo que pasa a alternos
  const celda = (fila) => page.evaluate((f) => {
    const t = document.querySelector('.grupo-coinc');
    const c = t.querySelector(`tr[data-fila="${f}"] td.quedaria`);
    const p = c.querySelector('.pieza');
    return { valor: p ? [...p.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join('').trim() : null,
      fuente: p?.querySelector(':scope > .fuente')?.dataset.fuente ?? null, de: p?.querySelector('.de-ficha')?.textContent.replace('de la ficha ', '') ?? null,
      pasan: c.querySelector('.pasan')?.title ?? null, cabeza: t.querySelector('thead .quedaria').textContent.replace(/\s+/g, ' ').trim() };
  }, fila);
  d.casos = {};
  for (const x of D.vista) {
    await ir(page, `/calidad?p=coincidencias&persona=${x.a}`);
    await page.waitForSelector('.unificacion .grupo-coinc', espera);
    const servidor = await celda(x.fila);
    // `tambien`: otra fila del mismo par (la dirección, que pasa con la ubicación)
    const servidorTambien = x.tambien ? await celda(x.tambien) : null;
    await page.check(`.grupo-coinc [data-conservar][value="${x.b}"]`);
    await page.waitForFunction(() => document.querySelector('.grupo-coinc thead .quedaria')?.textContent.includes('estimado con su elección'), null, espera);
    const estimada = await celda(x.fila);
    const estimadaTambien = x.tambien ? await celda(x.tambien) : null;
    const respuesta = page.waitForResponse((r) => new URL(r.url()).pathname === pref + '/api/coincidencias/lote', espera);
    await page.click('.grupo-coinc [data-unir]');
    const r = await respuesta;
    d.casos[x.clave] = { servidor, estimada, servidor_tambien: servidorTambien, estimada_tambien: estimadaTambien,
      post: r.request().postDataJSON(), lote: await r.json() };
    v[`${x.clave}_servidor`] = servidor.cabeza.startsWith('Quedaría Se conserva la ficha A') && !servidor.cabeza.includes('estimado');
    v[`${x.clave}_estimada`] = estimada.cabeza.startsWith('Quedaría Se conserva la ficha B · estimado con su elección');
    v[`${x.clave}_unida`] = d.casos[x.clave].lote.unidas === 1;
  }
  await ctx.close();
}

(async () => {
  const nav = await chromium.launch();
  const casos = [];
  // Los casos con la unión de verdad van en su propio conjunto (otro panel y otra base): cada uno corre solo en el suyo
  const REALES = new Set(['atajos-recarga', 'pagina26', 'edad']);
  const correr = async (nombre, f) => {
    if (REALES.has(nombre) !== (conjunto === 'real')) return;
    const caso = { nombre, revisiones: {}, datos: {}, errores: [], csp: [] };
    casos.push(caso);
    try { await f(caso); } catch (e) { caso.fallo = String(e && e.stack || e).slice(0, 2000); }
  };
  try {
    await correr('render', (c) => cRender(nav, c));
    await correr('excluir', (c) => cExcluir(nav, c));
    await correr('seleccion', (c) => cSeleccion(nav, c));
    await correr('masivo', (c) => cMasivo(nav, c));
    await correr('detener', (c) => cDetener(nav, c));
    await correr('atajos', (c) => cAtajos(nav, c));
    for (const [a, h] of [[820, 1180], [390, 844], [320, 568]]) await correr(`movil-${a}x${h}`, (c) => cMovil(nav, c, a, h));
    await correr('oscuro', (c) => cOscuro(nav, c));
    await correr('ficha', (c) => cFicha(nav, c));
    await correr('marcas', (c) => cMarcas(nav, c));
    await correr('persona', (c) => cPersona(nav, c));
    await correr('paginacion', (c) => cPaginacion(nav, c));
    await correr('paginacion-en-curso', (c) => cPaginacionEnCurso(nav, c));
    await correr('lugar', (c) => cLugar(nav, c));
    await correr('url', (c) => cUrl(nav, c));
    await correr('atajos-fuera', (c) => cAtajosFuera(nav, c));
    await correr('dialogos', (c) => cDialogos(nav, c));
    await correr('franja', (c) => cFranja(nav, c));
    // En este orden: los atajos no unen nada (el lote se contesta aquí), «pagina26» cuenta los 26 y une uno, y los pares
    // de la vista previa (que no son muy probables) se filtran por su ficha
    await correr('atajos-recarga', (c) => cAtajosRecarga(nav, c));
    await correr('pagina26', (c) => cPagina26(nav, c));
    await correr('edad', (c) => cEdad(nav, c));
  } finally {
    await nav.close();
  }
  console.log(JSON.stringify({ casos }));
})().catch((e) => { console.error(e); process.exit(1); });
"""
