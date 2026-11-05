"""Hallazgos de seguridad e integridad de la verificación móvil, reproducidos como ataques con la sesión del rol (solo
datos inventados):

1. La búsqueda y los filtros de P no son un oráculo: con prefijos o subcadenas de dígitos no se reconstruye la cédula
   ni el teléfono de quien no autorizó ni los teléfonos de un menor (tampoco con el total de Habitantes, otros filtros
   u órdenes); C no ubica por teléfono a quien no ve.
2. P no recupera los teléfonos de un menor registrando visitas con `telefono_indice`, ni los lee en sus acercamientos.
3. El 409 `cambiada` de PATCH no le muestra a P un campo fuera de su proyección (`lider`) y cuenta como lectura.
4. Una unión y un PATCH que llena la cédula vacía del destino con otra no funden a dos personas distintas.
"""
from __future__ import annotations

import pytest

from ayudas_g3 import autorizada, contactable, persona, tomar

NO_CED, NO_TEL = "77000004", "3157000004"
MENOR_TELS = ["6040700033", "3180700033", "3160700033"]
ADULTO_CED, ADULTO_TEL = "88000111", "3001234567"


def _con_telefonos(db, pid: int, nums: list[str]) -> None:
    from app import modelo
    tels = [modelo.telefono_nuevo(n, "panel", "2026-01-01") for n in nums]
    db.personas.update_one({"_id": pid}, {"$set": {"telefonos": tels, **modelo.derivar_telefonos(tels)}})


def _escenario(db) -> dict:
    """Quien dijo «no», un menor con tres números y un adulto tratable, en el mismo barrio."""
    lid = db.lugares.find_one({"tipo": "barrio"})["_id"]
    no = persona(db, nombre="LEOCADIA INVENTADA SALCEDO", cedula=NO_CED, tipo_documento="CC", consentimiento="no",
                 sexo="F", direccion="CALLE 12 # 3-45", direccion_norm="CALLE 12 3 45", lugar_id=lid,
                 completitud=90)
    _con_telefonos(db, no, [NO_TEL])
    menor = persona(db, nombre="ABIGAIL INVENTADA BOHORQUEZ", cedula="1012345678", tipo_documento="TI", lugar_id=lid,
                    completitud=10)
    _con_telefonos(db, menor, MENOR_TELS)
    adulto = persona(db, nombre="EUSTAQUIO INVENTADO SALCEDO", cedula=ADULTO_CED, tipo_documento="CC", lugar_id=lid,
                     direccion="CALLE 99 # 1-23", direccion_norm="CALLE 99 1 23", completitud=50)
    _con_telefonos(db, adulto, [ADULTO_TEL])
    return {"no": no, "menor": menor, "adulto": adulto, "lugar": lid}


def _ids_buscar(c, q: str) -> set[int]:
    r = c.get("/api/buscar", params={"q": q})
    assert r.status_code == 200, (q, r.text[:200])
    return {f["id"] for f in r.json()}


def _habitantes(c, **params) -> dict:
    r = c.get("/api/personas", params=params)
    assert r.status_code == 200, (params, r.text[:200])
    return r.json()


# ───────────────────────────── 1. Búsqueda sin oráculo ─────────────────────────────

def test_planillero_no_reconstruye_cedula_ni_telefono_de_quien_no_autorizo(sesion, como):
    db = sesion.app.state.db
    e = _escenario(db)
    p = como("planillero")
    # El ataque: un prefijo correcto y uno equivocado deben dar lo mismo, en la búsqueda y en el total de Habitantes
    for correcto, errado in (("SALCEDO 7700", "SALCEDO 7701"), ("SALCEDO 3157", "SALCEDO 3158"),
                             ("SALCEDO 7000004", "SALCEDO 7000005"), ("LEOCADIA 770000", "LEOCADIA 770001")):
        assert e["no"] not in _ids_buscar(p, correcto), correcto
        t_ok = _habitantes(p, q=correcto, pagina=1000)["total"]
        t_mal = _habitantes(p, q=errado, pagina=1000)["total"]
        assert t_ok == t_mal, (correcto, t_ok, t_mal)
    # Reconstrucción dígito a dígito: ningún primer paso le sirve
    pasos = [d for d in "0123456789" if e["no"] in _ids_buscar(p, f"SALCEDO 770{d}")]
    assert pasos == []
    # Ni el dato entero la ubica: es un dato que P no ve
    for q in (NO_CED, NO_TEL, f"SALCEDO {NO_CED}", "315 700 0004"):
        assert e["no"] not in _ids_buscar(p, q), q
        assert e["no"] not in {f["id"] for f in _habitantes(p, q=q)["filas"]}, q
    # Tampoco la dirección (oculta): «CALLE» no la trae, pero el nombre sí, con su fila mínima
    assert e["no"] not in _ids_buscar(p, "LEOCADIA CALLE")
    assert e["no"] in _ids_buscar(p, "LEOCADIA SALCEDO")
    # Los tres últimos de la cédula, que la fila ya muestra (···004), sí sirven
    assert e["no"] in _ids_buscar(p, "SALCEDO 004")
    # El administrador sigue buscando como hoy (prefijo de cédula y subcadena de teléfono)
    assert e["no"] in _ids_buscar(sesion, "SALCEDO 7700") and e["no"] in _ids_buscar(sesion, "SALCEDO 3157")


