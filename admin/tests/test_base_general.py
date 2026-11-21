"""La base general de la campaña: el tipo de persona (concejal, líder, votante), el «Liderado por» y los 17 campos
principales de la ficha (perfil profesional incluido), y su importación sin duplicar a nadie.

Solo personas inventadas. Las pruebas del lector, del modelo y de la proyección corren sin MongoDB; las de la
importación y de la API, con MongoDB (como en CI)."""
from __future__ import annotations

import io
import json
from datetime import datetime
from pathlib import Path

import openpyxl
import pytest

from app import modelo, proyeccion
from app.api import personas as api_personas
from app.pipeline import lectores
from app.pipeline import importar as imp
from app.pipeline.fuentes import GENERAL, Registro
from ayudas_g3 import autorizada, coordinador, persona, sin_vedados, sin_vedados_p, tomar
from conftest import COLUMNAS_PLANILLA, excel_cedulas, excel_planilla

# Los encabezados de la base general tal como llegan (con la errata «COMPLETPO» y tres columnas «CONTACTO»)
ENCABEZADOS = ["CC", "NOMBRE COMPLETPO", "CONTACTO", "CONTACTO", "CONTACTO", "DIRECCIÓN", "BARRIO", "MUNICIPIO",
               "GRUPO", "LIDER", "LIDER CONFIRMADO POR EL CANDIDATO", "VOTOS", "PUESTO DE VOTACIÓN", "MESA",
               "ELECCIÓN", "FECHA DE NACIMIENTO", "PROFESIÓN"]
# Los 17 campos principales de la ficha como columnas
CAMPOS_17 = ["Nombre", "Cédula", "Sexo", "Edad", "Teléfono", "Fecha de nacimiento", "Correo electrónico", "Dirección",
             "Barrio o vereda", "Zona Urbana o Rural", "Líder", "Votante", "Liderado por", "Perfil profesional",
             "Ocupación", "Estado civil", "Jefe de hogar"]


def fila(cc=None, nombre=None, contactos=(), direccion=None, barrio=None, municipio="YONDO", grupo=None, lider=" -   ",
         confirmado=None, votos=None, puesto="PUESTO INVENTADO", mesa=None, eleccion=None, nacimiento=None,
         profesion=None) -> list:
    tels = [*contactos, None, None, None][:3]
    return [cc, nombre, *tels, direccion, barrio, municipio, grupo, lider, confirmado, votos, puesto, mesa, eleccion,
            nacimiento, profesion]


def excel_general(ruta: Path, filas: list[list], encabezados=ENCABEZADOS, hoja="BD_campana") -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = hoja
    ws.append(encabezados)
    for f in filas:
        ws.append(list(f))
    wb.save(ruta)
    return ruta


# Una base inventada: un votante con su líder (que no tiene fila propia), un concejal que además es líder (con el grupo
# mal codificado, como sale de algunas exportaciones), uno sin cédula de una lista, una fila vacía y un coordinador
FILAS = [
    fila(1000000001, "ANA INVENTADA DE PRUEBA", (3001112233, 3004445566), "CL 49 # 45-12", "EL PRADO",
         grupo="Votante, Votante", lider="1000000009 - LIDER INVENTADO PRIMERO", mesa=3, eleccion=1,
         nacimiento=datetime(1980, 5, 17), profesion="DOCENTE"),
    fila("\xa01000000002", "BERTA INVENTADA CONCEJAL", (3007778899,), barrio="VILLA INVENTADA",
         grupo="LÃ­deres, Candidato al concejo", confirmado="SI", votos=20),
    fila(None, "CARLOS INVENTADO SIN CEDULA", (3109998877,), barrio="EL PRADO",
         grupo="Familias en acciÃ³n", votos="ZONA PLANA", nacimiento="Vigente con Perdida"),
    [None] * len(ENCABEZADOS),
    fila(1000000004, "DIEGO INVENTADO COORDINADOR", (3012223344,), grupo="Coordinadores",
         lider="1000000002 - BERTA INVENTADA CONCEJAL"),
]


# ───────────────────────────── Lector (sin base) ─────────────────────────────

