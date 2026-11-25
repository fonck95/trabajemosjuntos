"""Analítica avanzada del panel (solo A y K, permiso `analitica.ver`): el motor que calcula, en el servidor, los
análisis que la ruta `GET /api/analitica?consulta=<json>` entrega y que el asistente pide con `analizar` y
`diagnostico` (`app/agente/herramientas/analisis.py`).

Por qué está hecho así:

* **Una sola base para todo.** Cada consulta parte de las personas de Habitantes con los filtros pedidos
  (`filtros.filtro`, los mismos de la lista, el mapa y el tablero) **vigentes** (sin fallecidas ni quienes ya no viven
  en Yondó) y **tratables** (sin quienes no autorizaron el tratamiento de sus datos). Los eventos (acercamientos,
  autorizaciones, asistencias, altas) son solo de personas de esa base: llamar o registrar a alguien que dijo «no» no
  cambia ninguna cifra. Se lee una vez, proyectada (`Datos`), y el diagnóstico comparte esa lectura entre todos sus
  análisis.
* **Cifras de habitantes protegidas.** Una base de menos de 10 personas responde solo `{"pocas": true, "personas":
  "<10"}`. Toda celda de 1 a 4 personas sale «<5»; para que no se deduzca restando del total (o de los totales de
  filas y columnas, que salen en las tablas de una dimensión), se ocultan además otras celdas («oculta») hasta que
  ninguna «<5» se pueda calcular exacta. La comprobación es exacta (`fijadas`: la tabla como un flujo; una celda se
  deduce si no hay un ciclo por ella en la red residual) y, si ni ocultando todo se protege, el desglose no se publica
  (`dispersas`). Un porcentaje sale `null` si su numerador o lo que le falta está entre 1 y 4, o si su celda tiene
  menos de 10 personas (`pct`). Las series suben de día a semana y a mes si les quedan puntos ocultos, y sus
  tendencias usan solo puntos visibles. Lo que no se protege así: dos consultas con filtros distintos que se restan
  entre sí; por eso los filtros son pocos y gruesos.
* **Conteos del equipo sin supresión.** Lo que hizo cada usuario (equipo, franjas por usuario, calidad de captura) no
  es un dato de habitantes y sale completo, pero siempre sin lo hecho con quienes no autorizaron.
* **Nada sensible; lo político, solo si se habilita.** Las dimensiones son una lista cerrada: nunca régimen de
  salud, datos sensibles ni etiquetas sensibles. Los datos políticos (las dimensiones `tipo`, `lider` y `lista`, los
  filtros `tipo`, `lider_id`, `varios_lideres`, `sin_lider` y `lista`, y las fuentes «cedulas», «general» y «ambas»
  como filtro) solo con `politicos` (`analizar`): A o K con `agente_politicos` encendido para la vía de la petición
  (`api/analitica.py`: «mcp» con una clave por MCP, el asistente si no); si no, 403 `permiso`. Esas dimensiones son
  una partición (cada persona en un solo grupo), así valen la supresión exacta y las tablas de dos dimensiones: `tipo`
  es la combinación de sus tipos («Líder y votante»), `lider` su único líder nombrable (o «varios», «sin líder» o «sin
  nombre») y `lista` su única lista (o «varias» o «sin lista»); los líderes y las listas de menos de 10 personas van
  juntos («otros»), como los lugares. Un líder que no autorizó el tratamiento nunca se nombra ni sirve de filtro.
  `fuente` sigue siendo «tiene la fuente X» solo para trámites, reunión, panel y planilla, sin resto ni total, también
  con `politicos`: con las bases políticas, el resto sería la parte que falta y un grupo chico se deduciría. Las altas
  por importación de una base van a «importación», nunca al usuario que importó (`quien_capturo`); las de una
  planilla, al planillero.
* **Filtros acotados.** Como mucho 3, de una lista blanca; edad y completitud en múltiplos de 5 y días sin
  acercamiento de una lista fija (con valores finos, dos consultas casi iguales aislarían a una persona). Sin `q`,
  `ids`, polígonos, reunión, creador ni actualizador.
* **Salida corta.** 40 grupos más «otros», series de 120 puntos como mucho y 40 000 caracteres (`ajustar`). Ningún
  identificador de habitantes: los enlaces del diagnóstico llevan a Habitantes con filtros, y la cifra del enlace se
  cuenta con exactamente esos filtros (más `tratables`).

No registra lecturas (no entrega personas) ni usa `$setWindowFields`, `$dateTrunc` ni `$median`: la versión de MongoDB
de producción no se conoce. Las pasadas son en Python sobre documentos proyectados, como `tablero.resumir`.
"""
from __future__ import annotations

import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from functools import cached_property
from itertools import combinations
from typing import Annotated, Any, Callable, Iterable, Literal
from urllib.parse import urlencode

from fastapi import HTTPException
from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, model_validator
from pymongo.database import Database

from . import db as bd
from . import modelo, proyeccion
from .api import filtros as fapi
from .api import usuarios as uapi

# ───────────────────────────── Límites ─────────────────────────────

MINIMO_POBLACION = 10   # una base (o la celda de un %) con menos no da cifras
MINIMO_CELDA = 5        # una celda de 1 a 4 personas sale «<5»
MINIMO_TASA = 20        # tasas del equipo (franjas, intentos): con menos intentos no se publican
MINIMO_CAPTURA = 10     # fichas de un capturador para compararlo
MAX_GRUPOS = 40
MAX_COLUMNAS = 12
MAX_DESGLOSE = 8
MAX_PUNTOS = 120
MAX_CARACTERES = 40_000
MAX_FILTROS = 3
MAX_DIAS = 731
MAX_MS = 45_000         # maxTimeMS de las consultas grandes (el asistente espera 60 s a la API)
POCAS = {"pocas": True, "personas": "<10"}
MENOS = "<5"
OCULTA = "oculta"
RECHAZOS = frozenset({"no_contactar", "solicitud_derechos"})
UTILES = frozenset(modelo.EFECTIVOS - RECHAZOS)
FUENTES_SEGURAS = ("tramites", "reunion", "manual", "planilla")
FUENTES_POLITICAS = ("cedulas", "general")  # las bases que revelan listas de origen, partido o liderazgo
# Las fuentes como filtro (con `politicos`, también las bases políticas; «ambas»: trámites y cédulas, como Habitantes)
FUENTES_FILTRO = (*FUENTES_SEGURAS, *FUENTES_POLITICAS, "ambas")
# Las altas de estas fuentes (la primera de la ficha) entraron por una importación, no por el panel
IMPORTADAS = frozenset({"tramites", "cedulas", "general", "planilla"})
IMPORTACION = "importacion"
VIGENTE = {"situacion.estado": {"$in": [None, "activa"]}}
TRATABLE = {"consentimiento": {"$ne": "no"}}
DIAS_SEMANA = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")
FRANJAS = (("madrugada", 0, 6), ("manana", 6, 12), ("tarde", 12, 18), ("noche", 18, 22), ("madrugada", 22, 24))
CAMPOS_COMPLETADOS = tuple(c for c in modelo.CAMPOS_AVANCE if c != "regimen_salud")
NOTA_AUTORIZACION = (
    "Las cifras no cuentan a quienes no autorizaron el tratamiento de sus datos ni a quienes fallecieron o ya no "
    "viven en Yondó: por eso pueden diferir del Tablero. Los conteos de 1 a 4 personas salen «<5» y, para que no se "
    "deduzcan, otras celdas salen «oculta»; un porcentaje sale null si su numerador o lo que le falta es de 1 a 4 "
    "personas o si su grupo tiene menos de 10.")
NOTA_ENLACES = (
    "Cada enlace abre Habitantes con los mismos filtros y solo personas vigentes; su número no cuenta a quienes no "
    "autorizaron, que en Habitantes sí aparecen para A y K: la lista puede tener algunas personas más.")

# ───────────────────────────── Tipos, dimensiones, métricas ─────────────────────────────

TIPOS = ("tabla", "serie", "embudo", "cobertura", "brechas", "equipo", "calidad", "anomalias", "cohortes", "ritmo",
         "franjas", "intentos", "captura", "comparar", "reuniones_efecto", "diagnostico")
DIM_PERSONA = (
    "zona", "lugar", "lugar_tipo", "sexo", "rango_edad", "menor", "tipo_documento", "estado_civil", "nivel_educativo",
    "situacion_laboral", "tenencia_vivienda", "estrato", "jefe_hogar", "personas_hogar", "precision", "puesto", "mesa",
    "votacion_estado", "donde", "consentimiento", "consentimiento_medio", "contacto_habilitado", "abordaje_estado",
    "ultimo_resultado", "ultimo_canal", "intentos", "completitud", "con_cedula", "cedula_verificada",
    "telefono_usable", "varios_telefonos", "requiere_actualizacion", "etiqueta", "asistencia", "fuente",
    "quien_capturo", "mes_alta", "tipo", "lider", "lista")
# Datos políticos: solo con `politicos` (`analizar`). Sus dimensiones son una partición (ver `valor_de`)
DIM_POLITICAS = ("tipo", "lider", "lista")
FILTROS_POLITICOS = ("tipo", "lider_id", "varios_lideres", "sin_lider", "lista")
MULTI = ("etiqueta", "fuente")  # una persona cae en varios grupos: sin total, sin resto y sin %
SIN_TIPO, SIN_LIDER, SIN_LISTA = "sin_tipo", "sin_lider", "sin_lista"
VARIOS_LIDERES, VARIAS_LISTAS = "varios_lideres", "varias_listas"
LIDER_OCULTO = "lider_sin_nombre"  # solo líderes que no autorizaron (o ya no están activos): nunca se nombran
# Los grupos con nombre propio de menos de 10 personas van juntos (con valores chicos, dos consultas casi iguales
# aislarían a una persona, y quedarían tantas celdas ocultas que no se publicaría el desglose)
JUNTOS = {"lugar": "otros_lugares", "lider": "otros_lideres", "lista": "otras_listas"}
POLITICOS_APAGADOS = {
    "codigo": "permiso",
    "mensaje": "Los datos políticos (tipo de persona, líderes, listas y las bases de cédulas y general) no están "
               "habilitados para esta vía en Ajustes, o su rol no los usa: la analítica no cuenta por ellos."}
NOTA_LIDER = ("Cada persona va en un solo grupo: el de su líder si la trae uno solo, «Varios líderes» si la traen varios, "
              "«Sin líder» si no tiene. Los líderes que no autorizaron el tratamiento de sus datos no se nombran (sus "
              "personas van a «sin nombre») y los de menos de 10 personas van juntos en «Otros líderes». Para los "
              "conteos de cada líder, la lista de líderes.")
LIDER_NO_USABLE = {"codigo": "invalido", "campo": "lider_id",
                   "mensaje": "No hay un líder o concejal con ese id que se pueda usar (los que no autorizaron el "
                              "tratamiento de sus datos no se usan)."}
DIM_EVENTO = ("canal", "usuario", "resultado", "medio", "campo", "franja", "dia_semana")
DIMENSIONES = DIM_PERSONA + DIM_EVENTO
# Dimensiones de lo que hace el equipo: sus conteos de acercamientos no se suprimen
DIM_EQUIPO = frozenset({"canal", "usuario", "franja", "dia_semana"})
METRICAS_PCT: dict[str, Callable[["Datos", dict], bool]] = {
    "pct_con_cedula": lambda d, p: p["ced"],
    "pct_telefono_usable": lambda d, p: p["tel"],
    "pct_ubicadas": lambda d, p: p["ubicada"],
    "pct_ubicacion_exacta": lambda d, p: p["precision"] == "exacta",
    "pct_autorizadas": lambda d, p: p["autorizada"],
    "pct_contacto_habilitado": lambda d, p: p["habilitado"],
    "pct_abordadas": lambda d, p: p["n"] >= 1,
    "pct_contactadas": lambda d, p: p["efectivos"] >= 1,
    "pct_contacto_util": lambda d, p: p["id"] in d.utiles,
    "pct_puesto_mesa": lambda d, p: p["con_puesto"] and p["con_mesa"],
    "pct_votacion_verificada": lambda d, p: p["votacion_estado"] == "verificado",
    "pct_asistio": lambda d, p: p["asistencias"] > 0,
}
METRICAS = ("personas", "pct", "completitud_media", *METRICAS_PCT)
EVENTOS = ("altas", "acercamientos", "efectivos", "contacto_util", "reuniones", "asistencias", "autorizaciones",
           "completados")
DESGLOSES = {"altas": ("zona", "quien_capturo"), "acercamientos": ("canal", "resultado", "usuario", "zona"),
             "efectivos": ("canal", "usuario", "zona"), "contacto_util": ("canal", "usuario", "zona"),
             "reuniones": (), "asistencias": ("zona",), "autorizaciones": ("zona", "medio"),
             "completados": ("campo", "zona")}
DESGLOSE_TODOS = ("canal", "resultado", "usuario", "zona", "quien_capturo", "medio", "campo")
METRICAS_COMPARAR = ("altas", "acercamientos", "contacto_util", "tasa_contacto_util", "autorizaciones")
DIM_COMPARAR = {
    "altas": ("zona", "lugar", "sexo", "rango_edad", "quien_capturo"),
    "acercamientos": ("canal", "usuario", "franja", "dia_semana", "zona", "lugar", "sexo", "rango_edad"),
    "autorizaciones": ("medio", "usuario", "zona", "lugar"),
}
DIM_COMPARAR["contacto_util"] = DIM_COMPARAR["tasa_contacto_util"] = DIM_COMPARAR["acercamientos"]
GRANULARIDADES = ("dia", "semana", "mes")
DIAS_BRECHAS = (30, 60, 90, 180, 365)
DIAS_SIN_ACERCAMIENTO = (7, 14, 30, 60, 90, 180, 365)
FALTAN = ("cedula", "telefono", "sexo", "edad", "lugar", "puesto", "mesa", "direccion", "puesto_mesa")
# Parámetros de Habitantes que la vista de personas lee de la URL (`FILTROS` de web/js/vistas/personas.js) y que
# `filtros.Filtros` entiende: solo con ellos un hallazgo lleva enlace (con otro, la vista lo descartaría en silencio y
# mostraría otra lista). Una prueba compara esta lista con las dos
ENLAZABLES = frozenset({
    "zona", "lugar_id", "fuente", "etiqueta", "con_cedula", "con_telefono", "varios_telefonos", "precision", "asistio",
    "consentimiento", "sexo", "completitud_max", "edad_min", "edad_max", "puesto_id", "votacion_estado", "donde",
    "con_puesto", "con_mesa", "abordaje_estado", "abordado", "contactado", "ultimo_resultado", "sin_acercamiento_dias",
    "proximo_vencido", "canal_autorizado", "requiere_actualizacion", "situacion", "menor", "area_id", "tipo_documento",
    "cedula_verificada", "telefono_estado", "estado_civil", "nivel_educativo", "situacion_laboral", "estrato",
    "tenencia_vivienda", "jefe_hogar", "sin_cedula", "sin_telefono", "sin_sexo", "sin_edad", "sin_lugar", "sin_puesto",
    "sin_mesa", "sin_direccion", *FILTROS_POLITICOS})

def _tipos_legibles(tipos: Iterable[str]) -> str:
    """«Concejal», «Líder y votante», «Concejal, líder y votante»."""
    nombres = [modelo.TIPOS_PERSONA[t] for t in tipos]
    nombres = nombres[:1] + [n.lower() for n in nombres[1:]]
    return nombres[0] if len(nombres) == 1 else f"{', '.join(nombres[:-1])} y {nombres[-1]}"


# Los grupos de `tipo`: cada combinación de tipos (en el orden de `modelo.TIPOS_PERSONA`), de uno en adelante
_COMBINACIONES = [c for n in range(1, len(modelo.TIPOS_PERSONA) + 1)
                  for c in combinations(modelo.TIPOS_PERSONA, n)]

ETIQUETAS: dict[str, dict[str, str]] = {
    "zona": {"urbana": "Urbana", "rural": "Rural", "sin": "Sin zona"},
    "sexo": {**modelo.SEXOS, "sin": "Sin dato"},
    "rango_edad": {**{r: r for r in modelo.RANGOS_EDAD}, "sin": "Sin edad"},
    "tipo_documento": {**modelo.TIPOS_DOCUMENTO, "sin": "Sin dato"},
    "estado_civil": {**{x: x for x in modelo.ESTADOS_CIVILES}, "otro": "Otro valor", "sin": "Sin dato"},
    "nivel_educativo": {**{x: x for x in modelo.NIVELES}, "otro": "Otro valor", "sin": "Sin dato"},
    "situacion_laboral": {**{x: x for x in modelo.SITUACIONES_LABORALES}, "otro": "Otro valor", "sin": "Sin dato"},
    "tenencia_vivienda": {**{x: x for x in modelo.TENENCIAS}, "otro": "Otro valor", "sin": "Sin dato"},
    "estrato": {**{str(i): f"Estrato {i}" for i in range(7)}, "sin": "Sin dato"},
    "jefe_hogar": {"si": "Sí", "no": "No", "sin": "Sin dato"},
    "personas_hogar": {"1": "1", "2": "2", "3-4": "3 a 4", "5-6": "5 a 6", "7+": "7 o más", "sin": "Sin dato"},
    "precision": {"exacta": "Exacta (dirección o punto)", "aproximada": "Aproximada (barrio o vereda)",
                  "otra": "Otra", "sin": "Sin ubicación"},
    "votacion_estado": {**modelo.ESTADOS_VOTACION, "sin": "Sin votación"},
    "donde": {**modelo.DONDE_VOTA, "sin": "Sin dato"},
    "consentimiento": {"si": "Autorizó (contacto habilitado)", "por_confirmar": "Autorizó en planilla, por confirmar",
                       "pendiente": "Pendiente"},
    "consentimiento_medio": {**modelo.MEDIOS_AUTORIZACION, "sin": "Sin autorización"},
    "medio": dict(modelo.MEDIOS_AUTORIZACION),
    "abordaje_estado": dict(modelo.ESTADOS_ABORDAJE),
    "ultimo_resultado": {**{k: v["etiqueta"] for k, v in modelo.RESULTADOS.items()}, "sin": "Sin acercamiento"},
    "resultado": {k: v["etiqueta"] for k, v in modelo.RESULTADOS.items()},
    "ultimo_canal": {**modelo.CANALES, "sin": "Sin acercamiento"},
    "canal": dict(modelo.CANALES),
    "intentos": {"0": "Ninguno", "1": "1", "2-3": "2 a 3", "4+": "4 o más"},
    "completitud": {"0-24": "0 a 24 %", "25-49": "25 a 49 %", "50-74": "50 a 74 %", "75-100": "75 a 100 %"},
    "requiere_actualizacion": {**modelo.MOTIVOS_ACTUALIZACION, "no": "Sin pedido"},
    "asistencia": {"0": "Ninguna", "1": "Una", "2+": "Dos o más"},
    "fuente": {"tramites": "Base de trámites", "reunion": "Reuniones", "manual": "Panel", "planilla": "Planillas"},
    "tipo": {**{"+".join(c): _tipos_legibles(c) for c in _COMBINACIONES}, SIN_TIPO: "Sin tipo"},
    "lider": {VARIOS_LIDERES: "Varios líderes", LIDER_OCULTO: "Solo líderes sin nombre (no autorizaron o ya no están "
              "activos)", JUNTOS["lider"]: "Otros líderes (menos de 10 personas cada uno)", SIN_LIDER: "Sin líder"},
    "lista": {VARIAS_LISTAS: "Varias listas", JUNTOS["lista"]: "Otras listas (menos de 10 personas cada una)",
              SIN_LISTA: "Sin lista"},
    "campo": {c: modelo.ETIQUETAS_CAMPOS.get(c, c) for c in CAMPOS_COMPLETADOS},
    "franja": {"madrugada": "Madrugada (22 a 6)", "manana": "Mañana (6 a 12)", "tarde": "Tarde (12 a 18)",
               "noche": "Noche (18 a 22)"},
    "dia_semana": {"lunes": "Lunes", "martes": "Martes", "miercoles": "Miércoles", "jueves": "Jueves",
                   "viernes": "Viernes", "sabado": "Sábado", "domingo": "Domingo"},
    "puesto": {"otra_eleccion": "Puesto de otra elección", "texto_sin_catalogo": "Puesto escrito sin catálogo",
               "otro_municipio": "Vota en otro municipio", "no_inscrito": "No está inscrito",
               "sin_puesto": "Sin puesto"},
    "mesa": {"sin_mesa": "Sin mesa"},
    "lugar": {"sin": "Sin barrio ni vereda", "otros_lugares": "Otros lugares (menos de 10 personas cada uno)"},
    "lugar_tipo": {"barrio": "Barrio", "sector": "Sector", "vereda": "Vereda", "caserio": "Caserío",
                   "centro_poblado": "Centro poblado", "corregimiento": "Corregimiento", "sin": "Sin lugar"},
    "mes_alta": {IMPORTACION: "Importación de una base"},
    "quien_capturo": {IMPORTACION: "Importación de una base", "sin": "Sin dato"},
}
for _d in ("menor", "contacto_habilitado", "con_cedula", "cedula_verificada", "telefono_usable", "varios_telefonos"):
    ETIQUETAS[_d] = {"si": "Sí", "no": "No"}
# Orden de los grupos de las dimensiones de catálogo (las demás van por cantidad)
ORDEN = {k: list(v) for k, v in ETIQUETAS.items()}
ORDEN["menor"] = ORDEN["contacto_habilitado"] = ["si", "no"]
ORDEN["abordaje_estado"] = list(modelo.ESTADOS_ABORDAJE)
ORDEN["consentimiento"] = ["si", "por_confirmar", "pendiente"]
POR_CANTIDAD = frozenset({"lugar", "quien_capturo", "etiqueta", "usuario", "mesa", "consentimiento_medio", "medio",
                          "resultado", "ultimo_resultado", "campo", "canal", "ultimo_canal", "lider", "lista"})


# ───────────────────────────── Entrada ─────────────────────────────

def _no_booleano(v: Any) -> Any:
    if isinstance(v, bool):
        raise ValueError("Debe ser un número entero, no verdadero o falso")
    return v


def _fecha(v: str) -> str:
    try:
        d = date.fromisoformat(v)
    except ValueError:
        raise ValueError(f"Fecha inexistente o mal escrita: {v} (use AAAA-MM-DD)") from None
    if not 2000 <= d.year <= 2100:
        raise ValueError("La fecha debe estar entre los años 2000 y 2100")
    return d.isoformat()


def _multiplo_5(v: int | None) -> int | None:
    if v is not None and v % 5:
        raise ValueError("Use un múltiplo de 5 (con valores finos, dos consultas casi iguales aislarían a una persona)")
    return v


Id = Annotated[int, Field(ge=1, le=2_000_000_000), BeforeValidator(_no_booleano)]
IdOCero = Annotated[int, Field(ge=0, le=2_000_000_000), BeforeValidator(_no_booleano)]
Fecha = Annotated[str, Field(min_length=10, max_length=10, description="AAAA-MM-DD"), AfterValidator(_fecha)]
Multiplo5 = Annotated[int, Field(ge=0, le=120), AfterValidator(_multiplo_5)]


