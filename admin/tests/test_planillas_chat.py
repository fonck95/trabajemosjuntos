"""Las planillas físicas en el chat (área B2): `/api/agente/estado` anuncia las fotos (`adjuntos`), un mensaje lleva
los ids de fotos de la bandeja de quien escribe (comprobados: nunca las de otra persona), el modelo recibe un bloque
de texto con sus ids tras el contexto (nunca la imagen ni un bloque de texto vacío) y el historial las muestra al
repintar. Turnos completos con la Messages API simulada: leer → cotejar → cargar sin que el modelo reciba una cédula o
un teléfono entero de la planilla, y lo que pasa al cargar filas «No autoriza» (la conversación se borra si alguien
retira su autorización; si no, sigue). Solo personas y fotos inventadas."""
import json
from types import SimpleNamespace

from pydantic import BaseModel

import ayudas_agente as aa
from app.agente import bucle, proveedores
from app.agente import conversaciones as conv_db
from app.agente.herramientas.base import Herramienta, Resultado
from ayudas_agente import T, TU, decidir, ndjson, sse
from ayudas_g3 import autorizada, coordinador, persona
from ayudas_planillas import fila, lectura_json
from ayudas_planillas_chat import foto_distinta, leer_con, roles_planillas, subir_sin_leer

CED = {n: f"9005100{n}" for n in range(1, 8)}
TEL = {n: f"310777000{n}" for n in range(1, 8)}
NACIMIENTO, OBSERVACION = "1988-03-14", "Cuida a su madre inventada"
ENTEROS = (*CED.values(), *TEL.values(), NACIMIENTO, OBSERVACION)
ADJUNTOS = {"max_por_mensaje": 4, "lado_max": 2576, "calidad": 0.8, "max_bytes": 1_500_000}


def _filas():
    return [
        fila(1, cedula=CED[1], cedula_repetida=CED[1], tipo_documento="CC", nombre="ANA INVENTADA CHAT",
             celular=TEL[1], otro_telefono=TEL[6], sexo="F", fecha_nacimiento=NACIMIENTO, direccion="CALLE CHAT 1",
             barrio="CENTRO", autorizacion="si", medio="escrito", canales="llamada", mayor_18="si",
             observaciones=OBSERVACION),
        fila(2, cedula=CED[2], nombre="BETO INVENTADO CHAT", celular=TEL[2], direccion="CALLE CHAT 2"),
        fila(3, cedula=CED[3], nombre="CARLA INVENTADA CHAT", celular=TEL[3], dudosos=["celular"]),
        fila(5, tipo_documento="TI", cedula=CED[5], nombre="ELSA INVENTADA CHAT", celular=TEL[5], edad="16"),
    ]


def _enviar(c, texto="", adjuntos=(), conversacion=None):
    r = c.post("/api/agente/mensajes", json={"conversacion": conversacion, "texto": texto, "adjuntos": list(adjuntos)})
    return r, (ndjson(r.text) if r.status_code == 200 else [])


def _de(eventos, tipo):
    return [e for e in eventos if e["tipo"] == tipo]


def _sin_enteros(texto: str) -> None:
    for v in ENTEROS:
        assert v not in texto, v


def _todo_lo_enviado(api) -> str:
    return json.dumps([p["json"] for p in api.peticiones], ensure_ascii=False)


def _todo_lo_guardado(db) -> str:
    return json.dumps(list(db[conv_db.MENSAJES].find({}, {"_id": 0})), ensure_ascii=False, default=str)


def _agente_para(db, *roles):
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"agente": {"roles": list(roles)}}}, upsert=True)


# ───────────────────────────── El estado y el mensaje ─────────────────────────────

