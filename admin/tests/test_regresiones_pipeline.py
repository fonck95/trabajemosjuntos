"""Regresiones del pipeline halladas en la segunda verificación: referencias que se comían el lugar, «ESQUINA» antes
del barrio, «MZ B.», «S.N.», nombres de una sola palabra, erratas de apellidos, nombres de pila invertidos y
homónimos en importaciones parciales. Solo personas y direcciones inventadas; los lugares son los del nomenclátor
público (geo/gazetteer.json)."""
import json

import pytest

from app import db as bd
from app.pipeline import cruce
from app.pipeline import texto as tx
from app.pipeline.direcciones import Lugar, Nomenclator, leer
from app.pipeline.geocodificador import RAIZ_GEO, Geocodificador, GrillaCasco
from app.pipeline.importar import importar
from app.pipeline.lectores import FilaTramite
from conftest import excel_tramites

SMDT = "SAN MIGUEL DEL TIGRE"


@pytest.fixture(scope="module")
def geo():
    """Nomenclátor y grilla públicos, cargados como en db.sembrar_lugares."""
    datos = json.loads((RAIZ_GEO / "gazetteer.json").read_text(encoding="utf-8"))
    lugares = []
    for i, lg in enumerate(datos["lugares"], 1):
        nombre, punto = tx.limpiar(lg["nombre"]), lg.get("nucleo") or {}
        alias = sorted({tx.limpiar(a) for a in [*lg.get("alias", []), *lg.get("alias_ambiguos", [])]} - {nombre})
        lugares.append(Lugar(i, nombre, lg["tipo"], lg.get("zona") or ("urbana" if lg["tipo"] == "barrio" else "rural"),
                             punto.get("lat", lg.get("lat")), punto.get("lon", lg.get("lon")), tuple(alias),
                             tx.limpiar(lg.get("padre")) or None))
    return Geocodificador(Nomenclator(lugares), GrillaCasco.desde_archivo())


def _ubicar(geo, texto):
    d, u = geo.ubicar(texto)
    lg = u.lugar
    return (lg.tipo, lg.nombre) if lg else None, u.precision, d.normalizada(lg.nombre if lg else None,
                                                                            lg.tipo if lg else None)


# ───────────────────────────── Referencias ─────────────────────────────

@pytest.mark.parametrize("texto,lugar", [
    ("FRENTE A LA ESCUELA DE LA CONDOR", ("centro_poblado", "LA CONDOR")),
    ("AL LADO DEL PUESTO DE SALUD DE SAN MIGUEL DEL TIGRE", ("centro_poblado", SMDT)),
    ("FRENTE A LA ESCUELA, SAN MIGUEL DEL TIGRE", ("centro_poblado", SMDT)),
    ("DIAGONAL AL COLEGIO, LA CONDOR", ("centro_poblado", "LA CONDOR")),
    ("CERCA AL COLEGIO, PUERTO CASABE", ("centro_poblado", "PUERTO CASABE")),
    ("AL LADO DE LA TIENDA, PUERTO CASABE, MZ 7 LT 20", ("centro_poblado", "PUERTO CASABE")),
    ("ANTES DEL PUENTE, EL PARAISO", ("vereda", "EL PARAISO")),
    ("DONDE DON PEDRO, LA CONDOR", ("centro_poblado", "LA CONDOR")),
    ("FRENTE AL PARQUE, B/ 23 DE JULIO", ("barrio", "23 DE JULIO")),
    ("FRENTE A LA CANCHA DEL BARRIO GAITAN, LA ROMPIDA 2", ("vereda", "LA ROMPIDA 2")),
    ("CERCA AL COLEGIO, BARBACOAS", ("vereda", "BARBACOAS")),
    ("AL LADO DE LA TIENDA - CENTRAL", ("barrio", "CENTRAL")),
    ("ATRAS DE LA ALCALDIA. EL PARAISO", ("vereda", "EL PARAISO")),
])
def test_referencia_al_principio_no_se_come_el_lugar(geo, texto, lugar):
    assert _ubicar(geo, texto)[0] == lugar


