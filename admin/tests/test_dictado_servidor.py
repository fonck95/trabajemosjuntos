"""Preguntas por voz, lo del servidor (app/agente/dictado.py y `POST /api/agente/transcribir` de app/api/agente.py):
los topes que acotan el costo y la concurrencia (una pregunta a la vez por persona, dos llamadas a Mnemo a la vez en el
panel, un tope diario y nada con los mensajes del día agotados), la subida que se corta a mitad, que se estanca o que
va demasiado lenta (con plazo, y sin ocupar el cupo de Mnemo), la persona que se va mientras se transcribe (se deja de
esperar a Mnemo y su turno queda libre) y las herramientas guardadas de una conversación (`mnemo_transcribe` nunca es
una herramienta del modelo).

Sin MongoDB ni Mnemo: la ruta de verdad en una aplicación mínima, con la persona fija (por la cabecera `x-uid`), los
ajustes del asistente fijos y un cliente de Mnemo falso (`dictado._preparar`). Solo datos inventados."""
import asyncio
import logging
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import acceso
from app.agente import dictado, politica, proveedores
from app.agente.herramientas import mnemo
from app.api import agente as agente_api

AUDIO = b"\x1aE\xdf\xa3" + bytes(range(256)) * 4   # no es un audio de verdad: nadie lo decodifica aquí
PREGUNTA = "¿Qué obras de salud trae la propuesta?"
CONECTADA = {"estado": "conectada", "motivo": None, "url": "https://mnemo.example.org/mcp", "cuenta": None,
             "alcances": ["mnemo:read", "mnemo:model"], "modelo": True, "ofrece_modelo": True,
             "desde": "2026-11-01T10:00:00+00:00"}
QUIENES = {uid: acceso.Quien(uid=uid, usuario=f"p{uid}", rol=rol, permisos=acceso.PERMISOS[rol])
           for uid, rol in ((0, "admin"), (5, "coordinador"), (6, "coordinador"))}


class ClienteFalso:
    """El cliente de Mnemo: cuenta las llamadas (y las que se cancelaron a mitad) y, con `espera`, no responde hasta
    que se suelte."""

    def __init__(self):
        self.llamadas: list[str] = []
        self.canceladas = 0
        self.espera: asyncio.Event | None = None

    async def llamar(self, nombre, argumentos, plazo):
        self.llamadas.append(nombre)
        if self.espera is not None:
            try:
                await self.espera.wait()
            except asyncio.CancelledError:
                self.canceladas += 1
                raise
        return {"structuredContent": {"text": PREGUNTA}}


class Banco:
    def __init__(self, monkeypatch, *, mensajes: dict | None = None):
        self.app = FastAPI()
        self.app.include_router(agente_api.r)
        self.app.state.db = SimpleNamespace(name="prueba_dictado_servidor")
        self.app.state.cfg = SimpleNamespace()
        self.cliente = ClienteFalso()
        ruta = next(r for r in self.app.routes if isinstance(r, APIRoute) and r.path == "/api/agente/transcribir")
        (dep,) = [d.call for d in ruta.dependant.dependencies if hasattr(d.call, "permisos")]

        def quien(request: Request):
            return QUIENES[int(request.headers.get("x-uid", "0"))]
        self.app.dependency_overrides[dep] = quien
        ajustes = {"agente_mensajes_diarios": mensajes} if mensajes else {}
        monkeypatch.setattr(politica, "leer", lambda db: (dict(ajustes), {"roles": ["admin", "coordinador"],
                                                                          "escritura": True}))
        monkeypatch.setattr(proveedores, "clave_para_nueva", lambda cfg, db=None: "mnemo")
        monkeypatch.setattr(dictado, "_preparar", lambda app: (dict(CONECTADA), self.cliente))
        self.usados: dict[int, int] = {}
        monkeypatch.setattr(dictado.conv_db, "uso_de", lambda db, uid: self.usados.get(uid, 0))
        self.http = TestClient(self.app)

    def transcribir(self, uid: int = 0, audio: bytes = AUDIO):
        return self.http.post("/api/agente/transcribir", content=audio,
                              headers={"Content-Type": "audio/webm;codecs=opus", "x-uid": str(uid)})

    async def crudo(self, uid: int, recibir) -> list[dict]:
        """La ruta en ASGI crudo, con `recibir` como el `receive` del servidor web: lo que la aplicación mandó."""
        enviados: list[dict] = []

        async def enviar(m):
            enviados.append(m)
        alcance = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
                   "scheme": "http", "path": "/api/agente/transcribir", "raw_path": b"/api/agente/transcribir",
                   "query_string": b"", "root_path": "", "server": ("panel", 80), "client": ("127.0.0.1", 5000),
                   "headers": [(b"content-type", b"audio/webm"), (b"content-length", str(len(AUDIO)).encode()),
                               (b"x-uid", str(uid).encode())]}
        await self.app(alcance, recibir, enviar)
        return enviados


