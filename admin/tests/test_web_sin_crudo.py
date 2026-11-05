"""Grupo 4 (9.5): ningún dato de la base pasa por `crudo()` (9.2, regla de interfaz).

`crudo(x)` marca `x` como HTML de confianza: `html` no lo escapa. Desde que planilleros y consultores escriben textos
que lee el administrador (notas, `requiere_actualizacion.nota`, `telefonos[].nota`, `solicitudes.descripcion`), solo
se acepta con un texto fijo del código: una cadena literal sin interpolaciones. Tampoco se arma HTML por otra vía:
`new Crudo(` solo existe dentro de ui.js y todo `innerHTML =` recibe una plantilla `html`.
"""
import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web" / "js"
ARCHIVOS = sorted(WEB.rglob("*.js"))
DEFINICION = re.compile(r"export\s+const\s+crudo\s*=")
# El argumento de crudo( debe ser una cadena literal: '…', "…" o `…` sin ${…}, seguida del paréntesis de cierre
LITERAL = re.compile(r"""\s*(?:'(?:[^'\\\n]|\\.)*'|"(?:[^"\\\n]|\\.)*"|`[^`$]*`)\s*\)""")


def _sin_comentarios(texto: str) -> str:
    return "\n".join("" if l.lstrip().startswith(("//", "*", "/*")) else l for l in texto.splitlines())


def usos_de_crudo():
    """[(archivo, línea, resto)] de cada llamada `crudo(` (también `ui.crudo(`), sin contar la definición."""
    out = []
    for f in ARCHIVOS:
        t = _sin_comentarios(f.read_text(encoding="utf-8"))
        for m in re.finditer(r"(?<![\w$])crudo\s*\(", t):
            linea = t.count("\n", 0, m.start()) + 1
            if DEFINICION.search(t.splitlines()[linea - 1]):
                continue
            out.append((str(f.relative_to(WEB)), linea, t[m.end():m.end() + 200]))
    return out


def test_crudo_solo_con_textos_fijos():
    malos = [(a, l, resto.split("\n")[0]) for a, l, resto in usos_de_crudo() if not LITERAL.match(resto)]
    assert not malos, f"crudo() con un valor que no es un texto fijo: {malos}"


def test_la_regla_reconoce_los_usos_peligrosos():
    # Autocomprobación: la expresión rechaza variables, plantillas con interpolación y concatenaciones
    for malo in ["x)", "`<b>${p.nombre}</b>`)", "'<b>' + p.nota)", "p.nota || '')", "extra)"]:
        assert not LITERAL.match(malo), malo
    for bueno in ["'<br>')", '"&nbsp;")', "`<hr>`)"]:
        assert LITERAL.match(bueno), bueno


def test_no_se_arma_html_por_fuera_de_ui_js():
    otros = [str(f.relative_to(WEB)) for f in ARCHIVOS if f.name != "ui.js" and "new Crudo(" in f.read_text(encoding="utf-8")]
    assert not otros, otros
    ui = (WEB / "ui.js").read_text(encoding="utf-8")
    # Dentro de ui.js, Crudo solo envuelve el resultado de `html` y los íconos de la tabla fija P
    usos = re.findall(r"new Crudo\(([^;\n]*)", ui)
    assert all(u.startswith(("s)", "`<svg")) or "P[n]" in u for u in usos), usos


def test_inner_html_solo_con_plantillas():
    malos = []
    for f in ARCHIVOS:
        for n, l in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            for m in re.finditer(r"\.(?:inner|outer)HTML\s*=\s*(.*)", l):
                valor = m.group(1)
                if not (valor.startswith("String(html`") or valor.startswith("''") or (f.name == "ui.js" and valor.startswith("String(contenido)"))):
                    malos.append((str(f.relative_to(WEB)), n, l.strip()))
            if "insertAdjacentHTML" in l or "document.write" in l:
                malos.append((str(f.relative_to(WEB)), n, l.strip()))
    assert not malos, malos


def test_las_vistas_de_campo_no_importan_crudo():
    # Las vistas del grupo 4 arman todo con `html`; si una vuelve a importar crudo, que sea a conciencia
    for nombre in ["vistas/ficha.js", "vistas/personas.js", "vistas/comunes.js", "vistas/acercamiento.js", "vistas/trabajo.js",
                   "vistas/reunion.js", "vistas/reuniones.js", "vistas/panel.js", "graficos.js", "llamadas.js"]:
        t = (WEB / nombre).read_text(encoding="utf-8")
        assert not re.search(r"import\s*\{[^}]*\bcrudo\b[^}]*\}", t), nombre
