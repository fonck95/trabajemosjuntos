"""Casos de borde del pipeline: direcciones escritas a mano, homónimos, fincas, agrupación de hermanos y archivos
dañados. Solo personas y direcciones inventadas; los lugares imitan la forma del nomenclátor público."""
import io
import json
import zipfile

import pytest

from app.pipeline import cruce, lectores
from app.pipeline import texto as tx
from app.pipeline.direcciones import Lugar, Nomenclator, leer
from app.pipeline.geocodificador import RAIZ_GEO, Geocodificador, GrillaCasco, _valor
from app.pipeline.lectores import FilaTramite
from conftest import TRAMITES, excel_cedulas, excel_tramites

SMDT = "SAN MIGUEL DEL TIGRE"
LUGARES = [
    Lugar(1, "CENTRAL", "barrio", "urbana", 7.006, -73.907, ("BARRIO CENTRAL", "EL CENTRO"), "YONDO"),
    Lugar(2, "EL PROGRESO", "barrio", "urbana", 7.011, -73.905, ("PROGRESO",), "YONDO"),
    Lugar(3, "LA PAZ", "barrio", "urbana", None, None, (), "YONDO"),
    Lugar(4, "LA PAZ", "vereda", "rural", 6.86, -74.14, (), None),
    Lugar(5, "EL PARAISO", "barrio", "urbana", None, None, ("PARAISO",), "YONDO"),
    Lugar(6, "EL PARAISO", "vereda", "rural", 6.98, -74.07, ("PARAISO",), None),
    Lugar(7, "CANO DON JUAN", "vereda", "rural", 7.007, -74.12, ("DON JUAN",), None),
    Lugar(8, "LA ROMPIDA 1", "vereda", "rural", 7.15, -73.95, ("LA ROMPIDA N 1", "LA ROMPIDA NO 1", "LA CEIBA"), SMDT),
    Lugar(9, "LA ROMPIDA 2", "vereda", "rural", 7.12, -73.94, ("LA ROMPIDA N 2", "LA ROMPIDA"), SMDT),
    Lugar(10, "LA UNION", "vereda", "rural", 6.90, -74.0, ("UNION",), None),
    Lugar(11, "BOCAS DE SAN FRANCISCO", "vereda", "rural", 7.0, -74.0, ("SAN FRANCISCO",), None),
    Lugar(12, "BOCAS DE DON JUAN", "vereda", "rural", 7.06, -74.0, ("BOCAS DE SAN JUAN",), None),
    Lugar(13, "BOCAS DE BARBACOAS", "centro_poblado", "rural", 6.73, -74.2, (), "BOCAS DE BARBACOAS"),
    Lugar(14, "LA CONDOR", "vereda", "rural", 7.03, -73.97, ("EL CONDOR",), None),
    Lugar(15, "LAS FLORES", "sector", "rural", 6.96, -73.95, (), "YONDO NUEVO"),
    Lugar(16, "LA PRIMAVERA", "sector", "rural", 6.95, -73.96, (), "SAN LUIS BELTRAN"),
    Lugar(17, "SAN LUIS BELTRAN", "centro_poblado", "rural", 6.95, -73.95, (), "SAN LUIS BELTRAN"),
    Lugar(18, "SAN LUIS BELTRAN", "vereda", "rural", 6.95, -73.95, (), None),
    Lugar(19, "EL TOTUMO", "vereda", "rural", 7.13, -74.0, ("TOTUMO",), SMDT),
    Lugar(20, SMDT, "centro_poblado", "rural", 7.088, -73.947, (), SMDT),
    Lugar(21, SMDT, "corregimiento", "rural", 7.088, -73.947, (), None),
    Lugar(22, "LA GLORIA", "sector", "rural", 6.82, -74.32, (), "SAN JUAN DE ITE"),
    Lugar(23, "PUERTO CASABE", "centro_poblado", "rural", 7.067, -73.9, ("PUERTO CAASABE",), "PUERTO CASABE"),
]


@pytest.fixture(scope="module")
def geo():
    # Plano sintético como el de test_pipeline: calles 45-58 y carreras 41-63
    puntos = [{"cl": c, "kr": k, "lat": 7.0 + (c - 45) * 0.0008, "lon": -73.90 - (k - 40) * 0.0009}
              for c in range(45, 59) for k in range(41, 64, 2)]
    return Geocodificador(Nomenclator(LUGARES), GrillaCasco(puntos))


