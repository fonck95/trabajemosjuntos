#!/usr/bin/env python3
"""D3 · Regalías y fondos externos de Yondó (2004–2027).

Calcula tres cosas y las guarda en data/comparativa/sgr_fondos.json:

1. Proyectos de regalías (SGR) por periodo de gobierno: lo aprobado, lo pagado, lo
   terminado y lo que no; la "plata girada sin avance físico equivalente"; los
   proyectos devueltos a la MGA, desaprobados o sin contratar.
2. Asignaciones directas del SGR por bienio (2012–2026) frente a lo aprobado y lo
   comprometido, y las regalías directas del régimen anterior (2004–2011).
3. Fondos y mecanismos que Yondó no usó o usó poco, con lo que lograron municipios
   comparables y un rango de lo que pudo gestionarse.

Fuentes: archivos de data/fuentes/ y consultas a datos.gov.co (API Socrata). Las
respuestas de la API se guardan en una carpeta temporal (variable SGR_CACHE) para
no repetir descargas. Montos en pesos corrientes del año indicado.

Uso: python3 scripts/sgr_fondos.py
"""
import csv
import hashlib
import json
import os
import re
import statistics
import subprocess
import tempfile
import unicodedata
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

R = Path(__file__).resolve().parent.parent
D = R / 'data'
OUT = D / 'comparativa' / 'sgr_fondos.json'
CACHE = Path(os.environ.get('SGR_CACHE', Path(tempfile.gettempdir()) / 'sgr_fondos_cache'))
CORTE = '2026-10-21'
SOCRATA = 'https://www.datos.gov.co/resource/{}.json'

PERIODOS = ['2004-2007', '2008-2011', '2012-2015', '2016-2019', '2020-2023', '2024-2027']
YONDO_DANE = '05893'
COMPARABLES = {  # código DANE: (nombre, ¿PDET?, código CHIP)
    '05579': ('Puerto Berrío', False, '217905579'),
    '05585': ('Puerto Nare', False, '218505585'),
    '05604': ('Remedios', True, '210405604'),
    '05736': ('Segovia', True, '213605736'),
    '13160': ('Cantagallo', True, '216013160'),
    '13670': ('San Pablo', True, '217013670'),
    '13744': ('Simití', True, '214413744'),
    '68081': ('Barrancabermeja', False, '218168081'),
}
CHIP_YONDO = '219305893'


# ----------------------------------------------------------------------------- utilidades
def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def mm(x):
    """Pesos → millones de pesos, redondeado a 1 decimal."""
    return round(x / 1e6, 1)


def cop(x, dec=0):
    """Pesos → texto en millones con formato colombiano (punto de miles, coma decimal)."""
    t = f"{x / 1e6:,.{dec}f}"
    return t.replace(',', 'X').replace('.', ',').replace('X', '.')


def pct(x, dec=1):
    return f"{x:.{dec}f}".replace('.', ',')


def norm(s):
    return unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().upper().strip()


def periodo_de(anio):
    for p in PERIODOS:
        a, b = int(p[:4]), int(p[5:])
        if a <= anio <= b:
            return p
    return None


def _get(url):
    CACHE.mkdir(parents=True, exist_ok=True)
    fn = CACHE / (hashlib.md5(url.encode()).hexdigest() + '.json')
    if fn.exists():
        return json.loads(fn.read_text(encoding='utf-8'))
    try:
        with urllib.request.urlopen(url, timeout=180) as r:
            txt = r.read().decode('utf-8')
    except Exception:  # p. ej. un proxy con certificado propio: curl usa el almacén del sistema
        txt = subprocess.run(['curl', '-sS', '-m', '300', url], capture_output=True, text=True, check=True).stdout
    data = json.loads(txt)
    if isinstance(data, dict):
        raise RuntimeError(f'Error de la API: {data}')
    fn.write_text(txt, encoding='utf-8')
    return data


def socrata(dataset, where=None, limit=50000, **extra):
    q = {'$limit': str(limit)}
    if where:
        q['$where'] = where
    q.update(extra)
    return _get(SOCRATA.format(dataset) + '?' + urllib.parse.urlencode(q))


def socrata_in(dataset, campo, valores, paso=40):
    out = []
    for i in range(0, len(valores), paso):
        chunk = valores[i:i + paso]
        out += socrata(dataset, f"{campo} in(" + ','.join(f"'{v}'" for v in chunk) + ')')
    return out


# ----------------------------------------------------------------------------- fuentes
FUENTES = [
    {'id': 'proyectos_sgr', 'nombre': 'Proyectos de regalías de Yondó (cruce GESPROY + MapaInversiones por BPIN)', 'archivo': 'data/fuentes/proyectos_sgr.csv',
     'url': 'https://www.datos.gov.co/d/mzgh-shtp y https://www.datos.gov.co/d/cf9k-55fw', 'uso': 'estado, valor, pagos y avance físico y financiero de 287 proyectos'},
    {'id': 'v4ap', 'nombre': 'DNP-EjecucionFinancieraProy (MapaInversiones): fuentes y vigencias de cada proyecto', 'url': 'https://www.datos.gov.co/d/v4ap-cvae',
     'uso': 'año de aprobación (primera vigencia con recursos SGR) y valor de asignaciones directas aprobadas por bienio'},
    {'id': 'uwns', 'nombre': 'DNP-ProyectosContratos: contratos asociados a cada BPIN', 'url': 'https://www.datos.gov.co/d/uwns-mbwd',
     'uso': 'proyectos aprobados sin contrato registrado o contratados más de un año después (solo conteos y valores; no se publican nombres)'},
    {'id': 'br9a', 'nombre': 'MinHacienda – Ejecución financiera de regalías por proyecto, bienio 2025-2026', 'url': 'https://www.datos.gov.co/d/br9a-gygu',
     'uso': 'aprobado y pagado por proyecto en 2025-2026'},
    {'id': 'e624', 'nombre': 'MinHacienda – Situación de caja para regalías, bienio 2025-2026', 'url': 'https://www.datos.gov.co/d/e624-d9uy',
     'uso': 'presupuesto, aprobado, pagado y saldo en caja por fuente, para Yondó y comparables'},
    {'id': 'ovcf_gastos', 'nombre': 'Contraloría (CHIP) – OVCF SGR, programación y ejecución de gastos', 'url': 'https://www.datos.gov.co/d/xr2w-9eg2 y https://www.datos.gov.co/d/qkv4-ek54',
     'uso': 'apropiación definitiva, compromisos y pagos del capítulo SGR al cierre de 2021-2022, 2023-2024 y a junio de 2026'},
    {'id': 'ovcf_ingresos', 'nombre': 'Contraloría (CHIP) – OVCF SGR, programación de ingresos', 'url': 'https://www.datos.gov.co/d/5ka2-and2',
     'uso': 'disponibilidad inicial (saldo que pasa de un bienio al siguiente)'},
    {'id': 'chip_hist', 'nombre': 'Presupuesto de ingresos y gastos del SGR histórico (CHIP)', 'url': 'https://www.datos.gov.co/d/rr3v-r3jc y https://www.datos.gov.co/d/wtyw-nhcv',
     'uso': 'cierre del bienio 2015-2016 (2016-T4) y corte de 2017-2018 (2018-T3)'},
    {'id': 'mapa_regalias', 'nombre': 'DNP-DistribucionFuentesFinanciacion (MapaRegalías)', 'url': 'https://www.datos.gov.co/d/h6yd-ei3n',
     'uso': 'asignaciones directas distribuidas a Yondó por vigencia, 2012-2025'},
    {'id': 'terridata', 'nombre': 'DNP – TerriData (SICODIS SGR, OEC/FUT)', 'url': 'https://terridata.dnp.gov.co/index-app.html#/perfiles/05893',
     'archivo': 'data/fuentes/serie_fiscal_oec.csv', 'uso': 'regalías giradas 2004-2011; asignaciones SGR 2012-2018 y saldo de directas a junio de 2018'},
    {'id': 'art_oxi', 'nombre': 'ART – Base de proyectos de Obras por Impuestos 2018-2025 (corte 5-ago-2025)', 'url': 'https://www.renovacionterritorio.gov.co/sites/default/files/2025-10/proyectos_2018_2025.pdf',
     'uso': 'proyectos propios y multimunicipales de Obras por Impuestos por municipio'},
    {'id': 'fondo_adaptacion', 'nombre': 'Proyectos Fondo Adaptación', 'url': 'https://www.datos.gov.co/d/8yvj-6du4', 'uso': 'intervenciones por municipio'},
    {'id': 'centros_digitales', 'nombre': 'MinTIC – Centros Digitales Rurales (corte 31-oct-2023)', 'url': 'https://www.datos.gov.co/d/fybg-535s', 'uso': 'sedes conectadas e inversión por municipio'},
    {'id': 'pdet', 'nombre': 'ART – Iniciativas PDET', 'url': 'https://www.datos.gov.co/d/gmvf-t63e', 'uso': 'iniciativas con ruta de implementación activada'},
    {'id': 'apc', 'nombre': 'APC-Colombia – Recursos de cooperación internacional no reembolsables', 'url': 'https://www.datos.gov.co/d/2d3i-f9wd', 'uso': 'intervenciones de cooperación que mencionan a Yondó o su región'},
    {'id': 'fenoge', 'nombre': 'FENOGE – comunicados de proyectos entregados (hospitales y colegios)', 'url': 'https://fenoge.gov.co/documentos-noticias/2025/Comunicado_entrega_de_hospital_publico_autosostenible_en_Simiti_Bolivar.pdf',
     'uso': 'costo de referencia de un hospital solar y eficiente'},
    {'id': 'anexos', 'nombre': 'Anexos B, C y D de la investigación', 'archivo': 'docs/anexos/B-finanzas-regalias.md, docs/anexos/C-hospital-2028.md, docs/anexos/D-energia-mintic.md',
     'uso': 'convocatoria del Incentivo a la Producción 2025, casos FENOGE, Findeter'},
]

# ----------------------------------------------------------------------------- 1. proyectos
EJECUTOR_MUNICIPAL = {'MUNICIPIO DE YONDO', 'YONDOANTIOQUIA', 'ESE HOSPITAL HECTOR ABAD GOMEZ'}


