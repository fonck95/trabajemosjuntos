"""El proveedor de Mnemo (`ProveedorMnemo`, ver `proveedores.py`): cada ronda del bucle es una llamada a la herramienta
MCP `mnemo_model_complete` de la cuenta de Mnemo que el administrador conectó en Ajustes → Asistente (alcance
`mnemo:model`), con los modelos y los créditos de esa cuenta. Mnemo solo responde como modelo: las herramientas las
sigue corriendo el panel, con la sesión de quien conversa.

Contrato (Mnemo: `apps/api/src/agent-api/catalog/model.ts` y `docs/agentes-externos.md` §5.5):

* Entrada, en la forma de la Messages API: `system` (texto), `messages` (`text`, `image{media_type, data}`, `tool_use`,
  `tool_result{content: texto, is_error?}`, `thinking{text, signature?}`), `tools` (`name`, `description`,
  `input_schema`), `max_tokens`, `reasoning` (`off|low|medium|high`) y `model` (`{provider, model}`, o `{model}` con
  `principal` o `ligero`; sin él, el modelo por defecto de la cuenta).
* Salida en `structuredContent` (la copia en texto puede venir recortada): `content` (`text`, `tool_use`, `thinking`),
  `stop_reason` (`end_turn|tool_use|max_tokens|refusal|other`), `model` y `usage` (con `credits` si la pagó el plan).
* Avance: con `_meta.progressToken`, cada trozo de texto del modelo llega antes del resultado como
  `notifications/progress` (`message`: el trozo). Los `tool_use` y el razonamiento no llegan a trozos.
* Errores: `isError` con `{error: {code, message, details?}}`: `PLAN_REQUIRED`, `CREDITS_EXHAUSTED`, `RATE_LIMITED`
  (`details.reason`: `provider` o `concurrency`), `UNAVAILABLE`, `INVALID_ARGUMENT` (`details.reason: "context_window"`
  si la conversación no cabe en el modelo, `details.available` si el modelo pedido no es de la cuenta), `TIMEOUT` e
  `INTERNAL`.

Por qué está hecho así:

* El historial se guarda en la forma del panel y se traduce en cada ronda (`para_mnemo`, una función pura del
  historial: el prefijo es el mismo en cada petición y el proveedor de la cuenta reutiliza su caché). Un `tool_result`
  de Mnemo es solo texto: el de una herramienta que devolvió imágenes se vuelve texto y sus imágenes van como bloques
  sueltos después de los `tool_result` del mismo mensaje. Lo que Mnemo no conoce (bloques de respaldo y de
  herramientas de servidor) no viaja, y las herramientas van sin `eager_input_streaming`.
* Lo que devuelve se guarda en la forma de Mnemo (`text`, `tool_use`, `thinking{text, signature}`) y se le reenvía
  tal cual, razonamiento incluido (Mnemo descarta el que ya no vale). El razonamiento no se muestra: con Mnemo son
  resúmenes del modelo, no notas para la persona. Un `tool_use` cuyo id ya está en la conversación, o se repite en la
  misma respuesta (Mnemo numera `call_0`, `call_1`… en cada respuesta cuando el proveedor no da ids), recibe uno nuevo
  antes de anunciarlo y de guardarlo (`ids_unicos`): el bucle y el widget distinguen las llamadas por id.
* El texto llega en vivo: cada aviso de avance es un evento `texto`. Al llegar el resultado, si el texto final de la
  ronda no empieza por lo que ya se mostró, un evento `texto_ronda` con el texto completo de la ronda lo reemplaza en
  el widget (si solo falta el final, el final va como `texto`). Los `tool_use` se anuncian al final (`herramienta`).
* Mnemo lee cuerpos de hasta 4 MB: si la petición pasa de `mnemo_cliente.MAX_PETICION`, las imágenes de los mensajes
  viejos se cambian por un aviso, de la más vieja a la más nueva, y si aun así no cabe, la conversación es «larga».
  Por eso el tope de imágenes de una ronda es más bajo que con Anthropic (`TOPE_IMAGENES`).
* Reintentos (`reintento`): un corte de red, un plazo vencido o un 5xx esperan 1 y 2 s; `RATE_LIMITED` (o un 429),
  10 y 20 s, o de 2 a 5 s si es el tope de llamadas a la vez; `UNAVAILABLE` (el proveedor de la cuenta falló, o la
  cuenta no tiene modelo), una vez tras 1 s; una conexión que cambió a mitad (otra cuenta, otra vuelta), medio
  segundo. El bucle no repite si con la espera se pasaría del tope del turno.
* Los errores se explican sin datos ni nombres de variables (`explicar`), con códigos que el widget distingue:
  `mnemo_conexion` (sin conexión, caída, revocada, alterada o el 401 que sigue tras renovar), `mnemo_plan` (el plan
  no incluye usar sus modelos desde el panel, o no incluye el modelo de frontera elegido para el panel),
  `mnemo_creditos`, `mnemo_sin_modelo` (sin modelo disponible en la cuenta, o la conexión sin `mnemo:model`),
  `larga`, `llm_peticion`, `llm_limite`, `llm_conexion`, `llm_no_disponible` y `llm_respuesta`.
* Nada del contenido va al registro: solo códigos y tipos de excepción.
"""
from __future__ import annotations

