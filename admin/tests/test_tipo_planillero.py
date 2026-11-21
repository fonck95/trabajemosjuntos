"""El planillero (P) marca el tipo de persona (líder, votante, concejal) y el «Liderado por», pero solo suma: nunca
quita un tipo ni un líder. Lo hace en las personas de su zona y en las que registra (`proyeccion.tipo_visible`), y solo
ahí los ve en la ficha (sin quién asignó cada líder ni los líderes que no autorizaron); moverla a su zona (el barrio, la
dirección o la ubicación) no se la vuelve de su zona. Busca líderes y concejales de toda la campaña por el nombre o la
cédula completa (GET /api/lideres/candidatos, sin conteos ni la cédula entera), y un id que manda no dice gratis si es
un líder: lo que no depende del líder se revisa antes, y el que se guarda cuenta como lectura. Quitar un tipo o un líder,
la lista de líderes con sus conteos y los filtros siguen siendo de A y K; sin `personas.tipo` ni `lideres.asignar`, P
tampoco marca ni asigna; el consultor (C) no ve ni marca nada; el asistente no recibe nada de esto (ni como nombre en
`editables`); y marcar un tipo no cuenta como «corrección» en los indicadores.

Las pruebas de permisos, proyección, `tipo_visible`, `editables`, la consulta de candidatos y `minimizar` corren sin
MongoDB; las de la API, con MongoDB (como en CI). Solo datos inventados."""
from __future__ import annotations

import json

from fastapi.routing import APIRoute

from app import acceso, modelo, proyeccion
from app.agente import minimizar
from app.api import lideres as api_lideres
from app.api import personas as api_personas
from ayudas_g3 import (CLAVES_LIDER_P, TIPO_Y_LIDERES, contactable, coordinador, persona, sin_vedados, sin_vedados_p,
                       tomar)

TIPOS = tuple(modelo.TIPOS_PERSONA)
ELIJA = {"mensaje": "Elija un líder o concejal de la lista", "campo": "lider_id"}
CLAVES_CANDIDATO = {"id", "nombre", "tipo", "lugar", "cedula_ult3"}


def _quien(rol: str, uid: int = 5, permisos=None, asignacion=None) -> acceso.Quien:
    return acceso.Quien(uid=uid, usuario=f"{rol}{uid}", rol=rol,
                        permisos=acceso.PERMISOS[rol] if permisos is None else frozenset(permisos),
                        asignacion=asignacion)


# ───────────────────────────── Permisos y proyección (sin base) ─────────────────────────────

def test_permisos_nuevos_solo_del_planillero():
    for permiso in ("personas.tipo", "lideres.asignar"):
        assert permiso in acceso.PERMISOS["planillero"] and permiso not in acceso.PERMISOS["consultor"]
        assert permiso not in acceso.SOLO_ADMIN
        assert _quien("coordinador", permisos={"*"}).puede(permiso) and _quien("admin", uid=0).puede(permiso)
        assert _quien("planillero").puede(permiso) and not _quien("consultor").puede(permiso)


def _rutas_de_lideres() -> list[tuple[str, str, frozenset, bool]]:
    """(método, ruta, permisos, limitar) de las rutas de app/api/lideres.py, en el orden en que se declararon."""
    out = []
    for r in api_lideres.r.routes:
        if not isinstance(r, APIRoute):
            continue
        dep = next(d.call for d in r.dependant.dependencies if hasattr(d.call, "permisos"))
        out += [(m, r.path, frozenset(dep.permisos), dep.limitar) for m in sorted(r.methods)]
    return out


def test_rutas_de_lideres_y_sus_permisos():
    rutas = {(m, ruta): (permisos, limitar) for m, ruta, permisos, limitar in _rutas_de_lideres()}
    # Buscar candidatos y asignar: P (con límite de frecuencia); quitar y la lista con conteos: A y K
    assert rutas[("POST", "/api/personas/{pid}/lideres")] == ({"lideres.asignar"}, True)
    assert rutas[("GET", "/api/lideres/candidatos")] == ({"lideres.asignar"}, True)
    assert rutas[("DELETE", "/api/personas/{pid}/lideres/{lid}")][0] == {"admin"}
    assert rutas[("GET", "/api/lideres")][0] == {"admin"}
    # «candidatos» no es un id: va antes de cualquier ruta /api/lideres/{…}
    orden = [ruta for _, ruta, _, _ in _rutas_de_lideres()]
    assert all(orden.index("/api/lideres/candidatos") < i for i, ruta in enumerate(orden)
               if ruta.startswith("/api/lideres/{"))


def test_la_ficha_de_p_trae_el_tipo_y_su_fila_no():
    assert TIPO_Y_LIDERES == proyeccion.TIPO_Y_LIDERES == {*TIPOS, "lideres"}
    assert TIPO_Y_LIDERES <= proyeccion.CAMPOS_FICHA["planillero"]
    # Nunca a quiénes lidera, la traza de las reuniones, las listas, la procedencia, el historial ni lo que quitaron
    assert not {"traidas", "intervenciones", "listas", "procedencia", "historial", "lideres_quitados", "lideres_n",
                "fuentes"} & proyeccion.CAMPOS_FICHA["planillero"]
    # Las filas de P salen también en la búsqueda, las parecidas y las reuniones (toda la base): sin el tipo
    assert not TIPO_Y_LIDERES & proyeccion.CAMPOS_FILA["planillero"]
    assert not TIPO_Y_LIDERES & (proyeccion.CAMPOS_FICHA["consultor"] | proyeccion.CAMPOS_FILA["consultor"])
    assert not TIPO_Y_LIDERES & proyeccion.CAMPOS_NO_AUTORIZO
    # El tipo y los líderes ya no son campos vedados de P (los suma con sus permisos); lo demás vedado sigue
    assert api_personas.VEDADOS_P == ("motivo_cambio_cedula", "puesto_votacion", "consentimiento_fecha")


class _Personas:
    """`db.personas` de mentira para `tipo_visible`: responde si la persona cae en el alcance y anota las consultas."""

    def __init__(self, dentro: bool, creado_por=None, reubicada_por=None):
        self.dentro, self.creado_por, self.reubicada_por, self.consultas = dentro, creado_por, reubicada_por, []

    def count_documents(self, q, limit=0):
        self.consultas.append(q)
        return int(self.dentro)

    def find_one(self, q, campos=None):
        self.consultas.append(q)
        assert campos == proyeccion.CAMPOS_TIPO_VISIBLE  # quién la registró y quiénes la movieron, nada más
        return {"_id": q.get("_id"), "creado_por": self.creado_por, "reubicada_por": self.reubicada_por}


