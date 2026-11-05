"""Contrato del paso 0 de la ampliación: funciones puras de `modelo`, `geometria`, `acceso` y
`proyeccion.exigir_tratable`, los gemelos en Python de las expresiones de MongoDB y las piezas que comparten los grupos
(routers, módulos JS, fixture `como`, generadores de datos). Solo datos inventados.

Congelado desde el paso 0: ningún grupo lo edita. Lo que depende de otro grupo se salta por una condición explícita.
"""
import copy
import inspect
import json
import math
import re
import shutil
import subprocess
from datetime import date, timedelta
from pathlib import Path

import openpyxl
import pytest
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from app import acceso, geometria, migraciones, modelo, proyeccion
from app import db as bd
from app.pipeline import importar as imp
from app.pipeline import texto as tx
from conftest import (CEDULAS, COLUMNAS_PLANILLA, PLANILLA, crear_usuario, excel_planilla, insertar_personas,
                      personas_inventadas)

RAIZ = Path(__file__).resolve().parents[1]
HOY = date(2026, 11, 4)
ELECCION = "2026-presidencial"


def T(numero, *fuentes, **campos):
    """Un elemento de `telefonos` inventado."""
    return modelo.telefono_nuevo(numero, **({"fuentes": list(fuentes)} if fuentes else {}), **campos)


# ───────────────────────────── Catálogos ─────────────────────────────

def test_catalogos_de_la_especificacion():
    assert modelo.SEXOS == {"F": "Mujer", "M": "Hombre", "N": "Prefiere no decir"}
    assert modelo.NIVELES == ["Ninguno", "Primaria", "Secundaria", "Técnico", "Tecnólogo", "Universitario", "Posgrado"]
    assert modelo.ESTADOS_CIVILES == ["Soltero(a)", "Casado(a)", "Unión libre", "Separado(a) o divorciado(a)", "Viudo(a)"]
    assert modelo.SITUACIONES_LABORALES == ["Empleado(a)", "Independiente", "Agricultor(a) o pescador(a)", "Desempleado(a)",
                                            "Estudiante", "Oficios del hogar", "Pensionado(a)", "Otra"]
    assert modelo.TENENCIAS == ["Propia", "Arriendo", "Familiar", "Posesión", "Otra"]
    assert modelo.REGIMENES_SALUD == ["Contributivo", "Subsidiado", "Especial", "Ninguno"]
    assert modelo.RANGOS_EDAD == ["<18", "18-24", "25-34", "35-44", "45-54", "55-64", "65+"]
    assert set(modelo.TIPOS_DOCUMENTO) == {"CC", "TI", "CE", "PPT", "PEP", "PA"}
    assert set(modelo.SENSIBLES) == {"etnia", "discapacidad", "victima"}
    assert set(modelo.CANALES) == {"llamada", "whatsapp", "sms", "visita", "reunion", "correo", "otro"}
    assert set(modelo.CANALES_AUTORIZACION) == {"llamada", "whatsapp", "sms", "correo", "visita", "grupos"}
    assert set(modelo.CANALES_IMPLICITOS) == {"llamada", "whatsapp", "sms"}
    assert set(modelo.ESTADOS_TELEFONO) == {"sin_verificar", "confirmado", "no_usa", "equivocado", "inexistente", "retirado"}
    assert modelo.USABLES == {"sin_verificar", "confirmado"}
    assert set(modelo.FUENTES_TEL) == {"tramites", "cedulas", "planilla", "panel", "reunion", "consultor"}
    assert modelo.CONFIANZA == {"tramites": 1, "cedulas": 2, "planilla": 3, "consultor": 3, "panel": 4, "reunion": 4,
                                "manual": 4}
    assert set(modelo.CAMPOS_PROCEDENCIA) == {"cedula", "tipo_documento", "sexo", "edad", "fecha_nacimiento", "correo",
                                              "direccion", "votacion", "estado_civil", "nivel_educativo",
                                              "situacion_laboral", "ocupacion"}
    assert modelo.CAMPOS_AVANCE == ("cedula", "telefono", "sexo", "edad", "direccion", "lugar", "ubicacion", "puesto",
                                    "mesa", "autorizacion", "correo", "estado_civil", "nivel_educativo",
                                    "situacion_laboral", "ocupacion", "personas_hogar", "jefe_hogar", "tenencia_vivienda",
                                    "estrato", "regimen_salud")
    assert set(modelo.ETIQUETAS_CAMPOS) >= set(modelo.CAMPOS_AVANCE)
    assert set(modelo.ACCIONES) >= {"crear", "editar", "telefono_agregar", "telefono_estado", "telefono_principal",
                                    "telefono_retirar", "autorizacion", "ubicar", "asistencia", "acercamiento",
                                    "actualizacion_atendida", "situacion", "no_disponible"}
    assert "asistencia" not in modelo.ACCIONES_EDICION and "crear" not in modelo.ACCIONES_EDICION
    assert modelo.ZONA.utcoffset(None) == timedelta(hours=-5)


def test_resultados_neutrales_y_efectivos():
    efectivos = {"contesto", "volver_llamar", "actualizo_datos", "pidio_informacion", "solicitud_derechos", "no_contactar"}
    sin_efecto = {"no_contesto", "buzon", "numero_equivocado", "numero_inexistente", "no_vive_aqui", "fallecio"}
    assert set(modelo.RESULTADOS) >= efectivos | sin_efecto
    assert modelo.EFECTIVOS >= efectivos and not modelo.EFECTIVOS & sin_efecto
    assert set(modelo.SIN_EXITO) == {"no_contesto", "buzon"}
    assert modelo.etiqueta_resultado("contesto", "llamada") == "Contestó"
    assert modelo.etiqueta_resultado("contesto", "visita") == "Atendió"
    assert modelo.etiqueta_resultado("no_contesto", "visita") == "No estaba"
    assert modelo.etiqueta_resultado("no_contactar", "visita") == "Rechazó"


def test_ajustes_por_defecto():
    a = modelo.AJUSTES_POR_DEFECTO
    assert a["contactar_pendientes"] is False and a["sensibles_activos"] is False
    assert (a["dias_entre_intentos"], a["max_intentos_sin_exito"], a["dias_reintento_dato"]) == (2, 4, 90)
    assert a["eleccion_vigente"] == ELECCION and a["tope_cedulas_dictadas"] == 20
    assert a["presupuesto_diario"] == {"planillero": 1000, "consultor": 300}
    assert a["sesion"] == {"horas_max": 10, "inactividad_min": 60, "max_por_usuario": 2}
    assert a["horario"]["domingo"] is False and a["compromiso_version"]


def test_leer_ajustes_combina_con_los_valores_por_defecto(bases):
    db = bases()
    a = modelo.leer_ajustes(db)
    a["horario"]["semana"][0] = "00:00"
    assert modelo.AJUSTES_POR_DEFECTO["horario"]["semana"][0] == "07:00"  # devuelve una copia
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"dias_entre_intentos": 3, "sesion.horas_max": 8}}, upsert=True)
    a = modelo.leer_ajustes(db)
    assert a["dias_entre_intentos"] == 3
    assert a["sesion"] == {"horas_max": 8, "inactividad_min": 60, "max_por_usuario": 2}
    assert a["presupuesto_diario"] == {"planillero": 1000, "consultor": 300} and "_id" not in a


def test_modelo_js_trae_las_mismas_etiquetas():
    js = (RAIZ / "web" / "js" / "modelo.js").read_text(encoding="utf-8")
    m = re.search(r"export const CATALOGOS = (\{.*?\});\n// catalogos:fin", js, re.S)
    assert m, "web/js/modelo.js debe traer el bloque CATALOGOS entre las marcas"
    en_js = json.loads(m.group(1))
    en_py = json.loads(json.dumps(modelo.CATALOGOS_WEB, ensure_ascii=False))
    paso0 = {"SEXOS", "TIPOS_DOCUMENTO", "NIVELES", "ESTADOS_CIVILES", "SITUACIONES_LABORALES", "TENENCIAS",
             "REGIMENES_SALUD", "RANGOS_EDAD", "SENSIBLES", "NOMBRES_ROL", "ESTADOS_AUTORIZACION", "MEDIOS_AUTORIZACION",
             "MEDIOS_POR_ROL", "CANALES_AUTORIZACION", "CANALES_IMPLICITOS", "CANALES", "RESULTADOS", "SIN_EXITO",
             "FRANJAS", "ESTADOS_ABORDAJE", "SITUACIONES", "MOTIVOS_ACTUALIZACION", "CAMPOS_NO_DISPONIBLE",
             "MOTIVOS_NO_DISPONIBLE", "ESTADOS_TELEFONO", "USABLES", "TIPOS_TELEFONO", "ESTADOS_VOTACION", "DONDE_VOTA",
             "ETIQUETAS_CAMPOS", "CAMPOS_FALTAN"}
    assert paso0 <= set(en_py) and paso0 <= set(en_js)
    for k in set(en_js) & set(en_py):
        assert en_js[k] == en_py[k], k
    exportados = re.search(r"export const \{([^}]*)\} = CATALOGOS;", js)
    assert exportados and paso0 <= {x.strip() for x in exportados.group(1).split(",") if x.strip()}


