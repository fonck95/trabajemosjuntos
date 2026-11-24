"""Las herramientas del asistente para las planillas físicas por foto (app/agente/herramientas/planillas.py): el
esquema y el lugar en el catálogo, quién las recibe (`agente_planillas.roles` y los permisos de la API), lo que el
modelo recibe de la bandeja, de lo leído (enmascarado, con espera y tope) y del cotejo (sin escribir nada), y la carga
con aprobación: la tarjeta (30 personas + 6 líneas fijas, una línea por persona, lo dudoso marcado, las filas en «no»
aparte), las correcciones (nunca la autorización), lo que cambió entre la tarjeta y la aprobación, los reemplazos, la
reunión y las subclaves de idempotencia. Contra la API de verdad (por ASGI) y con un proveedor falso para leer las
fotos. Solo personas inventadas."""
import json
import re

import pytest
from pydantic import ValidationError

import ayudas_agente as aa
from app.agente import bucle
from app.agente import herramientas
from app.agente.herramientas import calidad as hc
from app.agente.herramientas import planillas as hp
from app.agente.herramientas.base import ErrorHerramienta
from ayudas_g3 import autorizada, coordinador, persona
from ayudas_planillas import fila
from ayudas_planillas_chat import (al_modelo, foto_distinta, foto_leida, roles_planillas, subir_sin_leer,
                                   tarjeta_y_ejecutar)
from test_agente_personas import PALABRAS_ESQUEMA, _objetos, _palabras

H = {h.nombre: h for h in hp.HERRAMIENTAS}
CED = {n: f"9003100{n}" for n in range(1, 8)}
TEL = {n: f"310555000{n}" for n in range(1, 8)}
ENTEROS = (*CED.values(), *TEL.values(), "1990-05-02", "Vive con la abuela inventada")


def _filas() -> list[dict]:
    return [
        fila(1, cedula=CED[1], cedula_repetida=CED[1], tipo_documento="CC", nombre="ANA INVENTADA FOTO",
             celular=TEL[1], sexo="F", fecha_nacimiento="1990-05-02", direccion="CALLE INVENTADA 1", barrio="CENTRO",
             autorizacion="si", medio="escrito", canales="llamada, whatsapp", mayor_18="si", firma="presente",
             observaciones="Vive con la abuela inventada"),
        fila(2, cedula=CED[2], nombre="BETO INVENTADO BASE", celular=TEL[2], direccion="CALLE NUEVA 2"),
        fila(3, cedula=CED[3], nombre="CARLA INVENTADA DUDA", celular=TEL[3], dudosos=["celular"]),
        fila(4, cedula=CED[4], nombre="DARIO INVENTADO NIEGA", celular=TEL[4], autorizacion="no", barrio="LA CONDOR"),
        fila(5, tipo_documento="TI", cedula=CED[5], nombre="ELSA INVENTADA MENOR", celular=TEL[5], edad="15"),
    ]


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


def _ej(cliente, ctx, nombre: str, entrada: dict):
    return aa.correr(cliente, aa.ejecutar, H[nombre], ctx, entrada)


def _error(cliente, fn, *args) -> ErrorHerramienta:
    with pytest.raises(ErrorHerramienta) as e:
        aa.correr(cliente, fn, *args)
    return e.value


def _sin_enteros(x) -> None:
    texto = json.dumps(x, ensure_ascii=False)
    for v in ENTEROS:
        assert v not in texto, v


def _conteos(db) -> dict:
    return {c: db[c].count_documents({}) for c in ("personas", "importaciones", "autorizaciones", "conflictos_cedula",
                                                   "coincidencias")}


# ───────────────────────────── Esquema y catálogo ─────────────────────────────

