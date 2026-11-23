"""Herramientas del asistente para la analítica avanzada: `analizar` (un análisis de los que calcula el servidor) y
`diagnostico` (hallazgos ordenados por urgencia). Solo A y K (permiso `analitica.ver`); también por MCP con una clave
de alcance «analitica».

Por qué está hecho así:

* El cálculo es del servidor (`app/analitica.py`, `GET /api/analitica?consulta=<json>`), con la sesión de quien
  conversa: los mismos permisos, la misma base que Habitantes y las mismas reglas de privacidad que vería cualquier
  otra vía (sin quienes no autorizaron, «<5» y celdas complementarias ocultas, `{pocas}` con menos de 10 personas).
  El modelo no cuenta nada por su cuenta ni escribe los números del gráfico: el gráfico lo arma esta herramienta con
  las cifras ya protegidas (`grafico_de`) y lo valida `app/agente/grafico.py`; las celdas ocultas no van y la `nota`
  lo dice.
* La entrada es la misma `Consulta` del servidor (un modelo plano con `tipo` y la validación por tipo en un
  `model_validator`: una unión discriminada metería `oneOf` y `const` en el esquema), más el lugar por nombre, que se
  resuelve aquí con el nomenclátor (un nombre ambiguo vuelve con sus candidatos para que el modelo pregunte). Una
  etiqueta sensible se rechaza antes de contar.
* No sale ninguna persona (`Resultado.personas` vacío): solo agregados, nombres de lugares, puestos y usuarios del
  equipo. Los títulos de las reuniones pasan por `texto_libre` (los escribe una persona y pueden traer un número).
"""
from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import Field, model_validator
from starlette.concurrency import run_in_threadpool

from ... import analitica as motor
from .. import grafico, minimizar
from . import gestion
from .base import Contexto, Herramienta, Resultado

TIPOS_ANALIZAR = tuple(t for t in motor.TIPOS if t != "diagnostico")
# Dimensiones de orden natural (columnas); las demás son categorías (barras)
ORDINALES = frozenset({"rango_edad", "completitud", "intentos", "personas_hogar", "estrato", "asistencia", "mes_alta"})
PLAZO_DIAGNOSTICO = 120.0
NOTA_OCULTAS = "Sin los grupos ocultos por privacidad (de 1 a 4 personas, o que dejarían deducirlas)."
TOPE_GRAFICO = 40


# ───────────────────────────── Entrada ─────────────────────────────

class FiltrosAnalisis(motor.FiltrosConsulta):
    """Filtros de Habitantes (como mucho 3; edad y completitud en múltiplos de 5). El barrio o vereda va por nombre
    (`lugar`) o por id (`lugar_id`)."""
    lugar: str | None = Field(None, min_length=2, max_length=80,
                              description="Barrio o vereda por nombre; el servidor lo busca en el nomenclátor")
    tipo_lugar: gestion.TipoLugar | None = Field(None, description="Tipo del lugar, si el nombre se repite (con lugar)")

    @model_validator(mode="after")
    def _lugar(self):
        if self.lugar is not None and self.lugar_id is not None:
            raise ValueError("Use lugar (nombre) o lugar_id, no los dos")
        if self.tipo_lugar is not None and self.lugar is None:
            raise ValueError("tipo_lugar acompaña a lugar (el nombre)")
        return self


class AnalizarEntrada(motor.Consulta):
    """Un análisis: `tipo` y solo los parámetros de ese tipo."""
    tipo: Literal[TIPOS_ANALIZAR] = Field(..., description="Qué análisis (ver la descripción de la herramienta)")
    filtros: FiltrosAnalisis | None = Field(None, description="Filtros de Habitantes (como mucho 3)")


class DiagnosticoEntrada(gestion._Entrada):
    filtros: FiltrosAnalisis | None = Field(None, description="Para revisar solo una parte de la base (como mucho 3)")
    fecha_meta: motor.Fecha | None = Field(None, description="Fecha de la meta de cobertura (AAAA-MM-DD): con ella se "
                                                             "calcula si cada puesto llega al ritmo actual")
    meta_pct: int | None = Field(None, ge=1, le=100, description="Meta de cobertura por puesto en % (30)")


