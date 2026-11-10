"""Regresiones de la revisión adversarial del núcleo del asistente (`app/agente/bucle.py`, `conversaciones.py`,
`llm.py`, la API del asistente y los ganchos de `db.py`, `api/personas.py` y `api/usuarios.py`). Cada sección lleva el
número del hallazgo y cada prueba falla sin su arreglo, salvo la que cuida que el arreglo no se pase de la raya (lo dice
en su docstring). La Messages API y Mnemo van simulados: nunca se llama a Anthropic ni a un Mnemo real. Solo datos
inventados."""
import asyncio
import base64
import json
from datetime import timedelta

import anthropic
import httpx2
import pytest
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from ayudas_agente import (ALCANCES_PANEL, T, TU, con_herramientas, conectar_mnemo, decidir, encender, enviar,
                           herramientas_falsas, quien_de, sse)
from ayudas_g3 import coordinador, persona
from conftest import crear_usuario

from app import db as bd
from app.agente import bucle, llm
from app.agente import conversaciones as conv_db
from app.agente.herramientas.base import Confirmacion, Herramienta, Resultado


async def _sin_espera(segundos):  # las rondas que fallan de paso se repiten sin esperar de verdad
    return None


@pytest.fixture
def falsas(monkeypatch):
    lista, registro = herramientas_falsas()
    con_herramientas(monkeypatch, lista)
    monkeypatch.setattr(bucle, "dormir", _sin_espera)
    return registro


class _Vacia(BaseModel):
    pass


def _ajustes(db, **agente):
    base = {"roles": ["admin", "coordinador"], "escritura": True, "mnemo_coordinadores": False, "retencion_dias": 30}
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"agente": {**base, **agente}}}, upsert=True)


def _conv(db, cid):
    return db[conv_db.CONVERSACIONES].find_one({"_id": cid})


def _conversacion_con(db, cid: int, uid: int, personas=()) -> int:
    """Una conversación guardada de `uid` en la que el modelo vio a `personas` (sin pasar por un turno)."""
    conv_db.crear(db, cid, uid, "Prueba", "s", [], [], 30, "t", "m")
    conv_db.soltar(db, cid, "t")
    if personas:
        conv_db.sumar_personas(db, cid, set(personas))
    conv_db.guardar(db, cid, uid, conv_db.ahora() + timedelta(days=30), "user", [{"type": "text", "text": "x"}])
    return cid


def _existe(db, cid) -> bool:
    return _conv(db, cid) is not None or db[conv_db.MENSAJES].count_documents({"conversacion": cid}) > 0


def _resultados(api, i=-1) -> list[dict]:
    """Los `tool_result` del último mensaje de la petición `i` al modelo."""
    return [b for b in api.peticiones[i]["json"]["messages"][-1]["content"] if b.get("type") == "tool_result"]


# ───────────────────────────── 2 y 23: la tarjeta muestra lo que se escribe ─────────────────────────────

def test_la_tarjeta_muestra_entero_el_valor_que_se_va_a_escribir(sesion, falsas):
    db = sesion.app.state.db
    pid = persona(db, nombre="ANA INVENTADA DE PRUEBA", consentimiento="si")
    texto = "Visita sin novedad. " * 60 + "OCULTO DESPUES DEL CARACTER 500: llamar al 3001112233."
    encender(sesion.app, sse(TU("toolu_n", "nota_falsa", {"persona_id": pid, "texto": texto}), stop="tool_use"),
             sse(T("Nota guardada.")))
    _, ev = enviar(sesion, "Agrega la nota")
    conf = next(e for e in ev if e["tipo"] == "confirmar")
    assert dict(conf["detalle"])["Nota"] == texto
    cid = ev[0]["conversacion"]
    pendiente = sesion.get(f"/api/agente/conversaciones/{cid}").json()["pendientes"][0]
    assert dict(pendiente["detalle"])["Nota"] == texto


