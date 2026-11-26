"""Lo mínimo de cada persona que se le entrega al modelo (Ley 1581: el modelo es un tercero; finalidad y circulación
restringida).

Se aplica DESPUÉS de la proyección por rol de la API: solo quita y enmascara (una máscara sale de un campo que la API
ya mandó, nunca de la base), así que un planillero o un consultor nunca recibe más que en la interfaz. Reglas:

* Lista blanca de campos. Fuera siempre: datos sensibles (`sensibles*`, `regimen_salud`, las etiquetas y los campos
  propios marcados como sensibles), `origen`, `procedencia`, `historial`, `alternos`, `coincidencias` (nombres de
  otras personas), `punto`/`lat`/`lon`, `correo`, el número de ficha, la fecha de nacimiento exacta, los teléfonos
  completos y los trámites. De quien registró o tomó algo (`uid`, `usuario`) no sale nada: no hace falta para la tarea.
* Los datos políticos (el tipo de persona: `lider`, `votante`, `concejal`; el «Liderado por»: `lideres`, `lideres_n`,
  `traidas`; las `listas` de origen; las `fuentes` y la `cedula_origen`, que nombran las bases «cedulas» y
  «general») salen solo con `Politicos` (`agente_politicos` encendido para la vía de la llamada,
  `Contexto.politicos`) y solo los que la API ya le mandó al rol: A y K, todos; P, el tipo y el «Liderado por» de las
  personas de su zona o que registró (`proyeccion.tipo_visible`); C, ninguno. Sin `Politicos` (el ajuste apagado)
  no salen, tampoco como nombres en `editables` ni `faltan`. Un líder que no autorizó el tratamiento nunca se nombra
  en el «Liderado por» de otra persona (`Politicos.no_autorizaron`): que lidera es un dato suyo.
* La cédula sale enmascarada («···123») también para el administrador; los teléfonos, con su estado y su `indice` (el
  que pide `registrar_acercamiento`) y el número enmascarado («···2233»).
* De quien no autorizó el tratamiento («No autorizó») solo sale quién es, que no autorizó y su barrio o vereda si es
  del nomenclátor (nunca el lugar escrito a mano, `lugar_texto`): ni para el administrador se le pasan sus datos al
  modelo. Para verla, la persona del equipo abre la ficha en el panel.
* Los textos libres (notas, observaciones, dirección, el lugar escrito a mano, también el `lugar` de las filas, y los
  campos propios) van recortados y con los números largos (7 o más dígitos, también escritos por grupos: «300 111 22
  33», «604 - 832 12 34», «71.234.567») y los correos enmascarados: los escriben personas del equipo, pueden traer un
  teléfono o una cédula copiados, y el modelo los trata como datos, nunca como instrucciones. Las fechas y los
  periodos («2018-2022», «07 / 11 / 2026») quedan como están.
* Las etiquetas y los campos propios se filtran con `Sensibles` (lo que la base marca como sensible). Sin ese dato la
  ficha sale sin etiquetas ni campos propios: ante la duda, no se manda.
* La descripción de una foto (`enmascarar_descripcion`), más estricta: la escribe el lector de fotos copiando el texto
  de la imagen tal cual, así que tapa desde 5 dígitos y une los grupos de más formas (ver el comentario de esa parte).
  `descripcion_con_datos` y `numeros_de_descripcion` le dicen a la bandeja si trae datos de alguien y qué cédulas.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Container, Iterable

from .. import acceso, modelo

AVISO_NO_AUTORIZO = "No autorizó el tratamiento de sus datos: el asistente no los recibe. Ábrala en el panel."
TEXTO_MAX, LUGAR_MAX = 300, 120
NOTAS_MAX, ACERCAMIENTOS_MAX, REUNIONES_MAX = 5, 5, 10

CAMPOS_FILA = (
    "id", "nombre", "cedula_ult3", "tiene_cedula", "telefonos_n", "telefono_mascara", "lugar", "lugar_tipo", "zona",
    "precision", "completitud", "reuniones", "consentimiento", "ultimo_contacto", "sexo", "rango_edad", "menor",
    "puesto", "mesa", "votacion_estado", "abordaje", "abordaje_estado", "contactable", "faltan",
    "requiere_actualizacion", "situacion", "parecido", "cedula_distinta",
    # Fila de la cola del consultor (4.5): con qué número (su índice) y por qué canal, sin el número
    "telefono_indice", "whatsapp", "canales_permitidos",
)
CAMPOS_FICHA = (
    "id", "nombre", "tipo_documento", "cedula_ult3", "cedula_verificada", "sexo", "edad_efectiva", "rango_edad",
    "menor", "estado_civil", "nivel_educativo", "situacion_laboral", "ocupacion", "personas_hogar", "jefe_hogar",
    "tenencia_vivienda", "estrato", "lugar_id", "lugar_nombre", "lugar_tipo", "zona", "geo_precision", "geo_manual",
    "puesto_nombre", "puesto_votacion", "mesa", "consentimiento", "consentimiento_fecha", "consentimiento_medio",
    "consentimiento_canales", "contacto_habilitado", "mayor_declarado", "reclamo_en_tramite", "faltan", "editables",
    "avisos", "completitud", "ultimo_contacto", "creado_en", "actualizado_en",
)
# El tipo de persona y el «Liderado por» (datos políticos): sin `Politicos`, ni como valor ni como nombre en
# `editables` o `faltan`
POLITICOS = frozenset({*modelo.TIPOS_PERSONA, "lideres"})
TIPOS = tuple(modelo.TIPOS_PERSONA)
LISTA_MAX = 120     # el nombre de una lista de origen
LIDERES_MAX = 10    # como `api.lideres.MAX_LIDERES`
# Textos libres de la ficha que pasan, recortados y enmascarados
TEXTOS_FICHA = ("direccion", "lugar_texto", "observaciones")
CLAVES_ABORDAJE = ("estado", "n", "efectivos", "intentos_sin_exito", "ultimo_fecha", "ultimo_canal", "ultimo_resultado",
                   "proximo", "proximo_franja")
CLAVES_VOTACION = ("puesto_id", "puesto_nombre", "puesto_texto", "puesto_codigo", "mesa", "mesa_texto", "donde",
                   "municipio")

# Números de 7 o más dígitos (cédulas, teléfonos), también escritos por grupos: con espacios (hasta 3), puntos, comas,
# guiones, rayas, barras o paréntesis («300 111 22 33», «(604) 832 12 34», «71.234.567», «+57 300 111-2233»), y con
# espacios alrededor de un guion, una raya o un punto («604 - 832 12 34», «300 – 111 – 22 33»). La coma y la barra van
# pegadas: en «300 111 22 33 / 310 444 55 66» hay dos números. «calle 50 # 48 - 21» no es un número: el «#» corta y lo
# que sigue tiene 4 dígitos.
_ESPACIO = r"[ \t\u00a0\u2007\u202f]"
_GUION = r"[.\-\u2010-\u2015]"
_SEP = rf"(?:{_ESPACIO}{{0,3}}{_GUION}{_ESPACIO}{{0,3}}|{_ESPACIO}{{1,3}}|[,/])"
_NUMEROS = re.compile(rf"(?<!\d)\+?(?:\(\d+\)|\d+)(?:{_SEP}?\(\d+\)|{_SEP}\d+|(?<=\))\d+)*")
DIGITOS_MIN = 7
# Las fechas (2026-11-07, 07/11/2026, también con espacios: 07 / 11 / 2026) y los periodos (2018-2022, 2018 – 2022)
# quedan como están
_E = rf"{_ESPACIO}{{0,3}}"
_FECHAS = re.compile(
    rf"(?<!\d)(?:(?P<a>\d{{4}}){_E}(?P<s>[-./\u2010-\u2015]){_E}(?P<m>\d{{1,2}}){_E}(?P=s){_E}(?P<d>\d{{1,2}})"
    rf"|(?P<d2>\d{{1,2}}){_E}(?P<s2>[-./\u2010-\u2015]){_E}(?P<m2>\d{{1,2}}){_E}(?P=s2){_E}(?P<a2>\d{{4}})"
    rf"|(?P<desde>(?:19|20)\d\d){_E}[-/\u2010-\u2015]{_E}(?P<hasta>(?:19|20)\d\d))(?!\d)")
_CORREOS = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


@dataclass(frozen=True)
class Politicos:
    """Que la respuesta lleve los datos políticos que la API ya le dio al rol (`agente_politicos` encendido para la
    vía de la llamada). `no_autorizaron`: los líderes de las personas de la respuesta que no autorizaron el
    tratamiento (no se nombran). `traidas`: lo que trajo la persona de la ficha, contado sin quienes no autorizaron
    (lo pone la herramienta: la API cuenta a todos); sin él, la ficha va sin `traidas`."""
    no_autorizaron: frozenset[int] = field(default_factory=frozenset)
    traidas: dict | None = None


@dataclass(frozen=True)
class Sensibles:
    """Lo que la base marca como sensible: ids de etiquetas y claves de campos propios (`sensibles_de`)."""
    etiquetas: frozenset[int] = field(default_factory=frozenset)
    campos: frozenset[str] = field(default_factory=frozenset)


def sensibles_de(db: Any) -> Sensibles:
    """Lee las etiquetas y los campos propios sensibles (pymongo, síncrono: correr con `run_in_threadpool`). Usa la
    misma regla que la proyección: la marca `sensible` o, sin marca, los nombres de la migración."""
    from .. import proyeccion  # aquí: proyeccion importa la base y FastAPI, que no hacen falta para lo demás
    return Sensibles(frozenset(proyeccion.etiquetas_sensibles(db)), frozenset(proyeccion.campos_sensibles(db)))


def lugares_de(db: Any) -> frozenset[str]:
    """Los nombres de los barrios y veredas del nomenclátor (pymongo, síncrono: correr con `run_in_threadpool`). En las
    filas de planilleros y consultores, `lugar` es el nombre del barrio o vereda o, sin él, el texto libre de la ficha,
    y la API no dice cuál: con estos nombres, `no_autorizo` reconoce el primero."""
    return frozenset(lg["nombre"] for lg in db.lugares.find({}, {"nombre": 1}) if isinstance(lg.get("nombre"), str))


def _enmascarar_numero(m: re.Match) -> str:
    digitos = re.sub(r"\D", "", m.group(0))
    return f"{acceso.MASCARA}{digitos[-3:]}" if len(digitos) >= DIGITOS_MIN else m.group(0)


def _es_fecha(m: re.Match) -> bool:
    if m.group("desde"):
        return int(m.group("desde")) <= int(m.group("hasta"))
    a, mes, dia = (m.group("a"), m.group("m"), m.group("d")) if m.group("a") else (m.group("a2"), m.group("m2"),
                                                                                       m.group("d2"))
    return 1900 <= int(a) <= 2099 and 1 <= int(mes) <= 12 and 1 <= int(dia) <= 31


def _sin_numeros(t: str) -> str:
    """`t` con los números largos enmascarados («···233»), sin tocar las fechas ni los periodos."""
    partes, desde = [], 0
    for f in _FECHAS.finditer(t):
        if _es_fecha(f):
            partes += [_NUMEROS.sub(_enmascarar_numero, t[desde:f.start()]), f.group(0)]
            desde = f.end()
    partes.append(_NUMEROS.sub(_enmascarar_numero, t[desde:]))
    return "".join(partes)


def texto_libre(v: Any, n: int = TEXTO_MAX) -> Any:
    """Un texto escrito por el equipo, recortado a `n` caracteres y sin números largos ni correos completos. Un número
    (un campo propio numérico) sale igual, salvo que sea largo: puede ser un teléfono o una cédula."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        t = str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)  # 3001112233.0, de un Excel
        tapado = _sin_numeros(t)
        return v if tapado == t else tapado
    if not isinstance(v, str):
        return v
    t = _sin_numeros(_CORREOS.sub("[correo]", v))  # primero los correos: un número dentro de uno no deja su comienzo
    return t[:n] + "…" if len(t) > n else t


