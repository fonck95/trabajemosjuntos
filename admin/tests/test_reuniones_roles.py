"""Reuniones por rol (3.7, 4.4, 7.13): P ve las suyas y las abiertas al equipo (de las demás, solo cuántas hay), solo
A abre una reunión al equipo, los asistentes van con la proyección de fila del rol (sin etiquetas sensibles ni la nota
de asistencia), la asistencia crea o anula el acercamiento automático y borrar la reunión lo anula. Solo datos
inventados."""
from ayudas_g3 import persona, sin_vedados


def test_planillero_ve_las_suyas_y_las_abiertas(sesion, como):
    p = como("planillero")
    cerrada = sesion.post("/api/reuniones", json={"titulo": "Reunión inventada cerrada", "fecha": "2026-11-01"}).json()["id"]
    abierta = sesion.post("/api/reuniones", json={"titulo": "Reunión inventada abierta", "fecha": "2026-11-02",
                                                  "abierta_a_equipo": True}).json()["id"]
    r = p.post("/api/reuniones", json={"titulo": "Reunión del planillero", "fecha": "2026-11-03"})
    assert r.status_code == 201 and r.json()["propia"] is True
    propia = r.json()["id"]
    r = p.get("/api/reuniones")
    assert {x["id"] for x in r.json()} == {abierta, propia} and r.headers["x-reuniones-ajenas"] == "1"
    assert p.get(f"/api/reuniones/{cerrada}").status_code == 403
    assert p.get(f"/api/reuniones/{abierta}").status_code == 200
    # Solo A abre una reunión al equipo; P solo cambia las suyas
    r = p.post("/api/reuniones", json={"titulo": "Otra del planillero", "fecha": "2026-11-03", "abierta_a_equipo": True})
    assert r.status_code == 403
    assert p.patch(f"/api/reuniones/{propia}", json={"tema": "Agua"}).status_code == 200
    assert p.patch(f"/api/reuniones/{abierta}", json={"tema": "Agua"}).status_code == 403
    assert p.patch(f"/api/reuniones/{propia}", json={"abierta_a_equipo": True}).status_code == 403
    assert p.delete(f"/api/reuniones/{propia}").status_code == 403
    assert p.get(f"/api/reuniones/{propia}/asistentes.csv").status_code == 403
    assert sesion.patch(f"/api/reuniones/{cerrada}", json={"abierta_a_equipo": True}).json()["abierta_a_equipo"] is True
    assert p.get(f"/api/reuniones/{cerrada}").status_code == 200


def test_asistentes_proyectados_y_acercamiento_automatico(sesion, como):
    db = sesion.app.state.db
    sens = db.etiquetas.find_one({"nombre": "Víctima del conflicto"})["_id"]
    agua = db.etiquetas.find_one({"nombre": "Agua potable"})["_id"]
    pid = persona(db, nombre="WALDINA INVENTADA ASISTENTE", cedula="97000111", telefono="3009000001", lider=True,
                  etiquetas=[sens, agua], fuentes=["cedulas"], listas=["Lista Inventada"])
    no = persona(db, nombre="WALDINA INVENTADA NO", consentimiento="no")
    p = como("planillero")
    reu = p.post("/api/reuniones", json={"titulo": "Reunión del planillero", "fecha": "2026-10-20"}).json()["id"]
    r = p.post(f"/api/reuniones/{reu}/asistentes", json={"persona_id": pid, "nota": "Pidió agua", "rol": "Vecina"})
    assert r.status_code == 201, r.text
    d = r.json()
    sin_vedados(d)
    a = d["asistentes"][0]
    assert a["etiquetas"] == ["Agua potable"] and "nota" not in a and "cedula" not in a and a["rol"] == "Vecina"
    assert d["necesidades"] == [{"nombre": "Agua potable", "n": 1}]
    # Quien no autorizó no se agrega
    r = p.post(f"/api/reuniones/{reu}/asistentes", json={"persona_id": no})
    assert r.status_code == 409 and r.json()["detail"]["motivo"] == "no_autorizo"
    auto = db.acercamientos.find_one({"persona_id": pid, "auto": True})
    assert auto["canal"] == "reunion" and auto["uid"] == p.uid and auto["fecha"] == "2026-10-20"
    assert db.personas.find_one({"_id": pid})["abordaje"]["estado"] == "contactado"
    # A ve la nota y lo demás
    a = sesion.get(f"/api/reuniones/{reu}").json()["asistentes"][0]
    assert a["nota"] == "Pidió agua" and a["cedula"] == "97000111" and "Víctima del conflicto" in a["etiquetas"]
    # Agregar dos veces no duplica el acercamiento; borrar la reunión lo anula
    p.post(f"/api/reuniones/{reu}/asistentes", json={"persona_id": pid})
    assert db.acercamientos.count_documents({"persona_id": pid, "auto": True}) == 1
    assert sesion.delete(f"/api/reuniones/{reu}").status_code == 200
    assert db.acercamientos.find_one({"_id": auto["_id"]})["anulado"] is True
    assert db.personas.find_one({"_id": pid})["abordaje"] is None
    assert db.personas.find_one({"_id": pid})["asistencias"] == []
