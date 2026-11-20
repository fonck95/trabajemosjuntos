"""Los datos principales de la ficha en el servidor: los filtros de Habitantes por esos datos (correo, perfil
profesional, ocupación, estado civil, jefe de hogar, sin líder), la fila de cada rol (A y K con correo, dirección,
fecha y «Liderado por»; P solo lo que no identifica) y la sugerencia del alta por la cédula sola (la misma para todos,
la que empieza igual solo para A y K).

Solo personas inventadas. La traducción de los filtros corre sin MongoDB; la API, con MongoDB (como en CI)."""
from __future__ import annotations

import re

from app.api import filtros as F
from ayudas_g3 import coordinador, persona, sin_vedados


# ───────────────────────────── Filtros (sin base) ─────────────────────────────

def _y(**params) -> list[dict]:
    return F.filtro(F.Filtros(**params))["$and"][1:]


def test_patron_de_texto_sin_tildes_ni_mayusculas_y_escapado():
    rx = re.compile(F.patron_texto("enfermeria"), re.I)
    assert rx.search("AUXILIAR DE ENFERMERÍA") and rx.search("Enfermeria") and not rx.search("ENFERMERA")
    assert re.compile(F.patron_texto("Técnico"), re.I).search("TECNICO AGROPECUARIO")
    assert F.patron_texto("a.b(c)*") == "[aáàä]\\.b\\(c\\)\\*"  # lo escrito nunca es una expresión


def test_los_filtros_de_los_datos_principales():
    assert _y(jefe_hogar="si") == [{"jefe_hogar": True}] and _y(jefe_hogar="no") == [{"jefe_hogar": False}]
    assert _y(jefe_hogar="otro") == []
    assert _y(sin_jefe_hogar=1) == [{"$and": [{"jefe_hogar": None}]}]
    assert _y(con_correo=1) == [{"correo": {"$nin": [None, ""]}}] and _y(con_correo=0) == [{"correo": {"$in": [None, ""]}}]
    assert _y(sin_correo=1) == [{"$and": [{"correo": {"$in": [None, ""]}}]}]
    for campo in ("estado_civil", "ocupacion", "perfil_profesional"):
        assert _y(**{f"sin_{campo}": 1}) == [{"$and": [{campo: {"$in": [None, ""]}}]}]
    (o,) = _y(ocupacion="  pescador ")
    assert o["ocupacion"]["$options"] == "i" and re.search(o["ocupacion"]["$regex"], "Pescador artesanal", re.I)
    assert _y(perfil_profesional="  ") == []
    assert _y(sin_lider=1) == [{"lideres.0": {"$exists": False}}]
    assert "sin_lider" in F.VEDADOS and not {"jefe_hogar", "ocupacion", "perfil_profesional", "con_correo"} & set(F.VEDADOS)


# ───────────────────────────── API (MongoDB) ─────────────────────────────

def _ids(c, **params):
    r = c.get("/api/personas", params=params)
    assert r.status_code == 200, r.text
    return {f["id"] for f in r.json()["filas"]}


