"""Los datos políticos en las herramientas del asistente (decisión del dueño: ya no se le ocultan al modelo), con el
ajuste `agente_politicos` encendido (lo de por defecto) y apagado: el tipo de persona, el «Liderado por», las listas,
las fuentes «cedulas» y «general», sus filtros, la lista de líderes con sus conteos y las escrituras de marcar un tipo
y asignar un líder, cada rol solo lo que el panel le muestra (A y K, todo; P, el tipo y el «Liderado por» de su zona,
y solo suma; C, nada). De quien no autorizó, nada: ni su tipo, ni que lidera, ni en los conteos. Solo datos
inventados."""
from __future__ import annotations

import json

import pytest

import ayudas_agente as aa
from ayudas_g3 import autorizada, coordinador, persona, recorrer
from app.agente import herramientas
from app.agente.herramientas import calidad as hc
from app.agente.herramientas import gestion as hg
from app.agente.herramientas import interfaz as hi
from app.agente.herramientas import personas as hp
from app.agente.herramientas.base import ErrorHerramienta

H = {h.nombre: h for h in herramientas.fijas()}
SIN = {"agente_politicos": {"asistente": False, "mcp": False}}
POLITICAS = {"lideres", "marcar_tipo", "asignar_lider"}
SENSIBLES = ("Raizal", "Subsidiado")  # los valores; las claves `sensibles*` y `regimen_salud`, con `_sin_claves`


@pytest.fixture
def ctx_de(sesion):
    abiertos = []

    def hacer(cli, **kw):
        c = aa.contexto(sesion.app, cli, **kw)
        abiertos.append(c)
        return c

    yield hacer
    for c in abiertos:
        aa.correr(sesion, c.api.cerrar)


def _ej(cli, ctx, nombre, entrada):
    return aa.correr(cli, aa.ejecutar, H[nombre], ctx, entrada)


def _conf(cli, ctx, nombre, entrada):
    return aa.correr(cli, aa.confirmar, H[nombre], ctx, entrada)


def _falla(cli, fn, ctx, nombre, entrada) -> ErrorHerramienta:
    with pytest.raises(ErrorHerramienta) as e:
        aa.correr(cli, fn, H[nombre], ctx, entrada)
    return e.value


def _texto(r) -> str:
    return r.texto_para_modelo()


def _sin_claves(x, *claves: str) -> None:
    for _, k, _ in recorrer(x):
        assert k not in claves, k


def _asignado(*ids: int) -> list[dict]:
    return [{"id": i, "asignado_en": "2026-11-01T00:00:00+00:00", "asignado_por": "admin", "asignado_por_uid": 0}
            for i in ids]


@pytest.fixture
def mundo(sesion):
    """Un líder que autorizó (L1), un concejal que no (L2), dos personas lideradas que autorizaron (X con los dos
    líderes, Y con L1) y una que no (Z, con L1)."""
    db = sesion.app.state.db
    l1 = persona(db, nombre="LIDER INVENTADO UNO", lider=True, cedula="93100001")
    autorizada(db, l1)
    l2 = persona(db, nombre="CONCEJAL INVENTADO NOAUTORIZA", concejal=True, consentimiento="no", cedula="93100002")
    x = persona(db, nombre="XIMENA INVENTADA LIDERADA", votante=True, lideres=_asignado(l1, l2),
                listas=["Lista Inventada Q7"], fuentes=["tramites", "general"], cedula_origen="general",
                sensibles={"etnia": "Raizal"}, regimen_salud="Subsidiado", cedula="93100003")
    autorizada(db, x)
    y = persona(db, nombre="YOLANDA INVENTADA LIDERADA", votante=True, lideres=_asignado(l1), fuentes=["manual"])
    autorizada(db, y)
    z = persona(db, nombre="ZOILA INVENTADA NOAUTORIZA", votante=True, lideres=_asignado(l1), consentimiento="no")
    return {"db": db, "l1": l1, "l2": l2, "x": x, "y": y, "z": z}


# ───────────────────────────── Catálogo ─────────────────────────────

