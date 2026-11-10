"""Regresiones del remate del núcleo del asistente, tras la revisión de los arreglos de la revisión adversarial
(`app/agente/bucle.py`, `conversaciones.py`, `app/api/zonas.py` y los ganchos de `app/db.py`). Cada prueba falla sin
su arreglo, salvo las que cuidan que el arreglo no se pase de la raya (lo dicen en su docstring). La Messages API va
simulada: nunca se llama a Anthropic ni a Mnemo. Solo datos inventados."""
import asyncio
import json
import threading
import time
from datetime import timedelta

import httpx
import pytest
from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from ayudas_agente import (T, TU, con_herramientas, decidir, encender, encender_lento, enviar, herramientas_falsas,
                           quien_de, sse)
from ayudas_g3 import persona
from conftest import CLAVE_USUARIO, crear_usuario
from test_agente_api import _entrar, _esperar, servido  # noqa: F401 - el servidor único de verdad (uvicorn h11)

import servidor
from app import db as bd
from app.agente import bucle
from app.agente import conversaciones as conv_db
from app.agente.herramientas import base as hb
from app.agente.herramientas.base import Confirmacion, ErrorHerramienta, Herramienta, Resultado
from app.api import personas as api_personas


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


def _conversacion_con(db, cid: int, uid: int, personas=()) -> int:
    """Una conversación guardada de `uid` en la que el modelo vio a `personas` (sin pasar por un turno)."""
    conv_db.crear(db, cid, uid, "Prueba", "s", [], [], 30, "t", "m")
    conv_db.soltar(db, cid, "t")
    if personas:
        conv_db.sumar_personas(db, cid, set(personas))
    conv_db.guardar(db, cid, uid, conv_db.ahora() + timedelta(days=30), "user", [{"type": "text", "text": "x"}])
    return cid


def _existe(db, cid) -> bool:
    return (db[conv_db.CONVERSACIONES].find_one({"_id": cid}) is not None
            or db[conv_db.MENSAJES].count_documents({"conversacion": cid}) > 0)


def _resultados(api, i=-1) -> list[dict]:
    """Los `tool_result` del último mensaje de la petición `i` al modelo."""
    return [b for b in api.peticiones[i]["json"]["messages"][-1]["content"] if b.get("type") == "tool_result"]


# ───────────────────────────── 1. La tarjeta no esconde nada ─────────────────────────────

# Valores que la tarjeta no mostraría como se van a escribir: caracteres invisibles o que cambian cómo se ve el resto, y
# tiradas que esconden el final
OCULTOS = {
    "invierte el orden": "Llamar al 300\u202e3322111\u202c el lunes",
    "aislamiento de dirección": "Nota \u2066oculta\u2069 visible",
    "marca de dirección": "3001112233\u200f",
    "espacio de ancho cero": "300\u200b1112233",
    "marca de orden de bytes": "\ufeffVolver el lunes",
    "guion blando": "Volver el lu\u00adnes",
    "control": "Volver\x07 el lunes",
    "secuencia de escape": "Volver \x1b[8m el lunes",
    "suprimir": "Volver el lunes\x7f",
    "siguiente línea": "Volver\x85el lunes",
    "separador de línea": "Volver\u2028el lunes",
    "relleno invisible": "Volver el lunes\u3164\u3164\u3164 de noche",
    "saltos de línea": "Visita sin novedad." + "\n" * 30 + "OCULTO: llamar al 3001112233",
    "líneas en blanco con espacios": "Visita sin novedad." + "\n   " * 6 + "OCULTO",
    "retornos": "Visita sin novedad." + "\r\n" * 5 + "OCULTO",
    "espacios": "Visita sin novedad." + " " * 300 + "OCULTO",
    "espacios duros": "Visita sin novedad." + "\u00a0" * 40 + "OCULTO",
    "tabuladores": "Visita sin novedad." + "\t" * 30 + "OCULTO",
    "marcas apiladas": "Vis" + "\u0301" * 30 + "ita",
}

VISIBLES = [
    "Visita sin novedad.\n\nVolver el lunes.",
    "Uno\n\n\nDos",
    "Línea\r\nOtra línea",
    "Columna\tColumna\tColumna",
    "Calle 50 # 45-12, apto 301",
    "María José Ñandú",
    "Mari\u0301a",  # la tilde como marca combinada
    "Te quiero \u2764\ufe0f",  # el selector de variante de un emoji
    "1\ufe0f\u20e3 Primero",
    "a" + " " * 19 + "b",
    "x" * bucle.TARJETA_VALOR,
]


