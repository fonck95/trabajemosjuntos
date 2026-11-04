"""Demográficos del tablero y de una zona (5.2): claves nuevas, sexo «sin», rangos de edad, denominadores VIGENTE,
zona con menos de 10 personas sin desgloses y celdas sensibles «<5». Solo A y K. Solo datos inventados."""
from app import modelo
from ayudas_g3 import coordinador, persona
from conftest import CASCO, insertar_personas
from test_filtros_nuevos import ANILLO


def test_claves_nuevas_y_denominadores_vigentes(sesion, como):
    db = sesion.app.state.db
    hoy = modelo.hoy_local().isoformat()
    persona(db, nombre="TOMASA INVENTADA UNO", sexo="F", edad=30, edad_ref=hoy, cedula="96000001", telefono="3007000001",
            telefono2="3007000002", estado_civil="Casado(a)",
            votacion={"puesto_id": 903, "mesa": 2, "eleccion": "2026-presidencial", "estado": "verificado"},
            abordaje={"n": 2, "efectivos": 1, "estado": "contactado"})
    persona(db, nombre="TOMASA INVENTADA DOS", sexo="M", edad=70, edad_ref=hoy,
            votacion={"puesto_texto": "OTRA ESCUELA", "eleccion": None, "estado": "sin_verificar", "donde": "yondo"})
    persona(db, nombre="TOMASA INVENTADA TRES", edad=10, edad_ref=hoy, consentimiento="si", contacto_habilitado=False)
    persona(db, nombre="TOMASA INVENTADA CUATRO", votacion={"donde": "otro_municipio", "municipio": "Barranca"})
    persona(db, nombre="TOMASA INVENTADA FALLECIDA", sexo="F", situacion={"estado": "fallecida", "confirmada": True})
    db.puestos.insert_one({"_id": 903, "eleccion": "2026-presidencial", "codigo": "T-03", "nombre": "PUESTO INVENTADO",
                           "mesas": 5, "activo": True})
    d = sesion.get("/api/indicadores").json()
    k = d["kpi"]
    assert k["personas"] == 4 and k["no_vigentes"] == 1
    assert (k["con_cedula"], k["sin_cedula"], k["con_varios_telefonos"], k["menores"]) == (1, 3, 1, 1)
    # Sin elección (o de otra) cuenta como «por confirmar», también la de otro municipio
    assert (k["votacion_verificada"], k["votacion_por_confirmar"], k["otro_municipio"]) == (1, 2, 1)
    assert (k["abordadas"], k["contactadas"], k["con_sexo"], k["con_edad"]) == (1, 1, 2, 3)
    assert d["sexo"] == {"F": 1, "M": 1, "N": 0, "sin": 2} and d["sin_edad"] == 1
    assert d["rangos_edad"]["25-34"] == 1 and d["rangos_edad"]["65+"] == 1 and d["rangos_edad"]["<18"] == 1
    assert {"rango": "<18", "sexo": "sin", "n": 1} in d["edades"]
    assert d["puestos"] == [{"id": 903, "codigo": "T-03", "nombre": "PUESTO INVENTADO", "n": 1, "con_mesa": 1, "mesas": 5}]
    assert d["puesto_sin_catalogo"] == 1 and d["demografia"]["estado_civil"] == {"Casado(a)": 1}
    assert d["autorizacion"]["por_confirmar"] == 1 and d["abordaje"]["contactado"] == 1
    assert {c["campo"] for c in d["completitud_campos"]} == set(modelo.CAMPOS_AVANCE)
    assert "sensibles" not in d and "tramites_mes" in d and "actividad" in d
    # Con alcance «zona» no van la actividad ni las reuniones; con detalle=mesas, las mesas
    z = sesion.get("/api/indicadores", params={"alcance": "zona", "q": "TOMASA"}).json()
    assert z["pocas"] is True and z["kpi"] == {"personas": "<10"} and z["lugares"] == []
    m = sesion.get("/api/indicadores", params={"detalle": "mesas"}).json()
    assert m["mesas"] == [{"puesto_id": 903, "mesa": 2, "n": 1}]
    # Solo A y K
    assert coordinador(sesion.app, db).get("/api/indicadores").status_code == 200
    for rol in ("planillero", "consultor"):
        assert como(rol).get("/api/indicadores").status_code == 403


def test_sensibles_solo_activos_y_celdas_pequenas(sesion):
    db = sesion.app.state.db
    datos = [{"nombre": f"URSULA INVENTADA SENSIBLE {i}", "lat": CASCO[1], "lon": CASCO[0], "geo_precision": "direccion",
              "sensibles": {"etnia": "Raizal" if i < 3 else "Ninguno"}} for i in range(12)]
    insertar_personas(db, datos)
    assert "sensibles" not in sesion.get("/api/indicadores").json()
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"sensibles_activos": True}}, upsert=True)
    from app import geometria
    z = sesion.get("/api/indicadores", params={"alcance": "zona", "poligono": geometria.codificar(ANILLO)}).json()
    assert z["kpi"]["personas"] == 12 and z["sensibles"]["etnia"] == {"Raizal": "<5", "Ninguno": 9}
    assert "actividad" not in z and "reuniones" not in z and z["area"]["m2"] > 0
