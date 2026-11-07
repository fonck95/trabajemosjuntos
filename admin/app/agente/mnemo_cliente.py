"""Cliente del servidor MCP remoto de Mnemo (en construcción: lo completa su implementador).

Interfaz:
* `cliente_de(app, cfg) -> ClienteMnemo | None`: uno por aplicación (en `app.state`), o None sin MNEMO_MCP_URL y
  MNEMO_TOKEN.
* `ClienteMnemo.instrucciones -> str | None` (las de `initialize`), `await herramientas()`, `await llamar(nombre,
  argumentos)`.
"""
from __future__ import annotations

from typing import Any


class ClienteMnemo:
    instrucciones: str | None = None


def cliente_de(app: Any, cfg: Any) -> ClienteMnemo | None:
    return None
