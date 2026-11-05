"""Calidad ampliada (7.12, 8.2): conflictos de cédula, solicitudes de titulares con plazos, situaciones reportadas,
ficha que se conserva al aceptar una coincidencia, confirmación de autorizaciones de planilla y turno de importación.
Solo personas inventadas."""
from datetime import date

from app import db as bd
from app import modelo
from ayudas_g1 import cedula, fila_planilla
from conftest import CEDULAS, excel_cedulas, excel_planilla, excel_tramites
from ayudas_g1 import tramite


def _db(c):
    return c.app.state.db


def _subir(c, ruta, cedulas=None, planilla=None, tramites=None, **extra):
    archivos = []
    if tramites is not None:
        archivos.append(("archivos", ("t.xlsx", excel_tramites(ruta / "t.xlsx", tramites).read_bytes())))
    if cedulas is not None:
        archivos.append(("archivos", ("c.xlsx", excel_cedulas(ruta / "c.xlsx", cedulas).read_bytes())))
    if planilla is not None:
        archivos.append(("archivos", ("p.xlsx", excel_planilla(ruta / "p.xlsx", planilla).read_bytes())))
    return c.post("/api/importar", files=archivos, **extra)


def _persona(c, **datos):
    d = bd.nueva_persona(_db(c), {"nombre": "PERSONA INVENTADA CALIDAD", **datos}, "manual")
    _db(c).personas.insert_one(d)
    return d["_id"]


def test_conflicto_aplicar_y_descartar(sesion, tmp_path):
    c = sesion
    assert _subir(c, tmp_path, cedulas=CEDULAS).status_code == 200
    r = _subir(c, tmp_path, planilla=[fila_planilla("90000003", "MARCO TULIO RENTERIA PALOMEQUE", "3101234511"),
                                      fila_planilla("90000004", "NOMBRE TOTALMENTE DISTINTO INVENTADO", "3101234512")])
    assert r.status_code == 200 and r.json()["conflictos_cedula"] == 2
    lista = c.get("/api/conflictos").json()
    assert len(lista) == 2 and all(x["motivo"] == "nombre_distinto" and x["persona"] for x in lista)
    por = {x["cedula"]: x for x in lista}
    assert por["90000003"]["registro"]["telefonos"] == ["3101234511"]
    # Aplicar: la fila es de esa persona y la completa (sin cambiar su cédula)
    assert c.post(f"/api/conflictos/{por['90000003']['id']}", json={"decision": "aplicar"}).status_code == 200
    p = _db(c).personas.find_one({"cedula": "90000003"})
    assert "3101234511" in [t["numero"] for t in p["telefonos"]] and "planilla" in p["fuentes"]
    assert c.post(f"/api/conflictos/{por['90000004']['id']}", json={"decision": "descartar"}).status_code == 200
    assert c.get("/api/conflictos").json() == []
    assert [x["id"] for x in c.get("/api/conflictos", params={"estado": "descartado"}).json()] == [por["90000004"]["id"]]
    assert c.post(f"/api/conflictos/{por['90000004']['id']}", json={"decision": "aplicar"}).status_code == 404
    aud = _db(c).auditoria.find_one({"accion": "resolver_conflicto", "entidad": "persona"})
    assert aud["uid"] == 0 and "90000003" not in aud["detalle"]


def test_conflicto_corregir_cedula(sesion, tmp_path):
    c = sesion
    _persona(c, nombre="OCUPADA INVENTADA", cedula="90000121")
    r = _subir(c, tmp_path, planilla=[fila_planilla("90000112", "ABELARDO SEGUNDO MONTIEL CUESTA", repetida="90000121")])
    assert r.status_code == 200
    conf = c.get("/api/conflictos").json()
    assert len(conf) == 1 and conf[0]["motivo"] == "posible_digitacion"
    assert conf[0]["registro"]["cedula_digitada"] == "90000112" and conf[0]["registro"]["cedula_repetida"] == "90000121"
    cid, pid = conf[0]["id"], conf[0]["persona"]["id"]
    assert c.post(f"/api/conflictos/{cid}", json={"decision": "aplicar"}).status_code == 422  # nunca une
    r = c.post(f"/api/conflictos/{cid}", json={"decision": "corregir", "cedula_correcta": "90000121"})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "cedula_ocupada"
    assert c.post(f"/api/conflictos/{cid}", json={"decision": "corregir"}).status_code == 422
    r = c.post(f"/api/conflictos/{cid}", json={"decision": "corregir", "cedula_correcta": "90000112"})
    assert r.status_code == 200
    p = _db(c).personas.find_one({"_id": pid})
    assert p["cedula"] == "90000112" and p["cedula_origen"] == "panel" and p["tipo_documento"] == "CC"
    assert p["procedencia"]["cedula"]["fuente"] == "panel"
    # Otra corrección deja la anterior en cedulas_anteriores
    otro = _db(c).conflictos_cedula.insert_one({"_id": 99, "clave": "x", "motivo": "posible_digitacion", "persona_id": pid,
                                                "cedula": "90000113", "estado": "pendiente", "registro": {}})
    assert c.post("/api/conflictos/99", json={"decision": "corregir", "cedula_correcta": "90000113"}).status_code == 200
    p = _db(c).personas.find_one({"_id": pid})
    assert p["cedula"] == "90000113" and p["cedulas_anteriores"] == ["90000112"] and otro