def test_esquemas_para_la_messages_api_y_reglas_del_catalogo():
    assert [h.nombre for h in hp.HERRAMIENTAS] == ["planillas", "leer_planilla", "cotejar_planilla", "cargar_planilla"]
    for h in hp.HERRAMIENTAS:
        d = h.definicion()
        assert set(d) == {"name", "description", "input_schema", "eager_input_streaming"}, h.nombre
        assert re.fullmatch(r"[a-z_]{3,64}", d["name"]) and d["eager_input_streaming"] is True
        assert 200 < len(d["description"]) < 1500, (h.nombre, len(d["description"]))
        assert re.match(r"^\w+(ando|endo|iendo)\b", h.etiqueta), h.etiqueta
        s = d["input_schema"]
        texto = json.dumps(s, ensure_ascii=False)
        for vedada in ("$ref", "$defs", '"title"', "oneOf", '"const"', '"format"', '"pattern"', "\\n"):
            assert vedada not in texto, (h.nombre, vedada)
        assert s["type"] == "object" and isinstance(s["properties"], dict) and s["properties"], h.nombre
        for obj in _objetos(s):
            assert obj.get("additionalProperties") is False, h.nombre
            assert set(obj.get("required", [])) <= set(obj.get("properties", {})), h.nombre
        for ruta, k in _palabras(s):
            assert k in PALABRAS_ESQUEMA, (h.nombre, ruta, k)
        assert "huellas" not in s["properties"] and "base" not in s["properties"], h.nombre
        assert (h.tipo == "escritura") == (h.confirmar is not None)
        # Nunca por MCP; solo con el rol en `agente_planillas.roles`
        assert h.mcp is None and h.alcance_mcp() is None and h.disponible_ajustes is not None, h.nombre
    assert {h.nombre: h.tipo for h in hp.HERRAMIENTAS} == {
        "planillas": "lectura", "leer_planilla": "lectura", "cotejar_planilla": "lectura",
        "cargar_planilla": "escritura"}
    assert H["cargar_planilla"].plazo == 170 and H["leer_planilla"].plazo <= 90
    assert H["planillas"].permisos == ("plantillas",) and H["leer_planilla"].permisos == ("plantillas",)
    assert set(H["cotejar_planilla"].permisos) == set(H["cargar_planilla"].permisos) == {"plantillas", "importar"}
    # Las celdas que el asistente corrige nunca son la autorización, su medio, los canales ni «mayor de 18»
    campos = H["cargar_planilla"].definicion()["input_schema"]["properties"]["correcciones"]["items"]["properties"]
    assert not {"autorizacion", "medio", "canales", "mayor_18", "observaciones"} & set(campos["campo"]["enum"])
    reemplazables = H["cargar_planilla"].definicion()["input_schema"]["properties"]["reemplazar"]["items"][
        "properties"]["campos"]["items"]["enum"]
    assert "cedula" not in reemplazables and set(reemplazables) == {"sexo", "edad", "direccion", "puesto"}
    # En el catálogo, después de las de calidad y antes de las de análisis
    nombres = [h.nombre for h in herramientas.fijas()]
    i = nombres.index("planillas")
    assert nombres[i:i + 4] == [h.nombre for h in hp.HERRAMIENTAS]
    assert nombres[i - 1] == hc.HERRAMIENTAS[-1].nombre and nombres.index("analizar") > i + 3


def test_entradas_invalidas():
    v = H["cargar_planilla"].validar
    ok = {"id": "a" * 32}
    for malo in ({"id": "x" * 32}, {"id": "a" * 31}, {**ok, "filas": list(range(1, 32))},
                 {**ok, "correcciones": [{"fila": 1, "campo": "autorizacion", "valor": "si"}]},
                 {**ok, "correcciones": [{"fila": 1, "campo": "medio", "valor": "escrito"}]},
                 {**ok, "correcciones": [{"fila": 1, "campo": "celular", "valor": "1"},
                                         {"fila": 1, "campo": "celular", "valor": "2"}]},
                 {**ok, "reemplazar": [{"fila": 1, "campos": ["cedula"]}]},
                 {**ok, "reemplazar": [{"fila": 1, "campos": ["sexo"]}, {"fila": 1, "campos": ["edad"]}]},
                 {**ok, "filas": [True]}, {**ok, "otra": 1}, {**ok, "huellas": {"1": "no-es-huella"}}):
        with pytest.raises(ValidationError):
            v(malo)
    assert v({"id": "A" * 32}).id == "a" * 32  # el id se toma en minúsculas
    assert H["leer_planilla"].validar({"ids": ["b" * 32, "b" * 32]}).ids == ["b" * 32]
    with pytest.raises(ValidationError):
        H["leer_planilla"].validar({"ids": ["c" * 32] * 0})
    with pytest.raises(ValidationError):
        H["leer_planilla"].validar({"ids": [f"{i:032x}" for i in range(5)]})


