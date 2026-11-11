"""Autenticación, sesiones, CSRF, límite de intentos y cabeceras de seguridad.

* El administrador entra con las variables de entorno `ADMIN` y `password` (se comparan en tiempo constante); los
  coordinadores, planilleros y consultores, con su usuario de la colección `usuarios` (ver app/acceso.py).
* La sesión es un token aleatorio en una cookie HttpOnly + SameSite=Strict (Secure en producción); en MongoDB
  solo se guarda su hash SHA-256, y la sesión caduca sola (índice TTL).
* Cada sesión guarda una huella: la del administrador sale de ADMIN y password; la de un usuario, además, de su `_id`
  y su `version`. Si cambian ADMIN o password, ninguna sesión vale; si sube la `version` de un usuario (desactivarlo,
  cambiarle el rol o la clave, «Cerrar sesiones»), se cierran solo las suyas.
* Las sesiones de un usuario duran como mucho `ajustes.sesion.horas_max`, caen tras `inactividad_min` sin uso y no
  pasan de `max_por_usuario` (las más viejas se cierran).
* Toda petición que cambia datos debe traer la cabecera X-CSRF-Token de la sesión.
* Cinco intentos fallidos por IP en 15 minutos bloquean esa IP (como mucho 15 minutos). Un navegador con la marca de
  un ingreso correcto a la cuenta que se intenta solo cuenta sus propios fallos (IP compartida). Con más de 100 fallos
  en total, cada intento espera un retroceso exponencial corto (como mucho 60 s): el ingreso nunca queda bloqueado
  indefinidamente. No hay bloqueo por nombre: nadie puede dejar a otro sin entrar.
* Ninguna ruta /api/* (salvo /api/login y /api/yo) se atiende sin sesión y el cuerpo de la petición tiene tamaño
  máximo: las dos cosas se comprueban antes de leerlo. Un usuario con la clave por cambiar o el compromiso por
  aceptar solo llega a su cuenta, e importar es solo del administrador.
* Si MongoDB se cae o se cuelga, la API responde 503 al instante durante unos segundos sin tocar la base
  (`Cortacircuitos`) y deja una sola línea en el registro, sin traza ni URI.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
import math
import secrets
import time
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from fastapi import HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, DuplicateKeyError
from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware

from . import db as bd
from . import modelo

log = logging.getLogger("panel")
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
# Con la clave temporal sin cambiar o el compromiso sin aceptar, un usuario solo llega a estas rutas (3.5)
RUTAS_DE_CUENTA = {"/api/yo", "/api/yo/clave", "/api/yo/compromiso", "/api/logout"}
ROLES_USUARIO = ("coordinador", "planillero", "consultor")  # los que viven en la colección `usuarios`
# Los que administran (adenda 1): A y el coordinador manejan los datos sin recorte, presupuesto ni límite de frecuencia
ROLES_ADMIN = frozenset({"admin", "coordinador"})
SIN_PERMISO = {"mensaje": "Su rol no permite esta acción", "codigo": "permiso"}
ACTIVIDAD_S = 60  # `ultima_actividad` de una sesión de usuario se escribe como mucho cada minuto
USUARIO_DESCONOCIDO = "desconocido"  # en la auditoría de un ingreso fallido con otro usuario
PAUSA_S = 5  # tras un fallo de conexión con MongoDB, la API responde 503 sin tocar la base durante este tiempo
SIN_BASE = "El panel se está conectando a la base de datos. Intente de nuevo en unos segundos."


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


def reservar_intento(db: Database, ip: str, conocido: bool = False, marca_h: str | None = None,
                     nombre_h: str | None = None):
    """Registra el intento ANTES de comprobar la clave y decide si se atiende.

    Devuelve (id del intento, 0) si se puede comprobar la clave, o (None, segundos de espera) si no. Se cuenta
    después de insertar, incluidos el propio intento y los simultáneos: una ráfaga en paralelo no pasa del límite.
    Los intentos rechazados se borran: no alargan el bloqueo ni cuentan para el límite global.
    `conocido`: el navegador trae la marca de un ingreso correcto anterior a la cuenta que se intenta (ver
    `dispositivo_valido`); no compite por el turno del freno global, así una inundación desde muchas IPs no deja fuera
    al administrador. Con `marca_h` (el hash de esa marca), el límite por IP cuenta solo los fallos hechos con la misma
    marca: en una IP compartida, los fallos ajenos no bloquean a quien ya entró antes desde ese navegador.
    `nombre_h` (HMAC del nombre escrito, exista o no) sirve para la alerta de ingresos y para desbloquear."""
    ahora = datetime.now(timezone.utc)
    desde = ahora - timedelta(seconds=VENTANA_S)
    clave = _clave_ip(ip)
    iid = db.intentos.insert_one({"ip": clave, "ts": ahora, "ok": False, "nombre_h": nombre_h,
                                  "marca_h": marca_h}).inserted_id
    de_ip = {"ip": clave, "ok": False, "ts": {"$gt": desde}}
    if marca_h:
        de_ip["marca_h"] = marca_h
    n = db.intentos.count_documents(de_ip)
    if n > MAX_POR_IP:
        db.intentos.delete_one({"_id": iid})
        # La IP se libera cuando sale de la ventana el fallo que sobra (como mucho 15 minutos)
        x = next(db.intentos.find(de_ip, {"ts": 1}).sort("ts", 1).skip(max(0, n - MAX_POR_IP - 1)).limit(1), None)
        espera = min(x["ts"] + timedelta(seconds=VENTANA_S) - ahora, timedelta(seconds=VENTANA_S)) if x else timedelta(seconds=1)
        return None, _segundos(espera)
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


def resolver_intento(db: Database, iid, ip: str, ok: bool, nombre_h: str | None = None) -> None:
    """El intento reservado queda como fallo; si la clave era correcta, se marca y se limpian los fallos de esa IP con
    el mismo nombre (los errores de tipeo propios, no los intentos contra otras cuentas)."""
    if ok:
        db.intentos.update_one({"_id": iid}, {"$set": {"ok": True}})
        q = {"ip": _clave_ip(ip), "ok": False}
        if nombre_h:
            q["nombre_h"] = nombre_h
        db.intentos.delete_many(q)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@lru_cache(maxsize=8)
def _llave(usuario: str, clave: str) -> bytes:
    # Derivación lenta (una vez por proceso): la huella guardada en la base no sirve para adivinar la clave rápido
    return hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), b"panel-yondo|" + usuario.encode("utf-8"), 600_000)


def huella(cfg) -> str:
    """Huella HMAC de la credencial vigente: si cambian ADMIN o password, cambia y las sesiones viejas no valen."""
    return hmac.new(_llave(cfg.usuario or "", cfg.clave or ""), b"sesion", hashlib.sha256).hexdigest()


def llave_mnemo(cfg) -> bytes:
    """La clave (32 bytes) con que se cifran en la base los tokens de la conexión con Mnemo (`agente/cifrado.py`):
    sale de la credencial del administrador (la derivación lenta de `_llave`) con una etiqueta propia, así no está en
    la base. Nunca es la salida de `huella()`, que se guarda en `sesiones`. Si cambian ADMIN o password, lo cifrado
    deja de descifrar y hay que volver a conectar Mnemo."""
    return hmac.new(_llave(cfg.usuario or "", cfg.clave or ""), b"mnemo|tokens", hashlib.sha256).digest()


def huella_usuario(cfg, u: dict) -> str:
    """Huella de las sesiones de un usuario: cambia con la credencial de .env (se cierran todas) y con la `version`
    del usuario (se cierran solo las suyas)."""
    return hmac.new(_llave(cfg.usuario or "", cfg.clave or ""), f"usuario|{u['_id']}|{u.get('version')}".encode(),
                    hashlib.sha256).hexdigest()


def _firma_dispositivo(cfg, marca: str) -> str:
    return hmac.new(_llave(cfg.usuario or "", cfg.clave or ""), b"dispositivo|" + marca.encode(), hashlib.sha256).hexdigest()


def _firma_usuario(cfg, uid: int, version, marca: str) -> str:
    return hmac.new(_llave(cfg.usuario or "", cfg.clave or ""), f"dispositivo|{uid}|{version}|{marca}".encode(),
                    hashlib.sha256).hexdigest()


def marcar_dispositivo(cfg, response: Response, base: str = "", uid: int = 0, version=None) -> None:
    """Tras un ingreso correcto, el navegador recibe una marca firmada con la credencial vigente (sin datos). La de un
    usuario lleva su uid y su versión: solo vale para su cuenta."""
    marca = secrets.token_urlsafe(18)
    valor = f"u{uid}.{marca}.{_firma_usuario(cfg, uid, version, marca)}" if uid else f"{marca}.{_firma_dispositivo(cfg, marca)}"
    response.set_cookie(COOKIE_DISPOSITIVO, valor, max_age=DIAS_DISPOSITIVO * 86400,
                        httponly=True, secure=cfg.cookie_segura, samesite="strict", path=f"{base}/api/login")


def dispositivo_valido(cfg, request: Request, cuenta: int | None, version=None) -> str | None:
    """La marca del navegador si es de un ingreso correcto a `cuenta` (0: el administrador; un uid: ese usuario, con
    su `version` vigente); si no, None. Una marca solo vale para su cuenta, y deja de valer si cambian ADMIN o
    password (o la versión del usuario)."""
    valor = request.cookies.get(COOKIE_DISPOSITIVO) or ""
    if cuenta is None or not valor or len(valor) > 200 or not cfg.usuario or not cfg.clave:
        return None
    partes = valor.split(".")
    if cuenta == 0 and len(partes) == 2:
        marca, firma = partes
        esperada = _firma_dispositivo(cfg, marca)
    elif cuenta and len(partes) == 3 and partes[0] == f"u{cuenta}":
        marca, firma = partes[1:]
        esperada = _firma_usuario(cfg, cuenta, version, marca)
    else:
        return None
    return valor if marca and hmac.compare_digest(firma.encode(), esperada.encode()) else None


def dispositivo_conocido(cfg, request: Request) -> bool:
    """¿El navegador ya ingresó antes como administrador con la credencial vigente?"""
    return dispositivo_valido(cfg, request, 0) is not None


def _ruta_cookie(request: Request) -> str:
    """La cookie de sesión viaja solo a las rutas del panel: «/panel/» dentro del sitio público (no a /atlas ni a
    /js/…), «/» con el panel solo."""
    return f"{base_de(request)}/"


def _borrar_cookie_vieja(request: Request, response: Response) -> None:
    # Antes la cookie iba con Path=/ también dentro del sitio. El navegador manda las dos y Starlette se queda con la
    # última, la vieja: si su sesión ya no vale, el ingreso volvería a pedir la clave hasta que caducara.
    if base_de(request):
        response.delete_cookie(COOKIE, path="/", httponly=True, samesite="strict",
                               secure=request.app.state.cfg.cookie_segura)


def crear_sesion(db: Database, cfg, response: Response, usuario: str, request: Request, uid: int = 0,
                 rol: str = "admin", version=None, horas: float | None = None) -> str:
    """Abre una sesión y deja la cookie. La de un usuario (`uid` > 0) dura como mucho `horas` y, al abrirla, se cierran
    sus sesiones más viejas por encima de `ajustes.sesion.max_por_usuario`."""
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    ahora = datetime.now(timezone.utc)
    if uid:
        firma = huella_usuario(cfg, {"_id": uid, "version": version})
        duracion = min(cfg.horas_sesion, horas or cfg.horas_sesion)
    else:
        firma, duracion = huella(cfg), cfg.horas_sesion
    db.sesiones.insert_one({"_id": _hash(token), "usuario": usuario, "uid": uid or 0, "rol": rol, "version": version,
                            "csrf": csrf, "huella": firma, "creada": ahora, "expira": ahora + timedelta(hours=duracion),
                            "ultima_actividad": ahora, "ip": ip_de(request),
                            "agente": (request.headers.get("user-agent") or "")[:200]})
    if uid:
        maximo = max(1, int(modelo.leer_ajustes(db)["sesion"].get("max_por_usuario") or 2))
        viejas = [x["_id"] for x in db.sesiones.find({"uid": uid}, {"_id": 1}).sort([("creada", -1), ("_id", 1)]).skip(maximo)]
        if viejas:
            db.sesiones.delete_many({"_id": {"$in": viejas}})
    _borrar_cookie_vieja(request, response)
    response.set_cookie(COOKIE, token, max_age=cfg.horas_sesion * 3600, httponly=True, secure=cfg.cookie_segura,
                        samesite="strict", path=_ruta_cookie(request))
    return csrf


def migrar_cookie(request: Request, response: Response, s: dict) -> None:
    """Con el panel dentro del sitio, pasa una sesión válida a la ruta nueva: borra la cookie con Path=/ (de antes de
    acotarla al panel) y vuelve a emitir el mismo token con la ruta y los atributos de `crear_sesion`. La duración es
    la que le queda a la sesión, así que no la alarga. `s` es la sesión que `sesion_actual` ya validó."""
    token = request.cookies.get(COOKIE)
    if not (token and base_de(request)):
        return
    cfg = request.app.state.cfg
    expira = s.get("expira")
    if isinstance(expira, datetime) and expira.tzinfo is None:
        expira = expira.replace(tzinfo=timezone.utc)
    resta = cfg.horas_sesion * 3600
    if isinstance(expira, datetime):
        resta = min(resta, int((expira - datetime.now(timezone.utc)).total_seconds()))
    if resta <= 0:
        return
    _borrar_cookie_vieja(request, response)
    response.set_cookie(COOKIE, token, max_age=resta, httponly=True, secure=cfg.cookie_segura,
                        samesite="strict", path=_ruta_cookie(request))


def cerrar_sesion(db: Database, request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        db.sesiones.delete_one({"_id": _hash(token)})
    _borrar_cookie_vieja(request, response)
    response.delete_cookie(COOKIE, path=_ruta_cookie(request), httponly=True, samesite="strict",
                           secure=request.app.state.cfg.cookie_segura)


def sesion_actual(db: Database, request: Request) -> dict | None:
    """La sesión de la cookie, si vale. La de un usuario exige que siga activo, con un rol válido (con otro valor la
    sesión no vale: falla cerrada), la huella de su versión vigente y uso reciente. Lleva en `_usuario` y `_ajustes`
    el usuario y los ajustes leídos (no se guardan en la base)."""
    token = request.cookies.get(COOKIE)
    if not token or len(token) > 100:
        return None
    s = db.sesiones.find_one({"_id": _hash(token)})
    ahora = datetime.now(timezone.utc)
    if s is None or s["expira"] < ahora:
        return None
    cfg = request.app.state.cfg
    if s.get("uid") in (None, 0):
        # Solo valen las sesiones de la credencial vigente
        return s if hmac.compare_digest(str(s.get("huella") or ""), huella(cfg)) else None
    u = db.usuarios.find_one({"_id": s["uid"], "activo": True}, {"clave": 0})
    if u is None or u.get("rol") not in ROLES_USUARIO:
        return None
    if not hmac.compare_digest(str(s.get("huella") or ""), huella_usuario(cfg, u)):
        return None
    aj = modelo.leer_ajustes(db)
    ultima = s.get("ultima_actividad") or s.get("creada")
    if ultima is not None and ahora - ultima > timedelta(minutes=float(aj["sesion"].get("inactividad_min") or 60)):
        db.sesiones.delete_one({"_id": s["_id"]})
        return None
    if ultima is None or ahora - ultima > timedelta(seconds=ACTIVIDAD_S):
        db.sesiones.update_one({"_id": s["_id"]}, {"$set": {"ultima_actividad": ahora}})
    s["_usuario"], s["_ajustes"] = u, aj
    return s


def rechazo_de_cuenta(s: dict, ruta: str, db: Database | None = None) -> dict | None:
    """Por qué la sesión `s` no puede usar `ruta` (3.5), o None. Aplica a los usuarios de la base (coordinador,
    planillero y consultor): importar es del administrador y del coordinador, y con la clave temporal sin cambiar o el
    compromiso vigente sin aceptar solo se llega a `RUTAS_DE_CUENTA`. Sin `_usuario` en la sesión, lo lee de `db`; si
    no hay cómo saber el rol, importar se rechaza (falla cerrada)."""
    if s.get("uid") in (None, 0):
        return None
    u = s.get("_usuario")
    if u is None and db is not None and ruta not in RUTAS_DE_CUENTA:
        u = db.usuarios.find_one({"_id": s["uid"]}, {"rol": 1, "debe_cambiar_clave": 1, "compromiso_version": 1})
    u = u or {}
    if ruta == "/api/importar" and u.get("rol") not in ROLES_ADMIN:
        return dict(SIN_PERMISO)
    if ruta in RUTAS_DE_CUENTA:
        return None
    if u.get("debe_cambiar_clave"):
        return {"mensaje": "Cambie su clave temporal para continuar", "codigo": "cambiar_clave"}
    aj = s.get("_ajustes") or (modelo.leer_ajustes(db) if db is not None else {})
    if u.get("compromiso_version") != aj.get("compromiso_version"):
        return {"mensaje": "Acepte el compromiso de confidencialidad para continuar", "codigo": "compromiso"}
    return None


def limpiar_al_iniciar(db: Database, cfg) -> None:
    """Al arrancar: cierra las sesiones de otra credencial (y las de usuarios inactivos o con otra versión), borra lo
    que se escribió como usuario en los ingresos fallidos auditados antes de este cambio (podía ser la clave), pone
    `uid` 0 a las entradas viejas del administrador y desactiva al usuario que tenga su nombre."""
    db.sesiones.delete_many({"uid": {"$in": [None, 0]}, "huella": {"$ne": huella(cfg)}})
    usuarios = list(db.usuarios.find({}, {"usuario": 1, "version": 1, "activo": 1}))
    for u in usuarios:
        q = {"uid": u["_id"], "huella": {"$ne": huella_usuario(cfg, u)}} if u.get("activo") else {"uid": u["_id"]}
        db.sesiones.delete_many(q)
    db.sesiones.delete_many({"uid": {"$nin": [None, 0, *(u["_id"] for u in usuarios)]}})
    nombres = [u["usuario"] for u in usuarios if u.get("usuario")]
    db.auditoria.update_many({"accion": "ingreso_fallido",
                              "usuario": {"$nin": [cfg.usuario, USUARIO_DESCONOCIDO, *nombres]}},
                             {"$set": {"usuario": USUARIO_DESCONOCIDO}})
    if not cfg.usuario:
        return
    db.auditoria.update_many({"uid": {"$exists": False}, "usuario": cfg.usuario}, {"$set": {"uid": 0, "rol": "admin"}})
    choque = db.usuarios.find_one({"usuario": cfg.usuario.strip().lower(), "activo": True}, {"usuario": 1})
    if choque:
        log.error("El usuario %s tiene el nombre del administrador: queda desactivado", choque["_id"])
        db.usuarios.update_one({"_id": choque["_id"]}, {"$set": {"activo": False, "desactivado_en": bd.ahora(),
                                                                 "actualizado_en": bd.ahora()}, "$inc": {"version": 1}})
        db.sesiones.delete_many({"uid": choque["_id"]})
        bd.auditar(db, "sistema", "conflicto_admin", "usuario", choque["_id"], {"usuario": choque["usuario"]})


def obtener_db(request: Request) -> Database:
    return request.app.state.db


def __getattr__(nombre: str):
    """`requiere_admin` y `Admin` vienen de app/acceso.py: `requiere("admin")` (denegar por defecto) y `Quien`. Se
    cargan al pedirlos, porque acceso importa este módulo."""
    if nombre in ("requiere_admin", "Admin"):
        from . import acceso
        globals().update(requiere_admin=acceso.requiere_admin, Admin=acceso.Quien)
        return globals()[nombre]
    raise AttributeError(f"module {__name__!r} has no attribute {nombre!r}")


class CuerpoDemasiadoGrande(HTTPException):
    def __init__(self):
        super().__init__(413, "La petición es demasiado grande")


def ruta_interna(scope) -> str:
    """Ruta dentro del panel, sin el prefijo con que esté montado (p. ej. «/panel/api/yo» → «/api/yo»).

    Starlette conserva en scope["path"] la ruta completa y pone el prefijo en root_path: los chequeos de ruta deben
    mirar la ruta interna, o bajo /panel dejarían de aplicarse."""
    ruta, raiz = scope["path"], scope.get("root_path", "")
    if raiz and ruta.startswith(raiz):
        ruta = ruta[len(raiz):] or "/"
    return ruta


def base_de(request: Request) -> str:
    """Prefijo con que está montado el panel («» si va solo, «/panel» dentro del sitio)."""
    return (request.scope.get("root_path") or "").rstrip("/")


def sin_base(ruta: str) -> JSONResponse:
    """503 mientras MongoDB no responde: el navegador reintenta solo y el sitio no espera."""
    cuerpo = {"ok": False, "detail": SIN_BASE} if ruta == "/salud" else {"detail": SIN_BASE}
    return JSONResponse(cuerpo, 503, headers={"Retry-After": str(PAUSA_S)})


class Cortacircuitos:
    """Si MongoDB se cae o se cuelga, que el panel no lo espere en cada petición.

    Cada petición que espera a MongoDB retiene un hilo hasta que vence el tiempo de espera de pymongo, y esos hilos
    los comparte el sitio público. Tras un fallo de conexión (`ConnectionFailure`: AutoReconnect, NetworkTimeout,
    ServerSelectionTimeoutError…) la API responde 503 durante `pausa_s` sin tocar la base. Pasada la pausa, una sola
    petición comprueba con un ping si MongoDB volvió (las demás siguen en 503): si responde, todo sigue normal; si
    no, empieza otra pausa. Vive en app.state: sirve igual con el panel solo y dentro del sitio. Solo se usa desde
    el bucle de eventos, así que no necesita candados."""

    def __init__(self, pausa_s: float = PAUSA_S):
        self.pausa_s = pausa_s
        self.caido = False      # hubo un fallo y todavía no se comprobó que MongoDB volvió
        self.hasta = 0.0        # fin de la pausa (time.monotonic)
        self.probando = False   # una petición está comprobando si MongoDB volvió

    def fallo(self, exc: Exception) -> None:
        # Una línea por caída, sin traza ni URI (el mensaje de pymongo nombra el servidor)
        if not self.caido:
            log.warning("MongoDB no responde (%s): la API responde 503 y vuelve a intentar cada %s s",
                        type(exc).__name__, self.pausa_s)
        self.caido = True
        self.hasta = time.monotonic() + self.pausa_s

    async def permitir(self, db: Database) -> bool:
        """¿Puede esta petición tocar MongoDB?"""
        if not self.caido:
            return True
        if self.probando or time.monotonic() < self.hasta:
            return False
        self.probando = True
        try:
            await run_in_threadpool(db.command, "ping")
        except ConnectionFailure as e:
            self.fallo(e)
            return False
        except Exception:  # MongoDB respondió, aunque con otro error (permisos…): lo verá la propia petición
            pass
        finally:
            self.probando = False
        self.caido = False
        log.info("MongoDB volvió a responder")
        return True


class GuardiaApi:
    """Middleware ASGI que actúa antes de que nadie lea el cuerpo de la petición.

    FastAPI lee el cuerpo entero (y guarda en disco cada archivo subido) antes de resolver `requiere_admin`: sin
    esto, un anónimo podía llenar la memoria con un JSON enorme o el disco con una subida a /api/importar.
    * Limita el tamaño del cuerpo, por su Content-Length y contando lo que llega por partes.
    * Mientras MongoDB no está listo o el `Cortacircuitos` está en pausa, /api/* y /salud responden 503 al instante.
    * Rechaza sin sesión válida toda ruta /api/*, salvo /api/login y /api/yo. El CSRF, el rol y los permisos siguen
      en `acceso.requiere`, que recibe la sesión en scope["state"].
    * A un usuario de la base con la clave temporal o el compromiso pendientes solo lo deja llegar a su cuenta, y a
      planilleros y consultores les rechaza /api/importar sin leer la subida.
    Va por fuera del manejador de excepciones de FastAPI: los fallos de conexión de su propia consulta se atrapan
    aquí."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        app, ruta = scope["app"], ruta_interna(scope)
        # Importar acepta hasta 6 Excel de max_subida_mb cada uno; el resto es JSON pequeño
        limite = (app.state.cfg.max_subida_mb * 6 + 1) * MB if ruta == "/api/importar" else LIMITE_JSON
        largo = Headers(scope=scope).get("content-length", "")
        if largo.isdigit() and int(largo) > limite:
            return await JSONResponse({"detail": "La petición es demasiado grande"}, 413)(scope, receive, send)
        if ruta.startswith("/api/") or ruta == "/salud":
            # Dentro del sitio, el panel arranca aunque MongoDB todavía no responda: la API espera hasta que conecte.
            # Tras un fallo de conexión, espera la pausa del cortacircuitos
            if not getattr(app.state, "listo", True) or not await app.state.cortacircuitos.permitir(app.state.db):
                return await sin_base(ruta)(scope, receive, send)
        if ruta.startswith("/api/") and ruta not in RUTAS_SIN_SESION:
            try:
                s = await run_in_threadpool(sesion_actual, app.state.db, Request(scope))
            except ConnectionFailure as e:
                app.state.cortacircuitos.fallo(e)
                return await sin_base(ruta)(scope, receive, send)
            if s is None:
                return await JSONResponse({"detail": "Inicie sesión"}, 401)(scope, receive, send)
            # Usuarios (3.3 y 3.5): la sesión queda para `requiere`; un usuario con la clave por cambiar o el
            # compromiso por aceptar solo llega a su cuenta, e importar se le rechaza antes de leer la subida
            scope.setdefault("state", {})["sesion"] = s
            rechazo = rechazo_de_cuenta(s, ruta)
            if rechazo is not None:
                return await JSONResponse({"detail": rechazo}, 403)(scope, receive, send)
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


# `frame-src 'self'`: la vista Presentación muestra la propuesta del sitio público en un iframe (en el servicio único,
# /propuesta del mismo origen; sin esta directiva regiría `child-src blob:` y el iframe quedaría bloqueado). El panel
# enmarca, pero nadie lo enmarca a él: `frame-ancestors 'none'` y X-Frame-Options siguen
_DIRECTIVAS_CSP = [
    "default-src 'self'",
    "script-src 'self'",
    "worker-src 'self' blob:",
    "child-src blob:",
    "frame-src 'self'",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data: blob: https://tiles.openfreemap.org https://server.arcgisonline.com https://s3.amazonaws.com",
    "connect-src 'self' https://tiles.openfreemap.org https://server.arcgisonline.com https://s3.amazonaws.com",
    "frame-ancestors 'none'",
    "base-uri 'none'",
    "form-action 'self'",
    "object-src 'none'",
]
CSP = "; ".join(_DIRECTIVAS_CSP)


@lru_cache(maxsize=4)
def politica_panel(origen_sitio: str = "") -> str:
    """La CSP del panel: `CSP` y, con el panel desplegado aparte y `SITIO_URL` configurada, también el origen del sitio
    en `frame-src` (de ahí viene la presentación). El origen ya viene validado (`config._url_sitio`)."""
    if not origen_sitio:
        return CSP
    return "; ".join(f"frame-src 'self' {origen_sitio}" if d == "frame-src 'self'" else d for d in _DIRECTIVAS_CSP)


class CabecerasSeguras(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # La ruta antes de seguir: el montaje de /static/ cambia el root_path del mismo scope y, leída después,
        # «/static/js/ui.js» quedaría como «/js/ui.js»
        ruta = ruta_interna(request.scope)
        resp = await call_next(request)
        h = resp.headers
        h["Content-Security-Policy"] = politica_panel(getattr(request.app.state.cfg, "origen_sitio", ""))
        h["X-Content-Type-Options"] = "nosniff"
        h["X-Frame-Options"] = "DENY"
        h["Referrer-Policy"] = "no-referrer"
        h["X-Robots-Tag"] = "noindex, nofollow"
        h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(self)"
        h["Cross-Origin-Opener-Policy"] = "same-origin"
        if request.app.state.cfg.cookie_segura:
            h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if ruta.startswith("/api/"):
            h["Cache-Control"] = "no-store"
        elif ruta.startswith("/static/"):
            # Los módulos se cargan por separado (cada vista al abrirla). Sin Cache-Control el navegador reusa sin
            # preguntar los que tiene guardados, y tras un despliegue junta un ui.js viejo con un personas.js nuevo:
            # «does not provide an export named …». Con «no-cache» revalida cada uno con su ETag (304 si no cambió).
            h["Cache-Control"] = "no-cache"
        return resp
