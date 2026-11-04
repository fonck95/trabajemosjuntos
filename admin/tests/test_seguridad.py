"""Seguridad: límite de ingreso, IP detrás del proxy, sesiones, cuerpo antes de la sesión, auditoría, exportaciones,
reuniones y configuración. Solo personas inventadas."""
import asyncio
import io
import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone

import openpyxl
import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app import config
from app import db as bd
from app import seguridad as seg

CLAVE = "clave-de-prueba-larga"


def _login(c, usuario="admin", clave=CLAVE, ip=None, **headers):
    if ip:
        headers["X-Real-IP"] = ip
    return c.post("/api/login", json={"usuario": usuario, "clave": clave}, headers=headers)


# ───────────────────────────── Límite de intentos de ingreso ─────────────────────────────

def test_bloqueo_por_ip_no_alcanza_a_otra_ip(cliente):
    for _ in range(seg.MAX_POR_IP):
        assert _login(cliente, clave="mala", ip="203.0.113.10").status_code == 401
    r = _login(cliente, ip="203.0.113.10")
    assert r.status_code == 429 and 0 < int(r.headers["retry-after"]) <= seg.VENTANA_S
    assert _login(cliente, ip="198.51.100.77").status_code == 200


def test_x_forwarded_for_falsificado_no_evade_el_limite(cliente):
    # Como en producción: uvicorn con --proxy-headers --forwarded-allow-ips=* copia a request.client el primer valor
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
    c = TestClient(ProxyHeadersMiddleware(cliente.app, trusted_hosts="*"))
    estados = [_login(c, clave="mala", **{"X-Forwarded-For": f"10.0.0.{i}, 203.0.113.9"}).status_code for i in range(7)]
    assert estados == [401] * seg.MAX_POR_IP + [429, 429]
    # X-Real-IP (la pone el borde de Railway) manda sobre X-Forwarded-For
    assert _login(c, **{"X-Real-IP": "198.51.100.5", "X-Forwarded-For": "203.0.113.9"}).status_code == 200


def test_bloqueo_global_no_deja_fuera_al_administrador(cliente):
    db = cliente.app.state.db
    # Muchos fallos desde muchas IPs: el administrador entra igual desde la suya
    for i in range(seg.MAX_GLOBAL):
        assert _login(cliente, clave="mala", ip=f"203.0.113.{i // seg.MAX_POR_IP + 1}").status_code == 401
    assert _login(cliente, ip="198.51.100.77").status_code == 200
    # Un ataque mucho mayor solo impone esperas cortas, nunca un bloqueo indefinido
    ahora = datetime.now(timezone.utc)
    db.intentos.insert_many([{"ip": f"ataque-{i}", "ts": ahora, "ok": False} for i in range(500)])
    db.intentos.update_one({"_id": "freno_global"}, {"$set": {"hasta": ahora - timedelta(seconds=1)}})
    assert _login(cliente, clave="mala", ip="192.0.2.1").status_code == 401  # toma el turno
    r = _login(cliente, ip="198.51.100.77")
    assert r.status_code == 429 and 0 < int(r.headers["retry-after"]) <= seg.ESPERA_MAX_S
    db.intentos.update_one({"_id": "freno_global"}, {"$set": {"hasta": datetime.now(timezone.utc) - timedelta(seconds=1)}})
    assert _login(cliente, ip="198.51.100.77").status_code == 200


