"""La bandeja de planillas físicas por foto (docs/agente.md, «Planillas físicas por foto»): de la foto de una planilla
de campo en papel a la importación, con la persona que la revisa en el medio. También de cualquier otra foto que se
adjunte en el chat: el panel la describe para que el asistente pueda hablar de ella.

Flujo. El administrador o un coordinador (con su rol en `agente_planillas.roles`; nunca planilleros ni consultores,
que no tienen `importar`) sube la foto desde el chat o desde Importar y exportar (`POST /api/planillas/fotos`,
`app/api/planillas.py`), si el compromiso de confidencialidad vigente lo permite (`exigir_compromiso`; la versión
2026-11-v2 deja fotografiar planillas físicas solo para subirlas por el panel). La foto se valida y se limpia
(`validar_imagen`), se guarda cifrada y se lee de fondo (`leer_foto`, con `agente/lector_planillas.py`): una llamada
aparte al modelo que la describe y, si es una hoja que lista personas (la planilla de campo, una lista de asistencia u
otra), transcribe sus filas. Lo leído (la descripción, `datos_personales`, el `aviso` y las filas) queda cifrado en la
misma planilla, «leida» aunque no tenga ninguna fila. A o K lo revisan (la grilla con la foto al lado, celdas
corregibles), lo cotejan con la base (`simular`: la vista previa fiel del importador, sin escribir) y lo cargan
(`cargar`: el importador real, como una planilla de campo). Al cargar todo se borra la foto (queda su SHA-256 en la
importación) y de la lectura queda solo lo no personal (número de fila, estado, ficha). Una foto leída sin filas (una
foto cualquiera, o una hoja que no se pudo leer: `aviso` «sin_filas») no tiene nada que cotejar ni cargar (`simular` y
`cargar` responden 422 `sin_filas`): se puede volver a leer o borrar, y vence como todo a las `retencion_horas`. No
cuenta en el tope de `SIN_CARGAR_MAX` (no espera una carga).

Privacidad (Ley 1581):
* Al reposo, la foto y las filas van cifradas (AES-GCM, `agente/cifrado.py`, variante para bytes) con una llave que
  sale de la credencial del administrador con una etiqueta propia (`llave`): un respaldo de la base no las abre. Todo
  vence a las `agente_planillas.retencion_horas` (índice TTL en `expira`).
* La foto pierde sus metadatos antes de guardarse: sin EXIF ni GPS (JPEG sin segmentos APPn ni COM; PNG solo con una
  lista cerrada de fragmentos) y cortada en su fin (EOI o IEND): nada escondido después de la imagen.
* Una fila «No autoriza», o de alguien que ya está en «no» por su cédula exacta, guarda solo número, nombre, cédula y
  barrio (`_reducir`); la de alguien que pidió la supresión (por sus huellas, como el importador) se vacía y queda «no
  se carga», sin decir por qué. Si la supresión llega después, `db.suprimir` borra la foto y marca sus filas
  (`filas_suprimidas`), que no vuelven a salir.
* Las autorizaciones de una foto quedan SIEMPRE «declaradas en planilla» (`importar.solo_declaradas`): no habilitan el
  contacto hasta que A o K las confirme con el papel en Importar y exportar. Una autorización «sí» dudosa o ilegible
  cuenta como sin marcar; una «no» dudosa se trata como «no» (lo que protege a quien quizá no autorizó).
* Solo A y K usan la bandeja: ven todas las planillas, con los valores completos y la descripción entera (`detalle`);
  el modelo de una conversación las recibe enmascaradas (`fila_enmascarada` y, la descripción,
  `minimizar.enmascarar_descripcion`). El planillero que llenó el papel queda como «capturado por» de lo cargado.
* La descripción puede nombrar a alguien: va cifrada como las filas, se borra con la foto al cargar la hoja entera y
  deja de mostrarse en cuanto una supresión marca filas de esa planilla (`lectura_de`). La bandeja, en claro, solo
  dice si la hay (`con_descripcion`).

Concurrencia: las lecturas de fondo tienen un cupo por proceso (`A_LA_VEZ`: 1 con Mnemo, que comparte sus cuatro
llamadas con el chat y el dictado; 2 con Anthropic) y esperan su turno en cola; sobreviven a que el navegador se vaya.
Mientras esperan o leen, renuevan `latido`: una planilla «leyendo» sin latido hace más de `VIVA_S` (el proceso se
reinició, por ejemplo) se da por fallida al consultarla y se puede volver a leer."""
from __future__ import annotations

import asyncio
import copy
import hashlib
import hmac
import json
import logging
import re
import secrets
import threading
import time
import zlib
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, AsyncIterator, Iterable

from bson import Binary
from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from pymongo import ReturnDocument
from pymongo.database import Database
from starlette.requests import ClientDisconnect

from . import acceso, modelo
from . import db as bd
from .agente import cifrado
from .agente import lector_planillas as lector
from .pipeline import importar as imp
from .pipeline import lectores
from .pipeline import texto as tx

log = logging.getLogger("panel")

# ───────────────────────────── Topes ─────────────────────────────

TIPOS = ("image/jpeg", "image/png")
MAX_BYTES = 1_500_000            # la foto que sube el navegador (JPEG 0,8, reducida): sobra para una hoja
LADO_MIN, LADO_MAX = 200, 2600   # el lado mayor (Claude lee hasta 2576 px de forma nativa)
LADO_MENOR_MIN = 100
POR_HORA, POR_DIA = 40, 150      # subidas por persona (en `planillas_subidas`, que no se reinicia al borrar fotos)
SIN_CARGAR_MAX = 30              # fotos de una persona todavía sin cargar (leyendo, leídas o fallidas)
LECTURAS_MAX = 2                 # veces que una foto va al modelo (la primera y una relectura)
VIVA_S = 300                     # una lectura «leyendo» sin latido en este tiempo se da por fallida
LATIDO_S = 60.0
ESPERA_CUPO_S = 0.5
A_LA_VEZ = {"mnemo": 1, "anthropic": 2}
PLAZO_SUBIDA_S, SUBIDA_CALLADA_S = 90.0, 20.0
NOTA_MAX, FOLIO_MAX = 300, 120
CARGANDO_S = 20 * 60             # una carga que no soltó la planilla en este tiempo se da por caída
BANDEJA_MAX = 100
ARCHIVO = "Foto de planilla física"
ETIQUETA_LLAVE = b"planillas|fotos"
# Lo que el widget del chat recibe en `/api/agente/estado` (B2 lo arma con `estado_adjuntos`)
MAX_POR_MENSAJE, CALIDAD = 4, 0.8
LADO_DIRECTO, LADO_MNEMO = 2576, 2000

# Estados de una planilla: «leyendo» (en cola o con el modelo), «leida» (con su descripción y sus filas, lista para
# revisar, cotejar y cargar; también tras una carga parcial, y sin ninguna fila si la foto no lista personas),
# «fallida» (se puede volver a leer), «rechazada» (una cédula u otro documento de identidad: sin foto) y «cargada»
# (todas sus filas cargadas o descartadas: sin foto ni datos)
ESTADOS = ("leyendo", "leida", "fallida", "rechazada", "cargada")
SIN_CARGAR = ("leyendo", "leida", "fallida")
FORMATOS = lector.PEDIDOS

# Columna de la lectura → clave normalizada de la plantilla (la que lee `lectores.registro_planilla`)
PLANTILLA = {"cedula": "CEDULA", "cedula_repetida": "REPITALACEDULA", "tipo_documento": "TIPODEDOCUMENTO",
             "nombre": "NOMBRECOMPLETO", "celular": "CELULAR", "otro_telefono": "OTROTELEFONO", "sexo": "SEXO",
             "fecha_nacimiento": "FECHADENACIMIENTO", "edad": "EDAD", "direccion": "DIRECCION",
             "barrio": "BARRIOOVEREDA", "puesto": "PUESTODEVOTACION", "mesa": "MESA",
             "autorizacion": "AUTORIZACIONDEDATOS", "medio": "MEDIODELAAUTORIZACION", "canales": "CANALESAUTORIZADOS",
             "mayor_18": "MAYORDE", "planillero": "PLANILLEROUSUARIO", "fecha": "FECHA",
             "observaciones": "OBSERVACIONES"}
COLUMNAS = lector.COLUMNAS
# Lo único que queda de una fila «No autoriza» (o de alguien ya en «no»)
SOLO_NO = ("nombre", "cedula", "barrio")