# La descripción de una foto de la bandeja (`lector_planillas.descripcion_de`), como la recibe el modelo de una
# conversación (`planillas.detalle` con `enmascarada=1`): más estricta que `texto_libre`, porque la escribe otro modelo
# mirando una imagen que puede traer documentos, listas o carteles, y copia su texto tal cual. Cualquier número de 5 o
# más dígitos queda en «…» y sus 3 últimos dígitos, también escrito por grupos («1.234.567», «310 123 4567»,
# «90-000-101», «(604) 832-1234», «1,234,567,890»). Une los grupos lo mismo que en `texto_libre` y algo más, porque
# aquí se tapa desde 5 dígitos y el texto viene de una imagen: hasta 3 espacios, o un punto, un guion (también el
# signo menos, el de ancho completo o el bajo), una raya, un punto medio o una barra con hasta 3 espacios alrededor,
# una coma pegada, un paréntesis o un salto de línea («310 123\n4567»). Un número largo seguido de otro
# («3101234567/3209876543», «3101234567 3209876543») se tapa por partes si cada una tiene 5 o más dígitos; si no, entero
# (`_tapar_digitos`). De un correo quedan su primer carácter y el dominio («a…@dominio.com»). Las fechas válidas
# (02/11/2026, 2026-11-30, 30 / 11 / 2026) y los periodos (2018-2022) quedan como están, como en `texto_libre`.
# Un valor en pesos («$ 10.000») también se tapa (no se distingue con certeza de un número de alguien), pero no cuenta
# como dato de una persona (`descripcion_con_datos`).
DESCRIPCION_DIGITOS_MIN = 5
DESCRIPCION_MASCARA = "…"
_D_UNE = r"[.\-‐-―−﹘﹣－．·‧・_]"
_D_CORTE = r"[/／]"
_D_SEP = (rf"(?:{_ESPACIO}{{0,3}}(?:{_D_UNE}|{_D_CORTE}){_ESPACIO}{{0,3}}|{_ESPACIO}{{0,3}}\n{_ESPACIO}{{0,3}}"
          rf"|{_ESPACIO}{{1,3}}|[,，])")
