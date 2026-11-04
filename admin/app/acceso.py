"""Quién hace cada petición y qué puede hacer: roles, permisos, claves de los usuarios, máscaras, lecturas,
frecuencia e idempotencia.

* Cuatro roles: el administrador (A, la credencial de `.env`, uid 0, que no vive en `usuarios`), el coordinador (K),
  el planillero (P) y el consultor (C). K tiene todos los permisos de A salvo `SOLO_ADMIN` (gestionar coordinadores,
  cambiar roles y cambiar los ajustes que son permisos); lo que es de A en el manejo de datos se comprueba con
  `quien.puede(...)` o `quien.administra`, nunca con el rol. Denegar por defecto: un rol desconocido no tiene permisos
  y una sesión con un rol inválido no vale.
* `requiere(*permisos)` es la dependencia de cada ruta de la API: valida la sesión y el CSRF, arma el `Quien`,
  vuelve a exigir la clave cambiada y el compromiso al día (la guardia ya lo hizo) y responde 403
  `{codigo: "permiso"}` si el rol no tiene todos los permisos pedidos. Deja `dep.permisos` para que una prueba recorra
  las rutas y compare con la tabla de permisos. Con `limitar=True`, P y C tienen además un límite de frecuencia.
* Las claves de los usuarios van con scrypt (n=2^15, r=8, p=1: 32 MiB), como mucho dos a la vez.
* `registrar_lecturas` anota en `lecturas` las personas servidas a cada usuario (también al administrador) y aplica
  el presupuesto diario de P y C. Con 20 rechazos por volumen en el día se cierran sus sesiones.
* `idempotencia_previa` e `idempotencia_guardar`: con `Idempotency-Key`, un POST repetido devuelve la respuesta
  guardada sin repetir efectos. Si la ruta falla o no guarda, la clave se libera al terminar la petición.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import math
import re
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable

from fastapi import Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response
from pymongo import ASCENDING, ReturnDocument, UpdateOne
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError, OperationFailure

from . import db as bd
from . import modelo
from .seguridad import (METODOS_SEGUROS, ROLES_ADMIN, ROLES_USUARIO, SIN_PERMISO, huella, ip_de, obtener_db,
                        rechazo_de_cuenta, ruta_interna, sesion_actual)

log = logging.getLogger("panel")

ROLES = {"admin", "coordinador", "planillero", "consultor"}
# Lo único que el coordinador no puede (adenda 1): solo A crea, edita, desactiva, reactiva o restablece la clave de un
# coordinador, cambia el rol de un usuario y cambia los ajustes que son permisos o límites de acceso
SOLO_ADMIN = frozenset({"usuarios.coordinadores", "usuarios.roles", "permisos.modificar"})
ROLES_CAMPO = ("planillero", "consultor")  # con alcance, presupuesto diario y límite de frecuencia
PERMISOS: dict[str, frozenset[str]] = {
    "admin": frozenset({"*"}),
    "coordinador": frozenset({"*"}),  # «*» menos SOLO_ADMIN: lo resta `Quien.puede`
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


@dataclass(kw_only=True)
class Quien:
    """Usuario autenticado de la petición. `uid` es 0 para el administrador y None para el sistema."""
    uid: int | None
    usuario: str | None
    rol: str
    nombre: str | None = None
    ip: str | None = None
    permisos: frozenset[str] = field(default_factory=frozenset)
    asignacion: dict | None = None  # {lugares: [int], areas: [int]} de P y C; None para A y K (sin límite)

    def puede(self, permiso: str) -> bool:
        """¿Tiene el permiso? Lo de `SOLO_ADMIN` es solo de A, aunque otro rol tenga «*»."""
        if permiso in SOLO_ADMIN and not self.es_admin:
            return False
        return "*" in self.permisos or permiso in self.permisos

    @property
    def es_admin(self) -> bool:
        """¿Es el administrador de `.env` (uid 0)? Solo para lo exclusivo de A y para su sesión."""
        return self.rol == "admin" and self.uid in (0, None)

    @property
    def administra(self) -> bool:
        """¿Es A o K? Manejo de datos sin recorte, sin alcance, sin presupuesto diario ni límite de frecuencia."""
        return self.rol in ROLES_ADMIN


def excepto(rol: str | None) -> list[str]:
    """Permisos que el rol no tiene aunque tenga «*» (los de `SOLO_ADMIN` para K): van a la interfaz con la sesión."""
    return sorted(SOLO_ADMIN) if rol != "admin" and "*" in PERMISOS.get(rol or "", ()) else []


def quien_admin(cfg, ip: str | None = None) -> Quien:
    """El administrador de `.env` como `Quien` (uid 0)."""
    return Quien(uid=0, usuario=cfg.usuario, nombre=cfg.usuario, rol="admin", ip=ip, permisos=PERMISOS["admin"])


def _quien_de(db: Database, request: Request, s: dict) -> Quien:
    cfg = request.app.state.cfg
    uid = s.get("uid")
    if uid in (None, 0):
        # El rol de administrador sale solo de una sesión sin uid (o con 0) firmada con la credencial vigente de .env
        if not hmac.compare_digest(str(s.get("huella") or ""), huella(cfg)):
            raise HTTPException(401, "Inicie sesión")
        return Quien(uid=0, usuario=s.get("usuario"), nombre=s.get("usuario"), rol="admin", ip=ip_de(request),
                     permisos=PERMISOS["admin"])
    u = s.get("_usuario") or db.usuarios.find_one({"_id": uid, "activo": True}, {"clave": 0})
    rol = (u or {}).get("rol")
    if not (u or {}).get("activo") or rol not in ROLES_USUARIO:  # inactivo, borrado o rol inválido: falla cerrada
        raise HTTPException(401, "Inicie sesión")
    asignacion = u.get("asignacion") or {}
    return Quien(uid=uid, usuario=u.get("usuario"), nombre=u.get("nombre"), rol=rol, ip=ip_de(request),
                 permisos=PERMISOS.get(rol, frozenset()),
                 asignacion=None if rol in ROLES_ADMIN else {"lugares": list(asignacion.get("lugares") or []),
                                                             "areas": list(asignacion.get("areas") or [])})


def requiere(*permisos: str, limitar: bool = False) -> Callable[..., Quien]:
    """Dependencia de una ruta: sesión (la que dejó la guardia en `scope["state"]["sesion"]`, o la de la cookie) +
    CSRF en lo que cambia datos + rol + todos los `permisos`. `limitar` marca las rutas con límite de frecuencia por
    usuario (120 por minuto para P y C; A y K quedan exentos). Al terminar la petición libera la clave de
    idempotencia que la ruta tomó y no guardó (falló o no la usó)."""
    pedidos = frozenset(permisos)

    def dep(request: Request, db: Database = Depends(obtener_db)):
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
        if not quien.es_admin:
            rechazo = rechazo_de_cuenta(s, ruta_interna(request.scope), db)
            if rechazo is not None:
                raise HTTPException(403, rechazo)
        if not all(quien.puede(p) for p in pedidos):
            raise HTTPException(403, dict(SIN_PERMISO))
        if limitar and not quien.administra:
            _frecuencia(db, quien.uid)
        try:
            yield quien
        finally:
            _soltar_idempotencia(db, request)

    dep.permisos = pedidos
    dep.limitar = limitar
    return dep


# Lo que usaban las rutas del administrador: ahora es `requiere("admin")` (seguridad.requiere_admin lo reexporta)
requiere_admin = requiere("admin")
Admin = Quien

# ───────────────────────────── Ajustes que son permisos (adenda 1) ─────────────────────────────

# Ajustes que fijan permisos o límites de acceso: solo A los cambia (`permisos.modificar`); K los ve en solo lectura
AJUSTES_DE_PERMISOS = frozenset({
    "presupuesto_diario", "sesion",  # límites de acceso de los usuarios
    "politica", "contactar_pendientes", "dias_entre_intentos", "max_intentos_sin_exito", "seguimiento_activo",
    "dias_seguimiento", "horario",  # política de contacto del consultor
    "sensibles_activos", "tope_cedulas_dictadas", "compromiso_version",  # qué se ve y con qué condiciones se trabaja
})


def _cambia(actual: Any, nuevo: Any) -> bool:
    if isinstance(nuevo, dict) and isinstance(actual, dict):
        return any(_cambia(actual.get(k), v) for k, v in nuevo.items())
    return nuevo != actual


def ajustes_de_permisos(actuales: dict, cambios: dict) -> list[str]:
    """Claves de `cambios` que dan a un ajuste de permisos un valor distinto del vigente. Un formulario que manda todo
    sin tocar esos valores (o solo parte de un objeto, como `sesion`) no cuenta."""
    return sorted(k for k, v in (cambios or {}).items()
                  if k in AJUSTES_DE_PERMISOS and _cambia((actuales or {}).get(k), v))


def exigir_ajustes(quien: Quien | None, actuales: dict, cambios: dict) -> None:
    """Para PUT /api/ajustes: 403 `{codigo: "permiso", campos}` si `quien` cambia un ajuste de permisos sin
    `permisos.modificar` (el coordinador). Los demás ajustes los cambian A y K."""
    campos = ajustes_de_permisos(actuales, cambios)
    if campos and not (quien is not None and quien.puede("permisos.modificar")):
        raise HTTPException(403, {**SIN_PERMISO, "campos": campos,
                                  "mensaje": "Solo el administrador cambia los permisos y límites de acceso"})

# ───────────────────────────── Claves ─────────────────────────────

SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_LARGO = 2 ** 15, 8, 1, 32
SCRYPT_MEMORIA = 64 * 1024 * 1024
_TURNOS = threading.BoundedSemaphore(2)  # scrypt usa 32 MiB y ~0,1 s de CPU: como mucho dos a la vez
_SAL_FALSA = b"panel-yondo-sal!"
_HASH_FALSO = bytes(SCRYPT_LARGO)
LARGO_MINIMO = 10
HORAS_CLAVE_TEMPORAL = 72
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


def vence_temporal() -> str:
    """Vencimiento de una clave temporal recién generada (ISO UTC, como `bd.ahora()`)."""
    return (datetime.now(timezone.utc) + timedelta(hours=HORAS_CLAVE_TEMPORAL)).replace(microsecond=0).isoformat()


def clave_vencida(u: dict | None) -> bool:
    """¿El usuario tiene una clave temporal sin cambiar que ya venció? Vencida, el ingreso da el 401 genérico."""
    if not u or not u.get("debe_cambiar_clave") or not u.get("clave_temporal_vence"):
        return False
    vence = u["clave_temporal_vence"]
    try:
        vence = vence if isinstance(vence, datetime) else datetime.fromisoformat(str(vence))
    except ValueError:
        return True  # un vencimiento ilegible no se da por vigente
    if vence.tzinfo is None:
        vence = vence.replace(tzinfo=timezone.utc)
    return vence <= datetime.now(timezone.utc)


# ───────────────────────────── Usuarios ─────────────────────────────

USUARIO_VALIDO = re.compile(r"[a-z0-9._-]{3,40}")
# Nombres que no puede tener un usuario: los que la auditoría usa para otros actores
RESERVADOS = frozenset({"sistema", "consola", "desconocido", "admin", "migración", "migracion"})


def clave_ingresos(db: Database) -> bytes:
    """Clave secreta (aleatoria, creada la primera vez) del HMAC de los nombres escritos al ingresar."""
    m = db.meta.find_one_and_update({"_id": "clave_ingresos"}, {"$setOnInsert": {"valor": secrets.token_hex(32)}},
                                    upsert=True, return_document=ReturnDocument.AFTER)
    return bytes.fromhex(m["valor"])


def nombre_h(db: Database, nombre: str | None, clave: bytes | None = None) -> str:
    """HMAC del nombre escrito al ingresar (en minúsculas), exista o no la cuenta: cuenta los fallos por nombre sin
    guardar lo escrito (a veces es la clave)."""
    clave = clave or clave_ingresos(db)
    return hmac.new(clave, b"ingreso|" + (nombre or "").strip().lower().encode("utf-8"), hashlib.sha256).hexdigest()


def cerrar_sesiones(db: Database, uid: int) -> int:
    """Sube la `version` del usuario (su huella cambia) y borra sus sesiones. Devuelve cuántas había."""
    db.usuarios.update_one({"_id": uid}, {"$inc": {"version": 1}, "$set": {"actualizado_en": bd.ahora()}})
    return db.sesiones.delete_many({"uid": uid}).deleted_count


def preparar(db: Database) -> None:
    """Índices de lo que usa este módulo (los mismos de 1.10, que `db.inicializar` también puede crear). Si ya
    existe uno igual con otras opciones, se avisa en el registro y el arranque sigue."""
    indices = [
        (db.usuarios, [("usuario", ASCENDING)], {"unique": True}),
        (db.sesiones, [("uid", ASCENDING)], {}),
        (db.intentos, [("nombre_h", ASCENDING), ("ts", ASCENDING)], {}),
        (db.intentos, [("ip", ASCENDING), ("marca_h", ASCENDING), ("ts", ASCENDING)], {}),
        (db.lecturas, [("uid", ASCENDING), ("dia", ASCENDING)], {}),
        (db.lecturas, [("ts", ASCENDING)], {"expireAfterSeconds": 90 * 86400}),
        (db.idempotencia, [("ts", ASCENDING)], {"expireAfterSeconds": 86400}),
        (db.idempotencia, [("persona_id", ASCENDING)], {}),
    ]
    for coleccion, claves, opciones in indices:
        try:
            coleccion.create_index(claves, **opciones)
        except OperationFailure as e:
            log.warning("Índice %s.%s con otras opciones: %s", coleccion.name, claves, e.code)


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


# ───────────────────────────── Frecuencia ─────────────────────────────

FRECUENCIA_MAX, FRECUENCIA_S = 120, 60
_ventanas: dict[tuple[str, int], deque] = {}
_candado_ventanas = threading.Lock()


def _frecuencia(db: Database, uid: int) -> None:
    """Ventana deslizante en memoria por usuario (y base): 120 peticiones limitadas por minuto. Vale por proceso; con
    réplicas sería un límite por réplica."""
    ahora = time.monotonic()
    with _candado_ventanas:
        if len(_ventanas) > 5000:  # se olvidan las ventanas ya vacías
            for k in [k for k, v in _ventanas.items() if not v or v[-1] <= ahora - FRECUENCIA_S]:
                del _ventanas[k]
        v = _ventanas.setdefault((db.name, uid), deque())
        while v and v[0] <= ahora - FRECUENCIA_S:
            v.popleft()
        if len(v) >= FRECUENCIA_MAX:
            espera = max(1, math.ceil(v[0] + FRECUENCIA_S - ahora))
            raise HTTPException(429, {"mensaje": "Demasiadas consultas seguidas. Espere un momento.",
                                      "codigo": "frecuencia"}, headers={"Retry-After": str(espera)})
        v.append(ahora)


# ───────────────────────────── Lecturas ─────────────────────────────

RECHAZOS_CIERRE = 20  # respuestas 429 por volumen en un día que cierran las sesiones del usuario


def presupuesto(db: Database, rol: str, ajustes: dict | None = None) -> int | None:
    """Personas distintas por día que puede consultar el rol (None: sin tope, como A y K)."""
    if rol not in ROLES_CAMPO:
        return None
    aj = ajustes or modelo.leer_ajustes(db)
    try:
        return int(aj["presupuesto_diario"].get(rol))
    except (TypeError, ValueError, KeyError):
        return int(modelo.AJUSTES_POR_DEFECTO["presupuesto_diario"][rol])


def registrar_lecturas(db: Database, quien: Quien, pids: Iterable[int], ficha: bool = False) -> None:
    """Anota en `lecturas` las personas servidas a `quien` (una por persona y día, también para A y K) y, para P y
    C, responde 429 `{codigo: "volumen"}` si con ellas pasa el presupuesto diario de personas distintas. Una
    ficha cuenta igual venga de un GET, un PATCH sin cambios o `?resumen=1`."""
    if quien is None or quien.uid is None:
        return
    ids = list(dict.fromkeys(p for p in pids or [] if isinstance(p, int) and not isinstance(p, bool)))
    if not ids:
        return
    dia = modelo.hoy_local().isoformat()
    ahora = datetime.now(timezone.utc)
    ops = []
    for pid in ids:
        nuevo = {"uid": quien.uid, "pid": pid, "dia": dia}
        if ficha:
            cambio = {"$set": {"ts": ahora, "ficha": True}, "$setOnInsert": nuevo}
        else:
            cambio = {"$set": {"ts": ahora}, "$setOnInsert": {**nuevo, "ficha": False}}
        ops.append(UpdateOne({"_id": f"{quien.uid}|{pid}|{dia}"}, cambio, upsert=True))
    res = db.lecturas.bulk_write(ops, ordered=False)
    tope = None if quien.administra else presupuesto(db, quien.rol)
    if tope is None or db.lecturas.count_documents({"uid": quien.uid, "dia": dia}) <= tope:
        return
    # Se pasó: las personas nuevas de esta respuesta no se sirven ni cuentan
    nuevas = list(res.upserted_ids.values())
    if nuevas:
        db.lecturas.delete_many({"_id": {"$in": nuevas}})
    _rechazo_por_volumen(db, quien, dia, tope)
    raise HTTPException(429, {"mensaje": f"Llegó al tope de {tope} personas consultadas hoy. Podrá seguir mañana.",
                              "codigo": "volumen"})


def _rechazo_por_volumen(db: Database, quien: Quien, dia: str, tope: int) -> None:
    """Cuenta el rechazo del día en el usuario: el primero se audita como `alerta_volumen` (A la ve en Usuarios) y desde
    el vigésimo cada rechazo cierra sus sesiones."""
    u = db.usuarios.find_one_and_update({"_id": quien.uid}, [{"$set": {"volumen": {"$cond": [
        {"$eq": [{"$ifNull": ["$volumen.dia", None]}, {"$literal": dia}]},
        {"dia": {"$literal": dia}, "rechazos": {"$add": [{"$ifNull": ["$volumen.rechazos", 0]}, 1]}},
        {"dia": {"$literal": dia}, "rechazos": 1}]}}}], projection={"volumen": 1}, return_document=ReturnDocument.AFTER)
    n = ((u or {}).get("volumen") or {}).get("rechazos", 0)
    if n == 1:
        bd.auditar(db, quien, "alerta_volumen", "usuario", quien.uid, {"tope": tope})
    if n >= RECHAZOS_CIERRE:
        cerradas = cerrar_sesiones(db, quien.uid)
        if n == RECHAZOS_CIERRE:
            bd.auditar(db, "sistema", "cerrar_sesiones", "usuario", quien.uid, {"motivo": "volumen", "cerradas": cerradas})


# ───────────────────────────── Idempotencia ─────────────────────────────

CLAVE_IDEMPOTENCIA = re.compile(r"[A-Za-z0-9_.:-]{8,100}")
EN_CURSO_S = 120  # una petición «en curso» más vieja que esto se da por perdida (el proceso se cayó a mitad)
EN_PROCESO = {"mensaje": "Esta acción ya se está guardando. Espere un momento.", "codigo": "en_proceso"}


def _ruta_de(request: Request) -> str:
    return f"{request.method} {ruta_interna(request.scope)}"


def idempotencia_previa(db: Database, quien: Quien, request: Request) -> Response | None:
    """Con `Idempotency-Key`: la respuesta guardada de esa clave, o 409 `{codigo: "en_proceso"}` mientras la primera
    sigue en curso. Sin la cabecera (o con una clave nueva) devuelve None y la petición sigue: la ruta llama después a
    `idempotencia_guardar` con su respuesta."""
    clave = request.headers.get("idempotency-key")
    if not clave or quien is None or quien.uid is None:
        return None
    if not CLAVE_IDEMPOTENCIA.fullmatch(clave):
        raise HTTPException(422, "La cabecera Idempotency-Key no es válida")
    _id, ruta = f"{quien.uid}:{clave}", _ruta_de(request)
    for _ in range(3):
        ahora = datetime.now(timezone.utc)
        try:
            db.idempotencia.insert_one({"_id": _id, "ruta": ruta, "estado": "en_curso", "codigo": None,
                                        "respuesta": None, "persona_id": None, "ts": ahora})
            request.state.idempotencia = _id
            return None
        except DuplicateKeyError:
            doc = db.idempotencia.find_one({"_id": _id})
        if doc is None:  # se borró entre medias: se vuelve a intentar
            continue
        if doc.get("ruta") != ruta:
            raise HTTPException(422, "Esa clave de idempotencia ya se usó en otra acción")
        if doc.get("estado") == "hecho":
            return Response(doc.get("respuesta") or "null", status_code=doc.get("codigo") or 200,
                            media_type="application/json", headers={"Idempotency-Replayed": "true"})
        ts = doc.get("ts")
        if ts is not None and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts is not None and ahora - ts > timedelta(seconds=EN_CURSO_S):
            tomada = db.idempotencia.find_one_and_update({"_id": _id, "estado": "en_curso", "ts": doc["ts"]},
                                                         {"$set": {"ts": ahora}})
            if tomada is not None:
                request.state.idempotencia = _id
                return None
            continue
        raise HTTPException(409, dict(EN_PROCESO))
    raise HTTPException(409, dict(EN_PROCESO))


def idempotencia_guardar(db: Database, quien: Quien, request: Request, codigo: int, cuerpo: Any,
                         persona_id: int | None = None) -> None:
    """Guarda la respuesta de una petición con `Idempotency-Key` (la que tomó `idempotencia_previa`). Se guarda como
    texto JSON, igual a lo que recibe el cliente; caduca a las 24 h y se borra al suprimir a la persona."""
    _id = getattr(request.state, "idempotencia", None)
    if not _id:
        return
    texto = json.dumps(jsonable_encoder(cuerpo), ensure_ascii=False, separators=(",", ":"))
    db.idempotencia.update_one({"_id": _id, "estado": "en_curso"},
                               {"$set": {"estado": "hecho", "codigo": int(codigo), "respuesta": texto,
                                         "persona_id": persona_id, "ts": datetime.now(timezone.utc)}})
    request.state.idempotencia = None


def _soltar_idempotencia(db: Database, request: Request) -> None:
    """Al terminar la petición: si la ruta tomó una clave y no guardó la respuesta (falló, o respondió sin guardar), la
    clave se libera para que el reintento se procese de nuevo."""
    _id = getattr(request.state, "idempotencia", None)
    if _id:
        request.state.idempotencia = None
        db.idempotencia.delete_one({"_id": _id, "estado": "en_curso"})


# ───────────────────────────── Compromiso de confidencialidad ─────────────────────────────

# Texto versionado (3.5). Lo valida un abogado antes de desplegar (riesgo R-E); una versión nueva va en Ajustes
COMPROMISOS = {
    "2026-11-v1": [
        "Guardaré la confidencialidad de los datos personales que conozca en este panel, también después de terminar "
        "mi relación con el equipo (Ley 1581 de 2012, art. 4, literal h).",
        "Usaré los datos solo para la finalidad informada al titular. No los copiaré, exportaré, fotografiaré ni "
        "compartiré, ni haré capturas de pantalla.",
        "No contactaré a quien no autorizó el tratamiento de sus datos ni a quien pidió no ser contactado.",
        "Sé que las fichas que consulto, los cambios que hago y mis indicadores de trabajo quedan registrados.",
    ],
}


def texto_compromiso(version: str | None) -> list[str]:
    """Los puntos del compromiso de esa versión (o los de la más reciente, si la versión no tiene texto propio)."""
    return list(COMPROMISOS.get(version or "") or COMPROMISOS[max(COMPROMISOS)])
