"""Catálogo de herramientas del asistente.

* Las fijas (`personas`, `gestion`, `interfaz`) van siempre en el mismo orden: la lista de herramientas de una
  conversación se congela al crearla (la caché del proveedor y el razonamiento conservado dependen de que el prefijo
  no cambie) y se rehace por nombre en cada turno.
* Las de Mnemo son dinámicas: salen de `tools/list` del servidor MCP al crear la conversación y se guardan con ella
  (`mnemo.desde_definiciones`).
* Ofrecer una herramienta no autoriza nada: cada llamada vuelve a pasar por los permisos de la API.
"""
from __future__ import annotations

from typing import Any

from . import gestion, interfaz, personas
from .base import Confirmacion, Contexto, ErrorHerramienta, Herramienta, Resultado

__all__ = ["Confirmacion", "Contexto", "ErrorHerramienta", "Herramienta", "Resultado", "fijas", "por_nombre", "para"]


def fijas() -> list[Herramienta]:
    return [*personas.HERRAMIENTAS, *gestion.HERRAMIENTAS, *interfaz.HERRAMIENTAS]


def por_nombre() -> dict[str, Herramienta]:
    return {h.nombre: h for h in fijas()}


def para(quien: Any, ajustes_agente: dict, cfg: Any) -> list[Herramienta]:
    """Las herramientas fijas que se le ofrecen a `quien`: sus permisos, el ajuste de escritura y la condición propia
    de cada una. El orden es el de `fijas()`."""
    escritura = bool(ajustes_agente.get("escritura", True))
    out = []
    for h in fijas():
        if not h.permitida(quien):
            continue
        if h.tipo == "escritura" and not escritura:
            continue
        if h.disponible is not None and not h.disponible(quien, ajustes_agente, cfg):
            continue
        out.append(h)
    return out
