"""Regresiones de la revisión adversarial de las herramientas del asistente (`app/agente/herramientas/` e
`app/agente/interno.py`). Cada prueba lleva en el nombre el número de su hallazgo y falla sin su arreglo, salvo dos que
cuidan lo que el arreglo no debe romper: un reintento del mismo acercamiento devuelve lo guardado (24) y, por el bucle,
volver a aprobar tras un corte no repite la escritura en Mnemo (25, que el bucle también evita).

Solo datos inventados. Nunca se llama a Anthropic ni a Mnemo: la Messages API va simulada (`ayudas_agente`) y Mnemo es
el servidor MCP falso (`ayudas_mcp`)."""
from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path

import pytest
from pydantic import ValidationError

import ayudas_agente as aa
from ayudas_g3 import autorizada, persona
from app import acceso, modelo
from app import db as bd
from app.agente import bucle
from app.agente.herramientas import base as hb
from app.agente.herramientas import gestion as hg
from app.agente.herramientas import interfaz as hi
from app.agente.herramientas import mnemo as hm
from app.agente.herramientas import personas as hp
from app.agente.herramientas.base import ErrorHerramienta

H = {h.nombre: h for h in hp.HERRAMIENTAS + hg.HERRAMIENTAS + hi.HERRAMIENTAS}
WEB = Path(__file__).resolve().parents[1] / "web" / "js"
TEL_A, TEL_B = "3001112233", "3204445566"


# ───────────────────────────── Ayudas ─────────────────────────────

def _tel(numero: str, **extra) -> dict:
    return {"numero": numero, "tipo": "celular", "fuentes": ["panel"], "estado": "sin_verificar",
            "no_contactar": False, **extra}


def _ctx(cliente, tid: str, **kw):
    return aa.contexto(cliente.app, cliente, tool_use_id=tid, **kw)


def _ej(cliente, ctx, nombre: str, entrada: dict):
    return aa.correr(cliente, aa.ejecutar, H[nombre], ctx, entrada)


def _falla(cliente, fn, *args) -> ErrorHerramienta:
    with pytest.raises(ErrorHerramienta) as e:
        aa.correr(cliente, fn, *args)
    return e.value


def _tarjeta(cliente, nombre: str, ctx, entrada: dict):
    """Como el bucle: valida, arma la tarjeta y guarda la entrada tal como quedó (con lo que `confirmar` le puso) para
    ejecutarla al aprobar. Devuelve (tarjeta, entrada guardada)."""
    h = H[nombre]
    a = h.validar(entrada)
    conf = aa.correr(cliente, h.confirmar, ctx, a)
    return conf, h.validar(bucle._entrada_pendiente(h, a, entrada))


def _vereda(db, nombre: str = "VEREDA INVENTADA DE PRUEBA") -> int:
    lid = bd.siguiente_id(db, "lugares")
    db.lugares.insert_one({"_id": lid, "nombre": nombre, "tipo": "vereda", "zona": "rural", "lat": 6.95,
                           "lon": -73.95, "alias": [], "padre": None})
    return lid


# ───────────────────────────── 24: el número de la tarjeta es el que se marca ─────────────────────────────

def test_24_el_acercamiento_marca_el_numero_que_mostro_la_tarjeta_aunque_se_corra_el_indice(sesion):
    """En el mismo turno: agregar un número como principal y registrar «número equivocado» con el índice 0. La tarjeta
    del acercamiento muestra el número viejo (índice 0 antes de aprobar); al aprobar las dos, el nuevo pasa a ser el
    0, pero el que queda «equivocado» es el que mostró la tarjeta."""
    db = sesion.app.state.db
    pid = persona(db, nombre="TELESFORA INVENTADA", telefono=TEL_A, telefonos=[_tel(TEL_A)])
    autorizada(db, pid)
    aa.encender(sesion.app, aa.sse(
        aa.TU("toolu_tel", "agregar_telefono", {"persona_id": pid, "numero": TEL_B, "principal": True}),
        aa.TU("toolu_ac", "registrar_acercamiento", {"persona_id": pid, "canal": "llamada",
                                                    "resultado": "numero_equivocado", "telefono_indice": 0}),
        stop="tool_use"), aa.sse(aa.T("Listo.")))
    r, ev = aa.enviar(sesion, "Agregue el número nuevo y marque el viejo como equivocado")
    assert r.status_code == 200 and ev[-1]["motivo"] == "confirmacion", r.text
    tarjeta = next(e for e in ev if e["tipo"] == "confirmar" and e["id"] == "toolu_ac")
    assert dict(tarjeta["detalle"])["Número"] == acceso.enmascarar_telefono(TEL_A)
    r, ev = aa.decidir(sesion, ev[0]["conversacion"], toolu_tel=True, toolu_ac=True)
    assert r.status_code == 200 and ev[-1]["motivo"] == "listo", r.text
    estados = {t["numero"]: t.get("estado") for t in db.personas.find_one({"_id": pid})["telefonos"]}
    assert estados[TEL_A] == "equivocado" and estados[TEL_B] != "equivocado", estados
    assert db.acercamientos.find_one({"persona_id": pid, "resultado": "numero_equivocado"})["telefono"] == TEL_A