def test_una_escritura_que_no_cabe_en_la_tarjeta_no_se_ofrece(sesion, monkeypatch):
    escritas = []

    class Larga(BaseModel):
        texto: str = Field(..., max_length=50_000)
        filas: int = 1

    async def preparar(ctx, a):
        return Confirmacion("Escribir", [("Texto", a.texto), *((f"Dato {i}", "x") for i in range(1, a.filas))])

    async def escribir(ctx, a):
        escritas.append(a.texto)
        return Resultado({"ok": True}, resumen="Hecho")

    con_herramientas(monkeypatch, [Herramienta("larga_falsa", "Escribe (prueba).", Larga, "escritura", ("cuenta",),
                                               "Escribiendo", escribir, confirmar=preparar)])
    api = encender(sesion.app, sse(TU("toolu_l", "larga_falsa", {"texto": "y" * (bucle.TARJETA_VALOR + 1)}),
                                   TU("toolu_f", "larga_falsa", {"texto": "corto", "filas": bucle.TARJETA_FILAS + 1}),
                                   stop="tool_use"),
                   sse(T("No cabe en la tarjeta: lo divido.")))
    _, ev = enviar(sesion, "Escribe el texto largo")
    assert [e for e in ev if e["tipo"] == "confirmar"] == [] and ev[-1]["motivo"] == "listo"
    res = _resultados(api)
    assert [b["tool_use_id"] for b in res] == ["toolu_l", "toolu_f"]
    assert all(b["is_error"] and json.loads(b["content"])["error"]["codigo"] == "no_cabe" for b in res)
    assert escritas == [] and _conv(sesion.app.state.db, ev[0]["conversacion"])["pendiente"] is None


def test_una_escritura_de_mnemo_que_la_tarjeta_no_muestra_entera_no_se_ofrece():
    """Mnemo recorta en su tarjeta los valores largos («… (N caracteres en total)») y los argumentos de más (fila
    «…»), pero escribe todo: esa tarjeta no se ofrece. Lo que cabe se muestra entero."""
    from app.agente.herramientas import mnemo as hm
    from app.agente.herramientas.base import ErrorHerramienta
    d = {"name": "mnemo_create_document", "description": "", "annotations": {"readOnlyHint": False},
         "inputSchema": {"type": "object", "properties": {"title": {"type": "string"}, "content": {"type": "string"}}}}
    texto = "Acta de la reunión. " * 60
    assert dict(bucle._tarjeta(hm.confirmacion(d, {"title": "Acta", "content": texto}))["detalle"])["content"] == texto
    with pytest.raises(ErrorHerramienta) as e:
        bucle._tarjeta(hm.confirmacion(d, {"title": "Acta", "content": "a" * 5000}))
    assert e.value.codigo == "no_cabe"
    with pytest.raises(ErrorHerramienta):
        bucle._tarjeta(hm.confirmacion(d, {f"campo_{i}": "x" for i in range(hm.DETALLE_FILAS + 2)}))


# ───────────────────────────── 6: revocar la autorización saca los datos de las conversaciones ─────────────────────

def test_revocar_la_autorizacion_borra_las_conversaciones_que_la_vieron(sesion, falsas):
    db = sesion.app.state.db
    pid = persona(db, nombre="LUIS INVENTADO REVOCA", consentimiento="si", direccion="CALLE 50 # 45-12")
    encender(sesion.app, sse(TU("toolu_p", "contar_falsa", {"lugar": "Casco", "persona_id": pid}), stop="tool_use"),
             sse(T("Luis vive en la CALLE 50 # 45-12.")))
    _, ev = enviar(sesion, "¿Dónde vive Luis?")
    cid = ev[0]["conversacion"]
    otra = _conversacion_con(db, 9101, 0)
    r = sesion.post(f"/api/personas/{pid}/autorizacion", json={"estado": "revocada"})
    assert r.status_code == 200, r.text
    assert not _existe(db, cid) and _existe(db, otra)
    assert sesion.get(f"/api/agente/conversaciones/{cid}").status_code == 404


