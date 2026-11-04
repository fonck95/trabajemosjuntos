"""Cruce de varias bases con la cédula como identificador definitivo (2.3) y procedencia de los campos (1.5).

Solo personas inventadas."""
from datetime import date

from app import db as bd
from app import modelo
from app.pipeline import importar as imp
from app.pipeline import lectores
from ayudas_g1 import cedula, ficha_vieja, fila_planilla, importar, tramite
from conftest import CEDULAS, excel_cedulas, excel_planilla


def _ficha(db, **datos):
    d = bd.nueva_persona(db, {"nombre": "PERSONA INVENTADA", **datos}, "manual")
    db.personas.insert_one(d)
    return d["_id"]


def test_nombre_distinto_produce_un_conflicto_sin_mezcla(bases, tmp_path):
    db = bases()
    importar(db, tmp_path, cedulas=CEDULAS)
    eusebio = db.personas.find_one({"cedula": "90000003"})
    res = importar(db, tmp_path, planilla=[fila_planilla("90000003", "MARCO TULIO RENTERIA PALOMEQUE", "3101234511",
                                                         sexo="Hombre", edad=47)], nombre="2")
    assert res.conflictos_cedula == 1 and res.personas_nuevas == 0
    c = db.conflictos_cedula.find_one()
    assert (c["motivo"], c["cedula"], c["persona_id"], c["fuente"]) == ("nombre_distinto", "90000003", eusebio["_id"], "planilla")
    assert c["registro"]["nombre"] == "MARCO TULIO RENTERIA PALOMEQUE" and c["puntaje_nombre"] < 0.6
    despues = db.personas.find_one({"_id": eusebio["_id"]})
    assert "3101234511" not in [t["numero"] for t in despues["telefonos"]]
    assert despues["edad"] == eusebio["edad"] and "planilla" not in despues["fuentes"]
    assert db.personas.count_documents({"cedula": "90000003"}) == 1


def test_madre_e_hija_con_la_cedula_de_la_madre_y_el_mismo_telefono(bases, tmp_path):
    db = bases()
    madre = _ficha(db, nombre="ROSA MARIA INVENTADA PEREZ", cedula="90000920", telefono="3001110920")
    res = importar(db, tmp_path, cedulas=[cedula("90000920", "LUISA FERNANDA INVENTADA PEREZ", "3001110920", edad=19)])
    assert res.conflictos_cedula == 1 and res.cedulas_ya_existian == 0
    assert db.conflictos_cedula.find_one()["persona_id"] == madre
    assert db.personas.find_one({"_id": madre})["edad"] is None


def test_cedula_anterior(bases, tmp_path):
    db = bases()
    pid = _ficha(db, nombre="ANACLETO INVENTADO ANTERIOR", cedula="90000901", cedulas_anteriores=["90000900"])
    res = importar(db, tmp_path, cedulas=[cedula("90000900", "ANACLETO INVENTADO ANTERIOR", "3001110900")])
    assert res.personas_nuevas == 0 and res.conflictos_cedula == 1
    c = db.conflictos_cedula.find_one()
    assert (c["motivo"], c["persona_id"]) == ("cedula_anterior", pid)
    assert db.personas.find_one({"_id": pid})["cedula"] == "90000901"


def test_llave_ya_vinculada_no_compara_nombres(bases, tmp_path):
    db = bases()
    importar(db, tmp_path, cedulas=[cedula("90000910", "BALTAZAR INVENTADO LLAVE", listas="Lista A")])
    p = db.personas.find_one({"cedula": "90000910"})
    # El administrador corrigió el nombre y cambió la cédula (la anterior quedó en cedulas_anteriores)
    db.personas.update_one({"_id": p["_id"]}, {"$set": {"nombre": "JUAN DE DIOS OTRO NOMBRE", "cedula": "90000911",
                                                        "cedulas_anteriores": ["90000910"]}})
    res = importar(db, tmp_path, cedulas=[cedula("90000910", "BALTAZAR INVENTADO LLAVE", listas="Lista B")], nombre="2")
    assert res.conflictos_cedula == 0 and res.personas_nuevas == 0 and res.cedulas_ya_existian == 1
    p = db.personas.find_one({"_id": p["_id"]})
    assert p["cedula"] == "90000911" and p["listas"] == ["Lista A", "Lista B"]


