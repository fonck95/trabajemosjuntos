"""Catálogos por rol (8.1) con ETag (7.0): A recibe todo con conteos de uso, listas y usuarios; P, sin lo sensible ni
lo político; C, solo lo que necesita para llamar. Con If-None-Match el servidor responde 304."""
from app import db as bd
from conftest import insertar_personas


def _preparar(sesion):
    db = sesion.app.state.db
    db.puestos.delete_many({})  # integración: el grupo 1 siembra los 7 puestos al iniciar
    db.puestos.insert_many([
        {"_id": 1, "eleccion": "2026-presidencial", "codigo": "00-01", "nombre": "IE LUIS EDUARDO DIAZ SECCION PRIMARIA",
         "area": "cabecera", "mesas": 35, "lugar_id": None, "activo": True},
        {"_id": 2, "eleccion": "2026-presidencial", "codigo": "99-99", "nombre": "PUESTO INACTIVO INVENTADO", "mesas": 1,
         "activo": False},
        {"_id": 3, "eleccion": "2022-congreso", "codigo": "00-01", "nombre": "DE OTRA ELECCION", "mesas": 30, "activo": True},
    ])
    sensible = sesion.post("/api/etiquetas", json={"nombre": "Etiqueta sensible inventada", "sensible": True}).json()["id"]
    sesion.post("/api/campos", json={"etiqueta": "Campo sensible inventado", "tipo": "texto", "sensible": True})
    sesion.post("/api/campos", json={"etiqueta": "Campo comun inventado", "tipo": "texto"})
    oculto = sesion.post("/api/campos", json={"etiqueta": "Campo oculto inventado", "tipo": "texto"}).json()["clave"]
    cid = next(c["id"] for c in sesion.get("/api/catalogos").json()["campos"] if c["clave"] == oculto)
    sesion.patch(f"/api/campos/{cid}", json={"activo": False})
    pid = insertar_personas(db, [{"nombre": "PERSONA INVENTADA CON LISTA", "consentimiento": "si"}])[0]
    db.personas.update_one({"_id": pid}, {"$set": {"listas": ["Lista inventada"], "etiquetas": [sensible]}})
    return db, sensible


def test_recorte_por_rol(sesion, como):
    db, sensible = _preparar(sesion)
    p, c = como("planillero"), como("consultor")
    a = sesion.get("/api/catalogos").json()
    assert a["listas"] == ["Lista inventada"] and {u["id"] for u in a["usuarios"]} == {p.uid, c.uid}
    assert next(e for e in a["etiquetas"] if e["id"] == sensible) == {
        "id": sensible, "nombre": "Etiqueta sensible inventada", "grupo": "necesidad", "orden": sensible, "n": 1, "sensible": True}
    assert {x["etiqueta"] for x in a["campos"]} == {"Campo sensible inventado", "Campo comun inventado", "Campo oculto inventado"}
    assert [x["codigo"] for x in a["puestos"]] == ["00-01", "99-99"] and a["puestos"][1]["activo"] is False
    for clave in ("eleccion_vigente", "aviso_privacidad", "politica", "sensibles_activos", "enlace_consulta_puesto", "lugares"):
        assert clave in a, clave
    vp = p.get("/api/catalogos").json()
    assert "listas" not in vp and "usuarios" not in vp
    assert sensible not in {e["id"] for e in vp["etiquetas"]} and vp["etiquetas"] and all("n" not in e for e in vp["etiquetas"])
    assert [x["etiqueta"] for x in vp["campos"]] == ["Campo comun inventado"]
    assert vp["puestos"] == [{"id": 1, "codigo": "00-01", "nombre": "IE LUIS EDUARDO DIAZ SECCION PRIMARIA", "area": "cabecera",
                              "mesas": 35, "lugar_id": None}]
    assert vp["lugares"] == a["lugares"] and vp["politica"] == a["politica"]
    vc = c.get("/api/catalogos").json()
    assert vc["campos"] == [] and vc["etiquetas"] == [] and "listas" not in vc and "usuarios" not in vc
    assert vc["puestos"] == [{"id": 1, "codigo": "00-01", "nombre": "IE LUIS EDUARDO DIAZ SECCION PRIMARIA"}]
    assert "Lista inventada" not in p.get("/api/catalogos").text + c.get("/api/catalogos").text


def test_etag_y_304(sesion, como):
    db, sensible = _preparar(sesion)
    p, c = como("planillero"), como("consultor")
    r = p.get("/api/catalogos")
    etag = r.headers["etag"]
    assert r.status_code == 200 and etag.startswith('W/"planillero-')
    r2 = p.get("/api/catalogos", headers={"If-None-Match": etag})
    assert r2.status_code == 304 and r2.headers["etag"] == etag and not r2.content
    otro = c.get("/api/catalogos").headers["etag"]
    assert otro != etag  # la etiqueta es del rol: un consultor no reusa la de un planillero
    assert c.get("/api/catalogos", headers={"If-None-Match": etag}).status_code == 200
    # Un cambio en los catálogos sube la versión: 200 con otra etiqueta
    for cambio in (lambda: sesion.post("/api/etiquetas", json={"nombre": "Etiqueta nueva inventada"}),
                   lambda: sesion.post("/api/campos", json={"etiqueta": "Otro campo inventado", "tipo": "texto"})):
        cambio()
        r = p.get("/api/catalogos", headers={"If-None-Match": etag})
        assert r.status_code == 200 and r.headers["etag"] != etag
        etag = r.headers["etag"]
    assert db.meta.find_one({"_id": "catalogos_version"})["valor"] >= 2
    # Cualquier campo del documento de versión cuenta (lo puede subir otro módulo)
    db.meta.update_one({"_id": "catalogos_version"}, {"$inc": {"n": 1}})
    assert p.get("/api/catalogos", headers={"If-None-Match": etag}).status_code == 200


def test_etag_del_administrador_sigue_los_conteos(sesion):
    db, sensible = _preparar(sesion)
    r = sesion.get("/api/catalogos")
    etag = r.headers["etag"]
    assert etag.startswith('W/"admin-') and sesion.get("/api/catalogos", headers={"If-None-Match": etag}).status_code == 304
    # Etiquetar a otra persona cambia el conteo de uso (sin cambiar la versión): la etiqueta cambia
    pid = insertar_personas(db, [{"nombre": "OTRA PERSONA INVENTADA"}])[0]
    db.personas.update_one({"_id": pid}, {"$set": {"etiquetas": [sensible], "actualizado_en": bd.ahora()}})
    r = sesion.get("/api/catalogos", headers={"If-None-Match": etag})
    assert r.status_code == 200 and next(e for e in r.json()["etiquetas"] if e["id"] == sensible)["n"] == 2
