"""Teléfonos de todas las fuentes (1.2, 2.5): ningún flujo reemplaza un número; todos se suman a `telefonos`.

Casos:
A. Trámites: todos los números del grupo (no solo los dos más frecuentes), del más frecuente al menos frecuente.
B. Base con cédula: todos los números de la fila; uno ya presente solo gana la fuente.
C. Planilla: celular y otro teléfono (varios en la misma celda), con la fecha de la fila y quien la llenó.
D. Un número retirado, equivocado o que ya no usa no se reactiva al reimportar (solo gana fuentes y última vez).
E. Un `telefono` que el código viejo escribió directamente no se pierde cuando una importación agrega números.
F. Al unir dos fichas se unen las listas; en un número repetido gana el estado más reciente.
Además: una ficha sin `telefonos` (escrita por el código viejo) con A y B a la que se le agrega C queda [A, B, C].
Solo datos inventados."""
from app import db as bd
from app import modelo
from ayudas_g1 import cedula, ficha_vieja, fila_planilla, importar, tramite


def _numeros(p):
    return [t["numero"] for t in p["telefonos"]]


def test_a_tramites_todos_los_numeros_por_frecuencia(bases, tmp_path):
    db = bases()
    nombre = "FILOMENA INVENTADA TELEFONOS"
    filas = [tramite(1, nombre, "3001110001; 3001110002", ficha="0589300009001", fecha="2/6/2025"),
             tramite(2, nombre, "3001110002 / 3001110003", ficha="0589300009001", fecha="3/6/2025"),
             tramite(3, nombre, "3001110002", ficha="0589300009001", fecha="4/6/2025")]
    res = importar(db, tmp_path, tramites=filas)
    p = db.personas.find_one({"nombre": nombre})
    assert _numeros(p) == ["3001110002", "3001110001", "3001110003"]
    assert res.telefonos_agregados == 3
    t = {x["numero"]: x for x in p["telefonos"]}
    assert t["3001110002"]["fuentes"] == ["tramites"]
    assert (t["3001110002"]["primera_vez"], t["3001110002"]["ultima_vez"]) == ("2025-02-06", "2025-04-06")
    assert (p["telefono"], p["telefono2"]) == ("3001110002", "3001110001")


def test_b_base_con_cedula_todos_los_de_la_fila(bases, tmp_path):
    db = bases()
    importar(db, tmp_path, tramites=[tramite(1, "GUMERSINDA INVENTADA CEDULA", "3001110001")])
    importar(db, tmp_path, cedulas=[cedula("90000801", "GUMERSINDA INVENTADA CEDULA", "3001110001; 3001110004 - 6047001234")])
    p = db.personas.find_one({"cedula": "90000801"})
    assert _numeros(p) == ["3001110001", "3001110004", "6047001234"]
    t = {x["numero"]: x for x in p["telefonos"]}
    assert t["3001110001"]["fuentes"] == ["tramites", "cedulas"] and t["3001110004"]["fuentes"] == ["cedulas"]
    assert t["6047001234"]["tipo"] == "fijo" and t["3001110004"]["tipo"] == "celular"


def test_c_planilla_varios_numeros(bases, tmp_path):
    from conftest import crear_usuario
    db = bases()
    u = crear_usuario(db, "planillero", usuario="ana.campo")
    from datetime import date
    importar(db, tmp_path, planilla=[fila_planilla("90000802", "HERMINIA INVENTADA PLANILLA", "3101110001",
                                                   "3101110002 / 6047001234", planillero="ana.campo",
                                                   fecha=date(2026, 11, 2))])
    p = db.personas.find_one({"cedula": "90000802"})
    assert _numeros(p) == ["3101110001", "3101110002", "6047001234"]
    assert all(t["fuentes"] == ["planilla"] and t["agregado_por"] == u["_id"] and t["primera_vez"] == "2026-11-02"
               for t in p["telefonos"])


