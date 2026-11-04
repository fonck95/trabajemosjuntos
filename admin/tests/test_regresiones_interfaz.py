"""Regresiones de la interfaz que el servidor debe cubrir: correos con dominio imposible y fechas que no existen.

Solo datos inventados. El navegador ya no valida el correo (el campo es de texto con teclado de correo) ni puede
mostrar una fecha imposible en un campo de fecha: por eso el servidor es quien las rechaza."""
import pytest

from app.pipeline import texto as tx
from conftest import excel_tramites


# ───────── Correo ─────────

@pytest.mark.parametrize("malo", [
    "teofilo@gmail..com",   # dos puntos seguidos
    "eufrasia@.gmail.com",  # punto inicial
    "gumer@-mail.com",      # etiqueta que empieza con guion
    "gumer@mail-.com",      # etiqueta que termina con guion
    "gumer@correo.-mi.co",  # etiqueta intermedia con guion inicial
    "gumer@gmail.com.",     # punto final
])
def test_correo_rechaza_dominios_imposibles(malo):
    assert tx.correo(malo) == ""
    assert tx.correo(malo.upper()) == ""


@pytest.mark.parametrize("bueno, esperado", [
    ("zoila@gmail.com", "zoila@gmail.com"),
    ("ZOILA@GMAIL.COMK", "zoila@gmail.com"),  # los arreglos de dominio siguen
    ("ana.maria_r+panel@sub.mi-dominio.com.co", "ana.maria_r+panel@sub.mi-dominio.com.co"),
    ("x@a1.co", "x@a1.co"),
    ("x@mi--dominio.org", "x@mi--dominio.org"),  # guiones en medio sí valen
])
def test_correo_sigue_aceptando_los_validos(bueno, esperado):
    assert tx.correo(bueno) == esperado


def test_ficha_rechaza_correo_imposible_y_guarda_lo_demas(sesion):
    c = sesion
    p = c.post("/api/personas", json={"nombre": "Teofilo Inventado Correo", "forzar": True}).json()
    for malo in ("teofilo@gmail..com", "teofilo@.gmail.com", "teofilo@-mail.com"):
        r = c.patch(f"/api/personas/{p['id']}", json={"correo": malo})
        assert r.status_code == 422 and "Correo no válido" in r.json()["detail"], r.text
    assert c.post("/api/personas", json={"nombre": "Eufrasia Inventada Correo", "correo": "e@gmail..com",
                                         "forzar": True}).status_code == 422
    # Una ficha con un correo así guardado de antes se sigue pudiendo editar: la interfaz no reenvía lo que no cambió
    c.app.state.db.personas.update_one({"_id": p["id"]}, {"$set": {"correo": "teofilo@gmail..com"}})
    r = c.patch(f"/api/personas/{p['id']}", json={"ocupacion": "Pescador"})
    assert r.status_code == 200 and r.json()["ocupacion"] == "Pescador" and r.json()["correo"] == "teofilo@gmail..com"


def test_importar_no_guarda_correos_con_dominio_imposible(sesion, tmp_path):
    c = sesion
    a = excel_tramites(tmp_path / "t.xlsx", [
        ("9001", "0589300000901", "2/6/2025 12:00:00 AM", "NUEVA ENCUESTA - TEOFILO INVENTADO PUNTOS", "CALLE 49 # 45 12", "TEOFILO@GMAIL..COM", "3001110001", 1),
        ("9002", "0589300000902", "2/6/2025 12:00:00 AM", "NUEVA ENCUESTA - EUFRASIA INVENTADA PUNTO", "CALLE 50 # 45 12", "EUFRASIA@.GMAIL.COM", "3001110002", 1),
        ("9003", "0589300000903", "2/6/2025 12:00:00 AM", "NUEVA ENCUESTA - GUMERCINDO INVENTADO GUION", "CALLE 51 # 45 12", "GUMER@-MAIL.COM", "3001110003", 1),
        ("9004", "0589300000904", "2/6/2025 12:00:00 AM", "NUEVA ENCUESTA - ZENAIDA INVENTADA BIEN", "CALLE 52 # 45 12", "ZENAIDA@GMAIL.COM", "3001110004", 1),
    ])
    with a.open("rb") as fa:
        assert c.post("/api/importar", files=[("archivos", ("tramites.xlsx", fa.read()))]).status_code == 200
    correos = {x["nombre_norm"]: x.get("correo") for x in c.app.state.db.personas.find({}, {"nombre_norm": 1, "correo": 1})}
    assert len(correos) == 4
    assert {n: v for n, v in correos.items() if v} == {"ZENAIDA INVENTADA BIEN": "zenaida@gmail.com"}


# ───────── Fechas ─────────

