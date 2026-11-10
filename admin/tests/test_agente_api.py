"""La API del asistente (app/api/agente.py): estado, conversaciones, las comprobaciones antes del flujo (también el
mensaje que llega mientras se cierra el turno anterior, tras «Detener»), el flujo NDJSON de verdad (uvicorn, sin gzip,
por partes, con latido y desconexión), los cupos del servidor, la retención y la supresión. La Messages API va simulada
(nunca se llama a Anthropic). Solo datos inventados."""
import asyncio
import json
import socket
import threading
import time
from datetime import datetime, timedelta, timezone

import httpx
import pymongo
import pytest
import uvicorn
from fastapi.routing import APIRoute

from ayudas_agente import (T, TU, con_herramientas, decidir, encender, encender_lento, enviar, herramientas_falsas,
                           ndjson, sse, tipos)
from ayudas_g3 import coordinador, persona
from conftest import MONGO, URI

import servidor
from app import acceso
from app import db as bd
from app import migraciones
from app.agente import bucle
from app.agente import conversaciones as conv_db


async def _sin_espera(segundos):  # las rondas que fallan de paso se repiten sin esperar de verdad
    return None


@pytest.fixture
def falsas(monkeypatch):
    lista, registro = herramientas_falsas()
    con_herramientas(monkeypatch, lista)
    monkeypatch.setattr(bucle, "dormir", _sin_espera)
    return registro


def _ajustes(db, **agente):
    base = {"roles": ["admin", "coordinador"], "escritura": True, "mnemo_coordinadores": False, "retencion_dias": 30}
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"agente": {**base, **agente}}}, upsert=True)


def _conversacion(sesion, texto="Hola", respuesta="Hola."):
    encender(sesion.app, sse(T(respuesta)))
    r, ev = enviar(sesion, texto)
    assert r.status_code == 200, r.text
    return ev[0]["conversacion"]


def _detalle(r):
    return r.json()["detail"]


# ───────────────────────────── Rutas y permisos ─────────────────────────────

def test_cada_ruta_declara_un_solo_requiere(cliente):
    rutas = {(m, r.path): r for r in cliente.app.routes if isinstance(r, APIRoute) and r.path.startswith("/api/agente")
             for m in r.methods}
    assert set(rutas) == {("GET", "/api/agente/estado"), ("GET", "/api/agente/conversaciones"),
                          ("GET", "/api/agente/conversaciones/{cid}"), ("DELETE", "/api/agente/conversaciones/{cid}"),
                          ("POST", "/api/agente/mensajes"), ("POST", "/api/agente/confirmaciones"),
                          ("POST", "/api/agente/mnemo/conectar"), ("POST", "/api/agente/mnemo/volver"),
                          ("DELETE", "/api/agente/mnemo")}
    for (m, ruta), r in rutas.items():
        pendientes, deps = list(r.dependant.dependencies), []
        while pendientes:
            d = pendientes.pop()
            if hasattr(d.call, "permisos"):
                deps.append(d.call.permisos)
            pendientes.extend(d.dependencies)
        esperado = ({"cuenta"} if ruta == "/api/agente/estado" else
                    {"agente.conectar"} if ruta.startswith("/api/agente/mnemo") else {"agente.usar"})
        assert deps == [frozenset(esperado)], (m, ruta, deps)


def test_sin_sesion_401(cliente):
    assert cliente.post("/api/agente/mensajes", json={"texto": "hola"}).status_code == 401
    assert cliente.get("/api/agente/estado").status_code == 401


# ───────────────────────────── Estado ─────────────────────────────

SIN_CONECTAR = {"estado": "sin_conectar", "motivo": None, "url": None, "cuenta": None, "alcances": [],
                "modelo": False, "ofrece_modelo": None, "desde": None, "url_sugerida": None}


def test_estado_sin_clave(sesion):
    e = sesion.get("/api/agente/estado").json()
    assert e == {"disponible": False, "motivo": "sin_configurar", "configurado": False, "proveedor": None,
                 "es_admin": True, "escritura": True, "limite": {"usados": 0, "maximo": 300},
                 "mnemo": {"activo": False, "origen": None, "conexion": SIN_CONECTAR}, "sugerencias": []}


def test_estado_con_clave_y_tope_diario(sesion, falsas):
    _conversacion(sesion)
    e = sesion.get("/api/agente/estado").json()
    assert e["disponible"] is True and e["motivo"] is None and e["configurado"] is True
    assert e["proveedor"] == "anthropic"  # sin Mnemo conectado, el modo directo
    assert e["limite"] == {"usados": 1, "maximo": 300} and e["sugerencias"]
    sesion.app.state.db.meta.update_one({"_id": "ajustes"}, {"$set": {"agente_mensajes_diarios": {"admin": 7}}},
                                        upsert=True)
    assert sesion.get("/api/agente/estado").json()["limite"] == {"usados": 1, "maximo": 7}