def test_las_referencias_siguen_sin_ser_el_lugar(geo):
    for texto in ("DETRAS DE LA CEIBA", "FRENTE A LA CEIBA", "CERCA DEL PARQUE LA PAZ", "CERCA DE LA PAZ",
                  "FRENTE A LA TIENDA, DONDE DON PEDRO", "ANTES DE LLEGAR A SAN MIGUEL"):
        assert _ubicar(geo, texto)[0] is None, texto
    # Con placa del casco, lo nombrado dentro de la referencia no se impone (tampoco tras «BRR.» con punto)
    for texto in ("CL 50 # 47-10 CERCA AL BARRIO LA PAZ", "CL 50 # 47-10 CERCA AL BRR. LA PAZ",
                  "CL 50 # 47-10 FRENTE A LA ESCUELA DE SAN MIGUEL DEL TIGRE"):
        assert _ubicar(geo, texto)[:2] == (None, "direccion"), texto
    # Lo nombrado fuera de la referencia manda sobre lo de dentro
    assert _ubicar(geo, "BARRIO CENTRAL FRENTE A LA ESCUELA DE SAN MIGUEL DEL TIGRE")[0] == ("barrio", "CENTRAL")
    assert _ubicar(geo, "VEREDA EL TOTUMO, CERCA DEL PUENTE DE SAN MIGUEL DEL TIGRE")[0] == ("vereda", "EL TOTUMO")
    # La referencia termina donde termina su trozo
    assert leer("FRENTE AL PARQUE, BARRIO LA PAZ CL 5 # 4-3").referencia == "FRENTE AL PARQUE"
    assert leer("BARRIO EL PROGRESO CL 50 # 47-10 AL LADO DE LA UNION").referencia == "AL LADO DE LA UNION"


@pytest.mark.parametrize("texto,lugar,norm", [
    ("CL 50 # 47-20 ESQUINA BARRIO VILLA MARIA", ("barrio", "VILLA MARIA"), "CL 50 # 47-20, B. VILLA MARIA"),
    ("ESQUINA, BARRIO LA PAZ, CL 50 # 47-20", ("barrio", "LA PAZ"), "CL 50 # 47-20, B. LA PAZ"),
    ("CL 50 # 47-20 ESQUINA, VILLA MARIA", ("barrio", "VILLA MARIA"), "CL 50 # 47-20, B. VILLA MARIA"),
    ("CL 50 # 47-20 ESQUINA B/ VILLA MARIA", ("barrio", "VILLA MARIA"), "CL 50 # 47-20, B. VILLA MARIA"),
    ("CL 50 # 47-20 ESQUINA, B. VILLA MARIA", ("barrio", "VILLA MARIA"), "CL 50 # 47-20, B. VILLA MARIA"),
    ("KR 50 # 50-10 ESQUINA BARRIO CENTRAL", ("barrio", "CENTRAL"), "KR 50 # 50-10, B. CENTRAL"),
    ("CL 50 # 47-20 LA ESQUINA BARRIO VILLA MARIA", ("barrio", "VILLA MARIA"), "CL 50 # 47-20, B. VILLA MARIA"),
])
def test_esquina_antes_del_barrio_no_se_lo_come(geo, texto, lugar, norm):
    assert _ubicar(geo, texto) == (lugar, "direccion", norm)


def test_esquina_con_vereda_y_esquina_de_algo(geo):
    assert _ubicar(geo, "CL 50 # 47-20 ESQUINA VEREDA LA PAZ")[0] == ("vereda", "LA PAZ")
    assert _ubicar(geo, "ESQUINA VEREDA NO TE PASES CALLE 48A BIS N 62 B 97")[0] == ("vereda", "NO TE PASES")
    # «ESQUINA DEL BARRIO…» sí es una referencia
    assert _ubicar(geo, "CL 50 # 47-20 ESQUINA DEL BARRIO VILLA MARIA")[:2] == (None, "direccion")


# ───────────────────────────── Nombres de una palabra ─────────────────────────────

def test_nombre_abreviado_de_una_palabra_con_alias_curado(geo):
    for texto, nombre in (("VEREDA BELTRAN", "SAN LUIS BELTRAN"), ("VDA BELTRAN", "SAN LUIS BELTRAN"),
                          ("VEREDA MATILDE", "PUERTO MATILDE"), ("VEREDA LAGRIMAS", "CHORRO DE LAGRIMAS"),
                          ("VEREDA MANGOS", "PUERTO LOS MANGOS")):
        assert _ubicar(geo, texto)[0] == ("centro_poblado", nombre), texto
    # Sin regla automática: lo ambiguo o genérico sigue sin reconocerse
    for texto in ("VEREDA LA ESPERANZA", "VEREDA ESPERANZA", "VDA CIMITARRA", "BOCAS", "PUERTO", "CANO", "SANTA"):
        assert _ubicar(geo, texto)[0] is None, texto


# ───────────────────────────── «MZ B.» y «S.N.» ─────────────────────────────

