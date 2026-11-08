"""La conexión del panel con la cuenta de Mnemo del administrador: OAuth 2.1 con PKCE S256, registro dinámico (RFC
7591), indicador de recurso (RFC 8707) e `iss` en la vuelta (RFC 9207); los tokens cifrados en la base y su
renovación sin carreras. Nadie copia claves: el administrador conecta desde Ajustes → Asistente, inicia sesión en
Mnemo, da permiso y vuelve.

Interfaz (la usan `api/agente_mnemo.py`, `mnemo_cliente.cliente_de`, `api/agente.py` y el proveedor del modelo):

* `vista(db, cfg=None) -> dict` — la conexión para mostrar, sin descifrar nada: `{"estado": "sin_conectar" |
  "conectada" | "caida", "motivo": "revocada" | "clave" | "error" | None, "url": str | None, "cuenta": str | None,
  "alcances": [str], "modelo": bool, "desde": iso | None}`; con `cfg`, además `"url_sugerida": str | None`
  (`MNEMO_MCP_URL`, o la última dirección con que se conectó).
* `con_modelo(db) -> bool` — ¿hay una conexión «conectada» con `mnemo:model` (Mnemo puede poner el modelo)?
* `conectada(db) -> dict | None` — `{"version", "conexion", "url_mcp"}` de la conexión «conectada» (lo que usa
  `mnemo_cliente.cliente_de` para armar y rehacer el cliente), o None.
* `FuenteTokens(app, conexion=None)` — los access tokens de la conexión para `mnemo_cliente.ClienteMnemo`:
  `await token()` y `await invalidar(usado)` (ver la clase).
* `async iniciar(app, quien, *, url, redirect_uri, sesion) -> str` — descubre, registra el cliente si hace falta,
  guarda el pendiente y devuelve la URL de autorización de Mnemo.
* `async volver(app, quien, *, sesion, state, code, iss, error, error_description) -> dict` — canjea el código,
  guarda la conexión cifrada y devuelve `vista(db, cfg)`.
* `async desconectar(app, quien) -> dict` — revoca la concesión con el refresh y borra la conexión local; devuelve
  `vista(db, cfg)` más `"revocada": bool | None`.
* `ErrorConexion(codigo, mensaje, estado=400)` — un paso que no se pudo hacer (la API lo responde tal cual).
* `instalar(db, cfg, datos, tokens, quien=None)` — guarda una conexión sin pasar por el flujo (pruebas).

Dónde vive: un documento de `meta` (`_id: "mnemo_conexion"`), sin índices nuevos:

    {_id, version: int, estado: "conectada" | "caida", motivo, conexion (id de esta conexión), url_mcp, recurso,
     emisor, endpoints: {authorize, token, register, revoke}, client_id, redirect_uri, alcances, cuenta: {sub,
     nombre?, correo?}, cifrado (access + refresh), vence (del access), renovando_hasta, renovador, conectada_por:
     {uid, usuario}, conectada_en, renovada_en, caida_en, ultima_url,
     pendiente: {state_h, sesion, verificador_cifrado, url_mcp, recurso, emisor, endpoints, client_id, redirect_uri,
                 pedidos, iss_requerido, expira} | None,
     clientes: [{emisor, redirect_uri, client_id}]}

Por qué está hecho así (verificado contra Mnemo en local):

* Nada de tokens en claro en la base, en el registro ni en las respuestas: los tokens van cifrados con AES-GCM
  (`cifrado.py`) con una clave que no está en la base (`seguridad.llave_mnemo`), atados a `emisor|client_id`. El
  verificador PKCE del pendiente, también. El `state` se guarda como hash. Al registro van códigos de estado y tipos
  de excepción, nunca URLs con secretos ni cuerpos.
* El pendiente es uno solo (un «Conectar» nuevo lo reemplaza) y está atado a la sesión que lo pidió (`s["_id"]`, el
  hash de la cookie): se toma y se borra en un solo paso (`find_one_and_update`), así un `code` nunca se canjea dos
  veces (Mnemo revocaría la conexión entera). La conexión vieja sigue viva hasta que la nueva termina.
* El `client_id` del registro dinámico se guarda por `(emisor, redirect_uri)` y se reutiliza: antes se comprueba que
  Mnemo lo conozca (un refresh inventado da `invalid_grant` si existe e `invalid_client` si no), porque un cliente
  desconocido en `/oauth/authorize` deja al administrador en una página de error de Mnemo que no vuelve al panel.
* Se piden `openid profile email` (para «Conectado como …»: el `id_token` llega directo del endpoint por TLS y solo se
  lee su carga, sin verificar la firma), `mnemo:model` y lo que necesitan las herramientas que ofrece el panel
  (`herramientas/mnemo.alcances`). Nunca `mnemo:forms.responses`: son datos de otras personas.
* Reconectar la MISMA cuenta con el mismo cliente nunca revoca lo viejo: en Mnemo es la misma concesión y se llevaría
  los tokens nuevos. Con otra cuenta (otro `sub`), otro cliente u otro Mnemo, el refresh viejo se revoca.
* Desconectar revoca con el REFRESH (`token_type_hint=refresh_token`): revocar con el access deja una conexión
  «zombi» en «Tu cuenta» de Mnemo.
* Renovar: el access dura 60 min y se renueva si le quedan menos de `MARGEN` o tras un 401 (`invalidar`). El refresh
  rota en cada uso y Mnemo revoca la concesión entera si llega uno ya usado, así que hay cerrojo: en el proceso, una
  tarea compartida por bucle de eventos (quien espera usa `asyncio.shield`: si el turno se corta a mitad, la
  renovación termina y se guarda igual); entre procesos (un despliegue solapa contenedores), un arriendo en el
  documento tomado con compare-and-set (`version`, `estado`, `renovando_hasta` vencido) y el guardado condicionado a
  `version` y `renovador`. El refresh nuevo se guarda ANTES de usar el access nuevo. `invalid_grant` (caducada,
  reusada, revocada o cuenta desactivada: Mnemo no las distingue) deja la conexión «caida». Un error de red suelta el
  arriendo: si Mnemo alcanzó a rotar, el siguiente intento dará `invalid_grant` (no se puede evitar).
* Si lo cifrado no descifra (cambiaron `ADMIN` o `password`), la conexión queda «caida» con motivo «clave».
* Las llamadas salientes son asíncronas (httpx2), con plazos cortos, sin seguir redirecciones y con cuerpos acotados.
  Las pruebas inyectan un transporte en `app.state.mnemo_transporte` (sin red), como `app.state.agente_cliente` en
  `llm.py`.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import hmac
import json
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

import httpx2
from fastapi.concurrency import run_in_threadpool
from pymongo import ReturnDocument

from .. import db as bd
from .. import seguridad
from . import cifrado
from . import mnemo_cliente as mc
from .herramientas.base import ErrorHerramienta

log = logging.getLogger("panel")

ID = "mnemo_conexion"
ESTADOS = ("conectada", "caida")
ALCANCE_MODELO = "mnemo:model"
ALCANCES_OIDC = ("openid", "profile", "email")
NOMBRE_CLIENTE = "Panel Trabajemos juntos"
AGENTE = f"{mc.CLIENTE['name']}/{mc.CLIENTE['version']}"

VIGENCIA_PENDIENTE = timedelta(minutes=10)
MARGEN = timedelta(minutes=5)       # se renueva si al access le queda menos que esto
ARRIENDO = timedelta(seconds=60)    # más que el plazo de la petición de renovación, con holgura
PLAZO_S = 10.0                      # descubrimiento, registro y revocación
PLAZO_TOKEN_S = 20.0                # canje y renovación
PLAZO_CONEXION_S = 5.0
ESPERA_OTRO_S = 30.0                # lo que se espera a que otro proceso (o tarea) termine de renovar
SONDEO_S = 0.2
VIDA_POR_DEFECTO_S = 3600           # si Mnemo no dice `expires_in`
MAX_CUERPO = 256 * 1024             # metadatos, registro y tokens: JSON pequeños
MAX_URL = 300
MAX_TOKEN = 4_096
MAX_CLIENTES = 10
MAX_ALCANCES = 40
GUARDAR_INTENTOS = 3

# Qué se quita de la conexión al desconectar (se quedan `version`, `clientes`, `ultima_url` y el pendiente)
CAMPOS_CONEXION = ("estado", "motivo", "conexion", "url_mcp", "recurso", "emisor", "endpoints", "client_id",
                   "redirect_uri", "alcances", "cuenta", "cifrado", "vence", "renovando_hasta", "renovador",
                   "renovada_en", "caida_en", "conectada_por", "conectada_en")

MENSAJE_SIN_CONEXION = "Mnemo no está conectado: el administrador lo conecta en Ajustes → Asistente."
MENSAJE_CLAVE = ("La conexión con Mnemo dejó de valer porque cambió la clave del administrador del panel: hay que "
                 "volver a conectarla en Ajustes → Asistente.")
MENSAJE_CAMBIO = "La conexión con Mnemo cambió mientras el asistente trabajaba: vuelva a intentarlo."
MENSAJE_URL = "La dirección MCP de Mnemo no es válida: tiene que ser https://…/mcp."
MENSAJE_URL_LOCAL = ("La dirección MCP de Mnemo no es válida: tiene que ser https://…/mcp (en local, también "
                     "http://127.0.0.1…).")
MENSAJE_RED = "No se pudo conectar con Mnemo en esa dirección. Revísela o inténtelo de nuevo en un rato."

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_SEGURO = re.compile(r"[\x21-\x7e]+")  # lo que puede ir en una cabecera o en un formulario sin escapar nada raro
_RESOURCE_METADATA = re.compile(r'resource_metadata="([^"]{1,500})"')
_LOOPBACK = ("127.0.0.1", "localhost", "::1")


class ErrorConexion(Exception):
    """Un paso de conectar, volver o desconectar que no se pudo hacer: un `codigo` estable, el `mensaje` para el
    administrador (en español, sin secretos) y el `estado` HTTP con que lo responde la API (400; 502 si Mnemo no
    respondió). Códigos: `url`, `descubrimiento`, `recurso`, `sin_oauth`, `servidor`, `registro`, `red`, `estado`,
    `emisor`, `denegada`, `autorizacion`, `canje` y `conflicto` (409)."""

    def __init__(self, codigo: str, mensaje: str, estado: int = 400):
        super().__init__(mensaje)
        self.codigo, self.mensaje, self.estado = codigo, mensaje, estado

    def para_api(self) -> dict:
        return {"codigo": self.codigo, "mensaje": self.mensaje}


class _SinRed(Exception):
    """Mnemo no respondió (red caída o plazo vencido). Nunca lleva la petición: las de httpx sí, con sus cabeceras."""

    def __init__(self, plazo: bool):
        super().__init__("plazo" if plazo else "red")
        self.plazo = plazo


class _OtraVez(Exception):
    """La conexión cambió mientras se renovaba (o el otro renovador soltó el arriendo): hay que volver a leerla."""


# ───────────────────────────── Utilidades ─────────────────────────────

def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _utc(d: Any) -> datetime | None:
    if not isinstance(d, datetime):
        return None
    return d if d.tzinfo is not None else d.replace(tzinfo=timezone.utc)


def _iso(d: Any) -> str | None:
    d = _utc(d)
    return d.replace(microsecond=0).isoformat() if d is not None else None


def _texto(v: Any, tope: int) -> str | None:
    if not isinstance(v, str):
        return None
    v = _CONTROL.sub(" ", v).strip()
    return v[:tope] or None


def _hash(texto: str) -> str:
    return hashlib.sha256(texto.encode()).hexdigest()


def _url(texto: Any, cfg: Any, *, consulta: bool = False) -> str | None:
    """La dirección normalizada (sin barra final) si sirve: https, o http de loopback solo si el panel no corre tras
    HTTPS (`not cfg.cookie_segura`, como `config._url_mnemo`). Sin usuario ni clave, sin fragmento y, salvo con
    `consulta`, sin query. None si no sirve."""
    if not isinstance(texto, str):
        return None
    u = texto.strip()
    if not u or len(u) > MAX_URL or _CONTROL.search(u) or " " in u:
        return None
    try:
        p = urlsplit(u)
        host, _ = p.hostname, p.port  # `port` lanza ValueError si no es un número válido
    except ValueError:
        return None
    if not host or p.username is not None or p.password is not None or p.fragment or "#" in u:
        return None
    if p.query and not consulta:
        return None
    if p.scheme == "https" or (p.scheme == "http" and not getattr(cfg, "cookie_segura", True) and host in _LOOPBACK):
        return u if p.query else u.rstrip("/")
    return None


def _origen(url: str) -> str:
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}".lower()


def _contexto(emisor: str, client_id: str) -> str:
    """Los datos asociados del cifrado de los tokens: lo de una conexión no sirve en otra."""
    return f"{ID}|{emisor}|{client_id}"


def _contexto_pendiente(state_h: str) -> str:
    return f"mnemo_pendiente|{state_h}"


def _token_valido(t: Any) -> bool:
    return isinstance(t, str) and 0 < len(t) <= MAX_TOKEN and bool(_SEGURO.fullmatch(t))


def _huella(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _pkce() -> tuple[str, str]:
    verificador = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    reto = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
    return verificador, reto


def transporte_de(app: Any) -> httpx2.AsyncBaseTransport | None:
    """El transporte inyectado por las pruebas (`app.state.mnemo_transporte`), envuelto para que cerrar un cliente no
    lo cierre; None en producción (la red de verdad)."""
    t = getattr(getattr(app, "state", None), "mnemo_transporte", None)
    return _SinCerrar(t) if t is not None else None


class _SinCerrar(httpx2.AsyncBaseTransport):
    """Un transporte compartido que no se cierra con el cliente que lo usa."""

    def __init__(self, transporte: httpx2.AsyncBaseTransport):
        self.transporte = transporte

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        return await self.transporte.handle_async_request(request)

    async def aclose(self) -> None:
        return None


@dataclass
class _Respuesta:
    estado: int
    datos: Any  # el JSON de la respuesta (None si no lo es o pasó del tope)
    cabeceras: httpx2.Headers


async def _pedir(app: Any, metodo: str, url: str, *, plazo: float, json_: Any = None, data: dict | None = None,
                 cabeceras: dict | None = None) -> _Respuesta:
    """Una petición saliente del flujo: sin seguir redirecciones, con un tope total de `plazo` segundos y el cuerpo de
    la respuesta acotado. Lanza `_SinRed` si Mnemo no responde."""
    cab = {"user-agent": AGENTE, "accept": "application/json", **(cabeceras or {})}
    try:
        async with asyncio.timeout(plazo):
            async with httpx2.AsyncClient(transport=transporte_de(app), trust_env=True, follow_redirects=False,
                                          timeout=httpx2.Timeout(plazo, connect=min(plazo, PLAZO_CONEXION_S))) as c:
                async with c.stream(metodo, url, json=json_, data=data, headers=cab) as r:
                    trozos, total, datos = [], 0, None
                    async for t in r.aiter_bytes():
                        total += len(t)
                        if total > MAX_CUERPO:
                            trozos = None
                            break
                        trozos.append(t)
                    if trozos is not None:
                        try:
                            datos = json.loads(b"".join(trozos) or b"null")
                        except (ValueError, UnicodeDecodeError, RecursionError):
                            datos = None
                    return _Respuesta(r.status_code, datos, r.headers)
    except (TimeoutError, httpx2.TimeoutException):
        log.warning("Mnemo: %s no respondió a tiempo (conexión)", metodo)
        raise _SinRed(True) from None
    except httpx2.HTTPError as e:  # sin el mensaje: el de httpx puede traer la petición
        log.warning("Mnemo: falló la conexión (%s)", type(e).__name__)
        raise _SinRed(False) from None


async def _json_de(app: Any, url: str) -> dict | None:
    """El JSON de un GET (metadatos), o None si no es un 200 con un objeto JSON."""
    try:
        r = await _pedir(app, "GET", url, plazo=PLAZO_S)
    except _SinRed:
        raise ErrorConexion("red", MENSAJE_RED, 502) from None
    return r.datos if r.estado == 200 and isinstance(r.datos, dict) else None


# ───────────────────────────── La vista ─────────────────────────────

def _cuenta_legible(cuenta: Any) -> str | None:
    """«Nombre (correo)», o lo que haya de los dos."""
    if not isinstance(cuenta, dict):
        return None
    nombre, correo = _texto(cuenta.get("nombre"), 200), _texto(cuenta.get("correo"), 200)
    if nombre and correo:
        return f"{nombre} ({correo})"
    return nombre or correo


def _sugerida(doc: dict, cfg: Any) -> str | None:
    return (getattr(cfg, "mnemo_url", "") or "") or _texto(doc.get("ultima_url"), MAX_URL)


def vista(db: Any, cfg: Any = None) -> dict:
    """La conexión para mostrar (Ajustes, `GET /api/agente/estado`), sin descifrar nada ni secretos:

    `{"estado": "sin_conectar" | "conectada" | "caida", "motivo": "revocada" | "clave" | "error" | None (solo en
    «caida»), "url": la dirección MCP | None, "cuenta": «Nombre (correo)» | None, "alcances": [los concedidos],
    "modelo": bool (conectada y con `mnemo:model`), "desde": iso de cuando se conectó | None}`. Con `cfg`, además
    `"url_sugerida"`: `MNEMO_MCP_URL` o la última dirección con que se conectó (None si ninguna)."""
    doc = db.meta.find_one({"_id": ID}, {"cifrado": 0, "pendiente": 0, "clientes": 0}) or {}
    estado = doc.get("estado") if doc.get("estado") in ESTADOS else "sin_conectar"
    hay = estado != "sin_conectar"
    alcances = [a for a in doc.get("alcances") or [] if isinstance(a, str)][:MAX_ALCANCES] if hay else []
    out = {"estado": estado,
           "motivo": _texto(doc.get("motivo"), 40) if estado == "caida" else None,
           "url": _texto(doc.get("url_mcp"), MAX_URL) if hay else None,
           "cuenta": _cuenta_legible(doc.get("cuenta")) if hay else None,
           "alcances": alcances,
           "modelo": estado == "conectada" and ALCANCE_MODELO in alcances,
           "desde": _iso(doc.get("conectada_en")) if hay else None}
    if cfg is not None:
        out["url_sugerida"] = _sugerida(doc, cfg)
    return out


def con_modelo(db: Any) -> bool:
    """¿Hay una conexión «conectada» con `mnemo:model`? (el proveedor del modelo elige Mnemo con esto). No descifra
    nada: si la clave del administrador cambió, se sabe al pedir el primer token."""
    return db.meta.count_documents({"_id": ID, "estado": "conectada", "alcances": ALCANCE_MODELO}, limit=1) == 1


def conectada(db: Any) -> dict | None:
    """`{"version": int, "conexion": str, "url_mcp": str}` de la conexión si está «conectada»; si no, None. Es lo que
    lee `mnemo_cliente.cliente_de` en cada turno (un documento por `_id`)."""
    doc = db.meta.find_one({"_id": ID}, {"version": 1, "estado": 1, "conexion": 1, "url_mcp": 1})
    if not doc or doc.get("estado") != "conectada" or not isinstance(doc.get("url_mcp"), str):
        return None
    return {"version": int(doc.get("version") or 0), "conexion": str(doc.get("conexion") or ""),
            "url_mcp": doc["url_mcp"]}


def url_sugerida(db: Any, cfg: Any) -> str | None:
    """La dirección MCP que se sugiere al conectar: `MNEMO_MCP_URL` o la última con que se conectó."""
    return _sugerida(db.meta.find_one({"_id": ID}, {"ultima_url": 1}) or {}, cfg)


# ───────────────────────────── Descubrimiento y registro ─────────────────────────────

async def _descubrir(app: Any, url_mcp: str, cfg: Any) -> dict:
    """El recurso protegido (RFC 9728) y su servidor de autorización (RFC 8414): `{recurso, emisor, endpoints,
    iss_requerido}`. El recurso tiene que ser la dirección que se dio (salvo una barra final)."""
    origen, ruta = _origen(url_mcp), urlsplit(url_mcp).path.rstrip("/")
    prm = await _json_de(app, f"{origen}/.well-known/oauth-protected-resource{ruta}")
    if prm is None:
        # Sin el documento en su lugar: el 401 de /mcp dice dónde está (`resource_metadata`), en el mismo origen
        try:
            r = await _pedir(app, "POST", url_mcp, plazo=PLAZO_S,
                             json_={"jsonrpc": "2.0", "id": 1, "method": "ping"},
                             cabeceras={"accept": "application/json, text/event-stream"})
        except _SinRed:
            raise ErrorConexion("red", MENSAJE_RED, 502) from None
        m = _RESOURCE_METADATA.search(r.cabeceras.get("www-authenticate", ""))
        dir_prm = _url(m.group(1), cfg) if (r.estado == 401 and m) else None
        if dir_prm and _origen(dir_prm) == origen:
            prm = await _json_de(app, dir_prm)
    if prm is None:
        raise ErrorConexion("descubrimiento", "En esa dirección no hay un servidor MCP de Mnemo que acepte "
                                              "conexiones: revise que sea la de su Mnemo (https://…/mcp).")
    recurso = prm.get("resource")
    if not isinstance(recurso, str) or recurso.rstrip("/") != url_mcp:
        dice = _texto(recurso, MAX_URL)
        raise ErrorConexion("recurso", "Esa dirección no es la del servidor MCP de Mnemo"
                                       + (f": Mnemo dice que la suya es {dice}." if dice else "."))
    servidores = prm.get("authorization_servers")
    if not isinstance(servidores, list) or not servidores:
        raise ErrorConexion("sin_oauth", "Mnemo no tiene OAuth: falta PUBLIC_BASE_URL en su despliegue.")
    emisor = servidores[0]
    if _url(emisor, cfg) is None:
        raise ErrorConexion("servidor", "El servidor de autorización que anuncia Mnemo no tiene una dirección válida.")
    meta = await _metadatos(app, emisor)
    if meta is None:
        raise ErrorConexion("servidor", "El servidor de autorización de Mnemo no publica sus metadatos.")
    if meta.get("issuer") != emisor:
        raise ErrorConexion("servidor", "Los metadatos del servidor de autorización de Mnemo no son de su emisor.")
    metodos = meta.get("code_challenge_methods_supported")
    if not isinstance(metodos, list) or "S256" not in metodos:
        raise ErrorConexion("servidor", "El servidor de autorización de Mnemo no admite PKCE con S256.")
    endpoints = {}
    for clave, campo in (("authorize", "authorization_endpoint"), ("token", "token_endpoint"),
                         ("register", "registration_endpoint"), ("revoke", "revocation_endpoint")):
        v = _url(meta.get(campo), cfg, consulta=clave == "authorize")
        if v is None or _origen(v) != _origen(emisor):
            raise ErrorConexion("servidor", f"El servidor de autorización de Mnemo no ofrece {campo}: el panel lo "
                                            "necesita.")
        endpoints[clave] = v
    # El `resource` se manda tal como lo anuncia Mnemo: lo compara byte a byte (si no, `invalid_target`)
    return {"recurso": recurso, "emisor": emisor, "endpoints": endpoints,
            "iss_requerido": meta.get("authorization_response_iss_parameter_supported") is True}


async def _metadatos(app: Any, emisor: str) -> dict | None:
    p = urlsplit(emisor)
    ruta = p.path.rstrip("/")
    for url in (f"{_origen(emisor)}/.well-known/oauth-authorization-server{ruta}",
                f"{emisor.rstrip('/')}/.well-known/openid-configuration"):
        m = await _json_de(app, url)
        if m is not None:
            return m
    return None


def _cliente_guardado(db: Any, emisor: str, redirect_uri: str) -> str | None:
    doc = db.meta.find_one({"_id": ID}, {"clientes": 1}) or {}
    for c in doc.get("clientes") or []:
        if isinstance(c, dict) and c.get("emisor") == emisor and c.get("redirect_uri") == redirect_uri:
            return c.get("client_id") if isinstance(c.get("client_id"), str) else None
    return None


def _guardar_cliente(db: Any, emisor: str, redirect_uri: str, client_id: str) -> None:
    doc = db.meta.find_one({"_id": ID}, {"clientes": 1}) or {}
    otros = [c for c in doc.get("clientes") or [] if isinstance(c, dict)
             and (c.get("emisor"), c.get("redirect_uri")) != (emisor, redirect_uri)]
    nuevo = {"emisor": emisor, "redirect_uri": redirect_uri, "client_id": client_id, "registrado_en": _ahora()}
    db.meta.update_one({"_id": ID}, {"$set": {"clientes": [nuevo, *otros][:MAX_CLIENTES]},
                                     "$setOnInsert": {"version": 0}}, upsert=True)


async def _cliente_vivo(app: Any, d: dict, client_id: str) -> bool:
    """¿Mnemo todavía conoce este cliente? Un refresh inventado da `invalid_grant` si existe e `invalid_client` si
    no (en memoria, Mnemo los pierde al reiniciar)."""
    try:
        r = await _pedir(app, "POST", d["endpoints"]["token"], plazo=PLAZO_S, data={
            "grant_type": "refresh_token", "refresh_token": secrets.token_urlsafe(24), "client_id": client_id})
    except _SinRed:
        raise ErrorConexion("red", MENSAJE_RED, 502) from None
    error = r.datos.get("error") if isinstance(r.datos, dict) else None
    if r.estado >= 500:
        raise ErrorConexion("red", MENSAJE_RED, 502)
    return not (r.estado == 401 or error == "invalid_client")


async def _registrar(app: Any, d: dict, redirect_uri: str) -> str:
    """Registro dinámico (RFC 7591): un cliente público, sin secreto, con PKCE."""
    try:
        r = await _pedir(app, "POST", d["endpoints"]["register"], plazo=PLAZO_S, json_={
            "client_name": NOMBRE_CLIENTE, "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
            "token_endpoint_auth_method": "none"})
    except _SinRed:
        raise ErrorConexion("red", MENSAJE_RED, 502) from None
    datos = r.datos if isinstance(r.datos, dict) else {}
    cid = datos.get("client_id")
    if r.estado in (200, 201) and isinstance(cid, str) and 0 < len(cid) <= MAX_URL and _SEGURO.fullmatch(cid):
        uris = datos.get("redirect_uris")
        if uris is None or (isinstance(uris, list) and redirect_uri in uris):
            return cid
    log.warning("Mnemo: no aceptó el registro del panel (HTTP %s)", r.estado)
    if r.estado == 429:
        raise ErrorConexion("registro", "Mnemo recibió demasiados registros desde esta dirección: inténtelo de nuevo "
                                        "en una hora.")
    dice = _texto(datos.get("error_description"), 300) or _texto(datos.get("error"), 100)
    raise ErrorConexion("registro", "Mnemo no aceptó registrar el panel" + (f": {dice}" if dice else ".")
                        + ("" if not dice or dice.endswith(".") else "."))


async def _client_id(app: Any, db: Any, d: dict, redirect_uri: str) -> str:
    guardado = await run_in_threadpool(_cliente_guardado, db, d["emisor"], redirect_uri)
    if guardado and await _cliente_vivo(app, d, guardado):
        return guardado
    cid = await _registrar(app, d, redirect_uri)
    await run_in_threadpool(_guardar_cliente, db, d["emisor"], redirect_uri, cid)
    return cid


def _pedidos(cfg: Any) -> list[str]:
    """Los alcances que se piden: OpenID (para saber la cuenta), `mnemo:model` y los de las herramientas que ofrece
    el panel (`MNEMO_HERRAMIENTAS`, o la lista blanca)."""
    from .herramientas import mnemo as hmnemo  # aquí y no arriba: el catálogo de herramientas se carga al usarlo
    return [*ALCANCES_OIDC, ALCANCE_MODELO,
            *(a for a in hmnemo.alcances(getattr(cfg, "mnemo_herramientas", "")) if a != ALCANCE_MODELO)]


# ───────────────────────────── Conectar ─────────────────────────────

async def iniciar(app: Any, quien: Any, *, url: str | None, redirect_uri: str, sesion: str) -> str:
    """POST /api/agente/mnemo/conectar: valida la dirección (o toma la sugerida), descubre el servidor de
    autorización, consigue un `client_id` (guardado y vivo, o uno nuevo), guarda el pendiente atado a `sesion` por
    `VIGENCIA_PENDIENTE` (reemplaza al anterior) y devuelve la URL de autorización de Mnemo (PKCE S256, `state` de 32
    bytes, `resource` = la dirección, `scope` de `_pedidos`). Lanza `ErrorConexion`."""
    db, cfg = app.state.db, app.state.cfg
    if not (url or "").strip():
        url = await run_in_threadpool(url_sugerida, db, cfg)
        if not url:
            raise ErrorConexion("url", "Escriba la dirección MCP de Mnemo (https://…/mcp).")
    url_mcp = _url(url, cfg)
    if url_mcp is None:
        raise ErrorConexion("url", MENSAJE_URL if getattr(cfg, "cookie_segura", True) else MENSAJE_URL_LOCAL)
    d = await _descubrir(app, url_mcp, cfg)
    client_id = await _client_id(app, db, d, redirect_uri)
    verificador, reto = _pkce()
    state = secrets.token_urlsafe(32)
    pedidos = _pedidos(cfg)
    state_h = _hash(state)
    pendiente = {"state_h": state_h, "sesion": sesion, "url_mcp": url_mcp, "recurso": d["recurso"],
                 "emisor": d["emisor"], "endpoints": d["endpoints"], "client_id": client_id,
                 "redirect_uri": redirect_uri, "pedidos": pedidos, "iss_requerido": d["iss_requerido"],
                 "uid": getattr(quien, "uid", None), "expira": _ahora() + VIGENCIA_PENDIENTE}

    def guardar() -> None:
        pendiente["verificador_cifrado"] = cifrado.cifrar(seguridad.llave_mnemo(cfg), {"v": verificador},
                                                          _contexto_pendiente(state_h))
        db.meta.update_one({"_id": ID}, {"$set": {"pendiente": pendiente}, "$setOnInsert": {"version": 0}},
                           upsert=True)

    await run_in_threadpool(guardar)
    q = {"response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri, "scope": " ".join(pedidos),
         "state": state, "code_challenge": reto, "code_challenge_method": "S256", "resource": d["recurso"]}
    autorizar = d["endpoints"]["authorize"]
    return autorizar + ("&" if "?" in autorizar else "?") + urlencode(q, quote_via=quote)


def _tomar_pendiente(db: Any, state: str, sesion: str) -> dict | None:
    """El pendiente de este `state` y esta sesión, si no venció, borrado en el mismo paso: una vuelta repetida (o la
    de otra sesión) no lo encuentra."""
    doc = db.meta.find_one_and_update(
        {"_id": ID, "pendiente.state_h": _hash(state), "pendiente.sesion": sesion,
         "pendiente.expira": {"$gt": _ahora()}},
        {"$set": {"pendiente": None}}, projection={"pendiente": 1}, return_document=ReturnDocument.BEFORE)
    return doc["pendiente"] if doc and isinstance(doc.get("pendiente"), dict) else None


def _tokens(r: _Respuesta, refresh_previo: str | None = None) -> dict | None:
    """Los tokens de una respuesta 200 de `/oauth/token`: `{access, refresh, expira, scope, id_token}`, o None si no
    sirve (sin refresh nuevo se sigue con el anterior, como dice RFC 6749)."""
    d = r.datos
    if r.estado != 200 or not isinstance(d, dict):
        return None
    access, refresh = d.get("access_token"), d.get("refresh_token") or refresh_previo
    tipo = d.get("token_type")
    if not _token_valido(access) or not _token_valido(refresh) or not isinstance(tipo, str) or tipo.lower() != "bearer":
        return None
    vida = d.get("expires_in")
    vida = int(vida) if isinstance(vida, (int, float)) and not isinstance(vida, bool) and 0 < vida <= 30 * 86400 \
        else VIDA_POR_DEFECTO_S
    return {"access": access, "refresh": refresh, "expira": vida,
            "scope": d.get("scope") if isinstance(d.get("scope"), str) else None,
            "id_token": d.get("id_token") if isinstance(d.get("id_token"), str) else None}


def _alcances(scope: str | None, pedidos: Any) -> list[str]:
    """Los alcances concedidos (sin los de OpenID). Sin `scope` en la respuesta, los pedidos (RFC 6749 §5.1)."""
    fuente = scope.split() if isinstance(scope, str) else [a for a in pedidos or [] if isinstance(a, str)]
    out: list[str] = []
    for a in fuente:
        if a not in ALCANCES_OIDC and a != "offline_access" and len(a) <= 64 and _SEGURO.fullmatch(a) and a not in out:
            out.append(a)
    return out[:MAX_ALCANCES]


def _cuenta(id_token: str | None, emisor: str, client_id: str) -> dict:
    """La cuenta de Mnemo del `id_token` (`{sub, nombre?, correo?}`), o {} si no hay o no es de este emisor y este
    cliente. Llega directo del endpoint de tokens por TLS: basta leer su carga, sin verificar la firma, y solo para
    mostrar quién se conectó y saber si es otra cuenta."""
    if not isinstance(id_token, str) or len(id_token) > 16_000:
        return {}
    partes = id_token.split(".")
    if len(partes) != 3:
        return {}
    try:
        carga = json.loads(base64.urlsafe_b64decode(partes[1] + "=" * (-len(partes[1]) % 4)))
    except (ValueError, binascii.Error, RecursionError):
        return {}
    if not isinstance(carga, dict) or carga.get("iss") != emisor:
        return {}
    aud = carga.get("aud")
    if client_id not in (aud if isinstance(aud, list) else [aud]):
        return {}
    sub = _texto(carga.get("sub"), 200)
    if not sub:
        return {}
    cuenta = {"sub": sub}
    nombre = _texto(carga.get("name"), 200) or _texto(carga.get("preferred_username"), 200)
    correo = _texto(carga.get("email"), 200)
    if nombre:
        cuenta["nombre"] = nombre
    if correo:
        cuenta["correo"] = correo
    return cuenta


def _campos(cfg: Any, datos: dict, tokens: dict, quien: Any, ahora: datetime) -> dict:
    """Lo que se guarda de una conexión nueva (los tokens, cifrados)."""
    llave = seguridad.llave_mnemo(cfg)
    return {"estado": "conectada", "motivo": None, "conexion": secrets.token_hex(12),
            "url_mcp": datos["url_mcp"], "recurso": datos.get("recurso") or datos["url_mcp"],
            "emisor": datos["emisor"], "endpoints": dict(datos["endpoints"]), "client_id": datos["client_id"],
            "redirect_uri": datos["redirect_uri"], "alcances": list(datos.get("alcances") or []),
            "cuenta": dict(datos.get("cuenta") or {}),
            "cifrado": cifrado.cifrar(llave, {"access": tokens["access"], "refresh": tokens["refresh"]},
                                      _contexto(datos["emisor"], datos["client_id"])),
            "vence": ahora + timedelta(seconds=int(tokens.get("expira") or VIDA_POR_DEFECTO_S)),
            "renovando_hasta": None, "renovada_en": None, "caida_en": None,
            "conectada_por": ({"uid": getattr(quien, "uid", None), "usuario": getattr(quien, "usuario", None)}
                              if quien is not None else None),
            "conectada_en": ahora, "ultima_url": datos["url_mcp"]}


def _escribir(db: Any, cfg: Any, filtro: dict, datos: dict, tokens: dict, quien: Any, upsert: bool = False) -> bool:
    r = db.meta.update_one(filtro, {"$set": _campos(cfg, datos, tokens, quien, _ahora()),
                                    "$unset": {"renovador": "", "desconectada_en": ""}, "$inc": {"version": 1}},
                           upsert=upsert)
    return r.matched_count == 1 or r.upserted_id is not None


def instalar(db: Any, cfg: Any, datos: dict, tokens: dict, quien: Any = None) -> None:
    """Guarda una conexión «conectada» sin pasar por el flujo (para las pruebas: `ayudas_agente.conectar_mnemo`).
    `datos`: `{url_mcp, emisor, endpoints: {authorize, token, register, revoke}, client_id, redirect_uri, alcances,
    cuenta?: {sub, nombre?, correo?}, recurso?}`; `tokens`: `{access, refresh, expira (segundos)}`. Reemplaza la que
    hubiera (sin revocarla)."""
    _escribir(db, cfg, {"_id": ID}, datos, tokens, quien, upsert=True)


def _libre(doc: dict, ahora: datetime) -> bool:
    hasta = _utc(doc.get("renovando_hasta"))
    return hasta is None or hasta < ahora


def _filtro_libre(version: int, ahora: datetime) -> dict:
    return {"_id": ID, "version": version, "$or": [{"renovando_hasta": None}, {"renovando_hasta": {"$lt": ahora}}]}


async def _con_arriendo(db: Any, cambio) -> dict:
    """Aplica `cambio(filtro) -> bool` (una escritura condicionada a `version`) cuando nadie está renovando, para no
    pisar una renovación en vuelo. Espera como mucho `ESPERA_OTRO_S` y después escribe igual (el arriendo pudo quedar
    de un proceso que murió). Devuelve el documento que había antes del cambio (sin el pendiente). Si la conexión
    cambia sin parar (o el documento desapareció), `ErrorConexion` 409 `conflicto` tras el doble de la espera."""
    bucle = asyncio.get_running_loop()
    fin = bucle.time() + ESPERA_OTRO_S
    while bucle.time() < fin + ESPERA_OTRO_S:
        doc = await run_in_threadpool(db.meta.find_one, {"_id": ID}, {"pendiente": 0}) or {"version": 0}
        version, ahora = int(doc.get("version") or 0), _ahora()
        libre = _libre(doc, ahora)
        if libre or bucle.time() >= fin:
            filtro = _filtro_libre(version, ahora) if libre else {"_id": ID, "version": version}
            if await run_in_threadpool(cambio, filtro):
                return doc
        await asyncio.sleep(SONDEO_S)
    raise ErrorConexion("conflicto", "La conexión con Mnemo cambió mientras se guardaba: vuelva a intentarlo.", 409)


def _misma_concesion(viejo: dict, datos: dict) -> bool:
    """¿La conexión nueva es la misma concesión de Mnemo que la vieja (mismo emisor, mismo cliente y misma cuenta, o
    no se sabe la cuenta)? Entonces revocar lo viejo se llevaría también los tokens nuevos."""
    if viejo.get("emisor") != datos["emisor"] or viejo.get("client_id") != datos["client_id"]:
        return False
    sv = (viejo.get("cuenta") or {}).get("sub") if isinstance(viejo.get("cuenta"), dict) else None
    sn = (datos.get("cuenta") or {}).get("sub")
    return not (sv and sn and sv != sn)


async def volver(app: Any, quien: Any, *, sesion: str, state: str, code: str | None = None, iss: str | None = None,
                 error: str | None = None, error_description: str | None = None) -> dict:
    """POST /api/agente/mnemo/volver: la vuelta de Mnemo (`/ajustes?code=…&state=…&iss=…`, o `error=…`). Toma el
    pendiente (mismo `state`, misma sesión, no vencido; nunca dos veces), exige `iss` igual al emisor, canjea el
    código en `/oauth/token` (PKCE, `redirect_uri`, `resource`), guarda la conexión cifrada (sin pisar una renovación
    en vuelo) y, si la vieja era otra concesión (otra cuenta, otro cliente u otro Mnemo), revoca su refresh. Audita
    `mnemo_conectar` y devuelve `vista(db, cfg)`. Lanza `ErrorConexion` (`estado`, `emisor`, `denegada`,
    `autorizacion`, `canje`, `red` o `conflicto`)."""
    db, cfg = app.state.db, app.state.cfg
    p = await run_in_threadpool(_tomar_pendiente, db, state, sesion)
    if p is None:
        raise ErrorConexion("estado", "La autorización no corresponde a esta sesión o ya venció: vuelva a conectar "
                                      "desde Ajustes → Asistente.")
    if (iss is not None and iss != p.get("emisor")) or (iss is None and p.get("iss_requerido")):
        log.warning("Mnemo: la vuelta trae un emisor que no es el de la conexión")
        raise ErrorConexion("emisor", "La respuesta no vino del servidor de autorización de Mnemo con que se empezó: "
                                      "no se conectó nada.")
    if error:
        if error == "access_denied":
            raise ErrorConexion("denegada", "Se canceló el permiso en Mnemo: no se conectó nada.")
        dice = _texto(error_description, 200) or _texto(error, 60)
        raise ErrorConexion("autorizacion", f"Mnemo no autorizó la conexión ({dice}).")
    if not code:
        raise ErrorConexion("canje", "Mnemo no devolvió un código de autorización: vuelva a conectar.")
    verificador = await run_in_threadpool(lambda: cifrado.descifrar(
        seguridad.llave_mnemo(cfg), p.get("verificador_cifrado"), _contexto_pendiente(p.get("state_h") or "")))
    if not verificador or not isinstance(verificador.get("v"), str):
        raise ErrorConexion("estado", "La autorización ya no se puede completar: vuelva a conectar desde Ajustes → "
                                      "Asistente.")
    try:
        r = await _pedir(app, "POST", p["endpoints"]["token"], plazo=PLAZO_TOKEN_S, data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": p["redirect_uri"],
            "client_id": p["client_id"], "code_verifier": verificador["v"], "resource": p["recurso"]})
    except _SinRed:
        raise ErrorConexion("red", MENSAJE_RED, 502) from None
    tokens = _tokens(r)
    if tokens is None:
        log.warning("Mnemo: no aceptó el canje del código (HTTP %s)", r.estado)
        raise ErrorConexion("canje", "Mnemo no aceptó el código de autorización (venció o ya se usó): vuelva a "
                                     "conectar.")
    datos = {"url_mcp": p["url_mcp"], "recurso": p["recurso"], "emisor": p["emisor"], "endpoints": p["endpoints"],
             "client_id": p["client_id"], "redirect_uri": p["redirect_uri"],
             "alcances": _alcances(tokens["scope"], p.get("pedidos")),
             "cuenta": _cuenta(tokens["id_token"], p["emisor"], p["client_id"])}
    viejo = await _con_arriendo(db, lambda filtro: _escribir(db, cfg, filtro, datos, tokens, quien))
    otra = viejo.get("estado") in ESTADOS and not _misma_concesion(viejo, datos)
    if otra and viejo.get("cifrado"):
        await _revocar_doc(app, cfg, viejo)
    await run_in_threadpool(bd.auditar, db, quien, "mnemo_conectar", None, None, {
        "url": datos["url_mcp"], "alcances": datos["alcances"], "modelo": ALCANCE_MODELO in datos["alcances"],
        "reemplaza_otra": otra})
    log.info("Mnemo: el panel quedó conectado")
    return await run_in_threadpool(vista, db, cfg)


# ───────────────────────────── Desconectar y revocar ─────────────────────────────

async def _revocar(app: Any, endpoint: str, client_id: str, refresh: str) -> bool:
    """Revoca la concesión con su refresh (`token_type_hint=refresh_token`): Mnemo la destruye entera y la marca
    revocada en «Tu cuenta». Con el access quedaría «zombi». True si Mnemo respondió 200."""
    try:
        r = await _pedir(app, "POST", endpoint, plazo=PLAZO_S, data={
            "token": refresh, "token_type_hint": "refresh_token", "client_id": client_id})
    except _SinRed:
        return False
    if r.estado != 200:
        log.warning("Mnemo: no aceptó revocar la conexión (HTTP %s)", r.estado)
    return r.estado == 200


async def _revocar_doc(app: Any, cfg: Any, doc: dict) -> bool:
    endpoints = doc.get("endpoints") if isinstance(doc.get("endpoints"), dict) else {}
    endpoint, client_id = endpoints.get("revoke"), doc.get("client_id")
    if not isinstance(endpoint, str) or not isinstance(client_id, str):
        return False
    tokens = await run_in_threadpool(lambda: cifrado.descifrar(
        seguridad.llave_mnemo(cfg), doc.get("cifrado"), _contexto(str(doc.get("emisor")), client_id)))
    if not tokens or not _token_valido(tokens.get("refresh")):
        return False
    return await _revocar(app, endpoint, client_id, tokens["refresh"])


def _quitar(db: Any, filtro: dict) -> bool:
    r = db.meta.update_one(filtro, {"$unset": {c: "" for c in CAMPOS_CONEXION},
                                    "$set": {"desconectada_en": _ahora()}, "$inc": {"version": 1}})
    return r.matched_count == 1


async def desconectar(app: Any, quien: Any) -> dict:
    """DELETE /api/agente/mnemo: borra la conexión local (sin pisar una renovación en vuelo) y revoca la concesión en
    Mnemo con el refresh. Devuelve `vista(db, cfg)` más `"revocada"`: True si Mnemo la revocó, False si no se pudo
    (Mnemo no respondió o no la aceptó: el administrador puede revocarla en Mnemo, «Tu cuenta → Agentes
    conectados») y None si no había nada que revocar (sin conexión, o una «caida», que ya no tiene tokens; con motivo
    «clave» la concesión puede seguir viva en Mnemo). Audita `mnemo_desconectar` si había una conexión."""
    db, cfg = app.state.db, app.state.cfg
    actual = await run_in_threadpool(db.meta.find_one, {"_id": ID}, {"estado": 1})
    revocada = None
    if actual and actual.get("estado") in ESTADOS:
        viejo = await _con_arriendo(db, lambda filtro: _quitar(db, filtro))
        if viejo.get("estado") in ESTADOS:  # si no, otra petición la quitó mientras tanto
            # Una conexión caída ya no tiene tokens: no hay nada que revocar desde el panel (None)
            revocada = await _revocar_doc(app, cfg, viejo) if viejo.get("cifrado") else None
            await run_in_threadpool(bd.auditar, db, quien, "mnemo_desconectar", None, None, {
                "url": viejo.get("url_mcp"), "revocada": revocada})
            log.info("Mnemo: el panel se desconectó (revocada en Mnemo: %s)", "sí" if revocada else "no")
    return {**(await run_in_threadpool(vista, db, cfg)), "revocada": revocada}


def _caer(db: Any, filtro: dict, motivo: str) -> None:
    """Deja la conexión «caida» (sin los tokens cifrados) y lo audita como el sistema. `filtro` evita pisar una
    reconexión hecha mientras tanto."""
    r = db.meta.update_one({**filtro, "estado": "conectada"}, {
        "$set": {"estado": "caida", "motivo": motivo, "caida_en": _ahora(), "renovando_hasta": None},
        "$unset": {"cifrado": "", "renovador": ""}, "$inc": {"version": 1}})
    if r.modified_count:
        log.warning("Mnemo: la conexión se cayó (%s): el administrador tiene que volver a conectarla", motivo)
        bd.auditar(db, "sistema", "mnemo_caida", None, None, {"motivo": motivo})


# ───────────────────────────── Los tokens del cliente MCP ─────────────────────────────

_PROYECCION = {"version": 1, "estado": 1, "motivo": 1, "conexion": 1, "cifrado": 1, "vence": 1, "emisor": 1,
               "client_id": 1, "endpoints": 1, "recurso": 1, "url_mcp": 1, "renovando_hasta": 1}


def _leer(db: Any) -> dict | None:
    return db.meta.find_one({"_id": ID}, _PROYECCION)


class FuenteTokens:
    """Los access tokens de la conexión guardada, para `mnemo_cliente.ClienteMnemo` (que pide uno en cada envío).

    * `await token() -> str` — un access vigente: el guardado si le quedan más de `MARGEN` (descifrado una vez por
      `version`); si no, o si Mnemo lo rechazó (`invalidar`), lo renueva con una sola renovación a la vez en el
      proceso y entre procesos. Si no hay conexión, se cayó, la reemplazó otra (otra `conexion` que la de esta
      fuente) o no se puede descifrar, lanza `ErrorHerramienta` con `mnemo_cliente.COD_TOKEN` y `detalle={"conexion":
      "sin_conectar" | "caida" | "revocada" | "clave" | "error" | "cambio"}` (y deja la conexión «caida» cuando
      corresponde); si Mnemo no responde al renovar, con `COD_RED` o `COD_PLAZO`; si responde otro error (un 5xx),
      con `COD_MNEMO` y su `estado`.
    * `await invalidar(usado: str)` — Mnemo respondió 401 con `usado`: el próximo `token()` renueva si el guardado
      sigue siendo ese (si otro ya renovó, da el nuevo sin pedir nada).

    `app` es la aplicación (o cualquier objeto con `state.db`, `state.cfg` y, en las pruebas, `state.mnemo_transporte`)
    y se lee en cada llamada: un cambio de clave del administrador se nota al instante. `conexion` es el id de la
    conexión que sirve (None: la que esté)."""

    def __init__(self, app: Any, conexion: str | None = None):
        self.app, self.conexion = app, conexion or None
        self._cache: tuple[int, str, datetime] | None = None  # (version, access, vence)
        self._invalidado: str | None = None                  # huella del access que Mnemo rechazó
        self._tarea: tuple[asyncio.AbstractEventLoop, asyncio.Task] | None = None
        self.renovaciones = 0                                 # las que pidió esta fuente

    def __repr__(self) -> str:  # sin tokens: el repr sale en trazas
        return f"FuenteTokens(conexion={self.conexion!r})"

    @property
    def _db(self) -> Any:
        return self.app.state.db

    @property
    def _cfg(self) -> Any:
        return self.app.state.cfg

    async def invalidar(self, usado: str) -> None:
        if isinstance(usado, str) and usado:
            self._invalidado = _huella(usado)

    async def token(self) -> str:
        for _ in range(4):
            doc = await run_in_threadpool(_leer, self._db)
            self._exigir(doc)
            acceso, vence = await self._acceso(doc)
            if vence - _ahora() >= MARGEN and not (
                    self._invalidado and hmac.compare_digest(self._invalidado, _huella(acceso))):
                return acceso
            try:
                return await self._renovacion(int(doc.get("version") or 0))
            except _OtraVez:
                continue
        raise ErrorHerramienta(MENSAJE_CAMBIO, mc.COD_TOKEN, detalle={"conexion": "cambio"})

    def _exigir(self, doc: dict | None) -> None:
        if not doc or doc.get("estado") != "conectada":
            caida = bool(doc and doc.get("estado") == "caida")
            motivo = doc.get("motivo") if caida else None
            mensaje = (MENSAJE_CLAVE if motivo == "clave" else mc.MENSAJE_TOKEN) if caida else MENSAJE_SIN_CONEXION
            raise ErrorHerramienta(mensaje, mc.COD_TOKEN, detalle={"conexion": motivo if caida and isinstance(
                motivo, str) else ("caida" if caida else "sin_conectar")})
        if self.conexion and doc.get("conexion") != self.conexion:
            raise ErrorHerramienta(MENSAJE_CAMBIO, mc.COD_TOKEN, detalle={"conexion": "cambio"})

    async def _acceso(self, doc: dict) -> tuple[str, datetime]:
        version = int(doc.get("version") or 0)
        vence = _utc(doc.get("vence")) or _ahora()
        if self._cache is not None and self._cache[0] == version:
            return self._cache[1], self._cache[2]
        tokens = await run_in_threadpool(self._descifrar, doc)
        if tokens is None or not _token_valido(tokens.get("access")):
            await run_in_threadpool(_caer, self._db, {"_id": ID, "version": version}, "clave")
            raise ErrorHerramienta(MENSAJE_CLAVE, mc.COD_TOKEN, detalle={"conexion": "clave"})
        self._cache = (version, tokens["access"], vence)
        return tokens["access"], vence

    def _descifrar(self, doc: dict) -> dict | None:
        return cifrado.descifrar(seguridad.llave_mnemo(self._cfg), doc.get("cifrado"),
                                 _contexto(str(doc.get("emisor")), str(doc.get("client_id"))))

    async def _renovacion(self, version: int) -> str:
        """Una sola renovación a la vez por bucle de eventos (las pruebas usan varios): quien llega mientras otra
        corre la espera. `shield`: si quien espera se cancela (el turno se cortó), la renovación sigue y se guarda;
        cortarla a mitad perdería el refresh que Mnemo ya rotó."""
        bucle = asyncio.get_running_loop()
        t = self._tarea
        if t is None or t[0] is not bucle or t[1].done():
            tarea = bucle.create_task(self._renovar(version))
            tarea.add_done_callback(lambda f: f.cancelled() or f.exception())  # nadie la espera: no se avisa
            t = self._tarea = (bucle, tarea)
        return await asyncio.shield(t[1])

    async def _renovar(self, version: int) -> str:
        db, ahora, dueño = self._db, _ahora(), secrets.token_hex(8)
        filtro = {**_filtro_libre(version, ahora), "estado": "conectada"}
        if self.conexion:
            filtro["conexion"] = self.conexion
        tomado = await run_in_threadpool(lambda: db.meta.find_one_and_update(
            filtro, {"$set": {"renovando_hasta": ahora + ARRIENDO, "renovador": dueño}}, projection=_PROYECCION,
            return_document=ReturnDocument.AFTER))
        if tomado is None:
            return await self._esperar_otro(version)
        mio = {"_id": ID, "renovador": dueño}
        tokens = await run_in_threadpool(self._descifrar, tomado)
        if tokens is None or not _token_valido(tokens.get("refresh")):
            await run_in_threadpool(_caer, db, mio, "clave")
            raise ErrorHerramienta(MENSAJE_CLAVE, mc.COD_TOKEN, detalle={"conexion": "clave"})
        endpoints = tomado.get("endpoints") if isinstance(tomado.get("endpoints"), dict) else {}
        try:
            self.renovaciones += 1
            r = await _pedir(self.app, "POST", str(endpoints.get("token")), plazo=PLAZO_TOKEN_S, data={
                "grant_type": "refresh_token", "refresh_token": tokens["refresh"],
                "client_id": str(tomado.get("client_id")), "resource": str(tomado.get("recurso") or "")})
        except BaseException as e:
            # No se sabe si Mnemo alcanzó a rotar: se suelta el arriendo y el siguiente intento lo dirá (si rotó, el
            # refresh viejo dará invalid_grant y la conexión quedará caída)
            await run_in_threadpool(db.meta.update_one, mio, {"$set": {"renovando_hasta": None},
                                                              "$unset": {"renovador": ""}})
            if isinstance(e, _SinRed):
                raise ErrorHerramienta(mc.MENSAJE_RED, mc.COD_PLAZO if e.plazo else mc.COD_RED) from None
            raise
        nuevos = _tokens(r, tokens["refresh"])
        if nuevos is None:
            error = r.datos.get("error") if isinstance(r.datos, dict) else None
            if r.estado in (400, 401) and error in ("invalid_grant", "invalid_client"):
                await run_in_threadpool(_caer, db, mio, "revocada")
                raise ErrorHerramienta(mc.MENSAJE_TOKEN, mc.COD_TOKEN, detalle={"conexion": "revocada"})
            if r.estado == 200:  # Mnemo rotó y respondió algo que no sirve: el refresh viejo ya no vale
                await run_in_threadpool(_caer, db, mio, "error")
                raise ErrorHerramienta(mc.MENSAJE_TOKEN, mc.COD_TOKEN, detalle={"conexion": "error"})
            await run_in_threadpool(db.meta.update_one, mio, {"$set": {"renovando_hasta": None},
                                                              "$unset": {"renovador": ""}})
            log.warning("Mnemo: no se pudo renovar la conexión (HTTP %s)", r.estado)
            raise ErrorHerramienta(f"Mnemo no pudo renovar la conexión (HTTP {r.estado}). Intente de nuevo en un rato.",
                                   mc.COD_MNEMO, estado=r.estado)
        # El refresh nuevo se guarda ANTES de usar el access nuevo: perderlo sería reusar el viejo la próxima vez
        vence = _ahora() + timedelta(seconds=nuevos["expira"])
        campos = {"cifrado": cifrado.cifrar(seguridad.llave_mnemo(self._cfg), {"access": nuevos["access"],
                                                                              "refresh": nuevos["refresh"]},
                                            _contexto(str(tomado.get("emisor")), str(tomado.get("client_id")))),
                  "vence": vence, "renovada_en": _ahora(), "renovando_hasta": None}
        if nuevos["scope"]:
            campos["alcances"] = _alcances(nuevos["scope"], None)
        hecho = None
        for intento in range(GUARDAR_INTENTOS):
            try:
                hecho = await run_in_threadpool(db.meta.update_one, {"_id": ID, "version": version, "renovador": dueño},
                                                {"$set": campos, "$unset": {"renovador": ""}, "$inc": {"version": 1}})
                break
            except Exception:  # noqa: BLE001 - MongoDB falló al guardar: se reintenta, el refresh viejo ya no vale
                if intento == GUARDAR_INTENTOS - 1:
                    log.error("Mnemo: no se pudo guardar la conexión renovada; la próxima renovación fallará")
                    raise
                await asyncio.sleep(0.2 * (intento + 1))
        if hecho is None or hecho.matched_count != 1:
            log.warning("Mnemo: la conexión cambió mientras se renovaba; se descarta lo renovado")
            raise _OtraVez
        self._cache, self._invalidado = (version + 1, nuevos["access"], vence), None
        log.info("Mnemo: se renovó la conexión")
        return nuevos["access"]

    async def _esperar_otro(self, version: int) -> str:
        """Otro (proceso o fuente) tiene el arriendo: se espera a que suba la `version` y se usa lo que guardó. Si
        suelta el arriendo sin renovar, se vuelve a intentar."""
        bucle = asyncio.get_running_loop()
        fin = bucle.time() + ESPERA_OTRO_S
        while bucle.time() < fin:
            await asyncio.sleep(SONDEO_S)
            doc = await run_in_threadpool(_leer, self._db)
            self._exigir(doc)
            if int(doc.get("version") or 0) != version:
                acceso, _ = await self._acceso(doc)
                return acceso
            if _libre(doc, _ahora()):
                raise _OtraVez
        raise ErrorHerramienta("Mnemo tardó demasiado en renovar la conexión. Intente de nuevo en un rato.",
                               mc.COD_PLAZO)
