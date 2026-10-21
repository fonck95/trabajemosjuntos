#!/usr/bin/env python3
"""D2 · "Fugas" en la contratación pública de Yondó, por año, gobierno y entidad.

Qué calcula (todo en pesos corrientes de cada año; otro script deflacta):
  - valor total, contratación sin competencia y contratación directa;
  - OPS (y OPS de formulación/estructuración de proyectos);
  - estudios, diseños y consultorías, y cuánto de ese valor no tiene obra posterior identificable;
  - obras de más de $1.000 millones sin contrato de interventoría identificable;
  - adiciones en valor y prórrogas (solo donde SECOP las publica);
  - procesos con un solo oferente (SECOP II) y régimen especial;
  - convenios interadministrativos y administración delegada (EDU de Medellín y otros);
  - concentración (10 mayores contratistas e índice HHI);
  - indicios de fraccionamiento (mismo contratista, objeto parecido, 30 días, cada contrato bajo el umbral).

Reutiliza la limpieza, la deduplicación, la función cat() y la coincidencia estudio→obra de
scripts/secop_analisis.py (copiadas abajo sin cambios, porque ese script corre al importarse) y
comprueba que se reproducen las cifras ya publicadas.

Uso (desde la raíz del repositorio):
  python3 scripts/fugas_secop.py --descargar   # baja los datos crudos a data/secop/raw/ (por páginas)
  python3 scripts/fugas_secop.py               # escribe data/comparativa/fugas_secop.json

Reglas: no se publican nombres ni documentos de personas naturales contratistas; las empresas y
entidades sí se nombran. Una coincidencia estadística es un indicio, no una conclusión.
"""
import json
import re
import subprocess
import sys
import time
import unicodedata
import urllib.parse
from datetime import date
from pathlib import Path

R = Path(__file__).resolve().parent.parent
RAW = R / 'data' / 'secop' / 'raw'
OUT = R / 'data' / 'comparativa' / 'fugas_secop.json'
SOCRATA = 'https://www.datos.gov.co/resource/{}.json'

# ----------------------------------------------------------------------------- descarga
C_S2 = ('nombre_entidad,nit_entidad,proceso_de_compra,id_contrato,referencia_del_contrato,estado_contrato,'
        'descripcion_del_proceso,objeto_del_contrato,tipo_de_contrato,modalidad_de_contratacion,justificacion_modalidad_de,'
        'fecha_de_firma,fecha_de_inicio_del_contrato,fecha_de_fin_del_contrato,tipodocproveedor,documento_proveedor,'
        'proveedor_adjudicado,es_grupo,habilita_pago_adelantado,liquidaci_n,origen_de_los_recursos,destino_gasto,'
        'valor_del_contrato,valor_de_pago_adelantado,valor_facturado,valor_pendiente_de_pago,valor_pagado,valor_amortizado,'
        'valor_pendiente_de_ejecucion,dias_adicionados,duraci_n_del_contrato,el_contrato_puede_ser_prorrogado,urlproceso,'
        'presupuesto_general_de_la_nacion_pgn,sistema_general_de_participaciones,sistema_general_de_regal_as,'
        'recursos_propios_alcald_as_gobernaciones_y_resguardos_ind_genas_,recursos_de_credito,recursos_propios,ultima_actualizacion')
C_P2 = ('entidad,nit_entidad,id_del_proceso,referencia_del_proceso,nombre_del_procedimiento,descripci_n_del_procedimiento,fase,'
        'fecha_de_publicacion_del,precio_base,modalidad_de_contratacion,justificaci_n_modalidad_de,proveedores_invitados,'
        'proveedores_con_invitacion,proveedores_que_manifestaron,respuestas_al_procedimiento,respuestas_externas,'
        'conteo_de_respuestas_a_ofertas,proveedores_unicos_con,estado_del_procedimiento,adjudicado,id_adjudicacion,'
        'fecha_adjudicacion,valor_total_adjudicacion,nit_del_proveedor_adjudicado,tipo_de_contrato,subtipo_de_contrato,urlproceso')
C_S1 = ('uid,anno_firma_contrato,nombre_entidad,nit_de_la_entidad,modalidad_de_contratacion,estado_del_proceso,'
        'causal_de_otras_formas_de,nombre_regimen_de_contratacion,objeto_a_contratar,detalle_del_objeto_a_contratar,tipo_de_contrato,'
        'numero_de_constancia,numero_de_proceso,numero_de_contrato,cuantia_proceso,tipo_identifi_del_contratista,'
        'identificacion_del_contratista,nom_razon_social_contratista,fecha_de_firma_del_contrato,fecha_ini_ejec_contrato,'
        'plazo_de_ejec_del_contrato,rango_de_ejec_del_contrato,tiempo_adiciones_en_dias,tiempo_adiciones_en_meses,'
        'fecha_fin_ejec_contrato,cuantia_contrato,valor_total_de_adiciones,valor_contrato_con_adiciones,proponentes_seleccionados,'
        'ruta_proceso_en_secop_i,marcacion_adiciones,fecha_liquidacion,codigo_bpin,destino_gasto')
C_MOD = ('identificador,id_contrato,fecha_de_aprobacion,descripcion,dias_extendidos,proposito_modificacion,valor_modificacion,'
         'estado_modificacion,identificador_modificacion,fecha_version,numero_version,fecha_inicio_contrato,fecha_fin_contrato')
C_EDU = ('nombre_entidad,id_contrato,fecha_de_firma,valor_del_contrato,proveedor_adjudicado,tipodocproveedor,modalidad_de_contratacion,'
         'objeto_del_contrato,valor_pagado,valor_facturado,valor_de_pago_adelantado,dias_adicionados,estado_contrato,urlproceso')
W_INT = "municipio_entidad='Yondó' OR upper(nombre_de_la_entidad) like '%YOND%'"


def _curl(url, intentos=5):
    for i in range(intentos):
        p = subprocess.run(['curl', '-sS', '-m', '600', '--retry', '2', url], capture_output=True, text=True)
        if p.returncode == 0:
            try:
                data = json.loads(p.stdout)
                if isinstance(data, list):
                    return data
                print('  respuesta de error de la API:', str(data)[:300], file=sys.stderr)
            except json.JSONDecodeError:
                print('  respuesta incompleta, reintento', file=sys.stderr)
        else:
            print('  curl falló:', p.stderr.strip()[:200], file=sys.stderr)
        time.sleep(5 * (i + 1))
    raise RuntimeError(f'No se pudo descargar {url[:200]}')


def socrata(dataset, where, select=None, paso=5000):
    """Descarga por páginas: las 14.301 filas en un solo bloque se cortan a mitad de camino."""
    out, off = [], 0
    while True:
        q = {'$where': where, '$limit': str(paso), '$offset': str(off), '$order': ':id'}
        if select:
            q['$select'] = select
        lote = _curl(SOCRATA.format(dataset) + '?' + urllib.parse.urlencode(q))
        out += lote
        print(f'  {dataset}: {len(out)} filas', file=sys.stderr)
        if len(lote) < paso:
            return out
        off += paso


def socrata_in(dataset, campo, valores, select=None, paso=60):
    out = []
    for i in range(0, len(valores), paso):
        chunk = valores[i:i + paso]
        out += socrata(dataset, f"{campo} in(" + ','.join(f"'{v}'" for v in chunk) + ')', select)
    return out


def descargar(raw=RAW):
    raw.mkdir(parents=True, exist_ok=True)
    guardar = lambda nombre, datos: json.dump(datos, open(raw / nombre, 'w'), ensure_ascii=False)
    # Mismo filtro que scripts/descargar_secop.sh, pero por páginas
    guardar('integrado.json', socrata('rpmr-utcd', W_INT))
    s2 = socrata('jbjy-vk9h', "upper(nombre_entidad) like '%YOND%'", C_S2)
    guardar('secop2_contratos.json', s2)
    guardar('secop2_procesos.json', socrata('p6dx-8zbt', "upper(entidad) like '%YOND%'", C_P2))
    guardar('secop1_procesos.json', socrata('f789-7hwg', "upper(nombre_entidad) like '%YOND%'", C_S1))
    ids = sorted({r['id_contrato'] for r in s2 if r.get('id_contrato')})
    guardar('secop2_adiciones.json', socrata_in('cb9c-h8sn', 'id_contrato', ids))
    guardar('secop2_modificaciones.json', socrata_in('u8cx-r425', 'id_contrato', ids, C_MOD))
    # Contratos que la EDU de Medellín firmó en SECOP II con objeto en Yondó (ejecución de la administración delegada)
    guardar('secop2_edu_yondo.json', socrata('jbjy-vk9h', "upper(nombre_entidad) like '%DESARROLLO URBANO%' AND "
                                              "(upper(objeto_del_contrato) like '%YOND%' OR upper(descripcion_del_proceso) like '%YOND%')", C_EDU))
    for f in sorted(raw.glob('*.json')):
        print(f.name, len(json.load(open(f))), 'registros')


# ----------------------------------------------------------------------------- limpieza (copia de secop_analisis.py)
def cargar(D):
    """Copia literal de scripts/secop_analisis.py, líneas 4–53 (limpieza, deduplicación, cat, periodo).
    Si cambia allá, hay que cambiarlo acá; la sección 'verificacion' del JSON avisa si las cifras no cuadran."""
    import pandas as pd
    d = pd.DataFrame(json.load(open(f'{D}/integrado.json')))
    d['valor'] = pd.to_numeric(d['valor_contrato'], errors='coerce')
    d['fecha'] = pd.to_datetime(d['fecha_de_firma_del_contrato'], errors='coerce')
    d['anio'] = d['fecha'].dt.year

    def ent(n):
        n = n.upper()
        if 'HOSPITAL' in n: return 'HOSPITAL'
        if 'ALCALD' in n or n == 'MUNICIPIO DE YONDO': return 'ALCALDIA'
        if 'AGUAS' in n or 'ACUEDUCTO' in n: return 'AGUAS'
        return 'OTRO'
    d['ent'] = d['nombre_de_la_entidad'].map(ent)
    d['obj'] = d['objeto_a_contratar'].fillna('').map(norm)
    d['tipo'] = d['tipo_de_contrato'].fillna('').map(norm)
    d['mod'] = d['modalidad_de_contrataci_n'].fillna('').map(norm)
    d['contratista_n'] = d['nom_raz_social_contratista'].fillna('').map(norm)
    d['natural'] = d['tipo_documento_proveedor'].fillna('').str.contains('dula', case=False)
    n0 = len(d)
    d = d[d['anio'].notna() & d['valor'].notna() & (d['valor'] > 0)]
    outliers = d[d['valor'] > 6e10]
    d = d[d['valor'] <= 6e10]
    # Para medir adiciones de SECOP II se guarda el menor valor de cada contrato antes de deduplicar
    vmin2 = d[d.origen == 'SECOPII'].groupby(['ent', 'numero_del_contrato'])['valor'].agg(['min', 'size'])
    s1 = d[d.origen == 'SECOPI'].drop_duplicates(subset=['ent', 'numero_del_contrato', 'valor'])
    s2 = d[d.origen == 'SECOPII'].sort_values('valor').drop_duplicates(subset=['ent', 'numero_del_contrato'], keep='last')
    d = pd.concat([s1, s2])
    d['categoria'] = d.apply(cat, axis=1)
    d['ops_formulacion'] = (d['categoria'] == 'OPS / apoyo a la gestión') & d['obj'].str.contains(r'FORMULACI|\bMGA\b|BANCO DE PROYECTOS|ESTRUCTURACI|GESTION DE PROYECTOS|PROYECTOS DE INVERSION|SECRETARIA DE PLANEACION|PLANEACION')
    d['periodo'] = d['anio'].map(periodo)
    d['directa'] = d['mod'].str.contains('DIRECTA|REGIMEN ESPECIAL|DECRETO 092')  # = "sin competencia" en secop_analisis.py
    return d, outliers, n0, vmin2


