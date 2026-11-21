"""La voz clonada del asistente, lo del servidor (app/agente/voz.py, `GET /api/agente/voces` y `POST /api/agente/voz` de
app/api/agente.py, el campo `voz` de `GET /api/agente/estado`, el ajuste `agente_voz` y el alcance `mnemo:voice` de la
conexión con Mnemo): la voz solo dice lo que generó el sistema (la narración por referencia al plan guardado, las
frases firmadas de una respuesta, la frase fija de la prueba), quién la hace sonar, los topes que acotan el costo y la
concurrencia, la caché de la narración y el «un solo vuelo» (la precarga y la reproducción se cuelgan de la misma
llamada a Mnemo, y quien llega tarde recibe lo ya producido), la llamada que se cancela cuando nadie escucha, los
errores de Mnemo traducidos a los códigos del panel y que nada de lo dicho va al registro.

Sin MongoDB la mayoría: la ruta de verdad en una aplicación mínima, con la persona fija (cabecera `x-uid`), los ajustes
fijos, una base en memoria (la de test_pantalla_mcp.py, con el plan guardado de verdad por la herramienta de la
presentación) y un cliente de Mnemo falso que manda el audio por avisos de progreso, como `mnemo_speak`. Las de la
conexión, Ajustes y el estado, con MongoDB (se saltan sin él) y el MCP falso de ayudas_mcp.py. Solo datos inventados:
el «audio» son bytes cualquiera que nadie decodifica."""
import asyncio
import base64
import json
import logging
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import acceso, pantalla
from app import recorrido as rec
from app.agente import conversaciones as conv_db
from app.agente import mnemo_cliente as mc
from app.agente import mnemo_conexion, politica, voz
from app.agente.herramientas import interfaz as hi
from app.agente.herramientas import mnemo as hmnemo
from app.agente.herramientas.base import ErrorHerramienta
from app.api import agente as agente_api
from test_automatica import TORRE, G
from test_pantalla_mcp import _Base

URL = "https://mnemo.example.org/mcp"
VOZ_ID = "6740aa0b1c2d3e4f5a6b7c8d"          # inventado (un ObjectId de Mnemo)
OTRA_VOZ = "6740aa0b1c2d3e4f5a6b7c8e"
HUELLA = "0123456789abcdef0123456789abcdef"  # la de la cuenta de Mnemo conectada (inventada)
CONECTADA = {"estado": "conectada", "motivo": None, "url": URL, "cuenta": None,
             "alcances": ["mnemo:read", "mnemo:model", "mnemo:voice"], "modelo": True, "ofrece_modelo": True,
             "voz": True, "ofrece_voz": True, "desde": "2026-11-01T10:00:00+00:00"}
VOZ = {"motor": "mnemo", "voz": VOZ_ID, "nombre": "Ana (voz de prueba)", "cuenta": HUELLA,
       "roles": ["admin", "coordinador"], "respuestas": True, "automatica": True}
AUTO = {**VOZ, "voz": "", "nombre": "", "cuenta": ""}   # sin una voz elegida: la que Mnemo ofrece a las apps
QUIENES = {uid: acceso.Quien(uid=uid, usuario=f"p{uid}", rol=rol, permisos=acceso.PERMISOS[rol])
           for uid, rol in ((0, "admin"), (5, "coordinador"), (6, "coordinador"), (8, "planillero"),
                            (9, "consultor"))}
AUDIO = bytes(range(256)) * 90                   # 23 040 bytes: tres trozos de Mnemo (9 600, 9 600 y 3 840)
TROZO = 9600
SECRETO = "Rosa Inventada vive en la vereda El Ejemplo"   # lo que nunca debe ir al registro
CFG = SimpleNamespace(usuario="admin", clave="clave-de-prueba-larga")


def b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def trozos_de(audio: bytes = AUDIO) -> list[str]:
    return [b64(audio[i:i + TROZO]) for i in range(0, len(audio), TROZO)]


class ClienteFalso:
    """El cliente de Mnemo: `mnemo_speak` manda primero el aviso `start` y después cada trozo de `audio` por
    `al_progreso` (como Mnemo con un `progressToken`) y responde la salida final; `mnemo_list_voices` responde `voces`.

    * `llamadas`: (nombre, argumentos, plazo, tope) de cada llamada; `canceladas`: las que se cortaron a mitad.
    * `puerta`: si está, el segundo trozo y los demás esperan a que se abra (`mandados` cuenta los que salieron).
    * `fallo`: el `ErrorHerramienta` con que responde (antes del primer aviso, o después de `fallo_tras` trozos).
    * `inicio`: el aviso `start` (None: no manda ninguno); `progreso=False`: un Mnemo sin avance (el audio entero en
      la salida, como sin `progressToken`)."""

    def __init__(self, audio: bytes = AUDIO):
        self.audio = audio
        self.llamadas: list[tuple] = []
        self.canceladas = 0
        self.mandados = 0
        self.puerta: asyncio.Event | None = None
        self.fallo: ErrorHerramienta | None = None
        self.fallo_tras: int | None = None
        self.progreso = True
        self.inicio: dict | None = {"type": "start", "format": "pcm_s16le_24000", "mime": "audio/pcm",
                                    "sample_rate": 24000, "channels": 1, "mode": "stream"}
        self.voces = [{"voice_id": VOZ_ID, "name": "Ana (voz de prueba)", "language": "es", "engine": "minimax",
                       "status": "ready"},
                      {"voice_id": OTRA_VOZ, "name": "Beto  Inventado", "language": "es-CO", "engine": "qwen3",
                       "status": "ready"}]
        self.salida_voces: dict | None = None

    def hablas(self) -> list[dict]:
        return [a for n, a, *_ in self.llamadas if n == voz.HERRAMIENTA]

    async def llamar(self, nombre, argumentos, plazo=60, al_progreso=None, *, tope=None):
        self.llamadas.append((nombre, argumentos, plazo, tope))
        if nombre == voz.HERRAMIENTA_VOCES:
            if self.fallo is not None:
                raise self.fallo
            por_defecto = self.voces[0]["voice_id"] if self.voces else None
            return {"structuredContent": self.salida_voces or {"voices": self.voces,
                                                              "default_voice_id": por_defecto}}
        assert nombre == voz.HERRAMIENTA
        try:
            if self.fallo is not None and self.fallo_tras is None:
                raise self.fallo
            partes = trozos_de(self.audio)
            if self.progreso and al_progreso is not None:
                n = 0
                if self.inicio is not None:
                    n += 1
                    al_progreso({"progress": n, "total": None, "message": json.dumps(self.inicio)})
                for i, t in enumerate(partes):
                    if i >= 1 and self.puerta is not None:
                        await self.puerta.wait()
                    if self.fallo_tras == i:
                        raise self.fallo
                    n += 1
                    al_progreso({"progress": n, "total": None,
                                 "message": json.dumps({"type": "audio", "seq": i + 1, "data": t})})
                    self.mandados += 1
                    await asyncio.sleep(0)
            datos = {"voice_id": argumentos["voice_id"], "format": "pcm_s16le_24000", "mime": "audio/pcm",
                     "sample_rate": 24000, "channels": 1, "characters": len(argumentos["text"]),
                     "bytes": len(self.audio), "chunks": len(partes), "first_audio_ms": 640, "total_ms": 2100,
                     "duration_ms": len(self.audio) // 48, "mode": "stream", "streamed": self.progreso}
            if not self.progreso:
                datos["audio"] = b64(self.audio)
            return {"structuredContent": datos}
        except asyncio.CancelledError:
            self.canceladas += 1
            raise


def _plan(db, uid: int, entrada: dict = TORRE) -> dict:
    """Guarda un plan para la pantalla de `uid` con la herramienta de la presentación (como lo arma el asistente) y lo
    devuelve como lo lee el servidor."""
    asyncio.run(hi.presentacion_en_pantalla(db, uid, hi.PresentacionEntrada.model_validate(entrada), "asistente"))
    return pantalla.recorrido_de(pantalla.leer(db, uid), G)


class Banco:
    """Las rutas de verdad en una aplicación mínima: `requiere(...)` sustituido por la persona de la cabecera `x-uid`,
    los ajustes fijos (`voz_ajustes`, validados como los lee el panel), la conexión con Mnemo simulada
    (`voz._preparar`) y una base en memoria con las pantallas y las conversaciones."""

    def __init__(self, monkeypatch, *, ajustes_voz: dict | None = None, conexion: dict | None = None,
                 huella: str = HUELLA, cliente: ClienteFalso | None = None):
        self.app = FastAPI()
        self.app.include_router(agente_api.r)
        self.db = _Base()
        self.db.name = "prueba_voz_servidor"
        self.app.state.db = self.db
        self.app.state.cfg = CFG
        self.cliente = cliente or ClienteFalso()
        self.voz = dict(VOZ if ajustes_voz is None else ajustes_voz)
        self.conexion = dict(CONECTADA if conexion is None else conexion)
        self.huella = huella
        for ruta in self.app.routes:
            if isinstance(ruta, APIRoute) and ruta.path in ("/api/agente/voz", "/api/agente/voces"):
                for d in ruta.dependant.dependencies:
                    if hasattr(d.call, "permisos"):
                        self.app.dependency_overrides[d.call] = self._quien(d.call.permisos)
        monkeypatch.setattr(politica, "leer", lambda db: ({"agente_voz": politica.ajustes_voz(
            {"agente_voz": self.voz})}, {"roles": ["admin", "coordinador"], "escritura": True}))
        monkeypatch.setattr(voz, "_preparar", lambda app: (dict(self.conexion), self.cliente, self.huella))
        # (la base en memoria no sabe de `$exists`: si la conversación trae personas, como lo mira conversaciones.py)
        monkeypatch.setattr(voz.conv_db, "tiene_personas", lambda db, cid: bool(
            (db[conv_db.CONVERSACIONES].find_one({"_id": cid}) or {}).get("personas")))
        self.http = TestClient(self.app)

    @staticmethod
    def _quien(permisos):
        def quien(request: Request):
            q = QUIENES[int(request.headers.get("x-uid", "0"))]
            if not all(q.puede(p) for p in permisos):
                from fastapi import HTTPException
                raise HTTPException(403, {"codigo": "permiso", "mensaje": "Sin permiso."})
            return q
        return quien

    def conversacion(self, cid: int, uid: int, personas: list[int] | None = None) -> None:
        self.db[conv_db.CONVERSACIONES].insert_one({"_id": cid, "uid": uid, "titulo": "Inventada",
                                                    "personas": personas or []})

    def firma(self, uid: int, cid: int, texto: str) -> str:
        return voz.firmar(voz.llave_respuestas(CFG), uid, cid, texto)

    def hablar(self, cuerpo: dict, uid: int = 0):
        return self.http.post("/api/agente/voz", json=cuerpo, headers={"x-uid": str(uid)})

    async def crudo(self, cuerpo: dict, recibir, uid: int = 0) -> list[dict]:
        """La ruta en ASGI crudo, con `recibir` como el `receive` del servidor web después del cuerpo: lo que mandó la
        aplicación (así se ven los trozos uno por uno y la persona que se va a mitad)."""
        enviados: list[dict] = []
        crudo = json.dumps(cuerpo).encode()
        entregado = False

        async def recibir_con_cuerpo():
            nonlocal entregado
            if not entregado:
                entregado = True
                return {"type": "http.request", "body": crudo, "more_body": False}
            return await recibir()

        async def enviar(m):
            enviados.append(m)
        alcance = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
                   "scheme": "http", "path": "/api/agente/voz", "raw_path": b"/api/agente/voz", "query_string": b"",
                   "root_path": "", "server": ("panel", 80), "client": ("127.0.0.1", 5000),
                   "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(crudo)).encode()),
                               (b"x-uid", str(uid).encode())]}
        await self.app(alcance, recibir_con_cuerpo, enviar)
        return enviados


def eventos(texto: str) -> list[dict]:
    lineas = texto.split("\n")
    assert lineas[-1] == "" and all(lineas[:-1]), "una línea JSON por evento, y termina con un salto de línea"
    return [json.loads(x) for x in lineas[:-1]]


def eventos_crudos(enviados: list[dict]) -> list[dict]:
    cuerpo = b"".join(m.get("body", b"") for m in enviados if m["type"] == "http.response.body")
    return eventos(cuerpo.decode()) if cuerpo else []


def audio_de(evs: list[dict]) -> bytes:
    return b"".join(base64.b64decode(e["datos"]) for e in evs if e["tipo"] == "audio")


async def _hasta(condicion, segundos: float = 3.0):
    for _ in range(int(segundos / 0.01)):
        if condicion():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("no se cumplió a tiempo")


def _detalle(r) -> dict:
    d = r.json()["detail"]
    assert set(d) == {"codigo", "mensaje"}, d
    return d


@pytest.fixture(autouse=True)
def limpio():
    def vaciar():
        voz._ventanas.clear()
        voz._en_curso.clear()
        voz._diarias.clear()
        voz._hablando.clear()
    vaciar()
    yield
    vaciar()


@pytest.fixture
def banco(monkeypatch):
    def crear(**kw):
        return Banco(monkeypatch, **kw)
    return crear


# ───────────────────────────── El contrato ─────────────────────────────

