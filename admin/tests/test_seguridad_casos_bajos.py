"""Los 8 casos de severidad baja que dejó la revisión adversarial de ccd650e (solo datos inventados):

1. P no saca a un menor de la minoría (edad, fecha de nacimiento o tipo de documento) para ver sus teléfonos, y lo que
   edita de un menor se le responde como de un menor.
2. Un reclamo (supresión, revocatoria) que llega durante una unión deja «reclamo en trámite» en la ficha unida: el
   consultor no llama a quien pidió suprimir sus datos.
3. La completitud que P ve de un menor no dice si tiene teléfono (al mostrarla, al ordenar ni al filtrar).
4. Una unión cortada que ya no puede terminar no deja la cédula ocupada para siempre; un error inesperado al
   repararla queda a la vista de A, y el 409 de A dice qué ficha tiene la cédula.
5. La importación ve la cédula que una unión está moviendo, y el 409 de una cédula tomada en la ventana lo dice.
6. «Aplicar» el conflicto de una unión que no se hizo devuelve la cédula con su procedencia de antes.
7. P y C que registran algo en una ficha que se une mientras tanto reciben 409 `registrado: true` con el id final.
8. «Ver como» de Mi trabajo: los enlaces de las tarjetas llevan el alcance del usuario (`como`, solo A y K).
"""
from __future__ import annotations

import json
from urllib.parse import parse_qsl, urlsplit

import pytest

from ayudas_g3 import autorizada, coordinador, persona, tomar
from conftest import excel_cedulas

CED = "71000077"
HOY = "2026-01-01"


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


def _despues(monkeypatch, modulo, nombre: str, despues, cuando=lambda *a, **k: True):
    """Como `_envolver`, pero `despues(*args)` corre una vez después de la original (cuando `cuando(*args)`)."""
    original = getattr(modulo, nombre)
    hecho = []

    def envuelta(*args, **kw):
        r = original(*args, **kw)
        if not hecho and cuando(*args, **kw):
            hecho.append(True)
            despues(*args, **kw)
        return r

    monkeypatch.setattr(modulo, nombre, envuelta)
    return hecho


def _telefonos(db, pid: int, *numeros: str) -> None:
    from app import modelo
    tels = [modelo.telefono_nuevo(n, "panel", HOY) for n in numeros]
    db.personas.update_one({"_id": pid}, {"$set": {"telefonos": tels, **modelo.derivar_telefonos(tels)}})


def _lid(db) -> int:
    return db.lugares.find_one({"tipo": "barrio"})["_id"]


# ───────────────────────────── 1. P no vuelve adulto a un menor ─────────────────────────────

def _menores(db, lid: int) -> dict[str, int]:
    """Tres menores con teléfono, creados por A: por la edad, por la tarjeta de identidad sin número y por la fecha."""
    from app import db as bd
    from app import modelo
    hoy = modelo.hoy_local().isoformat()
    ids = {"edad": persona(db, nombre="TOBIAS INVENTADO EDAD", edad=15, edad_ref=hoy, lugar_id=lid),
           "tipo_documento": persona(db, nombre="TOBIAS INVENTADO TI", tipo_documento="TI", lugar_id=lid),
           "fecha_nacimiento": persona(db, nombre="TOBIAS INVENTADO FECHA", fecha_nacimiento="2014-05-05",
                                       lugar_id=lid)}
    for i, pid in enumerate(ids.values()):
        _telefonos(db, pid, f"318434977{i}")
    bd.derivar(db, list(ids.values()))
    assert all(modelo.es_menor(db.personas.find_one({"_id": pid})) for pid in ids.values())
    return ids


CAMBIOS_ADULTO = {"edad": {"edad": 30}, "tipo_documento": {"tipo_documento": "CC"},
                  "fecha_nacimiento": {"fecha_nacimiento": "1990-03-03"}}


def _como_menor(f: dict) -> None:
    assert f["menor"] is True and f["telefonos"] == [] and f["telefono"] is None and f["telefono2"] is None, \
        (f.get("menor"), f.get("telefonos"))
    assert "telefono" not in f["editables"]