def test_quien_recibe_cada_herramienta(sesion, como):
    app, db = sesion.app, sesion.app.state.db
    k = coordinador(app, db)
    quienes = {"admin": aa.quien_de(app, 0), "coordinador": aa.quien_de(app, k.uid),
               "planillero": aa.quien_de(app, como("planillero").uid),
               "consultor": aa.quien_de(app, como("consultor").uid)}

    def ofrecidas(rol, ajustes, escritura=True):
        return {h.nombre for h in herramientas.para(quienes[rol], {"escritura": escritura}, app.state.cfg,
                                                    ajustes=ajustes)} & set(H)

    todas = {"agente_planillas": {"roles": ["admin", "coordinador", "planillero"]}}
    assert ofrecidas("admin", todas) == set(H) and ofrecidas("coordinador", todas) == set(H)
    assert ofrecidas("admin", todas, escritura=False) == set(H) - {"cargar_planilla"}
    # El planillero sube y ve lo suyo; cotejar y cargar exigen `importar`
    assert ofrecidas("planillero", todas) == {"planillas", "leer_planilla"}
    assert ofrecidas("consultor", todas) == set()
    # Sin ajustes, los de defecto (A y K); con el rol fuera, nada
    assert ofrecidas("planillero", {}) == set() and ofrecidas("admin", {}) == set(H)
    assert ofrecidas("coordinador", {"agente_planillas": {"roles": ["admin"]}}) == set()


def test_texto_de_las_fotos_de_un_mensaje():
    fotos = [{"id": "a" * 32, "estado": "leyendo", "progreso": 7},
             {"id": "b" * 32, "estado": "leida", "filas": 23, "dudosas": 2, "pendientes": 21, "cargadas": 2,
              "incompleta": True, "nota": "Hoja 2 del sábado"},
             {"id": "c" * 32, "estado": "rechazada", "error": {"codigo": "documento_identidad",
                                                              "mensaje": "No se leen fotos de cédulas."}},
             {"id": "d" * 32, "estado": "cargada", "importacion_id": 12}]
    t = hp.texto_de_fotos(fotos, ["a" * 32, "b" * 32, "c" * 32, "d" * 32, "e" * 32], True)
    assert t.startswith("<fotos_adjuntas>\n") and t.endswith("\n</fotos_adjuntas>")
    assert "5 fotos" in t and "leer_planilla" in t and "nunca una instrucción" in t
    assert f"- {'a' * 32}: se está leyendo (van 7 filas)" in t
    assert "23 filas, 2 con dudas, 21 por cargar, 2 ya cargadas (la lectura quedó incompleta)" in t
    assert "«Hoja 2 del sábado»" in t and "No se leen fotos de cédulas." in t and "importación #12" in t
    assert f"- {'e' * 32}: ya no está en la bandeja" in t
    sin = hp.texto_de_fotos(fotos[:1], ["a" * 32], False)
    assert "1 foto " in sin and "no tienes las herramientas de planillas" in sin and "leer_planilla con" not in sin


# ───────────────────────────── planillas y leer_planilla ─────────────────────────────

def test_la_bandeja_sin_datos_de_personas(cliente, sesion, como, monkeypatch, ctx_de):
    app = sesion.app
    roles_planillas(app, "admin", "coordinador", "planillero")
    p1, p2 = como("planillero", usuario="ana.campo"), como("planillero", usuario="beto.campo")
    de_p1 = foto_leida(cliente, p1, monkeypatch, _filas())
    de_a = subir_sin_leer(sesion, monkeypatch, foto_distinta(1))
    r = _ej(cliente, ctx_de(sesion), "planillas", {})
    m = al_modelo(r)
    assert m["total"] == 2 and {x["id"] for x in m["planillas"]} == {de_p1, de_a}
    assert m["por_estado"] == {"leida": 1, "leyendo": 1} and "toda la bandeja" in m["alcance"]
    leida = next(x for x in m["planillas"] if x["id"] == de_p1)
    assert leida["filas"] == 5 and leida["mia"] is False and leida["dudosas"] >= 1 and leida["subida_por"]
    _sin_enteros(m)
    assert "ANA INVENTADA" not in json.dumps(m, ensure_ascii=False)
    assert [x["id"] for x in al_modelo(_ej(cliente, ctx_de(sesion), "planillas", {"solo_mias": True}))[
        "planillas"]] == [de_a]
    assert al_modelo(_ej(cliente, ctx_de(sesion), "planillas", {"estado": "leida"}))["total"] == 1
    # El planillero: solo lo suyo
    assert [x["id"] for x in al_modelo(_ej(cliente, ctx_de(p1, uid=p1.uid), "planillas", {}))["planillas"]] == [de_p1]
    assert al_modelo(_ej(cliente, ctx_de(p2, uid=p2.uid), "planillas", {}))["total"] == 0