import json
import logging
import math
import random
import re
import secrets
from typing import Any, Callable

from fastapi.concurrency import run_in_threadpool

from . import conversaciones as conv_db
from . import mnemo_cliente as mc
from . import mnemo_conexion
from .herramientas.base import ErrorHerramienta
from .proveedores import MNEMO, ErrorProveedor, Evento, Respuesta, Uso

log = logging.getLogger("panel")

HERRAMIENTA = "mnemo_model_complete"
MAX_TOKENS = 16_000
TOPE_IMAGENES = 1_500_000      # base64 de las imágenes de los resultados de una ronda (el cuerpo entero cabe en 4 MB)
PLAZO_S = 185.0                # Mnemo corta a los 170 s (TIMEOUT); con avance es el plazo sin avisos
TOPE_S = 185.0                 # la llamada entera
MARGEN_SOBRE = 2_000           # lo que agrega el sobre JSON-RPC de `tools/call` a los argumentos
TEXTO_MAX = 400_000            # Mnemo: un texto (un bloque, el system, un resultado de herramienta)
DESCRIPCION_MAX = 8_000        # Mnemo: la descripción de una herramienta
IMAGEN_MAX = 3_000_000         # Mnemo: una imagen en base64
TIPOS_IMAGEN = ("image/png", "image/jpeg", "image/gif", "image/webp")
FINES = ("end_turn", "tool_use", "max_tokens", "refusal", "other")
ALIAS_MODELO = ("principal", "ligero")
# AGENTE_ESFUERZO → `reasoning` de Mnemo (que no tiene «xhigh» ni «max»)
ESFUERZOS = {"low": "low", "medium": "medium", "high": "high", "xhigh": "high", "max": "high"}
ESPERA_RED_S = 1.0             # corte de red, plazo vencido o 5xx: 1 s y 2 s
ESPERA_RITMO_S = 10.0          # RATE_LIMITED o 429: 10 s y 20 s
ESPERA_A_LA_VEZ_S = (2.0, 5.0)  # RATE_LIMITED por llamadas a la vez: una de las otras termina pronto
ESPERA_CAMBIO_S = 0.5          # la conexión cambió a mitad: se repite con la nueva

_NOMBRE = re.compile(r"[a-zA-Z0-9_-]{1,64}")
# Un id de `tool_use` que sirve tal cual: el widget y la API de confirmaciones lo toman hasta 100 caracteres, y la regla
# de la Messages API (a la que Mnemo lo reenvía si la cuenta usa Anthropic) es [a-zA-Z0-9_-]
_ID = re.compile(r"[a-zA-Z0-9_-]{1,100}")

MENSAJE_SIN_PERMISO = ("La conexión con Mnemo no tiene permiso para usar sus modelos: el administrador tiene que "
                       "volver a conectarla en Ajustes → Asistente dejando marcado «Usar tus modelos de IA y tus "
                       "créditos» (si Mnemo no muestra esa casilla, hay que actualizar Mnemo).")
