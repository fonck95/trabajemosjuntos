"""Control de cifras de los documentos de la torre (equipo E; especificación de integración, 11.6 y 13.5).

    python3 scripts/torre/verificar_cifras_docs.py                         # estricto: sale 1 si algo no cuadra
    python3 scripts/torre/verificar_cifras_docs.py --permitir-pendientes   # olas 1 y 2: lo que aún no se escribe o no
                                                                           # se calcula queda «pendiente» y no hace fallar
    python3 scripts/torre/verificar_cifras_docs.py --json                  # informe completo en JSON

Lee las cifras clave de los JSON (contraste con el proyecto tipo, inventario, cierre de brechas, matriz de cumplimiento,
exigencias, prediseño y validación del motor sísmico) y comprueba que aparecen tal cual, en formato es-CO, en
docs/11-torre-hospital-nivel-1.md, docs/14-simulacion-sismica.md y docs/15-dotacion-y-habilitacion.md; que $4.555.806
(sobre 320,6 m²) y $5,42 M (sobre 270 m²) aparecen juntas; que no quedan marcas «[CIFRA]» sin llenar; y que ninguna mención
de la Res. 1732 la da como vigente ni ninguna de la Res. 482 de 2018 como norma que rige (en docs/, en los JSON de
data/proyectos/torre_hospital/ y en web/data/torre*.json).

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
SISMO = C.DATOS / 'sismo'
MARCA = '[CIFRA]'
RE_MARCA = re.compile(r'\[CIFRA(?::[^\]]*)?\]')   # «[CIFRA]» o «[CIFRA: qué va]»
RE_1732 = re.compile(r'(?<![\w_/.%-])1732(?![\d_])')
RE_482 = re.compile(r'482 de 2018')
# archivos cuyo dueño es este equipo (2.1): sus fallas de vigencia nunca se toleran como pendientes
PROPIOS = {'docs/11-torre-hospital-nivel-1.md', 'docs/09-motor-3d-y-modelos.md', 'docs/14-simulacion-sismica.md',
           'docs/15-dotacion-y-habilitacion.md', 'data/proyectos/torre_hospital/normas.json',
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
    if est is None:
        ctrl.agregar('SI1', 'docs/14', 'prediseño (sistema, R, T1, Ta, Cu·Ta, derivas)', 'pendiente', 'no existe data/sismo/torre_hospital_estructura.json (equipo A)', 2)
    else:
        pre = est.get('prediseno') or {}
        cifras = []
        for nombre, rutas, d in (('R', ('R', 'sistema.R', 'r.valor'), 2), ('T1', ('periodo_fundamental_s', 'T1_s', 'periodos.T1_s'), 2),
                                 ('Cu·Ta', ('Cu_Ta_s', 'cu_ta_s', 'periodos.Cu_Ta_s'), 2)):
            x = obtener(pre, *rutas)
            if isinstance(x, (int, float)):
                cifras.append([decimal(x, d)])
        if not cifras:
            ctrl.agregar('SI1', 'docs/14', 'prediseño', 'pendiente', 'la estructura no trae todavía prediseno con R, T1 y Cu·Ta reconocibles', 2)
        else:
            buscar(ctrl, 'SI1', DOC14, 'prediseño: R, T1 y Cu·Ta', cifras, ola=2, seccion='4. El modelo de la torre (prediseño)')
    val = leer(SISMO / 'validacion_opensees.json')
    if val is None:
        ctrl.agregar('SI2', 'docs/14', 'validación con OpenSees', 'pendiente', 'no existe data/sismo/validacion_opensees.json (equipo A, ola 2)', 2)
    else:
        nums = [v for k, v in (val.get('resumen') or {}).items() if isinstance(v, (int, float))]
        if not nums:
            ctrl.agregar('SI2', 'docs/14', 'validación con OpenSees', 'pendiente', 'el archivo no trae un bloque «resumen» numérico reconocible', 2)
        else:
            buscar(ctrl, 'SI2', DOC14, 'validación con OpenSees: errores por criterio', [[decimal(x, 2), decimal(x, 1)] for x in nums], ola=2, seccion='9. Validación')
    esc = leer(SISMO / 'escenarios_referencia.json')
    if esc is None:
        ctrl.agregar('SI3', 'docs/14', 'resultados de los escenarios de referencia (Δt = 0,005 s)', 'pendiente',
                     'no existe data/sismo/escenarios_referencia.json (salida del motor de la ola 3; formato por acordar con A y D)', 3)
    else:
        cifras = []
        for e in esc.get('escenarios') or []:
            x = obtener(e, 'deriva_vector_max_pct', 'deriva_vectorial_max_pct')
            if isinstance(x, (int, float)):
                cifras.append([decimal(x, 2)])
        buscar(ctrl, 'SI3', DOC14, 'resultados de los escenarios de referencia', cifras or [['(sin cifras reconocibles)']], ola=3,
               seccion='8. Resultados de los escenarios de referencia')


def controles_marcas(ctrl: Control):
    for ruta in (DOC11, DOC14, DOC15):
        t = texto_doc(ruta)
        if t is None:
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
