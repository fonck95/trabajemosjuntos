"""Migración idempotente a la versión 2 del esquema (1.12). Solo fichas inventadas con la forma vieja."""
import json
import time
from datetime import timedelta

import pytest

from app import db as bd
from app import migraciones, modelo
from ayudas_g1 import a_vieja, base_vieja, cedula, ficha_vieja, importar, tramites_inventados
from conftest import LENTAS, personas_inventadas

COLECCIONES = ("personas", "autorizaciones", "acercamientos", "auditoria", "puestos", "etiquetas", "campos",
               "coincidencias")


def _foto(db) -> dict:
    return {c: list(db[c].find().sort("_id", 1)) for c in COLECCIONES}


def _base_vieja(db, docs, reuniones=(), auditoria=()):
    db.personas.insert_many(docs)
    if reuniones:
        db.reuniones.insert_many(list(reuniones))
    if auditoria:
        db.auditoria.insert_many(list(auditoria))
    db.etiquetas.update_many({}, {"$unset": {"sensible": ""}})
    base_vieja(db)


VIEJAS = [
    ficha_vieja(1, nombre="ZOILA INVENTADA QUINTERO", cedula="90000001", telefono="3001112233", sexo="F", edad=41,
                puesto_votacion="I.E.R. SAN MIGUEL DEL TIGRE", mesa="Mesa # 3", consentimiento="si",
                consentimiento_fecha="2024-06-30", lat=7.0062, lon=-73.9112, geo_precision="direccion",
                fuentes=["tramites", "cedulas"], clave_tramites="ZOILA INVENTADA QUINTERO",
                tramites=[{"id_externo": "1001", "fecha": "2025-06-02", "telefono": "3001112233;3014445566",
                           "correo": "zoila@ejemplo.test", "direccion": "CALLE 49 # 45-12"}],
                correo="zoila@ejemplo.test", direccion="CALLE 49 # 45-12",
                origen=[{"fuente": "cedulas", "clave": "90000001", "importacion_id": 4,
                         "datos": {"cedula": "90000001", "edad": 41, "sexo": "F", "telefonos": ["3001112233", "3045550001"],
                                   "puesto": "I.E.R. SAN MIGUEL DEL TIGRE", "mesa": "Mesa # 3"}}],
                asistencias=[{"reunion_id": 1, "rol": None, "nota": None, "creado_en": "2026-10-01T15:00:00+00:00"}]),
    ficha_vieja(2, nombre="ARQUIMEDES INVENTADO PANTOJA", telefono="3001110002", fecha_nacimiento="1990-06-31", lat=7.0,
                consentimiento="no", puesto_votacion="CABECERA MUNICIPAL", mesa="Mesa # 9",
                tramites=[{"id_externo": "1002", "fecha": "2025-07-03", "telefono": "3001110001"}]),
    ficha_vieja(3, nombre="EUSEBIO INVENTADO JHON", edad="52", telefono="300 111 2233", telefono2="8612345"),
]