@pytest.mark.parametrize("campo", list(CAMBIOS_ADULTO))
def test_planillero_no_vuelve_adulto_a_un_menor(sesion, como, campo):
    db = sesion.app.state.db
    lid = _lid(db)
    pid = _menores(db, lid)[campo]
    antes = db.personas.find_one({"_id": pid})
    p = como("planillero", asignacion={"lugares": [lid], "areas": []})
    r = p.patch(f"/api/personas/{pid}", json=CAMBIOS_ADULTO[campo])
    assert r.status_code == 403, r.text[:300]
    assert "Pida la corrección al administrador" in r.json()["detail"]["mensaje"]
    assert "3184349" not in r.text
    d = db.personas.find_one({"_id": pid})
    assert {k: d.get(k) for k in ("edad", "tipo_documento", "fecha_nacimiento", "nac_aprox")} == \
        {k: antes.get(k) for k in ("edad", "tipo_documento", "fecha_nacimiento", "nac_aprox")}
    _como_menor(p.get(f"/api/personas/{pid}").json())
    # A sí lo corrige
    assert sesion.patch(f"/api/personas/{pid}", json=CAMBIOS_ADULTO[campo]).status_code == 200


def test_planillero_sigue_editando_un_menor_sin_sacarlo_de_la_minoria(sesion, como):
    db = sesion.app.state.db
    lid = _lid(db)
    ids = _menores(db, lid)
    p = como("planillero", asignacion={"lugares": [lid], "areas": []})
    r = p.patch(f"/api/personas/{ids['edad']}", json={"edad": 16})
    assert r.status_code == 200, r.text[:300]
    _como_menor(r.json())
    r = p.patch(f"/api/personas/{ids['tipo_documento']}", json={"edad": 12})
    assert r.status_code == 200, r.text[:300]
    _como_menor(r.json())


def test_lo_que_p_edita_de_un_menor_se_le_responde_como_de_un_menor(sesion, como, monkeypatch):
    """Mientras P guarda una observación de un menor, A corrige su edad (ya es adulto): la respuesta del PATCH de P no
    trae sus teléfonos."""
    from app import db as bd
    from app import modelo
    db = sesion.app.state.db
    lid = _lid(db)
    pid = _menores(db, lid)["edad"]
    p = como("planillero", asignacion={"lugares": [lid], "areas": []})

    def a_corrige(*_a, **_k):
        db.personas.update_one({"_id": pid}, {"$set": {"edad": 30, "edad_ref": modelo.hoy_local().isoformat()}})
        bd.derivar(db, [pid])

    _envolver(monkeypatch, bd, "recalcular_completitud", a_corrige)
    r = p.patch(f"/api/personas/{pid}", json={"observaciones": "Visita inventada"})
    assert r.status_code == 200, r.text[:300]
    assert not modelo.es_menor(db.personas.find_one({"_id": pid}))
    _como_menor(r.json())
    assert "3184349" not in r.text


# ───────────────────────────── 2. Reclamo que llega durante la unión ─────────────────────────────

def _dos_contactables(db, lid: int) -> tuple[int, int]:
    """Destino y origen de una unión: la misma persona inventada, las dos adultas, con «sí», habilitadas y con número."""
    from app import db as bd
    d = persona(db, nombre="FAUSTINA INVENTADA RECLAMO", cedula="52000001", lugar_id=lid)
    o = persona(db, nombre="FAUSTINA INVENTADA RECLAMO B", lugar_id=lid)
    for pid, n in ((d, "3005550001"), (o, "3005550002")):
        _telefonos(db, pid, n)
        autorizada(db, pid)
    bd.reconciliar_consentimiento(db, [d, o])
    bd.derivar(db, [d, o])
    return d, o