def test_rafaga_en_paralelo_no_pasa_del_limite_por_ip(cliente, monkeypatch):
    from app.api import sistema
    comprobar = sistema.credenciales_validas

    def lenta(*args):
        time.sleep(0.2)  # ensancha la ventana entre contar los fallos y registrar el intento
        return comprobar(*args)

    monkeypatch.setattr(sistema, "credenciales_validas", lenta)
    n = 20
    barrera = threading.Barrier(n)
    estados = []

    def intento():
        barrera.wait()
        estados.append(_login(cliente, clave="mala", ip="192.0.2.50").status_code)

    hilos = [threading.Thread(target=intento) for _ in range(n)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert len(estados) == n and set(estados) <= {401, 429}
    assert estados.count(401) <= seg.MAX_POR_IP
    assert cliente.app.state.db.intentos.count_documents({"ip": "192.0.2.50", "ok": False}) == estados.count(401)


def _req(headers, client=("10.1.1.1", 1234)):
    return Request({"type": "http", "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
                    "client": client})


def test_ip_del_cliente_detras_del_proxy():
    assert seg.ip_de(_req({"X-Real-IP": "198.51.100.7", "X-Forwarded-For": "10.0.0.1, 198.51.100.7"})) == "198.51.100.7"
    assert seg.ip_de(_req({"X-Forwarded-For": "10.0.0.1, 203.0.113.9"})) == "203.0.113.9"
    assert seg.ip_de(_req({"X-Real-IP": "<script>", "X-Forwarded-For": "texto libre"})) == "10.1.1.1"
    assert seg.ip_de(_req({})) == "10.1.1.1"
    assert seg._clave_ip("2001:db8:1:2:3:4:5:6") == seg._clave_ip("2001:db8:1:2:ffff::1") == "2001:db8:1:2::/64"
    assert seg._clave_ip("::ffff:192.0.2.1") == "192.0.2.1" and seg._clave_ip("testclient") == "testclient"


# ───────────────────────────── Sesiones ─────────────────────────────

def test_cambiar_usuario_o_clave_cierra_las_sesiones(sesion, cfg):
    from app.main import crear_app
    token = sesion.cookies.get(seg.COOKIE)
    cookie = {"Cookie": f"{seg.COOKIE}={token}"}
    otra = crear_app(config.Config(usuario="otro_admin", clave="clave-nueva-totalmente-distinta", mongodb_uri=cfg.mongodb_uri,
                                   mongodb_db=cfg.mongodb_db, horas_sesion=1, cookie_segura=False, max_subida_mb=5))
    misma = crear_app(cfg)
    try:
        c = TestClient(otra)
        assert c.get("/api/yo", headers=cookie).status_code == 401
        assert c.get("/api/personas", headers=cookie).status_code == 401
        assert c.get("/api/exportar.xlsx", headers=cookie).status_code == 401
        assert TestClient(misma).get("/api/yo", headers=cookie).status_code == 200  # misma credencial: sigue
        with TestClient(otra):  # al arrancar con la credencial nueva se borran las sesiones viejas
            pass
        assert sesion.app.state.db.sesiones.count_documents({}) == 0
    finally:
        otra.state.cliente.close()
        misma.state.cliente.close()


# ───────────────────────────── Cuerpo de la petición ─────────────────────────────

def _asgi(app, metodo, ruta, headers, partes):
    """Llama a la aplicación ASGI y cuenta cuántas partes del cuerpo leyó antes de responder."""
    partes, leidas, res = list(partes), [], {}

    async def receive():
        leidas.append(1)
        if partes:
            return {"type": "http.request", "body": partes.pop(0), "more_body": bool(partes)}
        return {"type": "http.disconnect"}

    async def send(msg):
        if msg["type"] == "http.response.start":
            res.setdefault("estado", msg["status"])
            res.setdefault("leidas", len(leidas))

    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": metodo, "scheme": "http",
             "path": ruta, "raw_path": ruta.encode(), "query_string": b"", "root_path": "", "client": ("203.0.113.50", 1),
             "server": ("testserver", 80), "headers": [(k.encode(), v.encode()) for k, v in headers.items()]}
    asyncio.run(app(scope, receive, send))
    return res["estado"], res["leidas"]


