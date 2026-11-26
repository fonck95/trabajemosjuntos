"""Regresiones de la revisión adversarial de las planillas físicas en el chat (área B2): las fotos que llegan a una
conversación que no tiene las herramientas de planillas, la marca de datos de una fila sin nombre ni cédula, una hoja
larga que ni sola cabía en la respuesta de leer_planilla y las correcciones aprobadas que se escribían sobre una
planilla que ya no era la de la tarjeta. Solo personas y fotos inventadas."""
import json

import pytest

import ayudas_agente as aa
from app import planillas as pl
from app.agente import bucle, proveedores
from app.agente import conversaciones as conv_db
from app.agente.herramientas import planillas as hp
from app.agente.herramientas.base import ErrorHerramienta
from ayudas_agente import T, ndjson, sse
from ayudas_planillas import fila, lectura_json
from ayudas_planillas_chat import al_modelo, foto_distinta, foto_leida, leer_con, roles_planillas, subir_sin_leer

H = {h.nombre: h for h in hp.HERRAMIENTAS}


@pytest.fixture
def ctx_de(sesion):
    abiertos = []

    def hacer(cli, **kw):
        c = aa.contexto(sesion.app, cli, **kw)
        abiertos.append(c)
        return c

    yield hacer
    for c in abiertos:
        aa.correr(sesion, c.api.cerrar)


def _enviar(c, texto="", adjuntos=(), conversacion=None):
    r = c.post("/api/agente/mensajes", json={"conversacion": conversacion, "texto": texto, "adjuntos": list(adjuntos)})
    return r, (ndjson(r.text) if r.status_code == 200 else [])


def _leer(cliente, ctx, ids):
    return al_modelo(aa.correr(cliente, aa.ejecutar, H["leer_planilla"], ctx, {"ids": ids}))


def test_fotos_en_una_conversacion_creada_sin_las_herramientas_de_planillas(cliente, sesion, monkeypatch):
    app = sesion.app
    api = aa.encender(app, sse(T("Hola.")), sse(T("Revíselas en Importar y exportar.")))
    roles_planillas(app, "coordinador")  # la conversación se crea sin las herramientas de planillas (congeladas)
    r, ev = aa.enviar(sesion, "Hola")
    assert r.status_code == 200, r.text
    cid = next(e for e in ev if e["tipo"] == "inicio")["conversacion"]
    roles_planillas(app, "admin", "coordinador")  # después se le habilitan: la foto se acepta en esa conversación
    pid = subir_sin_leer(sesion, monkeypatch)
    r, _ = _enviar(sesion, "Revisa esta", [pid], conversacion=cid)
    assert r.status_code == 200, r.text
    peticion = api.peticiones[1]["json"]
    assert "leer_planilla" not in [t["name"] for t in peticion["tools"]]
    fotos = peticion["messages"][-1]["content"][1]["text"]
    # No se le pide usar una herramienta que no tiene: se le dice que no la tiene
    assert fotos.startswith("<fotos_adjuntas>") and pid in fotos
    assert "no tienes las herramientas de fotos" in fotos and "leer_planilla" not in fotos


def test_una_fila_sin_nombre_ni_cedula_tambien_marca_la_conversacion(cliente, sesion, monkeypatch, ctx_de):
    db = sesion.app.state.db
    pid = foto_leida(cliente, sesion, monkeypatch, [
        fila(1, celular="3105559911", direccion="CALLE INVENTADA 45", barrio="CENTRO", ilegibles=["nombre", "cedula"])])
    db.agente_conversaciones.insert_one({"_id": 51, "uid": 0, "personas": []})
    m = _leer(cliente, ctx_de(sesion, conversacion_id=51), [pid])
    (f,) = m["planillas"][0]["filas"]
    assert "nombre" not in f and "cedula" not in f and f["celular"] == "···9911" and f["direccion"]
    # Recibió el teléfono (enmascarado) y la dirección de alguien: ni voz clonada ni proyección
    assert conv_db.tiene_personas(db, 51)
    # Lo que no trae datos de nadie (las filas de una planilla ya cargada: número y estado) no marca
    db.agente_conversaciones.insert_one({"_id": 52, "uid": 0, "personas": []})
    sin = foto_leida(cliente, sesion, monkeypatch, [fila(1, nombre="SIN DATOS INVENTADO")], datos=foto_distinta(1))
    db.planillas.update_one({"_id": sin}, {"$set": {"estado": "cargada", "lectura": None, "cargadas": {
        "1": {"persona_id": None, "estado": "sin_nombre"}}}})
    assert _leer(cliente, ctx_de(sesion, conversacion_id=52), [sin])["planillas"][0]["filas"] == [
        {"n": 1, "estado": "cargada", "resultado": "sin_nombre"}]
    assert not conv_db.tiene_personas(db, 52)


def _hoja_larga(n: int) -> list[dict]:
    return [fila(i, cedula=f"90062{i:05d}", tipo_documento="CC", nombre=f"PERSONA INVENTADA NUMERO {i} DE LA HOJA",
                 celular=f"31066{i:05d}", sexo="F", edad="40", direccion=f"CALLE INVENTADA {i} CON CARRERA {i} CASA",
                 barrio="BARRIO INVENTADO DEL CENTRO", puesto="INSTITUCION EDUCATIVA INVENTADA", mesa="12",
                 autorizacion="si", medio="escrito", canales="llamada, whatsapp, mensaje", mayor_18="si",
                 planillero="ana.campo", fecha="02/11/2026") for i in range(1, n + 1)]


