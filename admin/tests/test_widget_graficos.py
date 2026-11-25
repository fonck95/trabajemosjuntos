"""Los gráficos del asistente en el chat (web/js/agente-graficos.js), sin navegador: con Node y un DOM mínimo.

* El contrato es el mismo de los dos lados: clases, topes y caracteres que se quitan (app/agente/grafico.py). Lo que el
  servidor descarta (clase desconocida, sin título, sin ítems válidos) el navegador tampoco lo dibuja, y de lo que sí
  dibuja salen los mismos títulos y los mismos ítems, en el mismo orden.
* Nada del gráfico se pinta como HTML: el título y la nota van por textContent y lo demás por `html` de ui.js (que
  escapa); un `color` que traiga el ítem no se usa (los colores salen solo de la paleta `SERIES`).
* Cada clase se dibuja con graficos.js: barras, columnas (que pasan a barras si no caben), la barra apilada (con una
  parte «Otras» si hay más partes que colores) y la serie en el tiempo (que generaliza `serieMensual`: cualquier
  periodo, con su globo por punto).
* agente.js solo lo carga con el primer gráfico (graficos.js toca `document` al importarse) y lo pone debajo del chip
  de su herramienta, en vivo y al repintar.
La prueba con Chromium está en test_widget_navegador.py. Solo datos inventados.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.agente import grafico

RAIZ = Path(__file__).resolve().parents[1]
JS = RAIZ / "web" / "js"
MODULO = (JS / "agente-graficos.js").read_text(encoding="utf-8")
AGENTE = (JS / "agente.js").read_text(encoding="utf-8")

requiere_node = pytest.mark.skipif(shutil.which("node") is None,
                                   reason="sin Node para cargar web/js/agente-graficos.js")


def _sin_comentarios(texto: str) -> str:
    return "\n".join("" if l.lstrip().startswith(("//", "*", "/*")) else l for l in texto.splitlines())


# Un DOM mínimo: lo que usan agente-graficos.js (createElement, append, textContent, dataset, setAttribute, className)
# y montar() de ui.js (innerHTML). graficos.js pone sus escuchas del globo en `document` al importarse
NODE = r"""
class Nodo {
  constructor(tag) { this.tag = tag; this.hijos = []; this.atributos = {}; this.dataset = {}; this.className = '';
    this._texto = ''; this.innerHTML = ''; }
  append(...xs) { this.hijos.push(...xs); }
  setAttribute(k, v) { this.atributos[k] = String(v); }
  set textContent(v) { this._texto = String(v); }
  get textContent() { return this._texto; }
}
const escuchas = [];
globalThis.document = { createElement: (t) => new Nodo(t), addEventListener: (t) => escuchas.push(t),
  querySelector: () => null, documentElement: {}, body: { append() {} } };
globalThis.innerWidth = 1280;
const m = await import('./web/js/agente-graficos.js');
const plano = (n) => (n instanceof Nodo
  ? { tag: n.tag, clase: n.className, dataset: n.dataset, atributos: n.atributos, texto: n.textContent, html: n.innerHTML,
    hijos: n.hijos.map(plano) }
  : n);
const casos = JSON.parse(process.argv[1]);
console.log(JSON.stringify({ exportados: Object.keys(m).sort(), escuchas,
  dibujos: casos.map((a) => { const f = m.pintarGrafico(a); return f ? plano(f) : null; }) }));