# ───────────────────────────── Llamada a la API ─────────────────────────────

async def _filtros(ctx: Contexto, f: FiltrosAnalisis | None) -> tuple[dict | None, dict]:
    """(filtros para la API, los mismos legibles para el modelo): el lugar por nombre resuelto a su id y la etiqueta
    revisada (que exista y no sea sensible) antes de contar."""
    if f is None:
        return None, {}
    datos = f.model_dump(exclude_none=True)
    legible = dict(datos)
    nom = gestion.Perezosa(ctx)
    if f.lugar is not None:
        lg = (await nom()).resolver(f.lugar, tipo=f.tipo_lugar)
        for x in (datos, legible):
            x.pop("lugar", None)
            x.pop("tipo_lugar", None)
        datos["lugar_id"], legible["lugar_id"] = lg.id, lg.legible()
    elif f.lugar_id:  # 0 = sin barrio ni vereda: no es un lugar del nomenclátor
        legible["lugar_id"] = (await nom()).por_id_o_error(f.lugar_id).legible()
    if f.etiqueta is not None:
        await run_in_threadpool(gestion._exigir_etiqueta, ctx.db, f.etiqueta)
    return datos, legible


async def consultar(ctx: Contexto, consulta: dict) -> Any:
    texto = json.dumps(consulta, ensure_ascii=False, separators=(",", ":"))
    return await gestion.pedir(ctx, "GET", "/api/analitica", params={"consulta": texto})


def _limpio(out: Any) -> Any:
    """Lo que el modelo recibe: los títulos de reuniones con `texto_libre` (texto que escribe una persona)."""
    if isinstance(out, dict):
        for x in out.get("reuniones") or []:
            if isinstance(x, dict) and isinstance(x.get("titulo"), str):
                x["titulo"] = minimizar.texto_libre(x["titulo"], 120)
    return out


# ───────────────────────────── Gráfico ─────────────────────────────

def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _items(filas: list[dict], etiqueta: str, valor: str, texto: str | None = None) -> tuple[list[dict], int]:
    items, ocultos = [], 0
    for f in filas:
        v = f.get(valor)
        if not _num(v):
            ocultos += 1
            continue
        it = {"etiqueta": str(f.get(etiqueta) if f.get(etiqueta) is not None else "")[:60] or "—", "valor": v}
        if texto and f.get(texto) is not None:
            it["texto"] = str(f[texto])[:40]
        items.append(it)
    return items[:TOPE_GRAFICO], ocultos


def _grafico(clase: str, titulo: str, unidad: str, items: list[dict], ocultos: int = 0,
             nota: str | None = None, motivo: str = NOTA_OCULTAS) -> dict | None:
    """`ocultos`: cuántos grupos no van (y `motivo`, por qué: la privacidad, salvo que se diga otra cosa)."""
    notas = [x for x in (motivo if ocultos else None, nota) if x]
    return grafico.validar({"tipo": "grafico", "clase": clase, "titulo": titulo, "unidad": unidad, "items": items,
                            **({"nota": " ".join(notas)} if notas else {})})


