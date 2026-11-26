"""Ajustes → «Planillas físicas por foto» (`agente_planillas`) y «Agentes externos por MCP» (`agente_mcp`), en
web/js/vistas/ajustes.js: los roles y los rangos del formulario son los del servidor (`agente.politica` y
`api/ajustes.py`), lo que manda cada formulario lo acepta PUT /api/ajustes tal cual y se ve igual al volver, el
coordinador los ve en solo lectura (y el servidor le responde 403) y guardar las planillas le avisa al asistente (quién
adjunta fotos sale de su estado). Las pruebas de la sección del asistente siguen en test_agente_ajustes.py y
test_agente_web.py. Solo datos inventados.
"""
import re
from pathlib import Path

import pytest

from ayudas_g3 import coordinador
from app.agente import politica
from app.api import ajustes as api_ajustes

AJUSTES = (Path(__file__).resolve().parents[1] / "web" / "js" / "vistas" / "ajustes.js").read_text(encoding="utf-8")


def _sin_comentarios(texto: str) -> str:
    return "\n".join("" if l.lstrip().startswith(("//", "*", "/*")) else l for l in texto.splitlines())


CODIGO = _sin_comentarios(AJUSTES)


def _rama(form: str) -> str:
    """Lo que hace el envío del formulario `form` (su rama en el escucha de `submit`)."""
    inicio = CODIGO.index(f"}} else if (f.id === '{form}') {{")
    fin = CODIGO.find("} else if (f.id ===", inicio + 10)
    return CODIGO[inicio:fin if fin > 0 else CODIGO.index("} catch (err) { avisoError(err); }", inicio)]


@pytest.fixture
def coord(sesion):
    k = coordinador(sesion.app, sesion.app.state.db)
    yield k
    k.close()


# ───────────────────────────── Los formularios, como los valida el servidor ─────────────────────────────

def test_roles_y_rangos_son_los_del_servidor():
    def roles(nombre):
        return tuple(re.findall(r"\['(\w+)', '", re.search(rf"const {nombre} = \[(.*?)\];", CODIGO, re.S).group(1)))

    assert roles("ROLES_PLANILLAS") == politica.ROLES_PLANILLAS
    assert roles("ROLES_MCP") == politica.ROLES_MCP

    def rango(nombre):
        return tuple(map(int, re.search(rf"const {nombre} = \[(\d+), (\d+)\];", CODIGO).groups()))

    assert rango("RETENCION_HORAS") == politica.RETENCION_HORAS
    assert rango("LLAMADAS_MCP") == politica.LLAMADAS_DIARIAS_MCP
    assert rango("PERSONAS_MCP") == politica.PERSONAS_DIARIAS_MCP
    # Los campos de número usan esos rangos
    assert ("numero('retencion_horas', pl.retencion_horas, 'Horas que se guardan la foto y lo leído', "
            "RETENCION_HORAS[0], RETENCION_HORAS[1])") in CODIGO
    assert ("numero('llamadas_diarias', mc.llamadas_diarias, 'Llamadas por clave y día', LLAMADAS_MCP[0], "
            "LLAMADAS_MCP[1])") in CODIGO
    assert ("numero('personas_diarias', mc.personas_diarias, 'Personas distintas por clave y día', PERSONAS_MCP[0], "
            "PERSONAS_MCP[1])") in CODIGO


def test_cada_formulario_manda_los_campos_del_modelo():
    planillas = _rama("f-planillas")
    cuerpo = planillas[planillas.index("agente_planillas: {"):planillas.index("'Planillas por foto guardadas'")]
    claves = set(re.findall(r"(\w+)(?::|,|\s*\})", cuerpo))
    assert set(api_ajustes.PlanillasAgente.model_fields) <= claves
    assert "agente_planillas: { roles, retencion_horas: Number(v.retencion_horas) } }" in planillas
    # `otros_formatos` se retiró (toda foto se describe y se lee toda hoja que liste personas): ni la casilla ni el
    # campo en lo que se manda
    assert "otros_formatos" not in CODIGO and "otros formatos" not in CODIGO
    assert set(api_ajustes.PlanillasAgente.model_fields) == {"roles", "retencion_horas"}
    mcp = _rama("f-mcp")
    assert ("agente_mcp: { roles, escritura: v.mcp_escritura === true,\n"
            "          llamadas_diarias: Number(v.llamadas_diarias), personas_diarias: Number(v.personas_diarias) } }"
            ) in mcp
    assert set(api_ajustes.McpAgente.model_fields) == {"roles", "escritura", "llamadas_diarias", "personas_diarias"}
    # Guardar las planillas le avisa al asistente (su estado dice quién adjunta fotos); el de MCP no lo cambia
    assert planillas.index("await guardar(") < planillas.index("avisarAlAsistente();")
    assert "avisarAlAsistente" not in mcp