def test_leer_enmascara_marca_la_conversacion_y_no_abre_lo_ajeno(cliente, sesion, como, monkeypatch, ctx_de):
    app, db = sesion.app, sesion.app.state.db
    roles_planillas(app, "admin", "coordinador", "planillero")
    p1, p2 = como("planillero", usuario="ana.campo"), como("planillero", usuario="beto.campo")
    pid = foto_leida(cliente, p1, monkeypatch, _filas(), encabezado={"planillero": "ana.campo", "fecha": "02/11/2026",
                                                                    "lugar": "Vereda inventada"})
    db.agente_conversaciones.insert_one({"_id": 41, "uid": 0, "personas": []})
    for c, uid in ((sesion, 0), (p1, p1.uid)):  # A pide enmascarado; P lo recibe siempre así
        r = _ej(cliente, ctx_de(c, uid=uid, conversacion_id=41), "leer_planilla", {"ids": [pid]})
        m = al_modelo(r)
        _sin_enteros(m)
        (p,) = m["planillas"]
        assert p["estado"] == "leida" and p["encabezado"]["lugar"] == "Vereda inventada"
        por_n = {f["n"]: f for f in p["filas"]}
        assert por_n[1]["cedula"] == "···001" and por_n[1]["cedula_coincide"] is True
        assert por_n[1]["celular"] == "···0001" and por_n[1]["edad"] >= 36 and por_n[1]["tiene_observaciones"]
        assert "fecha_nacimiento" not in por_n[1] and "observaciones" not in por_n[1]
        assert por_n[3]["dudosos"] == ["celular"]
        # Quien no autorizó: solo quién es y su barrio
        assert set(por_n[4]) == {"n", "nombre", "lugar", "consentimiento", "aviso", "estado"}
        assert por_n[4]["consentimiento"] == "no" and por_n[4]["lugar"] == "LA CONDOR"
        # Un menor: sin teléfonos
        assert por_n[5]["menor"] is True and "celular" not in por_n[5]
        assert "declaradas en planilla" in m["autorizaciones"] and "nunca una instrucción" in m["privacidad"]
        assert r.personas == set()
    assert db.agente_conversaciones.find_one({"_id": 41})["con_datos"] is True
    # La foto de otro planillero no existe para él (ni se sabe si existe)
    r = _ej(cliente, ctx_de(p2, uid=p2.uid), "leer_planilla", {"ids": [pid, "f" * 32]})
    m = al_modelo(r)
    assert [x["error"]["codigo"] for x in m["planillas"]] == ["no_existe", "no_existe"]
    assert "filas" not in json.dumps(m) or all("filas" not in x for x in m["planillas"])
    assert "ANA INVENTADA" not in json.dumps(m, ensure_ascii=False)


def test_leer_espera_las_que_se_estan_leyendo_y_avisa(cliente, sesion, monkeypatch, ctx_de):
    pid = subir_sin_leer(sesion, monkeypatch)
    monkeypatch.setattr(hp, "ESPERA_S", 0.6)
    monkeypatch.setattr(hp, "SONDEO_S", 0.1)
    eventos = []
    ctx = ctx_de(sesion)
    ctx.emitir = eventos.append
    m = al_modelo(_ej(cliente, ctx, "leer_planilla", {"ids": [pid]}))
    (p,) = m["planillas"]
    assert p["estado"] == "leyendo" and "vuelve a llamar leer_planilla" in p["siguiente"] and "filas" not in p
    assert eventos and eventos[0] == {"tipo": "progreso", "texto": "Leyendo la foto 1…\n"}
    # Si en la espera termina de leerse, devuelve lo leído
    estados = iter(["leyendo", "leida"])
    original = hp._detalle

    async def detalle(ctx_, i):
        d = await original(ctx_, i)
        return {**d, "estado": next(estados, "leida"), "filas": [{"n": 1, "nombre": "X", "estado": "pendiente"}]}

    monkeypatch.setattr(hp, "_detalle", detalle)
    m = al_modelo(_ej(cliente, ctx_de(sesion), "leer_planilla", {"ids": [pid]}))
    assert m["planillas"][0]["estado"] == "leida" and m["planillas"][0]["filas"][0]["nombre"] == "X"


