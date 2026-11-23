"""Rutas de planillas del panel (en construcción; ver docs/agente.md)."""
from __future__ import annotations

from fastapi import APIRouter

r = APIRouter(prefix="/api", tags=["planillas"])
