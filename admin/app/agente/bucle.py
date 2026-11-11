"""El turno del asistente: del mensaje de la persona (o de su aprobación) a los eventos NDJSON del navegador.

Cómo corre un turno (docs/agente.md):

* Antes de abrir el flujo, `abrir_mensaje` y `abrir_confirmacion` responden con JSON normal lo que impide el turno:
  sin modelo (503), rol apagado (403), conversación ajena o inexistente (404), larga, ocupada o de un proveedor que ya
  no está (409), sin pendientes o con decisiones sobre algo que ya no está pendiente (409) o el tope diario de mensajes
  (429: cuenta cada turno, también aprobar o rechazar). Ahí también se elige el proveedor del modelo
  (`proveedores.py`: Mnemo o Anthropic; el de una conversación existente es el suyo, congelado) y se toman los
  candados: uno por persona y por conversación en este proceso (`Ocupacion`, con un tope de turnos a la vez) y el de
  MongoDB (`ocupada_hasta`, que vale entre procesos: el turno lo renueva mientras corre y, si el proceso muere, vence
  solo en un minuto y medio). Si los tiene un turno que sigue vivo, 409 en el acto; solo se espera unos segundos a que
  se suelten si el turno anterior se está cerrando, como tras «Detener» (`_ocupar`).
* El turno corre en una tarea propia (el productor) que escribe eventos en una cola; la respuesta (`Turno.eventos`)
  los lee y, si en 15 s no llega nada, manda un `latido`. Si el navegador se desconecta, Starlette cancela la respuesta:
  se marca el turno como «cerrándose» (`Ocupacion.cerrar`), se cancela la tarea, la petición al modelo se corta (el
  flujo del SDK o la llamada a Mnemo) y el productor suelta los candados, lo primero, y cierra la API interna. Solo se
  guardan mensajes completos: lo que el modelo estaba escribiendo se pierde.
* Una ronda es una petición al modelo (`Proveedor.generar`). El productor emite `progreso`, `texto` (y, con Mnemo,
  `texto_ronda`) y `herramienta inicio` mientras llega, guarda el mensaje del asistente al final y ejecuta las
  herramientas en orden (como mucho `MAX_HERRAMIENTAS_RONDA` por ronda): las de lectura e interfaz en el acto; las
  de escritura quedan pendientes de aprobación (`confirmar`, con los valores enteros y solo si se ven como se van a
  escribir) y el turno termina hasta que la persona decide. Un fallo pasajero repite la ronda (`descartar`) tras la
  espera que dice el proveedor, si cabe en el tope del turno.
* Nada lanza fuera del flujo una vez abierto: cualquier fallo sale como `error` + `fin`, y al registro va solo el tipo
  de la excepción (nunca datos de personas ni lo que escribió el modelo).
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
import threading
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Awaitable, Callable

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from pymongo.errors import ConnectionFailure

from .. import db as bd
from ..seguridad import SIN_BASE
from . import conversaciones as conv_db
from . import politica, proveedores, sistema
# El plazo de una herramienta del panel es uno solo: el de `herramientas/base.py` (con él calcula una escritura cuánto
# le queda, `Contexto.plazo_escritura`)
from .herramientas.base import (PLAZO_HERRAMIENTA_S, Confirmacion, Contexto, ErrorHerramienta, Herramienta, Resultado,
                                errores_de_validacion)
from .interno import ApiInterna

log = logging.getLogger("panel")

MAX_RONDAS = 12
TOPE_TURNO_S = 240.0         # pasado esto no empieza otra ronda (la que va termina): `fin pasos`
TOPE_ABSOLUTO_S = 600.0      # un turno nunca dura más que esto
RENOVAR_S = 20.0             # cada cuánto renueva el turno su candado de MongoDB (vence en `conv_db.ARRIENDO`)
PLAZO_MNEMO_S = 20.0
# Lo que suman las imágenes (en base64) de los resultados de una ronda: van en un solo mensaje guardado en MongoDB,
# que no admite documentos de más de 16 MB (y cada proveedor tiene además su tope: `Proveedor.tope_imagenes`)
TOPE_IMAGENES = 8_000_000
# Lo que acumula una conversación: todo el historial se reenvía en cada ronda. Con más de 20 imágenes la API exige
# dimensiones menores a cada una (y Mnemo las da de hasta 8000 px), y cada petición tiene un tope de tamaño
TOPE_IMAGENES_CONVERSACION = 20_000_000
MAX_IMAGENES_CONVERSACION = 20
# Una respuesta del modelo no vuelca la base: herramientas por ronda y caracteres de resultados que se le pasan al
# modelo en un turno (con 40 000 por resultado, unas cinco lecturas grandes)
MAX_HERRAMIENTAS_RONDA = 8
TOPE_RESULTADOS_TURNO = 200_000
# La tarjeta de aprobación muestra los valores enteros: lo que no cabe no se ofrece (el texto más largo que escribe
# una herramienta del panel es la descripción de una reunión, de 4000). Las etiquetas también van enteras: en Mnemo
# son los nombres de los argumentos que se mandan
TARJETA_VALOR = 4_000
TARJETA_FILAS = 40
TARJETA_ETIQUETA = 80
# Cómo marca una herramienta lo que su tarjeta no muestra entero (Mnemo, en `herramientas/mnemo.py`: un valor largo
# termina en «… (N caracteres en total)» y los argumentos de más van en una fila «…»): esa tarjeta tampoco se ofrece
_RECORTADO = re.compile(r"…\s*\(\d+ caracteres en total\)\s*$")
# Ni la que no se vería como se va a escribir (`_se_ve_como_es`): un dato con caracteres invisibles o que cambian cómo
# se ve el resto (de formato, como las marcas de dirección o el espacio de ancho cero; de control, salvo el tabulador
# y los saltos de línea; los separadores de línea y de párrafo, los sustitutos sueltos, los sin asignar, los de uso
# privado, los rellenos que se ven como nada y los demás que Unicode da por ignorables, que el navegador pinta sin
# ancho) o con una tirada que esconde el final: más de TARJETA_SALTOS saltos de línea seguidos (aunque haya espacios en
# el medio), TARJETA_ESPACIOS espacios seguidos o más de TARJETA_MARCAS marcas apiladas sobre una letra
TARJETA_SALTOS = 3
TARJETA_ESPACIOS = 20
TARJETA_MARCAS = 4
_INVISIBLES = frozenset({"Cf", "Cs", "Cn", "Co", "Zl", "Zp"})
_RELLENOS = frozenset("\u034f\u115f\u1160\u2800\u3164\uffa0")
# Los ignorables por defecto de Unicode (Default_Ignorable_Code_Point) que no son de formato ni rellenos: las vocales
# inherentes jemer, los selectores de Mongolia y los de variante (VS1–VS256, con la etiqueta y los reservados del plano
# 14). Un selector de texto o de emoji (VS15, VS16) vale solo uno y justo tras un símbolo (un emoji: «❤️») o en un
# keycap («1️⃣»): tras una letra o un dígito no cambia nada de lo que se ve
_IGNORABLES = re.compile("[\u17b4\u17b5\u180b-\u180f\ufe00-\ufe0f\U000e0000-\U000e0fff]")
_DE_EMOJI = frozenset("\ufe0e\ufe0f")
_KEYCAP, _ENCIERRA_KEYCAP = frozenset("0123456789#*"), "\u20e3"
_TIRADA = re.compile(rf"(?:[^\S\r\n]*(?:\r\n?|\n)){{{TARJETA_SALTOS + 1},}}|[^\S\r\n]{{{TARJETA_ESPACIOS},}}")
LATIDO_S = 15.0
ESPERA_ARRANQUE_S = 30.0     # si la respuesta no empieza a leerse en este tiempo, el turno no corre
# Un turno nuevo que encuentra a la persona o la conversación con un turno que se está cerrando (tras «Detener», el
# turno cortado tarda un momento en soltar sus candados) o con el candado de MongoDB de otro proceso espera hasta esto
# a que se suelte, probando cada tanto (`_ocupar`)
ESPERA_OCUPADA_S = 5.0
SONDEO_OCUPADA_S = 0.1
# Un «no» que llega mientras una herramienta lee (`Turno._anotar`) se busca desde que empezó, con este margen: MongoDB
# guarda las fechas en milisegundos y otro proceso tiene su propio reloj
MARGEN_OLVIDO = timedelta(seconds=2)
REINTENTOS = 2               # repeticiones de una ronda tras fallos pasajeros (cuáles y cuánto esperar: el proveedor)
TURNOS_POR_PROCESO = 4
# Cómo termina una ronda que se cortó: con `tool_use` no se ejecuta (la entrada puede estar a medias), sin él se avisa
CORTES = frozenset({"max_tokens", "model_context_window_exceeded", "other"})
ACCIONES = frozenset({"navegar", "recargar", "insignias", "mapa", "presentacion"})
FLUJO = {"X-Accel-Buffering": "no", "Cache-Control": "no-store"}

RECHAZADA = "La persona rechazó esta acción: no la vuelvas a proponer salvo que lo pida."
NO_APROBADA = "La persona no aprobó esta acción: escribió otro mensaje. No la vuelvas a proponer salvo que lo pida."
INTERRUMPIDA = ("Interrumpida: el turno se cortó y esta herramienta no devolvió resultado. Si todavía hace falta, "
                "vuelve a llamarla.")
INTERRUMPIDA_ESCRITURA = ("Interrumpida: el turno se cortó y esta escritura no devolvió resultado. Puede que ya se "
                          "haya hecho: verifícalo (por ejemplo, leyendo la ficha o la reunión) antes de volver a "
                          "proponerla.")
DEMASIADAS = (f"No se ejecutó: una ronda admite como mucho {MAX_HERRAMIENTAS_RONDA} herramientas. Si todavía hace "
              "falta, llámala en la ronda siguiente.")
TOPE_TURNO = ("No se te pasó el resultado: en este turno ya se leyó mucha información. Responde con lo que ya tienes; "
              "si hace falta más, que la persona lo pida en otro mensaje, mejor acotado (filtros o una página).")
NO_CABE = ("No se puede proponer así: la tarjeta de aprobación muestra entero lo que se va a escribir y esto no cabe "
           f"(un dato de más de {format(TARJETA_VALOR, ',').replace(',', '.')} caracteres o más de {TARJETA_FILAS} "
           "datos). Divídelo en partes o acórtalo.")
OCULTO = ("No se puede proponer así: la tarjeta de aprobación tiene que mostrar lo que se va a escribir tal como es, y "
          "un dato trae caracteres invisibles o de control, o muchos saltos de línea, espacios o acentos seguidos, que "
          "esconderían o cambiarían parte del texto. Escríbelo sin ellos; si vienen de la ficha, que la persona lo "
          "corrija en el panel.")
MNEMO_YA_NO = "Su rol o los ajustes del asistente ya no permiten las herramientas de Mnemo."
SIN_EJECUTAR = "No se ejecutó: el turno terminó por un error anterior."
CORTADA = "No ejecutada: la entrada se cortó por max_tokens. Reintenta con una entrada más corta."
INCOMPLETA = ("No ejecutada: la respuesta del modelo terminó antes de tiempo y la entrada puede estar incompleta. Si "
              "todavía hace falta, vuelve a llamarla.")
AVISO_RECHAZO = "El asistente no puede continuar con esta solicitud. Puede reformularla o pedir otra cosa."
AVISO_LARGA = "La conversación ya es muy larga: empiece una nueva para seguir."
AVISO_CORTADA = "La respuesta se cortó por larga. Pida que continúe o que lo resuma."
AVISO_INCOMPLETA = "La respuesta del modelo terminó antes de tiempo. Pida que continúe o intente de nuevo."
AVISO_VACIA = "El asistente no respondió nada. Intente de nuevo o reformule la pregunta."
SUPRIMIDA = ("La conversación se borró: tenía datos de una persona que se suprimió o que dejó de autorizar mientras el "
             "asistente respondía. Empiece una nueva.")
OCUPADA = {"codigo": "ocupada", "mensaje": "El asistente todavía está respondiendo otro mensaje suyo. Espere a que "
                                          "termine."}
SATURADO = {"codigo": "saturado", "mensaje": "El asistente está atendiendo muchas conversaciones a la vez. Intente de "
                                            "nuevo en unos segundos."}
PROVEEDOR = {"codigo": "proveedor", "mensaje": "Esta conversación se empezó con un modelo que ya no está disponible: "
                                              "empiece una nueva."}
LARGA = {"codigo": "larga", "mensaje": "La conversación es demasiado larga: empiece una nueva."}
DESACTUALIZADA = {"codigo": "sin_pendientes", "mensaje": "Lo que decidió ya no es lo que espera su aprobación (se "
                                                         "atendió en otra pestaña o llegó otra propuesta). Vuelva a "
                                                         "abrir la conversación para verlo."}
VIEJA = {"codigo": "sin_pendientes", "mensaje": "Lo que esperaba su aprobación se preparó con una versión anterior del "
                                               "panel, que no mostraba los datos enteros: no se hizo y quedó como "
                                               "rechazado. Pídale al asistente que lo vuelva a proponer."}


class FinDelTurno(Exception):
    """Un final previsto del turno con un mensaje para la persona (un fallo del modelo, una herramienta fatal…)."""

    def __init__(self, mensaje: str, codigo: str):
        super().__init__(mensaje)
        self.mensaje, self.codigo = mensaje, codigo


# ───────────────────────────── Turnos en curso en este proceso ─────────────────────────────

class Ocupacion:
    """Un turno a la vez por persona y por conversación, y como mucho `maximo` turnos a la vez en el proceso (cada
    uno retiene una conexión con el navegador y otra con el modelo, Mnemo o Anthropic). Complementa el candado de
    MongoDB, que es el que vale entre procesos. Lleva además qué turnos se están cerrando (`cerrar`: el navegador se fue
    o la persona pulsó «Detener») y qué personas tienen un mensaje esperando a que se suelten (`esperar`). Lo protege un
    candado de hilos: las pruebas atienden peticiones desde varios bucles."""

    def __init__(self, maximo: int = TURNOS_POR_PROCESO):
        self.maximo = maximo
        self._candado = threading.Lock()
        self.usuarios: set = set()
        self.conversaciones: set = set()
        self.usuarios_cerrando: set = set()
        self.conversaciones_cerrando: set = set()
        self.esperando: set = set()

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

    def cerrar(self, uid: Any, cid: int | None) -> None:
        """El turno de `uid` en `cid` se está cerrando: suelta sus candados en un momento, así que quien llegue mientras
        tanto puede esperarlo (`viva`)."""
        with self._candado:
            if uid in self.usuarios:
                self.usuarios_cerrando.add(uid)
            if cid is not None and cid in self.conversaciones:
                self.conversaciones_cerrando.add(cid)

    def viva(self, uid: Any, cid: int | None) -> bool:
        """¿Tiene `uid` o `cid` un turno en este proceso que sigue vivo (reservado y sin cerrarse)?"""
        with self._candado:
            return (uid in self.usuarios and uid not in self.usuarios_cerrando) or (
                cid is not None and cid in self.conversaciones and cid not in self.conversaciones_cerrando)

    def esperar(self, uid: Any) -> bool:
        """Anota que un mensaje de `uid` espera a que se suelte un turno; False si ya había otro esperando (uno solo
        por persona: cada uno retiene un cupo del servidor)."""
        with self._candado:
            if uid in self.esperando:
                return False
            self.esperando.add(uid)
            return True

    def dejar_de_esperar(self, uid: Any) -> None:
        with self._candado:
            self.esperando.discard(uid)

    def soltar(self, uid: Any, cid: int | None) -> None:
        with self._candado:
            self.usuarios.discard(uid)
            self.conversaciones.discard(cid)
            self.usuarios_cerrando.discard(uid)
            self.conversaciones_cerrando.discard(cid)


_CREAR = threading.Lock()
_TAREAS: set[asyncio.Task] = set()  # referencia fuerte a los productores: asyncio solo guarda una débil


def _en_fondo(coro: Awaitable[Any]) -> asyncio.Task:
    t = asyncio.create_task(coro)
    _TAREAS.add(t)
    t.add_done_callback(_TAREAS.discard)
    return t


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


def _peso_imagenes(mensajes: list[dict]) -> tuple[int, int]:
    """(base64 total, cantidad) de las imágenes que ya lleva la conversación: se reenvían en cada ronda."""
    peso = n = 0
    for m in mensajes:
        for b in m.get("content") if isinstance(m.get("content"), list) else []:
            dentro = b.get("content") if isinstance(b, dict) and b.get("type") == "tool_result" else [b]
            for img in _imagenes(dentro):
                peso += len(str(img["source"].get("data") or ""))
                n += 1
    return peso, n


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


def _de_emoji(v: str, i: int) -> bool:
    """¿Es `v[i]` (VS15 o VS16) el selector de un emoji? Uno solo, justo tras un símbolo o en un keycap («1️⃣»)."""
    previo = v[i - 1] if i else ""
    if previo in _KEYCAP:
        return v[i + 1:i + 2] == _ENCIERRA_KEYCAP
    return bool(previo) and unicodedata.category(previo) == "So"


def _se_ve_como_es(v: str) -> bool:
    """¿Se ve `v` en la tarjeta tal como se va a escribir? No con caracteres invisibles o que cambian cómo se ve el
    resto (`_INVISIBLES`, los de control salvo el tabulador y los saltos de línea, `_RELLENOS`, `_IGNORABLES` salvo el
    selector de un emoji) ni con una tirada que esconde el final (`_TIRADA`, más de `TARJETA_MARCAS` marcas combinadas
    seguidas)."""
    if _TIRADA.search(v):
        return False
    marcas = 0
    for i, c in enumerate(v):
        categoria = unicodedata.category(c)
        if categoria in _INVISIBLES or (categoria == "Cc" and c not in "\t\n\r") or c in _RELLENOS:
            return False
        if _IGNORABLES.match(c) and not (c in _DE_EMOJI and _de_emoji(v, i)):
            return False
        marcas = marcas + 1 if categoria in ("Mn", "Me") else 0
        if marcas > TARJETA_MARCAS:
            return False
    return True


def _etiqueta_se_ve_como_es(k: str) -> bool:
    """Una etiqueta se pinta sin conservar los espacios (a diferencia del valor): tiene que venir ya con espacios
    sueltos entre las palabras, sin tabuladores ni saltos de línea."""
    return " ".join(k.split()) == k and _se_ve_como_es(k)


def _tarjeta(conf: Confirmacion) -> dict:
    """La tarjeta de una escritura con los valores y las etiquetas enteros: lo que se aprueba es exactamente lo que se
    escribe. Si no cabe (un valor de más de `TARJETA_VALOR` caracteres, una etiqueta de más de `TARJETA_ETIQUETA`, más
    de `TARJETA_FILAS` filas o algo que la herramienta ya recortó, `_RECORTADO`) o algo no se vería como se va a
    escribir (`_se_ve_como_es`, también en las etiquetas: en Mnemo son los nombres de los argumentos),
    `ErrorHerramienta`: la escritura no se ofrece. Nunca se recorta ni se limpia en silencio."""
    t = conf.para_interfaz()
    filas = [(str(k), str(v)) for k, v in list(t.get("detalle") or [])]
    if len(filas) > TARJETA_FILAS or any(k == "…" or len(k) > TARJETA_ETIQUETA or len(v) > TARJETA_VALOR
                                         or _RECORTADO.search(v) for k, v in filas):
        raise ErrorHerramienta(NO_CABE, "no_cabe")
    if not all(_etiqueta_se_ve_como_es(k) and _se_ve_como_es(v) for k, v in filas):
        raise ErrorHerramienta(OCULTO, "oculto")
    return {"titulo": _corto(t.get("titulo"), 200) or "Confirmar acción", "detalle": [[k, v] for k, v in filas],
            "aviso": _corto(t.get("aviso"), 500) or None}


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def ahora_s() -> float:
    """El reloj de los topes del turno (monótono). Las pruebas lo mueven junto con `dormir`."""
    return time.monotonic()


async def dormir(segundos: float) -> None:
    """La espera antes de repetir una ronda. Las pruebas la cambian para no esperar de verdad."""
    await asyncio.sleep(segundos)


def _tipo(e: BaseException) -> str:
    """Para el registro: el tipo de la excepción y, si lo tiene, su código estable (nunca su mensaje)."""
    codigo = getattr(e, "codigo", None)
    return f"{type(e).__name__} {codigo}" if isinstance(codigo, str) else type(e).__name__


# ───────────────────────────── El turno ─────────────────────────────

class Turno:
    """Un turno de una persona en una conversación: el productor (`_correr`) y la respuesta (`eventos`)."""

    def __init__(self, *, app: Any, quien: Any, ajustes: dict, agente: dict, api: ApiInterna, conv: dict | None,
                 cid: int, titulo: str, turno: str, limite: dict | None, proveedor: proveedores.Proveedor):
        self.app, self.db, self.cfg = app, app.state.db, app.state.cfg
        self.quien, self.ajustes, self.agente, self.api = quien, ajustes, agente, api
        self.conv, self.cid, self.titulo, self.turno, self.limite = conv, cid, titulo, turno, limite
        self.proveedor = proveedor  # el de la conversación (congelado) o, si es nueva, el que rige ahora
        self.cola: asyncio.Queue = asyncio.Queue()
        self.arrancado = asyncio.Event()
        self.tarea: asyncio.Task | None = None
        self.ocupacion = ocupacion_de(app)
        self.suelto = False  # ya soltó la reserva de este proceso: otro turno pudo tomarla
        self.mnemo = None
        self.herramientas: dict[str, Herramienta] = {}
        self.permitidas: set[str] = set()
        self.definiciones: list[dict] = []
        self.sistema = ""
        self.expira = None
        self.tokens = int((conv or {}).get("tokens_ultima") or 0)
        self.imagenes_ronda = 0  # base64 de imágenes en los resultados de la ronda en curso (TOPE_IMAGENES)
        # Lo que ya lleva la conversación (TOPE_IMAGENES_CONVERSACION y MAX_IMAGENES_CONVERSACION): base64 y cantidad
        self.imagenes_conv = self.imagenes_n = 0
        self.servido = 0  # caracteres de resultados de herramientas que se le pasaron al modelo en el turno

    # ── El productor y la respuesta ──
    def lanzar(self, trabajo: Callable[[], Awaitable[str]]) -> None:
        self.tarea = _en_fondo(self._correr(trabajo))

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
            # El navegador se fue (o la respuesta terminó): el productor no sigue gastando en un turno sin lector.
            # Antes, el turno queda como «cerrándose»: tras «Detener», el mensaje siguiente puede llegar antes de que
            # suelte sus candados, y ese sí espera (`_ocupar`)
            if self.tarea is not None and not self.tarea.done():
                self._cerrandose()
                self.tarea.cancel()

    def _cerrandose(self) -> None:
        if not self.suelto:  # si ya soltó, la reserva puede ser de otro turno
            self.ocupacion.cerrar(self.quien.uid, self.cid)

    async def _correr(self, trabajo: Callable[[], Awaitable[str]]) -> None:
        motivo, error = "error", None
        sostener = _en_fondo(self._sostener())
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
            # Primero los candados: cuando el navegador ve `fin`, ya puede mandar otro mensaje (y lo que llegue antes,
            # de otra pestaña, espera el momento que tarda en soltarlos en vez de recibir 409)
            self._cerrandose()
            sostener.cancel()
            await self._soltar()
            if error is not None:
                self.emitir({"tipo": "error", "mensaje": error[0], "codigo": error[1]})
                motivo = "error"
            fin: dict[str, Any] = {"tipo": "fin", "motivo": motivo}
            if self.limite:
                fin["limite"] = self.limite
            self.emitir(fin)
            self.cola.put_nowait(None)

    async def _sostener(self) -> None:
        """Renueva el candado de MongoDB cada `RENOVAR_S` mientras el turno corre: si el proceso muere (un despliegue,
        una caída), vence solo en `conv_db.ARRIENDO` y la persona no queda sin asistente."""
        while True:
            await asyncio.sleep(RENOVAR_S)
            try:
                await run_in_threadpool(conv_db.renovar_candado, self.db, self.cid, self.turno)
            except Exception as e:  # noqa: BLE001 - la vuelta siguiente lo intenta otra vez
                log.warning("Asistente: no se pudo renovar el candado de la conversación (%s)", type(e).__name__)

    async def _soltar(self) -> None:
        # Los candados antes que nada (el de MongoDB y después la reserva de este proceso): tras «Detener», el navegador
        # ya puede estar mandando el mensaje siguiente, que espera a que esto pase (`_ocupar`). La reserva se suelta
        # aunque el navegador se vaya justo ahora (la cancelación llega en medio): si no, la persona quedaría sin
        # asistente hasta que el proceso se reinicie (el candado de MongoDB lo termina de soltar su hilo, o vence solo)
        try:
            await run_in_threadpool(conv_db.soltar, self.db, self.cid, self.turno)
        except Exception as e:  # noqa: BLE001 - el candado de MongoDB vence solo
            log.warning("Asistente: no se pudo soltar la conversación (%s)", type(e).__name__)
        finally:
            self.ocupacion.soltar(self.quien.uid, self.cid)
            self.suelto = True
        if self.expira is not None:
            try:
                # Si el administrador bajó la retención mientras corría el turno, lo guardado en él venía con el plazo
                # viejo (se leyó al empezar): se vuelve a fijar con el vigente (un turno que empiece ya fija ese mismo)
                _, agente = await run_in_threadpool(politica.leer, self.db)
                if agente["retencion_dias"] < self.agente["retencion_dias"]:
                    await run_in_threadpool(conv_db.renovar, self.db, self.cid, agente["retencion_dias"])
            except Exception as e:  # noqa: BLE001 - el próximo turno lo vuelve a fijar
                log.warning("Asistente: no se pudo revisar la retención al terminar (%s)", type(e).__name__)
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
            cliente = (await run_in_threadpool(mnemo_cliente.cliente_de, self.app)
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
                # La conexión venció o se cayó: el mensaje dice que el administrador la vuelva a conectar
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
                                            self.proveedor.modelo, proveedor=self.proveedor.clave)
        self.expira = self.conv["expira"]
        return aviso

    async def _preparar(self) -> None:
        """Las herramientas de la conversación (las congeladas, rehechas por nombre con el código vigente) y cuáles se
        permiten hoy: los permisos y los ajustes pudieron cambiar desde que se creó."""
        from . import herramientas as registro
        from .herramientas import mnemo as hmnemo
        self.sistema = self.conv["sistema"]
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
                    self.mnemo = await run_in_threadpool(mnemo_cliente.cliente_de, self.app)
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
            raise FinDelTurno("La conversación se borró mientras el asistente respondía (por ejemplo, porque tenía "
                              "datos de una persona que se suprimió o que dejó de autorizar).", "borrada") from None

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
        await self._preparar()
        historial = await run_in_threadpool(conv_db.historial, self.db, self.cid)
        self.imagenes_conv, self.imagenes_n = _peso_imagenes(historial)
        pend, crudo = conv_db.pendiente_de(self.conv), self.conv.get("pendiente")
        if pend is not None:
            # Primero se quita lo pendiente (queda como no aprobado) y después se guardan sus resultados: si algo se
            # corta en el medio, el siguiente turno ve un `tool_use` sin resultado y nunca dos resultados para el mismo
            if not await run_in_threadpool(conv_db.quitar_pendiente, self.db, self.cid, crudo,
                                           [str(ll.get("id")) for ll in pend["llamadas"]]):
                raise FinDelTurno("Otro turno atendió lo pendiente de esta conversación. Intente de nuevo.", "ocupada")
            bloques, ui = self._rechazar(pend, NO_APROBADA)
        else:
            bloques, ui = self._interrumpidas(historial)
        # El filtro de etiqueta de la vista va solo si la etiqueta existe y no es sensible: eso lo dice la base
        filtros = contexto.get("filtros") if isinstance(contexto, dict) else None
        etiquetas = (await run_in_threadpool(sistema.etiquetas_del_contexto, self.db)
                     if isinstance(filtros, dict) and filtros.get("etiqueta") else None)
        # La presentación abierta (capítulo y paso) se dice solo si es del guion: el capítulo, el paso y su título
        guion = (await run_in_threadpool(sistema.guion_del_contexto)
                 if isinstance(contexto, dict) and contexto.get("presentacion") else None)
        contexto_panel = sistema.contexto_del_panel(contexto, _ahora(), etiquetas, guion)
        bloques = conv_db.limpio(bloques + [{"type": "text", "text": contexto_panel}, {"type": "text", "text": texto}])
        await self._guardar("user", bloques, texto=texto, herramientas=ui)
        historial.append({"role": "user", "content": bloques})
        if aviso:
            await self._avisar(aviso, "alerta")
        return await self._rondas(historial)

    async def confirmacion(self, decisiones: dict[str, bool]) -> str:
        """Las decisiones de la persona sobre lo pendiente (`abrir_confirmacion` ya comprobó que son sobre lo de ahora):
        lo aprobado se ejecuta (con su clave de idempotencia), lo rechazado o sin decisión vuelve como rechazo, y el
        bucle sigue con todos los resultados en un mensaje."""
        self.emitir({"tipo": "inicio", "conversacion": self.cid, "titulo": self.titulo})
        self.expira = await run_in_threadpool(conv_db.renovar, self.db, self.cid, self.agente["retencion_dias"])
        await self._preparar()
        pend, crudo = conv_db.pendiente_de(self.conv), self.conv.get("pendiente")
        if pend is None:
            raise FinDelTurno("No hay acciones pendientes en esta conversación.", "sin_pendientes")
        historial = await run_in_threadpool(conv_db.historial, self.db, self.cid)
        resultados = {r.get("tool_use_id"): r for r in pend.get("resultados") or [] if isinstance(r, dict)}
        ui = {h.get("id"): h for h in pend.get("ui") or [] if isinstance(h, dict)}
        self.imagenes_conv, self.imagenes_n = _peso_imagenes(
            [*historial, {"role": "user", "content": list(resultados.values())}])
        # Lo pendiente se quita antes de ejecutar nada: si el turno se corta a mitad (el navegador se va, el proceso se
        # reinicia), lo que alcanzó a hacerse no vuelve a quedar aprobable (se haría dos veces). Con él se guarda lo que
        # la persona no aprobó: el turno siguiente ve esas escrituras sin resultado y le dice al modelo que lo rechazado
        # se rechazó (`RECHAZADA`) y que lo aprobado pudo hacerse (`INTERRUMPIDA_ESCRITURA`)
        rechazadas = [str(ll.get("id")) for ll in pend["llamadas"] if decisiones.get(str(ll.get("id"))) is not True]
        if not await run_in_threadpool(conv_db.quitar_pendiente, self.db, self.cid, crudo, rechazadas):
            raise FinDelTurno("Otro turno atendió lo pendiente de esta conversación.", "sin_pendientes")
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

    def _interrumpidas(self, historial: list[dict]) -> tuple[list[dict], list[dict]]:
        """Resultados para los `tool_use` del último mensaje del asistente que no tienen resultado (un turno cortado):
        la API exige un resultado por cada uno antes del mensaje nuevo. Lo que la persona no aprobó al decidir vuelve
        como rechazado (`rechazadas`, que se guardan al quitar lo pendiente); otra escritura pudo hacerse (se cortó
        después de aprobarla): el modelo la verifica antes de proponerla otra vez; lo demás, «interrumpido»."""
        if not historial or historial[-1]["role"] != "assistant":
            return [], []
        usos = [b for b in historial[-1]["content"] if isinstance(b, dict) and b.get("type") == "tool_use"]
        rechazadas = {r for r in (self.conv or {}).get("rechazadas") or [] if isinstance(r, str)}
        bloques, ui = [], []
        for u in usos:
            tid, h = str(u.get("id")), self.herramientas.get(u.get("name"))
            if tid in rechazadas:
                bloques.append(_resultado(tid, RECHAZADA, True))
                ui.append({"id": tid, "estado": "rechazada", "resumen": "Rechazada"})
                continue
            motivo = INTERRUMPIDA_ESCRITURA if h is not None and h.tipo == "escritura" else INTERRUMPIDA
            bloques.append(_resultado(tid, motivo, True))
            ui.append({"id": tid, "estado": "error", "resumen": "Interrumpida"})
        return bloques, ui

    # ── Las rondas ──
    async def _rondas(self, historial: list[dict]) -> str:
        inicio, rondas, reintentos = ahora_s(), 0, 0
        while True:
            if rondas >= MAX_RONDAS or (rondas and ahora_s() - inicio >= TOPE_TURNO_S):
                return "pasos"
            if self.tokens > conv_db.TOPE_TOKENS:
                # La conversación ya no admite más mensajes (409 «larga»): el turno termina con ese código, así el
                # widget ofrece una conversación nueva y no «Continuar». El aviso queda en el historial
                await self._avisar(AVISO_LARGA, "alerta", emitir=False)
                raise FinDelTurno(AVISO_LARGA, "larga")
            anunciadas: list[tuple[str, str, str]] = []
            try:
                respuesta = await self._pedir(historial, anunciadas)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 - se decide abajo: repetir la ronda o cerrar con un error claro
                espera = self._espera(e, reintentos)
                # Sin pasarse del tope del turno: una espera larga (Mnemo limitando el ritmo) al final no se hace
                if espera is not None and ahora_s() - inicio + espera < TOPE_TURNO_S:
                    reintentos += 1
                    log.warning("Asistente: se repite la ronda (%s)", _tipo(e))
                    self.emitir({"tipo": "descartar"})
                    await dormir(espera)
                    continue
                log.warning("Asistente: falló la petición al modelo (%s)", _tipo(e))
                raise FinDelTurno(*self._explicar(e)) from None
            reintentos, rondas = 0, rondas + 1
            motivo = await self._cerrar_ronda(respuesta, historial, anunciadas)
            if motivo is not None:
                return motivo

    def _espera(self, e: BaseException, reintentos: int) -> float | None:
        """Los segundos antes de repetir la ronda tras `e`, o None si no se repite (no es pasajero o ya se repitió
        `REINTENTOS` veces)."""
        if reintentos >= REINTENTOS:
            return None
        try:
            espera = self.proveedor.reintento(e, reintentos)
        except Exception:  # noqa: BLE001 - ante la duda, no se repite
            return None
        return max(0.0, float(espera)) if isinstance(espera, (int, float)) and not isinstance(espera, bool) else None

    def _explicar(self, e: BaseException) -> tuple[str, str]:
        try:
            mensaje, codigo = self.proveedor.explicar(e)
            return str(mensaje), str(codigo)
        except Exception:  # noqa: BLE001
            return "El asistente falló al responder. Intente de nuevo.", "error"

    async def _pedir(self, historial: list[dict], anunciadas: list[tuple[str, str, str]]) -> proveedores.Respuesta:
        """Una ronda con el proveedor: emite lo que llega (y anuncia cada herramienta con su etiqueta) y devuelve la
        respuesta completa."""
        def al_evento(ev: dict) -> None:
            tipo = ev.get("tipo") if isinstance(ev, dict) else None
            if tipo == "herramienta":
                tid, crudo = str(ev.get("id")), ev.get("nombre")
                nombre = _corto(crudo, 64)
                h = self.herramientas.get(crudo) if isinstance(crudo, str) else None
                anunciadas.append((tid, nombre, h.etiqueta if h else nombre))
                self._herramienta(tid, nombre, anunciadas[-1][2], "inicio")
            elif tipo in proveedores.EVENTOS:
                self.emitir(ev)

        return await self.proveedor.generar(self.sistema, historial, self.definiciones,
                                            max_tokens=self.proveedor.max_tokens, esfuerzo=self.cfg.agente_esfuerzo,
                                            al_evento=al_evento)

    async def _cerrar_ronda(self, r: proveedores.Respuesta, historial: list[dict],
                            anunciadas: list[tuple[str, str, str]]) -> str | None:
        """Guarda la ronda y ejecuta sus herramientas. Devuelve el motivo de fin, o None para seguir con otra."""
        # Sin bloques de texto vacíos: la API los rechaza al reenviarlos
        contenido = [b for b in conv_db.limpio(list(r.contenido))
                     if not (b.get("type") == "text" and not b.get("text"))]
        u = r.uso
        self.tokens = u.entrada + u.cache_lectura + u.cache_escritura
        await run_in_threadpool(conv_db.sumar_uso, self.db, self.quien.uid, u.entrada, u.salida, u.cache_lectura,
                                u.cache_escritura, u.creditos)
        uso: dict[str, Any] = {"entrada": u.entrada, "salida": u.salida, "cache_lectura": u.cache_lectura,
                               "cache_escritura": u.cache_escritura}
        if u.creditos is not None:
            uso["creditos"] = u.creditos
        meta = {"modelo": r.modelo, "fin": r.fin, "uso": uso,
                "detalles": conv_db.a_json(r.detalles) if r.detalles else None,
                "transformaciones": conv_db.a_json(list(r.transformaciones))}
        ids = {b.get("id") for b in contenido if b.get("type") == "tool_use"}
        for tid, nombre, etiqueta in anunciadas:
            if tid not in ids:  # quedó antes de un cambio de modelo: no se ejecuta
                self._herramienta(tid, nombre, etiqueta, "error", "Descartada")
        if r.fin == "refusal":
            # Solo para auditoría: no se reenvía (puede traer una herramienta a medias) y lo pintado se borra
            log.info("Asistente: el modelo no continuó (categoría %s)", (r.detalles or {}).get("category"))
            await self._guardar("assistant", contenido, replay=False, **meta)
            self.emitir({"tipo": "descartar"})
            await self._avisar(AVISO_RECHAZO, "alerta")
            return "rechazo"
        if not contenido:
            # El modelo a veces termina sin bloques (sobre todo tras resultados de herramientas): queda solo para
            # auditoría. Reenviarlo sería un 400 en cada petición siguiente (solo el último mensaje del asistente puede
            # ir vacío) y la conversación quedaría inservible
            await self._guardar("assistant", contenido, replay=False, tokens=self.tokens, **meta)
            aviso = AVISO_VACIA if r.fin not in CORTES else AVISO_INCOMPLETA if r.fin == "other" else AVISO_CORTADA
            await self._avisar(aviso, "info")
            return "listo"
        await self._guardar("assistant", contenido, tokens=self.tokens, **meta)
        historial.append({"role": "assistant", "content": contenido})
        for texto in r.respaldos:  # ya se avisó al llegar el bloque: aquí queda en el historial
            await self._avisar(texto, "info", emitir=False)
        if r.fin == "pause_turn":
            return None  # herramienta del servidor en pausa: se reenvía tal cual
        usos = [b for b in contenido if b.get("type") == "tool_use"]
        if not usos or (r.fin != "tool_use" and r.fin not in CORTES):
            if r.fin in CORTES:
                await self._avisar(AVISO_INCOMPLETA if r.fin == "other" else AVISO_CORTADA, "info")
            return "listo"
        if r.fin == "tool_use":
            bloques, ui, llamadas, fatal = await self._ejecutar(usos)
        else:  # entrada cortada: el analizador tolerante da un objeto parcial «válido», que no se ejecuta
            bloques, ui, llamadas, fatal = {}, [], [], None
            motivo, resumen = (INCOMPLETA, "Respuesta incompleta") if r.fin == "other" else (CORTADA, "Entrada cortada")
            for b in usos:
                bloques[b["id"]] = _resultado(b["id"], motivo, True)
                ui.append({"id": b["id"], "estado": "error", "resumen": resumen})
                h = self.herramientas.get(b.get("name"))
                self._herramienta(b["id"], _corto(b.get("name"), 64), h.etiqueta if h else _corto(b.get("name"), 64),
                                  "error", resumen)
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
        for n, u in enumerate(usos):
            tid, nombre = str(u.get("id")), _corto(u.get("name"), 64)
            h = self.herramientas.get(u.get("name"))
            etiqueta = h.etiqueta if h else nombre
            if fatal is not None:
                bloque, estado, resumen = self._fallo(tid, nombre, etiqueta, ErrorHerramienta(SIN_EJECUTAR,
                                                                                             "sin_ejecutar"))[:3]
            elif n >= MAX_HERRAMIENTAS_RONDA:
                bloque, estado, resumen = self._fallo(tid, nombre, etiqueta, ErrorHerramienta(DEMASIADAS,
                                                                                             "demasiadas"))[:3]
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

    async def _mnemo_vigente(self, h: Herramienta) -> None:
        """Antes de cada herramienta de Mnemo, que no pasa por la API del panel (va con la cuenta del administrador):
        la sesión de quien conversa sigue valiendo (una petición a la API: un 401 termina el turno) y los ajustes de
        ahora todavía se la dan. Las del panel no lo necesitan: cada llamada a la API vuelve a revisarlo todo."""
        estado = await self.api.get("/api/agente/estado")
        _, agente = await run_in_threadpool(politica.leer, self.db)
        if not (isinstance(estado, dict) and estado.get("disponible")) or not politica.ofrecida(h, self.quien, agente,
                                                                                                self.cfg):
            raise ErrorHerramienta(MNEMO_YA_NO, "permiso")

    async def _anotar(self, personas: set[int], desde: datetime, anotadas: set[int] = frozenset()) -> None:
        """Anota en la conversación a las personas cuyos datos recibió el modelo (o mostró una tarjeta) y después
        comprueba que ninguna se haya suprimido ni, desde que se empezaron a leer (`desde`), dejado de autorizar: la
        supresión y el «no» borran las conversaciones que ya las tienen anotadas, así que uno que llegó mientras la
        herramienta las leía no encontró esta. Si pasó, la conversación se borra como lo habrían hecho ellos y el turno
        termina sin mandarle esos datos al modelo. En lo que devuelve una escritura aprobada, las personas de su
        tarjeta (`anotadas`) no se miran así: ya estaban anotadas (su «no» borró la conversación), y una revocatoria
        aprobada es la escritura misma; las demás sí (las parecidas que devuelve crear_persona)."""
        await run_in_threadpool(conv_db.sumar_personas, self.db, self.cid, personas)
        if await run_in_threadpool(conv_db.suprimidas, self.db, personas) or (
                personas - anotadas and await run_in_threadpool(conv_db.dejaron_de_autorizar, self.db,
                                                                personas - anotadas, desde)):
            await run_in_threadpool(bd.borrar_conversaciones, self.db, {"_id": self.cid})
            raise FinDelTurno(SUPRIMIDA, "borrada")

    async def _correr_herramienta(self, h: Herramienta, tid: str, args: Any) -> tuple:
        """Ejecuta una herramienta con plazo: (tool_result, estado, resumen, error fatal o None)."""
        if h.tipo != "escritura" and self.servido >= TOPE_RESULTADOS_TURNO:  # ni se lee: el modelo no lo recibiría
            return self._fallo(tid, h.nombre, h.etiqueta, ErrorHerramienta(TOPE_TURNO, "tope_turno"))
        desde = _ahora() - MARGEN_OLVIDO
        try:
            if h.nombre_remoto:
                await self._mnemo_vigente(h)
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
        # Lo que lee un turno tiene tope: pasado, el resultado no se le pasa al modelo (las escrituras sí: son cortas
        # y el modelo tiene que saber que se hicieron)
        if h.tipo != "escritura" and self.servido + len(texto) > TOPE_RESULTADOS_TURNO:
            self.servido = TOPE_RESULTADOS_TURNO  # lo que siga en el turno ya ni se lee
            return self._fallo(tid, h.nombre, h.etiqueta, ErrorHerramienta(TOPE_TURNO, "tope_turno"))
        self.servido += len(texto)
        imagenes, omitidas, pesadas, de_mas = [], 0, 0, 0
        tope = min(TOPE_IMAGENES, self.proveedor.tope_imagenes)
        for img in _imagenes(res.imagenes):
            peso = len(str((img.get("source") or {}).get("data") or ""))
            if peso > tope:  # sola ya no cabe: pedirla otra vez no sirve
                pesadas += 1
                continue
            if self.imagenes_n >= MAX_IMAGENES_CONVERSACION or self.imagenes_conv + peso > TOPE_IMAGENES_CONVERSACION:
                de_mas += 1
                continue
            if self.imagenes_ronda + peso > tope:
                omitidas += 1
                continue
            self.imagenes_ronda += peso
            self.imagenes_conv += peso
            self.imagenes_n += 1
            imagenes.append(img)
        if omitidas:
            texto += (f"\n[{omitidas} imagen(es) omitida(s): esta ronda ya llevaba demasiadas. Pídelas de a una en "
                      "otra llamada.]")
        if pesadas:
            texto += f"\n[{pesadas} imagen(es) omitida(s): pesa(n) demasiado para mandársela(s) al modelo.]"
        if de_mas:
            texto += (f"\n[{de_mas} imagen(es) omitida(s): la conversación ya lleva demasiadas imágenes. Si hace falta "
                      "verlas, que la persona empiece una conversación nueva.]")
        personas = _personas(res.personas)
        if personas:
            await self._anotar(personas, desde, _personas_de_entrada(args) if h.tipo == "escritura" else frozenset())
        resumen = _corto(res.resumen) or "Listo"
        self._herramienta(tid, h.nombre, h.etiqueta, "ok", resumen)
        for a in _acciones(res.acciones):
            self.emitir({"tipo": "accion", "accion": a})
        contenido: Any = [{"type": "text", "text": texto}, *imagenes] if imagenes else texto
        return _resultado(tid, contenido), "ok", resumen, None

    async def _preparar_escritura(self, h: Herramienta, tid: str, uso: dict, args: Any) -> tuple:
        """Arma la tarjeta de una escritura: (llamada pendiente, None) o (None, fallo) si `confirmar` falla."""
        desde = _ahora() - MARGEN_OLVIDO  # la tarjeta también lee la ficha (lo de «antes → después»)
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
            await self._anotar(personas, desde)
        self._herramienta(tid, h.nombre, h.etiqueta, "pendiente")
        self.emitir({"tipo": "confirmar", "id": tid, "nombre": h.nombre, "etiqueta": h.etiqueta, **tarjeta})
        # Lo pendiente se guarda con la marca de que su tarjeta muestra los valores enteros: lo que guardó una versión
        # anterior (que los cortaba a 500 caracteres sin decirlo) no se aprueba (`abrir_confirmacion`)
        return {"id": tid, "nombre": h.nombre, "etiqueta": h.etiqueta,
                "entrada": conv_db.a_json(_entrada_pendiente(h, args, uso.get("input"))),
                "confirmacion": {**tarjeta, "entera": True}}, None

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

def _entera(llamada: dict) -> bool:
    """¿La tarjeta guardada de esta escritura pendiente muestra los valores enteros? Las de una versión anterior del
    panel no llevan la marca (`Turno._preparar_escritura`)."""
    tarjeta = llamada.get("confirmacion")
    return isinstance(tarjeta, dict) and tarjeta.get("entera") is True


def _respuesta(turno: Turno) -> StreamingResponse:
    return StreamingResponse(turno.eventos(), media_type="application/x-ndjson", headers=FLUJO)


async def _ocupar(app: Any, uid: Any, cid: int | None, turno: str) -> dict | None:
    """Toma los candados del turno: la reserva de este proceso (`Ocupacion`) y, si la conversación ya existe, el de
    MongoDB (`conv_db.tomar`, que la devuelve fresca; si es nueva, None), después de comprobar que la persona no tiene
    un turno en otra conversación (`otra_ocupada`, que vale entre procesos).

    Si la persona o la conversación tienen un turno vivo en este proceso, 409 `ocupada` en el acto: mientras se espera
    se retiene uno de los cupos del asistente en el servidor, y ese turno no los va a soltar pronto (si no, quien tiene
    un turno largo dejaría a los demás en 503 mandando mensajes). Solo se espera si el turno anterior se está cerrando
    (`Ocupacion.cerrar`): tras «Detener», el navegador corta la respuesta y manda el mensaje siguiente, que en una
    máquina lenta llega antes de que el turno cortado suelte sus candados. También si lo que estorba es el candado de
    MongoDB de otro proceso, que no dice si su turno sigue vivo. Se vuelve a probar cada `SONDEO_OCUPADA_S` hasta
    `ESPERA_OCUPADA_S`, sin retener nada mientras tanto, y recién entonces 409; espera un solo mensaje por persona (otro
    recibe 409 enseguida). Un proceso lleno no espera: 503 `saturado`, con `Retry-After`."""
    db, ocupacion = app.state.db, ocupacion_de(app)
    limite = time.monotonic() + ESPERA_OCUPADA_S
    espera = False  # este mensaje es el que espera por esta persona
    try:
        while True:
            motivo = ocupacion.reservar(uid, cid)
            if motivo == "saturado":
                raise HTTPException(503, dict(SATURADO), headers={"Retry-After": "5"})
            if motivo is None:
                try:
                    libre = not await run_in_threadpool(conv_db.otra_ocupada, db, uid, cid)
                    conv = (await run_in_threadpool(conv_db.tomar, db, cid, uid, turno)
                            if libre and cid is not None else None)
                except BaseException:
                    ocupacion.soltar(uid, cid)
                    raise
                if libre and (cid is None or conv is not None):
                    return conv
                ocupacion.soltar(uid, cid)
            elif ocupacion.viva(uid, cid):
                raise HTTPException(409, dict(OCUPADA))
            if time.monotonic() >= limite or not (espera or (espera := ocupacion.esperar(uid))):
                raise HTTPException(409, dict(OCUPADA))
            await asyncio.sleep(SONDEO_OCUPADA_S)
    finally:
        if espera:
            ocupacion.dejar_de_esperar(uid)


async def _liberar(app: Any, uid: Any, cid: int | None, turno: str) -> None:
    """Suelta lo que tomó `_ocupar` cuando el turno no llega a lanzarse (un 429, un fallo de MongoDB…)."""
    if cid is not None:
        try:
            await run_in_threadpool(conv_db.soltar, app.state.db, cid, turno)
        except Exception as e:  # noqa: BLE001 - vence solo
            log.warning("Asistente: no se pudo soltar la conversación (%s)", type(e).__name__)
    ocupacion_de(app).soltar(uid, cid)


async def _proveedor(app: Any, conv: dict | None) -> proveedores.Proveedor:
    """El proveedor del turno: el de la conversación (congelado; 409 `proveedor` si ya no está) o, para una nueva, el
    que rige ahora (503 si no hay ninguno: se fue entre `exigir` y aquí)."""
    db, cfg = app.state.db, app.state.cfg
    if conv is not None:
        proveedor = await run_in_threadpool(proveedores.de_conversacion, app, cfg, db, conv)
        if proveedor is None:
            raise HTTPException(409, dict(PROVEEDOR))
        return proveedor
    proveedor = await run_in_threadpool(proveedores.para_nueva, app, cfg, db)
    if proveedor is None:
        raise HTTPException(503, dict(politica.SIN_CONFIGURAR))
    return proveedor


async def _contar(db: Any, quien: Any, ajustes: dict) -> dict:
    """Suma el turno al día de la persona: un mensaje, una aprobación o un rechazo (cada uno pone a trabajar al
    modelo). 429 `volumen` si ya llegó al tope. Devuelve el `limite` del evento `fin`."""
    maximo = politica.mensajes_diarios(ajustes, quien.rol)
    usados = await run_in_threadpool(conv_db.contar_mensaje, db, quien.uid, maximo)
    if usados is None:
        raise HTTPException(429, {"codigo": "volumen", "mensaje": f"Llegó al tope de {maximo} mensajes al asistente "
                                                                  "por hoy. Podrá seguir mañana."})
    return {"usados": usados, "maximo": maximo}


async def abrir_mensaje(request: Any, quien: Any, cid: int | None, texto: str, contexto: Any) -> StreamingResponse:
    """POST /api/agente/mensajes: las comprobaciones previas y el turno en flujo."""
    app = request.app
    db, cfg = app.state.db, app.state.cfg
    ajustes, agente = await run_in_threadpool(politica.leer, db)
    await run_in_threadpool(politica.exigir, quien, cfg, agente, db)
    texto = conv_db.texto_valido(texto)
    conv = None
    if cid is not None:
        conv = await run_in_threadpool(conv_db.de_usuario, db, cid, quien.uid)
        if conv is None:
            raise HTTPException(404, {"codigo": "no_existe", "mensaje": "No existe esa conversación."})
        if conv_db.larga(conv):
            raise HTTPException(409, dict(LARGA))
    proveedor = await _proveedor(app, conv)
    turno_id = secrets.token_hex(8)
    fresca = await _ocupar(app, quien.uid, cid, turno_id)
    try:
        if cid is not None:
            if conv_db.larga(fresca):  # el turno que se estaba cerrando la dejó larga
                raise HTTPException(409, dict(LARGA))
            conv, titulo = fresca, fresca.get("titulo") or "Conversación"
        else:  # la conversación se crea al empezar el flujo (con Mnemo, si toca): aquí solo se reserva su id
            cid = await run_in_threadpool(bd.siguiente_id, db, conv_db.CONVERSACIONES)
            ocupacion_de(app).agregar(cid)
            titulo = conv_db.titulo_de(texto)
        limite = await _contar(db, quien, ajustes)
        turno = Turno(app=app, quien=quien, ajustes=ajustes, agente=agente, api=ApiInterna.desde_peticion(request),
                      conv=conv, cid=cid, titulo=titulo, turno=turno_id, limite=limite, proveedor=proveedor)
        turno.lanzar(lambda: turno.mensaje(texto, contexto))
    except BaseException:
        await _liberar(app, quien.uid, cid, turno_id)
        raise
    return _respuesta(turno)


async def abrir_confirmacion(request: Any, quien: Any, cid: int, decisiones: dict[str, bool]) -> StreamingResponse:
    """POST /api/agente/confirmaciones: las comprobaciones previas y el turno que sigue tras la decisión. Cada decisión
    tiene que ser sobre algo que espera aprobación ahora (si no, 409): una pestaña vieja (o un «Reintentar» cuya
    respuesta no llegó) decide sobre tarjetas que ya no están, y lo nuevo, sin decisión, quedaría rechazado sin que la
    persona lo viera. Lo aprobado tiene que tener una tarjeta que mostró los valores enteros (`_entera`): lo que guardó
    una versión anterior del panel queda rechazado, con 409."""
    app = request.app
    db, cfg = app.state.db, app.state.cfg
    ajustes, agente = await run_in_threadpool(politica.leer, db)
    await run_in_threadpool(politica.exigir, quien, cfg, agente, db)
    conv = await run_in_threadpool(conv_db.de_usuario, db, cid, quien.uid)
    if conv is None:
        raise HTTPException(404, {"codigo": "no_existe", "mensaje": "No existe esa conversación."})
    sin_pendientes = HTTPException(409, {"codigo": "sin_pendientes", "mensaje": "No hay acciones esperando su "
                                                                                 "aprobación en esta conversación."})
    if conv_db.pendiente_de(conv) is None:
        raise sin_pendientes
    # Antes de ejecutar nada de lo aprobado: sin el proveedor de la conversación, el turno no podría seguir
    proveedor = await _proveedor(app, conv)
    turno_id = secrets.token_hex(8)
    conv = await _ocupar(app, quien.uid, cid, turno_id)
    try:
        pend = conv_db.pendiente_de(conv)
        if pend is None:  # otro turno lo atendió entre la lectura y el candado
            raise sin_pendientes
        if not set(decisiones) <= {str(ll.get("id")) for ll in pend["llamadas"] if isinstance(ll, dict)}:
            raise HTTPException(409, dict(DESACTUALIZADA))
        if any(decisiones.get(str(ll.get("id"))) is True and not _entera(ll) for ll in pend["llamadas"]
               if isinstance(ll, dict)):
            # Lo guardó una versión anterior del panel, que cortaba cada valor de la tarjeta a 500 caracteres (y a 30
            # filas) sin marcarlo: no se aprueba sin haberlo visto entero. Queda como rechazado (el modelo lo sabe en
            # el mensaje siguiente, `_interrumpidas`) y el asistente lo vuelve a proponer si se le pide
            await run_in_threadpool(conv_db.quitar_pendiente, db, cid, conv.get("pendiente"),
                                    [str(ll.get("id")) for ll in pend["llamadas"] if isinstance(ll, dict)])
            raise HTTPException(409, dict(VIEJA))
        limite = await _contar(db, quien, ajustes)
        turno = Turno(app=app, quien=quien, ajustes=ajustes, agente=agente, api=ApiInterna.desde_peticion(request),
                      conv=conv, cid=cid, titulo=conv.get("titulo") or "Conversación", turno=turno_id, limite=limite,
                      proveedor=proveedor)
        turno.lanzar(lambda: turno.confirmacion(decisiones))
    except BaseException:
        await _liberar(app, quien.uid, cid, turno_id)
        raise
    return _respuesta(turno)
