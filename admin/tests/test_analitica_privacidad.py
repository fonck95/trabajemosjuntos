"""Privacidad de la analítica avanzada (`app/analitica.py`, `/api/analitica`): lo que no se puede saber de los
habitantes por los agregados.

* Quien no autorizó (con sus llamadas, autorizaciones, asistencias, altas, conflictos, solicitudes, duplicados) no
  cambia ninguna salida de ningún tipo de análisis.
* Las bases políticas (personas solo de «general» o «cedulas») no se deducen: ni la fuente (multietiqueta, sin resto
  ni total), ni quién importó, ni las altas, los picos o las cohortes cambian con ellas, salvo la casilla
  «importación» y el total.
* Una población de menos de 10 responde exactamente `{pocas, personas: "<10"}`; una celda de 1 a 4 sale «<5»; un % se
  oculta si su numerador o su complemento es de 1 a 4; ninguna celda oculta se reconstruye con los márgenes
  (comprobado a fuerza bruta, en tablas de una y dos dimensiones y en tablas al azar).
* Planilleros y consultores reciben 403; los filtros fuera de la lista blanca, 422 (403 la etiqueta sensible).

Solo datos inventados."""
from __future__ import annotations

import itertools
import json
import random
from datetime import timedelta

import pytest

import ayudas_analitica as ya
from app import analitica as an
from app import db as bd
from app import modelo
from conftest import crear_usuario

HOY = modelo.hoy_local()
POCAS = {"pocas": True, "personas": "<10"}


# ───────────────────────────── Reconstrucción a fuerza bruta ─────────────────────────────

def _dominio(v, tope: int) -> range:
    """Lo que alguien que conoce la regla sabe de una celda publicada."""
    if v == an.MENOS:
        return range(1, 5)
    if v == an.OCULTA:
        return range(5, max(5, tope) + 1)
    return range(v, v + 1)


def _posibles_1d(publicado: dict, total: int) -> dict:
    """Para cada celda, los valores que puede tener sabiendo el total y lo publicado."""
    claves = list(publicado)
    doms = [_dominio(publicado[k], total) for k in claves]
    vistos = {k: set() for k in claves}
    for combo in itertools.product(*doms):
        if sum(combo) == total:
            for k, v in zip(claves, combo):
                vistos[k].add(v)
    return vistos


def _ok_total(t_real: int, suma: int) -> bool:
    return 1 <= suma <= 4 if 0 < t_real < 5 else suma == t_real


def _posibles_2d(publicado: dict, filas: list, columnas: list, tot_f: dict, tot_c: dict) -> dict:
    """Lo mismo con dos dimensiones: los totales de fila y de columna se conocen (salvo los de 1 a 4, que salen
    «<5» en la tabla de una dimensión: entonces se sabe que están entre 1 y 4). Fila por fila: primero las
    combinaciones de cada fila que cumplen su total, después las que cumplen las columnas."""
    ocultas = [k for k in publicado if not an.visible(publicado[k])]
    vistos = {k: set() for k in ocultas}
    por_fila = []
    for f in filas:
        hs = [(f, c) for c in columnas if (f, c) in vistos]
        fijo = sum(publicado[(f, c)] for c in columnas if (f, c) not in vistos)
        doms = [_dominio(publicado[k], min(tot_f[k[0]], tot_c[k[1]])) for k in hs]
        por_fila.append([dict(zip(hs, combo)) for combo in itertools.product(*doms)
                         if _ok_total(tot_f[f], fijo + sum(combo))])
    for eleccion in itertools.product(*por_fila):
        valor = {k: v for d in eleccion for k, v in d.items()}
        if all(_ok_total(tot_c[c], sum(valor.get((f, c), publicado[(f, c)]) if (f, c) in valor
                                       else publicado[(f, c)] for f in filas)) for c in columnas):
            for k, v in valor.items():
                vistos[k].add(v)
    return vistos


@pytest.mark.parametrize("valores", [
    {"a": 1, "b": 5, "c": 30},          # 1 + 5 = 6: sin un segundo complemento, el 1 se deduciría
    {"a": 3, "b": 40},
    {"a": 4, "b": 4, "c": 4},           # todas primarias: 12 entre tres «<5» se deduce (4, 4, 4): no se publica
    {"a": 1, "b": 1, "c": 50, "d": 60},  # 1 + 1 = 2 se deduce: hace falta un complemento
    {"a": 2, "b": 0, "c": 0, "d": 20},
    {"a": 0, "b": 12, "c": 30},
])
def test_ninguna_celda_oculta_se_reconstruye_con_el_total(valores):
    publicado = an.proteger(valores)
    if valores == {"a": 4, "b": 4, "c": 4}:  # sin celdas que ocultar: el desglose no se publica
        assert publicado is None
        return
    assert all(publicado[k] == an.MENOS for k, v in valores.items() if 0 < v < 5)
    assert all(publicado[k] == v for k, v in valores.items() if v == 0)
    posibles = _posibles_1d(publicado, sum(valores.values()))
    for k, v in publicado.items():
        if v == an.MENOS:
            assert len(posibles[k]) >= 2, (valores, publicado, k, posibles[k])
        assert valores[k] in posibles[k]