def test_el_contrato_y_los_topes():
    # Las herramientas de Mnemo (alcance `mnemo:voice`): ninguna es del modelo, ni con `*`
    assert (voz.HERRAMIENTA, voz.HERRAMIENTA_VOCES) == ("mnemo_speak", "mnemo_list_voices")
    assert {"mnemo_speak", "mnemo_list_voices"} <= hmnemo.NUNCA
    assert mnemo_conexion.ALCANCE_VOZ == "mnemo:voice"
    assert (voz.FORMATO, voz.IDIOMA) == ("pcm_s16le_24000", "es")
    # Por persona: la frase que suena y la siguiente, 90 por minuto y 30 000 caracteres por día; en el proceso, tres
    # llamadas a Mnemo a la vez (esperando hasta 10 s); el «no» de Mnemo se recuerda una hora
    assert voz.A_LA_VEZ_PERSONA == 2 and (voz.FRECUENCIA_MAX, voz.FRECUENCIA_S) == (90, 60)
    assert voz.CARACTERES_DIA == 30_000 and voz.A_LA_VEZ == 3 and voz.ESPERA_CUPO_S == 10
    assert voz.OLVIDO_S == 3600
    # La caché: 48 MB, 12 horas
    assert voz.CACHE_BYTES == 48 * 1024 * 1024 and voz.CACHE_S == 12 * 3600
    # Lo que se pide: una frase de una respuesta, hasta 400 caracteres; Mnemo dice hasta 1000 por llamada
    assert voz.MAX_TEXTO == 400 and voz.MAX_DICHO == 1000
    assert agente_api.VozIn.model_fields["texto"].metadata[-1].max_length == voz.MAX_TEXTO
    assert voz.ETIQUETA_FIRMA == b"voz-respuestas-v1"
    assert voz.FRASE_PRUEBA == ("Hola. Esta es la voz que usará el asistente para narrar la presentación y responder "
                                "sus preguntas.")
    # Los rangos de la narración son los del recorrido (como el avance de la presentación)
    for n, ok in ((0, False), (1, True), (rec.MAX_ESCENAS, True), (rec.MAX_ESCENAS + 1, False)):
        assert _valido({"rid": "a" * 12, "n": n, "frase": 0}) is ok, n
    for f, ok in ((-1, False), (0, True), (rec.MAX_FRASES - 1, True), (rec.MAX_FRASES, False)):
        assert _valido({"rid": "a" * 12, "n": 1, "frase": f}) is ok, f
    # Las rutas y sus permisos: las voces, solo el administrador; una frase, quien ve la presentación (su rol lo decide
    # `agente_voz.roles`)
    rutas = {(m, r.path): r for r in agente_api.r.routes if isinstance(r, APIRoute) for m in r.methods}
    for clave, permiso in ((("GET", "/api/agente/voces"), "agente.conectar"),
                           (("POST", "/api/agente/voz"), "presentacion.ver")):
        assert [d.call.permisos for d in rutas[clave].dependant.dependencies if hasattr(d.call, "permisos")] == [
            frozenset({permiso})], clave
    assert "agente.conectar" in acceso.SOLO_ADMIN
    assert all("presentacion.ver" in acceso.PERMISOS[r] or "*" in acceso.PERMISOS[r] for r in acceso.ROLES)


def _valido(cuerpo: dict) -> bool:
    from pydantic import ValidationError
    try:
        agente_api.VozIn.model_validate(cuerpo)
        return True
    except ValidationError:
        return False


@pytest.mark.parametrize("cuerpo", [
    {"texto": "Diga esto con la voz del administrador."},                 # texto libre: nunca
    {"conversacion": 3, "texto": "Hola, cómo le va hoy."},                 # sin firma
    {"rid": "a" * 12}, {"rid": "a" * 12, "n": 1}, {"n": 1, "frase": 0},     # a medias
    {"rid": "a" * 12, "n": 1, "frase": 0, "cierre": True},                 # dos a la vez
    {"rid": "a" * 12, "cierre": False}, {"prueba": False}, {"prueba": True, "rid": "a" * 12},
    {"prueba": "true"}, {"rid": "a" * 12, "n": "1", "frase": 0}, {"rid": "a" * 12, "n": 1.0, "frase": 0},
    {"rid": "A" * 12, "n": 1, "frase": 0}, {"rid": "a" * 13, "n": 1, "frase": 0},
    {"conversacion": 3, "texto": "Hola, cómo le va hoy.", "firma": "x" * 42},
    {"conversacion": 3, "texto": "Hola, cómo le va hoy.", "firma": "x" * 43 + "="},
    {"conversacion": 3, "texto": "", "firma": "x" * 43}, {"conversacion": 3, "texto": "a" * 401, "firma": "x" * 43},
    {"conversacion": True, "texto": "Hola, cómo le va hoy.", "firma": "x" * 43},
    {"prueba": True, "voz_id": VOZ_ID}, {"prueba": True, "formato": "mp3"}, {}])
def test_solo_se_pide_por_referencia(banco, cuerpo):
    b = banco()
    r = b.hablar(cuerpo)
    assert r.status_code == 422, (cuerpo, r.text)
    assert b.cliente.llamadas == []


# ───────────────────────────── La narración, por referencia al plan guardado ─────────────────────────────

def test_la_narracion_sale_del_plan_guardado(banco, caplog):
    b = banco()
    r0 = _plan(b.db, 0)
    assert r0["escenas"][1]["frases"] == ["Son cuatro pisos."]
    with caplog.at_level(logging.DEBUG):
        r = b.hablar({"rid": r0["id"], "n": 2, "frase": 0})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/x-ndjson" and r.headers["cache-control"] == "no-store"
    assert r.headers["x-accel-buffering"] == "no"
    ev = eventos(r.text)
    assert ev[0] == {"tipo": "inicio", "formato": "pcm_s16le", "muestreo": 24000, "canales": 1, "cache": False,
                     "voz": "Ana (voz de prueba)"}
    # El base64 de Mnemo pasa tal cual, trozo por trozo
    assert [e["datos"] for e in ev[1:-1]] == trozos_de() and audio_de(ev) == AUDIO
    fin = ev[-1]
    assert fin["tipo"] == "fin" and fin["ms_mnemo"] == 640 and fin["bytes"] == len(AUDIO)
    assert isinstance(fin["ms_primer_audio"], int) and 0 <= fin["ms_primer_audio"] < 5000
    assert set(fin) == {"tipo", "ms_primer_audio", "ms_mnemo", "bytes"}
    # Lo que recibe Mnemo: la voz elegida, el texto como se dice, PCM de 24 kHz y el idioma. Nada más
    ((nombre, args, plazo, tope),) = b.cliente.llamadas
    assert nombre == "mnemo_speak" and args == {"voice_id": VOZ_ID, "text": "Son cuatro pisos.",
                                                "format": "pcm_s16le_24000", "language": "es"}
    assert plazo == voz.PLAZO_S and tope == voz.TOPE_S and voz.TOPE_S > 120   # Mnemo corta a los 120 s
    # Nada del texto ni del audio al registro
    registro = "\n".join(x.getMessage() for x in caplog.records)
    assert "cuatro pisos" not in registro and trozos_de()[0][:40] not in registro
    # Lo pedido se suelta al terminar
    assert not voz._en_curso and not voz._hablando


def test_el_texto_se_dice_como_en_el_navegador_y_el_cierre_como_el_reproductor(banco):
    b = banco()
    entrada = {**TORRE, "pasos": [{**TORRE["pasos"][0], "dice": "La torre tiene 3.369,6 m² y cumple la NSR-10."},
                                  *TORRE["pasos"][1:]]}
    r0 = _plan(b.db, 0, entrada)
    assert b.hablar({"rid": r0["id"], "n": 1, "frase": 0}).status_code == 200
    assert b.cliente.hablas()[-1]["text"] == "La torre tiene 3.369,6 metros cuadrados y cumple la ene ese erre diez."
    # El cierre: «En resumen. » y sus puntos, como lo dice reproductor.js
    r = b.hablar({"rid": r0["id"], "cierre": True})
    assert r.status_code == 200 and eventos(r.text)[-1]["tipo"] == "fin"
    assert b.cliente.hablas()[-1]["text"] == "En resumen. Cuatro pisos. Sigue atendiendo"


def test_un_plan_que_no_es_el_vigente_es_409_y_lo_que_no_esta_422(banco):
    b = banco()
    viejo = _plan(b.db, 0)
    nuevo = _plan(b.db, 0, {**TORRE, "titulo": "Otra vez la torre"})
    assert viejo["id"] != nuevo["id"]
    r = b.hablar({"rid": viejo["id"], "n": 1, "frase": 0})
    assert r.status_code == 409 and _detalle(r)["codigo"] == "plan_vencido"
    # El plan es el de la pantalla de quien pide: el de otra persona no le sirve
    r = b.hablar({"rid": nuevo["id"], "n": 1, "frase": 0}, uid=5)
    assert r.status_code == 409 and _detalle(r)["codigo"] == "plan_vencido"
    # Una escena o una frase que el plan no tiene
    for cuerpo in ({"rid": nuevo["id"], "n": 4, "frase": 0}, {"rid": nuevo["id"], "n": 1, "frase": 1}):
        r = b.hablar(cuerpo)
        assert r.status_code == 422 and _detalle(r)["codigo"] == "texto", cuerpo
    assert b.cliente.llamadas == []
    # Sin el guion de la presentación en el servidor, ningún plan vale
    import app.agente.guion as guion_presentacion
    original = guion_presentacion.cargar
    guion_presentacion.cargar = lambda *a: None
    try:
        r = b.hablar({"rid": nuevo["id"], "n": 1, "frase": 0})
    finally:
        guion_presentacion.cargar = original
    assert r.status_code == 409 and _detalle(r)["codigo"] == "plan_vencido"


def test_con_la_automatica_sirven_su_plan_y_el_anterior(banco):
    b = banco()
    db = b.db
    pantalla.marcar_vista(db, 0)
    pantalla.iniciar_auto(db, 0, G, "panel")
    torre = _plan(db, 0)
    assert pantalla.guardar_progreso(db, 0, {"rid": torre["id"], "n": 3, "de": 3, "fase": "fin", "frase": 0,
                                             "voz": "activa"}, G)
    auto = pantalla.siguiente_auto(db, 0, G)
    assert auto is not None and pantalla.recorrido_de(pantalla.leer(db, 0), G)["auto"] is True
    # El de la automática y, mientras suena ella, el anterior del asistente («Volver a reproducir» de su tarjeta)
    assert b.hablar({"rid": auto["id"], "n": 1, "frase": 0}).status_code == 200
    assert b.cliente.hablas()[-1]["text"] == voz.para_decir(auto["escenas"][0]["frases"][0])
    assert b.hablar({"rid": torre["id"], "n": 1, "frase": 0}).status_code == 200
    # Con `automatica` apagado, la automática va con la voz del navegador (409 `voz_apagada`, solo esa frase); el plan
    # del asistente sigue con la clonada
    b.voz["automatica"] = False
    r = b.hablar({"rid": auto["id"], "n": 1, "frase": 0})
    assert r.status_code == 409 and _detalle(r)["codigo"] == "voz_apagada"
    assert b.hablar({"rid": torre["id"], "n": 2, "frase": 0}).status_code == 200


DICTADO = "Yo, el administrador, autorizo entregar los recursos del proyecto a la empresa Inventada."


def test_un_plan_escrito_por_mcp_nunca_se_narra_con_la_voz_clonada(banco):
    # Por MCP, quien tenga la presentación escribe las frases del plan a mano (sin modelo de por medio): eso no lo
    # generó el sistema, así que va con la voz del navegador (409 `voz_apagada`), escena y cierre
    b = banco()
    pantalla.marcar_vista(b.db, 5)
    entrada = {**TORRE, "pasos": [{**TORRE["pasos"][0], "dice": DICTADO}, *TORRE["pasos"][1:]]}
    res = asyncio.run(hi.presentacion_en_pantalla(b.db, 5, hi.PresentacionEntrada.model_validate(entrada), "mcp"))
    r = pantalla.recorrido_de(pantalla.leer(b.db, 5), G)
    assert r["id"] == res.contenido["plan"]["id"] and r["escenas"][0]["frases"] == [DICTADO]
    assert r["externo"] is True and r["auto"] is False
    for cuerpo in ({"rid": r["id"], "n": 1, "frase": 0}, {"rid": r["id"], "n": 2, "frase": 0},
                   {"rid": r["id"], "cierre": True}):
        x = b.hablar(cuerpo, uid=5)
        assert x.status_code == 409 and _detalle(x) == {"codigo": "voz_apagada",
                                                         "mensaje": voz.MENSAJE_PLAN_EXTERNO}, cuerpo
    # Volver a reproducirlo desde el panel (otro id, `por` = panel) no le quita la marca
    otro = pantalla.controlar(b.db, 5, G, "reproducir", "panel", rid=r["id"])["recorrido"]
    assert otro["id"] != r["id"] and otro["externo"] is True
    x = b.hablar({"rid": otro["id"], "n": 1, "frase": 0}, uid=5)
    assert x.status_code == 409 and _detalle(x)["codigo"] == "voz_apagada"
    # Ni tras la presentación automática: el plan que ella reemplazó («Volver a reproducir» de su tarjeta) sigue marcado
    pantalla.iniciar_auto(b.db, 5, G, "panel")
    previo = pantalla.recorrido_previo(pantalla.leer(b.db, 5), G)
    assert previo["id"] == otro["id"] and previo["externo"] is True
    x = b.hablar({"rid": otro["id"], "n": 1, "frase": 0}, uid=5)
    assert x.status_code == 409 and _detalle(x)["codigo"] == "voz_apagada"
    otra_vez = pantalla.controlar(b.db, 5, G, "reproducir", "panel", rid=otro["id"])["recorrido"]
    assert otra_vez["externo"] is True
    x = b.hablar({"rid": otra_vez["id"], "cierre": True}, uid=5)
    assert x.status_code == 409 and _detalle(x)["codigo"] == "voz_apagada"
    assert b.cliente.hablas() == []
    # El mismo plan armado por el asistente sí se narra con la clonada
    propio = _plan(b.db, 6, entrada)
    assert propio["externo"] is False
    assert b.hablar({"rid": propio["id"], "n": 1, "frase": 0}, uid=6).status_code == 200
    assert [h["text"] for h in b.cliente.hablas()] == [DICTADO]


