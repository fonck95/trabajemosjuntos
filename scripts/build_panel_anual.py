#!/usr/bin/env python3
"""Panel anual de Yondó 2004-2026 para comparar los seis gobiernos.

Genera:
  data/comparativa/panel_anual.json  -> años, IPC, indicadores por área (series anuales con fuente,
                                        y Antioquia y Colombia cuando son comparables) y agregados
                                        por gobierno (sumas, promedios, inicio y final de cada indicador).
  data/fuentes/ipc_dane.csv          -> el IPC que usa todo el proyecto (el mismo de costo_no_hacer.json).

Uso normal (solo lee archivos del repositorio, no descarga nada):
  python3 scripts/build_panel_anual.py

Actualizar las fuentes descargadas (opcional):
  python3 -I scripts/build_panel_anual.py --actualizar-fuentes --cache /ruta/temporal \\
          [--secop-raw /ruta/integrado.json]
  Descarga en --cache los perfiles de TerriData (Yondó, Antioquia y Colombia), la distribución de
  regalías de MapaRegalías y la ejecución presupuestal de CUIPO, y reescribe:
    data/fuentes/terridata_panel.csv, data/fuentes/sgr_distribucion_anual.csv,
    data/fuentes/cuipo_resumen_anual.csv
  Con --secop-raw (descarga de scripts/descargar_secop.sh) reescribe además
    data/fuentes/secop_competencia_anual.csv (requiere pandas).

Reglas: cada cifra lleva su fuente; los años sin dato se omiten (no se rellenan con cero);
los años incompletos van aparte, en "parcial".
"""
import argparse
import csv
import json
import statistics
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
D = RAIZ / "data"
F = D / "fuentes"
SALIDA = D / "comparativa" / "panel_anual.json"
FECHA_CORTE = "2026-10-21"

ANIOS = list(range(2004, 2027))
AREAS = ["Plata", "Gestión", "Contratación", "Agua y saneamiento", "Educación", "Salud",
         "Seguridad y conflicto", "Economía", "Conectividad y energía", "Ambiente y riesgo"]
ENTIDADES = {"05893": "Yondó", "05000": "Antioquia", "01001": "Colombia"}
URL_TD_ZIP = "https://terridata.dnp.gov.co/assets/docs/txt/entidades/TerriData{cod}.txt.zip"
URL_TD_PERFIL = "https://terridata.dnp.gov.co/index-app.html#/perfiles/05893"
URL_MAPA_REGALIAS = "https://www.datos.gov.co/resource/h6yd-ei3n.json"
URL_CUIPO_ING = "https://www.datos.gov.co/resource/9axr-9gnb.json"
URL_CUIPO_GAS = "https://www.datos.gov.co/resource/4f7r-epif.json"
CHIP_YONDO = "219305893"

