"""Ajustes (1.8, 7.11): valores por defecto, PUT parcial (también dentro de los objetos), validación, versión de los
catálogos y auditoría. Administrador y coordinador; los ajustes que son permisos (presupuestos, sesiones y política de
contacto) solo el administrador (adenda del coordinador)."""
import pytest
from fastapi.testclient import TestClient

from app import acceso, modelo
from conftest import CLAVE_USUARIO, crear_usuario

# Cuerpos que tocan ajustes de permisos (`permisos.modificar`)
DE_PERMISOS = [
    {"presupuesto_diario": {"planillero": 50}}, {"sesion": {"horas_max": 4}}, {"contactar_pendientes": True},
    {"horario": {"domingo": ["08:00", "12:00"]}}, {"max_intentos_sin_exito": 2}, {"dias_entre_intentos": 5},
    {"seguimiento_activo": True}, {"dias_seguimiento": 30}, {"tope_cedulas_dictadas": 5},
    {"sensibles_activos": True}, {"compromiso_version": "2026-12-v2"},  # integración: la lista es la de acceso (G2)
]


def test_valores_por_defecto(sesion):
    a = sesion.get("/api/ajustes").json()
    for k, v in modelo.AJUSTES_POR_DEFECTO.items():
        assert a[k] == v, k
    assert a["elecciones"] == ["2026-presidencial"] and a["catalogos_version"] == 0


def test_put_parcial_tambien_dentro_de_los_objetos(sesion):
    c = sesion
    r = c.put("/api/ajustes", json={"dias_entre_intentos": 3, "horario": {"sabado": ["09:00", "13:00"]},
                                    "sesion": {"inactividad_min": 45}, "aviso_privacidad": {"responsable": "Inventado S.A.S."},
                                    "contactar_pendientes": True})
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["dias_entre_intentos"] == 3 and a["contactar_pendientes"] is True
    assert a["horario"] == {"semana": ["07:00", "19:00"], "sabado": ["09:00", "13:00"], "domingo": False}
    assert a["sesion"] == {"horas_max": 10, "inactividad_min": 45, "max_por_usuario": 2}
    assert a["aviso_privacidad"]["responsable"] == "Inventado S.A.S." and a["aviso_privacidad"]["version"] == "2026-11-v1"
    assert a["catalogos_version"] == 1
    db = c.app.state.db
    assert modelo.leer_ajustes(db)["sesion"]["inactividad_min"] == 45
    aud = db.auditoria.find_one({"accion": "ajustes"})
    assert aud["uid"] == 0 and "contactar_pendientes" in aud["detalle"]
    # Un segundo PUT no pierde lo anterior
    a = c.put("/api/ajustes", json={"horario": {"domingo": ["08:00", "12:00"]}}).json()
    assert a["horario"]["sabado"] == ["09:00", "13:00"] and a["horario"]["domingo"] == ["08:00", "12:00"]
    assert c.put("/api/ajustes", json={}).json()["catalogos_version"] == 2


@pytest.mark.parametrize("cuerpo", [
    {"dias_entre_intentos": 0}, {"horario": {"semana": ["19:00", "07:00"]}}, {"horario": {"semana": ["7am", "19:00"]}},
    {"presupuesto_diario": {"planillero": 1}}, {"sesion": {"horas_max": 48}}, {"desconocido": 1},
    {"enlace_consulta_puesto": "http://inseguro.test/"}, {"eleccion_vigente": "presidencial"},
    {"horario": {"lunes": ["07:00", "19:00"]}}, {"vigencia_base": "2026-01-01"},
])
def test_valores_invalidos(sesion, cuerpo):
    assert sesion.put("/api/ajustes", json=cuerpo).status_code == 422


def test_eleccion_vigente_exige_sus_puestos(sesion):
    c = sesion
    r = c.put("/api/ajustes", json={"eleccion_vigente": "2027-territoriales"})
    assert r.status_code == 422
    c.post("/api/puestos", json={"eleccion": "2027-territoriales", "codigo": "00-01", "nombre": "Puesto inventado",
                                 "mesas": 3})
    r = c.put("/api/ajustes", json={"eleccion_vigente": "2027-territoriales"})
    assert r.status_code == 200 and r.json()["eleccion_vigente"] == "2027-territoriales"
    assert [p["codigo"] for p in c.get("/api/puestos").json()] == ["00-01"]
    assert r.json()["elecciones"] == ["2026-presidencial", "2027-territoriales"]


