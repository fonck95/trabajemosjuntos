"""El motor de la analítica avanzada (`app/analitica.py`) da las cifras correctas con datos inventados conocidos:
cada tipo (tabla, serie, embudo, cobertura, ritmo, brechas, equipo, calidad, anomalías, cohortes, franjas, intentos,
captura, comparar, efecto de las reuniones y diagnóstico), los enlaces del diagnóstico (con la misma cifra que abre
Habitantes), el catálogo y el rendimiento con unas 3000 personas.

Solo datos inventados."""
from __future__ import annotations

import json
import math
import re
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import ayudas_analitica as ya
from app import analitica as an
from app import db as bd
from app import modelo
from app.api import filtros as fapi
from conftest import crear_usuario

HOY = modelo.hoy_local()
RAIZ = Path(__file__).resolve().parents[1]


def _filas(t: dict) -> dict:
    return {f["valor"]: f for f in t["filas"]}


def _puestos(db) -> dict[str, int]:
    eleccion = modelo.leer_ajustes(db)["eleccion_vigente"]
    return {p["codigo"]: p["_id"] for p in bd.puestos_vigentes(db, eleccion)}


def _votacion(db, puesto_id, mesa=None, estado="sin_verificar", eleccion=None):
    return {"puesto_id": puesto_id, "mesa": mesa, "estado": estado, "donde": "yondo",
            "eleccion": eleccion or modelo.leer_ajustes(db)["eleccion_vigente"]}


# ───────────────────────────── tabla ─────────────────────────────

def test_tabla_de_una_y_dos_dimensiones(sesion):
    db = sesion.app.state.db
    filas = ([{"sexo": "F", "zona": "urbana", "cedula": str(81_000_000 + i) if i < 15 else None} for i in range(30)] +
             [{"sexo": "M", "zona": "rural"} for _ in range(20)] +
             [{"sexo": "M", "zona": "urbana", "telefono": str(3_001_000_000 + i)} for i in range(15)] +
             [{"sexo": "F", "zona": "rural"} for _ in range(12)])
    ya.personas(db, filas)
    ya.persona(db, sexo="F", zona="rural", consentimiento="no")
    ya.persona(db, sexo="F", zona="rural", situacion={"estado": "fallecida"})
    t = ya.consulta(sesion, tipo="tabla", dimensiones=["sexo"],
                    metricas=["personas", "pct", "pct_con_cedula", "pct_telefono_usable", "completitud_media"])
    f = _filas(t)
    assert t["base"] == {"personas": 77} and t["ocultas"] == 0
    assert (f["F"]["personas"], f["M"]["personas"]) == (42, 35)
    assert f["F"]["pct"] == round(100 * 42 / 77, 1) and f["M"]["pct"] == round(100 * 35 / 77, 1)
    assert f["F"]["pct_con_cedula"] == round(100 * 15 / 42, 1) and f["M"]["pct_con_cedula"] == 0.0
    assert f["M"]["pct_telefono_usable"] == round(100 * 15 / 35, 1)
    assert isinstance(f["F"]["completitud_media"], float)
    t2 = ya.consulta(sesion, tipo="tabla", dimensiones=["zona", "sexo"], metricas=["personas", "pct"])
    cols = [c["valor"] for c in t2["columnas"]]
    celdas = {(r["valor"], c): x for r in t2["filas"] for c, x in zip(cols, r["celdas"])}
    assert celdas[("urbana", "F")]["personas"] == 30 and celdas[("urbana", "M")]["personas"] == 15
    assert celdas[("rural", "F")]["personas"] == 12 and celdas[("rural", "M")]["personas"] == 20
    assert celdas[("urbana", "F")]["pct"] == round(100 * 30 / 45, 1)  # la parte de la fila
    assert t2["totales_columna_visibles"][cols.index("F")] == 42


def test_tabla_por_lugar_junta_los_chicos_y_nombra_los_lugares(sesion):
    db = sesion.app.state.db
    ls = ya.lugares(db, 5)
    filas = [{"lugar_id": ls[0]} for _ in range(12)] + [{"lugar_id": ls[1]} for _ in range(11)]
    filas += [{"lugar_id": l} for l in ls[2:] for _ in range(2)] + [{} for _ in range(7)]
    ya.personas(db, filas)
    t = ya.consulta(sesion, tipo="tabla", dimensiones=["lugar"])
    f = _filas(t)
    nombre = db.lugares.find_one({"_id": ls[0]})
    assert f[ls[0]]["personas"] == 12 and f[ls[0]]["etiqueta"] == f"{nombre['nombre']} ({nombre['tipo']})"
    assert f["otros_lugares"]["personas"] == 6 and f["sin"]["personas"] == 7
    assert [x["valor"] for x in t["filas"]][-1] == "otros_lugares"
    assert all(not isinstance(v, int) or v not in ls[2:] for v in f)