MENSAJES = {
    "planillas_apagado": "Su rol no sube fotos de planillas: el administrador lo habilita en Ajustes → Planillas "
                         "físicas por foto.",
    "compromiso_fotos": "El compromiso de confidencialidad vigente no permite fotografiar planillas: el administrador "
                        "elige en Ajustes una versión que lo permita (2026-11-v2) y cada persona la acepta de nuevo.",
    "sin_configurar": "El panel no tiene un modelo conectado para leer las fotos: el administrador lo conecta en "
                      "Ajustes → Asistente.",
    "tipo": "Solo se reciben fotos JPEG o PNG.",
    "pesada": f"La foto pesa más de {MAX_BYTES // 1_000_000},{MAX_BYTES % 1_000_000 // 100_000} MB. Vuelva a tomarla "
              "desde el panel (la reduce sola).",
    "vacia": "La foto llegó vacía.",
    "cortada": "La foto no llegó completa. Intente de nuevo.",
    "lenta": "La foto tardó demasiado en llegar. Intente de nuevo cuando haya mejor señal.",
    "imagen": "El archivo no es una foto JPEG o PNG válida.",
    "dimensiones": f"La foto tiene que medir entre {LADO_MIN} y {LADO_MAX} píxeles por su lado mayor.",
    "formato": "El formato de la foto es planilla_campo, asistencia u otro.",
    "frecuencia": "Subió muchas fotos seguidas. Espere un rato y vuelva a intentarlo.",
    "pendientes": f"Tiene {SIN_CARGAR_MAX} planillas sin cargar: espere a que se carguen o borre las que no sirvan.",
    "no_existe": "No existe esa planilla (o ya venció).",
    "sin_foto": "La foto de esta planilla ya se borró (se cargó, se rechazó o venció): queda solo lo leído.",
    "max_lecturas": f"Esta foto ya se leyó {LECTURAS_MAX} veces. Tome otra foto si hace falta.",
    "leyendo": "La foto todavía se está leyendo.",
    "no_leida": "Esta planilla no tiene filas leídas para revisar.",
    "cargando": "Esta planilla se está cargando. Espere a que termine.",
    "sin_filas": "No hay filas que cargar en esta planilla.",
    "fila": "Esa fila no está en la planilla.",
    "campo": "Esa columna no existe en la planilla.",
    "suprimida": "Esa fila no se carga: no se puede corregir.",
    "planillero": "«Capturado por» debe ser un planillero.",
    "desde_fila": "Releer desde una fila solo sirve para una lectura que quedó incompleta.",
    "clave": "La foto no se pudo abrir: la credencial del panel cambió desde que se subió. Súbala de nuevo.",
    "interrumpida": "La lectura se interrumpió (el panel se reinició). Vuelva a leerla.",
    "error": "La lectura falló. Vuelva a intentarlo.",
}
# `simular` y `cargar` de una foto leída sin ninguna fila (422 `sin_filas`)
FOTO_SIN_FILAS = ("Esta foto no tiene filas de personas leídas: no hay filas que cotejar ni cargar. Si es una hoja, "
                  "vuelva a leerla o tome otra foto.")
# Lo que avisa una lectura guardada (`lectura.aviso`, también en la bandeja): no es un error
AVISOS = lector.AVISOS


class ErrorPlanilla(HTTPException):
    """Lo que impide algo en la bandeja, como lo responde la API: `detail` es `{codigo, mensaje}` (y lo extra)."""

    def __init__(self, estado: int, codigo: str, mensaje: str | None = None, *, espera: int | None = None, **extra):
        super().__init__(estado, {"codigo": codigo, "mensaje": mensaje or MENSAJES.get(codigo, codigo), **extra},
                         headers={"Retry-After": str(espera)} if espera else None)
        self.codigo = codigo


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _utc(v: Any) -> datetime | None:
    if not isinstance(v, datetime):
        return None
    return v if v.tzinfo is not None else v.replace(tzinfo=timezone.utc)


def _iso(v: Any) -> str | None:
    d = _utc(v)
    return d.replace(microsecond=0).isoformat() if d is not None else None


def nuevo_id() -> str:
    """Un id de planilla: 32 hexadecimales al azar (no se adivina ni se recorre)."""
    return secrets.token_hex(16)


ID = re.compile(r"[0-9a-f]{32}")


# ───────────────────────────── Cifrado ─────────────────────────────

def llave(cfg: Any) -> bytes:
    """La llave (32 bytes) de las fotos y lecturas: la derivación lenta de la credencial del administrador
    (`seguridad._llave`, la de `llave_mnemo`) con una etiqueta propia. No está en la base."""
    from .seguridad import _llave
    return hmac.new(_llave(cfg.usuario or "", cfg.clave or ""), ETIQUETA_LLAVE, hashlib.sha256).digest()


def _contexto(tipo: str, pid: str, uid: Any) -> str:
    return f"planilla|{tipo}|{pid}|{uid}"


def _cifrar_foto(cfg: Any, pid: str, uid: Any, datos: bytes) -> Binary:
    return Binary(cifrado.cifrar_bytes(llave(cfg), datos, _contexto("foto", pid, uid)))


def foto_de(cfg: Any, doc: dict) -> bytes | None:
    """Los bytes de la foto (ya limpia), o None si se borró o no abre con esta credencial."""
    if not doc.get("foto"):
        return None
    return cifrado.descifrar_bytes(llave(cfg), doc["foto"], _contexto("foto", doc["_id"], doc.get("uid")))


def _cifrar_lectura(cfg: Any, pid: str, uid: Any, lectura: dict) -> Binary:
    claro = json.dumps(lectura, ensure_ascii=False, separators=(",", ":")).encode()
    return Binary(cifrado.cifrar_bytes(llave(cfg), claro, _contexto("lectura", pid, uid)))


def lectura_de(cfg: Any, doc: dict) -> dict | None:
    """Lo leído de la foto (`{tipo_formato, descripcion, datos_personales, aviso, filas_visibles, encabezado, filas,
    incompleta, ultima_fila}`; una lectura guardada antes de la descripción no trae sus tres claves), o None. Las filas
    que una supresión posterior marcó (`filas_suprimidas`) salen vacías («no se carga») y la descripción, que puede
    nombrar a esa persona, deja de salir (la próxima escritura la deja vacía, como la foto que la supresión borró)."""
    if not doc.get("lectura"):
        return None
    claro = cifrado.descifrar_bytes(llave(cfg), doc["lectura"], _contexto("lectura", doc["_id"], doc.get("uid")))
    if claro is None:
        return None
    try:
        lectura = json.loads(claro)
    except (ValueError, RecursionError):
        return None
    if not isinstance(lectura, dict) or not isinstance(lectura.get("filas"), list):
        return None
    marcadas = set(doc.get("filas_suprimidas") or [])
    if marcadas:
        lectura["filas"] = [{"n": f["n"], "reducida": "suprimida"} if f.get("n") in marcadas else f
                            for f in lectura["filas"]]
        if lectura.get("descripcion"):
            lectura["descripcion"] = ""
    return lectura


# ───────────────────────────── La imagen ─────────────────────────────

@dataclass(frozen=True)
class Imagen:
    datos: bytes        # la imagen limpia: sin metadatos y cortada en su fin
    media_type: str
    ancho: int
    alto: int


def tipo_de(cabecera: Any) -> str | None:
    """«image/jpeg» o «image/png» del `Content-Type` (sin parámetros); None si es otro."""
    if not isinstance(cabecera, str):
        return None
    t = cabecera.split(";", 1)[0].strip().lower()
    return {"image/jpg": "image/jpeg", "image/pjpeg": "image/jpeg"}.get(t, t) if t else None


def _firma(b: bytes) -> str | None:
    if b.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if b.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return None


class _Invalida(Exception):
    pass


# Un APP0 JFIF mínimo (versión 1.01, sin unidades ni miniatura): el que deja un JPEG sin sus metadatos legible por
# cualquier decodificador
_JFIF = b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
_SOF = (0xC0, 0xC1, 0xC2)            # base, extendido y progresivo con Huffman (lo que sale de una cámara o un canvas)
_TABLAS = (0xC4, 0xDB, 0xDD)         # DHT, DQT y DRI


def _jpeg(b: bytes) -> tuple[bytes, int, int]:
    """(JPEG limpio, ancho, alto): sin APPn ni COM (EXIF, GPS, miniaturas, comentarios) y cortado en EOI. Solo
    acepta lo que produce una cámara o el canvas del panel: un solo cuadro de 8 bits, en escala de grises o YCbCr."""
    n = len(b)
    if not b.startswith(b"\xff\xd8"):
        raise _Invalida
    out, i, sof = [b"\xff\xd8", _JFIF], 2, None
    while True:
        if i >= n or b[i] != 0xFF:
            raise _Invalida
        while i < n and b[i] == 0xFF:  # bytes de relleno antes del marcador
            i += 1
        if i >= n:
            raise _Invalida
        marca = b[i]
        i += 1
        if marca == 0xD9:  # EOI: lo que venga después no es de la imagen
            out.append(b"\xff\xd9")
            break
        if i + 2 > n:
            raise _Invalida
        largo = int.from_bytes(b[i:i + 2], "big")
        if largo < 2 or i + largo > n:
            raise _Invalida
        cuerpo, segmento = b[i + 2:i + largo], b"\xff" + bytes([marca]) + b[i:i + largo]
        i += largo
        if 0xE0 <= marca <= 0xEF:
            if marca == 0xEE and cuerpo.startswith(b"Adobe") and len(cuerpo) >= 12 and cuerpo[11] == 0:
                raise _Invalida  # RGB sin transformar: sin su APP14 se vería con otros colores
            continue
        if marca == 0xFE:
            continue
        if marca in _SOF:
            if sof is not None or len(cuerpo) < 6:
                raise _Invalida
            precision, alto, ancho, comp = cuerpo[0], int.from_bytes(cuerpo[1:3], "big"), \
                int.from_bytes(cuerpo[3:5], "big"), cuerpo[5]
            if precision != 8 or comp not in (1, 3) or len(cuerpo) != 6 + 3 * comp or not ancho or not alto:
                raise _Invalida
            if comp == 3 and bytes(cuerpo[6:15:3]) == b"RGB":
                raise _Invalida  # componentes RGB: un decodificador con JFIF los leería como YCbCr
            sof = (ancho, alto)
            out.append(segmento)
            continue
        if marca in _TABLAS:
            out.append(segmento)
            continue
        if marca == 0xDA:  # SOS: el segmento y los datos de la imagen hasta el siguiente marcador
            if sof is None:
                raise _Invalida
            out.append(segmento)
            j = i
            while True:
                k = b.find(b"\xff", j)
                if k < 0 or k + 1 >= n:
                    raise _Invalida  # sin EOI: la foto está cortada
                siguiente = b[k + 1]
                if siguiente == 0x00 or 0xD0 <= siguiente <= 0xD7 or siguiente == 0xFF:
                    j = k + 1 if siguiente == 0xFF else k + 2
                    continue
                break
            out.append(b[i:k])
            i = k
            continue
        raise _Invalida  # sin pérdida, aritmético, jerárquico o un marcador fuera de lugar
    if sof is None:
        raise _Invalida
    return b"".join(out), sof[0], sof[1]


