"""El importador para filas sueltas (app/pipeline/importar.py): `simular_registros` (la vista previa fiel, sin escribir)
y `importar_registros` (la carga de una foto como planilla de campo, con su turno, su registro y autorizaciones
siempre «declaradas en planilla»), y `lectores.registro_planilla`, que comparten el Excel y la foto: la misma fila da
el mismo `Registro`. Solo personas inventadas."""
from datetime import date

import pytest

from app import db as bd
from app import planillas as pl
from app.pipeline import importar as imp
from app.pipeline import lectores
from conftest import PLANILLA, crear_usuario, excel_planilla, insertar_personas


def _valores_de_foto(t: tuple) -> dict:
    """Una fila de la planilla de conftest como la transcribiría el lector (todo texto, fechas DD/MM/AAAA)."""
    claves = ["cedula", "cedula_repetida", "tipo_documento", "nombre", "celular", "otro_telefono", "sexo",
              "fecha_nacimiento", "edad", "direccion", "barrio", "puesto", "mesa", "autorizacion", "medio", "canales",
              "mayor_18", "planillero", "fecha", "observaciones"]
    out = {}
    for k, v in zip(claves, t):
        if v is None:
            continue
        out[k] = v.strftime("%d/%m/%Y") if isinstance(v, date) else str(v)
    return out


def test_la_misma_fila_da_el_mismo_registro_en_excel_y_en_foto(tmp_path):
    excel = list(lectores.leer_registros(excel_planilla(tmp_path / "p.xlsx", PLANILLA), "planilla"))
    assert len(excel) == len(PLANILLA)
    for t, r in zip(PLANILLA, excel):
        foto = pl.registro_de_fila({"n": r.fila, "valores": _valores_de_foto(t)})
        a, b = r.dict(), foto.dict()
        datos_foto = dict(b.pop("datos"))
        assert datos_foto.pop("captura") == "foto"
        assert a.pop("datos") == datos_foto, t[3]
        assert a == b, t[3]
    # La clave de una fila sin cédula no depende del número de fila: la misma fila en otra foto es la misma
    sin = pl.registro_de_fila({"n": 9, "valores": _valores_de_foto(PLANILLA[2])})
    assert sin.clave_fila == excel[2].clave_fila and len(sin.clave_fila) == 40


def test_registro_de_fila_encabezado_folio_y_autorizacion_dudosa():
    f = {"n": 3, "valores": {"nombre": "ANA INVENTADA", "cedula": "90000301", "autorizacion": "si", "medio": "escrito",
                             "canales": "llamada"}, "dudosos": ["autorizacion"]}
    r = pl.registro_de_fila(f, {"planillero": "ana.campo", "fecha": "02/11/2026"}, folio="Carpeta 3, hoja 12")
    assert r.autorizacion is None and r.canales == [] and r.datos["autorizacion_dudosa"] is True
    assert "autorizacion" not in r.datos and r.planillero == "ana.campo" and r.fecha == "2026-11-02"
    assert r.datos["folio"] == "Carpeta 3, hoja 12" and r.datos["captura"] == "foto" and r.fila == 3
    assert pl.registro_de_fila({"n": 1, "valores": {"cedula": "90000302"}}) is None  # sin nombre
    ilegible = pl.registro_de_fila({"n": 1, "valores": {"nombre": "LUIS INVENTADO", "autorizacion": "si"},
                                    "ilegibles": ["autorizacion"]})
    assert ilegible.autorizacion is None


def test_solo_declaradas_no_toca_los_registros_de_quien_llama():
    r = pl.registro_de_fila({"n": 1, "valores": {"nombre": "ANA INVENTADA", "autorizacion": "si",
                                                 "medio": "verbal_presencial"}})
    assert r.autorizacion_medio == "verbal_presencial"
    (d,) = imp.solo_declaradas([r])
    assert d.autorizacion_medio is None and d.datos["medio_leido"] == "verbal_presencial"
    assert "autorizacion_medio" not in d.datos
    assert r.autorizacion_medio == "verbal_presencial" and "medio_leido" not in r.datos


