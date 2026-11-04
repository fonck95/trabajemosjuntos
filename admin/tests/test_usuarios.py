"""Usuarios (3.2 a 3.5, 8.2): alta con clave temporal, nombres reservados, primer ingreso y compromiso, cambio de
clave, desactivar, cambio de rol, falla cerrada, choque con el administrador y auditoría. Solo datos inventados."""
import json
import logging
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import acceso, modelo
from app import seguridad as seg
from conftest import CLAVE_USUARIO, crear_usuario


def _alta(sesion, **campos):
    datos = {"usuario": "ana.campo", "nombre": "Ana Campo Inventada", "rol": "planillero", **campos}
    r = sesion.post("/api/usuarios", json=datos)
    assert r.status_code == 201, r.text
    return r.json()


def _entrar(app, usuario, clave, **headers):
    c = TestClient(app)
    r = c.post("/api/login", json={"usuario": usuario, "clave": clave}, headers=headers)
    if r.status_code == 200:
        c.headers["X-CSRF-Token"] = r.json()["csrf"]
    return c, r


def test_clave_temporal_no_queda_en_la_auditoria_ni_en_los_get_y_vence(sesion):
    db = sesion.app.state.db
    r = _alta(sesion, telefono="300 000 0001")
    temporal = r["clave_temporal"]
    assert len(temporal) == 12 and r["usuario"] == "ana.campo"
    falta = datetime.fromisoformat(r["vence"]) - datetime.now(timezone.utc)
    assert timedelta(hours=71, minutes=58) < falta <= timedelta(hours=72)
    textos = [json.dumps(list(db.auditoria.find({}, {"_id": 0})), default=str)]
    for ruta in ("/api/usuarios", f"/api/usuarios/{r['id']}", "/api/usuarios/indicadores", "/api/auditoria",
                 f"/api/usuarios/{r['id']}/indicadores", "/api/catalogos"):
        x = sesion.get(ruta)
        assert x.status_code == 200, ruta
        textos.append(x.text)
    texto = "".join(textos)
    assert temporal not in texto and "scrypt$" not in texto
    fila = sesion.get(f"/api/usuarios/{r['id']}").json()
    assert "clave" not in fila and fila["debe_cambiar_clave"] is True and fila["clave_vencida"] is False
    u = db.usuarios.find_one({"_id": r["id"]})
    assert u["clave"].startswith("scrypt$") and acceso.verificar_clave(u["clave"], temporal)
    assert db.auditoria.find_one({"accion": "crear_usuario", "entidad": "usuario", "entidad_id": r["id"], "uid": 0})
    # Restablecer da otra temporal, que tampoco queda guardada
    nueva = sesion.post(f"/api/usuarios/{r['id']}/clave").json()
    assert nueva["clave_temporal"] != temporal
    assert nueva["clave_temporal"] not in json.dumps(list(db.auditoria.find({}, {"_id": 0})), default=str)
    assert _entrar(sesion.app, "ana.campo", temporal)[1].status_code == 401
    # A las 72 h vence: el ingreso da el mismo 401 genérico y A la ve vencida
    db.usuarios.update_one({"_id": r["id"]}, {"$set": {
        "clave_temporal_vence": (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(microsecond=0).isoformat()}})
    c, rr = _entrar(sesion.app, "ana.campo", nueva["clave_temporal"])
    assert rr.status_code == 401 and rr.json() == {"detail": "Usuario o clave incorrectos"}
    fila = sesion.get(f"/api/usuarios/{r['id']}").json()
    assert fila["clave_vencida"] is True and "clave_vencida" in fila["alertas"]


@pytest.mark.parametrize("nombre", ["admin", "ADMIN", "Admin", "sistema", "consola", "desconocido", "migracion"])
def test_nombres_reservados_dan_409(sesion, nombre):
    r = sesion.post("/api/usuarios", json={"usuario": nombre, "nombre": "Persona Inventada", "rol": "consultor"})
    assert r.status_code == 409, r.text
    assert sesion.app.state.db.usuarios.count_documents({}) == 0


def test_choque_con_el_administrador_sin_distinguir_mayusculas(cfg):
    from app.main import crear_app
    import pymongo
    from conftest import MONGO, URI
    if not MONGO:
        pytest.skip("No hay MongoDB para las pruebas de la API")
    app = crear_app(replace(cfg, usuario="Jefa.Campana"))
    try:
        with TestClient(app) as c:
            r = c.post("/api/login", json={"usuario": "Jefa.Campana", "clave": cfg.clave})
            assert r.status_code == 200
            c.headers["X-CSRF-Token"] = r.json()["csrf"]
            for nombre in ("jefa.campana", "JEFA.CAMPANA", " Jefa.Campana "):
                x = c.post("/api/usuarios", json={"usuario": nombre, "nombre": "Persona Inventada", "rol": "planillero"})
                assert x.status_code == 409, nombre
            assert c.post("/api/usuarios", json={"usuario": "jefa.campo", "nombre": "Persona Inventada",
                                                 "rol": "planillero"}).status_code == 201
    finally:
        with pymongo.MongoClient(URI) as m:
            m.drop_database(cfg.mongodb_db)


def test_usuario_repetido_o_mal_escrito(sesion):
    _alta(sesion)
    for nombre in ("ana.campo", "Ana.Campo", " ANA.CAMPO"):
        assert sesion.post("/api/usuarios", json={"usuario": nombre, "nombre": "Otra Persona", "rol": "consultor"}).status_code == 409
    for nombre in ("an", "ana campo", "ñandú.uno", "ana/campo"):
        r = sesion.post("/api/usuarios", json={"usuario": nombre, "nombre": "Otra Persona", "rol": "consultor"})
        assert r.status_code == 422, nombre
    assert sesion.post("/api/usuarios", json={"usuario": "luis.llama", "nombre": "Luis", "rol": "admin"}).status_code == 422
    assert sesion.post("/api/usuarios", json={"usuario": "luis.llama", "nombre": "Luis Inventado", "rol": "consultor",
                                              "asignacion": {"lugares": [987654]}}).status_code == 422


def test_primer_ingreso_cambio_de_clave_y_compromiso(sesion):
    db = sesion.app.state.db
    r = _alta(sesion)
    c, rr = _entrar(sesion.app, "Ana.Campo", r["clave_temporal"])  # el usuario no distingue mayúsculas
    assert rr.status_code == 200, rr.text
    d = rr.json()
    assert (d["uid"], d["usuario"], d["rol"]) == (r["id"], "ana.campo", "planillero")
    assert d["debe_cambiar_clave"] is True and d["compromiso_pendiente"] is True
    # Todo lo demás responde 403 cambiar_clave, también lo que su rol sí puede
    for ruta in ("/api/catalogos", "/api/yo/indicadores", "/api/personas", "/api/usuarios"):
        x = c.get(ruta)
        assert x.status_code == 403 and x.json()["detail"]["codigo"] == "cambiar_clave", ruta
    assert c.get("/api/yo").status_code == 200
    assert c.post("/api/yo/compromiso", json={"version": "x"}).status_code in (403, 409)  # primero la clave (la UI)
    # Clave nueva mala o clave actual equivocada: 422 con el motivo
    assert c.post("/api/yo/clave", json={"actual": r["clave_temporal"], "nueva": "corta"}).status_code == 422
    assert c.post("/api/yo/clave", json={"actual": r["clave_temporal"], "nueva": "ana.campo"}).status_code == 422
    x = c.post("/api/yo/clave", json={"actual": "otra-cosa-cualquiera", "nueva": "tres palabras sueltas"})
    assert x.status_code == 422 and "actual" in x.json()["detail"]
    x = c.post("/api/yo/clave", json={"actual": r["clave_temporal"], "nueva": "tres palabras sueltas"})
    assert x.status_code == 200, x.text
    c.headers["X-CSRF-Token"] = x.json()["csrf"]
    yo = c.get("/api/yo").json()
    assert yo["debe_cambiar_clave"] is False and yo["compromiso_pendiente"] is True
    assert yo["compromiso"]["puntos"] and yo["compromiso"]["aceptado"] is False
    x = c.get("/api/catalogos")
    assert x.status_code == 403 and x.json()["detail"]["codigo"] == "compromiso"
    vigente = modelo.leer_ajustes(db)["compromiso_version"]
    assert c.post("/api/yo/compromiso", json={"version": "otra-version"}).status_code == 409
    assert c.post("/api/yo/compromiso", json={"version": vigente}).status_code == 200
    assert c.get("/api/catalogos").status_code == 200
    assert c.get("/api/yo").json()["compromiso_pendiente"] is False
    # Una versión nueva del compromiso lo vuelve a pedir
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"compromiso_version": "2027-01-v2"}}, upsert=True)
    assert c.get("/api/catalogos").json()["detail"]["codigo"] == "compromiso"
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"compromiso_version": vigente}})
    # La temporal ya no sirve; la nueva sí
    assert _entrar(sesion.app, "ana.campo", r["clave_temporal"])[1].status_code == 401
    assert _entrar(sesion.app, "ana.campo", "tres palabras sueltas")[1].status_code == 200
    acciones = {a["accion"] for a in db.auditoria.find({"uid": r["id"]})}
    assert {"ingreso", "cambiar_clave", "aceptar_compromiso"} <= acciones
    assert "tres palabras sueltas" not in json.dumps(list(db.auditoria.find({}, {"_id": 0})), default=str)


