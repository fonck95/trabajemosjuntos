"""Servidor MCP de la presentación: un agente externo (Claude, Mnemo u otro cliente MCP) maneja la pantalla en off de una
persona del equipo con la misma herramienta `presentacion` que usa el asistente del panel.

Qué expone y qué no:
* Una sola herramienta, `presentacion` (`interfaz.presentacion_en_pantalla`): la propuesta 2028–2031, que es pública, y
  la pantalla en off de la persona dueña de la clave. Nada de personas, de la base ni de otras vistas: con esta clave no
  se lee ni se escribe ningún dato de habitantes.
* Transporte Streamable HTTP sin estado (revisiones 2025-11-25, 2025-06-18, 2025-03-26 y 2024-11-05): cada POST lleva un
  mensaje JSON-RPC y recibe la respuesta en JSON (sin SSE ni sesiones MCP). GET y DELETE responden 405.
* La clave (de «Cuenta → Agentes por MCP», `api/pantalla.py`) va en `Authorization: Bearer <clave>` o, para los clientes
  que solo aceptan una dirección, en `?clave=`. Vale mientras la persona esté activa, con la cuenta al día y con la
  misma clave del panel con que la creó. Se comprueba antes de leer el cuerpo.
* Peticiones con una cabecera Origin que no es la del panel se rechazan (403): un navegador no puede usarla desde otra
  página (la regla de MCP contra el «DNS rebinding»). No hay CORS.
* Hasta LIMITE_MINUTO peticiones por minuto por clave (429 con Retry-After).
La ruta (`/api/mcp`) no lleva sesión: está en `RUTAS_SIN_SESION`, así que la guardia no pide cookie, el límite de cupos
del servicio único (`LimitePanel`) lee el cuerpo con plazo y tope antes de darle cupo, y con MongoDB caído responde 503."""
from __future__ import annotations

import json
import logging
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError
from pymongo.database import Database

from ..acceso import PERMISOS
from ..agente.herramientas.base import ErrorHerramienta
from ..agente.herramientas.interfaz import (D_PRESENTACION, PresentacionEntrada, _esquema_presentacion,
                                            presentacion_en_pantalla)
from ..seguridad import ROLES_USUARIO, rechazo_de_cuenta, obtener_db
from .pantalla import huella_clave, huella_de_sesion

log = logging.getLogger("panel.mcp")
r = APIRouter(prefix="/api", tags=["mcp"])

PROTOCOLOS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
LIMITE_MINUTO = 120
NOMBRE = "presentacion"
INSTRUCCIONES = (
    "Maneja la presentación técnica de la propuesta Yondó 2028–2031 (lo que se construye, sin costos, sobre la maqueta "
    "3D del territorio y con modelos 3D del atlas) en la pantalla en off de la persona: la vista Presentación del panel "
    "abierta en modo en off en un proyector o un televisor, sin controles, que solo cambia con estas órdenes. Usa la "
    "herramienta presentacion: indice para conocer los capítulos, sus componentes y las inmersiones; ir a un capítulo y "
    "paso (te devuelve lo que muestra ese paso para explicarlo con esos datos); siguiente y anterior desde donde esté; "
    "explicar para poner una frase corta en pantalla; vista para el panel de texto, el índice o las fichas técnicas; "
    "visual para lo que se ve sin cambiar de paso (enfocar un componente, su ficha técnica, hoy frente al proyecto, la "
    "cámara aérea, oblicua o rasante, el rumbo, que gire, un modelo del atlas como la torre del hospital por dentro, el "
    "simulador sísmico o el modelo BIM, y el tema); pantalla_completa para que llene la ventana y estado para saber qué "
    "muestra y si está abierta. Cambia la pantalla solo cuando la persona pide algo concreto. Lo que pones en pantalla "
    "lo ve una sala: nunca datos de personas, «@» ni números de 7 o más dígitos.")
