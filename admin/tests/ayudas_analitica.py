"""Ayudas de las pruebas de la analítica avanzada (`app/analitica.py`, `/api/analitica` y las herramientas `analizar` y
`diagnostico`). Solo datos inventados: nombres de prueba, cédulas y teléfonos que no existen."""
from __future__ import annotations

import json
import random
from datetime import date, datetime, time, timedelta, timezone

from pymongo import UpdateOne

from app import db as bd
from app import modelo
from conftest import insertar_personas


def ts(d: date, hora: int = 10, minuto: int = 0) -> str:
    """Instante ISO UTC (como `bd.ahora()`) de una hora de Colombia de ese día."""
    return datetime.combine(d, time(hora, minuto), tzinfo=modelo.ZONA).astimezone(timezone.utc).isoformat()


def personas(db, filas: list[dict], fuente: str = "manual") -> list[int]:
    """Inserta las fichas (con `bd.nueva_persona`) y después escribe tal cual cada fila, aunque pise lo derivado
    (`creado_en`, `fuentes`, `creado_por`…)."""
    base = [{k: v for k, v in f.items() if k in ("nombre", "cedula", "telefono", "sexo", "edad", "fecha_nacimiento",
                                                 "direccion", "lat", "lon", "geo_precision")} for f in filas]
    for b in base:
        b.setdefault("nombre", "PERSONA INVENTADA DE ANALITICA")
    ids = insertar_personas(db, base, fuente)
    ops = [UpdateOne({"_id": pid}, {"$set": f}) for pid, f in zip(ids, filas) if f]
    if ops:
        db.personas.bulk_write(ops)
    return ids


def persona(db, fuente: str = "manual", **campos) -> int:
    return personas(db, [campos], fuente)[0]


def acercamiento(db, pid: int | None, uid: int, *, dia: date, hora: int = 10, canal: str = "llamada",
                 resultado: str = "contesto", auto: bool = False, anulado: bool = False, fuera: bool = False) -> int:
    aid = bd.siguiente_id(db, "acercamientos")
    db.acercamientos.insert_one({
        "_id": aid, "persona_id": pid, "ts": ts(dia, hora), "fecha": dia.isoformat(), "uid": uid,
        "usuario": f"usuario{uid}", "rol": "consultor", "canal": canal, "telefono": None, "resultado": resultado,
        "efectivo": resultado in modelo.EFECTIVOS, "nota": None, "proximo": None, "proximo_franja": None,
        "confirma_numero": False, "alcance": None, "reunion_id": None, "autorizacion_id": None, "datos_dictados": [],
        "efectos": [], "fuera_de_horario": fuera, "auto": auto, "anulado": anulado, "anulado_por": None,
        "anulado_en": None, "motivo_anulacion": None, "suprimido": False, "clave_migracion": None})
    return aid


def autorizacion(db, pid: int, *, dia: date, estado: str = "si", medio: str = "escrito", uid: int = 0) -> int:
    aid = bd.siguiente_id(db, "autorizaciones")
    db.autorizaciones.insert_one({"_id": aid, "persona_id": pid, "estado": estado, "medio": medio,
                                  "canales": ["llamada"], "ts": ts(dia), "uid": uid, "usuario": f"usuario{uid}",
                                  "rol": "admin"})
    return aid


def alta_en_panel(db, pid: int, uid: int, dia: date, hora: int = 10) -> None:
    """La ficha queda como registrada por `uid` en el panel ese día, con su entrada «crear» en la auditoría."""
    db.personas.update_one({"_id": pid}, {"$set": {"creado_en": ts(dia, hora), "fuentes": ["manual"],
                                                   "creado_por": {"uid": uid, "usuario": f"usuario{uid}",
                                                                  "rol": "planillero"}}})
    db.auditoria.insert_one({"ts": ts(dia, hora), "usuario": f"usuario{uid}", "accion": "crear", "entidad": "persona",
                             "entidad_id": pid, "detalle": None, "ip": None, "uid": uid, "rol": "planillero",
                             "campos": ["nombre"], "completados": []})


def consulta(cli, **c) -> dict:
    r = cli.get("/api/analitica", params={"consulta": json.dumps(c)})
    assert r.status_code == 200, r.text
    return r.json()


