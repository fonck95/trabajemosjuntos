"""Quien no autorizó no se trata (3.9): toda escritura de P y C sobre una persona con «no» da 409 `no_contactable`
(salvo registrar su «sí» con evidencia o una solicitud), las filas son mínimas y A puede todo. Solo datos
inventados."""
from ayudas_g3 import persona


def _es_no(r):
    return r.status_code == 409 and r.json()["detail"]["codigo"] == "no_contactable" \
        and r.json()["detail"]["motivo"] == "no_autorizo"


def test_cada_escritura_de_planillero_y_consultor_da_409(sesion, como):
    db = sesion.app.state.db
    pid = persona(db, nombre="GENOVEVA INVENTADA NO", telefono="3005556677", consentimiento="no", tipo_documento="CC")
    otra = persona(db, nombre="OTRA INVENTADA CUALQUIERA")
    reu = sesion.post("/api/reuniones", json={"titulo": "Reunión inventada", "fecha": "2026-11-01",
                                              "abierta_a_equipo": True}).json()["id"]
    p = como("planillero")
    for metodo, ruta, cuerpo in [
        ("PATCH", f"/api/personas/{pid}", {"ocupacion": "Pescadora"}),
        ("PATCH", f"/api/personas/{pid}", {}),
        ("POST", f"/api/personas/{pid}/telefonos", {"numero": "3101112233"}),
        ("PATCH", f"/api/personas/{pid}/telefonos/3005556677", {"estado": "equivocado"}),
        ("POST", f"/api/personas/{pid}/notas", {"texto": "Nota inventada"}),
        ("PUT", f"/api/personas/{pid}/ubicacion", {"lat": 7.0, "lon": -73.9}),
        ("DELETE", f"/api/personas/{pid}/ubicacion", None),
        ("POST", f"/api/personas/{pid}/acercamientos", {"canal": "visita", "resultado": "contesto"}),
        ("POST", f"/api/personas/{pid}/duplicado", {"con_id": otra}),
        ("POST", f"/api/personas/{pid}/situacion", {"estado": "fallecida"}),
        ("POST", f"/api/personas/{pid}/no-disponible", {"campo": "cedula", "motivo": "no_tiene"}),
        ("POST", f"/api/personas/{pid}/actualizacion", {"nota": "Atendida"}),
        ("POST", f"/api/reuniones/{reu}/asistentes", {"persona_id": pid}),
        ("POST", f"/api/personas/{pid}/autorizacion", {"estado": "no"}),
    ]:
        r = p.request(metodo, ruta, json=cuerpo) if cuerpo is not None else p.request(metodo, ruta)
        assert _es_no(r), (metodo, ruta, r.status_code, r.text[:200])
    # El consultor tampoco (no la puede tomar: no está en la base de la cola)
    c = como("consultor")
    r = c.post(f"/api/trabajo/tomar/{pid}")
    assert _es_no(r)
    # Su «sí» con evidencia sí se puede registrar, y la persona vuelve a ser tratable
    r = p.post(f"/api/personas/{pid}/autorizacion", json={
        "estado": "si", "medio": "escrito", "canales": ["llamada"], "evidencia": "Planilla 3, folio 2",
        "mayor_declarado": True})
    assert r.status_code == 200 and r.json()["consentimiento"] == "si", r.text
    assert p.patch(f"/api/personas/{pid}", json={"ocupacion": "Pescadora"}).status_code == 200
    # A puede todo
    db.personas.update_one({"_id": pid}, {"$set": {"consentimiento": "no"}})
    assert sesion.patch(f"/api/personas/{pid}", json={"ocupacion": "Docente"}).status_code == 200


def test_filas_minimas_y_busqueda(sesion, como):
    db = sesion.app.state.db
    pid = persona(db, nombre="HIGINIA INVENTADA NO", cedula="93000444", telefono="3005556600", consentimiento="no")
    p = como("planillero")
    for filas in (p.get("/api/personas", params={"q": "HIGINIA"}).json()["filas"],
                  p.get("/api/buscar", params={"q": "HIGINIA"}).json()):
        assert filas[0] == {"id": pid, "nombre": "HIGINIA INVENTADA NO", "cedula_ult3": "···444", "lugar": None,
                            "consentimiento": "no", "abordaje": {"estado": "no_contactar"}}
    c = como("consultor")
    assert c.get("/api/buscar", params={"q": "HIGINIA"}).json()[0]["consentimiento"] == "no"
    assert sesion.get("/api/personas", params={"q": "HIGINIA"}).json()["filas"][0]["cedula"] == "93000444"


def test_revocar_borra_sensibles_y_abre_solicitud(sesion, como):
    db = sesion.app.state.db
    pid = persona(db, nombre="IRENEA INVENTADA REVOCA", sensibles={"victima": "Sí"}, sensibles_autorizados=["victima"],
                  consentimiento="si")
    p = como("planillero")
    r = p.post(f"/api/personas/{pid}/autorizacion", json={"estado": "revocada"})
    assert r.status_code == 200 and r.json()["consentimiento"] == "no"
    d = db.personas.find_one({"_id": pid})
    assert d["sensibles"] == {} and d["sensibles_autorizados"] == [] and d["abordaje"]["estado"] == "no_contactar"
    s = db.solicitudes.find_one({"persona_id": pid, "tipo": "revocatoria"})
    assert s and s["vence"] and d["reclamo_en_tramite"] is True
    assert db.autorizaciones.count_documents({"persona_id": pid}) == 1