def _justificado(m: dict, sumas_f: dict, sumas_c: dict, total: int) -> bool:
    """Un desglose que no se publica (None) es porque ni ocultando todas las celdas de 5 o más se protege."""
    todo = {k for k, n in m.items() if n > 0}
    return bool(an.fijadas(m, todo, sumas_f, sumas_c, (total, total)) & {k for k, n in m.items() if 0 < n < 5})


def test_proteger_al_azar_no_deja_deducir_ninguna_celda():
    rnd = random.Random(7)
    probadas = 0
    for _ in range(1500):
        valores = {i: rnd.choice((0, 1, 2, 3, 4, 5, 6, 7, 9, 12, 20)) for i in range(rnd.randint(2, 6))}
        publicado = an.proteger(valores)
        total = sum(valores.values())
        if publicado is None:
            m = {("_", k): n for k, n in valores.items()}
            assert _justificado(m, {"_": (total, total)}, {}, total), valores
            continue
        if sum(1 for v in publicado.values() if not an.visible(v)) > 5:
            continue  # la fuerza bruta se vuelve lenta
        probadas += 1
        posibles = _posibles_1d(publicado, total)
        for k, v in publicado.items():
            assert valores[k] in posibles[k]
            if v == an.MENOS:  # una complementaria («oculta», de 5 o más) sí puede deducirse
                assert len(posibles[k]) >= 2, (valores, publicado, k)
    assert probadas > 800


def test_proteger_2d_al_azar_no_se_reconstruye_con_los_margenes():
    """Tablas al azar de 2x2 a 3x4 con muchas celdas chicas: ninguna oculta se deduce con los totales de filas,
    columnas y el general (comprobado enumerando todas las tablas compatibles con lo publicado)."""
    rnd = random.Random(11)
    probadas = 0
    for _ in range(500):
        filas = [f"r{i}" for i in range(rnd.randint(2, 3))]
        columnas = [f"c{i}" for i in range(rnd.randint(2, 4))]
        m = {(f, c): rnd.choice((0, 0, 1, 2, 3, 4, 5, 6, 8, 9, 14)) for f in filas for c in columnas}
        tot_f = {f: sum(m[(f, c)] for c in columnas) for f in filas}
        tot_c = {c: sum(m[(f, c)] for f in filas) for c in columnas}
        publicado = an.proteger_2d(m, filas, columnas)
        if publicado is None:
            assert _justificado(m, {f: an._suma_conocida(n) for f, n in tot_f.items()},
                                {c: an._suma_conocida(n) for c, n in tot_c.items()}, sum(m.values())), m
            continue
        assert all(publicado[k] == an.MENOS for k, v in m.items() if 0 < v < 5)
        ocultas = [k for k, v in publicado.items() if not an.visible(v)]
        if len(ocultas) > 6:
            continue  # la fuerza bruta se vuelve lenta
        probadas += 1
        posibles = _posibles_2d(publicado, filas, columnas, tot_f, tot_c)
        for k in ocultas:
            assert m[k] in posibles[k]
            if publicado[k] == an.MENOS:
                assert len(posibles[k]) >= 2, (m, publicado, k, posibles[k])
    assert probadas > 150


def test_pct_y_atributo_se_ocultan_con_pocas_personas():
    assert an.pct(2, 40) is None and an.pct(38, 40) is None   # numerador o complemento de 1 a 4
    assert an.pct(5, 9) is None                               # grupo de menos de 10
    assert an.pct(0, 40) == 0.0 and an.pct(40, 40) == 100.0 and an.pct(10, 40) == 25.0
    assert an.atributo(3, 40) == an.MENOS and an.atributo(37, 40) == an.OCULTA and an.atributo(20, 40) == 20
    assert an.atributo(0, 8) == an.OCULTA and an.atributo(0, 0) == 0
    assert an.celda(0) == 0 and an.celda(4) == an.MENOS and an.celda(5) == 5


# ───────────────────────────── Datos del mundo ─────────────────────────────

@pytest.fixture
def ctx_de_analisis(sesion):
    import ayudas_agente as aa
    abiertos = []

    def hacer(cli):
        c = aa.contexto(sesion.app, cli)
        abiertos.append(c)
        return c

    yield hacer
    for c in abiertos:
        aa.correr(sesion, c.api.cerrar)