_DESCRIPCION_NUMEROS = re.compile(rf"(?<!\d)(?:\(\d+\)|\d+)(?:{_D_SEP}?\(\d+\)|{_D_SEP}\d+|(?<=\))\d+)*")
_D_GRUPO = re.compile(r"\(?\d+\)?")
_D_CORTES = re.compile(rf"[,，]|{_D_CORTE}")
_D_MONEDA_ANTES = re.compile(r"(?:\$|\bCOP|\bUSD|\bUS\$)[ \t ]?$", re.I)
_D_MONEDA_DESPUES = re.compile(r"^[ \t ]?(?:pesos\b|COP\b|millones\b|mil\b)", re.I)


def _digitos(t: str) -> str:
    """Los dígitos de `t`, en ASCII (un dígito de ancho completo cuenta igual)."""
    return "".join(str(unicodedata.digit(ch)) for ch in t if ch.isdecimal())


def _partes_numero(t: str) -> list[tuple[int, int]]:
    """Dónde empieza y termina cada parte de un número por grupos (un acierto de `_DESCRIPCION_NUMEROS`) que se tapa
    sola: cada grupo, si todos tienen 5 o más dígitos («3101234567 3209876543»); si no, lo que separan las comas y las
    barras, si cada parte los tiene («300 111 22 33 / 310 444 55 66»); si no, el número entero («310 / 123 / 4567»)."""
    grupos = list(_D_GRUPO.finditer(t))
    if not grupos:
        return []
    if len(grupos) > 1 and all(len(_digitos(g.group(0))) >= DESCRIPCION_DIGITOS_MIN for g in grupos):
        return [(g.start(), g.end()) for g in grupos]
    partes, desde = [], grupos[0].start()
    for a, b in zip(grupos, grupos[1:]):
        if _D_CORTES.search(t[a.end():b.start()]):
            partes.append((desde, a.end()))
            desde = b.start()
    partes.append((desde, grupos[-1].end()))
    if len(partes) > 1 and all(len(_digitos(t[x:y])) >= DESCRIPCION_DIGITOS_MIN for x, y in partes):
        return partes
    return [(grupos[0].start(), grupos[-1].end())]