def test_el_estado_anuncia_las_fotos_segun_el_rol_y_el_proveedor(sesion, como, monkeypatch):
    app, db = sesion.app, sesion.app.state.db
    assert sesion.get("/api/agente/estado").json()["adjuntos"] is None  # sin modelo
    aa.encender(app)
    assert sesion.get("/api/agente/estado").json()["adjuntos"] == ADJUNTOS
    with monkeypatch.context() as m:  # con Mnemo, el lado mayor que admite
        m.setattr(proveedores, "clave_para_nueva", lambda cfg, db_: "mnemo")
        assert sesion.get("/api/agente/estado").json()["adjuntos"] == {**ADJUNTOS, "lado_max": 2000}
    roles_planillas(app, "coordinador")
    assert sesion.get("/api/agente/estado").json()["adjuntos"] is None
    k = coordinador(app, db)
    assert k.get("/api/agente/estado").json()["adjuntos"] == ADJUNTOS
    # El planillero: con el asistente y su rol en `agente_planillas.roles`
    _agente_para(db, "admin", "coordinador", "planillero", "consultor")
    p, c = como("planillero"), como("consultor")
    assert p.get("/api/agente/estado").json()["adjuntos"] is None
    roles_planillas(app, "admin", "coordinador", "planillero")
    assert p.get("/api/agente/estado").json()["adjuntos"] == ADJUNTOS
    assert c.get("/api/agente/estado").json()["adjuntos"] is None
    _agente_para(db, "admin", "coordinador")  # sin el asistente, tampoco
    assert p.get("/api/agente/estado").json()["adjuntos"] is None


def test_mensajes_con_fotos_que_no_se_aceptan(sesion, como, monkeypatch):
    app, db = sesion.app, sesion.app.state.db
    aa.encender(app)  # sin guion: un turno que llegara a correr fallaría
    k = coordinador(app, db)
    de_k = subir_sin_leer(k, monkeypatch)
    mia = subir_sin_leer(sesion, monkeypatch, foto_distinta(1))
    for cuerpo in ({"texto": "", "adjuntos": []}, {"texto": "   "}, {"adjuntos": ["no-es-un-id"]},
                   {"texto": "hola", "adjuntos": [f"{i:032x}" for i in range(5)]}, {"adjuntos": "x" * 32}):
        assert sesion.post("/api/agente/mensajes", json=cuerpo).status_code == 422, cuerpo
    # La foto de otra persona (aunque quien escribe sea el administrador) o una que no existe: igual que si no estuviera
    for ids in ([de_k], [mia, de_k], ["f" * 32]):
        r, _ = _enviar(sesion, "Revísala", ids)
        assert r.status_code == 422 and r.json()["detail"]["codigo"] == "fotos", r.text
    assert db[conv_db.CONVERSACIONES].count_documents({}) == 0 and conv_db.uso_de(db, 0) == 0
    # Con el rol fuera de `agente_planillas.roles`, ni las suyas
    roles_planillas(app, "coordinador")
    r, _ = _enviar(sesion, "Revísala", [mia])
    assert r.status_code == 403 and r.json()["detail"]["codigo"] == "planillas_apagado"
    assert db[conv_db.CONVERSACIONES].count_documents({}) == 0


