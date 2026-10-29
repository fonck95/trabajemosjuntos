"""Genera docs/02-marco-comparativo-2004-2027.md desde data/periodos.json, data/gobiernos.json y data/secop.

Uso: python3 scripts/build_periodos.py && python3 scripts/build_marco_md.py
"""
import csv
import json
from pathlib import Path

R = Path(__file__).resolve().parent.parent
D = R / 'data'
P = json.loads((D / 'periodos.json').read_text())
sec = json.loads((D / 'secop/secop_resumen.json').read_text())
oec = {int(r['anio']): r for r in csv.DictReader(open(D / 'fuentes/serie_fiscal_oec.csv'))}
PER = [p['id'] for p in P['periodos']]
m = lambda v: f"{v:,.0f}".replace(',', '.')

# Dinero por periodo
cont = {}
for r in sec['por_periodo']:
    if r['ent'] == 'ALCALDIA':
        c = cont.setdefault(r['periodo'], {'total': 0, 'ops_n': 0, 'est': 0, 'obra': 0})
        c['total'] += r['valor']
        if r['categoria'] == 'OPS / apoyo a la gestión':
            c['ops_n'] += r['n']
        if r['categoria'] == 'Estudios / consultoría':
            c['est'] += r['valor']
        if r['categoria'] == 'Obra':
            c['obra'] += r['valor']
dir_ = {r['periodo']: r['pct_valor_directa'] for r in sec['directa_por_periodo']}

L = []
w = L.append
w('# 02 · Marco comparativo 2004–2027: seis gobiernos, las mismas brechas\n')
w('> Documento generado por `scripts/build_marco_md.py` a partir de `data/gobiernos.json`, `data/periodos.json` y `data/secop/`. La vista **Seis gobiernos** del atlas muestra la misma matriz en 3D. Las fuentes de cada dato están en `docs/anexos/` (A: gobiernos, B: finanzas, E: indicadores sociales).\n')
w('## 1. La plata de cada periodo\n')
w('| Periodo | Alcalde | Ingresos en caja (M COP) | Regalías en caja (M COP) | Contratado en SECOP (M COP) | Obra pública (M COP) | Estudios y consultorías (M COP) | Contratos OPS | % del valor sin competencia |')
w('|---|---|---:|---:|---:|---:|---:|---:|---:|')
for p in P['periodos']:
    pid = p['id']
    ys = [y for y in range(int(pid[:4]), int(pid[:4]) + 4) if y in oec]
    ing = sum(float(oec[y]['ingresos_totales_mm']) for y in ys)
    reg = sum(float(oec[y]['regalias_giradas_mm_derivado']) for y in ys)
    c = cont.get(pid, {})
    nota = '' if len(ys) == 4 else f' ({ys[0]})'
    sin = '—' if pid == '2004-2007' else f"{dir_.get(pid, 0):.0f} %"
    contr = '—' if pid == '2004-2007' else m(c.get('total', 0) / 1e6)
    w(f"| {pid} | {p['alcalde'].split(' (')[0]} | {m(ing)}{nota} | {m(reg)}{nota} | {contr} | {'—' if pid == '2004-2007' else m(c.get('obra', 0) / 1e6)} | {'—' if pid == '2004-2007' else m(c.get('est', 0) / 1e6)} | {'—' if pid == '2004-2007' else m(c.get('ops_n', 0))} | {sin} |")
w('\nIngresos y regalías: Operaciones Efectivas de Caja (DNP–FUT vía TerriData); desde 2012 "regalías" son los giros del SGR que entran a la caja municipal (los proyectos del OCAD Paz van aparte). Contratación: SECOP depurado (`docs/03`); 2004–2007 sin registros suficientes y 2024–2027 con datos hasta octubre de 2026. Valores corrientes.\n')
w('## 2. La matriz de desempeño (0–100)\n')
w('| Área | ' + ' | '.join(PER) + ' | Cómo se calcula |')
w('|---|' + '---:|' * len(PER) + '---|')
for a in P['areas']:
    cells = ['—' if a['valores'][p] is None else f"**{a['valores'][p]:.0f}** ({a['crudo'][p]})" for p in PER]
    w(f"| {a['nombre']} | " + ' | '.join(cells) + f" | {a['metodo']} |")