def test_cambio_de_clave_propio_cierra_las_otras_sesiones(sesion, como):
    c = como("consultor")
    otra, r = _entrar(sesion.app, c.usuario, CLAVE_USUARIO)
    assert r.status_code == 200
    x = c.post("/api/yo/clave", json={"actual": CLAVE_USUARIO, "nueva": "una clave nueva inventada"})
    assert x.status_code == 200
    c.headers["X-CSRF-Token"] = x.json()["csrf"]
    assert c.get("/api/yo").status_code == 200       # sigue, con una sesión nueva
    assert otra.get("/api/yo").status_code == 401    # la otra se cerró
    # El administrador cambia su clave en Railway
    r = sesion.post("/api/yo/clave", json={"actual": "x", "nueva": "una clave nueva inventada"})
    assert r.status_code == 409 and "Railway" in r.json()["detail"]


def test_desactivar_cae_en_la_peticion_siguiente(sesion, como):
    db = sesion.app.state.db
    c = como("consultor")
    assert c.get("/api/catalogos").status_code == 200
    r = sesion.patch(f"/api/usuarios/{c.uid}", json={"activo": False})
    assert r.status_code == 200 and r.json()["activo"] is False and r.json()["desactivado_en"]
    assert c.get("/api/catalogos").status_code == 401
    assert c.get("/api/yo").status_code == 401
    assert db.sesiones.count_documents({"uid": c.uid}) == 0
    assert _entrar(sesion.app, c.usuario, CLAVE_USUARIO)[1].status_code == 401  # el mismo 401 genérico
    assert sesion.patch(f"/api/usuarios/{c.uid}", json={"activo": True}).json()["desactivado_en"] is None
    assert _entrar(sesion.app, c.usuario, CLAVE_USUARIO)[1].status_code == 200
    detalle = [json.loads(a["detalle"]) for a in db.auditoria.find({"accion": "editar_usuario", "entidad_id": c.uid})]
    assert detalle == [{"activo": {"antes": True, "despues": False}}, {"activo": {"antes": False, "despues": True}}]


