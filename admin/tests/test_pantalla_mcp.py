"""La pantalla en off de la presentación (app/pantalla.py) y el servidor MCP que la maneja (app/api/mcp.py).

* Sin MongoDB: la herramienta compartida (`presentacion_en_pantalla`) y el protocolo MCP con una base en memoria, la ruta
  /api/mcp de punta a punta (con `obtener_db` reemplazada) y, con Node, el puente del navegador.
* Con MongoDB: la pantalla que pregunta por su estado, la clave MCP de Cuenta y un agente que la maneja por MCP.
Solo datos inventados: la presentación es pública y la pantalla no guarda datos de personas."""
import asyncio
import copy
import json
import shutil
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app import pantalla
from app.agente import guion as guion_presentacion
from app.agente.herramientas import interfaz as hi
from app.api import mcp
from app.api.pantalla import huella_clave

WEB = Path(__file__).resolve().parents[1] / "web"
G = guion_presentacion.cargar()
VIVIENDA = G.capitulos[G.por_id("vivienda")]


# ───────────────────────────── Una base en memoria (lo poco que usan pantalla y mcp) ─────────────────────────────

class _Coleccion:
    def __init__(self):
        self.docs: dict = {}

    @staticmethod
    def _valor(d: dict, k: str):
        for parte in k.split("."):
            d = d.get(parte) if isinstance(d, dict) else None
        return d

    @classmethod
    def _casa(cls, d: dict, filtro: dict) -> bool:
        return all(cls._valor(d, k) == v for k, v in (filtro or {}).items())

    @staticmethod
    def _poner(d: dict, k: str, v) -> None:
        *camino, ultima = k.split(".")
        for parte in camino:
            d = d.setdefault(parte, {})
        d[ultima] = v

    def find_one(self, filtro=None, proyeccion=None):
        for d in self.docs.values():
            if self._casa(d, filtro):
                return copy.deepcopy(d)
        return None

    def find_one_and_update(self, filtro, cambios, upsert=False, return_document=None):
        d = next((x for x in self.docs.values() if self._casa(x, filtro)), None)
        if d is None:
            if not upsert:
                return None
            d = dict(filtro)
            self.docs[d["_id"]] = d
        for k, v in cambios.get("$set", {}).items():
            self._poner(d, k, copy.deepcopy(v))
        for k, v in cambios.get("$inc", {}).items():
            d[k] = d.get(k, 0) + v
        return copy.deepcopy(d)

    def update_one(self, filtro, cambios, upsert=False):
        self.find_one_and_update(filtro, cambios, upsert)

    def insert_one(self, d):
        self.docs[d["_id"]] = copy.deepcopy(d)

    def delete_many(self, filtro):
        for k in [k for k, d in self.docs.items() if self._casa(d, filtro)]:
            del self.docs[k]


class _Base:
    def __init__(self):
        self._cols: dict = {}

    def __getattr__(self, nombre):
        if nombre.startswith("_"):
            raise AttributeError(nombre)
        return self._cols.setdefault(nombre, _Coleccion())

    def __getitem__(self, nombre):
        return getattr(self, nombre)


def _correr(coro):
    return asyncio.run(coro)


def _hacer(db, uid, entrada, por="mcp"):
    return _correr(hi.presentacion_en_pantalla(db, uid, hi.PresentacionEntrada.model_validate(entrada), por))


# ───────────────────────────── La herramienta compartida ─────────────────────────────

def test_un_agente_por_mcp_maneja_la_pantalla_paso_a_paso():
    db = _Base()
    r = _hacer(db, 7, {"op": "estado"})
    assert r.contenido["pantalla"]["abierta"] is False and r.contenido["pantalla"]["capitulo"] == "portada"
    assert r.contenido["pantalla"]["paso"] == 1 and "No hay ninguna pantalla en off abierta" in r.contenido["nota"]
    assert db.pantallas.find_one({"_id": 7}) is None   # mirar no guarda nada
    r = _hacer(db, 7, {"op": "ir", "capitulo": "vivienda", "paso": 3, "explicacion": "Trescientas  viviendas nuevas."})
    assert r.acciones == [] and r.contenido["guion"] == VIVIENDA["pasos"][2] and "pantalla" in r.contenido
    d = db.pantallas.find_one({"_id": 7})
    assert (d["capitulo"], d["paso"], d["explicacion"], d["v"], d["por"]) == ("vivienda", 3, "Trescientas viviendas nuevas.", 1, "mcp")
    # «Siguiente» sin punto de partida va desde donde está la pantalla, y quita la explicación del paso anterior
    r = _hacer(db, 7, {"op": "siguiente"})
    assert r.contenido["paso"] == 4 and r.contenido["capitulo"]["id"] == "vivienda"
    d = db.pantallas.find_one({"_id": 7})
    assert (d["paso"], d["explicacion"], d["v"]) == (4, None, 2)
    _hacer(db, 7, {"op": "explicar", "explicacion": "Así se ven."})
    assert db.pantallas.find_one({"_id": 7})["explicacion"] == "Así se ven."
    _hacer(db, 7, {"op": "quitar_explicacion"})
    assert db.pantallas.find_one({"_id": 7})["explicacion"] is None
    # Lo que se ve: el índice cierra las fichas y al revés; el panel no cambia de paso
    r = _hacer(db, 7, {"op": "vista", "panel": False})
    assert r.resumen == "La presentación muestra solo la maqueta 3D"
    _hacer(db, 7, {"op": "vista", "fichas": True})
    _hacer(db, 7, {"op": "vista", "indice": True})
    d = db.pantallas.find_one({"_id": 7})
    assert (d["panel"], d["indice"], d["fichas"], d["paso"]) == (False, True, False, 4)
    r = _hacer(db, 7, {"op": "pantalla_completa", "activar": True})
    assert r.contenido["llena_la_ventana"] is True and db.pantallas.find_one({"_id": 7})["completa"] is True
    # Cada orden de pantalla completa se distingue (la pantalla que la devolvió con Escape la vuelve a llenar)
    primera = db.pantallas.find_one({"_id": 7})["orden_completa"]
    time.sleep(0.002)
    _hacer(db, 7, {"op": "pantalla_completa", "activar": True})
    assert db.pantallas.find_one({"_id": 7})["orden_completa"] > primera
    # Ir a otro paso cierra el índice y las fichas; el panel y la ventana quedan
    _hacer(db, 7, {"op": "ir", "capitulo": "salud"})
    e = pantalla.estado(db.pantallas.find_one({"_id": 7}), G)
    assert (e["capitulo"], e["paso"], e["indice"], e["fichas"], e["panel"], e["completa"]) == ("salud", 1, False, False,
                                                                                              False, True)
    assert e["v"] == 10
    r = _hacer(db, 7, {"op": "estado"})
    p = r.contenido["pantalla"]
    assert p["capitulo"] == "salud" and p["llena_la_ventana"] is True and p["cambiada_por"] == "un agente por MCP"
    assert "Solo 3D" in p["muestra"] and "llena la ventana" in p["muestra"]
    # Otra persona tiene su propia pantalla
    assert _hacer(db, 8, {"op": "estado"}).contenido["pantalla"]["capitulo"] == "portada"