def test_24_si_el_numero_de_la_tarjeta_ya_no_se_puede_usar_no_registra_nada(sesion):
    """La tarjeta muestra el número del índice 0; antes de aprobar, otra persona lo marca como equivocado y el otro
    número pasa a ser el 0. Al aprobar no se registra nada en el número que la tarjeta no mostró: «cambiada»."""
    db = sesion.app.state.db
    pid = persona(db, nombre="TELESFORO INVENTADO", telefono=TEL_A, telefonos=[_tel(TEL_A), _tel(TEL_B)])
    autorizada(db, pid)
    ctx = _ctx(sesion, "toolu_ac2")
    conf, guardada = _tarjeta(sesion, "registrar_acercamiento", ctx, {
        "persona_id": pid, "canal": "llamada", "resultado": "contesto", "telefono_indice": 0,
        "confirma_numero": True})
    assert dict(conf.detalle)["Número"] == acceso.enmascarar_telefono(TEL_A)
    db.personas.update_one({"_id": pid, "telefonos.numero": TEL_A}, {"$set": {"telefonos.$.estado": "equivocado"}})
    e = _falla(sesion, H["registrar_acercamiento"].ejecutar, ctx, guardada)
    assert e.codigo == "cambiada" and e.estado == 409, (e.codigo, e.mensaje)
    assert db.acercamientos.count_documents({"persona_id": pid}) == 0
    assert {t["numero"]: t.get("estado") for t in db.personas.find_one({"_id": pid})["telefonos"]}[TEL_B] \
        == "sin_verificar"


def test_24_repetir_el_mismo_acercamiento_devuelve_lo_guardado(sesion):
    """Un reintento del mismo tool_use (la aprobación se repite tras un corte) devuelve la respuesta guardada, aunque
    el número ya quedó «equivocado» por la primera ejecución: no falla ni registra otro acercamiento."""
    db = sesion.app.state.db
    pid = persona(db, nombre="TEODORA INVENTADA", telefono=TEL_A, telefonos=[_tel(TEL_A), _tel(TEL_B)])
    autorizada(db, pid)
    ctx = _ctx(sesion, "toolu_ac3")
    _, guardada = _tarjeta(sesion, "registrar_acercamiento", ctx, {
        "persona_id": pid, "canal": "llamada", "resultado": "numero_equivocado", "telefono_indice": 1})
    r1 = aa.correr(sesion, H["registrar_acercamiento"].ejecutar, ctx, guardada)
    r2 = aa.correr(sesion, H["registrar_acercamiento"].ejecutar, ctx, guardada)
    assert r1.contenido["acercamiento_id"] == r2.contenido["acercamiento_id"]
    assert db.acercamientos.count_documents({"persona_id": pid}) == 1
    assert db.acercamientos.find_one({"persona_id": pid})["telefono"] == TEL_B


# ───────────────────────────── 26: el «sí» del administrador no supone canales ─────────────────────────────

def test_26_el_si_del_administrador_exige_medio_y_canales(sesion):
    db = sesion.app.state.db
    pid = persona(db, nombre="AURELIANA INVENTADA", telefono=TEL_A)
    ctx = _ctx(sesion, "toolu_aut")
    e = _falla(sesion, aa.confirmar, H["registrar_autorizacion"], ctx, {"persona_id": pid, "estado": "si"})
    assert e.codigo == "invalido" and "medio" in e.mensaje and "canal" in e.mensaje, e.mensaje
    e = _falla(sesion, aa.ejecutar, H["registrar_autorizacion"], ctx, {"persona_id": pid, "estado": "si",
                                                                      "medio": "verbal_presencial"})
    assert e.codigo == "invalido" and "canal" in e.mensaje
    assert db.autorizaciones.count_documents({"persona_id": pid}) == 0
    entrada = {"persona_id": pid, "estado": "si", "medio": "verbal_presencial", "canales": ["llamada"]}
    detalle = dict(aa.correr(sesion, aa.confirmar, H["registrar_autorizacion"], ctx, entrada).detalle)
    assert detalle["Medio"] == modelo.MEDIOS_AUTORIZACION["verbal_presencial"] and detalle["Canales"] == "Llamada"
    _ej(sesion, ctx, "registrar_autorizacion", entrada)
    ev = db.autorizaciones.find_one({"persona_id": pid})
    assert ev["canales_implicitos"] is False and ev["canales"] == ["llamada"] and ev["medio"] == "verbal_presencial"
    # Lo que no es un «sí» no pide medio ni canales (no habilita contactos)
    otra = persona(db, nombre="AURELIO INVENTADO", consentimiento="si")
    aa.correr(sesion, aa.confirmar, H["registrar_autorizacion"], _ctx(sesion, "toolu_aut2"),
              {"persona_id": otra, "estado": "revocada"})


# ───────────────────────────── 30: la solicitud de derechos dice qué se pidió ─────────────────────────────

