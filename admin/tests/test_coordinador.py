"""Rol coordinador (adenda 1): K tiene todos los permisos de A salvo gestionar coordinadores, cambiar roles y cambiar
los ajustes que son permisos. Crea planilleros y consultores; no toca la cuenta de otro coordinador ni cambia roles (403
en el servidor); maneja los datos como A, sin presupuesto ni límite de frecuencia; pasa por la clave temporal, el
compromiso y los límites de sesión de los usuarios; sus indicadores y su auditoría llevan su uid y su rol.

Solo datos inventados. La prueba de PUT /api/ajustes se salta mientras esa ruta (del grupo 1) no exista."""
import copy
import json

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import acceso, modelo
from conftest import CEDULAS, CLAVE_USUARIO, TRAMITES, crear_usuario, excel_cedulas, excel_tramites

CLAVE_NUEVA = "una frase nueva y larga del coordinador"


def _entrar(app, usuario, clave=CLAVE_USUARIO):
    c = TestClient(app)
    r = c.post("/api/login", json={"usuario": usuario, "clave": clave})
    assert r.status_code == 200, r.text
    c.headers["X-CSRF-Token"] = r.json()["csrf"]
    return c, r.json()


@pytest.fixture
def coordinador(sesion):
    """`coordinador(**campos)`: un coordinador activo, con la clave cambiada y el compromiso aceptado, ya ingresado (el
    `crear_usuario` de conftest solo crea P y C: se crea como planillero y se pasa a coordinador en la base)."""
    abiertos = []

    def nuevo(**campos):
        db = sesion.app.state.db
        u = crear_usuario(db, "planillero", **campos)
        nombre = campos.get("usuario") or f"coordinador{u['_id']}"
        db.usuarios.update_one({"_id": u["_id"]}, {"$set": {"rol": "coordinador", "usuario": nombre}})
        c, _ = _entrar(sesion.app, nombre, campos.get("clave", CLAVE_USUARIO))
        abiertos.append(c)
        c.uid, c.usuario = u["_id"], nombre
        return c

    yield nuevo
    for c in abiertos:
        c.close()


def _es_permiso(r):
    return r.status_code == 403 and isinstance(r.json()["detail"], dict) and r.json()["detail"]["codigo"] == "permiso"


def _hay_ruta(app, metodo, ruta):
    return any(isinstance(r, APIRoute) and r.path == ruta and metodo in r.methods for r in app.routes)


# ───────────────────────────── Roles y permisos ─────────────────────────────

def test_roles_y_permisos_del_coordinador():
    assert acceso.ROLES == {"admin", "coordinador", "planillero", "consultor"}
    assert acceso.SOLO_ADMIN == frozenset({"usuarios.coordinadores", "usuarios.roles", "permisos.modificar"})
    assert acceso.ROLES_ADMIN == frozenset({"admin", "coordinador"})
    K = acceso.Quien(uid=7, usuario="coordinador7", rol="coordinador", permisos=acceso.PERMISOS["coordinador"])
    A = acceso.Quien(uid=0, usuario="admin", rol="admin", permisos=acceso.PERMISOS["admin"])
    P = acceso.Quien(uid=5, usuario="planillero5", rol="planillero", permisos=acceso.PERMISOS["planillero"])
    for p in ("admin", "importar", "exportar", "tablero.ver", "mapa.ver", "usuarios.gestionar", "calidad.ver",
              "calidad.resolver", "ajustes.gestionar", "zonas.gestionar", "personas.editar", "trabajo.cola"):
        assert K.puede(p), p
    for p in acceso.SOLO_ADMIN:
        assert not K.puede(p) and A.puede(p) and not P.puede(p), p
    assert K.administra and not K.es_admin and A.administra and A.es_admin
    assert not P.administra and not P.es_admin
    # «*» no alcanza para lo exclusivo de A, ni un rol «admin» con uid de usuario es el administrador
    falso = acceso.Quien(uid=9, usuario="x", rol="admin", permisos=frozenset({"*"}))
    assert not falso.es_admin and not falso.puede("usuarios.roles")
    assert acceso.excepto("coordinador") == sorted(acceso.SOLO_ADMIN)
    assert acceso.excepto("admin") == [] and acceso.excepto("planillero") == []