def test_reconoce_la_base_general_sin_confundir_las_otras(tmp_path):
    assert lectores.tipo_de_archivo(excel_general(tmp_path / "g.xlsx", FILAS)) == "general"
    assert lectores.tipo_de_archivo(excel_general(tmp_path / "c17.xlsx", [], CAMPOS_17)) == "general"
    # La base con cédula tiene «Partido / grupo», no «Grupo»: sigue siendo la base con cédula
    assert lectores.tipo_de_archivo(excel_cedulas(tmp_path / "b.xlsx", [])) == "cedulas"
    assert lectores.tipo_de_archivo(excel_planilla(tmp_path / "p.xlsx", [])) == "planilla"
    assert len(COLUMNAS_PLANILLA) == 20


def test_lee_la_base_general(tmp_path):
    regs = list(lectores.leer_registros(excel_general(tmp_path / "g.xlsx", FILAS), "general"))
    assert [r.nombre for r in regs] == ["ANA INVENTADA DE PRUEBA", "BERTA INVENTADA CONCEJAL",
                                        "CARLOS INVENTADO SIN CEDULA", "DIEGO INVENTADO COORDINADOR"]
    ana, berta, carlos, diego = regs
    assert all(r.fuente == "general" for r in regs)
    # Ana: votante, liderada por alguien que no tiene fila, con sus dos teléfonos y su barrio en la dirección
    assert (ana.cedula, ana.tipo_documento, ana.telefonos) == ("1000000001", "CC", ["3001112233", "3004445566"])
    assert ana.tipos == ["votante"] and ana.listas == []
    assert ana.lider_ref == {"cedula": "1000000009", "nombre": "LIDER INVENTADO PRIMERO"}
    assert (ana.direccion, ana.lugar_texto) == ("CL 49 # 45-12, EL PRADO", "EL PRADO")
    assert (ana.fecha_nacimiento, ana.perfil_profesional) == ("1980-05-17", "DOCENTE")
    assert (ana.puesto_texto, ana.mesa_texto) == ("PUESTO INVENTADO", "3")
    assert ana.clave_fila == "1000000001"
    assert ana.datos["liderado_por"] == "1000000009 - LIDER INVENTADO PRIMERO"
    assert ana.datos["municipio"] == "YONDO" and ana.datos["eleccion"] == "1"
    # Berta: la cédula con un espacio duro delante, el grupo reparado y «Líder confirmado» con sus votos
    assert berta.cedula == "1000000002" and berta.lider_ref is None
    assert set(berta.tipos) == {"lider", "concejal"} and berta.listas == []
    assert berta.datos["lider_confirmado"] is True and berta.datos["votos"] == 20
    # Carlos: sin cédula (llave por huella), su lista reparada y lo que no es una fecha ni un número, aparte
    assert carlos.cedula is None and len(carlos.clave_fila) == 40
    assert carlos.tipos == [] and carlos.listas == ["Familias en acción"]
    assert carlos.fecha_nacimiento is None and carlos.datos["fecha_nacimiento_texto"] == "Vigente con Perdida"
    assert carlos.datos["votos_nota"] == "ZONA PLANA" and "votos" not in carlos.datos
    # Diego: los coordinadores traen gente (son líderes) y quedan en su lista
    assert diego.tipos == ["lider"] and diego.listas == ["Coordinadores"]
    assert diego.lider_ref == {"cedula": "1000000002", "nombre": "BERTA INVENTADA CONCEJAL"}


def test_lee_las_columnas_de_los_17_campos(tmp_path):
    filas = [
        ["ELENA INVENTADA COMPLETA", "1000000011", "Mujer", 34, "300 111 2211", "1990-02-03", "correo.inventado@ejemplo.org",
         "CL 50 # 40-10", "EL PRADO", "Urbana", "No", "Sí", "1000000012 - FABIO INVENTADO LIDER", "Enfermera",
         "Independiente", "CASADA", "Sí"],
        ["FABIO INVENTADO LIDER", "1000000012", "M", None, None, None, None, None, "LA VEREDA INVENTADA", "Rural",
         "Sí", "No", None, None, None, "union libre", "No"],
    ]
    elena, fabio = lectores.leer_registros(excel_general(tmp_path / "c.xlsx", filas, CAMPOS_17), "general")
    assert (elena.cedula, elena.sexo, elena.edad, elena.telefonos) == ("1000000011", "F", 34, ["3001112211"])
    assert (elena.fecha_nacimiento, elena.correo) == ("1990-02-03", "correo.inventado@ejemplo.org")
    assert elena.tipos == ["votante"]
    assert elena.lider_ref == {"cedula": "1000000012", "nombre": "FABIO INVENTADO LIDER"}
    assert (elena.perfil_profesional, elena.ocupacion) == ("Enfermera", "Independiente")
    assert (elena.estado_civil, elena.jefe_hogar) == ("Casado(a)", True)
    assert elena.datos["zona"] == "Urbana" and elena.direccion == "CL 50 # 40-10, EL PRADO"
    assert fabio.tipos == ["lider"] and fabio.lider_ref is None
    assert (fabio.estado_civil, fabio.jefe_hogar, fabio.sexo) == ("Unión libre", False, "M")