# ───────────────────────────── Las respuestas: solo con la firma del servidor ─────────────────────────────

FRASE = "La propuesta trae tres obras de salud para el municipio."


def test_una_frase_de_una_respuesta_con_su_firma(banco):
    b = banco()
    b.conversacion(31, 0)
    cuerpo = {"conversacion": 31, "texto": FRASE, "firma": b.firma(0, 31, FRASE)}
    r = b.hablar(cuerpo)
    assert r.status_code == 200, r.text
    ev = eventos(r.text)
    assert ev[0]["tipo"] == "inicio" and ev[0]["cache"] is False and ev[-1]["tipo"] == "fin"
    assert b.cliente.hablas()[-1]["text"] == FRASE
    # Las respuestas nunca se guardan (pueden traer datos de personas): la misma frase va otra vez a Mnemo
    r = b.hablar(cuerpo)
    assert r.status_code == 200 and eventos(r.text)[0]["cache"] is False and len(b.cliente.hablas()) == 2
    assert len(voz.cache_de(b.app)) == 0


def test_sin_la_firma_de_esa_persona_y_esa_conversacion_no_se_dice(banco):
    b = banco()
    b.conversacion(31, 0)
    b.conversacion(32, 0)
    b.conversacion(33, 5)
    bien = b.firma(0, 31, FRASE)
    for cuerpo in ({"conversacion": 31, "texto": FRASE + " Y algo más.", "firma": bien},    # otro texto
                   {"conversacion": 31, "texto": FRASE.replace("tres", "diez"), "firma": bien},
                   {"conversacion": 32, "texto": FRASE, "firma": bien},                     # otra conversación
                   {"conversacion": 31, "texto": FRASE, "firma": b.firma(5, 31, FRASE)},     # otra persona
                   {"conversacion": 31, "texto": FRASE, "firma": bien[:-1] + ("A" if bien[-1] != "A" else "B")},
                   {"conversacion": 31, "texto": FRASE,                                       # otra clave
                    "firma": voz.firmar(b"\0" * 32, 0, 31, FRASE)}):
        r = b.hablar(cuerpo)
        assert r.status_code == 422 and _detalle(r)["codigo"] == "texto", cuerpo
    # La firma es de esa persona: la conversación de otra es como si no existiera
    r = b.hablar({"conversacion": 33, "texto": FRASE, "firma": b.firma(0, 33, FRASE)})
    assert r.status_code == 404 and _detalle(r)["codigo"] == "no_existe"
    r = b.hablar({"conversacion": 40, "texto": FRASE, "firma": b.firma(0, 40, FRASE)})
    assert r.status_code == 404
    assert b.cliente.llamadas == []
    # La firma: HMAC-SHA256 de «uid␟conversación␟texto» con la clave derivada de la del administrador, en base64url sin
    # relleno (43 caracteres)
    import hashlib
    import hmac
    llave = hmac.new(voz.seguridad.llave_mnemo(CFG), b"voz-respuestas-v1", hashlib.sha256).digest()
    esperada = base64.urlsafe_b64encode(hmac.new(llave, f"0\x1f31\x1f{FRASE}".encode(), hashlib.sha256).digest())
    assert bien == esperada.rstrip(b"=").decode() and len(bien) == 43
    assert voz.llave_respuestas(CFG) == llave and llave != voz.seguridad.llave_mnemo(CFG)
    assert voz.firma_valida(llave, 0, 31, FRASE, bien) and not voz.firma_valida(llave, 0, 31, FRASE, None)


def test_una_conversacion_con_datos_de_habitantes_no_se_lee_en_voz_alta(banco):
    b = banco()
    b.conversacion(31, 0, personas=[1201])
    r = b.hablar({"conversacion": 31, "texto": FRASE, "firma": b.firma(0, 31, FRASE)})
    assert r.status_code == 409 and _detalle(r)["codigo"] == "con_personas"
    assert "datos de habitantes" in _detalle(r)["mensaje"] and b.cliente.llamadas == []


def test_lo_que_no_se_dice_ante_una_sala(banco):
    """Lo dicho es como lo proyectado: sin «@» ni números de 7 o más dígitos (aunque la firma valga)."""
    b = banco()
    b.conversacion(31, 0)
    for texto in ("Escríbale a rosa.inventada@example.org para coordinar.", "Su teléfono es 3001234567, llámela.",
                  "La cédula 1.234.567 no se dice.", "··· ···", "Su número es 300\u200b123\u200b4567, llámela.",
                  "Escríbale a rosa\u2060\uff20example.org hoy mismo."):
        r = b.hablar({"conversacion": 31, "texto": texto, "firma": b.firma(0, 31, texto)})
        assert r.status_code == 422 and _detalle(r)["codigo"] == "texto", texto
    assert b.cliente.llamadas == []
    # Lo que no se oye (un espacio de ancho cero, una marca de dirección) no va a Mnemo
    texto = "\u200bHola, esto trae\u200e un carácter invisible."
    assert b.hablar({"conversacion": 31, "texto": texto, "firma": b.firma(0, 31, texto)}).status_code == 200
    assert b.cliente.hablas()[-1]["text"] == "Hola, esto trae un carácter invisible."
    assert voz.hablable("Son 12.345 personas en 2026, con 45 % de avance.")
    assert not voz.hablable("") and not voz.hablable("   ") and not voz.hablable(None) and not voz.hablable("...")


def test_las_respuestas_solo_si_la_voz_lee_respuestas(banco):
    b = banco(ajustes_voz={**VOZ, "respuestas": False})
    b.conversacion(31, 0)
    r = b.hablar({"conversacion": 31, "texto": FRASE, "firma": b.firma(0, 31, FRASE)})
    assert r.status_code == 409 and _detalle(r)["codigo"] == "voz_apagada" and b.cliente.llamadas == []
    # La narración sigue con la voz clonada
    r0 = _plan(b.db, 0)
    assert b.hablar({"rid": r0["id"], "n": 1, "frase": 0}).status_code == 200


# ───────────────────────────── La prueba de Ajustes, quién y con qué ─────────────────────────────

def test_la_prueba_es_del_administrador_y_dice_la_frase_fija(banco):
    b = banco(ajustes_voz={**VOZ, "roles": ["coordinador"]})   # aunque su rol no la haga sonar
    r = b.hablar({"prueba": True})
    assert r.status_code == 200, r.text
    assert b.cliente.hablas()[-1]["text"] == voz.FRASE_PRUEBA and eventos(r.text)[-1]["ms_mnemo"] == 640
    # La segunda sale de la caché (la frase es fija): «inicio» lo dice
    r = b.hablar({"prueba": True})
    ev = eventos(r.text)
    assert ev[0]["cache"] is True and audio_de(ev) == AUDIO and ev[-1]["ms_mnemo"] is None
    assert len(b.cliente.hablas()) == 1
    for uid in (5, 8, 9):
        r = b.hablar({"prueba": True}, uid=uid)
        assert r.status_code == 403 and _detalle(r)["codigo"] == "voz_rol", uid


@pytest.mark.parametrize("uid, roles, estado", [
    (5, ["admin", "coordinador"], 200), (5, ["admin"], 403), (0, ["coordinador"], 403),
    (8, ["admin", "coordinador"], 403), (8, ["planillero"], 200), (9, ["admin", "consultor"], 200), (9, [], 403)])
def test_quien_la_hace_sonar_lo_decide_agente_voz_roles(banco, uid, roles, estado):
    b = banco(ajustes_voz={**VOZ, "roles": roles})
    r0 = _plan(b.db, uid)
    r = b.hablar({"rid": r0["id"], "n": 1, "frase": 0}, uid=uid)
    assert r.status_code == estado, r.text
    if estado == 403:
        assert _detalle(r)["codigo"] == "voz_rol" and b.cliente.llamadas == []


@pytest.mark.parametrize("cambio, mensaje", [
    ({"ajustes_voz": {**VOZ, "motor": "navegador"}}, "no está puesta la voz clonada"),
    ({"ajustes_voz": {**AUTO, "motor": "navegador"}}, "no está puesta la voz clonada"),
    ({"ajustes_voz": AUTO, "conexion": {**CONECTADA, "voz": False, "alcances": ["mnemo:read"]}},
     "Hablar con las voces"),
    ({"ajustes_voz": AUTO, "conexion": {**CONECTADA, "estado": "sin_conectar", "voz": False}}, "no está conectado"),
    ({"conexion": {**CONECTADA, "estado": "sin_conectar", "voz": False, "alcances": []}}, "no está conectado"),
    ({"conexion": {**CONECTADA, "estado": "caida", "motivo": "revocada", "voz": False}}, "no está conectado"),
    ({"conexion": {**CONECTADA, "voz": False, "alcances": ["mnemo:read", "mnemo:model"]}}, "Hablar con las voces"),
    ({"huella": "fedcba9876543210fedcba9876543210"}, "otra cuenta de Mnemo")])
def test_sin_voz_elegida_sin_el_permiso_o_de_otra_cuenta_es_409_sin_llamar_a_mnemo(banco, cambio, mensaje):
    b = banco(**cambio)
    r0 = _plan(b.db, 0)
    for cuerpo in ({"rid": r0["id"], "n": 1, "frase": 0}, {"prueba": True}):
        r = b.hablar(cuerpo)
        assert r.status_code == 409 and _detalle(r)["codigo"] == "sin_voz", cuerpo
        assert mensaje in _detalle(r)["mensaje"]
    assert b.cliente.llamadas == []


def test_sin_cliente_de_mnemo_es_409(banco, monkeypatch):
    b = banco()
    monkeypatch.setattr(voz, "_preparar", lambda app: (dict(CONECTADA), None, HUELLA))
    r = b.hablar({"prueba": True})
    assert r.status_code == 409 and _detalle(r)["codigo"] == "sin_voz"


# ───────────────────────────── Los errores de Mnemo ─────────────────────────────

def _mnemo(codigo: str, detalles: dict | None = None, estado: int = 200) -> ErrorHerramienta:
    """Un error que devolvió Mnemo (`isError`), como lo arma mnemo_cliente.py: con el mensaje en inglés de Mnemo."""
    return ErrorHerramienta(f"Mnemo dijo algo en inglés ({codigo}): secret provider text", mc.COD_MNEMO, estado=estado,
                            detalle={"code": codigo, "details": detalles})


TABLA_ERRORES = [
    # (error, estado, código, se recuerda)
    (_mnemo("NO_VOICE", {"reason": "not_shared"}), 409, "sin_voz", True),
    (_mnemo("NO_VOICE", {"reason": "expired"}), 409, "sin_voz", True),
    (_mnemo("PLAN_REQUIRED", {"feature": "voices"}), 409, "sin_voz", True),
    (_mnemo("UNAVAILABLE", {"reason": "speech"}), 409, "sin_voz", True),
    (_mnemo("UNAVAILABLE"), 409, "sin_voz", False),
    (ErrorHerramienta("Tool mnemo_speak not found", mc.COD_NO_DISPONIBLE), 409, "sin_voz", True),
    (ErrorHerramienta("expired", mc.COD_TOKEN, estado=401), 409, "sin_voz", False),
    (ErrorHerramienta("scope", mc.COD_TOKEN, estado=403), 409, "sin_voz", False),
    (ErrorHerramienta("cambio", mc.COD_TOKEN, detalle={"conexion": "cambio"}), 502, "mnemo_red", False),
    (_mnemo("CREDITS_EXHAUSTED", {"resets_at": "2026-11-23"}), 402, "mnemo_creditos", False),
    (_mnemo("RATE_LIMITED"), 429, "frecuencia", False),
    (ErrorHerramienta("429", mc.COD_MNEMO, estado=429), 429, "frecuencia", False),
    (_mnemo("INVALID_ARGUMENT", {"field": "text"}), 422, "texto", False),
    (_mnemo("TIMEOUT"), 502, "mnemo_red", False),
    (ErrorHerramienta("red", mc.COD_RED), 502, "mnemo_red", False),
    (ErrorHerramienta("plazo", mc.COD_PLAZO), 502, "mnemo_red", False),
    (_mnemo("INTERNAL"), 502, "mnemo", False),
    (_mnemo("FAILED"), 502, "mnemo", False),
    (ErrorHerramienta("503", mc.COD_MNEMO, estado=503), 502, "mnemo", False),
]


@pytest.mark.parametrize("error, estado, codigo, recuerda", TABLA_ERRORES)
def test_cada_fallo_de_mnemo_tiene_su_respuesta(banco, caplog, error, estado, codigo, recuerda):
    b = banco()
    b.cliente.fallo = error
    with caplog.at_level(logging.DEBUG):
        r = b.hablar({"prueba": True})
    assert r.status_code == estado, r.text
    d = _detalle(r)
    assert d["codigo"] == codigo and "secret" not in d["mensaje"] and "inglés" not in d["mensaje"]
    if codigo == "frecuencia":
        assert r.headers["Retry-After"] == "30"
    # Al registro, solo el código
    registro = "\n".join(x.getMessage() for x in caplog.records)
    assert "secret" not in registro and voz.FRASE_PRUEBA not in registro and codigo in registro
    # «Mnemo no puede con esa voz» se recuerda (`estado.voz.disponible` en falso) para esta conexión y esta voz
    av = politica.ajustes_voz({"agente_voz": b.voz})
    assert voz.puede(b.app, CONECTADA, av, HUELLA) is (not recuerda)
    assert not voz._en_curso and not voz._hablando and not voz.vuelos_de(b.app)
    assert len(voz.cache_de(b.app)) == 0


