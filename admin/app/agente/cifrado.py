"""Cifrado en reposo de los tokens de la conexión con Mnemo (`mnemo_conexion.py`): AES-GCM con la biblioteca
`cryptography`.

* La clave no está en la base: es `seguridad.llave_mnemo(cfg)`, un HMAC de la derivación lenta de `ADMIN` y `password`
  con una etiqueta propia (nunca la salida de `huella()`, que se guarda en `sesiones`). Una fuga solo de la base (un
  respaldo, la URI) no da acceso al Mnemo del administrador ni a sus créditos. Tampoco escribir en ella: lo cifrado
  lleva también las direcciones a las que se mandan los tokens (y el código y el verificador del pendiente), y
  `mnemo_conexion` usa solo esa copia para mandarlos.
* Cada texto lleva la versión del formato, un nonce aleatorio de 12 bytes y lo cifrado con su etiqueta de 16 bytes, en
  base64 url. Los datos asociados son el `contexto` (`"mnemo_conexion|<emisor>|<client_id>"`): lo cifrado para una
  conexión no se puede pegar en otra.
* `descifrar` da None si el texto no es de esta clave (cambiaron `ADMIN` o `password`), si lo alteraron o si no tiene
  la forma: quien lo llama decide qué hacer (la conexión queda «caida», motivo «clave», y hay que volver a conectar).
"""
from __future__ import annotations

import base64
import binascii
import json
import secrets
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VERSION = b"\x01"
NONCE = 12
ETIQUETA = 16
LARGO_LLAVE = 32  # AES-256
MAX_TEXTO = 64_000  # lo cifrado son dos tokens: unos cientos de caracteres


def _aes(llave: bytes) -> AESGCM:
    if not isinstance(llave, (bytes, bytearray)) or len(llave) != LARGO_LLAVE:
        raise ValueError("La clave de cifrado tiene que tener 32 bytes")
    return AESGCM(bytes(llave))


def cifrar(llave: bytes, datos: dict, contexto: str) -> str:
    """`datos` (un objeto JSON) cifrado con `llave` y atado a `contexto`, como texto base64 url."""
    claro = json.dumps(datos, ensure_ascii=False, separators=(",", ":")).encode()
    nonce = secrets.token_bytes(NONCE)
    cifrado = _aes(llave).encrypt(nonce, claro, contexto.encode())
    return base64.urlsafe_b64encode(VERSION + nonce + cifrado).decode()


def descifrar(llave: bytes, texto: Any, contexto: str) -> dict | None:
    """Lo que guardó `cifrar`, o None si no es de esta clave o de este contexto, si lo alteraron o si no tiene la
    forma (nunca lanza por el texto: viene de la base)."""
    if not isinstance(texto, str) or not texto or len(texto) > MAX_TEXTO:
        return None
    try:
        crudo = base64.urlsafe_b64decode(texto.encode())
    except (ValueError, binascii.Error):
        return None
    if len(crudo) < 1 + NONCE + ETIQUETA or crudo[:1] != VERSION:
        return None
    try:
        claro = _aes(llave).decrypt(crudo[1:1 + NONCE], crudo[1 + NONCE:], contexto.encode())
    except InvalidTag:
        return None
    try:
        datos = json.loads(claro)
    except (ValueError, RecursionError):
        return None
    return datos if isinstance(datos, dict) else None
