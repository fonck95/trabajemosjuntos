"""Migración idempotente del esquema (versión 2) y reconciliación de lo que escriba el código viejo (1.12).

`db.inicializar` la llamará al final, antes de que el panel quede listo. Todavía no hace nada.
"""
from __future__ import annotations

from pymongo.database import Database


class ErrorMigracion(RuntimeError):
    """Error estructural de la migración (índice, conexión, turno ocupado demasiado tiempo): el arranque se corta con su
    propio mensaje en el registro. Un error en un documento no la lanza: se anota y la migración sigue."""


def migrar(db: Database) -> None:
    """Lleva la base a la versión de esquema vigente y reconcilia lo que haya escrito el código viejo. Se puede repetir
    sin daño. Todavía no hace nada."""
    return None
