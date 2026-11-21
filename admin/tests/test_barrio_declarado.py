"""El barrio o vereda que la fuente trae en su propia columna («Barrio o vereda» de la base general y de la planilla)
ubica a la persona aunque la dirección lo tape con una descripción («AL LADO DE LA ESTACION 3, X-10»), sin quitarle a
la placa del casco la decisión entre homónimos ni a un lugar más preciso de la dirección su lugar.

Solo personas, direcciones y cédulas inventadas. Los lugares imitan la forma del nomenclátor público (y uno inventado:
un barrio de un centro poblado). Las pruebas del geocodificador y del lector corren sin MongoDB; las de la importación,
con MongoDB (como en CI)."""
from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from app.pipeline import lectores
from app.pipeline import importar as imp
from app.pipeline.direcciones import ANCLA, PALABRA_TIPO, PRIORIDAD, TIPO_PALABRA, Lugar, Nomenclator
from app.pipeline.geocodificador import Geocodificador, GrillaCasco
from ayudas_g1 import fila_planilla, importar as importar_planilla
from conftest import excel_planilla

SMDT = "SAN MIGUEL DEL TIGRE"
JARDIN = "EL JARDIN INVENTADO"  # barrio inventado de un centro poblado
LUGARES = [
    Lugar(1, "CENTRAL", "barrio", "urbana", 7.006, -73.907, ("BARRIO CENTRAL", "EL CENTRO"), "YONDO"),
    Lugar(2, "LA PAZ", "barrio", "urbana", None, None, (), "YONDO"),
    Lugar(3, "LA PAZ", "vereda", "rural", 6.86, -74.14, (), None),
    Lugar(4, "EL PRADO", "barrio", "urbana", None, None, ("PRADO",), "YONDO"),
    Lugar(5, "X-10", "vereda", "rural", 7.059, -73.913, ("X10", "LA X10", "VEREDA X-10"), None),
    Lugar(6, "LA CONDOR", "vereda", "rural", 7.03, -73.97, ("EL CONDOR",), None),
    Lugar(7, "EL TOTUMO", "vereda", "rural", 7.13, -74.0, ("TOTUMO",), SMDT),
    Lugar(8, SMDT, "centro_poblado", "rural", 7.088, -73.947, (), SMDT),
    Lugar(9, SMDT, "corregimiento", "rural", 7.088, -73.947, (), None),
    Lugar(10, JARDIN, "barrio", "urbana", 7.087, -73.948, (), SMDT),
]


@pytest.fixture(scope="module")
def geo():
    # Plano sintético como el de test_pipeline_casos: calles 45-58 y carreras 41-63
    puntos = [{"cl": c, "kr": k, "lat": 7.0 + (c - 45) * 0.0008, "lon": -73.90 - (k - 40) * 0.0009}
              for c in range(45, 59) for k in range(41, 64, 2)]
    return Geocodificador(Nomenclator(LUGARES), GrillaCasco(puntos))


def _donde(geo, direccion, barrio=None):
    """(id del lugar, precisión, zona, lugar escrito) de una dirección armada como la arma el lector: «dirección,
    barrio» si el barrio no está ya en ella."""
    texto = direccion if not barrio or barrio in direccion else f"{direccion}, {barrio}"
    _, u = geo.ubicar(texto, barrio)
    return (u.lugar.id if u.lugar else None), u.precision, u.zona, u.lugar_texto


# ───────────────────────────── Geocodificador (sin base) ─────────────────────────────