def _escenario(db):
    """Personas inventadas en la base, una por estado de la vista previa, y las filas de una foto que les tocan."""
    ids = insertar_personas(db, [
        {"nombre": "MARIA INVENTADA SIEMPRE", "cedula": "90001001", "consentimiento": "si", "telefono": "3109990001"},
        {"nombre": "PEDRO INVENTADO NEGADO", "cedula": "90001002", "consentimiento": "no"},
        {"nombre": "LUCIA INVENTADA PENDIENTE", "cedula": "90001003", "consentimiento": "pendiente"},
        {"nombre": "RAMON INVENTADO IGUAL", "cedula": "90001004", "telefono": "3109990004",
         "consentimiento": "pendiente"},
        {"nombre": "ELVIRA INVENTADA CONFLICTO", "cedula": "90001005"},
        {"nombre": "SUSANA INVENTADA SUPRIMIDA", "cedula": "90001006", "telefono": "3109990006"},
        {"nombre": "OTILIA INVENTADA ELECCION", "cedula": "90001007",
         "votacion": {"eleccion": "2022-congreso", "puesto_texto": "ESCUELA VIEJA", "mesa": 3, "estado": "verificado",
                      "fuente": "panel"}},
    ])
    bd.suprimir(db, ids[5], "admin")
    filas = [
        {"n": 1, "valores": {"cedula": "90002001", "nombre": "NUEVA INVENTADA UNO", "celular": "3108880001",
                             "autorizacion": "si", "medio": "escrito", "canales": "llamada, whatsapp",
                             "mayor_18": "si", "fecha": "02/11/2026"}},
        {"n": 2, "valores": {"cedula": "90002002", "nombre": "NUEVO INVENTADO NOAUTORIZA", "autorizacion": "no"}},
        {"n": 3, "valores": {"cedula": "90001001", "nombre": "MARIA INVENTADA SIEMPRE", "autorizacion": "no"}},
        {"n": 4, "valores": {"cedula": "90001002", "nombre": "PEDRO INVENTADO NEGADO", "celular": "3108880004",
                             "autorizacion": "si"}},
        {"n": 5, "valores": {"cedula": "90001003", "nombre": "LUCIA INVENTADA PENDIENTE", "celular": "3108880005",
                             "sexo": "F"}},
        {"n": 6, "valores": {"cedula": "90001004", "nombre": "RAMON INVENTADO IGUAL", "celular": "3109990004"}},
        {"n": 7, "valores": {"cedula": "90001005", "nombre": "TOTALMENTE DIFERENTE APELLIDOS"}},
        {"n": 8, "valores": {"cedula": "90001006", "nombre": "SUSANA INVENTADA SUPRIMIDA"}},
        {"n": 9, "valores": {"cedula": "90001007", "nombre": "OTILIA INVENTADA ELECCION",
                             "puesto": "CABECERA MUNICIPAL", "mesa": "2"}},
        {"n": 10, "valores": {"cedula": "90002003", "cedula_repetida": "90002030",
                              "nombre": "RUFINO INVENTADO DIGITO"}},
    ]
    return ids, [pl.registro_de_fila(f) for f in filas]


ESPERADOS = {1: "nueva", 2: "nueva_sin_autorizacion", 3: "revocaria", 4: "no_autorizo", 5: "completaria", 6: "igual",
             7: "conflicto_cedula", 8: "no_se_carga", 9: "otra_eleccion", 10: "revision"}


def _conteos(db) -> dict:
    return {c: db[c].count_documents({}) for c in ("personas", "autorizaciones", "suprimidos", "conflictos_cedula",
                                                    "coincidencias", "importaciones", "auditoria")} | {
        "contador": (db.contadores.find_one({"_id": "personas"}) or {}).get("n")}