def _tapar_digitos(m: re.Match) -> str:
    t, out, desde = m.group(0), [], 0
    for x, y in _partes_numero(t):
        digitos = _digitos(t[x:y])
        out += [t[desde:x], f"{DESCRIPCION_MASCARA}{digitos[-3:]}" if len(digitos) >= DESCRIPCION_DIGITOS_MIN
                else t[x:y]]
        desde = y
    return "".join(out) + t[desde:]


def _tapar_correo(m: re.Match) -> str:
    usuario, dominio = m.group(0).split("@", 1)
    return f"{usuario[:1]}{DESCRIPCION_MASCARA}@{dominio}"


def _fuera_de_fechas(t: str) -> list[tuple[int, str]]:
    """Los trozos de `t` (con dónde empiezan) que no son una fecha o un periodo válidos."""
    trozos, desde = [], 0
    for f in _FECHAS.finditer(t):
        if _es_fecha(f):
            trozos.append((desde, t[desde:f.start()]))
            desde = f.end()
    trozos.append((desde, t[desde:]))
    return trozos


def enmascarar_descripcion(v: Any) -> str:
    """La descripción de una foto como la puede recibir el modelo de una conversación (ver arriba): sin números de 5 o
    más dígitos (quedan «…» y sus 3 últimos) ni correos enteros («a…@dominio.com»), con las fechas como están. Los
    saltos de línea y lo demás no cambian. «» si no es un texto."""
    if not isinstance(v, str):
        return ""
    t = _CORREOS.sub(_tapar_correo, v)  # primero los correos: los dígitos de uno no dejan su comienzo
    partes, desde = [], 0
    for inicio, trozo in _fuera_de_fechas(t):
        partes += [t[desde:inicio], _DESCRIPCION_NUMEROS.sub(_tapar_digitos, trozo)]
        desde = inicio + len(trozo)
    return "".join(partes) + t[desde:]


