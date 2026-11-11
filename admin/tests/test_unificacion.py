"""Unificación en bloque (`app/unificacion.py`, `GET /api/coincidencias/grupos`, `POST /api/coincidencias/lote`):
grupos como componentes conexos, señales a favor y en contra, niveles, bloqueos, vista previa de la ficha unida, filtros
y conteos, resolución en lote (unir en estrella, excluir, separar, cambios, turno, límites) y costo. Solo datos
inventados."""
import json
import time
from collections import Counter

import pytest

from app import db as bd
from app import unificacion as un
from ayudas_g3 import coordinador
from conftest import insertar_personas

GRUPOS = "/api/coincidencias/grupos"
LOTE = "/api/coincidencias/lote"


# ───────────────────────────── Ayudas ─────────────────────────────

def _ficha(db, fuente="manual", **datos) -> int:
    """Una ficha inventada activa (con `bd.nueva_persona`) y su completitud calculada."""
    d = bd.nueva_persona(db, {"nombre": "PERSONA INVENTADA UNIFICACION", **datos}, fuente)
    if "completitud" not in datos:
        d["completitud"] = bd.completitud(d)
    db.personas.insert_one(d)
    return d["_id"]


def _par(db, a, b, puntaje=0.9, motivo="cruce_cedula", estado="pendiente", detalle=None) -> int:
    cid = bd.siguiente_id(db, "coincidencias")
    db.coincidencias.insert_one({"_id": cid, "persona_id": a, "candidato_id": b, "puntaje": puntaje, "estado": estado,
                                 "motivo": motivo, "detalle": detalle if detalle is not None else {}})
    return cid


def _p(_id=1, **campos) -> dict:
    """Una ficha en memoria para las pruebas puras de señales y vista previa."""
    return {"_id": _id, "nombre": "PERSONA INVENTADA PURA", "fuentes": ["manual"], **campos}


def _claves(senales) -> set:
    return {s["clave"] for s in senales}


def _db(c):
    return c.app.state.db


