"""Herramientas del asistente para las colas de Calidad de datos (`app/agente/herramientas/calidad.py`): coincidencias
y su resolución con la vista previa en la tarjeta, conflictos de cédula, situaciones, solicitudes sin de quién son,
importaciones sin las bases políticas, puestos y lugares sin reconocer. Lo que llega al modelo es una lista blanca
(nada de listas, fuentes políticas, datos sensibles, cédulas ni teléfonos completos, ni el texto de las señales); de
quien no autorizó, solo quién es; la tarjeta no escribe y aprobar escribe una sola vez; P y C reciben 403 de la API.

Las herramientas corren en el bucle de la aplicación y llaman a la API de verdad por ASGI. Solo datos inventados."""
from __future__ import annotations

import pytest

from ayudas_calidad import (CEDULA, TEL, TEL2, H, coincidencia, ejecutar, escribe_una_vez, falla_ejecutar, falla_leer,
                            falla_tarjeta, foto, leer, modelo, rica, sin_datos, tarjeta)
from ayudas_calidad import ctx_de  # noqa: F401 (fixture)
from ayudas_g3 import autorizada, coordinador, persona
from app import db as bd

FORMA_NO_AUTORIZO = {"id", "nombre", "lugar", "consentimiento", "aviso"}
# Las pruebas que fijan lo de siempre con los datos políticos apagados (`agente_politicos`)
SIN_POLITICOS = {"agente_politicos": {"asistente": False, "mcp": False}}


def _no(db, **extra) -> int:
    return persona(db, **{"nombre": "EUDOSIA INVENTADA NOAUTORIZA", "consentimiento": "no", "cedula": "71000999",
                          "telefono": "3005550099", **extra})


def _par_general(db) -> tuple[int, int]:
    """Dos fichas sin cédula de la base general con el mismo teléfono: la señal `misma_fuente` dice, en su texto, «la
    base general»; nada de eso puede llegar al modelo."""
    comun = {"telefono": TEL, "telefonos": [{"numero": TEL, "fuentes": ["general"], "estado": "confirmado"}],
             "fuentes": ["general"], "listas": ["Lista Inventada Q9"], "sexo": "F", "edad": 40}
    a = persona(db, nombre="ROSALBA INVENTADA DUPLICADA", **comun)
    b = persona(db, nombre="ROSALBA INVENTADA DUPLICADA", direccion="CALLE 50 # 48-21", **comun)
    autorizada(db, a)
    autorizada(db, b)
    return a, b


# ───────────────────────────── coincidencias ─────────────────────────────

def test_coincidencias_solo_claves_de_senales_y_fichas_minimizadas(sesion, ctx_de):
    db = sesion.app.state.db
    a, b = _par_general(db)
    cid = coincidencia(db, a, b, detalle="Reportado: llamar al 3001234567")
    res = leer(sesion, ctx_de(sesion), "coincidencias", {})
    out = modelo(res)
    sin_datos(out, "3001234567")
    assert res.personas == {a, b}
    g = out["grupos"][0]
    assert g["clave"] == str(cid) and g["conservaria"] in (a, b) and g["nivel"] in ("alta", "media", "baja")
    par = g["pares"][0]
    assert "misma_fuente" in par["en_contra"] and "mismo_telefono" in par["a_favor"]
    assert all(isinstance(x, str) for x in par["a_favor"] + par["en_contra"])
    assert "···567" in par["nota"]
    m = g["miembros"][0]
    assert m["telefono_mascara"] == "···0011" and "cedula" not in m and "telefonos" not in m


def test_grupo_con_quien_no_autorizo_sale_sin_senales_y_por_mcp_no_sale(sesion, ctx_de):
    db = sesion.app.state.db
    a = rica(db)
    no = _no(db, telefono=TEL, cedula=None)  # sin cédula: con dos distintas el par se cierra solo
    coincidencia(db, a, no)
    res = leer(sesion, ctx_de(sesion), "coincidencias", {})
    g = modelo(res)["grupos"][0]
    assert g["no_autorizo"] is True and "pares" not in g and "nivel" not in g
    fila_no = next(x for x in g["miembros"] if x["id"] == no)
    assert set(fila_no) <= FORMA_NO_AUTORIZO and "71000999" not in res.texto_para_modelo()
    ctx = ctx_de(sesion)
    ctx.via = "mcp"
    out = modelo(leer(sesion, ctx, "coincidencias", {}))
    assert out["grupos"] == [] and out["con_quien_no_autorizo"] == 1
    # Y no se resuelve desde el asistente
    e = falla_tarjeta(sesion, ctx_de(sesion), "resolver_coincidencias",
                      {"grupos": [{"clave": g["clave"], "decision": "unir"}]})
    assert e.codigo == "no_contactable"


