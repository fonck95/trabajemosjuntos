"""Herramientas del asistente para las colas de Calidad de datos y los catálogos que las acompañan: coincidencias
(posibles duplicados), conflictos de cédula, situaciones reportadas, solicitudes de los titulares, importaciones,
puestos de votación y lugares escritos sin reconocer (lectura), y resolverlas con aprobación: unir o separar fichas
duplicadas con la vista previa de la ficha unida, resolver un conflicto de cédula, confirmar o revertir una situación,
actualizar una solicitud y agregar un alias a un barrio o vereda.

Por qué está hecho así:

* Todo pasa por `ctx.api` con la sesión de quien conversa: las rutas de Calidad son de A y K (`admin`,
  `calidad.ver`, `calidad.resolver`, `importar`) y la API rechaza a P y C aunque la herramienta se les ofreciera. Lo que
  se lee directo de la base no se le pasa al modelo: si una persona no autorizó (las filas de situaciones no lo dicen),
  el estado de los pares de un grupo y la vista previa de la unión (`unificacion.vista_previa`, la misma función del
  panel: no hay ruta para la vista previa de una unión con otra ficha conservada o con fichas excluidas), y el alias y
  los nombres del nomenclátor (no son de personas).
* Las respuestas de estas rutas traen de más (las fuentes reales, las listas, la cédula, los teléfonos y el correo
  completos, la fila importada entera): cada herramienta vuelve a hacer su lista blanca. De las coincidencias, solo la
  clave de cada señal, nunca su texto (una dice «la base general»); de los conflictos, el motivo, el estado, la fecha,
  la cédula enmascarada, las personas con `minimizar.fila`, la fuente solo si es trámites o planilla (si no,
  «otra_base») y de las dos cédulas escritas en la planilla solo si coinciden; de las solicitudes, nunca la persona ni
  la descripción (que alguien pidió suprimir sus datos es un dato suyo); de las importaciones, nada de las bases
  políticas (cédulas y general: ni los conteos ni los archivos). Con `agente_politicos` encendido para la vía
  (`Contexto.politicos`; estas rutas son de A y K, que las ven en el panel), la fuente real de un conflicto y, de las
  importaciones de esas bases, su tipo, su archivo y sus conteos (también los tipos marcados y los líderes
  asignados).
* De quien no autorizó, solo `minimizar.no_autorizo`: un grupo de duplicados o un conflicto que la incluye sale sin
  señales ni datos y no se resuelve desde el asistente (unir es tratar sus datos); las situaciones y los lugares sin
  reconocer no la cuentan. Por MCP esas filas no salen (queda su conteo).
* Escrituras: `confirmar` lee y arma la tarjeta (unir lleva la vista previa: qué valor queda en cada campo y qué pasa a
  datos alternos, con la cédula, los teléfonos y el correo enmascarados) y anota en `Confirmacion.personas` a todas
  las personas que muestra. `ejecutar` escribe una sola vez: ninguna de estas rutas respeta la `Idempotency-Key`, así
  que se vuelve a leer y no se escribe lo que ya quedó como se pidió. Al unir, la tarjeta guarda la huella (HMAC) de lo
  que mostró y la ficha que se conserva: si al aprobar el grupo cambió, ese grupo no se une.
"""
from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema
from starlette.concurrency import run_in_threadpool

from ... import acceso, modelo, unificacion
from ... import db as bd
from ...pipeline import texto as tx
from .. import minimizar
from .base import Confirmacion, Contexto, ErrorHerramienta, Herramienta, Resultado
from .fichas import ACCIONES_SEGUIMIENTO, fecha_de, no_autorizaron, nombres_del_nomenclator, sin_no_autorizo_por_mcp
from .gestion import (Id, Nomenclatura, _Entrada, _lista, _sin_repetidos, esquema, exigir_permiso, miles, nomenclatura,
                      pedir)
from .personas import _clave_huellas, _exigir_tratable, _ficha, _huella, _pedir, _persona

MAX_GRUPOS = 5             # grupos por tarjeta de unión: cada uno ocupa hasta 5 filas de la tarjeta (máximo 40)
MAX_MIEMBROS_TARJETA = 12  # fichas que se nombran en una fila de la tarjeta
SUGERENCIAS_LUGAR = 3      # lugares parecidos por cada texto sin reconocer
FUENTES_VISIBLES = ("tramites", "planilla")  # las únicas fuentes que se nombran; las demás son «otra_base»
ESTADOS_CONFLICTO = ("pendiente", "aplicado", "corregido", "descartado", "reportado")
MOTIVOS_CONFLICTO = {"nombre_distinto": "Misma cédula, otro nombre", "cedula_anterior": "Cédula anterior de una ficha",
                     "posible_digitacion": "Posible error de digitación", "dictada": "Cédula dictada al consultor"}
ESTADO_DE_DECISION = {"aplicar": "aplicado", "descartar": "descartado", "corregir": "corregido",
                      "reportar": "reportado"}
_CLAVE_GRUPO = re.compile(r"\d{1,12}(?:-\d{1,12}){0,%d}" % (unificacion.MAX_PARES_GRUPO - 1))
ACCIONES = list(ACCIONES_SEGUIMIENTO)


def _miembros_texto(miembros: list[dict]) -> str:
    nombres = [_persona(m) for m in miembros[:MAX_MIEMBROS_TARJETA]]
    resto = len(miembros) - len(nombres)
    return ", ".join(nombres) + (f" y {resto} más" if resto > 0 else "")


def _numero(v: Any) -> float | None:
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


# ───────────────────────────── coincidencias ─────────────────────────────

class CoincidenciasEntrada(_Entrada):
    nivel: Literal[unificacion.NIVELES] | None = Field(
        None, description="alta (se puede unir con confianza), media, baja (revisar una por una) o bloqueada")
    motivo: Literal[unificacion.MOTIVOS] | None = Field(None, description="Por qué se propusieron")
    persona_id: Id | None = Field(None, description="Solo el grupo que contiene a esta ficha")
    pagina: int = Field(1, ge=1, le=1000)
    por_pagina: int = Field(5, ge=1, le=10, description="Grupos por página")


GRUPO_CON_NO_AUTORIZO = ("Incluye a alguien que no autorizó el tratamiento de sus datos: el asistente no recibe sus "
                         "datos ni une o separa este grupo. Se revisa en Calidad de datos del panel.")
# Los avisos de la API traen nombres y el texto de las señales (alguno nombra una base política): se cambian por
# estos, con solo lo que dicen de la decisión
AVISOS_GRUPO = (
    (re.compile(r"^Tienen \d+ cédulas distintas"), "Tienen cédulas distintas: dos cédulas distintas nunca se unen. "
                                                    "Excluya las que sobran o sepárelas."),
    (re.compile(r"^Ya se marcó antes"), "Ya se había marcado que dos de estas fichas son personas distintas."),
    (re.compile(r"^Grupo grande"), "Grupo grande: suele ser una cadena por nombres comunes; revíselo con cuidado."),
    (re.compile(r"no tienen una coincidencia directa"), "Hay fichas sin coincidencia directa que quedarían unidas y "
                                                        "algo las contradice."),
)
OTRO_AVISO = "Hay otro aviso sobre este grupo: véalo en Calidad de datos."


def _avisos(avisos: Any) -> list[str]:
    out: list[str] = []
    for a in avisos if isinstance(avisos, list) else []:
        texto = next((t for patron, t in AVISOS_GRUPO if isinstance(a, str) and patron.search(a)), OTRO_AVISO)
        if "no autorizó" in str(a):
            continue  # ese grupo ya sale sin datos (`GRUPO_CON_NO_AUTORIZO`)
        if texto not in out:
            out.append(texto)
    return out


def miembro_para_modelo(m: dict, lugares: frozenset[str]) -> dict:
    """Una ficha del grupo (la API la trae completa para A y K): lista blanca, con la cédula y el teléfono
    enmascarados y sin fuentes, listas, procedencia, correo, dirección ni fecha de nacimiento."""
    if m.get("consentimiento") == "no":
        return minimizar.no_autorizo({"id": m.get("id"), "nombre": m.get("nombre"), "lugar": m.get("lugar")}, lugares)
    tels = [t for t in m.get("telefonos") or [] if t]
    edad = m.get("edad") if isinstance(m.get("edad"), int) and not isinstance(m.get("edad"), bool) else None
    menor = edad is not None and edad < 18
    out = {"id": m.get("id"), "nombre": m.get("nombre"), "tiene_cedula": bool(m.get("cedula")),
           "cedula_ult3": acceso.enmascarar_cedula(m.get("cedula")), "telefonos_n": len(tels),
           "telefono_mascara": None if (menor or not tels) else acceso.enmascarar_telefono(tels[0]),
           "tiene_correo": bool(m.get("correo")), "tiene_direccion": bool(m.get("direccion")),
           "lugar": minimizar.texto_libre(m.get("lugar"), minimizar.LUGAR_MAX) if m.get("lugar") else None,
           "sexo": m.get("sexo"), "edad": edad, "completitud": m.get("completitud"),
           "consentimiento": m.get("consentimiento"),
           "tramites_n": m.get("tramites") if isinstance(m.get("tramites"), int) else None}
    return {k: v for k, v in out.items() if v is not None}


def _claves(senales: Any) -> list[str]:
    return [str(s["clave"]) for s in senales if isinstance(s, dict) and s.get("clave")] if isinstance(senales,
                                                                                                    list) else []


def _par(p: dict) -> dict:
    out: dict[str, Any] = {"id": p.get("id"), "fichas": [p.get("a"), p.get("b")], "nivel": p.get("nivel"),
                           "motivo": p.get("motivo"), "a_favor": _claves(p.get("a_favor")),
                           "en_contra": _claves(p.get("en_contra"))}
    if _numero(p.get("puntaje")) is not None:
        out["parecido_nombre"] = round(p["puntaje"] * 100)
    if isinstance(p.get("nota"), str) and p["nota"].strip():
        out["nota"] = minimizar.texto_libre(p["nota"], 200)
    return out