def test_cambio_de_rol_y_edicion(sesion, como):
    db = sesion.app.state.db
    c = como("planillero")
    assert c.get("/api/yo").json()["rol"] == "planillero"
    r = sesion.patch(f"/api/usuarios/{c.uid}", json={"rol": "consultor"})
    assert r.status_code == 200 and r.json()["rol"] == "consultor"
    assert c.get("/api/yo").status_code == 401  # sus sesiones se cerraron
    c2, rr = _entrar(sesion.app, c.usuario, CLAVE_USUARIO)
    assert rr.json()["rol"] == "consultor" and set(rr.json()["permisos"]) == set(acceso.PERMISOS["consultor"])
    # El nombre, el teléfono y la asignación no cierran la sesión; la asignación vale en la petición siguiente
    lugar = db.lugares.find_one({}, {"_id": 1})["_id"]
    r = sesion.patch(f"/api/usuarios/{c.uid}", json={"nombre": "Otro  Nombre Inventado", "telefono": " 300 111 2233 ",
                                                    "asignacion": {"lugares": [lugar, lugar], "areas": []}})
    assert r.status_code == 200
    assert (r.json()["nombre"], r.json()["telefono"], r.json()["asignacion"]) == (
        "Otro Nombre Inventado", "300 111 2233", {"lugares": [lugar], "areas": []})
    yo = c2.get("/api/yo")
    assert yo.status_code == 200 and yo.json()["nombre"] == "Otro Nombre Inventado"
    for malo in ({"nombre": None}, {"rol": None}, {"activo": None}, {"rol": "admin"}, {"asignacion": {"areas": [55]}}):
        assert sesion.patch(f"/api/usuarios/{c.uid}", json=malo).status_code == 422, malo
    assert sesion.patch("/api/usuarios/9999", json={"nombre": "Nadie Inventado"}).status_code == 404
    # Cerrar sesiones y desbloquear
    assert sesion.delete(f"/api/usuarios/{c.uid}/sesiones").json() == {"cerradas": 1}
    assert c2.get("/api/yo").status_code == 401
    assert sesion.delete(f"/api/usuarios/{c.uid}/bloqueo").json() == {"ok": True}


