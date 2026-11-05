"""Grupo 5 (9.5): zonas guardadas (`/api/areas`) y su geometría.

CRUD con auditoría; 422 `poligono`; área ±0,5 % frente a una medida independiente; planilleros y consultores reciben
403; tope de 200; nombre repetido; color inválido; la asignación queda igual en `areas` y en `usuarios`; el coordinador
gestiona zonas como A. El filtro `area_id` en Habitantes es del grupo 3: esa prueba se salta mientras no exista
GET /api/trabajo (la marca de ese grupo). El gemelo en JavaScript (web/js/zona.js) se compara con Node si está.

Solo datos inventados."""
import json
import math
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import geometria
from app.api import zonas
from conftest import CASCO, CLAVE_USUARIO, crear_usuario, insertar_personas, personas_inventadas

LON, LAT = CASCO
# Un pentágono de unos 1,1 km de ancho en el casco urbano (anillo abierto)
PENTAGONO = [[round(LON + 0.005 * math.cos(math.radians(90 + 72 * i)), 6),
              round(LAT + 0.005 * math.sin(math.radians(90 + 72 * i)), 6)] for i in range(5)]
CUADRO = [[LON - 0.004, LAT - 0.004], [LON + 0.004, LAT - 0.004], [LON + 0.004, LAT + 0.004], [LON - 0.004, LAT + 0.004]]
ZONA_JS = Path(__file__).resolve().parents[1] / "web" / "js" / "zona.js"


def _hay_ruta(app, metodo, ruta):
    return any(isinstance(r, APIRoute) and r.path == ruta and metodo in r.methods for r in app.routes)


def _area_plana(anillo):
    """Área por la fórmula del cordón en metros de una proyección equirrectangular (independiente de la esférica)."""
    lat0 = math.radians(sum(v[1] for v in anillo) / len(anillo))
    m = 6371008.8 * math.pi / 180
    xy = [(v[0] * m * math.cos(lat0), v[1] * m) for v in anillo]
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(xy, xy[1:] + xy[:1]))) / 2


def _auditoria(db, accion):
    return list(db.auditoria.find({"accion": accion}).sort("_id", 1))


@pytest.fixture
def coordinador(sesion):
    """Un coordinador activo con la clave cambiada y el compromiso aceptado, ya ingresado (como en test_coordinador:
    `crear_usuario` solo crea P y C, así que se crea como planillero y se pasa a coordinador en la base)."""
    abiertos = []

    def nuevo():
        db = sesion.app.state.db
        u = crear_usuario(db, "planillero")
        nombre = f"coordinador{u['_id']}"
        db.usuarios.update_one({"_id": u["_id"]}, {"$set": {"rol": "coordinador", "usuario": nombre}})
        c = TestClient(sesion.app)
        r = c.post("/api/login", json={"usuario": nombre, "clave": CLAVE_USUARIO})
        assert r.status_code == 200, r.text
        c.headers["X-CSRF-Token"] = r.json()["csrf"]
        c.uid = u["_id"]
        abiertos.append(c)
        return c

    yield nuevo
    for c in abiertos:
        c.close()


# ───────────────────────────── CRUD y auditoría ─────────────────────────────

def test_crud_con_auditoria(sesion):
    db = sesion.app.state.db
    r = sesion.post("/api/areas", json={"nombre": "  Casco   norte ", "descripcion": "Prueba", "color": "#2A78D6",
                                        "poligono": PENTAGONO})
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["nombre"] == "Casco norte" and a["color"] == "#2a78d6" and a["vertices"] == 5
    assert a["poligono"] == PENTAGONO and a["codificado"] == geometria.codificar(PENTAGONO)
    assert a["area_m2"] == round(geometria.area_m2(PENTAGONO)) and a["perimetro_m"] > 0
    assert a["asignada_a"] == [] and a["creado_por"] == 0
    aid = a["id"]

    lista = sesion.get("/api/areas").json()
    assert lista["tope"] == 200 and [x["id"] for x in lista["areas"]] == [aid]
    assert all(c.startswith("#") and len(c) == 7 for c in lista["paleta"])
    assert sesion.get(f"/api/areas/{aid}").json()["nombre"] == "Casco norte"
    assert sesion.get("/api/areas/999").status_code == 404

    # El polígono también llega como texto «lon,lat;…» (el de la URL); el área y el perímetro se recalculan
    r = sesion.patch(f"/api/areas/{aid}", json={"poligono": geometria.codificar(CUADRO), "nombre": "Casco centro",
                                                "descripcion": ""})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["vertices"] == 4 and b["nombre"] == "Casco centro" and b["descripcion"] is None
    assert b["area_m2"] == round(geometria.area_m2(geometria.validar_anillo(CUADRO))) != a["area_m2"]
    # Un PATCH sin cambios no audita
    assert sesion.patch(f"/api/areas/{aid}", json={"nombre": "Casco centro"}).status_code == 200

    r = sesion.delete(f"/api/areas/{aid}")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert sesion.get(f"/api/areas/{aid}").status_code == 404
    assert sesion.delete(f"/api/areas/{aid}").status_code == 404

    crear, editar, borrar = (_auditoria(db, x) for x in ("crear_area", "editar_area", "borrar_area"))
    assert len(crear) == 1 and len(editar) == 1 and len(borrar) == 1
    for e in crear + editar + borrar:
        assert e["entidad"] == "area" and e["entidad_id"] == aid and e["uid"] == 0 and e["rol"] == "admin"
    d = json.loads(editar[0]["detalle"])
    assert sorted(d["antes"]) == ["descripcion", "nombre", "poligono"]
    assert d["antes"]["poligono"] == geometria.codificar(PENTAGONO)
    # Borrar no pierde nada: la auditoría guarda el área completa con su polígono
    d = json.loads(borrar[0]["detalle"])
    assert d["nombre"] == "Casco centro" and geometria.decodificar(d["poligono"]) == geometria.validar_anillo(CUADRO)


