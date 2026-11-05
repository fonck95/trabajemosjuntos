"""Variantes de los hallazgos de seguridad que encontró la revisión de cf46ade, reproducidas como ataques o carreras
deterministas (solo datos inventados):

1. Unión y autorización: si el destino (o el origen) dice «no» mientras se unen, la unión no lo vuelve «sí»: «el no
   gana» siempre (2.6, Ley 1581).
2. Cédula «en traspaso»: un alta con la cédula que una unión está moviendo da 409; si otra ficha la toma de todos
   modos, la unión responde 409 sin dejar nada a medias, el origen queda a la vista de A como conflicto y el panel
   sigue arrancando (`reparar_fusiones` nunca aborta el arranque).
3. P no sondea ni cambia los teléfonos ocultos de un menor por PATCH /personas ni por POST …/telefonos: la misma
   respuesta para todos los menores y sin tocar sus números.
4. «Mis registros recientes» de Mi trabajo cuenta igual que su enlace a Habitantes (con el alcance).
"""
from __future__ import annotations

import logging

import pytest

from ayudas_g3 import persona

CED_ORIGEN = "71000001"


def _si(db, pid: int, canales=("llamada",), ts: str = "2026-01-01T00:00:00+00:00") -> None:
    """Un «sí» escrito que habilita el contacto (evento de 1.6) y los campos derivados."""
    from app import db as bd
    db.autorizaciones.insert_one(bd.autorizacion_doc(db, pid, "si", "escrito", canales=list(canales),
                                                     mayor_declarado=True, evidencia="Planilla 1, folio 1", ts=ts))
    bd.derivar(db, [pid])


def _no(db, pid: int, **campos) -> None:
    """El «no» del titular como lo registra el panel: el evento y luego la ficha derivada."""
    from app import db as bd
    db.autorizaciones.insert_one(bd.autorizacion_doc(db, pid, "no", "verbal_presencial", **campos))
    bd.derivar(db, [pid], reconciliar=False)


def _dos_con_si(db, lid: int | None = None) -> tuple[int, int]:
    """Destino y origen de una unión: la misma persona inventada, las dos con «sí» y habilitadas."""
    d = persona(db, nombre="MARIA INVENTADA REVOCA", cedula="51000001", tipo_documento="CC", lugar_id=lid)
    o = persona(db, nombre="MARIA INVENTADA REVOCA B", tipo_documento="CC", lugar_id=lid)
    _si(db, d)
    _si(db, o, ts="2026-01-02T00:00:00+00:00")
    assert db.personas.find_one({"_id": d})["contacto_habilitado"] is True
    return d, o


def _envolver(monkeypatch, modulo, nombre: str, antes):
    """Reemplaza `modulo.nombre` por una versión que la primera vez llama a `antes(*args)` y luego a la original."""
    original = getattr(modulo, nombre)
    hecho = []

    def envuelta(*args, **kw):
        if not hecho:
            hecho.append(True)
            antes(*args, **kw)
        return original(*args, **kw)

    monkeypatch.setattr(modulo, nombre, envuelta)
    return hecho


def _no_contactable(db, pid: int) -> None:
    p = db.personas.find_one({"_id": pid})
    assert p["consentimiento"] == "no" and p["contacto_habilitado"] is False, \
        (p["consentimiento"], p["contacto_habilitado"])
    assert p["autorizacion_ultima"]["estado"] in ("no", "revocada")


# ───────────────────────────── 1. Unión y autorización: el «no» gana ─────────────────────────────

