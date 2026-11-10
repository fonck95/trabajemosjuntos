"""Herramientas del asistente para la gestión: indicadores, reuniones (leer, crear y registrar asistentes), pendientes,
mi trabajo, el equipo, el nomenclátor de lugares y los catálogos. Las del mapa y las vistas están en `interfaz.py`.

Por qué está hecho así:

* Todo lo que toca personas o la gestión va por `ctx.api` (las mismas rutas que usa la interfaz, con la sesión del
  usuario): los permisos, el alcance del planillero, el presupuesto diario y las lecturas, la proyección por rol, el
  bloqueo de quien no autorizó, la idempotencia y la auditoría son exactamente los del panel. Solo lo que no es de
  personas se lee directo de la base: el nomenclátor (`db.lugares`), las etiquetas y, para no crear dos veces la misma
  reunión, las reuniones del propio usuario en esa fecha (`db.reuniones`).
* Al modelo le llega lo mínimo: conteos y resúmenes en vez de listas, y las personas que aparecen (asistentes, la cola
  de llamadas) pasan por `minimizar`, con sus ids en `Resultado.personas`. De los indicadores nunca salen las listas de
  origen, los datos sensibles, los líderes, la base con cédula ni la actividad del equipo (auditoría): el modelo es un
  tercero (Ley 1581) y esos datos revelan afiliación política o salud.
* De quien no autorizó el tratamiento, nada más que quién es: los indicadores se calculan siempre sin esas personas
  (`tratables`) y la lista de asistentes de una reunión no las trae ni suma sus necesidades. Un desglose de un grupo
  pequeño, o la resta de dos conteos, diría su sexo, su edad o sus necesidades. Por eso los conteos de las reuniones,
  de mi trabajo, de lo pendiente del trabajo y del equipo (lo que hizo cada usuario y el avance de cada lugar) tampoco
  las cuentan (`tratables` en la API).
* Las entradas vienen de un LLM: modelos pydantic con `extra="forbid"` (una clave mal escrita es un error visible, no
  un filtro que se ignora), los topes y valores de la API y una lista blanca de filtros. Fuera de esa lista quedan los
  que revelan datos políticos o de salud y la búsqueda por texto o número: contar con `q` dejaría reconstruir, dígito a
  dígito, una cédula o un teléfono que el modelo recibe enmascarados.
* Los lugares se resuelven en el servidor con el nomenclátor del panel (`Nomenclator`, sus alias y `PRIORIDAD`). Un
  nombre ambiguo («La Paz»: barrio del casco y vereda) no se adivina: vuelve con sus candidatos para que el modelo
  pregunte. Los homónimos del mismo sitio («San Miguel del Tigre»: corregimiento, vereda y centro poblado en el mismo
  punto) se resuelven por el más preciso, como hace el nomenclátor con las direcciones.
* Las escrituras arman su tarjeta sin escribir nada y escriben una sola vez al aprobarse: con la `Idempotency-Key` del
  `tool_use` (registrar un asistente) y, donde la API no la tiene (crear una reunión), sin repetir una reunión igual
  del mismo usuario.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Annotated, Any, Awaitable, Callable, Literal

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator
from rapidfuzz import fuzz, process
from starlette.concurrency import run_in_threadpool

from ... import modelo
from ...pipeline import direcciones as dirs
from ...pipeline import texto as tx
from .. import minimizar
from .base import Confirmacion, Contexto, ErrorHerramienta, Herramienta, Resultado

MAX_ID = 2_000_000_000
TOP = 10  # filas de cada ranking de los indicadores que llegan al modelo


# ───────────────────────────── Tipos y validación de la entrada ─────────────────────────────

def _no_booleano(v: Any) -> Any:
    """`True` es un `int` en Python y pydantic lo aceptaría como el id 1: con un id del modelo, mejor un error."""
    if isinstance(v, bool):
        raise ValueError("Debe ser un número entero (un id), no verdadero o falso")
    return v


# Los topes van antes del validador: así el esquema dice «minimum/maximum»
Id = Annotated[int, Field(ge=1, le=MAX_ID), BeforeValidator(_no_booleano)]
IdOCero = Annotated[int, Field(ge=0, le=MAX_ID), BeforeValidator(_no_booleano)]


def _fecha(v: str) -> str:
    """AAAA-MM-DD de una fecha que exista (como `fecha_iso` de la API), en un rango razonable."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        raise ValueError("Use el formato AAAA-MM-DD")
    try:
        d = date.fromisoformat(v)
    except ValueError:
        raise ValueError(f"Fecha inexistente: {v}") from None
    if not 2000 <= d.year <= 2100:
        raise ValueError("La fecha debe estar entre los años 2000 y 2100")
    return v


def _hora(v: str) -> str:
    """HH:MM de 24 horas («9:30» queda «09:30»): la API guarda hasta 5 caracteres sin revisar el formato."""
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", v)
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise ValueError("Use la hora en formato HH:MM de 24 horas (por ejemplo 15:30)")
    return f"{int(m.group(1)):02d}:{m.group(2)}"


Fecha = Annotated[str, Field(min_length=10, max_length=10, description="AAAA-MM-DD"), AfterValidator(_fecha)]
Hora = Annotated[str, Field(min_length=4, max_length=5, description="HH:MM de 24 horas"), AfterValidator(_hora)]


class _Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _sin_repetidos(v: list | None) -> list | None:
    return list(dict.fromkeys(v)) if v else v


# ───────────────────────────── Esquema para la Messages API ─────────────────────────────

_FUERA_DEL_ESQUEMA = ("$defs", "title", "discriminator")


def esquema(m: type[BaseModel]) -> dict:
    """El JSON Schema de pydantic, autocontenido y corto: sin `$defs` ni `$ref` (los modelos anidados quedan en línea),
    sin `title` ni `discriminator`, `oneOf` como `anyOf`, `const` como `enum` y los opcionales (`X | None = None`)
    como `X` (el modelo simplemente omite la clave). Usa solo palabras que la Messages API entiende en cualquier
    versión, y gasta menos contexto."""
    s = m.model_json_schema()
    defs = s.get("$defs", {})

    def resolver(x: Any) -> Any:
        if isinstance(x, list):
            return [resolver(v) for v in x]
        if not isinstance(x, dict):
            return x
        if "$ref" in x:
            nombre = str(x["$ref"]).rsplit("/", 1)[-1]
            return resolver({**defs[nombre], **{k: v for k, v in x.items() if k != "$ref"}})
        out: dict = {}
        for k, v in x.items():
            if k in _FUERA_DEL_ESQUEMA:
                continue
            if k == "properties" and isinstance(v, dict):  # aquí las claves son nombres de campos: no se filtran
                out[k] = {p: resolver(sub) for p, sub in v.items()}
            elif k == "oneOf":
                out["anyOf"] = resolver(v)
            elif k == "const":
                out["enum"] = [v]
            elif k == "description" and isinstance(v, str):  # los docstrings llegan con sus saltos de línea
                out[k] = " ".join(v.split())
            else:
                out[k] = resolver(v)
        if "anyOf" in out and "default" in out and out["default"] is None:
            ramas = [r for r in out["anyOf"] if r != {"type": "null"}]
            if len(ramas) == 1:
                out = {**ramas[0], **{k: v for k, v in out.items() if k not in ("anyOf", "default")}}
        return out

    s = resolver(s)
    s.setdefault("type", "object")
    s.setdefault("properties", {})
    return s


# ───────────────────────────── API interna y errores ─────────────────────────────

_FUERA_DE_CLAVE = re.compile(r"[^A-Za-z0-9_.:-]")
DETALLE_PERMITIDO = ("campo", "motivo", "campos")


def clave_de(ctx: Contexto) -> str | None:
    """La Idempotency-Key de una escritura: la misma para el mismo `tool_use`. Sin `tool_use_id` no se manda ninguna:
    una clave compartida devolvería la respuesta guardada de otra escritura en vez de hacer esta."""
    if not ctx.tool_use_id:
        return None
    return _FUERA_DE_CLAVE.sub("_", f"agente.{ctx.conversacion_id}.{ctx.tool_use_id}")[:100]


def seguro(e: ErrorHerramienta) -> ErrorHerramienta:
    """El error de la API con solo lo que el modelo necesita para explicarlo: el mensaje, el código y algunos campos
    que no son datos de personas (un 422 de FastAPI vuelve como «mensaje en campo»)."""
    d = e.detalle
    detalle: Any = None
    if isinstance(d, dict):
        detalle = {k: d[k] for k in DETALLE_PERMITIDO if isinstance(d.get(k), (str, int, list))} or None
    elif isinstance(d, list):
        detalle = [f"{x.get('msg')} en {'.'.join(map(str, x.get('loc') or []))}" for x in d[:10]
                   if isinstance(x, dict)] or None
    return ErrorHerramienta(e.mensaje, e.codigo, estado=e.estado, detalle=detalle, fatal=e.fatal)


async def pedir(ctx: Contexto, metodo: str, ruta: str, *, params: dict | None = None, cuerpo: Any = None,
                clave: str | None = None, respuesta: bool = False) -> Any:
    plazo = ctx.plazo_escritura() if metodo != "GET" else None
    try:
        return await ctx.api.pedir(metodo, ruta, params=params, json_=cuerpo, clave=clave, respuesta=respuesta,
                                   plazo=plazo)
    except ErrorHerramienta as e:
        raise seguro(e) from None


def miles(n: Any) -> str:
    """12.345, como se escriben las cifras en Colombia."""
    return f"{n:,}".replace(",", ".") if isinstance(n, int) and not isinstance(n, bool) else str(n)


def _plural(n: int, uno: str, varios: str) -> str:
    return f"{miles(n)} {uno if n == 1 else varios}"


def exigir_permiso(ctx: Contexto, permiso: str, mensaje: str) -> None:
    """Para las herramientas que no pasan por la API (el nomenclátor, el mapa, las vistas): la misma tabla de
    permisos que usa `requiere`."""
    if not ctx.quien.puede(permiso):
        raise ErrorHerramienta(mensaje, "permiso", estado=403)


def _sensibles(db: Any) -> minimizar.Sensibles:
    return minimizar.sensibles_de(db)


def _nombres_de_necesidades(db: Any) -> frozenset[str]:
    """Los nombres de las etiquetas del grupo «necesidad» (la API manda las de cada asistente por nombre)."""
    return frozenset(e["nombre"] for e in db.etiquetas.find({"grupo": "necesidad"}, {"nombre": 1})
                     if isinstance(e.get("nombre"), str))


def _nombres_sensibles(db: Any) -> tuple[frozenset[int], frozenset[str]]:
    """Ids y nombres de las etiquetas sensibles (algunas rutas las mandan por nombre)."""
    s = minimizar.sensibles_de(db)
    nombres = {e.get("nombre") for e in db.etiquetas.find({"_id": {"$in": list(s.etiquetas)}}, {"nombre": 1})}
    return s.etiquetas, frozenset(n for n in nombres if isinstance(n, str))


# ───────────────────────────── Nomenclátor de lugares ─────────────────────────────

TIPOS_LUGAR = ("barrio", "sector", "vereda", "caserio", "centro_poblado", "corregimiento")
TipoLugar = Literal[TIPOS_LUGAR]
NOMBRE_TIPO = {"barrio": "barrio", "sector": "sector", "vereda": "vereda", "caserio": "caserío",
               "centro_poblado": "centro poblado", "corregimiento": "corregimiento"}
