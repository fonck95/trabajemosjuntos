"""Indicadores por usuario (5.1) y avance por zona (5.3): conteos sobre la auditoría, `capturado_por` de las
planillas, las asistencias que no inflan «actualizadas», vaciar y volver a llenar que no suma, creadas netas, la serie
que no suma al total, los acercamientos del consultor y los porcentajes por zona. Solo datos inventados."""
from datetime import datetime, time, timedelta, timezone

from app import acceso, modelo
from app import db as bd
from conftest import CASCO, crear_usuario, insertar_personas


def _q(c, rol):
    return acceso.Quien(uid=c.uid, usuario=c.usuario, rol=rol, ip="10.0.0.9", permisos=acceso.PERMISOS[rol])


def _ts(dias_atras: int, hora: int = 12) -> str:
    """Un instante de hace `dias_atras` días a esa hora de Colombia, como texto ISO UTC."""
    d = modelo.hoy_local() - timedelta(days=dias_atras)
    return datetime.combine(d, time(hora), tzinfo=modelo.ZONA).astimezone(timezone.utc).isoformat()


def _escenario(sesion, como):
    db = sesion.app.state.db
    p, k = como("planillero"), como("consultor")
    otro = crear_usuario(db, "planillero")
    P, K = _q(p, "planillero"), _q(k, "consultor")
    Q = acceso.Quien(uid=otro["_id"], usuario=otro["usuario"], rol="planillero")
    A = acceso.Quien(uid=0, usuario="admin", rol="admin")
    ids = insertar_personas(db, [{"nombre": f"PERSONA INVENTADA {i}"} for i in range(1, 7)])
    p1, p2, p3, p4, p5, p6 = ids
    db.personas.update_one({"_id": p2}, {"$set": {"fusionada_en": p1}})  # p2 era un duplicado
    db.personas.update_one({"_id": p1}, {"$set": {"telefonos": [
        {"numero": "3001110001", "agregado_por": p.uid, "estado": "equivocado"},
        {"numero": "3001110002", "agregado_por": p.uid, "estado": "confirmado"},
        {"numero": "3001110003", "agregado_por": otro["_id"], "estado": "inexistente"}]}})
    au = bd.auditar
    au(db, P, "crear", "persona", p1, campos=["nombre", "cedula", "telefono"], completados=["cedula", "telefono"])
    au(db, P, "crear", "persona", p2, campos=["nombre"], completados=[])
    au(db, A, "crear", "persona", p3, campos=["nombre", "telefono"], completados=["telefono"], capturado_por=p.uid)
    au(db, P, "editar", "persona", p1, campos=["sexo"], completados=["sexo"])
    au(db, P, "editar", "persona", p1, campos=["cedula"], completados=[])  # la vació A y P la volvió a llenar
    au(db, P, "telefono_agregar", "persona", p1, campos=["telefono"], completados=[])
    au(db, P, "autorizacion", "persona", p2, campos=["autorizacion"], completados=["autorizacion"], estado="si")
    au(db, P, "autorizacion", "persona", p3, campos=["autorizacion"], completados=[], estado="no")
    au(db, P, "asistencia", "persona", p4, campos=["reunion"], completados=[])
    au(db, P, "ubicar", "persona", p5, campos=["ubicacion"], completados=["ubicacion"])
    au(db, Q, "editar", "persona", p6, campos=["sexo"], completados=["sexo"])
    au(db, P, "alerta_volumen", "usuario", p.uid, {"tope": 1})
    db.auditoria.insert_many([
        {"ts": _ts(1), "usuario": p.usuario, "uid": p.uid, "rol": "planillero", "accion": "editar", "entidad": "persona",
         "entidad_id": p1, "campos": ["sexo"], "completados": []},  # ayer
        {"ts": _ts(90), "usuario": p.usuario, "uid": p.uid, "rol": "planillero", "accion": "crear", "entidad": "persona",
         "entidad_id": p6, "campos": ["nombre"], "completados": ["cedula"]},  # fuera del periodo
    ])
    acceso.registrar_lecturas(db, P, [p1, p2], ficha=True)
    acceso.registrar_lecturas(db, P, [p3, p4, p5])

    def acercamiento(uid, pid, canal, resultado, ts=None, **extra):
        return {"persona_id": pid, "ts": ts or bd.ahora(), "uid": uid, "rol": "consultor", "canal": canal,
                "resultado": resultado, "efectivo": resultado in modelo.EFECTIVOS, "anulado": False, **extra}
    db.acercamientos.insert_many([
        acercamiento(k.uid, p1, "llamada", "no_contesto"),
        acercamiento(k.uid, p1, "llamada", "contesto", autorizacion_id=5, datos_dictados=["cedula"], fuera_de_horario=True),
        acercamiento(k.uid, p2, "whatsapp", "no_contactar"),
        acercamiento(k.uid, p3, "llamada", "contesto", anulado=True),
        acercamiento(k.uid, p4, "llamada", "buzon", suprimido=True, nota=None),  # anonimizado: se sigue contando
        acercamiento(otro["_id"], p5, "visita", "contesto"),
        acercamiento(k.uid, p5, "llamada", "contesto", ts=_ts(60)),
    ])
    return db, p, k, otro, ids


