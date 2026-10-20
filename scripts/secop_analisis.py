import json, re, sys, unicodedata
import pandas as pd
D = sys.argv[1]
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
def norm(s):
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode().upper()
    return re.sub(r'\s+', ' ', s)
d['obj'] = d['objeto_a_contratar'].fillna('').map(norm)
d['tipo'] = d['tipo_de_contrato'].fillna('').map(norm)
d['mod'] = d['modalidad_de_contrataci_n'].fillna('').map(norm)
d['contratista_n'] = d['nom_raz_social_contratista'].fillna('').map(norm)
d['natural'] = d['tipo_documento_proveedor'].fillna('').str.contains('dula', case=False)
n0 = len(d)
d = d[d['anio'].notna() & d['valor'].notna() & (d['valor'] > 0)]
# Errores de digitación evidentes: contratos > 60.000 millones (el mayor contrato real verificable es ~50.565 millones)
outliers = d[d['valor'] > 6e10]
d = d[d['valor'] <= 6e10]
# Duplicados: mismo numero_del_contrato o (entidad, fecha, valor, objeto)
# Duplicados: SECOP I repite filas por contratista/estado; SECOP II repite el contrato por cada modificación (se conserva el mayor valor)
s1 = d[d.origen == 'SECOPI'].drop_duplicates(subset=['ent', 'numero_del_contrato', 'valor'])
s2 = d[d.origen == 'SECOPII'].sort_values('valor').drop_duplicates(subset=['ent', 'numero_del_contrato'], keep='last')
d = pd.concat([s1, s2])
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
d['categoria'] = d.apply(cat, axis=1)
# OPS cuyo objeto es formular/estructurar proyectos (el "ciclo MGA")
d['ops_formulacion'] = (d['categoria'] == 'OPS / apoyo a la gestión') & d['obj'].str.contains(r'FORMULACI|\bMGA\b|BANCO DE PROYECTOS|ESTRUCTURACI|GESTION DE PROYECTOS|PROYECTOS DE INVERSION|SECRETARIA DE PLANEACION|PLANEACION')
def periodo(a):
    a = int(a)
    for i, p in [(2004, '2004-2007'), (2008, '2008-2011'), (2012, '2012-2015'), (2016, '2016-2019'), (2020, '2020-2023'), (2024, '2024-2027')]:
        if i <= a <= i + 3: return p
d['periodo'] = d['anio'].map(periodo)
out = {'fuente': 'SECOP Integrado (datos.gov.co, dataset rpmr-utcd), descargado 2026-10-20',
       'registros_brutos': n0, 'registros_limpios': len(d),
       'outliers_excluidos': outliers[['nombre_de_la_entidad', 'anio', 'valor', 'objeto_a_contratar']].fillna('').astype(str).to_dict('records')}
# Serie anual por entidad y categoría
g = d.groupby(['ent', 'anio', 'categoria']).agg(n=('valor', 'size'), valor=('valor', 'sum')).reset_index()
out['anual'] = g.to_dict('records')
p = d.groupby(['ent', 'periodo', 'categoria']).agg(n=('valor', 'size'), valor=('valor', 'sum')).reset_index()
out['por_periodo'] = p.to_dict('records')
f = d[d.ops_formulacion].groupby(['ent', 'periodo']).agg(n=('valor', 'size'), valor=('valor', 'sum')).reset_index()
out['ops_formulacion'] = f.to_dict('records')
nat = d[d.categoria == 'OPS / apoyo a la gestión'].groupby(['ent', 'anio']).agg(n=('valor', 'size'), valor=('valor', 'sum'), personas=('documento_proveedor', 'nunique')).reset_index()
out['ops_anual'] = nat.to_dict('records')
# Estudios / consultorías: buscar si existe obra posterior relacionada (indicio por palabras clave)
STOP = set('DE LA EL LOS LAS DEL Y EN PARA POR CON A AL SE QUE O U MUNICIPIO YONDO ANTIOQUIA ESTUDIOS ESTUDIO DISENOS DISENO TECNICOS TECNICO CONSTRUCCION MEJORAMIENTO REALIZAR ELABORACION ELABORAR CONSULTORIA PROYECTO PROYECTOS FASE II III I SU DETALLADOS DETALLE ADECUACION OBRAS OBRA REALIZACION SERVICIOS PRESTACION CONTRATAR CONTRATACION MUNICIPAL URBANA RURAL ZONA SECTOR'.split())
def kw(o): return {w for w in re.findall(r'[A-Z]{4,}', o) if w not in STOP}
obras = d[(d.categoria == 'Obra') & (d.ent == 'ALCALDIA') & ~d.obj.str.contains(r'PRESTACION DE SERVICIOS|APOYO A LA GESTION|^ACCIONES PARA')][['anio', 'obj', 'valor', 'estado_del_proceso']].copy()
obras['kw'] = obras['obj'].map(kw)
est = d[(d.categoria == 'Estudios / consultoría') & (d.ent == 'ALCALDIA')].copy()
est = est.drop_duplicates(subset=['anio', 'valor', 'obj'])
rows = []
for _, r in est.iterrows():
    k = kw(r['obj']); best = None; bs = 0
    for _, o in obras[obras.anio >= r['anio']].iterrows():
        if not k or not o['kw']: continue
        s = len(k & o['kw']) / len(k | o['kw'])
        if s > bs: bs, best = s, o
    rows.append({'anio': int(r['anio']), 'periodo': r['periodo'], 'valor': float(r['valor']), 'objeto': r['objeto_a_contratar'][:300],
                 'contratista_tipo': 'Persona natural' if r['natural'] else 'Persona jurídica',
                 'obra_relacionada_probable': (best['obj'][:200] if best is not None and bs >= 0.3 else None),
                 'anio_obra': (int(best['anio']) if best is not None and bs >= 0.3 else None),
                 'estado_obra': (best['estado_del_proceso'] if best is not None and bs >= 0.3 else None),
                 'similitud': round(bs, 2), 'url': r.get('url_contrato')})