def norm(s):
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode().upper()
    return re.sub(r'\s+', ' ', s)


EST = r'ESTUDIOS? (Y |DE |TECNICOS?|PREVIOS DE INGENIERIA)|DISENOS? (ARQUITECTONICOS|TECNICOS|Y |DE |PARA )|FORMULACION (DEL|DE LOS?|Y ESTRUCTURACION)|\bMGA\b|VIABILIZACION|FACTIBILIDAD|CONSULTORIA PARA|PLAN MAESTRO|PLAN PARCIAL|PLAN DE ORDENAMIENTO|ESQUEMA DE ORDENAMIENTO|\bEOT\b|\bPBOT\b|LEVANTAMIENTO TOPOGRAF|ESTUDIO TECNICO'
NOEST = r'^(MANTENIMIENTO|SUMINISTRO|ACCIONES PARA EL CUMPLIMIENTO)|LUBRICANTES|MATERIAL PEDAGOGICO'


def cat(r):
    t, o, m = r['tipo'], r['obj'], r['mod']
    if 'INTERVENTORIA' in t or o.startswith('INTERVENTORIA'): return 'Interventoría'
    if 'OBRA' in t and 'MANO DE OBRA' not in t: return 'Obra'
    if 'CONSULTORIA' in t or (re.search(EST, o) and not re.search(NOEST, o) and not re.search(r'PRESTAR? (LOS )?SERVICIOS (PROFESIONALES|DE APOYO)|APOYO A LA GESTION', o)): return 'Estudios / consultoría'
    if ('PRESTACION DE SERVICIOS' in t) and (r['natural'] or 'DIRECTA' in m) and re.search(r'PRESTA|APOYO|SERVICIOS PROFESIONALES|ASESOR|ACOMPAN', o) and not re.search(r'INTERADMINISTRATIVO|CONVENIO', o): return 'OPS / apoyo a la gestión'
    if re.search(r'INTERADMINISTRATIVO|CONVENIO|AUNAR ESFUERZOS|ADMINISTRACION DELEGADA', o) or 'DECRETO 092' in t: return 'Convenios / interadministrativos'
    if re.search(r'EMPRESA DE SERVICIOS PUBLICOS|AGUAS Y ASEO|HOSPITAL HECTOR ABAD|DESARROLLO URBANO|MUNICIPIO DE|DEPARTAMENTO DE|GOBERNACION', r['contratista_n']): return 'Convenios / interadministrativos'
    if re.match(r'(CONSTRUCCION|OBRA|PAVIMENTACION|REHABILITACION|MEJORAMIENTO DE (LA )?VIA|PLACA HUELLA)', o) and not re.search(r'SUMINISTRO|COMPRAVENTA', t): return 'Obra'
    if re.search(r'SUMINISTRO|COMPRAVENTA', t): return 'Suministro / compraventa'
    return 'Otros servicios'


PERIODOS = [(2004, '2004-2007'), (2008, '2008-2011'), (2012, '2012-2015'), (2016, '2016-2019'), (2020, '2020-2023'), (2024, '2024-2027')]


def periodo(a):
    a = int(a)
    for i, p in PERIODOS:
        if i <= a <= i + 3: return p


# Coincidencia estudio → obra: copia de secop_analisis.py, líneas 67–85
STOP = set('DE LA EL LOS LAS DEL Y EN PARA POR CON A AL SE QUE O U MUNICIPIO YONDO ANTIOQUIA ESTUDIOS ESTUDIO DISENOS DISENO TECNICOS TECNICO CONSTRUCCION MEJORAMIENTO REALIZAR ELABORACION ELABORAR CONSULTORIA PROYECTO PROYECTOS FASE II III I SU DETALLADOS DETALLE ADECUACION OBRAS OBRA REALIZACION SERVICIOS PRESTACION CONTRATAR CONTRATACION MUNICIPAL URBANA RURAL ZONA SECTOR'.split())


def kw(o): return {w for w in re.findall(r'[A-Z]{4,}', o) if w not in STOP}


def jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


# ----------------------------------------------------------------------------- utilidades nuevas
ENT_NOMBRE = {'ALCALDIA': 'Alcaldía', 'AGUAS': 'Aguas y Aseo', 'HOSPITAL': 'Hospital', 'OTRO': 'Otras', 'TOTAL': 'Todas'}
# Formas jurídicas o tipos de entidad que no aparecen en un nombre de persona natural
EMPRESA_RE = re.compile(r'\b(S ?A ?S|S ?A|LTDA|LIMITADA|E ?S ?P|E ?S ?E|EMPRESA|FUNDACION|ASOCIACION|ASOC|CORPORACION|COOPERATIVA|COOP|'
                        r'CONSORCIO|UNION TEMPORAL|MUNICIPIO|DEPARTAMENTO|GOBERNACION|HOSPITAL|INSTITUTO|UNIVERSIDAD|FONDO|COMPANIA|CIA|'
                        r'SOCIEDAD|CAMARA|FEDERACION|JUNTA|CLUB|BANCO|FIDUCIARIA|ASEGURADORA|SEGUROS|ORGANIZACION|AGENCIA|NACION|'
                        r'MINISTERIO|SERVICIO NACIONAL|POLICIA|EJERCITO|ESCUELA|COLEGIO|PARROQUIA|DIOCESIS|CENTRAL|RED|S EN C|SCA|'
                        r'E ?I ?C ?E|ECOPETROL|EPM|TELEFONICA|COLOMBIA)\b')
SIN_DATO = {'', 'NO DEFINIDO', 'SIN DESCRIPCION', 'NO APLICA', 'NA', 'N/A', 'SIN DATO', '0'}
SMMLV = {2007: 433700, 2008: 461500, 2009: 496900, 2010: 515000, 2011: 535600, 2012: 566700, 2013: 589500, 2014: 616000,
         2015: 644350, 2016: 689455, 2017: 737717, 2018: 781242, 2019: 828116, 2020: 877803, 2021: 908526, 2022: 1000000,
         2023: 1160000, 2024: 1300000, 2025: 1423500, 2026: 1750905}
UMBRAL_MIN_SMMLV, UMBRAL_MENOR_SMMLV = 28, 280
PUBLICAS_RE = r'EMPRESA DE SERVICIOS PUBLICOS|AGUAS (?:Y|&) ASEO|HOSPITAL|E ?S ?E\b|DESARROLLO URBANO|MUNICIPIO DE|DEPARTAMENTO DE|GOBERNACION|EMPRESA NACIONAL|ENTERRITORIO|FONDO MIXTO|INSTITUTO|UNIVERSIDAD|CITYLUM|EMPRESAS PUBLICAS|INDEPORTES|IDEA\b|ESCUELA SUPERIOR|SENA\b'


INTERNAS_RE = r'AGUAS (?:Y|&) ASEO DE YONDO|EMPRESA (?:DE )?SERVICIOS PUBLICOS DOMICI|HOSPITAL HECTOR ABAD|FONDO GANADERO|EMPRESA AGROPECUARIA DE YONDO|^MUNICIPIO DE YONDO|CONCEJO MUNICIPAL DE YONDO|PERSONERIA (?:MUNICIPAL )?DE YONDO'


def es_empresa(nombre):
    n = re.sub(r'[^A-Z0-9& ]', ' ', nombre)
    return bool(EMPRESA_RE.search(re.sub(r'\s+', ' ', n)))


# ----------------------------------------------------------------------------- ajustes para dinero_no_hecho.json (campos nuevos)
# Transferencias de la alcaldía a entidades de Yondó: además de INTERNAS_RE, grafías mal digitadas de Aguas y Aseo y del hospital
TRANSF_EXTRA_RE = r'AGUAS (?:Y|&) ASE[OI]|HOSPITAL ?HECT|^ESE HO|^(?:LA )?EMPRESA (?:DE )?SERVICIOS PUBLICOS|EMPRESA SOCIAL DEL ESTADO HOSP'
DEST_AGUAS_RE = r'AGUAS|SERVICIOS PUBLICOS'
DEST_HOSP_RE = r'HOSPITAL|^ESE |E ?S ?E\b|SOCIAL DEL ESTADO'
# Subsidios a las tarifas de servicios públicos (Fondo de Solidaridad y Redistribución del Ingreso): se buscan en el objeto completo
SUBSIDIO_RE = r'SUBSIDI|SOLIDARIDA|MINIMO VITAL'
SUBSIDIO_CTX_RE = r'ESTRATOS|SERVICIOS? (?:PUBLICOS|PULICOS|PULBIC|DOMICILIARIOS)|SERVIICIOS|FONDOS? (?:DE )?SOLIDARIDA'
SUBSIDIO_NO_RE = r'VIVIENDA|REGIMEN SUBSIDIADO|POBLACION POBRE|MEMORIA'
# Instituciones públicas que no son "nómina paralela" aunque cat() las ponga en OPS
INST_PUB_RE = r'UNIVERSIDAD|INSTITUTO UNIVERSITARIO|POLITECNICO|GOBERNACION|DEPARTAMENTO DE|DESARROLLO URBANO|ESCUELA SUPERIOR'
AUNAR_RE = r'A(?:UN|NU)AR? ESFUERZO'
CREDITO_RE = r'EMPRESTITO|PRESTAMISTA'
# Planes que no llevan a una obra directa (se restan en el mínimo de "estudios sin obra")
PLANES_RE = r'PLAN PARCIAL|ORDENAMIENTO|\bEOT\b|\bPBOT\b|PLAN DE GESTION DEL RIESGO|PLAN DE DESARROLLO'
FECHA_CORTE = '2026-10-21'
FECHA_RECIENTES = '2025-04-21'  # estudios de los últimos 18 meses: su obra todavía puede no haberse firmado
# Estudios de la alcaldía que la regla de palabras deja "sin obra", pero cuya obra (o su naturaleza) consta fuera del SECOP de la alcaldía
OBRA_FUERA = {
    '14-12-2536297': ('obra_posterior', 'estudios de 18 acueductos rurales (2013)', 'Estudios y diseños de 18 acueductos rurales (2013, convenio con la Empresa de Servicios Públicos, BPIN 2013058930008). '
                      'Después hubo obras de acueductos veredales ejecutadas por la empresa: BPIN 2013058930013 (tanque y conducción del sistema de veredas) y '
                      'BPIN 2015058930003 (rehabilitación de acueductos rurales en 8 veredas), ambos terminados (data/comparativa/sgr_fondos.json; '
                      'docs/anexos/A-gobiernos-2004-2027.md, §8.7).'),
    '14-12-2536076': ('obra_posterior', 'estudios de 18 acueductos rurales (2013)', 'Segundo registro del mismo convenio de acueductos rurales de 2013 (misma fecha, valor y objeto).'),
    '14-15-2238279': ('obra_suspendida', 'estudios de la Ciudadela Educativa (2014)', 'Estudios y diseños de la Ciudadela Educativa (2014). Hubo contrato de obra y quedó suspendido: el plan 2020–2023 '
                      'incluye el "reinicio del contrato de obra de la Ciudadela Educativa" (docs/anexos/A-gobiernos-2004-2027.md, §8.6; data/gobiernos.json).'),
    '18-15-8305058': ('no_es_estudio_previo', 'seguimiento técnico de proyectos en ejecución (2018)', 'Acompañamiento y seguimiento técnico de proyectos que ya se estaban ejecutando (2017-05893-0003 y otros): '
                      'no es un estudio previo a una obra.'),
    '22-15-13170989': ('obra_posterior', 'estudios de servicios públicos para el barrio José Domingo Oliveros (2022)', 'Estudios y diseños para dotar de servicios públicos el barrio José Domingo Oliveros (2022, BPIN 2022058930001). '
                       'Su obra es el BPIN 2023058930018 (acueducto, alcantarillado y urbanismo en el mismo barrio, ejecutado por Aguas y Aseo; '
                       'data/comparativa/sgr_fondos.json).'),
}


