"""Datos: supresión, fusión, reimportación, importación concurrente, ubicación elegida a mano y coincidencias.

Solo personas inventadas."""
import json

import pytest

from conftest import CEDULAS, TRAMITES, excel_cedulas, excel_tramites


def _db(c):
    return c.app.state.db


def _subir(c, ruta, tramites=None, cedulas=None) -> dict:
    archivos = []
    if tramites is not None:
        archivos.append(("archivos", ("tramites.xlsx", excel_tramites(ruta / "t.xlsx", tramites).read_bytes())))
    if cedulas is not None:
        archivos.append(("archivos", ("cedulas.xlsx", excel_cedulas(ruta / "c.xlsx", cedulas).read_bytes())))
    r = c.post("/api/importar", files=archivos)
    assert r.status_code == 200, r.text
    return r.json()


def _buscar(c, q):
    return c.get("/api/personas", params={"q": q}).json()["filas"]


def _lugar(c, nombre, tipo):
    return next(l for l in c.get("/api/lugares").json() if l["nombre"] == nombre and l["tipo"] == tipo)


def _cedula(cedula, nombre, telefono=None, listas="Lista A"):
    return (cedula, nombre, telefono, None, None, None, None, None, None, 40, "F", None, None, listas)


@pytest.fixture
def importado(sesion, tmp_path):
    _subir(sesion, tmp_path, TRAMITES, CEDULAS)
    return sesion


# ───────────────────────────── Supresión (Ley 1581) ─────────────────────────────

def test_suprimir_vacia_las_fichas_unidas_y_la_auditoria(importado):
    c = importado
    db = _db(c)
    yurani, rosalba = _buscar(c, "YURANI")[0], _buscar(c, "ROSALBA")[0]
    assert c.patch(f"/api/personas/{yurani['id']}", json={"telefono": "3150001122"}).status_code == 200
    assert c.post(f"/api/personas/{rosalba['id']}/fusionar", json={"con_id": yurani["id"]}).status_code == 200
    assert c.delete(f"/api/personas/{rosalba['id']}").status_code == 200
    for pid in (yurani["id"], rosalba["id"]):
        p = db.personas.find_one({"_id": pid})
        assert p["nombre"] == "SUPRIMIDO" and p["eliminado"] is True
        assert p["telefono"] is None and p["cedula"] is None and p["direccion"] is None and p["edad"] is None
        assert p["origen"] == [] and p["listas"] == [] and p["tramites"] == [] and not p.get("claves_tramites")
    texto = json.dumps(list(db.auditoria.find({}, {"_id": 0})), default=str) + json.dumps(c.get("/api/auditoria").json())
    for dato in ("90000002", "3150001122", "3027778899", "YURANI", "ROSALBA"):
        assert dato not in texto
    # Las huellas no guardan nada en claro
    huellas = json.dumps(list(db.suprimidos.find()), default=str)
    assert db.suprimidos.count_documents({}) >= 3
    assert "90000002" not in huellas and "ROSALBA" not in huellas and "1004" not in huellas
    secreto = db.meta.find_one({"_id": "clave_supresion"})["valor"]
    assert len(secreto) == 64


def test_suprimir_desde_la_ficha_unida_alcanza_a_la_raiz(importado):
    c = importado
    yurani, rosalba = _buscar(c, "YURANI")[0], _buscar(c, "ROSALBA")[0]
    c.post(f"/api/personas/{rosalba['id']}/fusionar", json={"con_id": yurani["id"]})
    assert c.delete(f"/api/personas/{yurani['id']}").status_code == 200
    assert c.get(f"/api/personas/{rosalba['id']}").status_code == 404
    assert _db(c).personas.find_one({"_id": rosalba["id"]})["telefono"] is None


def test_reimportar_no_vuelve_a_crear_a_los_suprimidos(importado, tmp_path):
    c = importado
    for q in ("QUINTERO", "ROSALBA", "SOLO CON CEDULA"):
        assert c.delete(f"/api/personas/{_buscar(c, q)[0]['id']}").status_code == 200
    res = _subir(c, tmp_path, TRAMITES, CEDULAS)
    assert res["personas_nuevas"] == 0
    assert res["suprimidas_omitidas"] == 5  # trámites: 2 de Zoila y 1 de Rosalba; cédulas: Zoila y la persona solo con cédula
    for q in ("QUINTERO", "ROSALBA", "SOLO CON CEDULA", "90000001", "3045556677"):
        assert _buscar(c, q) == []
    assert c.get("/api/personas").json()["total"] == 3


