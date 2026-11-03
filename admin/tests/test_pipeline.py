"""Normalización, lectura de direcciones, georreferenciación y cruce por nombre (sin base de datos)."""
from app.pipeline import cruce, texto as tx
from app.pipeline.direcciones import Lugar, Nomenclator, leer
from app.pipeline.geocodificador import Geocodificador, GrillaCasco
from app.pipeline.lectores import FilaCedula, FilaTramite


def test_telefonos_y_correos():
    assert tx.telefonos("+57 300 111 2233") == ["3001112233"]
    assert tx.telefonos("3001112233 / 3014445566") == ["3001112233", "3014445566"]
    assert tx.telefonos("0000000") == []
    assert tx.correo("ZOILA@GMAIL.COMK") == "zoila@gmail.com"
    assert tx.correo("notiene@gmail.com") == ""
    assert tx.cedula(90000001.0) == "90000001"
    assert tx.cedula("1111111") == ""


def test_tramite_y_nombres():
    assert tx.separar_tramite("MODIFICACIÓN DE FICHA - ODILIA  SARMIENTO") == ("MODIFICACION DE FICHA", "ODILIA SARMIENTO")
    assert tx.tokens_nombre("MARIA DELCARMEN DE LA OSSA") == ["MARIA", "CARMEN", "OSSA"]
    assert tx.fonetico("JHON") == tx.fonetico("JOHN")
    assert tx.fonetico("NUVIA") == tx.fonetico("NUBIA")
    assert tx.fonetico("YANETH") == tx.fonetico("JANETH")


def test_leer_direcciones():
    d = leer("BARRIO TRES DE OCTUBRE CALLE 49 # 45  12")
    assert (d.via, d.num, d.cruce, d.placa) == ("CL", "49", "45", "12")
    assert d.lugar_texto == "TRES DE OCTUBRE" and d.tipo_lugar == "BARRIO"
    assert leer("JORGE ELIECER GAITAN, KR 54# 51-20 FRENTE AL PARQUE").normalizada() == "KR 54 # 51-20, JORGE ELIECER GAITAN"
    assert leer("BARRIO NUEVA ESPERANZAMANZANA 4 LOTE 18").normalizada() == "MZ 4 LT 18, B. NUEVA ESPERANZA"
    assert leer("CRA 40 CON CALLE 45  22").via_texto() == "KR 40 # 45-22"
    assert leer("CLL 52 N 4610").via_texto() == "CL 52 # 46-10"
    assert leer("K 45 # 12-30").via_texto() == "KR 45 # 12-30"
    assert leer("VEREDA X-10 FINCA LOS ALMENDROS").lugar_texto == "X10"
    assert leer("VEREDA K -5").lugar_texto == "K5"
    assert leer("FINCA EL MANANTIAL").finca == "EL MANANTIAL"


LUGARES = [
    Lugar(1, "TRES DE OCTUBRE", "barrio", "urbana", 7.0074, -73.9076, (), "YONDO"),
    Lugar(2, "X-10", "vereda", "rural", 7.05, -73.90, ("X10",), None),
    Lugar(3, "SAN LUIS BELTRAN", "centro_poblado", "rural", 6.96, -73.95, (), None),
    Lugar(4, "LA PAZ", "barrio", "urbana", None, None, ("URBANIZACION LA PAZ",), "YONDO"),
    Lugar(5, "LA PAZ", "vereda", "rural", 6.9, -74.0, (), None),
]


def test_nomenclator_respeta_la_palabra_clave():
    nom = Nomenclator(LUGARES)
    assert nom.reconocer(leer("VEREDA LA PAZ"))[0].id == 5
    assert nom.reconocer(leer("URBANIZACION LA PAZ MZ 3"))[0].id == 4
    assert nom.reconocer(leer("VEREDA X-10 CERCA DE LA ESCUELA"))[0].id == 2
    assert nom.reconocer(leer("VEREDA SAN LUIS BELTRAN EN EL CASERIO"))[0].id == 3
    assert nom.reconocer(leer("SAN LUIZ BELTRAN"))[0].id == 3  # error de digitación