class _Db:
    def __init__(self, dentro: bool, creado_por=None, reubicada_por=None):
        self.personas = _Personas(dentro, creado_por, reubicada_por)


def test_tipo_visible_segun_el_rol_la_zona_y_quien_la_registro():
    zona = {"lugares": [3], "areas": []}
    # A y K, siempre; C y un rol desconocido, nunca; P sin `personas.tipo`, tampoco (sin mirar la base)
    assert proyeccion.tipo_visible(None, _quien("admin", uid=0), {"_id": 1})
    assert proyeccion.tipo_visible(None, _quien("coordinador", permisos={"*"}), {"_id": 1})
    assert not proyeccion.tipo_visible(None, _quien("consultor"), {"_id": 1})
    assert not proyeccion.tipo_visible(None, None, {"_id": 1})
    sin_permiso = _quien("planillero", permisos=acceso.PERMISOS["planillero"] - {"personas.tipo"})
    assert not proyeccion.tipo_visible(None, sin_permiso, {"_id": 1})
    # P sin asignación: toda la base (como en Habitantes)
    assert proyeccion.tipo_visible(None, _quien("planillero", asignacion={"lugares": [], "areas": []}), {"_id": 1})
    p = _quien("planillero", uid=5, asignacion=zona)
    # La registró él: la ve aunque no tenga barrio, sin consultar la zona
    db = _Db(dentro=False)
    assert proyeccion.tipo_visible(db, p, {"_id": 1, "creado_por": {"uid": 5, "usuario": "planillero5"}})
    assert db.personas.consultas == []
    # De su zona sí; de otra, no. Lo que se consulta es la zona de esa persona, no su tipo
    for dentro in (True, False):
        for lider in (True, False):
            db = _Db(dentro=dentro)
            ficha = {"_id": 1, "creado_por": {"uid": 8}, "lider": lider}
            assert proyeccion.tipo_visible(db, p, ficha) is dentro
            assert db.personas.consultas == [{"$and": [{"_id": 1}, {"$or": [{"lugar_id": {"$in": [3]}}]}]}]
    # Con solo el id, quién la registró se lee de la base
    db = _Db(dentro=False, creado_por={"uid": 5})
    assert proyeccion.tipo_visible(db, p, 1)
    db = _Db(dentro=False, creado_por={"uid": 9})
    assert not proyeccion.tipo_visible(db, p, 1)
    # Si él la movió a su zona (le cambió el barrio o la ubicación cuando no la veía), su zona no cuenta; la de otro
    # planillero, sí; y lo que registró él lo sigue viendo
    db = _Db(dentro=True)
    assert not proyeccion.tipo_visible(db, p, {"_id": 1, "creado_por": {"uid": 8}, "reubicada_por": [5]})
    assert db.personas.consultas == []
    assert proyeccion.tipo_visible(_Db(dentro=True), p, {"_id": 1, "creado_por": None, "reubicada_por": [7]})
    assert proyeccion.tipo_visible(_Db(dentro=False), p, {"_id": 1, "creado_por": {"uid": 5}, "reubicada_por": [5]})
    assert not proyeccion.tipo_visible(_Db(dentro=True, creado_por={"uid": 9}, reubicada_por=[5]), p, 1)


def test_quien_mueve_a_alguien_a_su_zona_queda_anotado():
    """`api.personas.reubicada`: lo que se suma a la escritura del barrio o la ubicación. Solo un planillero que no ve
    el tipo de esa persona; A, K y C nada, y P tampoco en las de su zona o las que registró."""
    p = _quien("planillero", uid=5, asignacion={"lugares": [3], "areas": []})
    ficha = {"_id": 1, "creado_por": {"uid": 8}}
    assert api_personas.reubicada(_Db(dentro=False), p, ficha) == {
        "reubicada_por": {"$setUnion": [{"$ifNull": ["$reubicada_por", []]}, [5]]}}
    assert api_personas.reubicada(_Db(dentro=True), p, ficha) == {}
    assert api_personas.reubicada(_Db(dentro=False), p, {"_id": 1, "creado_por": {"uid": 5}}) == {}
    sin_zona = _quien("planillero", uid=5, asignacion={"lugares": [], "areas": []})
    assert api_personas.reubicada(_Db(dentro=False), sin_zona, ficha) == {}
    for otro in (_quien("admin", uid=0), _quien("coordinador", permisos={"*"}), _quien("consultor")):
        assert api_personas.reubicada(_Db(dentro=False), otro, ficha) == {}


def test_editables_del_planillero_solo_los_tipos_que_faltan():
    p = _quien("planillero")
    ficha = {"_id": 1, "nombre": "PERSONA INVENTADA", "lider": True, "votante": False}
    con = proyeccion.editables(ficha, p, con_tipos=True)
    assert [t for t in con if t in TIPOS] == ["concejal", "votante"]
    assert not set(TIPOS) & set(proyeccion.editables(ficha, p))  # fuera de su zona
    todos = {**ficha, "votante": True, "concejal": True}
    assert not set(TIPOS) & set(proyeccion.editables(todos, p, con_tipos=True))
    assert set(TIPOS) <= set(proyeccion.editables(ficha, _quien("admin", uid=0)))
    assert not set(TIPOS) & set(proyeccion.editables(ficha, _quien("consultor"), con_tipos=True))


def test_consulta_de_candidatos():
    """Por nombre, 3 letras o más; por cédula, solo la completa (5 a 11 dígitos, actual o anterior); nunca el comienzo
    de un número."""
    q = api_lideres._consulta_candidatos
    for nada in ("", "  ", "be", "b e", "1000", "123456789012", "--", "12.34"):
        assert q(nada) is None, nada
    exacta = {"$or": [{"cedula": "1000000002"}, {"cedulas_anteriores": "1000000002"}]}
    assert q("1000000002") == exacta and q("1.000.000.002") == exacta and q(" 1000-000-002 ") == exacta
    assert q("12345") == {"$or": [{"cedula": "12345"}, {"cedulas_anteriores": "12345"}]}
    por_nombre = q("Bérta inventada")
    assert por_nombre == {"$and": [{"nombre_norm": {"$regex": "BERTA"}}, {"nombre_norm": {"$regex": "INVENTADA"}}]}
    # Letras y dígitos: por las letras
    assert q("berta 1000000002") == {"$and": [{"nombre_norm": {"$regex": "BERTA"}}]}
    assert q("be 100") is None


# ───────────────────────────── El asistente (sin base) ─────────────────────────────