def test_estado_del_coordinador_y_del_planillero(sesion, como, falsas):
    encender(sesion.app)
    k = coordinador(sesion.app, sesion.app.state.db)
    e = k.get("/api/agente/estado").json()
    assert e["disponible"] is True and e["es_admin"] is False and e["limite"]["maximo"] == 150
    p = como("planillero")
    e = p.get("/api/agente/estado").json()
    assert e["disponible"] is False and e["motivo"] == "rol" and e["sugerencias"] == []  # denegar por defecto
    _ajustes(sesion.app.state.db, roles=["admin"])
    assert k.get("/api/agente/estado").json()["motivo"] == "rol"


def test_estado_con_mnemo(sesion, monkeypatch):
    from dataclasses import replace

    from ayudas_agente import conectar_mnemo

    from app.agente.herramientas import mnemo
    monkeypatch.setattr(mnemo, "disponible_para", lambda quien, ajustes, cfg: quien.es_admin)
    sesion.app.state.cfg = replace(sesion.app.state.cfg, mnemo_url="https://mnemo.example.org/mcp")
    e = sesion.get("/api/agente/estado").json()["mnemo"]  # una dirección sugerida no es una conexión
    assert e == {"activo": False, "origen": None, "conexion": {**SIN_CONECTAR,
                                                               "url_sugerida": "https://mnemo.example.org/mcp"}}
    conectar_mnemo(sesion.app)
    e = sesion.get("/api/agente/estado").json()["mnemo"]
    assert e["activo"] is True and e["origen"] == "https://mnemo.example.org"
    assert e["conexion"]["estado"] == "conectada" and e["conexion"]["modelo"] is True
    monkeypatch.setattr(mnemo, "disponible_para", lambda quien, ajustes, cfg: False)
    e = sesion.get("/api/agente/estado").json()["mnemo"]
    assert e["activo"] is False and e["origen"] is None and e["conexion"]["estado"] == "conectada"


def test_ajustes_raros_toman_los_valores_por_defecto(sesion, falsas):
    sesion.app.state.db.meta.update_one({"_id": "ajustes"}, {"$set": {
        "agente": {"roles": "todos", "escritura": "si", "retencion_dias": 9999},
        "agente_mensajes_diarios": {"admin": -3}}}, upsert=True)
    e = sesion.get("/api/agente/estado").json()
    assert e["escritura"] is True and e["limite"]["maximo"] == 300 and e["disponible"] is False  # no hay clave
    encender(sesion.app)
    assert sesion.get("/api/agente/estado").json()["disponible"] is True


# ───────────────────────────── Antes del flujo: JSON normal ─────────────────────────────

def test_sin_clave_503(sesion):
    r, _ = enviar(sesion, "Hola")
    assert r.status_code == 503 and _detalle(r)["codigo"] == "sin_configurar"
    # Sin nombres de variables: lo ve quien conversa, y lo que hay que hacer es conectar Mnemo en Ajustes
    assert _detalle(r)["mensaje"] == ("El asistente no está conectado a un modelo: el administrador lo conecta con "
                                      "Mnemo en Ajustes → Asistente.")
    r = sesion.post("/api/agente/confirmaciones", json={"conversacion": 1, "decisiones": [{"id": "x", "aprobar": True}]})
    assert r.status_code == 503 and _detalle(r)["codigo"] == "sin_configurar"


def test_rol_apagado_403(sesion, falsas):
    encender(sesion.app)
    _ajustes(sesion.app.state.db, roles=["admin"])
    k = coordinador(sesion.app, sesion.app.state.db)
    r = k.post("/api/agente/mensajes", json={"texto": "Hola"})
    assert r.status_code == 403 and _detalle(r)["codigo"] == "agente_apagado"
    assert k.get("/api/agente/conversaciones").status_code == 403
    r = k.post("/api/agente/confirmaciones", json={"conversacion": 1, "decisiones": [{"id": "x", "aprobar": True}]})
    assert r.status_code == 403 and _detalle(r)["codigo"] == "agente_apagado"


def test_planillero_no_lo_usa_hasta_que_se_habilita(sesion, como, falsas, monkeypatch):
    from pydantic import BaseModel

    from app.agente.herramientas.base import Herramienta, Resultado

    class Nada(BaseModel):
        pass

    async def tablero(ctx, a):
        return Resultado({})
    lista, _ = herramientas_falsas()
    con_herramientas(monkeypatch, [*lista, Herramienta("tablero_falso", "Tablero (prueba).", Nada, "lectura",
                                                       ("tablero.ver",), "Mirando el tablero", tablero)])
    api = encender(sesion.app, sse(T("Hola, planillero.")))
    p = como("planillero")
    r = p.post("/api/agente/mensajes", json={"texto": "Hola"})
    assert r.status_code == 403 and _detalle(r)["codigo"] in ("permiso", "agente_apagado")
    # El administrador lo habilita (el permiso agente.usar lo agrega acceso.py; aquí por si aún no está)
    if "agente.usar" not in acceso.PERMISOS["planillero"]:
        monkeypatch.setitem(acceso.PERMISOS, "planillero", acceso.PERMISOS["planillero"] | {"agente.usar"})
    _ajustes(sesion.app.state.db, roles=["admin", "coordinador", "planillero"])
    r, ev = enviar(p, "Hola")
    assert r.status_code == 200 and ev[-1] == {"tipo": "fin", "motivo": "listo", "limite": {"usados": 1, "maximo": 40}}
    # Solo se le ofrece lo que su rol puede: el tablero es de A y K
    assert [t["name"] for t in api.peticiones[0]["json"]["tools"]] == ["contar_falsa", "nota_falsa", "falla_falsa"]
    conv = sesion.app.state.db[conv_db.CONVERSACIONES].find_one({"_id": ev[0]["conversacion"]})
    assert conv["uid"] == p.uid and "(planillero)" in conv["sistema"]