def test_conflicto_corregir_con_cedula_suprimida(sesion):
    c = sesion
    s = _persona(c, nombre="SUPRIMIDA INVENTADA", cedula="90000131")
    bd.suprimir(_db(c), s, "admin")
    pid = _persona(c, nombre="OTRA PERSONA INVENTADA")
    _db(c).conflictos_cedula.insert_one({"_id": 1, "clave": "y", "motivo": "posible_digitacion", "persona_id": pid,
                                         "cedula": "90000131", "estado": "pendiente", "registro": {}})
    r = c.post("/api/conflictos/1", json={"decision": "corregir", "cedula_correcta": "90000131"})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "suprimida"


def test_conflicto_dictada(sesion):
    c = sesion
    db = _db(c)
    libre = _persona(c, nombre="DICTADA INVENTADA LIBRE")
    ocupada = _persona(c, nombre="DICTADA INVENTADA OCUPADA")
    duena = _persona(c, nombre="DUENA INVENTADA", cedula="90000141")
    db.conflictos_cedula.insert_many([
        {"_id": 1, "clave": "d1", "motivo": "dictada", "persona_id": libre, "cedula": "90000140", "estado": "pendiente",
         "fuente": "consultor", "registro": {}},
        {"_id": 2, "clave": "d2", "motivo": "dictada", "persona_id": ocupada, "cedula": "90000141", "estado": "pendiente",
         "fuente": "consultor", "registro": {}}])
    lista = {x["id"]: x for x in c.get("/api/conflictos").json()}
    assert lista[2]["duena"]["id"] == duena and lista[1]["duena"] is None
    assert c.post("/api/conflictos/1", json={"decision": "aplicar"}).status_code == 200
    p = db.personas.find_one({"_id": libre})
    assert p["cedula"] == "90000140" and p["cedula_origen"] == "consultor"
    r = c.post("/api/conflictos/2", json={"decision": "aplicar"})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "cedula_ocupada"
    assert c.post("/api/conflictos/2", json={"decision": "reportar"}).status_code == 200
    co = db.coincidencias.find_one({"motivo": "reporte"})
    assert (co["persona_id"], co["candidato_id"], co["estado"]) == (ocupada, duena, "pendiente")
    assert db.conflictos_cedula.find_one({"_id": 2})["estado"] == "reportado"


