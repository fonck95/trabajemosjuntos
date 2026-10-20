"""Construye data/periodos.json: matriz área × periodo de gobierno (0–100) + narrativa de cada periodo.

Entradas: data/fuentes/series_sociales.json, data/fuentes/serie_fiscal_oec.csv, data/secop/secop_resumen.json,
data/gobiernos.json (narrativa e índices del DNP por periodo).
Uso: python3 scripts/build_periodos.py
"""
import csv
import json
from pathlib import Path

R = Path(__file__).resolve().parent.parent
D = R / 'data'
S = json.loads((D / 'fuentes/series_sociales.json').read_text())
G = json.loads((D / 'gobiernos.json').read_text())
sec = json.loads((D / 'secop/secop_resumen.json').read_text())
fis = {int(r['anio']): r for r in csv.DictReader(open(D / 'fuentes/serie_fiscal_oec.csv'))}

PER = ['2004-2007', '2008-2011', '2012-2015', '2016-2019', '2020-2023', '2024-2027']
yrs = lambda p: range(int(p[:4]), int(p[:4]) + 4)
serie = lambda k: {int(a): v for a, v in S[k]['serie'].items() if v is not None}
fmt = lambda v, d=1: f"{v:,.{d}f}".replace(',', 'X').replace('.', ',').replace('X', '.')

def por_periodo(fn):
    """fn(año) -> valor o None; devuelve promedio por periodo y años usados."""
    out = {}
    for p in PER:
        vals = [(a, fn(a)) for a in yrs(p)]
        vals = [(a, v) for a, v in vals if v is not None]
        out[p] = (sum(v for _, v in vals) / len(vals), [a for a, _ in vals]) if vals else (None, [])
    return out

def area(key, nombre, corto, slot, fuente, metodo, norm, crudo_fn):
    vals, crudo, det = {}, {}, {}
    for p, (v, anios) in norm.items():
        vals[p] = None if v is None else round(max(0, min(100, v)), 1)
        crudo[p] = crudo_fn(p) if v is not None else '—'
        if anios:
            det[p] = f"Años con dato: {anios[0]}–{anios[-1]}" if len(anios) > 1 else f"Año con dato: {anios[0]}"
    return {'key': key, 'nombre': nombre, 'corto': corto, 'slot': slot, 'fuente': fuente, 'metodo': metodo, 'valores': vals, 'crudo': crudo, 'detalle': det}

# 1. Desempeño fiscal (IDF antiguo 2000–2019; nuevo IDF 2020–2024)
idf = {}
for a, r in fis.items():
    v = r['idf'].strip()
    if v:
        idf[a] = float(v.split('/')[-1]) if '/' in v else float(v)
idf_nuevo = {2020: 64.32, 2021: 60.52, 2022: 66.46, 2023: 67.04, 2024: 64.48}
idf.update(idf_nuevo)
n_idf = por_periodo(idf.get)
a_fiscal = area('fiscal', 'Desempeño fiscal (IDF, DNP)', 'Fiscal', 1, 'DNP–FUT vía TerriData',
                'Índice de Desempeño Fiscal tal como lo publica el DNP (0–100). Hasta 2019 metodología antigua; desde 2020 la nueva, más exigente: no son comparables en nivel.',
                n_idf, lambda p: fmt(n_idf[p][0]) + (' · IDF nuevo' if int(p[:4]) >= 2020 else ''))

# 2. Desempeño municipal: IDI (2006–2015) y MDM (2016–2024)
mdm = serie('MDM_medicion_desempeno_municipal')
idi = {int(a): v for a, v in G.get('idi', {}).items()}
gest = {**idi, **mdm}
n_gest = por_periodo(gest.get)
a_gest = area('municipal', 'Desempeño municipal (IDI 2006–2015 · MDM 2016–2024, DNP)', 'Gestión', 2, 'DNP: Índice de Desempeño Integral y Medición de Desempeño Municipal',
              'Promedio del índice del DNP en los años del periodo (0–100). El IDI y la MDM son metodologías distintas.',
              n_gest, lambda p: fmt(n_gest[p][0]))