@pytest.mark.parametrize("caso", sorted(OCULTOS))
def test_la_tarjeta_no_ofrece_un_valor_que_no_se_ve_como_se_escribe(caso):
    with pytest.raises(ErrorHerramienta) as e:
        bucle._tarjeta(Confirmacion("Agregar una nota", [("Persona", "#1"), ("Nota", OCULTOS[caso])]))
    assert e.value.codigo == "oculto" and not e.value.fatal


def test_la_tarjeta_tampoco_ofrece_una_etiqueta_con_caracteres_invisibles():
    """En Mnemo las etiquetas son los nombres de los argumentos que se mandan."""
    with pytest.raises(ErrorHerramienta) as e:
        bucle._tarjeta(Confirmacion("Mnemo: crear un documento", [("title\u200b", "Acta")]))
    assert e.value.codigo == "oculto"


def test_la_tarjeta_sigue_mostrando_lo_que_se_ve_bien_y_con_los_mismos_topes():
    """Cuida que el arreglo no se pase de la raya (pasa también sin él): saltos de párrafo, tildes, emojis con su
    selector de variante y valores de hasta TARJETA_VALOR caracteres se ofrecen enteros; los topes no cambian."""
    t = bucle._tarjeta(Confirmacion("Escribir", [(f"Dato {i}", v) for i, v in enumerate(VISIBLES)]))
    assert [v for _, v in t["detalle"]] == VISIBLES
    assert (bucle.TARJETA_VALOR, bucle.TARJETA_FILAS) == (4_000, 40)
    with pytest.raises(ErrorHerramienta) as e:
        bucle._tarjeta(Confirmacion("Escribir", [("Texto", "x" * (bucle.TARJETA_VALOR + 1))]))
    assert e.value.codigo == "no_cabe"
    with pytest.raises(ErrorHerramienta):
        bucle._tarjeta(Confirmacion("Escribir", [(f"Dato {i}", "x") for i in range(bucle.TARJETA_FILAS + 1)]))


def test_una_escritura_con_un_valor_que_esconde_algo_no_se_propone(sesion, falsas):
    db = sesion.app.state.db
    pid = persona(db, nombre="ANA INVENTADA DE PRUEBA", consentimiento="si")
    texto = "Visita sin novedad." + "\n" * 40 + "Y que llame al 3001112233 para el voto."
    api = encender(sesion.app, sse(TU("toolu_n", "nota_falsa", {"persona_id": pid, "texto": texto}), stop="tool_use"),
                   sse(T("Lo escribo de otra forma.")))
    _, ev = enviar(sesion, "Agrega la nota")
    assert [e for e in ev if e["tipo"] == "confirmar"] == [] and ev[-1]["motivo"] == "listo"
    res = _resultados(api)
    assert res[0]["is_error"] and json.loads(res[0]["content"])["error"]["codigo"] == "oculto"
    assert db[conv_db.CONVERSACIONES].find_one({"_id": ev[0]["conversacion"]})["pendiente"] is None
    assert falsas == []


# ───────────────────────────── 2. Zonas: cambiar las áreas borra las conversaciones de los afectados ─────────────────

LAT, LON = 6.9, -73.95
CUADRO = [[LON - 0.004, LAT - 0.004], [LON + 0.004, LAT - 0.004], [LON + 0.004, LAT + 0.004],
          [LON - 0.004, LAT + 0.004]]
OTRO = [[LON + 0.1 - 0.004, LAT - 0.004], [LON + 0.1 + 0.004, LAT - 0.004], [LON + 0.1 + 0.004, LAT + 0.004],
        [LON + 0.1 - 0.004, LAT + 0.004]]