def test_el_asistente_sin_pantalla_abierta_mueve_la_pestana_del_chat_como_siempre():
    db = _Base()
    r = _hacer(db, 0, {"op": "ir", "capitulo": "vivienda", "paso": 3}, por="asistente")
    assert r.acciones == [{"tipo": "presentacion", "op": "ir", "capitulo": "vivienda", "paso": 3}]
    assert "pantalla" not in r.contenido
    assert db.pantallas.find_one({"_id": 0})["paso"] == 3   # y la pantalla en off arrancará ahí
    # Sin punto de partida lo calcula la vista de la pestaña: la pantalla en off no cambia
    r = _hacer(db, 0, {"op": "siguiente"}, por="asistente")
    assert r.acciones == [{"tipo": "presentacion", "op": "siguiente"}] and db.pantallas.find_one({"_id": 0})["v"] == 1
    assert _hacer(db, 0, {"op": "vista", "panel": False, "indice": True}, por="asistente").acciones == [
        {"tipo": "presentacion", "op": "vista", "panel": False, "indice": True}]
    assert _hacer(db, 0, {"op": "pantalla_completa", "activar": False}, por="asistente").acciones == [
        {"tipo": "presentacion", "op": "pantalla_completa", "activar": False}]


def test_con_la_pantalla_abierta_el_asistente_no_mueve_la_pestana_del_chat():
    db = _Base()
    pantalla.marcar_vista(db, 0)   # la pantalla en off preguntó recién
    r = _hacer(db, 0, {"op": "ir", "capitulo": "vivienda", "paso": 2}, por="asistente")
    assert r.acciones == [] and "pantalla en off" in r.contenido["pantalla"]
    r = _hacer(db, 0, {"op": "anterior"}, por="asistente")
    assert r.acciones == [] and r.contenido["paso"] == 1 and db.pantallas.find_one({"_id": 0})["paso"] == 1
    assert _hacer(db, 0, {"op": "estado"}, por="asistente").contenido["pantalla"]["abierta"] is True
    # Una pantalla que dejó de preguntar se da por cerrada
    db.pantallas.docs[0]["visto"] = datetime.now(timezone.utc) - timedelta(seconds=pantalla.VIVA_S + 1)
    assert _hacer(db, 0, {"op": "ir", "capitulo": "salud"}, por="asistente").acciones[0]["capitulo"] == "salud"


def test_visual_cambia_lo_que_se_ve_y_vuelve_a_lo_del_paso():
    """La op `visual`: resuelve los componentes del capítulo de la pantalla (por id o por nombre) y la inmersión del
    catálogo, guarda solo lo pedido, le devuelve al modelo la ficha técnica de lo que muestra y, al cambiar de paso,
    todo vuelve a lo del paso salvo el tema."""
    db = _Base()
    _hacer(db, 7, {"op": "ir", "capitulo": "salud", "paso": 3})
    r = _hacer(db, 7, {"op": "visual", "enfoque": "Torre de servicios de primer nivel del Hospital Héctor Abad Gómez",
                       "camara": "aerea", "rumbo": 180, "girar": True})
    assert r.acciones == [] and r.contenido["componente"]["id"] == "torre"
    assert r.contenido["componente"]["lugar_en_la_maqueta"] is True and r.contenido["componente"]["especificaciones"]
    assert "$" not in json.dumps(r.contenido, ensure_ascii=False)
    assert r.resumen == ("La presentación muestra la cámara en «Torre de servicios de primer nivel del Hospital Héctor "
                         "Abad Gómez», vista aérea, mirando desde el rumbo 180°, la cámara gira")
    d = db.pantallas.find_one({"_id": 7})
    assert (d["enfoque"], d["camara"], d["rumbo"], d["girar"], d["capitulo"], d["paso"]) == ("torre", "aerea", 180, True, "salud", 3)
    _hacer(db, 7, {"op": "visual", "detalle": "telesalud", "comparar": "hoy", "inmersion": "Simulador sísmico",
                   "tema": "oscuro"})
    d = db.pantallas.find_one({"_id": 7})
    assert (d["detalle"], d["comparar"], d["inmersion"], d["tema"]) == ("telesalud", "hoy", "torre_sismo", "oscuro")
    e = _hacer(db, 7, {"op": "estado"}).contenido["pantalla"]
    assert e["visual"]["inmersion"] == "torre_sismo" and "Simulador sísmico" in e["muestra"]
    assert "la ficha técnica de «Telesalud rural en red»" in e["muestra"] and "tema oscuro" in e["muestra"]
    # Lo que vuelve a lo del paso: «paso», «cerrar» y la cámara «paso» (que devuelve también el rumbo)
    _hacer(db, 7, {"op": "visual", "enfoque": "paso", "detalle": "cerrar", "inmersion": "paso", "camara": "paso"})
    d = db.pantallas.find_one({"_id": 7})
    assert (d["enfoque"], d["detalle"], d["inmersion"], d["camara"], d["rumbo"]) == (None, None, None, "paso", None)
    _hacer(db, 7, {"op": "visual", "inmersion": "maqueta", "enfoque": "torre"})
    # Cambiar de paso: todo vuelve a lo del paso, salvo el tema
    _hacer(db, 7, {"op": "siguiente"})
    d = db.pantallas.find_one({"_id": 7})
    assert (d["paso"], d["enfoque"], d["inmersion"], d["comparar"], d["girar"], d["tema"]) == \
        (4, None, None, "proyecto", False, "oscuro")
    # El asistente sin pantalla abierta: la acción exacta para la vista de la pestaña del chat
    r = _hacer(db, 9, {"op": "visual", "capitulo": "agroindustria", "enfoque": "trilladora", "detalle": "trilladora"},
               por="asistente")
    assert r.acciones == [{"tipo": "presentacion", "op": "visual", "enfoque": "trilladora", "detalle": "trilladora"}]
    r = _hacer(db, 9, {"op": "visual", "capitulo": "agroindustria", "enfoque": "paso"}, por="asistente")
    assert r.acciones == [{"tipo": "presentacion", "op": "visual", "enfoque": None}]


