"""MCP con datos (app/api/mcp.py, app/api/pantalla.py, app/sesion_interna.py): las dos claves por persona, los alcances
por rol, las herramientas exactas de cada alcance, las lecturas (sin quien no autorizó, páginas chicas, topes diarios,
entregas auditadas), las propuestas de escritura y su aprobación en Mi cuenta (con la sesión real, de punta a punta),
el IDOR de las propuestas, la anulación al revocar o reemplazar la clave, las sesiones internas (no desalojan las del
navegador ni salen en Usuarios) y la clave de datos solo por `Authorization: Bearer`.

Con MongoDB (fixtures `sesion` y `como`). Solo datos inventados."""
import json
import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from ayudas_g3 import autorizada, coordinador, persona
from app import db as bd
from app import sesion_interna
from app.agente import herramientas
from app.agente.herramientas import planillas as h_planillas
from app.api import mcp
from app.api.pantalla import huella_clave

# Lo que ya existía antes de las herramientas nuevas: se decide aquí, una por una (DECISIONES §D)
LECTURA_EXISTENTES = {"buscar_personas", "ver_persona", "personas_parecidas", "listar_reuniones", "ver_reunion",
                      "pendientes", "catalogos", "buscar_lugar", "indicadores"}
ESCRITURA_EXISTENTES = {"crear_persona", "editar_persona", "agregar_nota", "registrar_acercamiento", "ubicar_persona",
                        "agregar_telefono", "crear_reunion", "agregar_asistente"}
ANALITICA_EXISTENTES = {"analizar", "diagnostico"}
NUNCA = {"registrar_autorizacion", "equipo", "mi_trabajo", "mapa", "abrir_vista", "presentacion"}


# ───────────────────────────── Ayudas ─────────────────────────────

def _ajustes_mcp(db, **campos) -> None:
    """Cambia `agente_mcp` en los ajustes guardados (sin pasar por la API)."""
    db.meta.update_one({"_id": "ajustes"}, {"$set": {f"agente_mcp.{k}": v for k, v in campos.items()}}, upsert=True)


def _clave_datos(c, *alcances) -> str:
    r = c.post("/api/pantalla/clave", json={"tipo": "datos", "alcances": list(alcances)})
    assert r.status_code == 200, r.text
    return r.json()["clave"]


def _agente(app) -> TestClient:
    return TestClient(app)


def _rpc(agente, clave, metodo, params=None, id_=1):
    r = agente.post("/api/mcp", headers={"Authorization": f"Bearer {clave}"},
                    json={"jsonrpc": "2.0", "id": id_, "method": metodo, **({"params": params} if params else {})})
    assert r.status_code == 200, r.text
    return r.json()


def _llamar(agente, clave, nombre, argumentos):
    return _rpc(agente, clave, "tools/call", {"name": nombre, "arguments": argumentos})


def _ok(respuesta) -> dict:
    res = respuesta["result"]
    assert res["isError"] is False, res
    assert "structuredContent" not in res  # iría entero, sin el recorte de texto_para_modelo
    return json.loads(res["content"][0]["text"])


def _falla(respuesta) -> dict:
    res = respuesta["result"]
    assert res["isError"] is True, res
    return json.loads(res["content"][0]["text"])["error"]


def _nombres(agente, clave) -> set[str]:
    return {h["name"] for h in _rpc(agente, clave, "tools/list")["result"]["tools"]}


def _esperadas(alcance: str) -> set[str]:
    return {h.nombre for h in herramientas.fijas() if h.alcance_mcp() == alcance}


def _sin_sesiones_internas(db) -> bool:
    return db.sesiones.count_documents({"via": {"$exists": True}}) == 0


# ───────────────────────────── Las marcas: qué sale por MCP ─────────────────────────────

def test_nombres_exactos_por_alcance():
    lectura, analitica, escritura = _esperadas("lectura"), _esperadas("analitica"), _esperadas("escritura")
    # Las que ya existían, decididas una por una; las nuevas (de otras áreas) entran solo si están marcadas
    assert LECTURA_EXISTENTES <= lectura and ESCRITURA_EXISTENTES <= escritura and ANALITICA_EXISTENTES <= analitica
    assert not NUNCA & (lectura | analitica | escritura)
    assert not (lectura & escritura) and not (lectura & analitica) and not (analitica & escritura)
    # Lo que no está marcado nunca sale: la regla de las marcas, herramienta por herramienta
    for h in herramientas.fijas():
        if h.mcp is None or h.tipo == "interfaz" or h.nombre_remoto:
            assert h.alcance_mcp() is None, h.nombre
        if h.alcance_mcp() == "escritura":
            assert h.tipo == "escritura" and h.confirmar is not None, h.nombre
        if h.alcance_mcp() in ("lectura", "analitica"):
            assert h.tipo == "lectura", h.nombre
    # Las de planillas (fotos: solo en el chat) y la consulta de propuestas (solo existe por MCP) no son del catálogo
    assert all(h.alcance_mcp() is None for h in h_planillas.HERRAMIENTAS)
    assert mcp.ESTADO_PROPUESTA not in {h.nombre for h in herramientas.fijas()}
    # Las marcas de las existentes, exactas
    por_nombre = herramientas.por_nombre()
    assert {n: por_nombre[n].mcp for n in LECTURA_EXISTENTES} == {n: "lectura" for n in LECTURA_EXISTENTES}
    assert {n: por_nombre[n].mcp for n in ESCRITURA_EXISTENTES} == {n: "escritura" for n in ESCRITURA_EXISTENTES}
    assert {n: por_nombre[n].mcp for n in NUNCA} == {n: None for n in NUNCA}