def test_las_herramientas_politicas_se_ofrecen_por_rol_y_ajuste(sesion, como):
    app, db = sesion.app, sesion.app.state.db
    k = coordinador(app, db)
    quienes = {"admin": aa.quien_de(app, 0), "coordinador": aa.quien_de(app, k.uid),
               "planillero": aa.quien_de(app, como("planillero").uid),
               "consultor": aa.quien_de(app, como("consultor").uid)}
    for rol, quien in quienes.items():
        con = {h.nombre for h in herramientas.para(quien, {"escritura": True}, app.state.cfg)} & POLITICAS
        assert con == (set() if rol == "consultor" else POLITICAS), rol
        sin = {h.nombre for h in herramientas.para(quien, {"escritura": True}, app.state.cfg, ajustes=SIN)}
        assert not sin & POLITICAS, rol
    # Por MCP manda el ajuste `mcp`, no el del asistente
    admin_mcp = aa.quien_de(app, 0)
    admin_mcp.via = "mcp"
    solo_chat = {"agente_politicos": {"asistente": True, "mcp": False}}
    assert not {h.nombre for h in herramientas.para(admin_mcp, {"escritura": True}, app.state.cfg,
                                                     ajustes=solo_chat)} & POLITICAS
    assert POLITICAS <= {h.nombre for h in herramientas.para(aa.quien_de(app, 0), {"escritura": True},
                                                             app.state.cfg, ajustes=solo_chat)}
    assert {H[n].alcance_mcp() for n in POLITICAS} == {"lectura", "escritura"}
    assert H["lideres"].alcance_mcp() == "lectura"


# ───────────────────────────── Lecturas de A y K ─────────────────────────────

def test_administrador_y_coordinador_reciben_tipo_liderado_por_listas_y_fuentes(sesion, ctx_de, mundo):
    db, x, l1, l2 = mundo["db"], mundo["x"], mundo["l1"], mundo["l2"]
    for cli in (sesion, coordinador(sesion.app, db)):
        ctx = ctx_de(cli)
        r = _ej(sesion, ctx, "ver_persona", {"persona_id": x})
        f = r.contenido
        assert f["votante"] is True and f["lider"] is False and f["concejal"] is False
        assert f["lideres"] == [{"id": l1, "nombre": "LIDER INVENTADO UNO", "tipo": "lider", "marcado": True}]
        assert f["listas"] == ["Lista Inventada Q7"] and f["fuentes"] == ["tramites", "general"]
        assert f["cedula_origen"] == "general" and f["cedula_ult3"] == "···003"
        assert r.personas == {x, l1}
        texto = _texto(r)
        for vedado in (*SENSIBLES, "CONCEJAL INVENTADO NOAUTORIZA", "93100003", "asignado_por"):
            assert vedado not in texto, vedado
        _sin_claves(f, "sensibles", "sensibles_registrados", "regimen_salud", "asignado_por", "historial", "origen")
        # La lista con filtros: el tipo, el «Liderado por» (sin el que no autorizó) y las fuentes
        r = _ej(sesion, ctx, "buscar_personas", {"filtros": {"tipo": "votante"}})
        filas = {f["id"]: f for f in r.contenido["filas"]}
        assert set(filas) == {x, mundo["y"]} and r.contenido["total"] == 2  # sin Zoila: no autorizó
        assert filas[x]["votante"] is True and filas[x]["lideres"] == [
            {"id": l1, "nombre": "LIDER INVENTADO UNO", "tipo": "lider"}] and filas[x]["lideres_n"] == 1
        assert filas[x]["fuentes"] == ["tramites", "general"]
        assert r.personas == {x, mundo["y"], l1} and "nota_autorizacion" in r.contenido
        assert "CONCEJAL" not in _texto(r) and l2 not in r.personas


def test_la_ficha_de_un_lider_dice_lo_que_trajo_sin_quienes_no_autorizaron(sesion, ctx_de, mundo):
    db, l1 = mundo["db"], mundo["l1"]
    api = sesion.get(f"/api/personas/{l1}").json()
    assert api["traidas"] == {"total": 3, "compartidas": 1}  # el panel cuenta a todos
    f = _ej(sesion, ctx_de(sesion), "ver_persona", {"persona_id": l1}).contenido
    assert f["lider"] is True and f["traidas"] == {"total": 2, "compartidas": 0}
    db.personas.update_one({"_id": mundo["y"]}, {"$set": {"lideres": _asignado(l1, mundo["x"])}})
    db.personas.update_one({"_id": mundo["x"]}, {"$set": {"lider": True}})
    f = _ej(sesion, ctx_de(sesion), "ver_persona", {"persona_id": l1}).contenido
    assert f["traidas"] == {"total": 2, "compartidas": 1}


