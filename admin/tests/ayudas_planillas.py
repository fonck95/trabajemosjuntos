"""Ayudas de las pruebas de las planillas físicas por foto (área B1): imágenes inventadas generadas con Pillow (nunca
fotos reales), un proveedor del modelo falso que responde una lectura en JSON escrita por la prueba (sin red) y atajos
para subir, leer y cargar por la API. Solo personas inventadas."""
from __future__ import annotations

import asyncio
import functools
import io
import json
import struct
import zlib
from typing import Any

from PIL import Image

from app.agente.proveedores import Respuesta, Uso

# ───────────────────────────── Imágenes inventadas ─────────────────────────────

GPS_TEXTO = b"GPS-INVENTADO-7.0062N-73.9112W"


def _exif(con_gps: bool = True) -> bytes:
    """Un bloque EXIF con marca, modelo, un texto propio y (si se pide) una rama GPS: todo lo que la limpieza quita."""
    ex = Image.Exif()
    ex[0x010F] = "FabricanteInventado"   # Make
    ex[0x0110] = "ModeloInventado"       # Model
    ex[0x010E] = "DESCRIPCION-SECRETA"   # ImageDescription
    if con_gps:
        ex[0x8825] = {1: "N", 2: (7.0, 0.0, 22.32), 3: "W", 4: (73.0, 54.0, 40.32), 27: GPS_TEXTO.decode()}
    return ex.tobytes()