def test_sin_sesion_no_se_lee_la_subida(cliente):
    cuerpo = (b'--xx\r\nContent-Disposition: form-data; name="archivos"; filename="a.xlsx"\r\n\r\n' + b"0" * 4000
              + b"\r\n--xx--\r\n")
    partes = [cuerpo[i:i + 1000] for i in range(0, len(cuerpo), 1000)]
    h = {"content-type": "multipart/form-data; boundary=xx", "content-length": str(len(cuerpo))}
    assert _asgi(cliente.app, "POST", "/api/importar", h, partes) == (401, 0)
    # Una subida que anuncia más del máximo se rechaza sin leerla
    h["content-length"] = str(10 << 30)
    assert _asgi(cliente.app, "POST", "/api/importar", h, partes) == (413, 0)


def test_json_enorme_se_rechaza_antes_de_leerlo(cliente):
    h = {"content-type": "application/json", "content-length": str(300 << 20)}
    assert _asgi(cliente.app, "POST", "/api/login", h, [b'{"usuario":"a","clave":"b"}']) == (413, 0)
    assert _asgi(cliente.app, "POST", "/api/personas", h, [b"{}"]) == (413, 0)


def test_limite_del_cuerpo_con_sesion(sesion):
    grande = b'{"titulo": "' + b"x" * 300_000 + b'"}'
    assert sesion.post("/api/reuniones", content=grande, headers={"content-type": "application/json"}).status_code == 413
    # Por partes y sin Content-Length también se corta
    r = sesion.post("/api/reuniones", content=iter([grande[:200_000], grande[200_000:]]),
                    headers={"content-type": "application/json"})
    assert r.status_code == 413
    assert sesion.post("/api/reuniones", json={"titulo": "Normal", "fecha": "2026-01-01"}).status_code == 201


# ───────────────────────────── Auditoría del ingreso fallido ─────────────────────────────

def test_ingreso_fallido_no_guarda_lo_escrito_como_usuario(cliente):
    assert _login(cliente, usuario=CLAVE, clave="admin").status_code == 401  # la clave en el campo usuario
    assert _login(cliente, clave="otra-mala").status_code == 401
    assert _login(cliente).status_code == 200
    filas = [f for f in cliente.get("/api/auditoria").json()["filas"] if f["accion"] == "ingreso_fallido"]
    assert len(filas) == 2 and CLAVE not in json.dumps(filas)
    assert sorted((f["usuario"], json.loads(f["detalle"])["usuario_correcto"]) for f in filas) == [
        ("admin", True), ("desconocido", False)]
    # Los registros anteriores se limpian al arrancar
    db = cliente.app.state.db
    db.auditoria.insert_one({"ts": bd.ahora(), "usuario": "texto-viejo", "accion": "ingreso_fallido"})
    seg.limpiar_al_iniciar(db, cliente.app.state.cfg)
    assert db.auditoria.count_documents({"usuario": "texto-viejo"}) == 0
    assert db.auditoria.count_documents({"accion": "ingreso_fallido", "usuario": "admin"}) == 1


# ───────────────────────────── Exportaciones ─────────────────────────────

def _persona(c, nombre, **extra):
    r = c.post("/api/personas", json={"nombre": nombre, "forzar": True, **extra})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _nombres_xlsx(contenido):
    ws = openpyxl.load_workbook(io.BytesIO(contenido)).active
    return [f[1] for f in ws.iter_rows(min_row=2, values_only=True)]


def test_exportaciones_excluyen_a_quien_no_autorizo(sesion):
    db = sesion.app.state.db
    reu = sesion.post("/api/reuniones", json={"titulo": "Reunion inventada", "fecha": "2026-10-01"}).json()["id"]
    _persona(sesion, "Teodulfo Inventado Ramirez", reunion_id=reu)
    negada = _persona(sesion, "Gumersinda Ficticia Pardo", reunion_id=reu)
    db.personas.update_one({"_id": negada}, {"$set": {"consentimiento": "no"}})
    nombres = _nombres_xlsx(sesion.get("/api/exportar.xlsx").content)
    assert "TEODULFO INVENTADO RAMIREZ" in nombres and "GUMERSINDA FICTICIA PARDO" not in nombres
    nombres = _nombres_xlsx(sesion.get("/api/exportar.xlsx", params={"incluir_sin_autorizacion": 1}).content)
    assert "GUMERSINDA FICTICIA PARDO" in nombres
    csv = sesion.get(f"/api/reuniones/{reu}/asistentes.csv").text
    assert "TEODULFO" in csv and "GUMERSINDA" not in csv
    assert "GUMERSINDA" in sesion.get(f"/api/reuniones/{reu}/asistentes.csv", params={"incluir_sin_autorizacion": 1}).text


