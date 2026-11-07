"""Lo mínimo de cada persona que se le entrega al modelo (Ley 1581: el modelo es un tercero; finalidad y circulación
restringida).

Se aplica DESPUÉS de la proyección por rol de la API (nunca agrega campos: solo quita y enmascara), así que un
planillero o un consultor nunca recibe más que en la interfaz. Reglas:

* Lista blanca de campos. Fuera siempre: datos sensibles (`sensibles*`), `listas`, `lider`, `origen`, `procedencia`,
  `historial`, `alternos`, `fuentes` crudas, `punto`/`lat`/`lon`, `correo`, los teléfonos completos y los trámites.
* La cédula sale enmascarada («···123») también para el administrador; los teléfonos, solo como cuántos hay y su
  estado, con el número enmascarado («···2233»).
* De quien no autorizó el tratamiento («No autorizó») solo sale quién es y que no autorizó: ni para el administrador
  se le pasan sus datos al modelo. Para verla, la persona del equipo abre la ficha en el panel.
* Los textos libres (notas, observaciones) van recortados: los escriben personas del equipo y el modelo los trata como
  datos, nunca como instrucciones.
"""
from __future__ import annotations

from typing import Any, Iterable

from .. import acceso

AVISO_NO_AUTORIZO = "No autorizó el tratamiento de sus datos: el asistente no los recibe. Ábrala en el panel."
TEXTO_MAX = 300

CAMPOS_FILA = (
    "id", "nombre", "cedula_ult3", "tiene_cedula", "telefonos_n", "lugar", "lugar_tipo", "zona", "precision",
    "completitud", "reuniones", "consentimiento", "ultimo_contacto", "sexo", "rango_edad", "menor", "puesto", "mesa",
    "votacion_estado", "abordaje", "abordaje_estado", "contactable", "faltan", "requiere_actualizacion", "situacion",
    "parecido", "cedula_distinta",
)
CAMPOS_FICHA = (
    "id", "nombre", "tipo_documento", "cedula_ult3", "cedula_verificada", "sexo", "edad", "edad_efectiva",
    "rango_edad", "menor", "fecha_nacimiento", "estado_civil", "nivel_educativo", "situacion_laboral", "ocupacion",
    "personas_hogar", "jefe_hogar", "tenencia_vivienda", "estrato", "direccion_norm", "lugar_id", "lugar_nombre",
    "lugar_tipo", "zona", "geo_precision", "ficha", "votacion", "puesto_votacion", "mesa", "consentimiento",
    "consentimiento_fecha", "consentimiento_medio", "consentimiento_canales", "contacto_habilitado", "mayor_declarado",
    "requiere_actualizacion", "situacion", "no_disponible", "faltan", "editables", "avisos", "completitud",
    "etiquetas", "extra", "observaciones", "abordaje", "ultimo_contacto", "reclamo_en_tramite", "creado_en",
    "actualizado_en",
)
CLAVES_ABORDAJE = ("estado", "n", "ultimo_fecha", "ultimo_resultado", "ultimo_canal", "proximo", "proximo_franja")


def _texto(v: Any, n: int = TEXTO_MAX) -> Any:
    if isinstance(v, str) and len(v) > n:
        return v[:n] + "…"
    return v


def _abordaje(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: v[k] for k in CLAVES_ABORDAJE if k in v}
    return v


def _situacion(v: Any) -> Any:
    return {"estado": v.get("estado")} if isinstance(v, dict) else v


def no_autorizo(d: dict) -> dict:
    return {"id": d.get("id"), "nombre": d.get("nombre"), "lugar": d.get("lugar") or d.get("lugar_nombre"),
            "consentimiento": "no", "aviso": AVISO_NO_AUTORIZO}


def fila(f: dict) -> dict:
    """Una fila de Habitantes, de la búsqueda, de las parecidas o de una lista de asistentes, ya proyectada por rol."""
    if f.get("consentimiento") == "no":
        return no_autorizo(f)
    out = {k: f[k] for k in CAMPOS_FILA if k in f}
    if "cedula_ult3" not in out and f.get("cedula"):
        out["cedula_ult3"] = acceso.enmascarar_cedula(f.get("cedula"))
    if "abordaje" in out:
        out["abordaje"] = _abordaje(out["abordaje"])
    if "situacion" in out:
        out["situacion"] = _situacion(out["situacion"])
    return out


def filas(fs: Iterable[dict]) -> list[dict]:
    return [fila(f) for f in fs if isinstance(f, dict)]


def _telefonos(ts: Any) -> list[dict]:
    out = []
    for t in ts if isinstance(ts, list) else []:
        if isinstance(t, dict):
            out.append({"numero": acceso.enmascarar_telefono(t.get("numero")), "tipo": t.get("tipo"),
                        "estado": t.get("estado"), "whatsapp": t.get("whatsapp"), "indice": t.get("indice"),
                        "principal": t.get("principal")})
    return out


def ficha(d: dict) -> dict:
    """La ficha de `GET /api/personas/{id}` (proyectada por rol), reducida a lo que el modelo necesita."""
    if d.get("consentimiento") == "no":
        return no_autorizo(d)
    out = {k: d[k] for k in CAMPOS_FICHA if k in d}
    if d.get("cedula"):
        out["cedula_ult3"] = acceso.enmascarar_cedula(d["cedula"])
    elif d.get("cedula_ult3"):
        out["cedula_ult3"] = d["cedula_ult3"]
    out["tiene_correo"] = bool(d.get("correo"))
    if "telefonos" in d:
        out["telefonos"] = _telefonos(d["telefonos"])
    if "abordaje" in out:
        out["abordaje"] = _abordaje(out["abordaje"])
    if "situacion" in out:
        out["situacion"] = _situacion(out["situacion"])
    if "observaciones" in out:
        out["observaciones"] = _texto(out["observaciones"])
    if isinstance(d.get("notas"), list):
        out["notas"] = [{"texto": _texto(n.get("texto")), "autor": n.get("autor"), "creado_en": n.get("creado_en")}
                        for n in d["notas"][-5:] if isinstance(n, dict)]
    if isinstance(d.get("acercamientos"), list):
        out["acercamientos"] = [{k: a.get(k) for k in ("ts", "fecha", "canal", "resultado", "anulado")}
                                for a in d["acercamientos"][-5:] if isinstance(a, dict)]
    if isinstance(d.get("reuniones"), list):
        out["reuniones"] = [{k: r.get(k) for k in ("id", "titulo", "fecha", "rol")} if isinstance(r, dict) else r
                            for r in d["reuniones"][-10:]]
    if isinstance(d.get("tramites"), list):
        out["tramites_n"] = len(d["tramites"])
    if isinstance(out.get("extra"), dict):
        out["extra"] = {k: _texto(v, 120) for k, v in out["extra"].items()}
    return out


def ids_de(fs: Iterable[Any]) -> set[int]:
    """Los ids de personas de una lista de filas (para la supresión: la conversación recuerda a quién vio)."""
    return {f["id"] for f in fs if isinstance(f, dict) and isinstance(f.get("id"), int)}
