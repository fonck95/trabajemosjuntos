"""Quién usa el asistente, con qué herramientas y cuánto: los ajustes del asistente leídos con valores de respaldo.

* Los ajustes viven en `meta` (documento «ajustes») con los demás del panel: `agente` (`roles`, `escritura`,
  `mnemo_coordinadores`, `retencion_dias`), `agente_mensajes_diarios` (tope por rol), `agente_voz` (la voz del
  asistente: la del navegador o una voz clonada de Mnemo, quién la hace sonar y para qué; `agente/voz.py`),
  `agente_adelanto` (la respuesta inmediata de cada pregunta, `agente/adelanto.py`; encendida por defecto),
  `agente_planillas` (las planillas físicas por foto: solo el administrador y los coordinadores), `agente_mcp` (los
  datos por MCP) y `agente_politicos` (si el asistente y los agentes por MCP reciben los datos políticos que el panel
  ya muestra a cada rol). Se leen con `modelo.leer_ajustes` y se validan aquí otra vez: un valor que falta o que no
  tiene la forma esperada toma el valor por defecto, así un ajuste guardado a mano (o de una versión anterior) no abre
  ni rompe nada.
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

from .. import acceso, modelo
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
# Las fotos de planillas las suben, leen, cotejan y cargan solo A y K (las rutas exigen `importar`): nunca el
# planillero ni el consultor, aunque un ajuste guardado de antes los nombre (`ajustes_planillas` los quita). Las claves
# MCP con datos, solo A y K (y leer personas por MCP, solo quien puede exportar: A)
ROLES_PLANILLAS = ("admin", "coordinador")
ROLES_MCP = ("admin", "coordinador")
PLANILLAS_POR_DEFECTO: dict[str, Any] = {"roles": ["admin", "coordinador"], "retencion_horas": 24,
                                         "otros_formatos": False}
RETENCION_HORAS = (1, 168)
MCP_POR_DEFECTO: dict[str, Any] = {"roles": ["admin"], "escritura": True, "llamadas_diarias": 2000,
                                   "personas_diarias": 300}
LLAMADAS_DIARIAS_MCP = (10, 20000)
PERSONAS_DIARIAS_MCP = (10, 5000)
# Los datos políticos (`agente_politicos`): si el asistente (`asistente`) y los agentes por MCP (`mcp`) reciben el tipo
# de persona, el «Liderado por», las listas, la lista de líderes con sus conteos, los filtros por ellos y las fuentes
# políticas de importación, cada rol solo lo que el panel ya le muestra. Los mismos valores por defecto que
# `modelo.AJUSTES_POR_DEFECTO` y la misma forma que acepta `api/ajustes.py` (`PoliticosAgente`)
VIAS_POLITICOS = ("asistente", "mcp")
POLITICOS_POR_DEFECTO: dict[str, bool] = {"asistente": True, "mcp": True}
ID_VOZ = re.compile(r"[A-Za-z0-9_.:-]{1,100}")   # el id de una voz en Mnemo (un ObjectId: 24 hexadecimales)
MAX_NOMBRE_VOZ = 60
HUELLA_CUENTA = re.compile(r"[0-9a-f]{32}")
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029]")

# Lo que la bienvenida del chat ofrece a cada rol (botones que mandan la frase): solo lo que ese rol puede pedir con
# los ajustes por defecto (A y K: análisis, también por líder con `agente_politicos`, planillas por foto y calidad de
# datos; P y C, su trabajo y las fichas: las planillas por foto no son suyas), lo que más rinde y lo que muestra lo que
# el asistente sabe hacer. Pocas: el widget las apila todas
SUGERENCIAS = {
    "admin": ["¿Qué deberíamos priorizar esta semana?",
              "¿En qué barrios y veredas llevamos más tiempo sin ir?",
              "¿Qué líderes tienen más votantes sin contactar?",
              "¿Qué planillas por foto hay por cargar?",
              "¿Hay fichas duplicadas o conflictos de cédula por resolver?",
              "Muéstrame en el mapa a las personas que faltan por ubicar.",
              "Preséntame la propuesta 2028–2031, capítulo por capítulo."],
    "planillero": ["¿Qué tengo pendiente en mi trabajo?",
                   "¿Qué datos le faltan a la ficha que tengo abierta?",
                   "¿Cuándo fue el último contacto con la persona de esta ficha?",
                   "Busca a una persona por su nombre."],
    "consultor": ["¿A quién llamo ahora en mi cola?",
                  "Ayúdame a registrar el resultado de la llamada.",
                  "¿Qué acercamientos tiene ya la persona que estoy llamando?",
                  "El número que marqué está equivocado: márcalo en la ficha.",
                  "Busca a una persona por su nombre."],
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
    sube fotos de planillas físicas: admin o coordinador; un «planillero» guardado de antes se quita),
    `retencion_horas` (cuánto se guardan la foto y lo leído) y `otros_formatos` (si además de la planilla de campo del
    panel se leen listas de asistencia u otros formatos, que pueden traer columnas sensibles: apagado por defecto)."""
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


