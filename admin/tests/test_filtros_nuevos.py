"""Filtros comunes nuevos (8.3, 6.6): edades, `sin_*` con «no disponible», puesto 0, `poligono` frente a `area_id`
(el mismo total en Habitantes, mapa, exportación e indicadores), 422 `poligono`, más de 500 personas en una zona y el
alcance por lugares de quien no tiene coordenadas. Solo datos inventados."""
import io
from datetime import datetime, timedelta, timezone

import openpyxl

from app import geometria, modelo
from ayudas_g3 import persona
from conftest import CASCO, insertar_personas

ANILLO = [[CASCO[0] - 0.01, CASCO[1] - 0.01], [CASCO[0] + 0.01, CASCO[1] - 0.01], [CASCO[0] + 0.01, CASCO[1] + 0.01],
          [CASCO[0] - 0.01, CASCO[1] + 0.01]]


def _edad(db, nombre, **campos):
    pid = persona(db, nombre=nombre, **campos)
    p = db.personas.find_one({"_id": pid})
    db.personas.update_one({"_id": pid}, {"$set": modelo.calcular_nac(p)})
    return pid


def _total(c, **params):
    return c.get("/api/personas", params=params).json()["total"]


def test_edades_sin_y_puesto(sesion):
    db = sesion.app.state.db
    hoy = modelo.hoy_local()
    treinta = _edad(db, "ONESIMA INVENTADA EDAD", edad=30, edad_ref=hoy.isoformat())
    exacta = _edad(db, "ONESIMA INVENTADA FECHA", fecha_nacimiento=f"{hoy.year - 36}-01-15")
    _edad(db, "ONESIMA INVENTADA MAYOR", edad=50, edad_ref=hoy.isoformat())
    ids = {f["id"] for f in sesion.get("/api/personas", params={"q": "ONESIMA", "edad_min": 30, "edad_max": 40}).json()["filas"]}
    assert ids == {treinta, exacta}
    assert _total(sesion, q="ONESIMA", edad_min=51) == 0
    # sin_*: «no disponible» vigente lo saca; uno viejo, no
    viejo = (datetime.now(timezone.utc) - timedelta(days=120)).replace(microsecond=0).isoformat()
    a = persona(db, nombre="PETRONILA INVENTADA SIN", no_disponible={"cedula": {"motivo": "no_tiene", "uid": 0,
                                                                                "ts": datetime.now(timezone.utc).isoformat()}})
    b = persona(db, nombre="PETRONILA INVENTADA VIEJA", no_disponible={"cedula": {"motivo": "no_tiene", "uid": 0, "ts": viejo}})
    ids = {f["id"] for f in sesion.get("/api/personas", params={"q": "PETRONILA", "sin_cedula": 1}).json()["filas"]}
    assert ids == {b}
    assert a in {f["id"] for f in sesion.get("/api/personas", params={"q": "PETRONILA", "con_cedula": 0}).json()["filas"]}
    # puesto_id=0: sin puesto del catálogo; sexo «sin»
    con = persona(db, nombre="QUINTINA INVENTADA PUESTO", sexo="F",
                  votacion={"puesto_id": 903, "mesa": 2, "eleccion": "2026-presidencial", "estado": "sin_verificar"})
    sin = persona(db, nombre="QUINTINA INVENTADA SINPUESTO")
    assert {f["id"] for f in sesion.get("/api/personas", params={"q": "QUINTINA", "puesto_id": 0}).json()["filas"]} == {sin}
    assert {f["id"] for f in sesion.get("/api/personas", params={"q": "QUINTINA", "puesto_id": 903}).json()["filas"]} == {con}
    assert {f["id"] for f in sesion.get("/api/personas", params={"q": "QUINTINA", "sexo": "sin"}).json()["filas"]} == {sin}
    assert _total(sesion, q="QUINTINA", con_mesa=1) == 1 and _total(sesion, q="QUINTINA", sin_puesto_mesa=1) == 1
    assert _total(sesion, q="QUINTINA", votacion_estado="sin_verificar") == 1
    assert sesion.get("/api/personas", params={"votacion_estado": "inventado"}).status_code == 422


