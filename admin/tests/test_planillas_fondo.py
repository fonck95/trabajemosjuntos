"""La lectura de fondo de una planilla física (app/planillas.py, `leer_foto`): una sola lectura viva por planilla en el
proceso, lo leído no se guarda si una supresión tocó la planilla mientras tanto, y un apagado la deja fallida (no
«leyendo» para siempre). Con un proveedor del modelo falso (sin red). Solo datos inventados."""
import asyncio
import functools

from app import planillas as pl
from app.agente import lector_planillas as lp
from ayudas_planillas import ProveedorFalso, encender, fila, jpeg, lectura_json, subir


def test_una_sola_lectura_viva_por_planilla(cliente, sesion, monkeypatch):
    p = ProveedorFalso(lectura_json([fila(1, nombre="UNA INVENTADA")]), lectura_json([fila(1, nombre="OTRA")]),
                       pausa=0.3)
    encender(monkeypatch, cliente.app, p)
    d = subir(sesion, jpeg()).json()

    async def dos():
        await asyncio.gather(pl.leer_foto(cliente.app, d["id"]), pl.leer_foto(cliente.app, d["id"]))

    cliente.portal.call(dos)
    assert len(p.llamadas) == 1 and not pl._EN_CURSO
    doc = cliente.app.state.db.planillas.find_one({"_id": d["id"]})
    assert doc["estado"] == "leida" and doc["lecturas"] == 1


def test_lo_leido_no_se_guarda_si_una_supresion_toco_la_planilla(cliente, sesion, monkeypatch):
    encender(monkeypatch, cliente.app, ProveedorFalso())
    d = subir(sesion, jpeg()).json()
    db, cfg = cliente.app.state.db, cliente.app.state.cfg
    doc = db.planillas.find_one({"_id": d["id"]})
    lectura = lp.interpretar(lectura_json([fila(1, cedula="90010001", nombre="BORRADA INVENTADA")]))
    # Lo que hace `db.vaciar_planillas` mientras el modelo leía
    from app import db as bd
    bd.vaciar_planillas(db, [], [])  # sin nada que buscar: no toca nada
    assert db.planillas.find_one({"_id": d["id"]})["foto"] is not None
    from datetime import datetime, timezone
    db.planillas.update_one({"_id": d["id"]}, {"$set": {"foto": None, "actualizada": datetime.now(timezone.utc)},
                                               "$addToSet": {"filas_suprimidas": 1}})
    pl._guardar_lectura(db, cfg, doc, lectura, None, "anthropic")
    doc = db.planillas.find_one({"_id": d["id"]})
    assert doc["lectura"] is None and doc["estado"] == "fallida" and doc["error"]["codigo"] == "interrumpida"


def test_un_apagado_la_deja_fallida(cliente, sesion, monkeypatch):
    p = ProveedorFalso(lectura_json([fila(1, nombre="UNA INVENTADA")]), pausa=5.0)
    encender(monkeypatch, cliente.app, p)
    d = subir(sesion, jpeg()).json()

    async def cortar():
        t = asyncio.ensure_future(pl.leer_foto(cliente.app, d["id"]))
        await asyncio.sleep(0.3)
        t.cancel()
        await asyncio.gather(t, return_exceptions=True)

    cliente.portal.call(cortar)
    doc = cliente.app.state.db.planillas.find_one({"_id": d["id"]})
    assert doc["estado"] == "fallida" and doc["error"]["codigo"] == "interrumpida" and not pl._EN_CURSO
    assert pl._ocupados.get("anthropic", 0) == 0  # el cupo quedó libre
    assert sesion.get(f"/api/planillas/{d['id']}").json()["puede_releer"] is True


def test_una_borrada_mientras_espera_su_turno_no_se_lee(cliente, sesion, monkeypatch):
    p = ProveedorFalso(lectura_json([fila(1, nombre="UNA INVENTADA")]))
    encender(monkeypatch, cliente.app, p)
    d = subir(sesion, jpeg()).json()
    sesion.delete(f"/api/planillas/{d['id']}")
    cliente.portal.call(functools.partial(pl.leer_foto, cliente.app, d["id"]))
    assert p.llamadas == []


