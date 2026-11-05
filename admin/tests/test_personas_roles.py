"""Reglas por rol en la API de personas (3.6, 3.8): P no cambia una cédula existente ni vacía campos, conserva las
etiquetas sensibles, no crea menores; C no edita; parámetros vedados; alcance obligatorio en Habitantes y libre en la
búsqueda y la ficha. Solo datos inventados."""
import pytest

from ayudas_g3 import persona


def _sensible(db) -> int:
    return db.etiquetas.find_one({"nombre": "Víctima del conflicto"})["_id"]


def test_planillero_no_cambia_una_cedula_existente(sesion, como):
    db = sesion.app.state.db
    pid = persona(db, nombre="ANACLETA INVENTADA CEDULA", cedula="92000111", tipo_documento="CC")
    p = como("planillero")
    r = p.patch(f"/api/personas/{pid}", json={"cedula": "92000999"})
    assert r.status_code == 403 and r.json()["detail"]["codigo"] == "permiso" and r.json()["detail"]["campo"] == "cedula"
    assert p.patch(f"/api/personas/{pid}", json={"cedula": "92000111"}).status_code == 200  # la misma: nada cambia
    r = p.patch(f"/api/personas/{pid}", json={"motivo_cambio_cedula": "x"})
    assert r.status_code == 403
    # A sí, con motivo; la anterior queda en cedulas_anteriores y en alternos
    assert sesion.patch(f"/api/personas/{pid}", json={"cedula": "92000999"}).status_code == 422
    f = sesion.patch(f"/api/personas/{pid}", json={"cedula": "92000999", "motivo_cambio_cedula": "Error de digitación"}).json()
    assert f["cedula"] == "92000999" and f["cedulas_anteriores"] == ["92000111"]
    assert any(a["campo"] == "cedula" and a["valor"] == "92000111" for a in f["alternos"])
    a = db.auditoria.find_one({"accion": "editar", "entidad_id": pid})
    assert "92000111" not in a["detalle"] and "92000999" not in a["detalle"]  # cédulas enmascaradas
    # La vieja sigue ocupada: nadie más la usa
    r = sesion.post("/api/personas", json={"nombre": "Otra Persona Inventada", "cedula": "92000111", "forzar": True})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "cedula_ocupada"


def test_planillero_llena_una_cedula_vacia_y_no_vacia_campos(sesion, como):
    db = sesion.app.state.db
    pid = persona(db, nombre="BERNARDINA INVENTADA VACIA", ocupacion="Pescadora", telefono="3001231234", edad=40)
    p = como("planillero")
    f = p.patch(f"/api/personas/{pid}", json={"cedula": "92000222"}).json()
    assert f["cedula"] == "92000222" and f["tipo_documento"] == "CC" and f["cedula_origen"] == "panel"
    for campo in ("ocupacion", "edad"):
        r = p.patch(f"/api/personas/{pid}", json={campo: None})
        assert r.status_code == 422 and "corrección" in r.json()["detail"], campo
    r = p.patch(f"/api/personas/{pid}", json={"telefono": ""})
    assert r.status_code == 422 and "equivocado" in r.json()["detail"]
    # A sí vacía; el valor anterior queda en alternos
    f = sesion.patch(f"/api/personas/{pid}", json={"ocupacion": None}).json()
    assert f["ocupacion"] is None and any(a["campo"] == "ocupacion" and a["valor"] == "Pescadora" for a in f["alternos"])
    # P no puede marcar líder
    r = p.patch(f"/api/personas/{pid}", json={"lider": True})
    assert r.status_code == 403 and r.json()["detail"]["campo"] == "lider"


def test_planillero_conserva_las_etiquetas_sensibles(sesion, como):
    db = sesion.app.state.db
    sens = _sensible(db)
    agua = db.etiquetas.find_one({"nombre": "Agua potable"})["_id"]
    vias = db.etiquetas.find_one({"nombre": "Vías"})["_id"]
    pid = persona(db, nombre="CIRIACA INVENTADA ETIQUETAS", etiquetas=[sens, agua])
    p = como("planillero")
    assert [e["id"] for e in p.get(f"/api/personas/{pid}").json()["etiquetas"]] == [agua]
    # Con etiquetas_base: la diferencia
    p.patch(f"/api/personas/{pid}", json={"etiquetas": [vias], "etiquetas_base": [agua]})
    assert set(db.personas.find_one({"_id": pid})["etiquetas"]) == {sens, vias}
    # Sin base: el conjunto completo, conservando las sensibles
    p.patch(f"/api/personas/{pid}", json={"etiquetas": [agua]})
    assert set(db.personas.find_one({"_id": pid})["etiquetas"]) == {sens, agua}
    r = p.patch(f"/api/personas/{pid}", json={"etiquetas": [sens]})
    assert r.status_code == 403
    a = db.auditoria.find_one({"accion": "editar", "entidad_id": pid})
    assert str(sens) not in [str(x) for x in (a.get("detalle") or "").split()] or "(oculto)" in a["detalle"]