@pytest.mark.parametrize("texto,mz,lt,norm", [
    ("MZ B. LT 5 BARRIO LA PAZ", "B", "5", "MZ B LT 5, B. LA PAZ"),
    ("MZ. B. LT. 5", "B", "5", "MZ B LT 5"),
    ("MANZANA B. LOTE 12 VILLA MARIA", "B", "12", "MZ B LT 12"),
    ("MZA B. LOTE 3", "B", "3", "MZ B LT 3"),
    ("LOTE B. MZ 4", "4", "B", "MZ 4 LT B"),
    ("MZ B.LT 5", "B", "5", "MZ B LT 5"),
    ("MZ B/ LT 5", "B", "5", "MZ B LT 5"),
    ("CL 5 # 4-3 MZ B. LT 2", "B", "2", "CL 5 # 4-3, MZ B LT 2"),
    ("MZ 4 LT B. BARRIO LA PAZ", "4", "B", "MZ 4 LT B, B. LA PAZ"),
])
def test_letra_de_manzana_o_lote_con_punto_no_es_barrio(texto, mz, lt, norm):
    d = leer(texto)
    assert (d.mz, d.lt, d.normalizada()) == (mz, lt, norm)


def test_manzana_con_letra_en_la_direccion_normalizada(geo):
    assert _ubicar(geo, "MANZANA B. LOTE 12 VILLA MARIA")[2] == "MZ B LT 12, B. VILLA MARIA"
    assert _ubicar(geo, "LOTE B. MZ 4 BARRIO TRES DE OCTUBRE")[2] == "MZ 4 LT B, B. TRES DE OCTUBRE"


def test_b_con_punto_o_barra_sigue_siendo_barrio():
    for texto in ("B. LA PAZ", "B/ LA PAZ", "MZ 4 LT 5, B. LA PAZ", "CL 5 # 4-3, B. LA PAZ", "CL 5 # 4-3 B/LA PAZ"):
        d = leer(texto)
        assert (d.tipo_lugar, d.lugar_texto) == ("BARRIO", "LA PAZ"), texto
    assert leer("MZ 4 LT 5, B. LA PAZ").normalizada() == "MZ 4 LT 5, B. LA PAZ"


@pytest.mark.parametrize("texto", ["S.N.", "CASA S.N.", "s.n.", "S. N.", "S N.", "S.N.,", "S/N", "S.N", "SIN NOMENCLATURA"])
def test_s_n_con_puntos_es_sin_nomenclatura(texto):
    d = leer(texto)
    assert d.sin_nomenclatura and d.normalizada() == "SIN NOMENCLATURA"


def test_n_con_punto_sigue_siendo_numeral():
    assert leer("CL 45 N. 12-30").via_texto() == "CL 45 # 12-30"
    assert leer("KR 54 No. 51-20").via_texto() == "KR 54 # 51-20"
    assert leer("CALLE 10 NRO. 5-20").via_texto() == "CL 10 # 5-20"
    assert not leer("CL 45 N. 12-30").sin_nomenclatura
    assert leer("BARRIO LA PAZ S.N.").sin_nomenclatura


# ───────────────────────────── Agrupación de trámites ─────────────────────────────

def _ft(i, nombre, tel, ficha, fecha="2025-01-01"):
    return FilaTramite(str(i), ficha, fecha, "NUEVA ENCUESTA", nombre, "", "", [tel] if tel else [], "")


def _grupos(a, b, tel_a="3001112233", tel_b="3001112233", ficha_a="F55", ficha_b="F55"):
    return cruce.agrupar_tramites([_ft(1, a, tel_a, ficha_a), _ft(2, b, tel_b, ficha_b, "2025-02-01")])


@pytest.mark.parametrize("a,b", [
    ("LUZ MARINA ROJAS SOTO", "LUZ MARINA ROJA SOTO"),
    ("JUAN CARLOS PEREZ GOMEZ", "JUAN CARLOS PREZ GOMEZ"),
    ("TEOFILO ARRIETA BUELVAS", "TEOFILO ARRIETA BUELVSA"),
    ("NUBIA ESTHER OSPINA MEJIA", "NUBIA ESTHER OSPINO MEJIA"),
    ("ELKIN SOTO VEGA", "ELKIN SOTA VEGA"),
    ("ANA ARIAS MORA", "ANA ARIA MORA"),
    ("YOLIMA CUADRADO", "YOLIMA CUADRADA"),
    ("FLORALBA PEREZ GIL", "FLORALAB PEREZ GIL"),
    ("JUAN C PANTOJA GOMEZ", "JUAN PANTOJA GOMEZ"),
    ("ARRIETA BUELVAS JOSE MARIA", "JOSE MARIA ARRIETA BUELVAS"),
])
def test_erratas_con_la_misma_ficha_y_celular_se_unen(a, b):
    assert len(_grupos(a, b)) == 1