def test_un_mensaje_con_solo_fotos(cliente, sesion, monkeypatch):
    app, db = sesion.app, sesion.app.state.db
    api = aa.encender(app, sse(T("Veo que la foto se está leyendo.")), sse(T("Sigue igual.")))
    pid = subir_sin_leer(sesion, monkeypatch)
    r, ev = _enviar(sesion, "", [pid, pid])  # repetida: una sola
    assert r.status_code == 200, r.text
    inicio = _de(ev, "inicio")[0]
    assert inicio["titulo"] == "Fotos de planillas" and ev[-1] == {"tipo": "fin", "motivo": "listo",
                                                                   "limite": ev[-1]["limite"]}
    contenido = api.peticiones[0]["json"]["messages"][0]["content"]
    assert [b["type"] for b in contenido] == ["text", "text", "text"]
    assert contenido[0]["text"].startswith("<contexto_del_panel>")
    assert contenido[1]["text"].startswith("<fotos_adjuntas>") and f"- {pid}: se está leyendo" in contenido[1]["text"]
    assert "1 foto " in contenido[1]["text"] and "leer_planilla" in contenido[1]["text"]
    assert contenido[2] == {"type": "text", "text": bucle.SOLO_FOTOS}
    assert all(b["text"].strip() for b in contenido)  # nunca un bloque de texto vacío
    guardado = db[conv_db.MENSAJES].find_one({"rol": "user"})
    assert guardado["texto"] == "" and guardado["adjuntos"] == [{"id": pid, "ancho": 1200, "alto": 900}]
    cid = inicio["conversacion"]
    vista = sesion.get(f"/api/agente/conversaciones/{cid}").json()
    assert vista["mensajes"][0] == {"rol": "usuario", "texto": "", "adjuntos": [{"id": pid, "ancho": 1200,
                                                                               "alto": 900}]}
    # El mensaje siguiente, sin fotos: el anterior se reenvía igual (el prefijo no cambia) y el nuevo es el de siempre
    r, ev = aa.enviar(sesion, "¿Y ahora?", conversacion=cid)
    assert r.status_code == 200, r.text
    mensajes = api.peticiones[1]["json"]["messages"]
    assert mensajes[0]["content"] == contenido
    assert [b["type"] for b in mensajes[-1]["content"]] == ["text", "text"]
    assert mensajes[-1]["content"][1] == {"type": "text", "text": "¿Y ahora?"}
    assert sesion.get(f"/api/agente/conversaciones/{cid}").json()["mensajes"][-2] == {"rol": "usuario",
                                                                                      "texto": "¿Y ahora?"}


# ───────────────────────────── Turnos completos ─────────────────────────────

def test_leer_cotejar_y_cargar_sin_datos_enteros_al_modelo(cliente, sesion, monkeypatch):
    app, db = sesion.app, sesion.app.state.db
    beto = persona(db, nombre="BETO INVENTADO CHAT", cedula=CED[2], direccion="CALLE VIEJA 7")
    api = aa.encender(app)
    pid = subir_sin_leer(sesion, monkeypatch)
    leer_con(cliente, monkeypatch, pid, lectura_json(_filas()))
    # 1. La persona manda la foto; el modelo la lee
    api.agregar(sse(TU("toolu_l", "leer_planilla", {"ids": [pid]}), stop="tool_use"),
                sse(T("Leí 4 filas: la 3 tiene el celular dudoso.")))
    r, ev = _enviar(sesion, "Revisa esta planilla, por favor", [pid])
    assert r.status_code == 200, r.text
    cid = _de(ev, "inicio")[0]["conversacion"]
    assert [e["estado"] for e in _de(ev, "herramienta")] == ["inicio", "ok"]
    fotos = api.peticiones[0]["json"]["messages"][0]["content"][1]["text"]
    assert f"- {pid}: leída: 4 filas, 1 con dudas, 4 por cargar" in fotos
    resultado = api.peticiones[1]["json"]["messages"][-1]["content"][0]
    assert resultado["type"] == "tool_result" and "···001" in resultado["content"] and "ANA INVENTADA" in \
        resultado["content"]
    assert db[conv_db.CONVERSACIONES].find_one({"_id": cid})["con_datos"] is True
    # 2. Coteja y propone la carga con la corrección que dictó la persona
    api.agregar(sse(TU("toolu_c", "cotejar_planilla", {"id": pid}), stop="tool_use"),
                sse(TU("toolu_g", "cargar_planilla", {"id": pid, "folio": "Caja 4, folio 2", "correcciones": [
                    {"fila": 3, "campo": "celular", "valor": "3107770033"}]}), stop="tool_use"))
    r, ev = aa.enviar(sesion, "El celular de la fila 3 es 3107770033. Cotéjala y cárgala.", conversacion=cid)
    assert r.status_code == 200, r.text
    assert ev[-1]["motivo"] == "confirmacion"
    (tarjeta,) = _de(ev, "confirmar")
    detalle = dict(tarjeta["detalle"])
    # La tarjeta (para quien aprueba) muestra los valores enteros
    assert CED[1] in json.dumps(tarjeta, ensure_ascii=False) and detalle["Folio del papel"] == "Caja 4, folio 2"
    assert any(k == f"Fila 2 · Completa la ficha #{beto}" for k in detalle)
    assert "✎ corregido por el asistente: celular" in detalle["Fila 3 · Nueva"]
    assert beto in db[conv_db.CONVERSACIONES].find_one({"_id": cid})["personas"]
    # 3. La aprueba: se carga con el importador
    api.agregar(sse(T("Listo: cargué las 4 filas.")))
    r, ev = decidir(sesion, cid, toolu_g=True)
    assert r.status_code == 200, r.text
    assert [e["estado"] for e in _de(ev, "herramienta")] == ["aprobada", "ok"] and ev[-1]["motivo"] == "listo"
    ana = db.personas.find_one({"cedula": CED[1]})
    assert ana and db.importaciones.count_documents({"fotos_sha256": {"$size": 1}}) == 1
    assert "3107770033" in json.dumps(db.personas.find_one({"cedula": CED[3]}).get("telefonos"), default=str)
    conv = db[conv_db.CONVERSACIONES].find_one({"_id": cid})
    assert conv["pendiente"] is None and {ana["_id"], beto} <= set(conv["personas"])
    assert db.planillas.find_one({"_id": pid})["estado"] == "cargada"  # sin foto ni lectura
    # Nada de la planilla entera llegó al modelo ni quedó en el historial
    _sin_enteros(_todo_lo_enviado(api))
    _sin_enteros(_todo_lo_guardado(db))