def test_poligono_invalido_da_422(sesion):
    lejos = [[-75.5, 6.2], [-75.4, 6.2], [-75.4, 6.3]]  # Medellín, fuera de Yondó
    cruzado = [CUADRO[0], CUADRO[2], CUADRO[1], CUADRO[3]]
    diminuto = [[LON, LAT], [LON + 0.00005, LAT], [LON, LAT + 0.00005]]
    for pol in (CUADRO[:2], lejos, cruzado, diminuto, "no es un polígono", "1,2;3", [[LON, "x"], [1, 2], [3, 4]],
                {"type": "Point", "coordinates": [LON, LAT]}, None, [CUADRO[0]] * 200):
        r = sesion.post("/api/areas", json={"nombre": "Mala", "poligono": pol})
        assert r.status_code == 422, (pol, r.text)
        assert r.json()["detail"]["codigo"] == "poligono", pol
    assert sesion.post("/api/areas", json={"nombre": "Sin polígono"}).status_code == 422
    r = sesion.post("/api/areas", json={"nombre": "Buena", "poligono": CUADRO})
    assert sesion.patch(f"/api/areas/{r.json()['id']}", json={"poligono": cruzado}).json()["detail"]["codigo"] == "poligono"
    # GeoJSON Polygon (cerrado) también sirve
    g = sesion.post("/api/areas", json={"nombre": "GeoJSON", "poligono": geometria.a_geojson(PENTAGONO)})
    assert g.status_code == 201 and g.json()["poligono"] == PENTAGONO


def test_area_dentro_de_medio_por_ciento(sesion):
    for anillo in (PENTAGONO, CUADRO):
        a = sesion.post("/api/areas", json={"nombre": f"Medida {len(anillo)}", "poligono": anillo}).json()
        plana = _area_plana(geometria.validar_anillo(anillo))
        assert abs(a["area_m2"] - plana) / plana < 0.005, (a["area_m2"], plana)
        lado = 0.008 * 6371008.8 * math.pi / 180
        if anillo is CUADRO:  # perímetro de un cuadro de 0,008° de lado (con el coseno de la latitud en los paralelos)
            esperado = 2 * lado + 2 * lado * math.cos(math.radians(LAT))
            assert abs(a["perimetro_m"] - esperado) / esperado < 0.005


def test_color_invalido_y_nombre_repetido(sesion):
    for color in ("rojo", "#12345", "#1234567", "#gggggg", "12345678"):
        r = sesion.post("/api/areas", json={"nombre": "Color", "color": color, "poligono": CUADRO})
        assert r.status_code == 422, color
    a = sesion.post("/api/areas", json={"nombre": "Vereda Norte", "poligono": CUADRO})
    assert a.status_code == 201
    assert a.json()["color"] == "#2a78d6"  # el primero de la paleta
    r = sesion.post("/api/areas", json={"nombre": "vereda  NORTE", "poligono": PENTAGONO})
    assert r.status_code == 409, r.text
    b = sesion.post("/api/areas", json={"nombre": "Otra", "poligono": PENTAGONO}).json()
    assert sesion.patch(f"/api/areas/{b['id']}", json={"nombre": "VEREDA NORTE"}).status_code == 409
    assert sesion.patch(f"/api/areas/{b['id']}", json={"color": "azul"}).status_code == 422
    assert sesion.patch(f"/api/areas/{b['id']}", json={"otra_cosa": 1}).status_code == 422
    # Renombrar una zona a su propio nombre con otras mayúsculas sí se puede
    assert sesion.patch(f"/api/areas/{a.json()['id']}", json={"nombre": "VEREDA NORTE"}).json()["nombre"] == "VEREDA NORTE"
    assert sesion.post("/api/areas", json={"nombre": " ", "poligono": CUADRO}).status_code == 422


