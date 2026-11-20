"""La respuesta inmediata del asistente (app/agente/adelanto.py y su lugar en el turno, bucle.py): mientras el modelo
principal prepara la respuesta completa, otra petición corta (`rapido`) adelanta la idea general. Se prueba lo que se
muestra (el umbral que esconde la marca «—», sin Markdown, palabra por palabra, el tope cortado en el final de una
frase, «…» al cortar), los eventos y su orden entre los del turno, la carrera con el modelo principal, que un fallo no
toca el turno, lo que se guarda y cómo lo pinta el historial (nunca va al modelo), el renglón del contexto del modelo
principal, el ajuste `agente_adelanto` (y que con él apagado no hay petición), sus frases firmadas que acepta
`POST /api/agente/voz` (con el eco filtrado y sin datos de habitantes), que aprobar no la lanza, y la petición `rapido`
de los dos proveedores (Anthropic sin razonar o con lo mínimo; Mnemo con `reasoning: "off"`).

Solo datos inventados. Las del turno usan MongoDB (se saltan sin él) y el modelo falso: Anthropic simulado con dos
guiones (`APIDoble`: la respuesta inmediata se reconoce por su `system` en texto, sin caché) o el de Mnemo (la
respuesta inmediata va con `reasoning: "off"`). Las esperas en medio de una respuesta simulada miran los eventos que el
turno ya emitió (`Vistos`): nada depende de cuánto tarda la máquina."""
import asyncio
import copy
import dataclasses
import json
import logging
from collections import deque
from datetime import datetime, timezone
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from ayudas_agente import (ALCANCES_PANEL, TU, FakeAPI, R, T, con_herramientas, decidir, encender, encender_mnemo,
                           enviar, herramientas_falsas, poner_adelanto, sse, texto_de, tipos)
from ayudas_g3 import coordinador, persona
from app import acceso, modelo
from app.agente import adelanto, bucle, llm, modelo_mnemo, politica, sistema, voz
from app.agente import conversaciones as conv_db
from app.agente.proveedores import Respuesta, Uso
from test_voz_servidor import AUDIO, VOZ_ID, _mnemo_que_habla, audio_de, eventos

ADELANTO = ("Buena pregunta: la torre es la obra más grande de la propuesta. Enseguida se lo muestro en la "
            "presentación.")
RESPUESTA = "La torre tiene cuatro pisos y una placa de cimentación."
SECRETO = "Rosa Inventada vive en la vereda El Ejemplo"   # lo que nunca debe ir al registro


async def _sin_espera(segundos):
    return None


# ───────────────────────────── Ayudas ─────────────────────────────

class Vistos:
    """Los eventos que emite el turno, a medida que salen (`bucle.Turno.emitir`), y esperas sobre ellos para las
    respuestas simuladas: `hasta(condicion)` es una corrutina que vuelve cuando `condicion(eventos)` se cumple."""

    def __init__(self):
        self.eventos: list[dict] = []
        self._senales: set = set()

    def anotar(self, ev: dict) -> None:
        self.eventos.append(ev)
        for s in list(self._senales):
            s.set()

    def hasta(self, condicion, plazo: float = 15.0):
        async def esperar():
            async with asyncio.timeout(plazo):
                while not condicion(self.eventos):
                    s = asyncio.Event()
                    self._senales.add(s)
                    try:
                        await s.wait()
                    finally:
                        self._senales.discard(s)
        return esperar


def hay(tipo: str, veces: int = 1, **campos):
    """¿Ya salieron `veces` eventos de ese tipo (con esos campos)? Los eventos se acumulan entre turnos."""
    return lambda evs: sum(e.get("tipo") == tipo and all(e.get(k) == v for k, v in campos.items())
                           for e in evs) >= veces


def hasta_que(condicion, plazo: float = 15.0):
    """Una espera por sondeo (para lo que no es un evento del turno, como una petición que ya llegó)."""
    async def esperar():
        async with asyncio.timeout(plazo):
            while not condicion():
                await asyncio.sleep(0.01)
    return esperar


@pytest.fixture
def vistos(monkeypatch):
    v = Vistos()
    original = bucle.Turno.emitir

    def emitir(self, ev):
        original(self, ev)
        v.anotar(ev)
    monkeypatch.setattr(bucle.Turno, "emitir", emitir)
    monkeypatch.setattr(bucle, "dormir", _sin_espera)
    return v


class APIDoble:
    """La Messages API simulada con dos guiones: `adelanto` para las peticiones de la respuesta inmediata (`rapido`: el
    `system` va en texto, sin caché) y `principal` para las demás. Cada respuesta: una lista de eventos SSE (de `sse`)
    con, donde haga falta, esperas (una corrutina sin argumentos), una tupla (estado, cuerpo JSON) o una excepción.
    `peticiones[cual]`: el JSON y las cabeceras de cada una; `cortadas`: (cual, excepción) de los cuerpos que se
    dejaron de leer a mitad."""

    def __init__(self, principal, adelanto_):
        self.colas = {"principal": deque(principal), "adelanto": deque(adelanto_)}
        self.peticiones: dict[str, list] = {"principal": [], "adelanto": []}
        self.empezadas: list[str] = []          # los cuerpos que ya se empezaron a leer
        self.cortadas: list[tuple[str, str]] = []

    def __call__(self, req: httpx2.Request) -> httpx2.Response:
        j = json.loads(req.content)
        cual = "adelanto" if isinstance(j.get("system"), str) else "principal"
        self.peticiones[cual].append({"json": j, "cabeceras": dict(req.headers)})
        if not self.colas[cual]:
            raise AssertionError(f"APIDoble: no quedan respuestas para «{cual}»")
        item = self.colas[cual].popleft()
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, tuple):
            return httpx2.Response(item[0], json=item[1])

        async def cuerpo():
            self.empezadas.append(cual)
            terminado = False
            try:
                for e in item:
                    if callable(e):
                        await e()
                        continue
                    yield f"event: {e['type']}\ndata: {json.dumps(e)}\n\n".encode()
                terminado = True
            except BaseException as ex:
                self.cortadas.append((cual, type(ex).__name__))
                raise
            finally:
                if not terminado and not any(c == cual for c, _ in self.cortadas):
                    self.cortadas.append((cual, "cerrada"))

        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=cuerpo())


def encender_doble(app, principal, adelanto_, **cfg) -> APIDoble:
    """El asistente con el modelo de Anthropic simulado (`APIDoble`) y la respuesta inmediata encendida."""
    app.state.cfg = dataclasses.replace(app.state.cfg, anthropic_api_key="clave-falsa", **cfg)
    api = APIDoble(principal, adelanto_)
    http = httpx2.AsyncClient(transport=httpx2.MockTransport(api))
    app.state.agente_cliente = anthropic.AsyncAnthropic(api_key="clave-falsa", http_client=http, max_retries=0)
    poner_adelanto(app, True)
    return api


def con_espera(espera, eventos_sse: list, despues: int = 0) -> list:
    """`eventos_sse` con la espera insertada antes del evento `despues` (0: antes de todo)."""
    return [*eventos_sse[:despues], espera, *eventos_sse[despues:]]


def adelanto_mnemo(modelo_falso, *respuestas):
    """Separa las llamadas de la respuesta inmediata (`reasoning: "off"`) del modelo principal en el Mnemo falso:
    devuelve el `ModeloFalso` de la respuesta inmediata (su guion y sus `pedidos`)."""
    from ayudas_mcp import MODELO, ModeloFalso
    principal = modelo_falso.mcp.manejadores[MODELO]
    otro = ModeloFalso(modelo_falso.mcp, *respuestas)

    async def enrutar(args, avisar):
        return await (otro.atender if args.get("reasoning") == "off" else principal)(args, avisar)
    modelo_falso.mcp.manejadores[MODELO] = enrutar
    return otro


