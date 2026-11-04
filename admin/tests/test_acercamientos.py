"""Acercamientos (sección 4): efectos y anulación con reversión, cada 409 `no_contactable`, la política de
pendientes (sin la base de trámites), P solo visita, `ultimo_contacto`, la reunión como acercamiento, cédulas dictadas
(respuesta única y tope), fallecidos y quien no vive aquí, y el máximo de intentos. Solo datos inventados."""
from datetime import datetime, timedelta, timezone

import pytest

from ayudas_g3 import autorizada, contactable, persona, tomar

LLAMADA = {"canal": "llamada", "telefono_indice": 0}


@pytest.fixture(autouse=True)
def _siempre_en_horario(monkeypatch):
    from app.api import acercamientos as ac
    monkeypatch.setattr(ac, "fuera_de_horario", lambda *a, **k: False)


def _nc(r, motivo):
    return r.status_code == 409 and r.json()["detail"]["codigo"] == "no_contactable" \
        and r.json()["detail"]["motivo"] == motivo


def test_efectos_y_anulacion_con_reversion(sesion, como):
    db = sesion.app.state.db
    pid = contactable(db, "VALERIANA INVENTADA EFECTOS", "3001114455")
    c = como("consultor")
    tomar(c, pid)
    r = c.post(f"/api/personas/{pid}/acercamientos", json={**LLAMADA, "resultado": "contesto", "confirma_numero": True,
                                                            "nota": "Atendió bien"})
    assert r.status_code == 200, r.text
    aid = r.json()["acercamiento_id"]
    d = db.personas.find_one({"_id": pid})
    assert d["telefonos"][0]["estado"] == "confirmado" and d["en_curso"] is None
    assert d["abordaje"]["estado"] == "contactado" and d["abordaje"]["n"] == 1 and d["abordaje_seq"] == 1
    assert d["ultimo_contacto"] == d["abordaje"]["ultimo_fecha"]
    a = db.acercamientos.find_one({"_id": aid})
    assert a["efectos"] == [{"tipo": "telefono_estado", "numero": "3001114455", "antes": "sin_verificar",
                             "despues": "confirmado"}] and a["efectivo"] is True
    aud = db.auditoria.find_one({"accion": "acercamiento", "entidad_id": pid})
    assert aud["canal"] == "llamada" and aud["resultado"] == "contesto" and "Atendió" not in (aud["detalle"] or "")
    # Anular revierte el número y el resumen; no se borra
    f = c.post(f"/api/acercamientos/{aid}/anular", json={"motivo": "Me equivoqué de persona"}).json()
    d = db.personas.find_one({"_id": pid})
    assert d["telefonos"][0]["estado"] == "sin_verificar" and d["abordaje"] is None and f["abordaje"] is None
    assert db.acercamientos.find_one({"_id": aid})["anulado"] is True
    # Con lo anulado ya no está en su alcance: la vuelve a tomar
    assert c.get(f"/api/personas/{pid}").status_code == 403
    tomar(c, pid)
    # Otro consultor no anula lo ajeno; el autor, pasadas 24 h, tampoco; A siempre
    r = c.post(f"/api/personas/{pid}/acercamientos", json={**LLAMADA, "resultado": "numero_equivocado"})
    aid2 = r.json()["acercamiento_id"]
    assert db.personas.find_one({"_id": pid})["telefono"] is None
    assert como("consultor").post(f"/api/acercamientos/{aid2}/anular", json={}).status_code == 403
    viejo = (datetime.now(timezone.utc) - timedelta(hours=25)).replace(microsecond=0).isoformat()
    db.acercamientos.update_one({"_id": aid2}, {"$set": {"ts": viejo}})
    assert c.post(f"/api/acercamientos/{aid2}/anular", json={}).status_code == 403
    assert sesion.post(f"/api/acercamientos/{aid2}/anular", json={"motivo": "Revisión"}).status_code == 200
    assert db.personas.find_one({"_id": pid})["telefono"] == "3001114455"


