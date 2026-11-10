"""Remate de las herramientas del asistente tras la revisión de sus arreglos: la búsqueda libre (`q`) de
buscar_personas y la cédula o el teléfono de personas_parecidas ya no sirven de oráculo, y los conteos que vienen de la
API (reuniones, mi trabajo, lo pendiente del trabajo y el equipo) no cuentan a quien no autorizó el tratamiento de sus
datos, o no se dan.

Las pruebas tienen la forma del ataque: dos búsquedas, o dos situaciones, que solo se distinguen en un dato que el
modelo no debe conocer (la dirección de quien no autorizó, que asistió a una reunión, los dígitos enmascarados de un
teléfono…) tienen que darle al modelo exactamente lo mismo. Todas fallan sin el arreglo salvo
`test_la_interfaz_sigue_igual`, que cuida que el panel siga buscando y contando como siempre: los parámetros nuevos de
la API (`estricta` y `tratables`) son solo del asistente.

Solo datos inventados; nunca se llama a Anthropic ni a Mnemo."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import ayudas_agente as aa
from ayudas_g3 import autorizada, persona
from app import db as bd
from app import modelo
from app.agente.herramientas import gestion as hg
from app.agente.herramientas import personas as hp
from app.agente.herramientas.base import ErrorHerramienta

H = {h.nombre: h for h in hp.HERRAMIENTAS + hg.HERRAMIENTAS}
TEL_MARTA, CEDULA_MARTA = "3001112233", "71234567"
TEL_ROSA, CEDULA_ROSA = "3104445566", "1023456789"
FILA_NO_AUTORIZO = {"id", "nombre", "lugar", "consentimiento", "aviso"}


# ───────────────────────────── Ayudas ─────────────────────────────

@pytest.fixture
def ctx_de(sesion):
    """`ctx_de(cliente)`: el contexto de herramienta con la sesión de ese cliente; se cierra al terminar."""
    abiertos = []

    def hacer(cli, tid: str = "toolu_remate"):
        c = aa.contexto(sesion.app, cli, tool_use_id=tid)
        abiertos.append(c)
        return c

    yield hacer
    for c in abiertos:
        aa.correr(sesion, c.api.cerrar)


def _ej(sesion, ctx, nombre: str, entrada: dict):
    return aa.correr(sesion, aa.ejecutar, H[nombre], ctx, entrada)


def _visto(sesion, ctx, nombre: str, entrada: dict):
    """Lo que el modelo recibe de la herramienta: el texto de su resultado, o el código de su error."""
    try:
        return "ok", json.loads(_ej(sesion, ctx, nombre, entrada).texto_para_modelo())
    except ErrorHerramienta as e:
        return "error", e.codigo


def _ids(visto) -> set[int]:
    estado, c = visto
    if estado != "ok":
        return set()
    filas = c.get("filas") or c.get("parecidas") or (c.get("cola") or {}).get("filas") or []
    return {f.get("id") for f in filas}


def _sin(c: dict, *claves: str) -> dict:
    return {k: v for k, v in c.items() if k not in claves}


def _vereda(db, nombre: str = "VEREDA INVENTADA DEL REMATE") -> int:
    lid = bd.siguiente_id(db, "lugares")
    db.lugares.insert_one({"_id": lid, "nombre": nombre, "tipo": "vereda", "zona": "rural", "lat": 6.95,
                           "lon": -73.95, "alias": [], "padre": None})
    return lid


def _reunion(cli, titulo: str, fecha: str = "2026-11-02") -> int:
    r = cli.post("/api/reuniones", json={"titulo": titulo, "fecha": fecha})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _acercamiento(db, uid: int, pid: int) -> None:
    """Una llamada de hoy de `uid` a `pid`, como la deja la API (sin pasar por ella: a quien no autorizó, el
    consultor ya no lo llama, pero pudo llamarlo antes de que dijera que no)."""
    db.acercamientos.insert_one({"_id": bd.siguiente_id(db, "acercamientos"), "persona_id": pid, "uid": uid,
                                 "fecha": modelo.hoy_local().isoformat(), "ts": bd.ahora(), "canal": "llamada",
                                 "resultado": "contesto", "efectivo": True, "anulado": False, "auto": False})


@pytest.fixture
def gente(sesion):
    """Una vereda con MARTA, que no autorizó (con dirección, sitio, correo, cédula y teléfono), y ROSA, que sí."""
    db = sesion.app.state.db
    lugar = _vereda(db)
    marta = persona(db, nombre="MARTA NOAUTORIZO INVENTADA", consentimiento="no", lugar_id=lugar,
                    direccion="CALLE 49 # 47-10", direccion_norm="CALLE 49 4710", lugar_texto="FINCA LA ESPERANZA",
                    correo="marta.inventada@ejemplo.co", cedula=CEDULA_MARTA, telefono=TEL_MARTA)
    rosa = persona(db, nombre="ROSA SIAUTORIZO INVENTADA", lugar_id=lugar, cedula=CEDULA_ROSA, telefono=TEL_ROSA)
    autorizada(db, rosa)
    return SimpleNamespace(lugar=lugar, marta=marta, rosa=rosa)


# ───────────────────────────── 1. `q` no es un oráculo ─────────────────────────────

def test_q_no_deja_probar_datos_de_quien_no_autorizo(sesion, ctx_de, gente):
    """Cada par de búsquedas se distingue solo en un dato de MARTA: su dirección, su correo, el sitio escrito, el
    comienzo de su cédula, una parte de su teléfono o el número entero. El modelo recibe lo mismo con las dos, y nunca
    a MARTA. Antes, la que casaba la traía: cada «sí» era un dato suyo (también con `consentimiento: no`)."""
    ctx = ctx_de(sesion)
    pares = [("CALLE 49", "CALLE 50"), ("MARTA 49", "MARTA 50"), ("MARTA EJEMPLO", "MARTA HOTMAIL"),
             ("marta.inventada", "marta.otra"), ("MARTA ESPERANZA", "MARTA ALEGRIA"), ("7123", "7124"),
             ("71234", "71244"), ("30011", "30019"), ("MARTA 3001", "MARTA 3009"), ("MARTA 7123", "MARTA 7124"),
             (CEDULA_MARTA, "71234568"), (TEL_MARTA, "3001112234")]
    for a, b in pares:
        for extra in ({}, {"filtros": {"consentimiento": "no"}}, {"orden": "nombre"}):
            va, vb = (_visto(sesion, ctx, "buscar_personas", {"q": q, **extra}) for q in (a, b))
            assert va == vb, (a, b, extra, va, vb)
            assert gente.marta not in _ids(va), (a, extra, va)
    # Quién es, sí: por su nombre sale como quien no autorizó (solo quién es y su vereda), también en la lista
    for extra in ({}, {"filtros": {"consentimiento": "no", "lugar_id": gente.lugar}}):
        r = _ej(sesion, ctx, "buscar_personas", {"q": "MARTA NOAUTORIZO", **extra})
        assert [f["id"] for f in r.contenido["filas"]] == [gente.marta], extra
        assert set(r.contenido["filas"][0]) <= FILA_NO_AUTORIZO


def test_q_no_reconstruye_el_telefono_ni_la_cedula_enmascarados(sesion, ctx_de, gente):
    """La fila de ROSA trae los 4 últimos dígitos de su teléfono y los 3 últimos de su cédula. Antes, buscar
    «ROSA d5566» con cada dígito d decía cuál era el anterior, y en unas 25 búsquedas salía el número entero (la
    cédula, probando su comienzo). Ahora un número solo casa entero: la cédula o el teléfono completos."""
    ctx = ctx_de(sesion)

    def la_trae(q: str) -> bool:
        return gente.rosa in _ids(_visto(sesion, ctx, "buscar_personas", {"q": q}))

    fila = next(f for f in _ej(sesion, ctx, "buscar_personas", {"q": "ROSA SIAUTORIZO"}).contenido["filas"]
                if f["id"] == gente.rosa)
    assert (fila["telefono_mascara"], fila["cedula_ult3"]) == ("···5566", "···789")
    for forma in ("ROSA {}", "{}", "{} ROSA"):
        sufijo = "5566"
        for _ in range(6):
            mas_largo = next((d + sufijo for d in "0123456789" if la_trae(forma.format(d + sufijo))), None)
            if mas_largo is None:
                break
            sufijo = mas_largo
        assert sufijo == "5566", (forma, sufijo)
    assert not any(la_trae(q) for q in ("1023", "10234", "1023456", "ROSA 1023", "4445566", "310444"))
    # El número entero sí la encuentra, aunque venga escrito por grupos o con el indicativo, y la fila no suma los
    # dígitos enmascarados (el modelo ya tiene el número que escribió)
    for numero in (TEL_ROSA, CEDULA_ROSA, "+57 310 444 5566", "310-444-5566", "1.023.456.789"):
        r = _ej(sesion, ctx, "buscar_personas", {"q": numero})
        f = next(f for f in r.contenido["filas"] if f["id"] == gente.rosa)
        assert "telefono_mascara" not in f and "cedula_ult3" not in f, numero


def test_por_numero_nunca_sale_quien_no_autorizo(sesion, como, ctx_de, gente):
    """Con el número entero de MARTA, ni el administrador, ni el planillero de su vereda, ni el consultor la encuentran
    por el asistente: diría que ese número es suyo. Con «consentimiento: no», un número no se combina."""
    p = como("planillero", asignacion={"lugares": [gente.lugar], "areas": []})
    c = como("consultor")
    for cli, entradas in (
            (sesion, ({"q": TEL_MARTA}, {"q": CEDULA_MARTA}, {"q": TEL_MARTA, "orden": "nombre"},
                      {"q": CEDULA_MARTA, "filtros": {"lugar_id": gente.lugar}})),
            (p, ({"q": TEL_MARTA}, {"q": CEDULA_MARTA}, {"q": CEDULA_MARTA, "orden": "nombre"})),
            (c, ({"q": TEL_MARTA},))):
        ctx = ctx_de(cli)
        for entrada in entradas:
            r = _ej(sesion, ctx, "buscar_personas", entrada)
            ids = {f["id"] for f in r.contenido["filas"]}
            assert gente.marta not in ids and gente.marta not in r.personas, (cli, entrada)
            assert r.contenido["total"] == len(ids) and "nota_autorizacion" in r.contenido, (cli, entrada)
        if cli is not c:
            for q in (TEL_MARTA, CEDULA_MARTA):
                with pytest.raises(ErrorHerramienta) as e:
                    _ej(sesion, ctx, "buscar_personas", {"q": q, "filtros": {"consentimiento": "no"}})
                assert e.value.codigo == "invalido"


def test_el_orden_no_dice_nada_de_quien_no_autorizo(sesion, ctx_de, gente):
    """El orden de las filas también es una respuesta. La búsqueda rápida ponía primero las fichas más completas, y el
    orden «lugar» ordena dentro del lugar por la dirección: el puesto de MARTA entre otras fichas que el modelo sí ve
    decía cuán completa está la suya o entre qué direcciones queda la suya. Ahora la búsqueda rápida del asistente va
    por nombre, y el orden «lugar» es de los que la dejan fuera."""
    db = sesion.app.state.db
    for nombre, completitud, direccion in (("MARTA ANA INVENTADA", 30, "CALLE 10"), ("MARTA BEA INVENTADA", 70,
                                                                                    "CALLE 90")):
        pid = persona(db, nombre=nombre, lugar_id=gente.lugar, completitud=completitud, direccion=direccion,
                      direccion_norm=direccion)
        autorizada(db, pid)
    ctx = ctx_de(sesion)
    vistos = []
    for completitud, direccion in ((10, "CALLE 05"), (90, "CALLE 50")):
        db.personas.update_one({"_id": gente.marta}, {"$set": {"completitud": completitud,
                                                               "direccion_norm": direccion}})
        vistos.append([_visto(sesion, ctx, "buscar_personas", {"q": "MARTA"}),
                       _visto(sesion, ctx, "buscar_personas", {"filtros": {"lugar_id": gente.lugar},
                                                               "orden": "lugar"})])
    assert vistos[0] == vistos[1], vistos
    assert gente.marta in _ids(vistos[0][0]) and gente.marta not in _ids(vistos[0][1])
    with pytest.raises(ErrorHerramienta) as e:
        _ej(sesion, ctx, "buscar_personas", {"filtros": {"consentimiento": "no"}, "orden": "lugar"})
    assert e.value.codigo == "invalido"


def test_parecidas_por_cedula_o_telefono_no_traen_a_quien_no_autorizo(sesion, ctx_de, gente):
    """ROSA (que sí autorizó) comparte un teléfono con MARTA y su nombre se le parece, pero no tanto como para ser la
    misma persona. Que MARTA salga por coincidir en el teléfono o en la cédula diría que ese número es suyo; que ROSA
    salga entre las parecidas de MARTA, también. De quien no autorizó solo cuenta el nombre."""
    db = sesion.app.state.db
    tels = [modelo.telefono_nuevo(n, "panel") for n in (TEL_ROSA, TEL_MARTA)]
    db.personas.update_one({"_id": gente.rosa}, {"$set": {"telefonos": tels, **modelo.derivar_telefonos(tels)}})
    ctx = ctx_de(sesion)
    pares = [({"nombre": "ROSA SIAUTORIZO INVENTADA", "telefono": TEL_MARTA},
              {"nombre": "ROSA SIAUTORIZO INVENTADA", "telefono": "3001112234"}),
             ({"nombre": "JUANA DISTINTA INVENTADA", "cedula": CEDULA_MARTA},
              {"nombre": "JUANA DISTINTA INVENTADA", "cedula": "71234568"})]
    for a, b in pares:
        va, vb = (_visto(sesion, ctx, "personas_parecidas", x) for x in (a, b))
        assert va == vb, (a, va, vb)
        assert gente.marta not in _ids(va), a
    assert gente.marta not in _ids(_visto(sesion, ctx, "personas_parecidas", {"persona_id": gente.rosa}))
    assert gente.rosa not in _ids(_visto(sesion, ctx, "personas_parecidas", {"persona_id": gente.marta}))
    # Por el nombre, sí: es quién es (sin el parecido ni la cédula)
    r = _ej(sesion, ctx, "personas_parecidas", {"nombre": "MARTA NOAUTORIZO INVENTADA", "telefono": TEL_MARTA})
    fila = next(f for f in r.contenido["parecidas"] if f["id"] == gente.marta)
    assert set(fila) <= FILA_NO_AUTORIZO


# ───────────────────────────── 2. Los conteos no la cuentan ─────────────────────────────

def test_reuniones_no_cuentan_a_quien_no_autorizo(sesion, ctx_de, gente):
    """Dos reuniones iguales salvo que a una fue MARTA (y se registró en ella): listar, ver (con y sin asistentes),
    registrar a otra persona y los indicadores le dicen al modelo lo mismo de las dos. Antes, los asistentes, las
    personas nuevas y el aviso «Se muestran 1 de 2» decían que alguien que no se lista había ido: que asistió a una
    reunión de la campaña es un dato suyo (y puede revelar una afinidad política)."""
    db = sesion.app.state.db
    r1, r2 = _reunion(sesion, "Reunión inventada del remate A"), _reunion(sesion, "Reunión inventada del remate B")
    for rid, quienes in ((r1, (gente.rosa, gente.marta)), (r2, (gente.rosa,))):
        for pid in quienes:
            assert sesion.post(f"/api/reuniones/{rid}/asistentes", json={"persona_id": pid}).status_code == 201
    db.personas.update_one({"_id": gente.marta}, {"$set": {"reunion_origen": r1}})  # se registró en la primera
    ctx = ctx_de(sesion)
    propio = ("id", "titulo", "ruta")
    lista = {x["id"]: x for x in _ej(sesion, ctx, "listar_reuniones", {}).contenido["reuniones"]}
    assert _sin(lista[r1], *propio) == _sin(lista[r2], *propio)
    assert (lista[r1]["asistentes"], lista[r1]["nuevos"]) == (1, 0)
    for n in (30, 1, 0):
        v1, v2 = (_visto(sesion, ctx, "ver_reunion", {"reunion_id": rid, "asistentes": n}) for rid in (r1, r2))
        assert v1[0] == v2[0] == "ok" and _sin(v1[1], *propio) == _sin(v2[1], *propio), (n, v1, v2)
        assert v1[1]["asistentes_total"] == 1
    r = _ej(sesion, ctx, "ver_reunion", {"reunion_id": r1})
    assert r.resumen == "1 asistente" and gente.marta not in r.personas
    indicadores = {x["id"]: x for x in _ej(sesion, ctx, "indicadores", {}).contenido["reuniones_recientes"]}
    assert indicadores[r1]["asistentes"] == indicadores[r2]["asistentes"] == 1
    juana = persona(db, nombre="JUANA ASISTENTE INVENTADA")
    autorizada(db, juana)
    vistos = [_ej(sesion, ctx_de(sesion, f"toolu_asis{rid}"), "agregar_asistente",
                  {"reunion_id": rid, "persona_id": juana}).contenido["reunion"] for rid in (r1, r2)]
    assert _sin(vistos[0], *propio) == _sin(vistos[1], *propio) and vistos[0]["asistentes_total"] == 2


def test_mi_trabajo_no_cuenta_a_quien_no_autorizo(sesion, como, ctx_de, gente):
    """Lo que el planillero y el consultor hicieron con MARTA (registrarla, llamarla) no cambia lo que el modelo
    recibe de mi_trabajo: ni las listas, ni hoy y la semana, ni la cola «hoy» (tampoco cuando el administrador mira
    el trabajo de otro). Antes la contaban, y restando dos conteos se sabía que la habían llamado o registrado hoy."""
    db, app = sesion.app.state.db, sesion.app
    p = como("planillero", asignacion={"lugares": [gente.lugar], "areas": []})
    c = como("consultor")
    qp = aa.quien_de(app, p.uid)
    bd.auditar(db, qp, "crear", "persona", gente.rosa, {"nombre": "x"})
    db.personas.update_one({"_id": gente.rosa}, {"$set": {"creado_por": {"uid": p.uid, "usuario": p.usuario}}})
    _acercamiento(db, c.uid, gente.rosa)

    def fotos():
        return [_visto(sesion, ctx_de(p), "mi_trabajo", {}), _visto(sesion, ctx_de(c), "mi_trabajo", {}),
                _visto(sesion, ctx_de(c), "mi_trabajo", {"lista": "mis_hoy"}),
                _visto(sesion, ctx_de(sesion), "mi_trabajo", {"uid": p.uid}),
                _visto(sesion, ctx_de(sesion), "mi_trabajo", {"uid": c.uid})]

    antes = fotos()
    assert antes[2][1]["cola"]["total"] == 1 and _ids(antes[2]) == {gente.rosa}
    # Lo mismo con MARTA: la registró el planillero (y la editó) y la llamó el consultor
    bd.auditar(db, qp, "crear", "persona", gente.marta, {"nombre": "x"})
    bd.auditar(db, qp, "editar", "persona", gente.marta, {"nombre": "x"}, campos=["ocupacion"])
    db.personas.update_one({"_id": gente.marta}, {"$set": {"creado_por": {"uid": p.uid, "usuario": p.usuario},
                                                           "actualizado_por": {"uid": p.uid, "usuario": p.usuario}}})
    _acercamiento(db, c.uid, gente.marta)
    assert fotos() == antes


def test_lo_pendiente_del_trabajo_no_cuenta_a_quien_no_autorizo(sesion, como, ctx_de, gente):
    """Que MARTA tenga un pedido de actualización o una situación por confirmar no cambia lo que pendientes le dice al
    modelo. Antes, «trabajo» la contaba y mi_trabajo («Pendientes de actualizar») no: la resta era un dato suyo."""
    db = sesion.app.state.db
    p = como("planillero", asignacion={"lugares": [gente.lugar], "areas": []})
    db.personas.update_one({"_id": gente.rosa}, {"$set": {"requiere_actualizacion": {"motivo": "administrador"}}})

    def fotos():
        return [_visto(sesion, ctx_de(cli), "pendientes", {}) for cli in (sesion, p)]

    antes = fotos()
    assert antes[0][1]["trabajo"]["n"] == antes[1][1]["trabajo"]["n"] == 1
    assert antes[0][1]["calidad"]["situaciones_por_confirmar"] == 0
    db.personas.update_one({"_id": gente.marta}, {"$set": {"requiere_actualizacion": {"motivo": "administrador"}}})
    assert fotos() == antes
    # Reportada como fallecida, sin confirmar: deja de ser vigente (no cuenta en «trabajo») y cuenta en situaciones
    db.personas.update_one({"_id": gente.marta}, {"$set": {"situacion": {"estado": "fallecida",
                                                                         "confirmada": False}}})
    assert fotos() == antes


def test_pendientes_no_dice_de_quien_es_cada_solicitud(sesion, ctx_de, gente):
    """Las solicitudes de los titulares que vencen pronto llegaban con el id de la persona: de MARTA, el modelo sabía
    que pidió la supresión de sus datos (y, con ver_persona, quién es). La herramienta dice que no trae datos de
    personas: da el tipo, el canal y el plazo, sin de quién es (cada caso se atiende en Calidad del panel)."""
    db = sesion.app.state.db
    vistos = []
    for pid in (gente.marta, gente.rosa):
        r = sesion.post("/api/solicitudes", json={"persona_id": pid, "tipo": "supresion", "canal": "teléfono",
                                                  "descripcion": "Pide que se borren sus datos"})
        assert r.status_code == 201, r.text
        sid = r.json()["id"]
        r = _ej(sesion, ctx_de(sesion), "pendientes", {})
        proximas = r.contenido["calidad"]["solicitudes"]["proximas"]
        vistos.append([_sin(x, "id") for x in proximas if x["id"] == sid])
        assert pid not in r.personas and not any("persona_id" in x for x in proximas)
        db.solicitudes.delete_one({"_id": sid})
    assert vistos[0] and vistos[0] == vistos[1], vistos


def test_equipo_no_da_cifras_que_cuentan_a_quien_no_autorizo(sesion, como, ctx_de, gente):
    """Lo que el equipo hizo con una persona que no autorizó (registrarla, llamarla) y que esté en una vereda asignada
    no cambia lo que el modelo recibe del equipo: los indicadores de cada usuario y el avance por vereda se piden sin
    ella (`tratables`; que vuelven a estar, test_remate_cierre.py)."""
    db, app = sesion.app.state.db, sesion.app
    p = como("planillero", asignacion={"lugares": [gente.lugar], "areas": []})
    c = como("consultor")
    ctx = ctx_de(sesion)
    antes = _visto(sesion, ctx, "equipo", {"avance": "lugar"})
    assert antes[0] == "ok" and {u["usuario"] for u in antes[1]["usuarios"]} >= {p.usuario, c.usuario}
    teresa = persona(db, nombre="TERESA NOAUTORIZO INVENTADA", consentimiento="no", lugar_id=gente.lugar,
                     cedula="71230001", telefono="3001230001")
    bd.auditar(db, aa.quien_de(app, p.uid), "crear", "persona", teresa, {"nombre": "x"})
    bd.auditar(db, aa.quien_de(app, p.uid), "asistencia", "persona", teresa, {"reunion_id": 1})
    _acercamiento(db, c.uid, teresa)
    assert _visto(sesion, ctx, "equipo", {"avance": "lugar"}) == antes
    fila = next(f for f in antes[1]["avance"]["filas"] if f["id"] == gente.lugar)
    assert p.usuario in fila["responsables"] and fila["personas"] == 1  # ROSA, sin MARTA
    assert "no autorizaron" in antes[1]["nota_autorizacion"]


# ───────────────────────────── Lo que no cambia ─────────────────────────────

def test_la_interfaz_sigue_igual(sesion, como, gente):
    """Sin los parámetros del asistente, la API busca y cuenta como siempre: Habitantes busca por dirección, por el
    comienzo de la cédula o por parte del teléfono, y las reuniones, Mi trabajo y las insignias cuentan a todos (la
    persona del equipo los ve en el panel)."""
    db = sesion.app.state.db
    for q in ("CALLE 49", "7123", "30011", "marta.inventada"):
        assert gente.marta in {f["id"] for f in sesion.get("/api/buscar", params={"q": q}).json()}, q
        assert gente.marta in {f["id"] for f in sesion.get("/api/personas", params={"q": q}).json()["filas"]}, q
    rid = _reunion(sesion, "Reunión inventada de la interfaz")
    for pid in (gente.rosa, gente.marta):
        assert sesion.post(f"/api/reuniones/{rid}/asistentes", json={"persona_id": pid}).status_code == 201
    assert next(x for x in sesion.get("/api/reuniones").json() if x["id"] == rid)["asistentes"] == 2
    p = como("planillero", asignacion={"lugares": [gente.lugar], "areas": []})
    db.personas.update_many({"_id": {"$in": [gente.rosa, gente.marta]}},
                            {"$set": {"creado_por": {"uid": p.uid, "usuario": p.usuario},
                                      "requiere_actualizacion": {"motivo": "administrador"}}})
    listas = {x["clave"]: x["n"] for x in p.get("/api/trabajo").json()["listas"]}
    assert listas["mis_recientes"] == 2
    assert sesion.get("/api/insignias").json()["trabajo"] == 2
    parecidas = sesion.get("/api/parecidas", params={"nombre": "JUANA DISTINTA INVENTADA",
                                                     "cedula": CEDULA_MARTA}).json()
    assert gente.marta in {f["id"] for f in parecidas}
