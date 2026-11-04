"""Qué ve cada rol de una persona: las respuestas se arman solo con los campos permitidos, nunca copiando el documento
y quitando campos.

* `CAMPOS_FICHA[rol]` y `CAMPOS_FILA[rol]`: claves de primer nivel de la ficha y de las filas que puede recibir cada
  rol. `sensibles` y `cedula_en_traspaso` no están en ninguna lista, tampoco en la de A.
* Algunos campos llevan además un recorte por dentro, que aplica quien arma la respuesta (3.8): teléfonos solo usables
  para C, sin teléfonos para P si es menor, acercamientos sin `nota` para P, trámites con `fecha`, `tipo` y `ficha`
  para P, `situacion.estado` para C, `en_curso` propio, `abordaje` con solo `estado` en `CAMPOS_NO_AUTORIZO`.
* Para P y C la fuente «cedulas» se muestra como «otra_base» (`neutralizar_fuente`).
* `exigir_tratable` va en toda escritura sobre una persona: a quien no autorizó, P y C no lo tratan.
"""
from __future__ import annotations

from typing import Any, Iterable

from fastapi import HTTPException
from pymongo.database import Database

# ───────────────────────────── Ficha ─────────────────────────────

_IDENTIDAD_A = {"id", "nombre", "nombre_norm", "tipo_documento", "cedula", "cedula_verificada", "cedula_origen",
                "cedulas_anteriores"}
_DEMOGRAFIA = {"sexo", "edad", "edad_ref", "fecha_nacimiento", "nac_aprox", "nac_exacta", "edad_efectiva", "rango_edad",
               "menor", "estado_civil", "nivel_educativo", "situacion_laboral", "ocupacion", "personas_hogar",
               "jefe_hogar", "tenencia_vivienda", "estrato", "regimen_salud"}
_UBICACION = {"correo", "direccion", "direccion_norm", "lugar_id", "lugar_nombre", "lugar_tipo", "lugar_texto", "zona",
              "lat", "lon", "geo_precision", "geo_manual", "geo_fuente", "precision_m", "ficha"}
_VOTACION = {"votacion", "puesto_votacion", "mesa"}
_AUTORIZACION = {"consentimiento", "consentimiento_fecha", "consentimiento_medio", "consentimiento_canales",
                 "contacto_habilitado", "mayor_declarado"}
_SEGUIMIENTO = {"requiere_actualizacion", "situacion", "no_disponible", "faltan", "editables", "avisos"}

CAMPOS_FICHA: dict[str, frozenset[str]] = {
    "admin": frozenset(
        _IDENTIDAD_A | _DEMOGRAFIA | _UBICACION | _VOTACION | _AUTORIZACION | _SEGUIMIENTO
        | {"sensibles_registrados", "sensibles_autorizados", "telefonos", "telefono", "telefono2", "autorizacion",
           "autorizacion_ultima", "reclamo_en_tramite", "abordaje", "abordaje_seq", "acercamientos", "ultimo_contacto",
           "en_curso", "notas", "listas", "lider", "etiquetas", "extra", "observaciones", "origen", "procedencia",
           "tramites", "alternos", "avance", "historial", "coincidencias", "reuniones", "reunion_origen", "fuentes",
           "completitud", "clave_tramites", "claves_tramites", "creado_por", "actualizado_por", "creado_en",
           "actualizado_en", "fusionada_en", "eliminado", "punto", "nombre_fon"}),
    "planillero": frozenset(
        {"id", "nombre", "tipo_documento", "cedula", "cedula_verificada", "cedula_origen"} | _DEMOGRAFIA | _UBICACION
        | _VOTACION | _AUTORIZACION | _SEGUIMIENTO
        | {"sensibles_registrados", "telefonos", "telefono", "telefono2", "abordaje", "acercamientos", "ultimo_contacto",
           "notas", "etiquetas", "extra", "observaciones", "tramites", "alternos", "reuniones", "completitud"}),
    "consultor": frozenset(
        {"id", "nombre", "cedula_ult3", "rango_edad", "sexo", "telefonos", "lugar_nombre", "zona", "puesto_nombre",
         "consentimiento", "consentimiento_canales", "contacto_habilitado", "abordaje", "acercamientos",
         "requiere_actualizacion", "situacion", "faltan", "en_curso", "editables", "avisos"}),
}