def test_cambiar_las_areas_desde_zonas_borra_las_conversaciones_de_los_afectados(sesion):
    db = sesion.app.state.db
    p1, p2, p3 = (crear_usuario(db, "planillero")["_id"] for _ in range(3))
    ids = iter(range(9601, 9700))

    def conv(uid):
        return _conversacion_con(db, next(ids), uid, [123])

    propia = conv(0)  # la del administrador nunca se toca
    # Crear un área asignada a p1: p1 gana alcance, p2 no cambia
    a1, a2 = conv(p1), conv(p2)
    r = sesion.post("/api/areas", json={"nombre": "Zona inventada uno", "poligono": CUADRO, "asignada_a": [p1]})
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    assert (_existe(db, a1), _existe(db, a2)) == (False, True)
    # Asignársela a otro: entra p2 y sale p1 (los dos cambian de alcance); p3 no
    b1, b2, b3 = conv(p1), conv(p2), conv(p3)
    r = sesion.patch(f"/api/areas/{aid}", json={"asignada_a": [p2]})
    assert r.status_code == 200, r.text
    assert (_existe(db, b1), _existe(db, b2), _existe(db, b3)) == (False, False, True)
    # El nombre, la descripción o el color no cambian el alcance de nadie
    c2 = conv(p2)
    r = sesion.patch(f"/api/areas/{aid}", json={"nombre": "Zona inventada dos", "descripcion": "Otra",
                                                "color": "#eb6834"})
    assert r.status_code == 200, r.text
    assert _existe(db, c2)
    # Sumar a p3 sin quitar a p2: solo cambia p3
    d3 = conv(p3)
    r = sesion.patch(f"/api/areas/{aid}", json={"asignada_a": [p2, p3]})
    assert r.status_code == 200, r.text
    assert (_existe(db, c2), _existe(db, d3)) == (True, False)
    # Redibujar el polígono cambia el alcance de todos los asignados
    e1, e2, e3 = conv(p1), conv(p2), conv(p3)
    r = sesion.patch(f"/api/areas/{aid}", json={"poligono": OTRO})
    assert r.status_code == 200, r.text
    assert (_existe(db, e1), _existe(db, e2), _existe(db, e3)) == (True, False, False)
    # Borrar el área: todos los asignados la pierden
    f1, f2, f3 = conv(p1), conv(p2), conv(p3)
    assert sesion.delete(f"/api/areas/{aid}").status_code == 200
    assert (_existe(db, f1), _existe(db, f2), _existe(db, f3)) == (True, False, False)
    assert _existe(db, propia)


# ───────────────────────────── 3. Un turno vivo: 409 en el acto ─────────────────────────────

def test_con_un_turno_vivo_el_409_llega_en_el_acto(sesion, falsas):
    """Esperar (hasta ESPERA_OCUPADA_S) retiene uno de los cupos del asistente en el servidor: con un turno que sigue
    vivo no sirve de nada."""
    assert bucle.ESPERA_OCUPADA_S >= 1
    ocupacion = bucle.ocupacion_de(sesion.app)
    encender(sesion.app, sse(T("Hola.")))
    r, ev = enviar(sesion, "Hola")
    cid = ev[0]["conversacion"]
    encender(sesion.app, sse(T("No debería.")))
    for conversacion, reserva in ((None, None), (cid, cid), (None, cid)):
        assert ocupacion.reservar(0, reserva) is None  # un turno suyo en curso en este proceso
        try:
            t0 = time.monotonic()
            r, _ = enviar(sesion, "¿Ya?", conversacion=conversacion)
            assert r.status_code == 409 and r.json()["detail"]["codigo"] == "ocupada"
            assert time.monotonic() - t0 < 1, (conversacion, reserva)
        finally:
            ocupacion.soltar(0, reserva)
    assert not ocupacion.usuarios and not ocupacion.conversaciones


def test_se_espera_solo_a_un_turno_que_se_cierra_y_un_mensaje_por_persona(sesion):
    app = sesion.app
    ocupacion = bucle.ocupacion_de(app)
    assert ocupacion.reservar(0, None) is None
    ocupacion.cerrar(0, None)  # se canceló: el navegador se fue o la persona pulsó «Detener»

    async def probar():
        primero = asyncio.ensure_future(bucle._ocupar(app, 0, None, "nuevo"))
        await asyncio.sleep(0.3)
        assert not primero.done()  # espera a que el turno que se cierra suelte
        t0 = time.monotonic()
        with pytest.raises(HTTPException) as e:
            await bucle._ocupar(app, 0, None, "otro")  # otro mensaje suyo mientras tanto: 409 enseguida
        assert e.value.status_code == 409 and e.value.detail["codigo"] == "ocupada"
        assert time.monotonic() - t0 < 0.5
        ocupacion.soltar(0, None)  # el turno que se cerraba suelta sus candados
        return await asyncio.wait_for(primero, 3)

    try:
        assert asyncio.run(probar()) is None  # entró (una conversación nueva: sin candado de MongoDB)
        assert 0 in ocupacion.usuarios and not ocupacion.esperando
    finally:
        ocupacion.soltar(0, None)