def test_documentos_viejos_dos_corridas_sin_cambios(bases):
    db = bases()
    db.importaciones.insert_one({"_id": 4, "ts": "2026-01-10T15:00:00+00:00"})
    _base_vieja(db, [dict(d) for d in VIEJAS], reuniones=[{"_id": 1, "titulo": "Reunión inventada", "fecha": "2026-10-01"}])
    migraciones.migrar(db)
    assert migraciones.version(db) == 2
    primera = _foto(db)
    base_vieja(db)  # los pasos se vuelven a correr: no deben cambiar nada
    migraciones.migrar(db)
    migraciones.migrar(db)  # y la reconciliación sola tampoco
    assert _foto(db) == primera

    zoila = db.personas.find_one({"_id": 1})
    assert [t["numero"] for t in zoila["telefonos"]] == ["3001112233", "3014445566", "3045550001"]
    assert zoila["telefono"] == "3001112233" and zoila["telefono2"] == "3014445566"
    assert zoila["procedencia"]["cedula"]["fuente"] == "cedulas" and zoila["procedencia"]["correo"]["fuente"] == "tramites"
    assert zoila["edad_ref"] == "2026-01-10" and zoila["nac_base"] == {"edad": 41, "fecha": None}
    assert zoila["punto"] == modelo.punto(7.0062, -73.9112) and zoila["nombre_fon"]
    assert zoila["consentimiento"] == "si" and zoila["consentimiento_fecha"] == "2024-06-30"
    assert set(zoila["consentimiento_canales"]) == {"llamada", "whatsapp", "sms"}
    assert zoila["abordaje"]["estado"] == "contactado" and zoila["abordaje"]["ultimo_canal"] == "reunion"
    ev = db.autorizaciones.find_one({"persona_id": 1})
    assert ev["medio"] == "migrado" and ev["canales_implicitos"] is True and ev["clave_migracion"] == "consent:1"
    assert ev["ts"] > "2026-01-01"  # la hora de la migración, nunca la fecha heredada
    ac = db.acercamientos.find_one({"persona_id": 1})
    assert (ac["canal"], ac["resultado"], ac["auto"], ac["clave_migracion"]) == ("reunion", "contesto", True, "reunion:1:1")
    # Las listas nuevas existen en todas
    for p in db.personas.find():
        assert isinstance(p["alternos"], list) and isinstance(p["procedencia"], dict) and isinstance(p["telefonos"], list)
    # Etiquetas sensibles marcadas
    sensibles = {e["nombre"] for e in db.etiquetas.find({"sensible": True})}
    assert sensibles == set(bd.ETIQUETAS_SENSIBLES)
    no = db.personas.find_one({"_id": 2})
    assert no["consentimiento"] == "no" and no["abordaje"]["estado"] == "no_contactar"
    viejo = db.personas.find_one({"_id": 3})
    assert viejo["telefono"] == "300 111 2233" and viejo["telefono2"] == "8612345"  # tal cual
    assert viejo["nac_base"] == {"edad": "52", "fecha": None} and viejo["nac_aprox"]


def test_votacion_migrada_con_eleccion_desconocida(bases):
    db = bases()
    _base_vieja(db, [dict(d) for d in VIEJAS])
    migraciones.migrar(db)
    tigre = db.puestos.find_one({"codigo": "99-65"})
    v = db.personas.find_one({"_id": 1})
    assert v["votacion"]["puesto_id"] == tigre["_id"] and v["votacion"]["mesa"] == 3
    assert v["votacion"]["eleccion"] is None and v["votacion"]["estado"] == "por_confirmar"
    assert v["votacion"]["fuente"] == "cedulas" and v["votacion"]["puesto_texto"] == "I.E.R. SAN MIGUEL DEL TIGRE"
    assert v["mesa"] == "Mesa # 3" and v["puesto_votacion"] == tigre["nombre"]
    assert modelo.estado_votacion_efectivo(v["votacion"], "2026-presidencial") == "por_confirmar"
    cab = db.personas.find_one({"_id": 2})
    assert cab["votacion"]["puesto_id"] is None and cab["votacion"]["puesto_texto"] == "CABECERA MUNICIPAL"
    assert cab["votacion"]["fuente"] == "panel" and cab["puesto_votacion"] == "CABECERA MUNICIPAL"
    assert cab["mesa"] == "Mesa # 9" and cab["votacion"]["mesa"] == 9


def test_fecha_imposible_y_lat_sin_lon_no_la_tumban(bases):
    db = bases()
    _base_vieja(db, [dict(d) for d in VIEJAS])
    migraciones.migrar(db)
    p = db.personas.find_one({"_id": 2})
    assert p["fecha_nacimiento"] == "1990-06-31" and p["nac_aprox"] is None and p["nac_exacta"] is False
    assert p["lat"] == 7.0 and p["lon"] is None and p.get("punto") is None
    assert migraciones.version(db) == 2