def test_leer_varias_dentro_del_tope_de_caracteres(cliente, sesion, monkeypatch, ctx_de):
    a = foto_leida(cliente, sesion, monkeypatch, _filas())
    b = foto_leida(cliente, sesion, monkeypatch, _filas()[:2], datos=foto_distinta(2))
    m = al_modelo(_ej(cliente, ctx_de(sesion), "leer_planilla", {"ids": [a, b]}))
    assert [len(p["filas"]) for p in m["planillas"]] == [5, 2]
    # Con un tope en el que cabe la primera entera pero no las filas de la segunda
    monkeypatch.setattr(hp, "PRESUPUESTO", len(json.dumps(m["planillas"][0], ensure_ascii=False)) + 300)
    m = al_modelo(_ej(cliente, ctx_de(sesion), "leer_planilla", {"ids": [a, b]}))
    primera, segunda = m["planillas"]
    assert "filas" in primera and segunda["filas_omitidas"] == 2 and "solo con este id" in segunda["nota"]


# ───────────────────────────── cotejar_planilla ─────────────────────────────

def test_cotejar_no_escribe_y_minimiza(cliente, sesion, monkeypatch, ctx_de):
    db = sesion.app.state.db
    beto = persona(db, nombre="BETO INVENTADO BASE", cedula=CED[2], direccion="CALLE VIEJA 9", telefono="3109990002")
    dario = persona(db, nombre="DARIO INVENTADO NIEGA", cedula=CED[4], telefono="3109990004")
    autorizada(db, dario)
    pid = foto_leida(cliente, sesion, monkeypatch, _filas())
    antes = _conteos(db)
    r = _ej(cliente, ctx_de(sesion), "cotejar_planilla", {"id": pid})
    assert _conteos(db) == antes
    m = al_modelo(r)
    por_n = {f["n"]: f for f in m["filas"]}
    assert por_n[1]["estado"] == "nueva" and "persona" not in por_n[1] and por_n[1]["llenaria"]
    assert por_n[2]["estado"] == "completaria" and por_n[2]["persona"]["id"] == beto
    assert por_n[2]["persona"]["cedula_ult3"] == "···002" and por_n[2]["persona"]["telefono_mascara"] == "···0002"
    distinto = {d["campo"]: d for d in por_n[2]["distintos"]}["direccion"]
    assert distinto["base"] == "CALLE VIEJA 9" and distinto["planilla"].startswith("CALLE NUEVA 2")
    # La fila que retira una autorización: sin ficha, sin id, sin lo que cambiaría
    assert por_n[4] == {"n": 4, "estado": "revocaria"}
    assert r.personas == {beto} and "revocaria" in m["estados"] and "otra tarjeta" in m["siguiente"]
    texto = json.dumps(m, ensure_ascii=False)
    for v in (*ENTEROS, "3109990002", "3109990004", f'"id": {dario}'):
        assert v not in texto, v
    # Lee las fichas como lecturas de quien coteja (la API las anota)
    assert db.lecturas.count_documents({"uid": 0, "pid": beto}) == 1
    # Con un planillero inexistente, el error de la API
    e = _error(cliente, aa.ejecutar, H["cotejar_planilla"], ctx_de(sesion), {"id": pid, "capturado_por": 999})
    assert e.codigo == "planillero" and e.estado == 422


# ───────────────────────────── cargar_planilla ─────────────────────────────