def test_un_turno_vivo_no_deja_el_asistente_en_503_para_los_demas(servido, cfg):  # noqa: F811
    """Lo que encontró la revisión, en el servidor de verdad: un planillero con un turno largo en curso manda tres
    mensajes más, cada uno esperaba 5 s con un cupo del asistente tomado (y sin contar en su tope), y el administrador
    recibía 503. Ahora esos tres reciben 409 enseguida y el administrador conversa."""
    base, panel = servido
    db = panel.state.db
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"agente.roles": ["admin", "coordinador", "planillero"]}},
                       upsert=True)
    u = crear_usuario(db, "planillero")
    encender_lento(panel, sse(T("Respuesta larga de prueba.")), sse(T("Hola.")), pausa=1.0)

    def ingresar(usuario, clave):
        c = httpx.Client(base_url=base, timeout=30)
        r = c.post("/panel/api/login", json={"usuario": usuario, "clave": clave})
        assert r.status_code == 200, r.text
        c.headers["X-CSRF-Token"] = r.json()["csrf"]
        return c

    p = ingresar(u["usuario"], CLAVE_USUARIO)
    resultados: dict = {}

    def turno():
        resultados["turno"] = p.post("/panel/api/agente/mensajes", json={"texto": "Hola"}).status_code

    def repetido(i):
        t0 = time.monotonic()
        r = p.post("/panel/api/agente/mensajes", json={"texto": "¿Ya?"})
        resultados[i] = (r.status_code, time.monotonic() - t0)

    hilos = [threading.Thread(target=turno)]
    hilos[0].start()
    time.sleep(1.0)  # el turno ya corre (el modelo responde despacio)
    for i in range(servidor.CUPOS_AGENTE - 1):
        hilos.append(threading.Thread(target=repetido, args=(i,)))
        hilos[-1].start()
    time.sleep(0.5)
    adm = ingresar(cfg.usuario, cfg.clave)
    r = adm.post("/panel/api/agente/mensajes", json={"texto": "Hola"})
    for h in hilos:
        h.join(30)
    assert r.status_code == 200, r.text
    assert resultados["turno"] == 200
    repetidos = [resultados[i] for i in range(servidor.CUPOS_AGENTE - 1)]
    assert all(estado == 409 and segundos < 1 for estado, segundos in repetidos), repetidos


def test_si_el_navegador_se_va_mientras_el_turno_suelta_la_persona_no_queda_sin_asistente(servido, cfg,  # noqa: F811
                                                                                          monkeypatch):
    """Una carrera que apareció con este remate: el turno ya terminó y, mientras suelta sus candados, el navegador se va
    (la cancelación llega en medio de soltar el de MongoDB). La reserva de este proceso quedaba tomada para siempre: la
    persona recibía 409 hasta que se reiniciara el servidor."""
    base, panel = servido
    encender_lento(panel, sse(T("Hola.")), pausa=0.05)
    entro, seguir = threading.Event(), threading.Event()
    soltar = conv_db.soltar

    def soltar_lento(db, cid, turno):  # MongoDB tarda en soltar el candado
        entro.set()
        seguir.wait(10)
        soltar(db, cid, turno)

    monkeypatch.setattr(conv_db, "soltar", soltar_lento)
    with httpx.Client(base_url=base, timeout=30) as c:
        _entrar(c, cfg)
        with c.stream("POST", "/panel/api/agente/mensajes", json={"texto": "Hola"}) as r:
            assert r.status_code == 200
            assert entro.wait(10)  # el turno terminó y está soltando: el navegador se va justo ahora
        assert _esperar(lambda: not panel.state.agente_ocupacion.usuarios, 5)
        seguir.set()
        monkeypatch.setattr(conv_db, "soltar", soltar)
        encender_lento(panel, sse(T("Aquí sigo.")), pausa=0)
        r = c.post("/panel/api/agente/mensajes", json={"texto": "¿Sigues?"})
        assert r.status_code == 200, r.text


# ───────────────────────────── 4. Lo rechazado en una aprobación cortada vuelve como rechazado ───────────────────────