# 3. Competencia en la contratación (SECOP)
dir_ = {r['periodo']: r for r in sec['directa_por_periodo']}
n_comp = {p: ((100 - dir_[p]['pct_valor_directa']), [int(p[:4])]) if p in dir_ and p != '2004-2007' else (None, []) for p in PER}
a_comp = area('competencia', 'Competencia en la contratación de la alcaldía (SECOP)', 'Competencia', 3, 'SECOP I y II, datos.gov.co',
              '100 − % del valor contratado sin pluralidad de oferentes (contratación directa, convenios, régimen especial). 2004–2007 sin registros suficientes.',
              n_comp, lambda p: f"{fmt(dir_[p]['pct_valor_directa'])} % directa")
for p in PER:
    a_comp['detalle'].pop(p, None)

# 4. Agua potable: 100 − IRCA total (los ceros de 2007–2008 son ausencia de reporte)
irca = {a: v for a, v in serie('irca_total').items() if a >= 2009}
n_agua = por_periodo(lambda a: None if a not in irca else 100 - irca[a])
a_agua = area('agua', 'Calidad del agua (100 − IRCA, INS)', 'Agua', 4, 'INS–SIVICAP',
              '100 menos el IRCA promedio (0 = sin riesgo). El IRCA rural, cuando se mide, es "inviable sanitariamente" (82–97 en 2021–2023), y no hay PTAR.',
              n_agua, lambda p: f"IRCA {fmt(100 - n_agua[p][0])}")

# 5. Educación media: cobertura neta
cm = serie('cobertura_neta_media')
n_edu = por_periodo(cm.get)
a_edu = area('educacion', 'Cobertura neta en educación media (MEN)', 'Educación', 5, 'MEN–SIMAT vía TerriData',
             'Porcentaje de jóvenes de 15–16 años matriculados en media (meta 100).', n_edu, lambda p: f"{fmt(n_edu[p][0])} %")

# 6. Salud infantil: mortalidad infantil relativa a Colombia
tmi, tmic = serie('tasa_mortalidad_infantil_menor1'), serie('tasa_mortalidad_infantil_menor1_colombia')
n_sal = por_periodo(lambda a: 100 * min(1, tmic[a] / tmi[a]) if a in tmi and a in tmic and tmi[a] else None)
tmi_p = por_periodo(tmi.get)
a_sal = area('salud', 'Mortalidad infantil frente a Colombia (DANE/MinSalud)', 'Salud', 6, 'DANE–EEVV vía TerriData',
             '100 × (tasa nacional ÷ tasa de Yondó), tope 100. 100 = igual o mejor que el país.', n_sal, lambda p: f"{fmt(tmi_p[p][0])} ‰")

# 7. Seguridad: homicidio relativo a Antioquia
th, tha = serie('tasa_homicidio_intencional'), serie('tasa_homicidio_intencional_antioquia')
n_seg = por_periodo(lambda a: 100 * min(1, tha[a] / th[a]) if a in th and a in tha and th[a] else None)
th_p = por_periodo(th.get)
a_seg = area('seguridad', 'Homicidios frente a Antioquia (MinDefensa)', 'Seguridad', 7, 'MinDefensa/DNP vía TerriData',
             '100 × (tasa de Antioquia ÷ tasa de Yondó), tope 100. En 2025 Yondó tuvo 185,8 homicidios por 100.000 habitantes, 7,5 veces Antioquia.',
             n_seg, lambda p: f"{fmt(th_p[p][0])} por 100 mil")

# 8. Conectividad: internet fijo relativo a Antioquia
ni, nia = serie('penetracion_internet_fijo'), serie('penetracion_internet_fijo_antioquia')
n_con = por_periodo(lambda a: 100 * ni[a] / nia[a] if a in ni and a in nia else None)
ni_p = por_periodo(ni.get)
a_con = area('conectividad', 'Internet fijo frente a Antioquia (MinTIC)', 'Conectividad', 8, 'MinTIC vía TerriData',
             '100 × (accesos por 100 hab. en Yondó ÷ Antioquia). 100 = igual al promedio departamental.', n_con, lambda p: f"{fmt(ni_p[p][0], 2)} por 100 hab.")

areas = [a_fiscal, a_gest, a_comp, a_agua, a_edu, a_sal, a_seg, a_con]
out = {'periodos': G['periodos'], 'areas': areas}
(D / 'periodos.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
print('| Área | ' + ' | '.join(PER) + ' |')
for a in areas:
    print(f"| {a['corto']} | " + ' | '.join('—' if a['valores'][p] is None else f"{a['valores'][p]:.0f} ({a['crudo'][p]})" for p in PER) + ' |')