def test_tabla_por_puesto_y_mesa(sesion):
    db = sesion.app.state.db
    p = _puestos(db)
    ya.personas(db, [{"votacion": _votacion(db, p["00-01"], 1 + i % 2)} for i in range(24)] +
                [{"votacion": _votacion(db, p["99-65"], 1)} for _ in range(10)] +
                [{"votacion": _votacion(db, p["00-01"], 1, eleccion="2022-congreso")} for _ in range(6)] +
                [{"votacion": {"donde": "otro_municipio", "eleccion": "x"}} for _ in range(5)] + [{} for _ in range(8)])
    t = ya.consulta(sesion, tipo="tabla", dimensiones=["puesto"])
    f = _filas(t)
    assert f[f"p{p['00-01']}"]["personas"] == 24 and f[f"p{p['99-65']}"]["personas"] == 10
    assert f["otra_eleccion"]["personas"] == 6 and f["otro_municipio"]["personas"] == 5
    assert f["sin_puesto"]["personas"] == 8 and f[f"p{p['00-01']}"]["etiqueta"].startswith("00-01 ")
    t2 = ya.consulta(sesion, tipo="tabla", dimensiones=["mesa"], filtros={"puesto_id": p["00-01"]})
    assert {x["etiqueta"]: x["personas"] for x in t2["filas"]} == {
        f"00-01 IE LUIS EDUARDO DIAZ SECCION PRIMARIA · mesa 1": 12,
        f"00-01 IE LUIS EDUARDO DIAZ SECCION PRIMARIA · mesa 2": 12, "Sin mesa": 6}


# ───────────────────────────── serie ─────────────────────────────

def test_serie_de_altas_y_de_acercamientos(sesion):
    db = sesion.app.state.db
    u = crear_usuario(db, "consultor")["_id"]
    lunes = HOY - timedelta(days=HOY.weekday() + 21)  # el lunes de hace tres semanas
    ids = ya.personas(db, [{"fuentes": ["manual"], "creado_por": {"uid": u},
                            "creado_en": ya.ts(lunes + timedelta(days=7 * (i % 3)))} for i in range(30)])
    ya.personas(db, [{"fuentes": ["tramites"], "creado_por": {"uid": 0}, "creado_en": ya.ts(lunes)} for _ in range(50)])
    for i in range(36):
        dia = lunes + timedelta(days=7 * (i % 2) + 1)
        ya.acercamiento(db, ids[i % 30], u, dia=dia, resultado=("contesto", "no_contactar", "no_contesto")[i % 3])
    ya.acercamiento(db, ids[0], u, dia=lunes + timedelta(days=1), auto=True, canal="reunion")
    ya.acercamiento(db, ids[1], u, dia=lunes + timedelta(days=1), anulado=True)
    desde, hasta = lunes.isoformat(), (lunes + timedelta(days=20)).isoformat()
    s = ya.consulta(sesion, tipo="serie", evento="altas", granularidad="semana", desde=desde, hasta=hasta)
    assert [p["valor"] for p in s["puntos"]] == [10, 10, 10] and s["tendencia"]["total_visible"] == 30
    assert s["tendencia"]["pendiente"] == 0.0 and "importaciones de bases no cuentan" in s["nota"]
    # Sin el automático de la reunión ni el anulado; efectivo = contestó (también el rechazo); útil, sin rechazos
    serie = lambda ev, **k: [p["valor"] for p in ya.consulta(  # noqa: E731
        sesion, tipo="serie", evento=ev, granularidad="semana", desde=desde, hasta=hasta, **k)["puntos"]]
    assert serie("acercamientos") == [18, 18, 0]
    assert serie("efectivos") == [12, 12, 0] and serie("contacto_util") == [6, 6, 0]
    d = ya.consulta(sesion, tipo="serie", evento="acercamientos", granularidad="semana", desde=desde, hasta=hasta,
                    desglose="resultado")
    assert {g["valor"] for g in d["grupos"]} == {"contesto", "no_contactar", "no_contesto"}
    assert d["puntos"][0]["grupos"] == {"contesto": 6, "no_contactar": 6, "no_contesto": 6}
    assert d["puntos"][2]["valor"] == 0


def test_serie_semanal_con_tendencia_y_proyeccion(sesion):
    db = sesion.app.state.db
    u = crear_usuario(db, "planillero")["_id"]
    lunes = HOY - timedelta(days=HOY.weekday() + 28)
    filas = []
    for semana, n in enumerate((10, 15, 20, 25)):
        filas += [{"fuentes": ["manual"], "creado_por": {"uid": u},
                   "creado_en": ya.ts(lunes + timedelta(days=7 * semana + 2))} for _ in range(n)]
    ya.personas(db, filas)
    s = ya.consulta(sesion, tipo="serie", evento="altas", granularidad="semana", desde=lunes.isoformat(),
                    hasta=(lunes + timedelta(days=27)).isoformat())
    t = s["tendencia"]
    assert [p["valor"] for p in s["puntos"]] == [10, 15, 20, 25]
    assert t["pendiente"] == 5.0 and t["proyeccion_siguiente"] == 30 and t["variacion_pct"] == 25.0
    assert t["mejor"]["valor"] == 25 and t["peor"]["valor"] == 10 and t["media"] == 17.5


