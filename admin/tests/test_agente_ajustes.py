"""Ajustes del asistente (docs/agente.md): valores por defecto, validación estricta, mezcla parcial, quién los cambia
(solo el administrador; el coordinador los ve en solo lectura), el permiso `agente.usar` de planilleros y consultores,
que el asistente aplica lo guardado (`agente.politica`, `GET /api/agente/estado`), que lo escrito a mano en la base se
ve como su valor por defecto y que bajar la retención acorta las conversaciones que ya existen. Y la conexión con
Mnemo en la vista: sus textos y que solo el administrador ve los botones (el coordinador, el estado; el servidor le
responde 403).

Solo datos inventados. Nunca se llama a Anthropic ni a Mnemo: `encender` pone una clave inventada, el estado no habla
con el modelo y `conectar_mnemo` guarda una conexión con un Mnemo falso."""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ayudas_agente import encender
from ayudas_g3 import coordinador
from app import acceso, modelo
from app.agente import conversaciones as conv_db
from app.agente import politica
from app.api import ajustes as api_ajustes

AGENTE = {"roles": ["admin", "coordinador"], "escritura": True, "mnemo_coordinadores": False, "retencion_dias": 30}
MENSAJES = {"admin": 300, "coordinador": 150, "planillero": 40, "consultor": 40}
AJUSTES_JS = Path(__file__).resolve().parents[1] / "web" / "js" / "vistas" / "ajustes.js"


def _es_permiso(r):
    return r.status_code == 403 and isinstance(r.json()["detail"], dict) and r.json()["detail"]["codigo"] == "permiso"


def _guardado(db) -> dict:
    return db.meta.find_one({"_id": "ajustes"}) or {}


@pytest.fixture
def coord(sesion):
    k = coordinador(sesion.app, sesion.app.state.db)
    yield k
    k.close()


# ───────────────────────────── Valores por defecto y reglas ─────────────────────────────

def test_valores_por_defecto(sesion):
    a = modelo.AJUSTES_POR_DEFECTO
    assert a["agente"] == AGENTE and a["agente_mensajes_diarios"] == MENSAJES
    # Denegar por defecto: planilleros y consultores no lo usan hasta que el administrador los agrega; la lista va
    # ordenada como la deja la validación (si no, reenviarla igual contaría como un cambio)
    assert a["agente"]["roles"] == sorted(set(a["agente"]["roles"])) and not {"planillero", "consultor"} & set(
        a["agente"]["roles"])
    assert set(a["agente_mensajes_diarios"]) == acceso.ROLES
    # Lo que el asistente usa si falta el ajuste es lo mismo que muestra Ajustes, con los mismos rangos
    assert politica.POR_DEFECTO == AGENTE and politica.MENSAJES_POR_DEFECTO == MENSAJES
    assert api_ajustes.RETENCION_DIAS == politica.RETENCION_DIAS
    assert api_ajustes.MENSAJES_DIARIOS == politica.MENSAJES_DIARIOS
    # La validación acepta exactamente las claves de los valores por defecto
    assert set(api_ajustes.Agente.model_fields) == set(AGENTE)
    assert set(api_ajustes.MensajesAgente.model_fields) == set(MENSAJES)
    v = sesion.get("/api/ajustes").json()
    assert v["agente"] == AGENTE and v["agente_mensajes_diarios"] == MENSAJES
    assert {"agente", "agente_mensajes_diarios"} <= set(v["ajustes_de_permisos"])
    assert politica.leer(sesion.app.state.db)[1] == AGENTE


def test_permiso_agente_usar_y_ajustes_de_permisos():
    for rol in ("planillero", "consultor"):
        q = acceso.Quien(uid=5, usuario=f"{rol}5", rol=rol, permisos=acceso.PERMISOS[rol])
        assert q.puede("agente.usar"), rol
    for rol, uid in (("admin", 0), ("coordinador", 7)):
        assert acceso.Quien(uid=uid, usuario=rol, rol=rol, permisos=acceso.PERMISOS[rol]).puede("agente.usar"), rol
    assert not acceso.Quien(uid=9, usuario="x", rol="jefe").puede("agente.usar")  # rol desconocido: nada
    assert {"agente", "agente_mensajes_diarios"} <= acceso.AJUSTES_DE_PERMISOS
    defecto = json.loads(json.dumps(modelo.AJUSTES_POR_DEFECTO))  # una copia, como la que da leer_ajustes
    assert acceso.ajustes_de_permisos(defecto, {"agente": {"escritura": False}}) == ["agente"]
    assert acceso.ajustes_de_permisos(defecto, {"agente_mensajes_diarios": {"planillero": 5}}) == [
        "agente_mensajes_diarios"]
    # Reenviar lo vigente (o solo una parte) no es un cambio
    assert acceso.ajustes_de_permisos(defecto, {"agente": dict(AGENTE), "agente_mensajes_diarios": dict(MENSAJES)}) == []
    assert acceso.ajustes_de_permisos(defecto, {"agente": {"roles": ["admin", "coordinador"]}}) == []