def test_coincidencias_y_resolver_solo_administrador_y_coordinador(sesion, como, ctx_de):
    db = sesion.app.state.db
    a, b = _par_general(db)
    cid = coincidencia(db, a, b)
    k = coordinador(sesion.app, db)
    assert modelo(leer(sesion, ctx_de(k), "coincidencias", {}))["total"] == 1
    for rol in ("planillero", "consultor"):
        c = como(rol)
        e = falla_leer(sesion, ctx_de(c), "coincidencias", {})
        assert (e.codigo, e.estado) == ("permiso", 403), rol
        e = falla_tarjeta(sesion, ctx_de(c), "resolver_coincidencias",
                          {"grupos": [{"clave": str(cid), "decision": "unir"}]})
        assert (e.codigo, e.estado) == ("permiso", 403), rol
        # La API también: la ruta en lote es de A y K
        r = c.post("/api/coincidencias/lote", json={"grupos": [{"pares": [cid], "decision": "unir"}]})
        assert r.status_code == 403 and r.json()["detail"]["codigo"] == "permiso"


def test_unir_con_la_vista_previa_y_una_sola_vez(sesion, ctx_de):
    db = sesion.app.state.db
    a = rica(db)
    b = persona(db, nombre="ANACLETA INVENTADA RICA", telefono=TEL, direccion="VEREDA LA INVENTADA",
                telefonos=[{"numero": TEL, "fuentes": ["planilla"], "estado": "confirmado"}], fuentes=["planilla"])
    autorizada(db, b)
    cid = coincidencia(db, a, b)

    def cambia(db):
        assert db.personas.find_one({"_id": b})["fusionada_en"] == a
        c = db.coincidencias.find_one({"_id": cid})
        assert c["estado"] == "aceptada" and c["conservada"] == a

    conf, r1, r2 = escribe_una_vez(sesion, ctx_de(sesion), "resolver_coincidencias",
                                   {"grupos": [{"clave": str(cid), "decision": "unir"}]}, cambia)
    detalle = dict(conf.detalle)
    assert conf.personas == {a, b}
    assert detalle["Se conserva"] == f"ANACLETA INVENTADA RICA (#{a})"
    queda = detalle["Quedaría"]
    assert "Cédula: ···555" in queda and "···0011" in queda and "Correo: registrado" in queda
    assert CEDULA not in str(conf.detalle) and TEL not in str(conf.detalle) and TEL2 not in str(conf.detalle)
    assert "no se deshace" in conf.aviso
    assert modelo(r1)["unidas"] == 1 and modelo(r1)["resultados"][0]["conservada"] == a
    assert modelo(r2)["resultados"][0]["ya_estaba"] is True and modelo(r2)["unidas"] == 0


def test_unir_conservando_otra_y_si_el_grupo_cambio_no_se_toca(sesion, ctx_de):
    db = sesion.app.state.db
    a, b = _par_general(db)
    cid = coincidencia(db, a, b)
    conf, g = tarjeta(sesion, ctx_de(sesion), "resolver_coincidencias",
                      {"grupos": [{"clave": str(cid), "decision": "unir", "conservar": b}]})
    assert dict(conf.detalle)["Se conserva"].endswith(f"(#{b})")
    # Alguien cambia una de las fichas entre la tarjeta y la aprobación: ese grupo no se une
    db.personas.update_one({"_id": a}, {"$set": {"sexo": "M"}})
    antes = foto(db)
    r = ejecutar(sesion, ctx_de(sesion), "resolver_coincidencias", g)
    out = modelo(r)
    assert out["resultados"][0]["ok"] is False and out["resultados"][0]["codigo"] == "cambiada"
    assert foto(db) == antes
    # Sin tarjeta (la entrada sin lo que puso `confirmar`), tampoco
    r = ejecutar(sesion, ctx_de(sesion), "resolver_coincidencias",
                 H["resolver_coincidencias"].validar({"grupos": [{"clave": str(cid), "decision": "unir"}]}))
    assert modelo(r)["resultados"][0]["codigo"] == "cambiada" and foto(db) == antes