def test_ajustes_de_permisos_solo_los_cambia_el_admin():
    K = acceso.Quien(uid=7, usuario="coordinador7", rol="coordinador", permisos=acceso.PERMISOS["coordinador"])
    A = acceso.Quien(uid=0, usuario="admin", rol="admin", permisos=acceso.PERMISOS["admin"])
    actuales = copy.deepcopy(modelo.AJUSTES_POR_DEFECTO)
    for cambios in ({"presupuesto_diario": {"planillero": 5}}, {"sesion": {"horas_max": 4}},
                    {"sesion": {"max_por_usuario": 9}}, {"contactar_pendientes": True}, {"max_intentos_sin_exito": 9},
                    {"horario": {"domingo": ["08:00", "12:00"]}}, {"sensibles_activos": True}):
        with pytest.raises(HTTPException) as e:
            acceso.exigir_ajustes(K, actuales, cambios)
        assert e.value.status_code == 403 and e.value.detail["codigo"] == "permiso"
        assert e.value.detail["campos"] == sorted(cambios)
        acceso.exigir_ajustes(A, actuales, cambios)
    # Un formulario que manda todo sin cambiar los permisos, o solo otros ajustes, sí lo guarda K
    acceso.exigir_ajustes(K, actuales, copy.deepcopy(actuales))
    acceso.exigir_ajustes(K, actuales, {"sesion": {"horas_max": actuales["sesion"]["horas_max"]}})
    acceso.exigir_ajustes(K, actuales, {"enlace_consulta_puesto": "https://ejemplo.invalid/consulta",
                                        "eleccion_vigente": "2026-presidencial"})
    with pytest.raises(HTTPException):
        acceso.exigir_ajustes(None, actuales, {"presupuesto_diario": {"consultor": 1}})


# ───────────────────────────── Gestión de usuarios ─────────────────────────────

def test_coordinador_crea_y_gestiona_planilleros_y_consultores(sesion, coordinador):
    db = sesion.app.state.db
    k = coordinador()
    nuevos = {}
    for usuario, rol in (("pia.campo", "planillero"), ("leo.llama", "consultor")):
        r = k.post("/api/usuarios", json={"usuario": usuario, "nombre": "Persona Inventada", "rol": rol})
        assert r.status_code == 201, r.text
        nuevos[rol] = r.json()["id"]
        assert db.auditoria.find_one({"accion": "crear_usuario", "entidad_id": r.json()["id"], "uid": k.uid,
                                      "rol": "coordinador"})
    # No crea coordinadores: 403 y nada queda en la base
    r = k.post("/api/usuarios", json={"usuario": "otro.coord", "nombre": "Otro Coordinador", "rol": "coordinador"})
    assert _es_permiso(r) and db.usuarios.find_one({"usuario": "otro.coord"}) is None
    p = nuevos["planillero"]
    lugar = db.lugares.find_one({}, {"_id": 1})["_id"]
    r = k.patch(f"/api/usuarios/{p}", json={"nombre": "Pía Campo Inventada", "asignacion": {"lugares": [lugar]}})
    assert r.status_code == 200 and r.json()["asignacion"]["lugares"] == [lugar]
    # No cambia roles, ni siquiera mandando el mismo
    for rol in ("consultor", "coordinador", "planillero"):
        assert _es_permiso(k.patch(f"/api/usuarios/{p}", json={"rol": rol}))
    assert db.usuarios.find_one({"_id": p})["rol"] == "planillero"
    assert k.patch(f"/api/usuarios/{p}", json={"activo": False}).json()["activo"] is False
    assert k.patch(f"/api/usuarios/{p}", json={"activo": True}).json()["activo"] is True
    assert k.post(f"/api/usuarios/{p}/clave").status_code == 200
    assert k.delete(f"/api/usuarios/{p}/sesiones").status_code == 200
    assert k.delete(f"/api/usuarios/{p}/bloqueo").status_code == 200
    # Ve a todos, con su detalle e indicadores (también a los coordinadores)
    filas = {u["id"]: u for u in k.get("/api/usuarios").json()}
    assert set(filas) >= {k.uid, *nuevos.values()} and filas[k.uid]["rol"] == "coordinador"
    assert k.get(f"/api/usuarios/{k.uid}").status_code == 200
    assert k.get(f"/api/usuarios/{k.uid}/indicadores").status_code == 200