def test_la_vereda_de_su_columna_aunque_la_direccion_la_tape(geo):
    for direccion in ("AL LADO DE LA ESTACION 3", "CERCA DEL MANANTIAL VIA PRINCIPAL", "ESTADERO LAS MIRLAS"):
        assert _donde(geo, direccion, "X-10") == (5, "vereda", "rural", "X10"), direccion
        # Con la palabra clave en la columna, igual
        assert _donde(geo, direccion, "VEREDA X-10")[0] == 5, direccion
    # Un barrio y un corregimiento declarados, tras una referencia
    assert _donde(geo, "CERCA AL PARQUE INFANTIL", "EL PRADO")[:3] == (4, None, "urbana")
    assert _donde(geo, "AL LADO DE LA ESTACION 3", SMDT)[:3] == (8, "centro_poblado", "rural")
    # Otra vereda nombrada dentro de la referencia es solo la referencia: manda la de la columna
    assert _donde(geo, "CERCA A LA VEREDA LA CONDOR", "X-10")[0] == 5
    # Un barrio declarado que el nomenclátor no conoce queda como el lugar escrito (para crearlo o volverlo alias en
    # Calidad de datos), no la descripción entera
    assert _donde(geo, "ESTADERO LAS MIRLAS", "LOMA INVENTADA ZETA") == (None, None, None, "LOMA INVENTADA ZETA")
    # Sin barrio declarado, nada cambia
    assert _donde(geo, "VEREDA LA CONDOR FINCA EL RECREO") == (6, "vereda", "rural", "LA CONDOR")
    assert geo.ubicar("VEREDA LA CONDOR", "  ")[1].lugar.id == 6


def test_la_placa_del_casco_sigue_eligiendo_entre_homonimos(geo):
    # «LA PAZ» es barrio del casco y vereda: con una placa del casco, el barrio, aunque la referencia tape el nombre
    for direccion in ("CL 49 # 45-12", "CL 49 # 45-12 FRENTE A LA TIENDA LA PAZ", "KR 50 # 48-20 AL LADO DE LA IGLESIA"):
        lugar, precision, zona, _ = _donde(geo, direccion, "LA PAZ")
        assert (lugar, precision, zona) == (2, "direccion", "urbana"), direccion
    # Sin placa, la vereda (como «LA PAZ» escrito solo); con VEREDA en la dirección, también
    assert _donde(geo, "FRENTE A LA TIENDA LA PAZ", "LA PAZ")[:3] == (3, "vereda", "rural")
    assert _donde(geo, "VEREDA LA PAZ CL 49 # 45-12", "LA PAZ")[0] == 3
    # Una vereda declarada sin su palabra clave no se impone a la placa del casco (y como el nomenclátor la conoce, no
    # pasa por un nombre sin reconocer)
    assert _donde(geo, "CL 50 # 47-10 AL LADO DE LA TIENDA", "LA CONDOR") == (None, "direccion", "urbana", None)


def test_un_lugar_mas_preciso_de_la_direccion_sigue_ganando(geo):
    # Un barrio del centro poblado, o una vereda del corregimiento, nombrados en la dirección: siguen ganando
    assert _donde(geo, f"BARRIO {JARDIN} CERCA AL PARQUE", SMDT)[0] == 10
    assert _donde(geo, f"{JARDIN} AL LADO DE LA ESCUELA", SMDT)[0] == 10
    assert _donde(geo, "VEREDA EL TOTUMO FINCA LA ESPERANZA", SMDT)[0] == 7
    # Al revés, el lugar declarado más preciso gana al que lo contiene, aunque la referencia lo tape
    assert _donde(geo, f"{SMDT} AL LADO DE LA ESCUELA EL TOTUMO", "EL TOTUMO")[:3] == (7, "vereda", "rural")
    # El declarado mismo, o un homónimo suyo, no cambia nada
    assert _donde(geo, "BARRIO CENTRAL CL 50 # 47-10 DONDE DON JUAN", "CENTRAL")[:2] == (1, "direccion")


def test_palabra_clave_de_cada_tipo_de_lugar():
    # Cada tipo de lugar tiene una palabra que lo admite (TIPO_PALABRA) y que manda (ANCLA)
    assert set(PALABRA_TIPO) == set(PRIORIDAD)
    for tipo, palabra in PALABRA_TIPO.items():
        assert palabra in ANCLA and tipo in TIPO_PALABRA[palabra], tipo