def test_tope_de_200(sesion):
    db = sesion.app.state.db
    db.areas.insert_many([{"_id": 10_000 + i, "nombre": f"Zona {i}", "poligono": CUADRO, "color": "#e3141b",
                           "asignada_a": []} for i in range(200)])
    r = sesion.post("/api/areas", json={"nombre": "La 201", "poligono": CUADRO})
    assert r.status_code == 409 and "200" in r.text
    assert len(sesion.get("/api/areas").json()["areas"]) == 200
    sesion.delete("/api/areas/10000")
    assert sesion.post("/api/areas", json={"nombre": "La 201", "poligono": CUADRO}).status_code == 201


# ───────────────────────────── Roles ─────────────────────────────

@pytest.mark.parametrize("rol", ["planillero", "consultor"])
def test_planillero_y_consultor_reciben_403(sesion, como, rol):
    aid = sesion.post("/api/areas", json={"nombre": "Ajena", "poligono": CUADRO}).json()["id"]
    c = como(rol)
    for metodo, ruta, cuerpo in (("GET", "/api/areas", None), ("POST", "/api/areas", {"nombre": "X", "poligono": CUADRO}),
                                 ("GET", f"/api/areas/{aid}", None), ("PATCH", f"/api/areas/{aid}", {"nombre": "Y"}),
                                 ("DELETE", f"/api/areas/{aid}", None)):
        r = c.request(metodo, ruta, json=cuerpo) if cuerpo is not None else c.request(metodo, ruta)
        assert r.status_code == 403 and r.json()["detail"]["codigo"] == "permiso", (metodo, ruta, r.text)
    assert sesion.get(f"/api/areas/{aid}").json()["nombre"] == "Ajena"


def test_el_coordinador_gestiona_zonas_como_a(sesion, coordinador):
    db = sesion.app.state.db
    k = coordinador()
    p = crear_usuario(db, "planillero")
    r = k.post("/api/areas", json={"nombre": "Del coordinador", "poligono": PENTAGONO, "asignada_a": [p["_id"]]})
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    assert r.json()["creado_por"] == k.uid and r.json()["asignada_a"] == [p["_id"]]
    assert k.patch(f"/api/areas/{aid}", json={"color": "#1baf7a"}).status_code == 200
    assert k.delete(f"/api/areas/{aid}").status_code == 200
    for accion in ("crear_area", "editar_area", "borrar_area"):
        (e,) = _auditoria(db, accion)
        assert e["uid"] == k.uid and e["rol"] == "coordinador"
    # Un coordinador no se asigna a una zona: trabaja sobre toda la base (422, como en Usuarios)
    r = k.post("/api/areas", json={"nombre": "Para K", "poligono": CUADRO, "asignada_a": [k.uid]})
    assert r.status_code == 422


# ───────────────────────────── Asignación ─────────────────────────────

