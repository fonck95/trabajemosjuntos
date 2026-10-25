"""Control de cifras de los documentos de la torre (equipo E; especificación de integración, 11.6 y 13.5).

    python3 scripts/torre/verificar_cifras_docs.py                         # estricto: sale 1 si algo no cuadra
    python3 scripts/torre/verificar_cifras_docs.py --permitir-pendientes   # olas 1 y 2: lo que aún no se escribe o no
                                                                           # se calcula queda «pendiente» y no hace fallar
    python3 scripts/torre/verificar_cifras_docs.py --json                  # informe completo en JSON

Lee las cifras clave de los JSON (contraste con el proyecto tipo, inventario, cierre de brechas, matriz de cumplimiento,
exigencias, prediseño, escenarios de referencia y validación del motor sísmico, modelo BIM, interferencias, validación
de los IFC y cantidades frente al presupuesto) y comprueba que aparecen tal cual, en formato es-CO, en
docs/11-torre-hospital-nivel-1.md, docs/14-simulacion-sismica.md, docs/15-dotacion-y-habilitacion.md y
docs/16-bim-torre.md; que $4.555.806
(sobre 320,6 m²) y $5,42 M (sobre 270 m²) aparecen juntas; que no quedan marcas «[CIFRA]» sin llenar; y que ninguna mención
de la Res. 1732 la da como vigente ni ninguna de la Res. 482 de 2018 como norma que rige (en docs/, en los JSON de
data/proyectos/torre_hospital/ y en web/data/torre*.json).

El «antes» de las interferencias de docs/16 (primera corrida del modelo federado, 24-oct-2026) va como constante y, si hay
historial de git, se coteja con `git show` (solo lectura).

Estados de cada control: ok · falta (la fuente existe y el documento no trae la cifra) · pendiente (la fuente o el campo
todavía no existe, o el documento todavía tiene la marca «[CIFRA]» de esa cifra, o es una sección de una ola posterior).
Solo biblioteca estándar (Python 3.12).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import comun as C  # noqa: E402

DOCS = C.RAIZ / 'docs'
DOC11 = DOCS / '11-torre-hospital-nivel-1.md'
DOC14 = DOCS / '14-simulacion-sismica.md'
DOC15 = DOCS / '15-dotacion-y-habilitacion.md'
DOC16 = DOCS / '16-bim-torre.md'
SISMO = C.DATOS / 'sismo'
BIM = C.DATOS / 'bim'
PRESUPUESTO = C.TORRE / 'presupuesto.json'
MARCA = '[CIFRA]'
RE_MARCA = re.compile(r'\[CIFRA(?::[^\]]*)?\]')   # «[CIFRA]» o «[CIFRA: qué va]»
RE_1732 = re.compile(r'(?<![\w_/.%-])1732(?![\d_])')
RE_482 = re.compile(r'482 de 2018')
# archivos cuyo dueño es este equipo (2.1): sus fallas de vigencia nunca se toleran como pendientes
PROPIOS = {'docs/11-torre-hospital-nivel-1.md', 'docs/09-motor-3d-y-modelos.md', 'docs/14-simulacion-sismica.md',
           'docs/15-dotacion-y-habilitacion.md', 'docs/16-bim-torre.md', 'data/proyectos/torre_hospital/normas.json',
           'data/proyectos/torre_hospital/proyecto_tipo.json', 'data/proyectos/torre_hospital/proyecto_tipo_contraste.json',
           'data/proyectos/torre_hospital/programa.json'}


# ------------------------------------------------------------------------------------------------ formato es-CO
def entero(n) -> str:
    return f'{round(n):,}'.replace(',', '.')


def decimal(x, d=1) -> str:
    return f'{x:,.{d}f}'.replace(',', '§').replace('.', ',').replace('§', '.')


def pesos(n) -> str:
    return '$' + entero(n)


def millones(n, d=1) -> list[str]:
    """«$4.294 M», «$4.294,0 M» o «$198,1 M»: las formas que usan los documentos para millones."""
    m = n / 1e6
    formas = {f'${decimal(m, d)} M', f'${decimal(m, d)} M'}
    if m >= 100:
        formas |= {f'${entero(m)} M', f'${entero(m)} M'}
    return sorted(formas)


def pesos_signo(n) -> str:
    """«$526.716.630» o «−$98.991.438» (signo menos tipográfico, como en los documentos)."""
    return ('−' if n < 0 else '') + pesos(abs(n))


def pct(x, d) -> str:
    """Fracción → «0,939 %»."""
    return f'{decimal(x * 100, d)} %'


SUPER = str.maketrans('-0123456789', '⁻⁰¹²³⁴⁵⁶⁷⁸⁹')


def cientifica(x, d=1) -> str:
    """8.903e-06 → «8,9 × 10⁻⁶»."""
    m, e = f'{x:.{d}e}'.split('e')
    return f'{decimal(float(m), d)} × 10{str(int(e)).translate(SUPER)}'


def normal(t: str) -> str:
    """Texto comparable: espacios duros y finos como espacios normales."""
    return t.replace(' ', ' ').replace(' ', ' ')


# ------------------------------------------------------------------------------------------------ utilidades
def leer(ruta: Path):
    try:
        return C.cargar_json(ruta)
    except (FileNotFoundError, ValueError):
        return None


def obtener(d, *rutas):
    """El primer valor que exista entre varias rutas «a.b.c» (los generados de otros equipos todavía cambian de forma)."""
    for r in rutas:
        x = d
        for k in r.split('.'):
            if isinstance(x, dict) and k in x:
                x = x[k]
            elif isinstance(x, list) and k.isdigit() and int(k) < len(x):
                x = x[int(k)]
            else:
                x = None
                break
        if x is not None:
            return x
    return None


class Control:
    def __init__(self):
        self.filas = []

    def agregar(self, id_, doc, que, estado, detalle='', ola=1):
        self.filas.append({'id': id_, 'documento': doc, 'que': que, 'estado': estado, 'detalle': detalle, 'ola': ola})


def texto_doc(ruta: Path):
    return normal(ruta.read_text(encoding='utf-8')) if ruta.exists() else None


def buscar(ctrl: Control, id_, ruta: Path, que, alternativas_por_cifra, ola=1, seccion: str | None = None):
    """Cada elemento de `alternativas_por_cifra` es una lista de formas aceptadas de una cifra: deben aparecer todas las
    cifras (cualquiera de sus formas). Si el documento (o su sección) tiene «[CIFRA]», lo que falta queda pendiente."""
    doc = C.relativa(ruta)
    t = texto_doc(ruta)
    if t is None:
        ctrl.agregar(id_, doc, que, 'pendiente', 'el documento todavía no existe', ola)
        return
    zona = t
    if seccion:
        m = re.search(r'^(#+) ' + re.escape(seccion) + r'.*?$(.*?)(?=^#{1,%d} |\Z)' % 2, t, re.M | re.S)
        zona = m.group(2) if m else t
    faltan = [alts[0] for alts in alternativas_por_cifra if not any(normal(a) in zona for a in alts)]
    if not faltan:
        ctrl.agregar(id_, doc, que, 'ok', '', ola)
    elif RE_MARCA.search(zona):
        ctrl.agregar(id_, doc, que, 'pendiente', f'la sección aún tiene «{MARCA}»; faltan: {", ".join(faltan)}', ola)
    else:
        ctrl.agregar(id_, doc, que, 'falta', f'no aparece: {", ".join(faltan)}', ola)


# ------------------------------------------------------------------------------------------------ controles
def controles_contraste(ctrl: Control):
    c = leer(C.TORRE / 'proyecto_tipo_contraste.json')
    if not c:
        ctrl.agregar('CT0', 'docs/11', 'contraste con el proyecto tipo', 'pendiente', 'no existe proyecto_tipo_contraste.json', 2)
        return
    cif = {x['id']: x for x in obtener(c, 'resumen_para_la_web.cifras') or []}
    cm = c.get('costo_m2') or {}
    t320 = obtener(cm, 'tipo_dnp.por_m2_2026_sobre_320_6')
    t270 = obtener(cm, 'tipo_dnp.por_m2_2026_sobre_269_6')
    # programa.json lleva el mismo valor sobre 320,6 m² (9.1)
    pr = leer(C.PROGRAMA)
    vr = obtener(pr or {}, 'proyectos_tipo.1.costo_de_referencia.valor_m2_pesos_2026')
    ctrl.agregar('CT1', 'programa.json', 'costo de referencia del tipo = el del contraste (sobre 320,6 m²)',
                 'ok' if vr == t320 else 'falta', f'programa {vr} · contraste {t320}', 1)
    # docs/11: las dos cifras juntas (mismo párrafo), con sus áreas
    t = texto_doc(DOC11)
    if t is None:
        ctrl.agregar('CT2', 'docs/11', '$4.555.806 (320,6 m²) y $5,42 M (270 m²) juntas', 'pendiente', 'sin documento', 2)
    else:
        parrafos = re.split(r'\n\s*\n|\n(?=\|)', t)
        juntas = [p for p in parrafos if pesos(t320) in p and any(f in p for f in millones(t270, 2)) and '320,6' in p and re.search(r'\b(270|269,6)\b', p)]
        ctrl.agregar('CT2', 'docs/11', f'{pesos(t320)} (sobre 320,6 m²) y {millones(t270, 2)[0]} (sobre 270 m²) juntas en un párrafo',
                     'ok' if juntas else 'pendiente', '' if juntas else 'docs/11 se actualiza en la ola 2 (§3.2 y §6.2)', 2)
    # docs/11 §3: resumen del contraste con sus bases (ola 2)
    def v(i, k=None):
        x = cif.get(i, {}).get('valor')
        return x[k] if k is not None and isinstance(x, (list, dict)) else x
    if cif:
        ct, cn = v('ambientes_tipo') or {}, v('ambientes_norma') or {}
        buscar(ctrl, 'CT3', DOC11, 'contraste: tamaño, área con equivalente, costo por m² (rango), obra completa y dotación', [
            [f'{decimal(v("tamano"), 1)} veces'], [f'{entero(v("area_equivalente"))} %'],
            [f'{decimal(v("costo_obra_civil", 0), 1)} %'], [f'{decimal(v("costo_obra_civil", 1), 1)} %'],
            [decimal(v('costo_obra_completa', 0), 2)], [decimal(v('costo_obra_completa', 1), 2)],
            [f'{decimal(v("dotacion", 0), 1)} veces'], [f'{decimal(v("dotacion", 1), 1)} veces'],
            ['3.369,6 m²'], ['320,6 m²'], ['269,6 m²', '270 m²']], ola=2)
        buscar(ctrl, 'CT4', DOC11, 'contraste: veredictos frente al tipo y frente a la Res. 1633', [
            [f'{ct.get("mejora")} mejoran'], [f'{ct.get("cumple igual")} igual'], [f'{ct.get("se aparta")} se apartan'], [f'{ct.get("falta")} falta'],
            [f'{cn.get("mejora")} ', f'{cn.get("mejora")} '], [f'{cn.get("cumple igual")} ']], ola=2)
        buscar(ctrl, 'CT5', DOC15, 'dotación frente al tipo (§11): 21,7 veces y 2,1 por m², con sus bases', [
            [f'{decimal(v("dotacion", 0), 1)} veces'], [f'{decimal(v("dotacion", 1), 1)} veces por m²'], ['3.369,6 m²'], ['320,6 m²']],
            seccion='11. Dotación frente al proyecto tipo')


def controles_dotacion(ctrl: Control):
    inv = leer(C.INVENTARIO)
    dot = leer(C.DOTACION) or {}
    lab = leer(C.LABORATORIO) or {}
    # laboratorio (dato del repositorio)
    eq = lab.get('equipos') or []
    if eq:
        val = lambda e: ((e.get('precio_mercado') or {}).get('valor') or 0) * (e.get('cantidad') or 0)
        com = sum(val(e) for e in eq if 'comodato' in str(e.get('modelo_de_compra', '')).lower() and 'opcional' not in str(e.get('modelo_de_compra', '')).lower())
        tot = sum(val(e) for e in eq)
        gx = next((val(e) for e in eq if 'genexpert' in e.get('nombre', '').lower()), None)
        buscar(ctrl, 'DT1', DOC15, 'laboratorio: total, comodato y GeneXpert', [[pesos(tot)], [pesos(com)]] + ([[pesos(gx)]] if gx else []),
               seccion='9. Equipos del laboratorio')
    tg = dot.get('totales_generales') or {}
    if tg.get('solo_items_de_habilitacion_cop_2026'):
        buscar(ctrl, 'DT2', DOC15, 'valor de los ítems de habilitación (dato del repositorio)', [[pesos(tg['solo_items_de_habilitacion_cop_2026'])]],
               seccion='10. Reclasificaciones que propone la investigación')
    # inventario: unidades (ola 2)
    if inv is None:
        ctrl.agregar('DT3', 'docs/15', 'unidades del inventario', 'pendiente', 'no existe inventario_dotacion.json', 2)
    else:
        n = len(inv.get('unidades') or [])
        buscar(ctrl, 'DT3', DOC15, f'unidades del inventario ({entero(n)})', [[entero(n)]], ola=2, seccion='En pocas palabras')
    # cierre de brechas por proyecto (ola 2)
    tc = obtener(dot, 'cierre_brechas_habilitacion.totales')
    if not tc:
        ctrl.agregar('DT4', 'docs/15', 'cierre de brechas por proyecto', 'pendiente', 'dotacion.json sin cierre_brechas_habilitacion.totales', 2)
    else:
        cifras = []
        for p, x in (tc.get('por_proyecto') or {}).items():
            for k in ('habilitacion_cop_2026', 'recomendado_cop_2026', 'por_confirmar_cop_2026'):
                if x.get(k):
                    cifras.append([pesos(x[k])] + millones(x[k], 1))
        if tc.get('items_sin_precio') is not None:
            cifras.append([f'{tc["items_sin_precio"]} ítems'])
        op = obtener(tc, 'operacion_anual.cop_2026')
        if op:
            cifras.append([pesos(op)] + millones(op, 1))
        buscar(ctrl, 'DT4', DOC15, 'cierre de brechas: totales por proyecto, ítems sin precio y operación anual', cifras, ola=2, seccion='5. Cierre de brechas')
        buscar(ctrl, 'DT5', DOC11, 'cierre de brechas en docs/11 (§5.3)', cifras, ola=2)
    # exigencias (dato de las investigaciones, conteo propio)
    ex = leer(C.EXIGENCIAS)
    filas = obtener(ex or {}, 'conteos.filas') or 199
    pc = obtener(ex or {}, 'conteos.por_exigible.por_confirmar') or 61
    buscar(ctrl, 'DT6', DOC15, f'exigencias: {filas} filas de origen y {pc} por confirmar', [[f'{filas} filas de origen'], [f'{pc} son de guía secundaria o paráfrasis']],
           seccion='3. Método: de la exigencia al lugar')
    # matriz por servicio (ola 2): «cumple / parcial / falta / documento pendiente» de las exigibles en cada celda
    hab = leer(C.HABILITACION)
    if hab is None:
        ctrl.agregar('DT7', 'docs/15', 'matriz por servicio', 'pendiente', 'no existe habilitacion.json', 2)
        return
    t = texto_doc(DOC15) or ''
    faltan, pend = [], []
    for s in hab.get('servicios') or []:
        if s.get('habilitable') != 'si':
            continue
        r = s.get('resumen') or {}
        celdas = []
        for corte, esc in (('corte_2026', 'dotacion_actual'), ('corte_2026', 'con_cierre_de_brechas'), ('apertura', 'dotacion_actual')):
            e = obtener(r, f'{corte}.{esc}.exigibles') or {}
            celdas.append(f'{e.get("cumple", 0)} / {e.get("parcial", 0)} / {e.get("falta", 0)} / {e.get("documento_pendiente", 0)}')
        nombre = s.get('nombre') or s.get('id')
        linea = next((l for l in t.splitlines() if l.startswith(f'| {nombre} |')), None)
        if linea is None or RE_MARCA.search(linea):
            pend.append(nombre)
        elif not all(cel in linea for cel in celdas):
            faltan.append(f'{nombre} ({" | ".join(celdas)})')
    estado = 'falta' if faltan else ('pendiente' if pend else 'ok')
    ctrl.agregar('DT7', 'docs/15', 'matriz por servicio: exigibles cumple / parcial / falta / documento pendiente, en dos escenarios y dos cortes',
                 estado, ('no cuadran: ' + '; '.join(faltan)) if faltan else (f'sin llenar: {", ".join(pend)}' if pend else ''), 2)


def controles_sismo(ctrl: Control):
    est = leer(SISMO / 'torre_hospital_estructura.json')
    pre = (est or {}).get('prediseno') or {}
    if not pre:
        ctrl.agregar('SI1', 'docs/14', 'prediseño (sistema, R, T1, Ta, Cu·Ta, derivas)', 'pendiente',
                     'no existe data/sismo/torre_hospital_estructura.json o no trae «prediseno» (equipo A)', 2)
    else:
        r, per = pre.get('R') or {}, pre.get('periodos') or {}
        fhe = obtener(pre, 'cortante_basal.fhe.x') or {}
        modal = obtener(pre, 'cortante_basal.modal') or {}
        dv = [x['deriva'] for x in pre.get('derivas_vector') or []]
        ua = [x['deriva'] for x in obtener(pre, 'derivas_umbral_dano.aislados') or []]
        um = [x['deriva'] for x in obtener(pre, 'derivas_umbral_dano.mamposteria_adherida') or []]
        theta = max((max(x['x'], x['y']) for x in pre.get('estabilidad') or []), default=None)
        paso0 = next((h for h in pre.get('historial_de_ajustes') or [] if str(h.get('paso')) == '0'), {})
        cifras = [[decimal(r['R'], 2)], [decimal(r['R0'], 1)], [decimal(r['Omega0'], 1)],
                  [f'{decimal(per["T1y_s"], 3)} s'], [f'{decimal(per["T1x_s"], 3)} s'], [f'{decimal(per["Ta_s"], 3)} s'],
                  [f'{decimal(per["CuTa_s"], 3)} s'], [decimal(per['Cu'], 3)],
                  [f'{decimal(fhe["Sa_g"], 3)} g'], [f'{entero(fhe["W_kN"])} kN'],
                  [f'{entero(fhe["Vs_kN"])} kN'], [f'{entero(fhe["Vs_reducido_kN"])} kN'],
                  [f'{entero(modal["x"]["V_modal_kN"])} kN'], [f'{entero(modal["y"]["V_modal_kN"])} kN'],
                  [decimal(modal['x']['factor_ajuste'], 3)], [decimal(modal['y']['factor_ajuste'], 3)]]
        cifras += [[pct(x, 3)] for x in dv] + [[pct(max(ua), 3)], [pct(max(um), 3)]]
        if theta is not None:
            cifras.append([decimal(theta, 4)])
        if paso0.get('deriva_max_pct'):
            cifras.append([f'{decimal(paso0["deriva_max_pct"], 2)} %'])
        buscar(ctrl, 'SI1', DOC14, 'prediseño: R, períodos, cortante basal, derivas de diseño y del umbral de daño, P-Delta y deriva '
               'con las secciones del presupuesto', cifras, ola=2, seccion='5. El modelo de la torre (prediseño)')
        # docs/11 §1.1 y §4.2, y docs/16 §9.1: las mismas cifras de cabecera
        cab = [[pct(max(dv), 3)], [pct(max(ua), 3)], [decimal(r['R'], 2)]]
        buscar(ctrl, 'SI4', DOC11, 'qué le pasa a la torre en un sismo (§1.1): deriva de diseño y del umbral de daño', cab[:2],
               ola=2, seccion='1.1 ¿Qué le pasa a la torre en un sismo?')
        buscar(ctrl, 'SI5', DOC11, 'estructura y cimentación (§4.2): R, deriva con las secciones del presupuesto y con las del prediseño',
               [cab[2], [pct(max(dv), 3)], [f'{decimal(paso0.get("deriva_max_pct", 0), 2)} %']], ola=2,
               seccion='4.2 Estructura y cimentación (prediseño)')
    val = leer(SISMO / 'validacion_opensees.json')
    crit = (val or {}).get('criterios') or []
    if not crit:
        ctrl.agregar('SI2', 'docs/14', 'validación con OpenSees', 'pendiente', 'no existe data/sismo/validacion_opensees.json o no trae «criterios»', 2)
    else:
        cifras = []
        for c in crit:
            nom, x, det = c.get('criterio', ''), c.get('valor'), c.get('detalle') or ''
            if not isinstance(x, (int, float)):
                continue
            if nom.startswith('Control 1'):
                cifras.append([cientifica(x, 1)])
            elif 'Jaccard' in nom:
                cifras.append([decimal(x, 1)])
                cifras += [[n] for n in sorted(set(re.findall(r'comunes (\d+)', det)))]
            elif 'primera fluencia' in nom:
                cifras += [[f'{decimal(float(t), 2)} s'] for t in re.findall(r'OpenSees ([\d.]+) s', det)]
            else:
                cifras.append([pct(x, 2 if x * 100 >= 0.1 else 3)])
        if val.get('cumple_todo') is not True:
            ctrl.agregar('SI2', 'docs/14', 'validación con OpenSees', 'falta', 'validacion_opensees.json no cumple todo', 2)
        else:
            buscar(ctrl, 'SI2', DOC14, 'validación con OpenSees: diferencia de cada criterio', cifras, ola=2, seccion='10. Validación')
    esc = leer(SISMO / 'escenarios.json')
    if esc is None:
        ctrl.agregar('SI3', 'docs/14', 'resultados de los escenarios de referencia (Δt = 0,005 s)', 'pendiente', 'no existe data/sismo/escenarios.json', 3)
    else:
        cifras = []
        for e in esc.get('escenarios') or []:
            cifras.append([pct(e['deriva_vector_max'], 3)])
            v = e.get('cortante_basal_max_kN') or {}
            cifras.append([f'{entero(v["Vx"])} kN / {entero(v["Vy"])} kN'])
            fl = e.get('fluencia') or {}
            n = fl.get('elementos', 0)
            if n:
                por_nivel = ' / '.join(str(x.get('elementos_que_fluyen', 0)) for x in e.get('niveles') or [])
                cifras.append([f'{n}: {por_nivel}'])
            eq = e.get('equipos') or {}
            cifras.append([f'{eq.get("desliza", 0)} / {eq.get("balancea", 0)}'])
            dc = obtener(e, 'dc_max.valor')
            if isinstance(dc, (int, float)):
                cifras.append([decimal(dc, 2)])
            if e.get('factor') not in (None, 1):
                cifras.append([f'×{decimal(e["factor"], 2)}'])
        e0 = (esc.get('escenarios') or [{}])[0].get('equipos') or {}
        if e0:
            cifras += [[f'{e0["evaluados"]} equipos'], [f'{e0["anclado"]} están anclados']]
        buscar(ctrl, 'SI3', DOC14, 'resultados de los escenarios de referencia: deriva, cortante, fluencia por nivel, equipos, D/C y escala',
               cifras, ola=3, seccion='9. Resultados de los escenarios de referencia')


# interferencias de la primera corrida del modelo federado (24-oct-2026, commit 59716cb), la base del «antes» de docs/16 §8
INTERFERENCIAS_ANTES = {'fecha': '2026-10-24', 'commit': '59716cb', 'total': 932, 'por_responsable': {
    'A': {'dura': 201, 'media': 123, 'leve': 0}, 'A y B': {'dura': 33, 'media': 6, 'leve': 0},
    'A y F': {'dura': 0, 'media': 495, 'leve': 0}, 'B': {'dura': 46, 'media': 21, 'leve': 0}, 'F': {'dura': 0, 'media': 0, 'leve': 7}}}


def antes_en_git():
    """Cotejo de solo lectura de INTERFERENCIAS_ANTES con la versión guardada en el historial (si hay historial)."""
    import subprocess
    try:
        r = subprocess.run(['git', 'show', f'{INTERFERENCIAS_ANTES["commit"]}:data/bim/interferencias.json'], cwd=C.RAIZ,
                           capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return None
        return json.loads(r.stdout).get('resumen')
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def controles_bim(ctrl: Control):
    bim = leer(BIM / 'torre_hospital.bim.json')
    inter = leer(BIM / 'interferencias.json')
    vifc = leer(BIM / 'validacion_ifc.json')
    est = leer(SISMO / 'torre_hospital_estructura.json') or {}
    pres = leer(PRESUPUESTO) or {}
    if bim is None or inter is None or vifc is None:
        ctrl.agregar('BI0', 'docs/16', 'modelo BIM', 'pendiente', 'falta data/bim/torre_hospital.bim.json, interferencias.json o validacion_ifc.json', 3)
        return
    # BI1: totales y disciplinas (§4) y cabecera (En pocas palabras)
    tot = bim.get('totales') or {}
    por_disc = {k: sum(v.values()) for k, v in (bim.get('conteos') or {}).items()}
    cab = [[entero(tot['elementos'])], [entero(tot['juegos_de_barras'])], [entero(tot['barras'])], [f'{entero(tot["acero_kg"])} kg']]
    buscar(ctrl, 'BI1', DOC16, 'en pocas palabras: elementos, juegos de barras, barras y acero', cab, ola=3, seccion='En pocas palabras')
    filas = []
    for k, d in (bim.get('disciplinas') or {}).items():
        n = por_disc.get(k)
        if k == 'REF':
            filas.append([f'{entero(tot["juegos_de_barras"])} juegos ({entero(tot["barras"])} barras)'])
        elif n is not None:
            filas.append([f'| {entero(n)} |'])
    buscar(ctrl, 'BI1b', DOC16, 'organización: elementos por disciplina', filas, ola=3, seccion='4. Organización del modelo federado')
    # BI2: LOD objetivo por disciplina (§5)
    t16 = texto_doc(DOC16) or ''
    malas = []
    for k, d in (bim.get('disciplinas') or {}).items():
        if not re.search(r'^\| ' + re.escape(d['nombre']) + r' \| ' + re.escape(str(d['lod_objetivo'])) + r' \|', t16, re.M):
            malas.append(f'{d["nombre"]} (LOD {d["lod_objetivo"]})')
    ctrl.agregar('BI2', C.relativa(DOC16), 'LOIN: LOD objetivo de cada disciplina en la tabla del §5', 'falta' if malas else 'ok',
                 ('no cuadra: ' + ', '.join(malas)) if malas else '', 3)
    # BI3: georreferenciación (§7)
    g = bim.get('georreferenciacion') or {}
    buscar(ctrl, 'BI3', DOC16, 'georreferenciación: sistema, este, norte, convergencia, factor de escala y altura', [
        [g['crs']], [f'{decimal(g["este_m"], 2)} m'], [f'{decimal(g["norte_m"], 3)} m'], [f'{decimal(g["convergencia_deg"], 6)}°'],
        [decimal(g['factor_escala_punto'], 7)], [f'{entero(g["altura_ortometrica_m"])} m']], ola=3, seccion='7. Georreferenciación')
    # BI4: interferencias antes y después por responsable (§8)
    res = inter.get('resumen') or {}
    if res.get('duras_pendientes'):
        ctrl.agregar('BI4', 'data/bim/interferencias.json', 'interferencias duras pendientes', 'falta', f'{res["duras_pendientes"]} duras pendientes', 3)
    git = antes_en_git()
    if git is not None and git.get('por_responsable') != INTERFERENCIAS_ANTES['por_responsable']:
        ctrl.agregar('BI4', 'docs/16', 'interferencias «antes» frente al historial', 'falta',
                     f'el historial ({INTERFERENCIAS_ANTES["commit"]}) no coincide con las cifras documentadas', 3)
    ant, des = INTERFERENCIAS_ANTES['por_responsable'], res.get('por_responsable') or {}
    lineas = {l.split('|')[1].strip(): l for l in t16.splitlines() if l.startswith('| ') and l.count('|') >= 8}
    malas = []
    for resp in sorted(set(ant) | set(des)):
        a, d = ant.get(resp, {}), des.get(resp, {})
        celdas = ' | '.join(str(x) for x in (a.get('dura', 0), d.get('dura', 0), a.get('media', 0), d.get('media', 0), a.get('leve', 0), d.get('leve', 0)))
        linea = next((l for nombre, l in lineas.items() if nombre.endswith(f'({resp})')), None)
        if linea is None or f'| {celdas} |' not in linea:
            malas.append(f'{resp}: {celdas}')
    suma = lambda r, k: sum(x.get(k, 0) for x in r.values())
    total = ' | '.join(f'**{x}**' for x in (suma(ant, 'dura'), suma(des, 'dura'), suma(ant, 'media'), suma(des, 'media'), suma(ant, 'leve'), suma(des, 'leve')))
    if f'| {total} |' not in t16:
        malas.append(f'total: {total}')
    if f'{entero(INTERFERENCIAS_ANTES["total"])} interferencias antes y {entero(res.get("total", 0))} después' not in t16:
        malas.append(f'{INTERFERENCIAS_ANTES["total"]} antes y {res.get("total")} después')
    ctrl.agregar('BI4', C.relativa(DOC16), 'coordinación: duras, medias y leves antes y después por responsable (§8)',
                 'falta' if malas else 'ok', (('no cuadra: ' + '; '.join(malas)) if malas else '') +
                 ('' if git is not None else ' (sin historial de git: «antes» con las cifras documentadas)'), 3)
    cat = res.get('por_categoria') or {}
    queda = [[f'{cat["barras que se cruzan"]["media"]} cruces'], [f'{cat["separación libre entre barras"]["media"]} puntos'],
             [f'{cat["coherencia de la cimentación"]["media"]} de coherencia'], [f'{cat["ducto contra cimentación"]["media"]} ducto'],
             [f'{cat["concreto contra concreto"]["leve"]} contactos leves']]
    rv = inter.get('revisado') or {}
    queda += [[f'{entero(obtener(rv, "unidades_y_puertas.unidades_revisadas"))} unidades'], [f'{entero(obtener(rv, "concreto.solidos"))} sólidos'],
              [f'{entero(obtener(rv, "barras.parejas_revisadas"))} parejas'], [f'{entero(obtener(rv, "refuerzo.puntos_de_separacion"))} puntos de separación']]
    buscar(ctrl, 'BI5', DOC16, 'coordinación: lo revisado y lo que queda', queda, ola=3, seccion='8. Coordinación: detección de interferencias y su resultado')
    # BI6: cantidades frente al presupuesto (§9.1) y su efecto (docs/11 §6.3)
    cpa = {x['item']: x for x in obtener(est, 'cantidades.comparacion_presupuesto') or []}
    cpb = {x['item']: x for x in bim.get('comparacion_presupuesto') or [] if x.get('capitulo') in ('2', '3')}
    if not cpa or not cpb:
        ctrl.agregar('BI6', 'docs/16', 'cantidades contra el presupuesto', 'pendiente', 'sin comparación del prediseño o del modelo', 3)
        return
    cifras = []
    for it in sorted(set(cpa) | set(cpb), key=lambda k: [int(p) for p in k.split('.')]):
        for cp in (cpa, cpb):
            if it in cp:
                cifras.append([pesos_signo(round(cp[it]['efecto_cop']))])
    cap = lambda cp, c: sum(x['efecto_cop'] for k, x in cp.items() if k.split('.')[0] == c)
    ta, tb = sum(x['efecto_cop'] for x in cpa.values()), sum(x['efecto_cop'] for x in cpb.values())
    total_a = est['cantidades'].get('efecto_total_costo_directo_cop')
    if total_a is not None and round(total_a) != round(ta):
        ctrl.agregar('BI6', 'data/sismo/torre_hospital_estructura.json', 'efecto total = suma de los ítems', 'falta', f'{total_a} ≠ {ta}', 3)
    for c in ('2', '3'):
        cifras += [[f'**{pesos_signo(round(cap(cpa, c)))}**'], [f'**{pesos_signo(round(cap(cpb, c)))}**']]
    cifras += [[f'**{pesos(round(ta))}**'], [f'**{pesos(round(tb))}**']]
    fac, cd, vo = obtener(pres, 'aiu_valores.factor'), pres.get('costo_directo'), pres.get('valor_obra')
    m = lambda x: entero(x / 1e6)
    efecto = [[f'+${m(ta)} M a +${m(tb)} M'], [f'+${m(ta * fac)} M a +${m(tb * fac)} M'],
              [f'{decimal(ta / cd * 100, 1)} % a {decimal(tb / cd * 100, 1)} %'], [f'${m(cd)} M'],
              [f'${m(vo + ta * fac)} M o ${m(vo + tb * fac)} M'], [decimal(fac, 4)]]
    caps23 = sum(x.get('subtotal_costo_directo', 0) for x in pres.get('capitulos') or [] if str(x.get('codigo')) in ('2', '3'))
    efecto += [[f'${m(caps23)} M a ${m(caps23 + ta)} M o ${m(caps23 + tb)} M']]
    buscar(ctrl, 'BI6', DOC16, 'cantidades contra el presupuesto: efecto por ítem, por capítulo, total, con AIU y en el valor de la obra',
           cifras + efecto, ola=3, seccion='9. Cantidades contra el presupuesto (5D)')
    buscar(ctrl, 'BI7', DOC11, 'ajuste pendiente del prediseño estructural (§6.3): capítulos, total, porcentaje, AIU y valor de la obra', [
        [pesos_signo(round(cap(cpa, '2')))], [pesos_signo(round(cap(cpb, '2')))], [pesos_signo(round(cap(cpa, '3')))], [pesos_signo(round(cap(cpb, '3')))],
        [f'**{pesos(round(ta))}**'], [f'**{pesos(round(tb))}**'], [f'{decimal(ta / cd * 100, 1)} %'], [f'{decimal(tb / cd * 100, 1)} %'],
        [f'**{pesos(round(ta * fac))}**'], [f'**{pesos(round(tb * fac))}**'], [f'${m(vo + ta * fac)} M'], [f'${m(vo + tb * fac)} M'],
        [decimal(fac, 4)], [f'${m(caps23)} M']], ola=3, seccion='6.3 Ajuste pendiente del prediseño estructural')
    buscar(ctrl, 'BI8', DOC11, 'cuánto cuesta (en pocas palabras): el ajuste con y sin AIU',
           [[f'${m(ta)} M a ${m(tb)} M'], [f'${m(ta * fac)} M a ${m(tb * fac)} M']], ola=3, seccion='En pocas palabras')
    # BI9: entregables IFC4 y su validación (§11) y codificación (§6)
    arch = {Path(a['archivo']).name: a for a in vifc.get('archivos') or []}
    pri, ref = arch.get('torre_hospital.ifc') or {}, arch.get('torre_hospital_refuerzo.ifc') or {}
    if vifc.get('errores') != 0 or any((a.get('validacion_esquema') or {}).get('errores') for a in arch.values()):
        ctrl.agregar('BI9', 'data/bim/validacion_ifc.json', 'IFC sin errores', 'falta', f'errores: {vifc.get("errores")}', 3)
    mb = lambda x: decimal(x, 2 if round(x, 1) != x else 1)
    conc = pri.get('concreto') or {}
    ifc = [[f'{mb(pri["mb"])} MB'], [f'{mb(ref["mb"])} MB'], [entero(pri['entidades'])], [entero(ref['entidades'])],
           [f'{entero(obtener(ref, "acero.barras_geometria"))} barras'], [f'{entero(obtener(ref, "acero.peso_qto_kg"))} kg'],
           [f'{decimal(conc["qto_m3"], 1)} m³'], [f'{decimal(conc["geometria_ifcopenshell_m3"], 1)} m³'],
           [f'{obtener(pri, "muestra_geometria.n")} elementos'], [f'{obtener(ref, "muestra_geometria.n")} barras'],
           [f'{obtener(pri, "cinco_d.partidas")} partidas'], [f'{obtener(pri, "cuatro_d.tareas")} tareas']]
    buscar(ctrl, 'BI9', DOC16, 'entregables IFC4: tamaño, entidades, refuerzo, concreto, muestra, 5D y 4D', ifc, ola=3,
           seccion='11. Entregables IFC4 y su validación')
    pl = pri.get('plantillas_ifc4') or {}
    buscar(ctrl, 'BI10', DOC16, 'codificación: identificadores globales, compartidos y conjuntos de propiedades revisados', [
        [entero(obtener(pri, 'globalid.total'))], [entero(obtener(ref, 'globalid.total'))], [f'{obtener(vifc, "federacion.guid_compartidos")} del proyecto'],
        [f'{entero(pl.get("conjuntos_revisados", 0))} conjuntos'], [f'{entero(pl.get("propiedades_revisadas", 0))} propiedades']], ola=3,
        seccion='6. Codificación de los elementos')
    buscar(ctrl, 'BI11', DOC11, 'modelo BIM (§4.3): elementos, barras e interferencias duras antes y después', [
        [f'{entero(tot["elementos"])} elementos'], [f'{entero(tot["barras"])} barras'],
        [f'de {suma(ant, "dura")} a {suma(des, "dura")}']], ola=3, seccion='4.3 Modelo BIM')


def controles_marcas(ctrl: Control):
    for ruta in (DOC11, DOC14, DOC15, DOC16):
        t = texto_doc(ruta)
        if t is None:
            ctrl.agregar('MC', C.relativa(ruta), 'el documento existe', 'pendiente', 'todavía no existe', 2)
            continue
        n = len(RE_MARCA.findall(t))
        ctrl.agregar('MC', C.relativa(ruta), f'marcas «{MARCA}» sin llenar', 'ok' if n == 0 else 'pendiente', f'{n} marcas' if n else '', 2)
    t = texto_doc(DOC15) or ''
    ctrl.agregar('HB', 'docs/15', 'no dice «servicio habilitado» ni da la matriz como dictamen de habilitación',
                 'falta' if re.search(r'servicio habilitado', t, re.I) else 'ok')
    t14 = texto_doc(DOC14) or ''
    ctrl.agregar('HO', 'docs/14', 'texto de honestidad del 8.5', 'ok' if 'Modelo de prediseño (sin estudio de suelos ni diseño estructural firmado)' in t14 else 'falta')


def controles_vigencia(ctrl: Control):
    """1732 siempre «revocada»; 482 de 2018 solo como norma reemplazada (13.5). Línea por línea en los .md y cadena por
    cadena en los JSON (una línea de un JSON con sangría es una cadena)."""
    rutas = sorted(DOCS.glob('*.md')) + sorted(C.TORRE.glob('*.json')) + sorted((C.RAIZ / 'web' / 'data').glob('torre*.json'))
    for ruta in rutas:
        rel = C.relativa(ruta)
        if ruta.suffix == '.md':
            piezas = [(f'línea {i}', l) for i, l in enumerate(ruta.read_text(encoding='utf-8').splitlines(), 1)]
        else:
            d = leer(ruta)
            if d is None:
                continue
            piezas = []

            def textos(o, p=''):
                if isinstance(o, dict):
                    for k, v in o.items():
                        textos(v, f'{p}.{k}' if p else k)
                elif isinstance(o, list):
                    for i, v in enumerate(o):
                        textos(v, f'{p}[{i}]')
                elif isinstance(o, str):
                    piezas.append((p, o))
            textos(d)
        malas = []
        for donde, t in piezas:
            if re.match(r'^superados\.[^.]+\.buscar$', donde):
                continue          # el patrón que el normalizador reemplaza (su «reemplazo» va al lado): no es una mención
            if RE_1732.search(t) and not re.search(r'revoc', t, re.I):
                malas.append(f'{donde}: Res. 1732 sin «revocada»')
            if RE_482.search(t) and not re.search(r'1811|reemplaz|derog|→', t):
                malas.append(f'{donde}: Res. 482 de 2018 sin su reemplazo (Res. 1811 de 2025)')
        if malas:
            propio = rel in PROPIOS
            ctrl.agregar('VG', rel, 'Res. 1732 revocada y Res. 482 de 2018 reemplazada', 'falta' if propio else 'pendiente',
                         ('' if propio else 'archivo de otro equipo: ') + '; '.join(malas[:6]) + (f' … y {len(malas) - 6} más' if len(malas) > 6 else ''),
                         1 if propio else 2)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--permitir-pendientes', action='store_true', help='lo pendiente no hace fallar (olas 1 y 2)')
    ap.add_argument('--json', action='store_true', help='informe en JSON')
    a = ap.parse_args()
    ctrl = Control()
    controles_contraste(ctrl)
    controles_dotacion(ctrl)
    controles_sismo(ctrl)
    controles_bim(ctrl)
    controles_marcas(ctrl)
    controles_vigencia(ctrl)
    if a.permitir_pendientes:
        # lo de una ola posterior (docs/11 y docs/09 se actualizan en la ola 2; los resultados del motor, en la 3) no falla todavía
        for f in ctrl.filas:
            if f['estado'] == 'falta' and f['ola'] >= 2:
                f['estado'], f['detalle'] = 'pendiente', f'ola {f["ola"]}: {f["detalle"]}'
    n = {e: sum(1 for f in ctrl.filas if f['estado'] == e) for e in ('ok', 'falta', 'pendiente')}
    if a.json:
        sys.stdout.write(C.texto_json({'herramienta': 'verificar_cifras_docs', 'resumen': n, 'controles': ctrl.filas}))
    else:
        for f in ctrl.filas:
            print(f'{f["estado"]:<9} {f["id"]:<4} {f["documento"]:<45} {f["que"]}' + (f' — {f["detalle"]}' if f['detalle'] else ''))
        print(f'verificar_cifras_docs: {n["ok"]} ok, {n["falta"]} faltan, {n["pendiente"]} pendientes')
    falla = n['falta'] > 0 or (not a.permitir_pendientes and n['pendiente'] > 0)
    sys.exit(1 if falla else 0)


if __name__ == '__main__':
    main()