def _grupos(c, **params) -> dict:
    r = c.get(GRUPOS, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _lote(c, *grupos, estado=200) -> dict:
    r = c.post(LOTE, json={"grupos": list(grupos)})
    assert r.status_code == estado, r.text
    return r.json()


# ───────────────────────────── Señales y niveles (puras) ─────────────────────────────

def test_senales_a_favor():
    a = _p(1, nombre="ANSELMO INVENTADO QUINTERO", cedula="90007001", telefonos=[{"numero": "3007000001"}],
           correo="anselmo@ejemplo.test", nac_aprox="1980-05-04", nac_exacta=True, direccion_norm="CL 49 # 45-12",
           lugar_id=3, ficha="0589300007001", votacion={"puesto_id": 2, "mesa": 4}, fuentes=["cedulas"])
    tramite = {"telefono": "3007000099;3007000001", "correo": "ANSELMO@ejemplo.test", "ficha": "0589300007001"}
    b = _p(2, nombre="ANSELMO INVENTADO QUINTERO", tramites=[tramite],
           nac_aprox="1980-05-04", nac_exacta=True, direccion_norm="CL 49 # 45-12", lugar_id=3,
           votacion={"puesto_id": 2, "mesa": 4}, fuentes=["tramites"])
    favor, contra = un.senales(a, b, {"motivo": "cruce_cedula"})
    assert _claves(favor) == {"mismo_telefono", "mismo_correo", "misma_fecha", "misma_direccion", "misma_ficha",
                              "mismo_puesto", "nombre_igual", "completa_cedula", "fuentes_complementarias"}
    assert contra == []
    # Cada señal trae un texto corto para la interfaz; la ficha del hogar avisa que no prueba la misma persona
    textos = {s["clave"]: s["texto"] for s in favor}
    assert textos["mismo_puesto"] == "Mismo puesto y mesa de votación" and "parientes" in textos["misma_ficha"]
    # Con la dirección igual no se repite el barrio; sin ella, el barrio cuenta solo
    favor, _ = un.senales({**a, "direccion_norm": None}, b)
    assert "mismo_lugar" in _claves(favor) and "misma_direccion" not in _claves(favor)
    # La cédula de una entre las anteriores de la otra, palabras en común y edad parecida
    c = _p(3, nombre="ANSELMO QUINTERO RUIZ", cedulas_anteriores=["90007001"], nac_aprox="1981-01-01")
    d = _p(4, nombre="ANSELMO INVENTADO QUINTERO", cedula="90007001", nac_aprox="1980-06-01")
    favor, contra = un.senales(c, d)
    assert {"cedula_anterior", "palabras", "edad_parecida"} <= _claves(favor) and not contra
    assert next(s for s in favor if s["clave"] == "palabras")["texto"] == "2 palabras del nombre en común"


def test_senales_en_contra():
    a = _p(1, nombre="JUAN INVENTADO PEREZ", sexo="M", nac_aprox="1950-01-01", nac_exacta=True)
    b = _p(2, nombre="CARLOS INVENTADO PEREZ", sexo="F", nac_aprox="1990-01-01", nac_exacta=True)
    _, contra = un.senales(a, b)
    assert _claves(contra) == {"sexo_distinto", "edad_distinta", "fecha_distinta", "nombre_pila_distinto"}
    # Nombre de pila: otro género, casi igual, y lo que no cuenta (errata, otro orden, un nombre omitido)
    pila = un.nombre_de_pila_distinto
    assert "género" in pila("DANIEL INVENTADO ROJAS", "DANIELA INVENTADO ROJAS")["texto"]
    assert "casi igual" in pila("ROSALBA INVENTADA ROJAS", "OSALBA INVENTADA ROJAS")["texto"]
    assert "distinto" in pila("JOSE MARIA INVENTADO", "MARIA JOSE INVENTADO")["texto"]
    assert pila("FABIO MAURICO INVENTADO", "FABIO MAURICIO INVENTADO") is None
    assert pila("PEREZ GOMEZ JUAN", "JUAN PEREZ GOMEZ") is None
    assert pila("JHON INVENTADO PEREZ", "JOHN INVENTADO PEREZ") is None
    assert pila("MARIA DEL CARMEN RUIZ", "CARMEN RUIZ") is None
    assert pila("JUAN PEREZ", "JUAN PEREZ GOMEZ") is None
    # Un segundo nombre de otro género también: es justo un par «variante» que no se debe unir en lote
    assert pila("MARIA DANIELA PEREZ GOMEZ", "MARIA DANIEL PEREZ GOMEZ") is not None
    # Homónimo sin nada en común; con un teléfono en común ya no
    h1, h2 = _p(1, nombre="HOMERO INVENTADO IGUAL"), _p(2, nombre="HOMERO INVENTADO IGUAL")
    assert "homonimo_sin_evidencia" in _claves(un.senales(h1, h2, {"motivo": "homonimo"})[1])
    assert "homonimo_sin_evidencia" not in _claves(un.senales(h1, h2)[1])
    con_tel = {**h2, "telefono": "3007000002"}
    assert not un.senales({**h1, "telefono": "3007000002"}, con_tel, {"motivo": "homonimo"})[1]
    # Dos filas de la misma base importada sin cédula; dos altas del equipo no (es el duplicado de siempre)
    t1, t2 = _p(1, fuentes=["tramites"]), _p(2, fuentes=["tramites"])
    assert _claves(un.senales(t1, t2)[1]) == {"misma_fuente"}
    assert not un.senales(_p(1, fuentes=["manual"]), _p(2, fuentes=["panel"]))[1]
    assert not un.senales(t1, {**t2, "cedula": "90007003"})[1]


def test_nivel_del_par():
    fuerte, otra, media = {"clave": "mismo_telefono"}, {"clave": "mismo_correo"}, {"clave": "misma_direccion"}
    contra = [{"clave": "sexo_distinto"}]
    assert un.nivel_par(0.9, [fuerte], []) == "alta"
    assert un.nivel_par(0.84, [fuerte, media], []) == "media"
    assert un.nivel_par(0.5, [fuerte, otra], []) == "alta"
    assert un.nivel_par(None, [fuerte], []) == "media"         # sin puntaje cuenta como 0,75
    assert un.nivel_par(None, [fuerte, otra], []) == "alta"
    assert un.nivel_par(1.0, [fuerte, otra], contra) == "baja"
    assert un.nivel_par(1.0, [media], []) == "media"
    assert un.puntaje_del_nombre({"puntaje": 0.9, "detalle": {"puntaje_nombre": 0.75}}) == 0.75
    assert un.puntaje_del_nombre({"puntaje": 0.9, "detalle": None}) == 0.9
    assert un.puntaje_del_nombre({"puntaje": None, "detalle": "Es la misma"}) is None


def test_el_nivel_no_cuenta_dos_veces_el_telefono():
    """El puntaje final ya suma el teléfono en común: el nivel se decide con el del nombre solo."""
    a = _p(1, telefono="3007000201", cedula="90007030", fuentes=["cedulas"])
    b = _p(2, telefono="3007000201", fuentes=["tramites"])
    c = {"_id": 10, "persona_id": 1, "candidato_id": 2, "puntaje": 0.9, "motivo": "cruce_cedula",
         "detalle": {"puntaje_nombre": 0.75, "telefono": True}}
    g = un.evaluar_grupo({frozenset((1, 2)): [c]}, {1: a, 2: b}, set(), {})
    assert (g["nivel"], g["puntaje"], g["pares"][0]["puntaje"]) == ("media", 0.9, 0.9)
    c["detalle"]["puntaje_nombre"] = 0.88
    assert un.evaluar_grupo({frozenset((1, 2)): [c]}, {1: a, 2: b}, set(), {})["nivel"] == "alta"


def test_par_repetido_en_orden_inverso_se_evalua_junto():
    """(a, b) y (b, a) se muestran como un solo par, pero cuentan los dos: el homónimo baja el nivel aunque sea el de
    id mayor, las notas se ven y el puntaje que hay no lo tapa un reporte sin puntaje."""
    a = _p(1, nombre="HOMERO INVENTADO REPETIDO", fuentes=["tramites"])
    b = _p(2, nombre="HOMERO INVENTADO REPETIDO", fuentes=["cedulas"], cedula="90008501")
    cruce = {"_id": 3, "persona_id": 2, "candidato_id": 1, "puntaje": 0.95, "motivo": "cruce_cedula", "detalle": {}}
    homonimo = {"_id": 5, "persona_id": 1, "candidato_id": 2, "puntaje": 0.95, "motivo": "homonimo",
                "detalle": {"homonimo": True}}
    g = un.evaluar_grupo({frozenset((1, 2)): [cruce, homonimo]}, {1: a, 2: b}, set(), {})
    assert "homonimo_sin_evidencia" in _claves(g["pares"][0]["en_contra"]) and g["nivel"] == "baja"
    assert g["motivos"] == ["cruce_cedula", "homonimo"] and g["clave"] == "3" and len(g["pares"]) == 1
    reporte = {"_id": 2, "persona_id": 1, "candidato_id": 2, "puntaje": None, "motivo": "reporte",
               "detalle": "Es la misma: lo confirmó por teléfono"}
    con_nota = {**cruce, "detalle": {"nota": "Vino a la reunión"}}
    g = un.evaluar_grupo({frozenset((1, 2)): [reporte, con_nota]}, {1: a, 2: b}, set(), {})
    par = g["pares"][0]
    assert (par["id"], par["motivo"], par["puntaje"]) == (2, "reporte", 0.95)
    assert par["nota"] == "Es la misma: lo confirmó por teléfono · Vino a la reunión"
    assert g["motivos"] == ["cruce_cedula", "reporte"] and g["puntaje"] == 0.95


def test_no_autorizo_con_otra_que_si_nunca_es_muy_probable(sesion):
    """Al unir gana el «no» y se borran los sensibles que la otra autorizó: un grupo así queda como mucho «probable»,
    con su aviso, y nunca entra en «Unir las N muy probables» (que pide `nivel=alta`)."""
    a = _p(1, telefono="3008600001", cedula="90008601", fuentes=["cedulas"], consentimiento="si")
    b = _p(2, telefono="3008600001", fuentes=["tramites"], consentimiento="no")
    c = {"_id": 10, "persona_id": 2, "candidato_id": 1, "puntaje": 0.95, "motivo": "cruce_cedula",
         "detalle": {"puntaje_nombre": 0.95}}
    evaluar = lambda x, y: un.evaluar_grupo({frozenset((1, 2)): [c]}, {1: x, 2: y}, set(), {})  # noqa: E731
    assert evaluar({**a, "consentimiento": "pendiente"}, {**b, "consentimiento": "si"})["nivel"] == "alta"
    for otra in ("si", "pendiente", None):
        g = evaluar({**a, "consentimiento": otra}, b)
        assert g["nivel"] == "media" and g["pares"][0]["nivel"] == "alta", otra
        assert any("no autorizó" in x and "muy probables" in x for x in g["avisos"])
    assert evaluar({**a, "consentimiento": "no"}, b)["nivel"] == "alta"   # las dos «no»: nada que perder
    # Lo que se baja no deja de bajar: con algo en contra sigue «dudosa»
    assert evaluar({**a, "sexo": "F"}, {**b, "sexo": "M"})["nivel"] == "baja"
    # Con la API: no aparece entre las muy probables
    db = _db(sesion)
    x = _ficha(db, nombre="XIMENA INVENTADA NOAUTORIZO", cedula="90008602", fuente="cedulas", telefono="3008600002")
    y = _ficha(db, nombre="XIMENA INVENTADA NOAUTORIZO", fuente="planilla", telefono="3008600002")
    db.personas.update_one({"_id": x}, {"$set": {"consentimiento": "si", "sensibles": {"etnia": "Ninguno"},
                                                 "sensibles_autorizados": ["etnia"]}})
    db.personas.update_one({"_id": y}, {"$set": {"consentimiento": "no"}})
    _par(db, y, x, puntaje=0.95, detalle={"puntaje_nombre": 0.95})
    res = _grupos(sesion)
    assert res["niveles"]["alta"] == 0 and res["grupos"][0]["nivel"] == "media"
    assert _grupos(sesion, nivel="alta")["total"] == 0


def test_destino_y_orden_de_union():
    a = _p(5, completitud=40)
    b = _p(3, completitud=70)
    c = _p(9, cedula="90007010", completitud=10)
    d = _p(2, completitud=70)
    assert un.destino_de([a, b, c, d]) == 9                    # la que tiene cédula
    assert un.destino_de([a, b, d]) == 2                       # la más completa; con empate, la de menor id
    assert [p["_id"] for p in un.orden_union([a, b, c, d], 9)] == [9, 2, 3, 5]
    assert [p["_id"] for p in un.orden_union([a, b, c, d], 5)] == [5, 9, 2, 3]  # conservar otra: igual en estrella


def test_vista_previa():
    lugares = {7: "BARRIO INVENTADO", 8: "VEREDA INVENTADA"}
    d = _p(1, nombre="ROSA INVENTADA PEREZ", sexo="F", correo=None, direccion="CALLE 1", fuentes=["manual"],
           telefonos=[{"numero": "3007000101", "fuentes": ["panel"]}], lugar_id=7, lat=None,
           procedencia={"direccion": {"fuente": "panel", "ts": "x", "uid": 0}})
    o1 = _p(2, nombre="ROSA PEREZ", cedula="90007020", sexo="M", correo="rosa@ejemplo.test", direccion="CALLE 2",
            fuentes=["cedulas"], telefonos=[{"numero": "3007000102", "fuentes": ["cedulas"]}],
            procedencia={"correo": {"fuente": "cedulas"}, "sexo": {"fuente": "cedulas"}}, edad=40,
            edad_ref="2026-01-01", lugar_id=8, lat=6.9, geo_precision="vereda")
    o2 = _p(3, correo="otra@ejemplo.test", direccion="CALLE 2", fuentes=["tramites"], sexo="M",
            telefonos=[{"numero": "3007000101"}, {"numero": "3007000103", "fuentes": ["tramites"]}])
    vista = {f["campo"]: f for f in un.vista_previa([o2, d, o1], 1, lugares)}
    assert [f["campo"] for f in un.vista_previa([d], 1)] == [c for c, _ in un.CAMPOS_VISTA]
    # El nombre del destino se conserva (sin alternos: la unión no guarda el del origen)
    assert vista["nombre"] == {"campo": "nombre", "etiqueta": "Nombre", "valor": "ROSA INVENTADA PEREZ",
                               "fuente": "manual", "de": 1, "otros": []}
    # La cédula la trae la única que la tiene; el correo, la primera en el orden de unión; lo distinto, a alternos
    assert (vista["cedula"]["valor"], vista["cedula"]["de"], vista["cedula"]["otros"]) == ("90007020", 2, [])
    assert (vista["correo"]["valor"], vista["correo"]["fuente"], vista["correo"]["de"]) == \
        ("rosa@ejemplo.test", "cedulas", 2)
    assert vista["correo"]["otros"] == [{"valor": "otra@ejemplo.test", "fuente": "tramites", "de": 3}]
    # El valor del destino gana; los distintos de las otras van a alternos sin repetirse
    assert (vista["direccion"]["valor"], vista["direccion"]["fuente"]) == ("CALLE 1", "panel")
    assert vista["direccion"]["otros"] == [{"valor": "CALLE 2", "fuente": "cedulas", "de": 2}]
    assert vista["sexo"]["valor"] == "F" and [o["valor"] for o in vista["sexo"]["otros"]] == ["M"]
    # Los teléfonos se juntan todos (el destino primero), sin alternos
    assert vista["telefonos"]["valor"] == "3007000101, 3007000102, 3007000103"
    assert (vista["telefonos"]["fuente"], vista["telefonos"]["de"], vista["telefonos"]["otros"]) == ("panel", 1, [])
    # La ubicación pasa en bloque de la mejor ubicada
    assert (vista["lugar"]["valor"], vista["lugar"]["de"]) == ("VEREDA INVENTADA", 2)
    assert vista["edad"]["valor"] is not None and vista["edad"]["de"] == 2
    assert vista["fecha_nacimiento"] == {"campo": "fecha_nacimiento", "etiqueta": "Fecha de nacimiento",
                                         "valor": None, "fuente": None, "de": None, "otros": []}


def test_vista_previa_compara_la_edad_como_la_union(sesion):
    """La unión compara la edad declarada (`modelo.comparable`), no la llevada a hoy: la vista previa también, así
    «y N valores pasan a alternos» dice lo que de verdad pasa. Se muestra la edad de hoy de la que queda."""
    from app import modelo
    db = _db(sesion)
    hoy = modelo.hoy_local()
    casos = (  # (edad y referencia del destino, de la otra) → (edad que se muestra, alternos de edad)
        ((40, hoy.isoformat()), (40, f"{hoy.year - 10}-01-01"), "40", []),  # hoy serían 40 y 50: no deja alterno
        ((40, f"{hoy.year - 6}-01-01"), (46, hoy.isoformat()), "46", ["46"]),  # hoy los dos 46: sí deja
    )
    for i, ((ed, rd), (eo, ro), muestra, alternos) in enumerate(casos):
        nombre = f"VALERIANA INVENTADA EDAD{'AB'[i]}"
        d = _ficha(db, nombre=nombre, cedula=f"9000830{i}", fuente="cedulas", edad=ed, edad_ref=rd)
        o = _ficha(db, nombre=nombre, fuente="tramites", edad=eo, edad_ref=ro)
        p = _par(db, o, d)
        g = _grupos(sesion, persona=d)["grupos"][0]
        edad = next(f for f in g["vista_previa"] if f["campo"] == "edad")
        assert (edad["valor"], edad["de"], [x["valor"] for x in edad["otros"]]) == (muestra, d, alternos), edad
        assert _lote(sesion, {"pares": [p], "decision": "unir"})["unidas"] == 1
        unida = db.personas.find_one({"_id": d})
        assert [str(a["valor"]) for a in unida.get("alternos") or [] if a["campo"] == "edad"] == alternos
        assert unida["edad"] == ed and modelo.edad_efectiva(unida) == int(muestra)


def test_miembros_traen_la_fuente_de_sus_telefonos_y_de_su_barrio(sesion):
    """La interfaz pinta la insignia de cada ficha buscando la fuente en `procedencia`: los teléfonos (sin
    procedencia: cada número lleva sus fuentes) y el barrio o vereda (la ubicación no la anota) también la traen, con
    la regla de la vista previa."""
    db = _db(sesion)
    lugar = bd.siguiente_id(db, "lugares")
    db.lugares.insert_one({"_id": lugar, "nombre": "VEREDA INVENTADA FUENTE", "tipo": "vereda"})
    a = _ficha(db, nombre="WENCESLAO INVENTADO FUENTE", cedula="90008401", fuente="cedulas", lugar_id=lugar,
               telefonos=[{"numero": "3008400001", "fuentes": ["tramites", "cedulas"]}])
    b = _ficha(db, nombre="WENCESLAO INVENTADO FUENTE", fuente="tramites", telefono="3008400002")
    c = _ficha(db, nombre="WENCESLAO INVENTADO FUENTE", fuente="planilla",
               procedencia={"correo": {"fuente": "planilla", "ts": "x", "uid": 0}})
    _par(db, b, a), _par(db, c, a)
    g = _grupos(sesion)["grupos"][0]
    prov = {m["id"]: m["procedencia"] for m in g["miembros"]}
    assert prov[a] == {"telefonos": "tramites", "lugar": "cedulas"}   # la del número principal y la de la ficha
    assert prov[b] == {"telefonos": "tramites"}                        # sin barrio, sin fuente de barrio
    assert prov[c] == {"correo": "planilla"}                           # sin teléfonos ni barrio: nada inventado
    # La misma fuente que la vista previa da al valor que queda
    vista = {f["campo"]: f for f in g["vista_previa"]}
    assert (vista["telefonos"]["fuente"], vista["lugar"]["fuente"]) == (prov[a]["telefonos"], prov[a]["lugar"])


def test_miembro_lleva_el_rango_de_ubicacion():
    """La interfaz rehace la vista previa al elegir otra ficha o excluir alguna: sin el rango no sabría de cuál pasa la
    ubicación en bloque y prometería el barrio de la conservada (que la unión no deja si otra está mejor ubicada)."""
    lugares = {1: "BATALLON", 2: "LA CONDOR"}
    rangos = [un.miembro(_p(i, **geo), lugares)["rango_ubicacion"] for i, geo in enumerate([
        {"geo_manual": "punto", "lat": 6.9, "lugar_id": 1}, {"geo_precision": "direccion", "lat": 6.9},
        {"geo_manual": "lugar", "lugar_id": 2}, {"geo_precision": "centro", "lat": 6.9, "lugar_id": 2}, {}], 1)]
    assert rangos == [4, 3, 2, 1, 0]
    # El mismo criterio de la vista previa del servidor: conservar la peor ubicada no le quita el lugar a la mejor
    a = _p(1, cedula="90007030", geo_manual="punto", lat=6.9, lugar_id=1)
    b = _p(2, geo_precision="centro", lat=6.9, lugar_id=2)
    lugar = next(f for f in un.vista_previa([a, b], 2, lugares) if f["campo"] == "lugar")
    assert (lugar["valor"], lugar["de"]) == ("BATALLON", 1)


def test_miembro_lleva_la_edad_que_compara_la_union():
    """La interfaz rehace la vista previa al elegir otra ficha: con solo `edad` (la de hoy, también por la fecha de
    nacimiento) comparaba la edad llevada a hoy, y la unión compara la declarada. `edad_declarada` es lo que compara
    `vista_previa` (el texto de la guardada) y `edad_declarada_hoy`, lo que muestra de la que queda."""
    from datetime import timedelta
    from app import modelo
    ref = modelo.hoy_local() - timedelta(days=10)
    # 40 declarados hace diez días y 40 declarados diez años antes (hoy 50): la unión no deja alterno
    a = _p(1, cedula="90007040", edad=40, edad_ref=ref.isoformat())
    b = _p(2, edad=40, edad_ref=modelo._restar_anios(ref, 10).isoformat())
    # Con fecha de nacimiento, `edad` sale de ella; la vista previa sigue mostrando la declarada llevada a hoy
    c = _p(3, edad=40, edad_ref=ref.isoformat(), fecha_nacimiento="1970-01-01")
    ma, mb, mc = (un.miembro(p, {}) for p in (a, b, c))
    assert (ma["edad_declarada"], ma["edad_declarada_hoy"], ma["edad"]) == ("40", 40, 40)
    assert (mb["edad_declarada"], mb["edad_declarada_hoy"], mb["edad"]) == ("40", 50, 50)
    assert (mc["edad_declarada"], mc["edad_declarada_hoy"]) == ("40", 40) and mc["edad"] == modelo.edad_efectiva(c) != 40
    assert (un.miembro(_p(4), {})["edad_declarada"], un.miembro(_p(4), {})["edad_declarada_hoy"]) == (None, None)
    # Lo mismo que usa `vista_previa`, con cualquiera de las dos conservada: muestra la declarada llevada a hoy de la que
    # queda y no pasa nada a alternos (las dos declararon «40»)
    for destino, queda in ((1, ma), (2, mb)):
        edad = next(f for f in un.vista_previa([a, b], destino) if f["campo"] == "edad")
        assert (edad["valor"], edad["de"], edad["otros"]) == (str(queda["edad_declarada_hoy"]), queda["id"], [])


def test_detalle_y_nota():
    assert un.detalle_y_nota(None) == ({}, None)
    assert un.detalle_y_nota("  Es la misma  ") == ({}, "Es la misma")
    assert un.detalle_y_nota({"homonimo": True}) == ({"homonimo": True}, None)
    assert un.detalle_y_nota({"reporte": True, "nota": "x"}) == ({"reporte": True, "nota": "x"}, "x")


# ───────────────────────────── Grupos (API) ─────────────────────────────

def test_grupos_son_componentes_conexos_y_sin_pares_repetidos(sesion):
    db = _db(sesion)
    a = _ficha(db, cedula="90007101", telefono="3007100001", fuente="cedulas")
    b = _ficha(db, telefono="3007100001", fuente="tramites")
    c = _ficha(db, telefono="3007100001", fuente="tramites")
    d, e = _ficha(db, nombre="OTRA PERSONA INVENTADA"), _ficha(db, nombre="OTRA PERSONA INVENTADA")
    p1 = _par(db, a, b)
    p2 = _par(db, c, b, puntaje=0.8)
    p3 = _par(db, b, a)                     # el mismo par en orden inverso
    p4 = _par(db, d, e, puntaje=None, motivo="reporte", detalle="Las dio de alta dos veces")
    res = _grupos(sesion)
    assert (res["total"], res["pares"], res["personas"]) == (2, 3, 5)
    g = next(x for x in res["grupos"] if x["destino"] == a)
    assert g["clave"] == f"{p1}-{p2}" and p3 not in [p["id"] for p in g["pares"]]
    assert [m["id"] for m in g["miembros"]][0] == a and {m["id"] for m in g["miembros"]} == {a, b, c}
    assert g["puntaje"] == 0.8 and g["motivos"] == ["cruce_cedula"]       # el par más débil
    par = next(p for p in g["pares"] if p["id"] == p1)
    assert (par["a"], par["b"], par["motivo"], par["nota"]) == (a, b, "cruce_cedula", None)
    assert "mismo_telefono" in _claves(par["a_favor"])
    m = g["miembros"][0]
    assert set(m) == {"id", "nombre", "cedula", "telefonos", "correo", "direccion", "lugar", "edad", "sexo",
                      "fecha_nacimiento", "fuentes", "procedencia", "tramites", "listas", "completitud",
                      "consentimiento", "rango_ubicacion", "edad_declarada", "edad_declarada_hoy"}
    assert m["telefonos"] == ["3007100001"] and m["fuentes"] == ["cedulas"]
    assert {f["campo"] for f in g["vista_previa"]} == {c for c, _ in un.CAMPOS_VISTA}
    otro = next(x for x in res["grupos"] if x["destino"] != a)
    assert otro["pares"][0]["id"] == p4 and otro["pares"][0]["nota"] == "Las dio de alta dos veces"
    assert otro["puntaje"] is None
    assert set(res) == {"total", "pares", "personas", "niveles", "motivos", "pagina", "por_pagina", "grupos"}
    # Un par con una ficha suprimida o unida no forma grupo (y queda cerrado)
    db.personas.update_one({"_id": e}, {"$set": {"eliminado": True}})
    assert _grupos(sesion)["total"] == 1
    assert db.coincidencias.find_one({"_id": p4})["estado"] == "cerrada"


def test_grupo_bloqueado_por_dos_cedulas_y_por_un_rechazo_previo(sesion):
    db = _db(sesion)
    t = _ficha(db, nombre="CASIMIRO INVENTADO BLOQUEO", fuente="tramites")
    c1 = _ficha(db, nombre="CASIMIRO INVENTADO BLOQUEO", cedula="90007201", fuente="cedulas")
    c2 = _ficha(db, nombre="CASIMIRO INVENTADO BLOQUEO", cedula="90007202", fuente="cedulas")
    _par(db, c1, t), _par(db, c2, t)
    g = _grupos(sesion)["grupos"][0]
    assert g["nivel"] == "bloqueada" and "cédulas distintas" in g["avisos"][0]
    # Un rechazo anterior entre dos de sus miembros (decisión humana) también lo bloquea
    trio = [_ficha(db, nombre="DIONISIA INVENTADA RECHAZO") for _ in range(3)]
    x, y, z = trio
    _par(db, x, y), _par(db, y, z)
    _par(db, x, z, estado="rechazada")
    g = next(g for g in _grupos(sesion)["grupos"] if g["destino"] in trio)
    assert g["nivel"] == "bloqueada" and any("personas distintas" in a for a in g["avisos"])
    # Y uno marcado con una ficha que después se unió: el rechazo no se reapunta, pero sube a la ficha activa
    u, v, w = (_ficha(db, nombre="EUSEBIA INVENTADA RAIZ") for _ in range(3))
    _par(db, w, v, estado="rechazada")
    bd.fusionar(db, u, v, "admin")
    _par(db, w, u)
    g = next(g for g in _grupos(sesion)["grupos"] if g["destino"] in (u, w))
    assert g["nivel"] == "bloqueada"
    assert sum(g["nivel"] == "bloqueada" for g in _grupos(sesion)["grupos"]) == 3


def test_grupo_grande_y_contradiccion_entre_fichas_sin_par_directo(sesion):
    db = _db(sesion)
    cadena = [_ficha(db, nombre="FIDELINA INVENTADA CADENA", telefono="3007300001") for _ in range(7)]
    for x, y in zip(cadena, cadena[1:]):
        _par(db, x, y, puntaje=0.95)
    g = _grupos(sesion)["grupos"][0]
    assert g["nivel"] == "baja" and "Grupo grande (7 fichas)" in g["avisos"][0]
    assert all(p["nivel"] == "alta" for p in g["pares"])
    # A~B y B~C sin nada en contra, pero A y C tienen sexo distinto: quedarían unidas, así que el grupo baja
    a = _ficha(db, nombre="GENOVEVA INVENTADA SEXO", sexo="F", telefono="3007300002")
    b = _ficha(db, nombre="GENOVEVA INVENTADA SEXO", telefono="3007300002")
    c = _ficha(db, nombre="GENOVEVA INVENTADA SEXO", sexo="M", telefono="3007300002")
    _par(db, a, b, puntaje=0.95), _par(db, b, c, puntaje=0.95)
    g = next(g for g in _grupos(sesion)["grupos"] if g["destino"] in (a, b, c))
    assert [p["nivel"] for p in g["pares"]] == ["alta", "alta"] and g["nivel"] == "baja"
    assert any("no tienen una coincidencia directa" in x and "sexo distinto" in x for x in g["avisos"])


def _escenario_filtros(db) -> dict:
    """Cinco grupos: dos «alta» (0,95 y 0,90), un reporte «media», un homónimo «baja» y uno «bloqueada»."""
    ids = {}
    for n, p in (("uno", 0.95), ("dos", 0.90)):
        t = _ficha(db, nombre=f"ANSELMO INVENTADO {n.upper()}", telefono=f"300740000{len(ids)}", fuente="tramites")
        c = _ficha(db, nombre=f"ANSELMO INVENTADO {n.upper()}", telefono=f"300740000{len(ids)}",
                   cedula=f"9000740{len(ids)}", fuente="cedulas")
        ids[n] = (_par(db, c, t, puntaje=p), c)
    a, b = _ficha(db, nombre="REPORTADA INVENTADA TRES"), _ficha(db, nombre="REPORTADA INVENTADA TRES")
    ids["media"] = (_par(db, a, b, puntaje=None, motivo="reporte", detalle=None), a)
    a = _ficha(db, nombre="HOMERO INVENTADO IGUAL", telefono="3007400010", fuente="tramites")
    b = _ficha(db, nombre="HOMERO INVENTADO IGUAL", telefono="3007400011", fuente="tramites")
    ids["baja"] = (_par(db, a, b, puntaje=1.0, motivo="homonimo", detalle={"homonimo": True}), a)
    t = _ficha(db, nombre="CASIMIRA INVENTADA DOBLE", fuente="tramites")
    c1 = _ficha(db, nombre="CASIMIRA INVENTADA DOBLE", cedula="90007411", fuente="cedulas")
    c2 = _ficha(db, nombre="CASIMIRA INVENTADA DOBLE", cedula="90007412", fuente="cedulas")
    ids["bloqueada"] = (_par(db, c1, t, puntaje=0.99), c1)
    _par(db, c2, t, puntaje=0.98)
    return ids


def test_orden_filtros_paginacion_y_conteos(sesion):
    db = _db(sesion)
    ids = _escenario_filtros(db)
    res = _grupos(sesion)
    assert (res["total"], res["pares"], res["personas"]) == (5, 6, 11)
    assert res["niveles"] == {"alta": 2, "media": 1, "baja": 1, "bloqueada": 1}
    assert res["motivos"] == {"cruce_cedula": 3, "nombre_telefono": 0, "homonimo": 1, "variante": 0, "reporte": 1,
                              "alta_simultanea": 0}
    orden = [g["pares"][0]["id"] for g in res["grupos"]]
    assert orden == [ids[k][0] for k in ("uno", "dos", "media", "baja", "bloqueada")]
    assert [g["nivel"] for g in res["grupos"]] == ["alta", "alta", "media", "baja", "bloqueada"]
    assert (res["pagina"], res["por_pagina"]) == (1, 25)
    # `niveles` con el filtro de motivo y sin el de nivel; `motivos` al revés
    r = _grupos(sesion, motivo="cruce_cedula")
    assert r["niveles"] == {"alta": 2, "media": 0, "baja": 0, "bloqueada": 1} and r["total"] == 3
    assert r["motivos"] == res["motivos"]
    r = _grupos(sesion, nivel="alta")
    assert r["motivos"]["cruce_cedula"] == 2 and r["motivos"]["homonimo"] == 0 and r["niveles"] == res["niveles"]
    assert (r["total"], r["pares"], r["personas"]) == (2, 2, 4)
    r = _grupos(sesion, nivel="bloqueada", motivo="cruce_cedula")
    assert r["total"] == 1 and r["grupos"][0]["pares"][0]["id"] == ids["bloqueada"][0]
    # Paginación
    assert [g["pares"][0]["id"] for g in _grupos(sesion, por_pagina=2, pagina=2)["grupos"]] == \
        [ids["media"][0], ids["baja"][0]]
    assert len(_grupos(sesion, por_pagina=2, pagina=3)["grupos"]) == 1
    assert _grupos(sesion, por_pagina=2, pagina=4)["grupos"] == [] and \
        _grupos(sesion, por_pagina=2, pagina=4)["total"] == 5
    # Vacíos: sin filtro (la interfaz manda `nivel=`); desconocidos y fuera de rango, 422
    assert _grupos(sesion, nivel="", motivo="", persona="")["total"] == 5
    for params in ({"nivel": "segura"}, {"motivo": "otro"}, {"por_pagina": 101}, {"por_pagina": 0}, {"pagina": 0},
                   {"persona": "abc"}):
        assert sesion.get(GRUPOS, params=params).status_code == 422, params


def test_persona_trae_solo_su_grupo(sesion):
    db = _db(sesion)
    ids = _escenario_filtros(db)
    r = _grupos(sesion, persona=ids["baja"][1])
    assert r["total"] == 1 and r["grupos"][0]["pares"][0]["id"] == ids["baja"][0]
    assert r["niveles"] == {"alta": 0, "media": 0, "baja": 1, "bloqueada": 0}
    sola = _ficha(db, nombre="SOLITARIA INVENTADA")
    assert _grupos(sesion, persona=sola)["total"] == 0


def test_get_coincidencias_con_un_reporte_sin_nota(sesion, como):
    db = _db(sesion)
    a, b = _ficha(db, nombre="REPORTE INVENTADO SINNOTA"), _ficha(db, nombre="REPORTE INVENTADO SINNOTA")
    p = como("planillero")
    assert p.post(f"/api/personas/{a}/duplicado", json={"con_id": b}).status_code == 200
    assert db.coincidencias.find_one({"motivo": "reporte"})["detalle"] is None
    lista = sesion.get("/api/coincidencias").json()
    assert lista[0]["detalle"] == {} and lista[0]["nota"] is None
    c = _ficha(db, nombre="ALTA INVENTADA SIMULTANEA")
    _par(db, a, c, puntaje=None, motivo="alta_simultanea", detalle="Altas parecidas en menos de 10 minutos")
    nota = {x["motivo"]: x["nota"] for x in sesion.get("/api/coincidencias").json()}
    assert nota == {"reporte": None, "alta_simultanea": "Altas parecidas en menos de 10 minutos"}
    g = _grupos(sesion)["grupos"][0]
    assert {p["motivo"]: p["nota"] for p in g["pares"]} == nota


def test_insignia_no_cuenta_pares_imposibles(sesion):
    db = _db(sesion)
    a, b = _ficha(db, cedula="90007501"), _ficha(db, cedula="90007502")
    _par(db, a, b)
    assert sesion.get("/api/insignias").json()["calidad"] == 0
    c, d = _ficha(db), _ficha(db)
    _par(db, c, d)
    assert sesion.get("/api/insignias").json()["calidad"] == 1


def test_el_reporte_del_equipo_sobre_un_par_de_la_importacion_se_ve(sesion):
    """La importación crea el par como (ficha nueva, existente) y el reporte de un duplicado lo crea ordenado: quedan
    los dos pendientes. El grupo los muestra como un par, pero con el motivo y la nota del reporte."""
    db = _db(sesion)
    viejo = _ficha(db, nombre="YOLANDA INVENTADA REPORTE", fuente="tramites")
    nuevo = _ficha(db, nombre="YOLANDA INVENTADA REPORTE", cedula="90008701", fuente="cedulas")
    cruce = _par(db, nuevo, viejo, puntaje=0.82)
    nota = "La señora confirmó por teléfono que es ella: misma persona"
    r = sesion.post(f"/api/personas/{viejo}/duplicado", json={"con_id": nuevo, "nota": nota})
    assert r.status_code == 200 and r.json()["id"] != cruce
    res = _grupos(sesion)
    assert (res["total"], res["pares"], res["motivos"]["reporte"]) == (1, 1, 1)
    g = res["grupos"][0]
    assert g["motivos"] == ["cruce_cedula", "reporte"] and g["clave"] == str(cruce)
    assert (g["pares"][0]["id"], g["pares"][0]["nota"]) == (cruce, nota)
    assert _grupos(sesion, motivo="reporte")["total"] == 1
    # Unir el grupo resuelve los dos
    assert _lote(sesion, {"pares": [cruce], "decision": "unir"})["unidas"] == 1
    assert {x["estado"] for x in db.coincidencias.find()} == {"aceptada"}


def test_cerrar_imposibles_reapunta_los_pares_de_una_ficha_unida(sesion):
    """En medio de una unión el origen ya figura como unido y sus pares todavía no pasaron al destino: si en ese
    momento se cierran las imposibles (lo hacen el tablero, la lista de grupos y `/api/insignias` en cada vista), los
    pares de la ficha unida pasan a la ficha activa en que terminó, como al unir, en vez de cerrarse y perderse."""
    db = _db(sesion)
    a = _ficha(db, nombre="ZOILA INVENTADA RAIZ", cedula="90008801")
    b, c, d = (_ficha(db, nombre="ZOILA INVENTADA RAIZ") for _ in range(3))
    e = _ficha(db, nombre="ZOILA INVENTADA RAIZ", cedula="90008802")
    f = _ficha(db, nombre="ZOILA INVENTADA RAIZ")
    suprimida, encadenada = _ficha(db), _ficha(db)
    entre = _par(db, a, b)            # quedan en la misma ficha: ya no hay nada que decidir
    sigue = _par(db, b, c)            # el candidato que la unión pasaría a A
    ya = _par(db, a, d)
    repetido = _par(db, b, d)         # (A, D) ya existe: se cierra, como en `_reapuntar_coincidencias`
    cedulas = _par(db, e, b)          # con la cédula de A, dos cédulas distintas
    con_suprimida = _par(db, suprimida, c)
    de_cadena = _par(db, encadenada, f)
    db.personas.update_one({"_id": b}, {"$set": {"fusionada_en": a}})               # la unión, a mitad
    db.personas.update_one({"_id": encadenada}, {"$set": {"fusionada_en": b}})      # un eslabón más
    db.personas.update_one({"_id": suprimida}, {"$set": {"eliminado": True}})
    assert bd.cerrar_coincidencias_imposibles(db) == 4
    co = {x["_id"]: x for x in db.coincidencias.find()}
    assert (co[sigue]["persona_id"], co[sigue]["candidato_id"], co[sigue]["estado"]) == (a, c, "pendiente")
    assert (co[de_cadena]["persona_id"], co[de_cadena]["candidato_id"], co[de_cadena]["estado"]) == \
        (a, f, "pendiente")
    assert co[ya]["estado"] == "pendiente"
    for x in (entre, repetido, cedulas, con_suprimida):
        assert (co[x]["estado"], co[x]["resuelto_por"]) == ("cerrada", "sistema"), co[x]
    # Con `ids`, lo mismo: los de la ficha unida que se nombra
    g = _ficha(db, nombre="ZOILA INVENTADA RAIZ")
    otro = _par(db, g, b)
    assert bd.cerrar_coincidencias_imposibles(db, [g]) == 0
    assert (db.coincidencias.find_one({"_id": otro})["persona_id"],
            db.coincidencias.find_one({"_id": otro})["candidato_id"]) == (g, a)


def test_insignias_en_medio_de_una_union_no_pierden_el_candidato(sesion, monkeypatch):
    """La carrera de verdad: alguien acepta A~B y, entre que B queda marcada como unida y sus pares pasan a A, el menú
    de otra persona pide `/api/insignias`. B~C debe terminar como A~C pendiente, no cerrado."""
    db = _db(sesion)
    a = _ficha(db, nombre="ABIGAIL INVENTADA CARRERA", cedula="90009001", fuente="cedulas")
    b, c = (_ficha(db, nombre="ABIGAIL INVENTADA CARRERA", fuente="tramites") for _ in range(2))
    p1, p2 = _par(db, a, b), _par(db, b, c)
    original, insignias = bd._reapuntar_coincidencias, []

    def con_insignias(*args, **kw):
        insignias.append(sesion.get("/api/insignias").status_code)
        return original(*args, **kw)

    monkeypatch.setattr(bd, "_reapuntar_coincidencias", con_insignias)
    assert sesion.post(f"/api/coincidencias/{p1}", json={"decision": "aceptar"}).status_code == 200
    assert insignias == [200]
    x = db.coincidencias.find_one({"_id": p2})
    assert (x["estado"], x["persona_id"], x["candidato_id"]) == ("pendiente", a, c)
    assert _grupos(sesion)["total"] == 1


# ───────────────────────────── Resolución en lote ─────────────────────────────

def test_lote_une_tres_en_estrella(sesion):
    db = _db(sesion)
    a = _ficha(db, nombre="HERMINIA INVENTADA ESTRELLA", cedula="90007601", fuente="cedulas", telefono="3007600001")
    b = _ficha(db, nombre="HERMINIA INVENTADA ESTRELLA", fuente="tramites", telefono="3007600001",
               correo="herminia@ejemplo.test")
    c = _ficha(db, nombre="HERMINIA INVENTADA ESTRELLA", fuente="tramites", telefono="3007600002")
    p1, p2 = _par(db, b, a), _par(db, c, b)     # una cadena: se une en estrella en la que tiene cédula
    p3 = _par(db, a, b)                         # el mismo par en el otro orden
    res = _lote(sesion, {"pares": [p1, p2], "decision": "unir"})
    assert res == {"resultados": [{"ok": True, "decision": "unir", "conservada": a, "unidas": 2, "separadas": 0}],
                   "unidas": 2, "separadas": 0, "errores": 0}
    for o in (b, c):
        f = db.personas.find_one({"_id": o})
        assert f["fusionada_en"] == a and f["nombre"] == "FUSIONADA"
    queda = db.personas.find_one({"_id": a})
    assert queda["correo"] == "herminia@ejemplo.test" and {"3007600001", "3007600002"} <= \
        {t["numero"] for t in queda["telefonos"]}
    lote = None
    for pid in (p1, p2, p3):
        x = db.coincidencias.find_one({"_id": pid})
        assert (x["estado"], x["conservada"], x["resuelto_por"]) == ("aceptada", a, "admin"), x
        assert x["resuelto_en"] and isinstance(x["lote"], int)
        lote = lote or x["lote"]
        assert x["lote"] == lote
    # Cada unión, auditada con su persona; el lote, una sola entrada con conteos y sin ids ni nombres
    uniones = list(db.auditoria.find({"accion": "fusionar"}))
    assert sorted(json.loads(u["detalle"])["origen"] for u in uniones) == sorted([b, c])
    assert all((u["entidad"], u["entidad_id"], u["uid"]) == ("persona", a, 0) for u in uniones)
    entradas = list(db.auditoria.find({"accion": "resolver_lote"}))
    assert len(entradas) == 1 and (entradas[0]["entidad"], entradas[0]["entidad_id"]) == (None, None)
    assert json.loads(entradas[0]["detalle"]) == {"grupos": 1, "unidas": 2, "separadas": 0, "errores": 0}
    assert "HERMINIA" not in entradas[0]["detalle"]
    assert _grupos(sesion)["total"] == 0
    # El turno quedó libre: una importación puede empezar
    assert bd.tomar_turno(db, "importando", "otra-importacion", 1)


def test_lote_excluir_rechaza_sus_pares_y_exige_que_las_demas_sigan_conectadas(sesion):
    db = _db(sesion)
    a = _ficha(db, nombre="ISIDORA INVENTADA EXCLUIR", cedula="90007701", fuente="cedulas")
    b, c, d = (_ficha(db, nombre="ISIDORA INVENTADA EXCLUIR", fuente="tramites") for _ in range(3))
    p1, p2, p3 = _par(db, a, b), _par(db, b, c), _par(db, a, d)
    # Sin B, A y C no tienen una coincidencia directa: no se toca nada
    r = _lote(sesion, {"pares": [p1, p2, p3], "decision": "unir", "excluir": [b]})["resultados"][0]
    assert (r["ok"], r["codigo"]) == (False, "no_conexo") and "únalas por separado" in r["error"]
    assert {x["estado"] for x in db.coincidencias.find()} == {"pendiente"}
    assert db.personas.count_documents({"fusionada_en": {"$ne": None}}) == 0
    # Sin D: se unen A, B y C, y el par con D queda como personas distintas
    res = _lote(sesion, {"pares": [p1, p2, p3], "decision": "unir", "excluir": [d], "conservar": a})
    assert res["resultados"][0] == {"ok": True, "decision": "unir", "conservada": a, "unidas": 2, "separadas": 1}
    assert (res["unidas"], res["separadas"], res["errores"]) == (2, 1, 0)
    x = db.coincidencias.find_one({"_id": p3})
    assert x["estado"] == "rechazada" and x["resuelto_por"] == "admin" and x["lote"]
    assert db.personas.find_one({"_id": d})["fusionada_en"] is None
    # Si D vuelve a aparecer con la ficha unida, el grupo sale bloqueado por esa decisión
    _par(db, d, a)
    assert _grupos(sesion)["grupos"][0]["nivel"] == "bloqueada"


def test_lote_separar(sesion):
    db = _db(sesion)
    a, b, c = (_ficha(db, nombre="JACINTA INVENTADA SEPARAR") for _ in range(3))
    p1, p2 = _par(db, a, b), _par(db, b, c)
    p3 = _par(db, b, a)                     # repetido en el otro orden: se resuelve con su par
    res = _lote(sesion, {"pares": [p1, p2], "decision": "separar"})
    assert res == {"resultados": [{"ok": True, "decision": "separar", "unidas": 0, "separadas": 3}], "unidas": 0,
                   "separadas": 3, "errores": 0}
    for pid in (p1, p2, p3):
        x = db.coincidencias.find_one({"_id": pid})
        assert x["estado"] == "rechazada" and x["resuelto_por"] == "admin" and x["resuelto_en"]
    assert db.personas.count_documents({"_id": {"$in": [a, b, c]}, **bd.ACTIVA}) == 3
    assert _grupos(sesion)["total"] == 0


def test_lote_cambio_si_un_par_ya_se_resolvio_y_los_demas_siguen(sesion):
    db = _db(sesion)
    a, b = _ficha(db, nombre="LEOPOLDA INVENTADA CAMBIO"), _ficha(db, nombre="LEOPOLDA INVENTADA CAMBIO")
    c, d = _ficha(db, nombre="MODESTA INVENTADA SIGUE"), _ficha(db, nombre="MODESTA INVENTADA SIGUE")
    p1, p2 = _par(db, a, b), _par(db, c, d)
    assert sesion.post(f"/api/coincidencias/{p1}", json={"decision": "rechazar"}).status_code == 200
    res = _lote(sesion, {"pares": [p1], "decision": "unir"}, {"pares": [p2], "decision": "unir"},
                {"pares": [999999], "decision": "separar"})
    r1, r2, r3 = res["resultados"]
    assert (r1["ok"], r1["codigo"], r1["error"]) == (False, "cambio", "El grupo cambió: recargue.")
    assert r2["ok"] and r2["unidas"] == 1 and (r3["ok"], r3["codigo"]) == (False, "cambio")
    assert (res["unidas"], res["errores"]) == (1, 2)
    assert db.personas.find_one({"_id": b})["fusionada_en"] is None
    # El mismo grupo dos veces en un lote: la segunda ya no está pendiente
    e, f = _ficha(db), _ficha(db)
    p3 = _par(db, e, f)
    r = _lote(sesion, {"pares": [p3], "decision": "unir"}, {"pares": [p3], "decision": "separar"})["resultados"]
    assert r[0]["ok"] and r[1]["codigo"] == "cambio"


def test_lote_valida_cedulas_rechazos_y_la_ficha_que_se_conserva(sesion):
    db = _db(sesion)
    t = _ficha(db, nombre="NICOLASA INVENTADA CEDULAS", fuente="tramites")
    c1 = _ficha(db, nombre="NICOLASA INVENTADA CEDULAS", cedula="90007801", fuente="cedulas")
    c2 = _ficha(db, nombre="NICOLASA INVENTADA CEDULAS", cedula="90007802", fuente="cedulas")
    p1, p2 = _par(db, c1, t), _par(db, c2, t)
    r = _lote(sesion, {"pares": [p1, p2], "decision": "unir"})["resultados"][0]
    assert r["codigo"] == "cedulas_distintas" and "···801" in r["error"] and "90007801" not in r["error"]
    assert {x["estado"] for x in db.coincidencias.find({"_id": {"$in": [p1, p2]}})} == {"pendiente"}
    for conservar, excluir in ((c2, [c2]), (424242, [c2])):
        r = _lote(sesion, {"pares": [p1, p2], "decision": "unir", "excluir": excluir,
                           "conservar": conservar})["resultados"][0]
        assert r["codigo"] == "conservar_invalida", r
    r = _lote(sesion, {"pares": [p1, p2], "decision": "unir", "excluir": [424242]})["resultados"][0]
    assert r["codigo"] == "cambio"
    # Excluir la otra cédula desbloquea: la de trámites se une a la que tiene cédula
    r = _lote(sesion, {"pares": [p1, p2], "decision": "unir", "excluir": [c2]})["resultados"][0]
    assert r == {"ok": True, "decision": "unir", "conservada": c1, "unidas": 1, "separadas": 1}
    assert db.coincidencias.find_one({"_id": p2})["estado"] == "rechazada"
    # Un rechazo anterior entre las incluidas
    x, y, z = (_ficha(db, nombre="OLEGARIA INVENTADA RECHAZO") for _ in range(3))
    q1, q2 = _par(db, x, y), _par(db, y, z)
    _par(db, z, x, estado="rechazada")
    r = _lote(sesion, {"pares": [q1, q2], "decision": "unir"})["resultados"][0]
    assert r["codigo"] == "rechazada_antes" and "personas distintas" in r["error"]
    r = _lote(sesion, {"pares": [q1, q2], "decision": "unir", "excluir": [z]})["resultados"][0]
    assert r["ok"] and r["unidas"] == 1 and r["separadas"] == 1


def test_lote_parcial_si_una_union_falla_a_mitad(sesion, monkeypatch):
    db = _db(sesion)
    a = _ficha(db, nombre="PETRONILA INVENTADA PARCIAL", cedula="90007901")
    b, c = _ficha(db, nombre="PETRONILA INVENTADA PARCIAL"), _ficha(db, nombre="PETRONILA INVENTADA PARCIAL")
    p1, p2 = _par(db, a, b), _par(db, a, c)
    original, llamadas = bd.fusionar, []

    def fusionar(*args, **kw):
        llamadas.append(args[2])
        if len(llamadas) == 2:
            raise bd.FusionImposible("La ficha ya se unió o se suprimió")
        return original(*args, **kw)

    monkeypatch.setattr(bd, "fusionar", fusionar)
    res = _lote(sesion, {"pares": [p1, p2], "decision": "unir"})
    r = res["resultados"][0]
    assert (r["ok"], r["codigo"], r["unidas"], r["conservada"]) == (False, "parcial", 1, a)
    assert "Se unieron 1 de 2" in r["error"] and res["errores"] == 1 and res["unidas"] == 1
    hecho = db.coincidencias.find_one({"estado": "aceptada"})
    assert hecho["conservada"] == a and hecho["lote"]
    assert db.coincidencias.count_documents({"estado": "pendiente"}) == 1


def test_lote_con_el_turno_tomado_responde_409_sin_tocar_nada(sesion):
    db = _db(sesion)
    a, b = _ficha(db), _ficha(db)
    p = _par(db, a, b)
    assert bd.tomar_turno(db, "importando", "una-importacion", 15)
    r = sesion.post(LOTE, json={"grupos": [{"pares": [p], "decision": "unir"}]})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "importando"
    assert "unión en lote" in r.json()["detail"]["mensaje"]
    assert db.coincidencias.find_one({"_id": p})["estado"] == "pendiente"
    assert db.auditoria.count_documents({"accion": {"$in": ["fusionar", "resolver_lote"]}}) == 0
    bd.soltar_turno(db, "importando", "una-importacion")
    assert _lote(sesion, {"pares": [p], "decision": "unir"})["unidas"] == 1


def test_importar_durante_un_lote_nombra_las_dos_tareas(sesion, monkeypatch, tmp_path):
    """El lote toma el turno de la importación: quien importa mientras tanto recibe el 409 de siempre (`importando`),
    pero el mensaje dice que puede ser una unión en lote, no solo «una importación» que parecería trabada."""
    from ayudas_g1 import tramite
    from conftest import excel_tramites
    db = _db(sesion)
    a = _ficha(db, nombre="BRIGIDA INVENTADA TURNO", cedula="90009101")
    b = _ficha(db, nombre="BRIGIDA INVENTADA TURNO")
    p = _par(db, a, b)
    excel = excel_tramites(tmp_path / "t.xlsx", [tramite(9101, "CELESTINA INVENTADA TURNO")]).read_bytes()
    original, respuestas = bd._reapuntar_coincidencias, []

    def importar_en_medio(*args, **kw):
        respuestas.append(sesion.post("/api/importar", files=[("archivos", ("t.xlsx", excel))]))
        return original(*args, **kw)

    monkeypatch.setattr(bd, "_reapuntar_coincidencias", importar_en_medio)
    assert _lote(sesion, {"pares": [p], "decision": "unir"})["unidas"] == 1
    (r,) = respuestas
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "importando"
    mensaje = r.json()["detail"]["mensaje"]
    assert "importación" in mensaje and "unión en lote" in mensaje
    # El lote y la importación dicen lo mismo, sea cual sea la que tiene el turno
    monkeypatch.undo()
    assert bd.tomar_turno(db, "importando", "una-importacion", 15)
    lote = sesion.post(LOTE, json={"grupos": [{"pares": [p], "decision": "unir"}]})
    assert lote.status_code == 409 and lote.json()["detail"]["mensaje"] == mensaje
    bd.soltar_turno(db, "importando", "una-importacion")
    assert sesion.post("/api/importar", files=[("archivos", ("t.xlsx", excel))]).status_code == 200


def test_georreferenciar_una_sola_vez_por_peticion(sesion, monkeypatch):
    from app.pipeline import importar as imp
    db = _db(sesion)
    original, llamadas = imp.georreferenciar, []

    def contar(db_, solo_ids=None):
        llamadas.append(sorted(solo_ids) if solo_ids else None)
        return original(db_, solo_ids)

    from app.api import calidad
    monkeypatch.setattr(imp, "georreferenciar", contar)
    monkeypatch.setattr(calidad, "georreferenciar", contar)  # la cola individual la importa por su nombre
    a1 = _ficha(db, nombre="QUITERIA INVENTADA GEO", cedula="90008001", direccion="CALLE 50 # 49-10")
    b1, c1 = _ficha(db, nombre="QUITERIA INVENTADA GEO"), _ficha(db, nombre="QUITERIA INVENTADA GEO")
    a2 = _ficha(db, nombre="RUPERTA INVENTADA GEO", cedula="90008002")
    b2 = _ficha(db, nombre="RUPERTA INVENTADA GEO")
    grupos = [{"pares": [_par(db, a1, b1), _par(db, b1, c1)], "decision": "unir"},
              {"pares": [_par(db, b2, a2)], "decision": "unir"}]
    assert _lote(sesion, *grupos)["unidas"] == 3
    assert llamadas == [sorted([a1, a2])]
    assert db.personas.find_one({"_id": a1})["direccion_norm"]  # quedó ubicada al final
    # Las demás uniones siguen ubicando como antes: una vez por unión (y la de la cola individual, una sola vez)
    llamadas.clear()
    x, y = _ficha(db, nombre="SATURNINA INVENTADA GEO"), _ficha(db, nombre="SATURNINA INVENTADA GEO")
    assert sesion.post(f"/api/personas/{x}/fusionar", json={"con_id": y}).status_code == 200
    assert llamadas == [[x]]
    llamadas.clear()
    v, w = _ficha(db, nombre="TEODORA INVENTADA GEO"), _ficha(db, nombre="TEODORA INVENTADA GEO")
    assert sesion.post(f"/api/coincidencias/{_par(db, v, w)}", json={"decision": "aceptar"}).status_code == 200
    assert len(llamadas) == 1


def test_permisos_solo_administrador_y_coordinador(sesion, como):
    db = _db(sesion)
    a, b = _ficha(db), _ficha(db)
    p = _par(db, a, b)
    for rol in ("planillero", "consultor"):
        c = como(rol)
        for r in (c.get(GRUPOS), c.post(LOTE, json={"grupos": [{"pares": [p], "decision": "unir"}]})):
            assert r.status_code == 403 and r.json()["detail"]["codigo"] == "permiso", (rol, r.text)
    k = coordinador(sesion.app, db)
    assert k.get(GRUPOS).json()["total"] == 1
    r = k.post(LOTE, json={"grupos": [{"pares": [p], "decision": "separar"}]})
    assert r.status_code == 200 and r.json()["separadas"] == 1
    assert db.coincidencias.find_one({"_id": p})["resuelto_por"] == k.usuario
    # Escribir pide el token CSRF, como toda escritura
    sin = sesion.post(LOTE, json={"grupos": [{"pares": [p], "decision": "separar"}]}, headers={"X-CSRF-Token": "x"})
    assert sin.status_code == 403


@pytest.mark.parametrize("cuerpo", [
    {"grupos": []},
    {"grupos": [{"pares": [1], "decision": "unir"}] * 51},
    {"grupos": [{"pares": [], "decision": "unir"}]},
    {"grupos": [{"pares": list(range(1, 62)), "decision": "unir"}]},
    {"grupos": [{"pares": [1], "decision": "unir", "excluir": list(range(1, 22))}]},
    {"grupos": [{"pares": [1], "decision": "aceptar"}]},
    {"grupos": [{"pares": [0], "decision": "unir"}]},
    {"grupos": [{"pares": [1], "decision": "unir", "conservar": -3}]},
    {},
])
def test_lote_422_con_los_limites(sesion, cuerpo):
    assert sesion.post(LOTE, json=cuerpo).status_code == 422


def test_lote_en_los_limites_se_acepta(sesion):
    r = _lote(sesion, *[{"pares": list(range(1, 61)), "decision": "separar", "excluir": list(range(1, 21))}] * 50)
    assert r["errores"] == 50 and all(x["codigo"] == "cambio" for x in r["resultados"])


def test_con_coincidencias_de_una_importacion(sesion, tmp_path):
    """Los pares que deja la importación (dos cédulas para la misma ficha de trámites) forman un grupo bloqueado; se
    desbloquea excluyendo la que sobra, y reimportar no los vuelve a proponer."""
    from ayudas_g1 import cedula, tramite
    from conftest import excel_cedulas, excel_tramites
    db = _db(sesion)
    nombre = "CASIMIRO INVENTADO LOTE"
    archivos = [("archivos", ("t.xlsx", excel_tramites(tmp_path / "t.xlsx", [tramite(9001, nombre, "3009009001")])
                              .read_bytes())),
                ("archivos", ("c.xlsx", excel_cedulas(tmp_path / "c.xlsx", [cedula("90009001", nombre, "3009009001"),
                                                                             cedula("90009002", nombre)]).read_bytes()))]
    assert sesion.post("/api/importar", files=archivos).json()["cedulas_en_revision"] == 2
    res = _grupos(sesion)
    assert (res["total"], res["pares"], res["personas"]) == (1, 2, 3)
    g = res["grupos"][0]
    assert g["nivel"] == "bloqueada" and g["motivos"] == ["cruce_cedula"]
    uno, dos = (db.personas.find_one({"cedula": c})["_id"] for c in ("90009001", "90009002"))
    tramites = db.personas.find_one({"tramites.id_externo": "9001"})["_id"]
    par_uno = next(p for p in g["pares"] if uno in (p["a"], p["b"]))
    assert {"mismo_telefono", "nombre_igual", "completa_cedula", "fuentes_complementarias"} <= _claves(par_uno["a_favor"])
    r = _lote(sesion, {"pares": [p["id"] for p in g["pares"]], "decision": "unir", "excluir": [dos]})["resultados"][0]
    assert r == {"ok": True, "decision": "unir", "conservada": uno, "unidas": 1, "separadas": 1}
    assert db.personas.find_one({"_id": tramites})["fusionada_en"] == uno
    assert len(db.personas.find_one({"_id": uno})["tramites"]) == 1
    assert _grupos(sesion)["total"] == 0
    assert sesion.post("/api/importar", files=archivos).status_code == 200
    assert _grupos(sesion)["total"] == 0


# ───────────────────────────── Costo ─────────────────────────────

def _letras(n: int) -> str:
    """0 → «BA», 1 → «BB»…: palabras inventadas distintas para cada grupo (el nombre normalizado no lleva dígitos)."""
    out = ""
    for _ in range(3):
        n, r = divmod(n, 24)
        out = chr(66 + r) + out
    return out


def test_dos_mil_pares_con_pocas_consultas_y_rapido(sesion):
    db = _db(sesion)
    datos = []
    for g in range(1000):
        for k in range(3):
            datos.append({"nombre": f"GRUPO{_letras(g)} INVENTADO {_letras(g + 7)}", "telefono": f"3{g:05d}{k:04d}",
                          "sexo": "F", "edad": 30 + k})
    ids = insertar_personas(db, datos)
    pares = []
    for g in range(1000):
        x, y, z = ids[3 * g:3 * g + 3]
        pares += [(x, y, 0.9), (y, z, 0.8)]
    primero = bd.siguiente_id(db, "coincidencias", len(pares))
    db.coincidencias.insert_many([{"_id": primero + i, "persona_id": a, "candidato_id": b, "puntaje": p,
                                   "estado": "pendiente", "motivo": "nombre_telefono", "detalle": {}}
                                  for i, (a, b, p) in enumerate(pares)])
    # Una consulta por colección, sean cuantos sean los pares (con el perfilador de esta base de prueba)
    db.command("profile", 2)
    try:
        grupos = un.armar_grupos(db)
    finally:
        db.command("profile", 0)
    assert len(grupos) == 1000
    consultas = _lecturas_por_coleccion(db)
    assert consultas["personas"] <= 3 and consultas["coincidencias"] <= 3 and consultas["lugares"] <= 1, consultas
    inicio = time.perf_counter()
    res = _grupos(sesion, por_pagina=100)
    tarda = time.perf_counter() - inicio
    assert (res["total"], res["pares"], res["personas"]) == (1000, 2000, 3000) and len(res["grupos"]) == 100
    assert tarda < 10, f"GET /grupos con 2 000 pares tardó {tarda:.1f} s"


def _lecturas_por_coleccion(db) -> Counter:
    """Cuántas lecturas (`find`) hubo en cada colección, según el perfilador de la base."""
    c = Counter()
    for x in db.system.profile.find({"op": "query"}, {"ns": 1}):
        c[x["ns"].split(".", 1)[1]] += 1
    return c