def _grilla():
    # Plano sintético: cada calle sube 0.0008° de latitud y cada carrera resta 0.0009° de longitud
    puntos = [{"cl": c, "kr": k, "lat": 7.0 + (c - 45) * 0.0008, "lon": -73.90 - (k - 40) * 0.0009}
              for c in range(45, 59) for k in range(41, 64, 2)]
    return GrillaCasco(puntos)


def test_grilla_interpola_calles_y_placas():
    g = _grilla()
    lat, lon, dist = g.ubicar(49, 44.7)
    assert abs(lat - 7.0032) < 1e-6 and abs(lon - (-73.90423)) < 1e-6 and dist < 1
    assert g.ubicar(10, 10) is None  # fuera de la grilla


def test_geocodificador_prefiere_la_placa_y_cae_al_lugar():
    geo = Geocodificador(Nomenclator(LUGARES), _grilla())
    _, u = geo.ubicar("BARRIO TRES DE OCTUBRE CALLE 49 # 45  12")
    assert u.precision == "direccion" and u.lugar.id == 1
    _, u = geo.ubicar("VEREDA X-10 FINCA LOS ALMENDROS")
    assert u.precision == "vereda" and (u.lat, u.lon) == (7.05, -73.90)
    _, u = geo.ubicar("URBANIZACION LA PAZ MZ 3")  # barrio sin punto: se reconoce pero no se inventa coordenada
    assert u.lugar.id == 4 and u.lat is None
    _, u = geo.ubicar("FINCA EL MANANTIAL")
    assert u.lat is None and u.zona == "rural"


def _ft(i, nombre, tel, ficha="1"):
    return FilaTramite(str(i), ficha, "2025-01-01", "NUEVA ENCUESTA", nombre, "", "", [tel] if tel else [], "")


def _fc(ced, nombre, tels=()):
    return FilaCedula(ced, nombre, list(tels), "", "", "", "", "", "", None, "", "", "", [], "", "")


def test_agrupar_une_variantes_solo_con_dato_compartido():
    filas = [_ft(1, "FABIO MAURICO LEGUIZAMO PINILLA", "3001"), _ft(2, "FABIO MAURICIO LEGUIZAMO PINILLA", "3001"),
             _ft(3, "FABIO MAURICIO LEGUIZAMO PINILLA", "3999"), _ft(4, "ANA PINILLA", "3001")]
    grupos = cruce.agrupar_tramites(filas)
    assert len(grupos) == 2


def test_cruce_por_nombre():
    personas = cruce.agrupar_tramites([
        _ft(1, "TEODULO DE JESUS ARBELAEZ MONTOYA", "3001112233"),
        _ft(2, "ROSALBA QUIÑONES ZAPATEIRO", "3027778899"),
        _ft(3, "MARTHA NUBIA ESCORCIA", "3035550000"),
        _ft(4, "HERNAN PATIÑO", ""), _ft(5, "HERNAN PATIÑO SUAREZ", ""),
    ])
    res = {r.fila.cedula: r for r in cruce.cruzar(personas, [
        _fc("1", "ARBELAEZ MONTOYA TEODULO DE JESUS", ["3001112233"]),  # orden invertido + mismo teléfono
        _fc("2", "YURANI ANDREA QUIÑONES ZAPATEIRO", ["3027778899"]),      # hija con el teléfono de la madre: no se une
        _fc("3", "MARTHA NUVIA ESCORCIA"),                          # variante fonética
        _fc("4", "JUAN HERNAN PATIÑO"),                                # ambiguo
    ])}
    assert res["1"].estado == "auto" and personas[res["1"].mejor.indice].nombre.startswith("TEODULO")
    assert res["2"].estado == "sin_coincidencia"
    assert res["3"].estado == "auto"
    assert res["4"].estado != "auto"
