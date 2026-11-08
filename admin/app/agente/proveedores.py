"""El proveedor del modelo del asistente: quién responde cada ronda del bucle (`bucle.py`).

Hay dos, con la misma interfaz (`Proveedor`):

* `mnemo` (`modelo_mnemo.ProveedorMnemo`): los modelos y los créditos de la cuenta de Mnemo que el administrador
  conectó en Ajustes → Asistente (`mnemo_conexion.py`), por la herramienta MCP `mnemo_model_complete` (alcance
  `mnemo:model`). Es el de siempre: nadie copia claves.
* `anthropic` (`llm.ProveedorAnthropic`): la Messages API con `ANTHROPIC_API_KEY`, el «modo directo» (desarrollo o
  respaldo explícito). Solo se usa si no hay una conexión con Mnemo con `mnemo:model`.

Cada conversación guarda con qué proveedor se creó (`conversaciones.crear(..., proveedor=)`; las viejas, sin el campo,
son de `anthropic`) y sigue siempre con él: los historiales no se mezclan (los bloques `fallback` y las firmas del
razonamiento de uno no caben en el otro). Si su proveedor ya no está, la API responde 409 `proveedor` antes de abrir el
turno y el widget ofrece una conversación nueva.

Interfaz:

* `Proveedor` — `clave` («mnemo» | «anthropic», la que se guarda), `modelo` (el que se pide, para la conversación),
  `max_tokens`, `tope_imagenes` (base64 de las imágenes de los resultados de una ronda) y:
  - `async generar(sistema, mensajes, herramientas, *, max_tokens, esfuerzo, al_evento) -> Respuesta`: una ronda.
    `sistema` es el texto congelado de la conversación, `mensajes` el historial guardado tal cual (cada proveedor arma
    su forma de envío) y `herramientas` las definiciones congeladas. Mientras llega, llama `al_evento(ev)` con
    `{"tipo": "texto" | "progreso" | "texto_ronda", "texto"}`, `{"tipo": "aviso", "texto", "nivel"}` o
    `{"tipo": "herramienta", "id", "nombre"}` (un `tool_use` que empieza: el bucle le pone la etiqueta y lo anuncia).
  - `reintento(e, intento) -> float | None`: los segundos que hay que esperar antes de repetir la ronda tras el fallo
    `e` (`intento`: las repeticiones que ya se hicieron), o None si no vale la pena repetirla.
  - `explicar(e) -> (mensaje, codigo)`: el fallo para la persona (sin datos ni nombres de variables) y su código.
* `Respuesta` y `Uso`: lo que devuelve una ronda, ya en la forma que se guarda.
* `ErrorProveedor(mensaje, codigo)`: un fallo que el proveedor ya sabe explicar (no se repite).
* `clave_para_nueva(cfg, db)`, `para_nueva(app, cfg, db)` y `de_conversacion(app, cfg, db, conv)`: qué proveedor
  toca. Leen MongoDB (un documento por `_id`): desde código asíncrono, con `run_in_threadpool`.
* `async cerrar(app)`: al apagar, cierra los clientes que se crearon (Anthropic y Mnemo).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

log = logging.getLogger("panel")

MNEMO, ANTHROPIC = "mnemo", "anthropic"
CLAVES = (MNEMO, ANTHROPIC)
POR_DEFECTO = ANTHROPIC  # las conversaciones de antes de Mnemo no guardan el proveedor

# Lo que un proveedor manda al bucle mientras llega la ronda (ver `Proveedor.generar`)
Evento = dict
EVENTOS = frozenset({"texto", "progreso", "texto_ronda", "aviso", "herramienta"})


@dataclass(frozen=True)
class Uso:
    """Los tokens de una ronda (disjuntos: `entrada` no incluye lo leído de la caché) y, con Mnemo, los créditos que
    gastó la cuenta (None si no los dice: clave propia, cortesía o administración no descuentan)."""
    entrada: int = 0
    salida: int = 0
    cache_lectura: int = 0
    cache_escritura: int = 0
    creditos: float | None = None


@dataclass(frozen=True)
class Respuesta:
    """Una ronda del modelo, lista para guardar y reenviar.

    * `contenido`: los bloques del asistente en la forma que se guarda y se le reenvía al mismo proveedor (ya con su
      regla de reenvío).
    * `fin`: `end_turn`, `tool_use`, `max_tokens`, `refusal`, `pause_turn`, `model_context_window_exceeded` u `other`.
    * `modelo`: el que respondió (con Mnemo, «proveedor/modelo»).
    * `detalles`: `stop_details` (la categoría de un rechazo), si los hay.
    * `transformaciones`: lo que el proveedor cambió de la entrada (Anthropic), para auditoría.
    * `respaldos`: los avisos de cambio de modelo a mitad de la respuesta, para el historial."""
    contenido: list[dict]
    fin: str
    modelo: str
    uso: Uso = field(default_factory=Uso)
    detalles: dict | None = None
    transformaciones: list[dict] = field(default_factory=list)
    respaldos: list[str] = field(default_factory=list)


class ErrorProveedor(Exception):
    """Un fallo que el proveedor ya sabe explicar (la conversación no cabe, una respuesta ilegible…): `explicar` lo
    devuelve tal cual y no se repite la ronda."""

    def __init__(self, mensaje: str, codigo: str):
        super().__init__(mensaje)
        self.mensaje, self.codigo = mensaje, codigo


class Proveedor(Protocol):
    clave: str
    modelo: str
    max_tokens: int
    tope_imagenes: int

    async def generar(self, sistema: str, mensajes: list[dict], herramientas: list[dict], *, max_tokens: int,
                      esfuerzo: str, al_evento: Callable[[Evento], None]) -> Respuesta: ...

    def reintento(self, e: BaseException, intento: int) -> float | None: ...

    def explicar(self, e: BaseException) -> tuple[str, str]: ...


# ───────────────────────────── Cuál toca ─────────────────────────────

def _mnemo_con_modelo(db: Any) -> bool:
    if db is None:
        return False
    from .mnemo_conexion import con_modelo  # aquí: la conexión carga el cliente MCP y el cifrado
    return con_modelo(db)


def clave_para_nueva(cfg: Any, db: Any) -> str | None:
    """El proveedor con que empezaría una conversación nueva, sin armarlo: «mnemo» si hay una conexión «conectada»
    con `mnemo:model`; si no, «anthropic» si hay `ANTHROPIC_API_KEY`; si no, None (el asistente no tiene modelo)."""
    if _mnemo_con_modelo(db):
        return MNEMO
    if getattr(cfg, "anthropic_api_key", ""):
        return ANTHROPIC
    return None


def _armar(clave: str, app: Any, cfg: Any) -> Proveedor:
    if clave == MNEMO:
        from .modelo_mnemo import ProveedorMnemo
        return ProveedorMnemo(app, cfg)
    from .llm import ProveedorAnthropic
    return ProveedorAnthropic(app, cfg)


def para_nueva(app: Any, cfg: Any, db: Any) -> Proveedor | None:
    """El proveedor de una conversación nueva (Mnemo antes que Anthropic), o None si no hay ninguno."""
    clave = clave_para_nueva(cfg, db)
    return _armar(clave, app, cfg) if clave is not None else None


def de_conversacion(app: Any, cfg: Any, db: Any, conv: dict) -> Proveedor | None:
    """El proveedor con que se creó `conv` si sigue disponible; None si ya no está (no se cambia por otro)."""
    from .conversaciones import proveedor_de
    clave = proveedor_de(conv)
    if clave == MNEMO:
        return _armar(MNEMO, app, cfg) if _mnemo_con_modelo(db) else None
    if clave == ANTHROPIC:
        return _armar(ANTHROPIC, app, cfg) if getattr(cfg, "anthropic_api_key", "") else None
    return None


async def cerrar(app: Any) -> None:
    """Al apagar: el cliente de Anthropic, si este módulo lo creó, y el de Mnemo, si se llegó a armar."""
    try:
        from . import llm
        await llm.cerrar(app)
    except Exception as e:  # noqa: BLE001 - apagando: solo queda anotarlo
        log.warning("Asistente: no se pudo cerrar el cliente de Anthropic (%s)", type(e).__name__)
    mnemo = getattr(getattr(app, "state", None), "mnemo_cliente", None)
    if mnemo is not None:
        try:
            await mnemo.cerrar()
        except Exception as e:  # noqa: BLE001
            log.warning("Asistente: no se pudo cerrar el cliente de Mnemo (%s)", type(e).__name__)