def _lugar(geo, texto):
    _, u = geo.ubicar(texto)
    return u.lugar.id if u.lugar else None


# ───────────────────────────── Direcciones ─────────────────────────────

def test_cruce_con_letra_y_guion_se_ubica_por_la_grilla(geo):
    for texto in ("CL 47D # 55A-20", "KR 52 # 47D-15", "CALLE 48B # 45A-12", "KR 55 # 46A -16"):
        d, u = geo.ubicar(texto)
        assert d.tiene_placa and u.precision == "direccion", texto
    _, u = geo.ubicar("BARRIO CENTRAL KR 46 # 52A-10")
    assert u.precision == "direccion" and u.lugar.id == 1
    # «X-10» y «K-5» siguen siendo veredas
    assert leer("VEREDA X-10 FINCA LOS ALMENDROS").lugar_texto == "X10"
    assert leer("VEREDA K -5").lugar_texto == "K5"


def test_bis_no_es_la_letra_b():
    assert _valor("47 BIS") == pytest.approx(47.1)
    assert _valor("47BIS") == pytest.approx(47.1)
    assert _valor("47 BIS") != _valor("47B")
    assert 47.1 < _valor("47 BISA") < 47.15
    assert _valor("47A BIS") == pytest.approx(47.25)
    assert _valor("47D") == pytest.approx(47.6)


def test_las_referencias_no_son_el_lugar(geo):
    for texto in ("BARRIO CENTRAL CL 50 # 47-10 DONDE DON JUAN", "BARRIO CENTRAL CL 50 # 47-10 FRENTE A LA CEIBA"):
        _, u = geo.ubicar(texto)
        assert u.precision == "direccion" and u.zona == "urbana" and u.lugar.id == 1, texto
    d, u = geo.ubicar("BARRIO EL PROGRESO CL 50 # 47-10 AL LADO DE LA UNION")
    assert u.precision == "direccion" and u.lugar.id == 2 and d.referencia == "AL LADO DE LA UNION"
    assert _lugar(geo, "CERCA DEL PARQUE LA PAZ") is None
    assert _lugar(geo, "CL 50 # 47-10 CERCA AL BARRIO LA PAZ") is None
    # Si lo único nombrado está en la referencia con su palabra clave, al menos da ese lugar
    assert _lugar(geo, "CERCA A LA VEREDA LA UNION") == 10
    assert _lugar(geo, "JUNTO AL BARRIO CENTRAL") == 1
    # Lo que viene después de la referencia, con su palabra clave, sí cuenta
    assert _lugar(geo, "FRENTE A LA ESCUELA VEREDA LA CONDOR") == 14
    assert _lugar(geo, "VEREDA LA UNION CERCA DE LA ESCUELA") == 10
    # El centro poblado sigue mandando sobre el barrio homónimo del casco
    assert _lugar(geo, "SAN MIGUEL DEL TIGRE BARRIO CENTRAL") == 20


def test_homonimos_se_resuelven_con_la_placa_del_casco(geo):
    for texto, lid in (("LA PAZ CL 49 # 45-12", 3), ("CL 49 # 45-12 LA PAZ", 3), ("EL PARAISO KR 50 # 48-20", 5)):
        _, u = geo.ubicar(texto)
        assert u.lugar.id == lid and u.precision == "direccion" and u.zona == "urbana", texto
    # Con la palabra VEREDA, o sin placa, sigue siendo la vereda
    assert _lugar(geo, "VEREDA LA PAZ") == 4
    assert _lugar(geo, "VEREDA LA PAZ CL 49 # 45-12") == 4
    assert _lugar(geo, "LA PAZ") == 4
    # BARRIO + nombre de un sector rural, con placa del casco: manda la placa
    for texto in ("BARRIO LA PRIMAVERA CL 50 # 47-10", "URBANIZACION LAS FLORES KR 50 # 48-20",
                  "CL 50 # 47-10 SAN FRANCISCO"):
        _, u = geo.ubicar(texto)
        assert u.lugar is None and u.precision == "direccion" and u.zona == "urbana", texto


