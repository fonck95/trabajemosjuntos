"""Exportación (3.6 y 8.1): solo A; listas y datos sensibles solo con su casilla y un motivo; quien no autorizó, con
motivo opcional (por defecto «operacion_interna»); lo buscado nunca va en claro a la auditoría; columnas nuevas."""
import io
import json

import openpyxl
import pytest

from app import db as bd
from conftest import insertar_personas


def _hoja(r):
    assert r.status_code == 200, r.text
    filas = list(openpyxl.load_workbook(io.BytesIO(r.content)).active.iter_rows(values_only=True))
    cab = list(filas[0])
    return cab, [dict(zip(cab, f)) for f in filas[1:]]


def _ultima_exportacion(db):
    a = db.auditoria.find_one({"accion": "exportar"}, sort=[("_id", -1)])
    return a, json.loads(a["detalle"])


@pytest.fixture
def base(sesion):
    db = sesion.app.state.db
    db.puestos.insert_one({"_id": 3, "eleccion": "2026-presidencial", "codigo": "00-02", "nombre": "COLISEO BENITO ARIAS",
                           "mesas": 4, "activo": True})
    sensible = sesion.post("/api/etiquetas", json={"nombre": "Etiqueta sensible inventada", "sensible": True}).json()["id"]
    comun = sesion.post("/api/etiquetas", json={"nombre": "Etiqueta comun inventada"}).json()["id"]
    sesion.post("/api/campos", json={"etiqueta": "Campo sensible inventado", "tipo": "texto", "sensible": True})
    sesion.post("/api/campos", json={"etiqueta": "Campo comun inventado", "tipo": "texto"})
    claves = {c["etiqueta"]: c["clave"] for c in sesion.get("/api/catalogos").json()["campos"]}
    pid, negada = insertar_personas(db, [
        {"nombre": "TEODULFO INVENTADO RAMIREZ", "cedula": "71000001", "telefono": "3001112233", "consentimiento": "si",
         "fecha_nacimiento": "1980-05-01"},
        {"nombre": "GUMERSINDA FICTICIA PARDO", "consentimiento": "no"},
    ])
    db.personas.update_one({"_id": pid}, {"$set": {
        "tipo_documento": "CC", "cedula_verificada": True, "listas": ["Lista inventada"], "etiquetas": [sensible, comun],
        f"extra.{claves['Campo sensible inventado']}": "valor sensible", f"extra.{claves['Campo comun inventado']}": "valor comun",
        "sensibles": {"victima": "Sí"}, "estado_civil": "Casado(a)", "jefe_hogar": True, "estrato": 2,
        "telefonos": [{"numero": "3001112233", "estado": "confirmado", "no_contactar": False},
                      {"numero": "3004445566", "estado": "sin_verificar", "no_contactar": False},
                      {"numero": "3007778899", "estado": "equivocado", "no_contactar": False}],
        "votacion": {"puesto_id": 3, "puesto_nombre": "COLISEO BENITO ARIAS", "mesa": 2, "mesa_texto": "2", "donde": "yondo",
                     "eleccion": "2026-presidencial", "estado": "verificado", "fuente": "planilla"},
        "puesto_votacion": "COLISEO BENITO ARIAS", "mesa": "2",
        "abordaje": {"estado": "contactado", "ultimo_fecha": "2026-11-03", "n": 2},
        "situacion": {"estado": "activa"}, "creado_por": {"uid": 5, "usuario": "ana.campo", "rol": "planillero"},
        "actualizado_por": {"uid": 0, "usuario": "admin", "rol": "admin", "ts": bd.ahora()}}})
    return db, pid, negada