def test_tope_diario_429(sesion, falsas):
    sesion.app.state.db.meta.update_one({"_id": "ajustes"}, {"$set": {"agente_mensajes_diarios": {"admin": 1}}},
                                        upsert=True)
    encender(sesion.app, sse(T("Uno.")))
    r, ev = enviar(sesion, "Uno")
    assert r.status_code == 200 and ev[-1]["limite"] == {"usados": 1, "maximo": 1}
    r, _ = enviar(sesion, "Dos", conversacion=ev[0]["conversacion"])
    assert r.status_code == 429 and _detalle(r)["codigo"] == "volumen" and "1 mensajes" in _detalle(r)["mensaje"]
    conv = sesion.app.state.db[conv_db.CONVERSACIONES].find_one({"_id": ev[0]["conversacion"]})
    assert conv["ocupada_hasta"] is None  # el candado no quedó tomado por el 429
    assert not sesion.app.state.agente_ocupacion.usuarios


def test_ocupada_409(sesion, falsas, monkeypatch):
    monkeypatch.setattr(bucle, "ESPERA_OCUPADA_S", 0.3)  # lo que espera a que se suelte un turno que se cierra
    db = sesion.app.state.db
    cid = _conversacion(sesion)
    db[conv_db.CONVERSACIONES].update_one({"_id": cid}, {"$set": {
        "ocupada_hasta": datetime.now(timezone.utc) + timedelta(minutes=5), "turno": "otro"}})
    encender(sesion.app, sse(T("No debería.")))
    t0 = time.monotonic()
    r, _ = enviar(sesion, "Otra", conversacion=cid)
    assert r.status_code == 409 and _detalle(r)["codigo"] == "ocupada"
    assert 0.3 <= time.monotonic() - t0 < 5  # esperó a que se soltara, y no más que eso
    # Un turno en otra conversación de la misma persona también la ocupa (uno a la vez por persona)
    r, _ = enviar(sesion, "Nueva")
    assert r.status_code == 409 and _detalle(r)["codigo"] == "ocupada"
    assert sesion.delete(f"/api/agente/conversaciones/{cid}").status_code == 409
    # Un candado vencido (un proceso que se cayó) ya no estorba
    db[conv_db.CONVERSACIONES].update_one({"_id": cid}, {"$set": {
        "ocupada_hasta": datetime.now(timezone.utc) - timedelta(seconds=1)}})
    r, ev = enviar(sesion, "Ahora sí", conversacion=cid)
    assert r.status_code == 200 and ev[-1]["motivo"] == "listo"
    # Y el candado en memoria (un turno en curso en este proceso)
    assert sesion.app.state.agente_ocupacion.reservar(0, None) is None
    try:
        r, _ = enviar(sesion, "Otra vez", conversacion=cid)
        assert r.status_code == 409 and _detalle(r)["codigo"] == "ocupada"
    finally:
        sesion.app.state.agente_ocupacion.soltar(0, None)
    assert not sesion.app.state.agente_ocupacion.usuarios  # lo que esperó no quedó reservado


