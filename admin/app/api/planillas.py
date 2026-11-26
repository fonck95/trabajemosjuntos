"""La bandeja de planillas físicas por foto (`app/planillas.py`; docs/agente.md, «Planillas físicas por foto»). La usan
la vista Importar y exportar → Planillas por foto y las herramientas del asistente (por `ApiInterna`, con la sesión de
quien conversa): las mismas rutas, los mismos permisos. Cada foto, sea una planilla o cualquier otra imagen, se lee
igual: el panel la describe y, si lista personas, transcribe sus filas (una foto sin filas queda «leida» con su
descripción).

Todas exigen `importar`: solo el administrador y los coordinadores. Planilleros y consultores reciben 403 `permiso`
en cada una, antes de leer el cuerpo y diga lo que diga `agente_planillas.roles` (el planillero que llenó el papel queda
como «capturado por» de lo cargado).

* POST /api/planillas/fotos — sube una foto: el cuerpo es la imagen cruda (`Content-Type: image/jpeg` o `image/png`,
  hasta 1,5 MB), `?nota=&formato=` (planilla_campo | asistencia | otro, siempre: el ajuste
  `agente_planillas.otros_formatos` se retiró; el formato es solo una pista para el lector). El rol en
  `agente_planillas.roles`, un modelo
  conectado y un compromiso de confidencialidad vigente que deje fotografiar planillas (409 `compromiso_fotos`): todo
  eso se revisa antes de leer el cuerpo. Responde 201 `{id, estado: "leyendo", bytes, ancho, alto, expira}` y la
  lectura sigue de fondo; la misma foto de la misma persona, 200 con la que ya estaba (si había fallado, se vuelve a
  leer); una foto ya cargada, 409 `ya_cargada`.
* GET /api/planillas — la bandeja `{planillas: [...]}` (todas), sin datos de personas (de lo leído, solo conteos,
  `aviso`, `con_descripcion` y `datos_personales`).
* GET /api/planillas/{pid} — una planilla con su descripción (`descripcion`, `datos_personales`, `aviso`) y sus filas,
  con los valores completos (`?enmascarada=1` los pide enmascarados, como los recibe el modelo: la descripción sin
  números de 5 o más dígitos ni correos enteros).
* GET /api/planillas/{pid}/foto — la foto limpia, con su tipo real, `nosniff` y `no-store`.
* PATCH /api/planillas/{pid} — corrige celdas `{filas: [{n, campo, valor}], descartar: [n], restaurar: [n]}` y
  responde la planilla completa.
* POST /api/planillas/{pid}/leer — vuelve a leer la foto (como mucho 2 lecturas por foto) `{desde_fila?}` (solo en
  una lectura incompleta): 202 `{id, estado: "leyendo"}`.
* DELETE /api/planillas/{pid} — la borra entera.
* POST /api/planillas/{pid}/simular — la vista previa fiel de cargar `{filas?, capturado_por?}`, sin escribir: `{id,
  filas: [{n, estado, persona_id, llenaria, distintos, motivo}], conteo}`. Una foto leída sin filas: 422 `sin_filas`.
* POST /api/planillas/{pid}/cargar — idempotente con `Idempotency-Key`: carga `{filas?, folio?, capturado_por?}` con
  el importador real y responde `{importacion_id, resumen, filas: {n: {persona_id, estado, motivo}}}`. Una foto leída
  sin filas: 422 `sin_filas`.

Las rutas leen su cuerpo después de comprobar el permiso. Los errores son `{codigo, mensaje}`
(`planillas.ErrorPlanilla`)."""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError

from .. import acceso
from .. import planillas as pl
from ..acceso import Quien, requiere
from ..agente import politica, proveedores
from ..agente.lector_planillas import COLUMNAS, MAX_N

r = APIRouter(prefix="/api", tags=["planillas"])
# Las planillas por foto son una forma de importar: solo A y K, en cada ruta (sin depender de los ajustes guardados)
PLANILLAS = requiere("importar")