def test_la_revocatoria_registrada_desde_el_asistente_borra_tambien_su_conversacion(sesion, monkeypatch):
    db = sesion.app.state.db
    pid = persona(db, nombre="RITA INVENTADA DE PRUEBA", consentimiento="si")

    class Revocar(BaseModel):
        persona_id: int

    async def preparar(ctx, a):
        return Confirmacion("Registrar que revoca la autorización", [("Persona", f"#{a.persona_id}")])

    async def revocar(ctx, a):
        await ctx.api.post(f"/api/personas/{a.persona_id}/autorizacion", {"estado": "revocada"})
        return Resultado({"ok": True}, resumen="Revocatoria registrada", personas={a.persona_id})

    con_herramientas(monkeypatch, [Herramienta("revocar_falsa", "Revoca (prueba).", Revocar, "escritura",
                                               ("cuenta",), "Registrando", revocar, confirmar=preparar)])
    api = encender(sesion.app, sse(TU("toolu_r", "revocar_falsa", {"persona_id": pid}), stop="tool_use"),
                   sse(T("No debería llegar.")))
    _, ev = enviar(sesion, "Rita revoca su autorización")
    cid = ev[0]["conversacion"]
    r, ev = decidir(sesion, cid, toolu_r=True)
    assert r.status_code == 200, r.text
    estados = [(e["estado"], e.get("resumen")) for e in ev if e["tipo"] == "herramienta"]
    assert ("ok", "Revocatoria registrada") in estados
    assert ev[-2]["tipo"] == "error" and ev[-2]["codigo"] == "borrada" and len(api.peticiones) == 1
    assert db.personas.find_one({"_id": pid})["consentimiento"] == "no" and not _existe(db, cid)


def test_pedir_no_ser_contactado_borra_las_conversaciones_que_la_vieron(sesion):
    db = sesion.app.state.db
    pid = persona(db, nombre="MARTA INVENTADA DE PRUEBA", consentimiento="si")
    cid = _conversacion_con(db, 9102, 0, [pid])
    r = sesion.post(f"/api/personas/{pid}/acercamientos", json={"canal": "visita", "resultado": "no_contactar",
                                                                "alcance": "persona"})
    assert r.status_code == 200, r.text
    assert not _existe(db, cid)


def test_un_no_de_quien_ya_no_autorizaba_no_borra_nada(sesion):
    """Cuida que el arreglo no se pase (pasa también sin él): de quien ya figuraba sin autorizar el modelo solo
    recibió quién es y que no autorizó, así que otro «no» no borra nada."""
    db = sesion.app.state.db
    pid = persona(db, nombre="NORA INVENTADA DE PRUEBA", consentimiento="no")
    cid = _conversacion_con(db, 9103, 0, [pid])
    r = sesion.post(f"/api/personas/{pid}/autorizacion", json={"estado": "revocada"})
    assert r.status_code == 200, r.text
    assert _existe(db, cid)


def test_un_no_que_llega_por_importacion_o_por_una_union_tambien_borra(sesion):
    db = sesion.app.state.db
    quien = quien_de(sesion.app, 0)
    # Importación: la planilla trae un «no» de quien había autorizado
    pid = persona(db, nombre="OSCAR INVENTADO DE PRUEBA", consentimiento="si")
    cid = _conversacion_con(db, 9104, 0, [pid])
    db.autorizaciones.insert_one(bd.autorizacion_doc(db, pid, "no", "declarado_planilla"))
    bd.derivar(db, [pid], reconciliar=False)
    assert db.personas.find_one({"_id": pid})["consentimiento"] == "no" and not _existe(db, cid)
    # Unión: una ficha que había autorizado se une a una que no («no» gana)
    origen = persona(db, nombre="PILAR INVENTADA DE PRUEBA", consentimiento="si")
    destino = persona(db, nombre="PILAR INVENTADA DE PRUEBA", consentimiento="no")
    cid = _conversacion_con(db, 9105, 0, [origen])
    bd.fusionar(db, destino, origen, quien)
    assert db.personas.find_one({"_id": destino})["consentimiento"] == "no" and not _existe(db, cid)


# ───────────────────────────── 7: cambiar el rol o la zona recorta las conversaciones ─────────────────────────────

def test_cambiar_el_rol_borra_las_conversaciones_del_usuario(sesion, falsas):
    db = sesion.app.state.db
    pid = persona(db, nombre="PEDRO INVENTADO DE PRUEBA", consentimiento="si")
    k = coordinador(sesion.app, db)
    encender(sesion.app, sse(TU("toolu_p", "contar_falsa", {"lugar": "Casco", "persona_id": pid}), stop="tool_use"),
             sse(T("Pedro vive en el casco.")))
    _, ev = enviar(k, "¿Dónde vive Pedro?")
    cid = ev[0]["conversacion"]
    propia = _conversacion_con(db, 9201, 0, [pid])  # la del administrador no se toca
    r = sesion.patch(f"/api/usuarios/{k.uid}", json={"rol": "consultor"})
    assert r.status_code == 200, r.text
    assert not _existe(db, cid) and _existe(db, propia)