_PNG = b"\x89PNG\r\n\x1a\n"
# Los únicos fragmentos que se conservan (antes de los datos): el resto de los auxiliares (eXIf, tEXt, iTXt, zTXt,
# iCCP, tIME, pHYs…) se quita, y un crítico desconocido invalida la imagen
_PNG_ANTES = (b"PLTE", b"tRNS", b"gAMA", b"cHRM", b"sRGB")
_PNG_PROFUNDIDADES = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}


def _png(b: bytes) -> tuple[bytes, int, int]:
    """(PNG limpio, ancho, alto): solo IHDR, los fragmentos de `_PNG_ANTES`, los IDAT seguidos e IEND, con su CRC
    comprobado, y cortado en IEND."""
    if not b.startswith(_PNG):
        raise _Invalida
    out, i, n = [_PNG], len(_PNG), len(b)
    cabecera, color, paleta, datos_vistos, datos_cerrados = None, None, False, False, False
    while True:
        if i + 12 > n:
            raise _Invalida  # sin IEND
        largo, tipo = int.from_bytes(b[i:i + 4], "big"), b[i + 4:i + 8]
        if largo > 0x7FFFFFFF or i + 12 + largo > n or not all(65 <= c <= 90 or 97 <= c <= 122 for c in tipo):
            raise _Invalida
        datos = b[i + 8:i + 8 + largo]
        if zlib.crc32(tipo + datos) & 0xFFFFFFFF != int.from_bytes(b[i + 8 + largo:i + 12 + largo], "big"):
            raise _Invalida
        trozo = b[i:i + 12 + largo]
        i += 12 + largo
        if cabecera is None:
            if tipo != b"IHDR" or largo != 13:
                raise _Invalida
            ancho, alto = int.from_bytes(datos[0:4], "big"), int.from_bytes(datos[4:8], "big")
            profundidad, color, compresion, filtro, entrelazado = datos[8:13]
            if profundidad not in _PNG_PROFUNDIDADES.get(color, ()) or compresion or filtro or entrelazado > 1 \
                    or not ancho or not alto:
                raise _Invalida
            cabecera = (ancho, alto)
            out.append(trozo)
            continue
        if tipo == b"IEND":
            out.append(trozo)
            break
        if tipo == b"IDAT":
            if datos_cerrados:
                raise _Invalida  # los IDAT van seguidos
            datos_vistos = True
            out.append(trozo)
            continue
        if datos_vistos:
            datos_cerrados = True
        if tipo == b"IHDR":
            raise _Invalida
        if tipo in _PNG_ANTES:
            if datos_vistos:
                raise _Invalida
            paleta = paleta or tipo == b"PLTE"
            out.append(trozo)
            continue
        if not tipo[0] & 0x20:  # un fragmento crítico que no se conoce
            raise _Invalida
    if cabecera is None or not datos_vistos or (color == 3 and not paleta):
        raise _Invalida
    return b"".join(out), cabecera[0], cabecera[1]


def validar_imagen(crudo: bytes, media_type: str | None) -> Imagen:
    """La foto subida, validada y limpia, o `ErrorPlanilla`: 415 `tipo` si no es JPEG ni PNG o su firma no es la de
    su `Content-Type`, 422 `imagen` si su estructura no es la de una imagen sana (un archivo políglota, cortado, con
    fragmentos desconocidos…), 422 `dimensiones` si su lado mayor no está entre `LADO_MIN` y `LADO_MAX`."""
    if media_type not in TIPOS:
        raise ErrorPlanilla(415, "tipo")
    if _firma(crudo) != media_type:
        raise ErrorPlanilla(415, "tipo", "El archivo no es lo que dice ser: su contenido no es " +
                            ("JPEG." if media_type == "image/jpeg" else "PNG."))
    try:
        limpio, ancho, alto = (_jpeg if media_type == "image/jpeg" else _png)(crudo)
    except (_Invalida, IndexError, ValueError):
        raise ErrorPlanilla(422, "imagen") from None
    if not LADO_MIN <= max(ancho, alto) <= LADO_MAX or min(ancho, alto) < LADO_MENOR_MIN:
        raise ErrorPlanilla(422, "dimensiones")
    return Imagen(limpio, media_type, ancho, alto)


# ───────────────────────────── Subir ─────────────────────────────

def nota_de(v: Any) -> str | None:
    return lector.una_linea(v, NOTA_MAX)[0]


def exigir_compromiso(ajustes: dict) -> None:
    """409 `compromiso_fotos` si el compromiso de confidencialidad vigente (`compromiso_version`) no deja fotografiar
    planillas físicas (`acceso.compromiso_permite_fotos`): nadie sube la foto que el compromiso que aceptó le prohíbe
    tomar. Se revisa antes de leer el cuerpo; lo ya subido se sigue revisando y cargando."""
    if not acceso.compromiso_permite_fotos((ajustes or {}).get("compromiso_version")):
        raise ErrorPlanilla(409, "compromiso_fotos")


def exigir_subida(db: Database, quien: Any, formato: str, largo: str | None) -> None:
    """Lo que impide subir, antes de leer el cuerpo (los permisos y el modelo los revisa la ruta): 413 por el
    `Content-Length`, 422 `formato` (uno que no es de `FORMATOS`: los tres se aceptan siempre, el ajuste
    `agente_planillas.otros_formatos` se retiró), 429 `frecuencia` (40 por hora, 150 por día) y 409 `pendientes` (30 sin
    cargar: leyendo, fallidas o leídas con filas; una leída sin filas no espera una carga y no cuenta). Lee MongoDB:
    desde código asíncrono, con `run_in_threadpool`."""
    if largo and largo.isdigit() and int(largo) > MAX_BYTES:
        raise ErrorPlanilla(413, "pesada")
    if formato not in FORMATOS:
        raise ErrorPlanilla(422, "formato")
    ahora = _ahora()
    hora = db.planillas_subidas.count_documents({"uid": quien.uid, "ts": {"$gte": ahora - timedelta(hours=1)}})
    if hora >= POR_HORA:
        raise ErrorPlanilla(429, "frecuencia", espera=600)
    dia = db.planillas_subidas.count_documents({"uid": quien.uid, "ts": {"$gte": ahora - timedelta(days=1)}})
    if dia >= POR_DIA:
        raise ErrorPlanilla(429, "frecuencia", "Llegó al tope de fotos por hoy. Siga mañana.", espera=3600)
    if db.planillas.count_documents({"uid": quien.uid, "estado": {"$in": list(SIN_CARGAR)},
                                     "$nor": [{"estado": "leida", "resumen.filas": 0}]}) >= SIN_CARGAR_MAX:
        raise ErrorPlanilla(409, "pendientes")


async def leer_cuerpo(request: Any) -> bytes:
    """El cuerpo de la subida, leído por partes con plazo y tope (como `dictado.leer_audio`): 413 `pesada`, 400
    `cortada` (la conexión se cortó), 400 `lenta` y 422 `vacia`."""
    partes, total = [], 0
    trozos = request.stream().__aiter__()
    try:
        async with asyncio.timeout(PLAZO_SUBIDA_S):
            while True:
                try:
                    trozo = await asyncio.wait_for(anext(trozos), SUBIDA_CALLADA_S)
                except StopAsyncIteration:
                    break
                total += len(trozo)
                if total > MAX_BYTES:
                    raise ErrorPlanilla(413, "pesada")
                partes.append(trozo)
    except ClientDisconnect:
        raise ErrorPlanilla(400, "cortada") from None
    except TimeoutError:
        raise ErrorPlanilla(400, "lenta") from None
    if not total:
        raise ErrorPlanilla(422, "vacia")
    return b"".join(partes)


def _respuesta_subida(doc: dict) -> dict:
    return {"id": doc["_id"], "estado": doc["estado"], "bytes": doc.get("bytes"), "ancho": doc.get("ancho"),
            "alto": doc.get("alto"), "expira": _iso(doc.get("expira"))}


