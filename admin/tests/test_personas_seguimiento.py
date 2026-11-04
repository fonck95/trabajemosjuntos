"""Seguimiento y datos nuevos de la ficha (1.3, 1.4, 1.7, 2.4, 8.2): situación, «no disponible», «marcar como
atendido», duplicado, avisos de coherencia, datos sensibles con autorización, votación desde el panel, alta con
autorización y alta simultánea. Solo datos inventados."""
from app import modelo
from ayudas_g3 import persona, puesto


def test_situacion_no_disponible_y_atendido(sesion, como):
    db = sesion.app.state.db
    pid = persona(db, nombre="ADELAIDA INVENTADA SEGUIMIENTO", tipo_documento="CC")
    p = como("planillero")
    f = p.post(f"/api/personas/{pid}/situacion", json={"estado": "no_reside"}).json()
    assert f["situacion"]["estado"] == "no_reside" and f["situacion"]["confirmada"] is False
    assert p.post(f"/api/personas/{pid}/situacion", json={"estado": "activa"}).status_code == 403
    assert p.post(f"/api/personas/{pid}/situacion", json={"estado": "no_reside", "confirmar": True}).status_code == 403
    f = sesion.post(f"/api/personas/{pid}/situacion", json={"estado": "activa"}).json()
    assert f["situacion"]["estado"] == "activa" and f["situacion"]["confirmada"] is True
    a = db.auditoria.find_one({"accion": "situacion", "entidad_id": pid, "uid": p.uid})
    assert a["estado"] == "no_reside"
    # «No lo tiene»: sale de faltan; C solo cédula, puesto y mesa
    assert "cedula" in p.get(f"/api/personas/{pid}").json()["faltan"]
    f = p.post(f"/api/personas/{pid}/no-disponible", json={"campo": "cedula", "motivo": "no_tiene"}).json()
    assert "cedula" not in f["faltan"] and f["no_disponible"]["cedula"]["motivo"] == "no_tiene"
    f = p.post(f"/api/personas/{pid}/no-disponible", json={"campo": "cedula", "quitar": True}).json()
    assert "cedula" in f["faltan"]
    assert como("consultor").post(f"/api/personas/{pid}/no-disponible",
                                  json={"campo": "telefono", "motivo": "no_tiene"}).status_code == 403
    # «Marcar como atendido» es la única vía que borra el pendiente
    db.personas.update_one({"_id": pid}, {"$set": {"requiere_actualizacion": {"motivo": "pedido_consultor", "uid": 9,
                                                                              "usuario": "c", "ts": "x", "nota": "Dirección"}}})
    assert p.patch(f"/api/personas/{pid}", json={"ocupacion": "Docente"}).json()["requiere_actualizacion"]
    f = p.post(f"/api/personas/{pid}/actualizacion", json={"nota": "Se actualizó la dirección"}).json()
    assert f["requiere_actualizacion"] is None
    assert db.auditoria.find_one({"accion": "actualizacion_atendida", "entidad_id": pid, "uid": p.uid})
    assert p.post(f"/api/personas/{pid}/actualizacion", json={"pedir": True}).status_code == 403
    f = sesion.post(f"/api/personas/{pid}/actualizacion", json={"pedir": True, "nota": "Revisar"}).json()
    assert f["requiere_actualizacion"]["motivo"] == "administrador"


def test_duplicado_y_avisos(sesion, como):
    db = sesion.app.state.db
    a = persona(db, nombre="BALBINA INVENTADA DUPLICADA")
    b = persona(db, nombre="BALBINA INVENTADA DUPLICADA BIS")
    p = como("planillero")
    r = p.post(f"/api/personas/{a}/duplicado", json={"con_id": b, "nota": "Es la misma"})
    assert r.status_code == 200
    c = db.coincidencias.find_one({"_id": r.json()["id"]})
    assert c["motivo"] == "reporte" and {c["persona_id"], c["candidato_id"]} == {a, b}
    assert p.post(f"/api/personas/{b}/duplicado", json={"con_id": a}).json()["id"] == c["_id"]  # no se repite
    assert p.post(f"/api/personas/{a}/duplicado", json={"con_id": a}).status_code == 404
    hoy = modelo.hoy_local()
    f = sesion.patch(f"/api/personas/{a}", json={"edad": 20, "fecha_nacimiento": f"{hoy.year - 40}-01-01",
                                                 "tipo_documento": "TI", "cedula": "1001234567"}).json()
    assert any("no coincide" in x for x in f["avisos"]) and any("tarjeta de identidad" in x for x in f["avisos"])
    assert f["edad_efectiva"] == 40 and f["rango_edad"] == "35-44"  # manda la fecha
    assert p.patch(f"/api/personas/{b}", json={"estado_civil": "Inventado"}).status_code == 422
    f = p.patch(f"/api/personas/{b}", json={"estado_civil": "Viudo(a)", "estrato": 2, "jefe_hogar": True}).json()
    assert (f["estado_civil"], f["estrato"], f["jefe_hogar"]) == ("Viudo(a)", 2, True)