def test_cada_motivo_de_no_contactable(sesion, como):
    db = sesion.app.state.db
    c = como("consultor")

    def caso(**campos):
        pid = contactable(db, "WENCESLAA INVENTADA MOTIVO", "3001119900")
        tomar(c, pid)
        db.personas.update_one({"_id": pid}, {"$set": campos})
        return pid

    for campos, motivo in [
        ({"consentimiento": "no"}, "no_autorizo"),
        ({"edad": 15, "tipo_documento": None, "mayor_declarado": False}, "menor"),
        ({"tipo_documento": None, "mayor_declarado": False, "edad": None}, "edad_desconocida"),
        ({"reclamo_en_tramite": True}, "reclamo"),
        ({"situacion": {"estado": "fallecida", "confirmada": False}}, "situacion"),
        ({"consentimiento": "pendiente", "contacto_habilitado": False, "consentimiento_canales": []}, "pendiente"),
        ({"contacto_habilitado": False}, "no_habilitado"),
        ({"consentimiento_canales": ["llamada"]}, "canal"),
    ]:
        pid = caso(**campos)
        cuerpo = {**LLAMADA, "resultado": "contesto"}
        if motivo == "canal":
            cuerpo["canal"] = "whatsapp"
        r = c.post(f"/api/personas/{pid}/acercamientos", json=cuerpo)
        if motivo == "menor":  # el consultor ni siquiera abre la ficha de un menor
            assert r.status_code == 409 and r.json()["detail"]["codigo"] == "no_contactable", r.text
        else:
            assert _nc(r, motivo), (motivo, r.status_code, r.text[:200])


def test_pendientes_con_la_politica_apagada_y_prendida(sesion, como):
    db = sesion.app.state.db
    planilla = persona(db, nombre="XIMENA INVENTADA PENDIENTE", telefono="3002220001", tipo_documento="CC",
                       fuentes=["planilla"])
    tramites = persona(db, nombre="YOLANDA INVENTADA TRAMITES", telefono="3002220002", tipo_documento="CC",
                       fuentes=["tramites"])
    c = como("consultor")
    assert _nc(c.post(f"/api/trabajo/tomar/{planilla}"), "pendiente")
    ids = [f["id"] for f in c.get("/api/trabajo/cola").json()["filas"]]
    assert planilla not in ids and tramites not in ids
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"contactar_pendientes": True}}, upsert=True)
    ids = [f["id"] for f in c.get("/api/trabajo/cola").json()["filas"]]
    assert planilla in ids and tramites not in ids  # nunca a quien solo viene de la base de trámites
    assert _nc(c.post(f"/api/trabajo/tomar/{tramites}"), "pendiente")
    tomar(c, planilla)
    # El consultor le pide la autorización por teléfono, con evidencia
    r = c.post(f"/api/personas/{planilla}/acercamientos", json={
        **LLAMADA, "resultado": "contesto", "autorizacion": {"estado": "si", "medio": "verbal_telefono",
                                                             "canales": ["llamada"], "evidencia": "Dijo que sí a las 10",
                                                             "mayor_declarado": True}})
    assert r.status_code == 200 and r.json()["consentimiento"] == "si" and r.json()["contacto_habilitado"] is True
    ev = db.autorizaciones.find_one({"persona_id": planilla})
    assert ev["acercamiento_id"] == r.json()["acercamiento_id"] and ev["uid"] == c.uid
    # Sin evidencia o sin «mayor de 18», no
    r = c.post(f"/api/personas/{planilla}/acercamientos", json={
        **LLAMADA, "resultado": "contesto", "autorizacion": {"estado": "si", "medio": "verbal_telefono",
                                                             "canales": ["llamada"], "mayor_declarado": True}})
    assert r.status_code == 422


def test_planillero_solo_visita_o_reunion(sesion, como):
    db = sesion.app.state.db
    pid = contactable(db, "ZENOBIA INVENTADA VISITA", "3003330000")
    p = como("planillero")
    r = p.post(f"/api/personas/{pid}/acercamientos", json={**LLAMADA, "resultado": "contesto"})
    assert r.status_code == 403 and r.json()["detail"]["codigo"] == "permiso"
    r = p.post(f"/api/personas/{pid}/acercamientos", json={"canal": "visita", "resultado": "contesto", "nota": "Vive"})
    assert r.status_code == 200
    filas = p.get(f"/api/personas/{pid}/acercamientos").json()["filas"]
    assert filas and "nota" not in filas[0]  # P ve la lista sin la nota
    assert sesion.get(f"/api/personas/{pid}/acercamientos").json()["filas"][0]["nota"] == "Vive"