def test_union_no_pisa_el_no_que_el_destino_dice_al_entrar(sesion, como, monkeypatch):
    """El caso de la revisión (por HTTP, 50 de 120): K une D con O mientras P registra el «no» de D."""
    from app import db as bd
    db = sesion.app.state.db
    lid = db.lugares.find_one({"tipo": "barrio"})["_id"]
    destino, origen = _dos_con_si(db, lid)
    p = como("planillero", asignacion={"lugares": [lid], "areas": []})
    codigos = []
    _envolver(monkeypatch, bd, "_unir_en", lambda *a, **k: codigos.append(
        p.post(f"/api/personas/{destino}/autorizacion", json={"estado": "no"}).status_code))
    r = sesion.post(f"/api/personas/{destino}/fusionar", json={"con_id": origen})
    assert codigos == [200]
    assert r.status_code == 200, r.text[:300]
    _no_contactable(db, destino)
    assert sesion.get(f"/api/personas/{destino}").json()["consentimiento"] == "no"
    assert db.personas.find_one({"_id": origen})["nombre"] == "FUSIONADA"


@pytest.mark.parametrize("momento", ["al_escribir_la_union", "al_derivar"])
def test_union_no_pisa_un_no_que_se_ordena_antes_del_evento_de_union(bases, monkeypatch, momento):
    """El «no» tomó su `_id` y su `ts` antes que el evento «fusion» pero se escribió después de que la unión leyó los
    eventos: queda antes en el orden (ts, _id), y aun así gana. Llega justo después del evento «fusion», o cuando la
    unión ya lo comprobó y va a derivar la ficha."""
    import pymongo.collection
    from app import db as bd
    db = bases()
    destino = persona(db, nombre="LUCIA INVENTADA ORDEN", cedula="51000002", tipo_documento="CC")
    origen = persona(db, nombre="LUCIA INVENTADA ORDEN B", tipo_documento="CC")
    _si(db, destino, canales=("llamada",))
    _si(db, origen, canales=("llamada", "whatsapp"), ts="2026-01-02T00:00:00+00:00")  # la unión deja los comunes
    reservado = bd.siguiente_id(db, "autorizaciones")
    original = pymongo.collection.Collection.insert_one
    union = []

    def no_tardio(ts: str) -> None:
        original(db.autorizaciones, bd.autorizacion_doc(db, destino, "no", "verbal_presencial", _id=reservado, ts=ts))
        bd.derivar(db, [destino], reconciliar=False)  # lo que hace quien registra el «no»

    def insertar(self, doc, *a, **k):
        r = original(self, doc, *a, **k)
        if self.name == "autorizaciones" and doc.get("medio") == "fusion" and not union:
            union.append(doc)
            if momento == "al_escribir_la_union":
                no_tardio(doc["ts"])
        return r

    monkeypatch.setattr(pymongo.collection.Collection, "insert_one", insertar)
    if momento == "al_derivar":
        _envolver(monkeypatch, bd, "derivar", lambda *a, **k: no_tardio(union[0]["ts"]))
    bd.fusionar(db, destino, origen, "sistema")
    monkeypatch.undo()
    # Hubo un evento «fusion» con «sí» (los canales comunes) y el «no» quedó antes que él en el orden
    assert [u["estado"] for u in union] == ["si"]
    assert (union[0]["ts"], reservado) < (union[0]["ts"], union[0]["_id"])
    _no_contactable(db, destino)
    bd.derivar(db, [destino])  # y sigue así al volver a derivar (la reconciliación tampoco lo cambia)
    _no_contactable(db, destino)


