"""Lectores de los archivos de Excel que alimentan la base única.

Reconoce cada archivo por sus encabezados, no por su nombre, para que se pueda volver a subir una versión nueva:

* **Trámites por vereda** (hoja «Table»: ID, Número, Fecha, Nombre Solicitante, Dirección, Correo, Teléfono, Paquete).
  El nombre trae delante el trámite: «MODIFICACIÓN DE FICHA - ODILIA SARMIENTO PEÑA».
* **Base unificada con cédula** (hoja «Base unificada»: Cédula, Nombre completo, Teléfono(s), Correo, Municipio,
  Puesto de votación, Mesa…, Lista(s), Archivo(s) de origen).
* **Planilla de campo** (hoja «Planilla» de GET /api/plantillas/planilla.xlsx: Cédula, Repita la cédula, Nombre
  completo, teléfonos, demografía, puesto y mesa, autorización y planillero). Se prueba antes que la base con cédula.

Las fuentes con cédula entregan `fuentes.Registro` (`leer_registros`); `FilaCedula` y `leer_cedulas` siguen iguales.
"""
from __future__ import annotations

import zipfile
import zlib
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import Iterator

import openpyxl
from openpyxl.utils.exceptions import InvalidFileException

from . import texto as tx

# Topes del .xlsx descomprimido, para que un archivo pequeño no se infle en memoria al abrirlo (bomba zip)
MAX_DESCOMPRIMIDO = 200 * 1024 * 1024   # bytes de todos los miembros del zip
MAX_RAZON = 100                         # descomprimido / comprimido de un miembro grande (un Excel real ronda 5-15)
MAX_MIEMBROS = 2000
NO_ES_XLSX = "El archivo no es un Excel .xlsx válido (¿es un .xls antiguo o está dañado?)"
# Lo que openpyxl lanza ante un archivo que no es un .xlsx o está dañado (SyntaxError cubre los XML rotos)
_ERRORES_LIBRO = (zipfile.BadZipFile, zipfile.LargeZipFile, InvalidFileException, KeyError, OSError, EOFError,
                  zlib.error, SyntaxError)


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


def validar_xlsx(ruta: str | Path) -> None:
    """Revisa el .xlsx como zip antes de abrirlo: openpyxl carga entera la tabla de textos y no limita cuánto se
    descomprime. Lanza ValueError (la API responde 422) si no es un zip o si se inflaría demasiado."""
    try:
        with zipfile.ZipFile(ruta) as z:
            miembros = z.infolist()
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, EOFError) as e:
        raise ValueError(NO_ES_XLSX) from e
    if len(miembros) > MAX_MIEMBROS:
        raise ValueError(f"El archivo tiene demasiadas partes ({len(miembros)}) para ser un Excel normal")
    total = sum(m.file_size for m in miembros)
    if total > MAX_DESCOMPRIMIDO:
        raise ValueError(f"El Excel ocupa {total >> 20} MB al descomprimirlo (máximo {MAX_DESCOMPRIMIDO >> 20} MB)")
    for m in miembros:
        if m.file_size > (1 << 20) and m.file_size > MAX_RAZON * max(m.compress_size, 1):
            raise ValueError("El Excel está comprimido de forma anómala (posible bomba zip) y no se abre")


@contextmanager
def _libro(ruta: str | Path):
    """Libro de solo lectura; un archivo dañado o que no es .xlsx da ValueError, no un error 500."""
    validar_xlsx(ruta)
    try:
        wb = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    except _ERRORES_LIBRO as e:
        raise ValueError(NO_ES_XLSX) from e
    try:
        yield wb
    except (zipfile.BadZipFile, EOFError, zlib.error, SyntaxError) as e:  # partes que se leen al recorrer las filas
        raise ValueError(NO_ES_XLSX) from e
    finally:
        wb.close()


def tipo_de_archivo(ruta: str | Path) -> str | None:
    """«planilla», «cedulas» o «tramites» según las columnas (de la fuente de mayor prioridad a la de menor); None si
    no es ninguna."""
    from .fuentes import FUENTES  # aquí: fuentes usa este módulo
    with _libro(ruta) as wb:
        for f in sorted(FUENTES, key=lambda f: -f.prioridad):
            if _hoja_con(wb, set(f.columnas))[0] is not None:
                return f.clave
        return None


