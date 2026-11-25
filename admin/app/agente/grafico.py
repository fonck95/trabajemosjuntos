"""El gráfico que una herramienta muestra en el chat del asistente (acción `{"tipo": "grafico", …}`).

Lo arma el servidor con las cifras que calculó (la analítica, `herramientas/analisis.py`): el modelo no escribe los
números del gráfico. El bucle lo valida aquí antes de mandarlo al navegador y lo guarda con el estado de la
herramienta en el historial (`bucle.Turno._ui`), así se ve también al repintar la conversación. El navegador lo vuelve a
validar (`web/js/agente-graficos.js`) y lo dibuja con `web/js/graficos.js`, con los colores de su paleta.

Forma (todo lo demás se descarta):

    {"tipo": "grafico", "clase": "barras" | "columnas" | "apilada" | "serie", "titulo": str (≤ 120),
     "unidad": str (≤ 30), "items": [{"etiqueta": str (≤ 60), "valor": número ≥ 0, "texto"?: str (≤ 40)}] (1–60),
     "nota"?: str (≤ 200)}

`serie` es una secuencia de periodos en orden (días, semanas o meses) y las demás, categorías. Un ítem oculto por la
supresión de celdas pequeñas no se manda: lo dice la `nota`. Sin datos personales: los gráficos son de agregados.
"""
from __future__ import annotations

import math
import re
from typing import Any

CLASES = ("barras", "columnas", "apilada", "serie")
MAX_ITEMS = 60
TITULO_MAX, UNIDAD_MAX, ETIQUETA_MAX, TEXTO_MAX, NOTA_MAX = 120, 30, 60, 40, 200
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f  ​-‏‪-‮⁠-⁩﻿]")


def _texto(v: Any, n: int) -> str | None:
    if not isinstance(v, str):
        return None
    v = " ".join(_CONTROL.sub(" ", v).split())
    return v[:n] if v else None


def validar(a: Any) -> dict | None:
    """El gráfico limpio, o None si no cumple el contrato (sin clase conocida, sin título o sin ítems válidos)."""
    if not isinstance(a, dict) or a.get("clase") not in CLASES:
        return None
    titulo = _texto(a.get("titulo"), TITULO_MAX)
    items = []
    for it in a.get("items") if isinstance(a.get("items"), list) else []:
        if not isinstance(it, dict):
            continue
        etiqueta, valor = _texto(it.get("etiqueta"), ETIQUETA_MAX), it.get("valor")
        if etiqueta is None or isinstance(valor, bool) or not isinstance(valor, (int, float)):
            continue
        if not math.isfinite(valor) or valor < 0:
            continue
        x: dict[str, Any] = {"etiqueta": etiqueta, "valor": round(float(valor), 4) if isinstance(valor, float) else valor}
        texto = _texto(it.get("texto"), TEXTO_MAX)
        if texto:
            x["texto"] = texto
        items.append(x)
        if len(items) >= MAX_ITEMS:
            break
    if not titulo or not items:
        return None
    out: dict[str, Any] = {"tipo": "grafico", "clase": a["clase"], "titulo": titulo,
                           "unidad": _texto(a.get("unidad"), UNIDAD_MAX) or "", "items": items}
    nota = _texto(a.get("nota"), NOTA_MAX)
    if nota:
        out["nota"] = nota
    return out