# La palabra escrita delante del nombre («vereda La Paz») dice qué tipo se quiso: primero el tipo exacto; si con ese
# nombre no hay ninguno, los parecidos que usa el nomenclátor para las direcciones (`TIPO_PALABRA`)
TIPO_EXACTO = {"BARRIO": {"barrio"}, "URBANIZACION": {"barrio"}, "VEREDA": {"vereda"}, "SECTOR": {"sector"},
               "CORREGIMIENTO": {"corregimiento"}, "CASERIO": {"caserio"}, "ASENTAMIENTO": {"barrio", "sector"},
               "CENTRO_POBLADO": {"centro_poblado"}}
AMPLIO = {**{k: set(v) for k, v in dirs.TIPO_PALABRA.items()}, "CENTRO_POBLADO": {"centro_poblado", "caserio"}}
# Los polígonos que viajan al mapa (`/api/mapa/capas`, capa `veredas`): los demás lugares son un punto
CON_POLIGONO_EN_MAPA = ("vereda", "corregimiento")
PROYECCION_LUGAR = {"nombre": 1, "tipo": 1, "zona": 1, "lat": 1, "lon": 1, "alias": 1, "padre": 1, "geom.type": 1}
UMBRAL_PARECIDO = 0.86  # el parecido mínimo del nomenclátor (`fuzz.ratio` ≥ 86) para aceptar un error de escritura


def clave_lugar(s: Any) -> str:
    """El nombre como lo compara el nomenclátor: mayúsculas sin tildes, sin signos y con «No. 1», «N 1» y «#1» como
    «# 1»."""
    a = re.sub(r"[^A-Z0-9# ]", " ", tx.limpiar(s))
    a = re.sub(r"\b(?:N|NO|NRO|NUMERO)\s+(?=\d)", "# ", a)
    a = re.sub(r"#\s*", "# ", a)
    return re.sub(r"\s+", " ", a).strip()


@dataclass(frozen=True)
class Lugar:
    id: int
    nombre: str
    tipo: str
    zona: str | None
    padre: str | None
    lat: float | None
    lon: float | None
    geom: bool

    @property
    def tiene_punto(self) -> bool:
        return self.lat is not None and self.lon is not None

    @property
    def poligono_en_mapa(self) -> bool:
        return self.geom and self.tipo in CON_POLIGONO_EN_MAPA

    def para_modelo(self) -> dict:
        return {"id": self.id, "nombre": self.nombre, "tipo": self.tipo, "zona": self.zona, "padre": self.padre,
                "tiene_punto": self.tiene_punto, "tiene_poligono": self.geom}

    def legible(self) -> str:
        return f"{self.nombre} ({NOMBRE_TIPO.get(self.tipo, self.tipo)} #{self.id})"