def test_separar_y_cedulas_distintas_no_se_unen(sesion, ctx_de):
    db = sesion.app.state.db
    a, b = _par_general(db)
    cid = coincidencia(db, a, b)

    def cambia(db):
        assert db.coincidencias.find_one({"_id": cid})["estado"] == "rechazada"

    conf, _, r2 = escribe_una_vez(sesion, ctx_de(sesion), "resolver_coincidencias",
                                  {"grupos": [{"clave": str(cid), "decision": "separar"}]}, cambia)
    assert "personas distintas" in conf.titulo.lower() or "distintas" in conf.detalle[0][0]
    assert modelo(r2)["resultados"][0]["ya_estaba"] is True
    # Un grupo de tres (C~M y M~D) con dos cédulas distintas (C y D) no se une entero
    c, d = rica(db), rica(db, cedula="93000556")
    medio = persona(db, nombre="ANACLETA INVENTADA RICA", telefono=TEL)
    autorizada(db, medio)
    cid2, cid3 = coincidencia(db, c, medio), coincidencia(db, medio, d)
    clave = f"{cid2}-{cid3}"
    out = modelo(leer(sesion, ctx_de(sesion), "coincidencias", {"persona_id": c}))
    assert out["grupos"][0]["clave"] == clave and out["grupos"][0]["nivel"] == "bloqueada"
    assert any("cédulas distintas" in x for x in out["grupos"][0]["avisos"])
    e = falla_tarjeta(sesion, ctx_de(sesion), "resolver_coincidencias", {"grupos": [{"clave": clave,
                                                                                      "decision": "unir"}]})
    assert e.codigo == "cedulas_distintas"
    # Excluyendo la que sobra se unen las otras dos y la excluida queda como otra persona
    conf, g = tarjeta(sesion, ctx_de(sesion, tool_use_id="toolu_excluir"), "resolver_coincidencias",
                      {"grupos": [{"clave": clave, "decision": "unir", "excluir": [d]}]})
    assert "Quedan aparte (son otra persona)" in dict(conf.detalle) and conf.personas == {c, d, medio}
    r = ejecutar(sesion, ctx_de(sesion, tool_use_id="toolu_excluir"), "resolver_coincidencias", g)
    assert modelo(r)["resultados"][0]["ok"] is True and modelo(r)["unidas"] == 1
    assert db.coincidencias.find_one({"_id": cid3})["estado"] == "rechazada"
    assert db.personas.find_one({"_id": medio})["fusionada_en"] == c
    assert db.personas.find_one({"_id": d}).get("fusionada_en") is None


def test_una_clave_que_ya_no_es_el_grupo_se_vuelve_a_consultar(sesion, ctx_de):
    db = sesion.app.state.db
    a, b = _par_general(db)
    c = persona(db, nombre="ROSALBA INVENTADA DUPLICADA", telefono=TEL)
    autorizada(db, c)
    cid = coincidencia(db, a, b)
    coincidencia(db, b, c)  # el grupo ahora tiene dos pares: su clave cambió
    e = falla_tarjeta(sesion, ctx_de(sesion), "resolver_coincidencias",
                      {"grupos": [{"clave": str(cid), "decision": "separar"}]})
    assert e.codigo == "cambio"


# ───────────────────────────── conflictos_cedula ─────────────────────────────

def _conflicto(db, pid, motivo="posible_digitacion", fuente="general", **extra) -> int:
    cid = bd.siguiente_id(db, "conflictos_cedula")
    db.conflictos_cedula.insert_one({
        "_id": cid, "clave": f"c{cid}", "cedula": "93000554", "persona_id": pid, "motivo": motivo, "fuente": fuente,
        "importacion_id": 1, "puntaje_nombre": 0.91, "otra_persona": None, "estado": "pendiente", "creado_por": 0,
        "creado_en": bd.ahora(), "resuelto_por": None, "resuelto_en": None, "resolucion": None,
        "registro": {"nombre": "ANACLETA INVENTADA RIKA", "cedula": "93000554", "telefonos": [TEL2],
                     "direccion": "CALLE 9 # 9-99", "lugar_texto": "VEREDA INVENTADA", "sexo": "F", "edad": 40,
                     "fecha_nacimiento": "1986-04-02", "fila": 7, "fuente": fuente,
                     "datos": {"cedula_digitada": "93000554", "cedula_repetida": "93000545"}}, **extra})
    return cid


