"""Ajustes del panel (política de contacto, aviso de privacidad, presupuestos, sesiones, elección vigente…), catálogo
de puestos de votación y plantilla de la planilla de campo."""
from __future__ import annotations

import io
import re
from typing import Literal

import openpyxl
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from .. import db as bd
from .. import modelo
from .. import acceso
from ..acceso import Quien, requiere
from ..seguridad import obtener_db

r = APIRouter(prefix="/api", tags=["ajustes"])

_HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_ELECCION = re.compile(r"^\d{4}-[a-z0-9-]{3,40}$")


# ───────────────────────────── Ajustes ─────────────────────────────

class Horario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    semana: list[str] | Literal[False] | None = None
    sabado: list[str] | Literal[False] | None = None
    domingo: list[str] | Literal[False] | None = None

    @field_validator("semana", "sabado", "domingo")
    @classmethod
    def _franja(cls, v):
        if v in (None, False):
            return v
        if len(v) != 2 or not all(_HORA.match(x) for x in v) or v[0] >= v[1]:
            raise ValueError("La franja es [desde, hasta] en HH:MM, con desde antes que hasta")
        return v


class Aviso(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str | None = Field(None, min_length=1, max_length=40)
    responsable: str | None = Field(None, max_length=200)
    contacto: str | None = Field(None, max_length=200)
    canal_derechos: str | None = Field(None, max_length=200)
    texto: str | None = Field(None, max_length=8000)


class Presupuesto(BaseModel):
    model_config = ConfigDict(extra="forbid")
    planillero: int | None = Field(None, ge=10, le=100000)
    consultor: int | None = Field(None, ge=10, le=100000)


class Sesion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    horas_max: int | None = Field(None, ge=1, le=24)
    inactividad_min: int | None = Field(None, ge=5, le=600)
    max_por_usuario: int | None = Field(None, ge=1, le=10)


class AjustesIn(BaseModel):
    """PUT parcial: solo cambia lo enviado (también dentro de los objetos). La vigencia de la base solo se muestra."""
    model_config = ConfigDict(extra="forbid")
    contactar_pendientes: bool | None = None
    dias_entre_intentos: int | None = Field(None, ge=1, le=60)
    max_intentos_sin_exito: int | None = Field(None, ge=1, le=20)
    seguimiento_activo: bool | None = None
    dias_seguimiento: int | None = Field(None, ge=7, le=365)
    dias_reintento_dato: int | None = Field(None, ge=7, le=730)
    horario: Horario | None = None
    sensibles_activos: bool | None = None
    eleccion_vigente: str | None = None
    aviso_privacidad: Aviso | None = None
    compromiso_version: str | None = Field(None, min_length=1, max_length=40)
    presupuesto_diario: Presupuesto | None = None
    sesion: Sesion | None = None
    tope_cedulas_dictadas: int | None = Field(None, ge=0, le=500)
    enlace_consulta_puesto: str | None = Field(None, max_length=300)

    @field_validator("eleccion_vigente")
    @classmethod
    def _eleccion(cls, v):
        if v is not None and not _ELECCION.match(v):
            raise ValueError("La elección se escribe como AAAA-nombre (por ejemplo 2027-territoriales)")
        return v

    @field_validator("enlace_consulta_puesto")
    @classmethod
    def _enlace(cls, v):
        if v and not re.match(r"^https://[^\s<>\"']+$", v):
            raise ValueError("El enlace debe empezar por https://")
        return v or None


# Ajustes que son permisos o límites de acceso (adenda del coordinador): solo los cambia quien tiene
# `permisos.modificar` (el administrador). El coordinador los ve en solo lectura. La lista y la regla son las de
# `acceso` (una sola fuente): presupuestos, sesiones, tope de cédulas dictadas, política de contacto, datos sensibles y
# versión del compromiso.
AJUSTES_DE_PERMISOS = acceso.AJUSTES_DE_PERMISOS


def _vista_ajustes(db: Database, quien: Quien) -> dict:
    return {**modelo.leer_ajustes(db), "elecciones": sorted(x for x in db.puestos.distinct("eleccion") if x),
            "catalogos_version": bd.catalogos_version(db),
            "ajustes_de_permisos": sorted(AJUSTES_DE_PERMISOS),
            "puede_modificar_permisos": quien.puede("permisos.modificar")}


@r.get("/ajustes")
def ver_ajustes(db: Database = Depends(obtener_db), quien: Quien = Depends(requiere("ajustes.gestionar"))):
    return _vista_ajustes(db, quien)


@r.put("/ajustes")
def guardar_ajustes(body: AjustesIn, db: Database = Depends(obtener_db),
                    quien: Quien = Depends(requiere("ajustes.gestionar"))):
    actuales = modelo.leer_ajustes(db)
    datos = {}
    for k, v in body.model_dump(exclude_unset=True).items():
        if isinstance(v, dict):  # dentro de los objetos también es parcial
            datos[k] = {**actuales[k], **{kk: vv for kk, vv in v.items() if vv is not None}}
        elif v is not None:
            datos[k] = v
    # Lo que no cambia el valor guardado no cuenta: el formulario del coordinador puede reenviar todo sin tocarlos
    datos = {k: v for k, v in datos.items() if v != actuales.get(k)}
    acceso.exigir_ajustes(quien, actuales, datos)
    if "eleccion_vigente" in datos and not db.puestos.find_one({"eleccion": datos["eleccion_vigente"]}, {"_id": 1}):
        raise HTTPException(422, "No hay puestos de esa elección: créelos antes de cambiar la elección vigente")
    if datos:
        db.meta.update_one({"_id": "ajustes"}, {"$set": datos}, upsert=True)
        bd.subir_catalogos_version(db)
        bd.auditar(db, quien, "ajustes", None, None, {"campos": sorted(datos)})
    return _vista_ajustes(db, quien)


# ───────────────────────────── Puestos de votación ─────────────────────────────

class Habilitados(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mujeres: int = Field(0, ge=0, le=1_000_000)
    hombres: int = Field(0, ge=0, le=1_000_000)


class PuestoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    eleccion: str | None = None
    codigo: str | None = Field(None, pattern=r"^\d{2}-\d{2}$")
    nombre: str | None = Field(None, min_length=3, max_length=120)
    alias: list[str] | None = Field(None, max_length=20)
    alias_ambiguos: list[str] | None = Field(None, max_length=20)
    area: Literal["cabecera", "rural"] | None = None
    lugar_id: int | None = None
    lat: float | None = Field(None, ge=6.3, le=7.5)
    lon: float | None = Field(None, ge=-74.6, le=-73.6)
    mesas: int | None = Field(None, ge=1, le=300)
    habilitados: Habilitados | None = None
    activo: bool | None = None

    @field_validator("eleccion")
    @classmethod
    def _eleccion(cls, v):
        if v is not None and not _ELECCION.match(v):
            raise ValueError("La elección se escribe como AAAA-nombre (por ejemplo 2027-territoriales)")
        return v

    @field_validator("alias", "alias_ambiguos")
    @classmethod
    def _alias(cls, v):
        return None if v is None else list(dict.fromkeys(a.strip().upper()[:120] for a in v if a and a.strip()))

    @model_validator(mode="after")
    def _punto(self):
        enviados = self.model_fields_set & {"lat", "lon"}
        if enviados and (enviados != {"lat", "lon"} or (self.lat is None) != (self.lon is None)):
            raise ValueError("Indique latitud y longitud juntas (o ninguna)")
        return self


def _puesto(p: dict, completo: bool = True) -> dict:
    if not completo:  # el consultor ve el código y el nombre
        return {"id": p["_id"], "codigo": p.get("codigo"), "nombre": p.get("nombre")}
    return {"id": p["_id"], **{k: v for k, v in p.items() if k != "_id"}}


@r.get("/puestos")
def puestos(eleccion: str | None = None, todos: int = 0, db: Database = Depends(obtener_db),
            quien: Quien = Depends(requiere("puestos.ver"))):
    eleccion = eleccion or modelo.leer_ajustes(db)["eleccion_vigente"]
    q: dict = {"eleccion": eleccion}
    if not (todos and quien.puede("puestos.gestionar")):
        q["activo"] = {"$ne": False}
    return [_puesto(p, quien.rol != "consultor") for p in db.puestos.find(q).sort("codigo", 1)]


def _validar_lugar(db: Database, lid: int | None) -> None:
    if lid is not None and not db.lugares.find_one({"_id": lid}, {"_id": 1}):
        raise HTTPException(422, "Ese barrio o vereda no existe")


@r.post("/puestos", status_code=201)
def crear_puesto(body: PuestoIn, db: Database = Depends(obtener_db),
                 quien: Quien = Depends(requiere("puestos.gestionar"))):
    if not body.codigo or not body.nombre or not body.mesas:
        raise HTTPException(422, "Código (00-00), nombre y número de mesas son obligatorios")
    _validar_lugar(db, body.lugar_id)
    hab = (body.habilitados or Habilitados()).model_dump()
    doc = {"_id": bd.siguiente_id(db, "puestos"), "eleccion": body.eleccion or modelo.leer_ajustes(db)["eleccion_vigente"],
           "divipole": None, "zona": body.codigo[:2], "codigo": body.codigo, "nombre": body.nombre.strip().upper(),
           "alias": body.alias or [], "alias_ambiguos": body.alias_ambiguos or [], "area": body.area or "rural",
           "lugar_id": body.lugar_id, "lat": body.lat, "lon": body.lon,
           "coord_fuente": "manual" if body.lat is not None else None, "coord_dudosa": False, "mesas": body.mesas,
           "habilitados": {**hab, "total": hab["mujeres"] + hab["hombres"]},
           "activo": body.activo if body.activo is not None else True, "fuente": "panel", "verificado": False,
           "editado": True, "creado_en": bd.ahora()}
    try:
        db.puestos.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "Ya hay un puesto con ese código en esa elección")
    bd.subir_catalogos_version(db)
    bd.auditar(db, quien, "crear_puesto", "puesto", doc["_id"], {"codigo": doc["codigo"], "eleccion": doc["eleccion"]})
    return _puesto(doc)


@r.patch("/puestos/{puesto_id}")
def editar_puesto(puesto_id: int, body: PuestoIn, db: Database = Depends(obtener_db),
                  quien: Quien = Depends(requiere("puestos.gestionar"))):
    if db.puestos.find_one({"_id": puesto_id}, {"_id": 1}) is None:
        raise HTTPException(404, "No existe")
    datos = body.model_dump(exclude_unset=True)
    if "lugar_id" in datos:
        _validar_lugar(db, datos["lugar_id"])
    if "nombre" in datos and datos["nombre"]:
        datos["nombre"] = datos["nombre"].strip().upper()
    if "codigo" in datos and datos["codigo"]:
        datos["zona"] = datos["codigo"][:2]
    if "habilitados" in datos and datos["habilitados"] is not None:
        h = datos["habilitados"]
        datos["habilitados"] = {**h, "total": h["mujeres"] + h["hombres"]}
    if "lat" in datos:
        datos["coord_fuente"] = "manual" if datos["lat"] is not None else None
        datos["coord_dudosa"] = False
    datos = {k: v for k, v in datos.items() if v is not None or k in ("lugar_id", "lat", "lon", "coord_fuente")}
    if datos:
        try:
            db.puestos.update_one({"_id": puesto_id}, {"$set": {**datos, "editado": True}})
        except DuplicateKeyError:
            raise HTTPException(409, "Ya hay un puesto con ese código en esa elección")
        bd.subir_catalogos_version(db)
        bd.auditar(db, quien, "editar_puesto", "puesto", puesto_id, {"campos": sorted(datos)})
    return _puesto(db.puestos.find_one({"_id": puesto_id}))


# ───────────────────────────── Plantilla de la planilla de campo ─────────────────────────────

COLUMNAS_PLANILLA = [
    "Cédula", "Repita la cédula", "Tipo de documento", "Nombre completo", "Celular", "Otro teléfono", "Sexo",
    "Fecha de nacimiento", "Edad", "Dirección", "Barrio o vereda", "Puesto de votación", "Mesa", "Autorización de datos",
    "Medio de la autorización", "Canales autorizados", "Mayor de 18", "Planillero (usuario)", "Fecha", "Observaciones",
]
FILAS_PLANTILLA = 500


def _lista(ws, col: str, valores: list[str] | str, error: bool = True) -> None:
    formula = valores if isinstance(valores, str) else '"' + ",".join(valores) + '"'
    dv = DataValidation(type="list", formula1=formula, allow_blank=True, showErrorMessage=error,
                        errorTitle="Valor no válido", error="Elija un valor de la lista")
    dv.add(f"{col}2:{col}{FILAS_PLANTILLA + 1}")
    ws.add_data_validation(dv)


def plantilla_planilla(db: Database) -> bytes:
    """La planilla de campo: hoja «Planilla» (encabezados en la fila 1 y listas desplegables), «Puestos» con el
    catálogo vigente y «Aviso» con el aviso de privacidad vigente para imprimir. Se puede volver a importar."""
    ajustes = modelo.leer_ajustes(db)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Planilla"
    ws.append(COLUMNAS_PLANILLA)
    for i, celda in enumerate(ws[1], 1):
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor="1F4E79")
        celda.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[celda.column_letter].width = 22 if i in (4, 10, 12, 20) else 15
    ws.freeze_panes = "A2"
    for col in ("A", "B", "E", "F"):  # la cédula y los teléfonos como texto: Excel no les quita ceros ni los redondea
        for fila in range(2, FILAS_PLANTILLA + 2):
            ws[f"{col}{fila}"].number_format = "@"
    for fila in range(2, FILAS_PLANTILLA + 2):
        ws[f"H{fila}"].number_format = ws[f"S{fila}"].number_format = "DD/MM/YYYY"
    puestos = bd.puestos_vigentes(db, ajustes["eleccion_vigente"])
    _lista(ws, "C", list(modelo.TIPOS_DOCUMENTO))
    _lista(ws, "G", list(modelo.SEXOS.values()))
    _lista(ws, "L", f"Puestos!$B$2:$B${max(2, len(puestos) + 1)}", error=False)
    _lista(ws, "N", [modelo.ESTADOS_AUTORIZACION[k] for k in ("si", "no")])
    _lista(ws, "O", [modelo.MEDIOS_AUTORIZACION[k] for k in modelo.MEDIOS_POR_ROL["planillero"]])
    # Varios canales se escriben separados por coma: la lista ayuda con uno y acepta más
    _lista(ws, "P", list(modelo.CANALES_AUTORIZACION.values()), error=False)
    _lista(ws, "Q", ["Sí", "No"])
    hp = wb.create_sheet("Puestos")
    hp.append(["Código", "Puesto de votación", "Mesas", "Zona"])
    for p in puestos:
        hp.append([p.get("codigo"), p.get("nombre"), p.get("mesas"), p.get("area")])
    hp.column_dimensions["B"].width = 44
    av = wb.create_sheet("Aviso")
    aviso = ajustes.get("aviso_privacidad") or {}
    for fila in (["Aviso de privacidad", f"Versión {aviso.get('version') or ''}"],
                 ["Responsable", aviso.get("responsable") or ""], ["Contacto", aviso.get("contacto") or ""],
                 ["Canal para ejercer sus derechos", aviso.get("canal_derechos") or ""], [],
                 [aviso.get("texto") or "El administrador debe completar el texto del aviso en Ajustes."]):
        av.append(fila)
    av.column_dimensions["A"].width = 40
    av.column_dimensions["B"].width = 80
    av["A6"].alignment = Alignment(wrap_text=True, vertical="top")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@r.get("/plantillas/planilla.xlsx")
def plantilla(db: Database = Depends(obtener_db), quien: Quien = Depends(requiere("plantillas"))):
    datos = plantilla_planilla(db)
    bd.auditar(db, quien, "descargar_plantilla")
    return StreamingResponse(iter([datos]),
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": 'attachment; filename="planilla-de-campo.xlsx"'})