@pytest.fixture
def mundo(sesion):
    """Una base inventada con usuarios, personas variadas y sus acercamientos."""
    db = sesion.app.state.db
    uids = [crear_usuario(db, "planillero")["_id"], crear_usuario(db, "consultor")["_id"],
            crear_usuario(db, "planillero")["_id"]]
    ids = ya.base_variada(db, 160, 3, HOY, uids)
    for pid in ids[:40]:
        ya.autorizacion(db, pid, dia=HOY - timedelta(days=5))
    for i, pid in enumerate(ids[:12]):
        ya.alta_en_panel(db, pid, uids[0], HOY - timedelta(days=3))
    lid = ya.lugares(db, 1)[0]
    db.reuniones.insert_one({"_id": 1, "titulo": "Reunión inventada", "fecha": (HOY - timedelta(days=40)).isoformat(),
                             "lugar_id": lid, "creado_por_uid": uids[0], "creado_en": ya.ts(HOY - timedelta(days=41))})
    return {"db": db, "uids": uids, "ids": ids, "lugar": lid}


CONSULTAS = [
    {"tipo": "tabla", "dimensiones": ["sexo"]},
    {"tipo": "tabla", "dimensiones": ["lugar"], "metricas": ["personas", "pct", "pct_contacto_util", "pct_asistio"]},
    {"tipo": "tabla", "dimensiones": ["zona", "consentimiento"], "metricas": ["personas", "pct"]},
    {"tipo": "tabla", "dimensiones": ["zona"], "metricas": ["personas", "pct_con_cedula", "pct_contactadas"]},
    {"tipo": "tabla", "dimensiones": ["puesto", "mesa"]},
    {"tipo": "tabla", "dimensiones": ["fuente"]},
    {"tipo": "tabla", "dimensiones": ["quien_capturo"]},
    {"tipo": "tabla", "dimensiones": ["mes_alta"]},
    {"tipo": "serie", "evento": "altas"},
    {"tipo": "serie", "evento": "acercamientos", "desglose": "canal"},
    {"tipo": "serie", "evento": "contacto_util", "granularidad": "semana",
     "desde": (HOY - timedelta(days=120)).isoformat()},
    {"tipo": "serie", "evento": "autorizaciones", "desglose": "medio"},
    {"tipo": "serie", "evento": "asistencias", "granularidad": "mes", "desde": (HOY - timedelta(days=360)).isoformat()},
    {"tipo": "embudo"},
    {"tipo": "embudo", "dimensiones": ["zona"]},
    {"tipo": "cobertura"},
    {"tipo": "brechas"},
    {"tipo": "equipo", "granularidad": "semana"},
    {"tipo": "calidad", "dimensiones": ["zona"]},
    {"tipo": "anomalias"},
    {"tipo": "cohortes"},
    {"tipo": "ritmo", "fecha_meta": (HOY + timedelta(days=150)).isoformat()},
    {"tipo": "franjas", "desglose": "usuario"},
    {"tipo": "intentos"},
    {"tipo": "captura"},
    {"tipo": "comparar", "metrica": "acercamientos", "dimensiones": ["canal"]},
    {"tipo": "comparar", "metrica": "tasa_contacto_util", "dimensiones": ["zona"]},
    {"tipo": "comparar", "metrica": "altas", "dimensiones": ["quien_capturo"]},
    {"tipo": "reuniones_efecto"},
    {"tipo": "diagnostico", "fecha_meta": (HOY + timedelta(days=150)).isoformat()},
]


def _todas(cli) -> dict:
    return {json.dumps(c, sort_keys=True): ya.consulta(cli, **c) for c in CONSULTAS}