# ───────────────────────────── Fusión ─────────────────────────────

def test_fusion_deja_el_origen_sin_datos_y_conserva_la_ubicacion_manual(sesion):
    c = sesion
    a = c.post("/api/personas", json={"nombre": "Teodomiro Inventado Uno", "forzar": True}).json()
    b = c.post("/api/personas", json={"nombre": "Teodomiro Inventado Uno Bis", "telefono": "3201112233",
                                      "direccion": "VEREDA LA CONDOR", "forzar": True}).json()
    assert c.put(f"/api/personas/{b['id']}/ubicacion", json={"lat": 7.0, "lon": -73.9}).json()["geo_manual"] == "punto"
    r = c.post(f"/api/personas/{a['id']}/fusionar", json={"con_id": b["id"]}).json()
    assert (r["lat"], r["lon"], r["geo_precision"], r["geo_manual"]) == (7.0, -73.9, "manual", "punto")
    assert r["telefono"] == "3201112233"
    c.post("/api/georreferenciar")
    p = c.get(f"/api/personas/{a['id']}").json()
    assert (p["lat"], p["lon"], p["geo_precision"]) == (7.0, -73.9, "manual")
    o = _db(c).personas.find_one({"_id": b["id"]})
    assert o["fusionada_en"] == a["id"] and o["nombre"] == "FUSIONADA" and o["eliminado"] is False
    assert o["telefono"] is None and o["direccion"] is None and o["lat"] is None and o["origen"] == []


SIN_ID = [
    ("", "0589300000101", "2/6/2025 12:00:00 AM", "NUEVA ENCUESTA - PANCRACIO ZEBEDEO TRUJILLANO", "VEREDA LA CONDOR", "", "3101112233", 1),
    ("", "0589300000101", "3/6/2025 12:00:00 AM", "REENCUESTA - PANCRACIO ZEBEDEO TRUJILLANO", "VEREDA LA CONDOR", "", "3101112233", 1),
    ("", "0589300000102", "4/6/2025 12:00:00 AM", "NUEVA ENCUESTA - PANCRACIO Z TRUJILLANO", "VEREDA LA CONDOR", "", "3109998877", 1),
    ("2001", "0589300000103", "5/6/2025 12:00:00 AM", "NUEVA ENCUESTA - OTRO INVENTADO CONID", "", "", "3105554433", 1),
]


def test_tramites_sin_id_no_se_duplican_ni_se_pierden_al_unir(sesion, tmp_path):
    c = sesion
    res = _subir(c, tmp_path, SIN_ID)
    assert res["personas_nuevas"] == 3 and res["tramites_nuevos"] == 4
    res = _subir(c, tmp_path, SIN_ID)
    assert res["personas_nuevas"] == 0 and res["tramites_nuevos"] == 0
    a = _buscar(c, "ZEBEDEO")[0]
    b = next(p for p in _buscar(c, "TRUJILLANO") if p["id"] != a["id"])
    r = c.post(f"/api/personas/{a['id']}/fusionar", json={"con_id": b["id"]}).json()
    assert len(r["tramites"]) == 3
    res = _subir(c, tmp_path, SIN_ID)
    assert res["personas_nuevas"] == 0 and res["tramites_nuevos"] == 0
    assert len(_buscar(c, "TRUJILLANO")) == 1
    assert len(c.get(f"/api/personas/{a['id']}").json()["tramites"]) == 3


def test_fusion_y_archivo_incremental_no_recrea_el_duplicado(sesion, tmp_path):
    c = sesion
    _subir(c, tmp_path, [
        ("2001", "0589300000201", "2/6/2025", "NUEVA ENCUESTA - HERMINIA INVENTADA SOLANO", "VEREDA LA CONDOR", "", "3111112233", 1),
        ("2002", "0589300000202", "3/6/2025", "NUEVA ENCUESTA - HERMINIA INVENTADA SOLANO RUIZ", "VEREDA LA CONDOR", "", "3112223344", 1),
    ])
    fichas = _buscar(c, "HERMINIA")
    assert len(fichas) == 2
    c.post(f"/api/personas/{fichas[0]['id']}/fusionar", json={"con_id": fichas[1]["id"]})
    res = _subir(c, tmp_path, [("2003", "0589300000202", "4/6/2025", "REENCUESTA - HERMINIA INVENTADA SOLANO RUIZ",
                                "VEREDA LA CONDOR", "", "3112223344", 1)])
    assert res["personas_nuevas"] == 0 and res["tramites_nuevos"] == 1
    assert [p["id"] for p in _buscar(c, "HERMINIA")] == [fichas[0]["id"]]
    assert len(c.get(f"/api/personas/{fichas[0]['id']}").json()["tramites"]) == 3


