#!/usr/bin/env python3
"""
Nomenclátor geográfico público de Yondó (Antioquia, Colombia; código DANE 05893).

Construye dos archivos junto a este script, solo con datos geográficos públicos
(no lee ni escribe datos personales):

  yondo_limite.geojson  Límite municipal (WGS84, lon/lat). Fuente: DANE, Marco
                        Geoestadístico Nacional (MGN) 2025; respaldos: MGN 2024 y la
                        relación OSM 1316178.
  gazetteer.json        {"fuente": [...], "lugares": [...]}. Cada lugar trae nombre en
                        mayúsculas sin tildes (Ñ→N), tipo (barrio | vereda | corregimiento |
                        caserio | centro_poblado | sector), zona (urbana | rural), lat/lon,
                        alias, fuente (de la coordenada), precision (poligono_centroide |
                        punto | aproximado | sin_coordenada) y, cuando aplica, geom (polígono
                        simplificado a ~50 m), padre, codigo, codigo_dane, nucleo y nota.

Fuentes (todas públicas; el detalle, con URL y licencia, queda en gazetteer.json["fuente"]):
  * Gobernación de Antioquia (catastro): veredas y corregimiento catastrales, centros
    poblados y la tabla de barrios y veredas por municipio (ArcGIS Online, acceso público).
  * DANE: MGN 2025 (límite), nivel de referencia de veredas 2024, polígonos de centros
    poblados del MGN y DIVIPOLA de centros poblados (datos.gov.co, xaxy-8nri).
  * MinEducación: sedes educativas (datos.gov.co, x5ay-984n). Sus coordenadas vienen con
    2 decimales (~1 km): solo se usan como «aproximado» o para validar otras.
  * Alcaldía de Yondó (datos.gov.co, s39w-pjx4): solo los NOMBRES de corregimiento,
    vereda y barrio (agregados con GROUP BY; no se descarga ningún registro de personas).
  * OpenStreetMap (API 0.6, por teselas; Nominatim no hace falta): lugares (place=*),
    escuelas y puntos de referencia. © colaboradores de OpenStreetMap, ODbL 1.0.
  * Anclas de barrio: edificios públicos con dirección oficial en un barrio (hospital,
    alcaldía, colegios, biblioteca, empresa de aguas). Se usan como punto «aproximado»
    del barrio, nunca como centroide. Dos de ellas vienen del levantamiento del propio
    repositorio (data/edificios/*.json).

Reglas que aplica:
  * Toda coordenada debe caer dentro del límite municipal; lo que cae fuera se descarta.
  * Las veredas toman la geometría catastral de la Gobernación (la división vigente,
    con nombres como X-10, Las Américas o Patio Bonito). Las veredas del DANE (POT 2007)
    se cruzan por superposición para añadir su código y su nombre como alias.
  * lat/lon de una vereda = punto interior del polígono (centroide si cae dentro).
    Si hay un caserío, centro poblado o escuela validada dentro, va aparte en «nucleo».
  * Las escuelas solo cuentan si su punto cae dentro de la vereda que dice su dirección.
  * Barrios sin una base real quedan sin coordenada (precision «sin_coordenada»): la app
    puede reconocer el nombre y derivar el centroide de las direcciones.

Uso:
  python3 build_gazetteer.py                 # descarga (con caché) y escribe las salidas
  python3 build_gazetteer.py --offline       # solo con lo que ya está en la caché
  python3 build_gazetteer.py --cache DIR     # carpeta de caché (por defecto, en el temp del sistema)
  python3 build_gazetteer.py --sin-osm       # no descarga teselas de OSM

Solo usa la biblioteca estándar de Python 3.9+. User-Agent: «atlas-yondo-gazetteer/1.0».
Respeta 1 petición por segundo con los servidores de OpenStreetMap.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

AQUI = Path(__file__).resolve().parent
UA = "atlas-yondo-gazetteer/1.0"
DIVIPOLA = "05893"

# ───────────────────────────── URLs de las fuentes ─────────────────────────────

GOBANT = "https://services5.arcgis.com/K90UQIB09TmTjUL8/arcgis/rest/services"
URL = {
    "mgn2025": "https://services.arcgis.com/ioNRSZMYYlx0PUaB/arcgis/rest/services/MGN2025_MPIO_GRAFICO/FeatureServer/0",
    "mgn2024": "https://services.arcgis.com/wLfHepIACaM0pwj9/arcgis/rest/services/MGN_MPIO_POLITICO_2024/FeatureServer/0",
    "osm_limite": "https://polygons.openstreetmap.fr/get_geojson.py",
    "gob_veredas": f"{GOBANT}/Corregimientos_Antioquia_WFL1/FeatureServer/6",
    "gob_corregimientos": f"{GOBANT}/Corregimientos_Antioquia_WFL1/FeatureServer/5",
    "gob_cpob": f"{GOBANT}/Corregimientos_Antioquia_WFL1/FeatureServer/4",
    "gob_barrios": f"{GOBANT}/ViewBarriosVeredas/FeatureServer/8",
    "gob_sedes": f"{GOBANT}/MAPA_SEDE_EDUCATIVAS_POR_ZONA_URBANA_Y_RURAL_WFL1/FeatureServer",
    "dane_cpob": f"{GOBANT}/centros_poblados_Antioquia/FeatureServer/0",
    "dane_veredas": "https://services.arcgis.com/rBj217q0SEMHovrR/arcgis/rest/services/Veredas_Col_2024/FeatureServer/0",
    "divipola": "https://www.datos.gov.co/resource/xaxy-8nri.json",
    "men": "https://www.datos.gov.co/resource/x5ay-984n.json",
    "alcaldia": "https://www.datos.gov.co/resource/s39w-pjx4.json",
    "osm_api": "https://api.openstreetmap.org/api/0.6/map",
}

FUENTES = [
    {"id": "dane_mgn", "nombre": "DANE – Marco Geoestadístico Nacional 2025, nivel municipio (límite de Yondó)",
     "url": URL["mgn2025"] + "/query?where=mpio_cdpmp%3D%2705893%27&outFields=*&outSR=4326&f=geojson",
     "licencia": "Información oficial y pública del DANE; uso libre citando «DANE – MGN 2025». La copia en ArcGIS Online "
                 "(«MGN2025_MPIO_GRAFICO», herramienta Encuentra tu dirección) no declara licencia.",
     "uso": "yondo_limite.geojson y validación de todas las coordenadas"},
    {"id": "gobant_catastro", "nombre": "Gobernación de Antioquia (catastro) – veredas, corregimientos y centros poblados catastrales",
     "url": GOBANT + "/Corregimientos_Antioquia_WFL1/FeatureServer",
     "licencia": "Publicado en acceso público por la Gobernación de Antioquia en ArcGIS Online, sin licencia declarada en el ítem; "
                 "información pública (Ley 1712 de 2014). Citar «Gobernación de Antioquia – Catastro».",
     "uso": "geometría y nombre de las 62 veredas, el corregimiento San Miguel del Tigre y el centro poblado Cuatro Bocas"},
    {"id": "gobant_barrios", "nombre": "Gobernación de Antioquia – tabla de barrios y veredas por municipio (ViewBarriosVeredasU)",
     "url": URL["gob_barrios"] + "/query?where=CodMunicipio%3D%2705893%27&outFields=*&f=json",
     "licencia": "Acceso público en ArcGIS Online, sin licencia declarada; información pública (Ley 1712 de 2014).",
     "uso": "nombres de barrios de la cabecera"},
    {"id": "gobant_sedes", "nombre": "Gobernación de Antioquia – mapa de sedes educativas por zona urbana y rural",
     "url": URL["gob_sedes"],
     "licencia": "Acceso público en ArcGIS Online, sin licencia declarada. Muchos puntos están errados: solo se usa un punto "
                 "si cae dentro de la vereda de su dirección.",
     "uso": "puntos de escuelas rurales validados (núcleos de vereda y caseríos)"},
    {"id": "dane_veredas", "nombre": "DANE – Nivel de referencia de veredas 2024 (para Yondó, vigencia POT 2007)",
     "url": URL["dane_veredas"] + "/query?where=DPTOMPIO%3D%2705893%27&outFields=*&outSR=4326&f=geojson",
     "licencia": "Información oficial y pública del DANE; uso libre citando la fuente. Copia en ArcGIS Online («Veredas_Col_2024») "
                 "sin licencia declarada.",
     "uso": "código DANE de vereda y nombres alternos (alias) por superposición"},
    {"id": "dane_cpob", "nombre": "DANE – MGN, polígonos de centros poblados (copia de la Gobernación de Antioquia)",
     "url": URL["dane_cpob"],
     "licencia": "Información oficial y pública del DANE; uso libre citando la fuente.",
     "uso": "centroide de los centros poblados y perímetro de la cabecera"},
    {"id": "dane_divipola", "nombre": "DANE – DIVIPOLA, códigos de cabeceras y centros poblados (datos.gov.co xaxy-8nri)",
     "url": "https://www.datos.gov.co/d/xaxy-8nri",
     "licencia": "Creative Commons Attribution-ShareAlike 4.0 (CC BY-SA 4.0)",
     "uso": "lista oficial de centros poblados y su punto de referencia"},
    {"id": "men", "nombre": "MinEducación – Sedes educativas preescolar, básica y media (datos.gov.co x5ay-984n)",
     "url": "https://www.datos.gov.co/d/x5ay-984n",
     "licencia": "Creative Commons Attribution-ShareAlike 4.0 (CC BY-SA 4.0)",
     "uso": "vereda de cada escuela rural; coordenadas de 2 decimales solo como «aproximado» o para validar"},
    {"id": "alcaldia", "nombre": "Alcaldía de Yondó – Población por barrios (datos.gov.co s39w-pjx4), solo nombres",
     "url": "https://www.datos.gov.co/d/s39w-pjx4",
     "licencia": "Creative Commons Attribution-ShareAlike 4.0 (CC BY-SA 4.0)",
     "uso": "lista de nombres de barrio, vereda y corregimiento (consulta agregada GROUP BY, sin registros de personas)"},
    {"id": "osm", "nombre": "OpenStreetMap (API 0.6, teselas sobre el municipio)",
     "url": "https://www.openstreetmap.org/relation/1316178",
     "licencia": "Open Database License 1.0 (ODbL) – © colaboradores de OpenStreetMap",
     "uso": "lugares (place=*), escuelas y edificios públicos usados como anclas de barrio"},
    {"id": "repo_edificios", "nombre": "Levantamiento de sedes públicas del repositorio (data/edificios/*.json)",
     "url": "data/edificios/",
     "licencia": "La del repositorio",
     "uso": "dos anclas de barrio (sede de Aguas y Aseo, Biblioteca María Cano)"},
]

# ───────────────────────────── Nombres y alias ─────────────────────────────


def norm(s: str | None) -> str:
    """Mayúsculas sin tildes (Ñ→N), sin signos salvo el guion, espacios simples."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", str(s).upper())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("°", " ").replace("º", " ")
    s = re.sub(r"[^A-Z0-9\- ]", " ", s)
    s = re.sub(r"\s*-\s*", "-", s)
    return re.sub(r"\s+", " ", s).strip()


