"""Teléfonos en la API (1.2, 2.5): varios números en un texto, estados, «ya no lo usa», principal, retirar (solo A),
el consultor con `principal` y la compatibilidad del PATCH `telefono`. Ningún número se borra. Solo datos
inventados."""
from ayudas_g3 import contactable, persona, tomar


def _nums(d):
    return [(t["numero"], t["estado"]) for t in d["telefonos"]]


def test_varios_numeros_en_un_texto_y_compatibilidad(sesion, como):
    db = sesion.app.state.db
    pid = persona(db, nombre="ROSAURA INVENTADA TELEFONOS", telefono="3001112233")
    p = como("planillero")
    f = p.patch(f"/api/personas/{pid}", json={"telefono": "310 444 5566 / 320-777-8899"}).json()
    assert f["telefono"] == "3104445566" and f["telefono2"] == "3001112233"
    assert [n for n, _ in _nums(f)] == ["3104445566", "3001112233", "3207778899"]
    t = next(x for x in f["telefonos"] if x["numero"] == "3104445566")
    assert t["fuentes"] == ["panel"] and t["agregado_por"] == p.uid and t["tipo"] == "celular"
    # telefono2: justo después del principal
    f = p.patch(f"/api/personas/{pid}", json={"telefono2": "3207778899"}).json()
    assert (f["telefono"], f["telefono2"]) == ("3104445566", "3207778899")
    assert p.patch(f"/api/personas/{pid}", json={"telefono": "123"}).status_code == 422
    # Vaciar: P no puede; A lo marca «retirado» (no se borra)
    assert p.patch(f"/api/personas/{pid}", json={"telefono": None}).status_code == 422
    f = sesion.patch(f"/api/personas/{pid}", json={"telefono": None}).json()
    assert ("3104445566", "retirado") in _nums(f) and f["telefono"] == "3207778899"
    # Escribir de nuevo un número retirado lo vuelve a «sin verificar» y lo pone de principal
    f = p.patch(f"/api/personas/{pid}", json={"telefono": "3104445566"}).json()
    assert ("3104445566", "sin_verificar") in _nums(f) and f["telefono"] == "3104445566"
    assert len(f["telefonos"]) == 3


def test_estados_no_usa_principal_y_retirar(sesion, como):
    db = sesion.app.state.db
    pid = persona(db, nombre="SATURNINA INVENTADA ESTADOS", telefono="3001112200", telefono2="3001112211")
    p = como("planillero")
    r = p.patch(f"/api/personas/{pid}/telefonos/3001112200", json={"estado": "equivocado"})
    assert r.status_code == 200 and r.json()["telefono"] == "3001112211"
    assert p.patch(f"/api/personas/{pid}/telefonos/3009999999", json={"estado": "no_usa"}).status_code == 404
    r = p.patch(f"/api/personas/{pid}/telefonos/3001112211", json={"estado": "no_usa"})
    f = r.json()
    assert f["telefono"] is None and ("3001112211", "no_usa") in _nums(f)
    # Sin números usables: pendiente de actualizar
    assert f["requiere_actualizacion"]["motivo"] == "sin_telefono_valido"
    # Un número que no se usa no puede ser principal
    assert p.post(f"/api/personas/{pid}/telefonos/3001112211/principal").status_code == 422
    p.patch(f"/api/personas/{pid}/telefonos/3001112211", json={"estado": "confirmado"})
    f = p.post(f"/api/personas/{pid}/telefonos", json={"numero": "3155550000", "whatsapp": True}).json()
    assert f["telefono"] == "3001112211" and f["telefono2"] == "3155550000"
    f = p.post(f"/api/personas/{pid}/telefonos/3155550000/principal").json()
    assert f["telefono"] == "3155550000"
    # Retirar es solo de A
    r = p.delete(f"/api/personas/{pid}/telefonos/3155550000")
    assert r.status_code == 403 and r.json()["detail"]["codigo"] == "permiso"
    f = sesion.delete(f"/api/personas/{pid}/telefonos/3155550000").json()
    assert ("3155550000", "retirado") in _nums(f) and len(f["telefonos"]) == 3
    assert db.auditoria.count_documents({"entidad_id": pid, "accion": {"$in": ["telefono_estado", "telefono_agregar",
                                                                              "telefono_principal", "telefono_retirar"]}}) >= 5


def test_consultor_agrega_el_numero_que_dicta_como_principal(sesion, como):
    db = sesion.app.state.db
    pid = contactable(db, "TELESFORA INVENTADA DICTA", "3002223344")
    c = como("consultor")
    # Fuera de su alcance: 403
    assert c.post(f"/api/personas/{pid}/telefonos", json={"numero": "3119998877"}).status_code == 403
    tomar(c, pid)
    f = c.post(f"/api/personas/{pid}/telefonos", json={"numero": "3119998877", "principal": True,
                                                        "anterior_no_usa": True}).json()
    assert f["telefonos"][0] == {"numero": "3119998877", "tipo": "celular", "whatsapp": None, "estado": "confirmado",
                                 "indice": 0}
    d = db.personas.find_one({"_id": pid})
    nuevo = next(t for t in d["telefonos"] if t["numero"] == "3119998877")
    assert nuevo["fuentes"] == ["consultor"] and d["telefono"] == "3119998877" and d["telefono2"] is None
    assert next(t for t in d["telefonos"] if t["numero"] == "3002223344")["estado"] == "no_usa"
    # C marca estado, WhatsApp y «no contactar»; no retira ni hace principal por la ficha
    r = c.patch(f"/api/personas/{pid}/telefonos/3119998877", json={"whatsapp": True})
    assert r.status_code == 200 and r.json()["telefonos"][0]["whatsapp"] is True
    assert c.post(f"/api/personas/{pid}/telefonos/3119998877/principal").status_code == 403
    assert c.delete(f"/api/personas/{pid}/telefonos/3119998877").status_code == 403
    # Lo que no es usable no lo ve (404 para no confirmar que existe)
    assert c.patch(f"/api/personas/{pid}/telefonos/3002223344", json={"estado": "confirmado"}).status_code == 404


def test_reimportar_no_reactiva_y_la_lista_sobrevive_a_un_alta(sesion):
    r = sesion.post("/api/personas", json={"nombre": "Ubaldina Inventada Alta", "telefono": "3013334455",
                                           "telefonos": ["3023334455, 3033334455"], "forzar": True})
    f = r.json()
    assert r.status_code == 201 and [n for n, _ in _nums(f)] == ["3013334455", "3023334455", "3033334455"]
    assert f["telefono"] == "3013334455" and f["telefono2"] == "3023334455"
    assert all(t["fuentes"] == ["panel"] for t in f["telefonos"])
