"""Lectores de los archivos de Excel que alimentan la base única.

Reconoce cada archivo por sus encabezados, no por su nombre, para que se pueda volver a subir una versión nueva:

* **Trámites por vereda** (hoja «Table»: ID, Número, Fecha, Nombre Solicitante, Dirección, Correo, Teléfono, Paquete).
  El nombre trae delante el trámite: «MODIFICACIÓN DE FICHA - ODILIA SARMIENTO PEÑA».
* **Base unificada con cédula** (hoja «Base unificada»: Cédula, Nombre completo, Teléfono(s), Correo, Municipio,
  Puesto de votación, Mesa…, Lista(s), Archivo(s) de origen).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import Iterator

import openpyxl

from . import texto as tx


@dataclass
class FilaTramite:
    id_externo: str
    ficha: str
    fecha: str | None          # ISO AAAA-MM-DD
    tramite: str
    nombre: str
    direccion: str
    correo: str
    telefonos: list[str]
    paquete: str


@dataclass
class FilaCedula:
    cedula: str
    nombre: str
    telefonos: list[str]
    correo: str
    municipio: str
    puesto: str
    mesa: str
    mesa_testigo: str
    partido: str
    edad: int | None
    sexo: str
    direccion: str
    detalle: str
    listas: list[str]
    otros_nombres: str
    origen: str
    extra: dict = field(default_factory=dict)


def _clave(s: object) -> str:
    return tx.nombre_norm(s).replace(" ", "")


def _fecha(v: object) -> str | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    s = str(v).strip().split(" ")[0]
    for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def _texto(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _hoja_con(wb, columnas: set[str]):
    """Primera hoja cuya fila de encabezado (en las 5 primeras filas) contiene todas las columnas pedidas."""
    for ws in wb.worksheets:
        for i, fila in enumerate(ws.iter_rows(values_only=True, max_row=5)):
            claves = {_clave(c) for c in fila if c is not None}
            if columnas <= claves:
                return ws, i, [_clave(c) for c in fila]
    return None, None, None


TRAMITES = {"ID", "NUMERO", "FECHA", "NOMBRESOLICITANTE", "DIRECCION"}
CEDULAS = {"CEDULA", "NOMBRECOMPLETO"}


def tipo_de_archivo(ruta: str | Path) -> str | None:
    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    try:
        if _hoja_con(wb, TRAMITES)[0] is not None:
            return "tramites"
        if _hoja_con(wb, CEDULAS)[0] is not None:
            return "cedulas"
        return None
    finally:
        wb.close()


def leer_tramites(ruta: str | Path) -> Iterator[FilaTramite]:
    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    try:
        ws, fila_enc, enc = _hoja_con(wb, TRAMITES)
        if ws is None:
            raise ValueError("El archivo no tiene una hoja con ID, Número, Fecha, Nombre Solicitante y Dirección")
        col = {c: i for i, c in enumerate(enc)}
        for i, f in enumerate(ws.iter_rows(values_only=True)):
            if i <= fila_enc or not any(f):
                continue
            g = lambda c: f[col[c]] if c in col and col[c] < len(f) else None  # noqa: E731
            tramite, nombre = tx.separar_tramite(g("NOMBRESOLICITANTE"))
            if not tx.nombre_norm(nombre):
                continue
            yield FilaTramite(
                id_externo=_texto(g("ID")), ficha=_texto(g("NUMERO")), fecha=_fecha(g("FECHA")), tramite=tramite,
                nombre=nombre, direccion=_texto(g("DIRECCION")), correo=tx.correo(g("CORREO")),
                telefonos=tx.telefonos(g("TELEFONO")), paquete=_texto(g("PAQUETE")),
            )
    finally:
        wb.close()


def leer_cedulas(ruta: str | Path) -> Iterator[FilaCedula]:
    wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    try:
        ws, fila_enc, enc = _hoja_con(wb, CEDULAS)
        if ws is None:
            raise ValueError("El archivo no tiene una hoja con Cédula y Nombre completo")
        col = {c: i for i, c in enumerate(enc)}

        def busca(f, *opciones):
            for c in opciones:
                if c in col and col[c] < len(f) and f[col[c]] not in (None, ""):
                    return f[col[c]]
            return None

        for i, f in enumerate(ws.iter_rows(values_only=True)):
            if i <= fila_enc or not any(f):
                continue
            ced = tx.cedula(busca(f, "CEDULA"))
            nombre = tx.nombre_visible(busca(f, "NOMBRECOMPLETO"))
            if not ced or not tx.nombre_norm(nombre):
                continue
            edad = busca(f, "EDADSEGUNFUENTE", "EDAD")
            try:
                edad = int(float(edad)) if edad is not None else None
                if edad is not None and not 0 < edad < 115:
                    edad = None
            except (TypeError, ValueError):
                edad = None
            sexo = _texto(busca(f, "SEXO")).upper()[:1]
            listas = [s.strip() for s in _texto(busca(f, "LISTAS", "LISTA")).split(";") if s.strip()]
            yield FilaCedula(
                cedula=ced, nombre=nombre, telefonos=tx.telefonos(busca(f, "TELEFONOS", "TELEFONO")),
                correo=tx.correo(busca(f, "CORREO")), municipio=_texto(busca(f, "MUNICIPIO")),
                puesto=_texto(busca(f, "PUESTODEVOTACION")), mesa=_texto(busca(f, "MESADONDEVOTA")),
                mesa_testigo=_texto(busca(f, "MESACOMOTESTIGO")), partido=_texto(busca(f, "PARTIDOGRUPO")),
                edad=edad, sexo=sexo if sexo in ("F", "M") else "", direccion=_texto(busca(f, "DIRECCION")),
                detalle=_texto(busca(f, "DETALLE")), listas=listas,
                otros_nombres=_texto(busca(f, "OTROSNOMBRESREGISTRADOS")),
                origen=_texto(busca(f, "ARCHIVOSDEORIGEN")),
            )
    finally:
        wb.close()
