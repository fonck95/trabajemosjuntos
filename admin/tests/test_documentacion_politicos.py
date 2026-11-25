"""Las instrucciones del asistente sobre los datos políticos (app/agente/sistema.py), según el ajuste
`agente_politicos` y el rol: docs/agente.md, «Datos políticos».

Se prueba, sin MongoDB ni modelo:
* que las reglas de los datos políticos van solo si la conversación tiene sus herramientas (`lideres`, `marcar_tipo`,
  `asignar_lider`, que solo se ofrecen con `agente_politicos.asistente` encendido y a A, K y P), y que si no, el
  `system` dice que no le llegan (como antes);
* que con ellas ya no dice que no están a su alcance, y que cada rol recibe lo que ve en el panel (A y K, todo; P, el
  tipo y el «Liderado por» en las fichas de su zona, y solo suma; C, nada);
* que las reglas dicen lo que importa: dato sensible (art. 5), no inferir ni adivinar la afiliación, no excluir ni
  presionar, nada en la presentación ni con la voz clonada, quien no autorizó no aparece, marcar solo lo dictado;
* que la analítica por tipo, líder o lista va con la misma supresión y lo sensible sigue fuera;
* que la puerta (`HERRAMIENTAS_POLITICAS`) son justo las herramientas del catálogo que dependen del ajuste.
"""
from __future__ import annotations

import re

import pytest

from app import acceso
from app.agente import herramientas as H
from app.agente import politica, sistema
from app.agente.herramientas import base

LA_DE_SENSIBLES = ("- Úsalos solo para la tarea pedida. Los datos sensibles de salud, etnia, discapacidad y condición "
                   "de víctima no están a tu alcance: no los pidas ni los deduzcas.")


def _quien(rol: str) -> acceso.Quien:
    return acceso.Quien(uid=11, usuario="u11", nombre="Beto Inventado", rol=rol, permisos=acceso.PERMISOS[rol])


def _ofrecidas(rol: str, *, asistente: bool = True, mcp: bool = True, escritura: bool = True) -> list:
    """Las herramientas del catálogo que se le ofrecen a `rol` en el chat, con el asistente encendido para todos."""
    ajustes = {"agente_planillas": politica.ajustes_planillas({}),
               "agente_politicos": politica.ajustes_politicos({"agente_politicos": {"asistente": asistente,
                                                                                    "mcp": mcp}})}
    agente = politica.ajustes_agente({"agente": {"roles": list(politica.ROLES), "escritura": escritura}})
    return [h for h in H.fijas() if politica.ofrecida(h, _quien(rol), agente, None, ajustes=ajustes)]


def _texto(rol: str, **kw) -> str:
    return sistema.texto(_quien(rol), _ofrecidas(rol, **kw))


# ───────────────────────────── La puerta ─────────────────────────────

def test_la_puerta_son_las_herramientas_que_dependen_del_ajuste():
    del_ajuste = {h.nombre for h in H.fijas() if getattr(h, "disponible_ajustes", None) is base.politicos_ofrecidos}
    assert del_ajuste == set(sistema.HERRAMIENTAS_POLITICAS) == {"lideres", "marcar_tipo", "asignar_lider"}
    assert sistema.con_politicos({"lideres"}) and sistema.con_politicos({"marcar_tipo", "buscar_personas"})
    assert not sistema.con_politicos({"buscar_personas", "ver_persona", "analizar"})
    assert sistema.politicos({"buscar_personas"}, "admin") == []


@pytest.mark.parametrize("rol", ["admin", "coordinador", "planillero"])
def test_quien_los_ve_en_el_panel_recibe_sus_herramientas_con_el_ajuste_encendido(rol):
    nombres = {h.nombre for h in _ofrecidas(rol)}
    assert set(sistema.HERRAMIENTAS_POLITICAS) <= nombres
    apagado = {h.nombre for h in _ofrecidas(rol, asistente=False)}
    assert not set(sistema.HERRAMIENTAS_POLITICAS) & apagado
    # El ajuste de MCP no decide lo del chat
    assert set(sistema.HERRAMIENTAS_POLITICAS) <= {h.nombre for h in _ofrecidas(rol, mcp=False)}


def test_el_consultor_nunca_recibe_nada_politico():
    assert not set(sistema.HERRAMIENTAS_POLITICAS) & {h.nombre for h in _ofrecidas("consultor")}
    c = _texto("consultor")
    assert sistema.SIN_POLITICOS in c and sistema.POLITICOS_TITULO not in c
    assert sistema.POLITICOS_AK not in c and sistema.POLITICOS_P not in c


# ───────────────────────────── Lo que recibe cada rol ─────────────────────────────

@pytest.mark.parametrize("rol", ["admin", "coordinador"])
def test_a_y_k_con_el_ajuste_reciben_todo_y_sus_reglas(rol):
    t = _texto(rol)
    assert f"\n\n{sistema.POLITICOS_TITULO}\n{sistema.POLITICOS_AK}\n" in t
    for linea in (*sistema.POLITICOS_REGLAS, sistema.POLITICOS_MARCAR, sistema.ANALISIS_POLITICOS, LA_DE_SENSIBLES):
        assert linea in t, linea
    for linea in (sistema.SIN_POLITICOS, sistema.POLITICOS_P, sistema.ANALISIS_SIN_POLITICOS):
        assert linea not in t, linea
    # Ya no dice que lo político no está a su alcance, ni lo cuenta entre lo sensible que no ve
    assert "tampoco están a tu alcance" not in t and "afiliación política) y las listas de origen" not in t
    assert "ni listas" not in t and "Lo político y lo sensible" not in t
    for parte in ("el tipo de persona (líder, votante, concejal)", "«Liderado por»", "las listas de origen",
                  "las bases de cédulas y general", "`lideres`", "filtrar por tipo, líder y lista"):
        assert parte in sistema.POLITICOS_AK, parte