def grafico_de(out: Any) -> dict | None:
    """El gráfico de un resultado de la analítica, con las cifras que ya vienen protegidas: los grupos ocultos no van.
    None si no hay nada que dibujar (o el resultado es `{pocas}`)."""
    if not isinstance(out, dict) or out.get("pocas") or out.get("dispersas"):
        return None
    tipo = out.get("tipo")
    if tipo == "tabla" and len(out.get("dimensiones") or []) == 1:
        dim = out["dimensiones"][0]
        pct_ = next((m for m in out.get("metricas") or [] if m.startswith("pct_") or m == "completitud_media"), None)
        if pct_:
            items, ocultos = _items(out["filas"], "etiqueta", pct_)
            return _grafico("barras", f"{pct_.replace('_', ' ')} por {dim.replace('_', ' ')}",
                            "%" if pct_.startswith("pct") else "puntos", items, ocultos)
        items, ocultos = _items(out["filas"], "etiqueta", "personas")
        return _grafico("columnas" if dim in ORDINALES else "barras", f"Personas por {dim.replace('_', ' ')}",
                        "personas", items, ocultos)
    if tipo == "serie":
        puntos = list(out.get("puntos") or [])
        items = [{"etiqueta": p["periodo"], "valor": p["valor"]} for p in puntos if _num(p.get("valor"))]
        nota = None
        if len(items) > grafico.MAX_ITEMS:
            items, nota = items[-grafico.MAX_ITEMS:], f"Últimos {grafico.MAX_ITEMS} periodos."
        if out.get("desglose"):
            nota = " ".join(x for x in ("Total visible de cada periodo.", nota) if x)
            ocultos = sum(1 for p in puntos for v in (p.get("grupos") or {}).values() if not _num(v))
        else:
            ocultos = sum(1 for p in puntos if not _num(p.get("valor")))
        evento = (out.get("evento") or "").replace("_", " ").capitalize()
        return _grafico("serie", f"{evento} por {out.get('granularidad')}", out.get("evento") or "", items, ocultos,
                        nota)
    if tipo == "embudo":
        items, ocultos = _items(out.get("etapas") or [], "nombre", "personas")
        return _grafico("barras", "Embudo: de las personas vigentes al voto verificado", "personas", items, ocultos)
    if tipo == "cobertura":
        items, ocultos = _items(out.get("puestos") or [], "nombre", "cobertura_pct", "codigo")
        return _grafico("barras", f"Cobertura por puesto (meta {out.get('meta_pct')} %)", "%", items, ocultos)
    if tipo == "ritmo":
        items, ocultos = _items(out.get("puestos") or [], "nombre", "cobertura_proyectada_pct", "codigo")
        return _grafico("barras", f"Cobertura proyectada al {out.get('fecha_meta')} (meta {out.get('meta_pct')} %)",
                        "%", items, ocultos)
    if tipo == "brechas":
        items, _ = _items((out.get("lugares") or [])[:15], "nombre", "indice_atencion")
        return _grafico("barras", "Índice de atención (los más desatendidos primero)", "índice", items)
    if tipo == "equipo":
        items, _ = _items((out.get("usuarios") or [])[:15], "usuario", "acercamientos")
        return _grafico("barras", "Acercamientos por usuario", "acercamientos", [x for x in items if x["valor"]])
    if tipo == "calidad":
        items, ocultos = _items(out.get("faltan") or [], "etiqueta", "pct")
        return _grafico("barras", "Personas a las que les falta cada dato", "%", items, ocultos)
    if tipo == "cohortes":
        filas = out.get("cohortes") or []
        clave = "pct_abordadas_en_30_dias" if any(_num(f.get("pct_abordadas_en_30_dias")) for f in filas) \
            else "pct_contactadas"
        items, ocultos = _items(filas, "mes", clave)
        titulo = "Abordadas en 30 días por mes de alta" if clave.endswith("30_dias") else "Contactadas por mes de alta"
        return _grafico("columnas", titulo, "%", items, ocultos,
                        motivo="Sin los meses sin cifra (ocultos por privacidad o con menos de 30 días).")
    if tipo == "franjas":
        horas = [{**h, "hora": f"{h['hora']:02d}:00"} for h in out.get("por_hora") or []]
        items, ocultos = _items(horas, "hora", "tasa_util", "intentos")
        if items:
            return _grafico("columnas", "Tasa de contacto útil por hora", "%", items, ocultos,
                            motivo="Sin las horas con menos de 20 intentos (su tasa no es confiable).")
        # Con pocos intentos por hora todavía no hay tasas: al menos cuándo se llama
        items, _ = _items(horas, "hora", "intentos")
        return _grafico("columnas", "Intentos por hora (aún sin tasas: menos de 20 por hora)", "intentos", items)
    if tipo == "intentos":
        items, ocultos = _items([{**f, "n": f"Intento {f['intento']}"} for f in out.get("intentos") or []], "n",
                                "prob_contacto")
        return _grafico("columnas", "Probabilidad de contacto en cada intento", "%", items, ocultos,
                        motivo="Sin los intentos a los que llegaron menos de 20 personas.")
    if tipo == "captura":
        items, _ = _items(out.get("capturadores") or [], "usuario", "pct_telefono_equivocado", "fichas")
        return _grafico("barras", "Teléfonos equivocados por quien capturó", "%", items)
    if tipo == "comparar":
        filas = out.get("grupos") or []
        if out.get("metrica") == "tasa_contacto_util":
            items = [{"etiqueta": str(f["etiqueta"])[:60], "valor": f["tasa_util"]["periodo"],
                      "texto": f"antes {f['tasa_util']['referencia']} %"[:40]}
                     for f in filas if _num(f["tasa_util"]["periodo"])]
            return _grafico("barras", "Tasa de contacto útil en el periodo", "%", items[:TOPE_GRAFICO],
                            len(filas) - len(items))
        items = [{"etiqueta": str(f["etiqueta"])[:60], "valor": f["periodo"], "texto": f"antes {f['referencia']}"}
                 for f in filas if _num(f.get("periodo")) and _num(f.get("referencia"))]
        return _grafico("barras", f"{out.get('metrica', '').replace('_', ' ').capitalize()} en el periodo",
                        out.get("metrica") or "", items[:TOPE_GRAFICO], len(filas) - len(items))
    if tipo == "reuniones_efecto":
        ag = out.get("agregado") or {}
        items = [{"etiqueta": f"{m.replace('_', ' ').capitalize()} {cuando}", "valor": ag[m][k]}
                 for m in ("altas", "autorizaciones", "contactos_utiles") if m in ag
                 for k, cuando in (("antes", "antes"), ("despues", "después")) if _num(ag[m].get(k))]
        return _grafico("columnas", "4 semanas antes y después de las reuniones (agregado)", "", items,
                        nota="No prueba que la reunión lo causó.")
    if tipo == "diagnostico":
        sev: dict[str, int] = {}
        for x in out.get("hallazgos") or []:
            sev[x.get("severidad")] = sev.get(x.get("severidad"), 0) + 1
        items = [{"etiqueta": f"Urgencia {s}", "valor": sev[s]} for s in ("alta", "media", "baja") if sev.get(s)]
        return _grafico("apilada", "Hallazgos por urgencia", "hallazgos", items)
    return None