def _respuesta(enviados: list[dict]) -> tuple[int, dict]:
    """(estado, cuerpo JSON) de lo que mandó la aplicación en ASGI crudo."""
    import json
    cuerpo = b"".join(m.get("body", b"") for m in enviados if m["type"] == "http.response.body")
    return enviados[0]["status"], json.loads(cuerpo)


async def _hasta(condicion, segundos: float = 3.0):
    """Espera (en el mismo bucle) a que se cumpla `condicion()`."""
    for _ in range(int(segundos / 0.01)):
        if condicion():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("no se cumplió a tiempo")


@pytest.fixture
def limpio():
    def vaciar():
        dictado._ventanas.clear()
        dictado._en_curso.clear()
        dictado._transcribiendo.clear()
        dictado._diarias.clear()
    vaciar()
    yield
    vaciar()


# ───────────────────────────── Una a la vez ─────────────────────────────

def test_el_turno_es_uno_por_persona(limpio):
    with dictado.turno("base", 7):
        with pytest.raises(dictado.ErrorDictado) as e:   # la misma persona, otra vez
            with dictado.turno("base", 7):
                pass
        assert e.value.status_code == 429 and e.value.detail == {"codigo": "frecuencia",
                                                                 "mensaje": dictado.MENSAJE_A_LA_VEZ}
        assert e.value.headers["Retry-After"] == str(dictado.ESPERA_TURNO_S)
        # la misma persona en otra base es otra, y las demás personas no esperan por ella (eso es el cupo de Mnemo)
        with dictado.turno("otra", 7), dictado.turno("base", 8), dictado.turno("base", 9):
            assert len(dictado._en_curso) == 4
    assert not dictado._en_curso
    # el sitio se suelta también si lo de adentro falla
    with pytest.raises(RuntimeError):
        with dictado.turno("base", 7):
            raise RuntimeError("falló la transcripción")
    with dictado.turno("base", 7):
        assert dictado._en_curso == {("base", 7)}


def test_el_cupo_dos_llamadas_a_mnemo_en_el_panel(monkeypatch, limpio):
    assert dictado.A_LA_VEZ == 2 and dictado.ESPERA_CUPO_S == 10
    monkeypatch.setattr(dictado, "VIGILA_S", 0.01)

    async def correr():
        suelta = asyncio.Event()

        async def ocupar():
            async with dictado.cupo():
                await suelta.wait()
        ocupadas = [asyncio.create_task(ocupar()) for _ in range(2)]
        await _hasta(lambda: len(dictado._transcribiendo) == 2)
        # La tercera espera (la grabación ya llegó: transcribir tarda segundos) y entra en cuanto se libera uno
        dentro = asyncio.Event()

        async def tercera():
            async with dictado.cupo():
                dentro.set()
        t = asyncio.create_task(tercera())
        await asyncio.sleep(0.1)
        espero = not dentro.is_set()
        suelta.set()
        await asyncio.gather(t, *ocupadas)
        # Sin que se libere ninguno en ESPERA_CUPO_S: 429 `frecuencia` con su mensaje
        monkeypatch.setattr(dictado, "ESPERA_CUPO_S", 0.05)
        suelta.clear()
        ocupadas = [asyncio.create_task(ocupar()) for _ in range(2)]
        await _hasta(lambda: len(dictado._transcribiendo) == 2)
        with pytest.raises(dictado.ErrorDictado) as e:
            async with dictado.cupo():
                pass
        # Cancelado mientras espera, no se lleva nada; cancelado con el cupo tomado, lo suelta
        esperando = asyncio.create_task(tercera())
        await asyncio.sleep(0.02)
        esperando.cancel()
        suelta.set()
        await asyncio.gather(*ocupadas)
        tomado = asyncio.create_task(ocupar())
        suelta.clear()
        await _hasta(lambda: len(dictado._transcribiendo) == 1)
        tomado.cancel()
        await asyncio.gather(tomado, esperando, return_exceptions=True)
        return espero, dentro.is_set(), e.value
    espero, entro, error = asyncio.run(correr())
    assert espero and entro
    assert error.status_code == 429 and error.detail == {"codigo": "frecuencia", "mensaje": dictado.MENSAJE_OCUPADO}
    assert error.headers["Retry-After"] == str(dictado.ESPERA_TURNO_S)
    assert not dictado._transcribiendo


