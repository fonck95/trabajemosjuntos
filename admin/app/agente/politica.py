"""Quién usa el asistente, con qué herramientas y cuánto: los ajustes del asistente leídos con valores de respaldo.

* Los ajustes viven en `meta` (documento «ajustes») con los demás del panel: `agente` (`roles`, `escritura`,
  `mnemo_coordinadores`, `retencion_dias`) y `agente_mensajes_diarios` (tope por rol). Se leen con
  `modelo.leer_ajustes` y se validan aquí otra vez: un valor que falta o que no tiene la forma esperada toma el valor
  por defecto, así un ajuste guardado a mano (o de una versión anterior) no abre ni rompe nada.
* Denegar por defecto: planilleros y consultores no usan el asistente hasta que el administrador los agrega a
  `agente.roles`, y un rol desconocido no tiene mensajes.
* Ofrecer una herramienta no autoriza nada: cada llamada vuelve a pasar por los permisos de la API. Pero lo que se
  ofrece se decide en cada turno con los ajustes vigentes, porque pudieron cambiar desde que se creó la conversación.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from fastapi import HTTPException

from .. import modelo
from ..seguridad import rechazo_de_cuenta

ROLES = ("admin", "coordinador", "planillero", "consultor")
POR_DEFECTO: dict[str, Any] = {"roles": ["admin", "coordinador"], "escritura": True, "mnemo_coordinadores": False,
                               "retencion_dias": 30}
MENSAJES_POR_DEFECTO = {"admin": 300, "coordinador": 150, "planillero": 40, "consultor": 40}
RETENCION_DIAS = (1, 365)
MENSAJES_DIARIOS = (1, 5000)

SUGERENCIAS = {
    "admin": ["¿Cómo va la base? Dame los indicadores principales.",
              "Muéstrame en el mapa a las personas que faltan por ubicar.",
              "¿Qué pendientes de calidad hay para hoy?",
              "Resume las reuniones del último mes."],
    "planillero": ["¿Qué tengo pendiente en mi trabajo?",
                   "¿Qué datos le faltan a la ficha que tengo abierta?",
                   "Busca a una persona por su nombre."],
    "consultor": ["¿A quién llamo ahora en mi cola?",
                  "Busca a una persona por su nombre.",
                  "Ayúdame a registrar el resultado de la llamada."],
}
SUGERENCIAS["coordinador"] = SUGERENCIAS["admin"]


def _entero(v: Any, rango: tuple[int, int]) -> int | None:
    if isinstance(v, bool) or not isinstance(v, int):
        return None
    return v if rango[0] <= v <= rango[1] else None


def ajustes_agente(ajustes: dict | None) -> dict:
    """Los ajustes `agente` vigentes, completos y validados (una copia nueva en cada llamada)."""
    crudo = (ajustes or {}).get("agente")
    crudo = crudo if isinstance(crudo, dict) else {}
    roles = crudo.get("roles")
    if isinstance(roles, list):
        roles = sorted({r for r in roles if isinstance(r, str) and r in ROLES})
    else:
        roles = list(POR_DEFECTO["roles"])
    booleano = lambda k: crudo[k] if isinstance(crudo.get(k), bool) else POR_DEFECTO[k]  # noqa: E731
    dias = _entero(crudo.get("retencion_dias"), RETENCION_DIAS)
    return {"roles": roles, "escritura": booleano("escritura"), "mnemo_coordinadores": booleano("mnemo_coordinadores"),
            "retencion_dias": dias if dias is not None else POR_DEFECTO["retencion_dias"]}


def mensajes_diarios(ajustes: dict | None, rol: str | None) -> int:
    """Cuántos mensajes al asistente puede mandar una persona de ese rol en un día (hora de Colombia)."""
    crudo = (ajustes or {}).get("agente_mensajes_diarios")
    v = _entero(crudo.get(rol), MENSAJES_DIARIOS) if isinstance(crudo, dict) else None
    return v if v is not None else MENSAJES_POR_DEFECTO.get(rol or "", 0)


def leer(db) -> tuple[dict, dict]:
    """(ajustes del panel, ajustes del asistente). En los del panel, `agente` y `agente_mensajes_diarios` quedan ya
    validados: es lo que reciben las herramientas en `Contexto.ajustes`."""
    ajustes = modelo.leer_ajustes(db)
    agente = ajustes_agente(ajustes)
    ajustes["agente"] = agente
    ajustes["agente_mensajes_diarios"] = {r: mensajes_diarios(ajustes, r) for r in ROLES}
    return ajustes, agente


def motivo(quien: Any, cfg: Any, agente: dict, sesion: dict | None = None, db: Any = None) -> str | None:
    """Por qué esta persona no puede usar el asistente ahora (None si puede): `sin_configurar` (falta la clave de
    Anthropic), `rol` (su rol no está habilitado) o `cuenta` (debe cambiar la clave o aceptar el compromiso)."""
    if not cfg.agente_configurado:
        return "sin_configurar"
    if not quien.puede("agente.usar") or quien.rol not in agente["roles"]:
        return "rol"
    if sesion is not None and not quien.es_admin and rechazo_de_cuenta(sesion, "/api/agente/mensajes", db):
        return "cuenta"
    return None


def exigir(quien: Any, cfg: Any, agente: dict) -> None:
    """Antes de abrir un turno: 503 sin la clave de Anthropic y 403 si el rol no está habilitado (respuestas JSON
    normales, antes del flujo)."""
    if not cfg.agente_configurado:
        raise HTTPException(503, {"codigo": "sin_configurar",
                                  "mensaje": "El asistente no está configurado: falta la variable ANTHROPIC_API_KEY."})
    if not quien.puede("agente.usar") or quien.rol not in agente["roles"]:
        raise HTTPException(403, {"codigo": "agente_apagado",
                                  "mensaje": "El asistente no está habilitado para su rol."})


def ofrecida(h: Any, quien: Any, agente: dict, cfg: Any) -> bool:
    """¿Se le ofrece (o se le deja usar) esta herramienta ahora? Las mismas reglas de `herramientas.para`, para las
    que no son fijas (Mnemo): permisos, el ajuste de escritura y la condición propia de la herramienta."""
    if not h.permitida(quien):
        return False
    if h.tipo == "escritura" and not agente.get("escritura", True):
        return False
    return h.disponible is None or bool(h.disponible(quien, agente, cfg))


def origen_mnemo(url: Any) -> str | None:
    """`scheme://host` del servidor de Mnemo a partir de la dirección MCP de la conexión (`mnemo_conexion.vista(db)
    ["url"]`): el widget solo enlaza ahí (las aprobaciones) y a rutas del panel. None sin dirección."""
    if not isinstance(url, str) or not url:
        return None
    partes = urlsplit(url)
    return f"{partes.scheme}://{partes.netloc}" if partes.scheme and partes.netloc else None


def sugerencias(rol: str | None) -> list[str]:
    return list(SUGERENCIAS.get(rol or "", []))
