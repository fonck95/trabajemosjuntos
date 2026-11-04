"""Identidad en el panel (2.4): cédula ocupada, carrera con el índice único, personas suprimidas, modo «completar»,
escrituras concurrentes de la cédula, comparación por campo (`base`) y fichas unidas o suprimidas (R1: toda
escritura filtra por la ficha activa). Solo datos inventados."""
import pytest

from ayudas_g3 import persona


def test_cedula_ocupada_en_el_alta_y_en_la_edicion(sesion, como):
    db = sesion.app.state.db
    duena = persona(db, nombre="JACINTA INVENTADA DUENA", cedula="94000111", cedulas_anteriores=["94000999"])
    r = sesion.post("/api/personas", json={"nombre": "Otra Inventada", "cedula": "94000111", "forzar": True})
    d = r.json()["detail"]
    assert r.status_code == 409 and d["codigo"] == "cedula_ocupada" and d["id"] == duena and d["nombre"]
    r = sesion.post("/api/personas", json={"nombre": "Otra Inventada", "cedula": "94000999", "forzar": True})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "cedula_ocupada"  # también una cédula anterior
    otra = persona(db, nombre="KARINA INVENTADA OTRA")
    p = como("planillero")
    r = p.patch(f"/api/personas/{otra}", json={"cedula": "94000111"})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "cedula_ocupada"


def test_carrera_con_el_indice_unico_da_409(sesion, monkeypatch):
    from app.api import personas as per
    db = sesion.app.state.db
    persona(db, nombre="LEONOR INVENTADA PRIMERA", cedula="94000222")
    monkeypatch.setattr(per, "cedula_ocupada", lambda *a, **k: None)  # la otra alta llegó entre la revisión y la escritura
    r = sesion.post("/api/personas", json={"nombre": "Leonor Inventada Segunda", "cedula": "94000222", "forzar": True})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "cedula_ocupada"
    otra = persona(db, nombre="MARTINA INVENTADA SIN CEDULA")
    r = sesion.patch(f"/api/personas/{otra}", json={"cedula": "94000222"})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "cedula_ocupada"


def test_suprimida_en_el_alta_la_edicion_y_completar(sesion, como):
    db = sesion.app.state.db
    pid = persona(db, nombre="NICASIA INVENTADA SUPRIMIDA", cedula="94000333", telefono="3007770000")
    assert sesion.delete(f"/api/personas/{pid}").status_code == 200
    p = como("planillero")
    r = p.post("/api/personas", json={"nombre": "Nicasia Inventada Suprimida", "cedula": "94000333", "forzar": True})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "suprimida"
    r = p.post("/api/personas", json={"nombre": "Nicasia Inventada Suprimida", "telefono": "3007770000", "forzar": True})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "suprimida"
    otra = persona(db, nombre="OTRA INVENTADA SIN CEDULA")
    for modo in (None, "completar"):
        r = p.patch(f"/api/personas/{otra}", params={"modo": modo} if modo else {}, json={"cedula": "94000333"})
        assert r.status_code == 409 and r.json()["detail"]["codigo"] == "suprimida", modo
    # A sigue solo con forzar_suprimida y una autorización «sí» en la misma petición
    r = sesion.post("/api/personas", json={"nombre": "Nicasia Inventada Suprimida", "cedula": "94000333", "forzar": True,
                                           "forzar_suprimida": True})
    assert r.status_code == 409
    r = sesion.post("/api/personas", json={"nombre": "Nicasia Inventada Suprimida", "cedula": "94000333", "forzar": True,
                                           "forzar_suprimida": True, "autorizacion": {
                                               "estado": "si", "medio": "escrito", "canales": ["llamada"],
                                               "evidencia": "Formato firmado", "mayor_declarado": True}})
    assert r.status_code == 201 and r.json()["consentimiento"] == "si"