def _numero(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


@dataclass
class Busqueda:
    """Lo que dio buscar un nombre: los lugares que casan (con el tipo pedido), el elegido si no hay duda y por qué.

    `estado`: `unico`, `mismo_sitio` (homónimos de un mismo sitio: se elige el más preciso), `ambiguo` (lugares
    distintos con el mismo nombre: no se elige) o `ninguno`."""
    texto: str
    estado: str
    candidatos: list[Lugar] = field(default_factory=list)
    elegido: Lugar | None = None
    parecido: bool = False
    sugerencias: list[Lugar] = field(default_factory=list)


def orden_lugar(lg: Lugar) -> tuple:
    """El más preciso primero: con punto, luego por `PRIORIDAD` (barrio > sector > caserío y centro poblado > vereda >
    corregimiento), como elige el nomenclátor entre homónimos."""
    return (not lg.tiene_punto, -dirs.PRIORIDAD.get(lg.tipo, 0), lg.id)


MISMO_PUNTO = 0.001  # grados (unos 110 m): dos niveles del mismo sitio comparten el punto del nomenclátor


def _mismo_sitio(cs: list[Lugar]) -> bool:
    """¿Son el mismo sitio en distintos niveles? Misma zona y el mismo punto (a unos 100 m) en todos: así quedan en el
    nomenclátor el corregimiento, la vereda y el centro poblado de San Miguel del Tigre. «La Paz» (un barrio del casco
    sin punto y una vereda) no lo es."""
    if len({c.zona for c in cs}) != 1 or not all(c.tiene_punto for c in cs):
        return False
    p = cs[0]
    return all(abs(c.lat - p.lat) <= MISMO_PUNTO and abs(c.lon - p.lon) <= MISMO_PUNTO for c in cs)


class Nomenclatura:
    """El nomenclátor de lugares del panel (`db.lugares`) para resolver lo que nombra el modelo. Se arma en cada
    llamada (son unos cien lugares): así un lugar creado o corregido en Calidad de datos vale de inmediato."""

    def __init__(self, docs: list[dict]):
        self.por_id: dict[int, Lugar] = {}
        self.por_clave: dict[str, list[Lugar]] = {}
        para_nomenclator = []
        for d in docs:
            if not isinstance(d.get("_id"), int) or not d.get("nombre"):
                continue
            lg = Lugar(d["_id"], str(d["nombre"]), str(d.get("tipo") or ""), d.get("zona"), d.get("padre"),
                       _numero(d.get("lat")), _numero(d.get("lon")), bool(d.get("geom")))
            self.por_id[lg.id] = lg
            alias = tuple(a for a in d.get("alias") or () if isinstance(a, str))
            para_nomenclator.append(dirs.Lugar(lg.id, lg.nombre, lg.tipo, lg.zona or "", lg.lat, lg.lon, alias,
                                               lg.padre))
            # Aquí también los nombres que el nomenclátor de direcciones descarta (`NO_LUGAR`: «YONDO», «CASABE»):
            # en una dirección no dicen nada, pero quien los nombra en el chat sí quiere decir ese lugar
            for k in {clave_lugar(lg.nombre), *(clave_lugar(a) for a in alias)} - {""}:
                self.por_clave.setdefault(k, []).append(lg)
        self.nomenclator = dirs.Nomenclator(para_nomenclator)
        self._claves = list(self.por_clave)

    @classmethod
    def leer(cls, db: Any) -> "Nomenclatura":
        return cls(list(db.lugares.find({}, PROYECCION_LUGAR)))

    @staticmethod
    def _partir(texto: str) -> tuple[str, str | None, str]:
        """(nombre completo, palabra del tipo, nombre sin esa palabra): «la vereda La Paz» → («LA VEREDA LA PAZ»,
        «VEREDA», «LA PAZ»)."""
        completo = clave_lugar(texto)
        toks = completo.split()
        j = 1 if len(toks) > 2 and toks[0] in ("LA", "EL") and (toks[1] in dirs.LUGARES or toks[1] == "CENTRO") else 0
        if toks[j:j + 2] == ["CENTRO", "POBLADO"] and len(toks) > j + 2:
            return completo, "CENTRO_POBLADO", " ".join(toks[j + 2:])
        if len(toks) > j + 1 and dirs.LUGARES.get(toks[j]) not in (None, "FINCA"):
            return completo, dirs.LUGARES[toks[j]], " ".join(toks[j + 1:])
        return completo, None, completo

    @staticmethod
    def _por_tipo(cs: list[Lugar], tipo: str | None, palabra: str | None) -> list[Lugar]:
        if tipo:
            return [c for c in cs if c.tipo == tipo]
        if palabra:
            return ([c for c in cs if c.tipo in TIPO_EXACTO.get(palabra, ())]
                    or [c for c in cs if c.tipo in AMPLIO.get(palabra, ())])
        return cs

    def sugerir(self, texto: str, n: int = 5) -> list[Lugar]:
        """Los lugares de nombre más parecido (para cuando no se encontró ninguno). Con `fuzz.ratio`, que compara el
        nombre entero: los de parecido parcial premian alias cortos («GAITAN» para «MARGARITA»)."""
        _, _, resto = self._partir(texto)
        if len(resto) < 2 or not self._claves:
            return []
        out: dict[int, Lugar] = {}
        for clave, _, _ in process.extract(resto, self._claves, scorer=fuzz.ratio, limit=n * 3, score_cutoff=60):
            for lg in sorted(self.por_clave[clave], key=orden_lugar):
                out.setdefault(lg.id, lg)
        return list(out.values())[:n]

    def buscar(self, texto: str, tipo: str | None = None) -> Busqueda:
        completo, palabra, resto = self._partir(texto)
        cs = self.por_clave.get(completo) or (self.por_clave.get(resto) if resto else None) or []
        parecido = False
        if not cs and len(resto) >= 3:
            # Errores de escritura y abreviaturas («san migel del tigre», «San Miguel»), con el nomenclátor de las
            # direcciones; solo un parecido alto (el de su `fuzz.ratio`), nunca el parcial
            lg, _, conf = self.nomenclator.reconocer(dirs.leer(texto))
            if lg is not None and conf >= UMBRAL_PARECIDO:
                cs = self.por_clave.get(clave_lugar(lg.nombre)) or [self.por_id[lg.id]]
                parecido = True
        if not cs:
            return Busqueda(texto, "ninguno", sugerencias=self.sugerir(texto))
        filtrados = sorted({c.id: c for c in self._por_tipo(cs, tipo, palabra)}.values(), key=orden_lugar)
        if not filtrados:  # el nombre existe, pero no de ese tipo: se sugieren los que hay
            return Busqueda(texto, "ninguno", parecido=parecido, sugerencias=sorted(cs, key=orden_lugar))
        if len(filtrados) == 1:
            return Busqueda(texto, "unico", filtrados, filtrados[0], parecido)
        if _mismo_sitio(filtrados):
            return Busqueda(texto, "mismo_sitio", filtrados, filtrados[0], parecido)
        return Busqueda(texto, "ambiguo", filtrados, None, parecido)

    def por_id_o_error(self, lugar_id: int, tipo: str | None = None) -> Lugar:
        lg = self.por_id.get(lugar_id)
        if lg is None:
            raise ErrorHerramienta(f"No existe el lugar #{lugar_id} en el nomenclátor: búsquelo por nombre con "
                                   "buscar_lugar.", "no_existe", estado=404)
        if tipo and lg.tipo != tipo:
            raise ErrorHerramienta(f"El lugar #{lugar_id} es {lg.legible()}, no un {NOMBRE_TIPO.get(tipo, tipo)}.",
                                   "invalido", estado=422)
        return lg

    def resolver(self, texto: str | None = None, lugar_id: int | None = None, tipo: str | None = None) -> Lugar:
        """El lugar que se quiso decir, o `ErrorHerramienta` con los candidatos (ambiguo) o las sugerencias (no
        existe) para que el modelo pregunte o corrija."""
        if lugar_id is not None:
            return self.por_id_o_error(lugar_id, tipo)
        b = self.buscar(texto or "", tipo)
        if b.elegido is not None:
            return b.elegido
        raise error_de_busqueda(b, self)


def error_de_busqueda(b: Busqueda, nom: Nomenclatura) -> ErrorHerramienta:
    texto = minimizar.texto_libre(b.texto, 80)
    if b.estado == "ambiguo":
        return ErrorHerramienta(
            f"«{texto}» puede ser {len(b.candidatos)} lugares distintos de Yondó: pregunte a la persona cuál es y "
            "vuelva a llamar con su lugar_id (o con el tipo de lugar). No se hizo nada.", "ambiguo", estado=409,
            detalle={"candidatos": [c.para_modelo() for c in b.candidatos[:8]]})
    sugerencias = b.sugerencias or nom.sugerir(b.texto)
    return ErrorHerramienta(
        f"No encontré «{texto}» en el nomenclátor de lugares de Yondó" + (
            ": ¿quiso decir alguno de estos? Si es otro, se crea en Calidad de datos." if sugerencias else
            ". Si existe, se crea en Calidad de datos.") + " No se hizo nada.", "no_existe", estado=404,
        detalle={"sugerencias": [s.para_modelo() for s in sugerencias[:5]]} if sugerencias else None)


async def nomenclatura(ctx: Contexto) -> Nomenclatura:
    return await run_in_threadpool(Nomenclatura.leer, ctx.db)


class Perezosa:
    """El nomenclátor de un turno de herramienta, leído una sola vez y solo si hace falta."""

    def __init__(self, ctx: Contexto):
        self.ctx, self._nom = ctx, None

    async def __call__(self) -> Nomenclatura:
        if self._nom is None:
            self._nom = await nomenclatura(self.ctx)
        return self._nom


# ───────────────────────────── Filtros ─────────────────────────────

TIPOS_DOCUMENTO = tuple(modelo.TIPOS_DOCUMENTO)
FALTAN = ("cedula", "telefono", "sexo", "edad", "lugar", "puesto", "mesa", "direccion", "puesto_mesa")
# Banderas que la API lee como 0/1 en los dos sentidos, y las que solo valen con 1
BANDERAS = ("con_cedula", "con_telefono", "varios_telefonos", "asistio", "menor", "cedula_verificada", "con_puesto",
            "con_mesa", "abordado", "contactado")
SOLO_SI = ("tratables", "proximo_vencido")
NO_SON_FILTRO = ("lugar", "tipo_lugar")


class FiltrosBase(_Entrada):
    """Los filtros de Habitantes (`filtros.Filtros`) que el asistente puede usar, con los valores que acepta la API.

    Fuera a propósito: `q` (contar por texto o por números dejaría reconstruir una cédula, un teléfono o un correo
    enmascarados), las listas de origen, los líderes y la base con cédula (revelan afiliación política), el régimen de
    salud y las etiquetas sensibles (datos sensibles), y `ids`, `poligono`, `area_id` y `mios`, que tienen otra vía."""
    lugar: str | None = Field(None, min_length=2, max_length=80,
                              description="Barrio o vereda por nombre; el servidor lo busca en el nomenclátor")
    tipo_lugar: TipoLugar | None = Field(None, description="Tipo del lugar, si el nombre se repite (con `lugar`)")
    lugar_id: IdOCero | None = Field(None, description="Id del barrio o vereda (buscar_lugar); 0 = sin barrio ni "
                                                       "vereda reconocidos")
    zona: Literal["urbana", "rural", "sin"] | None = Field(None, description="urbana, rural o sin zona")
    fuente: Literal["tramites", "reunion", "manual", "planilla"] | None = Field(None, description="De dónde llegó")
    etiqueta: Id | None = Field(None, description="Necesidad, interés o rol (id de catalogos)")
    con_cedula: bool | None = None
    con_telefono: bool | None = Field(None, description="Con algún teléfono usable")
    varios_telefonos: bool | None = None
    telefono_estado: Literal[tuple(modelo.ESTADOS_TELEFONO)] | None = Field(None, description="Algún número así")
    precision: Literal["exacta", "aproximada", "ubicada", "sin"] | None = Field(
        None, description="Ubicación: exacta (dirección o punto), aproximada (barrio o vereda), ubicada (cualquiera, "
                          "lo que se ve en el mapa) o sin ubicación")
    reunion_id: Id | None = Field(None, description="Asistentes de esa reunión")
    asistio: bool | None = Field(None, description="Asistió (true) o no (false) a alguna reunión")
    consentimiento: Literal["si", "no", "pendiente", "por_confirmar"] | None = Field(
        None, description="Autorización de datos; por_confirmar = «sí» de planilla sin confirmar")
    tratables: bool | None = Field(None, description="true: sin quienes no autorizaron")
    sexo: Literal["F", "M", "N", "sin"] | None = Field(None, description="F mujer, M hombre, N prefiere no decir")
    edad_min: int | None = Field(None, ge=0, le=130)
    edad_max: int | None = Field(None, ge=0, le=130)
    menor: bool | None = Field(None, description="Menores de edad (true) o no (false)")
    tipo_documento: Literal[TIPOS_DOCUMENTO] | None = None
    cedula_verificada: bool | None = None
    completitud_max: int | None = Field(None, ge=0, le=100, description="Ficha completa hasta este porcentaje")
    puesto_id: IdOCero | None = Field(None, description="Puesto de votación (id de catalogos); 0 = sin puesto")
    con_puesto: bool | None = None
    con_mesa: bool | None = None
    votacion_estado: Literal[tuple(modelo.ESTADOS_VOTACION)] | None = None
    donde: Literal[tuple(modelo.DONDE_VOTA)] | None = Field(None, description="Dónde vota")
    abordado: bool | None = Field(None, description="Con algún acercamiento registrado")
    contactado: bool | None = Field(None, description="Con algún contacto efectivo")
    abordaje_estado: Literal[tuple(modelo.ESTADOS_ABORDAJE)] | None = None
    ultimo_resultado: Literal[tuple(modelo.RESULTADOS)] | None = Field(None, description="Del último acercamiento")
    sin_acercamiento_dias: int | None = Field(None, ge=0, le=3650, description="Sin acercamiento en estos días")
    proximo_vencido: bool | None = Field(None, description="true: con un «volver a llamar» ya vencido")
    canal_autorizado: Literal[tuple(modelo.CANALES_AUTORIZACION)] | None = Field(
        None, description="Autorizó ese canal de contacto")
    situacion: Literal["todas", "vigentes", "no_vigentes", "activa", "fallecida", "no_reside"] | None = Field(
        None, description="vigentes = activas; por defecto todas")
    requiere_actualizacion: bool | None = Field(None, description="Con un pedido de actualización pendiente (o sin)")
    motivos_actualizacion: list[Literal[tuple(modelo.MOTIVOS_ACTUALIZACION)]] | None = Field(
        None, min_length=1, max_length=len(modelo.MOTIVOS_ACTUALIZACION),
        description="Pedido de actualización por alguno de estos motivos")
    estado_civil: Literal[(*modelo.ESTADOS_CIVILES, "sin")] | None = None
    nivel_educativo: Literal[(*modelo.NIVELES, "sin")] | None = None
    situacion_laboral: Literal[(*modelo.SITUACIONES_LABORALES, "sin")] | None = None
    tenencia_vivienda: Literal[(*modelo.TENENCIAS, "sin")] | None = None
    estrato: int | None = Field(None, ge=0, le=6)
    creado_por: IdOCero | None = Field(None, description="Registradas por ese usuario (uid; 0 = el administrador)")
    actualizado_por: IdOCero | None = Field(None, description="Actualizadas por ese usuario (uid)")
    faltan: list[Literal[FALTAN]] | None = Field(
        None, min_length=1, max_length=len(FALTAN),
        description="Datos que les faltan (todos los de la lista); puesto_mesa = puesto o mesa")

    @field_validator("faltan", "motivos_actualizacion")
    @classmethod
    def _unicos(cls, v):
        return _sin_repetidos(v)

    @model_validator(mode="after")
    def _coherentes(self):
        if self.lugar is not None and self.lugar_id is not None:
            raise ValueError("Use lugar (nombre) o lugar_id, no los dos")
        if self.tipo_lugar is not None and self.lugar is None:
            raise ValueError("tipo_lugar acompaña a lugar (el nombre)")
        if self.edad_min is not None and self.edad_max is not None and self.edad_min > self.edad_max:
            raise ValueError("edad_min no puede ser mayor que edad_max")
        if self.requiere_actualizacion is not None and self.motivos_actualizacion:
            raise ValueError("Use requiere_actualizacion o motivos_actualizacion, no los dos")
        return self


class FiltrosIndicadores(FiltrosBase):
    area_id: Id | None = Field(None, description="Área de trabajo dibujada en el mapa (zona)")


def params_de(f: FiltrosBase | None, lugar_id: int | None = None) -> dict[str, str]:
    """Los filtros como parámetros de la API y de la URL del panel (los mismos de `filtros_query`), como texto."""
    if f is None:
        return {}
    out: dict[str, str] = {}
    for k, v in f.model_dump(exclude_none=True).items():
        if k in NO_SON_FILTRO:
            continue
        if k in BANDERAS:
            out[k] = "1" if v else "0"
        elif k in SOLO_SI:
            if v:
                out[k] = "1"
        elif k == "faltan":
            for campo in v:
                out[f"sin_{campo}"] = "1"
        elif k == "requiere_actualizacion":
            out[k] = "1" if v else "0"
        elif k == "motivos_actualizacion":
            out["requiere_actualizacion"] = ",".join(v)
        else:
            out[k] = str(v)
    if lugar_id is not None:
        out["lugar_id"] = str(lugar_id)
    return out


def _exigir_etiqueta(db: Any, eid: int) -> None:
    if db.etiquetas.find_one({"_id": eid}, {"_id": 1}) is None:
        raise ErrorHerramienta(f"No existe la etiqueta #{eid}: consulte los catálogos.", "no_existe", estado=404)
    if eid in minimizar.sensibles_de(db).etiquetas:
        raise ErrorHerramienta("Esa etiqueta revela un dato sensible: el asistente no filtra ni cuenta por ella.",
                               "permiso", estado=403)


async def preparar_filtros(ctx: Contexto, f: FiltrosBase | None,
                           nom: Callable[[], Awaitable[Nomenclatura]]) -> tuple[dict[str, str], dict[str, Any]]:
    """(parámetros para la API y el navegador, los mismos legibles para el modelo). Resuelve el lugar por nombre y
    rechaza una etiqueta sensible o inexistente antes de contar nada."""
    if f is None:
        return {}, {}
    lugar = None
    if f.lugar is not None:
        lugar = (await nom()).resolver(f.lugar, tipo=f.tipo_lugar)
    elif f.lugar_id:  # 0 = «sin barrio ni vereda»: no es un lugar del nomenclátor
        lugar = (await nom()).por_id_o_error(f.lugar_id)
    if f.etiqueta is not None:
        await run_in_threadpool(_exigir_etiqueta, ctx.db, f.etiqueta)
    params = params_de(f, lugar.id if lugar else None)
    legible: dict[str, Any] = dict(params)
    if lugar is not None:
        legible["lugar_id"] = lugar.legible()
    return params, legible


# ───────────────────────────── indicadores ─────────────────────────────

class IndicadoresEntrada(_Entrada):
    filtros: FiltrosIndicadores | None = Field(None, description="Filtros de Habitantes; sin filtros, toda la base")
    alcance: Literal["tablero", "zona"] = Field(
        "tablero", description="tablero (toda la base o los filtros) o zona (un área o polígono: menos de 10 personas "
                               "no dan desgloses)")


# Lo que de los indicadores nunca llega al modelo: los líderes y la base con cédula revelan afiliación política
KPI_FUERA = frozenset({"lideres", "en_ambas_bases"})
CAMPOS_FUERA = frozenset({"regimen_salud"})


def _dict_numeros(v: Any) -> dict:
    return {str(k): n for k, n in v.items() if isinstance(n, (int, float)) and not isinstance(n, bool)} \
        if isinstance(v, dict) else {}


def _lista(v: Any) -> list[dict]:
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def compactar_indicadores(d: dict, sens_ids: frozenset[int], sens_nombres: frozenset[str]) -> dict:
    """La respuesta de `GET /api/indicadores` reducida a lo que el modelo necesita: los totales y los rankings
    principales (los 10 primeros). Nunca `listas`, `sensibles`, `actividad`, `fuentes`, `demografia` (trae el régimen
    de salud), los líderes ni la base con cédula."""
    out: dict[str, Any] = {}
    if isinstance(d.get("area"), dict):
        out["area"] = {k: d["area"].get(k) for k in ("m2", "perimetro_m")}
    if isinstance(d.get("sin_ubicacion"), int):
        out["sin_ubicacion"] = d["sin_ubicacion"]
    if d.get("pocas"):
        out.update(pocas=True, kpi={"personas": "<10"},
                   nota="La zona tiene menos de 10 personas: el panel no da desgloses para no identificar a nadie.")
        return out
    kpi = d.get("kpi") if isinstance(d.get("kpi"), dict) else {}
    out["kpi"] = {k: v for k, v in kpi.items() if k not in KPI_FUERA}
    for k in ("zonas", "precision", "abordaje", "autorizacion", "rangos_edad", "sexo"):
        if isinstance(d.get(k), dict):
            out[k] = _dict_numeros(d[k])
    out["completitud"] = [{"rango": x.get("rango"), "n": x.get("n")} for x in _lista(d.get("completitud"))]
    out["lugares"] = [{k: x.get(k) for k in ("id", "nombre", "tipo", "n")} for x in _lista(d.get("lugares"))[:TOP]]
    out["necesidades"] = [{k: x.get(k) for k in ("id", "nombre", "grupo", "n")} for x in _lista(d.get("necesidades"))
                          if x.get("id") not in sens_ids and x.get("nombre") not in sens_nombres][:TOP]
    puestos = _lista(d.get("puestos"))
    out["puestos"] = [{k: x.get(k) for k in ("id", "codigo", "nombre", "n", "con_mesa")} for x in puestos[:TOP]]
    if len(puestos) > TOP:
        out["puestos_total"] = len(puestos)
    for k in ("sin_puesto", "puesto_sin_catalogo"):
        if isinstance(d.get(k), int):
            out[k] = d[k]
    out["cobertura_cedula"] = [{k: x.get(k) for k in ("id", "nombre", "personas", "sin_cedula", "con_cedula_pct")}
                               for x in _lista(d.get("cobertura_cedula"))[:TOP]]
    out["completitud_campos"] = [{k: x.get(k) for k in ("campo", "etiqueta", "con")}
                                 for x in _lista(d.get("completitud_campos")) if x.get("campo") not in CAMPOS_FUERA]
    if isinstance(d.get("reuniones"), list):
        out["reuniones_recientes"] = [{"id": x.get("id"), "titulo": minimizar.texto_libre(x.get("titulo"), 120),
                                       "fecha": x.get("fecha"), "asistentes": x.get("n"),
                                       "ruta": f"/reuniones/{x.get('id')}"} for x in _lista(d["reuniones"])]
    return out


SIN_NO_AUTORIZARON = ("No cuentan a quienes no autorizaron el tratamiento de sus datos: de ellos el asistente solo "
                      "sabe quiénes son. Para saber cuántos son, use buscar_personas con consentimiento «no» (y, si "
                      "hace falta, su barrio o vereda): su total.")
NO_AUTORIZO_EN_INDICADORES = ("Los indicadores no cuentan a quienes no autorizaron el tratamiento de sus datos: de "
                              "ellos solo se sabe quiénes son. Use buscar_personas con consentimiento «no» (y, si "
                              "hace falta, su barrio o vereda): su total dice cuántos son.")


async def _indicadores(ctx: Contexto, a: IndicadoresEntrada) -> Resultado:
    # Siempre sin quienes no autorizaron: un desglose de un grupo pequeño (una vereda, un filtro que deja a una sola
    # persona) diría su sexo, su edad o sus necesidades, y restar dos conteos con y sin ellos, también
    if a.filtros is not None and a.filtros.consentimiento == "no":
        raise ErrorHerramienta(NO_AUTORIZO_EN_INDICADORES, "invalido", estado=422)
    params, legible = await preparar_filtros(ctx, a.filtros, Perezosa(ctx))  # con area_id, si lo trae
    d = await pedir(ctx, "GET", "/api/indicadores", params={**params, "tratables": "1", "alcance": a.alcance})
    sens_ids, sens_nombres = await run_in_threadpool(_nombres_sensibles, ctx.db)
    out = {"alcance": a.alcance, "filtros": legible, **compactar_indicadores(d if isinstance(d, dict) else {},
                                                                              sens_ids, sens_nombres)}
    if isinstance(out.get("autorizacion"), dict):
        out["autorizacion"].pop("no", None)  # siempre 0 aquí: no es que nadie haya dicho que no
    out["nota_autorizacion"] = SIN_NO_AUTORIZARON
    n = (out.get("kpi") or {}).get("personas")
    resumen = "Zona con menos de 10 personas" if out.get("pocas") else (
        _plural(n, "persona", "personas") if isinstance(n, int) else "Indicadores")
    return Resultado(out, resumen)


# ───────────────────────────── Reuniones ─────────────────────────────

def _texto(v: Any, n: int) -> Any:
    return minimizar.texto_libre(v, n) if isinstance(v, str) and v else None


def _fila_reunion(x: dict) -> dict:
    return {"id": x.get("id"), "titulo": _texto(x.get("titulo"), 160), "fecha": x.get("fecha"),
            "hora": x.get("hora"), "tema": _texto(x.get("tema"), 160), "lugar": _texto(x.get("lugar"), 120),
            "asistentes": x.get("asistentes"), "nuevos": x.get("nuevos"),
            "abierta_a_equipo": x.get("abierta_a_equipo"), "propia": x.get("propia"),
            "ruta": f"/reuniones/{x.get('id')}"}


SIN_NO_AUTORIZARON_REUNION = ("Los asistentes y las personas nuevas no cuentan a quienes no autorizaron el "
                              "tratamiento de sus datos, ni se listan: que asistieron es un dato suyo. En Reuniones "
                              "del panel sí salen.")


async def _reuniones(ctx: Contexto) -> tuple[list[dict], int | None]:
    """Las reuniones que el rol puede ver (más recientes primero) y, para el planillero, cuántas otras hay. Sus conteos
    de asistentes y de personas nuevas son sin quienes no autorizaron (`tratables`): restando dos conteos, o
    comparando con ver_reunion, se sabría que alguien que no se lista asistió."""
    r = await pedir(ctx, "GET", "/api/reuniones", params={"tratables": "1"}, respuesta=True)
    try:
        datos = r.json()
    except ValueError:
        raise ErrorHerramienta("La API del panel respondió algo que no es JSON.", "error") from None
    ajenas = r.headers.get("x-reuniones-ajenas")
    return _lista(datos), (int(ajenas) if ajenas and ajenas.isdigit() else None)


class ListarReunionesEntrada(_Entrada):
    desde: Fecha | None = Field(None, description="Desde esta fecha (AAAA-MM-DD), incluida")
    hasta: Fecha | None = Field(None, description="Hasta esta fecha (AAAA-MM-DD), incluida")
    q: str | None = Field(None, min_length=2, max_length=80, description="Palabras del título, el tema o el lugar")
    solo_propias: bool = Field(False, description="true: solo las que creó usted")
    limite: int = Field(20, ge=1, le=50, description="Cuántas mostrar (las más recientes)")

    @model_validator(mode="after")
    def _rango(self):
        if self.desde and self.hasta and self.desde > self.hasta:
            raise ValueError("desde no puede ser posterior a hasta")
        return self


async def _listar_reuniones(ctx: Contexto, a: ListarReunionesEntrada) -> Resultado:
    reus, ajenas = await _reuniones(ctx)
    palabras = tx.limpiar(a.q).split() if a.q else []
    elegidas = []
    for x in reus:
        f = str(x.get("fecha") or "")
        if (a.desde and f < a.desde) or (a.hasta and f > a.hasta) or (a.solo_propias and not x.get("propia")):
            continue
        if palabras:
            texto = tx.limpiar(" ".join(str(x.get(k) or "") for k in ("titulo", "tema", "lugar")))
            if not all(p in texto for p in palabras):
                continue
        elegidas.append(x)
    filas = [_fila_reunion(x) for x in elegidas[:a.limite]]
    out: dict[str, Any] = {"total": len(elegidas), "mostradas": len(filas), "reuniones": filas,
                           "nota_autorizacion": SIN_NO_AUTORIZARON_REUNION}
    if ajenas:
        out["ajenas"] = ajenas
        out["nota"] = f"Hay {_plural(ajenas, 'reunión', 'reuniones')} de otras personas del equipo que su rol no ve."
    if len(elegidas) > len(filas):
        out["aviso"] = "Hay más reuniones: acote por fechas o por texto, o pida un límite mayor."
    return Resultado(out, _plural(len(elegidas), "reunión", "reuniones"))


class VerReunionEntrada(_Entrada):
    reunion_id: Id
    asistentes: int = Field(30, ge=0, le=100, description="Cuántos asistentes listar. 0 = solo los datos básicos y "
                                                          "los conteos, sin consultar a ninguna persona")


async def _resumen_reunion(ctx: Contexto, rid: int) -> Resultado:
    """La reunión sin sus asistentes, desde la lista del rol: ver el detalle registra como consultados a todos sus
    asistentes (el tope diario del planillero), y para «cuándo fue» o «cuántos vinieron» no hace falta."""
    reus, _ = await _reuniones(ctx)
    x = next((x for x in reus if x.get("id") == rid), None)
    if x is None:
        raise ErrorHerramienta(f"La reunión #{rid} no existe o su rol no la ve (el planillero ve las suyas y las "
                               "abiertas al equipo).", "no_existe", estado=404)
    # En la lista, «asistentes» es el conteo: aquí va como asistentes_total, y la lista de personas, vacía
    out = {**_fila_reunion(x), "asistentes_total": x.get("asistentes"), "asistentes": [],
           "nota": "Sin consultar personas: para la descripción, los compromisos, las necesidades y los asistentes, "
                   "pida asistentes mayor que 0.", "nota_autorizacion": SIN_NO_AUTORIZARON_REUNION}
    return Resultado({k: v for k, v in out.items() if v is not None},
                     _plural(int(x.get("asistentes") or 0), "asistente", "asistentes"))


async def _ver_reunion(ctx: Contexto, a: VerReunionEntrada) -> Resultado:
    if a.asistentes == 0:
        return await _resumen_reunion(ctx, a.reunion_id)
    try:
        d = await pedir(ctx, "GET", f"/api/reuniones/{a.reunion_id}")
    except ErrorHerramienta as e:
        if e.estado == 404:
            raise ErrorHerramienta(f"No existe la reunión #{a.reunion_id}.", "no_existe", estado=404) from None
        raise
    d = d if isinstance(d, dict) else {}
    # Quien no autorizó no se lista (que asistió es un dato suyo, como lo sería filtrar por reunion_id en
    # buscar_personas), ni se cuenta, ni suma en las necesidades: la API se las cuenta al administrador. Un total o un
    # aviso con ellos diría que alguien que no se lista vino
    tratables = [x for x in _lista(d.get("asistentes")) if x.get("consentimiento") != "no"]
    filas = minimizar.filas(tratables[:a.asistentes])
    _, sens_nombres = await run_in_threadpool(_nombres_sensibles, ctx.db)  # la API manda las necesidades por nombre
    de_necesidad = await run_in_threadpool(_nombres_de_necesidades, ctx.db)
    necesidades = Counter(n for x in tratables for n in dict.fromkeys(x.get("etiquetas") or [])
                          if n in de_necesidad and n not in sens_nombres)
    lugar = d.get("lugar_nombre") or d.get("lugar_texto")
    out = {"id": d.get("id", a.reunion_id), "titulo": _texto(d.get("titulo"), 160), "fecha": d.get("fecha"),
           "hora": d.get("hora"), "lugar": _texto(lugar, 120), "lugar_id": d.get("lugar_id"),
           "sitio": _texto(d.get("lugar_texto"), 160) if d.get("lugar_texto") != d.get("lugar_nombre") else None,
           "tema": _texto(d.get("tema"), 160), "descripcion": _texto(d.get("descripcion"), 800),
           "compromisos": _texto(d.get("compromisos"), 800), "abierta_a_equipo": d.get("abierta_a_equipo"),
           "propia": d.get("propia"), "asistentes_total": len(tratables), "asistentes": filas,
           "necesidades": [{"nombre": n, "n": c} for n, c in necesidades.most_common(TOP)],
           "ruta": f"/reuniones/{d.get('id', a.reunion_id)}", "nota_autorizacion": SIN_NO_AUTORIZARON_REUNION}
    if len(tratables) > len(filas):
        out["aviso"] = (f"Se muestran {len(filas)} de {len(tratables)} asistentes: para ver más, pida un número mayor "
                        "en asistentes.")
    out = {k: v for k, v in out.items() if v is not None}
    return Resultado(out, _plural(len(tratables), "asistente", "asistentes"), personas=minimizar.ids_de(filas))


def _fecha_legible(f: str | None) -> str:
    try:
        d = date.fromisoformat(str(f))
    except ValueError:
        return str(f or "")
    dias = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
    meses = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
             "noviembre", "diciembre")
    return f"{dias[d.weekday()]} {d.day} de {meses[d.month - 1]} de {d.year}"