def test_el_progreso_de_una_lectura_en_curso(cliente, sesion, monkeypatch):
    vistos = []

    class Lento(ProveedorFalso):
        async def generar(self, *a, **kw):
            async def mirar():
                await asyncio.sleep(0.15)
                vistos.append(pl._PROGRESO.get(d["id"]))
            t = asyncio.ensure_future(mirar())
            r = await super().generar(*a, **kw)
            await t
            return r

    p = Lento(lectura_json([fila(n, nombre=f"PERSONA INVENTADA {n}") for n in range(1, 4)]), pausa=0.3)
    encender(monkeypatch, cliente.app, p)
    d = subir(sesion, jpeg()).json()
    cliente.portal.call(functools.partial(pl.leer_foto, cliente.app, d["id"]))
    assert vistos == [3] and d["id"] not in pl._PROGRESO


def test_las_subidas_tienen_cupos_propios_en_el_servidor():
    """Unos planilleros subiendo fotos por una red lenta no dejan la API en 503 (servidor.py, `cupos_subida`), y el
    cuerpo de la subida no se lee antes de la sesión (no está entre las rutas que se leen enteras)."""
    import httpx
    import servidor

    def lenta(segundos):
        async def app(scope, receive, send):
            await asyncio.sleep(segundos)
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})
        return app

    assert servidor.RUTAS_SUBIDA == {"/api/planillas/fotos"} and servidor.CUPOS_SUBIDA == 4
    assert not servidor.RUTAS_SUBIDA & (servidor.RUTAS_AGENTE | servidor.RUTAS_VOZ)

    async def probar():
        limite = servidor.LimitePanel(lenta(0.4), cupos=1, espera_s=0.15, cupos_subida=2, limite=1024)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=limite), base_url="http://t") as c:
            rs = await asyncio.gather(*(c.post("/api/planillas/fotos", content=b"x" * 4096) for _ in range(3)),
                                      c.get("/api/planillas"))
            assert sorted(r.status_code for r in rs[:3]) == [200, 200, 503]  # dos subidas a la vez
            assert rs[3].status_code == 200  # la API no espera por ellas
    asyncio.run(probar())


def test_la_guardia_deja_llegar_la_foto_y_nada_mas():
    from app import seguridad as seg
    assert seg.RUTA_FOTOS == "/api/planillas/fotos" and pl.MAX_BYTES < seg.LIMITE_FOTO < 2 * pl.MAX_BYTES
    assert seg.LIMITE_JSON < pl.MAX_BYTES


def test_de_punta_a_punta_con_la_messages_api_simulada(cliente, sesion, monkeypatch):
    """El proveedor de verdad (Anthropic directo) contra la Messages API simulada: lo que de verdad se le manda al
    modelo para leer una foto (sin herramientas, la imagen en base64 y el tope de 24000) y lo que se guarda."""
    import ayudas_agente as aa
    api = aa.encender(cliente.app, aa.sse(aa.T(lectura_json([fila(1, cedula="90011001", nombre="PUNTA INVENTADA",
                                                                  autorizacion="si", medio="escrito")]))))
    monkeypatch.setattr(pl, "programar", lambda app, pid, desde_fila=None: None)
    d = subir(sesion, jpeg()).json()
    cliente.portal.call(functools.partial(pl.leer_foto, cliente.app, d["id"]))
    (peticion,) = api.peticiones
    j = peticion["json"]
    assert j["max_tokens"] == lp.MAX_TOKENS_DIRECTO and "tools" not in j and j["stream"] is True
    assert j["system"][0]["text"] == lp.instrucciones(False)
    imagen, texto = j["messages"][0]["content"]
    assert imagen == {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                  "data": imagen["source"]["data"]}}
    assert texto["type"] == "text" and "Transcribe" in texto["text"]
    v = sesion.get(f"/api/planillas/{d['id']}").json()
    assert v["estado"] == "leida" and v["filas"][0]["valores"]["nombre"] == "PUNTA INVENTADA"
    uso = cliente.app.state.db.agente_uso.find_one({"uid": 0})
    assert uso["entrada"] == 900 and uso["salida"] == 50