def test_traducir_cubre_la_tabla():
    for error, estado, codigo, recuerda in TABLA_ERRORES:
        e, r = voz.traducir(error)
        assert (e.status_code, e.codigo, r) == (estado, codigo, recuerda), error.detalle
        assert e.detail == {"codigo": codigo, "mensaje": e.mensaje} and "secret" not in e.mensaje


def test_el_recuerdo_es_de_esa_conexion_y_esa_voz_y_un_acierto_lo_borra(banco, monkeypatch):
    b = banco()
    av = politica.ajustes_voz({"agente_voz": b.voz})
    b.cliente.fallo = _mnemo("NO_VOICE", {"reason": "not_ready"})
    assert b.hablar({"prueba": True}).status_code == 409
    assert voz.puede(b.app, CONECTADA, av, HUELLA) is False
    # Otra voz elegida, u otra conexión (volvió a conectar), no cargan con el recuerdo
    assert voz.puede(b.app, CONECTADA, {**av, "voz": OTRA_VOZ}, HUELLA) is True
    assert voz.puede(b.app, {**CONECTADA, "desde": "2026-11-02T09:00:00+00:00"}, av, HUELLA) is True
    # Pasada la hora, se olvida
    ahora = voz.time.monotonic()
    monkeypatch.setattr(voz.time, "monotonic", lambda: ahora + voz.OLVIDO_S + 1)
    assert voz.puede(b.app, CONECTADA, av, HUELLA) is True
    monkeypatch.undo()
    # La ruta no deja de intentarlo: si ya se puede, el recuerdo se borra
    b = banco()
    b.cliente.fallo = _mnemo("PLAN_REQUIRED", {"feature": "voices"})
    assert b.hablar({"prueba": True}).status_code == 409 and voz.puede(b.app, CONECTADA, av, HUELLA) is False
    b.cliente.fallo = None
    assert b.hablar({"prueba": True}).status_code == 200 and voz.puede(b.app, CONECTADA, av, HUELLA) is True


def test_un_fallo_a_mitad_sale_en_el_flujo_y_no_queda_en_la_cache(banco):
    b = banco()
    r0 = _plan(b.db, 0)
    b.cliente.fallo, b.cliente.fallo_tras = _mnemo("INTERNAL"), 1
    r = b.hablar({"rid": r0["id"], "n": 1, "frase": 0})
    assert r.status_code == 200
    ev = eventos(r.text)
    assert [e["tipo"] for e in ev] == ["inicio", "audio", "error"]
    assert ev[-1] == {"tipo": "error", "codigo": "mnemo", "mensaje": voz.MENSAJE_FALLO}
    assert len(voz.cache_de(b.app)) == 0
    # La siguiente vez se pide otra vez a Mnemo
    b.cliente.fallo, b.cliente.fallo_tras = None, None
    r = b.hablar({"rid": r0["id"], "n": 1, "frase": 0})
    assert eventos(r.text)[-1]["tipo"] == "fin" and len(b.cliente.hablas()) == 2


def test_mnemo_sin_audio_o_sin_avance(banco):
    b = banco()
    r0 = _plan(b.db, 0)
    # Un Mnemo que no manda avance: el audio entero en la salida, partido en trozos de 200 ms de PCM
    b.cliente.progreso = False
    r = b.hablar({"rid": r0["id"], "n": 1, "frase": 0})
    ev = eventos(r.text)
    assert ev[0]["formato"] == "pcm_s16le" and audio_de(ev) == AUDIO and ev[-1]["tipo"] == "fin"
    assert [len(base64.b64decode(e["datos"])) for e in ev if e["tipo"] == "audio"] == [9600, 9600, 3840]
    # Sin audio de ningún modo: 502 antes del flujo (no llegó ni el aviso `start`)
    b2 = banco(cliente=ClienteFalso(audio=b""))
    b2.cliente.progreso = False
    r1 = _plan(b2.db, 0)
    r = b2.hablar({"rid": r1["id"], "n": 1, "frase": 0})
    assert r.status_code == 502 and _detalle(r)["codigo"] == "mnemo"
    # Con el `start` y sin audio, el error llega en el flujo; nada queda en la caché
    b2.cliente.progreso = True
    r = b2.hablar({"rid": r1["id"], "n": 1, "frase": 0})
    assert r.status_code == 200 and [e["tipo"] for e in eventos(r.text)] == ["inicio", "error"]
    assert eventos(r.text)[-1]["codigo"] == "mnemo" and len(voz.cache_de(b2.app)) == 0


def test_sin_pcm_se_pasa_el_formato_que_dio_mnemo(banco):
    """Sin ffmpeg, Mnemo entrega el formato original (mp3) y lo dice: el navegador decodifica la frase entera."""
    b = banco()
    b.cliente.inicio = {"type": "start", "format": "mp3", "mime": "audio/mpeg", "sample_rate": None,
                        "channels": None, "mode": "direct"}
    r = b.hablar({"prueba": True})
    ev = eventos(r.text)
    assert ev[0] == {"tipo": "inicio", "formato": "mp3", "muestreo": None, "canales": None, "cache": False,
                     "voz": "Ana (voz de prueba)"}
    assert audio_de(ev) == AUDIO
    # Lo que no tiene la forma esperada no pasa
    assert voz._inicio_de({"format": "<script>"})["formato"] == "desconocido"
    assert voz._inicio_de({"format": "pcm_s16le_16000"}) == {"formato": "pcm_s16le", "muestreo": 16000, "canales": 1}
    assert voz._inicio_de({}) == {"formato": "pcm_s16le", "muestreo": 24000, "canales": 1}


def test_los_avisos_raros_de_mnemo_se_ignoran():
    async def probar():
        v = voz.Vuelo("clave", False)
        for p in (None, {}, {"message": None}, {"message": "texto suelto"}, {"message": "{no json"},
                  {"message": "[1, 2]"}, {"message": json.dumps({"type": "audio", "data": "no es base64!"})},
                  {"message": json.dumps({"type": "audio", "data": "QUJD"[:3]})},
                  {"message": json.dumps({"type": "audio", "data": 12})}, {"message": json.dumps({"type": "otro"})}):
            v.al_progreso(p)
        assert v.trozos == [] and v.inicio is None
        v.al_progreso({"message": json.dumps({"type": "audio", "seq": 1, "data": b64(b"\0\1")})})
        assert v.trozos == [b64(b"\0\1")] and v.bytes == 2 and v.inicio["formato"] == "pcm_s16le"
        # Más audio del que cabe en una frase: se corta
        with pytest.raises(voz.ErrorVoz):
            v.agregar("AAAA", voz.MAX_AUDIO)
    asyncio.run(probar())


# ───────────────────────────── Los topes ─────────────────────────────

def test_dos_frases_a_la_vez_por_persona():
    a = voz.tomar("base", 7)
    b = voz.tomar("base", 7)   # la que suena y la siguiente, que el navegador precarga
    with pytest.raises(voz.ErrorVoz) as e:
        voz.tomar("base", 7)
    assert e.value.status_code == 429 and e.value.detail == {"codigo": "frecuencia", "mensaje": voz.MENSAJE_A_LA_VEZ}
    assert e.value.headers["Retry-After"] == str(voz.ESPERA_TURNO_S)
    # Otra persona, u otra base, no esperan por ella
    otras = [voz.tomar("base", 8), voz.tomar("otra", 7)]
    a.soltar()
    a.soltar()   # soltar dos veces no libera un lugar ajeno
    c = voz.tomar("base", 7)
    with pytest.raises(voz.ErrorVoz):
        voz.tomar("base", 7)
    for f in (b, c, *otras):
        f.soltar()
    assert not voz._en_curso


def test_noventa_frases_por_minuto(banco, monkeypatch):
    ahora = [1000.0]
    monkeypatch.setattr(voz.time, "monotonic", lambda: ahora[0])
    for _ in range(voz.FRECUENCIA_MAX):
        voz.frecuencia("base", 7)
        ahora[0] += 0.1
    with pytest.raises(voz.ErrorVoz) as e:
        voz.frecuencia("base", 7)
    assert e.value.status_code == 429 and e.value.codigo == "frecuencia"
    assert 1 <= int(e.value.headers["Retry-After"]) <= voz.FRECUENCIA_S
    voz.frecuencia("base", 8)   # otra persona sí
    ahora[0] += voz.FRECUENCIA_S
    voz.frecuencia("base", 7)   # pasado el minuto, sí
    # Por la ruta: lo rechazado no llega a Mnemo
    monkeypatch.undo()
    voz._ventanas.clear()
    b = banco()
    for _ in range(voz.FRECUENCIA_MAX):
        assert b.hablar({"prueba": True}).status_code == 200
    r = b.hablar({"prueba": True})
    assert r.status_code == 429 and _detalle(r)["codigo"] == "frecuencia" and len(b.cliente.hablas()) == 1


def test_treinta_mil_caracteres_por_dia_de_lo_que_va_a_mnemo(banco, monkeypatch):
    hoy = [__import__("datetime").date(2026, 11, 20)]
    monkeypatch.setattr(voz.modelo, "hoy_local", lambda: hoy[0])
    voz.diarias("base", 7, voz.CARACTERES_DIA - 10)
    voz.diarias("base", 7, 10)
    with pytest.raises(voz.ErrorVoz) as e:
        voz.diarias("base", 7, 1)
    assert e.value.status_code == 429 and e.value.codigo == "volumen" and "voz del navegador" in e.value.mensaje
    voz.diarias("base", 8, 500)   # otra persona sí
    hoy[0] = __import__("datetime").date(2026, 11, 21)
    voz.diarias("base", 7, 1)     # otro día, de nuevo
    # Por la ruta: cuenta lo dicho (como se dice), y lo que sale de la caché no gasta
    voz._diarias.clear()
    b = banco()
    r0 = _plan(b.db, 0)
    assert b.hablar({"rid": r0["id"], "n": 1, "frase": 0}).status_code == 200
    usado = len("Aquí va la torre nueva.")
    assert voz._diarias[(b.db.name, 0)] == (hoy[0].isoformat(), usado)
    assert b.hablar({"rid": r0["id"], "n": 1, "frase": 0}).status_code == 200   # de la caché
    assert voz._diarias[(b.db.name, 0)][1] == usado
    voz._diarias[(b.db.name, 0)] = (hoy[0].isoformat(), voz.CARACTERES_DIA - 3)
    r = b.hablar({"rid": r0["id"], "n": 2, "frase": 0})
    assert r.status_code == 429 and _detalle(r)["codigo"] == "volumen"
    assert b.hablar({"rid": r0["id"], "n": 1, "frase": 0}).status_code == 200   # la de la caché sigue
    assert len(b.cliente.hablas()) == 1 and not voz._en_curso


def test_tres_llamadas_a_mnemo_a_la_vez_en_el_proceso(monkeypatch):
    monkeypatch.setattr(voz, "VIGILA_S", 0.01)
    monkeypatch.setattr(voz, "ESPERA_CUPO_S", 0.2)

    async def probar():
        suelta = asyncio.Event()
        dentro = []

        async def hablar():
            async with voz.cupo():
                dentro.append(1)
                await suelta.wait()
        tareas = [asyncio.ensure_future(hablar()) for _ in range(voz.A_LA_VEZ)]
        await _hasta(lambda: len(dentro) == voz.A_LA_VEZ)
        with pytest.raises(voz.ErrorVoz) as e:   # la cuarta espera y después 429
            async with voz.cupo():
                pass
        assert e.value.status_code == 429 and e.value.mensaje == voz.MENSAJE_OCUPADO
        # Una que espera entra en cuanto otra suelta su cupo
        cuarta = asyncio.ensure_future(hablar())
        await asyncio.sleep(0.05)
        assert len(dentro) == voz.A_LA_VEZ
        tareas[0].cancel()   # una que se cancela también suelta
        await _hasta(lambda: len(dentro) == voz.A_LA_VEZ + 1)
        suelta.set()
        await asyncio.gather(*tareas[1:], cuarta)
        assert not voz._hablando
    asyncio.run(probar())


# ───────────────────────────── La caché de la narración ─────────────────────────────

def test_la_narracion_se_guarda_en_la_cache_y_se_vacia_al_cambiar_de_voz(banco):
    b = banco()
    r0 = _plan(b.db, 0)
    cuerpo = {"rid": r0["id"], "n": 1, "frase": 0}
    primera = eventos(b.hablar(cuerpo).text)
    segunda = eventos(b.hablar(cuerpo).text)
    assert primera[0]["cache"] is False and segunda[0]["cache"] is True
    assert audio_de(primera) == audio_de(segunda) == AUDIO and len(b.cliente.hablas()) == 1
    assert segunda[-1]["tipo"] == "fin" and segunda[-1]["bytes"] == len(AUDIO) and segunda[-1]["ms_mnemo"] is None
    # La misma frase en otro plan (u otra persona con el mismo plan) también sale de la caché: la clave es el texto
    otro = _plan(b.db, 5)
    assert eventos(b.hablar({"rid": otro["id"], "n": 1, "frase": 0}, uid=5).text)[0]["cache"] is True
    assert voz.clave_de(VOZ_ID, "Aquí va la torre nueva.") == __import__("hashlib").sha256(
        f"{VOZ_ID}\x1fpcm_s16le_24000\x1fAquí va la torre nueva.".encode()).hexdigest()
    # Otra voz elegida: la caché se vacía
    b.voz = {**VOZ, "voz": OTRA_VOZ, "nombre": "Beto"}
    ev = eventos(b.hablar(cuerpo).text)
    assert ev[0]["cache"] is False and ev[0]["voz"] == "Beto" and b.cliente.hablas()[-1]["voice_id"] == OTRA_VOZ
    assert len(voz.cache_de(b.app)) == 1