def test_exportar_con_caracteres_de_control(sesion):
    db = sesion.app.state.db
    clave = sesion.post("/api/campos", json={"etiqueta": "=Campo raro", "tipo": "texto"}).json()["clave"]
    pid = _persona(sesion, "Eleuterio Inventado Mora")
    db.personas.update_one({"_id": pid}, {"$set": {"ocupacion": "pesca\x01dor", "direccion": "Calle 1\x0b# 2-3",
                                                   f"extra.{clave}": "\x02=1+1"}})
    r = sesion.get("/api/exportar.xlsx")
    assert r.status_code == 200
    ws = openpyxl.load_workbook(io.BytesIO(r.content)).active
    filas = list(ws.iter_rows(values_only=True))
    cab, fila = filas[0], next(f for f in filas if f[1] == "ELEUTERIO INVENTADO MORA")
    assert cab[-1] == "'=Campo raro"
    assert fila[cab.index("Ocupación")] == "pescador" and fila[cab.index("Dirección original")] == "Calle 1# 2-3"
    assert fila[-1] == "'=1+1"


# ───────────────────────────── Reuniones ─────────────────────────────

def test_reunion_no_acepta_titulo_ni_fecha_nulos(sesion):
    reu = sesion.post("/api/reuniones", json={"titulo": "Reunion inventada", "fecha": "2026-10-01"}).json()["id"]
    _persona(sesion, "Teodulfo Inventado Ramirez", reunion_id=reu)
    for cambio in ({"fecha": None}, {"titulo": None}, {"titulo": "   "}, {"titulo": None, "fecha": "2026-10-02"}):
        assert sesion.patch(f"/api/reuniones/{reu}", json=cambio).status_code == 422, cambio
    assert sesion.post("/api/reuniones", json={"titulo": "   ", "fecha": "2026-10-01"}).status_code == 422
    r = sesion.get(f"/api/reuniones/{reu}").json()
    assert r["titulo"] == "Reunion inventada" and r["fecha"] == "2026-10-01"
    assert sesion.get(f"/api/reuniones/{reu}/asistentes.csv").status_code == 200
    assert sesion.patch(f"/api/reuniones/{reu}", json={"titulo": "  Nuevo titulo  "}).json()["titulo"] == "Nuevo titulo"


def test_reunion_con_solo_barrio_guarda_el_lugar(sesion):
    db = sesion.app.state.db
    a, b = list(db.lugares.find({}, {"nombre": 1}).sort("_id", 1).limit(2))
    reu = sesion.post("/api/reuniones", json={"titulo": "Reunion inventada", "fecha": "2026-10-01",
                                              "lugar_id": a["_id"], "lugar_texto": None}).json()
    assert reu["lugar_texto"] == a["nombre"]
    pid = _persona(sesion, "Teodulfo Inventado Ramirez", reunion_id=reu["id"])
    assert sesion.get(f"/api/personas/{pid}").json()["reuniones"][0]["lugar_texto"] == a["nombre"]
    # Al cambiar el barrio, el sitio que era su nombre cambia con él; un sitio escrito se conserva
    assert sesion.patch(f"/api/reuniones/{reu['id']}", json={"lugar_id": b["_id"]}).json()["lugar_texto"] == b["nombre"]
    otra = sesion.post("/api/reuniones", json={"titulo": "Otra inventada", "fecha": "2026-10-02", "lugar_id": a["_id"],
                                               "lugar_texto": "Caseta comunal"}).json()
    assert otra["lugar_texto"] == "Caseta comunal"