def clave(s: str) -> str:
    """Forma de comparación: sin guiones ni espacios dobles (así «X-10» = «X 10»)."""
    return re.sub(r"\s+", " ", norm(s).replace("-", " ")).strip()


# Nombre catastral → nombre de salida (errores de digitación y forma corta)
RENOMBRAR_VEREDA = {
    "SARDIANTA ALTA": "SARDINATA ALTA",
    "LA ROMPIDA N 1": "LA ROMPIDA 1",
    "LA ROMPIDA N 2": "LA ROMPIDA 2",
}

# Alias documentados en las fuentes (Alcaldía, MEN, DANE, Gobernación) o variantes de escritura.
ALIAS_MANUALES = {
    # veredas
    "X-10": ["X10", "X 10", "LA X-10", "LA X10", "VEREDA X-10", "EQUIS 10", "X DIEZ", "LA CONDOR X-10", "LA CONDOR X10"],
    "KILOMETRO CINCO": ["KILOMETRO 5", "KM 5", "KM5", "KM CINCO", "K-5", "K5", "K 5", "KM-5", "KILOMETRO5"],
    "LA ROMPIDA 1": ["LA ROMPIDA N 1", "LA ROMPIDA NO 1", "LA ROMPIDA UNO", "ROMPIDA UNO", "ROMPIDA 1", "ROMPIDA N 1",
                     "LA ROMPIDA NUMERO 1", "LA ROMPIDA N1"],
    "LA ROMPIDA 2": ["LA ROMPIDA N 2", "LA ROMPIDA NO 2", "LA ROMPIDA DOS", "ROMPIDA DOS", "ROMPIDA 2", "ROMPIDA N 2",
                     "LA ROMPIDA NUMERO 2", "LA ROMPIDA N2"],
    "SARDINATA ALTA": ["SARDIANTA ALTA", "SARDINATA ARRIBA"],
    "SARDINATA BAJA": ["SARDINATA ABAJO"],
    "REMOLINOS PENAS BLANCAS": ["REMOLINO PENAS BLANCAS", "REMOLINO", "REMOLINOS", "EL REMOLINO", "PENAS BLANCAS",
                                "REMOLINO PENA BLANCA"],
    "SAN JUAN DE ITE": ["SAN JUAN ITE", "SAN JUAN DEL ITE", "HACIENDA ITE", "ITE"],
    "BOCAS DE DON JUAN": ["BOCAS DEL DON JUAN", "BOCA DE DON JUAN", "BOCAS DON JUAN", "BOCA DEL DON JUAN"],
    "CANO DON JUAN": ["CANO DE DON JUAN", "CANO DEL DON JUAN"],
    "EL VIETNAM": ["VIETNAM"],
    "NO TE PASES": ["NOTE PASES", "NO TEPASES"],
    "PUERTO CASABE": ["PUERTO CAASABE", "PTO CASABE"],
    "LA RINCONADA": ["RINCONADA"],
    "ROMPEDEROS": ["ROMPEDERO", "EL ROMPEDERO"],
    "LA CONCHA": ["LA CONCEPCION"],        # MEN: «C. E. R. LA CONCEPCION», dirección «VDA LA CONCHA»; Alcaldía: vereda LA CONCEPCION
    "CAMPO CIMITARRA": ["EL CAMPO CIMITARRA", "EL CAMPO"],  # DANE 2024: EL CAMPO CIMITARRA; MEN: «C. E. R. EL CAMPO»
    "BOCAS DE SAN FRANCISCO": ["BOCA DE SAN FRANCISCO", "BOCAS SAN FRANCISCO"],
    "PUERTO NUEVO": ["PUERTO NUEVO 2", "PUERTO NUEVO N 2", "PUERTO NUEVO NO 2"],  # MEN: VDA PUERTO NUEVO N° 2
    "LAS AMERICAS": ["LA AMERICA", "LAS AMERICA"],
    "LA CASCAJERA": ["CASCAJERA"],
    "SANTA CLARA": ["SANTA CLARA RAMBLAS"],  # MEN: «VDA SANTA CLARA RAMBLAS» (punto validado dentro de Santa Clara)
    # centros poblados
    "CIENAGA DE BARBACOAS": ["CIENAGA DE BARBACOA", "CIENAGA DE BARBACOA - LA PUNTA", "CIENAGA DE BARBACOA LA PUNTA",
                             "LA PUNTA", "CIENAGA BARBACOAS"],
    "PUERTO LOS MANGOS": ["LOS MANGOS", "PTO LOS MANGOS"],
    "PUERTO TOMAS": ["PTO TOMAS"],
    "PUERTO MATILDE": ["PTO MATILDE"],
    "CHORRO DE LAGRIMAS": ["CHORRO LAGRIMAS"],
    "YONDO": ["CASABE", "YONDO CASABE", "CASCO URBANO", "CABECERA MUNICIPAL", "ZONA URBANA", "CABECERA"],
    # barrios
    "VILLA MARIA": ["VILLAMARIA", "VILLA MARIA YONDO"],
    "NUEVA ESPERANZA": ["LA NUEVA ESPERANZA", "NUEVA ESPERENZA"],
    "LAS VEGAS": ["OPV LAS VEGAS", "URBANIZACION LAS VEGAS"],
    "EL PROGRESO": ["PROGRESO"],
    "EL PRADO": ["PRADO", "PRADO VIEJO", "EL PRADO VIEJO"],
    "URBANIZACION EL PRADO": ["URB EL PRADO", "PRADO NUEVO", "EL PRADO NUEVO"],
    "LA VICTORIA": ["VICTORIA"],
    "CENTRAL": ["EL CENTRAL", "CENTRO", "BARRIO CENTRAL", "EL CENTRO"],
    "JORGE ELIECER GAITAN": ["GAITAN", "JORGE E GAITAN", "JORGE ELIECER", "JORGE GAITAN"],
    "EL PARAISO": ["PARAISO"],
    "TRES DE OCTUBRE": ["3 DE OCTUBRE"],
    "URBANIZACION LA PAZ": ["URB LA PAZ"],
    "JOSE DOMINGO OLIVEROS": ["JOSE D OLIVEROS", "OLIVEROS", "JOSE DOMINGO"],
    "CANTARRANA": ["CANTA RANA"],
    "LA ESPANOLA": ["CIUDADELA LA ESPANOLA", "ESPANOLA", "LA ESPANOLA CIUDADELA"],
    "COLONIA SUR": ["LA COLONIA SUR"],
    "23 DE JULIO": ["VEINTITRES DE JULIO"],
    "25 DE ENERO": ["VEINTICINCO DE ENERO"],
    "LOS NARANJOS": ["NARANJOS"],
    "BATALLON": ["BATALLON ENERGETICO", "BATALLON ENERGETICO Y VIAL N 7"],
}

# Alias demasiado cortos para usarlos sin la palabra «VEREDA» delante («VEREDA X», «VEREDA K»)
ALIAS_AMBIGUOS = {"X-10": ["X"], "KILOMETRO CINCO": ["K"]}

# Notas sobre nombres que se prestan a confusión
NOTAS = {
    "X-10": "Vereda catastral X-10, entre La Cóndor, El Dique y Puerto Casabe, sobre el campo petrolero de Casabe. "
            "La Alcaldía la escribe «X - 10» y el MEN «VDA. X-10» (escuelas Once de Noviembre y La Primavera). "
            "«VEREDA X» en una dirección es casi seguro esta vereda (ver alias_ambiguos).",
    "KILOMETRO CINCO": "La Alcaldía la escribe «K-5» y el MEN «VDA. KM. CINCO». «VEREDA K» en una dirección es casi "
                       "seguro esta vereda (ver alias_ambiguos).",
    "LA CONCHA": "El MEN ubica la escuela «La Concepción» en la vereda La Concha y la Alcaldía nombra la vereda "
                 "«LA CONCEPCION»: se toma como alias.",
    "SANTA CLARA": "El MEN registra una sede en «VDA SANTA CLARA RAMBLAS»; se toma como alias.",
    "PUERTO NUEVO": "El MEN registra la sede «Puerto Nuevo No. 2» en «VDA PUERTO NUEVO N° 2»; se toma como alias.",
    "CAMPO CIMITARRA": "El MEN registra la sede «El Campo» (de la I.E.R. San Miguel del Tigre) en «VDA EL CAMPO»; se toma como alias.",
    "REMOLINOS PENAS BLANCAS": "La Alcaldía la nombra «REMOLINO PEÑAS BLANCAS» y el MEN «VDA PEÑAS BLANCAS» (escuela El Remolino).",
}