def test_el_asistente_no_recibe_el_tipo_ni_en_editables():
    """La ficha de P trae el tipo y sus `editables` traen los tipos que le faltan a la persona: el modelo no recibe
    ninguno de los dos (diría si es líder)."""
    base = {"id": 7, "nombre": "PERSONA INVENTADA DEL ASISTENTE", "consentimiento": "si", "ocupacion": "Pescadora",
            "faltan": ["cedula", "lider", "lideres"]}
    lider = {**base, "lider": True, "votante": False, "concejal": False, "editables": ["nombre", "ocupacion",
                                                                                         "concejal", "votante"],
             "lideres": [{"id": 9, "nombre": "LIDER INVENTADO", "tipo": "lider", "marcado": True}]}
    nadie = {**base, "lider": False, "votante": False, "concejal": False, "lideres": [],
             "editables": ["nombre", "ocupacion", "concejal", "lider", "votante"]}
    salidas = [minimizar.ficha(d) for d in (lider, nadie)]
    for m in salidas:
        assert not TIPO_Y_LIDERES & set(m), m
        assert m["editables"] == ["nombre", "ocupacion"] and m["faltan"] == ["cedula"]
        assert "LIDER INVENTADO" not in json.dumps(m, ensure_ascii=False)
    assert salidas[0] == salidas[1]


# ───────────────────────────── API (MongoDB) ─────────────────────────────

def _lugares(db) -> tuple[int, int]:
    l1, l2 = [x["_id"] for x in db.lugares.find({}, {"_id": 1}).sort("_id", 1).limit(2)]
    return l1, l2


def _ultima(db, pid: int, accion: str) -> dict:
    return db.auditoria.find_one({"entidad_id": pid, "accion": accion}, sort=[("_id", -1)])


def _detalle(r) -> dict:
    return r.json()["detail"]


def test_planillero_registra_con_tipo_y_lider(sesion, como):
    db = sesion.app.state.db
    l1, _ = _lugares(db)
    lider = persona(db, nombre="LIDER INVENTADO DEL ALTA DE P", lider=True)
    # Con una zona asignada: lo que registra, aunque no tenga barrio, es suyo
    p = como("planillero", asignacion={"lugares": [l1], "areas": []})
    nombres = ("ANACLETA INVENTADA CONCEJAL", "BERNARDA INVENTADA LIDER", "CELESTINA INVENTADA VOTANTE")
    for t, nombre in zip(TIPOS, nombres):
        r = p.post("/api/personas", json={"nombre": nombre, t: True, "forzar": True})
        assert r.status_code == 201, r.text
        f = r.json()
        assert {k: f[k] for k in TIPOS} == {k: k == t for k in TIPOS} and f["lideres"] == []
        assert "procedencia" not in f and not {"traidas", "intervenciones", "historial"} & set(f)
        d = db.personas.find_one({"_id": f["id"]})
        assert d[t] is True and (d["procedencia"][t]["fuente"], d["procedencia"][t]["uid"]) == ("panel", p.uid)
        assert set(d["procedencia"]) & set(TIPOS) == {t}
    # Un votante con su líder; un «no» al registrar no quita nada ni da 403
    r = p.post("/api/personas", json={"nombre": "DOROTEA INVENTADA VOTANTE", "votante": True, "lider": False,
                                      "lideres": [lider], "forzar": True})
    assert r.status_code == 201, r.text
    f = r.json()
    sin_vedados_p(f, "alta de P")
    assert (f["votante"], f["lider"]) == (True, False)
    assert [(l["id"], l["nombre"], l["tipo"]) for l in f["lideres"]] == [
        (lider, "LIDER INVENTADO DEL ALTA DE P", "lider")]
    assert all(set(l) <= CLAVES_LIDER_P and "asignado_por" not in l for l in f["lideres"])
    d = db.personas.find_one({"_id": f["id"]})
    assert d["lideres"][0]["asignado_por_uid"] == p.uid and d["creado_por"]["uid"] == p.uid
    # La auditoría del alta dice qué campos se llenaron, no sus valores ni a qué líder
    a = _ultima(db, f["id"], "crear")
    assert {"votante", "lideres"} <= set(a["campos"])
    assert set(json.loads(a["detalle"])) <= {"fuente", "reunion_id"}
    # Lo que registró lo sigue viendo en su ficha (no tiene barrio: no es de su zona)
    g = p.get(f"/api/personas/{f['id']}").json()
    assert g["votante"] is True and [l["id"] for l in g["lideres"]] == [lider]
    # Solo líderes o concejales de la lista: el mismo 422, sin el nombre de la ficha
    no_lider = persona(db, nombre="PERSONA INVENTADA SIN MARCA DEL ALTA")
    for lid in (no_lider, 99999999):
        r = p.post("/api/personas", json={"nombre": "ERNESTINA INVENTADA VOTANTE", "lideres": [lid], "forzar": True})
        assert r.status_code == 422 and _detalle(r) == ELIJA, r.text
        assert "SIN MARCA" not in r.text


def test_planillero_completa_solo_sumando(sesion, como):
    db = sesion.app.state.db
    x = persona(db, nombre="PERSONA INVENTADA PARA COMPLETAR", votante=True)
    p = como("planillero")
    # Completar ignora un «no» (o un vacío) y suma el «sí»
    r = p.patch(f"/api/personas/{x}?modo=completar", json={"votante": False, "concejal": None, "lider": True})
    assert r.status_code == 200, r.text
    f = r.json()
    assert (f["votante"], f["lider"], f["concejal"]) == (True, True, False)
    d = db.personas.find_one({"_id": x})
    assert (d["votante"], d["lider"], d["concejal"]) == (True, True, False)
    assert (d["procedencia"]["lider"]["fuente"], d["procedencia"]["lider"]["uid"]) == ("panel", p.uid)
    assert "votante" not in d["procedencia"]  # no la tocó
    assert "procedencia" not in f
    # La auditoría no dice qué tipo marcó
    a = _ultima(db, x, "editar")
    assert json.loads(a["detalle"])["lider"] == "(oculto)" and "lider" in a["campos"]
    # Sin nada nuevo, nada cambia
    n = db.auditoria.count_documents({"entidad_id": x, "accion": "editar"})
    assert p.patch(f"/api/personas/{x}?modo=completar", json={"lider": True, "votante": False}).status_code == 200
    assert db.auditoria.count_documents({"entidad_id": x, "accion": "editar"}) == n