# ───────────────────────────── Guardar ─────────────────────────────

def test_guardar_mezcla_parcial_sin_borrar_hermanos(sesion):
    c, db = sesion, sesion.app.state.db
    r = c.put("/api/ajustes", json={"agente": {"escritura": False}})
    assert r.status_code == 200, r.text
    assert r.json()["agente"] == {**AGENTE, "escritura": False}
    assert r.json()["agente_mensajes_diarios"] == MENSAJES
    # El objeto se guarda entero: un segundo PUT de otra clave del mismo objeto no pierde el primero
    a = c.put("/api/ajustes", json={"agente": {"retencion_dias": 90}}).json()
    assert a["agente"] == {**AGENTE, "escritura": False, "retencion_dias": 90}
    assert _guardado(db)["agente"] == {**AGENTE, "escritura": False, "retencion_dias": 90}
    # El tope de un rol no borra el de los demás
    a = c.put("/api/ajustes", json={"agente_mensajes_diarios": {"planillero": 5}}).json()
    assert a["agente_mensajes_diarios"] == {**MENSAJES, "planillero": 5}
    assert a["agente"] == {**AGENTE, "escritura": False, "retencion_dias": 90}
    # Los roles quedan ordenados y sin repetidos
    a = c.put("/api/ajustes", json={"agente": {"roles": ["planillero", "admin", "admin"]}}).json()
    assert a["agente"]["roles"] == ["admin", "planillero"] and _guardado(db)["agente"]["roles"] == ["admin", "planillero"]
    # Los extremos de cada rango valen, y la lista vacía apaga el asistente para todos
    a = c.put("/api/ajustes", json={"agente": {"roles": [], "retencion_dias": 365, "mnemo_coordinadores": True},
                                    "agente_mensajes_diarios": {"admin": 5000, "consultor": 1}}).json()
    assert a["agente"] == {"roles": [], "escritura": False, "mnemo_coordinadores": True, "retencion_dias": 365}
    assert a["agente_mensajes_diarios"] == {**MENSAJES, "planillero": 5, "admin": 5000, "consultor": 1}
    # Lo que rige es lo guardado: el asistente lo lee así
    aj, agente = politica.leer(db)
    assert agente == a["agente"] and politica.mensajes_diarios(aj, "planillero") == 5
    # Cada cambio queda en la auditoría (solo los nombres de los campos); reenviar lo mismo no audita nada
    auds = list(db.auditoria.find({"accion": "ajustes"}))
    assert len(auds) == 5 and all(a["uid"] == 0 for a in auds)
    assert "agente_mensajes_diarios" in auds[-1]["detalle"] and "5000" not in auds[-1]["detalle"]
    r = c.put("/api/ajustes", json={"agente": a["agente"], "agente_mensajes_diarios": a["agente_mensajes_diarios"]})
    assert r.status_code == 200 and db.auditoria.count_documents({"accion": "ajustes"}) == 5


