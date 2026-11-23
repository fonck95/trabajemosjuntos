"""Analítica avanzada (solo A y K: permiso `analitica.ver`). El cálculo y sus reglas de privacidad están en
`app/analitica.py`; aquí solo se lee y valida la consulta.

* `GET /api/analitica?consulta=<json>`: un análisis (`analitica.Consulta`: `tipo` y solo los parámetros de ese tipo).
  Es un GET con la consulta en la URL, no un POST con cuerpo: es una lectura (no escribe, no audita, no registra
  lecturas: solo da agregados), y así el asistente la pide como cualquier otra lectura por `ApiInterna`. La consulta
  no lleva datos de personas (solo dimensiones, fechas y filtros de catálogo). Una consulta mal formada responde 422
  `invalido` con los errores en `campos` (el asistente se los pasa al modelo para que corrija).
* `GET /api/analitica/catalogo`: los tipos, dimensiones, métricas, eventos y filtros que se admiten, con los límites.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from pymongo.database import Database

from .. import analitica as motor
from ..acceso import Quien, requiere
from ..seguridad import obtener_db

r = APIRouter(prefix="/api", tags=["analitica"])
VER = requiere("analitica.ver")
MAX_CONSULTA = 4000  # caracteres del JSON de la consulta (una consulta válida ocupa unos cientos)


def _invalida(mensaje: str, campos: list[str] | None = None) -> HTTPException:
    return HTTPException(422, {"mensaje": mensaje, "codigo": "invalido", **({"campos": campos} if campos else {})})


def leer_consulta(texto: str | None) -> motor.Consulta:
    """La consulta del parámetro `consulta`, validada (422 `invalido` si no lo es)."""
    if not texto:
        raise _invalida("Falta la consulta: mande ?consulta=<JSON> con al menos el tipo (vea /api/analitica/catalogo)")
    if len(texto) > MAX_CONSULTA:
        raise _invalida(f"La consulta no puede pasar de {MAX_CONSULTA} caracteres")
    try:
        datos = json.loads(texto)
    except ValueError:
        raise _invalida("La consulta no es un JSON válido") from None
    try:
        return motor.Consulta.model_validate(datos)
    except ValidationError as e:
        errores = [f"{x['msg']} en {'.'.join(map(str, x['loc'])) or 'la consulta'}" for x in e.errors()[:10]]
        raise _invalida("La consulta no es válida: " + "; ".join(errores[:3]), errores) from None


@r.get("/analitica")
def analitica(consulta: str | None = Query(None), db: Database = Depends(obtener_db), _: Quien = Depends(VER)):
    """Un análisis agregado de la base (sin quienes no autorizaron, con supresión de celdas pequeñas)."""
    return motor.analizar(db, leer_consulta(consulta))


@r.get("/analitica/catalogo")
def catalogo(db: Database = Depends(obtener_db), _: Quien = Depends(VER)):
    return motor.catalogo(db)