def test_serie_de_reuniones_no_se_suprime_y_de_dia_pasa_a_semana_con_muchos_dias(sesion):
    db = sesion.app.state.db
    for i in range(3):
        db.reuniones.insert_one({"_id": 100 + i, "titulo": "Reunión inventada",
                                 "fecha": (HOY - timedelta(days=i)).isoformat()})
    s = ya.consulta(sesion, tipo="serie", evento="reuniones", granularidad="dia",
                    desde=(HOY - timedelta(days=6)).isoformat())
    assert sum(p["valor"] for p in s["puntos"]) == 3 and all(an.visible(p["valor"]) for p in s["puntos"])
    s = ya.consulta(sesion, tipo="serie", evento="reuniones", granularidad="dia",
                    desde=(HOY - timedelta(days=300)).isoformat())
    assert s["granularidad"] == "semana" and len(s["puntos"]) <= an.MAX_PUNTOS


# ───────────────────────────── embudo ─────────────────────────────

def test_embudo_anidado_con_mayor_caida(sesion):
    db = sesion.app.state.db
    p = _puestos(db)["00-01"]
    filas = []
    for i in range(100):
        f = {"telefono": str(3_002_000_000 + i) if i < 80 else None}
        if i < 60:
            f.update(consentimiento="si", contacto_habilitado=i < 50)
        if i < 40:
            f["abordaje"] = {"n": 1, "efectivos": 1 if i < 30 else 0, "estado": "contactado" if i < 30 else "intentado"}
        if i < 20:
            f["votacion"] = _votacion(db, p, 1, "verificado" if i < 10 else "sin_verificar")
        filas.append(f)
    ids = ya.personas(db, filas)
    u = crear_usuario(db, "consultor")["_id"]
    for pid in ids[:25]:
        ya.acercamiento(db, pid, u, dia=HOY - timedelta(days=3))
    for pid in ids[25:30]:
        ya.acercamiento(db, pid, u, dia=HOY - timedelta(days=3), resultado="no_contactar")
    e = ya.consulta(sesion, tipo="embudo")
    etapas = {x["etapa"]: x for x in e["etapas"]}
    assert [etapas[k]["personas"] for k in ("personas", "telefono", "autorizadas", "habilitadas", "abordadas",
                                            "contactadas", "utiles", "puesto_mesa", "verificadas")] == \
        [100, 80, 60, 50, 40, 30, 25, 20, 10]
    assert etapas["abordadas"]["tasa_desde_anterior"] == 80.0 and etapas["verificadas"]["tasa_desde_anterior"] == 50.0
    assert e["mayor_caida"]["hasta"] == "verificadas" and e["mayor_caida"]["accion"]
    assert e["aparte"]["rechazos"] == 0


def test_embudo_oculta_una_etapa_que_dejaria_ver_a_pocas(sesion):
    db = sesion.app.state.db
    ya.personas(db, [{"telefono": str(3_003_000_000 + i) if i < 97 else None} for i in range(100)])
    etapas = {x["etapa"]: x for x in ya.consulta(sesion, tipo="embudo")["etapas"]}
    assert etapas["telefono"]["personas"] == an.OCULTA  # 3 sin teléfono
    assert etapas["autorizadas"]["personas"] == 0 and "tasa_desde_anterior" not in etapas["autorizadas"]


# ───────────────────────────── cobertura y ritmo ─────────────────────────────

def test_cobertura_por_puesto_frente_al_censo(sesion):
    db = sesion.app.state.db
    p = _puestos(db)
    ya.personas(db, [{"sexo": "F" if i < 18 else "M", "votacion": _votacion(db, p["00-01"], 1 + i % 3,
                                                                            "verificado" if i < 6 else "sin_verificar")}
                     for i in range(30)] +
                [{"votacion": _votacion(db, p["99-65"], None)} for _ in range(10)] +
                [{"votacion": {"donde": "no_inscrito", "eleccion": "2026-presidencial"}} for _ in range(6)] +
                [{} for _ in range(9)])
    c = ya.consulta(sesion, tipo="cobertura", meta_pct=30)
    fila = next(x for x in c["puestos"] if x["codigo"] == "00-01")
    assert fila["registrados"] == 30 and fila["cobertura_pct"] == round(100 * 30 / 12164, 1)
    assert fila["mujeres"] == 18 and fila["hombres"] == 12 and fila["verificados"] == 6 and fila["con_mesa"] == 30
    assert fila["meta"] == math.ceil(0.3 * 12164) and fila["faltan_para_meta"] == fila["meta"] - 30
    assert fila["estimacion_habilitados_por_mesa"] == round(12164 / 35) and fila["mesas_sobre_estimacion"] == 0
    rural = next(x for x in c["puestos"] if x["codigo"] == "99-65")
    assert rural["registrados"] == 10 and rural["con_mesa"] == 0
    cero = next(x for x in c["puestos"] if x["codigo"] == "99-25")
    assert cero["registrados"] == 0 and cero["cobertura_pct"] == 0.0
    assert c["casillas"] == {"no_inscrito": 6, "sin_puesto": 9}