def test_la_ruta_no_deja_mas_de_una_por_persona_ni_mas_de_dos_a_la_vez(monkeypatch, limpio):
    b = Banco(monkeypatch)
    monkeypatch.setattr(dictado, "VIGILA_S", 0.01)

    async def correr():
        b.cliente.espera = asyncio.Event()
        transporte = httpx.ASGITransport(app=b.app)
        async with httpx.AsyncClient(transport=transporte, base_url="http://panel") as http:
            def pedir(uid):
                return http.post("/api/agente/transcribir", content=AUDIO,
                                 headers={"Content-Type": "audio/webm", "x-uid": str(uid)})

            def hasta(n):
                return _hasta(lambda: len(b.cliente.llamadas) >= n)
            primera = asyncio.create_task(pedir(0))
            await hasta(1)
            misma = await pedir(0)          # la misma persona mientras se transcribe la suya
            segunda = asyncio.create_task(pedir(5))
            await hasta(2)
            # ya hay dos en Mnemo: la tercera persona espera (sin llegar a Mnemo) y entra cuando se liberan
            tercera = asyncio.create_task(pedir(6))
            await asyncio.sleep(0.2)
            esperando = (not tercera.done(), len(b.cliente.llamadas), set(dictado._en_curso))
            b.cliente.espera.set()
            hechas = await primera, await segunda, await tercera
            # sin cupo en ESPERA_CUPO_S, 429 (y la persona queda libre para repetirla)
            monkeypatch.setattr(dictado, "ESPERA_CUPO_S", 0.1)
            b.cliente.espera = asyncio.Event()
            ocupan = [asyncio.create_task(pedir(uid)) for uid in (0, 5)]
            await hasta(5)
            sin_cupo = await pedir(6)
            sin_cupo_libre = ("prueba_dictado_servidor", 6) not in dictado._en_curso
            b.cliente.espera.set()
            await asyncio.gather(*ocupan)
            return misma, esperando, hechas, sin_cupo, sin_cupo_libre
    misma, esperando, hechas, sin_cupo, sin_cupo_libre = asyncio.run(correr())
    assert misma.status_code == 429 and misma.json()["detail"] == {"codigo": "frecuencia",
                                                                    "mensaje": dictado.MENSAJE_A_LA_VEZ}
    assert misma.headers["Retry-After"] == str(dictado.ESPERA_TURNO_S)
    # el reintento rechazado no gastó del tope de frecuencia de la persona: solo cuenta la que tenía el turno
    assert len(dictado._ventanas[("prueba_dictado_servidor", 0)]) == 2
    assert esperando == (True, 2, {("prueba_dictado_servidor", u) for u in (0, 5, 6)})
    assert [r.json() for r in hechas] == [{"texto": PREGUNTA, "via": "mnemo"}] * 3
    assert sin_cupo.status_code == 429 and sin_cupo.json()["detail"] == {"codigo": "frecuencia",
                                                                          "mensaje": dictado.MENSAJE_OCUPADO}
    assert sin_cupo.headers["Retry-After"] == str(dictado.ESPERA_TURNO_S) and sin_cupo_libre
    assert len(b.cliente.llamadas) == 5 and not dictado._en_curso and not dictado._transcribiendo
    b.cliente.espera = None
    assert b.transcribir(6).status_code == 200   # terminadas, hay sitio otra vez


# ───────────────────────────── El tope diario ─────────────────────────────