def test_consultor_no_edita(sesion, como):
    db = sesion.app.state.db
    pid = persona(db, nombre="DOROTEA INVENTADA CONSULTOR")
    c = como("consultor")
    r = c.patch(f"/api/personas/{pid}", json={"ocupacion": "Docente"})
    assert r.status_code == 403 and r.json()["detail"]["codigo"] == "permiso"
    assert c.post("/api/personas", json={"nombre": "Nueva Inventada", "forzar": True}).status_code == 403


@pytest.mark.parametrize("datos", [{"edad": 15}, {"tipo_documento": "TI", "cedula": "1012345678"},
                                   {"fecha_nacimiento": "2015-03-01"}])
def test_planillero_no_crea_menores(sesion, como, datos):
    p = como("planillero")
    r = p.post("/api/personas", json={"nombre": "Eulogia Inventada Menor", "forzar": True, **datos})
    assert r.status_code == 422 and "menores" in r.json()["detail"]
    # A sí, y el aviso queda visible
    r = sesion.post("/api/personas", json={"nombre": "Eulogia Inventada Menor", "forzar": True, **datos})
    assert r.status_code == 201 and r.json()["menor"] is True
    assert any("Menor" in a for a in r.json()["avisos"])


def test_parametros_vedados(sesion, como):
    db = sesion.app.state.db
    sens = _sensible(db)
    agua = db.etiquetas.find_one({"nombre": "Agua potable"})["_id"]
    for rol in ("planillero",):
        p = como(rol)
        for params in ({"poligono": "-73.92,7.0;-73.90,7.0;-73.90,7.01"}, {"ids": "1,2"}, {"lista": "Lista A"},
                       {"lider": 1}, {"fuente": "cedulas"}, {"fuente": "ambas"}, {"etiqueta": sens},
                       {"creado_por": 0}, {"actualizado_por": 0}, {"menor": 1}, {"menor": 0}):
            r = p.get("/api/personas", params=params)
            assert r.status_code == 403 and r.json()["detail"]["codigo"] == "permiso", params
        assert p.get("/api/personas", params={"etiqueta": agua}).status_code == 200
        assert p.get("/api/personas", params={"fuente": "tramites"}).status_code == 200
    assert sesion.get("/api/personas", params={"lider": 1, "menor": 0, "fuente": "cedulas"}).status_code == 200


def test_alcance_obligatorio_en_habitantes_y_libre_en_busqueda_y_ficha(sesion, como):
    db = sesion.app.state.db
    l1, l2 = [x["_id"] for x in db.lugares.find({}, {"_id": 1}).limit(2)]
    dentro = persona(db, nombre="EVARISTA INVENTADA DENTRO", lugar_id=l1)
    fuera = persona(db, nombre="EVARISTA INVENTADA FUERA", lugar_id=l2)
    p = como("planillero", asignacion={"lugares": [l1], "areas": []})
    ids = [f["id"] for f in p.get("/api/personas", params={"q": "EVARISTA"}).json()["filas"]]
    assert ids == [dentro]
    assert p.get("/api/personas", params={"lugar_id": l2}).json()["total"] == 0
    assert {f["id"] for f in p.get("/api/buscar", params={"q": "EVARISTA"}).json()} == {dentro, fuera}
    assert p.get(f"/api/personas/{fuera}").status_code == 200
    assert db.lecturas.find_one({"uid": p.uid, "pid": fuera, "ficha": True})
    # Un área que no tiene asignada: 403; una inexistente: 404
    db.areas.insert_one({"_id": 7, "nombre": "Área inventada", "poligono": [[-73.92, 7.0], [-73.90, 7.0], [-73.90, 7.01]],
                         "asignada_a": []})
    assert p.get("/api/personas", params={"area_id": 7}).status_code == 403
    assert p.get("/api/personas", params={"area_id": 99}).status_code == 404
    # Sin asignación: toda la base (con el presupuesto)
    q = como("planillero")
    assert {dentro, fuera} <= {f["id"] for f in q.get("/api/personas", params={"q": "EVARISTA"}).json()["filas"]}


def test_concurrencia_por_campo_con_base(sesion, como):
    db = sesion.app.state.db
    pid = persona(db, nombre="FAUSTINA INVENTADA BASE", ocupacion="Docente", correo="faustina@correo.co")
    p = como("planillero")
    assert p.patch(f"/api/personas/{pid}", json={"ocupacion": "Agricultora", "base": {"ocupacion": "Docente"}}).status_code == 200
    r = p.patch(f"/api/personas/{pid}", json={"ocupacion": "Comerciante", "base": {"ocupacion": "Docente"}})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "cambiada"
    assert r.json()["detail"]["campos"] == ["ocupacion"] and r.json()["detail"]["valores_actuales"] == {"ocupacion": "Agricultora"}
    assert db.personas.find_one({"_id": pid})["ocupacion"] == "Agricultora"
    # Sin base se escribe como siempre
    assert p.patch(f"/api/personas/{pid}", json={"ocupacion": "Comerciante"}).json()["ocupacion"] == "Comerciante"
    # La autoría y los alternos quedan
    d = db.personas.find_one({"_id": pid})
    assert d["actualizado_por"]["uid"] == p.uid
    a = db.auditoria.find_one({"accion": "editar", "entidad_id": pid, "uid": p.uid})
    assert a["rol"] == "planillero" and a["campos"] == ["ocupacion"]
