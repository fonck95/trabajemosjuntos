"""Autenticación del administrador, sesiones, CSRF, límite de intentos y cabeceras de seguridad.

* Usuario y clave salen de las variables de entorno `ADMIN` y `password`; se comparan en tiempo constante.
* La sesión es un token aleatorio en una cookie HttpOnly + SameSite=Strict (Secure en producción); en MongoDB
  solo se guarda su hash SHA-256, y la sesión caduca sola (índice TTL).
* Toda petición que cambia datos debe traer la cabecera X-CSRF-Token de la sesión.
* Cinco intentos fallidos por IP en 15 minutos bloquean esa IP; 30 en total bloquean el ingreso por 15 minutos.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, Response
from pymongo.database import Database
from starlette.middleware.base import BaseHTTPMiddleware

COOKIE = "yj_sesion"
VENTANA_S = 15 * 60
MAX_POR_IP = 5
MAX_GLOBAL = 30
METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}


def _h(s: str) -> bytes:
    return hashlib.sha256(s.encode("utf-8")).digest()


def credenciales_validas(cfg, usuario: str, clave: str) -> bool:
    if not cfg.usuario or not cfg.clave:
        return False
    ok_u = hmac.compare_digest(_h(usuario), _h(cfg.usuario))
    ok_c = hmac.compare_digest(_h(clave), _h(cfg.clave))
    return ok_u and ok_c


def ip_de(request: Request) -> str:
    return request.client.host if request.client else "?"


def bloqueado(db: Database, ip: str) -> bool:
    desde = datetime.now(timezone.utc) - timedelta(seconds=VENTANA_S)
    por_ip = db.intentos.count_documents({"ip": ip, "ok": False, "ts": {"$gt": desde}})
    total = db.intentos.count_documents({"ok": False, "ts": {"$gt": desde}})
    return por_ip >= MAX_POR_IP or total >= MAX_GLOBAL


def registrar_intento(db: Database, ip: str, ok: bool) -> None:
    db.intentos.insert_one({"ip": ip, "ts": datetime.now(timezone.utc), "ok": ok})
    if ok:  # un ingreso correcto limpia los fallos de esa IP
        db.intentos.delete_many({"ip": ip, "ok": False})


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def crear_sesion(db: Database, cfg, response: Response, usuario: str, request: Request) -> str:
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    expira = datetime.now(timezone.utc) + timedelta(hours=cfg.horas_sesion)
    db.sesiones.insert_one({"_id": _hash(token), "usuario": usuario, "csrf": csrf, "creada": datetime.now(timezone.utc),
                            "expira": expira, "ip": ip_de(request), "agente": (request.headers.get("user-agent") or "")[:200]})
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
    return s


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