# ───────────────────────────── Importación ─────────────────────────────

def test_importacion_no_pisa_lo_editado_mientras_corre(importado, tmp_path):
    from app.pipeline import importar as imp
    from app.pipeline import lectores
    c = importado
    db = _db(c)
    zoila, otra, eusebio = _buscar(c, "QUINTERO")[0], _buscar(c, "SOLO CON CEDULA")[0], _buscar(c, "CARVAJALINO")[0]
    e = list(CEDULAS[2])
    e[3], e[6] = "eusebio.inventado@gmail.com", "Mesa # 9"
    filas = list(lectores.leer_cedulas(excel_cedulas(tmp_path / "c2.xlsx", [
        (*CEDULAS[0][:-1], "Lista A; Lista Z"), (*CEDULAS[3][:-1], "Lista C; Lista Y"), tuple(e)])))
    alm = imp._Almacen(db)  # la importación ya cargó las fichas…
    # …y mientras tanto el panel sigue trabajando
    reu = c.post("/api/reuniones", json={"titulo": "Reunión de prueba", "fecha": "2026-11-01"}).json()
    c.post(f"/api/reuniones/{reu['id']}/asistentes", json={"persona_id": zoila["id"]})
    assert c.post(f"/api/personas/{zoila['id']}/notas", json={"texto": "Nota durante la importación"}).status_code == 201
    assert c.patch(f"/api/personas/{zoila['id']}", json={"ocupacion": "Pescadora", "consentimiento": "si"}).status_code == 200
    assert c.patch(f"/api/personas/{eusebio['id']}", json={"correo": "correo.del.panel@gmail.com"}).status_code == 200
    assert c.delete(f"/api/personas/{otra['id']}").status_code == 200
    imp._importar_cedulas(alm, filas, 99, imp.Resumen())
    alm.guardar()
    p = c.get(f"/api/personas/{zoila['id']}").json()
    assert len(p["notas"]) == 1 and len(p["reuniones"]) == 1
    assert p["ocupacion"] == "Pescadora" and p["consentimiento"] == "si"
    assert p["listas"] == ["Lista A", "Lista Z"]  # lo de la importación sí se escribió
    p = c.get(f"/api/personas/{eusebio['id']}").json()
    assert p["correo"] == "correo.del.panel@gmail.com" and p["mesa"] == "Mesa # 9"
    assert c.get(f"/api/personas/{otra['id']}").status_code == 404
    o = db.personas.find_one({"_id": otra["id"]})
    assert o["nombre"] == "SUPRIMIDO" and o["cedula"] is None and o["listas"] == []


def test_cedula_repetida_en_la_misma_importacion(sesion, tmp_path):
    c = sesion
    (tmp_path / "a").mkdir()
    a = excel_cedulas(tmp_path / "a" / "c1.xlsx", [_cedula("90000031", "ANA INVENTADA PEREZ", "3001230000")])
    b = excel_cedulas(tmp_path / "a" / "c2.xlsx", [_cedula("90000031", "ANA INVENTADA PEREZ DIAZ", None, "Lista B")])
    r = c.post("/api/importar", files=[("archivos", ("c1.xlsx", a.read_bytes())), ("archivos", ("c2.xlsx", b.read_bytes()))])
    assert r.status_code == 200, r.text
    assert r.json()["personas_nuevas"] == 1 and r.json()["cedulas_ya_existian"] == 1
    ana = _buscar(c, "90000031")
    assert len(ana) == 1
    assert c.get(f"/api/personas/{ana[0]['id']}").json()["listas"] == ["Lista A", "Lista B"]
    # Un solo archivo con la cédula dos veces
    res = _subir(c, tmp_path, cedulas=[_cedula("90000032", "BEATRIZ INVENTADA ROJAS"), _cedula("90000032", "BEATRIZ INVENTADA ROJAS")])
    assert res["personas_nuevas"] == 1 and res["cedulas_ya_existian"] == 1


