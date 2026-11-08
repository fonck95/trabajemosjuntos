"""La conexión del asistente con la cuenta de Mnemo del administrador (`app/agente/mnemo_conexion.py`,
`app/api/agente_mnemo.py`, `app/agente/cifrado.py`): OAuth 2.1 contra un Mnemo falso (`ayudas_mcp.OAuthFalso`, sin
red), los tokens cifrados, la renovación sin carreras, la revocación, el cliente MCP que sale de la conexión y lo que
ve el estado. Nunca se llama a Mnemo de verdad; solo datos inventados.

Qué se prueba: el descubrimiento (PRM, metadatos, recurso ajeno, http fuera de loopback, sin OAuth, por el 401), el
registro dinámico guardado y reutilizado (y otra vez ante `invalid_client`), la URL de autorización (S256, `resource`,
`scope`, la vuelta a Ajustes), la vuelta (state ajeno, de otra sesión, vencido o repetido, otro `iss`,
`access_denied`, el canje), que nada quede en claro en MongoDB ni en el registro, la auditoría, los permisos (el
coordinador y sin CSRF: 403), la renovación (20 a la vez, dos procesos, cancelación a mitad, `invalid_grant`, cambio
de clave del administrador, red caída), el 401 que renueva y repite, reconectar la misma cuenta u otra, y
desconectar."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from starlette.datastructures import State

from ayudas_agente import ALCANCES_PANEL, conectar_mnemo
from ayudas_g3 import coordinador
from ayudas_mcp import CUENTA, OTRA_CUENTA, OAuthFalso

from app import config, seguridad
from app.agente import cifrado
from app.agente import mnemo_cliente as mc
from app.agente import mnemo_conexion as mcx
from app.agente.herramientas.base import ErrorHerramienta

URL = "https://mnemo.example.org/mcp"
VUELTA = "http://testserver/ajustes"


def correr(coro):
    return asyncio.run(coro)


@pytest.fixture
def falso(sesion):
    """El Mnemo falso, con el transporte puesto en la aplicación de `sesion` (sin red)."""
    f = OAuthFalso()
    sesion.app.state.mnemo_transporte = f.transporte()
    return f


def _detalle(r) -> dict:
    return r.json()["detail"]


def _conectar(c, url: str | None = URL, **cab):
    return c.post("/api/agente/mnemo/conectar", json={} if url is None else {"url": url}, headers=cab or None)


def _consulta(url: str) -> dict:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def _doc(app) -> dict:
    return app.state.db.meta.find_one({"_id": mcx.ID}) or {}


def _tokens_guardados(app) -> dict:
    d = _doc(app)
    return cifrado.descifrar(seguridad.llave_mnemo(app.state.cfg), d["cifrado"],
                             f"mnemo_conexion|{d['emisor']}|{d['client_id']}")


def _conectado(c, falso) -> dict:
    """Conectar → la página de Mnemo (aprueba) → volver: la vista que responde `volver`."""
    r = _conectar(c)
    assert r.status_code == 200, r.text
    r = c.post("/api/agente/mnemo/volver", json=falso.seguir(r.json()["autorizar"]))
    assert r.status_code == 200, r.text
    return r.json()


def _app_de(app, falso) -> SimpleNamespace:
    """Otra «instancia» del panel sobre la misma base: sin la memoria del proceso (su propia `FuenteTokens`)."""
    return SimpleNamespace(state=State({"db": app.state.db, "cfg": app.state.cfg,
                                        "mnemo_transporte": falso.transporte()}))


async def _fallo(coro) -> ErrorHerramienta:
    with pytest.raises(ErrorHerramienta) as e:
        await coro
    return e.value


# ───────────────────────────── Conectar: descubrimiento y autorización ─────────────────────────────

def test_conectar_descubre_registra_y_arma_la_autorizacion(sesion, falso):
    r = _conectar(sesion)
    assert r.status_code == 200, r.text
    url = r.json()["autorizar"]
    assert url.startswith("https://mnemo.example.org/oauth/authorize?")
    q = _consulta(url)
    assert q["response_type"] == "code" and q["client_id"] in falso.clientes and q["redirect_uri"] == VUELTA
    assert q["code_challenge_method"] == "S256" and len(q["code_challenge"]) == 43 and len(q["state"]) >= 43
    assert q["resource"] == URL
    pedidos = q["scope"].split()
    assert pedidos[:4] == ["openid", "profile", "email", "mnemo:model"]
    assert set(pedidos[4:]) == {"mnemo:read", "mnemo:workspace.write", "mnemo:memory.write", "mnemo:share",
                                "mnemo:publish"}  # las de la lista blanca de herramientas/mnemo.py
    assert "mnemo:forms.responses" not in pedidos  # datos de otras personas: nunca
    assert [(p["metodo_http"], p["ruta"]) for p in falso.peticiones] == [
        ("GET", "/.well-known/oauth-protected-resource/mcp"), ("GET", "/.well-known/oauth-authorization-server"),
        ("POST", "/oauth/register")]
    assert falso.peticiones[-1]["json"] == {
        "client_name": "Panel Trabajemos juntos", "redirect_uris": [VUELTA],
        "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
        "token_endpoint_auth_method": "none"}
    # El pendiente: el hash del state, atado a la sesión, con el verificador cifrado (nada de eso en claro)
    doc = _doc(sesion.app)
    p = doc["pendiente"]
    sesion_h = hashlib.sha256(sesion.cookies.get(seguridad.COOKIE).encode()).hexdigest()
    assert p["state_h"] == hashlib.sha256(q["state"].encode()).hexdigest() and p["sesion"] == sesion_h
    assert p["client_id"] == q["client_id"] and p["redirect_uri"] == VUELTA and p["emisor"] == falso.base
    assert q["state"] not in json.dumps(doc, default=str)
    verificador = cifrado.descifrar(seguridad.llave_mnemo(sesion.app.state.cfg), p["verificador_cifrado"],
                                    f"mnemo_pendiente|{p['state_h']}")["v"]
    reto = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
    assert reto == q["code_challenge"] and verificador not in json.dumps(doc, default=str)
    assert doc["clientes"][0]["client_id"] == q["client_id"] and "estado" not in doc  # aún no hay conexión


def test_la_vuelta_lleva_el_origen_y_el_prefijo_de_la_peticion(sesion, falso):
    from starlette.requests import Request

    from app.api import agente_mnemo
    r = _conectar(sesion, host="127.0.0.1:8000")
    assert r.status_code == 200, r.text
    assert _consulta(r.json()["autorizar"])["redirect_uri"] == "http://127.0.0.1:8000/ajustes"
    # Dentro del sitio (servidor.py monta el panel en /panel) y detrás del proxy de Railway (https)
    scope = {"type": "http", "method": "POST", "scheme": "https", "server": ("panel.example.org", 443),
             "path": "/panel/api/agente/mnemo/conectar", "root_path": "/panel", "query_string": b"",
             "headers": [(b"host", b"panel.example.org")]}
    assert agente_mnemo._redirect_uri(Request(scope)) == "https://panel.example.org/panel/ajustes"


@pytest.mark.parametrize("url", ["http://mnemo.example.org/mcp", "ftp://mnemo.example.org/mcp", "mnemo",
                                 "https://usuario:clave@mnemo.example.org/mcp", "https://mnemo.example.org/mcp#x",
                                 "https://mnemo.example.org/mcp?x=1", "http://10.0.0.5/mcp", "javascript:alert(1)"])
def test_direcciones_que_no_sirven(sesion, falso, url):
    r = _conectar(sesion, url)
    assert r.status_code == 400 and _detalle(r)["codigo"] == "url" and falso.peticiones == []


def test_http_solo_de_loopback_y_solo_en_local(sesion, falso):
    falso.base = "http://127.0.0.1:9999"
    assert _conectar(sesion, "http://127.0.0.1:9999/mcp").status_code == 200
    sesion.app.state.cfg = replace(sesion.app.state.cfg, cookie_segura=True)  # detrás de HTTPS: solo https
    r = _conectar(sesion, "http://127.0.0.1:9999/mcp")
    assert r.status_code == 400 and _detalle(r)["codigo"] == "url"


def test_sin_direccion_usa_la_sugerida(sesion, falso):
    r = _conectar(sesion, None)
    assert r.status_code == 400 and _detalle(r) == {"codigo": "url", "mensaje": "Escriba la dirección MCP de Mnemo "
                                                                                 "(https://…/mcp)."}
    sesion.app.state.cfg = replace(sesion.app.state.cfg, mnemo_url=URL)
    r = _conectar(sesion, None)
    assert r.status_code == 200 and _consulta(r.json()["autorizar"])["resource"] == URL


def test_recurso_ajeno(sesion, falso):
    falso.prm_extra = {"resource": "https://otro.example.org/mcp"}
    r = _conectar(sesion)
    assert r.status_code == 400 and _detalle(r)["codigo"] == "recurso"
    assert "https://otro.example.org/mcp" in _detalle(r)["mensaje"]
    # Con una barra final es el mismo recurso, y se le manda a Mnemo tal como lo anuncia (lo compara exacto)
    falso.prm_extra = {"resource": URL + "/"}
    r = _conectar(sesion)
    assert r.status_code == 200 and _consulta(r.json()["autorizar"])["resource"] == URL + "/"


def test_mnemo_sin_oauth(sesion, falso):
    falso.prm_extra = {"authorization_servers": []}
    r = _conectar(sesion)
    assert r.status_code == 400 and _detalle(r) == {"codigo": "sin_oauth", "mensaje": "Mnemo no tiene OAuth: falta "
                                                                                      "PUBLIC_BASE_URL en su "
                                                                                      "despliegue."}


@pytest.mark.parametrize("extra", [{"issuer": "https://otro.example.org"},
                                   {"code_challenge_methods_supported": ["plain"]}, {"revocation_endpoint": None},
                                   {"registration_endpoint": None},
                                   {"token_endpoint": "https://otro.example.org/oauth/token"}])
def test_metadatos_que_no_sirven(sesion, falso, extra):
    falso.metadatos_extra = extra
    r = _conectar(sesion)
    assert r.status_code == 400 and _detalle(r)["codigo"] == "servidor"
    assert not any(p["ruta"] == "/oauth/register" for p in falso.peticiones)


def test_descubre_por_el_401_de_mcp(sesion, falso):
    """Sin el PRM en su lugar, el 401 de /mcp dice dónde está (`resource_metadata`, en el mismo origen)."""
    falso.forzar["/.well-known/oauth-protected-resource/mcp"] = (404, {"error": "not_found"})
    falso.ruta_prm = "/.well-known/oauth-protected-resource"
    r = _conectar(sesion)
    assert r.status_code == 200, r.text
    assert [(p["metodo_http"], p["ruta"]) for p in falso.peticiones][:3] == [
        ("GET", "/.well-known/oauth-protected-resource/mcp"), ("POST", "/mcp"),
        ("GET", "/.well-known/oauth-protected-resource")]
    falso.forzar["/.well-known/oauth-protected-resource"] = (404, {"error": "not_found"})
    r = _conectar(sesion)
    assert r.status_code == 400 and _detalle(r)["codigo"] == "descubrimiento"


def test_mnemo_no_responde(sesion, falso):
    falso.sin_red = {"/.well-known"}
    r = _conectar(sesion)
    assert r.status_code == 502 and _detalle(r)["codigo"] == "red"


def test_el_registro_se_guarda_y_se_reutiliza(sesion, falso):
    primero = _consulta(_conectar(sesion).json()["autorizar"])["client_id"]
    segundo = _consulta(_conectar(sesion).json()["autorizar"])["client_id"]
    assert primero == segundo and falso.registros == 1
    # Antes de reutilizarlo se comprueba que Mnemo lo conozca: un refresh inventado da invalid_grant si existe
    sonda = [p for p in falso.peticiones if p["ruta"] == "/oauth/token"]
    assert len(sonda) == 1 and sonda[0]["form"]["grant_type"] == "refresh_token"
    assert sonda[0]["form"]["client_id"] == primero and falso.renovaciones == 0


def test_otro_registro_si_mnemo_olvido_el_cliente(sesion, falso):
    primero = _consulta(_conectar(sesion).json()["autorizar"])["client_id"]
    falso.olvidar_clientes()  # Mnemo con el almacén en memoria, tras reiniciar: invalid_client
    segundo = _consulta(_conectar(sesion).json()["autorizar"])["client_id"]
    assert segundo != primero and falso.registros == 2 and segundo in falso.clientes
    clientes = _doc(sesion.app)["clientes"]
    assert [c["client_id"] for c in clientes] == [segundo]  # uno por (emisor, vuelta)


def test_registro_rechazado_por_mnemo(sesion, falso):
    falso.solo_loopback_http = True
    r = _conectar(sesion)
    assert r.status_code == 400 and _detalle(r)["codigo"] == "registro" and "loopback" in _detalle(r)["mensaje"]
    assert _conectar(sesion, host="127.0.0.1:8000").status_code == 200  # una vuelta de loopback sí la acepta


# ───────────────────────────── Volver ─────────────────────────────

def test_volver_conecta_sin_tokens_en_claro(sesion, falso, caplog):
    caplog.set_level(logging.DEBUG)
    panel = logging.getLogger("panel")
    panel.addHandler(caplog.handler)
    try:
        r = _conectar(sesion)
        vuelta = falso.seguir(r.json()["autorizar"])
        r = sesion.post("/api/agente/mnemo/volver", json=vuelta)
    finally:
        panel.removeHandler(caplog.handler)
    assert r.status_code == 200, r.text
    v = r.json()
    assert v == {"estado": "conectada", "motivo": None, "url": URL,
                 "cuenta": "Ana Inventada (ana.inventada@example.org)", "alcances": v["alcances"], "modelo": True,
                 "desde": v["desde"], "url_sugerida": URL}
    assert set(v["alcances"]) == {"mnemo:model", "mnemo:read", "mnemo:workspace.write", "mnemo:memory.write",
                                  "mnemo:share", "mnemo:publish"}
    assert datetime.fromisoformat(v["desde"]) > datetime.now(timezone.utc) - timedelta(minutes=1)
    # El canje: PKCE, la vuelta, el cliente y el recurso, en form-urlencoded
    canje = next(p for p in falso.peticiones if p["ruta"] == "/oauth/token")
    assert canje["tipo"].startswith("application/x-www-form-urlencoded")
    assert set(canje["form"]) == {"grant_type", "code", "redirect_uri", "client_id", "code_verifier", "resource"}
    assert canje["form"]["resource"] == URL and canje["form"]["redirect_uri"] == VUELTA
    # Ningún secreto en claro: ni en MongoDB, ni en el registro, ni en la respuesta
    secretos = [*falso.accesos, *falso.refrescos, vuelta["code"], vuelta["state"], canje["form"]["code_verifier"]]
    doc = _doc(sesion.app)
    guardado = json.dumps(doc, default=str)
    auditoria = json.dumps(list(sesion.app.state.db.auditoria.find({}, {"_id": 0})), default=str)
    for s in secretos:
        assert s not in guardado and s not in caplog.text and s not in r.text and s not in auditoria
    tokens = _tokens_guardados(sesion.app)
    assert falso.vigente(tokens["access"]) and tokens["refresh"] in falso.refrescos
    assert doc["pendiente"] is None and doc["estado"] == "conectada" and doc["cuenta"]["sub"] == CUENTA["sub"]
    assert doc["conectada_por"] == {"uid": 0, "usuario": "admin"} and doc["redirect_uri"] == VUELTA
    a = sesion.app.state.db.auditoria.find_one({"accion": "mnemo_conectar"})
    assert a["uid"] == 0 and a["rol"] == "admin"
    assert json.loads(a["detalle"]) == {"url": URL, "alcances": v["alcances"], "modelo": True,
                                        "reemplaza_otra": False}


def test_volver_con_state_ajeno_de_otra_sesion_vencido_o_repetido(sesion, falso, como):
    vuelta = falso.seguir(_conectar(sesion).json()["autorizar"])
    for cuerpo, cliente in (({**vuelta, "state": "un-state-inventado"}, sesion), (vuelta, como("admin"))):
        r = cliente.post("/api/agente/mnemo/volver", json=cuerpo)
        assert r.status_code == 400 and _detalle(r)["codigo"] == "estado"
    assert _doc(sesion.app)["pendiente"] is not None  # ni el state ajeno ni la otra sesión lo gastan
    sesion.app.state.db.meta.update_one({"_id": mcx.ID}, {"$set": {
        "pendiente.expira": datetime.now(timezone.utc) - timedelta(seconds=1)}})
    r = sesion.post("/api/agente/mnemo/volver", json=vuelta)
    assert r.status_code == 400 and _detalle(r)["codigo"] == "estado"
    # Otra vez, y la vuelta repetida (un doble clic, un reintento) no canjea dos veces el code
    vuelta = falso.seguir(_conectar(sesion).json()["autorizar"])
    assert sesion.post("/api/agente/mnemo/volver", json=vuelta).status_code == 200
    r = sesion.post("/api/agente/mnemo/volver", json=vuelta)
    assert r.status_code == 400 and _detalle(r)["codigo"] == "estado"
    assert sum(1 for p in falso.peticiones if p["ruta"] == "/oauth/token" and p["form"]["grant_type"]
               == "authorization_code") == 1
    assert not any(g["revocada"] for g in falso.concesiones.values())


def test_volver_de_otro_emisor(sesion, falso):
    vuelta = falso.seguir(_conectar(sesion).json()["autorizar"])
    r = sesion.post("/api/agente/mnemo/volver", json={**vuelta, "iss": "https://otro.example.org"})
    assert r.status_code == 400 and _detalle(r)["codigo"] == "emisor"
    vuelta = falso.seguir(_conectar(sesion).json()["autorizar"])
    sin_iss = {k: v for k, v in vuelta.items() if k != "iss"}  # Mnemo anuncia que siempre lo manda (RFC 9207)
    r = sesion.post("/api/agente/mnemo/volver", json=sin_iss)
    assert r.status_code == 400 and _detalle(r)["codigo"] == "emisor"
    assert not any(p["ruta"] == "/oauth/token" and p["form"]["grant_type"] == "authorization_code"
                   for p in falso.peticiones)


def test_volver_cuando_la_persona_cancela_en_mnemo(sesion, falso):
    falso.decision = "deny"
    vuelta = falso.seguir(_conectar(sesion).json()["autorizar"])
    assert vuelta["error"] == "access_denied" and "code" not in vuelta
    r = sesion.post("/api/agente/mnemo/volver", json=vuelta)
    assert r.status_code == 400 and _detalle(r) == {"codigo": "denegada", "mensaje": "Se canceló el permiso en "
                                                                                     "Mnemo: no se conectó nada."}
    assert sesion.post("/api/agente/mnemo/volver", json=vuelta).status_code == 400  # el pendiente ya se gastó
    assert mcx.vista(sesion.app.state.db)["estado"] == "sin_conectar"
    vuelta = falso.seguir(_conectar(sesion).json()["autorizar"])
    r = sesion.post("/api/agente/mnemo/volver", json={"state": vuelta["state"], "iss": vuelta["iss"],
                                                      "error": "invalid_target"})
    assert r.status_code == 400 and _detalle(r)["codigo"] == "autorizacion" and "invalid_target" in r.text


def test_un_codigo_que_mnemo_no_acepta(sesion, falso):
    vuelta = falso.seguir(_conectar(sesion).json()["autorizar"])
    r = sesion.post("/api/agente/mnemo/volver", json={**vuelta, "code": "un-codigo-inventado"})
    assert r.status_code == 400 and _detalle(r)["codigo"] == "canje"
    assert mcx.vista(sesion.app.state.db)["estado"] == "sin_conectar"


def test_solo_el_administrador_y_con_csrf(sesion, falso):
    k = coordinador(sesion.app, sesion.app.state.db)
    for r in (k.post("/api/agente/mnemo/conectar", json={"url": URL}),
              k.post("/api/agente/mnemo/volver", json={"state": "x"}), k.delete("/api/agente/mnemo")):
        assert r.status_code == 403 and _detalle(r)["codigo"] == "permiso"
    malo = {"X-CSRF-Token": "no-es-el-de-la-sesion"}
    for r in (sesion.post("/api/agente/mnemo/conectar", json={"url": URL}, headers=malo),
              sesion.post("/api/agente/mnemo/volver", json={"state": "x"}, headers=malo),
              sesion.delete("/api/agente/mnemo", headers=malo)):
        assert r.status_code == 403 and "CSRF" in r.text
    assert falso.peticiones == []


# ───────────────────────────── El estado ─────────────────────────────

def test_el_estado_muestra_la_conexion_al_administrador_y_al_coordinador(sesion, falso, como):
    e = sesion.get("/api/agente/estado").json()["mnemo"]
    assert e == {"activo": False, "origen": None, "conexion": {
        "estado": "sin_conectar", "motivo": None, "url": None, "cuenta": None, "alcances": [], "modelo": False,
        "desde": None, "url_sugerida": None}}
    sesion.app.state.cfg = replace(sesion.app.state.cfg, mnemo_url=URL)
    assert sesion.get("/api/agente/estado").json()["mnemo"]["conexion"]["url_sugerida"] == URL
    conectar_mnemo(sesion.app, falso=falso)
    e = sesion.get("/api/agente/estado").json()["mnemo"]
    assert e["activo"] is True and e["origen"] == "https://mnemo.example.org"
    assert e["conexion"]["estado"] == "conectada" and e["conexion"]["modelo"] is True
    k = coordinador(sesion.app, sesion.app.state.db).get("/api/agente/estado").json()["mnemo"]
    assert k["activo"] is False and k["conexion"]["estado"] == "conectada"  # lo ve, en solo lectura
    p = como("planillero").get("/api/agente/estado").json()["mnemo"]
    assert p == {"activo": False, "origen": None}


def test_vista_y_con_modelo(cliente):
    db = cliente.app.state.db
    assert mcx.con_modelo(db) is False and mcx.conectada(db) is None
    conectar_mnemo(cliente.app, alcances=("mnemo:read",))
    v = mcx.vista(db)
    assert v["estado"] == "conectada" and v["modelo"] is False and v["alcances"] == ["mnemo:read"]
    assert "url_sugerida" not in v and mcx.con_modelo(db) is False
    conectar_mnemo(cliente.app)
    assert mcx.con_modelo(db) is True and mcx.vista(db)["modelo"] is True
    c = mcx.conectada(db)
    assert c["url_mcp"] == URL and c["version"] == _doc(cliente.app)["version"] and c["conexion"]


# ───────────────────────────── Renovación ─────────────────────────────

def test_veinte_a_la_vez_una_sola_renovacion(cliente):
    app = cliente.app
    falso = conectar_mnemo(app, vence_en=60)  # le queda 1 minuto: se renueva al primer uso
    falso.demora = 0.3
    viejos = _tokens_guardados(app)
    version = _doc(app)["version"]
    fuente = mcx.FuenteTokens(app)

    async def prueba():
        return await asyncio.gather(*(fuente.token() for _ in range(20)))

    tokens = correr(prueba())
    assert len(set(tokens)) == 1 and tokens[0] != viejos["access"] and falso.vigente(tokens[0])
    assert falso.renovaciones == 1 and fuente.renovaciones == 1
    assert not any(g["revocada"] for g in falso.concesiones.values())
    doc = _doc(app)
    assert doc["version"] == version + 1 and doc["renovando_hasta"] is None and "renovador" not in doc
    nuevos = _tokens_guardados(app)
    assert nuevos["access"] == tokens[0] and nuevos["refresh"] != viejos["refresh"]  # el refresh rotó y se guardó
    assert correr(fuente.token()) == tokens[0] and falso.renovaciones == 1  # vigente: no se renueva otra vez


def test_dos_instancias_sin_memoria_compartida(cliente):
    app = cliente.app
    falso = conectar_mnemo(app, vence_en=60)
    falso.demora = 0.3
    a, b = mcx.FuenteTokens(_app_de(app, falso)), mcx.FuenteTokens(_app_de(app, falso))

    async def prueba():
        return await asyncio.gather(*(x.token() for x in (a, b) * 10))

    tokens = correr(prueba())
    assert len(set(tokens)) == 1 and falso.renovaciones == 1 and a.renovaciones + b.renovaciones == 1
    assert not any(g["revocada"] for g in falso.concesiones.values())


def test_cancelar_a_mitad_no_pierde_la_renovacion(cliente):
    """El turno se corta (el navegador se fue) mientras se renueva: con `shield` la renovación termina y se guarda;
    sin él, Mnemo rotaría y el panel no se enteraría (la siguiente sería una reutilización: concesión revocada)."""
    app = cliente.app
    falso = conectar_mnemo(app, vence_en=60)
    falso.demora = 0.5
    version = _doc(app)["version"]
    fuente = mcx.FuenteTokens(app)

    async def prueba():
        turno = asyncio.create_task(fuente.token())
        await asyncio.sleep(0.2)
        turno.cancel()
        with pytest.raises(asyncio.CancelledError):
            await turno
        await asyncio.sleep(0.7)
        return _doc(app), await fuente.token()

    doc, siguiente = correr(prueba())
    assert doc["version"] == version + 1 and falso.renovaciones == 1
    assert siguiente == _tokens_guardados(app)["access"] and falso.vigente(siguiente)
    assert not any(g["revocada"] for g in falso.concesiones.values())


def test_invalid_grant_deja_la_conexion_caida(sesion):
    app = sesion.app
    falso = conectar_mnemo(app, vence_en=60)
    for gid in falso.concesiones:  # el administrador la revocó en Mnemo (o venció, o se reusó)
        falso.revocar_concesion(gid)
    e = correr(_fallo(mcx.FuenteTokens(app).token()))
    assert e.codigo == mc.COD_TOKEN and e.mensaje == mc.MENSAJE_TOKEN and e.detalle == {"conexion": "revocada"}
    assert "MNEMO_TOKEN" not in e.mensaje and "Ajustes → Asistente" in e.mensaje
    doc = _doc(app)
    assert doc["estado"] == "caida" and doc["motivo"] == "revocada" and "cifrado" not in doc
    v = mcx.vista(app.state.db)
    assert v["estado"] == "caida" and v["motivo"] == "revocada" and v["modelo"] is False and v["url"] == URL
    a = app.state.db.auditoria.find_one({"accion": "mnemo_caida"})
    assert a["usuario"] == "sistema" and json.loads(a["detalle"]) == {"motivo": "revocada"}
    assert mc.cliente_de(app) is None and mcx.con_modelo(app.state.db) is False
    assert sesion.get("/api/agente/estado").json()["mnemo"]["activo"] is False
    e = correr(_fallo(mcx.FuenteTokens(app).token()))  # sin conexión ya no pide nada a Mnemo
    assert e.codigo == mc.COD_TOKEN and falso.renovaciones == 1


def test_cambio_de_clave_del_administrador_deja_la_conexion_caida(cliente):
    app = cliente.app
    conectar_mnemo(app)
    app.state.cfg = replace(app.state.cfg, clave="otra-clave-larga-inventada")  # cambió `password` en Railway
    e = correr(_fallo(mcx.FuenteTokens(app).token()))
    assert e.codigo == mc.COD_TOKEN and "cambió la clave del administrador" in e.mensaje
    v = mcx.vista(app.state.db)
    assert v["estado"] == "caida" and v["motivo"] == "clave" and "cifrado" not in _doc(app)
    e = correr(_fallo(mcx.FuenteTokens(app).token()))
    assert e.codigo == mc.COD_TOKEN and "cambió la clave" in e.mensaje and e.detalle == {"conexion": "clave"}


def test_sin_red_al_renovar_suelta_el_arriendo(cliente):
    app = cliente.app
    falso = conectar_mnemo(app, vence_en=60)
    falso.sin_red = {"/oauth/token"}
    fuente = mcx.FuenteTokens(app)
    e = correr(_fallo(fuente.token()))
    assert e.codigo == mc.COD_RED
    doc = _doc(app)
    assert doc["estado"] == "conectada" and doc["renovando_hasta"] is None and "renovador" not in doc
    falso.sin_red = set()
    assert falso.vigente(correr(fuente.token())) and falso.renovaciones == 1


def test_el_401_renueva_y_repite_una_sola_vez(cliente):
    app = cliente.app
    falso = conectar_mnemo(app)

    async def prueba():
        c = mc.cliente_de(app)
        primero = await c.llamar("search", {"query": "acta"})
        falso.vencer_accesos()  # Mnemo rechaza el access antes de lo que el panel creía
        segundo = await c.llamar("search", {"query": "otra"})
        for gid in falso.concesiones:
            falso.revocar_concesion(gid)
        falso.vencer_accesos()
        return primero, segundo, await _fallo(c.llamar("search", {"query": "y otra"}))

    primero, segundo, e = correr(prueba())
    assert primero["structuredContent"]["results"] and segundo["structuredContent"]["results"]
    assert falso.renovaciones == 2  # una por cada 401
    llamadas = [p for p in falso.mcp.peticiones if p["json"].get("method") == "tools/call"]
    assert len(llamadas) == 4  # 1 + (401 y la repetida) + (401, y no se repite: la conexión cayó al renovar)
    assert e.codigo == mc.COD_TOKEN and e.mensaje == mc.MENSAJE_TOKEN
    assert mcx.vista(app.state.db)["estado"] == "caida"


def test_cliente_de_sale_de_la_conexion_y_se_rehace_con_la_version(cliente):
    app = cliente.app
    assert mc.cliente_de(app) is None
    falso = conectar_mnemo(app, vence_en=60)
    c1 = mc.cliente_de(app)
    assert isinstance(c1, mc.ClienteMnemo) and c1.url == URL and isinstance(c1._fuente, mcx.FuenteTokens)
    assert mc.cliente_de(app) is c1 and app.state.mnemo_cliente is c1 and c1.version_conexion == _doc(app)["version"]
    correr(c1.llamar("search", {"query": "acta"}))  # renueva en el camino: sube la versión
    assert falso.renovaciones == 1
    c2 = mc.cliente_de(app)
    assert c2 is not c1 and c2.version_conexion == _doc(app)["version"] and c1._retirado
    assert correr(c1.llamar("search", {"query": "sigue sirviendo"}))["structuredContent"]  # un turno que ya lo tenía
    assert "Bearer" not in repr(c2) and "at_" not in repr(c2._fuente)
    app.state.db.meta.update_one({"_id": mcx.ID}, {"$set": {"estado": "caida", "motivo": "revocada"}})
    assert mc.cliente_de(app) is None


# ───────────────────────────── Reconectar y desconectar ─────────────────────────────

def test_reconectar_la_misma_cuenta_no_revoca(sesion, falso):
    _conectado(sesion, falso)
    viejos = _tokens_guardados(sesion.app)
    v = _conectado(sesion, falso)
    assert v["estado"] == "conectada" and falso.revocaciones == []
    nuevos = _tokens_guardados(sesion.app)
    assert nuevos["access"] != viejos["access"] and falso.vigente(nuevos["access"])
    assert falso.concesion_de(nuevos["access"]) is falso.concesion_de(viejos["access"])  # la misma concesión
    a = list(sesion.app.state.db.auditoria.find({"accion": "mnemo_conectar"}))
    assert len(a) == 2 and json.loads(a[-1]["detalle"])["reemplaza_otra"] is False


def test_conectar_otra_cuenta_revoca_la_anterior(sesion, falso):
    _conectado(sesion, falso)
    viejos = _tokens_guardados(sesion.app)
    falso.cuenta = dict(OTRA_CUENTA)
    v = _conectado(sesion, falso)
    assert v["cuenta"] == "Beto Inventado (beto.inventado@example.org)"
    assert falso.revocaciones == [{"token": viejos["refresh"], "token_type_hint": "refresh_token",
                                   "client_id": _doc(sesion.app)["client_id"], "tipo": "refresh"}]
    assert falso.concesion_de(viejos["access"])["revocada"] is True
    nuevos = _tokens_guardados(sesion.app)
    assert falso.vigente(nuevos["access"]) and falso.concesion_de(nuevos["access"])["cuenta"]["sub"] == \
        OTRA_CUENTA["sub"]
    a = sesion.app.state.db.auditoria.find_one({"accion": "mnemo_conectar"}, sort=[("_id", -1)])
    assert json.loads(a["detalle"])["reemplaza_otra"] is True


def test_desconectar_revoca_con_el_refresh(sesion, falso):
    _conectado(sesion, falso)
    tokens = _tokens_guardados(sesion.app)
    clientes = _doc(sesion.app)["clientes"]
    r = sesion.delete("/api/agente/mnemo")
    assert r.status_code == 200, r.text
    assert r.json() == {"estado": "sin_conectar", "motivo": None, "url": None, "cuenta": None, "alcances": [],
                        "modelo": False, "desde": None, "url_sugerida": URL, "revocada": True}
    assert falso.revocaciones == [{"token": tokens["refresh"], "token_type_hint": "refresh_token",
                                   "client_id": clientes[0]["client_id"], "tipo": "refresh"}]  # nunca con el access
    g = falso.concesion_de(tokens["refresh"])
    assert g["revocada"] is True and g["zombi"] is False and not falso.vigente(tokens["access"])
    doc = _doc(sesion.app)
    assert "cifrado" not in doc and "estado" not in doc and doc["clientes"] == clientes
    a = sesion.app.state.db.auditoria.find_one({"accion": "mnemo_desconectar"})
    assert a["uid"] == 0 and json.loads(a["detalle"]) == {"url": URL, "revocada": True}
    assert mc.cliente_de(sesion.app) is None
    r = sesion.delete("/api/agente/mnemo")
    assert r.status_code == 200 and r.json()["revocada"] is None and len(falso.revocaciones) == 1


def test_desconectar_sin_red_avisa_que_no_se_revoco(sesion, falso):
    _conectado(sesion, falso)
    falso.sin_red = {"/oauth/revoke"}
    r = sesion.delete("/api/agente/mnemo")
    assert r.status_code == 200 and r.json()["revocada"] is False and r.json()["estado"] == "sin_conectar"


def test_desconectar_una_conexion_caida(sesion, falso):
    conectar_mnemo(sesion.app, falso=falso)
    sesion.app.state.db.meta.update_one({"_id": mcx.ID}, {"$set": {"estado": "caida", "motivo": "clave"},
                                                          "$unset": {"cifrado": ""}})
    r = sesion.delete("/api/agente/mnemo")
    assert r.status_code == 200 and r.json()["revocada"] is None and r.json()["estado"] == "sin_conectar"
    assert falso.revocaciones == []  # sin tokens no hay nada que revocar desde el panel
    a = sesion.app.state.db.auditoria.find_one({"accion": "mnemo_desconectar"})
    assert json.loads(a["detalle"]) == {"url": URL, "revocada": None}


def test_desconectar_espera_a_la_renovacion_en_vuelo(cliente):
    """Si otro proceso está renovando, desconectar espera a que termine y revoca el refresh nuevo (revocar el viejo,
    ya rotado, dejaría viva la concesión con el nuevo)."""
    app = cliente.app
    falso = conectar_mnemo(app, vence_en=60)
    falso.demora = 0.5
    fuente = mcx.FuenteTokens(_app_de(app, falso))
    quien = SimpleNamespace(uid=0, usuario="admin", rol="admin", ip=None)

    async def prueba():
        renovacion = asyncio.create_task(fuente.token())
        await asyncio.sleep(0.2)  # ya tomó el arriendo y le pidió a Mnemo
        fuera = await mcx.desconectar(app, quien)
        return fuera, await asyncio.gather(renovacion, return_exceptions=True)

    fuera, (renovado,) = correr(prueba())
    assert fuera["revocada"] is True and falso.renovaciones == 1
    assert falso.revocaciones[-1]["token"] in falso.refrescos and not falso.refrescos[
        falso.revocaciones[-1]["token"]]["usado"]  # se revocó el refresh vigente, el que dejó la renovación
    assert all(g["revocada"] for g in falso.concesiones.values()) and not falso.vigente(renovado)


# ───────────────────────────── Cifrado y configuración ─────────────────────────────

def test_cifrado_aes_gcm(cfg):
    llave = seguridad.llave_mnemo(cfg)
    otra = seguridad.llave_mnemo(replace(cfg, clave="otra-clave-larga-inventada"))
    datos = {"access": "at_" + "x" * 43, "refresh": "rt_" + "y" * 43}
    texto = cifrado.cifrar(llave, datos, "mnemo_conexion|e|c")
    assert cifrado.descifrar(llave, texto, "mnemo_conexion|e|c") == datos
    assert cifrado.cifrar(llave, datos, "x") != cifrado.cifrar(llave, datos, "x")  # nonce aleatorio
    assert "x" * 43 not in texto
    assert cifrado.descifrar(otra, texto, "mnemo_conexion|e|c") is None  # cambiaron ADMIN o password
    assert cifrado.descifrar(llave, texto, "mnemo_conexion|e|otro") is None  # otra conexión
    crudo = bytearray(base64.urlsafe_b64decode(texto))
    crudo[20] ^= 1
    assert cifrado.descifrar(llave, base64.urlsafe_b64encode(bytes(crudo)).decode(), "mnemo_conexion|e|c") is None
    for basura in ("basura", "", None, 7, "A" * 100_000):
        assert cifrado.descifrar(llave, basura, "mnemo_conexion|e|c") is None


def test_la_llave_no_es_la_huella_de_las_sesiones(cfg):
    llave = seguridad.llave_mnemo(cfg)
    assert len(llave) == 32 and llave.hex() != seguridad.huella(cfg) and llave != seguridad._llave(cfg.usuario,
                                                                                                    cfg.clave)
    assert seguridad.llave_mnemo(replace(cfg, usuario="otro")) != llave
    assert seguridad.llave_mnemo(replace(cfg, clave="otra-clave-larga-inventada")) != llave


def _sin_variables(monkeypatch, *nombres):
    for n in nombres:
        monkeypatch.delenv(n, raising=False)


def test_mnemo_token_se_ignora_y_mnemo_modelo_se_valida(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(config, "RAIZ", tmp_path / "sin" / "admin")  # sin archivos .env
    _sin_variables(monkeypatch, "MNEMO_TOKEN", "MNEMO_MODELO", "MNEMO_MCP_URL", "MONGODB_URI", "MONGO_URL",
                   "MONGODB_URL", "RAILWAY_ENVIRONMENT", "RAILWAY_ENVIRONMENT_NAME", "RAILWAY_ENVIRONMENT_ID")
    monkeypatch.setenv("MONGODB_URI", "mongodb://127.0.0.1:27017")
    monkeypatch.setenv("MNEMO_TOKEN", "mnemo_pat_" + "z" * 40)
    with caplog.at_level(logging.WARNING, logger="panel"):
        cfg = config.cargar()
    assert "MNEMO_TOKEN ya no se usa" in caplog.text and "z" * 40 not in caplog.text
    assert not hasattr(cfg, "mnemo_token") and not hasattr(cfg, "mnemo_configurado")
    assert cfg.mnemo_modelo == "" and "z" * 40 not in repr(cfg)
    for valor, esperado in (("principal", "principal"), (" Ligero ", "ligero"), ("anthropic/claude-x-1", "anthropic/"
                                                                                                         "claude-x-1"),
                            ("openrouter/meta/llama-9:free", "openrouter/meta/llama-9:free"), ("", ""),
                            ("solo-un-nombre", ""), ("con espacios/modelo", ""), ("/sin-proveedor", ""),
                            ("p/" + "m" * 200, "")):
        monkeypatch.setenv("MNEMO_MODELO", valor)
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="panel"):
            assert config.cargar().mnemo_modelo == esperado, valor
        assert ("MNEMO_MODELO" in caplog.text) == (esperado == "" and valor.strip() != "")