def test_planillero_marca_en_la_ficha_pero_nunca_quita(sesion, como):
    db = sesion.app.state.db
    x = persona(db, nombre="PERSONA INVENTADA LIDER DE LA FICHA", lider=True, ocupacion="Pescadora")
    y = persona(db, nombre="PERSONA INVENTADA SIN TIPO DE LA FICHA")
    p = como("planillero")
    r = p.patch(f"/api/personas/{x}", json={"votante": True})
    assert r.status_code == 200 and (r.json()["votante"], r.json()["lider"]) == (True, True), r.text
    assert p.patch(f"/api/personas/{x}", json={"lider": True}).status_code == 200  # ya lo tenía: nada cambia
    # Un «no» (o un vacío) es 403 siempre, lo tenga o no la persona: la respuesta no dice si es líder
    detalles = []
    for pid in (x, y):
        for t in TIPOS:
            for v in (False, None):
                r = p.patch(f"/api/personas/{pid}", json={t: v})
                assert r.status_code == 403, r.text
                d = _detalle(r)
                assert (d["codigo"], d["campo"]) == ("permiso", t) and "solo marca" in d["mensaje"]
                detalles.append((pid, t, v, json.dumps(d, sort_keys=True)))
    for t in TIPOS:
        assert len({d for pid, tt, v, d in detalles if tt == t}) == 1
    # Antes de escribir nada: lo demás del mismo cuerpo tampoco se guarda
    r = p.patch(f"/api/personas/{x}", json={"ocupacion": "Docente", "lider": False})
    assert r.status_code == 403
    assert db.personas.find_one({"_id": x})["ocupacion"] == "Pescadora"
    tipos = lambda pid: {t: db.personas.find_one({"_id": pid})[t] for t in TIPOS}  # noqa: E731
    assert tipos(x) == {"concejal": False, "lider": True, "votante": True}
    assert tipos(y) == {"concejal": False, "lider": False, "votante": False}
    # El tipo no se compara con `base`: un 409 «cambiada» nunca diría si es concejal o líder
    r = p.patch(f"/api/personas/{x}", json={"concejal": True, "base": {"concejal": True, "lider": False}})
    assert r.status_code == 200, r.text
    assert db.personas.find_one({"_id": x})["concejal"] is True
    # A y K sí lo quitan
    k = coordinador(sesion.app, db)
    assert k.patch(f"/api/personas/{x}", json={"concejal": False}).status_code == 200
    assert sesion.patch(f"/api/personas/{x}", json={"votante": False}).status_code == 200
    assert tipos(x) == {"concejal": False, "lider": True, "votante": False}


def test_zona_del_planillero(sesion, como):
    db = sesion.app.state.db
    l1, l2 = _lugares(db)
    lid = persona(db, nombre="LIDER INVENTADA DE LA ZONA", lider=True)
    otro = persona(db, nombre="LIDER INVENTADO DE OTRA ZONA", concejal=True)
    lideres = [{"id": lid, "asignado_en": "2026-11-20", "asignado_por": "admin", "asignado_por_uid": 0}]
    dentro = persona(db, nombre="PERSONA INVENTADA DENTRO", lugar_id=l1, lider=True, lideres=lideres)
    fuera = persona(db, nombre="PERSONA INVENTADA FUERA", lugar_id=l2, votante=True, lideres=lideres,
                    lideres_quitados=[otro])
    fuera_sin = persona(db, nombre="PERSONA INVENTADA FUERA SIN TIPO", lugar_id=l2)
    p = como("planillero", asignacion={"lugares": [l1], "areas": []})
    # De su zona: el tipo, los tipos que le faltan en `editables` y el «Liderado por» sin quién lo asignó
    f = p.get(f"/api/personas/{dentro}").json()
    sin_vedados_p(f, "ficha de P dentro")
    assert (f["lider"], f["votante"], f["concejal"]) == (True, False, False)
    assert [t for t in f["editables"] if t in TIPOS] == ["concejal", "votante"]
    assert [l["id"] for l in f["lideres"]] == [lid] and set(f["lideres"][0]) <= CLAVES_LIDER_P
    assert "asignado_por" not in f["lideres"][0] and f["lideres"][0]["marcado"] is True
    # De otra zona: la ficha se abre (como siempre), pero sin el tipo ni el «Liderado por»
    for pid in (fuera, fuera_sin):
        g = p.get(f"/api/personas/{pid}")
        assert g.status_code == 200
        sin_vedados(g.json(), "ficha de P fuera")
        assert not TIPO_Y_LIDERES & set(g.json()) and not set(TIPOS) & set(g.json()["editables"])
    # Marcar o asignar fuera de su zona: 403 `fuera_de_zona`, el mismo lo tenga o no; nada cambia
    esperado = {"mensaje": api_personas.FUERA_DE_ZONA, "codigo": "fuera_de_zona"}
    for modo in ("", "?modo=completar"):
        respuestas = [p.patch(f"/api/personas/{pid}{modo}", json={"votante": True}) for pid in (fuera, fuera_sin)]
        for r in respuestas:
            assert r.status_code == 403 and _detalle(r) == {**esperado, "campo": "votante"}, r.text
        assert _detalle(respuestas[0]) == _detalle(respuestas[1])
    # Asignar fuera de su zona: el mismo 403 aunque ya lo tenga (`lid`) o se lo hayan quitado (`otro`): no dice ninguna
    # de las dos cosas
    for pid in (fuera, fuera_sin):
        for l in (lid, otro):
            r = p.post(f"/api/personas/{pid}/lideres", json={"lider_id": l})
            assert r.status_code == 403 and _detalle(r) == {**esperado, "campo": "lider_id"}, r.text
    assert db.personas.find_one({"_id": fuera_sin})["votante"] is False
    assert [l["id"] for l in db.personas.find_one({"_id": fuera})["lideres"]] == [lid]
    assert db.personas.find_one({"_id": fuera_sin})["lideres"] == []
    # Las filas (Habitantes, la búsqueda) nunca traen el tipo, tampoco las de su zona
    sin_vedados(p.get("/api/personas", params={"q": "PERSONA INVENTADA"}).json(), "filas de P")
    sin_vedados(p.get("/api/buscar", params={"q": "PERSONA INVENTADA"}).json(), "búsqueda de P")
    # Lo demás de esa ficha sí lo completa, y la respuesta sigue sin el tipo
    r = p.patch(f"/api/personas/{fuera}", json={"ocupacion": "Docente"})
    assert r.status_code == 200 and r.json()["ocupacion"] == "Docente" and not TIPO_Y_LIDERES & set(r.json())
    # Dentro de su zona marca y asigna
    r = p.patch(f"/api/personas/{dentro}", json={"votante": True})
    assert r.status_code == 200 and r.json()["votante"] is True
    r = p.post(f"/api/personas/{dentro}/lideres", json={"lider_id": otro})
    assert r.status_code == 201 and [l["id"] for l in r.json()["lideres"]] == [lid, otro], r.text
    # Lo que registró él, sin barrio: marca y asigna aunque no sea de su zona
    r = p.post("/api/personas", json={"nombre": "PERSONA INVENTADA REGISTRADA SIN BARRIO", "forzar": True})
    assert r.status_code == 201, r.text
    nueva = r.json()["id"]
    assert TIPO_Y_LIDERES <= set(r.json())
    assert p.patch(f"/api/personas/{nueva}", json={"lider": True}).status_code == 200
    r = p.post(f"/api/personas/{nueva}/lideres", json={"lider_id": lid})
    assert r.status_code == 201 and [l["id"] for l in r.json()["lideres"]] == [lid]
    # Un planillero sin asignación: toda la base es su zona
    q = como("planillero")
    g = q.get(f"/api/personas/{fuera}").json()
    assert g["votante"] is True and [l["id"] for l in g["lideres"]] == [lid]


