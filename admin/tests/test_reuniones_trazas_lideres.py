"""Reuniones con rango de tiempo, la traza de lo que se le hace a una persona durante una reunión (app/trazas.py) y
los líderes que traen a cada persona (app/api/lideres.py). Solo datos inventados.

Las pruebas de `modelo` y de `trazas` con una base de mentira corren sin MongoDB; las de la API, con MongoDB (como en
CI)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app import acceso, modelo, trazas
from ayudas_g3 import coordinador, persona, sin_vedados


# ───────────────────────────── Rango de tiempo (sin base) ─────────────────────────────

def test_hora_valida_normaliza_y_tolera_lo_viejo():
    assert modelo.hora_valida("9:30") == "09:30" and modelo.hora_valida(" 18:05 ") == "18:05"
    for mala in ("25:00", "9:60", "930", "", None, 9, "9:3"):
        assert modelo.hora_valida(mala) is None


def test_ventana_de_la_reunion_en_hora_de_colombia():
    r = {"fecha": "2026-11-18", "hora": "09:00", "hora_fin": "11:30"}
    inicio, fin = modelo.ventana_reunion(r)
    assert inicio.isoformat() == "2026-11-18T09:00:00-05:00" and fin.isoformat() == "2026-11-18T11:30:00-05:00"
    # Los cambios se guardan en UTC: 9:00 en Colombia son las 14:00 UTC
    assert modelo.durante_reunion(r, "2026-11-18T14:00:00+00:00")
    assert modelo.durante_reunion(r, "2026-11-18T16:30:00+00:00")  # el fin cuenta
    assert not modelo.durante_reunion(r, "2026-11-18T16:31:00+00:00")
    assert not modelo.durante_reunion(r, "2026-11-18T13:59:59+00:00")
    # Sin hora de fin (o con una que no es posterior): dura DURACION_REUNION
    for sin_fin in ({"fecha": "2026-11-18", "hora": "9:00"}, {"fecha": "2026-11-18", "hora": "09:00", "hora_fin": "08:00"},
                    {"fecha": "2026-11-18", "hora": "09:00", "hora_fin": "99:99"}):
        assert modelo.ventana_reunion(sin_fin)[1] - modelo.ventana_reunion(sin_fin)[0] == modelo.DURACION_REUNION
    # A la medianoche pasa al día siguiente
    assert modelo.ventana_reunion({"fecha": "2026-11-18", "hora": "23:00"})[1].date().isoformat() == "2026-11-19"
    # Sin hora de inicio (o con una fecha imposible) no hay rango
    for sin in ({"fecha": "2026-11-18"}, {"fecha": "2026-11-18", "hora": "25:00", "hora_fin": "11:00"},
                {"fecha": "2026-02-30", "hora": "09:00"}, {}, None):
        assert modelo.ventana_reunion(sin) is None
        assert not modelo.durante_reunion(sin, "2026-11-18T14:00:00+00:00")
    assert not modelo.durante_reunion(r, "no es una fecha")


# ───────────────────────────── La traza (base de mentira) ─────────────────────────────

class _Coleccion:
    def __init__(self, docs):
        self.docs = {d["_id"]: d for d in docs}

    @staticmethod
    def _cumple(d, q):
        for k, v in (q or {}).items():
            if isinstance(v, dict) and "$in" in v:
                if d.get(k) not in v["$in"]:
                    return False
            elif d.get(k) != v:
                return False
        return True

    def find(self, q=None, proy=None):
        return [dict(d) for d in self.docs.values() if self._cumple(d, q)]

    def find_one(self, q=None, proy=None):
        return next(iter(self.find(q)), None)


class _Base:
    def __init__(self, reuniones, personas):
        self.reuniones, self.personas = _Coleccion(reuniones), _Coleccion(personas)


AHORA = datetime(2026, 11, 18, 15, 0, tzinfo=timezone.utc)  # 10:00 en Colombia


def _q(rol="planillero", uid=5, reunion=None):
    return acceso.Quien(uid=uid, usuario=f"u{uid}", rol=rol, reunion=reunion)


def test_traza_por_asistencia_por_quien_la_creo_y_por_la_pantalla():
    db = _Base(
        reuniones=[
            {"_id": 1, "fecha": "2026-11-18", "hora": "09:00", "hora_fin": "11:00", "creado_por_uid": 5},
            {"_id": 2, "fecha": "2026-11-18", "hora": "09:30", "hora_fin": "12:00", "creado_por_uid": 9},
            {"_id": 3, "fecha": "2026-11-17", "hora": "09:00", "hora_fin": "11:00", "creado_por_uid": 9,
             "abierta_a_equipo": True},
            {"_id": 4, "fecha": "2026-11-18", "hora": "14:00", "creado_por_uid": 5},  # todavía no empieza
        ],
        personas=[{"_id": 10, "asistencias": [{"reunion_id": 2}]}, {"_id": 11, "asistencias": []}],
    )
    t = lambda q, pid, accion="editar", reunion=None: trazas.reuniones_del_cambio(db, q, accion, pid, reunion, AHORA)  # noqa: E731
    # La persona asiste a una reunión en curso: esa (aunque quien la cambia haya creado otra en curso)
    assert t(_q(uid=5), 10) == [2]
    # No asiste a ninguna en curso: la que creó quien la cambia
    assert t(_q(uid=5), 11) == [1]
    # Ni asiste ni la creó: una reunión en curso de otro no cuenta
    assert t(_q(uid=7), 11) == []
    # Desde la pantalla de una reunión que puede ver (abierta al equipo), aunque ya pasó; una que no ve, no
    assert t(_q(uid=7, reunion=3), 11) == [3]
    assert t(_q(uid=7, reunion=2), 11) == []
    assert t(_q(rol="coordinador", uid=8, reunion=2), 11) == [2]
    # La que nombra la ruta (asistencia, nota o alta en la reunión) siempre
    assert t(_q(uid=7), 11, "asistencia", 4) == [4]
    assert t(_q(uid=5), 10, "nota", 4) == [2, 4]
    # Ni las lecturas ni el sistema
    assert t(_q(uid=5), 10, "ver_sensibles") == [] and t(_q(uid=5), 10, "suprimir") == []
    assert trazas.reuniones_del_cambio(db, "sistema", "editar", 10, None, AHORA) == []
    assert trazas.reuniones_del_cambio(db, None, "editar", 10, None, AHORA) == []
    # Fuera de toda reunión en curso, nada
    assert trazas.reuniones_del_cambio(db, _q(uid=5), "editar", 10, None, AHORA + timedelta(hours=7)) == []


def test_la_traza_nunca_impide_guardar():
    class Rota:
        def __getattr__(self, k):
            raise RuntimeError("base caída")
    assert trazas.reuniones_del_cambio(Rota(), _q(), "editar", 1, None, AHORA) == []


def test_traza_de_una_entrada_dice_si_fue_durante():
    reus = {1: {"id": 1, "titulo": "Asamblea", "fecha": "2026-11-18", "hora": "09:00", "hora_fin": "11:00"}}
    assert trazas.traza({"ts": "2026-11-18T15:00:00+00:00", "reuniones": [1, 99]}, reus) == [
        {**reus[1], "durante": True}]  # la 99 se borró: no sale
    assert trazas.traza({"ts": "2026-11-19T15:00:00+00:00", "reuniones": [1]}, reus)[0]["durante"] is False
    assert trazas.traza({"ts": "2026-11-18T15:00:00+00:00"}, reus) == []


# ───────────────────────────── API (con MongoDB) ─────────────────────────────

def _todo_el_dia(sesion, titulo="Reunión inventada de hoy", **extra) -> int:
    """Una reunión de hoy que cubre el día entero (hora de Colombia): está en curso durante la prueba."""
    ahora = datetime.now(modelo.ZONA)
    if ahora.hour == 23 and ahora.minute >= 58:
        pytest.skip("Cerca de la medianoche la reunión de hoy termina durante la prueba")
    r = sesion.post("/api/reuniones", json={"titulo": titulo, "fecha": ahora.date().isoformat(), "hora": "00:00",
                                            "hora_fin": "23:59", **extra})
    assert r.status_code == 201, r.text
    assert r.json()["en_curso"] is True
    return r.json()["id"]


def _ultima(db, pid, accion=None):
    q = {"entidad": "persona", "entidad_id": pid, **({"accion": accion} if accion else {})}
    return db.auditoria.find_one(q, sort=[("_id", -1)])


def test_rango_de_horas_de_la_reunion(sesion):
    r = sesion.post("/api/reuniones", json={"titulo": "Asamblea inventada", "fecha": "2026-11-20", "hora": "9:00",
                                            "hora_fin": "11:30"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    assert (r.json()["hora"], r.json()["hora_fin"], r.json()["en_curso"]) == ("09:00", "11:30", False)
    for malo in ({"hora_fin": "11:00"}, {"hora": "11:00", "hora_fin": "10:00"}, {"hora": "25:00"},
                 {"hora": "11:00", "hora_fin": "11:00"}):
        r = sesion.post("/api/reuniones", json={"titulo": "Asamblea inventada", "fecha": "2026-11-20", **malo})
        assert r.status_code == 422, (malo, r.text)
    # Al editar se mira con lo guardado: una hora de fin antes del inicio guardado no pasa, y quitar el inicio tampoco
    assert sesion.patch(f"/api/reuniones/{rid}", json={"hora_fin": "08:00"}).status_code == 422
    assert sesion.patch(f"/api/reuniones/{rid}", json={"hora": ""}).status_code == 422
    r = sesion.patch(f"/api/reuniones/{rid}", json={"hora": "", "hora_fin": ""})
    assert r.status_code == 200 and (r.json()["hora"], r.json()["hora_fin"]) == (None, None)
    r = sesion.patch(f"/api/reuniones/{rid}", json={"hora": "14:00"})
    assert r.status_code == 200 and r.json()["hora"] == "14:00"
    fila = next(x for x in sesion.get("/api/reuniones").json() if x["id"] == rid)
    assert fila["hora"] == "14:00" and fila["hora_fin"] is None and fila["en_curso"] is False
    # Una hora mal escrita guardada de antes (la API no la revisaba) no impide editar lo demás
    db = sesion.app.state.db
    db.reuniones.update_one({"_id": rid}, {"$set": {"hora": "9.30"}})
    assert sesion.patch(f"/api/reuniones/{rid}", json={"tema": "Agua"}).status_code == 200
    assert sesion.patch(f"/api/reuniones/{rid}", json={"hora_fin": "10:00"}).status_code == 422  # sin inicio válido


def test_lo_que_se_hace_durante_la_reunion_queda_con_su_traza(sesion, como):
    db = sesion.app.state.db
    rid = _todo_el_dia(sesion)
    asiste = persona(db, nombre="ASISTENTE INVENTADA DE LA REUNION")
    otra = persona(db, nombre="INTERVENIDA INVENTADA SIN ASISTENCIA")
    lejos = persona(db, nombre="PERSONA INVENTADA DE OTRO LUGAR")
    assert sesion.post(f"/api/reuniones/{rid}/asistentes", json={"persona_id": asiste}).status_code == 201
    assert _ultima(db, asiste, "asistencia")["reuniones"] == [rid]
    # A (que creó la reunión) cambia a la asistente y a otra persona: las dos quedan con la traza
    assert sesion.patch(f"/api/personas/{asiste}", json={"ocupacion": "Docente"}).status_code == 200
    assert sesion.patch(f"/api/personas/{otra}", json={"ocupacion": "Pescador"}).status_code == 200
    assert _ultima(db, asiste, "editar")["reuniones"] == [rid] and _ultima(db, otra, "editar")["reuniones"] == [rid]
    # Un planillero que no creó la reunión cambia a alguien que no asiste: no es de la reunión
    p = como("planillero")
    assert p.patch(f"/api/personas/{lejos}", json={"ocupacion": "Agricultor"}).status_code == 200
    assert "reuniones" not in _ultima(db, lejos, "editar")
    # La ficha: cada cambio con su reunión («durante») y, por reunión, lo que se le hizo y si asistió
    f = sesion.get(f"/api/personas/{asiste}").json()
    h = next(x for x in f["historial"] if x["accion"] == "editar")
    assert [(r["id"], r["durante"]) for r in h["reuniones"]] == [(rid, True)]
    (i,) = f["intervenciones"]
    assert (i["id"], i["cambios"], i["asistio"], i["acciones"]) == (rid, 1, True, ["editar"])
    (i,) = sesion.get(f"/api/personas/{otra}").json()["intervenciones"]
    assert (i["id"], i["asistio"]) == (rid, False)
    assert sesion.get(f"/api/personas/{lejos}").json()["intervenciones"] == []
    # La reunión: cuántos cambios tuvo cada asistente y quién se intervino sin asistencia registrada
    r = sesion.get(f"/api/reuniones/{rid}").json()
    assert [(a["id"], a["cambios"]) for a in r["asistentes"]] == [(asiste, 1)]
    assert [(x["id"], x["cambios"]) for x in r["intervenidas"]] == [(otra, 1)]
    # Habitantes: las intervenidas en la reunión (sin contar registrar la asistencia); vedado para P
    ids = {x["id"] for x in sesion.get("/api/personas", params={"intervenida_en": rid}).json()["filas"]}
    assert ids == {asiste, otra}
    assert p.get("/api/personas", params={"intervenida_en": rid}).status_code == 403
    # Auditoría de Ajustes: lo que se hizo en la reunión
    filas = sesion.get("/api/auditoria", params={"reunion_id": rid}).json()["filas"]
    assert {(x["accion"], x["entidad_id"]) for x in filas} == {("asistencia", asiste), ("editar", asiste),
                                                                ("editar", otra)}
    assert all(x["reuniones"] == [rid] for x in filas)
    # Las lecturas no llevan traza; borrar la reunión la quita de la traza (como de las notas)
    assert sesion.delete(f"/api/reuniones/{rid}").status_code == 200
    assert db.auditoria.count_documents({"reuniones": rid}) == 0
    assert sesion.get(f"/api/personas/{otra}").json()["intervenciones"] == []


def test_la_pantalla_de_la_reunion_marca_la_traza_fuera_de_hora(sesion, como):
    db = sesion.app.state.db
    p = como("planillero")
    abierta = sesion.post("/api/reuniones", json={"titulo": "Reunión inventada de ayer", "fecha": "2025-01-10",
                                                  "hora": "09:00", "hora_fin": "10:00",
                                                  "abierta_a_equipo": True}).json()["id"]
    cerrada = sesion.post("/api/reuniones", json={"titulo": "Reunión inventada cerrada", "fecha": "2025-01-10"}).json()["id"]
    pid = persona(db, nombre="PERSONA INVENTADA COMPLETADA DESPUES")
    # El modo reunión manda X-Reunion: la reunión entra en la traza aunque ya pasó («desde», no «durante»)
    r = p.patch(f"/api/personas/{pid}?modo=completar", json={"ocupacion": "Docente"}, headers={"X-Reunion": str(abierta)})
    assert r.status_code == 200, r.text
    assert _ultima(db, pid, "editar")["reuniones"] == [abierta]
    h = next(x for x in sesion.get(f"/api/personas/{pid}").json()["historial"] if x["accion"] == "editar")
    assert [(x["id"], x["durante"]) for x in h["reuniones"]] == [(abierta, False)]
    # Una reunión que P no puede ver no entra; una cabecera que no es un número, tampoco
    assert p.patch(f"/api/personas/{pid}", json={"ocupacion": "Agricultor"},
                   headers={"X-Reunion": str(cerrada)}).status_code == 200
    assert "reuniones" not in _ultima(db, pid, "editar")
    assert p.patch(f"/api/personas/{pid}", json={"ocupacion": "Docente"},
                   headers={"X-Reunion": "1; DROP"}).status_code == 200
    assert "reuniones" not in _ultima(db, pid, "editar")
    # La nota «en la reunión» solo en una que existe y que se puede ver
    assert p.post(f"/api/personas/{pid}/notas", json={"texto": "Nota inventada", "reunion_id": 999999}).status_code == 422
    assert p.post(f"/api/personas/{pid}/notas", json={"texto": "Nota inventada", "reunion_id": cerrada}).status_code == 403
    r = p.post(f"/api/personas/{pid}/notas", json={"texto": "Nota inventada", "reunion_id": abierta})
    assert r.status_code == 201 and _ultima(db, pid, "nota")["reuniones"] == [abierta]
    # P ve la reunión con sus intervenidas, en la proyección de fila de su rol (sin lo vedado)
    d = p.get(f"/api/reuniones/{abierta}").json()
    assert [x["id"] for x in d["intervenidas"]] == [pid]
    sin_vedados(d, "reunión para P")


def _lider(db, nombre: str) -> int:
    return persona(db, nombre=nombre, lider=True)


def test_varios_lideres_por_persona(sesion, como):
    db = sesion.app.state.db
    l1, l2 = _lider(db, "LIDER INVENTADO UNO"), _lider(db, "LIDER INVENTADA DOS")
    no_lider = persona(db, nombre="PERSONA INVENTADA SIN MARCA")
    x = persona(db, nombre="PERSONA INVENTADA CAPTADA")
    y = persona(db, nombre="PERSONA INVENTADA DE UN LIDER")
    r = sesion.post(f"/api/personas/{x}/lideres", json={"lider_id": l1})
    assert r.status_code == 201, r.text
    assert [(l["id"], l["nombre"], l["marcado"]) for l in r.json()["lideres"]] == [(l1, "LIDER INVENTADO UNO", True)]
    assert r.json()["lideres"][0]["asignado_por"] == "admin" and r.json()["lideres"][0]["asignado_en"]
    # Repetir no cambia nada ni deja otra entrada en la auditoría
    n = db.auditoria.count_documents({"entidad_id": x, "accion": "asignar_lider"})
    assert len(sesion.post(f"/api/personas/{x}/lideres", json={"lider_id": l1}).json()["lideres"]) == 1
    assert db.auditoria.count_documents({"entidad_id": x, "accion": "asignar_lider"}) == n == 1
    # Un segundo líder: la persona la capta más de uno
    assert len(sesion.post(f"/api/personas/{x}/lideres", json={"lider_id": l2}).json()["lideres"]) == 2
    assert sesion.post(f"/api/personas/{y}/lideres", json={"lider_id": l1}).status_code == 201
    # Solo fichas marcadas como líder, y nadie es su propio líder
    assert sesion.post(f"/api/personas/{x}/lideres", json={"lider_id": no_lider}).status_code == 422
    assert sesion.post(f"/api/personas/{l1}/lideres", json={"lider_id": l1}).status_code == 422
    assert sesion.post(f"/api/personas/{x}/lideres", json={"lider_id": 99999999}).status_code == 422
    # El líder ve a quiénes trajo
    assert sesion.get(f"/api/personas/{l1}").json()["traidas"] == {"total": 2, "compartidas": 1}
    assert sesion.get(f"/api/personas/{no_lider}").json()["traidas"] is None
    # Habitantes: las que trajo un líder, las que trae más de uno, y el número de líderes en la fila
    filas = sesion.get("/api/personas", params={"lider_id": l1}).json()["filas"]
    assert {f["id"] for f in filas} == {x, y}
    filas = sesion.get("/api/personas", params={"varios_lideres": 1}).json()["filas"]
    assert [(f["id"], f["lideres_n"]) for f in filas] == [(x, 2)]
    # La lista de líderes
    d = sesion.get("/api/lideres").json()
    por = {l["id"]: l for l in d["lideres"]}
    assert (por[l1]["traidas"], por[l1]["compartidas"], por[l2]["traidas"], por[l2]["compartidas"]) == (2, 1, 1, 1)
    assert d["personas_con_varios"] == 1 and no_lider not in por
    # La auditoría no guarda a quién se asignó (es un dato político)
    a = _ultima(db, x, "asignar_lider")
    assert json.loads(a["detalle"]) == {"lider_id": "(oculto)"} and a["campos"] == ["lideres"]
    # Quitar
    r = sesion.delete(f"/api/personas/{x}/lideres/{l2}")
    assert r.status_code == 200 and [l["id"] for l in r.json()["lideres"]] == [l1]
    assert sesion.get("/api/lideres").json()["personas_con_varios"] == 0
    # Quitar la marca de líder no le quita a quienes trajo
    assert sesion.patch(f"/api/personas/{l1}", json={"lider": False}).status_code == 200
    assert sesion.get(f"/api/personas/{x}").json()["lideres"][0]["marcado"] is False
    assert sesion.post(f"/api/personas/{y}/lideres", json={"lider_id": l1}).status_code == 201  # ya lo tenía


def test_lideres_solo_para_administrador_y_coordinador(sesion, como):
    db = sesion.app.state.db
    l1 = _lider(db, "LIDER INVENTADO DEL EQUIPO")
    x = persona(db, nombre="PERSONA INVENTADA DEL EQUIPO")
    k = coordinador(sesion.app, db)
    assert k.post(f"/api/personas/{x}/lideres", json={"lider_id": l1}).status_code == 201
    assert [l["id"] for l in k.get(f"/api/personas/{x}").json()["lideres"]] == [l1]
    for rol in ("planillero", "consultor"):
        c = como(rol)
        assert c.post(f"/api/personas/{x}/lideres", json={"lider_id": l1}).status_code == 403
        assert c.delete(f"/api/personas/{x}/lideres/{l1}").status_code == 403
        assert c.get("/api/lideres").status_code == 403
        for filtro in ({"lider_id": l1}, {"varios_lideres": 1}):
            assert c.get("/api/personas", params=filtro).status_code == 403
    p = como("planillero")
    f = p.get(f"/api/personas/{x}").json()
    sin_vedados(f, "ficha de P")
    assert not {"lideres", "traidas", "intervenciones"} & set(f)
    sin_vedados(p.get("/api/personas").json(), "filas de P")
    # P no los manda al registrar a alguien; A y K sí
    r = p.post("/api/personas", json={"nombre": "PERSONA INVENTADA NUEVA DE P", "lideres": [l1]})
    assert r.status_code == 403
    r = sesion.post("/api/personas", json={"nombre": "PERSONA INVENTADA NUEVA DE A", "lideres": [l1], "forzar": True})
    assert r.status_code == 201, r.text
    assert [l["id"] for l in r.json()["lideres"]] == [l1]
    assert sesion.post("/api/personas", json={"nombre": "PERSONA INVENTADA NUEVA MAL", "lideres": [x],
                                              "forzar": True}).status_code == 422


def test_unir_y_suprimir_conservan_los_lideres_coherentes(sesion):
    db = sesion.app.state.db
    l1, l2 = _lider(db, "LIDER INVENTADO PRIMERO"), _lider(db, "LIDER INVENTADO REPETIDO")
    a = persona(db, nombre="PERSONA INVENTADA QUE QUEDA")
    b = persona(db, nombre="PERSONA INVENTADA QUE SE UNE")
    w = persona(db, nombre="PERSONA INVENTADA CON LOS DOS")
    for pid, lid in ((a, l1), (b, l2), (w, l1), (w, l2)):
        assert sesion.post(f"/api/personas/{pid}/lideres", json={"lider_id": lid}).status_code == 201
    # Al unir B en A, A queda con los líderes de las dos
    assert sesion.post(f"/api/personas/{a}/fusionar", json={"con_id": b}).status_code == 200
    assert [l["id"] for l in sesion.get(f"/api/personas/{a}").json()["lideres"]] == [l1, l2]
    # Al unir un líder en otro, quien tenía a los dos queda con uno solo (sin repetir) y nadie es su propio líder
    assert sesion.post(f"/api/personas/{l1}/lideres", json={"lider_id": l2}).status_code == 201
    assert sesion.post(f"/api/personas/{l1}/fusionar", json={"con_id": l2}).status_code == 200
    assert [l["id"] for l in db.personas.find_one({"_id": w})["lideres"]] == [l1]
    assert [l["id"] for l in db.personas.find_one({"_id": a})["lideres"]] == [l1]
    assert db.personas.find_one({"_id": l1})["lideres"] == []
    # Al suprimir un líder, sale de los líderes de todas
    assert sesion.delete(f"/api/personas/{l1}").status_code == 200
    assert db.personas.count_documents({"lideres.id": l1}) == 0
    assert sesion.get(f"/api/personas/{w}").json()["lideres"] == []