def guardar_subida(db: Database, cfg: Any, quien: Any, imagen: Imagen, *, nota: str | None, formato: str,
                   horas: int) -> tuple[dict, bool]:
    """Guarda la foto (cifrada) como una planilla «leyendo» y devuelve (respuesta, ¿es nueva?). Si la misma persona ya
    subió esa foto (mismo SHA-256) y sigue en la bandeja, es esa misma (sin otra lectura ni otro cupo); si ya se cargó
    en una importación, 409 `ya_cargada` con su número. Anota la subida (topes) y la audita (sin datos de personas)."""
    sha = hashlib.sha256(imagen.datos).hexdigest()
    previa = db.planillas.find_one({"uid": quien.uid, "sha256": sha, "estado": {"$ne": "cargada"}},
                                   sort=[("ts", -1)])
    if previa is not None:
        return _respuesta_subida(vigente(db, previa)), False
    cargada = db.importaciones.find_one({"fotos_sha256": sha}, {"_id": 1, "ts": 1}, sort=[("_id", -1)])
    if cargada is not None:
        fecha = str(cargada.get("ts") or "")[:10]
        cuando = f" del {fecha[8:10]}/{fecha[5:7]}/{fecha[:4]}" if len(fecha) == 10 else ""
        raise ErrorPlanilla(409, "ya_cargada", f"Esta foto ya se cargó en la importación #{cargada['_id']}{cuando}.",
                            importacion_id=cargada["_id"])
    pid, ahora = nuevo_id(), _ahora()
    u = db.usuarios.find_one({"_id": quien.uid}, {"nombre": 1}) if quien.uid else None
    doc = {"_id": pid, "uid": quien.uid, "usuario": quien.usuario, "nombre": (u or {}).get("nombre") or quien.nombre,
           "rol": quien.rol, "ts": ahora, "expira": ahora + timedelta(hours=horas), "actualizada": ahora,
           "estado": "leyendo", "latido": ahora, "lecturas": 0, "error": None, "cargando": None,
           "media_type": imagen.media_type, "bytes": len(imagen.datos), "ancho": imagen.ancho, "alto": imagen.alto,
           "sha256": sha, "foto": _cifrar_foto(cfg, pid, quien.uid, imagen.datos), "lectura": None, "resumen": None,
           "nota": nota, "formato": formato, "huellas": [], "personas": [], "filas_pid": {}, "cargadas": {},
           "importaciones": [], "importacion_id": None, "filas_suprimidas": []}
    db.planillas.insert_one(doc)
    db.planillas_subidas.insert_one({"uid": quien.uid, "ts": ahora})
    bd.auditar(db, quien, "subir_planilla", "planilla", None, {"sha256": sha, "bytes": len(imagen.datos),
                                                             "ancho": imagen.ancho, "alto": imagen.alto,
                                                             "formato": formato}, planilla=pid)
    return _respuesta_subida(doc), True


# ───────────────────────────── La lectura de fondo ─────────────────────────────

_TAREAS: set[asyncio.Task] = set()   # referencia fuerte: asyncio solo guarda una débil
_candado = threading.Lock()
_ocupados: dict[str, int] = {}
_PROGRESO: dict[str, int] = {}       # filas que van llegando de cada lectura en curso (en este proceso)
_EN_CURSO: set[str] = set()          # planillas con una lectura de fondo viva en este proceso (una a la vez cada una)


class _Abandonada(Exception):
    """La planilla se borró (o dejó de estar «leyendo») mientras esperaba su turno."""


def programar(app: Any, pid: str, *, desde_fila: int | None = None) -> None:
    """Encola la lectura de fondo de la planilla `pid` en el bucle de eventos del servidor: corre aunque el navegador
    se vaya. Desde una ruta asíncrona."""
    t = asyncio.get_running_loop().create_task(leer_foto(app, pid, desde_fila=desde_fila))
    _TAREAS.add(t)
    t.add_done_callback(_TAREAS.discard)


def _latir(db: Database, pid: str) -> bool:
    """Renueva el latido de una planilla «leyendo»; False si ya no lo está (se borró, venció o falló)."""
    return db.planillas.update_one({"_id": pid, "estado": "leyendo"}, {"$set": {"latido": _ahora()}}).matched_count > 0


@asynccontextmanager
async def _cupo(db: Database, pid: str, clave: str) -> AsyncIterator[None]:
    """Uno de los `A_LA_VEZ[clave]` cupos del proceso para leer fotos con ese proveedor, mientras dura el bloque. Espera
    su turno el tiempo que haga falta (en cola), renovando el latido; si la planilla se borra mientras espera, lanza
    `_Abandonada`. Al salir, pase lo que pase, el cupo queda libre."""
    tope = A_LA_VEZ.get(clave, 1)
    ultimo = time.monotonic()
    while True:
        with _candado:
            if _ocupados.get(clave, 0) < tope:
                _ocupados[clave] = _ocupados.get(clave, 0) + 1
                break
        await asyncio.sleep(ESPERA_CUPO_S)
        if time.monotonic() - ultimo >= LATIDO_S:
            ultimo = time.monotonic()
            if not await run_in_threadpool(_latir, db, pid):
                raise _Abandonada
    try:
        yield
    finally:
        with _candado:
            _ocupados[clave] = max(0, _ocupados.get(clave, 1) - 1)


async def _latiendo(db: Database, pid: str) -> None:
    while True:
        await asyncio.sleep(LATIDO_S)
        await run_in_threadpool(_latir, db, pid)


def _quien_de(doc: dict) -> SimpleNamespace:
    return SimpleNamespace(usuario=doc.get("usuario"), uid=doc.get("uid"), rol=doc.get("rol"), ip=None)


def _fallar(db: Database, pid: str, codigo: str, mensaje: str | None = None, *, rechazada: bool = False) -> None:
    cambios: dict[str, Any] = {"estado": "rechazada" if rechazada else "fallida", "actualizada": _ahora(),
                               "error": {"codigo": codigo, "mensaje": mensaje or MENSAJES.get(codigo, codigo)}}
    if rechazada:  # una cédula u otro documento de identidad: la foto no se guarda más
        cambios.update(foto=None, lectura=None, huellas=[])
    db.planillas.update_one({"_id": pid, "estado": "leyendo"}, {"$set": cambios})


async def leer_foto(app: Any, pid: str, *, desde_fila: int | None = None) -> None:
    """La lectura de fondo de una planilla «leyendo» (ver el docstring del módulo): espera su cupo, le pide la lectura
    al proveedor del modelo (`lector_planillas.leer`), suma el uso al día de quien subió la foto, sanea y reduce las
    filas (`_reducir`) y guarda todo cifrado («leida», con o sin filas), o deja el error («fallida», o «rechazada» sin
    la foto: un documento de identidad). Nunca lanza: lo que falle queda en la planilla. Una planilla con su lectura ya
    en curso en este proceso (en cola o con el modelo) no se lee dos veces."""
    db, cfg = app.state.db, app.state.cfg
    with _candado:
        if pid in _EN_CURSO:
            return
        _EN_CURSO.add(pid)
    try:
        doc = await run_in_threadpool(db.planillas.find_one, {"_id": pid, "estado": "leyendo"})
        if doc is None:
            return
        from .agente import proveedores
        proveedor = await run_in_threadpool(proveedores.para_nueva, app, cfg, db)
        if proveedor is None:
            await run_in_threadpool(_fallar, db, pid, "sin_configurar")
            return
        async with _cupo(db, pid, proveedor.clave):
            doc = await run_in_threadpool(
                db.planillas.find_one_and_update, {"_id": pid, "estado": "leyendo"},
                {"$inc": {"lecturas": 1}, "$set": {"latido": _ahora(), "proveedor": proveedor.clave}},
                return_document=ReturnDocument.AFTER)
            if doc is None:
                return
            imagen = foto_de(cfg, doc)
            if imagen is None:
                await run_in_threadpool(_fallar, db, pid, "clave" if doc.get("foto") else "sin_foto")
                return
            latido = asyncio.ensure_future(_latiendo(db, pid))
            try:
                lectura = await lector.leer(proveedor, imagen, doc["media_type"], formato=doc.get("formato") or
                                            "planilla_campo", desde_fila=desde_fila,
                                            progreso=lambda n: _PROGRESO.__setitem__(pid, n))
            except lector.ErrorLectura as e:
                await run_in_threadpool(_sumar_uso, db, doc, e.uso)
                await run_in_threadpool(_fallar, db, pid, e.codigo, e.mensaje, rechazada=e.borrar_foto)
                await run_in_threadpool(_auditar_lectura, db, doc, {"error": e.codigo, "proveedor": proveedor.clave})
                return
            finally:
                latido.cancel()
                _PROGRESO.pop(pid, None)
            await run_in_threadpool(_sumar_uso, db, doc, lectura.uso)
            await run_in_threadpool(_guardar_lectura, db, cfg, doc, lectura, desde_fila, proveedor.clave)
    except _Abandonada:
        return
    except asyncio.CancelledError:
        # El servidor se apaga: la planilla queda fallida (se puede volver a leer), no «leyendo» para siempre
        try:
            _fallar(db, pid, "interrumpida")
        except Exception:  # noqa: BLE001 - apagando: el latido vencido la dará por fallida al consultarla
            pass
        raise
    except Exception as e:  # noqa: BLE001 - de fondo: lo que falle queda en la planilla, sin datos en el registro
        log.warning("Planillas: la lectura de fondo falló (%s)", type(e).__name__)
        try:
            await run_in_threadpool(_fallar, db, pid, "error")
        except Exception:  # noqa: BLE001
            pass
    finally:
        with _candado:
            _EN_CURSO.discard(pid)


def _sumar_uso(db: Database, doc: dict, uso: Any) -> None:
    """El uso del modelo, al día de quien subió la foto (como el plan en flujo, `agente/redactor.py`)."""
    if uso is None or not (uso.entrada or uso.salida or uso.cache_lectura or uso.cache_escritura or uso.creditos):
        return
    from .agente import conversaciones as conv_db
    conv_db.sumar_uso(db, doc["uid"], uso.entrada, uso.salida, uso.cache_lectura, uso.cache_escritura, uso.creditos)


def _auditar_lectura(db: Database, doc: dict, detalle: dict) -> None:
    bd.auditar(db, _quien_de(doc), "leer_planilla", "planilla", None,
               {"sha256": doc.get("sha256"), "lectura": doc.get("lecturas"), **detalle}, planilla=doc["_id"])