def test_valores_invalidos_422(sesion):
    c, db = sesion, sesion.app.state.db
    cuerpos = [
        # roles: solo los cuatro del panel, en una lista
        {"agente": {"roles": ["todos"]}}, {"agente": {"roles": ["Admin"]}}, {"agente": {"roles": "admin"}},
        {"agente": {"roles": [1]}}, {"agente": {"roles": ["admin"] * 5}}, {"agente": {"roles": {"admin": True}}},
        # booleanos estrictos: ni textos ni números
        {"agente": {"escritura": "si"}}, {"agente": {"escritura": "true"}}, {"agente": {"escritura": 1}},
        {"agente": {"mnemo_coordinadores": "true"}}, {"agente": {"mnemo_coordinadores": 0}},
        # retención: entero de 1 a 365
        {"agente": {"retencion_dias": 0}}, {"agente": {"retencion_dias": 366}}, {"agente": {"retencion_dias": -1}},
        {"agente": {"retencion_dias": 30.5}}, {"agente": {"retencion_dias": True}}, {"agente": {"retencion_dias": "30"}},
        # claves que no existen, también anidadas, y formas que no son un objeto
        {"agente": {"desconocido": 1}}, {"agente": {"mensajes_diarios": {"admin": 5}}}, {"agente": "si"},
        {"agente": ["admin"]}, {"agente": True},
        # mensajes por día: entero de 1 a 5000, por rol conocido
        {"agente_mensajes_diarios": {"admin": 0}}, {"agente_mensajes_diarios": {"admin": 5001}},
        {"agente_mensajes_diarios": {"planillero": -1}}, {"agente_mensajes_diarios": {"supervisor": 5}},
        {"agente_mensajes_diarios": {"consultor": "40"}}, {"agente_mensajes_diarios": {"admin": True}},
        {"agente_mensajes_diarios": {"coordinador": 2.5}}, {"agente_mensajes_diarios": 40},
        {"agente_mensajes_diarios": [40]},
        # una clave inválida tumba todo el cuerpo: nada se guarda a medias
        {"agente": {"escritura": False}, "agente_mensajes_diarios": {"admin": 0}},
    ]
    for cuerpo in cuerpos:
        r = c.put("/api/ajustes", json=cuerpo)
        assert r.status_code == 422, (cuerpo, r.status_code, r.text[:200])
    aj = modelo.leer_ajustes(db)
    assert aj["agente"] == AGENTE and aj["agente_mensajes_diarios"] == MENSAJES
    assert "agente" not in _guardado(db) and db.auditoria.count_documents({"accion": "ajustes"}) == 0
    # null no cambia nada (como en los demás ajustes del PUT parcial)
    r = c.put("/api/ajustes", json={"agente": None, "agente_mensajes_diarios": {"admin": None}})
    assert r.status_code == 200 and r.json()["agente"] == AGENTE and "agente" not in _guardado(db)


# ───────────────────────────── Quién los cambia ─────────────────────────────

def test_solo_el_administrador_los_cambia_y_el_coordinador_los_ve(sesion, coord):
    db = sesion.app.state.db
    a = coord.get("/api/ajustes")
    assert a.status_code == 200
    a = a.json()
    assert a["puede_modificar_permisos"] is False
    assert a["agente"] == AGENTE and a["agente_mensajes_diarios"] == MENSAJES
    assert {"agente", "agente_mensajes_diarios"} <= set(a["ajustes_de_permisos"])
    for cuerpo, campos in (({"agente": {"roles": ["admin"]}}, ["agente"]),
                           ({"agente": {"mnemo_coordinadores": True}}, ["agente"]),  # no se da Mnemo a sí mismo
                           ({"agente": {"retencion_dias": 365}}, ["agente"]),
                           ({"agente_mensajes_diarios": {"coordinador": 5000}}, ["agente_mensajes_diarios"]),
                           ({"agente": {"escritura": False}, "agente_mensajes_diarios": {"planillero": 1}},
                            ["agente", "agente_mensajes_diarios"])):
        r = coord.put("/api/ajustes", json=cuerpo)
        assert _es_permiso(r), (cuerpo, r.status_code, r.text[:200])
        assert r.json()["detail"]["campos"] == campos
    # Reenviar lo que ve (el formulario entero), o los mismos roles en otro orden, no es un cambio: 200
    r = coord.put("/api/ajustes", json={"agente": a["agente"], "agente_mensajes_diarios": a["agente_mensajes_diarios"]})
    assert r.status_code == 200, r.text
    assert coord.put("/api/ajustes", json={"agente": {"roles": ["coordinador", "admin"]}}).status_code == 200
    aj = modelo.leer_ajustes(db)
    assert aj["agente"] == AGENTE and aj["agente_mensajes_diarios"] == MENSAJES
    assert db.auditoria.count_documents({"accion": "ajustes"}) == 0
    # El administrador sí
    r = sesion.put("/api/ajustes", json={"agente": {"mnemo_coordinadores": True}})
    assert r.status_code == 200 and r.json()["agente"]["mnemo_coordinadores"] is True
    assert coord.get("/api/ajustes").json()["agente"]["mnemo_coordinadores"] is True