def test_conflictos_con_lista_blanca_y_fuente_politica_como_otra_base(sesion, ctx_de):
    """Con los datos políticos apagados (`agente_politicos`): encendidos, la fuente sale como es
    (tests/test_politicos_herramientas.py)."""
    db = sesion.app.state.db
    pid = rica(db)
    cid = _conflicto(db, pid)
    _conflicto(db, pid, motivo="nombre_distinto", fuente="planilla")
    res = leer(sesion, ctx_de(sesion, ajustes=SIN_POLITICOS), "conflictos_cedula", {})
    out = modelo(res)
    sin_datos(out, "93000554", "93000545", "1986-04-02", "CALLE 9")
    assert res.personas == {pid} and out["total"] == 2
    c = next(x for x in out["conflictos"] if x["id"] == cid)
    assert c["fuente"] == "otra_base" and c["cedula_ult3"] == "···554"
    assert c["fila"]["cedulas_coinciden"] is False and c["fila"]["numero_fila"] == 7
    assert c["persona"]["cedula_ult3"] == "···555" and c["decisiones"] == ["corregir", "descartar"]
    assert next(x for x in out["conflictos"] if x["id"] != cid)["fuente"] == "planilla"
    assert modelo(leer(sesion, ctx_de(sesion, ajustes=SIN_POLITICOS), "conflictos_cedula",
                       {"motivo": "nombre_distinto"}))["total"] == 1


def test_conflicto_con_quien_no_autorizo(sesion, ctx_de):
    db = sesion.app.state.db
    no = _no(db)
    cid = _conflicto(db, no)
    res = leer(sesion, ctx_de(sesion), "conflictos_cedula", {})
    c = modelo(res)["conflictos"][0]
    assert c["no_autorizo"] is True and set(c["persona"]) <= FORMA_NO_AUTORIZO
    assert "fila" not in c and "cedula_ult3" not in c and "RIKA" not in res.texto_para_modelo()
    ctx = ctx_de(sesion)
    ctx.via = "mcp"
    out = modelo(leer(sesion, ctx, "conflictos_cedula", {}))
    assert out["conflictos"] == [] and out["con_quien_no_autorizo"] == 1
    assert falla_tarjeta(sesion, ctx_de(sesion), "resolver_conflicto", {"conflicto_id": cid, "decision": "descartar"}
                         ).codigo == "no_contactable"


def test_resolver_conflicto_corregir_y_descartar_una_vez(sesion, como, ctx_de):
    db = sesion.app.state.db
    pid = rica(db)
    cid = _conflicto(db, pid)
    assert falla_tarjeta(sesion, ctx_de(sesion), "resolver_conflicto", {"conflicto_id": cid, "decision": "aplicar"}
                         ).codigo == "invalido"  # una posible digitación se corrige o se descarta

    def corregida(db):
        p = db.personas.find_one({"_id": pid})
        assert p["cedula"] == "93000545" and CEDULA in p["cedulas_anteriores"]
        assert db.conflictos_cedula.find_one({"_id": cid})["estado"] == "corregido"

    conf, r1, r2 = escribe_una_vez(sesion, ctx_de(sesion), "resolver_conflicto",
                                   {"conflicto_id": cid, "decision": "corregir", "cedula_correcta": "93.000.545",
                                    "motivo": "La dictó la titular"}, corregida)
    detalle = dict(conf.detalle)
    assert detalle["Cédula correcta"] == "93000545" and detalle["Ficha"].endswith("cédula ···555")
    assert "Otra base importada" in detalle["Fila"] and conf.personas == {pid}
    assert modelo(r1)["estado"] == "corregido" and modelo(r2)["ya_estaba"] is True
    otro = _conflicto(db, pid, motivo="nombre_distinto", fuente="tramites")

    def descartado(db):
        assert db.conflictos_cedula.find_one({"_id": otro})["estado"] == "descartado"

    escribe_una_vez(sesion, ctx_de(sesion, tool_use_id="toolu_descartar"), "resolver_conflicto",
                    {"conflicto_id": otro, "decision": "descartar"}, descartado)
    p = como("planillero")
    e = falla_leer(sesion, ctx_de(p), "conflictos_cedula", {})
    assert (e.codigo, e.estado) == ("permiso", 403)