PALABRAS_VACIAS = {"EL", "LA", "LOS", "LAS", "DE", "DEL", "ALTA", "BAJA", "ALTO", "BAJO", "1", "2"}

# Nombres de la tabla de la Gobernación que no son barrios o están abreviados
BARRIO_GOBANT = {
    "NUEVA ESPERENZA": "NUEVA ESPERANZA", "VICTORIA": "LA VICTORIA", "PROGRESO": "EL PROGRESO",
    "PARAISO": "EL PARAISO", "PRADO": "EL PRADO", "CENTRO": "CENTRAL",
    "URBANIZACION": None, "AREA DE INVASION": None, "INVASION": None, "PREDIO DE INVASION": None,
    "ZONA URBANA": None, "LAS AMERICAS": None,  # Las Américas es vereda catastral
}
BARRIO_ALCALDIA = {"EL CENTRAL": "CENTRAL", "SIN BARRIO": None, "BARRIO_S4": None, "BARRIO S4": None}

# Anclas de barrio: edificios públicos cuya dirección oficial dice el barrio.
# (barrio, referencia OSM o None, lat, lon, fuente, base)
ANCLAS_BARRIO = [
    ("JOSE DOMINGO OLIVEROS", "node/4757181603", 7.005532, -73.914267, "osm",
     "E.S.E. Hospital Héctor Abad Gómez (punto OSM); dirección oficial Cra. 58 # 46-236, barrio José Domingo Oliveros"),
    ("EL PROGRESO", "node/12487375693", 7.0116125, -73.9077874, "osm",
     "I.E. Luis Eduardo Díaz, sede principal (punto OSM); MEN: KR 45 55 56, barrio El Progreso"),
    ("EL PROGRESO", "node/12487370011", 7.0106188, -73.9091226, "osm",
     "C.E. Mi Nuevo Horizonte (punto OSM); MEN: KR 47 54 74, B. El Progreso"),
    ("TRES DE OCTUBRE", "node/12487370012", 7.0070438, -73.9082705, "osm",
     "Colegio El Oasis (punto OSM); MEN: CRA. 47 48-06, B. Tres de Octubre"),
    ("COLONIA SUR", "node/4763237922", 7.0046596, -73.9106502, "osm",
     "Alcaldía Municipal (punto OSM); membrete oficial Cra. 55 No. 46A-16, Colonia Sur"),
    ("JORGE ELIECER GAITAN", "repo:data/edificios/aguas_aseo_sede.json", 7.008179, -73.91078, "estimado",
     "Sede de Aguas y Aseo de Yondó S.A. E.S.P.; certificación de la empresa: Cra. 53 No. 50-79, Barrio Jorge Eliécer Gaitán"),
    ("CENTRAL", "repo:data/edificios/cultura.json", 7.006156, -73.909777, "estimado",
     "Biblioteca Pública Municipal María Cano; directorio departamental: Cra. 50 # 43-13, barrio Central"),
    ("BATALLON", "way/499367198", 7.005538, -73.911373, "osm",
     "Batallón Energético y Vial Nº 7 (área militar en OSM, centroide)"),
]

# Nombres que llegan de las direcciones (lista del encargo); sirven solo para medir cobertura.
REQUERIDOS = [
    "VILLA MARIA", "BRISAS DEL ORIENTE", "BUENOS AIRES", "NUEVA ESPERANZA", "LA NUEVA ESPERANZA", "LAS VEGAS",
    "OPV LAS VEGAS", "EL PROGRESO", "EL PRADO", "PRADO VIEJO", "PRADO NUEVO", "URBANIZACION EL PRADO", "LOS NARANJOS",
    "LOS PALMITOS", "LA VICTORIA", "CENTRAL", "CENTRO", "JORGE ELIECER GAITAN", "GAITAN", "EL PARAISO", "TRES DE OCTUBRE",
    "LA PAZ", "URBANIZACION LA PAZ", "JOSE DOMINGO OLIVEROS", "CANTARRANA", "LA ESPANOLA", "CIUDADELA LA ESPANOLA",
    "OPV CASABE", "COLONIA SUR", "SANTA CAO", "LAS LOMAS", "MANZANA F", "EL RELLENO", "SAN MIGUEL DEL TIGRE",
    "SAN LUIS BELTRAN", "PUERTO LOS MANGOS", "PUERTO CASABE", "PUERTO TOMAS", "EL DIQUE", "LA CONDOR", "LA CONDOR PUENTE",
    "PUERTO 22", "CASERIO UNIVERSO", "UNIVERSO", "KILOMETRO 5", "KM 5", "K5", "X10", "X-10", "LA REPRESA", "SAN FRANCISCO",
    "BOCAS DE SAN FRANCISCO", "CANO BLANCO", "LA CONCEPCION", "PUERTO MATILDE", "EL GUAMO", "CUATRO BOCAS", "EL BAGRE",
    "LA ROMPIDA", "PUERTO NUEVO", "LA CABANA", "SARDINATA BAJA", "SARDINATA ALTA", "BOCAS DE BARBACOAS",
    "BOCAS DEL DON JUAN", "CANO DON JUAN", "CANO HUILA", "CAMPO CIMITARRA", "REMOLINO", "EL TOTUMO", "LAGUNA DEL MIEDO",
    "LAS AMERICAS", "CANO BODEGAS", "CAMPO VIJAO", "LA RAYA", "JABONAL", "BOCAS DE JABONAL", "LA CONGOJA", "LA FELICIDAD",
    "LA ORQUIDEA", "EL VIETNAM", "CANO BONITO", "LA RINCONADA", "LA SOLEDAD", "LA PRIMAVERA",
]

# ───────────────────────────── Red con caché ─────────────────────────────


class Red:
    """Descargas con caché en disco y cortesía de 1 s con los servidores de OSM."""

    LENTOS = ("openstreetmap.org", "openstreetmap.fr")

    def __init__(self, cache: Path, offline: bool = False):
        self.cache = cache
        self.cache.mkdir(parents=True, exist_ok=True)
        self.offline = offline
        self._ultimo: dict[str, float] = {}

    def get(self, url: str, params: dict | None = None) -> bytes:
        completo = url + ("?" + urllib.parse.urlencode(params) if params else "")
        ruta = self.cache / hashlib.sha1(completo.encode()).hexdigest()
        if ruta.exists():
            return ruta.read_bytes()
        if self.offline:
            raise RuntimeError(f"sin caché para {completo[:120]}")
        host = urllib.parse.urlsplit(completo).netloc
        if any(h in host for h in self.LENTOS):
            espera = 1.05 - (time.time() - self._ultimo.get(host, 0))
            if espera > 0:
                time.sleep(espera)
        error = None
        for intento in range(3):
            try:
                req = urllib.request.Request(completo, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=180) as r:
                    datos = r.read()
                self._ultimo[host] = time.time()
                ruta.write_bytes(datos)
                return datos
            except urllib.error.HTTPError as e:
                self._ultimo[host] = time.time()
                if 400 <= e.code < 500:
                    raise
                error = e
            except Exception as e:  # noqa: BLE001 - red inestable: reintentar
                error = e
            time.sleep(2 * (intento + 1))
        raise RuntimeError(f"no se pudo descargar {completo[:120]}: {error}")

    def json(self, url: str, params: dict | None = None):
        return json.loads(self.get(url, params))


def arcgis(red: Red, capa: str, where: str, campos: str = "*", geometria: bool = True) -> list[dict]:
    """Consulta una capa ArcGIS y devuelve rasgos GeoJSON (WGS84), paginando si hace falta."""
    rasgos, desde = [], 0
    while True:
        params = {"where": where, "outFields": campos, "outSR": 4326, "f": "geojson",
                  "returnGeometry": "true" if geometria else "false",
                  "resultOffset": desde, "resultRecordCount": 1000}
        d = red.json(capa + "/query", params)
        if "error" in d:
            raise RuntimeError(f"ArcGIS {capa}: {d['error']}")
        lote = d.get("features", [])
        rasgos += lote
        mas = d.get("exceededTransferLimit") or (d.get("properties") or {}).get("exceededTransferLimit")
        if not mas or not lote:
            return rasgos
        desde += len(lote)


# ───────────────────────────── Geometría (sin dependencias) ─────────────────────────────

LAT0 = 6.95
KX = 111320.0 * math.cos(math.radians(LAT0))  # metros por grado de longitud
KY = 110574.0                                  # metros por grado de latitud


def anillos_de(geom: dict | None) -> list[list[list[float]]]:
    """Todos los anillos de un Polygon o MultiPolygon (lista plana)."""
    if not geom:
        return []
    if geom["type"] == "Polygon":
        return [r for r in geom["coordinates"] if len(r) >= 4]
    if geom["type"] == "MultiPolygon":
        return [r for p in geom["coordinates"] for r in p if len(r) >= 4]
    return []


def dentro_anillos(lon: float, lat: float, anillos) -> bool:
    """Regla par-impar sobre todos los anillos: respeta huecos y partes múltiples."""
    c = False
    for r in anillos:
        j = len(r) - 1
        for i in range(len(r)):
            xi, yi = r[i][0], r[i][1]
            xj, yj = r[j][0], r[j][1]
            if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
                c = not c
            j = i
    return c