def test_30_la_solicitud_de_derechos_exige_el_tipo_y_la_tarjeta_lo_muestra(sesion):
    db = sesion.app.state.db
    pid = persona(db, nombre="SUPRIMENDA INVENTADA")
    autorizada(db, pid)
    sin_tipo = {"persona_id": pid, "canal": "visita", "resultado": "solicitud_derechos",
                "nota": "Pidió que borren todos sus datos"}
    with pytest.raises(ValidationError, match="solicitud_tipo"):
        H["registrar_acercamiento"].validar(sin_tipo)
    ctx = _ctx(sesion, "toolu_sol")
    entrada = {**sin_tipo, "solicitud_tipo": "supresion"}
    conf, guardada = _tarjeta(sesion, "registrar_acercamiento", ctx, entrada)
    assert dict(conf.detalle)["Qué pidió"] == "Supresión · plazo de 15 días hábiles"
    aa.correr(sesion, H["registrar_acercamiento"].ejecutar, ctx, guardada)
    assert db.solicitudes.find_one({"persona_id": pid})["tipo"] == "supresion"
    conf, _ = _tarjeta(sesion, "registrar_acercamiento", _ctx(sesion, "toolu_sol2"),
                       {**sin_tipo, "solicitud_tipo": "consulta", "nota": "Quiere saber qué datos hay"})
    assert dict(conf.detalle)["Qué pidió"] == "Consulta · plazo de 10 días hábiles"


# ───────────────────────────── 31: corregir tildes y mayúsculas ─────────────────────────────

def test_31_reemplazar_corrige_las_tildes_del_nombre(sesion):
    db = sesion.app.state.db
    pid = persona(db, nombre="MARIA GOMEZ INVENTADA")
    autorizada(db, pid)
    ctx = _ctx(sesion, "toolu_tilde")
    entrada = {"persona_id": pid, "cambios": {"nombre": "María Gómez Inventada"}, "modo": "reemplazar"}
    conf, guardada = _tarjeta(sesion, "editar_persona", ctx, entrada)
    assert dict(conf.detalle)["Nombre"] == "MARIA GOMEZ INVENTADA → MARÍA GÓMEZ INVENTADA"
    r = aa.correr(sesion, H["editar_persona"].ejecutar, ctx, guardada)
    assert r.contenido["guardado"] is True and not r.contenido.get("sin_cambios")
    assert db.personas.find_one({"_id": pid})["nombre"] == "MARÍA GÓMEZ INVENTADA"
    # Repetirlo no escribe otra vez: ya quedó como se pidió
    r = aa.correr(sesion, H["editar_persona"].ejecutar, ctx, guardada)
    assert r.contenido.get("sin_cambios") is True
    # Una ocupación con otra mayúscula también se corrige en modo reemplazar
    db.personas.update_one({"_id": pid}, {"$set": {"ocupacion": "pescadora"}})
    conf, _ = _tarjeta(sesion, "editar_persona", _ctx(sesion, "toolu_ocu"),
                       {"persona_id": pid, "cambios": {"ocupacion": "Pescadora"}, "modo": "reemplazar"})
    assert dict(conf.detalle)["Ocupación"] == "pescadora → Pescadora"
    # En modo completar, las tildes no son un dato nuevo: ni cambio ni alterno
    otra = persona(db, nombre="ROSALBA PEREZ INVENTADA")
    autorizada(db, otra)
    e = _falla(sesion, aa.confirmar, H["editar_persona"], _ctx(sesion, "toolu_comp"),
               {"persona_id": otra, "cambios": {"nombre": "Rosalba Pérez Inventada"}})
    assert e.codigo == "sin_cambios"


# ───────────────────────────── 32: quien dejó de autorizar entre la tarjeta y la aprobación ─────────────────

def test_32_nota_telefono_y_acercamiento_no_escriben_si_ya_no_autoriza(sesion):
    db = sesion.app.state.db
    pid = persona(db, nombre="REVOCANDA INVENTADA", telefono=TEL_A, telefonos=[_tel(TEL_A)])
    autorizada(db, pid)
    casos = {"agregar_nota": {"persona_id": pid, "texto": "Visitar el lunes"},
             "agregar_telefono": {"persona_id": pid, "numero": TEL_B},
             "registrar_acercamiento": {"persona_id": pid, "canal": "visita", "resultado": "contesto"}}
    preparadas = {}
    for nombre, entrada in casos.items():
        ctx = _ctx(sesion, f"toolu_{nombre}")
        preparadas[nombre] = (ctx, _tarjeta(sesion, nombre, ctx, entrada)[1])
    db.personas.update_one({"_id": pid}, {"$set": {"consentimiento": "no"}})  # otra persona registró que no autoriza
    for nombre, (ctx, guardada) in preparadas.items():
        e = _falla(sesion, H[nombre].ejecutar, ctx, guardada)
        assert e.codigo == "no_contactable", (nombre, e.codigo, e.mensaje)
    p = db.personas.find_one({"_id": pid})
    assert not p.get("notas") and [t["numero"] for t in p["telefonos"]] == [TEL_A]
    assert db.acercamientos.count_documents({"persona_id": pid}) == 0


# ───────────────────────────── 29: dos reuniones distintas del mismo día ─────────────────────────────