def test_ayudas_del_lector():
    assert lectores._reparar("LÃ­deres") == "Líderes"
    assert lectores._reparar("Familias en acción") == "Familias en acción"  # lo que ya está bien no cambia
    assert lectores._reparar("") == "" and lectores._reparar("EVENTOS") == "EVENTOS"
    assert lectores._referencia(" -   ") is None and lectores._referencia(None) is None
    assert lectores._referencia("1000000456 - JUAN  INVENTADO") == {"cedula": "1000000456", "nombre": "JUAN INVENTADO"}
    assert lectores._referencia("1.000.000.789") == {"cedula": "1000000789", "nombre": None}
    assert lectores._referencia("SOLO NOMBRE INVENTADO") == {"cedula": None, "nombre": "SOLO NOMBRE INVENTADO"}
    tipos, listas = lectores._grupos("Votante, Votante, Bd externa, Eventos, Bd externa")
    assert tipos == ["votante"] and listas == ["Bd externa", "Eventos"]
    assert lectores._grupos("Candidato al concejo, Lideres") == (["concejal", "lider"], [])
    assert lectores._grupos(None) == ([], [])


def test_el_lider_sin_fila_entra_como_una_fila_mas():
    def r(ced, nombre, ref=None):
        return Registro(fuente="general", fila=1, clave_fila=ced or nombre, cedula=ced, tipo_documento="CC",
                        nombre=nombre, lider_ref=ref)
    regs = [r("1000000001", "ANA", {"cedula": "1000000009", "nombre": "LIDER INVENTADO"}),
            r("1000000003", "OTRA", {"cedula": "1000000009", "nombre": "LIDER INVENTADO"}),
            r("1000000004", "CON FILA", {"cedula": "1000000001", "nombre": "ANA"}),
            r(None, "SIN NOMBRE DE LIDER", {"cedula": "1000000008", "nombre": None}),
            r(None, "SIN CEDULA DE LIDER", {"cedula": None, "nombre": "ALGUIEN"})]
    extra = imp._lideres_sin_fila(regs)
    assert [(x.cedula, x.nombre, x.clave_fila, x.tipos) for x in extra] == [
        ("1000000009", "LIDER INVENTADO", "1000000009", [])]
    assert extra[0].datos["nombrado_como_lider"] is True


def test_modelo_y_lo_que_ve_cada_rol():
    assert list(modelo.TIPOS_PERSONA) == ["concejal", "lider", "votante"]
    assert modelo.lidera({"concejal": True}) and modelo.lidera({"lider": True})
    assert not modelo.lidera({"votante": True}) and not modelo.lidera({}) and not modelo.lidera(None)
    assert modelo.tipos_de({"votante": True, "lider": True, "concejal": False}) == ["lider", "votante"]
    assert "perfil_profesional" in modelo.CAMPOS_PROCEDENCIA
    # El tipo de persona es un dato político: A y K en toda ficha y fila; P solo en la ficha (de las personas de su zona
    # o que registró: `proyeccion.tipo_visible`), nunca en la fila; C nunca. P lo marca (solo suma, con
    # `personas.tipo`): ya no es un campo vedado, pero no está en sus editables fijos (los suma `editables` por persona)
    for t in modelo.TIPOS_PERSONA:
        assert t in proyeccion.CAMPOS_FICHA["admin"] and t in proyeccion.CAMPOS_FILA["admin"]
        assert t in proyeccion.CAMPOS_FICHA["planillero"] and t not in proyeccion.CAMPOS_FILA["planillero"]
        assert t not in proyeccion.CAMPOS_FICHA["consultor"] and t not in proyeccion.CAMPOS_FILA["consultor"]
        assert t not in api_personas.VEDADOS_P and t in proyeccion.EDITABLES_A and t not in proyeccion.EDITABLES_P
    assert "perfil_profesional" in proyeccion.CAMPOS_FICHA["planillero"]
    assert "perfil_profesional" in proyeccion.EDITABLES_P
    # La base general, como la base con cédula, se ve como «otra base» para P y C
    assert proyeccion.neutralizar_fuente("general") == "otra_base"
    assert proyeccion.neutralizar_fuente(["general", "cedulas", "planilla"]) == ["otra_base", "planilla"]
    assert modelo.CONFIANZA["general"] == modelo.CONFIANZA["cedulas"]
    assert GENERAL.clave == "general" and GENERAL.tiene_cedula