# ---------------------------------------------------------------------------
# Indicadores que se extraen de TerriData: clave -> (dimensión, subcategoría o None, indicador)
# ---------------------------------------------------------------------------
_MDM = "Medición de desempeño municipal"
_FIN = "Finanzas públicas"
_VIV = "Vivienda y acceso a servicios públicos"
_INV = ("Finanzas públicas", "Inversión por sectores")
TD_SPEC = {
    "oec_deficit": (_FIN, "Operaciones efectivas de caja", "Déficit o superávit total"),
    "inv_recursos_propios": (_FIN, "Recursos propios", "Porcentaje de inversión con recursos propios"),
    "idf": (_FIN, "Desempeño fiscal", "Indicador de desempeño fiscal"),
    "idf_nuevo": (_FIN, "Nuevo Índice de Desempeño Fiscal", "Puntaje nuevo Índice de Desempeño Fiscal"),
    "igpr": (_FIN, "SGR - IGPR", "Índice de gestión de proyectos de regalías (IGPR)"),
    "igpr_nuevo": (_FIN, "SGR - Nuevo IGPR", "Puntaje nuevo Indice de gestión de proyectos de regalías - IGPR"),
    "mdm": (_MDM, "Resumen MDM", "MDM"),
    "mdm_gestion": (_MDM, "Resumen MDM", "Componente de gestión"),
    "mdm_resultados": (_MDM, "Resumen MDM", "Componente de resultados"),
    "mdm_movilizacion": (_MDM, "Componente de gestión", "Movilización de recursos"),
    "mdm_ejecucion": (_MDM, "Componente de gestión", "Ejecución de recursos"),
    "mdm_ot": (_MDM, "Componente de gestión", "Recaudo con instrumentos de ordenamiento territorial"),
    "mdm_gobierno_abierto": (_MDM, "Componente de gestión", "Gobierno abierto y transparencia"),
    "mdm_educacion": (_MDM, "Componente de resultados", "Educación"),
    "mdm_salud": (_MDM, "Componente de resultados", "Salud"),
    "mdm_servicios": (_MDM, "Componente de resultados", "Acceso a servicios públicos"),
    "mdm_seguridad": (_MDM, "Componente de resultados", "Seguridad"),
    "inv_educacion": (*_INV, "Inversión - Educación"),
    "inv_salud": (*_INV, "Inversión - Salud"),
    "inv_agua": (*_INV, "Inversión - Agua potable y saneamiento básico (sin incluir proyectos de vis)"),
    "inv_transporte": (*_INV, "Inversión - Transporte"),
    "inv_agro": (*_INV, "Inversión - Agropecuario"),
    "inv_ambiental": (*_INV, "Inversión - Ambiental"),
    "inv_desastres": (*_INV, "Inversión - Prevención y atención de desastres"),
    "inv_seguridad": (*_INV, "Inversión - Justicia y seguridad"),
    "inv_fortalecimiento": (*_INV, "Inversión - Fortalecimiento institucional"),
    "inv_otros_servicios": (*_INV, "Inversión - Servicios públicos diferentes a acueducto alcantarillado y aseo "
                                   "(sin incluir proyectos de vivienda de interés social)"),
    "acueducto_total": (_VIV, None, "Cobertura de acueducto (REC)"),
    "acueducto_urbana": (_VIV, None, "Cobertura de acueducto urbana (REC)"),
    "acueducto_rural": (_VIV, None, "Cobertura de acueducto rural (REC)"),
    "alcantarillado_total": (_VIV, None, "Cobertura de alcantarillado (REC)"),
    "alcantarillado_urbana": (_VIV, None, "Cobertura de alcantarillado urbana (REC)"),
    "alcantarillado_rural": (_VIV, None, "Cobertura de alcantarillado rural (REC)"),
    "aseo_total": (_VIV, None, "Cobertura de aseo (REC)"),
    "acueducto_censo": (_VIV, None, "Cobertura de acueducto (Censo)"),
    "alcantarillado_censo": (_VIV, None, "Cobertura de alcantarillado (Censo)"),
    "energia_rural": (_VIV, None, "Cobertura de energía eléctrica rural"),
    "energia_total": (_VIV, None, "Cobertura de energia eléctrica total"),
    "energia_urbana": (_VIV, None, "Cobertura de energia eléctrica urbana"),
    "internet_fijo": (_VIV, None, "Penetración de acceso fijo a Internet"),
    "cob_neta": ("Educación", None, "Cobertura neta en educación - Total"),
    "cob_bruta": ("Educación", None, "Cobertura bruta en educación - Total"),
    "cob_neta_transicion": ("Educación", None, "Cobertura neta en transición"),
    "cob_neta_secundaria": ("Educación", None, "Cobertura neta en educación secundaria"),
    "cob_neta_media": ("Educación", None, "Cobertura neta en educación media"),
    "desercion_oficial": ("Educación", None, "Tasa de deserción intra-anual del sector oficial en educación básica y "
                                             "media (Desde transición hasta once)"),
    "repitencia_oficial": ("Educación", None, "Tasa de repitencia del sector oficial en educación básica y media "
                                              "(Desde transición hasta once)"),
    "transito_superior": ("Educación", None, "Tasa de tránsito inmediato a la educación superior"),
    "saber11_mat": ("Educación", None, "Puntaje promedio Pruebas Saber 11 - Matemáticas"),
    "saber11_lec": ("Educación", None, "Puntaje promedio Pruebas Saber 11 - Lectura crítica"),
    "mort_infantil": ("Salud", None, "Tasa de mortalidad infantil en menores de 1 año (x cada 1.000 nacidos vivos)"),
    "mort_menor5": ("Salud", None, "Tasa de mortalidad infantil en menores de 5 años"),
    "mort_neonatal": ("Salud", None, "Tasa de mortalidad neonatal"),
    "mort_materna": ("Salud", None, "Razón de mortalidad materna a 42 días"),
    "vac_pentavalente": ("Salud", None, "Cobertura vacunación pentavalente en menores de 1 año"),
    "vac_triple_viral": ("Salud", None, "Cobertuna de vacunación triple viral"),
    "bajo_peso": ("Salud", None, "Porcentaje de nacidos vivos con bajo peso al nacer"),
    "prenatal4": ("Salud", None, "Porcentaje de nacidos vivos con 4 o más consultas de control prenatal"),
    "partos_calificados": ("Salud", None, "Porcentaje de partos atendidos por personal calificado"),
    "madres_14_17": ("Salud", None, "Porcentaje de nacidos vivos hijos de mujeres de 14 a 17 años"),
    "fecundidad_15_19": ("Salud", None, "Tasa de fecundidad en mujeres entre 15 y 19 años"),
    "dengue": ("Salud", None, "Incidencia del dengue"),
    "tuberculosis": ("Salud", None, "Incidencia de la tuberculosis"),
    "reg_subsidiado": ("Salud", None, "Cobertura del régimen subsidiado"),
    "homicidio_tasa": ("Convivencia y seguridad ciudadana", None, "Tasa de homicidio intencional por cada 100.000 habitantes"),
    "extorsion": ("Convivencia y seguridad ciudadana", None, "Tasa de extorsión por cada 100.000 habitantes"),
    "hurto_personas": ("Convivencia y seguridad ciudadana", None, "Tasa de hurto a personas por cada 100.000 habitantes"),
    "vif": ("Convivencia y seguridad ciudadana", None, "Tasa de violencia intrafamiliar por cada 100.000 habitantes"),
    "delitos_sexuales": ("Convivencia y seguridad ciudadana", None, "Tasa de delitos sexuales por cada 100.000 habitantes"),
    "minas": ("Paz y víctimas", None, "Eventos de Minas Antipersonal"),
    "coca": ("Paz y víctimas", None, "Hectáreas de cultivo de coca"),
    "iica": ("Paz y víctimas", None, "Índice de Incidencia del Conflicto Armado - IICA"),
    "va": ("Economía", "Valor agregado municipal", "Valor agregado"),
    "va_pc_vs_pais": ("Economía", "Valor agregado municipal", "Valor agregado per cápita como porcentaje del promedio nacional"),
    "va_primarias": ("Economía", "Valor agregado municipal",
                     "Porcentaje del valor agregado por actividades económicas - Actividades primarias"),
    "cotizantes": ("Mercado laboral", None, "Trabajadores cotizantes al sistema general de seguridad social (promedio mensual)"),
    "empleo_formal": ("Mercado laboral", None, "Porcentaje de personas ocupadas formalmente con respecto a la población total"),
    "bosque": ("Ambiente", None, "Área de bosque estable de la entidad territorial"),
    "deforestacion": ("Ambiente", None, "Área deforestada en la entidad territorial"),
    "afectados_desastres": ("Ambiente", None, "Tasa de personas afectadas (muertas, heridas, desaparecidas y/o afectadas) "
                                              "por eventos recurrentes"),
    "inundaciones": ("Ambiente", None, "Inundaciones"),
    "psa_cuencas": ("Ambiente", None, "Porcentaje de ingresos corrientes destinados a adquisición de predios o PSA en "
                                      "cuencas abastecedoras de acueducto"),
    "sinap": ("Ambiente", None, "Área de la entidad territorial que hace parte del SINAP"),
}


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def num_td(s):
    """Número en formato TerriData ('1.234,56') -> float; vacío -> None."""
    s = (s or "").strip()
    if not s:
        return None
    try:
        return float(s.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def r(v):
    """Redondeo para publicar: más decimales cuanto más pequeño es el número."""
    if v is None:
        return None
    a = abs(v)
    if a >= 10000:
        return round(v)
    if a >= 100:
        return round(v, 1)
    if a >= 1:
        return round(v, 2)
    return round(v, 3)


def descargar_json(url, params, destino):
    q = urllib.parse.urlencode(params)
    with urllib.request.urlopen(f"{url}?{q}", timeout=180) as resp:
        data = resp.read()
    Path(destino).write_bytes(data)
    return json.loads(data)


def leer_csv(nombre):
    with open(F / nombre, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


# ---------------------------------------------------------------------------
# 1. Actualización de fuentes (opcional, con descargas)
# ---------------------------------------------------------------------------
def actualizar_terridata(cache):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    filas = []
    for cod, nombre in ENTIDADES.items():
        z = cache / f"TerriData{cod}.txt.zip"
        if not z.exists():
            urllib.request.urlretrieve(URL_TD_ZIP.format(cod=cod), z)
        with zipfile.ZipFile(z) as zf:
            txt = zf.read([n for n in zf.namelist() if n.endswith(".txt")][0]).decode("utf-8")
        # (dim, subcat, indicador) -> {año: (mes, valor, unidad, fuente)}; se guarda el último mes con dato
        datos = {}
        for line in txt.splitlines():
            p = line.split("|")
            if len(p) < 13 or not p[9].isdigit():
                continue
            v = num_td(p[7])
            if v is None:
                continue
            k = (p[4], p[5], p[6])
            anio, mes = int(p[9]), int(p[10] or 0)
            prev = datos.setdefault(k, {}).get(anio)
            if prev is None or mes >= prev[0]:
                datos[k][anio] = (mes, v, p[12], p[11].strip())
        for clave, (dim, sub, ind) in TD_SPEC.items():
            cands = [k for k in datos if k[0] == dim and k[2] == ind and (sub is None or k[1] == sub)]
            if not cands:
                continue
            k = max(cands, key=lambda c: len(datos[c]))  # si hay dos subcategorías, la de serie más larga
            for anio in sorted(datos[k]):
                mes, v, unidad, fte = datos[k][anio]
                filas.append({"clave": clave, "codigo_entidad": cod, "entidad": nombre, "dimension": k[0],
                              "subcategoria": k[1], "indicador": k[2], "unidad": unidad, "anio": anio, "mes": mes,
                              "valor": repr(v), "fuente_original": fte, "url": URL_TD_ZIP.format(cod=cod)})
    campos = ["clave", "codigo_entidad", "entidad", "dimension", "subcategoria", "indicador", "unidad", "anio", "mes",
              "valor", "fuente_original", "url"]
    with open(F / "terridata_panel.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=campos)
        w.writeheader()
        w.writerows(filas)
    print(f"terridata_panel.csv: {len(filas)} filas")


def actualizar_mapa_regalias(cache):
    d = descargar_json(URL_MAPA_REGALIAS, {"entidadterritorial": "Antioquia-Yondó", "$limit": 5000},
                       Path(cache) / "mapa_regalias_yondo.json")
    tot = {}
    for x in d:
        k = (int(x["vigencia"]), x.get("tiporecurso") or "(sin tipo de recurso)")
        tot[k] = tot.get(k, 0.0) + float(x.get("distribucionpresupuestada") or 0)
    with open(F / "sgr_distribucion_anual.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["vigencia", "tipo_recurso", "distribucion_presupuestada_pesos", "registros_fuente", "url"])
        n = {}
        for x in d:
            k = (int(x["vigencia"]), x.get("tiporecurso") or "(sin tipo de recurso)")
            n[k] = n.get(k, 0) + 1
        for k in sorted(tot):
            w.writerow([k[0], k[1], round(tot[k], 2), n[k],
                        "https://www.datos.gov.co/d/h6yd-ei3n (entidadterritorial=Antioquia-Yondó)"])
    print(f"sgr_distribucion_anual.csv: {len(tot)} filas de {len(d)} registros")


CUIPO_ING = {"1": "recaudo_total", "1.1": "ingresos_corrientes", "1.1.01": "tributarios",
             "1.1.02": "no_tributarios", "1.1.02.06": "transferencias_corrientes", "1.2": "recursos_de_capital"}
CUIPO_GAS = {"2": "compromisos_total", "2.1": "funcionamiento", "2.2": "servicio_deuda", "2.3": "inversion"}


def actualizar_cuipo(cache):
    cache = Path(cache)
    lista = ",".join(f"'{c}'" for c in CUIPO_ING)
    ing = descargar_json(URL_CUIPO_ING, {"$where": f"codigo_entidad='{CHIP_YONDO}' AND cuenta in ({lista})",
                                         "$limit": 50000}, cache / "cuipo_ingresos_yondo.json")
    lista = ",".join(f"'{c}'" for c in CUIPO_GAS)
    gas = descargar_json(URL_CUIPO_GAS, {"$where": f"codigo_entidad='{CHIP_YONDO}' AND cuenta in ({lista}) "
                                                   f"AND nom_vigencia_del_gasto='VIGENCIA ACTUAL'",
                                         "$limit": 50000}, cache / "cuipo_gastos_yondo.json")
    periodos = sorted({x["periodo"] for x in ing} | {x["periodo"] for x in gas})
    ultimo = periodos[-1]
    usar = [p for p in periodos if p.endswith("1201")] + ([ultimo] if not ultimo.endswith("1201") else [])
    filas = []
    for per in usar:
        anio, completo = int(per[:4]), per.endswith("1201")
        for cta, concepto in CUIPO_ING.items():
            v = sum(float(x.get("total_recaudo") or 0) for x in ing if x["periodo"] == per and x["cuenta"] == cta)
            filas.append([anio, per, "sí" if completo else "no", concepto, cta, "recaudo", round(v, 2),
                          "https://www.datos.gov.co/d/9axr-9gnb"])
        for cta, concepto in CUIPO_GAS.items():
            v = sum(float(x.get("compromisos") or 0) for x in gas if x["periodo"] == per and x["cuenta"] == cta)
            filas.append([anio, per, "sí" if completo else "no", concepto, cta, "compromisos de la vigencia",
                          round(v, 2), "https://www.datos.gov.co/d/4f7r-epif"])
    with open(F / "cuipo_resumen_anual.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["anio", "periodo_corte", "anio_completo", "concepto", "cuenta", "medida", "valor_pesos", "url"])
        w.writerows(filas)
    print(f"cuipo_resumen_anual.csv: {len(filas)} filas ({', '.join(usar)})")


def actualizar_secop(raw):
    """Mismo filtro y depuración de scripts/secop_analisis.py; agrega por año los contratos de la alcaldía."""
    import re
    import unicodedata
    import pandas as pd
    d = pd.DataFrame(json.load(open(raw, encoding="utf-8")))
    d["valor"] = pd.to_numeric(d["valor_contrato"], errors="coerce")
    d["fecha"] = pd.to_datetime(d["fecha_de_firma_del_contrato"], errors="coerce")
    d["anio"] = d["fecha"].dt.year

    def ent(n):
        n = n.upper()
        if "HOSPITAL" in n:
            return "HOSPITAL"
        if "ALCALD" in n or n == "MUNICIPIO DE YONDO":
            return "ALCALDIA"
        if "AGUAS" in n or "ACUEDUCTO" in n:
            return "AGUAS"
        return "OTRO"

    def norm(s):
        s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().upper()
        return re.sub(r"\s+", " ", s)

    n0 = len(d)
    d["ent"] = d["nombre_de_la_entidad"].map(ent)
    d["mod"] = d["modalidad_de_contrataci_n"].fillna("").map(norm)
    d = d[d["anio"].notna() & d["valor"].notna() & (d["valor"] > 0)]
    d = d[d["valor"] <= 6e10]
    s1 = d[d.origen == "SECOPI"].drop_duplicates(subset=["ent", "numero_del_contrato", "valor"])
    s2 = d[d.origen == "SECOPII"].sort_values("valor").drop_duplicates(subset=["ent", "numero_del_contrato"], keep="last")
    d = pd.concat([s1, s2])
    d["directa"] = d["mod"].str.contains("DIRECTA|REGIMEN ESPECIAL|DECRETO 092")
    a = d[d.ent == "ALCALDIA"]
    with open(F / "secop_competencia_anual.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["anio", "entidad", "contratos", "valor_pesos", "contratos_sin_competencia",
                    "valor_sin_competencia_pesos", "pct_valor_sin_competencia", "pct_contratos_sin_competencia", "fuente"])
        for anio, x in a.groupby("anio"):
            n, v = len(x), float(x.valor.sum())
            nd, vd = int(x.directa.sum()), float(x[x.directa].valor.sum())
            w.writerow([int(anio), "Alcaldía de Yondó", n, round(v), nd, round(vd), round(100 * vd / v, 2),
                        round(100 * nd / n, 2),
                        "SECOP Integrado, datos.gov.co rpmr-utcd (https://www.datos.gov.co/d/rpmr-utcd), descarga del "
                        "2026-10-20; depuración de scripts/secop_analisis.py; sin competencia = modalidad directa, "
                        "régimen especial o Decreto 092"])
    print(f"secop_competencia_anual.csv: {a.anio.nunique()} años ({n0} registros brutos, {len(d)} depurados)")


# ---------------------------------------------------------------------------
# 2. Carga de insumos del repositorio
# ---------------------------------------------------------------------------
def cargar_ipc():
    cnh = json.loads((D / "comparativa" / "costo_no_hacer.json").read_text(encoding="utf-8"))
    ipc = cnh["series_usadas"]["ipc_dane"]
    mensual = {int(a): v for a, v in ipc["mensual"].items()}
    prom = {a: sum(v) / len(v) for a, v in mensual.items()}
    base = prom[2026]
    assert abs(base - ipc["base_2026"]) < 0.001, "la base 2026 no coincide con costo_no_hacer.json"
    return prom, base, mensual, ipc["fuente"]


def escribir_ipc_csv(prom, base, mensual, fuente):
    with open(F / "ipc_dane.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["anio", "ipc_promedio_anual_base_dic2018_100", "meses_promediados", "ipc_base_2026_igual_1",
                    "factor_a_pesos_2026", "fuente", "nota"])
        for a in sorted(prom):
            nota = ""
            if a == 2026:
                nota = "Base del proyecto: promedio de enero a septiembre de 2026 (158,284)."
            elif a == 2003:
                nota = "Solo para llevar a pesos de 2026 el dato de 2003, que sirve de punto de partida del gobierno 2004-2007."
            w.writerow([a, round(prom[a], 4), len(mensual[a]), round(prom[a] / base, 6), round(base / prom[a], 6),
                        fuente + "; copiado de data/comparativa/costo_no_hacer.json (series_usadas.ipc_dane)", nota])


def cargar_terridata():
    out = {}
    meta = {}
    for x in leer_csv("terridata_panel.csv"):
        out.setdefault((x["clave"], x["codigo_entidad"]), {})[int(x["anio"])] = float(x["valor"])
        if x["codigo_entidad"] == "05893":
            meta[x["clave"]] = (x["fuente_original"], x["unidad"], x["indicador"])
    return out, meta


def cargar_cuipo():
    out = {}
    for x in leer_csv("cuipo_resumen_anual.csv"):
        out[(x["concepto"], int(x["anio"]))] = (float(x["valor_pesos"]), x["anio_completo"] == "sí", x["periodo_corte"])
    return out


# ---------------------------------------------------------------------------
# 3. Construcción
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--actualizar-fuentes", action="store_true", help="descarga y reescribe las fuentes de data/fuentes")
    ap.add_argument("--cache", help="carpeta temporal para las descargas")
    ap.add_argument("--secop-raw", help="ruta a integrado.json de SECOP (opcional)")
    args = ap.parse_args()
    if args.actualizar_fuentes:
        if not args.cache:
            ap.error("--actualizar-fuentes necesita --cache")
        actualizar_terridata(args.cache)
        actualizar_mapa_regalias(args.cache)
        actualizar_cuipo(args.cache)
    if args.secop_raw:
        actualizar_secop(args.secop_raw)

    prom, base, mensual, ipc_fuente = cargar_ipc()
    escribir_ipc_csv(prom, base, mensual, ipc_fuente)

    def a26(v, anio):
        """Pesos corrientes del año -> pesos de 2026 (IPC promedio del año)."""
        return v * base / prom[anio]

    S = json.loads((F / "series_sociales.json").read_text(encoding="utf-8"))
    G = json.loads((D / "gobiernos.json").read_text(encoding="utf-8"))
    SEC = json.loads((D / "secop" / "secop_resumen.json").read_text(encoding="utf-8"))
    OEC = {int(x["anio"]): {k: float(v) for k, v in x.items() if v not in ("", None)} for x in leer_csv("serie_fiscal_oec.csv")}
    SGP = {int(x["anio"]): float(x["Total asignado SGP"]) for x in leer_csv("sgp_sicodis.csv") if x["Total asignado SGP"]}
    TD, TDMETA = cargar_terridata()
    CU = cargar_cuipo()
    SGR = {}
    for x in leer_csv("sgr_distribucion_anual.csv"):
        if x["tipo_recurso"] == "Asignaciones Directas":
            SGR[int(x["vigencia"])] = SGR.get(int(x["vigencia"]), 0.0) + float(x["distribucion_presupuestada_pesos"])
    COMP = {int(x["anio"]): x for x in leer_csv("secop_competencia_anual.csv")}
    IDI = {}
    for x in leer_csv("idi_gobernacion_antioquia.csv"):
        IDI.setdefault(x["indicador"], {})[int(x["anio"])] = float(x["valor"])

    POB = {int(a): float(v) for a, v in S["poblacion_total_dane_base_cnpv2018"]["serie"].items()}
    ss = lambda k: {int(a): float(v) for a, v in S[k]["serie"].items() if v is not None}

    # Fuentes en texto (se repiten en cada indicador)
    F_OEC = ("DNP, Operaciones efectivas de caja con datos del FUT, vía TerriData "
             f"({URL_TD_PERFIL}); data/fuentes/serie_fiscal_oec.csv")
    F_IPC = "deflactado con el IPC DANE (data/fuentes/ipc_dane.csv)"
    F_POB = "población DANE (data/fuentes/series_sociales.json)"
    F_SGP = "DNP-SICODIS, SGP asignado, vía TerriData; data/fuentes/sgp_sicodis.csv"
    F_SGR = "DNP-MapaRegalías, distribución por vigencia (https://www.datos.gov.co/d/h6yd-ei3n); data/fuentes/sgr_distribucion_anual.csv"
    F_CUIPO = ("Contraloría-CUIPO, ejecución de ingresos y gastos (https://www.datos.gov.co/d/9axr-9gnb, "
               "https://www.datos.gov.co/d/4f7r-epif); data/fuentes/cuipo_resumen_anual.csv")
    F_SECOP = ("SECOP I y II (SECOP Integrado, https://www.datos.gov.co/d/rpmr-utcd, descarga del 20-oct-2026), "
               "contratos de la alcaldía depurados con scripts/secop_analisis.py; data/secop/secop_resumen.json")
    F_COMP = F_SECOP.replace("data/secop/secop_resumen.json", "data/fuentes/secop_competencia_anual.csv")
    F_IDI = ("Gobernación de Antioquia, Evaluación del desempeño integral 2014 "
             "(https://www.antioquia.gov.co/images/pdf/Indice%20de%20Desempe%C3%B1o%20Integral%202014.pdf); "
             "data/fuentes/idi_gobernacion_antioquia.csv")

    def f_td(clave):
        fte, _, nombre_td = TDMETA.get(clave, ("", "", ""))
        return f"{fte}, indicador «{nombre_td}» en DNP-TerriData ({URL_TD_PERFIL}); data/fuentes/terridata_panel.csv"

    def f_ss(k):
        return f"{S[k]['fuente']}; data/fuentes/series_sociales.json"

    IND = []

    def add(id_, nombre, area, unidad, fuente, mejor, serie, tipo="nivel", antioquia=None, colombia=None,
            nota=None, parcial=None, nota_parcial=None, cero_vacio=False):
        """serie: {año: valor} con todos los años disponibles (también antes de 2004, para el punto de partida)."""
        assert area in AREAS, area
        limpia = lambda s: {a: v for a, v in (s or {}).items() if v is not None and not (cero_vacio and v == 0)}
        completa = limpia(serie)
        par = {a: v for a, v in (parcial or {}).items() if v is not None}
        ind = {"id": id_, "nombre": nombre, "area": area, "unidad": unidad, "fuente": fuente, "mejor": mejor,
               "tipo": tipo, "serie": {str(a): r(v) for a, v in sorted(completa.items()) if a in ANIOS}}
        for nom, s in (("antioquia", antioquia), ("colombia", colombia)):
            s = {str(a): r(v) for a, v in sorted(limpia(s).items()) if a in ANIOS}
            if s:
                ind[nom] = s
        if par:
            ind["parcial"] = {str(a): r(v) for a, v in sorted(par.items())}
            ind["nota_parcial"] = nota_parcial
        if nota:
            ind["nota"] = nota
        anios = sorted(int(a) for a in ind["serie"])
        ind["cobertura"] = f"{anios[0]}–{anios[-1]} ({len(anios)} años con dato)" if anios else "sin datos"
        ind["_completa"] = completa
        IND.append(ind)
        return ind

    def td(clave, cod="05893", escala=1.0):
        return {a: v * escala for a, v in TD.get((clave, cod), {}).items()}

    def mm26(serie_mm):
        return {a: a26(v, a) for a, v in serie_mm.items() if a in prom}

    def pc26(serie_mm):
        return {a: a26(v, a) * 1e6 / POB[a] for a, v in serie_mm.items() if a in prom and a in POB}

    def col(c, desde=2003):
        return {a: x[c] for a, x in OEC.items() if a >= desde and c in x}

    # ===================================================================== PLATA
    ing = col("ingresos_totales_mm")
    add("ingresos_totales", "Ingresos totales", "Plata", "millones de pesos de 2026", f"{F_OEC}; {F_IPC}", None,
        mm26(ing), tipo="flujo",
        nota="Ingresos de la caja municipal en el año (corrientes y de capital). 2025 y 2026 aún no están publicados en las "
             "operaciones efectivas de caja; para 2023-2025 ver «Ingresos recaudados del presupuesto (CUIPO)».")
    add("ingresos_pc", "Ingresos por habitante", "Plata", "pesos de 2026 por habitante", f"{F_OEC}; {F_POB}; {F_IPC}",
        None, pc26(ing), tipo="flujo")
    reg = col("regalias_giradas_mm_derivado")
    nota_reg = ("Regalías efectivamente giradas a la caja del municipio. Dato derivado: regalías por habitante de TerriData × "
                "población DANE. Desde 2012 incluye los giros del Sistema General de Regalías que entran a la caja.")
    add("regalias", "Regalías que entraron a la caja", "Plata", "millones de pesos de 2026", f"{F_OEC}; {F_IPC}", None,
        mm26(reg), tipo="flujo", nota=nota_reg)
    add("regalias_pc", "Regalías por habitante", "Plata", "pesos de 2026 por habitante", f"{F_OEC}; {F_POB}; {F_IPC}",
        None, pc26(reg), tipo="flujo", nota=nota_reg)
    add("regalias_pct_ingresos", "Peso de las regalías en los ingresos", "Plata", "% de los ingresos totales", F_OEC, None,
        {a: 100 * reg[a] / ing[a] for a in reg if a in ing and ing[a]},
        nota="Cuánto de cada peso que entró a la caja vino de regalías. Mide la dependencia del petróleo.")
    sgr_completo = {a: v / 1e6 for a, v in SGR.items() if a <= 2024}
    add("sgr_asignaciones_directas", "Regalías asignadas por el SGR (asignaciones directas)", "Plata",
        "millones de pesos de 2026", f"{F_SGR}; {F_IPC}", None, mm26(sgr_completo), tipo="flujo",
        parcial={a: a26(v / 1e6, a) for a, v in SGR.items() if a == 2025},
        nota_parcial="2025: distribución registrada hasta agosto de 2025 (última actualización del conjunto de datos).",
        nota="Plata de regalías que el Sistema General de Regalías distribuyó a Yondó para proyectos propios (desde 2012). "
             "Sigue la fecha de las instrucciones de abono, no el presupuesto bienal: por eso no coincide año a año con lo que "
             "entra a la caja.")
    sgp = {a: v / 1e6 for a, v in SGP.items() if a >= 2003}
    add("sgp", "Transferencias de la Nación (SGP)", "Plata", "millones de pesos de 2026", f"{F_SGP}; {F_IPC}", None,
        mm26(sgp), tipo="flujo",
        nota="Sistema General de Participaciones asignado a Yondó (educación, salud, agua, propósito general y asignaciones "
             "especiales; incluye la parte que va al Fonpet). 2025 no está publicado en SICODIS; CUIPO registra $21.291 M "
             "recaudados en 2025 sin Fonpet (no es comparable con esta serie).")
    add("sgp_pc", "Transferencias de la Nación por habitante", "Plata", "pesos de 2026 por habitante",
        f"{F_SGP}; {F_POB}; {F_IPC}", None, pc26(sgp), tipo="flujo")
    trib = col("tributarios_mm")
    if ("tributarios", 2025) in CU and CU[("tributarios", 2025)][1]:
        trib[2025] = CU[("tributarios", 2025)][0] / 1e6
    nota_cu = ("2025 viene de CUIPO (Contraloría): para 2023 y 2024 CUIPO y las operaciones efectivas de caja del DNP dan "
               "exactamente la misma cifra, así que la serie sigue siendo comparable.")
    add("tributarios", "Impuestos propios", "Plata", "millones de pesos de 2026", f"{F_OEC}; 2025: {F_CUIPO}; {F_IPC}", "alto",
        mm26(trib), tipo="flujo",
        nota="Recaudo tributario del municipio: industria y comercio, predial, estampillas, sobretasa a la gasolina y otros. "
             + nota_cu)
    add("tributarios_pc", "Impuestos propios por habitante", "Plata", "pesos de 2026 por habitante",
        f"{F_OEC}; 2025: {F_CUIPO}; {F_POB}; {F_IPC}", "alto", pc26(trib), tipo="flujo", nota=nota_cu)
    add("predial_pc", "Impuesto predial por habitante", "Plata", "pesos de 2026 por habitante", f"{F_OEC}; {F_IPC}", "alto",
        pc26(col("predial_mm_derivado")), tipo="flujo",
        nota="Dato derivado: predial por habitante de TerriData. El catastro de Yondó figura desactualizado (IGAC, 2024).")
    add("ica_pc", "Impuesto de industria y comercio por habitante", "Plata", "pesos de 2026 por habitante",
        f"{F_OEC}; {F_IPC}", "alto", pc26(col("ica_mm_derivado")), tipo="flujo",
        nota="Dato derivado: industria y comercio por habitante de TerriData. Casi todo viene de actividades de servicios "
             "ligadas al petróleo (CUIPO).")
    inv = col("inversion_mm")
    add("inversion", "Inversión", "Plata", "millones de pesos de 2026", f"{F_OEC}; {F_IPC}", "alto", mm26(inv), tipo="flujo",
        nota="Gastos de capital (inversión) pagados en el año según las operaciones efectivas de caja. Para 2023-2025 ver "
             "también «Inversión comprometida del presupuesto (CUIPO)».")
    add("inversion_pc", "Inversión por habitante", "Plata", "pesos de 2026 por habitante", f"{F_OEC}; {F_POB}; {F_IPC}",
        "alto", pc26(inv), tipo="flujo")
    func = col("funcionamiento_mm")
    if ("funcionamiento", 2025) in CU and CU[("funcionamiento", 2025)][1]:
        func[2025] = CU[("funcionamiento", 2025)][0] / 1e6
    add("funcionamiento", "Gastos de funcionamiento", "Plata", "millones de pesos de 2026",
        f"{F_OEC}; 2025: {F_CUIPO}; {F_IPC}", None, mm26(func), tipo="flujo",
        nota="Nómina de planta, gastos generales y transferencias para que la alcaldía funcione (no incluye contratos de "
             "prestación de servicios cargados a inversión). " + nota_cu)
    add("funcionamiento_pc", "Funcionamiento por habitante", "Plata", "pesos de 2026 por habitante",
        f"{F_OEC}; 2025: {F_CUIPO}; {F_POB}; {F_IPC}", None, pc26(func), tipo="flujo", nota=nota_cu)
    gt = col("gastos_totales_mm")
    add("funcionamiento_pct_gasto", "Peso del funcionamiento en el gasto", "Plata", "% del gasto total", F_OEC, "bajo",
        {a: 100 * col("funcionamiento_mm")[a] / gt[a] for a in gt if gt[a]},
        nota="Entre más bajo, más plata queda para inversión.")
    intr = col("intereses_deuda_mm")
    if ("compromisos_total", 2025) in CU and CU[("compromisos_total", 2025)][1]:
        intr[2025] = CU.get(("servicio_deuda", 2025), (0.0,))[0] / 1e6
    nota_deuda = ("2020-2025 sin intereses: el municipio no tenía deuda. 2025: CUIPO no registra compromisos de servicio de la "
                  "deuda. El presupuesto de 2026 incluye por primera vez $1.718,5 M de servicio de deuda (CUIPO, sin "
                  "compromisos a junio de 2026).")
    add("intereses_deuda", "Intereses de la deuda", "Plata", "millones de pesos de 2026", f"{F_OEC}; 2025: {F_CUIPO}; {F_IPC}",
        "bajo", mm26(intr), tipo="flujo", nota=nota_deuda)
    add("intereses_deuda_pc", "Intereses de la deuda por habitante", "Plata", "pesos de 2026 por habitante",
        f"{F_OEC}; 2025: {F_CUIPO}; {F_POB}; {F_IPC}", "bajo", pc26(intr), tipo="flujo", nota=nota_deuda)
    add("deficit_superavit", "Déficit (−) o superávit (+) del año", "Plata", "millones de pesos de 2026",
        f"{f_td('oec_deficit')}; {F_IPC}", "alto", mm26({a: v for a, v in td("oec_deficit").items() if a >= 2003}),
        tipo="flujo", nota="Ingresos menos gastos del año en la caja. Un déficit se cubre con saldos de años anteriores o con crédito.")
    add("inversion_recursos_propios", "Inversión pagada con recursos propios", "Plata", "% de la inversión",
        f_td("inv_recursos_propios"), "alto", td("inv_recursos_propios"),
        nota="Parte de la inversión que se financió con impuestos y rentas propias del municipio (no con regalías ni SGP).")
    cu_rec = {a: v[0] / 1e6 for (c, a), v in CU.items() if c == "recaudo_total" and v[1]}
    cu_rec_p = {a: a26(v[0] / 1e6, a) for (c, a), v in CU.items() if c == "recaudo_total" and not v[1]}
    add("cuipo_recaudo", "Ingresos recaudados del presupuesto (CUIPO)", "Plata", "millones de pesos de 2026",
        f"{F_CUIPO}; {F_IPC}", None, mm26(cu_rec), tipo="flujo", parcial=cu_rec_p,
        nota_parcial="2026: recaudo acumulado a junio.",
        nota="Recaudo total del presupuesto ordinario reportado por el municipio a la Contraloría. No incluye el presupuesto "
             "bienal de regalías (SGR) y no es igual a los ingresos de caja del DNP: no se deben sumar ni mezclar.")
    cu_inv = {a: v[0] / 1e6 for (c, a), v in CU.items() if c == "inversion" and v[1]}
    cu_inv_p = {a: a26(v[0] / 1e6, a) for (c, a), v in CU.items() if c == "inversion" and not v[1]}
    add("cuipo_inversion", "Inversión comprometida del presupuesto (CUIPO)", "Plata", "millones de pesos de 2026",
        f"{F_CUIPO}; {F_IPC}", "alto", mm26(cu_inv), tipo="flujo", parcial=cu_inv_p,
        nota_parcial="2026: compromisos acumulados a junio.",
        nota="Compromisos de inversión de la vigencia en el presupuesto ordinario (sin regalías del SGR).")

    # ===================================================================== GESTIÓN
    pts = "puntos (0 a 100)"
    add("idf", "Desempeño fiscal (método hasta 2020)", "Gestión", pts, f_td("idf"), "alto", td("idf"), cero_vacio=True,
        nota="Índice de Desempeño Fiscal del DNP con la metodología vigente hasta 2020. No se compara con el método nuevo.")
    add("idf_nuevo", "Desempeño fiscal (método nuevo, desde 2020)", "Gestión", pts, f_td("idf_nuevo"), "alto",
        td("idf_nuevo"), cero_vacio=True,
        nota="Nuevo Índice de Desempeño Fiscal del DNP (resultados fiscales y gestión financiera). Yondó queda en el rango "
             "«vulnerable» en todos los años.")
    add("mdm", "Desempeño municipal (MDM)", "Gestión", pts, f_td("mdm"), "alto", td("mdm"), cero_vacio=True,
        nota="Medición de Desempeño Municipal del DNP: promedio de gestión y resultados. Empezó en 2016.")
    add("mdm_gestion", "MDM: gestión", "Gestión", pts, f_td("mdm_gestion"), "alto", td("mdm_gestion"), cero_vacio=True)
    add("mdm_resultados", "MDM: resultados", "Gestión", pts, f_td("mdm_resultados"), "alto", td("mdm_resultados"),
        cero_vacio=True)
    add("mdm_movilizacion", "MDM: capacidad para recaudar recursos", "Gestión", pts, f_td("mdm_movilizacion"), "alto",
        td("mdm_movilizacion"))
    add("mdm_ejecucion", "MDM: ejecución de recursos", "Gestión", pts, f_td("mdm_ejecucion"), "alto", td("mdm_ejecucion"))
    add("mdm_ordenamiento", "MDM: recaudo con instrumentos de ordenamiento territorial", "Gestión", pts, f_td("mdm_ot"),
        "alto", td("mdm_ot"))
    add("mdm_gobierno_abierto", "MDM: gobierno abierto y transparencia", "Gestión", pts, f_td("mdm_gobierno_abierto"),
        "alto", td("mdm_gobierno_abierto"))
    add("idi", "Desempeño integral (IDI)", "Gestión", pts, F_IDI, "alto", IDI.get("idi", {}),
        nota="Índice de Desempeño Integral (DNP, 2006-2015). Solo se encontró el dato de 2014 (67,3, nivel «medio»; eficacia "
             "44,7, eficiencia 46,77, requisitos legales 90,82, gestión 86,9). Los demás años no están publicados en datos "
             "abiertos.")
    add("idi_capacidad_administrativa", "Capacidad administrativa (evaluación integral)", "Gestión", pts, F_IDI, "alto",
        IDI.get("capacidad_administrativa", {}), nota="Componente del Índice de Desempeño Integral.")
    add("igpr", "Gestión de proyectos de regalías (IGPR)", "Gestión", pts, f_td("igpr"), "alto", td("igpr"),
        nota="Índice de Gestión de Proyectos de Regalías del DNP; se toma el último trimestre con dato de cada año.")
    add("igpr_nuevo", "Gestión de proyectos de regalías (IGPR, método nuevo)", "Gestión", pts, f_td("igpr_nuevo"), "alto",
        td("igpr_nuevo"), nota="Metodología nueva del DNP desde 2020; no se compara con la anterior.")
    nota_sector = ("Inversión por sector reportada al FUT (DNP vía TerriData). TerriData la rotula en millones, pero las cifras "
                   "vienen en pesos; aquí se pasaron a millones. 2019 no está publicado y la serie termina en 2020.")
    inv_sec = lambda k: mm26(td(k, escala=1e-6))
    add("inv_fortalecimiento", "Inversión en fortalecimiento institucional", "Gestión", "millones de pesos de 2026",
        f"{f_td('inv_fortalecimiento')}; {F_IPC}", None, inv_sec("inv_fortalecimiento"), tipo="flujo", nota=nota_sector)

    # ===================================================================== CONTRATACIÓN
    alc = {}
    cats = {}
    for x in SEC["anual"]:
        if x["ent"] != "ALCALDIA":
            continue
        a = int(x["anio"])
        alc.setdefault(a, [0, 0.0])
        alc[a][0] += x["n"]
        alc[a][1] += x["valor"]
        cats.setdefault(x["categoria"], {})
        cats[x["categoria"]][a] = cats[x["categoria"]].get(a, 0.0) + x["valor"]
    ops = {int(x["anio"]): x for x in SEC["ops_anual"] if x["ent"] == "ALCALDIA"}
    PAR_SECOP = {2007, 2026}
    nota_par_secop = ("2007: SECOP casi no tiene registros (41 contratos), el dato no representa el año. "
                      "2026: contratos firmados hasta el 20 de octubre.")
    nota_secop = ("Contratos firmados por la alcaldía (no incluye Aguas de Yondó ni el hospital). Antes de 2008 SECOP no tiene "
                  "registros suficientes.")

    def sec(serie, fn=lambda a, v: v):
        full = {a: fn(a, v) for a, v in serie.items() if a not in PAR_SECOP}
        par = {a: fn(a, v) for a, v in serie.items() if a in PAR_SECOP}
        return full, par

    s, p = sec({a: v[1] / 1e6 for a, v in alc.items()}, lambda a, v: a26(v, a))
    add("secop_valor", "Valor contratado por la alcaldía", "Contratación", "millones de pesos de 2026", f"{F_SECOP}; {F_IPC}",
        None, s, tipo="flujo", parcial=p, nota_parcial=nota_par_secop, nota=nota_secop)
    s, p = sec({a: v[1] / 1e6 for a, v in alc.items()}, lambda a, v: a26(v, a) * 1e6 / POB[a])
    add("secop_valor_pc", "Valor contratado por habitante", "Contratación", "pesos de 2026 por habitante",
        f"{F_SECOP}; {F_POB}; {F_IPC}", None, s, tipo="flujo", parcial=p, nota_parcial=nota_par_secop)
    s, p = sec({a: v[0] for a, v in alc.items()})
    add("secop_contratos", "Contratos firmados por la alcaldía", "Contratación", "contratos", F_SECOP, None, s, tipo="flujo",
        parcial=p, nota_parcial=nota_par_secop)
    s, p = sec({a: float(x["pct_valor_sin_competencia"]) for a, x in COMP.items()})
    add("secop_sin_competencia_valor", "Valor contratado sin competencia", "Contratación", "% del valor contratado", F_COMP,
        "bajo", s, parcial=p, nota_parcial=nota_par_secop,
        nota="Modalidades sin concurso abierto de oferentes: contratación directa, régimen especial y convenios con entidades "
             "sin ánimo de lucro (Decreto 092 de 2017), con la misma regla de scripts/secop_analisis.py. Al agregar por "
             "gobierno da lo mismo que data/secop/secop_resumen.json (directa_por_periodo).")
    s, p = sec({a: float(x["pct_contratos_sin_competencia"]) for a, x in COMP.items()})
    add("secop_sin_competencia_contratos", "Contratos firmados sin competencia", "Contratación", "% de los contratos", F_COMP,
        "bajo", s, parcial=p, nota_parcial=nota_par_secop)
    s, p = sec({a: float(x["n"]) for a, x in ops.items()})
    add("ops_contratos", "Contratos de prestación de servicios (OPS)", "Contratación", "contratos", F_SECOP, None, s,
        tipo="flujo", parcial=p, nota_parcial=nota_par_secop,
        nota="Órdenes de prestación de servicios y contratos de apoyo a la gestión con personas (scripts/secop_analisis.py).")
    s, p = sec({a: x["valor"] / 1e6 for a, x in ops.items()}, lambda a, v: a26(v, a))
    add("ops_valor", "Valor de los contratos OPS", "Contratación", "millones de pesos de 2026", f"{F_SECOP}; {F_IPC}", None,
        s, tipo="flujo", parcial=p, nota_parcial=nota_par_secop)
    s, p = sec({a: float(x["personas"]) for a, x in ops.items()})
    add("ops_personas", "Personas con contrato OPS", "Contratación", "personas distintas en el año", F_SECOP, None, s,
        tipo="flujo", parcial=p, nota_parcial=nota_par_secop)
    s, p = sec({a: 100 * ops[a]["valor"] / alc[a][1] for a in ops if a in alc and alc[a][1]})
    add("ops_pct_valor", "Peso de las OPS en lo contratado", "Contratación", "% del valor contratado", F_SECOP, "bajo", s,
        parcial=p, nota_parcial=nota_par_secop,
        nota="Un peso alto indica una nómina paralela por contrato en lugar de planta de personal.")
    for cid, cat, nombre in (("secop_obra", "Obra", "Valor contratado en obra"),
                             ("secop_estudios", "Estudios / consultoría", "Valor en estudios, diseños y consultorías"),
                             ("secop_convenios", "Convenios / interadministrativos",
                              "Valor en convenios y contratos interadministrativos")):
        s, p = sec({a: v / 1e6 for a, v in cats.get(cat, {}).items()}, lambda a, v: a26(v, a))
        add(cid, nombre, "Contratación", "millones de pesos de 2026", f"{F_SECOP}; {F_IPC}", None, s, tipo="flujo",
            parcial=p, nota_parcial=nota_par_secop,
            nota="Categoría asignada por tipo de contrato, modalidad y palabras del objeto (scripts/secop_analisis.py)."
            + (" Incluye los $84.016 M con la EDU de Medellín en 2021-2023." if cid == "secop_convenios" else ""))

    # ===================================================================== AGUA Y SANEAMIENTO
    nota_rec = ("Reporte de Estratificación y Coberturas (REC) que el municipio entrega a la Superservicios. La serie tiene "
                "saltos que no son creíbles (por ejemplo 91 % en 2012 y 16 % en 2013-2015): son errores de reporte. Usar "
                "con cautela. Un cero se trata como dato faltante.")
    pct = "% de viviendas"
    for k, nombre in (("acueducto_total", "Cobertura de acueducto"),
                      ("acueducto_urbana", "Cobertura de acueducto en el casco urbano"),
                      ("acueducto_rural", "Cobertura de acueducto rural"),
                      ("alcantarillado_total", "Cobertura de alcantarillado"),
                      ("alcantarillado_urbana", "Cobertura de alcantarillado en el casco urbano"),
                      ("alcantarillado_rural", "Cobertura de alcantarillado rural"),
                      ("aseo_total", "Cobertura de aseo (recolección de basuras)")):
        add(k, nombre, "Agua y saneamiento", pct, f_td(k), "alto", td(k), antioquia=td(k, "05000"),
            colombia=td(k, "01001"), nota=nota_rec, cero_vacio=True)
    for k, nombre in (("acueducto_censo", "Viviendas con acueducto (censo)"),
                      ("alcantarillado_censo", "Viviendas con alcantarillado (censo)")):
        add(k, nombre, "Agua y saneamiento", pct, f_td(k), "alto", td(k), antioquia=td(k, "05000"),
            colombia=td(k, "01001"), cero_vacio=True,
            nota="Censos del DANE de 2005 y 2018: la medida más confiable, pero solo hay dos puntos.")
    nota_irca = "IRCA: 0 a 5 = sin riesgo; 5,1 a 14 = bajo; 14,1 a 35 = medio; 35,1 a 80 = alto; más de 80 = inviable sanitariamente."
    add("irca_total", "Riesgo en la calidad del agua (IRCA)", "Agua y saneamiento", "puntos IRCA (0 a 100)",
        f_ss("irca_total"), "bajo", ss("irca_total"), antioquia=ss("irca_total_antioquia"), nota=nota_irca)
    add("irca_urbano", "Riesgo en la calidad del agua en el casco urbano", "Agua y saneamiento", "puntos IRCA (0 a 100)",
        f_ss("irca_urbano"), "bajo", ss("irca_urbano"), nota=nota_irca)
    add("irca_rural", "Riesgo en la calidad del agua rural", "Agua y saneamiento", "puntos IRCA (0 a 100)",
        f_ss("irca_rural"), "bajo", ss("irca_rural"), nota=nota_irca + " " + S["irca_rural"].get("nota", ""))
    add("inv_agua", "Inversión en agua potable y saneamiento", "Agua y saneamiento", "millones de pesos de 2026",
        f"{f_td('inv_agua')}; {F_IPC}", "alto", inv_sec("inv_agua"), tipo="flujo", nota=nota_sector)
    add("mdm_servicios", "MDM: resultados en servicios públicos", "Agua y saneamiento", pts, f_td("mdm_servicios"), "alto",
        td("mdm_servicios"), nota="Componente de resultados de la Medición de Desempeño Municipal (acueducto, alcantarillado, "
                                  "energía e internet).")

    # ===================================================================== EDUCACIÓN
    edu = [("cob_neta", "Cobertura neta en educación (transición a once)", "% de niños y jóvenes en edad escolar", "alto"),
           ("cob_bruta", "Cobertura bruta en educación", "% (puede pasar de 100)", None),
           ("cob_neta_transicion", "Cobertura neta en transición (preescolar)", "%", "alto"),
           ("cob_neta_secundaria", "Cobertura neta en secundaria", "%", "alto"),
           ("cob_neta_media", "Cobertura neta en media (décimo y once)", "%", "alto"),
           ("desercion_oficial", "Deserción escolar en colegios oficiales", "% de estudiantes que dejan el colegio en el año",
            "bajo"),
           ("repitencia_oficial", "Repitencia en colegios oficiales", "% de estudiantes", "bajo"),
           ("transito_superior", "Bachilleres que entran de inmediato a la educación superior", "% de bachilleres", "alto"),
           ("saber11_mat", "Saber 11: matemáticas", "puntaje promedio (0 a 100)", "alto"),
           ("saber11_lec", "Saber 11: lectura crítica", "puntaje promedio (0 a 100)", "alto")]
    for k, nombre, unidad, mejor in edu:
        nota = None
        if k == "cob_bruta":
            nota = "Compara la matrícula total con la población en edad escolar; pasa de 100 cuando hay estudiantes en extraedad."
        add(k, nombre, "Educación", unidad, f_td(k), mejor, td(k), antioquia=td(k, "05000"), colombia=td(k, "01001"),
            cero_vacio=k.startswith("cob") or k.startswith("saber"), nota=nota)
    add("saber11_global", "Saber 11: puntaje global", "Educación", "puntaje promedio (0 a 500)",
        f_ss("saber11_puntaje_global_yondo"), "alto", ss("saber11_puntaje_global_yondo"),
        nota=S["saber11_puntaje_global_yondo"].get("nota"))
    add("matricula", "Estudiantes matriculados", "Educación", "estudiantes", f_ss("matricula_total_establecimientos"), None,
        ss("matricula_total_establecimientos"))
    add("inv_educacion", "Inversión en educación", "Educación", "millones de pesos de 2026",
        f"{f_td('inv_educacion')}; {F_IPC}", "alto", inv_sec("inv_educacion"), tipo="flujo", nota=nota_sector)
    add("mdm_educacion", "MDM: resultados en educación", "Educación", pts, f_td("mdm_educacion"), "alto", td("mdm_educacion"))

    # ===================================================================== SALUD
    salud = [("mort_infantil", "Mortalidad infantil (menores de 1 año)", "muertes por cada 1.000 nacidos vivos", "bajo", None),
             ("mort_menor5", "Mortalidad en menores de 5 años", "muertes por cada 1.000 nacidos vivos", "bajo", None),
             ("mort_neonatal", "Mortalidad neonatal (primer mes de vida)", "muertes por cada 1.000 nacidos vivos", "bajo", None),
             ("mort_materna", "Mortalidad materna", "muertes por cada 100.000 nacidos vivos", "bajo",
              "Con 250 a 330 nacimientos al año, una sola muerte materna da 300 a 400 por 100.000. Los años vacíos son años "
              "sin dato publicado."),
             ("vac_pentavalente", "Vacunación pentavalente (menores de 1 año)", "% de niños", "alto",
              "Puede pasar de 100 o caer de golpe por cambios en la población de referencia (desde 2020 usa la proyección del "
              "censo 2018)."),
             ("vac_triple_viral", "Vacunación triple viral (1 año)", "% de niños", "alto", None),
             ("bajo_peso", "Bebés con bajo peso al nacer", "% de nacidos vivos", "bajo", None),
             ("prenatal4", "Bebés cuyas madres tuvieron 4 o más controles prenatales", "% de nacidos vivos", "alto", None),
             ("partos_calificados", "Partos atendidos por personal calificado", "% de partos", "alto", None),
             ("madres_14_17", "Bebés de madres de 14 a 17 años", "% de nacidos vivos", "bajo", None),
             ("fecundidad_15_19", "Embarazo adolescente (15 a 19 años)", "nacimientos por cada 1.000 mujeres de 15 a 19 años",
              "bajo", None),
             ("dengue", "Dengue", "casos por cada 100.000 habitantes en riesgo", "bajo", None),
             ("tuberculosis", "Tuberculosis", "casos por cada 100.000 habitantes", "bajo", None),
             ("reg_subsidiado", "Cobertura del régimen subsidiado", "%", None,
              "El salto de 2017 a 2018 (de 98 % a 54 %) se debe al cambio de la población de referencia (censo 2018), no a una "
              "pérdida de afiliados; por eso no se califica si mejoró o empeoró.")]
    for k, nombre, unidad, mejor, nota in salud:
        add(k, nombre, "Salud", unidad, f_td(k), mejor, td(k), antioquia=td(k, "05000"), colombia=td(k, "01001"),
            cero_vacio=k in ("vac_pentavalente", "vac_triple_viral", "prenatal4", "partos_calificados", "reg_subsidiado"),
            nota=nota)
    add("inv_salud", "Inversión en salud", "Salud", "millones de pesos de 2026", f"{f_td('inv_salud')}; {F_IPC}", None,
        inv_sec("inv_salud"), tipo="flujo", nota=nota_sector + " Incluye el régimen subsidiado que se paga con el SGP.")
    add("mdm_salud", "MDM: resultados en salud", "Salud", pts, f_td("mdm_salud"), "alto", td("mdm_salud"))

    # ===================================================================== SEGURIDAD Y CONFLICTO
    t100 = "por cada 100.000 habitantes"
    add("homicidio_tasa", "Homicidios por 100.000 habitantes", "Seguridad y conflicto", t100, f_td("homicidio_tasa"), "bajo",
        td("homicidio_tasa"), antioquia=td("homicidio_tasa", "05000"), colombia=td("homicidio_tasa", "01001"))
    hn = ss("homicidios_numero_mindefensa")
    add("homicidios", "Homicidios (número de casos)", "Seguridad y conflicto", "homicidios",
        f_ss("homicidios_numero_mindefensa"), "bajo", {a: v for a, v in hn.items() if a <= 2025}, tipo="flujo",
        parcial={a: v for a, v in hn.items() if a == 2026}, nota_parcial="2026: enero a agosto.")
    add("extorsion", "Extorsión por 100.000 habitantes", "Seguridad y conflicto", t100, f_td("extorsion"), "bajo",
        td("extorsion"), antioquia=td("extorsion", "05000"), colombia=td("extorsion", "01001"),
        nota="Casos denunciados; muchos no se denuncian.")
    add("hurto_personas", "Hurto a personas por 100.000 habitantes", "Seguridad y conflicto", t100, f_td("hurto_personas"),
        "bajo", td("hurto_personas"), antioquia=td("hurto_personas", "05000"), colombia=td("hurto_personas", "01001"),
        nota="Casos denunciados.")
    nota_den = ("Casos denunciados. Más casos pueden significar más violencia o más denuncias (mejor acceso a la justicia); "
                "por eso no se califica si mejoró o empeoró.")
    add("violencia_intrafamiliar", "Violencia intrafamiliar por 100.000 habitantes", "Seguridad y conflicto", t100,
        f_td("vif"), None, td("vif"), antioquia=td("vif", "05000"), colombia=td("vif", "01001"), nota=nota_den)
    add("delitos_sexuales", "Delitos sexuales por 100.000 habitantes", "Seguridad y conflicto", t100,
        f_td("delitos_sexuales"), None, td("delitos_sexuales"), antioquia=td("delitos_sexuales", "05000"),
        colombia=td("delitos_sexuales", "01001"), nota=nota_den)
    vr = ss("victimas_ruv_por_ocurrencia")
    add("victimas_conflicto", "Personas víctimas del conflicto en el año", "Seguridad y conflicto", "personas",
        f_ss("victimas_ruv_por_ocurrencia"), "bajo", {a: v for a, v in vr.items() if a <= 2025}, tipo="flujo",
        parcial={a: v for a, v in vr.items() if a == 2026}, nota_parcial="2026: corte al 30 de septiembre.",
        nota=S["victimas_ruv_por_ocurrencia"].get("nota"))
    dz = ss("desplazamiento_expulsion_ruv")
    add("desplazamiento", "Personas desplazadas desde Yondó", "Seguridad y conflicto", "personas",
        f_ss("desplazamiento_expulsion_ruv"), "bajo", {a: v for a, v in dz.items() if a <= 2025}, tipo="flujo",
        parcial={a: v for a, v in dz.items() if a == 2026}, nota_parcial="2026: corte al 30 de septiembre.")
    add("minas", "Eventos con minas antipersonal", "Seguridad y conflicto", "eventos", f_td("minas"), "bajo", td("minas"),
        tipo="flujo")
    add("coca", "Cultivos de coca", "Seguridad y conflicto", "hectáreas", f_td("coca"), "bajo", td("coca"))
    add("iica", "Incidencia del conflicto armado (IICA)", "Seguridad y conflicto", "índice (0 a 1)", f_td("iica"), "bajo",
        td("iica"), nota=S["indice_incidencia_conflicto_armado_IICA"].get("nota"))
    add("inv_seguridad", "Inversión en justicia y seguridad", "Seguridad y conflicto", "millones de pesos de 2026",
        f"{f_td('inv_seguridad')}; {F_IPC}", None, inv_sec("inv_seguridad"), tipo="flujo", nota=nota_sector)
    add("mdm_seguridad", "MDM: resultados en seguridad", "Seguridad y conflicto", pts, f_td("mdm_seguridad"), "alto",
        td("mdm_seguridad"))

    # ===================================================================== ECONOMÍA
    va = td("va")  # miles de millones corrientes
    nota_va = ("Valor agregado municipal del DANE (base 2015). Se llevó a pesos de 2026 con el IPC: es una aproximación, porque "
               "el valor de la producción petrolera sigue el precio del crudo y no los precios al consumidor.")
    add("valor_agregado", "Tamaño de la economía (valor agregado)", "Economía", "millones de pesos de 2026",
        f"{f_td('va')}; {F_IPC}", "alto", {a: a26(v * 1000, a) for a, v in va.items() if a in prom}, tipo="flujo", nota=nota_va)
    add("valor_agregado_pc", "Valor agregado por habitante", "Economía", "pesos de 2026 por habitante",
        f"{f_td('va')}; {F_POB}; {F_IPC}", "alto", {a: a26(v * 1e9, a) / POB[a] for a, v in va.items() if a in prom and a in POB},
        tipo="flujo", nota=nota_va + " Cálculo propio: valor agregado ÷ población DANE.")
    add("valor_agregado_pc_vs_pais", "Valor agregado por habitante frente al país", "Economía",
        "% del promedio nacional (100 = igual al país)", f_td("va_pc_vs_pais"), None, td("va_pc_vs_pais"),
        nota="Alto por la producción de petróleo, que no se queda en los hogares del municipio.")
    add("peso_actividades_primarias", "Peso del petróleo, la minería y el agro en la economía", "Economía",
        "% del valor agregado", f_td("va_primarias"), None, td("va_primarias"),
        nota=S["participacion_actividades_primarias_en_VA"].get("nota"))
    add("produccion_crudo", "Producción de petróleo", "Economía", "barriles por día (promedio del año)",
        f_ss("produccion_crudo_fiscalizada_bpd"), None, ss("produccion_crudo_fiscalizada_bpd"),
        nota=S["produccion_crudo_fiscalizada_bpd"].get("nota"))
    add("ganado_bovino", "Ganado bovino", "Economía", "cabezas", f_ss("inventario_bovino"), None, ss("inventario_bovino"))
    add("cotizantes", "Trabajadores que cotizan a seguridad social", "Economía", "trabajadores (promedio mensual)",
        f_td("cotizantes"), "alto", td("cotizantes"), cero_vacio=True)
    add("empleo_formal", "Personas con empleo formal", "Economía", "% de la población", f_td("empleo_formal"), "alto",
        td("empleo_formal"), colombia={a: v for a, v in td("empleo_formal", "01001").items() if a <= 2016},
        cero_vacio=True, nota="FILCO (Ministerio del Trabajo). Colombia se muestra solo hasta 2016: después cambia el método.")
    add("inv_agro", "Inversión en el sector agropecuario", "Economía", "millones de pesos de 2026",
        f"{f_td('inv_agro')}; {F_IPC}", "alto", inv_sec("inv_agro"), tipo="flujo", nota=nota_sector)
    add("inv_transporte", "Inversión en vías y transporte", "Economía", "millones de pesos de 2026",
        f"{f_td('inv_transporte')}; {F_IPC}", None, inv_sec("inv_transporte"), tipo="flujo", nota=nota_sector)

    # ===================================================================== CONECTIVIDAD Y ENERGÍA
    add("internet_fijo", "Accesos a internet fijo por cada 100 habitantes", "Conectividad y energía", "accesos por cada 100 "
        "habitantes", f_td("internet_fijo"), "alto", td("internet_fijo"), antioquia=td("internet_fijo", "05000"),
        colombia=td("internet_fijo", "01001"), cero_vacio=True, nota="Último trimestre publicado de cada año.")
    add("accesos_internet", "Conexiones de internet fijo", "Conectividad y energía", "accesos",
        f_ss("accesos_internet_fijo"), "alto", ss("accesos_internet_fijo"), nota=S["accesos_internet_fijo"].get("nota"))
    nota_en = "Índice de Cobertura de Energía Eléctrica (UPME). Serie volátil por cambios en el número de viviendas de referencia."
    for k, nombre in (("energia_rural", "Cobertura de energía eléctrica rural"),
                      ("energia_total", "Cobertura de energía eléctrica"),
                      ("energia_urbana", "Cobertura de energía eléctrica en el casco urbano")):
        add(k, nombre, "Conectividad y energía", "% de viviendas", f_td(k), "alto", td(k), antioquia=td(k, "05000"),
            colombia=td(k, "01001"), cero_vacio=True, nota=nota_en)
    add("energia_censo", "Viviendas con energía eléctrica (censo)", "Conectividad y energía", "% de viviendas",
        f_ss("cobertura_energia_censo"), "alto", ss("cobertura_energia_censo"), nota="Censos del DANE de 2005 y 2018.")
    add("gas_censo", "Viviendas con gas natural (censo)", "Conectividad y energía", "% de viviendas",
        f_ss("cobertura_gas_natural_censo"), "alto", ss("cobertura_gas_natural_censo"), nota="Censos del DANE de 2005 y 2018.")
    add("inv_otros_servicios", "Inversión en energía, alumbrado y gas", "Conectividad y energía", "millones de pesos de 2026",
        f"{f_td('inv_otros_servicios')}; {F_IPC}", None, inv_sec("inv_otros_servicios"), tipo="flujo",
        nota=nota_sector + " Corresponde al sector «servicios públicos diferentes a acueducto, alcantarillado y aseo».")

    # ===================================================================== AMBIENTE Y RIESGO
    add("bosque", "Bosque estable", "Ambiente y riesgo", "hectáreas", f_td("bosque"), "alto", td("bosque"),
        nota="IDEAM. Años 2000, 2005, 2010 y 2012 corresponden a mediciones de varios años.")
    defo = td("deforestacion")
    add("deforestacion", "Área deforestada en el año", "Ambiente y riesgo", "hectáreas", f_td("deforestacion"), "bajo",
        {a: v for a, v in defo.items() if a >= 2013}, tipo="flujo",
        nota="IDEAM. Solo se muestran los años con medición anual (2013-2018). Antes: 5.421 ha en 2000-2005, 13.986 ha en "
             "2005-2010 y 2.044 ha en 2010-2012 (mediciones de varios años, no comparables con un año).")
    add("afectados_desastres", "Personas afectadas por desastres", "Ambiente y riesgo", t100, f_td("afectados_desastres"),
        "bajo", td("afectados_desastres"), nota="UNGRD. Muertos, heridos, desaparecidos y afectados por inundaciones y otros "
                                                  "eventos recurrentes. Un cero indica que no se registraron afectados.")
    add("inundaciones", "Inundaciones registradas", "Ambiente y riesgo", "eventos", f_td("inundaciones"), "bajo",
        td("inundaciones"), tipo="flujo")
    add("psa_cuencas", "Ingresos para proteger las cuencas que surten los acueductos", "Ambiente y riesgo",
        "% de los ingresos corrientes", f_td("psa_cuencas"), "alto", td("psa_cuencas"),
        nota="Compra de predios o pago por servicios ambientales en cuencas abastecedoras. La ley (artículo 111 de la Ley 99 "
             "de 1993) pide destinar al menos el 1 % de los ingresos corrientes.")
    add("area_protegida", "Área protegida (SINAP)", "Ambiente y riesgo", "hectáreas", f_td("sinap"), "alto", td("sinap"))
    add("inv_ambiental", "Inversión ambiental", "Ambiente y riesgo", "millones de pesos de 2026",
        f"{f_td('inv_ambiental')}; {F_IPC}", "alto", inv_sec("inv_ambiental"), tipo="flujo", nota=nota_sector)
    add("inv_desastres", "Inversión en prevención y atención de desastres", "Ambiente y riesgo", "millones de pesos de 2026",
        f"{f_td('inv_desastres')}; {F_IPC}", "alto", inv_sec("inv_desastres"), tipo="flujo", nota=nota_sector)

    # ===================================================================== PERIODOS
    ind_by = {i["id"]: i for i in IND}

    def comparar(ini, fin, mejor):
        if ini is None or fin is None:
            return None, "sin datos"
        if fin == ini:
            return None, "igual"
        if mejor is None:
            return None, "subió" if fin > ini else "bajó"
        bueno = (fin > ini) == (mejor == "alto")
        return bueno, "mejoró" if bueno else "empeoró"

    AGREG = [("ingresos_totales", "Ingresos totales"), ("inversion", "Inversión"), ("regalias", "Regalías que entraron a la caja"),
             ("sgp", "Transferencias de la Nación (SGP)"), ("tributarios", "Impuestos propios"),
             ("funcionamiento", "Gastos de funcionamiento"), ("intereses_deuda", "Intereses de la deuda"),
             ("sgr_asignaciones_directas", "Regalías asignadas por el SGR"), ("secop_valor", "Valor contratado por la alcaldía"),
             ("ops_valor", "Valor de los contratos OPS")]
    periodos = []
    for g in G["periodos"]:
        a0, a1 = int(g["id"][:4]), int(g["id"][5:])
        rango = [a for a in range(a0, a1 + 1) if a in ANIOS]
        agreg = {}
        for k, nombre in AGREG:
            s = ind_by[k]["_completa"]
            con = [a for a in rango if a in s]
            if not con:
                agreg[k] = {"nombre": nombre, "anios_con_dato": [], "suma_mm_2026": None, "promedio_anual_mm_2026": None,
                            "por_habitante_al_anio_2026": None}
                continue
            suma = sum(s[a] for a in con)
            agreg[k] = {"nombre": nombre, "anios_con_dato": con, "suma_mm_2026": r(suma),
                        "promedio_anual_mm_2026": r(suma / len(con)),
                        "por_habitante_al_anio_2026": round(suma * 1e6 / sum(POB[a] for a in con)),
                        "por_habitante_en_el_periodo_2026": round(sum(s[a] * 1e6 / POB[a] for a in con))}
            if [a for a in rango if a not in s]:
                agreg[k]["anios_sin_dato"] = [a for a in rango if a not in s]
        res = {}
        balance = {ar: {"mejoró": 0, "empeoró": 0, "igual": 0, "sin datos": 0} for ar in AREAS}
        for i in IND:
            s = i["_completa"]
            antes = [a for a in s if a < a0]
            dentro = [a for a in s if a0 <= a <= a1 and a in ANIOS]
            fin = max(dentro) if dentro else None
            if antes:
                ini, regla = max(antes), "último dato antes del periodo"
            elif dentro and min(dentro) < fin:
                ini, regla = min(dentro), "primer dato del periodo (no hay dato anterior)"
            else:
                ini, regla = None, None
            vi = s[ini] if ini is not None else None
            vf = s[fin] if fin is not None else None
            if fin is None:
                vi = None
            bueno, resultado = comparar(vi, vf, i["mejor"])
            e = {"inicio": {"anio": ini, "valor": r(vi), "regla": regla} if ini is not None and fin is not None else None,
                 "final": {"anio": fin, "valor": r(vf)} if fin is not None else None,
                 "cambio": r(vf - vi) if vi is not None and vf is not None else None,
                 "cambio_pct": (round(100 * (vf - vi) / abs(vi), 1) if vi not in (None, 0) and vf is not None else None),
                 "mejoro": bueno, "resultado": resultado,
                 "promedio_periodo": r(statistics.fmean(s[a] for a in dentro)) if dentro else None,
                 "anios_con_dato": len(dentro)}
            if i["tipo"] == "flujo" and dentro:
                e["suma_periodo"] = r(sum(s[a] for a in dentro))
            for nom in ("antioquia", "colombia"):
                if fin is not None and str(fin) in i.get(nom, {}):
                    e[f"{nom}_final"] = i[nom][str(fin)]
            res[i["id"]] = e
            if i["mejor"]:
                balance[i["area"]][resultado if resultado in balance[i["area"]] else "sin datos"] += 1
        periodos.append({
            "id": g["id"], "alcalde": g["alcalde"], "anios": rango,
            "nota": ("Periodo en curso: la plata solo tiene 2024 completo en las operaciones de caja (impuestos y funcionamiento "
                     "llegan a 2025 con CUIPO); la contratación llega a 2025 completo." if a0 == 2024 else
                     "SECOP casi no tiene registros de estos años: la contratación no se puede comparar." if a0 == 2004 else None),
            "agregados": agreg,
            "balance_por_area": balance,
            "indicadores": res,
        })

    # ===================================================================== SALIDA
    for i in IND:
        i.pop("_completa")
    vacios = [
        "Plata: las operaciones efectivas de caja del DNP llegan hasta 2024. 2025 solo tiene impuestos, funcionamiento e "
        "intereses (CUIPO) y el recaudo y la inversión del presupuesto ordinario (CUIPO 2023-2025); 2026 va parcial a junio.",
        "Plata: el SGP de 2025 y 2026 no está publicado en SICODIS; las regalías asignadas por el SGR (MapaRegalías) llegan a "
        "agosto de 2025.",
        "Plata y sectores: la inversión por sector del FUT (TerriData) cubre 2011-2020 y no tiene 2019; de 2021 en adelante "
        "CUIPO usa otra clasificación por sectores y no se mezcló.",
        "Gestión: del Índice de Desempeño Integral (2006-2015) solo se encontró 2014; la capacidad administrativa, 2012-2014. "
        "El IDF cambió de método en 2020 y la MDM empezó en 2016.",
        "Contratación: SECOP no tiene registros suficientes antes de 2008 (41 contratos en 2007). 2026 va hasta el 20 de octubre.",
        "Agua: la cobertura reportada a la Superservicios (REC) tiene saltos por errores de reporte y un vacío en 2021; los "
        "censos (2005 y 2018) son la referencia confiable. El IRCA rural solo tiene 6 años.",
        "Educación: Saber 11 por municipio (TerriData) llega a 2022; la cobertura en educación superior de Yondó figura en cero "
        "y se omitió.",
        "Salud: la mortalidad materna tiene pocos años publicados; la vacunación y el régimen subsidiado cambian de base de "
        "población en 2018-2020.",
        "Economía: el valor agregado municipal llega a 2023 y el empleo formal (FILCO) solo cubre 2009-2016. TerriData publica "
        "ceros para las empresas que generan empleo formal en Yondó; se omitió.",
        "Conectividad: no hay serie municipal de internet móvil; las conexiones de internet fijo por operador llegan a 2023.",
        "Ambiente: la deforestación anual por municipio llega a 2018; los eventos de desastre por tipo, a 2021.",
        "Antioquia y Colombia: solo se incluyen para tasas y porcentajes comparables. Los índices fiscales del departamento "
        "miden a la Gobernación, no a sus municipios, y no se muestran.",
    ]
    fuentes = [
        {"archivo": "data/fuentes/ipc_dane.csv", "url": ipc_fuente, "uso": "IPC para llevar todo a pesos de 2026"},
        {"archivo": "data/fuentes/serie_fiscal_oec.csv", "url": URL_TD_PERFIL, "uso": "operaciones efectivas de caja 2004-2024"},
        {"archivo": "data/fuentes/sgp_sicodis.csv", "url": URL_TD_PERFIL, "uso": "SGP asignado 2004-2024"},
        {"archivo": "data/fuentes/series_sociales.json", "url": "ver campo fuente de cada serie",
         "uso": "población DANE, IRCA, Saber 11 global, matrícula, homicidios (número), víctimas, desplazamiento, petróleo, "
                "ganado, internet fijo (conexiones), censos de energía y gas"},
        {"archivo": "data/fuentes/terridata_panel.csv", "url": URL_TD_ZIP.format(cod="{05893|05000|01001}"),
         "uso": "series de TerriData para Yondó, Antioquia y Colombia (nuevo)"},
        {"archivo": "data/fuentes/sgr_distribucion_anual.csv", "url": "https://www.datos.gov.co/d/h6yd-ei3n",
         "uso": "regalías distribuidas por el SGR por vigencia y fuente, 2012-2025 (nuevo)"},
        {"archivo": "data/fuentes/cuipo_resumen_anual.csv", "url": "https://www.datos.gov.co/d/9axr-9gnb y https://www.datos.gov.co/d/4f7r-epif",
         "uso": "presupuesto ordinario 2023-2026: recaudo y compromisos (nuevo)"},
        {"archivo": "data/fuentes/secop_competencia_anual.csv", "url": "https://www.datos.gov.co/d/rpmr-utcd",
         "uso": "contratos de la alcaldía con y sin competencia por año (nuevo)"},
        {"archivo": "data/fuentes/idi_gobernacion_antioquia.csv",
         "url": "https://www.antioquia.gov.co/images/pdf/Indice%20de%20Desempe%C3%B1o%20Integral%202014.pdf",
         "uso": "Índice de Desempeño Integral 2014 y capacidad administrativa 2012-2014 (nuevo)"},
        {"archivo": "data/secop/secop_resumen.json", "url": "https://www.datos.gov.co/d/rpmr-utcd",
         "uso": "valor contratado por categoría y OPS por año"},
        {"archivo": "data/gobiernos.json", "url": None, "uso": "periodos y alcaldes"},
    ]
    out = {
        "titulo": "Panel anual de Yondó, 2004-2026: plata, gestión y resultados de cada gobierno",
        "generado_por": "scripts/build_panel_anual.py",
        "fecha_corte": FECHA_CORTE,
        "moneda": "Pesos de 2026 = IPC DANE promedio de enero a septiembre de 2026 (158,284; base dic-2018 = 100), el mismo "
                  "de data/comparativa/costo_no_hacer.json. Cada año se deflacta con el IPC promedio de ese año.",
        "como_leer": [
            "Cada indicador trae su serie anual («serie»), su unidad, su fuente y si es mejor un valor alto o bajo («mejor»; "
            "null cuando subir o bajar no es en sí bueno ni malo).",
            "Los años sin dato no aparecen: un vacío no es un cero. Los años incompletos van en «parcial» y no entran en las "
            "comparaciones.",
            "«antioquia» y «colombia» solo aparecen cuando la cifra es comparable (tasas y porcentajes).",
            "En «periodos», el inicio es el último dato antes de que empiece el gobierno (lo que recibió) y el final, el último "
            "dato dentro del gobierno. Si no hay dato anterior, se usa el primer dato del periodo y se indica en «regla».",
            "Los agregados de plata suman millones de pesos de 2026 de los años con dato; «por_habitante_al_anio_2026» divide esa "
            "suma por la población de esos mismos años.",
        ],
        "anios": ANIOS,
        "ipc": {str(a): round(prom[a] / base, 4) for a in ANIOS},
        "ipc_fuente": f"{ipc_fuente}; data/fuentes/ipc_dane.csv",
        "poblacion": {str(a): int(POB[a]) for a in ANIOS if a in POB},
        "poblacion_fuente": S["poblacion_total_dane_base_cnpv2018"]["fuente"],
        "areas": AREAS,
        "indicadores": sorted(IND, key=lambda i: AREAS.index(i["area"])),
        "periodos": periodos,
        "vacios": vacios,
        "fuentes": fuentes,
    }
    SALIDA.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    por_area = {a: sum(1 for i in IND if i["area"] == a) for a in AREAS}
    print(f"{SALIDA.relative_to(RAIZ)}: {len(IND)} indicadores")
    for a, n in por_area.items():
        print(f"  {a}: {n}")


if __name__ == "__main__":
    main()