def _no_autorizaron(m: dict, n: int = 15) -> list[int]:
    """Personas que dijeron «no», con todo lo que el equipo pudo hacer con ellas: llamarlas (también hoy), una
    autorización «sí» anterior, asistencias, un alta en el panel, un conflicto de cédula, una solicitud vencida, un
    posible duplicado con alguien de la base y una ficha unida."""
    db, uids, lid = m["db"], m["uids"], m["lugar"]
    eleccion = modelo.leer_ajustes(db)["eleccion_vigente"]
    puesto = bd.puestos_vigentes(db, eleccion)[0]["_id"]
    filas = [{"nombre": f"NOAUTORIZO INVENTADA {i}", "consentimiento": "no", "zona": "urbana", "lugar_id": lid,
              "sexo": "F", "cedula": str(97_000_000 + i), "telefono": str(3_009_000_000 + i),
              "votacion": {"puesto_id": puesto, "mesa": 1, "eleccion": eleccion, "estado": "verificado",
                           "donde": "yondo"},
              "abordaje": {"n": 2, "efectivos": 1, "estado": "no_contactar"},
              "asistencias": [{"reunion_id": 1, "creado_en": ya.ts(HOY - timedelta(days=30))}],
              "fuentes": ["planilla"], "creado_por": {"uid": uids[0], "capturado_por": uids[2]},
              "creado_en": ya.ts(HOY - timedelta(days=2))} for i in range(n)]
    ids = ya.personas(db, filas)
    for k, pid in enumerate(ids):
        for d in range(4):
            ya.acercamiento(db, pid, uids[1], dia=HOY - timedelta(days=d), hora=9 + d,
                            resultado=("contesto", "no_contesto", "no_contactar", "contesto")[d])
        ya.autorizacion(db, pid, dia=HOY - timedelta(days=4))
        ya.autorizacion(db, pid, dia=HOY - timedelta(days=1), estado="no")
        ya.alta_en_panel(db, pid, uids[0], HOY - timedelta(days=2))
        db.personas.update_one({"_id": pid}, {"$set": {"consentimiento": "no", "fuentes": ["planilla"]}})
    db.conflictos_cedula.insert_one({"_id": 9001, "clave": "x9001", "cedula": "97000000", "persona_id": ids[0],
                                     "motivo": "posible_digitacion", "estado": "pendiente",
                                     "creado_en": ya.ts(HOY - timedelta(days=1))})
    db.solicitudes.insert_one({"_id": 9001, "persona_id": ids[1], "tipo": "supresion", "canal": "presencial",
                               "estado": "pendiente", "vence": (HOY - timedelta(days=3)).isoformat(),
                               "ts": ya.ts(HOY - timedelta(days=20))})
    db.coincidencias.insert_one({"_id": 9001, "persona_id": m["ids"][0], "candidato_id": ids[2], "puntaje": 90,
                                 "estado": "pendiente"})
    unida = ya.persona(db, nombre="NOAUTORIZO UNIDA INVENTADA", consentimiento="no", fuentes=["manual"],
                       creado_por={"uid": uids[0]}, creado_en=ya.ts(HOY - timedelta(days=3)))
    db.personas.update_one({"_id": unida}, {"$set": {"fusionada_en": ids[3]}})
    return ids


def test_quien_no_autorizo_no_cambia_ninguna_salida(sesion, mundo):
    antes = _todas(sesion)
    assert all(not v.get("pocas") for v in antes.values())
    _no_autorizaron(mundo)
    despues = _todas(sesion)
    for k in antes:
        assert despues[k] == antes[k], k


def test_registrarlos_y_llamarlos_no_cambia_el_equipo_ni_su_serie(sesion, mundo):
    """`usuarios.serie(..., tratables=True)` (la serie de cada usuario del equipo) tampoco cuenta lo hecho con quien
    no autorizó; sin `tratables` sí (lo que ve Usuarios del panel)."""
    from app.api import usuarios as uapi
    db, uid = mundo["db"], mundo["uids"][0]
    d, h = HOY - timedelta(days=10), HOY
    td, th = uapi._utc(d), uapi._utc(h + timedelta(days=1))
    antes_t = uapi.serie(db, uid, td, th, "dia", tratables=True)
    antes = uapi.serie(db, uid, td, th, "dia")
    _no_autorizaron(mundo)
    assert uapi.serie(db, uid, td, th, "dia", tratables=True) == antes_t
    assert uapi.serie(db, uid, td, th, "dia") != antes
    # Lo anonimizado por una supresión sigue contando (ya no es de nadie): un acercamiento sin persona del usuario
    c = mundo["uids"][1]
    antes_c = uapi.serie(db, c, td, th, "dia", tratables=True)
    ya.acercamiento(db, None, c, dia=HOY)
    despues_c = uapi.serie(db, c, td, th, "dia", tratables=True)
    assert sum(x["acercamientos"] for x in despues_c) == sum(x["acercamientos"] for x in antes_c) + 1


