"""La forma de la ficha (1.1): dos fichas nuevas no comparten listas ni objetos y PERSONA_VACIA no cambia."""
import copy

from app import db as bd
from app import modelo

CAMPOS_1_1 = {
    "tipo_documento", "cedula_verificada", "cedula_origen", "cedulas_anteriores", "sexo", "edad", "edad_ref",
    "fecha_nacimiento", "nac_aprox", "nac_exacta", "nac_base", "estado_civil", "nivel_educativo", "situacion_laboral",
    "jefe_hogar", "tenencia_vivienda", "estrato", "regimen_salud", "sensibles", "sensibles_autorizados", "telefonos",
    "telefono", "telefono2", "votacion", "puesto_votacion", "mesa", "consentimiento", "consentimiento_fecha",
    "consentimiento_medio", "consentimiento_canales", "contacto_habilitado", "mayor_declarado", "autorizacion_ultima",
    "reclamo_en_tramite", "abordaje", "abordaje_seq", "requiere_actualizacion", "en_curso", "situacion",
    "no_disponible", "nombre_fon", "creado_por", "actualizado_por", "procedencia", "alternos", "avance", "punto",
    "geo_fuente", "precision_m", "fuentes",
}


def test_persona_vacia_tiene_los_campos_de_la_especificacion():
    assert CAMPOS_1_1 <= set(bd.PERSONA_VACIA)
    assert "cedula_en_traspaso" not in bd.PERSONA_VACIA  # solo existe durante una unión
    assert {"punto", "geo_fuente", "precision_m"} <= set(bd.GEO)
    assert bd.PERSONA_VACIA["consentimiento"] == "pendiente" and bd.PERSONA_VACIA["abordaje_seq"] == 0


def test_dos_fichas_nuevas_no_comparten_listas(bases):
    db = bases()
    antes = copy.deepcopy(bd.PERSONA_VACIA)
    a = bd.nueva_persona(db, {"nombre": "Primera Persona Inventada"}, "manual")
    b = bd.nueva_persona(db, {"nombre": "Segunda Persona Inventada"}, "manual")
    for k, v in bd.PERSONA_VACIA.items():
        if isinstance(v, (list, dict)) and k != "fuentes":
            assert a[k] is not b[k] and a[k] is not bd.PERSONA_VACIA[k], k
    a["alternos"].append({"campo": "sexo", "valor": "F"})
    a["procedencia"]["sexo"] = {"fuente": "panel"}
    a["telefonos"].append(modelo.telefono_nuevo("3001112233"))
    a["no_disponible"]["cedula"] = {"motivo": "no_la_dio"}
    assert b["alternos"] == [] and b["procedencia"] == {} and b["telefonos"] == [] and b["no_disponible"] == {}
    assert bd.PERSONA_VACIA == antes


def test_el_almacen_de_la_importacion_no_toca_el_molde(bases):
    from app.pipeline.importar import _Almacen
    db = bases()
    antes = copy.deepcopy(bd.PERSONA_VACIA)
    alm = _Almacen(db)
    x = alm.nueva({"nombre": "Tercera Persona Inventada"}, "cedulas")
    y = alm.nueva({"nombre": "Cuarta Persona Inventada"}, "cedulas")
    alm.agregar(x, "listas", "Lista A")
    alm.telefonos(x, [modelo.telefono_nuevo("3001112233", "cedulas")])
    alm.aplicar(x, "sexo", "F", "cedulas")
    assert y["listas"] == [] and y["telefonos"] == [] and y["procedencia"] == {}
    assert x["telefono"] == "3001112233" and x["procedencia"]["sexo"]["fuente"] == "cedulas"
    assert bd.PERSONA_VACIA == antes


def test_nueva_persona_deriva_lo_que_puede(bases):
    db = bases()
    p = bd.nueva_persona(db, {"nombre": "Yesica Inventada", "cedula": "90000901", "telefono": "3001112233",
                              "telefono2": "8612345", "edad": 40, "lat": 7.0062, "lon": -73.9112}, "reunion")
    assert p["tipo_documento"] == "CC" and p["nombre_fon"] == modelo.claves_foneticas("Yesica Inventada")
    assert [t["numero"] for t in p["telefonos"]] == ["3001112233", "8612345"]
    assert all(t["fuentes"] == ["reunion"] for t in p["telefonos"])
    assert (p["telefono"], p["telefono2"]) == ("3001112233", "8612345")
    assert p["punto"] == modelo.punto(7.0062, -73.9112) and p["nac_aprox"] and p["nac_base"]["edad"] == 40
    sin = bd.nueva_persona(db, {"nombre": "Otra Inventada", "lat": 7.0}, "manual")
    assert sin["punto"] is None and sin["telefonos"] == [] and sin["tipo_documento"] is None