def test_dos_cedulas_para_la_misma_ficha_gana_la_de_mayor_puntaje(bases, tmp_path):
    from app.pipeline.importar import importar
    tram = excel_tramites(tmp_path / "t.xlsx", [
        ("3001", "0589300000301", "2/6/2025", "NUEVA ENCUESTA - EUSTAQUIO BARTOLOME ZAPATEIRO QUINTERO", "VEREDA LA CONDOR", "", "3001112233", 1)])
    parcial = _cedula("90000042", "EUSTAQUIO BARTOLOME ZAPATEIRO", "3001112233")
    completo = _cedula("90000041", "EUSTAQUIO BARTOLOME ZAPATEIRO QUINTERO")
    for i, orden in enumerate(([parcial, completo], [completo, parcial])):
        db = bases()
        res = importar(db, [tram, excel_cedulas(tmp_path / f"c{i}.xlsx", orden)])
        assert res.cedulas_unidas_auto == 1 and res.personas_nuevas == 2
        ficha = db.personas.find_one({"tramites.id_externo": "3001"})
        assert ficha["cedula"] == "90000041"


def test_cedulas_empatadas_van_a_revision_y_la_otra_se_cierra_al_aceptar(sesion, tmp_path):
    c = sesion
    res = _subir(c, tmp_path, [("3101", "0589300000311", "2/6/2025", "NUEVA ENCUESTA - CASIMIRO INVENTADO HOMONIMO", "", "", "", 1)],
                 [_cedula("90000051", "CASIMIRO INVENTADO HOMONIMO"), _cedula("90000052", "CASIMIRO INVENTADO HOMONIMO")])
    assert res["cedulas_unidas_auto"] == 0 and res["cedulas_en_revision"] == 2
    pendientes = c.get("/api/coincidencias").json()
    assert len(pendientes) == 2
    assert c.post(f"/api/coincidencias/{pendientes[0]['id']}", json={"decision": "aceptar"}).status_code == 200
    assert c.get("/api/coincidencias").json() == []
    assert c.get("/api/indicadores").json()["kpi"]["pendientes_revision"] == 0


def test_coincidencias_que_ya_no_se_pueden_aceptar_se_cierran(sesion, tmp_path):
    c = sesion
    _subir(c, tmp_path, [("3201", "0589300000321", "2/6/2025", "NUEVA ENCUESTA - TIBURCIO ANSELMO PEDRAZA", "", "", "", 1)],
           [_cedula("90000061", "TIBURCIO ANSELMO PEDRAZA GOMEZ"), _cedula("90000062", "TIBURCIO ANSELMO PEDRAZA GOMES")])
    pendientes = c.get("/api/coincidencias").json()
    assert len(pendientes) == 2
    assert c.post(f"/api/coincidencias/{pendientes[0]['id']}", json={"decision": "aceptar"}).status_code == 200
    assert c.get("/api/coincidencias").json() == []
    assert c.get("/api/indicadores").json()["kpi"]["pendientes_revision"] == 0
    assert _db(c).coincidencias.find_one({"_id": pendientes[1]["id"]})["estado"] == "cerrada"


def test_sector_aprendido_del_casco_queda_urbano(sesion, tmp_path):
    c = sesion
    nombres = ["ANACLETO INVENTADO UNO", "BERNABE INVENTADO DOS", "CRISANTO INVENTADO TRES"]
    res = _subir(c, tmp_path, [(str(4000 + i), f"05893000004{i:02d}", "2/6/2025", f"NUEVA ENCUESTA - {n}",
                                f"CL 50 # 47-{10 + 2 * i} SECTOR LA PLAYITA", "", f"31{i}0001122", 1) for i, n in enumerate(nombres)])
    assert res["lugares_nuevos"] == 1
    lg = _lugar(c, "LA PLAYITA", "sector")
    assert lg["zona"] == "urbana" and lg["padre"] == "YONDO"
    for p in _buscar(c, "INVENTADO"):
        assert p["precision"] == "direccion" and p["zona"] == "urbana" and p["lugar"] == "LA PLAYITA"


# ───────────────────────────── Ubicación elegida a mano ─────────────────────────────