def test_solicitudes_y_plazos(sesion):
    c = sesion
    pid = _persona(c)
    r = c.post("/api/solicitudes", json={"persona_id": pid, "tipo": "consulta", "canal": "telefono",
                                         "descripcion": "Quiere saber qué datos tenemos"})
    assert r.status_code == 201
    hoy = modelo.hoy_local()
    assert r.json()["vence"] == modelo.sumar_dias_habiles(hoy, 10).isoformat()
    assert _db(c).personas.find_one({"_id": pid})["reclamo_en_tramite"] is False  # una consulta no es reclamo
    r = c.post("/api/solicitudes", json={"persona_id": pid, "tipo": "supresion", "descripcion": "Pide borrar sus datos"})
    sid = r.json()["id"]
    assert r.json()["vence"] == modelo.sumar_dias_habiles(hoy, 15).isoformat()
    assert _db(c).personas.find_one({"_id": pid})["reclamo_en_tramite"] is True
    r = c.post("/api/solicitudes", json={"tipo": "registro", "descripcion": "Llamó alguien que no está en la base"})
    assert r.status_code == 201 and r.json()["vence"] is None
    assert c.post("/api/solicitudes", json={"tipo": "correccion", "descripcion": "Sin persona"}).status_code == 422
    assert c.post("/api/solicitudes", json={"persona_id": 9999, "tipo": "otro", "descripcion": "No existe"}).status_code == 404
    lista = c.get("/api/solicitudes").json()
    assert [x["tipo"] for x in lista][:2] == ["consulta", "supresion"] and lista[0]["dias_restantes"] >= 10
    assert lista[0]["persona"] == "PERSONA INVENTADA CALIDAD" and lista[-1]["vence"] is None
    assert c.patch(f"/api/solicitudes/{sid}", json={"estado": "resuelta", "respuesta": "Se suprimió"}).status_code == 200
    assert _db(c).personas.find_one({"_id": pid})["reclamo_en_tramite"] is False
    assert len(c.get("/api/solicitudes").json()) == 2 and len(c.get("/api/solicitudes", params={"estado": "resuelta"}).json()) == 1
    aud = _db(c).auditoria.find_one({"accion": "solicitud_crear", "entidad": "persona"})
    assert aud["entidad_id"] == pid and "borrar" not in (aud["detalle"] or "")
    assert modelo.sumar_dias_habiles(date(2026, 11, 6), 1) == date(2026, 11, 9)  # viernes → lunes


def test_situaciones_reportadas(sesion):
    c = sesion
    pid = _persona(c, situacion={"estado": "fallecida", "confirmada": False, "reportado_por": 7, "ts": bd.ahora(),
                                  "fuente": "consultor"})
    otra = _persona(c, situacion={"estado": "no_reside", "confirmada": False, "reportado_por": 7, "ts": bd.ahora()})
    assert {x["id"] for x in c.get("/api/situaciones").json()} == {pid, otra}
    assert c.post(f"/api/situaciones/{pid}", json={"decision": "confirmar"}).status_code == 200
    p = _db(c).personas.find_one({"_id": pid})
    assert p["situacion"]["estado"] == "fallecida" and p["situacion"]["confirmada"] is True
    assert [x["id"] for x in c.get("/api/situaciones").json()] == [otra]
    assert len(c.get("/api/situaciones", params={"todas": 1}).json()) == 2
    assert c.post(f"/api/situaciones/{otra}", json={"decision": "revertir"}).status_code == 200
    assert _db(c).personas.find_one({"_id": otra})["situacion"]["estado"] == "activa"
    assert c.post(f"/api/situaciones/{otra}", json={"decision": "confirmar"}).status_code == 404
    assert _db(c).auditoria.find_one({"accion": "situacion", "entidad_id": pid})["estado"] == "fallecida"


def test_conservar_al_aceptar_una_coincidencia(sesion, tmp_path):
    c = sesion
    tram = [tramite(5001, "CASIMIRO INVENTADO CONSERVAR", "3005001001")]
    r = _subir(c, tmp_path, tramites=tram, cedulas=[cedula("90000151", "CASIMIRO INVENTADO CONSERVAR"),
                                                    cedula("90000152", "CASIMIRO INVENTADO CONSERVAR")])
    assert r.json()["cedulas_en_revision"] == 2
    pares = c.get("/api/coincidencias").json()
    assert all(p["motivo"] == "cruce_cedula" for p in pares)
    tramites_id = pares[0]["candidato"]["id"]
    # Por defecto se conserva la que tiene cédula
    r = c.post(f"/api/coincidencias/{pares[0]['id']}", json={"decision": "aceptar"})
    assert r.status_code == 200 and r.json()["id"] == pares[0]["persona"]["id"]
    assert _db(c).personas.find_one({"_id": tramites_id})["fusionada_en"] == pares[0]["persona"]["id"]
    assert len(_db(c).personas.find_one({"_id": pares[0]["persona"]["id"]})["tramites"]) == 1
    assert c.get("/api/coincidencias").json() == []  # la otra quedó cerrada al reapuntarse


def test_conservar_el_candidato_si_se_pide(sesion, tmp_path):
    c = sesion
    r = _subir(c, tmp_path, tramites=[tramite(5101, "TIBURCIA INVENTADA PIDE", "3005101001")],
               cedulas=[cedula("90000161", "TIBURCIA INVENTADA PIDE"), cedula("90000162", "TIBURCIA INVENTADA PIDE")])
    pares = c.get("/api/coincidencias").json()
    r = c.post(f"/api/coincidencias/{pares[0]['id']}", json={"decision": "aceptar", "conservar": "candidato"})
    assert r.status_code == 200 and r.json()["id"] == pares[0]["candidato"]["id"]
    assert _db(c).personas.find_one({"_id": pares[0]["candidato"]["id"]})["cedula"] == pares[0]["persona"]["cedula"]