def test_la_cache_es_lru_por_tamano_y_con_vida():
    ahora = [0.0]
    c = voz.Cache(maximo=1000, vida=60, reloj=lambda: ahora[0])
    c.de_voz("v")
    inicio = {"formato": "pcm_s16le", "muestreo": 24000, "canales": 1}
    assert c.guardar("a", inicio, ["A" * 300], 225) and c.guardar("b", inicio, ["B" * 300], 225)
    assert c.leer("a") is not None   # «a» es la más reciente ahora
    assert c.guardar("c", inicio, ["C" * 300], 225)
    assert c.leer("b") is None and c.leer("a") is not None and c.leer("c") is not None and c.peso <= 1000
    # Una frase que no cabe entera no se guarda (ni saca a las demás)
    assert c.guardar("d", inicio, ["D" * 2000], 1500) is False and len(c) == 2
    # Con vida: pasado el plazo ya no está
    ahora[0] = 61
    assert c.leer("a") is None and c.leer("c") is None and c.peso == 0
    # Otra voz la vacía; la misma no
    c.guardar("e", inicio, ["E"], 1)
    c.de_voz("v")
    assert len(c) == 1
    c.de_voz("w")
    assert len(c) == 0 and c.peso == 0


@pytest.mark.parametrize("retiro", [_mnemo("NO_VOICE", {"reason": "not_shared"}),
                                    _mnemo("PLAN_REQUIRED", {"feature": "voices"}),
                                    ErrorHerramienta("expired", mc.COD_TOKEN, estado=401)])
def test_cuando_mnemo_retira_la_voz_la_cache_se_vacia(banco, retiro):
    # Un televisor con la presentación automática vive de la caché: si la persona borra la voz en Mnemo (o la
    # desmarca, o se revoca la conexión), lo guardado no se sigue diciendo con ella
    b = banco()
    r0 = _plan(b.db, 0)
    c1, c2 = {"rid": r0["id"], "n": 1, "frase": 0}, {"rid": r0["id"], "n": 2, "frase": 0}
    assert eventos(b.hablar(c1).text)[0]["cache"] is False
    assert eventos(b.hablar(c1).text)[0]["cache"] is True and len(b.cliente.hablas()) == 1
    b.cliente.fallo = retiro
    r = b.hablar(c2)
    assert r.status_code == 409 and _detalle(r)["codigo"] == "sin_voz"
    assert len(voz.cache_de(b.app)) == 0
    # La frase que estaba guardada ya no sale de la caché: la decide Mnemo, que dice que no
    r = b.hablar(c1)
    assert r.status_code == 409 and _detalle(r)["codigo"] == "sin_voz" and len(b.cliente.hablas()) == 3


def test_mientras_se_recuerda_el_no_de_mnemo_la_cache_no_se_lee(banco):
    b = banco()
    r0 = _plan(b.db, 0)
    c1, c2 = {"rid": r0["id"], "n": 1, "frase": 0}, {"rid": r0["id"], "n": 2, "frase": 0}
    assert b.hablar(c1).status_code == 200
    entrada = next(iter(voz.cache_de(b.app)._d.items()))
    b.cliente.fallo = _mnemo("NO_VOICE", {"reason": "expired"})
    assert b.hablar(c2).status_code == 409 and len(voz.cache_de(b.app)) == 0
    # Aunque algo la vuelva a guardar (un vuelo que terminó tarde), mientras se recuerda el «no» la pide a Mnemo...
    voz.cache_de(b.app).guardar(entrada[0], entrada[1].inicio, list(entrada[1].trozos), entrada[1].bytes)
    r = b.hablar(c1)
    assert r.status_code == 409 and len(b.cliente.hablas()) == 3
    # ...y si Mnemo ya la deja (la volvieron a marcar para las apps), el acierto borra el «no» y la guarda otra vez
    b.cliente.fallo = None
    assert eventos(b.hablar(c1).text)[0]["cache"] is False and len(b.cliente.hablas()) == 4
    assert eventos(b.hablar(c1).text)[0]["cache"] is True and len(b.cliente.hablas()) == 4


def _vieja(b) -> None:
    """Mnemo aceptó la voz hace más de `REVALIDAR_S` (la presentación vivía de la caché)."""
    b.app.state.voz_aceptada = (CONECTADA["desde"], VOZ_ID, voz.time.monotonic() - voz.REVALIDAR_S - 1)


def _nombres(b) -> list[str]:
    return [n for n, *_ in b.cliente.llamadas]


def test_la_cache_se_revisa_con_mnemo_cada_diez_minutos(banco):
    assert voz.REVALIDAR_S == 600
    b = banco()
    r0 = _plan(b.db, 0)
    c1 = {"rid": r0["id"], "n": 1, "frase": 0}
    assert b.hablar(c1).status_code == 200 and _nombres(b) == ["mnemo_speak"]
    # Dentro de los diez minutos, sale de la caché sin preguntarle nada a Mnemo
    assert eventos(b.hablar(c1).text)[0]["cache"] is True and _nombres(b) == ["mnemo_speak"]
    # Pasados, se pregunta si la sigue ofreciendo (`mnemo_list_voices`, sin gastar): sí, y sale de la caché
    _vieja(b)
    assert eventos(b.hablar(c1).text)[0]["cache"] is True
    assert _nombres(b) == ["mnemo_speak", "mnemo_list_voices"]
    assert eventos(b.hablar(c1).text)[0]["cache"] is True and len(_nombres(b)) == 2   # queda aceptada otra vez
    # Si Mnemo no responde (la red, el plazo, un fallo suyo), no dijo que no: sale de la caché
    for fallo in (ErrorHerramienta("red", mc.COD_RED), ErrorHerramienta("plazo", mc.COD_PLAZO), _mnemo("INTERNAL")):
        _vieja(b)
        b.cliente.fallo = fallo
        assert eventos(b.hablar(c1).text)[0]["cache"] is True, fallo.codigo
    assert b.cliente.hablas() == [b.cliente.hablas()[0]] and len(voz.cache_de(b.app)) == 1
    # Ya no la ofrece (la borraron o la desmarcaron): 409 `sin_voz`, la caché se vacía y se recuerda el «no»
    b.cliente.fallo = None
    b.cliente.voces = [v for v in b.cliente.voces if v["voice_id"] != VOZ_ID]
    _vieja(b)
    antes = len(_nombres(b))
    r = b.hablar(c1)
    assert r.status_code == 409 and _detalle(r) == {"codigo": "sin_voz", "mensaje": voz.MENSAJE_SIN_ESA_VOZ}
    assert _nombres(b)[antes:] == ["mnemo_list_voices"] and len(voz.cache_de(b.app)) == 0
    assert voz.puede(b.app, CONECTADA, politica.ajustes_voz({"agente_voz": b.voz}), HUELLA) is False
    assert not voz._en_curso and not voz._hablando


@pytest.mark.parametrize("fallo", [_mnemo("NO_VOICE", {"reason": "not_shared"}),
                                   ErrorHerramienta("expired", mc.COD_TOKEN, estado=401)])
def test_si_al_revisar_mnemo_dice_que_no_la_cache_se_vacia(banco, fallo):
    b = banco()
    r0 = _plan(b.db, 0)
    c1 = {"rid": r0["id"], "n": 1, "frase": 0}
    assert b.hablar(c1).status_code == 200
    _vieja(b)
    b.cliente.fallo = fallo
    r = b.hablar(c1)
    assert r.status_code == 409 and _detalle(r)["codigo"] == "sin_voz"
    assert _nombres(b) == ["mnemo_speak", "mnemo_list_voices"] and len(voz.cache_de(b.app)) == 0


def test_listar_sin_la_voz_elegida_vacia_la_cache(banco):
    b = banco()
    r0 = _plan(b.db, 0)
    assert b.hablar({"rid": r0["id"], "n": 1, "frase": 0}).status_code == 200 and len(voz.cache_de(b.app)) == 1
    b.cliente.voces = [v for v in b.cliente.voces if v["voice_id"] != VOZ_ID]
    d = b.http.get("/api/agente/voces").json()
    assert d["elegida"] is None and [v["id"] for v in d["voces"]] == [OTRA_VOZ]
    assert len(voz.cache_de(b.app)) == 0
    assert voz.puede(b.app, CONECTADA, politica.ajustes_voz({"agente_voz": b.voz}), HUELLA) is False
    # Si la lista falla porque la conexión venció, también
    b.cliente.voces = ClienteFalso().voces
    assert b.hablar({"rid": r0["id"], "n": 1, "frase": 0}).status_code == 200 and len(voz.cache_de(b.app)) == 1
    b.cliente.fallo = ErrorHerramienta("expired", mc.COD_TOKEN, estado=401)
    assert b.http.get("/api/agente/voces").status_code == 409 and len(voz.cache_de(b.app)) == 0


# ───────────────────────────── Un solo vuelo y la cancelación ─────────────────────────────

def test_la_precarga_y_la_reproduccion_se_cuelgan_de_la_misma_llamada(banco):
    """Dos peticiones iguales a la vez (la precarga del navegador y la reproducción, o dos ventanas): una sola llamada a
    Mnemo, y la que llega tarde recibe lo ya producido y lo que viene."""
    b = banco()
    r0 = _plan(b.db, 0)
    cuerpo = {"rid": r0["id"], "n": 1, "frase": 0}

    async def probar():
        b.cliente.puerta = asyncio.Event()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=b.app), base_url="http://t") as c:
            primera = asyncio.ensure_future(c.post("/api/agente/voz", json=cuerpo, headers={"x-uid": "0"}))
            await _hasta(lambda: b.cliente.mandados == 1)   # el primer trozo ya salió
            segunda = asyncio.ensure_future(c.post("/api/agente/voz", json=cuerpo, headers={"x-uid": "0"}))
            await _hasta(lambda: any(v.oyentes == 2 for v in voz.vuelos_de(b.app).values()))
            b.cliente.puerta.set()
            return await primera, await segunda
    r1, r2 = asyncio.run(probar())
    e1, e2 = eventos(r1.text), eventos(r2.text)
    assert len(b.cliente.hablas()) == 1
    assert audio_de(e1) == audio_de(e2) == AUDIO and e1[-1]["tipo"] == e2[-1]["tipo"] == "fin"
    assert e2[0]["cache"] is False   # no salió de la caché: se colgó del vuelo
    assert not voz.vuelos_de(b.app) and not voz._en_curso and len(voz.cache_de(b.app)) == 1


def test_las_respuestas_tambien_comparten_el_vuelo_pero_solo_de_la_misma_persona(banco):
    b = banco()
    b.conversacion(31, 0)
    b.conversacion(32, 5)
    c0 = {"conversacion": 31, "texto": FRASE, "firma": b.firma(0, 31, FRASE)}
    c5 = {"conversacion": 32, "texto": FRASE, "firma": b.firma(5, 32, FRASE)}
    assert voz.clave_de(VOZ_ID, FRASE, "respuesta\x1f0") != voz.clave_de(VOZ_ID, FRASE, "respuesta\x1f5")

    async def probar():
        b.cliente.puerta = asyncio.Event()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=b.app), base_url="http://t") as c:
            rs = [asyncio.ensure_future(c.post("/api/agente/voz", json=x, headers={"x-uid": u}))
                  for x, u in ((c0, "0"), (c0, "0"), (c5, "5"))]
            await _hasta(lambda: sum(v.oyentes for v in voz.vuelos_de(b.app).values()) == 3)
            assert len(voz.vuelos_de(b.app)) == 2
            b.cliente.puerta.set()
            return [await r for r in rs]
    rs = asyncio.run(probar())
    assert all(audio_de(eventos(r.text)) == AUDIO for r in rs)
    assert len(b.cliente.hablas()) == 2 and len(voz.cache_de(b.app)) == 0


def test_si_nadie_escucha_se_cancela_la_llamada_a_mnemo(banco):
    b = banco()
    r0 = _plan(b.db, 0)
    cuerpo = {"rid": r0["id"], "n": 1, "frase": 0}

    async def probar():
        b.cliente.puerta = asyncio.Event()
        se_fue = asyncio.Event()

        async def recibir():
            await se_fue.wait()
            return {"type": "http.disconnect"}
        tarea = asyncio.ensure_future(b.crudo(cuerpo, recibir))
        await _hasta(lambda: b.cliente.mandados == 1)
        se_fue.set()   # el navegador se va a mitad de la frase (el reproductor la calló, cerró la pestaña…)
        enviados = await tarea
        await _hasta(lambda: b.cliente.canceladas == 1 and not voz._en_curso)
        return enviados
    enviados = asyncio.run(probar())
    assert enviados[0]["status"] == 200
    assert b.cliente.canceladas == 1 and not voz.vuelos_de(b.app) and not voz._hablando
    assert len(voz.cache_de(b.app)) == 0   # no llegó entera: no se guarda