def numeros_de_descripcion(v: Any) -> list[tuple[str, bool]]:
    """Los números que `enmascarar_descripcion` tapa, como (sus dígitos en ASCII, ¿es un valor en pesos?): un número
    con «$», «COP» o «USD» antes, o «pesos», «mil» o «millones» después. Con ellos la bandeja decide si la descripción
    trae datos de alguien (`descripcion_con_datos`) y calcula sus huellas (las de una cédula, para la supresión)."""
    if not isinstance(v, str):
        return []
    t, out = _CORREOS.sub("", v), []
    for _, trozo in _fuera_de_fechas(t):
        for m in _DESCRIPCION_NUMEROS.finditer(trozo):
            for x, y in _partes_numero(m.group(0)):
                digitos = _digitos(m.group(0)[x:y])
                if len(digitos) < DESCRIPCION_DIGITOS_MIN:
                    continue
                antes, despues = trozo[:m.start() + x], trozo[m.start() + y:]
                monto = bool(_D_MONEDA_ANTES.search(antes[-6:]) or _D_MONEDA_DESPUES.search(despues[:12]))
                out.append((digitos, monto))
    return out


def descripcion_con_datos(v: Any) -> bool:
    """Si la descripción trae un dato de alguien aunque el lector no lo haya dicho (`datos_personales`): un correo o
    un número de 5 o más dígitos que no es un valor en pesos (una cédula, un teléfono). La bandeja enciende con esto
    `datos_personales` (`planillas._guardar_lectura`)."""
    if not isinstance(v, str):
        return False
    return bool(_CORREOS.search(v)) or any(not monto for _, monto in numeros_de_descripcion(v))


def _abordaje(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: v[k] for k in CLAVES_ABORDAJE if k in v}
    return v


def _situacion(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: v[k] for k in ("estado", "confirmada") if k in v}
    return v


