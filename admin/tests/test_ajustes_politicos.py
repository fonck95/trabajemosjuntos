"""El ajuste `agente_politicos` (app/modelo.py, app/agente/politica.py, app/api/ajustes.py, app/acceso.py y
web/js/vistas/ajustes.js): si el asistente (`asistente`) y los agentes por MCP (`mcp`) reciben los datos políticos que
el panel ya muestra a cada rol. Encendidos por defecto; booleanos estrictos; un ajuste de permisos (solo el
administrador lo cambia, el coordinador lo ve en solo lectura); lo guardado a mano que no tiene la forma esperada
rige como su valor por defecto. Solo datos inventados."""
import re
from pathlib import Path

import pytest

from app import acceso, modelo
from app.agente import politica
from app.api import ajustes as api_ajustes
from ayudas_g3 import coordinador

AJUSTES_JS = (Path(__file__).resolve().parents[1] / "web" / "js" / "vistas" / "ajustes.js").read_text(encoding="utf-8")
DEFECTO = {"asistente": True, "mcp": True}


def _sin_comentarios(texto: str) -> str:
    return "\n".join("" if l.lstrip().startswith(("//", "*", "/*")) else l for l in texto.splitlines())


@pytest.fixture
def coord(sesion):
    k = coordinador(sesion.app, sesion.app.state.db)
    yield k
    k.close()


# ───────────────────────────── La lectura ─────────────────────────────

def test_valores_por_defecto_y_los_dos_lados_iguales():
    assert modelo.AJUSTES_POR_DEFECTO["agente_politicos"] == DEFECTO == politica.POLITICOS_POR_DEFECTO
    assert politica.VIAS_POLITICOS == ("asistente", "mcp")
    assert set(api_ajustes.PoliticosAgente.model_fields) == set(politica.VIAS_POLITICOS)
    assert "agente_politicos" in acceso.AJUSTES_DE_PERMISOS
    assert politica.ajustes_politicos(None) == DEFECTO and politica.ajustes_politicos({}) == DEFECTO


@pytest.mark.parametrize("guardado,esperado", [
    ({"asistente": False}, {"asistente": False, "mcp": True}),
    ({"mcp": False, "asistente": False}, {"asistente": False, "mcp": False}),
    ({"asistente": "false", "mcp": 0}, DEFECTO),  # solo booleanos de verdad
    ({"asistente": None, "mcp": 1}, DEFECTO),
    ("apagado", DEFECTO), (["asistente"], DEFECTO), (None, DEFECTO),
    ({"asistente": False, "otra": True}, {"asistente": False, "mcp": True}),
])
def test_lo_guardado_se_valida(guardado, esperado):
    aj = {"agente_politicos": guardado}
    assert politica.ajustes_politicos(aj) == esperado
    assert politica.usa_politicos(aj, "chat") is esperado["asistente"]
    assert politica.usa_politicos(aj, None) is esperado["asistente"]
    assert politica.usa_politicos(aj, "mcp") is esperado["mcp"]


def test_leer_lo_deja_validado(sesion):
    db = sesion.app.state.db
    assert politica.leer(db)[0]["agente_politicos"] == DEFECTO
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"agente_politicos": {"asistente": "no", "mcp": False}}},
                       upsert=True)
    aj, _ = politica.leer(db)
    assert aj["agente_politicos"] == {"asistente": True, "mcp": False}
    # GET /api/ajustes muestra lo que rige (no lo escrito a mano)
    assert sesion.get("/api/ajustes").json()["agente_politicos"] == {"asistente": True, "mcp": False}


# ───────────────────────────── PUT /api/ajustes ─────────────────────────────

