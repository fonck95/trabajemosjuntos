"""La respuesta inmediata del asistente (el «adelanto», docs/agente.md, «La respuesta inmediata»): mientras el modelo
principal prepara la respuesta completa (o el plan de una presentación, que con el razonamiento puede tardar de veinte
segundos a más de un minuto), otra petición corta al mismo proveedor le dice a la persona, en una a tres frases, la
idea general de lo que preguntó y que el detalle viene enseguida. Así nadie espera en silencio.

Cómo corre (`bucle.Turno`):

* Solo en un mensaje nuevo (`POST /api/agente/mensajes`), nunca al aprobar o rechazar, y solo con `agente_adelanto`
  encendido en Ajustes → Asistente. Es una tarea aparte dentro del turno, a la par con la primera ronda del modelo
  principal: no la espera, no la frena y su fallo no la toca (se descarta en silencio: `adelanto_fin` con `vacio`, y al
  registro solo el tipo de la excepción).
* La petición (`Proveedor.generar(..., rapido=True)`): las instrucciones fijas de `sistema.SISTEMA_ADELANTO`, sin
  herramientas, sin razonar (o lo mínimo, si el modelo no deja apagarlo) y con `ADELANTO_TOKENS` de tope. Los mensajes
  (`mensajes`): los últimos `MENSAJES_MAX` de la conversación en texto plano (lo que escribió la persona, sin el
  contexto del panel de entonces, y el texto del asistente; sin herramientas, resultados, imágenes ni razonamiento) y
  el mensaje nuevo con su contexto del panel (así sabe si hay una presentación abierta).
* Los eventos, entre los del turno:
  - `{"tipo": "adelanto", "texto"}`: el texto, a trozos y en texto plano. Lo primero espera a tener `VISIBLE_MIN`
    caracteres (o el final), así la marca de «no hace falta» (`SALTO`, «—», o sus variantes) nunca se ve; después va
    palabra por palabra (lo que se muestra siempre termina en una palabra entera), sin las marcas de Markdown, y
    como mucho `ADELANTO_MAX` caracteres, cortado en el final de una frase.
  - `{"tipo": "adelanto_frase", "n", "texto", "firma"}`: sus frases para decir en voz alta, numeradas desde 0 aparte de
    las `frase` de la respuesta y firmadas igual (`voz.firmar`: `POST /api/agente/voz` las acepta tal cual), con el
    mismo filtro de eco y las mismas reglas de lo que se dice en voz alta (`voz.Frases`). Solo si el mensaje pidió la
    respuesta hablada (`contexto.voz`) o solo la inmediata hablada (`contexto.voz_adelanto`: la sala oye una
    presentación, y la respuesta sigue escrita) y la conversación no trae datos de habitantes: con la voz clonada si la
    hay y, si no, con la del navegador.
  - `{"tipo": "adelanto_fin"}` al terminar, o `{"tipo": "adelanto_fin", "vacio": true}` si no se mostró nada (la marca,
    un fallo, el plazo antes de mostrar algo o la carrera de abajo).
* La carrera (`principal_escribe`): si el modelo principal escribe antes de que el adelanto muestre algo, el adelanto
  se cancela (una respuesta rápida no lo necesita). Lo que ya empezó a mostrarse sigue hasta el final, como mucho
  `ADELANTO_S` desde que empezó; ahí se corta en lo que haya («…» si quedó a mitad de una frase). Si el turno termina
  antes y el adelanto no mostró nada, también se cancela.
* Lo mostrado se guarda con el turno (`guardar`: un mensaje `adelanto` que nunca se reenvía, `replay: False`, y que
  `conversaciones.para_interfaz` pinta arriba de la respuesta de ese turno): no entra en el historial del modelo
  principal, que sigue alternando y con el mismo prefijo para la caché.
* No es un turno: no cuenta en el tope diario de mensajes ni toma otro cupo. Sí gasta: una llamada corta más al modelo
  por pregunta. Sus tokens (y créditos de Mnemo) se suman al uso del día de la persona cuando la petición termina
  (también si contesta «—»); una que se corta a mitad (la carrera, el tope de lo que se muestra, el plazo o el fin del
  turno) no se suma, como una ronda cortada con «Detener», aunque el proveedor cobre lo que alcanzó a gastar.
* Con Mnemo, que deja pocas llamadas al modelo a la vez para todo el panel, solo va si sobra (`bucle.Turno`): el
  proceso no atiende el turno de otra persona ni transcribe un dictado, y no hay otra en curso (`tomar_mnemo`, una a
  la vez). Así nunca le quita el cupo a una respuesta.
* Termina de verdad solo si el modelo llegó a su final (`FINES_COMPLETOS`) y lo mostrado casa con lo que escribió: si
  no (el tope de tokens, un rechazo), lo que se retenía no se muestra y se cierra como cortado («…» o vacío).
"""
from __future__ import annotations