def _guardar_lectura(db: Database, cfg: Any, doc: dict, lectura: lector.Lectura, desde_fila: int | None,
                     proveedor: str) -> None:
    """Guarda lo leído (cifrado) y deja la planilla «leida», aunque no tenga ninguna fila (una foto cualquiera: queda su
    descripción). Releída desde una fila, se juntan las filas de antes con las nuevas (y, si la nueva lectura no trajo
    descripción, queda la de antes). Las filas ya cargadas no vuelven a guardar datos. `datos_personales` queda
    encendido también si la descripción trae un número largo o un correo (`minimizar.enmascarar_descripcion` la
    cambia), lo diga o no el lector; `aviso` («sin_filas»), solo si al final no quedó ninguna fila."""
    from .agente.minimizar import enmascarar_descripcion
    filas = [copy.deepcopy(f) for f in lectura.filas]
    descripcion, personales = lectura.descripcion, lectura.datos_personales
    if desde_fila is not None:
        previa = lectura_de(cfg, doc) or {}
        antes = [f for f in previa.get("filas") or [] if f.get("n", 0) < desde_fila]
        filas = antes + [f for f in filas if f["n"] >= desde_fila]
        descripcion = descripcion or previa.get("descripcion") or ""
        personales = personales or bool(previa.get("datos_personales"))
    cargadas = {int(n) for n in (doc.get("cargadas") or {})}
    filas = [{"n": f["n"], "cargada": True} if f["n"] in cargadas else f for f in filas]
    filas = _reducir(db, filas)
    personales = bool(personales or enmascarar_descripcion(descripcion) != descripcion)
    aviso = lectura.aviso if not filas else None
    datos = {"tipo_formato": lectura.tipo_formato, "descripcion": descripcion, "datos_personales": personales,
             "aviso": aviso, "filas_visibles": lectura.filas_visibles, "encabezado": lectura.encabezado,
             "filas": filas, "incompleta": lectura.incompleta, "ultima_fila": lectura.ultima_fila}
    resumen = _resumen(datos)
    resumen.update(proveedor=proveedor, modelo=(lectura.modelo or "")[:80] or None)
    # Solo si nada la tocó mientras se leía (una supresión borra la foto y marca filas: lo leído antes no se guarda)
    hecho = db.planillas.update_one({"_id": doc["_id"], "estado": "leyendo", "actualizada": doc.get("actualizada")},
                                    {"$set": {
        "estado": "leida", "lectura": _cifrar_lectura(cfg, doc["_id"], doc.get("uid"), datos), "resumen": resumen,
        "huellas": _huellas(db, filas), "error": None, "actualizada": _ahora(), "filas_suprimidas": []}})
    if hecho.matched_count:
        _auditar_lectura(db, doc, {"filas": resumen["filas"], "dudosas": resumen["dudosas"],
                                   "tipo_formato": lectura.tipo_formato, "incompleta": lectura.incompleta,
                                   "con_descripcion": bool(descripcion), "datos_personales": personales,
                                   "aviso": aviso, "proveedor": proveedor})
    else:
        _fallar(db, doc["_id"], "interrumpida")


def _resumen(lectura: dict) -> dict:
    """Lo no personal de una lectura, en claro (para la bandeja): cuántas filas, cuántas dudosas, cuántas pendientes,
    el aviso, si hay descripción (nunca su texto) y si la foto muestra datos de personas."""
    filas = lectura.get("filas") or []
    con_datos = [f for f in filas if f.get("valores")]
    return {"tipo_formato": lectura.get("tipo_formato"), "filas_visibles": lectura.get("filas_visibles"),
            "filas": len(filas), "dudosas": sum(1 for f in con_datos if f.get("dudosos") or f.get("ilegibles")),
            "pendientes": sum(1 for f in con_datos if not f.get("descartada") and not f.get("cargada")),
            "incompleta": bool(lectura.get("incompleta")), "ultima_fila": lectura.get("ultima_fila"),
            "aviso": lectura.get("aviso"), "con_descripcion": bool(lectura.get("descripcion")),
            "datos_personales": bool(lectura.get("datos_personales"))}


# ───────────────────────────── Privacidad de las filas ─────────────────────────────

_ESTADOS_AUT = {**lectores._inverso(modelo.ESTADOS_AUTORIZACION), "SI": "si", "NO": "no", "AUTORIZA": "si"}


def autorizacion_de(v: Any) -> str | None:
    """«si», «no» o None, como lo lee la planilla en Excel (`lectores.registro_planilla`)."""
    return _ESTADOS_AUT.get(lectores._clave(v)) if v not in (None, "") else None


def _identidad(valores: dict) -> tuple[list[str], list[tuple[str, Any]]]:
    """(cédulas, pares de identidad) de una fila, normalizados como los usa el importador para la supresión."""
    cedulas = [c for c in (tx.cedula(valores.get("cedula")), tx.cedula(valores.get("cedula_repetida"))) if c]
    tels = [*tx.telefonos(valores.get("celular")), *tx.telefonos(valores.get("otro_telefono"))]
    nombre = tx.nombre_visible(valores.get("nombre"))
    return list(dict.fromkeys(cedulas)), bd.pares_identidad([nombre] if tx.nombre_norm(nombre) else [], [], tels)


def _huellas_fila(clave: bytes, valores: dict) -> list[str]:
    cedulas, pares = _identidad(valores)
    hs = [bd.huella(clave, "cedula", c) for c in cedulas] + [bd.huella(clave, t, v) for t, v in pares]
    return list(dict.fromkeys(h for h in hs if h))


def _huellas(db: Database, filas: list[dict]) -> list[dict]:
    """Por fila con datos, las huellas (HMAC, como las de `suprimidos`) de su cédula y de su nombre con cada teléfono:
    con ellas la supresión de una persona encuentra sus filas sin abrir lo cifrado (`db.vaciar_planillas`)."""
    clave = bd.clave_supresion(db)
    out = []
    for f in filas:
        hs = _huellas_fila(clave, f.get("valores") or {})
        if hs:
            out.append({"n": f["n"], "h": hs})
    return out


def _reducir(db: Database, filas: list[dict]) -> list[dict]:
    """Las reglas de privacidad sobre las filas leídas, antes de guardarlas (y tras cada corrección):
    * de quien pidió la supresión (su cédula o su nombre con un teléfono, como el importador), nada: `{n, reducida:
      "suprimida"}` («no se carga», sin motivo);
    * «No autoriza» (aunque la marca sea dudosa: protege a quien quizá no autorizó), solo nombre, cédula y barrio, y la
      autorización «no» (`reducida: "no"`);
    * de alguien que ya está en «no» por su cédula exacta, lo mismo, sin la autorización (`reducida: "no_base"`)."""
    clave = bd.clave_supresion(db)
    por_fila: dict[int, tuple[list[str], list[str]]] = {}
    todas_h, todas_c = set(), set()
    for f in filas:
        if f.get("reducida") == "suprimida" or not f.get("valores"):
            continue
        cedulas, _ = _identidad(f["valores"])
        hs = _huellas_fila(clave, f["valores"])
        por_fila[f["n"]] = (cedulas, hs)
        todas_h.update(hs)
        todas_c.update(cedulas)
    suprimidas = {x["_id"] for x in db.suprimidos.find({"_id": {"$in": sorted(todas_h)}}, {"_id": 1})} \
        if todas_h else set()
    en_no = {p["cedula"] for p in db.personas.find({"cedula": {"$in": sorted(todas_c)}, "consentimiento": "no",
                                                    **bd.ACTIVA}, {"cedula": 1})} if todas_c else set()
    out = []
    for f in filas:
        if f["n"] not in por_fila:
            out.append(f)
            continue
        cedulas, hs = por_fila[f["n"]]
        if set(hs) & suprimidas:
            out.append({"n": f["n"], "reducida": "suprimida"})
            continue
        v = f["valores"]
        dice_no = autorizacion_de(v.get("autorizacion")) == "no"
        if dice_no or set(cedulas) & en_no:
            quedan = {k: v[k] for k in SOLO_NO if v.get(k)}
            if dice_no:
                quedan["autorizacion"] = "no"
            g = {"n": f["n"], "valores": quedan, "reducida": "no" if dice_no else "no_base",
                 "firma": f.get("firma"), "dudosos": [k for k in f.get("dudosos") or [] if k in quedan],
                 "ilegibles": [k for k in f.get("ilegibles") or [] if k in SOLO_NO], "descartada": f.get("descartada")}
            out.append({k: x for k, x in g.items() if x not in (None, [])})
            continue
        out.append(f)
    return out


# ───────────────────────────── Vistas ─────────────────────────────

def vigente(db: Database, doc: dict) -> dict:
    """La planilla con la regla del latido: una «leyendo» sin latido hace más de `VIVA_S` se da por fallida (se
    guarda así) y se puede volver a leer."""
    if doc.get("estado") != "leyendo":
        return doc
    latido = _utc(doc.get("latido")) or _utc(doc.get("ts"))
    if latido is None or _ahora() - latido <= timedelta(seconds=VIVA_S):
        return doc
    nuevo = db.planillas.find_one_and_update(
        {"_id": doc["_id"], "estado": "leyendo", "latido": doc.get("latido")},
        {"$set": {"estado": "fallida", "actualizada": _ahora(),
                  "error": {"codigo": "interrumpida", "mensaje": MENSAJES["interrumpida"]}}},
        return_document=ReturnDocument.AFTER)
    return nuevo or db.planillas.find_one({"_id": doc["_id"]}) or doc