def test_planillero_no_reconstruye_los_telefonos_de_un_menor(sesion, como):
    db = sesion.app.state.db
    e = _escenario(db)
    p = como("planillero")
    for q in ("BOHORQUEZ 3180", "BOHORQUEZ 0700033", "BOHORQUEZ 6040700033", "3180700033", "0033"):
        assert e["menor"] not in _ids_buscar(p, q), q
        assert _habitantes(p, q=q, pagina=1000)["total"] == 0, q
    # Su cédula sí la ve (entera, no por prefijo)
    assert e["menor"] in _ids_buscar(p, "1012345678")
    assert e["menor"] not in _ids_buscar(p, "BOHORQUEZ 1012")


def test_planillero_busca_lo_que_ve_entero(sesion, como):
    db = sesion.app.state.db
    e = _escenario(db)
    p = como("planillero")
    for q in (ADULTO_CED, ADULTO_TEL, "300 123 4567", "+57 300 123 4567", "SALCEDO 4567", "EUSTAQUIO CALLE 99"):
        assert e["adulto"] in _ids_buscar(p, q), q
        assert e["adulto"] in {f["id"] for f in _habitantes(p, q=q)["filas"]}, q
    # Un pedazo no: ni prefijo de la cédula ni subcadena del teléfono
    for q in ("8800", "SALCEDO 300123", "1234567"):
        assert e["adulto"] not in _ids_buscar(p, q), q


def test_filtros_y_orden_de_habitantes_no_revelan_lo_oculto(sesion, como):
    db = sesion.app.state.db
    e = _escenario(db)
    p = como("planillero", asignacion={"lugares": [e["lugar"]], "areas": []})
    # Sin filtros sobre datos ocultos, quien no autorizó aparece (para no duplicarla) con su fila mínima
    assert e["no"] in {f["id"] for f in _habitantes(p, q="LEOCADIA")["filas"]}
    assert _habitantes(p, q="LEOCADIA", consentimiento="no")["total"] == 1
    # Un filtro sobre un dato que P no ve de ella (sexo, dirección, teléfono…) no la incluye nunca, coincida o no
    for params in ({"sexo": "F"}, {"sexo": "M"}, {"sin_direccion": 1}, {"con_telefono": 1}, {"con_telefono": 0},
                   {"completitud_max": 100}, {"zona": "urbana"}, {"edad_min": 0}):
        assert _habitantes(p, q="LEOCADIA", **params)["total"] == 0, params
    # Del menor, los filtros de teléfono tampoco lo incluyen
    for params in ({"con_telefono": 1}, {"con_telefono": 0}, {"varios_telefonos": 1}, {"sin_telefono": 1},
                   {"telefono_estado": "sin_verificar"}):
        assert _habitantes(p, q="ABIGAIL", **params)["total"] == 0, params
    assert _habitantes(p, q="ABIGAIL", sexo="sin")["total"] == 1  # lo demás del menor sí lo ve
    # Un orden por un dato oculto (perfil, dirección, abordaje) la deja al final, por nombre: su lugar no dice nada
    for orden in ("completitud", "-completitud", "lugar", "contacto", "reciente", "por_llamar"):
        filas = _habitantes(p, orden=orden, por_pagina=10)["filas"]
        assert filas[-1]["id"] == e["no"], (orden, [f["id"] for f in filas])
    # Paginación en dos tramos (las tratables y luego las que no autorizaron): no repite ni pierde a nadie
    extra = [persona(db, nombre=f"PERSONA INVENTADA RELLENO {i:02d}", lugar_id=e["lugar"], completitud=i * 5,
                     consentimiento="no" if i % 6 == 0 else "pendiente") for i in range(1, 15)]
    total = _habitantes(p, orden="completitud")["total"]
    assert total == 3 + len(extra)
    todas = [f for pag in (1, 2) for f in _habitantes(p, orden="completitud", por_pagina=10, pagina=pag)["filas"]]
    assert len({f["id"] for f in todas}) == len(todas) == total
    n_no = sum(1 for f in todas if f["consentimiento"] == "no")
    assert n_no == 3 and all(f["consentimiento"] == "no" for f in todas[-n_no:])
    assert [f["nombre"] for f in todas[-n_no:]] == sorted(f["nombre"] for f in todas[-n_no:])
    # «Mi trabajo»: la tarjeta «Sin teléfono» cuenta lo mismo que su enlace (sin menores)
    db.personas.update_one({"_id": e["menor"]}, {"$set": {"telefonos": [], "telefono": None, "telefono2": None}})
    t = {x["clave"]: x["n"] for x in p.get("/api/trabajo").json()["listas"]}
    enlace = _habitantes(p, situacion="vigentes", tratables=1, sin_telefono=1, por_pagina=200)
    assert t["sin_telefono"] == enlace["total"] and e["menor"] not in {f["id"] for f in enlace["filas"]}