def test_visual_no_mueve_nada_si_no_existe():
    db = _Base()
    _hacer(db, 7, {"op": "ir", "capitulo": "vivienda", "paso": 1})
    v = db.pantallas.find_one({"_id": 7})["v"]
    for entrada, codigo, dice in [
            ({"op": "visual", "enfoque": "titulacion"}, "invalido", "no tiene un lugar propio en la maqueta"),
            ({"op": "visual", "enfoque": "marte"}, "no_existe", "no tiene el componente «marte»"),
            ({"op": "visual", "detalle": "torre"}, "no_existe", "no tiene el componente «torre»"),
            ({"op": "visual", "inmersion": "marte"}, "no_existe", "no tiene la inmersión «marte»"),
            ({"op": "visual", "capitulo": "salud", "enfoque": "torre"}, "invalido", "vaya primero a ese capítulo")]:
        with pytest.raises(hi.ErrorHerramienta) as e:
            _hacer(db, 7, entrada)
        assert e.value.codigo == codigo and dice in str(e.value), (entrada, str(e.value))
    assert db.pantallas.find_one({"_id": 7})["v"] == v   # todo o nada
    # Con candidatos: los componentes con lugar en la maqueta (para enfoque) o todos (para detalle)
    with pytest.raises(hi.ErrorHerramienta) as e:
        _hacer(db, 7, {"op": "visual", "enfoque": "titulacion"})
    assert {"id": "nuevas", "nombre": "Urbanización VIP/VIS urbana (Lote 1 y Lote 2)"} in e.value.detalle["con_lugar"]
    assert all(x["id"] != "titulacion" for x in e.value.detalle["con_lugar"])


def test_entradas_que_no_valen():
    for malo, dice in [({"op": "vista"}, "diga qué mostrar"), ({"op": "vista", "indice": True, "fichas": True}, "no se abren a la vez"),
                       ({"op": "vista", "panel": "no"}, "boolean"), ({"op": "vista", "panel": 1}, "boolean"),
                       ({"op": "pantalla_completa"}, "activar"), ({"op": "ir", "capitulo": "salud", "activar": True}, "no usa"),
                       ({"op": "explicar", "explicacion": "x", "panel": True}, "no usa"), ({"op": "estado", "paso": 1}, "no usa"),
                       ({"op": "vista", "panel": True, "explicacion": "x"}, "no usa"),
                       ({"op": "visual"}, "diga qué cambiar"), ({"op": "visual", "camara": "cenital"}, "camara"),
                       ({"op": "visual", "rumbo": 360}, "rumbo"), ({"op": "visual", "rumbo": True}, "rumbo"),
                       ({"op": "visual", "comparar": "ayer"}, "comparar"), ({"op": "visual", "camara": None}, "no va vacío"),
                       ({"op": "visual", "enfoque": "torre", "paso": 2}, "no usa"),
                       ({"op": "ir", "capitulo": "salud", "enfoque": "torre"}, "no usa"),
                       ({"op": "vista", "panel": True, "tema": "oscuro"}, "no usa")]:
        with pytest.raises(ValueError) as e:
            hi.PresentacionEntrada.model_validate(malo)
        assert dice in str(e.value), (malo, str(e.value))


