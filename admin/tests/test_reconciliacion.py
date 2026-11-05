"""Reconciliación en cada arranque (1.12): lo que el código viejo escribe directamente después de migrar (durante un
despliegue o una vuelta atrás) se corrige en el próximo `inicializar`. Solo fichas inventadas."""
from app import db as bd
from app import modelo
from ayudas_g1 import importar, tramite


def _preparar(db, tmp_path):
    importar(db, tmp_path, tramites=[tramite(1, "TEODORA INVENTADA RECONCILIA", "3001110001"),
                                     tramite(2, "SATURNINO INVENTADO RECONCILIA", "3001110002", direccion="CALLE 50 # 45-12")])
    a = db.personas.find_one({"nombre": "TEODORA INVENTADA RECONCILIA"})
    b = db.personas.find_one({"nombre": "SATURNINO INVENTADO RECONCILIA"})
    return a["_id"], b["_id"]


def test_lo_escrito_por_el_codigo_viejo_se_corrige_al_arrancar(bases, tmp_path):
    db = bases()
    a, b = _preparar(db, tmp_path)
    p = db.personas
    # El código viejo escribe directamente los campos heredados
    p.update_one({"_id": a}, {"$set": {"telefono": "3209998877", "telefono2": "3001110001", "puesto_votacion": "COLISEO BENITO ARIAS",
                                       "mesa": "Mesa # 2", "consentimiento": "si", "lat": 7.0062, "lon": -73.9112,
                                       "edad": 33}})
    p.update_one({"_id": b}, {"$set": {"consentimiento": "no", "lat": None}})
    bd.inicializar(db)  # el próximo arranque
    x = p.find_one({"_id": a})
    assert [t["numero"] for t in x["telefonos"]][:2] == ["3209998877", "3001110001"]
    assert x["telefono"] == "3209998877" and x["telefono2"] == "3001110001"
    assert x["telefonos"][0]["fuentes"] == ["panel"] and x["telefonos"][0]["tipo"] == "celular"
    coliseo = db.puestos.find_one({"codigo": "00-02"})
    assert x["votacion"]["puesto_id"] == coliseo["_id"] and x["votacion"]["fuente"] == "panel"
    assert x["votacion"]["estado"] == "por_confirmar" and x["mesa"] == "Mesa # 2"
    assert x["puesto_votacion"] == coliseo["nombre"]
    assert x["consentimiento"] == "si" and x["autorizacion_ultima"]["estado"] == "si"
    ev = list(db.autorizaciones.find({"persona_id": a}))
    assert len(ev) == 1 and ev[0]["medio"] == "migrado" and ev[0]["canales_implicitos"] is True
    assert x["punto"] == modelo.punto(7.0062, -73.9112)
    assert x["nac_base"] == {"edad": 33, "fecha": None} and x["edad_ref"] == modelo.hoy_local().isoformat()
    assert x["nac_aprox"] == modelo.calcular_nac({"edad": 33, "edad_ref": x["edad_ref"]})["nac_aprox"]
    y = p.find_one({"_id": b})
    assert y["consentimiento"] == "no" and y["autorizacion_ultima"]["estado"] == "no" and y["punto"] is None
    # Un segundo arranque no cambia nada
    antes = list(p.find().sort("_id", 1)), list(db.autorizaciones.find().sort("_id", 1))
    bd.inicializar(db)
    assert (list(p.find().sort("_id", 1)), list(db.autorizaciones.find().sort("_id", 1))) == antes


def test_puesto_cambiado_deja_el_anterior_en_alternos(bases, tmp_path):
    db = bases()
    a, _ = _preparar(db, tmp_path)
    db.personas.update_one({"_id": a}, [{"$set": {"puesto_votacion": "I.E.R. SAN MIGUEL DEL TIGRE", "mesa": "Mesa # 4"}}])
    bd.inicializar(db)
    db.personas.update_one({"_id": a}, {"$set": {"mesa": "Mesa # 5"}})
    bd.inicializar(db)
    x = db.personas.find_one({"_id": a})
    assert x["votacion"]["mesa"] == 5 and x["mesa"] == "Mesa # 5"
    assert any(al["campo"] == "votacion" and al["valor"]["mesa"] == 4 for al in x["alternos"])


def test_ficha_suprimida_con_acercamientos_se_limpia(bases, tmp_path):
    db = bases()
    a, b = _preparar(db, tmp_path)
    db.acercamientos.insert_one({"_id": 1, "persona_id": a, "uid": 7, "canal": "llamada", "resultado": "contesto",
                                 "efectivo": True, "ts": "2026-11-01T15:00:00+00:00", "telefono": "3001110001",
                                 "nota": "Nota inventada", "datos_dictados": ["cedula"]})
    db.autorizaciones.insert_one(bd.autorizacion_doc(db, a, "si", "escrito", evidencia="Planilla inventada"))
    db.conflictos_cedula.insert_one({"_id": 1, "clave": "x", "persona_id": a, "cedula": "90000777"})
    db.idempotencia.insert_one({"_id": "7:clave", "persona_id": a, "ts": bd._instante()})
    db.coincidencias.insert_one({"_id": 1, "persona_id": a, "candidato_id": b, "estado": "pendiente", "puntaje": 0.8})
    # El código viejo suprime sin limpiar lo ligado
    db.personas.replace_one({"_id": a}, {**bd.persona_vacia(), "_id": a, "nombre": "SUPRIMIDO", "eliminado": True})
    bd.inicializar(db)
    ac = db.acercamientos.find_one({"_id": 1})
    assert ac["persona_id"] is None and ac["telefono"] is None and ac["nota"] is None and ac["suprimido"] is True
    assert (ac["uid"], ac["canal"], ac["resultado"], ac["efectivo"]) == (7, "llamada", "contesto", True)
    au = db.autorizaciones.find_one({})
    assert au["persona_id"] is None and au["evidencia"] is None
    assert db.conflictos_cedula.count_documents({}) == 0 and db.idempotencia.count_documents({}) == 0
    assert db.coincidencias.count_documents({}) == 0


def test_union_cortada_a_mitad_se_repara(bases, tmp_path):
    db = bases()
    a, b = _preparar(db, tmp_path)
    db.personas.update_one({"_id": b}, {"$set": {"cedula": "90000555"}})
    # Paso 1 de la unión hecho y después se cayó el proceso
    db.personas.update_one({"_id": b}, [{"$set": {"fusionada_en": a, "cedula_en_traspaso": "$cedula", "cedula": None,
                                                  "clave_tramites": None}}])
    bd.inicializar(db)
    x, o = db.personas.find_one({"_id": a}), db.personas.find_one({"_id": b})
    assert x["cedula"] == "90000555" and {"3001110001", "3001110002"} <= {t["numero"] for t in x["telefonos"]}
    assert o["nombre"] == "FUSIONADA" and "cedula_en_traspaso" not in o and o["telefonos"] == []
    assert len(x["tramites"]) == 2