def test_planillero_asigna_lideres_pero_no_quita(sesion, como):
    db = sesion.app.state.db
    l1 = persona(db, nombre="LIDER INVENTADO QUE ASIGNA P", lider=True)
    c1 = persona(db, nombre="CONCEJAL INVENTADA QUE ASIGNA P", concejal=True)
    no_lider = persona(db, nombre="VOTANTE INVENTADA NO LIDER", votante=True)
    no_autorizo = persona(db, nombre="LIDER INVENTADO QUE NO AUTORIZO", lider=True, consentimiento="no")
    unido = persona(db, nombre="LIDER INVENTADO UNIDO", lider=True, fusionada_en=l1)
    x = persona(db, nombre="PERSONA INVENTADA QUE LIDERAN")
    p = como("planillero")
    r = p.post(f"/api/personas/{x}/lideres", json={"lider_id": l1})
    assert r.status_code == 201, r.text
    assert [(l["id"], l["tipo"], l["marcado"]) for l in r.json()["lideres"]] == [(l1, "lider", True)]
    assert all("asignado_por" not in l for l in r.json()["lideres"])
    d = db.personas.find_one({"_id": x})
    assert (d["lideres"][0]["asignado_por"], d["lideres"][0]["asignado_por_uid"]) == (p.usuario, p.uid)
    a = _ultima(db, x, "asignar_lider")
    assert json.loads(a["detalle"]) == {"lider_id": "(oculto)"} and a["campos"] == ["lideres"] and a["uid"] == p.uid
    # Repetir no cambia nada
    r = p.post(f"/api/personas/{x}/lideres", json={"lider_id": l1})
    assert r.status_code == 201 and len(r.json()["lideres"]) == 1
    assert db.auditoria.count_documents({"entidad_id": x, "accion": "asignar_lider"}) == 1
    r = p.post(f"/api/personas/{x}/lideres", json={"lider_id": c1})
    assert r.status_code == 201
    assert [(l["id"], l["tipo"]) for l in r.json()["lideres"]] == [(l1, "lider"), (c1, "concejal")]
    # Un id que no es un líder de la lista (no marcado, no autorizó, unido, inexistente): el mismo 422, sin el nombre
    for lid in (no_lider, no_autorizo, unido, 99999999):
        r = p.post(f"/api/personas/{x}/lideres", json={"lider_id": lid})
        assert r.status_code == 422 and _detalle(r) == ELIJA, (lid, r.text)
        assert "INVENTAD" not in r.text
    r = p.post(f"/api/personas/{l1}/lideres", json={"lider_id": l1})
    assert r.status_code == 422 and "propio líder" in _detalle(r)["mensaje"]
    # A sigue recibiendo el motivo
    r = sesion.post(f"/api/personas/{x}/lideres", json={"lider_id": no_lider})
    assert r.status_code == 422 and "VOTANTE INVENTADA NO LIDER" in _detalle(r)["mensaje"]
    # Quitar es de A y K; lo que quitaron, P no lo devuelve (ellos sí)
    assert p.delete(f"/api/personas/{x}/lideres/{l1}").status_code == 403
    k = coordinador(sesion.app, db)
    assert k.delete(f"/api/personas/{x}/lideres/{l1}").status_code == 200
    assert db.personas.find_one({"_id": x})["lideres_quitados"] == [l1]
    r = p.post(f"/api/personas/{x}/lideres", json={"lider_id": l1})
    assert r.status_code == 409 and _detalle(r) == {
        "mensaje": "El administrador o el coordinador le quitó ese líder a esta persona: pídales que lo vuelvan a "
                   "asignar", "codigo": "lider_quitado", "campo": "lider_id"}, r.text
    d = db.personas.find_one({"_id": x})
    assert [l["id"] for l in d["lideres"]] == [c1] and d["lideres_quitados"] == [l1]
    assert k.post(f"/api/personas/{x}/lideres", json={"lider_id": l1}).status_code == 201
    assert db.personas.find_one({"_id": x})["lideres_quitados"] == []
    assert p.post(f"/api/personas/{x}/lideres", json={"lider_id": l1}).status_code == 201  # ya lo tiene
    # La lista general con sus conteos y los filtros por líder: solo A y K
    assert p.get("/api/lideres").status_code == 403
    for filtro in ({"lider_id": l1}, {"varios_lideres": 1}, {"sin_lider": 1}, {"tipo": "votante"}):
        assert p.get("/api/personas", params=filtro).status_code == 403, filtro
    # Su ficha: el «Liderado por» sin quién asignó, sin a quiénes lidera
    f = p.get(f"/api/personas/{x}").json()
    sin_vedados_p(f, "ficha de P")
    assert [l["id"] for l in f["lideres"]] == [c1, l1]
    assert not {"traidas", "lideres_quitados", "intervenciones"} & set(p.get(f"/api/personas/{l1}").json())