# ───────────────────────────── situaciones ─────────────────────────────

def _situacion(db, pid, estado="fallecida", confirmada=False):
    db.personas.update_one({"_id": pid}, {"$set": {"situacion": {
        "estado": estado, "confirmada": confirmada, "reportado_por": {"uid": 7, "usuario": "ana.campo",
                                                                      "rol": "planillero"},
        "ts": bd.ahora(), "fuente": "panel"}}})


def test_situaciones_sin_quien_no_autorizo_y_confirmar_una_vez(sesion, como, ctx_de):
    db = sesion.app.state.db
    pid = rica(db)
    no = _no(db)
    _situacion(db, pid)
    _situacion(db, no, "no_reside")
    res = leer(sesion, ctx_de(sesion), "situaciones", {})
    out = modelo(res)
    sin_datos(out, "ana.campo")
    assert out["total"] == 1 and [x["id"] for x in out["situaciones"]] == [pid] and res.personas == {pid}
    assert "EUDOSIA" not in res.texto_para_modelo()

    def confirmada(db):
        assert db.personas.find_one({"_id": pid})["situacion"]["confirmada"] is True

    conf, _, r2 = escribe_una_vez(sesion, ctx_de(sesion), "confirmar_situacion",
                                  {"persona_id": pid, "decision": "confirmar"}, confirmada)
    assert conf.personas == {pid} and dict(conf.detalle)["Situación reportada"] == "Fallecida"
    assert modelo(r2)["ya_estaba"] is True

    def revertida(db):
        assert db.personas.find_one({"_id": pid})["situacion"]["estado"] == "activa"

    escribe_una_vez(sesion, ctx_de(sesion, tool_use_id="toolu_revertir"), "confirmar_situacion",
                    {"persona_id": pid, "decision": "revertir"}, revertida)
    assert falla_tarjeta(sesion, ctx_de(sesion), "confirmar_situacion", {"persona_id": no, "decision": "confirmar"}
                         ).codigo == "no_contactable"
    c = como("consultor")
    assert falla_leer(sesion, ctx_de(c), "situaciones", {}).estado == 403


# ───────────────────────────── solicitudes ─────────────────────────────

def test_solicitudes_sin_de_quien_son_y_actualizar_una_vez(sesion, como, ctx_de):
    db = sesion.app.state.db
    pid = rica(db)
    r = sesion.post("/api/solicitudes", json={"persona_id": pid, "tipo": "supresion", "canal": "visita",
                                              "descripcion": f"Que borren todo; su hija responde al {TEL2}"})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    sesion.post("/api/solicitudes", json={"tipo": "consulta", "canal": "correo", "descripcion": "Qué datos tienen"})
    res = leer(sesion, ctx_de(sesion), "solicitudes", {})
    out = modelo(res)
    sin_datos(out, "ANACLETA", "borren")
    assert res.personas == set() and out["total"] == 2 and out["por_tipo"] == {"supresion": 1, "consulta": 1}
    assert all("persona_id" not in s and "persona" not in s for s in out["solicitudes"])

    def cambia(db):
        s = db.solicitudes.find_one({"_id": sid})
        assert s["estado"] == "resuelta" and s["respuesta"] == "Se suprimieron sus datos en el panel"

    conf, r1, r2 = escribe_una_vez(sesion, ctx_de(sesion), "actualizar_solicitud",
                                   {"solicitud_id": sid, "estado": "resuelta",
                                    "respuesta": "Se suprimieron sus datos en el panel"}, cambia)
    # La tarjeta muestra de quién es (y la anota); al modelo no le llega
    assert dict(conf.detalle)["Persona"] == f"ANACLETA INVENTADA RICA (#{pid})" and conf.personas == {pid}
    assert "no suprime los datos" in conf.aviso
    assert "ANACLETA" not in r1.texto_para_modelo() and r1.personas == set()
    assert modelo(r2)["ya_estaba"] is True
    p = como("planillero")
    assert falla_leer(sesion, ctx_de(p), "solicitudes", {}).estado == 403
    assert falla_tarjeta(sesion, ctx_de(p), "actualizar_solicitud", {"solicitud_id": sid, "estado": "pendiente"}
                         ).estado == 403