# ───────────────────────────── Importación (MongoDB) ─────────────────────────────

def _importar(db, tmp_path, filas, nombre="g"):
    return imp.importar(db, [excel_general(tmp_path / f"{nombre}.xlsx", filas)])


def test_importa_la_base_general_sin_duplicar(bases, tmp_path):
    from app import db as bd
    db = bases()
    # Ana ya estaba (otra base, con otro teléfono): la base general la completa, no la duplica
    previa = bd.nueva_persona(db, {"nombre": "ANA INVENTADA DE PRUEBA", "cedula": "1000000001",
                                   "telefono": "3205550001"}, "manual")
    db.personas.insert_one(previa)
    res = _importar(db, tmp_path, FILAS)
    assert db.personas.count_documents({"cedula": "1000000001"}) == 1
    ana = db.personas.find_one({"cedula": "1000000001"})
    assert ana["_id"] == previa["_id"] and "general" in ana["fuentes"]
    assert {"3205550001", "3001112233", "3004445566"} <= {t["numero"] for t in ana["telefonos"]}
    assert ana["votante"] is True and ana["procedencia"]["votante"]["fuente"] == "general"
    assert ana["perfil_profesional"] == "DOCENTE" and ana["fecha_nacimiento"] == "1980-05-17"
    # Su líder no tenía fila: se creó su ficha con la cédula y el nombre, marcada como líder, y quedó enlazada
    lider = db.personas.find_one({"cedula": "1000000009"})
    assert lider["nombre"] == "LIDER INVENTADO PRIMERO" and lider["lider"] is True and lider["fuentes"] == ["general"]
    assert [l["id"] for l in ana["lideres"]] == [lider["_id"]] and ana["lideres"][0]["fuente"] == "general"
    # Berta: concejal y líder; Diego (coordinador) es líder y lo lidera Berta
    berta = db.personas.find_one({"cedula": "1000000002"})
    assert (berta["concejal"], berta["lider"], berta["votante"]) == (True, True, False)
    diego = db.personas.find_one({"cedula": "1000000004"})
    assert diego["lider"] is True and [l["id"] for l in diego["lideres"]] == [berta["_id"]]
    assert "Coordinadores" in diego["listas"]
    carlos = db.personas.find_one({"nombre": "CARLOS INVENTADO SIN CEDULA"})
    assert carlos["cedula"] is None and carlos["listas"] == ["Familias en acción"]
    assert res.lideres_asignados == 2 and res.lideres_sin_resolver == 0
    assert res.tipos_marcados == {"votante": 1, "lider": 3, "concejal": 1}
    total = db.personas.count_documents({})
    # Volver a importar no duplica nada ni repite líderes
    res2 = _importar(db, tmp_path, FILAS, "g2")
    assert db.personas.count_documents({}) == total and res2.personas_nuevas == 0
    assert res2.lideres_asignados == 0 and res2.tipos_marcados == {}
    assert len(db.personas.find_one({"_id": ana["_id"]})["lideres"]) == 1


def test_la_importacion_no_deshace_lo_que_se_hizo_a_mano(bases, tmp_path):
    db = bases()
    _importar(db, tmp_path, FILAS)
    ana = db.personas.find_one({"cedula": "1000000001"})
    lider = ana["lideres"][0]["id"]
    # En el panel le quitaron el «votante» y el líder (como lo dejan PATCH y DELETE /lideres)
    db.personas.update_one({"_id": ana["_id"]}, {"$set": {
        "votante": False, "procedencia.votante": {"fuente": "panel", "ts": "2026-11-20T00:00:00+00:00", "uid": 0},
        "lideres": [], "lideres_quitados": [lider]}})
    _importar(db, tmp_path, FILAS, "g2")
    ana = db.personas.find_one({"_id": ana["_id"]})
    assert ana["votante"] is False and ana["lideres"] == []