def test_si_una_de_dos_se_va_la_otra_sigue_y_queda_en_la_cache(banco):
    b = banco()
    r0 = _plan(b.db, 0)
    cuerpo = {"rid": r0["id"], "n": 1, "frase": 0}

    async def probar():
        b.cliente.puerta = asyncio.Event()
        se_fue = asyncio.Event()

        async def recibir():
            await se_fue.wait()
            return {"type": "http.disconnect"}

        async def nunca():
            await asyncio.Event().wait()
        precarga = asyncio.ensure_future(b.crudo(cuerpo, recibir))
        await _hasta(lambda: b.cliente.mandados == 1)
        sonando = asyncio.ensure_future(b.crudo(cuerpo, nunca, uid=0))
        await _hasta(lambda: any(v.oyentes == 2 for v in voz.vuelos_de(b.app).values()))
        se_fue.set()
        await precarga
        await _hasta(lambda: any(v.oyentes == 1 for v in voz.vuelos_de(b.app).values()))
        b.cliente.puerta.set()
        return await asyncio.wait_for(sonando, 5)
    enviados = asyncio.run(probar())
    ev = eventos_crudos(enviados)
    assert audio_de(ev) == AUDIO and ev[-1]["tipo"] == "fin"
    assert b.cliente.canceladas == 0 and len(voz.cache_de(b.app)) == 1 and not voz._en_curso


def test_si_se_va_antes_de_que_empiece_tampoco_se_gasta(banco):
    b = banco()
    b.cliente.inicio = None   # Mnemo todavía no dijo nada

    async def probar():
        b.cliente.puerta = asyncio.Event()
        b.cliente.audio = AUDIO
        espera = asyncio.Event()

        async def lento(nombre, argumentos, plazo=60, al_progreso=None, *, tope=None):
            b.cliente.llamadas.append((nombre, argumentos, plazo, tope))
            try:
                await espera.wait()
            except asyncio.CancelledError:
                b.cliente.canceladas += 1
                raise
        b.cliente.llamar = lento

        async def recibir():
            await asyncio.sleep(0.05)
            return {"type": "http.disconnect"}
        enviados = await b.crudo({"prueba": True}, recibir)
        await _hasta(lambda: b.cliente.canceladas == 1)
        return enviados
    enviados = asyncio.run(probar())
    assert enviados[0]["status"] == 400 and json.loads(enviados[1]["body"])["detail"]["codigo"] == "cortada"
    assert not voz._en_curso and not voz.vuelos_de(b.app) and not voz._hablando


def test_una_respuesta_que_nunca_empieza_a_leerse_suelta_el_vuelo(banco, monkeypatch):
    """Un flujo que nunca empezó no corre su `finally` (el navegador se fue entre la respuesta y el primer trozo): el
    vigía suelta el lugar y cancela la llamada a Mnemo (como `ESPERA_ARRANQUE_S` del turno del asistente)."""
    monkeypatch.setattr(voz, "ESPERA_ARRANQUE_S", 0.1)
    b = banco()

    async def probar():
        b.cliente.puerta = asyncio.Event()

        async def recibir():
            await asyncio.Event().wait()
        alcance = {"type": "http", "method": "POST", "path": "/api/agente/voz", "headers": [], "app": b.app,
                   "query_string": b""}
        request = Request(alcance, recibir)
        respuesta = await voz.hablar(request, QUIENES[0], {"prueba": True})   # nadie lee el cuerpo
        assert respuesta.media_type == "application/x-ndjson" and voz._en_curso
        await _hasta(lambda: b.cliente.canceladas == 1 and not voz._en_curso)
    asyncio.run(probar())
    assert not voz.vuelos_de(b.app)


# ───────────────────────────── Nada al registro ─────────────────────────────

def test_ni_el_texto_ni_el_audio_ni_la_firma_van_al_registro(banco, caplog):
    b = banco()
    b.conversacion(31, 0)
    texto = SECRETO + ", y pide una cita."
    firma = b.firma(0, 31, texto)
    with caplog.at_level(logging.DEBUG):
        assert b.hablar({"conversacion": 31, "texto": texto, "firma": firma}).status_code == 200
        b.cliente.fallo = _mnemo("INTERNAL")
        assert b.hablar({"conversacion": 31, "texto": texto, "firma": firma}).status_code == 502
        b.cliente.fallo, b.cliente.fallo_tras = _mnemo("CREDITS_EXHAUSTED"), 1
        assert b.hablar({"conversacion": 31, "texto": texto, "firma": firma}).status_code == 200
        assert b.hablar({"conversacion": 31, "texto": texto + "!", "firma": firma}).status_code == 422
    registro = "\n".join(f"{x.name} {x.getMessage()}" for x in caplog.records)
    for secreto in ("Rosa Inventada", "El Ejemplo", firma, trozos_de()[0][:32], VOZ_ID):
        assert secreto not in registro, secreto
    assert "mnemo_creditos" in registro or "mnemo" in registro


# ───────────────────────────── Con el cliente de Mnemo de verdad y el MCP falso ─────────────────────────────

def _mnemo_que_habla(manejador=None):
    """El MCP falso con `mnemo_speak` y `mnemo_list_voices`, como los lista Mnemo (sección 1.7 del contrato)."""
    from ayudas_mcp import LECTURA, MnemoFalso, correcto, herramienta
    falso = MnemoFalso()
    falso.herramientas.append(herramienta("mnemo_list_voices", "List voices", {}, [], LECTURA))
    falso.herramientas.append(herramienta("mnemo_speak", "Speak", {
        "voice_id": {"type": "string"}, "text": {"type": "string", "minLength": 1, "maxLength": 1000},
        "format": {"type": "string", "enum": ["pcm_s16le_24000", "mp3"]}, "language": {"type": "string"}},
        ["voice_id", "text"], LECTURA))

    async def habla(args, avisar):
        await avisar(1, json.dumps({"type": "start", "format": "pcm_s16le_24000", "mime": "audio/pcm",
                                    "sample_rate": 24000, "channels": 1, "mode": "stream"}))
        for i, t in enumerate(trozos_de()):
            await avisar(i + 2, json.dumps({"type": "audio", "seq": i + 1, "data": t}))
        return correcto({"voice_id": args["voice_id"], "format": "pcm_s16le_24000", "mime": "audio/pcm",
                         "sample_rate": 24000, "channels": 1, "characters": len(args["text"]), "bytes": len(AUDIO),
                         "chunks": 3, "first_audio_ms": 512, "total_ms": 1900, "duration_ms": 480, "mode": "stream",
                         "streamed": True, "usage": {"credits": 0.4}})

    async def voces(args):
        return correcto({"voices": [{"voice_id": VOZ_ID, "name": "Ana (voz de prueba)", "language": "es",
                                     "engine": "minimax", "status": "ready"}], "default_voice_id": VOZ_ID})
    falso.manejadores["mnemo_speak"] = manejador or habla
    falso.manejadores["mnemo_list_voices"] = voces
    return falso


def test_con_el_cliente_mcp_de_verdad(banco, monkeypatch):
    from ayudas_mcp import TOKEN
    falso = _mnemo_que_habla()
    b = banco()
    b.cliente = mc.ClienteMnemo(URL, TOKEN, transporte=falso.transporte())
    r0 = _plan(b.db, 0)
    r = b.hablar({"rid": r0["id"], "n": 3, "frase": 0})
    assert r.status_code == 200, r.text
    ev = eventos(r.text)
    assert ev[0]["formato"] == "pcm_s16le" and audio_de(ev) == AUDIO and ev[-1]["ms_mnemo"] == 512
    ((nombre, args),) = [x for x in falso.llamadas if x[0] == "mnemo_speak"]
    assert args == {"voice_id": VOZ_ID, "text": "Y esta es su ficha.", "format": "pcm_s16le_24000", "language": "es"}
    # La llamada pidió avance (así llega el audio por partes) y los avisos fueron el `start` y los tres trozos
    pedida = next(p for p in falso.peticiones if (p["json"] or {}).get("method") == "tools/call")
    assert pedida["json"]["params"]["_meta"]["progressToken"]
    assert [json.loads(a["message"])["type"] for a in falso.avisos] == ["start", "audio", "audio", "audio"]
    # Y las voces
    r = b.http.get("/api/agente/voces", headers={"x-uid": "0"})
    assert r.status_code == 200 and r.json()["voces"] == [{"id": VOZ_ID, "nombre": "Ana (voz de prueba)",
                                                           "idioma": "es", "motor": "minimax"}]
    # Un Mnemo que todavía no tiene la herramienta: 409 `sin_voz`, y se recuerda
    from ayudas_mcp import MnemoFalso
    b.cliente = mc.ClienteMnemo(URL, TOKEN, transporte=MnemoFalso().transporte())
    r = b.hablar({"prueba": True})
    assert r.status_code == 409 and _detalle(r)["codigo"] == "sin_voz"
    assert "todavía no ofrece sus voces" in _detalle(r)["mensaje"]
    assert voz.puede(b.app, CONECTADA, politica.ajustes_voz({"agente_voz": VOZ}), HUELLA) is False


# ───────────────────────────── Las voces de la cuenta (Ajustes) ─────────────────────────────