def test_cargar_filas_que_retiran_la_autorizacion_borra_la_conversacion(cliente, sesion, monkeypatch):
    app, db = sesion.app, sesion.app.state.db
    dario = persona(db, nombre="DARIO INVENTADO CHAT", cedula=CED[4], telefono="3109990444")
    autorizada(db, dario)
    api = aa.encender(app)
    pid = subir_sin_leer(sesion, monkeypatch)
    leer_con(cliente, monkeypatch, pid, lectura_json([
        fila(1, cedula=CED[1], nombre="ANA INVENTADA CHAT", celular=TEL[1]),
        fila(4, cedula=CED[4], nombre="DARIO INVENTADO CHAT", celular=TEL[4], autorizacion="no")]))
    # Sin filas, primero las que no están en «no»
    api.agregar(sse(TU("toolu_1", "cargar_planilla", {"id": pid}), stop="tool_use"))
    r, ev = _enviar(sesion, "Carga la planilla", [pid])
    cid = _de(ev, "inicio")[0]["conversacion"]
    (tarjeta,) = _de(ev, "confirmar")
    assert [k for k, _ in tarjeta["detalle"] if k.startswith("Fila")] == ["Fila 1 · Nueva"]
    api.agregar(sse(T("Cargué la fila 1. La 4 dice que no autoriza: va aparte.")))
    r, ev = decidir(sesion, cid, toolu_1=True)
    assert ev[-1]["motivo"] == "listo"
    # Después, la fila «no» sola, con el aviso de que la conversación se borra
    api.agregar(sse(TU("toolu_2", "cargar_planilla", {"id": pid}), stop="tool_use"))
    r, ev = aa.enviar(sesion, "Carga también la fila 4", conversacion=cid)
    (tarjeta,) = _de(ev, "confirmar")
    assert "esta conversación se borrará" in tarjeta["aviso"]
    assert [k for k, _ in tarjeta["detalle"] if k.startswith("Fila")] == [
        f"Fila 4 · Retira la autorización de la ficha #{dario}"]
    r, ev = decidir(sesion, cid, toolu_2=True)
    assert r.status_code == 200
    assert _de(ev, "error")[0]["codigo"] == "borrada" and ev[-1]["motivo"] == "error"
    # Lo exige la ley y no se exceptúa: la conversación y sus mensajes ya no están; la negativa quedó guardada
    assert db[conv_db.CONVERSACIONES].find_one({"_id": cid}) is None
    assert db[conv_db.MENSAJES].count_documents({"conversacion": cid}) == 0
    assert db.personas.find_one({"_id": dario})["consentimiento"] == "no"
    assert db.planillas.find_one({"_id": pid})["estado"] == "cargada"
    _sin_enteros(_todo_lo_enviado(api))