def buscar(db: Database, pid: str, quien: Any) -> dict:
    """La planilla `pid` si `quien` la puede ver, con la regla del latido; si no, 404 `no_existe`. A y K ven todas (las
    rutas no dejan pasar a nadie más); el filtro por dueño queda por si otro rol llegara aquí: de otra persona es igual
    que si no existiera."""
    if not isinstance(pid, str) or not ID.fullmatch(pid):
        raise ErrorPlanilla(404, "no_existe")
    filtro: dict[str, Any] = {"_id": pid}
    if not quien.administra:
        filtro["uid"] = quien.uid
    doc = db.planillas.find_one(filtro)
    if doc is None:
        raise ErrorPlanilla(404, "no_existe")
    return vigente(db, doc)


def _subida_por(doc: dict) -> dict:
    return {"uid": doc.get("uid"), "usuario": doc.get("usuario"), "nombre": doc.get("nombre")}


def en_bandeja(doc: dict) -> dict:
    """Una planilla en la bandeja, sin datos de personas: lo que se ve en la lista. De lo leído, solo conteos y marcas:
    `aviso` («sin_filas» o None), `con_descripcion` (si hay una descripción que ver en `detalle`; no después de
    cargarla entera ni de una supresión) y `datos_personales` (si la foto muestra datos de personas aparte de las
    filas). Una foto leída sin filas tiene `filas: 0` y `pendientes: 0`."""
    from .agente.minimizar import texto_libre
    r = doc.get("resumen") or {}
    con_lectura = doc.get("estado") not in ("cargada", "rechazada")
    return {"id": doc["_id"], "estado": doc.get("estado"), "subida_por": _subida_por(doc), "ts": _iso(doc.get("ts")),
            "expira": _iso(doc.get("expira")), "formato": doc.get("formato"), "tipo_formato": r.get("tipo_formato"),
            "filas": r.get("filas"), "dudosas": r.get("dudosas"), "pendientes": r.get("pendientes"),
            "cargadas": len(doc.get("cargadas") or {}), "incompleta": bool(r.get("incompleta")),
            "importacion_id": doc.get("importacion_id"), "nota": texto_libre(doc.get("nota"), NOTA_MAX),
            "error": doc.get("error"), "ancho": doc.get("ancho"), "alto": doc.get("alto"), "bytes": doc.get("bytes"),
            "lecturas": doc.get("lecturas") or 0,
            "con_foto": doc["con_foto"] if "con_foto" in doc else bool(doc.get("foto")),
            "progreso": _PROGRESO.get(doc["_id"]) if doc.get("estado") == "leyendo" else None,
            "aviso": r.get("aviso") if con_lectura else None,
            "con_descripcion": bool(con_lectura and r.get("con_descripcion") and not doc.get("filas_suprimidas")),
            "datos_personales": bool(con_lectura and r.get("datos_personales"))}


def _sin_binarios(db: Database, filtro: dict, limite: int = BANDEJA_MAX) -> list[dict]:
    """Las planillas del filtro, de la más nueva a la más vieja, sin bajar la foto ni lo leído (solo si hay foto)."""
    return list(db.planillas.aggregate([
        {"$match": filtro}, {"$sort": {"ts": -1}}, {"$limit": limite},
        {"$addFields": {"con_foto": {"$ne": [{"$ifNull": ["$foto", None]}, None]}}},
        {"$project": {"foto": 0, "lectura": 0, "huellas": 0}}]))


def bandeja(db: Database, quien: Any, estado: str | None = None) -> list[dict]:
    """Las planillas de la bandeja (A y K, todas; otro rol, solo las suyas), de la más nueva a la más vieja."""
    filtro: dict[str, Any] = {} if quien.administra else {"uid": quien.uid}
    if estado in ESTADOS:
        filtro["estado"] = estado
    return [en_bandeja(vigente(db, d)) for d in _sin_binarios(db, filtro)]


def _es_menor(v: dict) -> bool:
    edad = lector._entero(v.get("edad"), 0, 120)
    fecha = lectores._fecha_local(v.get("fecha_nacimiento"))
    if fecha:
        e = modelo.edad_efectiva({"fecha_nacimiento": fecha})
        edad = e if e is not None else edad
    return (str(v.get("tipo_documento") or "").upper() == "TI" or (edad is not None and edad < 18)
            or lectores._si_no(v.get("mayor_18")) is False)


def fila_enmascarada(f: dict) -> dict:
    """Una fila como la ve quien no administra (y como la puede recibir el modelo de una conversación): cédula con sus
    3 últimos dígitos y si coincide con su repetición, teléfonos con sus 4 últimos (ninguno de un menor), edad en vez
    de la fecha de nacimiento, sin observaciones (solo si las hay), y de quien no autorizó, solo quién es y su
    barrio."""
    from .agente.minimizar import AVISO_NO_AUTORIZO, texto_libre
    if f.get("reducida") == "suprimida":
        return {"n": f["n"], "estado": "no_se_carga"}
    v = f.get("valores") or {}
    if f.get("reducida") in ("no", "no_base"):
        return {"n": f["n"], "nombre": v.get("nombre"), "lugar": texto_libre(v.get("barrio"), 120),
                "consentimiento": "no", "aviso": AVISO_NO_AUTORIZO}
    out: dict[str, Any] = {"n": f["n"]}
    menor = _es_menor(v)
    for k in COLUMNAS:
        x = v.get(k)
        if x is None or k in ("cedula_repetida", "fecha_nacimiento", "observaciones"):
            continue
        if k == "cedula":
            out[k] = acceso.enmascarar_cedula(tx.cedula(x) or x)
        elif k in ("celular", "otro_telefono"):
            if not menor:
                out[k] = acceso.enmascarar_telefono(re.sub(r"\D", "", x) or x)
        elif k in ("direccion", "barrio", "puesto", "planillero", "nombre"):
            out[k] = texto_libre(x, lector.LARGOS[k])
        else:
            out[k] = x if k != "edad" else lector._entero(x, 0, 120)
    if v.get("cedula") or v.get("cedula_repetida"):
        out["cedula_coincide"] = None if not v.get("cedula_repetida") else \
            tx.cedula(v.get("cedula")) == tx.cedula(v.get("cedula_repetida"))
    fecha = lectores._fecha_local(v.get("fecha_nacimiento"))
    if fecha:
        edad = modelo.edad_efectiva({"fecha_nacimiento": fecha})
        if edad is not None:
            out["edad"] = edad
    if menor:
        out["menor"] = True
    if v.get("observaciones"):
        out["tiene_observaciones"] = True
    for k in ("firma",):
        if f.get(k):
            out[k] = f[k]
    out["dudosos"] = list(f.get("dudosos") or [])
    out["ilegibles"] = list(f.get("ilegibles") or [])
    if f.get("descartada"):
        out["descartada"] = True
    return out


def _estado_fila(f: dict, doc: dict) -> str:
    n = str(f["n"])
    if n in (doc.get("cargadas") or {}) or f.get("cargada"):
        return "cargada"
    if f.get("reducida") == "suprimida":
        return "no_se_carga"
    if f.get("descartada"):
        return "descartada"
    if f.get("reducida") in ("no", "no_base"):
        return "no_autoriza"
    return "pendiente"


def detalle(cfg: Any, doc: dict, *, completa: bool) -> dict:
    """Una planilla abierta: lo de la bandeja más la descripción, el encabezado y las filas. `completa` (A y K) trae la
    descripción entera y los valores tal como se leyeron (con lo corregido); si no, enmascarados (la descripción con
    `minimizar.enmascarar_descripcion`, las filas con `fila_enmascarada`). `descripcion` es None sin lectura o sin
    descripción; `datos_personales` y `aviso`, los de la lectura (False y None sin ella). Cada fila lleva su `estado`
    («pendiente», «no_autoriza», «no_se_carga», «descartada» o «cargada») y, si está cargada, la ficha. Una foto
    leída sin filas trae `filas: []`."""
    out = en_bandeja(doc)
    out.update(media_type=doc.get("media_type"), sha256=doc.get("sha256"), columnas=list(COLUMNAS),
               puede_releer=_puede_releer(doc), importaciones=list(doc.get("importaciones") or []),
               descripcion=None, datos_personales=False, aviso=None, encabezado=None, filas_visibles=None,
               ultima_fila=None, filas=[])
    lectura = lectura_de(cfg, doc) if doc.get("lectura") else None
    cargadas = doc.get("cargadas") or {}
    if lectura is not None:
        from .agente.minimizar import enmascarar_descripcion, texto_libre
        enc = lectura.get("encabezado") or {}
        descripcion = lectura.get("descripcion") if isinstance(lectura.get("descripcion"), str) else ""
        out.update(descripcion=(descripcion if completa else enmascarar_descripcion(descripcion)) or None,
                   datos_personales=bool(lectura.get("datos_personales")), aviso=lectura.get("aviso"),
                   encabezado=enc if completa else {k: texto_libre(x, 160) for k, x in enc.items()},
                   filas_visibles=lectura.get("filas_visibles"), ultima_fila=lectura.get("ultima_fila"))
        for f in lectura.get("filas") or []:
            if completa:
                fila = {"n": f["n"], "valores": dict(f.get("valores") or {}), "firma": f.get("firma"),
                        "dudosos": list(f.get("dudosos") or []), "ilegibles": list(f.get("ilegibles") or []),
                        "corregidos": list(f.get("corregidos") or [])}
            else:
                fila = fila_enmascarada(f)
            fila["estado"] = _estado_fila(f, doc)
            c = cargadas.get(str(f["n"]))
            if c:
                fila.update(persona_id=c.get("persona_id"), resultado=c.get("estado"))
            out["filas"].append(fila)
    elif cargadas:
        out["filas"] = [{"n": int(n), "estado": "cargada", "persona_id": c.get("persona_id"),
                         "resultado": c.get("estado")} for n, c in sorted(cargadas.items(), key=lambda x: int(x[0]))]
    return out