def tras(espera, respuesta: dict):
    """Una respuesta del Mnemo falso (`R(...)`) que empieza después de `espera`."""
    from ayudas_mcp import correcto

    async def f(args, avisar):
        await espera()
        datos = copy.deepcopy(respuesta["datos"])
        avance = respuesta.get("avance")
        if avance is None:
            avance = [t for b in datos["content"] if b.get("type") == "text"
                      for t in (b["text"][:len(b["text"]) // 2], b["text"][len(b["text"]) // 2:]) if t]
        for i, trozo in enumerate(avance, 1):
            await avisar(i, trozo)
        return correcto(datos)
    return f


def con_voz_clonada(sesion, modelo_falso):
    """La voz clonada elegida en Ajustes y `mnemo_speak` en el Mnemo falso (como en test_voz_frases)."""
    falso = _mnemo_que_habla()
    modelo_falso.mcp.herramientas += [h for h in falso.herramientas if h["name"] in ("mnemo_speak",
                                                                                      "mnemo_list_voices")]
    modelo_falso.mcp.manejadores.update({k: falso.manejadores[k] for k in ("mnemo_speak", "mnemo_list_voices")})
    r = sesion.put("/api/ajustes", json={"agente_voz": {"motor": "mnemo", "voz": VOZ_ID, "nombre": "Ana"}})
    assert r.status_code == 200, r.text


def _guardados(db, cid) -> list[dict]:
    return list(db[conv_db.MENSAJES].find({"conversacion": cid, "rol": "adelanto"}, {"_id": 0}))


# ───────────────────────────── Lo que se muestra (sin MongoDB) ─────────────────────────────

class ProveedorFalso:
    """Un proveedor inventado con la interfaz de `proveedores.Proveedor`: `generar` manda `trozos` como eventos
    `texto` (con `pausa` antes de cada uno) y devuelve una `Respuesta`, o lanza `error` al final. Anota cada llamada y
    si la cancelaron a mitad."""
    clave, modelo, max_tokens, tope_imagenes = "falso", "modelo-falso", 1000, 0

    def __init__(self, *trozos, error: BaseException | None = None, pausa: float = 0.0, antes: float = 0.0,
                 despues: float = 0.0, eventos: list[dict] | None = None, fin: str = "end_turn"):
        self.trozos, self.error, self.pausa, self.antes, self.despues = trozos, error, pausa, antes, despues
        self.eventos, self.fin = eventos, fin
        self.llamadas: list[dict] = []
        self.cancelada = False

    async def generar(self, sistema_, mensajes, herramientas, *, max_tokens, esfuerzo, al_evento, rapido=False):
        self.llamadas.append({"sistema": sistema_, "mensajes": mensajes, "herramientas": herramientas,
                              "max_tokens": max_tokens, "esfuerzo": esfuerzo, "rapido": rapido})
        try:
            await asyncio.sleep(self.antes)
            for ev in self.eventos or []:
                al_evento(ev)
            for t in self.trozos:
                await asyncio.sleep(self.pausa)
                al_evento({"tipo": "texto", "texto": t})
            await asyncio.sleep(self.despues)
        except asyncio.CancelledError:
            self.cancelada = True
            raise
        if self.error is not None:
            raise self.error
        return Respuesta(contenido=[{"type": "text", "text": "".join(self.trozos)}], fin=self.fin,
                         modelo="modelo-falso", uso=Uso(entrada=40, salida=12))

    def reintento(self, e, intento):
        return None

    def explicar(self, e):
        return "falló", "error"


def correr(proveedor, frases=None, durante=None) -> tuple[adelanto.Adelanto, list[dict], list]:
    """Corre una respuesta inmediata con `proveedor` hasta que termina: (el adelanto, sus eventos, lo que guardó).
    `durante(a)`: una corrutina que corre a la par (para cortarla o avisarle)."""
    eventos_, guardado = [], []

    async def guardar(texto, uso):
        guardado.append((texto, uso))

    async def principal():
        a = adelanto.Adelanto(proveedor, [{"role": "user", "content": [{"type": "text", "text": "Hola"}]}],
                              eventos_.append, frases, guardar=guardar)
        a.tarea = asyncio.ensure_future(a.correr())
        if durante is not None:
            await durante(a)
        await a.tarea
        return a
    return asyncio.run(principal()), eventos_, guardado


def mostrado(eventos_: list[dict]) -> str:
    return "".join(e["texto"] for e in eventos_ if e["tipo"] == "adelanto")


def test_lo_que_llega_se_muestra_palabra_por_palabra_y_termina():
    p = ProveedorFalso("Cla", "ro, con", " gusto le ex", "plico la torre", ". Enseguida le doy el detalle.")
    a, ev, guardado = correr(p)
    assert mostrado(ev) == "Claro, con gusto le explico la torre. Enseguida le doy el detalle."
    assert ev[-1] == {"tipo": "adelanto_fin"} and [e["tipo"] for e in ev].count("adelanto_fin") == 1
    # Lo primero espera a tener VISIBLE_MIN caracteres; después, nunca una palabra a medias
    entero = "Claro, con gusto le explico la torre. Enseguida le doy el detalle."
    primero = ev[0]["texto"]
    assert len(primero) >= adelanto.VISIBLE_MIN and primero == "Claro, con gusto le"
    acumulado = ""
    for e in ev[:-2]:   # hasta el final, cada trozo termina en una palabra entera (lo que sigue es un blanco)
        acumulado += e["texto"]
        assert entero.startswith(acumulado) and entero[len(acumulado)] == " ", acumulado
    # La petición: rápida, sin herramientas, con las instrucciones fijas y su tope de tokens
    assert p.llamadas == [{"sistema": sistema.SISTEMA_ADELANTO, "mensajes": a.mensajes, "herramientas": [],
                           "max_tokens": adelanto.ADELANTO_TOKENS, "esfuerzo": "low", "rapido": True}]
    # Lo mostrado y el uso se guardan
    assert guardado == [("Claro, con gusto le explico la torre. Enseguida le doy el detalle.", Uso(40, 12))]


@pytest.mark.parametrize("marca", ["—", " — ", "-", "–", "«—»", "—.", "", "\n— \n"])
def test_la_marca_de_no_hace_falta_nunca_se_ve(marca):
    a, ev, guardado = correr(ProveedorFalso(*marca) if marca else ProveedorFalso())
    assert ev == [{"tipo": "adelanto_fin", "vacio": True}] and a.visible is False
    assert guardado == [("", Uso(40, 12))]   # no se muestra nada, pero lo que gastó se suma


def test_sin_markdown_ni_la_marca_al_comienzo():
    _, ev, _ = correr(ProveedorFalso("— **Claro**, con `gusto` le explico ", "la ## torre."))
    assert mostrado(ev) == "Claro, con gusto le explico la  torre."


def test_un_texto_corto_completo_se_muestra():
    _, ev, _ = correr(ProveedorFalso("Con gusto."))
    assert mostrado(ev) == "Con gusto." and ev[-1] == {"tipo": "adelanto_fin"}


def test_el_tope_corta_en_el_final_de_una_frase_y_cancela_la_peticion():
    frase = "La propuesta trae obras de salud, vías y vivienda para las veredas. "
    p = ProveedorFalso(*[frase] * 12)
    _, ev, guardado = correr(p)
    texto = mostrado(ev)
    caben = max(n for n in range(13) if len((frase * n).rstrip()) <= adelanto.ADELANTO_MAX)
    assert caben >= 5 and texto == (frase * caben).rstrip()
    assert ev[-1] == {"tipo": "adelanto_fin"} and p.cancelada is True   # no sigue gastando en lo que no se muestra
    assert guardado == [(texto, None)]


def test_el_tope_sin_un_final_de_frase_corta_en_una_palabra_con_puntos_suspensivos():
    entero = "palabra larga sin punto " * 30
    p = ProveedorFalso(*["palabra larga sin punto "] * 30)
    _, ev, _ = correr(p)
    texto = mostrado(ev)
    assert texto.endswith("…") and texto[-2].isalpha() and len(texto) <= adelanto.ADELANTO_MAX + 1
    assert entero.startswith(texto[:-1]) and entero[len(texto) - 1] == " " and p.cancelada is True


def test_recortar_no_deja_atras_lo_ya_mostrado():
    largo = "Primera frase corta. " + "x" * 500
    assert adelanto._recortar(largo, 0) == "Primera frase corta."
    # lo mostrado ya pasó el final de la frase: se corta después, en una palabra, con «…»
    assert adelanto._recortar("Una frase. Y otra sin fin " + "y " * 300, 15).endswith("y…")
    # un punto entre cifras no es el final de una frase
    assert adelanto._recortar("Son 3.5 km de vía nueva " + "y " * 300, 0).endswith("y…")


def test_el_plazo_corta_lo_mostrado_con_puntos_suspensivos(monkeypatch):
    monkeypatch.setattr(adelanto, "ADELANTO_S", 0.3)
    p = ProveedorFalso("Claro, con gusto le explico la torre de", despues=5)   # el modelo no termina a tiempo
    _, ev, guardado = correr(p)
    assert mostrado(ev) == "Claro, con gusto le explico la torre…" and ev[-1] == {"tipo": "adelanto_fin"}
    assert p.cancelada is True and guardado == [("Claro, con gusto le explico la torre…", None)]


def test_el_plazo_antes_de_mostrar_algo_es_vacio(monkeypatch):
    monkeypatch.setattr(adelanto, "ADELANTO_S", 0.2)
    p = ProveedorFalso("Claro, con gusto le explico.", antes=5)
    _, ev, guardado = correr(p)
    assert ev == [{"tipo": "adelanto_fin", "vacio": True}] and p.cancelada is True and guardado == []


def test_un_fallo_se_descarta_y_al_registro_va_solo_el_tipo(caplog):
    caplog.set_level(logging.INFO, logger="panel")
    _, ev, guardado = correr(ProveedorFalso(error=RuntimeError(SECRETO)))
    assert ev == [{"tipo": "adelanto_fin", "vacio": True}] and guardado == []
    assert "la respuesta inmediata falló (RuntimeError)" in caplog.text and SECRETO not in caplog.text
    # A mitad: lo mostrado queda, cortado en la última palabra entera
    _, ev, guardado = correr(ProveedorFalso("Claro, con gusto le explico la ", "torre de sal",
                                            error=RuntimeError(SECRETO)))
    assert mostrado(ev) == "Claro, con gusto le explico la torre de…" and ev[-1] == {"tipo": "adelanto_fin"}
    assert SECRETO not in caplog.text and "Claro" not in caplog.text


def test_si_el_principal_escribe_antes_se_cancela_y_despues_no():
    async def antes(a):
        await asyncio.sleep(0.05)
        a.principal_escribe()
    p = ProveedorFalso("Claro, con gusto le explico.", antes=1)
    _, ev, guardado = correr(p, durante=antes)
    assert ev == [{"tipo": "adelanto_fin", "vacio": True}] and p.cancelada is True and guardado == []

    async def despues(a):
        while not a.visible:
            await asyncio.sleep(0.01)
        a.principal_escribe()
    p = ProveedorFalso("Claro, con gusto le explico ", "la torre nueva. ", "Enseguida le doy el detalle.",
                       pausa=0.02)
    _, ev, _ = correr(p, durante=despues)
    assert mostrado(ev) == "Claro, con gusto le explico la torre nueva. Enseguida le doy el detalle."
    assert ev[-1] == {"tipo": "adelanto_fin"} and p.cancelada is False


def test_texto_ronda_de_mnemo():
    # Antes de mostrar algo, el texto final reemplaza lo que llegó
    _, ev, _ = correr(ProveedorFalso(eventos=[{"tipo": "texto", "texto": "Clar"},
                                              {"tipo": "texto_ronda", "texto": "Con gusto le explico la torre."}]))
    assert mostrado(ev) == "Con gusto le explico la torre."
    # Después, lo mostrado no se retira: queda como está, no se agrega lo que no casa y se cierra como cortado («…»)
    _, ev, _ = correr(ProveedorFalso(eventos=[{"tipo": "texto", "texto": "Con gusto le explico el hospital "},
                                              {"tipo": "texto_ronda", "texto": "Otra cosa distinta por completo."},
                                              {"tipo": "texto", "texto": "y más."}]))
    assert mostrado(ev) == "Con gusto le explico el hospital…" and ev[-1] == {"tipo": "adelanto_fin"}
    # El razonamiento, los avisos y las herramientas no se muestran
    _, ev, _ = correr(ProveedorFalso("Con gusto le explico la torre.", eventos=[
        {"tipo": "progreso", "texto": "Pienso en algo largo y privado."}, {"tipo": "aviso", "texto": "x"},
        {"tipo": "herramienta", "id": "t", "nombre": "x"}]))
    assert mostrado(ev) == "Con gusto le explico la torre."


@pytest.mark.parametrize("fin", ["max_tokens", "refusal", "other"])
def test_si_la_peticion_no_termino_de_verdad_lo_retenido_no_se_muestra(fin):
    # El modelo se quedó a mitad de una palabra (el tope de tokens) o dejó de escribir (un rechazo): la palabra que se
    # retenía no sale y lo mostrado termina en «…» (también en lo que se guarda y en lo que se dice)
    frases = voz.Frases(lambda t: voz.firmar(b"k" * 32, 0, 7, t), eco="¿Qué es la torre?")
    _, ev, guardado = correr(ProveedorFalso("Claro, con gusto le cuento la ide", fin=fin), frases=frases)
    assert mostrado(ev) == "Claro, con gusto le cuento la…"
    assert [e for e in ev if e["tipo"] == "adelanto"][-1] == {"tipo": "adelanto", "texto": "…"}
    assert ev[-1] == {"tipo": "adelanto_fin"} and guardado == [("Claro, con gusto le cuento la…", Uso(40, 12))]
    assert [e["texto"] for e in ev if e["tipo"] == "adelanto_frase"] == ["Claro, con gusto le cuento la…"]
    # Si no alcanzó a mostrar nada, no se muestra lo poco que llegó: vacío (lo que gastó, igual se suma)
    _, ev, guardado = correr(ProveedorFalso("Claro, con", fin=fin))
    assert ev == [{"tipo": "adelanto_fin", "vacio": True}] and guardado == [("", Uso(40, 12))]
    # Con su final de verdad, lo retenido sí sale entero
    _, ev, _ = correr(ProveedorFalso("Claro, con", fin="stop_sequence"))
    assert mostrado(ev) == "Claro, con" and ev[-1] == {"tipo": "adelanto_fin"}


def test_sus_frases_se_numeran_aparte_y_se_firman():
    frases = voz.Frases(lambda t: voz.firmar(b"k" * 32, 0, 7, t), eco="¿Qué es la torre?")
    _, ev, _ = correr(ProveedorFalso("Con gusto le cuento lo esencial de la torre. ", "Enseguida se lo muestro en "
                                     "la presentación"), frases=frases)
    af = [e for e in ev if e["tipo"] == "adelanto_frase"]
    assert [(e["n"], e["texto"]) for e in af] == [(0, "Con gusto le cuento lo esencial de la torre."),
                                                 (1, "Enseguida se lo muestro en la presentación")]
    assert all(voz.firma_valida(b"k" * 32, 0, 7, e["texto"], e["firma"]) for e in af)
    assert "frase" not in tipos(ev)
    # La última sale al cerrar, antes de `adelanto_fin`
    assert ev.index(af[-1]) < ev.index({"tipo": "adelanto_fin"})


def test_los_mensajes_de_la_peticion():
    ctx = "<contexto_del_panel>\nFecha y hora en Colombia: hoy\n</contexto_del_panel>"
    historial = [
        {"role": "user", "content": [{"type": "text", "text": "<contexto_del_panel>\nviejo\n</contexto_del_panel>"},
                                     {"type": "text", "text": "¿Cuántas obras hay?"}]},
        {"role": "assistant", "content": [{"type": "thinking", "thinking": "privado", "signature": "f"},
                                          {"type": "text", "text": "Voy a mirar."},
                                          {"type": "tool_use", "id": "t1", "name": "x", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "resultado"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "Hay tres obras."}]},
    ]
    assert adelanto.mensajes(historial, ctx, "¿Y la torre?") == [
        {"role": "user", "content": [{"type": "text", "text": "¿Cuántas obras hay?"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "Voy a mirar."},
                                          {"type": "text", "text": "Hay tres obras."}]},
        {"role": "user", "content": [{"type": "text", "text": ctx}, {"type": "text", "text": "¿Y la torre?"}]}]
    # Solo los últimos MENSAJES_MAX con texto, empezando por la persona, cada uno acotado
    largo = [{"role": r, "content": [{"type": "text", "text": f"{r} {i} " + "x" * 3000}]}
             for i in range(10) for r in ("user", "assistant")]
    m = adelanto.mensajes(largo, ctx, "Hola")
    assert [x["role"] for x in m] == ["user", "assistant"] * 4 + ["user"] and len(m) == 9
    assert m[0]["content"][0]["text"].startswith("user 6 ")
    assert all(len(b["text"]) <= adelanto.TEXTO_MENSAJE_MAX for x in m[:-1] for b in x["content"])
    # Un historial que termina en la persona (un turno cortado): se junta con el mensaje nuevo
    m = adelanto.mensajes([{"role": "user", "content": [{"type": "text", "text": "Antes"}]}], ctx, "Ahora")
    assert m == [{"role": "user", "content": [{"type": "text", "text": "Antes"}, {"type": "text", "text": ctx},
                                              {"type": "text", "text": "Ahora"}]}]
    assert adelanto.mensajes([], ctx, "Hola") == [
        {"role": "user", "content": [{"type": "text", "text": ctx}, {"type": "text", "text": "Hola"}]}]


# ───────────────────────────── Los candados y el cupo de Mnemo (sin MongoDB) ─────────────────────────────

class _ApiInterna:
    async def cerrar(self):
        pass


def _turno(proveedor, uid=7, cid=5) -> bucle.Turno:
    app = SimpleNamespace(state=SimpleNamespace(db=None, cfg=SimpleNamespace(), cortacircuitos=None))
    return bucle.Turno(app=app, quien=SimpleNamespace(uid=uid, rol="admin"), ajustes={},
                       agente={"retencion_dias": 30}, api=_ApiInterna(), conv=None, cid=cid, titulo="x", turno="t1",
                       limite=None, proveedor=proveedor)


def test_si_el_navegador_se_va_mientras_se_corta_el_adelanto_se_suelta_la_reserva(monkeypatch):
    soltadas = []
    monkeypatch.setattr(conv_db, "soltar", lambda db, cid, turno: soltadas.append(cid))
    monkeypatch.setattr(conv_db, "renovar_candado", lambda db, cid, turno: True)

    async def principal():
        t = _turno(ProveedorFalso("Claro, con gusto le cuento la idea general ", despues=10))
        assert t.ocupacion.reservar(7, 5) is None
        guardando = asyncio.Event()

        async def guardar_lento(texto, uso):   # MongoDB lento: guardar lo mostrado tarda
            guardando.set()
            await asyncio.sleep(2)

        async def trabajo():
            t.adelanto = adelanto.Adelanto(t.proveedor, [], t.emitir, None, guardar=guardar_lento)
            t.adelanto.tarea = bucle._en_fondo(t.adelanto.correr())
            while not t.adelanto.visible:
                await asyncio.sleep(0.01)
            raise bucle.FinDelTurno("El modelo falló.", "llm_limite")   # el turno falla con el adelanto a la vista

        t.lanzar(trabajo)
        t.arrancado.set()
        # El turno está en su cierre, esperando a que el adelanto cortado guarde: la persona cierra la pestaña
        # (`Turno.eventos` cancela el productor)
        await asyncio.wait_for(guardando.wait(), 5)
        assert t.adelanto.terminado and not t.suelto
        t._cerrandose()
        t.tarea.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t.tarea
        return t
    t = asyncio.run(principal())
    # La reserva del proceso y el candado de MongoDB se soltaron igual: la persona puede volver a escribir
    assert t.suelto is True and soltadas == [5]
    assert t.ocupacion.usuarios == set() and t.ocupacion.conversaciones == set()
    assert t.ocupacion.usuarios_cerrando == set() and t.ocupacion.reservar(7, 5) is None


def test_el_lugar_de_mnemo_es_uno_a_la_vez_y_sin_esperar():
    a, b = object(), object()
    try:
        assert adelanto.tomar_mnemo(a) is True and adelanto.tomar_mnemo(b) is False
        adelanto.soltar_mnemo(a)
        assert adelanto.tomar_mnemo(b) is True
    finally:
        adelanto.soltar_mnemo(a)
        adelanto.soltar_mnemo(b)
    # Dos turnos con Mnemo (cada uno solo en su proceso): el segundo no la da mientras el primero la tiene
    mnemo = ProveedorFalso()
    mnemo.clave = "mnemo"
    uno, dos = _turno(mnemo, uid=1, cid=1), _turno(mnemo, uid=2, cid=2)
    try:
        assert uno.ocupacion.reservar(1, 1) is None and dos.ocupacion.reservar(2, 2) is None
        assert uno._cabe_adelanto() is True and dos._cabe_adelanto() is False
        uno._soltar_ficha_adelanto()
        assert dos._cabe_adelanto() is True and adelanto._mnemo == {dos.ficha_adelanto}
    finally:
        uno._soltar_ficha_adelanto()
        dos._soltar_ficha_adelanto()
    assert adelanto._mnemo == set()
    # En modo directo no se toma nada
    directo = _turno(ProveedorFalso(), uid=3, cid=3)
    assert directo.ocupacion.reservar(3, 3) is None and directo.ocupacion.reservar(4, None) is None
    assert directo._cabe_adelanto() is True and directo.ficha_adelanto is None


# ───────────────────────────── La petición `rapido` de cada proveedor ─────────────────────────────

def _cfg(**k):
    return SimpleNamespace(agente_modelo="claude-opus-5-5", agente_esfuerzo="high", agente_modelo_adelanto="", **k)


def test_rapido_de_anthropic_sin_razonar_ni_herramientas_ni_cache():
    p = llm.parametros_rapido(_cfg(), max_tokens=300)
    # Claude Opus 5.5 no deja apagar el razonamiento: esfuerzo bajo y margen para lo poco que razone
    assert p == {"model": "claude-opus-5-5", "max_tokens": 300 + llm.MARGEN_PENSAR_RAPIDO, "timeout": llm.PLAZO,
                 "output_config": {"effort": "low"}}
    # Los que sí dejan, lo apagan (sin ningún otro campo)
    s = llm.parametros_rapido(SimpleNamespace(agente_modelo="claude-opus-5-5",
                                              agente_modelo_adelanto="claude-sonnet-5-5"), max_tokens=300)
    assert s["model"] == "claude-sonnet-5-5" and s["thinking"] == {"type": "between_tools"} and s["max_tokens"] == 300
    h = llm.parametros_rapido(SimpleNamespace(agente_modelo="claude-haiku-5-5"), max_tokens=300)
    assert h["thinking"] == {"type": "disabled"} and h["output_config"] == {"effort": "low"}
    # Un modelo sin capacidades conocidas: ni `thinking` ni esfuerzo (los viejos lo rechazan), pero con el margen: los
    # actuales fuera de CAPACIDADES (Claude Sonnet 5) piensan por defecto, y sin él se comerían los 300 tokens
    assert llm.parametros_rapido(SimpleNamespace(agente_modelo="claude-haiku-4-5"), max_tokens=300) == {
        "model": "claude-haiku-4-5", "max_tokens": 300 + llm.MARGEN_PENSAR_RAPIDO, "timeout": llm.PLAZO}
    s5 = llm.parametros_rapido(SimpleNamespace(agente_modelo="claude-opus-5-5",
                                               agente_modelo_adelanto="claude-sonnet-5"),
                               max_tokens=adelanto.ADELANTO_TOKENS)
    assert s5 == {"model": "claude-sonnet-5", "max_tokens": adelanto.ADELANTO_TOKENS + llm.MARGEN_PENSAR_RAPIDO,
                  "timeout": llm.PLAZO}
    # Claude Opus 5: piensa con el esfuerzo `low` (no se apaga: podría colar marcas de razonamiento en lo que se dice)
    o5 = llm.parametros_rapido(SimpleNamespace(agente_modelo="claude-opus-5"), max_tokens=300)
    assert "thinking" not in o5 and o5["max_tokens"] == 300 + llm.MARGEN_PENSAR_RAPIDO
    assert o5["output_config"] == {"effort": "low"}

    cliente, api = None, FakeAPI([sse(T("Con gusto."))])
    http = httpx2.AsyncClient(transport=httpx2.MockTransport(api))
    cliente = anthropic.AsyncAnthropic(api_key="clave-falsa", http_client=http, max_retries=0)
    app = SimpleNamespace(state=SimpleNamespace(agente_cliente=cliente))
    textos = []

    async def pedir():
        return await llm.ProveedorAnthropic(app, _cfg()).generar(
            "Instrucciones.", [{"role": "user", "content": [{"type": "text", "text": "Hola"}]}],
            [{"name": "x", "description": "x", "input_schema": {"type": "object"}}], max_tokens=300,
            esfuerzo="high", al_evento=lambda ev: textos.append(ev), rapido=True)
    r = asyncio.run(pedir())
    j = api.peticiones[0]["json"]
    assert j["system"] == "Instrucciones." and "tools" not in j and "thinking" not in j
    assert "cache_control" not in j and "fallbacks" not in j and j["output_config"] == {"effort": "low"}
    assert "anthropic-beta" not in api.peticiones[0]["cabeceras"]
    assert "".join(e["texto"] for e in textos if e["tipo"] == "texto") == "Con gusto." and r.fin == "end_turn"


def test_rapido_de_mnemo_sin_razonar_ni_herramientas():
    hs = [{"name": "contar", "description": "x", "input_schema": {"type": "object"}}]
    args = modelo_mnemo.argumentos("S", [{"role": "user", "content": [{"type": "text", "text": "Hola"}]}], hs,
                                   max_tokens=300, esfuerzo="high", modelo="ligero", rapido=True)
    assert args["reasoning"] == "off" and "tools" not in args and args["max_tokens"] == 300
    assert args["model"] == {"model": "ligero"}   # el mismo modelo de siempre
    normal = modelo_mnemo.argumentos("S", [{"role": "user", "content": "Hola"}], hs, max_tokens=300,
                                     esfuerzo="high")
    assert normal["reasoning"] == "high" and normal["tools"]


def test_la_configuracion_del_modelo_de_la_respuesta_inmediata(monkeypatch):
    from app import config
    monkeypatch.setenv("AGENTE_MODELO_ADELANTO", " claude-haiku-5-5 ")
    monkeypatch.setenv("MONGODB_URI", "mongodb://127.0.0.1:27017")
    assert config.cargar().agente_modelo_adelanto == "claude-haiku-5-5"
    monkeypatch.delenv("AGENTE_MODELO_ADELANTO")
    c = config.cargar()
    assert c.agente_modelo_adelanto == "" and llm.modelo_rapido(c) == c.agente_modelo


# ───────────────────────────── El renglón del contexto del modelo principal ─────────────────────────────

def test_el_renglon_del_adelanto_va_en_el_contexto_y_no_en_el_system():
    ahora = datetime(2026, 11, 20, 15, 0, tzinfo=timezone.utc)
    con = sistema.contexto_del_panel({}, ahora, adelanto=True)
    assert sistema.ADELANTO_EN_CURSO in con and con.endswith("</contexto_del_panel>")
    # En condicional y con las mismas excepciones que sus instrucciones (ahí no hay adelanto): a un saludo, saluda
    e = sistema.ADELANTO_EN_CURSO
    assert "puede estar dándole" in e and "no vuelvas a saludar ni repitas esa idea general" in e
    for caso in ("un saludo", "una orden simple", "una aprobación", "una sola frase"):
        assert caso in e and caso.split()[-1] in sistema.SISTEMA_ADELANTO, caso
    assert "no hay adelanto: responde como siempre (si la persona saluda, salúdala)" in e
    assert "no saludes" not in e
    assert sistema.ADELANTO_EN_CURSO not in sistema.contexto_del_panel({}, ahora)
    assert sistema.ADELANTO_EN_CURSO not in sistema.texto(SimpleNamespace(nombre="Ana", rol="admin"), [])
    # Las instrucciones de la respuesta inmediata: cortas, sin datos inventados, la marca y lo que promete
    s = sistema.SISTEMA_ADELANTO
    assert "1 a 3 frases" in s and "45 palabras" in s and "«—»" in s and adelanto.SALTO == "—"
    assert "enseguida se lo muestro en la presentación" in s and "enseguida le doy el detalle" in s
    assert "sin cifras, nombres, fechas ni datos que no estén ya en la conversación" in s
    assert "sin listas, enlaces, Markdown, emojis, «@» ni números de 7 o más dígitos" in s


# ───────────────────────────── El turno (con MongoDB) ─────────────────────────────

def test_el_adelanto_llega_antes_de_la_respuesta_y_no_la_toca(sesion, vistos):
    db = sesion.app.state.db
    api = encender_doble(sesion.app, [con_espera(vistos.hasta(hay("adelanto_fin")), sse(T(RESPUESTA)))],
                         [sse(T(ADELANTO)), sse(T("—"))])
    api.colas["principal"].append(con_espera(vistos.hasta(hay("adelanto_fin", 2)), sse(T("Son cuatro."))))
    r, ev = enviar(sesion, "Explícanos la torre", contexto={"vista": "presentacion"})
    assert r.status_code == 200, r.text
    cid = ev[0]["conversacion"]
    assert texto_de(ev, "adelanto") == ADELANTO and texto_de(ev) == RESPUESTA
    fin_adelanto = ev.index({"tipo": "adelanto_fin"})
    assert max(i for i, e in enumerate(ev) if e["tipo"] == "adelanto") < fin_adelanto
    assert fin_adelanto < next(i for i, e in enumerate(ev) if e["tipo"] == "texto")
    assert ev[0]["tipo"] == "inicio" and ev[-1]["motivo"] == "listo"
    # No es un turno: no cuenta en el tope diario
    assert ev[-1]["limite"]["usados"] == 1
    # La petición de la respuesta inmediata: rápida, con el mensaje y su contexto, sin el renglón del principal
    (pa,) = api.peticiones["adelanto"]
    j = pa["json"]
    assert j["system"] == sistema.SISTEMA_ADELANTO and "tools" not in j and "thinking" not in j
    assert j["output_config"] == {"effort": "low"} and "cache_control" not in j and "fallbacks" not in j
    assert j["max_tokens"] == adelanto.ADELANTO_TOKENS + llm.MARGEN_PENSAR_RAPIDO
    assert "anthropic-beta" not in pa["cabeceras"]
    (m,) = j["messages"]
    assert m["role"] == "user" and m["content"][1] == {"type": "text", "text": "Explícanos la torre"}
    assert "Vista abierta: presentacion" in m["content"][0]["text"]
    assert sistema.ADELANTO_EN_CURSO not in m["content"][0]["text"]
    # Al modelo principal le llega el renglón que le dice que hay un adelanto
    principal = api.peticiones["principal"][0]["json"]
    assert sistema.ADELANTO_EN_CURSO in principal["messages"][0]["content"][0]["text"]
    # Lo mostrado se guarda con el turno, nunca para el modelo
    (g,) = _guardados(db, cid)
    assert g["texto"] == ADELANTO and g["replay"] is False and "contenido" not in g
    vista = sesion.get(f"/api/agente/conversaciones/{cid}").json()
    assert vista["mensajes"][0] == {"rol": "usuario", "texto": "Explícanos la torre"}
    assert vista["mensajes"][1]["partes"] == [{"tipo": "adelanto", "texto": ADELANTO},
                                              {"tipo": "texto", "texto": RESPUESTA}]
    assert ADELANTO not in json.dumps(conv_db.historial(db, cid), ensure_ascii=False)
    assert conv_db.textos_de_la_persona(db, cid) == ["Explícanos la torre"]
    # Lo que gastó se suma al día de la persona (50 de salida cada una)
    assert db[conv_db.USO].find_one({"uid": 0})["salida"] == 100
    # El turno siguiente: el modelo principal no ve el adelanto y su historial sigue alternando
    _, ev = enviar(sesion, "¿Cuántos pisos?", conversacion=cid)
    assert {"tipo": "adelanto_fin", "vacio": True} in ev and "adelanto" not in tipos(ev)
    segunda = api.peticiones["principal"][1]["json"]["messages"]
    assert [x["role"] for x in segunda] == ["user", "assistant", "user"]
    assert ADELANTO not in json.dumps(segunda, ensure_ascii=False)
    # La respuesta inmediata del segundo turno lee la conversación (sin el contexto viejo ni el adelanto)
    msgs = api.peticiones["adelanto"][1]["json"]["messages"]
    assert [x["role"] for x in msgs] == ["user", "assistant", "user"]
    assert msgs[0]["content"] == [{"type": "text", "text": "Explícanos la torre"}]
    assert msgs[1]["content"] == [{"type": "text", "text": RESPUESTA}]
    assert len(_guardados(db, cid)) == 1   # vacío: no se guarda nada


@pytest.mark.parametrize("respuesta", [sse(T("—")), sse(T("  -  ")), sse()])
def test_la_marca_no_se_muestra_y_el_turno_sigue(sesion, vistos, respuesta):
    encender_doble(sesion.app, [con_espera(vistos.hasta(hay("adelanto_fin")), sse(T(RESPUESTA)))], [respuesta])
    _, ev = enviar(sesion, "Hola")
    assert "adelanto" not in tipos(ev) and [e for e in ev if e["tipo"] == "adelanto_fin"] == [
        {"tipo": "adelanto_fin", "vacio": True}]
    assert texto_de(ev) == RESPUESTA and ev[-1]["motivo"] == "listo"
    assert _guardados(sesion.app.state.db, ev[0]["conversacion"]) == []


def test_si_la_respuesta_llega_antes_el_adelanto_se_cancela(sesion, vistos):
    # La respuesta inmediata no llega nunca (espera el fin del turno); el modelo principal escribe en cuanto el cuerpo
    # de la respuesta inmediata se empezó a leer
    api = encender_doble(sesion.app, [], [con_espera(vistos.hasta(hay("fin"), plazo=60), sse(T(ADELANTO)))])
    api.colas["principal"].append(con_espera(hasta_que(lambda: "adelanto" in api.empezadas), sse(T(RESPUESTA))))
    _, ev = enviar(sesion, "¿Cuántas obras hay?")
    assert "adelanto" not in tipos(ev) and ev[-1]["motivo"] == "listo" and texto_de(ev) == RESPUESTA
    vacio = ev.index({"tipo": "adelanto_fin", "vacio": True})
    assert vacio < next(i for i, e in enumerate(ev) if e["tipo"] == "texto")
    # Su petición se cortó (no esperó a su plazo) y no se guardó nada
    assert api.cortadas and api.cortadas[0][0] == "adelanto" and api.cortadas[0][1] != "TimeoutError"
    assert _guardados(sesion.app.state.db, ev[0]["conversacion"]) == []


def test_lo_que_ya_se_mostro_sigue_hasta_el_final(sesion, vistos):
    # Muestra la primera mitad, espera a que el modelo principal escriba y termina
    a = sse(T(ADELANTO))
    principal = con_espera(vistos.hasta(hay("adelanto")), sse(T(RESPUESTA)))
    api = encender_doble(sesion.app, [principal], [con_espera(vistos.hasta(hay("texto")), a, despues=4)])
    _, ev = enviar(sesion, "Explícanos la torre")
    assert texto_de(ev, "adelanto") == ADELANTO and texto_de(ev) == RESPUESTA
    assert {"tipo": "adelanto_fin"} in ev and {"tipo": "adelanto_fin", "vacio": True} not in ev
    primer_texto = next(i for i, e in enumerate(ev) if e["tipo"] == "texto")
    assert any(e["tipo"] == "adelanto" for e in ev[primer_texto:])
    # El turno lo espera: su fin va antes del `fin` del turno
    assert ev.index({"tipo": "adelanto_fin"}) < len(ev) - 1 and ev[-1]["tipo"] == "fin"
    assert api.cortadas == []
    assert _guardados(sesion.app.state.db, ev[0]["conversacion"])[0]["texto"] == ADELANTO


def test_un_fallo_del_adelanto_no_toca_el_turno(sesion, vistos, caplog):
    caplog.set_level(logging.INFO, logger="panel")
    error = {"type": "error", "error": {"type": "api_error", "message": SECRETO}}
    encender_doble(sesion.app, [con_espera(vistos.hasta(hay("adelanto_fin")), sse(T(RESPUESTA))),
                                con_espera(vistos.hasta(hay("adelanto_fin", 2)), sse(T(RESPUESTA)))],
                   [(500, error), sse(T(ADELANTO), error="overloaded_error")])
    _, ev = enviar(sesion, "Hola")
    cid = ev[0]["conversacion"]
    assert [e for e in ev if e["tipo"].startswith("adelanto")] == [{"tipo": "adelanto_fin", "vacio": True}]
    assert texto_de(ev) == RESPUESTA and ev[-1]["motivo"] == "listo" and "error" not in tipos(ev)
    # A mitad del flujo: lo mostrado queda (cortado en la última palabra entera, con «…») y se guarda
    _, ev = enviar(sesion, "Hola otra vez", conversacion=cid)
    mostrado_ = texto_de(ev, "adelanto")
    assert mostrado_.endswith("…") and ADELANTO.startswith(mostrado_[:-1]) and {"tipo": "adelanto_fin"} in ev
    assert texto_de(ev) == RESPUESTA and ev[-1]["motivo"] == "listo"
    assert [g["texto"] for g in _guardados(sesion.app.state.db, cid)] == [mostrado_]
    assert "la respuesta inmediata falló" in caplog.text
    assert SECRETO not in caplog.text and "torre" not in caplog.text


def test_un_error_del_turno_corta_el_adelanto_y_guarda_lo_mostrado(sesion, vistos):
    # El modelo principal falla (sin reintentos) cuando el adelanto ya mostró algo y sigue escribiendo
    api = encender_doble(sesion.app, [con_espera(vistos.hasta(hay("adelanto")), sse(error="invalid_request_error"))],
                         [con_espera(vistos.hasta(hay("fin"), plazo=60), sse(T(ADELANTO)), despues=4)])
    _, ev = enviar(sesion, "Hola")
    assert ev[-2]["tipo"] == "error" and ev[-1]["motivo"] == "error"
    corte = ev.index({"tipo": "adelanto_fin"})
    assert corte < len(ev) - 2   # el fin del adelanto va antes del error y del fin del turno
    mostrado_ = texto_de(ev, "adelanto")
    assert mostrado_.endswith("…") and ADELANTO.startswith(mostrado_[:-1])
    assert [c for c in api.cortadas if c[0] == "adelanto"] == [("adelanto", "CancelledError")]
    assert [g["texto"] for g in _guardados(sesion.app.state.db, ev[0]["conversacion"])] == [mostrado_]


def test_con_el_ajuste_apagado_no_hay_adelanto(sesion, vistos):
    api = encender(sesion.app, sse(T(RESPUESTA)))   # (`encender` lo deja apagado)
    _, ev = enviar(sesion, "Explícanos la torre", contexto={"voz": True})
    assert not any(e["tipo"].startswith("adelanto") for e in ev) and texto_de(ev) == RESPUESTA
    assert len(api.peticiones) == 1   # una sola petición: la del modelo principal
    assert sistema.ADELANTO_EN_CURSO not in json.dumps(api.peticiones[0]["json"], ensure_ascii=False)
    assert _guardados(sesion.app.state.db, ev[0]["conversacion"]) == []


def test_aprobar_no_lanza_el_adelanto(sesion, vistos, monkeypatch):
    lista, falsas = herramientas_falsas()
    con_herramientas(monkeypatch, lista)
    pid = persona(sesion.app.state.db, nombre="ANA INVENTADA DE PRUEBA", consentimiento="si")
    api = encender_doble(sesion.app, [
        con_espera(vistos.hasta(hay("adelanto_fin")), sse(
            T("Propongo la nota."), TU("toolu_n", "nota_falsa", {"persona_id": pid, "texto": "Llamar el lunes"}),
            stop="tool_use")),
        sse(T("Listo, quedó la nota."))], [sse(T("—"))])
    _, ev = enviar(sesion, "Agrega una nota")
    assert ev[-1]["motivo"] == "confirmacion"
    r, ev = decidir(sesion, ev[0]["conversacion"], toolu_n=True)
    assert r.status_code == 200, r.text
    assert not any(e["tipo"].startswith("adelanto") for e in ev) and ev[-1]["motivo"] == "listo"
    assert len(api.peticiones["adelanto"]) == 1 and len(api.peticiones["principal"]) == 2
    assert sistema.ADELANTO_EN_CURSO not in json.dumps(api.peticiones["principal"][1]["json"]["messages"][-1],
                                                       ensure_ascii=False)


def test_se_guarda_arriba_de_la_respuesta_aunque_termine_despues_de_una_ronda(sesion, vistos, monkeypatch):
    lista, _ = herramientas_falsas()
    con_herramientas(monkeypatch, lista)
    db = sesion.app.state.db
    # La primera ronda (solo una herramienta, sin texto) termina antes; el adelanto, después; la respuesta, al final
    guardado = hasta_que(lambda: db[conv_db.MENSAJES].count_documents({"rol": "adelanto"}) > 0)
    encender_doble(sesion.app, [sse(TU("toolu_1", "contar_falsa", {"lugar": "Casco"}), stop="tool_use"),
                                con_espera(guardado, sse(T(RESPUESTA)))],
                   [con_espera(vistos.hasta(hay("herramienta", estado="ok")), sse(T(ADELANTO)))])
    _, ev = enviar(sesion, "¿Cuántas personas hay en el casco?")
    cid = ev[0]["conversacion"]
    assert ev[-1]["motivo"] == "listo" and texto_de(ev, "adelanto") == ADELANTO
    roles = [d["rol"] for d in conv_db.mensajes_de(db, cid)]
    assert roles == ["user", "assistant", "user", "adelanto", "assistant"]
    partes = sesion.get(f"/api/agente/conversaciones/{cid}").json()["mensajes"][1]["partes"]
    assert partes[0] == {"tipo": "adelanto", "texto": ADELANTO}
    assert [p["tipo"] for p in partes] == ["adelanto", "herramienta", "texto"]


def test_para_interfaz_pone_el_adelanto_arriba_de_su_turno():
    a = conv_db.a_json
    docs = [
        {"rol": "user", "texto": "Primera", "contenido": a([{"type": "text", "text": "Primera"}]), "replay": True},
        {"rol": "assistant", "replay": True, "contenido": a([{"type": "text", "text": "Uno."}])},
        {"rol": "user", "texto": "Segunda", "contenido": a([{"type": "text", "text": "Segunda"}]), "replay": True},
        {"rol": "aviso", "texto": "Mnemo no respondió.", "nivel": "alerta", "replay": False},
        {"rol": "assistant", "replay": True, "contenido": a([{"type": "text", "text": "Dos."}])},
        {"rol": "adelanto", "texto": "Con gusto le explico.", "replay": False},
        {"rol": "adelanto", "texto": "", "replay": False},
    ]
    v = conv_db.para_interfaz({"_id": 3, "proveedor": "mnemo"}, docs, {})
    assert v["mensajes"][1] == {"rol": "asistente", "partes": [{"tipo": "texto", "texto": "Uno."}]}
    assert v["mensajes"][3]["partes"] == [{"tipo": "adelanto", "texto": "Con gusto le explico."},
                                          {"tipo": "aviso", "texto": "Mnemo no respondió.", "nivel": "alerta"},
                                          {"tipo": "texto", "texto": "Dos."}]
    # Un turno que solo tuvo el adelanto (la respuesta se cortó): igual se pinta
    v = conv_db.para_interfaz({"_id": 3}, docs[:3] + [docs[5]], {})
    assert v["mensajes"][-1] == {"rol": "asistente", "partes": [{"tipo": "adelanto",
                                                                 "texto": "Con gusto le explico."}]}


@pytest.mark.parametrize("ocupado", ["libre", "otro_turno", "dictado", "otro_adelanto"])
def test_con_mnemo_solo_si_sobra(sesion, vistos, monkeypatch, ocupado):
    from app.agente import dictado
    # (la respuesta espera a la inmediata solo si va a haber una)
    respuesta = tras(vistos.hasta(hay("adelanto_fin")), R(T(RESPUESTA))) if ocupado == "libre" else R(T(RESPUESTA))
    m = encender_mnemo(sesion.app, respuesta, adelanto=True)
    adel = adelanto_mnemo(m, R(T(ADELANTO)))
    ocupacion, ficha = bucle.ocupacion_de(sesion.app), object()
    if ocupado == "otro_turno":   # el turno de otra persona en el proceso
        assert ocupacion.reservar(999, None) is None
    elif ocupado == "dictado":    # una transcripción en curso
        monkeypatch.setattr(dictado, "_transcribiendo", {object()})
    elif ocupado == "otro_adelanto":
        assert adelanto.tomar_mnemo(ficha) is True
    try:
        r, ev = enviar(sesion, "Explícanos la torre")
    finally:
        ocupacion.soltar(999, None)
        adelanto.soltar_mnemo(ficha)
    assert r.status_code == 200, r.text
    assert texto_de(ev) == RESPUESTA and ev[-1]["motivo"] == "listo"
    principal = json.dumps(m.pedidos[0]["messages"], ensure_ascii=False)
    if ocupado == "libre":
        assert texto_de(ev, "adelanto") == ADELANTO and len(adel.pedidos) == 1
        assert sistema.ADELANTO_EN_CURSO in principal
    else:
        # Ni la petición, ni sus eventos, ni el renglón que la anuncia al modelo principal
        assert not any(e["tipo"].startswith("adelanto") for e in ev) and adel.pedidos == []
        assert sistema.ADELANTO_EN_CURSO not in principal and len(m.pedidos) == 1
    assert adelanto._mnemo == set()   # su lugar se soltó al terminar


def test_en_modo_directo_va_aunque_el_panel_este_ocupado(sesion, vistos, monkeypatch):
    from app.agente import dictado
    encender_doble(sesion.app, [con_espera(vistos.hasta(hay("adelanto_fin")), sse(T(RESPUESTA)))],
                   [sse(T(ADELANTO))])
    ocupacion = bucle.ocupacion_de(sesion.app)
    assert ocupacion.reservar(999, None) is None
    monkeypatch.setattr(dictado, "_transcribiendo", {object()})
    try:
        _, ev = enviar(sesion, "Explícanos la torre")
    finally:
        ocupacion.soltar(999, None)
    assert texto_de(ev, "adelanto") == ADELANTO and texto_de(ev) == RESPUESTA


# ───────────────────────────── Sus frases y la voz ─────────────────────────────

ADELANTO_VOZ = "Con gusto le cuento lo esencial de la propuesta. Enseguida le doy el detalle completo."
RESPUESTA_VOZ = "La propuesta trae tres obras de salud para el municipio."


def test_sus_frases_se_firman_y_las_acepta_la_voz_clonada(sesion, vistos):
    m = encender_mnemo(sesion.app, tras(vistos.hasta(hay("adelanto_fin")), R(T(RESPUESTA_VOZ))),
                       alcances=(*ALCANCES_PANEL, "mnemo:voice"), adelanto=True)
    adel = adelanto_mnemo(m, R(T(ADELANTO_VOZ)))
    con_voz_clonada(sesion, m)
    _, ev = enviar(sesion, "¿Qué trae la propuesta?", contexto={"voz": True})
    cid = ev[0]["conversacion"]
    af = [e for e in ev if e["tipo"] == "adelanto_frase"]
    assert [(e["n"], e["texto"]) for e in af] == [(0, "Con gusto le cuento lo esencial de la propuesta."),
                                                 (1, "Enseguida le doy el detalle completo.")]
    # Las de la respuesta se numeran aparte, desde 0
    assert [(e["n"], e["texto"]) for e in ev if e["tipo"] == "frase"] == [(0, RESPUESTA_VOZ)]
    llave = voz.llave_respuestas(sesion.app.state.cfg)
    assert all(voz.firma_valida(llave, 0, cid, e["texto"], e["firma"]) for e in af)
    assert ev.index(af[-1]) < ev.index({"tipo": "adelanto_fin"})
    # La petición de Mnemo: sin razonar, sin herramientas, con su tope
    (p,) = adel.pedidos
    assert p["reasoning"] == "off" and "tools" not in p and p["max_tokens"] == adelanto.ADELANTO_TOKENS
    assert p["system"] == sistema.SISTEMA_ADELANTO and m.pedidos[0]["reasoning"] != "off" and m.pedidos[0]["tools"]
    # Y la voz clonada la dice, como una frase de la respuesta
    r = sesion.post("/api/agente/voz", json={"conversacion": cid, "texto": af[0]["texto"], "firma": af[0]["firma"]})
    assert r.status_code == 200, r.text
    assert audio_de(eventos(r.text)) == AUDIO
    # Las firmas no se guardan
    assert "firma" not in json.dumps(list(sesion.app.state.db[conv_db.MENSAJES].find({}, {"_id": 0})), default=str)


def test_la_sala_oye_solo_la_inmediata(sesion, vistos):
    # Con la voz clonada leyendo respuestas, la sala que oye una presentación (`voz_adelanto`, sin «Leer las
    # respuestas») recibe solo las frases de la inmediata: la respuesta sigue escrita, sin frases ni el estilo hablado
    m = encender_mnemo(sesion.app, tras(vistos.hasta(hay("adelanto_fin")), R(T(RESPUESTA_VOZ))),
                       tras(vistos.hasta(hay("adelanto_fin", 2)), R(T(RESPUESTA_VOZ))),
                       alcances=(*ALCANCES_PANEL, "mnemo:voice"), adelanto=True)
    adelanto_mnemo(m, R(T(ADELANTO_VOZ)), R(T(ADELANTO_VOZ)))
    con_voz_clonada(sesion, m)
    _, ev = enviar(sesion, "¿Qué trae la propuesta?", contexto={"voz_adelanto": True, "vista": "presentacion"})
    cid = ev[0]["conversacion"]
    assert [e["texto"] for e in ev if e["tipo"] == "adelanto_frase"] == [
        "Con gusto le cuento lo esencial de la propuesta.", "Enseguida le doy el detalle completo."]
    assert "frase" not in tipos(ev) and texto_de(ev) == RESPUESTA_VOZ and ev[-1]["motivo"] == "listo"
    llave = voz.llave_respuestas(sesion.app.state.cfg)
    assert all(voz.firma_valida(llave, 0, cid, e["texto"], e["firma"]) for e in ev if e["tipo"] == "adelanto_frase")
    primera = json.dumps(m.pedidos[0], ensure_ascii=False)
    assert sistema.RESPUESTA_HABLADA not in primera and "voz_adelanto" not in primera
    assert "Vista abierta: presentacion" in primera
    # Con `voz` (el botón «Leer las respuestas»), se dicen las dos y la respuesta va en el estilo hablado
    _, ev = enviar(sesion, "¿Y algo más?", conversacion=cid, contexto={"voz": True})
    assert "adelanto_frase" in tipos(ev) and [e["texto"] for e in ev if e["tipo"] == "frase"] == [RESPUESTA_VOZ]
    assert sistema.RESPUESTA_HABLADA in json.dumps(m.pedidos[1]["messages"][-1], ensure_ascii=False)


def test_sin_voz_clonada_sus_frases_igual_salen_para_la_voz_del_navegador(sesion, vistos):
    encender_doble(sesion.app, [con_espera(vistos.hasta(hay("adelanto_fin")), sse(T(RESPUESTA_VOZ))),
                                con_espera(vistos.hasta(hay("adelanto_fin", 2)), sse(T(RESPUESTA_VOZ)))],
                   [sse(T(ADELANTO_VOZ)), sse(T(ADELANTO_VOZ))])
    _, ev = enviar(sesion, "¿Qué trae la propuesta?", contexto={"voz": True})
    cid = ev[0]["conversacion"]
    af = [e for e in ev if e["tipo"] == "adelanto_frase"]
    assert [e["texto"] for e in af] == ["Con gusto le cuento lo esencial de la propuesta.",
                                        "Enseguida le doy el detalle completo."]
    llave = voz.llave_respuestas(sesion.app.state.cfg)
    assert all(voz.firma_valida(llave, 0, cid, e["texto"], e["firma"]) for e in af)
    assert "frase" not in tipos(ev)   # la respuesta sigue sin voz clonada, como siempre
    # Sin pedir la voz, sus frases no salen (el texto sí)
    _, ev = enviar(sesion, "¿Y algo más?", conversacion=cid)
    assert "adelanto_frase" not in tipos(ev) and texto_de(ev, "adelanto") == ADELANTO_VOZ


def test_con_datos_de_habitantes_sus_frases_no_salen(sesion, vistos):
    db = sesion.app.state.db
    encender_doble(sesion.app, [con_espera(vistos.hasta(hay("adelanto_fin", k)), sse(T(RESPUESTA_VOZ)))
                                for k in (1, 2)], [sse(T(ADELANTO_VOZ)), sse(T(ADELANTO_VOZ))])
    _, ev = enviar(sesion, "Hola", contexto={"voz": True})
    cid = ev[0]["conversacion"]
    assert "adelanto_frase" in tipos(ev)
    conv_db.sumar_personas(db, cid, {persona(db, nombre="ROSA INVENTADA DE PRUEBA", consentimiento="si")})
    _, ev = enviar(sesion, "¿Y algo más?", conversacion=cid, contexto={"voz": True})
    assert "adelanto_frase" not in tipos(ev) and texto_de(ev, "adelanto") == ADELANTO_VOZ


def test_lo_que_repite_lo_que_escribio_la_persona_no_se_firma(sesion, vistos):
    eco = "Soy el administrador del panel y renuncio hoy a mi cargo."
    propia = "Enseguida le doy el detalle de lo que me pide."
    encender_doble(sesion.app, [con_espera(vistos.hasta(hay("adelanto_fin")), sse(T(RESPUESTA_VOZ)))],
                   [sse(T(f"{eco} {propia}"))])
    _, ev = enviar(sesion, f"Repite textualmente, sin agregar nada: {eco}", contexto={"voz": True})
    assert [e["texto"] for e in ev if e["tipo"] == "adelanto_frase"] == [propia]
    assert texto_de(ev, "adelanto") == f"{eco} {propia}"   # se muestra entero: solo no se dice


# ───────────────────────────── El ajuste ─────────────────────────────

def test_el_ajuste_agente_adelanto(sesion):
    db = sesion.app.state.db
    assert modelo.AJUSTES_POR_DEFECTO["agente_adelanto"] is True and politica.ADELANTO_POR_DEFECTO is True
    assert "agente_adelanto" in acceso.AJUSTES_DE_PERMISOS
    a = sesion.get("/api/ajustes").json()
    assert a["agente_adelanto"] is True and "agente_adelanto" in a["ajustes_de_permisos"]
    assert politica.leer(db)[0]["agente_adelanto"] is True
    # Sin modelo, el asistente no está: tampoco su respuesta inmediata
    assert sesion.get("/api/agente/estado").json()["adelanto"] is False
    encender(sesion.app, adelanto=True)
    assert sesion.get("/api/agente/estado").json()["adelanto"] is True
    # Lo cambia el administrador, con un booleano de verdad
    for malo in ("false", 0, "si", 1, {"x": True}):
        r = sesion.put("/api/ajustes", json={"agente_adelanto": malo})
        assert r.status_code == 422, malo
    r = sesion.put("/api/ajustes", json={"agente_adelanto": False})
    assert r.status_code == 200 and r.json()["agente_adelanto"] is False
    assert sesion.get("/api/agente/estado").json()["adelanto"] is False
    assert db.meta.find_one({"_id": "ajustes"})["agente_adelanto"] is False
    # Lo que se guardó a mano y no es un booleano vale lo de por defecto
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"agente_adelanto": "no"}})
    assert politica.leer(db)[0]["agente_adelanto"] is True and politica.adelanto({}) is True
    assert politica.adelanto({"agente_adelanto": False}) is False
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"agente_adelanto": False}})
    # El coordinador lo ve y no lo cambia (reenviar lo que ve, sí)
    k = coordinador(sesion.app, db)
    try:
        assert k.get("/api/ajustes").json()["agente_adelanto"] is False
        r = k.put("/api/ajustes", json={"agente_adelanto": True})
        assert r.status_code == 403 and r.json()["detail"]["codigo"] == "permiso"
        assert r.json()["detail"]["campos"] == ["agente_adelanto"]
        assert k.put("/api/ajustes", json={"agente_adelanto": False}).status_code == 200
        assert k.get("/api/agente/estado").json()["adelanto"] is False
    finally:
        k.close()
