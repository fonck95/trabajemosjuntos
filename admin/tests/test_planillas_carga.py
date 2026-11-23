"""Revisar, cotejar y cargar una planilla física por la API (app/api/planillas.py): correcciones de celdas, filas
descartadas, la vista previa con cada estado (sin escribir, con las lecturas anotadas), la carga real con el importador
(autorizaciones declaradas aunque se lea «Escrito», el folio, la foto borrada al terminar, idempotente), las cargas
parciales, las relecturas y la supresión de una persona que estaba en una foto. Con un proveedor del modelo falso (sin
red). Solo personas inventadas."""
from app import db as bd
from app import planillas as pl
from app.agente import cifrado
from ayudas_planillas import ProveedorFalso, encender, fila, jpeg, lectura_json, leer, subir
from conftest import crear_usuario, insertar_personas


def _base(db):
    """Personas inventadas en la base, una por estado de la vista previa."""
    ids = insertar_personas(db, [
        {"nombre": "MARIA INVENTADA SIEMPRE", "cedula": "90001001", "consentimiento": "si", "telefono": "3109990001"},
        {"nombre": "PEDRO INVENTADO NEGADO", "cedula": "90001002", "consentimiento": "no"},
        {"nombre": "LUCIA INVENTADA PENDIENTE", "cedula": "90001003", "consentimiento": "pendiente"},
        {"nombre": "RAMON INVENTADO IGUAL", "cedula": "90001004", "telefono": "3109990004"},
        {"nombre": "ELVIRA INVENTADA CONFLICTO", "cedula": "90001005"},
        {"nombre": "SUSANA INVENTADA SUPRIMIDA", "cedula": "90001006", "telefono": "3109990006"},
        {"nombre": "OTILIA INVENTADA ELECCION", "cedula": "90001007",
         "votacion": {"eleccion": "2022-congreso", "puesto_texto": "ESCUELA VIEJA", "mesa": 3, "estado": "verificado",
                      "fuente": "panel"}},
    ])
    bd.suprimir(db, ids[5], "admin")
    return ids


FILAS = [
    fila(1, cedula="90002001", cedula_repetida="90002001", nombre="NUEVA INVENTADA UNO", celular="3108880001",
         autorizacion="si", medio="escrito", canales="llamada, whatsapp", mayor_18="si", observaciones="Ojo"),
    fila(2, cedula="90002002", nombre="NUEVO INVENTADO NOAUTORIZA", celular="3108880002", autorizacion="no",
         barrio="LA CONDOR"),
    fila(3, cedula="90001001", nombre="MARIA INVENTADA SIEMPRE", autorizacion="no"),
    fila(4, cedula="90001002", nombre="PEDRO INVENTADO NEGADO", celular="3108880004", autorizacion="si"),
    fila(5, cedula="90001003", nombre="LUCIA INVENTADA PENDIENTE", celular="3108880005", sexo="F"),
    fila(6, cedula="90001004", nombre="RAMON INVENTADO IGUAL", celular="3109990004"),
    fila(7, cedula="90001005", nombre="TOTALMENTE DIFERENTE APELLIDOS"),
    fila(8, cedula="90001006", nombre="SUSANA INVENTADA SUPRIMIDA", celular="3109990006"),
    fila(9, cedula="90001007", nombre="OTILIA INVENTADA ELECCION", puesto="CABECERA MUNICIPAL", mesa="2"),
    fila(10, cedula="90002003", cedula_repetida="90002030", nombre="RUFINO INVENTADO DIGITO"),
    fila(11, celular="3108880011", direccion="SIN NOMBRE"),
]


def _leida(cliente, sesion, monkeypatch, filas=FILAS, **kw) -> str:
    encender(monkeypatch, cliente.app, ProveedorFalso(lectura_json(filas, **kw)))
    d = subir(sesion, jpeg()).json()
    leer(cliente, d["id"])
    assert sesion.get(f"/api/planillas/{d['id']}").json()["estado"] == "leida"
    return d["id"]