def test_el_estado_guardado_se_corrige_si_el_guion_cambio():
    e = pantalla.estado({"capitulo": "marte", "paso": 9, "explicacion": "Vieja.", "v": 4, "indice": "si"}, G)
    assert (e["capitulo"], e["paso"], e["explicacion"], e["v"], e["indice"]) == ("portada", 1, None, 4, False)
    assert pantalla.estado({"capitulo": "vivienda", "paso": len(VIVIENDA["pasos"]) + 1}, G)["capitulo"] == "portada"
    assert pantalla.conectada(None) is False and pantalla.conectada({"visto": datetime.now(timezone.utc)}) is True
    with pytest.raises(ValueError):
        pantalla.guardar(_Base(), 1, {"personas": [1]}, "mcp")
    # Lo visual que no vale (o que ya no está en el capítulo) vuelve a lo del paso; el tema raro, al del navegador
    e = pantalla.estado({"capitulo": "salud", "paso": 3, "enfoque": "marte", "detalle": "torre", "camara": "cenital",
                         "rumbo": 400, "girar": "si", "comparar": "hoy", "inmersion": "torre_bim", "tema": "gris"}, G)
    assert (e["enfoque"], e["detalle"], e["camara"], e["rumbo"], e["girar"], e["comparar"], e["inmersion"], e["tema"]) == \
        (None, "torre", "paso", None, False, "hoy", "torre_bim", None)
    assert pantalla.estado({"capitulo": "vivienda", "paso": 1, "enfoque": "titulacion"}, G)["enfoque"] is None
    assert pantalla.estado({"capitulo": "marte", "paso": 1, "enfoque": "torre", "tema": "oscuro"}, G)["tema"] == "oscuro"


# ───────────────────────────── El protocolo MCP ─────────────────────────────

def _rpc(db, metodo, params=None, id_=1):
    r = _correr(mcp.atender(db, 3, {"jsonrpc": "2.0", "id": id_, "method": metodo, **({"params": params} if params is not None else {})}))
    return None if r is None else json.loads(r.body)


def test_protocolo_mcp():
    db = _Base()
    r = _rpc(db, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "x", "version": "1"}})
    assert r["result"]["protocolVersion"] == "2025-06-18" and r["result"]["capabilities"] == {"tools": {"listChanged": False}}
    assert r["result"]["serverInfo"]["name"] == "yondo-presentacion" and "pantalla en off" in r["result"]["instructions"]
    assert _rpc(db, "initialize", {"protocolVersion": "1999-01-01"})["result"]["protocolVersion"] == mcp.PROTOCOLOS[0]
    assert _rpc(db, "ping")["result"] == {}
    herramientas = _rpc(db, "tools/list")["result"]["tools"]
    assert [h["name"] for h in herramientas] == ["presentacion"]
    assert herramientas[0]["inputSchema"]["properties"]["op"]["enum"] == list(hi.OPS_PRESENTACION)
    assert "pantalla en off de la persona" in herramientas[0]["description"]
    r = _rpc(db, "tools/call", {"name": "presentacion", "arguments": {"op": "ir", "capitulo": "vivienda", "paso": 2}})
    res = r["result"]
    assert res["isError"] is False and res["structuredContent"]["paso"] == 2
    assert json.loads(res["content"][0]["text"])["guion"] == VIVIENDA["pasos"][1]
    assert db.pantallas.find_one({"_id": 3})["capitulo"] == "vivienda"
    # Los errores de la herramienta vuelven como isError (el agente los lee y corrige)
    r = _rpc(db, "tools/call", {"name": "presentacion", "arguments": {"op": "ir", "capitulo": "marte"}})["result"]
    assert r["isError"] is True and "no tiene un capítulo" in r["content"][0]["text"]
    r = _rpc(db, "tools/call", {"name": "presentacion", "arguments": {"op": "explicar", "explicacion": "Llame al 300 123 4567"}})["result"]
    assert r["isError"] is True and "7 o más dígitos" in r["content"][0]["text"]
    assert db.pantallas.find_one({"_id": 3})["explicacion"] is None
    r = _rpc(db, "tools/call", {"name": "presentacion", "arguments": "ir"})["result"]
    assert r["isError"] is True
    assert _rpc(db, "tools/call", {"name": "buscar_personas", "arguments": {}})["error"]["code"] == -32602
    assert _rpc(db, "resources/list")["error"]["code"] == -32601
    assert _rpc(db, "tools/list", id_=True)["error"]["code"] == -32600
    # Una notificación (sin id) no tiene respuesta
    assert _correr(mcp.atender(db, 3, {"jsonrpc": "2.0", "method": "notifications/initialized"})) is None


@pytest.fixture
def app_sin_base(cfg):
    """El panel sin MongoDB, con una base en memoria para /api/mcp: la clave del administrador ya creada."""
    from fastapi.testclient import TestClient
    from dataclasses import replace
    from app.main import crear_app
    from app.seguridad import huella, obtener_db
    app = crear_app(replace(cfg, mongodb_uri="mongodb://127.0.0.1:1/?serverSelectionTimeoutMS=300"))
    db = _Base()
    clave = "ypm_" + "x" * 43
    db.claves_mcp.insert_one({"_id": huella_clave(clave), "uid": 0, "huella": huella(app.state.cfg),
                              "creada": datetime.now(timezone.utc), "usada": None})
    app.dependency_overrides[obtener_db] = lambda: db
    mcp._usos.clear()
    try:
        yield TestClient(app), db, clave
    finally:
        app.state.cliente.close()


INICIO = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
          "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "prueba", "version": "1"}}}