def test_el_tope_diario_es_el_doble_de_los_mensajes_del_dia(monkeypatch, limpio):
    assert dictado.DIARIAS_POR_MENSAJE == 2
    b = Banco(monkeypatch, mensajes={"coordinador": 2})
    for _ in range(4):
        assert b.transcribir(5).status_code == 200
    r = b.transcribir(5)
    assert r.status_code == 429 and r.json()["detail"] == {"codigo": "volumen", "mensaje": dictado.MENSAJE_DIARIAS}
    assert len(b.cliente.llamadas) == 4
    assert b.transcribir(6).status_code == 200   # otra persona no se entera
    # al día siguiente (hora de Colombia) vuelve a poder
    manana = dictado.modelo.hoy_local().replace(year=dictado.modelo.hoy_local().year + 1)
    monkeypatch.setattr(dictado.modelo, "hoy_local", lambda: manana)
    assert b.transcribir(5).status_code == 200


def test_con_los_mensajes_del_dia_agotados_no_transcribe(monkeypatch, limpio, caplog):
    b = Banco(monkeypatch, mensajes={"coordinador": 3})
    b.usados[5] = 3
    r = b.transcribir(5)
    assert r.status_code == 429
    assert r.json()["detail"] == {"codigo": "volumen",
                                  "mensaje": "Llegó al tope de 3 mensajes al asistente por hoy. Podrá seguir mañana."}
    assert b.cliente.llamadas == [] and not dictado._diarias   # ni se leyó el audio ni se contó
    b.usados[5] = 2
    assert b.transcribir(5).status_code == 200
    # Si el uso no se puede leer, no frena (los demás topes siguen) y el registro solo dice el tipo del error

    def roto(db, uid):
        raise RuntimeError("MongoDB no responde: dato privado")
    monkeypatch.setattr(dictado.conv_db, "uso_de", roto)
    with caplog.at_level(logging.WARNING, logger="panel"):
        assert b.transcribir(5).status_code == 200
    registro = "\n".join(m.getMessage() for m in caplog.records)
    assert "RuntimeError" in registro and "dato privado" not in registro


# ───────────────────────────── La subida que se corta ─────────────────────────────

def test_una_subida_cortada_responde_400_sin_traza(monkeypatch, limpio):
    from starlette.requests import ClientDisconnect

    class Cortada:
        headers = {"content-length": "100000"}

        async def stream(self):
            yield b"\0" * 1000
            raise ClientDisconnect()
    with pytest.raises(dictado.ErrorDictado) as e:
        asyncio.run(dictado.leer_audio(Cortada()))
    assert e.value.status_code == 400 and e.value.detail == {"codigo": "cortada", "mensaje": dictado.MENSAJE_CORTADA}
    # La ruta de verdad, en ASGI crudo: llegan 1000 de los 100000 bytes y el cliente se va. La aplicación responde 400
    # (no sale ninguna excepción hacia el servidor, que la registraría con su traza), no llama a Mnemo y suelta el turno
    b = Banco(monkeypatch)
    mensajes = iter([{"type": "http.request", "body": b"\0" * 1000, "more_body": True}, {"type": "http.disconnect"}])
    enviados: list[dict] = []

    async def recibir():
        return next(mensajes, {"type": "http.disconnect"})

    async def enviar(m):
        enviados.append(m)
    alcance = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "scheme": "http",
               "path": "/api/agente/transcribir", "raw_path": b"/api/agente/transcribir", "query_string": b"",
               "root_path": "", "server": ("panel", 80), "client": ("127.0.0.1", 5000),
               "headers": [(b"content-type", b"audio/webm"), (b"content-length", b"100000"), (b"x-uid", b"0")]}
    asyncio.run(b.app(alcance, recibir, enviar))
    assert enviados[0]["type"] == "http.response.start" and enviados[0]["status"] == 400
    assert b.cliente.llamadas == [] and not dictado._en_curso


class Estancada:
    """Un cuerpo que llega a medias y se queda: el celular perdió la señal sin cerrar la conexión."""
    headers = {"content-length": "100000"}

    def __init__(self, cada: float | None = None):
        self.cada = cada   # con `cada`, llega a gotas (un trozo cada tantos segundos) y nunca termina

    async def stream(self):
        yield b"\0" * 1000
        while self.cada is not None:
            await asyncio.sleep(self.cada)
            yield b"\0" * 10
        await asyncio.Event().wait()