# ───────────────────────────── analizar ─────────────────────────────

def _resumen(out: Any) -> str:
    if not isinstance(out, dict):
        return "Análisis"
    if out.get("pocas"):
        return "Menos de 10 personas: sin cifras"
    if out.get("dispersas"):
        return "Grupos demasiado chicos: sin desglose"
    tipo = out.get("tipo")
    if tipo == "tabla":
        return f"Tabla por {' y '.join(out.get('dimensiones') or [])}: {len(out.get('filas') or [])} grupos"
    if tipo == "serie":
        return f"Serie de {out.get('evento')} por {out.get('granularidad')}"
    if tipo == "diagnostico":
        hs = out.get("hallazgos") or []
        altas = sum(1 for h in hs if h.get("severidad") == "alta")
        return f"{len(hs)} hallazgos" + (f" ({altas} de urgencia alta)" if altas else "")
    return {"embudo": "Embudo", "cobertura": "Cobertura por puesto", "brechas": "Lugares por atención",
            "equipo": "Trabajo del equipo", "calidad": "Calidad de los datos", "anomalias": "Anomalías",
            "cohortes": "Cohortes por mes de alta", "ritmo": "Ritmo por puesto", "franjas": "Franjas horarias",
            "intentos": "Intentos de contacto", "captura": "Calidad de captura", "comparar": "Comparación de periodos",
            "reuniones_efecto": "Antes y después de las reuniones"}.get(tipo, "Análisis")


def _resultado(out: Any, legible: dict) -> Resultado:
    out = _limpio(out)
    if isinstance(out, dict) and not out.get("pocas") and legible:
        out["filtros"] = legible
    if isinstance(out, dict) and out.get("pocas"):
        out = {**out, "nota": "Con estos filtros quedan menos de 10 personas: el panel no da cifras para no "
                              "identificar a nadie. Quite un filtro."}
    g = grafico_de(out)
    return Resultado(out, _resumen(out), [g] if g else [])


