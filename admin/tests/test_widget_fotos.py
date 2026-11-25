"""Las fotos de planillas físicas en el cuadro de escribir del asistente (web/js/agente.js y css/agente.css), sin
navegador: lo que se calcula (con Node) y lo que el código tiene que cumplir.

* Lo que se calcula: los topes que da el estado (`adjuntos`, o null sin la forma esperada), a qué tamaño se reduce una
  foto (nunca se agranda), las calidades JPEG que se prueban antes de achicarla, la luz y la nitidez de una copia chica
  (varianza del laplaciano) y los avisos (pequeña, oscura, movida).
* La cámara con capture="environment", la galería con `multiple`; el aviso fijo junto a los botones; las fotos se
  preparan de a una (bitmap.close()), se abren derechas (EXIF), se vuelven a codificar en un canvas (sin EXIF ni GPS)
  y su miniatura es un canvas (nunca `.src =`); se suben crudas con `api.subir` a la bandeja de planillas; el mensaje
  lleva sus ids como un `adjuntos` aparte (sin tocar lo que fijan test_voz_clonada.py y test_dictado.py); «Reintentar»
  y «Nueva conversación» las conservan; al repintar, el chip; nada va al almacenamiento del navegador.
* Las rutas de la bandeja que usa (POST /api/planillas/fotos, DELETE /api/planillas/{id}) existen en la API.
La prueba con Chromium (fotos de verdad, subida simulada) está en test_widget_navegador.py. Solo datos inventados.
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
CSS = (RAIZ / "web" / "css" / "agente.css").read_text(encoding="utf-8")
UI = (JS / "ui.js").read_text(encoding="utf-8")
AVISO = ("Solo planillas o listas. No fotografíe cédulas. Tape columnas de salud, etnia, víctima o políticas. Borre "
         "la foto del teléfono.")

requiere_node = pytest.mark.skipif(shutil.which("node") is None, reason="sin Node para cargar web/js/agente.js")


def _sin_comentarios(texto: str) -> str:
    return "\n".join("" if l.lstrip().startswith(("//", "*", "/*")) else l for l in texto.splitlines())


def _funcion(texto: str, nombre: str) -> str:
    """El cuerpo de `function nombre(…) {…}` (o `async function`), hasta la llave que lo cierra."""
    m = re.search(rf"(?:async\s+)?function\s+{nombre}\s*\([^)]*\)\s*\{{", texto)
    assert m, nombre
    nivel, i = 1, m.end()
    while nivel:
        nivel += {"{": 1, "}": -1}.get(texto[i], 0)
        i += 1
    return texto[m.end():i - 1]


CODIGO = _sin_comentarios(AGENTE)


# ───────────────────────────── Lo que se calcula, con Node ─────────────────────────────

NODE = r"""
globalThis.document = { querySelector: () => null, documentElement: {} };
globalThis.MutationObserver = class { observe() {} };
globalThis.window = globalThis;
globalThis.addEventListener ||= () => {};
const m = await import('./web/js/agente.js');
const { limites, medidas, calidades } = JSON.parse(process.argv[1]);
// Imágenes inventadas de 160 × 120: una planilla nítida (trazos de letra de 1 px en renglones cada 14 px y la
// cuadrícula cada 40), la misma muy borrosa (dos pasadas de un promedio de 7 × 7), la misma oscura, blanco liso y negro
const W = 160, H = 120;
const imagen = (f) => { const d = new Uint8ClampedArray(W * H * 4); for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
  const v = f(x, y); const i = (y * W + x) * 4; d[i] = d[i + 1] = d[i + 2] = v; d[i + 3] = 255; } return d; };
let semilla = 7;
const azar = () => (semilla = (semilla * 16807) % 2147483647) / 2147483647;
const tinta = new Set();
for (let r = 4; r < H; r += 14) for (let x = 2; x < W - 2; x++) if (azar() < 0.35) for (let k = 0; k < 7; k++) if (azar() < 0.5) tinta.add((r + k) * W + x);
const planilla = (x, y) => (tinta.has(y * W + x) || x % 40 === 0 || y % 40 === 0 ? 30 : 230);
const promedio = (f, r) => { const d = imagen((x, y) => { let s = 0, n = 0; for (let dy = -r; dy <= r; dy++) for (let dx = -r; dx <= r; dx++) {
  s += f(Math.min(W - 1, Math.max(0, x + dx)), Math.min(H - 1, Math.max(0, y + dy))); n++; } return s / n; });
  return (x, y) => d[(y * W + x) * 4]; };