def test_d_un_numero_marcado_no_se_reactiva(bases, tmp_path):
    db = bases()
    filas = [tramite(1, "PRUDENCIA INVENTADA MARCADA", "3001110001; 3001110002")]
    importar(db, tmp_path, tramites=filas)
    p = db.personas.find_one({"nombre": "PRUDENCIA INVENTADA MARCADA"})
    for num, estado in (("3001110001", "retirado"), ("3001110002", "equivocado")):
        db.personas.update_one({"_id": p["_id"]}, modelo.expr_estado_telefono(num, {"estado": estado, "estado_por": 0}))
    importar(db, tmp_path, tramites=filas + [tramite(2, "PRUDENCIA INVENTADA MARCADA", "3001110001", fecha="5/6/2026")],
             cedulas=[cedula("90000803", "PRUDENCIA INVENTADA MARCADA", "3001110002")], nombre="2")
    p = db.personas.find_one({"_id": p["_id"]})
    t = {x["numero"]: x for x in p["telefonos"]}
    assert t["3001110001"]["estado"] == "retirado" and t["3001110002"]["estado"] == "equivocado"
    assert t["3001110002"]["fuentes"] == ["tramites", "cedulas"] and t["3001110001"]["ultima_vez"] == "2026-05-06"
    assert p["telefono"] is None and p["telefono2"] is None


def test_e_telefono_del_codigo_viejo_no_se_pierde(bases, tmp_path):
    db = bases()
    importar(db, tmp_path, tramites=[tramite(1, "RIGOBERTA INVENTADA VIEJA", "3001110001")])
    p = db.personas.find_one({"nombre": "RIGOBERTA INVENTADA VIEJA"})
    db.personas.update_one({"_id": p["_id"]}, {"$set": {"telefono": "3209990000"}})  # PATCH del código viejo
    importar(db, tmp_path, tramites=[tramite(1, "RIGOBERTA INVENTADA VIEJA", "3001110001"),
                                     tramite(2, "RIGOBERTA INVENTADA VIEJA", "3001110005", ficha="0589300000001",
                                             fecha="3/6/2025")], nombre="2")
    p = db.personas.find_one({"_id": p["_id"]})
    assert _numeros(p) == ["3209990000", "3001110001", "3001110005"]
    assert p["telefono"] == "3209990000" and p["telefono2"] == "3001110001"


def test_f_unir_fichas_une_las_listas(bases):
    db = bases()
    a = bd.nueva_persona(db, {"nombre": "Teodulo Inventado Union", "telefonos": [
        modelo.telefono_nuevo("3001110001", "panel"),
        modelo.telefono_nuevo("3001110002", "panel", estado="confirmado", estado_en="2026-10-01T15:00:00+00:00")]}, "manual")
    b = bd.nueva_persona(db, {"nombre": "Teodulo Inventado Union", "telefonos": [
        modelo.telefono_nuevo("3001110002", "tramites", estado="equivocado", estado_en="2026-11-01T15:00:00+00:00"),
        modelo.telefono_nuevo("3001110003", "tramites")]}, "tramites")
    db.personas.insert_many([a, b])
    bd.fusionar(db, a["_id"], b["_id"], "admin")
    p = db.personas.find_one({"_id": a["_id"]})
    assert _numeros(p) == ["3001110001", "3001110002", "3001110003"]
    t = {x["numero"]: x for x in p["telefonos"]}
    assert t["3001110002"]["estado"] == "equivocado" and t["3001110002"]["fuentes"] == ["panel", "tramites"]
    assert (p["telefono"], p["telefono2"]) == ("3001110001", "3001110003")


def test_ficha_sin_telefonos_queda_a_b_c(bases, tmp_path):
    db = bases()
    db.personas.insert_one(ficha_vieja(9001, nombre="CELMIRA INVENTADA LEGADO", cedula="90000804",
                                       telefono="3001110001", telefono2="3001110002"))
    importar(db, tmp_path, cedulas=[cedula("90000804", "CELMIRA INVENTADA LEGADO", "3001110003")])
    p = db.personas.find_one({"_id": 9001})
    assert _numeros(p) == ["3001110001", "3001110002", "3001110003"]
    assert (p["telefono"], p["telefono2"]) == ("3001110001", "3001110002")
    assert p["telefonos"][2]["fuentes"] == ["cedulas"]
