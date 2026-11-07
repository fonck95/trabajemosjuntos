"""Herramientas de Mnemo por su servidor MCP (en construcción: lo completa su implementador).

Interfaz que usa el bucle (`bucle.py`):
* `async definiciones(cliente, filtro: str) -> list[dict]`: las herramientas que ofrece el servidor (tools/list),
  acotadas por `MNEMO_HERRAMIENTAS`, como diccionarios serializables que la conversación guarda congelados.
* `desde_definiciones(definiciones) -> list[Herramienta]`: las herramientas del asistente a partir de lo guardado.
* `disponible_para(quien, ajustes_agente, cfg) -> bool`: si a esta persona se le ofrecen.
"""
from __future__ import annotations

from typing import Any

from .base import Herramienta


async def definiciones(cliente: Any, filtro: str) -> list[dict]:
    return []


def desde_definiciones(definiciones: list[dict]) -> list[Herramienta]:
    return []


def disponible_para(quien: Any, ajustes_agente: dict, cfg: Any) -> bool:
    return False