def test_sin_no_autorizo_quita_las_filas_y_deja_el_conteo():
    from app.agente import minimizar
    no = minimizar.no_autorizo({"id": 7, "nombre": "ROSA INVENTADA", "lugar_nombre": "Centro"})
    contenido = {"filas": [{"id": 1, "nombre": "ANA INVENTADA"}, no], "reunion": {"asistentes": [no, {"id": 2}]},
                 "persona": no, "total": 3}
    limpio, ids, n, entera = mcp.sin_no_autorizo(contenido)
    assert ids == {7} and n == 3 and not entera
    assert limpio["filas"] == [{"id": 1, "nombre": "ANA INVENTADA"}] and limpio["reunion"]["asistentes"] == [{"id": 2}]
    assert limpio["persona"] is None and limpio["total"] == 3 and limpio["omitidas_no_autorizo"] == 3
    assert "ROSA" not in json.dumps(limpio)
    # Una lista suelta queda dentro de un objeto con el conteo; una ficha entera de quien no autorizó, nada
    limpio, ids, n, entera = mcp.sin_no_autorizo([no, {"id": 3}])
    assert limpio["resultado"] == [{"id": 3}] and limpio["omitidas_no_autorizo"] == 1
    assert mcp.sin_no_autorizo(no)[3] is True
    # Sin filas de esas, el contenido sale igual
    assert mcp.sin_no_autorizo({"a": [1, {"b": 2}]}) == ({"a": [1, {"b": 2}]}, set(), 0, False)


# ───────────────────────────── Claves y alcances por rol ─────────────────────────────

def test_alcances_por_rol_al_crear_la_clave(sesion, como):
    db = sesion.app.state.db
    info = sesion.get("/api/pantalla/clave").json()
    assert info["permitidos"] == ["lectura", "analitica", "escritura"] and info["motivos"] == {}
    assert info["datos"]["tiene"] is False and info["propuestas_pendientes"] == 0 and info["tiene"] is False
    # El coordinador, con los ajustes de defecto (`agente_mcp.roles` = admin): nada
    k = coordinador(sesion.app, db)
    info = k.get("/api/pantalla/clave").json()
    assert info["permitidos"] == [] and set(info["motivos"]) == {"lectura", "analitica", "escritura"}
    r = k.post("/api/pantalla/clave", json={"tipo": "datos", "alcances": ["analitica"]})
    assert r.status_code == 403 and r.json()["detail"]["codigo"] == "permiso"
    # Habilitado: analítica y escritura, nunca lectura (leer personas por MCP es exportarlas: solo A)
    _ajustes_mcp(db, roles=["admin", "coordinador"])
    info = k.get("/api/pantalla/clave").json()
    assert info["permitidos"] == ["analitica", "escritura"] and "lectura" in info["motivos"]
    r = k.post("/api/pantalla/clave", json={"tipo": "datos", "alcances": ["lectura", "analitica"]})
    assert r.status_code == 403 and r.json()["detail"]["alcances"] == ["lectura"]
    assert db.claves_mcp.count_documents({"uid": k.uid}) == 0
    r = k.post("/api/pantalla/clave", json={"alcances": ["escritura", "analitica"]})  # sin tipo: los alcances lo dicen
    assert r.status_code == 200, r.text
    nueva = r.json()
    assert nueva["clave"].startswith("ypd_") and nueva["tipo"] == "datos" and "direccion_con_clave" not in nueva
    assert nueva["alcances"] == ["analitica", "escritura"] and nueva["datos"]["tiene"] is True
    guardada = db.claves_mcp.find_one({"uid": k.uid})
    assert guardada["_id"] == huella_clave(nueva["clave"]) and nueva["clave"] not in json.dumps(guardada, default=str)
    assert timedelta(days=29) < guardada["expira"] - datetime.now(timezone.utc) <= timedelta(days=30)
    a = db.auditoria.find_one({"accion": "crear_clave_mcp", "uid": k.uid})
    assert a and json.loads(a["detalle"]) == {"tipo": "datos", "alcances": ["analitica", "escritura"]}
    # Planillero y consultor: ninguna, aunque el ajuste los nombrara (solo admite A y K)
    _ajustes_mcp(db, roles=["admin", "coordinador", "planillero", "consultor"])
    for rol in ("planillero", "consultor"):
        c = como(rol)
        assert c.get("/api/pantalla/clave").json()["permitidos"] == []
        assert c.post("/api/pantalla/clave", json={"tipo": "datos", "alcances": ["escritura"]}).status_code == 403
        assert c.post("/api/pantalla/clave").status_code == 200  # la de la presentación, como siempre
    # Las escrituras se apagan con cualquiera de los dos ajustes
    _ajustes_mcp(db, escritura=False)
    assert sesion.get("/api/pantalla/clave").json()["permitidos"] == ["lectura", "analitica"]
    _ajustes_mcp(db, escritura=True)
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"agente.escritura": False}})
    assert "escritura" in sesion.get("/api/pantalla/clave").json()["motivos"]


def test_el_cuerpo_de_la_clave_se_valida(sesion):
    for cuerpo in ({"tipo": "datos", "alcances": ["presentacion"]}, {"tipo": "datos"},
                   {"tipo": "datos", "alcances": ["lectura", "presentacion"]},
                   {"tipo": "presentacion", "alcances": ["lectura"]}, {"alcances": ["todo"]}, {"otra": 1}):
        assert sesion.post("/api/pantalla/clave", json=cuerpo).status_code == 422, cuerpo
    assert sesion.post("/api/pantalla/clave", json={}).json()["clave"].startswith("ypm_")
    r = sesion.post("/api/pantalla/clave", json={"alcances": ["presentacion"]}).json()
    assert r["tipo"] == "presentacion" and r["direccion_con_clave"].endswith(f"?clave={r['clave']}")