def test_el_planillero_con_el_ajuste_ve_solo_lo_de_su_zona_y_solo_suma():
    p = _texto("planillero")
    assert f"\n\n{sistema.POLITICOS_TITULO}\n{sistema.POLITICOS_P}\n" in p
    assert all(linea in p for linea in (*sistema.POLITICOS_REGLAS, sistema.POLITICOS_MARCAR))
    assert sistema.POLITICOS_AK not in p and sistema.SIN_POLITICOS not in p
    assert "Análisis de la base" not in p and "Planillas físicas por foto" not in p
    for parte in ("solo en la ficha de las personas de su zona o que registró", "no en búsquedas ni listas",
                  "no filtras por ellos", "Solo sumas", "`lideres`", "quitarlos es del administrador o el coordinador",
                  "Las listas de origen y los conteos por líder no los ves"):
        assert parte in sistema.POLITICOS_P, parte


@pytest.mark.parametrize("rol", ["admin", "coordinador", "planillero"])
def test_con_el_ajuste_apagado_queda_como_antes(rol):
    t = _texto(rol, asistente=False)
    assert sistema.SIN_POLITICOS in t and sistema.POLITICOS_TITULO not in t and LA_DE_SENSIBLES in t
    assert sistema.POLITICOS_MARCAR not in t and all(linea not in t for linea in sistema.POLITICOS_REGLAS)
    if rol != "planillero":
        assert sistema.ANALISIS_SIN_POLITICOS in t and sistema.ANALISIS_POLITICOS not in t
    # La línea de lo que no le llega va con los datos personales, justo después de la de lo sensible
    assert f"{LA_DE_SENSIBLES}\n{sistema.SIN_POLITICOS}\n" in t


@pytest.mark.parametrize("rol", ["admin", "planillero"])
def test_sin_escrituras_no_le_habla_de_marcar(rol):
    t = _texto(rol, escritura=False)
    assert sistema.POLITICOS_TITULO in t and sistema.POLITICOS_MARCAR not in t
    assert "`marcar_tipo`" not in t and "`asignar_lider`" not in t


def test_la_seccion_va_despues_de_los_datos_personales_y_antes_de_las_demas():
    t = _texto("admin")
    i_datos, i_pol = t.index("Datos personales (Ley 1581 de 2012)"), t.index(sistema.POLITICOS_TITULO)
    assert i_datos < i_pol < t.index("Análisis de la base") < t.index("Formato: respuestas cortas")
    assert t.count(sistema.POLITICOS_TITULO) == 1


# ───────────────────────────── Lo que dicen ─────────────────────────────

def test_las_reglas_dicen_lo_que_importa():
    reglas = "\n".join([sistema.POLITICOS_TITULO, *sistema.POLITICOS_REGLAS, sistema.POLITICOS_MARCAR])
    for parte in ("dato sensible, Ley 1581 de 2012, art. 5", "solo para la tarea pedida",
                  "Nunca infieras ni adivines la afiliación política de nadie", "si no está marcada, no la sabes",
                  "Quien no autorizó no aparece en nada político", "Nunca los uses para excluir, presionar ni "
                  "condicionar a nadie", "señalar a quien no apoya", "el contacto depende de la autorización",
                  "Nunca los pongas en la presentación ni en la pantalla en off", "voz clonada",
                  "solo con lo que te dice la persona del equipo, nunca por deducción",
                  "no los escribas en notas ni en otros campos de texto"):
        assert parte in reglas, parte


def test_la_analitica_politica_va_con_la_misma_supresion_y_sin_lo_sensible():
    a = sistema.ANALISIS_POLITICOS
    for parte in ("`tipo`, `lider`, `lista`", "con la misma supresión", "lo oculto no se deduce",
                  "menos de 10 personas van juntos", "Lo sensible (salud, etnia, discapacidad, víctima) nunca"):
        assert parte in a, parte
    s = "\n".join(sistema.secciones({"analizar", "lideres"}))
    assert a in s and sistema.ANALISIS_SIN_POLITICOS not in s
    s = "\n".join(sistema.secciones({"diagnostico"}))
    assert sistema.ANALISIS_SIN_POLITICOS in s and a not in s
    # Las dimensiones que nombra existen en el motor
    from app import analitica
    assert set(re.findall(r"`([a-z_]+)`", a)) == set(analitica.DIM_POLITICAS)


def test_lo_que_nombran_existe_y_sigue_sin_fecha():
    catalogo = {h.nombre for h in H.fijas()}
    for texto in (sistema.POLITICOS_AK, sistema.POLITICOS_P, *sistema.POLITICOS_REGLAS, sistema.POLITICOS_MARCAR):
        for palabra in re.findall(r"`([a-z_]+)`", texto):
            assert palabra in catalogo, palabra
    for rol in ("admin", "planillero"):
        t = _texto(rol)
        assert sorted(set(re.findall(r"\b(?:19|20)\d\d\b", t))) == ["2012"]
        assert t == _texto(rol)