class CrearReunionEntrada(_Entrada):
    titulo: str = Field(..., min_length=3, max_length=160)
    fecha: Fecha = Field(..., description="AAAA-MM-DD; puede ser pasada (una reunión que ya ocurrió)")
    hora: Hora | None = None
    lugar: str | None = Field(None, min_length=2, max_length=80, description="Barrio o vereda por nombre")
    tipo_lugar: TipoLugar | None = Field(None, description="Tipo del lugar, si el nombre se repite")
    lugar_id: Id | None = Field(None, description="Id del barrio o vereda (buscar_lugar)")
    sitio: str | None = Field(None, min_length=2, max_length=160, description="Dónde exactamente: caseta comunal, "
                                                                             "escuela, casa de…")
    tema: str | None = Field(None, max_length=160)
    descripcion: str | None = Field(None, max_length=4000)
    abierta_a_equipo: bool | None = Field(None, description="Que todo el equipo la vea (solo administrador y "
                                                            "coordinador)")

    @field_validator("titulo")
    @classmethod
    def _titulo(cls, v):
        if len(re.sub(r"[^A-Za-zÁÉÍÓÚÑáéíóúñ]", "", v)) < 3:
            raise ValueError("El título necesita al menos 3 letras")
        return v

    @model_validator(mode="after")
    def _lugar(self):
        if self.lugar is not None and self.lugar_id is not None:
            raise ValueError("Use lugar (nombre) o lugar_id, no los dos")
        if self.tipo_lugar is not None and self.lugar is None:
            raise ValueError("tipo_lugar acompaña a lugar (el nombre)")
        return self