Fila = StrictInt


class CeldaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    n: StrictInt = Field(..., ge=1, le=MAX_N)
    campo: Literal[COLUMNAS]  # type: ignore[valid-type]
    valor: Annotated[str, Field(max_length=1000)] | StrictInt | None = None


class CorreccionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filas: list[CeldaIn] = Field(default_factory=list, max_length=500)
    descartar: list[Fila] = Field(default_factory=list, max_length=500)
    restaurar: list[Fila] = Field(default_factory=list, max_length=500)


class ReleerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    desde_fila: StrictInt | None = Field(None, ge=1, le=MAX_N)


class SimularIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filas: list[Fila] | None = Field(None, min_length=1, max_length=500)
    capturado_por: StrictInt | None = None


class CargarIn(SimularIn):
    folio: str | None = Field(None, max_length=pl.FOLIO_MAX * 2)


async def _cuerpo(request: Request, modelo: type[BaseModel]) -> BaseModel:
    """El cuerpo JSON validado con `modelo` (vacío vale `{}`), leído en la ruta: después de que `requiere` comprobó el
    permiso, así a quien no lo tiene se le responde sin leerlo."""
    crudo = await request.body()
    try:
        return modelo.model_validate_json(crudo or b"{}")
    except ValidationError as e:
        errores = [f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()]
        raise HTTPException(422, "; ".join(errores) or "Datos no válidos") from None


async def _exigir_lectura(request: Request, quien: Quien) -> dict:
    """Subir o releer manda la foto al modelo: el rol en `agente_planillas.roles` (403 `planillas_apagado`; solo A y K
    pueden estar) y un proveedor del modelo conectado (503 `sin_configurar`). Devuelve los ajustes validados."""
    db, cfg = request.app.state.db, request.app.state.cfg
    ajustes, _ = await run_in_threadpool(politica.leer, db)
    if not politica.usa_planillas(quien, ajustes):
        raise pl.ErrorPlanilla(403, "planillas_apagado")
    if await run_in_threadpool(proveedores.clave_para_nueva, cfg, db) is None:
        raise pl.ErrorPlanilla(503, "sin_configurar")
    return ajustes


async def _capturado_por(request: Request, uid: int | None) -> None:
    if uid is None:
        return
    p = await run_in_threadpool(request.app.state.db.usuarios.find_one, {"_id": uid, "rol": "planillero"}, {"_id": 1})
    if p is None:
        raise pl.ErrorPlanilla(422, "planillero")


@r.post("/planillas/fotos", status_code=201)
async def subir(request: Request, nota: str | None = Query(None, max_length=2000),
                formato: str = Query("planilla_campo", max_length=40),
                quien: Quien = Depends(PLANILLAS)):
    """Sube una foto (una planilla física o cualquier otra imagen; ver el docstring del módulo). Errores, todos
    `{codigo, mensaje}`: 403 `permiso` o `planillas_apagado`, 503 `sin_configurar`, 409 `compromiso_fotos`, 415 `tipo`,
    413 `pesada`, 422 `formato` (uno que no es planilla_campo, asistencia ni otro), `imagen`, `dimensiones` o `vacia`,
    400 `cortada` o `lenta`, 429 `frecuencia`, 409 `pendientes` o `ya_cargada` (con `importacion_id`)."""
    app = request.app
    db, cfg = app.state.db, app.state.cfg
    ajustes = await _exigir_lectura(request, quien)
    pl.exigir_compromiso(ajustes)
    media = pl.tipo_de(request.headers.get("content-type"))
    if media not in pl.TIPOS:
        raise pl.ErrorPlanilla(415, "tipo")
    await run_in_threadpool(pl.exigir_subida, db, quien, formato, request.headers.get("content-length"))
    crudo = await pl.leer_cuerpo(request)
    imagen = await run_in_threadpool(pl.validar_imagen, crudo, media)
    respuesta, nueva = await run_in_threadpool(pl.guardar_subida, db, cfg, quien, imagen, nota=pl.nota_de(nota),
                                               formato=formato, horas=ajustes["agente_planillas"]["retencion_horas"])
    if nueva:
        pl.programar(app, respuesta["id"])
        return respuesta
    if respuesta["estado"] == "fallida":  # la misma foto otra vez: se vuelve a leer si todavía se puede
        doc = await run_in_threadpool(db.planillas.find_one, {"_id": respuesta["id"]})
        if doc is not None and pl._puede_releer(doc):
            try:
                doc = await run_in_threadpool(pl.preparar_relectura, db, cfg, doc, None)
                pl.programar(app, doc["_id"])
                respuesta["estado"] = doc["estado"]
            except pl.ErrorPlanilla:
                pass
    return JSONResponse({**respuesta, "repetida": True}, status_code=200)