# ───────────────────────────── importaciones ─────────────────────────────

def test_importaciones_sin_las_bases_politicas(sesion, como, ctx_de):
    """Con los datos políticos apagados (`agente_politicos`): encendidos, salen como son
    (tests/test_politicos_herramientas.py)."""
    db = sesion.app.state.db
    db.importaciones.insert_many([
        {"_id": 1, "ts": "2026-11-01T15:00:00+00:00", "usuario": "admin", "uid": 0, "capturado_por": None,
         "archivo": "base general lideres zona norte.xlsx", "tipo": "general", "evidencia_sha256": {},
         "resumen": {"personas_nuevas": 812, "registros_por_fuente": {"general": 812}, "tipos_marcados": {"lider": 9},
                     "lideres_asignados": 40}},
        {"_id": 2, "ts": "2026-11-02T15:00:00+00:00", "usuario": "admin", "uid": 0, "capturado_por": None,
         "archivo": "cedulas.xlsx, planilla vereda.xlsx", "tipo": "cedulas, planilla", "evidencia_sha256": {},
         "resumen": {"personas_nuevas": 30}},
        {"_id": 3, "ts": "2026-11-03T15:00:00+00:00", "usuario": "coordinador7", "uid": 7, "capturado_por": 12,
         "archivo": f"planilla de {TEL}.xlsx", "tipo": "planilla", "evidencia_sha256": {"a": "b"},
         "resumen": {"personas_nuevas": 14, "autorizaciones_por_confirmar": 6, "registros_por_fuente": {"planilla": 15},
                     "suprimidas_omitidas": 1, "planilleros_desconocidos": ["MARTA INVENTADA"]}},
    ])
    res = leer(sesion, ctx_de(sesion, ajustes=SIN_POLITICOS), "importaciones", {})
    out = modelo(res)
    sin_datos(out, "812", "lideres", "lider", "MARTA", "suprimidas")
    por_id = {x["id"]: x for x in out["importaciones"]}
    assert por_id[1] == {"id": 1, "fecha": "2026-11-01", "usuario": "admin", "tipo": "otra_base"}
    assert por_id[2]["tipo"] == "otra_base" and "resumen" not in por_id[2]
    assert por_id[3]["resumen"] == {"personas_nuevas": 14, "autorizaciones_por_confirmar": 6}
    assert por_id[3]["archivo"] == "planilla de ···011.xlsx" and por_id[3]["capturado_por"] == 12
    assert "6 autorizaciones por confirmar" in res.resumen
    for rol in ("planillero", "consultor"):
        assert falla_leer(sesion, ctx_de(como(rol)), "importaciones", {}).estado == 403


# ───────────────────────────── puestos ─────────────────────────────

def test_puestos_con_el_censo_y_el_consultor_solo_codigo_y_nombre(sesion, como, ctx_de):
    out = modelo(leer(sesion, ctx_de(sesion), "puestos", {}))
    assert out["total"] >= 7 and out["totales"]["habilitados"] > 0
    p0 = out["puestos"][0]
    assert {"id", "codigo", "nombre", "mesas", "habilitados"} <= set(p0) and "lat" not in p0 and "alias" not in p0
    uno = modelo(leer(sesion, ctx_de(sesion), "puestos", {"texto": p0["codigo"]}))
    assert [x["id"] for x in uno["puestos"]] == [p0["id"]]
    c = como("consultor")
    out = modelo(leer(sesion, ctx_de(c), "puestos", {}))
    assert all(set(x) <= {"id", "codigo", "nombre"} for x in out["puestos"]) and "totales" not in out


# ───────────────────────────── lugares_sin_reconocer ─────────────────────────────

