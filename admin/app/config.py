"""Configuración desde variables de entorno (y un archivo .env opcional, sin dependencias).

* `ADMIN` (usuario) y `password` (clave) del administrador, tal como están en Railway. También `admin` / `PASSWORD`.
* `MONGODB_URI`: conexión a MongoDB (la del plugin de Railway o de Atlas). `MONGODB_DB` opcional; si la URI no trae
  base de datos se usa `panel_yondo`. En Railway es obligatoria; en local se usa un MongoDB en 127.0.0.1.
* El asistente (`app/agente`, `docs/agente.md`): `ANTHROPIC_API_KEY` (opcional: el «modo directo», sin Mnemo),
  `AGENTE_MODELO` y `AGENTE_ESFUERZO`. La conexión con Mnemo no es una variable: el administrador la hace desde
  Ajustes → Asistente con OAuth (`agente/mnemo_conexion.py`), y los tokens quedan cifrados en la base. `MNEMO_MCP_URL`
  (opcional) es solo la dirección que se le sugiere ahí; `MNEMO_MODELO` (opcional) elige el modelo de la cuenta de
  Mnemo (`principal`, `ligero` o `<proveedor>/<modelo>`; vacía, el de la cuenta) y `MNEMO_HERRAMIENTAS` acota qué
  herramientas de Mnemo se ofrecen (lista separada por comas, o `*` para todas las que permita la conexión).
  `MNEMO_TOKEN` ya no se usa: si está definida se ignora con un aviso en el registro.
* `SITIO_URL` (opcional): la dirección https:// del sitio público cuando el panel se despliega aparte (Root Directory =
  admin). La vista Presentación muestra de ahí la propuesta 2028–2031 en un iframe, y la CSP del panel lo permite
  (`frame-src`). En el servicio único (`servidor.py`) no hace falta: el sitio está en la raíz del mismo origen.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
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


ESFUERZOS = ("low", "medium", "high", "xhigh", "max")
MODELO_AGENTE = "claude-opus-5-5"


@dataclass(frozen=True)
class Config:
    usuario: str
    clave: str
    mongodb_uri: str
    mongodb_db: str
    horas_sesion: int
    cookie_segura: bool
    max_subida_mb: int
    # El asistente. Las claves no salen en el repr: el de `Config` aparece en las trazas de pytest y en el registro
    anthropic_api_key: str = field(default="", repr=False)
    agente_modelo: str = MODELO_AGENTE
    agente_esfuerzo: str = "medium"
    # Mnemo: la dirección MCP que se sugiere al conectar en Ajustes (la conexión, con sus tokens, vive en la base)
    mnemo_url: str = ""
    mnemo_herramientas: str = ""
    mnemo_modelo: str = ""  # «» (el de la cuenta), «principal», «ligero» o «<proveedor>/<modelo>»
    # El sitio público si vive en otro origen (el panel desplegado aparte): «https://sitio.example» o con una ruta
    sitio_url: str = ""

    @property
    def agente_configurado(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def origen_sitio(self) -> str:
        """El origen de `sitio_url` («https://sitio.example:8443»), o «» sin él."""
        m = re.match(r"^(https?://[^/]+)", self.sitio_url)
        return m.group(1) if m else ""


def _url_mnemo(v: str) -> str:
    """La dirección del servidor MCP de Mnemo que se sugiere al conectar (`https://<host>/mcp`). Solo https, salvo en
    la propia máquina. Una dirección que no cumple se descarta con un aviso, sin cortar el arranque: el administrador
    puede escribir otra en Ajustes."""
    v = v.strip().rstrip("/")
    if not v:
        return ""
    if re.match(r"^https://[^\s/]+(/\S*)?$", v) or re.match(r"^http://(127\.0\.0\.1|localhost)(:\d+)?(/\S*)?$", v):
        return v
    log.warning("MNEMO_MCP_URL debe ser una dirección https://…/mcp: se ignora (es solo la dirección que se sugiere "
                "para conectar Mnemo en Ajustes)")
    return ""


def _url_sitio(v: str) -> str:
    """`SITIO_URL`: la dirección del sitio público (`https://<host>[:puerto][/ruta]`; en la propia máquina también
    http://127.0.0.1 o http://localhost). Sin consulta, fragmento, usuario ni espacios: va a la CSP del panel y al src de
    un iframe. Otra cosa se descarta con un aviso (el panel sigue: la vista Presentación dice que no hay sitio)."""
    v = v.strip().rstrip("/")
    if not v:
        return ""
    ruta = r"(/[A-Za-z0-9._~%-]*)*"
    if (re.fullmatch(rf"https://[A-Za-z0-9.-]+(:\d{{1,5}})?{ruta}", v)
            or re.fullmatch(rf"http://(127\.0\.0\.1|localhost)(:\d{{1,5}})?{ruta}", v)):
        return v
    log.warning("SITIO_URL debe ser la dirección https://… del sitio público: se ignora (la vista Presentación queda "
                "sin la propuesta)")
    return ""


_MODELO_MNEMO = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}/[A-Za-z0-9][A-Za-z0-9._:@/+-]{0,159}")


def _modelo_mnemo(v: str) -> str:
    """`MNEMO_MODELO`: `principal`, `ligero` o `<proveedor>/<modelo>` (como los nombra Mnemo: proveedor de hasta 64
    caracteres, modelo de hasta 160). Vacía o con otra forma, el modelo por defecto de la cuenta (lo segundo con un
    aviso en el registro, sin el valor: no se sabe qué se pegó ahí)."""
    v = v.strip()
    if not v:
        return ""
    if v.lower() in ("principal", "ligero"):
        return v.lower()
    if _MODELO_MNEMO.fullmatch(v):
        return v
    log.warning("MNEMO_MODELO debe ser principal, ligero o <proveedor>/<modelo>: se ignora y se usa el modelo por "
                "defecto de la cuenta de Mnemo")
    return ""


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
    if _primera("MNEMO_TOKEN"):
        log.warning("MNEMO_TOKEN ya no se usa y se ignora: el administrador conecta Mnemo desde Ajustes → Asistente "
                    "(inicia sesión en Mnemo y da permiso). Puede borrar la variable")
    esfuerzo = _primera("AGENTE_ESFUERZO").strip().lower() or "medium"
    if esfuerzo not in ESFUERZOS:
        log.warning("AGENTE_ESFUERZO vale %r y debe ser uno de %s: se usa medium", esfuerzo, ", ".join(ESFUERZOS))
        esfuerzo = "medium"
    return Config(
        usuario=_primera("ADMIN", "admin"),
        clave=_primera("password", "PASSWORD"),
        mongodb_uri=uri,
        mongodb_db=_primera("MONGODB_DB"),
        horas_sesion=_entero("SESSION_HOURS", 12),
        cookie_segura=cookie_segura,
        max_subida_mb=_entero("MAX_UPLOAD_MB", 25),
        anthropic_api_key=_primera("ANTHROPIC_API_KEY").strip(),
        agente_modelo=_primera("AGENTE_MODELO").strip() or MODELO_AGENTE,
        agente_esfuerzo=esfuerzo,
        mnemo_url=_url_mnemo(_primera("MNEMO_MCP_URL")),
        mnemo_herramientas=_primera("MNEMO_HERRAMIENTAS").strip(),
        mnemo_modelo=_modelo_mnemo(_primera("MNEMO_MODELO")),
        sitio_url=_url_sitio(_primera("SITIO_URL")),
    )