async def _analizar(ctx: Contexto, a: AnalizarEntrada) -> Resultado:
    filtros, legible = await _filtros(ctx, a.filtros)
    consulta = a.model_dump(exclude_none=True)
    consulta.pop("filtros", None)
    if filtros:
        consulta["filtros"] = filtros
    return _resultado(await consultar(ctx, consulta), legible)


async def _diagnostico(ctx: Contexto, a: DiagnosticoEntrada) -> Resultado:
    filtros, legible = await _filtros(ctx, a.filtros)
    consulta: dict[str, Any] = {"tipo": "diagnostico", **a.model_dump(exclude_none=True, exclude={"filtros"})}
    if filtros:
        consulta["filtros"] = filtros
    return _resultado(await consultar(ctx, consulta), legible)


ANALIZAR = Herramienta(
    nombre="analizar",
    descripcion=(
        "Calcula en el servidor un análisis agregado de la base (nunca personas) y muestra su gráfico en el chat. "
        "Tipos: tabla (personas y % por 1 o 2 dimensiones, con métricas como pct_con_cedula o pct_contacto_util), "
        "serie (un evento en el tiempo con tendencia y proyección), embudo (de vigentes a contacto útil y voto "
        "verificado, con la mayor caída), cobertura (registrados por puesto frente al censo), brechas (barrios y "
        "veredas más desatendidos), equipo (lo de cada usuario frente a la mediana), calidad, anomalias, cohortes "
        "(por mes de alta), ritmo (con fecha_meta: a qué cobertura llega cada puesto y cuántas altas por semana "
        "faltan), franjas (horas, días y canales que más contestan), intentos (cuándo dejar de insistir), captura "
        "(calidad por quien capturó), comparar (qué explica el cambio de una métrica entre dos periodos) y "
        "reuniones_efecto (4 semanas antes y después). Cada tipo admite solo sus parámetros. Filtros: como mucho 3, "
        "edad en múltiplos de 5. Las cifras no cuentan a quienes no autorizaron ni a fallecidos; de 1 a 4 personas "
        "salen «<5» y otras «oculta» para que no se deduzcan; un % sale null si dejaría ver a pocas personas; con "
        "menos de 10 responde pocas. Úsalo antes de opinar sobre números; cita las cifras como vienen y no describas "
        "el gráfico punto por punto: ya se ve."),
    entrada=AnalizarEntrada, tipo="lectura", permisos=("analitica.ver",), etiqueta="Analizando los datos",
    ejecutar=_analizar, esquema=gestion.esquema(AnalizarEntrada), mcp="analitica")

DIAGNOSTICO = Herramienta(
    nombre="diagnostico",
    descripcion=(
        "Revisa la base (toda o con hasta 3 filtros) y devuelve hallazgos ordenados por urgencia (alta, media, baja), "
        "cada uno con su evidencia en cifras, por qué importa, una acción concreta y, cuando se puede, un enlace a "
        "Habitantes con los filtros exactos y cuántas personas abre. Revisa solicitudes de titulares vencidas, "
        "autorizaciones por confirmar, autorizadas sin llamar, «volver a llamar» vencidos, la mayor caída del embudo, "
        "datos que faltan, cobertura por puesto (con fecha_meta, si se llega a la meta al ritmo actual), lugares "
        "desatendidos, cambios en la tasa de contacto útil, horas que más contestan, intentos, calidad de captura, "
        "duplicados, anomalías, cohortes y el efecto de las reuniones. Úsalo cuando pidan un panorama, qué está mal o "
        "qué hacer esta semana, y después profundiza con analizar. Presenta los hallazgos en su orden, con sus cifras "
        "tal como vienen y la acción; el enlace se abre en el panel. No cuenta a quienes no autorizaron ni a "
        "fallecidos; las cifras pequeñas salen «<5»."),
    entrada=DiagnosticoEntrada, tipo="lectura", permisos=("analitica.ver",), etiqueta="Diagnosticando la base",
    ejecutar=_diagnostico, esquema=gestion.esquema(DiagnosticoEntrada), plazo=PLAZO_DIAGNOSTICO, mcp="analitica")

HERRAMIENTAS: list[Herramienta] = [ANALIZAR, DIAGNOSTICO]