"""


def _pintar(casos: list) -> dict:
    r = subprocess.run(["node", "--input-type=module", "-e", NODE, json.dumps(casos, ensure_ascii=False)], cwd=RAIZ,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-3000:]
    return json.loads(r.stdout)


def _partes(fig: dict) -> dict:
    """{titulo, unidad, html (el dibujo), cifras (el texto para lectores de pantalla), nota} de un <figure>."""
    cab, cuerpo, cifras, *resto = fig["hijos"]
    assert cab["tag"] == "figcaption" and cuerpo["clase"] == "agente-grafico-cuerpo" and cifras["clase"] == "sr"
    titulo = cab["hijos"][0]
    unidad = cab["hijos"][2]["texto"] if len(cab["hijos"]) == 3 else ""
    nota = resto[0]["texto"] if resto else None
    if resto:
        assert resto[0]["clase"] == "agente-grafico-nota"
    return {"titulo": titulo["texto"], "unidad": unidad, "html": cuerpo["html"], "cifras": cifras["texto"],
            "nota": nota}


def _items(n: int, **extra) -> list[dict]:
    return [{"etiqueta": f"Vereda inventada {i}", "valor": i * 3 + 1, **extra} for i in range(n)]


# ───────────────────────────── El contrato, igual de los dos lados ─────────────────────────────

def test_el_contrato_es_el_del_servidor():
    codigo = _sin_comentarios(MODULO)
    clases = re.search(r"const CLASES = new Set\(\[([^\]]*)\]\);", codigo).group(1)
    assert tuple(re.findall(r"'(\w+)'", clases)) == grafico.CLASES
    assert f"const MAX_ITEMS = {grafico.MAX_ITEMS};" in codigo
    topes = re.search(r"const TITULO_MAX = (\d+), UNIDAD_MAX = (\d+), ETIQUETA_MAX = (\d+), TEXTO_MAX = (\d+), "
                      r"NOTA_MAX = (\d+);", codigo)
    assert tuple(map(int, topes.groups())) == (grafico.TITULO_MAX, grafico.UNIDAD_MAX, grafico.ETIQUETA_MAX,
                                               grafico.TEXTO_MAX, grafico.NOTA_MAX)
    # Los mismos caracteres que quita el servidor (escritos con escapes: un U+2028 literal rompe la expresión)
    control = re.search(r"const CONTROL = /\[(.*?)\]/g;", codigo).group(1)
    assert control == grafico._CONTROL.pattern[1:-1].encode("ascii", "backslashreplace").decode().replace(
        "\\x00", "\\u0000").replace("\\x1f", "\\u001f").replace("\\x7f", "\\u007f").replace("\\x9f", "\\u009f")
    # Una sola función exportada, que dibuja con graficos.js y monta con ui.js
    assert re.findall(r"^export\s+(?:async\s+)?(?:function|const|let|class)\s+(\w+)", codigo, re.M) == ["pintarGrafico"]
    assert "import { SERIES, apilada, barras, columnas } from './graficos.js';" in codigo
    # Sin HTML a mano: ni innerHTML, ni crudo, ni insertAdjacentHTML (montar() de ui.js con una plantilla `html`)
    for prohibido in ("innerHTML", "crudo", "insertAdjacentHTML", "outerHTML", ".src", "localStorage", "style="):
        assert prohibido not in codigo, prohibido


@requiere_node
def test_valida_lo_mismo_que_el_servidor():
    """Cada entrada, por los dos lados: lo que el servidor descarta no se dibuja; de lo demás, el mismo título, los
    mismos ítems (etiqueta y valor) en el mismo orden, la misma unidad y la misma nota."""
    raro = "​Ve‮reda  nueva﻿\x07"
    casos = [
        {"tipo": "grafico", "clase": "barras", "titulo": "Personas por zona", "unidad": "personas",
         "items": [{"etiqueta": "Rural", "valor": 120}, {"etiqueta": "Urbana", "valor": 80.5, "texto": "80,5 mil"}],
         "nota": "Sin quienes no autorizaron."},
        {"tipo": "grafico", "clase": "pastel", "titulo": "No existe", "items": _items(2)},
        {"tipo": "grafico", "clase": "barras", "titulo": "   ", "items": _items(2)},
        {"tipo": "grafico", "clase": "barras", "titulo": "Sin ítems válidos", "items": [
            {"etiqueta": "Negativo", "valor": -1}, {"etiqueta": "Texto", "valor": "5"},
            {"etiqueta": "Bool", "valor": True}, {"etiqueta": "", "valor": 3}, {"valor": 4}, "no es un objeto",
            ["lista"], {"etiqueta": "Nulo", "valor": None}]},
        {"tipo": "grafico", "clase": "columnas", "titulo": "Mezcla", "unidad": "u" * 50, "items": [
            {"etiqueta": raro, "valor": 2}, {"etiqueta": "Bueno", "valor": 0}, {"etiqueta": "Malo", "valor": -0.5},
            {"etiqueta": "x" * 80, "valor": 7, "texto": "t" * 60}]},
        {"tipo": "grafico", "clase": "serie", "titulo": "T" * 200, "items": _items(75), "nota": "n" * 300},
        {"tipo": "grafico", "clase": "apilada", "titulo": "Autorizaciones", "items": [], "nota": "vacía"},
        {"clase": "barras", "titulo": "Sin tipo también vale (lo pone el servidor)", "items": _items(1)},
        "no es un objeto", None, [],
        {"tipo": "grafico", "clase": "barras", "titulo": "Ítems no lista", "items": {"a": 1}},
    ]
    salida = _pintar(casos)
    assert salida["exportados"] == ["pintarGrafico"]
    for caso, fig in zip(casos, salida["dibujos"]):
        esperado = grafico.validar(caso)
        if esperado is None:
            assert fig is None, caso
            continue
        assert fig is not None and fig["tag"] == "figure" and fig["clase"] == "agente-grafico", caso
        assert fig["dataset"] == {"clase": esperado["clase"]}
        p = _partes(fig)
        assert p["titulo"] == esperado["titulo"] and p["unidad"] == esperado["unidad"]
        assert p["nota"] == esperado.get("nota")
        etiquetas = [c.split(": ")[0] for c in p["cifras"].split("; ")]
        assert etiquetas == [it["etiqueta"] for it in esperado["items"]], caso.get("titulo")
    # Los topes: 60 ítems, título de 120, etiqueta de 60, unidad de 30, nota de 200, sin los caracteres raros
    serie = _partes(salida["dibujos"][5])
    assert len(serie["cifras"].split("; ")) == 60 and len(serie["titulo"]) == 120 and len(serie["nota"]) == 200
    mezcla = _partes(salida["dibujos"][4])
    assert mezcla["cifras"].startswith("Ve reda nueva: 2") and len(mezcla["unidad"]) == 30
    assert "Malo" not in mezcla["cifras"] and "x" * 61 not in mezcla["cifras"] and "x" * 60 in mezcla["cifras"]


# ───────────────────────────── Sin HTML de afuera ─────────────────────────────

@requiere_node
def test_nada_del_grafico_entra_como_html():
    xss = '<img src=x onerror="window.__xss=1">'
    casos = [{"tipo": "grafico", "clase": clase, "titulo": f"Título {xss}", "unidad": f"u{xss}"[:30],
              "nota": f"Nota {xss}",
              "items": [{"etiqueta": f"<script>alert(1)</script>{i}", "valor": i + 1, "texto": "<b>dos</b>",
                         "color": "red;background:url(https://malo.example/x)"} for i in range(3)]}
             for clase in ("barras", "columnas", "apilada", "serie")]
    for fig in _pintar(casos)["dibujos"]:
        p = _partes(fig)
        # El título y la nota, como texto (textContent): se ven tal cual
        assert p["titulo"] == f"Título {xss}" and p["nota"] == f"Nota {xss}"
        # En el dibujo, todo escapado: ningún elemento ni atributo que venga del servidor
        assert "<script" not in p["html"] and "<img" not in p["html"] and "<b>dos" not in p["html"]
        assert "onerror=" not in p["html"].replace("onerror=&quot;", "")
        assert "malo.example" not in p["html"] and "url(" not in p["html"]
        # Los colores, de la paleta
        colores = set(re.findall(r"(?:background|fill|stroke)[:=]\"?(var\(--[a-z0-9]+\)|#[0-9a-f]+|[a-z]+)", p["html"]))
        assert colores <= {"var(--s1)", "var(--s2)", "var(--s3)", "var(--surface)", "none"}, p["html"]


# ───────────────────────────── Cada clase con su dibujo ─────────────────────────────

@requiere_node
def test_cada_clase_se_dibuja_con_graficos_js():
    casos = [
        {"tipo": "grafico", "clase": "barras", "titulo": "Barras", "unidad": "personas", "items": [
            {"etiqueta": "La Paz", "valor": 1234}, {"etiqueta": "El Dique", "valor": 56.5, "texto": "56,5 %"}]},
        # Columnas cortas: el histograma; con etiquetas largas o más de 12, barras
        {"tipo": "grafico", "clase": "columnas", "titulo": "Edades", "items": [
            {"etiqueta": e, "valor": v} for e, v in (("18-24", 10), ("25-34", 20), ("35-44", 15))]},
        {"tipo": "grafico", "clase": "columnas", "titulo": "Largas", "items": [
            {"etiqueta": "Una etiqueta bastante larga para una columna", "valor": 3},
            {"etiqueta": "Otra", "valor": 4}]},
        {"tipo": "grafico", "clase": "columnas", "titulo": "Muchas", "items": [
            {"etiqueta": str(i), "valor": i} for i in range(13)]},
        # Apilada: una parte por color; con 9, las 6 primeras y «Otras» con la suma del resto
        {"tipo": "grafico", "clase": "apilada", "titulo": "Partes", "unidad": "personas", "items": _items(9)},
        # Serie: periodos que se leen como fechas, con un globo por punto; un solo punto, barras
        {"tipo": "grafico", "clase": "serie", "titulo": "Altas por mes", "unidad": "altas", "items": [
            {"etiqueta": "2026-08", "valor": 10}, {"etiqueta": "2026-09", "valor": 0},
            {"etiqueta": "2026-10", "valor": 25},
            {"etiqueta": "2026-11", "valor": 40, "texto": "40 (parcial)"}]},
        {"tipo": "grafico", "clase": "serie", "titulo": "Un punto", "items": [{"etiqueta": "2026-S46", "valor": 3}]},
        {"tipo": "grafico", "clase": "serie", "titulo": "Por día", "items": [
            {"etiqueta": f"2026-10-{d:02d}", "valor": d % 7} for d in range(1, 32)]},
    ]
    barras, cols, largas, muchas, apilada, serie, punto, dias = [_partes(f) for f in _pintar(casos)["dibujos"]]
    assert 'class="lista-barras"' in barras["html"] and barras["html"].count('class="f"') == 2
    assert "1.234" in barras["html"] and "56,5 %" in barras["html"] and "var(--s1)" in barras["html"]
    assert barras["cifras"] == "La Paz: 1.234 personas; El Dique: 56,5 % personas"
    assert 'aria-label="Histograma"' in cols["html"] and cols["html"].count("<path ") == 3
    assert 'class="lista-barras"' in largas["html"] and 'class="lista-barras"' in muchas["html"]
    assert 'class="apilada"' in apilada["html"] and apilada["html"].count('class="leyenda"') == 1
    assert apilada["html"].count("tabindex=\"0\" style=\"flex:") == 7 and ">Otras <b>" in apilada["html"]
    otras = sum(i * 3 + 1 for i in range(6, 9))
    assert f"{otras} personas" in apilada["html"].replace("&nbsp;", " ")
    assert "Serie en el tiempo de altas" in serie["html"] and serie["html"].count('class="golpe"') == 4
    assert ">ago 2026<" in serie["html"] and ">nov 2026<" in serie["html"]
    assert 'data-gd="40 (parcial) altas"' in serie["html"] and 'data-gt="sep 2026"' in serie["html"]
    assert 'class="lista-barras"' in punto["html"]
    # 31 días: un globo por día y como mucho 6 fechas debajo (la primera y la última)
    assert dias["html"].count('class="golpe"') == 31 and dias["html"].count('text-anchor="middle">') <= 4
    assert ">1 oct 2026<" in dias["html"] and ">31 oct 2026<" in dias["html"]


# ───────────────────────────── En el chat ─────────────────────────────

def test_el_widget_carga_el_modulo_con_el_primer_grafico_y_lo_pone_bajo_su_herramienta():
    codigo = AGENTE
    # No se importa arriba: graficos.js pone escuchas en `document` al cargarse y la mayoría de las conversaciones no
    # tiene gráficos
    assert not re.search(r"^import .*agente-graficos", codigo, re.M)
    assert "modGraficos ||= import('./agente-graficos.js');" in codigo
    assert "else if (a.tipo === 'grafico') grafico(a);" in codigo
    # En vivo: debajo del chip de la última herramienta que terminó (el servidor manda la acción justo después)
    assert "if (estado === 'ok') ultimoOk = c;" in codigo
    funcion = codigo[codigo.index("function grafico(a, chip = ultimoOk) {"):
                     codigo.index("// ── La presentación automática")]
    assert "if (esta !== vez) return;" in funcion and "antes.after(fig);" in funcion
    assert ("while (antes.nextElementSibling?.classList.contains('agente-grafico')) "
            "antes = antes.nextElementSibling;") in funcion
    # Al repintar: el `grafico` de la parte de la herramienta, debajo de su chip
    repintar = codigo[codigo.index("function pintarConversacion(d) {"):codigo.index("// ── Preguntas por voz")]
    assert "if (p.grafico) grafico(p.grafico, chips.get(texto(p.id, 100)));" in repintar
    assert "ultimoOk = null;" in codigo[codigo.index("function limpiarConversacion() {"):]