def test_una_subida_estancada_o_lenta_tiene_plazo(monkeypatch, limpio):
    assert (dictado.PLAZO_SUBIDA_S, dictado.SUBIDA_CALLADA_S) == (30, 10)
    # Sin que llegue nada en SUBIDA_CALLADA_S, o sin terminar en PLAZO_SUBIDA_S aunque siga llegando a gotas: 400
    # `lenta` (el servidor web espera para siempre un cuerpo que deja de llegar)
    monkeypatch.setattr(dictado, "SUBIDA_CALLADA_S", 0.1)
    monkeypatch.setattr(dictado, "PLAZO_SUBIDA_S", 0.4)
    for cuerpo in (Estancada(), Estancada(cada=0.05)):
        with pytest.raises(dictado.ErrorDictado) as e:
            asyncio.run(dictado.leer_audio(cuerpo))
        assert e.value.status_code == 400 and e.value.detail == {"codigo": "lenta", "mensaje": dictado.MENSAJE_LENTA}


def test_una_subida_estancada_no_deja_sin_voz_al_resto_del_panel(monkeypatch, limpio):
    # Mientras su audio no llega, la persona tiene su turno, pero no un cupo de Mnemo: las demás transcriben (antes,
    # dos subidas estancadas dejaban a todo el panel sin voz). Al vencer el plazo, 400 `lenta` y su turno queda libre
    b = Banco(monkeypatch)
    monkeypatch.setattr(dictado, "SUBIDA_CALLADA_S", 0.3)

    async def correr():
        llega = iter([{"type": "http.request", "body": AUDIO[:100], "more_body": True}])

        async def recibir():
            m = next(llega, None)
            if m is None:
                await asyncio.Event().wait()   # no llega nada más, y la conexión sigue abierta
            return m
        estancada = asyncio.create_task(b.crudo(0, recibir))
        await _hasta(lambda: ("prueba_dictado_servidor", 0) in dictado._en_curso)
        transporte = httpx.ASGITransport(app=b.app)
        async with httpx.AsyncClient(transport=transporte, base_url="http://panel") as http:
            def pedir(uid):
                return http.post("/api/agente/transcribir", content=AUDIO,
                                 headers={"Content-Type": "audio/webm", "x-uid": str(uid)})
            otras = await asyncio.gather(pedir(5), pedir(6))
            misma = await pedir(0)
            enviados = await estancada
            libre = ("prueba_dictado_servidor", 0) not in dictado._en_curso
            despues = await pedir(0)
        return otras, misma, enviados, libre, despues
    otras, misma, estancada, libre, despues = asyncio.run(correr())
    assert [r.status_code for r in otras] == [200, 200]
    assert misma.status_code == 429 and misma.json()["detail"]["mensaje"] == dictado.MENSAJE_A_LA_VEZ
    assert _respuesta(estancada) == (400, {"detail": {"codigo": "lenta", "mensaje": dictado.MENSAJE_LENTA}})
    assert libre and despues.status_code == 200
    assert len(b.cliente.llamadas) == 3 and not dictado._transcribiendo


# ───────────────────────────── La persona que se va ─────────────────────────────

