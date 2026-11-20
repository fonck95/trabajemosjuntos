"""Registro de las fuentes que alimentan la base única y forma común de sus filas (2.1).

Cada fuente se reconoce por sus columnas (`tipo_de_archivo` las prueba de mayor a menor prioridad: la planilla antes
que la base general y que la base con cédula, que comparten columnas con ella; a igual prioridad, en el orden de
`FUENTES`) y entrega `Registro`s. Los trámites siguen con su agrupación propia (`cruce.agrupar_tramites`). Para sumar
una fuente basta una función `leer_x(ruta) -> Iterator[Registro]` y su entrada en `FUENTES`.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Iterator

from . import texto as tx


@dataclass
class Registro:
    """Una fila de una fuente con cédula (base unificada, planilla de campo…), ya normalizada."""
    fuente: str
    fila: int
    clave_fila: str
    cedula: str | None
    tipo_documento: str | None
    nombre: str
    telefonos: list[str] = field(default_factory=list)
    correo: str | None = None
    direccion: str | None = None
    lugar_texto: str | None = None
    sexo: str | None = None
    edad: int | None = None
    fecha_nacimiento: str | None = None
    puesto_texto: str | None = None
    mesa_texto: str | None = None
    listas: list[str] = field(default_factory=list)
    autorizacion: str | None = None
    autorizacion_medio: str | None = None
    canales: list[str] = field(default_factory=list)
    planillero: str | None = None
    fecha: str | None = None
    observaciones: str | None = None
    # Base general de la campaña (y cualquier fuente que los traiga)
    ocupacion: str | None = None
    perfil_profesional: str | None = None
    estado_civil: str | None = None
    jefe_hogar: bool | None = None
    tipos: list[str] = field(default_factory=list)       # modelo.TIPOS_PERSONA que la fila marca
    lider_ref: dict | None = None                         # «Liderado por»: {cedula, nombre} del líder o concejal
    datos: dict = field(default_factory=dict)

    def dict(self) -> dict:
        return asdict(self)


def clave_fila(cedula: str | None, nombre: str, nacimiento: str | int | None, telefonos: list[str],
               lugar_texto: str | None) -> str:
    """Identifica una fila en todas las importaciones: la cédula; sin ella, una huella del nombre, la fecha de
    nacimiento (o la edad), el primer teléfono y el barrio o vereda, sin el número de fila (insertar filas o reordenar
    la planilla no la cambia)."""
    if cedula:
        return cedula
    partes = (tx.nombre_norm(nombre), str(nacimiento or ""), (telefonos or [""])[0], tx.limpiar(lugar_texto))
    return hashlib.sha1("|".join(partes).encode()).hexdigest()


@dataclass(frozen=True)
class Fuente:
    clave: str
    nombre: str
    columnas: frozenset[str | tuple[str, ...]]  # cada una, un nombre o una tupla de nombres alternativos (basta uno)
    prioridad: int
    leer: Callable[[Path], Iterator[Registro]] | None  # None: trámites (agrupación propia)
    tiene_cedula: bool


def _leer(clave: str) -> Callable[[Path], Iterator[Registro]]:
    def leer(ruta: Path) -> Iterator[Registro]:
        from . import lectores  # aquí: lectores usa este módulo
        return lectores.leer_registros(ruta, clave)
    return leer


# Columnas (normalizadas: mayúsculas, sin tildes, espacios ni signos) que reconocen cada fuente
COLUMNAS_PLANILLA = frozenset({"CEDULA", "NOMBRECOMPLETO", "AUTORIZACIONDEDATOS"})
COLUMNAS_CEDULAS = frozenset({"CEDULA", "NOMBRECOMPLETO"})
COLUMNAS_TRAMITES = frozenset({"ID", "NUMERO", "FECHA", "NOMBRESOLICITANTE", "DIRECCION"})
# Base general de la campaña: el documento (CC o Cédula), el nombre y algo de la campaña (líder, votante, grupo…)
COLUMNAS_GENERAL = frozenset({
    ("CC", "CEDULA", "DOCUMENTO", "NUMERODEDOCUMENTO"),
    ("NOMBRECOMPLETO", "NOMBRECOMPLETPO", "NOMBRE", "NOMBRES"),
    ("LIDER", "LIDERADOPOR", "VOTANTE", "CONCEJAL", "GRUPO", "TIPO", "TIPODEPERSONA")})

PLANILLA = Fuente("planilla", "Planilla de campo", COLUMNAS_PLANILLA, 3, _leer("planilla"), True)
GENERAL = Fuente("general", "Base general de la campaña", COLUMNAS_GENERAL, 2, _leer("general"), True)
CEDULAS = Fuente("cedulas", "Base unificada con cédula", COLUMNAS_CEDULAS, 2, _leer("cedulas"), True)
TRAMITES = Fuente("tramites", "Trámites por vereda", COLUMNAS_TRAMITES, 1, None, False)
FUENTES = [PLANILLA, GENERAL, CEDULAS, TRAMITES]
POR_CLAVE = {f.clave: f for f in FUENTES}
