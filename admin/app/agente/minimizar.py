"""Lo mínimo de cada persona que se le entrega al modelo (Ley 1581: el modelo es un tercero; finalidad y circulación
restringida).

Se aplica DESPUÉS de la proyección por rol de la API: solo quita y enmascara (una máscara sale de un campo que la API
ya mandó, nunca de la base), así que un planillero o un consultor nunca recibe más que en la interfaz. Reglas:

* Lista blanca de campos. Fuera siempre: datos sensibles (`sensibles*`, `regimen_salud`, las etiquetas y los campos
  propios marcados como sensibles), `listas`, `lider`, `origen`, `procedencia`, `historial`, `alternos`, `fuentes` y
  `cedula_origen` (la fuente «cedulas» revela una base política), `coincidencias` (nombres de otras personas),
  `punto`/`lat`/`lon`, `correo`, el número de ficha, la fecha de nacimiento exacta, los teléfonos completos y los
  trámites. De quien registró o tomó algo (`uid`, `usuario`) no sale nada: no hace falta para la tarea.
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
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Container, Iterable

from .. import acceso

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


def no_autorizo(d: dict, lugares: Container[str] | None = None) -> dict:
    """De quien no autorizó el tratamiento: quién es, que no autorizó y su barrio o vereda del nomenclátor."""
    return {"id": d.get("id"), "nombre": d.get("nombre"), "lugar": _barrio_o_vereda(d, lugares),
            "consentimiento": "no", "aviso": AVISO_NO_AUTORIZO}


def fila(f: dict, lugares: Container[str] | None = None) -> dict:
    """Una fila de Habitantes, de la búsqueda, de las parecidas, de una cola o de una lista de asistentes, ya
    proyectada por rol. `lugar` puede ser el texto libre de la ficha: pasa por las máscaras. `lugares`
    (`lugares_de`), si se tiene, reconoce el barrio o vereda de quien no autorizó en las filas que no lo dicen."""
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
    return out


def filas(fs: Iterable[dict], lugares: Container[str] | None = None) -> list[dict]:
    return [fila(f, lugares) for f in fs or [] if isinstance(f, dict)]


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


def ficha(d: dict, sensibles: Sensibles | None = None, lugares: Container[str] | None = None) -> dict:
    """La ficha de `GET /api/personas/{id}` (o la que devuelve una escritura), proyectada por rol, reducida a lo que el
    modelo necesita. Las listas de la API llegan de la más reciente a la más vieja: se toman las primeras. `lugares`,
    como en `fila`: la ficha de quien no autorizó, para planilleros y consultores, no dice si `lugar` es del
    nomenclátor."""
    if not isinstance(d, dict):
        return {}
    if d.get("consentimiento") == "no":
        return no_autorizo(d, lugares)
    out = {k: d[k] for k in CAMPOS_FICHA if k in d}
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