@pytest.mark.parametrize("caso", ["este_proceso", "otro_proceso", "otra_conversacion", "confirmacion"])
def test_un_turno_que_se_esta_cerrando_no_da_409(sesion, falsas, monkeypatch, caso):
    """Regresión del CI (test_flujo_real_por_partes_y_detener en una máquina lenta): tras «Detener», el mensaje
    siguiente llegaba antes de que el turno cortado soltara sus candados y recibía 409 «ocupada». Ahora espera a que se
    suelten. El turno que se cierra los suelta recién DESPUÉS de que el turno nuevo los encontró tomados, así que la
    prueba no depende de la velocidad de la máquina. Casos: el turno que se cierra corre en este proceso (la reserva en
    memoria, marcada como cerrándose, y el candado de MongoDB; sin la marca es un turno vivo y el 409 llega en el acto,
    test_remate_nucleo.py) o en otro (solo el de MongoDB); ocupa otra conversación de la persona (el mensaje nuevo
    empieza una); o lo que llega es la aprobación de una tarjeta."""
    db = sesion.app.state.db
    ocupacion = bucle.ocupacion_de(sesion.app)
    if caso == "confirmacion":
        pid = persona(db, nombre="LUCIA INVENTADA DE PRUEBA")
        encender(sesion.app, sse(TU("toolu_c", "nota_falsa", {"persona_id": pid, "texto": "Llamar el lunes"}),
                                 stop="tool_use"))
        r, ev = enviar(sesion, "Anota que la llame el lunes")
        assert ev[-1]["motivo"] == "confirmacion", ev
        cid = ev[0]["conversacion"]
    else:
        cid = _conversacion(sesion)
    vio = threading.Event()  # el turno nuevo encontró tomado el candado que espera

    def espiar(funcion, ocupado):
        def espia(*a):
            r = funcion(*a)
            if ocupado(r):
                vio.set()
            return r
        return espia

    if caso == "este_proceso":
        assert ocupacion.reservar(0, cid) is None
        ocupacion.cerrar(0, cid)  # lo que hace el turno cortado al notar que el navegador se fue
        monkeypatch.setattr(bucle.Ocupacion, "reservar", espiar(bucle.Ocupacion.reservar, lambda r: r == "ocupada"))
    elif caso == "otra_conversacion":
        monkeypatch.setattr(conv_db, "otra_ocupada", espiar(conv_db.otra_ocupada, lambda r: r is True))
    else:
        monkeypatch.setattr(conv_db, "tomar", espiar(conv_db.tomar, lambda r: r is None))
    # El turno que se cierra: el candado de MongoDB (y, en este proceso, la reserva)
    db[conv_db.CONVERSACIONES].update_one({"_id": cid}, {"$set": {
        "ocupada_hasta": datetime.now(timezone.utc) + timedelta(minutes=5), "turno": "cerrando"}})

    def cerrar():
        assert vio.wait(10)
        conv_db.soltar(db, cid, "cerrando")
        if caso == "este_proceso":
            ocupacion.soltar(0, cid)

    hilo = threading.Thread(target=cerrar, daemon=True)
    hilo.start()
    if caso == "confirmacion":
        encender(sesion.app, sse(T("Quedó sin anotar.")))
        r, ev = decidir(sesion, cid, toolu_c=False)
    else:
        encender(sesion.app, sse(T("Aquí sigo.")))
        r, ev = enviar(sesion, "¿Sigues?", conversacion=None if caso == "otra_conversacion" else cid)
    hilo.join(15)
    assert vio.is_set() and r.status_code == 200, (r.status_code, r.text[:300])
    assert ev[-1]["motivo"] == "listo"
    assert not ocupacion.usuarios and not ocupacion.conversaciones


def test_el_turno_que_se_cierra_deja_la_conversacion_larga_409(sesion, falsas, monkeypatch):
    """Lo que se leyó antes de esperar puede haber cambiado: si el turno que se cerraba dejó la conversación larga, el
    mensaje nuevo recibe 409 «larga» (y no queda nada tomado)."""
    db = sesion.app.state.db
    cid = _conversacion(sesion)
    vio = threading.Event()
    tomar = conv_db.tomar

    def espia(*a):
        r = tomar(*a)
        if r is None:
            vio.set()
        return r

    monkeypatch.setattr(conv_db, "tomar", espia)
    db[conv_db.CONVERSACIONES].update_one({"_id": cid}, {"$set": {
        "ocupada_hasta": datetime.now(timezone.utc) + timedelta(minutes=5), "turno": "cerrando"}})

    def cerrar():
        assert vio.wait(10)
        db[conv_db.CONVERSACIONES].update_one({"_id": cid}, {"$set": {"n_mensajes": conv_db.TOPE_MENSAJES}})
        conv_db.soltar(db, cid, "cerrando")

    hilo = threading.Thread(target=cerrar, daemon=True)
    hilo.start()
    encender(sesion.app, sse(T("No debería.")))
    r, _ = enviar(sesion, "¿Sigues?", conversacion=cid)
    hilo.join(15)
    assert r.status_code == 409 and _detalle(r)["codigo"] == "larga"
    conv = db[conv_db.CONVERSACIONES].find_one({"_id": cid})
    assert conv["ocupada_hasta"] is None and not bucle.ocupacion_de(sesion.app).usuarios


def test_tope_de_turnos_del_proceso_503(sesion, falsas):
    encender(sesion.app, sse(T("Hola.")))
    sesion.app.state.agente_ocupacion = bucle.Ocupacion(maximo=0)
    r, _ = enviar(sesion, "Hola")
    assert r.status_code == 503 and _detalle(r)["codigo"] == "saturado" and r.headers["retry-after"] == "5"


def test_larga_409(sesion, falsas):
    cid = _conversacion(sesion)
    sesion.app.state.db[conv_db.CONVERSACIONES].update_one({"_id": cid}, {"$set": {"n_mensajes": 400}})
    encender(sesion.app, sse(T("x")))
    r, _ = enviar(sesion, "Más", conversacion=cid)
    assert r.status_code == 409 and _detalle(r)["codigo"] == "larga"


def test_conversacion_ajena_o_inexistente_404(sesion, falsas):
    cid = _conversacion(sesion)
    k = coordinador(sesion.app, sesion.app.state.db)
    encender(sesion.app, sse(T("x")))
    assert k.get(f"/api/agente/conversaciones/{cid}").status_code == 404
    assert k.delete(f"/api/agente/conversaciones/{cid}").status_code == 404
    r = k.post("/api/agente/mensajes", json={"conversacion": cid, "texto": "Hola"})
    assert r.status_code == 404 and _detalle(r)["codigo"] == "no_existe"
    r = k.post("/api/agente/confirmaciones", json={"conversacion": cid, "decisiones": [{"id": "x", "aprobar": True}]})
    assert r.status_code == 404
    assert k.get("/api/agente/conversaciones").json() == {"conversaciones": []}
    assert sesion.get("/api/agente/conversaciones/999999").status_code == 404
    assert sesion.app.state.db[conv_db.CONVERSACIONES].find_one({"_id": cid}) is not None