def test_sensibles_con_autorizacion(sesion, como):
    db = sesion.app.state.db
    pid = persona(db, nombre="CALIXTA INVENTADA SENSIBLE", tipo_documento="CC")
    p = como("planillero")
    assert p.patch(f"/api/personas/{pid}", json={"sensibles": {"etnia": "Raizal"}}).status_code == 422  # apagados
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"sensibles_activos": True}}, upsert=True)
    r = p.patch(f"/api/personas/{pid}", json={"sensibles": {"etnia": "Raizal"}})
    assert r.status_code == 422 and "no autorizó" in r.json()["detail"]
    r = p.post(f"/api/personas/{pid}/autorizacion", json={
        "estado": "si", "medio": "escrito", "canales": ["visita"], "sensibles": ["etnia"], "evidencia": "Formato 7",
        "mayor_declarado": True})
    assert r.status_code == 200 and r.json()["sensibles_registrados"] == []
    f = p.patch(f"/api/personas/{pid}", json={"sensibles": {"etnia": "Raizal"}}).json()
    assert f["sensibles_registrados"] == ["etnia"] and "sensibles" not in f
    assert db.personas.find_one({"_id": pid})["sensibles"] == {"etnia": "Raizal"}
    assert all("Raizal" not in (x.get("detalle") or "") for x in db.auditoria.find({"entidad_id": pid}))
    assert p.patch(f"/api/personas/{pid}", json={"sensibles": {"victima": "Sí"}}).status_code == 422


def test_votacion_desde_el_panel(sesion, como):
    db = sesion.app.state.db
    puesto(db, 3, "I.E.R. SAN MIGUEL DEL TIGRE", "99-65", mesas=5)
    puesto(db, 4, "COLISEO BENITO ARIAS", "00-02", mesas=4)
    pid = persona(db, nombre="DIGNA INVENTADA VOTA")
    p = como("planillero")
    f = p.patch(f"/api/personas/{pid}", json={"puesto_texto": "SAN MIGUEL DEL TIGRE", "mesa": "Mesa # 2"}).json()
    v = f["votacion"]
    assert (v["puesto_id"], v["mesa"], v["mesa_texto"], v["fuente"], v["estado"]) == (3, 2, "Mesa # 2", "panel", "sin_verificar")
    assert f["puesto_votacion"] == "I.E.R. SAN MIGUEL DEL TIGRE" and f["mesa"] == "Mesa # 2"
    assert v["eleccion"] == "2026-presidencial" and v["estado_efectivo"] == "sin_verificar"
    # Mesa fuera de rango: no se guarda como número y queda por confirmar; el anterior va a alternos
    f = p.patch(f"/api/personas/{pid}", json={"puesto_id": 4, "mesa": 9}).json()
    assert f["votacion"]["mesa"] is None and f["votacion"]["estado"] == "por_confirmar" and f["votacion"]["mesa_texto"] == "9"
    assert any(a["campo"] == "votacion" and a["valor"]["puesto_id"] == 3 for a in f["alternos"])
    # P no vacía el puesto; verificado con el titular
    assert p.patch(f"/api/personas/{pid}", json={"puesto_id": None}).status_code == 422
    f = p.patch(f"/api/personas/{pid}", json={"mesa": 3, "votacion_verificada": True}).json()
    assert f["votacion"]["estado"] == "verificado" and f["votacion"]["fuente"] == "titular"
    assert db.personas.find_one({"_id": pid})["avance"].get("puesto")


def test_alta_con_autorizacion_y_alta_simultanea(sesion, como):
    db = sesion.app.state.db
    p, q = como("planillero"), como("planillero")
    r = p.post("/api/personas", json={"nombre": "Eufemia Inventada Nueva", "telefono": "3017778899", "forzar": True,
                                      "sexo": "F", "edad": 40, "autorizacion": {
                                          "estado": "si", "medio": "verbal_presencial", "canales": ["llamada", "visita"],
                                          "evidencia": "En su casa, 4 nov", "mayor_declarado": True}})
    assert r.status_code == 201, r.text
    f = r.json()
    assert f["consentimiento"] == "si" and f["contacto_habilitado"] is True and f["consentimiento_canales"] == ["llamada", "visita"]
    d = db.personas.find_one({"_id": f["id"]})
    assert d["creado_por"]["uid"] == p.uid and d["cedula_origen"] is None and d["nac_aprox"]
    assert {"telefono", "sexo", "edad", "autorizacion"} <= set(d["avance"])
    a = db.auditoria.find_one({"accion": "crear", "entidad_id": f["id"]})
    assert a["uid"] == p.uid and "autorizacion" in a["completados"]
    # Otro planillero, la misma persona minutos después (con «forzar»): coincidencia por alta simultánea
    r = q.post("/api/personas", json={"nombre": "Eufemia Inventada Nueba", "telefono": "3017778899", "forzar": True})
    assert r.status_code == 201
    c = db.coincidencias.find_one({"motivo": "alta_simultanea"})
    assert c and {c["persona_id"], c["candidato_id"]} == {f["id"], r.json()["id"]}
    # Sin «forzar», las parecidas (por la clave fonética y el teléfono)
    r = q.post("/api/personas", json={"nombre": "Eufemia Inventada Nueva", "telefono": "3017778899"})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "parecidas"
    # Con Idempotency-Key, repetir el alta no crea otra ficha
    clave = {"Idempotency-Key": "alta-inventada-0001"}
    a1 = q.post("/api/personas", json={"nombre": "Fortunata Inventada Unica", "forzar": True}, headers=clave)
    a2 = q.post("/api/personas", json={"nombre": "Fortunata Inventada Unica", "forzar": True}, headers=clave)
    assert a1.status_code == a2.status_code == 201 and a1.json()["id"] == a2.json()["id"]
    assert db.personas.count_documents({"nombre": "FORTUNATA INVENTADA UNICA"}) == 1
