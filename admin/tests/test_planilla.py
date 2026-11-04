"""Planilla de campo (2.1, 2.2): reconocimiento, autorizaciones, auditoría con el actor real y quien la llenó, cédula
mal repetida, columna «Planillero» y plantilla que se vuelve a importar. Solo personas inventadas."""
import io
from datetime import date

import openpyxl

from app.pipeline import lectores
from ayudas_g1 import fila_planilla, importar
from conftest import (CEDULAS, COLUMNAS_PLANILLA, PLANILLA, TRAMITES, crear_usuario, excel_cedulas, excel_planilla,
                      excel_tramites)


def test_reconocimiento(tmp_path):
    assert lectores.tipo_de_archivo(excel_planilla(tmp_path / "p.xlsx", PLANILLA)) == "planilla"
    assert lectores.tipo_de_archivo(excel_cedulas(tmp_path / "c.xlsx", CEDULAS)) == "cedulas"
    assert lectores.tipo_de_archivo(excel_tramites(tmp_path / "t.xlsx", TRAMITES)) == "tramites"
    regs = list(lectores.leer_registros(tmp_path / "p.xlsx", "planilla"))
    assert len(regs) == len(PLANILLA)
    r = regs[0]
    assert (r.cedula, r.tipo_documento, r.sexo, r.fecha_nacimiento) == ("90000101", "CC", "F", "1979-03-14")
    assert r.telefonos == ["3101234501", "3101234502", "6047001234"]
    assert (r.autorizacion, r.autorizacion_medio, r.canales) == ("si", "escrito", ["llamada", "whatsapp"])
    assert r.datos["mayor_de_18"] is True and r.planillero == "ana.campo" and r.fecha == "2026-11-02"
    assert r.clave_fila == "90000101" and r.lugar_texto == "TRES DE OCTUBRE" and "TRES DE OCTUBRE" in r.direccion
    sin = regs[2]
    assert sin.cedula is None and len(sin.clave_fila) == 40 and sin.mesa_texto == "Mesa # 3"
    mal = regs[3]
    assert mal.cedula is None and (mal.datos["cedula_digitada"], mal.datos["cedula_repetida"]) == ("90000121", "90000112")
    assert regs[4].autorizacion == "no" and regs[5].tipo_documento == "TI" and regs[5].datos["mayor_de_18"] is False
    # La clave de una fila sin cédula no depende del número de fila
    otra = list(lectores.leer_registros(excel_planilla(tmp_path / "p2.xlsx", [PLANILLA[5], PLANILLA[2]]), "planilla"))
    assert otra[1].clave_fila == sin.clave_fila


def test_auditoria_con_el_actor_real_y_capturado_por(bases, tmp_path):
    db = bases()
    ana = crear_usuario(db, "planillero", usuario="ana.campo")
    otro = crear_usuario(db, "planillero", usuario="beto.campo")
    res = importar(db, tmp_path, planilla=PLANILLA, capturado_por=otro["_id"])
    assert res.planilleros_desconocidos == ["pedro.inexistente"]
    aud = list(db.auditoria.find({"accion": {"$in": ["crear", "editar"]}, "entidad": "persona"}))
    assert aud and all(a["uid"] == 0 and a["rol"] == "admin" for a in aud)
    por = {db.personas.find_one({"_id": a["entidad_id"]})["nombre"]: a for a in aud}
    assert por["HERMELINDA PATROCINIA OSPINO VILLAREAL"]["capturado_por"] == ana["_id"]  # la columna manda
    assert por["ROSAURA DEL CARMEN BOHORQUEZ TAPIAS"]["capturado_por"] == otro["_id"]  # planillero desconocido
    h = por["HERMELINDA PATROCINIA OSPINO VILLAREAL"]
    assert h["accion"] == "crear" and {"cedula", "telefono", "sexo", "edad", "puesto", "mesa"} <= set(h["completados"])
    assert '"via": "planilla"' in h["detalle"]
    nueva = db.personas.find_one({"cedula": "90000101"})
    assert nueva["creado_por"] == {"uid": 0, "usuario": "admin", "rol": "admin", "capturado_por": ana["_id"]}
    # Las entradas van después de guardar: cada una corresponde a una ficha que existe
    assert all(db.personas.find_one({"_id": a["entidad_id"]}) for a in aud)
    # Reimportar lo mismo no audita nada
    n = db.auditoria.count_documents({"accion": {"$in": ["crear", "editar"]}})
    res = importar(db, tmp_path, planilla=PLANILLA, capturado_por=otro["_id"], nombre="2")
    assert db.auditoria.count_documents({"accion": {"$in": ["crear", "editar"]}}) == n
    assert res.personas_nuevas == 0
    # Una fila con un dato nuevo audita «editar» solo con ese campo
    fila = list(PLANILLA[0])
    fila[COLUMNAS_PLANILLA.index("Observaciones")] = "Vive con su hija"
    fila[COLUMNAS_PLANILLA.index("Otro teléfono")] = "3101234502 / 6047001234 / 3101234509"
    importar(db, tmp_path, planilla=[tuple(fila)], nombre="3")
    ultima = db.auditoria.find_one({"accion": "editar", "entidad_id": nueva["_id"]})
    assert ultima["campos"] == ["observaciones", "telefono"] and ultima["completados"] == []
    assert ultima["capturado_por"] == ana["_id"]