def test_sin_pendientes_409(sesion, falsas):
    cid = _conversacion(sesion)
    r, _ = decidir(sesion, cid, toolu_x=True)
    assert r.status_code == 409 and _detalle(r)["codigo"] == "sin_pendientes"


@pytest.mark.parametrize("cuerpo", [{"texto": ""}, {"texto": "   "}, {"texto": "x" * 4001}, {},
                                    {"texto": "hola", "conversacion": 0}, {"texto": "hola", "contexto": "no"},
                                    {"texto": "hola", "conversacion": 10**15}])
def test_mensaje_invalido_422(sesion, cuerpo):
    assert sesion.post("/api/agente/mensajes", json=cuerpo).status_code == 422


@pytest.mark.parametrize("cuerpo", [{"conversacion": 1, "decisiones": []},
                                    {"conversacion": 1, "decisiones": [{"id": "x", "aprobar": "si"}]},
                                    {"conversacion": 1, "decisiones": [{"id": "x", "aprobar": True}] * 21},
                                    {"decisiones": [{"id": "x", "aprobar": True}]}])
def test_confirmacion_invalida_422(sesion, cuerpo):
    assert sesion.post("/api/agente/confirmaciones", json=cuerpo).status_code == 422


# ───────────────────────────── Historial ─────────────────────────────

def test_historial_y_lista(sesion, falsas):
    pid = persona(sesion.app.state.db, nombre="GINA INVENTADA DE PRUEBA")
    encender(sesion.app,
             sse(T("Cuento."), TU("toolu_1", "contar_falsa", {"lugar": "Casco"}),
                 TU("toolu_2", "nota_falsa", {"persona_id": pid, "texto": "Hola"}), stop="tool_use"))
    _, ev = enviar(sesion, "  Cuenta   y anota  ")
    cid = ev[0]["conversacion"]
    assert ev[0]["titulo"] == "Cuenta y anota"
    lista = sesion.get("/api/agente/conversaciones").json()["conversaciones"]
    assert len(lista) == 1 and lista[0]["id"] == cid and lista[0]["titulo"] == "Cuenta y anota"
    assert lista[0]["pendiente"] is True and datetime.fromisoformat(lista[0]["actualizada"])
    v = sesion.get(f"/api/agente/conversaciones/{cid}").json()
    assert v["id"] == cid and v["titulo"] == "Cuenta y anota"
    assert v["mensajes"] == [
        {"rol": "usuario", "texto": "  Cuenta   y anota  "},
        {"rol": "asistente", "partes": [
            {"tipo": "texto", "texto": "Cuento."},
            {"tipo": "herramienta", "id": "toolu_1", "nombre": "contar_falsa", "etiqueta": "Contando personas",
             "estado": "ok", "resumen": "3 personas"},
            {"tipo": "herramienta", "id": "toolu_2", "nombre": "nota_falsa", "etiqueta": "Agregando la nota",
             "estado": "pendiente", "resumen": ""}]}]
    assert [p["id"] for p in v["pendientes"]] == ["toolu_2"]
    # Al rechazar, el historial queda con el estado final
    encender(sesion.app, sse(T("Bueno.")))
    decidir(sesion, cid, toolu_2=False)
    v = sesion.get(f"/api/agente/conversaciones/{cid}").json()
    assert v["pendientes"] == [] and v["mensajes"][1]["partes"][2]["estado"] == "rechazada"
    assert v["mensajes"][1]["partes"][3] == {"tipo": "texto", "texto": "Bueno."}
    assert sesion.get("/api/agente/conversaciones").json()["conversaciones"][0]["pendiente"] is False


def test_lista_solo_las_30_mas_recientes(sesion):
    db = sesion.app.state.db
    for i in range(35):
        conv_db.crear(db, 1000 + i, 0, f"Conversación {i}", "s", [], [], 30, "t", "m")
        conv_db.soltar(db, 1000 + i, "t")
    lista = sesion.get("/api/agente/conversaciones").json()["conversaciones"]
    assert len(lista) == 30 and lista[0]["titulo"] == "Conversación 34"


def test_borrar_conversacion(sesion, falsas):
    cid = _conversacion(sesion)
    otra = _conversacion(sesion, "Otra")
    assert sesion.delete(f"/api/agente/conversaciones/{cid}").json() == {"ok": True}
    db = sesion.app.state.db
    assert db[conv_db.CONVERSACIONES].find_one({"_id": cid}) is None
    assert db[conv_db.MENSAJES].count_documents({"conversacion": cid}) == 0
    assert db[conv_db.MENSAJES].count_documents({"conversacion": otra}) == 2
    assert sesion.get(f"/api/agente/conversaciones/{cid}").status_code == 404
    assert sesion.delete(f"/api/agente/conversaciones/{cid}").status_code == 404


