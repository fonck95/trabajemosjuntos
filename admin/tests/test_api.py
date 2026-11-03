"""API: autenticación, importación con cruce, directorio, ficha, reuniones, calidad y exportación."""
import io

import openpyxl
import pytest

from conftest import CEDULAS, TRAMITES, excel_cedulas, excel_tramites


def test_sin_sesion_no_hay_datos(cliente):
    assert cliente.get("/api/personas").status_code == 401
    assert cliente.get("/api/indicadores").status_code == 401
    r = cliente.get("/api/yo")
    assert r.status_code == 401 and r.json()["detail"]["configurado"] is True


def test_login_y_cabeceras(cliente):
    r = cliente.post("/api/login", json={"usuario": "admin", "clave": "mala"})
    assert r.status_code == 401
    r = cliente.post("/api/login", json={"usuario": "admin", "clave": "clave-de-prueba-larga"})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    h = cliente.get("/panel").headers
    assert "default-src 'self'" in h["content-security-policy"] and h["x-frame-options"] == "DENY"
    assert cliente.get("/api/yo").json()["usuario"] == "admin"


def test_csrf_obligatorio(cliente):
    cliente.post("/api/login", json={"usuario": "admin", "clave": "clave-de-prueba-larga"})
    assert cliente.post("/api/reuniones", json={"titulo": "Prueba", "fecha": "2026-01-01"}).status_code == 403


def test_bloqueo_por_intentos(cliente):
    for _ in range(5):
        cliente.post("/api/login", json={"usuario": "x", "clave": "y"})
    r = cliente.post("/api/login", json={"usuario": "admin", "clave": "clave-de-prueba-larga"})
    assert r.status_code == 429


@pytest.fixture
def importado(sesion, tmp_path):
    a = excel_tramites(tmp_path / "t.xlsx", TRAMITES)
    b = excel_cedulas(tmp_path / "c.xlsx", CEDULAS)
    with a.open("rb") as fa, b.open("rb") as fb:
        r = sesion.post("/api/importar", files=[("archivos", ("tramites.xlsx", fa.read())), ("archivos", ("cedulas.xlsx", fb.read()))])
    assert r.status_code == 200, r.text
    return sesion, r.json()


def test_importacion_cruza_y_no_duplica(importado, tmp_path):
    c, res = importado
    assert res["tramites_nuevos"] == 5
    assert res["cedulas_unidas_auto"] == 2  # Zoila (mismo nombre y teléfono) y Eusebio (JHON/JOHN)
    total = c.get("/api/personas").json()["total"]
    assert total == 4 + 2  # 4 de trámites + Anyi + la persona solo con cédula
    zoila = c.get("/api/personas", params={"q": "QUINTERO"}).json()["filas"][0]
    assert zoila["cedula"] == "90000001" and set(zoila["fuentes"]) == {"tramites", "cedulas"}
    ficha = c.get(f"/api/personas/{zoila['id']}").json()
    assert ficha["correo"] == "zoila@gmail.com" and len(ficha["tramites"]) == 2 and ficha["listas"] == ["Lista A"]
    assert ficha["geo_precision"] == "direccion" and ficha["direccion_norm"].startswith("CL 49 # 45-12")
    # Segunda importación: nada nuevo
    a = excel_tramites(tmp_path / "t2.xlsx", TRAMITES)
    with a.open("rb") as fa:
        r2 = c.post("/api/importar", files=[("archivos", ("tramites.xlsx", fa.read()))]).json()
    assert r2["personas_nuevas"] == 0 and r2["tramites_nuevos"] == 0
    assert c.get("/api/personas").json()["total"] == total