def ajustes_politicos(ajustes: dict | None) -> dict:
    """Los ajustes `agente_politicos` vigentes, completos y validados (una copia nueva en cada llamada): `asistente`
    (el chat del panel) y `mcp` (los agentes externos con clave de datos), booleanos. Lo que no es un booleano vale lo
    de por defecto (encendido)."""
    crudo = (ajustes or {}).get("agente_politicos")
    crudo = crudo if isinstance(crudo, dict) else {}
    return {k: crudo[k] if isinstance(crudo.get(k), bool) else POLITICOS_POR_DEFECTO[k] for k in VIAS_POLITICOS}


def usa_politicos(ajustes: dict | None, via: str | None = "chat") -> bool:
    """¿Los datos políticos pueden llegar por esta vía? `via` es la de `Contexto.via`: «mcp» mira `agente_politicos.mcp`
    y cualquier otra (el chat), `agente_politicos.asistente`. Solo enciende la vía: qué ve cada rol lo siguen decidiendo
    los permisos y `proyeccion.tipo_visible`, como en el panel."""
    return ajustes_politicos(ajustes)["mcp" if via == "mcp" else "asistente"]


def usa_planillas(quien: Any, ajustes: dict | None) -> bool:
    """¿Esta persona puede subir fotos de planillas físicas al asistente? Solo A y K (`ROLES_PLANILLAS`), con su rol
    en `agente_planillas.roles` (además de usar el asistente: `agente.roles`, que se revisa aparte)."""
    rol = getattr(quien, "rol", None)
    return rol in ROLES_PLANILLAS and rol in ajustes_planillas(ajustes)["roles"]


def fotos_permitidas(ajustes: dict | None) -> bool:
    """¿El compromiso de confidencialidad vigente (`compromiso_version`) deja fotografiar planillas físicas para
    subirlas por el panel (`acceso.compromiso_permite_fotos`)? Si no, no se sube ninguna foto (409 `compromiso_fotos`)
    y el chat no ofrece la cámara; lo ya subido se sigue revisando, cotejando y cargando."""
    return acceso.compromiso_permite_fotos((ajustes or {}).get("compromiso_version"))


def mensajes_diarios(ajustes: dict | None, rol: str | None) -> int:
    """Cuántos mensajes al asistente puede mandar una persona de ese rol en un día (hora de Colombia)."""
    crudo = (ajustes or {}).get("agente_mensajes_diarios")
    v = _entero(crudo.get(rol), MENSAJES_DIARIOS) if isinstance(crudo, dict) else None
    return v if v is not None else MENSAJES_POR_DEFECTO.get(rol or "", 0)


def leer(db) -> tuple[dict, dict]:
    """(ajustes del panel, ajustes del asistente). En los del panel, `agente`, `agente_mensajes_diarios`, `agente_voz`,
    `agente_adelanto`, `agente_planillas`, `agente_mcp` y `agente_politicos` quedan ya validados: es lo que reciben las
    herramientas en `Contexto.ajustes`."""
    ajustes = modelo.leer_ajustes(db)
    agente = ajustes_agente(ajustes)
    ajustes["agente"] = agente
    ajustes["agente_mensajes_diarios"] = {r: mensajes_diarios(ajustes, r) for r in ROLES}
    ajustes["agente_voz"] = ajustes_voz(ajustes)
    ajustes["agente_adelanto"] = adelanto(ajustes)
    ajustes["agente_planillas"] = ajustes_planillas(ajustes)
    ajustes["agente_mcp"] = ajustes_mcp(ajustes)
    ajustes["agente_politicos"] = ajustes_politicos(ajustes)
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


# Las sugerencias que dependen de un ajuste: sin él, la bienvenida no las ofrece (el asistente no podría responderlas)
SUGERENCIA_POLITICA = "¿Qué líderes tienen más votantes sin contactar?"
SUGERENCIA_PLANILLAS = "¿Qué planillas por foto hay por cargar?"


def sugerencias(rol: str | None, ajustes: dict | None = None, *, planillas: bool = True) -> list[str]:
    """Las preguntas de la bienvenida del rol. Con `ajustes`, sin la de los datos políticos si `agente_politicos`
    está apagado para el asistente; con `planillas=False`, sin la de las planillas por foto."""
    out = list(SUGERENCIAS.get(rol or "", []))
    if ajustes is not None and not usa_politicos(ajustes, "chat"):
        out = [s for s in out if s != SUGERENCIA_POLITICA]
    return out if planillas else [s for s in out if s != SUGERENCIA_PLANILLAS]