@pytest.mark.parametrize("como_deriva", ["bd.derivar", "derivar_autorizacion"])
def test_una_derivacion_con_lectura_vieja_no_deja_el_si_encima_del_no(bases, monkeypatch, como_deriva):
    """Una derivación leyó los eventos («sí») y escribe la ficha después de que otra registró un «no» y lo derivó: lo
    escrito no puede quedar en «sí» (la unión deriva así el destino; el registro de una autorización también)."""
    import pymongo.collection
    from app import db as bd
    from app.api import personas as per
    db = bases()
    pid = persona(db, nombre="DORA INVENTADA VIEJA", cedula="51000004", tipo_documento="CC")
    _si(db, pid)
    db.personas.update_one({"_id": pid}, {"$set": {"consentimiento": "pendiente"}})  # que haya algo que escribir
    original_bulk = pymongo.collection.Collection.bulk_write
    original_update = pymongo.collection.Collection.update_one
    hecho = []

    def antes_de_escribir(self, ops_o_filtro, cambios=None) -> None:
        texto = repr(ops_o_filtro) + repr(cambios)
        if self.name == "personas" and "consentimiento" in texto and not hecho:
            hecho.append(True)
            _no(db, pid)  # el otro registra el «no» y deriva antes de que esta escritura llegue

    def bulk(self, ops, *a, **k):
        antes_de_escribir(self, ops)
        return original_bulk(self, ops, *a, **k)

    def update(self, filtro, cambios, *a, **k):
        antes_de_escribir(self, filtro, cambios)
        return original_update(self, filtro, cambios, *a, **k)

    monkeypatch.setattr(pymongo.collection.Collection, "bulk_write", bulk)
    monkeypatch.setattr(pymongo.collection.Collection, "update_one", update)
    if como_deriva == "bd.derivar":
        bd.derivar(db, [pid], reconciliar=False)
    else:
        per.derivar_autorizacion(db, pid)
    monkeypatch.undo()
    assert hecho == [True]
    _no_contactable(db, pid)


def test_union_no_pierde_el_no_que_el_origen_dice_tarde(bases, monkeypatch):
    """El origen dice «no» cuando la unión ya movió sus eventos (su evento llega a la ficha ya unida)."""
    from app import db as bd
    db = bases()
    destino = persona(db, nombre="ROSA INVENTADA TARDE", cedula="51000003", tipo_documento="CC")
    origen = persona(db, nombre="ROSA INVENTADA TARDE B", tipo_documento="CC")
    _si(db, destino)
    _si(db, origen, ts="2026-01-02T00:00:00+00:00")
    _envolver(monkeypatch, bd, "_reapuntar_coincidencias", lambda db_, o, d, marca: _no(db_, o))
    bd.fusionar(db, destino, origen, "sistema")
    _no_contactable(db, destino)
    assert db.autorizaciones.count_documents({"persona_id": origen}) == 0


def test_no_registrado_en_una_ficha_ya_unida_llega_al_destino(sesion, monkeypatch):
    """El «no» pasó la comprobación de ficha activa antes de la unión y se escribió después: va a la ficha unida."""
    from app import db as bd
    from app.api import personas as per
    db = sesion.app.state.db
    destino, origen = _dos_con_si(db)
    _envolver(monkeypatch, per, "registrar_autorizacion",
              lambda db_, pid, *a, **k: bd.fusionar(db_, destino, origen, "sistema"))
    r = sesion.post(f"/api/personas/{origen}/autorizacion", json={"estado": "no"})
    assert db.personas.find_one({"_id": origen})["fusionada_en"] == destino
    assert r.status_code in (200, 409), r.text[:300]
    assert db.autorizaciones.count_documents({"persona_id": origen}) == 0
    _no_contactable(db, destino)


# ───────────────────────────── 2. Cédula «en traspaso» ─────────────────────────────

def _union_cortada(db, cedula_destino: str | None = None) -> tuple[int, int]:
    """Una unión cortada después de marcar el origen (su cédula, en traspaso)."""
    destino = persona(db, nombre="LUZ INVENTADA DESTINO", cedula=cedula_destino, tipo_documento="CC")
    origen = persona(db, nombre="LUZ INVENTADA ORIGEN", cedula=CED_ORIGEN, tipo_documento="CC")
    db.personas.update_one({"_id": origen}, {"$set": {"fusionada_en": destino, "cedula": None,
                                                      "cedula_en_traspaso": CED_ORIGEN}})
    return destino, origen