def test_cambiar_la_zona_o_desactivar_borra_las_conversaciones_y_otros_cambios_no(sesion):
    db = sesion.app.state.db
    db.lugares.insert_one({"_id": 9301, "nombre": "BARRIO INVENTADO", "tipo": "barrio"})
    p = crear_usuario(db, "planillero")
    cid = _conversacion_con(db, 9302, p["_id"])
    r = sesion.patch(f"/api/usuarios/{p['_id']}", json={"nombre": "Planillero renombrado", "telefono": "3000000000"})
    assert r.status_code == 200, r.text
    assert _existe(db, cid)
    r = sesion.patch(f"/api/usuarios/{p['_id']}", json={"asignacion": {"lugares": [9301], "areas": []}})
    assert r.status_code == 200, r.text
    assert not _existe(db, cid)
    cid = _conversacion_con(db, 9303, p["_id"])
    r = sesion.patch(f"/api/usuarios/{p['_id']}", json={"activo": False})
    assert r.status_code == 200, r.text
    assert not _existe(db, cid)


# ───────────────────────────── 8: topes por ronda y por turno ─────────────────────────────

def test_una_ronda_ejecuta_como_mucho_ocho_herramientas(sesion, falsas):
    usos = [TU(f"toolu_{i}", "contar_falsa", {"lugar": f"Lugar {i}"}) for i in range(12)]
    api = encender(sesion.app, sse(*usos, stop="tool_use"), sse(T("Listo.")))
    _, ev = enviar(sesion, "Cuenta en doce lugares")
    assert len(falsas) == 8 and bucle.MAX_HERRAMIENTAS_RONDA == 8
    res = _resultados(api)
    assert [b["tool_use_id"] for b in res] == [f"toolu_{i}" for i in range(12)]  # todas tienen su resultado
    assert not any(b.get("is_error") for b in res[:8])
    assert all(b.get("is_error") and json.loads(b["content"])["error"]["codigo"] == "demasiadas" for b in res[8:])
    assert ev[-1]["motivo"] == "listo"


def test_pasado_el_tope_del_turno_no_se_le_pasan_mas_resultados_al_modelo(sesion, monkeypatch):
    leidas = []

    class Pagina(BaseModel):
        n: int

    async def leer(ctx, a):
        leidas.append(a.n)
        return Resultado({"pagina": a.n, "texto": "dato " * 7_000}, resumen=f"Página {a.n}")  # ~35 000 caracteres

    con_herramientas(monkeypatch, [Herramienta("leer_falsa", "Lee (prueba).", Pagina, "lectura", ("cuenta",),
                                               "Leyendo", leer)])
    api = encender(sesion.app, sse(*[TU(f"toolu_{i}", "leer_falsa", {"n": i}) for i in range(7)], stop="tool_use"),
                   sse(T("Con lo que hay alcanza.")))
    _, ev = enviar(sesion, "Lee todas las páginas")
    res = _resultados(api)
    servidos = [b for b in res if not b.get("is_error")]
    assert len(servidos) == 5 and sum(len(b["content"]) for b in servidos) <= bucle.TOPE_RESULTADOS_TURNO
    assert all(json.loads(b["content"])["error"]["codigo"] == "tope_turno" for b in res[5:])
    assert leidas == [0, 1, 2, 3, 4, 5]  # la que no cupo ya se leyó; las siguientes, no
    assert ev[-1]["motivo"] == "listo"


# ───────────────────────────── 12: Mnemo vuelve a revisar la sesión y los ajustes ─────────────────────────────

