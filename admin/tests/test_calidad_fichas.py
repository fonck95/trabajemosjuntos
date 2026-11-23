"""Herramientas del asistente sobre los registros de cada persona (`app/agente/herramientas/fichas.py`): el historial
de acercamientos y de autorizaciones con su lista blanca (nada de teléfonos, datos dictados, categorías sensibles,
filas de planilla ni quién lo registró), y las escrituras de seguimiento (situación, solicitud, duplicado, dato no
disponible, actualización, teléfono, anular, reunión y asistentes): la tarjeta no escribe, aprobar escribe una sola
vez aunque se repita, los permisos de cada rol los decide la API y de quien no autorizó no se escribe nada.

Las herramientas corren en el bucle de la aplicación y llaman a la API de verdad por ASGI con la sesión de cada rol.
Solo datos inventados."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ayudas_calidad import (CEDULA, TEL, TEL2, H, ejecutar, escribe_una_vez, falla_ejecutar, falla_leer, falla_tarjeta,
                            foto, leer, modelo, rica, sin_datos, tarjeta)
from ayudas_calidad import ctx_de  # noqa: F401 (fixture)
from ayudas_g3 import coordinador, persona, tomar
from app import db as bd


@pytest.fixture(autouse=True)
def _siempre_en_horario(monkeypatch):
    from app.api import acercamientos as ac
    monkeypatch.setattr(ac, "fuera_de_horario", lambda *a, **k: False)


FORMA_NO_AUTORIZO = {"id", "nombre", "lugar", "consentimiento", "aviso"}


def _no(db, **extra) -> int:
    return persona(db, nombre="EUDOSIA INVENTADA NOAUTORIZA", consentimiento="no", cedula="71000999",
                   telefono="3005550099", **extra)


# ───────────────────────────── historial_acercamientos ─────────────────────────────

def test_historial_con_lista_blanca_y_notas_enmascaradas(sesion, como, ctx_de):
    db = sesion.app.state.db
    pid = rica(db)
    r = sesion.post(f"/api/personas/{pid}/acercamientos", json={
        "canal": "llamada", "telefono_indice": 0, "resultado": "contesto", "confirma_numero": True,
        "nota": f"Dijo que la llamen al {TEL2} o escriban a otro@correo.co"})
    assert r.status_code == 200, r.text
    aid = r.json()["acercamiento_id"]
    r = sesion.post(f"/api/personas/{pid}/acercamientos", json={"canal": "visita", "resultado": "no_contesto"})
    assert r.status_code == 200, r.text
    res = leer(sesion, ctx_de(sesion), "historial_acercamientos", {"persona_id": pid})
    out = modelo(res)
    sin_datos(out)
    assert res.personas == {pid}
    assert out["total"] == 2 and out["persona"] == {"id": pid, "nombre": "ANACLETA INVENTADA RICA"}
    llamada = next(x for x in out["acercamientos"] if x["id"] == aid)
    assert set(llamada) <= {"id", "fecha", "canal", "resultado", "efectivo", "nota", "anulado", "de_reunion",
                            "propio", "anulable"}
    assert llamada["canal"] == "llamada" and llamada["efectivo"] is True and llamada["propio"] is True
    assert llamada["anulable"] is True  # el administrador, siempre
    assert "···022" in llamada["nota"] and "[correo]" in llamada["nota"]


def test_historial_del_planillero_sin_notas_y_del_consultor_fuera_de_su_trabajo(sesion, como, ctx_de):
    db = sesion.app.state.db
    pid = rica(db)
    sesion.post(f"/api/personas/{pid}/acercamientos", json={"canal": "visita", "resultado": "contesto",
                                                             "nota": "Nota del administrador"})
    p = como("planillero")
    out = modelo(leer(sesion, ctx_de(p), "historial_acercamientos", {"persona_id": pid}))
    assert out["total"] == 1 and "nota" not in out["acercamientos"][0] and "nota" in out
    assert out["acercamientos"][0]["propio"] is False and out["acercamientos"][0]["anulable"] is False
    c = como("consultor")
    e = falla_leer(sesion, ctx_de(c), "historial_acercamientos", {"persona_id": pid})
    assert e.estado in (403, 404, 409)  # la API: el consultor solo con las personas de su trabajo


def test_historial_de_quien_no_autorizo_no_trae_nada(sesion, ctx_de):
    db = sesion.app.state.db
    pid = _no(db)
    db.acercamientos.insert_one({"_id": bd.siguiente_id(db, "acercamientos"), "persona_id": pid, "ts": bd.ahora(),
                                 "fecha": "2026-11-01", "canal": "visita", "resultado": "contesto", "efectivo": True,
                                 "nota": "Contó que está enfermo", "uid": 0})
    res = leer(sesion, ctx_de(sesion), "historial_acercamientos", {"persona_id": pid})
    out = modelo(res)
    assert set(out["persona"]) <= FORMA_NO_AUTORIZO and out["acercamientos"] == []
    assert "enfermo" not in res.texto_para_modelo() and "71000999" not in res.texto_para_modelo()
    assert res.personas == {pid}
    # Por MCP, ni quién es
    ctx = ctx_de(sesion)
    ctx.via = "mcp"
    e = falla_leer(sesion, ctx, "historial_acercamientos", {"persona_id": pid})
    assert e.codigo == "no_contactable" and "EUDOSIA" not in e.mensaje


# ───────────────────────────── autorizaciones_de ─────────────────────────────

def _evento(db, pid, **campos) -> int:
    aid = bd.siguiente_id(db, "autorizaciones")
    db.autorizaciones.insert_one({"_id": aid, "persona_id": pid, "estado": "si", "medio": "escrito",
                                  "canales": ["llamada"], "ts": bd.ahora(), "uid": 0, "usuario": "admin",
                                  "rol": "admin", "confirmada_por": None, **campos})
    return aid


def test_autorizaciones_sin_sensibles_ni_fila_ni_nota_y_con_la_confirmacion(sesion, ctx_de):
    db = sesion.app.state.db
    pid = rica(db)
    ev = _evento(db, pid, medio="declarado_planilla", canales=["llamada", "whatsapp"], sensibles=["salud"],
                 evidencia="Planilla 4, folio 12", evidencia_fila={"cedula": CEDULA, "celular": TEL},
                 nota="Dijo que es víctima", importacion_id=3)
    _evento(db, pid, medio="declarado_planilla", confirmada_por=0, clave_migracion=f"confirma:{ev}",
            nota=f"Confirma la autorización {ev}")
    no_confirmada = _evento(db, pid, medio="declarado_planilla", estado="si", evidencia_sha256={"f.jpg": "ab" * 32})
    res = leer(sesion, ctx_de(sesion), "autorizaciones_de", {"persona_id": pid})
    out = modelo(res)
    sin_datos(out, "víctima", "Planilla 4", "salud")
    assert res.personas == {pid} and out["total"] == 3
    por_id = {x["id"]: x for x in out["autorizaciones"]}
    assert por_id[ev]["confirmada"] is True and por_id[ev]["tiene_evidencia"] is True
    assert por_id[ev]["canales"] == ["llamada", "whatsapp"]
    assert por_id[no_confirmada]["confirmada"] is False and por_id[no_confirmada]["tiene_evidencia"] is True
    assert all(set(x) <= {"id", "estado", "medio", "canales", "fecha", "tiene_evidencia", "confirmada"}
               for x in out["autorizaciones"])


def test_autorizaciones_solo_administrador_y_coordinador_y_nada_de_quien_no_autorizo(sesion, como, ctx_de):
    db = sesion.app.state.db
    pid = rica(db)
    _evento(db, pid)
    k = coordinador(sesion.app, db)
    assert modelo(leer(sesion, ctx_de(k), "autorizaciones_de", {"persona_id": pid}))["total"] == 1
    for rol in ("planillero", "consultor"):
        antes = db.lecturas.count_documents({})
        e = falla_leer(sesion, ctx_de(como(rol)), "autorizaciones_de", {"persona_id": pid})
        assert (e.codigo, e.estado) == ("permiso", 403), rol
        assert db.lecturas.count_documents({}) == antes  # la API rechaza antes de leer la ficha
    no = _no(db)
    _evento(db, no, estado="no", medio="verbal_presencial", nota="Se enojó")
    res = leer(sesion, ctx_de(sesion), "autorizaciones_de", {"persona_id": no})
    out = modelo(res)
    assert set(out["persona"]) <= FORMA_NO_AUTORIZO and out["autorizaciones"] == []
    assert "Se enojó" not in res.texto_para_modelo()


# ───────────────────────────── reportar_situacion ─────────────────────────────

def test_reportar_situacion_escribe_una_vez_y_queda_por_confirmar(sesion, como, ctx_de):
    db = sesion.app.state.db
    pid = rica(db)
    p = como("planillero")

    def cambia(db):
        sit = db.personas.find_one({"_id": pid})["situacion"]
        assert sit["estado"] == "fallecida" and sit["confirmada"] is False

    conf, r1, r2 = escribe_una_vez(sesion, ctx_de(p), "reportar_situacion", {"persona_id": pid,
                                                                             "situacion": "fallecida"}, cambia)
    assert conf.personas == {pid} and "Fallecida" in dict(conf.detalle)["Situación"]
    assert modelo(r1)["reportada"] is True and modelo(r2)["ya_estaba"] is True
    assert r1.personas == {pid}
    # Ya reportada: la tarjeta no se arma otra vez
    assert falla_tarjeta(sesion, ctx_de(p), "reportar_situacion", {"persona_id": pid, "situacion": "fallecida"}
                         ).codigo == "sin_cambios"


def test_reportar_situacion_de_quien_no_autorizo_no_se_hace(sesion, ctx_de):
    db = sesion.app.state.db
    no = _no(db)
    antes = foto(db)
    e = falla_tarjeta(sesion, ctx_de(sesion), "reportar_situacion", {"persona_id": no, "situacion": "no_reside"})
    assert e.codigo == "no_contactable" and foto(db) == antes


# ───────────────────────────── registrar_solicitud ─────────────────────────────

def test_registrar_solicitud_una_vez_con_su_plazo(sesion, como, ctx_de):
    db = sesion.app.state.db
    pid = rica(db)
    p = como("planillero")
    entrada = {"persona_id": pid, "tipo": "correccion", "canal": "visita",
               "descripcion": "Pide corregir el nombre de su barrio"}

    def cambia(db):
        s = db.solicitudes.find_one({"persona_id": pid})
        assert s["tipo"] == "correccion" and s["vence"] and s["creado_por"]["uid"] == p.uid

    conf, r1, r2 = escribe_una_vez(sesion, ctx_de(p), "registrar_solicitud", entrada, cambia)
    detalle = dict(conf.detalle)
    assert detalle["Qué pide"] == "Corrección" and detalle["Plazo de respuesta"] == "15 días hábiles"
    assert "reclamo en trámite" in conf.aviso and conf.personas == {pid}
    assert db.solicitudes.count_documents({}) == 1
    assert modelo(r2)["ya_existia"] is True and modelo(r1)["solicitud"]["id"] == modelo(r2)["solicitud"]["id"]
    # Una igual el mismo día ya no se ofrece
    assert falla_tarjeta(sesion, ctx_de(p), "registrar_solicitud", entrada).codigo == "duplicada"


def test_registrar_solicitud_sin_persona_y_de_quien_no_autorizo(sesion, ctx_de):
    db = sesion.app.state.db
    conf, g = tarjeta(sesion, ctx_de(sesion), "registrar_solicitud", {
        "tipo": "consulta", "canal": "correo", "descripcion": "Preguntan qué datos guarda la campaña"})
    assert "Persona" not in dict(conf.detalle) and conf.personas == set()
    r = ejecutar(sesion, ctx_de(sesion), "registrar_solicitud", g)
    assert r.personas == set() and db.solicitudes.count_documents({"persona_id": None}) == 1
    # Ejercer sus derechos no es tratar sus datos: la supresión de quien no autorizó sí se registra
    no = _no(db)
    conf, g = tarjeta(sesion, ctx_de(sesion), "registrar_solicitud", {
        "persona_id": no, "tipo": "supresion", "canal": "visita", "descripcion": "Pide que borren sus datos"})
    assert conf.personas == {no}
    r = ejecutar(sesion, ctx_de(sesion), "registrar_solicitud", g)
    out = modelo(r)
    assert out["registrada"] is True and "EUDOSIA" not in r.texto_para_modelo()
    assert db.solicitudes.count_documents({"persona_id": no, "tipo": "supresion"}) == 1


# ───────────────────────────── reportar_duplicado ─────────────────────────────

def test_reportar_duplicado_anota_las_dos_fichas_y_es_idempotente(sesion, como, ctx_de):
    db = sesion.app.state.db
    a = rica(db)
    b = persona(db, nombre="ANACLETA INVENTADA RICA BIS")
    p = como("planillero")

    def cambia(db):
        assert db.coincidencias.count_documents({"motivo": "reporte", "estado": "pendiente"}) == 1

    conf, r1, r2 = escribe_una_vez(sesion, ctx_de(p), "reportar_duplicado",
                                   {"persona_id": a, "con_id": b, "nota": "Mismo teléfono y misma vereda"}, cambia)
    assert conf.personas == {a, b} and "No se une nada" in conf.aviso
    assert r1.personas == {a, b} and modelo(r1)["coincidencia_id"] == modelo(r2)["coincidencia_id"]
    # El consultor no tiene la herramienta; si la llamara (por ejemplo, con una lista vieja), la API lo frena
    c = como("consultor")
    antes = foto(db)
    e = falla_ejecutar(sesion, ctx_de(c, tool_use_id="toolu_c"), "reportar_duplicado",
                       H["reportar_duplicado"].validar({"persona_id": a, "con_id": b}))
    assert e.estado == 403 and foto(db) == antes


def test_reportar_duplicado_con_quien_no_autorizo_no_se_hace(sesion, ctx_de):
    db = sesion.app.state.db
    a, no = rica(db), _no(db)
    assert falla_tarjeta(sesion, ctx_de(sesion), "reportar_duplicado", {"persona_id": a, "con_id": no}
                         ).codigo == "no_contactable"
    assert falla_tarjeta(sesion, ctx_de(sesion), "reportar_duplicado", {"persona_id": no, "con_id": a}
                         ).codigo == "no_contactable"


# ───────────────────────────── marcar_no_disponible ─────────────────────────────

def test_marcar_no_disponible_y_quitar_la_marca(sesion, ctx_de):
    db = sesion.app.state.db
    pid = rica(db, cedula=None)

    def cambia(db):
        assert db.personas.find_one({"_id": pid})["no_disponible"]["cedula"]["motivo"] == "no_tiene"

    conf, r1, r2 = escribe_una_vez(sesion, ctx_de(sesion), "marcar_no_disponible",
                                   {"persona_id": pid, "campo": "cedula", "motivo": "no_tiene"}, cambia)
    assert dict(conf.detalle)["Motivo"] == "No lo tiene" and "90 días" in conf.aviso
    assert modelo(r2)["ya_estaba"] is True

    def quitada(db):
        assert "cedula" not in (db.personas.find_one({"_id": pid}).get("no_disponible") or {})

    escribe_una_vez(sesion, ctx_de(sesion, tool_use_id="toolu_quitar"), "marcar_no_disponible",
                    {"persona_id": pid, "campo": "cedula", "quitar": True}, quitada)
    # Un dato que la ficha ya tiene no se marca
    assert falla_tarjeta(sesion, ctx_de(sesion), "marcar_no_disponible",
                         {"persona_id": pid, "campo": "telefono", "motivo": "no_la_dio"}).codigo == "sin_cambios"


def test_el_consultor_solo_marca_cedula_puesto_y_mesa(sesion, como, ctx_de):
    db = sesion.app.state.db
    pid = rica(db, cedula=None)
    c = como("consultor")
    tomar(c, pid)
    e = falla_tarjeta(sesion, ctx_de(c), "marcar_no_disponible", {"persona_id": pid, "campo": "sexo",
                                                                  "motivo": "no_sabe"})
    assert (e.codigo, e.estado) == ("permiso", 403)
    conf, g = tarjeta(sesion, ctx_de(c), "marcar_no_disponible", {"persona_id": pid, "campo": "cedula",
                                                                  "motivo": "no_la_dio"})
    ejecutar(sesion, ctx_de(c), "marcar_no_disponible", g)
    assert db.personas.find_one({"_id": pid})["no_disponible"]["cedula"]["motivo"] == "no_la_dio"


# ───────────────────────────── pedir_actualizacion ─────────────────────────────

def test_pedir_y_atender_una_actualizacion(sesion, como, ctx_de):
    db = sesion.app.state.db
    pid = rica(db)

    def pedida(db):
        assert db.personas.find_one({"_id": pid})["requiere_actualizacion"]["motivo"] == "administrador"

    conf, _, r2 = escribe_una_vez(sesion, ctx_de(sesion), "pedir_actualizacion",
                                  {"persona_id": pid, "accion": "pedir", "nota": "Revisar la dirección"}, pedida)
    assert conf.personas == {pid} and modelo(r2)["ya_estaba"] is True
    p = como("planillero")
    assert falla_tarjeta(sesion, ctx_de(p), "pedir_actualizacion", {"persona_id": pid, "accion": "pedir"}
                         ).codigo == "permiso"

    def atendida(db):
        assert db.personas.find_one({"_id": pid}).get("requiere_actualizacion") is None

    escribe_una_vez(sesion, ctx_de(p), "pedir_actualizacion", {"persona_id": pid, "accion": "atendida"}, atendida)
    assert falla_tarjeta(sesion, ctx_de(p), "pedir_actualizacion", {"persona_id": pid, "accion": "atendida"}
                         ).codigo == "sin_cambios"


# ───────────────────────────── estado_telefono ─────────────────────────────

def test_estado_telefono_resuelve_el_numero_en_el_servidor(sesion, ctx_de):
    db = sesion.app.state.db
    pid = rica(db)
    ctx = ctx_de(sesion)

    def cambia(db):
        t = next(t for t in db.personas.find_one({"_id": pid})["telefonos"] if t["numero"] == TEL2)
        assert t["estado"] == "equivocado"

    conf, r1, r2 = escribe_una_vez(sesion, ctx, "estado_telefono",
                                   {"persona_id": pid, "telefono_indice": 1, "estado": "equivocado"}, cambia)
    detalle = dict(conf.detalle)
    assert detalle["Número"] == "···0022" and "Equivocado" in detalle["Estado"]
    assert TEL2 not in str(conf.detalle) and conf.personas == {pid}
    assert "deja de usarse" in conf.aviso
    assert modelo(r2)["ya_estaba"] is True  # el número ya no es usable y se encontró por su huella
    assert all(TEL2 not in str(x) for x in modelo(r1)["telefonos"])
    # Devolverlo: ya no tiene indice, se nombra por su posición
    def confirmado(db):
        t = next(t for t in db.personas.find_one({"_id": pid})["telefonos"] if t["numero"] == TEL2)
        assert t["estado"] == "confirmado"

    escribe_una_vez(sesion, ctx_de(sesion, tool_use_id="toolu_dos"), "estado_telefono",
                    {"persona_id": pid, "telefono_posicion": 1, "estado": "confirmado", "whatsapp": True}, confirmado)


def test_estado_telefono_principal_y_cambios_entre_tarjeta_y_aprobacion(sesion, como, ctx_de):
    db = sesion.app.state.db
    pid = rica(db)
    conf, g = tarjeta(sesion, ctx_de(sesion), "estado_telefono", {"persona_id": pid, "telefono_indice": 1,
                                                                  "principal": True})
    assert dict(conf.detalle)["Principal"] == "Pasa a ser el primer número"
    r = ejecutar(sesion, ctx_de(sesion), "estado_telefono", g)
    assert modelo(r)["cambios"] == ["principal"]
    assert db.personas.find_one({"_id": pid})["telefono"] == TEL2
    # Si el número de la tarjeta ya no está en la ficha, no se cambia otro
    conf, g = tarjeta(sesion, ctx_de(sesion), "estado_telefono", {"persona_id": pid, "telefono_indice": 1,
                                                                  "estado": "no_usa"})
    db.personas.update_one({"_id": pid}, {"$pull": {"telefonos": {"numero": TEL}}})
    antes = foto(db)
    assert falla_ejecutar(sesion, ctx_de(sesion), "estado_telefono", g).codigo == "cambiada"
    assert foto(db) == antes
    # El consultor no cambia cuál es el principal
    c = como("consultor")
    tomar(c, pid)
    assert falla_tarjeta(sesion, ctx_de(c), "estado_telefono", {"persona_id": pid, "telefono_indice": 0,
                                                                "principal": True}).codigo == "permiso"


def test_estado_telefono_de_quien_no_autorizo_no_se_hace(sesion, ctx_de):
    db = sesion.app.state.db
    no = _no(db)
    assert falla_tarjeta(sesion, ctx_de(sesion), "estado_telefono", {"persona_id": no, "telefono_indice": 0,
                                                                     "estado": "equivocado"}).codigo == "no_contactable"


# ───────────────────────────── anular_acercamiento ─────────────────────────────

def test_anular_el_propio_y_no_el_ajeno(sesion, como, ctx_de):
    db = sesion.app.state.db
    pid = rica(db)
    p = como("planillero")
    r = p.post(f"/api/personas/{pid}/acercamientos", json={"canal": "visita", "resultado": "contesto"})
    assert r.status_code == 200, r.text
    propio = r.json()["acercamiento_id"]
    r = sesion.post(f"/api/personas/{pid}/acercamientos", json={"canal": "visita", "resultado": "no_contesto"})
    ajeno = r.json()["acercamiento_id"]

    def cambia(db):
        assert db.acercamientos.find_one({"_id": propio})["anulado"] is True

    conf, r1, r2 = escribe_una_vez(sesion, ctx_de(p), "anular_acercamiento",
                                   {"persona_id": pid, "acercamiento_id": propio,
                                    "motivo": "Se registró en la ficha equivocada"}, cambia)
    assert conf.personas == {pid} and f"#{propio}" in dict(conf.detalle)["Acercamiento"]
    assert modelo(r2)["ya_estaba"] is True
    e = falla_tarjeta(sesion, ctx_de(p), "anular_acercamiento", {"persona_id": pid, "acercamiento_id": ajeno,
                                                                 "motivo": "No es mío"})
    assert (e.codigo, e.estado) == ("permiso", 403)
    # Pasadas las 24 horas, tampoco el propio
    r = p.post(f"/api/personas/{pid}/acercamientos", json={"canal": "visita", "resultado": "contesto"})
    viejo = r.json()["acercamiento_id"]
    hace = (datetime.now(timezone.utc) - timedelta(hours=30)).replace(microsecond=0).isoformat()
    db.acercamientos.update_one({"_id": viejo}, {"$set": {"ts": hace}})
    assert falla_tarjeta(sesion, ctx_de(p), "anular_acercamiento", {"persona_id": pid, "acercamiento_id": viejo,
                                                                    "motivo": "Tarde"}).codigo == "permiso"
    # Uno que no es de esa persona
    otra = rica(db, nombre="OTRA PERSONA INVENTADA", cedula="93000556")
    assert falla_tarjeta(sesion, ctx_de(sesion), "anular_acercamiento", {"persona_id": otra, "acercamiento_id": ajeno,
                                                                         "motivo": "Prueba"}).codigo == "no_existe"


def test_anular_el_de_una_asistencia_se_hace_quitando_al_asistente(sesion, ctx_de):
    db = sesion.app.state.db
    pid = rica(db)
    rid = sesion.post("/api/reuniones", json={"titulo": "Reunión inventada de prueba",
                                              "fecha": "2026-11-20"}).json()["id"]
    assert sesion.post(f"/api/reuniones/{rid}/asistentes", json={"persona_id": pid}).status_code == 201
    auto = db.acercamientos.find_one({"persona_id": pid, "auto": True})["_id"]
    out = modelo(leer(sesion, ctx_de(sesion), "historial_acercamientos", {"persona_id": pid}))
    fila = next(x for x in out["acercamientos"] if x["id"] == auto)
    assert fila["de_reunion"] is True and fila["anulable"] is False
    assert falla_tarjeta(sesion, ctx_de(sesion), "anular_acercamiento", {"persona_id": pid, "acercamiento_id": auto,
                                                                         "motivo": "Prueba"}).codigo == "invalido"


# ───────────────────────────── editar_reunion y quitar_asistente ─────────────────────────────

def test_editar_reunion_antes_y_despues_una_sola_vez(sesion, como, ctx_de):
    p = como("planillero")
    rid = p.post("/api/reuniones", json={"titulo": "Reunión inventada vereda", "fecha": "2026-11-20",
                                         "hora": "15:00", "descripcion": "Primera versión"}).json()["id"]
    entrada = {"reunion_id": rid, "titulo": "Reunión inventada corregida", "hora_fin": "17:00",
               "compromisos": "Volver en diciembre", "descripcion": "Segunda versión"}

    def cambia(db):
        x = db.reuniones.find_one({"_id": rid})
        assert (x["titulo"], x["hora_fin"], x["compromisos"], x["descripcion"]) == (
            "Reunión inventada corregida", "17:00", "Volver en diciembre", "Segunda versión")

    conf, r1, r2 = escribe_una_vez(sesion, ctx_de(p), "editar_reunion", entrada, cambia)
    detalle = dict(conf.detalle)
    assert detalle["Título"] == "Reunión inventada vereda → Reunión inventada corregida"
    assert "Primera versión" in detalle["Descripción"] and "Segunda versión" in detalle["Descripción"]
    assert modelo(r1)["guardada"] is True and modelo(r2)["ya_estaba"] is True
    assert "asistentes" not in modelo(r1)["reunion"]
    # El planillero no abre la reunión al equipo ni edita las de otros
    assert falla_tarjeta(sesion, ctx_de(p), "editar_reunion", {"reunion_id": rid, "abierta_a_equipo": True}
                         ).codigo == "permiso"
    ajena = sesion.post("/api/reuniones", json={"titulo": "Reunión del administrador", "fecha": "2026-11-21",
                                                "abierta_a_equipo": True}).json()["id"]
    assert falla_tarjeta(sesion, ctx_de(p), "editar_reunion", {"reunion_id": ajena, "tema": "Otro tema"}
                         ).codigo == "permiso"


def test_editar_reunion_cambiada_entre_tarjeta_y_aprobacion(sesion, ctx_de):
    db = sesion.app.state.db
    rid = sesion.post("/api/reuniones", json={"titulo": "Reunión inventada", "fecha": "2026-11-20",
                                              "tema": "Agua"}).json()["id"]
    conf, g = tarjeta(sesion, ctx_de(sesion), "editar_reunion", {"reunion_id": rid, "tema": "Vías"})
    db.reuniones.update_one({"_id": rid}, {"$set": {"tema": "Salud"}})
    e = falla_ejecutar(sesion, ctx_de(sesion), "editar_reunion", g)
    assert e.codigo == "cambiada" and db.reuniones.find_one({"_id": rid})["tema"] == "Salud"
    assert falla_tarjeta(sesion, ctx_de(sesion), "editar_reunion", {"reunion_id": rid, "hora_fin": "10:00"}
                         ).codigo == "invalido"  # hora de fin sin la de inicio


def test_quitar_asistente_una_vez_y_nunca_a_quien_no_autorizo(sesion, ctx_de):
    db = sesion.app.state.db
    pid = rica(db)
    rid = sesion.post("/api/reuniones", json={"titulo": "Reunión inventada", "fecha": "2026-11-20"}).json()["id"]
    assert sesion.post(f"/api/reuniones/{rid}/asistentes", json={"persona_id": pid}).status_code == 201

    def cambia(db):
        assert not db.personas.find_one({"_id": pid}).get("asistencias")
        assert db.acercamientos.find_one({"persona_id": pid, "auto": True})["anulado"] is True

    conf, r1, r2 = escribe_una_vez(sesion, ctx_de(sesion), "quitar_asistente", {"reunion_id": rid, "persona_id": pid},
                                   cambia)
    assert conf.personas == {pid} and modelo(r1)["reunion"]["asistentes_total"] == 0
    assert modelo(r2)["ya_estaba"] is True
    no = _no(db)
    db.personas.update_one({"_id": no}, {"$push": {"asistencias": {"reunion_id": rid, "creado_en": bd.ahora()}}})
    assert falla_tarjeta(sesion, ctx_de(sesion), "quitar_asistente", {"reunion_id": rid, "persona_id": no}
                         ).codigo == "no_contactable"


def test_personas_de_las_tarjetas_quedan_en_la_conversacion(sesion, ctx_de):
    """`Confirmacion.personas` lleva a toda persona que muestra la tarjeta: con la supresión o un «no» se borra la
    conversación que la guarda (también la que solo nombra `con_id`)."""
    db = sesion.app.state.db
    a, b = rica(db), persona(db, nombre="SEGUNDA FICHA INVENTADA")
    conf, _ = tarjeta(sesion, ctx_de(sesion), "reportar_duplicado", {"persona_id": a, "con_id": b})
    assert conf.personas == {a, b}
    assert CEDULA not in str(conf.detalle) and TEL not in str(conf.detalle)
    # El bucle anota las de la entrada y las de la tarjeta
    from app.agente import bucle
    a_ = H["reportar_duplicado"].validar({"persona_id": a, "con_id": b})
    assert bucle._personas_de_entrada(a_) | bucle._personas(conf.personas) == {a, b}