def test_el_barrio_declarado_solo_acompana_a_la_direccion_de_su_fila():
    fila = {"fuente": "general", "clave": "1000000201",
            "datos": {"direccion": "AL LADO DE LA ESTACION 3, X-10", "lugar_texto": "X-10"}}
    p = {"direccion": "AL LADO DE LA ESTACION 3, X-10", "procedencia": {"direccion": {"fuente": "general"}},
         "origen": [{"fuente": "tramites", "clave": "1", "datos": {}}, fila]}
    assert imp.barrio_declarado(p) == "X-10"
    # La dirección cambió (otra fuente o una persona en el panel): ese barrio ya no la acompaña
    assert imp.barrio_declarado({**p, "direccion": "AL LADO DE LA ESTACION 3"}) is None
    assert imp.barrio_declarado({**p, "direccion": None}) is None
    # Sin barrio en la fila, o sin el origen de la fila (quien no autorizó), nada
    assert imp.barrio_declarado({**p, "origen": [{**fila, "datos": {"direccion": p["direccion"]}}]}) is None
    assert imp.barrio_declarado({**p, "origen": [{"fuente": "general", "clave": "x", "datos": {}}]}) is None
    # Dos filas con la misma dirección: la de la fuente de la dirección
    planilla = {"fuente": "planilla", "clave": "y", "datos": {**fila["datos"], "lugar_texto": "VEREDA X-10"}}
    assert imp.barrio_declarado({**p, "origen": [fila, planilla]}) == "X-10"
    otra = {**p, "procedencia": {"direccion": {"fuente": "planilla"}}, "origen": [planilla, fila]}
    assert imp.barrio_declarado(otra) == "VEREDA X-10"


# ───────────────────────────── Lectores (sin base) ─────────────────────────────

ENCABEZADOS = ["CC", "NOMBRE COMPLETO", "CONTACTO", "DIRECCIÓN", "BARRIO", "GRUPO"]
FILAS = [
    (1000000201, "ANA DECLARADA INVENTADA", 3101239901, "AL LADO DE LA ESTACION 3", "X-10", "Votante"),
    (1000000202, "BETO DECLARADO INVENTADO", 3101239902, "CERCA DEL MANANTIAL VIA PRINCIPAL", "X-10", "Votante"),
    (1000000203, "CARMEN DECLARADA INVENTADA", 3101239903, "CL 49 # 45-12 FRENTE A LA TIENDA LA PAZ", "LA PAZ",
     "Votante"),
    (1000000204, "DORA DECLARADA INVENTADA", 3101239904, f"BARRIO {JARDIN} CERCA AL PARQUE", SMDT, "Votante"),
    (1000000205, "ELIAS DECLARADO INVENTADO", 3101239905, "ESTADERO LAS MIRLAS", "LOMA INVENTADA ZETA", "Votante"),
]


def _excel_general(ruta: Path, filas=FILAS) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "BD_campana"
    ws.append(ENCABEZADOS)
    for f in filas:
        ws.append(list(f))
    wb.save(ruta)
    return ruta


def test_los_lectores_guardan_el_barrio_aparte_con_la_direccion_de_su_fila(tmp_path):
    """`barrio_declarado` lee el barrio del origen de la fila: la base general y la planilla lo dejan ahí junto a la
    dirección tal como queda en la ficha."""
    regs = list(lectores.leer_registros(_excel_general(tmp_path / "g.xlsx"), "general"))
    ana = regs[0]
    assert ana.direccion == "AL LADO DE LA ESTACION 3, X-10" and ana.lugar_texto == "X-10"
    assert (ana.datos["direccion"], ana.datos["lugar_texto"]) == (ana.direccion, "X-10")
    assert regs[2].direccion == "CL 49 # 45-12 FRENTE A LA TIENDA LA PAZ" and regs[2].datos["lugar_texto"] == "LA PAZ"
    planilla = excel_planilla(tmp_path / "p.xlsx", [fila_planilla(
        "1000000301", "FELIPA DECLARADA DE PLANILLA", "3101239911", direccion="CERCA DEL MANANTIAL VIA PRINCIPAL",
        barrio="X-10")])
    felipa = next(lectores.leer_registros(planilla, "planilla"))
    assert felipa.direccion == "CERCA DEL MANANTIAL VIA PRINCIPAL, X-10"
    assert (felipa.datos["direccion"], felipa.datos["lugar_texto"]) == (felipa.direccion, "X-10")


# ───────────────────────────── Importación (con MongoDB) ─────────────────────────────

def _lugar_id(db, nombre, tipo):
    return db.lugares.find_one({"nombre": nombre, "tipo": tipo}, {"_id": 1})["_id"]


def _con_jardin(db):
    from app import db as bd
    db.lugares.insert_one({"_id": bd.siguiente_id(db, "lugares"), "nombre": JARDIN, "tipo": "barrio", "zona": "urbana",
                           "lat": None, "lon": None, "alias": [], "padre": SMDT, "fuente": "manual", "precision": None,
                           "geom": None, "editado": True, "creado_en": bd.ahora()})


