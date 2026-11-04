"""Unión de fichas (2.6): escritura parcial sobre el destino, autorización combinada, alternos, lo ligado reasignado,
coincidencias reapuntadas y reparación de una unión cortada. Solo personas inventadas."""
import pytest

from app import db as bd
from app import modelo


def _ficha(db, **datos):
    d = bd.nueva_persona(db, {"nombre": "PERSONA INVENTADA UNION", **datos}, datos.pop("fuente", "manual"))
    db.personas.insert_one(d)
    return d["_id"]


def _autoriza(db, pid, estado, canales=(), medio="escrito", **k):
    db.autorizaciones.insert_one(bd.autorizacion_doc(db, pid, estado, medio, canales=list(canales), **k))
    bd.derivar(db, [pid])


def test_no_gana_y_se_borran_los_sensibles(bases):
    db = bases()
    a = _ficha(db, sensibles={"etnia": "Ninguno"})
    b = _ficha(db)
    _autoriza(db, a, "si", ["llamada", "whatsapp"], sensibles=["etnia"])
    _autoriza(db, b, "no", medio="verbal_presencial")
    bd.fusionar(db, a, b, "admin")
    p = db.personas.find_one({"_id": a})
    assert p["consentimiento"] == "no" and p["sensibles"] == {} and p["sensibles_autorizados"] == []
    assert p["contacto_habilitado"] is False


def test_interseccion_de_canales_y_evento_fusion(bases):
    db = bases()
    a, b = _ficha(db), _ficha(db)
    _autoriza(db, a, "si", ["llamada", "whatsapp"], ts="2026-10-01T15:00:00+00:00")
    _autoriza(db, b, "si", ["whatsapp", "sms"], ts="2026-10-02T15:00:00+00:00")
    bd.fusionar(db, a, b, "admin")
    p = db.personas.find_one({"_id": a})
    assert p["consentimiento"] == "si" and p["consentimiento_canales"] == ["whatsapp"] and p["contacto_habilitado"]
    ev = db.autorizaciones.find_one({"medio": "fusion"})
    assert ev["persona_id"] == a and ev["canales"] == ["whatsapp"] and ev["estado"] == "si"
    assert db.autorizaciones.count_documents({"persona_id": a}) == 3  # las dos reasignadas y la de la unión


def test_un_si_declarado_sin_confirmar_no_se_habilita_al_unir(bases):
    db = bases()
    a, b = _ficha(db), _ficha(db)
    _autoriza(db, a, "si", ["llamada"], medio="declarado_planilla", ts="2026-10-01T15:00:00+00:00")
    _autoriza(db, b, "si", ["llamada", "sms"], medio="declarado_planilla", ts="2026-10-02T15:00:00+00:00")
    bd.fusionar(db, a, b, "admin")
    p = db.personas.find_one({"_id": a})
    assert p["consentimiento_canales"] == ["llamada"] and p["contacto_habilitado"] is False


def test_alternos_solo_de_campos_con_procedencia(bases):
    db = bases()
    a = _ficha(db, sexo="F", ficha="0589300000001", ocupacion=None, edad=40, personas_hogar=3)
    b = _ficha(db, sexo="M", ficha="0589300000002", ocupacion="Pescador", edad=41, personas_hogar=5,
               correo="b@ejemplo.test")
    bd.fusionar(db, a, b, "admin")
    p = db.personas.find_one({"_id": a})
    assert (p["sexo"], p["ficha"], p["ocupacion"], p["edad"], p["correo"]) == ("F", "0589300000001", "Pescador", 40,
                                                                                "b@ejemplo.test")
    alt = {(x["campo"], x["valor"]) for x in p["alternos"]}
    assert alt == {("sexo", "M"), ("edad", 41)}
    assert all(x["fuente"] == f"fusion:{b}" for x in p["alternos"])