@pytest.mark.skipif(shutil.which("node") is None, reason="sin Node para correr web/js/modelo.js")
def test_modelo_js_marcable_y_usable():
    codigo = ("import * as m from './web/js/modelo.js';"
              "console.log(JSON.stringify([m.marcable('8612345'), m.marcable('3001112233'), m.marcable('604 861 2345'),"
              "m.esUsable({estado: 'retirado'}), m.esUsable({numero: '3001112233'}), m.esUsable({no_contactar: true}),"
              "m.etiquetaResultado('contesto', 'visita')]))")
    r = subprocess.run(["node", "--input-type=module", "-e", codigo], cwd=RAIZ, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == ["6048612345", "3001112233", "6048612345", False, True, False, "Atendió"]


# ───────────────────────────── Fechas, edad y menores ─────────────────────────────

def test_fecha_valida_nunca_lanza():
    assert modelo.fecha_valida("1990-06-30") == date(1990, 6, 30)
    assert modelo.fecha_valida(date(2000, 1, 2)) == date(2000, 1, 2)
    for malo in ("1990-06-31", "1985-02-30", "1990-13-01", "0000-01-01", "19900630", "30/06/1990", "1990-06-3", "",
                 None, 1990, [], {"a": 1}):
        assert modelo.fecha_valida(malo) is None, malo


def test_edad_efectiva_con_fecha_imposible():
    # «1990-06-31» no existe: cuenta la edad declarada, más los años desde que se declaró
    assert modelo.edad_efectiva({"fecha_nacimiento": "1990-06-31", "edad": 30, "edad_ref": "2020-11-04"}, HOY) == 36
    assert modelo.edad_efectiva({"fecha_nacimiento": "1990-06-31"}, HOY) is None
    assert modelo.edad_efectiva({"fecha_nacimiento": "1990-06-30", "edad": 99}, HOY) == 36  # la fecha válida manda
    assert modelo.edad_efectiva({"fecha_nacimiento": "1990-11-05"}, HOY) == 35  # cumple mañana
    assert modelo.edad_efectiva({"edad": 40, "creado_en": "2024-01-15T10:00:00+00:00"}, HOY) == 42
    assert modelo.edad_efectiva({"edad": 40}, HOY) == 40
    assert modelo.edad_efectiva({}, HOY) is None


def test_calcular_nac():
    assert modelo.calcular_nac({"fecha_nacimiento": "1984-02-29", "edad": 7}) == {
        "nac_aprox": "1984-02-29", "nac_exacta": True, "nac_base": {"edad": 7, "fecha": "1984-02-29"}}
    aprox = modelo.calcular_nac({"edad": 40, "edad_ref": "2026-11-04"})
    assert aprox == {"nac_aprox": (date(1986, 11, 4) - timedelta(days=182)).isoformat(), "nac_exacta": False,
                     "nac_base": {"edad": 40, "fecha": None}}
    assert modelo.calcular_nac({"fecha_nacimiento": "1990-06-31"}) == {
        "nac_aprox": None, "nac_exacta": False, "nac_base": {"edad": None, "fecha": "1990-06-31"}}
    sin_ref = modelo.calcular_nac({"edad": 10, "creado_en": "2020-02-29T12:00:00+00:00"})
    assert sin_ref["nac_aprox"] == (date(2010, 2, 28) - timedelta(days=182)).isoformat()


@pytest.mark.parametrize("edad, rango", [
    (0, "<18"), (17, "<18"), (18, "18-24"), (24, "18-24"), (25, "25-34"), (34, "25-34"), (35, "35-44"), (44, "35-44"),
    (45, "45-54"), (54, "45-54"), (55, "55-64"), (64, "55-64"), (65, "65+"), (120, "65+"), (None, None), (-1, None),
])
def test_rango_edad_en_los_limites(edad, rango):
    assert modelo.rango_edad(edad) == rango
    assert rango is None or rango in modelo.RANGOS_EDAD


def test_es_menor_y_adulto_conocido():
    assert modelo.es_menor({"tipo_documento": "TI"}, HOY)  # TI sin edad
    assert modelo.es_menor({"tipo_documento": "TI", "edad": 30}, HOY)
    assert not modelo.es_menor({"tipo_documento": "CC"}, HOY)
    assert modelo.es_menor({"fecha_nacimiento": "2008-11-05"}, HOY)  # cumple 18 mañana
    assert not modelo.es_menor({"fecha_nacimiento": "2008-11-04"}, HOY)  # hoy cumple 18
    assert modelo.es_menor({"edad": 17, "edad_ref": "2026-11-04"}, HOY)
    assert not modelo.es_menor({"nac_aprox": "1980-01-01"}, HOY)
    # Edad desconocida: no es menor, pero tampoco adulto conocido
    assert not modelo.es_menor({}, HOY) and not modelo.es_adulto_conocido({}, HOY)
    assert modelo.es_adulto_conocido({"fecha_nacimiento": "2008-11-04"}, HOY)
    assert modelo.es_adulto_conocido({"tipo_documento": "CC"}, HOY)
    assert modelo.es_adulto_conocido({"mayor_declarado": True}, HOY)
    assert not modelo.es_adulto_conocido({"tipo_documento": "TI", "mayor_declarado": True}, HOY)
    assert not modelo.es_adulto_conocido({"fecha_nacimiento": "2010-01-01", "tipo_documento": "CC"}, HOY)


def test_filtros_de_edad_y_vigencia_coinciden_con_sus_gemelos(bases):
    db = bases()
    casos = [
        {"tipo_documento": "TI"}, {"tipo_documento": "TI", "edad": 30}, {"tipo_documento": "CC"},
        {"edad": 17, "edad_ref": "2026-11-04"}, {"edad": 18, "edad_ref": "2026-11-04"}, {"fecha_nacimiento": "2008-11-05"},
        {"fecha_nacimiento": "2008-11-04"}, {"fecha_nacimiento": "1990-06-31"}, {"mayor_declarado": True}, {},
        {"edad": 40, "mayor_declarado": True}, {"fecha_nacimiento": "2012-05-20", "tipo_documento": "CC"},
        {"situacion": None}, {"situacion": {"estado": "activa"}}, {"situacion": {"estado": "fallecida"}},
        {"situacion": {"estado": "no_reside", "confirmada": False}}, {"eliminado": True}, {"fusionada_en": 3},
    ]
    docs = []
    for i, c in enumerate(casos, 1):
        d = {"_id": i, **c}
        if "edad" in c or "fecha_nacimiento" in c:
            d.update(modelo.calcular_nac(d, HOY))
        docs.append(d)
    db.personas.insert_many(copy.deepcopy(docs))

    def ids(q):
        return {d["_id"] for d in db.personas.find(q, {"_id": 1})}

    assert ids(modelo.filtro_menor(HOY)) == {d["_id"] for d in docs if modelo.es_menor(d, HOY)} == {1, 2, 4, 6, 12}
    assert ids(modelo.filtro_adulto_conocido(HOY)) == {d["_id"] for d in docs if modelo.es_adulto_conocido(d, HOY)}
    assert ids(modelo.filtro_adulto_conocido(HOY)) == {3, 5, 7, 9, 11}
    vigentes = {d["_id"] for d in docs if not d.get("eliminado") and d.get("fusionada_en") is None
                and (d.get("situacion") or {}).get("estado") in (None, "activa")}
    assert ids(modelo.filtro_vigente()) == vigentes and not {15, 16, 17, 18} & vigentes
    q = modelo.filtro_vigente()
    q["x"] = 1
    assert "x" not in modelo.filtro_vigente() and "x" not in bd.ACTIVA


def test_punto():
    assert modelo.punto(7.0062, -73.9112) == {"type": "Point", "coordinates": [-73.9112, 7.0062]}
    assert modelo.punto(7.0, None) is None and modelo.punto(None, -73.9) is None
    assert modelo.punto(4.6, -74.08) is None  # fuera de Yondó
    assert modelo.punto("7.0", "-73.9") is None and modelo.punto(True, -73.9) is None
    assert modelo.punto(float("nan"), -73.9) is None


# ───────────────────────────── Teléfonos ─────────────────────────────

def test_tipo_y_forma_del_telefono():
    assert modelo.tipo_telefono("3001112233") == "celular"
    assert modelo.tipo_telefono("8612345") == "fijo" and modelo.tipo_telefono("6048612345") == "fijo"
    assert modelo.tipo_telefono(None) is None
    t = modelo.telefono_nuevo("3001112233", "planilla", "2026-11-02", agregado_por=5)
    assert set(t) == set(modelo.CAMPOS_TELEFONO)
    assert t["fuentes"] == ["planilla"] and t["primera_vez"] == t["ultima_vez"] == "2026-11-02"
    assert t["estado"] == "sin_verificar" and t["no_contactar"] is False and t["agregado_por"] == 5
    with pytest.raises(ValueError):
        modelo.telefono_nuevo("3001112233", color="rojo")


def test_unir_telefonos_no_modifica_no_duplica_y_no_reactiva():
    lista = [T("3001112233", "tramites", ultima_vez="2025-06-02"), T("3014445566", "cedulas", estado="retirado")]
    nuevos = [T("3014445566", "planilla", ultima_vez="2026-11-02"), T("3001112233", "planilla", ultima_vez="2026-11-02"),
              T("3027778899", "planilla"), "3027778899"]
    antes, antes_nuevos = copy.deepcopy(lista), copy.deepcopy(nuevos)
    r = modelo.unir_telefonos(lista, nuevos)
    assert lista == antes and nuevos == antes_nuevos
    assert [t["numero"] for t in r] == ["3001112233", "3014445566", "3027778899"]
    assert r[0]["fuentes"] == ["tramites", "planilla"] and r[0]["ultima_vez"] == "2026-11-02"
    assert r[1]["estado"] == "retirado" and r[1]["fuentes"] == ["cedulas", "planilla"]  # no se reactiva
    assert r[2]["fuentes"] == ["planilla"] and r[2]["estado"] == "sin_verificar"
    assert modelo.derivar_telefonos(r) == {"telefono": "3001112233", "telefono2": "3027778899"}
    assert modelo.unir_telefonos(r, nuevos) == r  # volver a unir lo mismo no cambia nada
    r[0]["fuentes"].append("otra")
    assert lista == antes  # el resultado no comparte listas con la entrada
    al_frente = modelo.unir_telefonos(lista, ["3039990000", "3001112233"], al_frente=True)
    assert [t["numero"] for t in al_frente] == ["3039990000", "3001112233", "3014445566"]
    assert modelo.unir_telefonos(None, []) == []


def test_usables_y_derivados():
    lista = [T("3001110001", estado="equivocado"), T("3001110002", no_contactar=True), T("3001110003", estado="confirmado"),
             T("3001110004"), T("3001110005", estado="no_usa"), T("3001110006", estado="inexistente"),
             T("3001110007", estado="retirado")]
    assert [t["numero"] for t in modelo.usables(lista)] == ["3001110003", "3001110004"]
    assert modelo.derivar_telefonos(lista) == {"telefono": "3001110003", "telefono2": "3001110004"}
    assert modelo.derivar_telefonos([]) == {"telefono": None, "telefono2": None}
    assert modelo.usables([{"numero": "3001110008"}])  # sin estado cuenta como sin verificar
    assert modelo.telefonos_de({"telefono": "3001110009", "telefono2": None}) == [
        {"numero": "3001110009", "tipo": None, "fuentes": ["panel"], "estado": "sin_verificar", "no_contactar": False}]
    assert modelo.telefonos_de({"telefonos": [], "telefono": "3001110009"}) == []  # la lista manda


def test_cambiar_telefono_y_principal():
    lista = [T("3001110001"), T("3001110002", estado="confirmado")]
    r = modelo.cambiar_telefono(lista, "3001110001", {"estado": "equivocado", "estado_por": 7})
    assert r[0]["estado"] == "equivocado" and r[0]["estado_por"] == 7 and lista[0]["estado"] == "sin_verificar"
    assert modelo.derivar_telefonos(r)["telefono"] == "3001110002"
    assert [t["numero"] for t in modelo.hacer_principal(lista, "3001110002")] == ["3001110002", "3001110001"]
    with pytest.raises(ValueError):
        modelo.cambiar_telefono(lista, "3001110001", {"numero": "3009999999"})
    with pytest.raises(ValueError):
        modelo.cambiar_telefono(lista, "3001110001", {"estado": "perdido"})


def test_telefonos_iniciales_conserva_telefono_tal_cual():
    p = {"telefono": "1111111", "telefono2": None,
         "tramites": [{"fecha": "2025-06-02", "telefono": "3001112233;3014445566"},
                      {"fecha": "2025-07-03", "telefono": "3014445566"}, {"fecha": "2025-08-01", "telefono": "1111111"}],
         "origen": [{"fuente": "cedulas", "clave": "90000001", "importacion_id": 4,
                     "datos": {"telefonos": ["3001112233", "3045556677"]}},
                    {"fuente": "planilla", "clave": "x", "datos": {"telefonos": ["3990000000"]}}]}
    antes = copy.deepcopy(p)
    r = modelo.telefonos_iniciales(p, {4: "2026-01-10"})
    assert p == antes
    assert [t["numero"] for t in r] == ["1111111", "3014445566", "3001112233", "3045556677"]
    assert all(set(t) == set(modelo.CAMPOS_TELEFONO) and t["estado"] == "sin_verificar" for t in r)
    por = {t["numero"]: t for t in r}
    assert por["1111111"]["fuentes"] == ["tramites"]  # también aparece en un trámite
    assert por["3014445566"]["fuentes"] == ["tramites"]
    assert (por["3014445566"]["primera_vez"], por["3014445566"]["ultima_vez"]) == ("2025-06-02", "2025-07-03")
    assert set(por["3001112233"]["fuentes"]) == {"tramites", "cedulas"} and por["3001112233"]["ultima_vez"] == "2026-01-10"
    assert por["3045556677"]["fuentes"] == ["cedulas"]
    # telefono no cambia (aunque hoy tx.telefonos lo rechace) y telefono2 vacío se llena
    assert modelo.derivar_telefonos(r) == {"telefono": "1111111", "telefono2": "3014445566"}
    r2 = modelo.telefonos_iniciales({"telefono": "300 111 2233", "telefono2": "8612345", "tramites": [], "origen": []})
    assert [(t["numero"], t["fuentes"]) for t in r2] == [("300 111 2233", ["panel"]), ("8612345", ["panel"])]
    assert modelo.derivar_telefonos(r2) == {"telefono": "300 111 2233", "telefono2": "8612345"}
    assert modelo.telefonos_iniciales({}) == []


def _aplicar(db, docs, actualizacion):
    db.personas.delete_many({})
    db.personas.insert_many(copy.deepcopy(docs))
    db.personas.update_many({}, actualizacion)
    return {d["_id"]: d for d in db.personas.find()}


def test_expresiones_de_telefonos_igual_que_sus_gemelos(bases):
    db = bases()
    docs = [
        {"_id": 1, "telefonos": [T("3001112233", "tramites", ultima_vez="2025-06-02"), T("3014445566", "cedulas", estado="retirado"),
                                 T("8612345", "panel", estado="confirmado")], "telefono": "3001112233", "telefono2": "8612345"},
        {"_id": 2, "telefono": "3027778899", "telefono2": "3039990000"},  # ficha vieja sin la lista
        {"_id": 3, "telefono": None, "telefono2": None},
    ]
    # «$telefono» prueba que un valor de fuera no se lee como campo
    nuevos = [T("3014445566", "planilla", ultima_vez="2026-11-02"), T("3027778899", "tramites", ultima_vez="2025-01-01"),
              T("3045556677", "planilla"), T("$telefono", "planilla"), "3045556677"]
    casos = [
        (modelo.expr_unir_telefonos(nuevos), lambda l: modelo.unir_telefonos(l, nuevos)),
        (modelo.expr_unir_telefonos(nuevos, al_frente=True), lambda l: modelo.unir_telefonos(l, nuevos, al_frente=True)),
        (modelo.expr_estado_telefono("3014445566", {"estado": "confirmado", "estado_por": 5, "nota": "$nota"}),
         lambda l: modelo.cambiar_telefono(l, "3014445566", {"estado": "confirmado", "estado_por": 5, "nota": "$nota"})),
        (modelo.expr_estado_telefono("3027778899", {"no_contactar": True}),
         lambda l: modelo.cambiar_telefono(l, "3027778899", {"no_contactar": True})),
        (modelo.expr_principal("8612345"), lambda l: modelo.hacer_principal(l, "8612345")),
        (modelo.expr_principal("3039990000"), lambda l: modelo.hacer_principal(l, "3039990000")),
        ([modelo.ETAPA_DERIVAR_TELEFONOS], lambda l: l if l else None),
    ]
    for actualizacion, gemelo in casos:
        hechos = _aplicar(db, docs, actualizacion)
        for d in docs:
            lista = gemelo(modelo.telefonos_de(d))
            h = hechos[d["_id"]]
            if lista is not None and (actualizacion[0] is not modelo.ETAPA_DERIVAR_TELEFONOS):
                assert h["telefonos"] == lista, (actualizacion, d["_id"])
            assert {k: h.get(k) for k in ("telefono", "telefono2")} == modelo.derivar_telefonos(modelo.telefonos_de(h)), d
    # Lo derivado sale de la lista: si el principal pasa a equivocado, toma su lugar el siguiente usable (no el retirado)
    hechos = _aplicar(db, docs, modelo.expr_estado_telefono("3001112233", {"estado": "equivocado"}))
    assert (hechos[1]["telefono"], hechos[1]["telefono2"]) == ("8612345", None)


# ───────────────────────────── Puesto y mesa ─────────────────────────────

PUESTOS = [  # catálogo DIVIPOLE 2026 (público), con ids inventados
    {"_id": 1, "codigo": "00-01", "nombre": "IE LUIS EDUARDO DIAZ SECCION PRIMARIA", "alias": [],
     "alias_ambiguos": ["CABECERA MUNICIPAL", "PUESTO CABECERA MUNICIPAL"], "mesas": 35},
    {"_id": 2, "codigo": "00-02", "nombre": "COLISEO BENITO ARIAS", "alias": [],
     "alias_ambiguos": ["CABECERA MUNICIPAL", "PUESTO CABECERA MUNICIPAL"], "mesas": 4},
    {"_id": 3, "codigo": "99-25", "nombre": "C.E.R CUATRO BOCAS", "alias": ["CUATRO BOCAS"], "mesas": 1},
    {"_id": 4, "codigo": "99-32", "nombre": "I.E.R. ALTO CIMITARRA", "alias": ["SAN FRANCISCO", "C.E.R ALTO CIMITARRA"],
     "mesas": 2},
    {"_id": 5, "codigo": "99-50", "nombre": "C.E.R CAÑO BLANCO", "alias": ["CAÑO BLANCO"], "mesas": 1},
    {"_id": 6, "codigo": "99-60", "nombre": "I.E.R. SAN LUIS BELTRAN", "alias": ["SAN LUIS BELTRAN"], "mesas": 2},
    {"_id": 7, "codigo": "99-65", "nombre": "I.E.R. SAN MIGUEL DEL TIGRE", "alias": ["SAN MIGUEL DEL TIGRE"], "mesas": 5},
]


@pytest.mark.parametrize("v, n", [
    ("Mesa # 9", 9), ("MESA 12", 12), ("009", 9), (7, 7), (7.0, 7), ("12.0", 12), ("Mesa uno", None), ("1234", None),
    ("", None), (None, None), (True, None),
])
def test_normalizar_mesa(v, n):
    assert modelo.normalizar_mesa(v) == n


@pytest.mark.parametrize("texto, esperado", [
    ("SAN MIGUEL DEL TIGRE", (7, False)), ("I.E.R. San Miguel del Tigre", (7, False)),
    ("CABECERA MUNICIPAL", (None, True)), ("PUESTO CABECERA MUNICIPAL", (None, True)),
    ("LUIS", (None, False)), ("SAN", (None, False)), ("SAN MIGUEL", (None, False)),
    ("SAN LUIS BELTRAN", (6, False)), ("IE LUIS EDUARDO DIAZ", (1, False)), ("C.E.R CAÑO BLANCO", (5, False)),
    ("SAN FRANCISCO", (4, False)), ("COLISEO BENITO ARIAS", (2, False)), ("ESCUELA RURAL", (None, False)),
    ("", (None, False)), (None, (None, False)),
])
def test_reconocer_puesto(texto, esperado):
    assert modelo.reconocer_puesto(texto, PUESTOS) == esperado


def test_reconocer_puesto_inactivo_o_repetido():
    inactivo = [{**PUESTOS[6], "activo": False}]
    assert modelo.reconocer_puesto("SAN MIGUEL DEL TIGRE", inactivo) == (None, False)
    dos = [PUESTOS[6], {**PUESTOS[6], "_id": 70, "codigo": "99-66"}]
    assert modelo.reconocer_puesto("SAN MIGUEL DEL TIGRE", dos) == (None, True)


def test_derivar_votacion_igual_que_la_etapa(bases):
    db = bases()
    votaciones = [
        {"puesto_id": 7, "puesto_nombre": "I.E.R. SAN MIGUEL DEL TIGRE", "puesto_texto": None, "mesa": 2, "mesa_texto": None},
        {"puesto_id": None, "puesto_nombre": None, "puesto_texto": "ESCUELA VIEJA", "mesa": None, "mesa_texto": "Mesa # 3"},
        {"puesto_id": 1, "puesto_nombre": "IE LUIS EDUARDO DIAZ SECCION PRIMARIA", "mesa": 40, "mesa_texto": "Mesa 40"},
        {"donde": "otro_municipio", "municipio": "MUNICIPIO INVENTADO"},
        {"donde": "otro_municipio", "municipio": None},
        {"donde": "no_inscrito"},
    ]
    docs = [{"_id": i, "votacion": v, "puesto_votacion": "VIEJO", "mesa": "Mesa # 1"} for i, v in enumerate(votaciones, 1)]
    docs += [{"_id": 10, "votacion": None, "puesto_votacion": "CABECERA MUNICIPAL", "mesa": "Mesa # 9"},
             {"_id": 11, "puesto_votacion": "OTRO TEXTO", "mesa": None}]
    hechos = _aplicar(db, docs, [modelo.ETAPA_DERIVAR_VOTACION])
    for d in docs:
        esperado = {"puesto_votacion": d.get("puesto_votacion"), "mesa": d.get("mesa"), **modelo.derivar_votacion(d.get("votacion"))}
        assert {k: hechos[d["_id"]].get(k) for k in ("puesto_votacion", "mesa")} == esperado, d
    assert modelo.derivar_votacion(votaciones[0]) == {"puesto_votacion": "I.E.R. SAN MIGUEL DEL TIGRE", "mesa": "2"}
    assert modelo.derivar_votacion(votaciones[1]) == {"puesto_votacion": "ESCUELA VIEJA", "mesa": "Mesa # 3"}
    assert modelo.derivar_votacion(votaciones[3])["puesto_votacion"] == "Otro municipio: MUNICIPIO INVENTADO"
    assert modelo.derivar_votacion(None) == {}


def test_estado_de_votacion_efectivo_igual_que_su_filtro(bases):
    db = bases()
    votaciones = [None, {"eleccion": ELECCION, "estado": "verificado"}, {"eleccion": ELECCION, "estado": "sin_verificar"},
                  {"eleccion": ELECCION, "estado": "por_confirmar"}, {"eleccion": None, "estado": "verificado"},
                  {"eleccion": "2022-presidencial", "estado": "sin_verificar"}, {"estado": "verificado"},
                  {"eleccion": ELECCION}, {"eleccion": ELECCION, "estado": "verificado", "donde": "no_inscrito"}]
    db.personas.insert_many([{"_id": i, "votacion": v} for i, v in enumerate(votaciones)] + [{"_id": 99}])
    for estado in modelo.ESTADOS_VOTACION:
        en_base = {d["_id"] for d in db.personas.find(modelo.filtro_estado_votacion(estado, ELECCION), {"_id": 1})}
        assert en_base == {i for i, v in enumerate(votaciones) if modelo.estado_votacion_efectivo(v, ELECCION) == estado}
    assert modelo.estado_votacion_efectivo(votaciones[4], ELECCION) == "por_confirmar"  # elección desconocida
    assert modelo.estado_votacion_efectivo(None, ELECCION) is None
    with pytest.raises(ValueError):
        modelo.filtro_estado_votacion("otro", ELECCION)


# ───────────────────────────── Abordaje y autorización ─────────────────────────────

def A(ts, resultado, canal="llamada", **k):
    return {"ts": ts, "resultado": resultado, "canal": canal, "uid": 7, "usuario": "consultor7", **k}


def test_resumen_abordaje():
    assert modelo.resumen_abordaje([]) is None
    assert modelo.resumen_abordaje([], consentimiento="no")["estado"] == "no_contactar"
    r = modelo.resumen_abordaje([A("2026-11-01T14:00:00+00:00", "no_contesto"), A("2026-11-02T14:00:00+00:00", "buzon"),
                                 A("2026-11-03T02:00:00+00:00", "numero_equivocado")])
    assert (r["n"], r["efectivos"], r["intentos_sin_exito"], r["estado"]) == (3, 0, 2, "intentado")
    assert r["ultimo_resultado"] == "numero_equivocado" and r["ultimo_fecha"] == "2026-11-02"  # 21:00 en Colombia
    assert (r["ultimo_uid"], r["ultimo_usuario"], r["ultimo_canal"]) == (7, "consultor7", "llamada")
    # Un acercamiento efectivo vuelve a cero los intentos sin éxito; los anulados no cuentan
    r = modelo.resumen_abordaje([A("2026-11-01T14:00:00+00:00", "no_contesto"), A("2026-11-02T14:00:00+00:00", "contesto"),
                                 A("2026-11-03T14:00:00+00:00", "no_contesto"),
                                 A("2026-11-04T14:00:00+00:00", "contesto", anulado=True)])
    assert (r["n"], r["efectivos"], r["intentos_sin_exito"], r["estado"]) == (3, 1, 1, "contactado")
    assert r["ultimo_resultado"] == "no_contesto"
    # «Volver a llamar»: el próximo sale del último acercamiento
    r = modelo.resumen_abordaje([A("2026-11-02T14:00:00+00:00", "volver_llamar", proximo="2026-11-06", proximo_franja="tarde",
                                   fecha="2026-11-02")])
    assert (r["proximo"], r["proximo_franja"], r["ultimo_fecha"], r["estado"]) == ("2026-11-06", "tarde", "2026-11-02",
                                                                                     "contactado")
    # Mismo instante: manda el _id mayor
    r = modelo.resumen_abordaje([{**A("2026-11-02T14:00:00+00:00", "contesto"), "_id": 9},
                                 {**A("2026-11-02T14:00:00+00:00", "buzon"), "_id": 3}])
    assert r["ultimo_resultado"] == "contesto"
    # Reunión: cuenta como abordaje
    assert modelo.resumen_abordaje([A("2026-11-02T14:00:00+00:00", "contesto", canal="reunion", auto=True)])["estado"] == "contactado"


def test_resumen_abordaje_no_contactar():
    ts = "2026-11-02T14:00:00+00:00"
    assert modelo.resumen_abordaje([A(ts, "no_contactar", alcance="numero")])["estado"] == "contactado"
    assert modelo.resumen_abordaje([A(ts, "no_contactar", alcance="persona")])["estado"] == "no_contactar"
    assert modelo.resumen_abordaje([A(ts, "no_contactar")])["estado"] == "no_contactar"  # sin alcance: la persona
    assert modelo.resumen_abordaje([A(ts, "contesto")], consentimiento="no")["estado"] == "no_contactar"


def E(_id, ts, estado, medio="escrito", **k):
    return {"_id": _id, "ts": ts, "estado": estado, "medio": medio, **k}


def test_consentimiento_vigente_canales():
    vacio = modelo.consentimiento_vigente([])
    assert vacio["consentimiento"] == "pendiente" and vacio["consentimiento_canales"] == []
    assert vacio["contacto_habilitado"] is False and vacio["autorizacion_ultima"] is None
    # Canales vacíos: ningún canal
    r = modelo.consentimiento_vigente([E(1, "2026-11-04T15:00:00+00:00", "si", canales=[], mayor_declarado=True)])
    assert r["consentimiento"] == "si" and r["consentimiento_canales"] == [] and r["contacto_habilitado"] is True
    assert r["mayor_declarado"] is True and r["autorizacion_ultima"] == {"id": 1, "estado": "si"}
    # Los implícitos (migrado o PATCH heredado de A) valen como llamada, WhatsApp y SMS: nunca grupos, visita ni correo
    for medio in ("migrado", "panel"):
        r = modelo.consentimiento_vigente([E(2, "2026-11-04T15:00:00+00:00", "si", medio=medio, canales=[],
                                             canales_implicitos=True)])
        assert set(r["consentimiento_canales"]) == {"llamada", "whatsapp", "sms"}
    r = modelo.consentimiento_vigente([E(3, "2026-11-04T15:00:00+00:00", "si", canales=["grupos", "llamada", "fax"])])
    assert set(r["consentimiento_canales"]) == {"grupos", "llamada"}


def test_consentimiento_vigente_estado_fecha_y_habilitado():
    # Manda el último por (ts, _id); revocada cuenta como «no»
    ev = [E(1, "2026-11-01T15:00:00+00:00", "si", canales=["llamada"]), E(5, "2026-11-02T15:00:00+00:00", "revocada"),
          E(4, "2026-11-02T15:00:00+00:00", "si", canales=["whatsapp"])]
    r = modelo.consentimiento_vigente(ev)
    assert r["consentimiento"] == "no" and r["consentimiento_canales"] == [] and r["contacto_habilitado"] is False
    assert r["autorizacion_ultima"] == {"id": 5, "estado": "revocada"}
    # Fecha local del evento (03:00 UTC es el día anterior en Colombia) o la declarada
    r = modelo.consentimiento_vigente([E(1, "2026-11-05T03:00:00+00:00", "si", canales=["llamada"])])
    assert r["consentimiento_fecha"] == "2026-11-04" and r["consentimiento_medio"] == "escrito"
    r = modelo.consentimiento_vigente([E(1, "2026-11-05T03:00:00+00:00", "si", fecha_declarada="2024-06-30")])
    assert r["consentimiento_fecha"] == "2024-06-30"
    # Declarado en planilla: vale como «si» pero no habilita la cola hasta que A lo confirme (A es el uid 0)
    planilla = E(1, "2026-11-04T15:00:00+00:00", "si", medio="declarado_planilla", canales=["llamada"])
    assert modelo.consentimiento_vigente([planilla])["contacto_habilitado"] is False
    assert modelo.consentimiento_vigente([{**planilla, "confirmada_por": 0}])["contacto_habilitado"] is True
    # Pendiente (corrección de A)
    r = modelo.consentimiento_vigente([E(1, "2026-11-01T15:00:00+00:00", "si", mayor_declarado=True),
                                       E(2, "2026-11-02T15:00:00+00:00", "pendiente", medio="panel")])
    assert r["consentimiento"] == "pendiente" and r["mayor_declarado"] is True


def test_consentimiento_vigente_sensibles():
    si = E(1, "2026-11-01T15:00:00+00:00", "si", canales=["llamada"], sensibles=["etnia"])
    telefono = E(2, "2026-11-02T15:00:00+00:00", "si", medio="verbal_telefono", canales=["llamada"], sensibles=["victima"])
    assert modelo.consentimiento_vigente([si, telefono])["sensibles_autorizados"] == ["etnia"]
    con_evidencia = {**telefono, "evidencia": "Respondió SÍ al aviso por WhatsApp"}
    assert modelo.consentimiento_vigente([si, con_evidencia])["sensibles_autorizados"] == ["etnia", "victima"]
    otra_vez = [si, E(3, "2026-11-03T15:00:00+00:00", "no"), E(4, "2026-11-04T15:00:00+00:00", "si", canales=["llamada"])]
    assert modelo.consentimiento_vigente(otra_vez)["sensibles_autorizados"] == []


# ───────────────────────────── Avance, faltantes y nombre ─────────────────────────────

def test_completados_canonicos():
    antes = {"telefono": None, "votacion": None, "consentimiento": "pendiente", "personas_hogar": 0}
    despues = {"cedula": "90000101", "telefonos": [T("3001112233")], "votacion": {"puesto_id": 3, "mesa": 2}, "lugar_id": 4,
               "fecha_nacimiento": "1979-03-14", "consentimiento": "si", "estrato": 0, "jefe_hogar": False,
               "personas_hogar": 0, "lat": 7.0, "lon": -73.9}
    assert modelo.completados(antes, despues) == ["cedula", "telefono", "edad", "lugar", "ubicacion", "puesto", "mesa",
                                                  "autorizacion", "jefe_hogar", "estrato"]
    assert modelo.completados(despues, despues) == []
    assert modelo.completados(None, {"nombre": "PERSONA INVENTADA"}) == []
    # Un número que no es usable no completa el teléfono; uno que ya había (ficha vieja) tampoco
    assert "telefono" not in modelo.completados({}, {"telefonos": [T("3001112233", estado="equivocado")]})
    assert "telefono" not in modelo.completados({"telefono": "3001112233"}, {"telefonos": [T("3001112233")]})
    # Puesto: escrito a mano o «no inscrito» completan; el puesto heredado ya contaba
    assert modelo.completados({}, {"votacion": {"puesto_texto": "ESCUELA VIEJA"}}) == ["puesto"]
    assert modelo.completados({}, {"votacion": {"donde": "no_inscrito"}}) == ["puesto"]
    assert modelo.completados({"puesto_votacion": "CABECERA MUNICIPAL"}, {"votacion": {"puesto_id": 1}}) == []
    # Una fecha imposible no es un dato de edad; la edad declarada sí
    assert modelo.completados({"fecha_nacimiento": "1990-06-31"}, {"fecha_nacimiento": "1990-06-31", "edad": 36}) == ["edad"]


def test_faltan_respeta_no_disponible_vigente():
    p = {"consentimiento": "pendiente", "no_disponible": {
        "cedula": {"motivo": "no_la_dio", "uid": 5, "ts": "2026-10-01T15:00:00+00:00"},
        "sexo": {"motivo": "no_sabe", "uid": 5, "ts": "2026-01-01T15:00:00+00:00"}}}
    assert modelo.faltan(p, HOY) == ["telefono", "sexo", "edad", "lugar", "puesto", "mesa", "direccion", "autorizacion"]
    completa = {"cedula": "90000101", "telefono": "3001112233", "sexo": "F", "edad": 40, "lugar_id": 1, "direccion": "CALLE 1",
                "votacion": {"puesto_id": 1, "mesa": 3}, "consentimiento": "no"}
    assert modelo.faltan(completa, HOY) == []


def test_claves_foneticas():
    assert modelo.claves_foneticas("YESICA DEL CARMEN") == modelo.claves_foneticas("JESSICA CARMEN")
    assert modelo.claves_foneticas("JHON") == modelo.claves_foneticas("JOHN")
    assert modelo.claves_foneticas("LEGUIZAMO") == modelo.claves_foneticas("LEGUISAMO")
    assert len(modelo.claves_foneticas("ZOILA ESPERANZA QUINTERO")) == 3
    assert modelo.claves_foneticas("") == [] and modelo.claves_foneticas(None) == []


# ───────────────────────────── Geometría ─────────────────────────────

CUADRO = [[-73.915, 7.002], [-73.905, 7.002], [-73.905, 7.012], [-73.915, 7.012]]


def _circulo(n, radio=0.005):
    return [[-73.91 + radio * math.cos(2 * math.pi * i / n), 7.0 + radio * math.sin(2 * math.pi * i / n)] for i in range(n)]


def test_validar_anillo_limpia_y_acepta():
    sucio = [[-73.9150000004, 7.002], [-73.915, 7.002], [-73.905, 7.002], [-73.905, 7.012], [-73.905, 7.012],
             [-73.915, 7.012], [-73.915, 7.002]]
    assert geometria.validar_anillo(sucio) == CUADRO
    assert geometria.validar_anillo([tuple(v) for v in CUADRO]) == CUADRO
    assert len(geometria.validar_anillo(_circulo(150))) == 150


@pytest.mark.parametrize("anillo", [
    [], None, "-73.9,7.0", [[-73.91, 7.0], [-73.90, 7.0]],
    [[-73.915, 7.002], [-73.905, 7.012], [-73.905, 7.002], [-73.915, 7.012]],  # lados cruzados (moño)
    [[-74.09, 4.6], [-74.08, 4.6], [-74.08, 4.61]],  # fuera de Yondó
    [[-73.91, 7.0], [-73.90999, 7.0], [-73.90999, 7.00001]],  # menos de 100 m²
    [[-74.5, 6.4], [-73.7, 6.4], [-73.7, 7.4], [-74.5, 7.4]],  # más de 4 000 km²
    _circulo(151), [[-73.91, 7.0], [-73.90, "7.0"], [-73.90, 7.01]], [[-73.91, 7.0], [-73.90, True], [-73.90, 7.01]],
    [[-73.91, 7.0], [-73.90, float("nan")], [-73.90, 7.01]], [[-73.91, 7.0, 1], [-73.90, 7.0], [-73.90, 7.01]],
])
def test_validar_anillo_rechaza(anillo):
    with pytest.raises(HTTPException) as e:
        geometria.validar_anillo(anillo)
    assert e.value.status_code == 422 and e.value.detail["codigo"] == "poligono" and e.value.detail["mensaje"]


def test_se_cruza():
    assert not geometria.se_cruza(CUADRO)
    assert geometria.se_cruza([CUADRO[0], CUADRO[2], CUADRO[1], CUADRO[3]])
    # Un lado que vuelve sobre el anterior (espiga) y dos lados que se tocan en un vértice (ocho)
    assert geometria.se_cruza([[-73.915, 7.002], [-73.905, 7.002], [-73.910, 7.002], [-73.910, 7.010]])
    assert geometria.se_cruza([[-73.92, 7.0], [-73.91, 7.005], [-73.92, 7.01], [-73.90, 7.01], [-73.91, 7.005], [-73.90, 7.0]])


def test_area_y_perimetro():
    k = math.pi / 180
    # Rectángulo de 0,01° × 0,01°: área esférica exacta R²·Δλ·(sen φ2 − sen φ1), y menos de 0,5 % de la plana local
    exacta = geometria.R_AREA ** 2 * (0.01 * k) * (math.sin(7.012 * k) - math.sin(7.002 * k))
    plana = (0.01 * k * geometria.R_AREA * math.cos(7.007 * k)) * (0.01 * k * geometria.R_AREA)
    assert geometria.area_m2(CUADRO) == pytest.approx(exacta, rel=1e-9)
    assert geometria.area_m2(CUADRO) == pytest.approx(plana, rel=0.005)
    # Un cuadrado de 1 km de lado (medido sobre la esfera del área)
    dlat = 1000 / geometria.R_AREA / k
    dlon = 1000 / (geometria.R_AREA * math.cos(7.0 * k)) / k
    km = [[-73.91, 7.0], [-73.91 + dlon, 7.0], [-73.91 + dlon, 7.0 + dlat], [-73.91, 7.0 + dlat]]
    assert geometria.area_m2(km) == pytest.approx(1e6, rel=0.005)
    # El sentido del recorrido y el vértice de cierre no cambian nada
    assert geometria.area_m2(CUADRO[::-1]) == pytest.approx(geometria.area_m2(CUADRO))
    assert geometria.area_m2(CUADRO + [CUADRO[0]]) == pytest.approx(geometria.area_m2(CUADRO))
    r = geometria.R_PERIMETRO
    esperado = 2 * 0.01 * k * r + 0.01 * k * r * (math.cos(7.002 * k) + math.cos(7.012 * k))
    assert geometria.perimetro_m(CUADRO) == pytest.approx(esperado, rel=1e-6)
    assert geometria.perimetro_m(CUADRO + [CUADRO[0]]) == pytest.approx(esperado, rel=1e-6)


def test_codificar_y_decodificar():
    texto = geometria.codificar(CUADRO)
    assert texto == "-73.915,7.002;-73.905,7.002;-73.905,7.012;-73.915,7.012"
    assert geometria.decodificar(texto) == CUADRO and geometria.decodificar(texto + ";") == CUADRO
    assert geometria.codificar([[-73.9123456789, 7.0]]) == "-73.912346,7"
    for malo in ("x,y", "1,2,3", "-73.9;7.0", "nan,7", "-73.9,inf", "-73.9," + "1" * 4000, None, 5):
        with pytest.raises(HTTPException) as e:
            geometria.decodificar(malo)
        assert e.value.status_code == 422 and e.value.detail["codigo"] == "poligono"


def test_a_geojson_sirve_para_geowithin(bases):
    db = bases()
    g = geometria.a_geojson(CUADRO)
    assert g["type"] == "Polygon" and g["coordinates"][0][0] == g["coordinates"][0][-1] and len(g["coordinates"][0]) == 5
    assert geometria.a_geojson(CUADRO + [CUADRO[0]]) == g
    db.personas.insert_many([{"_id": 1, "punto": modelo.punto(7.007, -73.91)}, {"_id": 2, "punto": modelo.punto(7.05, -73.91)},
                             {"_id": 3, "punto": None}])
    assert [d["_id"] for d in db.personas.find({"punto": {"$geoWithin": {"$geometry": g}}})] == [1]


# ───────────────────────────── Acceso ─────────────────────────────

def test_hashear_y_verificar_clave(monkeypatch):
    h = acceso.hashear_clave("una clave larga de prueba")
    assert h.startswith("scrypt$32768$8$1$") and len(h.split("$")) == 6
    assert h != acceso.hashear_clave("una clave larga de prueba")  # sal distinta cada vez
    assert acceso.verificar_clave(h, "una clave larga de prueba")
    assert not acceso.verificar_clave(h, "una clave larga de prueba ")
    for guardada in (None, "", "scrypt$1$1$1$00$00", "texto", h.replace("scrypt$32768", "scrypt$1024")):
        assert not acceso.verificar_clave(guardada, "una clave larga de prueba")
    # Sin clave guardada hace el mismo trabajo (no revela si el usuario existe)
    llamadas = []
    real = acceso.hashlib.scrypt
    monkeypatch.setattr(acceso.hashlib, "scrypt", lambda *a, **k: llamadas.append(k) or real(*a, **k))
    assert not acceso.verificar_clave(None, "otra clave cualquiera")
    assert len(llamadas) == 1 and (llamadas[0]["n"], llamadas[0]["r"], llamadas[0]["p"]) == (2 ** 15, 8, 1)


def test_scrypt_sin_turno_responde_503(monkeypatch):
    class Lleno:
        def acquire(self, timeout=None):
            return False

        def release(self):
            raise AssertionError("no se tomó el turno")

    monkeypatch.setattr(acceso, "_TURNOS", Lleno())
    with pytest.raises(HTTPException) as e:
        acceso.hashear_clave("una clave larga de prueba")
    assert e.value.status_code == 503 and e.value.headers["Retry-After"] == "2"


def test_clave_temporal_y_clave_nueva():
    claves = {acceso.clave_temporal() for _ in range(20)}
    assert len(claves) == 20 and all(len(c) == 12 and re.fullmatch(r"[A-Za-z0-9_-]+", c) for c in claves)
    for usuario, mala in (("ana.campo", "corta"), ("ana.campo", "Ana.Campo"), ("ana.campo123", "ANA.CAMPO123"),
                          ("luis", "1234567890"), ("luis", "Contraseña"), ("luis", "aaaaaaaaaaaa")):
        with pytest.raises(HTTPException) as e:
            acceso.validar_clave_nueva(usuario, mala)
        assert e.value.status_code == 422 and e.value.detail
    assert acceso.validar_clave_nueva("ana.campo", "tres palabras sueltas") is None


def test_mascaras():
    assert acceso.enmascarar_cedula("90000123") == "···123"
    assert acceso.enmascarar_cedula(90000123) == "···123"
    assert acceso.enmascarar_cedula(None) is None and acceso.enmascarar_cedula("") is None
    assert acceso.enmascarar_telefono("3001112233") == "···2233"
    assert acceso.enmascarar_telefono(None) is None


def test_roles_y_permisos():
    assert acceso.ROLES == {"admin", "coordinador", "planillero", "consultor"}  # adenda 1: rol coordinador
    assert acceso.PERMISOS["admin"] == frozenset({"*"})
    planillero = {"cuenta", "catalogos.ver", "insignias", "trabajo.ver", "personas.listar", "personas.buscar",
                  "personas.ver", "personas.crear", "personas.editar", "personas.parecidas", "personas.notas",
                  "personas.ubicar", "personas.telefonos", "personas.autorizacion", "personas.duplicado",
                  "personas.situacion", "personas.no_disponible", "acercamientos.registrar", "acercamientos.ver",
                  "reuniones.ver", "reuniones.crear", "reuniones.asistentes", "puestos.ver", "plantillas", "solicitudes.crear"}
    consultor = {"cuenta", "catalogos.ver", "insignias", "trabajo.ver", "trabajo.cola", "personas.buscar", "personas.ver",
                 "personas.telefonos", "personas.autorizacion", "personas.situacion", "personas.no_disponible",
                 "acercamientos.registrar", "acercamientos.ver", "puestos.ver", "solicitudes.crear"}
    assert acceso.PERMISOS["planillero"] >= planillero and acceso.PERMISOS["consultor"] >= consultor
    solo_admin = {"*", "admin", "importar", "exportar", "tablero.ver", "mapa.ver", "usuarios.gestionar", "calidad.ver",
                  "calidad.resolver", "puestos.gestionar", "ajustes.gestionar", "zonas.gestionar"}
    for rol in ("planillero", "consultor"):
        assert not acceso.PERMISOS[rol] & solo_admin
    assert not acceso.PERMISOS["consultor"] & {"personas.editar", "personas.crear", "personas.listar", "personas.notas"}
    assert "trabajo.cola" not in acceso.PERMISOS["planillero"]
    p = acceso.Quien(uid=5, usuario="planillero5", rol="planillero", permisos=acceso.PERMISOS["planillero"])
    a = acceso.Quien(uid=0, usuario="admin", rol="admin", permisos=acceso.PERMISOS["admin"])
    assert p.puede("personas.editar") and not p.puede("usuarios.gestionar") and not p.es_admin
    assert a.puede("usuarios.gestionar") and a.puede("admin") and a.es_admin
    assert not acceso.Quien(uid=9, usuario="x", rol="jefe").puede("cuenta")  # sin permisos por defecto


def test_lecturas_e_idempotencia_tienen_su_firma():
    assert list(inspect.signature(acceso.registrar_lecturas).parameters) == ["db", "quien", "pids", "ficha"]
    assert list(inspect.signature(acceso.idempotencia_previa).parameters) == ["db", "quien", "request"]
    assert list(inspect.signature(acceso.idempotencia_guardar).parameters) == ["db", "quien", "request", "codigo", "cuerpo",
                                                                               "persona_id"]


def _mini(app_real, inyectar=None):
    """Una aplicación con rutas protegidas por `requiere`, sobre la configuración y la base de la real. `inyectar`
    pone esa sesión en scope["state"], como la deja la guardia."""
    mini = FastAPI()
    mini.state.cfg, mini.state.db = app_real.state.cfg, app_real.state.db

    @mini.get("/ver")
    def ver(q: acceso.Quien = Depends(acceso.requiere("personas.ver"))):
        return {"uid": q.uid, "usuario": q.usuario, "rol": q.rol, "asignacion": q.asignacion}

    @mini.post("/editar")
    def editar(q: acceso.Quien = Depends(acceso.requiere("personas.editar"))):
        return {"ok": True}

    @mini.get("/solo-admin")
    def solo_admin(q: acceso.Quien = Depends(acceso.requiere("admin"))):
        return {"ok": True}

    if inyectar is not None:
        class Inyecta:
            def __init__(self, app):
                self.app = app

            async def __call__(self, scope, receive, send):
                if scope["type"] == "http":
                    scope.setdefault("state", {})["sesion"] = inyectar
                await self.app(scope, receive, send)

        mini.add_middleware(Inyecta)
    return mini


def test_requiere_con_la_sesion_del_administrador(sesion):
    dep = acceso.requiere("personas.ver", "personas.editar", limitar=True)
    assert dep.permisos == frozenset({"personas.ver", "personas.editar"}) and dep.limitar is True
    c = TestClient(_mini(sesion.app), cookies=dict(sesion.cookies))
    yo = c.get("/ver").json()
    assert (yo["uid"], yo["usuario"], yo["rol"]) == (0, "admin", "admin")
    assert c.get("/solo-admin").status_code == 200
    r = c.post("/editar")
    assert r.status_code == 403 and "CSRF" in r.json()["detail"]
    assert c.post("/editar", headers={"X-CSRF-Token": sesion.headers["X-CSRF-Token"]}).json() == {"ok": True}
    assert TestClient(_mini(sesion.app)).get("/ver").status_code == 401


def test_requiere_falla_cerrada(cliente):
    # El rol de administrador sale solo de una sesión sin uid (o con 0) firmada con la credencial vigente
    for falsa in ({"uid": None, "usuario": "admin", "huella": "otra", "csrf": "x"}, {"uid": 0, "usuario": "admin", "csrf": "x"}):
        c = TestClient(_mini(cliente.app, falsa))
        assert c.get("/ver").status_code == 401, falsa
        assert c.post("/editar", headers={"X-CSRF-Token": "x"}).status_code == 401, falsa
    # Un rol desconocido no tiene permisos, y «admin» en la sesión de un usuario no lo hace administrador
    crear_usuario(cliente.app.state.db, "planillero", _id=98)
    for falsa in ({"uid": 98, "rol": "jefe", "csrf": "x"}, {"uid": 98, "rol": "admin", "csrf": "x"},
                  {"uid": 99, "rol": "admin", "usuario": "admin", "csrf": "x"}):
        c = TestClient(_mini(cliente.app, falsa))
        assert c.get("/solo-admin").status_code in (401, 403), falsa
    assert TestClient(_mini(cliente.app, {"uid": 99, "rol": "jefe", "csrf": "x"})).get("/ver").status_code in (401, 403)


@pytest.mark.parametrize("rol", ["planillero", "consultor"])
def test_requiere_con_sesion_de_usuario(como, rol):
    c = como(rol, asignacion={"lugares": [3], "areas": []})
    m = TestClient(_mini(c.app), cookies=dict(c.cookies))
    assert m.get("/ver").json() == {"uid": c.uid, "usuario": c.usuario, "rol": rol, "asignacion": {"lugares": [3], "areas": []}}
    r = m.get("/solo-admin")
    assert r.status_code == 403 and r.json()["detail"]["codigo"] == "permiso"
    r = m.post("/editar", headers={"X-CSRF-Token": c.headers["X-CSRF-Token"]})
    assert r.status_code == (200 if rol == "planillero" else 403)


# ───────────────────────────── Proyección ─────────────────────────────

def test_exigir_tratable():
    P = acceso.Quien(uid=5, usuario="planillero5", rol="planillero", permisos=acceso.PERMISOS["planillero"])
    C = acceso.Quien(uid=6, usuario="consultor6", rol="consultor", permisos=acceso.PERMISOS["consultor"])
    A_ = acceso.Quien(uid=0, usuario="admin", rol="admin", permisos=acceso.PERMISOS["admin"])
    no = {"_id": 1, "consentimiento": "no"}
    for accion in ("editar", "telefonos", "nota", "ubicar", "asistencia", "acercamiento", "duplicado", "situacion",
                   "no_disponible"):
        for quien in (P, C, None):
            with pytest.raises(HTTPException) as e:
                proyeccion.exigir_tratable(no, quien, accion)
            assert e.value.status_code == 409
            assert (e.value.detail["codigo"], e.value.detail["motivo"]) == ("no_contactable", "no_autorizo")
        assert proyeccion.exigir_tratable(no, A_, accion) is None  # A puede todo
    for accion in ("autorizacion", "solicitud"):
        proyeccion.exigir_tratable(no, P, accion)
        proyeccion.exigir_tratable(no, C, accion)
    for consentimiento in ("si", "pendiente", None):
        proyeccion.exigir_tratable({"consentimiento": consentimiento}, C, "acercamiento")
    proyeccion.exigir_tratable({}, P, "editar")


def test_proyeccion_por_lista_de_campos():
    vedados = {"sensibles", "listas", "lider", "historial", "origen", "procedencia", "cedulas_anteriores", "partido",
               "mesa_testigo", "cedula_en_traspaso", "fuentes", "coincidencias"}
    for rol in ("admin", "planillero", "consultor"):
        assert not proyeccion.CAMPOS_FICHA[rol] & {"sensibles", "cedula_en_traspaso"}
        assert not proyeccion.CAMPOS_FILA[rol] & {"sensibles", "cedula_en_traspaso"}
        assert "id" in proyeccion.CAMPOS_FICHA[rol] and "id" in proyeccion.CAMPOS_FILA[rol]
    for rol in ("planillero", "consultor"):
        assert not proyeccion.CAMPOS_FICHA[rol] & vedados and not proyeccion.CAMPOS_FILA[rol] & vedados
    assert not {"cedula", "telefono", "notas", "tramites", "alternos"} & proyeccion.CAMPOS_FICHA["consultor"]
    assert not {"cedula", "telefono", "lider", "fuentes"} & proyeccion.CAMPOS_FILA["planillero"]
    assert proyeccion.CAMPOS_FILA["consultor"] == {"id", "nombre", "lugar", "abordaje_estado", "contactable"}
    assert proyeccion.CAMPOS_NO_AUTORIZO == {"id", "nombre", "cedula_ult3", "lugar", "consentimiento", "abordaje"}
    assert {"lider", "listas", "origen", "historial", "sensibles_registrados"} <= proyeccion.CAMPOS_FICHA["admin"]


def test_neutralizar_fuente_y_firmas():
    assert proyeccion.neutralizar_fuente("cedulas") == "otra_base"
    assert proyeccion.neutralizar_fuente("planilla") == "planilla" and proyeccion.neutralizar_fuente(None) is None
    assert proyeccion.neutralizar_fuente(["tramites", "cedulas", "otra_base"]) == ["tramites", "otra_base"]
    assert list(inspect.signature(proyeccion.ficha_para).parameters) == ["db", "quien", "pid"]
    assert list(inspect.signature(proyeccion.filas_para).parameters) == ["quien", "docs"]


# ───────────────────────────── Piezas compartidas ─────────────────────────────

def test_persona_vacia_no_comparte_listas():
    a, b = bd.persona_vacia(), bd.persona_vacia()
    assert a == bd.PERSONA_VACIA
    a["fuentes"].append("x")
    a["extra"]["k"] = 1
    assert b["fuentes"] == [] and bd.PERSONA_VACIA["fuentes"] == [] and bd.PERSONA_VACIA["extra"] == {}


def test_auditar_con_quien(bases):
    db = bases()
    q = acceso.Quien(uid=5, usuario="planillero5", rol="planillero", ip="10.0.0.5", permisos=acceso.PERMISOS["planillero"])
    bd.auditar(db, q, "editar", "persona", 12, {"via": "panel"}, campos=["sexo"], completados=["sexo"], capturado_por=5,
               canal="visita")
    a = db.auditoria.find_one({"accion": "editar"})
    assert (a["usuario"], a["uid"], a["rol"], a["ip"]) == ("planillero5", 5, "planillero", "10.0.0.5")
    assert (a["entidad"], a["entidad_id"], json.loads(a["detalle"])) == ("persona", 12, {"via": "panel"})
    assert (a["campos"], a["completados"], a["capturado_por"], a["canal"]) == (["sexo"], ["sexo"], 5, "visita")
    bd.auditar(db, "admin", "ingreso", ip="10.0.0.1")  # con texto, como siempre
    b = db.auditoria.find_one({"accion": "ingreso"})
    assert (b["usuario"], b["ip"], b["detalle"]) == ("admin", "10.0.0.1", None)
    assert list(inspect.signature(bd.auditar).parameters)[:9] == ["db", "quien", "accion", "entidad", "entidad_id", "detalle",
                                                                  "ip", "campos", "completados"]


def test_importar_acepta_quien_y_capturado_por():
    ps = inspect.signature(imp.importar).parameters
    assert list(ps)[:4] == ["db", "rutas", "usuario", "nombres"]
    for nombre in ("quien", "capturado_por"):
        assert ps[nombre].kind is inspect.Parameter.KEYWORD_ONLY and ps[nombre].default is None


def test_migrar_se_puede_repetir(bases):
    assert issubclass(migraciones.ErrorMigracion, RuntimeError)
    db = bases()
    migraciones.migrar(db)
    migraciones.migrar(db)


def test_main_incluye_los_routers_nuevos(cfg):
    from app.api import acercamientos, ajustes, usuarios, zonas
    from app.main import crear_app
    modulos = (usuarios, acercamientos, zonas, ajustes)
    for m in modulos:
        assert isinstance(m.r, APIRouter) and m.r.prefix == "/api"
        m.r.add_api_route(f"/_contrato_{m.__name__.rsplit('.', 1)[1]}", lambda: {}, methods=["GET"])
    try:
        app = crear_app(cfg)
        rutas = {getattr(x, "path", None) for x in app.routes}
        app.state.cliente.close()
    finally:
        for m in modulos:
            m.r.routes[:] = [x for x in m.r.routes if "/_contrato_" not in getattr(x, "path", "")]
    for m in modulos:
        assert f"/api/_contrato_{m.__name__.rsplit('.', 1)[1]}" in rutas


@pytest.mark.parametrize("archivo, nombres", [
    ("web/js/llamadas.js", ["revisarLlamadasPendientes", "marcarLlamada", "llamadaPendiente", "olvidarLlamada"]),
    ("web/js/vistas/trabajo.js", ["vistaTrabajo"]),
    ("web/js/vistas/usuarios.js", ["vistaUsuarios", "vistaUsuario"]),
    ("web/js/vistas/cuenta.js", ["vistaCuenta"]),
    ("web/js/vistas/acercamiento.js", ["dialogoAcercamiento"]),
    ("web/js/modelo.js", ["CATALOGOS", "marcable", "esUsable", "etiquetaResultado"]),
    ("web/js/api.js", ["sesion", "configurar", "puede", "api", "descargar", "ErrorApi"]),
])
def test_modulos_js_exportan_su_contrato(archivo, nombres):
    js = (RAIZ / archivo).read_text(encoding="utf-8")
    for n in nombres:
        assert re.search(rf"export (async )?(function|const|class|let) {n}\b", js), f"{archivo}: falta {n}"


def test_js_de_la_aplicacion_conoce_las_piezas_nuevas():
    app_js = (RAIZ / "web/js/app.js").read_text(encoding="utf-8")
    for vista, modulo in (("vistaTrabajo", "trabajo"), ("vistaUsuarios", "usuarios"), ("vistaUsuario", "usuarios"),
                          ("vistaCuenta", "cuenta")):
        assert f"vistas/{modulo}.js" in app_js and re.search(rf"\b{vista}\b", app_js), vista
    assert re.search(r"import \{[^}]*\brevisarLlamadasPendientes\b[^}]*\} from '\./llamadas\.js'", app_js)
    assert re.search(r"\brevisarLlamadasPendientes\(\)", app_js)
    ui = (RAIZ / "web/js/ui.js").read_text(encoding="utf-8")
    for icono in ("trabajo", "usuarios", "cuenta", "zona", "telefono", "acercamiento"):
        assert re.search(rf"^\s*{icono}:\s*['\"`]<", ui, re.M), icono
    for fuente in ("planilla", "consultor", "otra_base"):
        assert re.search(rf"\b{fuente}:\s*['\"`]", ui), fuente
    api = (RAIZ / "web/js/api.js").read_text(encoding="utf-8")
    assert "Idempotency-Key" in api and "AbortController" in api
    assert all(re.search(rf"\b{k}\b", api) for k in ("uid", "rol", "permisos", "nombre"))


# ───────────────────────────── Fixture `como` y generadores ─────────────────────────────

def test_como_admin(como):
    c = como("admin")
    assert (c.uid, c.usuario, c.rol) == (0, "admin", "admin")
    assert c.get("/api/yo").json()["usuario"] == "admin"
    assert c.post("/api/logout").status_code == 200  # trae su CSRF


@pytest.mark.parametrize("rol", ["planillero", "consultor"])
def test_como_usuario(como, rol):
    c = como(rol, nombre="Persona Inventada de Prueba")
    yo = c.get("/api/yo")
    assert yo.status_code == 200, yo.text
    yo = yo.json()
    assert (yo["uid"], yo["usuario"], yo["rol"], yo["nombre"]) == (c.uid, c.usuario, rol, "Persona Inventada de Prueba")
    assert set(yo["permisos"]) == set(acceso.PERMISOS[rol])
    assert yo["debe_cambiar_clave"] is False and yo["compromiso_pendiente"] is False


def test_planilla_inventada(tmp_path):
    ruta = excel_planilla(tmp_path / "planilla.xlsx", PLANILLA)
    filas = list(openpyxl.load_workbook(ruta)["Planilla"].iter_rows(values_only=True))
    assert list(filas[0]) == COLUMNAS_PLANILLA and len(filas) == 1 + len(PLANILLA)
    col = {c: i for i, c in enumerate(COLUMNAS_PLANILLA)}
    tels = [len(tx.telefonos(f"{f[col['Celular']]} / {f[col['Otro teléfono']] or ''}")) for f in PLANILLA]
    assert 3 in tels and all(n >= 1 for n in tels)
    cedulas_base = {c[0]: c[1] for c in CEDULAS}
    assert any(f[0] in cedulas_base and f[col["Nombre completo"]] != cedulas_base[f[0]] for f in PLANILLA)
    assert any(f[0] is None for f in PLANILLA)
    assert any(f[0] and f[1] and f[0] != f[1] for f in PLANILLA)
    assert any(f[col["Autorización de datos"]] == "No autoriza" for f in PLANILLA)
    ti = [f for f in PLANILLA if f[col["Tipo de documento"]] == "TI"]
    assert ti and modelo.es_menor({"tipo_documento": "TI", "fecha_nacimiento": ti[0][col["Fecha de nacimiento"]].isoformat()}, HOY)
    assert modelo.edad_efectiva({"fecha_nacimiento": ti[0][col["Fecha de nacimiento"]].isoformat()}, HOY) < 18
    etiquetas = {"Sexo": set(modelo.SEXOS.values()), "Autorización de datos": set(modelo.ESTADOS_AUTORIZACION.values()),
                 "Medio de la autorización": set(modelo.MEDIOS_AUTORIZACION.values()),
                 "Tipo de documento": set(modelo.TIPOS_DOCUMENTO)}
    for f in PLANILLA:
        for c, validos in etiquetas.items():
            assert f[col[c]] is None or f[col[c]] in validos, (c, f[col[c]])
        for canal in (f[col["Canales autorizados"]] or "").split(","):
            assert not canal.strip() or canal.strip() in modelo.CANALES_AUTORIZACION.values()


def test_personas_inventadas(bases):
    a, b = personas_inventadas(300), personas_inventadas(300)
    assert a == b and personas_inventadas(300, semilla=1) != a
    cedulas = [p["cedula"] for p in a + personas_inventadas(300, semilla=1) if p["cedula"]]
    telefonos = [p["telefono"] for p in a + personas_inventadas(300, semilla=1) if p["telefono"]]
    assert len(cedulas) == len(set(cedulas)) and all(tx.cedula(c) == c for c in cedulas)
    assert len(telefonos) == len(set(telefonos)) and all(tx.telefonos(t) == [t] for t in telefonos)
    assert all((p["lat"] is None) == (modelo.punto(p["lat"], p["lon"]) is None) for p in a)
    db = bases()
    ids = insertar_personas(db, a[:50])
    assert len(ids) == 50 == db.personas.count_documents({"_id": {"$in": ids}})
    doc = db.personas.find_one({"_id": ids[1]})
    assert doc["nombre"] == a[1]["nombre"] and doc["punto"] == modelo.punto(a[1]["lat"], a[1]["lon"])
    assert insertar_personas(db, []) == []