def test_no_existe_delete_de_usuarios(sesion, como):
    c = como("planillero")
    assert sesion.delete(f"/api/usuarios/{c.uid}").status_code == 405
    assert not [r for r in sesion.app.routes if isinstance(r, APIRoute) and r.path.startswith("/api/usuarios")
                and r.path.count("/") == 3 and "DELETE" in r.methods]
    assert sesion.app.state.db.usuarios.count_documents({"_id": c.uid}) == 1


@pytest.mark.parametrize("rol", ["admin", "jefe", None])
def test_rol_invalido_en_la_base_da_401(sesion, como, rol):
    db = sesion.app.state.db
    c = como("consultor")
    assert c.get("/api/catalogos").status_code == 200
    db.usuarios.update_one({"_id": c.uid}, {"$set": {"rol": rol}})
    for ruta in ("/api/yo", "/api/catalogos", "/api/usuarios", "/api/exportar.xlsx"):
        assert c.get(ruta).status_code == 401, ruta
    assert _entrar(sesion.app, c.usuario, CLAVE_USUARIO)[1].status_code == 401


def test_usuario_con_el_nombre_del_administrador_queda_desactivado_al_arrancar(sesion, cfg, caplog):
    db = sesion.app.state.db
    u = crear_usuario(db, "planillero", usuario=cfg.usuario.lower())
    db.sesiones.insert_one({"_id": "sesion-inventada", "uid": u["_id"], "huella": seg.huella_usuario(cfg, u),
                            "expira": datetime.now(timezone.utc) + timedelta(hours=1)})
    with caplog.at_level(logging.ERROR, logger="panel"):
        seg.limpiar_al_iniciar(db, cfg)
    assert "nombre del administrador" in caplog.text
    v = db.usuarios.find_one({"_id": u["_id"]})
    assert v["activo"] is False and v["version"] == u["version"] + 1
    assert db.sesiones.count_documents({"uid": u["_id"]}) == 0
    assert db.auditoria.find_one({"accion": "conflicto_admin", "entidad_id": u["_id"]})
    # Su clave no le abre la cuenta del administrador, y no se puede volver a activar
    assert _entrar(sesion.app, cfg.usuario, CLAVE_USUARIO)[1].status_code == 401
    assert sesion.patch(f"/api/usuarios/{u['_id']}", json={"activo": True}).status_code == 409


def test_lista_detalle_y_auditoria_por_usuario(sesion, como):
    db = sesion.app.state.db
    c = como("planillero", nombre="Planillera Inventada")
    lista = sesion.get("/api/usuarios").json()
    fila = next(x for x in lista if x["id"] == c.uid)
    assert fila["nombre"] == "Planillera Inventada" and fila["rol"] == "planillero" and fila["activo"] is True
    assert fila["ultimo_ingreso"] and fila["alertas"] == [] and "indicadores" in fila
    assert {"planillero", "consultor"} <= set(fila["indicadores"])
    det = sesion.get(f"/api/usuarios/{c.uid}").json()
    assert len(det["sesiones"]) == 1 and det["sesiones"][0]["ip"] and "csrf" not in json.dumps(det, default=str)
    assert det["intentos_recientes"] == []
    _entrar(sesion.app, c.usuario, "clave-equivocada")
    assert len(sesion.get(f"/api/usuarios/{c.uid}").json()["intentos_recientes"]) == 1
    assert sesion.get("/api/usuarios/9999").status_code == 404
    # La auditoría filtra por usuario, acción y fechas, con uid y rol en cada fila
    aud = sesion.get("/api/auditoria", params={"uid": c.uid}).json()
    assert aud["total"] >= 1 and all(f["uid"] == c.uid and f["rol"] == "planillero" for f in aud["filas"])
    assert {f["accion"] for f in sesion.get("/api/auditoria", params={"accion": "ingreso_fallido"}).json()["filas"]} == {"ingreso_fallido"}
    hoy = modelo.hoy_local().isoformat()
    assert sesion.get("/api/auditoria", params={"desde": hoy, "hasta": hoy}).json()["total"] == db.auditoria.count_documents({})
    assert sesion.get("/api/auditoria", params={"hasta": "2001-01-01"}).json()["total"] == 0
    assert sesion.get("/api/auditoria", params={"desde": "2026-02-30"}).status_code == 422