def area_centroide_anillo(r) -> tuple[float, float, float]:
    """Área (m², con signo) y centroide (lon, lat) de un anillo."""
    a = cx = cy = 0.0
    x0, y0 = r[0][0], r[0][1]
    for i in range(len(r) - 1):
        x1, y1 = (r[i][0] - x0) * KX, (r[i][1] - y0) * KY
        x2, y2 = (r[i + 1][0] - x0) * KX, (r[i + 1][1] - y0) * KY
        f = x1 * y2 - x2 * y1
        a += f
        cx += (x1 + x2) * f
        cy += (y1 + y2) * f
    a /= 2
    if abs(a) < 1e-9:
        return 0.0, x0, y0
    return a, x0 + cx / (6 * a) / KX, y0 + cy / (6 * a) / KY


def dist_seg_m(px, py, ax, ay, bx, by) -> float:
    px, py, ax, ay, bx, by = px * KX, py * KY, ax * KX, ay * KY, bx * KX, by * KY
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


class Area:
    """Polígono con caja envolvente, área, punto interior y prueba de pertenencia."""

    def __init__(self, geom: dict, **props):
        self.geom = geom
        self.anillos = anillos_de(geom)
        self.props = props
        xs = [p[0] for r in self.anillos for p in r]
        ys = [p[1] for r in self.anillos for p in r]
        self.bbox = (min(xs), min(ys), max(xs), max(ys)) if xs else (0, 0, 0, 0)
        self._poligonos = None

    def contiene(self, lon: float, lat: float) -> bool:
        x0, y0, x1, y1 = self.bbox
        return x0 <= lon <= x1 and y0 <= lat <= y1 and dentro_anillos(lon, lat, self.anillos)

    def distancia_m(self, lon: float, lat: float) -> float:
        """0 si está dentro; si no, distancia al borde en metros."""
        if self.contiene(lon, lat):
            return 0.0
        return min(dist_seg_m(lon, lat, r[i][0], r[i][1], r[i + 1][0], r[i + 1][1])
                   for r in self.anillos for i in range(len(r) - 1))

    def poligonos(self):
        """[(exterior, [huecos])] según la profundidad de anidamiento de cada anillo."""
        if self._poligonos is None:
            prof = []
            for i, r in enumerate(self.anillos):
                p = r[0]
                prof.append(sum(1 for j, s in enumerate(self.anillos) if j != i and dentro_anillos(p[0], p[1], [s])))
            ext = [i for i, d in enumerate(prof) if d % 2 == 0]
            polys = {i: [] for i in ext}
            for i, d in enumerate(prof):
                if d % 2 == 1:
                    cands = [e for e in ext if prof[e] == d - 1 and dentro_anillos(
                        self.anillos[i][0][0], self.anillos[i][0][1], [self.anillos[e]])]
                    if cands:
                        polys[min(cands, key=lambda e: abs(area_centroide_anillo(self.anillos[e])[0]))].append(i)
            self._poligonos = [(self.anillos[e], [self.anillos[h] for h in hs]) for e, hs in polys.items()]
        return self._poligonos

    def area_m2(self) -> float:
        return sum(abs(area_centroide_anillo(e)[0]) - sum(abs(area_centroide_anillo(h)[0]) for h in hs)
                   for e, hs in self.poligonos())

    def centroide(self) -> tuple[float, float]:
        a = sx = sy = 0.0
        for e, hs in self.poligonos():
            for r, s in [(e, 1)] + [(h, -1) for h in hs]:
                ar, cx, cy = area_centroide_anillo(r)
                ar = abs(ar) * s
                a += ar
                sx += cx * ar
                sy += cy * ar
        if a == 0:
            return self.anillos[0][0][0], self.anillos[0][0][1]
        return sx / a, sy / a

    def punto_interior(self) -> tuple[float, float]:
        """Centroide si cae dentro; si no, el centro del tramo interior más ancho de una horizontal."""
        cx, cy = self.centroide()
        if self.contiene(cx, cy):
            return cx, cy
        y0, y1 = self.bbox[1], self.bbox[3]
        for y in [cy] + [y0 + f * (y1 - y0) for f in (0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8, 0.1, 0.9)]:
            xs = []
            for r in self.anillos:
                for i in range(len(r) - 1):
                    (xa, ya), (xb, yb) = r[i][:2], r[i + 1][:2]
                    if (ya > y) != (yb > y):
                        xs.append(xa + (y - ya) * (xb - xa) / (yb - ya))
            xs.sort()
            tramos = [(xs[i + 1] - xs[i], (xs[i] + xs[i + 1]) / 2) for i in range(0, len(xs) - 1, 2)]
            if tramos:
                return max(tramos)[1], y
        return cx, cy


def _dp_indices(pts, i, j, tol, keep):
    pila = [(i, j)]
    while pila:
        a, b = pila.pop()
        (xa, ya), (xb, yb) = pts[a], pts[b]
        dx, dy = xb - xa, yb - ya
        l2 = dx * dx + dy * dy
        dmax, k = -1.0, -1
        for m in range(a + 1, b):
            px, py = pts[m]
            t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((px - xa) * dx + (py - ya) * dy) / l2))
            d = math.hypot(px - (xa + t * dx), py - (ya + t * dy))
            if d > dmax:
                dmax, k = d, m
        if dmax > tol:
            keep[k] = True
            pila += [(a, k), (k, b)]


def simplificar_anillo(r, tol_m: float):
    """Douglas-Peucker en metros. Devuelve el anillo cerrado o None si colapsa."""
    if r[0] == r[-1]:
        r = r[:-1]
    if len(r) < 3:
        return None
    pts = [(p[0] * KX, p[1] * KY) for p in r]
    n = len(pts)
    k = max(range(n), key=lambda i: (pts[i][0] - pts[0][0]) ** 2 + (pts[i][1] - pts[0][1]) ** 2)
    if k == 0:
        return None
    keep = [False] * n
    keep[0] = keep[k] = True
    _dp_indices(pts, 0, k, tol_m, keep)
    pts2 = pts + [pts[0]]
    keep2 = keep + [True]
    _dp_indices(pts2, k, n, tol_m, keep2)
    sal = [r[i] for i in range(n) if keep[i] or keep2[i]]
    if len(sal) < 3:
        return None
    return sal + [sal[0]]


def geom_simplificada(area: Area, tol_m: float = 50.0, min_ha: float = 1.0, dec: int = 5) -> dict | None:
    """Polígono simplificado (RFC 7946: exterior antihorario, huecos horarios), sin partes de menos de min_ha."""
    salida = []
    for ext, huecos in area.poligonos():
        e = simplificar_anillo(ext, tol_m)
        if not e or abs(area_centroide_anillo(e)[0]) < min_ha * 1e4:
            continue
        if area_centroide_anillo(e)[0] < 0:
            e = e[::-1]
        anillos = [e]
        for h in huecos:
            hs = simplificar_anillo(h, tol_m)
            if hs and abs(area_centroide_anillo(hs)[0]) >= min_ha * 1e4:
                anillos.append(hs if area_centroide_anillo(hs)[0] < 0 else hs[::-1])
        salida.append([[[round(p[0], dec), round(p[1], dec)] for p in a] for a in anillos])
    if not salida:
        return None
    if len(salida) == 1:
        return {"type": "Polygon", "coordinates": salida[0]}
    return {"type": "MultiPolygon", "coordinates": salida}


def geom_redondeada(geom: dict, dec: int = 6) -> dict:
    """Misma geometría, con las coordenadas redondeadas (6 decimales ≈ 0,1 m)."""
    def rd(c):
        return [round(c[0], dec), round(c[1], dec)] if isinstance(c[0], (int, float)) else [rd(x) for x in c]
    return {"type": geom["type"], "coordinates": rd(geom["coordinates"])}


def unir_geoms(geoms: list[dict]) -> dict:
    """Une varias geometrías en un MultiPolygon (sin disolver bordes)."""
    partes = []
    for g in geoms:
        if g and g["type"] == "Polygon":
            partes.append(g["coordinates"])
        elif g and g["type"] == "MultiPolygon":
            partes += g["coordinates"]
    return {"type": "MultiPolygon", "coordinates": partes} if len(partes) != 1 else {"type": "Polygon", "coordinates": partes[0]}


def muestras(area: Area, n: int = 24):
    """Rejilla de puntos dentro del polígono (para medir superposiciones)."""
    x0, y0, x1, y1 = area.bbox
    pts = []
    for i in range(n):
        for j in range(n):
            x = x0 + (i + 0.5) * (x1 - x0) / n
            y = y0 + (j + 0.5) * (y1 - y0) / n
            if area.contiene(x, y):
                pts.append((x, y))
    return pts


def r6(v: float) -> float:
    return round(v, 6)


# ───────────────────────────── OpenStreetMap por teselas ─────────────────────────────

TAGS_OSM = ("place", "amenity", "landuse", "natural", "water", "man_made", "divipola", "alt_name", "official_name",
            "old_name", "military")