def _en_la_cola(db, pid: int, c, lid: int) -> bool:
    """¿La ficha está en la base de la cola del consultor `c` (asignado al barrio `lid`)?"""
    from app import acceso
    from app.api.filtros import base_cola
    quien = acceso.Quien(uid=c.uid, usuario=c.usuario, rol="consultor", permisos=acceso.PERMISOS["consultor"],
                         asignacion={"lugares": [lid], "areas": []})
    return db.personas.count_documents({"$and": [{"_id": pid}, base_cola(db, quien)]}, limit=1) > 0


def _fuera_de_la_cola(db, pid: int, c, lid: int) -> None:
    assert db.personas.find_one({"_id": pid})["reclamo_en_tramite"] is True
    assert not _en_la_cola(db, pid, c, lid)


def test_supresion_que_llega_al_entrar_a_la_union_deja_el_reclamo_en_el_destino(sesion, como, monkeypatch):
    """La supresión llega al origen después de que la unión lo leyó y antes de mover lo ligado."""
    from app import db as bd
    from app.api import personas as per
    db = sesion.app.state.db
    lid = _lid(db)
    destino, origen = _dos_contactables(db, lid)
    c = como("consultor", asignacion={"lugares": [lid], "areas": []})
    assert _en_la_cola(db, destino, c, lid)
    _envolver(monkeypatch, bd, "_unir_en", lambda *a, **k: per.crear_solicitud(
        db, origen, "supresion", None, "Pide suprimir sus datos (inventado)"))
    r = sesion.post(f"/api/personas/{destino}/fusionar", json={"con_id": origen})
    assert r.status_code == 200, r.text[:300]
    s = db.solicitudes.find_one({"tipo": "supresion"})
    assert s["persona_id"] == destino
    _fuera_de_la_cola(db, destino, c, lid)
    assert c.post(f"/api/trabajo/tomar/{destino}").status_code != 200


def test_supresion_por_http_en_una_ficha_que_se_une_queda_en_el_destino(sesion, como, monkeypatch):
    """A crea la supresión del origen; la unión termina entre la comprobación de ficha activa y la inserción."""
    from app import db as bd
    db = sesion.app.state.db
    lid = _lid(db)
    destino, origen = _dos_contactables(db, lid)
    c = como("consultor", asignacion={"lugares": [lid], "areas": []})
    _envolver(monkeypatch, bd, "siguiente_id", lambda db_, col, *a, **k: col == "solicitudes" and bd.fusionar(
        db_, destino, origen, "sistema"))
    r = sesion.post("/api/solicitudes", json={"persona_id": origen, "tipo": "supresion",
                                              "descripcion": "Pide suprimir sus datos (inventado)"})
    assert r.status_code == 201, r.text[:300]
    assert db.personas.find_one({"_id": origen})["nombre"] == "FUSIONADA"
    assert db.solicitudes.find_one({"_id": r.json()["id"]})["persona_id"] == destino
    _fuera_de_la_cola(db, destino, c, lid)
    assert r.json()["persona_id"] == destino


def test_consultor_registra_una_supresion_mientras_se_une_y_el_reclamo_queda_en_el_destino(sesion, como, monkeypatch):
    """C registra «solicitud de derechos: supresión» en el origen; la unión termina entre su escritura de la ficha y
    la del acercamiento. El acercamiento y la solicitud quedan en el destino, con la marca, y C recibe 409 `registrado`
    (caso 7) en vez de «la ficha se unió»."""
    from app.api import personas as per
    from app import db as bd
    db = sesion.app.state.db
    lid = _lid(db)
    destino, origen = _dos_contactables(db, lid)
    c = como("consultor", asignacion={"lugares": [lid], "areas": []})
    tomar(c, origen)
    _despues(monkeypatch, per, "escribir", lambda db_, pid, *a, **k: bd.fusionar(db_, destino, origen, "sistema"),
             cuando=lambda db_, pid, *a, **k: pid == origen)
    r = c.post(f"/api/personas/{origen}/acercamientos", json={
        "canal": "llamada", "resultado": "solicitud_derechos", "solicitud_tipo": "supresion", "telefono_indice": 0,
        "nota": "Pide suprimir sus datos (inventado)"})
    assert db.acercamientos.find_one({"resultado": "solicitud_derechos"})["persona_id"] == destino
    assert db.solicitudes.find_one({"tipo": "supresion"})["persona_id"] == destino
    assert db.solicitudes.count_documents({"persona_id": origen}) == 0
    _fuera_de_la_cola(db, destino, c, lid)
    assert r.status_code == 409, r.text[:300]
    det = r.json()["detail"]
    assert det["registrado"] is True and det["id"] == destino and det["codigo"] == "unida"