def test_confirmar_autorizaciones_de_la_planilla(sesion, tmp_path):
    c = sesion
    r = _subir(c, tmp_path, planilla=[fila_planilla("90000171", "PRUDENCIA INVENTADA DECLARA", "3101110171", medio=None),
                                      fila_planilla("90000172", "RIGOBERTO INVENTADO REVOCA", "3101110172", medio=None)])
    assert r.json()["autorizaciones_por_confirmar"] == 2
    db = _db(c)
    imp_id = db.importaciones.find_one()["_id"]
    a = db.personas.find_one({"cedula": "90000171"})
    b = db.personas.find_one({"cedula": "90000172"})
    assert a["contacto_habilitado"] is False
    # Uno revocó después: no se confirma lo que ya no está vigente
    db.autorizaciones.insert_one(bd.autorizacion_doc(db, b["_id"], "revocada", "verbal_telefono"))
    bd.derivar(db, [b["_id"]])
    assert c.post(f"/api/importaciones/{imp_id}/confirmar-autorizaciones", json={"evidencia": "x"}).status_code == 422
    r = c.post(f"/api/importaciones/{imp_id}/confirmar-autorizaciones",
               json={"evidencia": "Planillas físicas archivadas en la sede, carpeta 3"})
    assert r.status_code == 200 and r.json() == {"confirmadas": 1}
    a = db.personas.find_one({"_id": a["_id"]})
    assert a["contacto_habilitado"] is True and a["consentimiento_medio"] == "declarado_planilla"
    assert db.personas.find_one({"_id": b["_id"]})["consentimiento"] == "no"
    r = c.post(f"/api/importaciones/{imp_id}/confirmar-autorizaciones", json={"evidencia": "Otra vez la evidencia"})
    assert r.json() == {"confirmadas": 0}
    assert c.post("/api/importaciones/999/confirmar-autorizaciones", json={"evidencia": "No existe"}).status_code == 404


def test_turno_de_importacion_409_y_se_libera_tras_un_error(sesion, tmp_path):
    c = sesion
    db = _db(c)
    db.meta.insert_one({"_id": "importando", "dueño": "otro", "hasta": bd._instante() + bd.timedelta(minutes=10)})
    r = _subir(c, tmp_path, cedulas=CEDULAS)
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "importando"
    db.meta.delete_one({"_id": "importando"})
    malo = tmp_path / "malo.xlsx"
    malo.write_bytes(b"esto no es un Excel")
    r = c.post("/api/importar", files=[("archivos", ("malo.xlsx", malo.read_bytes()))])
    assert r.status_code == 422
    assert db.meta.find_one({"_id": "importando"})["hasta"] <= bd._instante()  # liberado en el finally
    assert _subir(c, tmp_path, cedulas=CEDULAS).status_code == 200


def test_lugar_exige_latitud_y_longitud_juntas(sesion):
    c = sesion
    assert c.post("/api/lugares", json={"nombre": "Lugar inventado", "tipo": "vereda", "lat": 7.0}).status_code == 422
    r = c.post("/api/lugares", json={"nombre": "Lugar inventado", "tipo": "vereda", "lat": 7.0, "lon": -73.9})
    assert r.status_code == 201
    lid = r.json()["id"]
    assert c.patch(f"/api/lugares/{lid}", json={"lon": -73.95}).status_code == 422
    assert c.patch(f"/api/lugares/{lid}", json={"lat": 7.01, "lon": -73.95}).status_code == 200
    assert c.patch(f"/api/lugares/{lid}", json={"alias": ["OTRO NOMBRE"]}).status_code == 200


def test_planillero_y_consultor_no_resuelven(cliente, como):
    p = como("planillero")
    assert p.get("/api/conflictos").status_code == 403
    assert p.get("/api/solicitudes").status_code == 403
    assert p.post("/api/situaciones/1", json={"decision": "confirmar"}).status_code == 403
    pid = _persona(p, nombre="PERSONA INVENTADA SOLICITUD")
    r = p.post("/api/solicitudes", json={"persona_id": pid, "tipo": "correccion", "descripcion": "Corregir el nombre"})
    assert r.status_code == 201