def leer_tramites(ruta: str | Path) -> Iterator[FilaTramite]:
    with _libro(ruta) as wb:
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


# Cómo puede venir escrito el sexo; lo demás queda vacío («MUJER» no es «M»)
_SEXO = {"F": "F", "FEM": "F", "FEMENINO": "F", "FEMENINA": "F", "MUJER": "F",
         "M": "M", "MASC": "M", "MASCULINO": "M", "HOMBRE": "M", "H": "M"}


def leer_cedulas(ruta: str | Path) -> Iterator[FilaCedula]:
    with _libro(ruta) as wb:
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
            sexo = _SEXO.get(tx.nombre_norm(busca(f, "SEXO")), "")
            listas = [s.strip() for s in _texto(busca(f, "LISTAS", "LISTA")).split(";") if s.strip()]
            yield FilaCedula(
                cedula=ced, nombre=nombre, telefonos=tx.telefonos(busca(f, "TELEFONOS", "TELEFONO")),
                correo=tx.correo(busca(f, "CORREO")), municipio=_texto(busca(f, "MUNICIPIO")),
                puesto=_texto(busca(f, "PUESTODEVOTACION")), mesa=_texto(busca(f, "MESADONDEVOTA")),
                mesa_testigo=_texto(busca(f, "MESACOMOTESTIGO")), partido=_texto(busca(f, "PARTIDOGRUPO")),
                edad=edad, sexo=sexo, direccion=_texto(busca(f, "DIRECCION")),
                detalle=_texto(busca(f, "DETALLE")), listas=listas,
                otros_nombres=_texto(busca(f, "OTROSNOMBRESREGISTRADOS")),
                origen=_texto(busca(f, "ARCHIVOSDEORIGEN")),
            )


# ───────────────────────────── Registros de las fuentes con cédula ─────────────────────────────

def a_registro(f: FilaCedula, fila: int = 0):
    """La fila de la base con cédula como `Registro` (tipo de documento CC). Lo que no tiene campo propio (municipio,
    mesa como testigo, partido…) queda en `datos`, que solo ve el administrador."""
    from .fuentes import Registro
    return Registro(
        fuente="cedulas", fila=fila, clave_fila=f.cedula, cedula=f.cedula, tipo_documento="CC", nombre=f.nombre,
        telefonos=list(f.telefonos), correo=f.correo or None, direccion=f.direccion or None, lugar_texto=None,
        sexo=f.sexo or None, edad=f.edad, fecha_nacimiento=None, puesto_texto=f.puesto or None, mesa_texto=f.mesa or None,
        listas=list(f.listas), datos={k: v for k, v in f.__dict__.items() if v not in (None, "", [], {})})


PLANILLA = {"CEDULA", "NOMBRECOMPLETO", "AUTORIZACIONDEDATOS"}


def _inverso(catalogo: dict) -> dict:
    """Etiqueta o clave (normalizadas) → clave de un catálogo de modelo.py."""
    out = {}
    for k, v in catalogo.items():
        out[_clave(k)] = k
        out[_clave(v)] = k
    return out