MENSAJE_URL = ("La dirección de la conexión con Mnemo no es válida: el administrador tiene que volver a conectarla en "
               "Ajustes → Asistente.")
MENSAJE_PLAN = ("El plan de la cuenta de Mnemo conectada no incluye usar sus modelos desde el panel. Avise al "
                "administrador: puede revisarlo en Mnemo.")
MENSAJE_PLAN_MODELO = ("El plan de la cuenta de Mnemo conectada no incluye el modelo que tiene elegido el panel. Avise "
                       "al administrador: puede usar el modelo por defecto de la cuenta o ampliar el plan en Mnemo.")
MENSAJE_CREDITOS = ("Se acabaron los créditos de Mnemo de esta semana de la cuenta conectada. Avise al administrador: "
                    "puede esperar a la semana siguiente o ampliar el plan en Mnemo.")
MENSAJE_SIN_MODELO = ("La cuenta de Mnemo conectada no tiene un modelo disponible ahora (sin un modelo configurado, "
                      "con su clave rechazada o con el proveedor caído). Si se repite, avise al administrador.")
MENSAJE_MODELO_AJENO = ("El modelo que el panel le pide a Mnemo no está entre los de la cuenta conectada. Avise al "
                        "administrador.")
MENSAJE_LARGA = "La conversación ya es muy larga: empiece una nueva para seguir."
MENSAJE_PETICION = "El modelo rechazó la petición. Si se repite, empiece otra conversación."
MENSAJE_LIMITE = "Mnemo está recibiendo demasiadas peticiones del panel. Intente de nuevo en un minuto."
MENSAJE_LIMITE_PROVEEDOR = ("El proveedor del modelo de la cuenta de Mnemo está limitando las peticiones. Intente de "
                            "nuevo en unos minutos.")
MENSAJE_RED = "No se pudo conectar con Mnemo. Intente de nuevo en un rato."
MENSAJE_PLAZO = "Mnemo no respondió a tiempo. Intente de nuevo en un rato."
MENSAJE_PLAZO_MODELO = "El modelo tardó demasiado en responder. Intente de nuevo; si se repite, pida algo más corto."
MENSAJE_NO_DISPONIBLE = "Mnemo no pudo pedirle la respuesta al modelo. Intente de nuevo en un rato."
MENSAJE_ILEGIBLE = "Mnemo respondió algo que no se pudo leer. Intente de nuevo."
MENSAJE_ERROR = "El asistente falló al responder. Intente de nuevo."
MARCADOR_IMAGEN = ("[Imagen omitida: la conversación ya pesa demasiado para volver a mandarla. Si todavía hace falta, "
                   "vuelve a pedirla.]")
IMAGEN_ROTA = "[Imagen omitida: no tiene un formato que el modelo acepte.]"
NOTA_IMAGENES = "[{n} imagen(es) de este resultado van aparte, después de los resultados.]"


# ───────────────────────────── Del historial del panel a la forma de Mnemo ─────────────────────────────

def _texto(v: Any) -> str:
    return v[:TEXTO_MAX] if isinstance(v, str) else ""


def _imagen(b: dict) -> dict | None:
    """Un bloque `image` (el del panel, con `source` base64, o ya en la forma de Mnemo) como lo acepta Mnemo; None si
    no sirve."""
    fuente = b.get("source") if isinstance(b.get("source"), dict) else None
    if fuente is not None:
        tipo, datos = fuente.get("media_type"), fuente.get("data")
        if fuente.get("type") not in (None, "base64"):
            return None
    else:
        tipo, datos = b.get("media_type"), b.get("data")
    if tipo not in TIPOS_IMAGEN or not isinstance(datos, str) or not datos or len(datos) > IMAGEN_MAX:
        return None
    return {"type": "image", "media_type": tipo, "data": datos}