def test_las_bases_politicas_no_se_deducen(sesion):
    """30 personas que vienen solo de la base «general» o de la base con cédula (importadas por el administrador):
    ninguna tabla por fuente, quién capturó o mes de alta, serie de altas, anomalía, cohorte ni captura cambia con
    ellas, salvo la casilla «importación» (que junta todas las importaciones de bases, también la de trámites) y el
    total. Con los datos políticos apagados (`agente_politicos`): encendidos, la fuente nombra esas bases
    (tests/test_politicos_analitica.py)."""
    db = sesion.app.state.db
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"agente_politicos": {"asistente": False, "mcp": False}}},
                       upsert=True)
    u1, u2 = crear_usuario(db, "planillero")["_id"], crear_usuario(db, "planillero")["_id"]
    filas = []
    for i in range(60):
        uid = (u1, u2)[i % 2]
        filas.append({"nombre": f"PERSONA EQUIPO INVENTADA {i}", "sexo": "F", "zona": "urbana", "fuentes": ["manual"],
                      "creado_por": {"uid": uid}, "creado_en": ya.ts(HOY - timedelta(days=i % 50))})
    for i in range(40):
        filas.append({"nombre": f"PERSONA TRAMITES INVENTADA {i}", "fuentes": ["tramites"],
                      "creado_por": {"uid": 0}, "creado_en": ya.ts(HOY - timedelta(days=100))})
    ya.personas(db, filas)
    consultas = [{"tipo": "tabla", "dimensiones": ["fuente"]}, {"tipo": "tabla", "dimensiones": ["quien_capturo"]},
                 {"tipo": "tabla", "dimensiones": ["mes_alta"]}, {"tipo": "serie", "evento": "altas"},
                 {"tipo": "serie", "evento": "altas", "desglose": "quien_capturo"}, {"tipo": "anomalias"},
                 {"tipo": "cohortes"}, {"tipo": "captura"},
                 {"tipo": "comparar", "metrica": "altas", "dimensiones": ["quien_capturo"]}]
    antes = [ya.consulta(sesion, **c) for c in consultas]
    politicas = [{"nombre": f"PERSONA BASE GENERAL INVENTADA {i}", "fuentes": ["general" if i % 3 else "cedulas"],
                  "creado_por": {"uid": 0}, "creado_en": ya.ts(HOY - timedelta(days=7), 11)} for i in range(30)]
    ya.personas(db, politicas)
    despues = [ya.consulta(sesion, **c) for c in consultas]
    for c, a, d in zip(consultas, antes, despues):
        if c.get("dimensiones") in (["quien_capturo"], ["mes_alta"]) and c["tipo"] == "tabla":
            fa = {f["valor"]: f for f in a["filas"]}
            fd = {f["valor"]: f for f in d["filas"]}
            assert set(fa) == set(fd)
            for v in fa:
                if v != "importacion":
                    assert fd[v]["personas"] == fa[v]["personas"], (c, v)
            assert fd["importacion"]["personas"] == fa["importacion"]["personas"] + 30
            assert "administrador" not in {f["etiqueta"] for f in d["filas"]}
        else:
            assert d == a, c
    # La fuente no tiene total, resto ni porcentaje: ni «general» ni «cedulas» aparecen
    fuente = despues[0]
    assert "base" not in fuente and {f["valor"] for f in fuente["filas"]} <= set(an.FUENTES_SEGURAS)
    texto = json.dumps(despues, ensure_ascii=False)
    assert '"general"' not in texto and '"cedulas"' not in texto


def test_quien_capturo_es_el_planillero_de_la_planilla(sesion):
    db = sesion.app.state.db
    planillero, coord = crear_usuario(db, "planillero"), crear_usuario(db, "planillero")
    db.usuarios.update_one({"_id": coord["_id"]}, {"$set": {"rol": "coordinador"}})
    ya.personas(db, [{"nombre": f"PERSONA PLANILLA INVENTADA {i}", "fuentes": ["planilla"],
                      "creado_por": {"uid": coord["_id"], "capturado_por": planillero["_id"]}} for i in range(12)])
    ya.personas(db, [{"nombre": f"PERSONA PANEL INVENTADA {i}", "fuentes": ["manual"],
                      "creado_por": {"uid": coord["_id"]}} for i in range(7)])
    ya.personas(db, [{"nombre": f"PERSONA PLANILLA SIN PLANILLERO {i}", "fuentes": ["planilla"],
                      "creado_por": {"uid": coord["_id"], "capturado_por": None}} for i in range(6)])
    t = ya.consulta(sesion, tipo="tabla", dimensiones=["quien_capturo"])
    filas = {f["etiqueta"]: f["personas"] for f in t["filas"]}
    assert filas == {planillero["usuario"]: 12, coord["usuario"]: 7, "Importación de una base": 6}


# ───────────────────────────── Población chica, celdas y porcentajes ─────────────────────────────

def test_con_menos_de_10_personas_solo_pocas(sesion, mundo):
    db = mundo["db"]
    vereda = ya.lugares(db, 8)[-1]
    db.personas.update_many({"lugar_id": vereda}, {"$set": {"lugar_id": None}})
    ya.personas(db, [{"nombre": f"PERSONA VEREDA INVENTADA {i}", "lugar_id": vereda, "sexo": "F",
                      "consentimiento": "si", "contacto_habilitado": True} for i in range(4)])
    for c in CONSULTAS:
        if "filtros" not in an.PARAMETROS[c["tipo"]][1]:
            continue
        c = {**c, "filtros": {"lugar_id": vereda}}
        assert ya.consulta(sesion, **c) == POCAS, c
    # Con un filtro que deja 0 personas, igual
    assert ya.consulta(sesion, tipo="tabla", dimensiones=["sexo"], filtros={"lugar_id": vereda, "sexo": "M"}) == POCAS