def test_numeros_retirados_segun_la_auditoria(bases):
    db = bases()
    aud = [{"ts": "2026-05-01T15:00:00+00:00", "usuario": "admin", "accion": "editar", "entidad": "persona", "entidad_id": 2,
            "detalle": json.dumps({"telefono": {"antes": "3001110001", "despues": "3001110002"}}), "ip": None}]
    _base_vieja(db, [dict(d) for d in VIEJAS], auditoria=aud)
    migraciones.migrar(db)
    p = db.personas.find_one({"_id": 2})
    estados = {t["numero"]: t["estado"] for t in p["telefonos"]}
    assert estados == {"3001110002": "sin_verificar", "3001110001": "retirado"}
    assert p["telefono"] == "3001110002" and p["telefono2"] is None
    retirado = next(t for t in p["telefonos"] if t["numero"] == "3001110001")
    assert retirado["estado_por"] == 0 and retirado["estado_en"] == "2026-05-01T15:00:00+00:00"
    a = db.auditoria.find_one({"entidad_id": 2, "accion": "editar"})
    assert a["campos"] == ["telefono"] and a["completados"] == []


def test_auditoria_vieja_gana_campos_y_completados(bases):
    db = bases()
    aud = [
        {"_id": 1, "ts": "2026-05-01T15:00:00+00:00", "usuario": "admin", "accion": "editar", "entidad": "persona",
         "entidad_id": 3, "detalle": json.dumps({"sexo": {"antes": None, "despues": "M"}, "etiquetas": [1, 2],
                                                 "puesto_votacion": {"antes": None, "despues": "X"}})},
        {"_id": 2, "ts": "2026-05-01T15:00:00+00:00", "usuario": "admin", "accion": "crear", "entidad": "persona",
         "entidad_id": 3, "detalle": json.dumps({"fuente": "manual", "nombre": "X", "telefono": "3001112233",
                                                 "cedula": None})},
        {"_id": 3, "ts": "2026-05-01T15:00:00+00:00", "usuario": "admin", "accion": "editar", "entidad": "persona",
         "entidad_id": 9, "detalle": None},
    ]
    _base_vieja(db, [dict(d) for d in VIEJAS], auditoria=aud)
    migraciones.migrar(db)
    a = {x["_id"]: x for x in db.auditoria.find({"_id": {"$in": [1, 2, 3]}})}
    assert a[1]["campos"] == ["sexo", "etiquetas", "puesto"] and a[1]["completados"] == ["sexo", "puesto"]
    assert a[2]["campos"] == ["nombre", "telefono"] and a[2]["completados"] == ["telefono"]
    assert a[3]["campos"] == [] and a[3]["completados"] == []


def test_una_edicion_entre_lotes_no_se_pierde(bases, monkeypatch):
    db = bases()
    docs = [a_vieja(i, p) for i, p in enumerate(personas_inventadas(30, semilla=3), 1)]
    _base_vieja(db, docs)
    monkeypatch.setattr(migraciones, "LOTE", 7)
    real = migraciones._Migracion.renovar
    llamadas = []

    def renovar(self):
        real(self)
        llamadas.append(self.paso)
        if self.paso == 6 and llamadas.count(6) == 2:  # el código viejo escribe mientras migra
            db.personas.update_one({"_id": 2}, {"$set": {"ocupacion": "Pescadora", "telefono": "3209990000"}})
            db.personas.update_one({"_id": 29}, {"$set": {"sexo": "F", "puesto_votacion": "COLISEO BENITO ARIAS"}})

    monkeypatch.setattr(migraciones._Migracion, "renovar", renovar)
    migraciones.migrar(db)
    p = db.personas.find_one({"_id": 2})
    assert p["ocupacion"] == "Pescadora"
    assert p["telefono"] == "3209990000" and "3209990000" in [t["numero"] for t in p["telefonos"]]
    q = db.personas.find_one({"_id": 29})
    assert q["sexo"] == "F" and q["votacion"]["puesto_id"] == db.puestos.find_one({"codigo": "00-02"})["_id"]
    assert q["puesto_votacion"] == "COLISEO BENITO ARIAS"