def test_la_ruta_mcp_pide_la_clave_y_respeta_el_protocolo(app_sin_base, monkeypatch):
    from app.seguridad import huella
    c, db, clave = app_sin_base
    con = {"Authorization": f"Bearer {clave}"}
    r = c.post("/api/mcp", json=INICIO)
    assert r.status_code == 401 and r.headers["www-authenticate"].startswith("Bearer") and "Cuenta" in r.json()["error"]
    assert c.post("/api/mcp", json=INICIO, headers={"Authorization": "Bearer ypm_otra"}).status_code == 401
    r = c.post("/api/mcp", json=INICIO, headers=con)
    assert r.status_code == 200 and r.json()["result"]["protocolVersion"] == "2025-11-25"
    assert r.headers["content-type"].startswith("application/json") and r.headers["cache-control"] == "no-store"
    assert db.claves_mcp.find_one({"uid": 0})["usada"] is not None
    # La clave en la dirección, para los clientes que solo aceptan una URL
    assert c.post(f"/api/mcp?clave={clave}", json=INICIO).status_code == 200
    # Otro origen (una página en un navegador): no
    assert c.post("/api/mcp", json=INICIO, headers={**con, "Origin": "https://malo.example"}).status_code == 403
    assert c.post("/api/mcp", json=INICIO, headers={**con, "Origin": "http://testserver"}).status_code == 200
    assert c.post("/api/mcp", json=INICIO, headers={**con, "MCP-Protocol-Version": "1999-01-01"}).status_code == 400
    # Sin flujo SSE ni sesiones: GET y DELETE, 405
    for metodo in ("GET", "DELETE"):
        r = c.request(metodo, "/api/mcp", headers=con)
        assert r.status_code == 405 and r.headers["allow"] == "POST", metodo
    r = c.post("/api/mcp", content=b"{no es json", headers={**con, "Content-Type": "application/json"})
    assert r.status_code == 400 and r.json()["error"]["code"] == -32700
    assert c.post("/api/mcp", json=[INICIO], headers=con).status_code == 400
    assert c.post("/api/mcp", json={"id": 1, "method": "ping"}, headers=con).json()["error"]["code"] == -32600
    r = c.post("/api/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=con)
    assert r.status_code == 202 and r.content == b""
    r = c.post("/api/mcp", headers=con, json={"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {
        "name": "presentacion", "arguments": {"op": "pantalla_completa", "activar": True}}})
    assert r.json()["result"]["isError"] is False and db.pantallas.find_one({"_id": 0})["completa"] is True
    # Al cambiar la credencial del administrador, la clave deja de valer (como sus sesiones)
    db.claves_mcp.docs[huella_clave(clave)]["huella"] = "otra"
    assert c.post("/api/mcp", json=INICIO, headers=con).status_code == 401
    db.claves_mcp.docs[huella_clave(clave)]["huella"] = huella(c.app.state.cfg)
    # Hasta LIMITE_MINUTO por minuto
    monkeypatch.setattr(mcp, "LIMITE_MINUTO", 2)
    mcp._usos.clear()
    assert [c.post("/api/mcp", json=INICIO, headers=con).status_code for _ in range(3)] == [200, 200, 429]


# ───────────────────────────── El puente del navegador (Node) ─────────────────────────────