def test_celdas_chicas_porcentajes_y_complementarias(sesion):
    db = sesion.app.state.db
    filas = ([{"sexo": "F", "cedula": str(92_000_000 + i) if i < 10 else None} for i in range(20)] +
             [{"sexo": "M", "cedula": str(92_100_000 + i) if i < 10 else None,
               "telefono": str(3_001_200_000 + i) if i < 2 else None} for i in range(12)] +
             [{"sexo": "N"} for _ in range(3)] + [{"cedula": None} for _ in range(6)])
    ya.personas(db, filas)
    t = ya.consulta(sesion, tipo="tabla", dimensiones=["sexo"],
                    metricas=["personas", "pct", "pct_con_cedula", "pct_telefono_usable"])
    f = {x["valor"]: x for x in t["filas"]}
    assert t["base"] == {"personas": 41}
    assert f["N"]["personas"] == "<5" and "pct" not in f["N"]
    assert f["sin"]["personas"] == "oculta" and "pct_con_cedula" not in f["sin"]  # la complementaria
    assert f["M"]["pct_con_cedula"] is None        # 10 de 12: faltan 2
    assert f["M"]["pct_telefono_usable"] is None   # 2 de 12
    # El % de las mujeres (10 de 20) también se oculta: con el total de personas con cédula (otra tabla) y los
    # demás grupos, dejaría deducir las 2 sin cédula de los hombres
    assert f["F"]["personas"] == 20 and f["F"]["pct_con_cedula"] is None
    assert f["F"]["pct"] == round(100 * 20 / 41, 1)
    posibles = _posibles_1d({k: x["personas"] for k, x in f.items()}, 41)
    assert len(posibles["N"]) >= 2 and 3 in posibles["N"]


def test_un_porcentaje_por_grupo_no_se_deduce_con_el_total_y_los_demas(sesion):
    """Por zona: el % con cédula de cada zona y el total con cédula (de la tabla por con_cedula) no dejan deducir la
    zona que tiene 3 sin cédula; cuando nada es chico, los % salen."""
    db = sesion.app.state.db
    filas = ([{"zona": "urbana", "cedula": str(86_000_000 + i) if i < 15 else None} for i in range(30)] +
             [{"zona": "rural", "cedula": str(86_100_000 + i) if i < 17 else None} for i in range(20)] +
             [{"cedula": str(86_200_000 + i) if i < 9 else None} for i in range(18)])
    ya.personas(db, filas)
    t = ya.consulta(sesion, tipo="tabla", dimensiones=["zona"], metricas=["personas", "pct_con_cedula"])
    f = {x["valor"]: x for x in t["filas"]}
    assert f["rural"]["pct_con_cedula"] is None   # 17 de 20: faltan 3
    total = {x["valor"]: x["personas"] for x in
             ya.consulta(sesion, tipo="tabla", dimensiones=["con_cedula"])["filas"]}
    assert total == {"si": 41, "no": 27}
    # Lo publicado (tamaños y %) frente al total con cédula: la zona rural no queda determinada
    conocidos = {k: round(x["pct_con_cedula"] * x["personas"] / 100) for k, x in f.items()
                 if x.get("pct_con_cedula") is not None}
    assert "rural" not in conocidos and len(conocidos) <= 1
    ya.personas(db, [{"zona": "rural", "cedula": None} for _ in range(10)])
    t = ya.consulta(sesion, tipo="tabla", dimensiones=["zona"], metricas=["personas", "pct_con_cedula"])
    assert {x["valor"]: x["pct_con_cedula"] for x in t["filas"]} == {"urbana": 50.0, "rural": round(1700 / 30, 1),
                                                                     "sin": 50.0}


def test_un_desglose_que_no_se_puede_proteger_no_se_publica(sesion, ctx_de_analisis):
    """12 personas en tres grupos de 4: con el total publicado, cada «<5» sería exactamente 4. No se publica el
    desglose (ni por la API ni por la herramienta), solo el total y por qué."""
    db = sesion.app.state.db
    ya.personas(db, [{"sexo": s} for s in ("F", "M", "N") for _ in range(4)])
    t = ya.consulta(sesion, tipo="tabla", dimensiones=["sexo"])
    assert t == {"tipo": "tabla", "dispersas": True, "base": {"personas": 12}, "nota": an.NOTA_DISPERSAS,
                 "nota_autorizacion": an.NOTA_AUTORIZACION}
    from app.agente.herramientas import analisis as ha
    import ayudas_agente as aa
    r = aa.correr(sesion, aa.ejecutar, ha.ANALIZAR, ctx_de_analisis(sesion), {"tipo": "tabla", "dimensiones": ["sexo"]})
    assert r.contenido["dispersas"] is True and r.acciones == [] and "sin desglose" in r.resumen