@pytest.mark.parametrize("a,b", [
    ("JOSE MARIA ARRIETA BUELVAS", "MARIA JOSE ARRIETA BUELVAS"),
    ("LUIS ANGEL SOLANO YEPES", "ANGEL LUIS SOLANO YEPES"),
    ("ANA MARIA PEREZ ROA", "MARIA ANA PEREZ ROA"),
])
def test_nombres_de_pila_invertidos_son_dos_personas(a, b):
    assert len(_grupos(a, b)) == 2  # misma ficha y celular
    assert len(_grupos(a, b, tel_b="3115550004")) == 2  # solo la ficha
    assert len(_grupos(a, b, ficha_b="F56")) == 2  # solo el celular del hogar


def test_una_inicial_que_sirve_a_dos_hermanos_no_los_une():
    grupos = cruce.agrupar_tramites([_ft(1, "JUAN C PEREZ GOMEZ", "3001112233", "F7"),
                                     _ft(2, "JUAN D PEREZ GOMEZ", "3001112233", "F7"),
                                     _ft(3, "JUAN PEREZ GOMEZ", "3001112233", "F7")])
    assert not any({"JUAN C PEREZ GOMEZ", "JUAN D PEREZ GOMEZ"} <= set(g.nombres) for g in grupos)


def test_nombre_de_pila_casi_igual_queda_aparte_pero_a_revision():
    grupos = _grupos("ROSALBA BARRAGAN CRUZ", "OSALBA BARRAGAN CRUZ")
    assert len(grupos) == 2 and sum(len(g.parecidos) for g in grupos) == 1
    grupos = _grupos("DANIEL ORTIZ MESA", "DANIELA ORTIZ MESA")
    assert len(grupos) == 2 and sum(len(g.parecidos) for g in grupos) == 1
    # Solo con la ficha del hogar (sin el mismo celular) no va a revisión; y dos nombres distintos tampoco
    assert sum(len(g.parecidos) for g in _grupos("ROSALBA BARRAGAN CRUZ", "OSALBA BARRAGAN CRUZ", tel_b="3115550004")) == 0
    assert sum(len(g.parecidos) for g in _grupos("JUAN CARLOS PEREZ GOMEZ", "JUAN CAMILO PEREZ GOMEZ")) == 0


# ───────────────────────────── Importación (MongoDB) ─────────────────────────────

NOMBRE = "TEOFILO ARRIETA BUELVAS"
FA, TA, CA = "0589311111111", "3001110000", "teofilo.a@ejemplo.test"
FB, TB, CB = "0589322222222", "3002220000", "teofilo.b@ejemplo.test"


def _fila(i, quien, fecha):
    ficha, tel, correo = (FA, TA, CA) if quien == "A" else (FB, TB, CB)
    return (str(i), ficha, f"{fecha} 12:00:00 AM", f"NUEVA ENCUESTA - {NOMBRE}", "VEREDA LA CONDOR", correo, tel, 1)


A1, B1 = _fila(7001, "A", "2/2/2024"), _fila(7002, "B", "3/3/2024")
B0, B2, A2 = _fila(7000, "B", "1/1/2023"), _fila(7003, "B", "4/4/2025"), _fila(7004, "A", "5/5/2025")


def _estado(db):
    """{ficha → ids de trámite} de las personas con ese nombre, y sus correos, y los pares pendientes entre ellas."""
    personas = list(db.personas.find({**bd.ACTIVA, "nombre_norm": NOMBRE}))
    tramites = {p["_id"]: {t["id_externo"] for t in p["tramites"]} for p in personas}
    correos = {p["_id"]: p.get("correo") for p in personas}
    pares = db.coincidencias.count_documents({"estado": "pendiente", "detalle.homonimo": True})
    return tramites, correos, pares


@pytest.mark.parametrize("segunda", [
    [B1, B2],          # el archivo de la otra vereda, completo
    [B2],              # solo lo nuevo de B
    [A2, B2],          # lo nuevo de los dos, B con el trámite más antiguo
    [B0, A1, B1, B2],  # todo, con una fila vieja de B que no estaba antes
    [A1, B1, B2],
    [A2],
], ids=["B1-B2", "B2", "A2-B2", "B0-A1-B1-B2", "A1-B1-B2", "A2"])
def test_homonimos_separados_siguen_separados_en_importaciones_parciales(bases, tmp_path, segunda):
    db = bases()
    importar(db, [excel_tramites(tmp_path / "1.xlsx", [A1, B1])])
    importar(db, [excel_tramites(tmp_path / "2.xlsx", segunda)])
    tramites, correos, pares = _estado(db)
    de_a = {f[0] for f in [A1, B1, B0, B2, A2, *segunda] if f[1] == FA}
    de_b = {f[0] for f in [A1, B1, B0, B2, A2, *segunda] if f[1] == FB}
    esperado = sorted([sorted(de_a & {f[0] for f in [A1, B1, *segunda]}), sorted(de_b & {f[0] for f in [A1, B1, *segunda]})])
    assert sorted(sorted(t) for t in tramites.values()) == esperado
    pid_a = next(p for p, t in tramites.items() if "7001" in t)
    assert correos[pid_a] == CA  # los datos de B no pasan a la ficha de A
    assert pares == 1