class _Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FiltrosConsulta(_Entrada):
    """Los filtros de Habitantes que admite la analítica (como mucho 3). Fuera a propósito: búsqueda por texto o por
    números, ids, polígonos, régimen de salud, reunión, creador y actualizador, ocupación y perfil, y la situación (la
    base es siempre la de personas vigentes). Los políticos (`tipo`, `lider_id`, `varios_lideres`, `sin_lider`,
    `lista` y las fuentes «cedulas», «general» y «ambas») solo valen con `politicos` (`analizar`)."""
    zona: Literal["urbana", "rural", "sin"] | None = Field(None, description="urbana, rural o sin zona")
    lugar_id: IdOCero | None = Field(None, description="Barrio o vereda (id del nomenclátor); 0 = sin lugar")
    fuente: Literal[FUENTES_FILTRO] | None = Field(
        None, description="Tiene esa fuente; cedulas, general y ambas (trámites y cédulas) son bases políticas: solo "
                          "con los datos políticos habilitados")
    tipo: Literal[(*modelo.TIPOS_PERSONA, SIN_TIPO)] | None = Field(
        None, description="Tipo de persona: concejal, lider, votante o sin_tipo (dato político)")
    lider_id: Id | None = Field(None, description="Las que trajo ese líder o concejal (dato político)")
    varios_lideres: bool | None = Field(None, description="true: las que trae más de un líder (dato político)")
    sin_lider: bool | None = Field(None, description="true: las que nadie lidera (dato político)")
    lista: str | None = Field(None, min_length=1, max_length=120,
                              description="Lista de origen, con su nombre exacto (dato político)")
    etiqueta: Id | None = Field(None, description="Necesidad, interés o rol (id; nunca una sensible)")
    con_cedula: bool | None = None
    con_telefono: bool | None = Field(None, description="Con un teléfono usable")
    varios_telefonos: bool | None = None
    telefono_estado: Literal[tuple(modelo.ESTADOS_TELEFONO)] | None = Field(None, description="Algún número así")
    precision: Literal["exacta", "aproximada", "ubicada", "sin"] | None = Field(None, description="Ubicación")
    asistio: bool | None = Field(None, description="Asistió a alguna reunión")
    consentimiento: Literal["si", "pendiente", "por_confirmar"] | None = Field(
        None, description="Autorización; por_confirmar = «sí» de planilla sin confirmar")
    sexo: Literal["F", "M", "N", "sin"] | None = None
    edad_min: Multiplo5 | None = Field(None, description="Edad mínima (múltiplo de 5)")
    edad_max: Multiplo5 | None = Field(None, description="Edad máxima (múltiplo de 5)")
    menor: bool | None = None
    tipo_documento: Literal[tuple(modelo.TIPOS_DOCUMENTO)] | None = None
    cedula_verificada: bool | None = None
    completitud_max: Multiplo5 | None = Field(None, description="Completitud hasta este % (múltiplo de 5)")
    puesto_id: IdOCero | None = Field(None, description="Puesto de votación (id); 0 = sin puesto")
    con_puesto: bool | None = None
    con_mesa: bool | None = None
    votacion_estado: Literal[tuple(modelo.ESTADOS_VOTACION)] | None = None
    donde: Literal[tuple(modelo.DONDE_VOTA)] | None = None
    abordado: bool | None = Field(None, description="Con algún acercamiento")
    contactado: bool | None = Field(None, description="Con algún contacto efectivo")
    abordaje_estado: Literal[tuple(modelo.ESTADOS_ABORDAJE)] | None = None
    ultimo_resultado: Literal[tuple(modelo.RESULTADOS)] | None = None
    sin_acercamiento_dias: Literal[DIAS_SIN_ACERCAMIENTO] | None = Field(None, description="Sin acercamiento en días")
    proximo_vencido: bool | None = Field(None, description="true: con un «volver a llamar» vencido")
    canal_autorizado: Literal[tuple(modelo.CANALES_AUTORIZACION)] | None = None
    requiere_actualizacion: bool | None = Field(None, description="Con un pedido de actualización pendiente (o sin)")
    motivos_actualizacion: list[Literal[tuple(modelo.MOTIVOS_ACTUALIZACION)]] | None = Field(
        None, min_length=1, max_length=len(modelo.MOTIVOS_ACTUALIZACION))
    estado_civil: Literal[(*modelo.ESTADOS_CIVILES, "sin")] | None = None
    nivel_educativo: Literal[(*modelo.NIVELES, "sin")] | None = None
    situacion_laboral: Literal[(*modelo.SITUACIONES_LABORALES, "sin")] | None = None
    tenencia_vivienda: Literal[(*modelo.TENENCIAS, "sin")] | None = None
    estrato: int | None = Field(None, ge=0, le=6)
    faltan: list[Literal[FALTAN]] | None = Field(None, min_length=1, max_length=3,
                                                 description="Le faltan estos datos (cada uno cuenta como un filtro)")
    area_id: Id | None = Field(None, description="Área de trabajo dibujada en el mapa")

    def activos(self) -> int:
        """Cuántos filtros lleva: cada dato de `faltan` cuenta como uno (el nombre de un lugar y su tipo, como uno)."""
        n = 0
        for k, v in self.model_dump(exclude_none=True).items():
            if k == "tipo_lugar":
                continue
            n += len(set(v)) if k == "faltan" else 1
        return n

    @model_validator(mode="after")
    def _coherentes(self):
        if self.activos() > MAX_FILTROS:
            raise ValueError(f"Use como mucho {MAX_FILTROS} filtros (cada dato de «faltan» cuenta como uno)")
        if self.edad_min is not None and self.edad_max is not None and self.edad_min > self.edad_max:
            raise ValueError("edad_min no puede ser mayor que edad_max")
        if self.requiere_actualizacion is not None and self.motivos_actualizacion:
            raise ValueError("Use requiere_actualizacion o motivos_actualizacion, no los dos")
        for k in ("proximo_vencido", "varios_lideres", "sin_lider"):
            if getattr(self, k) is False:
                raise ValueError(f"{k} solo admite true")
        return self

    def politicos(self) -> list[str]:
        """Los filtros políticos que trae (también una fuente política)."""
        datos = self.model_dump(exclude_none=True)
        usados = [k for k in FILTROS_POLITICOS if k in datos]
        if datos.get("fuente") in (*FUENTES_POLITICAS, "ambas"):
            usados.append("fuente")
        return usados


class Consulta(_Entrada):
    """Una consulta de analítica: un `tipo` y solo los parámetros de ese tipo (un parámetro que no aplica es un error,
    no se ignora). Ver `catalogo()` para lo que admite cada tipo."""
    tipo: Literal[TIPOS] = Field(..., description="Qué análisis")
    dimensiones: list[Literal[DIMENSIONES]] | None = Field(
        None, min_length=1, max_length=2, description="tabla: 1 o 2; embudo: 0 o 1; calidad: zona; comparar: 1")
    metricas: list[Literal[METRICAS]] | None = Field(None, min_length=1, max_length=6, description="tabla")
    evento: Literal[EVENTOS] | None = Field(None, description="serie: qué se cuenta en el tiempo")
    granularidad: Literal[GRANULARIDADES] | None = Field(None, description="serie, equipo: dia, semana o mes")
    desglose: Literal[DESGLOSE_TODOS] | None = Field(None, description="serie: abrir por; franjas: usuario")
    metrica: Literal[METRICAS_COMPARAR] | None = Field(None, description="comparar: qué métrica se explica")
    desde: Fecha | None = Field(None, description="Inicio del periodo (AAAA-MM-DD)")
    hasta: Fecha | None = Field(None, description="Fin del periodo (AAAA-MM-DD), incluido")
    referencia_desde: Fecha | None = Field(None, description="comparar: inicio del periodo de referencia")
    referencia_hasta: Fecha | None = Field(None, description="comparar: fin del periodo de referencia")
    meta_pct: int | None = Field(None, ge=1, le=100, description="cobertura, ritmo: meta de cobertura (%; 30)")
    fecha_meta: Fecha | None = Field(None, description="ritmo, diagnostico: fecha en que se quiere la meta")
    semanas: int | None = Field(None, ge=2, le=26, description="ritmo: semanas que miden el ritmo actual (8)")
    dias: Literal[DIAS_BRECHAS] | None = Field(None, description="brechas: ventana en días (90)")
    filtros: FiltrosConsulta | None = Field(None, description="Filtros de Habitantes (como mucho 3)")

    @model_validator(mode="after")
    def _segun_tipo(self):
        obligatorios, opcionales = PARAMETROS[self.tipo]
        presentes = {k for k, v in self if k != "tipo" and v is not None}
        sobran = sorted(presentes - obligatorios - opcionales)
        if sobran:
            raise ValueError(f"«{', '.join(sobran)}» no aplica al tipo {self.tipo}")
        faltan = sorted(obligatorios - presentes)
        if faltan:
            raise ValueError(f"El tipo {self.tipo} necesita «{', '.join(faltan)}»")
        dims = self.dimensiones or []
        if len(set(dims)) != len(dims):
            raise ValueError("Dimensiones repetidas")
        if self.tipo == "tabla":
            if any(x not in DIM_PERSONA for x in dims):
                raise ValueError("tabla admite solo dimensiones de personas (" + ", ".join(DIM_PERSONA) + ")")
            if len(dims) == 2 and set(dims) & set(MULTI):
                raise ValueError("etiqueta y fuente van solas (una persona cae en varios grupos)")
            if "mesa" in dims and not (dims == ["puesto", "mesa"] or (self.filtros and self.filtros.puesto_id)):
                raise ValueError("mesa va con el filtro puesto_id o como segunda dimensión después de puesto")
            mets = self.metricas or []
            if set(dims) & set(MULTI) and "pct" in mets:
                raise ValueError("pct (la parte del total) no aplica a etiqueta ni a fuente: no tienen total")
            if len(dims) == 2 and set(mets) - {"personas", "pct"}:
                raise ValueError("Con dos dimensiones solo van personas y pct (la parte de la fila): un % de un "
                                 "atributo por celda dejaría deducir las celdas ocultas. Use una dimensión y un filtro")
        elif self.tipo == "embudo":
            if len(dims) > 1 or any(x not in DIM_PERSONA or x in MULTI or x == "mesa" for x in dims):
                raise ValueError("embudo admite una dimensión de personas (no etiqueta, fuente ni mesa)")
        elif self.tipo == "calidad":
            if dims and dims != ["zona"]:
                raise ValueError("calidad solo se abre por zona")
        elif self.tipo == "comparar":
            permitidas = DIM_COMPARAR[self.metrica]
            if len(dims) != 1 or dims[0] not in permitidas:
                raise ValueError(f"comparar {self.metrica} se abre por una de: {', '.join(permitidas)}")
        elif self.tipo == "serie":
            if self.desglose is not None and self.desglose not in DESGLOSES[self.evento]:
                abre = ", ".join(DESGLOSES[self.evento]) or "nada"
                raise ValueError(f"La serie de {self.evento} se abre por: {abre}")
            if self.evento == "reuniones" and self.filtros is not None:
                raise ValueError("Los filtros de personas no aplican a la serie de reuniones")
        elif self.tipo == "franjas" and self.desglose not in (None, "usuario"):
            raise ValueError("franjas solo se abre por usuario")
        for a, b in (("desde", "hasta"), ("referencia_desde", "referencia_hasta")):
            x, y = getattr(self, a), getattr(self, b)
            if x and y:
                if x > y:
                    raise ValueError(f"{a} no puede ser posterior a {b}")
                if (date.fromisoformat(y) - date.fromisoformat(x)).days >= MAX_DIAS:
                    raise ValueError(f"El periodo no puede pasar de {MAX_DIAS} días")
        if (self.referencia_desde is None) != (self.referencia_hasta is None):
            raise ValueError("Use referencia_desde y referencia_hasta juntas")
        return self


# (obligatorios, opcionales) de cada tipo
PARAMETROS: dict[str, tuple[set[str], set[str]]] = {
    "tabla": ({"dimensiones"}, {"metricas", "filtros"}),
    "serie": ({"evento"}, {"granularidad", "desglose", "desde", "hasta", "filtros"}),
    "embudo": (set(), {"dimensiones", "filtros"}),
    "cobertura": (set(), {"meta_pct", "filtros"}),
    "brechas": (set(), {"dias", "filtros"}),
    "equipo": (set(), {"desde", "hasta", "granularidad"}),
    "calidad": (set(), {"dimensiones", "filtros"}),
    "anomalias": (set(), {"desde", "hasta"}),
    "cohortes": (set(), {"desde", "hasta", "filtros"}),
    "ritmo": ({"fecha_meta"}, {"meta_pct", "semanas", "filtros"}),
    "franjas": (set(), {"desde", "hasta", "desglose", "filtros"}),
    "intentos": (set(), {"desde", "hasta", "filtros"}),
    "captura": (set(), {"desde", "hasta"}),
    "comparar": ({"metrica", "dimensiones"}, {"desde", "hasta", "referencia_desde", "referencia_hasta", "filtros"}),
    "reuniones_efecto": (set(), {"desde", "hasta"}),
    "diagnostico": (set(), {"filtros", "fecha_meta", "meta_pct"}),
}
BANDERAS = ("con_cedula", "con_telefono", "varios_telefonos", "asistio", "menor", "cedula_verificada", "con_puesto",
            "con_mesa", "abordado", "contactado")
SOLO_SI = ("proximo_vencido", "varios_lideres", "sin_lider")  # filtros que solo valen con true


def politicos_de(c: "Consulta") -> list[str]:
    """Lo político que usa una consulta: sus dimensiones políticas y sus filtros políticos."""
    return [x for x in c.dimensiones or [] if x in DIM_POLITICAS] + (c.filtros.politicos() if c.filtros else [])


def a_filtros(f: FiltrosConsulta | None) -> dict[str, Any]:
    """Los filtros como argumentos de `filtros.Filtros` (los parámetros de Habitantes, con sus valores)."""
    out: dict[str, Any] = {}
    if f is None:
        return out
    for k, v in f.model_dump(exclude_none=True).items():
        if k in ("lugar", "tipo_lugar"):  # los del asistente, ya resueltos a lugar_id
            continue
        if k in BANDERAS:
            out[k] = 1 if v else 0
        elif k in SOLO_SI:
            out[k] = 1
        elif k == "faltan":
            for campo in v:
                out[f"sin_{campo}"] = 1
        elif k == "requiere_actualizacion":
            out[k] = "1" if v else "0"
        elif k == "motivos_actualizacion":
            out["requiere_actualizacion"] = ",".join(v)
        else:
            out[k] = v
    return out


def consulta_mongo(db: Database, params: dict[str, Any], hoy: date, *, vigentes: bool = True) -> dict:
    """La consulta de MongoDB de la base: los filtros de Habitantes (`filtros.filtro`, que ya exige ACTIVA), sin quienes
    no autorizaron y, salvo que se pida lo contrario, solo vigentes. 404 si el área no existe."""
    f = fapi.preparar(db, fapi.Filtros(**params))
    y = [fapi.filtro(f, hoy), dict(TRATABLE)]
    if vigentes:
        y.append(dict(VIGENTE))
    return {"$and": y}


def lider_usable(db: Database, lid: int) -> bool:
    """¿`lid` es una ficha activa que autorizó y que lidera (marcada como líder o concejal, o que figura como líder de
    alguien, como la lista de líderes)? Un líder que no autorizó no sirve de filtro: contar a quienes trajo diría que
    lidera."""
    l = db.personas.find_one({"_id": lid, **bd.ACTIVA, "consentimiento": {"$ne": "no"}},
                             {t: 1 for t in modelo.TIPOS_LIDERAN})
    if l is None:
        return False
    return modelo.lidera(l) or db.personas.count_documents({**bd.ACTIVA, "lideres.id": lid}, limit=1) > 0


def exigir_politicos(db: Database, c: "Consulta", politicos: bool) -> None:
    """403 `permiso` si la consulta usa datos políticos sin `politicos`; 422 si filtra por un líder que no sirve (el
    mismo mensaje para todo motivo: no dice si el id existe)."""
    if not politicos_de(c):
        return
    if not politicos:
        raise HTTPException(403, dict(POLITICOS_APAGADOS))
    if c.filtros is not None and c.filtros.lider_id is not None and not lider_usable(db, c.filtros.lider_id):
        raise HTTPException(422, dict(LIDER_NO_USABLE))


def exigir_etiqueta(db: Database, f: FiltrosConsulta | None) -> None:
    """Una etiqueta que no existe (404) o sensible (403 `permiso`): no se cuenta por ella."""
    if f is None or f.etiqueta is None:
        return
    e = db.etiquetas.find_one({"_id": f.etiqueta}, {"nombre": 1, "sensible": 1})
    if e is None:
        raise HTTPException(404, {"mensaje": f"No existe la etiqueta #{f.etiqueta}", "codigo": "no_existe"})
    if proyeccion.etiqueta_sensible(e):
        raise HTTPException(403, {"mensaje": "Esa etiqueta revela un dato sensible: la analítica no cuenta por ella",
                                  "codigo": "permiso"})


# ───────────────────────────── Privacidad ─────────────────────────────

def celda(n: int) -> int | str:
    """Un conteo de habitantes: de 1 a 4 sale «<5»."""
    return MENOS if 0 < n < MINIMO_CELDA else n


def pct(num: int, den: int, decimales: int = 1) -> float | None:
    """Un porcentaje de habitantes, o None si dejaría ver a pocas personas: su grupo tiene menos de 10, o el numerador
    o lo que le falta (den − num) están entre 1 y 4."""
    if den < MINIMO_POBLACION or 0 < num < MINIMO_CELDA or 0 < den - num < MINIMO_CELDA:
        return None
    return round(100 * num / den, decimales)


def atributo(num: int, den: int) -> int | str:
    """Cuántos de un grupo tienen un atributo, con la regla de `pct`: «<5» si son de 1 a 4; «oculta» si lo que falta
    es de 1 a 4 o el grupo tiene menos de 10."""
    if den == 0:
        return 0
    if 0 < num < MINIMO_CELDA:
        return MENOS
    if den < MINIMO_POBLACION or 0 < den - num < MINIMO_CELDA:
        return OCULTA
    return num


def media(valores: list[float], decimales: int = 1) -> float | None:
    return round(statistics.fmean(valores), decimales) if len(valores) >= MINIMO_POBLACION else None


def _publicar(n: int, oculta: bool) -> int | str:
    return (MENOS if n < MINIMO_CELDA else OCULTA) if oculta else n


Suma = tuple[int, float]  # lo que se sabe de un total: (mínimo, máximo); math.inf si no tiene tope


def _cotas_celda(n: int) -> tuple[int, float]:
    """Lo que alguien que conoce la regla sabe de una celda oculta: «<5» está entre 1 y 4; «oculta», de 5 en
    adelante."""
    return (1, MINIMO_CELDA - 1) if n < MINIMO_CELDA else (MINIMO_CELDA, math.inf)


def fijadas(m: dict[tuple, int], ocultas: set, sumas_fila: dict, sumas_col: dict, total: Suma) -> set:
    """Las celdas ocultas que se pueden calcular exactas con lo publicado y los totales conocidos (cada fila, cada
    columna y el total, con sus cotas). Es exacto: la tabla es un flujo (el total va a las filas, de cada fila a sus
    columnas por las celdas ocultas, y de las columnas vuelve al total) y una celda puede valer otra cosa si y solo si
    hay un ciclo por ella en la red residual (lo que le falta a cada arco para su cota de arriba y lo que le sobra
    sobre la de abajo, con las cotas de «<5» y «oculta»). Sin ciclo, su valor es el único posible: quedó expuesta."""
    arcos: list[tuple[Any, Any, int, float, float]] = []  # (desde, hasta, valor, mínimo, máximo)
    celdas: list[tuple[int, tuple]] = []
    filas, cols = defaultdict(int), defaultdict(int)
    vis_f, vis_c = defaultdict(int), defaultdict(int)
    for (f, c), n in m.items():
        if (f, c) in ocultas:
            lo, hi = _cotas_celda(n)
            celdas.append((len(arcos), (f, c)))
            arcos.append((("f", f), ("c", c), n, lo, hi))
            filas[f] += n
            cols[c] += n
        else:
            vis_f[f] += n
            vis_c[c] += n
    if not celdas:
        return set()
    for f, x in filas.items():
        lo, hi = sumas_fila.get(f, (0, math.inf))
        arcos.append(("*f", ("f", f), x, lo - vis_f[f], hi - vis_f[f]))
    for c, x in cols.items():
        lo, hi = sumas_col.get(c, (0, math.inf))
        arcos.append((("c", c), "*c", x, lo - vis_c[c], hi - vis_c[c]))
    vis = sum(n for k, n in m.items() if k not in ocultas)
    arcos.append(("*c", "*f", sum(filas.values()), total[0] - vis, total[1] - vis))
    residual: dict[Any, list[tuple[Any, int]]] = defaultdict(list)
    for i, (u, v, x, lo, hi) in enumerate(arcos):
        if x < hi:
            residual[u].append((v, i))
        if x > lo:
            residual[v].append((u, i))

    def llega(origen: Any, destino: Any, sin: int) -> bool:
        vistos, pila = {origen}, [origen]
        while pila:
            u = pila.pop()
            for v, i in residual[u]:
                if i != sin and v not in vistos:
                    if v == destino:
                        return True
                    vistos.add(v)
                    pila.append(v)
        return False

    out = set()
    for i, k in celdas:
        u, v, x, lo, hi = arcos[i]
        sube = x < hi and llega(v, u, i)
        baja = x > lo and not sube and llega(u, v, i)
        if not sube and not baja:
            out.add(k)
    return out


def suprimir(m: dict[tuple, int], sumas_fila: dict, sumas_col: dict, total: Suma) -> set | None:
    """Las celdas que se ocultan: las de 1 a 4 y, mientras alguna de ellas quede expuesta (`fijadas`), la visible más
    chica (de 5 o más: un 0 no protege), primero de su fila o columna. Que se deduzca una complementaria no importa
    (es de 5 o más: se habría podido publicar). None si no hay cómo protegerlas: ese desglose no se publica."""
    primarias = {k for k, n in m.items() if 0 < n < MINIMO_CELDA}
    ocultas = set(primarias)
    orden = {k: i for i, k in enumerate(m)}
    revisado = False
    while ocultas:
        exp = fijadas(m, ocultas, sumas_fila, sumas_col, total) & primarias
        if not exp:
            break
        if not revisado:
            # Ocultar más solo agrega ciclos posibles: si con todo oculto alguna sigue expuesta, no hay arreglo
            todo = ocultas | {k for k, n in m.items() if n >= MINIMO_CELDA}
            if fijadas(m, todo, sumas_fila, sumas_col, total) & primarias:
                return None
            revisado = True
        filas, cols = {k[0] for k in exp}, {k[1] for k in exp}
        libres = [k for k, n in m.items() if k not in ocultas and n >= MINIMO_CELDA]
        cerca = [k for k in libres if k[0] in filas or k[1] in cols]
        if not libres:
            return None
        ocultas.add(min(cerca or libres, key=lambda k: (m[k], orden[k])))
    return ocultas