def test_dos_dimensiones_no_se_reconstruyen_con_las_tablas_de_una(sesion):
    db = sesion.app.state.db
    datos = {("urbana", "F"): 3, ("urbana", "M"): 20, ("urbana", "sin"): 8,
             ("rural", "F"): 15, ("rural", "M"): 2, ("rural", "sin"): 9,
             ("sin", "F"): 6, ("sin", "M"): 7, ("sin", "sin"): 1}
    filas = []
    for (z, s), k in datos.items():
        filas += [{"zona": None if z == "sin" else z, "sexo": None if s == "sin" else s} for _ in range(k)]
    ya.personas(db, filas)
    t = ya.consulta(sesion, tipo="tabla", dimensiones=["zona", "sexo"])
    cols = [c["valor"] for c in t["columnas"]]
    pub = {(f["valor"], c): x["personas"] for f in t["filas"] for c, x in zip(cols, f["celdas"])}
    # Lo que se sabe además: las tablas de una dimensión (los márgenes) y el total
    zonas = {x["valor"]: x["personas"] for x in ya.consulta(sesion, tipo="tabla", dimensiones=["zona"])["filas"]}
    sexos = {x["valor"]: x["personas"] for x in ya.consulta(sesion, tipo="tabla", dimensiones=["sexo"])["filas"]}
    assert all(an.visible(v) for v in list(zonas.values()) + list(sexos.values()))
    filas_v = [f["valor"] for f in t["filas"]]
    assert pub[("urbana", "F")] == "<5" and pub[("rural", "M")] == "<5" and pub[("sin", "sin")] == "<5"
    posibles = _posibles_2d(pub, filas_v, cols, zonas, sexos)
    for k, v in pub.items():
        if not an.visible(v):
            assert datos[k] in posibles[k]
        if v == an.MENOS:
            assert len(posibles[k]) >= 2, (k, posibles[k])
    # Los márgenes publicados son solo lo visible
    for f in t["filas"]:
        assert f["total_visible"] == sum(x["personas"] for x in f["celdas"] if an.visible(x["personas"]))


def test_series_suben_de_granularidad_y_la_tendencia_solo_usa_lo_visible(sesion):
    db = sesion.app.state.db
    uid = crear_usuario(db, "planillero")["_id"]
    filas = []
    # 2 altas cada 3 días durante 60 días: por día son de 1 a 4; por semana, 4 o 6; por mes, más
    for k in range(20):
        for j in range(2):
            filas.append({"nombre": f"PERSONA SERIE INVENTADA {k}-{j}", "fuentes": ["manual"],
                          "creado_por": {"uid": uid}, "creado_en": ya.ts(HOY - timedelta(days=3 * k + 1))})
    ya.personas(db, filas)
    s = ya.consulta(sesion, tipo="serie", evento="altas", granularidad="dia",
                    desde=(HOY - timedelta(days=60)).isoformat())
    assert s["granularidad"] in ("semana", "mes") and "Se pasó a" in s["nota"]
    vis = [p["valor"] for p in s["puntos"] if an.visible(p["valor"])]
    assert s["tendencia"]["total_visible"] == sum(vis)
    assert all(not (an.visible(p["valor"]) and 0 < p["valor"] < 5) for p in s["puntos"])
    publicado = {p["periodo"]: p["valor"] for p in s["puntos"]}
    posibles = _posibles_1d(publicado, 40)
    assert all(len(posibles[k]) >= 2 for k, v in publicado.items() if v == an.MENOS)


# ───────────────────────────── Quién y qué filtros ─────────────────────────────

@pytest.mark.parametrize("rol", ["planillero", "consultor"])
def test_planillero_y_consultor_reciben_403(sesion, como, rol):
    c = como(rol)
    for r in (c.get("/api/analitica", params={"consulta": json.dumps({"tipo": "tabla", "dimensiones": ["sexo"]})}),
              c.get("/api/analitica"), c.get("/api/analitica/catalogo")):
        assert r.status_code == 403 and r.json()["detail"]["codigo"] == "permiso"


