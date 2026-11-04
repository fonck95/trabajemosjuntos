"""Autenticación del administrador, sesiones, CSRF, límite de intentos y cabeceras de seguridad.

* Usuario y clave salen de las variables de entorno `ADMIN` y `password`; se comparan en tiempo constante.
* La sesión es un token aleatorio en una cookie HttpOnly + SameSite=Strict (Secure en producción); en MongoDB
  solo se guarda su hash SHA-256, y la sesión caduca sola (índice TTL).
* Cada sesión guarda una huella de usuario y clave: si cambian ADMIN o password, las sesiones abiertas dejan de valer.
* Toda petición que cambia datos debe traer la cabecera X-CSRF-Token de la sesión.
* Cinco intentos fallidos por IP en 15 minutos bloquean esa IP (como mucho 15 minutos). Con más de 100 fallos en
  total, cada intento espera un retroceso exponencial corto (como mucho 60 s): el ingreso nunca queda bloqueado
  indefinidamente.
* Ninguna ruta /api/* (salvo /api/login y /api/yo) se atiende sin sesión y el cuerpo de la petición tiene tamaño
  máximo: las dos cosas se comprueban antes de leerlo.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import math
import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from fastapi import Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError
from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware

COOKIE = "yj_sesion"
COOKIE_DISPOSITIVO = "yj_dispositivo"
DIAS_DISPOSITIVO = 180
VENTANA_S = 15 * 60
MAX_POR_IP = 5
MAX_GLOBAL = 100
ESPERA_MAX_S = 60
METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}
MB = 1 << 20
LIMITE_JSON = 256 * 1024  # el JSON más grande del panel (una ficha o una reunión) cabe de sobra
RUTAS_SIN_SESION = {"/api/login", "/api/yo"}
USUARIO_DESCONOCIDO = "desconocido"  # en la auditoría de un ingreso fallido con otro usuario


def _h(s: str) -> bytes:
    return hashlib.sha256(s.encode("utf-8")).digest()


def credenciales_validas(cfg, usuario: str, clave: str) -> bool:
    if not cfg.usuario or not cfg.clave:
        return False
    ok_u = hmac.compare_digest(_h(usuario), _h(cfg.usuario))
    ok_c = hmac.compare_digest(_h(clave), _h(cfg.clave))
    return ok_u and ok_c


def usuario_correcto(cfg, usuario: str) -> bool:
    return bool(cfg.usuario) and hmac.compare_digest(_h(usuario), _h(cfg.usuario))


def _ip_valida(valor: str | None) -> str | None:
    try:
        return str(ipaddress.ip_address((valor or "").strip()))
    except ValueError:
        return None


def ip_de(request: Request) -> str:
    """IP del cliente, para el límite de intentos y la auditoría.

    En Railway el panel está detrás del proxy de borde y uvicorn arranca con `--proxy-headers
    --forwarded-allow-ips=*`, que copia a `request.client` el PRIMER valor de X-Forwarded-For: ese lo escribe el
    cliente y se puede falsificar. Por eso se usa, en este orden:
    1. X-Real-IP: el borde de Railway la pone en cada petición con la IP real y sobrescribe la que mande el cliente
       (respuestas del personal de Railway en station.railway.com, mayo y septiembre de 2026).
    2. El ÚLTIMO valor de X-Forwarded-For, que es el que añade el proxy más cercano.
    3. La dirección de la conexión.
    Sin un proxy delante que fije estas cabeceras (servidor expuesto directo a Internet) se podrían falsificar."""
    h = request.headers
    ip = _ip_valida(h.get("x-real-ip"))
    if ip is None and h.get("x-forwarded-for"):
        ip = _ip_valida(h["x-forwarded-for"].split(",")[-1])
    # El respaldo también se valida: con --forwarded-allow-ips=* uvicorn ya puso aquí el valor que escribió el cliente
    return ip or _ip_valida(request.client.host if request.client else None) or "?"


def _clave_ip(ip: str) -> str:
    """Clave del límite por IP: una IPv6 cuenta por su /64, que suele ser de un solo cliente."""
    try:
        d = ipaddress.ip_address(ip)
    except ValueError:
        return ip[:64]
    if d.version == 6:
        if d.ipv4_mapped is not None:
            return str(d.ipv4_mapped)
        return str(ipaddress.IPv6Network((int(d) >> 64 << 64, 64)))
    return str(d)


def _segundos(t: timedelta) -> int:
    return max(1, math.ceil(t.total_seconds()))


def reservar_intento(db: Database, ip: str, conocido: bool = False):
    """Registra el intento ANTES de comprobar la clave y decide si se atiende.

    Devuelve (id del intento, 0) si se puede comprobar la clave, o (None, segundos de espera) si no. Se cuenta
    después de insertar, incluidos el propio intento y los simultáneos: una ráfaga en paralelo no pasa del límite.
    Los intentos rechazados se borran: no alargan el bloqueo ni cuentan para el límite global.
    `conocido`: el navegador trae la marca de un ingreso correcto anterior (ver `dispositivo_conocido`); no compite
    por el turno del freno global, así una inundación desde muchas IPs no deja fuera al administrador."""
    ahora = datetime.now(timezone.utc)
    desde = ahora - timedelta(seconds=VENTANA_S)
    clave = _clave_ip(ip)
    iid = db.intentos.insert_one({"ip": clave, "ts": ahora, "ok": False}).inserted_id
    de_ip = {"ip": clave, "ok": False, "ts": {"$gt": desde}}
    n = db.intentos.count_documents(de_ip)
    if n > MAX_POR_IP:
        db.intentos.delete_one({"_id": iid})
        # La IP se libera cuando sale de la ventana el fallo que sobra (como mucho 15 minutos)
        x = next(db.intentos.find(de_ip, {"ts": 1}).sort("ts", 1).skip(max(0, n - MAX_POR_IP - 1)).limit(1), None)
        return None, _segundos(x["ts"] + timedelta(seconds=VENTANA_S) - ahora if x else timedelta(seconds=1))
    total = db.intentos.count_documents({"ok": False, "ts": {"$gt": desde}})
    if total > MAX_GLOBAL and not conocido:
        # Muchos fallos desde muchas IPs: cada intento atendido abre una espera corta (1, 2, 4… hasta 60 s). Un solo
        # documento hace de turno, así que dos intentos simultáneos no pasan a la vez.
        espera = min(2 ** min(total - MAX_GLOBAL - 1, 10), ESPERA_MAX_S)
        try:
            db.intentos.find_one_and_update({"_id": "freno_global", "hasta": {"$lte": ahora}},
                                            {"$set": {"hasta": ahora + timedelta(seconds=espera)}}, upsert=True)
        except DuplicateKeyError:  # el turno lo tiene otro intento
            db.intentos.delete_one({"_id": iid})
            f = db.intentos.find_one({"_id": "freno_global"}) or {}
            return None, _segundos(min(f.get("hasta", ahora) - ahora, timedelta(seconds=ESPERA_MAX_S)))
    return iid, 0


def resolver_intento(db: Database, iid, ip: str, ok: bool) -> None:
    """El intento reservado queda como fallo; si la clave era correcta, se marca y se limpian los fallos de esa IP."""
    if ok:
        db.intentos.update_one({"_id": iid}, {"$set": {"ok": True}})
        db.intentos.delete_many({"ip": _clave_ip(ip), "ok": False})


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@lru_cache(maxsize=8)
def _llave(usuario: str, clave: str) -> bytes:
    # Derivación lenta (una vez por proceso): la huella guardada en la base no sirve para adivinar la clave rápido
    return hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), b"panel-yondo|" + usuario.encode("utf-8"), 600_000)


def huella(cfg) -> str:
    """Huella HMAC de la credencial vigente: si cambian ADMIN o password, cambia y las sesiones viejas no valen."""
    return hmac.new(_llave(cfg.usuario or "", cfg.clave or ""), b"sesion", hashlib.sha256).hexdigest()


def _firma_dispositivo(cfg, marca: str) -> str:
    return hmac.new(_llave(cfg.usuario or "", cfg.clave or ""), b"dispositivo|" + marca.encode(), hashlib.sha256).hexdigest()


def marcar_dispositivo(cfg, response: Response) -> None:
    """Tras un ingreso correcto, el navegador recibe una marca firmada con la credencial vigente (sin datos)."""
    marca = secrets.token_urlsafe(18)
    response.set_cookie(COOKIE_DISPOSITIVO, f"{marca}.{_firma_dispositivo(cfg, marca)}", max_age=DIAS_DISPOSITIVO * 86400,
                        httponly=True, secure=cfg.cookie_segura, samesite="strict", path="/api/login")


def dispositivo_conocido(cfg, request: Request) -> bool:
    """¿El navegador ya ingresó antes con la credencial vigente? Si cambian ADMIN o password, la marca deja de valer."""
    valor = request.cookies.get(COOKIE_DISPOSITIVO) or ""
    marca, _, firma = valor.partition(".")
    if not marca or len(valor) > 200 or not cfg.usuario or not cfg.clave:
        return False
    return hmac.compare_digest(firma.encode(), _firma_dispositivo(cfg, marca).encode())


def crear_sesion(db: Database, cfg, response: Response, usuario: str, request: Request) -> str:
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    expira = datetime.now(timezone.utc) + timedelta(hours=cfg.horas_sesion)
    db.sesiones.insert_one({"_id": _hash(token), "usuario": usuario, "csrf": csrf, "huella": huella(cfg),
                            "creada": datetime.now(timezone.utc), "expira": expira, "ip": ip_de(request),
                            "agente": (request.headers.get("user-agent") or "")[:200]})
    response.set_cookie(COOKIE, token, max_age=cfg.horas_sesion * 3600, httponly=True, secure=cfg.cookie_segura,
                        samesite="strict", path="/")
    return csrf


def cerrar_sesion(db: Database, request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        db.sesiones.delete_one({"_id": _hash(token)})
    response.delete_cookie(COOKIE, path="/")


def sesion_actual(db: Database, request: Request) -> dict | None:
    token = request.cookies.get(COOKIE)
    if not token or len(token) > 100:
        return None
    s = db.sesiones.find_one({"_id": _hash(token)})
    if s is None or s["expira"] < datetime.now(timezone.utc):
        return None
    # Solo valen las sesiones de la credencial vigente
    if not hmac.compare_digest(str(s.get("huella") or ""), huella(request.app.state.cfg)):
        return None
    return s


def limpiar_al_iniciar(db: Database, cfg) -> None:
    """Al arrancar: cierra las sesiones de otra credencial y borra lo que se escribió como usuario en los ingresos
    fallidos auditados antes de este cambio (podía ser la clave)."""
    db.sesiones.delete_many({"huella": {"$ne": huella(cfg)}})
    db.auditoria.update_many({"accion": "ingreso_fallido", "usuario": {"$nin": [cfg.usuario, USUARIO_DESCONOCIDO]}},
                             {"$set": {"usuario": USUARIO_DESCONOCIDO}})


def obtener_db(request: Request) -> Database:
    return request.app.state.db


class Admin:
    """Usuario autenticado de la petición (para auditoría)."""

    def __init__(self, usuario: str, ip: str):
        self.usuario = usuario
        self.ip = ip


def requiere_admin(request: Request, db: Database = Depends(obtener_db)) -> Admin:
    s = sesion_actual(db, request)
    if s is None:
        raise HTTPException(401, "Inicie sesión")
    if request.method not in METODOS_SEGUROS:
        enviado = request.headers.get("x-csrf-token", "")
        if not hmac.compare_digest(enviado.encode(), s["csrf"].encode()):
            raise HTTPException(403, "Token CSRF inválido; recargue la página")
    return Admin(s["usuario"], ip_de(request))


class CuerpoDemasiadoGrande(HTTPException):
    def __init__(self):
        super().__init__(413, "La petición es demasiado grande")


class GuardiaApi:
    """Middleware ASGI que actúa antes de que nadie lea el cuerpo de la petición.

    FastAPI lee el cuerpo entero (y guarda en disco cada archivo subido) antes de resolver `requiere_admin`: sin
    esto, un anónimo podía llenar la memoria con un JSON enorme o el disco con una subida a /api/importar.
    * Limita el tamaño del cuerpo, por su Content-Length y contando lo que llega por partes.
    * Rechaza sin sesión válida toda ruta /api/*, salvo /api/login y /api/yo. El CSRF sigue en `requiere_admin`."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        app, ruta = scope["app"], scope["path"]
        # Importar acepta hasta 6 Excel de max_subida_mb cada uno; el resto es JSON pequeño
        limite = (app.state.cfg.max_subida_mb * 6 + 1) * MB if ruta == "/api/importar" else LIMITE_JSON
        largo = Headers(scope=scope).get("content-length", "")
        if largo.isdigit() and int(largo) > limite:
            return await JSONResponse({"detail": "La petición es demasiado grande"}, 413)(scope, receive, send)
        if ruta.startswith("/api/") and ruta not in RUTAS_SIN_SESION:
            if await run_in_threadpool(sesion_actual, app.state.db, Request(scope)) is None:
                return await JSONResponse({"detail": "Inicie sesión"}, 401)(scope, receive, send)
        recibidos = 0

        async def recibir():
            nonlocal recibidos
            msg = await receive()
            if msg["type"] == "http.request":
                recibidos += len(msg.get("body", b""))
                if recibidos > limite:
                    raise CuerpoDemasiadoGrande()
            return msg

        await self.app(scope, recibir, send)


CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "worker-src 'self' blob:",
    "child-src blob:",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data: blob: https://tiles.openfreemap.org https://server.arcgisonline.com https://s3.amazonaws.com",
    "connect-src 'self' https://tiles.openfreemap.org https://server.arcgisonline.com https://s3.amazonaws.com",
    "frame-ancestors 'none'",
    "base-uri 'none'",
    "form-action 'self'",
    "object-src 'none'",
])


class CabecerasSeguras(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        resp = await call_next(request)
        h = resp.headers
        h["Content-Security-Policy"] = CSP
        h["X-Content-Type-Options"] = "nosniff"
        h["X-Frame-Options"] = "DENY"
        h["Referrer-Policy"] = "no-referrer"
        h["X-Robots-Tag"] = "noindex, nofollow"
        h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(self)"
        h["Cross-Origin-Opener-Policy"] = "same-origin"
        if request.app.state.cfg.cookie_segura:
            h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.url.path.startswith("/api/"):
            h["Cache-Control"] = "no-store"
        return resp