# ───────────────────────────── Retención y supresión ─────────────────────────────

def test_indices_de_las_colecciones_del_asistente(sesion):
    db = sesion.app.state.db
    ttl = lambda col: {next(iter(i["key"])): i["expireAfterSeconds"] for i in db[col].list_indexes()  # noqa: E731
                       if "expireAfterSeconds" in i}
    assert ttl(conv_db.CONVERSACIONES) == {"expira": 0} and ttl(conv_db.MENSAJES) == {"expira": 0}
    assert ttl(conv_db.USO) == {"ts": 180 * 24 * 3600}
    unicos = [i["key"] for i in db[conv_db.MENSAJES].list_indexes() if i.get("unique")]
    assert [list(k.keys()) for k in unicos] == [["conversacion", "seq"]]


def test_la_retencion_de_ajustes_fija_el_vencimiento(sesion, falsas):
    _ajustes(sesion.app.state.db, retencion_dias=3)
    cid = _conversacion(sesion)
    c = sesion.app.state.db[conv_db.CONVERSACIONES].find_one({"_id": cid})
    assert 2 <= (c["expira"] - datetime.now(timezone.utc)).days <= 3


def test_suprimir_una_persona_borra_las_conversaciones_que_la_vieron(sesion, falsas):
    db = sesion.app.state.db
    pid = persona(db, nombre="HUGO INVENTADO DE PRUEBA")
    encender(sesion.app, sse(TU("toolu_p", "contar_falsa", {"lugar": "Casco", "persona_id": pid}), stop="tool_use"),
             sse(T("Hugo vive en el casco.")))
    _, ev = enviar(sesion, "¿Dónde vive Hugo?")
    cid = ev[0]["conversacion"]
    otra = _conversacion(sesion, "Algo sin personas")
    assert db[conv_db.CONVERSACIONES].find_one({"_id": cid})["personas"] == [pid]
    assert db[conv_db.MENSAJES].count_documents({"conversacion": cid}) == 4
    r = sesion.delete(f"/api/personas/{pid}")
    assert r.status_code == 200, r.text
    assert db[conv_db.CONVERSACIONES].find_one({"_id": cid}) is None
    assert db[conv_db.MENSAJES].count_documents({"conversacion": cid}) == 0
    assert db[conv_db.CONVERSACIONES].find_one({"_id": otra}) is not None
    assert sesion.get(f"/api/agente/conversaciones/{cid}").status_code == 404


def test_la_reconciliacion_borra_lo_que_quedo_de_una_suprimida(sesion):
    db = sesion.app.state.db
    viva = persona(db, nombre="IVAN INVENTADO DE PRUEBA")
    suprimida = persona(db, nombre="SUPRIMIDO")
    db.personas.update_one({"_id": suprimida}, {"$set": {"eliminado": True}})
    db.acercamientos.insert_one({"_id": 1, "persona_id": viva, "ts": bd.ahora(), "nota": "nota de una persona viva",
                                 "telefono": "3001234567"})
    conv_db.crear(db, 77, 0, "Vieja", "s", [], [], 30, "t", "m")
    db[conv_db.CONVERSACIONES].update_one({"_id": 77}, {"$set": {"personas": [viva, suprimida]}})
    conv_db.guardar(db, 77, 0, datetime.now(timezone.utc), "user", [{"type": "text", "text": "x"}])
    hechos = migraciones.migrar(db)
    assert hechos["reconciliacion"]["suprimidas"] == 1
    assert db[conv_db.CONVERSACIONES].find_one({"_id": 77}) is None
    assert db[conv_db.MENSAJES].count_documents({"conversacion": 77}) == 0
    # La otra persona de la conversación no estaba suprimida: lo suyo no se toca
    assert db.acercamientos.find_one({"_id": 1})["nota"] == "nota de una persona viva"


# ───────────────────────────── El flujo ─────────────────────────────