def test_una_hoja_que_ni_sola_cabe_entera_muestra_las_filas_que_caben(cliente, sesion, monkeypatch, ctx_de):
    db = sesion.app.state.db
    pid = foto_leida(cliente, sesion, monkeypatch, _hoja_larga(90))
    db.agente_conversaciones.insert_one({"_id": 53, "uid": 0, "personas": []})
    m = _leer(cliente, ctx_de(sesion, conversacion_id=53), [pid])
    (p,) = m["planillas"]
    # Antes: ninguna fila y «llama leer_planilla solo con este id» (ya estaba sola): no la podía leer nunca
    assert len(p["filas"]) > 30 and p["filas_omitidas"] == 90 - len(p["filas"])
    assert [f["n"] for f in p["filas"]] == list(range(1, len(p["filas"]) + 1))
    assert "solo con este id" not in p["nota"] and "Importar y exportar" in p["nota"]
    assert len(json.dumps(m, ensure_ascii=False)) < 40_000 and conv_db.tiene_personas(db, 53)
    for f in p["filas"]:
        assert f["cedula"].startswith("···") and f["celular"].startswith("···")
    # Con otra antes en la misma llamada: también las que caben, y que sola caben más
    otra = foto_leida(cliente, sesion, monkeypatch, _hoja_larga(3), datos=foto_distinta(2))
    primera, segunda = _leer(cliente, ctx_de(sesion), [otra, pid])["planillas"]
    assert len(primera["filas"]) == 3 and 0 < len(segunda["filas"]) <= len(p["filas"])
    assert "Sola, en otra llamada, caben más." in segunda["nota"]


def test_las_correcciones_no_se_escriben_si_la_planilla_ya_no_es_la_de_la_tarjeta(cliente, sesion, monkeypatch,
                                                                                    ctx_de):
    db = sesion.app.state.db
    pid = foto_leida(cliente, sesion, monkeypatch, [
        fila(1, cedula="9007100001", nombre="ANA INVENTADA RELEIDA", celular="3108880001"),
        fila(3, cedula="9007100003", nombre="CARLA INVENTADA RELEIDA", celular="3108880003", dudosos=["celular"])])
    db.agente_conversaciones.insert_one({"_id": 61, "uid": 0, "personas": []})
    ctx = ctx_de(sesion, conversacion_id=61, tool_use_id="toolu_releida")
    h = H["cargar_planilla"]
    a = h.validar({"id": pid, "filas": [3], "correcciones": [{"fila": 3, "campo": "celular", "valor": "3108880033"}]})
    conf = aa.correr(cliente, h.confirmar, ctx, a)
    assert "CARLA INVENTADA RELEIDA" in json.dumps(conf.detalle, ensure_ascii=False)
    guardada = h.validar(bucle._entrada_pendiente(h, a, None))
    # Entre la tarjeta y la aprobación, la foto se relee y en la fila 3 queda otra persona
    with monkeypatch.context() as m:
        m.setattr(pl, "programar", lambda *x, **k: None)
        m.setattr(proveedores, "clave_para_nueva", lambda cfg, db_: "anthropic")
        r = sesion.post(f"/api/planillas/{pid}/leer", json={})
        assert r.status_code == 202, r.text
    leer_con(cliente, monkeypatch, pid, lectura_json([
        fila(1, cedula="9007100001", nombre="ANA INVENTADA RELEIDA", celular="3108880001"),
        fila(3, cedula="9007100099", nombre="OTRO INVENTADO DISTINTO", celular="3108880099", dudosos=["celular"])]))
    with pytest.raises(ErrorHerramienta) as e:
        aa.correr(cliente, h.ejecutar, ctx, guardada)
    assert e.value.codigo == "cambiada" and "Tampoco se escribieron las correcciones" in e.value.mensaje
    # El celular aprobado para CARLA no quedó en la fila de OTRO (ni le quitó la marca de dudoso)
    fila3 = next(f for f in sesion.get(f"/api/planillas/{pid}").json()["filas"] if f["n"] == 3)
    assert fila3["valores"]["celular"] == "3108880099" and fila3["dudosos"] == ["celular"]
    assert not fila3["corregidos"] and db.personas.count_documents({}) == 0


def test_sin_cambios_las_correcciones_aprobadas_se_escriben_y_se_carga(cliente, sesion, monkeypatch, ctx_de):
    db = sesion.app.state.db
    pid = foto_leida(cliente, sesion, monkeypatch, [
        fila(3, cedula="9007200003", nombre="CARLA INVENTADA SIGUE", celular="3108870003", dudosos=["celular"])])
    db.agente_conversaciones.insert_one({"_id": 62, "uid": 0, "personas": []})
    ctx = ctx_de(sesion, conversacion_id=62, tool_use_id="toolu_sigue")
    h = H["cargar_planilla"]
    a = h.validar({"id": pid, "correcciones": [{"fila": 3, "campo": "celular", "valor": "3108870033"}]})
    aa.correr(cliente, h.confirmar, ctx, a)
    m = al_modelo(aa.correr(cliente, h.ejecutar, ctx, h.validar(bucle._entrada_pendiente(h, a, None))))
    assert m["correcciones"] == 1 and [(f["n"], f["estado"]) for f in m["filas"]] == [(3, "nueva")]
    assert "3108870033" in json.dumps(db.personas.find_one({"cedula": "9007200003"})["telefonos"], default=str)