def test_lo_que_se_guarda_de_cada_fila(cliente, sesion, monkeypatch):
    ids = _base(cliente.app.state.db)
    pid = _leida(cliente, sesion, monkeypatch)
    v = sesion.get(f"/api/planillas/{pid}").json()
    por_n = {f["n"]: f for f in v["filas"]}
    assert por_n[2]["valores"] == {"nombre": "NUEVO INVENTADO NOAUTORIZA", "cedula": "90002002",
                                   "barrio": "LA CONDOR", "autorizacion": "no"}
    assert por_n[4]["valores"] == {"nombre": "PEDRO INVENTADO NEGADO", "cedula": "90001002"}  # ya en «no»
    assert por_n[4]["estado"] == "no_autoriza"
    assert por_n[8] == {"n": 8, "valores": {}, "firma": None, "dudosos": [], "ilegibles": [], "corregidos": [],
                        "estado": "no_se_carga"}  # suprimida: nada
    assert por_n[1]["valores"]["observaciones"] == "Ojo" and por_n[1]["estado"] == "pendiente"
    doc = cliente.app.state.db.planillas.find_one({"_id": pid})
    claro = cifrado.descifrar_bytes(pl.llave(cliente.app.state.cfg), doc["lectura"], f"planilla|lectura|{pid}|0")
    for secreto in (b"SUSANA", b"3109990006", b"3108880002", b"3108880004"):
        assert secreto not in claro
    assert ids


def test_la_vista_previa_por_la_api(cliente, sesion, monkeypatch):
    db = cliente.app.state.db
    ids = _base(db)
    pid = _leida(cliente, sesion, monkeypatch)
    antes = {c: db[c].count_documents({}) for c in ("personas", "autorizaciones", "conflictos_cedula", "suprimidos")}
    r = sesion.post(f"/api/planillas/{pid}/simular", json={})
    assert r.status_code == 200, r.text
    s = r.json()
    estados = {f["n"]: f["estado"] for f in s["filas"]}
    assert estados == {1: "nueva", 2: "nueva_sin_autorizacion", 3: "revocaria", 4: "no_autorizo", 5: "completaria",
                       6: "igual", 7: "conflicto_cedula", 8: "no_se_carga", 9: "otra_eleccion", 10: "revision",
                       11: "sin_nombre"}
    assert {c: db[c].count_documents({}) for c in antes} == antes  # no escribe nada
    f8 = next(f for f in s["filas"] if f["n"] == 8)
    assert f8 == {"n": 8, "estado": "no_se_carga", "persona_id": None, "llenaria": [], "distintos": [], "motivo": None}
    assert s["conteo"]["nueva"] == 1 and sum(s["conteo"].values()) == 11
    f5 = next(f for f in s["filas"] if f["n"] == 5)
    assert f5["persona_id"] == ids[2] and "telefono" in f5["llenaria"]
    # Las fichas encontradas quedan en las lecturas de quien coteja
    leidas = {x["pid"] for x in db.lecturas.find({"uid": 0})}
    assert {ids[0], ids[1], ids[2], ids[3], ids[6]} <= leidas
    # Solo algunas filas; una descartada sale como tal si se pide
    sesion.patch(f"/api/planillas/{pid}", json={"descartar": [6]})
    s = sesion.post(f"/api/planillas/{pid}/simular", json={"filas": [1, 6]}).json()
    assert [(f["n"], f["estado"]) for f in s["filas"]] == [(1, "nueva"), (6, "descartada")]
    assert 6 not in {f["n"] for f in sesion.post(f"/api/planillas/{pid}/simular", json={}).json()["filas"]}
    r = sesion.post(f"/api/planillas/{pid}/simular", json={"filas": [99]})
    assert r.status_code == 422 and r.json()["detail"]["codigo"] == "fila"