def _resultado(b: dict) -> tuple[dict, list[dict]]:
    """Un `tool_result` con su contenido como texto, y las imágenes que traía (van aparte)."""
    contenido = b.get("content")
    imagenes: list[dict] = []
    if isinstance(contenido, list):
        textos = []
        for x in contenido:
            if not isinstance(x, dict):
                continue
            if x.get("type") == "text" and isinstance(x.get("text"), str):
                textos.append(x["text"])
            elif x.get("type") == "image":
                img = _imagen(x)
                imagenes.append(img or {"type": "text", "text": IMAGEN_ROTA})
        texto = "\n".join(textos)
        if imagenes:
            texto += ("\n" if texto else "") + NOTA_IMAGENES.format(n=len(imagenes))
    else:
        texto = contenido if isinstance(contenido, str) else ""
    r: dict[str, Any] = {"type": "tool_result", "tool_use_id": str(b.get("tool_use_id") or ""),
                         "content": _texto(texto)}
    if b.get("is_error") is True:
        r["is_error"] = True
    return r, imagenes


def _de_usuario(bloques: list) -> list[dict]:
    """Los `tool_result` primero (Anthropic lo exige y Mnemo no reordena), después sus imágenes y al final lo demás."""
    resultados: list[dict] = []
    imagenes: list[dict] = []
    resto: list[dict] = []
    for b in bloques:
        if not isinstance(b, dict):
            continue
        t = b.get("type")
        if t == "tool_result":
            r, imgs = _resultado(b)
            resultados.append(r)
            imagenes += imgs
        elif t == "text" and isinstance(b.get("text"), str):
            resto.append({"type": "text", "text": _texto(b["text"])})
        elif t == "image":
            resto.append(_imagen(b) or {"type": "text", "text": IMAGEN_ROTA})
    return resultados + imagenes + resto


def _de_asistente(bloques: list) -> list[dict]:
    """Texto, `tool_use` y el razonamiento que devolvió Mnemo, tal cual. Lo demás (respaldo, herramientas de servidor,
    razonamiento con otra forma, texto vacío) no viaja."""
    out: list[dict] = []
    for b in bloques:
        if not isinstance(b, dict):
            continue
        t = b.get("type")
        if t == "text" and isinstance(b.get("text"), str):
            if b["text"]:
                out.append({"type": "text", "text": _texto(b["text"])})
        elif t == "tool_use":
            out.append({"type": "tool_use", "id": str(b.get("id") or ""), "name": str(b.get("name") or ""),
                        "input": b["input"] if isinstance(b.get("input"), dict) else {}})
        elif t == "thinking" and isinstance(b.get("text"), str):
            out.append(_razonamiento(b))
    return out


def _razonamiento(b: dict) -> dict:
    r = {"type": "thinking", "text": b["text"]}
    if isinstance(b.get("signature"), str) and b["signature"]:
        r["signature"] = b["signature"]
    return r


def para_mnemo(historial: list[dict]) -> list[dict]:
    """Los mensajes guardados en la forma de `mnemo_model_complete`. Un mensaje que queda vacío no viaja, y dos
    seguidos del mismo rol se juntan (tras un rechazo que no se reenvía, o un turno cortado antes de responder): la
    API del modelo exige que se alternen. Es una función pura del historial: el prefijo es el mismo en cada petición."""
    out: list[dict] = []
    for m in historial:
        rol, contenido = m.get("role"), m.get("content")
        bloques = [{"type": "text", "text": contenido}] if isinstance(contenido, str) else (
            contenido if isinstance(contenido, list) else [])
        if rol == "user":
            nuevos = _de_usuario(bloques)
        elif rol == "assistant":
            nuevos = _de_asistente(bloques)
        else:
            continue
        if not nuevos:
            continue
        if out and out[-1]["role"] == rol:
            out[-1] = {"role": rol, "content": out[-1]["content"] + nuevos}
        else:
            out.append({"role": rol, "content": nuevos})
    return out


