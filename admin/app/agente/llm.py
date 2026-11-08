"""El proveedor de Anthropic (`ProveedorAnthropic`, el «modo directo» con `ANTHROPIC_API_KEY`; ver `proveedores.py`):
el cliente, la forma de cada petición, el flujo de cada ronda y las reglas para reenviar lo que el modelo respondió.

* El cliente es `app.state.agente_cliente` si existe (las pruebas inyectan uno falso, sin red) o un `AsyncAnthropic`
  que se crea en la primera petición: nunca al importar ni en `crear_app`, que corren sin red y sin clave.
* Cada petición lleva el `system` y las herramientas congelados de la conversación (el razonamiento conservado y la
  caché exigen que ese prefijo no cambie), caché automática, pensamiento adaptativo y, en los modelos que lo admiten
  (`CAPACIDADES`), las notas de progreso (`display: "updates"`), el modelo de respaldo ante un rechazo
  (`fallbacks: "default"`) y el descarte de razonamiento que ya no casa (`block_binding: drop_block`), en vez de un 400.
  Con otro modelo solo va `thinking: {type: adaptive}`: sin betas ni respaldo.
* `reenviable`, `para_peticion` y `reintentable` vienen de la receta probada con el SDK 2.6.0 (ver docs/agente.md).
* `ProveedorAnthropic.generar` es una ronda en flujo: emite el texto, las notas de progreso (`Notas`), el inicio de
  cada herramienta y el aviso de un modelo de respaldo mientras llegan, y arma la `Respuesta` con el mensaje final.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

import anthropic
import httpx2

from .proveedores import ANTHROPIC, Evento, Respuesta, Uso

log = logging.getLogger("panel")

MAX_TOKENS = 32_000
# Lo que suman las imágenes (en base64) de los resultados de una ronda (el bucle además acota por MongoDB)
TOPE_IMAGENES = 8_000_000
ESPERA_REINTENTO_S = 0.5  # una ronda que falló de paso se repite tras 1 s y tras 2 s
BETA_RESPALDO = "server-side-fallback-2026-07-01"
BETA_NOVEDADES = "thinking-display-updates-2026-08-18"
BETA_VINCULO = "thinking-binding-controls-2026-08-01"
# El texto exacto de un bloque de progreso que reemplaza trabajo cortado (max_tokens): no es una nota para la persona
CENTINELA = "This part of the response was interrupted before it finished."
REINTENTOS_SDK = 2  # el SDK reintenta solo los fallos antes de abrir el flujo (429, 5xx, conexión)
# Sin un byte del modelo en este tiempo la ronda falla y se reintenta (los `ping` del flujo llegan cada pocos segundos)
PLAZO = httpx2.Timeout(120.0, connect=10.0)


@dataclass(frozen=True)
class Capacidades:
    respaldo: bool = False   # fallbacks="default" (beta server-side-fallback-2026-07-01)
    novedades: bool = False  # thinking.display="updates" (beta thinking-display-updates-2026-08-18)
    vinculo: bool = False    # thinking.block_binding (beta thinking-binding-controls-2026-08-01)


# Opus 5 no escribe notas de progreso (su texto entre herramientas llega como `text`), así que no lleva `display`
CAPACIDADES = {
    "claude-opus-5-5": Capacidades(respaldo=True, novedades=True, vinculo=True),
    "claude-sonnet-5-5": Capacidades(respaldo=True, novedades=True, vinculo=True),
    "claude-fable-5-1": Capacidades(respaldo=True, novedades=True, vinculo=True),
    "claude-opus-5": Capacidades(respaldo=True, vinculo=True),
}


def capacidades(modelo: str) -> Capacidades:
    return CAPACIDADES.get(modelo, Capacidades())


def parametros(cfg: Any, *, max_tokens: int = MAX_TOKENS, esfuerzo: str | None = None) -> dict:
    """Los parámetros de cada petición, salvo `system`, `tools` y `messages` (`esfuerzo`: por defecto
    `AGENTE_ESFUERZO`)."""
    cap = capacidades(cfg.agente_modelo)
    pensar: dict[str, Any] = {"type": "adaptive"}
    betas = []
    if cap.respaldo:
        betas.append(BETA_RESPALDO)
    if cap.novedades:
        pensar["display"] = "updates"
        betas.append(BETA_NOVEDADES)
    if cap.vinculo:
        pensar["block_binding"] = {"prefix_mismatch_behavior": "drop_block"}
        betas.append(BETA_VINCULO)
    p: dict[str, Any] = {"model": cfg.agente_modelo, "max_tokens": max_tokens, "thinking": pensar,
                         "output_config": {"effort": esfuerzo or cfg.agente_esfuerzo},
                         "cache_control": {"type": "ephemeral"}, "timeout": PLAZO}
    if cap.respaldo:
        p["fallbacks"] = "default"
    if betas:
        p["betas"] = betas
    return p


def sistema_para_peticion(texto: str) -> list[dict]:
    return [{"type": "text", "text": texto, "cache_control": {"type": "ephemeral"}}]


def cliente(app: Any, cfg: Any) -> anthropic.AsyncAnthropic:
    """El cliente de Anthropic de la aplicación: el inyectado o uno propio creado ahora (una vez por aplicación)."""
    c = getattr(app.state, "agente_cliente", None)
    if c is None:
        c = anthropic.AsyncAnthropic(api_key=cfg.anthropic_api_key, max_retries=REINTENTOS_SDK)
        app.state.agente_cliente, app.state.agente_cliente_propio = c, True
    return c


async def cerrar(app: Any) -> None:
    """Al apagar: cierra el cliente que creó este módulo (uno inyectado lo cierra quien lo inyectó)."""
    if getattr(app.state, "agente_cliente_propio", False):
        c, app.state.agente_cliente, app.state.agente_cliente_propio = app.state.agente_cliente, None, False
        try:
            await c.close()
        except Exception as e:  # noqa: BLE001 - apagando: solo queda anotarlo
            log.warning("Asistente: no se pudo cerrar el cliente de Anthropic (%s)", type(e).__name__)


def reenviable(bloques: list[dict]) -> list[dict]:
    """El contenido del asistente que se guarda y se reenvía tal cual, salvo dos reglas: un `thinking` sin firma (flujo
    cortado) es un 400 seguro, y tras un cambio de modelo a mitad de la respuesta se omite, antes del ÚLTIMO bloque
    `fallback`, lo que el modelo nuevo no puede retomar: thinking, redacted_thinking, tool_use (esas herramientas no se
    ejecutan), server_tool_use sin su resultado y los tipos desconocidos. Los bloques `fallback` quedan en su sitio."""
    corte = max((i for i, b in enumerate(bloques) if b.get("type") == "fallback"), default=-1)
    pareados = {b.get("tool_use_id") for b in bloques if str(b.get("type", "")).endswith("_tool_result")}
    out = []
    for i, b in enumerate(bloques):
        t = str(b.get("type", ""))
        if t == "thinking" and not b.get("signature"):
            continue
        conocido = t in ("text", "fallback") or t.endswith("_tool_result") or (
            t == "server_tool_use" and b.get("id") in pareados)
        if i < corte and not conocido:
            continue
        out.append(b)
    return out


def para_peticion(historial: list[dict]) -> list[dict]:
    """Une los mensajes `user` seguidos (tras un rechazo que no se reenvía, o un turno cortado antes de responder): la
    API exige que se alternen. Es una función pura del historial guardado, así el prefijo es el mismo en cada
    petición."""
    out: list[dict] = []
    for m in historial:
        if out and m["role"] == "user" == out[-1]["role"]:
            bloques = lambda c: [{"type": "text", "text": c}] if isinstance(c, str) else list(c)  # noqa: E731
            out[-1] = {"role": "user", "content": bloques(out[-1]["content"]) + bloques(m["content"])}
        else:
            out.append(m)
    return out


def reintentable(e: BaseException) -> bool:
    """¿Vale la pena repetir la ronda? Lo que el SDK no reintenta porque pasa con el flujo ya abierto: el JSON de una
    herramienta que no se pudo leer (sale del iterador, sin `tool_use_id` que responder), un corte o una espera
    vencida a mitad del cuerpo y un evento `error` de sobrecarga después del 200."""
    if type(e) is ValueError:
        return str(e).startswith("Unable to parse tool parameter JSON")
    if isinstance(e, httpx2.TransportError):
        return True
    return isinstance(e, anthropic.APIStatusError) and e.status_code == 200 and e.type in (
        "overloaded_error", "api_error")


def explicar(e: BaseException) -> tuple[str, str]:
    """(mensaje para la persona, código) de un fallo del modelo. Al registro va solo el tipo (`log` en el bucle)."""
    if isinstance(e, anthropic.AuthenticationError):
        return "El servicio del modelo rechazó la clave del panel. Avise al administrador.", "llm_clave"
    if isinstance(e, anthropic.PermissionDeniedError):
        return "La cuenta de Anthropic del panel no permite usar este modelo. Avise al administrador.", "llm_permiso"
    if isinstance(e, anthropic.NotFoundError):
        return "El modelo configurado para el asistente no existe. Avise al administrador.", "llm_modelo"
    if isinstance(e, anthropic.RateLimitError):
        return "El servicio del modelo está saturado o llegó a su límite. Intente de nuevo en unos minutos.", "llm_limite"
    if isinstance(e, (anthropic.BadRequestError, anthropic.UnprocessableEntityError)):
        return "El servicio del modelo rechazó la petición. Si se repite, empiece otra conversación.", "llm_peticion"
    if isinstance(e, anthropic.APIStatusError) and e.status_code == 402:
        return "La cuenta de Anthropic del panel no tiene saldo. Avise al administrador.", "llm_cuota"
    if isinstance(e, anthropic.APIStatusError):
        return "El modelo no está disponible en este momento. Intente de nuevo en un rato.", "llm_no_disponible"
    if isinstance(e, (anthropic.APIConnectionError, httpx2.TransportError)):
        return "No se pudo conectar con el servicio del modelo. Intente de nuevo en un rato.", "llm_conexion"
    if type(e) is ValueError:
        return "El modelo respondió algo que no se pudo leer. Intente de nuevo.", "llm_respuesta"
    return "El asistente falló al responder. Intente de nuevo.", "error"


def aviso_respaldo(bloque: dict) -> str:
    """El aviso de un bloque `fallback`: el modelo cambió a uno de respaldo a mitad de la respuesta."""
    destino = " ".join(str((bloque.get("to") or {}).get("model") or "").split())[:60] or "otro modelo"
    return f"El asistente pasó a un modelo de respaldo ({destino}) para seguir con la respuesta."


class Notas:
    """Notas de progreso de un bloque `thinking` (con `display: "updates"`): se emiten según llegan, salvo el texto
    fijo que reemplaza trabajo cortado (`CENTINELA`), que no es una nota para la persona."""

    def __init__(self) -> None:
        self.emitido = 0

    def delta(self, acumulado: str) -> str:
        if CENTINELA.startswith(acumulado):
            return ""  # todavía puede ser el centinela: se espera
        nuevo, self.emitido = acumulado[self.emitido:], len(acumulado)
        return nuevo

    def cerrar(self, completo: str) -> str:
        if completo == CENTINELA:
            return ""
        resto, self.emitido = completo[self.emitido:], len(completo)
        return resto


class ProveedorAnthropic:
    """La Messages API de Anthropic con `ANTHROPIC_API_KEY` (ver `proveedores.Proveedor`). Cada ronda va en flujo con
    el `system` y las herramientas congelados de la conversación y los parámetros de `parametros`."""

    clave = ANTHROPIC
    max_tokens = MAX_TOKENS
    tope_imagenes = TOPE_IMAGENES

    def __init__(self, app: Any, cfg: Any):
        self.app, self.cfg = app, cfg
        self.modelo = cfg.agente_modelo

    def __repr__(self) -> str:  # sin la clave
        return f"ProveedorAnthropic(modelo={self.modelo!r})"

    async def generar(self, sistema: str, mensajes: list[dict], herramientas: list[dict], *, max_tokens: int,
                      esfuerzo: str, al_evento: Callable[[Evento], None]) -> Respuesta:
        kw: dict[str, Any] = {"system": sistema_para_peticion(sistema), "messages": para_peticion(mensajes),
                              **parametros(self.cfg, max_tokens=max_tokens, esfuerzo=esfuerzo)}
        if herramientas:
            kw["tools"] = herramientas
        notas: Notas | None = None
        async with cliente(self.app, self.cfg).beta.messages.stream(**kw) as flujo:
            async for ev in flujo:
                t = ev.type
                if t == "text":
                    if ev.text:
                        al_evento({"tipo": "texto", "texto": ev.text})
                elif t == "thinking":
                    nuevo = notas.delta(ev.snapshot) if notas is not None else ""
                    if nuevo:
                        al_evento({"tipo": "progreso", "texto": nuevo})
                elif t == "content_block_start":
                    b = ev.content_block
                    if b.type == "thinking":
                        notas = Notas()
                    elif b.type == "tool_use":
                        al_evento({"tipo": "herramienta", "id": b.id, "nombre": b.name})
                    elif b.type == "fallback":
                        al_evento({"tipo": "aviso", "texto": aviso_respaldo(b.to_dict()), "nivel": "info"})
                elif t == "content_block_stop":
                    b = ev.content_block
                    if b.type == "thinking" and notas is not None:
                        resto = notas.cerrar(b.thinking or "")
                        if resto:
                            al_evento({"tipo": "progreso", "texto": resto})
                        notas = None
            msg = await flujo.get_final_message()
        contenido = reenviable([b.to_dict() for b in msg.content])
        u = msg.usage
        return Respuesta(
            contenido=contenido, fin=msg.stop_reason, modelo=msg.model,
            uso=Uso(entrada=u.input_tokens or 0, salida=u.output_tokens or 0,
                    cache_lectura=u.cache_read_input_tokens or 0, cache_escritura=u.cache_creation_input_tokens or 0),
            detalles=msg.stop_details.to_dict() if msg.stop_details else None,
            transformaciones=[x.to_dict() for x in msg.input_transformations or []],
            respaldos=[aviso_respaldo(b) for b in contenido if b.get("type") == "fallback"])

    def reintento(self, e: BaseException, intento: int) -> float | None:
        return ESPERA_REINTENTO_S * 2 ** (intento + 1) if reintentable(e) else None

    def explicar(self, e: BaseException) -> tuple[str, str]:
        return explicar(e)