def test_el_administrador_lo_cambia_por_partes(sesion):
    r = sesion.put("/api/ajustes", json={"agente_politicos": {"mcp": False}})
    assert r.status_code == 200, r.text
    assert r.json()["agente_politicos"] == {"asistente": True, "mcp": False}
    r = sesion.put("/api/ajustes", json={"agente_politicos": {"asistente": False}})
    assert r.json()["agente_politicos"] == {"asistente": False, "mcp": False}
    db = sesion.app.state.db
    assert modelo.leer_ajustes(db)["agente_politicos"] == {"asistente": False, "mcp": False}
    assert "agente_politicos" in str(db.auditoria.find_one({"accion": "ajustes"}, sort=[("_id", -1)])["detalle"])
    # Lo que manda el formulario, entero
    r = sesion.put("/api/ajustes", json={"agente_politicos": {"asistente": True, "mcp": True}})
    assert r.json()["agente_politicos"] == DEFECTO


@pytest.mark.parametrize("cuerpo", [
    {"agente_politicos": {"asistente": "true"}}, {"agente_politicos": {"mcp": 1}},
    {"agente_politicos": {"otra": True}}, {"agente_politicos": True}, {"agente_politicos": ["mcp"]},
])
def test_valores_invalidos_422(sesion, cuerpo):
    assert sesion.put("/api/ajustes", json=cuerpo).status_code == 422


def test_el_coordinador_lo_ve_y_no_lo_cambia(sesion, coord):
    a = coord.get("/api/ajustes").json()
    assert a["agente_politicos"] == DEFECTO and "agente_politicos" in a["ajustes_de_permisos"]
    r = coord.put("/api/ajustes", json={"agente_politicos": {"mcp": False}})
    assert r.status_code == 403 and r.json()["detail"]["codigo"] == "permiso"
    assert r.json()["detail"]["campos"] == ["agente_politicos"]
    # Reenviar lo que ve no es un cambio
    assert coord.put("/api/ajustes", json={"agente_politicos": DEFECTO}).status_code == 200
    assert sesion.get("/api/ajustes").json()["agente_politicos"] == DEFECTO


def test_planillero_y_consultor_no_lo_ven(como):
    for rol in ("planillero", "consultor"):
        c = como(rol)
        assert c.get("/api/ajustes").status_code == 403
        assert c.put("/api/ajustes", json={"agente_politicos": {"mcp": False}}).status_code == 403


# ───────────────────────────── La vista ─────────────────────────────

def test_el_formulario_de_ajustes():
    codigo = _sin_comentarios(AJUSTES_JS)
    assert "<h2>Datos políticos en el asistente y por MCP</h2>" in codigo and 'id="f-politicos"' in codigo
    assert "${casilla('politicos_asistente', po.asistente !== false," in codigo
    assert "${casilla('politicos_mcp', po.mcp !== false," in codigo
    assert ("${soloLectura ? SOLO_ADMIN : html`<div class=\"ancho\"><button class=\"btn primario\">"
            "Guardar datos políticos</button></div>`}") in codigo
    # Lo que manda: los dos booleanos del modelo, y nada más
    inicio = codigo.index("} else if (f.id === 'f-politicos') {")
    rama = codigo[inicio:codigo.index("} catch (err) { avisoError(err); }", inicio)]
    assert ("agente_politicos: { asistente: v.politicos_asistente === true, mcp: v.politicos_mcp === true }"
            in rama)
    assert set(re.findall(r"(\w+): v\.politicos_", rama)) == set(api_ajustes.PoliticosAgente.model_fields)
    # El coordinador lo ve en solo lectura
    solo = codigo[codigo.index("if (soloLectura) {"):]
    assert "for (const id of ['#f-planillas', '#f-mcp', '#f-politicos']) {" in solo[:solo.index("const dePermisos")]
    # La nota legal: dato sensible, solo a quien ya lo ve en el panel, terceros, y nunca quien no autorizó ni lo sensible
    texto = re.sub(r"\s+", " ", codigo[codigo.index('id="f-politicos"'):codigo.index("Guardar datos políticos")])
    for frase in ("La orientación política es un dato sensible (Ley 1581 de 2012, art. 5).",
                  "solo la muestra a los roles que ya la ven en el panel", "proveedor del modelo",
                  "Quien no autorizó y los datos de salud, etnia, discapacidad o víctima nunca salen."):
        assert frase in texto, frase