def test_ritmo_proyecta_la_cobertura_a_la_fecha_meta(sesion):
    db = sesion.app.state.db
    p = _puestos(db)["99-65"]  # 1578 habilitados
    viejos = [{"votacion": _votacion(db, p, 1), "creado_en": ya.ts(HOY - timedelta(days=200))} for _ in range(24)]
    nuevos = [{"votacion": _votacion(db, p, 1), "creado_en": ya.ts(HOY - timedelta(days=200)),
               "avance": {"puesto": {"uid": 0, "ts": ya.ts(HOY - timedelta(days=10 + i))}}} for i in range(16)]
    ya.personas(db, viejos + nuevos)
    meta = (HOY + timedelta(days=70)).isoformat()
    r = ya.consulta(sesion, tipo="ritmo", fecha_meta=meta, meta_pct=10, semanas=8)
    fila = next(x for x in r["puestos"] if x["puesto_id"] == p)
    assert fila["registrados"] == 40 and fila["nuevos_en_ventana"] == 16 and fila["ritmo_semanal"] == 2.0
    assert fila["proyeccion"] == 60 and fila["meta"] == math.ceil(157.8) and fila["llega"] is False
    assert fila["faltan"] == 158 - 40 and fila["necesarias_por_semana"] == round(118 / 10, 1)
    assert r["mayor_brecha"]["codigo"] in {x["codigo"] for x in r["puestos"]}
    estado, detalle = ya.error(sesion, {"tipo": "ritmo", "fecha_meta": HOY.isoformat()})
    assert estado == 422 and "posterior" in detalle["mensaje"]


# ───────────────────────────── brechas ─────────────────────────────

def test_brechas_ordena_del_mas_desatendido(sesion):
    db = sesion.app.state.db
    a, b = ya.lugares(db, 2)
    u = crear_usuario(db, "consultor")["_id"]
    atendidos = ya.personas(db, [{"lugar_id": a, "telefono": str(3_004_000_000 + i), "consentimiento": "si",
                                  "contacto_habilitado": True, "abordaje": {"n": 1, "efectivos": 1},
                                  "ultimo_contacto": (HOY - timedelta(days=5)).isoformat()} for i in range(15)])
    ya.personas(db, [{"lugar_id": b} for _ in range(15)])
    for pid in atendidos:
        ya.acercamiento(db, pid, u, dia=HOY - timedelta(days=5))
    db.reuniones.insert_many([{"_id": 200 + i, "titulo": "Reunión inventada", "lugar_id": a,
                               "fecha": (HOY - timedelta(days=10 + i)).isoformat()} for i in range(2)])
    br = ya.consulta(sesion, tipo="brechas", dias=30)
    primero, segundo = br["lugares"]
    assert primero["lugar_id"] == b and primero["indice_atencion"] == 0
    assert segundo["lugar_id"] == a and segundo["indice_atencion"] == 100
    assert segundo["reuniones_en_ventana"] == 2 and segundo["pct_contacto_util_en_ventana"] == 100.0
    assert segundo["mediana_dias_desde_ultimo_contacto"] == 5 and primero["sin_ningun_contacto"] == 15


# ───────────────────────────── equipo ─────────────────────────────

def test_equipo_cuenta_contactos_utiles_rechazos_y_la_mediana(sesion):
    db = sesion.app.state.db
    u1, u2 = crear_usuario(db, "consultor"), crear_usuario(db, "consultor")
    ids = ya.personas(db, [{} for _ in range(20)])
    no = ya.persona(db, consentimiento="no")
    for i, r in enumerate(["contesto"] * 8 + ["no_contactar"] * 2 + ["no_contesto"] * 2):
        ya.acercamiento(db, ids[i], u1["_id"], dia=HOY - timedelta(days=2), resultado=r, fuera=i < 3)
    ya.acercamiento(db, ids[0], u1["_id"], dia=HOY - timedelta(days=2), auto=True, canal="reunion")
    ya.acercamiento(db, ids[0], u1["_id"], dia=HOY - timedelta(days=2), anulado=True)
    ya.acercamiento(db, no, u1["_id"], dia=HOY - timedelta(days=2))
    ya.acercamiento(db, None, u1["_id"], dia=HOY - timedelta(days=2))  # anonimizado por una supresión: cuenta
    for i in range(10):
        ya.acercamiento(db, ids[i], u2["_id"], dia=HOY - timedelta(days=1), resultado="no_contesto")
    e = ya.consulta(sesion, tipo="equipo")
    filas = {f["usuario"]: f for f in e["usuarios"]}
    x = filas[u1["usuario"]]
    assert (x["acercamientos"], x["efectivos"], x["contactos_utiles"], x["rechazos"]) == (13, 11, 9, 2)
    assert x["tasa_contacto_util"] == round(100 * 9 / 13, 1) and x["pct_fuera_de_horario"] == round(300 / 13, 1)
    assert filas[u2["usuario"]]["tasa_contacto_util"] == 0.0 and filas[u2["usuario"]]["contactos_utiles"] == 0
    assert e["mediana_del_equipo"]["acercamientos"] == 11.5
    assert x["frente_a_mediana"]["acercamientos"] == round(100 * (13 - 11.5) / 11.5)
    assert "sesiones" not in json.dumps(e) and "ip" not in {k for f in e["usuarios"] for k in f}


# ───────────────────────────── calidad ─────────────────────────────