import asyncio
import logging
import re
import threading
from typing import Any, Awaitable, Callable

from . import sistema

log = logging.getLogger("panel")

ADELANTO_TOKENS = 300   # el tope de tokens de la petición (unas 45 palabras caben de sobra)
ADELANTO_MAX = 420      # lo que se muestra, en caracteres: se corta en el final de una frase
ADELANTO_S = 20.0       # lo que dura como mucho, desde que empieza
VISIBLE_MIN = 12        # lo que espera antes de mostrar algo: la marca de «no hace falta» nunca se ve
MENSAJES_MAX = 8        # los mensajes anteriores que lee (en texto plano)
TEXTO_MENSAJE_MAX = 1500  # de cada uno, en caracteres
ESPERA_CORTE_S = 3.0    # lo que el turno espera a que un adelanto cortado termine (y se guarde)
SALTO = "—"             # la marca de «no hace falta» que piden las instrucciones (`sistema.SISTEMA_ADELANTO`)
# Los `Respuesta.fin` de una petición que terminó de verdad: con otro (`max_tokens`, `refusal`…) lo que llegó quedó
# a medias y se cierra como cortado
FINES_COMPLETOS = ("end_turn", "stop_sequence")

CONTEXTO = "<contexto_del_panel>"
_RAYAS = "—–‐‑‒―-−"
_MARCA = re.compile(rf"^[\s{_RAYAS}]+")                  # la marca (y los blancos) al comienzo
_SIN_MARKDOWN = str.maketrans("", "", "*#`")             # se muestra como texto plano
_FIN_FRASE = re.compile(r"[.?!…][)\]»\"'”’]*")
_TERMINADA = re.compile(r"[.?!…][)\]»\"'”’]*\s*$")
_BLANCOS = re.compile(r"\s")


# Las respuestas inmediatas con Mnemo en curso en el proceso (como mucho `MNEMO_A_LA_VEZ`): Mnemo deja pocas llamadas
# al modelo a la vez para todo el panel, y la respuesta inmediata nunca le quita una a una respuesta
MNEMO_A_LA_VEZ = 1
_mnemo: set[object] = set()
_candado = threading.Lock()


def tomar_mnemo(ficha: object) -> bool:
    """Toma el lugar de una respuesta inmediata con Mnemo, sin esperar: False si ya hay `MNEMO_A_LA_VEZ` en curso."""
    with _candado:
        if len(_mnemo) >= MNEMO_A_LA_VEZ:
            return False
        _mnemo.add(ficha)
        return True


def soltar_mnemo(ficha: object) -> None:
    with _candado:
        _mnemo.discard(ficha)


def _tipo(e: BaseException) -> str:
    """Para el registro: el tipo de la excepción y, si lo tiene, su código estable (nunca su mensaje)."""
    codigo = getattr(e, "codigo", None)
    return f"{type(e).__name__} {codigo}" if isinstance(codigo, str) else type(e).__name__


# ───────────────────────────── Los mensajes de la petición ─────────────────────────────

def _acotar(t: str) -> str:
    return t if len(t) <= TEXTO_MENSAJE_MAX else t[:TEXTO_MENSAJE_MAX - 1].rstrip() + "…"