# ───────────────────────────── Filas ─────────────────────────────

CAMPOS_FILA: dict[str, frozenset[str]] = {
    # Las de hoy (app/api/personas.py:53-58) más las nuevas de 8.1
    "admin": frozenset({
        "id", "nombre", "cedula", "telefono", "lugar", "lugar_tipo", "zona", "precision", "completitud", "fuentes",
        "reuniones", "lider", "consentimiento", "ultimo_contacto", "tiene_cedula", "telefonos_n", "sexo", "rango_edad",
        "menor", "puesto", "mesa", "votacion_estado", "abordaje", "faltan", "requiere_actualizacion", "situacion"}),
    "planillero": frozenset({
        "id", "nombre", "tiene_cedula", "cedula_ult3", "telefono_mascara", "telefonos_n", "lugar", "zona", "rango_edad",
        "sexo", "puesto", "mesa", "votacion_estado", "abordaje", "consentimiento", "faltan", "requiere_actualizacion",
        "menor", "situacion", "completitud"}),
    # La búsqueda del consultor
    "consultor": frozenset({"id", "nombre", "lugar", "abordaje_estado", "contactable"}),
}
# Fila de la cola del consultor (4.5)
CAMPOS_COLA = frozenset({"id", "nombre", "lugar", "zona", "rango_edad", "telefono_indice", "telefono", "whatsapp",
                         "canales_permitidos", "consentimiento", "abordaje"})
# Persona que no autorizó, para P y C, en filas y ficha (`abordaje` lleva solo su `estado`)
CAMPOS_NO_AUTORIZO = frozenset({"id", "nombre", "cedula_ult3", "lugar", "consentimiento", "abordaje"})
# Nadie los recibe
NUNCA = frozenset({"sensibles", "cedula_en_traspaso"})


def neutralizar_fuente(fuente: Any) -> Any:
    """Para P y C: «cedulas» se muestra como «otra_base» (en `telefonos[].fuentes`, `alternos[].fuente`,
    `votacion.fuente` y `cedula_origen`). Acepta un texto o una lista; una lista no repite valores."""
    if isinstance(fuente, (list, tuple)):
        return list(dict.fromkeys(neutralizar_fuente(f) for f in fuente))
    return "otra_base" if fuente == "cedulas" else fuente


# Lo único que P y C pueden hacer con quien no autorizó: registrar su «sí» (con evidencia, 1.6) y una solicitud
ACCIONES_SIN_AUTORIZACION = frozenset({"autorizacion", "solicitud"})
NO_AUTORIZO = {"mensaje": "Esta persona no autorizó el tratamiento de sus datos", "codigo": "no_contactable",
               "motivo": "no_autorizo"}


def exigir_tratable(p: dict, quien: Any, accion: str) -> None:
    """409 `{codigo: "no_contactable", motivo: "no_autorizo"}` si P o C intentan `accion` sobre una persona con
    `consentimiento == "no"` (PATCH, teléfonos, notas, ubicación, asistencia, acercamientos, duplicado, situación,
    no-disponible…). Solo se permiten `autorizacion` y `solicitud`. A puede todo. Sin `quien` se trata como P y C."""
    if getattr(quien, "es_admin", False):
        return
    if (p or {}).get("consentimiento") == "no" and accion not in ACCIONES_SIN_AUTORIZACION:
        raise HTTPException(409, dict(NO_AUTORIZO))


def ficha_para(db: Database, quien: Any, pid: int) -> dict:
    """La ficha de `pid` con los campos de `CAMPOS_FICHA[quien.rol]`, `editables`, `avisos` y `faltan`; registra la
    lectura. Lo implementa el grupo 3."""
    raise NotImplementedError("ficha_para: lo implementa el grupo 3")


def filas_para(quien: Any, docs: Iterable[dict]) -> list[dict]:
    """Las filas de `docs` con los campos de `CAMPOS_FILA[quien.rol]` (o `CAMPOS_NO_AUTORIZO`). Lo implementa el
    grupo 3."""
    raise NotImplementedError("filas_para: lo implementa el grupo 3")