def test_candidatos_por_nombre_o_cedula_completa(sesion, como):
    db = sesion.app.state.db
    l1, l2 = _lugares(db)
    lugar = db.lugares.find_one({"_id": l1})["nombre"]
    berta = persona(db, nombre="BERTA INVENTADA CONCEJAL", concejal=True, cedula="1000000002", lugar_id=l1)
    bernardo = persona(db, nombre="BERNARDO INVENTADO LIDER", lider=True, cedula="1000000003",
                       cedulas_anteriores=["1000000099"])
    persona(db, nombre="BERNARDA INVENTADA VOTANTE", votante=True, cedula="1000000004")
    berenice = persona(db, nombre="BERENICE INVENTADA SIN AUTORIZAR", lider=True, cedula="1000000005",
                       consentimiento="no")
    persona(db, nombre="BERTO INVENTADO UNIDO", lider=True, fusionada_en=berta)
    # Un planillero de otra zona: los candidatos son de toda la campaña
    p = como("planillero", asignacion={"lugares": [l2], "areas": []})

    def ids(c, q):
        r = c.get("/api/lideres/candidatos", params={"q": q})
        assert r.status_code == 200, r.text
        return [l["id"] for l in r.json()["lideres"]]

    r = p.get("/api/lideres/candidatos", params={"q": "ber"})
    assert r.status_code == 200, r.text
    ls = r.json()["lideres"]
    # Solo líderes y concejales activos que autorizaron, por nombre; sin conteos ni la cédula completa
    assert [l["id"] for l in ls] == [bernardo, berta]
    assert all(set(l) == {"id", "nombre", "tipo", "lugar", "cedula_ult3"} for l in ls)
    assert ls[1] == {"id": berta, "nombre": "BERTA INVENTADA CONCEJAL", "tipo": "concejal", "lugar": lugar,
                     "cedula_ult3": "···002"}
    assert ls[0]["tipo"] == "lider" and "1000000003" not in r.text
    assert ids(p, "Bérta inventada") == [berta] and ids(p, "berta 1000") == [berta]
    # Por cédula, solo la completa (la actual o una anterior); nunca por el comienzo del número
    assert ids(p, "1000000002") == [berta] and ids(p, "1.000.000.002") == [berta]
    assert ids(p, "1000000099") == [bernardo]
    for nada in ("100000000", "1000", "10000000020", "be", "", "1000000004"):
        assert ids(p, nada) == [], nada
    # Quien no autorizó: P no lo encuentra; A sí (su ficha la ve igual)
    assert ids(p, "berenice") == [] and ids(p, "1000000005") == []
    assert ids(sesion, "berenice") == [berenice]
    assert set(sesion.get("/api/lideres/candidatos", params={"q": "berenice"}).json()["lideres"][0]) == CLAVES_CANDIDATO
    # Cuenta en el presupuesto diario de P
    assert db.lecturas.find_one({"uid": p.uid, "pid": berta, "ficha": False})
    # Como mucho 12, por nombre
    serie = [persona(db, nombre=f"LIDER INVENTADO SERIE {letra}", lider=True) for letra in "ABCDEFGHIJKLM"]
    assert ids(p, "serie") == serie[:12]
    # C: nada
    c = como("consultor")
    r = c.get("/api/lideres/candidatos", params={"q": "berta"})
    assert r.status_code == 403 and _detalle(r)["codigo"] == "permiso"


def test_consultor_no_ve_ni_marca_el_tipo(sesion, como):
    db = sesion.app.state.db
    lid = persona(db, nombre="LIDER INVENTADO DEL CONSULTOR", lider=True)
    x = contactable(db, "PERSONA INVENTADA DEL CONSULTOR", "3001239876", votante=True, lider=True,
                    lideres=[{"id": lid, "asignado_en": "2026-11-20", "asignado_por": "admin"}])
    c = como("consultor")
    tomar(c, x)
    f = c.get(f"/api/personas/{x}").json()
    sin_vedados(f, "ficha de C")
    assert not TIPO_Y_LIDERES & set(f)
    assert not set(TIPOS) & set(f.get("editables") or []) and not set(TIPOS) & set(f.get("faltan") or [])
    for r in (c.patch(f"/api/personas/{x}", json={"votante": True}),
              c.patch(f"/api/personas/{x}?modo=completar", json={"concejal": True}),
              c.post(f"/api/personas/{x}/lideres", json={"lider_id": lid}),
              c.delete(f"/api/personas/{x}/lideres/{lid}"),
              c.get("/api/lideres"), c.get("/api/lideres/candidatos", params={"q": "lider inventado"}),
              c.post("/api/personas", json={"nombre": "PERSONA INVENTADA DEL CONSULTOR NUEVA", "lider": True,
                                            "forzar": True})):
        assert r.status_code == 403 and _detalle(r)["codigo"] == "permiso", (r.request.url, r.text)
    d = db.personas.find_one({"_id": x})
    assert (d["votante"], d["lider"], d["concejal"]) == (True, True, False) and len(d["lideres"]) == 1


def test_quien_no_autorizo_no_se_marca_ni_se_lidera(sesion, como):
    db = sesion.app.state.db
    lid = persona(db, nombre="LIDER INVENTADO DE QUIEN NO AUTORIZO", lider=True)
    x = persona(db, nombre="PERSONA INVENTADA QUE NO AUTORIZO", lider=True, consentimiento="no")
    p = como("planillero")
    for r in (p.patch(f"/api/personas/{x}", json={"votante": True}),
              p.patch(f"/api/personas/{x}?modo=completar", json={"concejal": True}),
              p.post(f"/api/personas/{x}/lideres", json={"lider_id": lid})):
        assert r.status_code == 409 and _detalle(r)["codigo"] == "no_contactable", r.text
    # La ficha mínima de siempre: sin el tipo
    f = p.get(f"/api/personas/{x}").json()
    assert set(f) == proyeccion.CAMPOS_NO_AUTORIZO
    d = db.personas.find_one({"_id": x})
    assert (d["votante"], d["concejal"], d["lideres"]) == (False, False, [])


def test_marcar_un_tipo_no_es_una_correccion(sesion, como):
    db = sesion.app.state.db
    x = persona(db, nombre="PERSONA INVENTADA DE LOS INDICADORES", ocupacion="Pescadora")
    y = persona(db, nombre="OTRA PERSONA INVENTADA DE LOS INDICADORES")
    p = como("planillero")
    # Un tipo y una corrección de verdad en el mismo cambio; otro tipo al completar
    assert p.patch(f"/api/personas/{x}", json={"votante": True, "ocupacion": "Docente"}).status_code == 200
    assert p.patch(f"/api/personas/{y}?modo=completar", json={"lider": True}).status_code == 200
    a = _ultima(db, x, "editar")
    assert set(a["campos"]) == {"ocupacion", "votante"}
    pl = p.get("/api/yo/indicadores").json()["planillero"]
    assert pl["correcciones"] == 1  # la ocupación; el tipo no corrige nada
    assert pl["actualizadas"] == 2
    assert sesion.get(f"/api/usuarios/{p.uid}/indicadores").json()["planillero"]["correcciones"] == 1