def tipo_ejecutor(ej):
    e = norm(ej)
    if e in EJECUTOR_MUNICIPAL:
        return 'municipio'
    if 'YONDO E.S.P' in e or ('SERVICIOS PUBLICOS' in e and 'YONDO' in e):
        return 'empresa_servicios_publicos_municipal'
    if e in ('ANTIOQUIA', 'DEPARTAMENTO DE ANTIOQUIA') or 'CULTURA Y PATRIMONIO DE ANTIOQUIA' in e or 'VIVIENDA  DE ANTIOQUIA' in e \
            or 'VIVIENDA DE ANTIOQUIA' in e or 'FERROCARRIL DE ANTIOQUIA' in e:
        return 'departamento'
    if 'INSTITUTO NACIONAL DE VIAS' in e or 'COLCIENCIAS' in e or 'CORMAGDALENA' in e or 'MAGDALENA - CORMAGDALENA' in e:
        return 'nacion'
    if e == 'OCAD PAZ':
        return 'por_definir_ocad_paz'
    if 'ASOCIACION DE MUNICIPIOS' in e or 'PROVINCIA ADMINISTRATIVA' in e or 'REGION EJE CAFETERO' in e:
        return 'asociacion_o_provincia'
    if 'UNIVERSIDAD' in e or 'CORPORACION CENTRO DE CIENCIA' in e:
        return 'universidad_o_centro'
    if 'CONSEJO COMUNITARIO' in e:
        return 'consejo_comunitario'
    if 'CARACOLI' in e or 'PUERTO NARE' in e or 'CANTAGALLO' in e:
        return 'otro_municipio'
    return 'otro'


def clase_estado(r, fis):
    es, em, sub = r['estado_sgr'], r['estado_mapa'], r['subestado']
    if es == 'DESAPROBADO' or em == 'Desaprobado':
        return 'desaprobado'
    if es in ('TERMINADO', 'EN EJECUCIÓN') or em in ('Terminado', 'En Ejecución', 'Aprobado'):
        if es == 'TERMINADO' or (es == '' and em == 'Terminado') or (es == 'EN EJECUCIÓN' and em == 'Terminado' and fis is not None and fis >= 95):
            return 'terminado'
        if em == 'Aprobado':
            return 'aprobado_sin_iniciar'
        return 'en_ejecucion'
    if 'Devuelto a MGA' in sub:
        return 'devuelto_mga'
    if em == 'No Viable':
        return 'no_viable'
    if em == 'No Aprobado':
        return 'no_aprobado'
    if em == 'Viable':
        return 'viable_sin_aprobar'
    return 'en_formulacion'


APROBADAS = ('terminado', 'en_ejecucion', 'aprobado_sin_iniciar')
MULTI_PAT = re.compile(r'MUNICIPIOS|DEPARTAMENTO DE  ?ANTIOQUIA|NIVEL +NACIONAL|SUBREGION|REGION MAGDALENA|67 MUNICIPIOS')


def proyectos():
    rows = list(csv.DictReader(open(D / 'fuentes/proyectos_sgr.csv', encoding='utf-8')))
    bpins = [r['bpin'] for r in rows]
    v4 = socrata_in('v4ap-cvae', 'bpin', bpins)
    contr = socrata_in('uwns-mbwd', 'bpin', bpins)
    br9a = socrata('br9a-gygu', f"codigodaneentidad='{YONDO_DANE}'")

    v4b = defaultdict(list)
    for x in v4:
        v4b[x['bpin']].append(x)
    cb = defaultdict(list)
    for x in contr:
        cb[x['bpin']].append(x)
    mh = defaultdict(lambda: [0.0, 0.0, set()])
    for x in br9a:
        a = mh[x['codigobpin']]
        a[0] += f(x['recursosaprobadosasignadosspgr'])
        a[1] += f(x['apropiacionpagada'])
        a[2].add(x['codigofondo'])

    items = []
    for r in rows:
        b = r['bpin']
        fis = f(r['ej_fis']) if r['ej_fis'] != '' else None
        fin = f(r['ej_fin']) if r['ej_fin'] != '' else None
        clase = clase_estado(r, fis)
        aprobada = clase in APROBADAS
        # año de referencia
        sgr = [x for x in v4b[b] if x['fuentedefinanciaci_n'].startswith('SGR')]
        con_plata = [int(x['vigencia']) for x in sgr if f(x['valorinicial']) > 0 or f(x['valorvigente']) > 0 or f(x['valorpagado']) > 0]
        anio_bpin = int(b[:4])
        hz = int(r['horizonte'][:4]) if r['horizonte'][:4].isdigit() else None
        cs = cb.get(b, [])
        vig_c = sorted(int(x['vigenciacontrato']) for x in cs if (x.get('vigenciacontrato') or '').isdigit())
        primer_c = vig_c[0] if vig_c else None
        anio_incierto = False
        if aprobada or clase == 'desaprobado':
            if con_plata:
                # MapaInversiones registra el valor inicial en el primer año del bienio: la aprobación pudo
                # ser ese año o el siguiente. Cota inferior: el año del BPIN (no se aprueba antes de registrar).
                v0 = min(con_plata)
                anio = max(anio_bpin, v0)
                base_anio = 'máximo entre el año del BPIN y la primera vigencia con recursos SGR (MapaInversiones v4ap-cvae)'
                if anio == v0 and v0 >= 2013 and v0 % 2 == 1 and hz and hz >= v0 + 1 and (primer_c is None or primer_c >= v0 + 1):
                    anio = v0 + 1
                    base_anio += '; segundo año del bienio porque el horizonte y el primer contrato empiezan ese año'
                anio_incierto = anio in (2015, 2019, 2023)
            elif hz:
                anio, base_anio = max(hz, anio_bpin), 'inicio del horizonte del proyecto'
            else:
                anio, base_anio = anio_bpin, 'año del BPIN'
        else:
            anio, base_anio = anio_bpin, 'año de registro del BPIN (formulación)'
        per = periodo_de(anio)
        # valores
        vs, vm, vv = f(r['valor_total_sgr']), f(r['valor_total_mapa']), f(r['valor_vigente'])
        pm = f(r['pagado'])
        mhb = mh.get(b)
        flags = []
        if aprobada or clase == 'desaprobado':
            if vs > 0:
                valor, fv = vs, 'GESPROY (valor total)'
            elif vv > 0:
                valor, fv = vv, 'MapaInversiones (valor vigente)'
            elif mhb and mhb[0] > 0:
                valor, fv = mhb[0], 'MinHacienda SPGR 2025-2026 (aprobado)'
            else:
                valor, fv = vm, 'MapaInversiones (valor total)'
            otros = [x for x in (vm, vv) if x > 0]
            if valor > 0 and any(abs(x - valor) / valor > 0.25 for x in otros):
                flags.append('valor distinto entre GESPROY y MapaInversiones (>25 %)')
        else:
            valor, fv = vm, 'MapaInversiones (valor formulado)'
        # pagado
        if aprobada:
            if r['estado_sgr'] and fin is not None:
                pagado, fp = valor * min(fin, 100) / 100, 'valor × ejecución financiera (GESPROY)'
                if fin > 100:
                    flags.append(f'ejecución financiera de {fin:.0f} % (pagos por encima del valor registrado)')
            elif mhb and not r['estado_sgr']:
                pagado, fp = min(mhb[1], valor) if valor else mhb[1], 'pagado bienio 2025-2026 (MinHacienda)'
            else:
                pagado, fp = min(pm, valor) if valor else 0.0, 'pagado MapaInversiones (topado al valor)'
            if pm > valor * 1.05 and valor > 0:
                flags.append(f'MapaInversiones reporta pagos de {cop(pm)} M, más que el valor aprobado')
        else:
            pagado, fp = 0.0, None
        # girado sin avance físico equivalente
        gsa = None
        if aprobada and fis is not None and fin is not None and r['estado_sgr']:
            gsa = valor * max(0.0, min(fin, 100) - fis) / 100
        # contratos (solo conteos y valores; no se publican nombres)
        sin_contrato = aprobada and not cs and anio <= int(CORTE[:4]) - 1
        contratado_tarde = aprobada and primer_c is not None and primer_c - anio >= 2
        if aprobada and fis is not None and fis < 90 and clase == 'terminado':
            flags.append(f'figura como terminado con {fis:.0f} % de avance físico')
        te = tipo_ejecutor(r['ejecutor'])
        grupo = 'municipio' if te in ('municipio', 'empresa_servicios_publicos_municipal') else 'otros'
        multi = bool(MULTI_PAT.search(norm(r['nombre']))) and grupo == 'otros'
        items.append({
            'bpin': b, 'nombre': re.sub(r'\s+', ' ', r['nombre']).strip()[:160], 'sector': r['sector'].capitalize(),
            'anio': anio, 'base_anio': base_anio, 'anio_en_bienio_compartido': anio_incierto, 'periodo': per, 'horizonte': r['horizonte'],
            'clase': clase, 'estado_gesproy': r['estado_sgr'] or None, 'estado_mapa': r['estado_mapa'], 'subestado': r['subestado'].replace('\xa0', ' ').strip(),
            'ejecutor': r['ejecutor'], 'tipo_ejecutor': te, 'grupo_ejecutor': grupo, 'multimunicipal': multi,
            'ocad': r['ocad'] or None, 'valor': round(valor), 'fuente_valor': fv,
            'pagado': round(pagado), 'fuente_pagado': fp, 'ej_fisica': fis, 'ej_financiera': fin,
            'girado_sin_avance': round(gsa) if gsa is not None else None,
            'contratos_registrados': len(cs), 'valor_contratos': round(sum(f(x.get('valorcontrato')) for x in cs)),
            'primer_contrato_vigencia': primer_c, 'sin_contrato_registrado': sin_contrato, 'contratado_mas_de_un_anio_despues': contratado_tarde,
            'minhacienda_2025_2026': {'aprobado': round(mhb[0]), 'pagado': round(mhb[1]), 'fondos': sorted(mhb[2])} if mhb else None,
            'alertas_datos': flags,
        })
    return items