def test_dos_claves_por_persona_cada_una_reemplaza_solo_la_suya(sesion):
    db = sesion.app.state.db
    agente = _agente(sesion.app)
    pres = sesion.post("/api/pantalla/clave").json()["clave"]
    datos = _clave_datos(sesion, "analitica")
    assert db.claves_mcp.count_documents({"uid": 0}) == 2
    info = sesion.get("/api/pantalla/clave").json()
    assert info["tiene"] is True and info["datos"]["tiene"] is True and info["datos"]["alcances"] == ["analitica"]
    assert _rpc(agente, pres, "initialize")["result"]["serverInfo"]["name"] == "yondo-presentacion"
    inicio = _rpc(agente, datos, "initialize")["result"]
    assert inicio["serverInfo"]["name"] == "yondo-datos" and "PROPUESTA" in inicio["instructions"]
    assert inicio["capabilities"] == {"tools": {"listChanged": False}}
    # Otra de la presentación no toca la de datos, y al revés
    pres2 = sesion.post("/api/pantalla/clave").json()["clave"]
    assert _inicio_http(agente, pres) == 401
    assert _rpc(agente, datos, "ping")["result"] == {}
    datos2 = _clave_datos(sesion, "lectura")
    assert _inicio_http(agente, datos) == 401
    assert _rpc(agente, pres2, "ping")["result"] == {} and _rpc(agente, datos2, "ping")["result"] == {}
    # La de la presentación nunca da datos, la de datos nunca proyecta
    assert _nombres(agente, pres2) == {"presentacion"}
    assert _llamar(agente, pres2, "buscar_personas", {"q": "ANA"})["error"]["code"] == -32602
    assert "presentacion" not in _nombres(agente, datos2)
    assert _llamar(agente, datos2, "presentacion", {"op": "estado"})["error"]["code"] == -32602
    # Revocar una sola; sin tipo, las dos
    r = sesion.delete("/api/pantalla/clave?tipo=presentacion").json()
    assert r["revocada"] is True and r["tiene"] is False and r["datos"]["tiene"] is True
    assert _rpc(agente, datos2, "ping")["result"] == {}
    pres3 = sesion.post("/api/pantalla/clave").json()["clave"]
    assert sesion.delete("/api/pantalla/clave").json()["revocada"] is True
    assert db.claves_mcp.count_documents({"uid": 0}) == 0
    for clave in (pres3, datos2):
        assert _inicio_http(agente, clave) == 401
    assert db.auditoria.count_documents({"accion": "revocar_clave_mcp", "uid": 0}) == 2
    agente.close()


def mcp_inicio() -> dict:
    return {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                       "clientInfo": {"name": "prueba", "version": "1"}}}


def _inicio_http(agente, clave) -> int:
    """El estado HTTP de un `initialize` con la clave en la cabecera."""
    return agente.post("/api/mcp", headers={"Authorization": f"Bearer {clave}"}, json=mcp_inicio()).status_code


def test_la_clave_de_datos_va_solo_en_la_cabecera_y_vence(sesion):
    db = sesion.app.state.db
    datos = _clave_datos(sesion, "analitica")
    agente = _agente(sesion.app)
    r = agente.post(f"/api/mcp?clave={datos}", json=mcp_inicio())
    assert r.status_code == 401 and "Authorization: Bearer" in r.json()["error"]
    assert r.headers["www-authenticate"].startswith("Bearer")
    assert db.claves_mcp.find_one({"_id": huella_clave(datos)})["usada"] is None  # ni cuenta como usada
    # Con la cabecera, sí (aunque la dirección traiga otra cosa: manda la cabecera)
    r = agente.post("/api/mcp?clave=ypm_otra", headers={"Authorization": f"Bearer {datos}"}, json=mcp_inicio())
    assert r.status_code == 200
    # Vencida (el índice TTL tarda hasta un minuto): no vale aunque siga en la base
    antes = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.claves_mcp.update_one({"_id": huella_clave(datos)}, {"$set": {"expira": antes}})
    assert _inicio_http(agente, datos) == 401
    # Una de datos sin fecha: tampoco
    db.claves_mcp.update_one({"_id": huella_clave(datos)}, {"$unset": {"expira": ""}})
    assert _inicio_http(agente, datos) == 401
    assert sesion.get("/api/pantalla/clave").json()["datos"]["tiene"] is False
    agente.close()


