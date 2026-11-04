"""Usuarios del panel: alta, roles, claves, sesiones e indicadores por usuario."""
from __future__ import annotations

from fastapi import APIRouter

r = APIRouter(prefix="/api", tags=["usuarios"])