def test_filtros_y_filas_de_los_datos_principales(sesion, como):
    db = sesion.app.state.db
    lider = persona(db, nombre="LIDER INVENTADO DE LA FILA", lider=True)
    ana = persona(db, nombre="ANA INVENTADA PRINCIPAL", correo="ana.inventada@ejemplo.org", direccion="CL 49 # 45-12",
                  fecha_nacimiento="1980-05-17", perfil_profesional="AUXILIAR DE ENFERMERÍA", ocupacion="Pescadora",
                  estado_civil="Casado(a)", jefe_hogar=True, votante=True,
                  lideres=[{"id": lider, "asignado_en": "2026-11-20", "asignado_por": "admin"}])
    beto = persona(db, nombre="BETO INVENTADO PRINCIPAL", jefe_hogar=False)
    q = {"q": "INVENTAD"}
    assert _ids(sesion, **q, jefe_hogar="si") == {ana} and _ids(sesion, **q, jefe_hogar="no") == {beto}
    assert _ids(sesion, **q, sin_jefe_hogar=1) == {lider}
    assert _ids(sesion, **q, perfil_profesional="enfermeria") == {ana}
    assert _ids(sesion, **q, ocupacion="PESCAD") == {ana}
    assert _ids(sesion, **q, con_correo=1) == {ana} and ana not in _ids(sesion, **q, sin_correo=1)
    assert _ids(sesion, **q, estado_civil="Casado(a)") == {ana} and ana not in _ids(sesion, **q, sin_estado_civil=1)
    assert _ids(sesion, **q, sin_lider=1) == {lider, beto} and _ids(sesion, **q, lider_id=lider) == {ana}
    # La fila de A y K: los datos principales y quién la lidera (una consulta por página)
    fila = next(f for f in sesion.get("/api/personas", params={"q": "ANA INVENTADA"}).json()["filas"] if f["id"] == ana)
    assert (fila["correo"], fila["direccion"], fila["fecha_nacimiento"]) == ("ana.inventada@ejemplo.org", "CL 49 # 45-12",
                                                                             "1980-05-17")
    assert fila["edad_efectiva"] is not None and fila["tiene_correo"] is True and fila["jefe_hogar"] is True
    assert (fila["perfil_profesional"], fila["ocupacion"], fila["estado_civil"]) == (
        "AUXILIAR DE ENFERMERÍA", "Pescadora", "Casado(a)")
    assert fila["lideres"] == [{"id": lider, "nombre": "LIDER INVENTADO DE LA FILA", "tipo": "lider"}]
    assert fila["votante"] is True and fila["lideres_n"] == 1
    k = coordinador(sesion.app, db)
    assert next(f for f in k.get("/api/personas", params={"q": "ANA INVENTADA"}).json()["filas"])["lideres"][0]["id"] == lider
    # La fila de P: lo que no identifica (sin correo, dirección, fecha exacta ni nada político); sus filtros no políticos
    p = como("planillero")
    filas = p.get("/api/personas", params={"q": "ANA INVENTADA"}).json()
    sin_vedados(filas, "filas de P")
    fp = next(f for f in filas["filas"] if f["id"] == ana)
    assert not {"correo", "direccion", "fecha_nacimiento", "edad_efectiva", "lideres"} & set(fp)
    assert (fp["tiene_correo"], fp["perfil_profesional"], fp["ocupacion"], fp["estado_civil"], fp["jefe_hogar"]) == (
        True, "AUXILIAR DE ENFERMERÍA", "Pescadora", "Casado(a)", True)
    for filtro in ({"jefe_hogar": "si"}, {"ocupacion": "pesc"}, {"perfil_profesional": "enfer"}, {"con_correo": 1},
                   {"sin_correo": 1}, {"sin_jefe_hogar": 1}):
        assert p.get("/api/personas", params={**q, **filtro}).status_code == 200, filtro
    assert p.get("/api/personas", params={**q, "sin_lider": 1}).status_code == 403
    # Lo buscado como texto no queda en claro en la auditoría de una exportación
    r = sesion.get("/api/exportar.xlsx", params={"ocupacion": "pescad", "motivo": "operacion_interna"})
    assert r.status_code == 200
    a = db.auditoria.find_one({"accion": {"$regex": "export"}}, sort=[("_id", -1)])
    assert a is not None and "pescad" not in str(a.get("detalle"))


def test_la_sugerencia_del_alta_tambien_por_la_cedula(sesion, como):
    db = sesion.app.state.db
    ana = persona(db, nombre="ANA INVENTADA CEDULA", cedula="1000000001")
    berta = persona(db, nombre="BERTA INVENTADA CEDULA", cedula="1000000002")
    anterior = persona(db, nombre="CARLOS INVENTADO CEDULA", cedula="1000000003", cedulas_anteriores=["1000000099"])

    def sug(c, **params):
        r = c.get("/api/parecidas", params=params)
        assert r.status_code == 200, r.text
        return {f["id"]: f for f in r.json()}

    # La misma cédula, sin nombre: para todos los roles
    s = sug(sesion, cedula="1000000001")
    assert list(s) == [ana] and s[ana]["coincide_cedula"] == "exacta" and s[ana]["cedula_distinta"] is False
    assert list(sug(sesion, cedula="1000000099")) == [anterior]  # una cédula anterior de la ficha
    # Mientras se escribe (5 dígitos o más): A y K ven las que empiezan igual, marcadas como tales
    s = sug(sesion, cedula="1000000")
    assert {ana, berta, anterior} <= set(s) and s[ana]["coincide_cedula"] == "inicio" and not s[ana]["cedula_distinta"]
    assert sug(sesion, cedula="1000") == {}  # menos de 5 dígitos: nada
    # P: solo la misma cédula, nunca por partes de un número (no recorre la base)
    p = como("planillero")
    assert list(sug(p, cedula="1000000001")) == [ana]
    assert sug(p, cedula="1000000") == {}
    sin_vedados(p.get("/api/parecidas", params={"cedula": "1000000001"}).json(), "parecidas de P")
    # Con nombre y cédula: la misma cédula entra aunque el nombre sea otro, y una cédula distinta se marca
    s = sug(sesion, nombre="ANA INVENTADA CEDULA", cedula="1000000005")
    assert s[ana]["cedula_distinta"] is True and s[ana]["coincide_cedula"] is None
    s = sug(sesion, nombre="OTRO NOMBRE DISTINTO", cedula="1000000002")
    assert berta in s and s[berta]["coincide_cedula"] == "exacta"
    # El asistente (estricta) sigue pidiendo el nombre
    assert sug(sesion, cedula="1000000001", estricta=1) == {}