def _mnemo_con_coordinador(sesion, monkeypatch, efecto):
    """Mnemo conectado (el modelo es la Messages API simulada), un coordinador con las herramientas de Mnemo y una
    primera herramienta del panel que hace `efecto` a mitad del turno, antes de la de Mnemo."""
    db = sesion.app.state.db
    _ajustes(db, mnemo_coordinadores=True)

    async def cambiar(ctx, a):
        efecto(ctx)
        return Resultado({"ok": True}, resumen="Listo")

    con_herramientas(monkeypatch, [Herramienta("cambiar_falsa", "Cambia algo (prueba).", _Vacia, "lectura",
                                               ("cuenta",), "Cambiando", cambiar)])
    mcp = conectar_mnemo(sesion.app, alcances=[a for a in ALCANCES_PANEL if a != "mnemo:model"]).mcp
    api = encender(sesion.app, sse(TU("toolu_c", "cambiar_falsa", {}), TU("toolu_m", "mnemo_search", {"query": "acta"}),
                                   stop="tool_use"),
                   sse(T("No pude buscar en Mnemo.")))
    k = coordinador(sesion.app, db)
    r, ev = enviar(k, "Busca el acta en Mnemo")
    assert r.status_code == 200, r.text
    return mcp, api, ev


def test_mnemo_a_mitad_del_turno_respeta_el_ajuste_apagado(sesion, monkeypatch):
    db = sesion.app.state.db
    mcp, api, ev = _mnemo_con_coordinador(sesion, monkeypatch, lambda ctx: _ajustes(db, mnemo_coordinadores=False))
    assert mcp.llamadas == []
    res = _resultados(api)
    assert res[1]["tool_use_id"] == "toolu_m" and json.loads(res[1]["content"])["error"]["codigo"] == "permiso"


def test_mnemo_a_mitad_del_turno_respeta_la_sesion_cerrada(sesion, monkeypatch):
    db = sesion.app.state.db
    mcp, api, ev = _mnemo_con_coordinador(
        sesion, monkeypatch, lambda ctx: db.usuarios.update_one({"_id": ctx.quien.uid}, {"$set": {"activo": False}}))
    assert mcp.llamadas == []
    assert ev[-2]["tipo"] == "error" and ev[-2]["codigo"] == "sesion" and len(api.peticiones) == 1


# ───────────────────────────── 13: las confirmaciones cuentan en el tope diario ─────────────────────────────

def test_aprobar_o_rechazar_cuenta_como_un_mensaje_del_dia(sesion, falsas):
    db = sesion.app.state.db
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"agente_mensajes_diarios": {"admin": 2}}}, upsert=True)
    pid = persona(db, nombre="ANA INVENTADA DE PRUEBA", consentimiento="si")
    encender(sesion.app, sse(TU("toolu_n", "nota_falsa", {"persona_id": pid, "texto": "Uno"}), stop="tool_use"),
             sse(TU("toolu_m", "nota_falsa", {"persona_id": pid, "texto": "Dos"}), stop="tool_use"))
    _, ev = enviar(sesion, "Agrega dos notas")
    cid = ev[0]["conversacion"]
    assert ev[-1]["limite"] == {"usados": 1, "maximo": 2}
    r, ev = decidir(sesion, cid, toolu_n=False)
    assert r.status_code == 200 and ev[-1]["limite"] == {"usados": 2, "maximo": 2}
    r, _ = decidir(sesion, cid, toolu_m=False)  # ya no quedan: lo pendiente espera a mañana
    assert r.status_code == 429 and r.json()["detail"]["codigo"] == "volumen"
    assert [p["id"] for p in sesion.get(f"/api/agente/conversaciones/{cid}").json()["pendientes"]] == ["toolu_m"]
    assert falsas == []


# ───────────────────────────── 14: suprimida mientras una herramienta la leía ─────────────────────────────

def test_la_suprimida_mientras_se_leia_no_queda_en_la_conversacion(sesion, monkeypatch):
    db = sesion.app.state.db
    pid = persona(db, nombre="JULIA INVENTADA DE PRUEBA", consentimiento="si")

    async def ver(ctx, a):
        # La supresión llega mientras la herramienta lee la ficha: todavía no está anotada en la conversación
        await run_in_threadpool(bd.suprimir, db, pid, quien_de(sesion.app, 0))
        return Resultado({"nombre": "JULIA INVENTADA DE PRUEBA", "direccion": "CALLE FALSA 123"}, personas={pid})

    con_herramientas(monkeypatch, [Herramienta("ver_falsa", "Ver (prueba).", _Vacia, "lectura", ("cuenta",), "Viendo",
                                               ver)])
    api = encender(sesion.app, sse(TU("toolu_v", "ver_falsa", {}), stop="tool_use"), sse(T("No debería llegar.")))
    _, ev = enviar(sesion, "¿Quién es Julia?")
    cid = ev[0]["conversacion"]
    assert ev[-2]["tipo"] == "error" and ev[-2]["codigo"] == "borrada" and ev[-1]["motivo"] == "error"
    assert len(api.peticiones) == 1  # sus datos no llegaron al modelo
    assert not _existe(db, cid)