def grupo_para_modelo(g: dict, lugares: frozenset[str]) -> dict:
    miembros = _lista(g.get("miembros"))
    out: dict[str, Any] = {"clave": g.get("clave"), "miembros": [miembro_para_modelo(m, lugares) for m in miembros]}
    if any(m.get("consentimiento") == "no" for m in miembros):
        # Las señales, el nivel y los avisos se calcularon con sus datos: no van
        return {**out, "no_autorizo": True, "nota": GRUPO_CON_NO_AUTORIZO}
    out.update({"nivel": g.get("nivel"), "motivos": [m for m in g.get("motivos") or [] if isinstance(m, str)],
                "conservaria": g.get("destino"), "pares": [_par(p) for p in _lista(g.get("pares"))]})
    if _numero(g.get("puntaje")) is not None:
        out["parecido_nombre"] = round(g["puntaje"] * 100)
    avisos = _avisos(g.get("avisos"))
    if avisos:
        out["avisos"] = avisos
    return out


NOTA_COINCIDENCIAS = ("Cada grupo son fichas que podrían ser la misma persona. `a_favor` y `en_contra` son las claves "
                      "de las señales (mismo_telefono, misma_fecha, nombre_igual, sexo_distinto, edad_distinta…). "
                      "`conservaria`: la ficha que se conserva al unir si no se elige otra. Unir o separar: "
                      "resolver_coincidencias, con la clave del grupo, solo si la persona del equipo lo decide.")


