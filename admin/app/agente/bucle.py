"""El turno del asistente: del mensaje de la persona (o de su aprobación) a los eventos NDJSON del navegador.

Cómo corre un turno (docs/agente.md):

* Antes de abrir el flujo, `abrir_mensaje` y `abrir_confirmacion` responden con JSON normal lo que impide el turno:
  sin clave (503), rol apagado (403), conversación ajena o inexistente (404), larga u ocupada (409), sin pendientes
  (409) o el tope diario de mensajes (429). Ahí también se toman los candados: uno por persona y por conversación en
  este proceso (`Ocupacion`, con un tope de turnos a la vez) y el de MongoDB (`ocupada_hasta`, que vale entre
  procesos y vence solo).
* El turno corre en una tarea propia (el productor) que escribe eventos en una cola; la respuesta (`Turno.eventos`)
  los lee y, si en 15 s no llega nada, manda un `latido`. Si el navegador se desconecta, Starlette cancela la respuesta:
  se cancela la tarea, el `async with` cierra el flujo del SDK y el productor suelta los candados y cierra la API
  interna. Solo se guardan mensajes completos: lo que el modelo estaba escribiendo se pierde.
* Una ronda es una petición al modelo. El productor emite `progreso`, `texto` y `herramienta inicio` mientras llega,
  guarda el mensaje del asistente al final y ejecuta las herramientas en orden: las de lectura e interfaz en el acto;
  las de escritura quedan pendientes de aprobación (`confirmar`) y el turno termina hasta que la persona decide.
* Nada lanza fuera del flujo una vez abierto: cualquier fallo sale como `error` + `fin`, y al registro va solo el tipo
  de la excepción (nunca datos de personas ni lo que escribió el modelo).
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
import threading
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Awaitable, Callable

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from pymongo.errors import ConnectionFailure

from .. import db as bd
from ..seguridad import SIN_BASE
from . import conversaciones as conv_db
from . import llm, politica, sistema
from .herramientas.base import (Confirmacion, Contexto, ErrorHerramienta, Herramienta, Resultado,
                                errores_de_validacion)
from .interno import ApiInterna

log = logging.getLogger("panel")

MAX_RONDAS = 12
TOPE_TURNO_S = 240.0         # pasado esto no empieza otra ronda (la que va termina): `fin pasos`
TOPE_ABSOLUTO_S = 600.0      # un turno nunca dura más que esto (el candado de MongoDB vence a los 11 min)
PLAZO_HERRAMIENTA_S = 60.0
PLAZO_MNEMO_S = 20.0
# Lo que suman las imágenes (en base64) de los resultados de una ronda: van en un solo mensaje guardado en MongoDB,
# que no admite documentos de más de 16 MB
TOPE_IMAGENES = 8_000_000
LATIDO_S = 15.0
ESPERA_ARRANQUE_S = 30.0     # si la respuesta no empieza a leerse en este tiempo, el turno no corre
REINTENTOS = 2
ESPERA_REINTENTO_S = 0.5
TURNOS_POR_PROCESO = 4
ACCIONES = frozenset({"navegar", "recargar", "insignias", "mapa"})
FLUJO = {"X-Accel-Buffering": "no", "Cache-Control": "no-store"}

RECHAZADA = "La persona rechazó esta acción: no la vuelvas a proponer salvo que lo pida."
NO_APROBADA = "La persona no aprobó esta acción: escribió otro mensaje. No la vuelvas a proponer salvo que lo pida."
INTERRUMPIDA = ("Interrumpida: el turno se cortó y esta herramienta no devolvió resultado. Si todavía hace falta, "
                "vuelve a llamarla.")
SIN_EJECUTAR = "No se ejecutó: el turno terminó por un error anterior."
CORTADA = "No ejecutada: la entrada se cortó por max_tokens. Reintenta con una entrada más corta."
AVISO_RECHAZO = "El asistente no puede continuar con esta solicitud. Puede reformularla o pedir otra cosa."
AVISO_LARGA = "La conversación ya es muy larga: empiece una nueva para seguir."
AVISO_CORTADA = "La respuesta se cortó por larga. Pida que continúe o que lo resuma."
OCUPADA = {"codigo": "ocupada", "mensaje": "El asistente todavía está respondiendo otro mensaje suyo. Espere a que "
                                          "termine."}
SATURADO = {"codigo": "saturado", "mensaje": "El asistente está atendiendo muchas conversaciones a la vez. Intente de "
                                            "nuevo en unos segundos."}


class FinDelTurno(Exception):
    """Un final previsto del turno con un mensaje para la persona (un fallo del modelo, una herramienta fatal…)."""

    def __init__(self, mensaje: str, codigo: str):
        super().__init__(mensaje)
        self.mensaje, self.codigo = mensaje, codigo


# ───────────────────────────── Turnos en curso en este proceso ─────────────────────────────

class Ocupacion:
    """Un turno a la vez por persona y por conversación, y como mucho `maximo` turnos a la vez en el proceso (cada
    uno retiene una conexión con el navegador y otra con Anthropic). Complementa el candado de MongoDB, que es el que
    vale entre procesos. Lo protege un candado de hilos: las pruebas atienden peticiones desde varios bucles."""

    def __init__(self, maximo: int = TURNOS_POR_PROCESO):
        self.maximo = maximo
        self._candado = threading.Lock()
        self.usuarios: set = set()
        self.conversaciones: set = set()

    def reservar(self, uid: Any, cid: int | None) -> str | None:
        """None si quedó reservado; si no, «ocupada» (esa persona o conversación ya tiene turno) o «saturado»."""
        with self._candado:
            if uid in self.usuarios or (cid is not None and cid in self.conversaciones):
                return "ocupada"
            if len(self.usuarios) >= self.maximo:
                return "saturado"
            self.usuarios.add(uid)
            if cid is not None:
                self.conversaciones.add(cid)
            return None

    def agregar(self, cid: int) -> None:
        """La conversación nueva que acaba de recibir su id (su dueño ya está reservado)."""
        with self._candado:
            self.conversaciones.add(cid)

    def ocupada(self, cid: int) -> bool:
        with self._candado:
            return cid in self.conversaciones

    def soltar(self, uid: Any, cid: int | None) -> None:
        with self._candado:
            self.usuarios.discard(uid)
            self.conversaciones.discard(cid)


_CREAR = threading.Lock()
_TAREAS: set[asyncio.Task] = set()  # referencia fuerte a los productores: asyncio solo guarda una débil


def ocupacion_de(app: Any) -> Ocupacion:
    with _CREAR:
        o = getattr(app.state, "agente_ocupacion", None)
        if o is None:
            o = app.state.agente_ocupacion = Ocupacion()
        return o


# ───────────────────────────── Utilidades ─────────────────────────────

def linea(ev: dict) -> bytes:
    """Un evento como una línea NDJSON (nunca vacía: un trozo vacío no pasa por los middleware)."""
    return (json.dumps(ev, ensure_ascii=False, separators=(",", ":"), default=str) + "\n").encode("utf-8", "replace")


LATIDO = linea({"tipo": "latido"})


def _corto(v: Any, n: int = 200) -> str:
    return " ".join(v.split())[:n] if isinstance(v, str) else ""


def _resultado(tid: str, contenido: Any, error: bool = False) -> dict:
    r = {"type": "tool_result", "tool_use_id": tid, "content": contenido}
    if error:
        r["is_error"] = True
    return r


def _imagenes(imgs: Any) -> list[dict]:
    """Solo bloques `image` con fuente: lo demás no se le manda al modelo (sería un 400)."""
    return [i for i in imgs if isinstance(i, dict) and i.get("type") == "image" and isinstance(i.get("source"), dict)
            ] if isinstance(imgs, list) else []


def _acciones(acciones: Any) -> list[dict]:
    out = []
    for a in acciones if isinstance(acciones, list) else []:
        if isinstance(a, dict) and a.get("tipo") in ACCIONES:
            out.append(a)
        else:
            log.warning("Asistente: se descartó una acción del navegador sin tipo válido")
    return out


def _personas(ids: Any) -> set[int]:
    return {p for p in ids if isinstance(p, int) and not isinstance(p, bool) and p > 0} if isinstance(
        ids, (set, list, tuple, frozenset)) else set()


def _plazo(h: Herramienta) -> float:
    """El plazo de una herramienta. Las de Mnemo llevan el suyo (una escritura puede gastar modelo en Mnemo y pasar de
    60 s) más el `initialize` que puede tocar en la primera llamada: cortarlas antes las cancelaría a medias allá."""
    if h.nombre_remoto:
        from . import mnemo_cliente as mc
        return (mc.PLAZO_ESCRITURA_S if h.tipo == "escritura" else mc.PLAZO_LECTURA_S) + mc.PLAZO_CATALOGO_S + 5
    return PLAZO_HERRAMIENTA_S


def _entrada_pendiente(h: Herramienta, args: Any, crudo: Any) -> Any:
    """La entrada de una escritura pendiente tal como quedó después de `confirmar` (lleva las huellas de lo que mostró
    la tarjeta, con las que la herramienta detecta cambios entre la tarjeta y la aprobación), si vuelve a validar. Si
    no, la que mandó el modelo."""
    try:
        d = args.model_dump(mode="json")
        h.validar(d)
        return d
    except Exception:  # noqa: BLE001 - se guarda la entrada original
        return crudo


def _personas_de_entrada(args: Any) -> set[int]:
    """Las personas que nombra la entrada de una escritura: la tarjeta de confirmación pudo mostrar sus datos."""
    ids = {getattr(args, "persona_id", None)}
    ids |= set(getattr(args, "persona_ids", None) or [])
    return _personas(ids)


def _tarjeta(conf: Confirmacion) -> dict:
    t = conf.para_interfaz()
    return {"titulo": _corto(t.get("titulo"), 200) or "Confirmar acción",
            "detalle": [[_corto(k, 80), str(v)[:500]] for k, v in list(t.get("detalle") or [])[:30]],
            "aviso": _corto(t.get("aviso"), 500) or None}


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _aviso_respaldo(bloque: dict) -> str:
    destino = _corto(str((bloque.get("to") or {}).get("model") or ""), 60) or "otro modelo"
    return f"El asistente pasó a un modelo de respaldo ({destino}) para seguir con la respuesta."


class _Notas:
    """Notas de progreso de un bloque `thinking` (con `display: "updates"`): se emiten según llegan, salvo el texto
    fijo que reemplaza trabajo cortado (`llm.CENTINELA`), que no es una nota para la persona."""

    def __init__(self) -> None:
        self.emitido = 0

    def delta(self, acumulado: str) -> str:
        if llm.CENTINELA.startswith(acumulado):
            return ""  # todavía puede ser el centinela: se espera
        nuevo, self.emitido = acumulado[self.emitido:], len(acumulado)
        return nuevo

    def cerrar(self, completo: str) -> str:
        if completo == llm.CENTINELA:
            return ""
        resto, self.emitido = completo[self.emitido:], len(completo)
        return resto


# ───────────────────────────── El turno ─────────────────────────────

class Turno:
    """Un turno de una persona en una conversación: el productor (`_correr`) y la respuesta (`eventos`)."""

    def __init__(self, *, app: Any, quien: Any, ajustes: dict, agente: dict, api: ApiInterna, conv: dict | None,
                 cid: int, titulo: str, turno: str, limite: dict | None):
        self.app, self.db, self.cfg = app, app.state.db, app.state.cfg
        self.quien, self.ajustes, self.agente, self.api = quien, ajustes, agente, api
        self.conv, self.cid, self.titulo, self.turno, self.limite = conv, cid, titulo, turno, limite
        self.cola: asyncio.Queue = asyncio.Queue()
        self.arrancado = asyncio.Event()
        self.tarea: asyncio.Task | None = None
        self.ocupacion = ocupacion_de(app)
        self.cliente = None
        self.mnemo = None
        self.herramientas: dict[str, Herramienta] = {}
        self.permitidas: set[str] = set()
        self.definiciones: list[dict] = []
        self.sistema: list[dict] = []
        self.expira = None
        self.tokens = int((conv or {}).get("tokens_ultima") or 0)
        self.imagenes_ronda = 0  # base64 de imágenes en los resultados de la ronda en curso (TOPE_IMAGENES)

    # ── El productor y la respuesta ──
    def lanzar(self, trabajo: Callable[[], Awaitable[str]]) -> None:
        t = asyncio.create_task(self._correr(trabajo))
        _TAREAS.add(t)
        t.add_done_callback(_TAREAS.discard)
        self.tarea = t

    def emitir(self, ev: dict) -> None:
        self.cola.put_nowait(ev)

    async def eventos(self) -> AsyncIterator[bytes]:
        """El cuerpo de la respuesta: los eventos del productor y un latido cada `LATIDO_S` sin otros eventos."""
        self.arrancado.set()
        try:
            while True:
                try:
                    ev = await asyncio.wait_for(self.cola.get(), LATIDO_S)
                except TimeoutError:
                    yield LATIDO
                    continue
                if ev is None:
                    return
                try:
                    datos = linea(ev)
                except (TypeError, ValueError):
                    log.error("Asistente: un evento no se pudo convertir a JSON")
                    continue
                yield datos
        finally:
            # El navegador se fue (o la respuesta terminó): el productor no sigue gastando en un turno sin lector
            if self.tarea is not None and not self.tarea.done():
                self.tarea.cancel()

    async def _correr(self, trabajo: Callable[[], Awaitable[str]]) -> None:
        motivo, error = "error", None
        try:
            try:
                await asyncio.wait_for(self.arrancado.wait(), ESPERA_ARRANQUE_S)
            except TimeoutError:
                return  # nadie leyó la respuesta (el navegador se fue antes de empezar): se sueltan los candados
            async with asyncio.timeout(TOPE_ABSOLUTO_S):
                motivo = await trabajo()
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            error = ("El turno tardó demasiado y se cortó. Intente de nuevo.", "plazo")
        except FinDelTurno as e:
            error = (e.mensaje, e.codigo)
        except ConnectionFailure as e:
            self.app.state.cortacircuitos.fallo(e)
            error = (SIN_BASE, "base")
        except Exception as e:  # noqa: BLE001 - nada sale del flujo: se avisa y se cierra
            log.error("Asistente: el turno falló (%s)", type(e).__name__)
            error = ("El asistente falló al responder. Intente de nuevo.", "error")
        finally:
            # Primero los candados: cuando el navegador ve `fin`, ya puede mandar otro mensaje
            await self._soltar()
            if error is not None:
                self.emitir({"tipo": "error", "mensaje": error[0], "codigo": error[1]})
                motivo = "error"
            fin: dict[str, Any] = {"tipo": "fin", "motivo": motivo}
            if self.limite:
                fin["limite"] = self.limite
            self.emitir(fin)
            self.cola.put_nowait(None)

    async def _soltar(self) -> None:
        if self.expira is not None:
            try:
                # Si el administrador bajó la retención mientras corría el turno, lo guardado en él venía con el plazo
                # viejo (se leyó al empezar): se vuelve a fijar con el vigente
                _, agente = await run_in_threadpool(politica.leer, self.db)
                if agente["retencion_dias"] < self.agente["retencion_dias"]:
                    await run_in_threadpool(conv_db.renovar, self.db, self.cid, agente["retencion_dias"])
            except Exception as e:  # noqa: BLE001 - el próximo turno lo vuelve a fijar
                log.warning("Asistente: no se pudo revisar la retención al terminar (%s)", type(e).__name__)
        try:
            await run_in_threadpool(conv_db.soltar, self.db, self.cid, self.turno)
        except Exception as e:  # noqa: BLE001 - el candado de MongoDB vence solo
            log.warning("Asistente: no se pudo soltar la conversación (%s)", type(e).__name__)
        self.ocupacion.soltar(self.quien.uid, self.cid)
        try:
            await self.api.cerrar()
        except Exception as e:  # noqa: BLE001
            log.warning("Asistente: no se pudo cerrar la API interna (%s)", type(e).__name__)

    # ── Preparación ──
    async def _crear(self) -> str | None:
        """Crea la conversación con su `system` y sus herramientas congeladas. Devuelve un aviso si Mnemo falló."""
        from . import herramientas as registro
        from . import mnemo_cliente
        from .herramientas import mnemo as hmnemo
        ofrecidas = list(registro.para(self.quien, self.agente, self.cfg))
        defs_mnemo, de_mnemo, instrucciones, aviso = [], [], None, None
        try:
            cliente = (mnemo_cliente.cliente_de(self.app, self.cfg)
                       if hmnemo.disponible_para(self.quien, self.agente, self.cfg) else None)
            if cliente is not None:
                defs_mnemo = list(await asyncio.wait_for(
                    hmnemo.definiciones(cliente, self.cfg.mnemo_herramientas), PLAZO_MNEMO_S) or [])
                json.dumps(defs_mnemo)  # se guardan con la conversación: tienen que ser JSON de verdad
                de_mnemo = [h for h in hmnemo.desde_definiciones(defs_mnemo)
                            if politica.ofrecida(h, self.quien, self.agente, self.cfg)]
                instrucciones = getattr(cliente, "instrucciones", None)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - sin Mnemo la conversación sigue
            log.warning("Asistente: Mnemo no respondió al crear la conversación (%s)", type(e).__name__)
            defs_mnemo, de_mnemo, instrucciones = [], [], None
            if isinstance(e, ErrorHerramienta) and e.codigo == "mnemo_token":
                # El administrador tiene que cambiar el token: el mensaje lo dice (nunca lleva el token)
                aviso = f"{e.mensaje} Esta conversación sigue sin las herramientas de Mnemo."
            else:
                aviso = "Mnemo no respondió: esta conversación sigue sin sus herramientas."
        lista, defs = [], []
        for h in [*ofrecidas, *de_mnemo]:
            try:
                defs.append(h.definicion())
                lista.append(h)
            except Exception as e:  # noqa: BLE001 - una herramienta mal definida no impide conversar
                log.error("Asistente: la herramienta %s no tiene una definición válida (%s)", h.nombre,
                          type(e).__name__)
        texto = sistema.texto(self.quien, lista, instrucciones if de_mnemo else None)
        self.conv = await run_in_threadpool(conv_db.crear, self.db, self.cid, self.quien.uid, self.titulo, texto, defs,
                                            defs_mnemo, self.agente["retencion_dias"], self.turno,
                                            self.cfg.agente_modelo)
        self.expira = self.conv["expira"]
        return aviso

    def _preparar(self) -> None:
        """Las herramientas de la conversación (las congeladas, rehechas por nombre con el código vigente) y cuáles se
        permiten hoy: los permisos y los ajustes pudieron cambiar desde que se creó."""
        from . import herramientas as registro
        from .herramientas import mnemo as hmnemo
        self.cliente = llm.cliente(self.app, self.cfg)
        self.sistema = llm.sistema_para_peticion(self.conv["sistema"])
        self.definiciones = conv_db.de_json(self.conv.get("herramientas"), [])
        nombres = [d.get("name") for d in self.definiciones if isinstance(d, dict)]
        fijas = registro.por_nombre()
        de_mnemo: dict[str, Herramienta] = {}
        defs_mnemo = conv_db.de_json(self.conv.get("mnemo"), [])
        if defs_mnemo:
            try:
                de_mnemo = {h.nombre: h for h in hmnemo.desde_definiciones(defs_mnemo)}
            except Exception as e:  # noqa: BLE001 - la conversación sigue sin Mnemo
                log.warning("Asistente: no se pudieron rehacer las herramientas de Mnemo (%s)", type(e).__name__)
        self.herramientas = {n: fijas.get(n) or de_mnemo[n] for n in nombres if n in fijas or n in de_mnemo}
        self.permitidas = {h.nombre for h in registro.para(self.quien, self.agente, self.cfg)}
        if de_mnemo:
            try:
                from . import mnemo_cliente
                if hmnemo.disponible_para(self.quien, self.agente, self.cfg):
                    self.mnemo = mnemo_cliente.cliente_de(self.app, self.cfg)
            except Exception as e:  # noqa: BLE001 - sus herramientas quedan sin permiso en este turno
                log.warning("Asistente: Mnemo no está disponible (%s)", type(e).__name__)
                self.mnemo = None
            if self.mnemo is not None:
                self.permitidas |= {n for n, h in de_mnemo.items()
                                    if politica.ofrecida(h, self.quien, self.agente, self.cfg)}

    def _contexto(self, tid: str) -> Contexto:
        return Contexto(quien=self.quien, db=self.db, cfg=self.cfg, app=self.app, api=self.api, ajustes=self.ajustes,
                        conversacion_id=self.cid, tool_use_id=tid, mnemo=self.mnemo)

    async def _guardar(self, rol: str, contenido: Any = None, replay: bool = True, tokens: int | None = None,
                       **campos: Any) -> None:
        try:
            await run_in_threadpool(conv_db.guardar, self.db, self.cid, self.quien.uid, self.expira, rol, contenido,
                                    replay, campos, tokens)
        except conv_db.ConversacionBorrada:
            raise FinDelTurno("La conversación se borró mientras el asistente respondía.", "borrada") from None

    async def _avisar(self, texto: str, nivel: str, emitir: bool = True) -> None:
        """Un aviso para la persona (y en el historial, para que se vea igual al reabrir la conversación)."""
        if emitir:
            self.emitir({"tipo": "aviso", "texto": texto, "nivel": nivel})
        await self._guardar("aviso", replay=False, texto=texto, nivel=nivel)

    def _herramienta(self, tid: str, nombre: str, etiqueta: str, estado: str, resumen: str | None = None) -> None:
        ev = {"tipo": "herramienta", "id": tid, "nombre": nombre, "etiqueta": etiqueta, "estado": estado}
        if resumen is not None:
            ev["resumen"] = resumen
        self.emitir(ev)

    # ── Trabajo de cada ruta ──
    async def mensaje(self, texto: str, contexto: Any) -> str:
        """Un mensaje nuevo de la persona: lo pendiente queda rechazado y un `tool_use` sin resultado, interrumpido."""
        self.emitir({"tipo": "inicio", "conversacion": self.cid, "titulo": self.titulo})
        aviso = None
        if self.conv is None:
            aviso = await self._crear()
        else:
            self.expira = await run_in_threadpool(conv_db.renovar, self.db, self.cid, self.agente["retencion_dias"])
        self._preparar()
        historial = await run_in_threadpool(conv_db.historial, self.db, self.cid)
        pend, crudo = conv_db.pendiente_de(self.conv), self.conv.get("pendiente")
        if pend is not None:
            # Primero se quita lo pendiente y después se guardan sus resultados: si algo se corta en el medio, el
            # siguiente turno ve un `tool_use` sin resultado (interrumpido) y nunca dos resultados para el mismo
            if not await run_in_threadpool(conv_db.quitar_pendiente, self.db, self.cid, crudo):
                raise FinDelTurno("Otro turno atendió lo pendiente de esta conversación. Intente de nuevo.", "ocupada")
            bloques, ui = self._rechazar(pend, NO_APROBADA)
        else:
            bloques, ui = self._interrumpidas(historial)
        bloques = conv_db.limpio(bloques + [{"type": "text", "text": sistema.contexto_del_panel(contexto, _ahora())},
                                            {"type": "text", "text": texto}])
        await self._guardar("user", bloques, texto=texto, herramientas=ui)
        historial.append({"role": "user", "content": bloques})
        if aviso:
            await self._avisar(aviso, "alerta")
        return await self._rondas(historial)

    async def confirmacion(self, decisiones: dict[str, bool]) -> str:
        """Las decisiones de la persona sobre lo pendiente: lo aprobado se ejecuta (con su clave de idempotencia), lo
        rechazado o sin decisión vuelve como rechazo, y el bucle sigue con todos los resultados en un mensaje."""
        self.emitir({"tipo": "inicio", "conversacion": self.cid, "titulo": self.titulo})
        self.expira = await run_in_threadpool(conv_db.renovar, self.db, self.cid, self.agente["retencion_dias"])
        self._preparar()
        pend, crudo = conv_db.pendiente_de(self.conv), self.conv.get("pendiente")
        if pend is None:
            raise FinDelTurno("No hay acciones pendientes en esta conversación.", "sin_pendientes")
        historial = await run_in_threadpool(conv_db.historial, self.db, self.cid)
        resultados = {r.get("tool_use_id"): r for r in pend.get("resultados") or [] if isinstance(r, dict)}
        ui = {h.get("id"): h for h in pend.get("ui") or [] if isinstance(h, dict)}
        fatal: ErrorHerramienta | None = None
        self.imagenes_ronda = 0
        for ll in pend["llamadas"]:
            tid, nombre = str(ll.get("id")), str(ll.get("nombre"))
            etiqueta = ll.get("etiqueta") or nombre
            if fatal is not None:
                resultados[tid] = _resultado(tid, ErrorHerramienta(SIN_EJECUTAR, "sin_ejecutar").para_modelo(), True)
                ui[tid] = {"id": tid, "estado": "error", "resumen": "No se ejecutó"}
                self._herramienta(tid, nombre, etiqueta, "error", "No se ejecutó")
            elif decisiones.get(tid) is True:
                bloque, estado, resumen, fatal = await self._aprobada(ll)
                resultados[tid], ui[tid] = bloque, {"id": tid, "estado": estado, "resumen": resumen}
            else:
                resultados[tid] = _resultado(tid, RECHAZADA, True)
                ui[tid] = {"id": tid, "estado": "rechazada", "resumen": "Rechazada"}
                self._herramienta(tid, nombre, etiqueta, "rechazada", "Rechazada")
        orden = [i for i in pend.get("orden") or [] if i in resultados]
        bloques = conv_db.limpio([resultados[i] for i in orden] + [r for i, r in resultados.items() if i not in orden])
        if not await run_in_threadpool(conv_db.quitar_pendiente, self.db, self.cid, crudo):
            raise FinDelTurno("Otro turno atendió lo pendiente de esta conversación.", "sin_pendientes")
        await self._guardar("user", bloques, herramientas=list(ui.values()))
        historial.append({"role": "user", "content": bloques})
        if fatal is not None:
            raise FinDelTurno(fatal.mensaje, fatal.codigo)
        return await self._rondas(historial)

    def _rechazar(self, pend: dict, motivo: str) -> tuple[list[dict], list[dict]]:
        """Los resultados de lo pendiente cuando la persona no lo aprobó: los listos tal cual y el resto rechazado."""
        resultados = {r.get("tool_use_id"): r for r in pend.get("resultados") or [] if isinstance(r, dict)}
        ui = [h for h in pend.get("ui") or [] if isinstance(h, dict)]
        for ll in pend["llamadas"]:
            tid = str(ll.get("id"))
            resultados[tid] = _resultado(tid, motivo, True)
            ui.append({"id": tid, "estado": "rechazada", "resumen": "No aprobada"})
            self._herramienta(tid, str(ll.get("nombre")), ll.get("etiqueta") or str(ll.get("nombre")), "rechazada",
                              "No aprobada")
        orden = [i for i in pend.get("orden") or [] if i in resultados]
        return [resultados[i] for i in orden] + [r for i, r in resultados.items() if i not in orden], ui

    @staticmethod
    def _interrumpidas(historial: list[dict]) -> tuple[list[dict], list[dict]]:
        """Resultados «interrumpido» para los `tool_use` del último mensaje del asistente que no tienen resultado (un
        turno cortado): la API exige un resultado por cada uno antes del mensaje nuevo."""
        if not historial or historial[-1]["role"] != "assistant":
            return [], []
        usos = [b for b in historial[-1]["content"] if isinstance(b, dict) and b.get("type") == "tool_use"]
        return ([_resultado(str(u.get("id")), INTERRUMPIDA, True) for u in usos],
                [{"id": str(u.get("id")), "estado": "error", "resumen": "Interrumpida"} for u in usos])

    # ── Las rondas ──
    async def _rondas(self, historial: list[dict]) -> str:
        reloj = asyncio.get_running_loop()
        inicio, rondas, reintentos = reloj.time(), 0, 0
        while True:
            if rondas >= MAX_RONDAS or (rondas and reloj.time() - inicio >= TOPE_TURNO_S):
                return "pasos"
            if self.tokens > conv_db.TOPE_TOKENS:
                await self._avisar(AVISO_LARGA, "alerta")
                return "pasos"
            anunciadas: list[tuple[str, str, str]] = []
            try:
                msg = await self._pedir(historial, anunciadas)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 - se decide abajo: repetir la ronda o cerrar con un error claro
                if llm.reintentable(e) and reintentos < REINTENTOS:
                    reintentos += 1
                    log.warning("Asistente: se repite la ronda (%s)", type(e).__name__)
                    self.emitir({"tipo": "descartar"})
                    await asyncio.sleep(ESPERA_REINTENTO_S * 2 ** reintentos)
                    continue
                log.warning("Asistente: falló la petición al modelo (%s)", type(e).__name__)
                raise FinDelTurno(*llm.explicar(e)) from None
            reintentos, rondas = 0, rondas + 1
            motivo = await self._cerrar_ronda(msg, historial, anunciadas)
            if motivo is not None:
                return motivo

    async def _pedir(self, historial: list[dict], anunciadas: list[tuple[str, str, str]]) -> Any:
        """Una petición al modelo en flujo: emite lo que llega y devuelve el mensaje completo."""
        kw: dict[str, Any] = {"system": self.sistema, "messages": llm.para_peticion(historial),
                              **llm.parametros(self.cfg)}
        if self.definiciones:
            kw["tools"] = self.definiciones
        notas: _Notas | None = None
        async with self.cliente.beta.messages.stream(**kw) as flujo:
            async for ev in flujo:
                t = ev.type
                if t == "text":
                    if ev.text:
                        self.emitir({"tipo": "texto", "texto": ev.text})
                elif t == "thinking":
                    nuevo = notas.delta(ev.snapshot) if notas is not None else ""
                    if nuevo:
                        self.emitir({"tipo": "progreso", "texto": nuevo})
                elif t == "content_block_start":
                    b = ev.content_block
                    if b.type == "thinking":
                        notas = _Notas()
                    elif b.type == "tool_use":
                        nombre = _corto(b.name, 64)
                        h = self.herramientas.get(b.name)
                        anunciadas.append((b.id, nombre, h.etiqueta if h else nombre))
                        self._herramienta(b.id, nombre, anunciadas[-1][2], "inicio")
                    elif b.type == "fallback":
                        self.emitir({"tipo": "aviso", "texto": _aviso_respaldo(b.to_dict()), "nivel": "info"})
                elif t == "content_block_stop":
                    b = ev.content_block
                    if b.type == "thinking" and notas is not None:
                        resto = notas.cerrar(b.thinking or "")
                        if resto:
                            self.emitir({"tipo": "progreso", "texto": resto})
                        notas = None
            return await flujo.get_final_message()

    async def _cerrar_ronda(self, msg: Any, historial: list[dict], anunciadas: list[tuple[str, str, str]]) -> str | None:
        """Guarda la ronda y ejecuta sus herramientas. Devuelve el motivo de fin, o None para seguir con otra."""
        contenido = conv_db.limpio(llm.reenviable([b.to_dict() for b in msg.content]))
        u = msg.usage
        entrada, salida = u.input_tokens or 0, u.output_tokens or 0
        lectura, escritura = u.cache_read_input_tokens or 0, u.cache_creation_input_tokens or 0
        self.tokens = entrada + lectura + escritura
        await run_in_threadpool(conv_db.sumar_uso, self.db, self.quien.uid, entrada, salida, lectura, escritura)
        meta = {"modelo": msg.model, "fin": msg.stop_reason,
                "uso": {"entrada": entrada, "salida": salida, "cache_lectura": lectura, "cache_escritura": escritura},
                "detalles": conv_db.a_json(msg.stop_details.to_dict()) if msg.stop_details else None,
                "transformaciones": conv_db.a_json([x.to_dict() for x in msg.input_transformations or []])}
        ids = {b.get("id") for b in contenido if b.get("type") == "tool_use"}
        for tid, nombre, etiqueta in anunciadas:
            if tid not in ids:  # quedó antes de un cambio de modelo: no se ejecuta
                self._herramienta(tid, nombre, etiqueta, "error", "Descartada")
        respaldos = [_aviso_respaldo(b) for b in contenido if b.get("type") == "fallback"]
        if msg.stop_reason == "refusal":
            # Solo para auditoría: no se reenvía (puede traer una herramienta a medias) y lo pintado se borra
            categoria = (msg.stop_details.to_dict() if msg.stop_details else {}).get("category")
            log.info("Asistente: el modelo no continuó (categoría %s)", categoria)
            await self._guardar("assistant", contenido, replay=False, **meta)
            self.emitir({"tipo": "descartar"})
            await self._avisar(AVISO_RECHAZO, "alerta")
            return "rechazo"
        await self._guardar("assistant", contenido, tokens=self.tokens, **meta)
        historial.append({"role": "assistant", "content": contenido})
        for texto in respaldos:  # ya se avisó al llegar el bloque: aquí queda en el historial
            await self._avisar(texto, "info", emitir=False)
        if msg.stop_reason == "pause_turn":
            return None  # herramienta del servidor en pausa: se reenvía tal cual
        usos = [b for b in contenido if b.get("type") == "tool_use"]
        if not usos or msg.stop_reason not in ("tool_use", "max_tokens", "model_context_window_exceeded"):
            if msg.stop_reason in ("max_tokens", "model_context_window_exceeded"):
                await self._avisar(AVISO_CORTADA, "info")
            return "listo"
        if msg.stop_reason == "tool_use":
            bloques, ui, llamadas, fatal = await self._ejecutar(usos)
        else:  # entrada cortada: el analizador tolerante da un objeto parcial «válido», que no se ejecuta
            bloques, ui, llamadas, fatal = {}, [], [], None
            for b in usos:
                bloques[b["id"]] = _resultado(b["id"], CORTADA, True)
                ui.append({"id": b["id"], "estado": "error", "resumen": "Entrada cortada"})
                h = self.herramientas.get(b.get("name"))
                self._herramienta(b["id"], _corto(b.get("name"), 64), h.etiqueta if h else _corto(b.get("name"), 64),
                                  "error", "Entrada cortada")
        orden = [b["id"] for b in usos]
        if llamadas:
            await run_in_threadpool(conv_db.poner_pendiente, self.db, self.cid, {
                "orden": orden, "resultados": [bloques[i] for i in orden if i in bloques], "ui": ui,
                "llamadas": llamadas})
            return "confirmacion"
        resultados = conv_db.limpio([bloques[i] for i in orden])
        await self._guardar("user", resultados, herramientas=ui)
        historial.append({"role": "user", "content": resultados})
        if fatal is not None:
            raise FinDelTurno(fatal.mensaje, fatal.codigo)
        return None

    # ── Las herramientas ──
    async def _ejecutar(self, usos: list[dict]) -> tuple[dict, list[dict], list[dict], ErrorHerramienta | None]:
        """Cada `tool_use` en orden: (resultados por id, estados para la interfaz, escrituras pendientes, error fatal).
        Tras un error fatal lo que queda no se ejecuta (y lo pendiente se descarta)."""
        bloques: dict[str, dict] = {}
        ui: list[dict] = []
        llamadas: list[dict] = []
        fatal: ErrorHerramienta | None = None
        self.imagenes_ronda = 0
        for u in usos:
            tid, nombre = str(u.get("id")), _corto(u.get("name"), 64)
            h = self.herramientas.get(u.get("name"))
            etiqueta = h.etiqueta if h else nombre
            if fatal is not None:
                bloque, estado, resumen = self._fallo(tid, nombre, etiqueta, ErrorHerramienta(SIN_EJECUTAR,
                                                                                             "sin_ejecutar"))[:3]
            elif h is None:
                bloque, estado, resumen = self._fallo(tid, nombre, etiqueta, ErrorHerramienta(
                    f"La herramienta «{nombre}» no existe en esta conversación.", "no_existe"))[:3]
            else:
                try:
                    args = h.validar(u.get("input"))
                except ValidationError as e:
                    bloque, estado, resumen = self._fallo(tid, nombre, etiqueta, ErrorHerramienta(
                        "La entrada no cumple el esquema de la herramienta: corrígela y vuelve a llamarla.",
                        "INVALID_JSON", detalle={"entrada": conv_db.a_json(u.get("input"))[:2000],
                                                 "errores": errores_de_validacion(e)[:20]}))[:3]
                except Exception as e:  # noqa: BLE001 - una entrada rara del modelo no tumba el turno
                    log.warning("Asistente: entrada no validable para %s (%s)", h.nombre, type(e).__name__)
                    bloque, estado, resumen = self._fallo(tid, nombre, etiqueta, ErrorHerramienta(
                        "La entrada de la herramienta no es válida.", "INVALID_JSON"))[:3]
                else:
                    if h.nombre not in self.permitidas:
                        bloque, estado, resumen = self._fallo(tid, nombre, etiqueta, ErrorHerramienta(
                            "Su rol o los ajustes del asistente ya no permiten esta herramienta.", "permiso"))[:3]
                    elif h.tipo == "escritura":
                        llamada, fallo = await self._preparar_escritura(h, tid, u, args)
                        if llamada is not None:
                            llamadas.append(llamada)
                            continue
                        bloque, estado, resumen, fatal = fallo
                    else:
                        bloque, estado, resumen, fatal = await self._correr_herramienta(h, tid, args)
            bloques[tid] = bloque
            ui.append({"id": tid, "estado": estado, "resumen": resumen})
        if fatal is not None and llamadas:
            for ll in llamadas:  # el turno termina: lo que esperaba aprobación tampoco se ejecuta
                bloques[ll["id"]] = self._fallo(ll["id"], ll["nombre"], ll["etiqueta"], ErrorHerramienta(
                    SIN_EJECUTAR, "sin_ejecutar"))[0]
                ui.append({"id": ll["id"], "estado": "error", "resumen": "No se ejecutó"})
            llamadas = []
        return bloques, ui, llamadas, fatal

    def _fallo(self, tid: str, nombre: str, etiqueta: str, e: ErrorHerramienta) -> tuple:
        resumen = _corto(e.mensaje) or "Falló"
        self._herramienta(tid, nombre, etiqueta, "error", resumen)
        return _resultado(tid, e.para_modelo(), True), "error", resumen, (e if e.fatal else None)

    async def _correr_herramienta(self, h: Herramienta, tid: str, args: Any) -> tuple:
        """Ejecuta una herramienta con plazo: (tool_result, estado, resumen, error fatal o None)."""
        try:
            res = await asyncio.wait_for(h.ejecutar(self._contexto(tid), args), _plazo(h))
            if not isinstance(res, Resultado):
                raise TypeError("la herramienta no devolvió un Resultado")
            texto = res.texto_para_modelo()
        except ErrorHerramienta as e:
            return self._fallo(tid, h.nombre, h.etiqueta, e)
        except TimeoutError:
            return self._fallo(tid, h.nombre, h.etiqueta, ErrorHerramienta(
                "La herramienta tardó demasiado en responder.", "plazo"))
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - el fallo vuelve al modelo como is_error
            log.error("Asistente: la herramienta %s falló (%s)", h.nombre, type(e).__name__)
            return self._fallo(tid, h.nombre, h.etiqueta, ErrorHerramienta(
                "La herramienta falló por un error interno del panel.", "error"))
        imagenes, omitidas = [], 0
        for img in _imagenes(res.imagenes):
            peso = len(str((img.get("source") or {}).get("data") or ""))
            if self.imagenes_ronda + peso > TOPE_IMAGENES:
                omitidas += 1
                continue
            self.imagenes_ronda += peso
            imagenes.append(img)
        if omitidas:
            texto += (f"\n[{omitidas} imagen(es) omitida(s): esta ronda ya llevaba demasiadas. Pídelas de a una en "
                      "otra llamada.]")
        personas = _personas(res.personas)
        if personas:
            await run_in_threadpool(conv_db.sumar_personas, self.db, self.cid, personas)
        resumen = _corto(res.resumen) or "Listo"
        self._herramienta(tid, h.nombre, h.etiqueta, "ok", resumen)
        for a in _acciones(res.acciones):
            self.emitir({"tipo": "accion", "accion": a})
        contenido: Any = [{"type": "text", "text": texto}, *imagenes] if imagenes else texto
        return _resultado(tid, contenido), "ok", resumen, None

    async def _preparar_escritura(self, h: Herramienta, tid: str, uso: dict, args: Any) -> tuple:
        """Arma la tarjeta de una escritura: (llamada pendiente, None) o (None, fallo) si `confirmar` falla."""
        try:
            conf = await asyncio.wait_for(h.confirmar(self._contexto(tid), args), PLAZO_HERRAMIENTA_S)
            if not isinstance(conf, Confirmacion):
                raise TypeError("confirmar no devolvió una Confirmacion")
            tarjeta = _tarjeta(conf)
        except ErrorHerramienta as e:
            return None, self._fallo(tid, h.nombre, h.etiqueta, e)
        except TimeoutError:
            return None, self._fallo(tid, h.nombre, h.etiqueta, ErrorHerramienta(
                "La herramienta tardó demasiado en preparar la acción.", "plazo"))
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.error("Asistente: la herramienta %s no pudo preparar la acción (%s)", h.nombre, type(e).__name__)
            return None, self._fallo(tid, h.nombre, h.etiqueta, ErrorHerramienta(
                "No se pudo preparar la acción por un error interno del panel.", "error"))
        personas = _personas_de_entrada(args)
        if personas:
            await run_in_threadpool(conv_db.sumar_personas, self.db, self.cid, personas)
        self._herramienta(tid, h.nombre, h.etiqueta, "pendiente")
        self.emitir({"tipo": "confirmar", "id": tid, "nombre": h.nombre, "etiqueta": h.etiqueta, **tarjeta})
        return {"id": tid, "nombre": h.nombre, "etiqueta": h.etiqueta,
                "entrada": conv_db.a_json(_entrada_pendiente(h, args, uso.get("input"))), "confirmacion": tarjeta}, None

    async def _aprobada(self, ll: dict) -> tuple:
        """Una escritura aprobada: se vuelven a comprobar los permisos (pudieron cambiar) y se ejecuta."""
        tid, nombre = str(ll.get("id")), _corto(ll.get("nombre"), 64)
        h = self.herramientas.get(ll.get("nombre"))
        etiqueta = h.etiqueta if h else (ll.get("etiqueta") or nombre)
        if h is None or h.tipo != "escritura" or h.nombre not in self.permitidas:
            return self._fallo(tid, nombre, etiqueta, ErrorHerramienta(
                "Su rol o los ajustes del asistente ya no permiten esta acción: no se ejecutó.", "permiso"))
        try:
            args = h.validar(conv_db.de_json(ll.get("entrada")))
        except Exception:  # noqa: BLE001 - la entrada guardada ya no cumple el esquema (cambió el código)
            return self._fallo(tid, nombre, etiqueta, ErrorHerramienta(
                "La acción ya no es válida: vuelve a prepararla.", "INVALID_JSON"))
        self._herramienta(tid, h.nombre, h.etiqueta, "aprobada")
        return await self._correr_herramienta(h, tid, args)


# ───────────────────────────── Apertura del turno (antes del flujo) ─────────────────────────────

def _respuesta(turno: Turno) -> StreamingResponse:
    return StreamingResponse(turno.eventos(), media_type="application/x-ndjson", headers=FLUJO)


def _reservar(app: Any, uid: Any, cid: int | None) -> None:
    motivo = ocupacion_de(app).reservar(uid, cid)
    if motivo == "saturado":
        raise HTTPException(503, dict(SATURADO), headers={"Retry-After": "5"})
    if motivo is not None:
        raise HTTPException(409, dict(OCUPADA))


async def _liberar(app: Any, uid: Any, cid: int | None, turno: str, tomada: bool) -> None:
    if tomada and cid is not None:
        try:
            await run_in_threadpool(conv_db.soltar, app.state.db, cid, turno)
        except Exception as e:  # noqa: BLE001 - vence solo
            log.warning("Asistente: no se pudo soltar la conversación (%s)", type(e).__name__)
    ocupacion_de(app).soltar(uid, cid)


async def abrir_mensaje(request: Any, quien: Any, cid: int | None, texto: str, contexto: Any) -> StreamingResponse:
    """POST /api/agente/mensajes: las comprobaciones previas y el turno en flujo."""
    app = request.app
    db, cfg = app.state.db, app.state.cfg
    ajustes, agente = await run_in_threadpool(politica.leer, db)
    politica.exigir(quien, cfg, agente)
    texto = conv_db.texto_valido(texto)
    conv = None
    if cid is not None:
        conv = await run_in_threadpool(conv_db.de_usuario, db, cid, quien.uid)
        if conv is None:
            raise HTTPException(404, {"codigo": "no_existe", "mensaje": "No existe esa conversación."})
        if conv_db.larga(conv):
            raise HTTPException(409, {"codigo": "larga", "mensaje": "La conversación es demasiado larga: empiece "
                                                                    "una nueva."})
    turno_id, tomada = secrets.token_hex(8), False
    _reservar(app, quien.uid, cid)
    try:
        if await run_in_threadpool(conv_db.otra_ocupada, db, quien.uid, cid):
            raise HTTPException(409, dict(OCUPADA))
        if conv is not None:
            conv = await run_in_threadpool(conv_db.tomar, db, cid, quien.uid, turno_id)
            if conv is None:
                raise HTTPException(409, dict(OCUPADA))
            tomada = True
            titulo = conv.get("titulo") or "Conversación"
        else:  # la conversación se crea al empezar el flujo (con Mnemo, si toca): aquí solo se reserva su id
            cid = await run_in_threadpool(bd.siguiente_id, db, conv_db.CONVERSACIONES)
            ocupacion_de(app).agregar(cid)
            tomada, titulo = True, conv_db.titulo_de(texto)
        maximo = politica.mensajes_diarios(ajustes, quien.rol)
        usados = await run_in_threadpool(conv_db.contar_mensaje, db, quien.uid, maximo)
        if usados is None:
            raise HTTPException(429, {"codigo": "volumen", "mensaje": f"Llegó al tope de {maximo} mensajes al "
                                                                      "asistente por hoy. Podrá seguir mañana."})
        turno = Turno(app=app, quien=quien, ajustes=ajustes, agente=agente, api=ApiInterna.desde_peticion(request),
                      conv=conv, cid=cid, titulo=titulo, turno=turno_id, limite={"usados": usados, "maximo": maximo})
        turno.lanzar(lambda: turno.mensaje(texto, contexto))
    except BaseException:
        await _liberar(app, quien.uid, cid, turno_id, tomada)
        raise
    return _respuesta(turno)


async def abrir_confirmacion(request: Any, quien: Any, cid: int, decisiones: dict[str, bool]) -> StreamingResponse:
    """POST /api/agente/confirmaciones: las comprobaciones previas y el turno que sigue tras la decisión."""
    app = request.app
    db, cfg = app.state.db, app.state.cfg
    ajustes, agente = await run_in_threadpool(politica.leer, db)
    politica.exigir(quien, cfg, agente)
    conv = await run_in_threadpool(conv_db.de_usuario, db, cid, quien.uid)
    if conv is None:
        raise HTTPException(404, {"codigo": "no_existe", "mensaje": "No existe esa conversación."})
    sin_pendientes = HTTPException(409, {"codigo": "sin_pendientes", "mensaje": "No hay acciones esperando su "
                                                                                 "aprobación en esta conversación."})
    if conv_db.pendiente_de(conv) is None:
        raise sin_pendientes
    turno_id, tomada = secrets.token_hex(8), False
    _reservar(app, quien.uid, cid)
    try:
        if await run_in_threadpool(conv_db.otra_ocupada, db, quien.uid, cid):
            raise HTTPException(409, dict(OCUPADA))
        conv = await run_in_threadpool(conv_db.tomar, db, cid, quien.uid, turno_id)
        if conv is None:
            raise HTTPException(409, dict(OCUPADA))
        tomada = True
        if conv_db.pendiente_de(conv) is None:  # otro turno lo atendió entre la lectura y el candado
            raise sin_pendientes
        maximo = politica.mensajes_diarios(ajustes, quien.rol)
        usados = await run_in_threadpool(conv_db.uso_de, db, quien.uid)
        turno = Turno(app=app, quien=quien, ajustes=ajustes, agente=agente, api=ApiInterna.desde_peticion(request),
                      conv=conv, cid=cid, titulo=conv.get("titulo") or "Conversación", turno=turno_id,
                      limite={"usados": usados, "maximo": maximo})
        turno.lanzar(lambda: turno.confirmacion(decisiones))
    except BaseException:
        await _liberar(app, quien.uid, cid, turno_id, tomada)
        raise
    return _respuesta(turno)
