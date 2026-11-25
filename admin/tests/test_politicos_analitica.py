"""Los datos políticos en la analítica (decisión del dueño: ya no se le ocultan al modelo): las dimensiones `tipo`,
`lider` y `lista`, sus filtros y las bases «cedulas» y «general» como filtro de `fuente`, solo para A y K con
`agente_politicos` encendido para la vía de la petición (el asistente, o MCP con su clave); si no, 403 `permiso`. Las
dimensiones son una partición, con la supresión exacta de siempre («<5» y las complementarias «oculta», sin quienes no
autorizaron) y sin nombrar nunca a un líder que no autorizó. Solo datos inventados."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import ayudas_agente as aa
import ayudas_analitica as ya
from ayudas_g3 import coordinador
from app import analitica as an
from app.agente.herramientas import analisis as ha

SIN = {"agente_politicos": {"asistente": False, "mcp": False}}


def _ajuste(db, asistente: bool, mcp: bool) -> None:
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"agente_politicos": {"asistente": asistente, "mcp": mcp}}},
                       upsert=True)


def _lider(i: int) -> list[dict]:
    return [{"id": i, "asignado_en": "2026-11-01T00:00:00+00:00", "asignado_por": "admin", "asignado_por_uid": 0}]


def _filas(t: dict) -> dict:
    return {f["valor"]: f for f in t["filas"]}


@pytest.fixture
def mundo(sesion):
    """41 personas vigentes que autorizaron (o pendientes) y 5 que no: un líder L1 que autorizó, un concejal L2 que no,
    20 votantes traídos por L1 (12 en la lista A), 6 traídas por L2, 3 líderes sin líder, 3 en la lista B y 8 personas
    de la base general y 2 de la base con cédula."""
    db = sesion.app.state.db
    l1 = ya.persona(db, nombre="LIDER INVENTADO UNO", lider=True, consentimiento="si", sexo="M")
    l2 = ya.persona(db, nombre="CONCEJAL INVENTADO NOAUTORIZA", concejal=True, consentimiento="no", sexo="M")
    filas = []
    for i in range(20):
        filas.append({"nombre": f"VOTANTE INVENTADA {i}", "votante": True, "lideres": _lider(l1),
                      "sexo": "F" if i % 2 else "M", **({"listas": ["Lista Inventada A"]} if i < 12 else {})})
    filas += [{"nombre": f"TRAIDA POR L2 INVENTADA {i}", "lideres": _lider(l2), "sexo": "F"} for i in range(6)]
    filas += [{"nombre": f"LIDER SUELTO INVENTADO {i}", "lider": True, "sexo": "M"} for i in range(3)]
    filas += [{"nombre": f"PERSONA LISTA B INVENTADA {i}", "listas": ["Lista Inventada B"], "sexo": "F"}
              for i in range(3)]
    filas += [{"nombre": f"PERSONA GENERAL INVENTADA {i}", "fuentes": ["general"], "sexo": "F"} for i in range(8)]
    ids = ya.personas(db, filas)
    no = ya.personas(db, [{"nombre": f"NOAUTORIZA INVENTADA {i}", "votante": True, "lideres": _lider(l1),
                           "listas": ["Lista Inventada A"], "consentimiento": "no"} for i in range(5)])
    # Dos de las «sueltas» vienen de la base con cédula
    db.personas.update_many({"_id": {"$in": ids[-2:]}}, {"$set": {"fuentes": ["cedulas"]}})
    return {"db": db, "l1": l1, "l2": l2, "ids": ids, "no": no}


POLITICAS = [
    {"tipo": "tabla", "dimensiones": ["tipo"]},
    {"tipo": "tabla", "dimensiones": ["lider"]},
    {"tipo": "tabla", "dimensiones": ["lista"]},
    {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"tipo": "votante"}},
    {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"lista": "Lista Inventada A"}},
    {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"fuente": "general"}},
    {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"fuente": "cedulas"}},
    {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"fuente": "ambas"}},
    {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"varios_lideres": True}},
    {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"sin_lider": True}},
    {"tipo": "diagnostico", "filtros": {"tipo": "votante"}},
]


@pytest.mark.parametrize("consulta", POLITICAS)
def test_apagado_lo_politico_es_403(sesion, mundo, consulta):
    _ajuste(mundo["db"], False, True)  # el del asistente apagado: la petición del panel (sin `via`) es del asistente
    estado, detalle = ya.error(sesion, consulta)
    assert estado == 403 and detalle["codigo"] == "permiso", consulta


def test_apagado_el_catalogo_y_la_fuente_como_antes(sesion, mundo):
    _ajuste(mundo["db"], False, False)
    c = sesion.get("/api/analitica/catalogo").json()
    assert not {"tipo", "lider", "lista"} & set(c["dimensiones"]["personas"])
    assert not set(an.FILTROS_POLITICOS) & set(c["filtros"]) and c["fuentes_filtro"] == list(an.FUENTES_SEGURAS)
    t = ya.consulta(sesion, tipo="tabla", dimensiones=["fuente"])
    assert set(_filas(t)) <= set(an.FUENTES_SEGURAS)
    assert '"general"' not in json.dumps(t) and '"cedulas"' not in json.dumps(t)


def test_encendido_tipo_lider_y_lista_con_supresion_y_sin_quien_no_autorizo(sesion, mundo):
    l1 = mundo["l1"]
    c = sesion.get("/api/analitica/catalogo").json()
    assert {"tipo", "lider", "lista"} <= set(c["dimensiones"]["personas"]) and "lider_id" in c["filtros"]
    assert {"cedulas", "general", "ambas"} <= set(c["fuentes_filtro"])
    t = ya.consulta(sesion, tipo="tabla", dimensiones=["tipo"])
    f = _filas(t)
    # L1 y las 3 sueltas son líderes (4: «<5») y, para que no se deduzca restando del total (41), la más chica de las
    # demás sale «oculta»; el concejal no autorizó: ni cuenta ni tiene grupo
    assert t["base"] == {"personas": 41}
    assert f["votante"]["personas"] == 20 and f["lider"]["personas"] == "<5" and f["sin_tipo"]["personas"] == "oculta"
    assert "concejal" not in f and f["votante"]["etiqueta"] == "Votante" and f["votante"]["pct"] == 48.8
    t = ya.consulta(sesion, tipo="tabla", dimensiones=["lider"])
    f = _filas(t)
    assert f[l1]["personas"] == 20 and f[l1]["etiqueta"] == "LIDER INVENTADO UNO (Líder)"
    assert f[an.LIDER_OCULTO]["personas"] == 6 and f[an.SIN_LIDER]["personas"] == 15 and t["nota"] == an.NOTA_LIDER
    texto = json.dumps(t, ensure_ascii=False)
    assert "CONCEJAL" not in texto and str(mundo["l2"]) not in {str(k) for k in f}
    t = ya.consulta(sesion, tipo="tabla", dimensiones=["lista"])
    f = _filas(t)
    # La lista B tiene 3 personas: va con las demás listas chicas («<5») y la lista A sale «oculta»
    assert set(f) == {"Lista Inventada A", "otras_listas", an.SIN_LISTA}
    assert f["otras_listas"]["personas"] == "<5" and f["Lista Inventada A"]["personas"] == "oculta"
    assert f[an.SIN_LISTA]["personas"] == 26 and "Lista Inventada B" not in json.dumps(t)
    # La fuente sigue sin las bases políticas (con ellas, el resto dejaría deducir un grupo chico)
    t = ya.consulta(sesion, tipo="tabla", dimensiones=["fuente"])
    assert set(_filas(t)) <= set(an.FUENTES_SEGURAS) and '"general"' not in json.dumps(t)
    # Dos dimensiones: tipo por sexo, con la supresión de las tablas de dos dimensiones
    # (o, si ni ocultando se protege, sin desglose)
    t = ya.consulta(sesion, tipo="tabla", dimensiones=["tipo", "sexo"])
    assert t["base"] == {"personas": 41} and (t.get("dispersas") is True or t["ocultas"] >= 1)
    t = ya.consulta(sesion, tipo="tabla", dimensiones=["sexo", "lider"])
    assert [c["valor"] for c in t["columnas"]][0] == l1 and t["filas"]
    # Ninguna celda de 1 a 4 sale como número
    for consulta in (["tipo"], ["lider"], ["lista"], ["tipo", "sexo"], ["lider", "zona"], ["sexo", "lider"]):
        t = ya.consulta(sesion, tipo="tabla", dimensiones=consulta)
        celdas = [x["personas"] for fila in t.get("filas") or [] for x in fila.get("celdas", [fila])]
        assert not any(isinstance(n, int) and 0 < n < an.MINIMO_CELDA for n in celdas), (consulta, t)


def test_encendido_filtros_politicos(sesion, mundo):
    l1, l2 = mundo["l1"], mundo["l2"]
    t = ya.consulta(sesion, tipo="tabla", dimensiones=["sexo"], filtros={"lider_id": l1})
    assert t["base"]["personas"] == 20
    t = ya.consulta(sesion, tipo="tabla", dimensiones=["sexo"], filtros={"tipo": "votante"})
    assert t["base"]["personas"] == 20 and t["filtros"] == {"tipo": "votante"}
    t = ya.consulta(sesion, tipo="tabla", dimensiones=["sexo"], filtros={"lista": "Lista Inventada A"})
    assert t["base"]["personas"] == 12
    # Menos de 10 personas: sin cifras, también con un filtro político
    for fuente in ("general", "cedulas"):
        assert ya.consulta(sesion, tipo="tabla", dimensiones=["sexo"], filtros={"fuente": fuente}) == an.POCAS
    # Un líder que no autorizó (o un id que no lidera): 422, el mismo mensaje
    for lid in (l2, mundo["ids"][-1], 999999):
        estado, detalle = ya.error(sesion, {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"lider_id": lid}})
        assert estado == 422 and detalle == an.LIDER_NO_USABLE, lid
    for mala in ({"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"sin_lider": False}},
                 {"tipo": "tabla", "dimensiones": ["tipo"], "filtros": {"tipo": "candidato"}},
                 {"tipo": "comparar", "metrica": "altas", "dimensiones": ["lider"]}):
        assert ya.error(sesion, mala)[0] == 422, mala
    # El embudo por tipo
    e = ya.consulta(sesion, tipo="embudo", dimensiones=["tipo"])
    assert e["dimension"] == "tipo" and {g["valor"] for g in e["grupos"]} >= {"votante"}


def test_planillero_y_consultor_siguen_sin_analitica(sesion, como, mundo):
    for rol in ("planillero", "consultor"):
        r = como(rol).get("/api/analitica", params={"consulta": json.dumps({"tipo": "tabla",
                                                                             "dimensiones": ["tipo"]})})
        assert r.status_code == 403


def test_la_herramienta_anota_a_los_lideres_que_nombra(sesion, mundo):
    db, l1 = mundo["db"], mundo["l1"]
    for cli in (sesion, coordinador(sesion.app, db)):
        ctx = aa.contexto(sesion.app, cli)
        r = aa.correr(sesion, aa.ejecutar, ha.ANALIZAR, ctx, {"tipo": "tabla", "dimensiones": ["lider"]})
        assert r.personas == {l1} and "CONCEJAL" not in r.texto_para_modelo()
        g = r.acciones[0]
        assert g["tipo"] == "grafico" and "LIDER INVENTADO UNO (Líder)" in {x["etiqueta"] for x in g["items"]}
        r = aa.correr(sesion, aa.ejecutar, ha.ANALIZAR, ctx, {"tipo": "tabla", "dimensiones": ["sexo", "lider"]})
        assert r.personas == {l1}
        # Los ids de los lugares, los puestos o los tipos no son personas
        for dims in (["tipo"], ["lugar"], ["lugar", "sexo"]):
            r = aa.correr(sesion, aa.ejecutar, ha.ANALIZAR, ctx, {"tipo": "tabla", "dimensiones": dims})
            assert r.personas == set(), dims
        aa.correr(sesion, ctx.api.cerrar)


def test_la_herramienta_con_el_ajuste_apagado(sesion, mundo):
    _ajuste(mundo["db"], False, True)
    ctx = aa.contexto(sesion.app, sesion, ajustes=SIN)
    from app.agente.herramientas.base import ErrorHerramienta
    with pytest.raises(ErrorHerramienta) as e:
        aa.correr(sesion, aa.ejecutar, ha.ANALIZAR, ctx, {"tipo": "tabla", "dimensiones": ["lista"]})
    assert e.value.codigo == "permiso"
    aa.correr(sesion, ctx.api.cerrar)


# ───────────────────────────── Por MCP: el ajuste `mcp` ─────────────────────────────

def _clave(sesion, *alcances) -> str:
    r = sesion.post("/api/pantalla/clave", json={"tipo": "datos", "alcances": list(alcances)})
    assert r.status_code == 200, r.text
    return r.json()["clave"]


def _llamar(agente, clave, nombre, argumentos) -> dict:
    r = agente.post("/api/mcp", headers={"Authorization": f"Bearer {clave}"},
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                          "params": {"name": nombre, "arguments": argumentos}})
    assert r.status_code == 200, r.text
    return r.json()["result"]


def test_por_mcp_manda_su_propio_ajuste(sesion, mundo):
    db = mundo["db"]
    # Con lectura: la tabla por líder nombra personas (sin lectura, 403: test_revision_politicos_mcp)
    clave = _clave(sesion, "analitica", "lectura")
    agente = TestClient(sesion.app)
    consulta = {"tipo": "tabla", "dimensiones": ["lider"]}
    # El del asistente apagado y el de MCP encendido: por MCP sí, en el panel (el asistente) no
    _ajuste(db, False, True)
    res = _llamar(agente, clave, "analizar", consulta)
    assert res["isError"] is False, res
    out = json.loads(res["content"][0]["text"])
    assert {f["valor"] for f in out["filas"]} >= {mundo["l1"], an.SIN_LIDER}
    assert db.mcp_entregas.find_one({"herramienta": "analizar", "personas": mundo["l1"]})  # el líder cuenta
    assert ya.error(sesion, consulta)[0] == 403
    # Al revés: en el panel sí, por MCP no
    _ajuste(db, True, False)
    res = _llamar(agente, clave, "analizar", consulta)
    assert res["isError"] is True and json.loads(res["content"][0]["text"])["error"]["codigo"] == "permiso"
    assert ya.consulta(sesion, **consulta)["filas"]