def test_nuevos_de_cada_reunion(sesion):
    db = sesion.app.state.db
    a = sesion.post("/api/reuniones", json={"titulo": "Reunion A", "fecha": "2026-10-01"}).json()["id"]
    b = sesion.post("/api/reuniones", json={"titulo": "Reunion B", "fecha": "2026-10-08"}).json()["id"]
    # Registrada en A y luego asistente en B: nueva solo en A
    pid = _persona(sesion, "Teodulfo Inventado Ramirez", reunion_id=a)
    assert sesion.post(f"/api/reuniones/{b}/asistentes", json={"persona_id": pid}).status_code == 201
    # Con reunion_origen manda ese campo, aunque haya asistido antes a otra
    doc = bd.nueva_persona(db, {"nombre": "GUMERSINDA FICTICIA PARDO"}, "reunion")
    doc["reunion_origen"] = b
    doc["asistencias"] = [{"reunion_id": a, "rol": None, "nota": None, "creado_en": "2026-01-01T00:00:00+00:00"},
                          {"reunion_id": b, "rol": None, "nota": None, "creado_en": "2026-02-01T00:00:00+00:00"}]
    db.personas.insert_one(doc)
    lista = {x["id"]: x for x in sesion.get("/api/reuniones").json()}
    assert (lista[a]["asistentes"], lista[a]["nuevos"]) == (2, 1)
    assert (lista[b]["asistentes"], lista[b]["nuevos"]) == (2, 1)


# ───────────────────────────── Configuración ─────────────────────────────

def _sin_variables(monkeypatch, *nombres):
    for n in nombres:  # setenv + delenv: al terminar la prueba la variable vuelve a no existir
        monkeypatch.setenv(n, "x")
        monkeypatch.delenv(n)


def test_env_ignora_comentarios_en_linea(tmp_path, monkeypatch):
    nombres = ["PRUEBA_HORAS", "PRUEBA_SEGURA", "PRUEBA_NUMERAL", "PRUEBA_COMILLAS", "PRUEBA_VACIA", "PRUEBA_SIMPLE"]
    _sin_variables(monkeypatch, *nombres)
    env = tmp_path / ".env"
    env.write_text("PRUEBA_HORAS=12      # duración de la sesión\n"
                   "PRUEBA_SEGURA=1\t# cookie solo por HTTPS\n"
                   "PRUEBA_NUMERAL=abc#def\n"
                   'PRUEBA_COMILLAS="con # adentro"   # comentario\n'
                   "PRUEBA_VACIA=   # nada\n"
                   "PRUEBA_SIMPLE='uno dos'\n", encoding="utf-8")
    config._cargar_env(env)
    import os
    assert [os.environ[n] for n in nombres] == ["12", "1", "abc#def", "con # adentro", "", "uno dos"]


def test_falta_mongodb_uri_en_railway(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(config, "RAIZ", tmp_path / "sin" / "admin")  # sin archivos .env
    _sin_variables(monkeypatch, "MONGODB_URI", "MONGO_URL", "MONGODB_URL", "RAILWAY_ENVIRONMENT",
                   "RAILWAY_ENVIRONMENT_NAME", "RAILWAY_ENVIRONMENT_ID", "SESSION_HOURS", "MAX_UPLOAD_MB", "COOKIE_SECURE")
    with caplog.at_level(logging.WARNING, logger="panel"):
        assert config.cargar().mongodb_uri == "mongodb://127.0.0.1:27017"  # en local: aviso y MongoDB local
    assert "MONGODB_URI" in caplog.text
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    with pytest.raises(RuntimeError, match="MONGODB_URI"):
        config.cargar()
    monkeypatch.setenv("MONGODB_URI", "mongodb://mongo.invalid:27017")
    monkeypatch.setenv("SESSION_HOURS", "doce")
    with pytest.raises(RuntimeError, match="SESSION_HOURS"):
        config.cargar()