def agregar(items, gob):
    out = []
    for p in PERIODOS:
        its = [i for i in items if i['periodo'] == p]

        def bloque(sub):
            ap = [i for i in sub if i['clase'] in APROBADAS]
            return {
                'n_aprobados': len(ap),
                'aprobado': sum(i['valor'] for i in ap),
                'pagado': sum(i['pagado'] for i in ap),
                'terminados': {'n': sum(1 for i in ap if i['clase'] == 'terminado'), 'valor': sum(i['valor'] for i in ap if i['clase'] == 'terminado')},
                'sin_terminar': {'n': sum(1 for i in ap if i['clase'] != 'terminado'), 'valor': sum(i['valor'] for i in ap if i['clase'] != 'terminado')},
                'girado_sin_avance': sum(i['girado_sin_avance'] or 0 for i in ap),
                'n_con_girado_sin_avance': sum(1 for i in ap if (i['girado_sin_avance'] or 0) > 0),
            }

        def conteo(cl):
            s = [i for i in its if i['clase'] == cl]
            m = [i for i in s if i['grupo_ejecutor'] == 'municipio']
            return {'n': len(s), 'valor_formulado': sum(i['valor'] for i in s),
                    'formulados_por_el_municipio': {'n': len(m), 'valor_formulado': sum(i['valor'] for i in m)},
                    'formulados_por_otros': {'n': len(s) - len(m), 'valor_formulado': sum(i['valor'] for i in s) - sum(i['valor'] for i in m)}}

        ap = [i for i in its if i['clase'] in APROBADAS]
        top = sorted([i for i in ap if (i['girado_sin_avance'] or 0) > 0], key=lambda i: -i['girado_sin_avance'])
        out.append({
            'periodo': p, 'alcalde': gob.get(p),
            'n': len(its), **bloque(its),
            'por_ejecutor': {'municipio': bloque([i for i in its if i['grupo_ejecutor'] == 'municipio']),
                             'otros': bloque([i for i in its if i['grupo_ejecutor'] == 'otros']),
                             'otros_multimunicipales': bloque([i for i in its if i['multimunicipal']])},
            'aprobados_fechados_en_bienio_compartido': {'n': sum(1 for i in ap if i['anio_en_bienio_compartido']), 'valor': sum(i['valor'] for i in ap if i['anio_en_bienio_compartido'])},
            'aprobados_sin_iniciar': {'n': sum(1 for i in ap if i['clase'] == 'aprobado_sin_iniciar'), 'valor': sum(i['valor'] for i in ap if i['clase'] == 'aprobado_sin_iniciar')},
            'devueltos_mga': conteo('devuelto_mga'), 'desaprobados': {'n': sum(1 for i in its if i['clase'] == 'desaprobado'), 'valor': sum(i['valor'] for i in its if i['clase'] == 'desaprobado')},
            'no_viables': conteo('no_viable'), 'no_aprobados': conteo('no_aprobado'), 'viables_sin_aprobar': conteo('viable_sin_aprobar'), 'en_formulacion': conteo('en_formulacion'),
            'sin_contrato_registrado': {'n': sum(1 for i in ap if i['sin_contrato_registrado']), 'valor': sum(i['valor'] for i in ap if i['sin_contrato_registrado'])},
            'contratados_mas_de_un_anio_despues': {'n': sum(1 for i in ap if i['contratado_mas_de_un_anio_despues']), 'valor': sum(i['valor'] for i in ap if i['contratado_mas_de_un_anio_despues'])},
            'principales_girado_sin_avance': [{'bpin': i['bpin'], 'nombre': i['nombre'][:110], 'valor': i['valor'], 'ej_fisica': i['ej_fisica'], 'ej_financiera': i['ej_financiera'],
                                               'girado_sin_avance': i['girado_sin_avance'], 'ejecutor': i['tipo_ejecutor']} for i in top[:6]],
            'certeza': 'hecho (registros de GESPROY, MapaInversiones y MinHacienda); el periodo se asigna por el año de aprobación estimado',
            'items': sorted(its, key=lambda i: (i['clase'] not in APROBADAS, -i['valor'])),
        })
    return out


# ----------------------------------------------------------------------------- 2. asignaciones directas
SICODIS_TOTAL = {  # TerriData, "SGR – Asignación presupuestal" (DNP–SICODIS SGR), pesos
    '2012': 15437548519.15, '2013-2014': 12993027235.98 + 13084224911.79,
    '2015-2016': 13364404946.64 + 4655132898.34, '2017-2018': 15212109053.36 + 4528426652.00,
}
SICODIS_SALDO_2018 = {'directas': 29501230716.43, 'especificas': 3078671746.11, 'total': 36455602701.02}  # TerriData, corte jun-2018


def bienio_de(v):
    v = int(v)
    if v == 2012:
        return '2012'
    a = v if v % 2 == 1 else v - 1
    return f'{a}-{a + 1}'