def test_cedula_en_traspaso_esta_ocupada(sesion, como):
    db = sesion.app.state.db
    lid = db.lugares.find_one({"tipo": "barrio"})["_id"]
    destino, origen = _union_cortada(db)
    otra = persona(db, nombre="TERCERA PERSONA INVENTADA", lugar_id=lid, tipo_documento="CC")
    p = como("planillero", asignacion={"lugares": [lid], "areas": []})
    for c in (sesion, p):
        r = c.post("/api/personas", json={"nombre": "LUZ INVENTADA OTRA ALTA", "cedula": CED_ORIGEN, "lugar_id": lid})
        assert r.status_code == 409 and r.json()["detail"]["codigo"] == "cedula_ocupada", r.text[:300]
        # A ve a qué ficha va la cédula (seg. 5, caso 4); P no
        if c is sesion:
            assert (r.json()["detail"]["id"], r.json()["detail"]["origen"]) == (destino, origen)
        else:
            assert "id" not in r.json()["detail"] and "origen" not in r.json()["detail"]
        r = c.patch(f"/api/personas/{otra}", json={"cedula": CED_ORIGEN})
        assert r.status_code == 409 and r.json()["detail"]["codigo"] == "cedula_ocupada", r.text[:300]
    assert db.personas.count_documents({"cedula": CED_ORIGEN}) == 0


def test_alta_en_la_ventana_de_la_union_da_409_y_la_union_termina(sesion, como, monkeypatch):
    from app import db as bd
    db = sesion.app.state.db
    a = como("admin")
    destino = persona(db, nombre="LUZ INVENTADA DESTINO", tipo_documento="CC")
    origen = persona(db, nombre="LUZ INVENTADA ORIGEN", cedula=CED_ORIGEN, tipo_documento="CC")
    codigos = []
    _envolver(monkeypatch, bd, "_unir_en", lambda *x, **k: codigos.append(a.post(
        "/api/personas", json={"nombre": "LUZ INVENTADA OTRA ALTA", "cedula": CED_ORIGEN}).status_code))
    r = sesion.post(f"/api/personas/{destino}/fusionar", json={"con_id": origen})
    assert codigos == [409]
    assert r.status_code == 200, r.text[:300]
    assert db.personas.find_one({"_id": destino})["cedula"] == CED_ORIGEN
    assert db.personas.find_one({"_id": origen})["nombre"] == "FUSIONADA"


def _conflicto_visible(sesion, db, origen: int, duena: int) -> None:
    o = db.personas.find_one({"_id": origen})
    assert o["fusionada_en"] is None and o["cedula"] is None and "cedula_en_traspaso" not in o
    assert o["nombre"] == "LUZ INVENTADA ORIGEN"
    lista = sesion.get("/api/conflictos").json()
    c = next(x for x in lista if x["persona"] and x["persona"]["id"] == origen)
    assert c["cedula"] == CED_ORIGEN and c["duena"]["id"] == duena


def test_union_con_la_cedula_tomada_en_la_ventana_no_queda_a_medias(sesion, monkeypatch):
    """Otra ficha toma la cédula del origen mientras se une (sin pasar por el alta): 409, nada a medias, el origen
    vuelve sin la cédula y con un conflicto para A, y el panel sigue arrancando."""
    from app import db as bd
    db = sesion.app.state.db
    destino = persona(db, nombre="LUZ INVENTADA DESTINO", tipo_documento="CC")
    origen = persona(db, nombre="LUZ INVENTADA ORIGEN", cedula=CED_ORIGEN, tipo_documento="CC")
    otra = []
    _envolver(monkeypatch, bd, "_unir_en", lambda *a, **k: otra.append(
        persona(db, nombre="LUZ INVENTADA OTRA", cedula=CED_ORIGEN, tipo_documento="CC")))
    r = sesion.post(f"/api/personas/{destino}/fusionar", json={"con_id": origen})
    assert r.status_code == 409, r.text[:300]
    d = db.personas.find_one({"_id": destino})
    assert d["cedula"] is None and d["nombre"] == "LUZ INVENTADA DESTINO" and not d.get("alternos")
    _conflicto_visible(sesion, db, origen, otra[0])
    monkeypatch.undo()
    bd.inicializar(db)  # el arranque no aborta
    assert bd.reparar_fusiones(db) == 0