def test_con_el_ajuste_apagado_nada_politico(sesion, ctx_de, mundo):
    ctx = ctx_de(sesion, ajustes=SIN)
    f = _ej(sesion, ctx, "ver_persona", {"persona_id": mundo["x"]}).contenido
    assert not {"lider", "votante", "concejal", "lideres", "listas", "fuentes", "cedula_origen", "traidas"} & set(f)
    r = _ej(sesion, ctx, "buscar_personas", {"filtros": {"zona": "sin"}})
    assert all(not {"lider", "votante", "lideres", "lideres_n", "fuentes"} & set(f) for f in r.contenido["filas"])
    assert r.personas == {f["id"] for f in r.contenido["filas"]}
    for filtros in ({"tipo": "votante"}, {"lider_id": mundo["l1"]}, {"lista": "Lista Inventada Q7"},
                    {"fuente": "general"}, {"sin_lider": True}, {"varios_lideres": True}):
        e = _falla(sesion, aa.ejecutar, ctx, "buscar_personas", {"filtros": filtros})
        assert e.codigo == "permiso" and "Ajustes" in e.mensaje, filtros
    for nombre, entrada in (("lideres", {}), ("marcar_tipo", {"persona_id": mundo["y"], "tipos": ["lider"]}),
                            ("asignar_lider", {"persona_id": mundo["y"], "lider_id": mundo["l1"]})):
        fn = aa.ejecutar if H[nombre].tipo == "lectura" else aa.confirmar
        assert _falla(sesion, fn, ctx, nombre, entrada).codigo == "permiso", nombre


def test_filtros_politicos_de_a_y_k(sesion, ctx_de, mundo):
    ctx = ctx_de(sesion)
    l1, x, y = mundo["l1"], mundo["x"], mundo["y"]
    ids = lambda r: {f["id"] for f in r.contenido["filas"]}  # noqa: E731
    assert ids(_ej(sesion, ctx, "buscar_personas", {"filtros": {"lider_id": l1}})) == {x, y}
    assert ids(_ej(sesion, ctx, "buscar_personas", {"filtros": {"lista": "Lista Inventada Q7"}})) == {x}
    assert ids(_ej(sesion, ctx, "buscar_personas", {"filtros": {"fuente": "general"}})) == {x}
    assert ids(_ej(sesion, ctx, "buscar_personas", {"filtros": {"varios_lideres": True}})) == {x}
    sin_lider = ids(_ej(sesion, ctx, "buscar_personas", {"filtros": {"sin_lider": True}}))
    assert l1 in sin_lider and not {x, y} & sin_lider and mundo["z"] not in sin_lider
    # Un líder que no autorizó no sirve de filtro (contar a quienes trajo diría que lidera); el mismo mensaje que un id
    # que no existe o que no lidera
    for lid in (mundo["l2"], 999999, y):
        e = _falla(sesion, aa.ejecutar, ctx, "buscar_personas", {"filtros": {"lider_id": lid}})
        assert e.codigo == "invalido" and e.mensaje == hp.LIDER_NO_USABLE, lid


def test_planillero_y_consultor_no_filtran_por_datos_politicos(sesion, como, ctx_de, mundo):
    p = ctx_de(como("planillero"))
    for filtros in ({"tipo": "lider"}, {"lista": "Lista Inventada Q7"}, {"fuente": "cedulas"}):
        e = _falla(sesion, aa.ejecutar, p, "buscar_personas", {"filtros": filtros})
        assert e.codigo == "permiso" and e.detalle["campos"], filtros
    # Tampoco en los indicadores ni para abrir Habitantes o mover el mapa
    e = _falla(sesion, aa.ejecutar, p, "abrir_vista", {"vista": "habitantes", "filtros": {"tipo": "lider"}})
    assert e.codigo == "permiso"


# ───────────────────────────── La lista de líderes ─────────────────────────────

