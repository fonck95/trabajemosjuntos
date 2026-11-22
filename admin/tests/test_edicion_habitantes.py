"""Editar y guardar habitantes sin trabas falsas (A, K y P), y la autorización del planillero sin pasos de más:

* «Vi el documento» en una ficha vieja (sin `cedula_verificada` o con null) no da un 409 «cambiada» falso: sin el campo
  cuenta como «no», igual que el tipo de persona.
* El planillero registra el «sí» sin evidencia, canales ni «mayor de 18» obligatorios, y da de alta sin responder la
  autorización (queda pendiente). Lo de quien no autorizó no cambia: P solo registra su «sí».
* El 403 del CSRF lleva `codigo: "csrf"` para que la interfaz tome el de la sesión vigente y reintente.
* P recibe `sensibles_autorizados` en la ficha: con los datos sensibles activos, sus listas no salen siempre bloqueadas.

Solo datos inventados."""
from ayudas_g3 import persona


def test_vi_el_documento_en_una_ficha_vieja_no_da_cambiada(sesion, como):
    db = sesion.app.state.db
    for quien in (sesion, como("planillero")):
        pid = persona(db, nombre="ROSALBA INVENTADA VIEJA", cedula="92000333", tipo_documento="CC")
        db.personas.update_one({"_id": pid}, {"$unset": {"cedula_verificada": ""}})
        r = quien.patch(f"/api/personas/{pid}", json={"cedula_verificada": True, "ocupacion": "Modista",
                                                      "base": {"cedula_verificada": False, "ocupacion": None}})
        assert r.status_code == 200, r.text
        assert r.json()["cedula_verificada"] is True and r.json()["ocupacion"] == "Modista"
        # Con null pasa lo mismo
        pid = persona(db, nombre="ROSALBA INVENTADA NULA", cedula="92000334", tipo_documento="CC")
        db.personas.update_one({"_id": pid}, {"$set": {"cedula_verificada": None}})
        r = quien.patch(f"/api/personas/{pid}", json={"cedula_verificada": True, "base": {"cedula_verificada": False}})
        assert r.status_code == 200, r.text
    # Un cambio real de otra persona sí se detecta
    pid = persona(db, nombre="ROSALBA INVENTADA MARCADA", cedula="92000335", tipo_documento="CC", cedula_verificada=True)
    r = sesion.patch(f"/api/personas/{pid}", json={"ocupacion": "Modista", "base": {"cedula_verificada": False}})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "cambiada"


def test_el_planillero_registra_el_si_sin_pasos_de_mas(sesion, como):
    db = sesion.app.state.db
    p = como("planillero")
    pid = persona(db, nombre="TEODORA INVENTADA SI", tipo_documento="CC")
    r = p.post(f"/api/personas/{pid}/autorizacion", json={"estado": "si", "medio": "verbal_presencial"})
    assert r.status_code == 200, r.text
    assert r.json()["consentimiento"] == "si"
    ev = db.autorizaciones.find_one({"persona_id": pid})
    assert ev["estado"] == "si" and ev["medio"] == "verbal_presencial" and ev["evidencia"] is None
    # Sin medio, el presencial; un medio que no es del planillero sigue rechazado
    pid = persona(db, nombre="TEODORA INVENTADA SIN MEDIO", tipo_documento="CC")
    assert p.post(f"/api/personas/{pid}/autorizacion", json={"estado": "si"}).status_code == 200
    assert db.autorizaciones.find_one({"persona_id": pid})["medio"] == "verbal_presencial"
    pid = persona(db, nombre="TEODORA INVENTADA OTRO MEDIO", tipo_documento="CC")
    assert p.post(f"/api/personas/{pid}/autorizacion", json={"estado": "si", "medio": "verbal_telefono"}).status_code == 422
    # Quien no autorizó sigue igual: el planillero no edita su ficha, solo registra su «sí»
    pid = persona(db, nombre="TEODORA INVENTADA NO", tipo_documento="CC", consentimiento="no")
    r = p.patch(f"/api/personas/{pid}", json={"ocupacion": "Modista"})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "no_contactable"
    assert p.post(f"/api/personas/{pid}/autorizacion", json={"estado": "si"}).status_code == 200


def test_el_alta_del_planillero_sin_autorizacion_queda_pendiente(sesion, como):
    p = como("planillero")
    r = p.post("/api/personas", json={"nombre": "Gumersinda Inventada Alta", "telefono": "3004445566", "forzar": True})
    assert r.status_code in (200, 201), r.text
    assert r.json()["consentimiento"] == "pendiente"


def test_el_csrf_viejo_lleva_su_codigo(sesion):
    r = sesion.patch("/api/personas/1", json={"ocupacion": "x"}, headers={"X-CSRF-Token": "de-otra-sesion"})
    assert r.status_code == 403 and r.json()["detail"]["codigo"] == "csrf"


def test_el_planillero_recibe_las_categorias_sensibles_autorizadas(sesion, como):
    db = sesion.app.state.db
    pid = persona(db, nombre="EUFEMIA INVENTADA SENSIBLE", tipo_documento="CC", consentimiento="si",
                  sensibles={"etnia": "Raizal"}, sensibles_autorizados=["etnia"])
    f = como("planillero").get(f"/api/personas/{pid}").json()
    assert f["sensibles_autorizados"] == ["etnia"] and "sensibles" not in f