def test_asignacion_igual_en_areas_y_usuarios(sesion):
    db = sesion.app.state.db
    p1, p2 = crear_usuario(db, "planillero"), crear_usuario(db, "planillero")
    c1 = crear_usuario(db, "consultor", asignacion={"lugares": [], "areas": [77]})
    sin_asig = crear_usuario(db, "planillero", asignacion=None)
    asig = lambda uid: (db.usuarios.find_one({"_id": uid}).get("asignacion") or {}).get("areas")
    r = sesion.post("/api/areas", json={"nombre": "Asignada", "poligono": CUADRO,
                                        "asignada_a": [p1["_id"], c1["_id"], p1["_id"], sin_asig["_id"]]})
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    assert r.json()["asignada_a"] == sorted([p1["_id"], c1["_id"], sin_asig["_id"]],
                                            key=lambda u: db.usuarios.find_one({"_id": u})["usuario"])
    assert asig(p1["_id"]) == [aid] and asig(c1["_id"]) == [77, aid] and asig(sin_asig["_id"]) == [aid]
    assert db.usuarios.find_one({"_id": c1["_id"]})["asignacion"]["lugares"] == []
    assert db.areas.find_one({"_id": aid})["asignada_a"] == [p1["_id"], c1["_id"], sin_asig["_id"]]

    r = sesion.patch(f"/api/areas/{aid}", json={"asignada_a": [p2["_id"], c1["_id"]]})
    assert sorted(r.json()["asignada_a"]) == sorted([p2["_id"], c1["_id"]])
    assert asig(p1["_id"]) == [] and asig(p2["_id"]) == [aid] and asig(c1["_id"]) == [77, aid]

    # Lo que se cambia desde Usuarios se ve en la zona
    r = sesion.patch(f"/api/usuarios/{p1['_id']}", json={"asignacion": {"lugares": [], "areas": [aid]}})
    assert r.status_code == 200, r.text
    assert p1["_id"] in sesion.get(f"/api/areas/{aid}").json()["asignada_a"]

    for malo in ([999_999], [0]):
        assert sesion.patch(f"/api/areas/{aid}", json={"asignada_a": malo}).status_code == 422
    sesion.delete(f"/api/areas/{aid}")
    assert asig(p1["_id"]) == [] and asig(p2["_id"]) == [] and asig(c1["_id"]) == [77]
    assert json.loads(_auditoria(db, "borrar_area")[0]["detalle"])["asignada_a"]


def test_area_id_asignado_filtra_y_no_asignado_da_403(sesion, como):
    app = sesion.app
    if not _hay_ruta(app, "GET", "/api/trabajo"):
        pytest.skip("requiere el grupo 3: no existe GET /api/trabajo")
    db = app.state.db
    datos = personas_inventadas(60, semilla=51)
    insertar_personas(db, datos)
    dentro = sum(1 for d in datos if d["lat"] is not None and d["lon"] is not None
                 and abs(d["lon"] - LON) <= 0.004 and abs(d["lat"] - LAT) <= 0.004)
    assert 0 < dentro < 60
    otra = sesion.post("/api/areas", json={"nombre": "No asignada", "poligono": PENTAGONO}).json()["id"]
    p = como("planillero")
    aid = sesion.post("/api/areas", json={"nombre": "Del planillero", "poligono": CUADRO,
                                          "asignada_a": [p.uid]}).json()["id"]
    r = p.get("/api/personas", params={"area_id": aid, "situacion": "todas", "por_pagina": 100})
    assert r.status_code == 200, r.text
    assert r.json()["total"] == sesion.get("/api/personas", params={"area_id": aid, "situacion": "todas"}).json()["total"]
    assert r.json()["total"] == sesion.get("/api/personas", params={
        "poligono": geometria.codificar(CUADRO), "situacion": "todas"}).json()["total"]
    r = p.get("/api/personas", params={"area_id": otra})
    assert r.status_code == 403 and r.json()["detail"]["codigo"] == "permiso"
    assert p.get("/api/personas", params={"poligono": geometria.codificar(CUADRO)}).status_code == 403
    assert sesion.get("/api/personas", params={"area_id": 999_999}).status_code == 404


# ───────────────────────────── Gemelo en JavaScript ─────────────────────────────

def test_zona_js_mide_igual_que_el_servidor():
    node = shutil.which("node")
    if node is None:
        pytest.skip("no hay Node para comparar web/js/zona.js")
    casos = [PENTAGONO, CUADRO, [CUADRO[0], CUADRO[2], CUADRO[1], CUADRO[3]], [[LON, LAT], [LON + 0.01, LAT],
                                                                               [LON + 0.01, LAT], [LON, LAT + 0.01]]]
    guion = (f"import({json.dumps(ZONA_JS.as_uri())}).then((z) => {{ const casos = {json.dumps(casos)};"
             " console.log(JSON.stringify({paleta: z.PALETA, casos: casos.map((a) => [z.areaM2(a), z.perimetroM(a),"
             " z.seCruza(a), z.codificar(a), z.decodificar(z.codificar(a))])})); });")
    salida = subprocess.run([node, "--input-type=module", "-e", guion], capture_output=True, text=True, timeout=30)
    assert salida.returncode == 0, salida.stderr
    datos = json.loads(salida.stdout)
    assert tuple(datos["paleta"]) == zonas.PALETA
    for anillo, (area, perimetro, cruza, codigo, vuelta) in zip(casos, datos["casos"]):
        assert area == pytest.approx(geometria.area_m2(anillo), rel=1e-9)
        assert perimetro == pytest.approx(geometria.perimetro_m(anillo), rel=1e-9)
        assert cruza == geometria.se_cruza(anillo), anillo
        assert codigo == geometria.codificar(anillo)
        assert vuelta == geometria.decodificar(codigo)
