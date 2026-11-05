"""Reglas de la interfaz para el celular que una prueba de API no ve (se comprueban en la hoja de estilos)."""
import re
from pathlib import Path

CSS = (Path(__file__).resolve().parent.parent / "web" / "css" / "app.css").read_text(encoding="utf-8")


def _regla(selector: str, dentro: str = CSS) -> str:
    m = re.search(r"(?m)^\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", dentro)
    assert m, f"no está la regla {selector}"
    return m.group(1)


def test_el_menu_lateral_se_desplaza_en_pantallas_bajas():
    """El menú del administrador y del coordinador mide unos 650 px: en un celular en horizontal o en un iPhone SE con las
    barras de Safari quedaban fuera «Usuarios», «Ajustes», «Mi cuenta» y «Cerrar sesión», sin forma de llegar."""
    lateral = _regla(".lateral")
    assert re.search(r"overflow-y:\s*auto", lateral) and "overscroll-behavior: contain" in lateral
    assert "100dvh" in lateral  # el alto visible, no el de iOS sin barras
    movil = CSS[CSS.index("@media (max-width: 900px)"):]
    assert re.search(r"\.lateral\s*\{[^}]*height:\s*auto", movil)  # en el celular manda inset: 0 (arriba y abajo)