def test_coordinador_no_toca_a_otro_coordinador_ni_a_si_mismo(sesion, coordinador):
    db = sesion.app.state.db
    k, otro = coordinador(), coordinador()
    for objetivo in (otro.uid, k.uid):
        for metodo, ruta, cuerpo in (("patch", "", {"nombre": "Nombre Cambiado"}), ("patch", "", {"activo": False}),
                                     ("patch", "", {"telefono": "300 000 0009"}), ("post", "/clave", None),
                                     ("delete", "/sesiones", None), ("delete", "/bloqueo", None)):
            kw = {"json": cuerpo} if cuerpo is not None else {}
            r = getattr(k, metodo)(f"/api/usuarios/{objetivo}{ruta}", **kw)
            assert _es_permiso(r), (objetivo, metodo, ruta, r.status_code)
    u = db.usuarios.find_one({"_id": otro.uid})
    assert u["activo"] is True and u["nombre"] != "Nombre Cambiado" and u["debe_cambiar_clave"] is False
    assert otro.get("/api/catalogos").status_code == 200  # su sesión sigue abierta
    # Un usuario con un rol que no es de campo también queda fuera del alcance de K (falla cerrada)
    raro = crear_usuario(db, "consultor")
    db.usuarios.update_one({"_id": raro["_id"]}, {"$set": {"rol": "jefe"}})
    assert _es_permiso(k.patch(f"/api/usuarios/{raro['_id']}", json={"activo": False}))


def test_admin_crea_coordinador_y_le_cambia_el_rol(sesion):
    db = sesion.app.state.db
    lugar = db.lugares.find_one({}, {"_id": 1})["_id"]
    # Un coordinador no tiene asignación: trabaja sobre toda la base
    r = sesion.post("/api/usuarios", json={"usuario": "kata.coord", "nombre": "Kata Coordinadora Inventada",
                                           "rol": "coordinador", "asignacion": {"lugares": [lugar]}})
    assert r.status_code == 422
    r = sesion.post("/api/usuarios", json={"usuario": "kata.coord", "nombre": "Kata Coordinadora Inventada",
                                           "rol": "coordinador"})
    assert r.status_code == 201, r.text
    kid = r.json()["id"]
    alta = db.auditoria.find_one({"accion": "crear_usuario", "entidad_id": kid, "uid": 0, "rol": "admin"})
    assert json.loads(alta["detalle"])["rol"] == "coordinador"
    version = db.usuarios.find_one({"_id": kid})["version"]
    r = sesion.patch(f"/api/usuarios/{kid}", json={"rol": "planillero"})
    assert r.status_code == 200 and r.json()["rol"] == "planillero"
    sesion.patch(f"/api/usuarios/{kid}", json={"asignacion": {"lugares": [lugar]}})
    # De vuelta a coordinador: deja la asignación, sube la versión y queda en la auditoría con quién lo hizo
    r = sesion.patch(f"/api/usuarios/{kid}", json={"rol": "coordinador"})
    assert r.status_code == 200 and r.json()["rol"] == "coordinador"
    assert r.json()["asignacion"] == {"lugares": [], "areas": []}
    assert db.usuarios.find_one({"_id": kid})["version"] > version
    cambios = [json.loads(x["detalle"]) for x in db.auditoria.find({"accion": "editar_usuario", "entidad_id": kid,
                                                                     "uid": 0, "rol": "admin"})]
    assert {"antes": "planillero", "despues": "coordinador"} in [x.get("rol") for x in cambios]
    # A gestiona coordinadores: desactivar, restablecer la clave, cerrar sesiones
    assert sesion.patch(f"/api/usuarios/{kid}", json={"activo": False}).json()["activo"] is False
    ultima = db.auditoria.find_one({"accion": "editar_usuario", "entidad_id": kid, "uid": 0}, sort=[("_id", -1)])
    assert json.loads(ultima["detalle"])["activo"] == {"antes": True, "despues": False}
    assert sesion.patch(f"/api/usuarios/{kid}", json={"activo": True}).status_code == 200
    assert sesion.post(f"/api/usuarios/{kid}/clave").status_code == 200
    assert sesion.delete(f"/api/usuarios/{kid}/sesiones").status_code == 200


