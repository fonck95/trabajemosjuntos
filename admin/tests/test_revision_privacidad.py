"""Regresiones de la revisión adversarial del asistente, grupo «privacidad»: lo que sale del panel hacia el modelo (el
contexto de la vista que acompaña cada mensaje y las máscaras de los textos libres) y los cupos del asistente en el
servidor único. Solo datos inventados: nunca se llama a Anthropic ni a Mnemo."""
import asyncio
import json
import socket
import threading
import time
from datetime import datetime, timezone

import httpx
import pymongo
import pytest
import uvicorn

import ayudas_agente as aa
from ayudas_agente import T, encender, enviar, sse
from ayudas_g3 import autorizada, persona
from conftest import CLAVE_USUARIO, MONGO, URI, crear_usuario

import servidor
from app import seguridad as seg
from app.agente import conversaciones as conv_db
from app.agente import minimizar, sistema
from app.agente.herramientas import personas as hp

AHORA = datetime(2026, 11, 9, 15, 0, tzinfo=timezone.utc)
PUNTO = [-73.912345, 6.987654]  # [lon, lat], como lo da MapLibre: el punto de una persona inventada
LISTA = "Lista concejo Juana Inventada"


def _filtros(t: str) -> dict:
    """Los «Filtros de la URL» de un contexto del panel ({} si no hay)."""
    linea = next((x for x in t.split("\n") if x.startswith("Filtros de la URL: ")), None)
    return json.loads(linea.split(": ", 1)[1]) if linea else {}


# ───────────────────────────── n.º 3: el centro del mapa ─────────────────────────────

def test_el_centro_del_mapa_de_cerca_no_llega_al_modelo():
    """Al resaltar a una sola persona, el mapa se encuadra en su punto (zoom 16,5): el centro de la pantalla es su
    ubicación. De cerca solo va el zoom; de lejos (zoom 14 o menos), el centro con 2 decimales (unos 1,1 km)."""
    t = sistema.contexto_del_panel({"ruta": "/mapa", "mapa": {"centro": PUNTO, "zoom": 16.5}}, AHORA)
    assert "\nMapa: zoom 16.5\n" in t and "centro" not in t and "6.98" not in t and "73.91" not in t
    t = sistema.contexto_del_panel({"mapa": {"camara": {"centro": {"lat": 6.987654, "lon": -73.912345},
                                                        "zoom": 12}}}, AHORA)
    assert "\nMapa: centro lat 6.99, lon -73.91, zoom 12.0\n" in t and "6.987" not in t and "73.912" not in t
    assert "centro lat 6.99, lon -73.91, zoom 14.0" in sistema.contexto_del_panel(
        {"mapa": {"centro": PUNTO, "zoom": 14}}, AHORA)
    assert "centro" not in sistema.contexto_del_panel({"mapa": {"centro": PUNTO, "zoom": 14.2}}, AHORA)


# ───────────────────────────── n.º 4: los filtros de la dirección ─────────────────────────────

def test_los_filtros_que_no_son_del_asistente_no_llegan_al_modelo_aunque_el_navegador_los_mande():
    """El buscador de Habitantes acepta cédula, teléfono o correo, y la dirección puede traer la lista de origen, el
    liderazgo, el régimen de salud, la selección o el dibujo del mapa y la vuelta de Mnemo: nada de eso va al modelo."""
    filtros = {"q": "3001234567", "lista": LISTA, "lider": "1", "regimen_salud": "subsidiado", "ids": "11,12,13",
               "poligono": "[[-73.91,6.98],[-73.92,6.99],[-73.9,6.97]]", "fuente": "cedulas", "code": "codigo-falso",
               "state": "estado-falso", "iss": "https://mnemo.invalid", "error": "access_denied",
               "zona": "rural", "consentimiento": "si", "orden": "nombre", "edad_min": "18", "ids_total": "3"}
    t = sistema.contexto_del_panel({"ruta": "/personas", "filtros": filtros}, AHORA)
    assert _filtros(t) == {"q": sistema.Q_CON_NUMEROS, "zona": "rural", "consentimiento": "si", "orden": "nombre",
                           "edad_min": "18", "ids_total": "3"}
    for dato in ("3001234567", LISTA, "lider", "subsidiado", "11,12", "-73.91", "cedulas", "codigo-falso",
                 "estado-falso", "mnemo.invalid", "access_denied"):
        assert dato not in t, dato
    # La búsqueda por nombre sí va (recortada como en la API); con números o un correo, no
    for q, va in (("Rosa Inventada", True), ("rosa@correo.co", False), ("71234", False), ("calle 10 # 4-21", False),
                  ("Rosa \uff13\uff10\uff10", False)):
        assert _filtros(sistema.contexto_del_panel({"filtros": {"q": q}}, AHORA)) == {
            "q": q if va else sistema.Q_CON_NUMEROS}, q
    assert _filtros(sistema.contexto_del_panel({"filtros": {"q": "x" * 300}}, AHORA)) == {"q": "x" * 120}
    # La fuente, sin la base de cédulas (sola o en «ambas»)
    for fuente, va in (("tramites", True), ("planilla", True), ("ambas", False), ("cedulas", False)):
        assert ("fuente" in _filtros(sistema.contexto_del_panel({"filtros": {"fuente": fuente}}, AHORA))) is va
    # Un número largo en el valor de una clave conocida sale tapado
    assert _filtros(sistema.contexto_del_panel({"filtros": {"orden": "300 111 22 33", "desde": "2026-11-01"}},
                                               AHORA)) == {"orden": "···233", "desde": "2026-11-01"}