def _requiere(v: Any) -> Any:
    """`requiere_actualizacion` sin su nota libre ni quién la pidió: basta el motivo."""
    if isinstance(v, dict):
        return {"motivo": v.get("motivo")}
    return v if isinstance(v, str) else None


def _barrio_o_vereda(d: dict, lugares: Container[str] | None) -> str | None:
    """El barrio o vereda de `d` si es del nomenclátor; el texto libre de la ficha (`lugar_texto`), nunca. Ante la duda,
    nada: en la ficha del administrador y del coordinador lo dice `lugar_nombre`; en sus filas, `lugar_tipo` (sin
    barrio ni vereda reconocidos, `lugar` es el texto libre); en las de planilleros y consultores, solo los nombres del
    nomenclátor (`lugares_de`)."""
    if "lugar_nombre" in d:
        lugar = d.get("lugar_nombre")
    elif "lugar_tipo" in d:
        lugar = d.get("lugar") if d.get("lugar_tipo") else None
    else:
        lugar = d.get("lugar")
        lugar = lugar if isinstance(lugar, str) and lugares is not None and lugar in lugares else None
    return texto_libre(lugar, LUGAR_MAX) if isinstance(lugar, str) and lugar else None


def ids_lideres(docs: Iterable[Any]) -> set[int]:
    """Los ids de los líderes que nombran las filas o fichas de la API (su «Liderado por»): para saber cuáles no
    autorizaron antes de minimizar (`Politicos.no_autorizaron`)."""
    out: set[int] = set()
    for d in docs or []:
        for l in (d.get("lideres") if isinstance(d, dict) and isinstance(d.get("lideres"), list) else []):
            i = l.get("id") if isinstance(l, dict) else None
            if isinstance(i, int) and not isinstance(i, bool):
                out.add(i)
    return out


def lideres(v: Any, politicos: Politicos) -> list[dict]:
    """El «Liderado por» de una fila o ficha: quién la lidera (id, nombre y si es líder o concejal; en la ficha, si
    sigue marcado), sin quién lo asignó y sin los líderes que no autorizaron."""
    out = []
    for l in v if isinstance(v, list) else []:
        i = l.get("id") if isinstance(l, dict) else None
        if not isinstance(i, int) or isinstance(i, bool) or i in politicos.no_autorizaron:
            continue
        x = {"id": i, "nombre": l.get("nombre"), "tipo": l.get("tipo")}
        if isinstance(l.get("marcado"), bool):
            x["marcado"] = l["marcado"]
        out.append(x)
    return out[:LIDERES_MAX]


def _listas(v: Any) -> list[str]:
    return [texto_libre(x, LISTA_MAX) for x in v if isinstance(x, str) and x.strip()] if isinstance(v, list) else []


def _fuentes(v: Any) -> list[str]:
    return [x for x in v if isinstance(x, str)] if isinstance(v, list) else []


def _politicos_fila(f: dict, out: dict, politicos: Politicos) -> None:
    """Los datos políticos de una fila que la API ya trae para el rol (A y K: el tipo, el «Liderado por» y las
    fuentes; P y C no los reciben en sus filas)."""
    for t in TIPOS:
        if t in f:
            out[t] = f[t] is True
    if isinstance(f.get("lideres"), list):
        out["lideres"] = lideres(f["lideres"], politicos)
        out["lideres_n"] = len(out["lideres"])
    elif isinstance(f.get("lideres_n"), int) and not isinstance(f.get("lideres_n"), bool):
        out["lideres_n"] = f["lideres_n"]
    if "fuentes" in f:
        out["fuentes"] = _fuentes(f["fuentes"])


def no_autorizo(d: dict, lugares: Container[str] | None = None) -> dict:
    """De quien no autorizó el tratamiento: quién es, que no autorizó y su barrio o vereda del nomenclátor."""
    return {"id": d.get("id"), "nombre": d.get("nombre"), "lugar": _barrio_o_vereda(d, lugares),
            "consentimiento": "no", "aviso": AVISO_NO_AUTORIZO}


