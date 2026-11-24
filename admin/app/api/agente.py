"""API del asistente del panel (docs/agente.md).

* GET /api/agente/estado — si el asistente está disponible para quien pregunta y por qué no (`requiere("cuenta")`:
  cualquier rol lo consulta para saber si mostrar el botón), y con qué proveedor del modelo empezaría una conversación
  nueva (`proveedor`: «mnemo», «anthropic» o None; ver `agente/proveedores.py`). Para el administrador y el
  coordinador trae además la conexión con Mnemo (`mnemo.conexion`, `mnemo_conexion.vista`; al coordinador, sin la
  cuenta personal de Mnemo del administrador ni la dirección sugerida); conectarla y desconectarla está en
  `api/agente_mnemo.py`. Y `dictado`: si esta instalación puede transcribir por Mnemo las preguntas por voz; `voz`:
  si esta persona puede hacer sonar la voz clonada de Mnemo (`agente/voz.py`); y `adelanto`: si sus preguntas reciben
  la respuesta inmediata (`agente/adelanto.py`).
* GET /api/agente/conversaciones, GET y DELETE /api/agente/conversaciones/{cid} — las conversaciones propias: solo
  su dueño las ve o las borra (de otra persona es un 404, como si no existiera).
* POST /api/agente/mensajes y POST /api/agente/confirmaciones — un turno en flujo (NDJSON, `bucle.py`). Lo que impide
  el turno sale antes como JSON normal (503, 403, 404, 409, 422, 429); entre ellos, 409 `proveedor` si la conversación
  es de un proveedor del modelo que ya no está. Un mensaje puede traer fotos de planillas físicas (`adjuntos`: ids de
  la bandeja de planillas de quien escribe, como mucho 4; con ellas el texto puede ir vacío; solo A y K): 403
  `planillas_apagado` si su rol no sube fotos, 422 `fotos` si alguna no es suya o ya no está.
* POST /api/agente/transcribir — una pregunta por voz: el cuerpo es el audio crudo que grabó el panel y la respuesta,
  su texto (`agente/dictado.py`, que se lo pide a la cuenta de Mnemo conectada). No guarda nada.
* GET /api/agente/voces — las voces clonadas de la cuenta de Mnemo conectada que se pueden usar desde el panel (solo
  el administrador, que la elige en Ajustes → Asistente) y POST /api/agente/voz — una frase dicha con la voz clonada,
  en flujo (NDJSON): la narración del plan guardado, una frase firmada de una respuesta del asistente o la prueba de
  Ajustes (`agente/voz.py`). No guarda nada.

El módulo del bucle (y con él el catálogo de herramientas) se importa al usarlo: `crear_app` no depende de que cada
herramienta cargue, y una herramienta rota deja sin asistente, no sin panel."""
from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator, model_validator
from pymongo.database import Database

from .. import planillas as bandeja
from .. import recorrido as rec
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
    # Vacío solo si el mensaje trae fotos (`adjuntos`): el modelo recibe entonces un texto fijo, nunca uno vacío
    texto: str = Field("", max_length=4000)
    # La vista, la ficha abierta, los filtros y el mapa: una pista que se limpia y se acota en `sistema.py`
    contexto: dict[str, Any] | None = None
    # Fotos de planillas físicas: ids de la bandeja de quien escribe (`POST /api/planillas/fotos`), como mucho 4; el
    # bucle comprueba que sean suyas (`bucle.abrir_mensaje`)
    adjuntos: list[Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]] = Field(default_factory=list,
                                                                          max_length=bandeja.MAX_POR_MENSAJE)

    @field_validator("adjuntos")
    @classmethod
    def _sin_repetir(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(v))

    @model_validator(mode="after")
    def _con_texto(self):
        if not self.texto.strip() and not self.adjuntos:
            raise ValueError("el mensaje está vacío")
        return self


class DecisionIn(BaseModel):
    id: str = Field(..., min_length=1, max_length=100)
    aprobar: StrictBool


class ConfirmacionIn(BaseModel):
    conversacion: int = Field(..., ge=1, le=ID_MAX)
    decisiones: list[DecisionIn] = Field(..., min_length=1, max_length=20)
    # La respuesta que sigue se dice con la voz clonada (como `contexto.voz` de un mensaje)
    voz: StrictBool | None = None


# Lo que se puede pedir a la voz clonada: una referencia, nunca un texto libre (salvo la frase firmada de una respuesta,
# `agente/voz.py`). Los rangos de la narración son los del recorrido (como `api/pantalla.ProgresoEntrada`)


