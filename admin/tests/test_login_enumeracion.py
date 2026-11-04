"""Ingreso sin enumeración (3.4): misma respuesta y tiempo parecido para nombres reales e inventados, la marca del
navegador atada a su cuenta, la alerta de ingresos y el semáforo de scrypt."""
import statistics
import time

from fastapi.testclient import TestClient

from app import acceso
from app import seguridad as seg
from conftest import CLAVE_USUARIO

CLAVE = "clave-de-prueba-larga"


def _login(app_o_cliente, usuario, clave, ip=None, **headers):
    c = app_o_cliente if isinstance(app_o_cliente, TestClient) else TestClient(app_o_cliente)
    if ip:
        headers["X-Real-IP"] = ip
    return c.post("/api/login", json={"usuario": usuario, "clave": clave}, headers=headers)


def test_misma_respuesta_para_un_nombre_real_y_uno_inventado(cliente, como):
    db = cliente.app.state.db
    p = como("planillero")
    inactivo = como("consultor")
    db.usuarios.update_one({"_id": inactivo.uid}, {"$set": {"activo": False}})
    respuestas = [
        _login(cliente.app, p.usuario, "clave-equivocada-1", ip="198.51.100.20"),
        _login(cliente.app, "nadie.inventado", "clave-equivocada-1", ip="198.51.100.21"),
        _login(cliente.app, "admin", "clave-equivocada-1", ip="198.51.100.22"),
        _login(cliente.app, inactivo.usuario, CLAVE_USUARIO, ip="198.51.100.23"),  # clave correcta, cuenta inactiva
    ]
    assert {r.status_code for r in respuestas} == {401}
    assert len({r.text for r in respuestas}) == 1
    for r in respuestas:
        assert "set-cookie" not in r.headers
    # La auditoría guarda la cuenta si existe, nunca lo escrito
    fallidos = list(db.auditoria.find({"accion": "ingreso_fallido"}))
    assert {a["usuario"] for a in fallidos} == {p.usuario, "desconocido", "admin", inactivo.usuario}
    assert "nadie.inventado" not in str(fallidos)


def test_tiempo_parecido_para_el_administrador_un_usuario_y_un_desconocido(cliente, como):
    c = como("consultor")

    def mediana(usuario, ip):
        tiempos = []
        for i in range(5):
            t = time.perf_counter()
            assert _login(cliente.app, usuario, f"clave-equivocada-{i}", ip=ip).status_code == 401
            tiempos.append(time.perf_counter() - t)
        return statistics.median(tiempos)

    medianas = [mediana("admin", "198.51.100.31"), mediana(c.usuario, "198.51.100.32"),
                mediana("nadie.inventado", "198.51.100.33")]
    for a in medianas:
        for b in medianas:
            # Difieren menos de un 50 % o de 100 ms
            assert abs(a - b) < max(0.1, 0.5 * max(a, b)), medianas


def test_fallos_ajenos_en_la_misma_ip_no_bloquean_al_navegador_con_su_marca(cliente, como):
    app = cliente.app
    p, k = como("planillero"), como("consultor")
    ip = "203.0.113.70"  # una IP compartida (CGNAT)
    nav = TestClient(app)
    assert _login(nav, p.usuario, CLAVE_USUARIO, ip=ip).status_code == 200
    marca = nav.cookies.get(seg.COOKIE_DISPOSITIVO)
    assert marca and marca.startswith(f"u{p.uid}.")
    con_marca = {"Cookie": f"{seg.COOKIE_DISPOSITIVO}={marca}"}
    # Otro, desde la misma IP, falla 5 veces con otra cuenta
    for _ in range(seg.MAX_POR_IP):
        assert _login(app, "admin", "clave-mala", ip=ip).status_code == 401
    assert _login(app, p.usuario, CLAVE_USUARIO, ip=ip).status_code == 429             # sin marca: espera
    assert _login(app, p.usuario, CLAVE_USUARIO, ip=ip, **con_marca).status_code == 200  # con su marca: entra
    # Una marca de otra cuenta no sirve (ni para otro usuario ni para el administrador)
    assert _login(app, k.usuario, CLAVE_USUARIO, ip=ip, **con_marca).status_code == 429
    assert _login(app, "admin", CLAVE, ip=ip, **con_marca).status_code == 429
    # Sus propios fallos con la marca sí la bloquean
    for _ in range(seg.MAX_POR_IP):
        assert _login(app, p.usuario, "clave-mala", ip=ip, **con_marca).status_code == 401
    assert _login(app, p.usuario, CLAVE_USUARIO, ip=ip, **con_marca).status_code == 429
    # Una marca inventada o de una versión vieja tampoco
    falsa = f"u{p.uid}.inventada.{'0' * 64}"
    assert _login(app, p.usuario, CLAVE_USUARIO, ip="203.0.113.71", Cookie=f"{seg.COOKIE_DISPOSITIVO}={falsa}").status_code == 200
    assert cliente.app.state.db.intentos.count_documents({"ip": "203.0.113.71", "marca_h": {"$ne": None}}) == 0