def test_calidad_de_la_base(sesion):
    db = sesion.app.state.db
    ids = ya.personas(db, [{"cedula": str(83_000_000 + i) if i < 20 else None,
                            "consentimiento": "si" if i < 12 else "pendiente", "contacto_habilitado": i < 5,
                            "lugar_texto": "UN SITIO INVENTADO" if i >= 34 else None} for i in range(40)])
    db.coincidencias.insert_many([{"_id": 300 + i, "persona_id": ids[20 + i], "candidato_id": ids[30 + i],
                                   "estado": "pendiente", "puntaje": 90} for i in range(3)])
    db.conflictos_cedula.insert_many([{"_id": 300 + i, "clave": f"c{i}", "persona_id": ids[i],
                                       "motivo": "posible_digitacion", "estado": "pendiente"} for i in range(6)])
    db.solicitudes.insert_many([{"_id": 300 + i, "persona_id": ids[i], "tipo": "consulta", "estado": "pendiente",
                                 "vence": (HOY - timedelta(days=1 if i < 5 else -5)).isoformat()} for i in range(8)])
    ya.persona(db, situacion={"estado": "fallecida", "confirmada": False})
    c = ya.consulta(sesion, tipo="calidad")
    faltan = {x["campo"]: x for x in c["faltan"]}
    assert faltan["cedula"]["personas"] == 20 and faltan["cedula"]["pct"] == 50.0
    assert c["indicadores"]["autorizaciones_por_confirmar"]["personas"] == 7
    assert c["indicadores"]["lugar_escrito_sin_reconocer"]["personas"] == 6
    assert c["coincidencias_pendientes_personas"] == 6
    assert c["conflictos_cedula_pendientes"] == {"posible_digitacion": 6}
    assert c["solicitudes"]["abiertas"] == {"consulta": 8} and c["solicitudes"]["vencidas"] == {"consulta": 5}
    assert c["situaciones_sin_confirmar"] == an.MENOS
    z = ya.consulta(sesion, tipo="calidad", dimensiones=["zona"])
    assert z["por_zona"][0]["zona"] == "sin" and z["por_zona"][0]["personas"] == 40


# ───────────────────────────── anomalías ─────────────────────────────

def test_anomalias_picos_telefonos_compartidos_y_duplicados(sesion):
    db = sesion.app.state.db
    u, importador = crear_usuario(db, "planillero"), crear_usuario(db, "planillero")
    ids = ya.personas(db, [{} for _ in range(40)])
    for k in range(30):  # una alta por día...
        ya.alta_en_panel(db, ids[k], u["_id"], HOY - timedelta(days=k + 1))
    pico = ya.personas(db, [{} for _ in range(15)])
    for pid in pico:  # ...y un día con 15
        ya.alta_en_panel(db, pid, u["_id"], HOY - timedelta(days=40))
    # Una importación de planilla: no es un pico (sus altas llevan `capturado_por`)
    for pid in ya.personas(db, [{} for _ in range(30)]):
        db.auditoria.insert_one({"ts": ya.ts(HOY - timedelta(days=20)), "accion": "crear", "entidad": "persona",
                                 "entidad_id": pid, "uid": importador["_id"], "capturado_por": None})
    compartido = "3005550000"
    for pid in ids[:5]:
        db.personas.update_one({"_id": pid}, {"$set": {"telefonos": [{"numero": compartido, "estado": "confirmado"}]}})
    unidas = ya.personas(db, [{"fuentes": ["manual"], "creado_por": {"uid": u["_id"]},
                               "creado_en": ya.ts(HOY - timedelta(days=5))} for _ in range(3)])
    db.personas.update_many({"_id": {"$in": unidas}}, {"$set": {"fusionada_en": ids[0]}})
    a = ya.consulta(sesion, tipo="anomalias")
    picos = [p for p in a["picos"] if p["tipo"] == "altas"]
    assert [p["usuario"] for p in picos] == [u["usuario"]] and picos[0]["dias"][0]["cantidad"] == 15
    assert importador["usuario"] not in json.dumps(a["picos"])
    assert a["telefonos_compartidos"] == {"grupos_de_mas_de_3_fichas": 1, "fichas": 5}
    assert a["altas_luego_unidas_como_duplicadas"] == [{"usuario": u["usuario"], "uid": u["_id"], "unidas": 3}]
    assert compartido not in json.dumps(a)


# ───────────────────────────── cohortes ─────────────────────────────

def test_cohortes_por_mes_de_alta(sesion):
    db = sesion.app.state.db
    u = crear_usuario(db, "planillero")["_id"]
    mes = (HOY.replace(day=1) - timedelta(days=70)).replace(day=1)
    ids = ya.personas(db, [{"fuentes": ["manual"], "creado_por": {"uid": u},
                            "creado_en": ya.ts(mes + timedelta(days=2)),
                            "consentimiento": "si" if i < 10 else "pendiente", "cedula": str(84_000_000 + i)}
                           for i in range(20)])
    ya.personas(db, [{"fuentes": ["tramites"], "creado_por": {"uid": 0}, "creado_en": ya.ts(mes)} for _ in range(30)])
    for i, pid in enumerate(ids[:10]):
        ya.acercamiento(db, pid, u, dia=mes + timedelta(days=2 + (10 if i < 5 else 60)))
    c = ya.consulta(sesion, tipo="cohortes", desde=mes.isoformat())
    fila = next(x for x in c["cohortes"] if x["mes"] == mes.strftime("%Y-%m"))
    assert fila["personas"] == 20 and fila["pct_abordadas_en_30_dias"] == 25.0
    assert fila["pct_autorizadas"] == 50.0 and fila["pct_con_cedula"] == 100.0 and "en_curso" not in fila
    assert all(x["mes"] != "importacion" for x in c["cohortes"])