def _textos(contenido: Any, rol: str) -> str:
    """El texto plano de un mensaje guardado: sus bloques `text` (de la persona, sin el contexto del panel)."""
    if isinstance(contenido, str):
        partes = [contenido]
    elif isinstance(contenido, list):
        partes = [b["text"] for b in contenido if isinstance(b, dict) and b.get("type") == "text"
                  and isinstance(b.get("text"), str)]
    else:
        partes = []
    if rol == "user":
        partes = [t for t in partes if not t.lstrip().startswith(CONTEXTO)]
    return "\n\n".join(t.strip() for t in partes if t.strip())


def mensajes(historial: list[dict], contexto_panel: str, texto: str) -> list[dict]:
    """Los mensajes de la petición: los últimos `MENSAJES_MAX` del historial que tienen texto (la persona sin el
    contexto del panel de entonces; el asistente sin herramientas ni razonamiento), cada uno acotado a
    `TEXTO_MENSAJE_MAX`, y el mensaje nuevo con su contexto del panel. Empieza por la persona y los roles se alternan
    (dos seguidos del mismo rol se juntan)."""
    previos: list[tuple[str, str]] = []
    for m in historial if isinstance(historial, list) else []:
        rol = m.get("role") if isinstance(m, dict) else None
        if rol in ("user", "assistant"):
            t = _textos(m.get("content"), rol)
            if t:
                previos.append((rol, _acotar(t)))
    previos = previos[-MENSAJES_MAX:]
    while previos and previos[0][0] != "user":
        previos.pop(0)
    salida: list[dict] = []
    nuevo = [{"type": "text", "text": contexto_panel}, {"type": "text", "text": texto}]
    for rol, bloques in [*((r, [{"type": "text", "text": t}]) for r, t in previos), ("user", nuevo)]:
        if salida and salida[-1]["role"] == rol:
            salida[-1]["content"].extend(bloques)
        else:
            salida.append({"role": rol, "content": list(bloques)})
    return salida


# ───────────────────────────── Lo que se muestra ─────────────────────────────

def _limpio(crudo: str) -> str:
    """El texto como se muestra: sin las marcas de Markdown ni la marca de «no hace falta» (o blancos) al comienzo.
    Solo crece cuando llega más texto (lo ya limpio no cambia)."""
    return _MARCA.sub("", crudo.translate(_SIN_MARKDOWN))


def _hasta_palabra(s: str) -> str:
    """`s` hasta su última palabra entera, sin el blanco que la sigue: la que está llegando puede crecer. Solo crece
    cuando `s` crece."""
    ultimo = max((m.start() for m in _BLANCOS.finditer(s)), default=-1)
    return s[:ultimo].rstrip() if ultimo >= 0 else ""


def _recortar(limpio: str, mostrado: int) -> str:
    """`limpio` (de más de `ADELANTO_MAX` caracteres) cortado en el último final de frase que cabe y no deja atrás lo
    ya mostrado (`mostrado` caracteres); si no hay, en la última palabra entera, con «…»."""
    fin = None
    for m in _FIN_FRASE.finditer(limpio, 0, ADELANTO_MAX):
        k = m.end()
        if k >= max(mostrado, 1) and limpio[k:k + 1].isspace():
            fin = k
    if fin is not None:
        return limpio[:fin]
    k = limpio.rfind(" ", mostrado, ADELANTO_MAX)
    cola = limpio[mostrado:k] if k >= mostrado else limpio[mostrado:ADELANTO_MAX - 1]
    return limpio[:mostrado] + cola.rstrip() + "…"


# ───────────────────────────── La respuesta inmediata de un turno ─────────────────────────────