def test_el_flujo_no_va_comprimido_y_lo_demas_si(sesion, falsas):
    encender(sesion.app, sse(T("x" * 3000)))
    r = sesion.post("/api/agente/mensajes", json={"texto": "Hola"}, headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200 and "content-encoding" not in r.headers
    assert r.headers["content-type"].startswith("application/x-ndjson")
    assert r.headers["x-accel-buffering"] == "no" and r.headers["cache-control"] == "no-store"
    assert "default-src 'self'" in r.headers["content-security-policy"]
    cid = ndjson(r.text)[0]["conversacion"]
    v = sesion.get(f"/api/agente/conversaciones/{cid}", headers={"Accept-Encoding": "gzip"})
    assert v.headers["content-encoding"] == "gzip" and len(v.json()["mensajes"][1]["partes"][0]["texto"]) == 3000


def test_latido_sin_otros_eventos(sesion, falsas, monkeypatch):
    monkeypatch.setattr(bucle, "LATIDO_S", 0.05)
    encender_lento(sesion.app, sse(T("Hola.")), pausa=0.15)
    r = sesion.post("/api/agente/mensajes", json={"texto": "Hola"})
    ev = ndjson(r.text)
    assert {"tipo": "latido"} in ev and ev[0]["tipo"] == "inicio" and ev[-1]["tipo"] == "fin"
    assert "".join(e["texto"] for e in ev if e["tipo"] == "texto") == "Hola."


def _servir(app):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    srv = uvicorn.Server(uvicorn.Config(app, http="h11", lifespan="on", log_level="warning", access_log=False,
                                        server_header=False, timeout_graceful_shutdown=2))
    hilo = threading.Thread(target=srv.run, kwargs={"sockets": [sock]}, daemon=True)
    hilo.start()
    return srv, hilo, sock


def _esperar(condicion, segundos=15.0):
    fin = time.time() + segundos
    while time.time() < fin and not condicion():
        time.sleep(0.05)
    return condicion()


@pytest.fixture
def servido(cfg, tmp_path, monkeypatch):
    """El servidor único de verdad (uvicorn h11, como en Railway, con LimitePanel y el panel en /panel) en un puerto
    libre. Devuelve (base, app del panel)."""
    if not MONGO:
        pytest.skip("No hay MongoDB para las pruebas del servidor")
    lista, _ = herramientas_falsas()
    con_herramientas(monkeypatch, lista)
    sitio = tmp_path / "site"
    sitio.mkdir()
    (sitio / "index.html").write_text("<!doctype html><title>Inicio</title>INICIO", encoding="utf-8")
    app = servidor.crear_servidor(cfg, sitio)
    srv, hilo, sock = _servir(app)
    try:
        assert _esperar(lambda: srv.started and app.state.panel is not None and app.state.panel.state.listo)
        yield f"http://127.0.0.1:{sock.getsockname()[1]}", app.state.panel
    finally:
        srv.should_exit = True
        hilo.join(15)
        sock.close()
        with pymongo.MongoClient(URI) as m:
            m.drop_database(cfg.mongodb_db)


def _entrar(c, cfg):
    r = c.post("/panel/api/login", json={"usuario": cfg.usuario, "clave": cfg.clave})
    assert r.status_code == 200, r.text
    c.headers["X-CSRF-Token"] = r.json()["csrf"]


def test_flujo_de_verdad_llega_por_partes_y_sin_gzip(servido, cfg):
    base, panel = servido
    encender_lento(panel, sse(T("Hola, "), T("ya miro "), T("la base.")), pausa=0.2)
    llegadas = []
    with httpx.Client(base_url=base, timeout=30) as c:
        _entrar(c, cfg)
        t0 = time.perf_counter()
        with c.stream("POST", "/panel/api/agente/mensajes", json={"texto": "Hola"},
                      headers={"Accept-Encoding": "gzip, deflate, br"}) as r:
            assert r.status_code == 200 and "content-encoding" not in r.headers
            for linea in r.iter_lines():
                llegadas.append((time.perf_counter() - t0, json.loads(linea)))
    ev = [e for _, e in llegadas]
    assert tipos(ev) == ["inicio", "texto", "fin"] and ev[-1]["motivo"] == "listo"
    t_textos = [t for t, e in llegadas if e["tipo"] == "texto"]
    # Cada trozo llega cuando sale (no todos juntos al final, como pasaba con el GZip de Starlette)
    assert len(t_textos) == 6 and t_textos[-1] - t_textos[0] > 1.0
    assert llegadas[-1][0] - t_textos[0] > 1.0


def test_desconectarse_suelta_el_candado_y_no_guarda_a_medias(servido, cfg):
    base, panel = servido
    api = encender_lento(panel, sse(*[T(f"parte {i}. ") for i in range(40)]), pausa=0.2)
    db = panel.state.db
    with httpx.Client(base_url=base, timeout=30) as c:
        _entrar(c, cfg)
        with c.stream("POST", "/panel/api/agente/mensajes", json={"texto": "Cuéntame algo largo"}) as r:
            for linea in r.iter_lines():
                e = json.loads(linea)
                if e["tipo"] == "inicio":
                    cid = e["conversacion"]
                if e["tipo"] == "texto":
                    break  # la persona cierra el panel (o pulsa Detener) a mitad de la respuesta
        assert _esperar(lambda: not panel.state.agente_ocupacion.usuarios, 10)
        conv = db[conv_db.CONVERSACIONES].find_one({"_id": cid})
        assert conv["ocupada_hasta"] is None and conv["turno"] is None
        assert [m["rol"] for m in db[conv_db.MENSAJES].find({"conversacion": cid})] == ["user"]
        assert len(api.peticiones) == 1 and not api.guion  # una sola ronda, cortada a la mitad
        # La conversación queda libre para el mensaje siguiente
        encender_lento(panel, sse(T("Aquí sigo.")), pausa=0)
        r = c.post("/panel/api/agente/mensajes", json={"conversacion": cid, "texto": "¿Sigues?"})
        assert r.status_code == 200 and ndjson(r.text)[-1]["motivo"] == "listo"


def test_detener_y_escribir_enseguida_no_da_409(servido, cfg, monkeypatch):
    """Lo que falló en el CI, en el servidor de verdad: la persona pulsa «Detener» (el navegador corta la respuesta) y
    manda otro mensaje al instante. El turno cortado tarda en soltar sus candados a propósito: los suelta recién cuando
    el mensaje nuevo ya los encontró tomados (así no depende de la velocidad de la máquina). El mensaje nuevo espera y
    entra; antes recibía 409 «ocupada»."""
    base, panel = servido
    encender_lento(panel, sse(*[T(f"parte {i}. ") for i in range(40)]), pausa=0.2)
    vio = threading.Event()
    reservar, soltar = bucle.Ocupacion.reservar, conv_db.soltar

    def espiar(self, uid, cid):
        motivo = reservar(self, uid, cid)
        if motivo == "ocupada":
            vio.set()
        return motivo

    def soltar_tarde(db, cid, turno):
        vio.wait(10)
        soltar(db, cid, turno)

    monkeypatch.setattr(bucle.Ocupacion, "reservar", espiar)
    monkeypatch.setattr(conv_db, "soltar", soltar_tarde)
    with httpx.Client(base_url=base, timeout=30) as c:
        _entrar(c, cfg)
        with c.stream("POST", "/panel/api/agente/mensajes", json={"texto": "Cuéntame algo largo"}) as r:
            for linea in r.iter_lines():
                e = json.loads(linea)
                if e["tipo"] == "inicio":
                    cid = e["conversacion"]
                if e["tipo"] == "texto":
                    break  # «Detener»
        encender_lento(panel, sse(T("Aquí sigo.")), pausa=0)
        r = c.post("/panel/api/agente/mensajes", json={"conversacion": cid, "texto": "¿Sigues?"})
        assert r.status_code == 200, r.text
        ev = ndjson(r.text)
    assert vio.is_set() and ev[-1]["motivo"] == "listo"
    assert "".join(e["texto"] for e in ev if e["tipo"] == "texto") == "Aquí sigo."
    db = panel.state.db
    assert [m["rol"] for m in db[conv_db.MENSAJES].find({"conversacion": cid}, sort=[("seq", 1)])] == [
        "user", "user", "assistant"]  # lo cortado no se guardó a medias
    assert _esperar(lambda: not panel.state.agente_ocupacion.usuarios, 10)


# ───────────────────────────── Cupos del servidor ─────────────────────────────

def _app_lenta(segundos):
    async def app(scope, receive, send):
        await asyncio.sleep(segundos)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})
    return app


