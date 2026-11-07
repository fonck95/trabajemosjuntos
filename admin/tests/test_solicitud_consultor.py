"""Solicitudes de los titulares creadas por un consultor (`POST /api/solicitudes` con `persona_id`).

El consultor solo trabaja con las personas de su trabajo (las que tiene tomadas o a las que les hizo un acercamiento
propio en los últimos 30 días, `filtros.en_alcance_consultor`). Al crear una solicitud con `persona_id` se le aplicaba
esa regla con los argumentos corridos (faltaba `db`) y la ruta respondía 500 con cualquier persona."""
from datetime import datetime, timedelta, timezone

from ayudas_g3 import contactable, persona, tomar


def _consultor(como):
    return como("consultor")


def test_consultor_crea_la_solicitud_de_una_persona_que_tiene_tomada(cliente, como):
    db = cliente.app.state.db
    c = _consultor(como)
    pid = contactable(db, "PERSONA TOMADA INVENTADA", "3001112233")
    tomar(c, pid)
    r = c.post("/api/solicitudes", json={"persona_id": pid, "tipo": "consulta", "canal": "telefono",
                                         "descripcion": "Pregunta qué datos suyos tiene la base"})
    assert r.status_code == 201, r.text
    assert set(r.json()) == {"id", "vence"}
    s = db.solicitudes.find_one({"_id": r.json()["id"]})
    assert s["persona_id"] == pid and s["creado_por"]["rol"] == "consultor"


def test_consultor_crea_la_solicitud_tras_un_acercamiento_propio_reciente(cliente, como):
    db = cliente.app.state.db
    c = _consultor(como)
    pid = contactable(db, "PERSONA LLAMADA AYER INVENTADA", "3002223344")
    ayer = (datetime.now(timezone.utc) - timedelta(days=1)).replace(microsecond=0).isoformat()
    db.acercamientos.insert_one({"persona_id": pid, "uid": c.uid, "ts": ayer, "canal": "llamada",
                                 "resultado": "contesto", "anulado": False})
    r = c.post("/api/solicitudes", json={"persona_id": pid, "tipo": "correccion",
                                         "descripcion": "Su nombre está mal escrito"})
    assert r.status_code == 201, r.text
    assert db.personas.find_one({"_id": pid})["reclamo_en_tramite"] is True


def test_consultor_no_crea_la_solicitud_de_una_persona_fuera_de_su_trabajo(cliente, como):
    db = cliente.app.state.db
    c = _consultor(como)
    pid = contactable(db, "PERSONA AJENA INVENTADA", "3003334455")
    # Un acercamiento de hace más de 30 días, o de otro usuario, no la pone en su trabajo
    viejo = (datetime.now(timezone.utc) - timedelta(days=45)).replace(microsecond=0).isoformat()
    db.acercamientos.insert_many([
        {"persona_id": pid, "uid": c.uid, "ts": viejo, "canal": "llamada", "resultado": "contesto", "anulado": False},
        {"persona_id": pid, "uid": c.uid + 1000, "ts": viejo, "canal": "llamada", "resultado": "contesto"}])
    r = c.post("/api/solicitudes", json={"persona_id": pid, "tipo": "consulta", "descripcion": "Consulta"})
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["codigo"] == "permiso"
    assert db.solicitudes.count_documents({}) == 0


def test_consultor_crea_solicitudes_sin_persona_y_recibe_404_si_no_existe(cliente, como):
    db = cliente.app.state.db
    c = _consultor(como)
    r = c.post("/api/solicitudes", json={"tipo": "registro", "descripcion": "Llamó alguien que no está en la base"})
    assert r.status_code == 201, r.text
    assert c.post("/api/solicitudes", json={"persona_id": 99999, "tipo": "consulta",
                                            "descripcion": "No existe"}).status_code == 404
    assert db.solicitudes.count_documents({}) == 1


def test_planillero_y_administrador_no_usan_la_regla_del_consultor(cliente, sesion, como):
    db = cliente.app.state.db
    pid = persona(db, nombre="PERSONA DE CUALQUIER ZONA INVENTADA")
    p = como("planillero")
    assert p.post("/api/solicitudes", json={"persona_id": pid, "tipo": "consulta",
                                            "descripcion": "Desde la planilla"}).status_code == 201
    assert sesion.post("/api/solicitudes", json={"persona_id": pid, "tipo": "otro",
                                                 "descripcion": "Desde la oficina"}).status_code == 201