def test_lista_de_lideres_con_conteos_sin_quienes_no_autorizaron(sesion, ctx_de, mundo):
    l1 = mundo["l1"]
    api = sesion.get("/api/lideres").json()
    por_id = {f["id"]: f for f in api["lideres"]}
    assert por_id[l1]["traidas"] == 3 and mundo["l2"] in por_id  # el panel: todos
    for cli in (sesion, coordinador(sesion.app, mundo["db"])):
        r = _ej(sesion, ctx_de(cli), "lideres", {})
        c = r.contenido
        assert c["tipo"] == "lideres" and c["total"] == 1 and c["personas_con_varios"] == 0
        assert c["lideres"] == [{"id": l1, "nombre": "LIDER INVENTADO UNO", "tipo": "lider", "cedula_ult3": "···001",
                                 "marcado": True, "traidas": 2, "votantes": 2, "compartidas": 0}]
        assert r.personas == {l1} and "CONCEJAL" not in _texto(r) and "93100001" not in _texto(r)
        # El buscador del «Liderado por»: tampoco el que no autorizó
        assert _ej(sesion, ctx_de(cli), "lideres", {"q": "concejal inventado"}).contenido["lideres"] == []
        b = _ej(sesion, ctx_de(cli), "lideres", {"q": "lider inventado"})
        assert [x["id"] for x in b.contenido["lideres"]] == [l1] and b.personas == {l1}
        # Por la cédula completa: sin sus dígitos enmascarados
        b = _ej(sesion, ctx_de(cli), "lideres", {"q": "93100001"})
        assert [x["id"] for x in b.contenido["lideres"]] == [l1] and "cedula_ult3" not in b.contenido["lideres"][0]


def test_el_planillero_solo_busca_lideres(sesion, como, ctx_de, mundo):
    p = como("planillero")
    e = _falla(sesion, aa.ejecutar, ctx_de(p), "lideres", {})
    assert e.codigo == "permiso"
    b = _ej(sesion, ctx_de(p), "lideres", {"q": "inventado"})
    assert [x["id"] for x in b.contenido["lideres"]] == [mundo["l1"]]
    assert mundo["db"].lecturas.count_documents({"uid": p.uid, "pid": mundo["l1"]}) == 1


# ───────────────────────────── El planillero: su zona ─────────────────────────────

@pytest.fixture
def zona(sesion, como, mundo):
    db = mundo["db"]
    suyo, ajeno = [x["_id"] for x in db.lugares.find({}, {"_id": 1}).sort("_id", 1).limit(2)]
    p = como("planillero", asignacion={"lugares": [suyo], "areas": []})
    w = persona(db, nombre="WILMA INVENTADA DE SU ZONA", lugar_id=suyo, votante=True, lideres=_asignado(mundo["l1"]))
    autorizada(db, w)
    v = persona(db, nombre="VILMA INVENTADA AJENA", lugar_id=ajeno, lider=True)
    autorizada(db, v)
    return {**mundo, "p": p, "w": w, "v": v}


def test_planillero_ve_el_tipo_solo_en_su_zona_y_solo_suma(sesion, ctx_de, zona):
    db, p, w, v, l1 = zona["db"], zona["p"], zona["w"], zona["v"], zona["l1"]
    f = _ej(sesion, ctx_de(p), "ver_persona", {"persona_id": w}).contenido
    assert f["votante"] is True and f["lider"] is False and f["lideres"][0]["id"] == l1
    assert "lider" in f["editables"] and "votante" not in f["editables"]  # P solo suma lo que no tiene
    assert not {"listas", "fuentes", "traidas"} & set(f)  # lo que el panel no le muestra a P
    ajena = _ej(sesion, ctx_de(p), "ver_persona", {"persona_id": v}).contenido
    assert not {"lider", "votante", "concejal", "lideres"} & set(ajena)
    assert not {"lider", "votante", "concejal"} & set(ajena.get("editables") or [])
    # Marca un tipo en su zona, con su tarjeta; fuera de ella no; quitar nunca
    tarjeta = _conf(sesion, ctx_de(p), "marcar_tipo", {"persona_id": w, "tipos": ["lider"]})
    assert tarjeta.titulo.startswith("Marcar el tipo de WILMA") and ["Tipo", "+ Líder"] in tarjeta.para_interfaz()[
        "detalle"]
    r = _ej(sesion, ctx_de(p, tool_use_id="toolu_tipo_p"), "marcar_tipo", {"persona_id": w, "tipos": ["lider"]})
    assert r.contenido["guardado"] is True and r.contenido["persona"]["lider"] is True and r.personas == {w}
    assert db.personas.find_one({"_id": w})["lider"] is True
    assert _falla(sesion, aa.confirmar, ctx_de(p), "marcar_tipo",
                  {"persona_id": v, "tipos": ["votante"]}).codigo == "fuera_de_zona"
    assert _falla(sesion, aa.confirmar, ctx_de(p), "marcar_tipo",
                  {"persona_id": w, "tipos": ["votante"], "quitar": True}).codigo == "permiso"
    assert _falla(sesion, aa.confirmar, ctx_de(p), "asignar_lider",
                  {"persona_id": v, "lider_id": l1}).codigo == "fuera_de_zona"