def test_planillero_y_consultor_no_ven_ni_cambian_los_ajustes(sesion, como):
    for rol in ("planillero", "consultor"):
        u = como(rol)
        assert _es_permiso(u.get("/api/ajustes")), rol
        assert _es_permiso(u.put("/api/ajustes", json={"agente": {"roles": ["admin", rol]}})), rol
        assert _es_permiso(u.put("/api/ajustes", json={"agente_mensajes_diarios": {rol: 5000}})), rol
        assert "agente.usar" in u.get("/api/yo").json()["permisos"], rol
    assert modelo.leer_ajustes(sesion.app.state.db)["agente"] == AGENTE


# ───────────────────────────── El asistente los aplica ─────────────────────────────

def test_el_asistente_aplica_lo_guardado(sesion, como, coord):
    encender(sesion.app)  # una clave inventada: el estado no llama al modelo
    p, c = como("planillero"), como("consultor")
    e = p.get("/api/agente/estado").json()
    assert e["disponible"] is False and e["motivo"] == "rol"  # tiene el permiso, pero su rol no está habilitado
    assert c.get("/api/agente/estado").json()["motivo"] == "rol"
    assert coord.get("/api/agente/estado").json()["disponible"] is True
    r = sesion.put("/api/ajustes", json={"agente": {"roles": ["admin", "coordinador", "planillero"]},
                                         "agente_mensajes_diarios": {"planillero": 12}})
    assert r.status_code == 200, r.text
    e = p.get("/api/agente/estado").json()
    assert e["disponible"] is True and e["motivo"] is None and e["limite"]["maximo"] == 12
    assert c.get("/api/agente/estado").json()["motivo"] == "rol"
    # Sin escritura, el estado lo dice (el widget no ofrece cambios)
    sesion.put("/api/ajustes", json={"agente": {"escritura": False}})
    assert p.get("/api/agente/estado").json()["escritura"] is False
    # Sin ningún rol, se apaga para todos, también para el administrador
    sesion.put("/api/ajustes", json={"agente": {"roles": []}})
    for cli in (sesion, coord, p):
        assert cli.get("/api/agente/estado").json()["motivo"] == "rol"


def test_lo_guardado_a_mano_se_ve_como_rige_y_se_limpia_al_guardar(sesion, coord):
    db = sesion.app.state.db
    db.meta.update_one({"_id": "ajustes"}, {"$set": {
        "agente": {"roles": "todos", "escritura": "si", "retencion_dias": 9999, "de_otra_version": 1},
        "agente_mensajes_diarios": {"admin": -3, "otro_rol": 9}}}, upsert=True)
    a = sesion.get("/api/ajustes").json()
    assert a["agente"] == AGENTE and a["agente_mensajes_diarios"] == MENSAJES  # lo que de verdad aplica el asistente
    # El coordinador reenvía lo que ve sin un 403: para él no cambia nada
    r = coord.put("/api/ajustes", json={"agente": a["agente"], "agente_mensajes_diarios": a["agente_mensajes_diarios"]})
    assert r.status_code == 200, r.text
    # Al guardar una parte, el objeto entero queda limpio
    sesion.put("/api/ajustes", json={"agente": {"escritura": False}})
    assert _guardado(db)["agente"] == {**AGENTE, "escritura": False}
    sesion.put("/api/ajustes", json={"agente_mensajes_diarios": {"admin": 10}})
    assert _guardado(db)["agente_mensajes_diarios"] == {**MENSAJES, "admin": 10}


# ───────────────────────────── Retención ─────────────────────────────

def _conversacion(db, cid: int, hace_dias: float, dias: int, n_mensajes: int = 2) -> None:
    """Una conversación inventada cuyo último mensaje fue hace `hace_dias`, renovada entonces con `dias` de
    retención (como lo deja cada turno: la conversación y sus mensajes con la misma fecha de borrado)."""
    ultimo = datetime.now(timezone.utc) - timedelta(days=hace_dias)
    expira = ultimo + timedelta(days=dias)
    db[conv_db.CONVERSACIONES].insert_one({"_id": cid, "uid": 0, "titulo": "Conversación inventada", "personas": [],
                                           "creada": ultimo, "actualizada": ultimo, "expira": expira})
    db[conv_db.MENSAJES].insert_many([{"conversacion": cid, "uid": 0, "seq": i + 1, "rol": "user", "replay": True,
                                       "ts": ultimo, "expira": expira} for i in range(n_mensajes)])