def test_cargar_con_autorizaciones_declaradas_y_borrar_la_foto(cliente, sesion, como, monkeypatch):
    db = cliente.app.state.db
    ids = _base(db)
    pid = _leida(cliente, sesion, monkeypatch, filas=FILAS[:10])
    ana = crear_usuario(db, "planillero", usuario="ana.campo")
    r = sesion.post(f"/api/planillas/{pid}/cargar", json={"capturado_por": 12345})
    assert r.status_code == 422 and r.json()["detail"]["codigo"] == "planillero"
    clave = {"Idempotency-Key": "carga-prueba-planilla-1"}
    r = sesion.post(f"/api/planillas/{pid}/cargar", json={"folio": "Carpeta 3,\nhoja 12", "capturado_por": ana["_id"]},
                    headers=clave)
    assert r.status_code == 200, r.text
    c = r.json()
    assert set(c) == {"importacion_id", "resumen", "filas"} and isinstance(c["importacion_id"], int)
    assert {n: f["estado"] for n, f in c["filas"].items()} == {
        "1": "nueva", "2": "nueva_sin_autorizacion", "3": "revocada", "4": "no_autorizo", "5": "completada",
        "6": "igual", "7": "conflicto_cedula", "8": "no_se_carga", "9": "completada", "10": "revision"}
    assert c["filas"]["8"]["persona_id"] is None and c["filas"]["3"]["persona_id"] == ids[0]
    # Repetir con la misma clave devuelve lo mismo sin cargar otra vez
    r2 = sesion.post(f"/api/planillas/{pid}/cargar", json={"folio": "Carpeta 3,\nhoja 12",
                                                           "capturado_por": ana["_id"]}, headers=clave)
    assert r2.json() == c and r2.headers.get("idempotency-replayed") == "true"
    assert db.importaciones.count_documents({}) == 1
    # Las autorizaciones de la foto, declaradas: el «Escrito» leído no habilita el contacto
    nueva = db.personas.find_one({"cedula": "90002001"})
    assert (nueva["consentimiento"], nueva["consentimiento_medio"], nueva["contacto_habilitado"]) == \
        ("si", "declarado_planilla", False)
    ev = db.autorizaciones.find_one({"persona_id": nueva["_id"]})
    assert ev["evidencia_fila"]["medio_leido"] == "escrito" and ev["evidencia_fila"]["folio"] == "Carpeta 3, hoja 12"
    assert ev["evidencia_fila"]["captura"] == "foto" and ev["evidencia"] == "Foto de planilla física, fila 1"
    doc = db.planillas.find_one({"_id": pid})
    assert ev["evidencia_sha256"] == doc["sha256"] and ev["capturado_por"] == ana["_id"]
    assert nueva["creado_por"]["capturado_por"] == ana["_id"] and nueva["observaciones"] == "Ojo"
    imp_doc = db.importaciones.find_one()
    assert imp_doc["fotos_sha256"] == [doc["sha256"]] and imp_doc["folio"] == "Carpeta 3, hoja 12"
    assert imp_doc["archivo"] == "Foto de planilla física" and imp_doc["resumen"]["autorizaciones_por_confirmar"] == 1
    # Confirmarlas sigue siendo de A o K con el papel, en Importar y exportar (la ruta de siempre)
    r = sesion.post(f"/api/importaciones/{imp_doc['_id']}/confirmar-autorizaciones",
                    json={"evidencia": "Revisé el papel archivado en la carpeta 3, hoja 12"})
    assert r.status_code == 200, r.text
    assert db.personas.find_one({"_id": nueva["_id"]})["contacto_habilitado"] is True
    # La foto y lo leído se borraron: queda lo no personal
    assert doc["estado"] == "cargada" and doc["foto"] is None and doc["lectura"] is None and doc["huellas"] == []
    assert doc["cargadas"]["1"] == {"persona_id": nueva["_id"], "estado": "nueva"}
    assert doc["importacion_id"] == imp_doc["_id"] and doc["importaciones"] == [imp_doc["_id"]]
    v = sesion.get(f"/api/planillas/{pid}").json()
    assert v["estado"] == "cargada" and v["filas"][0] == {"n": 1, "estado": "cargada", "persona_id": nueva["_id"],
                                                          "resultado": "nueva"}
    assert "NUEVA" not in str(v)
    assert db.auditoria.find_one({"accion": "cargar_planilla", "planilla": pid})["detalle"].count("NUEVA") == 0
    # Ya no se corrige, ni se coteja, ni se carga otra vez
    assert sesion.post(f"/api/planillas/{pid}/cargar", json={}).json()["detail"]["codigo"] == "no_leida"
    assert sesion.patch(f"/api/planillas/{pid}", json={"descartar": [1]}).json()["detail"]["codigo"] == "no_leida"