async def _coincidencias(ctx: Contexto, a: CoincidenciasEntrada) -> Resultado:
    params = {"nivel": a.nivel, "motivo": a.motivo, "persona": a.persona_id, "pagina": a.pagina,
              "por_pagina": a.por_pagina}
    d = await pedir(ctx, "GET", "/api/coincidencias/grupos", params=params)
    d = d if isinstance(d, dict) else {}
    lugares = await nombres_del_nomenclator(ctx)
    grupos = [grupo_para_modelo(g, lugares) for g in _lista(d.get("grupos"))]
    grupos, ocultos = sin_no_autorizo_por_mcp(ctx, grupos, lambda g: g.get("no_autorizo"))
    total = int(d.get("total") or 0)
    pp = int(d.get("por_pagina") or a.por_pagina)
    out: dict[str, Any] = {"total": total, "pagina": a.pagina, "paginas": max(1, -(-total // pp)),
                           "niveles": d.get("niveles") if isinstance(d.get("niveles"), dict) else {},
                           "grupos": grupos, "nota": NOTA_COINCIDENCIAS, "ruta": "/calidad?p=coincidencias"}
    if ocultos:
        out["con_quien_no_autorizo"] = ocultos
    personas = {m["id"] for g in grupos for m in g["miembros"] if isinstance(m.get("id"), int)}
    return Resultado(out, "Sin coincidencias pendientes" if not total else
                     f"{miles(total)} grupo{'s' if total != 1 else ''} de posibles duplicados", personas=personas)


COINCIDENCIAS = Herramienta(
    nombre="coincidencias",
    descripcion=(
        "Grupos de posibles fichas duplicadas pendientes de revisar (Calidad de datos > Coincidencias), del más "
        "confiable al menos: cada grupo con su `clave`, su nivel (alta, media, baja o bloqueada), los motivos, las "
        "fichas (nombre, cédula y teléfono enmascarados, barrio o vereda, sexo, edad, completitud), los pares con las "
        "claves de sus señales a favor y en contra, los avisos y qué ficha se conservaría al unir (`conservaria`). "
        "Filtra por nivel, motivo o una ficha (`persona_id`). Úsala antes de proponer resolver_coincidencias y para "
        "explicarle a la persona del equipo por qué parecen la misma persona. Un grupo con alguien que no autorizó "
        "sale solo con quiénes son y se revisa en el panel. Solo administrador y coordinador."),
    entrada=CoincidenciasEntrada, tipo="lectura", permisos=("admin",), etiqueta="Revisando las coincidencias",
    ejecutar=_coincidencias, esquema=esquema(CoincidenciasEntrada), mcp="lectura")


# ───────────────────────────── resolver_coincidencias ─────────────────────────────

class GrupoDecision(_Entrada):
    clave: str = Field(..., min_length=1, max_length=800, description="La `clave` del grupo, tal como la da "
                                                                      "coincidencias")
    decision: Literal["unir", "separar"] = Field(..., description="unir: son la misma persona; separar: son personas "
                                                                  "distintas")
    conservar: Id | None = Field(None, description="Con unir: la ficha que se conserva (sin esto, `conservaria`)")
    excluir: list[Id] = Field(default_factory=list, max_length=unificacion.MAX_EXCLUIR,
                              description="Con unir: fichas del grupo que NO son la misma persona (quedan aparte)")

    @field_validator("clave")
    @classmethod
    def _clave(cls, v):
        if not _CLAVE_GRUPO.fullmatch(v):
            raise ValueError("Clave no válida: use la `clave` del grupo que da coincidencias (números con guiones)")
        return v

    @field_validator("excluir")
    @classmethod
    def _e(cls, v):
        return _sin_repetidos(v) or []

    @model_validator(mode="after")
    def _coherente(self):
        if self.decision == "separar" and (self.conservar is not None or self.excluir):
            raise ValueError("conservar y excluir solo van con unir")
        if self.conservar is not None and self.conservar in self.excluir:
            raise ValueError("La ficha que se conserva no puede estar en excluir")
        return self


def pares_de(clave: str) -> list[int]:
    return [int(x) for x in clave.split("-")]


def _previas_validas(v: dict | None) -> dict | None:
    if v is None:
        return v
    if len(v) > MAX_GRUPOS or any(
            not _CLAVE_GRUPO.fullmatch(str(k)) or not isinstance(x, dict) or set(x) != {"huella", "destino"}
            or not re.fullmatch(r"[0-9a-f]{24}", str(x.get("huella"))) or not isinstance(x.get("destino"), int)
            or isinstance(x.get("destino"), bool) for k, x in v.items()):
        raise ValueError("previas no válidas")
    return v


class ResolverCoincidenciasEntrada(_Entrada):
    grupos: list[GrupoDecision] = Field(..., min_length=1, max_length=MAX_GRUPOS,
                                        description="Los grupos que la persona del equipo decidió (hasta 5)")
    # Lo que mostró la tarjeta de cada grupo (huella de su estado y la ficha que se conserva): lo pone `confirmar`, el
    # modelo no lo ve. Al aprobar, un grupo que cambió no se une
    previas: SkipJsonSchema[dict[str, dict[str, Any]] | None] = None

    @field_validator("previas")
    @classmethod
    def _p(cls, v):
        return _previas_validas(v)

    @model_validator(mode="after")
    def _distintos(self):
        claves = [g.clave for g in self.grupos]
        if len(set(claves)) != len(claves):
            raise ValueError("Un grupo va una sola vez")
        if len({p for c in claves for p in pares_de(c)}) != sum(len(pares_de(c)) for c in claves):
            raise ValueError("Dos grupos comparten pares: use la clave de cada grupo tal como la da coincidencias")
        return self


def _pares_guardados(db: Any, ids: list[int]) -> list[dict]:
    return list(db.coincidencias.find({"_id": {"$in": ids}}, {"persona_id": 1, "candidato_id": 1, "estado": 1,
                                                               "conservada": 1}))


def _conexas(ids: set[int], pares: list[dict]) -> bool:
    """¿Las fichas `ids` quedan conectadas solo con los pares entre ellas? (como `unificacion._conexas`)."""
    padre = {i: i for i in ids}

    def raiz(i: int) -> int:
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    for c in pares:
        a, b = c.get("persona_id"), c.get("candidato_id")
        if a in padre and b in padre:
            padre[raiz(a)] = raiz(b)
    return len({raiz(i) for i in ids}) <= 1


def _estado_grupo(db: Any, g: GrupoDecision) -> dict:
    """El estado del grupo según la base, para la tarjeta y para saber al aprobar si cambió: sus pares, sus fichas
    activas, las que se unen, la ficha que se conserva (como `unificacion.resolver_grupo`), la vista previa de la ficha
    unida (`unificacion.vista_previa`) y los motivos por los que no se podría unir."""
    pares = _pares_guardados(db, pares_de(g.clave))
    miembros = sorted({c["persona_id"] for c in pares} | {c["candidato_id"] for c in pares})
    fichas = unificacion.cargar_fichas(db, miembros)
    incluidas = [i for i in miembros if i not in set(g.excluir)]
    problema = None
    if len(pares) != len(pares_de(g.clave)) or any(c.get("estado") != "pendiente" for c in pares) \
            or set(fichas) != set(miembros):
        problema = "cambio"
    elif not set(g.excluir) <= set(miembros) or (g.conservar is not None and g.conservar not in incluidas):
        problema = "fuera_del_grupo"
    destino, vista = None, []
    if problema is None and g.decision == "unir":
        if not incluidas:
            problema = "no_conexo"
        elif len({fichas[i]["cedula"] for i in incluidas if fichas[i].get("cedula")}) > 1:
            problema = "cedulas_distintas"
        elif any(r <= set(incluidas) for r in unificacion.rechazos_entre(db, incluidas)):
            problema = "rechazada_antes"
        elif not _conexas(set(incluidas), pares):
            problema = "no_conexo"
        else:
            destino = g.conservar if g.conservar is not None else unificacion.destino_de(fichas[i] for i in incluidas)
            vista = unificacion.vista_previa([fichas[i] for i in incluidas], destino,
                                             unificacion.nombres_de_lugares(db))
    no = sorted(i for i in miembros if (fichas.get(i) or {}).get("consentimiento") == "no")
    firma = json.dumps({"pares": sorted((c["_id"], c.get("estado")) for c in pares), "miembros": miembros,
                        "decision": g.decision, "excluir": sorted(g.excluir), "destino": destino, "vista": vista,
                        "consentimientos": no}, ensure_ascii=False, sort_keys=True, default=str)
    return {"pares": pares, "miembros": miembros, "fichas": fichas, "incluidas": incluidas, "destino": destino,
            "vista": vista, "problema": problema, "no_autorizaron": no, "firma": firma}


MENSAJES_LOTE = {
    "cambio": "El grupo cambió (se resolvió, o una ficha se unió o se suprimió): vuelva a consultarlo con "
              "coincidencias.",
    "fuera_del_grupo": "La ficha que se conserva o alguna de las excluidas no está en el grupo.",
    "cedulas_distintas": "Tienen cédulas distintas: dos cédulas distintas nunca se unen. Excluya las que sobran o "
                         "sepárelas.",
    "rechazada_antes": "Ya se había marcado que dos de estas fichas son personas distintas: excluya una o sepárelas.",
    "no_conexo": "Sin las fichas excluidas, las que quedan no tienen una coincidencia directa: únalas por separado.",
    "conservar_invalida": "La ficha que se iba a conservar no está entre las que se unen.",
    "parcial": "Se unieron algunas fichas y la siguiente no se pudo unir: revise el grupo en Calidad de datos.",
    "cambiada": "El grupo cambió después de que se armó la tarjeta (otra ficha, otra decisión o datos distintos): no "
                "se tocó. Vuelva a consultarlo y proponga de nuevo.",
    "no_autorizo": GRUPO_CON_NO_AUTORIZO,
}


def _error_grupo(codigo: str, clave: str) -> ErrorHerramienta:
    estado = 409 if codigo in ("cambio", "cambiada", "rechazada_antes", "cedulas_distintas") else 422
    if codigo == "no_autorizo":
        return ErrorHerramienta(GRUPO_CON_NO_AUTORIZO, "no_contactable", estado=409, detalle={"clave": clave})
    return ErrorHerramienta(MENSAJES_LOTE.get(codigo, MENSAJES_LOTE["cambio"]), codigo, estado=estado,
                            detalle={"clave": clave})


async def _grupo_de_la_api(ctx: Contexto, clave: str) -> dict:
    """El grupo tal como lo muestra Calidad de datos (`GET /api/coincidencias/grupos`, solo A y K): con su clave
    exacta. Si cambió (se resolvió, o se le sumaron o quitaron pares), error: el modelo lo vuelve a consultar."""
    pares = await run_in_threadpool(_pares_guardados, ctx.db, pares_de(clave)[:1])
    if not pares:
        raise _error_grupo("cambio", clave)
    d = await pedir(ctx, "GET", "/api/coincidencias/grupos",
                    params={"persona": pares[0]["persona_id"], "por_pagina": unificacion.TOPE_POR_PAGINA})
    d = d if isinstance(d, dict) else {}
    g = next((x for x in _lista(d.get("grupos")) if x.get("clave") == clave), None)
    if g is None:
        raise _error_grupo("cambio", clave)
    return g


def _valor_tarjeta(campo: str, v: Any) -> str:
    """Un valor de la vista previa para la tarjeta (que se guarda con la conversación): la cédula y los teléfonos
    enmascarados como en el resto del asistente, y el correo solo como que lo tiene."""
    if campo == "cedula":
        return acceso.enmascarar_cedula(v) or "(vacía)"
    if campo == "telefonos":
        return ", ".join(acceso.enmascarar_telefono(n.strip()) or "" for n in str(v).split(",") if n.strip())
    if campo == "correo":
        return "registrado"
    if campo == "sexo":
        return modelo.SEXOS.get(v, str(v))
    return str(v)


def _filas_union(i: int, g: GrupoDecision, api: dict, estado: dict) -> list[tuple[str, str]]:
    por_id = {m.get("id"): m for m in _lista(api.get("miembros"))}
    nombre = {k: _persona(m) for k, m in por_id.items()}
    if g.decision == "separar":
        return [(f"Grupo {i}: son personas distintas",
                 _miembros_texto([por_id[k] for k in estado["miembros"] if k in por_id]) + ": quedan como personas "
                 "distintas y no se vuelven a proponer juntas")]
    filas = [(f"Grupo {i}: unir (nivel {api.get('nivel')})",
              _miembros_texto([por_id[k] for k in estado["incluidas"] if k in por_id])),
             ("Se conserva", nombre.get(estado["destino"], f"#{estado['destino']}"))]
    queda = [f"{f['etiqueta']}: {_valor_tarjeta(f['campo'], f['valor'])}" for f in estado["vista"]
             if f.get("valor") is not None]
    filas.append(("Quedaría", " · ".join(queda) or "(sin datos)"))
    alternos = [f"{f['etiqueta']}: {_valor_tarjeta(f['campo'], o['valor'])} (de #{o.get('de')})"
                for f in estado["vista"] for o in f.get("otros") or [] if o.get("valor") is not None]
    if alternos:
        filas.append(("Pasan a datos alternos", " · ".join(alternos)))
    if g.excluir:
        filas.append(("Quedan aparte (son otra persona)", _miembros_texto([por_id[k] for k in g.excluir
                                                                            if k in por_id])))
    return filas


AVISO_UNIR = ("Unir no se deshace desde el asistente: la ficha conservada se queda con los datos, las autorizaciones, "
              "los acercamientos y las asistencias de las otras, y lo distinto pasa a datos alternos. Cédulas y "
              "teléfonos van enmascarados: compárelos en Calidad de datos si hace falta.")
AVISO_SEPARAR = "Las fichas quedan como personas distintas: la importación no las vuelve a proponer juntas."


async def _confirmar_resolver(ctx: Contexto, a: ResolverCoincidenciasEntrada) -> Confirmacion:
    exigir_permiso(ctx, "admin", "Solo el administrador y el coordinador resuelven coincidencias.")
    clave_h = await _clave_huellas(ctx)
    detalle: list[tuple[str, str]] = []
    personas: set[int] = set()
    previas: dict[str, dict] = {}
    for i, g in enumerate(a.grupos, 1):
        api = await _grupo_de_la_api(ctx, g.clave)
        miembros = _lista(api.get("miembros"))
        personas |= {m["id"] for m in miembros if isinstance(m.get("id"), int)}
        if any(m.get("consentimiento") == "no" for m in miembros):
            raise _error_grupo("no_autorizo", g.clave)
        estado = await run_in_threadpool(_estado_grupo, ctx.db, g)
        if estado["problema"]:
            raise _error_grupo(estado["problema"], g.clave)
        detalle += _filas_union(i, g, api, estado)
        previas[g.clave] = {"huella": _huella(clave_h, f"grupo.{g.clave}", estado["firma"]),
                            "destino": estado["destino"] if estado["destino"] is not None else 0}
    a.previas = previas
    unir = any(g.decision == "unir" for g in a.grupos)
    n = len(a.grupos)
    titulo = (("Unir fichas duplicadas" if all(g.decision == "unir" for g in a.grupos) else
               "Resolver coincidencias") if unir else "Marcar como personas distintas")
    return Confirmacion(f"{titulo} ({n} grupo{'s' if n != 1 else ''})", detalle, AVISO_UNIR if unir else AVISO_SEPARAR,
                        personas=personas)


def _ya_resuelto(db: Any, g: GrupoDecision, previa: dict | None) -> str | None:
    """'hecho' si el grupo ya quedó como se pidió (un reintento de esta misma aprobación), 'otro' si se resolvió de
    otra forma y None si sigue pendiente (la ruta en lote no tiene idempotencia)."""
    pares = _pares_guardados(db, pares_de(g.clave))
    if not pares or any(c.get("estado") == "pendiente" for c in pares):
        return None if pares else "otro"
    if g.decision == "separar":
        return "hecho" if all(c.get("estado") == "rechazada" for c in pares) else "otro"
    destino = (previa or {}).get("destino")
    aceptadas = [c for c in pares if c.get("estado") == "aceptada"]
    return "hecho" if aceptadas and all(c.get("conservada") == destino for c in aceptadas) else "otro"


async def _resolver(ctx: Contexto, a: ResolverCoincidenciasEntrada) -> Resultado:
    exigir_permiso(ctx, "admin", "Solo el administrador y el coordinador resuelven coincidencias.")
    clave_h = await _clave_huellas(ctx)
    resultados: dict[str, dict] = {}
    enviar: list[tuple[GrupoDecision, dict]] = []
    personas: set[int] = set()
    for g in a.grupos:
        previa = (a.previas or {}).get(g.clave)
        ya = await run_in_threadpool(_ya_resuelto, ctx.db, g, previa)
        if ya == "hecho":
            resultados[g.clave] = {"clave": g.clave, "ok": True, "ya_estaba": True, "decision": g.decision,
                                   **({"conservada": previa["destino"]} if g.decision == "unir" and previa else {})}
            continue
        if ya == "otro":
            resultados[g.clave] = {"clave": g.clave, "ok": False, "codigo": "cambio",
                                   "mensaje": MENSAJES_LOTE["cambio"]}
            continue
        estado = await run_in_threadpool(_estado_grupo, ctx.db, g)
        personas |= set(estado["miembros"])
        if estado["no_autorizaron"]:
            codigo = "no_autorizo"
        elif estado["problema"]:
            codigo = estado["problema"]
        elif previa is None or _huella(clave_h, f"grupo.{g.clave}", estado["firma"]) != previa["huella"]:
            codigo = "cambiada"  # sin tarjeta, o el grupo no es el que mostró: no se toca
        else:
            codigo = None
        if codigo:
            resultados[g.clave] = {"clave": g.clave, "ok": False, "codigo": codigo, "mensaje": MENSAJES_LOTE[codigo]}
            continue
        enviar.append((g, estado))
    if enviar:
        cuerpo = {"grupos": [{"pares": pares_de(g.clave), "decision": g.decision, "excluir": g.excluir,
                              **({"conservar": e["destino"]} if g.decision == "unir" else {})} for g, e in enviar]}
        r = await pedir(ctx, "POST", "/api/coincidencias/lote", cuerpo=cuerpo)
        lote = _lista((r if isinstance(r, dict) else {}).get("resultados"))
        for k, (g, _) in enumerate(enviar):
            x = lote[k] if k < len(lote) else {"ok": False, "codigo": "cambio"}
            if x.get("ok"):
                resultados[g.clave] = {"clave": g.clave, "ok": True, "decision": g.decision,
                                       **{c: x[c] for c in ("conservada", "unidas", "separadas") if c in x}}
            else:
                codigo = str(x.get("codigo") or "cambio")
                resultados[g.clave] = {"clave": g.clave, "ok": False, "codigo": codigo,
                                       "mensaje": MENSAJES_LOTE.get(codigo, MENSAJES_LOTE["cambio"]),
                                       **{c: x[c] for c in ("conservada", "unidas") if c in x}}
    salida = [resultados[g.clave] for g in a.grupos]
    unidas = sum(int(x.get("unidas") or 0) for x in salida)
    separadas = sum(int(x.get("separadas") or 0) for x in salida)
    errores = sum(not x["ok"] for x in salida)
    personas |= {x["conservada"] for x in salida if isinstance(x.get("conservada"), int)}
    resumen = (f"{unidas} ficha{'s' if unidas != 1 else ''} unida{'s' if unidas != 1 else ''}"
               f" · {separadas} par{'es' if separadas != 1 else ''} separado{'s' if separadas != 1 else ''}"
               + (f" · {errores} grupo{'s' if errores != 1 else ''} sin resolver" if errores else ""))
    return Resultado({"resultados": salida, "unidas": unidas, "separadas": separadas, "errores": errores}, resumen,
                     list(ACCIONES), personas=personas)


RESOLVER_COINCIDENCIAS = Herramienta(
    nombre="resolver_coincidencias",
    descripcion=(
        "Propone resolver grupos de posibles duplicados (hasta 5 por tarjeta), con la `clave` de cada grupo tal como "
        "la da coincidencias: `unir` (son la misma persona: las fichas se unen en una, la que se conserva) o `separar` "
        "(son personas distintas). Al unir puedes elegir `conservar` (si no, la que propone el panel) y `excluir` las "
        "que no son la misma persona. La tarjeta muestra la vista previa: qué ficha queda, qué valor queda en cada "
        "campo y qué pasa a datos alternos. Une solo lo que la persona del equipo decidió después de ver las fichas: "
        "nunca supongas que dos fichas son la misma persona; con nivel media o baja, pide que lo revise. Dos cédulas "
        "distintas nunca se unen. Un grupo con alguien que no autorizó no se resuelve aquí. Unir no se deshace desde "
        "el asistente. Solo administrador y coordinador, con su aprobación."),
    entrada=ResolverCoincidenciasEntrada, tipo="escritura", permisos=("admin",), etiqueta="Resolviendo coincidencias",
    ejecutar=_resolver, confirmar=_confirmar_resolver, esquema=esquema(ResolverCoincidenciasEntrada), plazo=160,
    mcp="escritura")


# ───────────────────────────── conflictos_cedula ─────────────────────────────

class ConflictosEntrada(_Entrada):
    estado: Literal[ESTADOS_CONFLICTO] = Field("pendiente", description="pendiente (por defecto) o ya resueltos")
    motivo: Literal[tuple(MOTIVOS_CONFLICTO)] | None = None
    limite: int = Field(20, ge=1, le=50)


def _decisiones(c: dict) -> list[str]:
    """Las decisiones que la interfaz ofrece para el conflicto (`calidad.js`)."""
    if c.get("motivo") == "posible_digitacion":
        return ["corregir", "descartar"]
    if c.get("motivo") == "dictada" and c.get("duena"):
        return ["reportar", "descartar"]
    return ["aplicar", "descartar"]


def _involucradas(c: dict) -> list[tuple[str, dict]]:
    return [(rol, c[rol]) for rol in ("persona", "otra_persona", "duena") if isinstance(c.get(rol), dict)]


def conflicto_para_modelo(c: dict, lugares: frozenset[str], politicos: bool = False) -> dict:
    """Un conflicto de cédula: lista blanca. Las personas con `minimizar.fila`; la cédula y la de la fila
    enmascaradas; la fuente solo si es trámites o planilla («otra_base» si no: cédulas y general revelan una base
    política), o la real con `politicos`; de las dos cédulas escritas en la planilla, solo si coinciden."""
    out: dict[str, Any] = {"id": c.get("id"), "motivo": c.get("motivo"), "estado": c.get("estado"),
                           "fecha": fecha_de(c.get("creado_en"))}
    involucradas = _involucradas(c)
    for rol, p in involucradas:
        out[rol] = minimizar.fila(p, lugares)
    if c.get("persona") is None:
        out["ficha_activa"] = False
    if any(p.get("consentimiento") == "no" for _, p in involucradas):
        return {**out, "no_autorizo": True, "nota": "Incluye a alguien que no autorizó el tratamiento de sus datos: se "
                                                    "resuelve en Calidad de datos del panel."}
    out["cedula_ult3"] = acceso.enmascarar_cedula(c.get("cedula"))
    if c.get("motivo") != "dictada":
        visible = c.get("fuente") in FUENTES_VISIBLES or (politicos and isinstance(c.get("fuente"), str))
        out["fuente"] = c.get("fuente") if visible else "otra_base"
    reg = c.get("registro") if isinstance(c.get("registro"), dict) else {}
    if c.get("motivo") != "dictada" and reg:
        fila: dict[str, Any] = {"nombre": minimizar.texto_libre(reg.get("nombre"), 160),
                                "cedula_ult3": acceso.enmascarar_cedula(reg.get("cedula")), "sexo": reg.get("sexo"),
                                "edad": reg.get("edad") if isinstance(reg.get("edad"), int) else None,
                                "lugar": minimizar.texto_libre(reg.get("lugar_texto"), minimizar.LUGAR_MAX),
                                "telefonos_n": len(reg.get("telefonos") or []), "numero_fila": reg.get("fila")}
        digitada, repetida = reg.get("cedula_digitada"), reg.get("cedula_repetida")
        if digitada or repetida:
            fila["cedulas_coinciden"] = bool(digitada and repetida and digitada == repetida)
        out["fila"] = {k: v for k, v in fila.items() if v is not None}
    if _numero(c.get("puntaje_nombre")) is not None:
        out["parecido_nombre"] = round(c["puntaje_nombre"] * 100)
    if c.get("estado") == "pendiente":
        out["decisiones"] = _decisiones(c)
    elif isinstance(c.get("resolucion"), dict):
        out["decision"] = c["resolucion"].get("decision")
    return out


async def _conflictos(ctx: Contexto, a: ConflictosEntrada) -> Resultado:
    lista = _lista(await pedir(ctx, "GET", "/api/conflictos", params={"estado": a.estado}))
    if a.motivo:
        lista = [c for c in lista if c.get("motivo") == a.motivo]
    lugares = await nombres_del_nomenclator(ctx)
    politicos = ctx.quien.administra and ctx.politicos()
    filas = [conflicto_para_modelo(c, lugares, politicos) for c in lista]
    filas, ocultos = sin_no_autorizo_por_mcp(ctx, filas, lambda c: c.get("no_autorizo"))
    mostradas = filas[:a.limite]
    out: dict[str, Any] = {"total": len(filas), "mostrados": len(mostradas), "conflictos": mostradas,
                           "motivos": MOTIVOS_CONFLICTO, "ruta": "/calidad?p=conflictos",
                           "nota": ("Ninguno mezcla datos hasta que se decide. Para resolverlo: resolver_conflicto con "
                                    "una de sus `decisiones`.")}
    if ocultos:
        out["con_quien_no_autorizo"] = ocultos
    if len(filas) > len(mostradas):
        out["aviso"] = "Hay más: filtre por motivo o pida un límite mayor."
    personas = {p["id"] for c in mostradas for rol in ("persona", "otra_persona", "duena")
                if isinstance(p := c.get(rol), dict) and isinstance(p.get("id"), int)}
    return Resultado(out, f"{len(filas)} conflicto{'s' if len(filas) != 1 else ''} de cédula", personas=personas)


CONFLICTOS = Herramienta(
    nombre="conflictos_cedula",
    descripcion=(
        "Conflictos de cédula de Calidad de datos: filas importadas o cédulas dictadas que chocan con una ficha. Cada "
        "uno con su motivo (nombre_distinto: misma cédula y otro nombre; cedula_anterior; posible_digitacion: difiere "
        "en un dígito o las dos cédulas escritas en la planilla no coinciden; dictada: la dictó el titular al "
        "consultor), la fecha, la cédula enmascarada, la ficha (y la otra ficha o la dueña de la cédula), los datos "
        "mínimos de la fila (nombre, sexo, edad, lugar, cuántos teléfonos), la fuente (trámites, planilla u otra base) "
        "y las decisiones posibles. Úsala antes de resolver_conflicto. Los que incluyen a alguien que no autorizó "
        "salen solo con quiénes son y se resuelven en el panel. Solo administrador y coordinador."),
    entrada=ConflictosEntrada, tipo="lectura", permisos=("calidad.ver",), etiqueta="Revisando los conflictos de cédula",
    ejecutar=_conflictos, esquema=esquema(ConflictosEntrada), mcp="lectura")


# ───────────────────────────── resolver_conflicto ─────────────────────────────

class ResolverConflictoEntrada(_Entrada):
    conflicto_id: Id
    decision: Literal["aplicar", "descartar", "corregir", "reportar"] = Field(
        ..., description="aplicar: la fila es de esta persona (la completa); descartar: cerrar sin cambiar nada; "
                         "corregir: poner la cédula correcta; reportar: las dos fichas como posible duplicado")
    cedula_correcta: str | None = Field(None, min_length=5, max_length=20, description="Con corregir: la cédula "
                                                                                       "correcta, dictada")
    motivo: str | None = Field(None, min_length=3, max_length=300, description="Por qué (con corregir queda como el "
                                                                               "motivo del cambio de cédula)")

    @model_validator(mode="after")
    def _coherente(self):
        if self.decision == "corregir":
            if not self.cedula_correcta:
                raise ValueError("Con corregir indique cedula_correcta (la dictada; no la supongas)")
            if re.search(r"[A-Za-z]", self.cedula_correcta):
                raise ValueError("La cédula solo lleva números")
            ced = tx.cedula(self.cedula_correcta)
            if not ced:
                raise ValueError("La cédula correcta debe tener entre 5 y 11 dígitos")
            self.cedula_correcta = ced
        elif self.cedula_correcta is not None:
            raise ValueError("cedula_correcta solo va con corregir")
        return self


async def _conflicto(ctx: Contexto, cid: int, estado: str = "pendiente") -> dict | None:
    lista = _lista(await pedir(ctx, "GET", "/api/conflictos", params={"estado": estado}))
    return next((c for c in lista if c.get("id") == cid), None)


DECISIONES_CONFLICTO = {
    "aplicar": ("Aplicar: la fila es de esta persona", "La fila completa la ficha sin cambiar su cédula; lo distinto "
                                                       "queda como dato alterno."),
    "descartar": ("Descartar el aviso", "El aviso se cierra sin cambiar ninguna ficha."),
    "corregir": ("Corregir la cédula de la ficha", "La cédula de la ficha cambia y la anterior pasa a sus cédulas "
                                                   "anteriores."),
    "reportar": ("Reportar como posible duplicado", "Las dos fichas quedan en Coincidencias para decidir si son la "
                                                    "misma persona."),
}


def _lado(p: dict | None) -> str:
    if not isinstance(p, dict):
        return "Ya no está activa"
    ced = acceso.enmascarar_cedula(p.get("cedula"))
    return _persona(p) + (f" · cédula {ced}" if ced else " · sin cédula")


async def _confirmar_conflicto(ctx: Contexto, a: ResolverConflictoEntrada) -> Confirmacion:
    c = await _conflicto(ctx, a.conflicto_id)
    if c is None:
        raise ErrorHerramienta(f"El conflicto #{a.conflicto_id} ya se resolvió o no existe.", "no_existe", estado=404)
    involucradas = _involucradas(c)
    if any(p.get("consentimiento") == "no" for _, p in involucradas):
        raise ErrorHerramienta("El conflicto incluye a alguien que no autorizó el tratamiento de sus datos: se "
                               "resuelve en Calidad de datos del panel.", "no_contactable", estado=409,
                               detalle={"motivo": "no_autorizo"})
    if a.decision not in _decisiones(c):
        raise ErrorHerramienta(f"Para este conflicto ({MOTIVOS_CONFLICTO.get(c.get('motivo'), c.get('motivo'))}) las "
                               f"decisiones son: {', '.join(_decisiones(c))}.", "invalido", estado=422)
    if c.get("persona") is None and a.decision != "descartar":
        raise ErrorHerramienta("La ficha ya se unió o se suprimió: solo se puede descartar.", "invalido", estado=422)
    detalle = [("Motivo", MOTIVOS_CONFLICTO.get(c.get("motivo"), str(c.get("motivo")))),
               ("Ficha", _lado(c.get("persona")))]
    reg = c.get("registro") if isinstance(c.get("registro"), dict) else {}
    if c.get("motivo") != "dictada" and reg:
        fuente = {"tramites": "Trámites", "planilla": "Planilla de campo"}.get(c.get("fuente"), "Otra base importada")
        partes = (str(reg.get("nombre") or "(sin nombre)"), f"fila {reg['fila']}" if reg.get("fila") else None, fuente)
        detalle.append(("Fila", " · ".join(x for x in partes if x)))
    if c.get("duena"):
        detalle.append(("Ficha que ya tiene esa cédula", _lado(c["duena"])))
    if c.get("otra_persona"):
        detalle.append(("Ficha con una cédula parecida", _lado(c["otra_persona"])))
    titulo, aviso = DECISIONES_CONFLICTO[a.decision]
    detalle.append(("Decisión", titulo))
    if a.decision == "corregir":
        detalle.append(("Cédula correcta", a.cedula_correcta))
    if a.motivo:
        detalle.append(("Motivo de la decisión", a.motivo))
    if a.decision == "aplicar" and c.get("motivo") == "dictada":
        aviso = "La cédula dictada queda en la ficha si sigue libre."
    personas = {p["id"] for _, p in involucradas if isinstance(p.get("id"), int)}
    return Confirmacion(f"Resolver un conflicto de cédula (#{a.conflicto_id})", detalle, aviso, personas=personas)


async def _resolver_conflicto(ctx: Contexto, a: ResolverConflictoEntrada) -> Resultado:
    c = await _conflicto(ctx, a.conflicto_id)
    estado = ESTADO_DE_DECISION[a.decision]
    if c is None:  # la ruta no tiene idempotencia: si esta misma decisión ya quedó, no se repite
        hecho = await _conflicto(ctx, a.conflicto_id, estado)
        if hecho is not None and (hecho.get("resolucion") or {}).get("decision") == a.decision:
            return Resultado({"resuelto": True, "ya_estaba": True, "conflicto_id": a.conflicto_id, "estado": estado},
                             f"El conflicto #{a.conflicto_id} ya estaba resuelto")
        raise ErrorHerramienta(f"El conflicto #{a.conflicto_id} ya se resolvió de otra forma o no existe.", "no_existe",
                               estado=404)
    involucradas = _involucradas(c)
    if any(p.get("consentimiento") == "no" for _, p in involucradas):
        raise ErrorHerramienta("El conflicto incluye a alguien que no autorizó el tratamiento de sus datos: se "
                               "resuelve en Calidad de datos del panel.", "no_contactable", estado=409,
                               detalle={"motivo": "no_autorizo"})
    cuerpo = {"decision": a.decision, "cedula_correcta": a.cedula_correcta, "motivo": a.motivo}
    await _pedir(ctx, "POST", f"/api/conflictos/{a.conflicto_id}", cuerpo={k: v for k, v in cuerpo.items()
                                                                            if v is not None})
    personas = {p["id"] for _, p in involucradas if isinstance(p.get("id"), int)}
    return Resultado({"resuelto": True, "conflicto_id": a.conflicto_id, "decision": a.decision, "estado": estado},
                     f"Conflicto #{a.conflicto_id}: {estado}", list(ACCIONES), personas=personas)


RESOLVER_CONFLICTO = Herramienta(
    nombre="resolver_conflicto",
    descripcion=(
        "Propone resolver un conflicto de cédula (de conflictos_cedula) con una de sus decisiones: `aplicar` (la fila "
        "es de esta persona: completa la ficha sin cambiar su cédula; con una cédula dictada, la pone si sigue libre), "
        "`descartar` (cerrar el aviso sin cambiar nada), `corregir` (poner la cédula correcta que te dictaron en "
        "`cedula_correcta`, con `motivo`; nunca la supongas ni la armes con las enmascaradas) o `reportar` (las dos "
        "fichas como posible duplicado). La tarjeta muestra el conflicto y la decisión. Los que incluyen a alguien que "
        "no autorizó se resuelven en el panel. Solo administrador y coordinador, con su aprobación."),
    entrada=ResolverConflictoEntrada, tipo="escritura", permisos=("calidad.resolver",),
    etiqueta="Resolviendo el conflicto", ejecutar=_resolver_conflicto, confirmar=_confirmar_conflicto,
    esquema=esquema(ResolverConflictoEntrada), mcp="escritura")


# ───────────────────────────── situaciones ─────────────────────────────

class SituacionesEntrada(_Entrada):
    todas: bool = Field(False, description="true: también las ya confirmadas")
    limite: int = Field(30, ge=1, le=100)


SIN_NO_AUTORIZARON = ("Sin quienes no autorizaron el tratamiento de sus datos (ni se listan ni se cuentan): en Calidad "
                      "de datos del panel sí salen.")


async def _situaciones(ctx: Contexto, a: SituacionesEntrada) -> Resultado:
    filas = _lista(await pedir(ctx, "GET", "/api/situaciones", params={"todas": 1 if a.todas else None}))
    # Las filas no dicen si la persona autorizó: que se reportó fallecida o que se fue es un dato suyo
    no = await no_autorizaron(ctx, [f.get("id") for f in filas])
    tratables = [f for f in filas if f.get("id") not in no]
    salida = []
    for f in tratables[:a.limite]:
        sit = f.get("situacion") if isinstance(f.get("situacion"), dict) else {}
        salida.append({"id": f.get("id"), "nombre": f.get("nombre"),
                       "lugar": minimizar.texto_libre(f.get("lugar"), minimizar.LUGAR_MAX) if f.get("lugar") else None,
                       "situacion": sit.get("estado"), "confirmada": sit.get("confirmada") is True,
                       "fecha": fecha_de(sit.get("ts"))})
    out: dict[str, Any] = {"total": len(tratables), "mostradas": len(salida), "situaciones": salida,
                           "etiquetas": {k: v for k, v in modelo.SITUACIONES.items() if k != "activa"},
                           "nota_autorizacion": SIN_NO_AUTORIZARON, "ruta": "/calidad?p=situaciones",
                           "nota": "Para confirmar o revertir una: confirmar_situacion."}
    if len(tratables) > len(salida):
        out["aviso"] = "Hay más: pida un límite mayor."
    return Resultado(out, f"{len(tratables)} situacion{'es' if len(tratables) != 1 else ''} reportada"
                          f"{'s' if len(tratables) != 1 else ''}", personas=minimizar.ids_de(salida))


SITUACIONES = Herramienta(
    nombre="situaciones",
    descripcion=(
        "Personas reportadas como fallecidas o que ya no viven en Yondó (Calidad de datos > Situaciones), por "
        "confirmar (o todas, con `todas: true`): id, nombre, barrio o vereda, la situación, si está confirmada y la "
        "fecha del reporte. Mientras tanto la persona está fuera de las colas. No lista ni cuenta a quienes no "
        "autorizaron el tratamiento de sus datos. Úsala antes de confirmar_situacion. Solo administrador y "
        "coordinador."),
    entrada=SituacionesEntrada, tipo="lectura", permisos=("calidad.ver",), etiqueta="Revisando las situaciones",
    ejecutar=_situaciones, esquema=esquema(SituacionesEntrada), mcp="lectura")


# ───────────────────────────── confirmar_situacion ─────────────────────────────

class ConfirmarSituacionEntrada(_Entrada):
    persona_id: Id
    decision: Literal["confirmar", "revertir"] = Field(
        ..., description="confirmar: es cierto (sigue fuera de colas e indicadores); revertir: no lo es (vuelve a "
                         "estar activa)")


def _reportada(d: dict) -> dict:
    sit = d.get("situacion") if isinstance(d.get("situacion"), dict) else {}
    return sit if sit.get("estado") in ("fallecida", "no_reside") else {}


async def _tarjeta_situacion(ctx: Contexto, a: ConfirmarSituacionEntrada) -> Confirmacion:
    d = await _ficha(ctx, a.persona_id)
    _exigir_tratable(d)
    sit = _reportada(d)
    if not sit:
        raise ErrorHerramienta("La persona no tiene una situación reportada (fallecida o ya no vive en Yondó).",
                               "no_existe", estado=404)
    if a.decision == "confirmar" and sit.get("confirmada"):
        raise ErrorHerramienta("Esa situación ya está confirmada.", "sin_cambios")
    detalle = [("Persona", _persona(d)),
               ("Situación reportada", modelo.SITUACIONES.get(sit["estado"], sit["estado"])
                + (" (confirmada)" if sit.get("confirmada") else ""))]
    if fecha_de(sit.get("ts")):
        detalle.append(("Reportada el", fecha_de(sit.get("ts"))))
    if a.decision == "confirmar":
        detalle.append(("Decisión", "Confirmar"))
        return Confirmacion(f"Confirmar la situación de {_persona(d)}", detalle,
                            "Sigue fuera de las colas y de los indicadores, sin borrarse nada.",
                            personas={a.persona_id})
    detalle.append(("Decisión", "Revertir: vuelve a estar activa"))
    return Confirmacion(f"Revertir la situación de {_persona(d)}", detalle,
                        "Vuelve a estar activa: entra de nuevo en las colas y las listas de trabajo.",
                        personas={a.persona_id})


async def _resolver_situacion(ctx: Contexto, a: ConfirmarSituacionEntrada) -> Resultado:
    d = await _ficha(ctx, a.persona_id)
    _exigir_tratable(d)
    sit = _reportada(d)
    hecho = (bool(sit) and sit.get("confirmada") is True) if a.decision == "confirmar" else not sit
    if hecho:  # la ruta no tiene idempotencia: si ya quedó así, no se escribe ni se audita otra vez
        return Resultado({"guardado": True, "ya_estaba": True, "decision": a.decision},
                         f"La situación de la ficha #{a.persona_id} ya estaba así", personas={a.persona_id})
    if not sit:
        raise ErrorHerramienta("La persona ya no tiene una situación reportada.", "no_existe", estado=404)
    r = await _pedir(ctx, "POST", f"/api/situaciones/{a.persona_id}", cuerpo={"decision": a.decision})
    nueva = (r or {}).get("situacion") if isinstance(r, dict) else None
    return Resultado({"guardado": True, "decision": a.decision,
                      "situacion": minimizar.fila({"situacion": nueva}).get("situacion") if nueva else None},
                     "Situación confirmada" if a.decision == "confirmar" else "Situación revertida", list(ACCIONES),
                     personas={a.persona_id})


CONFIRMAR_SITUACION = Herramienta(
    nombre="confirmar_situacion",
    descripcion=(
        "Propone confirmar o revertir una situación reportada (de situaciones): `confirmar` (es cierto que falleció o "
        "que ya no vive en Yondó: sigue fuera de las colas y los indicadores, sin borrar nada) o `revertir` (no es "
        "cierto: vuelve a estar activa). Confirma solo con lo que la persona del equipo sabe (un familiar, la "
        "Registraduría, una visita), nunca por suposición. Para reportar una nueva usa reportar_situacion. No se usa "
        "con quien no autorizó el tratamiento de sus datos. Solo administrador y coordinador, con su aprobación."),
    entrada=ConfirmarSituacionEntrada, tipo="escritura", permisos=("calidad.resolver",),
    etiqueta="Confirmando la situación", ejecutar=_resolver_situacion, confirmar=_tarjeta_situacion,
    esquema=esquema(ConfirmarSituacionEntrada), mcp="escritura")


# ───────────────────────────── solicitudes ─────────────────────────────

TIPOS_SOLICITUD = tuple(modelo.TIPOS_SOLICITUD)
ESTADOS_SOLICITUD = tuple(modelo.ESTADOS_SOLICITUD)
POR_VENCER_DIAS = 3


class SolicitudesEntrada(_Entrada):
    estado: Literal[("abiertas", *ESTADOS_SOLICITUD, "todas")] = Field(
        "abiertas", description="abiertas (pendiente o en trámite, por defecto), un estado, o todas")
    tipo: Literal[TIPOS_SOLICITUD] | None = None
    limite: int = Field(30, ge=1, le=100)


def solicitud_para_modelo(s: dict) -> dict:
    """Una solicitud sin de quién es: que alguien pidió, por ejemplo, la supresión de sus datos es un dato suyo. Sin la
    descripción (texto del titular) ni la respuesta. El caso se atiende en Calidad del panel."""
    return {"id": s.get("id"), "tipo": s.get("tipo"), "canal": s.get("canal"), "estado": s.get("estado"),
            "creada": fecha_de(s.get("ts")), "vence": s.get("vence"), "dias_restantes": s.get("dias_restantes"),
            "vencida": s.get("vencida") is True}


async def _solicitudes(ctx: Contexto, a: SolicitudesEntrada) -> Resultado:
    lista = _lista(await pedir(ctx, "GET", "/api/solicitudes", params={"estado": a.estado, "tipo": a.tipo}))
    filas = [solicitud_para_modelo(s) for s in lista]
    por_tipo: dict[str, int] = {}
    por_estado: dict[str, int] = {}
    for f in filas:
        por_tipo[str(f["tipo"])] = por_tipo.get(str(f["tipo"]), 0) + 1
        por_estado[str(f["estado"])] = por_estado.get(str(f["estado"]), 0) + 1
    vencidas = sum(1 for f in filas if f["vencida"])
    por_vencer = sum(1 for f in filas if not f["vencida"] and f["estado"] in modelo.ABIERTAS
                     and isinstance(f["dias_restantes"], int) and 0 <= f["dias_restantes"] <= POR_VENCER_DIAS)
    mostradas = filas[:a.limite]
    out: dict[str, Any] = {"total": len(filas), "vencidas": vencidas, f"por_vencer_{POR_VENCER_DIAS}_dias": por_vencer,
                           "por_tipo": por_tipo, "por_estado": por_estado, "solicitudes": mostradas,
                           "tipos": modelo.TIPOS_SOLICITUD, "ruta": "/calidad?p=solicitudes",
                           "nota": ("Sin de quién es cada solicitud ni lo que pidió: el caso se lee en Calidad del "
                                    "panel. Para cambiar su estado o anotar la respuesta: actualizar_solicitud. "
                                    "Atienda primero las vencidas: el plazo es legal.")}
    if len(filas) > len(mostradas):
        out["aviso"] = "Hay más: filtre por tipo o estado, o pida un límite mayor."
    return Resultado(out, f"{len(filas)} solicitud{'es' if len(filas) != 1 else ''}"
                          + (f" ({vencidas} vencidas)" if vencidas else ""))


SOLICITUDES = Herramienta(
    nombre="solicitudes",
    descripcion=(
        "Las solicitudes de los titulares sobre sus datos (Ley 1581: consulta, corrección, supresión, revocatoria, "
        "otro, pedido de registro), abiertas por defecto: id, tipo, canal, estado, fecha, vencimiento del plazo legal, "
        "días restantes y si está vencida, con los totales por tipo y estado. Nunca dice de quién es ni lo que pidió: "
        "eso se lee en Calidad de datos del panel. Úsala para saber qué está por vencer y antes de "
        "actualizar_solicitud. Para registrar una nueva: registrar_solicitud. Solo administrador y coordinador."),
    entrada=SolicitudesEntrada, tipo="lectura", permisos=("calidad.ver",), etiqueta="Revisando las solicitudes",
    ejecutar=_solicitudes, esquema=esquema(SolicitudesEntrada), mcp="lectura")


# ───────────────────────────── actualizar_solicitud ─────────────────────────────

class ActualizarSolicitudEntrada(_Entrada):
    solicitud_id: Id
    estado: Literal[ESTADOS_SOLICITUD] | None = Field(None, description="pendiente, en_tramite, resuelta o rechazada")
    respuesta: str | None = Field(None, min_length=2, max_length=2000, description="La respuesta que se le dio al "
                                                                                  "titular (queda en el registro)")

    @model_validator(mode="after")
    def _algo(self):
        if self.estado is None and self.respuesta is None:
            raise ValueError("Indique estado, respuesta o los dos")
        return self


async def _solicitud_por_id(ctx: Contexto, sid: int) -> dict:
    lista = _lista(await pedir(ctx, "GET", "/api/solicitudes", params={"estado": "todas"}))
    s = next((s for s in lista if s.get("id") == sid), None)
    if s is None:
        raise ErrorHerramienta(f"No encuentro la solicitud #{sid} entre las 500 más recientes.", "no_existe",
                               estado=404)
    return s


def _cambios_solicitud(s: dict, a: ActualizarSolicitudEntrada) -> dict:
    cambios: dict[str, Any] = {}
    if a.estado is not None and a.estado != s.get("estado"):
        cambios["estado"] = a.estado
    if a.respuesta is not None and a.respuesta != s.get("respuesta"):
        cambios["respuesta"] = a.respuesta
    return cambios


def _persona_de(s: dict) -> int | None:
    pid = s.get("persona_id")
    return pid if isinstance(pid, int) and not isinstance(pid, bool) else None


async def _confirmar_actualizar_solicitud(ctx: Contexto, a: ActualizarSolicitudEntrada) -> Confirmacion:
    s = await _solicitud_por_id(ctx, a.solicitud_id)
    cambios = _cambios_solicitud(s, a)
    if not cambios:
        raise ErrorHerramienta("La solicitud ya está así: no hay nada que cambiar.", "sin_cambios")
    pid = _persona_de(s)
    tipo = modelo.TIPOS_SOLICITUD.get(s.get("tipo"), s.get("tipo"))
    detalle = [("Solicitud", f"#{a.solicitud_id} · {tipo}"),
               ("Persona", f"{s.get('persona') or 'Persona sin nombre'} (#{pid})" if pid else "Sin persona")]
    if s.get("vence"):
        detalle.append(("Vence", str(s["vence"]) + (" (vencida)" if s.get("vencida") else "")))
    if "estado" in cambios:
        detalle.append(("Estado", f"{modelo.ESTADOS_SOLICITUD.get(s.get('estado'), s.get('estado'))} → "
                                  f"{modelo.ESTADOS_SOLICITUD[cambios['estado']]}"))
    if "respuesta" in cambios:
        detalle.append(("Respuesta", cambios["respuesta"]))
    aviso = "Responder dentro del plazo es una obligación legal (Ley 1581): la respuesta queda en el registro."
    if s.get("tipo") == "supresion" and cambios.get("estado") == "resuelta":
        aviso += " Marcarla resuelta no suprime los datos: la supresión se hace en la ficha del panel."
    return Confirmacion(f"Actualizar la solicitud #{a.solicitud_id}", detalle, aviso,
                        personas={pid} if pid else set())


async def _actualizar_solicitud(ctx: Contexto, a: ActualizarSolicitudEntrada) -> Resultado:
    s = await _solicitud_por_id(ctx, a.solicitud_id)
    cambios = _cambios_solicitud(s, a)
    if cambios:  # PATCH: sin idempotencia en la API; lo que ya quedó como se pidió no se escribe otra vez
        await pedir(ctx, "PATCH", f"/api/solicitudes/{a.solicitud_id}", cuerpo=cambios)
    # Sin la persona: el modelo no sabe de quién es cada solicitud
    contenido: dict[str, Any] = {"actualizada": True, "solicitud": {
        "id": a.solicitud_id, "tipo": s.get("tipo"), "estado": cambios.get("estado", s.get("estado")),
        "vence": s.get("vence")}, "cambios": sorted(cambios)}
    if not cambios:
        contenido["ya_estaba"] = True
    return Resultado(contenido, f"Solicitud #{a.solicitud_id} actualizada" if cambios else
                     f"La solicitud #{a.solicitud_id} ya estaba así", list(ACCIONES))


ACTUALIZAR_SOLICITUD = Herramienta(
    nombre="actualizar_solicitud",
    descripcion=(
        "Propone cambiar el estado de una solicitud de un titular (pendiente, en_tramite, resuelta o rechazada) y "
        "anotar la respuesta que se le dio, con el id de solicitudes. La tarjeta muestra de quién es; a ti no te "
        "llega. Anota solo la respuesta que te dictaron. Marcar resuelta una supresión no suprime los datos: eso se "
        "hace en la ficha del panel. Responder dentro del plazo legal es obligatorio (10 días hábiles la consulta, 15 "
        "los reclamos). Solo administrador y coordinador, con su aprobación."),
    entrada=ActualizarSolicitudEntrada, tipo="escritura", permisos=("calidad.resolver",),
    etiqueta="Actualizando la solicitud", ejecutar=_actualizar_solicitud, confirmar=_confirmar_actualizar_solicitud,
    esquema=esquema(ActualizarSolicitudEntrada), mcp="escritura")


# ───────────────────────────── importaciones ─────────────────────────────

class ImportacionesEntrada(_Entrada):
    limite: int = Field(10, ge=1, le=30, description="Las más recientes")


# Del resumen de una importación, lo que no dice nada de las bases políticas
RESUMEN_IMPORTACION = ("personas_nuevas", "personas_actualizadas", "tramites_nuevos", "telefonos_agregados",
                       "alternos_agregados", "registros_en_revision", "conflictos_cedula", "no_guardadas",
                       "omitidas_sin_autorizacion", "votacion_por_confirmar", "autorizaciones_por_confirmar",
                       "lugares_nuevos")
# Con `agente_politicos`: lo que cuenta la importación de la base general (tipos marcados y líderes) y por fuente
RESUMEN_POLITICO = ("lideres_asignados", "lideres_sin_resolver")
RESUMEN_POLITICO_POR_CLAVE = ("tipos_marcados", "registros_por_fuente")


def importacion_para_modelo(x: dict, politicos: bool = False) -> dict:
    """Una importación: la fecha, quién la hizo (del equipo) y, si solo trae trámites o planillas, el archivo y los
    conteos. Una con la base con cédula o la base general sale como «otra_base», sin archivo ni conteos: revelan el
    tamaño de una base política. Con `politicos` (A y K con `agente_politicos` encendido) sale como es, con lo que
    contó de tipos marcados, líderes y registros por fuente."""
    tipos = [t.strip() for t in str(x.get("tipo") or "").split(",") if t.strip()]
    out: dict[str, Any] = {"id": x.get("id"), "fecha": fecha_de(x.get("ts")), "usuario": x.get("usuario")}
    if not politicos and (not tipos or any(t not in FUENTES_VISIBLES for t in tipos)):
        return {**out, "tipo": "otra_base"}
    resumen = x.get("resumen") if isinstance(x.get("resumen"), dict) else {}
    claves = (*RESUMEN_IMPORTACION, *RESUMEN_POLITICO) if politicos else RESUMEN_IMPORTACION
    out.update({"tipo": tipos, "archivo": minimizar.texto_libre(x.get("archivo"), 160),
                "resumen": {k: resumen[k] for k in claves if isinstance(resumen.get(k), int)
                            and not isinstance(resumen.get(k), bool)}})
    if politicos:
        for k in RESUMEN_POLITICO_POR_CLAVE:
            if isinstance(resumen.get(k), dict):
                out["resumen"][k] = {str(t): n for t, n in resumen[k].items()
                                     if isinstance(n, int) and not isinstance(n, bool)}
    if isinstance(x.get("capturado_por"), int):
        out["capturado_por"] = x["capturado_por"]
    return out


async def _importaciones(ctx: Contexto, a: ImportacionesEntrada) -> Resultado:
    lista = _lista(await pedir(ctx, "GET", "/api/importaciones"))
    politicos = ctx.quien.administra and ctx.politicos()
    filas = [importacion_para_modelo(x, politicos) for x in lista[:a.limite]]
    por_confirmar = sum(int((f.get("resumen") or {}).get("autorizaciones_por_confirmar") or 0) for f in filas)
    out = {"mostradas": len(filas), "importaciones": filas, "ruta": "/importar",
           "nota": ("Las autorizaciones «declaradas en planilla» no habilitan el contacto hasta que el administrador o "
                    "el coordinador las confirma con la evidencia física en Importar y exportar del panel; el "
                    "asistente no las confirma. `autorizaciones_por_confirmar` es lo que dejó cada importación al "
                    "cargarse.")}
    return Resultado(out, f"{len(filas)} importacion{'es' if len(filas) != 1 else ''}"
                          + (f" · {por_confirmar} autorizaciones por confirmar" if por_confirmar else ""))


IMPORTACIONES = Herramienta(
    nombre="importaciones",
    descripcion=(
        "Las últimas importaciones de datos (Importar y exportar): fecha, quién la hizo, el tipo (trámites o planilla "
        "de campo), el archivo y los conteos (personas nuevas y actualizadas, teléfonos, conflictos de cédula, filas "
        "en revisión, omitidas por no autorizar, votación por confirmar y autorizaciones declaradas en planilla por "
        "confirmar). Las de la base con cédula y la base general (bases políticas) salen con su tipo, archivo y "
        "conteos solo si los datos políticos están habilitados; si no, como otra_base, sin archivo ni conteos. Úsala "
        "para contar qué entró, qué quedó por "
        "revisar y qué autorizaciones faltan por confirmar con la evidencia física (eso se hace en el panel). No "
        "importa nada. Solo administrador y coordinador."),
    entrada=ImportacionesEntrada, tipo="lectura", permisos=("importar",), etiqueta="Revisando las importaciones",
    ejecutar=_importaciones, esquema=esquema(ImportacionesEntrada), mcp="lectura")


# ───────────────────────────── puestos ─────────────────────────────

class PuestosEntrada(_Entrada):
    texto: str | None = Field(None, min_length=2, max_length=80, description="Parte del nombre o el código del puesto")
    limite: int = Field(60, ge=1, le=200)


def puesto_para_modelo(p: dict) -> dict:
    """Un puesto de votación de la elección vigente: el catálogo, con los habilitados (el censo por puesto) y las mesas.
    Sin coordenadas, alias ni fuentes."""
    out: dict[str, Any] = {k: p.get(k) for k in ("id", "codigo", "nombre") if p.get(k) is not None}
    if isinstance(p.get("mesas"), int):
        out["mesas"] = p["mesas"]
    hab = p.get("habilitados")
    if isinstance(hab, dict):
        out["habilitados"] = {k: hab[k] for k in ("mujeres", "hombres", "total") if isinstance(hab.get(k), int)}
    for k in ("area", "lugar_id"):
        if p.get(k) is not None:
            out[k] = p[k]
    return out


async def _puestos(ctx: Contexto, a: PuestosEntrada) -> Resultado:
    lista = _lista(await pedir(ctx, "GET", "/api/puestos"))
    if a.texto:
        buscado = tx.limpiar(a.texto)
        lista = [p for p in lista if buscado in tx.limpiar(p.get("nombre")) or buscado in str(p.get("codigo") or "")]
    filas = [puesto_para_modelo(p) for p in lista]
    mostrados = filas[:a.limite]
    out: dict[str, Any] = {"total": len(filas), "mostrados": len(mostrados), "puestos": mostrados,
                           "eleccion": next((p.get("eleccion") for p in lista if p.get("eleccion")), None)}
    if any("habilitados" in f for f in filas):
        out["totales"] = {"mesas": sum(f.get("mesas") or 0 for f in filas),
                          "habilitados": sum((f.get("habilitados") or {}).get("total") or 0 for f in filas)}
        out["nota"] = "habilitados = personas habilitadas para votar en el puesto (censo electoral), no registradas."
    if len(filas) > len(mostrados):
        out["aviso"] = "Hay más: busque por nombre o código, o pida un límite mayor."
    return Resultado(out, f"{len(filas)} puesto{'s' if len(filas) != 1 else ''} de votación")


PUESTOS = Herramienta(
    nombre="puestos",
    descripcion=(
        "Catálogo de puestos de votación de la elección vigente: id, código, nombre, número de mesas, zona (urbana o "
        "rural), barrio o vereda y cuántas personas están habilitadas para votar en cada uno (el censo electoral, por "
        "mujeres y hombres), con los totales. Busca por parte del nombre o el código. Úsala para el puesto_id de "
        "editar_persona, para saber cuántas mesas tiene un puesto o para comparar el censo con lo registrado "
        "(indicadores). El consultor solo recibe el código y el nombre. No trae personas."),
    entrada=PuestosEntrada, tipo="lectura", permisos=("puestos.ver",), etiqueta="Consultando los puestos",
    ejecutar=_puestos, esquema=esquema(PuestosEntrada), mcp="lectura")


# ───────────────────────────── lugares_sin_reconocer ─────────────────────────────

class SinReconocerEntrada(_Entrada):
    limite: int = Field(30, ge=1, le=80)


def _no_autorizaron_por_texto(db: Any, textos: list[str]) -> dict[str, int]:
    """Cuántas de las personas con cada lugar escrito no autorizaron (para no contarlas)."""
    return {x["_id"]: x["n"] for x in db.personas.aggregate([
        {"$match": {**bd.ACTIVA, "lugar_id": None, "lugar_texto": {"$in": textos}, "consentimiento": "no"}},
        {"$group": {"_id": "$lugar_texto", "n": {"$sum": 1}}}])}


async def _sin_reconocer(ctx: Contexto, a: SinReconocerEntrada) -> Resultado:
    filas = [x for x in _lista(await pedir(ctx, "GET", "/api/lugares/sin-reconocer"))
             if isinstance(x.get("texto"), str)]
    no = await run_in_threadpool(_no_autorizaron_por_texto, ctx.db, [x["texto"] for x in filas]) if filas else {}
    # Sin quienes no autorizaron, y solo los textos que siguen teniendo 2 personas o más (como la API)
    contadas = [(x["texto"], int(x.get("n") or 0) - no.get(x["texto"], 0)) for x in filas]
    contadas = [(t, n) for t, n in contadas if n >= 2]
    nom: Nomenclatura = await nomenclatura(ctx)
    textos = []
    for t, n in contadas[:a.limite]:
        sug = [{"id": lg.id, "nombre": lg.nombre, "tipo": lg.tipo} for lg in nom.sugerir(t, SUGERENCIAS_LUGAR)]
        textos.append({"texto": minimizar.texto_libre(t, 120), "personas": n, **({"parecidos": sug} if sug else {})})
    out: dict[str, Any] = {"total": len(contadas), "personas": sum(n for _, n in contadas), "textos": textos,
                           "ruta": "/calidad?p=sin", "nota_autorizacion": SIN_NO_AUTORIZARON,
                           "nota": ("Lugares escritos en las direcciones que no casan con el nomenclátor. Si uno es "
                                    "otra forma de escribir un barrio o vereda que existe, agregar_alias_lugar lo "
                                    "agrega como alias y esas personas se vuelven a ubicar. `parecidos` son "
                                    "sugerencias por el nombre: confírmelas con la persona del equipo. Un lugar nuevo "
                                    "se crea en Calidad de datos.")}
    return Resultado(out, f"{len(contadas)} lugar{'es' if len(contadas) != 1 else ''} escrito"
                          f"{'s' if len(contadas) != 1 else ''} sin reconocer")


SIN_RECONOCER = Herramienta(
    nombre="lugares_sin_reconocer",
    descripcion=(
        "Lugares escritos en las direcciones de las fichas que no casan con el nomenclátor de barrios y veredas "
        "(Calidad de datos > Sin reconocer), con cuántas personas los tienen (2 o más) y hasta 3 lugares de nombre "
        "parecido como sugerencia. Úsala para mejorar la ubicación de la base: si un texto es otra forma de escribir "
        "un lugar que existe («B. EL PROGRESO», «PROGRESO»), propón agregar_alias_lugar. No cuenta a quienes no "
        "autorizaron el tratamiento de sus datos. No trae personas. Solo administrador y coordinador."),
    entrada=SinReconocerEntrada, tipo="lectura", permisos=("admin",), etiqueta="Revisando los lugares sin reconocer",
    ejecutar=_sin_reconocer, esquema=esquema(SinReconocerEntrada), mcp="lectura")


# ───────────────────────────── agregar_alias_lugar ─────────────────────────────

class AliasEntrada(_Entrada):
    lugar_id: Id = Field(..., description="El barrio o vereda (id de buscar_lugar)")
    texto: str = Field(..., min_length=2, max_length=80, description="El nombre como lo escriben (de "
                                                                     "lugares_sin_reconocer)")


def _lugar_y_choque(db: Any, lid: int, alias: str) -> tuple[dict | None, dict | None, int]:
    """El lugar, otro lugar que ya se llama o se escribe así (el alias lo volvería ambiguo) y cuántas personas sin
    barrio o vereda tienen ese lugar escrito (las que se volverían a ubicar)."""
    from ...api.calidad import otro_lugar_con, personas_con_lugar_escrito  # aquí: la API carga FastAPI
    lg = db.lugares.find_one({"_id": lid}, {"nombre": 1, "tipo": 1, "alias": 1})
    return lg, otro_lugar_con(db, lid, alias), len(personas_con_lugar_escrito(db, alias))


def _alias(texto: str) -> str:
    from ...api.calidad import alias_de
    return alias_de(texto)


async def _revisar_alias(ctx: Contexto, a: AliasEntrada) -> tuple[Any, str, dict, int]:
    exigir_permiso(ctx, "admin", "Solo el administrador y el coordinador editan el nomenclátor de lugares.")
    alias = _alias(a.texto)
    if len(alias) < 2:
        raise ErrorHerramienta("Escriba el nombre del lugar con letras (al menos 2).", "invalido", estado=422)
    lugar = (await nomenclatura(ctx)).por_id_o_error(a.lugar_id)
    doc, otro, n = await run_in_threadpool(_lugar_y_choque, ctx.db, a.lugar_id, alias)
    if doc is None:
        raise ErrorHerramienta(f"No existe el lugar #{a.lugar_id}.", "no_existe", estado=404)
    if otro is not None:
        raise ErrorHerramienta(f"«{alias}» ya es el nombre o un alias de {otro.get('nombre')} "
                               f"({otro.get('tipo')} #{otro.get('_id')}): agregarlo aquí lo volvería ambiguo.",
                               "ambiguo", estado=409, detalle={"id": otro.get("_id")})
    return lugar, alias, doc, n


async def _confirmar_alias(ctx: Contexto, a: AliasEntrada) -> Confirmacion:
    lugar, alias, doc, n = await _revisar_alias(ctx, a)
    actuales = [x for x in doc.get("alias") or [] if isinstance(x, str)]
    if alias == _alias(doc.get("nombre") or "") or alias in actuales:
        raise ErrorHerramienta(f"«{alias}» ya es el nombre o un alias de {lugar.legible()}.", "sin_cambios")
    detalle = [("Barrio o vereda", lugar.legible()), ("Alias nuevo", alias),
               ("Alias que ya tiene", ", ".join(actuales) or "(ninguno)"),
               ("Personas con ese lugar escrito y sin barrio o vereda", miles(n))]
    return Confirmacion(f"Agregar un alias a {lugar.nombre}", detalle,
                        "Las personas sin barrio o vereda que tienen ese lugar escrito se vuelven a ubicar; desde "
                        "ahora el alias vale también para las direcciones nuevas. Quitar un alias se hace en Calidad "
                        "de datos.")


async def _agregar_alias(ctx: Contexto, a: AliasEntrada) -> Resultado:
    lugar, alias, _, _ = await _revisar_alias(ctx, a)
    # La ruta es idempotente ($addToSet y la reubicación acotada a esas personas): repetirla no duplica ni audita dos
    # veces
    r = await pedir(ctx, "POST", f"/api/lugares/{a.lugar_id}/alias", cuerpo={"alias": a.texto})
    r = r if isinstance(r, dict) else {}
    reubicadas = int(r.get("reconocidas_tratables") or 0)
    contenido = {"guardado": True, "lugar": lugar.para_modelo(), "alias": alias, "ya_estaba": not r.get("nuevo"),
                 "reubicadas": reubicadas,
                 "nota": "reubicadas: personas sin barrio o vereda que ahora quedaron en este lugar (sin contar a "
                         "quienes no autorizaron)."}
    return Resultado(contenido, f"Alias agregado a {lugar.nombre}" + (f" · {reubicadas} reubicadas" if reubicadas
                                                                       else ""), [{"tipo": "recargar"}])


AGREGAR_ALIAS = Herramienta(
    nombre="agregar_alias_lugar",
    descripcion=(
        "Propone agregar un alias a un barrio o vereda del nomenclátor: otra forma de escribir su nombre (de "
        "lugares_sin_reconocer, por ejemplo «B. EL PROGRESO» o «PROGRESO» para El Progreso). Desde ese momento el "
        "panel reconoce ese texto en las direcciones, y las personas sin barrio o vereda que lo tienen escrito se "
        "vuelven a ubicar. No se agrega si ya es el nombre o un alias de otro lugar (sería ambiguo). Confirma el lugar "
        "con la persona del equipo antes: un alias equivocado ubica mal a todos los que lo escriben. Crear un lugar "
        "nuevo o quitar un alias se hace en Calidad de datos. Solo administrador y coordinador, con su aprobación."),
    entrada=AliasEntrada, tipo="escritura", permisos=("admin",), etiqueta="Agregando el alias",
    ejecutar=_agregar_alias, confirmar=_confirmar_alias, esquema=esquema(AliasEntrada), plazo=160, mcp="escritura")


HERRAMIENTAS: list[Herramienta] = [COINCIDENCIAS, RESOLVER_COINCIDENCIAS, CONFLICTOS, RESOLVER_CONFLICTO, SITUACIONES,
                                   CONFIRMAR_SITUACION, SOLICITUDES, ACTUALIZAR_SOLICITUD, IMPORTACIONES, PUESTOS,
                                   SIN_RECONOCER, AGREGAR_ALIAS]