def fila(f: dict, lugares: Container[str] | None = None, politicos: Politicos | None = None) -> dict:
    """Una fila de Habitantes, de la búsqueda, de las parecidas, de una cola o de una lista de asistentes, ya
    proyectada por rol. `lugar` puede ser el texto libre de la ficha: pasa por las máscaras. `lugares`
    (`lugares_de`), si se tiene, reconoce el barrio o vereda de quien no autorizó en las filas que no lo dicen.
    `politicos`: con los datos políticos que la fila ya trae para el rol (sin él, ninguno)."""
    if not isinstance(f, dict):
        return {}
    if f.get("consentimiento") == "no":
        return no_autorizo(f, lugares)
    out = {k: f[k] for k in CAMPOS_FILA if k in f}
    if "lugar" in out:
        out["lugar"] = texto_libre(out["lugar"], LUGAR_MAX)
    if "cedula_ult3" not in out and "cedula" in f:  # A y K reciben la cédula completa: solo sus 3 últimos dígitos
        out["cedula_ult3"] = acceso.enmascarar_cedula(f.get("cedula"))
    if "telefono_mascara" not in out and "telefono" in f:  # A, K y la cola reciben el número completo
        out["telefono_mascara"] = None if f.get("menor") else acceso.enmascarar_telefono(f.get("telefono"))
    if "abordaje" in out:
        out["abordaje"] = _abordaje(out["abordaje"])
    if "situacion" in out:
        out["situacion"] = _situacion(out["situacion"])
    if "requiere_actualizacion" in out:
        out["requiere_actualizacion"] = _requiere(out["requiere_actualizacion"])
    if politicos is not None:
        _politicos_fila(f, out, politicos)
    return out


def filas(fs: Iterable[dict], lugares: Container[str] | None = None,
          politicos: Politicos | None = None) -> list[dict]:
    return [fila(f, lugares, politicos) for f in fs or [] if isinstance(f, dict)]


def _telefonos(ts: Any) -> list[dict]:
    out = []
    for t in ts if isinstance(ts, list) else []:
        if not isinstance(t, dict):
            continue
        x = {"numero": acceso.enmascarar_telefono(t.get("numero")), "tipo": t.get("tipo"), "estado": t.get("estado"),
             "whatsapp": t.get("whatsapp"), "indice": t.get("indice")}
        if t.get("indice") == 0:  # el primero usable es el que la ficha muestra como principal
            x["principal"] = True
        if t.get("no_contactar"):
            x["no_contactar"] = True
        out.append(x)
    return out


def _votacion(v: Any) -> dict | None:
    if not isinstance(v, dict):
        return None
    out = {k: v[k] for k in CLAVES_VOTACION if v.get(k) is not None}
    out["estado"] = v.get("estado_efectivo") or v.get("estado")
    return out


def _lista(d: dict, clave: str) -> list[dict] | None:
    v = d.get(clave)
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else None