# ───────────────────────────── franjas e intentos ─────────────────────────────

def test_franjas_horarias_y_horario_configurado(sesion):
    db = sesion.app.state.db
    u = crear_usuario(db, "consultor")["_id"]
    ids = ya.personas(db, [{} for _ in range(40)])
    dia = HOY - timedelta(days=HOY.weekday() + 7)  # un lunes: horario de 7 a 19
    for i, pid in enumerate(ids[:20]):
        ya.acercamiento(db, pid, u, dia=dia, hora=9, resultado="contesto" if i < 15 else "no_contesto")
    for i, pid in enumerate(ids[20:]):
        ya.acercamiento(db, pid, u, dia=dia, hora=20, resultado="contesto" if i < 2 else "buzon")
    f = ya.consulta(sesion, tipo="franjas", desglose="usuario")
    horas = {h["hora"]: h for h in f["por_hora"]}
    assert horas[9]["tasa_util"] == 75.0 and horas[20]["tasa_util"] == 10.0
    assert f["mejores_horas"][0] == 9 and f["peores_horas"][0] == 20
    assert f["horario_configurado"]["dentro"]["intentos"] == 20 and f["horario_configurado"]["fuera"]["intentos"] == 20
    assert f["por_dia"][0]["dia"] == "lunes" and f["por_usuario"][0]["intentos"] == 40


def test_intentos_recomienda_cuando_dejar_de_insistir(sesion):
    db = sesion.app.state.db
    u = crear_usuario(db, "consultor")["_id"]
    ids = ya.personas(db, [{} for _ in range(100)])
    inicio = HOY - timedelta(days=60)
    for i, pid in enumerate(ids):
        # 40 contestan al 1.º, 30 al 2.º, 1 al 3.º y 29 nunca (4 intentos)
        intentos = 1 if i < 40 else 2 if i < 70 else 3 if i < 71 else 4
        for k in range(intentos):
            ok = k == intentos - 1 and i < 71
            ya.acercamiento(db, pid, u, dia=inicio + timedelta(days=3 * k),
                            resultado="contesto" if ok else "no_contesto")
    r = ya.consulta(sesion, tipo="intentos")
    filas = {x["intento"]: x for x in r["intentos"]}
    assert filas[1]["personas_que_llegaron"] == 100 and filas[1]["prob_contacto"] == 40.0
    assert filas[2]["prob_contacto"] == 50.0 and filas[3]["prob_contacto"] == round(100 / 30, 1)
    assert filas[2]["contactadas_acumulado_pct"] == 70.0
    assert r["recomendacion"]["max_intentos_sin_exito"] == 2 and r["recomendacion"]["dias_entre_intentos"] == 2
    assert r["recomendacion"]["actual_max_intentos_sin_exito"] == 4


# ───────────────────────────── captura ─────────────────────────────

def test_captura_por_quien_capturo(sesion):
    db = sesion.app.state.db
    p1, p2, p3 = (crear_usuario(db, "planillero") for _ in range(3))
    malo = [{"numero": "3006660000", "estado": "equivocado"}]
    ya.personas(db, [{"fuentes": ["planilla"], "creado_por": {"uid": 0, "capturado_por": p1["_id"]},
                      "telefonos": malo if i < 6 else []} for i in range(12)])
    ya.personas(db, [{"fuentes": ["manual"], "creado_por": {"uid": p2["_id"]}, "consentimiento": "si"}
                     for _ in range(12)])
    ya.personas(db, [{"fuentes": ["manual"], "creado_por": {"uid": p3["_id"]}} for _ in range(4)])
    c = ya.consulta(sesion, tipo="captura")
    filas = {f["usuario"]: f for f in c["capturadores"]}
    assert set(filas) == {p1["usuario"], p2["usuario"]} and c["capturadores_con_menos_de_10_fichas"] == 1
    assert filas[p1["usuario"]]["pct_telefono_equivocado"] == 50.0 and filas[p2["usuario"]]["pct_sin_autorizacion"] == 0
    assert filas[p1["usuario"]]["frente_a_mediana"]["pct_telefono_equivocado"] == 25.0


# ───────────────────────────── comparar ─────────────────────────────

def test_comparar_conteos_y_tasa_con_efecto_mezcla_y_tasa(sesion):
    db = sesion.app.state.db
    u = crear_usuario(db, "consultor")["_id"]
    ids = ya.personas(db, [{} for _ in range(30)])
    ref, per = HOY - timedelta(days=40), HOY - timedelta(days=10)
    # Referencia: 40 llamadas (20 útiles) y 10 WhatsApp (8 útiles); periodo: 20 llamadas (10 útiles), 30 WhatsApp (12)
    for canal, n, utiles, dia in (("llamada", 40, 20, ref), ("whatsapp", 10, 8, ref), ("llamada", 20, 10, per),
                                  ("whatsapp", 30, 12, per)):
        for i in range(n):
            ya.acercamiento(db, ids[i % 30], u, dia=dia, canal=canal, resultado="contesto" if i < utiles else "buzon")
    q = dict(desde=(HOY - timedelta(days=20)).isoformat(), hasta=HOY.isoformat(),
             referencia_desde=(HOY - timedelta(days=50)).isoformat(),
             referencia_hasta=(HOY - timedelta(days=30)).isoformat())
    c = ya.consulta(sesion, tipo="comparar", metrica="acercamientos", dimensiones=["canal"], **q)
    assert c["total"] == {"referencia": 50, "periodo": 50, "cambio": 0, "cambio_pct": 0.0}
    g = {x["valor"]: x for x in c["grupos"]}
    assert g["llamada"]["cambio"] == -20 and g["whatsapp"]["cambio"] == 20
    t = ya.consulta(sesion, tipo="comparar", metrica="tasa_contacto_util", dimensiones=["canal"], **q)
    tot = t["total"]
    assert tot["referencia"]["tasa_util"] == 56.0 and tot["periodo"]["tasa_util"] == 44.0 and tot["cambio_pp"] == -12.0
    assert abs(tot["efecto_mezcla_pp"] + tot["efecto_tasa_pp"] - tot["cambio_pp"]) < 0.2
    assert "descenso" in t["explicacion"] and "WhatsApp" in t["explicacion"]


