"""Grupo 4 (9.5): cada ruta '/api/…' escrita en web/js existe en la aplicación, con el método con que se llama.

Las rutas de un grupo que todavía no llegó (G1, G3 o G5) se saltan por una condición explícita: la ruta que marca la
llegada de ese grupo no existe. Una ruta que no es de ningún grupo pendiente y no existe es una falla.
"""
import re
from pathlib import Path

import pytest
from fastapi.routing import APIRoute

from app.main import crear_app

WEB = Path(__file__).resolve().parents[1] / "web" / "js"
# Una ruta de cada grupo que llega después (las mismas marcas de test_permisos.py)
MARCAS = {"G1": ("GET", "/api/ajustes"), "G3": ("GET", "/api/trabajo"), "G5": ("GET", "/api/areas")}
# De qué grupo es cada ruta nueva que la interfaz ya usa (8.2), por su forma
DUENOS = [
    (r"/api/(ajustes|puestos(/X)?|conflictos(/X)?|solicitudes(/X)?|plantillas/planilla\.xlsx|importaciones/X/confirmar-autorizaciones)", "G1"),
    (r"/api/(trabajo(/.*)?|insignias|parecidas|acercamientos(/X/anular)?)", "G3"),
    (r"/api/personas/X/(telefonos(/X(/principal)?)?|autorizacion|autorizaciones|sensibles|duplicado|actualizacion|situacion|no-disponible|acercamientos)", "G3"),
    (r"/api/areas(/X)?", "G5"),
]
METODOS = {"get": "GET", "post": "POST", "patch": "PATCH", "put": "PUT", "del": "DELETE", "subir": "POST"}

# Una cadena que empieza por /api/: entre comillas simples, dobles o en una plantilla `…${x}…`
LITERAL = re.compile(r"""(['"`])(/api/(?:[^'"`$\\]|\$\{[^}]*\})*)\1""")
LLAMADA = re.compile(r"""\b(?:api\.(get|post|patch|put|del|subir)|(descargar))\(\s*$""")


def _sin_comentarios(texto: str) -> str:
    return "\n".join("" if l.lstrip().startswith(("//", "*", "/*")) else l for l in texto.splitlines())


def _forma(literal: str) -> str:
    """`/api/personas/${id}/telefonos/${n}?x=1` → `/api/personas/X/telefonos/X`."""
    ruta = re.sub(r"\$\{[^}]*\}", "X", literal).split("?", 1)[0]
    return ruta.rstrip("/") or ruta


def literales() -> list[tuple[str, str, str | None]]:
    """[(archivo, forma, método o None)] de cada '/api/…' literal de web/js."""
    out = []
    for f in sorted(WEB.rglob("*.js")):
        texto = _sin_comentarios(f.read_text(encoding="utf-8"))
        for m in LITERAL.finditer(texto):
            llamada = LLAMADA.search(texto[max(0, m.start() - 40):m.start()])
            metodo = (METODOS.get(llamada.group(1)) or "GET") if llamada else None
            out.append((str(f.relative_to(WEB)), _forma(m.group(2)), metodo))
    return out


def _rutas():
    rutas = []
    for r in crear_app().routes:
        if isinstance(r, APIRoute) and r.path.startswith("/api/"):
            patron = re.compile("^" + re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(r.path)) + "$")
            rutas.append((patron, r.methods, r.path))
    return rutas


RUTAS = _rutas()
LLEGADOS = {g for g, (m, p) in MARCAS.items() if any(m in met and ruta == p for _, met, ruta in RUTAS)}


def _existe(forma: str, metodo: str | None) -> bool:
    return any(p.match(forma) and (metodo is None or metodo in met) for p, met, _ in RUTAS)


def _dueno(forma: str) -> str | None:
    return next((g for patron, g in DUENOS if re.fullmatch(patron, forma)), None)


LITERALES = literales()


def test_hay_literales_que_revisar():
    formas = {f for _, f, _ in LITERALES}
    assert {"/api/personas", "/api/catalogos", "/api/personas/X", "/api/trabajo/cola"} <= formas
    # El método se reconoce en las llamadas de api.*: la prueba no compara solo rutas
    assert ("vistas/ficha.js", "/api/personas/X/telefonos/X/principal", "POST") in LITERALES


def test_las_rutas_de_web_js_existen():
    faltan = [(a, f, m) for a, f, m in LITERALES if not _existe(f, m) and _dueno(f) is None]
    assert not faltan, f"Rutas de web/js que no existen en la API: {faltan}"


@pytest.mark.parametrize("grupo", ["G1", "G3", "G5"])
def test_las_rutas_de_cada_grupo_existen_cuando_llega(grupo):
    if grupo not in LLEGADOS:
        pytest.skip(f"requiere el grupo {grupo[1]}: no existe {' '.join(MARCAS[grupo])}")
    faltan = [(a, f, m) for a, f, m in LITERALES if _dueno(f) == grupo and not _existe(f, m)]
    assert not faltan, f"Rutas del grupo {grupo} que la interfaz usa y no existen: {faltan}"


def test_las_rutas_de_grupos_pendientes_son_solo_las_previstas():
    # Lo que se salta tiene dueño conocido; si un grupo ya llegó, sus rutas se comparan en la prueba de arriba
    pendientes = {(f, _dueno(f)) for _, f, m in LITERALES if not _existe(f, m)}
    assert all(g is not None for _, g in pendientes), pendientes