async def _lugar_de_reunion(ctx: Contexto, a: CrearReunionEntrada) -> Lugar | None:
    if a.lugar is None and a.lugar_id is None:
        return None
    return (await nomenclatura(ctx)).resolver(a.lugar, a.lugar_id, a.tipo_lugar)


def _exigir_apertura(ctx: Contexto, a: CrearReunionEntrada) -> None:
    if a.abierta_a_equipo is not None and not ctx.quien.administra:
        raise ErrorHerramienta("Solo el administrador y el coordinador abren una reunión al equipo: créela sin "
                               "abierta_a_equipo.", "permiso", estado=403)


def _misma(db: Any, uid: Any, a: CrearReunionEntrada, lugar: Lugar | None) -> dict | None:
    """La reunión de `uid` que es la misma que se pide (de la base: no es de personas), o None. Cuenta todo lo que la
    tarjeta muestra y distingue a una reunión de otra: el título (sin tildes ni mayúsculas), la fecha, la hora, el
    barrio o vereda, el sitio (sin sitio, la API guarda el nombre del lugar) y el tema. Dos reuniones del mismo día y
    título en sitios distintos son dos; la misma llamada repetida (un reintento) encuentra la que ya creó."""
    sitio = a.sitio or (lugar.nombre if lugar else None)
    pedida = (tx.limpiar(a.titulo), a.hora or None, lugar.id if lugar else None, tx.limpiar(sitio), tx.limpiar(a.tema))
    for x in db.reuniones.find({"creado_por_uid": uid, "fecha": a.fecha},
                               {"titulo": 1, "fecha": 1, "hora": 1, "lugar_id": 1, "lugar_texto": 1, "tema": 1}):
        if (tx.limpiar(x.get("titulo")), x.get("hora") or None, x.get("lugar_id") or None,
                tx.limpiar(x.get("lugar_texto")), tx.limpiar(x.get("tema"))) == pedida:
            return {"id": x["_id"], "titulo": x.get("titulo"), "fecha": x.get("fecha"), "hora": x.get("hora"),
                    "tema": x.get("tema"), "lugar": x.get("lugar_texto"), "propia": True}
    return None


async def _igual_existente(ctx: Contexto, a: CrearReunionEntrada, lugar: Lugar | None) -> dict | None:
    return await run_in_threadpool(_misma, ctx.db, ctx.quien.uid, a, lugar)


async def _preparar_reunion(ctx: Contexto, a: CrearReunionEntrada) -> Confirmacion:
    _exigir_apertura(ctx, a)
    lugar = await _lugar_de_reunion(ctx, a)
    ya = await _igual_existente(ctx, a, lugar)
    if ya is not None:
        raise ErrorHerramienta(f"Ya existe una reunión suya igual: «{_texto(ya.get('titulo'), 160)}» del "
                               f"{ya.get('fecha')} (#{ya.get('id')}). Use esa; no se crea otra.", "duplicada",
                               estado=409, detalle={"id": ya.get("id"), "ruta": f"/reuniones/{ya.get('id')}"})
    detalle = [("Título", a.titulo), ("Fecha", _fecha_legible(a.fecha)), ("Hora", a.hora or "Sin hora"),
               ("Barrio o vereda", lugar.legible() if lugar else "Sin lugar del nomenclátor")]
    for etiqueta, v in (("Sitio", a.sitio), ("Tema", a.tema), ("Descripción", a.descripcion)):
        if v:
            detalle.append((etiqueta, v))
    if ctx.quien.administra:
        detalle.append(("Abierta al equipo", "Sí" if a.abierta_a_equipo else "No"))
    aviso = "Queda en Reuniones a su nombre; después se registran los asistentes."
    if a.fecha < modelo.hoy_local().isoformat():
        aviso += " La fecha ya pasó: se registra como una reunión que ya ocurrió."
    return Confirmacion("Crear una reunión", detalle, aviso)


async def _crear_reunion(ctx: Contexto, a: CrearReunionEntrada) -> Resultado:
    _exigir_apertura(ctx, a)
    lugar = await _lugar_de_reunion(ctx, a)
    # La API no tiene idempotencia al crear reuniones: si esta misma llamada ya la creó (un reintento), no se repite.
    # Una igual de antes de la tarjeta no puede ser: la tarjeta no se habría armado («duplicada»)
    ya = await _igual_existente(ctx, a, lugar)
    if ya is not None:
        return Resultado({"ok": True, "ya_existia": True, "reunion": _fila_reunion(ya)},
                         f"Ya existía la reunión #{ya.get('id')}", acciones=[{"tipo": "recargar"}])
    cuerpo = {"titulo": a.titulo, "fecha": a.fecha, "hora": a.hora, "lugar_id": lugar.id if lugar else None,
              "lugar_texto": a.sitio, "tema": a.tema, "descripcion": a.descripcion,
              "abierta_a_equipo": a.abierta_a_equipo}
    d = await pedir(ctx, "POST", "/api/reuniones", cuerpo={k: v for k, v in cuerpo.items() if v is not None},
                    clave=clave_de(ctx))
    d = d if isinstance(d, dict) else {}
    rid = d.get("id")
    reunion = {"id": rid, "titulo": _texto(d.get("titulo"), 160), "fecha": d.get("fecha"), "hora": d.get("hora"),
               "lugar": _texto(d.get("lugar_nombre") or d.get("lugar_texto"), 120), "ruta": f"/reuniones/{rid}"}
    return Resultado({"ok": True, "ya_existia": False, "reunion": reunion}, f"Reunión #{rid} creada",
                     acciones=[{"tipo": "recargar"}])


class AgregarAsistenteEntrada(_Entrada):
    reunion_id: Id
    persona_id: Id
    rol: str | None = Field(None, min_length=2, max_length=60, description="Su papel en la reunión, si lo dijeron")
    nota: str | None = Field(None, min_length=2, max_length=1000, description="Una nota de su asistencia")


async def _reunion_visible(ctx: Contexto, rid: int) -> dict:
    """La reunión en la lista del rol (sin registrar lecturas de sus asistentes, como sí haría verla entera)."""
    reus, _ = await _reuniones(ctx)
    x = next((x for x in reus if x.get("id") == rid), None)
    if x is None:
        raise ErrorHerramienta(f"La reunión #{rid} no existe o su rol no la ve (el planillero ve las suyas y las "
                               "abiertas al equipo).", "no_existe", estado=404)
    return x


async def _persona_tratable(ctx: Contexto, pid: int) -> dict:
    """La ficha del rol (cuenta como lectura: es la persona que se va a registrar). De quien no autorizó, el asistente
    no registra nada: sus datos no se le pasan al modelo, y escribirlos sería tratarlos a través de él."""
    try:
        d = await pedir(ctx, "GET", f"/api/personas/{pid}")
    except ErrorHerramienta as e:
        if e.estado == 404:
            raise ErrorHerramienta(f"No existe la ficha #{pid} (o se suprimió).", "no_existe", estado=404) from None
        raise
    if not isinstance(d, dict) or "id" not in d:
        raise ErrorHerramienta("La API del panel devolvió una ficha vacía.", "error")
    if d.get("consentimiento") == "no":
        raise ErrorHerramienta("Esta persona no autorizó el tratamiento de sus datos: el asistente no la registra en "
                               "reuniones. Hágalo desde la reunión en el panel si corresponde.", "no_contactable",
                               estado=409, detalle={"motivo": "no_autorizo"})
    return d