@pytest.mark.parametrize("rol", ["consultor", "planillero"])
def test_solicitud_de_derechos_sin_tipo_saca_a_la_persona_de_la_cola(sesion, como, rol):
    """La interfaz registra «Pidió consultar, corregir o borrar sus datos» sin solicitud_tipo: queda «otro», sin
    clasificar, y mientras esté abierta a esa persona no se le llama (sale de la cola)."""
    db = sesion.app.state.db
    lid = _lid(db)
    pid, _ = _dos_contactables(db, lid)
    quien = como(rol, asignacion={"lugares": [lid], "areas": []})
    canal = "llamada" if rol == "consultor" else "visita"
    if rol == "consultor":
        tomar(quien, pid)
    cuerpo = {"canal": canal, "resultado": "solicitud_derechos", "nota": "Pide saber qué datos tienen (inventado)"}
    if canal == "llamada":
        cuerpo["telefono_indice"] = 0
    r = quien.post(f"/api/personas/{pid}/acercamientos", json=cuerpo)
    assert r.status_code in (200, 201), r.text[:300]
    assert db.solicitudes.find_one({"persona_id": pid})["tipo"] == "otro"
    assert db.personas.find_one({"_id": pid})["reclamo_en_tramite"] is True
    otro = como("consultor", asignacion={"lugares": [lid], "areas": []}, usuario="cons.otro")
    _fuera_de_la_cola(db, pid, otro, lid)


# ───────────────────────────── 3. Completitud de un menor para P ─────────────────────────────

def _vistas_p(p, pid: int, nombre: str) -> tuple:
    ficha = p.get(f"/api/personas/{pid}").json()["completitud"]
    fila = next(x for x in p.get("/api/personas", params={"q": nombre}).json()["filas"] if x["id"] == pid)
    busqueda = next(x for x in p.get("/api/buscar", params={"q": nombre}).json() if x["id"] == pid)
    return ficha, fila["completitud"], busqueda["completitud"]


def _marcar(db, pid: int, numero: str, estado: str) -> None:
    from app import db as bd
    from app import modelo
    db.personas.update_one({"_id": pid}, modelo.expr_estado_telefono(numero, {"estado": estado}))
    bd.recalcular_completitud(db, [pid])


def test_completitud_de_un_menor_no_dice_si_tiene_telefono(sesion, como):
    from app import db as bd
    db = sesion.app.state.db
    lid = _lid(db)
    pid = persona(db, nombre="JACINTA INVENTADA MENOR", tipo_documento="TI", lugar_id=lid, sexo="F")
    _telefonos(db, pid, "3184340001")
    bd.recalcular_completitud(db, [pid])
    con = db.personas.find_one({"_id": pid})["completitud"]
    p = como("planillero", asignacion={"lugares": [lid], "areas": []})
    vista = _vistas_p(p, pid, "JACINTA")
    assert vista == (con - 14,) * 3
    _marcar(db, pid, "3184340001", "equivocado")
    assert db.personas.find_one({"_id": pid})["completitud"] == con - 14  # A sí ve el cambio
    assert _vistas_p(p, pid, "JACINTA") == vista
    assert sesion.get(f"/api/personas/{pid}").json()["completitud"] == con - 14
    _marcar(db, pid, "3184340001", "sin_verificar")
    assert _vistas_p(p, pid, "JACINTA") == vista
    assert sesion.get(f"/api/personas/{pid}").json()["completitud"] == con