def test_autorizacion_con_y_sin_medio(bases, tmp_path):
    db = bases()
    filas = [fila_planilla("90000201", "ABIGAIL INVENTADA ESCRITO", "3101110201", medio="Escrito", canales="Llamada, SMS",
                           fecha=date(2026, 11, 2)),
             fila_planilla("90000202", "BALTAZAR INVENTADO SINMEDIO", "3101110202", medio=None, canales="WhatsApp"),
             fila_planilla("90000203", "CELMIRA INVENTADA NOAUTORIZA", "3101110203", autoriza="No autoriza",
                           medio=None, canales=None, sexo="Mujer", edad=44)]
    res = importar(db, tmp_path, planilla=filas)
    assert res.autorizaciones_por_confirmar == 1
    a = db.personas.find_one({"cedula": "90000201"})
    assert (a["consentimiento"], a["consentimiento_medio"], a["contacto_habilitado"]) == ("si", "escrito", True)
    assert a["consentimiento_canales"] == ["llamada", "sms"] and a["consentimiento_fecha"] == "2026-11-02"
    assert a["mayor_declarado"] is True
    ev = db.autorizaciones.find_one({"persona_id": a["_id"]})
    assert ev["evidencia"].endswith("fila 2") and len(ev["evidencia_sha256"]) == 64
    assert ev["evidencia_fila"]["nombre"] == "ABIGAIL INVENTADA ESCRITO" and ev["uid"] == 0
    b = db.personas.find_one({"cedula": "90000202"})
    assert (b["consentimiento"], b["consentimiento_medio"], b["contacto_habilitado"]) == ("si", "declarado_planilla", False)
    c = db.personas.find_one({"cedula": "90000203"})
    assert c["consentimiento"] == "no" and c["telefonos"] == [] and c["sexo"] is None and c["edad"] is None
    assert c["origen"][0]["datos"] == {}
    # Reimportar no duplica los eventos
    importar(db, tmp_path, planilla=filas, nombre="2")
    assert db.autorizaciones.count_documents({}) == 3


def test_cedula_y_repeticion_distintas(bases, tmp_path):
    db = bases()
    res = importar(db, tmp_path, planilla=[PLANILLA[3]])
    p = db.personas.find_one({"nombre": "ABELARDO SEGUNDO MONTIEL CUESTA"})
    assert p["cedula"] is None and res.conflictos_cedula == 1
    c = db.conflictos_cedula.find_one()
    assert (c["motivo"], c["persona_id"], c["cedula"]) == ("posible_digitacion", p["_id"], "90000121")
    assert c["registro"]["datos"]["cedula_repetida"] == "90000112"
    assert p["votacion"]["estado"] == "por_confirmar" and p["votacion"]["puesto_id"] is None  # puesto ambiguo


def test_columna_planillero(bases, tmp_path):
    db = bases()
    activo = crear_usuario(db, "planillero", usuario="ana.campo")
    inactivo = crear_usuario(db, "planillero", usuario="luz.inactiva", activo=False)
    consultor = crear_usuario(db, "consultor", usuario="carlos.consultor")
    filas = [fila_planilla("90000301", "PERSONA INVENTADA UNO", planillero="ana.campo"),
             fila_planilla("90000302", "PERSONA INVENTADA DOS", planillero="luz.inactiva"),
             fila_planilla("90000303", "PERSONA INVENTADA TRES", planillero="carlos.consultor"),
             fila_planilla("90000304", "PERSONA INVENTADA CUATRO")]
    res = importar(db, tmp_path, planilla=filas, capturado_por=77)
    assert res.planilleros_desconocidos == ["luz.inactiva", "carlos.consultor"]
    cap = {p["cedula"]: p["creado_por"].get("capturado_por") for p in db.personas.find({}, {"cedula": 1, "creado_por": 1})}
    assert cap == {"90000301": activo["_id"], "90000302": 77, "90000303": 77, "90000304": 77}
    assert inactivo["_id"] and consultor["_id"]


def test_tipo_ti_menor_y_votacion(bases, tmp_path):
    db = bases()
    importar(db, tmp_path, planilla=PLANILLA)
    menor = db.personas.find_one({"cedula": "1012345678"})
    assert menor["tipo_documento"] == "TI" and menor["mayor_declarado"] is False and menor["nac_exacta"] is True
    h = db.personas.find_one({"cedula": "90000101"})
    luis = db.puestos.find_one({"codigo": "00-01"})
    assert h["votacion"]["puesto_id"] == luis["_id"] and h["votacion"]["mesa"] == 12
    assert h["votacion"]["eleccion"] == "2026-presidencial" and h["votacion"]["estado"] == "sin_verificar"
    assert h["votacion"]["fuente"] == "planilla" and h["puesto_votacion"] == luis["nombre"] and h["mesa"] == "12"
    r = db.personas.find_one({"nombre": "ROSAURA DEL CARMEN BOHORQUEZ TAPIAS"})
    assert r["mesa"] == "Mesa # 3" and r["votacion"]["mesa"] == 3


def test_la_plantilla_se_puede_volver_a_importar(sesion):
    r = sesion.get("/api/plantillas/planilla.xlsx")
    assert r.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Planilla", "Puestos", "Aviso"]
    ws = wb["Planilla"]
    assert [c.value for c in ws[1]] == COLUMNAS_PLANILLA
    assert len(ws.data_validations.dataValidation) >= 7
    assert wb["Puestos"].max_row == 8  # encabezado y los 7 puestos vigentes
    for f in PLANILLA[:2]:
        ws.append(list(f))
    buf = io.BytesIO()
    wb.save(buf)
    r = sesion.post("/api/importar", files=[("archivos", ("planilla-llena.xlsx", buf.getvalue()))])
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["archivos"][0]["tipo"] == "planilla" and res["registros_por_fuente"] == {"planilla": 2}
    assert res["personas_nuevas"] == 2
    assert sesion.app.state.db.auditoria.count_documents({"accion": "descargar_plantilla"}) == 1