def test_fila_sin_cedula_con_ficha_con_cedula_solo_con_evidencia(bases, tmp_path):
    db = bases()
    pid = _ficha(db, nombre="HERMOGENES INVENTADO ARRIETA", cedula="90000930", telefono="3001110930")
    # Solo el nombre: no se une sola, va a revisión
    res = importar(db, tmp_path, planilla=[fila_planilla(None, "HERMOGENES INVENTADO ARRIETA", "3101110931")])
    assert res.registros_unidos_auto == 0 and res.personas_nuevas == 1 and res.registros_en_revision == 1
    c = db.coincidencias.find_one({"candidato_id": pid})
    assert c["motivo"] == "nombre_telefono"
    # Con el mismo teléfono: se une sola
    res = importar(db, tmp_path, planilla=[fila_planilla(None, "HERMOGENES INVENTADO ARRIETA", "3001110930",
                                                         barrio="EL PRADO")], nombre="2")
    assert res.registros_unidos_auto == 1 and res.personas_nuevas == 0
    p = db.personas.find_one({"_id": pid})
    assert "planilla" in p["fuentes"] and p["cedula"] == "90000930"


def test_zapateiro_en_lote_las_dos_a_revision(bases, tmp_path):
    db = bases()
    for orden in (0, 1):
        db = bases()
        importar(db, tmp_path, tramites=[tramite(3001, "EUSTAQUIO BARTOLOME ZAPATEIRO QUINTERO", "3001112233")])
        filas = [fila_planilla("90000942", "EUSTAQUIO BARTOLOME ZAPATEIRO", "3001112233"),
                 fila_planilla("90000941", "EUSTAQUIO BARTOLOME ZAPATEIRO QUINTERO")]
        res = importar(db, tmp_path, planilla=filas[::-1] if orden else filas, nombre=f"z{orden}")
        assert res.cedulas_unidas_auto == 0 and res.cedulas_en_revision == 2 and res.personas_nuevas == 2
        ficha = db.personas.find_one({"tramites.id_externo": "3001"})
        assert ficha["cedula"] is None
        assert db.coincidencias.count_documents({"candidato_id": ficha["_id"], "estado": "pendiente",
                                                 "motivo": "cruce_cedula"}) == 2


def test_posible_digitacion(bases, tmp_path):
    db = bases()
    pid = _ficha(db, nombre="CRISANTO INVENTADO DIGITADO", cedula="90000931")
    res = importar(db, tmp_path, cedulas=[cedula("90000913", "CRISANTO INVENTADO DIGITADO")])
    assert res.personas_nuevas == 1 and res.conflictos_cedula == 1  # solo un aviso: nunca se une
    nueva = db.personas.find_one({"cedula": "90000913"})
    c = db.conflictos_cedula.find_one()
    assert (c["motivo"], c["persona_id"], c["cedula"], c["otra_persona"]) == ("posible_digitacion", nueva["_id"], "90000931", pid)
    assert imp.variantes_cedula("123") == ["023", "223", "323", "423", "523", "623", "723", "823", "923", "103", "113",
                                           "133", "143", "153", "163", "173", "183", "193", "120", "121", "122", "124",
                                           "125", "126", "127", "128", "129", "213", "132"]


def test_no_autorizo_solo_origen_minimo(bases, tmp_path):
    db = bases()
    pid = _ficha(db, nombre="CENOBIA INVENTADA NOAUTORIZA", cedula="90000950", consentimiento="no")
    bd.derivar(db, [pid])
    res = importar(db, tmp_path, cedulas=[cedula("90000950", "CENOBIA INVENTADA NOAUTORIZA", "3001110950",
                                                 listas="Lista Z", sexo="F", puesto="COLISEO BENITO ARIAS")])
    assert res.omitidas_sin_autorizacion == 1
    p = db.personas.find_one({"_id": pid})
    assert p["origen"] == [{"fuente": "cedulas", "clave": "90000950", "importacion_id": p["origen"][0]["importacion_id"],
                            "datos": {}}]
    assert p["telefonos"] == [] and p["listas"] == [] and p["sexo"] is None and p["votacion"] is None
    assert "cedulas" not in p["fuentes"]
    # Reimportar no duplica nada
    importar(db, tmp_path, cedulas=[cedula("90000950", "CENOBIA INVENTADA NOAUTORIZA", "3001110950")], nombre="2")
    assert len(db.personas.find_one({"_id": pid})["origen"]) == 1
    assert db.personas.count_documents({"nombre": "CENOBIA INVENTADA NOAUTORIZA"}) == 1


def test_sin_procedencia_cuenta_como_panel(bases, tmp_path):
    db = bases()
    db.personas.insert_one(ficha_vieja(9100, nombre="EDELMIRA INVENTADA PANEL", cedula="90000960", sexo="F", edad=50))
    res = importar(db, tmp_path, cedulas=[cedula("90000960", "EDELMIRA INVENTADA PANEL", sexo="M", edad=51)])
    p = db.personas.find_one({"_id": 9100})
    assert p["sexo"] == "F" and p["edad"] == 50
    alt = {a["campo"]: a for a in p["alternos"]}
    assert alt["sexo"]["valor"] == "M" and alt["sexo"]["fuente"] == "cedulas" and alt["edad"]["valor"] == 51
    assert res.alternos_agregados == 2
    # Reimportar lo mismo no repite alternos
    importar(db, tmp_path, cedulas=[cedula("90000960", "EDELMIRA INVENTADA PANEL", sexo="M", edad=51)], nombre="2")
    assert len(db.personas.find_one({"_id": 9100})["alternos"]) == 2