# ───────────────────────────── Cuenta y sesiones ─────────────────────────────

def test_coordinador_pasa_por_clave_temporal_y_compromiso(sesion, tmp_path):
    r = sesion.post("/api/usuarios", json={"usuario": "kata.coord", "nombre": "Kata Coordinadora Inventada",
                                           "rol": "coordinador"})
    c, d = _entrar(sesion.app, "kata.coord", r.json()["clave_temporal"])
    assert d["rol"] == "coordinador" and d["permisos"] == ["*"] and d["excepto"] == sorted(acceso.SOLO_ADMIN)
    assert d["debe_cambiar_clave"] is True and d["compromiso_pendiente"] is True
    assert c.get("/api/usuarios").json()["detail"]["codigo"] == "cambiar_clave"
    # Importar no se le rechaza por el rol, sino por la clave pendiente (y antes de leer la subida)
    x = excel_tramites(tmp_path / "t.xlsx", TRAMITES)
    with x.open("rb") as f:
        r = c.post("/api/importar", files=[("archivos", ("tramites.xlsx", f.read()))])
    assert r.status_code == 403 and r.json()["detail"]["codigo"] == "cambiar_clave"
    # Su cuenta sí la abre; con la clave actual equivocada, 422 (no 401: la sesión sigue)
    assert c.get("/api/yo").status_code == 200
    assert c.post("/api/yo/clave", json={"actual": "no es la temporal", "nueva": CLAVE_NUEVA}).status_code == 422
    c.close()


def test_coordinador_cambia_la_clave_acepta_el_compromiso_y_trabaja(sesion):
    db = sesion.app.state.db
    temporal = sesion.post("/api/usuarios", json={"usuario": "kata.coord", "nombre": "Kata Coordinadora Inventada",
                                                  "rol": "coordinador"}).json()["clave_temporal"]
    c, _ = _entrar(sesion.app, "kata.coord", temporal)
    r = c.post("/api/yo/clave", json={"actual": temporal, "nueva": CLAVE_NUEVA})
    assert r.status_code == 200, r.text
    c.headers["X-CSRF-Token"] = r.json()["csrf"]
    assert c.get("/api/usuarios").json()["detail"]["codigo"] == "compromiso"
    vigente = modelo.leer_ajustes(db)["compromiso_version"]
    assert c.post("/api/yo/compromiso", json={"version": vigente}).status_code == 200
    assert c.get("/api/usuarios").status_code == 200
    yo = c.get("/api/yo").json()
    assert yo["rol"] == "coordinador" and not yo["debe_cambiar_clave"] and not yo["compromiso_pendiente"]
    assert db.auditoria.find_one({"accion": "cambiar_clave", "uid": yo["uid"], "rol": "coordinador"})
    c.close()