def posibles_duplicados(d):
    """Registros de $100 millones o más que coinciden con otro en entidad, fecha de firma, valor y contratista, con objeto parecido."""
    dup_ids = set()
    for _, g in d[d.valor >= 1e8].groupby(['ent', 'dia', 'valor']):
        if len(g) < 2: continue
        rr = list(g.itertuples())
        for a_i, a in enumerate(rr):
            for b in rr[a_i + 1:]:
                pa, pb = set(re.findall(r'[A-Z]{3,}', a.contratista_n)), set(re.findall(r'[A-Z]{3,}', b.contratista_n))
                mismo = (a.cid is not None and a.cid == b.cid) or a.contratista_n[:15] == b.contratista_n[:15] or jaccard(pa, pb) >= 0.5
                if mismo and (jaccard(kw(a.obj), kw(b.obj)) >= 0.4 or a.obj[:60] == b.obj[:60]):
                    dup_ids.update([a.rid, b.rid])
    return dup_ids


ORG2_RE = re.compile(r'\b(UT|E ?U|BOMBEROS|LABORATORIO|ESTACION DE SERVICIOS?|CENTRO DE|INGENIERIA|INGENIERA DE PROYECTOS?|CONSTRUCCIONES|'
                     r'CONSTRUCTORA|CONSULTORIA|COMERCIALIZADORA|DISTRIBUIDORA|INSPECCIONES|ASISTENCIA MEDICA|OBRAS CIVILES|MANTENIMIENTO|'
                     r'TELECOMUNICACIONES|INFORMATICA|COORPORACION|COLOMBIANA|PROYECTOS)\b')
NATURAL_DOC = ('DULA', 'NATURAL', 'TARJETA', 'PASAPORTE', 'CARNE')


def sin_parentesis(s):
    return re.sub(r'\(.*?\)|\(.*$', '', str(s)).strip()


def publicar_nombre(nombre, tipo_doc):
    """Nombre del contratista solo si es empresa o entidad. Nunca se publica el de una persona natural."""
    n = sin_parentesis(norm(nombre or ''))
    if n in SIN_DATO: return 'Sin dato en SECOP'
    publicar = re.sub(r'\s+', ' ', sin_parentesis(nombre))[:90]
    if es_empresa(n): return publicar
    tipo = norm(tipo_doc or '')
    if any(t in tipo for t in NATURAL_DOC): return 'Persona natural (nombre no publicado)'
    if ('JURIDICA' in tipo or tipo == 'NIT' or 'SOCIEDAD' in tipo) and ((' ' not in n and len(n) >= 4) or ORG2_RE.search(re.sub(r'[^A-Z0-9& ]', ' ', n))):
        return publicar
    return 'Nombre no publicado (no se pudo confirmar que sea empresa)'


# Entidades públicas que aparecen con muchas grafías y documentos mal digitados: se unifican
CANON = [(r'AGUAS (?:Y|&) ASEO DE YONDO|SERVICIOS PUBLICOS DOMICI', 'D811021151', 'Aguas y Aseo de Yondó S.A. E.S.P. (antes Empresa de Servicios Públicos Domiciliarios; NIT 811021151)'),
         (r'DESARROLLO URBANO', 'EEDU', 'Empresa de Desarrollo Urbano de Medellín (EDU)'),
         (r'HOSPITAL HECTOR ABAD', 'EHOSP', 'E.S.E. Hospital Héctor Abad Gómez de Yondó')]


def canon(r):
    n, doc = r['contratista_n'], str(r.get('documento_proveedor') or '')
    for pat, cid, nombre in CANON:
        if re.search(pat, n) and 'CEJA' not in n:
            if cid == 'D811021151' and not ('AGUAS' in n or '811021' in doc or 'YONDO' in n or r['ent'] == 'ALCALDIA'):
                continue
            return cid, nombre
    return None


def nombre_publico(r):
    return publicar_nombre(r['nom_raz_social_contratista'], r.get('tipo_documento_proveedor'))


def contratista_id(r):
    tipo = norm(r.get('tipo_documento_proveedor') or '')
    doc = re.sub(r'\D', '', str(r.get('documento_proveedor') or '').split('-')[0])
    if len(doc) >= 5 and not set(doc) <= {'0'}:
        if 'NIT' in tipo and len(doc) >= 10: doc = doc[:9]
        return 'D' + doc
    n = r['contratista_n'].strip()
    if n in SIN_DATO: return None
    return 'N' + re.sub(r'[^A-Z0-9]', '', n)


def modg(m):
    if 'REGIMEN ESPECIAL' in m: return 'Régimen especial'
    if 'DIRECTA' in m: return 'Contratación directa'
    if 'MINIMA' in m: return 'Mínima cuantía'
    if 'SELECCION ABREVIADA' in m or 'SUBASTA' in m: return 'Selección abreviada'
    if 'LICITACION' in m: return 'Licitación pública'
    if 'CONCURSO' in m: return 'Concurso de méritos'
    if 'PUBLICO PRIVADA' in m: return 'Asociación público-privada'
    return 'Otra o sin dato'


def notice(u):
    m = re.search(r'noticeUID=(CO1\.NTC\.\d+)', str(u or ''))
    return m.group(1) if m else None


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def r0(x): return int(round(float(x)))


def pct(a, b): return round(100 * a / b, 1) if b else None


def miles(x): return f'{r0(x):,}'.replace(',', '.')


def corto(s, n=240):
    s = re.sub(r'\s+', ' ', str(s or '')).strip()
    return s if len(s) <= n else s[:n - 1].rstrip() + '…'