def asignaciones_directas(items):
    # asignado: MapaRegalías (AD distribuidas por vigencia)
    dist = socrata('h6yd-ei3n', "entidadterritorial='Antioquia-Yondó'")
    asign = defaultdict(float)
    for x in dist:
        if (x.get('tiporecurso') or '').strip().lower() == 'asignaciones directas':
            asign[bienio_de(x['vigencia'])] += f(x['distribucionpresupuestada'])
    # aprobado: valor inicial de las fuentes AD de Yondó en los proyectos (MapaInversiones)
    bpins = [i['bpin'] for i in items]
    v4 = socrata_in('v4ap-cvae', 'bpin', bpins)
    aprob = defaultdict(float)
    for x in v4:
        t = x['tiporecursofuentefinanciacion'].lower()
        if 'directas' in t and x['entidadfuentefinanciacion'].startswith('Yond'):
            aprob[bienio_de(x['vigencia'])] += f(x['valorinicial'])
    # CHIP histórico: 2016-T4 (cierre 2015-2016) y 2018-T3 (corte 2017-2018)
    ing = socrata('rr3v-r3jc', f"codigochip='{CHIP_YONDO}'")
    gas = socrata('wtyw-nhcv', f"codigochip='{CHIP_YONDO}'")

    def chip_hist(ano, tri):
        g = [x for x in gas if x['ano'] == ano and x['periodotrimestral'] == tri and x['codigocuenta'].startswith('2.3')]
        ad = [x for x in ing if x['ano'] == ano and x['periodotrimestral'] == tri and 'ASIGNACIONES DIRECTAS' in norm(x['nombrecuenta'])]
        rec = [x for x in ing if x['ano'] == ano and x['periodotrimestral'] == tri]
        return {'apropiacion_definitiva_sgr': sum(f(x['valorapropiaciondefinitiva']) for x in g), 'compromisos_sgr': sum(f(x['valorcompromisos']) for x in g),
                'pagos_sgr': sum(f(x['valorpagos']) for x in g), 'presupuesto_ad': sum(f(x['valorpresupuestodefinitivo']) for x in ad),
                'recaudo_ad': sum(f(x['valorrecaudo']) for x in ad), 'recaudo_total_sgr': sum(f(x['valorrecaudo']) for x in rec)}
    h16, h18 = chip_hist('2016', '4'), chip_hist('2018', '3')
    # OVCF (CHIP) 2021-2026
    prog = socrata('xr2w-9eg2', f"codigo_entidad='{CHIP_YONDO}'")
    ejec = socrata('qkv4-ek54', f"codigo_entidad='{CHIP_YONDO}'")
    ingp = socrata('5ka2-and2', f"codigo_entidad='{CHIP_YONDO}'")

    def ovcf(periodo, pat):
        a = sum(f(x['apropiacion_definitiva']) for x in prog if x['periodo'] == periodo and x['nom_fuentes_financiacion'] != 'NO APLICA' and pat in norm(x['nom_fuentes_financiacion']))
        c = sum(f(x['compromisos']) for x in ejec if x['periodo'] == periodo and x['nom_fuentes_financiacion'] != 'NO APLICA' and pat in norm(x['nom_fuentes_financiacion']))
        p = sum(f(x['pagos']) for x in ejec if x['periodo'] == periodo and x['nom_fuentes_financiacion'] != 'NO APLICA' and pat in norm(x['nom_fuentes_financiacion']))
        return a, c, p

    def disp_inicial(periodo):
        """Disponibilidad inicial de asignaciones directas (20 % + anticipadas 5 % + incentivo) en el presupuesto del bienio."""
        s = 0.0
        for x in ingp:
            if x['periodo'] == periodo and x['nom_tipo_recurso'] == 'DISPONIBILIDAD INICIAL' and x['cuenta'].startswith('1.1.02.06.002.01.03.01.0'):
                s += f(x['presupuesto_definitivo'])
        return s
    di21, di23, di25 = disp_inicial('20221201'), disp_inicial('20241201'), disp_inicial('20260601')
    a21, c21, p21 = ovcf('20221201', 'DIRECTAS')
    a23, c23, p23 = ovcf('20241201', 'DIRECTAS')
    a25, c25, p25 = ovcf('20260601', 'DIRECTAS')
    # MinHacienda 2025-2026
    caja = socrata('e624-d9uy', f"codigodaneentidad='{YONDO_DANE}'")
    cj = {x['codigofondo']: x for x in caja}

    def mhv(cod, campo):
        return f(cj[cod][campo]) if cod in cj else 0.0
    pres25 = mhv('ADIR', 'presupuestosgrinversion') + mhv('ADAN', 'presupuestosgrinversion')
    apr25 = mhv('ADIR', 'recursosaprobadosasignadosspgr') + mhv('ADAN', 'recursosaprobadosasignadosspgr')
    pag25 = mhv('ADIR', 'totalpagado') + mhv('ADAN', 'totalpagado')
    caja25 = mhv('ADIR', 'saldocaja') + mhv('ADAN', 'saldocaja')

    def fila(bienio, asignado, aprobado, saldo, tipo_saldo, fuente, certeza, extra=None, nota=None):
        d = {'bienio': bienio, 'asignado': round(asignado), 'aprobado': round(aprobado), 'saldo': round(saldo) if saldo is not None else None,
             'que_mide_el_saldo': tipo_saldo, 'fuente': fuente, 'certeza': certeza}
        if extra:
            d.update({k: (round(v) if isinstance(v, float) else v) for k, v in extra.items()})
        if nota:
            d['nota'] = nota
        return d
    fA = 'Asignado: MapaRegalías h6yd-ei3n (asignaciones directas distribuidas). Aprobado: MapaInversiones v4ap-cvae (valor inicial de las fuentes de asignaciones directas de Yondó en sus proyectos).'
    filas = [
        fila('2012', asign['2012'], aprob['2012'], None, None, fA, 'hecho (registros); saldo sin dato oficial',
             {'asignado_total_sgr_sicodis': SICODIS_TOTAL['2012']}),
        fila('2013-2014', asign['2013-2014'], aprob['2013-2014'], None, None, fA, 'hecho (registros); saldo sin dato oficial',
             {'asignado_total_sgr_sicodis': SICODIS_TOTAL['2013-2014']}),
        fila('2015-2016', asign['2015-2016'], aprob['2015-2016'], h16['recaudo_total_sgr'] - h16['compromisos_sgr'],
             'plata del SGR recaudada por el municipio y no comprometida al cierre del bienio (recaudo − compromisos, CHIP 2016-T4)', fA + ' Saldo: CHIP rr3v-r3jc y wtyw-nhcv, 2016-T4.', 'hecho (CHIP)',
             {'asignado_total_sgr_sicodis': SICODIS_TOTAL['2015-2016'], 'presupuesto_definitivo_ad_chip': h16['presupuesto_ad'], 'recaudo_ad_chip': h16['recaudo_ad'],
              'apropiacion_definitiva_sgr_chip': h16['apropiacion_definitiva_sgr'], 'comprometido_sgr_chip': h16['compromisos_sgr'], 'pagado_sgr_chip': h16['pagos_sgr'],
              'sin_comprometer_sgr_chip': h16['apropiacion_definitiva_sgr'] - h16['compromisos_sgr'], 'recaudo_total_sgr_chip': h16['recaudo_total_sgr'],
              'recaudo_ad_no_presupuestado': h16['recaudo_ad'] - h16['presupuesto_ad']},
             'Las asignaciones directas recaudadas superaron en ese monto lo presupuestado: entraron a la caja sin incorporarse al presupuesto del bienio.'),
        fila('2017-2018', asign['2017-2018'], aprob['2017-2018'], SICODIS_SALDO_2018['directas'],
             'saldo de asignaciones directas sin aprobar acumulado 2012–junio de 2018 (SICODIS)', fA + ' Saldo: TerriData (DNP–SICODIS SGR), corte jun-2018. CHIP wtyw-nhcv 2018-T3.', 'hecho (SICODIS)',
             {'asignado_total_sgr_sicodis': SICODIS_TOTAL['2017-2018'], 'saldo_total_sgr_sicodis_jun2018': SICODIS_SALDO_2018['total'],
              'apropiacion_definitiva_sgr_chip_sep2018': h18['apropiacion_definitiva_sgr'], 'comprometido_sgr_chip_sep2018': h18['compromisos_sgr'],
              'sin_comprometer_sgr_chip_sep2018': h18['apropiacion_definitiva_sgr'] - h18['compromisos_sgr']},
             'En 2019 se aprobó el valor más alto de asignaciones directas de la serie, en buena parte con este saldo acumulado.'),
        fila('2019-2020', asign['2019-2020'], aprob['2019-2020'], di21, 'saldo de asignaciones directas que pasó al bienio 2021-2022 (disponibilidad inicial, CHIP)',
             fA + ' Saldo: OVCF 5ka2-and2, disponibilidad inicial del presupuesto 2021-2022.', 'hecho (CHIP)'),
        fila('2021-2022', asign['2021-2022'], aprob['2021-2022'], a21 - c21, 'apropiación de asignaciones directas sin comprometer al cierre (CHIP)',
             fA + ' Presupuesto y compromisos: OVCF xr2w-9eg2 y qkv4-ek54, corte dic-2022.', 'hecho (CHIP)',
             {'presupuesto_definitivo_ad_chip': a21, 'comprometido_ad_chip': c21, 'pagado_ad_chip': p21, 'paso_al_siguiente_bienio_sin_pagar': di23}),
        fila('2023-2024', asign['2023-2024'], aprob['2023-2024'], a23 - c23, 'apropiación de asignaciones directas sin comprometer al cierre (CHIP)',
             fA + ' Presupuesto y compromisos: OVCF, corte dic-2024.', 'hecho (CHIP)',
             {'presupuesto_definitivo_ad_chip': a23, 'comprometido_ad_chip': c23, 'pagado_ad_chip': p23, 'paso_al_siguiente_bienio_sin_pagar': di25}),
        fila('2025-2026', pres25, apr25, pres25 - apr25, 'presupuesto de asignaciones directas (incluye anticipadas) sin aprobar en proyectos, corte oct-2026 (bienio en curso)',
             'MinHacienda e624-d9uy (ADIR + ADAN), corte oct-2026. CHIP OVCF a jun-2026 como contraste.', 'hecho (MinHacienda); bienio sin cerrar',
             {'pagado': pag25, 'saldo_en_caja': caja25, 'presupuesto_definitivo_ad_chip_jun2026': a25, 'comprometido_ad_chip_jun2026': c25,
              'asignado_mapa_regalias_2025_parcial': asign.get('2025-2026', 0.0)},
             'El capítulo SGR que el municipio reporta al CHIP va rezagado frente a MinHacienda.'),
    ]
    tot = {'asignado_2012_2024': round(sum(asign[b] for b in ['2012', '2013-2014', '2015-2016', '2017-2018', '2019-2020', '2021-2022', '2023-2024'])),
           'aprobado_2012_2024': round(sum(aprob[b] for b in ['2012', '2013-2014', '2015-2016', '2017-2018', '2019-2020', '2021-2022', '2023-2024']))}
    return filas, tot, {'chip_2016': h16, 'chip_2018': h18}


def regalias_directas_2004_2011():
    oec = {int(r['anio']): r for r in csv.DictReader(open(D / 'fuentes/serie_fiscal_oec.csv', encoding='utf-8'))}
    anos = []
    for y in range(2004, 2012):
        r = oec[y]
        reg, ing, inv = f(r['regalias_giradas_mm_derivado']) * 1e6, f(r['ingresos_totales_mm']) * 1e6, f(r['inversion_mm']) * 1e6
        anos.append({'anio': y, 'periodo': periodo_de(y), 'regalias_giradas': round(reg), 'ingresos_totales': round(ing), 'pct_ingresos': round(100 * reg / ing, 1),
                     'inversion': round(inv), 'poblacion': int(f(r['poblacion'])), 'regalias_por_habitante': round(reg / f(r['poblacion']))})
    per = []
    for p in ('2004-2007', '2008-2011'):
        s = [a for a in anos if a['periodo'] == p]
        per.append({'periodo': p, 'regalias_giradas': sum(a['regalias_giradas'] for a in s), 'ingresos_totales': sum(a['ingresos_totales'] for a in s),
                    'pct_ingresos': round(100 * sum(a['regalias_giradas'] for a in s) / sum(a['ingresos_totales'] for a in s), 1)})
    return {'anios': anos, 'por_periodo': per,
            'fuente': 'data/fuentes/serie_fiscal_oec.csv (TerriData, Operaciones Efectivas de Caja DNP–FUT: regalías per cápita giradas × población)',
            'certeza': 'hecho derivado (cálculo sobre cifras oficiales)',
            'contexto_anh': {'liquidado_todos_los_beneficiarios_2010': 91055e6, 'liquidado_todos_los_beneficiarios_2011': 122267e6,
                             'fuente': 'ANH, liquidación de regalías por campo, https://www.datos.gov.co/d/j7js-yk74 (docs/anexos/B-finanzas-regalias.md)',
                             'nota': 'Es lo liquidado para todos los beneficiarios (Nación, departamento, municipio, puertos); a Yondó llegó cerca del 28 %.'},
            'nota': 'Antes de 2012 no hay registro de proyectos por BPIN en datos abiertos: no se puede saber en qué obras terminó cada peso del régimen anterior.'}


# ----------------------------------------------------------------------------- 3. fondos
# Base ART de Obras por Impuestos 2018-2025 (corte 5-ago-2025), procesada con pdfplumber.
# "Propios" = proyectos cuyo único municipio es el indicado. Valores en pesos del año del proyecto.
OXI_PROPIOS = {
    'Yondó': [('2019', '20181719000376', 1169234194, 'Dotación de mobiliario escolar y equipos, sedes educativas oficiales (Ecopetrol)'),
              ('2024', '20230214000033', 52237169780, 'Mejoramiento y pavimentación de la vía terciaria El Paraíso – La Raya – Las Lomas (Ecopetrol)')],
    'Cantagallo': [('2019', '20191719000012', 5332563307, '150 unidades sanitarias para viviendas dispersas (Ecopetrol)')],
    'San Pablo': [('2024', '20240214000048', 412160000, 'Ambulancia básica (TAB) para la red pública de salud')],
    'Puerto Berrío': [], 'Remedios': [], 'Segovia': [], 'Simití': [], 'Puerto Nare': [], 'Barrancabermeja': [],
}
OXI_MULTI_N = {'Yondó': 8, 'Puerto Berrío': 8, 'Remedios': 12, 'Segovia': 16, 'Cantagallo': 3, 'San Pablo': 5, 'Simití': 4, 'Puerto Nare': 0, 'Barrancabermeja': 0}
OXI_STATS = {'proyectos_propios_pais': 396, 'municipios_con_proyecto_propio': 173, 'transporte_propio_mediana': 7025588480, 'transporte_propio_p75': 16128508389,
             'total_por_municipio_mediana': 6777944621, 'total_por_municipio_p75': 22562288472}