# ───────────────────────────── Escrituras ─────────────────────────────

def test_marcar_y_quitar_un_tipo_por_a_y_k(sesion, ctx_de, mundo):
    db, y = mundo["db"], mundo["y"]
    t = _conf(sesion, ctx_de(sesion), "marcar_tipo", {"persona_id": y, "tipos": ["concejal", "votante"]})
    assert t.aviso == "Sin cambio (ya lo tenía): Votante." and t.personas == set()
    r = _ej(sesion, ctx_de(sesion, tool_use_id="toolu_t1"), "marcar_tipo",
            {"persona_id": y, "tipos": ["concejal", "votante"]})
    assert r.contenido["guardado"] is True and db.personas.find_one({"_id": y})["concejal"] is True
    # Repetirla no escribe otra vez (PATCH no respeta la clave: se relee)
    antes = db.auditoria.count_documents({"entidad_id": y})
    r = _ej(sesion, ctx_de(sesion, tool_use_id="toolu_t1"), "marcar_tipo",
            {"persona_id": y, "tipos": ["concejal", "votante"]})
    assert r.contenido["guardado"] is False and db.auditoria.count_documents({"entidad_id": y}) == antes
    assert _falla(sesion, aa.confirmar, ctx_de(sesion), "marcar_tipo",
                  {"persona_id": y, "tipos": ["concejal"]}).codigo == "sin_cambios"
    k = coordinador(sesion.app, db)
    r = _ej(sesion, ctx_de(k, tool_use_id="toolu_t2"), "marcar_tipo",
            {"persona_id": y, "tipos": ["concejal"], "quitar": True})
    assert r.contenido["persona"]["concejal"] is False and db.personas.find_one({"_id": y})["concejal"] is False
    # A quien no autorizó no se le marca nada desde el asistente
    assert _falla(sesion, aa.confirmar, ctx_de(sesion), "marcar_tipo",
                  {"persona_id": mundo["z"], "tipos": ["lider"]}).codigo == "no_contactable"


def test_asignar_un_lider(sesion, ctx_de, mundo):
    db, y, l1, l2 = mundo["db"], mundo["y"], mundo["l1"], mundo["l2"]
    otro = persona(db, nombre="LIDER INVENTADO DOS", lider=True)
    autorizada(db, otro)
    t = _conf(sesion, ctx_de(sesion), "asignar_lider", {"persona_id": y, "lider_id": otro})
    assert t.personas == {otro} and ["Liderado por", f"+ LIDER INVENTADO DOS (Líder) #{otro}"] in \
        t.para_interfaz()["detalle"]
    assert "Ya tiene 1 líder" in t.aviso
    r = _ej(sesion, ctx_de(sesion, tool_use_id="toolu_l1"), "asignar_lider", {"persona_id": y, "lider_id": otro})
    assert r.contenido["guardado"] is True and r.personas >= {y, otro, l1}
    assert {x["id"] for x in r.contenido["persona"]["lideres"]} == {l1, otro}
    assert [x["id"] for x in db.personas.find_one({"_id": y})["lideres"]] == [l1, otro]
    # Ya lo tenía; un líder que no autorizó, un id que no lidera o uno que no existe: el mismo mensaje
    assert _falla(sesion, aa.confirmar, ctx_de(sesion), "asignar_lider",
                  {"persona_id": y, "lider_id": otro}).codigo == "sin_cambios"
    for lid in (l2, mundo["x"], 999999):
        e = _falla(sesion, aa.confirmar, ctx_de(sesion), "asignar_lider", {"persona_id": y, "lider_id": lid})
        assert e.codigo == "invalido" and e.mensaje == hp.LIDER_NO_USABLE, lid
    assert _falla(sesion, aa.confirmar, ctx_de(sesion), "asignar_lider",
                  {"persona_id": mundo["z"], "lider_id": l1}).codigo == "no_contactable"
    with pytest.raises(Exception):
        H["asignar_lider"].validar({"persona_id": y, "lider_id": y})


# ───────────────────────────── Indicadores, calidad y vistas ─────────────────────────────