def test_orden_y_filtro_por_completitud_no_dicen_si_un_menor_tiene_telefono(sesion, como):
    from app import db as bd
    db = sesion.app.state.db
    lid = _lid(db)
    ana = persona(db, nombre="ZACARIAS INVENTADO ANA", tipo_documento="TI", lugar_id=lid)
    beto = persona(db, nombre="ZACARIAS INVENTADO BETO", tipo_documento="TI", lugar_id=lid)
    _telefonos(db, beto, "3184340002")
    bd.recalcular_completitud(db, [ana, beto])
    p = como("planillero", asignacion={"lugares": [lid], "areas": []})

    def orden(o: str) -> list[int]:
        return [x["id"] for x in p.get("/api/personas", params={"q": "ZACARIAS", "orden": o}).json()["filas"]]

    for o in ("completitud", "-completitud", "por_llamar"):
        assert orden(o) == [ana, beto], o
    vista = db.personas.find_one({"_id": ana})["completitud"]
    filtradas = p.get("/api/personas", params={"q": "ZACARIAS", "completitud_max": vista}).json()
    assert filtradas["total"] == 2
    # El número pasa de Beto a Ana: el orden sigue siendo el del nombre
    _marcar(db, beto, "3184340002", "equivocado")
    _telefonos(db, ana, "3184340003")
    bd.recalcular_completitud(db, [ana, beto])
    for o in ("completitud", "-completitud", "por_llamar"):
        assert orden(o) == [ana, beto], o
    assert p.get("/api/personas", params={"q": "ZACARIAS", "completitud_max": vista}).json()["total"] == 2
    # A ve y ordena por la completitud real
    filas_a = sesion.get("/api/personas", params={"q": "ZACARIAS", "orden": "-completitud"}).json()["filas"]
    assert [x["id"] for x in filas_a] == [beto, ana]


# ───────────────────────────── 4. Unión cortada que no puede terminar ─────────────────────────────

def _union_sin_destino(db) -> tuple[int, int]:
    """Una unión cortada después de marcar el origen cuyo destino se suprimió (antes de que lo marcara)."""
    from app import db as bd
    destino = persona(db, nombre="RUFINA INVENTADA DESTINO", tipo_documento="CC")
    bd.suprimir(db, destino, "sistema")
    origen = persona(db, nombre="RUFINA INVENTADA ORIGEN", cedula=CED, tipo_documento="CC")
    db.personas.update_one({"_id": origen}, {"$set": {"fusionada_en": destino, "cedula": None,
                                                      "cedula_en_traspaso": CED}})
    return destino, origen


def _activa_con_cedula(db, pid: int) -> None:
    o = db.personas.find_one({"_id": pid})
    assert o["fusionada_en"] is None and o["cedula"] == CED and "cedula_en_traspaso" not in o
    assert o["nombre"] == "RUFINA INVENTADA ORIGEN"


def test_cedula_de_una_union_que_no_puede_terminar_no_queda_ocupada(sesion):
    """La cédula vuelve a su ficha, que A encuentra, y el 409 de A dice cuál es."""
    db = sesion.app.state.db
    _, origen = _union_sin_destino(db)
    r = sesion.post("/api/personas", json={"nombre": "RUFINA INVENTADA OTRA", "cedula": CED})
    assert r.status_code == 409, r.text[:300]
    assert r.json()["detail"]["id"] == origen and r.json()["detail"]["codigo"] == "cedula_ocupada"
    _activa_con_cedula(db, origen)
    assert [x["id"] for x in sesion.get("/api/buscar", params={"q": CED}).json()] == [origen]


def test_reparar_devuelve_el_origen_de_una_union_que_no_puede_terminar(bases):
    from app import db as bd
    db = bases()
    _, origen = _union_sin_destino(db)
    bd.reparar_fusiones(db)
    _activa_con_cedula(db, origen)
    assert not bd.cedula_en_traspaso(db, CED)