def test_el_asistente_tiene_cupos_propios_en_el_servidor():
    async def probar():
        limite = servidor.LimitePanel(_app_lenta(0.4), cupos=2, espera_s=0.15, cupos_agente=1)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=limite), base_url="http://t") as c:
            rs = await asyncio.gather(c.post("/api/agente/mensajes"), c.post("/api/agente/confirmaciones"),
                                      c.get("/api/x"), c.get("/api/y"))
            agente, api = sorted(r.status_code for r in rs[:2]), [r.status_code for r in rs[2:]]
            assert agente == [200, 503] and api == [200, 200]  # el turno largo no le quita cupo a la API
            assert next(r for r in rs[:2] if r.status_code == 503).text == servidor.OCUPADO
        limite = servidor.LimitePanel(_app_lenta(0.3), cupos=1, espera_s=0.1, cupos_agente=2)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=limite), base_url="http://t") as c:
            rs = await asyncio.gather(c.post("/api/agente/mensajes"), c.post("/api/agente/mensajes"), c.get("/api/x"))
            assert [r.status_code for r in rs] == [200, 200, 200]
    asyncio.run(probar())
    assert servidor.CUPOS_AGENTE == 4 and servidor.RUTAS_AGENTE == {"/api/agente/mensajes",
                                                                    "/api/agente/confirmaciones"}


def test_escritura_aprobada_por_la_api_interna_bajo_panel(servido, cfg):
    """En el servidor de verdad (panel montado en /panel): la herramienta escribe por la API interna con la cookie y
    el CSRF de la petición del chat, y la clave de idempotencia evita la nota doble."""
    base, panel = servido
    db = panel.state.db
    pid = persona(db, nombre="KAREN INVENTADA DE PRUEBA")
    encender(panel, sse(TU("toolu_k", "nota_falsa", {"persona_id": pid, "texto": "Visitar el martes"}),
                        stop="tool_use"), sse(T("Quedó la nota.")))
    with httpx.Client(base_url=base, timeout=30) as c:
        _entrar(c, cfg)
        r = c.post("/panel/api/agente/mensajes", json={"texto": "Anota la visita"})
        ev = ndjson(r.text)
        assert ev[-1]["motivo"] == "confirmacion", ev
        cid = ev[0]["conversacion"]
        r = c.post("/panel/api/agente/confirmaciones", json={"conversacion": cid, "decisiones": [
            {"id": "toolu_k", "aprobar": True}]})
        ev = ndjson(r.text)
        assert [e["estado"] for e in ev if e["tipo"] == "herramienta"] == ["aprobada", "ok"], ev
        assert ev[-1]["motivo"] == "listo"
    notas = db.personas.find_one({"_id": pid})["notas"]
    assert [n["texto"] for n in notas] == ["Visitar el martes"] and notas[0]["autor_uid"] == 0
    assert db.idempotencia.find_one({"_id": f"0:agente.{cid}.toolu_k"})["estado"] == "hecho"