def proteger(conteos: dict, *, total_conocido: bool = True) -> dict | None:
    """Conteos de habitantes de una dimensión: «<5» las de 1 a 4 y, si su total se conoce (el de la base o el de otra
    consulta), las complementarias («oculta») que hagan falta para que ninguna se deduzca restando. None si eso no es
    posible (todo el desglose son celdas chicas): quien llama no lo publica."""
    if not total_conocido:
        return {k: _publicar(n, 0 < n < MINIMO_CELDA) for k, n in conteos.items()}
    total = sum(conteos.values())
    m = {("_", k): n for k, n in conteos.items()}
    ocultas = suprimir(m, {"_": (total, total)}, {}, (total, total))
    if ocultas is None:
        return None
    return {k: _publicar(n, ("_", k) in ocultas) for k, n in conteos.items()}


def _suma_conocida(n: int) -> Suma:
    """Lo que se sabe del total de una fila o columna: exacto, o entre 1 y 4 si sale «<5» en la tabla de una
    dimensión."""
    return (1, MINIMO_CELDA - 1) if 0 < n < MINIMO_CELDA else (n, n)


def conocida(publicado: Any, n: int) -> Suma:
    """Lo que se sabe de un total por cómo salió publicado: exacto, «<5» (1 a 4) u «oculta» (5 o más)."""
    if publicado == MENOS:
        return (1, MINIMO_CELDA - 1)
    if publicado == OCULTA:
        return (MINIMO_CELDA, math.inf)
    return (n, n)


def proteger_2d(m: dict[tuple, int], filas: list, columnas: list,
                sumas_fila: dict[Any, Suma] | None = None) -> dict[tuple, int | str] | None:
    """Una tabla de dos dimensiones: «<5» las celdas de 1 a 4 y supresión complementaria hasta que ninguna oculta se
    pueda deducir con los márgenes (cada fila, cada columna y el total salen en las tablas de una dimensión). Sin
    `sumas_fila`, el total de cada fila se da por conocido (exacto, o de 1 a 4); con él, lo que de verdad se publicó
    de cada fila (`conocida`). None si no se puede proteger."""
    sumas_f = sumas_fila or {f: _suma_conocida(sum(m[(f, c)] for c in columnas)) for f in filas}
    sumas_c = {c: _suma_conocida(sum(m[(f, c)] for f in filas)) for c in columnas}
    total = sum(m.values())
    ocultas = suprimir(m, sumas_f, sumas_c, (total, total))
    if ocultas is None:
        return None
    return {k: _publicar(n, k in ocultas) for k, n in m.items()}


NOTA_DISPERSAS = ("Las personas quedan tan repartidas en grupos chicos que este desglose no se puede mostrar sin "
                  "dejar deducir cuántas hay en alguno: use menos grupos, quite un filtro o una dimensión.")


def dispersas(tipo: str, n: int) -> dict:
    """La respuesta cuando un desglose no se puede proteger (`proteger` devolvió None)."""
    return {"tipo": tipo, "dispersas": True, "base": {"personas": n}, "nota": NOTA_DISPERSAS}