def test_ultimo_contacto_solo_con_efectivos_y_reuniones(sesion, como):
    db = sesion.app.state.db
    pid = contactable(db, "AGRIPINA INVENTADA CONTACTO", "3004440000")
    c = como("consultor")
    tomar(c, pid)
    c.post(f"/api/personas/{pid}/acercamientos", json={**LLAMADA, "resultado": "no_contesto"})
    assert db.personas.find_one({"_id": pid}).get("ultimo_contacto") is None
    assert sesion.post(f"/api/personas/{pid}/notas", json={"texto": "Nota"}).status_code == 201
    assert db.personas.find_one({"_id": pid}).get("ultimo_contacto") is None  # las notas ya no cuentan
    reu = sesion.post("/api/reuniones", json={"titulo": "Reunión inventada", "fecha": "2026-10-15"}).json()["id"]
    sesion.post(f"/api/reuniones/{reu}/asistentes", json={"persona_id": pid})
    d = db.personas.find_one({"_id": pid})
    assert d["ultimo_contacto"] == "2026-10-15" and d["abordaje"]["estado"] == "contactado" and d["abordaje"]["n"] == 2
    auto = db.acercamientos.find_one({"persona_id": pid, "auto": True})
    assert auto["canal"] == "reunion" and auto["reunion_id"] == reu and auto["uid"] == 0
    # Quitarla de la reunión anula el acercamiento automático
    sesion.delete(f"/api/reuniones/{reu}/asistentes/{pid}")
    assert db.acercamientos.find_one({"_id": auto["_id"]})["anulado"] is True
    assert db.personas.find_one({"_id": pid})["abordaje"]["estado"] == "intentado"


def test_cedula_dictada_respuesta_unica_y_tope(sesion, como):
    db = sesion.app.state.db
    duena = persona(db, nombre="BRIGIDA INVENTADA DUENA", cedula="95000111")
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"tope_cedulas_dictadas": 2}}, upsert=True)
    c = como("consultor")
    respuestas = []
    for i, cedula in enumerate(("95000111", "95000222")):
        pid = contactable(db, f"CASILDA INVENTADA DICTA {i}", f"300555000{i}")
        tomar(c, pid)
        r = c.post(f"/api/personas/{pid}/acercamientos", json={
            **LLAMADA, "resultado": "actualizo_datos",
            "datos_dictados": {"cedula": cedula, "cedula_confirmacion": cedula}})
        assert r.status_code == 200, r.text
        respuestas.append(r.json())
        assert db.personas.find_one({"_id": pid})["cedula"] is None  # nunca se aplica sola
    # La misma respuesta exista o no la cédula; C nunca ve la cédula
    assert [x["avisos"][0] for x in respuestas] == ["Cédula registrada para revisión"] * 2
    assert all("cedula" not in x for x in respuestas)
    conf = list(db.conflictos_cedula.find({"motivo": "dictada"}))
    assert len(conf) == 2 and {x["cedula"] for x in conf} == {"95000111", "95000222"}
    assert all(x["estado"] == "pendiente" and x["creado_por"]["uid"] == c.uid for x in conf)
    assert duena  # la dueña sigue igual
    pid = contactable(db, "CASILDA INVENTADA TOPE", "3005550009")
    tomar(c, pid)
    r = c.post(f"/api/personas/{pid}/acercamientos", json={
        **LLAMADA, "resultado": "actualizo_datos", "datos_dictados": {"cedula": "95000333", "cedula_confirmacion": "95000333"}})
    assert r.status_code == 429 and r.json()["detail"]["codigo"] == "volumen"
    r = c.post(f"/api/personas/{pid}/acercamientos", json={
        **LLAMADA, "resultado": "actualizo_datos", "datos_dictados": {"cedula": "95000333", "cedula_confirmacion": "95000334"}})
    assert r.status_code == 422
    assert db.acercamientos.count_documents({"persona_id": pid}) == 0
    # Puesto y mesa dictados: solo si faltan, con fuente consultor y sin verificar
    db.puestos.insert_one({"_id": 3, "eleccion": "2026-presidencial", "codigo": "99-65", "nombre": "PUESTO INVENTADO",
                           "mesas": 5, "activo": True, "alias": [], "alias_ambiguos": []})
    r = c.post(f"/api/personas/{pid}/acercamientos", json={**LLAMADA, "resultado": "actualizo_datos",
                                                            "datos_dictados": {"puesto_id": 3, "mesa": 2}})
    v = db.personas.find_one({"_id": pid})["votacion"]
    assert (v["puesto_id"], v["mesa"], v["fuente"], v["estado"]) == (3, 2, "consultor", "sin_verificar")
    assert db.personas.find_one({"_id": pid})["mesa"] == "2"