def ficha(d: dict, sensibles: Sensibles | None = None, lugares: Container[str] | None = None,
          politicos: Politicos | None = None) -> dict:
    """La ficha de `GET /api/personas/{id}` (o la que devuelve una escritura), proyectada por rol, reducida a lo que el
    modelo necesita. Las listas de la API llegan de la más reciente a la más vieja: se toman las primeras. `lugares`,
    como en `fila`: la ficha de quien no autorizó, para planilleros y consultores, no dice si `lugar` es del
    nomenclátor. `politicos`: con los datos políticos que la ficha ya trae para el rol (sin él, ninguno)."""
    if not isinstance(d, dict):
        return {}
    if d.get("consentimiento") == "no":
        return no_autorizo(d, lugares)
    out = {k: d[k] for k in CAMPOS_FICHA if k in d}
    # Sin `politicos`, ni el tipo de persona ni el «Liderado por» en las listas que pasan tal cual: los `editables` de P
    # traen solo los tipos que la persona todavía no tiene (P solo suma), así que cambian de una persona a otra y
    # dirían su tipo. Con `politicos`, P ya recibe el tipo de esas mismas personas (`tipo_visible`): pasan como están
    if politicos is None:
        for k in ("editables", "faltan"):
            if isinstance(out.get(k), list):
                out[k] = [x for x in out[k] if x not in POLITICOS]
    else:
        for t in TIPOS:
            if t in d:
                out[t] = d[t] is True
        if isinstance(d.get("lideres"), list):
            out["lideres"] = lideres(d["lideres"], politicos)
        if "listas" in d:
            out["listas"] = _listas(d["listas"])
        if "fuentes" in d:
            out["fuentes"] = _fuentes(d["fuentes"])
        if isinstance(d.get("cedula_origen"), str):
            out["cedula_origen"] = d["cedula_origen"]
        if d.get("traidas") is not None and isinstance(politicos.traidas, dict):
            out["traidas"] = dict(politicos.traidas)
    if d.get("cedula"):
        out["cedula_ult3"] = acceso.enmascarar_cedula(d["cedula"])
    if "cedula" in d or "cedula_ult3" in d:
        out["tiene_cedula"] = bool(d.get("cedula") or d.get("cedula_ult3"))
    if "correo" in d:
        out["tiene_correo"] = bool(d.get("correo"))
    for k in TEXTOS_FICHA:
        if d.get(k):
            out[k] = texto_libre(d[k])
    if "telefonos" in d:
        out["telefonos"] = _telefonos(d["telefonos"])
    if "votacion" in d:
        out["votacion"] = _votacion(d["votacion"])
    if "abordaje" in d:
        out["abordaje"] = _abordaje(d["abordaje"])
    if "situacion" in d:
        out["situacion"] = _situacion(d["situacion"])
    if "requiere_actualizacion" in d:
        out["requiere_actualizacion"] = _requiere(d["requiere_actualizacion"])
    if isinstance(d.get("no_disponible"), dict):
        out["no_disponible"] = {c: (m.get("motivo") if isinstance(m, dict) else m)
                                for c, m in d["no_disponible"].items()}
    if isinstance(d.get("en_curso"), dict):
        out["en_curso"] = {"hasta": d["en_curso"].get("hasta")}
    notas = _lista(d, "notas")
    if notas is not None:
        out["notas_n"] = len(notas)
        out["notas"] = [{"texto": texto_libre(n.get("texto")), "autor": n.get("autor"), "creado_en": n.get("creado_en")}
                        for n in notas[:NOTAS_MAX]]
    acs = _lista(d, "acercamientos")
    if acs is not None:
        out["acercamientos_n"] = len(acs)
        out["acercamientos"] = [{k: a[k] for k in ("fecha", "canal", "resultado", "anulado", "proximo")
                                 if a.get(k) not in (None, False)} for a in acs[:ACERCAMIENTOS_MAX]]
    reus = _lista(d, "reuniones")
    if reus is not None:
        out["reuniones_n"] = len(reus)
        out["reuniones"] = [{"id": r.get("id"), "titulo": texto_libre(r.get("titulo"), 120), "fecha": r.get("fecha")}
                            for r in reus[:REUNIONES_MAX]]
    if isinstance(d.get("tramites"), list):
        out["tramites_n"] = len(d["tramites"])
    if sensibles is not None:
        ets = _lista(d, "etiquetas")
        if ets is not None:
            out["etiquetas"] = [{k: e.get(k) for k in ("id", "nombre", "grupo")} for e in ets
                                if e.get("id") not in sensibles.etiquetas]
        if isinstance(d.get("extra"), dict):  # texto, número o sí/no; otra cosa, como texto (pasa por las máscaras)
            out["extra"] = {k: texto_libre(v if v is None or isinstance(v, (str, int, float)) else str(v), 120)
                            for k, v in d["extra"].items() if k not in sensibles.campos}
    return out


def ids_de(fs: Iterable[Any]) -> set[int]:
    """Los ids de personas de una lista de filas (para la supresión: la conversación recuerda a quién vio)."""
    return {f["id"] for f in fs or [] if isinstance(f, dict) and isinstance(f.get("id"), int)
            and not isinstance(f.get("id"), bool)}