def visible(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def partir(filas: list, cuentas: dict[Any, list[int]], clases: list[str],
           publicado: dict | None = None) -> dict[tuple, int | str] | None:
    """Un atributo de cada grupo como tabla de dos dimensiones (grupos × clases: «sí» y «no», o mujeres, hombres y
    otro): el tamaño de cada grupo (como se publicó: `publicado`) y el total de cada clase se conocen (salen en otras
    tablas), así que un % o un conteo de un grupo no se puede ocultar solo: los demás grupos lo dejarían deducir
    restando. Se protege como cualquier tabla de dos dimensiones."""
    sumas = {f: conocida(publicado[f], sum(cuentas[f])) for f in filas} if publicado is not None else None
    return proteger_2d({(f, c): cuentas[f][i] for f in filas for i, c in enumerate(clases)}, filas, clases, sumas)


def pcts(d: "Datos", filas: list, miembros: dict, pred: Callable[["Datos", dict], bool],
         publicado: dict | None = None) -> dict[Any, float | None]:
    """El % de cada grupo que cumple `pred`, protegido como tabla (`partir`): sale si el grupo tiene 10 o más y sus
    dos celdas («sí» y «no») quedan visibles. `publicado`: cómo salió el tamaño de cada grupo."""
    cuentas = {}
    for f in filas:
        si = sum(1 for p in miembros[f] if pred(d, p))
        cuentas[f] = [si, len(miembros[f]) - si]
    pub = partir(filas, cuentas, ["si", "no"], publicado)
    out = {}
    for f in filas:
        n = len(miembros[f])
        ok = pub is not None and n >= MINIMO_POBLACION and visible(pub[(f, "si")]) and visible(pub[(f, "no")])
        out[f] = round(100 * cuentas[f][0] / n, 1) if ok else None
    return out


def conteos_atributo(d: "Datos", filas: list, miembros: dict, pred: Callable[["Datos", dict], bool],
                     publicado: dict | None = None) -> dict[Any, int | str]:
    """Cuántos de cada grupo cumplen `pred`, con la misma protección que `pcts` («<5», «oculta»)."""
    cuentas = {}
    for f in filas:
        si = sum(1 for p in miembros[f] if pred(d, p))
        cuentas[f] = [si, len(miembros[f]) - si]
    pub = partir(filas, cuentas, ["si", "no"], publicado)
    out = {}
    for f in filas:
        if pub is None:
            out[f] = OCULTA if cuentas[f][0] >= MINIMO_CELDA or cuentas[f][0] == 0 else MENOS
        elif visible(pub[(f, "si")]) and visible(pub[(f, "no")]):
            out[f] = cuentas[f][0]
        else:
            out[f] = pub[(f, "si")] if not visible(pub[(f, "si")]) else OCULTA
    return out


# ───────────────────────────── Fechas ─────────────────────────────

def _dia(ts: Any) -> date | None:
    f = modelo.fecha_local(ts)
    return date.fromisoformat(f) if f else None


def _instante(ts: Any) -> datetime | None:
    t = modelo.instante(ts)
    return t.astimezone(modelo.ZONA) if t else None


def _utc(d: date) -> str:
    return uapi._utc(d)


def _periodo(c: Consulta, dias: int, hoy: date) -> tuple[date, date]:
    """(desde, hasta) del periodo pedido, o los últimos `dias` días hasta hoy."""
    h = date.fromisoformat(c.hasta) if c.hasta else hoy
    d = date.fromisoformat(c.desde) if c.desde else h - timedelta(days=dias - 1)
    if d > h:
        raise HTTPException(422, {"mensaje": "«desde» no puede ser posterior a «hasta» (ni a hoy)",
                                  "codigo": "invalido"})
    if (h - d).days >= MAX_DIAS:
        raise HTTPException(422, {"mensaje": f"El periodo no puede pasar de {MAX_DIAS} días", "codigo": "invalido"})
    return d, h


def clave_periodo(d: date, gran: str) -> str:
    if gran == "dia":
        return d.isoformat()
    if gran == "semana":
        y, w, _ = d.isocalendar()
        return f"{y}-S{w:02d}"
    return f"{d.year}-{d.month:02d}"


def _inicio(d: date, gran: str) -> date:
    if gran == "dia":
        return d
    if gran == "semana":
        return d - timedelta(days=d.weekday())
    return d.replace(day=1)


def _siguiente(d: date, gran: str) -> date:
    if gran == "dia":
        return d + timedelta(days=1)
    if gran == "semana":
        return d + timedelta(days=7)
    return (d.replace(day=28) + timedelta(days=4)).replace(day=1)


def periodos(desde: date, hasta: date, gran: str) -> list[tuple[str, bool]]:
    """Los periodos entre `desde` y `hasta` (incluidos): (clave, parcial). Un periodo es parcial si el rango no lo
    cubre entero (el primero o el último)."""
    out, x = [], _inicio(desde, gran)
    while x <= hasta:
        fin = _siguiente(x, gran) - timedelta(days=1)
        out.append((clave_periodo(x, gran), x < desde or fin > hasta))
        x = _siguiente(x, gran)
    return out


def _franja(hora: int) -> str:
    return next(n for n, a, b in FRANJAS if a <= hora < b)


# ───────────────────────────── La lectura compartida ─────────────────────────────

def _no_vacio(campo: str) -> dict:
    return {"$not": [{"$in": [{"$ifNull": [campo, None]}, [None, ""]]}]}


def _lista(campo: str) -> dict:
    return {"$cond": [{"$isArray": campo}, campo, []]}


# Lo que se lee de cada persona: los identificadores (cédula, teléfonos, dirección, coordenadas) solo como sí o no,
# calculados en MongoDB; nunca salen del servidor
PROYECCION = {
    "creado_en": 1, "fuentes": 1, "zona": 1, "lugar_id": 1, "sexo": 1, "edad": 1, "edad_ref": 1,
    "fecha_nacimiento": 1, "nac_aprox": 1, "tipo_documento": 1, "estado_civil": 1, "nivel_educativo": 1,
    "situacion_laboral": 1, "tenencia_vivienda": 1, "estrato": 1, "jefe_hogar": 1, "personas_hogar": 1,
    "geo_precision": 1, "consentimiento": 1, "consentimiento_medio": 1, "contacto_habilitado": 1,
    "cedula_verificada": 1, "completitud": 1, "etiquetas": 1, "avance": 1, "no_disponible": 1, "ultimo_contacto": 1,
    "cp_uid": "$creado_por.uid", "cp_cap": "$creado_por.capturado_por",
    "lt": _no_vacio("$lugar_texto"), "ced": _no_vacio("$cedula"), "dir": _no_vacio("$direccion"),
    "t1": {"$ne": [{"$ifNull": ["$telefono", None]}, None]}, "t2": {"$ne": [{"$ifNull": ["$telefono2", None]}, None]},
    "tel_est": {"$map": {"input": _lista("$telefonos"), "as": "t", "in": "$$t.estado"}},
    "ubic": {"$ne": [{"$ifNull": ["$lat", None]}, None]},
    "vo": {"$eq": [{"$type": "$votacion"}, "object"]},
    "v_pid": "$votacion.puesto_id", "v_mesa": "$votacion.mesa", "v_el": "$votacion.eleccion",
    "v_est": "$votacion.estado", "v_donde": "$votacion.donde", "v_txt": _no_vacio("$votacion.puesto_texto"),
    "pv": _no_vacio("$puesto_votacion"), "mesa_l": _no_vacio("$mesa"),
    "ab": "$abordaje", "ra": "$requiere_actualizacion.motivo",
    "ra_on": {"$ne": [{"$ifNull": ["$requiere_actualizacion", None]}, None]},
    "asis": {"$map": {"input": _lista("$asistencias"), "as": "a", "in": "$$a.creado_en"}},
}
# Lo político que se lee de cada persona, solo con `politicos`: el tipo, los ids de sus líderes y sus listas
PROYECCION_POLITICA = {
    **{t: 1 for t in modelo.TIPOS_PERSONA}, "listas": 1,
    "lids": {"$map": {"input": _lista("$lideres"), "as": "l", "in": "$$l.id"}},
}


def _catalogo(v: Any, cat: Iterable[str]) -> str:
    if v in (None, ""):
        return "sin"
    return v if v in cat else "otro"


def _hogar(n: Any) -> str:
    if not isinstance(n, int) or isinstance(n, bool) or n <= 0:
        return "sin"
    return "1" if n == 1 else "2" if n == 2 else "3-4" if n <= 4 else "5-6" if n <= 6 else "7+"


def _intentos(n: int) -> str:
    return "0" if n == 0 else "1" if n == 1 else "2-3" if n <= 3 else "4+"


def _completitud(c: int) -> str:
    return "0-24" if c < 25 else "25-49" if c < 50 else "50-74" if c < 75 else "75-100"


def _efectivo(a: dict) -> bool:
    return a["efectivo"] if isinstance(a.get("efectivo"), bool) else a.get("resultado") in modelo.EFECTIVOS


def _util(a: dict) -> bool:
    return _efectivo(a) and a.get("resultado") not in RECHAZOS


def _si_no(v: bool) -> str:
    return "si" if v else "no"


class Datos:
    """Lo que leen los análisis de una consulta, una sola vez y solo si lo usan: la base (personas vigentes y
    tratables con los filtros, proyectadas), los catálogos y los eventos de un periodo, siempre de personas de la
    base."""

    def __init__(self, db: Database, filtros: FiltrosConsulta | None = None, hoy: date | None = None,
                 politicos: bool = False):
        self.db = db
        self.politicos = politicos
        self.hoy = hoy or modelo.hoy_local()
        self.ajustes = modelo.leer_ajustes(db)
        self.eleccion = self.ajustes.get("eleccion_vigente")
        self.dias_dato = int(self.ajustes.get("dias_reintento_dato") or 90)
        self.filtros = filtros
        self.params = a_filtros(filtros)
        self._acercamientos: dict[tuple, list[dict]] = {}
        self._autorizaciones: dict[tuple, list[dict]] = {}
        self.consulta = consulta_mongo(db, self.params, self.hoy)

    # ── Catálogos ──
    @cached_property
    def puestos(self) -> dict[int, dict]:
        return {p["_id"]: p for p in bd.puestos_vigentes(self.db, self.eleccion)}

    @cached_property
    def lugares(self) -> dict[int, dict]:
        return {x["_id"]: x for x in self.db.lugares.find({}, {"nombre": 1, "tipo": 1, "zona": 1, "lat": 1})}

    @cached_property
    def usuarios(self) -> dict[int, dict]:
        out = {0: {"usuario": "administrador", "nombre": "Administrador", "rol": "admin", "activo": True}}
        for u in self.db.usuarios.find({}, {"usuario": 1, "nombre": 1, "rol": 1, "activo": 1}):
            out[u["_id"]] = u
        return out

    @cached_property
    def etiquetas(self) -> dict[int, dict]:
        """Las etiquetas que no son sensibles (las sensibles nunca son un grupo)."""
        sens = proyeccion.etiquetas_sensibles(self.db)
        return {e["_id"]: e for e in self.db.etiquetas.find({}, {"nombre": 1, "grupo": 1}) if e["_id"] not in sens}

    @cached_property
    def no_autorizaron(self) -> set[int]:
        return set(uapi._no_autorizaron(self.db))

    @cached_property
    def lideres(self) -> dict[int, dict]:
        """Los líderes que lideran a alguien de la base y se pueden nombrar: activos y que autorizaron (solo con
        `politicos`). Los demás no cuentan como líderes de nadie aquí (`valor_de`)."""
        ids = {i for p in self.personas for i in p.get("lideres") or []}
        if not ids:
            return {}
        return {x["_id"]: x for x in self.db.personas.find(
            {"_id": {"$in": sorted(ids)}, **bd.ACTIVA, "consentimiento": {"$ne": "no"}},
            {"nombre": 1, **{t: 1 for t in modelo.TIPOS_LIDERAN}})}

    def nombre_usuario(self, uid: Any) -> str:
        if uid == IMPORTACION:
            return ETIQUETAS["quien_capturo"][IMPORTACION]
        u = self.usuarios.get(uid) if isinstance(uid, int) else None
        return (u or {}).get("usuario") or f"usuario #{uid}"

    # ── La base ──
    @cached_property
    def personas(self) -> list[dict]:
        proyeccion_ = {**PROYECCION, **PROYECCION_POLITICA} if self.politicos else PROYECCION
        cursor = self.db.personas.aggregate([{"$match": self.consulta}, {"$project": proyeccion_}], maxTimeMS=MAX_MS)
        return [self._ficha(x) for x in cursor]

    @cached_property
    def por_id(self) -> dict[int, dict]:
        return {p["id"]: p for p in self.personas}

    def _ficha(self, x: dict) -> dict:
        """Una persona de la base reducida a lo que agrupan los análisis (sin ningún identificador)."""
        hoy = self.hoy
        edad = modelo.edad_efectiva(x, hoy)
        rango = modelo.rango_edad(edad) or "sin"
        ab = x.get("ab") if isinstance(x.get("ab"), dict) else {}
        consent = x.get("consentimiento")
        habilitado = consent == "si" and x.get("contacto_habilitado") is True
        gp = x.get("geo_precision")
        precision = ("sin" if not x.get("ubic") else "exacta" if gp in ("direccion", "manual")
                     else "aproximada" if gp in fapi.APROXIMADAS else "otra")
        fuentes = x.get("fuentes") if isinstance(x.get("fuentes"), list) else []
        primera = fuentes[0] if fuentes else None
        importada = primera in IMPORTADAS
        cap = x.get("cp_cap")
        if importada:
            quien: Any = cap if primera == "planilla" and isinstance(cap, int) and not isinstance(cap, bool) \
                else IMPORTACION
        else:
            uid = x.get("cp_uid")
            quien = uid if isinstance(uid, int) and not isinstance(uid, bool) else "sin"
        alta = _dia(x.get("creado_en"))
        vo = bool(x.get("vo"))
        v = {"puesto_id": x.get("v_pid"), "mesa": x.get("v_mesa"), "eleccion": x.get("v_el"),
             "estado": x.get("v_est"), "donde": x.get("v_donde")} if vo else None
        con_puesto = (vo and (x.get("v_pid") is not None or bool(x.get("v_txt"))
                              or x.get("v_donde") in ("otro_municipio", "no_inscrito"))) \
            or (not vo and bool(x.get("pv")))
        con_mesa = (vo and x.get("v_mesa") is not None) or (not vo and bool(x.get("mesa_l")))
        tel_est = [e for e in x.get("tel_est") or [] if isinstance(e, str)]
        avance = {}
        for campo, marca in (x.get("avance") or {}).items():
            if campo in CAMPOS_COMPLETADOS and isinstance(marca, dict):
                f = _dia(marca.get("ts"))
                if f:
                    avance[campo] = f
        asis = [f for f in (_dia(t) for t in x.get("asis") or []) if f]
        p = {
            "id": x["_id"], "zona": x.get("zona") if x.get("zona") in ("urbana", "rural") else "sin",
            "lugar": x.get("lugar_id"), "lugar_texto": bool(x.get("lt")),
            "sexo": x.get("sexo") if x.get("sexo") in modelo.SEXOS else "sin", "edad": edad, "rango_edad": rango,
            "menor": modelo.es_menor(x, hoy), "tipo_documento": x.get("tipo_documento") or "sin",
            "estado_civil": _catalogo(x.get("estado_civil"), modelo.ESTADOS_CIVILES),
            "nivel_educativo": _catalogo(x.get("nivel_educativo"), modelo.NIVELES),
            "situacion_laboral": _catalogo(x.get("situacion_laboral"), modelo.SITUACIONES_LABORALES),
            "tenencia_vivienda": _catalogo(x.get("tenencia_vivienda"), modelo.TENENCIAS),
            "estrato": str(x["estrato"]) if isinstance(x.get("estrato"), int) and not isinstance(x["estrato"], bool)
            and 0 <= x["estrato"] <= 6 else "sin",
            "jefe_hogar": "sin" if x.get("jefe_hogar") is None else _si_no(x.get("jefe_hogar") is True),
            "personas_hogar": _hogar(x.get("personas_hogar")), "precision": precision, "ubicada": bool(x.get("ubic")),
            "votacion": v, "votacion_estado": modelo.estado_votacion_efectivo(v, self.eleccion) or "sin",
            "donde": (v or {}).get("donde") or "sin", "con_puesto": bool(con_puesto), "con_mesa": bool(con_mesa),
            "puesto_texto": bool(x.get("v_txt")) if vo else bool(x.get("pv")),
            "consentimiento": "si" if habilitado else "por_confirmar" if consent == "si" else "pendiente",
            "autorizada": consent == "si", "habilitado": habilitado,
            "medio": (x.get("consentimiento_medio") or "sin") if consent == "si" else "sin",
            "abordaje_estado": ab.get("estado") or "sin_abordar", "n": int(ab.get("n") or 0),
            "efectivos": int(ab.get("efectivos") or 0), "ultimo_resultado": ab.get("ultimo_resultado") or "sin",
            "ultimo_canal": ab.get("ultimo_canal") or "sin", "proximo": ab.get("proximo"),
            "completitud": int(x.get("completitud") or 0), "ced": bool(x.get("ced")),
            "ced_verif": bool(x.get("ced")) and x.get("cedula_verificada") is True, "dir": bool(x.get("dir")),
            "tel": bool(x.get("t1")), "tel2": bool(x.get("t2")),
            "tel_malo": any(e in ("equivocado", "inexistente") for e in tel_est),
            "requiere": (x.get("ra") or "no") if x.get("ra_on") else "no",
            "etiquetas": [e for e in x.get("etiquetas") or [] if isinstance(e, int)],
            "asistencias": len(x.get("asis") or []), "asis": asis,
            "fuentes": [f for f in fuentes if f in FUENTES_SEGURAS], "quien": quien, "alta": alta,
            "mes_alta": IMPORTACION if quien == IMPORTACION else (alta.strftime("%Y-%m") if alta else "sin"),
            "avance": avance, "ultimo_contacto": modelo.fecha_valida(x.get("ultimo_contacto")),
        }
        p["faltan"] = self._faltan(x, p)
        if self.politicos:
            p["tipos"] = [t for t in modelo.TIPOS_PERSONA if x.get(t) is True]
            p["lideres"] = list(dict.fromkeys(i for i in x.get("lids") or []
                                              if isinstance(i, int) and not isinstance(i, bool)))
            p["listas"] = list(dict.fromkeys(l.strip() for l in x.get("listas") or [] if isinstance(l, str)
                                             and l.strip()))
        return p

    def _faltan(self, x: dict, p: dict) -> list[str]:
        """Los datos que le faltan (la regla de `filtros.falta`: vacío y sin marca «no lo tiene» vigente)."""
        nd = x.get("no_disponible") if isinstance(x.get("no_disponible"), dict) else {}
        out = []
        tiene = {"cedula": p["ced"], "telefono": p["tel"], "sexo": p["sexo"] != "sin",
                 "edad": x.get("edad") is not None or x.get("nac_aprox") is not None, "lugar": p["lugar"] is not None,
                 "puesto": p["con_puesto"], "mesa": p["con_mesa"], "direccion": p["dir"],
                 "autorizacion": x.get("consentimiento") in ("si", "no")}
        for campo in modelo.CAMPOS_FALTAN:
            if tiene[campo]:
                continue
            marca = nd.get(campo)
            if campo in modelo.CAMPOS_NO_DISPONIBLE and isinstance(marca, dict):
                f = _dia(marca.get("ts"))
                if f is not None and (self.hoy - f).days < self.dias_dato:
                    continue
            out.append(campo)
        return out

    def puesto_de(self, p: dict) -> str:
        """La casilla electoral de una persona: «p<id>» (un puesto de la elección vigente) o una casilla aparte."""
        v = p["votacion"]
        if v is None:
            return "texto_sin_catalogo" if p["puesto_texto"] else "sin_puesto"
        if v.get("donde") in ("otro_municipio", "no_inscrito"):
            return v["donde"]
        if v.get("puesto_id") is not None:
            return f"p{v['puesto_id']}" if v["puesto_id"] in self.puestos and v.get("eleccion") == self.eleccion \
                else "otra_eleccion"
        return "texto_sin_catalogo" if p["puesto_texto"] else "sin_puesto"

    # ── Contactos de cada persona (toda la historia) ──
    @cached_property
    def contactos(self) -> dict[int, dict]:
        """Por persona de la base: su primer acercamiento (`primero`, ISO) y si tuvo un contacto útil. Sin los
        anulados; con los de las reuniones (asistir es un contacto)."""
        util = {"$and": [{"$ifNull": ["$efectivo", {"$in": ["$resultado", sorted(modelo.EFECTIVOS)]}]},
                         {"$not": [{"$in": ["$resultado", sorted(RECHAZOS)]}]}]}
        out = {}
        for x in self.db.acercamientos.aggregate([
                {"$match": {"anulado": {"$ne": True}, "persona_id": {"$ne": None}}},
                {"$group": {"_id": "$persona_id", "primero": {"$min": "$ts"},
                            "util": {"$max": {"$cond": [util, 1, 0]}}}}], maxTimeMS=MAX_MS):
            if x["_id"] in self.por_id:
                out[x["_id"]] = {"primero": x.get("primero"), "util": bool(x.get("util"))}
        return out

    @cached_property
    def utiles(self) -> set[int]:
        return {pid for pid, x in self.contactos.items() if x["util"]}

    # ── Eventos ──
    def acercamientos(self, desde: date | None = None, hasta: date | None = None) -> list[dict]:
        """Los acercamientos hechos a mano (sin anulados ni los automáticos de las reuniones) a personas de la base, del
        periodo (o de toda la historia), en orden."""
        clave = (desde, hasta)
        if clave not in self._acercamientos:
            q: dict = {"anulado": {"$ne": True}, "auto": {"$ne": True}, "persona_id": {"$ne": None}}
            if desde is not None:
                q["ts"] = {"$gte": _utc(desde), "$lt": _utc(hasta + timedelta(days=1))}
            campos = {"persona_id": 1, "ts": 1, "fecha": 1, "uid": 1, "canal": 1, "resultado": 1, "efectivo": 1,
                      "fuera_de_horario": 1}
            filas = []
            for a in self.db.acercamientos.find(q, campos).max_time_ms(MAX_MS):
                if a.get("persona_id") not in self.por_id:
                    continue
                t = _instante(a.get("ts"))
                if t is None:
                    continue
                a["_t"] = t
                a["_d"] = modelo.fecha_valida(a.get("fecha")) or t.date()
                filas.append(a)
            filas.sort(key=lambda a: (a["_t"], a["_id"]))
            self._acercamientos[clave] = filas
        return self._acercamientos[clave]

    def autorizaciones(self, desde: date, hasta: date) -> list[dict]:
        """Los «sí» del periodo de personas de la base (sin los migrados ni los de una unión de fichas: su fecha es la
        de la migración o la unión, no la de la autorización)."""
        clave = (desde, hasta)
        if clave not in self._autorizaciones:
            q = {"estado": "si", "ts": {"$gte": _utc(desde), "$lt": _utc(hasta + timedelta(days=1))},
                 "medio": {"$nin": ["migrado", "fusion"]}, "persona_id": {"$ne": None}}
            filas = []
            for a in self.db.autorizaciones.find(q, {"persona_id": 1, "ts": 1, "medio": 1, "uid": 1}):
                if a.get("persona_id") in self.por_id and (f := _dia(a.get("ts"))):
                    a["_d"] = f
                    filas.append(a)
            self._autorizaciones[clave] = filas
        return self._autorizaciones[clave]

    def reuniones(self, desde: date, hasta: date) -> list[dict]:
        return list(self.db.reuniones.find({"fecha": {"$gte": desde.isoformat(), "$lte": hasta.isoformat()}},
                                           {"titulo": 1, "fecha": 1, "lugar_id": 1, "creado_por_uid": 1,
                                            "creado_en": 1}))


# ───────────────────────────── Grupos de una dimensión ─────────────────────────────

def valor_de(d: Datos, dim: str, p: dict) -> Any:
    """El grupo de una persona en una dimensión (una lista en las de varios grupos)."""
    if dim in ("zona", "sexo", "rango_edad", "tipo_documento", "estado_civil", "nivel_educativo", "situacion_laboral",
               "tenencia_vivienda", "estrato", "jefe_hogar", "personas_hogar", "precision", "votacion_estado", "donde",
               "consentimiento", "abordaje_estado", "ultimo_resultado", "ultimo_canal", "mes_alta"):
        return p[dim]
    if dim == "lugar":
        return p["lugar"] if p["lugar"] is not None else "sin"
    if dim == "lugar_tipo":
        return (d.lugares.get(p["lugar"]) or {}).get("tipo") or "sin"
    if dim == "menor":
        return _si_no(p["menor"])
    if dim == "puesto":
        return d.puesto_de(p)
    if dim == "mesa":
        k = d.puesto_de(p)
        m = (p["votacion"] or {}).get("mesa")
        return f"{k}:{m}" if k.startswith("p") and isinstance(m, int) else "sin_mesa"
    if dim == "consentimiento_medio":
        return p["medio"]
    if dim == "contacto_habilitado":
        return _si_no(p["habilitado"])
    if dim == "intentos":
        return _intentos(p["n"])
    if dim == "completitud":
        return _completitud(p["completitud"])
    if dim == "con_cedula":
        return _si_no(p["ced"])
    if dim == "cedula_verificada":
        return _si_no(p["ced_verif"])
    if dim == "telefono_usable":
        return _si_no(p["tel"])
    if dim == "varios_telefonos":
        return _si_no(p["tel2"])
    if dim == "requiere_actualizacion":
        return p["requiere"]
    if dim == "etiqueta":
        return [e for e in dict.fromkeys(p["etiquetas"]) if e in d.etiquetas]
    if dim == "asistencia":
        return "0" if p["asistencias"] == 0 else "1" if p["asistencias"] == 1 else "2+"
    if dim == "fuente":
        return list(dict.fromkeys(p["fuentes"]))
    if dim == "tipo":
        return "+".join(p.get("tipos") or []) or SIN_TIPO
    if dim == "lider":
        ids = p.get("lideres") or []
        visibles = [i for i in ids if i in d.lideres]
        if len(visibles) > 1:
            return VARIOS_LIDERES
        return visibles[0] if visibles else LIDER_OCULTO if ids else SIN_LIDER
    if dim == "lista":
        listas = p.get("listas") or []
        return VARIAS_LISTAS if len(listas) > 1 else listas[0] if listas else SIN_LISTA
    if dim == "quien_capturo":
        return p["quien"]
    raise ValueError(dim)


def etiqueta_de(d: Datos, dim: str, v: Any) -> str:
    """El nombre de un grupo para leer (nombres de lugares, puestos y usuarios del equipo: no son de habitantes)."""
    if v == "otros":
        return "Otros"
    if v is None:
        return "Sin dato"
    fijo = ETIQUETAS.get(dim, {}).get(str(v))
    if fijo is not None:
        return fijo
    if dim == "lugar" and isinstance(v, int):
        lg = d.lugares.get(v) or {}
        return f"{lg.get('nombre') or f'#{v}'} ({lg.get('tipo') or 'lugar'})"
    if dim in ("quien_capturo", "usuario"):
        return d.nombre_usuario(v)
    if dim == "etiqueta":
        return (d.etiquetas.get(v) or {}).get("nombre") or f"#{v}"
    if dim == "lider" and isinstance(v, int):
        l = d.lideres.get(v) or {}
        tipo = next((modelo.TIPOS_PERSONA[t] for t in modelo.TIPOS_LIDERAN if l.get(t) is True), "Ya no marcado")
        return f"{l.get('nombre') or f'#{v}'} ({tipo})"
    if dim == "lista":
        return str(v)[:120]
    if dim in ("puesto", "mesa") and isinstance(v, str) and v.startswith("p"):
        pid, _, mesa = v[1:].partition(":")
        pu = d.puestos.get(int(pid)) or {}
        base = f"{pu.get('codigo') or ''} {pu.get('nombre') or ''}".strip()
        return f"{base} · mesa {mesa}" if mesa else base
    if dim == "mes_alta":
        return str(v)
    return str(v)


def _orden_grupos(d: Datos, dim: str, conteos: Counter) -> list:
    if dim == "puesto":
        pues = [f"p{i}" for i in sorted(d.puestos, key=lambda i: str(d.puestos[i].get("codigo") or ""))]
        return [k for k in pues + ORDEN["puesto"] if k in conteos]
    if dim == "mes_alta":
        return sorted((k for k in conteos if k not in (IMPORTACION, "sin")), reverse=False) + \
            [k for k in (IMPORTACION, "sin") if k in conteos]
    if dim in ORDEN and dim not in POR_CANTIDAD:
        orden = [k for k in ORDEN[dim] if k in conteos]
        return orden + sorted((k for k in conteos if k not in orden), key=str)
    return [k for k, _ in sorted(conteos.items(), key=lambda kv: (-kv[1], str(kv[0])))]


def agrupar(d: Datos, dim: str, personas: list[dict] | None = None,
            max_grupos: int = MAX_GRUPOS) -> tuple[list, dict[Any, list[dict]]]:
    """(orden, miembros) de una dimensión: los lugares, líderes y listas con menos de 10 personas van juntos
    (`JUNTOS`: «otros_lugares»…) y, con más de `max_grupos` grupos, los más chicos van a «otros»."""
    personas = d.personas if personas is None else personas
    miembros: dict[Any, list[dict]] = defaultdict(list)
    for p in personas:
        v = valor_de(d, dim, p)
        for x in (v if isinstance(v, list) else [v]):
            miembros[x].append(p)
    juntos = JUNTOS.get(dim)
    if juntos:
        chicos = [k for k, ps in miembros.items() if k not in ETIQUETAS.get(dim, {}) and k != "sin"
                  and len(ps) < MINIMO_POBLACION]
        if chicos:
            otros = [p for k in chicos for p in miembros.pop(k)]
            miembros[juntos] = otros
    conteos = Counter({k: len(v) for k, v in miembros.items()})
    orden = _orden_grupos(d, dim, conteos)
    if juntos and juntos in orden:
        orden = [k for k in orden if k != juntos] + [juntos]
    if len(orden) > max_grupos:
        principales = sorted(orden, key=lambda k: -conteos[k])[:max_grupos]
        resto = [k for k in orden if k not in principales]
        orden = [k for k in orden if k in principales] + ["otros"]
        miembros["otros"] = [p for k in resto for p in miembros.pop(k)]
    return orden, miembros


# ───────────────────────────── tabla ─────────────────────────────

def _metricas(d: Datos, orden: list, miembros: dict, mets: list[str], publicado: dict) -> dict[Any, dict]:
    """Las métricas de cada grupo: los % de un atributo, protegidos entre grupos (`pcts`), y la completitud media
    (de 10 o más personas)."""
    por_metrica = {m: pcts(d, orden, miembros, METRICAS_PCT[m], publicado) for m in mets if m in METRICAS_PCT}
    out: dict[Any, dict] = {}
    for k in orden:
        x: dict[str, Any] = {}
        for m in mets:
            if m == "completitud_media":
                x[m] = media([p["completitud"] for p in miembros[k]])
            elif m in por_metrica:
                x[m] = por_metrica[m][k]
        out[k] = x
    return out


def _tabla(d: Datos, c: Consulta) -> dict:
    n = len(d.personas)
    if n < MINIMO_POBLACION:
        return dict(POCAS)
    por_defecto = ["personas"] if c.dimensiones[0] in MULTI else ["personas", "pct"]
    mets = list(dict.fromkeys(c.metricas or por_defecto))
    if len(c.dimensiones) == 2:
        return _tabla2(d, c.dimensiones[0], c.dimensiones[1], mets, n)
    dim = c.dimensiones[0]
    multi = dim in MULTI
    orden, miembros = agrupar(d, dim)
    conteos = {k: len(miembros[k]) for k in orden}
    publicado = proteger(conteos, total_conocido=not multi)
    if publicado is None:
        return dispersas("tabla", n)
    metricas = _metricas(d, orden, miembros, mets, publicado)
    filas = []
    for k in orden:
        fila: dict[str, Any] = {"valor": k, "etiqueta": etiqueta_de(d, dim, k), "personas": publicado[k]}
        if visible(publicado[k]):
            if "pct" in mets and not multi:
                fila["pct"] = pct(conteos[k], n)
            fila.update(metricas[k])
        filas.append(fila)
    out: dict[str, Any] = {"tipo": "tabla", "dimensiones": [dim], "metricas": mets, "filas": filas,
                           "ocultas": sum(1 for v in publicado.values() if not visible(v))}
    if multi:
        out["nota"] = (f"Cada persona cuenta en todos sus grupos de {dim}: los grupos no suman un total y no hay "
                       "resto." + (" Solo fuentes de trámites, reuniones, panel y planillas." if dim == "fuente"
                                   else " Sin las etiquetas sensibles."))
    else:
        out["base"] = {"personas": n}
        if dim == "lider":
            out["nota"] = NOTA_LIDER
    return out


def _tabla2(d: Datos, dim_f: str, dim_c: str, mets: list[str], n: int) -> dict:
    filas, miembros_f = agrupar(d, dim_f)
    columnas, miembros_c = agrupar(d, dim_c, max_grupos=MAX_COLUMNAS)
    columna_de = {p["id"]: k for k in columnas for p in miembros_c[k]}  # sin varios grupos: una columna por persona
    celdas: dict[tuple, list[dict]] = {(f, k): [] for f in filas for k in columnas}
    for f in filas:
        for p in miembros_f[f]:
            celdas[(f, columna_de[p["id"]])].append(p)
    m = {k: len(ps) for k, ps in celdas.items()}
    publicado = proteger_2d(m, filas, columnas)
    if publicado is None:
        return dispersas("tabla", n)
    total_fila = {f: sum(m[(f, k)] for k in columnas) for f in filas}
    salida_filas = []
    for f in filas:
        cs = []
        for k in columnas:
            v = publicado[(f, k)]
            x: dict[str, Any] = {"personas": v}
            if visible(v) and "pct" in mets:
                x["pct"] = pct(m[(f, k)], total_fila[f])
            cs.append(x)
        salida_filas.append({"valor": f, "etiqueta": etiqueta_de(d, dim_f, f), "celdas": cs,
                             "total_visible": sum(x["personas"] for x in cs if visible(x["personas"]))})
    tot_col = [sum(publicado[(f, k)] for f in filas if visible(publicado[(f, k)])) for k in columnas]
    return {"tipo": "tabla", "dimensiones": [dim_f, dim_c], "metricas": mets, "base": {"personas": n},
            "columnas": [{"valor": k, "etiqueta": etiqueta_de(d, dim_c, k)} for k in columnas],
            "filas": salida_filas, "totales_columna_visibles": tot_col,
            "ocultas": sum(1 for v in publicado.values() if not visible(v)),
            "nota": "pct es la parte de la fila. Los totales suman solo lo visible."}


# ───────────────────────────── serie ─────────────────────────────

def _eventos(d: Datos, evento: str, desde: date, hasta: date, desglose: str | None) -> list[tuple[date, Any]]:
    """(día, grupo) de cada evento del periodo, solo de personas de la base."""
    def grupo_persona(p: dict) -> Any:
        if desglose == "zona":
            return p["zona"]
        if desglose == "quien_capturo":
            return p["quien"]
        return None

    out: list[tuple[date, Any]] = []
    if evento == "altas":
        for p in d.personas:
            if p["quien"] != IMPORTACION and p["alta"] and desde <= p["alta"] <= hasta:
                out.append((p["alta"], grupo_persona(p)))
    elif evento in ("acercamientos", "efectivos", "contacto_util"):
        for a in d.acercamientos(desde, hasta):
            if evento == "efectivos" and not _efectivo(a) or evento == "contacto_util" and not _util(a):
                continue
            g = (a.get("canal") if desglose == "canal" else a.get("resultado") if desglose == "resultado"
                 else a.get("uid") if desglose == "usuario" else grupo_persona(d.por_id[a["persona_id"]]))
            out.append((a["_d"], g))
    elif evento == "reuniones":
        for r in d.reuniones(desde, hasta):
            f = modelo.fecha_valida(r.get("fecha"))
            if f:
                out.append((f, None))
    elif evento == "asistencias":
        for p in d.personas:
            for f in p["asis"]:
                if desde <= f <= hasta:
                    out.append((f, grupo_persona(p)))
    elif evento == "autorizaciones":
        for a in d.autorizaciones(desde, hasta):
            g = a.get("medio") if desglose == "medio" else grupo_persona(d.por_id[a["persona_id"]])
            out.append((a["_d"], g))
    elif evento == "completados":
        for p in d.personas:
            for campo, f in p["avance"].items():
                if desde <= f <= hasta:
                    out.append((f, campo if desglose == "campo" else grupo_persona(p)))
    return out


def tendencia(puntos: list[dict]) -> dict:
    """Total, media, último frente al anterior, pendiente (mínimos cuadrados), proyección del siguiente periodo y
    mejor y peor periodo, solo con los puntos visibles y completos (un periodo partido no se compara)."""
    vis = [(i, x["valor"]) for i, x in enumerate(puntos) if visible(x["valor"]) and not x.get("parcial")]
    todos = [x["valor"] for x in puntos if visible(x["valor"])]
    out: dict[str, Any] = {"total_visible": sum(todos), "puntos_visibles": len(todos),
                           "puntos_ocultos": sum(1 for x in puntos if not visible(x["valor"]))}
    if not vis:
        return out
    vals = [v for _, v in vis]
    out["media"] = round(statistics.fmean(vals), 1)
    if len(vis) >= 2:
        (_, a), (_, b) = vis[-2], vis[-1]
        out["ultimo"], out["anterior"] = b, a
        out["variacion_pct"] = round(100 * (b - a) / a, 1) if a else None
        xs = [i for i, _ in vis]
        mx, my = statistics.fmean(xs), statistics.fmean(vals)
        sxx = sum((x - mx) ** 2 for x in xs)
        pendiente = sum((x - mx) * (y - my) for x, y in vis) / sxx if sxx else 0.0
        out["pendiente"] = round(pendiente, 2)
        siguiente = len(puntos) if puntos[-1].get("parcial") is not True else len(puntos) - 1
        out["proyeccion_siguiente"] = max(0, round(my + pendiente * (siguiente - mx)))
    mejor = max(vis, key=lambda t: t[1])
    peor = min(vis, key=lambda t: t[1])
    out["mejor"] = {"periodo": puntos[mejor[0]]["periodo"], "valor": mejor[1]}
    out["peor"] = {"periodo": puntos[peor[0]]["periodo"], "valor": peor[1]}
    return out


def _granularidad_inicial(desde: date, hasta: date, pedida: str | None) -> tuple[str, str | None]:
    dias = (hasta - desde).days + 1
    gran = pedida or ("dia" if dias <= 45 else "semana" if dias <= 365 else "mes")
    nota = None
    while len(periodos(desde, hasta, gran)) > MAX_PUNTOS and gran != "mes":
        gran = GRANULARIDADES[GRANULARIDADES.index(gran) + 1]
        nota = f"Con {dias} días la serie va por {gran} (como mucho {MAX_PUNTOS} puntos)."
    return gran, nota


def _serie(d: Datos, c: Consulta) -> dict:
    desde, hasta = _periodo(c, 90, d.hoy)
    poblacion = c.evento != "reuniones"
    if poblacion and len(d.personas) < MINIMO_POBLACION:
        return dict(POCAS)
    eventos = _eventos(d, c.evento, desde, hasta, c.desglose)
    gran, nota = _granularidad_inicial(desde, hasta, c.granularidad)
    notas = [nota] if nota else []
    while True:
        pers = periodos(desde, hasta, gran)
        claves = [k for k, _ in pers]
        if c.desglose:
            eventos = [(f, "sin" if g is None else g) for f, g in eventos]
            tot = Counter(g for _, g in eventos)
            grupos = [g for g, _ in sorted(tot.items(), key=lambda kv: (-kv[1], str(kv[0])))]
            if len(grupos) > MAX_DESGLOSE:
                principales = set(grupos[:MAX_DESGLOSE])
                grupos = grupos[:MAX_DESGLOSE] + ["otros"]
            else:
                principales = set(grupos)
            m = {(k, g): 0 for k in claves for g in grupos}
            for f, g in eventos:
                m[(clave_periodo(f, gran), g if g in principales else "otros")] += 1
            chicas = any(0 < n < MINIMO_CELDA for n in m.values())
        else:
            conteo = Counter(clave_periodo(f, gran) for f, _ in eventos)
            m = {k: conteo.get(k, 0) for k in claves}
            chicas = any(0 < n < MINIMO_CELDA for n in m.values())
        if not poblacion or not chicas or gran == "mes":
            break
        gran = GRANULARIDADES[GRANULARIDADES.index(gran) + 1]
        notas.append(f"Se pasó a {gran}: con periodos más cortos quedaban cifras de 1 a 4.")
    parcial = dict(pers)
    out: dict[str, Any] = {"tipo": "serie", "evento": c.evento, "granularidad": gran, "desde": desde.isoformat(),
                           "hasta": hasta.isoformat()}
    if c.desglose:
        publicado = proteger_2d(m, claves, grupos) if poblacion else m
        if publicado is None:
            return dispersas("serie", len(d.personas))
        puntos = []
        for k in claves:
            vals = {str(g): publicado[(k, g)] for g in grupos}
            puntos.append({"periodo": k, **({"parcial": True} if parcial[k] else {}), "grupos": vals,
                           "valor": sum(v for v in vals.values() if visible(v))})
        out["desglose"] = c.desglose
        out["grupos"] = [{"valor": g, "etiqueta": etiqueta_de(d, "usuario" if c.desglose == "usuario"
                                                             else c.desglose, g)} for g in grupos]
        out["puntos"] = puntos
        out["tendencia"] = tendencia(puntos)
        out["tendencia"]["nota"] = "La tendencia usa el total visible de cada periodo."
    else:
        publicado = proteger(m) if poblacion else m
        if publicado is None:
            return dispersas("serie", len(d.personas))
        puntos = [{"periodo": k, **({"parcial": True} if parcial[k] else {}), "valor": publicado[k]} for k in claves]
        out["puntos"] = puntos
        out["tendencia"] = tendencia(puntos)
    if c.evento == "altas":
        notas.append("Altas del equipo (en el panel o de planillas con su planillero); las importaciones de bases no "
                     "cuentan.")
    if c.evento in ("acercamientos", "efectivos", "contacto_util"):
        notas.append("Sin los acercamientos anulados ni los automáticos de las reuniones. Efectivo = contestó o "
                     "atendió; contacto útil = efectivo sin los rechazos (no contactar, pedir sus datos).")
    if notas:
        out["nota"] = " ".join(notas)
    return out


# ───────────────────────────── embudo ─────────────────────────────

ETAPAS = (
    ("personas", "Personas vigentes", lambda d, p: True),
    ("telefono", "Con teléfono usable", lambda d, p: p["tel"]),
    ("autorizadas", "Autorizaron", lambda d, p: p["autorizada"]),
    ("habilitadas", "Contacto habilitado", lambda d, p: p["habilitado"]),
    ("abordadas", "Abordadas", lambda d, p: p["n"] >= 1),
    ("contactadas", "Contestaron (efectivo)", lambda d, p: p["efectivos"] >= 1),
    ("utiles", "Con contacto útil", lambda d, p: p["id"] in d.utiles),
    ("puesto_mesa", "Con puesto y mesa", lambda d, p: p["con_puesto"] and p["con_mesa"]),
    ("verificadas", "Votación verificada", lambda d, p: p["votacion_estado"] == "verificado"),
)
ACCION_ETAPA = {
    "telefono": "Complete teléfonos: pídalos en las reuniones y en las visitas, o marque «no lo tiene».",
    "autorizadas": "Pida la autorización de datos (planilla firmada, verbal por teléfono o presencial) antes de "
                   "contactar.",
    "habilitadas": "Confirme con el papel las autorizaciones declaradas en planilla (Importar y exportar).",
    "abordadas": "Ponga a los consultores a llamar a las personas habilitadas que nadie ha llamado.",
    "contactadas": "Cambie de franja horaria o de canal: muchas no contestan.",
    "utiles": "Revise el guion: muchas contestan pero rechazan o piden sus datos.",
    "puesto_mesa": "Pida el puesto y la mesa en cada contacto (consulta de la Registraduría).",
    "verificadas": "Verifique la votación con la consulta de la Registraduría.",
}


def _contar_etapas(d: Datos, ps: list[dict]) -> list[int]:
    cuentas = [0] * len(ETAPAS)
    for p in ps:
        for i, (_, _, cond) in enumerate(ETAPAS):
            if not cond(d, p):
                break
            cuentas[i] += 1
    return cuentas


def _etapas(cuentas: list[int]) -> tuple[list[dict], dict | None]:
    """Las etapas publicables de un embudo: cada una con la regla de `atributo` frente a la anterior y frente a la
    última publicada (que ninguna diferencia sea de 1 a 4 personas: con una etapa oculta en medio, sus dos vecinas
    publicadas la acotarían), la tasa desde la anterior si las dos se ven y la mayor caída."""
    salida, caida = [], None
    previa_visible = None
    for i, (clave, nombre, _) in enumerate(ETAPAS):
        n = cuentas[i]
        v = celda(n) if i == 0 else atributo(n, cuentas[i - 1])
        if i > 0 and visible(v) and (previa_visible is None or not visible(atributo(n, previa_visible[1]))):
            v = OCULTA
        x: dict[str, Any] = {"etapa": clave, "nombre": nombre, "personas": v}
        if i > 0 and visible(v) and previa_visible is not None and previa_visible[0] == i - 1:
            tasa = pct(n, cuentas[i - 1])
            x["tasa_desde_anterior"] = tasa
            if tasa is not None and (caida is None or tasa < caida["tasa"]):
                caida = {"desde": ETAPAS[i - 1][0], "hasta": clave, "tasa": tasa}
        if i > 0:
            x["pct_del_total"] = pct(n, cuentas[0]) if visible(v) else None
        if visible(v):
            previa_visible = (i, n)
        salida.append(x)
    return salida, caida


def _embudo(d: Datos, c: Consulta) -> dict:
    n = len(d.personas)
    if n < MINIMO_POBLACION:
        return dict(POCAS)
    cuentas = _contar_etapas(d, d.personas)
    etapas, caida = _etapas(cuentas)
    rechazos = sum(1 for p in d.personas if p["abordaje_estado"] == "no_contactar")
    asistieron = sum(1 for p in d.personas if p["asistencias"] > 0)
    out: dict[str, Any] = {
        "tipo": "embudo", "base": {"personas": n}, "etapas": etapas,
        "aparte": {"rechazos": atributo(rechazos, n), "asistieron_a_reunion": atributo(asistieron, n),
                   "pct_asistieron": pct(asistieron, n)},
        "nota": ("Cada etapa cuenta a quienes cumplen también las anteriores. «Contestaron» incluye a quienes "
                 "rechazaron; «contacto útil» no. Rechazos: pidieron no ser contactados.")}
    if caida:
        out["mayor_caida"] = {**caida, "accion": ACCION_ETAPA.get(caida["hasta"])}
    if c.dimensiones:
        dim = c.dimensiones[0]
        orden, miembros = agrupar(d, dim)
        publicado = proteger({k: len(miembros[k]) for k in orden})
        out["dimension"] = dim
        if publicado is None:
            out["nota_grupos"] = NOTA_DISPERSAS
            return out
        # Por grupo, lo que se quedó en cada etapa es una tabla grupos × etapas: sus filas suman cada grupo y sus
        # columnas, lo que se quedó en cada etapa del embudo general. Se protege entera (`partir`) y una etapa de un
        # grupo se publica solo si todo lo que se quedó antes quedó visible (si no, restando se vería lo oculto)
        cuentas_g = {k: _contar_etapas(d, miembros[k]) for k in orden}
        n_et = len(ETAPAS)
        quedaron = {k: [c[i] - (c[i + 1] if i + 1 < n_et else 0) for i in range(n_et)] for k, c in cuentas_g.items()}
        pub = partir(orden, quedaron, [e[0] for e in ETAPAS], publicado)
        if pub is None:
            out["nota_grupos"] = NOTA_DISPERSAS
        grupos = []
        for k in orden:
            g: dict[str, Any] = {"valor": k, "etiqueta": etiqueta_de(d, dim, k), "personas": publicado[k]}
            if pub is not None and visible(publicado[k]) and len(miembros[k]) >= MINIMO_POBLACION:
                c = cuentas_g[k]
                etapas_g, caida_g, previa = [], None, None
                for i, (clave, _, _) in enumerate(ETAPAS):
                    ve = all(visible(pub[(k, ETAPAS[j][0])]) for j in range(i))
                    v = c[i] if ve else celda(c[i]) if 0 < c[i] < MINIMO_CELDA else OCULTA
                    x: dict[str, Any] = {"etapa": clave, "personas": v}
                    if i > 0 and visible(v) and visible(previa):
                        x["tasa_desde_anterior"] = pct(c[i], c[i - 1])
                        t = x["tasa_desde_anterior"]
                        if t is not None and (caida_g is None or t < caida_g["tasa"]):
                            caida_g = {"desde": ETAPAS[i - 1][0], "hasta": clave, "tasa": t}
                    etapas_g.append(x)
                    previa = v
                g["etapas"] = etapas_g
                if caida_g:
                    g["mayor_caida"] = caida_g
            grupos.append(g)
        out["grupos"] = grupos
    return out


# ───────────────────────────── cobertura y ritmo ─────────────────────────────

def _habilitados(pu: dict) -> dict:
    h = pu.get("habilitados") if isinstance(pu.get("habilitados"), dict) else {}
    return {k: h.get(k) if isinstance(h.get(k), int) and h.get(k) > 0 else None
            for k in ("total", "mujeres", "hombres")}


def _casillas(d: Datos) -> tuple[list[str], dict[str, list[dict]]]:
    miembros: dict[str, list[dict]] = defaultdict(list)
    for p in d.personas:
        miembros[d.puesto_de(p)].append(p)
    pues = [f"p{i}" for i in sorted(d.puestos, key=lambda i: str(d.puestos[i].get("codigo") or ""))]
    return pues + [k for k in ORDEN["puesto"] if k in miembros], miembros


def _cobertura(d: Datos, c: Consulta) -> dict:
    n = len(d.personas)
    if n < MINIMO_POBLACION:
        return dict(POCAS)
    meta_pct = c.meta_pct or 30
    orden, miembros = _casillas(d)
    miembros = {k: miembros.get(k, []) for k in orden}
    publicado = proteger({k: len(miembros[k]) for k in orden})
    if publicado is None:
        return dispersas("cobertura", n)
    # Mujeres y hombres, con mesa y verificados de cada puesto: tablas casillas × clase, protegidas enteras (el total
    # de mujeres, o de verificados, sale en otras tablas y dejaría deducir el de un puesto restando los demás)
    sexo = {k: [sum(1 for p in ps if p["sexo"] == "F"), sum(1 for p in ps if p["sexo"] == "M")] for k, ps in
            miembros.items()}
    sexo_pub = partir(orden, {k: [f, m_, len(miembros[k]) - f - m_] for k, (f, m_) in sexo.items()},
                      ["F", "M", "otro"], publicado)
    con_mesa = conteos_atributo(d, orden, miembros, lambda d_, p: p["con_mesa"], publicado)
    verificados = conteos_atributo(d, orden, miembros, lambda d_, p: p["votacion_estado"] == "verificado",
                                   publicado)
    puestos, casillas = [], {}
    total_reg = total_hab = 0
    for k in orden:
        ps = miembros.get(k, [])
        if not k.startswith("p"):
            casillas[k] = publicado[k]
            continue
        pu = d.puestos[int(k[1:])]
        hab = _habilitados(pu)
        reg = len(ps)
        fila: dict[str, Any] = {"puesto_id": pu["_id"], "codigo": pu.get("codigo"), "nombre": pu.get("nombre"),
                                "habilitados": hab, "mesas": pu.get("mesas"), "registrados": publicado[k]}
        if visible(publicado[k]):
            total_reg += reg
            mujeres, hombres = sexo[k]
            # «otro» no sale, pero se deduce (registrados − mujeres − hombres): `partir` lo trató como publicado
            f_pub = sexo_pub[(k, "F")] if sexo_pub else OCULTA
            m_pub = sexo_pub[(k, "M")] if sexo_pub else OCULTA
            fila.update({
                "cobertura_pct": pct(reg, hab["total"]) if hab["total"] else None,
                "mujeres": f_pub, "hombres": m_pub,
                "cobertura_mujeres_pct": pct(mujeres, hab["mujeres"]) if hab["mujeres"] and visible(f_pub) else None,
                "cobertura_hombres_pct": pct(hombres, hab["hombres"]) if hab["hombres"] and visible(m_pub) else None,
                "con_mesa": con_mesa[k], "verificados": verificados[k]})
            if hab["total"]:
                meta = math.ceil(meta_pct * hab["total"] / 100)
                fila["meta"] = meta
                fila["faltan_para_meta"] = max(0, meta - reg)
            mesas = pu.get("mesas") if isinstance(pu.get("mesas"), int) and pu.get("mesas") > 0 else None
            if mesas and hab["total"]:
                est = round(hab["total"] / mesas)
                por_mesa = Counter((p["votacion"] or {}).get("mesa") for p in ps if p["con_mesa"])
                fila["estimacion_habilitados_por_mesa"] = est
                fila["mesas_sobre_estimacion"] = sum(1 for m, x in por_mesa.items() if m is not None and x > est)
        if hab["total"]:
            total_hab += hab["total"]
        puestos.append(fila)
    return {"tipo": "cobertura", "eleccion": d.eleccion, "meta_pct": meta_pct, "base": {"personas": n},
            "puestos": puestos, "casillas": casillas,
            "total": {"registrados_visibles": total_reg, "habilitados": total_hab,
                      "cobertura_pct": pct(total_reg, total_hab) if total_hab else None},
            "nota": ("Registrados = personas vigentes de la base con ese puesto de la elección vigente. Los "
                     "habilitados son del censo electoral por puesto; por mesa solo hay una estimación (habilitados ÷ "
                     "mesas). "
                     "«otra_eleccion»: su puesto es de otra elección o no dice de cuál.")}


def _ritmo(d: Datos, c: Consulta) -> dict:
    meta_fecha = date.fromisoformat(c.fecha_meta)
    if meta_fecha <= d.hoy:
        raise HTTPException(422, {"mensaje": "fecha_meta debe ser posterior a hoy", "codigo": "invalido"})
    if (meta_fecha - d.hoy).days > 1100:
        raise HTTPException(422, {"mensaje": "fecha_meta no puede estar a más de 3 años", "codigo": "invalido"})
    n = len(d.personas)
    if n < MINIMO_POBLACION:
        return dict(POCAS)
    meta_pct = c.meta_pct or 30
    semanas = c.semanas or 8
    desde = d.hoy - timedelta(days=7 * semanas)
    restantes = (meta_fecha - d.hoy).days / 7
    orden, miembros = _casillas(d)
    miembros = {k: miembros.get(k, []) for k in orden}
    publicado = proteger({k: len(miembros[k]) for k in orden})
    if publicado is None:
        return dispersas("ritmo", n)

    def es_nueva(d_: Datos, p: dict) -> bool:
        return (p["avance"].get("puesto") or p["alta"] or date.min) >= desde

    nuevos_pub_de = conteos_atributo(d, orden, miembros, es_nueva, publicado)
    filas = []
    for k in orden:
        if not k.startswith("p"):
            continue
        pu = d.puestos[int(k[1:])]
        ps = miembros.get(k, [])
        reg = len(ps)
        hab = _habilitados(pu)["total"]
        fila: dict[str, Any] = {"puesto_id": pu["_id"], "codigo": pu.get("codigo"), "nombre": pu.get("nombre"),
                                "habilitados": hab, "registrados": publicado[k]}
        if visible(publicado[k]):
            nuevos = sum(1 for p in ps if es_nueva(d, p))
            nuevos_pub = nuevos_pub_de[k]
            meta = math.ceil(meta_pct * hab / 100) if hab else None
            fila["cobertura_pct"] = pct(reg, hab) if hab else None
            if meta is not None:
                fila["meta"] = meta
                fila["faltan"] = max(0, meta - reg)
                fila["necesarias_por_semana"] = round(max(0, meta - reg) / restantes, 1)
            if visible(nuevos_pub):
                ritmo = nuevos / semanas
                proyeccion = round(reg + ritmo * restantes)
                fila.update({"nuevos_en_ventana": nuevos, "ritmo_semanal": round(ritmo, 1),
                             "proyeccion": proyeccion,
                             "cobertura_proyectada_pct": round(100 * proyeccion / hab, 1) if hab else None,
                             "llega": proyeccion >= meta if meta is not None else None})
            else:
                fila["ritmo_semanal"] = None
                fila["nota"] = "Ritmo oculto: muy pocas personas nuevas en la ventana"
        filas.append(fila)
    brechas = [f for f in filas if isinstance(f.get("faltan"), int)]
    peor = max(brechas, key=lambda f: f["faltan"]) if brechas else None
    return {"tipo": "ritmo", "fecha_meta": c.fecha_meta, "meta_pct": meta_pct, "semanas_ventana": semanas,
            "semanas_restantes": round(restantes, 1), "base": {"personas": n}, "puestos": filas,
            "mayor_brecha": {"codigo": peor["codigo"], "nombre": peor["nombre"], "faltan": peor["faltan"],
                             "necesarias_por_semana": peor["necesarias_por_semana"]} if peor else None,
            "nota": ("Ritmo = personas que tienen ese puesto desde las últimas semanas (cuando se llenó el puesto o, "
                     "si llegó con él, su alta), por semana. La proyección supone que el ritmo sigue igual.")}


# ───────────────────────────── brechas ─────────────────────────────

def _brechas(d: Datos, c: Consulta) -> dict:
    n = len(d.personas)
    if n < MINIMO_POBLACION:
        return dict(POCAS)
    dias = c.dias or 90
    desde = d.hoy - timedelta(days=dias - 1)
    por_lugar: dict[Any, list[dict]] = defaultdict(list)
    for p in d.personas:
        por_lugar[p["lugar"] if p["lugar"] is not None else "sin"].append(p)
    grupos: dict[Any, list[dict]] = {}
    otros: list[dict] = []
    for lid, ps in por_lugar.items():
        if lid != "sin" and len(ps) < MINIMO_POBLACION:
            otros.extend(ps)
        elif lid != "sin":
            grupos[lid] = ps
    if otros:
        grupos["otros_lugares"] = otros
    if por_lugar.get("sin"):
        grupos["sin"] = por_lugar["sin"]
    orden = list(grupos)
    conteos = proteger({k: len(grupos[k]) for k in orden})
    if conteos is None:
        return dispersas("brechas", n)
    reuniones = Counter(r.get("lugar_id") for r in d.reuniones(desde, d.hoy) if r.get("lugar_id") is not None)
    utiles = {a["persona_id"] for a in d.acercamientos(desde, d.hoy) if _util(a)}
    # Cada % y cada conteo por lugar, protegido entre lugares (`pcts`): el total de cada uno sale en otras tablas
    medidas = {
        "pct_telefono_usable": lambda d_, p: p["tel"],
        "pct_contactables": lambda d_, p: p["tel"] and p["habilitado"],
        "pct_ubicadas_exactas": lambda d_, p: p["precision"] == "exacta",
        "pct_contacto_util_en_ventana": lambda d_, p: p["id"] in utiles,
        "pct_contactadas_alguna_vez": lambda d_, p: p["efectivos"] >= 1,
    }
    por_medida = {m: pcts(d, orden, grupos, f, conteos) for m, f in medidas.items()}
    util_n = conteos_atributo(d, orden, grupos, medidas["pct_contacto_util_en_ventana"], conteos)
    sin_contacto = conteos_atributo(d, orden, grupos, lambda d_, p: not p["ultimo_contacto"], conteos)
    filas = []
    for lid in orden:
        if lid in ("otros_lugares", "sin"):
            continue
        ps = grupos[lid]
        k = len(ps)
        n_util = sum(1 for p in ps if p["id"] in utiles)
        contactadas = sum(1 for p in ps if p["efectivos"] >= 1)
        recientes = sum(1 for p in ps if p["ultimo_contacto"] and p["ultimo_contacto"] >= desde)
        dias_ult = [(d.hoy - p["ultimo_contacto"]).days for p in ps if p["ultimo_contacto"]]
        indice = 100 * (0.35 * n_util / k + 0.25 * contactadas / k + 0.25 * recientes / k
                        + 0.15 * min(1, reuniones.get(lid, 0) / 2))
        lg = d.lugares.get(lid) or {}
        fila: dict[str, Any] = {
            "lugar_id": lid, "nombre": lg.get("nombre"), "tipo_lugar": lg.get("tipo"), "zona": lg.get("zona"),
            "personas": conteos[lid], "reuniones_en_ventana": reuniones.get(lid, 0),
            "mediana_dias_desde_ultimo_contacto": round(statistics.median(dias_ult)) if len(dias_ult) >= 10 else None,
            "indice_atencion": int(round(indice, -1)), "_indice": indice}
        if visible(conteos[lid]):
            fila.update({m: por_medida[m][lid] for m in medidas})
            fila.update(contacto_util_en_ventana=util_n[lid], sin_ningun_contacto=sin_contacto[lid])
        filas.append(fila)
    filas.sort(key=lambda f: (f.pop("_indice"), -len(grupos[f["lugar_id"]])))
    out: dict[str, Any] = {"tipo": "brechas", "dias": dias, "base": {"personas": n}, "lugares": filas[:MAX_GRUPOS],
                           "sin_lugar": conteos.get("sin", 0)}
    if otros:
        out["otros_lugares"] = {"lugares": len({p["lugar"] for p in otros}), "personas": conteos["otros_lugares"],
                                "nota": "Lugares con menos de 10 personas: no se muestran uno por uno"}
    out["nota"] = (f"Lugares con 10 o más personas, del más desatendido al más atendido. Índice de atención (0 a 100, "
                   f"en decenas para que no deje deducir cifras ocultas) = 35 % contacto útil en {dias} días + 25 % "
                   f"contactadas alguna vez + 25 % con contacto reciente ({dias} días) + 15 % reuniones en {dias} días "
                   "(2 o más = completo).")
    return out


# ───────────────────────────── equipo ─────────────────────────────

def _mediana(vals: list[float]) -> float | None:
    vals = [v for v in vals if v is not None]
    return round(statistics.median(vals), 1) if vals else None


def _equipo(d: Datos, c: Consulta) -> dict:
    desde, hasta = _periodo(c, 30, d.hoy)
    td, th = _utc(desde), _utc(hasta + timedelta(days=1))
    uids = list(d.usuarios)
    ind = uapi.indicadores(d.db, uids, desde, hasta, td, th, tratables=True)
    sin = sorted(d.no_autorizaron)
    acerc: dict[int, Counter] = defaultdict(Counter)
    personas_u: dict[int, set] = defaultdict(set)
    for a in d.db.acercamientos.find({"ts": {"$gte": td, "$lt": th}, "anulado": {"$ne": True}, "auto": {"$ne": True},
                                      **({"persona_id": {"$nin": sin}} if sin else {})},
                                     {"uid": 1, "resultado": 1, "efectivo": 1, "fuera_de_horario": 1, "persona_id": 1}):
        u = a.get("uid")
        if not isinstance(u, int):
            continue
        k = acerc[u]
        k["acercamientos"] += 1
        k["efectivos"] += _efectivo(a)
        k["utiles"] += _util(a)
        k["rechazos"] += a.get("resultado") in RECHAZOS
        k["fuera_de_horario"] += a.get("fuera_de_horario") is True
        if a.get("persona_id") is not None:
            personas_u[u].add(a["persona_id"])
    reuniones = Counter(r.get("creado_por_uid") for r in d.db.reuniones.find(
        {"creado_en": {"$gte": td, "$lt": th}}, {"creado_por_uid": 1}))
    filas = []
    for uid in uids:
        u = d.usuarios[uid]
        pl, k = ind[uid]["planillero"], acerc.get(uid, Counter())
        fila = {"uid": uid, "usuario": u.get("usuario"), "nombre": u.get("nombre"), "rol": u.get("rol"),
                "activo": bool(u.get("activo")), "altas": pl["creadas"], "altas_netas": pl["creadas_netas"],
                "altas_de_planilla": pl["creadas_por_planilla"], "actualizadas": pl["actualizadas"],
                "campos_completados": sum(v for kk, v in pl["completados"].items() if kk != "regimen_salud"),
                "acercamientos": k["acercamientos"], "personas_abordadas": len(personas_u.get(uid, ())),
                "efectivos": k["efectivos"], "contactos_utiles": k["utiles"], "rechazos": k["rechazos"],
                "tasa_contacto_util": round(100 * k["utiles"] / k["acercamientos"], 1)
                if k["acercamientos"] >= MINIMO_POBLACION else None,
                "pct_fuera_de_horario": round(100 * k["fuera_de_horario"] / k["acercamientos"], 1)
                if k["acercamientos"] >= MINIMO_POBLACION else None,
                "reuniones_creadas": reuniones.get(uid, 0), "asistentes_registrados": pl["asistencias"]}
        activo_periodo = any(fila[x] for x in ("altas", "actualizadas", "acercamientos", "reuniones_creadas",
                                               "asistentes_registrados"))
        if fila["activo"] or activo_periodo:
            fila["_actividad"] = activo_periodo
            filas.append(fila)
    medianas = {}
    for m in ("altas", "actualizadas", "acercamientos", "contactos_utiles", "tasa_contacto_util", "campos_completados"):
        medianas[m] = _mediana([f[m] for f in filas if f["_actividad"] and f[m] not in (None, 0)])
    for f in filas:
        f.pop("_actividad")
        f["frente_a_mediana"] = {
            m: (round(100 * (f[m] - med) / med) if isinstance(f[m], (int, float)) and med else None)
            for m, med in medianas.items() if m in ("altas", "acercamientos", "tasa_contacto_util")}
    filas.sort(key=lambda f: (-(f["acercamientos"] + f["altas"] + f["actualizadas"]), f["usuario"] or ""))
    out: dict[str, Any] = {"tipo": "equipo", "desde": desde.isoformat(), "hasta": hasta.isoformat(),
                           "usuarios": filas[:MAX_GRUPOS], "mediana_del_equipo": medianas,
                           "nota": ("Lo que hizo cada usuario, sin contar lo hecho con quienes no autorizaron. Las "
                                    "altas de planilla cuentan para el planillero que la capturó. Acercamientos sin "
                                    "los automáticos de las reuniones. La mediana es entre quienes hicieron algo de "
                                    "eso; frente_a_mediana: % por encima (+) o por debajo (−) de ella.")}
    if c.granularidad:
        out["series"] = []
        for f in filas[:MAX_GRUPOS]:
            s = uapi.serie(d.db, f["uid"], td, th, c.granularidad, tratables=True)
            if s:
                out["series"].append({"usuario": f["usuario"], "puntos": [
                    {"periodo": x["fecha"], "altas": x["creadas"], "actualizadas": x["actualizadas"]} for x in s]})
    return out


# ───────────────────────────── calidad ─────────────────────────────

def _calidad(d: Datos, c: Consulta) -> dict:
    n = len(d.personas)
    if n < MINIMO_POBLACION:
        return dict(POCAS)
    db = d.db
    comp = Counter(_completitud(p["completitud"]) for p in d.personas)
    comp_pub = proteger({k: comp.get(k, 0) for k in ORDEN["completitud"]})
    faltan = Counter(x for p in d.personas for x in p["faltan"])
    bd.cerrar_coincidencias_imposibles(db)
    ids = d.por_id
    coinc = set()
    for x in db.coincidencias.find({"estado": "pendiente"}, {"persona_id": 1, "candidato_id": 1}):
        par = (x.get("persona_id"), x.get("candidato_id"))
        if all(i in ids for i in par):  # con una sola de la base, contaría algo de quien no autorizó (su duplicado)
            coinc |= set(par)
    conflictos = Counter(x.get("motivo") or "otro" for x in db.conflictos_cedula.find(
        {"estado": "pendiente"}, {"persona_id": 1, "motivo": 1}) if x.get("persona_id") in ids)
    hoy = d.hoy.isoformat()
    abiertas, vencidas = Counter(), Counter()
    for s in db.solicitudes.find({"estado": {"$in": ["pendiente", "en_tramite"]}},
                                 {"persona_id": 1, "tipo": 1, "vence": 1}):
        if s.get("persona_id") in d.no_autorizaron:
            continue
        abiertas[s.get("tipo") or "otro"] += 1
        if s.get("vence") and str(s["vence"]) < hoy:
            vencidas[s.get("tipo") or "otro"] += 1
    sit = db.personas.count_documents({"$and": [consulta_mongo(db, d.params, d.hoy, vigentes=False),
                                                {"situacion.estado": {"$in": ["fallecida", "no_reside"]},
                                                 "situacion.confirmada": {"$ne": True}}]})
    con_lugar = {p["lugar"] for p in d.personas if p["lugar"] is not None}
    sin_punto = sum(1 for lid in con_lugar if (d.lugares.get(lid) or {}).get("lat") is None)
    cuenta = lambda f: sum(1 for p in d.personas if f(p))  # noqa: E731
    indicadores = {
        "autorizaciones_por_confirmar": cuenta(lambda p: p["consentimiento"] == "por_confirmar"),
        "con_telefono_equivocado_o_inexistente": cuenta(lambda p: p["tel_malo"]),
        "votacion_por_confirmar": cuenta(lambda p: p["votacion_estado"] == "por_confirmar"),
        "puesto_escrito_sin_catalogo": cuenta(lambda p: d.puesto_de(p) == "texto_sin_catalogo"),
        "lugar_escrito_sin_reconocer": cuenta(lambda p: p["lugar"] is None and p["lugar_texto"]),
        "pedido_de_actualizacion": cuenta(lambda p: p["requiere"] != "no"),
    }
    out: dict[str, Any] = {
        "tipo": "calidad", "base": {"personas": n},
        "completitud": [{"rango": k, "personas": comp_pub[k]} for k in ORDEN["completitud"]] if comp_pub else None,
        "completitud_media": media([p["completitud"] for p in d.personas]),
        "faltan": [{"campo": k, "etiqueta": modelo.ETIQUETAS_CAMPOS.get(k, k),
                    "personas": atributo(faltan.get(k, 0), n), "pct": pct(faltan.get(k, 0), n)}
                   for k in modelo.CAMPOS_FALTAN],
        "indicadores": {k: {"personas": atributo(v, n), "pct": pct(v, n)} for k, v in indicadores.items()},
        "coincidencias_pendientes_personas": celda(len(coinc)),
        # Por tipo, sin total publicado en otra parte: basta «<5» (no hay resta que deshacer)
        "conflictos_cedula_pendientes": proteger(dict(conflictos), total_conocido=False),
        "solicitudes": {"abiertas": proteger(dict(abiertas), total_conocido=False),
                        "vencidas": proteger(dict(vencidas), total_conocido=False)},
        "situaciones_sin_confirmar": celda(sit),
        "lugares_sin_punto_con_personas": sin_punto,
        "nota": ("Faltan: el dato vacío y sin marca vigente de «no lo tiene». Las solicitudes de quienes no "
                 "autorizaron se gestionan en Calidad del panel y no se cuentan aquí."),
    }
    if c.dimensiones == ["zona"]:
        orden, miembros = agrupar(d, "zona")
        publicado = proteger({k: len(miembros[k]) for k in orden}) or {k: OCULTA for k in orden}
        # Los % por zona, protegidos entre zonas (`pcts`): el total de cada uno sale arriba
        falta = {campo: pcts(d, orden, miembros, lambda d_, p, c_=campo: c_ in p["faltan"], publicado)
                 for campo in modelo.CAMPOS_FALTAN}
        por_confirmar = pcts(d, orden, miembros, lambda d_, p: p["consentimiento"] == "por_confirmar", publicado)
        zonas = []
        for k in orden:
            z: dict[str, Any] = {"zona": k, "personas": publicado[k]}
            if visible(publicado[k]):
                z["faltan"] = [{"campo": campo, "pct": falta[campo][k]} for campo in modelo.CAMPOS_FALTAN]
                z["completitud_media"] = media([p["completitud"] for p in miembros[k]])
                z["pct_autorizaciones_por_confirmar"] = por_confirmar[k]
            zonas.append(z)
        out["por_zona"] = zonas
    return out


# ───────────────────────────── anomalías ─────────────────────────────

def _picos(por_dia: dict[int, Counter], dias: int, d: Datos, tipo: str) -> list[dict]:
    """Por usuario: los días con 10 o más y a 3 desviaciones o más de su propia media diaria (con los días sin nada)."""
    out = []
    for uid, cont in por_dia.items():
        vals = list(cont.values()) + [0] * max(0, dias - len(cont))
        if len(vals) < 7:
            continue
        mu = statistics.fmean(vals)
        sd = statistics.pstdev(vals)
        if sd == 0:
            continue
        picos = sorted((f, x) for f, x in cont.items() if x >= 10 and (x - mu) / sd >= 3)
        if picos:
            out.append({"usuario": d.nombre_usuario(uid), "tipo": tipo, "dias_pico": len(picos),
                        "dias": [{"fecha": f.isoformat(), "cantidad": x} for f, x in picos[-5:]],
                        "media_diaria": round(mu, 1)})
    return sorted(out, key=lambda x: -x["dias_pico"])


def _anomalias(d: Datos, c: Consulta) -> dict:
    desde, hasta = _periodo(c, 90, d.hoy)
    td, th = _utc(desde), _utc(hasta + timedelta(days=1))
    dias = (hasta - desde).days + 1
    sin = sorted(d.no_autorizaron)
    db = d.db
    altas: dict[int, Counter] = defaultdict(Counter)
    # Solo las altas hechas en el panel: las de una importación (con o sin planillero) no son de ese día
    for a in db.auditoria.find({"accion": "crear", "entidad": "persona", "ts": {"$gte": td, "$lt": th},
                                "capturado_por": {"$exists": False}, **({"entidad_id": {"$nin": sin}} if sin else {})},
                               {"uid": 1, "ts": 1}):
        if isinstance(a.get("uid"), int) and (f := _dia(a.get("ts"))):
            altas[a["uid"]][f] += 1
    acerc: dict[int, Counter] = defaultdict(Counter)
    fuera: dict[int, Counter] = defaultdict(Counter)
    for a in db.acercamientos.find({"ts": {"$gte": td, "$lt": th}, "anulado": {"$ne": True}, "auto": {"$ne": True},
                                    **({"persona_id": {"$nin": sin}} if sin else {})},
                                   {"uid": 1, "ts": 1, "fecha": 1, "fuera_de_horario": 1}):
        u = a.get("uid")
        f = modelo.fecha_valida(a.get("fecha")) or _dia(a.get("ts"))
        if isinstance(u, int) and f:
            acerc[u][f] += 1
            fuera[u]["n"] += 1
            fuera[u]["fuera"] += a.get("fuera_de_horario") is True
    fuera_filas = [{"usuario": d.nombre_usuario(u), "acercamientos": x["n"],
                    "pct_fuera_de_horario": round(100 * x["fuera"] / x["n"], 1)}
                   for u, x in fuera.items() if x["n"] >= MINIMO_TASA and x["fuera"]]
    fuera_filas.sort(key=lambda x: -x["pct_fuera_de_horario"])
    # Números en más de 3 fichas de la base (solo cuántos grupos y cuántas fichas)
    compartidos = list(db.personas.aggregate([
        {"$match": d.consulta}, {"$unwind": "$telefonos"},
        {"$match": {"telefonos.estado": {"$in": sorted(modelo.USABLES)}}},
        {"$group": {"_id": "$telefonos.numero", "fichas": {"$addToSet": "$_id"}}},
        {"$project": {"n": {"$size": "$fichas"}}}, {"$match": {"n": {"$gt": 3}}},
        {"$group": {"_id": None, "grupos": {"$sum": 1}, "fichas": {"$sum": "$n"}}}], maxTimeMS=MAX_MS))
    comp = compartidos[0] if compartidos else {"grupos": 0, "fichas": 0}
    ids = d.por_id
    digitaciones = sum(1 for x in db.conflictos_cedula.find({"estado": "pendiente", "motivo": "posible_digitacion"},
                                                           {"persona_id": 1}) if x.get("persona_id") in ids)
    unidas = _unidas(d, desde, hasta)
    mesas_sobre = 0
    por_mesa: Counter = Counter()
    rural_urbana = 0
    for p in d.personas:
        k = d.puesto_de(p)
        if k.startswith("p"):
            pu = d.puestos[int(k[1:])]
            m = (p["votacion"] or {}).get("mesa")
            if isinstance(m, int):
                por_mesa[(k, m)] += 1
            if p["zona"] == "urbana" and (pu.get("area") == "rural" or str(pu.get("codigo") or "").startswith("99")):
                rural_urbana += 1
    for (k, m), x in por_mesa.items():
        pu = d.puestos[int(k[1:])]
        hab, mesas = _habilitados(pu)["total"], pu.get("mesas")
        if hab and isinstance(mesas, int) and mesas > 0 and x > hab / mesas:
            mesas_sobre += 1
    return {"tipo": "anomalias", "desde": desde.isoformat(), "hasta": hasta.isoformat(),
            "picos": (_picos(altas, dias, d, "altas") + _picos(acerc, dias, d, "acercamientos"))[:MAX_GRUPOS],
            "fuera_de_horario": fuera_filas[:MAX_GRUPOS],
            "telefonos_compartidos": {"grupos_de_mas_de_3_fichas": comp["grupos"], "fichas": celda(comp["fichas"])},
            "posibles_digitaciones_de_cedula_pendientes": celda(digitaciones),
            "altas_luego_unidas_como_duplicadas": unidas[:MAX_GRUPOS],
            "mesas_con_mas_registrados_que_la_estimacion": mesas_sobre,
            "urbanas_con_puesto_rural": celda(rural_urbana),
            "nota": ("Solo conteos. Picos: días de 10 o más con 3 desviaciones o más sobre la media diaria del usuario "
                     "(sin las altas de importaciones). Un pico no es un error: revíselo con la persona.")}


def _unidas(d: Datos, desde: date | None, hasta: date | None) -> list[dict]:
    """Por quién capturó: altas que después se unieron con otra ficha (duplicados), sin importaciones de bases."""
    q: dict = {"fusionada_en": {"$ne": None}, "eliminado": {"$ne": True}, "consentimiento": {"$ne": "no"}}
    if desde is not None:
        q["creado_en"] = {"$gte": _utc(desde), "$lt": _utc(hasta + timedelta(days=1))}
    cont: Counter = Counter()
    for x in d.db.personas.find(q, {"creado_por.uid": 1, "creado_por.capturado_por": 1, "fuentes": 1}):
        fuentes = x.get("fuentes") or []
        cp = x.get("creado_por") or {}
        if fuentes and fuentes[0] in IMPORTADAS:
            quien = cp.get("capturado_por") if fuentes[0] == "planilla" else None
        else:
            quien = cp.get("uid")
        if isinstance(quien, int) and not isinstance(quien, bool):
            cont[quien] += 1
    return [{"usuario": d.nombre_usuario(u), "uid": u, "unidas": x} for u, x in cont.most_common()]


# ───────────────────────────── cohortes ─────────────────────────────

def _cohortes(d: Datos, c: Consulta) -> dict:
    hasta = date.fromisoformat(c.hasta) if c.hasta else d.hoy
    desde = date.fromisoformat(c.desde) if c.desde else (hasta.replace(day=1) - timedelta(days=330)).replace(day=1)
    if desde > hasta:
        raise HTTPException(422, {"mensaje": "«desde» no puede ser posterior a «hasta»", "codigo": "invalido"})
    if (hasta - desde).days >= MAX_DIAS:
        raise HTTPException(422, {"mensaje": f"El periodo no puede pasar de {MAX_DIAS} días", "codigo": "invalido"})
    if len(d.personas) < MINIMO_POBLACION:
        return dict(POCAS)
    grupos: dict[str, list[dict]] = defaultdict(list)
    for p in d.personas:
        if p["quien"] != IMPORTACION and p["alta"] and desde <= p["alta"] <= hasta:
            grupos[p["mes_alta"]].append(p)
    meses = sorted(grupos)
    publicado = proteger({m: len(grupos[m]) for m in meses})
    if publicado is None:
        return dispersas("cohortes", len(d.personas))

    def en_30(d_: Datos, p: dict) -> bool:
        prim = _dia((d_.contactos.get(p["id"]) or {}).get("primero"))
        return prim is not None and (prim - p["alta"]).days <= 30

    # Cada % por mes, protegido entre meses (`pcts`): el total de cada atributo sale en otras tablas
    medidas = {"pct_abordadas_en_30_dias": en_30, "pct_contactadas": lambda d_, p: p["efectivos"] >= 1,
               "pct_con_cedula": lambda d_, p: p["ced"], "pct_autorizadas": lambda d_, p: p["autorizada"],
               "pct_asistieron": lambda d_, p: p["asistencias"] > 0}
    por_medida = {k: pcts(d, meses, grupos, f, publicado) for k, f in medidas.items()}
    filas = []
    for m in meses:
        fila: dict[str, Any] = {"mes": m, "personas": publicado[m]}
        if visible(publicado[m]):
            fin = _siguiente(date.fromisoformat(m + "-01"), "mes") - timedelta(days=1)
            completa = (d.hoy - fin).days >= 30
            fila.update({k: por_medida[k][m] for k in medidas})
            if not completa:
                fila["pct_abordadas_en_30_dias"] = None
                fila["en_curso"] = True
        filas.append(fila)
    return {"tipo": "cohortes", "desde": desde.isoformat(), "hasta": hasta.isoformat(), "cohortes": filas,
            "nota": ("Cohorte = mes de alta de las personas registradas por el equipo (sin las importaciones de "
                     "bases). "
                     "«Abordadas en 30 días»: su primer acercamiento (sin anulados) llegó a los 30 días del alta; en "
                     "las cohortes que no cumplieron 30 días sale null.")}


# ───────────────────────────── franjas e intentos ─────────────────────────────

def _tasas(k: Counter) -> dict:
    n = k["intentos"]
    return {"intentos": n, "efectivos": k["efectivos"], "utiles": k["utiles"],
            "tasa_contacto": round(100 * k["efectivos"] / n, 1) if n >= MINIMO_TASA else None,
            "tasa_util": round(100 * k["utiles"] / n, 1) if n >= MINIMO_TASA else None}


def _en_horario(ajustes: dict, t: datetime) -> bool:
    h = ajustes.get("horario") or {}
    rango = h.get("semana") if t.weekday() < 5 else h.get("sabado") if t.weekday() == 5 else h.get("domingo")
    if not isinstance(rango, list) or len(rango) != 2:
        return False
    return str(rango[0]) <= t.strftime("%H:%M") < str(rango[1])


def _franjas(d: Datos, c: Consulta) -> dict:
    if len(d.personas) < MINIMO_POBLACION:
        return dict(POCAS)
    desde, hasta = _periodo(c, 90, d.hoy)
    hora, dia, canal, franja, usuario = (defaultdict(Counter) for _ in range(5))
    dentro = defaultdict(Counter)
    for a in d.acercamientos(desde, hasta):
        t = a["_t"]
        for tabla, k in ((hora, t.hour), (dia, DIAS_SEMANA[t.weekday()]), (canal, a.get("canal") or "otro"),
                         (franja, _franja(t.hour)), (usuario, a.get("uid")),
                         (dentro, "dentro" if _en_horario(d.ajustes, t) else "fuera")):
            tabla[k]["intentos"] += 1
            tabla[k]["efectivos"] += _efectivo(a)
            tabla[k]["utiles"] += _util(a)
    total = Counter()
    for x in hora.values():
        total.update(x)
    horas = [{"hora": h, **_tasas(hora[h])} for h in range(24) if hora[h]["intentos"]]
    con_tasa = [x for x in horas if x["tasa_util"] is not None]
    mejores = sorted(con_tasa, key=lambda x: -x["tasa_util"])[:3]
    peores = sorted(con_tasa, key=lambda x: x["tasa_util"])[:3]
    out: dict[str, Any] = {
        "tipo": "franjas", "desde": desde.isoformat(), "hasta": hasta.isoformat(), "total": _tasas(total),
        "por_hora": horas, "por_dia": [{"dia": x, **_tasas(dia[x])} for x in DIAS_SEMANA if dia[x]["intentos"]],
        "por_canal": [{"canal": k, "etiqueta": ETIQUETAS["canal"].get(k, k), **_tasas(v)}
                      for k, v in sorted(canal.items(), key=lambda kv: -kv[1]["intentos"])],
        "por_franja": [{"franja": k, "etiqueta": ETIQUETAS["franja"][k], **_tasas(franja[k])}
                       for k in ("manana", "tarde", "noche", "madrugada") if franja[k]["intentos"]],
        "horario_configurado": {k: _tasas(dentro[k]) for k in ("dentro", "fuera")},
        "mejores_horas": [x["hora"] for x in mejores], "peores_horas": [x["hora"] for x in peores],
        "nota": ("Hora de Colombia del registro del acercamiento. Tasa = de cada 100 intentos (con 20 o más intentos); "
                 "útil = contestó sin rechazar. Sin los automáticos de las reuniones."),
    }
    if c.desglose == "usuario":
        out["por_usuario"] = [{"usuario": d.nombre_usuario(u), **_tasas(v)}
                              for u, v in sorted(usuario.items(), key=lambda kv: -kv[1]["intentos"])
                              if isinstance(u, int)][:MAX_GRUPOS]
    return out


CUBETAS_DIAS = (("0", 0, 0), ("1", 1, 1), ("2-3", 2, 3), ("4-7", 4, 7), ("8-14", 8, 14), ("15+", 15, 10 ** 6))
MAX_INTENTO = 10


def _intentos(d: Datos, c: Consulta) -> dict:
    if len(d.personas) < MINIMO_POBLACION:
        return dict(POCAS)
    desde, hasta = _periodo(c, 365, d.hoy)
    secuencias: dict[int, list[dict]] = defaultdict(list)
    for a in d.acercamientos():
        secuencias[a["persona_id"]].append(a)
    llegaron, exitos, utiles = Counter(), Counter(), Counter()
    por_espera: dict[str, Counter] = defaultdict(Counter)
    personas = contactadas_en = 0
    contactada_en_k = Counter()
    for seq in secuencias.values():
        if not desde <= seq[0]["_d"] <= hasta:
            continue
        personas += 1
        previo = None
        for k, a in enumerate(seq[:MAX_INTENTO], start=1):
            llegaron[k] += 1
            ef = _efectivo(a)
            exitos[k] += ef
            utiles[k] += _util(a)
            if previo is not None:
                espera = (a["_d"] - previo["_d"]).days
                cub = next(n for n, lo, hi in CUBETAS_DIAS if lo <= espera <= hi)
                por_espera[cub]["intentos"] += 1
                por_espera[cub]["efectivos"] += ef
                por_espera[cub]["utiles"] += _util(a)
            if ef:
                contactadas_en += 1
                contactada_en_k[k] += 1
                break
            previo = a
    filas, acumulada = [], 0
    for k in range(1, MAX_INTENTO + 1):
        if not llegaron[k]:
            break
        acumulada += contactada_en_k[k]
        filas.append({"intento": k, "personas_que_llegaron": llegaron[k],
                      "prob_contacto": round(100 * exitos[k] / llegaron[k], 1) if llegaron[k] >= MINIMO_TASA else None,
                      "prob_util": round(100 * utiles[k] / llegaron[k], 1) if llegaron[k] >= MINIMO_TASA else None,
                      "contactadas_acumulado_pct": round(100 * acumulada / personas, 1) if personas >= MINIMO_TASA
                      else None})
    umbral = 5.0
    recomendado_max = None
    for i, f in enumerate(filas[:-1]):
        sig = filas[i + 1]["prob_contacto"]
        if sig is not None and sig < umbral:
            recomendado_max = f["intento"]
            break
    if recomendado_max is None and filas and all(f["prob_contacto"] is not None for f in filas):
        recomendado_max = filas[-1]["intento"]
    esperas = [{"dias_de_espera": n, **_tasas(por_espera[n])} for n, _, _ in CUBETAS_DIAS if por_espera[n]["intentos"]]
    con_tasa = [e for e in esperas if e["tasa_contacto"] is not None and e["dias_de_espera"] != "0"]
    mejor = max(con_tasa, key=lambda e: e["tasa_contacto"]) if con_tasa else None
    dias_rec = int(mejor["dias_de_espera"].split("-")[0].rstrip("+")) if mejor else None
    return {"tipo": "intentos", "desde": desde.isoformat(), "hasta": hasta.isoformat(),
            "personas": personas, "intentos": filas, "por_dias_de_espera": esperas,
            "recomendacion": {"max_intentos_sin_exito": recomendado_max, "dias_entre_intentos": dias_rec,
                              "actual_max_intentos_sin_exito": d.ajustes.get("max_intentos_sin_exito"),
                              "actual_dias_entre_intentos": d.ajustes.get("dias_entre_intentos"),
                              "criterio": (f"Dejar de insistir cuando el intento siguiente contesta menos del "
                                           f"{umbral:g} %; esperar los días con la mejor tasa de contacto.")},
            "nota": ("Personas cuyo primer intento cayó en el periodo, hasta que contestaron (efectivo). Probabilidad "
                     "con 20 o más personas en ese intento. Sin los automáticos de las reuniones.")}


# ───────────────────────────── captura ─────────────────────────────

def _captura(d: Datos, c: Consulta) -> dict:
    desde = date.fromisoformat(c.desde) if c.desde else None
    hasta = date.fromisoformat(c.hasta) if c.hasta else (d.hoy if desde else None)
    if desde and hasta and desde > hasta:
        raise HTTPException(422, {"mensaje": "«desde» no puede ser posterior a «hasta»", "codigo": "invalido"})
    grupos: dict[int, list[dict]] = defaultdict(list)
    for p in d.personas:
        if not isinstance(p["quien"], int) or p["alta"] is None:
            continue
        if desde and not desde <= p["alta"] <= hasta:
            continue
        grupos[p["quien"]].append(p)
    con_conflicto = {x.get("persona_id") for x in d.db.conflictos_cedula.find(
        {"persona_id": {"$in": [p["id"] for ps in grupos.values() for p in ps]}}, {"persona_id": 1})}
    unidas = {x["uid"]: x["unidas"] for x in _unidas(d, desde, hasta)}
    filas, chicos = [], 0
    for uid, ps in grupos.items():
        n = len(ps)
        if n < MINIMO_CAPTURA:
            chicos += 1
            continue
        u = unidas.get(uid, 0)
        filas.append({"usuario": d.nombre_usuario(uid), "rol": (d.usuarios.get(uid) or {}).get("rol"), "fichas": n,
                      "pct_telefono_equivocado": round(100 * sum(1 for p in ps if p["tel_malo"]) / n, 1),
                      "pct_conflicto_cedula": round(100 * sum(1 for p in ps if p["id"] in con_conflicto) / n, 1),
                      "pct_sin_autorizacion": round(100 * sum(1 for p in ps if not p["autorizada"]) / n, 1),
                      "completitud_media": round(statistics.fmean(p["completitud"] for p in ps), 1),
                      "duplicados_unidos": u, "pct_duplicados": round(100 * u / (n + u), 1)})
    claves = ("pct_telefono_equivocado", "pct_conflicto_cedula", "pct_sin_autorizacion", "completitud_media",
              "pct_duplicados")
    medianas = {k: _mediana([f[k] for f in filas]) for k in claves}
    for f in filas:
        f["frente_a_mediana"] = {k: round(f[k] - medianas[k], 1) if medianas[k] is not None else None for k in claves}
    filas.sort(key=lambda f: -f["fichas"])
    return {"tipo": "captura", "desde": desde.isoformat() if desde else None,
            "hasta": hasta.isoformat() if hasta else None, "capturadores": filas[:MAX_GRUPOS],
            "mediana": medianas, "capturadores_con_menos_de_10_fichas": chicos,
            "nota": ("Calidad de las fichas que registró cada persona del equipo (las de planilla, del planillero que "
                     "la llenó; sin importaciones de bases), frente a la mediana, en puntos. Sirve para capacitar, no "
                     "para sancionar: un barrio difícil también baja las cifras.")}


# ───────────────────────────── comparar ─────────────────────────────

def _eventos_comparar(d: Datos, metrica: str, dim: str, desde: date, hasta: date) -> list[tuple[Any, bool]]:
    """(grupo, útil) de cada evento del periodo."""
    def de_persona(p: dict) -> Any:
        return valor_de(d, dim, p)

    out = []
    if metrica == "altas":
        for p in d.personas:
            if p["quien"] != IMPORTACION and p["alta"] and desde <= p["alta"] <= hasta:
                out.append((de_persona(p), True))
    elif metrica == "autorizaciones":
        for a in d.autorizaciones(desde, hasta):
            g = (a.get("medio") if dim == "medio" else a.get("uid") if dim == "usuario"
                 else de_persona(d.por_id[a["persona_id"]]))
            out.append((g, True))
    else:
        for a in d.acercamientos(desde, hasta):
            t = a["_t"]
            g = (a.get("canal") if dim == "canal" else a.get("uid") if dim == "usuario" else _franja(t.hour)
                 if dim == "franja" else DIAS_SEMANA[t.weekday()] if dim == "dia_semana"
                 else de_persona(d.por_id[a["persona_id"]]))
            out.append((g, _util(a)))
    return out


def _comparar(d: Datos, c: Consulta) -> dict:
    if len(d.personas) < MINIMO_POBLACION:
        return dict(POCAS)
    b_desde, b_hasta = _periodo(c, 28, d.hoy)
    largo = (b_hasta - b_desde).days + 1
    if c.referencia_desde:
        a_desde, a_hasta = date.fromisoformat(c.referencia_desde), date.fromisoformat(c.referencia_hasta)
    else:
        a_hasta = b_desde - timedelta(days=1)
        a_desde = a_hasta - timedelta(days=largo - 1)
    dim = c.dimensiones[0]
    metrica = c.metrica
    poblacion = metrica in ("altas", "autorizaciones") or dim not in DIM_EQUIPO
    ev_a = _eventos_comparar(d, metrica, dim, a_desde, a_hasta)
    ev_b = _eventos_comparar(d, metrica, dim, b_desde, b_hasta)
    n_a, n_b, u_a, u_b = Counter(), Counter(), Counter(), Counter()
    for g, u in ev_a:
        n_a[g] += 1
        u_a[g] += u
    for g, u in ev_b:
        n_b[g] += 1
        u_b[g] += u
    grupos = sorted(set(n_a) | set(n_b), key=lambda g: -(n_a[g] + n_b[g]))
    tasa = metrica == "tasa_contacto_util"
    # Grupos chicos a «otros»: de habitantes, los de 1 a 4 en algún periodo; para una tasa, los de menos de 10
    minimo = MINIMO_POBLACION if tasa else (MINIMO_CELDA if poblacion else 1)
    chicos = [g for g in grupos if (0 < n_a[g] < minimo) or (0 < n_b[g] < minimo)] if (poblacion or tasa) else []
    if len(grupos) - len(chicos) > MAX_DESGLOSE * 2:
        chicos += [g for g in grupos if g not in chicos][MAX_DESGLOSE * 2:]
    for g in chicos:
        for cont in (n_a, n_b, u_a, u_b):
            cont["otros"] += cont.pop(g, 0)
    grupos = [g for g in grupos if g not in chicos] + (["otros"] if chicos else [])
    valor = (lambda n, u: u) if metrica == "contacto_util" else (lambda n, u: n)
    out: dict[str, Any] = {"tipo": "comparar", "metrica": metrica, "dimension": dim,
                           "periodo": {"desde": b_desde.isoformat(), "hasta": b_hasta.isoformat()},
                           "referencia": {"desde": a_desde.isoformat(), "hasta": a_hasta.isoformat()}}
    filas = []
    if not tasa:
        va = {g: valor(n_a[g], u_a[g]) for g in grupos}
        vb = {g: valor(n_b[g], u_b[g]) for g in grupos}
        if poblacion:
            pa, pb = proteger(va), proteger(vb)
            if pa is None or pb is None:
                return dispersas("comparar", len(d.personas))
        else:
            pa, pb = va, vb
        tot_a, tot_b = sum(va.values()), sum(vb.values())
        delta = tot_b - tot_a
        for g in grupos:
            fila: dict[str, Any] = {"valor": g, "etiqueta": etiqueta_de(d, dim, g), "referencia": pa[g],
                                    "periodo": pb[g]}
            if visible(pa[g]) and visible(pb[g]):
                fila["cambio"] = vb[g] - va[g]
                fila["parte_del_cambio_pct"] = round(100 * (vb[g] - va[g]) / delta) if delta else None
            filas.append(fila)
        out["total"] = {"referencia": celda(tot_a) if poblacion else tot_a,
                        "periodo": celda(tot_b) if poblacion else tot_b}
        if visible(out["total"]["referencia"]) and visible(out["total"]["periodo"]):
            out["total"]["cambio"] = delta
            out["total"]["cambio_pct"] = round(100 * delta / tot_a, 1) if tot_a else None
        con_cambio = [f for f in filas if isinstance(f.get("cambio"), int) and f["cambio"]]
        if con_cambio and delta:
            mayor = max(con_cambio, key=lambda f: abs(f["cambio"]) if (f["cambio"] > 0) == (delta > 0) else -1)
            if (mayor["cambio"] > 0) == (delta > 0):
                out["explicacion"] = (f"El {abs(mayor['parte_del_cambio_pct'] or 0)} % del "
                                      f"{'aumento' if delta > 0 else 'descenso'} viene de «{mayor['etiqueta']}».")
    else:
        na, nb = sum(n_a.values()), sum(n_b.values())
        if na < MINIMO_TASA or nb < MINIMO_TASA:
            out.update(total={"referencia": {"intentos": na}, "periodo": {"intentos": nb}},
                       nota="Muy pocos acercamientos en algún periodo para comparar tasas (20 o más).")
            out["grupos"] = []
            return out
        ra, rb = sum(u_a.values()) / na, sum(u_b.values()) / nb
        # La mezcla de cada grupo se mide frente a la tasa media (los pesos suman 1 en los dos periodos, así el total
        # no cambia): ganar peso un grupo que contesta más que el promedio sube la tasa, y al revés
        media_r = (ra + rb) / 2
        mezcla_t = tasa_t = 0.0
        for g in grupos:
            wa, wb = n_a[g] / na, n_b[g] / nb
            rga = u_a[g] / n_a[g] if n_a[g] else None
            rgb = u_b[g] / n_b[g] if n_b[g] else None
            rga = rgb if rga is None else rga
            rgb = rga if rgb is None else rgb
            mezcla = (wb - wa) * ((rga + rgb) / 2 - media_r)
            efecto = (rgb - rga) * (wa + wb) / 2
            mezcla_t += mezcla
            tasa_t += efecto
            cifra = celda if poblacion else (lambda x: x)
            filas.append({"valor": g, "etiqueta": etiqueta_de(d, dim, g),
                          "intentos": {"referencia": cifra(n_a[g]), "periodo": cifra(n_b[g])},
                          "tasa_util": {"referencia": round(100 * u_a[g] / n_a[g], 1)
                                        if n_a[g] >= MINIMO_POBLACION else None,
                                        "periodo": round(100 * u_b[g] / n_b[g], 1) if n_b[g] >= MINIMO_POBLACION
                                        else None},
                          "efecto_mezcla_pp": round(100 * mezcla, 2), "efecto_tasa_pp": round(100 * efecto, 2)})
        delta = rb - ra
        out["total"] = {"referencia": {"intentos": na, "tasa_util": round(100 * ra, 1)},
                        "periodo": {"intentos": nb, "tasa_util": round(100 * rb, 1)},
                        "cambio_pp": round(100 * delta, 1), "efecto_mezcla_pp": round(100 * mezcla_t, 1),
                        "efecto_tasa_pp": round(100 * tasa_t, 1)}
        if abs(delta) > 1e-9:
            mayor = max(filas, key=lambda f: (f["efecto_mezcla_pp"] + f["efecto_tasa_pp"]) * (1 if delta > 0 else -1))
            parte = (mayor["efecto_mezcla_pp"] + mayor["efecto_tasa_pp"]) / (100 * delta) * 100
            causa = "la tasa" if abs(mayor["efecto_tasa_pp"]) >= abs(mayor["efecto_mezcla_pp"]) else "la mezcla"
            out["explicacion"] = (f"El {round(parte)} % del {'aumento' if delta > 0 else 'descenso'} de la tasa de "
                                  f"contacto útil viene de «{mayor['etiqueta']}», sobre todo por {causa} (mezcla = "
                                  "cuánto pesó ese grupo; tasa = qué tan bien le fue).")
    out["grupos"] = filas
    out["nota"] = ("Periodo frente a referencia. En las tasas, el cambio se parte en efecto mezcla (cambió cuánto se "
                   "usó cada grupo) y efecto tasa (cambió el resultado dentro del grupo).") + (
        " Los grupos de 1 a 4 van en «otros»." if poblacion and not tasa else "")
    return out


# ───────────────────────────── efecto de las reuniones ─────────────────────────────

def _reuniones_efecto(d: Datos, c: Consulta) -> dict:
    if len(d.personas) < MINIMO_POBLACION:
        return dict(POCAS)
    desde, hasta = _periodo(c, 180, d.hoy)
    por_lugar: dict[int, list[dict]] = defaultdict(list)
    for p in d.personas:
        if p["lugar"] is not None:
            por_lugar[p["lugar"]].append(p)
    reus = sorted((r for r in d.reuniones(desde, hasta) if r.get("lugar_id") is not None
                   and modelo.fecha_valida(r.get("fecha"))), key=lambda r: (r["fecha"], r["_id"]), reverse=True)
    ventana = 28
    autoriz = d.autorizaciones(desde - timedelta(days=ventana), min(d.hoy, hasta + timedelta(days=ventana)))
    acerc = [a for a in d.acercamientos(desde - timedelta(days=ventana), min(d.hoy, hasta + timedelta(days=ventana)))
             if _util(a)]
    filas, pocas, valores = [], 0, defaultdict(dict)
    for r in reus:
        lid = r["lugar_id"]
        ps = por_lugar.get(lid, [])
        if len(ps) < MINIMO_POBLACION:
            pocas += 1
            continue
        f = modelo.fecha_valida(r["fecha"])
        a_ini, a_fin = f - timedelta(days=ventana), f - timedelta(days=1)
        b_ini, b_fin = f, f + timedelta(days=ventana - 1)
        completa = b_fin <= d.hoy
        ids = {p["id"] for p in ps}
        en = lambda x, i, j: i <= x <= j  # noqa: E731
        cuenta = {
            "altas": [sum(1 for p in ps if p["quien"] != IMPORTACION and p["alta"] and en(p["alta"], i, j))
                      for i, j in ((a_ini, a_fin), (b_ini, b_fin))],
            "autorizaciones": [sum(1 for a in autoriz if a["persona_id"] in ids and en(a["_d"], i, j))
                               for i, j in ((a_ini, a_fin), (b_ini, b_fin))],
            "contactos_utiles": [sum(1 for a in acerc if a["persona_id"] in ids and en(a["_d"], i, j))
                                 for i, j in ((a_ini, a_fin), (b_ini, b_fin))],
        }
        lg = d.lugares.get(lid) or {}
        filas.append({"reunion_id": r["_id"], "titulo": r.get("titulo"), "fecha": r["fecha"],
                      "lugar": lg.get("nombre"), "personas_del_lugar": len(ps), "completa": completa, "_c": cuenta})
    completas = [x for x in filas if x["completa"]]
    agregado: dict[str, Any] = {}
    for m in ("altas", "autorizaciones", "contactos_utiles"):
        for i, nombre in enumerate(("antes", "despues")):
            conteos = {x["reunion_id"]: x["_c"][m][i] for x in completas}
            publicado = proteger(conteos) if conteos else {}
            for x in completas:  # sin cómo proteger el desglose, ese conteo no va reunión por reunión
                x.setdefault(nombre, {})[m] = publicado[x["reunion_id"]] if publicado is not None else None
            valores[m][nombre] = sum(conteos.values())
        antes, despues = valores[m]["antes"], valores[m]["despues"]
        agregado[m] = {"antes": celda(antes), "despues": celda(despues),
                       "cambio_pct": round(100 * (despues - antes) / antes, 1)
                       if antes >= MINIMO_CELDA and despues >= MINIMO_CELDA else None}
    for x in filas:
        x.pop("_c")
        if not x["completa"]:
            x["nota"] = "Todavía no pasaron 4 semanas: no entra en el agregado"
    return {"tipo": "reuniones_efecto", "desde": desde.isoformat(), "hasta": hasta.isoformat(),
            "reuniones_consideradas": len(completas), "reuniones_en_lugares_con_menos_de_10": pocas,
            "agregado": agregado, "reuniones": filas[:MAX_GRUPOS],
            "advertencia": ("Comparar 4 semanas antes y 4 después en el barrio o la vereda de cada reunión no prueba "
                            "que la reunión lo causó: puede haber otras campañas, temporadas o reuniones cercanas (sus "
                            "ventanas se pisan y cuentan dos veces)."),
            "nota": ("Altas del equipo, autorizaciones «sí» y contactos útiles de las personas de ese lugar "
                     "(vigentes y que no dijeron que no). Solo reuniones con barrio o vereda y 10 o más personas "
                     "allí.")}


# ───────────────────────────── diagnóstico ─────────────────────────────

SEVERIDADES = {"alta": 0, "media": 1, "baja": 2}


def _enlace(d: Datos, extra: dict[str, Any], nota: str | None = None) -> dict | None:
    """El enlace a Habitantes de un hallazgo y su cifra contada con exactamente esos filtros (los de la consulta, los
    del hallazgo y `situacion=vigentes`), sin quienes no autorizaron. Sin enlace si algún filtro no lo lee Habitantes
    o si choca con un filtro de la consulta. `nota`: en qué difiere la lista del hallazgo (cuando Habitantes no tiene
    un filtro exacto para él)."""
    params: dict[str, Any] = dict(d.params)
    for k, v in extra.items():
        if k in params and str(params[k]) != str(v):
            return None
        params[k] = v
    params["situacion"] = "vigentes"
    if not set(params) <= ENLAZABLES:
        return None
    q = consulta_mongo(d.db, params, d.hoy, vigentes=False)
    n = d.db.personas.count_documents(q, maxTimeMS=MAX_MS)
    out = {"ruta": "/personas?" + urlencode({k: str(v) for k, v in params.items()}), "personas": celda(n)}
    if nota:
        out["nota"] = nota
    return out


def _hallazgo(id_: str, severidad: str, titulo: str, evidencia: dict, por_que: str, accion: str,
              enlace: dict | None = None, puntaje: float = 0.0, ruta: str | None = None) -> dict:
    h = {"id": id_, "severidad": severidad, "titulo": titulo, "evidencia": evidencia, "por_que": por_que,
         "accion": accion, "_puntaje": puntaje}
    if enlace:
        h["enlace"] = enlace
    elif ruta:
        h["enlace"] = {"ruta": ruta}
    return h


def _diagnostico(d: Datos, c: Consulta) -> dict:
    n = len(d.personas)
    if n < MINIMO_POBLACION:
        return dict(POCAS)
    hallazgos: list[dict] = []
    revisados: list[str] = []
    cuenta = lambda f: sum(1 for p in d.personas if f(p))  # noqa: E731
    h = hallazgos.append

    # 1. Solicitudes de derechos vencidas o por vencer (Ley 1581: plazos legales)
    cal = _calidad(d, Consulta(tipo="calidad"))
    venc = cal["solicitudes"]["vencidas"]
    revisados.append("solicitudes")
    if venc:
        h(_hallazgo("solicitudes_vencidas", "alta", "Hay solicitudes de titulares con el plazo vencido",
                    {"vencidas_por_tipo": venc, "abiertas_por_tipo": cal["solicitudes"]["abiertas"]},
                    "La Ley 1581 da 10 días hábiles para consultas y 15 para reclamos (corrección, supresión): una "
                    "solicitud vencida es un incumplimiento que la Superintendencia puede sancionar.",
                    "Responda hoy las vencidas en Calidad de datos → Solicitudes, empezando por las de supresión.",
                    puntaje=1e6, ruta="/calidad"))

    # 2. Autorizaciones de planilla sin confirmar (no se pueden contactar)
    por_confirmar = cuenta(lambda p: p["consentimiento"] == "por_confirmar")
    autorizadas = cuenta(lambda p: p["autorizada"])
    revisados.append("autorizaciones_por_confirmar")
    if por_confirmar >= MINIMO_CELDA:
        parte = por_confirmar / autorizadas if autorizadas else 0
        h(_hallazgo("autorizaciones_por_confirmar", "alta" if parte >= 0.2 else "media",
                    "Autorizaciones declaradas en planilla esperan confirmación",
                    {"personas": atributo(por_confirmar, n), "pct_de_las_autorizadas": pct(por_confirmar, autorizadas)},
                    "Hasta que alguien las confirme con el papel firmado, esas personas no se pueden llamar ni "
                    "escribir: es trabajo de campo que no rinde.",
                    "Confirme las autorizaciones con las planillas físicas en Importar y exportar (o pida que las "
                    "traigan los planilleros).",
                    _enlace(d, {"consentimiento": "por_confirmar"}), por_confirmar))

    # 3. Habilitadas que nadie ha abordado
    habilitadas = cuenta(lambda p: p["habilitado"] and p["tel"])
    sin_abordar = cuenta(lambda p: p["habilitado"] and p["tel"] and p["n"] == 0)
    revisados.append("habilitadas_sin_abordar")
    if sin_abordar >= MINIMO_POBLACION:
        parte = sin_abordar / habilitadas if habilitadas else 0
        h(_hallazgo("habilitadas_sin_abordar", "alta" if parte >= 0.3 else "media",
                    "Personas que ya autorizaron y tienen teléfono, pero nadie las ha llamado",
                    {"personas": atributo(sin_abordar, n), "pct_de_las_habilitadas": pct(sin_abordar, habilitadas)},
                    "Es la gente más fácil de contactar: dieron su autorización y su número. Cada semana que pasa "
                    "sin llamarlas baja la probabilidad de que contesten.",
                    "Póngalas en la cola de los consultores esta semana (Mi trabajo → cola) y revise que tengan "
                    "consultores asignados en su zona.",
                    _enlace(d, {"consentimiento": "si", "abordaje_estado": "sin_abordar", "con_telefono": 1},
                            "La lista incluye también las autorizaciones de planilla por confirmar (Habitantes no "
                            "filtra por contacto habilitado)."),
                    sin_abordar * 2))

    # 4. «Volver a llamar» vencidos
    hoy = d.hoy.isoformat()
    vencidos = cuenta(lambda p: p["proximo"] is not None and str(p["proximo"]) <= hoy)
    revisados.append("proximo_vencido")
    if vencidos >= MINIMO_CELDA:
        h(_hallazgo("volver_a_llamar_vencidos", "media", "Compromisos de «volver a llamar» ya vencidos",
                    {"personas": atributo(vencidos, n)},
                    "Son personas que pidieron que las llamaran otro día: si no se cumple, se pierde la confianza "
                    "ganada en el primer contacto.",
                    "Llámelas primero en la próxima jornada (Habitantes con «volver a llamar vencido»).",
                    _enlace(d, {"proximo_vencido": 1}), vencidos * 1.5))

    # 5. Pendientes de autorización con teléfono
    pendientes = cuenta(lambda p: p["consentimiento"] == "pendiente" and p["tel"])
    revisados.append("pendientes_con_telefono")
    if pendientes >= MINIMO_POBLACION and pendientes / n >= 0.15:
        lugares = Counter(p["lugar"] for p in d.personas if p["consentimiento"] == "pendiente" and p["tel"]
                          and p["lugar"] is not None)
        top = [{"lugar": (d.lugares.get(l) or {}).get("nombre"), "personas": celda(x)}
               for l, x in lugares.most_common(3) if x >= MINIMO_POBLACION]
        h(_hallazgo("pendientes_con_telefono", "media", "Muchas personas con teléfono todavía no autorizan",
                    {"personas": atributo(pendientes, n), "pct_de_la_base": pct(pendientes, n),
                     "lugares_con_mas": top},
                    "Sin autorización no se pueden contactar (Ley 1581): ese teléfono no sirve todavía.",
                    "Pida la autorización en terreno con la planilla o por teléfono de forma verbal (si Ajustes lo "
                    "permite), empezando por los lugares con más pendientes.",
                    _enlace(d, {"consentimiento": "pendiente", "con_telefono": 1}), pendientes * 0.8))

    # 6. La mayor caída del embudo
    emb = _embudo(d, Consulta(tipo="embudo"))
    revisados.append("embudo")
    caida = emb.get("mayor_caida")
    if caida and caida["tasa"] is not None and caida["tasa"] < 50:
        h(_hallazgo("embudo_mayor_caida", "media" if caida["tasa"] >= 25 else "alta",
                    f"El embudo se cae entre «{caida['desde']}» y «{caida['hasta']}»",
                    {"tasa_pct": caida["tasa"], "etapas": [{"etapa": e["etapa"], "personas": e["personas"]}
                                                           for e in emb["etapas"]]},
                    "Es el paso donde se pierde más gente camino a un contacto útil y a un voto verificado: mejorarlo "
                    "rinde más que mejorar cualquier otro.",
                    ACCION_ETAPA.get(caida["hasta"], "Revise ese paso con el equipo."), None, 500 - caida["tasa"]))

    # 7. Datos que faltan en mucha gente
    revisados.append("faltan")
    for campo, filtro, umbral in (("cedula", {"sin_cedula": 1}, 0.3), ("puesto", {"sin_puesto": 1}, 0.4)):
        x = cuenta(lambda p: campo in p["faltan"])
        if x >= MINIMO_POBLACION and x / n >= umbral:
            accion = ("Pida la cédula en cada contacto y en las reuniones; sin ella no se puede consultar el puesto."
                      if campo == "cedula" else
                      "Consulte el puesto en la Registraduría para quienes ya tienen cédula (enlace en Ajustes).")
            extra = filtro if campo == "cedula" else {**filtro, "con_cedula": 1}
            h(_hallazgo(f"faltan_{campo}", "media", f"Falta {modelo.ETIQUETAS_CAMPOS[campo].lower()} en mucha gente",
                        {"personas": atributo(x, n), "pct": pct(x, n)},
                        "Sin cédula no se verifica identidad ni votación; sin puesto no se puede planear el día de "
                        "elecciones ni medir la cobertura por puesto.", accion, _enlace(d, extra), x * 0.5))

    # 8. Cobertura y ritmo por puesto
    revisados.append("cobertura")
    meta_pct = c.meta_pct or 30
    if c.fecha_meta:
        rit = _ritmo(d, Consulta(tipo="ritmo", fecha_meta=c.fecha_meta, meta_pct=meta_pct))
        lejos = sorted((f for f in rit.get("puestos") or [] if f.get("llega") is False),
                       key=lambda f: -(f.get("faltan") or 0))
        if lejos:
            peor = lejos[0]
            h(_hallazgo("ritmo_insuficiente", "alta", "Al ritmo actual no se llega a la meta en algunos puestos",
                        {"puestos_que_no_llegan": [{"codigo": f["codigo"], "nombre": f["nombre"],
                                                    "cobertura_pct": f.get("cobertura_pct"),
                                                    "cobertura_proyectada_pct": f.get("cobertura_proyectada_pct"),
                                                    "necesarias_por_semana": f.get("necesarias_por_semana"),
                                                    "ritmo_semanal": f.get("ritmo_semanal")} for f in lejos[:5]],
                         "fecha_meta": c.fecha_meta, "meta_pct": meta_pct},
                        "La meta de cobertura es por puesto: un puesto rezagado no se compensa con otro adelantado.",
                        f"Concentre las altas en el puesto {peor['codigo']} ({peor['nombre']}): hacen falta unas "
                        f"{peor.get('necesarias_por_semana')} por semana.",
                        _enlace(d, {"puesto_id": peor["puesto_id"]}), 1e5))
    else:
        cob = _cobertura(d, Consulta(tipo="cobertura", meta_pct=meta_pct))
        bajos = [f for f in cob.get("puestos") or [] if isinstance(f.get("cobertura_pct"), (int, float))
                 and f["cobertura_pct"] < meta_pct / 2]
        if bajos:
            peor = min(bajos, key=lambda f: f["cobertura_pct"])
            h(_hallazgo("cobertura_baja", "media", "Puestos de votación con poca cobertura",
                        {"puestos": [{"codigo": f["codigo"], "nombre": f["nombre"], "cobertura_pct": f["cobertura_pct"],
                                      "faltan_para_meta": f.get("faltan_para_meta")} for f in bajos[:5]],
                         "meta_pct": meta_pct},
                        "La cobertura de cada puesto frente a sus habilitados dice dónde falta presencia.",
                        f"Programe trabajo de campo en el área del puesto {peor['codigo']} ({peor['nombre']}). Con "
                        "fecha_meta, el diagnóstico calcula el ritmo necesario por semana.",
                        _enlace(d, {"puesto_id": peor["puesto_id"]}), 1000 - peor["cobertura_pct"]))

    # 9. Lugares desatendidos
    br = _brechas(d, Consulta(tipo="brechas"))
    revisados.append("brechas")
    desatendidos = [f for f in br.get("lugares", []) if f["indice_atencion"] <= 30 and visible(f["personas"])
                    and f["personas"] >= 20]
    if desatendidos:
        peor = desatendidos[0]
        h(_hallazgo("lugares_desatendidos", "alta" if peor["indice_atencion"] <= 10 else "media",
                    "Barrios o veredas casi sin atención en los últimos 90 días",
                    {"lugares": [{"nombre": f["nombre"], "personas": f["personas"],
                                  "indice_atencion": f["indice_atencion"],
                                  "reuniones_en_ventana": f["reuniones_en_ventana"],
                                  "pct_contacto_util_en_ventana": f["pct_contacto_util_en_ventana"]}
                                 for f in desatendidos[:5]]},
                    "Un lugar sin reuniones ni contactos recientes se enfría: la gente registrada deja de sentirse "
                    "tenida en cuenta.",
                    f"Programe una reunión o una jornada de llamadas en {peor['nombre']} "
                    f"({peor['personas']} personas).",
                    _enlace(d, {"lugar_id": peor["lugar_id"], "contactado": 0}), 300 + sum(f["personas"]
                                                                                           for f in desatendidos[:3])))

    # 10. Contacto útil: cambio de las últimas 4 semanas y qué lo explica (por canal y por usuario)
    revisados.append("contacto_util")
    por_canal = _comparar(d, Consulta(tipo="comparar", metrica="tasa_contacto_util", dimensiones=["canal"]))
    tot = por_canal.get("total") or {}
    cambio = tot.get("cambio_pp")
    if cambio is not None and tot["referencia"]["intentos"] >= 50 and tot["periodo"]["intentos"] >= 50 \
            and cambio <= -5:
        por_usuario = _comparar(d, Consulta(tipo="comparar", metrica="tasa_contacto_util", dimensiones=["usuario"]))
        explicaciones = [x for x in (por_canal.get("explicacion"), por_usuario.get("explicacion")) if x]
        h(_hallazgo("contacto_util_baja", "alta" if cambio <= -10 else "media",
                    f"La tasa de contacto útil bajó {abs(cambio)} puntos en 4 semanas",
                    {"referencia": tot["referencia"], "periodo": tot["periodo"],
                     "efecto_mezcla_pp": tot["efecto_mezcla_pp"], "efecto_tasa_pp": tot["efecto_tasa_pp"],
                     "por_canal": por_canal.get("explicacion"), "por_usuario": por_usuario.get("explicacion")},
                    "Cada punto menos es gente que se llama y no da un contacto útil: tiempo del equipo que no rinde.",
                    "Revise con el equipo lo que cambió: " + (" ".join(explicaciones) or "compare canales y usuarios."),
                    None, 2000 + abs(cambio) * 10))

    # 11. Franjas horarias
    fr = _franjas(d, Consulta(tipo="franjas"))
    revisados.append("franjas")
    tot_fr = fr["total"]
    if tot_fr["tasa_util"] is not None and fr["mejores_horas"]:
        mejores = [x for x in fr["por_hora"] if x["hora"] in fr["mejores_horas"]]
        parte = sum(x["intentos"] for x in mejores) / tot_fr["intentos"]
        mejor_tasa = max(x["tasa_util"] for x in mejores)
        if mejor_tasa >= 1.5 * tot_fr["tasa_util"] and parte < 0.25:
            horas = ", ".join(f"{x:02d}:00" for x in sorted(fr["mejores_horas"]))
            h(_hallazgo("franjas_mejores", "media", "Hay horas en que se contesta mucho más y se llama poco",
                        {"tasa_util_general": tot_fr["tasa_util"], "mejores_horas": fr["mejores_horas"],
                         "tasa_util_mejor_hora": mejor_tasa, "pct_de_intentos_en_esas_horas": round(100 * parte, 1)},
                        "La misma llamada rinde más a otra hora: mover las jornadas sube los contactos útiles sin "
                        "más trabajo.", f"Concentre las llamadas cerca de las {horas} (hora de Colombia), dentro del "
                        "horario permitido.", None, 800))
        fuera = fr["horario_configurado"]["fuera"]["intentos"]
        if fuera and fuera / tot_fr["intentos"] >= 0.1:
            h(_hallazgo("fuera_de_horario", "media", "Muchos intentos fuera del horario configurado",
                        {"pct_fuera": round(100 * fuera / tot_fr["intentos"], 1)},
                        "La Ley 2300 limita los horarios de contacto: llamar fuera del horario arriesga quejas.",
                        "Recuérdele al equipo el horario de Ajustes o ajústelo si la ley lo permite.", None, 700,
                        ruta="/ajustes"))

    # 12. Intentos: cuándo dejar de insistir
    it = _intentos(d, Consulta(tipo="intentos"))
    revisados.append("intentos")
    rec = it["recomendacion"]
    if rec["max_intentos_sin_exito"] and rec["actual_max_intentos_sin_exito"] and \
            abs(rec["max_intentos_sin_exito"] - rec["actual_max_intentos_sin_exito"]) >= 2:
        h(_hallazgo("max_intentos", "baja", "El número de intentos antes de dejar a alguien no cuadra con los datos",
                    {"recomendado": rec["max_intentos_sin_exito"], "actual": rec["actual_max_intentos_sin_exito"],
                     "intentos": [{"intento": f["intento"], "prob_contacto": f["prob_contacto"]}
                                  for f in it["intentos"][:6]]},
                    "Insistir de más gasta llamadas en gente que casi nunca contesta; de menos, deja contactos sin "
                    "hacer.", f"Considere poner «intentos sin éxito» en {rec['max_intentos_sin_exito']} en Ajustes.",
                    None, 100, ruta="/ajustes"))

    # 13. Calidad de captura
    cap = _captura(d, Consulta(tipo="captura"))
    revisados.append("captura")
    med = cap["mediana"].get("pct_telefono_equivocado")
    malos = [f for f in cap["capturadores"]
             if med is not None and f["pct_telefono_equivocado"] >= max(2 * med, med + 10)]
    if malos:
        h(_hallazgo("captura_telefonos", "media", "Fichas con muchos teléfonos equivocados según quién las capturó",
                    {"capturadores": [{"usuario": f["usuario"], "fichas": f["fichas"],
                                       "pct_telefono_equivocado": f["pct_telefono_equivocado"]} for f in malos[:5]],
                     "mediana_pct": med},
                    "Un número mal anotado es una persona que no se podrá contactar y una llamada perdida.",
                    f"Repase con {malos[0]['usuario']} cómo anotar el número (que la persona lo repita y se lea de "
                    "vuelta). Es para capacitar, no para sancionar.", None, 400))

    # 14. Calidad de la base
    revisados.append("calidad")
    coinc = cal["coincidencias_pendientes_personas"]
    if visible(coinc) and coinc >= MINIMO_POBLACION:
        h(_hallazgo("duplicados_pendientes", "media", "Posibles duplicados sin revisar",
                    {"personas_en_coincidencias": coinc},
                    "Dos fichas de la misma persona parten su historia: se la llama dos veces y las cifras se inflan.",
                    "Revise las coincidencias en Calidad de datos (o pídale al asistente unirlas con la vista previa).",
                    None, coinc, ruta="/calidad"))
    sin_rec = cal["indicadores"]["lugar_escrito_sin_reconocer"]["personas"]
    if visible(sin_rec) and sin_rec >= MINIMO_POBLACION:
        h(_hallazgo("lugares_sin_reconocer", "baja", "Barrios o veredas escritos que el nomenclátor no reconoce",
                    {"personas": sin_rec},
                    "Sin lugar reconocido, esas personas no salen en el mapa ni en los análisis por lugar.",
                    "Agregue los nombres como alias de su barrio o vereda en Calidad de datos.",
                    _enlace(d, {"sin_lugar": 1}), sin_rec * 0.3))

    # 15. Anomalías
    an = _anomalias(d, Consulta(tipo="anomalias"))
    revisados.append("anomalias")
    if an["telefonos_compartidos"]["grupos_de_mas_de_3_fichas"]:
        h(_hallazgo("telefonos_compartidos", "baja", "Números de teléfono repetidos en más de 3 fichas",
                    an["telefonos_compartidos"],
                    "Puede ser un número de una familia o de un líder, pero también duplicados o datos inventados.",
                    "Revise esas fichas en Calidad de datos antes de llamar en masa a esos números.", None, 50,
                    ruta="/calidad"))
    if an["picos"]:
        h(_hallazgo("picos_de_actividad", "baja", "Días con actividad muy por encima de lo normal de un usuario",
                    {"picos": an["picos"][:5]},
                    "Un pico puede ser una buena jornada o registros apresurados que luego hay que corregir.",
                    "Revise con la persona las fichas o llamadas de esos días.", None, 40))

    # 16. Cohortes recientes más lentas
    co = _cohortes(d, Consulta(tipo="cohortes"))
    revisados.append("cohortes")
    completas = [f for f in co.get("cohortes", []) if isinstance(f.get("pct_abordadas_en_30_dias"), (int, float))]
    if len(completas) >= 3:
        ult = completas[-1]
        previas = [f["pct_abordadas_en_30_dias"] for f in completas[:-1]]
        prom = statistics.fmean(previas)
        if prom >= 20 and ult["pct_abordadas_en_30_dias"] < 0.6 * prom:
            h(_hallazgo("cohorte_lenta", "media", "Las altas recientes tardan más en recibir su primer contacto",
                        {"mes": ult["mes"], "pct_abordadas_en_30_dias": ult["pct_abordadas_en_30_dias"],
                         "promedio_meses_anteriores": round(prom, 1)},
                        "El primer contacto en las semanas siguientes al registro es el que más contesta.",
                        "Programe el primer contacto de las altas nuevas dentro de su primer mes.", None, 300))

    # 17. Efecto de las reuniones (informativo)
    ef = _reuniones_efecto(d, Consulta(tipo="reuniones_efecto"))
    revisados.append("reuniones_efecto")
    ag = (ef.get("agregado") or {}).get("altas") or {}
    if ef.get("reuniones_consideradas", 0) >= 5 and visible(ag.get("antes")) and visible(ag.get("despues")) \
            and ag["antes"] and ag["despues"] >= 1.5 * ag["antes"]:
        h(_hallazgo("reuniones_y_altas", "baja", "Después de las reuniones suben las altas en el lugar",
                    {"reuniones": ef["reuniones_consideradas"], "altas_antes": ag["antes"],
                     "altas_despues": ag["despues"]},
                    "Sugiere que las reuniones ayudan a registrar gente, aunque no lo prueba (puede haber otras "
                    "causas).",
                    "Programe reuniones en los lugares desatendidos y mida de nuevo.", None, 20))

    hallazgos.sort(key=lambda x: (SEVERIDADES[x["severidad"]], -x.pop("_puntaje")))
    return {"tipo": "diagnostico", "base": {"personas": n}, "hallazgos": hallazgos[:20],
            "revisado": revisados, "nota_enlaces": NOTA_ENLACES,
            "nota": ("Hallazgos de más a menos urgente, calculados con las mismas reglas de la analítica; cada uno con "
                     "su evidencia, por qué importa y qué hacer.")}


# ───────────────────────────── Entrada única ─────────────────────────────

ANALISIS: dict[str, Callable[[Datos, Consulta], dict]] = {
    "tabla": _tabla, "serie": _serie, "embudo": _embudo, "cobertura": _cobertura, "brechas": _brechas,
    "equipo": _equipo, "calidad": _calidad, "anomalias": _anomalias, "cohortes": _cohortes, "ritmo": _ritmo,
    "franjas": _franjas, "intentos": _intentos, "captura": _captura, "comparar": _comparar,
    "reuniones_efecto": _reuniones_efecto, "diagnostico": _diagnostico,
}


def ajustar(out: dict) -> dict:
    """La salida en 40 000 caracteres como mucho: recorta la lista más larga (y lo dice) hasta que quepa."""
    for _ in range(40):
        if len(json.dumps(out, ensure_ascii=False, default=str)) <= MAX_CARACTERES:
            return out
        listas = [(len(json.dumps(v, ensure_ascii=False, default=str)), k) for k, v in out.items()
                  if isinstance(v, list) and len(v) > 1]
        if not listas:
            break
        _, k = max(listas)
        out[k] = out[k][:max(1, len(out[k]) * 3 // 4)]
        out["recortado"] = True
    return out


def analizar(db: Database, c: Consulta, hoy: date | None = None, *, politicos: bool = False) -> dict:
    """El análisis pedido, ya protegido y recortado. `politicos`: se pueden usar los datos políticos (A o K con
    `agente_politicos` encendido para la vía de la petición, `api/analitica.py`); sin él, una consulta que los use
    responde 403 y `fuente` no nombra las bases políticas."""
    exigir_etiqueta(db, c.filtros)
    exigir_politicos(db, c, politicos)
    d = Datos(db, c.filtros, hoy, politicos=politicos)
    out = ANALISIS[c.tipo](d, c)
    if out == POCAS:
        return dict(POCAS)
    if c.filtros is not None:
        out["filtros"] = a_filtros(c.filtros)
    out["nota_autorizacion"] = NOTA_AUTORIZACION
    return ajustar(out)


def catalogo(db: Database, politicos: bool = False) -> dict:
    """Lo que admite la analítica: tipos con sus parámetros, dimensiones, métricas, eventos y filtros (y los puestos
    de la elección vigente, para `puesto_id`). Las dimensiones y los filtros políticos, solo con `politicos`."""
    aj = modelo.leer_ajustes(db)
    descripciones = {
        "tabla": "Conteos y métricas por 1 o 2 dimensiones de personas",
        "serie": "Un evento en el tiempo (día, semana o mes) con su tendencia",
        "embudo": "De las personas vigentes al contacto útil y al voto verificado, con la mayor caída",
        "cobertura": "Registrados por puesto frente a los habilitados del censo y la meta",
        "brechas": "Barrios y veredas con su índice de atención, del más desatendido",
        "equipo": "Lo que hizo cada usuario en el periodo frente a la mediana del equipo",
        "calidad": "Completitud, datos que faltan, duplicados, conflictos, solicitudes y pendientes de calidad",
        "anomalias": "Picos, horarios, teléfonos repetidos, duplicados y mesas fuera de lo esperado (solo conteos)",
        "cohortes": "Por mes de alta: qué tan rápido se aborda, contacta y autoriza",
        "ritmo": ("Al ritmo actual, a qué cobertura llega cada puesto en la fecha meta y cuántas altas por semana "
                  "faltan"),
        "franjas": "Tasa de contacto por hora, día, canal y franja; dentro y fuera del horario",
        "intentos": "Probabilidad de contacto en cada intento y la espera que mejor funciona",
        "captura": "Calidad de las fichas por quien las capturó, frente a la mediana",
        "comparar": "Qué explica el cambio de una métrica entre dos periodos (mezcla frente a tasa)",
        "reuniones_efecto": "Altas, autorizaciones y contactos 4 semanas antes y después de cada reunión",
        "diagnostico": "Hallazgos ordenados por urgencia con evidencia, acción y enlace a Habitantes",
    }
    return {
        "tipos": {t: {"descripcion": descripciones[t], "obligatorios": sorted(PARAMETROS[t][0]),
                      "opcionales": sorted(PARAMETROS[t][1])} for t in TIPOS},
        "dimensiones": {"personas": [x for x in DIM_PERSONA if politicos or x not in DIM_POLITICAS],
                        "varios_grupos": [x for x in MULTI if politicos or x not in DIM_POLITICAS],
                        "eventos": list(DIM_EVENTO), "comparar": DIM_COMPARAR},
        "metricas": list(METRICAS), "eventos": DESGLOSES, "granularidades": list(GRANULARIDADES),
        "metricas_comparar": list(METRICAS_COMPARAR),
        "filtros": sorted(k for k in FiltrosConsulta.model_fields if politicos or k not in FILTROS_POLITICOS),
        "fuentes_filtro": list(FUENTES_FILTRO if politicos else FUENTES_SEGURAS), "faltan": list(FALTAN),
        "valores": {"dias_brechas": list(DIAS_BRECHAS), "sin_acercamiento_dias": list(DIAS_SIN_ACERCAMIENTO)},
        "limites": {"minimo_poblacion": MINIMO_POBLACION, "minimo_celda": MINIMO_CELDA, "max_filtros": MAX_FILTROS,
                    "max_grupos": MAX_GRUPOS, "max_puntos": MAX_PUNTOS, "max_dias": MAX_DIAS,
                    "max_caracteres": MAX_CARACTERES},
        "eleccion_vigente": aj.get("eleccion_vigente"),
        "puestos": [{"id": p["_id"], "codigo": p.get("codigo"), "nombre": p.get("nombre"), "mesas": p.get("mesas")}
                    for p in bd.puestos_vigentes(db, aj.get("eleccion_vigente"))],
    }