def test_coordinador_con_los_limites_de_sesion_de_los_usuarios(sesion, coordinador):
    db = sesion.app.state.db
    k = coordinador()
    otras = [_entrar(sesion.app, k.usuario)[0] for _ in range(2)]
    assert db.sesiones.count_documents({"uid": k.uid}) == 2  # como mucho 2: la más vieja (la de `k`) se cerró
    assert k.get("/api/catalogos").status_code == 401
    s = db.sesiones.find_one({"uid": k.uid})
    assert s["rol"] == "coordinador" and (s["expira"] - s["creada"]).total_seconds() <= 10 * 3600
    # Un coordinador desactivado pierde sus sesiones en la siguiente petición
    assert otras[1].get("/api/catalogos").status_code == 200
    assert sesion.patch(f"/api/usuarios/{k.uid}", json={"activo": False}).status_code == 200
    assert otras[1].get("/api/catalogos").status_code == 401
    with TestClient(sesion.app) as nuevo:
        assert nuevo.post("/api/login", json={"usuario": k.usuario, "clave": CLAVE_USUARIO}).status_code == 401
    for o in otras:
        o.close()


# ───────────────────────────── Datos como A ─────────────────────────────

def test_coordinador_importa_exporta_y_ve_los_datos_como_el_admin(sesion, coordinador, tmp_path):
    db = sesion.app.state.db
    k = coordinador()
    a = excel_tramites(tmp_path / "t.xlsx", TRAMITES)
    b = excel_cedulas(tmp_path / "c.xlsx", CEDULAS)
    with a.open("rb") as fa, b.open("rb") as fb:
        r = k.post("/api/importar", files=[("archivos", ("tramites.xlsx", fa.read())),
                                          ("archivos", ("cedulas.xlsx", fb.read()))])
    assert r.status_code == 200, r.text
    assert k.get("/api/importaciones").status_code == 200
    r = k.get("/api/exportar.xlsx", params={"incluir_listas": 1, "motivo": "Revisión de listas inventadas"})
    assert r.status_code == 200 and r.content[:2] == b"PK"
    assert db.auditoria.find_one({"accion": "exportar", "uid": k.uid, "rol": "coordinador"})
    # Datos políticos y cédula completa: la ficha de K tiene lo mismo que la de A
    p = db.personas.find_one({"cedula": "90000001", "fusionada_en": None}, {"_id": 1})
    db.personas.update_one({"_id": p["_id"]}, {"$set": {"lider": True}})
    fk, fa_ = k.get(f"/api/personas/{p['_id']}"), sesion.get(f"/api/personas/{p['_id']}")
    assert fk.status_code == fa_.status_code == 200
    fk, fa_ = fk.json(), fa_.json()
    assert fk["cedula"] == "90000001" and fk["lider"] is True and "Lista A" in (fk.get("listas") or [])
    assert set(fk) == set(fa_) and all(fk[c] == fa_[c] for c in ("cedula", "lider", "listas", "nombre"))
    # Catálogos completos, auditoría y tablero
    cat = k.get("/api/catalogos")
    assert cat.status_code == 200 and cat.headers["etag"].startswith('W/"admin-')
    assert "Lista A" in cat.json()["listas"] and any(u["id"] == k.uid for u in cat.json()["usuarios"])
    assert set(cat.json()) == set(sesion.get("/api/catalogos").json())
    assert k.get("/api/auditoria", params={"uid": k.uid}).json()["total"] >= 2
    assert k.get("/api/indicadores").status_code == 200


def test_coordinador_sin_presupuesto_diario_ni_limite_de_frecuencia(sesion, coordinador, como):
    db = sesion.app.state.db
    db.meta.update_one({"_id": "ajustes"},
                       {"$set": {"presupuesto_diario.planillero": 3, "presupuesto_diario.consultor": 3}}, upsert=True)
    assert acceso.presupuesto(db, "coordinador") is None and acceso.presupuesto(db, "admin") is None
    mini = FastAPI()
    mini.state.cfg, mini.state.db = sesion.app.state.cfg, db

    @mini.get("/leer")
    def leer(n: int, q: acceso.Quien = Depends(acceso.requiere("personas.buscar"))):
        acceso.registrar_lecturas(db, q, list(range(1, n + 1)))
        return {"n": n}

    @mini.get("/limitada")
    def limitada(q: acceso.Quien = Depends(acceso.requiere("personas.buscar", limitar=True))):
        return {"asignacion": q.asignacion}

    k = coordinador()
    mk = TestClient(mini, cookies=dict(k.cookies))
    assert mk.get("/leer", params={"n": 50}).status_code == 200
    assert db.lecturas.count_documents({"uid": k.uid}) == 50  # queda registrado, sin tope
    mp = TestClient(mini, cookies=dict(como("planillero").cookies))
    assert mp.get("/leer", params={"n": 4}).json()["detail"]["codigo"] == "volumen"
    for _ in range(acceso.FRECUENCIA_MAX + 5):
        r = mk.get("/limitada")
        assert r.status_code == 200
    assert r.json()["asignacion"] is None  # sin alcance: toda la base