def test_solo_el_administrador(cliente, como):
    for rol in ("planillero", "consultor"):
        u = como(rol)
        assert u.get("/api/ajustes").status_code == 403
        assert u.put("/api/ajustes", json={"dias_entre_intentos": 3}).status_code == 403
    p = como("planillero")
    assert p.get("/api/plantillas/planilla.xlsx").status_code == 200
    assert como("consultor").get("/api/plantillas/planilla.xlsx").status_code == 403


def test_ajustes_de_permisos_exigen_permisos_modificar(sesion, monkeypatch):
    """Quien tiene `ajustes.gestionar` pero no `permisos.modificar` (el coordinador) recibe 403 `permiso` en
    presupuestos, sesiones y política de contacto, y cambia lo demás. Se simula con los permisos del rol mientras el
    coordinador no exista (llega con el grupo 2)."""
    c = sesion
    db = c.app.state.db
    assert c.get("/api/ajustes").json()["puede_modificar_permisos"] is True
    monkeypatch.setitem(acceso.PERMISOS, "admin", frozenset({"ajustes.gestionar", "puestos.ver", "puestos.gestionar"}))
    a = c.get("/api/ajustes").json()
    assert a["puede_modificar_permisos"] is False and "presupuesto_diario" in a["ajustes_de_permisos"]
    for cuerpo in DE_PERMISOS:
        r = c.put("/api/ajustes", json=cuerpo)
        assert r.status_code == 403 and r.json()["detail"]["codigo"] == "permiso", cuerpo
    assert modelo.leer_ajustes(db) == modelo.AJUSTES_POR_DEFECTO and db.auditoria.count_documents({"accion": "ajustes"}) == 0
    # Lo demás sí; reenviar los de permisos con su valor actual (el formulario completo) no estorba
    r = c.put("/api/ajustes", json={"aviso_privacidad": {"responsable": "Inventado S.A.S."}, "sesion": a["sesion"],
                                    "contactar_pendientes": a["contactar_pendientes"], "dias_reintento_dato": 60,
                                    "sensibles_activos": a["sensibles_activos"],
                                    "compromiso_version": a["compromiso_version"]})
    assert r.status_code == 200, r.text
    a = modelo.leer_ajustes(db)
    assert a["aviso_privacidad"]["responsable"] == "Inventado S.A.S." and a["dias_reintento_dato"] == 60
    assert a["sesion"] == modelo.AJUSTES_POR_DEFECTO["sesion"]
    assert "sesion" not in db.auditoria.find_one({"accion": "ajustes"})["detalle"]
    # El catálogo completo de puestos (también los inactivos) va con `puestos.gestionar`, no con el rol
    assert c.get("/api/puestos", params={"todos": 1}).status_code == 200


def _coordinador(cliente):
    """Un coordinador activo y su cliente. Se salta mientras el rol no exista (grupo 2 con la adenda)."""
    if "coordinador" not in acceso.ROLES:
        pytest.skip("requiere el rol coordinador (grupo 2 con la adenda)")
    db = cliente.app.state.db
    u = crear_usuario(db, "planillero", usuario="coordinadora.k", nombre="Coordinadora de prueba")
    db.usuarios.update_one({"_id": u["_id"]}, {"$set": {"rol": "coordinador"}})
    k = TestClient(cliente.app)
    r = k.post("/api/login", json={"usuario": "coordinadora.k", "clave": CLAVE_USUARIO})
    assert r.status_code == 200, r.text
    k.headers["X-CSRF-Token"] = r.json()["csrf"]
    return k


def test_coordinador_ve_y_cambia_lo_que_no_es_permiso(sesion, cliente):
    k = _coordinador(cliente)
    try:
        a = k.get("/api/ajustes")
        assert a.status_code == 200 and a.json()["puede_modificar_permisos"] is False
        for cuerpo in DE_PERMISOS:
            assert k.put("/api/ajustes", json=cuerpo).status_code == 403, cuerpo
        assert k.put("/api/ajustes", json={"aviso_privacidad": {"contacto": "datos@ejemplo.test"}}).status_code == 200
        for ruta in ("/api/conflictos", "/api/solicitudes", "/api/situaciones", "/api/coincidencias", "/api/lugares"):
            assert k.get(ruta).status_code == 200, ruta
        assert k.post("/api/puestos", json={"codigo": "99-99", "nombre": "Puesto inventado", "mesas": 1}).status_code == 201
        # El administrador sí cambia los ajustes de permisos
        r = sesion.put("/api/ajustes", json={"presupuesto_diario": {"consultor": 200}, "contactar_pendientes": True})
        assert r.status_code == 200 and r.json()["puede_modificar_permisos"] is True
    finally:
        k.close()