def _fecha_local(v: object) -> str | None:
    """Fecha de una celda: fecha de Excel o texto AAAA-MM-DD, DD/MM/AAAA o DD-MM-AAAA (como se escribe en Colombia)."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    s = str(v).strip().split(" ")[0]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def _si_no(v: object) -> bool | None:
    t = _clave(v)
    return True if t in ("SI", "S", "X") else False if t in ("NO", "N") else None


def leer_planilla(ruta: str | Path):
    """Filas de la planilla de campo como `Registro`s. Si «Cédula» y «Repita la cédula» difieren, la fila va sin cédula
    y las dos quedan en `datos` (cedula_digitada y cedula_repetida) para el conflicto de posible digitación."""
    from .. import modelo
    from .fuentes import Registro, clave_fila
    tipos = {**{_clave(k): k for k in modelo.TIPOS_DOCUMENTO}, **_inverso(modelo.TIPOS_DOCUMENTO)}
    sexos = {**_inverso(modelo.SEXOS), **{k: v for k, v in _SEXO.items()}}
    estados = {**_inverso(modelo.ESTADOS_AUTORIZACION), "SI": "si", "NO": "no", "AUTORIZA": "si"}
    medios = _inverso(modelo.MEDIOS_AUTORIZACION)
    canales = _inverso(modelo.CANALES_AUTORIZACION)
    with _libro(ruta) as wb:
        ws, fila_enc, enc = _hoja_con(wb, PLANILLA)
        if ws is None:
            raise ValueError("El archivo no tiene una hoja con Cédula, Nombre completo y Autorización de datos")
        col = {c: i for i, c in enumerate(enc)}

        def busca(f, *opciones):
            for c in opciones:
                if c in col and col[c] < len(f) and f[col[c]] not in (None, ""):
                    return f[col[c]]
            return None

        for i, f in enumerate(ws.iter_rows(values_only=True)):
            if i <= fila_enc or not any(x not in (None, "") for x in f):
                continue
            nombre = tx.nombre_visible(busca(f, "NOMBRECOMPLETO"))
            if not tx.nombre_norm(nombre):
                continue
            datos: dict = {"fila": i + 1}
            cedula = tx.cedula(busca(f, "CEDULA")) or None
            repetida_cruda = busca(f, "REPITALACEDULA")
            repetida = tx.cedula(repetida_cruda) or None
            if repetida_cruda is not None and cedula != repetida:
                datos.update(cedula_digitada=cedula, cedula_repetida=repetida or _texto(repetida_cruda))
                cedula = None
            tipo = tipos.get(_clave(busca(f, "TIPODEDOCUMENTO")))
            tels = []
            for t in (*tx.telefonos(busca(f, "CELULAR", "TELEFONO")), *tx.telefonos(busca(f, "OTROTELEFONO"))):
                if t not in tels:
                    tels.append(t)
            edad = busca(f, "EDAD")
            try:
                edad = int(float(edad)) if edad is not None else None
                if edad is not None and not 0 <= edad <= 120:
                    edad = None
            except (TypeError, ValueError):
                edad = None
            fecha_nac = _fecha_local(busca(f, "FECHADENACIMIENTO"))
            barrio = _texto(busca(f, "BARRIOOVEREDA")) or None
            direccion = _texto(busca(f, "DIRECCION")) or None
            if barrio and tx.limpiar(barrio) not in tx.limpiar(direccion or ""):
                direccion = f"{direccion}, {barrio}" if direccion else barrio
            mesa = busca(f, "MESA")
            lista_canales = [canales[_clave(c)] for c in str(busca(f, "CANALESAUTORIZADOS") or "").replace(";", ",").split(",")
                             if _clave(c) in canales]
            reg = Registro(
                fuente="planilla", fila=i + 1, clave_fila="", cedula=cedula,
                tipo_documento=tipo or ("CC" if cedula else None), nombre=nombre, telefonos=tels,
                direccion=direccion, lugar_texto=barrio, sexo=sexos.get(_clave(busca(f, "SEXO"))), edad=edad,
                fecha_nacimiento=fecha_nac, puesto_texto=_texto(busca(f, "PUESTODEVOTACION")) or None,
                mesa_texto=_texto(mesa) or None, autorizacion=estados.get(_clave(busca(f, "AUTORIZACIONDEDATOS"))),
                autorizacion_medio=medios.get(_clave(busca(f, "MEDIODELAAUTORIZACION"))),
                canales=list(dict.fromkeys(lista_canales)),
                planillero=_texto(busca(f, "PLANILLEROUSUARIO", "PLANILLERO")).lower() or None,
                fecha=_fecha_local(busca(f, "FECHA")), observaciones=_texto(busca(f, "OBSERVACIONES")) or None)
            reg.clave_fila = clave_fila(cedula, nombre, fecha_nac or edad, tels, barrio)
            datos["mayor_de_18"] = _si_no(busca(f, "MAYORDE"))
            reg.datos = {**{k: v for k, v in reg.dict().items()
                            if k not in ("fuente", "fila", "clave_fila", "datos") and v not in (None, "", [], {})},
                         **{k: v for k, v in datos.items() if v is not None}}
            yield reg


def leer_registros(ruta: str | Path, fuente: str):
    """Las filas de una fuente con cédula como `Registro`s."""
    if fuente == "planilla":
        yield from leer_planilla(ruta)
    elif fuente == "cedulas":
        for i, f in enumerate(leer_cedulas(ruta), 1):
            yield a_registro(f, i)
    else:
        raise ValueError(f"La fuente {fuente} no entrega registros")