D_MCP = D_PRESENTACION.replace("en el panel de la persona o en su pantalla en off", "en la pantalla en off de la persona")

_usos: dict[str, deque] = {}


def _herramienta() -> dict:
    return {"name": NOMBRE, "title": "Presentación de la propuesta Yondó 2028–2031", "description": D_MCP,
            "inputSchema": _esquema_presentacion(),
            "annotations": {"title": "Presentación de la propuesta", "readOnlyHint": False, "destructiveHint": False,
                            "idempotentHint": False, "openWorldHint": False}}


def _error_http(estado: int, mensaje: str, **cabeceras) -> JSONResponse:
    return JSONResponse({"error": mensaje}, estado, headers=cabeceras or None)


def _rpc_error(id_: Any, codigo: int, mensaje: str, estado: int = 200) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": id_, "error": {"code": codigo, "message": mensaje}}, estado)


def _rpc(id_: Any, resultado: dict) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": id_, "result": resultado})


def _clave(request: Request, en_consulta: str | None) -> str | None:
    auth = request.headers.get("authorization") or ""
    if auth[:7].lower() == "bearer " and auth[7:].strip():
        return auth[7:].strip()
    return en_consulta or None


def identidad(db: Database, cfg, clave: str) -> int | None:
    """El uid dueño de la clave si sigue valiendo: la persona activa, con la cuenta al día, con un rol que ve la
    presentación y con la misma credencial con que la creó. Deja `usada` (a lo sumo una vez por minuto)."""
    doc = db.claves_mcp.find_one({"_id": huella_clave(clave)})
    if not doc or not isinstance(doc.get("uid"), int):
        return None
    uid = doc["uid"]
    if not doc.get("huella") or doc["huella"] != huella_de_sesion(db, cfg, uid):
        return None
    if uid != 0:
        u = db.usuarios.find_one({"_id": uid, "activo": True}, {"rol": 1})
        if not u or u.get("rol") not in ROLES_USUARIO:
            return None
        permisos = PERMISOS.get(u["rol"], frozenset())
        if "*" not in permisos and "presentacion.ver" not in permisos:
            return None
        if rechazo_de_cuenta({"uid": uid}, "/api/mcp", db) is not None:
            return None
    ahora = datetime.now(timezone.utc)
    usada = doc.get("usada")
    if not isinstance(usada, datetime) or (usada if usada.tzinfo else usada.replace(tzinfo=timezone.utc)) < \
            ahora - timedelta(minutes=1):
        db.claves_mcp.update_one({"_id": doc["_id"]}, {"$set": {"usada": ahora}})
    return uid


def _dentro_del_limite(huella: str, ahora: float | None = None) -> bool:
    ahora = time.monotonic() if ahora is None else ahora
    usos = _usos.setdefault(huella, deque())
    while usos and usos[0] <= ahora - 60:
        usos.popleft()
    if len(usos) >= LIMITE_MINUTO:
        return False
    usos.append(ahora)
    if len(_usos) > 1000:   # claves que ya no se usan
        for k in [k for k, v in _usos.items() if not v or v[-1] <= ahora - 60]:
            _usos.pop(k, None)
    return True


def _texto_de_validacion(e: ValidationError) -> str:
    partes = []
    for err in e.errors()[:5]:
        donde = ".".join(str(x) for x in err.get("loc", ()) if x != "__root__")
        msg = str(err.get("msg", "")).removeprefix("Value error, ")
        partes.append(f"{donde}: {msg}" if donde else msg)
    return "La entrada no es válida: " + "; ".join(partes)