def test_29_dos_reuniones_del_mismo_dia_y_titulo_en_sitios_distintos_son_dos(sesion):
    db = sesion.app.state.db
    a = {"titulo": "Reunión comunitaria", "fecha": "2026-11-20", "sitio": "Escuela de la vereda A"}
    b = {**a, "sitio": "Caseta comunal de la vereda B"}
    ca, cb = _ctx(sesion, "toolu_ra"), _ctx(sesion, "toolu_rb")
    _, ga = _tarjeta(sesion, "crear_reunion", ca, a)
    _, gb = _tarjeta(sesion, "crear_reunion", cb, b)  # las dos tarjetas en el mismo turno
    r1 = aa.correr(sesion, H["crear_reunion"].ejecutar, ca, ga)
    r2 = aa.correr(sesion, H["crear_reunion"].ejecutar, cb, gb)
    assert r1.contenido["ya_existia"] is False and r2.contenido["ya_existia"] is False
    assert r1.contenido["reunion"]["id"] != r2.contenido["reunion"]["id"]
    assert sorted(x["lugar_texto"] for x in db.reuniones.find()) == sorted([a["sitio"], b["sitio"]])
    # Un reintento de la misma llamada no crea otra: es la que ya hizo
    r3 = aa.correr(sesion, H["crear_reunion"].ejecutar, cb, gb)
    assert r3.contenido["ya_existia"] is True and r3.contenido["reunion"]["id"] == r2.contenido["reunion"]["id"]
    assert db.reuniones.count_documents({}) == 2
    # Una tarjeta igual a una reunión que ya existe se rechaza
    e = _falla(sesion, aa.confirmar, H["crear_reunion"], _ctx(sesion, "toolu_rc"), b)
    assert e.codigo == "duplicada"
    # En el mismo barrio o vereda, con otro sitio, también son dos
    lugar = _vereda(db)
    c = {"titulo": "Reunión de la junta", "fecha": "2026-11-21", "lugar_id": lugar, "sitio": "Escuela"}
    d = {**c, "sitio": "Caseta comunal"}
    cc, cd = _ctx(sesion, "toolu_rd"), _ctx(sesion, "toolu_re")
    _, gc = _tarjeta(sesion, "crear_reunion", cc, c)
    _, gd = _tarjeta(sesion, "crear_reunion", cd, d)
    assert aa.correr(sesion, H["crear_reunion"].ejecutar, cc, gc).contenido["ya_existia"] is False
    assert aa.correr(sesion, H["crear_reunion"].ejecutar, cd, gd).contenido["ya_existia"] is False
    assert db.reuniones.count_documents({"lugar_id": lugar}) == 2


# ───────────────────────────── 5: con filtros no se deduce nada de quien no autorizó ─────────────────────────

@pytest.fixture
def marta(sesion):
    """Una vereda con dos mujeres: MARTA, que no autorizó (con su necesidad y ubicada), y ROSA, que sí."""
    db = sesion.app.state.db
    vivienda = db.etiquetas.find_one({"nombre": "Vivienda"})["_id"]
    lugar = _vereda(db)
    m = persona(db, nombre="MARTA NOAUTORIZO INVENTADA", sexo="F", lugar_id=lugar, etiquetas=[vivienda],
                consentimiento="no", lat=6.951, lon=-73.951)
    r = persona(db, nombre="ROSA SIAUTORIZO INVENTADA", sexo="F", lugar_id=lugar, consentimiento="si", lat=6.952,
                lon=-73.952)
    return {"marta": m, "rosa": r, "lugar": lugar, "vivienda": vivienda}


def test_05_con_filtros_u_orden_buscar_no_trae_a_quien_no_autorizo(sesion, marta):
    ctx = _ctx(sesion, "toolu_b")
    for entrada in ({"filtros": {"sexo": "F"}},
                    {"filtros": {"lugar_id": marta["lugar"], "etiqueta": marta["vivienda"]}},
                    {"filtros": {"faltan": ["cedula", "telefono"]}}, {"orden": "-completitud"}):
        r = _ej(sesion, ctx, "buscar_personas", entrada)
        ids = {f["id"] for f in r.contenido["filas"]}
        assert marta["marta"] not in ids and marta["marta"] not in r.personas, entrada
        assert r.contenido["total"] == len(ids), entrada
    # Quién no autorizó, solo con su barrio o vereda (lo que su fila ya dice): sí
    r = _ej(sesion, ctx, "buscar_personas", {"filtros": {"consentimiento": "no", "lugar_id": marta["lugar"]}})
    assert [f["id"] for f in r.contenido["filas"]] == [marta["marta"]]
    assert set(r.contenido["filas"][0]) <= {"id", "nombre", "lugar", "consentimiento", "aviso"}
    # Con otro dato no se combina: cada filtro que casa sería un dato de ella
    e = _falla(sesion, aa.ejecutar, H["buscar_personas"], ctx, {"filtros": {"consentimiento": "no", "sexo": "F"}})
    assert e.codigo == "invalido"
    # Sin filtros, la lista por nombre la trae como quien no autorizó (solo quién es)
    r = _ej(sesion, ctx, "buscar_personas", {"por_pagina": 10})
    assert marta["marta"] in {f["id"] for f in r.contenido["filas"]}