def test_carga_parcial_y_ya_cargada(cliente, sesion, monkeypatch):
    db = cliente.app.state.db
    pid = _leida(cliente, sesion, monkeypatch, filas=[
        fila(1, cedula="90006001", nombre="PRIMERA INVENTADA", autorizacion="si"),
        fila(2, cedula="90006002", nombre="SEGUNDA INVENTADA"),
        fila(3, celular="3107770003")])
    c = sesion.post(f"/api/planillas/{pid}/cargar", json={"filas": [1]}).json()
    assert c["filas"] == {"1": {"persona_id": c["filas"]["1"]["persona_id"], "estado": "nueva", "motivo": None}}
    doc = db.planillas.find_one({"_id": pid})
    assert doc["estado"] == "leida" and doc["foto"] is not None and doc["resumen"]["pendientes"] == 2
    s = sesion.post(f"/api/planillas/{pid}/simular", json={"filas": [1, 2, 3]}).json()
    assert [(f["n"], f["estado"]) for f in s["filas"]] == [(1, "ya_cargada"), (2, "nueva"), (3, "sin_nombre")]
    assert s["filas"][0]["persona_id"] == c["filas"]["1"]["persona_id"]
    lectura = pl.lectura_de(cliente.app.state.cfg, doc)
    assert lectura["filas"][0] == {"n": 1, "cargada": True}  # la fila cargada ya no guarda datos
    # La fila sin nombre sigue pendiente: se corrige y se carga
    c2 = sesion.post(f"/api/planillas/{pid}/cargar", json={}).json()
    assert c2["filas"]["2"]["estado"] == "nueva" and c2["filas"]["3"]["estado"] == "sin_nombre"
    assert db.planillas.find_one({"_id": pid})["estado"] == "leida"
    v = sesion.patch(f"/api/planillas/{pid}",
                     json={"filas": [{"n": 3, "campo": "nombre", "valor": "TERCERA INVENTADA"}]})
    assert v.status_code == 200 and v.json()["filas"][2]["corregidos"] == ["nombre"]
    c3 = sesion.post(f"/api/planillas/{pid}/cargar", json={}).json()
    assert c3["filas"]["3"]["estado"] == "nueva" and set(c3["filas"]) == {"3"}
    doc = db.planillas.find_one({"_id": pid})
    assert doc["estado"] == "cargada" and doc["foto"] is None and len(doc["importaciones"]) == 3
    assert sesion.post(f"/api/planillas/{pid}/cargar", json={"filas": [1]}).json()["detail"]["codigo"] == "no_leida"


def test_correcciones(cliente, sesion, monkeypatch):
    db = cliente.app.state.db
    ids = _base(db)
    pid = _leida(cliente, sesion, monkeypatch, filas=[
        fila(1, cedula="90007001", nombre="CORREGIDA INVENTADA", celular="3107", dudosos=["celular"]),
        fila(2, cedula="90007002", nombre="OTRA INVENTADA", celular="3107770002", observaciones="x"),
        fila(3, cedula="90001006", nombre="SUSANA INVENTADA SUPRIMIDA")])
    r = sesion.patch(f"/api/planillas/{pid}", json={"filas": [
        {"n": 1, "campo": "celular", "valor": " 310 777​0001 "},
        {"n": 2, "campo": "autorizacion", "valor": "No autoriza"}], "descartar": []})
    assert r.status_code == 200, r.text
    f1, f2, f3 = r.json()["filas"]
    assert f1["valores"]["celular"] == "310 777 0001" and f1["dudosos"] == [] and f1["corregidos"] == ["celular"]
    # La corrección la volvió «No autoriza»: se reduce como al leerla
    assert f2["valores"] == {"nombre": "OTRA INVENTADA", "cedula": "90007002", "autorizacion": "no"}
    assert f2["estado"] == "no_autoriza"
    # Una fila de alguien suprimido no se corrige; una columna o fila que no existe, tampoco
    for cuerpo, codigo in (({"filas": [{"n": 3, "campo": "nombre", "valor": "X"}]}, "suprimida"),
                           ({"filas": [{"n": 9, "campo": "nombre", "valor": "X"}]}, "fila"),
                           ({"descartar": [9]}, "fila")):
        r = sesion.patch(f"/api/planillas/{pid}", json=cuerpo)
        assert r.status_code == 422 and r.json()["detail"]["codigo"] == codigo, r.text
    assert sesion.patch(f"/api/planillas/{pid}", json={"filas": [{"n": 1, "campo": "etnia", "valor": "x"}]}) \
        .status_code == 422
    # Una corrección que la vuelve de alguien suprimido la vacía
    r = sesion.patch(f"/api/planillas/{pid}", json={"filas": [{"n": 1, "campo": "cedula", "valor": "90001006"}]})
    assert r.json()["filas"][0]["estado"] == "no_se_carga" and r.json()["filas"][0]["valores"] == {}
    # Descartar y recuperar
    r = sesion.patch(f"/api/planillas/{pid}", json={"descartar": [2]})
    assert r.json()["filas"][1]["estado"] == "descartada" and r.json()["pendientes"] == 0
    r = sesion.patch(f"/api/planillas/{pid}", json={"restaurar": [2]})
    assert r.json()["filas"][1]["estado"] == "no_autoriza"
    aud = db.auditoria.find_one({"accion": "corregir_planilla", "planilla": pid})
    assert aud and "OTRA" not in aud["detalle"] and "3107770001" not in str(aud)
    assert ids