def test_tarjeta_y_carga_con_el_importador(cliente, sesion, monkeypatch, ctx_de):
    db = sesion.app.state.db
    beto = persona(db, nombre="BETO INVENTADO BASE", cedula=CED[2])
    pid = foto_leida(cliente, sesion, monkeypatch, _filas())
    ctx = ctx_de(sesion)
    conf, tarjeta, guardada, res = tarjeta_y_ejecutar(cliente, H["cargar_planilla"], ctx,
                                                      {"id": pid, "folio": "Carpeta 3, folio 12"})
    # Sin filas: las pendientes que no están en «no» (la 4 va aparte), con la del menor y la dudosa
    assert guardada.filas == [1, 2, 3, 5] and set(guardada.huellas) == {"1", "2", "3", "5", "_"}
    assert conf.personas == {beto}
    etiquetas = [k for k, _ in tarjeta["detalle"]]
    assert etiquetas[:5] == ["Planilla", "Evidencia", "Folio del papel", "Capturado por", "Resumen"]
    assert etiquetas[5:] == ["Fila 1 · Nueva", f"Fila 2 · Completa la ficha #{beto}", "Fila 3 · Nueva",
                             "Fila 5 · Nueva"]
    lineas = dict(tarjeta["detalle"])
    assert "Carpeta 3, folio 12" == lineas["Folio del papel"] and "SHA-256" in lineas["Evidencia"]
    uno = lineas["Fila 1 · Nueva"]
    # Una línea por persona, con los valores enteros (para quien aprueba) en un orden fijo
    assert uno.startswith(f"ANA INVENTADA FOTO · CC {CED[1]} · Cel. {TEL[1]} · Sexo F · Nac. 1990-05-02")
    assert "Autoriza: sí, declarada en planilla" in uno and "Observaciones: Vive con la abuela inventada" in uno
    assert "Firma presente" in uno and "\n" not in uno
    assert "⚠ dudoso: celular" in lineas["Fila 3 · Nueva"]
    assert "declaradas en planilla" in tarjeta["aviso"] and len(tarjeta["detalle"]) <= bucle.TARJETA_FILAS
    # La carga: importación real (fuente planilla, la foto como evidencia), autorizaciones declaradas
    m = al_modelo(res)
    assert isinstance(m["importacion_id"], int) and m["planilla"]["estado"] == "leida"
    estados = {f["n"]: f["estado"] for f in m["filas"]}
    assert estados == {1: "nueva", 2: "completada", 3: "nueva", 5: "nueva"}
    nueva = db.personas.find_one({"cedula": CED[1]})
    assert nueva and {f["n"]: f.get("persona_id") for f in m["filas"]}[1] == nueva["_id"]
    assert res.personas == {f["persona_id"] for f in m["filas"]} and beto in res.personas
    imp = db.importaciones.find_one({"_id": m["importacion_id"]})
    assert imp["archivo"] == "Foto de planilla física" and imp["fotos_sha256"] and imp["folio"] == "Carpeta 3, folio 12"
    ev = db.autorizaciones.find_one({"persona_id": nueva["_id"]})
    assert ev and ev["medio"] == "declarado_planilla"
    assert not db.personas.find_one({"_id": nueva["_id"]}).get("contacto_habilitado")
    _sin_enteros(m)
    assert "declaradas en planilla" in m["autorizaciones"]
    # La subclave de la carga, y repetir la misma aprobación no carga otra vez
    assert db.idempotencia.find_one({"_id": "0:agente.1.toolu_prueba.imp"})["estado"] == "hecho"
    n_imp = db.importaciones.count_documents({})
    otra = aa.correr(cliente, H["cargar_planilla"].ejecutar, ctx, guardada)
    assert al_modelo(otra)["importacion_id"] == m["importacion_id"] and db.importaciones.count_documents({}) == n_imp


def test_las_filas_en_no_van_en_una_tarjeta_aparte(cliente, sesion, monkeypatch, ctx_de):
    db = sesion.app.state.db
    dario = persona(db, nombre="DARIO INVENTADO NIEGA", cedula=CED[4], telefono="3109990004")
    autorizada(db, dario)
    pid = foto_leida(cliente, sesion, monkeypatch, _filas())
    h = H["cargar_planilla"]
    e = _error(cliente, aa.confirmar, h, ctx_de(sesion), {"id": pid, "filas": [1, 4]})
    assert e.codigo == "separar" and e.detalle == {"filas": [4]} and "otra tarjeta" in e.mensaje
    # Primero las demás; después, sin filas, solo quedan las de «no»
    tarjeta_y_ejecutar(cliente, h, ctx_de(sesion), {"id": pid})
    e = _error(cliente, aa.confirmar, h, ctx_de(sesion), {"id": pid, "filas": [4], "reunion_id": 1})
    assert e.codigo in ("invalido", "no_existe")
    conf, tarjeta, guardada, res = tarjeta_y_ejecutar(cliente, h, ctx_de(sesion, tool_use_id="toolu_no"), {"id": pid})
    assert guardada.filas == [4] and conf.personas == {dario}
    assert tarjeta["titulo"] == "Cargar 1 fila(s) que dicen «No autoriza»"
    assert "esta conversación se borrará" in tarjeta["aviso"] and "1 persona(s) retiran" in tarjeta["aviso"]
    linea = dict(tarjeta["detalle"])[f"Fila 4 · Retira la autorización de la ficha #{dario}"]
    assert linea.startswith("DARIO INVENTADO NIEGA") and "Autoriza: NO" in linea and TEL[4] not in linea
    m = al_modelo(res)
    assert m["filas"] == [{"n": 4, "estado": "revocada"}] and res.personas == set()
    assert db.personas.find_one({"_id": dario})["consentimiento"] == "no"
    assert m["planilla"]["estado"] == "cargada"


