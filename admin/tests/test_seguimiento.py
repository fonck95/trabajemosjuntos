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
    # El enlace del mapa pide además «con ubicación»: quien no tiene coordenada no está en el mapa
    assert sesion.get("/api/personas", params={"lugar_id": 0, "precision": "ubicada"}).json()["total"] == 0


def test_mas_de_seis_archivos_se_rechaza(sesion, tmp_path):
    ruta = excel_tramites(tmp_path / "t.xlsx", TRAMITES)
    r = _subir(sesion, *([ruta] * 7))
    assert r.status_code == 422 and "6 archivos" in r.json()["detail"]


def test_error_de_formato_nombra_el_archivo(sesion, tmp_path):
    malo = tmp_path / "listado-reunion.xlsx"
    malo.write_bytes(b"esto no es un libro de Excel")
    r = _subir(sesion, malo)
    assert r.status_code == 422 and "listado-reunion.xlsx" in r.json()["detail"]


def test_suprimir_no_bloquea_a_los_homonimos(sesion, tmp_path):
    persona = [("4001", "0589300000401", "2/6/2025 12:00:00 AM", "NUEVA ENCUESTA - SEVERIANO ARCADIO TOVAR",
                "VEREDA X-10", "", "3101230001", 1)]
    homonimo = [("4002", "0589300000402", "3/6/2025 12:00:00 AM", "NUEVA ENCUESTA - SEVERIANO ARCADIO TOVAR",
                 "VEREDA LA CONDOR", "", "3109870002", 1)]
    cedulas = [("90000071", "SEVERIANO ARCADIO TOVAR", "3101230001", None, None, None, None, None, None, 50, "M", None,
                None, "Lista A")]
    otra_cedula = [("90000072", "SEVERIANO ARCADIO TOVAR", "3209870003", None, None, None, None, None, None, 33, "M",
                    None, None, "Lista B")]
    _subir(sesion, excel_tramites(tmp_path / "p.xlsx", persona), excel_cedulas(tmp_path / "c.xlsx", cedulas))
    pid = sesion.get("/api/personas", params={"q": "TOVAR"}).json()["filas"][0]["id"]
    assert sesion.delete(f"/api/personas/{pid}").status_code == 200
    # Reimportar sus filas no la vuelve a crear…
    r = _subir(sesion, excel_tramites(tmp_path / "p2.xlsx", persona), excel_cedulas(tmp_path / "c2.xlsx", cedulas)).json()
    assert r["personas_nuevas"] == 0 and r["suprimidas_omitidas"] == 2
    # …pero otra persona con el mismo nombre (otra ficha, otro celular, otra cédula) sí entra
    r = _subir(sesion, excel_tramites(tmp_path / "h.xlsx", homonimo), excel_cedulas(tmp_path / "c3.xlsx", otra_cedula)).json()
    assert r["suprimidas_omitidas"] == 0
    assert sesion.get("/api/personas", params={"q": "TOVAR"}).json()["total"] >= 1


def test_fusion_conserva_la_mejor_ubicacion(sesion, tmp_path):
    _subir(sesion, excel_tramites(tmp_path / "t.xlsx", TRAMITES))
    zoila = sesion.get("/api/personas", params={"q": "QUINTERO"}).json()["filas"][0]
    assert sesion.get(f"/api/personas/{zoila['id']}").json()["geo_precision"] == "direccion"
    lugares = sesion.get("/api/catalogos").json()["lugares"]
    vereda = next(l for l in lugares if l["tipo"] == "vereda")
    otra = sesion.post("/api/personas", json={"nombre": "Ficha Duplicada Inventada", "forzar": True,
                                              "lugar_id": vereda["id"]}).json()
    assert otra["geo_manual"] == "lugar"
    unida = sesion.post(f"/api/personas/{zoila['id']}/fusionar", json={"con_id": otra["id"]}).json()
    # La placa exacta del casco gana sobre una vereda elegida a mano en la otra ficha
    assert unida["geo_precision"] == "direccion" and unida["lugar_nombre"] != vereda["nombre"]