def test_fallecio_no_vive_aqui_y_maximo_de_intentos(sesion, como):
    db = sesion.app.state.db
    c = como("consultor")
    a = contactable(db, "DIONISIA INVENTADA FALLECIO", "3006660001")
    tomar(c, a)
    c.post(f"/api/personas/{a}/acercamientos", json={**LLAMADA, "resultado": "fallecio"})
    d = db.personas.find_one({"_id": a})
    assert d["situacion"]["estado"] == "fallecida" and d["situacion"]["confirmada"] is False
    assert a not in [f["id"] for f in c.get("/api/trabajo/cola").json()["filas"]]
    b = contactable(db, "EMERENCIANA INVENTADA SEFUE", "3006660002")
    tomar(c, b)
    c.post(f"/api/personas/{b}/acercamientos", json={**LLAMADA, "resultado": "no_vive_aqui", "se_fue_del_municipio": True})
    d = db.personas.find_one({"_id": b})
    assert d["requiere_actualizacion"]["motivo"] == "direccion" and d["situacion"]["estado"] == "no_reside"
    # Anular revierte la situación reportada
    aid = db.acercamientos.find_one({"persona_id": b})["_id"]
    c.post(f"/api/acercamientos/{aid}/anular", json={})
    assert db.personas.find_one({"_id": b})["situacion"] is None
    # El máximo de intentos sin éxito crea «pendiente de actualizar: no contesta»
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"max_intentos_sin_exito": 2}}, upsert=True)
    x = contactable(db, "FIDELINA INVENTADA NOCONTESTA", "3006660003")
    tomar(c, x)
    for resultado in ("no_contesto", "buzon"):
        c.post(f"/api/personas/{x}/acercamientos", json={**LLAMADA, "resultado": resultado})
    d = db.personas.find_one({"_id": x})
    assert d["abordaje"]["intentos_sin_exito"] == 2 and d["requiere_actualizacion"]["motivo"] == "no_contesta"
    # «No contactar» en la persona: revoca, abre la solicitud y sale de todo
    y = contactable(db, "GENOVEVA INVENTADA RECHAZA", "3006660004")
    tomar(c, y)
    assert c.post(f"/api/personas/{y}/acercamientos", json={**LLAMADA, "resultado": "no_contactar"}).status_code == 422
    c.post(f"/api/personas/{y}/acercamientos", json={**LLAMADA, "resultado": "no_contactar", "alcance": "persona"})
    d = db.personas.find_one({"_id": y})
    assert d["consentimiento"] == "no" and d["abordaje"]["estado"] == "no_contactar"
    assert db.solicitudes.find_one({"persona_id": y, "tipo": "revocatoria"})
    # «No contactar» en un número: solo ese número
    z = contactable(db, "HERMELINDA INVENTADA NUMERO", "3006660005")
    autorizada(db, z)
    tomar(c, z)
    c.post(f"/api/personas/{z}/acercamientos", json={**LLAMADA, "resultado": "no_contactar", "alcance": "numero"})
    d = db.personas.find_one({"_id": z})
    assert d["telefonos"][0]["no_contactar"] is True and d["consentimiento"] == "si" and d["telefono"] is None