def test_05_los_indicadores_no_cuentan_a_quien_no_autorizo(sesion, marta):
    """Un grupo de una sola persona que no autorizó ya no da su sexo ni sus necesidades: los indicadores son siempre
    sin quienes no autorizaron (también sin filtros: restar dos conteos lo diría igual)."""
    ctx = _ctx(sesion, "toolu_i")
    r = _ej(sesion, ctx, "indicadores", {"filtros": {"lugar_id": marta["lugar"]}})
    assert r.contenido["kpi"]["personas"] == 1 and r.contenido["sexo"].get("F") == 1
    assert not [x for x in r.contenido["necesidades"] if x["id"] == marta["vivienda"]]
    assert "buscar_personas" in r.contenido["nota_autorizacion"]
    r = _ej(sesion, ctx, "indicadores", {"filtros": {"lugar_id": marta["lugar"], "sexo": "F", "edad_max": 40}})
    assert r.contenido["kpi"].get("personas", 0) == 0
    r = _ej(sesion, ctx, "indicadores", {})
    assert r.contenido["kpi"]["personas"] == 1 and "no" not in r.contenido["autorizacion"]
    e = _falla(sesion, aa.ejecutar, H["indicadores"], ctx, {"filtros": {"consentimiento": "no"}})
    assert e.codigo == "invalido"


def test_05_el_mapa_no_cuenta_a_quien_no_autorizo(sesion, marta):
    ctx = _ctx(sesion, "toolu_m")
    r = _ej(sesion, ctx, "mapa", {"acciones": [{"tipo": "filtros", "valores": {"lugar_id": marta["lugar"],
                                                                              "sexo": "F"}}]})
    aplicada = r.contenido["aplicadas"][0]
    assert (aplicada["personas"], aplicada["ubicadas"]) == (1, 1)
    # El mapa del navegador lleva los filtros pedidos: la persona del equipo ve a todos
    assert r.acciones[0]["acciones"][0]["valores"] == {"lugar_id": str(marta["lugar"]), "sexo": "F"}
    r = _ej(sesion, ctx, "mapa", {"acciones": [{"tipo": "volar", "lugar_id": marta["lugar"]}]})
    assert (r.contenido["aplicadas"][0]["personas_del_lugar"], r.contenido["aplicadas"][0]["ubicadas"]) == (1, 1)
    # De quienes no autorizaron, el mapa se mueve pero no le da cifras al modelo
    r = _ej(sesion, ctx, "mapa", {"acciones": [{"tipo": "filtros", "valores": {"consentimiento": "no"}},
                                               {"tipo": "volar", "lugar_id": marta["lugar"]}]})
    for aplicada in r.contenido["aplicadas"]:
        assert not {"personas", "ubicadas", "personas_del_lugar"} & set(aplicada), aplicada
    assert r.acciones[0]["acciones"][0]["valores"] == {"consentimiento": "no"}


def test_05_resaltar_no_dice_si_quien_no_autorizo_tiene_ubicacion(sesion, marta):
    """Resaltar por id a quien no autorizó: el mapa del navegador la marca si tiene punto, pero el modelo recibe lo
    mismo tenga o no ubicación (no cuenta en «resaltadas» ni sale en «sin_ubicacion»)."""
    db = sesion.app.state.db
    sin_punto = persona(db, nombre="TERESA NOAUTORIZO SIN PUNTO", consentimiento="no", lugar_id=marta["lugar"])
    ctx = _ctx(sesion, "toolu_rs")
    vistas = []
    for pid in (marta["marta"], sin_punto):  # la primera tiene punto, la segunda no
        r = _ej(sesion, ctx, "mapa", {"acciones": [{"tipo": "resaltar", "persona_ids": [pid, marta["rosa"]]}]})
        vistas.append(r.contenido["aplicadas"][0])
        puntos = {x.get("id") for x in r.acciones[0]["acciones"][0]["puntos"]}
        assert marta["rosa"] in puntos and (pid in puntos) == (pid == marta["marta"])
    assert vistas[0] == vistas[1]
    assert vistas[0]["resaltadas"] == 1 and vistas[0]["sin_ubicacion"] == [] and vistas[0]["no_autorizaron"] == 1
    # Solo ella y sin punto: no hay error que lo delate (el mapa no se mueve)
    r = _ej(sesion, ctx, "mapa", {"acciones": [{"tipo": "resaltar", "persona_ids": [sin_punto]}]})
    assert r.contenido["aplicadas"][0]["resaltadas"] == 0 and r.acciones == [{"tipo": "mapa", "acciones": []}]