# ───────────────────────────── 15: una respuesta vacía no rompe la conversación ─────────────────────────────

def test_una_respuesta_vacia_no_queda_para_reenviarse(sesion, falsas):
    api = encender(sesion.app, sse(), sse(T("")), sse(T("Sigo aquí.")))
    _, ev = enviar(sesion, "Hola")
    cid = ev[0]["conversacion"]
    assert ev[-1]["motivo"] == "listo" and any(e["tipo"] == "aviso" for e in ev)
    _, ev = enviar(sesion, "¿Sigues?", conversacion=cid)
    assert ev[-1]["motivo"] == "listo"
    _, ev = enviar(sesion, "¿Y ahora?", conversacion=cid)
    assert ev[-1]["motivo"] == "listo"
    for p in api.peticiones:
        mensajes = p["json"]["messages"]
        assert all(m["content"] for m in mensajes)  # solo el último del asistente podría ir vacío, y no hay
        assert all(b["text"] for m in mensajes for b in m["content"] if b.get("type") == "text")
        assert [m["role"] for m in mensajes][::2] == ["user"] * len(mensajes[::2])


# ───────────────────────────── 16: una decisión vieja no decide lo pendiente nuevo ─────────────────────────────

def test_una_decision_vieja_no_rechaza_lo_pendiente_nuevo(sesion, falsas):
    db = sesion.app.state.db
    pid = persona(db, nombre="ANA INVENTADA DE PRUEBA", consentimiento="si")
    encender(sesion.app,
             sse(TU("toolu_x", "nota_falsa", {"persona_id": pid, "texto": "Uno"}), stop="tool_use"),
             sse(TU("toolu_y", "nota_falsa", {"persona_id": pid, "texto": "Dos"}), stop="tool_use"),
             sse(T("Listo.")))
    _, ev = enviar(sesion, "Agrega dos notas")
    cid = ev[0]["conversacion"]
    _, ev = decidir(sesion, cid, toolu_x=True)  # pestaña A
    assert ev[-1]["motivo"] == "confirmacion"
    r, _ = decidir(sesion, cid, toolu_x=True)  # pestaña B, que todavía muestra la tarjeta vieja
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "sin_pendientes"
    assert [p["id"] for p in sesion.get(f"/api/agente/conversaciones/{cid}").json()["pendientes"]] == ["toolu_y"]
    r, ev = decidir(sesion, cid, toolu_y=True)
    assert r.status_code == 200 and ev[-1]["motivo"] == "listo"
    assert [x[1]["texto"] for x in falsas if x[0] == "nota_falsa"] == ["Uno", "Dos"]


# ───────────────────────────── 17: una escritura aprobada no queda aprobable si el turno se corta ─────────────────

def test_una_escritura_aprobada_no_se_repite_si_el_turno_se_corta(sesion, monkeypatch):
    hechas = []

    class Escritura(BaseModel):
        texto: str

    async def preparar(ctx, a):
        return Confirmacion("Escribir", [("Texto", a.texto)])

    async def escribir(ctx, a):
        hechas.append(a.texto)
        if len(hechas) == 1:
            raise asyncio.CancelledError()  # el navegador se fue justo después de hacerla
        return Resultado({"ok": True}, resumen="Hecho")

    con_herramientas(monkeypatch, [Herramienta("escribir_falsa", "Escribe (prueba).", Escritura, "escritura",
                                               ("cuenta",), "Escribiendo", escribir, confirmar=preparar)])
    api = encender(sesion.app, sse(TU("toolu_w", "escribir_falsa", {"texto": "Reunión del martes"}), stop="tool_use"),
                   sse(T("La reviso antes de repetirla.")))
    _, ev = enviar(sesion, "Crea la reunión")
    cid = ev[0]["conversacion"]
    decidir(sesion, cid, toolu_w=True)
    assert hechas == ["Reunión del martes"]
    assert sesion.get(f"/api/agente/conversaciones/{cid}").json()["pendientes"] == []
    r, _ = decidir(sesion, cid, toolu_w=True)
    assert r.status_code == 409 and hechas == ["Reunión del martes"]
    _, ev = enviar(sesion, "¿Quedó?", conversacion=cid)
    resultado = next(b for b in _resultados(api) if b["tool_use_id"] == "toolu_w")
    assert resultado["is_error"] and resultado["content"] == bucle.INTERRUMPIDA_ESCRITURA
    assert "Puede que ya se haya hecho" in resultado["content"]