def test_desbloquear_borra_los_fallos_de_su_nombre(sesion, como):
    app = sesion.app
    p = como("planillero")
    for _ in range(seg.MAX_POR_IP):
        assert _login(app, p.usuario, "clave-mala", ip="203.0.113.80").status_code == 401
    assert _login(app, p.usuario, CLAVE_USUARIO, ip="203.0.113.80").status_code == 429
    fila = next(u for u in sesion.get("/api/usuarios").json() if u["id"] == p.uid)
    assert fila["bloqueado"] is True and "bloqueo" in fila["alertas"]
    assert sesion.delete(f"/api/usuarios/{p.uid}/bloqueo").status_code == 200
    assert _login(app, p.usuario, CLAVE_USUARIO, ip="203.0.113.80").status_code == 200
    assert next(u for u in sesion.get("/api/usuarios").json() if u["id"] == p.uid)["bloqueado"] is False


def test_un_ingreso_correcto_borra_solo_los_fallos_de_su_nombre(cliente, como):
    db = cliente.app.state.db
    p = como("planillero")
    ip = "203.0.113.90"
    assert _login(cliente.app, "admin", "clave-mala", ip=ip).status_code == 401
    assert _login(cliente.app, p.usuario, "clave-mala", ip=ip).status_code == 401
    assert _login(cliente.app, p.usuario, CLAVE_USUARIO, ip=ip).status_code == 200
    restantes = list(db.intentos.find({"ip": ip, "ok": False}))
    assert len(restantes) == 1 and restantes[0]["nombre_h"] == acceso.nombre_h(db, "admin")


def test_alerta_con_21_fallos(sesion, como):
    db = sesion.app.state.db
    k = como("consultor")
    for i in range(21):
        assert _login(sesion.app, k.usuario, "clave-mala", ip=f"198.51.100.{100 + i // 5}").status_code == 401
    alertas = list(db.auditoria.find({"accion": "alerta_ingresos"}))
    assert len(alertas) == 1 and (alertas[0]["entidad"], alertas[0]["entidad_id"]) == ("usuario", k.uid)
    assert _login(sesion.app, k.usuario, "clave-mala", ip="198.51.100.120").status_code == 401
    assert db.auditoria.count_documents({"accion": "alerta_ingresos"}) == 1  # una vez por día
    # La respuesta no cambia: no hay bloqueo por nombre, entra desde su IP
    assert _login(sesion.app, k.usuario, CLAVE_USUARIO, ip="198.51.100.200").status_code == 200
    fila = next(u for u in sesion.get("/api/usuarios").json() if u["id"] == k.uid)
    assert "ingresos" in fila["alertas"]
    # Con un nombre inventado también hay alerta, sin guardar lo escrito
    for i in range(21):
        _login(sesion.app, "otro.inventado", "clave-mala", ip=f"198.51.100.{150 + i // 5}")
    otra = db.auditoria.find_one({"accion": "alerta_ingresos", "entidad_id": None})
    assert otra and "otro.inventado" not in str(otra) and '"usuario": "desconocido"' in otra["detalle"]


def test_semaforo_de_scrypt_responde_503(cliente, monkeypatch):
    class Lleno:
        def acquire(self, timeout=None):
            return False

        def release(self):
            raise AssertionError("no se tomó el turno")

    monkeypatch.setattr(acceso, "_TURNOS", Lleno())
    r = _login(cliente.app, "admin", CLAVE, ip="198.51.100.250")
    assert r.status_code == 503 and r.headers["retry-after"] == "2"
    # No cuenta como intento fallido
    assert cliente.app.state.db.intentos.count_documents({"ip": "198.51.100.250"}) == 0