def test_editar_no_se_pisa_al_reimportar(importado, tmp_path):
    c, _ = importado
    p = c.get("/api/personas", params={"q": "PANTOJA"}).json()["filas"][0]
    r = c.patch(f"/api/personas/{p['id']}", json={"telefono": "3115551234", "ocupacion": "Pescador", "etiquetas": [1, 2]})
    assert r.status_code == 200 and r.json()["telefono"] == "3115551234"
    assert r.json()["completitud"] > p["completitud"]
    a = excel_tramites(tmp_path / "t3.xlsx", TRAMITES)
    with a.open("rb") as fa:
        c.post("/api/importar", files=[("archivos", ("tramites.xlsx", fa.read()))])
    assert c.get(f"/api/personas/{p['id']}").json()["telefono"] == "3115551234"
    assert c.patch(f"/api/personas/{p['id']}", json={"telefono": "123"}).status_code == 422


def test_reunion_con_asistentes_y_notas(importado):
    c, _ = importado
    reu = c.post("/api/reuniones", json={"titulo": "Reunión de prueba", "fecha": "2026-11-01", "tema": "Agua"}).json()
    p = c.get("/api/buscar", params={"q": "ZOILA"}).json()[0]
    r = c.post(f"/api/reuniones/{reu['id']}/asistentes", json={"persona_id": p["id"]})
    assert len(r.json()["asistentes"]) == 1
    # Persona nueva registrada en la reunión; primero avisa de parecidas
    r = c.post("/api/personas", json={"nombre": "Zoila Esperanza Quintero", "reunion_id": reu["id"]})
    assert r.status_code == 409 and r.json()["detail"]["parecidas"]
    r = c.post("/api/personas", json={"nombre": "Nueva Persona Inventada", "telefono": "3209998877", "reunion_id": reu["id"], "forzar": True})
    assert r.status_code == 201 and r.json()["fuentes"] == ["reunion"]
    n = c.post(f"/api/personas/{p['id']}/notas", json={"texto": "Pidió conexión al acueducto", "reunion_id": reu["id"]}).json()
    assert n["notas"][0]["reunion"] == "Reunión de prueba" and n["reuniones"][0]["id"] == reu["id"]
    assert len(c.get(f"/api/reuniones/{reu['id']}").json()["asistentes"]) == 2
    k = c.get("/api/indicadores").json()["kpi"]
    assert k["reuniones"] == 1 and k["alcanzadas"] == 2 and k["nuevas_en_reuniones"] == 1
    csv = c.get(f"/api/reuniones/{reu['id']}/asistentes.csv")
    assert csv.status_code == 200 and "NUEVA PERSONA INVENTADA" in csv.text


def test_fusion_y_supresion(importado):
    c, _ = importado
    yurani = c.get("/api/personas", params={"q": "YURANI"}).json()["filas"][0]
    rosalba = c.get("/api/personas", params={"q": "ROSALBA"}).json()["filas"][0]
    r = c.post(f"/api/personas/{rosalba['id']}/fusionar", json={"con_id": yurani["id"]})
    assert r.status_code == 200 and r.json()["cedula"] == "90000002"
    assert c.get(f"/api/personas/{yurani['id']}").status_code == 409
    assert c.delete(f"/api/personas/{rosalba['id']}").status_code == 200
    assert c.get(f"/api/personas/{rosalba['id']}").status_code == 404


def test_mapa_lugares_y_exportacion(importado):
    c, _ = importado
    pts = c.get("/api/mapa/puntos").json()
    assert pts["ubicadas"] >= 3 and len(pts["puntos"][0]) == 8
    capas = c.get("/api/mapa/capas").json()
    assert capas["limite"]["type"] in ("FeatureCollection", "Feature")
    assert any(f["properties"]["tipo"] == "vereda" for f in capas["veredas"]["features"])
    lugar = next(l for l in c.get("/api/lugares").json() if l["lat"] is None)
    assert c.patch(f"/api/lugares/{lugar['id']}", json={"lat": 7.0, "lon": -73.91}).status_code == 200
    x = c.get("/api/exportar.xlsx")
    assert x.status_code == 200
    ws = openpyxl.load_workbook(io.BytesIO(x.content)).active
    assert ws.cell(1, 2).value == "Nombre" and ws.max_row == 7