def _ya_asiste(d: dict, rid: int) -> bool:
    return any(isinstance(r, dict) and r.get("id") == rid for r in d.get("reuniones") or [])


async def _preparar_asistente(ctx: Contexto, a: AgregarAsistenteEntrada) -> Confirmacion:
    reu = await _reunion_visible(ctx, a.reunion_id)
    d = await _persona_tratable(ctx, a.persona_id)
    ya = _ya_asiste(d, a.reunion_id)
    if ya and not (a.rol or a.nota):
        raise ErrorHerramienta("Esa persona ya está registrada como asistente de esa reunión.", "ya_registrada",
                               estado=409)
    detalle = [("Reunión", f"{reu.get('titulo')} ({_fecha_legible(reu.get('fecha'))}) #{a.reunion_id}"),
               ("Persona", f"{d.get('nombre') or 'Persona sin nombre'} (#{a.persona_id})")]
    if a.rol:
        detalle.append(("Rol en la reunión", a.rol))
    if a.nota:
        detalle.append(("Nota", a.nota))
    if ya:
        return Confirmacion("Actualizar un asistente", detalle, "Ya estaba registrada: solo cambia su rol o su nota.")
    return Confirmacion("Registrar un asistente", detalle,
                        "Asistir cuenta como un acercamiento en su ficha (contestó, en reunión).")


async def _agregar_asistente(ctx: Contexto, a: AgregarAsistenteEntrada) -> Resultado:
    await _persona_tratable(ctx, a.persona_id)  # pudo cambiar su autorización entre la tarjeta y la aprobación
    cuerpo = {"persona_id": a.persona_id, "rol": a.rol, "nota": a.nota}
    d = await pedir(ctx, "POST", f"/api/reuniones/{a.reunion_id}/asistentes",
                    cuerpo={k: v for k, v in cuerpo.items() if v is not None}, clave=clave_de(ctx))
    d = d if isinstance(d, dict) else {}
    asistentes = _lista(d.get("asistentes"))
    fila = next((minimizar.fila(x) for x in asistentes if x.get("id") == a.persona_id), {"id": a.persona_id})
    persona = {k: fila[k] for k in ("id", "nombre", "consentimiento") if k in fila}
    tratables = sum(1 for x in asistentes if x.get("consentimiento") != "no")  # como en ver_reunion
    return Resultado({"ok": True, "reunion": {"id": d.get("id", a.reunion_id), "titulo": _texto(d.get("titulo"), 160),
                                              "fecha": d.get("fecha"), "asistentes_total": tratables,
                                              "ruta": f"/reuniones/{a.reunion_id}"},
                      "persona": persona}, "Asistente registrado", acciones=[{"tipo": "recargar"}],
                     personas={a.persona_id})


# ───────────────────────────── pendientes ─────────────────────────────

class SinEntrada(_Entrada):
    pass


POR_VENCER_DIAS = 3


def _que_trabajo(quien: Any) -> str:
    """Qué cuenta la insignia «trabajo» para cada rol (`GET /api/insignias`)."""
    if quien.administra:
        return "fichas de toda la base con un pedido de actualización pendiente"
    if quien.rol == "consultor":
        return "personas de su cola para volver a llamar (hoy o ya vencidas)"
    return "fichas de su zona con un pedido de actualización pendiente"


async def _pendientes(ctx: Contexto, _: SinEntrada) -> Resultado:
    quien = ctx.quien
    # `tratables`: el trabajo y las situaciones sin quienes no autorizaron, como mi_trabajo y buscar_personas
    ins = await pedir(ctx, "GET", "/api/insignias", params={"tratables": "1"})
    ins = ins if isinstance(ins, dict) else {}
    out: dict[str, Any] = {"trabajo": {"n": ins.get("trabajo", 0), "que": _que_trabajo(quien), "ruta": "/trabajo"}}
    partes = [f"Trabajo: {miles(ins.get('trabajo', 0))}"]
    if quien.puede("calidad.ver"):
        sols = _lista(await pedir(ctx, "GET", "/api/solicitudes", params={"estado": "abiertas"}))
        vencidas = [s for s in sols if s.get("vencida")]
        por_vencer = [s for s in sols if not s.get("vencida") and isinstance(s.get("dias_restantes"), int)
                      and 0 <= s["dias_restantes"] <= POR_VENCER_DIAS]
        por_tipo: dict[str, int] = {}
        for s in sols:
            por_tipo[str(s.get("tipo"))] = por_tipo.get(str(s.get("tipo")), 0) + 1
        # Sin de quién es: que alguien pidió, por ejemplo, la supresión de sus datos es un dato suyo (y de quien no
        # autorizó, el modelo no recibe nada). El caso se atiende en Calidad del panel
        proximas = [{k: s.get(k) for k in ("id", "tipo", "canal", "estado", "vence", "dias_restantes", "vencida")}
                    for s in sols if s.get("vence")][:5]
        calidad: dict[str, Any] = {
            "coincidencias_por_revisar": ins.get("calidad", 0), "conflictos_cedula": ins.get("conflictos", 0),
            "situaciones_por_confirmar": ins.get("situaciones", 0),
            "solicitudes": {"abiertas": len(sols), "vencidas": len(vencidas),
                            f"por_vencer_{POR_VENCER_DIAS}_dias": len(por_vencer), "por_tipo": por_tipo,
                            "proximas": proximas},
            "ruta": "/calidad"}
        if quien.puede("admin"):
            lugares = _lista(await pedir(ctx, "GET", "/api/lugares"))
            sin_punto = [x for x in lugares if x.get("lat") is None and (x.get("n") or 0) > 0]
            calidad["lugares_sin_punto"] = {
                "lugares": len(sin_punto), "personas": sum(int(x.get("n") or 0) for x in sin_punto),
                "principales": [{k: x.get(k) for k in ("id", "nombre", "tipo", "n")} for x in sin_punto[:5]],
                "ruta": "/calidad?p=lugares"}
            textos = _lista(await pedir(ctx, "GET", "/api/lugares/sin-reconocer"))
            calidad["lugares_sin_reconocer"] = {"textos": len(textos),
                                                "personas": sum(int(x.get("n") or 0) for x in textos),
                                                "ruta": "/calidad?p=sin"}
        out["calidad"] = calidad
        partes.insert(0, f"Solicitudes: {miles(len(sols))}" + (f" ({miles(len(vencidas))} vencidas)" if vencidas
                                                               else ""))
        out["nota"] = ("Para atender cada caso abra Calidad de datos (abrir_vista). Las solicitudes de los titulares "
                       "tienen plazo legal: atienda primero las vencidas.")
    return Resultado(out, " · ".join(partes))


# ───────────────────────────── mi_trabajo ─────────────────────────────

LISTAS_COLA = ("por_llamar", "volver_a_llamar", "seguimiento", "mis_hoy")


class MiTrabajoEntrada(_Entrada):
    lista: Literal[LISTAS_COLA] | None = Field(
        None, description="Además, una página de esa cola de llamadas (consultor, administrador y coordinador)")
    pagina: int = Field(1, ge=1, le=10, description="Página de la cola (20 por página)")
    uid: IdOCero | None = Field(None, description="Ver las listas de otro usuario (solo administrador y "
                                                  "coordinador; sin la cola)")


SIN_NO_AUTORIZARON_TRABAJO = ("Las listas, la cola y lo de hoy y la semana no cuentan a quienes no autorizaron el "
                              "tratamiento de sus datos: en Mi trabajo del panel algunas cifras pueden ser mayores.")


def _sin_numero(f: dict) -> dict:
    """Una fila de la cola sin ningún número de teléfono, ni enmascarado: el consultor llama desde la ficha."""
    return {k: v for k, v in f.items() if k != "telefono_mascara"}


async def _mi_trabajo(ctx: Contexto, a: MiTrabajoEntrada) -> Resultado:
    quien = ctx.quien
    otro = a.uid is not None and a.uid != quien.uid
    if a.lista and otro:
        raise ErrorHerramienta("La cola de llamadas es siempre la suya: pida las listas del otro usuario sin `lista`.",
                               "invalido", estado=422)
    if a.lista and not quien.puede("trabajo.cola"):
        raise ErrorHerramienta("Su rol no trabaja la cola de llamadas: sus listas son las de Mi trabajo.", "permiso",
                               estado=403)
    # `tratables`: las listas y lo de hoy y la semana sin quienes no autorizaron (que alguien del equipo los llamó o
    # los registró hoy es un dato suyo)
    t = await pedir(ctx, "GET", "/api/trabajo", params={"uid": a.uid if otro else None, "tratables": "1"})
    t = t if isinstance(t, dict) else {}
    listas = [{"clave": x.get("clave"), "titulo": x.get("titulo"), "n": x.get("n"), "ruta": x.get("enlace")}
              for x in _lista(t.get("listas"))]
    # «listas_de_trabajo», no «listas»: en el panel «listas» son las listas de origen (políticas), que nunca salen
    out: dict[str, Any] = {"rol": t.get("rol"), "listas_de_trabajo": listas,
                           "pendientes_sin_autorizacion": t.get("pendientes_sin_autorizacion"),
                           "hoy": _dict_numeros(t.get("hoy")), "semana": _dict_numeros(t.get("semana")),
                           "nota_autorizacion": SIN_NO_AUTORIZARON_TRABAJO}
    if isinstance(t.get("alcance"), dict):
        out["zona_asignada"] = {k: [{"id": x.get("id"), "nombre": x.get("nombre")} for x in _lista(t["alcance"].get(k))]
                                for k in ("lugares", "areas")}
    personas: set[int] = set()
    resumen = _plural(len(listas), "lista", "listas")
    if a.lista:
        c = await pedir(ctx, "GET", "/api/trabajo/cola", params={"lista": a.lista, "pagina": a.pagina,
                                                                  "tratables": "1"})
        c = c if isinstance(c, dict) else {}
        filas = [_sin_numero(minimizar.fila(f)) for f in _lista(c.get("filas"))]
        out["cola"] = {"nombre": a.lista, "total": c.get("total", 0), "pagina": a.pagina, "filas": filas,
                       "nota": "Sin números de teléfono: la llamada se hace desde la ficha (/personas/<id>)."}
        personas = minimizar.ids_de(filas)
        resumen += f" · cola: {_plural(int(c.get('total') or 0), 'persona', 'personas')}"
    return Resultado(out, resumen, personas=personas)


# ───────────────────────────── equipo ─────────────────────────────

class EquipoEntrada(_Entrada):
    desde: Fecha | None = Field(None, description="Inicio del periodo (por defecto, hace 30 días)")
    hasta: Fecha | None = Field(None, description="Fin del periodo (por defecto, hoy)")
    rol: Literal["coordinador", "planillero", "consultor"] | None = Field(None, description="Solo usuarios de ese rol")
    incluir_inactivos: bool = False
    avance: Literal["lugar", "area"] | None = Field(None, description="Además, el avance por barrio o vereda asignada "
                                                                      "(lugar) o por área de trabajo (area)")

    @model_validator(mode="after")
    def _periodo(self):
        if self.desde and self.hasta and self.desde > self.hasta:
            raise ValueError("desde no puede ser posterior a hasta")
        return self