w('\n"—" significa que no hay un dato verificable para ese periodo; no es cero. El periodo 2024–2027 es parcial.\n')
w('### Lo que dice la matriz\n')
w('- **El dinero subió, la competencia bajó.** Los ingresos en caja pasaron de $93.088 M (2004–2007) a $252.429 M (2020–2023), pero desde 2020 más del 80 % del valor contratado se adjudica sin competencia.')
w('- **La gestión fiscal pasó de "solvente" a "vulnerable".** Parte de la caída se explica por el cambio de metodología del DNP en 2020, pero el municipio sigue dependiendo de transferencias en un 56 % (2024).')
w('- **El agua urbana mejoró; la rural no.** El IRCA urbano está "sin riesgo" desde 2015, pero el rural fue "inviable sanitariamente" en 2021–2023 y el casco urbano no tiene planta de tratamiento de aguas residuales; la vereda La Represa tiene una desde 2022 (BPIN 20201301011453).')
w('- **La educación media avanza despacio**: la cobertura neta pasó de 14 % a 31 % en veinte años.')
w('- **La seguridad empeoró en los dos últimos periodos**: de 25 homicidios por 100.000 habitantes en 2016–2019 a 134 en 2024–2025, con 2025 como el peor año de la serie.')
w('- **La conectividad retrocedió**: Yondó tiene la séptima parte de la penetración de internet fijo de Antioquia.\n')
w('## 3. Cada periodo: qué se hizo, qué pudo hacerse y no se hizo\n')
for p in P['periodos']:
    w(f"### {p['id']} · {p['alcalde']}\n")
    w(f"**Plan:** {p['plan']}  ")
    w(f"**Plata:** {p['plata']}\n")
    w('**Lo que se hizo**\n')
    for x in p['hizo']:
        w(f'- {x}')
    w('\n**Lo que pudo hacerse y no se hizo**\n')
    for x in p['falto']:
        w(f'- {x}')
    if p.get('alertas'):
        w('\n**Órganos de control**\n')
        for x in p['alertas']:
            w(f'- {x}')
    if p.get('contexto'):
        w(f"\n*Contexto:* {p['contexto']}")
    w('')
w('## 4. Los cuatro patrones que se repiten\n')
w('1. **Los grandes compromisos de agua y saneamiento se reciclan.** El Plan Maestro de Acueducto y Alcantarillado aparece en el plan de 2005 y sus estudios siguen inactivos en 2026; la PTAR del casco urbano nunca se construyó.')
w('2. **Los estudios no tienen dueño de la obra.** La Ciudadela Educativa (diseños 2014), la revisión del EOT (2019, suspendida), la Transversal de las Américas (diseños 2021 sin obra) y el Plan Maestro (2024, inactivo) son el mismo patrón en gobiernos distintos.')
w('3. **La ejecución se delega y se pierde el control.** En 2020–2023, $84.016 M pasaron por la EDU de Medellín; los proyectos de vivienda quedaron con 9 % y 17 % de avance físico y cerca del 90 % de los recursos girados.')
w('4. **La nómina paralela crece y no responde por productos.** De 91 OPS en 2008–2011 a más de 1.200 por periodo desde 2012; 425 contratos para "formular proyectos" sin un solo producto radicado exigido en su objeto.\n')
w('La hoja de ruta para romper estos patrones está en `docs/04`.')
(R / 'docs/02-marco-comparativo-2004-2027.md').write_text('\n'.join(L) + '\n', encoding='utf-8')
print('docs/02 generado:', len(L), 'líneas')