def test_lo_que_recibe_y_guarda_el_modelo_no_lleva_la_busqueda_ni_el_punto(sesion):
    """De punta a punta: la petición al modelo y el mensaje guardado (que se le reenvía en cada ronda)."""
    api = encender(sesion.app, sse(T("En la vista hay una búsqueda por número.")))
    contexto = {"ruta": "/personas", "vista": "personas",
                "filtros": {"q": "3001234567", "lista": LISTA, "lider": "1", "regimen_salud": "subsidiado",
                            "ids": "11,12", "zona": "rural"},
                "mapa": {"centro": PUNTO, "zoom": 16.5}}
    r, ev = enviar(sesion, "¿Cuántas personas hay?", contexto=contexto)
    assert r.status_code == 200 and ev[-1]["motivo"] == "listo", ev
    # La conversación que va al modelo (las instrucciones y las herramientas no cambian con el contexto)
    enviado = json.dumps(api.peticiones[0]["json"]["messages"], ensure_ascii=False)
    guardado = json.dumps(list(sesion.app.state.db[conv_db.MENSAJES].find({}, {"_id": 0})), ensure_ascii=False,
                          default=str)
    for texto in (enviado, guardado):
        assert "rural" in texto and "zoom 16.5" in texto and "¿Cuántas personas hay?" in texto
        for dato in ("3001234567", LISTA, "subsidiado", "lider", "11,12", "6.98", "73.91"):
            assert dato not in texto, dato


# ───────────────────────────── n.º 10 y 27: las máscaras del texto libre ─────────────────────────────

@pytest.mark.parametrize("texto, esperado", [
    ("Llamar al 300 111 22 33", "Llamar al ···233"),
    ("cel 300-111-22-33", "cel ···233"),
    ("300.111.22.33 o 300 111 2233", "···233 o ···233"),
    ("(300) 111 2233", "···233"),
    ("tel (604) 832 12 34", "tel ···234"),
    ("(604)8321234", "···234"),
    ("+57 300 1112233", "···233"),
    ("+57 (300) 111-2233.", "···233."),
    ("CC 71 234 567", "CC ···567"),
    ("Cédula 71 234 000", "Cédula ···000"),
    ("cédula 1 036 123 456", "cédula ···456"),
    ("71.234.000 y 1,234,567", "···000 y ···567"),
    ("Tel: 300 111 22 33 / 310 444 55 66", "Tel: ···233 / ···566"),
    ("300\u00a0111\u00a022\u00a033", "···233"),
    ("\uff13\uff10\uff10 111 22 33", "···233"),
    ("rosa3001112233@correo.co o 3001112233", "[correo] o ···233"),
    ("07/11/2026 3001112233", "07/11/2026 ···233"),
])
def test_las_mascaras_tapan_telefonos_y_cedulas_escritos_por_grupos(texto, esperado):
    assert minimizar.texto_libre(texto) == esperado


@pytest.mark.parametrize("texto", [
    "Visita el 2026-11-07 10:30 o el 07/11/2026", "7/11/2026 y 2026/11/07 y 07.11.2026", "Vivió en Bogotá 2018-2022",
    "calle 50 # 48-21", "Cra 7 # 12 - 45 apto 301", "3 hijos, 45 años, mesa 12", "Barrio 20 de Julio, lote 3-4",
])
def test_las_mascaras_dejan_fechas_direcciones_y_numeros_cortos(texto):
    assert minimizar.texto_libre(texto) == texto