def test_herramientas_exactas_por_rol_y_alcance(sesion):
    db = sesion.app.state.db
    agente = _agente(sesion.app)
    completa = _clave_datos(sesion, "lectura", "analitica", "escritura")
    lista = _rpc(agente, completa, "tools/list")["result"]["tools"]
    nombres = [h["name"] for h in lista]
    assert len(nombres) == len(set(nombres))
    assert set(nombres) == _esperadas("lectura") | _esperadas("analitica") | _esperadas("escritura") | {
        mcp.ESTADO_PROPUESTA}
    por_nombre = {h["name"]: h for h in lista}
    for h in herramientas.fijas():
        if h.alcance_mcp() == "escritura":
            d = por_nombre[h.nombre]
            esquema = d["inputSchema"]
            assert mcp.CAMPO_MOTIVO in esquema["properties"] and mcp.CAMPO_MOTIVO in esquema["required"], h.nombre
            assert esquema.get("additionalProperties") is False, h.nombre
            assert d["annotations"]["readOnlyHint"] is False and "NO se ejecuta" in d["description"]
        elif h.alcance_mcp():
            assert por_nombre[h.nombre]["annotations"]["readOnlyHint"] is True, h.nombre
            assert mcp.CAMPO_MOTIVO not in por_nombre[h.nombre]["inputSchema"].get("properties", {})
    assert por_nombre["buscar_personas"]["inputSchema"]["properties"]["por_pagina"]["maximum"] == mcp.POR_PAGINA_MCP
    # El esquema del catálogo no cambió (lo de MCP va en una copia)
    assert mcp.CAMPO_MOTIVO not in herramientas.por_nombre()["agregar_nota"].input_schema()["properties"]
    # Un solo alcance: solo lo suyo
    assert _nombres(agente, _clave_datos(sesion, "analitica")) == _esperadas("analitica")
    # El coordinador: sin lectura nunca; con escritura, la consulta de propuestas
    _ajustes_mcp(db, roles=["admin", "coordinador"])
    k = coordinador(sesion.app, db)
    clave_k = _clave_datos(k, "analitica", "escritura")
    vistas = _nombres(agente, clave_k)
    assert not vistas & _esperadas("lectura")
    assert vistas == _esperadas("analitica") | _esperadas("escritura") | {mcp.ESTADO_PROPUESTA}
    assert _llamar(agente, clave_k, "buscar_personas", {"q": "ANA"})["error"]["code"] == -32602
    # Los alcances se vuelven a mirar en cada petición: el ajuste apaga las escrituras sin crear otra clave
    _ajustes_mcp(db, escritura=False)
    assert _nombres(agente, clave_k) == _esperadas("analitica")
    assert _llamar(agente, clave_k, mcp.ESTADO_PROPUESTA, {"propuesta": "0" * 32})["error"]["code"] == -32602
    # Y el rol: si sale de `agente_mcp.roles`, la clave queda sin herramientas (y las llamadas, sin nada que llamar)
    _ajustes_mcp(db, roles=["admin"], escritura=True)
    assert _nombres(agente, clave_k) == set()
    assert sesion.get("/api/pantalla/clave").json()["datos"]["vigentes"] == ["analitica"]  # la última de A
    assert k.get("/api/pantalla/clave").json()["datos"]["vigentes"] == []
    agente.close()


# ───────────────────────────── Lecturas ─────────────────────────────

def test_lectura_sin_quien_no_autorizo_con_paginas_chicas_y_entregas_auditadas(sesion):
    db = sesion.app.state.db
    lugar = db.lugares.find_one({}, {"_id": 1})["_id"]
    si = [persona(db, nombre=f"MARGARITA LECTURA {x}", lugar_id=lugar) for x in ("UNO", "DOS", "TRES")]
    for pid in si:
        autorizada(db, pid)
    no = persona(db, nombre="MARGARITA LECTURA NEGADA", lugar_id=lugar, consentimiento="no")
    agente = _agente(sesion.app)
    clave = _clave_datos(sesion, "lectura")
    # Búsqueda rápida por nombre: en el chat sale quien no autorizó (quién es); por MCP, ni eso
    d = _ok(_llamar(agente, clave, "buscar_personas", {"q": "MARGARITA LECTURA"}))
    assert {f["id"] for f in d["filas"]} == set(si) and d["omitidas_no_autorizo"] == 1
    assert "NEGADA" not in json.dumps(d) and str(no) not in [str(f["id"]) for f in d["filas"]]
    # La lista: de a POR_PAGINA_MCP aunque pida 50
    d = _ok(_llamar(agente, clave, "buscar_personas", {"q": "MARGARITA", "por_pagina": 50}))
    assert d["por_pagina"] == mcp.POR_PAGINA_MCP and "NEGADA" not in json.dumps(d)
    # La ficha de quien no autorizó: nada, ni su nombre
    e = _falla(_llamar(agente, clave, "ver_persona", {"persona_id": no}))
    assert e["codigo"] == "no_contactable" and "NEGADA" not in json.dumps(e)
    f = _ok(_llamar(agente, clave, "ver_persona", {"persona_id": si[0]}))
    assert f["id"] == si[0] and "cedula" not in f
    # Cada llamada queda en mcp_entregas (con las personas entregadas) y cada entrega en la auditoría, con via «mcp»
    entregas = list(db.mcp_entregas.find({"clave_h": huella_clave(clave)}))
    assert len(entregas) == 4 and all(e["uid"] == 0 for e in entregas)
    assert set().union(*(set(e["personas"]) for e in entregas)) == set(si) and no not in {
        p for e in entregas for p in e["personas"]}
    auditadas = list(db.auditoria.find({"accion": "entrega_mcp"}))
    assert len(auditadas) == 3 and all(a["via"] == "mcp" and a["uid"] == 0 for a in auditadas)
    assert json.loads(auditadas[0]["detalle"])["personas"] == 3
    # Las lecturas de la API quedan a nombre de quien es dueño de la clave (sesión interna), y la sesión se cerró
    assert db.lecturas.count_documents({"uid": 0, "pid": si[0]}) == 1
    assert _sin_sesiones_internas(db)
    agente.close()


def test_se_descarta_lo_de_una_persona_suprimida_mientras_se_leia(sesion, monkeypatch):
    db = sesion.app.state.db
    pid = persona(db, nombre="TOMASA DESCARTE INVENTADA")
    autorizada(db, pid)
    agente = _agente(sesion.app)
    clave = _clave_datos(sesion, "lectura")
    from app.agente import conversaciones as conv_db
    monkeypatch.setattr(conv_db, "dejaron_de_autorizar", lambda db_, ids, desde: sorted(ids))
    e = _falla(_llamar(agente, clave, "ver_persona", {"persona_id": pid}))
    assert e["codigo"] == "descartado" and "TOMASA" not in json.dumps(e)
    assert db.auditoria.count_documents({"accion": "entrega_mcp"}) == 0
    agente.close()