def osm_teselas(red: Red, limite: Area, paso: float = 0.2) -> dict[str, dict]:
    """Descarga el mapa OSM por teselas (API 0.6) y extrae rasgos con nombre útiles para el nomenclátor."""
    x0, y0, x1, y1 = limite.bbox
    rasgos: dict[str, dict] = {}
    pendientes = []
    y = y0
    while y < y1:
        x = x0
        while x < x1:
            pendientes.append((round(x, 4), round(y, 4), round(min(x + paso, x1 + 1e-4), 4), round(min(y + paso, y1 + 1e-4), 4)))
            x += paso
        y += paso
    while pendientes:
        bx0, by0, bx1, by1 = pendientes.pop(0)
        # ¿la tesela toca el municipio? (esquinas, centro o algún vértice del límite)
        esquinas = [(bx0, by0), (bx0, by1), (bx1, by0), (bx1, by1), ((bx0 + bx1) / 2, (by0 + by1) / 2)]
        toca = any(limite.contiene(a, b) for a, b in esquinas) or any(
            bx0 <= p[0] <= bx1 and by0 <= p[1] <= by1 for r in limite.anillos for p in r[::10])
        if not toca:
            continue
        try:
            xml = red.get(URL["osm_api"], {"bbox": f"{bx0},{by0},{bx1},{by1}"})
        except urllib.error.HTTPError as e:
            if e.code == 400 and (bx1 - bx0) > 0.03:  # demasiados nodos: partir en cuatro
                mx, my = (bx0 + bx1) / 2, (by0 + by1) / 2
                pendientes += [(bx0, by0, mx, my), (mx, by0, bx1, my), (bx0, my, mx, by1), (mx, my, bx1, by1)]
                continue
            raise
        raiz = ET.fromstring(xml)
        nodos = {n.get("id"): (float(n.get("lat")), float(n.get("lon"))) for n in raiz.iter("node")}
        for el in raiz:
            if el.tag not in ("node", "way"):
                continue
            tags = {t.get("k"): t.get("v") for t in el.findall("tag")}
            nombre = tags.get("name")
            if "highway" in tags:  # de las vías solo interesa un nombre alterno de barrio («El Progreso»)
                nombre = tags.get("alt_name")
            elif not any(k in tags for k in ("place", "amenity", "landuse", "military")) and \
                    tags.get("natural") not in ("water", "wetland"):
                continue
            if not nombre:
                continue
            if el.tag == "node":
                lat, lon = nodos[el.get("id")]
            else:
                pts = [nodos[nd.get("ref")] for nd in el.findall("nd") if nd.get("ref") in nodos]
                if not pts:
                    continue
                if len(pts) > 1 and pts[0] == pts[-1]:
                    pts = pts[:-1]
                lat, lon = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
            ref = f"{el.tag}/{el.get('id')}"
            rasgos[ref] = {"ref": ref, "nombre": nombre,
                           "tags": {k: v for k, v in tags.items() if k in TAGS_OSM or k == "highway"},
                           "lat": lat, "lon": lon}
    return rasgos


# ───────────────────────────── Escuelas ─────────────────────────────

PREFIJOS_ESCUELA = re.compile(
    r"^(SEDE |CENTRO EDUCATIVO RURAL |CENTRO EDUCATIVO RUR |CENTRO EDUCATIVO |INSTITUCION EDUCATIVA RURAL |"
    r"INSTITUCION EDUCATIVA |INTSTITUCION EDUCATIVA |ESCUELA RURAL |ESCUELA |COLEGIO |C E R |CER |I E R |IER |C E |I E )+")


def nucleo_escuela(nombre: str) -> str:
    s = clave(re.sub(r"[.]", " ", nombre or ""))
    s = PREFIJOS_ESCUELA.sub("", s + " ").strip()
    s = re.sub(r"\bNO 2\b|\bN 2\b", "2", s)
    return s.replace("LUIS LOPEZ MESA", "LUIS LOPEZ DE MESA").replace("KM CINCO", "KILOMETRO CINCO")


def vereda_men(fila: dict) -> str:
    """Nombre de la vereda o corregimiento de una sede MEN (barrio_vereda o, si falta, dirección)."""
    s = fila.get("barrio_vereda") or fila.get("direccion") or ""
    s = clave(re.sub(r"[.]", " ", s))
    s = re.sub(r"^(VDA|VEREDA|CORREG|CORREGIMIENTO|B|BARRIO)\s+", "", s)
    return s.strip()


# ───────────────────────────── Construcción ─────────────────────────────


class Nomenclator:
    def __init__(self):
        self.lugares: list[dict] = []

    def agregar(self, **lg) -> dict:
        lg = {k: v for k, v in lg.items() if v not in (None, [], {}, "")}
        lg.setdefault("lat", None)
        lg.setdefault("lon", None)
        self.lugares.append(lg)
        return lg

    def buscar(self, nombre: str, tipos: tuple[str, ...] | None = None) -> list[dict]:
        c = clave(nombre)
        return [lg for lg in self.lugares if (tipos is None or lg["tipo"] in tipos)
                and (clave(lg["nombre"]) == c or c in {clave(a) for a in lg.get("alias", [])})]