def fondos(items, ad_filas):
    caja = socrata('e624-d9uy', "codigodaneentidad in(" + ','.join(f"'{c}'" for c in [YONDO_DANE, *COMPARABLES]) + ')')
    mh = defaultdict(dict)
    for x in caja:
        mh[x['codigodaneentidad']][x['codigofondo']] = {k: f(x[k]) for k in ('presupuestosgrinversion', 'recursosaprobadosasignadosspgr', 'totalpagado', 'saldocaja')}

    def g(dane, fondo, campo):
        return mh.get(dane, {}).get(fondo, {}).get(campo, 0.0)
    nombre = {YONDO_DANE: 'Yondó', **{k: v[0] for k, v in COMPARABLES.items()}}
    U_E624 = 'https://www.datos.gov.co/d/e624-d9uy (bienio 2025-2026, corte oct-2026)'

    # OVCF ejecución como ejecutor (Asignación para la Paz) 2021-2022 y 2023-2024
    chips = {v[2]: k for k, v in COMPARABLES.items()}
    chips[CHIP_YONDO] = YONDO_DANE
    w = "codigo_entidad in(" + ','.join(f"'{c}'" for c in chips) + ") and periodo in('20221201','20241201','20260601')"
    prog = socrata('xr2w-9eg2', w)
    ejec = socrata('qkv4-ek54', w)
    ov = defaultdict(lambda: [0.0, 0.0, 0.0])
    for x in prog:
        if x['nom_fuentes_financiacion'] != 'NO APLICA':
            ov[(chips[x['codigo_entidad']], x['periodo'], norm(x['nom_fuentes_financiacion']))][0] += f(x['apropiacion_definitiva'])
    for x in ejec:
        if x['nom_fuentes_financiacion'] != 'NO APLICA':
            k = (chips[x['codigo_entidad']], x['periodo'], norm(x['nom_fuentes_financiacion']))
            ov[k][1] += f(x['compromisos'])
            ov[k][2] += f(x['pagos'])

    def ovsum(dane, periodo, pat, i):
        return sum(v[i] for (d, p, fu), v in ov.items() if d == dane and p == periodo and pat in fu)

    out = []
    # --- OCAD Paz / Asignación para la Paz
    paz = {d: g(d, 'ASPAZ', 'recursosaprobadosasignadosspgr') + g(d, 'ADPAZ', 'recursosaprobadosasignadosspgr') for d in nombre}
    pares_sb = [paz[d] for d in ('13160', '13670', '13744')]
    med_sb = statistics.median(pares_sb)
    ocad_paz_local = [i for i in items if (i['ocad'] or '') == 'OCAD PAZ' and i['grupo_ejecutor'] == 'municipio' and i['clase'] in APROBADAS]
    gsa_paz = sum(i['girado_sin_avance'] or 0 for i in ocad_paz_local)
    out.append({
        'fondo': 'OCAD Paz – Asignación para la Paz del SGR (municipios PDET)', 'desde': 2017,
        'que_es': 'Bolsa de regalías creada por el Acto Legislativo 04 de 2017 para financiar proyectos del Acuerdo de Paz en municipios PDET; un órgano colegiado nacional (OCAD Paz) los aprueba. Yondó es PDET de la subregión Sur de Bolívar.',
        'yondo_obtuvo': {
            'texto': f"{len(ocad_paz_local)} proyectos locales del OCAD Paz ejecutados por el municipio o su empresa de servicios (2018–2021) por {cop(sum(i['valor'] for i in ocad_paz_local))} M, más dos multimunicipales (INVÍAS y U. de Antioquia). En 2025-2026 el OCAD Paz aprobó {cop(paz[YONDO_DANE])} M para proyectos en Yondó. Como ejecutor, el municipio presupuestó {cop(ovsum(YONDO_DANE, '20221201', 'PAZ', 0))} M en 2021-2022 y {cop(ovsum(YONDO_DANE, '20241201', 'PAZ', 0))} M en 2023-2024. El problema no fue conseguir la plata sino ejecutarla: en los proyectos locales del OCAD Paz hay {cop(gsa_paz)} M girados sin avance físico equivalente.",
            'aprobado_2025_2026': round(paz[YONDO_DANE]), 'proyectos_locales_2018_2021': round(sum(i['valor'] for i in ocad_paz_local)),
            'presupuesto_como_ejecutor_2021_2022': round(ovsum(YONDO_DANE, '20221201', 'PAZ', 0)), 'comprometido_2021_2022': round(ovsum(YONDO_DANE, '20221201', 'PAZ', 1)),
            'presupuesto_como_ejecutor_2023_2024': round(ovsum(YONDO_DANE, '20241201', 'PAZ', 0)), 'comprometido_2023_2024': round(ovsum(YONDO_DANE, '20241201', 'PAZ', 1)),
            'girado_sin_avance_ocad_paz': round(gsa_paz), 'certeza': 'hecho',
        },
        'comparables': [{'municipio': nombre[d], 'pdet': COMPARABLES[d][1], 'monto': round(paz[d]), 'que_mide': 'aprobado por el OCAD Paz (ASPAZ + ADPAZ) en 2025-2026',
                         'presupuesto_como_ejecutor_2021_2022': round(ovsum(d, '20221201', 'PAZ', 0)), 'presupuesto_como_ejecutor_2023_2024': round(ovsum(d, '20241201', 'PAZ', 0)),
                         'fuente': U_E624 + '; OVCF xr2w-9eg2'} for d in COMPARABLES],
        'monto_referencia_min': 0, 'monto_referencia_max': round(max(paz.values()) - paz[YONDO_DANE]),
        'monto_referencia_central': round(max(0, med_sb - paz[YONDO_DANE])),
        'metodo': 'Contrafactual. Diferencia entre lo aprobado a Yondó en 2025-2026 y lo aprobado a sus pares PDET del Sur de Bolívar (Cantagallo, San Pablo, Simití): mínimo 0 (Yondó ya está dentro del rango), central = mediana de los tres pares menos Yondó, máximo = Cantagallo menos Yondó. Pesos de 2025-2026. En 2021-2024 Yondó, como ejecutor, presupuestó más plata del OCAD Paz que sus pares: en ese periodo la brecha no fue de gestión sino de ejecución (ver girado sin avance).',
        'tipo': 'contrafactual', 'periodos_afectados': ['2024-2027'],
        'evidencia': [U_E624, 'https://www.datos.gov.co/d/mzgh-shtp', 'https://www.datos.gov.co/d/xr2w-9eg2'],
    })
    # --- Incentivo a la Producción
    ip = {d: (g(d, 'IPAZ', 'presupuestosgrinversion'), g(d, 'IPAZ', 'recursosaprobadosasignadosspgr')) for d in nombre}
    pres_y, apr_y = ip[YONDO_DANE]
    tasa_barranca = ip['68081'][1] / ip['68081'][0] if ip['68081'][0] else 0
    tasa_cant = ip['13160'][1] / ip['13160'][0] if ip['13160'][0] else 0
    di_inc = {}
    ingp = socrata('5ka2-and2', f"codigo_entidad='{CHIP_YONDO}'")
    for per in ('20221201', '20241201', '20260601'):
        di_inc[per] = sum(f(x['presupuesto_definitivo']) for x in ingp if x['periodo'] == per and 'ACTO LEGISLATIVO 04' in norm(x['nombre_cuenta']))
    out.append({
        'fondo': 'Incentivo a la Producción del SGR (incluida la bolsa de incentivos del OCAD Paz)', 'desde': 2017,
        'que_es': 'Parte de las regalías que premia a los municipios productores para proyectos que aprueba el OCAD Paz (Acto Legislativo 04 de 2017) y, desde la Ley 2056 de 2020, el incentivo a la producción, exploración y formalización. En 2025 MinEnergía abrió una convocatoria para 209 municipios, Yondó entre ellos, con la línea "Territorios energéticos" (hasta $8.000 M y dos proyectos).',
        'yondo_obtuvo': {
            'texto': f"En 2025-2026 Yondó tiene {cop(pres_y)} M presupuestados en esta bolsa y solo {cop(apr_y, 1)} M aprobados ({pct(100 * apr_y / pres_y)} %); {cop(g(YONDO_DANE, 'IPAZ', 'saldocaja'))} M siguen en caja. Antes, {cop(di_inc['20221201'])} M de incentivos del Acto Legislativo 04 de 2017 pasaron sin usar a 2021-2022 y {cop(di_inc['20241201'])} M a 2023-2024. En la convocatoria de 2025 el municipio presentó un solo proyecto (sistemas solares rurales), que quedó en la lista de los que no cumplen.",
            'presupuesto_2025_2026': round(pres_y), 'aprobado_2025_2026': round(apr_y), 'saldo_caja_oct2026': round(g(YONDO_DANE, 'IPAZ', 'saldocaja')),
            'saldo_sin_aprobar': round(pres_y - apr_y), 'incentivos_al04_sin_usar_inicio_2021': round(di_inc['20221201']),
            'incentivos_al04_sin_usar_inicio_2023': round(di_inc['20241201']), 'incentivos_al04_sin_usar_inicio_2025': round(di_inc['20260601']), 'certeza': 'hecho',
        },
        'comparables': [{'municipio': nombre[d], 'monto': round(ip[d][1]), 'presupuesto': round(ip[d][0]),
                         'pct_aprobado': round(100 * ip[d][1] / ip[d][0], 1) if ip[d][0] else None, 'que_mide': 'aprobado del incentivo a la producción OCAD Paz (IPAZ), 2025-2026',
                         'fuente': U_E624} for d in COMPARABLES],
        'monto_referencia_min': round(max(0, pres_y * tasa_barranca - apr_y)), 'monto_referencia_max': round(pres_y - apr_y),
        'monto_referencia_central': round(max(0, pres_y * tasa_cant - apr_y)),
        'metodo': 'Hecho + contrafactual. El máximo es el saldo sin aprobar (plata que ya está asignada a Yondó). El mínimo aplica a Yondó la tasa de aprobación de Barrancabermeja (16 %) y el central la de Cantagallo (43 %), menos lo ya aprobado. Pesos de 2025-2026.',
        'tipo': 'hecho_y_contrafactual', 'periodos_afectados': ['2020-2023', '2024-2027'],
        'evidencia': [U_E624, 'https://www.datos.gov.co/d/5ka2-and2', 'https://www.minenergia.gov.co/documents/13987/Listado209-Municipios-ConvocatoriaIP-2025.pdf', 'docs/anexos/D-energia-mintic.md'],
    })
    # --- Asignación para la Inversión Local
    ail = {d: (g(d, 'AIL', 'presupuestosgrinversion') + g(d, 'AILA', 'presupuestosgrinversion'), g(d, 'AIL', 'recursosaprobadosasignadosspgr') + g(d, 'AILA', 'recursosaprobadosasignadosspgr')) for d in nombre}
    a21, c21 = ovsum(YONDO_DANE, '20221201', 'INVERSION LOCAL', 0), ovsum(YONDO_DANE, '20221201', 'INVERSION LOCAL', 1)
    a23, c23 = ovsum(YONDO_DANE, '20241201', 'INVERSION LOCAL', 0), ovsum(YONDO_DANE, '20241201', 'INVERSION LOCAL', 1)
    sin = (ail[YONDO_DANE][0] - ail[YONDO_DANE][1]) + (a21 - c21) + (a23 - c23)
    out.append({
        'fondo': 'Asignación para la Inversión Local del SGR (incluye la ambiental)', 'desde': 2021,
        'que_es': 'Cupo de regalías que la Ley 2056 de 2020 reparte a municipios pobres o de categorías 4 a 6 para proyectos locales; el municipio los aprueba.',
        'yondo_obtuvo': {
            'texto': f"2021-2022: {cop(a21)} M presupuestados y {cop(c21)} M comprometidos. 2023-2024: {cop(a23)} M y {cop(c23)} M. 2025-2026: {cop(ail[YONDO_DANE][0])} M presupuestados y {cop(ail[YONDO_DANE][1])} M aprobados a octubre de 2026.",
            'presupuesto_2025_2026': round(ail[YONDO_DANE][0]), 'aprobado_2025_2026': round(ail[YONDO_DANE][1]),
            'sin_comprometer_2021_2022': round(a21 - c21), 'sin_comprometer_2023_2024': round(a23 - c23), 'certeza': 'hecho'},
        'comparables': [{'municipio': nombre[d], 'monto': round(ail[d][1]), 'presupuesto': round(ail[d][0]),
                         'pct_aprobado': round(100 * ail[d][1] / ail[d][0], 1) if ail[d][0] else None, 'que_mide': 'aprobado AIL + AIL ambiental, 2025-2026', 'fuente': U_E624} for d in COMPARABLES],
        'monto_referencia_min': 0, 'monto_referencia_max': round(sin),
        'metodo': 'Hecho. Suma de lo presupuestado y no comprometido en 2021-2022 y 2023-2024 (CHIP) y de lo no aprobado en 2025-2026 (MinHacienda). El mínimo es 0 porque parte de ese saldo se reprograma en el bienio siguiente.',
        'tipo': 'hecho', 'periodos_afectados': ['2020-2023', '2024-2027'],
        'evidencia': [U_E624, 'https://www.datos.gov.co/d/xr2w-9eg2', 'https://www.datos.gov.co/d/qkv4-ek54'],
    })
    # --- Obras por Impuestos
    oxi_y = sum(v for _, _, v, _ in OXI_PROPIOS['Yondó'])
    out.append({
        'fondo': 'Obras por Impuestos (municipios ZOMAC y PDET)', 'desde': 2017,
        'que_es': 'Las empresas pagan parte de su impuesto de renta construyendo proyectos en municipios ZOMAC o PDET (Ley 1819 de 2016, art. 238; Decreto 1915 de 2017; opción convenio desde 2019). El municipio debe tener proyectos viabilizados en el banco de la ART para que una empresa los escoja.',
        'yondo_obtuvo': {
            'texto': f"Dos proyectos propios, ambos con Ecopetrol: dotación escolar en 2019 ($1.169 M) y la vía El Paraíso – La Raya – Las Lomas en 2024 ($52.237 M según la ART; Ecopetrol anunció en enero de 2026 una inversión de $42.128 M para 9,4 km). Además figura en {OXI_MULTI_N['Yondó']} proyectos multimunicipales de dotación escolar y biomédica. Entre 2018 y 2023, aunque Ecopetrol (el mayor contribuyente de Obras por Impuestos del país) opera en su territorio, Yondó solo tuvo el proyecto de 2019.",
            'propios': [{'anio': a, 'bpin': b, 'valor': v, 'proyecto': n} for a, b, v, n in OXI_PROPIOS['Yondó']], 'total_propios': oxi_y,
            'multimunicipales_n': OXI_MULTI_N['Yondó'], 'certeza': 'hecho',
            'nota': 'MapaInversiones (cf9k-55fw) registra para el BPIN 20230214000033 un valor de $229.297 M, que no coincide con la ART ni con Ecopetrol; se usa el valor de la ART.'},
        'comparables': [{'municipio': m, 'monto': sum(v for _, _, v, _ in OXI_PROPIOS[m]), 'proyectos_propios': len(OXI_PROPIOS[m]), 'multimunicipales_n': OXI_MULTI_N[m],
                         'que_mide': 'valor de proyectos propios (un solo municipio) 2018-2025', 'fuente': 'ART, base de proyectos OxI 2018-2025 (corte 5-ago-2025)'}
                        for m in ['Puerto Berrío', 'Puerto Nare', 'Remedios', 'Segovia', 'Cantagallo', 'San Pablo', 'Simití', 'Barrancabermeja']]
        + [{'municipio': 'Referencia Antioquia PDET 2025 (vías propias)', 'monto': None, 'casos': {'Nechí': 43964136915, 'Amalfi': 36179479644, 'Anorí': 24863578374, 'Zaragoza': 15339919769},
            'fuente': 'Gobernación de Antioquia, Informe final PDET (30-may-2026), tabla 9; ART'}],
        'monto_referencia_min': OXI_STATS['transporte_propio_mediana'], 'monto_referencia_max': 2 * OXI_STATS['transporte_propio_p75'],
        'metodo': 'Contrafactual para la ventana 2018-2023, cuando Yondó no tuvo proyectos viales propios. Mínimo: un proyecto vial propio de valor mediano en el país (396 proyectos propios, 84 viales, ART 2018-2025). Máximo: dos proyectos viales del percentil 75, uno por cada gobierno (2016-2019 y 2020-2023). Pesos del año de cada proyecto (2018-2025). Desde 2024 Yondó está por encima del percentil 75 de los municipios con proyecto propio.',
        'tipo': 'contrafactual', 'periodos_afectados': ['2016-2019', '2020-2023'],
        'evidencia': ['https://www.renovacionterritorio.gov.co/sites/default/files/2025-10/proyectos_2018_2025.pdf',
                      'https://www.vanguardia.com/santander/barrancabermeja/2026/01/22/ecopetrol-invertira-cerca-de-42-mil-millones-en-vias-rurales-del-magdalena-medio-antioqueno/',
                      'https://www.elcolombiano.com/negocios/estos-son-los-proyectos-de-obras-por-impuestos-que-se-ejecutaran-en-antioquia-GE25476198'],
    })
    # --- FENOGE
    out.append({
        'fondo': 'FENOGE (Fondo de Energías No Convencionales y Gestión Eficiente de la Energía), incluido ConEnergía', 'desde': 2014,
        'que_es': 'Fondo del Ministerio de Minas y Energía creado por la Ley 1715 de 2014 que financia, con recursos no reembolsables o créditos, paneles solares y eficiencia energética en edificios públicos. Su programa ConEnergía (2023) prioriza municipios ZOMAC, PDET y de categorías 5 y 6.',
        'yondo_obtuvo': {'texto': 'No se encontró ningún proyecto de FENOGE en Yondó en los comunicados y rendiciones de cuentas del fondo.', 'monto': 0, 'certeza': 'hecho negativo (no hallado en las fuentes consultadas)'},
        'comparables': [{'municipio': 'Simití', 'monto': 3152000000, 'que_mide': 'hospital San Antonio de Padua: 230 kWp y eficiencia energética, cubre el 100 % del consumo (jul-2025)',
                         'fuente': 'https://fenoge.gov.co/documentos-noticias/2025/Comunicado_entrega_de_hospital_publico_autosostenible_en_Simiti_Bolivar.pdf'},
                        {'municipio': 'Cunday (Tolima), referencia de menor escala', 'monto': 713538995, 'que_mide': 'hospital de 43 kWp con eficiencia energética (jun-2025)',
                         'fuente': 'https://fenoge.gov.co/documentos-noticias/2025/BoletinCunday14062025.pdf'},
                        {'municipio': 'Puerto Berrío, Puerto Nare, Remedios, Segovia, Cantagallo, San Pablo, Barrancabermeja', 'monto': None,
                         'que_mide': 'no se hallaron proyectos FENOGE en estos municipios', 'fuente': 'búsqueda en fenoge.gov.co (oct-2026)'}],
        'monto_referencia_min': 713538995, 'monto_referencia_max': 3152000000,
        'metodo': 'Contrafactual. Rango del costo de un hospital público solar y eficiente financiado por FENOGE en 2025 (Cunday a Simití). Sirve para el hospital de Yondó o para un conjunto de sedes públicas. Pesos de 2025.',
        'tipo': 'contrafactual', 'periodos_afectados': ['2020-2023', '2024-2027'],
        'evidencia': ['https://fenoge.gov.co/proyectos/conenergia/', 'docs/anexos/D-energia-mintic.md', 'docs/anexos/C-hospital-2028.md'],
    })
    # --- MinTIC Centros Digitales
    cd = socrata('fybg-535s', None)
    cdc = defaultdict(lambda: [0, 0.0])
    claves = {('ANTIOQUIA', 'YONDO'): 'Yondó', ('ANTIOQUIA', 'PUERTO BERRIO'): 'Puerto Berrío', ('ANTIOQUIA', 'PUERTO NARE'): 'Puerto Nare', ('ANTIOQUIA', 'REMEDIOS'): 'Remedios',
              ('ANTIOQUIA', 'SEGOVIA'): 'Segovia', ('BOLIVAR', 'CANTAGALLO'): 'Cantagallo', ('BOLIVAR', 'SAN PABLO'): 'San Pablo', ('BOLIVAR', 'SIMITI'): 'Simití',
              ('SANTANDER', 'BARRANCABERMEJA'): 'Barrancabermeja'}
    for x in cd:
        k = claves.get((norm(x['departamento']), norm(x['municipio'])))
        if k:
            cdc[k][0] += 1
            cdc[k][1] += f(x.get('inversion'))
    costo = cdc['Yondó'][1] / cdc['Yondó'][0] if cdc['Yondó'][0] else 142684114
    ns = sorted(cdc[m][0] for m in claves.values() if m != 'Yondó')
    med = statistics.median(ns)
    out.append({
        'fondo': 'MinTIC – Centros Digitales rurales (y otras líneas de conectividad)', 'desde': 2020,
        'que_es': 'Programa nacional que conecta sedes educativas rurales con internet gratuito hasta 2032. MinTIC prioriza las sedes; el municipio puede pedir su inclusión y aportar el inventario de sedes sin conexión.',
        'yondo_obtuvo': {'texto': f"{cdc['Yondó'][0]} sedes conectadas, todas en el corregimiento San Miguel del Tigre, con una inversión registrada de {cop(cdc['Yondó'][1])} M (corte oct-2023).",
                         'sedes': cdc['Yondó'][0], 'inversion': round(cdc['Yondó'][1]), 'certeza': 'hecho'},
        'comparables': [{'municipio': m, 'monto': round(cdc[m][1]), 'sedes': cdc[m][0], 'que_mide': 'inversión registrada en Centros Digitales (corte 31-oct-2023)',
                         'fuente': 'https://www.datos.gov.co/d/fybg-535s'} for m in claves.values() if m != 'Yondó'],
        'monto_referencia_min': round((min(ns) - cdc['Yondó'][0]) * costo), 'monto_referencia_max': round((max(ns) - cdc['Yondó'][0]) * costo),
        'monto_referencia_central': round((med - cdc['Yondó'][0]) * costo),
        'metodo': f'Contrafactual. Sedes adicionales que tendría Yondó con la cobertura de sus comparables (mínimo {min(ns)}, mediana {pct(med) if med % 1 else int(med)}, máximo {max(ns)} sedes) por la inversión registrada por sede ({cop(costo, 1)} M). Pesos de 2023.',
        'tipo': 'contrafactual', 'periodos_afectados': ['2020-2023'],
        'evidencia': ['https://www.datos.gov.co/d/fybg-535s', 'docs/anexos/D-energia-mintic.md'],
    })
    # --- Findeter
    oec = {int(r['anio']): r for r in csv.DictReader(open(D / 'fuentes/serie_fiscal_oec.csv', encoding='utf-8'))}
    ic24 = f(oec[2024]['ingresos_corrientes_mm']) * 1e6
    sin_deuda = [y for y in range(2020, 2025) if f(oec[y]['intereses_deuda_mm']) == 0]
    out.append({
        'fondo': 'Findeter – crédito con tasa compensada', 'desde': 1989,
        'que_es': 'Findeter existe desde 1989; las líneas con tasa compensada se abren por decreto o resolución en cada vigencia. Son crédito barato (el Gobierno paga parte de los intereses) para agua, vías, salud, educación y energía; por ejemplo, la línea de redescuento para infraestructura en salud (Res. 2316 de 2025) y "Municipios Territorios Energéticos" (IBR + 0,7 %, 2024). No es plata regalada: hay que pagarla.',
        'yondo_obtuvo': {'texto': f"Yondó no pagó intereses de deuda entre {sin_deuda[0]} y {sin_deuda[-1]} (OEC). El presupuesto de 2026 trae por primera vez servicio de deuda ($1.718,5 M) con un instituto de desarrollo departamental, no con Findeter.",
                         'monto': 0, 'certeza': 'hecho'},
        'comparables': [{'municipio': 'Sin dato por municipio', 'monto': None, 'que_mide': 'Findeter publica desembolsos por departamento y sector, no por municipio',
                         'fuente': 'https://www.datos.gov.co/d/bu9y-ytgi'}],
        'monto_referencia_min': round(0.2 * ic24), 'monto_referencia_max': round(0.4 * ic24),
        'metodo': 'Estimado/contrafactual. Un saldo de deuda prudente del 20 % al 40 % de los ingresos corrientes de 2024 ($23.192 M), muy por debajo del límite de la Ley 358 de 1997 (80 %). Es capacidad de crédito, no plata adicional sin costo. Pesos de 2024.',
        'tipo': 'contrafactual', 'periodos_afectados': ['2020-2023', '2024-2027'],
        'evidencia': ['data/fuentes/serie_fiscal_oec.csv', 'docs/anexos/B-finanzas-regalias.md', 'docs/anexos/C-hospital-2028.md', 'docs/anexos/D-energia-mintic.md'],
    })
    # --- Fondo Adaptación
    fa = socrata('8yvj-6du4', None, limit=100000)
    fam = defaultdict(lambda: [0, 0.0])
    fclaves = {('ANTIOQUIA', 'YONDO'): 'Yondó', ('ANTIOQUIA', 'PUERTO BERRIO'): 'Puerto Berrío', ('ANTIOQUIA', 'PUERTO NARE'): 'Puerto Nare', ('ANTIOQUIA', 'REMEDIOS'): 'Remedios',
               ('ANTIOQUIA', 'SEGOVIA'): 'Segovia', ('BOLIVAR', 'CANTAGALLO'): 'Cantagallo', ('BOLIVAR', 'SAN PABLO'): 'San Pablo', ('BOLIVAR', 'SIMITI'): 'Simití',
               ('SANTANDER', 'BARRANCABERMEJA'): 'Barrancabermeja'}
    for x in fa:
        k = fclaves.get((norm(x.get('departamento')), norm(x.get('municipio'))))
        if k:
            fam[k][0] += 1
            fam[k][1] += f(x.get('total'))
    out.append({
        'fondo': 'Fondo Adaptación', 'desde': 2011,
        'que_es': 'Fondo nacional creado tras la ola invernal de 2010-2011 (Decreto 4819 de 2010) para reconstruir vivienda, acueductos, vías y medios de vida con obras adaptadas al clima. Llegaba a los municipios que registraron daños.',
        'yondo_obtuvo': {'texto': f"{fam['Yondó'][0]} intervenciones ambientales por {cop(fam['Yondó'][1])} M.", 'monto': round(fam['Yondó'][1]), 'certeza': 'hecho'},
        'comparables': [{'municipio': m, 'monto': round(fam[m][1]), 'intervenciones': fam[m][0], 'que_mide': 'valor total de intervenciones del Fondo Adaptación',
                         'fuente': 'https://www.datos.gov.co/d/8yvj-6du4'} for m in fclaves.values() if m != 'Yondó'],
        'monto_referencia_min': 0, 'monto_referencia_max': round(fam['Puerto Nare'][1] - fam['Yondó'][1]),
        'metodo': 'Contrafactual de baja certeza. Diferencia con Puerto Nare, municipio ribereño antioqueño de tamaño parecido. Depende de que Yondó hubiera registrado daños en 2010-2011, dato que no se verificó. Pesos de la fecha de cada intervención (2012-2018).',
        'tipo': 'contrafactual', 'periodos_afectados': ['2008-2011', '2012-2015'],
        'evidencia': ['https://www.datos.gov.co/d/8yvj-6du4'],
    })
    # --- Cooperación internacional
    trm24 = 4071.0
    out.append({
        'fondo': 'Cooperación internacional no reembolsable', 'desde': 2004,
        'que_es': 'Donaciones de gobiernos y organismos (Unión Europea, Japón, agencias de la ONU, entre otros) que se gestionan con proyectos propios o en alianza con organizaciones regionales. El PDET tiene un pilar de articulación con la cooperación.',
        'yondo_obtuvo': {'texto': 'En el registro de APC-Colombia aparece una sola intervención con el nombre de Yondó: el mejoramiento de la vía de la vereda Caño Bodegas, donado por Japón en 2014 (US$106.715), con el Programa de Desarrollo y Paz. Hay proyectos regionales del Magdalena Medio y el Sur de Bolívar que pueden incluir a Yondó, pero el registro no desagrega por municipio.',
                         'monto_usd': 106715, 'certeza': 'hecho'},
        'comparables': [{'municipio': '5 municipios del Sur de Bolívar (Unión Europea, 2016)', 'monto_usd': 1680153, 'que_mide': 'inclusión socioeconómica de jóvenes',
                         'fuente': 'https://www.datos.gov.co/d/2d3i-f9wd (intervención R-BL-00-12897)'},
                        {'municipio': 'Sur de Bolívar (Unión Europea, 2023)', 'monto_usd': None, 'que_mide': '"Jóvenes y mujeres resilientes", gobernanza y desarrollo sostenible',
                         'fuente': 'https://www.datos.gov.co/d/2d3i-f9wd (intervención R-AO-23-4354)'}],
        'monto_referencia_min': round(70000 * trm24), 'monto_referencia_max': round(1680153 / 5 * trm24),
        'metodo': f'Contrafactual de baja certeza, por gobierno. Mínimo: una donación comunitaria tipo Japón (US$70.000). Máximo: la parte de un municipio en un proyecto regional de la Unión Europea (US$1.680.153 / 5). Convertido a pesos con una TRM aproximada de {trm24:,.0f} (promedio 2024).',
        'tipo': 'contrafactual', 'periodos_afectados': ['2012-2015', '2016-2019', '2020-2023', '2024-2027'],
        'evidencia': ['https://www.datos.gov.co/d/2d3i-f9wd'],
    })
    # --- iniciativas PDET (contexto)
    pd = socrata('gmvf-t63e', "codigodane in('5893','5604','5736','13160','13670','13744')", **{'$select': 'codigodane,cuenta_con_ria,count(*)', '$group': 'codigodane,cuenta_con_ria'})
    pdc = defaultdict(lambda: [0, 0])
    for x in pd:
        pdc[x['codigodane'].zfill(5)][0 if norm(x['cuenta_con_ria']) == 'SI' else 1] += int(x['count'])
    contexto_pdet = {k_: {'municipio': nombre.get(k_, k_), 'con_ruta': v[0], 'sin_ruta': v[1], 'pct_con_ruta': round(100 * v[0] / (v[0] + v[1]), 1)} for k_, v in pdc.items()}
    return out, contexto_pdet


