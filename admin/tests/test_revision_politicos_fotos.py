"""Regresiones de la revisión adversarial de los datos políticos y las planillas por foto (sin MongoDB ni modelo).

* El aviso fijo de la cámara (el chat y Importar y exportar) y las instrucciones del asistente piden tapar también las
  columnas políticas: el lector no las transcribe (`lector_planillas.INSTRUCCIONES`), así que en la foto solo
  llegarían enteras al proveedor del modelo, también con `agente_politicos` apagado, sin servir para nada.
* La documentación no dice que la analítica nunca nombra personas: con los datos políticos, una tabla por `lider`
  nombra a los líderes (`herramientas/analisis.py`, `lideres_de`), que van en `Resultado.personas`.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.agente import lector_planillas, sistema
from app.agente.herramientas import analisis

RAIZ = Path(__file__).resolve().parents[1]
AGENTE_JS = (RAIZ / "web" / "js" / "agente.js").read_text(encoding="utf-8")
IMPORTAR_JS = (RAIZ / "web" / "js" / "vistas" / "importar.js").read_text(encoding="utf-8")
DOCS = (RAIZ / "docs" / "agente.md").read_text(encoding="utf-8")
README = (RAIZ / "README.md").read_text(encoding="utf-8")
AVISO = ("Solo planillas o listas. No fotografíe cédulas. Tape columnas de salud, etnia, víctima o políticas. Borre la "
         "foto del teléfono.")


def _aviso_js(codigo: str) -> str:
    crudo = re.search(r"const AVISO_FOTOS = ('[^']*'\s*\+\s*'[^']*');", codigo).group(1)
    return re.sub(r"'\s*\+\s*'", "", crudo).strip("'")


def _plano(texto: str) -> str:
    return re.sub(r"\s+", " ", texto)


def test_el_lector_no_transcribe_las_columnas_politicas():
    no_va = lector_planillas.INSTRUCCIONES.split("LO QUE NO SE TRANSCRIBE", 1)[1].split("PRIMERO CLASIFICA", 1)[0]
    assert "Datos políticos" in no_va and "tipo de persona" in no_va and "Esas columnas se omiten por completo" in no_va


def test_el_aviso_de_la_camara_pide_tapar_las_columnas_politicas():
    assert _aviso_js(AGENTE_JS) == AVISO and _aviso_js(IMPORTAR_JS) == AVISO
    # Nada dice que las columnas políticas de la foto se leen: el lector las omite
    assert "políticas sí se leen" not in AGENTE_JS and "las políticas ya no se piden tapar" not in DOCS


def test_el_asistente_pide_la_foto_con_las_columnas_politicas_tapadas():
    planillas = "\n".join(sistema.PLANILLAS)
    assert "con las columnas de salud, etnia, víctima o políticas tapadas" in planillas
    assert "El tipo de persona y el líder no se leen de la foto" in planillas


def test_la_documentacion_dice_el_mismo_aviso():
    docs, readme = _plano(DOCS), _plano(README)
    assert f"«{AVISO}»" in docs
    assert "tapar las columnas de salud, etnia, víctima o políticas" in docs
    assert "tapar las columnas de salud, etnia, víctima o políticas" in readme
    for texto in (docs, readme):
        assert "etnia o víctima. Borre" not in texto and "columnas de salud, etnia o víctima" not in texto


def test_la_documentacion_no_dice_que_la_analitica_nunca_nombra_personas():
    # El código: una tabla por `lider` nombra a los líderes y los anota como personas de la conversación
    out = {"dimensiones": ["lider"], "filas": [{"valor": 7, "etiqueta": "LIDER INVENTADO (Líder)"},
                                               {"valor": "sin_lider", "etiqueta": "Sin líder"}]}
    assert analisis.lideres_de(out) == {7}
    fila = next(linea for linea in DOCS.splitlines() if linea.startswith("| `analizar` |"))
    assert "Nunca personas:" not in fila and "salvo los líderes" in fila and "`Resultado.personas`" in fila
    docs = _plano(DOCS)
    assert "solo agregados ya protegidos: ninguna persona, las cifras" not in docs
    assert ("solo agregados ya protegidos: ninguna persona (salvo, con los datos políticos, los líderes de 10 o más "
            "personas que nombra una tabla por `lider`)") in docs
    # Por MCP, esa tabla solo con `lectura` (el coordinador nunca la tiene: test_revision_politicos_mcp.py)
    assert "A y K, la analítica por tipo, líder o lista" not in docs
    assert "La tabla por `lider` nombra a cada líder (es entregar personas): por MCP solo con `lectura`" in docs