def test_el_coordinador_los_ve_en_solo_lectura():
    assert 'id="f-planillas"' in CODIGO and 'id="f-mcp"' in CODIGO
    assert "<h2>Planillas físicas por foto</h2>" in CODIGO and "<h2>Agentes externos por MCP</h2>" in CODIGO
    solo = CODIGO[CODIGO.index("if (soloLectura) {"):]
    assert "for (const id of ['#f-planillas', '#f-mcp', '#f-politicos']) {" in solo[:solo.index("const dePermisos")]
    # Sin botón para el coordinador: el aviso de solo lectura
    for boton in ("Guardar planillas por foto", "Guardar agentes por MCP"):
        assert ("${soloLectura ? SOLO_ADMIN : html`<div class=\"ancho\"><button class=\"btn primario\">"
                f"{boton}</button></div>`}}") in CODIGO
    # Lo que se dice: la foto entera va al proveedor del modelo, las autorizaciones se confirman con el papel, nada de
    # cédulas; por MCP, terceros que el panel no controla y las claves vencen
    texto = re.sub(r"\s+", " ", CODIGO)
    for frase in ("La foto entera, con cédulas, teléfonos y firmas de habitantes, viaja al proveedor del modelo",
                  "«declaradas en planilla»", "Nunca se leen fotos de cédulas.",
                  "terceros que el panel no controla", "Las claves de datos vencen a los 30 días"):
        assert frase in texto, frase


# ───────────────────────────── Lo que mandan, contra la API ─────────────────────────────

def test_lo_que_manda_el_formulario_se_guarda_y_se_ve_igual(sesion, coord):
    """El cuerpo que arma cada formulario (como en `_rama`): PUT /api/ajustes lo acepta y GET lo devuelve igual. El
    coordinador lo lee y recibe 403 al guardarlo."""
    planillas = {"roles": ["admin", "coordinador"], "retencion_horas": 48}
    mcp = {"roles": ["admin", "coordinador"], "escritura": False, "llamadas_diarias": 500, "personas_diarias": 50}
    # Un formulario de antes que todavía manda `otros_formatos` (el ajuste se retiró) se acepta: el valor no se guarda
    r = sesion.put("/api/ajustes", json={"agente_planillas": {**planillas, "otros_formatos": True}})
    assert r.status_code == 200, r.text
    r = sesion.put("/api/ajustes", json={"agente_mcp": mcp})
    assert r.status_code == 200, r.text
    a = sesion.get("/api/ajustes").json()
    assert a["agente_planillas"] == planillas and a["agente_mcp"] == mcp
    # Sin ningún rol marcado: apagado para todos (también se acepta)
    r = sesion.put("/api/ajustes", json={"agente_planillas": {**planillas, "roles": []}})
    assert r.status_code == 200 and sesion.get("/api/ajustes").json()["agente_planillas"]["roles"] == []
    # Fuera de rango (lo que el formulario no deja escribir): 422
    for cuerpo in ({"agente_planillas": {"retencion_horas": 169}}, {"agente_mcp": {"llamadas_diarias": 9}},
                   {"agente_mcp": {"personas_diarias": 5001}}, {"agente_planillas": {"roles": ["consultor"]}},
                   {"agente_planillas": {"roles": ["planillero"]}}, {"agente_mcp": {"roles": ["planillero"]}}):
        assert sesion.put("/api/ajustes", json=cuerpo).status_code == 422, cuerpo
    # El coordinador los ve (para la vista en solo lectura) y no los puede cambiar
    k = coord.get("/api/ajustes")
    assert k.status_code == 200 and k.json()["agente_planillas"]["retencion_horas"] == 48
    for cuerpo in ({"agente_planillas": {**planillas, "retencion_horas": 2}},
                   {"agente_mcp": {**mcp, "escritura": True}}):
        r = coord.put("/api/ajustes", json=cuerpo)
        assert r.status_code == 403, (cuerpo, r.text)
    assert sesion.get("/api/ajustes").json()["agente_mcp"] == mcp