def test_un_lider_con_otro_nombre_no_se_enlaza(bases, tmp_path):
    from app import db as bd
    db = bases()
    otra = bd.nueva_persona(db, {"nombre": "PERSONA INVENTADA TOTALMENTE DISTINTA", "cedula": "1000000009"}, "manual")
    db.personas.insert_one(otra)
    res = _importar(db, tmp_path, FILAS[:1])
    ana = db.personas.find_one({"cedula": "1000000001"})
    assert ana["lideres"] == [] and res.lideres_sin_resolver == 1
    assert db.personas.find_one({"_id": otra["_id"]})["lider"] is False
    # La fila del líder nombrado con otro nombre quedó como conflicto de cédula, para que el administrador decida
    assert db.conflictos_cedula.count_documents({"cedula": "1000000009", "motivo": "nombre_distinto"}) == 1


# ───────────────────────────── API (MongoDB) ─────────────────────────────

def test_tipo_de_persona_y_liderado_por_en_la_api(sesion, como):
    db = sesion.app.state.db
    concejal = persona(db, nombre="CONCEJAL INVENTADA DE PRUEBA")
    votante = persona(db, nombre="VOTANTE INVENTADO DE PRUEBA")
    # Marcar el tipo (A y K; P solo suma: tests/test_tipo_planillero.py) queda con su procedencia (la importación no lo
    # vuelve a cambiar)
    r = sesion.patch(f"/api/personas/{concejal}", json={"concejal": True, "perfil_profesional": "Abogada",
                                                         "base": {"concejal": False}})
    assert r.status_code == 200, r.text
    f = r.json()
    assert (f["concejal"], f["lider"], f["votante"], f["perfil_profesional"]) == (True, False, False, "Abogada")
    assert f["procedencia"]["concejal"]["fuente"] == "panel"
    a = db.auditoria.find_one({"entidad_id": concejal, "accion": "editar"}, sort=[("_id", -1)])
    assert json.loads(a["detalle"])["concejal"] == "(oculto)"  # dato político: la auditoría no dice cuál
    # Un concejal lidera votantes como un líder
    assert sesion.post(f"/api/personas/{votante}/lideres", json={"lider_id": concejal}).status_code == 201
    assert sesion.patch(f"/api/personas/{votante}", json={"votante": True}).status_code == 200
    f = sesion.get(f"/api/personas/{votante}").json()
    assert [(l["id"], l["tipo"], l["marcado"]) for l in f["lideres"]] == [(concejal, "concejal", True)]
    ls = {l["id"]: l for l in sesion.get("/api/lideres").json()["lideres"]}
    assert (ls[concejal]["tipo"], ls[concejal]["traidas"], ls[concejal]["votantes"]) == ("concejal", 1, 1)
    assert sesion.get(f"/api/personas/{concejal}").json()["traidas"] == {"total": 1, "compartidas": 0}
    # Habitantes por tipo
    ids = lambda **q: {x["id"] for x in sesion.get("/api/personas", params=q).json()["filas"]}  # noqa: E731
    assert ids(tipo="votante") == {votante} and ids(tipo="concejal") == {concejal}
    assert votante not in ids(tipo="sin_tipo") and concejal not in ids(tipo="sin_tipo")
    # Quitarle el líder a mano queda anotado: la importación no se lo vuelve a poner; asignarlo de nuevo lo borra
    assert sesion.delete(f"/api/personas/{votante}/lideres/{concejal}").status_code == 200
    assert db.personas.find_one({"_id": votante})["lideres_quitados"] == [concejal]
    assert sesion.post(f"/api/personas/{votante}/lideres", json={"lider_id": concejal}).status_code == 201
    assert db.personas.find_one({"_id": votante})["lideres_quitados"] == []
    # Una ficha vieja, sin el campo: la base «no» no da un 409 falso
    db.personas.update_one({"_id": concejal}, {"$unset": {"votante": ""}})
    r = sesion.patch(f"/api/personas/{concejal}", json={"votante": True, "base": {"votante": False}})
    assert r.status_code == 200 and r.json()["votante"] is True


