"""Quién hace cada petición y qué puede hacer: roles, permisos, claves de los usuarios y máscaras.

* Tres roles: el administrador (la credencial de `.env`, uid 0, que no vive en `usuarios`), el planillero y el
  consultor. Denegar por defecto: un rol desconocido no tiene permisos y una sesión con un rol inválido no vale.
* `requiere(*permisos)` es la dependencia de cada ruta de la API: valida la sesión y el CSRF, arma el `Quien` y
  responde 403 `{codigo: "permiso"}` si el rol no tiene todos los permisos pedidos. Deja `dep.permisos` para que una
  prueba recorra las rutas y compare con la tabla de permisos.
* Las claves de los usuarios van con scrypt (n=2^15, r=8, p=1: 32 MiB), como mucho dos a la vez.
* `registrar_lecturas` y `idempotencia_*` tienen su firma final; todavía no hacen nada.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pymongo.database import Database

from .seguridad import METODOS_SEGUROS, huella, ip_de, obtener_db, sesion_actual

ROLES = {"admin", "planillero", "consultor"}
ROLES_USUARIO = ("planillero", "consultor")  # los que viven en la colección `usuarios`
PERMISOS: dict[str, frozenset[str]] = {
    "admin": frozenset({"*"}),
    "planillero": frozenset({
        "cuenta", "catalogos.ver", "insignias", "trabajo.ver", "personas.listar", "personas.buscar", "personas.ver",
        "personas.crear", "personas.editar", "personas.parecidas", "personas.notas", "personas.ubicar",
        "personas.telefonos", "personas.autorizacion", "personas.duplicado", "personas.situacion",
        "personas.no_disponible", "acercamientos.registrar", "acercamientos.ver", "reuniones.ver", "reuniones.crear",
        "reuniones.asistentes", "puestos.ver", "plantillas", "solicitudes.crear",
    }),
    "consultor": frozenset({
        "cuenta", "catalogos.ver", "insignias", "trabajo.ver", "trabajo.cola", "personas.buscar", "personas.ver",
        "personas.telefonos", "personas.autorizacion", "personas.situacion", "personas.no_disponible",
        "acercamientos.registrar", "acercamientos.ver", "puestos.ver", "solicitudes.crear",
    }),
}
SIN_PERMISO = {"mensaje": "Su rol no permite esta acción", "codigo": "permiso"}


@dataclass(kw_only=True)
class Quien:
    """Usuario autenticado de la petición. `uid` es 0 para el administrador y None para el sistema."""
    uid: int | None
    usuario: str | None
    rol: str
    nombre: str | None = None
    ip: str | None = None
    permisos: frozenset[str] = field(default_factory=frozenset)
    asignacion: dict | None = None  # {lugares: [int], areas: [int]} de P y C; None para A (sin límite)

    def puede(self, permiso: str) -> bool:
        return "*" in self.permisos or permiso in self.permisos

    @property
    def es_admin(self) -> bool:
        return self.rol == "admin"


def _quien_de(db: Database, request: Request, s: dict) -> Quien:
    cfg = request.app.state.cfg
    uid = s.get("uid")
    if uid in (None, 0):
        # El rol de administrador sale solo de una sesión sin uid (o con 0) firmada con la credencial vigente de .env
        if not hmac.compare_digest(str(s.get("huella") or ""), huella(cfg)):
            raise HTTPException(401, "Inicie sesión")
        return Quien(uid=0, usuario=s.get("usuario"), nombre=s.get("usuario"), rol="admin", ip=ip_de(request),
                     permisos=PERMISOS["admin"])
    u = db.usuarios.find_one({"_id": uid, "activo": True})
    rol = (u or {}).get("rol")
    if rol not in ROLES_USUARIO:  # usuario inactivo, borrado o con un rol inválido en la base: falla cerrada
        raise HTTPException(401, "Inicie sesión")
    asignacion = u.get("asignacion") or {}
    return Quien(uid=uid, usuario=u.get("usuario"), nombre=u.get("nombre"), rol=rol, ip=ip_de(request),
                 permisos=PERMISOS.get(rol, frozenset()),
                 asignacion={"lugares": list(asignacion.get("lugares") or []), "areas": list(asignacion.get("areas") or [])})


def requiere(*permisos: str, limitar: bool = False) -> Callable[..., Quien]:
    """Dependencia de una ruta: sesión (la que dejó la guardia en `scope["state"]["sesion"]`, o la de la cookie) +
    CSRF en lo que cambia datos + rol + todos los `permisos`. `limitar` marca las rutas con límite de frecuencia por
    usuario (lo aplica el grupo 2)."""
    pedidos = frozenset(permisos)

    def dep(request: Request, db: Database = Depends(obtener_db)) -> Quien:
        s = (request.scope.get("state") or {}).get("sesion")
        if s is None:
            s = sesion_actual(db, request)
        if s is None:
            raise HTTPException(401, "Inicie sesión")
        if request.method not in METODOS_SEGUROS:
            enviado = request.headers.get("x-csrf-token", "")
            esperado = str(s.get("csrf") or "")
            if not esperado or not hmac.compare_digest(enviado.encode(), esperado.encode()):
                raise HTTPException(403, "Token CSRF inválido; recargue la página")
        quien = _quien_de(db, request, s)
        if not all(quien.puede(p) for p in pedidos):
            raise HTTPException(403, dict(SIN_PERMISO))
        return quien

    dep.permisos = pedidos
    dep.limitar = limitar
    return dep


# ───────────────────────────── Claves ─────────────────────────────

SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_LARGO = 2 ** 15, 8, 1, 32
SCRYPT_MEMORIA = 64 * 1024 * 1024
_TURNOS = threading.BoundedSemaphore(2)  # scrypt usa 32 MiB y ~0,1 s de CPU: como mucho dos a la vez
_SAL_FALSA = b"panel-yondo-sal!"
_HASH_FALSO = bytes(SCRYPT_LARGO)
LARGO_MINIMO = 10
CLAVES_COMUNES = frozenset({
    "1234567890", "0123456789", "0987654321", "9876543210", "12345678910", "123456789a", "a123456789", "1234567890a",
    "1q2w3e4r5t", "qwertyuiop", "qwerty1234", "asdfghjkl1", "abcdefghij", "abc1234567", "password12", "password123",
    "contraseña", "contrasena", "contraseña1", "contrasena1", "contraseña123", "contrasena123", "iloveyou12",
    "teamo12345", "colombia123", "colombia2026", "yondo12345", "yondo123456", "yondo2026", "casabe2026",
    "planillero", "consultor1", "administrador", "trabajemosjuntos",
})


def _derivar(clave: str, sal: bytes) -> bytes:
    if not _TURNOS.acquire(timeout=5):
        raise HTTPException(503, "El servidor está ocupado. Intente de nuevo en unos segundos.",
                            headers={"Retry-After": "2"})
    try:
        return hashlib.scrypt(clave.encode("utf-8"), salt=sal, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_LARGO,
                              maxmem=SCRYPT_MEMORIA)
    finally:
        _TURNOS.release()


def hashear_clave(c: str) -> str:
    """`scrypt$32768$8$1$<sal hex>$<hash hex>`, con sal aleatoria de 16 bytes."""
    sal = secrets.token_bytes(16)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${sal.hex()}${_derivar(c, sal).hex()}"


def _leer_guardada(guardada: Any) -> tuple[bytes, bytes] | None:
    partes = guardada.split("$") if isinstance(guardada, str) else []
    if len(partes) != 6 or partes[:4] != ["scrypt", str(SCRYPT_N), str(SCRYPT_R), str(SCRYPT_P)]:
        return None
    try:
        sal, esperado = bytes.fromhex(partes[4]), bytes.fromhex(partes[5])
    except ValueError:
        return None
    return (sal, esperado) if len(sal) == 16 and len(esperado) == SCRYPT_LARGO else None


def verificar_clave(guardada: str | None, c: str) -> bool:
    """¿`c` es la clave guardada? Sin clave guardada (usuario que no existe) o con una mal formada hace el mismo
    trabajo con una sal falsa: la respuesta tarda lo mismo y no revela si el usuario existe."""
    leida = _leer_guardada(guardada)
    sal, esperado = leida if leida else (_SAL_FALSA, _HASH_FALSO)
    ok = hmac.compare_digest(_derivar(c or "", sal), esperado)
    return ok and leida is not None


def clave_temporal() -> str:
    """Clave temporal de 12 caracteres: se muestra una sola vez y nunca va a la auditoría."""
    return secrets.token_urlsafe(9)


def validar_clave_nueva(usuario: str | None, c: str) -> None:
    """422 con el motivo si la clave nueva no sirve: corta, igual al usuario, común o casi sin variedad."""
    if len(c or "") < LARGO_MINIMO:
        raise HTTPException(422, f"La clave debe tener al menos {LARGO_MINIMO} caracteres")
    if c.strip().lower() == (usuario or "").strip().lower():
        raise HTTPException(422, "La clave no puede ser igual al usuario")
    if c.strip().lower() in CLAVES_COMUNES or len(set(c)) < 4:
        raise HTTPException(422, "Esa clave es demasiado fácil de adivinar; elija otra")


# ───────────────────────────── Máscaras ─────────────────────────────

MASCARA = "···"


def enmascarar_cedula(c: Any) -> str | None:
    """«···123»: solo los 3 últimos dígitos."""
    s = re.sub(r"\s+", "", str(c)) if c not in (None, "") else ""
    return f"{MASCARA}{s[-3:]}" if s else None


def enmascarar_telefono(t: Any) -> str | None:
    """«···2233»: solo los 4 últimos dígitos."""
    s = re.sub(r"\s+", "", str(t)) if t not in (None, "") else ""
    return f"{MASCARA}{s[-4:]}" if s else None


# ───────────────────────────── Lecturas e idempotencia (grupo 2) ─────────────────────────────

def registrar_lecturas(db: Database, quien: Quien, pids: Iterable[int], ficha: bool = False) -> None:
    """Anota en `lecturas` las personas servidas a `quien` y, para P y C, responde 429 `{codigo: "volumen"}` al pasar
    el presupuesto diario. Todavía no hace nada."""
    return None


def idempotencia_previa(db: Database, quien: Quien, request: Request) -> JSONResponse | None:
    """Con `Idempotency-Key`: la respuesta guardada de esa clave, o 409 `{codigo: "en_proceso"}` mientras la primera
    sigue en curso. Todavía no hace nada (devuelve None: la petición sigue)."""
    return None


def idempotencia_guardar(db: Database, quien: Quien, request: Request, codigo: int, cuerpo: Any,
                         persona_id: int | None = None) -> None:
    """Guarda la respuesta de una petición con `Idempotency-Key`. Todavía no hace nada."""
    return None