def test_topes_diarios_de_llamadas_y_de_personas(sesion):
    db = sesion.app.state.db
    ids = [persona(db, nombre=f"TOPE INVENTADA {i:02d}") for i in range(12)]
    for pid in ids:
        autorizada(db, pid)
    _ajustes_mcp(db, personas_diarias=10)
    agente = _agente(sesion.app)
    clave = _clave_datos(sesion, "lectura")
    p1 = _ok(_llamar(agente, clave, "buscar_personas", {"q": "TOPE", "por_pagina": 10, "pagina": 1}))
    assert len(p1["filas"]) == 10
    e = _falla(_llamar(agente, clave, "buscar_personas", {"q": "TOPE", "por_pagina": 10, "pagina": 2}))
    assert e["codigo"] == "tope_personas"
    # Las mismas de antes sí: el tope es de personas distintas, y la entrega rechazada no cuenta
    assert len(_ok(_llamar(agente, clave, "buscar_personas", {"q": "TOPE", "por_pagina": 10}))["filas"]) == 10
    assert mcp.personas_del_dia(db, huella_clave(clave), mcp._dia()) == 10
    # Llamadas: con 10 por día, la 11.ª no corre (ya van 3). Sin `arguments` (una herramienta sin parámetros) vale
    _ajustes_mcp(db, llamadas_diarias=10)
    assert _ok(_rpc(agente, clave, "tools/call", {"name": "pendientes"})) is not None
    assert _falla(_rpc(agente, clave, "tools/call", {"name": "pendientes", "arguments": "x"}))["codigo"] == "invalido"
    for _ in range(5):
        _ok(_llamar(agente, clave, "catalogos", {}))
    assert _falla(_llamar(agente, clave, "catalogos", {}))["codigo"] == "tope_llamadas"
    assert db.mcp_entregas.count_documents({"clave_h": huella_clave(clave)}) == 10
    # Otra clave tiene su propio tope
    assert _ok(_llamar(agente, _clave_datos(sesion, "lectura"), "catalogos", {}))
    agente.close()


# ───────────────────────────── Propuestas de escritura ─────────────────────────────

def _proponer_nota(agente, clave, pid, texto="Pidió que la llamen en la tarde.", motivo="Lo dictó en la reunión"):
    return _llamar(agente, clave, "agregar_nota", {"persona_id": pid, "texto": texto, "motivo_propuesta": motivo})


def test_propuesta_y_aprobacion_de_punta_a_punta(sesion):
    db = sesion.app.state.db
    pid = persona(db, nombre="CLEMENCIA PROPUESTA INVENTADA")
    autorizada(db, pid)
    agente = _agente(sesion.app)
    clave = _clave_datos(sesion, "lectura", "escritura")
    # Sin motivo (o con uno vacío o largo) no hay propuesta
    sin = _llamar(agente, clave, "agregar_nota", {"persona_id": pid, "texto": "Hola"})
    assert _falla(sin)["codigo"] == "invalido" and mcp.CAMPO_MOTIVO in _falla(sin)["mensaje"]
    assert _falla(_proponer_nota(agente, clave, pid, motivo="   "))["codigo"] == "invalido"
    assert _falla(_proponer_nota(agente, clave, pid, motivo="x" * 301))["codigo"] == "invalido"
    assert db.mcp_propuestas.count_documents({}) == 0
    texto = "Pidió que la llamen en la tarde.\n  Vive cerca del parque."
    d = _ok(_proponer_nota(agente, clave, pid, texto=texto))
    assert d["estado"] == "pendiente" and re.fullmatch(r"[0-9a-f]{32}", d["propuesta"])
    assert d["aprobar_en"].endswith(f"/cuenta?propuesta={d['propuesta']}") and "NO está hecho" in d["mensaje"]
    assert "CLEMENCIA" not in json.dumps(d)  # la tarjeta (con el nombre) nunca va al agente
    assert not (db.personas.find_one({"_id": pid}).get("notas") or [])  # nada escrito todavía
    guardada = db.mcp_propuestas.find_one({"_id": d["propuesta"]})
    assert guardada["uid"] == 0 and guardada["clave_h"] == huella_clave(clave) and guardada["personas"] == [pid]
    assert guardada["vence"] - guardada["creada"] == timedelta(hours=48) and guardada["expira"] == guardada["vence"]
    # Mi cuenta: la tarjeta entera, el motivo, de qué clave y desde qué IP; la insignia la cuenta
    lista = sesion.get("/api/mcp/propuestas").json()
    p = lista["propuestas"][0]
    assert p["id"] == d["propuesta"] and p["motivo"] == "Lo dictó en la reunión" and p["ip"]
    assert ["Nota", texto] in p["detalle"] and p["titulo"].startswith("Agregar una nota a")
    assert p["clave"]["vigente"] is True and p["clave"]["huella"] == "…" + huella_clave(clave)[-8:]
    assert sesion.get("/api/insignias").json()["propuestas_mcp"] == 1
    assert sesion.get("/api/pantalla/clave").json()["propuestas_pendientes"] == 1
    e = _ok(_llamar(agente, clave, mcp.ESTADO_PROPUESTA, {"propuesta": d["propuesta"]}))
    assert e["estado"] == "pendiente" and e["aprobar_en"] == d["aprobar_en"]
    # Aprobar: se ejecuta con la sesión de quien aprueba, una sola vez
    r = sesion.post(f"/api/mcp/propuestas/{d['propuesta']}", json={"aprobar": True})
    assert r.status_code == 200 and r.json()["estado"] == "hecha", r.text
    notas = db.personas.find_one({"_id": pid})["notas"]
    assert [n["texto"] for n in notas] == [texto]
    r = sesion.post(f"/api/mcp/propuestas/{d['propuesta']}", json={"aprobar": True})
    assert r.status_code == 409 and r.json()["detail"]["estado"] == "hecha"
    assert len(db.personas.find_one({"_id": pid})["notas"]) == 1
    hecha = db.mcp_propuestas.find_one({"_id": d["propuesta"]})
    assert hecha["estado"] == "hecha" and "entrada" not in hecha and "confirmacion" not in hecha
    assert hecha["expira"] - hecha["decidida_en"] == timedelta(days=7)
    assert db.auditoria.find_one({"accion": "aprobar_propuesta_mcp", "uid": 0}) is not None
    assert db.auditoria.find_one({"accion": "proponer_mcp", "uid": 0, "via": "mcp"}) is not None
    assert sesion.get("/api/insignias").json()["propuestas_mcp"] == 0
    reciente = sesion.get("/api/mcp/propuestas").json()["recientes"][0]
    assert reciente["estado"] == "hecha" and reciente["resumen"]
    # El agente lee cómo terminó (esta clave lee personas: con el resultado)
    e = _ok(_llamar(agente, clave, mcp.ESTADO_PROPUESTA, {"propuesta": d["propuesta"]}))
    assert e["estado"] == "hecha" and json.loads(e["resultado"])["guardada"] is True
    # Rechazar: no se escribe nada
    d2 = _ok(_proponer_nota(agente, clave, pid, texto="Otra nota que no va."))
    r = sesion.post(f"/api/mcp/propuestas/{d2['propuesta']}", json={"aprobar": False})
    assert r.status_code == 200 and r.json() == {"estado": "rechazada"}
    assert len(db.personas.find_one({"_id": pid})["notas"]) == 1
    assert _ok(_llamar(agente, clave, mcp.ESTADO_PROPUESTA, {"propuesta": d2["propuesta"]}))["estado"] == "rechazada"
    assert sesion.post(f"/api/mcp/propuestas/{d2['propuesta']}", json={"aprobar": True}).status_code == 409
    # Ids que no son de una propuesta
    assert sesion.post("/api/mcp/propuestas/xyz", json={"aprobar": True}).status_code == 422
    assert sesion.post(f"/api/mcp/propuestas/{'a' * 32}", json={"aprobar": True}).status_code == 404
    assert sesion.post(f"/api/mcp/propuestas/{d2['propuesta']}", json={"aprobar": "si"}).status_code == 422
    assert _sin_sesiones_internas(db)
    agente.close()