def test_poligono_y_area_dan_el_mismo_total_en_las_cuatro_rutas(sesion):
    db = sesion.app.state.db
    datos = []
    for i in range(520):  # dentro de la zona: más de 500
        datos.append({"nombre": f"RUFINA INVENTADA ZONA {i}", "consentimiento": "pendiente",
                      "lat": round(CASCO[1] - 0.009 + (i % 26) * 0.0007, 6),
                      "lon": round(CASCO[0] - 0.009 + (i // 26) * 0.0009, 6), "geo_precision": "direccion"})
    datos += [{"nombre": "RUFINA INVENTADA FUERA", "lat": 7.2, "lon": -74.0, "geo_precision": "direccion",
               "consentimiento": "pendiente"},
              {"nombre": "RUFINA INVENTADA SINUBICACION", "consentimiento": "pendiente"}]
    insertar_personas(db, datos)
    texto = geometria.codificar(ANILLO)
    db.areas.insert_one({"_id": 5, "nombre": "Zona inventada", "poligono": ANILLO, "asignada_a": [],
                         "area_m2": round(geometria.area_m2(ANILLO)), "perimetro_m": round(geometria.perimetro_m(ANILLO))})
    for params in ({"poligono": texto}, {"area_id": 5}):
        assert _total(sesion, **params) == 520
        assert sesion.get("/api/mapa/puntos", params=params).json()["total"] == 520
        x = sesion.get("/api/exportar.xlsx", params=params)
        assert openpyxl.load_workbook(io.BytesIO(x.content)).active.max_row == 521
        ind = sesion.get("/api/indicadores", params={**params, "alcance": "zona"}).json()
        assert ind["kpi"]["personas"] == 520 and ind["sin_ubicacion"] == 1
        assert abs(ind["area"]["m2"] - geometria.area_m2(ANILLO)) <= 0.005 * geometria.area_m2(ANILLO)
    r = sesion.get("/api/personas", params={"poligono": "-73.9,7.0;-73.9,7.0"})
    assert r.status_code == 422 and r.json()["detail"]["codigo"] == "poligono"
    r = sesion.get("/api/personas", params={"poligono": "-80,7;-79,7;-79,8"})
    assert r.status_code == 422 and r.json()["detail"]["codigo"] == "poligono"
    assert sesion.get("/api/personas", params={"area_id": 404}).status_code == 404


def test_alcance_por_lugares_sin_coordenadas_y_por_areas(sesion, como):
    db = sesion.app.state.db
    l1, l2 = [x["_id"] for x in db.lugares.find({}, {"_id": 1}).limit(2)]
    sin_coord = persona(db, nombre="SEVERA INVENTADA LUGAR", lugar_id=l1)
    en_area = insertar_personas(db, [{"nombre": "SEVERA INVENTADA AREA", "lugar_id": l2, "lat": CASCO[1], "lon": CASCO[0],
                                      "geo_precision": "direccion"}])[0]
    fuera = insertar_personas(db, [{"nombre": "SEVERA INVENTADA FUERA", "lugar_id": l2, "lat": 7.3, "lon": -74.1,
                                    "geo_precision": "direccion"}])[0]
    db.areas.insert_one({"_id": 6, "nombre": "Área inventada", "poligono": ANILLO, "asignada_a": []})
    p = como("planillero", asignacion={"lugares": [l1], "areas": [6]})
    ids = {f["id"] for f in p.get("/api/personas", params={"q": "SEVERA"}).json()["filas"]}
    assert ids == {sin_coord, en_area} and fuera not in ids
    # Su área asignada sí la puede usar como filtro
    assert {f["id"] for f in p.get("/api/personas", params={"q": "SEVERA", "area_id": 6}).json()["filas"]} == {en_area}
    t = p.get("/api/trabajo").json()
    assert t["alcance"]["lugares"][0]["id"] == l1 and t["alcance"]["areas"] == [{"id": 6, "nombre": "Área inventada"}]