def test_reemplazo_condicional_y_el_valor_pisado_va_a_alternos(bases, tmp_path):
    db = bases()
    importar(db, tmp_path, cedulas=[cedula("90000970", "OBDULIO INVENTADO REEMPLAZO", sexo="F", edad=30),
                                    cedula("90000971", "TELESFORO INVENTADO CARRERA", sexo="F", edad=30)])
    a = db.personas.find_one({"cedula": "90000970"})
    assert a["procedencia"]["sexo"]["fuente"] == "cedulas"
    # La planilla (más confianza que la base con cédula) reemplaza, y el valor anterior va a alternos
    importar(db, tmp_path, planilla=[fila_planilla("90000970", "OBDULIO INVENTADO REEMPLAZO", sexo="Hombre",
                                                   edad=31, fecha=date(2026, 11, 2))], nombre="2")
    a = db.personas.find_one({"_id": a["_id"]})
    assert a["sexo"] == "M" and a["procedencia"]["sexo"]["fuente"] == "planilla" and a["edad"] == 31
    assert {(x["campo"], x["valor"], x["fuente"]) for x in a["alternos"]} >= {("sexo", "F", "cedulas"), ("edad", 30, "cedulas")}
    assert a["nac_base"]["edad"] == 31 and a["edad_ref"] == modelo.hoy_local().isoformat()
    # Mientras corre la importación, el panel cambia el sexo: la condición de la escritura no se cumple
    b = db.personas.find_one({"cedula": "90000971"})
    filas = list(lectores.leer_registros(excel_planilla(tmp_path / "p3.xlsx", [
        fila_planilla("90000971", "TELESFORO INVENTADO CARRERA", sexo="Hombre", edad=30)]), "planilla"))
    alm = imp._Almacen(db)
    db.personas.update_one({"_id": b["_id"]}, {"$set": {"sexo": "N", "procedencia.sexo": {"fuente": "panel"}}})
    imp._importar_registros(alm, "planilla", filas, 99, imp.Resumen())
    alm.guardar()
    b = db.personas.find_one({"_id": b["_id"]})
    assert b["sexo"] == "N" and b["procedencia"]["sexo"]["fuente"] == "panel"
    assert ("sexo", "M") in {(x["campo"], x["valor"]) for x in b["alternos"]}
    assert ("sexo", "F") not in {(x["campo"], x["valor"]) for x in b["alternos"]}


def test_los_conflictos_no_se_duplican_al_reimportar(bases, tmp_path):
    db = bases()
    importar(db, tmp_path, cedulas=CEDULAS)
    fila = [fila_planilla("90000003", "MARCO TULIO RENTERIA PALOMEQUE", "3101234511")]
    importar(db, tmp_path, planilla=fila, nombre="2")
    res = importar(db, tmp_path, planilla=fila, nombre="3")
    assert res.conflictos_cedula == 0 and db.conflictos_cedula.count_documents({}) == 1
    db.conflictos_cedula.update_one({}, {"$set": {"estado": "descartado"}})
    importar(db, tmp_path, planilla=fila, nombre="4")
    assert db.conflictos_cedula.count_documents({}) == 1  # uno descartado no vuelve
    assert db.conflictos_cedula.find_one()["estado"] == "descartado"


def test_cedula_puesta_en_el_panel_mientras_corre(bases, tmp_path):
    db = bases()
    importar(db, tmp_path, tramites=[tramite(4001, "DAMASO INVENTADO CONCURRENTE", "3001114001")])
    p = db.personas.find_one({"nombre": "DAMASO INVENTADO CONCURRENTE"})
    filas = list(lectores.leer_cedulas(excel_cedulas(tmp_path / "c.xlsx", [
        cedula("90000980", "DAMASO INVENTADO CONCURRENTE", "3001114001", listas="Lista Q")])))
    alm = imp._Almacen(db)
    db.personas.update_one({"_id": p["_id"]}, {"$set": {"cedula": "90000981"}})  # el panel le puso otra
    res = imp.Resumen()
    imp._importar_cedulas(alm, filas, 99, res)
    alm.guardar()
    alm.despues_de_guardar(99, "admin")
    p = db.personas.find_one({"_id": p["_id"]})
    assert p["cedula"] == "90000981" and p["listas"] == []  # la fila no escribió nada
    c = db.conflictos_cedula.find_one()
    assert (c["motivo"], c["persona_id"], c["cedula"]) == ("nombre_distinto", p["_id"], "90000980")
    assert db.auditoria.count_documents({"accion": "cruce_automatico"}) == 0