def _expira(db, cid: int) -> tuple[datetime | None, set[datetime]]:
    """La fecha de borrado de la conversación (None si ya no está: el monitor TTL de MongoDB pasa cada minuto y puede
    haber borrado una vencida) y las de sus mensajes."""
    conv = db[conv_db.CONVERSACIONES].find_one({"_id": cid})
    return (conv or {}).get("expira"), {m["expira"] for m in db[conv_db.MENSAJES].find({"conversacion": cid})}


def test_bajar_la_retencion_acorta_las_conversaciones_que_ya_existen(sesion):
    db = sesion.app.state.db
    ahora = datetime.now(timezone.utc)
    _conversacion(db, 1, hace_dias=20, dias=30)   # vence en 10 días; con 7, ya venció
    _conversacion(db, 2, hace_dias=2, dias=30)    # vence en 28 días; con 7, en 5
    _conversacion(db, 3, hace_dias=1, dias=3)     # vence en 2 días: ya es más corta que 7, no se toca
    antes3 = _expira(db, 3)[0]
    r = sesion.put("/api/ajustes", json={"agente": {"retencion_dias": 7}})
    assert r.status_code == 200, r.text
    e1, m1 = _expira(db, 1)
    e2, m2 = _expira(db, 2)
    # Vencida: el índice TTL la borra con sus mensajes (lo que todavía no haya borrado, vencido y con la misma fecha)
    assert all(x < ahora for x in m1) and (e1 is None or (e1 < ahora and m1 <= {e1}))
    assert abs(e2 - (ahora + timedelta(days=5))) < timedelta(minutes=1) and m2 == {e2}
    assert _expira(db, 3) == (antes3, {antes3})
    aud = db.auditoria.find_one({"accion": "ajustes"})
    assert '"conversaciones_acortadas": 2' in aud["detalle"]
    # Subirla no alarga lo que ya existe (cada turno renueva con el plazo vigente)
    assert sesion.put("/api/ajustes", json={"agente": {"retencion_dias": 365}}).status_code == 200
    assert _expira(db, 2) == (e2, {e2})
    assert "conversaciones_acortadas" not in db.auditoria.find_one({"accion": "ajustes"}, sort=[("_id", -1)])["detalle"]


# ───────────────────────────── La vista de Ajustes ─────────────────────────────

def test_la_vista_de_ajustes_tiene_la_seccion_del_asistente():
    """La sección «Asistente» de Ajustes manda lo que valida el servidor: los cuatro roles, los mismos rangos, y el
    coordinador la ve en solo lectura."""
    js = AJUSTES_JS.read_text(encoding="utf-8")
    assert 'id="f-agente"' in js and "<h2>Asistente</h2>" in js
    roles = re.search(r"const ROLES_AGENTE = \[(.*?)\];", js, re.S)
    assert roles and set(re.findall(r"\['(\w+)', '", roles.group(1))) == acceso.ROLES
    solo_lectura = re.search(r"for \(const id of \[([^\]]*)\]\)", js)
    assert solo_lectura and "'#f-agente'" in solo_lectura.group(1)
    assert f"'Días que se guardan las conversaciones', {api_ajustes.RETENCION_DIAS[0]}, " \
           f"{api_ajustes.RETENCION_DIAS[1]})" in js
    assert f"`Mensajes por día · ${{t}}`, {api_ajustes.MENSAJES_DIARIOS[0]}, {api_ajustes.MENSAJES_DIARIOS[1]})" in js
    for clave in ("agente: { roles, escritura:", "mnemo_coordinadores:", "retencion_dias: Number(",
                  "agente_mensajes_diarios: Object.fromEntries("):
        assert clave in js, clave


# ───────────────────────────── La conexión con Mnemo ─────────────────────────────