def test_consultor_no_ubica_por_telefono_a_quien_no_ve(sesion, como):
    db = sesion.app.state.db
    e = _escenario(db)
    c = como("consultor")
    for q in (NO_TEL, MENOR_TELS[1]):
        r = c.get("/api/buscar", params={"q": q})
        assert r.status_code == 200 and r.json() == [], (q, r.text[:200])
    # Un número que no es usable (equivocado) tampoco: C solo ve los usables
    adulto = contactable(db, "FILOMENA INVENTADA LLAMADA", "3009998877")
    _con_telefonos(db, adulto, ["3009998877"])
    db.personas.update_one({"_id": adulto}, {"$set": {"telefonos.0.estado": "equivocado", "telefono": None}})
    assert c.get("/api/buscar", params={"q": "3009998877"}).json() == []
    # El de un adulto que se puede llamar, sí (llamada entrante)
    otro = contactable(db, "SERAFINA INVENTADA LLAMADA", "3009998866")
    assert [x["id"] for x in c.get("/api/buscar", params={"q": "300 999 8866"}).json()] == [otro]
    assert e["adulto"] in {x["id"] for x in c.get("/api/buscar", params={"q": ADULTO_TEL}).json()}


def test_parecidas_y_cedula_ocupada_no_ubican_a_quien_no_autorizo(sesion, como):
    db = sesion.app.state.db
    e = _escenario(db)
    p = como("planillero")
    # Parecidas del alta con la cédula (o el teléfono) de quien no autorizó y otro nombre: no la trae
    r = p.get("/api/parecidas", params={"nombre": "NOMBRE CUALQUIERA DISTINTO", "cedula": NO_CED})
    assert r.status_code == 200 and e["no"] not in {x["id"] for x in r.json()}
    r = p.get("/api/parecidas", params={"nombre": "LEOCADIA INVENTADA SALZEDO", "cedula": "77000005"})
    assert all(not x.get("cedula_distinta") for x in r.json() if x["id"] == e["no"])
    # Con un nombre a medio parecer (0,60 a 0,80), el teléfono del menor no la vuelve «parecida»
    r = p.get("/api/parecidas", params={"nombre": "ABIGAIL ROJAS", "telefono": MENOR_TELS[0]})
    assert r.status_code == 200 and e["menor"] not in {x["id"] for x in r.json()}
    assert e["menor"] in {x["id"] for x in sesion.get("/api/parecidas", params={
        "nombre": "ABIGAIL ROJAS", "telefono": MENOR_TELS[0]}).json()}
    # El alta con su cédula se rechaza (la cédula manda), pero sin decir de quién es
    r = p.post("/api/personas", json={"nombre": "Otra Persona Inventada", "cedula": NO_CED})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "cedula_ocupada"
    assert "id" not in r.json()["detail"] and "LEOCADIA" not in r.text
    sin = persona(db, nombre="CANDELARIA INVENTADA SIN CEDULA", tipo_documento="CC")
    r = p.patch(f"/api/personas/{sin}", json={"cedula": NO_CED})
    assert r.status_code == 409 and "id" not in r.json()["detail"] and "LEOCADIA" not in r.text
    # De un adulto tratable, P sí sabe de quién es (ve su cédula)
    r = p.post("/api/personas", json={"nombre": "Otra Persona Inventada", "cedula": ADULTO_CED})
    assert r.status_code == 409 and r.json()["detail"]["id"] == e["adulto"]
    # A sigue viendo de quién es
    r = sesion.post("/api/personas", json={"nombre": "Otra Persona Inventada", "cedula": NO_CED})
    assert r.status_code == 409 and r.json()["detail"]["id"] == e["no"]