def test_la_ficha_que_cambio_entre_la_propuesta_y_la_aprobacion_falla(sesion):
    db = sesion.app.state.db
    pid = persona(db, nombre="EUDOSIA CAMBIADA INVENTADA", direccion="CALLE 10 # 1-1")
    autorizada(db, pid)
    agente = _agente(sesion.app)
    clave = _clave_datos(sesion, "escritura")
    d = _ok(_llamar(agente, clave, "editar_persona", {"persona_id": pid, "modo": "reemplazar",
                                                       "cambios": {"direccion": "CALLE 20 # 2-2"},
                                                       "motivo_propuesta": "Se mudó"}))
    sesion.patch(f"/api/personas/{pid}", json={"direccion": "CALLE 30 # 3-3"})
    r = sesion.post(f"/api/mcp/propuestas/{d['propuesta']}", json={"aprobar": True}).json()
    assert r["estado"] == "fallida" and r["error"]["codigo"] == "cambiada" and "cambió" in r["error"]["mensaje"]
    assert db.personas.find_one({"_id": pid})["direccion"] == "CALLE 30 # 3-3"
    e = _ok(_llamar(agente, clave, mcp.ESTADO_PROPUESTA, {"propuesta": d["propuesta"]}))
    assert e["estado"] == "fallida" and e["error"]["codigo"] == "cambiada"
    agente.close()


def test_una_clave_sin_lectura_no_recibe_datos_de_personas(sesion):
    db = sesion.app.state.db
    _ajustes_mcp(db, roles=["admin", "coordinador"])
    k = coordinador(sesion.app, db)
    pid = persona(db, nombre="HERMINIA SINLECTURA INVENTADA")
    autorizada(db, pid)
    agente = _agente(sesion.app)
    clave = _clave_datos(k, "escritura")
    d = _ok(_proponer_nota(agente, clave, pid))
    assert "HERMINIA" not in json.dumps(d) and d["titulo"] == "Propuesta: agregar_nota"
    assert k.post(f"/api/mcp/propuestas/{d['propuesta']}", json={"aprobar": True}).json()["estado"] == "hecha"
    e = _ok(_llamar(agente, clave, mcp.ESTADO_PROPUESTA, {"propuesta": d["propuesta"]}))
    assert e["estado"] == "hecha" and "resultado" not in e and e["mensaje"] == mcp.SIN_DETALLE
    assert "HERMINIA" not in json.dumps(e)
    agente.close()