async def llamar(db: Database, uid: int, nombre: Any, argumentos: Any) -> dict:
    """El resultado MCP de `tools/call`: los errores de la herramienta vuelven como `isError` (el agente los lee y
    corrige), no como errores del protocolo."""
    if nombre != NOMBRE:
        raise LookupError(nombre)
    try:
        entrada = PresentacionEntrada.model_validate(argumentos if isinstance(argumentos, dict) else {})
    except ValidationError as e:
        return {"content": [{"type": "text", "text": _texto_de_validacion(e)}], "isError": True}
    try:
        res = await presentacion_en_pantalla(db, uid, entrada, "mcp")
    except ErrorHerramienta as e:
        return {"content": [{"type": "text", "text": e.para_modelo()}], "isError": True}
    contenido = res.contenido if isinstance(res.contenido, dict) else {"texto": res.contenido}
    return {"content": [{"type": "text", "text": res.texto_para_modelo()}],
            "structuredContent": {"resumen": res.resumen, **contenido}, "isError": False}


async def atender(db: Database, uid: int, m: dict) -> JSONResponse | None:
    """La respuesta a un mensaje JSON-RPC, o None si es una notificación o una respuesta (202 sin cuerpo)."""
    if "id" not in m or "method" not in m:
        return None
    id_, metodo, params = m.get("id"), m.get("method"), m.get("params")
    if not isinstance(id_, (str, int)) or isinstance(id_, bool):
        return _rpc_error(None, -32600, "El id debe ser un texto o un número")
    params = params if isinstance(params, dict) else {}
    if metodo == "initialize":
        pedida = params.get("protocolVersion")
        return _rpc(id_, {"protocolVersion": pedida if pedida in PROTOCOLOS else PROTOCOLOS[0],
                          "capabilities": {"tools": {"listChanged": False}},
                          "serverInfo": {"name": "yondo-presentacion", "title": "Presentación Yondó 2028–2031",
                                         "version": "1"},
                          "instructions": INSTRUCCIONES})
    if metodo == "ping":
        return _rpc(id_, {})
    if metodo == "tools/list":
        return _rpc(id_, {"tools": [_herramienta()]})
    if metodo == "tools/call":
        try:
            return _rpc(id_, await llamar(db, uid, params.get("name"), params.get("arguments")))
        except LookupError:
            return _rpc_error(id_, -32602, f"No hay una herramienta {str(params.get('name'))[:60]!r}: solo «presentacion»")
    return _rpc_error(id_, -32601, f"Método no disponible: {str(metodo)[:60]}")


@r.post("/mcp")
async def mcp(request: Request, clave: str | None = Query(None, max_length=200), db: Database = Depends(obtener_db)):
    origen = request.headers.get("origin")
    if origen and origen != f"{request.url.scheme}://{request.url.netloc}":
        return _error_http(403, "Origen no permitido")
    version = request.headers.get("mcp-protocol-version")
    if version and version not in PROTOCOLOS:
        return _error_http(400, f"Versión del protocolo MCP no admitida: {version[:20]}")
    secreto = _clave(request, clave)
    uid = await run_in_threadpool(identidad, db, request.app.state.cfg, secreto) if secreto else None
    if uid is None:
        return _error_http(401, "Falta la clave MCP o ya no vale: créela en el panel, en Cuenta → Agentes por MCP",
                           **{"WWW-Authenticate": 'Bearer realm="yondo-presentacion"'})
    if not _dentro_del_limite(huella_clave(secreto)):
        return _error_http(429, "Demasiadas peticiones: espere un minuto", **{"Retry-After": "60"})
    try:
        m = json.loads(await request.body())
    except (ValueError, UnicodeDecodeError):
        return _rpc_error(None, -32700, "El cuerpo no es JSON", 400)
    if isinstance(m, list):
        return _rpc_error(None, -32600, "Un mensaje JSON-RPC por petición (sin lotes)", 400)
    if not isinstance(m, dict) or m.get("jsonrpc") != "2.0":
        return _rpc_error(None, -32600, "Se espera un mensaje JSON-RPC 2.0", 400)
    respuesta = await atender(db, uid, m)
    return respuesta if respuesta is not None else Response(status_code=202)


@r.get("/mcp")
@r.delete("/mcp")
def mcp_sin_flujo():
    return Response(status_code=405, headers={"Allow": "POST"})