def test_lugar_elegido_a_mano_se_conserva_y_sigue_al_punto_del_lugar(sesion):
    c = sesion
    central, julio, barbacoas = _lugar(c, "CENTRAL", "barrio"), _lugar(c, "23 DE JULIO", "barrio"), _lugar(c, "BARBACOAS", "vereda")
    assert julio["lat"] is None and barbacoas["lat"] is not None

    def nueva(nombre, **datos):
        r = c.post("/api/personas", json={"nombre": nombre, "forzar": True, **datos})
        assert r.status_code == 201, r.text
        return r.json()

    # Con placa en Tres de Octubre: se corrige el barrio y se conserva el punto de la placa
    a = nueva("Abundio Inventado Placa", direccion="BARRIO TRES DE OCTUBRE CALLE 49 # 45 12")
    assert a["geo_precision"] == "direccion"
    r = c.patch(f"/api/personas/{a['id']}", json={"lugar_id": central["id"]}).json()
    assert r["lugar_id"] == central["id"] and r["geo_precision"] == "direccion"
    # Sin dirección, un barrio sin punto
    b = nueva("Bonifacia Inventada Sinpunto")
    r = c.patch(f"/api/personas/{b['id']}", json={"lugar_id": julio["id"]}).json()
    assert r["lugar_id"] == julio["id"] and r["lat"] is None
    # Lugar y dirección en el mismo cambio
    d = nueva("Dagoberto Inventado Mixto", direccion="CASA 4 FRENTE A LA TIENDA")
    assert c.patch(f"/api/personas/{d['id']}", json={"lugar_id": julio["id"], "direccion": "FINCA EL PORVENIR"}).json()["lugar_id"] == julio["id"]
    # Alta con un lugar sin punto aunque la dirección diga otro barrio
    e = nueva("Eulalia Inventada Alta", direccion="BARRIO TRES DE OCTUBRE", lugar_id=julio["id"])
    assert e["lugar_id"] == julio["id"] and e["geo_manual"] == "lugar"
    # Vereda con punto: la persona toma el punto del lugar
    f = nueva("Filomena Inventada Vereda", lugar_id=barbacoas["id"])
    assert (f["lat"], f["lon"], f["geo_precision"]) == (barbacoas["lat"], barbacoas["lon"], "vereda")
    # Punto puesto a mano (y uno viejo con geo_manual=True): no se mueven
    g = nueva("Gumersindo Inventado Punto", lugar_id=barbacoas["id"])
    c.put(f"/api/personas/{g['id']}/ubicacion", json={"lat": 6.8, "lon": -74.2})
    h = nueva("Herminio Inventado Viejo", direccion="VEREDA LA CONDOR")
    _db(c).personas.update_one({"_id": h["id"]}, {"$set": {"geo_manual": True, "lat": 7.1, "lon": -73.95, "geo_precision": "manual"}})

    # Recalcular todo y corregir lugares no deshace lo elegido; corregir el punto de un lugar mueve a su gente
    assert c.post("/api/georreferenciar").status_code == 200
    c.patch(f"/api/lugares/{barbacoas['id']}", json={"lat": 6.9, "lon": -74.1})
    c.patch(f"/api/lugares/{julio['id']}", json={"lat": 7.001, "lon": -73.905})
    ver = lambda p: c.get(f"/api/personas/{p['id']}").json()  # noqa: E731
    assert ver(a)["lugar_id"] == central["id"] and ver(a)["geo_precision"] == "direccion"
    assert (ver(b)["lugar_id"], ver(b)["lat"], ver(b)["lon"]) == (julio["id"], 7.001, -73.905)
    assert ver(d)["lugar_id"] == julio["id"] and ver(e)["lugar_id"] == julio["id"]
    assert (ver(f)["lat"], ver(f)["lon"]) == (6.9, -74.1)
    assert (ver(g)["lat"], ver(g)["lon"], ver(g)["geo_manual"]) == (6.8, -74.2, "punto")
    assert (ver(h)["lat"], ver(h)["lon"]) == (7.1, -73.95)
    # «Volver a la automática»
    r = c.delete(f"/api/personas/{g['id']}/ubicacion").json()
    assert r["geo_manual"] is False and r["lat"] is None


def test_persona_creada_en_una_reunion_guarda_la_reunion(sesion):
    c = sesion
    reu = c.post("/api/reuniones", json={"titulo": "Reunión de prueba", "fecha": "2026-11-01"}).json()
    p = c.post("/api/personas", json={"nombre": "Nueva Persona Inventada", "reunion_id": reu["id"], "forzar": True}).json()
    assert _db(c).personas.find_one({"_id": p["id"]}).get("reunion_origen") == reu["id"]
    q = c.post("/api/personas", json={"nombre": "Otra Persona Inventada", "forzar": True}).json()
    assert _db(c).personas.find_one({"_id": q["id"]}).get("reunion_origen") is None


def test_etiquetas_borradas_no_se_vuelven_a_sembrar(sesion):
    from app import db as bd
    c = sesion
    etiquetas = c.get("/api/catalogos").json()["etiquetas"]
    assert len(etiquetas) == len(bd.ETIQUETAS_INICIALES)
    for e in etiquetas:
        assert c.delete(f"/api/etiquetas/{e['id']}").status_code == 200
    bd.inicializar(_db(c))  # como en un reinicio o un despliegue
    assert c.get("/api/catalogos").json()["etiquetas"] == []