# ───────────────────────────── 2. Teléfonos de un menor por los acercamientos ─────────────────────────────

def _sin_numeros(texto: str, nums) -> None:
    for n in nums:
        assert n not in texto, n


def test_planillero_no_recupera_telefonos_de_un_menor_con_visitas(sesion, como):
    db = sesion.app.state.db
    e = _escenario(db)
    p = como("planillero")
    vistos = []
    for i in range(5):
        r = p.post(f"/api/personas/{e['menor']}/acercamientos",
                   json={"canal": "visita", "resultado": "no_contesto", "telefono_indice": i})
        vistos.append((r.status_code, r.json().get("detail")))
        _sin_numeros(r.text, MENOR_TELS)
    # Siempre la misma respuesta: no dice cuántos números tiene
    assert all(v == (422, "Una visita o una reunión no lleva número") for v in vistos), vistos
    r = p.post(f"/api/personas/{e['menor']}/acercamientos",
               json={"canal": "visita", "resultado": "no_contesto", "telefono": MENOR_TELS[0]})
    assert r.status_code == 422
    assert db.acercamientos.count_documents({"persona_id": e["menor"]}) == 0
    # La visita sin número sí se registra
    r = p.post(f"/api/personas/{e['menor']}/acercamientos", json={"canal": "visita", "resultado": "no_contesto"})
    assert r.status_code == 200, r.text
    # Un acercamiento de A con número a un menor: P no lo lee, ni en la ficha ni en el historial
    r = sesion.post(f"/api/personas/{e['menor']}/acercamientos",
                    json={"canal": "llamada", "resultado": "no_contesto", "telefono_indice": 1})
    assert r.status_code == 200 and MENOR_TELS[1] in r.text
    f = p.get(f"/api/personas/{e['menor']}")
    assert f.status_code == 200 and all(a["telefono"] is None for a in f.json()["acercamientos"])
    h = p.get(f"/api/personas/{e['menor']}/acercamientos")
    assert h.status_code == 200 and all(a["telefono"] is None for a in h.json()["filas"])
    _sin_numeros(f.text + h.text, MENOR_TELS)


def test_adulto_corregido_a_menor_oculta_el_numero_de_sus_acercamientos(sesion, como):
    db = sesion.app.state.db
    pid = contactable(db, "HERMINIA INVENTADA CORREGIDA", "3140700006")
    c = como("consultor")
    tomar(c, pid)
    r = c.post(f"/api/personas/{pid}/acercamientos", json={"canal": "whatsapp", "resultado": "contesto",
                                                            "telefono_indice": 0})
    assert r.status_code == 200, r.text
    assert sesion.patch(f"/api/personas/{pid}", json={"tipo_documento": "TI", "edad": 15}).status_code == 200
    p = como("planillero")
    f = p.get(f"/api/personas/{pid}")
    assert f.json()["menor"] is True and f.json()["telefonos"] == []
    assert [a["telefono"] for a in f.json()["acercamientos"]] == [None]
    _sin_numeros(f.text + p.get(f"/api/personas/{pid}/acercamientos").text, ["3140700006", "0700006"])
    # P tampoco prueba números del menor en las rutas por número (404 o 200 dirían si es suyo)
    for metodo, ruta, cuerpo in (("PATCH", f"/api/personas/{pid}/telefonos/3140700006", {"estado": "confirmado"}),
                                 ("PATCH", f"/api/personas/{pid}/telefonos/3999999999", {"estado": "confirmado"}),
                                 ("POST", f"/api/personas/{pid}/telefonos/3140700006/principal", None)):
        r = p.request(metodo, ruta, json=cuerpo) if cuerpo else p.request(metodo, ruta)
        assert r.status_code == 403 and r.json()["detail"]["codigo"] == "permiso", (ruta, r.text[:200])