def test_error_inesperado_al_reparar_queda_a_la_vista_de_a(sesion, monkeypatch):
    from app import db as bd
    db = sesion.app.state.db
    destino = persona(db, nombre="RUFINA INVENTADA DESTINO", tipo_documento="CC")
    origen = persona(db, nombre="RUFINA INVENTADA ORIGEN", cedula=CED, tipo_documento="CC")
    db.personas.update_one({"_id": origen}, {"$set": {"fusionada_en": destino, "cedula": None,
                                                      "cedula_en_traspaso": CED}})

    def falla(*a, **k):
        raise RuntimeError(f"falla inventada con la cédula {CED}")

    monkeypatch.setattr(bd, "_unir_en", falla)
    assert bd.reparar_fusiones(db) == 0
    assert bd.reparar_fusiones(db) == 0  # el segundo arranque no repite el aviso
    monkeypatch.undo()
    aud = sesion.get("/api/auditoria", params={"accion": "union_cortada"}).json()
    assert aud["total"] == 1 and aud["filas"][0]["entidad_id"] == origen
    assert json.loads(aud["filas"][0]["detalle"])["destino"] == destino
    assert CED not in json.dumps(aud)  # sin el texto del error, que traía la cédula
    # Mientras tanto, el 409 de A dice a qué ficha va la cédula y desde cuál
    r = sesion.post("/api/personas", json={"nombre": "RUFINA INVENTADA OTRA", "cedula": CED})
    assert r.status_code == 409, r.text[:300]
    assert (r.json()["detail"]["id"], r.json()["detail"]["origen"]) == (destino, origen)
    assert "RUFINA INVENTADA DESTINO" in r.json()["detail"]["mensaje"]


# ───────────────────────────── 5. Importación y cédula en traspaso ─────────────────────────────

def test_importacion_en_la_ventana_de_la_union_no_crea_otra_ficha_con_la_cedula(bases, monkeypatch, tmp_path):
    from app import db as bd
    from app.pipeline import importar as imp
    db = bases()
    destino = persona(db, nombre="LUZ MARINA INVENTADA PEREZ", tipo_documento="CC")
    origen = persona(db, nombre="LUZ MARINA INVENTADA PEREZ", cedula="93000001", tipo_documento="CC")
    xl = excel_cedulas(tmp_path / "cedulas.xlsx", [("93000001", "HERMENEGILDO INVENTADO DISTINTO", "3159990001", None,
                                                    "YONDÓ", None, None, None, None, 40, "M", None, None, "Lista A")])
    res = []
    _envolver(monkeypatch, bd, "_unir_en", lambda db_, *a, **k: res.append(imp.importar(db_, [xl], "sistema")))
    bd.fusionar(db, destino, origen, "sistema")
    assert res[0].personas_nuevas == 0
    assert db.personas.count_documents({"cedula": "93000001"}) == 1
    assert db.personas.find_one({"_id": destino})["cedula"] == "93000001"
    assert db.personas.find_one({"_id": origen})["nombre"] == "FUSIONADA"
    c = db.conflictos_cedula.find_one({"cedula": "93000001"})
    assert (c["motivo"], c["persona_id"]) == ("nombre_distinto", destino)


def test_importacion_con_la_cedula_de_una_union_que_no_puede_terminar(bases, tmp_path):
    """La unión ya no puede terminar (su destino se suprimió): la cédula vuelve a su ficha antes de cargarlas, y la
    fila con otro nombre va a conflicto con esa ficha en vez de crear otra con la misma cédula."""
    from app.pipeline import importar as imp
    db = bases()
    _, origen = _union_sin_destino(db)
    xl = excel_cedulas(tmp_path / "cedulas.xlsx", [(CED, "HERMENEGILDO INVENTADO DISTINTO", "3159990002", None,
                                                    "YONDÓ", None, None, None, None, 40, "M", None, None, "Lista A")])
    res = imp.importar(db, [xl], "sistema")
    assert res.personas_nuevas == 0
    assert db.personas.count_documents({"cedula": CED}) == 1
    _activa_con_cedula(db, origen)
    c = db.conflictos_cedula.find_one({"cedula": CED, "motivo": "nombre_distinto"})
    assert c is not None and c["persona_id"] == origen


