"""Quién usa el asistente, con qué herramientas y cuánto: los ajustes del asistente leídos con valores de respaldo.

* Los ajustes viven en `meta` (documento «ajustes») con los demás del panel: `agente` (`roles`, `escritura`,
  `mnemo_coordinadores`, `retencion_dias`), `agente_mensajes_diarios` (tope por rol), `agente_voz` (la voz del
  asistente: la del navegador o una voz clonada de Mnemo, quién la hace sonar y para qué; `agente/voz.py`) y
  `agente_adelanto` (la respuesta inmediata de cada pregunta, `agente/adelanto.py`; encendida por defecto). Se leen con
  `modelo.leer_ajustes` y se validan aquí otra vez: un valor que falta o que no tiene la forma esperada toma el valor
  por defecto, así un ajuste guardado a mano (o de una versión anterior) no abre ni rompe nada.
* Denegar por defecto: planilleros y consultores no usan el asistente hasta que el administrador los agrega a
  `agente.roles`, y un rol desconocido no tiene mensajes.
* Ofrecer una herramienta no autoriza nada: cada llamada vuelve a pasar por los permisos de la API. Pero lo que se
  ofrece se decide en cada turno con los ajustes vigentes, porque pudieron cambiar desde que se creó la conversación.
* Sin un proveedor del modelo (`proveedores.clave_para_nueva`: Mnemo conectado con `mnemo:model`, o
  `ANTHROPIC_API_KEY`) el asistente no está disponible para nadie: motivo `sin_configurar` y 503 antes de un turno.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from fastapi import HTTPException

from .. import modelo
from ..seguridad import rechazo_de_cuenta
from . import proveedores

ROLES = ("admin", "coordinador", "planillero", "consultor")
POR_DEFECTO: dict[str, Any] = {"roles": ["admin", "coordinador"], "escritura": True, "mnemo_coordinadores": False,
                               "retencion_dias": 30}
MENSAJES_POR_DEFECTO = {"admin": 300, "coordinador": 150, "planillero": 40, "consultor": 40}
RETENCION_DIAS = (1, 365)
MENSAJES_DIARIOS = (1, 5000)
# La voz del asistente (`agente_voz`): los mismos valores por defecto que `modelo.AJUSTES_POR_DEFECTO` y la misma forma
# que acepta `api/ajustes.py` (`VozAgente`; una prueba compara los dos lados)
MOTORES_VOZ = ("navegador", "mnemo")
VOZ_POR_DEFECTO: dict[str, Any] = {"motor": "mnemo", "voz": "", "nombre": "", "cuenta": "",
                                   "roles": ["admin", "coordinador"], "respuestas": True, "automatica": True}
# La respuesta inmediata (`agente_adelanto`): el mismo valor por defecto que `modelo.AJUSTES_POR_DEFECTO`
ADELANTO_POR_DEFECTO = True
# Las planillas físicas por foto (`agente_planillas`) y los datos por MCP (`agente_mcp`): los mismos valores por
# defecto que `modelo.AJUSTES_POR_DEFECTO` y los mismos rangos que acepta `api/ajustes.py` (una prueba compara los lados)
# Las fotos las suben A, K o P (el planillero tiene el papel; cotejar y cargar exigen `importar`: A y K); nunca el
# consultor. Las claves MCP con datos, solo A y K (y leer personas por MCP, solo quien puede exportar: A)
ROLES_PLANILLAS = ("admin", "coordinador", "planillero")
ROLES_MCP = ("admin", "coordinador")
PLANILLAS_POR_DEFECTO: dict[str, Any] = {"roles": ["admin", "coordinador"], "retencion_horas": 24,
                                         "otros_formatos": False}
RETENCION_HORAS = (1, 168)
MCP_POR_DEFECTO: dict[str, Any] = {"roles": ["admin"], "escritura": True, "llamadas_diarias": 2000,
                                   "personas_diarias": 300}
LLAMADAS_DIARIAS_MCP = (10, 20000)
PERSONAS_DIARIAS_MCP = (10, 5000)
ID_VOZ = re.compile(r"[A-Za-z0-9_.:-]{1,100}")   # el id de una voz en Mnemo (un ObjectId: 24 hexadecimales)
MAX_NOMBRE_VOZ = 60
HUELLA_CUENTA = re.compile(r"[0-9a-f]{32}")
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]")

SUGERENCIAS = {
    "admin": ["¿Cómo va la base? Dame los indicadores principales.",
              "Muéstrame en el mapa a las personas que faltan por ubicar.",
              "¿Qué pendientes de calidad hay para hoy?",
              "Resume las reuniones del último mes.",
              "Preséntame la propuesta 2028–2031, capítulo por capítulo."],
    "planillero": ["¿Qué tengo pendiente en mi trabajo?",
                   "¿Qué datos le faltan a la ficha que tengo abierta?",
                   "Busca a una persona por su nombre."],
    "consultor": ["¿A quién llamo ahora en mi cola?",
                  "Busca a una persona por su nombre.",
                  "Ayúdame a registrar el resultado de la llamada."],
}
SUGERENCIAS["coordinador"] = SUGERENCIAS["admin"]

# El 503 de un turno sin proveedor del modelo (sin nombres de variables: lo ve quien conversa)
SIN_CONFIGURAR = {"codigo": "sin_configurar", "mensaje": "El asistente no está conectado a un modelo: el administrador "
                                                         "lo conecta con Mnemo en Ajustes → Asistente."}


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


def nombre_de_voz(v: Any) -> str | None:
    """El nombre de una voz para mostrar: un renglón sin caracteres de control, con los espacios en uno, de hasta
    `MAX_NOMBRE_VOZ` caracteres; None si no es texto o trae caracteres de control (vienen de Mnemo o del formulario)."""
    if not isinstance(v, str) or _CONTROL.search(v):
        return None
    v = " ".join(v.split())
    return v if len(v) <= MAX_NOMBRE_VOZ else None


def ajustes_voz(ajustes: dict | None) -> dict:
    """Los ajustes `agente_voz` vigentes, completos y validados (una copia nueva en cada llamada): `motor`
    («navegador» o «mnemo»), `voz` (el id de la voz en Mnemo, o «»), `nombre`, `cuenta` (la huella de la cuenta de Mnemo
    con que se eligió, `mnemo_conexion.huella_cuenta`, o «»), `roles` (quién la hace sonar), `respuestas` y
    `automatica`. Con el motor «mnemo» y sin `voz`, suena la voz automática: la que Mnemo ofrece a las apps
    (`voz.automatica`). Lo que no tiene la forma esperada toma el valor por defecto."""
    crudo = (ajustes or {}).get("agente_voz")
    crudo = crudo if isinstance(crudo, dict) else {}
    roles = crudo.get("roles")
    if isinstance(roles, list):
        roles = sorted({r for r in roles if isinstance(r, str) and r in ROLES})
    else:
        roles = list(VOZ_POR_DEFECTO["roles"])
    booleano = lambda k: crudo[k] if isinstance(crudo.get(k), bool) else VOZ_POR_DEFECTO[k]  # noqa: E731
    voz = crudo.get("voz")
    voz = voz if isinstance(voz, str) and ID_VOZ.fullmatch(voz) else ""
    cuenta = crudo.get("cuenta")
    return {"motor": crudo["motor"] if crudo.get("motor") in MOTORES_VOZ else VOZ_POR_DEFECTO["motor"],
            "voz": voz, "nombre": (nombre_de_voz(crudo.get("nombre")) or "") if voz else "",
            "cuenta": cuenta if voz and isinstance(cuenta, str) and HUELLA_CUENTA.fullmatch(cuenta) else "",
            "roles": roles, "respuestas": booleano("respuestas"), "automatica": booleano("automatica")}


def adelanto(ajustes: dict | None) -> bool:
    """¿El asistente da la respuesta inmediata (`agente_adelanto`)? Lo que no es un booleano vale lo de por defecto."""
    v = (ajustes or {}).get("agente_adelanto")
    return v if isinstance(v, bool) else ADELANTO_POR_DEFECTO


def _roles(v: Any, por_defecto: list[str], validos: tuple[str, ...] = ROLES) -> list[str]:
    if isinstance(v, list):
        return sorted({r for r in v if isinstance(r, str) and r in validos})
    return list(por_defecto)


def ajustes_planillas(ajustes: dict | None) -> dict:
    """Los ajustes `agente_planillas` vigentes, completos y validados (una copia nueva en cada llamada): `roles` (quién
    sube fotos de planillas físicas: admin, coordinador o planillero), `retencion_horas` (cuánto se guardan la foto y
    lo leído) y `otros_formatos` (si además de la planilla de campo del panel se leen listas de asistencia u otros
    formatos, que pueden traer columnas sensibles: apagado por defecto)."""
    crudo = (ajustes or {}).get("agente_planillas")
    crudo = crudo if isinstance(crudo, dict) else {}
    horas = _entero(crudo.get("retencion_horas"), RETENCION_HORAS)
    otros = crudo.get("otros_formatos")
    return {"roles": _roles(crudo.get("roles"), PLANILLAS_POR_DEFECTO["roles"], ROLES_PLANILLAS),
            "retencion_horas": horas if horas is not None else PLANILLAS_POR_DEFECTO["retencion_horas"],
            "otros_formatos": otros if isinstance(otros, bool) else PLANILLAS_POR_DEFECTO["otros_formatos"]}


def ajustes_mcp(ajustes: dict | None) -> dict:
    """Los ajustes `agente_mcp` vigentes, completos y validados (una copia nueva en cada llamada): `roles` (quién crea
    claves MCP con datos), `escritura` (si una clave puede proponer cambios, que siempre se aprueban en el panel) y
    `llamadas_diarias` (tope por clave y día) y `personas_diarias` (a cuántas personas distintas por día puede ver una
    clave). Los roles: admin y coordinador."""
    crudo = (ajustes or {}).get("agente_mcp")
    crudo = crudo if isinstance(crudo, dict) else {}
    llamadas = _entero(crudo.get("llamadas_diarias"), LLAMADAS_DIARIAS_MCP)
    personas = _entero(crudo.get("personas_diarias"), PERSONAS_DIARIAS_MCP)
    escritura = crudo.get("escritura")
    return {"roles": _roles(crudo.get("roles"), MCP_POR_DEFECTO["roles"], ROLES_MCP),
            "escritura": escritura if isinstance(escritura, bool) else MCP_POR_DEFECTO["escritura"],
            "llamadas_diarias": llamadas if llamadas is not None else MCP_POR_DEFECTO["llamadas_diarias"],
            "personas_diarias": personas if personas is not None else MCP_POR_DEFECTO["personas_diarias"]}


def usa_planillas(quien: Any, ajustes: dict | None) -> bool:
    """¿Esta persona puede subir fotos de planillas físicas al asistente? Su rol en `agente_planillas.roles` (además
    de usar el asistente: `agente.roles`, que se revisa aparte)."""
    return getattr(quien, "rol", None) in ajustes_planillas(ajustes)["roles"]


def mensajes_diarios(ajustes: dict | None, rol: str | None) -> int:
    """Cuántos mensajes al asistente puede mandar una persona de ese rol en un día (hora de Colombia)."""
    crudo = (ajustes or {}).get("agente_mensajes_diarios")
    v = _entero(crudo.get(rol), MENSAJES_DIARIOS) if isinstance(crudo, dict) else None
    return v if v is not None else MENSAJES_POR_DEFECTO.get(rol or "", 0)


def leer(db) -> tuple[dict, dict]:
    """(ajustes del panel, ajustes del asistente). En los del panel, `agente`, `agente_mensajes_diarios`, `agente_voz` y
    `agente_adelanto` quedan ya validados: es lo que reciben las herramientas en `Contexto.ajustes`."""
    ajustes = modelo.leer_ajustes(db)
    agente = ajustes_agente(ajustes)
    ajustes["agente"] = agente
    ajustes["agente_mensajes_diarios"] = {r: mensajes_diarios(ajustes, r) for r in ROLES}
    ajustes["agente_voz"] = ajustes_voz(ajustes)
    ajustes["agente_adelanto"] = adelanto(ajustes)
    ajustes["agente_planillas"] = ajustes_planillas(ajustes)
    ajustes["agente_mcp"] = ajustes_mcp(ajustes)
    return ajustes, agente


def motivo(quien: Any, cfg: Any, agente: dict, sesion: dict | None = None, db: Any = None) -> str | None:
    """Por qué esta persona no puede usar el asistente ahora (None si puede): `sin_configurar` (no hay proveedor del
    modelo: ni Mnemo conectado con `mnemo:model` ni `ANTHROPIC_API_KEY`; sin `db` solo se mira la clave), `rol` (su
    rol no está habilitado) o `cuenta` (debe cambiar la clave o aceptar el compromiso)."""
    if proveedores.clave_para_nueva(cfg, db) is None:
        return "sin_configurar"
    if not quien.puede("agente.usar") or quien.rol not in agente["roles"]:
        return "rol"
    if sesion is not None and not quien.es_admin and rechazo_de_cuenta(sesion, "/api/agente/mensajes", db):
        return "cuenta"
    return None


def exigir(quien: Any, cfg: Any, agente: dict, db: Any) -> None:
    """Antes de abrir un turno: 503 sin proveedor del modelo y 403 si el rol no está habilitado (respuestas JSON
    normales, antes del flujo). Lee la conexión con Mnemo en MongoDB: desde código asíncrono, con
    `run_in_threadpool`."""
    if proveedores.clave_para_nueva(cfg, db) is None:
        raise HTTPException(503, dict(SIN_CONFIGURAR))
    if not quien.puede("agente.usar") or quien.rol not in agente["roles"]:
        raise HTTPException(403, {"codigo": "agente_apagado",
                                  "mensaje": "El asistente no está habilitado para su rol."})


def ofrecida(h: Any, quien: Any, agente: dict, cfg: Any, *, ajustes: dict | None = None) -> bool:
    """¿Se le ofrece (o se le deja usar) esta herramienta ahora? Permisos, el ajuste de escritura, la condición propia
    de la herramienta con los ajustes del asistente (`disponible`) y la que depende de los del panel
    (`disponible_ajustes`, con `ajustes` de `leer` o, sin ellos, los de defecto). La usan `herramientas.para`, las de
    Mnemo y el servidor MCP."""
    if not h.permitida(quien):
        return False
    if h.tipo == "escritura" and not agente.get("escritura", True):
        return False
    if h.disponible is not None and not h.disponible(quien, agente, cfg):
        return False
    extra = getattr(h, "disponible_ajustes", None)
    return extra is None or bool(extra(quien, ajustes if ajustes is not None else {}))


def origen_mnemo(url: Any) -> str | None:
    """`scheme://host` del servidor de Mnemo a partir de la dirección MCP de la conexión (`mnemo_conexion.vista(db)
    ["url"]`): el widget solo enlaza ahí (las aprobaciones) y a rutas del panel. None sin dirección."""
    if not isinstance(url, str) or not url:
        return None
    partes = urlsplit(url)
    return f"{partes.scheme}://{partes.netloc}" if partes.scheme and partes.netloc else None


def sugerencias(rol: str | None) -> list[str]:
    return list(SUGERENCIAS.get(rol or "", []))