def test_idor_las_propuestas_son_de_su_dueno_y_de_su_clave(sesion):
    db = sesion.app.state.db
    _ajustes_mcp(db, roles=["admin", "coordinador"])
    k1, k2 = coordinador(sesion.app, db), coordinador(sesion.app, db)
    pid = persona(db, nombre="AURORA IDOR INVENTADA")
    autorizada(db, pid)
    agente = _agente(sesion.app)
    c1, c2 = _clave_datos(k1, "escritura"), _clave_datos(k2, "escritura")
    d = _ok(_proponer_nota(agente, c1, pid))
    # Otro coordinador no la ve, no la aprueba ni la rechaza, ni la consulta con su clave
    assert k2.get("/api/mcp/propuestas").json() == {"propuestas": [], "recientes": []}
    assert k2.post(f"/api/mcp/propuestas/{d['propuesta']}", json={"aprobar": True}).status_code == 404
    assert k2.post(f"/api/mcp/propuestas/{d['propuesta']}", json={"aprobar": False}).status_code == 404
    assert sesion.post(f"/api/mcp/propuestas/{d['propuesta']}", json={"aprobar": True}).status_code == 404  # ni A
    assert _ok(_llamar(agente, c2, mcp.ESTADO_PROPUESTA, {"propuesta": d["propuesta"]}))["estado"] == "no_existe"
    assert k2.get("/api/insignias").json()["propuestas_mcp"] == 0
    # La misma persona con otra clave (la reemplazó): la vieja quedó anulada y la nueva no la consulta
    c1b = _clave_datos(k1, "escritura")
    assert _ok(_llamar(agente, c1b, mcp.ESTADO_PROPUESTA, {"propuesta": d["propuesta"]}))["estado"] == "no_existe"
    assert db.mcp_propuestas.find_one({"_id": d["propuesta"]})["estado"] == "anulada"
    # Un id mal formado
    e = _falla(_llamar(agente, c1b, mcp.ESTADO_PROPUESTA, {"propuesta": "../../x"}))
    assert e["codigo"] == "invalido"
    assert db.personas.find_one({"_id": pid}).get("notas") in (None, [])
    agente.close()


def test_revocar_o_reemplazar_la_clave_anula_sus_pendientes(sesion):
    db = sesion.app.state.db
    pid = persona(db, nombre="GENOVEVA REVOCA INVENTADA")
    autorizada(db, pid)
    agente = _agente(sesion.app)
    clave = _clave_datos(sesion, "escritura")
    a, b = _ok(_proponer_nota(agente, clave, pid)), _ok(_proponer_nota(agente, clave, pid, texto="Otra"))
    sesion.delete("/api/pantalla/clave?tipo=datos")
    for x in (a, b):
        doc = db.mcp_propuestas.find_one({"_id": x["propuesta"]})
        assert doc["estado"] == "anulada" and "confirmacion" not in doc and doc["error"]["codigo"] == "clave_revocada"
        r = sesion.post(f"/api/mcp/propuestas/{x['propuesta']}", json={"aprobar": True})
        assert r.status_code == 409 and r.json()["detail"]["estado"] == "anulada"
    assert sesion.get("/api/mcp/propuestas").json()["propuestas"] == []
    # Reemplazarla, igual
    clave = _clave_datos(sesion, "escritura")
    c = _ok(_proponer_nota(agente, clave, pid))
    _clave_datos(sesion, "escritura", "lectura")
    assert db.mcp_propuestas.find_one({"_id": c["propuesta"]})["estado"] == "anulada"
    assert not (db.personas.find_one({"_id": pid}).get("notas") or [])


def test_la_clave_que_dejo_de_valer_no_ejecuta_lo_pendiente(sesion):
    """Una clave que deja de valer sin revocarla (otra versión de la cuenta, otro rol en los ajustes): su propuesta no
    se ejecuta al aprobarla."""
    db = sesion.app.state.db
    _ajustes_mcp(db, roles=["admin", "coordinador"])
    k = coordinador(sesion.app, db)
    pid = persona(db, nombre="LIBRADA VENCIDA INVENTADA")
    autorizada(db, pid)
    agente = _agente(sesion.app)
    clave = _clave_datos(k, "escritura")
    d = _ok(_proponer_nota(agente, clave, pid))
    db.claves_mcp.update_one({"_id": huella_clave(clave)}, {"$set": {"huella": "otra"}})
    r = k.post(f"/api/mcp/propuestas/{d['propuesta']}", json={"aprobar": True}).json()
    assert r["estado"] == "anulada" and r["error"]["codigo"] == "clave_revocada"
    # Sin el rol en los ajustes: tampoco (la clave sigue valiendo, el permiso no)
    clave = _clave_datos(k, "escritura")
    d = _ok(_proponer_nota(agente, clave, pid))
    _ajustes_mcp(db, roles=["admin"])
    r = k.post(f"/api/mcp/propuestas/{d['propuesta']}", json={"aprobar": True}).json()
    assert r["estado"] == "fallida" and r["error"]["codigo"] == "permiso"
    assert not (db.personas.find_one({"_id": pid}).get("notas") or [])
    agente.close()


def test_la_supresion_y_el_no_borran_las_propuestas(sesion):
    db = sesion.app.state.db
    p1, p2 = persona(db, nombre="SUPRIMIDA PROPUESTA INVENTADA"), persona(db, nombre="NEGADA PROPUESTA INVENTADA")
    autorizada(db, p1)
    autorizada(db, p2)
    agente = _agente(sesion.app)
    clave = _clave_datos(sesion, "escritura")
    a, b = _ok(_proponer_nota(agente, clave, p1)), _ok(_proponer_nota(agente, clave, p2))
    assert sesion.delete(f"/api/personas/{p1}").status_code == 200
    assert db.mcp_propuestas.find_one({"_id": a["propuesta"]}) is None
    bd.olvidar_en_conversaciones(db, [p2])
    assert db.mcp_propuestas.find_one({"_id": b["propuesta"]}) is None
    assert sesion.get("/api/insignias").json()["propuestas_mcp"] == 0
    # Las entregas quedan (como `lecturas`): a qué clave se le entregó quién, sin datos
    assert db.mcp_entregas.count_documents({"clave_h": huella_clave(clave)}) == 2
    agente.close()


def test_demasiadas_pendientes_por_clave(sesion, monkeypatch):
    db = sesion.app.state.db
    pid = persona(db, nombre="PRUDENCIA TOPE INVENTADA")
    autorizada(db, pid)
    monkeypatch.setattr(mcp, "MAX_PENDIENTES", 2)
    agente = _agente(sesion.app)
    clave = _clave_datos(sesion, "escritura")
    _ok(_proponer_nota(agente, clave, pid))
    _ok(_proponer_nota(agente, clave, pid, texto="Dos"))
    assert _falla(_proponer_nota(agente, clave, pid, texto="Tres"))["codigo"] == "demasiadas_pendientes"
    agente.close()