class VozIn(BaseModel):
    """Exactamente uno de: `{rid, n, frase}` o `{rid, cierre: true}` (la narración del plan guardado de la persona),
    `{conversacion, texto, firma}` (una frase de una respuesta del asistente, con la firma del evento `frase`) o
    `{prueba: true}` (la frase de prueba de Ajustes, solo el administrador)."""
    model_config = ConfigDict(extra="forbid")
    rid: str | None = Field(None, pattern=r"^[0-9a-f]{12}$")
    n: StrictInt | None = Field(None, ge=1, le=rec.MAX_ESCENAS)
    frase: StrictInt | None = Field(None, ge=0, le=rec.MAX_FRASES - 1)
    cierre: StrictBool | None = None
    conversacion: StrictInt | None = Field(None, ge=1, le=ID_MAX)
    texto: str | None = Field(None, min_length=1, max_length=400)
    firma: str | None = Field(None, pattern=r"^[A-Za-z0-9_-]{43}$")
    prueba: StrictBool | None = None

    @model_validator(mode="after")
    def _uno(self):
        dado = {k for k in type(self).model_fields if getattr(self, k) is not None}
        if dado not in ({"rid", "n", "frase"}, {"rid", "cierre"}, {"conversacion", "texto", "firma"}, {"prueba"}):
            raise ValueError("Pida una frase del plan ({rid, n, frase}), su cierre ({rid, cierre: true}), una frase de "
                             "una respuesta ({conversacion, texto, firma}) o la prueba ({prueba: true})")
        if self.cierre is False or self.prueba is False:
            raise ValueError("cierre y prueba solo pueden ser true")
        return self


def _exigir_rol(quien: Quien, agente: dict) -> None:
    if not quien.puede("agente.usar") or quien.rol not in agente["roles"]:
        raise HTTPException(403, {"codigo": "agente_apagado", "mensaje": "El asistente no está habilitado para su rol."})


SIN_CONEXION = {"estado": "sin_conectar", "motivo": None, "url": None, "cuenta": None, "alcances": [],
                "modelo": False, "ofrece_modelo": None, "voz": False, "ofrece_voz": None, "desde": None}
SIN_VOZ = {"disponible": False, "nombre": None, "respuestas": False, "automatica": False}


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