@pytest.mark.parametrize("cedula_destino", [None, "61000002"])
def test_reparar_union_cortada_con_la_cedula_tomada_no_aborta(sesion, cedula_destino):
    """Una unión cortada cuya cédula de origen tomó otra ficha (con el destino sin cédula: E11000 al escribirlo; con
    otra cédula: son dos personas): el arranque sigue y el origen queda a la vista de A."""
    from app import db as bd
    db = sesion.app.state.db
    destino, origen = _union_cortada(db, cedula_destino)
    otra = persona(db, nombre="LUZ INVENTADA OTRA", cedula=CED_ORIGEN, tipo_documento="CC")
    bd.inicializar(db)
    assert bd.reparar_fusiones(db) == 0
    assert db.personas.find_one({"_id": destino})["cedula"] == cedula_destino
    _conflicto_visible(sesion, db, origen, otra)


def test_reparar_fusiones_registra_y_sigue_con_un_error_inesperado(bases, monkeypatch, caplog):
    from app import db as bd
    db = bases()
    _union_cortada(db)
    d2, o2 = _union_cortada(db)

    def falla(db_, destino, o, quien, d_antes=None):
        raise RuntimeError("falla inventada")

    monkeypatch.setattr(bd, "_unir_en", falla)
    with caplog.at_level(logging.WARNING, logger="panel"):
        assert bd.reparar_fusiones(db) == 0
        bd.inicializar(db)
    assert sum("falla inventada" in r.getMessage() for r in caplog.records) >= 2
    assert db.personas.find_one({"_id": o2})["fusionada_en"] == d2  # queda para el próximo arranque


# ───────────────────────────── 3. Teléfonos ocultos de un menor ─────────────────────────────

def _menores(db, lid: int) -> tuple[int, int]:
    """Dos menores del mismo barrio: uno con dos números usables y otro sin ninguno."""
    from app import modelo
    con = persona(db, nombre="ABIGAIL INVENTADA CON", cedula="1012345601", tipo_documento="TI", lugar_id=lid)
    tels = [modelo.telefono_nuevo(n, "panel", "2026-01-01") for n in ("3160700033", "3180700033")]
    db.personas.update_one({"_id": con}, {"$set": {"telefonos": tels, **modelo.derivar_telefonos(tels)}})
    sin = persona(db, nombre="ABIGAIL INVENTADA SIN", cedula="1012345602", tipo_documento="TI", lugar_id=lid)
    return con, sin


def _respuesta(r) -> tuple:
    return r.status_code, r.json()


def test_planillero_no_sondea_los_telefonos_de_un_menor_por_patch(sesion, como):
    db = sesion.app.state.db
    lid = db.lugares.find_one({"tipo": "barrio"})["_id"]
    con, sin = _menores(db, lid)
    antes = {pid: db.personas.find_one({"_id": pid})["telefonos"] for pid in (con, sin)}
    p = como("planillero", asignacion={"lugares": [lid], "areas": []})
    for cuerpo in ({"telefono2": None}, {"telefono": None}, {"observaciones": "prueba", "telefono2": None},
                   {"telefono": "3001112233"}, {"telefono2": "3001112233"}):
        r_con = _respuesta(p.patch(f"/api/personas/{con}", json=cuerpo))
        r_sin = _respuesta(p.patch(f"/api/personas/{sin}", json=cuerpo))
        assert r_con == r_sin, (cuerpo, r_con, r_sin)
        assert r_con[0] == 403, (cuerpo, r_con)
    for pid in (con, sin):
        assert db.personas.find_one({"_id": pid})["telefonos"] == antes[pid]
        # Lo que la ficha y la fila de P dicen de sus teléfonos tampoco depende de si los tiene
        f = p.get(f"/api/personas/{pid}").json()
        assert "telefono" not in f["editables"] and "telefono2" not in f["editables"]
        assert "telefono" not in f["faltan"]
        fila = next(x for x in p.get("/api/personas", params={"q": "ABIGAIL"}).json()["filas"] if x["id"] == pid)
        assert "telefono" not in fila["faltan"] and fila["telefonos_n"] == 0
    # Lo demás de la ficha de un menor sí lo edita
    assert p.patch(f"/api/personas/{sin}", json={"observaciones": "prueba"}).status_code == 200