def herramientas_para_mnemo(definiciones: list[dict]) -> list[dict]:
    """Las definiciones congeladas de la conversación como las acepta Mnemo: nombre, descripción y esquema (sin
    `eager_input_streaming` ni nada más)."""
    out = []
    for d in definiciones or []:
        if isinstance(d, dict) and isinstance(d.get("name"), str) and isinstance(d.get("input_schema"), dict):
            out.append({"name": d["name"], "description": str(d.get("description") or "")[:DESCRIPCION_MAX],
                        "input_schema": d["input_schema"]})
    return out


def modelo_pedido(valor: Any) -> dict | None:
    """`MNEMO_MODELO` como el `model` de Mnemo: `principal` y `ligero` sin proveedor, `<proveedor>/<modelo>` partido
    en la primera barra (el modelo puede llevar más). Vacía: None (el modelo por defecto de la cuenta)."""
    v = valor.strip() if isinstance(valor, str) else ""
    if not v:
        return None
    if v in ALIAS_MODELO:
        return {"model": v}
    proveedor, _, modelo = v.partition("/")
    return {"provider": proveedor, "model": modelo} if proveedor and modelo else None


def argumentos(sistema: str, mensajes: list[dict], herramientas: list[dict], *, max_tokens: int, esfuerzo: str,
               modelo: Any = None) -> dict:
    """Los argumentos de `mnemo_model_complete` para una ronda (sin acotar su tamaño: `ajustar`)."""
    args: dict[str, Any] = {"system": _texto(sistema), "messages": para_mnemo(mensajes)}
    tools = herramientas_para_mnemo(herramientas)
    if tools:
        args["tools"] = tools
    args["max_tokens"] = max_tokens
    args["reasoning"] = ESFUERZOS.get(esfuerzo, "medium")
    pedido = modelo_pedido(modelo)
    if pedido is not None:
        args["model"] = pedido
    return args


def _peso(x: Any) -> int:
    """Los bytes de `x` en el JSON que manda `mnemo_cliente` (UTF-8, sin espacios)."""
    return len(json.dumps(x, ensure_ascii=False, separators=(",", ":")).encode("utf-8", "replace"))


def ajustar(args: dict, tope: int | None = None) -> dict:
    """`args` si la petición cabe en `tope` (por defecto `mnemo_cliente.MAX_PETICION`). Si no, con las imágenes de los
    mensajes viejos (todos menos el último) cambiadas por un aviso, de la más vieja a la más nueva, hasta que quepa; si
    ni así cabe, `ErrorProveedor` «larga». No toca `args`."""
    tope = mc.MAX_PETICION if tope is None else tope
    exceso = _peso(args) + MARGEN_SOBRE - tope
    if exceso <= 0:
        return args
    marcador = {"type": "text", "text": MARCADOR_IMAGEN}
    mensajes = list(args.get("messages") or [])
    for i, m in enumerate(mensajes[:-1]):
        if exceso <= 0:
            break
        if not isinstance(m.get("content"), list) or not any(b.get("type") == "image" for b in m["content"]):
            continue
        nuevos = []
        for b in m["content"]:
            if exceso > 0 and b.get("type") == "image":
                exceso -= _peso(b) - _peso(marcador)
                nuevos.append(dict(marcador))
            else:
                nuevos.append(b)
        mensajes[i] = {"role": m["role"], "content": nuevos}
    nuevo = {**args, "messages": mensajes}
    if _peso(nuevo) + MARGEN_SOBRE > tope:
        log.warning("Mnemo: la conversación no cabe en una petición al modelo")
        raise ErrorProveedor(MENSAJE_LARGA, "larga")
    log.info("Mnemo: se omitieron imágenes viejas para que la conversación quepa en la petición")
    return nuevo


# ───────────────────────────── De la respuesta de Mnemo a lo que se guarda ─────────────────────────────

def _id_nuevo() -> str:
    return "toolu_mnemo_" + secrets.token_hex(8)


def _id_herramienta(v: Any) -> str:
    """El id tal cual si sirve (`_ID`); si no (vacío, largo o con caracteres raros), uno nuevo: con uno de más de 100
    caracteres el widget recortaría el de su tarjeta y la aprobación no encontraría la llamada."""
    return v if isinstance(v, str) and _ID.fullmatch(v) else _id_nuevo()