def test_planillero_y_consultor_no_tienen_propuestas(sesion, como):
    for rol in ("planillero", "consultor"):
        c = como(rol)
        assert c.get("/api/mcp/propuestas").json() == {"propuestas": [], "recientes": []}
        assert c.post(f"/api/mcp/propuestas/{'b' * 32}", json={"aprobar": True}).status_code == 404
        assert c.get("/api/insignias").json()["propuestas_mcp"] == 0
    # Sin sesión: las rutas de las propuestas sí la piden (no son /api/mcp)
    anonimo = TestClient(sesion.app)
    assert anonimo.get("/api/mcp/propuestas").status_code == 401
    anonimo.close()


# ───────────────────────────── Sesiones internas ─────────────────────────────

def test_las_sesiones_internas_no_desalojan_las_del_navegador_ni_salen_en_usuarios(sesion):
    from conftest import CLAVE_USUARIO
    db = sesion.app.state.db
    cfg = sesion.app.state.cfg
    k = coordinador(sesion.app, db)
    otro = TestClient(sesion.app)
    assert otro.post("/api/login", json={"usuario": k.usuario, "clave": CLAVE_USUARIO}).status_code == 200
    assert db.sesiones.count_documents({"uid": k.uid}) == 2  # el tope de defecto
    # Dos llamadas por MCP en curso (sesiones internas abiertas) y otro ingreso: se cierra la más vieja del navegador,
    # nunca una interna, y las internas no cuentan para el tope
    internas = [sesion_interna.abrir(db, cfg, k.uid, ip="203.0.113.9") for _ in range(2)]
    tercero = TestClient(sesion.app)
    assert tercero.post("/api/login", json={"usuario": k.usuario, "clave": CLAVE_USUARIO}).status_code == 200
    assert db.sesiones.count_documents({"uid": k.uid, "via": {"$exists": False}}) == 2
    assert db.sesiones.count_documents({"uid": k.uid, "via": "mcp"}) == 2
    assert k.get("/api/yo").status_code == 401  # la más vieja del navegador
    assert otro.get("/api/yo").status_code == 200 and tercero.get("/api/yo").status_code == 200
    # El detalle de Usuarios lista solo las del navegador
    det = sesion.get(f"/api/usuarios/{k.uid}").json()
    assert len(det["sesiones"]) == 2 and all(s["agente"] != "mcp" for s in det["sesiones"])
    # Con la sesión interna, la API sabe que es por MCP: la auditoría lo guarda
    pid = persona(db, nombre="VICTORIA INTERNA INVENTADA")
    autorizada(db, pid)
    s = internas[0]
    agente = TestClient(sesion.app, cookies={"yj_sesion": s.token})
    agente.headers["X-CSRF-Token"] = s.csrf
    assert agente.post(f"/api/personas/{pid}/notas", json={"texto": "Nota de prueba"}).status_code == 201
    a = db.auditoria.find_one({"entidad": "persona", "entidad_id": pid, "uid": k.uid}, sort=[("ts", -1)])
    assert a["via"] == "mcp"
    # Una del navegador no lleva via
    r = tercero.post("/api/login", json={"usuario": k.usuario, "clave": CLAVE_USUARIO})
    tercero.headers["X-CSRF-Token"] = r.json()["csrf"]
    assert tercero.post(f"/api/personas/{pid}/notas", json={"texto": "Otra nota"}).status_code == 201
    b = db.auditoria.find_one({"entidad": "persona", "entidad_id": pid, "uid": k.uid}, sort=[("_id", -1)])
    assert "via" not in b
    # Cerrar una interna nunca borra una del navegador, aunque se pase su id
    navegador = db.sesiones.find_one({"uid": k.uid, "via": {"$exists": False}})
    sesion_interna.cerrar(db, navegador["_id"])
    assert db.sesiones.find_one({"_id": navegador["_id"]}) is not None
    for s in internas:
        sesion_interna.cerrar(db, s.sid)
    assert _sin_sesiones_internas(db)
    # Cuenta inactiva: no se abre
    db.usuarios.update_one({"_id": k.uid}, {"$set": {"activo": False}})
    with pytest.raises(PermissionError):
        sesion_interna.abrir(db, cfg, k.uid)
    for c in (otro, tercero, agente):
        c.close()


def test_la_sesion_interna_vence_sola_y_se_cierra_aunque_la_herramienta_falle(sesion, monkeypatch):
    db = sesion.app.state.db
    s = sesion_interna.abrir(db, sesion.app.state.cfg, 0, ip=None, segundos=1)
    doc = db.sesiones.find_one({"_id": s.sid})
    assert doc["via"] == "mcp" and doc["agente"] == "mcp" and doc["expira"] - doc["creada"] == timedelta(seconds=1)
    assert s.token not in json.dumps(doc, default=str)
    sesion_interna.cerrar(db, s.sid)
    with pytest.raises(ValueError):
        sesion_interna.abrir(db, sesion.app.state.cfg, 0, via="otra")
    # Una herramienta que revienta: isError, y la sesión interna no queda
    from app.agente.herramientas import personas as hp

    async def revienta(ctx, a):
        raise RuntimeError("falla inventada")

    monkeypatch.setattr(hp.VER, "ejecutar", revienta)
    agente = _agente(sesion.app)
    clave = _clave_datos(sesion, "lectura")
    e = _falla(_llamar(agente, clave, "ver_persona", {"persona_id": 1}))
    assert e["codigo"] == "error" and "falla inventada" not in json.dumps(e)
    assert _sin_sesiones_internas(db)
    agente.close()
