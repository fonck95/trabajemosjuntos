"""Configuración desde variables de entorno (y un archivo .env opcional, sin dependencias).

* `ADMIN` (usuario) y `password` (clave) del administrador, tal como están en Railway. También `admin` / `PASSWORD`.
* `MONGODB_URI`: conexión a MongoDB (la del plugin de Railway o de Atlas). `MONGODB_DB` opcional; si la URI no trae
  base de datos se usa `panel_yondo`. En Railway es obligatoria; en local se usa un MongoDB en 127.0.0.1.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
MONGO_LOCAL = "mongodb://127.0.0.1:27017"
log = logging.getLogger("panel")


def _cargar_env(ruta: Path) -> None:
    """Lee KEY=valor de un .env sin pisar variables que ya existan en el entorno.

    Un valor sin comillas termina antes de un comentario en línea (` # ...`, con un espacio antes); un «#» pegado o
    al inicio es parte del valor (claves como `#abc`). Entre comillas se toma tal cual."""
    if not ruta.is_file():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, crudo = linea.partition("=")
        clave, valor = clave.strip(), crudo.strip()
        if valor[:1] in ("'", '"') and valor.find(valor[0], 1) > 0:
            valor = valor[1:valor.find(valor[0], 1)]
        else:
            # « # comentario» tras un espacio (o tras «= ») se descarta; un «#» pegado al «=» es parte del valor
            valor = "" if valor.startswith("#") and crudo[:1].isspace() else re.sub(r"\s+#.*$", "", valor)
        os.environ.setdefault(clave, valor)


def _primera(*nombres: str) -> str:
    for n in nombres:
        v = os.environ.get(n)
        if v:
            return v
    return ""


def _entero(nombre: str, defecto: int) -> int:
    v = _primera(nombre)
    try:
        return int(v) if v else defecto
    except ValueError:
        raise RuntimeError(f"La variable {nombre} debe ser un número entero (vale {v!r})") from None


def sin_credenciales(texto: str) -> str:
    """Quita usuario y clave de una URI (o de un mensaje de error que la cite) antes de escribirla en el registro.

    Una URI se corta por su estructura y no con una expresión: pymongo acepta claves sin escapar con espacios o
    tabuladores, y con la expresión salían enteras en el registro. La autoridad va de «://» a la primera «/» o «?» y la
    credencial, hasta su última «@» (como la separa pymongo). En un mensaje, lo mismo tras cada «//» y, aparte,
    cualquier «usuario:clave@» suelto."""
    esquema, sep, resto = texto.partition("://")
    if sep and re.fullmatch(r"[A-Za-z][A-Za-z0-9+.-]*", esquema):
        fin = min((i for i in (resto.find("/"), resto.find("?")) if i >= 0), default=len(resto))  # como pymongo
        return f"{esquema}://{resto[:fin].rpartition('@')[2]}{resto[fin:]}"
    return re.sub(r"[^\s/@]*:[^\s/@]*@", "", re.sub(r"//[^/]*@", "//", texto))


def en_railway() -> bool:
    return any(os.environ.get(n) for n in ("RAILWAY_ENVIRONMENT", "RAILWAY_ENVIRONMENT_NAME", "RAILWAY_ENVIRONMENT_ID"))


@dataclass(frozen=True)
class Config:
    usuario: str
    clave: str
    mongodb_uri: str
    mongodb_db: str
    horas_sesion: int
    cookie_segura: bool
    max_subida_mb: int


def cargar() -> Config:
    _cargar_env(RAIZ / ".env")
    _cargar_env(RAIZ.parent / ".env")
    # En Railway (o detrás de HTTPS) la cookie viaja solo cifrada; en local se permite http://localhost
    seguro = _primera("COOKIE_SECURE")
    cookie_segura = seguro.lower() in ("1", "true", "si", "sí") if seguro else en_railway()
    uri = _primera("MONGODB_URI", "MONGO_URL", "MONGODB_URL")
    if not uri:
        if en_railway():
            # Sin esto se intentaba 127.0.0.1 y el despliegue caía con un error que no nombraba la variable
            msg = ("Falta la variable MONGODB_URI en el servicio del panel (en Railway: MONGODB_URI = "
                   "${{MongoDB.MONGO_URL}}, o la URI de Atlas)")
            log.error(msg)
            raise RuntimeError(msg)
        log.warning("MONGODB_URI no está definida: se usa el MongoDB local %s", MONGO_LOCAL)
        uri = MONGO_LOCAL
    return Config(
        usuario=_primera("ADMIN", "admin"),
        clave=_primera("password", "PASSWORD"),
        mongodb_uri=uri,
        mongodb_db=_primera("MONGODB_DB"),
        horas_sesion=_entero("SESSION_HOURS", 12),
        cookie_segura=cookie_segura,
        max_subida_mb=_entero("MAX_UPLOAD_MB", 25),
    )
