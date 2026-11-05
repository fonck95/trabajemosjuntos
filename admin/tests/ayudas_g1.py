"""Ayudas de las pruebas del grupo 1 (datos, identidad, fuentes y puestos). Solo datos inventados."""
from __future__ import annotations

import copy
import random
from pathlib import Path

from conftest import excel_cedulas, excel_planilla, excel_tramites

# La ficha tal como la dejaba el código anterior a la versión 2 del esquema (sin listas ni campos nuevos)
CAMPOS_VIEJOS = {
    "nombre": None, "nombre_norm": None, "cedula": None, "sexo": None, "edad": None, "fecha_nacimiento": None,
    "telefono": None, "telefono2": None, "correo": None, "direccion": None, "direccion_norm": None, "lugar_id": None,
    "lugar_texto": None, "zona": None, "lat": None, "lon": None, "geo_precision": None, "geo_manual": False,
    "ficha": None, "puesto_votacion": None, "mesa": None, "ocupacion": None, "nivel_educativo": None,
    "personas_hogar": None, "lider": False, "consentimiento": "pendiente", "consentimiento_fecha": None,
    "observaciones": None, "extra": {}, "fuentes": [], "clave_tramites": None, "completitud": 0, "ultimo_contacto": None,
    "fusionada_en": None, "eliminado": False, "listas": [], "etiquetas": [], "tramites": [], "notas": [], "origen": [],
    "asistencias": [], "claves_tramites": [], "reunion_origen": None,
}


def ficha_vieja(_id: int, **datos) -> dict:
    """Una ficha con la forma vieja (como la escribía `nueva_persona` antes de la versión 2)."""
    from app.pipeline import texto as tx
    doc = {**copy.deepcopy(CAMPOS_VIEJOS), "_id": _id, "fuentes": ["manual"], **datos}
    doc["nombre_norm"] = tx.nombre_norm(doc.get("nombre"))
    doc.setdefault("creado_en", "2025-03-01T15:00:00+00:00")
    doc.setdefault("actualizado_en", doc["creado_en"])
    return doc


def a_vieja(i: int, p: dict) -> dict:
    """Una persona de `personas_inventadas` como ficha vieja."""
    return ficha_vieja(i, **{k: v for k, v in p.items() if k in CAMPOS_VIEJOS})


def base_vieja(db) -> None:
    """Deja la base como antes de la migración: sin versión de esquema ni eventos migrados."""
    db.meta.delete_many({"_id": {"$in": ["esquema", "migracion"]}})


def importar(db, tmp_path: Path, tramites=None, cedulas=None, planilla=None, nombre: str = "x", **kw):
    from app.pipeline.importar import importar as imp
    rutas = []
    if tramites is not None:
        rutas.append(excel_tramites(tmp_path / f"t-{nombre}.xlsx", tramites))
    if cedulas is not None:
        rutas.append(excel_cedulas(tmp_path / f"c-{nombre}.xlsx", cedulas))
    if planilla is not None:
        rutas.append(excel_planilla(tmp_path / f"p-{nombre}.xlsx", planilla))
    return imp(db, rutas, "admin", **kw)


def cedula(ced, nombre, telefono=None, listas="Lista A", edad=40, sexo="F", puesto=None, mesa=None, correo=None,
           direccion=None):
    """Una fila de la base unificada con cédula (para `excel_cedulas`)."""
    return (ced, nombre, telefono, correo, None, puesto, mesa, None, None, edad, sexo, direccion, None, listas)


def tramite(i, nombre, telefono="", ficha=None, fecha="2/6/2025", direccion="VEREDA LA CONDOR", correo=""):
    return (str(i), ficha or f"05893{i:08d}", f"{fecha} 12:00:00 AM", f"NUEVA ENCUESTA - {nombre}", direccion, correo,
            telefono, 1)


def fila_planilla(cedula=None, nombre="PERSONA INVENTADA DE PLANILLA", celular=None, otro=None, repetida="igual",
                  tipo="CC", sexo="Mujer", nacimiento=None, edad=None, direccion=None, barrio=None, puesto=None,
                  mesa=None, autoriza="Sí autoriza", medio="Escrito", canales="Llamada", mayor="Sí",
                  planillero=None, fecha=None, observaciones=None):
    """Una fila de planilla en el orden de COLUMNAS_PLANILLA."""
    return (cedula, cedula if repetida == "igual" else repetida, tipo if cedula else None, nombre, celular, otro, sexo,
            nacimiento, edad, direccion, barrio, puesto, mesa, autoriza, medio, canales, mayor, planillero, fecha,
            observaciones)


# ───────── Muchos trámites y cédulas inventados (medición) ─────────

def tramites_inventados(n: int, semilla: int = 7) -> list[tuple]:
    """`n` filas de trámites inventadas: ~1 de cada 3 personas con dos o tres trámites."""
    from conftest import personas_inventadas
    rnd = random.Random(semilla)
    personas = personas_inventadas(int(n / 1.4) + 1, semilla=semilla)
    filas, i = [], 0
    for k, p in enumerate(personas):
        for _ in range(rnd.choice((1, 1, 2, 3)) if len(filas) < n else 0):
            if len(filas) >= n:
                break
            i += 1
            filas.append((str(500000 + i), f"05893{k:08d}", f"{rnd.randint(1, 12)}/{rnd.randint(1, 28)}/2025",
                          f"NUEVA ENCUESTA - {p['nombre']}", p["direccion"], "", p["telefono"] or "", 1))
    return filas[:n]