def test_lugares_sin_reconocer_no_cuentan_a_quien_no_autorizo(sesion, como, ctx_de):
    db = sesion.app.state.db
    for i in range(3):
        persona(db, nombre=f"VECINA INVENTADA {i}", lugar_id=None, lugar_texto="VILLA INVENTADA")
    persona(db, nombre="VECINA NO INVENTADA", lugar_id=None, lugar_texto="VILLA INVENTADA", consentimiento="no")
    persona(db, nombre="SOLA INVENTADA", lugar_id=None, lugar_texto="FINCA SOLITARIA")
    persona(db, nombre="SOLA NO INVENTADA", lugar_id=None, lugar_texto="FINCA SOLITARIA", consentimiento="no")
    res = leer(sesion, ctx_de(sesion), "lugares_sin_reconocer", {})
    out = modelo(res)
    textos = {x["texto"]: x["personas"] for x in out["textos"]}
    assert textos.get("VILLA INVENTADA") == 3 and "FINCA SOLITARIA" not in textos
    assert res.personas == set()
    for rol in ("planillero", "consultor"):
        assert falla_leer(sesion, ctx_de(como(rol)), "lugares_sin_reconocer", {}).estado == 403


@pytest.mark.parametrize("nombre", ["coincidencias", "conflictos_cedula", "situaciones", "solicitudes",
                                    "importaciones", "lugares_sin_reconocer"])
def test_lecturas_vacias(sesion, ctx_de, nombre):
    r = leer(sesion, ctx_de(sesion), nombre, {})
    assert r.resumen and modelo(r)


def test_escrituras_de_calidad_rechazadas_al_planillero_por_la_api(sesion, como, ctx_de):
    """Si P las llamara (una lista vieja, un error), la API las rechaza con 403 sin escribir nada."""
    db = sesion.app.state.db
    pid = rica(db)
    _situacion(db, pid)
    cid = _conflicto(db, pid)
    p = como("planillero")
    antes = foto(db)
    for nombre, entrada in (("resolver_conflicto", {"conflicto_id": cid, "decision": "descartar"}),
                            ("confirmar_situacion", {"persona_id": pid, "decision": "confirmar"})):
        e = falla_ejecutar(sesion, ctx_de(p), nombre, H[nombre].validar(entrada))
        assert e.estado == 403, nombre
    assert foto(db) == antes


# ───────────────────────────── Listas blancas, sin base ─────────────────────────────

def test_los_avisos_de_un_grupo_no_traen_nombres_ni_el_texto_de_las_senales():
    from app.agente.herramientas import calidad as hc
    avisos = ["Tienen 2 cédulas distintas: dos cédulas distintas nunca se unen. Marque «No es la misma» en las que "
              "sobran.", "Ya se marcó antes que ANA INVENTADA y LUZ INVENTADA son personas distintas.",
              "Grupo grande (7 fichas): suele ser una cadena por nombres comunes. Revíselo con cuidado.",
              "ANA INVENTADA y LUZ INVENTADA no tienen una coincidencia directa y quedarían unidas: las dos vienen "
              "solo de la base general y sin cédula.", "Un aviso nuevo sobre ANA INVENTADA", "Otro aviso nuevo"]
    out = hc._avisos(avisos)
    assert len(out) == 5 and out[-1] == hc.OTRO_AVISO
    assert "INVENTADA" not in str(out) and "general" not in str(out)


def test_conflicto_dictado_sin_fuente_ni_fila_y_con_sus_decisiones():
    from app.agente.herramientas import calidad as hc
    ficha = {"id": 4, "nombre": "ANA INVENTADA", "cedula": None, "telefono": TEL, "correo": "ana@correo.co",
             "fuentes": ["general"], "listas": "Lista Inventada Q9", "lugar": "VEREDA INVENTADA", "consentimiento": "si",
             "completitud": 50}
    duena = {**ficha, "id": 5, "nombre": "LUZ INVENTADA", "cedula": CEDULA}
    c = {"id": 9, "motivo": "dictada", "cedula": CEDULA, "fuente": "consultor", "estado": "pendiente",
         "creado_en": "2026-11-20T12:00:00+00:00", "registro": {"nombre": "ANA INVENTADA"}, "persona": ficha,
         "duena": duena, "otra_persona": None}
    out = hc.conflicto_para_modelo(c, frozenset())
    sin_datos(out)
    assert "fuente" not in out and "fila" not in out and out["decisiones"] == ["reportar", "descartar"]
    assert out["duena"]["cedula_ult3"] == "···555" and out["fecha"] == "2026-11-20"