# ───────────────────────────── efecto de las reuniones ─────────────────────────────

def test_reuniones_efecto_antes_y_despues(sesion):
    db = sesion.app.state.db
    lid = ya.lugares(db, 1)[0]
    u = crear_usuario(db, "planillero")["_id"]
    fecha = HOY - timedelta(days=60)
    db.reuniones.insert_one({"_id": 400, "titulo": "Reunión inventada 3001234567", "fecha": fecha.isoformat(),
                             "lugar_id": lid})
    ya.personas(db, [{"lugar_id": lid} for _ in range(20)])
    ya.personas(db, [{"lugar_id": lid, "fuentes": ["manual"], "creado_por": {"uid": u},
                      "creado_en": ya.ts(fecha + timedelta(days=(-10 if i < 5 else 3)))} for i in range(17)])
    r = ya.consulta(sesion, tipo="reuniones_efecto")
    assert r["reuniones_consideradas"] == 1 and r["agregado"]["altas"] == {"antes": 5, "despues": 12,
                                                                          "cambio_pct": 140.0}
    assert "no prueba" in r["advertencia"] and r["reuniones"][0]["personas_del_lugar"] == 37


# ───────────────────────────── diagnóstico ─────────────────────────────

def test_diagnostico_hallazgos_con_evidencia_accion_y_enlaces_validos(sesion):
    db = sesion.app.state.db
    u = crear_usuario(db, "consultor")["_id"]
    filas = []
    for i in range(120):
        f = {"telefono": str(3_007_000_000 + i), "cedula": str(85_000_000 + i) if i < 30 else None}
        if i < 50:
            f.update(consentimiento="si", contacto_habilitado=i >= 20)  # 20 por confirmar, 30 habilitadas
        filas.append(f)
    ids = ya.personas(db, filas)
    ya.persona(db, consentimiento="no", telefono="3007999999")
    db.solicitudes.insert_one({"_id": 500, "persona_id": ids[0], "tipo": "supresion", "estado": "pendiente",
                               "vence": (HOY - timedelta(days=2)).isoformat()})
    for pid in ids[20:25]:
        ya.acercamiento(db, pid, u, dia=HOY - timedelta(days=1))
        db.personas.update_one({"_id": pid}, {"$set": {"abordaje": {"n": 1, "efectivos": 1, "estado": "contactado"}}})
    d = ya.consulta(sesion, tipo="diagnostico")
    hs = d["hallazgos"]
    ids_h = [h["id"] for h in hs]
    assert ids_h[0] == "solicitudes_vencidas" and hs[0]["severidad"] == "alta"
    assert {"autorizaciones_por_confirmar", "habilitadas_sin_abordar", "faltan_cedula"} <= set(ids_h)
    orden = [an.SEVERIDADES[h["severidad"]] for h in hs]
    assert orden == sorted(orden)
    for h in hs:
        assert {"id", "severidad", "titulo", "evidencia", "por_que", "accion"} <= set(h)
        assert h["accion"] and h["por_que"]
    por_confirmar = next(h for h in hs if h["id"] == "autorizaciones_por_confirmar")
    assert por_confirmar["evidencia"]["personas"] == 20 and por_confirmar["severidad"] == "alta"
    # Cada enlace a Habitantes: solo filtros que la vista lee y la cifra que abre (sin quienes no autorizaron)
    enlaces = [h["enlace"] for h in hs if h.get("enlace", {}).get("ruta", "").startswith("/personas?")]
    assert enlaces
    for e in enlaces:
        params = dict(parse_qsl(urlsplit(e["ruta"]).query))
        assert set(params) <= an.ENLAZABLES and params["situacion"] == "vigentes"
        total = sesion.get("/api/personas", params={**params, "tratables": "1"}).json()["total"]
        assert e["personas"] == an.celda(total), e
    sin_abordar = next(h for h in hs if h["id"] == "habilitadas_sin_abordar")
    assert sin_abordar["evidencia"]["personas"] == 25 and sin_abordar["severidad"] == "alta"
    # Habitantes no filtra por contacto habilitado: la lista trae también las 20 por confirmar, y lo dice
    assert sin_abordar["enlace"]["personas"] == 45 and "por confirmar" in sin_abordar["enlace"]["nota"]
    assert "abordaje_estado=sin_abordar" in sin_abordar["enlace"]["ruta"]
    assert "nota_enlaces" in d and d["revisado"]
    # Con un filtro, los enlaces lo llevan
    dz = ya.consulta(sesion, tipo="diagnostico", filtros={"con_cedula": True})
    for h in dz["hallazgos"]:
        if h.get("enlace", {}).get("ruta", "").startswith("/personas?"):
            assert "con_cedula=1" in h["enlace"]["ruta"]