def test_las_voces_para_elegir(banco):
    b = banco()
    b.cliente.voces += [{"voice_id": "6740aa0b1c2d3e4f5a6b7c8f", "name": "Clonando", "status": "cloning"},
                        {"voice_id": "no vale con espacios", "name": "Rara", "status": "ready"},
                        {"voice_id": VOZ_ID, "name": "Repetida", "status": "ready"},
                        {"voice_id": "6740aa0b1c2d3e4f5a6b7c90", "name": "\x07con control", "language": "??",
                         "engine": "<b>", "status": "ready"}, "no es un objeto"]
    r = b.http.get("/api/agente/voces", headers={"x-uid": "0"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d == {"voces": [
        {"id": VOZ_ID, "nombre": "Ana (voz de prueba)", "idioma": "es", "motor": "minimax"},
        {"id": OTRA_VOZ, "nombre": "Beto Inventado", "idioma": "es-CO", "motor": "qwen3"},
        {"id": "6740aa0b1c2d3e4f5a6b7c90", "nombre": "Voz sin nombre", "idioma": "es", "motor": ""}],
        "elegida": {"id": VOZ_ID, "nombre": "Ana (voz de prueba)", "idioma": "es", "motor": "minimax"},
        "automatica": {"id": VOZ_ID, "nombre": "Ana (voz de prueba)", "idioma": "es", "motor": "minimax"},
        "conexion": {"voz": True, "ofrece_voz": True}}
    assert [n for n, *_ in b.cliente.llamadas] == ["mnemo_list_voices"]
    # La elegida con otra cuenta de Mnemo no es la elegida
    b.huella = "fedcba9876543210fedcba9876543210"
    assert b.http.get("/api/agente/voces").json()["elegida"] is None
    # Solo el administrador (la voz es de su cuenta)
    for uid in (5, 8, 9):
        assert b.http.get("/api/agente/voces", headers={"x-uid": str(uid)}).status_code == 403


def test_sin_el_permiso_de_la_voz_no_se_le_pregunta_a_mnemo(banco):
    for conexion, info in (({**CONECTADA, "estado": "sin_conectar", "voz": False, "ofrece_voz": None},
                            {"voz": False, "ofrece_voz": True}),
                           ({**CONECTADA, "voz": False}, {"voz": False, "ofrece_voz": True}),
                           ({**CONECTADA, "voz": False, "ofrece_voz": False}, {"voz": False, "ofrece_voz": False})):
        b = banco(conexion=conexion)
        assert b.http.get("/api/agente/voces").json() == {"voces": [], "elegida": None, "automatica": None,
                                                          "conexion": info}
        assert b.cliente.llamadas == []


@pytest.mark.parametrize("error, estado, codigo", [
    (_mnemo("PLAN_REQUIRED", {"feature": "voices"}), 409, "sin_voz"),
    (_mnemo("CREDITS_EXHAUSTED"), 402, "mnemo_creditos"), (_mnemo("INTERNAL"), 502, "mnemo"),
    (ErrorHerramienta("red", mc.COD_RED), 502, "mnemo_red")])
def test_los_errores_al_listar(banco, error, estado, codigo):
    b = banco()
    b.cliente.fallo = error
    r = b.http.get("/api/agente/voces")
    assert r.status_code == estado and _detalle(r)["codigo"] == codigo and "secret" not in r.text
    b.cliente.fallo, b.cliente.salida_voces = None, {"nada": []}
    r = b.http.get("/api/agente/voces")
    assert r.status_code == 502 and _detalle(r)["codigo"] == "mnemo"


def test_listar_la_voz_elegida_olvida_el_no_de_mnemo(banco):
    b = banco()
    av = politica.ajustes_voz({"agente_voz": VOZ})
    b.cliente.fallo = _mnemo("NO_VOICE", {"reason": "not_shared"})
    assert b.hablar({"prueba": True}).status_code == 409 and not voz.puede(b.app, CONECTADA, av, HUELLA)
    b.cliente.fallo = None   # la persona la volvió a marcar «Disponible para apps conectadas» en Mnemo
    assert b.http.get("/api/agente/voces").json()["elegida"]["id"] == VOZ_ID
    assert voz.puede(b.app, CONECTADA, av, HUELLA)


# ───────────────────────────── La voz automática (sin una elegida) ─────────────────────────────

def test_la_voz_automatica_es_la_que_mnemo_ofrece_a_las_apps(banco):
    b = banco(ajustes_voz=AUTO, huella="fedcba9876543210fedcba9876543210")   # (la huella no cuenta: la da Mnemo)
    b.cliente.salida_voces = {"voices": b.cliente.voces, "default_voice_id": OTRA_VOZ}
    r0 = _plan(b.db, 0)
    r = b.hablar({"rid": r0["id"], "n": 1, "frase": 0})
    assert r.status_code == 200, r.text
    ev = eventos(r.text)
    assert ev[0]["voz"] == "Beto Inventado" and audio_de(ev) == AUDIO and ev[-1]["tipo"] == "fin"
    assert [a["voice_id"] for a in b.cliente.hablas()] == [OTRA_VOZ]
    # Se recuerda cuál es: la frase siguiente (y la prueba) no vuelven a preguntar
    assert b.hablar({"rid": r0["id"], "cierre": True}).status_code == 200
    assert b.hablar({"prueba": True}).status_code == 200
    assert [n for n, *_ in b.cliente.llamadas] == ["mnemo_list_voices", "mnemo_speak", "mnemo_speak", "mnemo_speak"]
    av = politica.ajustes_voz({"agente_voz": AUTO})
    assert voz.estado_de(b.app, None, QUIENES[0], {"agente_voz": av}, CONECTADA)["nombre"] == "Beto Inventado"
    # Sin `default_voice_id` entre las listas, la primera
    b = banco(ajustes_voz=AUTO)
    b.cliente.salida_voces = {"voices": b.cliente.voces, "default_voice_id": "6740aa0b1c2d3e4f5a6b7c99"}
    assert b.hablar({"prueba": True}).status_code == 200 and b.cliente.hablas()[0]["voice_id"] == VOZ_ID


def test_sin_voces_para_las_apps_es_409_y_se_vuelve_a_preguntar(banco, monkeypatch):
    b = banco(ajustes_voz=AUTO)
    b.cliente.voces = [{"voice_id": VOZ_ID, "name": "Clonando", "status": "cloning"}]
    av = politica.ajustes_voz({"agente_voz": AUTO})
    assert voz.puede(b.app, CONECTADA, av, None) is True   # no se sabe todavía
    r = b.hablar({"prueba": True})
    assert r.status_code == 409 and _detalle(r) == {"codigo": "sin_voz", "mensaje": voz.MENSAJE_SIN_VOCES}
    assert b.cliente.hablas() == [] and voz.puede(b.app, CONECTADA, av, None) is False
    # Mientras dure lo que se sabe, ni se le pregunta
    assert b.hablar({"prueba": True}).status_code == 409 and len(b.cliente.llamadas) == 1
    # Pasado `AUTO_S`, se vuelve a preguntar: la persona ya marcó una para las apps
    b.cliente.voces = ClienteFalso().voces
    ahora = voz.time.monotonic()
    monkeypatch.setattr(voz.time, "monotonic", lambda: ahora + voz.AUTO_S + 1)
    assert voz.puede(b.app, CONECTADA, av, None) is True
    assert b.hablar({"prueba": True}).status_code == 200 and b.cliente.hablas()[0]["voice_id"] == VOZ_ID
    assert not voz._en_curso and not voz._hablando


def test_ajustes_ve_la_automatica_y_listarla_la_pone(banco):
    b = banco(ajustes_voz=AUTO)
    b.cliente.voces = []
    assert b.hablar({"prueba": True}).status_code == 409
    av = politica.ajustes_voz({"agente_voz": AUTO})
    assert voz.puede(b.app, CONECTADA, av, None) is False
    # La persona la marcó para las apps y el administrador abre Ajustes: la lista la trae y vale sin esperar
    b.cliente.voces = ClienteFalso().voces
    d = b.http.get("/api/agente/voces").json()
    assert d["elegida"] is None and d["automatica"]["id"] == VOZ_ID
    assert voz.puede(b.app, CONECTADA, av, None) is True
    antes = len(b.cliente.llamadas)
    assert b.hablar({"prueba": True}).status_code == 200
    assert [n for n, *_ in b.cliente.llamadas[antes:]] == ["mnemo_speak"]


def test_los_fallos_de_mnemo_con_la_voz_automatica(banco, monkeypatch):
    av = politica.ajustes_voz({"agente_voz": AUTO})
    # Esa voz dejó de estar para las apps (`NO_VOICE`): no se recuerda una hora, se anota que no hay automática por
    # `AUTO_S` y después se pregunta otra vez cuál es
    b = banco(ajustes_voz=AUTO)
    r0 = _plan(b.db, 0)
    assert b.hablar({"prueba": True}).status_code == 200 and len(voz.cache_de(b.app)) == 1
    b.cliente.fallo = _mnemo("NO_VOICE", {"reason": "not_shared"})
    r = b.hablar({"rid": r0["id"], "n": 1, "frase": 0})   # (otra frase: la prueba saldría de la caché)
    assert r.status_code == 409 and _detalle(r)["codigo"] == "sin_voz"
    # La caché de esa voz se vacía (también la prueba, que se dijo antes con ella)
    assert voz.puede(b.app, CONECTADA, av, None) is False and len(voz.cache_de(b.app)) == 0
    assert not voz._recordado(b.app, CONECTADA, voz.AUTOMATICA)
    b.cliente.fallo = None
    ahora = voz.time.monotonic()
    monkeypatch.setattr(voz.time, "monotonic", lambda: ahora + voz.AUTO_S + 1)
    assert voz.puede(b.app, CONECTADA, av, None) is True
    monkeypatch.undo()
    # El plan, o un Mnemo sin la herramienta: se recuerda una hora para la automática (no para una voz elegida)
    for fallo in (_mnemo("PLAN_REQUIRED", {"feature": "voices"}),
                  ErrorHerramienta("Tool mnemo_list_voices not found", mc.COD_NO_DISPONIBLE)):
        b = banco(ajustes_voz=AUTO)
        b.cliente.fallo = fallo
        r = b.hablar({"prueba": True})
        assert r.status_code == 409 and _detalle(r)["codigo"] == "sin_voz"
        assert [n for n, *_ in b.cliente.llamadas] == ["mnemo_list_voices"]
        assert voz.puede(b.app, CONECTADA, av, None) is False
        assert voz.puede(b.app, CONECTADA, politica.ajustes_voz({"agente_voz": VOZ}), HUELLA) is True
        # Un acierto lo olvida
        b.cliente.fallo = None
        assert b.hablar({"prueba": True}).status_code == 200 and voz.puede(b.app, CONECTADA, av, None) is True
    # Si se acaban los créditos a mitad, la automática sigue siendo la misma
    b = banco(ajustes_voz=AUTO)
    assert b.hablar({"prueba": True}).status_code == 200
    b.cliente.fallo, b.cliente.fallo_tras = _mnemo("CREDITS_EXHAUSTED"), 0
    voz.cache_de(b.app).vaciar()
    r = b.hablar({"prueba": True})
    assert eventos(r.text)[-1]["codigo"] == "mnemo_creditos" and voz.puede(b.app, CONECTADA, av, None) is True
    assert voz._auto(b.app, CONECTADA)[0] == VOZ_ID


def _conocer(b: "Banco", av: dict = AUTO, conexion: dict = CONECTADA, plazo: float = voz.PLAZO_CONOCER_S):
    asyncio.run(voz.conocer_automatica(b.app, conexion, politica.ajustes_voz({"agente_voz": av}), plazo))


def test_el_estado_pregunta_cual_es_la_automatica_antes_de_ofrecerla(banco, monkeypatch):
    monkeypatch.setattr(voz.mc, "cliente_de", lambda app: b.cliente)
    av = politica.ajustes_voz({"agente_voz": AUTO})

    def estado():
        return voz.estado_de(b.app, None, QUIENES[0], {"agente_voz": av}, CONECTADA)
    # Sin voces para las apps: el estado ya no la ofrece (antes de que se pida ninguna frase)
    b = banco(ajustes_voz=AUTO)
    b.cliente.voces = []
    assert voz.hay_que_conocer(b.app, CONECTADA, av) is True
    _conocer(b)
    assert estado()["disponible"] is False and [n for n, *_ in b.cliente.llamadas] == ["mnemo_list_voices"]
    assert voz.hay_que_conocer(b.app, CONECTADA, av) is False   # ya se sabe: no se vuelve a preguntar
    _conocer(b)
    assert len(b.cliente.llamadas) == 1
    # Con una: se ofrece, con su nombre
    b = banco(ajustes_voz=AUTO)
    _conocer(b)
    assert estado() == {"disponible": True, "nombre": "Ana (voz de prueba)", "respuestas": True, "automatica": True}
    # Ni con una voz elegida, ni con la del navegador, ni sin `mnemo:voice` se le pregunta nada
    for otra, conexion in ((VOZ, CONECTADA), ({**AUTO, "motor": "navegador"}, CONECTADA),
                           (AUTO, {**CONECTADA, "voz": False})):
        b = banco(ajustes_voz=AUTO)
        _conocer(b, otra, conexion)
        assert b.cliente.llamadas == [], otra
    # Si Mnemo no responde, se ofrece sin saberlo (como antes) y no se le vuelve a esperar hasta `REINTENTO_S`
    b = banco(ajustes_voz=AUTO)
    b.cliente.fallo = ErrorHerramienta("red", mc.COD_RED)
    _conocer(b)
    assert estado()["disponible"] is True and voz.hay_que_conocer(b.app, CONECTADA, av) is False
    _conocer(b)
    assert len(b.cliente.llamadas) == 1
    ahora = voz.time.monotonic()
    monkeypatch.setattr(voz.time, "monotonic", lambda: ahora + voz.REINTENTO_S + 1)
    assert voz.hay_que_conocer(b.app, CONECTADA, av) is True
    monkeypatch.undo()
    # Si dice que no puede (el plan), se recuerda: el estado no la ofrece
    monkeypatch.setattr(voz.mc, "cliente_de", lambda app: b.cliente)
    b = banco(ajustes_voz=AUTO)
    b.cliente.fallo = _mnemo("PLAN_REQUIRED", {"feature": "voices"})
    _conocer(b)
    assert estado()["disponible"] is False


def test_el_estado_no_espera_a_mnemo_mas_que_su_plazo(banco, monkeypatch):
    b = banco(ajustes_voz=AUTO)
    monkeypatch.setattr(voz.mc, "cliente_de", lambda app: b.cliente)

    async def lenta(*a, **kw):
        await asyncio.sleep(30)
    b.cliente.llamar = lenta
    t0 = voz.time.monotonic()
    _conocer(b, plazo=0.05)
    assert voz.time.monotonic() - t0 < 3
    assert voz._intentada(b.app, CONECTADA) and voz.hay_que_conocer(
        b.app, CONECTADA, politica.ajustes_voz({"agente_voz": AUTO})) is False


def test_la_ruta_del_estado_pregunta_por_la_automatica(banco, monkeypatch):
    # `api/agente._voz` corre en un hilo del servidor (la ruta no es asíncrona) y le pregunta a Mnemo por el bucle
    b = banco(ajustes_voz=AUTO)
    b.cliente.voces = []
    monkeypatch.setattr(voz.mc, "cliente_de", lambda app: b.cliente)
    monkeypatch.setattr(voz.mnemo_conexion, "huella_cuenta", lambda db: HUELLA)
    ajustes = {"agente_voz": politica.ajustes_voz({"agente_voz": AUTO})}

    async def en_un_hilo():
        from fastapi.concurrency import run_in_threadpool
        return await run_in_threadpool(agente_api._voz, b.app, None, QUIENES[0], ajustes, dict(CONECTADA))
    assert asyncio.run(en_un_hilo()) == agente_api.SIN_VOZ
    assert [n for n, *_ in b.cliente.llamadas] == ["mnemo_list_voices"]
    # Un rol que no la hace sonar no hace preguntar nada
    b = banco(ajustes_voz=AUTO)

    async def otro():
        from fastapi.concurrency import run_in_threadpool
        return await run_in_threadpool(agente_api._voz, b.app, None, QUIENES[8], ajustes, dict(CONECTADA))
    assert asyncio.run(otro()) == agente_api.SIN_VOZ and b.cliente.llamadas == []


def test_con_la_automatica_los_topes_van_antes_de_preguntarle_a_mnemo(banco, monkeypatch):
    b = banco(ajustes_voz=AUTO)
    b.cliente.fallo = ErrorHerramienta("red", mc.COD_RED)   # la lista no responde: no se recuerda nada
    monkeypatch.setattr(voz, "FRECUENCIA_MAX", 2)
    codigos = [b.hablar({"prueba": True}).status_code for _ in range(5)]
    assert codigos == [502, 502, 429, 429, 429]
    assert [n for n, *_ in b.cliente.llamadas] == ["mnemo_list_voices", "mnemo_list_voices"]
    assert not voz._en_curso and not voz._hablando


def test_la_cache_es_de_la_voz_automatica_de_ahora(banco, monkeypatch):
    b = banco(ajustes_voz=AUTO)
    r0 = _plan(b.db, 0)
    c1 = {"rid": r0["id"], "n": 1, "frase": 0}
    assert b.hablar(c1).status_code == 200
    assert eventos(b.hablar(c1).text)[0]["cache"] is True and len(b.cliente.hablas()) == 1
    # Pasado `AUTO_S`, Mnemo ofrece otra (la persona marcó una más reciente): la caché de la anterior no se sirve
    b.cliente.salida_voces = {"voices": b.cliente.voces, "default_voice_id": OTRA_VOZ}
    ahora = voz.time.monotonic()
    monkeypatch.setattr(voz.time, "monotonic", lambda: ahora + voz.AUTO_S + 1)
    ev = eventos(b.hablar(c1).text)
    assert ev[0]["cache"] is False and ev[0]["voz"] == "Beto Inventado"
    assert [a["voice_id"] for a in b.cliente.hablas()] == [VOZ_ID, OTRA_VOZ]


# ───────────────────────────── `voz` en el estado ─────────────────────────────

def test_el_estado_de_la_voz(monkeypatch):
    app = SimpleNamespace(state=SimpleNamespace())
    monkeypatch.setattr(mnemo_conexion, "huella_cuenta", lambda db: HUELLA)

    def estado(uid=0, av=VOZ, conexion=CONECTADA):
        return voz.estado_de(app, None, QUIENES[uid], {"agente_voz": politica.ajustes_voz({"agente_voz": av})},
                             conexion)
    assert estado() == {"disponible": True, "nombre": "Ana (voz de prueba)", "respuestas": True, "automatica": True}
    assert estado(5) == estado()
    nada = {"disponible": False, "nombre": None, "respuestas": False, "automatica": False}
    assert estado(8) == nada   # su rol no la hace sonar
    assert estado(av={**VOZ, "motor": "navegador"}) == nada
    assert estado(av={**AUTO, "motor": "navegador"}) == nada
    # Sin una voz elegida, la automática: mientras no se sabe cuál es, se ofrece (la ruta le pregunta a Mnemo); de
    # otra cuenta no hay nada que mirar (la da Mnemo con la conexión de ahora); sin `mnemo:voice` o sin su rol, no
    assert estado(av=AUTO) == {"disponible": True, "nombre": None, "respuestas": True, "automatica": True}
    assert estado(av={**AUTO, "cuenta": "fedcba9876543210fedcba9876543210"}) == estado(av=AUTO)
    assert estado(av=AUTO, conexion={**CONECTADA, "voz": False}) == nada and estado(8, av=AUTO) == nada
    voz._anotar_auto(app, CONECTADA, {"id": OTRA_VOZ, "nombre": "Beto Inventado"})
    assert estado(av=AUTO) == {"disponible": True, "nombre": "Beto Inventado", "respuestas": True, "automatica": True}
    voz._anotar_auto(app, CONECTADA, None)   # Mnemo dijo que no ofrece ninguna a las apps
    assert estado(av=AUTO) == nada and estado() != nada
    assert estado(conexion={**CONECTADA, "voz": False}) == nada
    assert estado(conexion={**CONECTADA, "estado": "caida", "motivo": "clave"}) == nada
    assert estado(av={**VOZ, "cuenta": "fedcba9876543210fedcba9876543210"}) == nada
    assert estado(av={**VOZ, "respuestas": False}) == {**estado(), "respuestas": False}
    assert estado(av={**VOZ, "automatica": False, "nombre": ""}) == {**estado(), "automatica": False, "nombre": None}
    # Lo que diga `api/agente.py` nunca falla por esto
    monkeypatch.setattr(voz, "estado_de", lambda *a: 1 / 0)
    assert agente_api._voz(app, None, QUIENES[0], {}, CONECTADA) == agente_api.SIN_VOZ


# ───────────────────────────── Los cupos del servidor ─────────────────────────────

def _app_lenta(segundos):
    async def app(scope, receive, send):
        await asyncio.sleep(segundos)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})
    return app