def ids_usados(mensajes: list[dict]) -> set[str]:
    """Los ids de `tool_use` (y de sus `tool_result`) que ya están en el historial."""
    usados: set[str] = set()
    for m in mensajes:
        contenido = m.get("content") if isinstance(m, dict) else None
        for b in contenido if isinstance(contenido, list) else []:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use" and isinstance(b.get("id"), str):
                usados.add(b["id"])
            elif b.get("type") == "tool_result" and isinstance(b.get("tool_use_id"), str):
                usados.add(b["tool_use_id"])
    return usados


def ids_unicos(contenido: list[dict], usados: set[str]) -> list[dict]:
    """`contenido` (de `contenido_de`) con un id nuevo en cada `tool_use` cuyo id ya está en la conversación
    (`usados`) o se repite en la misma respuesta. Cuando el proveedor de la cuenta no da ids, Mnemo los numera en cada
    respuesta (`call_0`, `call_1`…): repetidos, el bucle juntaría sus resultados y el widget, que pinta la conversación
    por id, no mostraría la tarjeta de aprobación nueva. No toca `contenido`."""
    vistos = set(usados)
    out = []
    for b in contenido:
        if b.get("type") == "tool_use":
            if b["id"] in vistos:
                nuevo = _id_nuevo()
                while nuevo in vistos:  # pragma: no cover - 64 bits al azar
                    nuevo = _id_nuevo()
                b = {**b, "id": nuevo}
            vistos.add(b["id"])
        out.append(b)
    return out


def _nombre_herramienta(v: Any) -> str:
    """El nombre tal cual si cumple la regla de Mnemo; si no, uno que la cumpla (no existe en la conversación, así
    que el panel responde «no existe»; con el nombre crudo, la próxima petición sería inválida para siempre)."""
    if isinstance(v, str) and _NOMBRE.fullmatch(v):
        return v
    return re.sub(r"[^a-zA-Z0-9_-]", "_", v if isinstance(v, str) else "")[:64] or "herramienta_desconocida"


def contenido_de(bloques: Any) -> list[dict]:
    """Los bloques que devolvió Mnemo en la forma que se guarda y se le reenvía: `text`, `tool_use` (con su entrada
    como objeto) y `thinking` (con su firma). Lo que no tiene esa forma se descarta, y también un texto vacío:
    reenviarlo sería inválido en cada ronda que siga."""
    out: list[dict] = []
    for b in bloques if isinstance(bloques, list) else []:
        if not isinstance(b, dict):
            continue
        t = b.get("type")
        if t == "text" and isinstance(b.get("text"), str):
            if b["text"]:
                out.append({"type": "text", "text": b["text"]})
        elif t == "tool_use":
            out.append({"type": "tool_use", "id": _id_herramienta(b.get("id")),
                        "name": _nombre_herramienta(b.get("name")),
                        "input": b["input"] if isinstance(b.get("input"), dict) else {}})
        elif t == "thinking" and isinstance(b.get("text"), str):
            out.append(_razonamiento(b))
    return out


