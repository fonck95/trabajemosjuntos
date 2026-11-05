"""Proyección por rol (3.6, 3.8): P y C reciben solo los campos de su lista, en toda respuesta con fichas o filas
(Habitantes, búsqueda, ficha, PATCH, notas, teléfonos, parecidas, acercamientos, reuniones y colas); para ellos la
fuente «cedulas» se muestra como «otra_base». Nadie recibe `sensibles` ni `cedula_en_traspaso`; A y K reciben lo
político y la cédula completa. Solo datos inventados."""
from ayudas_g3 import autorizada, coordinador, persona, sin_vedados, tomar


def _rica(db, **extra) -> int:
    """Una ficha con todo lo que P y C no deben ver."""
    et = db.etiquetas.find_one({"nombre": "Líder comunitario"})["_id"]
    pid = persona(
        db, nombre="EUSTAQUIA INVENTADA RICA", cedula="91000777", telefono="3009990011", tipo_documento="CC",
        cedula_origen="cedulas", cedulas_anteriores=["91000111"], cedula_en_traspaso="91000222", lider=True,
        listas=["Lista Inventada"], sensibles={"etnia": "Raizal"}, sensibles_autorizados=["etnia"],
        fuentes=["tramites", "cedulas"], origen=[{"fuente": "cedulas", "datos": {"partido": "X", "mesa_testigo": "9"}}],
        procedencia={"cedula": {"fuente": "cedulas", "ts": "2026-01-01T00:00:00+00:00", "uid": None}},
        alternos=[{"campo": "correo", "valor": "viejo@correo.co", "fuente": "cedulas", "ts": "2026-01-01", "uid": None}],
        telefonos=[{"numero": "3009990011", "tipo": "celular", "fuentes": ["cedulas", "tramites"], "estado": "confirmado",
                    "no_contactar": False}],
        votacion={"puesto_id": None, "puesto_nombre": None, "puesto_texto": "ESCUELA INVENTADA", "mesa": 3,
                  "mesa_texto": None, "donde": "yondo", "eleccion": None, "estado": "por_confirmar", "fuente": "cedulas"},
        etiquetas=[et], edad=40, **extra)
    autorizada(db, pid)
    return pid


def test_planillero_y_consultor_no_reciben_lo_vedado(sesion, como):
    db = sesion.app.state.db
    pid = _rica(db)
    otra = persona(db, nombre="EUSTAQUIA INVENTADA RICAS", telefono="3009990011", cedula="91000888", edad=33,
                   cedulas_anteriores=["1234567"], lider=True, listas=["Lista Z"], fuentes=["cedulas"])
    reu = sesion.post("/api/reuniones", json={"titulo": "Reunión inventada", "fecha": "2026-11-01"}).json()["id"]
    sesion.patch(f"/api/reuniones/{reu}", json={"abierta_a_equipo": True})
    assert sesion.post(f"/api/reuniones/{reu}/asistentes", json={"persona_id": pid}).status_code == 201
    p = como("planillero")
    respuestas = [
        p.get("/api/personas"), p.get("/api/personas", params={"q": "EUSTAQUIA"}), p.get("/api/buscar", params={"q": "EUSTAQUIA"}),
        p.get(f"/api/personas/{pid}"), p.patch(f"/api/personas/{pid}", json={}),
        p.patch(f"/api/personas/{pid}", json={"ocupacion": "Pescadora"}),
        p.post(f"/api/personas/{pid}/notas", json={"texto": "Nota inventada"}),
        p.post(f"/api/personas/{pid}/telefonos", json={"numero": "3101112233"}),
        p.get(f"/api/personas/{pid}/parecidas"), p.get("/api/parecidas", params={"nombre": "Eustaquia Inventada Rica"}),
        p.post("/api/personas", json={"nombre": "Eustaquia Inventada Rica", "telefono": "3009990011"}),
        p.post(f"/api/personas/{pid}/acercamientos", json={"canal": "visita", "resultado": "contesto"}),
        p.get(f"/api/personas/{pid}/acercamientos"), p.get(f"/api/reuniones/{reu}"), p.get(f"/api/personas/{otra}"),
    ]
    for x in respuestas:
        assert x.status_code in (200, 201, 409), (x.request.url, x.status_code, x.text[:300])
        sin_vedados(x.json(), str(x.request.url))
    f = p.get(f"/api/personas/{pid}").json()
    assert f["cedula"] == "91000777" and f["cedula_origen"] == "otra_base"
    assert f["telefonos"][0]["fuentes"] == ["otra_base", "tramites"] and f["alternos"][0]["fuente"] == "otra_base"
    assert f["votacion"]["fuente"] == "otra_base" and "fuentes" not in f
    assert f["sensibles_registrados"] == ["etnia"] and all(e["nombre"] != "Líder comunitario" for e in f["etiquetas"])
    # «Mi trabajo» trae conteos, no fichas («listas» es el nombre de sus tarjetas)
    t = p.get("/api/trabajo").json()
    assert all(set(x) == {"clave", "titulo", "n", "enlace"} for x in t["listas"])
    fila = p.get("/api/personas", params={"q": "EUSTAQUIA"}).json()["filas"][0]
    assert "cedula" not in fila and "telefono" not in fila and fila["cedula_ult3"] == "···777"
    assert fila["telefono_mascara"] == "···0011"
    # El 409 de parecidas también va proyectado
    r = p.post("/api/personas", json={"nombre": "Eustaquia Inventada Rica", "telefono": "3009990011"})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "parecidas"
    assert all("cedula" not in x and x["tiene_cedula"] for x in r.json()["detail"]["parecidas"])

    c = como("consultor")
    tomar(c, pid)
    respuestas = [c.get(f"/api/personas/{pid}"), c.get("/api/buscar", params={"q": "EUSTAQUIA"}),
                  c.get("/api/buscar", params={"q": "3009990011"}), c.get("/api/trabajo/cola"),
                  c.post(f"/api/personas/{pid}/telefonos", json={"numero": "3201112233"}),
                  c.post(f"/api/personas/{pid}/acercamientos", json={"canal": "llamada", "telefono_indice": 0,
                                                                     "resultado": "contesto", "nota": "Bien"}),
                  c.get(f"/api/personas/{pid}/acercamientos"), c.get("/api/insignias")]
    for x in respuestas:
        assert x.status_code == 200, (x.request.url, x.text[:300])
        sin_vedados(x.json(), str(x.request.url))
    f = c.get(f"/api/personas/{pid}").json()
    assert "cedula" not in f and f["cedula_ult3"] == "···777" and "telefono" not in f and "notas" not in f
    assert all(set(t) == {"numero", "tipo", "whatsapp", "estado", "indice"} for t in f["telefonos"])
    assert set(f["faltan"]) <= {"cedula", "puesto", "mesa"}
    assert c.get("/api/buscar", params={"q": "EUSTAQUIA"}).json()[0].keys() == {"id", "nombre", "lugar",
                                                                                "abordaje_estado", "contactable"}