def test_conteos_del_planillero(sesion, como):
    db, p, k, otro, (p1, p2, p3, p4, p5, p6) = _escenario(sesion, como)
    ind = sesion.get(f"/api/usuarios/{p.uid}/indicadores").json()
    pl = ind["planillero"]
    assert (ind["uid"], ind["rol"], ind["agrupar"]) == (p.uid, "planillero", "dia")
    assert (pl["creadas"], pl["creadas_por_planilla"], pl["creadas_netas"]) == (3, 1, 2)
    assert pl["calidad"] == {"telefonos_luego_equivocados": 1, "cedulas_en_conflicto": 0, "duplicados_unidos": 1}
    # p1 (editar, teléfono), p2 y p3 (autorización), p5 (ubicar); la asistencia de p4 no cuenta
    assert pl["actualizadas"] == 4
    assert pl["con_datos_nuevos"] == 4
    assert pl["correcciones"] == 2  # la cédula que se volvió a llenar y el sexo que se cambió ayer
    assert {c: n for c, n in pl["completados"].items() if n} == {"cedula": 1, "telefono": 2, "sexo": 1, "autorizacion": 1,
                                                                  "ubicacion": 1}
    assert set(pl["completados"]) >= set(modelo.CAMPOS_AVANCE)
    assert (pl["telefonos_agregados"], pl["asistencias"], pl["ubicadas"]) == (1, 1, 1)
    assert pl["autorizaciones"] == {"si": 1, "no": 1}
    assert (pl["fichas_vistas"], pl["personas_vistas"]) == (2, 5)
    # Lo propio, también desde «Mi cuenta»
    assert p.get("/api/yo/indicadores").json()["planillero"] == pl


def test_serie_por_dia_no_suma_al_total(sesion, como):
    db, p, *_ = _escenario(sesion, como)
    ind = sesion.get(f"/api/usuarios/{p.uid}/indicadores").json()
    serie = {s["fecha"]: s for s in ind["serie"]}
    hoy, ayer = modelo.hoy_local().isoformat(), (modelo.hoy_local() - timedelta(days=1)).isoformat()
    assert set(serie) == {hoy, ayer}
    assert (serie[hoy]["creadas"], serie[hoy]["actualizadas"]) == (3, 4)
    assert (serie[ayer]["creadas"], serie[ayer]["actualizadas"]) == (0, 1)
    # p1 cuenta en los dos días, pero una sola vez en el total
    assert sum(s["actualizadas"] for s in ind["serie"]) == 5 and ind["planillero"]["actualizadas"] == 4
    mes = sesion.get(f"/api/usuarios/{p.uid}/indicadores", params={"agrupar": "mes"}).json()
    assert sum(s["creadas"] for s in mes["serie"]) == 3 and all(len(s["fecha"]) == 7 for s in mes["serie"])
    semana = sesion.get(f"/api/usuarios/{p.uid}/indicadores", params={"agrupar": "semana"}).json()
    assert all("-S" in s["fecha"] for s in semana["serie"])
    # Solo hoy: lo de ayer no entra
    solo_hoy = sesion.get(f"/api/usuarios/{p.uid}/indicadores", params={"desde": hoy, "hasta": hoy}).json()
    assert [s["fecha"] for s in solo_hoy["serie"]] == [hoy]
    # El periodo de hace 90 días tiene la creada vieja (con su cédula)
    viejo = (modelo.hoy_local() - timedelta(days=90)).isoformat()
    r = sesion.get(f"/api/usuarios/{p.uid}/indicadores", params={"desde": viejo, "hasta": viejo}).json()
    assert r["planillero"]["creadas"] == 1 and r["planillero"]["completados"]["cedula"] == 1


def test_conteos_del_consultor(sesion, como):
    db, p, k, otro, ids = _escenario(sesion, como)
    co = sesion.get(f"/api/usuarios/{k.uid}/indicadores").json()["consultor"]
    assert (co["acercamientos"], co["personas"], co["contactadas"]) == (4, 3, 2)
    assert {c: n for c, n in co["por_canal"].items() if n} == {"llamada": 3, "whatsapp": 1}
    assert {r: n for r, n in co["por_resultado"].items() if n} == {"no_contesto": 1, "contesto": 1, "no_contactar": 1,
                                                                   "buzon": 1}
    assert (co["no_contactar"], co["autorizaciones_obtenidas"], co["cedulas_dictadas"], co["fuera_de_horario"]) == (1, 1, 1, 1)
    assert sum(s["acercamientos"] for s in sesion.get(f"/api/usuarios/{k.uid}/indicadores").json()["serie"]) == 4


