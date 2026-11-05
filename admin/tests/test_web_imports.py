"""Grupo 4 (9.5): los módulos de web/js se importan bien entre sí, sin compilar.

Cada `import { a, b as c } from './x.js'`, `import * as m`, `export … from` e `import('./x.js')` apunta a un archivo
que existe, y cada nombre importado lo exporta el módulo de destino. Las vistas que carga app.js con
`import('./vistas/x.js').then((m) => m.vistaX)` exportan esa función. Con Node, además, cada archivo es JavaScript
válido como módulo (`node --check`).
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "web"
JS = WEB / "js"
ARCHIVOS = sorted(JS.rglob("*.js"))

IMPORT = re.compile(r"""^\s*(?:import|export)\s+(?P<que>[^'";]*?)\s+from\s+['"](?P<de>\.{1,2}/[^'"]+)['"]""", re.M)
IMPORT_SOLO = re.compile(r"""^\s*import\s+['"](?P<de>\.{1,2}/[^'"]+)['"]""", re.M)
DINAMICO = re.compile(r"""import\(\s*['"](?P<de>\.{1,2}/[^'"]+)['"]\s*\)(?:\.then\(\(\s*m\s*\)\s*=>\s*m\.(?P<nombre>\w+)\))?""")


def _sin_comentarios(texto: str) -> str:
    return "\n".join("" if l.lstrip().startswith(("//", "*", "/*")) else l for l in texto.splitlines())


def exportados(archivo: Path) -> set[str]:
    """Nombres que exporta un módulo: declaraciones, `export { a, b as c }` y `export const { A, B } = …`."""
    t = _sin_comentarios(archivo.read_text(encoding="utf-8"))
    nombres = set(re.findall(r"^\s*export\s+(?:async\s+)?(?:function\*?|const|let|var|class)\s+([\w$]+)", t, re.M))
    for grupo in re.findall(r"^\s*export\s+(?:const|let|var)\s+\{([^}]*)\}\s*=", t, re.M):
        nombres |= {x.split(":")[-1].strip() for x in grupo.split(",") if x.strip()}
    for grupo in re.findall(r"^\s*export\s+\{([^}]*)\}", t, re.M):
        nombres |= {x.split(" as ")[-1].strip() for x in grupo.split(",") if x.strip()}
    if re.search(r"^\s*export\s+default\b", t, re.M):
        nombres.add("default")
    return nombres


def importados(que: str) -> list[str]:
    """`{ a, b as c }` → [a, b]; `* as m` → []; `def, { a }` → [default, a]."""
    nombres = []
    if que.startswith("*"):
        return nombres
    llaves = re.search(r"\{([^}]*)\}", que, re.S)
    if llaves:
        nombres += [x.strip().split(" as ")[0].strip() for x in llaves.group(1).split(",") if x.strip()]
    fuera = re.sub(r"\{[^}]*\}", "", que).strip().strip(",").strip()
    if fuera and not fuera.startswith("*"):
        nombres.append("default")
    return nombres


def _relaciones():
    out = []
    for f in ARCHIVOS:
        t = _sin_comentarios(f.read_text(encoding="utf-8"))
        for m in IMPORT.finditer(t):
            out.append((f, (f.parent / m.group("de")).resolve(), importados(" ".join(m.group("que").split()))))
        for m in IMPORT_SOLO.finditer(t):
            out.append((f, (f.parent / m.group("de")).resolve(), []))
        for m in DINAMICO.finditer(t):
            out.append((f, (f.parent / m.group("de")).resolve(), [m.group("nombre")] if m.group("nombre") else []))
    return out


RELACIONES = _relaciones()


def test_se_revisan_los_modulos_del_panel():
    assert len(ARCHIVOS) > 20
    destinos = {d.name for _, d, _ in RELACIONES}
    assert {"api.js", "ui.js", "modelo.js", "comunes.js", "acercamiento.js", "llamadas.js", "trabajo.js"} <= destinos


@pytest.mark.parametrize("origen, destino, nombres", RELACIONES,
                         ids=[f"{o.relative_to(JS)}->{d.name}" for o, d, _ in RELACIONES])
def test_cada_import_existe_y_exporta_lo_que_se_pide(origen, destino, nombres):
    assert destino.is_file(), f"{origen.relative_to(JS)} importa {destino}, que no existe"
    assert JS in destino.parents, f"{origen.relative_to(JS)} importa fuera de web/js: {destino}"
    faltan = [n for n in nombres if n not in exportados(destino)]
    assert not faltan, f"{origen.relative_to(JS)} importa {faltan} de {destino.relative_to(JS)}, que no los exporta"


def test_las_vistas_de_app_js_existen():
    app = (JS / "app.js").read_text(encoding="utf-8")
    vistas = DINAMICO.findall(app)
    assert len(vistas) >= 12
    for de, nombre in vistas:
        assert nombre, f"app.js carga {de} sin nombrar la vista"
        assert nombre in exportados((JS / de).resolve()), (de, nombre)


def test_index_carga_lo_que_existe():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    for ruta in re.findall(r'(?:src|href)="/static/([^"]+)"', html):
        assert (WEB / ruta).is_file(), ruta


@pytest.mark.skipif(shutil.which("node") is None, reason="sin Node para revisar la sintaxis")
def test_cada_modulo_es_javascript_valido(tmp_path):
    malos = []
    for f in ARCHIVOS:
        copia = tmp_path / (str(f.relative_to(JS)).replace("/", "_") + ".mjs")
        copia.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
        r = subprocess.run(["node", "--check", str(copia)], capture_output=True, text=True, timeout=30)
        if r.returncode:
            malos.append((str(f.relative_to(JS)), r.stderr.strip().splitlines()[-1:]))
    assert not malos, malos


@pytest.mark.skipif(shutil.which("node") is None, reason="sin Node para cargar web/js/modelo.js")
def test_ayudas_puras_de_modelo_js():
    codigo = ("import * as m from './web/js/modelo.js';"
              "const ab = m.textoAbordaje({estado: 'contactado', ultimo_fecha: '2026-11-03', ultimo_canal: 'llamada', ultimo_usuario: 'Luis'});"
              "console.log(JSON.stringify([ab.texto, ab.clase, m.textoAbordaje({estado: 'intentado', n: 2}).texto, m.textoAbordaje(null).texto,"
              "m.rangoAParams('25-34'), m.rangoAParams('<18'), m.rangoAParams('65+'),"
              "m.fueraDeHorario({semana: ['07:00', '19:00'], sabado: ['08:00', '15:00'], domingo: false}, new Date('2026-11-04T15:00:00Z')),"
              "m.fueraDeHorario({semana: ['07:00', '19:00'], sabado: ['08:00', '15:00'], domingo: false}, new Date('2026-11-08T15:00:00Z')),"
              "m.canalesPermitidos({consentimiento: 'si', consentimiento_canales: ['llamada', 'whatsapp'], telefonos: [{numero: '3001112233'}]}, 'consultor'),"
              "m.canalesPermitidos({consentimiento: 'si', consentimiento_canales: ['llamada', 'whatsapp'], telefonos: [{numero: '8612345'}]}, 'consultor'),"
              "m.canalesPermitidos({consentimiento: 'pendiente', telefonos: [{numero: '3001112233'}]}, 'consultor'),"
              "m.canalesPermitidos({consentimiento: 'si', telefonos: []}, 'planillero'),"
              "m.telefonosUsables({telefonos: [{numero: '1', estado: 'retirado'}, {numero: '3001112233'}]}).map((t) => t.numero),"
              "m.enmascarar('3001112233'), m.hoyColombia(new Date('2026-11-05T03:00:00Z')),"
              "m.enlaceWhatsapp('300 111 2233', 'hola')]))")
    r = subprocess.run(["node", "--input-type=module", "-e", codigo], cwd=WEB.parent, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    import json
    assert json.loads(r.stdout) == [
        "Contactado · 3 nov · llamada · Luis", "verde", "Intentado ×2", "Sin abordar",
        {"edad_min": 25, "edad_max": 34}, {"edad_max": 17}, {"edad_min": 65},
        False, True,  # miércoles 10:00 en Colombia: dentro; domingo: fuera
        ["llamada", "whatsapp"], ["llamada"], [], ["visita"],
        ["3001112233"], "···2233", "2026-11-04", "https://wa.me/573001112233?text=hola",
    ]
