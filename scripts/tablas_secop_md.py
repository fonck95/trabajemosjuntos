"""Imprime en Markdown las tablas SECOP usadas en docs/03 (para regenerarlas si cambian los datos)."""
import json
from pathlib import Path
o = json.loads((Path(__file__).resolve().parent.parent / 'data/secop/secop_resumen.json').read_text())
P = ['2008-2011', '2012-2015', '2016-2019', '2020-2023', '2024-2027']
C = ['Obra', 'OPS / apoyo a la gestión', 'Convenios / interadministrativos', 'Estudios / consultoría', 'Interventoría', 'Suministro / compraventa', 'Otros servicios']
m = lambda v: f"{v / 1e6:,.0f}".replace(',', '.')
def tabla(ent, campo, titulo):
    cell = {(r['periodo'], r['categoria']): r[campo] for r in o['por_periodo'] if r['ent'] == ent}
    print(f"\n**{titulo}**\n")
    print('| Categoría | ' + ' | '.join(P) + ' |')
    print('|---|' + '---:|' * len(P))
    for c in C:
        f = (lambda v: m(v)) if campo == 'valor' else (lambda v: f"{v:,.0f}".replace(',', '.'))
        print(f'| {c} | ' + ' | '.join(f(cell.get((p, c), 0)) for p in P) + ' |')
    tot = [sum(cell.get((p, c), 0) for c in C) for p in P]
    f = m if campo == 'valor' else (lambda v: f"{v:,.0f}".replace(',', '.'))
    print('| **Total** | ' + ' | '.join(f'**{f(t)}**' for t in tot) + ' |')
for ent, nom in [('ALCALDIA', 'Alcaldía'), ('HOSPITAL', 'E.S.E. Hospital Héctor Abad Gómez'), ('AGUAS', 'Aguas y Aseo de Yondó')]:
    tabla(ent, 'valor', f'{nom} — valor contratado (millones COP corrientes)')
    tabla(ent, 'n', f'{nom} — número de contratos')
print('\n**Alcaldía — modalidad sin competencia (directa, convenios, régimen especial)**\n')
print('| Periodo | Contratos | Valor (M COP) | % del valor | % de los contratos |\n|---|---:|---:|---:|---:|')
for r in o['directa_por_periodo']:
    print(f"| {r['periodo']} | {r['n']:,.0f} | {m(r['valor'])} | {r['pct_valor_directa']} % | {r['pct_n_directa']} % |".replace(',', '.'))
print('\n**Alcaldía — OPS y apoyo a la gestión por año**\n')
print('| Año | Contratos | Personas/empresas distintas | Valor (M COP) |\n|---|---:|---:|---:|')
for r in o['ops_anual']:
    if r['ent'] == 'ALCALDIA':
        print(f"| {int(r['anio'])} | {r['n']} | {r['personas']} | {m(r['valor'])} |")
print('\n**OPS cuyo objeto es planeación, formulación o banco de proyectos**\n')
print('| Entidad | Periodo | Contratos | Valor (M COP) |\n|---|---|---:|---:|')
for r in o['ops_formulacion']:
    print(f"| {r['ent']} | {r['periodo']} | {r['n']} | {m(r['valor'])} |")
print('\n**Contratos con la Empresa de Desarrollo Urbano de Medellín (EDU)**\n')
print('| Fecha | Valor (M COP) | Objeto |\n|---|---:|---|')
for r in o['edu']:
    print(f"| {r['fecha']} | {m(r['valor'])} | {r['objeto'][:200].capitalize()} |")
e = o['estudios']
print(f"\n**Estudios y consultorías (alcaldía): {len(e)} contratos, {m(sum(x['valor'] for x in e))} M COP; con obra posterior identificable: {sum(1 for x in e if x['obra_relacionada_probable'])}**\n")
print('| Año | Valor (M COP) | Objeto | Obra posterior identificable en SECOP |\n|---|---:|---|---|')
for x in sorted(e, key=lambda x: -x['valor'])[:25]:
    ob = f"Sí ({x['anio_obra']}, {x['estado_obra']}): {x['obra_relacionada_probable'][:90].capitalize()}" if x['obra_relacionada_probable'] else 'No hallada'
    print(f"| {x['anio']} | {m(x['valor'])} | {x['objeto'][:150].capitalize()} | {ob} |")