def test_la_voz_tiene_cupos_propios_en_el_servidor():
    import servidor
    assert servidor.CUPOS_VOZ == 6 and servidor.RUTAS_VOZ == {"/api/agente/voz"}
    assert not servidor.RUTAS_VOZ & servidor.RUTAS_AGENTE
    from app.main import RUTAS_EN_FLUJO
    assert servidor.RUTAS_VOZ <= RUTAS_EN_FLUJO   # sin gzip: cada trozo suena en cuanto llega

    async def probar():
        limite = servidor.LimitePanel(_app_lenta(0.4), cupos=1, espera_s=0.15, cupos_agente=1, cupos_voz=2,
                                      limite=1024)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=limite), base_url="http://t") as c:
            rs = await asyncio.gather(*(c.post("/api/agente/voz", json={"prueba": True}) for _ in range(3)),
                                      c.post("/api/agente/mensajes", json={"texto": "hola"}), c.get("/api/x"))
            voces = sorted(r.status_code for r in rs[:3])
            assert voces == [200, 200, 503]   # dos frases a la vez; la tercera, sin cupo
            assert [r.status_code for r in rs[3:]] == [200, 200]   # ni el chat ni la API esperan por la voz
            # Un cuerpo de más del tope ni toma cupo
            r = await c.post("/api/agente/voz", content=b"x" * 2048, headers={"content-type": "application/json"})
            assert r.status_code == 413
    asyncio.run(probar())


# ───────────────────────────── El ajuste `agente_voz` (con MongoDB) ─────────────────────────────

POR_DEFECTO = {"motor": "mnemo", "voz": "", "nombre": "", "cuenta": "", "roles": ["admin", "coordinador"],
               "respuestas": True, "automatica": True}


def test_el_ajuste_por_defecto_y_sus_reglas(sesion):
    from app import modelo
    from app.api import ajustes as api_ajustes
    assert modelo.AJUSTES_POR_DEFECTO["agente_voz"] == POR_DEFECTO == politica.VOZ_POR_DEFECTO
    assert POR_DEFECTO["roles"] == sorted(POR_DEFECTO["roles"])   # como lo deja la validación
    # La validación acepta exactamente sus claves, con las mismas reglas con que se lee lo guardado
    assert set(api_ajustes.VozAgente.model_fields) == set(POR_DEFECTO)
    assert api_ajustes.MOTORES_VOZ == politica.MOTORES_VOZ and api_ajustes.MAX_NOMBRE_VOZ == politica.MAX_NOMBRE_VOZ
    assert "agente_voz" in acceso.AJUSTES_DE_PERMISOS   # solo el administrador lo cambia
    v = sesion.get("/api/ajustes").json()
    assert v["agente_voz"] == POR_DEFECTO and "agente_voz" in v["ajustes_de_permisos"]
    assert politica.leer(sesion.app.state.db)[0]["agente_voz"] == POR_DEFECTO


def test_elegir_la_voz_guarda_la_cuenta_conectada(sesion):
    from ayudas_agente import ALCANCES_PANEL, conectar_mnemo
    db = sesion.app.state.db
    # Sin conexión, la voz se guarda sin cuenta (no sonará hasta elegirla con una conexión)
    r = sesion.put("/api/ajustes", json={"agente_voz": {"motor": "mnemo", "voz": VOZ_ID, "nombre": "Ana",
                                                        "cuenta": HUELLA}})   # la cuenta del formulario no cuenta
    assert r.status_code == 200, r.text
    assert r.json()["agente_voz"] == {**POR_DEFECTO, "motor": "mnemo", "voz": VOZ_ID, "nombre": "Ana", "cuenta": ""}
    conectar_mnemo(sesion.app, alcances=(*ALCANCES_PANEL, "mnemo:voice"))
    huella = mnemo_conexion.huella_cuenta(db)
    sesion.put("/api/ajustes", json={"agente_voz": {"voz": OTRA_VOZ, "nombre": "  Beto   Inventado "}})
    av = sesion.get("/api/ajustes").json()["agente_voz"]
    assert av == {**POR_DEFECTO, "motor": "mnemo", "voz": OTRA_VOZ, "nombre": "Beto Inventado", "cuenta": huella}
    # Cambiar otra cosa no cambia la cuenta; otra voz sin su nombre no se queda con el de la anterior
    sesion.put("/api/ajustes", json={"agente_voz": {"respuestas": False, "roles": ["coordinador", "admin",
                                                                                   "admin"]}})
    av = sesion.get("/api/ajustes").json()["agente_voz"]
    assert av["cuenta"] == huella and av["respuestas"] is False and av["roles"] == ["admin", "coordinador"]
    sesion.put("/api/ajustes", json={"agente_voz": {"voz": VOZ_ID}})
    assert sesion.get("/api/ajustes").json()["agente_voz"]["nombre"] == ""
    # Sin voz, ni nombre ni cuenta
    sesion.put("/api/ajustes", json={"agente_voz": {"voz": "", "nombre": "Queda"}})
    av = sesion.get("/api/ajustes").json()["agente_voz"]
    assert (av["voz"], av["nombre"], av["cuenta"]) == ("", "", "")
    a = db.auditoria.find_one({"accion": "ajustes"}, sort=[("_id", -1)])
    assert "agente_voz" in a["detalle"] and VOZ_ID not in a["detalle"]


@pytest.mark.parametrize("valor", [
    {"motor": "elevenlabs"}, {"motor": None, "voz": "con espacios"}, {"voz": "x" * 101}, {"respuestas": "true"},
    {"automatica": 1}, {"roles": ["jefe"]}, {"roles": "admin"}, {"nombre": "dos\nrenglones"},
    {"nombre": "n" * 61}, {"cuenta": "x" * 65}, {"otra": True}, "mnemo", ["mnemo"]])
def test_el_ajuste_es_estricto(sesion, valor):
    r = sesion.put("/api/ajustes", json={"agente_voz": valor})
    assert r.status_code == 422, (valor, r.text)
    assert sesion.get("/api/ajustes").json()["agente_voz"] == POR_DEFECTO


def test_el_coordinador_lo_ve_y_no_lo_cambia(sesion):
    from ayudas_g3 import coordinador
    k = coordinador(sesion.app, sesion.app.state.db)
    try:
        a = k.get("/api/ajustes").json()
        assert a["agente_voz"] == POR_DEFECTO
        r = k.put("/api/ajustes", json={"agente_voz": {"motor": "navegador"}})
        assert r.status_code == 403 and r.json()["detail"]["codigo"] == "permiso"
        assert r.json()["detail"]["campos"] == ["agente_voz"]
        # Reenviar lo que ve no es un cambio
        assert k.put("/api/ajustes", json={"agente_voz": a["agente_voz"]}).status_code == 200
        # Ni las voces de la cuenta del administrador
        assert k.get("/api/agente/voces").status_code == 403
    finally:
        k.close()


def test_lo_guardado_a_mano_se_lee_con_las_reglas():
    raro = {"agente_voz": {"motor": "otro", "voz": "no vale!", "nombre": "x", "cuenta": "zz", "roles": ["jefe", "admin",
                                                                                                     5],
                           "respuestas": "si", "automatica": None}}
    assert politica.ajustes_voz(raro) == {**POR_DEFECTO, "roles": ["admin"]}
    assert politica.ajustes_voz({"agente_voz": "mnemo"}) == POR_DEFECTO == politica.ajustes_voz(None)
    bien = {"agente_voz": {**VOZ, "nombre": "  Ana  (voz) "}}
    assert politica.ajustes_voz(bien) == {**VOZ, "nombre": "Ana (voz)"}
    # Un nombre con caracteres de control no se muestra; sin voz no hay nombre ni cuenta
    assert politica.ajustes_voz({"agente_voz": {**VOZ, "nombre": "Ana\x1b[31m"}})["nombre"] == ""
    assert politica.ajustes_voz({"agente_voz": {**VOZ, "voz": ""}})[("nombre")] == ""
    assert politica.ajustes_voz({"agente_voz": {**VOZ, "voz": ""}})["cuenta"] == ""
    # Una copia nueva cada vez
    a = politica.ajustes_voz(None)
    a["roles"].append("planillero")
    assert politica.ajustes_voz(None)["roles"] == ["admin", "coordinador"]


def test_el_estado_dice_si_la_voz_esta_disponible(sesion, monkeypatch):
    from ayudas_agente import ALCANCES_PANEL, conectar_mnemo
    nada = {"disponible": False, "nombre": None, "respuestas": False, "automatica": False}
    assert sesion.get("/api/agente/estado").json()["voz"] == nada
    falso = conectar_mnemo(sesion.app, alcances=(*ALCANCES_PANEL, "mnemo:voice"))
    # Sin tocar Ajustes: la voz automática. El estado le pregunta a Mnemo cuál es antes de ofrecerla: este Mnemo falso
    # todavía no tiene las herramientas de la voz, así que no la ofrece (y lo recuerda)
    assert sesion.get("/api/agente/estado").json()["voz"] == nada
    pedidas = [(p["json"] or {}).get("params", {}).get("name") for p in falso.mcp.peticiones
               if (p["json"] or {}).get("method") == "tools/call"]
    assert pedidas == ["mnemo_list_voices"], pedidas
    # Mnemo se actualiza y, pasada la hora del «no», la ofrece con su nombre
    habla = _mnemo_que_habla()
    falso.mcp.herramientas += [h for h in habla.herramientas if h["name"] in ("mnemo_speak", "mnemo_list_voices")]
    falso.mcp.manejadores.update({k: habla.manejadores[k] for k in ("mnemo_speak", "mnemo_list_voices")})
    ahora = voz.time.monotonic()
    monkeypatch.setattr(voz.time, "monotonic", lambda: ahora + voz.OLVIDO_S + 1)
    assert sesion.get("/api/agente/estado").json()["voz"] == {"disponible": True, "nombre": "Ana (voz de prueba)",
                                                              "respuestas": True, "automatica": True}
    monkeypatch.undo()
    r = sesion.put("/api/ajustes", json={"agente_voz": {"motor": "mnemo", "voz": VOZ_ID, "nombre": "Ana",
                                                        "automatica": False}})
    assert r.status_code == 200
    assert sesion.get("/api/agente/estado").json()["voz"] == {"disponible": True, "nombre": "Ana",
                                                              "respuestas": True, "automatica": False}
    # Con otra cuenta de Mnemo conectada, la voz elegida ya no vale
    from ayudas_mcp import OTRA_CUENTA
    conectar_mnemo(sesion.app, alcances=(*ALCANCES_PANEL, "mnemo:voice"), cuenta=OTRA_CUENTA)
    assert sesion.get("/api/agente/estado").json()["voz"] == nada
    # Y sin `mnemo:voice`, tampoco
    conectar_mnemo(sesion.app)
    sesion.put("/api/ajustes", json={"agente_voz": {"voz": OTRA_VOZ, "nombre": "Beto"}})
    assert sesion.get("/api/agente/estado").json()["voz"] == nada