def test_la_base_general_ubica_con_el_barrio_de_su_columna(bases, tmp_path):
    db = bases()
    _con_jardin(db)
    imp.importar(db, [_excel_general(tmp_path / "g.xlsx")])
    x10 = _lugar_id(db, "X-10", "vereda")
    por = {p["cedula"]: p for p in db.personas.find({"cedula": {"$regex": "^10000002"}})}
    # Dirección descriptiva con la vereda en su columna: en la vereda
    for ced in ("1000000201", "1000000202"):
        assert (por[ced]["lugar_id"], por[ced]["zona"], por[ced]["geo_precision"]) == (x10, "rural", "vereda"), ced
        assert por[ced]["direccion_norm"].endswith("VDA. X-10"), ced
    # La placa del casco elige el barrio «LA PAZ», no la vereda
    carmen = por["1000000203"]
    assert carmen["lugar_id"] == _lugar_id(db, "LA PAZ", "barrio") and carmen["geo_precision"] == "direccion"
    # El barrio del centro poblado nombrado en la dirección gana al centro poblado declarado
    assert por["1000000204"]["lugar_id"] == _lugar_id(db, JARDIN, "barrio")
    # Un barrio declarado que no se conoce queda como lugar escrito, para Calidad de datos
    elias = por["1000000205"]
    assert elias["lugar_id"] is None and elias["lugar_texto"] == "LOMA INVENTADA ZETA"

    # Lo puesto a mano no se toca: el barrio o vereda elegido y el punto en el mapa
    db.personas.update_one({"_id": carmen["_id"]}, {"$set": {"geo_manual": "lugar", "lugar_id": x10}})
    db.personas.update_one({"_id": por["1000000202"]["_id"]}, {"$set": {
        "geo_manual": "punto", "lugar_id": None, "lat": 7.01, "lon": -73.91, "geo_precision": "manual"}})
    imp.georreferenciar(db)
    carmen = db.personas.find_one({"_id": carmen["_id"]})
    assert (carmen["lugar_id"], carmen["zona"]) == (x10, "rural")
    beto = db.personas.find_one({"_id": por["1000000202"]["_id"]})
    assert (beto["lugar_id"], beto["lat"], beto["geo_precision"]) == (None, 7.01, "manual")

    # Si alguien cambia la dirección en el panel, el barrio de la fila ya no la acompaña
    ana = por["1000000201"]
    db.personas.update_one({"_id": ana["_id"]}, {"$set": {
        "direccion": "AL LADO DE LA ESTACION 3",
        "procedencia.direccion": {"fuente": "panel", "ts": "2026-11-20T00:00:00+00:00", "uid": 0}}})
    imp.georreferenciar(db, [ana["_id"]])
    assert db.personas.find_one({"_id": ana["_id"]})["lugar_id"] is None

    # Reimportar no cambia a los demás
    imp.importar(db, [_excel_general(tmp_path / "g2.xlsx")])
    assert db.personas.find_one({"cedula": "1000000201"})["lugar_id"] is None  # su dirección es la del panel
    assert db.personas.find_one({"_id": carmen["_id"]})["lugar_id"] == x10


def test_la_planilla_ubica_con_el_barrio_de_su_columna(bases, tmp_path):
    db = bases()
    importar_planilla(db, tmp_path, planilla=[
        fila_planilla("1000000301", "FELIPA DECLARADA DE PLANILLA", "3101239911",
                      direccion="CERCA DEL MANANTIAL VIA PRINCIPAL", barrio="X-10"),
        fila_planilla("1000000302", "GUSTAVO DECLARADO DE PLANILLA", "3101239912",
                      direccion="CL 49 # 45-12 FRENTE A LA TIENDA LA PAZ", barrio="LA PAZ")])
    felipa = db.personas.find_one({"cedula": "1000000301"})
    assert (felipa["lugar_id"], felipa["zona"]) == (_lugar_id(db, "X-10", "vereda"), "rural")
    gustavo = db.personas.find_one({"cedula": "1000000302"})
    assert gustavo["lugar_id"] == _lugar_id(db, "LA PAZ", "barrio") and gustavo["geo_precision"] == "direccion"