def test_cedula_tomada_en_la_ventana_lo_dice_el_409(sesion, monkeypatch):
    from app import db as bd
    db = sesion.app.state.db
    destino = persona(db, nombre="LUZ INVENTADA DESTINO", tipo_documento="CC")
    origen = persona(db, nombre="LUZ INVENTADA ORIGEN", cedula=CED, tipo_documento="CC")
    _envolver(monkeypatch, bd, "_unir_en", lambda *a, **k: persona(db, nombre="LUZ INVENTADA OTRA", cedula=CED,
                                                                   tipo_documento="CC"))
    r = sesion.post(f"/api/personas/{destino}/fusionar", json={"con_id": origen})
    assert r.status_code == 409, r.text[:300]
    assert "tomó la cédula del origen" in r.json()["detail"]
    assert "cédulas distintas" not in r.json()["detail"]


# ───────────────────────────── 6. «Aplicar» tras una unión que no se hizo ─────────────────────────────

def test_aplicar_el_conflicto_de_una_union_fallida_devuelve_la_procedencia(sesion):
    from app import db as bd
    db = sesion.app.state.db
    prov = {"fuente": "cedulas", "ts": "2026-01-02T00:00:00+00:00", "uid": None}
    destino = persona(db, nombre="LUZ INVENTADA DESTINO", tipo_documento="CC")
    origen = persona(db, nombre="LUZ INVENTADA ORIGEN", cedula=CED, tipo_documento="CC", cedula_origen="cedulas",
                     procedencia={"cedula": prov})
    db.personas.update_one({"_id": origen}, {"$set": {"fusionada_en": destino, "cedula": None,
                                                      "cedula_en_traspaso": CED}})
    otra = persona(db, nombre="LUZ INVENTADA OTRA", cedula=CED, tipo_documento="CC")
    bd.reparar_fusiones(db)  # E11000: el origen vuelve sin la cédula y con un conflicto
    c = db.conflictos_cedula.find_one({"persona_id": origen, "fuente": "fusion"})
    assert isinstance(c["creado_por"], dict) and "uid" in c["creado_por"]
    db.personas.update_one({"_id": otra}, {"$set": {"cedula": "61000077"}})  # la cédula se libera
    r = sesion.post(f"/api/conflictos/{c['_id']}", json={"decision": "aplicar"})
    assert r.status_code == 200, r.text[:300]
    o = db.personas.find_one({"_id": origen})
    assert o["cedula"] == CED and o["cedula_origen"] == "cedulas"
    assert o["procedencia"]["cedula"] == prov
    ed = db.auditoria.find_one({"accion": "editar", "entidad_id": origen}, sort=[("_id", -1)])
    assert "unión que no se hizo" in json.loads(ed["detalle"])["motivo_cambio_cedula"]
    assert "consultor" not in ed["detalle"]


# ───────────────────────────── 7. 409 `registrado` ─────────────────────────────

def test_planillero_revoca_en_una_ficha_que_se_une_y_sabe_que_quedo_registrado(sesion, como, monkeypatch):
    from app import db as bd
    from app.api import personas as per
    db = sesion.app.state.db
    lid = _lid(db)
    destino, origen = _dos_contactables(db, lid)
    p = como("planillero", asignacion={"lugares": [lid], "areas": []})
    _envolver(monkeypatch, per, "registrar_autorizacion",
              lambda db_, pid, *a, **k: bd.fusionar(db_, destino, origen, "sistema"))
    clave = {"Idempotency-Key": "revoca-unida-0001"}
    r = p.post(f"/api/personas/{origen}/autorizacion", json={"estado": "revocada"}, headers=clave)
    assert r.status_code == 409, r.text[:300]
    det = r.json()["detail"]
    assert det["registrado"] is True and det["id"] == destino
    assert db.personas.find_one({"_id": destino})["consentimiento"] == "no"
    assert db.solicitudes.find_one({"tipo": "revocatoria"})["persona_id"] == destino
    assert db.personas.find_one({"_id": destino})["reclamo_en_tramite"] is True
    # El reintento con la misma clave dice lo mismo y no registra otra revocatoria
    r2 = p.post(f"/api/personas/{origen}/autorizacion", json={"estado": "revocada"}, headers=clave)
    assert (r2.status_code, r2.json()) == (409, r.json())
    assert db.autorizaciones.count_documents({"estado": "revocada"}) == 1


