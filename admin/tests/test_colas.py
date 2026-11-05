"""Colas del consultor (4.5): las listas no se solapan, quien contestó no vuelve a «por llamar», `siguiente` es
atómico, `tomar` exige BASE_COLA y deja como mucho 3 personas tomadas, el alcance del consultor y su búsqueda. Solo
datos inventados."""
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from ayudas_g3 import contactable, persona, tomar

LLAMADA = {"canal": "llamada", "telefono_indice": 0}


@pytest.fixture(autouse=True)
def _siempre_en_horario(monkeypatch):
    from app.api import acercamientos as ac
    monkeypatch.setattr(ac, "fuera_de_horario", lambda *a, **k: False)


def _ids(c, lista):
    return {f["id"] for f in c.get("/api/trabajo/cola", params={"lista": lista}).json()["filas"]}


def test_listas_disjuntas_y_contactados_fuera_de_por_llamar(sesion, como):
    db = sesion.app.state.db
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"seguimiento_activo": True, "dias_seguimiento": 0,
                                                     "dias_entre_intentos": 0}}, upsert=True)
    ids = [contactable(db, f"IGNACIA INVENTADA COLA {i}", f"30111100{i:02d}") for i in range(6)]
    c = como("consultor")
    por_llamar = _ids(c, "por_llamar")
    assert set(ids) <= por_llamar and not _ids(c, "volver_a_llamar") and not _ids(c, "seguimiento")
    fila = c.get("/api/trabajo/cola").json()["filas"][0]
    assert set(fila) == {"id", "nombre", "lugar", "zona", "rango_edad", "telefono_indice", "telefono", "whatsapp",
                         "canales_permitidos", "consentimiento", "abordaje"}
    assert fila["canales_permitidos"] == ["llamada", "whatsapp", "sms"]
    for pid, resultado, extra in [(ids[0], "contesto", {}), (ids[1], "no_contesto", {}),
                                  (ids[2], "volver_llamar", {"proximo": "2020-01-01", "proximo_franja": "tarde"}),
                                  (ids[3], "pidio_informacion", {})]:
        tomar(c, pid)
        assert c.post(f"/api/personas/{pid}/acercamientos", json={**LLAMADA, "resultado": resultado, **extra}).status_code == 200
    listas = {x: _ids(c, x) for x in ("por_llamar", "volver_a_llamar", "seguimiento")}
    assert ids[0] not in listas["por_llamar"] and ids[3] not in listas["por_llamar"]
    assert {ids[1], ids[2]} <= listas["volver_a_llamar"]
    assert {ids[0], ids[3]} <= listas["seguimiento"]
    assert {ids[4], ids[5]} <= listas["por_llamar"]
    vistos = [i for l in listas.values() for i in l]
    assert len(vistos) == len(set(vistos))  # no se solapan
    hoy = c.get("/api/trabajo/cola", params={"lista": "mis_hoy"}).json()
    assert [f["id"] for f in hoy["filas"]] == [ids[3], ids[2], ids[1], ids[0]]
    t = c.get("/api/trabajo").json()
    assert {x["clave"]: x["n"] for x in t["listas"]}["mis_hoy"] == 4 and t["hoy"]["acercamientos"] == 4


def test_dos_siguiente_concurrentes_nunca_dan_la_misma_persona(sesion, como):
    db = sesion.app.state.db
    for i in range(8):
        contactable(db, f"JOVITA INVENTADA CONCURRENTE {i}", f"30222200{i:02d}")
    clientes = [como("consultor") for _ in range(6)]
    barrera = threading.Barrier(len(clientes))

    def pedir(c):
        barrera.wait()
        r = c.post("/api/trabajo/siguiente")
        assert r.status_code == 200, r.text
        return r.json()["id"]

    with ThreadPoolExecutor(len(clientes)) as ex:
        recibidos = list(ex.map(pedir, clientes))
    assert len(set(recibidos)) == len(clientes)
    for c, pid in zip(clientes, recibidos):
        assert db.personas.find_one({"_id": pid})["en_curso"]["uid"] == c.uid
    # «Siguiente» de nuevo da otra persona, y la anterior sigue tomada hasta que se registre o se libere
    otra = clientes[0].post("/api/trabajo/siguiente").json()["id"]
    assert otra not in recibidos