def test_b_barra_es_barrio(geo):
    assert _lugar(geo, "B/ LA PAZ") == 3
    assert _lugar(geo, "B. LA PAZ") == 3
    assert _lugar(geo, "B/ EL PARAISO") == 5
    _, u = geo.ubicar("CL 50 # 47-10 B/ CENTRAL")
    assert u.lugar.id == 1 and u.precision == "direccion"
    assert leer("CL 50 # 47B/ CENTRAL").cruce == "47B"  # pegada al número es letra


def test_la_finca_no_compite_y_la_vereda_explicita_manda(geo):
    assert _lugar(geo, "VEREDA LA CONDOR FINCA LAS FLORES") == 14
    assert _lugar(geo, "FINCA LAS FLORES VEREDA LA CONDOR") == 14
    assert _lugar(geo, "VEREDA SAN LUIS BELTRAN FINCA LA GLORIA") == 17
    assert _lugar(geo, "VEREDA LA CONDOR SECTOR LAS FLORES") == 14  # sector de otra vereda
    assert _lugar(geo, "VEREDA EL TOTUMO SAN MIGUEL DEL TIGRE") == 19
    assert _lugar(geo, "VEREDA SAN LUIS BELTRAN SECTOR LA PRIMAVERA") == 16  # sector dentro de la vereda
    _, u = geo.ubicar("FINCA LA GLORIA")
    assert u.lugar is None and u.zona == "rural"


def test_texto_corto_no_casa_con_un_alias_largo(geo):
    for texto in ("BOCAS", "PUERTO", "SANTA", "BARRIO SAN JUAN"):
        assert _lugar(geo, texto) is None, texto
    _, u = geo.ubicar("CL 49 # 45-12 BARRIO SAN JUAN")
    assert u.lugar is None and u.precision == "direccion"
    # Abreviatura de un solo lugar: se reconoce con menos confianza
    _, u = geo.ubicar("SAN MIGUEL")
    assert u.lugar.nombre == SMDT and u.confianza < 1
    # El alias contenido en el texto sigue valiendo
    assert _lugar(geo, "SAN MIGUEL DEL TIGRE BARR") == 20


def test_numero_de_vereda_con_no_y_numeral(geo):
    for texto in ("VEREDA LA ROMPIDA NO. 1", "VEREDA LA ROMPIDA #1", "VEREDA LA ROMPIDA # 1", "VDA LA ROMPIDA N.1",
                  "VEREDA LA ROMPIDA N° 1", "VEREDA LA ROMPIDA 1"):
        assert _lugar(geo, texto) == 8, texto
    assert _lugar(geo, "VEREDA LA ROMPIDA") == 9
    assert _lugar(geo, "VEREDA LA ROMPIDA NO. 2") == 9