def error(cli, c) -> tuple[int, dict]:
    r = cli.get("/api/analitica", params={"consulta": c if isinstance(c, str) else json.dumps(c)})
    return r.status_code, r.json().get("detail")


def lugares(db, n: int = 6) -> list[int]:
    return [x["_id"] for x in db.lugares.find({"tipo": {"$in": ["barrio", "vereda"]}}, {"_id": 1}).sort("_id", 1)
            .limit(n)]


def base_variada(db, n: int, semilla: int, hoy: date, uids: list[int], *, con_acercamientos: bool = True) -> list[int]:
    """`n` personas inventadas con todos los atributos que agrupa la analítica (y sus acercamientos): repartidas en
    zonas, lugares, puestos, autorizaciones y fechas de alta del último año. Determinista por `semilla`."""
    rnd = random.Random(semilla)
    ls = lugares(db, 8)
    eleccion = modelo.leer_ajustes(db)["eleccion_vigente"]
    puestos = [p["_id"] for p in bd.puestos_vigentes(db, eleccion)]
    filas = []
    for i in range(n):
        alta = hoy - timedelta(days=rnd.randint(0, 360))
        consent = rnd.choice(("si", "si", "pendiente", "pendiente", "pendiente"))
        habilitado = consent == "si" and rnd.random() < 0.7
        tiene_tel = rnd.random() < 0.8
        n_acerc = rnd.choice((0, 0, 1, 2, 3)) if habilitado else 0
        efectivos = sum(1 for _ in range(n_acerc) if rnd.random() < 0.5)
        importada = rnd.random() < 0.3
        fuente = "tramites" if importada else rnd.choice(("manual", "manual", "reunion", "planilla"))
        cap = rnd.choice(uids) if fuente == "planilla" else None
        f = {
            "nombre": f"PERSONA INVENTADA {semilla}-{i}", "sexo": rnd.choice(("F", "M", "F", "M", None)),
            "edad": rnd.choice((None, rnd.randint(14, 85))), "cedula": str(91_000_000 + semilla * 100_000 + i)
            if rnd.random() < 0.7 else None,
            "telefono": str(3_210_000_000 + semilla * 100_000 + i) if tiene_tel else None,
            "zona": rnd.choice(("urbana", "rural", None)), "lugar_id": rnd.choice(ls + [None]),
            "estado_civil": rnd.choice((None, *modelo.ESTADOS_CIVILES)), "estrato": rnd.choice((None, 1, 2, 3)),
            "consentimiento": consent, "contacto_habilitado": habilitado,
            "consentimiento_medio": rnd.choice(("escrito", "verbal_telefono", "declarado_planilla")) if consent == "si"
            else None,
            "creado_en": ts(alta, rnd.randint(7, 18)), "fuentes": [fuente],
            "creado_por": {"uid": 0 if importada else rnd.choice(uids), "usuario": "x", "rol": "coordinador",
                           **({"capturado_por": cap} if fuente == "planilla" else {})},
            "abordaje": None if n_acerc == 0 else {
                "n": n_acerc, "efectivos": efectivos, "intentos_sin_exito": 0, "estado":
                    "contactado" if efectivos else "intentado", "ultimo_resultado": "contesto" if efectivos
                    else "no_contesto", "ultimo_canal": "llamada", "ultimo_fecha": hoy.isoformat(), "proximo": None},
            "asistencias": [{"reunion_id": 1, "rol": None, "nota": None, "creado_en": ts(alta)}]
            if rnd.random() < 0.2 else [],
        }
        if rnd.random() < 0.6:
            f["votacion"] = {"puesto_id": rnd.choice(puestos), "mesa": rnd.randint(1, 3), "eleccion": eleccion,
                             "estado": rnd.choice(("verificado", "sin_verificar")), "donde": "yondo"}
        filas.append(f)
    ids = personas(db, filas)
    if con_acercamientos:
        for pid, f in zip(ids, filas):
            ab = f["abordaje"]
            if not ab:
                continue
            for k in range(ab["n"]):
                dia = hoy - timedelta(days=rnd.randint(0, 120))
                res = rnd.choice(("contesto", "no_contesto", "buzon", "no_contactar", "volver_llamar"))
                acercamiento(db, pid, rnd.choice(uids), dia=dia, hora=rnd.randint(7, 20),
                             canal=rnd.choice(("llamada", "whatsapp", "visita")), resultado=res)
    return ids