def imagen(ancho: int = 1200, alto: int = 900, color=(240, 240, 235)) -> Image.Image:
    """Una «planilla» inventada: fondo claro con unas líneas oscuras (no es una foto de nadie)."""
    im = Image.new("RGB", (ancho, alto), color)
    px = im.load()
    for y in range(40, alto, max(20, alto // 15)):
        for x in range(20, ancho - 20):
            px[x, y] = (30, 30, 30)
    return im


def jpeg(ancho: int = 1200, alto: int = 900, *, exif: bool = True, gps: bool = True, comentario: bytes | None = None,
         progresivo: bool = False, modo: str = "RGB", despues: bytes = b"") -> bytes:
    im = imagen(ancho, alto)
    if modo != "RGB":
        im = im.convert(modo)
    b = io.BytesIO()
    kw: dict[str, Any] = {"quality": 80, "progressive": progresivo}
    if exif:
        kw["exif"] = _exif(gps)
    if comentario is not None:
        kw["comment"] = comentario
    im.save(b, "JPEG", **kw)
    return b.getvalue() + despues


def _trozo(tipo: bytes, datos: bytes) -> bytes:
    return struct.pack(">I", len(datos)) + tipo + datos + struct.pack(">I", zlib.crc32(tipo + datos) & 0xFFFFFFFF)


def png(ancho: int = 1000, alto: int = 800, *, textos: bool = True, despues: bytes = b"", modo: str = "RGB") -> bytes:
    """Un PNG inventado con fragmentos de metadatos (tEXt, iTXt, zTXt, eXIf, iCCP, tIME) metidos antes de los datos
    y un gAMA, que se conserva."""
    im = imagen(ancho, alto)
    if modo != "RGB":
        im = im.convert(modo)
    b = io.BytesIO()
    im.save(b, "PNG")
    crudo = b.getvalue()
    if textos:
        extra = (_trozo(b"gAMA", struct.pack(">I", 45455)) +
                 _trozo(b"tEXt", b"Comment\x00TEXTO-SECRETO") +
                 _trozo(b"iTXt", b"Autor\x00\x00\x00\x00\x00ITXT-SECRETO") +
                 _trozo(b"zTXt", b"Nota\x00\x00" + zlib.compress(b"ZTXT-SECRETO")) +
                 _trozo(b"eXIf", _exif(True)[6:] if _exif(True).startswith(b"Exif") else _exif(True)) +
                 _trozo(b"iCCP", b"perfil\x00\x00" + zlib.compress(b"ICCP-SECRETO")) +
                 _trozo(b"tIME", struct.pack(">HBBBBB", 2026, 11, 2, 10, 0, 0)))
        crudo = crudo[:33] + extra + crudo[33:]  # justo después de IHDR (8 + 25 bytes)
    return crudo + despues


def gif(ancho: int = 400, alto: int = 300) -> bytes:
    b = io.BytesIO()
    imagen(ancho, alto).save(b, "GIF")
    return b.getvalue()


def abre(datos: bytes) -> Image.Image:
    im = Image.open(io.BytesIO(datos))
    im.load()
    return im


# ───────────────────────────── La lectura del modelo, inventada ─────────────────────────────

COLUMNAS = ["cedula", "cedula_repetida", "tipo_documento", "nombre", "celular", "otro_telefono", "sexo",
            "fecha_nacimiento", "edad", "direccion", "barrio", "puesto", "mesa", "autorizacion", "medio", "canales",
            "mayor_18", "planillero", "fecha", "observaciones"]


def fila(n: int, *, firma=None, dudosos=(), ilegibles=(), **valores) -> dict:
    """Una fila como la escribe el lector: `{"n", "v": [valores en el orden de COLUMNAS], ...}`."""
    v = [valores.get(c) for c in COLUMNAS]
    while v and v[-1] is None:
        v.pop()
    return {"n": n, "v": v, "firma": firma, "dudosos": list(dudosos), "ilegibles": list(ilegibles)}


def lectura_json(filas: list[dict], *, visibles: int | None = None, tipo: str = "planilla_campo",
                 imagen_visible: bool = True, encabezado: dict | None = None, columnas: list[str] | None = None,
                 descripcion: str | None = None, datos_personales: bool | None = None) -> str:
    """La respuesta del lector, con las claves en el orden que se le piden. Sin `descripcion` ni `datos_personales`,
    como respondería un lector de antes (sin esas claves): así las pruebas de las filas siguen igual."""
    obj: dict[str, Any] = {"imagen_visible": imagen_visible, "tipo_formato": tipo}
    if descripcion is not None:
        obj["descripcion"] = descripcion
    if datos_personales is not None:
        obj["datos_personales"] = datos_personales
    obj.update({"filas_visibles": len(filas) if visibles is None else visibles,
                "encabezado": encabezado or {"planillero": None, "fecha": "02/11/2026", "lugar": None},
                "columnas": columnas or COLUMNAS, "filas": filas})
    return json.dumps(obj, ensure_ascii=False)


class ProveedorFalso:
    """Un proveedor del modelo (`proveedores.Proveedor`) que responde lo que la prueba le pone en `respuestas`: un
    texto (la lectura), una tupla (texto, fin) o una excepción. Guarda cada llamada en `llamadas` y manda el texto por
    `al_evento` a trozos, como Mnemo y Anthropic."""

    def __init__(self, *respuestas, clave: str = "anthropic", uso: Uso | None = None, pausa: float = 0.0):
        self.clave, self.modelo, self.max_tokens, self.tope_imagenes = clave, "modelo-falso", 32_000, 8_000_000
        self.respuestas, self.llamadas = list(respuestas), []
        self.uso = uso or Uso(entrada=1200, salida=340, cache_lectura=0, cache_escritura=900)
        self.pausa = pausa

    def agregar(self, *respuestas) -> None:
        self.respuestas.extend(respuestas)

    async def generar(self, sistema, mensajes, herramientas, *, max_tokens, esfuerzo, al_evento, rapido=False,
                      vision=False):
        self.llamadas.append({"sistema": sistema, "mensajes": mensajes, "herramientas": herramientas,
                              "max_tokens": max_tokens, "esfuerzo": esfuerzo, "al_evento": al_evento,
                              "rapido": rapido, "vision": vision})
        if not self.respuestas:
            raise AssertionError("ProveedorFalso: no quedan respuestas")
        r = self.respuestas.pop(0)
        if isinstance(r, BaseException):
            raise r
        texto, fin = (r if isinstance(r, tuple) else (r, "end_turn"))
        for i in range(0, len(texto), 97):
            al_evento({"tipo": "texto", "texto": texto[i:i + 97]})
        if self.pausa:
            await asyncio.sleep(self.pausa)
        return Respuesta(contenido=[{"type": "text", "text": texto}], fin=fin, modelo="modelo-falso", uso=self.uso)

    def reintento(self, e, intento):
        return None

    def explicar(self, e):
        return f"Falló el modelo falso ({type(e).__name__}).", "llm_falso"


# ───────────────────────────── La API ─────────────────────────────

def encender(monkeypatch, app, proveedor: ProveedorFalso, *, roles=("admin", "coordinador", "planillero"),
             horas: int = 24, de_fondo: bool = False) -> list:
    """Deja la bandeja lista en `app`: el proveedor falso para leer, los roles que suben fotos y la retención. Sin
    `de_fondo`, la lectura no se encola sola (la prueba la corre con `leer`): devuelve la lista de las encoladas."""
    from app import planillas as pl
    from app.agente import proveedores
    monkeypatch.setattr(proveedores, "clave_para_nueva", lambda cfg, db: proveedor.clave)
    monkeypatch.setattr(proveedores, "para_nueva", lambda app_, cfg, db: proveedor)
    app.state.db.meta.update_one({"_id": "ajustes"}, {"$set": {"agente_planillas": {
        "roles": list(roles), "retencion_horas": horas}}}, upsert=True)
    encoladas: list = []
    if not de_fondo:
        monkeypatch.setattr(pl, "programar", lambda app_, pid, desde_fila=None: encoladas.append((pid, desde_fila)))
    return encoladas


def subir(c, datos: bytes, tipo: str = "image/jpeg", **params):
    return c.post("/api/planillas/fotos", content=datos, headers={"Content-Type": tipo}, params=params)


def leer(cliente, pid: str, desde_fila: int | None = None) -> None:
    """Corre la lectura de fondo de `pid` en el bucle de la aplicación (el del fixture `cliente`)."""
    from app import planillas as pl
    cliente.portal.call(functools.partial(pl.leer_foto, cliente.app, pid, desde_fila=desde_fila))


def subir_y_leer(cliente, c, texto_o_proveedor, datos: bytes | None = None, **params) -> str:
    """Sube una foto con el cliente `c` y corre su lectura; devuelve el id."""
    r = subir(c, datos or jpeg(), **params)
    assert r.status_code in (200, 201), r.text
    leer(cliente, r.json()["id"])
    return r.json()["id"]


def esperar(c, pid: str, hasta: float = 10.0) -> dict:
    """Consulta la planilla hasta que deje de estar «leyendo» (la lectura de fondo de verdad)."""
    import time
    fin = time.monotonic() + hasta
    while True:
        d = c.get(f"/api/planillas/{pid}").json()
        if d.get("estado") != "leyendo" or time.monotonic() > fin:
            return d
        time.sleep(0.05)


def asgi(app, metodo: str, ruta: str, headers: dict, partes: list[bytes]):
    """Llama a la aplicación ASGI y cuenta cuántas partes del cuerpo leyó antes de responder (como
    tests/test_permisos.py)."""
    partes, leidas, res = list(partes), [], {}

    async def receive():
        leidas.append(1)
        if partes:
            return {"type": "http.request", "body": partes.pop(0), "more_body": bool(partes)}
        return {"type": "http.disconnect"}

    async def send(msg):
        if msg["type"] == "http.response.start":
            res.setdefault("estado", msg["status"])
            res.setdefault("leidas", len(leidas))
        if msg["type"] == "http.response.body" and "cuerpo" not in res:
            res["cuerpo"] = msg.get("body", b"")

    ruta_cruda, _, consulta = ruta.partition("?")
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": metodo, "scheme": "http",
             "path": ruta_cruda, "raw_path": ruta_cruda.encode(), "query_string": consulta.encode(), "root_path": "",
             "client": ("203.0.113.50", 1), "server": ("testserver", 80),
             "headers": [(k.encode(), v.encode()) for k, v in headers.items()]}
    asyncio.run(app(scope, receive, send))
    return res["estado"], res["leidas"], res.get("cuerpo", b"")


def cabeceras_de(c, **mas) -> dict:
    from app import seguridad as seg
    return {"cookie": f"{seg.COOKIE}={c.cookies.get(seg.COOKIE)}", "x-csrf-token": c.headers["X-CSRF-Token"], **mas}