def test_colecciones_reasignadas_y_coincidencias_reapuntadas(bases):
    db = bases()
    a, b, c, d = _ficha(db), _ficha(db), _ficha(db), _ficha(db)
    db.acercamientos.insert_one({"_id": 1, "persona_id": b, "resultado": "contesto", "canal": "llamada",
                                 "ts": "2026-11-01T15:00:00+00:00", "anulado": False})
    db.solicitudes.insert_one({"_id": 1, "persona_id": b, "tipo": "consulta", "estado": "pendiente"})
    db.conflictos_cedula.insert_one({"_id": 1, "clave": "k", "persona_id": b, "cedula": "90000555"})
    db.coincidencias.insert_many([
        {"_id": 1, "persona_id": b, "candidato_id": c, "estado": "pendiente", "puntaje": 0.8},
        {"_id": 2, "persona_id": a, "candidato_id": b, "estado": "pendiente", "puntaje": 0.9},
        {"_id": 3, "persona_id": a, "candidato_id": d, "estado": "pendiente", "puntaje": 0.7},
        {"_id": 4, "persona_id": b, "candidato_id": d, "estado": "pendiente", "puntaje": 0.7}])
    bd.fusionar(db, a, b, "admin")
    assert db.acercamientos.find_one({"_id": 1})["persona_id"] == a
    assert db.solicitudes.find_one({"_id": 1})["persona_id"] == a
    assert db.conflictos_cedula.find_one({"_id": 1})["persona_id"] == a
    co = {x["_id"]: x for x in db.coincidencias.find()}
    assert (co[1]["persona_id"], co[1]["candidato_id"], co[1]["estado"]) == (a, c, "pendiente")
    assert co[2]["estado"] == "aceptada"
    assert co[3]["estado"] == "pendiente" and co[4]["estado"] == "cerrada"  # (a, d) ya existía
    p = db.personas.find_one({"_id": a})
    assert p["abordaje"]["estado"] == "contactado" and p["abordaje"]["n"] == 1


def test_dos_cedulas_distintas_nunca_se_unen(bases):
    db = bases()
    a, b = _ficha(db, cedula="90000601"), _ficha(db, cedula="90000602")
    with pytest.raises(bd.FusionImposible):
        bd.fusionar(db, a, b, "admin")
    assert db.personas.find_one({"_id": b})["cedula"] == "90000602" and db.personas.find_one({"_id": b})["fusionada_en"] is None


def test_la_union_conserva_cedula_ubicacion_y_listas(bases):
    db = bases()
    a = _ficha(db, lat=7.0, lon=-73.9, geo_precision="manual", geo_manual="punto", listas=["Lista A"],
               telefono="3001110001")
    b = _ficha(db, cedula="90000603", listas=["Lista B"], telefono="3001110002", fuente="cedulas",
               origen=[{"fuente": "cedulas", "clave": "90000603", "datos": {"nombre": "X"}, "importacion_id": 1}],
               tramites=[{"id_externo": "77", "fecha": "2025-01-01", "telefono": "3001110002"}],
               clave_tramites="PERSONA INVENTADA UNION",
               votacion={"puesto_id": 3, "puesto_nombre": "X", "mesa": 2, "mesa_texto": None, "estado": "sin_verificar"})
    bd.fusionar(db, a, b, "admin")
    p = db.personas.find_one({"_id": a})
    assert p["cedula"] == "90000603" and p["listas"] == ["Lista A", "Lista B"]
    assert (p["lat"], p["lon"], p["geo_manual"]) == (7.0, -73.9, "punto") and p["punto"] == modelo.punto(7.0, -73.9)
    assert [t["numero"] for t in p["telefonos"]] == ["3001110001", "3001110002"]
    assert p["votacion"]["puesto_id"] == 3 and p["mesa"] == "2" and len(p["tramites"]) == 1 and len(p["origen"]) == 1
    assert "PERSONA INVENTADA UNION" in p["claves_tramites"] and set(p["fuentes"]) == {"manual", "cedulas"}
    o = db.personas.find_one({"_id": b})
    assert o["nombre"] == "FUSIONADA" and o["fusionada_en"] == a and o["cedula"] is None and "cedula_en_traspaso" not in o
    assert db.auditoria.find_one({"accion": "fusionar"})["entidad_id"] == a


def test_reparacion_de_una_union_cortada_despues_del_paso_1(bases):
    db = bases()
    a = _ficha(db, telefono="3001110001")
    b = _ficha(db, cedula="90000604", telefono="3001110002", listas=["Lista C"],
               tramites=[{"id_externo": "78", "fecha": "2025-01-01", "telefono": "3001110002"}])
    _autoriza(db, b, "si", ["llamada"])
    # Paso 1 hecho (el origen ya no está activo) y el proceso se cayó
    db.personas.update_one({"_id": b}, [{"$set": {"fusionada_en": a, "cedula_en_traspaso": "$cedula", "cedula": None,
                                                  "clave_tramites": None}}])
    assert bd.reparar_fusiones(db) == 1
    assert bd.reparar_fusiones(db) == 0  # repetir no hace nada
    p = db.personas.find_one({"_id": a})
    assert p["cedula"] == "90000604" and p["listas"] == ["Lista C"] and len(p["tramites"]) == 1
    assert [t["numero"] for t in p["telefonos"]] == ["3001110001", "3001110002"]
    assert p["consentimiento"] == "si" and db.autorizaciones.find_one({"persona_id": a})
    assert db.personas.find_one({"_id": b})["nombre"] == "FUSIONADA"