@r.get("/planillas")
async def bandeja(request: Request, estado: str | None = Query(None, max_length=20),
                  quien: Quien = Depends(PLANILLAS)):
    """La bandeja: `{planillas: [{id, estado, subida_por: {uid, usuario, nombre}, ts, expira, formato, tipo_formato,
    filas, dudosas, pendientes, cargadas, incompleta, importacion_id, nota, error, ancho, alto, bytes, lecturas,
    con_foto, progreso, aviso, con_descripcion, datos_personales, filas_visibles}]}` (las 100 más nuevas; `?estado=`
    filtra). El error de un rechazo que ya no existe sale con el mensaje de ahora (`planillas.error_de`)."""
    return {"planillas": await run_in_threadpool(pl.bandeja, request.app.state.db, quien, estado)}


@r.get("/planillas/{pid}")
async def ver(pid: str, request: Request, enmascarada: bool = False,
              quien: Quien = Depends(PLANILLAS)):
    """Una planilla con su descripción, su encabezado y sus filas (`planillas.detalle`): lo de la bandeja más
    `descripcion` (str o None), `datos_personales`, `aviso`, `media_type`, `sha256`, `columnas`, `puede_releer`,
    `importaciones`, `encabezado`, `filas_visibles`, `ultima_fila` y `filas`. Completa para A y K; con
    `?enmascarada=1`, como la recibe el modelo."""
    db, cfg = request.app.state.db, request.app.state.cfg
    doc = await run_in_threadpool(pl.buscar, db, pid, quien)
    return await run_in_threadpool(lambda: pl.detalle(cfg, doc, completa=quien.administra and not enmascarada))


@r.get("/planillas/{pid}/foto")
async def foto(pid: str, request: Request, quien: Quien = Depends(PLANILLAS)):
    """La foto limpia (sin metadatos), para verla al lado de la grilla. 404 `sin_foto` si ya se borró."""
    db, cfg = request.app.state.db, request.app.state.cfg
    doc = await run_in_threadpool(pl.buscar, db, pid, quien)
    datos = await run_in_threadpool(pl.foto_de, cfg, doc)
    if datos is None:
        raise pl.ErrorPlanilla(404, "sin_foto")
    extension = "png" if doc.get("media_type") == "image/png" else "jpg"
    return Response(datos, media_type=doc.get("media_type"), headers={
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        "Content-Disposition": f'attachment; filename="planilla.{extension}"',
        "Cross-Origin-Resource-Policy": "same-origin"})


@r.patch("/planillas/{pid}")
async def corregir(pid: str, request: Request, quien: Quien = Depends(PLANILLAS)):
    """Corrige celdas y descarta o recupera filas; responde la planilla completa. 409 `leyendo`, `cargando`,
    `no_leida` o `cambiada`; 422 `fila`, `campo` o `suprimida`."""
    cuerpo = await _cuerpo(request, CorreccionIn)
    db, cfg = request.app.state.db, request.app.state.cfg
    doc = await run_in_threadpool(pl.buscar, db, pid, quien)
    celdas = [c.model_dump() for c in cuerpo.filas]
    doc = await run_in_threadpool(pl.corregir, db, cfg, quien, doc, celdas, cuerpo.descartar, cuerpo.restaurar)
    return await run_in_threadpool(lambda: pl.detalle(cfg, doc, completa=True))


