"""Catálogo de herramientas del asistente.

* Las fijas (`personas`, `fichas`, `calidad`, `planillas`, `analisis`, `gestion`, `interfaz`) van siempre en el
  mismo orden: la lista de herramientas de una conversación se congela al crearla (la caché del proveedor y el
  razonamiento conservado dependen de que el prefijo no cambie) y se rehace por nombre en cada turno.
* Las de Mnemo son dinámicas: salen de `tools/list` del servidor MCP al crear la conversación y se guardan con ella
  (`mnemo.desde_definiciones`).
* Ofrecer una herramienta no autoriza nada: cada llamada vuelve a pasar por los permisos de la API.
"""
from __future__ import annotations

from typing import Any

from . import analisis, calidad, fichas, gestion, interfaz, personas, planillas
from .base import Confirmacion, Contexto, ErrorHerramienta, Herramienta, Resultado

__all__ = ["Confirmacion", "Contexto", "ErrorHerramienta", "Herramienta", "Resultado", "fijas", "por_nombre", "para"]


def fijas() -> list[Herramienta]:
    # Las nuevas van entre `personas` y `gestion`: el principio y el final del catálogo no cambian (las pruebas lo fijan)
    return [*personas.HERRAMIENTAS, *fichas.HERRAMIENTAS, *calidad.HERRAMIENTAS, *planillas.HERRAMIENTAS,
            *analisis.HERRAMIENTAS, *gestion.HERRAMIENTAS, *interfaz.HERRAMIENTAS]


def por_nombre() -> dict[str, Herramienta]:
    return {h.nombre: h for h in fijas()}


def para(quien: Any, ajustes_agente: dict, cfg: Any, *, ajustes: dict | None = None) -> list[Herramienta]:
    """Las herramientas fijas que se le ofrecen a `quien`: sus permisos, el ajuste de escritura y la condición propia
    de cada una (`disponible`, con los ajustes del asistente, y `disponible_ajustes`, con los del panel: `ajustes`, ya
    validados por `politica.leer`; sin ellos, los de defecto). El orden es el de `fijas()`."""
    from .. import politica  # aquí: politica importa el proveedor del modelo
    return [h for h in fijas() if politica.ofrecida(h, quien, ajustes_agente, cfg, ajustes=ajustes)]