# ───────────────────────────── Permisos: ajustes y campos sensibles ─────────────────────────────

def test_campo_sensible_solo_lo_cambia_el_admin(sesion, coordinador):
    k = coordinador()
    r = k.post("/api/campos", json={"etiqueta": "Mascotas inventadas", "tipo": "texto"})
    assert r.status_code == 201
    cid = sesion.app.state.db.campos.find_one({"clave": r.json()["clave"]})["_id"]
    r = k.patch(f"/api/campos/{cid}", json={"sensible": True})
    assert _es_permiso(r) and r.json()["detail"]["campos"] == ["sensible"]
    assert k.patch(f"/api/campos/{cid}", json={"etiqueta": "Mascotas de la casa", "sensible": False}).status_code == 200
    assert sesion.patch(f"/api/campos/{cid}", json={"sensible": True}).status_code == 200
    assert _es_permiso(k.patch(f"/api/campos/{cid}", json={"sensible": False}))
    assert sesion.app.state.db.campos.find_one({"_id": cid})["sensible"] is True


def test_ajustes_de_permisos_por_la_api(sesion, coordinador):
    if not _hay_ruta(sesion.app, "PUT", "/api/ajustes"):
        pytest.skip("PUT /api/ajustes llega con el grupo 1")
    k = coordinador()
    assert k.get("/api/ajustes").status_code == 200
    for cambios in ({"presupuesto_diario": {"planillero": 5}}, {"sesion": {"horas_max": 4}},
                    {"contactar_pendientes": True}):
        assert _es_permiso(k.put("/api/ajustes", json=cambios)), cambios
        r = sesion.put("/api/ajustes", json=cambios)
        assert r.status_code < 300, (cambios, r.text)
    aj = modelo.leer_ajustes(sesion.app.state.db)
    assert aj["presupuesto_diario"]["planillero"] == 5 and aj["sesion"]["horas_max"] == 4 and aj["contactar_pendientes"]


# ───────────────────────────── Indicadores ─────────────────────────────

def test_indicadores_incluyen_a_los_coordinadores(sesion, coordinador):
    k = coordinador()
    assert k.post("/api/usuarios", json={"usuario": "pia.campo", "nombre": "Pía Campo Inventada",
                                         "rol": "planillero"}).status_code == 201
    assert k.get("/api/exportar.xlsx").status_code == 200
    for cliente in (sesion, k):  # A los ve, y K también
        ind = cliente.get("/api/usuarios/indicadores").json()
        fila = next(u for u in ind["usuarios"] if u["uid"] == k.uid)
        assert fila["rol"] == "coordinador"
        assert fila["administracion"]["exportaciones"] == 1 and fila["administracion"]["usuarios_creados"] == 1
        assert ind["totales"]["coordinadores_activos"] == 1
    yo = k.get("/api/yo/indicadores").json()
    assert yo["rol"] == "coordinador" and yo["administracion"]["usuarios_creados"] == 1
    # Un planillero no tiene trabajo de administración, pero el bloque está (en cero)
    pia = next(u for u in sesion.get("/api/usuarios/indicadores").json()["usuarios"] if u["usuario"] == "pia.campo")
    assert set(pia["administracion"].values()) == {0}
