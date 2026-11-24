"""Los datos políticos en `minimizar` (decisión del dueño: ya no se le ocultan al modelo): con `Politicos` pasan los que
la API ya le dio al rol (el tipo, el «Liderado por», las listas y las fuentes), sin nombrar a un líder que no autorizó;
sin `Politicos` (el ajuste `agente_politicos` apagado) no pasan, como antes. Lo sensible y la forma de quien no
autorizó no cambian. Solo datos inventados."""
from __future__ import annotations

import json

from app.agente import minimizar

POL = minimizar.Politicos(no_autorizaron=frozenset({77}), traidas={"total": 12, "compartidas": 2})


def _fila_ak() -> dict:
    """Una fila de Habitantes como la da la API a A y K (con `cargar_lideres`)."""
    return {"id": 4, "nombre": "ANA INVENTADA", "cedula": "91000777", "telefono": "3009990011", "lider": True,
            "votante": False, "concejal": False, "lideres_n": 2, "fuentes": ["tramites", "general"],
            "lideres": [{"id": 9, "nombre": "LIDER INVENTADO", "tipo": "lider"},
                        {"id": 77, "nombre": "LIDER QUE NO AUTORIZO", "tipo": "concejal"}],
            "consentimiento": "si", "menor": False, "lugar": "EL PRADO", "lugar_tipo": "barrio"}


def _ficha_ak() -> dict:
    return {"id": 4, "nombre": "ANA INVENTADA", "cedula": "91000777", "consentimiento": "si", "lider": True,
            "votante": True, "concejal": False, "listas": ["Lista Inventada 300 111 22 33", 5],
            "fuentes": ["tramites", "cedulas"], "cedula_origen": "cedulas", "traidas": {"total": 40, "compartidas": 9},
            "lideres": [{"id": 9, "nombre": "LIDER INVENTADO", "tipo": "lider", "marcado": True,
                         "asignado_en": "2026-11-01T00:00:00+00:00", "asignado_por": "coordinador7"},
                        {"id": 77, "nombre": "LIDER QUE NO AUTORIZO", "tipo": "concejal", "marcado": True}],
            "editables": ["nombre", "lider", "concejal"], "faltan": ["cedula", "lideres"],
            "sensibles": {"etnia": "Raizal"}, "sensibles_registrados": ["etnia"], "regimen_salud": "Subsidiado",
            "extra": {"religion": "Pastafari", "talla": "M"}, "lugar_nombre": "EL PRADO"}


def test_fila_con_politicos_trae_el_tipo_y_el_liderado_por_sin_el_que_no_autorizo():
    f = minimizar.fila(_fila_ak(), politicos=POL)
    assert f["lider"] is True and f["votante"] is False and f["concejal"] is False
    assert f["lideres"] == [{"id": 9, "nombre": "LIDER INVENTADO", "tipo": "lider"}] and f["lideres_n"] == 1
    assert f["fuentes"] == ["tramites", "general"]
    assert "LIDER QUE NO AUTORIZO" not in json.dumps(f) and "91000777" not in json.dumps(f)
    assert f["cedula_ult3"] == "···777"
    # Los líderes que nombra van en Resultado.personas (los ids de la fila y de su «Liderado por»)
    assert minimizar.ids_lideres([f]) == {9}


def test_fila_sin_politicos_como_siempre():
    f = minimizar.fila(_fila_ak())
    assert not {"lider", "votante", "concejal", "lideres", "lideres_n", "fuentes"} & set(f)
    assert minimizar.fila(_fila_ak(), politicos=None) == f


def test_fila_sin_la_lista_de_lideres_conserva_el_conteo_de_la_api():
    """`/api/buscar` no carga los líderes: la fila trae solo `lideres_n`."""
    fila = {k: v for k, v in _fila_ak().items() if k != "lideres"}
    f = minimizar.fila(fila, politicos=minimizar.Politicos())
    assert f["lideres_n"] == 2 and "lideres" not in f


def test_ficha_con_politicos_y_lo_sensible_sigue_fuera():
    sens = minimizar.Sensibles(campos=frozenset({"religion"}))
    f = minimizar.ficha(_ficha_ak(), sens, politicos=POL)
    assert f["lider"] is True and f["votante"] is True and f["concejal"] is False
    assert f["lideres"] == [{"id": 9, "nombre": "LIDER INVENTADO", "tipo": "lider", "marcado": True}]
    assert f["listas"] == ["Lista Inventada ···233"]  # texto libre: los números largos enmascarados
    assert f["fuentes"] == ["tramites", "cedulas"] and f["cedula_origen"] == "cedulas"
    assert f["traidas"] == {"total": 12, "compartidas": 2}  # la de la herramienta (sin quienes no autorizaron)
    assert f["editables"] == ["nombre", "lider", "concejal"] and f["faltan"] == ["cedula", "lideres"]
    texto = json.dumps(f, ensure_ascii=False)
    for vedado in ("Raizal", "Subsidiado", "Pastafari", "coordinador7", "asignado_por", "sensibles", "regimen_salud",
                   "LIDER QUE NO AUTORIZO"):
        assert vedado not in texto, vedado
    assert f["extra"] == {"talla": "M"}


def test_ficha_sin_traidas_de_la_herramienta_no_trae_las_de_la_api():
    f = minimizar.ficha(_ficha_ak(), politicos=minimizar.Politicos())
    assert "traidas" not in f


def test_ficha_sin_politicos_como_siempre():
    f = minimizar.ficha(_ficha_ak())
    assert not {"lider", "votante", "concejal", "lideres", "listas", "fuentes", "cedula_origen", "traidas"} & set(f)
    assert f["editables"] == ["nombre"] and f["faltan"] == ["cedula"]


def test_de_quien_no_autorizo_solo_su_forma_con_o_sin_politicos():
    for d in ({**_ficha_ak(), "consentimiento": "no"}, {**_fila_ak(), "consentimiento": "no"}):
        for f in (minimizar.ficha(d, politicos=POL), minimizar.fila(d, politicos=POL)):
            assert set(f) == {"id", "nombre", "lugar", "consentimiento", "aviso"}
            assert f["aviso"] == minimizar.AVISO_NO_AUTORIZO


def test_ficha_del_planillero_fuera_de_su_zona_no_trae_nada_politico():
    """La API no le manda el tipo a P fuera de su zona: con `Politicos` tampoco se inventa nada."""
    d = {"id": 5, "nombre": "PERSONA INVENTADA", "consentimiento": "si", "editables": ["nombre"], "faltan": []}
    f = minimizar.ficha(d, politicos=minimizar.Politicos())
    assert not {"lider", "votante", "concejal", "lideres", "listas", "fuentes"} & set(f)


def test_lideres_recorta_y_descarta_lo_que_no_es_un_lider():
    v = [{"id": i, "nombre": f"LIDER INVENTADO {i}", "tipo": "lider"} for i in range(1, 15)]
    v += [{"id": True, "nombre": "x"}, {"nombre": "sin id"}, "texto", {"id": 77, "nombre": "OCULTO"}]
    out = minimizar.lideres(v, POL)
    assert len(out) == minimizar.LIDERES_MAX and all(isinstance(x["id"], int) for x in out)
    assert minimizar.ids_lideres([{"lideres": v}]) == set(range(1, 15)) | {77}