def test_casos_reportados_con_el_nomenclator_y_la_grilla_publicos():
    """Los mismos casos con geo/gazetteer.json y geo/grilla_casco.json (geografía pública), cargados como en
    db.sembrar_lugares."""
    datos = json.loads((RAIZ_GEO / "gazetteer.json").read_text(encoding="utf-8"))
    lugares = []
    for i, lg in enumerate(datos["lugares"], 1):
        nombre, punto = tx.limpiar(lg["nombre"]), lg.get("nucleo") or {}
        alias = sorted({tx.limpiar(a) for a in [*lg.get("alias", []), *lg.get("alias_ambiguos", [])]} - {nombre})
        lugares.append(Lugar(i, nombre, lg["tipo"], lg.get("zona") or ("urbana" if lg["tipo"] == "barrio" else "rural"),
                             punto.get("lat", lg.get("lat")), punto.get("lon", lg.get("lon")), tuple(alias),
                             tx.limpiar(lg.get("padre")) or None))
    geo = Geocodificador(Nomenclator(lugares), GrillaCasco.desde_archivo())

    def ubicar(texto):
        _, u = geo.ubicar(texto)
        return (u.lugar.tipo, u.lugar.nombre) if u.lugar else None, u.precision

    for texto in ("CL 47D # 55A-20", "BARRIO CENTRAL CL 50 # 47-10 DONDE DON JUAN",
                  "BARRIO CENTRAL CL 50 # 47-10 FRENTE A LA CEIBA", "BARRIO EL PROGRESO CL 50 # 47-10 AL LADO DE LA UNION",
                  "LA PAZ CL 49 # 45-12", "EL PARAISO KR 50 # 48-20", "BARRIO LA PRIMAVERA CL 50 # 47-10",
                  "CL 49 # 45-12 BARRIO SAN JUAN", "CL 50 # 47-10 SAN FRANCISCO"):
        assert ubicar(texto)[1] == "direccion", texto
    assert ubicar("VEREDA LA ROMPIDA NO. 1")[0] == ("vereda", "LA ROMPIDA 1")
    assert ubicar("VEREDA LA ROMPIDA #1")[0] == ("vereda", "LA ROMPIDA 1")
    assert ubicar("VEREDA LA CONDOR FINCA LAS FLORES")[0][1] == "LA CONDOR"
    assert ubicar("VEREDA SAN LUIS BELTRAN FINCA LA GLORIA")[0][1] == "SAN LUIS BELTRAN"
    assert ubicar("VEREDA EL TOTUMO SAN MIGUEL DEL TIGRE")[0] == ("vereda", "EL TOTUMO")
    assert ubicar("VEREDA SAN LUIS BELTRAN SECTOR LA PRIMAVERA")[0] == ("sector", "LA PRIMAVERA")
    assert ubicar("SAN MIGUEL DEL TIGRE BARRIO CENTRAL")[0] == ("centro_poblado", SMDT)
    assert ubicar("B/ LA PAZ")[0] == ("barrio", "LA PAZ")
    for texto in ("BOCAS", "PUERTO", "CANO", "SANTA", "BARRIO SAN JUAN"):
        assert ubicar(texto)[0] is None, texto


# ───────────────────────────── Agrupación de trámites ─────────────────────────────

def _ft(i, nombre, tel, ficha, fecha="2025-01-01"):
    return FilaTramite(str(i), ficha, fecha, "NUEVA ENCUESTA", nombre, "", "", [tel] if tel else [], "")


@pytest.mark.parametrize("a,b", [
    ("JUAN CARLOS PEREZ GOMEZ", "JUAN CAMILO PEREZ GOMEZ"),
    ("DANIEL FELIPE ORTIZ MESA", "DANIELA FELIPE ORTIZ MESA"),
    ("ANDRES FELIPE MORA RIOS", "ANDREA FELIPA MORA RIOS"),
    ("LUZ MARINA TORRES DIAZ", "LUZ MARY TORRES DIAZ"),
    ("MARIA JOSE PEREZ ROA", "MARIA JOSEFA PEREZ ROA"),
    ("JUAN C PEREZ GOMEZ", "JUAN D PEREZ GOMEZ"),
])
def test_hermanos_con_la_misma_ficha_no_se_funden(a, b):
    assert len(cruce.agrupar_tramites([_ft(1, a, "3001112233", "F55"), _ft(2, b, "3001112233", "F55")])) == 2


@pytest.mark.parametrize("a,b", [
    ("FABIO MAURICO LEGUIZAMO PINILLA", "FABIO MAURICIO LEGUIZAMO PINILLA"),
    ("YESICA PAOLA RUEDA", "JESSICA PAOLA RUEDA"),
    ("MARIA DEL CARMEN ROJAS", "MARIA CARMEN ROJAS"),
    ("MARITZA LOPEZ GIL", "MARTIZA LOPEZ GIL"),
])
def test_errores_de_digitacion_con_dato_compartido_se_unen(a, b):
    assert len(cruce.agrupar_tramites([_ft(1, a, "3001112233", "F55"), _ft(2, b, "3001112233", "F55")])) == 1