def test_modo_completar_no_pisa_y_deja_alternos(sesion, como):
    db = sesion.app.state.db
    pid = persona(db, nombre="OLIMPIA INVENTADA COMPLETAR", correo="olimpia@correo.co", ocupacion=None)
    p = como("planillero")
    r = p.patch(f"/api/personas/{pid}", params={"modo": "completar"},
                json={"correo": "otro@correo.co", "ocupacion": "Modista", "telefono": "3104445566"})
    f = r.json()
    assert r.status_code == 200 and f["correo"] == "olimpia@correo.co" and f["ocupacion"] == "Modista"
    assert f["telefono"] == "3104445566" and any("alterno" in a for a in f["avisos"])
    assert any(a["campo"] == "correo" and a["valor"] == "otro@correo.co" for a in f["alternos"])
    d = db.personas.find_one({"_id": pid})
    assert d["procedencia"]["ocupacion"]["fuente"] == "panel" and "ocupacion" in d["avance"]
    # Una cédula distinta en «completar» no es la misma persona
    db.personas.update_one({"_id": pid}, {"$set": {"cedula": "94000444"}})
    r = p.patch(f"/api/personas/{pid}", params={"modo": "completar"}, json={"cedula": "94000555"})
    assert r.status_code == 422


def test_dos_cedulas_concurrentes_la_segunda_da_409(sesion, como, monkeypatch):
    from app import proyeccion
    from app.api import personas as per
    db = sesion.app.state.db
    pid = persona(db, nombre="PASCUALA INVENTADA CARRERA")
    p1, p2 = como("planillero"), como("planillero")
    vieja = db.personas.find_one({"_id": pid})  # lo que leyó el segundo antes de que el primero guardara
    assert p1.patch(f"/api/personas/{pid}", json={"cedula": "94000666"}).status_code == 200
    real = proyeccion.persona_activa
    monkeypatch.setattr(per.proyeccion, "persona_activa", lambda db_, pid_, proy=None: dict(vieja) if pid_ == pid
                        else real(db_, pid_, proy))
    r = p2.patch(f"/api/personas/{pid}", json={"cedula": "94000777"})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "cambiada", r.text
    assert r.json()["detail"]["valores_actuales"]["cedula"] == "···666"
    assert db.personas.find_one({"_id": pid})["cedula"] == "94000666"


@pytest.mark.parametrize("como_queda", ["fusionada", "suprimida"])
def test_escrituras_sobre_una_ficha_que_ya_no_esta_activa(sesion, como, como_queda):
    """R1: la escritura filtra por la ficha activa; si se unió o se suprimió, 409 (también en ubicar, notas,
    teléfonos y asistentes de reuniones, R5)."""
    db = sesion.app.state.db
    pid = persona(db, nombre="QUITERIA INVENTADA INACTIVA", telefono="3001110000")
    destino = persona(db, nombre="QUITERIA INVENTADA DESTINO")
    if como_queda == "fusionada":
        db.personas.update_one({"_id": pid}, {"$set": {"fusionada_en": destino}})
    else:
        db.personas.update_one({"_id": pid}, {"$set": {"eliminado": True}})
    reu = sesion.post("/api/reuniones", json={"titulo": "Reunión inventada", "fecha": "2026-11-01"}).json()["id"]
    p = como("planillero")
    for c in (sesion, p):
        for metodo, ruta, cuerpo in [
            ("PATCH", f"/api/personas/{pid}", {"ocupacion": "Pescadora"}),
            ("PUT", f"/api/personas/{pid}/ubicacion", {"lat": 7.0, "lon": -73.9}),
            ("DELETE", f"/api/personas/{pid}/ubicacion", None),
            ("POST", f"/api/personas/{pid}/notas", {"texto": "Nota"}),
            ("POST", f"/api/personas/{pid}/telefonos", {"numero": "3109998877"}),
            ("POST", f"/api/reuniones/{reu}/asistentes", {"persona_id": pid}),
        ]:
            if c is p and "reuniones" in ruta:
                continue  # la reunión es de A y no está abierta: 403 antes
            r = c.request(metodo, ruta, json=cuerpo) if cuerpo is not None else c.request(metodo, ruta)
            assert r.status_code == 409, (metodo, ruta, r.status_code, r.text[:200])
    assert db.personas.find_one({"_id": pid}).get("ocupacion") is None