# ----------------------------------------------------------------------------- análisis
def main(D=RAW):
    import pandas as pd
    d, outliers, n0, vmin2 = cargar(D)
    d = d.copy()
    d['entidad'] = d['ent'].map(ENT_NOMBRE)
    d['anio'] = d['anio'].astype(int)
    d['modg'] = d['mod'].map(modg)
    d['cid'] = d.apply(contratista_id, axis=1)
    d['contratista_pub'] = d.apply(nombre_publico, axis=1)
    cn = d.apply(canon, axis=1)
    m = cn.notna()
    d.loc[m, 'cid'] = cn[m].map(lambda t: t[0])
    d.loc[m, 'contratista_pub'] = cn[m].map(lambda t: t[1])
    # Si un mismo documento aparece con nombre publicable en una fila y sin confirmar en otra, se usa el publicable (nunca para personas naturales)
    ok = d[~d.contratista_pub.str.startswith(('Persona natural', 'Nombre no publicado', 'Sin dato')) & d.cid.notna()]
    mapa = ok.groupby('cid')['contratista_pub'].agg(lambda x: x.value_counts().index[0])
    nat = set(d[d.contratista_pub.str.startswith('Persona natural') & d.cid.notna()].cid)
    m = d.contratista_pub.str.startswith('Nombre no publicado') & d.cid.isin(mapa.index) & ~d.cid.isin(nat)
    d.loc[m, 'contratista_pub'] = d.loc[m, 'cid'].map(mapa)
    d['publica'] = d['contratista_n'].str.contains(PUBLICAS_RE)
    d['interna'] = d['contratista_n'].str.contains(INTERNAS_RE)  # el contratista es otra entidad de Yondó
    d['objeto'] = d['objeto_a_contratar'].where(~d['obj'].isin(['NO DEFINIDO', '']), d['objeto_del_proceso']).fillna('')
    d['url'] = d['url_contrato'].fillna('')
    d['rid'] = range(len(d))
    d = d.set_index('rid', drop=False)

    # --- 1. estudios → obra (lógica publicada para la alcaldía; extensión a Aguas y Aseo y hospital)
    obras_alc = d[(d.categoria == 'Obra') & (d.ent == 'ALCALDIA') & ~d.obj.str.contains(r'PRESTACION DE SERVICIOS|APOYO A LA GESTION|^ACCIONES PARA')].copy()
    obras_ext = d[(d.categoria == 'Obra') & d.ent.isin(['ALCALDIA', 'AGUAS', 'HOSPITAL']) & ~d.obj.str.contains(r'PRESTACION DE SERVICIOS|APOYO A LA GESTION|^ACCIONES PARA')].copy()
    for o in (obras_alc, obras_ext):
        o['kw'] = o['obj'].map(kw)
    est = d[d.categoria == 'Estudios / consultoría'].drop_duplicates(subset=['ent', 'anio', 'valor', 'obj'])  # = drop_duplicates(['anio','valor','obj']) por entidad
    d['est_evaluado'] = d.index.isin(est.index)
    d['est_obra'] = None
    d['est_sim'] = None
    for i, r in est.iterrows():
        pool = obras_alc if r['ent'] == 'ALCALDIA' else obras_ext
        k = kw(r['obj']); best, bs = None, 0
        for _, o in pool[pool.anio >= r['anio']].iterrows():
            if not k or not o['kw']: continue
            s = len(k & o['kw']) / len(k | o['kw'])
            if s > bs: bs, best = s, o
        con = best is not None and bs >= 0.3
        d.at[i, 'est_obra'] = bool(con)
        d.at[i, 'est_sim'] = round(bs, 2)
        d.at[i, 'est_sim_raw'] = float(bs)
    d['est_sin_obra'] = d['est_evaluado'] & (d['est_obra'] == False)  # noqa: E712
    # "Mixtos": el mismo contrato incluye diseño y construcción (la obra va dentro del contrato, no después)
    MIXTO = (r'(?:ESTUDIOS?|DISENOS?)\b[^.]{0,60}?\b(?:Y|E|ASI COMO)\s+(?:LA |LAS |LOS |EL )?(?:ADECUACION|CONSTRUCCION|CONSTRUCCIONES|EJECUCION DE (?:LAS )?OBRAS|INTERVENTORIAS? Y CONSTRUCCION)'
             r'|CONSTRUCCION DE LAS OBRAS')
    PARA = r'(?:ESTUDIOS?|DISENOS?)(?: TECNICOS?| Y DISENOS?| DEFINITIVOS)? PARA (?:LA|EL|LOS|LAS)\b'
    d['est_mixto'] = d['est_sin_obra'] & (d.obj.str.contains('ADMINISTRACION DELEGADA') | (d.obj.str.contains(MIXTO) & ~d.obj.str.contains(PARA)))

    # --- 2. obras > 1.000 millones sin interventoría identificable
    STOP_I = STOP | set('INTERVENTORIA INTEVENTORIA TECNICA TENICA ADMINISTRATIVA ADMINISIKATIVA FINANCIERA FINANCIARA CONTABLE AMBIENTAL SOCIAL '
                        'JURIDICA LEGAL INTEGRAL PUBLICA CONTRATO EJECUCION DEPARTAMENTO DENOMINADO CUYO OBJETO'.split())
    kwi = lambda o: {w for w in re.findall(r'[A-Z]{4,}', o) if w not in STOP_I}
    bpin = lambda o: set(re.findall(r'(?:19|20)\d{2}[- ]?05893[- ]?\d{3,4}|\b20\d{11}\b', o))
    inter = d[(d.categoria == 'Interventoría') | d.obj.str.contains('INTERVENTORIA|INTEVENTORIA')].copy()
    inter['kw'] = inter['obj'].map(kwi)
    inter['bp'] = inter['obj'].map(bpin)
    delegada_obra = d.obj.str.contains('ADMINISTRACION DELEGADA') & d.obj.str.contains('CONSTRUCCION|OBRA|ADECUACION|MEJORAMIENTO|PAVIMENT')
    cand = d[(d.valor > 1e9) & ((d.categoria == 'Obra') | delegada_obra)].copy()
    obras_sin_int, n_obra_big, n_obra_big_con = [], 0, 0
    d['obra_sin_int'] = False
    d['obra_big'] = False
    for i, r in cand.iterrows():
        ko, bo = kwi(r['obj']), bpin(r['obj'])
        w = inter[(inter.index != i) & (inter.fecha >= r['fecha'] - pd.Timedelta(days=120)) & (inter.fecha <= r['fecha'] + pd.Timedelta(days=365))]
        best, bs = None, 0.0
        for _, x in w.iterrows():
            if bo and bo & x['bp']:
                best, bs = x, 1.0
                break
            if not ko or not x['kw']: continue
            ov = len(ko & x['kw'])
            s = max(jaccard(ko, x['kw']), ov / len(ko))
            if ov >= 3 and ov / min(len(ko), len(x['kw'])) >= 0.6:  # objeto corto de interventoría contenido en el de la obra
                s = max(s, 0.5)
            if s > bs: bs, best = s, x
        incluida = 'INTERVENTORIA' in r['obj'] or 'INTEVENTORIA' in r['obj']
        hay = best is not None and bs >= 0.5
        d.at[i, 'obra_big'] = True
        n_obra_big += 1
        if hay or incluida:
            n_obra_big_con += 1
            continue
        d.at[i, 'obra_sin_int'] = True
        obras_sin_int.append({
            'entidad': r['entidad'], 'anio': int(r['anio']), 'fecha': str(r['fecha'])[:10], 'valor': r0(r['valor']),
            'tipo': 'Administración delegada (convenio)' if delegada_obra.get(i, False) and r['categoria'] != 'Obra' else 'Contrato de obra',
            'modalidad': r['modg'], 'objeto': corto(r['objeto']), 'contratista': r['contratista_pub'],
            'interventoria_mas_parecida': (None if best is None else {'anio': int(best['anio']), 'valor': r0(best['valor']), 'objeto': corto(best['objeto'], 160), 'similitud': round(bs, 2)}),
            'nota': ('La entidad delegada (EDU, Aguas y Aseo u otra) suele contratar la interventoría por su cuenta; hay que pedirla en su expediente.'
                     if 'DELEGADA' in r['obj'] else
                     'La obra ejecuta un convenio con otra entidad (por ejemplo, INVÍAS en Colombia Rural); la interventoría pudo contratarla esa entidad. Hay que verificarlo.'
                     if re.search(r'CONVENIO|COLOMBIA RURAL', r['obj']) else
                     ('Adjudicada por licitación: la ley exige interventoría externa (Ley 80 de 1993, art. 32, num. 1, parágrafo 1). Puede estar registrada con otro objeto o fuera de SECOP.'
                      if r['modg'] == 'Licitación pública' else
                      'Sin licitación la ley permite que la vigile un supervisor de la entidad (Ley 1474 de 2011, art. 83); hay que verificar quién la vigiló y con qué informes.')),
            'url': r['url']})
    obras_sin_int.sort(key=lambda x: -x['valor'])

    # --- 3. adiciones y prórrogas
    f1 = pd.DataFrame(json.load(open(f'{D}/secop1_procesos.json')))
    for c in ['valor_total_de_adiciones', 'tiempo_adiciones_en_dias', 'tiempo_adiciones_en_meses', 'cuantia_contrato']:
        f1[c] = pd.to_numeric(f1[c], errors='coerce').fillna(0)
    f1['dias_ad'] = f1['tiempo_adiciones_en_dias'] + 30 * f1['tiempo_adiciones_en_meses']
    f1g = f1.groupby('numero_de_constancia').agg(adv=('valor_total_de_adiciones', 'max'), add=('dias_ad', 'max'), cu=('cuantia_contrato', 'max'))
    s2c = pd.DataFrame(json.load(open(f'{D}/secop2_contratos.json')))
    s2c['dias_adicionados'] = pd.to_numeric(s2c['dias_adicionados'], errors='coerce').fillna(0)
    for c in ['valor_pagado', 'valor_facturado', 'valor_de_pago_adelantado', 'valor_del_contrato']:
        s2c[c] = pd.to_numeric(s2c[c], errors='coerce').fillna(0)
    s2g = s2c.set_index('id_contrato')
    d['adic_dato'] = False
    d['adic_valor'] = 0.0
    d['adic_dias'] = 0.0
    m1 = d.origen.eq('SECOPI') & d.numero_del_contrato.isin(f1g.index)
    d.loc[m1, 'adic_dato'] = True
    # Si un número de constancia quedó en varias filas (valores distintos), la adición se asigna una sola vez (a la de mayor valor)
    primero = d[m1].sort_values('valor', ascending=False).drop_duplicates(['ent', 'numero_del_contrato']).index
    m1p = d.index.isin(primero)
    d.loc[m1p, 'adic_valor'] = d.loc[m1p, 'numero_del_contrato'].map(f1g['adv']).values
    d.loc[m1p, 'adic_dias'] = d.loc[m1p, 'numero_del_contrato'].map(f1g['add']).values
    m2 = d.origen.eq('SECOPII')
    d.loc[m2, 'adic_dato'] = True
    key2 = list(zip(d.loc[m2, 'ent'], d.loc[m2, 'numero_del_contrato']))
    vmin = [vmin2['min'].get(k, v) for k, v in zip(key2, d.loc[m2, 'valor'])]
    d.loc[m2, 'adic_valor'] = (d.loc[m2, 'valor'].values - pd.Series(vmin).values).clip(min=0)
    d.loc[m2, 'adic_dias'] = d.loc[m2, 'numero_del_contrato'].map(s2g['dias_adicionados']).fillna(0).values
    d['valor_inicial'] = d['valor'] - d['adic_valor'].where(m2, 0)  # en SECOP II el valor publicado ya incluye la adición
    # Base para el % de adición: cuantía inicial de f789 en SECOP I (si existe) y valor de la primera versión en SECOP II
    cu1 = d['numero_del_contrato'].map(f1g['cu']).where(m1p)
    d['base_adic'] = cu1.where(cu1 > 0, d['valor_inicial'])
    d['pct_adic'] = (100 * d['adic_valor'] / d['base_adic']).where(d['adic_valor'] > 0, 0)

    # --- 4. un solo oferente (SECOP II) y régimen especial
    p2 = pd.DataFrame(json.load(open(f'{D}/secop2_procesos.json')))
    p2['ntc'] = p2['urlproceso'].map(lambda u: notice(u.get('url') if isinstance(u, dict) else u))
    p2['ofer'] = pd.to_numeric(p2['proveedores_unicos_con'], errors='coerce')
    p2g = p2[p2.ntc.notna()].sort_values('ofer').drop_duplicates('ntc', keep='last').set_index('ntc')['ofer']
    d['ntc'] = d['url'].map(notice)
    d['competitivo'] = d['modg'].isin(['Mínima cuantía', 'Selección abreviada', 'Licitación pública', 'Concurso de méritos'])
    d['con_ofertas'] = d['mod'].str.contains(r'\(CON OFERTAS\)')  # directa o régimen especial con invitación a ofertar
    d['oferentes'] = d['ntc'].map(p2g)
    d['un_oferente'] = d['competitivo'] & (d['oferentes'] == 1)
    d['ofer_dato'] = d['competitivo'] & d['oferentes'].notna()
    d['co_dato'] = d['con_ofertas'] & d['oferentes'].notna()
    d['co_uno'] = d['con_ofertas'] & (d['oferentes'] == 1)

    # --- 5. convenios, administración delegada y EDU
    conv = d.categoria.eq('Convenios / interadministrativos')
    d['edu'] = d['contratista_n'].str.contains('DESARROLLO URBANO') & ~d['contratista_n'].str.contains('CEJA') & d.ent.eq('ALCALDIA')
    # Administración delegada: el objeto la menciona y no es una OPS de apoyo que solo la nombra como contexto
    d['delegada'] = (d.obj.str.contains('ADMINISTRACION DELEGADA') & ~d.categoria.eq('OPS / apoyo a la gestión')
                     & ~d.obj.str.contains(r'^PRESTACION DE (?:LOS )?SERVICIOS|SERVICIOS PROFESIONALES|APOYO A LA GESTION'))

    def tipo_conv(r):
        if r['delegada']: return 'Administración delegada'
        if r['edu']: return 'Interadministrativo con la EDU'
        if 'DECRETO 092' in r['tipo'] or (r['modg'] == 'Régimen especial' and re.search(r'FUNDACION|ASOCIACION|ASOC|CORPORACION|UNION TEMPORAL|CONSORCIO', r['contratista_n'])):
            return 'Convenio con entidad sin ánimo de lucro (Decreto 092 de 2017)'
        if r['publica'] or 'INTERADMINISTRATIVO' in r['obj']: return 'Interadministrativo (otra entidad pública)'
        return 'Otro convenio'
    d['tipo_conv'] = None
    d.loc[conv | d.edu | d.delegada, 'tipo_conv'] = d[conv | d.edu | d.delegada].apply(tipo_conv, axis=1)

    # --- 6. indicios de fraccionamiento (solo entidades que contratan con la Ley 80: alcaldía, concejo, personería)
    d['umbral_min'] = d['anio'].map(lambda a: UMBRAL_MIN_SMMLV * SMMLV.get(a, SMMLV[2007]))
    d['umbral_menor'] = d['anio'].map(lambda a: UMBRAL_MENOR_SMMLV * SMMLV.get(a, SMMLV[2007]))
    # Servicios profesionales o de apoyo con persona natural: causal de contratación directa sin tope de valor (Ley 1150 de 2007, art. 2, num. 4, lit. h)
    directa_servicios = (d.modg == 'Contratación directa') & d.tipo.str.contains('PRESTACION DE SERVICIOS') & d.contratista_pub.str.startswith('Persona natural')
    F = d[d.ent.isin(['ALCALDIA', 'OTRO']) & d.cid.notna() & ~d.categoria.isin(['OPS / apoyo a la gestión', 'Convenios / interadministrativos'])
          & ~directa_servicios & ~d.modg.isin(['Licitación pública', 'Concurso de méritos']) & (d.valor < d.umbral_menor)].sort_values('fecha')
    fracc, d['fracc'] = [], False
    for cid, g in F.groupby('cid'):
        if len(g) < 2: continue
        rows = list(g.itertuples())
        usado = set()
        for a_i, a in enumerate(rows):
            if a.rid in usado: continue
            ka = kw(a.obj)
            grupo = [a]
            for b in rows[a_i + 1:]:
                if b.rid in usado: continue
                if (b.fecha - a.fecha).days > 30: break
                if (ka and jaccard(ka, kw(b.obj)) >= 0.5) or (not ka and a.obj[:80] == b.obj[:80]):
                    grupo.append(b)
            if len(grupo) < 2: continue
            tot = sum(x.valor for x in grupo)
            um_min, um_men = a.umbral_min, a.umbral_menor
            if all(x.valor < um_men for x in grupo) and tot > um_men:
                nivel, um = 'menor cuantía', um_men
            elif all(x.valor < um_min for x in grupo) and tot > um_min:
                nivel, um = 'mínima cuantía', um_min
            else:
                continue
            for x in grupo:
                usado.add(x.rid)
            d.loc[[x.rid for x in grupo], 'fracc'] = True
            fracc.append({'entidad': a.entidad, 'anio': int(a.anio), 'periodo': a.periodo, 'desde': str(a.fecha)[:10], 'hasta': str(grupo[-1].fecha)[:10],
                          'contratos': len(grupo), 'valor_total': r0(tot), 'mayor_contrato': r0(max(x.valor for x in grupo)),
                          'umbral_superado': nivel, 'umbral_valor': r0(um), 'veces_umbral': round(tot / um, 2),
                          'categoria': a.categoria, 'modalidades': sorted({x.modg for x in grupo}),
                          'contratista': a.contratista_pub, 'objeto': corto(a.objeto, 200), 'urls': [x.url for x in grupo][:6]})
    fracc.sort(key=lambda x: -x['valor_total'])

    # --- 6b. ajustes para data/comparativa/dinero_no_hecho.json (campos nuevos en "ajustes"; no cambian las cifras ya publicadas)
    d['dia'] = d.fecha.dt.date
    dup_ids = posibles_duplicados(d)
    dd = d.loc[sorted(dup_ids)]
    d['dup_copia'] = d.index.isin(dd[dd.duplicated(subset=['ent', 'dia', 'valor'], keep='first')].index)  # la segunda copia de cada grupo
    alc_m = d.ent.eq('ALCALDIA')
    d['subsidio_tarifas'] = d.obj.str.contains(SUBSIDIO_RE) & d.obj.str.contains(SUBSIDIO_CTX_RE) & ~d.obj.str.contains(SUBSIDIO_NO_RE)
    d['transf'] = alc_m & (d.interna | d.contratista_n.str.contains(TRANSF_EXTRA_RE) | (d.subsidio_tarifas & d.directa))
    d['transf_dest'] = None
    d.loc[d.transf, 'transf_dest'] = 'otras'
    d.loc[d.transf & d.contratista_n.str.contains(DEST_HOSP_RE), 'transf_dest'] = 'hospital'
    d.loc[d.transf & (d.contratista_n.str.contains(DEST_AGUAS_RE) | d.subsidio_tarifas), 'transf_dest'] = 'aguas'
    d['credito'] = d.obj.str.contains(CREDITO_RE)
    ops0 = d.categoria.eq('OPS / apoyo a la gestión')
    d['ops_reclas'] = ops0 & (d.transf | d.interna | d.subsidio_tarifas | d.obj.str.match(AUNAR_RE) | d.contratista_n.str.contains(INST_PUB_RE))
    d['ops_cat2'] = ops0 & ~d.ops_reclas
    d['ops_aj'] = d.ops_cat2 & ~d.dup_copia
    d['obra_fuera'] = d.numero_del_contrato.isin(list(OBRA_FUERA))
    mixto_todos = d.est_evaluado & (d.obj.str.contains('ADMINISTRACION DELEGADA') | (d.obj.str.contains(MIXTO) & ~d.obj.str.contains(PARA)))
    sim = d['est_sim_raw'].astype(float)
    d['est_sm_aj'] = d.est_sin_obra & ~d.est_mixto & ~d.obra_fuera                       # estudios sin obra, sin mixtos, ajustados
    d['est_sm_020'] = d.est_evaluado & (sim < 0.2) & ~mixto_todos & ~d.obra_fuera         # umbral de similitud más laxo (más obras halladas)
    d['est_sm_040'] = d.est_evaluado & (sim < 0.4) & ~mixto_todos & ~d.obra_fuera         # umbral más exigente
    d['est_plan'] = d.obj.str.contains(PLANES_RE)
    d['est_reciente'] = d.fecha >= pd.Timestamp(FECHA_RECIENTES)
    # base del sobrecosto: compras sin competencia de la alcaldía a terceros (sin OPS, sin estudios sin obra, sin transferencias a entidades
    # de Yondó ni operaciones de crédito) y procesos competitivos con un solo oferente con el mismo filtro
    d['base_sc'] = alc_m & d.directa & ~d.ops_cat2 & ~d.est_sm_aj & ~d.transf & ~d.credito
    d['base_uo'] = alc_m & d.un_oferente & ~d.directa & ~d.ops_cat2 & ~d.est_sm_aj & ~d.transf

    def ajustes(x):
        oa = x[x.ops_aj]; rc = x[x.ops_reclas]; od = x[x.ops_cat2 & x.dup_copia]
        sm = x[x.est_sm_aj]; of_ = x[x.obra_fuera & x.est_evaluado]
        tr = x[x.transf]
        bsc = x[x.base_sc]; buo = x[x.base_uo]
        return {
            'ops': {'n': len(oa), 'valor': r0(oa.valor.sum()), 'valor_sin_competencia': r0(oa[oa.directa].valor.sum()),
                    'formulacion_n': int(oa.ops_formulacion.sum()), 'formulacion_valor': r0(oa[oa.ops_formulacion].valor.sum()),
                    'reclasificadas_n': len(rc), 'reclasificadas_valor': r0(rc.valor.sum()), 'reclasificadas_transferencias_valor': r0(rc[rc.transf].valor.sum()),
                    'duplicados_n': len(od), 'duplicados_valor': r0(od.valor.sum())},
            'estudios': {'sin_obra_n': len(sm), 'sin_obra_valor': r0(sm.valor.sum()), 'sin_obra_valor_sin_competencia': r0(sm[sm.directa].valor.sum()),
                         'sin_obra_valor_un_oferente': r0(sm[sm.un_oferente].valor.sum()),
                         'umbral_020_valor': r0(x[x.est_sm_020].valor.sum()), 'umbral_040_valor': r0(x[x.est_sm_040].valor.sum()),
                         'planes_valor': r0(sm[sm.est_plan].valor.sum()), 'recientes_valor': r0(sm[sm.est_reciente].valor.sum()),
                         'central_valor': r0(sm[~sm.est_reciente].valor.sum()),
                         'minimo_valor': r0(x[x.est_sm_020 & ~x.est_plan & ~x.est_reciente].valor.sum()),
                         'maximo_valor': r0(max(x[x.est_sm_040].valor.sum(), sm.valor.sum())),
                         'obra_hallada_fuera_n': len(of_), 'obra_hallada_fuera_valor': r0(of_.valor.sum())},
            'subsidios_tarifas': {'n': int((tr.subsidio_tarifas).sum()), 'valor': r0(tr[tr.subsidio_tarifas].valor.sum())},
            'transferencias': {k: {'n': int((tr.transf_dest == k).sum()), 'valor': r0(tr[tr.transf_dest == k].valor.sum()),
                                   'sin_competencia_valor': r0(tr[(tr.transf_dest == k) & tr.directa].valor.sum()),
                                   'subsidios_valor': r0(tr[(tr.transf_dest == k) & tr.subsidio_tarifas].valor.sum()),
                                   'duplicados_valor': r0(tr[(tr.transf_dest == k) & tr.dup_copia].valor.sum())} for k in ('aguas', 'hospital', 'otras')},
            'base_sobrecosto': {'sin_competencia_valor': r0(bsc.valor.sum()), 'un_oferente_valor': r0(buo.valor.sum()),
                                'duplicados_valor': r0(bsc[bsc.dup_copia].valor.sum() + buo[buo.dup_copia].valor.sum()),
                                'credito_excluido_valor': r0(x[x.directa & x.credito & x.ent.eq('ALCALDIA')].valor.sum())},
            'propios_sin_competencia_sin_ops_valor': r0(x[x.directa & ~x.categoria.eq('OPS / apoyo a la gestión')].valor.sum()),
        }

    # --- 7. métricas por celda
    def bloque(x):
        v = x.valor.sum()
        sc = x[x.directa]; dr = x[x.modg == 'Contratación directa']; re_ = x[x.modg == 'Régimen especial']
        ops = x[x.categoria == 'OPS / apoyo a la gestión']; of = x[x.ops_formulacion]
        es = x[x.categoria == 'Estudios / consultoría']; ev = x[x.est_evaluado]; so = x[x.est_sin_obra]
        ob = x[x.categoria == 'Obra']; big = x[x.obra_big & (x.categoria == 'Obra')]; si = x[x.obra_sin_int & (x.categoria == 'Obra')]
        bigd = x[x.obra_big & (x.categoria != 'Obra')]; sid = x[x.obra_sin_int & (x.categoria != 'Obra')]; mx = x[x.est_mixto]
        cd = x[x.co_dato]; cu = x[x.co_uno]
        cv = x[x.tipo_conv.notna()]; dl = x[x.delegada]; ed = x[x.edu]
        ad = x[x.adic_dato]; adv = ad[ad.adic_valor > 0]; adt = ad[ad.adic_dias > 0]
        co = x[x.ofer_dato]; uo = x[x.un_oferente]; fr = x[x.fracc]; ti = x[x.interna]
        return {
            'contratos': len(x), 'valor': r0(v),
            'transferencias_internas': {'n': len(ti), 'valor': r0(ti.valor.sum())},
            'sin_competencia': {'n': len(sc), 'valor': r0(sc.valor.sum()), 'pct_valor': pct(sc.valor.sum(), v), 'pct_n': pct(len(sc), len(x))},
            'contratacion_directa': {'n': len(dr), 'valor': r0(dr.valor.sum()), 'pct_valor': pct(dr.valor.sum(), v)},
            'regimen_especial': {'n': len(re_), 'valor': r0(re_.valor.sum()), 'pct_valor': pct(re_.valor.sum(), v)},
            'ops': {'n': len(ops), 'valor': r0(ops.valor.sum()), 'formulacion_n': len(of), 'formulacion_valor': r0(of.valor.sum())},
            'estudios': {'n': len(es), 'valor': r0(es.valor.sum()), 'evaluados_n': len(ev), 'con_obra_n': int((ev.est_obra == True).sum()),  # noqa: E712
                         'sin_obra_n': len(so), 'sin_obra_valor': r0(so.valor.sum()), 'pct_valor_sin_obra': pct(so.valor.sum(), ev.valor.sum()),
                         'sin_obra_mixtos_n': len(mx), 'sin_obra_valor_sin_mixtos': r0(so.valor.sum() - mx.valor.sum())},
            'obras': {'n': len(ob), 'valor': r0(ob.valor.sum()), 'mayores_1000M_n': len(big), 'sin_interventoria_n': len(si), 'sin_interventoria_valor': r0(si.valor.sum()),
                      'delegada_obra_mayores_1000M_n': len(bigd), 'delegada_obra_sin_interventoria_n': len(sid), 'delegada_obra_sin_interventoria_valor': r0(sid.valor.sum())},
            'convenios': {'n': len(cv), 'valor': r0(cv.valor.sum()), 'adm_delegada_n': len(dl), 'adm_delegada_valor': r0(dl.valor.sum()),
                          'edu_n': len(ed), 'edu_valor': r0(ed.valor.sum())},
            'adiciones': {'contratos_con_dato': len(ad), 'pct_valor_con_dato': pct(ad.valor.sum(), v), 'con_adicion_valor_n': len(adv),
                          'valor_adicionado': r0(adv.adic_valor.sum()), 'pct_sobre_valor_inicial': pct(adv.adic_valor.sum(), ad.valor_inicial.sum()),
                          'con_prorroga_n': len(adt), 'dias_prorrogados': r0(adt.adic_dias.sum()),
                          'mas_del_50pct_n': int((ad.pct_adic > 50).sum()), 'mas_del_50pct_valor_adicionado': r0(ad[ad.pct_adic > 50].adic_valor.sum())},
            'un_oferente': {'procesos_competitivos_con_dato': len(co), 'un_oferente_n': len(uo), 'un_oferente_valor': r0(uo.valor.sum()),
                            'pct_n': pct(len(uo), len(co)), 'con_ofertas_con_dato': len(cd), 'con_ofertas_un_oferente_n': len(cu), 'con_ofertas_un_oferente_valor': r0(cu.valor.sum())},
            'fraccionamiento_indicios': {'contratos': len(fr), 'valor': r0(fr.valor.sum())},
            'ajustes': ajustes(x),
        }

    gob = {p['id']: p['alcalde'] for p in json.load(open(R / 'data' / 'gobiernos.json'))['periodos']}
    por_anio, por_periodo = [], []
    for a in sorted(d.anio.unique()):
        x = d[d.anio == a]
        por_anio.append({'anio': int(a), 'periodo': periodo(a), 'entidad': 'Todas', **bloque(x)})
        for e in ['ALCALDIA', 'AGUAS', 'HOSPITAL', 'OTRO']:
            y = x[x.ent == e]
            if len(y): por_anio.append({'anio': int(a), 'periodo': periodo(a), 'entidad': ENT_NOMBRE[e], **bloque(y)})

    # Concentración
    def concentracion(x):
        idf = x[x.cid.notna()]
        v = idf.valor.sum()
        g = idf.groupby('cid').agg(n=('valor', 'size'), valor=('valor', 'sum'), nombre=('contratista_pub', 'first'), publica=('publica', 'max')).sort_values('valor', ascending=False)
        sh = g.valor / v if v else g.valor * 0
        g2 = g[~g.publica]
        sh2 = g2.valor / g2.valor.sum() if len(g2) else g2.valor * 0
        return {'contratistas_distintos': int(len(g)), 'pct_valor_sin_contratista_identificado': pct(x.valor.sum() - v, x.valor.sum()),
                'top10_pct': round(100 * sh.head(10).sum(), 1) if v else None, 'hhi': r0((100 * sh).pow(2).sum()) if v else None,
                'hhi_sin_entidades_publicas': r0((100 * sh2).pow(2).sum()) if len(g2) else None,
                'top10': [{'contratista': r['nombre'], 'contratos': int(r['n']), 'valor': r0(r['valor']), 'pct': round(100 * r['valor'] / v, 1)} for _, r in g.head(10).iterrows()]}

    concent = []
    for p in [p for _, p in PERIODOS]:
        x = d[d.periodo == p]
        if not len(x): continue
        por_periodo.append({'periodo': p, 'alcalde': gob.get(p), 'entidad': 'Todas', **bloque(x)})
        for e in ['ALCALDIA', 'AGUAS', 'HOSPITAL', 'OTRO']:
            y = x[x.ent == e]
            if not len(y): continue
            c = concentracion(y)
            por_periodo.append({'periodo': p, 'alcalde': gob.get(p), 'entidad': ENT_NOMBRE[e], **bloque(y),
                                'concentracion': {k: c[k] for k in ['contratistas_distintos', 'top10_pct', 'hhi', 'hhi_sin_entidades_publicas', 'pct_valor_sin_contratista_identificado']}})
            concent.append({'periodo': p, 'entidad': ENT_NOMBRE[e], **c})

    # Estudios sin obra: 15 mayores
    so = d[d.est_sin_obra].sort_values('valor', ascending=False).head(15)
    estudios_top = [{'entidad': r['entidad'], 'anio': int(r['anio']), 'valor': r0(r['valor']), 'objeto': corto(r['objeto'], 300),
                     'contratista': r['contratista_pub'], 'similitud_maxima_con_una_obra': r['est_sim'],
                     'nota': ('El mismo contrato incluye obra (diseño y construcción). Que no aparezca una obra posterior no significa que no se construyó; hay que revisar las actas de recibo.'
                              if r['est_mixto'] else
                              ('Planes y ordenamiento territorial no llevan a una obra directa: se evalúan por su adopción y uso.'
                               if re.search(r'ORDENAMIENTO|\bEOT\b|PBOT|PLAN DE DESARROLLO|PLAN MAESTRO|PLAN PARCIAL', r['obj']) else None)),
                     'url': r['url']} for _, r in so.iterrows()]

    # Posibles registros duplicados: misma entidad, fecha de firma, valor (≥ $100 millones) y contratista, objeto parecido y distinto número
    # (calculados en el paso 6b con posibles_duplicados)

    # Convenios y delegada: lista
    conv_list = []
    cv = d[d.tipo_conv.notna() & ((d.valor >= 1e9) | d.delegada | d.edu)].sort_values('fecha')
    aguas_c = d[d.ent == 'AGUAS'].copy()
    aguas_c['kw'] = aguas_c['obj'].map(kw)
    for i, r in cv.iterrows():
        f1row = f1g.loc[r['numero_del_contrato']] if r['numero_del_contrato'] in f1g.index else None
        s2row = s2g.loc[r['numero_del_contrato']] if r['numero_del_contrato'] in s2g.index else None
        item = {'entidad': r['entidad'], 'anio': int(r['anio']), 'fecha': str(r['fecha'])[:10], 'valor': r0(r['valor']), 'tipo': r['tipo_conv'],
                'contratista': r['contratista_pub'], 'objeto': corto(r['objeto'], 260), 'fuente': r['origen'],
                'adicion_valor': (r0(r['adic_valor']) if r['adic_dato'] else None), 'prorroga_dias': (r0(r['adic_dias']) if r['adic_dato'] else None),
                'anticipo': (r0(s2row['valor_de_pago_adelantado']) if s2row is not None else None),
                'valor_pagado_secop2': (r0(s2row['valor_pagado']) if s2row is not None else None),
                'url': r['url']}
        if i in dup_ids:
            item['posible_registro_duplicado'] = True
        if item['anticipo'] is None:
            item['anticipo_nota'] = 'SECOP I no publica anticipos en datos abiertos; consta solo en el expediente.'
        # Contratos que Aguas y Aseo firmó después con objeto parecido (indicio de que el dinero se ejecutó por régimen especial)
        if re.search(r'AGUAS (?:Y|&) ASEO|EMPRESA DE SERVICIOS PUBLICOS', r['contratista_n']) and r['ent'] == 'ALCALDIA':
            k = kw(r['obj'])
            w = aguas_c[(aguas_c.fecha >= r['fecha']) & (aguas_c.fecha <= r['fecha'] + pd.Timedelta(days=180)) & (aguas_c.valor >= 0.05 * r['valor'])]
            der = []
            for _, x in w.iterrows():
                s = jaccard(k, x['kw'])
                if s >= 0.25:
                    der.append({'fecha': str(x['fecha'])[:10], 'valor': r0(x['valor']), 'modalidad': x['modg'], 'categoria': x['categoria'],
                                'contratista': x['contratista_pub'], 'objeto': corto(x['objeto'], 160), 'similitud': round(s, 2)})
            item['contratos_derivados_probables_aguas'] = sorted(der, key=lambda z: -z['valor'])[:5]
        conv_list.append(item)
    edu2 = []
    if (Path(D) / 'secop2_edu_yondo.json').exists():
        for r in json.load(open(f'{D}/secop2_edu_yondo.json')):
            edu2.append({'fecha': str(r.get('fecha_de_firma', ''))[:10], 'valor': r0(num(r.get('valor_del_contrato'))),
                         'modalidad': r.get('modalidad_de_contratacion'), 'contratista': publicar_nombre(r.get('proveedor_adjudicado'), r.get('tipodocproveedor')),
                         'objeto': corto(r.get('objeto_del_contrato'), 220), 'valor_pagado': r0(num(r.get('valor_pagado'))),
                         'anticipo': r0(num(r.get('valor_de_pago_adelantado'))), 'estado': r.get('estado_contrato')})

    resumen_conv = []
    for p in [p for _, p in PERIODOS]:
        x = d[(d.periodo == p) & d.tipo_conv.notna()]
        for t, g in x.groupby('tipo_conv'):
            resumen_conv.append({'periodo': p, 'tipo': t, 'n': len(g), 'valor': r0(g.valor.sum()),
                                 'por_entidad': {ENT_NOMBRE[e]: r0(v) for e, v in g.groupby('ent').valor.sum().items()}})

    # Adiciones: las 20 mayores y todas las que pasan del 50 % del valor inicial
    adx = d[d.adic_valor > 0]
    sel = pd.concat([adx.sort_values('adic_valor', ascending=False).head(20), adx[(adx.pct_adic > 50) & (adx.adic_valor >= 1e7)]])
    sel = sel[~sel.index.duplicated()].sort_values('adic_valor', ascending=False)
    adiciones_list = [{'entidad': r['entidad'], 'anio': int(r['anio']), 'valor_inicial': r0(r['base_adic']), 'valor_adicionado': r0(r['adic_valor']),
                       'pct_sobre_inicial': round(r['pct_adic'], 1), 'prorroga_dias': r0(r['adic_dias']), 'categoria': r['categoria'], 'modalidad': r['modg'],
                       'contratista': r['contratista_pub'], 'objeto': corto(r['objeto'], 200), 'fuente': ('SECOP I (f789-7hwg)' if r['origen'] == 'SECOPI' else 'SECOP II (versiones en rpmr-utcd)'),
                       'pasa_50pct': bool(r['pct_adic'] > 50), 'url': r['url']} for _, r in sel.iterrows()]

    # Listas para dinero_no_hecho.json
    def fila_est(r):
        return {'anio': int(r['anio']), 'fecha': str(r['fecha'])[:10], 'valor': r0(r['valor']), 'objeto': corto(r['objeto'], 220),
                'contratista': r['contratista_pub'], 'modalidad': r['modg'], 'sin_competencia': bool(r['directa']), 'un_oferente': bool(r['un_oferente']),
                'similitud_maxima_con_una_obra': r['est_sim'], 'plan': bool(r['est_plan']), 'reciente': bool(r['est_reciente']), 'url': r['url']}
    est_aj_list = [fila_est(r) for _, r in d[d.est_sm_aj & alc_m].sort_values(['anio', 'valor'], ascending=[True, False]).iterrows()]
    est_fuera_list = [{**fila_est(r), 'motivo': OBRA_FUERA[r['numero_del_contrato']][0], 'etiqueta': OBRA_FUERA[r['numero_del_contrato']][1], 'evidencia': OBRA_FUERA[r['numero_del_contrato']][2]}
                      for _, r in d[d.obra_fuera & d.est_evaluado].sort_values('anio').iterrows()]
    rc = d[d.ops_reclas & alc_m].sort_values('valor', ascending=False)
    ops_rec_list = [{'anio': int(r['anio']), 'valor': r0(r['valor']), 'contratista': r['contratista_pub'],
                     'motivo': ('subsidio a tarifas de servicios públicos' if r['subsidio_tarifas'] else
                                'transferencia a otra entidad de Yondó' if r['transf'] else
                                'convenio para aunar esfuerzos' if re.match(AUNAR_RE, r['obj']) else 'contrato con otra entidad pública'),
                     'objeto': corto(r['objeto'], 160), 'url': r['url']} for _, r in rc.iterrows()]
    dup_list = []
    for (e, dia, v), g in d.loc[sorted(dup_ids)].groupby(['ent', 'dia', 'valor']):
        dup_list.append({'entidad': ENT_NOMBRE[e], 'anio': int(g.anio.iloc[0]), 'fecha': str(dia), 'valor': r0(v), 'registros': len(g),
                         'categoria': g.categoria.iloc[0], 'transferencia_interna': bool(g.transf.any()), 'sin_competencia': bool(g.directa.all()),
                         'contratista': g.contratista_pub.iloc[0], 'numeros': sorted(g.numero_del_contrato.astype(str)), 'objeto': corto(g.objeto.iloc[0], 160)})

    # --- 8. verificación frente a las cifras publicadas
    alc = d[(d.ent == 'ALCALDIA') & (d.anio >= 2008)]
    a20 = alc[alc.anio >= 2020]
    est_alc = d[(d.ent == 'ALCALDIA') & d.est_evaluado]
    edu = d[d.edu]
    ver = {
        'contratacion_alcaldia_2008_2026': {'publicado': 703.8e9, 'calculado': r0(alc.valor.sum())},
        'pct_valor_sin_competencia_alcaldia_2020_2026': {'publicado': 83, 'calculado': pct(a20[a20.directa].valor.sum(), a20.valor.sum())},
        'ops_alcaldia_2008_2026': {'publicado': 5580, 'calculado': int((alc.categoria == 'OPS / apoyo a la gestión').sum())},
        'edu_medellin': {'publicado': {'n': 5, 'valor': 84.0e9}, 'calculado': {'n': len(edu), 'valor': r0(edu.valor.sum())}},
        'estudios_alcaldia': {'publicado': {'n': 124, 'valor': 24.4e9, 'con_obra': 27}, 'calculado': {'n': len(est_alc), 'valor': r0(est_alc.valor.sum()), 'con_obra': int((est_alc.est_obra == True).sum())}},  # noqa: E712
        'ops_formulacion_alcaldia': {'publicado': {'n': 425, 'valor': 10.5e9}, 'calculado': {'n': int(alc.ops_formulacion.sum()), 'valor': r0(alc[alc.ops_formulacion].valor.sum())}},
        'registros': {'brutos': n0, 'depurados': len(d)},
    }
    ok = (abs(ver['contratacion_alcaldia_2008_2026']['calculado'] / 1e9 - 703.8) < 0.05 and round(ver['pct_valor_sin_competencia_alcaldia_2020_2026']['calculado']) == 83
          and ver['ops_alcaldia_2008_2026']['calculado'] == 5580 and len(edu) == 5 and len(est_alc) == 124 and ver['estudios_alcaldia']['calculado']['con_obra'] == 27
          and ver['ops_formulacion_alcaldia']['calculado']['n'] == 425)
    ver['reproduce_cifras_publicadas'] = bool(ok)
    ver['nota'] = ('Las 124 consultorías de la cifra publicada incluyen 2007 y quitan repetidos (mismo año, valor y objeto); por eso no coinciden con la suma de la '
                   'categoría "Estudios / consultoría" de las tablas por periodo (125 contratos y $25.569 millones en 2008–2026).')

    # --- 9. calidad de datos
    est_dudoso = d[d['estado_del_proceso'].fillna('').str.contains('Convocado|Borrador|Cancelado|Descartado|Anormalmente', case=False)]
    dup = d.loc[sorted(dup_ids)]
    dup_exceso = dup[dup.duplicated(subset=['ent', 'dia', 'valor'], keep='first')]
    npa = d.groupby('anio').size().to_dict()
    cobertura = [{'anio': int(a), **{ENT_NOMBRE[e]: int(((d.anio == a) & (d.ent == e)).sum()) for e in ['ALCALDIA', 'AGUAS', 'HOSPITAL', 'OTRO']}} for a in sorted(d.anio.unique())]
    umbral_check = []
    for a, g in d[(d.ent == 'ALCALDIA') & d['mod'].str.contains('MINIMA')].groupby('anio'):
        umbral_check.append({'anio': int(a), 'mayor_contrato_minima_cuantia': r0(g.valor.max()), 'en_smmlv': round(g.valor.max() / SMMLV[int(a)], 1),
                             'umbral_usado': r0(UMBRAL_MIN_SMMLV * SMMLV[int(a)])})

    out = {
        'titulo': 'Fugas posibles en la contratación pública de Yondó, por año, gobierno y entidad (SECOP)',
        'generado': date.today().isoformat(),
        'fuente': {
            'principal': 'SECOP Integrado (datos.gov.co, conjunto rpmr-utcd; une SECOP I y SECOP II). Filtro: municipio de la entidad = Yondó o nombre de la entidad contiene "YOND".',
            'complementarias': [
                'SECOP I – Procesos de compra pública (f789-7hwg): adiciones en valor y en tiempo. Para Yondó solo trae contratos firmados desde 2017.',
                'SECOP II – Contratos electrónicos (jbjy-vk9h): días adicionados, valor pagado, valor facturado y anticipo (pago adelantado).',
                'SECOP II – Procesos de contratación (p6dx-8zbt): número de proveedores que presentaron oferta.',
                'SECOP II – Adiciones (cb9c-h8sn) y Modificaciones (u8cx-r425): descargadas como respaldo; no se usan en los cálculos (ver limitaciones).',
                'SECOP II – Contratos de la EDU de Medellín con objeto en Yondó (jbjy-vk9h).',
                'data/gobiernos.json: alcalde de cada periodo.'],
            'descarga': ('python3 scripts/fugas_secop.py --descargar (por páginas; guarda en data/secop/raw/, que no se sube al repositorio). '
                         'scripts/descargar_secop.sh pide las 14.301 filas en un solo bloque y el 21 de octubre de 2026 la transferencia se cortó (error 18 de curl); '
                         'la descarga por páginas usa el mismo filtro y trae las mismas 14.301 filas.'),
            'fecha_descarga': '2026-10-21',
            'registros': {'brutos': n0, 'depurados': len(d), 'excluidos_por_valor_anomalo': len(outliers)},
        },
        'metodo': {
            'que_es_una_fuga': ('Aquí "fuga" es un punto donde el dinero público queda expuesto a perder valor o control: se contrata sin competencia, se paga un '
                                'estudio que no llega a obra, una obra grande no tiene interventoría visible, el contrato crece con adiciones, se presenta un solo '
                                'oferente, la ejecución se delega a otra entidad, unos pocos contratistas concentran el dinero o un contrato se divide para no '
                                'pasar un umbral. No son pérdidas comprobadas y no se deben sumar entre sí: un mismo contrato puede aparecer en varias.'),
            'niveles_de_certeza': {
                'hecho': 'Valor, fecha, modalidad, entidad y contratista tal como están registrados en SECOP (con enlace al contrato).',
                'estimado': 'Clasificación por categoría (función cat), OPS de formulación, adiciones y concentración: cálculos sobre los registros con reglas explícitas.',
                'indicio': 'Estudios sin obra posterior, obras sin interventoría identificable, contratos derivados probables e indicios de fraccionamiento: coincidencias de texto y fechas que hay que verificar en el expediente.'},
            'limpieza': 'Igual que scripts/secop_analisis.py: se quitan registros sin fecha de firma o sin valor, un valor anómalo (> $60.000 millones) y repetidos (SECOP I: mismo número y valor; SECOP II: se conserva la versión de mayor valor).',
            'entidades': 'Alcaldía (incluye "MUNICIPIO DE YONDO" en SECOP II), Aguas y Aseo (también la antigua Empresa de Servicios Públicos de Acueducto, Alcantarillado y Aseo), Hospital (E.S.E. Héctor Abad Gómez) y Otras (Concejo, Personería, Fondo Ganadero, una institución educativa).',
            'sin_competencia': 'Modalidad que contiene "directa", "régimen especial" o "Decreto 092" (misma definición de la cifra publicada del 83 %). "contratacion_directa" cuenta solo la modalidad de contratación directa; "regimen_especial" la de régimen especial (propia de Aguas y Aseo y del hospital, y de los convenios con entidades sin ánimo de lucro). En Aguas y Aseo y el hospital el 100 % "sin competencia" refleja su régimen legal (derecho privado y manual propio), no una decisión de cada contrato.',
            'ops': 'Categoría "OPS / apoyo a la gestión" de la función cat(); OPS de formulación: objeto que menciona formulación, MGA, banco de proyectos, estructuración, proyectos de inversión o planeación.',
            'estudios_sin_obra': 'Para cada estudio, diseño o consultoría (sin repetidos de mismo año, valor y objeto) se busca una obra firmada el mismo año o después y se mide la similitud de Jaccard entre las palabras significativas de los objetos. Similitud ≥ 0,30 = obra relacionada probable. Para la alcaldía se usa la lógica publicada (solo obras de la alcaldía); para Aguas y Aseo y el hospital se buscan obras de la alcaldía, Aguas y Aseo y el hospital. "sin_obra_valor_sin_mixtos" descuenta los contratos que incluyen diseño y construcción en el mismo objeto (como el de $11.696 millones con la EDU), donde la obra va dentro del contrato.',
            'obras_sin_interventoria': 'Contratos de obra (o de administración delegada para obra) de más de $1.000 millones. Se buscan contratos de interventoría firmados entre 120 días antes y 365 días después, con el mismo código de proyecto o con al menos la mitad de las palabras significativas del objeto de la obra. Si el propio objeto de la obra incluye la interventoría, no se marca. En los bloques por año y periodo, "sin_interventoria_*" cuenta contratos de obra y "delegada_obra_sin_interventoria_*" los convenios de administración delegada para obra (cuya interventoría suele contratarla la entidad delegada).',
            'adiciones': 'SECOP I: valor total de adiciones y tiempo adicionado (días + 30 × meses) del conjunto f789-7hwg, unido por número de constancia (hecho registrado). SECOP II: adición en valor = valor mayor menos valor menor entre las versiones del contrato en SECOP Integrado (estimado); prórroga = días adicionados (jbjy-vk9h). "pct_valor_con_dato" dice qué parte del valor tiene esa información. "mas_del_50pct" cuenta contratos cuya adición supera la mitad del valor inicial.',
            'un_oferente': 'Procesos competitivos de SECOP II (mínima cuantía, selección abreviada, licitación o concurso de méritos) en los que solo un proveedor presentó oferta (campo proveedores_unicos_con). Aparte ("con_ofertas_...") se cuentan las contrataciones directas o de régimen especial "con ofertas", donde una sola oferta es lo esperable. SECOP I no publica el número de oferentes en datos abiertos.',
            'convenios': 'Contratos de la categoría "Convenios / interadministrativos", más los de la EDU de Medellín y los de administración delegada aunque cat() los ponga en otra categoría (por ejemplo, el de $11.696 millones con la EDU, que cat() clasifica como estudios por incluir diseños). Tipos: administración delegada, interadministrativo con la EDU, con otra entidad pública, con entidad sin ánimo de lucro (Decreto 092 de 2017) y otros.',
            'concentracion': 'Participación de los 10 mayores contratistas en el valor con contratista identificado e índice de Herfindahl-Hirschman (HHI = suma de los cuadrados de las participaciones en %, de 0 a 10.000; como referencia, más de 1.500 indica concentración moderada y más de 2.500, alta, según las guías de competencia de EE. UU. de 2010). Se identifica al contratista por su documento (NIT sin dígito de verificación) o, si falta, por su nombre. "hhi_sin_entidades_publicas" quita a la EDU, Aguas y Aseo, el hospital y otras entidades públicas.',
            'fraccionamiento': f'Contratos de la alcaldía, el concejo y la personería (no se aplica a Aguas y Aseo ni al hospital, que tienen régimen especial y umbrales propios), sin OPS, sin prestación de servicios con persona natural por contratación directa y sin convenios (todos se pueden contratar directamente sin importar el valor), y sin licitaciones ni concursos. Se agrupan los del mismo contratista con objeto parecido (Jaccard ≥ 0,50) firmados dentro de 30 días después del primero. Es indicio si cada contrato queda por debajo del umbral y la suma lo supera. Umbrales: mínima cuantía = {UMBRAL_MIN_SMMLV} salarios mínimos; menor cuantía = {UMBRAL_MENOR_SMMLV} salarios mínimos (Ley 1150 de 2007, art. 2, y Ley 1474 de 2011, art. 94). El valor de {UMBRAL_MIN_SMMLV} salarios sale de los datos: el mayor contrato de mínima cuantía de la alcaldía cada año ronda ese valor (ver "umbral_minima_cuantia_verificacion").',
            'transferencias_internas': 'Contratos cuyo contratista es otra entidad de Yondó (sobre todo la alcaldía con Aguas y Aseo o con el hospital). En las filas "Todas" ese dinero cuenta dos veces: una cuando la alcaldía lo transfiere y otra cuando la empresa o el hospital lo contrata. Para un total sin doble conteo, reste "transferencias_internas.valor".',
            'valores': 'Pesos corrientes de cada año, sin deflactar.',
            'personas': 'No se publican nombres ni documentos de personas naturales contratistas. Se nombra al contratista cuando el nombre trae una forma jurídica o de entidad (S.A.S., Ltda., E.S.P., fundación, asociación, consorcio, unión temporal, municipio, etc.) o cuando SECOP lo registra con NIT de persona jurídica y el nombre es una sigla o una razón social evidente. Se quita lo que va entre paréntesis. En la duda, el nombre no se publica.',
        },
        'limitaciones': [
            (f'SECOP casi no tiene datos de Yondó antes de 2011: {npa.get(2007, 0)} contratos en 2007 (ninguno de 2004–2006) y entre {min(npa.get(a, 0) for a in range(2008, 2012))} y '
             f'{max(npa.get(a, 0) for a in range(2008, 2012))} por año en 2008–2011, frente a {min(npa.get(a, 0) for a in range(2012, 2026))} o más por año en 2012–2025 '
             f'(2026 va hasta octubre: {npa.get(2026, 0)}). El periodo 2004–2007 no se puede auditar con estos datos y 2008–2011 está subregistrado.'),
            'Aguas y Aseo no publicó contratos antes de 2014 (salvo uno en 2011) y casi nada después de 2022; el hospital solo publicó en 2013–2014 y desde 2021. Los vacíos no significan que no hubo contratos.',
            'Las adiciones solo constan para los contratos de SECOP I firmados desde 2017 (conjunto f789-7hwg) y para SECOP II. Para 2008–2016 no hay dato abierto de adiciones: un cero ahí es "sin dato", no "sin adiciones". Ver "pct_valor_con_dato".',
            'En SECOP I el valor publicado es el inicial (sin adiciones); en SECOP II es el de la última versión (con adiciones). Las cifras de valor total heredan esta diferencia del análisis publicado.',
            'Anticipos: SECOP II tiene el campo de pago adelantado, pero vale cero en todos los contratos de Yondó; SECOP I no lo publica. Los anticipos de los convenios con la EDU (SECOP I) solo constan en el expediente.',
            'El número de oferentes solo existe para procesos de SECOP II (la mayoría de 2023 en adelante).',
            'Los conjuntos de Adiciones (cb9c-h8sn) y Modificaciones (u8cx-r425) de SECOP II no se usan: el campo valor_modificacion repite el valor total del contrato en cada versión (no la diferencia) y la mayoría de registros están "en edición" o sin tipo.',
            'Las coincidencias por palabras del objeto producen falsos negativos (una obra o interventoría registrada con otras palabras, o contratada por otra entidad como la Gobernación, Findeter, Ecopetrol o la EDU) y algunos falsos positivos. Por eso son indicios y agenda de verificación.',
            'La clasificación depende de cómo cada entidad redactó el objeto y eligió el tipo de contrato. Los errores de registro de SECOP se heredan.',
            f'Se conservan, como en el análisis publicado, {len(est_dudoso)} registros con fecha de firma cuyo estado en SECOP es "convocado" (u otro que no confirma un contrato firmado) (${miles(est_dudoso.valor.sum() / 1e6)} millones).',
            f'Hay {len(dup)} registros de $100 millones o más que coinciden con otro en entidad, fecha de firma, valor exacto, contratista y objeto, pero tienen distinto número de contrato: parecen el mismo contrato registrado dos veces. Si lo son, el valor contado de más es ${miles(dup_exceso.valor.sum() / 1e6)} millones ({len(dup_exceso)} registros). Se dejan como en el análisis publicado para no cambiar las cifras ya divulgadas y se marcan con "posible_registro_duplicado" en la lista de convenios.',
            'El salario mínimo de 2026 ($1.750.905) se usa para el umbral de ese año.',
        ],
        'verificacion': ver,
        'cobertura_contratos_por_anio': cobertura,
        'umbral_minima_cuantia_verificacion': umbral_check,
        'resumen_alcaldia_por_periodo': [
            {'periodo': p['periodo'], 'alcalde': p['alcalde'], 'valor': p['valor'], 'pct_sin_competencia': p['sin_competencia']['pct_valor'],
             'ops_n': p['ops']['n'], 'ops_formulacion_n': p['ops']['formulacion_n'], 'estudios_sin_obra_valor': p['estudios']['sin_obra_valor'],
             'estudios_sin_obra_valor_sin_mixtos': p['estudios']['sin_obra_valor_sin_mixtos'], 'obras_sin_interventoria_valor': p['obras']['sin_interventoria_valor'],
             'delegada_obra_sin_interventoria_valor': p['obras']['delegada_obra_sin_interventoria_valor'], 'un_oferente_n': p['un_oferente']['un_oferente_n'],
             'competitivos_con_dato_oferentes': p['un_oferente']['procesos_competitivos_con_dato'],
             'adm_delegada_valor': p['convenios']['adm_delegada_valor'], 'top10_pct': p['concentracion']['top10_pct'], 'hhi': p['concentracion']['hhi'],
             'valor_adicionado': p['adiciones']['valor_adicionado'], 'pct_valor_con_dato_adiciones': p['adiciones']['pct_valor_con_dato'],
             'fraccionamiento_valor': p['fraccionamiento_indicios']['valor']}
            for p in por_periodo if p['entidad'] == 'Alcaldía'],
        'por_anio': por_anio,
        'por_periodo': por_periodo,
        'estudios_sin_obra_top': estudios_top,
        'obras_sin_interventoria': obras_sin_int,
        'obras_sin_interventoria_resumen': {'obras_mayores_1000M': n_obra_big, 'con_interventoria_identificada_o_incluida': n_obra_big_con, 'sin_interventoria_identificable': len(obras_sin_int),
                                            'valor_sin_interventoria': r0(sum(x['valor'] for x in obras_sin_int))},
        'adiciones_mayores': {'nota': ('Ley 80 de 1993, art. 40, parágrafo: un contrato no puede adicionarse en más del 50 % de su valor inicial, medido en salarios mínimos. '
                                       'Aplica a la alcaldía y demás entidades de la Ley 80; Aguas y Aseo y el hospital tienen régimen especial. Como el tope se mide en salarios '
                                       'mínimos, una adición hecha en un año posterior puede pasar del 50 % en pesos y no en salarios. Es un indicio para revisar, no una conclusión.'),
                              'contratos': adiciones_list},
        'concentracion': concent,
        'fraccionamiento_indicios': fracc,
        'fraccionamiento_resumen': {'grupos': len(fracc), 'contratos': int(sum(x['contratos'] for x in fracc)), 'valor': r0(sum(x['valor_total'] for x in fracc)),
                                    'por_periodo': {p: {'grupos': sum(1 for x in fracc if x['periodo'] == p), 'valor': r0(sum(x['valor_total'] for x in fracc if x['periodo'] == p))} for _, p in PERIODOS}},
        'convenios_delegada': conv_list,
        'convenios_resumen_por_periodo': resumen_conv,
        'edu_contratos_derivados_secop2': {'nota': 'Contratos que la propia EDU de Medellín publicó en SECOP II con objeto en Yondó. Los contratos derivados de 2021–2023 no aparecen con "Yondó" en el objeto; hay que pedirlos a la EDU.', 'contratos': edu2},
        'ajustes_dinero_no_hecho': {
            'nota': ('Campos que usa scripts/build_dinero_no_hecho.py. No cambian las cifras ya publicadas (5.580 OPS, 124 estudios, 27 con obra, 83 %): '
                     'las corrigen solo para ese cálculo. En cada bloque por año y periodo están en "ajustes".'),
            'metodo': {
                'ops': ('OPS de cat() sin los contratos que no son prestación de servicios de personas o empresas: transferencias a Aguas y Aseo, al hospital '
                        'u otra entidad de Yondó (también con grafías mal digitadas), subsidios a las tarifas, objetos que empiezan por "aunar esfuerzos" y '
                        'contratos con universidades u otras instituciones públicas. Además se quita la segunda copia de cada posible registro duplicado.'),
                'estudios': ('Estudios sin obra posterior hallada en el SECOP de la alcaldía (regla de similitud ≥ 0,30), sin contratos mixtos y sin los '
                             'estudios cuya obra consta fuera de ese SECOP (lista "estudios_obra_hallada_fuera"). Sensibilidad: umbral de similitud 0,20 '
                             '(más obras halladas) y 0,40 (menos). "planes" = planes de ordenamiento, parciales, de desarrollo o de gestión del riesgo. '
                             f'"recientes" = firmados desde el {FECHA_RECIENTES} (18 meses antes del corte): su obra todavía puede no haberse firmado.'),
                'transferencias': ('Contratos de la alcaldía con Aguas y Aseo, el hospital u otra entidad de Yondó, y subsidios a tarifas aunque el contratista '
                                   'esté mal registrado. "subsidios_valor": Fondo de Solidaridad y Redistribución del Ingreso, identificados por el objeto completo.'),
                'base_sobrecosto': ('Valor sin competencia de la alcaldía sin OPS, sin estudios sin obra, sin transferencias a entidades de Yondó y sin '
                                    'operaciones de crédito (empréstitos), más los procesos competitivos con un solo oferente con el mismo filtro. '
                                    '"duplicados_valor" = segunda copia de posibles duplicados dentro de esa base.'),
                'propios_sin_competencia_sin_ops_valor': 'Para Aguas y Aseo y el hospital: lo que contrataron sin competencia, sin OPS (sirve para acotar el sobrecosto de lo que la alcaldía les transfiere).',
            },
            'estudios_sin_obra_alcaldia': est_aj_list,
            'estudios_obra_hallada_fuera': est_fuera_list,
            'ops_reclasificadas_alcaldia': ops_rec_list,
            'posibles_duplicados': dup_list,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(OUT, 'w'), ensure_ascii=False, indent=1)
    return out


def imprimir(out):
    print('Verificación:', json.dumps(out['verificacion'], ensure_ascii=False, default=str)[:900])
    print(f"{'periodo':10} {'valor M':>9} {'%sinC':>6} {'OPS':>5} {'estSinObra M':>12} {'obraSinInt M':>12} {'delegada M':>10} {'top10%':>6} {'HHI':>5} {'adic M':>7} {'%dato':>6} {'fracc M':>7} {'deleg s/int M':>13} {'est s/mixt M':>12} {'1 oferente':>10}")
    for p in out['resumen_alcaldia_por_periodo']:
        print(f"{p['periodo']:10} {p['valor'] / 1e6:9,.0f} {p['pct_sin_competencia'] or 0:6.1f} {p['ops_n']:5d} {p['estudios_sin_obra_valor'] / 1e6:12,.0f} "
              f"{p['obras_sin_interventoria_valor'] / 1e6:12,.0f} {p['adm_delegada_valor'] / 1e6:10,.0f} {p['top10_pct'] or 0:6.1f} {p['hhi'] or 0:5d} "
              f"{p['valor_adicionado'] / 1e6:7,.0f} {p['pct_valor_con_dato_adiciones'] or 0:6.1f} {p['fraccionamiento_valor'] / 1e6:7,.0f} "
              f"{p['delegada_obra_sin_interventoria_valor'] / 1e6:13,.0f} {p['estudios_sin_obra_valor_sin_mixtos'] / 1e6:12,.0f} {p['un_oferente_n']:>4d}/{p['competitivos_con_dato_oferentes']:<5d}")
    print('obras sin interventoría:', out['obras_sin_interventoria_resumen'])
    print('fraccionamiento:', out['fraccionamiento_resumen'])


if __name__ == '__main__':
    if '--descargar' in sys.argv:
        descargar()
    else:
        imprimir(main())