def test_moverla_a_su_zona_no_le_da_el_tipo(sesion, como):
    """P le cambia el barrio, la dirección o la ubicación a cualquier persona, como siempre; pero si no era de su zona,
    moverla no se la vuelve de su zona (`reubicada_por`): si no, la traería, leería su tipo y su «Liderado por», los
    marcaría y la devolvería. Ni la respuesta de ese cambio trae el tipo."""
    db = sesion.app.state.db
    l1, l2 = _lugares(db)
    lid = persona(db, nombre="LIDER INVENTADO DE LA MUDANZA", lider=True)
    lideres = [{"id": lid, "asignado_en": "2026-11-20", "asignado_por": "admin", "asignado_por_uid": 0}]
    x = persona(db, nombre="PERSONA INVENTADA QUE MUDAN", lugar_id=l2, concejal=True, lideres=lideres)
    y, z, w, quieta = (persona(db, nombre=f"PERSONA INVENTADA FUERA {n}", lugar_id=l2)
                       for n in ("QUE UBICAN", "QUE VUELVE A LO AUTOMATICO", "DE OTRA DIRECCION", "QUE NO MUEVEN"))
    dentro = persona(db, nombre="PERSONA INVENTADA QUE YA ERA DE SU ZONA", lugar_id=l1, votante=True)
    zona = {"lugares": [l1], "areas": []}
    p = como("planillero", asignacion=zona)
    assert not TIPO_Y_LIDERES & set(p.get(f"/api/personas/{x}").json())
    # Pasarla a su barrio se guarda, pero ni la respuesta ni la ficha después traen el tipo
    r = p.patch(f"/api/personas/{x}", json={"lugar_id": l1})
    assert r.status_code == 200 and r.json()["lugar_id"] == l1, r.text
    assert not TIPO_Y_LIDERES & set(r.json()) and "LIDER INVENTADO" not in r.text
    d = db.personas.find_one({"_id": x})
    assert d["lugar_id"] == l1 and d["reubicada_por"] == [p.uid]
    f = p.get(f"/api/personas/{x}").json()
    assert not TIPO_Y_LIDERES & set(f) and not set(TIPOS) & set(f["editables"])
    # Ni marca ni asigna: el mismo 403 de fuera de su zona
    for r in (p.patch(f"/api/personas/{x}", json={"votante": True}),
              p.patch(f"/api/personas/{x}?modo=completar", json={"votante": True}),
              p.post(f"/api/personas/{x}/lideres", json={"lider_id": lid})):
        assert r.status_code == 403 and _detalle(r)["codigo"] == "fuera_de_zona", r.text
    # Otro planillero de ese barrio, que no la movió, la ve: para él es de su zona
    q = como("planillero", asignacion=zona)
    g = q.get(f"/api/personas/{x}").json()
    assert g["concejal"] is True and [l["id"] for l in g["lideres"]] == [lid]
    # Devolverla tampoco la muestra; queda anotado una sola vez
    r = p.patch(f"/api/personas/{x}", json={"lugar_id": l2})
    assert r.status_code == 200 and not TIPO_Y_LIDERES & set(r.json())
    assert db.personas.find_one({"_id": x})["reubicada_por"] == [p.uid]
    # Ubicarla en el mapa, volver a la ubicación automática o cambiarle la dirección (de ella sale el punto): igual
    r = p.put(f"/api/personas/{y}/ubicacion", json={"lat": 7.0, "lon": -74.0})
    assert r.status_code == 200 and not TIPO_Y_LIDERES & set(r.json()), r.text
    assert p.delete(f"/api/personas/{z}/ubicacion").status_code == 200
    assert p.patch(f"/api/personas/{w}", json={"direccion": "CL 10 # 20-30"}).status_code == 200
    for pid in (y, z, w):
        assert db.personas.find_one({"_id": pid})["reubicada_por"] == [p.uid], pid
    # Lo demás no anota nada
    assert p.patch(f"/api/personas/{quieta}", json={"ocupacion": "Docente"}).status_code == 200
    assert "reubicada_por" not in db.personas.find_one({"_id": quieta})
    # En una de su zona o en una que registró, cambiar la ubicación o el barrio no le quita nada
    r = p.put(f"/api/personas/{dentro}/ubicacion", json={"lat": 7.0, "lon": -74.0})
    assert r.status_code == 200 and r.json()["votante"] is True
    r = p.post("/api/personas", json={"nombre": "PERSONA INVENTADA QUE REGISTRA Y MUDA", "forzar": True})
    nueva = r.json()["id"]
    r = p.patch(f"/api/personas/{nueva}", json={"lugar_id": l2})
    assert r.status_code == 200 and TIPO_Y_LIDERES <= set(r.json())
    for pid in (dentro, nueva):
        assert "reubicada_por" not in db.personas.find_one({"_id": pid}), pid
    # A y K, como siempre (y no borran la anotación: P la movió)
    k = coordinador(sesion.app, db)
    assert k.patch(f"/api/personas/{x}", json={"lugar_id": l1}).status_code == 200
    assert db.personas.find_one({"_id": x})["reubicada_por"] == [p.uid]
    assert sesion.get(f"/api/personas/{x}").json()["concejal"] is True
    assert not TIPO_Y_LIDERES & set(p.get(f"/api/personas/{x}").json())
    # Nadie recibe la anotación
    for c in (p, q, k, sesion):
        assert "reubicada_por" not in c.get(f"/api/personas/{x}").json()


def test_el_lider_que_no_autorizo_no_sale_en_la_ficha_de_p(sesion, como):
    """Para P, quien no autorizó es la ficha mínima, sin tipo: tampoco sale en el «Liderado por» de otra persona (diría
    que lidera), ni una asignación repetida dice que lo tiene."""
    db = sesion.app.state.db
    lid = persona(db, nombre="LIDER INVENTADO QUE SI AUTORIZO", lider=True)
    no = persona(db, nombre="LIDER INVENTADO QUE NO AUTORIZO", lider=True, consentimiento="no")
    lideres = [{"id": l, "asignado_en": "2026-11-20", "asignado_por": "admin", "asignado_por_uid": 0} for l in (no, lid)]
    x = persona(db, nombre="PERSONA INVENTADA LIDERADA POR QUIEN NO AUTORIZO", lideres=lideres)
    p = como("planillero")
    for r in (p.get(f"/api/personas/{x}"), p.patch(f"/api/personas/{x}", json={"ocupacion": "Docente"})):
        assert r.status_code == 200, r.text
        assert [l["id"] for l in r.json()["lideres"]] == [lid] and "QUE NO AUTORIZO" not in r.text
    assert set(p.get(f"/api/personas/{no}").json()) == proyeccion.CAMPOS_NO_AUTORIZO
    # Asignarlo otra vez: el 422 genérico, como a cualquier id que no es un líder de la lista; nada cambia
    r = p.post(f"/api/personas/{x}/lideres", json={"lider_id": no})
    assert r.status_code == 422 and _detalle(r) == ELIJA, r.text
    assert [l["id"] for l in db.personas.find_one({"_id": x})["lideres"]] == [no, lid]
    # A y K lo ven y lo repiten sin daño
    assert [l["id"] for l in sesion.get(f"/api/personas/{x}").json()["lideres"]] == [no, lid]
    r = sesion.post(f"/api/personas/{x}/lideres", json={"lider_id": no})
    assert r.status_code == 201 and [l["id"] for l in r.json()["lideres"]] == [no, lid]