def construir(red: Red, usar_osm: bool = True) -> tuple[dict, dict, dict]:
    log = defaultdict(list)

    # 1) Límite municipal ───────────────────────────────────────────────
    limite_rasgo, fuente_limite = None, None
    for nombre, capa, where in (("DANE MGN 2025", URL["mgn2025"], f"mpio_cdpmp='{DIVIPOLA}'"),
                                ("DANE MGN 2024", URL["mgn2024"], f"MPIO_CDPMP='{DIVIPOLA}'")):
        try:
            fs = arcgis(red, capa, where)
            if fs and fs[0].get("geometry"):
                limite_rasgo, fuente_limite = fs[0], nombre
                break
        except Exception as e:  # noqa: BLE001
            log["avisos"].append(f"límite {nombre}: {e}")
    if limite_rasgo is None:
        g = red.json(URL["osm_limite"], {"id": 1316178, "params": 0})
        limite_rasgo, fuente_limite = {"geometry": g, "properties": {}}, "OSM relación 1316178"
    limite = Area(limite_rasgo["geometry"])
    log["limite"] = [fuente_limite, f"{limite.area_m2() / 1e6:.1f} km²", f"bbox {tuple(round(v, 4) for v in limite.bbox)}"]

    def en_limite(lon, lat, tol_m=0.0) -> bool:
        return lon is not None and (limite.contiene(lon, lat) or (tol_m > 0 and limite.distancia_m(lon, lat) <= tol_m))

    # 2) Veredas catastrales y corregimiento ───────────────────────────
    veredas: list[Area] = []
    for f in arcgis(red, URL["gob_veredas"], f"COD_MPIO='{DIVIPOLA}'"):
        p = f["properties"]
        if not f.get("geometry"):
            continue
        nombre = norm(p.get("NOMBRE_VEREDA"))
        nombre = RENOMBRAR_VEREDA.get(nombre, nombre)
        corr = norm(p.get("NOMBRE_CORREGIMIENTO"))
        veredas.append(Area(f["geometry"], nombre=nombre, nombre_fuente=norm(p.get("NOMBRE_VEREDA")),
                            codigo=p.get("COD_VEREDA"),
                            corregimiento=None if "SIN CORREGIMIENTO" in corr else corr))
    log["veredas_catastro"] = [str(len(veredas))]

    def vereda_en(lon, lat) -> Area | None:
        for v in veredas:
            if v.contiene(lon, lat):
                return v
        return None

    corregimientos = [Area(f["geometry"], nombre=norm(f["properties"].get("NOMBRE_CORREG")))
                      for f in arcgis(red, URL["gob_corregimientos"], f"COD_MPIO='{DIVIPOLA}'") if f.get("geometry")]

    # 3) Veredas DANE 2024 → cruce por superposición ───────────────────
    dane_veredas = []
    try:
        for f in arcgis(red, URL["dane_veredas"], f"DPTOMPIO='{DIVIPOLA}'", "CODIGO_VER,NOMBRE_VER,VIGENCIA,FUENTE"):
            if f.get("geometry"):
                dane_veredas.append(Area(f["geometry"], nombre=norm(f["properties"]["NOMBRE_VER"]),
                                         codigo=f["properties"]["CODIGO_VER"]))
    except Exception as e:  # noqa: BLE001
        log["avisos"].append(f"veredas DANE: {e}")
    cruce_dane = {}  # codigo catastral -> [(codigo DANE, nombre DANE, fracción del DANE, fracción del catastro)]
    if dane_veredas:
        muestras_cat = {v.props["codigo"]: muestras(v, 20) for v in veredas}
        for d in dane_veredas:
            pts = muestras(d, 20)
            cuenta = Counter(v.props["codigo"] for x, y in pts for v in [vereda_en(x, y)] if v)
            for cod, n in cuenta.items():
                frac_d = n / max(1, len(pts))
                mc = muestras_cat[cod]
                frac_c = sum(1 for x, y in mc if d.contiene(x, y)) / max(1, len(mc))
                cruce_dane.setdefault(cod, []).append((d.props["codigo"], d.props["nombre"], frac_d, frac_c))

    # 4) Centros poblados (DANE MGN + DIVIPOLA + Gobernación) ──────────
    cp_poligonos: dict[str, dict] = {}
    try:
        for f in arcgis(red, URL["dane_cpob"], f"COD_MPIO='{DIVIPOLA}'", "COD_CPOB,NOM_CPOB,COD_CLAS"):
            p = f["properties"]
            if f.get("geometry"):
                cp_poligonos.setdefault(p["COD_CPOB"], {"nombre": norm(p["NOM_CPOB"]), "clase": p["COD_CLAS"], "geoms": []})["geoms"].append(f["geometry"])
    except Exception as e:  # noqa: BLE001
        log["avisos"].append(f"centros poblados MGN: {e}")
    divipola = red.json(URL["divipola"], {"$where": f"codigo_municipio='{DIVIPOLA}'", "$limit": 100})
    gob_cpob = []
    try:
        for f in arcgis(red, URL["gob_cpob"], "MUNICIPIO LIKE 'YOND%'", "CPOB_CNMBR,CORREGIMIENTO"):
            if f.get("geometry"):
                gob_cpob.append(Area(f["geometry"], nombre=norm(re.sub(r"^Cp\.\s*", "", f["properties"]["CPOB_CNMBR"]))))
    except Exception as e:  # noqa: BLE001
        log["avisos"].append(f"centros poblados Gobernación: {e}")

    # 5) Sedes educativas: MEN (nombres, vereda, punto de 2 decimales) y Gobernación (puntos) ──
    men = red.json(URL["men"], {"$select": "a_o,codigo_dane_sede,nombre_sede,zona,barrio_vereda,direccion,"
                                           "coordenada_y_sede,coordenada_x_sede",
                                "$where": f"cod_dane_municipio='{DIVIPOLA}'", "$limit": 5000})
    gob_sedes = {}
    for capa in (0, 1):
        try:
            for f in arcgis(red, f"{URL['gob_sedes']}/{capa}", "Código_municipio=5893", "Código_Sede,Nombre_Sede,Zona,Dirección"):
                g = f.get("geometry") or {}
                if g.get("type") == "Point":
                    gob_sedes[str(f["properties"]["Código_Sede"])] = (g["coordinates"][1], g["coordinates"][0])
        except Exception as e:  # noqa: BLE001
            log["avisos"].append(f"sedes Gobernación capa {capa}: {e}")

    # 6) Nombres de barrios y veredas (Alcaldía y Gobernación) ───────
    alcaldia = red.json(URL["alcaldia"], {"$select": "nom_corregimiento,nom_vereda,nom_barrio,count(*) as n",
                                          "$group": "nom_corregimiento,nom_vereda,nom_barrio", "$limit": 5000})
    gob_tabla = arcgis(red, URL["gob_barrios"], f"CodMunicipio='{DIVIPOLA}'", geometria=False)

    # 7) OpenStreetMap ─────────────────────────────────────────────────
    osm = {}
    if usar_osm:
        try:
            osm = osm_teselas(red, limite)
        except Exception as e:  # noqa: BLE001
            log["avisos"].append(f"OSM: {e}")
    log["osm_rasgos"] = [str(len(osm))]

    # ─────────────────────────── Armar el nomenclátor ───────────────────────────
    N = Nomenclator()
    fuentes_usadas = set(["dane_mgn" if "DANE" in fuente_limite else "osm"])

    # Cabecera municipal: perímetro urbano del MGN
    cab = next((c for c in cp_poligonos.values() if c["clase"] == "1"), None)
    cab_area = Area(unir_geoms(cab["geoms"])) if cab else None
    div_cab = next((d for d in divipola if d.get("tipo_centro_poblado") == "CM"), None)
    if cab_area:
        lon, lat = cab_area.punto_interior()
        precision, fuente = "poligono_centroide", "dane"
        fuentes_usadas.add("dane_cpob")
    else:
        lon, lat = float(div_cab["longitud"].replace(",", ".")), float(div_cab["latitud"].replace(",", "."))
        precision, fuente = "punto", "dane"
    N.agregar(nombre="YONDO", tipo="centro_poblado", zona="urbana", lat=r6(lat), lon=r6(lon),
              alias=ALIAS_MANUALES["YONDO"], fuente=fuente, precision=precision, codigo_dane=f"{DIVIPOLA}000",
              geom=geom_simplificada(cab_area, 15, 0.1) if cab_area else None,
              nota="Cabecera municipal (casco urbano, antiguo Casabe). La geometría es el perímetro urbano del MGN del DANE.")

    def es_urbano(lon, lat) -> bool:
        return bool(cab_area and cab_area.distancia_m(lon, lat) <= 150)

    # Corregimiento
    for c in corregimientos:
        cp = next((d for d in divipola if clave(d["nombre_centro_poblado"]) == clave(c.props["nombre"])), None)
        if cp:
            lon, lat = float(cp["longitud"].replace(",", ".")), float(cp["latitud"].replace(",", "."))
            precision, nota = "punto", "Coordenada de la cabecera del corregimiento (DIVIPOLA, DANE)."
        else:
            lon, lat = c.punto_interior()
            precision, nota = "poligono_centroide", None
        N.agregar(nombre=c.props["nombre"], tipo="corregimiento", zona="rural", lat=r6(lat), lon=r6(lon),
                  alias=["CORREGIMIENTO " + c.props["nombre"], "CORREG " + c.props["nombre"]],
                  fuente="dane" if cp else "gobant", precision=precision, geom=geom_simplificada(c, 50, 1.0), nota=nota)
        fuentes_usadas.add("gobant_catastro")

    # Veredas catastrales
    fuentes_usadas.add("gobant_catastro")
    por_codigo = {}
    for v in sorted(veredas, key=lambda v: v.props["nombre"]):
        lon, lat = v.punto_interior()
        alias = list(ALIAS_MANUALES.get(v.props["nombre"], []))
        if v.props["nombre_fuente"] != v.props["nombre"]:
            alias.append(v.props["nombre_fuente"])
        nombre_sin_art = re.sub(r"^(EL|LA|LOS|LAS) ", "", v.props["nombre"])
        if nombre_sin_art != v.props["nombre"] and len(nombre_sin_art) >= 5:
            alias.append(nombre_sin_art)
        codigo_dane = None
        nombres_dane = []
        cruces = sorted(cruce_dane.get(v.props["codigo"], []), key=lambda t: -t[3])
        for cod_d, nom_d, frac_d, frac_c in cruces:
            # misma vereda si se cubren mutuamente en su mayoría, o si el nombre coincide y el DANE cae mayormente aquí
            if (frac_d >= 0.5 and frac_c >= 0.5) or (clave(nom_d) == clave(v.props["nombre"]) and frac_d >= 0.5):
                codigo_dane = codigo_dane or cod_d
                nombres_dane.append(nom_d)
                fuentes_usadas.add("dane_veredas")
        otros = {x.props["nombre"] for x in veredas if x is not v}
        for nd in nombres_dane:
            if clave(nd) != clave(v.props["nombre"]) and nd not in otros:
                alias.append(nd)
        nota = NOTAS.get(v.props["nombre"])
        if not codigo_dane and cruces and cruces[0][3] >= 0.5:
            cod_d, nom_d, _, frac_c = cruces[0]
            nota = ((nota + " ") if nota else "") + (
                f"En la cartografía veredal del DANE (POT 2007) el {round(frac_c * 100)} % de su área cae en "
                f"{nom_d} ({cod_d}).")
        lg = N.agregar(nombre=v.props["nombre"], tipo="vereda", zona="rural", lat=r6(lat), lon=r6(lon),
                       alias=alias, fuente="gobant", precision="poligono_centroide",
                       padre=v.props.get("corregimiento"), codigo=v.props["codigo"], codigo_dane=codigo_dane,
                       area_ha=round(v.area_m2() / 1e4), nota=nota, geom=geom_simplificada(v, 50, 1.0))
        if v.props["nombre"] in ALIAS_AMBIGUOS:
            lg["alias_ambiguos"] = ALIAS_AMBIGUOS[v.props["nombre"]]
        por_codigo[v.props["codigo"]] = lg
        lg["_area"] = v

    def lugar_de_vereda(lon, lat):
        v = vereda_en(lon, lat)
        return por_codigo.get(v.props["codigo"]) if v else None

    def vereda_por_nombre(nombre: str):
        r = N.buscar(nombre, ("vereda",))
        return r[0] if len(r) == 1 else None

    def poner_nucleo(lg_vereda, lat, lon, fuente, precision, ref, prioridad):
        if lg_vereda is None:
            return
        actual = lg_vereda.get("nucleo")
        if actual and actual["_p"] <= prioridad:
            return
        lg_vereda["nucleo"] = {"lat": r6(lat), "lon": r6(lon), "fuente": fuente, "precision": precision, "ref": ref, "_p": prioridad}

    # Centros poblados (DIVIPOLA + polígono MGN)
    fuentes_usadas.add("dane_divipola")
    for d in sorted(divipola, key=lambda d: d["codigo_centro_poblado"]):
        if d.get("tipo_centro_poblado") == "CM":
            continue
        nombre = norm(d["nombre_centro_poblado"])
        if nombre.startswith("CIENAGA DE BARBACOA"):
            nombre = "CIENAGA DE BARBACOAS"
        dlon, dlat = float(d["longitud"].replace(",", ".")), float(d["latitud"].replace(",", "."))
        poly = cp_poligonos.get(d["codigo_centro_poblado"])
        area = Area(unir_geoms(poly["geoms"])) if poly else None
        if area:
            lon, lat = area.punto_interior()
            precision = "poligono_centroide"
        else:
            lon, lat, precision = dlon, dlat, "punto"
        if not en_limite(lon, lat):
            log["fuera_del_limite"].append(f"centro poblado {nombre} ({lat:.5f}, {lon:.5f})")
            continue
        vpad = lugar_de_vereda(lon, lat)
        alias = list(ALIAS_MANUALES.get(nombre, []))
        if norm(d["nombre_centro_poblado"]) != nombre:
            alias.append(norm(d["nombre_centro_poblado"]))
        N.agregar(nombre=nombre, tipo="centro_poblado", zona="rural", lat=r6(lat), lon=r6(lon), alias=alias,
                  fuente="dane", precision=precision, codigo_dane=d["codigo_centro_poblado"],
                  padre=vpad["nombre"] if vpad else None)
        # núcleo de la vereda homónima o de la que lo contiene
        homonima = vereda_por_nombre(nombre)
        if homonima and homonima["_area"].distancia_m(lon, lat) <= 500:
            poner_nucleo(homonima, lat, lon, "dane", precision, f"centro poblado {nombre} ({d['codigo_centro_poblado']})", 1)
        elif vpad:
            poner_nucleo(vpad, lat, lon, "dane", precision, f"centro poblado {nombre} ({d['codigo_centro_poblado']})", 2)

    for c in gob_cpob:  # centros poblados que solo trae la Gobernación (p. ej. Cuatro Bocas)
        if N.buscar(c.props["nombre"], ("centro_poblado",)):
            continue
        lon, lat = c.punto_interior()
        if not en_limite(lon, lat):
            continue
        vpad = lugar_de_vereda(lon, lat)
        N.agregar(nombre=c.props["nombre"], tipo="centro_poblado", zona="rural", lat=r6(lat), lon=r6(lon),
                  fuente="gobant", precision="poligono_centroide", padre=vpad["nombre"] if vpad else None,
                  nota="Centro poblado catastral de la Gobernación de Antioquia (no figura en la DIVIPOLA del DANE).")
        homonima = vereda_por_nombre(c.props["nombre"])
        if homonima and homonima["_area"].distancia_m(lon, lat) <= 500:
            poner_nucleo(homonima, lat, lon, "gobant", "poligono_centroide", f"centro poblado {c.props['nombre']}", 1)

    # Escuelas rurales → núcleos de vereda y caseríos con nombre propio
    fuentes_usadas.add("men")
    osm_escuelas = defaultdict(list)
    for r in osm.values():
        if r["tags"].get("amenity") == "school":
            osm_escuelas[nucleo_escuela(r["nombre"])].append(r)
    conteo_men_xy = Counter((f.get("coordenada_y_sede"), f.get("coordenada_x_sede")) for f in men)
    # el año más reciente de cada sede
    sedes = {}
    for f in sorted(men, key=lambda f: f.get("a_o") or ""):
        sedes[f.get("codigo_dane_sede") or f["nombre_sede"]] = f
    escuelas_validas = []
    for cod, f in sorted(sedes.items()):
        if (f.get("zona") or "").upper() != "RURAL":
            continue
        ver = vereda_men(f)
        if not ver:
            continue
        nucleo_nom = nucleo_escuela(f["nombre_sede"])
        lg_ver = vereda_por_nombre(ver)
        try:
            my, mx = float(f["coordenada_y_sede"]), float(f["coordenada_x_sede"])
        except (TypeError, ValueError, KeyError):
            my = mx = None
        men_ok = my is not None and abs(my) > 1 and conteo_men_xy[(f.get("coordenada_y_sede"), f.get("coordenada_x_sede"))] < 3
        candidatos = []  # (lat, lon, fuente, precision, ref)
        for r in osm_escuelas.get(nucleo_nom, []):
            candidatos.append((r["lat"], r["lon"], "osm", "punto", f"{r['nombre']} ({r['ref']})"))
        if cod in gob_sedes:
            candidatos.append((*gob_sedes[cod], "gobant", "punto", f"{f['nombre_sede']} (Gobernación, sede {cod})"))
        if men_ok:
            candidatos.append((my, mx, "men", "aproximado", f"{f['nombre_sede']} (MEN, sede {cod}, 2 decimales)"))
        elegido = None
        palabras = set(ver.split()) | set(nucleo_nom.split())
        for lat, lon, fu, pr, ref in candidatos:
            if not en_limite(lon, lat):
                continue
            v_cont = vereda_en(lon, lat)
            nucleo_v = set(clave(v_cont.props["nombre"]).split()) - PALABRAS_VACIAS if v_cont else set()
            if lg_ver is not None:
                ok = lg_ver["_area"].distancia_m(lon, lat) <= 300
            elif nucleo_v and nucleo_v <= palabras:
                # «BOCAS DE JABONAL» dentro de la vereda Jabonal; escuela «La Orquídea» dentro de La Orquídea
                ok = True
            elif men_ok and fu != "men":
                ok = math.hypot((lon - mx) * KX, (lat - my) * KY) <= 1500
            else:
                ok = fu == "men"
            if ok:
                elegido = (lat, lon, fu, pr, ref)
                break
        if not elegido:
            log["escuelas_sin_punto_valido"].append(f"{f['nombre_sede']} ({ver})")
            continue
        escuelas_validas.append((ver, nucleo_nom, *elegido))
        lat, lon, fu, pr, ref = elegido
        if fu == "gobant":
            fuentes_usadas.add("gobant_sedes")
        if fu == "osm":
            fuentes_usadas.add("osm")
        if lg_ver is not None:
            poner_nucleo(lg_ver, lat, lon, fu, pr, "escuela " + ref, 3 if pr == "punto" else 5)
        elif not N.buscar(ver):
            # lugar con nombre propio que solo conocemos por la escuela (p. ej. «EL TAMAR», «BOCAS DE JABONAL»)
            vpad = lugar_de_vereda(lon, lat)
            N.agregar(nombre=ver, tipo="caserio", zona="rural", lat=r6(lat), lon=r6(lon), fuente=fu, precision=pr,
                      padre=vpad["nombre"] if vpad else None,
                      nota=f"Ubicado por la escuela {ref}, cuya dirección es «VDA {ver}».")

    # Lugares de OSM (place=*)
    for r in sorted(osm.values(), key=lambda r: r["ref"]):
        t = r["tags"]
        lugar = t.get("place")
        if lugar not in ("village", "hamlet", "locality", "isolated_dwelling", "neighbourhood", "suburb", "quarter", "farm"):
            continue
        if t.get("divipola") and t["divipola"] != DIVIPOLA:
            continue
        nombre = norm(r["nombre"])
        if not nombre or clave(nombre) in ("YONDO", "CASABE"):
            continue
        if not en_limite(r["lon"], r["lat"]):
            continue
        fuentes_usadas.add("osm")
        existentes = N.buscar(nombre)
        vpad = lugar_de_vereda(r["lon"], r["lat"])
        if existentes:
            homonima = next((e for e in existentes if e["tipo"] == "vereda"), None)
            if homonima and homonima["_area"].distancia_m(r["lon"], r["lat"]) <= 500:
                poner_nucleo(homonima, r["lat"], r["lon"], "osm", "punto", f"place={lugar} {r['nombre']} ({r['ref']})", 2)
            else:
                lejos = min(math.hypot((r["lon"] - e["lon"]) * KX, (r["lat"] - e["lat"]) * KY)
                            for e in existentes if e.get("lat") is not None)
                if lejos > 3000:
                    log["osm_homonimos_descartados"].append(f"{nombre} {r['ref']} a {lejos / 1000:.1f} km del homónimo")
            continue
        urbano = es_urbano(r["lon"], r["lat"])
        tipo = ("barrio" if urbano else "sector") if lugar in ("neighbourhood", "suburb", "quarter") else \
            ("sector" if lugar == "locality" else "caserio")
        N.agregar(nombre=nombre, tipo=tipo, zona="urbana" if urbano else "rural", lat=r6(r["lat"]), lon=r6(r["lon"]),
                  fuente="osm", precision="punto", padre=(vpad["nombre"] if vpad else None) if not urbano else "YONDO",
                  nota=f"OpenStreetMap place={lugar} ({r['ref']}).")

    # Barrios de la cabecera
    nombres_barrio: dict[str, set] = defaultdict(set)
    for f in alcaldia:
        b = norm(f.get("nom_barrio"))
        b = BARRIO_ALCALDIA.get(b, b)
        if b and clave(f.get("nom_vereda") or "") == "SIN VEREDA":
            nombres_barrio[b].add("alcaldia")
    for f in gob_tabla:
        a = f["properties"] if "properties" in f else f.get("attributes", {})
        if a.get("Zona") != "U":
            continue
        b = norm(a.get("Nombre"))
        b = BARRIO_GOBANT.get(b, b)
        if b:
            nombres_barrio[b].add("gobant_barrios")
    anclas = defaultdict(list)
    for barrio, ref, lat, lon, fu, base in ANCLAS_BARRIO:
        if ref and ref in osm:  # coordenada OSM vigente
            lat, lon = osm[ref]["lat"], osm[ref]["lon"]
        if not en_limite(lon, lat) or not es_urbano(lon, lat):
            log["anclas_descartadas"].append(f"{barrio}: {base}")
            continue
        anclas[barrio].append((lat, lon, fu, base))
    for b in sorted(nombres_barrio):
        fuentes_b = sorted(nombres_barrio[b])
        fuentes_usadas.update(fuentes_b)
        a = anclas.get(b, [])
        if a:
            lat = sum(x[0] for x in a) / len(a)
            lon = sum(x[1] for x in a) / len(a)
            fu = "osm" if all(x[2] == "osm" for x in a) else "estimado"
            if any(x[2] == "estimado" for x in a):
                fuentes_usadas.add("repo_edificios")
            N.agregar(nombre=b, tipo="sector" if b == "BATALLON" else "barrio", zona="urbana", lat=r6(lat), lon=r6(lon),
                      alias=ALIAS_MANUALES.get(b), fuente=fu, precision="aproximado", padre="YONDO",
                      nombre_en=fuentes_b,
                      nota="Punto de un edificio público con dirección oficial en el barrio (no es el centroide): "
                           + "; ".join(x[3] for x in a))
        else:
            N.agregar(nombre=b, tipo="sector" if b == "BATALLON" else "barrio", zona="urbana",
                      alias=ALIAS_MANUALES.get(b), fuente="alcaldia" if "alcaldia" in fuentes_b else "gobant",
                      precision="sin_coordenada", padre="YONDO",
                      nombre_en=fuentes_b,
                      nota="Barrio reconocido en fuentes públicas sin coordenada pública; derivarla de las direcciones.")

    # Veredas que solo nombra la Alcaldía (sin polígono)
    for f in alcaldia:
        v = norm(f.get("nom_vereda"))
        if not v or v in ("SIN VEREDA",) or clave(v) == "X 10":
            continue
        if N.buscar(v):
            continue
        log["veredas_solo_alcaldia"].append(v)
        # ¿un rasgo de OSM con ese nombre (o «Ciénaga/Caño/Quebrada <nombre>») dentro del municipio?
        apoyo = [r for r in osm.values() if clave(r["nombre"]) in {clave(v), *(clave(f"{pre} {v}") for pre in
                 ("CIENAGA", "CANO", "QUEBRADA", "LAGUNA"))} and not r["tags"].get("amenity")]
        dentro_m = [r for r in apoyo if en_limite(r["lon"], r["lat"])]
        if dentro_m:
            r = dentro_m[0]
            vpad = lugar_de_vereda(r["lon"], r["lat"])
            N.agregar(nombre=v, tipo="sector", zona="rural", lat=r6(r["lat"]), lon=r6(r["lon"]), fuente="osm",
                      precision="aproximado", padre=vpad["nombre"] if vpad else None, nombre_en=["alcaldia"],
                      nota=f"La Alcaldía de Yondó la nombra como vereda; no es vereda catastral. Punto aproximado: "
                           f"«{r['nombre']}» en OpenStreetMap ({r['ref']}).")
            fuentes_usadas.add("osm")
            continue
        nota = "Vereda que nombra la Alcaldía de Yondó (datos abiertos) sin polígono ni punto público dentro del municipio."
        fuera = sorted((limite.distancia_m(r["lon"], r["lat"]), r) for r in apoyo if r["tags"].get("place"))
        if fuera and fuera[0][0] <= 3000:
            d, r = fuera[0]
            nota += (f" En OpenStreetMap «{r['nombre']}» ({r['ref']}, place={r['tags']['place']}"
                     + (f", DIVIPOLA {r['tags']['divipola']}" if r["tags"].get("divipola") else "")
                     + f") queda a {round(d)} m por fuera del límite municipal.")
        N.agregar(nombre=v, tipo="vereda", zona="rural", fuente="alcaldia", precision="sin_coordenada",
                  nombre_en=["alcaldia"], nota=nota)

    # Caseríos y sectores con una escuela homónima lejos (p. ej. «LA PRIMAVERA»)
    for lg in N.lugares:
        if lg["tipo"] not in ("caserio", "sector") or lg.get("lat") is None:
            continue
        for ver, nuc, lat, lon, fu, pr, ref in escuelas_validas:
            d = math.hypot((lon - lg["lon"]) * KX, (lat - lg["lat"]) * KY)
            if nuc == clave(lg["nombre"]) and d > 2000:
                lg["nota"] = (lg.get("nota", "") + f" Ojo: la escuela {ref} (dirección «VDA {ver}») queda a "
                              f"{d / 1000:.1f} km; una dirección «{lg['nombre']}» puede referirse a ese otro sitio.").strip()

    # Validación final: todo dentro del límite; limpiar campos internos
    lugares = []
    for lg in N.lugares:
        lg.pop("_area", None)
        if "nucleo" in lg:
            lg["nucleo"].pop("_p", None)
            if not en_limite(lg["nucleo"]["lon"], lg["nucleo"]["lat"]):
                lg.pop("nucleo")
        if lg.get("lat") is not None and not en_limite(lg["lon"], lg["lat"]):
            log["fuera_del_limite"].append(f"{lg['tipo']} {lg['nombre']} ({lg['lat']}, {lg['lon']})")
            continue
        alias = []
        for a in lg.get("alias", []):
            a = norm(a)
            if a and clave(a) != clave(lg["nombre"]) and a not in alias:
                alias.append(a)
        lg["alias"] = alias
        lugares.append(lg)

    orden_tipo = {"centro_poblado": 0, "corregimiento": 1, "vereda": 2, "caserio": 3, "sector": 4, "barrio": 5}
    lugares.sort(key=lambda lg: (lg["zona"] != "urbana", orden_tipo.get(lg["tipo"], 9), lg["nombre"]))
    campos = ["nombre", "tipo", "zona", "lat", "lon", "alias", "alias_ambiguos", "fuente", "precision", "padre",
              "codigo", "codigo_dane", "area_ha", "nucleo", "nombre_en", "nota", "geom"]
    lugares = [{k: lg[k] for k in campos if k in lg} for lg in lugares]

    gaz = {
        "descripcion": "Nomenclátor geográfico público de Yondó (Antioquia, DANE 05893): barrios, veredas, "
                       "corregimiento, centros poblados y caseríos. Coordenadas WGS84. Generado por build_gazetteer.py.",
        "generado": time.strftime("%Y-%m-%d"),
        "leyenda": {
            "fuente": {"dane": "DANE (MGN, DIVIPOLA, veredas)", "gobant": "Gobernación de Antioquia (catastro, sedes, tabla de barrios)",
                       "osm": "OpenStreetMap", "men": "MinEducación (sedes, coordenadas de 2 decimales)",
                       "alcaldia": "Alcaldía de Yondó, datos abiertos (solo el nombre)",
                       "estimado": "punto de un edificio público del levantamiento del repositorio"},
            "precision": {"poligono_centroide": "punto interior del polígono oficial (centroide si cae dentro)",
                          "punto": "punto publicado del lugar (centro poblado, caserío o su escuela)",
                          "aproximado": "punto con base real pero no central (edificio público del barrio, escuela con "
                                        "coordenada de 2 decimales, cuerpo de agua homónimo)",
                          "sin_coordenada": "nombre reconocido en fuentes públicas, sin coordenada pública; lat/lon = null"},
            "nucleo": "punto poblado dentro de la vereda (centro poblado, caserío OSM o escuela validada), útil como "
                      "alternativa al centroide del polígono",
            "alias_ambiguos": "alias de una sola letra; úsense solo tras la palabra VEREDA",
            "geom": "polígono simplificado (Douglas-Peucker, 50 m; la cabecera a 15 m), coordenadas lon/lat WGS84",
            "padre": "corregimiento, vereda o cabecera (YONDO) que contiene el lugar",
            "codigo": "código catastral de vereda de la Gobernación de Antioquia",
            "codigo_dane": "código DANE de vereda (8 dígitos, nivel de referencia 2024) o de centro poblado (DIVIPOLA)",
            "nombre_en": "fuentes públicas que listan el nombre",
        },
        "fuente": [f for f in FUENTES if f["id"] in fuentes_usadas],
        "lugares": lugares,
    }
    limite_fc = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"nombre": "YONDO", "codigo_dane": DIVIPOLA, "departamento": "ANTIOQUIA",
                           "fuente": fuente_limite, "area_km2": round(limite.area_m2() / 1e6, 1),
                           "url": FUENTES[0]["url"] if "DANE" in fuente_limite else "https://www.openstreetmap.org/relation/1316178"},
            "geometry": geom_redondeada(limite_rasgo["geometry"], 6),
        }],
    }
    return gaz, limite_fc, log