CLAVES_PLANILLERO = ("creadas_netas", "actualizadas", "con_datos_nuevos", "correcciones", "telefonos_agregados",
                     "asistencias", "ubicadas", "personas_vistas", "fichas_vistas")
CLAVES_CONSULTOR = ("acercamientos", "personas", "contactadas", "no_contactar", "autorizaciones_obtenidas",
                    "cedulas_dictadas", "fuera_de_horario")
MAX_USUARIOS = 60
# Lo que cada usuario hizo con las personas (fichas, teléfonos, asistencias, acercamientos…) y el avance de cada lugar
# (personas y porcentajes) se piden sin quienes no autorizaron (`tratables`): las demás herramientas no los cuentan, y
# la resta diría algo de ellos (que a alguien de una vereda lo llamaron hoy, o que tiene cédula)
SIN_NO_AUTORIZARON_EQUIPO = ("Lo que hizo cada usuario con las personas y las cifras de cada lugar no cuentan a "
                             "quienes no autorizaron el tratamiento de sus datos: en Usuarios del panel algunas cifras "
                             "pueden ser mayores.")


def _usuario(u: dict) -> dict:
    """Lo que el modelo necesita de cada usuario: quién es, sus alertas, su asignación, lo que hizo y lo que administró.
    Nunca su teléfono, sesiones, direcciones IP ni nada de su clave."""
    ind = u.get("indicadores") if isinstance(u.get("indicadores"), dict) else {}
    p = ind.get("planillero") if isinstance(ind.get("planillero"), dict) else {}
    c = ind.get("consultor") if isinstance(ind.get("consultor"), dict) else {}
    adm = ind.get("administracion") if isinstance(ind.get("administracion"), dict) else {}
    asig = u.get("asignacion") if isinstance(u.get("asignacion"), dict) else {}
    out: dict[str, Any] = {"id": u.get("id"), "usuario": u.get("usuario"), "nombre": u.get("nombre"),
                           "rol": u.get("rol"), "activo": u.get("activo"),
                           "alertas": [x for x in u.get("alertas") or [] if isinstance(x, str)],
                           "asignacion": {"lugares": len(asig.get("lugares") or []),
                                          "areas": len(asig.get("areas") or [])}}
    completados = p.get("completados") if isinstance(p.get("completados"), dict) else {}
    plan = {k: p.get(k, 0) for k in CLAVES_PLANILLERO}
    plan.update(cedulas=completados.get("cedula", 0), puestos=completados.get("puesto", 0),
                mesas=completados.get("mesa", 0),
                autorizaciones_si=(p.get("autorizaciones") or {}).get("si", 0)
                if isinstance(p.get("autorizaciones"), dict) else 0)
    if isinstance(p.get("calidad"), dict):
        plan["calidad"] = _dict_numeros(p["calidad"])
    cons = {k: c.get(k, 0) for k in CLAVES_CONSULTOR}
    if u.get("rol") == "planillero" or any(v for k, v in plan.items() if k != "calidad"):
        out["planillero"] = plan
    if u.get("rol") == "consultor" or any(cons.values()):
        out["consultor"] = cons
    hechos = {k: v for k, v in _dict_numeros(adm).items() if v}  # importaciones, exportaciones, uniones…
    if hechos:
        out["administracion"] = hechos
    return out


async def _equipo(ctx: Contexto, a: EquipoEntrada) -> Resultado:
    hoy = modelo.hoy_local()
    hasta = a.hasta or hoy.isoformat()
    desde = a.desde or (date.fromisoformat(hasta) - timedelta(days=29)).isoformat()
    us = _lista(await pedir(ctx, "GET", "/api/usuarios", params={"desde": desde, "hasta": hasta, "tratables": "1"}))
    elegidos = [u for u in us if (a.incluir_inactivos or u.get("activo")) and (a.rol is None or u.get("rol") == a.rol)]
    filas = [_usuario(u) for u in elegidos]

    def activos(rol: str) -> int:
        return sum(1 for u in us if u.get("activo") and u.get("rol") == rol)

    def suma(bloque: str, k: str) -> int:
        return sum(int((f.get(bloque) or {}).get(k) or 0) for f in filas)

    totales = {"coordinadores_activos": activos("coordinador"), "planilleros_activos": activos("planillero"),
               "consultores_activos": activos("consultor")}
    totales.update({k: suma("planillero", k) for k in ("creadas_netas", "actualizadas", "cedulas", "puestos", "mesas",
                                                       "telefonos_agregados", "asistencias")})
    totales.update({k: suma("consultor", k) for k in ("acercamientos", "contactadas", "no_contactar",
                                                      "autorizaciones_obtenidas")})
    out: dict[str, Any] = {"periodo": {"desde": desde, "hasta": hasta}, "totales": totales,
                           "usuarios": filas[:MAX_USUARIOS],
                           "con_alertas": [f["usuario"] for f in filas if f["alertas"]],
                           "nota_autorizacion": SIN_NO_AUTORIZARON_EQUIPO}
    if len(filas) > MAX_USUARIOS:
        out["aviso"] = f"Se muestran {MAX_USUARIOS} de {len(filas)} usuarios: filtre por rol."
    if a.avance:
        av = await pedir(ctx, "GET", "/api/usuarios/avance", params={"por": a.avance, "tratables": "1"})
        av = av if isinstance(av, dict) else {}
        out["avance"] = {"por": a.avance, "filas": [
            {"id": x.get("id"), "nombre": x.get("nombre"), "personas": x.get("personas"),
             **{k: x.get(k) for k in ("pct_cedula", "pct_puesto_mesa", "pct_telefono", "pct_contactadas")},
             "responsables": [r.get("usuario") for r in _lista(x.get("responsables"))]}
            for x in _lista(av.get("filas"))[:25]]}
    return Resultado(out, _plural(len(filas), "usuario", "usuarios"))


# ───────────────────────────── buscar_lugar ─────────────────────────────

class BuscarLugarEntrada(_Entrada):
    texto: str = Field(..., min_length=2, max_length=80, description="Nombre del barrio, vereda, sector, caserío, "
                                                                    "centro poblado o corregimiento")
    tipo: TipoLugar | None = Field(None, description="Solo lugares de ese tipo")
    limite: int = Field(5, ge=1, le=10, description="Cuántas sugerencias si no lo encuentra")


NOTAS_BUSQUEDA = {
    "unico": "Use este lugar_id.",
    "mismo_sitio": ("Son el mismo sitio en distintos niveles (por ejemplo el corregimiento, la vereda y su centro "
                    "poblado): para el mapa y los filtros vale el sugerido, el más preciso; use otro id si la persona "
                    "habla de la vereda o del corregimiento completo."),
    "ambiguo": "Son lugares distintos con el mismo nombre: pregunte a la persona cuál es antes de usar uno.",
    "ninguno": ("No está en el nomenclátor: revise el nombre con la persona. Un lugar nuevo se crea en Calidad de "
                "datos > Barrios y veredas."),
}


def _buscar_lugar_sync(db: Any, a: BuscarLugarEntrada) -> dict:
    nom = Nomenclatura.leer(db)
    b = nom.buscar(a.texto, a.tipo)
    lugares = b.candidatos if b.candidatos else (b.sugerencias or nom.sugerir(a.texto, a.limite))[:a.limite]
    out: dict[str, Any] = {"texto": minimizar.texto_libre(a.texto, 80), "resultado": b.estado,
                           "lugares": [lg.para_modelo() for lg in lugares], "nota": NOTAS_BUSQUEDA[b.estado]}
    if b.elegido is not None:
        out["sugerido"] = b.elegido.id
    if b.parecido:
        out["parecido"] = True
        out["nota"] += " El nombre no era exacto: confirme con la persona que es este."
    if b.estado == "ninguno" and lugares:
        out["sugerencias"] = out.pop("lugares")
    return out


async def _buscar_lugar(ctx: Contexto, a: BuscarLugarEntrada) -> Resultado:
    exigir_permiso(ctx, "catalogos.ver", "Su rol no consulta los catálogos del panel.")
    out = await run_in_threadpool(_buscar_lugar_sync, ctx.db, a)
    n = len(out.get("lugares") or [])
    resumen = {"unico": "1 lugar", "mismo_sitio": f"{n} niveles del mismo sitio",
               "ambiguo": f"{n} lugares con ese nombre", "ninguno": "Sin coincidencias exactas"}[out["resultado"]]
    return Resultado(out, resumen)


# ───────────────────────────── catalogos ─────────────────────────────

SECCIONES = ("etiquetas", "puestos", "campos", "valores")
# Medios con que el asistente registra una autorización para A y K (los del panel, la migración y la fusión no)
MEDIOS_ADMIN = ("escrito", "verbal_presencial", "verbal_telefono", "mensaje", "formulario")


class CatalogosEntrada(_Entrada):
    secciones: list[Literal[SECCIONES]] | None = Field(
        None, min_length=1, max_length=len(SECCIONES),
        description="Qué catálogos traer; sin esto, todos (valores = los valores válidos de los campos fijos)")

    @field_validator("secciones")
    @classmethod
    def _unicas(cls, v):
        return _sin_repetidos(v)


def _valores(quien: Any) -> dict:
    """Los valores válidos de los campos fijos, con lo que el rol puede usar (canales de acercamiento y medios de
    autorización). Sin el régimen de salud ni las categorías sensibles: el asistente no los registra."""
    rol = "admin" if quien.administra else quien.rol
    canales = dict(modelo.CANALES)
    if rol == "planillero":
        canales = {k: v for k, v in canales.items() if k in ("visita", "reunion")}
    elif rol == "consultor":
        canales = {k: v for k, v in canales.items() if k not in ("visita", "reunion")}
    medios = modelo.MEDIOS_POR_ROL.get(rol) or list(MEDIOS_ADMIN)
    return {
        "canales_acercamiento": canales,
        "resultados_acercamiento": {k: v["etiqueta"] for k, v in modelo.RESULTADOS.items()},
        "franjas": dict(modelo.FRANJAS),
        "medios_autorizacion": {m: modelo.MEDIOS_AUTORIZACION.get(m, m) for m in medios},
        "canales_autorizacion": dict(modelo.CANALES_AUTORIZACION),
        "estados_abordaje": dict(modelo.ESTADOS_ABORDAJE), "situaciones": dict(modelo.SITUACIONES),
        "motivos_actualizacion": dict(modelo.MOTIVOS_ACTUALIZACION),
        "motivos_no_disponible": dict(modelo.MOTIVOS_NO_DISPONIBLE),
        "tipos_documento": dict(modelo.TIPOS_DOCUMENTO), "sexos": dict(modelo.SEXOS),
        "estados_telefono": dict(modelo.ESTADOS_TELEFONO), "estados_votacion": dict(modelo.ESTADOS_VOTACION),
        "donde_vota": dict(modelo.DONDE_VOTA), "niveles_educativos": list(modelo.NIVELES),
        "estados_civiles": list(modelo.ESTADOS_CIVILES), "situaciones_laborales": list(modelo.SITUACIONES_LABORALES),
        "tenencias_vivienda": list(modelo.TENENCIAS),
    }