def test_la_conexion_con_mnemo_en_la_vista_de_ajustes():
    """El bloque «Conexión con Mnemo» de Ajustes → Asistente: el estado, la cuenta y los permisos para el administrador
    y el coordinador; la dirección y los botones (conectar, volver a conectar y desconectar, con confirmación) solo
    para quien puede conectar. Los textos hablan de la cuenta de Mnemo, no de tokens ni de variables."""
    js = AJUSTES_JS.read_text(encoding="utf-8")
    bloque = js[js.index("function bloqueMnemo("):js.index("export async function vistaAjustes(")]
    # Quién actúa lo dice el permiso `agente.conectar` (solo del administrador: el coordinador lo tiene en `excepto`)
    assert "const admin = puede('agente.conectar');" in bloque
    rama_admin = bloque[bloque.index("if (admin) {"):bloque.index("} else {\n    acciones")]
    for texto in ("'Conectar con Mnemo'", "'Volver a conectar'", ">Desconectar</button>", 'id="f-mnemo"',
                  "Dirección MCP de Mnemo", 'id="mnemo-conectar"', 'id="mnemo-desconectar"'):
        assert texto in rama_admin and bloque.count(texto) == 1, texto
    assert "Solo el administrador conecta o desconecta Mnemo." in bloque[bloque.index("} else {\n    acciones"):]
    # Los tres estados y el aviso sin permiso para usar los modelos
    for texto in ("Conectado como <b>", ">Sin conectar<", ">Conexión caída<", "if (!c.modelo) partes.push(",
                  "data-estado=\"${estado}\""):
        assert texto in bloque, texto
    assert ("const SIN_PERMISO_MODELO = 'Mnemo se conectó sin permiso para usar sus modelos: vuelva a conectar y "
            "marque esa casilla '") in js
    assert ("Todos los roles que usan el asistente gastan los modelos y los créditos de esa cuenta; los mensajes por "
            "día de cada rol (abajo) siguen valiendo.") in bloque
    # El bloque va fuera del formulario de los ajustes (no son ajustes: el coordinador los ve en solo lectura)
    seccion = js[js.index("<h2>Asistente</h2>"):js.index('<form id="f-agente"')]
    assert "bloqueMnemo(est.mnemo.conexion, nota)" in seccion and "estadoAgente(est)" in seccion
    # Desconectar pide confirmación antes de llamar a la API
    desconectar = js[js.index("async function desconectarMnemo("):js.index("function horario(")]
    assert "peligro: true" in desconectar
    assert desconectar.index("await confirmar(") < desconectar.index("api.del('/api/agente/mnemo')")
    # Ni tokens ni variables; el aviso legal nombra a Mnemo y al proveedor de la cuenta (y a Anthropic en modo directo)
    assert "token" not in js.lower() and "ANTHROPIC_API_KEY" not in js and "MNEMO_" not in js
    assert "con la cuenta de Mnemo del administrador: lo que hagan allá queda a nombre del administrador" in js
    legal = js[js.index('<div class="aviso-legal ancho">Lo que el asistente consulta'):]
    assert ("a Mnemo y, de ahí, al proveedor de modelos que esa cuenta tenga elegido; en modo directo, a "
            "Anthropic") in legal


def test_quien_conecta_mnemo_y_que_ve_cada_rol(sesion, coord, como):
    """La vista muestra los botones con `puede('agente.conectar')`: el administrador lo tiene; el coordinador lo tiene en
    `excepto` (ve el estado sin botones) y el servidor le responde 403 si lo intenta. Planilleros y consultores ni ven
    Ajustes ni reciben la conexión en el estado."""
    from ayudas_agente import conectar_mnemo
    yo_a, yo_k = sesion.get("/api/yo").json(), coord.get("/api/yo").json()
    assert "agente.conectar" not in (yo_a.get("excepto") or []) and "*" in yo_a["permisos"]
    assert "agente.conectar" in yo_k["excepto"] and "*" in yo_k["permisos"]
    # Los dos reciben la conexión en el estado, con lo que pinta la vista
    claves = {"estado", "motivo", "url", "cuenta", "alcances", "modelo", "desde", "url_sugerida"}
    for c in (sesion, coord):
        con = c.get("/api/agente/estado").json()["mnemo"]["conexion"]
        assert claves <= set(con) and con["estado"] == "sin_conectar" and con["modelo"] is False, con
    p = como("planillero")
    assert "conexion" not in p.get("/api/agente/estado").json()["mnemo"]
    # Conectada: la cuenta, los permisos y si puede usar los modelos (lo que la vista muestra)
    conectar_mnemo(sesion.app)
    con = coord.get("/api/agente/estado").json()["mnemo"]["conexion"]
    assert con["estado"] == "conectada" and con["cuenta"] == "Ana Inventada (ana.inventada@example.org)", con
    assert con["modelo"] is True and "mnemo:model" in con["alcances"] and con["desde"]
    # El coordinador no conecta, no termina una conexión ni desconecta: 403 permiso, y la conexión sigue
    for r in (coord.post("/api/agente/mnemo/conectar", json={}), coord.delete("/api/agente/mnemo"),
              coord.post("/api/agente/mnemo/volver", json={"state": "inventado"})):
        assert _es_permiso(r), (r.status_code, r.text[:200])
    assert sesion.get("/api/agente/estado").json()["mnemo"]["conexion"]["estado"] == "conectada"