def test_05_ver_reunion_no_lista_ni_cuenta_las_necesidades_de_quien_no_autorizo(sesion, marta):
    """Que asistió a una reunión es un dato de quien no autorizó (como filtrar por reunion_id): no se lista, y sus
    necesidades no suman en las de la reunión (la API se las cuenta al administrador)."""
    r = sesion.post("/api/reuniones", json={"titulo": "Reunión en la vereda inventada", "fecha": "2026-11-02"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    for pid in (marta["marta"], marta["rosa"]):
        assert sesion.post(f"/api/reuniones/{rid}/asistentes", json={"persona_id": pid}).status_code == 201
    r = _ej(sesion, _ctx(sesion, "toolu_vr"), "ver_reunion", {"reunion_id": rid})
    assert [f["id"] for f in r.contenido["asistentes"]] == [marta["rosa"]] and marta["marta"] not in r.personas
    assert not [x for x in r.contenido["necesidades"] if x["nombre"] == "Vivienda"]


# ───────────────────────────── 33 y 34: lo que la vista y el mapa aceptan ─────────────────────────────

def _tope_de_consulta_del_widget() -> int:
    texto = (WEB / "agente.js").read_text(encoding="utf-8")
    m = re.search(r"u\.search\.length\s*>\s*(\d+)", texto)
    assert m, "destinoEnlace ya no limita el largo de la consulta"
    return int(m.group(1))


def test_33_abrir_vista_con_demasiados_ids_no_dice_que_abrio(sesion):
    """El widget no abre una ruta con más de 600 caracteres de consulta: la herramienta no puede decir que la abrió."""
    ctx = _ctx(sesion, "toolu_v")
    ids = list(range(10_001, 10_081))  # 80 ids de 5 dígitos: «ids=10001%2C10002…» pasa de 600 caracteres
    e = _falla(sesion, aa.ejecutar, H["abrir_vista"], ctx, {"vista": "habitantes", "ids": ids})
    assert e.codigo == "invalido" and "resaltar" in e.mensaje
    r = _ej(sesion, ctx, "abrir_vista", {"vista": "habitantes", "ids": ids[:20]})
    ruta = r.acciones[0]["ruta"]
    assert hi.MAX_CONSULTA == _tope_de_consulta_del_widget()  # el mismo tope que agente.js
    assert len(ruta.split("?", 1)[1]) + 1 <= hi.MAX_CONSULTA and r.resumen == "Abrí Habitantes"


def test_34_resaltar_500_personas_y_un_lugar_no_pasa_del_tope_del_mapa(monkeypatch):
    texto = (WEB.parent / "js" / "mapa3d.js").read_text(encoding="utf-8")
    assert hi.MAX_RESALTAR == int(re.search(r"export const MAX_IDS = (\d+)", texto).group(1))
    ids = list(range(1, hi.MAX_RESALTAR + 1))

    async def coordenadas(ctx, xs):
        return {i: (7.0, -73.9) for i in xs}

    async def filas(ctx, xs):
        return {}

    monkeypatch.setattr(hi, "_coordenadas", coordenadas)
    monkeypatch.setattr(hi, "_filas", filas, raising=False)
    monkeypatch.setattr(hi, "_nombres", filas, raising=False)  # el nombre de antes del arreglo
    lugar = hg.Lugar(7, "LA PAZ", "barrio", "urbana", None, 7.01, -73.91, False)

    class Nom:
        def por_id_o_error(self, i, t=None):
            return lugar

    async def nom():
        return Nom()

    plan = hi._Plan()
    a = hi.AccionResaltar.model_validate({"tipo": "resaltar", "persona_ids": ids, "lugar_id": 7})
    asyncio.run(hi._resaltar(None, a, plan, nom, None))
    accion = next(x for x in plan.navegador if x["tipo"] == "resaltar")
    assert len(accion["puntos"]) == hi.MAX_RESALTAR and plan.modelo[-1]["resaltadas"] == hi.MAX_RESALTAR
    assert plan.modelo[-1]["lugar_sin_marca"]  # el modelo sabe que el lugar no quedó marcado


# ───────────────────────────── 25: una escritura de Mnemo no se repite ─────────────────────────────

def _herramientas_mnemo(sesion):
    """Mnemo conectado (OAuth falso, sin `mnemo:model`): (servidor MCP falso, cliente, herramientas por nombre)."""
    from ayudas_agente import ALCANCES_PANEL
    from app.agente import mnemo_cliente as mc
    mcp = aa.conectar_mnemo(sesion.app, alcances=[a for a in ALCANCES_PANEL if a != "mnemo:model"]).mcp
    cliente = mc.cliente_de(sesion.app)
    defs = aa.correr(sesion, hm.definiciones, cliente, "")
    return mcp, cliente, {h.nombre: h for h in hm.desde_definiciones(defs)}


def test_25_la_misma_escritura_de_mnemo_no_se_manda_dos_veces(sesion):
    """Mnemo no tiene clave de idempotencia: el mismo `tool_use` aprobado dos veces (un turno cortado después de que
    Mnemo la hizo deja la tarjeta aprobable) se manda una sola vez; la segunda dice que ya se intentó."""
    mcp, cliente, hs = _herramientas_mnemo(sesion)
    db = sesion.app.state.db
    db.agente_conversaciones.insert_one({"_id": 4242, "uid": 0, "titulo": "Prueba", "personas": [], "pendiente": None})
    ctx = aa.contexto(sesion.app, sesion, conversacion_id=4242, tool_use_id="toolu_ev", mnemo=cliente)
    entrada = {"title": "Reunión en la vereda", "start": "2026-11-10T09:00:00-05:00"}
    aa.correr(sesion, aa.ejecutar, hs["mnemo_create_event"], ctx, entrada)
    e = _falla(sesion, aa.ejecutar, hs["mnemo_create_event"], ctx, entrada)
    assert e.codigo == "ya_intentada" and "ya se intentó" in e.mensaje
    assert [n for n, _ in mcp.llamadas].count("mnemo_create_event") == 1
    # Otro tool_use sí se manda; las lecturas no se anotan (se pueden repetir)
    aa.correr(sesion, aa.ejecutar, hs["mnemo_create_event"], aa.contexto(
        sesion.app, sesion, conversacion_id=4242, tool_use_id="toolu_ev2", mnemo=cliente), entrada)
    for _ in range(2):
        aa.correr(sesion, aa.ejecutar, hs["mnemo_search"], ctx, {"query": "acta"})
    assert [n for n, _ in mcp.llamadas].count("mnemo_create_event") == 2
    assert db.agente_conversaciones.find_one({"_id": 4242})["mnemo_intentadas"] == ["toolu_ev", "toolu_ev2"]
    # Sin la conversación (se borró a mitad del turno) no se manda nada
    e = _falla(sesion, aa.ejecutar, hs["mnemo_create_event"], aa.contexto(
        sesion.app, sesion, conversacion_id=999, tool_use_id="toolu_ev3", mnemo=cliente), entrada)
    assert e.codigo == "no_existe" and [n for n, _ in mcp.llamadas].count("mnemo_create_event") == 2


def test_25_volver_a_aprobar_tras_un_turno_cortado_no_repite_la_escritura_en_mnemo(sesion, monkeypatch):
    """Por el bucle: el turno de la aprobación se corta (falla quitar lo pendiente) y la tarjeta se vuelve a aprobar.
    Mnemo recibe la escritura una sola vez, corte donde corte el turno."""
    from app.agente import conversaciones as conv_db
    aa.con_herramientas(monkeypatch, [])
    mcp, _, _ = _herramientas_mnemo(sesion)
    api = aa.encender(sesion.app, aa.sse(aa.TU("toolu_ev", "mnemo_create_event", {
        "title": "Reunión en la vereda", "start": "2026-11-10T09:00:00-05:00"}), stop="tool_use"),
        aa.sse(aa.T("Revise el calendario de Mnemo.")))
    r, ev = aa.enviar(sesion, "Agenda la reunión en Mnemo")
    assert r.status_code == 200 and ev[-1]["motivo"] == "confirmacion", r.text
    cid = ev[0]["conversacion"]
    original, veces = conv_db.quitar_pendiente, []

    def se_corta_una_vez(db, c, crudo, *resto):  # `resto`: lo rechazado, si el bucle lo pasa
        veces.append(1)
        if len(veces) == 1:
            raise RuntimeError("corte inventado")
        return original(db, c, crudo, *resto)

    monkeypatch.setattr(conv_db, "quitar_pendiente", se_corta_una_vez)
    r, ev = aa.decidir(sesion, cid, toolu_ev=True)
    assert ev[-1]["tipo"] == "fin" and ev[-1]["motivo"] == "error", ev
    r, ev = aa.decidir(sesion, cid, toolu_ev=True)  # la tarjeta sigue ahí y se aprueba otra vez
    assert r.status_code == 200, r.text
    assert [n for n, _ in mcp.llamadas].count("mnemo_create_event") == 1
    resultado = api.peticiones[-1]["json"]["messages"][-1]["content"][0]
    assert resultado["tool_use_id"] == "toolu_ev"
    assert not resultado.get("is_error") or "ya se intentó" in resultado["content"]


# ───────────────────────────── 28: fetch de Mnemo sigue donde de verdad se cortó ─────────────────────────────

def _ventana(datos: dict):
    r = hm.resultado_de({"content": [{"type": "text", "text": json.dumps(datos)}], "structuredContent": datos},
                        "https://mnemo.example.org")
    assert len(r.texto_para_modelo()) <= hb.MAX_CONTENIDO
    return json.loads(r.contenido)


@pytest.mark.parametrize("prefijo", ["doc", "deck"])
def test_28_fetch_largo_sigue_donde_se_corto_la_ventana(prefijo):
    texto = "".join(f"[{i:05d}]" for i in range(90_000 // 7))[:90_000]
    vista = _ventana({"id": f"{prefijo}_x", "title": "Largo", "text": texto, "url": "/biblioteca/x",
                      "metadata": {"kind": "document", "offset": 70_000, "next_offset": 160_000}})
    visto = vista["text"]
    assert texto.startswith(visto) and len(visto) > 30_000  # casi todo el presupuesto, no 20 000
    assert vista["metadata"]["next_offset"] == 70_000 + len(visto) and vista["metadata"]["clipped"] is True
    # Sin next_offset (Mnemo la dio entera) también sigue: el resto no cupo en el panel
    vista = _ventana({"id": f"{prefijo}_y", "title": "Entero", "text": texto, "metadata": {"offset": 0}})
    assert vista["metadata"]["next_offset"] == len(vista["text"])


def test_28_los_offsets_de_mnemo_cuentan_unidades_utf16():
    texto = "😀" * 60_000  # 2 unidades UTF-16 por carácter, como cuenta Mnemo (JavaScript)
    vista = _ventana({"id": "doc_e", "title": "Emojis", "text": texto, "metadata": {"offset": 10}})
    assert vista["metadata"]["next_offset"] == 10 + 2 * len(vista["text"])


def test_28_un_lienzo_recortado_sigue_en_el_bloque_que_falta():
    lineas = [f"[blk_{i:04d}] párrafo: " + "texto del bloque " * 9 for i in range(300)]
    texto = "documento de 900 bloques; se muestran 300 desde el 301\n" + "\n".join(lineas)
    vista = _ventana({"id": "canvas_x", "title": "Lienzo", "text": texto,
                      "metadata": {"format": "docx", "body": "blocks", "blocks": 900, "offset": 300,
                                   "next_offset": 600}})
    completas = [x for x in vista["text"].split("\n")[1:] if x in lineas]
    assert 0 < len(completas) < 300
    assert vista["metadata"]["next_offset"] == 300 + len(completas) and vista["metadata"]["clipped"] is True
    # Una hoja de cálculo (o un esquema que no se reconoce): sin un next_offset que salte, y con el aviso
    hoja = "rejilla de 1 hoja\n" + "\n".join(f"  {i}: " + "celda | " * 40 for i in range(2_000))
    vista = _ventana({"id": "canvas_h", "title": "Hoja", "text": hoja,
                      "metadata": {"format": "xlsx", "body": "sheets", "offset": 0, "next_offset": 1}})
    assert "next_offset" not in vista["metadata"] and "ábralo en Mnemo" in vista["metadata"]["nota_panel"]


# ───────────────────────────── 35: una escritura que vence el plazo pudo guardarse ─────────────────────────────

def test_35_una_nota_que_vence_el_plazo_avisa_que_pudo_guardarse_y_no_se_duplica(sesion, monkeypatch):
    db = sesion.app.state.db
    pid = persona(db, nombre="LENTA INVENTADA")
    autorizada(db, pid)
    monkeypatch.setattr(bucle, "PLAZO_HERRAMIENTA_S", 3.0)
    monkeypatch.setattr(hb, "PLAZO_HERRAMIENTA_S", 3.0, raising=False)
    monkeypatch.setattr(hb, "MARGEN_PLAZO_S", 1.0, raising=False)
    previa = acceso.idempotencia_previa

    def lenta(db_, quien, request):  # MongoDB lento: la nota se guarda, pero tarde
        time.sleep(4)
        return previa(db_, quien, request)

    monkeypatch.setattr(acceso, "idempotencia_previa", lenta)
    api = aa.encender(sesion.app, aa.sse(aa.TU("toolu_lenta", "agregar_nota", {"persona_id": pid,
                                                                               "texto": "Volver el lunes"}),
                                         stop="tool_use"), aa.sse(aa.T("Revise la ficha.")))
    r, ev = aa.enviar(sesion, "Anote que hay que volver el lunes")
    cid = ev[0]["conversacion"]
    r, ev = aa.decidir(sesion, cid, toolu_lenta=True)
    assert r.status_code == 200, r.text
    resultado = api.peticiones[-1]["json"]["messages"][-1]["content"][0]
    assert resultado["is_error"] is True and "no se sabe si alcanzó a guardarse" in resultado["content"]
    limite = time.monotonic() + 15
    while not (db.personas.find_one({"_id": pid}).get("notas") and db.idempotencia.find_one({"estado": "hecho"})):
        assert time.monotonic() < limite, "la nota no se guardó"
        time.sleep(0.1)
    # La escritura siguió hasta el final y guardó su respuesta: repetir el mismo tool_use no la duplica
    monkeypatch.setattr(acceso, "idempotencia_previa", previa)
    ctx = aa.contexto(sesion.app, sesion, conversacion_id=cid, tool_use_id="toolu_lenta")
    aa.correr(sesion, aa.ejecutar, H["agregar_nota"], ctx, {"persona_id": pid, "texto": "Volver el lunes"})
    assert len(db.personas.find_one({"_id": pid})["notas"]) == 1


def test_35_el_plazo_de_las_herramientas_es_el_del_bucle():
    assert hb.PLAZO_HERRAMIENTA_S == bucle.PLAZO_HERRAMIENTA_S


# ───────────────────────────── Con el núcleo: la tarjeta de Mnemo y la del bucle ─────────────────────────────

def test_la_tarjeta_de_mnemo_muestra_entero_lo_que_cabe_en_la_del_bucle():
    """La tarjeta del bucle no ofrece lo que llega recortado: la de Mnemo no recorta antes de los topes de aquella, así
    un documento de unos miles de caracteres se puede proponer (y se ve entero)."""
    d = {"name": "mnemo_create_document", "description": "", "annotations": {"readOnlyHint": False},
         "inputSchema": {"type": "object", "properties": {"title": {"type": "string"}, "content": {"type": "string"}}}}
    conf = hm.confirmacion(d, {"title": "Acta inventada", "content": "a" * 3_500})
    assert dict(conf.detalle)["content"] == "a" * 3_500
    assert hm.DETALLE_VALOR >= getattr(bucle, "TARJETA_VALOR", 0)
    assert hm.DETALLE_FILAS >= getattr(bucle, "TARJETA_FILAS", 0)