@r.post("/planillas/{pid}/leer", status_code=202)
async def releer(pid: str, request: Request, quien: Quien = Depends(PLANILLAS)):
    """Vuelve a leer la foto de fondo. 409 `leyendo`, `cargando`, `sin_foto` o `max_lecturas`; 422 `desde_fila`."""
    cuerpo = await _cuerpo(request, ReleerIn)
    db, cfg = request.app.state.db, request.app.state.cfg
    doc = await run_in_threadpool(pl.buscar, db, pid, quien)
    await _exigir_lectura(request, quien)
    doc = await run_in_threadpool(pl.preparar_relectura, db, cfg, doc, cuerpo.desde_fila)
    pl.programar(request.app, doc["_id"], desde_fila=cuerpo.desde_fila)
    return {"id": doc["_id"], "estado": doc["estado"]}


@r.delete("/planillas/{pid}")
async def borrar(pid: str, request: Request, quien: Quien = Depends(PLANILLAS)):
    """Borra la planilla entera (la foto y lo leído). 409 `cargando`."""
    db = request.app.state.db
    doc = await run_in_threadpool(pl.buscar, db, pid, quien)
    await run_in_threadpool(pl.borrar, db, quien, doc)
    return {"borrada": True}


@r.post("/planillas/{pid}/simular")
async def simular(pid: str, request: Request, quien: Quien = Depends(PLANILLAS)):
    """La vista previa de cargar: por fila `{n, estado, persona_id, llenaria, distintos: [{campo, base, planilla,
    queda}], motivo}`. Estados: nueva, nueva_sin_autorizacion, completaria, igual, revocaria, conflicto_cedula,
    revision, no_autorizo, no_se_carga, sin_nombre, ya_cargada, otra_eleccion (y descartada, si se pide). No escribe
    nada; anota las lecturas de las fichas encontradas. 409 `leyendo`, `cargando` o `no_leida`; 422 `sin_filas` (una
    foto leída sin ninguna fila) o `fila`."""
    cuerpo = await _cuerpo(request, SimularIn)
    db, cfg = request.app.state.db, request.app.state.cfg
    doc = await run_in_threadpool(pl.buscar, db, pid, quien)
    await _capturado_por(request, cuerpo.capturado_por)
    return await run_in_threadpool(pl.simular, db, cfg, quien, doc, cuerpo.filas, cuerpo.capturado_por)


@r.post("/planillas/{pid}/cargar")
async def cargar(pid: str, request: Request, quien: Quien = Depends(PLANILLAS)):
    """Carga las filas con el importador real (ver `planillas.cargar`). Idempotente con `Idempotency-Key`. 409
    `importando` (otra importación o unión en curso), `cargando` o `no_leida`; 422 `sin_filas` (ninguna fila que
    cargar, también una foto leída sin filas), `fila` o `planillero`."""
    cuerpo = await _cuerpo(request, CargarIn)
    db, cfg = request.app.state.db, request.app.state.cfg
    doc = await run_in_threadpool(pl.buscar, db, pid, quien)
    await _capturado_por(request, cuerpo.capturado_por)
    previa = await run_in_threadpool(acceso.idempotencia_previa, db, quien, request)
    if previa is not None:
        return previa
    folio = pl.lector.una_linea(cuerpo.folio, pl.FOLIO_MAX)[0]
    res = await run_in_threadpool(pl.cargar, db, cfg, quien, doc, cuerpo.filas, folio, cuerpo.capturado_por)
    await run_in_threadpool(acceso.idempotencia_guardar, db, quien, request, 200, res)
    return res