def test_cola_de_hoy_no_muestra_el_numero_de_quien_ya_no_autoriza(sesion, como):
    db = sesion.app.state.db
    pid = contactable(db, "IRMA INVENTADA REVOCA", "3150001122")
    c = como("consultor")
    tomar(c, pid)
    r = c.post(f"/api/personas/{pid}/acercamientos", json={"canal": "llamada", "resultado": "no_contactar",
                                                            "alcance": "persona", "telefono_indice": 0})
    assert r.status_code == 200, r.text
    assert db.personas.find_one({"_id": pid})["consentimiento"] == "no"
    r = c.get("/api/trabajo/cola", params={"lista": "mis_hoy"})
    fila = next(f for f in r.json()["filas"] if f["id"] == pid)
    assert fila["telefono"] is None and fila["telefono_indice"] is None and fila["canales_permitidos"] == []
    assert "3150001122" not in r.text


# ───────────────────────────── 3. El 409 «cambiada» ─────────────────────────────

def test_cambiada_no_muestra_lider_al_planillero(sesion, como):
    db = sesion.app.state.db
    pid = persona(db, nombre="OBDULIO INVENTADO LIDER", tipo_documento="CC")
    assert sesion.patch(f"/api/personas/{pid}", json={"lider": True}).status_code == 200
    p = como("planillero")
    assert "lider" not in p.get(f"/api/personas/{pid}").json()
    for base in ({"lider": False}, {"lider": True}, {"lider": False, "nombre": "\x00"}):
        r = p.patch(f"/api/personas/{pid}", json={"observaciones": "zzz-sonda", "base": base})
        assert r.status_code == 403 and r.json()["detail"]["codigo"] == "permiso", (base, r.text[:300])
        assert "valores_actuales" not in r.text
    assert db.personas.find_one({"_id": pid}).get("observaciones") is None
    # De un menor, P tampoco compara teléfonos (el 409 o el 200 dirían si acertó)
    menor = persona(db, nombre="TEOFILA INVENTADA MENOR", tipo_documento="TI")
    _con_telefonos(db, menor, ["3170700019"])
    for v in ("3170700019", "3170700018"):
        r = p.patch(f"/api/personas/{menor}", json={"ocupacion": "Estudiante", "base": {"telefono": v}})
        assert r.status_code == 403, r.text[:300]
    # Un campo que P ve: 409 con su valor, y cuenta como lectura de la ficha
    db.lecturas.delete_many({"uid": p.uid})
    r = p.patch(f"/api/personas/{pid}", json={"observaciones": "x", "base": {"nombre": "OTRO NOMBRE INVENTADO"}})
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "cambiada"
    assert r.json()["detail"]["valores_actuales"] == {"nombre": "OBDULIO INVENTADO LIDER"}
    assert db.lecturas.find_one({"uid": p.uid, "pid": pid, "ficha": True})
    # El coordinador y A sí comparan `lider`
    r = sesion.patch(f"/api/personas/{pid}", json={"observaciones": "x", "base": {"lider": False}})
    assert r.status_code == 409 and r.json()["detail"]["valores_actuales"] == {"lider": True}


# ───────────────────────────── 4. Carrera entre la unión y el PATCH ─────────────────────────────

def test_union_y_patch_que_llena_la_cedula_no_funden_dos_personas(sesion, como, monkeypatch):
    from app import db as bd
    db = sesion.app.state.db
    lid = db.lugares.find_one({"tipo": "barrio"})["_id"]
    destino = persona(db, nombre="JUANA INVENTADA DESTINO", lugar_id=lid, tipo_documento="CC")
    _con_telefonos(db, destino, ["3001110001"])
    origen = persona(db, nombre="CARLOS INVENTADO ORIGEN", cedula="71000001", tipo_documento="CC")
    p = como("planillero", asignacion={"lugares": [lid], "areas": []})
    original = bd._unir_en
    intercalado = []

    def unir_con_carrera(db_, dest, o, quien, d_antes=None):
        # Entre la lectura del destino (sin cédula) y su escritura, el planillero le llena otra cédula
        if not intercalado:
            r = p.patch(f"/api/personas/{dest}", json={"cedula": "72000002"})
            intercalado.append(r.status_code)
        return original(db_, dest, o, quien, d_antes)

    monkeypatch.setattr(bd, "_unir_en", unir_con_carrera)
    r = sesion.post(f"/api/personas/{destino}/fusionar", json={"con_id": origen})
    assert intercalado == [200]
    assert r.status_code == 409, r.text[:300]
    d, o = db.personas.find_one({"_id": destino}), db.personas.find_one({"_id": origen})
    assert d["cedula"] == "72000002" and d.get("fusionada_en") is None
    assert o["cedula"] == "71000001" and o.get("fusionada_en") is None and "cedula_en_traspaso" not in o
    assert o["nombre"] == "CARLOS INVENTADO ORIGEN"
    assert not db.auditoria.find_one({"accion": "fusionar", "entidad_id": destino})
    # Sin la carrera, las mismas dos fichas (destino ya con su propia cédula) tampoco se unen
    r = sesion.post(f"/api/personas/{destino}/fusionar", json={"con_id": origen})
    assert r.status_code == 409