def test_homonimo_nuevo_mas_antiguo_no_cae_en_la_ficha_existente(bases, tmp_path):
    """Primero solo A; luego un archivo con A y un homónimo B cuyo trámite es más antiguo."""
    db = bases()
    importar(db, [excel_tramites(tmp_path / "1.xlsx", [A1])])
    importar(db, [excel_tramites(tmp_path / "2.xlsx", [A2, B2])])
    tramites, correos, pares = _estado(db)
    assert sorted(sorted(t) for t in tramites.values()) == [["7001", "7004"], ["7003"]]
    assert pares == 1
    # Reimportar lo mismo no cambia nada ni duplica el par
    importar(db, [excel_tramites(tmp_path / "3.xlsx", [A1, A2, B2])])
    assert _estado(db) == (tramites, correos, pares)


VARIANTES = [("8001", "0589340000004", "2/2/2024 12:00:00 AM", "NUEVA ENCUESTA - ROSALBA BARRAGAN CRUZ",
              "VEREDA LA CONDOR", "", "3004440004", 1),
             ("8002", "0589340000004", "3/3/2024 12:00:00 AM", "REENCUESTA - OSALBA BARRAGAN CRUZ",
              "VEREDA LA CONDOR", "", "3004440004", 1),
             ("8003", "0589340000004", "3/3/2024 12:00:00 AM", "NUEVA ENCUESTA - LUZ MARINA ROJAS SOTO",
              "VEREDA LA CONDOR", "", "3004440004", 1),
             ("8004", "0589340000004", "4/4/2024 12:00:00 AM", "REENCUESTA - LUZ MARINA ROJA SOTO",
              "VEREDA LA CONDOR", "", "3004440004", 1)]


def test_variante_del_nombre_de_pila_va_a_revision(bases, tmp_path):
    db = bases()
    filas = VARIANTES
    importar(db, [excel_tramites(tmp_path / "1.xlsx", filas)])
    # La errata del apellido se une sola; la del nombre de pila queda en dos fichas con un par por revisar
    assert db.personas.count_documents(bd.ACTIVA) == 3
    pares = list(db.coincidencias.find({"estado": "pendiente"}))
    assert len(pares) == 1 and pares[0]["detalle"].get("variante")
    nombres = {p["nombre"] for p in db.personas.find({"_id": {"$in": [pares[0]["persona_id"], pares[0]["candidato_id"]]}})}
    assert nombres == {"ROSALBA BARRAGAN CRUZ", "OSALBA BARRAGAN CRUZ"}
    # Rechazado, no vuelve al reimportar
    db.coincidencias.update_one({"_id": pares[0]["_id"]}, {"$set": {"estado": "rechazada"}})
    importar(db, [excel_tramites(tmp_path / "2.xlsx", filas)])
    assert db.coincidencias.count_documents({"estado": "pendiente"}) == 0
    assert db.personas.count_documents(bd.ACTIVA) == 3


def test_api_muestra_y_resuelve_el_par_de_variantes(sesion, tmp_path):
    ruta = excel_tramites(tmp_path / "v.xlsx", VARIANTES)
    r = sesion.post("/api/importar", files=[("archivos", (ruta.name, ruta.read_bytes()))])
    assert r.status_code == 200, r.text
    pares = sesion.get("/api/coincidencias").json()
    assert len(pares) == 1 and pares[0]["detalle"]["variante"] and pares[0]["detalle"]["telefono"]
    assert {pares[0]["persona"]["nombre"], pares[0]["candidato"]["nombre"]} == {"ROSALBA BARRAGAN CRUZ",
                                                                              "OSALBA BARRAGAN CRUZ"}
    total = sesion.get("/api/personas").json()["total"]
    assert sesion.post(f"/api/coincidencias/{pares[0]['id']}", json={"decision": "aceptar"}).status_code == 200
    assert sesion.get("/api/personas").json()["total"] == total - 1
    assert sesion.get("/api/coincidencias").json() == []