def test_si_la_persona_se_va_mientras_se_transcribe_se_deja_de_esperar(monkeypatch, limpio, caplog):
    # Canceló o cerró la página mientras Mnemo transcribía: la llamada a Mnemo se cancela y su turno y su cupo quedan
    # libres en el acto (la pregunta que repite enseguida no rebota con 429). La respuesta, 400 `cortada`, nadie la lee
    b = Banco(monkeypatch)
    monkeypatch.setattr(dictado, "VIGILA_S", 0.01)

    async def correr():
        b.cliente.espera = asyncio.Event()
        se_va = asyncio.Event()
        llega = iter([{"type": "http.request", "body": AUDIO, "more_body": False}])

        async def recibir():
            m = next(llega, None)
            if m is None:
                await se_va.wait()
                return {"type": "http.disconnect"}
            return m
        tarea = asyncio.create_task(b.crudo(0, recibir))
        await _hasta(lambda: len(b.cliente.llamadas) == 1)
        tomado = (set(dictado._en_curso), len(dictado._transcribiendo))
        se_va.set()
        enviados = await asyncio.wait_for(tarea, 2)
        libre = (set(dictado._en_curso), len(dictado._transcribiendo))
        # Lo mismo mientras espera un cupo (dos personas lo ocupan): se va sin llegar a Mnemo
        transporte = httpx.ASGITransport(app=b.app)
        async with httpx.AsyncClient(transport=transporte, base_url="http://panel") as http:
            ocupan = [asyncio.create_task(http.post("/api/agente/transcribir", content=AUDIO,
                                                    headers={"Content-Type": "audio/webm", "x-uid": str(uid)}))
                      for uid in (5, 6)]
            await _hasta(lambda: len(b.cliente.llamadas) == 3)
            se_va.clear()
            llega = iter([{"type": "http.request", "body": AUDIO, "more_body": False}])   # la que lee `recibir`
            esperando = asyncio.create_task(b.crudo(0, recibir))
            await _hasta(lambda: ("prueba_dictado_servidor", 0) in dictado._en_curso)
            await asyncio.sleep(0.05)
            se_va.set()
            sin_cupo = await asyncio.wait_for(esperando, 2)
            sin_cupo_libre = ("prueba_dictado_servidor", 0) not in dictado._en_curso
            b.cliente.espera.set()
            await asyncio.gather(*ocupan)
        return tomado, enviados, libre, sin_cupo, sin_cupo_libre
    with caplog.at_level(logging.INFO, logger="panel"):
        tomado, enviados, libre, sin_cupo, sin_cupo_libre = asyncio.run(correr())
    assert tomado == ({("prueba_dictado_servidor", 0)}, 1)
    assert _respuesta(enviados) == (400, {"detail": {"codigo": "cortada", "mensaje": dictado.MENSAJE_CORTADA}})
    assert libre == (set(), 0) and b.cliente.canceladas == 1
    assert _respuesta(sin_cupo)[0] == 400 and sin_cupo_libre
    assert len(b.cliente.llamadas) == 3   # la que esperaba cupo no llegó a Mnemo
    assert not dictado._en_curso and not dictado._transcribiendo
    registro = "\n".join(m.getMessage() for m in caplog.records)
    assert "Dictado: no se transcribió (cortada)" in registro and PREGUNTA not in registro
    b.cliente.espera = None
    assert b.transcribir(0).json() == {"texto": PREGUNTA, "via": "mnemo"}   # y vuelve a preguntar enseguida


def test_mientras_siga_sin_aviso_del_servidor_espera_a_mnemo():
    # Un servidor que no sabe decir si la persona se fue (su `receive` falla): se espera el resultado, como siempre
    async def roto():
        raise RuntimeError("sin receive")

    async def trabajo():
        await asyncio.sleep(0.05)
        return "texto"
    assert asyncio.run(dictado.mientras_siga(SimpleNamespace(receive=roto), trabajo())) == "texto"

    # Y con la persona ahí, el vigía no queda colgado al terminar
    async def con_persona():
        nunca = asyncio.Event()

        async def recibir():
            await nunca.wait()
        r = await dictado.mientras_siga(SimpleNamespace(receive=recibir), trabajo())
        return r, [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    assert asyncio.run(con_persona()) == ("texto", [])


# ───────────────────────────── Las herramientas guardadas de una conversación ─────────────────────────────

def test_las_herramientas_guardadas_nunca_traen_las_del_modelo():
    def definicion(nombre):
        return {"name": nombre, "description": "x", "inputSchema": {"type": "object", "properties": {}},
                "annotations": {"readOnlyHint": True}}
    # una conversación guardada con un panel anterior (o con MNEMO_HERRAMIENTAS=*) contra un Mnemo que ya las ofrecía
    guardadas = [definicion("mnemo_transcribe"), definicion("mnemo_model_complete"), definicion("search")]
    nombres = [h.nombre for h in mnemo.desde_definiciones(guardadas)]
    assert nombres == ["mnemo_search"] and not set(nombres) & mnemo.NUNCA   # (el panel les antepone «mnemo_»)
    assert mnemo.desde_definiciones([definicion("mnemo_transcribe")]) == []