def test_indicadores_con_lideres_listas_y_fuentes(sesion, ctx_de, mundo):
    c = _ej(sesion, ctx_de(sesion), "indicadores", {}).contenido
    assert c["kpi"]["lideres"] == 1 and "en_ambas_bases" in c["kpi"]
    assert c["listas"] == [{"lista": "Lista Inventada Q7", "n": 1}] and c["fuentes"]["general"] == 1
    assert not {"sensibles", "actividad", "demografia"} & set(c)
    apagado = _ej(sesion, ctx_de(sesion, ajustes=SIN), "indicadores", {}).contenido
    assert not {"listas", "fuentes"} & set(apagado) and "lideres" not in apagado["kpi"]
    # Filtrar los indicadores por tipo (A y K)
    t = _ej(sesion, ctx_de(sesion), "indicadores", {"filtros": {"tipo": "votante"}}).contenido
    assert t["kpi"]["personas"] == 2


def test_conflictos_e_importaciones_con_sus_fuentes_reales(sesion, ctx_de, mundo):
    db = mundo["db"]
    c = {"id": 1, "motivo": "nombre_distinto", "estado": "pendiente", "fuente": "cedulas", "cedula": "93000554",
         "persona": {"id": mundo["x"], "nombre": "XIMENA", "consentimiento": "si"}}
    assert hc.conflicto_para_modelo(c, frozenset())["fuente"] == "otra_base"
    assert hc.conflicto_para_modelo(c, frozenset(), politicos=True)["fuente"] == "cedulas"
    db.importaciones.insert_one(
        {"_id": 1, "ts": "2026-11-01T15:00:00+00:00", "usuario": "admin", "uid": 0, "capturado_por": None,
         "archivo": "base general zona norte.xlsx", "tipo": "general", "evidencia_sha256": {},
         "resumen": {"personas_nuevas": 812, "registros_por_fuente": {"general": 812}, "tipos_marcados": {"lider": 9},
                     "lideres_asignados": 40, "planilleros_desconocidos": ["MARTA INVENTADA"]}})
    out = _ej(sesion, ctx_de(sesion), "importaciones", {}).contenido["importaciones"][0]
    assert out["tipo"] == ["general"] and out["archivo"] == "base general zona norte.xlsx"
    assert out["resumen"] == {"personas_nuevas": 812, "lideres_asignados": 40, "tipos_marcados": {"lider": 9},
                              "registros_por_fuente": {"general": 812}}
    apagado = _ej(sesion, ctx_de(sesion, ajustes=SIN), "importaciones", {}).contenido["importaciones"][0]
    assert apagado == {"id": 1, "fecha": "2026-11-01", "usuario": "admin", "tipo": "otra_base"}


def test_abrir_habitantes_con_filtros_politicos(sesion, ctx_de, mundo):
    r = _ej(sesion, ctx_de(sesion), "abrir_vista", {"vista": "habitantes",
                                                    "filtros": {"tipo": "lider", "lista": "Lista Inventada Q7"}})
    assert r.acciones[0]["ruta"].startswith("/personas?") and "tipo=lider" in r.acciones[0]["ruta"]
    e = _falla(sesion, aa.ejecutar, ctx_de(sesion, ajustes=SIN), "abrir_vista",
               {"vista": "habitantes", "filtros": {"tipo": "lider"}})
    assert e.codigo == "permiso"
    assert set(hi.DE_HABITANTES) >= set(hp.FILTROS_POLITICOS)
    assert hg.params_de(hg.FiltrosBase.model_validate({"varios_lideres": True, "sin_lider": False,
                                                       "lider_id": 3})) == {"varios_lideres": "1", "lider_id": "3"}


def test_de_punta_a_punta_por_el_bucle_lo_politico_va_con_la_persona(sesion, mundo):
    """Con el bucle de verdad: la ficha que vuelve al modelo trae el tipo y el «Liderado por», y la conversación
    recuerda al líder que nombró (si se suprime, se borra) y queda con datos de personas (sin voz clonada)."""
    from app.agente import conversaciones as conv_db
    db, x, l1 = mundo["db"], mundo["x"], mundo["l1"]
    api = aa.encender(sesion.app, aa.sse(aa.TU("toolu_v", "ver_persona", {"persona_id": x}), stop="tool_use"),
                      aa.sse(aa.T("Es votante y la trajo el líder uno.")))
    r, ev = aa.enviar(sesion, "¿Quién trajo a Ximena?")
    assert r.status_code == 200, r.text
    resultado = api.peticiones[1]["json"]["messages"][-1]["content"][0]
    ficha = json.loads(resultado["content"])
    assert ficha["votante"] is True and ficha["lideres"][0]["id"] == l1
    cid = ev[0]["conversacion"]
    conv = db[conv_db.CONVERSACIONES].find_one({"_id": cid})
    assert {x, l1} <= set(conv["personas"]) and conv_db.con_datos(conv)