GUION_PUENTE = r"""const [modulo] = process.argv.slice(2);
globalThis.document = { querySelector: () => null };
globalThis.location = { pathname: '/panel/presentacion' };
const P = await import(modulo);
const r = {};
const A = (x) => P.accionPresentacion({ tipo: 'presentacion', ...x });
r.validas = [A({ op: 'vista', panel: false }), A({ op: 'vista', indice: true, panel: true }), A({ op: 'pantalla_completa', activar: true })];
r.malas = [A({ op: 'vista' }), A({ op: 'vista', panel: 'no' }), A({ op: 'vista', indice: true, fichas: true }),
  A({ op: 'vista', panel: true, activar: true }), A({ op: 'vista', panel: true, capitulo: 'vivienda' }),
  A({ op: 'pantalla_completa' }), A({ op: 'pantalla_completa', activar: 1 }), A({ op: 'pantalla_completa', activar: true, panel: true }),
  A({ op: 'ir', capitulo: 'vivienda', panel: true }), A({ op: 'explicar', explicacion: 'x', activar: false })];
r.ir_sigue = A({ op: 'ir', capitulo: 'vivienda', paso: 2 });
const base = { v: 3, capitulo: 'vivienda', paso: 2, explicacion: null, panel: true, indice: false, fichas: false, completa: false, orden_completa: 0 };
r.estado = P.estadoDePantalla(base);
r.estados_malos = [{ ...base, v: -1 }, { ...base, capitulo: 'Vivienda' }, { ...base, paso: 0 }, { ...base, explicacion: '' },
  { ...base, panel: 'si' }, { ...base, completa: undefined }, { ...base, orden_completa: -1 }, null, []].map((e) => P.estadoDePantalla(e));
r.desde_nada = P.ordenesHacia(null, base);
r.explicar = P.ordenesHacia(base, { ...base, explicacion: 'Hola.' });
r.quitar = P.ordenesHacia({ ...base, explicacion: 'Hola.' }, base);
r.otro_paso = P.ordenesHacia({ ...base, indice: true, panel: false }, { ...base, paso: 3, explicacion: 'Tres.', panel: false });
r.otro_paso_con_indice = P.ordenesHacia(base, { ...base, paso: 3, indice: true });
r.solo_vista = P.ordenesHacia(base, { ...base, fichas: true, panel: false });
r.solo_completa = P.ordenesHacia(base, { ...base, completa: true });
// visual: la acción, el estado con sus partes y lo que cambia (al cambiar de paso, desde lo del paso; el tema queda)
r.visual_validas = [A({ op: 'visual', enfoque: 'torre', camara: 'aerea' }), A({ op: 'visual', enfoque: null, rumbo: null }),
  A({ op: 'visual', rumbo: 0, girar: false, comparar: 'hoy', detalle: 'torre', inmersion: 'torre_sismo', tema: 'claro' })];
r.visual_malas = [A({ op: 'visual' }), A({ op: 'visual', camara: 'cenital' }), A({ op: 'visual', rumbo: 360 }),
  A({ op: 'visual', enfoque: 'Torre' }), A({ op: 'visual', tema: null }), A({ op: 'visual', camara: 'aerea', panel: true }),
  A({ op: 'ir', capitulo: 'salud', enfoque: 'torre' }), A({ op: 'vista', panel: true, girar: true })];
const vis = { ...base, enfoque: 'torre', camara: 'aerea', rumbo: 180, girar: false, comparar: 'proyecto', detalle: null, inmersion: null, tema: null };
r.estado_visual = P.estadoDePantalla(vis);
r.estados_visuales_malos = [{ ...vis, camara: 'x' }, { ...vis, rumbo: 400 }, { ...vis, enfoque: 'A' }, { ...vis, tema: 'gris' }].map((e) => P.estadoDePantalla(e));
r.estado_sin_visual = P.estadoDePantalla(base);
const sv = P.estadoDePantalla(base);
r.solo_visual = P.ordenesHacia(sv, P.estadoDePantalla(vis));
r.visual_vuelve = P.ordenesHacia(P.estadoDePantalla(vis), sv);
r.paso_con_visual = P.ordenesHacia(P.estadoDePantalla({ ...vis, tema: 'oscuro' }), P.estadoDePantalla({ ...vis, paso: 3, enfoque: null, camara: 'paso', rumbo: null, tema: 'oscuro', detalle: 'torre' }));
r.desde_nada_visual = P.ordenesHacia(null, P.estadoDePantalla({ ...vis, tema: 'oscuro' }));
console.log(JSON.stringify(r));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="sin Node")
def test_el_puente_acepta_las_ordenes_nuevas_y_la_pantalla_en_off_calcula_lo_que_cambia(tmp_path):
    (tmp_path / "puente.mjs").write_text(GUION_PUENTE, encoding="utf-8")
    p = subprocess.run(["node", str(tmp_path / "puente.mjs"), (WEB / "js" / "agente-presentacion.js").as_uri()],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    r = json.loads(p.stdout.strip().splitlines()[-1])
    assert r["validas"] == [{"tipo": "presentacion", "op": "vista", "panel": False},
                            {"tipo": "presentacion", "op": "vista", "panel": True, "indice": True},
                            {"tipo": "presentacion", "op": "pantalla_completa", "activar": True}]
    assert r["malas"] == [None] * 10
    assert r["ir_sigue"] == {"tipo": "presentacion", "op": "ir", "capitulo": "vivienda", "paso": 2}
    assert r["estado"]["capitulo"] == "vivienda" and r["estados_malos"] == [None] * 9
    assert r["desde_nada"] == [{"orden": "ir", "capitulo": "vivienda", "paso": 2}]
    assert r["explicar"] == [{"orden": "explicar", "explicacion": "Hola."}]
    assert r["quitar"] == [{"orden": "quitar_explicacion"}]
    # Cambiar de paso cierra allá el índice (no hace falta pedirlo) y lleva la explicación nueva
    assert r["otro_paso"] == [{"orden": "ir", "capitulo": "vivienda", "paso": 3, "explicacion": "Tres."}]
    assert r["otro_paso_con_indice"] == [{"orden": "ir", "capitulo": "vivienda", "paso": 3},
                                         {"orden": "vista", "indice": True}]
    assert r["solo_vista"] == [{"orden": "vista", "panel": False, "fichas": True}]
    assert r["solo_completa"] == []   # la ventana la llena la vista, no mando.js
    assert r["visual_validas"] == [
        {"tipo": "presentacion", "op": "visual", "enfoque": "torre", "camara": "aerea"},
        {"tipo": "presentacion", "op": "visual", "enfoque": None, "rumbo": None},
        {"tipo": "presentacion", "op": "visual", "rumbo": 0, "girar": False, "comparar": "hoy", "detalle": "torre",
         "inmersion": "torre_sismo", "tema": "claro"}]
    assert r["visual_malas"] == [None] * 8
    assert r["estado_visual"]["enfoque"] == "torre" and r["estado_visual"]["tema"] is None
    assert r["estados_visuales_malos"] == [None] * 4
    # un servidor de antes (sin lo visual): lo del paso
    assert (r["estado_sin_visual"]["camara"], r["estado_sin_visual"]["comparar"]) == ("paso", "proyecto")
    assert r["solo_visual"] == [{"orden": "visual", "enfoque": "torre", "camara": "aerea", "rumbo": 180}]
    assert r["visual_vuelve"] == [{"orden": "visual", "enfoque": None, "camara": "paso", "rumbo": None}]
    # cambiar de paso deja lo visual en lo del paso: solo va lo que difiere de eso (el tema ya estaba)
    assert r["paso_con_visual"] == [{"orden": "ir", "capitulo": "vivienda", "paso": 3},
                                    {"orden": "visual", "detalle": "torre"}]
    assert r["desde_nada_visual"] == [{"orden": "ir", "capitulo": "vivienda", "paso": 2},
                                      {"orden": "visual", "enfoque": "torre", "camara": "aerea", "rumbo": 180,
                                       "tema": "oscuro"}]


# ───────────────────────────── Con MongoDB ─────────────────────────────

def test_la_pantalla_pregunta_por_su_estado(sesion):
    r = sesion.get("/api/pantalla")
    assert r.status_code == 200
    e = r.json()
    assert e == {"v": 0, "capitulo": "portada", "paso": 1, "explicacion": None, "panel": True, "indice": False,
                 "fichas": False, "completa": False, "orden_completa": 0, **pantalla.VISUAL_INICIAL, "tema": None,
                 "recorrido": None, "control_recorrido": None, "progreso": None}
    assert sesion.get("/api/pantalla?v=0").status_code == 204
    db = sesion.app.state.db
    assert pantalla.conectada(db.pantallas.find_one({"_id": 0}))
    pantalla.guardar(db, 0, {"capitulo": "vivienda", "paso": 2, "completa": True}, "asistente")
    e = sesion.get("/api/pantalla?v=0").json()
    assert (e["v"], e["capitulo"], e["paso"], e["completa"]) == (1, "vivienda", 2, True)
    assert sesion.get("/api/pantalla?v=1").status_code == 204


def test_sin_sesion_no_hay_pantalla(cliente):
    assert cliente.get("/api/pantalla").status_code == 401
    assert cliente.post("/api/pantalla/clave").status_code == 401


def test_clave_mcp_y_un_agente_que_maneja_la_pantalla(sesion, como):
    c = como("planillero")
    info = c.get("/api/pantalla/clave").json()
    assert info["tiene"] is False and info["direccion"].endswith("/api/mcp")
    r = c.post("/api/pantalla/clave")
    assert r.status_code == 200
    nueva = r.json()
    clave = nueva["clave"]
    assert clave.startswith("ypm_") and nueva["direccion_con_clave"].endswith(f"/api/mcp?clave={clave}")
    db = sesion.app.state.db
    guardada = db.claves_mcp.find_one({"uid": c.uid})
    assert guardada["_id"] == huella_clave(clave) and clave not in json.dumps(guardada, default=str)
    assert db.auditoria.find_one({"accion": "crear_clave_mcp", "uid": c.uid}) is not None
    # El agente: sin cookie, con la clave
    from fastapi.testclient import TestClient
    agente = TestClient(sesion.app)
    con = {"Authorization": f"Bearer {clave}"}
    assert agente.post("/api/mcp", json=INICIO, headers=con).json()["result"]["serverInfo"]["name"] == "yondo-presentacion"
    r = agente.post("/api/mcp", headers=con, json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
        "name": "presentacion", "arguments": {"op": "ir", "capitulo": "vivienda", "paso": 3, "explicacion": "Las nuevas."}}})
    assert r.status_code == 200 and r.json()["result"]["isError"] is False
    # La pantalla en off del planillero lo ve; la del administrador no cambió
    e = c.get("/api/pantalla").json()
    assert (e["capitulo"], e["paso"], e["explicacion"]) == ("vivienda", 3, "Las nuevas.")
    assert sesion.get("/api/pantalla").json()["capitulo"] == "portada"
    assert c.get("/api/pantalla/clave").json()["usada"] is not None
    # Crear otra reemplaza la anterior; revocar la anula
    otra = c.post("/api/pantalla/clave").json()["clave"]
    assert agente.post("/api/mcp", json=INICIO, headers=con).status_code == 401
    assert agente.post("/api/mcp", json=INICIO, headers={"Authorization": f"Bearer {otra}"}).status_code == 200
    assert c.delete("/api/pantalla/clave").json()["revocada"] is True
    assert agente.post("/api/mcp", json=INICIO, headers={"Authorization": f"Bearer {otra}"}).status_code == 401
    assert db.claves_mcp.count_documents({"uid": c.uid}) == 0
    agente.close()


def test_la_clave_mcp_deja_de_valer_con_la_cuenta(sesion, como):
    c = como("consultor")
    clave = c.post("/api/pantalla/clave").json()["clave"]
    db = sesion.app.state.db
    from fastapi.testclient import TestClient
    agente = TestClient(sesion.app)
    con = {"Authorization": f"Bearer {clave}"}
    assert agente.post("/api/mcp", json=INICIO, headers=con).status_code == 200
    # Le cambian la clave del panel (otra versión de sus sesiones): la clave MCP ya no vale
    db.usuarios.update_one({"_id": c.uid}, {"$inc": {"version": 1}})
    assert agente.post("/api/mcp", json=INICIO, headers=con).status_code == 401
    db.usuarios.update_one({"_id": c.uid}, {"$inc": {"version": -1}})
    assert agente.post("/api/mcp", json=INICIO, headers=con).status_code == 200
    # Desactivado, tampoco
    db.usuarios.update_one({"_id": c.uid}, {"$set": {"activo": False}})
    assert agente.post("/api/mcp", json=INICIO, headers=con).status_code == 401
    agente.close()


def test_el_contexto_del_asistente_dice_lo_que_muestra_la_pantalla_abierta(sesion):
    from app.agente import sistema
    db = sesion.app.state.db
    assert sistema.pantalla_del_contexto(db, 0) == ""
    pantalla.guardar(db, 0, {"capitulo": "vivienda", "paso": 2, "explicacion": "Dos lotes.", "panel": False}, "mcp")
    assert sistema.pantalla_del_contexto(db, 0) == ""   # guardada pero sin pantalla abierta
    pantalla.marcar_vista(db, 0)
    t = sistema.pantalla_del_contexto(db, 0)
    assert t.startswith("Vivienda (vivienda), paso 2 de ") and "«Dos lotes.»" in t and "Solo 3D" in t
    bloque = sistema.contexto_del_panel({}, datetime.now(timezone.utc), pantalla=t)
    assert f"Pantalla en off abierta: {t}" in bloque


# ───────────────────────────── En Chromium, con MongoDB ─────────────────────────────

from test_agente_mapa import requiere_navegador  # noqa: E402
from test_agente_presentacion import panel_con_sitio  # noqa: E402,F401  (el fixture: el servidor único con el sitio)

GUION_OFF = r"""// La pantalla en off en Chromium: un agente por MCP (fetch desde Node) y el asistente del panel desde otra pestaña.
// Uso: node <guion> <base del panel> <usuario> <clave> <clave MCP>
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const [base, usuario, clave, claveMcp] = process.argv.slice(2);
const origen = new URL(base).origin;
const espera = { timeout: 90000 };
const salida = { errores: [] };
(async () => {
  const nav = await chromium.launch();
  const ctx = await nav.newContext({ viewport: { width: 1280, height: 720 } });
  await ctx.route((u) => u.origin !== origen, (r) => r.abort());
  const A = await ctx.newPage();
  A.on('pageerror', (e) => salida.errores.push(String(e)));
  await A.goto(base + '/', { waitUntil: 'domcontentloaded' });
  await A.fill('#f-login [name=usuario]', usuario);
  await A.fill('#f-login [name=clave]', clave);
  await A.click('#f-login button[type=submit]');
  await A.waitForSelector('#app #vista > .vista', espera);
  await A.goto(base + '/presentacion?off=1', { waitUntil: 'domcontentloaded' });
  await A.waitForFunction(() => /Conectada/.test(document.querySelector('#pres-off-estado')?.textContent || ''), null, espera);
  const marco = () => A.frames().find((f) => /\/propuesta/.test(f.url()));
  const mirar = async () => ({
    hash: await marco().evaluate(() => location.hash),
    sub: await marco().evaluate(() => (document.querySelector('.subtitulo').classList.contains('visible') ? document.querySelector('.subtitulo p').textContent : null)),
    sin_panel: await marco().evaluate(() => document.querySelector('#pres').classList.contains('sin-panel')),
    sin_controles: await marco().evaluate(() => document.querySelector('#pres').classList.contains('sin-controles')),
    llena: await A.evaluate(() => 'presLlena' in document.documentElement.dataset),
    inerte: await A.evaluate(() => document.querySelector('#pres-iframe').inert),
  });
  const hasta = async (cond, nombre) => {
    const fin = Date.now() + 60000;
    while (Date.now() < fin) { const m = await mirar(); if (cond(m)) return m; await new Promise((ok) => setTimeout(ok, 300)); }
    return { ...(await mirar()), fallo: nombre };
  };
  let n = 0;
  const mcp = async (metodo, params) => (await fetch(base + '/api/mcp', { method: 'POST', headers: {
    Authorization: `Bearer ${claveMcp}`, 'Content-Type': 'application/json', Accept: 'application/json, text/event-stream' },
    body: JSON.stringify({ jsonrpc: '2.0', id: ++n, method: metodo, ...(params ? { params } : {}) }) })).json();
  const llamar = (args) => mcp('tools/call', { name: 'presentacion', arguments: args });
  salida.inicio = await mcp('initialize', { protocolVersion: '2025-11-25', capabilities: {}, clientInfo: { name: 'prueba', version: '1' } });
  salida.ir = await llamar({ op: 'ir', capitulo: 'vivienda', paso: 3, explicacion: 'Las viviendas nuevas.' });
  salida.tras_ir = await hasta((m) => m.hash === '#vivienda/3' && m.sub === 'Las viviendas nuevas.', 'ir');
  await llamar({ op: 'vista', panel: false });
  salida.tras_vista = await hasta((m) => m.sin_panel, 'vista');
  await llamar({ op: 'pantalla_completa', activar: true });
  salida.tras_completa = await hasta((m) => m.llena, 'completa');
  // Nadie la mueve a mano
  await A.mouse.click(900, 500);
  await A.keyboard.press('ArrowRight');
  await A.waitForTimeout(2000);
  salida.tras_tecla = await mirar();
  salida.estado = await llamar({ op: 'estado' });
  // El asistente del panel desde otra pestaña: mueve la pantalla en off y su pestaña no cambia de vista
  const B = await ctx.newPage();
  B.on('pageerror', (e) => salida.errores.push(String(e)));
  await B.goto(base + '/reuniones', { waitUntil: 'domcontentloaded' });
  await B.waitForSelector('#app #vista > .vista', espera);
  await B.waitForSelector('#agente-boton:not([hidden])', espera);
  await B.click('#agente-boton');
  await B.fill('#agente-texto', 'Muéstrame el hospital');
  await B.press('#agente-texto', 'Enter');
  await B.waitForFunction(() => document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);
  salida.tras_asistente = await hasta((m) => m.hash === '#salud/2', 'asistente');
  salida.ruta_chat = await B.evaluate(() => location.pathname);
  console.log(JSON.stringify(salida));
  await nav.close();
})().catch((e) => { console.error(e); process.exit(1); });
"""


@requiere_navegador
def test_un_agente_por_mcp_y_el_asistente_manejan_la_pantalla_en_off_en_chromium(panel_con_sitio, cfg, tmp_path):
    import ayudas_agente as aa
    from app.seguridad import huella
    base, panel = panel_con_sitio
    clave = "ypm_" + "p" * 43
    panel.state.db.claves_mcp.insert_one({"_id": huella_clave(clave), "uid": 0, "huella": huella(panel.state.cfg),
                                          "creada": datetime.now(timezone.utc), "usada": None})
    aa.encender(panel, aa.sse(aa.TU("toolu_off1", "presentacion", {"op": "ir", "capitulo": "salud", "paso": 2}),
                              stop="tool_use"),
                aa.sse(aa.T("Listo: el hospital, en la pantalla en off.")))
    (tmp_path / "off.cjs").write_text(GUION_OFF, encoding="utf-8")
    r = subprocess.run(["node", str(tmp_path / "off.cjs"), base, cfg.usuario, cfg.clave, clave],
                       capture_output=True, text=True, timeout=400)
    assert r.returncode == 0, (r.stdout[-3000:], r.stderr[-3000:])
    s = json.loads(r.stdout.strip().splitlines()[-1])
    assert s["errores"] == []
    assert s["inicio"]["result"]["serverInfo"]["name"] == "yondo-presentacion"
    assert s["ir"]["result"]["isError"] is False
    for paso in ("tras_ir", "tras_vista", "tras_completa", "tras_asistente"):
        assert "fallo" not in s[paso], (paso, s[paso])
    assert s["tras_ir"]["sin_controles"] is True and s["tras_ir"]["inerte"] is True
    assert s["tras_tecla"]["hash"] == "#vivienda/3" and s["tras_tecla"]["llena"] is True
    assert s["estado"]["result"]["structuredContent"]["pantalla"]["abierta"] is True
    # El asistente no se llevó la pestaña del chat a la presentación: la sala ve la pantalla en off
    assert s["ruta_chat"].endswith("/reuniones")
    assert panel.state.db.pantallas.find_one({"_id": 0})["por"] == "asistente"