def _numero(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0 else None


def uso_de(u: Any) -> Uso:
    u = u if isinstance(u, dict) else {}
    entero = lambda k: int(_numero(u.get(k)) or 0)  # noqa: E731
    return Uso(entrada=entero("input_tokens"), salida=entero("output_tokens"),
               cache_lectura=entero("cache_read_tokens"), creditos=_numero(u.get("credits")))


def modelo_de(m: Any) -> str:
    """«proveedor/modelo» de la respuesta (lo que haya), para el historial."""
    m = m if isinstance(m, dict) else {}
    partes = [" ".join(v.split())[:160] for v in (m.get("provider"), m.get("model"))
              if isinstance(v, str) and v.strip()]
    return "/".join(partes) or MNEMO


# ───────────────────────────── El proveedor ─────────────────────────────

def _sin_cliente(db: Any) -> ErrorHerramienta:
    """Por qué no hay cliente de Mnemo ahora (la conexión se cayó, se desconectó o su dirección no sirve)."""
    v = mnemo_conexion.vista(db)
    if v["estado"] == "caida":
        return ErrorHerramienta(mnemo_conexion.mensaje_caida(v.get("motivo")), mc.COD_TOKEN,
                                detalle={"conexion": v.get("motivo") or "caida"})
    if v["estado"] == "conectada":
        return ErrorHerramienta(MENSAJE_URL, mc.COD_TOKEN, detalle={"conexion": "error"})
    return ErrorHerramienta(mnemo_conexion.MENSAJE_SIN_CONEXION, mc.COD_TOKEN, detalle={"conexion": "sin_conectar"})


def _de_mnemo(e: BaseException) -> tuple[str | None, dict]:
    """(código de Mnemo, `details`) de un error que devolvió Mnemo (`isError`); (None, {}) si es otra cosa."""
    if isinstance(e, ErrorHerramienta) and e.codigo == mc.COD_MNEMO and isinstance(e.detalle, dict):
        codigo, detalles = e.detalle.get("code"), e.detalle.get("details")
        return (codigo if isinstance(codigo, str) else None), (detalles if isinstance(detalles, dict) else {})
    return None, {}


def _conexion(e: ErrorHerramienta) -> str | None:
    return e.detalle.get("conexion") if isinstance(e.detalle, dict) else None


class ProveedorMnemo:
    """Los modelos de la cuenta de Mnemo conectada (ver `proveedores.Proveedor` y el docstring del módulo)."""

    clave = MNEMO
    max_tokens = MAX_TOKENS
    tope_imagenes = TOPE_IMAGENES

    def __init__(self, app: Any, cfg: Any):
        self.app, self.cfg = app, cfg
        self.modelo = getattr(cfg, "mnemo_modelo", "") or "principal"

    def __repr__(self) -> str:
        return f"ProveedorMnemo(modelo={self.modelo!r})"

    async def generar(self, sistema: str, mensajes: list[dict], herramientas: list[dict], *, max_tokens: int,
                      esfuerzo: str, al_evento: Callable[[Evento], None]) -> Respuesta:
        # Fuera del bucle de eventos: con imágenes son megas de JSON que medir
        args = await run_in_threadpool(self._argumentos, sistema, mensajes, herramientas, max_tokens, esfuerzo)
        cliente = await run_in_threadpool(mc.cliente_de, self.app)
        if cliente is None:
            raise await run_in_threadpool(_sin_cliente, self.app.state.db)
        emitido: list[str] = []

        def al_progreso(aviso: dict) -> None:
            trozo = aviso.get("message")
            if isinstance(trozo, str) and trozo:
                emitido.append(trozo)
                al_evento({"tipo": "texto", "texto": trozo})

        res = await cliente.llamar(HERRAMIENTA, args, PLAZO_S, al_progreso, tope=TOPE_S)
        datos = res.get("structuredContent")
        if not isinstance(datos, dict) or not isinstance(datos.get("content"), list):
            log.warning("Mnemo: la respuesta del modelo no trae structuredContent")
            raise ErrorProveedor(MENSAJE_ILEGIBLE, "llm_respuesta")
        # Antes de anunciar y de guardar: cada `tool_use` con un id que no esté ya en la conversación
        contenido = ids_unicos(contenido_de(datos["content"]), ids_usados(mensajes))
        fin = datos.get("stop_reason") if datos.get("stop_reason") in FINES else "other"
        final, ya = "".join(b["text"] for b in contenido if b["type"] == "text"), "".join(emitido)
        if final != ya:
            if final.startswith(ya):
                al_evento({"tipo": "texto", "texto": final[len(ya):]})
            else:  # lo mostrado no es el comienzo del texto final: el widget lo reemplaza entero
                al_evento({"tipo": "texto_ronda", "texto": final})
        for b in contenido:
            if b["type"] == "tool_use":
                al_evento({"tipo": "herramienta", "id": b["id"], "nombre": b["name"]})
        return Respuesta(contenido=contenido, fin=fin, modelo=modelo_de(datos.get("model")),
                         uso=uso_de(datos.get("usage")))

    def _argumentos(self, sistema: str, mensajes: list[dict], herramientas: list[dict], max_tokens: int,
                    esfuerzo: str) -> dict:
        return ajustar(conv_db.limpio(argumentos(sistema, mensajes, herramientas, max_tokens=max_tokens,
                                                 esfuerzo=esfuerzo, modelo=getattr(self.cfg, "mnemo_modelo", ""))))

    def reintento(self, e: BaseException, intento: int) -> float | None:
        if not isinstance(e, ErrorHerramienta):
            return None
        if e.codigo in (mc.COD_RED, mc.COD_PLAZO):
            return ESPERA_RED_S * 2 ** intento
        if e.codigo == mc.COD_TOKEN:
            return ESPERA_CAMBIO_S if _conexion(e) == "cambio" else None
        if e.codigo != mc.COD_MNEMO:
            return None
        codigo, detalles = _de_mnemo(e)
        if codigo == "RATE_LIMITED" or (codigo is None and e.estado == 429):
            if detalles.get("reason") == "concurrency":
                return random.uniform(*ESPERA_A_LA_VEZ_S)
            return ESPERA_RITMO_S * 2 ** intento
        if codigo is None and isinstance(e.estado, int) and e.estado >= 500:
            return ESPERA_RED_S * 2 ** intento
        if codigo == "UNAVAILABLE" and intento == 0:
            # Mnemo lo da también cuando el proveedor de la cuenta falló (ya tras sus propios reintentos): se repite
            # una vez. Si la cuenta no tiene modelo, vuelve a fallar al instante y sin gastar
            return ESPERA_RED_S
        return None

    def explicar(self, e: BaseException) -> tuple[str, str]:
        if isinstance(e, ErrorProveedor):
            return e.mensaje, e.codigo
        if not isinstance(e, ErrorHerramienta):
            return MENSAJE_ERROR, "error"
        if e.codigo == mc.COD_TOKEN:
            return e.mensaje, "mnemo_conexion"
        if e.codigo == mc.COD_NO_DISPONIBLE:
            return MENSAJE_SIN_PERMISO, "mnemo_sin_modelo"
        if e.codigo == mc.COD_RED:
            return MENSAJE_RED, "llm_conexion"
        if e.codigo == mc.COD_PLAZO:
            return MENSAJE_PLAZO, "llm_conexion"
        codigo, detalles = _de_mnemo(e)
        if codigo == "PLAN_REQUIRED":
            # Un modelo de frontera elegido para el panel que el plan no incluye: sin él, el modelo por defecto sirve
            if detalles.get("feature") == "frontier_models":
                return MENSAJE_PLAN_MODELO, "mnemo_plan"
            return MENSAJE_PLAN, "mnemo_plan"
        if codigo == "CREDITS_EXHAUSTED":
            return MENSAJE_CREDITOS, "mnemo_creditos"
        if codigo == "UNAVAILABLE":
            return MENSAJE_SIN_MODELO, "mnemo_sin_modelo"
        if codigo == "INVALID_ARGUMENT":
            if detalles.get("reason") == "context_window":
                return MENSAJE_LARGA, "larga"
            if "available" in detalles:
                return MENSAJE_MODELO_AJENO, "mnemo_sin_modelo"
            return MENSAJE_PETICION, "llm_peticion"
        if codigo == "RATE_LIMITED" or (codigo is None and e.estado == 429):
            return (MENSAJE_LIMITE_PROVEEDOR if detalles.get("reason") == "provider" else MENSAJE_LIMITE), "llm_limite"
        if codigo == "TIMEOUT":
            return MENSAJE_PLAZO_MODELO, "llm_no_disponible"
        if codigo is None and e.estado == 413:
            return MENSAJE_LARGA, "larga"
        if codigo is None and isinstance(e.estado, int) and (e.estado == 404 or 300 <= e.estado < 400):
            return e.mensaje, "mnemo_conexion"  # la dirección de la conexión no es la de su servidor MCP
        return MENSAJE_NO_DISPONIBLE, "llm_no_disponible"