def test_tope_de_30_personas_por_tarjeta(cliente, sesion, monkeypatch, ctx_de):
    db = sesion.app.state.db
    rid = sesion.post("/api/reuniones", json={"titulo": "Reunión inventada", "fecha": "2026-11-20"}).json()["id"]
    filas = [fila(n, cedula=f"9004{n:04d}", nombre=f"PERSONA INVENTADA NUMERO {n}", celular=f"31066{n:05d}")
             for n in range(1, 36)]
    pid = foto_leida(cliente, sesion, monkeypatch, filas)
    h = H["cargar_planilla"]
    e = _error(cliente, aa.confirmar, h, ctx_de(sesion), {"id": pid})
    assert e.codigo == "demasiadas" and e.detalle == {"filas": list(range(1, 31))} and "[31…35]" in e.mensaje
    conf, tarjeta, guardada, res = tarjeta_y_ejecutar(cliente, h, ctx_de(sesion), {
        "id": pid, "filas": list(range(1, 31)), "reunion_id": rid})
    fijas = [k for k, _ in tarjeta["detalle"] if not k.startswith("Fila ")]
    assert len(fijas) == hp.TARJETA_FIJAS and "Reunión" in fijas
    assert len(tarjeta["detalle"]) == 36 <= bucle.TARJETA_FILAS
    m = al_modelo(res)
    assert m["asistentes"]["registrados"] == 30 and m["asistentes"]["omitidos"] == []
    pids = sorted(f["persona_id"] for f in m["filas"])
    assert db.personas.count_documents({"_id": {"$in": pids}, "asistencias.reunion_id": rid}) == 30
    assert db.idempotencia.find_one({"_id": f"0:agente.1.toolu_prueba.as{pids[0]}"})["estado"] == "hecho"
    # Las que faltan, en la tarjeta siguiente
    _, tarjeta, guardada, _ = tarjeta_y_ejecutar(cliente, h, ctx_de(sesion, tool_use_id="toolu_2"), {"id": pid})
    assert guardada.filas == list(range(31, 36))
    assert db.planillas.find_one({"_id": pid})["estado"] == "cargada"


def test_correcciones_aprobadas_y_lo_que_no_se_corrige(cliente, sesion, monkeypatch, ctx_de):
    db = sesion.app.state.db
    pid = foto_leida(cliente, sesion, monkeypatch, _filas())
    h = H["cargar_planilla"]
    e = _error(cliente, aa.confirmar, h, ctx_de(sesion), {
        "id": pid, "filas": [4], "correcciones": [{"fila": 4, "campo": "celular", "valor": "3001112233"}]})
    assert e.codigo == "fila" and "solo se guardan nombre, cédula y barrio" in e.mensaje
    e = _error(cliente, aa.confirmar, h, ctx_de(sesion), {
        "id": pid, "filas": [1], "correcciones": [{"fila": 3, "campo": "celular", "valor": "3105550033"}]})
    assert e.codigo == "fila" and e.detalle == {"filas": [3]}
    conf, tarjeta, guardada, res = tarjeta_y_ejecutar(cliente, h, ctx_de(sesion), {
        "id": pid, "filas": [3], "correcciones": [{"fila": 3, "campo": "celular", "valor": "3105550033"}]})
    linea = dict(tarjeta["detalle"])["Fila 3 · Nueva"]
    assert "Cel. 3105550033" in linea and "⚠ dudoso" not in linea
    assert f"✎ corregido por el asistente: celular «{TEL[3]}» → «3105550033»" in linea
    assert al_modelo(res)["correcciones"] == 1
    carla = db.personas.find_one({"cedula": CED[3]})
    assert "3105550033" in json.dumps(carla.get("telefonos"), default=str)