def test_releer_como_mucho_dos_veces_y_desde_una_fila(cliente, sesion, monkeypatch):
    filas = [fila(n, cedula=f"9100{n:04d}", nombre=f"PERSONA INVENTADA {n}") for n in range(1, 6)]
    entero = lectura_json(filas, visibles=8)
    cortado = (entero[:entero.index('"PERSONA INVENTADA 4"') + 3], "max_tokens")
    resto = lectura_json([fila(n, cedula=f"9100{n:04d}", nombre=f"PERSONA INVENTADA {n}") for n in range(4, 9)],
                         visibles=8)
    p = ProveedorFalso(cortado, resto)
    encoladas = encender(monkeypatch, cliente.app, p)
    d = subir(sesion, jpeg()).json()
    leer(cliente, d["id"])
    v = sesion.get(f"/api/planillas/{d['id']}").json()
    assert v["incompleta"] is True and v["ultima_fila"] == 3 and len(v["filas"]) == 3 and v["puede_releer"]
    # Se corrige la fila 2 antes de releer desde la 4: se conserva
    sesion.patch(f"/api/planillas/{d['id']}", json={"filas": [{"n": 2, "campo": "celular", "valor": "3105550002"}]})
    r = sesion.post(f"/api/planillas/{d['id']}/leer", json={"desde_fila": 4})
    assert r.status_code == 202 and r.json() == {"id": d["id"], "estado": "leyendo"}
    assert encoladas[-1] == (d["id"], 4)
    leer(cliente, d["id"], desde_fila=4)
    v = sesion.get(f"/api/planillas/{d['id']}").json()
    assert [f["n"] for f in v["filas"]] == [1, 2, 3, 4, 5, 6, 7, 8] and v["incompleta"] is False
    assert v["filas"][1]["valores"]["celular"] == "3105550002"
    assert "desde la fila 4" in p.llamadas[1]["mensajes"][0]["content"][1]["text"]
    assert v["lecturas"] == 2 and v["puede_releer"] is False
    r = sesion.post(f"/api/planillas/{d['id']}/leer", json={})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "max_lecturas"


def test_releer_desde_una_fila_solo_si_quedo_incompleta(cliente, sesion, monkeypatch):
    pid = _leida(cliente, sesion, monkeypatch, filas=[fila(1, nombre="UNA INVENTADA")])
    r = sesion.post(f"/api/planillas/{pid}/leer", json={"desde_fila": 2})
    assert r.status_code == 422 and r.json()["detail"]["codigo"] == "desde_fila"
    r = sesion.post(f"/api/planillas/{pid}/leer", json={"otra": 1})
    assert r.status_code == 422


