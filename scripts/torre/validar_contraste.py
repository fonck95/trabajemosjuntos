"""Valida el contraste de la torre con el proyecto tipo (equipo E; especificación de integración, 9.1 y 9.3).

    python3 scripts/torre/validar_contraste.py              # informe JSON en la salida estándar; sale 1 si hay errores duros
    python3 scripts/torre/validar_contraste.py --resumen    # solo la línea de resumen y los costos por fila (cálculo propio)
    python3 scripts/torre/validar_contraste.py --archivo otra_copia.json   # valida otra copia (pruebas)

Reglas (duras salvo que se diga):
  K1  estructura: secciones de la copia de la investigación (10 referentes, 40 filas por ambiente, 39 temas, 12 filas de
      dotación, 7 inconsistencias, conclusiones y fuentes) e ids únicos.
  K2  ambientes del programa: cada referencia de `ambientes_programa` existe en programa.json y corresponde a una sola fila
      (regla común del 3.4); ninguna fila del programa en dos filas del contraste; las filas sin referencias llevan
      `sin_recinto`; `ver_en_3d` es el recinto del 1.3 de la primera referencia y, si la planta existe, está en ella.
  K3  veredictos: `veredicto_tipo` solo en las filas con ambiente del tipo (nunca en «Sin ambiente equivalente») y en todas
      ellas; `veredicto_norma` en toda fila con mínimo numérico de la Res. 1633 (las demás dicen por qué no); los dos en
      {mejora, cumple igual, se aparta, falta}; el veredicto calculado frente a la norma coincide con las áreas; los
      conteos coinciden con `conteos_veredictos` y con el resumen.
  K4  cifras del resumen: 5 a 8, cada una con tipo de dato, base de área (o «no aplica» en los conteos), método y fuente;
      las razones se rehacen con los números de `costo_m2` y de las bases; el costo de referencia de programa.json
      ($4.555.806 sobre 320,6 m²) coincide con el del contraste.
  K5  fuentes: cada fila por ambiente con fuente del tipo, cita de la Res. 1633 y tipo de dato; cada tema, inconsistencia y
      fila de dotación con su fuente o tipo.
  K6  dotación por ambiente: cada línea de `lineas_torre` existe en el inventario (o, si el inventario falta o está
      desactualizado, en dotacion.json con el id del 1.3) con el mismo nombre; 0 < cantidad ≤ la de la línea; los ids de
      `pares` y de `cierre_brechas` existen; `servicios_torre` existe en dotacion.json; ningún precio de la torre copiado
      a mano (`costo_torre*`).
  K7  tamaño del archivo web (10.1): lo que exporta build_data.py (sin búsquedas, acceso a fuentes ni campos internos)
      pesa ≤ 150 KB (aviso desde 145 KB).
  K8  vigencia: toda mención de la Res. 1732 dice que fue revocada y la Res. 482 de 2018 solo aparece como reemplazada.
  K9  normas.json (9.3) y proyecto_tipo.json (9.1): normas agregadas con su esquema y nivel de verificación, la 1732
      «revocada», la lista de modificaciones de la 3100 con la de 2022 por confirmar, el marcapasos externo y los criterios
      18.14 y 18.15 por confirmar, y `escalamiento_a_torre.estado`.
  K10 filas del 17.6 (alineado con el proyecto tipo): en `contraste_capitulos`, con `seccion: "17.6"`, una fila por tema
      (sistema estructural, capacidad de disipación de energía, cimentación, cuantías de acero y concreto por m², luces y
      alturas), cada una con veredicto y tipo de dato (con su fuente); lo que el tipo no trae dice «por confirmar» (y la fila lleva
      `por_confirmar`); las cifras de la torre se rehacen desde el prediseño estructural
      (data/sismo/torre_hospital_estructura.json), el presupuesto y el programa, y deben aparecer tal cual (es-CO) en la
      fila. Las filas nuevas llevan `agregada: true` (K1 cuenta las 39 de la investigación aparte).
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

CONTRASTE = C.TORRE / 'proyecto_tipo_contraste.json'
PROYECTO_TIPO = C.TORRE / 'proyecto_tipo.json'
VEREDICTOS = ('mejora', 'cumple igual', 'se aparta', 'falta')
ESTADOS_PAR = ('cubre', 'cubre en parte', 'compartido', 'falta', 'se aparta', 'sobra')
SIN_RECINTO = ('no está en el programa', 'exterior sin planta', 'varios servicios')
SIN_EQ = 'Sin ambiente equivalente'
TOL_M2 = 0.05
LIMITE_WEB_KB, AVISO_WEB_KB = 150, 145
# lo que build_data.py no exporta (10.1): las búsquedas, el acceso a fuentes y los campos internos
NO_WEB = ('busquedas', 'acceso_a_fuentes')
INTERNOS = {'origen', 'ref', 'fuente_reparto', 'nota_interna', 'insumos_sha1', 'sha256_dotacion', 'generado_por'}
NORMAS_NUEVAS = ('res_2080_2026', 'res_1732_2026', 'res_914_2025', 'res_1811_2025', 'res_2065_2025', 'decreto_4725_2005',
                 'res_4816_2008', 'decreto_3770_2004')
VERIFICACION = ('literal_compilacion', 'contenido_compilacion', 'fuente_secundaria', 'por_confirmar')

REGLAS = {
    'K1': ('Estructura de la copia de la investigación e ids únicos', 'duro'),
    'K2': ('Ambientes del programa por fila (3.4) y recinto de «Ver en 3D»', 'duro'),
    'K3': ('Veredictos frente al tipo y frente a la Res. 1633 (9.1)', 'duro'),
    'K4': ('Cifras del resumen con tipo, base de área y método', 'duro'),
    'K5': ('Cada fila con fuente', 'duro'),
    'K6': ('Líneas de la torre en la dotación por ambiente', 'duro'),
    'K7': ('Tamaño del archivo web (≤ 150 KB)', 'duro'),
    'K8': ('Res. 1732 revocada y Res. 482 de 2018 reemplazada', 'duro'),
    'K9': ('normas.json (9.3) y proyecto_tipo.json (9.1)', 'duro'),
    'K10': ('Filas del 17.6: estructura, disipación, cimentación, cuantías, luces y alturas frente al tipo', 'duro'),
}
ESTRUCTURA = C.DATOS / 'sismo' / 'torre_hospital_estructura.json'
PRESUPUESTO = C.TORRE / 'presupuesto.json'
TEMAS_17_6 = ('Sistema estructural', 'Capacidad de disipación de energía', 'Cimentación', 'Cuantías de acero y concreto por m²',
              'Luces y modulación', 'Pisos y alturas')
CAPITULOS_INVESTIGACION = 39


def dec(x, d=1) -> str:
    """Número en formato es-CO con d decimales («2.483,1»)."""
    return f'{x:,.{d}f}'.replace(',', '§').replace('.', ',').replace('§', '.')


def ent(x) -> str:
    return f'{round(x):,}'.replace(',', '.')


def cifras_17_6(est, pres, prog, costo_m2) -> dict:
    """Cifras de la torre que debe decir cada fila del 17.6, rehechas desde el prediseño estructural (cálculo propio del
    equipo A, estimación sin firmar), el presupuesto y el programa: {tema: [(qué es, texto es-CO), ...]}. Las usa
    validar_contraste (K10) y, con los mismos números, quien escribe las filas."""
    pre, dis, cim, can = est['prediseno'], est['diseno'], est['cimentacion'], est['cantidades']
    sec = est['secciones'].values()
    area = prog['totales']['m2_construido_torre']
    m2_proy = prog['totales']['m2_construido_total_proyecto']
    hist = pre['historial_de_ajustes']
    col = sorted({s['b'] for k, s in est['secciones'].items() if k.startswith('C')})
    vig = sorted({(s['b'], s['h']) for k, s in est['secciones'].items() if k.startswith('V')})
    mur = sorted({s['b'] for k, s in est['secciones'].items() if k.startswith('MURO')})
    fr = est['sistema']['fraccion_cortante_porticos']
    losa = re.search(r'(\d+,\d+) m', pre['dimensiones_adoptadas']['losa']).group(1)
    R = pre['R']
    irr = pre['irregularidades']
    cfvd = next(x['valor'] for x in pre['chequeos'] if x['id'] == 'CFVD')
    pil = cim['pilotes']
    n_pil = sum(p['n'] for p in pil)
    L = sorted({p['L_m'] for p in pil})
    dados = [g for g in cim['dados'] if g['tipo'] == 'dado']
    losas = [g for g in cim['dados'] if g['tipo'] != 'dado']
    por_dado = sorted({g['pilotes'] for g in dados})
    q = can['por_tipo']
    sup = ('columnas', 'muros', 'vigas', 'losas', 'escaleras')
    m3s = sum(q[k]['m3'] for k in sup)
    m3c = sum(v['m3'] for k, v in q.items() if k not in sup)
    kgs, kgc = can['acero_superestructura_kg'], can['acero_cimentacion_kg']
    items = {it.get('codigo'): it for c_ in pres['capitulos'] for it in c_['items']}
    kg_pres_s, kg_pres_c = items['3.05']['cantidad'], items['2.13']['cantidad']
    est_cap = next(x for x in costo_m2['por_capitulo'] if x['torre_capitulos'] == ['2', '3'])
    aiu = pres['aiu_valores']['factor']
    por_m2_ajuste = (est_cap['torre_costo_directo'] + can['efecto_total_costo_directo_cop']) * aiu / m2_proy
    tipo_m2 = est_cap['tipo_dnp_por_m2_2026_sobre_269_6']
    niveles = est['bloques'][0]['niveles']
    xs = [e_['x'] for e_ in est['ejes']['x'] if not e_.get('auxiliar')]
    ys = [e_['y'] for e_ in est['ejes']['y'] if not e_.get('auxiliar')]
    luces_y = ' / '.join(dec(b - a, 2) for a, b in zip(ys, ys[1:]))
    cols = (pre.get('cuantias') or {}).get('columnas') or {}
    por_piso = {n: sum(1 for k in cols if k.endswith(f'-{n}')) for n in (1, 4)}
    retro = niveles[3]['contorno'][0][1] - niveles[0]['contorno'][0][1]
    m_lib = re.search(r'(\d+,\d+) m', prog['implantacion']['pisos_y_alturas']['altura_libre_interior'])
    h_lib = float(m_lib.group(1).replace(',', '.'))
    bajo_viga = niveles[1]['altura_entrepiso'] - h_lib - vig[0][1]
    return {
        'Sistema estructural': [
            ('muros del prediseño', f'{len(pre["eleccion_muros"]["activos"])} muros de concreto de {dec(mur[0], 2)} m'),
            ('alma de los muros', f'{dec(pre["eleccion_muros"]["longitud_alma_m"], 2)} m'),
            ('columnas', f'{dec(col[0], 2)} × {dec(col[0], 2)} m'), ('columnas del eje A', f'{dec(col[-1], 2)} × {dec(col[-1], 2)} m'),
            ('vigas', f'{dec(vig[0][0], 2)} × {dec(vig[0][1], 2)} m'), ('vigas del eje A', f'{dec(vig[-1][0], 2)} × {dec(vig[-1][1], 2)} m'),
            ('losa nervada', f'{losa} m'), ('cortante de los pórticos en x', f'{dec(100 * fr["x"], 1)} %'),
            ('cortante de los pórticos en y', f'{dec(100 * fr["y"], 1)} %'),
            ('deriva con las secciones del presupuesto', f'{dec(hist[0]["deriva_max_pct"], 2)} %'),
            ('deriva con las secciones adoptadas', f'{dec(hist[-1]["deriva_max_pct"], 2)} %')],
        'Capacidad de disipación de energía': [
            ('capacidad de disipación', dis['capacidad_disipacion']), ('Aa', f'Aa = Av = {dec(dis["Aa"], 2)}'),
            ('coeficiente de importancia', f'I = {dec(dis["I"], 1)}'), ('R0', f'R0 = {dec(R["R0"], 1)}'),
            ('Ω0', f'Ω0 = {dec(R["Omega0"], 1)}'),
            ('R', f'{dec(R["phi_a"], 1)} × {dec(R["phi_p"], 1)} × {dec(R["phi_r"], 1)} × {dec(R["R0"], 1)} = {dec(R["R"], 2)}'),
            ('irregularidad 3A', dec(irr['geometrica_3A']['cociente'], 2)), ('irregularidad 1aP', dec(irr['torsional_1P']['maximo']['x'], 3)),
            ('columna fuerte-viga débil mínima', dec(cfvd, 2))],
        'Cimentación': [
            ('pilotes', f'{n_pil} pilotes'), ('pilote', f'{dec(pil[0]["D_m"], 2)} m × {ent(L[0])} m'),
            ('metros de pilote', f'{ent(sum(p["ml"] for p in pil))} m'), ('dados', f'{len(dados)} dados de {por_dado[0]} a {por_dado[-1]} pilotes'),
            ('losas de pilotes', f'{len(losas)} losas de pilotes'),
            ('pilotes de las losas', ' y '.join(str(g['pilotes']) for g in losas)),
            ('vigas de amarre', f'{len(cim["vigas_amarre"])} vigas de amarre'), ('muros de contención', f'{len(cim["muros_contencion"])} muros de contención'),
            ('contrapiso', f'contrapiso de {dec(cim["contrapiso"]["espesor_m"], 2)} m'),
            ('capacidad de servicio por pilote', f'{ent(cim["pilote"]["capacidad_kN"]["Qadm"])} kN'),
            ('metros de pilote del presupuesto', f'{ent(items["2.04"]["cantidad"])} m')],
        'Cuantías de acero y concreto por m²': [
            ('concreto', f'{dec(m3s + m3c, 1)} m³'), ('concreto por m²', f'{dec((m3s + m3c) / area, 2)} m³/m²'),
            ('acero', f'{ent(kgs + kgc)} kg'), ('acero por m²', f'{dec((kgs + kgc) / area, 1)} kg/m²'),
            ('acero por m³', f'{ent((kgs + kgc) / (m3s + m3c))} kg/m³'),
            ('superestructura', f'{dec(m3s / area, 2)} m³/m² y {dec(kgs / area, 1)} kg/m²'),
            ('cimentación', f'{dec(m3c / area, 2)} m³/m² y {dec(kgc / area, 1)} kg/m²'),
            ('acero del presupuesto por m²', f'{dec((kg_pres_s + kg_pres_c) / area, 1)} kg/m²'),
            ('acero del presupuesto en la superestructura y en la cimentación', f'{dec(kg_pres_s / area, 1)} en la superestructura y {dec(kg_pres_c / area, 1)} en la cimentación'),
            ('área de la torre', f'{dec(area, 1)} m²'),
            ('estructura por m² en el presupuesto', '$' + ent(est_cap['torre_por_m2_con_aiu_sobre_3620_6'])),
            ('estructura por m² con el prediseño', '$' + ent(por_m2_ajuste)),
            ('estructura del tipo por m²', '$' + ent(tipo_m2)),
            ('razón frente al tipo, presupuesto', dec(est_cap['torre_por_m2_con_aiu_sobre_3620_6'] / tipo_m2, 2)),
            ('razón frente al tipo, prediseño', dec(por_m2_ajuste / tipo_m2, 2))],
        'Luces y modulación': [
            ('luces en x', f'{len(xs) - 1} luces de {dec(xs[1] - xs[0], 2)} m'), ('luces en y', f'{luces_y} m'),
            ('columnas en los pisos 1 a 3', f'{por_piso[1]} columnas'), ('columnas en el piso 4', f'{por_piso[4]} en el piso 4')],
        'Pisos y alturas': [
            ('entrepiso del piso 1', f'{dec(niveles[0]["altura_entrepiso"], 2)} m en el piso 1'),
            ('entrepiso de los pisos 2 a 4', f'{dec(niveles[1]["altura_entrepiso"], 2)} m en los pisos 2 a 4'),
            ('cubierta del piso 4', f'{dec(niveles[3]["z"], 1)} m'), ('cubierta del piso 3 sur', f'{dec(niveles[2]["z"], 1)} m'),
            ('retroceso', f'{ent(retro)} m'), ('altura libre', f'{dec(h_lib, 2)} m'), ('bajo las vigas', f'{dec(bajo_viga, 2)} m')],
    }


def num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def tiene_minimo(v) -> bool:
    """Mínimo de la Res. 1633 comparable: un número o un texto con alguna cifra («10 sin procedimientos; 14 si …»)."""
    return num(v) or (isinstance(v, str) and bool(re.search(r'\d', v)))


def textos(o, ruta=''):
    """(ruta, texto) de todas las cadenas de una estructura."""
    if isinstance(o, dict):
        for k, v in o.items():
            yield from textos(v, f'{ruta}.{k}' if ruta else k)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from textos(v, f'{ruta}[{i}]')
    elif isinstance(o, str):
        yield ruta, o


RE_1732 = re.compile(r'(?<![\w_/.-])1732(?![\d_])')
RE_482 = re.compile(r'482 de 2018')


def menciones_vigencia(o, nombre):
    """Errores de K8 en una estructura: menciones de la 1732 sin «revoc» y de la 482 de 2018 sin su reemplazo."""
    errores = []
    for ruta, t in textos(o):
        if RE_1732.search(t) and not re.search(r'revoc', t, re.I):
            errores.append(f'{nombre} → {ruta}: menciona la Res. 1732 sin decir que fue revocada')
        if RE_482.search(t) and not re.search(r'1811|reemplaz|derog|→', t):
            errores.append(f'{nombre} → {ruta}: cita la Res. 482 de 2018 sin decir que la reemplazó la Res. 1811 de 2025')
    return errores


def sin_internos(o):
    if isinstance(o, dict):
        return {k: sin_internos(v) for k, v in o.items() if k not in INTERNOS}
    if isinstance(o, list):
        return [sin_internos(x) for x in o]
    return o


def lineas_disponibles(inf: C.Informe):
    """{id de línea: (nombre, cantidad)} desde el inventario (si está al día con dotacion.json) o desde dotacion.json."""
    dot = C.cargar_json(C.DOTACION)
    desde_dot = {}
    for sv in dot.get('servicios', []):
        for lista, letra in (('equipos', 'e'), ('mobiliario', 'm')):
            for it in sv.get(lista) or []:
                desde_dot[C.id_linea(sv['id'], letra, it['nombre'])] = (it['nombre'], it.get('cantidad'), it.get('precio_unitario_cop_2026'))
    for it in dot.get('equipamiento_fijo') or []:
        desde_dot[C.id_linea('fijo', 'f', it['nombre'])] = (it['nombre'], it.get('cantidad'), it.get('precio_unitario_cop_2026'))
    for it in (dot.get('cierre_brechas_habilitacion') or {}).get('items', []):
        desde_dot[C.id_linea(it['servicio'], 'x', it['nombre'])] = (it['nombre'], it.get('cantidad'), it.get('precio_unitario_cop_2026'))
    fuente = 'dotacion.json (ids del 1.3)'
    if C.INVENTARIO.exists():
        inv = C.cargar_json(C.INVENTARIO)
        sha = (inv.get('insumos_sha1') or {}).get('dotacion.json')
        if sha and sha != C.sha1_archivo(C.DOTACION):
            inf.aviso('K6', 'inventario_dotacion.json está desactualizado frente a dotacion.json: las líneas se comprueban contra dotacion.json')
        else:
            ids_inv = {l['id']: l for l in inv.get('lineas', [])}
            faltan = [k for k in desde_dot if k not in ids_inv]
            if faltan:
                inf.aviso('K6', f'{len(faltan)} líneas de dotacion.json no están en el inventario (p. ej. {faltan[0]})')
            fuente = 'inventario_dotacion.json'
            return {k: (l.get('nombre'), l.get('cantidad'), desde_dot.get(k, (None, None, None))[2]) for k, l in ids_inv.items()}, dot, fuente
    else:
        inf.aviso('K6', 'todavía no existe inventario_dotacion.json: las líneas se comprueban contra dotacion.json')
    return desde_dot, dot, fuente


def validar(archivo: Path = CONTRASTE) -> C.Informe:
    inf = C.Informe('validar_contraste', REGLAS, archivo=C.relativa(archivo))
    try:
        c = C.cargar_json(archivo)
        programa = C.cargar_json(C.PROGRAMA)
    except (FileNotFoundError, ValueError) as e:
        inf.error('K1', str(e))
        inf.omitir_resto('no se pudo leer el contraste o el programa')
        return inf
    amb = programa['ambientes']

    # ---------------------------------------------------------------- K1
    agregadas = sum(1 for x in c.get('contraste_capitulos') or [] if x.get('seccion') == '17.6' and x.get('agregada'))
    esperado = {'referentes': 10, 'contraste_ambientes': 40, 'contraste_capitulos': CAPITULOS_INVESTIGACION + agregadas,
                'dotacion_por_ambiente': 12, 'inconsistencias_detectadas': 7}
    for k, n in esperado.items():
        inf.revisado('K1')
        if len(c.get(k) or []) != n:
            inf.error('K1', f'{k}: {len(c.get(k) or [])} filas; la investigación trae {n}'
                            + (f' (con las {agregadas} agregadas del 17.6)' if k == 'contraste_capitulos' and agregadas else ''))
    for k in ('resumen_para_la_web', 'referente_principal', 'novedades_2025_2026', 'costo_m2', 'escalamiento', 'capa_contraste_3d',
              'conclusiones', 'fuentes', 'conteos_veredictos', 'convenciones'):
        inf.revisado('K1')
        if not c.get(k):
            inf.error('K1', f'falta la sección {k}')
    for sec in ('contraste_ambientes', 'dotacion_por_ambiente', 'inconsistencias_detectadas'):
        ids = [f.get('id') for f in c.get(sec) or []]
        if len(set(ids)) != len(ids) or None in ids:
            inf.error('K1', f'{sec}: ids repetidos o faltantes')

    filas = c.get('contraste_ambientes') or []
    dfilas = c.get('dotacion_por_ambiente') or []

    # ---------------------------------------------------------------- K2
    plantas_ids = None
    if C.PLANTAS.exists():
        try:
            pl = C.cargar_json(C.PLANTAS)
            plantas_ids = {r['id'] for nv in pl.get('niveles', []) for r in nv.get('recintos', [])}
        except (ValueError, KeyError) as e:
            inf.aviso('K2', f'no se pudo leer la planta: {e}')
    else:
        inf.aviso('K2', 'todavía no existe la planta: «Ver en 3D» se comprueba solo con la regla de ids del 1.3')
    uso = {}

    def revisar_refs(f, seccion, exclusivo):
        refs = f.get('ambientes_programa')
        if not isinstance(refs, list):
            inf.error('K2', f'{f.get("id")}: ambientes_programa debe ser una lista')
            return
        filas_ref = []
        for r in refs:
            inf.revisado('K2')
            try:
                filas_ref.append(C.resolver_ambiente(r, amb))
            except C.ErrorAmbiente as e:
                inf.error('K2', f'{f.get("id")}: {e}')
        if len(set(filas_ref)) != len(filas_ref):
            inf.error('K2', f'{f.get("id")}: una fila del programa repetida en la misma fila')
        if exclusivo:
            for x in filas_ref:
                if x in uso and uso[x] != f['id']:
                    inf.error('K2', f'la fila {x} del programa está en {uso[x]} y en {f["id"]}: el color del recorrido sería ambiguo')
                uso[x] = f['id']
        if not refs:
            if f.get('sin_recinto') not in SIN_RECINTO:
                inf.error('K2', f'{f.get("id")}: sin ambientes del programa y sin «sin_recinto» válido ({SIN_RECINTO})')
            if f.get('ver_en_3d'):
                inf.error('K2', f'{f.get("id")}: una fila sin recinto no lleva «Ver en 3D»')
            return
        if f.get('sin_recinto'):
            inf.error('K2', f'{f.get("id")}: tiene ambientes del programa y también sin_recinto')
        if not filas_ref:
            return
        a = amb[filas_ref[0]]
        piso = a.get('piso')
        nivel = {'exterior (patio de servicio)': 'BT', 'subsuelo del patio de servicio': 'BT'}.get(piso) or C.prefijo_nivel(piso)
        esperado_id = C.id_recinto(nivel, filas_ref[0], 1)
        if f.get('ver_en_3d') != esperado_id:
            inf.error('K2', f'{f.get("id")}: ver_en_3d es {f.get("ver_en_3d")!r}; con la fila {filas_ref[0]} debe ser {esperado_id}')
        elif plantas_ids is not None and esperado_id not in plantas_ids:
            inf.error('K2', f'{f.get("id")}: el recinto {esperado_id} no está en la planta')

    for f in filas:
        revisar_refs(f, 'contraste_ambientes', True)
    for f in dfilas:
        revisar_refs(f, 'dotacion_por_ambiente', False)

    # ---------------------------------------------------------------- K3
    cont_t = {v: 0 for v in VEREDICTOS}
    cont_n = {v: 0 for v in VEREDICTOS}
    n_tipo = sin_norma = 0
    for f in filas:
        inf.revisado('K3')
        sin_tipo = str(f.get('ambiente_tipo', '')).startswith(SIN_EQ)
        vt, vn = f.get('veredicto_tipo'), f.get('veredicto_norma')
        if sin_tipo and vt is not None:
            inf.error('K3', f'{f["id"]}: fila «Sin ambiente equivalente» con veredicto_tipo')
        if not sin_tipo:
            n_tipo += 1
            if vt is None:
                inf.error('K3', f'{f["id"]}: fila con ambiente del tipo sin veredicto_tipo')
        for campo, v, cont in (('veredicto_tipo', vt, cont_t), ('veredicto_norma', vn, cont_n)):
            if v is None:
                continue
            if v not in VEREDICTOS:
                inf.error('K3', f'{f["id"]}: {campo} «{v}» no está en {VEREDICTOS}')
            else:
                cont[v] += 1
        if 'veredicto' in f:
            inf.error('K3', f'{f["id"]}: queda el veredicto único de la investigación; debe partirse en veredicto_tipo y veredicto_norma')
        if vn is None:
            sin_norma += 1
            if tiene_minimo(f.get('m2_min_1633')):
                inf.error('K3', f'{f["id"]}: tiene mínimo de la Res. 1633 ({f.get("m2_min_1633")!r}) y no tiene veredicto_norma')
            if not f.get('sin_veredicto_norma'):
                inf.error('K3', f'{f["id"]}: sin veredicto_norma y sin decir por qué (sin_veredicto_norma)')
        # veredicto calculado frente a la norma (filas con ambiente del tipo): se rehace con las áreas (m2_torre_comparado
        # cuando el mínimo es de un ambiente y m2_torre es el conjunto, p. ej. los 4 cubículos y la toma especial)
        if not sin_tipo and vn is not None:
            m = f.get('m2_min_comparado')
            t = f.get('m2_torre_comparado', f.get('m2_torre'))
            if not num(m) or not num(t):
                inf.error('K3', f'{f["id"]}: veredicto_norma calculado sin m2_min_comparado o sin área numérica de la torre (m2_torre_comparado)')
            elif not f.get('metodo_norma'):
                inf.error('K3', f'{f["id"]}: veredicto_norma calculado sin metodo_norma')
            else:
                calc = 'mejora' if t > m + TOL_M2 else ('cumple igual' if t >= m - TOL_M2 else 'falta')
                if calc != vn:
                    inf.error('K3', f'{f["id"]}: con {t} m² frente a {m} m² el veredicto sería «{calc}», no «{vn}»')
    cv = c.get('conteos_veredictos') or {}
    if cv.get('frente_al_tipo') != cont_t:
        inf.error('K3', f'conteos_veredictos.frente_al_tipo {cv.get("frente_al_tipo")} no coincide con las filas {cont_t}')
    if cv.get('frente_a_la_norma') != cont_n:
        inf.error('K3', f'conteos_veredictos.frente_a_la_norma {cv.get("frente_a_la_norma")} no coincide con las filas {cont_n}')
    if n_tipo != 18 or cont_t != {'mejora': 9, 'cumple igual': 4, 'se aparta': 4, 'falta': 1}:
        inf.error('K3', f'frente al tipo deben quedar 18 filas con 9/4/4/1 (dato de la investigación); quedan {n_tipo} con {cont_t}')
    if cv.get('sin_veredicto_norma') != sin_norma:
        inf.error('K3', f'conteos_veredictos.sin_veredicto_norma {cv.get("sin_veredicto_norma")} ≠ {sin_norma}')
    for f in dfilas:
        v = f.get('veredicto_tipo')
        inf.revisado('K3')
        if v is not None and v not in VEREDICTOS:
            inf.error('K3', f'{f["id"]}: veredicto_tipo «{v}» no válido')
        if v is None and not f.get('sin_equivalente_tipo'):
            inf.error('K3', f'{f["id"]}: sin veredicto_tipo y sin «sin_equivalente_tipo»')

    # ---------------------------------------------------------------- K4
    rw = c.get('resumen_para_la_web') or {}
    cifras, bases = rw.get('cifras') or [], rw.get('bases_de_area') or {}
    if not 5 <= len(cifras) <= 8:
        inf.error('K4', f'el resumen trae {len(cifras)} cifras; deben ser de 5 a 8')
    for k, b in bases.items():
        if not (num(b.get('m2')) and b['m2'] > 0 and b.get('que')):
            inf.error('K4', f'base de área {k} sin m² o sin descripción')
    for x in cifras:
        inf.revisado('K4')
        for campo in ('id', 'titulo', 'texto', 'tipo_dato', 'metodo', 'fuente'):
            if not x.get(campo):
                inf.error('K4', f'cifra {x.get("id")}: falta {campo}')
        ba = x.get('base_area')
        if isinstance(ba, list):
            for k in ba:
                if k not in bases:
                    inf.error('K4', f'cifra {x.get("id")}: base de área «{k}» no definida en bases_de_area')
        elif not (isinstance(ba, str) and ba.startswith('no aplica')):
            inf.error('K4', f'cifra {x.get("id")}: base_area debe ser una lista de bases o «no aplica (…)»')
    por_id = {x.get('id'): x for x in cifras}
    cm = c.get('costo_m2') or {}
    try:
        t_dnp, torre = cm['tipo_dnp'], cm['torre']
        b = {k: v['m2'] for k, v in bases.items()}
        chequeos = [
            ('tamano', round(b['torre_construida'] / b['tipo_texto'], 1), por_id['tamano']['valor']),
            ('area_equivalente', round(100 * 601.9 / b['torre_util']), por_id['area_equivalente']['valor']),
            ('costo_obra_civil', [round(100 * (torre['obra_civil_P2_por_m2'] / t_dnp['por_m2_2026_sobre_269_6'] - 1), 1),
                                  round(100 * (torre['obra_civil_P2_por_m2'] / t_dnp['por_m2_2026_sobre_320_6'] - 1), 1)], por_id['costo_obra_civil']['valor']),
            ('costo_obra_completa', [round(torre['valor_obra_por_m2'] / t_dnp['por_m2_2026_sobre_269_6'], 2),
                                     round(torre['valor_obra_por_m2'] / t_dnp['por_m2_2026_sobre_320_6'], 2)], por_id['costo_obra_completa']['valor']),
            ('ambientes_tipo', cont_t, por_id['ambientes_tipo']['valor']),
            ('ambientes_norma', cont_n, por_id['ambientes_norma']['valor']),
        ]
        for nombre, calc, dado in chequeos:
            inf.revisado('K4')
            if calc != dado:
                inf.error('K4', f'cifra {nombre}: el resumen dice {dado} y el cálculo da {calc}')
        # el costo por m² del tipo sobre 320,6 m²: costo directo de 2026 / área
        calc = round(t_dnp['costo_directo_2026'] / b['tipo_texto'])
        if abs(calc - t_dnp['por_m2_2026_sobre_320_6']) > 1:
            inf.error('K4', f'costo del tipo sobre 320,6 m²: {t_dnp["por_m2_2026_sobre_320_6"]} frente a {calc} calculado')
        cr = programa['proyectos_tipo'][1].get('costo_de_referencia') or {}
        inf.revisado('K4')
        if cr.get('valor_m2_pesos_2026') != t_dnp['por_m2_2026_sobre_320_6']:
            inf.error('K4', f'programa.json → proyectos_tipo[1].costo_de_referencia = {cr.get("valor_m2_pesos_2026")}; el contraste da {t_dnp["por_m2_2026_sobre_320_6"]} sobre 320,6 m²')
        if '320,6' not in str(cr.get('nota', '')) or '5,42' not in str(cr.get('nota', '')):
            inf.error('K4', 'programa.json → costo_de_referencia.nota debe decir la base (320,6 m²) y la cifra de docs/11 ($5,42 M sobre 270 m²)')
    except (KeyError, TypeError, ZeroDivisionError) as e:
        inf.error('K4', f'no se pudieron rehacer las cifras: falta {e}')

    # ---------------------------------------------------------------- K5
    for f in filas:
        inf.revisado('K5')
        for campo in ('fuente_tipo', 'cita_1633', 'tipo_dato'):
            if not f.get(campo):
                inf.error('K5', f'{f.get("id")}: sin {campo}')
    fit = c.get('fuentes_items_tipo') or {}
    for f in dfilas:
        inf.revisado('K5')
        fu = f.get('fuente_items_tipo')
        if not fu or (re.fullmatch(r'[a-z0-9_]+', fu) and fu not in fit):
            inf.error('K5', f'{f.get("id")}: fuente de los ítems del tipo vacía o no definida ({fu!r})')
    for x in c.get('contraste_capitulos') or []:
        inf.revisado('K5')
        if not x.get('tipo_dato'):
            inf.error('K5', f'tema «{x.get("tema")}»: sin tipo_dato')
    for x in c.get('inconsistencias_detectadas') or []:
        inf.revisado('K5')
        if not (x.get('donde') and x.get('tipo') and x.get('estado')):
            inf.error('K5', f'{x.get("id")}: falta donde, tipo o estado')
    for x in c.get('fuentes') or []:
        if not (x.get('titulo') and x.get('url')):
            inf.error('K5', f'fuente sin título o sin URL: {x}')

    # ---------------------------------------------------------------- K6
    lineas, dot, fuente_lineas = lineas_disponibles(inf)
    nombres = c.get('nombres_lineas') or {}
    servicios_dot = {s['id']: s for s in dot.get('servicios', [])}
    costos = []
    for f in dfilas:
        inf.revisado('K6')
        for k in f:
            if k.startswith('costo_torre'):
                inf.error('K6', f'{f["id"]}: {k} es un precio de la torre copiado a mano; se calcula al publicar desde lineas_torre (9.1)')
        lt, st = f.get('lineas_torre'), f.get('servicios_torre')
        if lt is None and st is None:
            inf.error('K6', f'{f["id"]}: sin lineas_torre ni servicios_torre')
        total, sin_precio = 0, 0
        for e in lt or []:
            inf.revisado('K6')
            lid = e.get('linea')
            if lid not in lineas:
                inf.error('K6', f'{f["id"]}: la línea {lid} no existe en {fuente_lineas}')
                continue
            nom, cant, precio = lineas[lid]
            if e.get('nombre') != nom:
                inf.error('K6', f'{f["id"]}: {lid} se llama «{nom}», no «{e.get("nombre")}»')
            q = e.get('cantidad', cant)
            if not (num(q) and 0 < q <= (cant or 0)):
                inf.error('K6', f'{f["id"]}: cantidad {q} de {lid} fuera de (0, {cant}]')
            elif precio is None:
                sin_precio += 1
            else:
                total += precio * q
        for s in st or []:
            inf.revisado('K6')
            if s not in servicios_dot:
                inf.error('K6', f'{f["id"]}: el servicio {s} no está en dotacion.json')
            else:
                total += (servicios_dot[s].get('totales') or {}).get('total_cop_2026') or 0
        # una fila de servicios completos descuenta las líneas que ya cuentan otras filas (excluye_lineas)
        for e in f.get('excluye_lineas') or []:
            inf.revisado('K6')
            lid = e.get('linea')
            if lid not in lineas:
                inf.error('K6', f'{f["id"]}: excluye_lineas cita {lid}, que no existe')
                continue
            nom, cant, precio = lineas[lid]
            if C.partes_linea(lid)[0] not in (st or []):
                inf.error('K6', f'{f["id"]}: excluye_lineas cita {lid}, que no es de sus servicios_torre')
            if e.get('nombre') != nom:
                inf.error('K6', f'{f["id"]}: {lid} se llama «{nom}», no «{e.get("nombre")}»')
            q = e.get('cantidad')
            if not (num(q) and 0 < q <= (cant or 0)):
                inf.error('K6', f'{f["id"]}: excluye {q} de {lid}, fuera de (0, {cant}]')
            elif precio is not None:
                total -= precio * q
        for p in f.get('pares') or []:
            inf.revisado('K6')
            if p.get('estado') not in ESTADOS_PAR:
                inf.error('K6', f'{f["id"]}: estado de par «{p.get("estado")}» no está en {ESTADOS_PAR}')
            for lid in p.get('items_torre') or []:
                if lid not in lineas:
                    inf.error('K6', f'{f["id"]}: el par «{p.get("item_tipo")}» cita {lid}, que no existe')
                elif not any(e.get('linea') == lid for g in dfilas for e in g.get('lineas_torre') or []) and lid not in nombres:
                    inf.error('K6', f'{f["id"]}: {lid} no tiene nombre ni en lineas_torre ni en nombres_lineas')
            cb = p.get('cierre_brechas')
            if cb is not None:
                if cb not in lineas or C.partes_linea(cb)[1] != 'x':
                    inf.error('K6', f'{f["id"]}: cierre_brechas {cb} no es una línea del cierre de brechas')
                elif cb not in nombres:
                    inf.error('K6', f'{f["id"]}: cierre_brechas {cb} sin nombre en nombres_lineas')
            if not isinstance(p.get('items_torre'), list):
                inf.error('K6', f'{f["id"]}: par «{p.get("item_tipo")}» sin la lista items_torre')
        for k, v in nombres.items():
            if k in lineas and lineas[k][0] != v:
                inf.error('K6', f'nombres_lineas: {k} se llama «{lineas[k][0]}», no «{v}»')
        costos.append((f['id'], f.get('ambiente'), total, sin_precio, f.get('costo_tipo_dnp_cop_2026'), (f.get('unidades_comparables') or {})))
    # ninguna unidad se cuenta en dos filas: Σ cantidad de una línea en todas las filas ≤ su cantidad (las filas de servicios
    # completos se llevan toda la línea menos lo que excluyen)
    uso = {}
    for f in dfilas:
        for e in f.get('lineas_torre') or []:
            if num(e.get('cantidad')):
                uso.setdefault(e.get('linea'), []).append((f['id'], e['cantidad']))
        if f.get('servicios_torre'):
            excl = {e.get('linea'): e.get('cantidad') or 0 for e in f.get('excluye_lineas') or []}
            for lid, (nom, cant, precio) in lineas.items():
                if C.partes_linea(lid)[0] in f['servicios_torre'] and C.partes_linea(lid)[1] in ('e', 'm') and (cant or 0) - excl.get(lid, 0) > 0:
                    uso.setdefault(lid, []).append((f['id'], (cant or 0) - excl.get(lid, 0)))
    for lid, usos in sorted(uso.items()):
        cant = (lineas.get(lid) or (None, None, None))[1] or 0
        if sum(q for _, q in usos) > cant:
            inf.error('K6', f'{lid}: se cuenta {sum(q for _, q in usos)} veces entre las filas ({", ".join(f"{i}: {q}" for i, q in usos)}) '
                            f'y la línea tiene {cant}: la misma unidad está en dos filas')
    inf.cabecera['costos_por_fila_calculo_propio'] = [
        {'id': i, 'ambiente': a, 'torre_cop_2026': t, 'lineas_sin_precio': s, 'tipo_cop_2026': ct,
         **({'torre_por_unidad': round(t / u['torre']), 'tipo_por_unidad': round(ct / u['tipo'])} if u.get('torre') and ct else {})}
        for i, a, t, s, ct, u in costos]
    inf.cabecera['metodo_costos_por_fila'] = ('Σ precio de dotacion.json × cantidad de la fila (lineas_torre[].cantidad, la parte de '
                                               'la línea que va a ese ambiente); en las filas de servicios completos, los totales de '
                                               'esos servicios menos excluye_lineas. Es lo que la web debe mostrar.')
    # lo publicado por build_data.py (equipo D) debe coincidir con este cálculo
    web = C.RAIZ / 'web' / 'data' / 'torre_contraste.json'
    if web.exists():
        pub = {f.get('id'): f for f in (C.cargar_json(web).get('dotacion_por_ambiente') or [])}
        for i, a, t, s_, ct, u in costos:
            v = (pub.get(i) or {}).get('costo_torre_cop_2026')
            if v != t:
                inf.aviso('K6', f'{i}: web/data/torre_contraste.json publica {v} y el cálculo de la fila da {t} '
                                '(build_data.py debe usar la cantidad de la fila y descontar excluye_lineas)')

    # ---------------------------------------------------------------- K7
    web = sin_internos({k: v for k, v in c.items() if k not in NO_WEB})
    kb = len(json.dumps(web, ensure_ascii=False, separators=(',', ':')).encode('utf-8')) / 1024
    inf.revisado('K7')
    inf.cabecera['tamano_web_kb'] = round(kb, 1)
    if kb > LIMITE_WEB_KB:
        inf.error('K7', f'el archivo web pesaría {kb:.1f} KB (máximo {LIMITE_WEB_KB} KB del 10.1)')
    elif kb > AVISO_WEB_KB:
        inf.aviso('K7', f'el archivo web pesaría {kb:.1f} KB: queda poco margen bajo los {LIMITE_WEB_KB} KB (build_data.py agrega el costo de cada fila)')

    # ---------------------------------------------------------------- K8
    for nombre, obj in (('proyecto_tipo_contraste.json', web), ('normas.json', C.cargar_json(C.NORMAS)), ('proyecto_tipo.json', C.cargar_json(PROYECTO_TIPO))):
        inf.revisado('K8')
        for m in menciones_vigencia(obj, nombre):
            inf.error('K8', m)

    # ---------------------------------------------------------------- K9
    n = C.cargar_json(C.NORMAS)
    por = {x.get('id'): x for x in n.get('normas', [])}
    for nid in NORMAS_NUEVAS:
        inf.revisado('K9')
        x = por.get(nid)
        if not x:
            inf.error('K9', f'normas.json: falta {nid}')
            continue
        for campo in ('numero', 'anio', 'emisor', 'objeto', 'estado', 'url', 'fecha_consulta', 'requisitos_aplicables', 'lo_que_no_trae'):
            if x.get(campo) in (None, ''):
                inf.error('K9', f'normas.json → {nid}: falta {campo}')
        for r in x.get('requisitos_aplicables') or []:
            if not (r.get('requisito') and r.get('cita') and r.get('tipo')):
                inf.error('K9', f'normas.json → {nid}: requisito sin texto, cita o tipo')
            if r.get('verificacion') not in VERIFICACION:
                inf.error('K9', f'normas.json → {nid}: requisito «{r.get("tema")}» sin nivel de verificación válido ({VERIFICACION})')
    if por.get('res_1732_2026', {}).get('estado') != 'revocada':
        inf.error('K9', 'normas.json → res_1732_2026.estado debe ser «revocada»')
    e3100 = por.get('res_3100_2019', {}).get('estado', '')
    if not re.search(r'1138 o 1410; por confirmar', e3100):
        inf.error('K9', 'normas.json → res_3100_2019.estado: la modificación de 2022 debe decir «1138 o 1410; por confirmar»')
    urg = next((x for x in n.get('servicios_3100', []) if str(x.get('servicio', '')).startswith('Urgencias')), {})
    dm = urg.get('dotacion_minima', '')
    if 'marcapasos' in dm and not re.search(r'marcapasos externo, según guía secundaria; por confirmar', dm):
        inf.error('K9', 'normas.json → servicios_3100 (urgencias): el marcapasos externo debe decir «según guía secundaria; por confirmar»')
    for ruta, t in textos(n):
        if re.search(r'criterio 18\.1[45]', t) and 'por confirmar' not in t:
            inf.error('K9', f'normas.json → {ruta}: el criterio 18.14 o 18.15 debe quedar «por confirmar»')
    pt = C.cargar_json(PROYECTO_TIPO)
    inf.revisado('K9')
    if pt.get('escalamiento_a_torre', {}).get('estado') != 'escenario inicial superado por programa.json (4 pisos, 3.369,6 m²)':
        inf.error('K9', 'proyecto_tipo.json → escalamiento_a_torre.estado no tiene el texto del 9.1')

    # ---------------------------------------------------------------- K10
    validar_17_6(inf, c, programa)
    return inf


def validar_17_6(inf: C.Informe, c: dict, programa: dict) -> None:
    """K10: filas del 17.6 en contraste_capitulos, con las cifras de la torre rehechas desde el prediseño."""
    caps = c.get('contraste_capitulos') or []
    filas = [x for x in caps if x.get('seccion') == '17.6']
    por_tema = {}
    for x in filas:
        por_tema.setdefault(x.get('tema'), []).append(x)
    for tema in TEMAS_17_6:
        inf.revisado('K10')
        if len(por_tema.get(tema, [])) != 1:
            inf.error('K10', f'el 17.6 pide una fila «{tema}» con seccion 17.6; hay {len(por_tema.get(tema, []))}')
    for tema in por_tema:
        if tema not in TEMAS_17_6:
            inf.error('K10', f'fila «{tema}» marcada 17.6 que no es un tema del 17.6 ({", ".join(TEMAS_17_6)})')
    temas = [x.get('tema') for x in caps]
    if len(set(temas)) != len(temas):
        inf.error('K10', 'contraste_capitulos: temas repetidos (las filas del 17.6 reemplazan las de la investigación con el mismo tema)')
    for x in filas:
        inf.revisado('K10')
        t = x.get('tema')
        if x.get('veredicto') not in VEREDICTOS:
            inf.error('K10', f'«{t}»: veredicto «{x.get("veredicto")}» no está en {VEREDICTOS}')
        for campo in ('tipo', 'torre', 'explicacion', 'tipo_dato'):
            if not x.get(campo):
                inf.error('K10', f'«{t}»: falta {campo}')
        pc = 'por confirmar' in str(x.get('tipo', '')).lower()
        if pc and not x.get('por_confirmar'):
            inf.error('K10', f'«{t}»: el tipo dice «por confirmar» y la fila no lleva por_confirmar')
        if x.get('por_confirmar') and not any('por confirmar' in str(x.get(k, '')).lower() for k in ('tipo', 'torre', 'explicacion')):
            inf.error('K10', f'«{t}»: lleva por_confirmar y ningún texto dice qué está por confirmar')
        if re.search(r'\.json|\b[a-z]+_[a-z0-9_]+\b', ' '.join(str(x.get(k, '')) for k in ('tipo', 'torre', 'explicacion'))):
            inf.error('K10', f'«{t}»: el texto cita rutas o claves internas (la web no las muestra)')
    if not ESTRUCTURA.exists():
        inf.aviso('K10', 'todavía no existe el prediseño estructural: las cifras de las filas del 17.6 no se pudieron rehacer')
        return
    try:
        est = C.cargar_json(ESTRUCTURA)
        esperadas = cifras_17_6(est, C.cargar_json(PRESUPUESTO), programa, c.get('costo_m2') or {})
    except (KeyError, StopIteration, AttributeError, IndexError, TypeError, ValueError) as e:
        inf.error('K10', f'no se pudieron rehacer las cifras del 17.6 desde el prediseño: {type(e).__name__}: {e}')
        return
    viejos = [k for k, h in (est.get('insumos_sha1') or {}).items() if (C.RAIZ / k).exists() and C.sha1_archivo(C.RAIZ / k) != h]
    if viejos:
        inf.aviso('K10', f'el prediseño estructural está desactualizado frente a {", ".join(viejos)}: regenerarlo y revisar las cifras')
    for tema, cifras in esperadas.items():
        x = (por_tema.get(tema) or [None])[0]
        if not x:
            continue
        texto = ' '.join(str(x.get(k, '')) for k in ('tipo', 'torre', 'explicacion')).replace('\u00a0', ' ').replace('\u202f', ' ')
        for que, cifra in cifras:
            inf.revisado('K10')
            if cifra not in texto:
                inf.error('K10', f'«{tema}»: no dice {cifra} ({que}, rehecho desde el prediseño, el presupuesto o el programa)')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--resumen', action='store_true', help='solo la línea de resumen y los costos por fila')
    ap.add_argument('--archivo', type=Path, default=CONTRASTE, help='contraste a validar (por defecto, el del repositorio)')
    a = ap.parse_args()
    inf = validar(a.archivo)
    if a.resumen:
        d = inf.como_dict()
        for x in d.get('costos_por_fila_calculo_propio', []):
            print(json.dumps(x, ensure_ascii=False))
        print(f'tamaño web ≈ {d.get("tamano_web_kb")} KB')
        for r in d['reglas']:
            for m in r['errores'] + r['avisos']:
                print(f'{r["regla"]} {"ERROR" if m in r["errores"] else "aviso"}: {m}')
        print(f'validar_contraste: {d["errores_duros"]} errores duros, {d["avisos"]} avisos')
        sys.exit(1 if d['errores_duros'] else 0)
    inf.salir()


if __name__ == '__main__':
    main()