def test_cargar_un_no_de_alguien_nuevo_no_borra_la_conversacion(cliente, sesion, monkeypatch):
    app, db = sesion.app, sesion.app.state.db
    api = aa.encender(app)
    pid = subir_sin_leer(sesion, monkeypatch)
    leer_con(cliente, monkeypatch, pid, lectura_json([
        fila(1, cedula=CED[7], nombre="FABIO INVENTADO NUEVO", celular=TEL[7], autorizacion="no")]))
    api.agregar(sse(TU("toolu_1", "cargar_planilla", {"id": pid}), stop="tool_use"))
    r, ev = _enviar(sesion, "Carga la planilla", [pid])
    cid = _de(ev, "inicio")[0]["conversacion"]
    (tarjeta,) = _de(ev, "confirmar")
    assert tarjeta["titulo"] == "Cargar 1 fila(s) que dicen «No autoriza»"
    assert "Si alguna ya había autorizado" in tarjeta["aviso"]
    api.agregar(sse(T("Quedó guardado que no autoriza.")))
    r, ev = decidir(sesion, cid, toolu_1=True)
    assert ev[-1]["motivo"] == "listo" and not _de(ev, "error")
    nuevo = db.personas.find_one({"cedula": CED[7]})
    assert nuevo["consentimiento"] == "no" and TEL[7] not in json.dumps(nuevo, default=str)
    conv = db[conv_db.CONVERSACIONES].find_one({"_id": cid})
    assert conv is not None and nuevo["_id"] not in conv["personas"]
    # Al modelo: la fila y su estado, sin la ficha de quien no autorizó
    resultado = json.loads(api.peticiones[-1]["json"]["messages"][-1]["content"][0]["content"])
    assert resultado["filas"] == [{"n": 1, "estado": "nueva_sin_autorizacion"}]


# ───────────────────────────── La voz ─────────────────────────────

class _SinApi:
    async def cerrar(self):
        pass


def test_la_voz_se_apaga_cuando_una_herramienta_deja_datos_de_una_planilla(cliente, sesion):
    app, db = sesion.app, sesion.app.state.db

    class Vacia(BaseModel):
        pass

    async def marca(ctx, a):
        conv_db.marcar_datos(ctx.db, ctx.conversacion_id)
        return Resultado({"filas": 3}, "3 filas")

    async def no_marca(ctx, a):
        return Resultado({"total": 3}, "3")

    def turno(cid):
        db[conv_db.CONVERSACIONES].insert_one({"_id": cid, "uid": 0, "personas": []})
        t = bucle.Turno(app=app, quien=aa.quien_de(app, 0), ajustes={}, agente={"retencion_dias": 30}, api=_SinApi(),
                        conv=None, cid=cid, titulo="x", turno="t", limite=None,
                        proveedor=SimpleNamespace(tope_imagenes=8_000_000, clave="anthropic"))
        t.frases = object()  # la respuesta hablada pedida
        return t

    for cid, fn, sigue in ((71, no_marca, True), (72, marca, False)):
        h = Herramienta("prueba", "Prueba.", Vacia, "lectura", (), "Probando", fn)
        t = turno(cid)
        aa.correr(cliente, t._correr_herramienta, h, "toolu_x", Vacia())
        assert (t.frases is not None) is sigue, cid
    assert conv_db.tiene_personas(db, 72) and not conv_db.tiene_personas(db, 71)