def test_planillero_dice_no_por_patch_en_una_ficha_que_se_une(sesion, como, monkeypatch):
    from app import db as bd
    from app.api import personas as per
    db = sesion.app.state.db
    lid = _lid(db)
    destino, origen = _dos_contactables(db, lid)
    p = como("planillero", asignacion={"lugares": [lid], "areas": []})
    _envolver(monkeypatch, per, "registrar_autorizacion",
              lambda db_, pid, *a, **k: bd.fusionar(db_, destino, origen, "sistema"))
    r = p.patch(f"/api/personas/{origen}", json={"consentimiento": "no"})
    assert r.status_code == 409, r.text[:300]
    assert r.json()["detail"]["registrado"] is True and r.json()["detail"]["id"] == destino
    assert db.personas.find_one({"_id": destino})["consentimiento"] == "no"


# ───────────────────────────── 8. «Ver como» en Mi trabajo ─────────────────────────────

def test_ver_como_los_enlaces_de_mi_trabajo_llevan_el_alcance_del_usuario(sesion, como):
    db = sesion.app.state.db
    dentro, fuera = [x["_id"] for x in db.lugares.find({"tipo": "barrio"}).limit(2)]
    p = como("planillero", asignacion={"lugares": [dentro], "areas": []})
    assert p.post("/api/personas", json={"nombre": "TOMASA INVENTADA DENTRO", "lugar_id": dentro}).status_code == 201
    for i, lid in enumerate((dentro, fuera, fuera, None)):
        persona(db, nombre=f"CASIMIRO INVENTADO {i}", lugar_id=lid, tipo_documento="CC")
    propias = {x["clave"]: x for x in p.get("/api/trabajo").json()["listas"]}
    listas = sesion.get("/api/trabajo", params={"uid": p.uid}).json()["listas"]
    assert {x["clave"]: x["n"] for x in listas} == {k: x["n"] for k, x in propias.items()}
    for x in listas:
        url = urlsplit(x["enlace"])
        params = dict(parse_qsl(url.query))
        assert params.get("como") == str(p.uid), x
        total = sesion.get("/api" + url.path, params=params).json()["total"]
        assert total == x["n"], (x["clave"], total, x["n"])
    assert sum(x["n"] for x in listas) > 0
    # Sin `como` (lo de A) es otra cosa: el enlace de antes abría la Habitantes de A
    sin_ced = next(x for x in listas if x["clave"] == "sin_cedula")
    params = {k: v for k, v in parse_qsl(urlsplit(sin_ced["enlace"]).query) if k != "como"}
    assert sesion.get("/api/personas", params=params).json()["total"] > sin_ced["n"]
    # Las propias de P no llevan `como`
    assert all("como=" not in x["enlace"] for x in propias.values())


def test_como_solo_lo_usan_a_y_k(sesion, como):
    db = sesion.app.state.db
    lid = _lid(db)
    p = como("planillero", asignacion={"lugares": [lid], "areas": []})
    otro = como("planillero", asignacion={"lugares": [lid], "areas": []})
    r = p.get("/api/personas", params={"como": otro.uid})
    assert r.status_code == 403, r.text[:300]
    k = coordinador(sesion.app, db)
    try:
        assert k.get("/api/personas", params={"como": p.uid}).status_code == 200
    finally:
        k.close()
    assert sesion.get("/api/personas", params={"como": 999999}).status_code == 404