def cobertura(gaz: dict) -> tuple[list, list, list]:
    """Qué nombres de la lista del encargo quedan cubiertos (exacto, contenido) o faltan."""
    idx = {}
    for lg in gaz["lugares"]:
        for n in [lg["nombre"], *lg.get("alias", []), *lg.get("alias_ambiguos", [])]:
            idx.setdefault(clave(n), []).append(lg)
    exactos, contenidos, faltan = [], [], []
    for r in REQUERIDOS:
        c = clave(r)
        if c in idx:
            exactos.append((r, idx[c][0]))
            continue
        toks = c.split()
        hallado = None
        for largo in range(len(toks) - 1, 0, -1):
            for i in range(len(toks) - largo + 1):
                frase = " ".join(toks[i:i + largo])
                if frase in idx and len(frase) >= 5:
                    hallado = (r, idx[frase][0], frase)
                    break
            if hallado:
                break
        (contenidos if hallado else faltan).append(hallado or r)
    return exactos, contenidos, faltan


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--cache", type=Path, default=Path(tempfile.gettempdir()) / "yondo_gazetteer_cache")
    ap.add_argument("--offline", action="store_true", help="usar solo la caché")
    ap.add_argument("--sin-osm", action="store_true", help="no descargar teselas de OpenStreetMap")
    ap.add_argument("--salida", type=Path, default=AQUI)
    args = ap.parse_args()

    red = Red(args.cache, offline=args.offline)
    gaz, limite_fc, log = construir(red, usar_osm=not args.sin_osm)

    args.salida.mkdir(parents=True, exist_ok=True)
    (args.salida / "yondo_limite.geojson").write_text(json.dumps(limite_fc, ensure_ascii=False, separators=(",", ":")), "utf-8")
    texto = json.dumps(gaz, ensure_ascii=False, separators=(",", ":"))
    (args.salida / "gazetteer.json").write_text(texto, "utf-8")

    # Resumen
    print(f"Límite: {' | '.join(log['limite'])}")
    print(f"gazetteer.json: {len(texto) / 1e6:.2f} MB, {len(gaz['lugares'])} lugares")
    por_tipo = Counter((lg["tipo"], lg["precision"]) for lg in gaz["lugares"])
    for (t, p), n in sorted(por_tipo.items()):
        print(f"  {t:15s} {p:20s} {n}")
    for k in ("veredas_catastro", "osm_rasgos", "veredas_solo_alcaldia", "fuera_del_limite", "anclas_descartadas",
              "osm_homonimos_descartados", "escuelas_sin_punto_valido", "avisos"):
        if log.get(k):
            print(f"{k}: {'; '.join(log[k])}")
    exactos, contenidos, faltan = cobertura(gaz)
    print(f"Cobertura de la lista del encargo: {len(exactos)} exactos, {len(contenidos)} por nombre contenido, {len(faltan)} faltan")
    for r, lg, frase in contenidos:
        print(f"  contenido: {r} → «{frase}» ({lg['tipo']} {lg['nombre']})")
    print(f"  faltan: {', '.join(faltan)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