@pytest.mark.parametrize("consulta", [
    {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"q": "ana"}},
    # Los políticos válidos (lista, tipo, fuente general o cedulas, la dimensión lider) ya no son 422: 403 con
    # `agente_politicos` apagado y 200 encendido (tests/test_politicos_analitica.py)
    {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"lista": ""}},
    {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"lider": 1}},
    {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"tipo": "candidato"}},
    {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"fuente": "otra_base"}},
    {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"varios_lideres": False}},
    {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"regimen_salud": "Subsidiado"}},
    {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"consentimiento": "no"}},
    {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"reunion_id": 1}},
    {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"creado_por": 1}},
    {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"actualizado_por": 1}},
    {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"ids": "1,2"}},
    {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"poligono": "1,2;3,4;5,6"}},
    {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"situacion": "fallecida"}},
    {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"edad_min": 46}},
    {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"edad_max": 47}},
    {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"completitud_max": 51}},
    {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"sin_acercamiento_dias": 13}},
    {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"zona": "rural", "sexo": "F", "menor": False,
                                                           "con_cedula": True}},
    {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"zona": "rural", "faltan": ["cedula", "telefono", "sexo"]}},
    {"tipo": "tabla", "dimensiones": ["lideres"]},
    {"tipo": "tabla", "dimensiones": ["lider", "fuente"]},
    {"tipo": "tabla", "dimensiones": ["regimen_salud"]},
    {"tipo": "tabla", "dimensiones": ["listas"]},
    {"tipo": "tabla", "dimensiones": ["creado_por"]},
    {"tipo": "tabla", "dimensiones": ["fuente", "sexo"]},
    {"tipo": "tabla", "dimensiones": ["fuente"], "metricas": ["personas", "pct"]},
    {"tipo": "tabla", "dimensiones": ["zona", "sexo"], "metricas": ["personas", "pct_con_cedula"]},
    {"tipo": "tabla", "dimensiones": ["mesa"]},
    {"tipo": "tabla", "dimensiones": ["canal"]},
    {"tipo": "tabla"},
    {"tipo": "tabla", "dimensiones": ["sexo"], "evento": "altas"},
    {"tipo": "serie"},
    {"tipo": "serie", "evento": "altas", "desglose": "canal"},
    {"tipo": "serie", "evento": "reuniones", "filtros": {"zona": "rural"}},
    {"tipo": "serie", "evento": "altas", "desde": "2024-01-01", "hasta": "2026-11-01"},
    {"tipo": "serie", "evento": "altas", "desde": "2026-11-10", "hasta": "2026-11-01"},
    {"tipo": "serie", "evento": "altas", "desde": "2026-02-30"},
    {"tipo": "ritmo"},
    {"tipo": "cohortes", "desde": "2020-01-01"},
    {"tipo": "comparar", "metrica": "altas", "dimensiones": ["canal"]},
    {"tipo": "comparar", "metrica": "altas", "dimensiones": ["zona"], "referencia_desde": "2026-01-01"},
    {"tipo": "equipo", "filtros": {"zona": "rural"}},
    {"tipo": "calidad", "dimensiones": ["sexo"]},
    {"tipo": "franjas", "desglose": "canal"},
    {"tipo": "brechas", "dias": 45},
    {"tipo": "desconocido"},
    {"tipo": "tabla", "dimensiones": ["sexo"], "extra": 1},
])
def test_consultas_fuera_de_la_lista_blanca_dan_422(sesion, consulta):
    estado, detalle = ya.error(sesion, consulta)
    assert estado == 422, (consulta, detalle)
    assert detalle["codigo"] == "invalido" and detalle["mensaje"]


def test_consulta_mal_formada_o_ausente(sesion):
    for texto in ("", "{no es json", "[1, 2]", "x" * 5000):
        estado, detalle = ya.error(sesion, texto)
        assert estado == 422 and detalle["codigo"] == "invalido", texto
    r = sesion.get("/api/analitica")
    assert r.status_code == 422


def test_etiqueta_sensible_403_y_area_inexistente_404(sesion):
    db = sesion.app.state.db
    sensible = db.etiquetas.find_one({"nombre": "Discapacidad"})["_id"]
    estado, detalle = ya.error(sesion, {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"etiqueta": sensible}})
    assert estado == 403 and detalle["codigo"] == "permiso"
    estado, _ = ya.error(sesion, {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"etiqueta": 99999}})
    assert estado == 404
    estado, _ = ya.error(sesion, {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"area_id": 99999}})
    assert estado == 404


def test_la_etiqueta_sensible_nunca_es_un_grupo(sesion):
    db = sesion.app.state.db
    sensible = db.etiquetas.find_one({"nombre": "Víctima del conflicto"})["_id"]
    vivienda = db.etiquetas.find_one({"nombre": "Vivienda"})["_id"]
    ya.personas(db, [{"etiquetas": [sensible, vivienda]} for _ in range(20)])
    t = ya.consulta(sesion, tipo="tabla", dimensiones=["etiqueta"])
    assert [f["etiqueta"] for f in t["filas"]] == ["Vivienda"] and "base" not in t
    assert "Víctima" not in json.dumps(t, ensure_ascii=False)


def test_ninguna_salida_trae_identificadores_ni_datos_politicos(sesion, mundo):
    db = mundo["db"]
    db.personas.update_many({}, {"$set": {"lider": True, "listas": ["Lista Inventada B3"],
                                          "sensibles": {"etnia": "Raizal"}, "regimen_salud": "Subsidiado"}})
    vedadas = {"cedula", "telefono", "telefono2", "telefonos", "correo", "direccion", "lat", "lon", "punto",
               "nombre_norm", "listas", "lider", "lideres", "sensibles", "regimen_salud", "origen", "procedencia",
               "fuentes"}
    numeros = [x[k] for x in db.personas.find({}, {"cedula": 1, "telefono": 1}) for k in ("cedula", "telefono")
               if x.get(k)]
    assert len(numeros) > 100
    for c in CONSULTAS:
        out = ya.consulta(sesion, **c)
        texto = json.dumps(out, ensure_ascii=False)
        for v in ("Lista Inventada B3", "Raizal", "Subsidiado", "PERSONA INVENTADA", *numeros):
            assert v not in texto, (c["tipo"], v)

        def recorrer(x):
            if isinstance(x, dict):
                for k, v in x.items():
                    assert k not in vedadas, (c["tipo"], k)
                    recorrer(v)
            elif isinstance(x, list):
                for v in x:
                    recorrer(v)
        recorrer(out)
