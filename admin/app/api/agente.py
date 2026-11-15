"""API del asistente del panel (docs/agente.md).

* GET /api/agente/estado — si el asistente está disponible para quien pregunta y por qué no (`requiere("cuenta")`:
  cualquier rol lo consulta para saber si mostrar el botón), y con qué proveedor del modelo empezaría una conversación
  nueva (`proveedor`: «mnemo», «anthropic» o None; ver `agente/proveedores.py`). Para el administrador y el
  coordinador trae además la conexión con Mnemo (`mnemo.conexion`, `mnemo_conexion.vista`; al coordinador, sin la
  cuenta personal de Mnemo del administrador ni la dirección sugerida); conectarla y desconectarla está en
  `api/agente_mnemo.py`. Y `dictado`: si esta instalación puede transcribir por Mnemo las preguntas por voz.
* GET /api/agente/conversaciones, GET y DELETE /api/agente/conversaciones/{cid} — las conversaciones propias: solo
  su dueño las ve o las borra (de otra persona es un 404, como si no existiera).
* POST /api/agente/mensajes y POST /api/agente/confirmaciones — un turno en flujo (NDJSON, `bucle.py`). Lo que impide
  el turno sale antes como JSON normal (503, 403, 404, 409, 429); entre ellos, 409 `proveedor` si la conversación es
  de un proveedor del modelo que ya no está.
* POST /api/agente/transcribir — una pregunta por voz: el cuerpo es el audio crudo que grabó el panel y la respuesta,
  su texto (`agente/dictado.py`, que se lo pide a la cuenta de Mnemo conectada). No guarda nada.

El módulo del bucle (y con él el catálogo de herramientas) se importa al usarlo: `crear_app` no depende de que cada
herramienta cargue, y una herramienta rota deja sin asistente, no sin panel."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, StrictBool, field_validator
from pymongo.database import Database

from ..acceso import Quien, requiere
from ..agente import conversaciones as conv_db
from ..agente import politica, proveedores
from ..seguridad import obtener_db

log = logging.getLogger("panel")
r = APIRouter(prefix="/api", tags=["agente"])

ID_MAX = 10**12  # los ids de conversación son enteros pequeños; más grande ni siquiera cabe en MongoDB
NO_EXISTE = {"codigo": "no_existe", "mensaje": "No existe esa conversación."}


class MensajeIn(BaseModel):
    conversacion: int | None = Field(None, ge=1, le=ID_MAX)
    texto: str = Field(..., min_length=1, max_length=4000)
    # La vista, la ficha abierta, los filtros y el mapa: una pista que se limpia y se acota en `sistema.py`
    contexto: dict[str, Any] | None = None

    @field_validator("texto")
    @classmethod
    def _con_texto(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("el mensaje está vacío")
        return v


class DecisionIn(BaseModel):
    id: str = Field(..., min_length=1, max_length=100)
    aprobar: StrictBool


class ConfirmacionIn(BaseModel):
    conversacion: int = Field(..., ge=1, le=ID_MAX)
    decisiones: list[DecisionIn] = Field(..., min_length=1, max_length=20)


def _exigir_rol(quien: Quien, agente: dict) -> None:
    if not quien.puede("agente.usar") or quien.rol not in agente["roles"]:
        raise HTTPException(403, {"codigo": "agente_apagado", "mensaje": "El asistente no está habilitado para su rol."})


SIN_CONEXION = {"estado": "sin_conectar", "motivo": None, "url": None, "cuenta": None, "alcances": [],
                "modelo": False, "ofrece_modelo": None, "desde": None}


def _conexion(db: Database, cfg: Any) -> dict:
    """La conexión con Mnemo (`mnemo_conexion.vista`, con la dirección sugerida). Si no se puede leer, sin conectar:
    el estado nunca falla por Mnemo."""
    try:
        from ..agente import mnemo_conexion
        return mnemo_conexion.vista(db, cfg)
    except Exception as e:  # noqa: BLE001
        log.warning("Asistente: no se pudo leer la conexión con Mnemo (%s)", type(e).__name__)
        return {**SIN_CONEXION, "url_sugerida": getattr(cfg, "mnemo_url", "") or None}


def _mnemo_activo(quien: Quien, agente: dict, cfg: Any, conexion: dict) -> bool:
    """¿Esta persona usa las herramientas de Mnemo ahora? Hay una conexión «conectada» y su rol las tiene."""
    if conexion.get("estado") != "conectada":
        return False
    try:
        from ..agente.herramientas import mnemo
        return bool(mnemo.disponible_para(quien, agente, cfg))
    except Exception as e:  # noqa: BLE001 - el estado nunca falla por Mnemo
        log.warning("Asistente: no se pudo saber si Mnemo está disponible (%s)", type(e).__name__)
        return False


def _dictado(app: Any, conexion: dict) -> bool:
    """¿Esta instalación puede transcribir por Mnemo las preguntas por voz? (`dictado.puede`). Sin eso el panel usa el
    reconocimiento de voz del navegador. El estado nunca falla por esto."""
    try:
        from ..agente import dictado
        return dictado.puede(app, conexion)
    except Exception as e:  # noqa: BLE001
        log.warning("Asistente: no se pudo saber si se puede transcribir por Mnemo (%s)", type(e).__name__)
        return False


def _etiquetas(conv: dict) -> dict[str, str]:
    """La etiqueta (en gerundio) de cada herramienta de la conversación, para pintar el historial."""
    try:
        from ..agente import herramientas
        from ..agente.herramientas import mnemo
        out = {n: h.etiqueta for n, h in herramientas.por_nombre().items()}
        defs = conv_db.de_json(conv.get("mnemo"), [])
        if defs:
            out.update({h.nombre: h.etiqueta for h in mnemo.desde_definiciones(defs)})
        return out
    except Exception as e:  # noqa: BLE001 - sin etiquetas se muestra el nombre
        log.warning("Asistente: no se pudieron leer las etiquetas de las herramientas (%s)", type(e).__name__)
        return {}


@r.get("/agente/estado")
def estado(request: Request, db: Database = Depends(obtener_db), quien: Quien = Depends(requiere("cuenta"))):
    """`proveedor`: con qué proveedor del modelo empezaría una conversación nueva («mnemo» si hay una conexión con
    `mnemo:model`, si no «anthropic» si hay `ANTHROPIC_API_KEY`, si no None, y entonces `motivo` es `sin_configurar`);
    `configurado` es `proveedor` no None. `mnemo`: `{"activo": bool (esta persona usa las herramientas de Mnemo),
    "origen": scheme://host de Mnemo | None}` para todos y, para el administrador y el coordinador (que la ve en solo
    lectura en Ajustes), `"conexion"`: `mnemo_conexion.vista(db, cfg)` (`estado`, `motivo`, `url`, `cuenta`,
    `alcances`, `modelo`, `ofrece_modelo`, `desde` y `url_sugerida`). Al coordinador le llegan `cuenta` y
    `url_sugerida` en None: la cuenta es la personal del administrador (nombre y correo) y la dirección sugerida solo
    le sirve a quien conecta. `dictado`: True si las preguntas por voz se pueden transcribir por Mnemo (hay una
    conexión con `mnemo:model` y Mnemo no dijo hace poco que no transcribe); con False el panel usa el reconocimiento
    de voz del navegador."""
    cfg = request.app.state.cfg
    ajustes, agente = politica.leer(db)
    sesion = (request.scope.get("state") or {}).get("sesion")
    proveedor = proveedores.clave_para_nueva(cfg, db)
    motivo = politica.motivo(quien, cfg, agente, sesion, db)
    conexion = _conexion(db, cfg)
    activo = _mnemo_activo(quien, agente, cfg, conexion)
    mnemo: dict[str, Any] = {"activo": activo, "origen": politica.origen_mnemo(conexion.get("url")) if activo else None}
    if quien.administra:
        mnemo["conexion"] = conexion if quien.es_admin else {**conexion, "cuenta": None, "url_sugerida": None}
    return {"disponible": motivo is None, "motivo": motivo, "configurado": proveedor is not None,
            "proveedor": proveedor, "es_admin": quien.es_admin, "escritura": agente["escritura"],
            "limite": {"usados": conv_db.uso_de(db, quien.uid), "maximo": politica.mensajes_diarios(ajustes, quien.rol)},
            "mnemo": mnemo, "dictado": _dictado(request.app, conexion),
            "sugerencias": politica.sugerencias(quien.rol) if motivo is None else []}


@r.get("/agente/conversaciones")
def conversaciones(db: Database = Depends(obtener_db), quien: Quien = Depends(requiere("agente.usar"))):
    _exigir_rol(quien, politica.leer(db)[1])
    return {"conversaciones": conv_db.listar(db, quien.uid)}


@r.get("/agente/conversaciones/{cid}")
def conversacion(cid: int = Path(..., ge=1, le=ID_MAX), db: Database = Depends(obtener_db),
                 quien: Quien = Depends(requiere("agente.usar"))):
    _exigir_rol(quien, politica.leer(db)[1])
    conv = conv_db.de_usuario(db, cid, quien.uid)
    if conv is None:
        raise HTTPException(404, dict(NO_EXISTE))
    return conv_db.para_interfaz(conv, conv_db.mensajes_de(db, cid), _etiquetas(conv))


@r.delete("/agente/conversaciones/{cid}")
def borrar_conversacion(request: Request, cid: int = Path(..., ge=1, le=ID_MAX), db: Database = Depends(obtener_db),
                        quien: Quien = Depends(requiere("agente.usar"))):
    """Borra la conversación y sus mensajes (también con el rol apagado: los datos son de su dueño). No mientras un
    turno la está usando: ese turno seguiría guardando en ella."""
    conv = conv_db.de_usuario(db, cid, quien.uid)
    if conv is None:
        raise HTTPException(404, dict(NO_EXISTE))
    ocupacion = getattr(request.app.state, "agente_ocupacion", None)
    if conv_db.ocupada(conv) or (ocupacion is not None and ocupacion.ocupada(cid)):
        raise HTTPException(409, {"codigo": "ocupada", "mensaje": "El asistente todavía está respondiendo en esa "
                                                                  "conversación. Espere a que termine."})
    if not conv_db.borrar(db, cid, quien.uid):
        raise HTTPException(404, dict(NO_EXISTE))
    return {"ok": True}


@r.post("/agente/mensajes")
async def mensajes(cuerpo: MensajeIn, request: Request, quien: Quien = Depends(requiere("agente.usar"))):
    from ..agente import bucle
    return await bucle.abrir_mensaje(request, quien, cuerpo.conversacion, cuerpo.texto, cuerpo.contexto)


@r.post("/agente/confirmaciones")
async def confirmaciones(cuerpo: ConfirmacionIn, request: Request, quien: Quien = Depends(requiere("agente.usar"))):
    from ..agente import bucle
    return await bucle.abrir_confirmacion(request, quien, cuerpo.conversacion,
                                          {d.id: d.aprobar for d in cuerpo.decisiones})


@r.post("/agente/transcribir")
async def transcribir(request: Request, quien: Quien = Depends(requiere("agente.usar"))):
    """Una pregunta por voz. El cuerpo es el audio crudo (`Content-Type`: `audio/webm`, `audio/ogg`, `audio/mp4`,
    `audio/mpeg` o `audio/wav`; hasta 2 MB) y la respuesta, `{"texto": lo transcrito ("" si no se oyó nada), "via":
    "mnemo"}`. Con la sesión y el permiso del asistente (503 sin proveedor del modelo, 403 con el rol apagado), con
    mensajes del día por gastar (429 `volumen`), una a la vez por persona (429 `frecuencia`), como mucho 20 por minuto
    por persona (429 `frecuencia`), como mucho el doble de sus mensajes del día (429 `volumen`) y dos llamadas a Mnemo
    a la vez en todo el panel (Mnemo comparte sus cupos con el modelo del asistente: la tercera espera unos segundos y
    después, 429 `frecuencia`). Errores, todos `{codigo, mensaje}`: 415 `tipo`, 413 `grande`, 400 `cortada` (la subida
    se cortó, o la persona se fue mientras se transcribía: se deja de esperar a Mnemo) o `lenta` (la grabación no
    terminó de llegar a tiempo), 422 `vacio` (sin cuerpo) o `audio` (Mnemo no pudo leerlo), 409
    `sin_transcriptor` (Mnemo sin conectar, la conexión sin `mnemo:model`, o Mnemo sin un modelo que transcriba: el
    panel pasa al reconocimiento del navegador), 402 `mnemo_creditos` y 502. No guarda ni registra el audio ni el
    texto."""
    from ..agente import dictado
    app = request.app
    db, cfg = app.state.db, app.state.cfg
    ajustes, agente = await run_in_threadpool(politica.leer, db)
    await run_in_threadpool(politica.exigir, quien, cfg, agente, db)
    mime = dictado.tipo_de(request.headers.get("content-type"))
    if mime is None:
        raise dictado.ErrorDictado(415, "tipo", dictado.MENSAJE_TIPO)
    maximo = politica.mensajes_diarios(ajustes, quien.rol)
    await run_in_threadpool(dictado.exigir_mensajes, db, quien.uid, maximo)
    # El turno de la persona abarca todo (un reintento rechazado no gasta frecuencia ni tope diario); el cupo del
    # proceso, solo la llamada a Mnemo; y si la persona se va mientras tanto, se deja de esperar
    with dictado.turno(db.name, quien.uid):
        dictado.frecuencia(db.name, quien.uid)
        dictado.diarias(db.name, quien.uid, maximo * dictado.DIARIAS_POR_MENSAJE)
        audio = await dictado.leer_audio(request)
        texto = await dictado.mientras_siga(request, dictado.transcribir_con_cupo(app, audio, mime))
    return {"texto": texto, "via": "mnemo"}
