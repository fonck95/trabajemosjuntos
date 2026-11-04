"""Ajustes posteriores a la revisión: homónimos a revisión, filtro «sin barrio o vereda», límite de archivos y
errores de formato con el nombre del archivo. Solo datos inventados."""
from conftest import CEDULAS, TRAMITES, excel_cedulas, excel_tramites


def _subir(c, *rutas):
    archivos = [("archivos", (r.name, r.read_bytes())) for r in rutas]
    return c.post("/api/importar", files=archivos)


def test_homonimos_separados_van_a_revision(sesion, tmp_path):
    filas = [
        ("2001", "0589300000101", "1/3/2025 12:00:00 AM", "NUEVA ENCUESTA - ELADIO FERNEY CUESTA MORANTES",
         "VEREDA X-10", "", "3101112233", 1),
        ("2002", "0589300000202", "2/4/2025 12:00:00 AM", "NUEVA ENCUESTA - ELADIO FERNEY CUESTA MORANTES",
         "VEREDA LA CONDOR", "", "3209998877", 1),
    ]
    r = _subir(sesion, excel_tramites(tmp_path / "h.xlsx", filas))
    assert r.status_code == 200, r.text
    personas = sesion.get("/api/personas", params={"q": "CUESTA MORANTES"}).json()
    assert personas["total"] == 2
    pares = sesion.get("/api/coincidencias").json()
    homonimos = [p for p in pares if p["detalle"].get("homonimo")]
    assert len(homonimos) == 1
    assert {homonimos[0]["persona"]["id"], homonimos[0]["candidato"]["id"]} == {f["id"] for f in personas["filas"]}
    # Reimportar no duplica el par
    _subir(sesion, excel_tramites(tmp_path / "h2.xlsx", filas))
    assert len([p for p in sesion.get("/api/coincidencias").json() if p["detalle"].get("homonimo")]) == 1


def test_lugar_cero_filtra_sin_barrio_ni_vereda(sesion, tmp_path):
    _subir(sesion, excel_tramites(tmp_path / "t.xlsx", TRAMITES), excel_cedulas(tmp_path / "c.xlsx", CEDULAS))
    nueva = sesion.post("/api/personas", json={"nombre": "Persona Inventada Sin Direccion", "forzar": True}).json()
    todas = sesion.get("/api/personas").json()["total"]
    sin = sesion.get("/api/personas", params={"lugar_id": 0}).json()
    assert [f["id"] for f in sin["filas"]] == [nueva["id"]] and sin["total"] < todas
    assert sesion.get("/api/personas", params={"lugar_id": 0, "q": "QUINTERO"}).json()["total"] == 0


def test_mas_de_seis_archivos_se_rechaza(sesion, tmp_path):
    ruta = excel_tramites(tmp_path / "t.xlsx", TRAMITES)
    r = _subir(sesion, *([ruta] * 7))
    assert r.status_code == 422 and "6 archivos" in r.json()["detail"]


def test_error_de_formato_nombra_el_archivo(sesion, tmp_path):
    malo = tmp_path / "listado-reunion.xlsx"
    malo.write_bytes(b"esto no es un libro de Excel")
    r = _subir(sesion, malo)
    assert r.status_code == 422 and "listado-reunion.xlsx" in r.json()["detail"]
