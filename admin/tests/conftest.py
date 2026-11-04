"""Pruebas del panel. Usan solo datos inventados: nunca datos reales de personas.

Las pruebas de la API necesitan un MongoDB (TEST_MONGODB_URI, por defecto mongodb://127.0.0.1:27017); si no hay,
se omiten. Cada prueba usa una base de datos propia que se borra al terminar.
"""
import os
import sys
import uuid
from pathlib import Path

import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

URI = os.environ.get("TEST_MONGODB_URI", "mongodb://127.0.0.1:27017")


def _mongo_disponible() -> bool:
    try:
        import pymongo
        pymongo.MongoClient(URI, serverSelectionTimeoutMS=1500).admin.command("ping")
        return True
    except Exception:
        return False


MONGO = _mongo_disponible()


@pytest.fixture
def cfg():
    from app.config import Config
    return Config(usuario="admin", clave="clave-de-prueba-larga", mongodb_uri=URI, mongodb_db=f"prueba_{uuid.uuid4().hex[:10]}",
                  horas_sesion=1, cookie_segura=False, max_subida_mb=5)


@pytest.fixture
def cliente(cfg):
    if not MONGO:
        pytest.skip("No hay MongoDB para las pruebas de la API")
    from fastapi.testclient import TestClient
    from app.main import crear_app
    app = crear_app(cfg)
    with TestClient(app) as c:
        yield c
        app.state.cliente.drop_database(cfg.mongodb_db)


@pytest.fixture
def sesion(cliente):
    r = cliente.post("/api/login", json={"usuario": "admin", "clave": "clave-de-prueba-larga"})
    assert r.status_code == 200, r.text
    cliente.headers["X-CSRF-Token"] = r.json()["csrf"]
    return cliente


@pytest.fixture
def bases():
    """Crea bases de datos nuevas e inicializadas (para usar el pipeline sin la API) y las borra al terminar."""
    if not MONGO:
        pytest.skip("No hay MongoDB para las pruebas de la base")
    import pymongo
    from app import db as bd
    cli = pymongo.MongoClient(URI, tz_aware=True)
    creadas = []

    def nueva():
        b = cli[f"prueba_{uuid.uuid4().hex[:10]}"]
        creadas.append(b.name)
        bd.inicializar(b)
        return b

    yield nueva
    for n in creadas:
        cli.drop_database(n)
    cli.close()


def excel_tramites(ruta: Path, filas: list[tuple]) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Table"
    ws.append(["ID", "Número", "Fecha", "Nombre Solicitante", "Dirección", "Correo", "Teléfono", "Paquete"])
    for f in filas:
        ws.append(list(f))
    wb.save(ruta)
    return ruta


def excel_cedulas(ruta: Path, filas: list[tuple]) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Base unificada"
    ws.append(["N°", "Cédula", "Nombre completo", "Teléfono(s)", "Correo", "Municipio", "Puesto de votación", "Mesa donde vota",
               "Mesa como testigo", "Partido / grupo", "Edad (según fuente)", "Sexo", "Dirección", "Detalle", "Lista(s)"])
    for i, f in enumerate(filas, 1):
        ws.append([i, *f])
    wb.save(ruta)
    return ruta


# Personas inventadas
TRAMITES = [
    ("1001", "0589300000001", "2/6/2025 12:00:00 AM", "NUEVA ENCUESTA - ZOILA ESPERANZA QUINTERO BARRAGAN", "BARRIO TRES DE OCTUBRE CALLE 49 # 45  12", "ZOILA@GMAIL.COMK", "3001112233", 1),
    ("1002", "0589300000001", "3/7/2025 12:00:00 AM", "REENCUESTA - ZOILA ESPERANZA QUINTERO BARRAGAN", "BARRIO TRES DE OCTUBRE CALLE 49 # 45  12", "", "3001112233", 1),
    ("1003", "0589300000002", "4/8/2025 12:00:00 AM", "MODIFICACIÓN DE FICHA - ARQUIMEDES PANTOJA RIVADENEIRA", "VEREDA X-10 FINCA LOS ALMENDROS", "", "3014445566", 2),
    ("1004", "0589300000003", "5/9/2025 12:00:00 AM", "NUEVA ENCUESTA - ROSALBA QUIÑONES ZAPATEIRO", "VEREDA SAN LUIS BELTRAN EN EL CASERIO", "", "3027778899", 2),
    ("1005", "0589300000004", "6/9/2025 12:00:00 AM", "NUEVA ENCUESTA - EUSEBIO JHON CARVAJALINO", "JORGE ELIECER GAITAN, KR 54# 51-20 FRENTE AL PARQUE", "", "3039990000", 3),
]
CEDULAS = [
    ("90000001", "ZOILA ESPERANZA QUINTERO BARRAGAN", "3001112233", None, "YONDÓ", "CABECERA MUNICIPAL", "Mesa # 3", None, None, 41, "F", None, None, "Lista A"),
    ("90000002", "YURANI ANDREA QUIÑONES ZAPATEIRO", "3027778899", None, None, None, None, None, None, 19, "F", "VEREDA SAN LUIS BELTRAN", None, "Lista B"),
    ("90000003", "EUSEBIO JOHN CARVAJALINO", None, None, None, None, None, None, None, 52, "M", None, None, "Lista A"),
    ("90000004", "PERSONA SOLO CON CEDULA", "3045556677", None, None, None, None, None, None, None, None, "VEREDA LA CONDOR", None, "Lista C"),
]