def test_la_supresion_vacia_las_filas_y_borra_la_foto(cliente, sesion, monkeypatch):
    db = cliente.app.state.db
    (con_cedula, sin_cedula, otra) = insertar_personas(db, [
        {"nombre": "GUMERCINDA INVENTADA BORRAR", "cedula": "90008001"},
        {"nombre": "TELESFORO INVENTADO BORRAR", "telefono": "3106660002"},
        {"nombre": "FILOMENO INVENTADO QUEDA", "cedula": "90008003"}])
    pid = _leida(cliente, sesion, monkeypatch, filas=[
        fila(1, cedula="90008001", nombre="GUMERCINDA INVENTADA BORRAR", celular="3106660001"),
        fila(2, nombre="TELESFORO INVENTADO BORRAR", celular="3106660002"),
        fila(3, cedula="90008003", nombre="FILOMENO INVENTADO QUEDA")])
    # La fila 1 se encuentra por las huellas de su cédula; la 2 (sin cédula), por la ficha que le tocó al cotejar
    s = sesion.post(f"/api/planillas/{pid}/simular", json={}).json()
    assert {f["n"]: f["persona_id"] for f in s["filas"]} == {1: con_cedula, 2: sin_cedula, 3: otra}
    assert sesion.delete(f"/api/personas/{con_cedula}").status_code == 200
    assert sesion.delete(f"/api/personas/{sin_cedula}").status_code == 200
    doc = db.planillas.find_one({"_id": pid})
    assert doc["foto"] is None and sorted(doc["filas_suprimidas"]) == [1, 2]
    assert doc["filas_pid"]["1"] is None and doc["filas_pid"]["3"] == otra
    assert con_cedula not in doc["personas"] and {h["n"] for h in doc["huellas"]} == {3}
    v = sesion.get(f"/api/planillas/{pid}").json()
    assert [(f["n"], f["estado"]) for f in v["filas"]] == [(1, "no_se_carga"), (2, "no_se_carga"), (3, "pendiente")]
    assert "GUMERCINDA" not in str(v) and "TELESFORO" not in str(v) and "3106660001" not in str(v)
    # La próxima escritura deja lo cifrado sin esas filas
    sesion.patch(f"/api/planillas/{pid}", json={"filas": [{"n": 3, "campo": "celular", "valor": "3106660003"}]})
    doc = db.planillas.find_one({"_id": pid})
    claro = cifrado.descifrar_bytes(pl.llave(cliente.app.state.cfg), doc["lectura"], f"planilla|lectura|{pid}|0")
    assert b"GUMERCINDA" not in claro and b"TELESFORO" not in claro and b"FILOMENO" in claro
    assert doc["filas_suprimidas"] == []
    c = sesion.post(f"/api/planillas/{pid}/cargar", json={}).json()
    assert {n: f["estado"] for n, f in c["filas"].items()} == {"1": "no_se_carga", "2": "no_se_carga",
                                                                 "3": "completada"}
    assert c["filas"]["1"]["persona_id"] is None and db.planillas.find_one({"_id": pid})["estado"] == "cargada"
    assert db.personas.count_documents({"nombre": {"$regex": "BORRAR"}}) == 0  # no se volvieron a crear


def test_k_coteja_y_carga_como_a(cliente, sesion, monkeypatch):
    from conftest import CLAVE_USUARIO
    from fastapi.testclient import TestClient
    db = cliente.app.state.db
    pid = _leida(cliente, sesion, monkeypatch, filas=[fila(1, cedula="90009001", nombre="COORDINADA INVENTADA")])
    r = sesion.post("/api/usuarios", json={"usuario": "coordinadora.prueba", "nombre": "Coordinadora de prueba",
                                           "rol": "coordinador"})
    assert r.status_code in (200, 201), r.text
    uid = r.json()["id"]
    from app.acceso import hashear_clave
    from app import modelo
    vigente = modelo.leer_ajustes(db)["compromiso_version"]
    db.usuarios.update_one({"_id": uid}, {"$set": {"clave": hashear_clave(CLAVE_USUARIO), "debe_cambiar_clave": False,
                                                   "compromiso_version": vigente}})
    k = TestClient(cliente.app)
    r = k.post("/api/login", json={"usuario": "coordinadora.prueba", "clave": CLAVE_USUARIO})
    assert r.status_code == 200, r.text
    k.headers["X-CSRF-Token"] = r.json()["csrf"]
    assert pid in [x["id"] for x in k.get("/api/planillas").json()["planillas"]]
    assert k.get(f"/api/planillas/{pid}").json()["filas"][0]["valores"]["cedula"] == "90009001"
    assert k.post(f"/api/planillas/{pid}/simular", json={}).json()["filas"][0]["estado"] == "nueva"
    c = k.post(f"/api/planillas/{pid}/cargar", json={})
    assert c.status_code == 200 and c.json()["filas"]["1"]["estado"] == "nueva"
    k.close()