def test_turno_con_dueno_reentrada_inmediata_y_espera(bases):
    db = bases()
    t0 = time.monotonic()
    migraciones.migrar(db)
    migraciones.migrar(db)  # la misma base y el mismo proceso: entra de inmediato
    assert time.monotonic() - t0 < 2
    turno = db.meta.find_one({"_id": "migracion"})
    assert turno["hasta"] <= bd._instante()
    # Otro proceso tiene el turno y la base sigue vieja: espera y al agotarse corta con ErrorMigracion
    base_vieja(db)
    db.meta.insert_one({"_id": "migracion", "dueño": "otro-proceso", "hasta": bd._instante() + timedelta(minutes=5)})
    with pytest.raises(migraciones.ErrorMigracion):
        migraciones.migrar(db, espera_s=0.3, pausa_s=0.1)
    # Si el otro ya dejó la base en la versión 2, no espera
    db.meta.update_one({"_id": "esquema"}, {"$set": {"version": 2}}, upsert=True)
    t0 = time.monotonic()
    migraciones.migrar(db, espera_s=5, pausa_s=0.1)
    assert time.monotonic() - t0 < 1
    # Un turno vencido se toma
    db.meta.update_one({"_id": "migracion"}, {"$set": {"hasta": bd._instante() - timedelta(seconds=5)}})
    migraciones.migrar(db, espera_s=0.3, pausa_s=0.1)
    assert db.meta.find_one({"_id": "migracion"})["dueño"] != "otro-proceso"


def test_error_en_un_documento_no_corta_la_migracion(bases):
    db = bases()
    docs = [dict(d) for d in VIEJAS] + [ficha_vieja(4, nombre="INVENTADA RARA", origen="esto no es una lista",
                                                    telefono="3001119999")]
    _base_vieja(db, docs)
    migraciones.migrar(db)
    assert migraciones.version(db) == 2
    errores = db.meta.find_one({"_id": "migracion"}).get("errores") or []
    assert any(e["id"] == 4 for e in errores)
    assert db.personas.find_one({"_id": 1})["telefonos"]


@pytest.mark.skipif(not LENTAS, reason="medición larga: PRUEBAS_LENTAS=1")
def test_medicion_12000_fichas_y_12000_tramites(bases, tmp_path, capsys):
    """Mide la migración de 12 000 fichas viejas y la importación de 12 000 trámites y 700 cédulas inventados."""
    db = bases()
    personas = personas_inventadas(12000, semilla=11)
    docs = [a_vieja(i, p) for i, p in enumerate(personas, 1)]
    for i, d in enumerate(docs):  # trámites con teléfono, como las fichas reales de la base de trámites
        if d["telefono"]:
            d["tramites"] = [{"id_externo": str(900000 + i), "fecha": "2025-06-02", "telefono": d["telefono"]}]
    _base_vieja(db, docs)
    t0 = time.perf_counter()
    hechos = migraciones.migrar(db)
    t_migrar = time.perf_counter() - t0
    assert migraciones.version(db) == 2 and db.personas.count_documents({"telefonos": {"$exists": False}}) == 0
    t0 = time.perf_counter()
    migraciones.migrar(db)
    t_reconciliar = time.perf_counter() - t0

    db2 = bases()
    tramites = tramites_inventados(12000)
    nombres = {}
    for f in tramites:
        nombres.setdefault(f[3].split(" - ", 1)[1], f[6])
    cedulas = [cedula(str(80_000_000 + i), n, t or None) for i, (n, t) in enumerate(list(nombres.items())[:700])]
    t0 = time.perf_counter()
    res = importar(db2, tmp_path, tramites=tramites, cedulas=cedulas, nombre="medicion")
    t_importar = time.perf_counter() - t0
    t0 = time.perf_counter()
    importar(db2, tmp_path, tramites=tramites, cedulas=cedulas, nombre="medicion2")
    t_reimportar = time.perf_counter() - t0
    with capsys.disabled():
        print(f"\nMigración de 12 000 fichas: {t_migrar:.1f} s (reconciliación sola: {t_reconciliar:.2f} s); pasos: "
              f"{ {k: v for k, v in hechos.items() if k != 'reconciliacion'} }")
        print(f"Importación de {len(tramites)} trámites y {len(cedulas)} cédulas: {t_importar:.1f} s "
              f"({res.personas_nuevas} personas, {res.cedulas_unidas_auto} cédulas unidas); "
              f"reimportación igual: {t_reimportar:.1f} s")
    assert t_migrar < 300 and t_importar < 300