def test_diagnostico_con_fecha_meta_avisa_los_puestos_que_no_llegan(sesion):
    db = sesion.app.state.db
    p = _puestos(db)["99-65"]
    ya.personas(db, [{"votacion": _votacion(db, p, 1), "creado_en": ya.ts(HOY - timedelta(days=300))}
                     for _ in range(30)])
    d = ya.consulta(sesion, tipo="diagnostico", fecha_meta=(HOY + timedelta(days=60)).isoformat(), meta_pct=20)
    h = next(x for x in d["hallazgos"] if x["id"] == "ritmo_insuficiente")
    assert h["severidad"] == "alta" and any(x["codigo"] == "99-65" for x in h["evidencia"]["puestos_que_no_llegan"])
    # La acción y el enlace son del puesto con la mayor brecha (00-01: el de más habilitados, sin nadie registrado)
    assert "00-01" in h["accion"] and f"puesto_id={_puestos(db)['00-01']}" in h["enlace"]["ruta"]


def test_enlazables_son_filtros_de_habitantes_y_de_la_api():
    texto = (RAIZ / "web" / "js" / "vistas" / "personas.js").read_text(encoding="utf-8")
    bloque = re.search(r"const FILTROS = \[(.*?)\];", texto, re.S).group(1)
    nombres = set(re.findall(r"'([a-z_]+)'", bloque.split("...")[0]))
    sin = re.search(r"\.\.\.\[(.*?)\]\.map", bloque, re.S).group(1)
    nombres |= {f"sin_{x}" for x in re.findall(r"'([a-z_]+)'", sin)}
    assert an.ENLAZABLES <= nombres, an.ENLAZABLES - nombres
    assert an.ENLAZABLES <= set(fapi.Filtros.model_fields), an.ENLAZABLES - set(fapi.Filtros.model_fields)
    assert "sin_puesto_mesa" not in an.ENLAZABLES and "tratables" not in an.ENLAZABLES


def test_catalogo(sesion):
    c = sesion.get("/api/analitica/catalogo").json()
    assert set(c["tipos"]) == set(an.TIPOS) and c["tipos"]["ritmo"]["obligatorios"] == ["fecha_meta"]
    assert "lider" not in c["dimensiones"]["personas"] and "regimen_salud" not in c["filtros"]
    assert {"q", "lista", "reunion_id", "creado_por", "ids"}.isdisjoint(c["filtros"])
    assert c["limites"]["minimo_poblacion"] == 10 and len(c["puestos"]) == 7


def test_salida_recortada_a_40000_caracteres():
    filas = [{"valor": i, "etiqueta": "x" * 200} for i in range(400)]
    out = an.ajustar({"tipo": "tabla", "filas": filas})
    assert len(json.dumps(out, ensure_ascii=False)) <= an.MAX_CARACTERES and out["recortado"] is True


# ───────────────────────────── Rendimiento ─────────────────────────────

def test_rendimiento_con_3000_personas(sesion):
    db = sesion.app.state.db
    uids = [crear_usuario(db, r)["_id"] for r in ("planillero", "consultor", "consultor", "planillero")]
    ya.base_variada(db, 3000, 9, HOY, uids)
    assert db.acercamientos.count_documents({}) > 800
    tiempos = {}
    consultas = [{"tipo": "tabla", "dimensiones": ["lugar", "sexo"], "metricas": ["personas", "pct"]},
                 {"tipo": "tabla", "dimensiones": ["lugar"], "metricas": ["personas", "pct_con_cedula", "pct_asistio"]},
                 {"tipo": "serie", "evento": "acercamientos", "desglose": "canal"}, {"tipo": "embudo"},
                 {"tipo": "cobertura"}, {"tipo": "brechas"}, {"tipo": "equipo"}, {"tipo": "calidad"},
                 {"tipo": "anomalias"}, {"tipo": "cohortes"}, {"tipo": "franjas"}, {"tipo": "intentos"},
                 {"tipo": "captura"}, {"tipo": "comparar", "metrica": "tasa_contacto_util", "dimensiones": ["canal"]},
                 {"tipo": "reuniones_efecto"},
                 {"tipo": "ritmo", "fecha_meta": (HOY + timedelta(days=100)).isoformat()},
                 {"tipo": "diagnostico", "fecha_meta": (HOY + timedelta(days=100)).isoformat()}]
    for c in consultas:
        t0 = time.perf_counter()
        out = ya.consulta(sesion, **c)
        tiempos[c["tipo"]] = time.perf_counter() - t0
        assert not out.get("pocas") and len(json.dumps(out, ensure_ascii=False)) <= an.MAX_CARACTERES
    assert max(tiempos.values()) < 15, tiempos
    assert tiempos["diagnostico"] < 15 and sum(tiempos.values()) < 60, tiempos
