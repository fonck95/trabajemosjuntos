"""Configuración desde variables de entorno (y un archivo .env opcional, sin dependencias).

* `ADMIN` (usuario) y `password` (clave) del administrador, tal como están en Railway. También `admin` / `PASSWORD`.
* `MONGODB_URI`: conexión a MongoDB (la del plugin de Railway o de Atlas). `MONGODB_DB` opcional; si la URI no trae
  base de datos se usa `panel_yondo`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _cargar_env(ruta: Path) -> None:
    """Lee KEY=valor de un .env sin pisar variables que ya existan en el entorno."""
    if not ruta.is_file():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        clave, valor = clave.strip(), valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "'\"":
            valor = valor[1:-1]
        os.environ.setdefault(clave, valor)


def _primera(*nombres: str) -> str:
    for n in nombres:
        v = os.environ.get(n)
        if v:
            return v
    return ""


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
    cookie_segura = seguro.lower() in ("1", "true", "si", "sí") if seguro else bool(os.environ.get("RAILWAY_ENVIRONMENT"))
    return Config(
        usuario=_primera("ADMIN", "admin"),
        clave=_primera("password", "PASSWORD"),
        mongodb_uri=_primera("MONGODB_URI", "MONGO_URL", "MONGODB_URL") or "mongodb://127.0.0.1:27017",
        mongodb_db=_primera("MONGODB_DB"),
        horas_sesion=int(_primera("SESSION_HOURS") or 12),
        cookie_segura=cookie_segura,
        max_subida_mb=int(_primera("MAX_UPLOAD_MB") or 25),
    )