def _puede_releer(doc: dict) -> bool:
    return (doc.get("estado") in ("leida", "fallida") and bool(doc.get("foto"))
            and (doc.get("lecturas") or 0) < LECTURAS_MAX and not _cargando(doc))


def _cargando(doc: dict) -> bool:
    c = _utc(doc.get("cargando"))
    return c is not None and _ahora() - c < timedelta(seconds=CARGANDO_S)


# ───────────────────────────── Releer, corregir, borrar ─────────────────────────────

def preparar_relectura(db: Database, cfg: Any, doc: dict, desde_fila: int | None) -> dict:
    """Deja la planilla «leyendo» para volver a leerla (la ruta encola la lectura): solo si ya terminó («leida» o
    «fallida»), conserva su foto y no se leyó `LECTURAS_MAX` veces. `desde_fila`, solo en una lectura incompleta."""
    if doc.get("estado") == "leyendo":
        raise ErrorPlanilla(409, "leyendo")
    if _cargando(doc):
        raise ErrorPlanilla(409, "cargando")
    if not doc.get("foto") or doc.get("estado") in ("rechazada", "cargada"):
        raise ErrorPlanilla(409, "sin_foto")
    if (doc.get("lecturas") or 0) >= LECTURAS_MAX:
        raise ErrorPlanilla(409, "max_lecturas")
    if desde_fila is not None and not (doc.get("resumen") or {}).get("incompleta"):
        raise ErrorPlanilla(422, "desde_fila")
    nuevo = db.planillas.find_one_and_update(
        {"_id": doc["_id"], "estado": doc["estado"], "lecturas": doc.get("lecturas") or 0},
        {"$set": {"estado": "leyendo", "latido": _ahora(), "error": None, "actualizada": _ahora()}},
        return_document=ReturnDocument.AFTER)
    if nuevo is None:
        raise ErrorPlanilla(409, "leyendo", "La planilla cambió mientras tanto: vuelva a abrirla.")
    return nuevo


def _lectura_editable(cfg: Any, doc: dict) -> dict:
    if doc.get("estado") == "leyendo":
        raise ErrorPlanilla(409, "leyendo")
    if _cargando(doc):
        raise ErrorPlanilla(409, "cargando")
    lectura = lectura_de(cfg, doc) if doc.get("estado") == "leida" else None
    if lectura is None:
        raise ErrorPlanilla(409, "no_leida")
    return lectura


def _guardar_filas(db: Database, cfg: Any, doc: dict, lectura: dict, **mas) -> dict:
    """Vuelve a cifrar y guarda la lectura (y su resumen y sus huellas), si la planilla no cambió mientras tanto."""
    resumen = {**(doc.get("resumen") or {}), **_resumen(lectura)}
    nuevo = db.planillas.find_one_and_update(
        {"_id": doc["_id"], "estado": "leida", "actualizada": doc.get("actualizada")},
        {"$set": {"lectura": _cifrar_lectura(cfg, doc["_id"], doc.get("uid"), lectura), "resumen": resumen,
                  "huellas": _huellas(db, lectura["filas"]), "actualizada": _ahora(), "filas_suprimidas": [],
                  **mas}},
        return_document=ReturnDocument.AFTER)
    if nuevo is None:
        raise ErrorPlanilla(409, "cambiada", "La planilla cambió mientras tanto: vuelva a abrirla.")
    return nuevo


def corregir(db: Database, cfg: Any, quien: Any, doc: dict, celdas: list[dict], descartar: Iterable[int] = (),
             restaurar: Iterable[int] = ()) -> dict:
    """Corrige celdas (`{n, campo, valor}`: el valor se sanea como lo leído; vacío borra la celda) y descarta o
    recupera filas, y vuelve a aplicar las reglas de privacidad (`_reducir`): una corrección puede convertir la fila en
    «No autoriza» o en la de alguien suprimido. Una fila que no se carga o ya cargada no se corrige. Audita cuántas
    celdas y filas (sin valores)."""
    lectura = _lectura_editable(cfg, doc)
    filas = {f["n"]: f for f in lectura["filas"]}
    tocadas: set[int] = set()
    for c in celdas:
        f = filas.get(c["n"])
        if f is None:
            raise ErrorPlanilla(422, "fila", n=c["n"])
        if c["campo"] not in lector.LARGOS:
            raise ErrorPlanilla(422, "campo")
        if f.get("reducida") == "suprimida" or f.get("cargada") or str(f["n"]) in (doc.get("cargadas") or {}):
            raise ErrorPlanilla(422, "suprimida" if f.get("reducida") == "suprimida" else "fila",
                                None if f.get("reducida") == "suprimida" else "Esa fila ya se cargó.", n=c["n"])
        valor, _ = lector.sanear(c["campo"], c.get("valor"))
        valores = f.setdefault("valores", {})
        if valor is None:
            valores.pop(c["campo"], None)
        else:
            valores[c["campo"]] = valor
        for k in ("dudosos", "ilegibles"):
            f[k] = [x for x in f.get(k) or [] if x != c["campo"]]
        f["corregidos"] = sorted({*(f.get("corregidos") or []), c["campo"]})
        if f.get("reducida") == "no_base":
            f.pop("reducida", None)  # se vuelve a comprobar abajo
        if f.get("reducida") == "no" and autorizacion_de(valores.get("autorizacion")) != "no":
            f.pop("reducida", None)
        tocadas.add(c["n"])
    for n, marca in [*((n, True) for n in descartar), *((n, False) for n in restaurar)]:
        f = filas.get(n)
        if f is None:
            raise ErrorPlanilla(422, "fila", n=n)
        if marca:
            f["descartada"] = True
        else:
            f.pop("descartada", None)
        tocadas.add(n)
    lectura["filas"] = _reducir(db, [filas[n] for n in sorted(filas)])
    nuevo = _guardar_filas(db, cfg, doc, lectura)
    bd.auditar(db, quien, "corregir_planilla", "planilla", None,
               {"celdas": len(celdas), "descartadas": len(list(descartar)), "filas": len(tocadas)}, planilla=doc["_id"])
    return nuevo


def borrar(db: Database, quien: Any, doc: dict) -> None:
    """Borra la planilla entera (foto y lectura). No mientras se carga."""
    if _cargando(doc):
        raise ErrorPlanilla(409, "cargando")
    db.planillas.delete_one({"_id": doc["_id"]})
    _PROGRESO.pop(doc["_id"], None)
    bd.auditar(db, quien, "borrar_planilla", "planilla", None, {"sha256": doc.get("sha256"),
                                                              "estado": doc.get("estado")}, planilla=doc["_id"])


# ───────────────────────────── Cotejar y cargar ─────────────────────────────

def registro_de_fila(f: dict, encabezado: dict | None = None, folio: str | None = None):
    """La fila leída como `Registro` de la planilla de campo (`lectores.registro_planilla`, igual que el Excel), o
    None si no trae nombre. Lo que la fila no dice del planillero y la fecha lo toma del encabezado de la hoja. Una
    autorización «sí» dudosa o ilegible cuenta como sin marcar. Marca la captura («foto») y el folio del papel."""
    valores = dict(f.get("valores") or {})
    enc = encabezado or {}
    for k in ("planillero", "fecha"):
        if not valores.get(k) and enc.get(k):
            valores[k] = enc[k]
    r = lectores.registro_planilla({PLANTILLA[k]: v for k, v in valores.items() if k in PLANTILLA}, f["n"])
    if r is None:
        return None
    dudosa = "autorizacion" in (f.get("dudosos") or []) or "autorizacion" in (f.get("ilegibles") or [])
    if dudosa and r.autorizacion == "si":
        r.autorizacion, r.canales = None, []
        r.datos = {k: v for k, v in r.datos.items() if k not in ("autorizacion", "canales")}
        r.datos["autorizacion_dudosa"] = True
    r.datos["captura"] = "foto"
    if folio:
        r.datos["folio"] = folio
    return r


def _filas_pedidas(lectura: dict, doc: dict, pedidas: list[int] | None) -> tuple[list[dict], dict[int, dict]]:
    """(filas que van al importador, las que no: `{n: {estado, persona_id}}`). Sin `pedidas`, todas las que faltan
    (y las que no se cargan, para que cada fila de la hoja tenga su estado)."""
    cargadas = doc.get("cargadas") or {}
    por_n = {f["n"]: f for f in lectura.get("filas") or []}
    if pedidas is None:
        pedidas = [n for n, f in sorted(por_n.items())
                   if _estado_fila(f, doc) in ("pendiente", "no_autoriza", "no_se_carga")]
    van, fuera = [], {}
    for n in dict.fromkeys(pedidas):
        f = por_n.get(n)
        if f is None:
            raise ErrorPlanilla(422, "fila", n=n)
        estado = _estado_fila(f, doc)
        if estado == "cargada":
            fuera[n] = {"estado": "ya_cargada", "persona_id": (cargadas.get(str(n)) or {}).get("persona_id")}
        elif estado == "no_se_carga":
            fuera[n] = {"estado": "no_se_carga", "persona_id": None}
        elif estado == "descartada":
            fuera[n] = {"estado": "descartada", "persona_id": None}
        else:
            van.append(f)
    return van, fuera


def _registros(van: list[dict], lectura: dict, folio: str | None) -> tuple[list, dict[int, dict]]:
    registros, sin_nombre = [], {}
    for f in van:
        r = registro_de_fila(f, lectura.get("encabezado"), folio)
        if r is None:
            sin_nombre[f["n"]] = {"estado": "sin_nombre", "persona_id": None}
        else:
            registros.append(r)
    return registros, sin_nombre