async def _catalogos(ctx: Contexto, a: CatalogosEntrada) -> Resultado:
    quieren = set(a.secciones or SECCIONES)
    out: dict[str, Any] = {}
    if quieren & {"etiquetas", "puestos", "campos"}:
        d = await pedir(ctx, "GET", "/api/catalogos")
        d = d if isinstance(d, dict) else {}
        sens = await run_in_threadpool(_sensibles, ctx.db)
        out["eleccion_vigente"] = d.get("eleccion_vigente")
        if "etiquetas" in quieren:
            out["etiquetas"] = [{k: e.get(k) for k in ("id", "nombre", "grupo")} for e in _lista(d.get("etiquetas"))
                                if not e.get("sensible") and e.get("id") not in sens.etiquetas]
        if "puestos" in quieren:
            puestos = [x for x in _lista(d.get("puestos")) if x.get("activo", True) is not False]
            out["puestos"] = [{k: x.get(k) for k in ("id", "codigo", "nombre", "mesas") if k in x}
                              for x in puestos[:200]]
        if "campos" in quieren:
            out["campos_propios"] = [{k: c.get(k) for k in ("clave", "etiqueta", "tipo", "opciones")}
                                     for c in _lista(d.get("campos")) if c.get("activo", True) is not False
                                     and not c.get("sensible") and c.get("clave") not in sens.campos]
    if "valores" in quieren:
        out["valores"] = _valores(ctx.quien)
    out["nota"] = "Barrios y veredas: use buscar_lugar. Las etiquetas y campos sensibles no están al alcance."
    partes = [f"{len(out[k])} {k.replace('_', ' ')}" for k in ("etiquetas", "puestos") if k in out]
    return Resultado(out, " · ".join(partes) or "Catálogos")


# ───────────────────────────── Catálogo de herramientas ─────────────────────────────

D_INDICADORES = (
    "Indicadores agregados de la base de habitantes (lo mismo que el Panel): cuántas personas hay y cuántas tienen "
    "cédula, teléfono, ubicación, puesto y mesa; autorización de datos, abordaje y completitud; los barrios y veredas "
    "con más personas, las necesidades más frecuentes, los puestos de votación, la cobertura de cédula por lugar y las "
    "reuniones recientes. Acepta los filtros de Habitantes (zona, lugar por nombre o id, sexo, edad, autorización, "
    "abordaje, datos que faltan…) y un área de trabajo (area_id, con alcance «zona»). Úsela para preguntas de cuántos, "
    "cómo va o qué falta: no lista personas. Nunca trae datos sensibles, listas de origen ni actividad del equipo, y "
    "no cuenta a quienes no autorizaron el tratamiento de sus datos (cuántos son: buscar_personas con consentimiento "
    "«no»). Solo administrador y coordinador.")
D_LISTAR_REUNIONES = (
    "Lista las reuniones que su rol puede ver (el planillero: las suyas y las abiertas al equipo), de la más reciente "
    "a la más vieja, con fecha, hora, tema, lugar, cuántos asistentes tuvo y cuántas personas nuevas se registraron en "
    "ella (sin contar a quienes no autorizaron el tratamiento de sus datos). Filtra por fechas (desde y hasta, "
    "AAAA-MM-DD), por palabras del título, el tema o el lugar y por las suyas. No trae los asistentes: para eso use "
    "ver_reunion.")
D_VER_REUNION = (
    "Detalle de una reunión: título, fecha, hora, lugar, tema, descripción, compromisos, las necesidades más "
    "mencionadas por los asistentes y la lista de asistentes con datos mínimos (nombre, barrio o vereda, autorización, "
    "completitud; cédulas y teléfonos enmascarados), sin quienes no autorizaron el tratamiento de sus datos (ni se "
    "listan, ni se cuentan, ni suman sus necesidades). Abrir el detalle cuenta como consulta de todos sus asistentes "
    "(el planillero tiene un tope diario): para saber solo cuándo fue o cuántos vinieron, use `asistentes: 0`, que no "
    "consulta a nadie.")
D_CREAR_REUNION = (
    "Prepara una reunión nueva en el panel: no queda guardada hasta que la persona la aprueba en la tarjeta. Necesita "
    "título y fecha (AAAA-MM-DD; puede ser pasada, para registrar una que ya ocurrió); opcionales: hora (HH:MM de 24 "
    "horas), barrio o vereda (por nombre en `lugar` o con `lugar_id` de buscar_lugar), el sitio exacto (caseta "
    "comunal, escuela…), tema y descripción. Si el nombre del lugar es ambiguo devuelve los candidatos: pregunte "
    "cuál. Solo el administrador y el coordinador la abren al equipo. Si ya hay una reunión suya igual (título, fecha, "
    "hora, lugar, sitio y tema) no se crea otra.")
D_AGREGAR_ASISTENTE = (
    "Prepara el registro de una persona como asistente de una reunión: se guarda cuando la persona del equipo lo "
    "aprueba en la tarjeta. Necesita reunion_id y persona_id (de listar_reuniones, ver_reunion o buscar_personas); "
    "opcionales: su rol en la reunión y una nota, solo si los dijeron. Asistir cuenta como un acercamiento en la "
    "ficha. No registra a quien no autorizó el tratamiento de sus datos. Si ya estaba registrada, solo cambia el rol o "
    "la nota.")
D_PENDIENTES = (
    "Lo pendiente según su rol, en conteos: lo de su trabajo (fichas por actualizar o, para el consultor, a quién "
    "volver a llamar) y, para administrador y coordinador, las colas de Calidad de datos: coincidencias por revisar, "
    "conflictos de cédula, situaciones reportadas (fallecidas o que ya no viven en Yondó), solicitudes de los "
    "titulares (abiertas, vencidas y por vencer, con su plazo) y barrios o veredas sin punto en el mapa. Lo del "
    "trabajo y las situaciones no cuentan a quienes no autorizaron el tratamiento de sus datos. No trae datos de "
    "personas: para atender cada caso abra Calidad de datos con abrir_vista.")
D_MI_TRABAJO = (
    "Mi trabajo: las listas de trabajo de su rol con cuántas personas tiene cada una y la ruta para abrirla "
    "(planillero: sin cédula, sin puesto o mesa, por actualizar, para visitar…; consultor: por llamar, volver a "
    "llamar, seguimiento y hoy), su zona asignada y lo que hizo hoy y esta semana, sin contar a quienes no autorizaron "
    "el tratamiento de sus datos. Con `lista` (consultor, administrador y coordinador) trae además una página de 20 "
    "personas de esa cola con datos mínimos y sin números de teléfono; cada una cuenta para el tope diario de personas "
    "consultadas. Con `uid`, el administrador y el coordinador ven las listas de otro usuario.")
D_EQUIPO = (
    "Cómo va el equipo en un periodo (por defecto los últimos 30 días; desde y hasta en AAAA-MM-DD, hasta 2 años): "
    "por usuario, lo que hizo (fichas creadas y actualizadas, cédulas, puestos y mesas completados, teléfonos, "
    "autorizaciones y asistencias; para consultores, acercamientos, contactos, «no contactar» y cédulas dictadas), lo "
    "que administró (importaciones, exportaciones, uniones, supresiones y usuarios creados), cuántos barrios, veredas "
    "o áreas tiene asignados y sus alertas (bloqueo, tope diario alcanzado, ingresos raros, clave vencida); los "
    "totales; y, con `avance`, el avance por barrio o vereda asignada o por área (responsables, personas y porcentaje "
    "con cédula, puesto y mesa, teléfono y contactadas). Las cifras no cuentan a quienes no autorizaron el tratamiento "
    "de sus datos. Sin sesiones, direcciones IP ni claves. Solo administrador y coordinador.")
D_BUSCAR_LUGAR = (
    "Busca un barrio, vereda, sector, caserío, centro poblado o corregimiento de Yondó en el nomenclátor del panel y "
    "devuelve su id, tipo, zona, a qué pertenece y si tiene punto o polígono en el mapa. Úsela para conseguir el "
    "lugar_id de filtros, reuniones o del mapa. Acepta errores de escritura y la palabra del tipo («vereda La Paz», "
    "«barrio La Paz»). Hay nombres repetidos: «La Paz» es un barrio del casco y también una vereda (pregunte cuál o "
    "use tipo); «San Miguel del Tigre» es el corregimiento, la vereda y el centro poblado del mismo sitio. No da "
    "datos de personas.")
D_CATALOGOS = (
    "Catálogos del panel para armar filtros y registros: etiquetas (necesidades, intereses y roles, sin las "
    "sensibles) con su id, puestos de votación de la elección vigente, campos propios no sensibles y los valores "
    "válidos de los campos fijos (canales y resultados de acercamiento y medios de autorización que su rol puede usar, "
    "canales de autorización, estados de abordaje, situaciones, motivos de actualización, tipos de documento, sexos, "
    "estados de teléfono y de votación, nivel educativo, estado civil, situación laboral y tenencia de vivienda). "
    "Para barrios y veredas use buscar_lugar.")

HERRAMIENTAS: list[Herramienta] = [
    Herramienta("indicadores", D_INDICADORES, IndicadoresEntrada, "lectura", ("tablero.ver",),
                "Calculando los indicadores", _indicadores, esquema=esquema(IndicadoresEntrada)),
    Herramienta("listar_reuniones", D_LISTAR_REUNIONES, ListarReunionesEntrada, "lectura", ("reuniones.ver",),
                "Listando las reuniones", _listar_reuniones, esquema=esquema(ListarReunionesEntrada)),
    Herramienta("ver_reunion", D_VER_REUNION, VerReunionEntrada, "lectura", ("reuniones.ver",),
                "Leyendo la reunión", _ver_reunion, esquema=esquema(VerReunionEntrada)),
    Herramienta("crear_reunion", D_CREAR_REUNION, CrearReunionEntrada, "escritura", ("reuniones.crear",),
                "Creando la reunión", _crear_reunion, confirmar=_preparar_reunion,
                esquema=esquema(CrearReunionEntrada)),
    Herramienta("agregar_asistente", D_AGREGAR_ASISTENTE, AgregarAsistenteEntrada, "escritura",
                ("reuniones.asistentes",), "Registrando el asistente", _agregar_asistente,
                confirmar=_preparar_asistente, esquema=esquema(AgregarAsistenteEntrada)),
    Herramienta("pendientes", D_PENDIENTES, SinEntrada, "lectura", ("insignias",), "Revisando los pendientes",
                _pendientes, esquema=esquema(SinEntrada)),
    Herramienta("mi_trabajo", D_MI_TRABAJO, MiTrabajoEntrada, "lectura", ("trabajo.ver",), "Revisando su trabajo",
                _mi_trabajo, esquema=esquema(MiTrabajoEntrada)),
    Herramienta("equipo", D_EQUIPO, EquipoEntrada, "lectura", ("usuarios.gestionar",), "Revisando el equipo",
                _equipo, esquema=esquema(EquipoEntrada)),
    Herramienta("buscar_lugar", D_BUSCAR_LUGAR, BuscarLugarEntrada, "lectura", ("catalogos.ver",),
                "Buscando el lugar", _buscar_lugar, esquema=esquema(BuscarLugarEntrada)),
    Herramienta("catalogos", D_CATALOGOS, CatalogosEntrada, "lectura", ("catalogos.ver",), "Leyendo los catálogos",
                _catalogos, esquema=esquema(CatalogosEntrada)),
]