def test_reparar_una_union_cortada_no_funde_cedulas_distintas(bases):
    from app import db as bd
    from conftest import insertar_personas
    db = bases()
    destino, origen = insertar_personas(db, [{"nombre": "JUANA INVENTADA CORTADA"},
                                             {"nombre": "CARLOS INVENTADO CORTADO", "cedula": "71000003"}])
    # La unión se cortó después de marcar el origen; luego alguien le llenó otra cédula al destino
    db.personas.update_one({"_id": origen}, {"$set": {"fusionada_en": destino, "cedula": None,
                                                      "cedula_en_traspaso": "71000003"}})
    db.personas.update_one({"_id": destino}, {"$set": {"cedula": "72000004"}})
    assert bd.reparar_fusiones(db) == 0
    d, o = db.personas.find_one({"_id": destino}), db.personas.find_one({"_id": origen})
    assert d["cedula"] == "72000004"
    assert o["cedula"] == "71000003" and o["fusionada_en"] is None and "cedula_en_traspaso" not in o
    assert o["nombre"] == "CARLOS INVENTADO CORTADO"


def test_reparar_una_union_cortada_compatible_sigue_uniendo(bases):
    from app import db as bd
    from conftest import insertar_personas
    db = bases()
    destino, origen = insertar_personas(db, [{"nombre": "JUANA INVENTADA COMPATIBLE"},
                                             {"nombre": "CARLOS INVENTADO COMPATIBLE", "cedula": "71000005"}])
    db.personas.update_one({"_id": origen}, {"$set": {"fusionada_en": destino, "cedula": None,
                                                      "cedula_en_traspaso": "71000005"}})
    assert bd.reparar_fusiones(db) == 1
    assert db.personas.find_one({"_id": destino})["cedula"] == "71000005"
    assert db.personas.find_one({"_id": origen})["nombre"] == "FUSIONADA"


# ───────────────────────────── Contadores ─────────────────────────────

def test_insignia_del_planillero_no_cuenta_a_quien_no_autorizo(sesion, como):
    db = sesion.app.state.db
    lid = db.lugares.find_one({"tipo": "barrio"})["_id"]
    pid = persona(db, nombre="ZENAIDA INVENTADA NO", consentimiento="no", lugar_id=lid,
                  requiere_actualizacion={"motivo": "direccion", "uid": None, "usuario": None, "ts": None, "nota": None})
    p = como("planillero", asignacion={"lugares": [lid], "areas": []})
    assert p.get("/api/insignias").json()["trabajo"] == 0
    db.personas.update_one({"_id": pid}, {"$set": {"consentimiento": "pendiente"}})
    assert p.get("/api/insignias").json()["trabajo"] == 1


@pytest.mark.parametrize("orden", ["nombre", "completitud"])
def test_coordinador_y_administrador_ordenan_y_buscan_como_hoy(sesion, orden):
    db = sesion.app.state.db
    e = _escenario(db)
    autorizada(db, e["adulto"])
    filas = sesion.get("/api/personas", params={"q": "SALCEDO", "orden": orden}).json()["filas"]
    assert {f["id"] for f in filas} == {e["no"], e["adulto"]}
    if orden == "completitud":
        assert [f["id"] for f in filas] == [e["no"], e["adulto"]]  # 90 antes que 50: sin tramos
    assert _habitantes(sesion, q="LEOCADIA", sexo="F")["total"] == 1