def test_lo_que_cambia_entre_la_tarjeta_y_la_aprobacion_no_se_carga(cliente, sesion, monkeypatch, ctx_de):
    db = sesion.app.state.db
    persona(db, nombre="BETO INVENTADO BASE", cedula=CED[2])
    pid = foto_leida(cliente, sesion, monkeypatch, _filas())
    h = H["cargar_planilla"]
    # Alguien corrige la planilla en Importar y exportar después de la tarjeta
    a = h.validar({"id": pid, "filas": [1, 2]})
    aa.correr(cliente, h.confirmar, ctx_de(sesion), a)
    guardada = h.validar(bucle._entrada_pendiente(h, a, {}))
    r = sesion.patch(f"/api/planillas/{pid}", json={"filas": [{"n": 1, "campo": "celular", "valor": "3001234567"}]})
    assert r.status_code == 200, r.text
    antes = _conteos(db)
    e = _error(cliente, h.ejecutar, ctx_de(sesion), guardada)
    assert e.codigo == "cambiada" and e.detalle == {"filas": [1]} and _conteos(db) == antes
    # Una corrección que cambia a quién corresponde la fila: se escribe la corrección, no se carga
    a = h.validar({"id": pid, "filas": [3], "correcciones": [{"fila": 3, "campo": "cedula", "valor": CED[2]}]})
    conf = aa.correr(cliente, h.confirmar, ctx_de(sesion), a)
    assert dict(conf.detalle)["Fila 3 · Nueva"]
    guardada = h.validar(bucle._entrada_pendiente(h, a, {}))
    e = _error(cliente, h.ejecutar, ctx_de(sesion), guardada)
    assert e.codigo == "cambiada" and "Las correcciones aprobadas ya quedaron" in e.mensaje
    assert _conteos(db) == antes
    fila3 = next(f for f in sesion.get(f"/api/planillas/{pid}").json()["filas"] if f["n"] == 3)
    assert fila3["valores"]["cedula"] == CED[2] and "cedula" in fila3["corregidos"]


def test_reemplazar_solo_en_fichas_que_la_fila_completa(cliente, sesion, monkeypatch, ctx_de):
    db = sesion.app.state.db
    beto = persona(db, nombre="BETO INVENTADO BASE", cedula=CED[2], direccion="CALLE VIEJA 9", sexo="M")
    pid = foto_leida(cliente, sesion, monkeypatch, _filas())
    h = H["cargar_planilla"]
    e = _error(cliente, aa.confirmar, h, ctx_de(sesion), {
        "id": pid, "filas": [1], "reemplazar": [{"fila": 1, "campos": ["direccion"]}]})
    assert e.codigo == "invalido" and "completan una ficha" in e.mensaje
    e = _error(cliente, aa.confirmar, h, ctx_de(sesion), {
        "id": pid, "filas": [2], "reemplazar": [{"fila": 2, "campos": ["sexo"]}]})
    assert e.codigo == "invalido" and "no trae sexo" in e.mensaje
    conf, tarjeta, guardada, res = tarjeta_y_ejecutar(cliente, h, ctx_de(sesion), {
        "id": pid, "filas": [2], "reemplazar": [{"fila": 2, "campos": ["direccion"]}]})
    linea = dict(tarjeta["detalle"])[f"Fila 2 · Completa la ficha #{beto}"]
    assert f"Reemplaza en la ficha #{beto}: dirección «CALLE NUEVA 2»" in linea
    m = al_modelo(res)
    assert m["reemplazos"][0]["n"] == 2 and m["reemplazos"][0]["hecho"] is True
    assert db.personas.find_one({"_id": beto})["direccion"] == "CALLE NUEVA 2"


def test_la_carga_es_de_quien_puede_importar(cliente, sesion, como, monkeypatch, ctx_de):
    roles_planillas(sesion.app, "admin", "coordinador", "planillero")
    p = como("planillero")
    pid = foto_leida(cliente, p, monkeypatch, _filas())
    # La API decide aunque la herramienta se le ofreciera: el planillero no coteja ni carga
    for nombre, entrada in (("cotejar_planilla", {"id": pid}), ("cargar_planilla", {"id": pid})):
        fn = aa.ejecutar if nombre == "cotejar_planilla" else aa.confirmar
        e = _error(cliente, fn, H[nombre], ctx_de(p, uid=p.uid), entrada)
        assert e.codigo == "permiso" and e.estado == 403
    # El administrador sí, también lo que subió el planillero (con su nombre como «capturado por»)
    _, tarjeta, _, res = tarjeta_y_ejecutar(cliente, H["cargar_planilla"], ctx_de(sesion), {"id": pid, "filas": [1]})
    assert "el planillero que subió la foto" in dict(tarjeta["detalle"])["Capturado por"]
    imp = sesion.app.state.db.importaciones.find_one({"_id": al_modelo(res)["importacion_id"]})
    assert imp["capturado_por"] == p.uid