# ----------------------------------------------------------------------------- principal
def main():
    gobs = json.loads((D / 'gobiernos.json').read_text(encoding='utf-8'))
    gob = {p['id']: p['alcalde'] for p in gobs['periodos']}
    items = proyectos()
    por_periodo = agregar(items, gob)
    ad, ad_tot, chip_hist = asignaciones_directas(items)
    rd = regalias_directas_2004_2011()
    fon, pdet = fondos(items, ad)

    ap = [i for i in items if i['clase'] in APROBADAS]
    resumen = []
    oec = {int(r['anio']): r for r in csv.DictReader(open(D / 'fuentes/serie_fiscal_oec.csv', encoding='utf-8'))}
    for p in por_periodo:
        a, b = int(p['periodo'][:4]), int(p['periodo'][5:])
        reg = sum(f(oec[y]['regalias_giradas_mm_derivado']) * 1e6 for y in range(a, b + 1) if y in oec)
        opp = [x for x in fon if p['periodo'] in x['periodos_afectados']]
        resumen.append({
            'periodo': p['periodo'], 'alcalde': p['alcalde'],
            'regalias_en_caja': round(reg), 'regalias_en_caja_nota': 'OEC (DNP–FUT vía TerriData); 2024-2027 solo 2024',
            'sgr_aprobado': p['aprobado'], 'sgr_pagado': p['pagado'], 'sgr_proyectos_aprobados': p['n_aprobados'],
            'sgr_terminados': p['terminados']['n'], 'sgr_sin_terminar': p['sin_terminar']['n'],
            'girado_sin_avance': p['girado_sin_avance'], 'girado_sin_avance_ejecutor_municipal': p['por_ejecutor']['municipio']['girado_sin_avance'],
            'devueltos_mga': p['devueltos_mga'], 'no_viables': p['no_viables'],
            'saldos_asignaciones_directas': [{'bienio': x['bienio'], 'saldo': x['saldo'], 'que_mide': x['que_mide_el_saldo'],
                                              'cruza_dos_gobiernos': periodo_de(int(x['bienio'][:4])) != periodo_de(int(x['bienio'][-4:]))} for x in ad
                                             if x['saldo'] is not None and periodo_de(int(x['bienio'][-4:])) == p['periodo']],
            'nota_saldos': 'Cada saldo se asigna al gobierno que cerró el bienio; los bienios 2015-2016, 2019-2020 y 2023-2024 empezaron en el gobierno anterior.',
            'oportunidades_en_fondos': [{'fondo': x['fondo'], 'tipo': x['tipo'], 'monto_referencia_min': x['monto_referencia_min'], 'monto_referencia_max': x['monto_referencia_max']} for x in opp],
            'nota_oportunidades': 'Rangos de referencia de cada fondo, no plata perdida comprobada; no se deben sumar entre sí (mezclan hechos, contrafactuales y crédito).',
        })

    data = {
        'titulo': 'Regalías y fondos externos de Yondó, 2004–2027',
        'corte': CORTE, 'generado_por': 'scripts/sgr_fondos.py', 'moneda': 'pesos colombianos corrientes del año indicado en cada cifra (sin deflactar)',
        'como_leer': [
            'Hecho: cifra tomada de un registro oficial verificable (GESPROY, MapaInversiones, MinHacienda, CHIP, ART, MinTIC).',
            'Estimado: cálculo con método explícito sobre registros oficiales; se da como rango cuando hay supuestos.',
            'Contrafactual: lo que pudo pasar si Yondó hubiera gestionado como sus pares; no es plata perdida comprobada.',
            'Este archivo describe hechos y oportunidades perdidas. No acusa a nadie: una investigación no es una condena.',
        ],
        'fuentes': FUENTES,
        'definiciones': {
            'periodo': 'Gobierno municipal según el año estimado de aprobación: el mayor entre el año de registro del BPIN y la primera vigencia con recursos SGR en MapaInversiones (que corresponde al primer año del bienio); si el horizonte y el primer contrato empiezan al año siguiente, se toma ese año. Los bienios 2015-2016, 2019-2020 y 2023-2024 cruzan dos gobiernos: los proyectos fechados en 2015, 2019 o 2023 llevan la marca anio_en_bienio_compartido porque pudieron aprobarse a comienzos del año siguiente. Para proyectos no aprobados se usa el año de registro del BPIN.',
            'aprobado': 'Valor total del proyecto en GESPROY; si no existe, valor vigente de MapaInversiones o lo aprobado por MinHacienda en 2025-2026. Incluye cofinanciación de otras fuentes cuando el registro la suma.',
            'pagado': 'Valor × ejecución financiera de GESPROY; si no existe, pagos de MinHacienda 2025-2026 o de MapaInversiones (topados al valor).',
            'terminado': 'Estado TERMINADO en GESPROY, o "Terminado" en MapaInversiones cuando GESPROY no lo tiene; si GESPROY dice "en ejecución", solo cuenta como terminado con avance físico de 95 % o más.',
            'girado_sin_avance': 'valor × max(0, ejecución financiera − ejecución física) / 100, por proyecto, con datos de GESPROY (ejecución financiera topada en 100 %).',
            'grupo_ejecutor': '"municipio" = alcaldía, su empresa de servicios públicos o la E.S.E.; "otros" = departamento, INVÍAS, universidades, asociaciones de municipios, provincias y otros municipios.',
            'devuelto_mga': 'Proyecto formulado que el sistema devolvió a la Metodología General Ajustada (MGA) para corregir: no se aprobó.',
        },
        'totales': {
            'proyectos': len(items), 'aprobados': len(ap), 'aprobado': sum(i['valor'] for i in ap), 'pagado': sum(i['pagado'] for i in ap),
            'girado_sin_avance': sum(i['girado_sin_avance'] or 0 for i in ap),
            'girado_sin_avance_ejecutor_municipal': sum(i['girado_sin_avance'] or 0 for i in ap if i['grupo_ejecutor'] == 'municipio'),
            'devueltos_mga': {'n': sum(1 for i in items if i['clase'] == 'devuelto_mga'), 'valor_formulado': sum(i['valor'] for i in items if i['clase'] == 'devuelto_mga')},
            'asignaciones_directas': ad_tot,
            'regalias_directas_2004_2011': sum(a['regalias_giradas'] for a in rd['anios']),
        },
        'resumen_por_periodo': resumen,
        'proyectos_por_periodo': por_periodo,
        'asignaciones_directas': ad,
        'regalias_directas_2004_2011': rd,
        'fondos': fon,
        'contexto_pdet_iniciativas': {'datos': pdet, 'fuente': 'https://www.datos.gov.co/d/gmvf-t63e',
                                      'lectura': 'Yondó tiene una proporción de iniciativas PDET con ruta de implementación parecida a la de sus pares; la brecha está en convertirlas en proyectos aprobados y bien ejecutados.'},
        'notas': [
            'Los proyectos multimunicipales (INVÍAS, Gobernación, U. de Antioquia) se cuentan por su valor total, no por la parte de Yondó; por eso se separan en "otros" y "otros_multimunicipales".',
            'GESPROY y MapaInversiones no siempre coinciden. Ejemplos: los estudios de la Transversal de las Américas (GESPROY $1.344 M; MapaInversiones $10.288 M) y la placa huella de Caño Negro y Caño Bonito (GESPROY $16.722 M; MapaInversiones $11.074 M vigente). Cada ítem trae "alertas_datos" cuando hay diferencias.',
            'MapaInversiones duplica valores en algunas vigencias recientes del conjunto v4ap-cvae; por eso se usa solo para fechar proyectos y para sumar asignaciones directas por bienio, y se contrasta con MinHacienda (2025-2026: $39.455 M en v4ap frente a $39.771 M en MinHacienda).',
            'Los aprobados de MinHacienda 2025-2026 incluyen saldos de proyectos aprobados en bienios anteriores que se vuelven a presupuestar (por ejemplo, la vía Ye de Marley – San Francisco); no se suman al valor original.',
            'El proyecto 20201301012118 (ciénaga Sardinata, "Viable") fue reemplazado por el 2023058930020, que sí se aprobó y terminó.',
            'El conjunto de contratos (uwns-mbwd) solo trae los contratos reportados al sistema de regalías; "sin contrato registrado" es una alerta para verificar, no prueba de que no hubo contrato. No se publican nombres de contratistas.',
            'Un mismo proyecto puede aparecer varias veces entre los devueltos a la MGA o en formulación porque se registró de nuevo con otro BPIN (por ejemplo, el polideportivo con características de inclusión, $2.533 M, aparece dos veces). Por eso el "valor formulado" de los devueltos mide intentos, no plata disponible.',
            'Los saldos por bienio no son plata perdida: en el SGR lo no ejecutado pasa al bienio siguiente. Lo que sí muestran es plata disponible que tardó en convertirse en obras.',
            'TerriData (GESPROY) registraba en junio de 2018 cinco proyectos aprobados sin contratar.',
            'En asignaciones directas, "asignado" (MapaRegalías) y "aprobado" (MapaInversiones) vienen de sistemas distintos y no cuadran entre sí: lo aprobado incluye saldos de bienios anteriores que se vuelven a aprobar. Para medir la plata sin usar se prefieren los saldos oficiales (SICODIS 2018, CHIP y MinHacienda).',
            'Periodo 2024-2027 en curso: cifras parciales con corte de octubre de 2026.',
        ],
        'auditoria': {'chip_historico': {k: {kk: round(vv) for kk, vv in v.items()} for k, v in chip_hist.items()}},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'Escrito {OUT.relative_to(R)}: {len(items)} proyectos, {len(fon)} fondos')
    for rr in resumen:
        print(f"  {rr['periodo']}: aprobado {cop(rr['sgr_aprobado'])} M · pagado {cop(rr['sgr_pagado'])} M · "
              f"girado sin avance {cop(rr['girado_sin_avance'])} M · devueltos MGA {rr['devueltos_mga']['n']}")


if __name__ == '__main__':
    main()