def test_tomar_maximo_tres_y_solo_base_cola(sesion, como):
    db = sesion.app.state.db
    ids = [contactable(db, f"LIBRADA INVENTADA TOMAR {i}", f"30333300{i:02d}") for i in range(4)]
    sin_tel = persona(db, nombre="LIBRADA INVENTADA SINTEL", tipo_documento="CC")
    db.personas.update_one({"_id": sin_tel}, {"$set": {"consentimiento": "si", "contacto_habilitado": True,
                                                        "consentimiento_canales": ["llamada"]}})
    c, otro = como("consultor"), como("consultor")
    for pid in ids:
        tomar(c, pid)
    mias = [p["_id"] for p in db.personas.find({"en_curso.uid": c.uid})]
    assert len(mias) == 3 and ids[0] not in mias  # la más vieja se liberó
    r = otro.post(f"/api/trabajo/tomar/{ids[1]}")
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "tomada" and r.json()["detail"]["usuario"] == c.usuario
    assert otro.post(f"/api/trabajo/tomar/{ids[0]}").status_code == 200
    r = c.post(f"/api/trabajo/tomar/{sin_tel}")
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "no_contactable"
    assert c.delete(f"/api/trabajo/tomar/{ids[1]}").json()["liberada"] is True
    assert otro.post(f"/api/trabajo/tomar/{ids[1]}").status_code == 200


def test_alcance_del_consultor_y_su_busqueda(sesion, como):
    db = sesion.app.state.db
    l1, l2 = [x["_id"] for x in db.lugares.find({}, {"_id": 1}).limit(2)]
    dentro = contactable(db, "MACARIA INVENTADA DENTRO", "3044440001", lugar_id=l1)
    fuera = contactable(db, "MACARIA INVENTADA FUERA", "3044440002", lugar_id=l2)
    c = como("consultor", asignacion={"lugares": [l1], "areas": []})
    assert _ids(c, "por_llamar") == {dentro}
    # Ficha fuera de su alcance (no tomada ni trabajada): 403
    r = c.get(f"/api/personas/{dentro}")
    assert r.status_code == 403 and r.json()["detail"]["codigo"] == "permiso"
    tomar(c, dentro)
    assert c.get(f"/api/personas/{dentro}").status_code == 200
    r = c.post(f"/api/trabajo/tomar/{fuera}")
    assert r.status_code == 403
    # Búsqueda: nombre (3 letras o más) o un número completo de 10 dígitos
    assert len(c.get("/api/buscar", params={"q": "MACARIA"}).json()) == 2
    assert c.get("/api/buscar", params={"q": "MA"}).json() == []
    for q in ("3044", "MACARIA 30444", "123456789012"):
        assert c.get("/api/buscar", params={"q": q}).status_code == 422, q
    r = c.get("/api/buscar", params={"q": "304 444 0002"})
    assert [x["id"] for x in r.json()] == [fuera]
    assert db.auditoria.find_one({"accion": "buscar_telefono", "uid": c.uid})
    assert "3044440002" not in (db.auditoria.find_one({"accion": "buscar_telefono"}).get("detalle") or "")
    # Tras registrar un acercamiento sigue en su alcance (30 días) aunque ya no esté tomada
    c.post(f"/api/personas/{dentro}/acercamientos", json={**LLAMADA, "resultado": "no_contesto"})
    assert db.personas.find_one({"_id": dentro})["en_curso"] is None
    assert c.get(f"/api/personas/{dentro}").status_code == 200


def test_cola_vacia_responde_204_y_explica_los_pendientes(sesion, como):
    db = sesion.app.state.db
    persona(db, nombre="NARCISA INVENTADA PENDIENTE", telefono="3055550001", tipo_documento="CC", fuentes=["planilla"])
    c = como("consultor")
    r = c.post("/api/trabajo/siguiente")
    assert r.status_code == 204
    t = c.get("/api/trabajo").json()
    assert t["pendientes_sin_autorizacion"] == 1 and t["politica"]["contactar_pendientes"] is False
    assert {x["clave"] for x in t["listas"]} == {"por_llamar", "volver_a_llamar", "mis_hoy"}


def test_el_administrador_ve_el_trabajo_de_un_usuario(sesion, como):
    db = sesion.app.state.db
    c = como("consultor")
    t = sesion.get("/api/trabajo", params={"uid": c.uid}).json()
    assert t["rol"] == "consultor" and {x["clave"] for x in t["listas"]} >= {"por_llamar", "volver_a_llamar"}
    assert sesion.get("/api/trabajo").json()["rol"] == "admin"
    assert c.get("/api/trabajo", params={"uid": 0}).status_code == 403
    assert sesion.get("/api/trabajo", params={"uid": 999}).status_code == 404
    assert db.usuarios.count_documents({}) >= 1