def test_columnas_nuevas_sin_listas_ni_sensibles(sesion, base):
    db, pid, negada = base
    cab, filas = _hoja(sesion.get("/api/exportar.xlsx"))
    assert cab[1] == "Nombre" and cab[-1] == "Campo comun inventado"
    for t in ("Tipo de documento", "Cédula verificada", "Edad calculada", "Rango de edad", "Otros teléfonos usables",
              "Teléfonos no usables", "Código del puesto", "Estado de la votación", "Dónde vota", "Estado civil",
              "Jefe de hogar", "Estrato", "Abordaje", "Último acercamiento", "Situación", "Creado por", "Actualizado por"):
        assert t in cab, t
    assert "Listas" not in cab and "Campo sensible inventado" not in cab and "Víctima del conflicto" not in cab
    (f,) = filas  # quien no autorizó no sale
    assert f["Nombre"] == "TEODULFO INVENTADO RAMIREZ" and f["Tipo de documento"] == "CC" and f["Cédula verificada"] == "Sí"
    assert f["Otros teléfonos usables"] == "3004445566" and f["Teléfonos no usables"] == "3007778899 (Equivocado)"
    assert (f["Código del puesto"], f["Mesa"], f["Estado de la votación"], f["Dónde vota"]) == ("00-02", "2", "Verificado", "En Yondó")
    assert f["Edad calculada"] >= 46 and f["Rango de edad"] in ("45-54", "55-64")
    assert (f["Abordaje"], f["Último acercamiento"], f["Situación"]) == ("Contactado", "2026-11-03", "Activa")
    assert (f["Creado por"], f["Actualizado por"], f["Jefe de hogar"]) == ("ana.campo", "admin", "Sí")
    assert f["Necesidades / etiquetas"] == "Etiqueta comun inventada" and f["Campo comun inventado"] == "valor comun"
    assert "valor sensible" not in json.dumps(filas, default=str)
    a, d = _ultima_exportacion(db)
    assert (a["uid"], a["rol"]) == (0, "admin")
    assert d["incluir_listas"] is False and d["incluir_sensibles"] is False and d["motivo"] is None


def test_listas_y_sensibles_exigen_motivo(sesion, base):
    db, pid, negada = base
    for params in ({"incluir_listas": 1}, {"incluir_sensibles": 1}, {"incluir_listas": 1, "motivo": "   "}):
        assert sesion.get("/api/exportar.xlsx", params=params).status_code == 422, params
    cab, (f,) = _hoja(sesion.get("/api/exportar.xlsx", params={"incluir_listas": 1, "motivo": "Revisión de listas"}))
    assert f["Listas"] == "Lista inventada" and "Víctima del conflicto" not in cab
    a, d = _ultima_exportacion(db)
    assert d["incluir_listas"] is True and d["motivo"] == "Revisión de listas"
    cab, (f,) = _hoja(sesion.get("/api/exportar.xlsx", params={"incluir_sensibles": 1, "motivo": "Informe a la SIC"}))
    assert f["Víctima del conflicto"] == "Sí" and f["Campo sensible inventado"] == "valor sensible"
    assert "Etiqueta sensible inventada" in f["Necesidades / etiquetas"] and "Listas" not in cab
    assert _ultima_exportacion(db)[1]["incluir_sensibles"] is True
    # Los valores sensibles nunca van a la auditoría
    assert "Sí" not in [v for v in _ultima_exportacion(db)[1].values() if isinstance(v, str)]


def test_sin_autorizacion_con_motivo_opcional_y_busqueda_sin_claro(sesion, base):
    db, pid, negada = base
    cab, filas = _hoja(sesion.get("/api/exportar.xlsx", params={"incluir_sin_autorizacion": 1}))
    assert {f["Nombre"] for f in filas} == {"TEODULFO INVENTADO RAMIREZ", "GUMERSINDA FICTICIA PARDO"}
    d = _ultima_exportacion(db)[1]
    assert d["motivo"] == "operacion_interna" and d["incluir_sin_autorizacion"] is True
    _hoja(sesion.get("/api/exportar.xlsx", params={"incluir_sin_autorizacion": 1, "motivo": "Atender un reclamo"}))
    assert _ultima_exportacion(db)[1]["motivo"] == "Atender un reclamo"
    cab, filas = _hoja(sesion.get("/api/exportar.xlsx", params={"q": "TEODULFO"}))
    assert len(filas) == 1
    a, d = _ultima_exportacion(db)
    assert d["filtros"] == {"q_longitud": 8} and "TEODULFO" not in json.dumps(a, default=str)


@pytest.mark.parametrize("rol", ["planillero", "consultor"])
def test_solo_el_administrador_exporta(sesion, como, rol):
    c = como(rol)
    for ruta in ("/api/exportar.xlsx", "/api/importaciones"):
        r = c.get(ruta)
        assert r.status_code == 403 and r.json()["detail"]["codigo"] == "permiso", ruta
    reu = sesion.post("/api/reuniones", json={"titulo": "Reunion inventada", "fecha": "2026-10-01"}).json()["id"]
    assert c.get(f"/api/reuniones/{reu}/asistentes.csv").status_code == 403
    assert sesion.app.state.db.auditoria.count_documents({"accion": "exportar"}) == 0