const luz = {
  nitida: m.revisarLuz(imagen(planilla), W, H),
  borrosa: m.revisarLuz(imagen(promedio(promedio(planilla, 3), 3)), W, H),
  oscura: m.revisarLuz(imagen((x, y) => planilla(x, y) * 0.25), W, H),
  blanca: m.revisarLuz(imagen(() => 255), W, H),
  negra: m.revisarLuz(imagen(() => 0), W, H),
  sin_datos: m.revisarLuz(new Uint8ClampedArray(10), W, H),
};
const avisos = Object.fromEntries(Object.entries(luz).map(([k, v]) => [k, m.avisosFoto({ ladoOriginal: 3000, ...v })]));
console.log(JSON.stringify({
  limites: limites.map((a) => m.limitesFotos(a)),
  medidas: medidas.map(([a, b, l]) => m.medidasFoto(a, b, l)),
  calidades: calidades.map((q) => m.pasosCalidad(q)),
  luz, avisos,
  pequena: m.avisosFoto({ ladoOriginal: 1599, ...luz.nitida }),
  justa: m.avisosFoto({ ladoOriginal: 1600, ...luz.nitida }),
}));
"""

ESTADO = {"max_por_mensaje": 4, "lado_max": 2576, "calidad": 0.8, "max_bytes": 1500000}


@requiere_node
def test_lo_que_se_calcula_de_las_fotos():
    limites = [
        ESTADO, {**ESTADO, "lado_max": 2000},
        None, [], "si", {}, {**ESTADO, "max_por_mensaje": 0}, {**ESTADO, "max_por_mensaje": 4.5},
        {**ESTADO, "lado_max": 100}, {**ESTADO, "calidad": "0.8"}, {**ESTADO, "calidad": 2},
        {**ESTADO, "max_bytes": None},
        {**ESTADO, "max_por_mensaje": True},
    ]
    medidas = [[4000, 3000, 2576], [3000, 4000, 2000], [1200, 900, 2576], [2576, 10, 2576], [1, 1, 400],
               [5000, 5000, 400]]
    calidades = [0.8, 0.5, 0.95, 0.3]
    r = subprocess.run(["node", "--input-type=module", "-e", NODE,
                        json.dumps({"limites": limites, "medidas": medidas, "calidades": calidades})],
                       cwd=RAIZ, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-3000:]
    s = json.loads(r.stdout)
    # Los topes del estado: solo con la forma que da el servidor (enteros, calidad numérica); si no, sin cámara
    assert s["limites"][:2] == [{"maxPorMensaje": 4, "ladoMax": 2576, "calidad": 0.8, "maxBytes": 1500000},
                                {"maxPorMensaje": 4, "ladoMax": 2000, "calidad": 0.8, "maxBytes": 1500000}]
    assert s["limites"][2:] == [None] * (len(limites) - 2)
    # Se reduce hasta el lado mayor del estado (con la proporción), nunca se agranda
    assert s["medidas"] == [{"ancho": 2576, "alto": 1932, "escala": 0.644},
                            {"ancho": 1500, "alto": 2000, "escala": 0.5}, {"ancho": 1200, "alto": 900, "escala": 1},
                            {"ancho": 2576, "alto": 10, "escala": 1}, {"ancho": 1, "alto": 1, "escala": 1},
                            {"ancho": 400, "alto": 400, "escala": 0.08}]
    # La calidad del estado y, si pesa más de max_bytes, de a 0,1 hasta 0,5
    assert s["calidades"] == [[0.8, 0.7, 0.6, 0.5], [0.5], [0.95, 0.85, 0.75, 0.65, 0.55], [0.3]]
    luz = s["luz"]
    # Brillo: la luminancia media; nitidez: la varianza del laplaciano (alta con bordes de letra, baja si está movida)
    assert luz["blanca"] == {"brillo": 255, "nitidez": 0} and luz["negra"] == {"brillo": 0, "nitidez": 0}
    assert luz["sin_datos"] == {"brillo": 0, "nitidez": 0}
    assert luz["nitida"]["brillo"] > 150 and luz["nitida"]["nitidez"] > 1000
    assert luz["borrosa"]["nitidez"] < 40 < luz["nitida"]["nitidez"]
    assert luz["oscura"]["brillo"] < 70
    assert s["avisos"] == {"nitida": [], "borrosa": ["movida"], "oscura": ["oscura"], "blanca": ["movida"],
                           "negra": ["oscura"], "sin_datos": ["oscura"]}
    # Pequeña: el lado mayor original por debajo de 1 600 px
    assert s["pequena"] == ["pequena"] and s["justa"] == []


# ───────────────────────────── La cámara, la galería y el aviso ─────────────────────────────

def test_camara_galeria_y_aviso_fijo():
    plantilla = AGENTE[AGENTE.index('<form id="agente-form"'):AGENTE.index("</form>")]
    camara = re.search(r'<input type="file" id="agente-foto-camara-in"[^>]*>', plantilla).group(0)
    galeria = re.search(r'<input type="file" id="agente-foto-galeria-in"[^>]*>', plantilla).group(0)
    assert 'capture="environment"' in camara and 'accept="image/*"' in camara and "multiple" not in camara
    assert "multiple" in galeria and 'accept="image/*"' in galeria and "capture" not in galeria
    # Los botones: el de la cámara del cuadro de escribir (oculto hasta que el estado lo ofrezca) y los de la bandeja
    assert ('<button type="button" class="btn agente-adjuntar" id="agente-adjuntar" aria-label="Adjuntar fotos de '
            'planillas" title="Adjuntar fotos de planillas" aria-expanded="false" aria-controls="agente-fotos" hidden>'
            "${icono('camara')}") in plantilla
    assert "${icono('camara')}<span>Tomar foto</span>" in plantilla
    assert "${icono('galeria')}<span>Elegir de la galería</span>" in plantilla
    for nombre in ("camara", "galeria", "girar"):
        assert re.search(rf"^\s*{nombre}:\s*'<", UI, re.M), nombre
    # El aviso fijo, junto a los botones (la bandeja lo nombra)
    assert re.sub(r"'\s*\+\s*'", "", re.search(r"const AVISO_FOTOS = (.*?);\n", AGENTE, re.S).group(1)) == f"'{AVISO}'"
    assert ('<div class="agente-fotos" id="agente-fotos" role="group" aria-labelledby="agente-fotos-aviso" '
            'hidden>') in plantilla
    assert "$('#agente-fotos-aviso > span').textContent = AVISO_FOTOS;" in CODIGO
    # Se ofrece solo con `adjuntos` en el estado (el rol sube fotos de planillas) y un navegador que las prepara
    assert "adjuntos: limitesFotos(o.adjuntos)," in CODIGO
    assert "const puedeFotos = () => !!info?.disponible && !!info.adjuntos && soporteFotos;" in CODIGO
    assert "aplicarFotos();" in _funcion(CODIGO, "aplicarEstado")
    # Topes de la galería: las que caben en el mensaje
    agregar = _funcion(CODIGO, "agregarFotos")
    assert "archivos.slice(0, Math.max(0, lim.maxPorMensaje - fotos.length))" in agregar
    # Los selectores se vacían tras elegir (la misma foto se puede volver a elegir)
    assert "entradaFoto.value = '';" in CODIGO


def test_las_fotos_se_preparan_de_a_una_y_sin_metadatos():
    # De a una: la cola, y la imagen abierta se cierra en cuanto deja de servir
    assert "colaPreparar = colaPreparar.then(() => preparar(f, archivo));" in CODIGO
    assert "colaSubir = colaSubir.then(() => subirAhora(f));" in CODIGO
    preparar = _funcion(CODIGO, "prepararImagen")
    assert preparar.count("bmp.close();") == 2 and "c.width = c.height = 0;" in preparar
    assert "const luz = medirLuz(bmp);" in preparar and "medidasFoto(bmp.width, bmp.height, lim.ladoMax)" in preparar
    assert "avisosFoto({ ladoOriginal, ...luz })" in preparar and "dibujarMiniatura(mini, c);" in preparar
    # Derecha según su EXIF, y vuelta a codificar en un canvas como JPEG (no sale nada de lo que traía el archivo)
    assert "createImageBitmap(fuente, { imageOrientation: 'from-image' })" in _funcion(CODIGO, "abrirImagen")
    assert "c.toBlob(listo, 'image/jpeg', calidad)" in CODIGO
    codificar = _funcion(CODIGO, "codificar")
    assert "for (const q of pasosCalidad(lim.calidad)) {" in codificar and "b.size <= lim.maxBytes" in codificar
    # Girar: 90° a la derecha, en un canvas con los lados cambiados
    girar = _funcion(CODIGO, "girarImagen")
    assert "lienzo(bmp.height, bmp.width)" in girar and "ctx.rotate(Math.PI / 2);" in girar and "bmp.close();" in girar
    # Las miniaturas, en canvas: ni `.src =`, ni URL.createObjectURL, ni <img>
    assert not re.search(r"\.src\s*=|setAttribute\(\s*['\"]src|createObjectURL|createElement\('img'\)|new Image\(",
                         CODIGO)
    assert "const mini = document.createElement('canvas');" in _funcion(CODIGO, "crearItem")
    # Nada de las fotos va al almacenamiento del navegador (solo el id de la conversación, como siempre)
    assert "localStorage" not in AGENTE and "indexedDB" not in AGENTE
    assert CODIGO.count("sessionStorage.setItem(") == 1
    assert "JSON.stringify({ abierto, conversacion: conv, uid: sesion.uid, hablar })" in CODIGO


def test_la_subida_y_el_mensaje():
    assert "const RUTA_FOTOS = '/api/planillas/fotos';" in CODIGO
    assert "const rutaFoto = (id) => `/api/planillas/${encodeURIComponent(id)}`;" in CODIGO
    subir = _funcion(CODIGO, "subirAhora")
    assert ("api.subir(RUTA_FOTOS, f.blob, { cabeceras: { 'Content-Type': 'image/jpeg' },\n"
            "        timeout: ESPERA_FOTO_MS, signal: f.control.signal })") in subir
    # El id que da la bandeja va en la ruta al borrar: solo letras, números, - y _
    assert "const ID_FOTO = /^[A-Za-z0-9_-]{1,64}$/;" in CODIGO and "ID_FOTO.test(d.id)" in subir
    assert "api.del(rutaFoto(id))" in CODIGO
    # Quitar o girar una foto que no llegó en un mensaje la borra de la bandeja; una que sí llegó, no
    assert "if (f.id && !f.enviada) borrarDeLaBandeja(f.id);" in _funcion(CODIGO, "quitarFoto")
    assert "if (f.id && !f.enviada) borrarDeLaBandeja(f.id);" in CODIGO[CODIGO.index("function girarFoto(f) {"):]
    assert "if (t.inicio) for (const f of t.fotos || []) f.enviada = true;" in _funcion(CODIGO, "cerrarTurno")
    # El mensaje: los ids como un `adjuntos` aparte (las subcadenas que fijan test_voz_clonada.py y test_dictado.py
    # siguen enteras), y un mensaje puede ser solo fotos
    enviar = _funcion(CODIGO, "enviar")
    assert "if (!t && !adjuntas.length) return;" in enviar
    assert "const conFotos = ids.length ? { adjuntos: ids } : {};" in enviar
    assert "await correr('/api/agente/mensajes', { ...cuerpo, ...conFotos }, { ...datos, fotos: adjuntas });" in enviar
    assert "{ tipo: 'mensaje', texto: t, burbuja, msj: actual.el, sinAprobar, hablar: leer || sala, sala }" in enviar
    assert "contexto: contexto({ voz: leer, vozAdelanto: sala })" in enviar
    assert enviar.index("soltarFotos(adjuntas);") < enviar.index("await correr(")
    # Desde el cuadro: con una foto que falló no se envía; con fotos subiendo, sale sola al terminar
    compositor = _funcion(CODIGO, "enviarDelCompositor")
    assert "if ((!t.trim() && !fotos.length) || turno || cargando || !info?.disponible) return;" in compositor
    assert compositor.index("f.estado === 'error'") < compositor.index("enviarAlSubir = { voz: vozEntregando };") \
        < compositor.index("enviar(t, { fotos: fotos.slice() });")
    assert "try { enviarDelCompositor(); } finally { vozEntregando = false; }" in _funcion(CODIGO, "revisarEnvio")
    # «Reintentar» y «Nueva conversación» las conservan
    cerrar = _funcion(CODIGO, "cerrarTurno")
    assert "enviar(t.texto, { reusar, fotos: t.fotos });" in cerrar and "if (traer) devolverFotos(t.fotos);" in cerrar
    # Con fotos en el cuadro, una sesión vencida abre el ingreso en un diálogo (no se pierden al recargar)
    assert "const conAlgo = () => !!entrada.value.trim() || fotos.length > 0 || !!turno;" in CODIGO
    # Sin asistente (la cuenta quedó pendiente), las fotos salen de la memoria
    assert "vaciarFotos();" in _funcion(CODIGO, "ocultar")


def test_al_repintar_el_chip_de_las_fotos():
    repintar = _funcion(CODIGO, "pintarConversacion")
    assert ("const conFotos = m?.rol === 'usuario' && Array.isArray(m.adjuntos) ? Math.min(m.adjuntos.length, 20) : 0;"
            in repintar)
    assert ("if (m?.rol === 'usuario' && (texto(m.texto) || conFotos)) { agregarUsuario(texto(m.texto), conFotos); "
            "continue; }") in repintar
    usuario = _funcion(CODIGO, "agregarUsuario")
    # El texto sigue en un <p> (las pruebas del navegador lo buscan ahí) y el chip va aparte, arriba
    assert "if (n > 0) m.append(chipFotos(n, Array.isArray(adjuntas) ? adjuntas : []));" in usuario
    assert usuario.index("chipFotos(") < usuario.index("if (t) m.append(el('p', null, t));")
    chip = _funcion(CODIGO, "chipFotos")
    assert "el('div', 'agente-fotos-chip')" in chip and "ico('camara')" in chip
    assert "n === 1 ? '1 foto adjunta' : `${num(n)} fotos adjuntas`" in chip


def test_estilos_de_las_fotos():
    for regla in (".btn.agente-adjuntar {", ".agente-adjuntar-n {", ".agente-fotos {", ".agente-fotos-aviso {",
                  ".agente-foto {", ".agente-foto-mini {", ".agente-fotos-chip {", ".agente-grafico {",
                  ".agente-fotos[hidden] { display: none; }", ".agente-foto-reintentar[hidden] { display: none; }"):
        assert regla in CSS, regla
    # La bandeja se desplaza sola si crece (en un celular bajo no tapa la conversación)
    assert re.search(r"\.agente-fotos \{[^}]*overflow-y: auto", CSS)


# ───────────────────────────── Las rutas de la bandeja existen ─────────────────────────────

def test_las_rutas_de_la_bandeja_que_usa_el_widget_existen():
    """El widget sube a POST /api/planillas/fotos y borra con DELETE /api/planillas/{id} (la bandeja de planillas,
    app/api/planillas.py). Mientras ese router no tenga rutas (se construye en paralelo), se salta."""
    from app.main import crear_app
    rutas = [(r.path, r.methods) for r in crear_app().routes
             if isinstance(r, APIRoute) and r.path.startswith("/api/planillas")]
    if not rutas:
        pytest.skip("app/api/planillas.py todavía no registra rutas")
    assert any(p == "/api/planillas/fotos" and "POST" in m for p, m in rutas), rutas
    assert any(re.fullmatch(r"/api/planillas/\{[a-z_]+\}", p) and "DELETE" in m for p, m in rutas), rutas