def test_un_campo_propio_numerico_con_un_telefono_sale_tapado():
    sin = minimizar.Sensibles()
    f = minimizar.ficha({"id": 4, "nombre": "ANA INVENTADA", "extra": {
        "celular": 3001112233, "cedula_madre": 71234567.0, "hijos": 3, "talla": 1.7, "vive_sola": True, "nada": None,
        "lista": ["300 111 22 33"]}}, sin)
    assert f["extra"] == {"celular": "···233", "cedula_madre": "···567", "hijos": 3, "talla": 1.7, "vive_sola": True,
                          "nada": None, "lista": "['···233']"}
    assert minimizar.texto_libre(3001112233) == "···233" and minimizar.texto_libre(5) == 5


def test_ver_persona_no_le_pasa_al_modelo_numeros_escritos_por_grupos(sesion):
    """De punta a punta con `ver_persona`: observaciones, notas, dirección y un campo propio numérico."""
    app, db = sesion.app, sesion.app.state.db
    db.campos.update_one({"clave": "celular_alterno"}, {"$setOnInsert": {
        "_id": 950, "clave": "celular_alterno", "etiqueta": "Celular alterno", "tipo": "numero", "opciones": [],
        "orden": 950, "activo": True, "sensible": False}}, upsert=True)
    pid = persona(db, nombre="TEODORA INVENTADA GRUPOS", observaciones="Llamar al 300 111 22 33 o al (604) 832 12 34",
                  direccion="Cra 7 # 12 - 45", extra={"celular_alterno": 3104445566},
                  notas=[{"id": "n1", "texto": "Dictó su CC 71 234 567 el 07/11/2026", "autor": "admin",
                          "autor_uid": 0, "creado_en": "2026-11-07T10:00:00+00:00", "reunion_id": None}])
    autorizada(db, pid)
    ctx = aa.contexto(app, sesion)
    r = aa.correr(sesion, aa.ejecutar, next(h for h in hp.HERRAMIENTAS if h.nombre == "ver_persona"), ctx,
                  {"persona_id": pid})
    al_modelo = r.texto_para_modelo()
    for dato in ("300 111 22 33", "832 12 34", "71 234 567", "3104445566", "111 22", "234 567"):
        assert dato not in al_modelo, dato
    assert r.contenido["observaciones"] == "Llamar al ···233 o al ···234"
    assert r.contenido["notas"][0]["texto"] == "Dictó su CC ···567 el 07/11/2026"
    assert r.contenido["direccion"] == "Cra 7 # 12 - 45" and r.contenido["extra"] == {"celular_alterno": "···566"}
    aa.correr(sesion, ctx.api.cerrar)


# ───────────────────────────── n.º 9: cuerpos lentos y cupos del asistente ─────────────────────────────

async def _lee_y_responde(scope, receive, send):
    """Como el panel: lee el cuerpo entero y responde con lo que leyó."""
    cuerpo = b""
    while True:
        msg = await receive()
        cuerpo += msg.get("body", b"")
        if not msg.get("more_body"):
            break
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": cuerpo})


def test_un_cuerpo_lento_no_retiene_los_cupos_del_asistente():
    """El turno del asistente pide su cupo con el cuerpo ya leído (con plazo total y tope), como el ingreso: un cuerpo
    que no termina de llegar recibe 408 y no deja al asistente en 503 para todos."""
    async def lento():
        yield b'{"texto": "Hola'
        await asyncio.sleep(3600)  # el resto nunca llega

    async def probar():
        limite = servidor.LimitePanel(_lee_y_responde, cupos=1, espera_s=0.3, limite=1000, plazo_s=0.8,
                                      cupos_agente=1)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=limite), base_url="http://t") as c:
            tareas = [asyncio.create_task(c.post(ruta, content=lento())) for ruta in sorted(servidor.RUTAS_AGENTE)]
            await asyncio.sleep(0.1)
            for ruta in sorted(servidor.RUTAS_AGENTE):
                r = await c.post(ruta, json={"texto": "Hola"})
                assert r.status_code == 200 and r.json() == {"texto": "Hola"}, (ruta, r.text)
            lentas = await asyncio.wait_for(asyncio.gather(*tareas), 3)
            assert [r.status_code for r in lentas] == [408, 408]
            assert all(r.headers["connection"] == "close" for r in lentas)
            # El tope, por Content-Length, sin leer nada ni pedir cupo
            r = await c.post("/api/agente/mensajes", content=b"x" * 1001)
            assert r.status_code == 413
    asyncio.run(probar())