@pytest.mark.parametrize("campo, fecha", [
    ("fecha_nacimiento", "1985-02-30"), ("fecha_nacimiento", "1990-06-31"), ("fecha_nacimiento", "1990-25-12"),
    ("consentimiento_fecha", "2024-06-31"), ("consentimiento_fecha", "2023-02-29"), ("consentimiento_fecha", "2024-00-10"),
])
def test_ficha_rechaza_fechas_inexistentes(sesion, campo, fecha):
    c = sesion
    p = c.post("/api/personas", json={"nombre": "Fulgencio Inventado Fecha", "forzar": True}).json()
    r = c.patch(f"/api/personas/{p['id']}", json={campo: fecha})
    assert r.status_code == 422 and "Fecha inexistente" in r.json()["detail"], r.text
    assert c.get(f"/api/personas/{p['id']}").json()[campo] is None
    r = c.post("/api/personas", json={"nombre": "Otra Persona Inventada Fecha", campo: fecha, "forzar": True})
    assert r.status_code == 422 and "Fecha inexistente" in r.json()["detail"], r.text


def test_ficha_acepta_fechas_reales_y_vacias(sesion):
    c = sesion
    p = c.post("/api/personas", json={"nombre": "Fulgencio Inventado Fecha", "fecha_nacimiento": "1984-02-29",
                                      "forzar": True}).json()
    assert p["fecha_nacimiento"] == "1984-02-29"  # bisiesto
    r = c.patch(f"/api/personas/{p['id']}", json={"fecha_nacimiento": "1980-01-15", "consentimiento_fecha": "2024-06-30"})
    assert r.status_code == 200 and r.json()["fecha_nacimiento"] == "1980-01-15" and r.json()["consentimiento_fecha"] == "2024-06-30"
    r = c.patch(f"/api/personas/{p['id']}", json={"fecha_nacimiento": None, "consentimiento_fecha": ""})
    assert r.status_code == 200 and r.json()["fecha_nacimiento"] is None and r.json()["consentimiento_fecha"] is None
    # El formato sigue siendo AAAA-MM-DD: lo que `date.fromisoformat` aceptaría de más no entra
    for otro in ("19800115", "1980-W03-2", "15/01/1980"):
        r = c.patch(f"/api/personas/{p['id']}", json={"fecha_nacimiento": otro})
        assert r.status_code == 422 and "AAAA-MM-DD" in r.json()["detail"], r.text


def test_fecha_imposible_guardada_de_antes_no_se_borra_al_editar_otro_campo(sesion):
    c = sesion
    p = c.post("/api/personas", json={"nombre": "Fulgencio Inventado Fecha", "forzar": True}).json()
    c.app.state.db.personas.update_one({"_id": p["id"]}, {"$set": {"fecha_nacimiento": "1990-06-31",
                                                                    "consentimiento_fecha": "2024-06-31"}})
    r = c.patch(f"/api/personas/{p['id']}", json={"ocupacion": "Agricultor", "extra": {}, "etiquetas": []})
    assert r.status_code == 200
    f = r.json()
    assert f["ocupacion"] == "Agricultor" and f["fecha_nacimiento"] == "1990-06-31" and f["consentimiento_fecha"] == "2024-06-31"


@pytest.mark.parametrize("fecha", ["2026-02-30", "2026-04-31", "2026-13-01"])
def test_reunion_rechaza_fechas_inexistentes(sesion, fecha):
    c = sesion
    r = c.post("/api/reuniones", json={"titulo": "Reunión inventada", "fecha": fecha})
    assert r.status_code == 422 and "Fecha inexistente" in r.json()["detail"], r.text
    reu = c.post("/api/reuniones", json={"titulo": "Reunión inventada", "fecha": "2028-02-29"}).json()
    r = c.patch(f"/api/reuniones/{reu['id']}", json={"fecha": fecha})
    assert r.status_code == 422 and "Fecha inexistente" in r.json()["detail"], r.text
    assert c.get(f"/api/reuniones/{reu['id']}").json()["fecha"] == "2028-02-29"
    r = c.patch(f"/api/reuniones/{reu['id']}", json={"fecha": "2026-11-04"})
    assert r.status_code == 200 and r.json()["fecha"] == "2026-11-04"


def test_reunion_sin_fecha_sigue_rechazada(sesion):
    c = sesion
    for vacia in ("", None):
        r = c.post("/api/reuniones", json={"titulo": "Reunión inventada", "fecha": vacia})
        assert r.status_code == 422, r.text
    reu = c.post("/api/reuniones", json={"titulo": "Reunión inventada", "fecha": "2026-11-04"}).json()
    r = c.patch(f"/api/reuniones/{reu['id']}", json={"fecha": ""})
    assert r.status_code == 422 and "necesita título y fecha" in r.json()["detail"], r.text
    assert c.get(f"/api/reuniones/{reu['id']}").json()["fecha"] == "2026-11-04"