def _voz(app: Any, db: Database, quien: Quien, ajustes: dict, conexion: dict) -> dict:
    """¿Esta persona puede hacer sonar la voz clonada de Mnemo? (`voz.estado_de`). Sin eso el panel narra y lee con la
    voz del navegador. El estado nunca falla por esto."""
    try:
        from ..agente import voz
        return voz.estado_de(app, db, quien, ajustes, conexion)
    except Exception as e:  # noqa: BLE001
        log.warning("Asistente: no se pudo saber si hay voz clonada (%s)", type(e).__name__)
        return dict(SIN_VOZ)


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
    `alcances`, `modelo`, `ofrece_modelo`, `voz`, `ofrece_voz`, `desde` y `url_sugerida`). Al coordinador le llegan
    `cuenta` y `url_sugerida` en None: la cuenta es la personal del administrador (nombre y correo) y la dirección
    sugerida solo le sirve a quien conecta. `dictado`: True si las preguntas por voz se pueden transcribir por Mnemo
    (hay una conexión con `mnemo:model` y Mnemo no dijo hace poco que no transcribe); con False el panel usa el
    reconocimiento de voz del navegador. `voz`: `{"disponible": bool (esta persona puede hacer sonar la voz clonada:
    la elegida en Ajustes o, sin una elegida, la que Mnemo ofrece a las apps), "nombre": el de la voz | None,
    "respuestas": bool (la voz lee las respuestas del asistente), "automatica": bool (narra también la presentación
    automática)}`; sin ella, la voz del navegador. `adelanto`:
    True si cada pregunta de esta persona recibe la respuesta inmediata mientras se prepara la completa (el asistente
    está disponible para ella y `agente_adelanto` está encendido en Ajustes). `adjuntos`: si puede adjuntar fotos de
    planillas físicas al chat, los topes con que el navegador las prepara (`planillas.estado_adjuntos`:
    `{max_por_mensaje: 4, lado_max: 2000 con Mnemo o 2576 en modo directo, calidad: 0.8, max_bytes: 1500000}`); None si
    el asistente no está disponible para ella, no es A ni K (`importar`), su rol no está en `agente_planillas.roles`, el
    compromiso de confidencialidad vigente no deja fotografiar planillas (`politica.fotos_permitidas`) o no hay
    modelo."""
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
    # Las fotos de planillas: solo si el asistente está disponible para esta persona, es A o K con su rol en
    # `agente_planillas.roles` (nunca P ni C), el compromiso vigente deja fotografiarlas y hay modelo; el lado mayor
    # depende del proveedor (Mnemo lee hasta 2000 px)
    adjuntos = (bandeja.estado_adjuntos(proveedor) if motivo is None and quien.puede("importar")
                and politica.usa_planillas(quien, ajustes) and politica.fotos_permitidas(ajustes) else None)
    return {"disponible": motivo is None, "motivo": motivo, "configurado": proveedor is not None,
            "proveedor": proveedor, "es_admin": quien.es_admin, "escritura": agente["escritura"],
            "limite": {"usados": conv_db.uso_de(db, quien.uid), "maximo": politica.mensajes_diarios(ajustes, quien.rol)},
            "mnemo": mnemo, "dictado": _dictado(request.app, conexion),
            "voz": _voz(request.app, db, quien, ajustes, conexion),
            "adelanto": motivo is None and ajustes["agente_adelanto"], "adjuntos": adjuntos,
            "sugerencias": (politica.sugerencias(quien.rol, ajustes, planillas=quien.puede("importar")
                                                 and politica.usa_planillas(quien, ajustes))
                            if motivo is None else [])}


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
    return await bucle.abrir_mensaje(request, quien, cuerpo.conversacion, cuerpo.texto, cuerpo.contexto,
                                     adjuntos=cuerpo.adjuntos)


@r.post("/agente/confirmaciones")
async def confirmaciones(cuerpo: ConfirmacionIn, request: Request, quien: Quien = Depends(requiere("agente.usar"))):
    from ..agente import bucle
    return await bucle.abrir_confirmacion(request, quien, cuerpo.conversacion,
                                          {d.id: d.aprobar for d in cuerpo.decisiones}, voz=cuerpo.voz is True)


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


@r.get("/agente/voces")
async def voces(request: Request, quien: Quien = Depends(requiere("agente.conectar"))):
    """Las voces clonadas de la cuenta de Mnemo conectada que la persona marcó para las apps (`mnemo_list_voices`):
    `{"voces": [{"id", "nombre", "idioma", "motor"}], "elegida": la de Ajustes si está entre ellas y es de esta cuenta |
    None, "automatica": la que Mnemo ofrece a las apps (la que suena sin una elegida) | None, "conexion": {"voz": bool
    (la conexión tiene `mnemo:voice`), "ofrece_voz": bool (ese Mnemo lo ofrece)}}`. Sin
    conexión o sin `mnemo:voice`, sin voces. Solo el administrador: la voz es de su cuenta. Errores de Mnemo, `{codigo,
    mensaje}`: 409 `sin_voz`, 402 `mnemo_creditos`, 429 `frecuencia`, 502 `mnemo` o `mnemo_red`."""
    from ..agente import voz
    return await voz.listar(request.app)


@r.post("/agente/voz")
async def voz_clonada(cuerpo: VozIn, request: Request, quien: Quien = Depends(requiere("presentacion.ver"))):
    """Una frase con la voz clonada de Mnemo, en flujo (`application/x-ndjson`): `{"tipo": "inicio", "formato":
    "pcm_s16le" | "mp3" | "wav"…, "muestreo", "canales", "cache": bool, "voz": nombre}`, `{"tipo": "audio", "datos":
    base64}` mientras Mnemo la genera y `{"tipo": "fin", "ms_primer_audio", "ms_mnemo", "bytes"}` o `{"tipo": "error",
    "codigo", "mensaje"}`. El texto sale del servidor (`VozIn`): el plan guardado de la persona, una frase firmada de
    una respuesta o la prueba. Con `presentacion.ver` y el rol en `agente_voz.roles` (403 `voz_rol`; la prueba, solo el
    administrador). Lo que lo impide sale antes, `{codigo, mensaje}`: 409 `sin_voz` (sin voz elegida, sin
    `mnemo:voice`, otra cuenta o Mnemo no puede: el navegador sigue con su voz), `voz_apagada` (la voz no lee
    respuestas o no narra la presentación automática), `plan_vencido` o `con_personas`, 404 `no_existe`, 422 `texto`,
    402 `mnemo_creditos`, 429 `frecuencia` o `volumen`, 502 `mnemo` o `mnemo_red`. No guarda ni registra el texto ni el
    audio (`agente/voz.py`)."""
    from ..agente import voz
    return await voz.hablar(request, quien, cuerpo.model_dump(exclude_none=True))