@pytest.fixture
def servido(cfg, tmp_path, monkeypatch):
    """El servidor único de verdad (uvicorn h11, como en Railway) con el plazo del cuerpo en 2 s. Devuelve (base,
    puerto, app del panel)."""
    if not MONGO:
        pytest.skip("No hay MongoDB para las pruebas del servidor")
    monkeypatch.setattr(servidor, "PLAZO_CUERPO_S", 2)
    sitio = tmp_path / "site"
    sitio.mkdir()
    (sitio / "index.html").write_text("<!doctype html><title>Inicio</title>INICIO", encoding="utf-8")
    app = servidor.crear_servidor(cfg, sitio)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    srv = uvicorn.Server(uvicorn.Config(app, http="h11", lifespan="on", log_level="warning", access_log=False,
                                        server_header=False, timeout_graceful_shutdown=2))
    hilo = threading.Thread(target=srv.run, kwargs={"sockets": [sock]}, daemon=True)
    hilo.start()
    try:
        fin = time.time() + 15
        while time.time() < fin and not (srv.started and app.state.panel is not None and app.state.panel.state.listo):
            time.sleep(0.05)
        assert app.state.panel is not None and app.state.panel.state.listo
        puerto = sock.getsockname()[1]
        yield f"http://127.0.0.1:{puerto}", puerto, app.state.panel
    finally:
        srv.should_exit = True
        hilo.join(15)
        sock.close()
        with pymongo.MongoClient(URI) as m:
            m.drop_database(cfg.mongodb_db)


def _estado(s, segundos):
    """El código de estado de lo que llega por `s` en `segundos` (None si nada) y si el servidor cerró."""
    fin, datos, cerrada = time.monotonic() + segundos, b"", False
    while not cerrada and time.monotonic() < fin:
        s.settimeout(max(0.01, fin - time.monotonic()))
        try:
            parte = s.recv(65536)
        except TimeoutError:
            break
        except ConnectionResetError:
            parte = b""
        cerrada, datos = not parte, datos + parte
    return (int(datos.split()[1]) if datos.startswith(b"HTTP/1.1 ") else None), cerrada


def test_un_consultor_sin_asistente_no_deja_al_asistente_en_503(servido, cfg):
    """La reproducción de la revisión, en el servidor de verdad: un consultor (con el asistente apagado para su rol)
    abre más conexiones que cupos con un `Content-Length` que nunca completa. El administrador conversa igual, y cada
    conexión lenta recibe 408 al vencer el plazo."""
    base, puerto, panel = servido
    u = crear_usuario(panel.state.db, "consultor")
    with httpx.Client(base_url=base, timeout=10) as c:
        r = c.post("/panel/api/login", json={"usuario": u["usuario"], "clave": CLAVE_USUARIO})
        assert r.status_code == 200, r.text
        cookie = c.cookies.get(seg.COOKIE)
        assert c.post("/panel/api/agente/mensajes", json={"texto": "Hola"}).status_code == 403  # su rol no lo usa
    lentas = []
    try:
        for _ in range(servidor.CUPOS_AGENTE + 2):
            s = socket.create_connection(("127.0.0.1", puerto))
            s.sendall(f"POST /panel/api/agente/mensajes HTTP/1.1\r\nHost: t\r\nCookie: {seg.COOKIE}={cookie}\r\n"
                      "Content-Type: application/json\r\nContent-Length: 100\r\n\r\n{\"texto\": \"".encode())
            lentas.append(s)
        time.sleep(0.3)
        encender(panel, sse(T("Hola.")))
        with httpx.Client(base_url=base, timeout=10) as c:
            r = c.post("/panel/api/login", json={"usuario": cfg.usuario, "clave": cfg.clave})
            c.headers["X-CSRF-Token"] = r.json()["csrf"]
            r = c.post("/panel/api/agente/mensajes", json={"texto": "Hola"})
            assert r.status_code == 200 and r.text != servidor.OCUPADO, r.text
            assert aa.ndjson(r.text)[-1]["motivo"] == "listo"
        assert [_estado(s, servidor.PLAZO_CUERPO_S + 3) for s in lentas] == [(408, True)] * len(lentas)
    finally:
        for s in lentas:
            s.close()