out['estudios'] = rows
# Top contratistas personas jurídicas (alcaldía)
pj = d[(d.ent == 'ALCALDIA') & (~d.natural)].groupby('nom_raz_social_contratista').agg(n=('valor', 'size'), valor=('valor', 'sum'), desde=('anio', 'min'), hasta=('anio', 'max')).sort_values('valor', ascending=False).head(20).reset_index()
out['top_juridicas_alcaldia'] = pj.to_dict('records')
# Concentración: % del valor en contratación directa por periodo
d['directa'] = d['mod'].str.contains('DIRECTA|REGIMEN ESPECIAL|DECRETO 092')
c = d[d.ent == 'ALCALDIA'].groupby('periodo').apply(lambda x: pd.Series({'n': len(x), 'valor': x.valor.sum(), 'pct_valor_directa': round(100 * x[x.directa].valor.sum() / x.valor.sum(), 1), 'pct_n_directa': round(100 * x.directa.mean(), 1)})).reset_index()
out['directa_por_periodo'] = c.to_dict('records')
# Contratos de mayor valor por celda (entidad, periodo, categoría). Las personas naturales no se nombran.
tops = []
for (e, per, ca), x in d.groupby(['ent', 'periodo', 'categoria']):
    for _, r in x.sort_values('valor', ascending=False).head(3).iterrows():
        tops.append({'ent': e, 'periodo': per, 'categoria': ca, 'anio': int(r['anio']), 'valor': float(r['valor']),
                     'objeto': str(r['objeto_a_contratar'])[:220],
                     'contratista': 'Persona natural' if r['natural'] else str(r['nom_raz_social_contratista'])[:80],
                     'url': r.get('url_contrato')})
out['top_celdas'] = tops
# Contratos con la Empresa de Desarrollo Urbano de Medellín (EDU), excluida la EDU de La Ceja
edu = d[(d.ent == 'ALCALDIA') & d['nom_raz_social_contratista'].fillna('').str.upper().str.contains('DESARROLLO URBANO') & ~d['nom_raz_social_contratista'].fillna('').str.upper().str.contains('CEJA')]
out['edu'] = [{'fecha': str(r['fecha'])[:10], 'valor': float(r['valor']), 'objeto': str(r['objeto_a_contratar'])[:300], 'url': r.get('url_contrato')} for _, r in edu.sort_values('fecha').iterrows()]
json.dump(out, open(f'{D}/secop_resumen.json', 'w'), ensure_ascii=False, indent=1, default=float)
pd.set_option('display.width', 250)
print('limpios', len(d), 'de', n0, '; outliers', len(outliers))
print(p[p.ent == 'ALCALDIA'].pivot_table(index='periodo', columns='categoria', values='valor', aggfunc='sum').div(1e6).round(0).to_string())
print(p[p.ent == 'ALCALDIA'].pivot_table(index='periodo', columns='categoria', values='n', aggfunc='sum').to_string())
print(p[p.ent == 'HOSPITAL'].pivot_table(index='periodo', columns='categoria', values='valor', aggfunc='sum').div(1e6).round(0).to_string())
print(pd.DataFrame(out['ops_formulacion']).to_string())
print(c.to_string())
print(pd.DataFrame(out['ops_anual']).query("ent=='ALCALDIA'").to_string())
print(len(rows), 'estudios;', sum(1 for r in rows if r['obra_relacionada_probable']), 'con obra probable')