def test_la_vista_previa_dice_que_pasaria_con_cada_fila_sin_escribir(bases):
    db = bases()
    ids, registros = _escenario(db)
    antes = _conteos(db)
    filas = imp.simular_registros(db, registros)
    assert _conteos(db) == antes  # nada escrito: ni fichas, ni huellas, ni conflictos, ni el contador
    assert {n: f["estado"] for n, f in filas.items()} == ESPERADOS
    assert filas[1]["persona_id"] is None and "telefono" in filas[1]["llenaria"] and "cedula" in filas[1]["llenaria"]
    assert filas[3]["persona_id"] == ids[0] and filas[4]["persona_id"] == ids[1]
    assert filas[5]["persona_id"] == ids[2] and set(filas[5]["llenaria"]) >= {"telefono", "sexo"}
    assert filas[6] == {"persona_id": ids[3], "estado": "igual", "motivo": None, "llenaria": [], "distintos": []}
    assert filas[7]["persona_id"] is None and filas[7]["motivo"] == "nombre_distinto"
    assert filas[8] == {"persona_id": None, "estado": "no_se_carga", "motivo": None, "llenaria": [], "distintos": []}
    assert filas[9]["motivo"] == "puesto_de_otra_eleccion" and filas[9]["persona_id"] == ids[6]
    assert filas[10]["motivo"] == "posible_digitacion" and filas[10]["persona_id"] is None
    # Los «no» no llevan campos
    assert all(not filas[n]["llenaria"] and not filas[n]["distintos"] for n in (2, 3, 4))


def test_distintos_lleva_el_valor_de_la_base_y_el_de_la_planilla(bases):
    db = bases()
    (pid,) = insertar_personas(db, [{"nombre": "TERESA INVENTADA DIRECCION", "cedula": "90003001",
                                     "direccion": "CALLE 10 # 1-01"}])
    db.personas.update_one({"_id": pid}, {"$set": {"procedencia.direccion": {"fuente": "panel"}}})
    r = pl.registro_de_fila({"n": 1, "valores": {"cedula": "90003001", "nombre": "TERESA INVENTADA DIRECCION",
                                                 "direccion": "CALLE 99 # 9-99"}})
    f = imp.simular_registros(db, [r])[1]
    assert f["estado"] == "completaria"
    assert {"campo": "direccion", "base": "CALLE 10 # 1-01", "planilla": "CALLE 99 # 9-99", "queda": "base"} \
        in f["distintos"]


def test_cargar_crea_y_completa_con_autorizaciones_declaradas(bases):
    db = bases()
    ids, registros = _escenario(db)
    ana = crear_usuario(db, "planillero", usuario="ana.campo")
    sha = "ab" * 32
    res, filas = imp.importar_registros(db, registros, capturado_por=ana["_id"], archivo=pl.ARCHIVO, sha=sha,
                                        fotos_sha256=[sha])
    estados = {n: f["estado"] for n, f in filas.items()}
    assert estados == {**ESPERADOS, 3: "revocada", 5: "completada", 9: "completada"}
    nueva = db.personas.find_one({"cedula": "90002001"})
    assert filas[1]["persona_id"] == nueva["_id"]
    # El «sí» leído con medio «Escrito» queda declarado en planilla: no habilita el contacto
    assert (nueva["consentimiento"], nueva["consentimiento_medio"], nueva["contacto_habilitado"]) == \
        ("si", "declarado_planilla", False)
    ev = db.autorizaciones.find_one({"persona_id": nueva["_id"]})
    assert ev["medio"] == "declarado_planilla" and ev["evidencia_fila"]["medio_leido"] == "escrito"
    assert ev["evidencia"] == "Foto de planilla física, fila 1" and ev["evidencia_sha256"] == sha
    assert ev["capturado_por"] == ana["_id"]
    assert res.autorizaciones_por_confirmar == 1
    assert nueva["creado_por"]["capturado_por"] == ana["_id"]
    assert nueva["origen"][0]["datos"]["captura"] == "foto"
    # «No autoriza»: nueva con lo mínimo; la que decía «sí» queda en «no»
    no = db.personas.find_one({"cedula": "90002002"})
    assert no["consentimiento"] == "no" and no["telefonos"] == []
    assert db.personas.find_one({"_id": ids[0]})["consentimiento"] == "no"
    assert db.personas.find_one({"_id": ids[2]})["telefono"] == "3108880005"
    # Nada de la persona suprimida: no se creó otra vez
    assert db.personas.count_documents({"cedula": "90001006"}) == 0
    imp_doc = db.importaciones.find_one()
    assert imp_doc["fotos_sha256"] == [sha] and imp_doc["evidencia_sha256"] == {pl.ARCHIVO: sha}
    assert imp_doc["tipo"] == "planilla" and imp_doc["archivo"] == pl.ARCHIVO and imp_doc["capturado_por"] == ana["_id"]
    assert ev["importacion_id"] == imp_doc["_id"]
    assert db.auditoria.find_one({"accion": "importar", "entidad_id": imp_doc["_id"]}) is not None
    assert db.conflictos_cedula.count_documents({"motivo": "nombre_distinto"}) == 1
    # Volver a cargar lo mismo no duplica fichas ni autorizaciones
    personas, autorizaciones = db.personas.count_documents({}), db.autorizaciones.count_documents({})
    imp.importar_registros(db, registros, archivo=pl.ARCHIVO, sha=sha, fotos_sha256=[sha])
    assert db.personas.count_documents({}) == personas and db.autorizaciones.count_documents({}) == autorizaciones