def test_lo_rechazado_en_una_aprobacion_cortada_vuelve_como_rechazado(sesion, monkeypatch):
    class Escritura(BaseModel):
        texto: str = Field(..., max_length=200)

    async def preparar(ctx, a):
        return Confirmacion("Escribir", [("Texto", a.texto)])

    async def escribir(ctx, a):
        raise asyncio.CancelledError()  # el turno se corta mientras se hace la aprobada (el navegador se fue)

    con_herramientas(monkeypatch, [Herramienta("escribir_falsa", "Escribe (prueba).", Escritura, "escritura",
                                               ("cuenta",), "Escribiendo", escribir, confirmar=preparar)])
    api = encender(sesion.app, sse(TU("toolu_si", "escribir_falsa", {"texto": "La que aprobó"}),
                                   TU("toolu_no", "escribir_falsa", {"texto": "La que rechazó"}), stop="tool_use"),
                   sse(T("Reviso lo aprobado; lo rechazado no lo vuelvo a proponer.")))
    _, ev = enviar(sesion, "Escribe las dos")
    cid = ev[0]["conversacion"]
    r, _ = decidir(sesion, cid, toolu_si=True, toolu_no=False)
    assert r.status_code == 200, r.text
    r, ev = enviar(sesion, "¿Qué pasó?", conversacion=cid)
    assert r.status_code == 200 and ev[-1]["motivo"] == "listo", ev
    res = {b["tool_use_id"]: b for b in _resultados(api)}
    assert res["toolu_no"]["content"] == bucle.RECHAZADA and res["toolu_no"]["is_error"]
    assert res["toolu_si"]["content"] == bucle.INTERRUMPIDA_ESCRITURA  # esa sí pudo hacerse: que la verifique
    partes = [p for m in sesion.get(f"/api/agente/conversaciones/{cid}").json()["mensajes"] if m["rol"] == "asistente"
              for p in m["partes"] if p["tipo"] == "herramienta"]
    assert {p["id"]: p["estado"] for p in partes} == {"toolu_si": "error", "toolu_no": "rechazada"}


# ───────────────────────────── 5. Quien deja de autorizar mientras una herramienta lo lee ────────────────────────────

def _revocar(db, pid, como, quien=None):
    """Que `pid` deje de autorizar, por cada camino que lo hace (otro usuario, en otra petición)."""
    if como == "panel":
        db.autorizaciones.insert_one(bd.autorizacion_doc(db, pid, "revocada", "verbal_presencial"))
        api_personas.derivar_autorizacion(db, pid)
    elif como == "importacion":
        db.autorizaciones.insert_one(bd.autorizacion_doc(db, pid, "no", "declarado_planilla"))
        bd.derivar(db, [pid], reconciliar=False)
    else:  # una unión con una ficha que no autorizó («no» gana)
        origen = persona(db, nombre="LUCIA INVENTADA DE PRUEBA", consentimiento="no")
        db.autorizaciones.insert_one(bd.autorizacion_doc(db, origen, "no", "escrito"))
        bd.fusionar(db, pid, origen, quien)
    assert db.personas.find_one({"_id": pid})["consentimiento"] == "no"


@pytest.mark.parametrize("como", ["panel", "importacion", "union"])
def test_quien_deja_de_autorizar_mientras_se_lee_no_queda_en_la_conversacion(sesion, monkeypatch, como):
    db = sesion.app.state.db
    pid = persona(db, nombre="LUCIA INVENTADA DE PRUEBA", consentimiento="si", direccion="CALLE 50 # 45-12")
    db.autorizaciones.insert_one(bd.autorizacion_doc(db, pid, "si", "escrito", canales=["llamada"]))
    quien = quien_de(sesion.app, 0)

    async def ver(ctx, a):
        # El «no» llega mientras la herramienta lee la ficha: todavía no está anotada en la conversación
        await run_in_threadpool(_revocar, db, pid, como, quien)
        return Resultado({"nombre": "LUCIA INVENTADA DE PRUEBA", "direccion": "CALLE 50 # 45-12",
                          "observaciones": "Vive con su madre enferma"}, personas={pid})

    con_herramientas(monkeypatch, [Herramienta("ver_falsa", "Ver (prueba).", _Vacia, "lectura", ("cuenta",), "Viendo",
                                               ver)])
    api = encender(sesion.app, sse(TU("toolu_v", "ver_falsa", {}), stop="tool_use"), sse(T("No debería llegar.")))
    _, ev = enviar(sesion, "¿Quién es Lucía?")
    cid = ev[0]["conversacion"]
    assert ev[-2]["tipo"] == "error" and ev[-2]["codigo"] == "borrada" and ev[-1]["motivo"] == "error", ev[-3:]
    assert len(api.peticiones) == 1  # sus datos no llegaron al modelo
    assert not _existe(db, cid)


