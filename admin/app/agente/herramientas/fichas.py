"""Herramientas del asistente sobre los registros de cada persona: su historial de acercamientos y de autorizaciones
(lectura) y las correcciones del día a día, que pasan por una tarjeta y la aprobación de la persona del equipo:
reportar una situación (fallecida o ya no vive en Yondó), registrar una solicitud del titular, reportar un posible
duplicado, marcar un dato como no disponible, marcar una ficha como atendida o pedir su actualización, cambiar el
estado de un teléfono, anular un acercamiento y, en las reuniones, editarlas y quitar un asistente.

Por qué está hecho así:

* Todo pasa por `ctx.api` con la sesión de quien conversa (las mismas rutas que usa la interfaz): los permisos, el
  alcance de P y C, el presupuesto diario, las lecturas, la proyección por rol y la auditoría son los del panel. De la
  base se lee directo solo lo que no tiene ruta y no se le pasa al modelo: si una persona no autorizó (en las rutas de
  Calidad, cuyas filas no lo dicen), la reunión que se va a editar (verla por la API registraría como consultados a
  todos sus asistentes) y, para no repetir una solicitud, las del propio usuario del último día.
* Al modelo le llega lo mínimo, con una lista blanca por herramienta: del historial de acercamientos, la fecha, el
  canal, el resultado, si fue efectivo, la nota con `minimizar.texto_libre` y el id (para anularlo); nunca el teléfono
  marcado, los datos dictados ni quién lo registró. De las autorizaciones, el estado, el medio, los canales, la fecha,
  si hay evidencia y si está confirmada; nunca las categorías sensibles autorizadas, la fila de la planilla, la
  evidencia escrita, la nota ni el usuario. De quien no autorizó el tratamiento, solo `minimizar.no_autorizo`, y el
  asistente no escribe en su ficha; sí registra una solicitud sobre sus datos: ejercer sus derechos (consultar,
  corregir, suprimir) no es tratarlos, y la API la permite a todos los roles.
* Escrituras: `confirmar` lee y arma la tarjeta, sin escribir nada, y anota en `Confirmacion.personas` a todas las
  personas que muestra (también las que la entrada no nombra con `persona_id`). `ejecutar` escribe una sola vez: con
  la `Idempotency-Key` del `tool_use` donde la ruta la respeta (reportar un duplicado) y, en las demás (situación,
  solicitud, dato no disponible, actualización, teléfono, anular, la reunión y sus asistentes), volviendo a leer y sin
  escribir si ya quedó como se pidió. Un número de teléfono nunca lo escribe el modelo: la tarjeta guarda la huella
  (HMAC) del número que mostró y, al aprobar, se busca en la ficha recién leída (como `registrar_acercamiento`).
* Al aprobar se vuelve a leer la ficha: la persona pudo dejar de autorizar, o alguien cambió lo que mostró la tarjeta.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from urllib.parse import quote

from pydantic import Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema
from starlette.concurrency import run_in_threadpool

from ... import acceso, modelo
from .. import minimizar
from .base import Confirmacion, Contexto, ErrorHerramienta, Herramienta, Resultado
from .gestion import (Fecha, Hora, Id, TipoLugar, _Entrada, _fecha_legible, _lista, _persona_tratable, _reunion_visible,
                      _texto, _ya_asiste, esquema, nomenclatura, pedir)
from .personas import (ACCIONES_ESCRITURA, _breve, _clave, _clave_huellas, _exigir_tratable, _ficha, _huella, _pedir,
                       _persona, _si_no, _tratable_al_escribir)

POR_PAGINA_API = 50          # acercamientos por página de `GET /api/personas/{pid}/acercamientos`
PAGINAS_HISTORIAL = 20       # el modelo recorre hasta los 1.000 más recientes
PAGINAS_PARA_ANULAR = 10     # un acercamiento se anula entre los 500 más recientes de la persona
MAX_AUTORIZACIONES = 30      # eventos de autorización que llegan al modelo (del más reciente al más viejo)
HORAS_ANULAR = 24            # como `api.acercamientos.HORAS_ANULAR`: el autor anula durante 24 horas; A y K, siempre
ACCIONES_SEGUIMIENTO = [*ACCIONES_ESCRITURA, {"tipo": "insignias"}]


# ───────────────────────────── Ayudas comunes (también las usa calidad.py) ─────────────────────────────

def fecha_de(v: Any) -> str | None:
    """El día (AAAA-MM-DD) de una fecha ISO de la base, o None."""
    return str(v)[:10] if isinstance(v, str) and re.match(r"\d{4}-\d{2}-\d{2}", v) else None


async def nombres_del_nomenclator(ctx: Contexto) -> frozenset[str]:
    """Los nombres del nomenclátor, también para A y K: las filas de Calidad (coincidencias, conflictos, situaciones)
    no dicen si `lugar` es el barrio o vereda o el texto libre de la ficha, y de quien no autorizó solo sale el primero
    (`minimizar.no_autorizo`)."""
    return await run_in_threadpool(minimizar.lugares_de, ctx.db)


def _que_no_autorizaron(db: Any, ids: set[int]) -> set[int]:
    return {p["_id"] for p in db.personas.find({"_id": {"$in": sorted(ids)}, "consentimiento": "no"}, {"_id": 1})}


async def no_autorizaron(ctx: Contexto, ids: Any) -> set[int]:
    """Cuáles de `ids` no autorizaron el tratamiento de sus datos: para las rutas cuyas filas no lo dicen (situaciones,
    lugares sin reconocer). Solo se lee la marca, nada se le pasa al modelo."""
    limpios = {i for i in ids if isinstance(i, int) and not isinstance(i, bool)}
    return await run_in_threadpool(_que_no_autorizaron, ctx.db, limpios) if limpios else set()


def sin_no_autorizo_por_mcp(ctx: Contexto, filas: list, es_de_no_autorizo: Any) -> tuple[list, int]:
    """Por MCP las filas de quien no autorizó no salen (queda su conteo): el agente externo es un tercero más, y de esa
    persona no hace falta ni quién es. En el chat sí, con la forma `no_autorizo`."""
    if getattr(ctx, "via", "chat") != "mcp":
        return filas, 0
    quedan = [f for f in filas if not es_de_no_autorizo(f)]
    return quedan, len(filas) - len(quedan)


NO_AUTORIZO_MCP = ("Esta persona no autorizó el tratamiento de sus datos: por MCP no se entrega nada de ella. "
                   "Se consulta en el panel.")


async def solo_quien_es(ctx: Contexto, d: dict, pid: int, vacio: str) -> Resultado:
    """La respuesta de una lectura sobre alguien que no autorizó: en el chat, solo quién es (`minimizar.no_autorizo`) y
    la lista `vacio` vacía (ni para A y K, aunque la API se lo dé); por MCP, nada (un error que no la nombra)."""
    if getattr(ctx, "via", "chat") == "mcp":
        raise ErrorHerramienta(NO_AUTORIZO_MCP, "no_contactable", estado=409, detalle={"motivo": "no_autorizo"})
    f = minimizar.no_autorizo(d, await nombres_del_nomenclator(ctx))
    return Resultado({"persona": f, vacio: [], "nota": minimizar.AVISO_NO_AUTORIZO}, f"#{pid}: no autorizó",
                     personas={pid})


def huellas_validas(v: dict | None, claves: frozenset[str] | None = None, tope: int = 30) -> dict | None:
    """Huellas (HMAC de `personas._huella`) que puso `confirmar`: hasta `tope`, con las claves esperadas y 24 hexa."""
    if v is not None and (len(v) > tope or any((claves is not None and k not in claves)
                                               or not re.fullmatch(r"[0-9a-f]{24}", str(x)) for k, x in v.items())):
        raise ValueError("huellas no válidas")
    return v


def _situacion(d: dict) -> dict:
    return d["situacion"] if isinstance(d.get("situacion"), dict) else {}


def _miles(n: int) -> str:
    return f"{n:,}".replace(",", ".")


# ───────────────────────────── historial_acercamientos ─────────────────────────────

class HistorialEntrada(_Entrada):
    persona_id: Id = Field(..., description="Id de la persona (de buscar_personas o ver_persona)")
    pagina: int = Field(1, ge=1, le=PAGINAS_HISTORIAL, description="Página de 50, del más reciente al más viejo")


def _limite_anular() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=HORAS_ANULAR)).replace(microsecond=0).isoformat()


def anulable(a: dict, quien: Any, limite: str | None = None) -> bool:
    """¿Lo puede anular quien conversa? Como la API: el autor durante 24 horas, A y K siempre. Nunca el automático de
    una asistencia (se anula quitando al asistente) ni uno ya anulado."""
    if a.get("anulado") or a.get("auto"):
        return False
    if quien.administra:
        return True
    return a.get("uid") == quien.uid and str(a.get("ts") or "") >= (limite or _limite_anular())


def fila_historial(a: dict, quien: Any, limite: str | None = None) -> dict:
    """Un acercamiento para el modelo: lista blanca (sin el teléfono, los datos dictados ni quién lo registró)."""
    out: dict[str, Any] = {"id": a.get("id"), "fecha": a.get("fecha") or fecha_de(a.get("ts")),
                           "canal": a.get("canal"), "resultado": a.get("resultado"),
                           "efectivo": a.get("efectivo") is True}
    nota = a.get("nota")
    if isinstance(nota, str) and nota.strip():
        out["nota"] = minimizar.texto_libre(nota)
    if a.get("anulado"):
        out["anulado"] = True
    if a.get("auto"):
        out["de_reunion"] = True  # el que deja una asistencia: se anula quitando al asistente
    out["propio"] = a.get("uid") == quien.uid
    out["anulable"] = anulable(a, quien, limite)
    return out


async def _historial(ctx: Contexto, a: HistorialEntrada) -> Resultado:
    d = await _ficha(ctx, a.persona_id)
    if d.get("consentimiento") == "no":  # ni para A y K, aunque la API se lo dé
        return await solo_quien_es(ctx, d, a.persona_id, "acercamientos")
    r = await _pedir(ctx, "GET", f"/api/personas/{a.persona_id}/acercamientos", params={"pagina": a.pagina})
    r = r if isinstance(r, dict) else {}
    total = int(r.get("total") or 0)
    limite = _limite_anular()
    filas = [fila_historial(x, ctx.quien, limite) for x in _lista(r.get("filas"))]
    paginas = max(1, -(-total // POR_PAGINA_API))
    out: dict[str, Any] = {"persona": {"id": a.persona_id, "nombre": d.get("nombre")}, "total": total,
                           "pagina": a.pagina, "paginas": paginas, "acercamientos": filas}
    if ctx.quien.rol == "planillero" and not ctx.quien.administra:
        out["nota"] = "Su rol no ve las notas de los acercamientos."
    if a.pagina < paginas:
        out["aviso"] = f"Hay más: pida la página {a.pagina + 1}."
    return Resultado(out, f"{_miles(total)} acercamiento{'s' if total != 1 else ''}" if total else "Sin acercamientos",
                     personas={a.persona_id})


HISTORIAL = Herramienta(
    nombre="historial_acercamientos",
    descripcion=(
        "Historial completo de acercamientos (contactos e intentos) de una persona, del más reciente al más viejo, de "
        "a 50 por página: fecha, canal, resultado, si fue efectivo, la nota (con los números largos enmascarados), "
        "si está anulado, si salió de una asistencia a reunión y el `id` de cada uno. `propio` dice si lo registró "
        "usted y `anulable`, si usted lo puede anular con anular_acercamiento (el autor durante 24 horas; el "
        "administrador y el coordinador, siempre). Úsala cuando ver_persona (que trae solo los 5 últimos) no alcance "
        "o para buscar el id de uno a anular. Nunca trae el teléfono usado ni quién lo registró. De quien no autorizó "
        "el tratamiento de sus datos no trae nada. Cuenta como consulta de la persona en el tope diario."),
    entrada=HistorialEntrada, tipo="lectura", permisos=("acercamientos.ver",), etiqueta="Leyendo el historial",
    ejecutar=_historial, esquema=esquema(HistorialEntrada), mcp="lectura")


# ───────────────────────────── autorizaciones_de ─────────────────────────────

class AutorizacionesEntrada(_Entrada):
    persona_id: Id = Field(..., description="Id de la persona")


def _confirmadas(eventos: list[dict]) -> set[Any]:
    """Los ids de los «sí» de planilla que alguien confirmó con la evidencia física: la confirmación es un evento nuevo
    (`clave_migracion` «confirma:<id>», `api/calidad.py`)."""
    out = set()
    for e in eventos:
        c = e.get("clave_migracion")
        if isinstance(c, str) and c.startswith("confirma:"):
            try:
                out.add(int(c.split(":", 1)[1]))
            except ValueError:
                continue
    return out


def fila_autorizacion(e: dict, confirmadas: set[Any]) -> dict:
    """Un evento de autorización para el modelo: lista blanca (nunca las categorías sensibles autorizadas, la fila de la
    planilla, la evidencia escrita, la nota ni quién lo registró)."""
    out: dict[str, Any] = {
        "id": e.get("id"), "estado": e.get("estado"), "medio": e.get("medio"),
        "canales": [c for c in e.get("canales") or [] if c in modelo.CANALES_AUTORIZACION],
        "fecha": fecha_de(e.get("ts")),
        "tiene_evidencia": bool(e.get("evidencia") or e.get("evidencia_sha256") or e.get("evidencia_fila"))}
    if e.get("medio") == "declarado_planilla":
        out["confirmada"] = bool(e.get("confirmada_por") is not None or e.get("id") in confirmadas)
    return out


async def _autorizaciones(ctx: Contexto, a: AutorizacionesEntrada) -> Resultado:
    # Primero la ruta exclusiva de A y K: a P y C los rechaza la API sin gastar una consulta de su tope diario
    eventos = _lista(await _pedir(ctx, "GET", f"/api/personas/{a.persona_id}/autorizaciones"))
    d = await _ficha(ctx, a.persona_id)
    if d.get("consentimiento") == "no":
        return await solo_quien_es(ctx, d, a.persona_id, "autorizaciones")
    confirmadas = _confirmadas(eventos)
    filas = [fila_autorizacion(e, confirmadas) for e in eventos[:MAX_AUTORIZACIONES]]
    out: dict[str, Any] = {
        "persona": {"id": a.persona_id, "nombre": d.get("nombre"), "consentimiento": d.get("consentimiento"),
                    "contacto_habilitado": d.get("contacto_habilitado")},
        "total": len(eventos), "autorizaciones": filas,
        "nota": ("Cada registro es un evento (no se borran): el último manda. Un «sí» declarado en planilla no "
                 "habilita el contacto hasta que se confirma con la evidencia física en Importar y exportar del "
                 "panel.")}
    if len(eventos) > len(filas):
        out["aviso"] = f"Se muestran los {len(filas)} más recientes de {len(eventos)}."
    return Resultado(out, f"{len(eventos)} registro{'s' if len(eventos) != 1 else ''} de autorización",
                     personas={a.persona_id})


AUTORIZACIONES = Herramienta(
    nombre="autorizaciones_de",
    descripcion=(
        "Historial de la autorización de tratamiento de datos (Ley 1581) de una persona: cada registro con su estado "
        "(si, no, revocada, pendiente), el medio (escrito, verbal, formulario, declarado en planilla…), los canales "
        "autorizados, la fecha, si tiene evidencia y, en los «sí» declarados en una planilla, si ya se confirmaron con "
        "la evidencia física. Úsala para verificar una autorización contra una planilla o para explicar por qué una "
        "persona no se puede contactar. Nunca trae las categorías sensibles autorizadas, la fila de la planilla, la "
        "evidencia escrita ni quién lo registró. De quien no autorizó no trae nada. Solo administrador y coordinador. "
        "Para registrar una autorización nueva usa registrar_autorizacion."),
    entrada=AutorizacionesEntrada, tipo="lectura", permisos=("admin",), etiqueta="Leyendo las autorizaciones",
    ejecutar=_autorizaciones, esquema=esquema(AutorizacionesEntrada), mcp="lectura")


# ───────────────────────────── reportar_situacion ─────────────────────────────

class ReportarSituacionEntrada(_Entrada):
    persona_id: Id
    situacion: Literal["fallecida", "no_reside"] = Field(
        ..., description="fallecida, o no_reside (ya no vive en Yondó)")


def _texto_situacion(sit: dict) -> str:
    estado = sit.get("estado") or "activa"
    texto = modelo.SITUACIONES.get(estado, estado)
    if estado in ("fallecida", "no_reside"):
        texto += " (confirmada)" if sit.get("confirmada") else " (por confirmar)"
    return texto


async def _confirmar_reportar_situacion(ctx: Contexto, a: ReportarSituacionEntrada) -> Confirmacion:
    d = await _ficha(ctx, a.persona_id)
    _exigir_tratable(d)
    sit = _situacion(d)
    if sit.get("estado") == a.situacion:
        raise ErrorHerramienta(f"La persona ya figura así: {_texto_situacion(sit)}.", "sin_cambios")
    detalle = [("Persona", _persona(d)),
               ("Situación", f"{_texto_situacion(sit)} → {modelo.SITUACIONES[a.situacion]} (por confirmar)")]
    aviso = ("Sale de las colas y de las listas de trabajo sin borrar nada. El administrador o el coordinador la "
             "confirma o la revierte en Calidad de datos.")
    return Confirmacion(f"Reportar la situación de {_persona(d)}", detalle, aviso, personas={a.persona_id})


async def _reportar_situacion(ctx: Contexto, a: ReportarSituacionEntrada) -> Resultado:
    d = await _ficha(ctx, a.persona_id)
    _exigir_tratable(d)
    if _situacion(d).get("estado") == a.situacion:  # la API no tiene idempotencia aquí: no se reporta dos veces
        return Resultado({"reportada": True, "ya_estaba": True, "persona": _breve(d)},
                         f"La ficha #{a.persona_id} ya estaba así", personas={a.persona_id})
    r = await _pedir(ctx, "POST", f"/api/personas/{a.persona_id}/situacion", cuerpo={"estado": a.situacion})
    r = r if isinstance(r, dict) else {}
    return Resultado({"reportada": True, "situacion": a.situacion, "persona": _breve(r) or {"id": a.persona_id}},
                     f"Situación reportada en la ficha #{a.persona_id}", list(ACCIONES_SEGUIMIENTO),
                     personas={a.persona_id})


REPORTAR_SITUACION = Herramienta(
    nombre="reportar_situacion",
    descripcion=(
        "Propone reportar que una persona falleció (`fallecida`) o que ya no vive en Yondó (`no_reside`). La persona "
        "sale de las colas y las listas de trabajo sin que se borre nada, y queda por confirmar: el administrador o el "
        "coordinador la confirma o la revierte (confirmar_situacion). Se guarda solo si la persona del equipo lo "
        "aprueba en la tarjeta. Úsala solo con lo que te contaron (un familiar, un vecino, la persona del equipo); "
        "nunca lo supongas por falta de contacto. Si el aviso salió de una llamada o una visita, "
        "registrar_acercamiento con su resultado ya lo reporta. No se usa con quien no autorizó el tratamiento de sus "
        "datos."),
    entrada=ReportarSituacionEntrada, tipo="escritura", permisos=("personas.situacion",),
    etiqueta="Reportando la situación", ejecutar=_reportar_situacion, confirmar=_confirmar_reportar_situacion,
    esquema=esquema(ReportarSituacionEntrada), mcp="escritura")


# ───────────────────────────── registrar_solicitud ─────────────────────────────

TIPOS_SOLICITUD = tuple(modelo.TIPOS_SOLICITUD)
# Los canales del formulario de la ficha (web/js/vistas/ficha.js)
CANALES_SOLICITUD = ("llamada", "whatsapp", "sms", "visita", "correo", "otro")
SIN_PERSONA = ("consulta", "otro", "registro")  # las que la API acepta sin persona
DEDUPE_SOLICITUD = timedelta(days=1)


class SolicitudEntrada(_Entrada):
    persona_id: Id | None = Field(None, description="La persona titular (sin ella, solo consulta, otro o registro)")
    tipo: Literal[TIPOS_SOLICITUD] = Field(
        ..., description="consulta, correccion, supresion (borrar sus datos), revocatoria (de la autorización), otro o "
                         "registro (pedido de registro)")
    canal: Literal[CANALES_SOLICITUD] = Field(..., description="Por dónde llegó la solicitud")
    descripcion: str = Field(..., min_length=3, max_length=2000, description="Qué pidió, como lo dijo; sin datos "
                                                                             "sensibles")

    @model_validator(mode="after")
    def _con_persona(self):
        if self.persona_id is None and self.tipo not in SIN_PERSONA:
            raise ValueError("Una corrección, supresión o revocatoria es de una persona: indique persona_id")
        return self


def _plazo_solicitud(tipo: str) -> str:
    dias = modelo.PLAZOS_SOLICITUD.get(tipo)
    return f"{dias} días hábiles" if dias else "Sin plazo legal"


def _misma_solicitud(db: Any, uid: Any, a: SolicitudEntrada) -> dict | None:
    """Una solicitud igual que el mismo usuario registró en el último día (la ruta no tiene idempotencia): una
    aprobación repetida no la duplica. Solo se lee su id y su plazo."""
    desde = (datetime.now(timezone.utc) - DEDUPE_SOLICITUD).replace(microsecond=0).isoformat()
    return db.solicitudes.find_one({"persona_id": a.persona_id, "tipo": a.tipo, "descripcion": a.descripcion.strip(),
                                    "creado_por.uid": uid, "ts": {"$gte": desde}}, {"_id": 1, "vence": 1})


async def _confirmar_solicitud(ctx: Contexto, a: SolicitudEntrada) -> Confirmacion:
    detalle: list[tuple[str, str]] = []
    personas: set[int] = set()
    if a.persona_id is not None:
        d = await _ficha(ctx, a.persona_id)  # el consultor solo con las personas de su trabajo, como la API
        detalle.append(("Persona", _persona(d)))
        personas.add(a.persona_id)
    ya = await run_in_threadpool(_misma_solicitud, ctx.db, ctx.quien.uid, a)
    if ya is not None:
        raise ErrorHerramienta(f"Usted ya registró hoy una solicitud igual (#{ya['_id']}): no se registra otra.",
                               "duplicada", estado=409, detalle={"id": ya["_id"]})
    detalle += [("Qué pide", modelo.TIPOS_SOLICITUD[a.tipo]), ("Plazo de respuesta", _plazo_solicitud(a.tipo)),
                ("Canal", modelo.CANALES.get(a.canal, a.canal)), ("Descripción", a.descripcion)]
    aviso = "Queda en Calidad de datos (Solicitudes) con su plazo legal de respuesta."
    if a.tipo in modelo.RECLAMOS:
        aviso += " Mientras se resuelve, la ficha queda con «reclamo en trámite» y sale de las colas."
    return Confirmacion("Registrar una solicitud del titular", detalle, aviso, personas=personas)


async def _solicitud(ctx: Contexto, a: SolicitudEntrada) -> Resultado:
    personas = {a.persona_id} if a.persona_id is not None else set()
    ya = await run_in_threadpool(_misma_solicitud, ctx.db, ctx.quien.uid, a)
    if ya is not None:  # esta misma aprobación ya la registró (un reintento): no se repite
        return Resultado({"registrada": True, "ya_existia": True, "solicitud": {
            "id": ya["_id"], "tipo": a.tipo, "vence": ya.get("vence")}}, f"Ya estaba la solicitud #{ya['_id']}",
            personas=personas)
    cuerpo = {"persona_id": a.persona_id, "tipo": a.tipo, "canal": a.canal, "descripcion": a.descripcion}
    r = await _pedir(ctx, "POST", "/api/solicitudes", cuerpo=cuerpo)
    r = r if isinstance(r, dict) else {}
    return Resultado({"registrada": True, "solicitud": {"id": r.get("id"), "tipo": a.tipo, "vence": r.get("vence"),
                                                       "plazo": _plazo_solicitud(a.tipo)}},
                     f"Solicitud #{r.get('id')} registrada", list(ACCIONES_SEGUIMIENTO), personas=personas)


SOLICITUD = Herramienta(
    nombre="registrar_solicitud",
    descripcion=(
        "Propone registrar una solicitud de un titular sobre sus datos (derechos de la Ley 1581): consulta, "
        "corrección, supresión, revocatoria de la autorización, otro, o un pedido de registro. Queda en Calidad de "
        "datos con su plazo legal (10 días hábiles la consulta, 15 los reclamos) para que el administrador responda. "
        "Corrección, supresión y revocatoria van con `persona_id`; consulta, otro y registro pueden ir sin persona. "
        "Registra solo lo que el titular pidió, con sus palabras y sin datos sensibles. También vale para quien no "
        "autorizó: ejercer sus derechos no es tratar sus datos. Registrarla no suprime ni corrige nada: lo hace el "
        "administrador. Si salió de un contacto, registrar_acercamiento con resultado solicitud_derechos ya la abre. "
        "Se guarda solo si la persona del equipo lo aprueba."),
    entrada=SolicitudEntrada, tipo="escritura", permisos=("solicitudes.crear",), etiqueta="Registrando la solicitud",
    ejecutar=_solicitud, confirmar=_confirmar_solicitud, esquema=esquema(SolicitudEntrada), mcp="escritura")


# ───────────────────────────── reportar_duplicado ─────────────────────────────

class DuplicadoEntrada(_Entrada):
    persona_id: Id = Field(..., description="Una de las dos fichas")
    con_id: Id = Field(..., description="La otra ficha, que sería la misma persona")
    nota: str | None = Field(None, min_length=2, max_length=500, description="Por qué parecen la misma persona")

    @model_validator(mode="after")
    def _distintas(self):
        if self.persona_id == self.con_id:
            raise ValueError("persona_id y con_id deben ser dos fichas distintas")
        return self


async def _confirmar_duplicado(ctx: Contexto, a: DuplicadoEntrada) -> Confirmacion:
    d = await _ficha(ctx, a.persona_id)
    _exigir_tratable(d)
    o = await _ficha(ctx, a.con_id)
    _exigir_tratable(o)
    detalle = [("Ficha", _persona(d)), ("Posible misma persona que", _persona(o))]
    if a.nota:
        detalle.append(("Nota", a.nota))
    return Confirmacion("Reportar un posible duplicado", detalle,
                        "Queda en Coincidencias de Calidad de datos para que el administrador o el coordinador decida "
                        "si son la misma persona. No se une nada.", personas={a.persona_id, a.con_id})


async def _duplicado(ctx: Contexto, a: DuplicadoEntrada) -> Resultado:
    clave = _clave(ctx)
    if await _tratable_al_escribir(ctx, a.persona_id, clave) is not None:
        _exigir_tratable(await _ficha(ctx, a.con_id))  # la API solo mira la primera
    r = await _pedir(ctx, "POST", f"/api/personas/{a.persona_id}/duplicado",
                     cuerpo={"con_id": a.con_id, "nota": a.nota}, clave=clave)
    r = r if isinstance(r, dict) else {}
    return Resultado({"reportado": True, "coincidencia_id": r.get("id"), "fichas": [a.persona_id, a.con_id]},
                     "Posible duplicado reportado", list(ACCIONES_SEGUIMIENTO), personas={a.persona_id, a.con_id})


DUPLICADO = Herramienta(
    nombre="reportar_duplicado",
    descripcion=(
        "Propone reportar que dos fichas parecen ser la misma persona (`persona_id` y `con_id`), con una nota "
        "opcional de por qué. No une nada: queda en Coincidencias de Calidad de datos para que el administrador o el "
        "coordinador lo revise (ellos pueden unirlas con resolver_coincidencias). Úsala cuando personas_parecidas o la "
        "persona del equipo encuentran un duplicado. Si ya estaba reportado, no se repite. No se usa con quien no "
        "autorizó el tratamiento de sus datos. Se guarda solo si la persona del equipo lo aprueba."),
    entrada=DuplicadoEntrada, tipo="escritura", permisos=("personas.duplicado",),
    etiqueta="Reportando el duplicado", ejecutar=_duplicado, confirmar=_confirmar_duplicado,
    esquema=esquema(DuplicadoEntrada), mcp="escritura")


# ───────────────────────────── marcar_no_disponible ─────────────────────────────

CAMPOS_NO_DISPONIBLE = ("cedula", "telefono", "mesa", "puesto", "edad", "sexo")
DEL_CONSULTOR = ("cedula", "puesto", "mesa")
NOMBRE_DATO = {"cedula": "Cédula", "telefono": "Teléfono", "mesa": "Mesa", "puesto": "Puesto de votación",
               "edad": "Edad", "sexo": "Sexo"}


class NoDisponibleEntrada(_Entrada):
    persona_id: Id
    campo: Literal[CAMPOS_NO_DISPONIBLE] = Field(..., description="El dato (el consultor: cedula, puesto o mesa)")
    motivo: Literal[tuple(modelo.MOTIVOS_NO_DISPONIBLE)] | None = Field(
        None, description="no_la_dio, no_tiene o no_sabe (obligatorio salvo con quitar)")
    quitar: bool = Field(False, description="true: quitar la marca (el dato vuelve a figurar como faltante)")

    @model_validator(mode="after")
    def _motivo(self):
        if self.quitar and self.motivo is not None:
            raise ValueError("Con quitar: true no va motivo")
        if not self.quitar and self.motivo is None:
            raise ValueError("Indique el motivo: no_la_dio, no_tiene o no_sabe")
        return self


def _exigir_campo_del_rol(ctx: Contexto, a: NoDisponibleEntrada) -> None:
    q = ctx.quien
    if not q.administra and q.rol == "consultor" and a.campo not in DEL_CONSULTOR:
        raise ErrorHerramienta("El consultor solo marca la cédula, el puesto y la mesa.", "permiso", estado=403,
                               detalle={"campo": a.campo})


def _marca(d: dict, campo: str) -> str | None | bool:
    """El motivo marcado en la ficha, None sin marca, o False si la ficha del rol no trae las marcas (el consultor)."""
    nd = d.get("no_disponible")
    if not isinstance(nd, dict):
        return False
    m = nd.get(campo)
    return (m.get("motivo") if isinstance(m, dict) else m) if m else None


def _ya_marcado(d: dict, a: NoDisponibleEntrada) -> bool:
    marca = _marca(d, a.campo)
    if marca is False:  # sin las marcas a la vista no se sabe: se escribe (la API deja la misma marca)
        return False
    return marca is None if a.quitar else marca == a.motivo


def _dias_reintento(db: Any) -> int:
    return int(modelo.leer_ajustes(db).get("dias_reintento_dato") or 90)


async def _confirmar_no_disponible(ctx: Contexto, a: NoDisponibleEntrada) -> Confirmacion:
    _exigir_campo_del_rol(ctx, a)
    d = await _ficha(ctx, a.persona_id)
    _exigir_tratable(d)
    if _ya_marcado(d, a):
        raise ErrorHerramienta("La ficha ya está así: " + ("ese dato no tiene marca." if a.quitar else
                                                          "ese dato ya tiene esa marca."), "sin_cambios")
    if not a.quitar and isinstance(d.get("faltan"), list) and a.campo not in d["faltan"] and _marca(d, a.campo) is None:
        raise ErrorHerramienta("La ficha ya tiene ese dato: no hace falta marcarlo como no disponible.", "sin_cambios")
    dato = NOMBRE_DATO[a.campo]
    if a.quitar:
        return Confirmacion(f"Quitar la marca de dato no disponible de {_persona(d)}",
                            [("Persona", _persona(d)), ("Dato", dato), ("Marca", "Se quita")],
                            "El dato vuelve a figurar como faltante.", personas={a.persona_id})
    dias = await run_in_threadpool(_dias_reintento, ctx.db)
    return Confirmacion(f"Marcar un dato no disponible de {_persona(d)}",
                        [("Persona", _persona(d)), ("Dato", dato),
                         ("Motivo", modelo.MOTIVOS_NO_DISPONIBLE[a.motivo])],
                        "Ese dato deja de figurar como faltante (y sale de las listas de trabajo por él) durante "
                        f"{dias} días; después se vuelve a pedir.", personas={a.persona_id})


async def _no_disponible(ctx: Contexto, a: NoDisponibleEntrada) -> Resultado:
    _exigir_campo_del_rol(ctx, a)
    d = await _ficha(ctx, a.persona_id)
    _exigir_tratable(d)
    if _ya_marcado(d, a):
        return Resultado({"guardado": True, "ya_estaba": True, "persona": _breve(d)},
                         f"La ficha #{a.persona_id} ya estaba así", personas={a.persona_id})
    cuerpo = {"campo": a.campo, "motivo": a.motivo, "quitar": a.quitar}
    r = await _pedir(ctx, "POST", f"/api/personas/{a.persona_id}/no-disponible", cuerpo=cuerpo)
    r = r if isinstance(r, dict) else {}
    return Resultado({"guardado": True, "campo": a.campo, "quitar": a.quitar,
                      "persona": _breve(r) or {"id": a.persona_id}},
                     f"Dato marcado en la ficha #{a.persona_id}", list(ACCIONES_SEGUIMIENTO), personas={a.persona_id})


NO_DISPONIBLE = Herramienta(
    nombre="marcar_no_disponible",
    descripcion=(
        "Propone marcar que un dato de la ficha no se pudo conseguir: la cédula, el teléfono, el puesto, la mesa, la "
        "edad o el sexo, con el motivo (no_la_dio, no_tiene, no_sabe). Por un tiempo (el de Ajustes) el dato deja de "
        "figurar como faltante y la persona sale de las listas de trabajo por ese dato; después se vuelve a pedir. "
        "Con `quitar: true` quita la marca. El consultor solo marca la cédula, el puesto y la mesa. Úsala solo cuando "
        "te digan que la persona no tiene, no sabe o no quiso dar el dato; si te dictaron el dato, usa editar_persona "
        "o agregar_telefono. No se usa con quien no autorizó. Se guarda solo si la persona del equipo lo aprueba."),
    entrada=NoDisponibleEntrada, tipo="escritura", permisos=("personas.no_disponible",),
    etiqueta="Marcando el dato no disponible", ejecutar=_no_disponible, confirmar=_confirmar_no_disponible,
    esquema=esquema(NoDisponibleEntrada), mcp="escritura")


# ───────────────────────────── pedir_actualizacion ─────────────────────────────

class ActualizacionEntrada(_Entrada):
    persona_id: Id
    accion: Literal["atendida", "pedir"] = Field(
        ..., description="atendida: la ficha ya se actualizó (quita el pedido pendiente); pedir: que el equipo la "
                         "actualice (solo administrador y coordinador)")
    nota: str | None = Field(None, min_length=2, max_length=1000, description="Qué se actualizó o qué hay que revisar")


def _pedido(d: dict) -> dict | None:
    r = d.get("requiere_actualizacion")
    return r if isinstance(r, dict) else ({"motivo": r} if isinstance(r, str) else None)


def _motivo_pedido(p: dict | None) -> str:
    m = (p or {}).get("motivo")
    return modelo.MOTIVOS_ACTUALIZACION.get(m, m or "Sin motivo")


def _actualizacion_hecha(d: dict, a: ActualizacionEntrada) -> bool:
    p = _pedido(d)
    return p is None if a.accion == "atendida" else (p or {}).get("motivo") == "administrador"


async def _confirmar_actualizacion(ctx: Contexto, a: ActualizacionEntrada) -> Confirmacion:
    if a.accion == "pedir" and not ctx.quien.administra:
        raise ErrorHerramienta("Solo el administrador y el coordinador piden una actualización.", "permiso", estado=403)
    d = await _ficha(ctx, a.persona_id)
    _exigir_tratable(d)
    p = _pedido(d)
    if _actualizacion_hecha(d, a):
        raise ErrorHerramienta("La ficha no tiene un pedido de actualización pendiente." if a.accion == "atendida" else
                               "La ficha ya tiene un pedido de actualización del administrador.", "sin_cambios")
    detalle = [("Persona", _persona(d))]
    if a.accion == "atendida":
        detalle.append(("Pedido que se atiende", _motivo_pedido(p)))
        titulo, aviso = (f"Marcar como atendida la ficha de {_persona(d)}",
                         "Se quita el pedido de actualización: la ficha sale de la lista «por actualizar».")
    else:
        detalle.append(("Pedido", (f"{_motivo_pedido(p)} → " if p else "") + _motivo_pedido({"motivo":
                                                                                             "administrador"})))
        titulo, aviso = (f"Pedir que actualicen la ficha de {_persona(d)}",
                         "La ficha entra en la lista «por actualizar» del equipo que trabaja su zona.")
    if a.nota:
        detalle.append(("Nota", a.nota))
    return Confirmacion(titulo, detalle, aviso, personas={a.persona_id})


async def _actualizacion(ctx: Contexto, a: ActualizacionEntrada) -> Resultado:
    if a.accion == "pedir" and not ctx.quien.administra:
        raise ErrorHerramienta("Solo el administrador y el coordinador piden una actualización.", "permiso", estado=403)
    d = await _ficha(ctx, a.persona_id)
    _exigir_tratable(d)
    if _actualizacion_hecha(d, a):  # la ruta no tiene idempotencia: si ya quedó, no se escribe ni se audita otra vez
        return Resultado({"guardado": True, "ya_estaba": True, "accion": a.accion, "persona": _breve(d)},
                         f"La ficha #{a.persona_id} ya estaba así", personas={a.persona_id})
    r = await _pedir(ctx, "POST", f"/api/personas/{a.persona_id}/actualizacion",
                     cuerpo={"nota": a.nota, "pedir": a.accion == "pedir"})
    r = r if isinstance(r, dict) else {}
    return Resultado({"guardado": True, "accion": a.accion, "persona": _breve(r) or {"id": a.persona_id}},
                     "Ficha marcada como atendida" if a.accion == "atendida" else "Actualización pedida",
                     list(ACCIONES_SEGUIMIENTO), personas={a.persona_id})


ACTUALIZACION = Herramienta(
    nombre="pedir_actualizacion",
    descripcion=(
        "Propone una de dos cosas sobre el pedido de actualización de una ficha: `atendida` (la ficha ya se revisó o "
        "se actualizó: quita el pedido pendiente y la saca de la lista «por actualizar») o `pedir` (que el equipo de "
        "su zona la actualice; solo administrador y coordinador). Con una nota opcional de qué se hizo o qué revisar. "
        "Úsala después de corregir la ficha con editar_persona, ubicar_persona o agregar_telefono, o cuando te pidan "
        "que alguien la revise. No se usa con quien no autorizó. Se guarda solo si la persona del equipo lo aprueba."),
    entrada=ActualizacionEntrada, tipo="escritura", permisos=("personas.editar",),
    etiqueta="Guardando el pedido de actualización", ejecutar=_actualizacion, confirmar=_confirmar_actualizacion,
    esquema=esquema(ActualizacionEntrada), mcp="escritura")


# ───────────────────────────── estado_telefono ─────────────────────────────

ESTADOS_PARA_TELEFONO = ("confirmado", "sin_verificar", "no_usa", "equivocado", "inexistente")


class EstadoTelefonoEntrada(_Entrada):
    persona_id: Id
    telefono_indice: int | None = Field(None, ge=0, le=50, description="El `indice` del número en ver_persona (los "
                                                                        "que se pueden usar)")
    telefono_posicion: int | None = Field(
        None, ge=0, le=50, description="Solo para un número sin `indice` (ya no se puede usar): su posición, desde 0, "
                                       "en la lista `telefonos` de ver_persona")
    estado: Literal[ESTADOS_PARA_TELEFONO] | None = Field(
        None, description="confirmado (es suyo), sin_verificar, no_usa (ya no lo usa), equivocado (de otra persona) o "
                          "inexistente")
    whatsapp: bool | None = Field(None, description="Si tiene WhatsApp")
    no_contactar: bool | None = Field(None, description="true: no llamar ni escribir a ese número (pedido del titular)")
    principal: bool = Field(False, description="true: pasa a ser el primer número de la ficha")
    nota: str | None = Field(None, min_length=1, max_length=300)
    # La huella del número que mostró la tarjeta: la pone `confirmar` (el modelo no la ve). Al aprobar se cambia ese
    # número, aunque su `indice` o su posición hayan cambiado
    huellas: SkipJsonSchema[dict[str, str] | None] = None

    @field_validator("huellas")
    @classmethod
    def _h(cls, v):
        return huellas_validas(v, frozenset({"telefono"}))

    @model_validator(mode="after")
    def _coherente(self):
        if (self.telefono_indice is None) == (self.telefono_posicion is None):
            raise ValueError("Indique telefono_indice (el número que se puede usar) o telefono_posicion (uno que ya "
                             "no), no los dos")
        if self.estado is None and self.whatsapp is None and self.no_contactar is None and not self.principal \
                and self.nota is None:
            raise ValueError("No hay cambios: indique estado, whatsapp, no_contactar, principal o nota")
        if self.principal and (self.estado in ("no_usa", "equivocado", "inexistente") or self.no_contactar):
            raise ValueError("Un número que no se puede usar no puede ser el principal")
        return self


def _telefonos_de(d: dict) -> list[dict]:
    return [t for t in d.get("telefonos") or [] if isinstance(t, dict) and t.get("numero")]


def _elegido(d: dict, a: EstadoTelefonoEntrada) -> dict:
    """El número de la ficha que nombra la entrada (por su `indice` entre los usables o por su posición)."""
    tels = _telefonos_de(d)
    if a.telefono_indice is not None:
        t = next((t for t in tels if t.get("indice") == a.telefono_indice), None)
        if t is None:
            usables = sorted(t["indice"] for t in tels if isinstance(t.get("indice"), int))
            raise ErrorHerramienta(f"La ficha no tiene un número usable con indice {a.telefono_indice}"
                                   + (f" (los usables: {usables})." if usables else ": no tiene números usables."),
                                   "invalido", estado=422)
        return t
    if a.telefono_posicion >= len(tels):
        raise ErrorHerramienta(f"La ficha tiene {len(tels)} número(s): no hay uno en la posición {a.telefono_posicion} "
                               "(se cuenta desde 0).", "invalido", estado=422)
    return tels[a.telefono_posicion]


def _cambios_telefono(t: dict, a: EstadoTelefonoEntrada) -> dict:
    """Lo que cambia de verdad en ese número (lo igual no se manda: la ruta no tiene idempotencia)."""
    cambios: dict[str, Any] = {}
    if a.estado is not None and (t.get("estado") or "sin_verificar") != a.estado:
        cambios["estado"] = a.estado
    if a.whatsapp is not None and bool(t.get("whatsapp")) != a.whatsapp:
        cambios["whatsapp"] = a.whatsapp
    if a.no_contactar is not None and bool(t.get("no_contactar")) != a.no_contactar:
        cambios["no_contactar"] = a.no_contactar
    if a.nota is not None and t.get("nota") != a.nota:
        cambios["nota"] = a.nota
    return cambios


def _es_principal(d: dict, numero: str) -> bool:
    return any(t.get("numero") == numero and t.get("indice") == 0 for t in _telefonos_de(d))


def _exigir_principal(ctx: Contexto, a: EstadoTelefonoEntrada) -> None:
    if a.principal and not ctx.quien.puede("personas.editar"):
        raise ErrorHerramienta("Su rol no cambia cuál es el número principal.", "permiso", estado=403)


def _antes_despues(etiqueta: str, antes: str, despues: str) -> tuple[str, str]:
    return etiqueta, f"{antes} → {despues}"


async def _confirmar_estado_telefono(ctx: Contexto, a: EstadoTelefonoEntrada) -> Confirmacion:
    _exigir_principal(ctx, a)
    d = await _ficha(ctx, a.persona_id)
    _exigir_tratable(d)
    t = _elegido(d, a)
    numero = str(t["numero"])
    cambios = _cambios_telefono(t, a)
    principal = a.principal and not _es_principal(d, numero)
    if not cambios and not principal:
        raise ErrorHerramienta("Ese número ya está así: no hay nada que cambiar.", "sin_cambios")
    detalle = [("Persona", _persona(d)), ("Número", acceso.enmascarar_telefono(numero) or "(sin número)")]
    if "estado" in cambios:
        detalle.append(_antes_despues("Estado", modelo.ESTADOS_TELEFONO.get(t.get("estado") or "sin_verificar", ""),
                                      modelo.ESTADOS_TELEFONO[cambios["estado"]]))
    if "whatsapp" in cambios:
        detalle.append(_antes_despues("WhatsApp", _si_no(bool(t.get("whatsapp"))), _si_no(cambios["whatsapp"])))
    if "no_contactar" in cambios:
        detalle.append(_antes_despues("No contactar a este número", _si_no(bool(t.get("no_contactar"))),
                                      _si_no(cambios["no_contactar"])))
    if principal:
        detalle.append(("Principal", "Pasa a ser el primer número"))
    if "nota" in cambios:
        detalle.append(("Nota", cambios["nota"]))
    aviso = None
    if cambios.get("estado") in ("no_usa", "equivocado", "inexistente") or cambios.get("no_contactar"):
        aviso = "Ese número deja de usarse para contactar a la persona."
    a.huellas = {"telefono": _huella(await _clave_huellas(ctx), "telefono", numero)}
    return Confirmacion(f"Cambiar un teléfono de {_persona(d)}", detalle, aviso, personas={a.persona_id})


async def _numero_por_huella(ctx: Contexto, d: dict, huella: str) -> dict:
    """El número de la ficha recién leída que mostró la tarjeta (entre todos, no solo los usables: el cambio pudo
    dejarlo sin usar en un intento anterior)."""
    clave = await _clave_huellas(ctx)
    t = next((t for t in _telefonos_de(d) if _huella(clave, "telefono", t.get("numero")) == huella), None)
    if t is None:
        raise ErrorHerramienta("El número que mostró la tarjeta ya no está en la ficha (otra persona lo cambió): no se "
                               "cambió nada. Vuelva a leer la ficha y proponga el cambio de nuevo.", "cambiada",
                               estado=409, detalle={"campos": ["telefono"]})
    return t


async def _estado_telefono(ctx: Contexto, a: EstadoTelefonoEntrada) -> Resultado:
    _exigir_principal(ctx, a)
    d = await _ficha(ctx, a.persona_id)
    _exigir_tratable(d)
    t = await _numero_por_huella(ctx, d, a.huellas["telefono"]) if (a.huellas or {}).get("telefono") \
        else _elegido(d, a)
    numero = str(t["numero"])
    ruta = f"/api/personas/{a.persona_id}/telefonos/{quote(numero, safe='')}"
    cambios = _cambios_telefono(t, a)
    hechos: list[str] = []
    r: Any = d
    if cambios:  # PATCH: sin idempotencia en la API; lo que ya está como se pidió no se manda
        r = await _pedir(ctx, "PATCH", ruta, cuerpo=cambios)
        hechos += list(cambios)
    r = r if isinstance(r, dict) else d
    if a.principal and not _es_principal(r, numero):
        r = await _pedir(ctx, "POST", f"{ruta}/principal")
        r = r if isinstance(r, dict) else d
        hechos.append("principal")
    f = minimizar.ficha(r)
    contenido = {"guardado": True, "cambios": hechos, "persona": _breve(r) or {"id": a.persona_id},
                 **({"telefonos": f["telefonos"]} if "telefonos" in f else {})}
    if not hechos:
        contenido["ya_estaba"] = True
    return Resultado(contenido, f"Teléfono actualizado en la ficha #{a.persona_id}" if hechos else
                     f"El teléfono de la ficha #{a.persona_id} ya estaba así", list(ACCIONES_SEGUIMIENTO),
                     personas={a.persona_id})


ESTADO_TELEFONO = Herramienta(
    nombre="estado_telefono",
    descripcion=(
        "Propone cambiar las marcas de un teléfono que ya está en la ficha: el estado (confirmado, sin_verificar, "
        "no_usa, equivocado, inexistente), si tiene WhatsApp, «no contactar» para ese número y una nota; con "
        "`principal: true` pasa a ser el primero (no el consultor). Nombra el número por su `indice` de ver_persona "
        "(los usables) o, si ya no se puede usar, por su `telefono_posicion` en esa lista; nunca escribas el número: "
        "el panel lo busca y la tarjeta lo muestra enmascarado. Para un número nuevo usa agregar_telefono; para un "
        "contacto que falló, registrar_acercamiento ya marca el número. No se usa con quien no autorizó. Se guarda "
        "solo si la persona del equipo lo aprueba."),
    entrada=EstadoTelefonoEntrada, tipo="escritura", permisos=("personas.telefonos",),
    etiqueta="Cambiando el teléfono", ejecutar=_estado_telefono, confirmar=_confirmar_estado_telefono,
    esquema=esquema(EstadoTelefonoEntrada), mcp="escritura")


# ───────────────────────────── anular_acercamiento ─────────────────────────────

class AnularEntrada(_Entrada):
    persona_id: Id = Field(..., description="La persona del acercamiento")
    acercamiento_id: Id = Field(..., description="El `id` del acercamiento (de historial_acercamientos)")
    motivo: str = Field(..., min_length=3, max_length=300, description="Por qué se anula (por ejemplo, se registró "
                                                                       "en la ficha equivocada)")


async def _buscar_acercamiento(ctx: Contexto, pid: int, aid: int) -> dict | None:
    """El acercamiento `aid` entre los de la persona (de la más reciente a la más vieja, hasta
    `PAGINAS_PARA_ANULAR` páginas): la API no tiene una ruta para uno solo."""
    for pagina in range(1, PAGINAS_PARA_ANULAR + 1):
        r = await _pedir(ctx, "GET", f"/api/personas/{pid}/acercamientos", params={"pagina": pagina})
        r = r if isinstance(r, dict) else {}
        filas = _lista(r.get("filas"))
        x = next((x for x in filas if x.get("id") == aid), None)
        if x is not None or len(filas) < POR_PAGINA_API:
            return x
    return None


def _describir(x: dict) -> str:
    canal = x.get("canal")
    return " · ".join(s for s in (x.get("fecha") or fecha_de(x.get("ts")), modelo.CANALES.get(canal, canal),
                                  modelo.etiqueta_resultado(x.get("resultado"), canal)) if s)


async def _anulable_o_error(ctx: Contexto, a: AnularEntrada) -> tuple[dict, dict]:
    d = await _ficha(ctx, a.persona_id)
    _exigir_tratable(d)
    x = await _buscar_acercamiento(ctx, a.persona_id, a.acercamiento_id)
    if x is None:
        raise ErrorHerramienta(f"El acercamiento #{a.acercamiento_id} no está entre los de la ficha #{a.persona_id} "
                               "(búsquelo con historial_acercamientos).", "no_existe", estado=404)
    return d, x


async def _confirmar_anular(ctx: Contexto, a: AnularEntrada) -> Confirmacion:
    d, x = await _anulable_o_error(ctx, a)
    if x.get("anulado"):
        raise ErrorHerramienta("Ese acercamiento ya está anulado.", "sin_cambios")
    if x.get("auto"):
        raise ErrorHerramienta("Ese acercamiento lo dejó una asistencia a reunión: se anula quitando a la persona de "
                               "la reunión (quitar_asistente).", "invalido", estado=422)
    if not anulable(x, ctx.quien):
        raise ErrorHerramienta("Solo su autor lo anula, y durante 24 horas (el administrador y el coordinador, "
                               "siempre).", "permiso", estado=403)
    detalle = [("Persona", _persona(d)), ("Acercamiento", f"{_describir(x)} (#{a.acercamiento_id})"),
               ("Motivo", a.motivo)]
    return Confirmacion(f"Anular un acercamiento con {_persona(d)}", detalle,
                        "Deja de contar en el abordaje y se revierten sus efectos en los teléfonos y la situación si "
                        "siguen como los dejó. Las autorizaciones y las solicitudes que abrió no se revierten.",
                        personas={a.persona_id})


async def _anular(ctx: Contexto, a: AnularEntrada) -> Resultado:
    _, x = await _anulable_o_error(ctx, a)
    if x.get("anulado"):  # la ruta devuelve la ficha si ya estaba, pero tampoco se pide dos veces
        return Resultado({"anulado": True, "ya_estaba": True, "acercamiento_id": a.acercamiento_id},
                         f"El acercamiento #{a.acercamiento_id} ya estaba anulado", personas={a.persona_id})
    r = await _pedir(ctx, "POST", f"/api/acercamientos/{a.acercamiento_id}/anular", cuerpo={"motivo": a.motivo})
    r = r if isinstance(r, dict) else {}
    contenido: dict[str, Any] = {"anulado": True, "acercamiento_id": a.acercamiento_id}
    if "id" in r:
        f = minimizar.ficha(r)
        contenido["persona"] = {**_breve(r), **({"abordaje": f["abordaje"]} if "abordaje" in f else {})}
    return Resultado(contenido, f"Acercamiento #{a.acercamiento_id} anulado", list(ACCIONES_SEGUIMIENTO),
                     personas={a.persona_id})


ANULAR = Herramienta(
    nombre="anular_acercamiento",
    descripcion=(
        "Propone anular un acercamiento registrado por error (en otra ficha, con otro resultado o repetido), con el "
        "`motivo`. Necesita `persona_id` y el `acercamiento_id` (de historial_acercamientos, donde `anulable` dice si "
        "usted puede). El autor lo anula durante 24 horas; el administrador y el coordinador, siempre. El de una "
        "asistencia a reunión se anula quitando a la persona de la reunión (quitar_asistente). Anular no borra nada: "
        "deja de contar en el abordaje y revierte sus efectos en los teléfonos y la situación; las autorizaciones y "
        "solicitudes que abrió no se revierten. No se usa con quien no autorizó. Se hace solo si la persona del equipo "
        "lo aprueba."),
    entrada=AnularEntrada, tipo="escritura", permisos=("acercamientos.registrar",),
    etiqueta="Anulando el acercamiento", ejecutar=_anular, confirmar=_confirmar_anular, esquema=esquema(AnularEntrada),
    mcp="escritura")


# ───────────────────────────── editar_reunion ─────────────────────────────

# (campo de la entrada, campo de la API, etiqueta de la tarjeta)
CAMPOS_REUNION = (("titulo", "titulo", "Título"), ("fecha", "fecha", "Fecha"), ("hora", "hora", "Hora de inicio"),
                  ("hora_fin", "hora_fin", "Hora de fin"), ("lugar_id", "lugar_id", "Barrio o vereda"),
                  ("sitio", "lugar_texto", "Sitio"), ("tema", "tema", "Tema"),
                  ("descripcion", "descripcion", "Descripción"), ("compromisos", "compromisos", "Compromisos"),
                  ("abierta_a_equipo", "abierta_a_equipo", "Abierta al equipo"))
CAMPOS_API_REUNION = frozenset(api for _, api, _ in CAMPOS_REUNION)


class EditarReunionEntrada(_Entrada):
    """Lo que se cambia de la reunión, con su valor nuevo. Sin valores vacíos: vaciar un dato se hace en el panel."""
    reunion_id: Id
    titulo: str | None = Field(None, min_length=3, max_length=160)
    fecha: Fecha | None = Field(None, description="AAAA-MM-DD")
    hora: Hora | None = Field(None, description="Hora de inicio")
    hora_fin: Hora | None = Field(None, description="Hora de fin (después de la de inicio)")
    lugar: str | None = Field(None, min_length=2, max_length=80, description="Barrio o vereda por nombre")
    tipo_lugar: TipoLugar | None = Field(None, description="Tipo del lugar, si el nombre se repite")
    lugar_id: Id | None = Field(None, description="Id del barrio o vereda (buscar_lugar)")
    sitio: str | None = Field(None, min_length=2, max_length=160, description="Dónde exactamente: caseta comunal, "
                                                                             "escuela…")
    tema: str | None = Field(None, min_length=1, max_length=160)
    descripcion: str | None = Field(None, min_length=1, max_length=4000)
    compromisos: str | None = Field(None, min_length=1, max_length=4000, description="Lo que se acordó")
    abierta_a_equipo: bool | None = Field(None, description="Que todo el equipo la vea (solo administrador y "
                                                            "coordinador)")
    # Huellas de los valores de antes que mostró la tarjeta (las pone `confirmar`, el modelo no las ve)
    huellas: SkipJsonSchema[dict[str, str] | None] = None

    @field_validator("huellas")
    @classmethod
    def _h(cls, v):
        return huellas_validas(v, CAMPOS_API_REUNION)

    @model_validator(mode="after")
    def _coherente(self):
        if self.lugar is not None and self.lugar_id is not None:
            raise ValueError("Use lugar (nombre) o lugar_id, no los dos")
        if self.tipo_lugar is not None and self.lugar is None:
            raise ValueError("tipo_lugar acompaña a lugar (el nombre)")
        if all(getattr(self, k) is None for k in ("titulo", "fecha", "hora", "hora_fin", "lugar", "lugar_id", "sitio",
                                                  "tema", "descripcion", "compromisos", "abierta_a_equipo")):
            raise ValueError("No hay cambios: indique al menos un dato de la reunión")
        return self


def _reunion_doc(db: Any, rid: int) -> dict | None:
    """La reunión de la base (no es de personas): verla por la API registraría como consultados a todos sus
    asistentes, y para la tarjeta de una edición no hace falta."""
    return db.reuniones.find_one({"_id": rid}, {"titulo": 1, "fecha": 1, "hora": 1, "hora_fin": 1, "lugar_id": 1,
                                               "lugar_texto": 1, "tema": 1, "descripcion": 1, "compromisos": 1,
                                               "abierta_a_equipo": 1, "creado_por_uid": 1})


async def _reunion_editable(ctx: Contexto, a: EditarReunionEntrada) -> dict:
    """La reunión, si quien conversa la puede editar (como la API: A y K todas; P, solo las suyas)."""
    fila = await _reunion_visible(ctx, a.reunion_id)
    if not ctx.quien.administra and not fila.get("propia"):
        raise ErrorHerramienta("Solo puede cambiar sus propias reuniones.", "permiso", estado=403)
    if a.abierta_a_equipo is not None and not ctx.quien.administra:
        raise ErrorHerramienta("Solo el administrador y el coordinador abren una reunión al equipo.", "permiso",
                               estado=403)
    x = await run_in_threadpool(_reunion_doc, ctx.db, a.reunion_id)
    if x is None:
        raise ErrorHerramienta(f"La reunión #{a.reunion_id} no existe.", "no_existe", estado=404)
    return x


def _vacio(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _mostrar_reunion(api: str, v: Any, nombres: dict[int, str]) -> str:
    if _vacio(v):
        return "(vacío)"
    if api == "fecha":
        return _fecha_legible(v)
    if api == "lugar_id":
        return f"{nombres.get(v, '(lugar borrado)')} (#{v})"
    if isinstance(v, bool):
        return _si_no(v)
    return str(v)


async def _plan_reunion(ctx: Contexto, x: dict, a: EditarReunionEntrada) -> tuple[list[tuple[str, str, Any, Any]],
                                                                                  dict[int, str]]:
    """[(campo de la API, etiqueta, antes, después)] de lo que cambia de verdad, y los nombres de los lugares."""
    nuevos: dict[str, Any] = {}
    nom = await nomenclatura(ctx) if (a.lugar is not None or a.lugar_id is not None or x.get("lugar_id")) else None
    for campo, api, _ in CAMPOS_REUNION:
        v = getattr(a, campo)
        if campo == "lugar_id" and (a.lugar is not None or a.lugar_id is not None):
            v = nom.resolver(a.lugar, a.lugar_id, a.tipo_lugar).id
        if v is not None:
            nuevos[api] = v
    nombres = {lg.id: lg.nombre for lg in (nom.por_id.values() if nom else ())}
    plan = []
    for _, api, etiqueta in CAMPOS_REUNION:
        if api in nuevos and nuevos[api] != (bool(x.get(api)) if api == "abierta_a_equipo" else x.get(api)):
            plan.append((api, etiqueta, x.get(api), nuevos[api]))
    hora = nuevos.get("hora", modelo.hora_valida(x.get("hora")) if x.get("hora") else None)
    hora_fin = nuevos.get("hora_fin", modelo.hora_valida(x.get("hora_fin")) if x.get("hora_fin") else None)
    if any(api in ("hora", "hora_fin") for api, *_ in plan) and hora_fin and (not hora or hora_fin <= hora):
        raise ErrorHerramienta("La hora de fin necesita la de inicio y va después de ella.", "invalido", estado=422,
                               detalle={"campo": "hora_fin"})
    return plan, nombres


async def _confirmar_editar_reunion(ctx: Contexto, a: EditarReunionEntrada) -> Confirmacion:
    x = await _reunion_editable(ctx, a)
    plan, nombres = await _plan_reunion(ctx, x, a)
    if not plan:
        raise ErrorHerramienta("La reunión ya tiene esos valores: no hay nada que cambiar.", "sin_cambios")
    clave = await _clave_huellas(ctx)
    a.huellas = {api: _huella(clave, f"reunion.{api}", antes) for api, _, antes, _ in plan}
    detalle = [("Reunión", f"{x.get('titulo')} ({_fecha_legible(x.get('fecha'))}) #{a.reunion_id}")]
    for api, etiqueta, antes, despues in plan:
        if api in ("descripcion", "compromisos") and not _vacio(antes):
            detalle.append((etiqueta, f"Antes: {antes}\n\nAhora: {despues}"))
        else:
            detalle.append((etiqueta, f"{_mostrar_reunion(api, antes, nombres)} → "
                                      f"{_mostrar_reunion(api, despues, nombres)}"))
    return Confirmacion("Editar una reunión", detalle,
                        "Solo cambian estos datos; los asistentes y sus acercamientos quedan como están.")


async def _editar_reunion(ctx: Contexto, a: EditarReunionEntrada) -> Resultado:
    x = await _reunion_editable(ctx, a)
    plan, _ = await _plan_reunion(ctx, x, a)
    if plan and a.huellas:
        clave = await _clave_huellas(ctx)
        cambiados = [api for api, _, antes, _ in plan if api in a.huellas
                     and _huella(clave, f"reunion.{api}", antes) != a.huellas[api]]
        if cambiados:
            raise ErrorHerramienta("Otra persona cambió la reunión después de que se armó la tarjeta: vuelva a leerla "
                                   "y, si sigue haciendo falta, proponga el cambio de nuevo.", "cambiada", estado=409,
                                   detalle={"campos": cambiados})
    if plan:  # PATCH: sin idempotencia en la API; si ya quedó como se pidió, no se escribe ni se audita otra vez
        d = await pedir(ctx, "PATCH", f"/api/reuniones/{a.reunion_id}", cuerpo={api: v for api, _, _, v in plan})
    else:
        d = {"id": a.reunion_id, **{k: x.get(k) for k in ("titulo", "fecha", "hora", "hora_fin", "tema")},
             "lugar_texto": x.get("lugar_texto")}
    d = d if isinstance(d, dict) else {}
    # La respuesta de la API trae los asistentes: al modelo le llega solo la reunión
    reunion = {"id": a.reunion_id, "titulo": _texto(d.get("titulo"), 160), "fecha": d.get("fecha"),
               "hora": d.get("hora"), "hora_fin": d.get("hora_fin"), "tema": _texto(d.get("tema"), 160),
               "lugar": _texto(d.get("lugar_nombre") or d.get("lugar_texto"), 120),
               "ruta": f"/reuniones/{a.reunion_id}"}
    contenido: dict[str, Any] = {"guardada": True, "cambios": [api for api, *_ in plan], "reunion": reunion}
    if not plan:
        contenido["ya_estaba"] = True
    return Resultado(contenido, f"Reunión #{a.reunion_id} actualizada" if plan else
                     f"La reunión #{a.reunion_id} ya estaba así", acciones=[{"tipo": "recargar"}])


EDITAR_REUNION = Herramienta(
    nombre="editar_reunion",
    descripcion=(
        "Propone cambiar datos de una reunión existente: título, fecha, horas (HH:MM de 24 horas), barrio o vereda "
        "(por nombre en `lugar` o con `lugar_id`), sitio exacto, tema, descripción, compromisos (lo que se acordó) y, "
        "solo el administrador y el coordinador, si está abierta al equipo. Pon solo lo que cambia, con el valor "
        "dictado; vaciar un dato se hace en el panel. El planillero edita solo las reuniones que creó; el "
        "administrador y el coordinador, todas. La tarjeta muestra «antes → después» y se guarda solo si la persona "
        "del equipo la aprueba. Los asistentes no cambian: para eso agregar_asistente y quitar_asistente."),
    entrada=EditarReunionEntrada, tipo="escritura", permisos=("reuniones.crear",), etiqueta="Editando la reunión",
    ejecutar=_editar_reunion, confirmar=_confirmar_editar_reunion, esquema=esquema(EditarReunionEntrada),
    mcp="escritura")


# ───────────────────────────── quitar_asistente ─────────────────────────────

class QuitarAsistenteEntrada(_Entrada):
    reunion_id: Id
    persona_id: Id


async def _confirmar_quitar(ctx: Contexto, a: QuitarAsistenteEntrada) -> Confirmacion:
    reu = await _reunion_visible(ctx, a.reunion_id)
    d = await _persona_tratable(ctx, a.persona_id)
    if not _ya_asiste(d, a.reunion_id):
        raise ErrorHerramienta("Esa persona no figura como asistente de esa reunión.", "no_es_asistente", estado=409)
    detalle = [("Reunión", f"{reu.get('titulo')} ({_fecha_legible(reu.get('fecha'))}) #{a.reunion_id}"),
               ("Persona", _persona(d))]
    return Confirmacion("Quitar un asistente de una reunión", detalle,
                        "Deja de figurar como asistente y se anula el acercamiento que dejó su asistencia.",
                        personas={a.persona_id})


async def _quitar(ctx: Contexto, a: QuitarAsistenteEntrada) -> Resultado:
    await _reunion_visible(ctx, a.reunion_id)
    d = await _persona_tratable(ctx, a.persona_id)  # pudo dejar de autorizar entre la tarjeta y la aprobación
    if not _ya_asiste(d, a.reunion_id):  # DELETE: sin idempotencia en la API; ya quitada, no se repite
        return Resultado({"quitado": True, "ya_estaba": True, "persona": {"id": a.persona_id}},
                         "Ya no figuraba como asistente", personas={a.persona_id})
    r = await pedir(ctx, "DELETE", f"/api/reuniones/{a.reunion_id}/asistentes/{a.persona_id}")
    r = r if isinstance(r, dict) else {}
    tratables = sum(1 for x in _lista(r.get("asistentes")) if x.get("consentimiento") != "no")  # como ver_reunion
    return Resultado({"quitado": True, "persona": {"id": a.persona_id, "nombre": d.get("nombre")},
                      "reunion": {"id": a.reunion_id, "titulo": _texto(r.get("titulo"), 160), "fecha": r.get("fecha"),
                                  "asistentes_total": tratables, "ruta": f"/reuniones/{a.reunion_id}"}},
                     "Asistente quitado", acciones=[{"tipo": "recargar"}], personas={a.persona_id})


QUITAR_ASISTENTE = Herramienta(
    nombre="quitar_asistente",
    descripcion=(
        "Propone quitar a una persona de los asistentes de una reunión (por ejemplo, se registró por error o en otra "
        "reunión). Necesita reunion_id y persona_id (de ver_reunion o listar_reuniones y buscar_personas). Se anula el "
        "acercamiento automático que dejó su asistencia. El planillero solo en las reuniones que ve (las suyas y las "
        "abiertas al equipo). No se usa con quien no autorizó el tratamiento de sus datos: eso se hace en la reunión "
        "del panel. Se guarda solo si la persona del equipo lo aprueba en la tarjeta."),
    entrada=QuitarAsistenteEntrada, tipo="escritura", permisos=("reuniones.asistentes",),
    etiqueta="Quitando el asistente", ejecutar=_quitar, confirmar=_confirmar_quitar,
    esquema=esquema(QuitarAsistenteEntrada), mcp="escritura")


HERRAMIENTAS: list[Herramienta] = [HISTORIAL, AUTORIZACIONES, REPORTAR_SITUACION, SOLICITUD, DUPLICADO, NO_DISPONIBLE,
                                   ACTUALIZACION, ESTADO_TELEFONO, ANULAR, EDITAR_REUNION, QUITAR_ASISTENTE]