def test_el_folio_queda_en_la_importacion_y_en_la_fila(bases):
    db = bases()
    r = pl.registro_de_fila({"n": 1, "valores": {"cedula": "90004001", "nombre": "FOLIO INVENTADO",
                                                 "autorizacion": "si"}}, folio="Carpeta 3, hoja 12")
    _, filas = imp.importar_registros(db, [r], archivo=pl.ARCHIVO, sha=None, importacion_id=777)
    assert db.importaciones.find_one({"_id": 777})["folio"] == "Carpeta 3, hoja 12"
    p = db.personas.find_one({"_id": filas[1]["persona_id"]})
    assert p["origen"][0]["datos"]["folio"] == "Carpeta 3, hoja 12"
    assert db.autorizaciones.find_one({"persona_id": p["_id"]})["evidencia_fila"]["folio"] == "Carpeta 3, hoja 12"


def test_una_importacion_a_la_vez(bases):
    db = bases()
    assert bd.tomar_turno(db, "importando", "otro-dueño", 15)
    r = pl.registro_de_fila({"n": 1, "valores": {"nombre": "TURNO INVENTADO"}})
    with pytest.raises(imp.ImportacionEnCurso) as e:
        imp.importar_registros(db, [r], archivo=pl.ARCHIVO, sha=None)
    assert e.value.status_code == 409 and e.value.detail["codigo"] == "importando"
    assert db.personas.count_documents({}) == 0
    bd.soltar_turno(db, "importando", "otro-dueño")
    _, filas = imp.importar_registros(db, [r], archivo=pl.ARCHIVO, sha=None)
    assert filas[1]["estado"] == "nueva"
    # Soltó el turno al terminar
    assert bd.tomar_turno(db, "importando", "otro-más", 15)


def test_el_excel_sigue_igual(bases, tmp_path):
    """`_importar` (Excel) no cambió: el medio «Escrito» de la planilla en Excel sí habilita el contacto, como antes."""
    from ayudas_g1 import fila_planilla, importar
    db = bases()
    res = importar(db, tmp_path, planilla=[fila_planilla("90005001", "EXCEL INVENTADO ESCRITO", "3101110201",
                                                         medio="Escrito")])
    p = db.personas.find_one({"cedula": "90005001"})
    assert (p["consentimiento_medio"], p["contacto_habilitado"]) == ("escrito", True)
    assert res.autorizaciones_por_confirmar == 0
    assert "fotos_sha256" not in db.importaciones.find_one()