def test_administrador_y_coordinador_ven_todo_menos_los_sensibles(sesion):
    db = sesion.app.state.db
    pid = _rica(db)
    k = coordinador(sesion.app, db)
    for c in (sesion, k):
        f = c.get(f"/api/personas/{pid}").json()
        assert "sensibles" not in f and "cedula_en_traspaso" not in f
        assert f["sensibles_registrados"] == ["etnia"] and f["lider"] is True and f["listas"] == ["Lista Inventada"]
        assert f["cedula"] == "91000777" and f["cedulas_anteriores"] == ["91000111"] and f["cedula_origen"] == "cedulas"
        assert f["origen"][0]["datos"]["partido"] == "X" and "historial" in f and "procedencia" in f
        assert any(e["nombre"] == "Líder comunitario" for e in f["etiquetas"])
        fila = c.get("/api/personas", params={"q": "EUSTAQUIA"}).json()["filas"][0]
        assert fila["cedula"] == "91000777" and fila["lider"] is True and "cedulas" in fila["fuentes"]
    # Los valores sensibles solo con su clic auditado, y nunca en la auditoría
    r = k.get(f"/api/personas/{pid}/sensibles")
    assert r.status_code == 200 and r.json()["sensibles"] == {"etnia": "Raizal"}
    a = db.auditoria.find_one({"accion": "ver_sensibles", "entidad_id": pid})
    assert a and "Raizal" not in (a.get("detalle") or "")


def test_quien_no_autorizo_sale_minimo(sesion, como):
    db = sesion.app.state.db
    pid = _rica(db)
    db.personas.update_one({"_id": pid}, {"$set": {"consentimiento": "no", "contacto_habilitado": False}})
    p = como("planillero")
    f = p.get(f"/api/personas/{pid}").json()
    assert set(f) == {"id", "nombre", "cedula_ult3", "lugar", "consentimiento", "abordaje"}
    fila = p.get("/api/personas", params={"q": "EUSTAQUIA"}).json()["filas"][0]
    assert set(fila) == {"id", "nombre", "cedula_ult3", "lugar", "consentimiento", "abordaje"}
    assert fila["abordaje"] == {"estado": "no_contactar"}


def test_planillero_no_ve_telefonos_de_menores(sesion, como):
    db = sesion.app.state.db
    pid = persona(db, nombre="TEODORA INVENTADA MENOR", telefono="3112223344", edad=15, consentimiento="si")
    p = como("planillero")
    f = p.get(f"/api/personas/{pid}").json()
    assert f["telefonos"] == [] and f["telefono"] is None and f["menor"] is True
    fila = p.get("/api/personas", params={"q": "TEODORA"}).json()["filas"][0]
    assert fila["telefono_mascara"] is None and fila["telefonos_n"] == 0
    assert sesion.get(f"/api/personas/{pid}").json()["telefono"] == "3112223344"