# ───────────────────────────── 18: el candado de un proceso caído vence pronto ─────────────────────────────

def test_el_candado_de_un_proceso_caido_vence_pronto(sesion, falsas):
    encender(sesion.app, sse(T("Hola.")))
    _, ev = enviar(sesion, "Hola")
    db = sesion.app.state.db
    c = conv_db.tomar(db, ev[0]["conversacion"], 0, "turno-de-un-proceso-que-murio")
    assert c["ocupada_hasta"] - conv_db.ahora() <= timedelta(seconds=90)


def test_un_turno_largo_renueva_su_candado(sesion, monkeypatch):
    monkeypatch.setattr(conv_db, "ARRIENDO", timedelta(seconds=1))
    monkeypatch.setattr(bucle, "RENOVAR_S", 0.2)
    db = sesion.app.state.db
    visto = []

    async def lenta(ctx, a):
        await asyncio.sleep(2.0)  # más que el arriendo
        c = await run_in_threadpool(_conv, db, ctx.conversacion_id)
        visto.append(conv_db.ocupada(c))
        return Resultado({"ok": True}, resumen="Listo")

    con_herramientas(monkeypatch, [Herramienta("lenta_falsa", "Lenta (prueba).", _Vacia, "lectura", ("cuenta",),
                                               "Esperando", lenta)])
    encender(sesion.app, sse(TU("toolu_l", "lenta_falsa", {}), stop="tool_use"), sse(T("Listo.")))
    _, ev = enviar(sesion, "Haz algo lento")
    assert visto == [True] and ev[-1]["motivo"] == "listo"
    assert not conv_db.ocupada(_conv(db, ev[0]["conversacion"]))  # al terminar se suelta


# ───────────────────────────── 19: imágenes por conversación y el 413 ─────────────────────────────