def test_el_422_del_lider_no_dice_gratis_si_un_id_es_lider(sesion, como):
    """Lo que no depende del líder se revisa antes que él: un alta o una asignación que no sigue responde lo mismo sea
    o no un líder el id (no hay un «sí» sin costo para recorrer los ids), y el líder que sí se guarda sale con su nombre
    y cuenta como lectura en el presupuesto diario de P."""
    db = sesion.app.state.db
    lid = persona(db, nombre="LIDER INVENTADO DEL ORACULO", lider=True)
    no_lider = persona(db, nombre="PERSONA INVENTADA SIN MARCA DEL ORACULO")
    r = sesion.post("/api/personas", json={"nombre": "HERMINIA INVENTADA EXISTENTE", "telefono": "3001112233",
                                           "forzar": True})
    assert r.status_code == 201, r.text
    p = como("planillero")
    n = db.personas.count_documents({})
    # Con parecidas: el 409 para todo id
    for x in (lid, no_lider, 99999999):
        r = p.post("/api/personas", json={"nombre": "HERMINIA INVENTADA EXISTENTE", "telefono": "3001112233",
                                          "lideres": [x]})
        assert r.status_code == 409 and _detalle(r)["codigo"] == "parecidas", (x, r.text)
    # Con una etiqueta que su rol no usa: el 403 para todo id
    sensible = sorted(proyeccion.etiquetas_sensibles(db))[0]
    for x in (lid, no_lider):
        r = p.post("/api/personas", json={"nombre": "IRMA INVENTADA DEL ORACULO", "etiquetas": [sensible],
                                          "lideres": [x], "forzar": True})
        assert r.status_code == 403 and _detalle(r)["campo"] == "etiquetas", (x, r.text)
    assert db.personas.count_documents({}) == n
    assert db.lecturas.find_one({"uid": p.uid, "pid": lid}) is None
    # El que pasa todo: el alta se hace y el líder cuenta como leído
    r = p.post("/api/personas", json={"nombre": "IRMA INVENTADA DEL ORACULO", "lideres": [lid], "forzar": True})
    assert r.status_code == 201 and [l["id"] for l in r.json()["lideres"]] == [lid], r.text
    assert db.lecturas.find_one({"uid": p.uid, "pid": lid})
    # Al tope de líderes, el mismo 422 para todo id
    diez = [persona(db, nombre=f"LIDER INVENTADO DEL TOPE {i}", lider=True) for i in range(10)]
    x = persona(db, nombre="PERSONA INVENTADA CON DIEZ LIDERES",
                lideres=[{"id": l, "asignado_en": "2026-11-20", "asignado_por": "admin"} for l in diez])
    for l in (lid, no_lider, 99999999):
        r = p.post(f"/api/personas/{x}/lideres", json={"lider_id": l})
        assert r.status_code == 422 and "hasta 10 líderes" in r.text, (l, r.text)
    # Asignar uno también cuenta como lectura
    y = persona(db, nombre="PERSONA INVENTADA DE LA LECTURA AL ASIGNAR")
    otro = persona(db, nombre="LIDER INVENTADO LEIDO AL ASIGNAR", lider=True)
    assert db.lecturas.find_one({"uid": p.uid, "pid": otro}) is None
    assert p.post(f"/api/personas/{y}/lideres", json={"lider_id": otro}).status_code == 201
    assert db.lecturas.find_one({"uid": p.uid, "pid": otro})


def test_sin_los_permisos_nuevos_el_planillero_no_marca_ni_asigna(sesion, como, monkeypatch):
    """Un planillero sin `personas.tipo` ni `lideres.asignar` (los permisos se leen en cada petición): 403 con el campo
    al registrar, al editar y al completar, 403 al asignar y al buscar candidatos, y sus fichas sin el tipo."""
    db = sesion.app.state.db
    lid = persona(db, nombre="LIDER INVENTADO SIN PERMISOS", lider=True)
    x = persona(db, nombre="PERSONA INVENTADA SIN PERMISOS", lider=True)
    p = como("planillero")
    monkeypatch.setitem(acceso.PERMISOS, "planillero",
                        acceso.PERMISOS["planillero"] - {"personas.tipo", "lideres.asignar"})
    n = db.personas.count_documents({})
    for r, campo in ((p.post("/api/personas", json={"nombre": "PERSONA INVENTADA NUEVA CON TIPO", "votante": True,
                                                    "forzar": True}), "votante"),
                     (p.post("/api/personas", json={"nombre": "PERSONA INVENTADA NUEVA CON LIDER", "lideres": [lid],
                                                    "forzar": True}), "lideres"),
                     (p.patch(f"/api/personas/{x}", json={"votante": True}), "votante"),
                     (p.patch(f"/api/personas/{x}?modo=completar", json={"concejal": True}), "concejal")):
        d = _detalle(r)
        assert r.status_code == 403 and (d["codigo"], d["campo"]) == ("permiso", campo), r.text
        assert d["mensaje"] == f"Su rol no puede cambiar «{campo}»"
    for r in (p.post(f"/api/personas/{x}/lideres", json={"lider_id": lid}),
              p.get("/api/lideres/candidatos", params={"q": "lider inventado"})):
        assert r.status_code == 403 and _detalle(r)["codigo"] == "permiso", r.text
    assert db.personas.count_documents({}) == n
    d = db.personas.find_one({"_id": x})
    assert (d["votante"], d["concejal"], d["lideres"]) == (False, False, [])
    # Ni en la de otra persona ni en la que registra: sin el tipo ni el «Liderado por»
    assert not TIPO_Y_LIDERES & set(p.get(f"/api/personas/{x}").json())
    r = p.post("/api/personas", json={"nombre": "PERSONA INVENTADA NUEVA SIN PERMISOS", "forzar": True})
    assert r.status_code == 201 and not TIPO_Y_LIDERES & set(r.json()), r.text