def test_quien_deja_de_autorizar_mientras_se_arma_la_tarjeta_no_queda_en_la_conversacion(sesion, monkeypatch):
    db = sesion.app.state.db
    pid = persona(db, nombre="LUCIA INVENTADA DE PRUEBA", consentimiento="si", direccion="CALLE 50 # 45-12")
    db.autorizaciones.insert_one(bd.autorizacion_doc(db, pid, "si", "escrito", canales=["llamada"]))

    class Editar(BaseModel):
        persona_id: int

    async def preparar(ctx, a):
        await run_in_threadpool(_revocar, db, pid, "panel")
        return Confirmacion("Editar la ficha", [("Dirección", "CALLE 50 # 45-12 → CALLE 51 # 45-12")])

    async def editar(ctx, a):
        raise AssertionError("no se aprueba")

    con_herramientas(monkeypatch, [Herramienta("editar_falsa", "Edita (prueba).", Editar, "escritura", ("cuenta",),
                                               "Editando", editar, confirmar=preparar)])
    api = encender(sesion.app, sse(TU("toolu_e", "editar_falsa", {"persona_id": pid}), stop="tool_use"))
    _, ev = enviar(sesion, "Cambia la dirección de Lucía")
    assert [e for e in ev if e["tipo"] == "confirmar"] == []
    assert ev[-2]["tipo"] == "error" and ev[-2]["codigo"] == "borrada" and len(api.peticiones) == 1
    assert not _existe(db, ev[0]["conversacion"])


def test_quien_ya_no_autorizaba_antes_de_leerlo_no_borra_la_conversacion(sesion, monkeypatch):
    """Cuida que el arreglo no se pase de la raya (pasa también sin él): de quien ya figuraba sin autorizar la API solo
    da quién es y que no autorizó, aunque haya dejado de autorizar hace un rato; la conversación sigue."""
    db = sesion.app.state.db
    nunca = persona(db, nombre="NORA INVENTADA DE PRUEBA", consentimiento="no")
    antes = persona(db, nombre="RITA INVENTADA DE PRUEBA", consentimiento="si")
    _revocar(db, antes, "panel")
    db[getattr(conv_db, "OLVIDOS", "agente_olvidos")].update_many(
        {"persona_id": antes}, {"$set": {"ts": conv_db.ahora() - timedelta(minutes=5)}})

    async def listar(ctx, a):
        return Resultado({"personas": [{"id": nunca, "consentimiento": "no"}, {"id": antes, "consentimiento": "no"}]},
                         resumen="2 personas", personas={nunca, antes})

    con_herramientas(monkeypatch, [Herramienta("listar_falsa", "Lista (prueba).", _Vacia, "lectura", ("cuenta",),
                                               "Listando", listar)])
    encender(sesion.app, sse(TU("toolu_l", "listar_falsa", {}), stop="tool_use"), sse(T("No autorizaron.")))
    _, ev = enviar(sesion, "¿Quiénes no autorizaron?")
    assert ev[-1]["motivo"] == "listo", ev[-3:]
    conv = db[conv_db.CONVERSACIONES].find_one({"_id": ev[0]["conversacion"]})
    assert sorted(conv["personas"]) == sorted([nunca, antes])


# ───────────────────────────── 6. Menores ─────────────────────────────

def test_el_bucle_usa_el_plazo_de_las_herramientas_una_sola_constante():
    assert bucle.PLAZO_HERRAMIENTA_S is hb.PLAZO_HERRAMIENTA_S


def test_la_lista_de_conversaciones_desempata_por_la_mas_nueva(sesion):
    """Dos conversaciones creadas en el mismo milisegundo salían en cualquier orden
    (test_lista_solo_las_30_mas_recientes fallaba a veces): ahora desempata la más nueva."""
    db = sesion.app.state.db
    for i in range(35):
        conv_db.crear(db, 2000 + i, 0, f"Conversación {i}", "s", [], [], 30, "t", "m")
    db[conv_db.CONVERSACIONES].update_many({"uid": 0}, {"$set": {"actualizada": conv_db.ahora()}})
    assert [c["id"] for c in conv_db.listar(db, 0)] == list(range(2034, 2004, -1))


def test_el_docstring_de_conversaciones_nombra_lo_que_guarda():
    assert "mnemo_intentadas" in conv_db.__doc__ and "rechazadas" in conv_db.__doc__