def _con_imagenes(monkeypatch, n_por_llamada=2):
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\0" * 64).decode()
    img = {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": png}}

    async def ver(ctx, a):
        return Resultado("Imágenes de Mnemo", resumen="Imágenes", imagenes=[img] * n_por_llamada)

    con_herramientas(monkeypatch, [Herramienta("ver_imagenes_falsa", "Ver (prueba).", _Vacia, "lectura", ("cuenta",),
                                               "Mirando", ver)])
    return png


def _imagenes_en(peticion) -> int:
    n = 0
    for m in peticion["json"]["messages"]:
        for b in m["content"] if isinstance(m["content"], list) else []:
            n += b.get("type") == "image"
            if b.get("type") == "tool_result" and isinstance(b.get("content"), list):
                n += sum(x.get("type") == "image" for x in b["content"])
    return n


def test_las_imagenes_de_una_conversacion_tienen_tope(sesion, monkeypatch):
    _con_imagenes(monkeypatch)
    guion = []
    for t in range(3):
        guion += [sse(*[TU(f"toolu_{t}_{i}", "ver_imagenes_falsa", {}) for i in range(4)], stop="tool_use"),
                  sse(T("Las veo."))]
    api = encender(sesion.app, *guion, sse(T("Fin.")))
    cid = None
    for t in range(3):  # 3 turnos × 4 llamadas × 2 imágenes = 24
        _, ev = enviar(sesion, f"Muéstrame las fotos {t}", conversacion=cid)
        cid = ev[0]["conversacion"]
    enviar(sesion, "¿Y ahora?", conversacion=cid)
    assert _imagenes_en(api.peticiones[-1]) == bucle.MAX_IMAGENES_CONVERSACION == 20
    assert "conversación ya lleva demasiadas imágenes" in json.dumps(api.peticiones[-1]["json"], ensure_ascii=False)


def test_las_imagenes_de_una_conversacion_tienen_tope_de_peso(sesion, monkeypatch):
    png = _con_imagenes(monkeypatch, n_por_llamada=5)
    monkeypatch.setattr(bucle, "TOPE_IMAGENES_CONVERSACION", 3 * len(png))
    api = encender(sesion.app, sse(TU("toolu_i", "ver_imagenes_falsa", {}), stop="tool_use"), sse(T("Las veo.")))
    enviar(sesion, "Muéstrame las fotos")
    assert _imagenes_en(api.peticiones[-1]) == 3


def test_un_413_del_modelo_se_explica_como_conversacion_larga():
    r = httpx2.Response(413, request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"),
                        json={"type": "error", "error": {"type": "request_too_large", "message": "too large"}})
    e = anthropic.APIStatusError("413", response=r, body=r.json())
    assert llm.explicar(e)[1] == "larga"


# ───────────────────────────── 20: un sustituto suelto en un error de herramienta ─────────────────────────────

def test_un_sustituto_suelto_en_el_error_de_una_herramienta_no_tumba_el_turno(sesion, monkeypatch):
    from app.agente.herramientas.base import ErrorHerramienta
    dice = json.loads('"El evento \\u00abFiesta \\ud83d"')  # lo que llega de un JSON con un emoji partido

    async def falla(ctx, a):
        raise ErrorHerramienta(f"Mnemo no pudo hacerlo. Mnemo dice: {dice}", "mnemo")

    con_herramientas(monkeypatch, [Herramienta("mnemo_falsa", "Prueba.", _Vacia, "lectura", ("cuenta",),
                                               "Consultando Mnemo", falla)])
    monkeypatch.setattr(bucle, "dormir", _sin_espera)
    api = encender(sesion.app, sse(TU("toolu_m", "mnemo_falsa", {}), stop="tool_use"), sse(T("Mnemo falló.")))
    _, ev = enviar(sesion, "Mira el evento")
    assert ev[-1]["motivo"] == "listo" and len(api.peticiones) == 2
    db = sesion.app.state.db
    guardado = db[conv_db.MENSAJES].find_one({"conversacion": ev[0]["conversacion"], "herramientas.id": "toolu_m"})
    assert guardado["herramientas"][0]["resumen"] == "Mnemo no pudo hacerlo. Mnemo dice: El evento «Fiesta ?"


# ───────────────────────────── 21: el tope de tokens termina con «larga» ─────────────────────────────

def test_el_tope_de_tokens_termina_con_el_codigo_larga(sesion, falsas):
    encender(sesion.app, sse(TU("toolu_c", "contar_falsa", {"lugar": "Casco"}), stop="tool_use",
                             uso={"input_tokens": conv_db.TOPE_TOKENS + 1}), sse(T("No llega.")))
    _, ev = enviar(sesion, "Cuenta")
    cid = ev[0]["conversacion"]
    assert ev[-2] == {"tipo": "error", "mensaje": bucle.AVISO_LARGA, "codigo": "larga"} and ev[-1]["motivo"] == "error"
    vista = sesion.get(f"/api/agente/conversaciones/{cid}").json()
    assert {"tipo": "aviso", "texto": bucle.AVISO_LARGA, "nivel": "alerta"} in vista["mensajes"][-1]["partes"]
    r, _ = enviar(sesion, "Continúa donde quedaste.", conversacion=cid)
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "larga"


# ───────────────────────────── 22: un modelo sin capacidades conocidas ─────────────────────────────

def test_un_modelo_desconocido_no_recibe_pensamiento_ni_esfuerzo(sesion, falsas):
    from dataclasses import replace
    api = encender(sesion.app, sse(T("Hola.")), modelo="claude-haiku-4-5")
    _, ev = enviar(sesion, "Hola")
    j = api.peticiones[0]["json"]
    assert ev[-1]["motivo"] == "listo" and "thinking" not in j and "output_config" not in j
    assert "anthropic-beta" not in api.peticiones[0]["cabeceras"] and "fallbacks" not in j
    conocido = llm.parametros(replace(sesion.app.state.cfg, agente_modelo="claude-opus-5-5"))
    assert conocido["thinking"]["type"] == "adaptive" and conocido["output_config"] == {"effort": "medium"}