def test_planillero_no_cambia_los_telefonos_ocultos_de_un_menor(sesion, como):
    db = sesion.app.state.db
    lid = db.lugares.find_one({"tipo": "barrio"})["_id"]
    con, sin = _menores(db, lid)
    antes = {pid: db.personas.find_one({"_id": pid})["telefonos"] for pid in (con, sin)}
    p = como("planillero", asignacion={"lugares": [lid], "areas": []})
    for cuerpo in ({"numero": "3001112233", "principal": True, "anterior_no_usa": True},
                   {"numero": "3001112233"}, {"numero": "3160700033"}):
        r_con = _respuesta(p.post(f"/api/personas/{con}/telefonos", json=cuerpo))
        r_sin = _respuesta(p.post(f"/api/personas/{sin}/telefonos", json=cuerpo))
        assert r_con == r_sin, (cuerpo, r_con, r_sin)
        assert r_con[0] == 403, (cuerpo, r_con)
    for pid in (con, sin):
        assert db.personas.find_one({"_id": pid})["telefonos"] == antes[pid]
    assert db.personas.find_one({"_id": con})["telefono"] == "3160700033"


def test_planillero_sigue_manejando_los_telefonos_de_un_adulto(sesion, como):
    db = sesion.app.state.db
    lid = db.lugares.find_one({"tipo": "barrio"})["_id"]
    adulto = persona(db, nombre="EUSTAQUIO INVENTADO ADULTO", cedula="88000111", tipo_documento="CC", lugar_id=lid)
    p = como("planillero", asignacion={"lugares": [lid], "areas": []})
    assert "telefono" in p.get(f"/api/personas/{adulto}").json()["editables"]
    assert p.patch(f"/api/personas/{adulto}", json={"telefono": "3001234567"}).status_code == 200
    r = p.post(f"/api/personas/{adulto}/telefonos", json={"numero": "3007654321", "principal": True,
                                                          "anterior_no_usa": True})
    assert r.status_code == 200, r.text[:300]
    tels = {t["numero"]: t.get("estado") for t in db.personas.find_one({"_id": adulto})["telefonos"]}
    assert tels == {"3001234567": "no_usa", "3007654321": "sin_verificar"}


# ───────────────────────────── 4. «Mis registros recientes» ─────────────────────────────

def test_mis_registros_recientes_cuenta_como_su_enlace(sesion, como):
    db = sesion.app.state.db
    dentro, fuera = [x["_id"] for x in db.lugares.find({"tipo": "barrio"}).limit(2)]
    p = como("planillero", asignacion={"lugares": [dentro], "areas": []})
    r = p.post("/api/personas", json={"nombre": "TOMASA INVENTADA DENTRO", "lugar_id": dentro})
    assert r.status_code == 201, r.text[:300]
    otra = persona(db, nombre="TOMASA INVENTADA FUERA", lugar_id=fuera, tipo_documento="CC")
    db.personas.update_one({"_id": otra}, {"$set": {"actualizado_por": {"uid": p.uid, "usuario": p.usuario,
                                                                        "ts": "2026-11-01T00:00:00+00:00"}}})
    tarjeta = next(x for x in p.get("/api/trabajo").json()["listas"] if x["clave"] == "mis_recientes")
    total = p.get("/api/personas", params={"mios": 1, "orden": "reciente"}).json()["total"]
    assert tarjeta["n"] == total == 1
    # A, viendo Mi trabajo de ese planillero, cuenta lo mismo
    tarjeta_a = next(x for x in sesion.get("/api/trabajo", params={"uid": p.uid}).json()["listas"]
                     if x["clave"] == "mis_recientes")
    assert tarjeta_a["n"] == 1