def test_homonimos_sin_datos_en_comun_quedan_separados():
    grupos = cruce.agrupar_tramites([_ft(1, "JOSE GARCIA", "3001112233", "F1"),
                                     _ft(2, "JOSE GARCIA", "3109998877", "F2", "2025-03-01")])
    assert [(g.clave, g.separado_de, set(g.fichas)) for g in grupos] == [
        ("JOSE GARCIA", None, {"F1"}), ("JOSE GARCIA#F2", "JOSE GARCIA", {"F2"})]
    # Sin teléfono (o con un dato en común) no hay evidencia de que sean dos: sigue siendo una persona
    assert len(cruce.agrupar_tramites([_ft(1, "JOSE GARCIA", "3001112233", "F1"),
                                       _ft(2, "JOSE GARCIA", "", "F2", "2025-03-01")])) == 1
    assert len(cruce.agrupar_tramites([_ft(1, "JOSE GARCIA", "3001112233", "F1"),
                                       _ft(2, "JOSE GARCIA", "3001112233", "F2", "2025-03-01")])) == 1


# ───────────────────────────── Lectores ─────────────────────────────

def test_sexo_escrito_completo(tmp_path):
    filas = [(str(90000010 + i), f"PERSONA INVENTADA {n}", *[None] * 7, 30, sexo, None, None, None)
             for i, (n, sexo) in enumerate([("UNO", "MUJER"), ("DOS", "Hombre"), ("TRES", "Femenino"), ("CUATRO", "M"),
                                            ("CINCO", "f"), ("SEIS", "Otro")])]
    ruta = excel_cedulas(tmp_path / "c.xlsx", filas)
    assert [f.sexo for f in lectores.leer_cedulas(ruta)] == ["F", "M", "F", "M", "F", ""]


def _zip(ruta, miembros):
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as z:
        for nombre, datos in miembros.items():
            z.writestr(nombre, datos)
    return ruta


@pytest.mark.parametrize("contenido", [
    b"esto no es un zip",
    bytes.fromhex("D0CF11E0A1B11AE1") + b"\0" * 512,  # cabecera OLE2: un .xls renombrado
    b"",
], ids=["texto", "xls", "vacio"])
def test_archivo_que_no_es_xlsx_da_error_de_formato(tmp_path, contenido):
    ruta = tmp_path / "malo.xlsx"
    ruta.write_bytes(contenido)
    for f in (lectores.tipo_de_archivo, lambda r: list(lectores.leer_tramites(r)), lambda r: list(lectores.leer_cedulas(r))):
        with pytest.raises(ValueError, match="no es un Excel"):
            f(ruta)


def test_zip_sin_estructura_de_excel_da_error_de_formato(tmp_path):
    ruta = _zip(tmp_path / "vacio.xlsx", {"hola.txt": b"nada"})
    with pytest.raises(ValueError):
        lectores.tipo_de_archivo(ruta)


def test_bomba_zip_se_rechaza_antes_de_abrirla(tmp_path, monkeypatch):
    def no_abrir(*a, **k):
        raise AssertionError("openpyxl no debe abrir el archivo")

    # 8 MB de texto repetido caben en unos KB: razón de compresión imposible en un Excel real
    ruta = _zip(tmp_path / "bomba.xlsx", {"[Content_Types].xml": b"<Types/>",
                                          "xl/sharedStrings.xml": b"<si><t>A</t></si>" * (8 << 16)})
    monkeypatch.setattr(lectores.openpyxl, "load_workbook", no_abrir)
    with pytest.raises(ValueError, match="bomba zip"):
        lectores.tipo_de_archivo(ruta)
    # Tope del total descomprimido
    monkeypatch.setattr(lectores, "MAX_DESCOMPRIMIDO", 1 << 20)
    ruta = _zip(tmp_path / "grande.xlsx", {"xl/a.xml": bytes(range(256)) * 8192})
    with pytest.raises(ValueError, match="MB al descomprimirlo"):
        lectores.tipo_de_archivo(ruta)


def test_excel_normal_se_sigue_leyendo(tmp_path):
    ruta = excel_tramites(tmp_path / "t.xlsx", TRAMITES)
    assert lectores.tipo_de_archivo(ruta) == "tramites"
    assert len(list(lectores.leer_tramites(ruta))) == len(TRAMITES)


def test_api_responde_422_con_un_archivo_danado(sesion):
    for contenido in (b"no es zip", bytes.fromhex("D0CF11E0A1B11AE1") + b"\0" * 512):
        r = sesion.post("/api/importar", files=[("archivos", ("malo.xlsx", io.BytesIO(contenido).read()))])
        assert r.status_code == 422 and "no es un Excel" in r.json()["detail"]