def test_alta_de_un_votante_con_su_lider(sesion, como):
    db = sesion.app.state.db
    lider = persona(db, nombre="LIDER INVENTADO DEL ALTA", lider=True)
    r = sesion.post("/api/personas", json={"nombre": "VOTANTE INVENTADA DEL ALTA", "votante": True, "lideres": [lider],
                                           "perfil_profesional": "Contadora", "ocupacion": "Comerciante",
                                           "estado_civil": "Soltero(a)", "jefe_hogar": True,
                                           "correo": "votante@ejemplo.org", "forzar": True})
    assert r.status_code == 201, r.text
    f = r.json()
    assert (f["votante"], f["lider"], f["concejal"]) == (True, False, False)
    assert [l["id"] for l in f["lideres"]] == [lider]
    assert (f["perfil_profesional"], f["ocupacion"], f["estado_civil"], f["jefe_hogar"]) == (
        "Contadora", "Comerciante", "Soltero(a)", True)
    # Solo el tipo marcado lleva procedencia (un «no» por defecto no le impide a la importación marcarlo)
    assert set(f["procedencia"]) & set(modelo.TIPOS_PERSONA) == {"votante"}
    # «Completar» una ficha que ya existe solo suma tipos
    r = sesion.patch(f"/api/personas/{f['id']}?modo=completar", json={"votante": False, "lider": True})
    assert r.status_code == 200 and (r.json()["votante"], r.json()["lider"]) == (True, True)


def test_planillero_no_quita_el_tipo_y_el_consultor_no_lo_ve(sesion, como):
    db = sesion.app.state.db
    x = persona(db, nombre="PERSONA INVENTADA CON TIPO", votante=True, concejal=True, lider=True,
                perfil_profesional="Ingeniero", fuentes=["general"], telefono="3001110099")
    p = como("planillero")
    # P ve el tipo en la ficha (sin asignación, toda la base es su zona) y lo suma, pero no lo quita
    for campo in modelo.TIPOS_PERSONA:
        r = p.patch(f"/api/personas/{x}", json={campo: False})
        assert r.status_code == 403 and r.json()["detail"]["campo"] == campo, r.text
    d = db.personas.find_one({"_id": x})
    assert (d["votante"], d["concejal"], d["lider"]) == (True, True, True)
    f = p.get(f"/api/personas/{x}").json()
    sin_vedados_p(f, "ficha de P")
    assert (f["votante"], f["concejal"], f["lider"], f["perfil_profesional"]) == (True, True, True, "Ingeniero")
    sin_vedados(p.get("/api/personas").json(), "filas de P")
    for filtro in ({"tipo": "votante"}, {"fuente": "general"}):
        assert p.get("/api/personas", params=filtro).status_code == 403
    # C: ni lo ve en la ficha ni lo marca
    autorizada(db, x)
    c = como("consultor")
    tomar(c, x)
    f = c.get(f"/api/personas/{x}").json()
    sin_vedados(f, "ficha de C")
    for campo in modelo.TIPOS_PERSONA:
        assert c.patch(f"/api/personas/{x}", json={campo: True}).status_code == 403
        assert c.post("/api/personas", json={"nombre": "OTRA PERSONA INVENTADA", campo: True,
                                             "forzar": True}).status_code == 403
    k = coordinador(sesion.app, db)
    assert k.get(f"/api/personas/{x}").json()["votante"] is True
    assert k.patch(f"/api/personas/{x}", json={"votante": False}).status_code == 200


def test_la_exportacion_lleva_los_campos_nuevos(sesion):
    db = sesion.app.state.db
    lider = persona(db, nombre="LIDER INVENTADO EXPORTADO", lider=True)
    x = persona(db, nombre="VOTANTE INVENTADA EXPORTADA", votante=True, perfil_profesional="Docente",
                lideres=[{"id": lider, "asignado_en": "2026-11-20", "asignado_por": "admin"}])
    r = sesion.get("/api/exportar.xlsx", params={"motivo": "operacion_interna"})
    assert r.status_code == 200, r.text
    ws = openpyxl.load_workbook(io.BytesIO(r.content), read_only=True).worksheets[0]
    filas = list(ws.iter_rows(values_only=True))
    enc = list(filas[0])
    for c in ("Concejal", "Líder", "Votante", "Liderado por", "Perfil profesional"):
        assert c in enc, c
    por_id = {f[enc.index("ID")]: f for f in filas[1:]}
    v = por_id[x]
    assert (v[enc.index("Votante")], v[enc.index("Perfil profesional")]) == ("Sí", "Docente")
    assert v[enc.index("Liderado por")] == "LIDER INVENTADO EXPORTADO"