def test_lista_y_totales(sesion, como):
    db, p, k, otro, ids = _escenario(sesion, como)
    filas = {u["id"]: u for u in sesion.get("/api/usuarios").json()}
    assert filas[p.uid]["indicadores"]["planillero"]["creadas"] == 3
    assert filas[k.uid]["indicadores"]["consultor"]["acercamientos"] == 4
    assert filas[otro["_id"]]["indicadores"]["planillero"]["actualizadas"] == 1
    assert filas[otro["_id"]]["indicadores"]["planillero"]["calidad"]["telefonos_luego_equivocados"] == 1
    t = sesion.get("/api/usuarios/indicadores").json()
    assert (t["totales"]["planilleros_activos"], t["totales"]["consultores_activos"]) == (2, 1)
    assert (t["totales"]["creadas"], t["totales"]["creadas_netas"], t["totales"]["cedulas"]) == (3, 2, 1)
    assert (t["totales"]["acercamientos"], t["totales"]["contactadas"]) == (5, 3)
    assert {u["uid"] for u in t["usuarios"]} == {p.uid, k.uid, otro["_id"]}
    # Periodos mal escritos
    assert sesion.get("/api/usuarios", params={"desde": "2026-11-31"}).status_code == 422
    assert sesion.get("/api/usuarios", params={"desde": "2026-11-05", "hasta": "2026-11-01"}).status_code == 422
    assert sesion.get(f"/api/usuarios/{p.uid}/indicadores", params={"agrupar": "hora"}).status_code == 422
    assert sesion.get("/api/usuarios/indicadores", params={"desde": "2001-01-01", "hasta": "2001-01-31"}).json()["totales"]["creadas"] == 0


def test_avance_por_zona(sesion, como):
    db = sesion.app.state.db
    l1, l2 = [x["_id"] for x in db.lugares.find({}, {"_id": 1}).sort("_id", 1).limit(2)]
    db.areas.insert_one({"_id": 1, "nombre": "Zona inventada", "poligono": [
        [CASCO[0] - 0.01, CASCO[1] - 0.01], [CASCO[0] + 0.01, CASCO[1] - 0.01], [CASCO[0] + 0.01, CASCO[1] + 0.01],
        [CASCO[0] - 0.01, CASCO[1] + 0.01]]})
    p = como("planillero", asignacion={"lugares": [l1], "areas": []})
    k = como("consultor", asignacion={"lugares": [l1, l2], "areas": [1]})
    dentro = {"lat": CASCO[1] + 0.001, "lon": CASCO[0] + 0.001}
    ids = insertar_personas(db, [
        {"nombre": "UNO INVENTADO", "lugar_id": l1, "cedula": "70000001", "telefono": "3150000001", **dentro},
        {"nombre": "DOS INVENTADO", "lugar_id": l1, "cedula": "70000002", "telefono": "3150000002",
         "puesto_votacion": "COLISEO BENITO ARIAS", "mesa": "2"},
        {"nombre": "TRES INVENTADO", "lugar_id": l1, "telefono": "3150000003", **dentro},
        {"nombre": "CUATRO INVENTADO", "lugar_id": l1},
        {"nombre": "FALLECIDA INVENTADA", "lugar_id": l1, "cedula": "70000005"},
        {"nombre": "SUPRIMIDA", "lugar_id": l1, "eliminado": True},
    ])
    db.personas.update_one({"_id": ids[2]}, {"$set": {"abordaje": {"estado": "contactado", "n": 1}}})
    db.personas.update_one({"_id": ids[4]}, {"$set": {"situacion": {"estado": "fallecida", "confirmada": False}}})
    r = sesion.get("/api/usuarios/avance", params={"por": "lugar"}).json()
    assert r["por"] == "lugar"
    filas = {f["id"]: f for f in r["filas"]}
    f1 = filas[l1]
    assert {x["usuario"] for x in f1["responsables"]} == {p.usuario, k.usuario}
    assert (f1["personas"], f1["pct_cedula"], f1["pct_puesto_mesa"], f1["pct_telefono"], f1["pct_contactadas"]) == (4, 50, 25, 75, 25)
    assert filas[l2]["personas"] == 0 and filas[l2]["pct_cedula"] == 0 and [x["usuario"] for x in filas[l2]["responsables"]] == [k.usuario]
    a = sesion.get("/api/usuarios/avance", params={"por": "area"}).json()["filas"]
    assert [(x["id"], x["nombre"], x["personas"], x["pct_contactadas"]) for x in a] == [(1, "Zona inventada", 2, 50)]
    # Un usuario inactivo no es responsable
    sesion.patch(f"/api/usuarios/{k.uid}", json={"activo": False})
    assert l2 not in {f["id"] for f in sesion.get("/api/usuarios/avance").json()["filas"]}
    assert sesion.get("/api/usuarios/avance", params={"por": "barrio"}).status_code == 422
