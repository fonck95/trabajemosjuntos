"""Supresión ampliada (2.6): todas las cédulas de la persona quedan como huella, lo ligado se anonimiza o se borra y
los indicadores no cambian. Solo personas inventadas."""
import json
import re

from app import db as bd
from ayudas_g1 import cedula, fila_planilla, importar


def test_cedula_anterior_y_la_de_la_planilla_no_se_vuelven_a_crear(bases, tmp_path):
    db = bases()
    importar(db, tmp_path, planilla=[fila_planilla("90000701", "PERSONA INVENTADA SUPRIMIR", "3101110701")])
    p = db.personas.find_one({"cedula": "90000701"})
    # El administrador corrigió la cédula: la de la planilla quedó como anterior
    db.personas.update_one({"_id": p["_id"]}, {"$set": {"cedula": "90000702", "cedulas_anteriores": ["90000701"]}})
    bd.suprimir(db, p["_id"], "admin")
    res = importar(db, tmp_path, cedulas=[cedula("90000701", "OTRO NOMBRE INVENTADO", "3009990001"),
                                          cedula("90000702", "OTRO NOMBRE MAS INVENTADO", "3009990002")],
                   planilla=[fila_planilla("90000701", "PERSONA INVENTADA SUPRIMIR", "3101110701")], nombre="2")
    assert res.personas_nuevas == 0 and res.suprimidas_omitidas == 3
    assert db.personas.count_documents({**bd.ACTIVA}) == 0
    # Tampoco por la otra cédula mal repetida en la planilla
    res = importar(db, tmp_path, planilla=[fila_planilla("90000702", "NOMBRE INVENTADO NUEVO", repetida="90000720")],
                   nombre="3")
    assert res.suprimidas_omitidas == 1 and res.personas_nuevas == 0


def test_lo_ligado_se_anonimiza_y_los_indicadores_no_cambian(bases, tmp_path):
    db = bases()
    importar(db, tmp_path, cedulas=[cedula("90000711", "PERSONA INVENTADA LIGADA", "3001110711"),
                                    cedula("90000712", "OTRA PERSONA INVENTADA", "3001110712")])
    p = db.personas.find_one({"cedula": "90000711"})
    otra = db.personas.find_one({"cedula": "90000712"})
    db.acercamientos.insert_many([
        {"_id": 1, "persona_id": p["_id"], "uid": 7, "canal": "llamada", "resultado": "contesto", "efectivo": True,
         "ts": "2026-11-01T15:00:00+00:00", "telefono": "3001110711", "nota": "Nota inventada",
         "datos_dictados": ["cedula"]},
        {"_id": 2, "persona_id": otra["_id"], "uid": 7, "canal": "llamada", "resultado": "no_contesto", "efectivo": False,
         "ts": "2026-11-01T16:00:00+00:00", "telefono": "3001110712", "nota": None, "datos_dictados": []}])
    db.autorizaciones.insert_one(bd.autorizacion_doc(db, p["_id"], "si", "escrito", evidencia="Planilla inventada 3",
                                                     evidencia_fila={"nombre": "PERSONA INVENTADA LIGADA"}))
    db.solicitudes.insert_one({"_id": 1, "persona_id": p["_id"], "tipo": "supresion", "descripcion": "Texto inventado",
                               "respuesta": "Respuesta inventada", "estado": "resuelta"})
    db.conflictos_cedula.insert_many([
        {"_id": 1, "clave": "a", "persona_id": p["_id"], "cedula": "90000799"},
        {"_id": 2, "clave": "b", "persona_id": otra["_id"], "cedula": "90000711"},  # la cédula suprimida en otra ficha
        {"_id": 3, "clave": "c", "persona_id": otra["_id"], "cedula": "90000798"}])
    db.idempotencia.insert_many([{"_id": "7:a", "persona_id": p["_id"], "ts": bd._instante()},
                                 {"_id": "7:b", "persona_id": otra["_id"], "ts": bd._instante()}])
    antes = [(a["uid"], a["canal"], a["resultado"], a["efectivo"], a["ts"]) for a in db.acercamientos.find().sort("_id", 1)]
    bd.suprimir(db, p["_id"], "admin")
    despues = [(a["uid"], a["canal"], a["resultado"], a["efectivo"], a["ts"]) for a in db.acercamientos.find().sort("_id", 1)]
    assert antes == despues  # los indicadores por usuario se calculan igual
    a1 = db.acercamientos.find_one({"_id": 1})
    assert (a1["persona_id"], a1["telefono"], a1["nota"], a1["datos_dictados"], a1["suprimido"]) == (None, None, None, [], True)
    assert db.acercamientos.find_one({"_id": 2})["persona_id"] == otra["_id"]
    au = db.autorizaciones.find_one({})
    assert (au["persona_id"], au["evidencia"], au["evidencia_fila"], au["suprimido"]) == (None, None, None, True)
    s = db.solicitudes.find_one({"_id": 1})
    assert s["descripcion"] is None and s["respuesta"] is None and s["tipo"] == "supresion"  # queda como constancia
    assert sorted(c["_id"] for c in db.conflictos_cedula.find()) == [3]
    assert [i["_id"] for i in db.idempotencia.find()] == ["7:b"]
    texto = json.dumps(list(db.auditoria.find({}, {"_id": 0})), default=str)
    for dato in ("90000711", "3001110711", "PERSONA INVENTADA LIGADA"):
        assert dato not in texto
    assert all(set(d) == {"_id", "creado_en"} and re.fullmatch(r"[0-9a-f]{64}", d["_id"]) for d in db.suprimidos.find())


def test_auditoria_enmascara_cedulas_y_sensibles(bases):
    db = bases()
    sensible = db.etiquetas.find_one({"nombre": "Discapacidad"})
    normal = db.etiquetas.find_one({"nombre": "Vivienda"})
    db.campos.insert_one({"_id": 1, "clave": "condicion", "etiqueta": "Condición", "tipo": "texto", "sensible": True})
    bd.auditar(db, "admin", "editar", "persona", 1, {
        "cedula": {"antes": "90000721", "despues": "90000722"}, "lider": {"antes": False, "despues": True},
        "sensibles.etnia": "Ninguno", "etiquetas": [sensible["_id"], normal["_id"]],
        "extra": {"condicion": "dato sensible inventado", "cultivo": "Yuca"}})
    det = json.loads(db.auditoria.find_one({"accion": "editar"})["detalle"])
    assert det["cedula"] == {"antes": "···721", "despues": "···722"} and det["lider"] == "(oculto)"
    assert det["sensibles.etnia"] == "(oculto)" and det["etiquetas"] == ["(oculto)", normal["_id"]]
    assert det["extra"] == {"condicion": "(oculto)", "cultivo": "Yuca"}