class Adelanto:
    """La respuesta inmediata de un turno. `bucle.Turno` la arma con su proveedor, los mensajes (`mensajes`), su
    `emitir`, las frases para decir en voz alta (una `voz.Frases` propia, o None) y `guardar(texto, uso)`, que guarda lo
    mostrado con el turno y suma el uso; la lanza (`correr`, en una tarea propia que queda en `tarea`), le avisa cuando
    el modelo principal escribe (`principal_escribe`) y al terminar la espera (`esperar`) o la corta (`cortar`)."""

    def __init__(self, proveedor: Any, mensajes_: list[dict], emitir: Callable[[dict], None], frases: Any = None,
                 guardar: Callable[[str, Any], Awaitable[None]] | None = None):
        self.proveedor, self.mensajes, self._emitir = proveedor, mensajes_, emitir
        self.frases, self._guardar = frases, guardar
        self.crudo = ""          # lo que llegó del modelo
        self.texto = ""          # lo que ya se mostró (`adelanto`)
        self.visible = False     # ya se mostró algo
        self.terminado = False   # ya se emitió `adelanto_fin`
        self.desfasado = False   # un `texto_ronda` que no empieza por lo mostrado: no se agrega nada más
        self.uso: Any = None     # el uso de la petición, si terminó
        self.tarea: asyncio.Task | None = None      # `correr` (la lanza el turno)
        self.peticion: asyncio.Future | None = None  # la llamada al proveedor, dentro de `correr`

    # ── El flujo ──
    async def correr(self) -> None:
        """La petición (en su propia tarea, `peticion`: el tope de lo que se muestra y `cortar` la cancelan sin tocar
        esta), con su plazo; después guarda lo mostrado y el uso. Nunca lanza, salvo que se cancele esta tarea."""
        self.peticion = asyncio.ensure_future(self.proveedor.generar(
            sistema.SISTEMA_ADELANTO, self.mensajes, [], max_tokens=ADELANTO_TOKENS, esfuerzo="low",
            al_evento=self._al_evento, rapido=True))
        try:
            hechas, _ = await asyncio.wait([self.peticion], timeout=ADELANTO_S)
        except asyncio.CancelledError:
            self.peticion.cancel()
            raise
        if not hechas:  # el plazo: se corta en lo que haya
            self.peticion.cancel()
            self._cerrar(cortado=True)
        elif self.peticion.cancelled():  # la cortó el turno o el tope de lo que se muestra: ya se cerró
            self._cerrar(cortado=True)
        elif self.peticion.exception() is not None:
            log.warning("Asistente: la respuesta inmediata falló (%s)", _tipo(self.peticion.exception()))
            self._cerrar(cortado=True)
        else:
            r = self.peticion.result()
            self.uso = getattr(r, "uso", None)
            # Terminó de verdad solo si el modelo llegó a su final y lo mostrado casa con lo que escribió; si no (el
            # tope de tokens, un rechazo, un `texto_ronda` que no casa), lo que se retenía (la palabra que estaba
            # llegando) no se muestra y se cierra como cortado: «…» si quedó a mitad de una frase, o vacío
            completa = getattr(r, "fin", None) in FINES_COMPLETOS and not self.desfasado
            if not self.terminado and completa:
                try:
                    self._avanzar(final=True)
                except Exception as e:  # noqa: BLE001
                    log.warning("Asistente: la respuesta inmediata falló al mostrarse (%s)", _tipo(e))
            self._cerrar(cortado=not completa)
        await self._guardado()

    async def _guardado(self) -> None:
        if self._guardar is None or not (self.visible or self.uso is not None):
            return
        try:
            await self._guardar(self.texto if self.visible else "", self.uso)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - no se guarda, y el turno sigue
            log.warning("Asistente: no se pudo guardar la respuesta inmediata (%s)", _tipo(e))

    def _al_evento(self, ev: Any) -> None:
        if self.terminado or self.desfasado or not isinstance(ev, dict):
            return
        tipo, t = ev.get("tipo"), ev.get("texto")
        if not isinstance(t, str):
            return
        if tipo == "texto":
            self.crudo += t
        elif tipo == "texto_ronda":  # (Mnemo) el texto entero de la ronda, que reemplaza lo que llegó
            if self.visible and not _limpio(t).startswith(self.texto):
                self.desfasado = True  # lo mostrado no se puede retirar: queda como está
                return
            self.crudo = t
        else:  # el razonamiento, los avisos y las herramientas no se muestran
            return
        try:
            lleno = self._avanzar(final=False)
        except Exception as e:  # noqa: BLE001
            log.warning("Asistente: la respuesta inmediata falló al mostrarse (%s)", _tipo(e))
            self._cerrar(cortado=True)
            lleno = True
        if lleno and self.peticion is not None and not self.peticion.done():
            self.peticion.cancel()  # ya no hace falta lo que siga escribiendo

    def _avanzar(self, final: bool) -> bool:
        """Muestra lo nuevo que se puede mostrar. True si llegó al tope (y quedó cerrado)."""
        limpio = _limpio(self.crudo)
        destino = limpio.rstrip() if final else _hasta_palabra(limpio)
        lleno = len(limpio) > ADELANTO_MAX
        if lleno:
            destino = _recortar(limpio, len(self.texto))
        if not self.visible and not lleno:
            if not any(c.isalnum() for c in destino):
                return False  # la marca de «no hace falta», o todavía nada
            if not final and len(destino) < VISIBLE_MIN:
                return False
        nuevo = destino[len(self.texto):] if destino.startswith(self.texto) else ""
        if nuevo and any(c.isalnum() for c in destino):
            # (lo primero que se muestra va sin blancos al comienzo; lo que sigue, con el que separa las palabras)
            self.texto = destino
            self.visible = True
            self._emitir({"tipo": "adelanto", "texto": nuevo})
            self._frases("agregar", nuevo)
        if lleno:
            self._cerrar(cortado=False)
        return lleno

    def _frases(self, metodo: str, *args: Any) -> None:
        """Las frases para decir en voz alta (si las hay), como `adelanto_frase`. Un fallo deja el adelanto sin voz."""
        if self.frases is None:
            return
        try:
            for ev in getattr(self.frases, metodo)(*args):
                if isinstance(ev, dict) and ev.get("tipo") == "frase":
                    self._emitir({**ev, "tipo": "adelanto_frase"})
        except Exception as e:  # noqa: BLE001
            log.warning("Asistente: las frases de la respuesta inmediata fallaron (%s)", _tipo(e))
            self.frases = None

    def _cerrar(self, cortado: bool) -> None:
        """`adelanto_fin` (una sola vez): vacío si no se mostró nada; si no, con la última frase dicha. `cortado`: el
        plazo, un fallo o el turno lo cortaron a mitad (si quedó a mitad de una frase, termina en «…»)."""
        if self.terminado:
            return
        self.terminado = True
        if not self.visible:
            self._emitir({"tipo": "adelanto_fin", "vacio": True})
            return
        if cortado and not _TERMINADA.search(self.texto):
            self.texto += "…"
            self._emitir({"tipo": "adelanto", "texto": "…"})
            self._frases("agregar", "…")
        self._frases("cerrar_ronda")
        self._emitir({"tipo": "adelanto_fin"})

    # ── Lo que hace el turno ──
    def principal_escribe(self) -> None:
        """El modelo principal empezó a escribir: si el adelanto todavía no mostró nada, ya no hace falta."""
        if not self.visible and not self.terminado:
            self.cortar()

    def cortar(self) -> None:
        """Lo cierra con lo que se mostró (o vacío) y cancela la petición si sigue (`correr` termina y guarda lo
        mostrado)."""
        self._cerrar(cortado=True)
        if self.peticion is not None and not self.peticion.done():
            self.peticion.cancel()

    async def esperar(self, plazo: float = ADELANTO_S + ESPERA_CORTE_S) -> None:
        """Espera a que termine (y se guarde). Lo que no mostró nada todavía se corta: el turno ya respondió."""
        if self.tarea is None:
            return
        if not self.visible:
            self.cortar()
        await asyncio.wait([self.tarea], timeout=plazo)
        if not self.tarea.done():
            self.cortar()
            await asyncio.wait([self.tarea], timeout=ESPERA_CORTE_S)