def _anotar_personas(db: Database, doc: dict, filas: dict[int, dict]) -> None:
    """Qué ficha corresponde a cada fila (de la vista previa o de la carga): así la supresión de esa persona encuentra
    su fila (`db.vaciar_planillas`). Solo ids, en claro."""
    pids = {str(n): f["persona_id"] for n, f in filas.items() if isinstance(f.get("persona_id"), int)}
    if pids:
        db.planillas.update_one({"_id": doc["_id"]}, {"$addToSet": {"personas": {"$each": sorted(set(pids.values()))}},
                                                      "$set": {f"filas_pid.{n}": p for n, p in pids.items()}})


def simular(db: Database, cfg: Any, quien: Any, doc: dict, pedidas: list[int] | None,
            capturado_por: int | None = None) -> dict:
    """La vista previa fiel de cargar las filas (`importar.simular_registros`, sin escribir nada): por fila `{n,
    estado, persona_id, llenaria, distintos, motivo}` y cuántas hay de cada estado. Anota las lecturas de las fichas
    que encontró (`acceso.registrar_lecturas`: quien coteja las ve). Una foto leída sin ninguna fila: 422 `sin_filas`
    (`FOTO_SIN_FILAS`)."""
    lectura = _lectura_editable(cfg, doc)
    if not lectura.get("filas"):
        raise ErrorPlanilla(422, "sin_filas", FOTO_SIN_FILAS)
    van, fuera = _filas_pedidas(lectura, doc, pedidas)
    registros, sin_nombre = _registros(van, lectura, None)
    res = imp.simular_registros(db, registros, quien=quien, capturado_por=capturado_por) if registros else {}
    filas: list[dict] = []
    for n in sorted({*fuera, *sin_nombre, *res}):
        if n in res:
            f = res[n]
            filas.append({"n": n, "estado": f["estado"], "persona_id": f["persona_id"], "llenaria": f["llenaria"],
                          "distintos": f["distintos"], "motivo": f["motivo"]})
        else:
            f = fuera.get(n) or sin_nombre[n]
            filas.append({"n": n, "estado": f["estado"], "persona_id": f["persona_id"], "llenaria": [],
                          "distintos": [], "motivo": None})
    encontradas = sorted({f["persona_id"] for f in filas if isinstance(f["persona_id"], int)})
    acceso.registrar_lecturas(db, quien, encontradas)
    _anotar_personas(db, doc, {f["n"]: f for f in filas})
    conteo: dict[str, int] = {}
    for f in filas:
        conteo[f["estado"]] = conteo.get(f["estado"], 0) + 1
    return {"id": doc["_id"], "filas": filas, "conteo": conteo}


def _tomar(db: Database, doc: dict) -> dict:
    """Marca la planilla como «cargando» (una carga a la vez por planilla); 409 si ya lo está."""
    ahora = _ahora()
    tomada = db.planillas.find_one_and_update(
        {"_id": doc["_id"], "estado": "leida",
         "$or": [{"cargando": None}, {"cargando": {"$lt": ahora - timedelta(seconds=CARGANDO_S)}}]},
        {"$set": {"cargando": ahora}}, return_document=ReturnDocument.AFTER)
    if tomada is None:
        actual = db.planillas.find_one({"_id": doc["_id"]}, {"estado": 1, "cargando": 1}) or {}
        raise ErrorPlanilla(409, "cargando" if _cargando(actual) else "no_leida")
    return tomada


def cargar(db: Database, cfg: Any, quien: Any, doc: dict, pedidas: list[int] | None, folio: str | None,
           capturado_por: int | None) -> dict:
    """Carga las filas con el importador real (`importar.importar_registros`: fuente «planilla», archivo «Foto de
    planilla física», la foto como evidencia por su SHA-256, el folio del papel y la captura «foto»; autorizaciones
    declaradas). Devuelve `{importacion_id, resumen, filas: {n: {persona_id, estado, motivo}}}`. Las filas cargadas
    pierden sus datos en la lectura (queda número, estado y ficha); cuando no queda ninguna pendiente, se borran la foto
    y lo leído y la planilla queda «cargada». Sin el planillero, el «capturado por» es quien subió la foto si es
    planillero (una foto subida antes de que las planillas por foto quedaran solo para A y K). Una foto leída sin
    ninguna fila: 422 `sin_filas` (`FOTO_SIN_FILAS`), sin tocar nada."""
    doc = _tomar(db, doc)
    try:
        lectura = lectura_de(cfg, doc)
        if lectura is None:
            raise ErrorPlanilla(409, "no_leida")
        if not lectura.get("filas"):
            raise ErrorPlanilla(422, "sin_filas", FOTO_SIN_FILAS)
        van, fuera = _filas_pedidas(lectura, doc, pedidas)
        registros, sin_nombre = _registros(van, lectura, folio)
        if not registros:
            raise ErrorPlanilla(422, "sin_filas")
        if capturado_por is None and doc.get("rol") == "planillero":
            capturado_por = doc.get("uid")
        imp_id = bd.siguiente_id(db, "importaciones")
        res, filas = imp.importar_registros(db, registros, quien=quien, capturado_por=capturado_por, archivo=ARCHIVO,
                                            sha=doc.get("sha256"), fotos_sha256=[doc["sha256"]],
                                            importacion_id=imp_id)
        salida = {**{n: {"persona_id": None, **f} for n, f in fuera.items()},
                  **{n: {"persona_id": None, "motivo": None, **f} for n, f in sin_nombre.items()},
                  **{n: {"persona_id": f["persona_id"], "estado": f["estado"], "motivo": f["motivo"]}
                     for n, f in filas.items()}}
        # Una fila sin nombre o que no se pudo guardar sigue pendiente (se corrige y se vuelve a cargar)
        hechas = {n: f for n, f in filas.items() if f["estado"] != "no_guardada"}
        cargadas = {**(doc.get("cargadas") or {}),
                    **{str(n): {"persona_id": f.get("persona_id"), "estado": f["estado"]} for n, f in hechas.items()}}
        lectura["filas"] = [{"n": f["n"], "cargada": True} if f["n"] in hechas else f for f in lectura["filas"]]
        resumen_lectura = _resumen(lectura)
        cambios: dict[str, Any] = {"cargadas": cargadas, "importacion_id": imp_id, "actualizada": _ahora(),
                                   "cargando": None}
        if resumen_lectura["pendientes"] == 0:
            cambios.update(estado="cargada", foto=None, lectura=None, huellas=[], filas_suprimidas=[],
                           resumen={**(doc.get("resumen") or {}), **resumen_lectura})
        else:
            cambios.update(lectura=_cifrar_lectura(cfg, doc["_id"], doc.get("uid"), lectura),
                           resumen={**(doc.get("resumen") or {}), **resumen_lectura},
                           huellas=_huellas(db, lectura["filas"]), filas_suprimidas=[])
        hecho = db.planillas.update_one({"_id": doc["_id"], "actualizada": doc.get("actualizada")},
                                        {"$set": cambios, "$push": {"importaciones": imp_id}})
        if not hecho.matched_count:
            # Una supresión la tocó mientras se cargaba: lo cifrado queda como lo dejó (con sus filas marcadas) y solo
            # se anota la carga
            minimos: dict[str, Any] = {"cargadas": cargadas, "importacion_id": imp_id, "actualizada": _ahora(),
                                       "cargando": None}
            if resumen_lectura["pendientes"] == 0:
                minimos.update(estado="cargada", foto=None, lectura=None, huellas=[], filas_suprimidas=[])
            db.planillas.update_one({"_id": doc["_id"]}, {"$set": minimos, "$push": {"importaciones": imp_id}})
        _anotar_personas(db, doc, filas)
        bd.auditar(db, quien, "cargar_planilla", "planilla", None,
                   {"importacion_id": imp_id, "filas": len(registros), "sha256": doc.get("sha256")},
                   planilla=doc["_id"])
        return {"importacion_id": imp_id, "resumen": res.dict(),
                "filas": {str(n): salida[n] for n in sorted(salida)}}
    finally:
        db.planillas.update_one({"_id": doc["_id"], "cargando": doc.get("cargando")}, {"$set": {"cargando": None}})


# ───────────────────────────── Para el chat (B2) ─────────────────────────────

def fotos_de(db: Database, uid: Any, ids: Iterable[str]) -> list[dict]:
    """Las planillas `ids` que son de `uid` (en el orden pedido; las que no existen o son de otra persona no salen),
    como en la bandeja: lo que el chat verifica antes de mandar un mensaje con fotos adjuntas."""
    ids = [i for i in dict.fromkeys(ids) if isinstance(i, str) and ID.fullmatch(i)]
    if not ids:
        return []
    docs = {d["_id"]: d for d in _sin_binarios(db, {"_id": {"$in": ids}, "uid": uid}, len(ids))}
    return [en_bandeja(vigente(db, docs[i])) for i in ids if i in docs]


def estado_adjuntos(clave_proveedor: str | None) -> dict | None:
    """Lo que el widget necesita para preparar las fotos (`/api/agente/estado.adjuntos`): None sin proveedor."""
    if clave_proveedor is None:
        return None
    return {"max_por_mensaje": MAX_POR_MENSAJE, "lado_max": LADO_MNEMO if clave_proveedor == "mnemo" else LADO_DIRECTO,
            "calidad": CALIDAD, "max_bytes": MAX_BYTES}
