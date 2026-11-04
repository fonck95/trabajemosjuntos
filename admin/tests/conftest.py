"""Pruebas del panel. Usan solo datos inventados: nunca datos reales de personas.

Las pruebas de la API necesitan un MongoDB (TEST_MONGODB_URI, por defecto mongodb://127.0.0.1:27017); si no hay,
se omiten. Cada prueba usa una base de datos propia que se borra al terminar.

Este archivo está congelado desde el paso 0 de la ampliación (usuarios, acercamientos, zonas…): los grupos agregan sus
pruebas en archivos nuevos y no lo cambian.
"""
import os
import random
import sys
import uuid
from datetime import date
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
# Las mediciones largas (p. ej. migrar 12 000 fichas) corren solo con PRUEBAS_LENTAS=1
LENTAS = os.environ.get("PRUEBAS_LENTAS") == "1"
CLAVE_USUARIO = "clave-de-usuario-de-prueba"  # clave de los usuarios que crea `como` (y `crear_usuario`)


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
    import pymongo
    app = crear_app(cfg)
    try:
        with TestClient(app) as c:
            yield c
    finally:  # aunque falle el arranque o la prueba, no deja bases prueba_* huérfanas
        with pymongo.MongoClient(URI, serverSelectionTimeoutMS=3000) as m:
            m.drop_database(cfg.mongodb_db)


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


def crear_usuario(db, rol: str, clave: str = CLAVE_USUARIO, **campos) -> dict:
    """Inserta un planillero o consultor activo, con la clave ya cambiada y el compromiso vigente aceptado, y devuelve
    su documento. `campos` pisa los del documento (`usuario`, `nombre`, `asignacion`, `activo`, `telefono`…)."""
    from app import db as bd
    from app import modelo
    from app.acceso import hashear_clave
    if rol not in ("planillero", "consultor"):
        raise ValueError(f"Rol de usuario desconocido: {rol}")
    uid = bd.siguiente_id(db, "usuarios")
    ahora = bd.ahora()
    doc = {"_id": uid, "usuario": f"{rol}{uid}", "nombre": f"{rol.capitalize()} de prueba {uid}", "rol": rol,
           "activo": True, "clave": hashear_clave(clave), "version": 1, "debe_cambiar_clave": False,
           "clave_temporal_vence": None, "compromiso_version": modelo.leer_ajustes(db)["compromiso_version"],
           "compromiso_en": ahora, "telefono": None, "asignacion": {"lugares": [], "areas": []}, "creado_por": 0,
           "creado_en": ahora, "actualizado_en": ahora, "ultimo_ingreso": None, "desactivado_en": None, **campos}
    db.usuarios.insert_one(doc)
    return doc


def _hay_ruta(app, metodo: str, ruta: str) -> bool:
    from fastapi.routing import APIRoute
    return any(isinstance(r, APIRoute) and r.path == ruta and metodo in r.methods for r in app.routes)


@pytest.fixture
def como(cliente, cfg):
    """`como(rol, **campos)`: un TestClient nuevo, con la sesión de ese rol y su CSRF, sobre la misma aplicación y la
    misma base que `cliente` y `sesion` (cada cliente tiene sus propias cookies).

    * «planillero» o «consultor»: crea el usuario con `crear_usuario(db, rol, **campos)` (`clave=` es la clave en
      claro) e ingresa con él. Se salta mientras la aplicación no tenga POST /api/usuarios (los usuarios llegan con el
      grupo 2); un ingreso rechazado no se salta: falla.
    * «admin»: ingresa con la credencial de `.env` (no usa `campos`).
    El cliente trae `.uid`, `.usuario` y `.rol`."""
    from fastapi.testclient import TestClient
    app = cliente.app
    abiertos = []

    def entrar(rol: str, **campos):
        if rol == "admin":
            uid, usuario, clave = 0, cfg.usuario, cfg.clave
        elif rol in ("planillero", "consultor"):
            if not _hay_ruta(app, "POST", "/api/usuarios"):
                pytest.skip("requiere el grupo 2")
            clave = campos.pop("clave", CLAVE_USUARIO)
            u = crear_usuario(app.state.db, rol, clave, **campos)
            uid, usuario = u["_id"], u["usuario"]
        else:
            raise ValueError(f"Rol desconocido: {rol}")
        c = TestClient(app)
        abiertos.append(c)
        r = c.post("/api/login", json={"usuario": usuario, "clave": clave})
        assert r.status_code == 200, r.text
        c.headers["X-CSRF-Token"] = r.json()["csrf"]
        c.uid, c.usuario, c.rol = uid, usuario, rol
        return c

    yield entrar
    for c in abiertos:
        c.close()


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


# Planilla de campo (hoja «Planilla», encabezados en la fila 1), como la plantilla de GET /api/plantillas/planilla.xlsx
COLUMNAS_PLANILLA = [
    "Cédula", "Repita la cédula", "Tipo de documento", "Nombre completo", "Celular", "Otro teléfono", "Sexo",
    "Fecha de nacimiento", "Edad", "Dirección", "Barrio o vereda", "Puesto de votación", "Mesa", "Autorización de datos",
    "Medio de la autorización", "Canales autorizados", "Mayor de 18", "Planillero (usuario)", "Fecha", "Observaciones",
]


def excel_planilla(ruta: Path, filas: list[tuple]) -> Path:
    """Una planilla de campo con las `filas` (tuplas en el orden de COLUMNAS_PLANILLA)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Planilla"
    ws.append(COLUMNAS_PLANILLA)
    for f in filas:
        assert len(f) == len(COLUMNAS_PLANILLA), f
        ws.append(list(f))
    wb.save(ruta)
    return ruta


# Personas inventadas de una planilla. Los valores de las listas desplegables son las etiquetas de app/modelo.py.
# «ana.campo» es un planillero que la prueba debe crear (p. ej. `como("planillero", usuario="ana.campo")`);
# «pedro.inexistente» no existe
PLANILLA = [
    # Tres teléfonos (dos en «Otro teléfono»), puesto del catálogo con su mesa y fecha de nacimiento
    ("90000101", "90000101", "CC", "HERMELINDA PATROCINIA OSPINO VILLAREAL", "3101234501", "3101234502 / 6047001234",
     "Mujer", date(1979, 3, 14), None, "CALLE 50 # 48-21", "TRES DE OCTUBRE", "IE LUIS EDUARDO DIAZ SECCION PRIMARIA", 12,
     "Sí autoriza", "Escrito", "Llamada, WhatsApp", "Sí", "ana.campo", date(2026, 11, 2), None),
    # Cédula que en la base con cédula (CEDULAS) es de EUSEBIO JOHN CARVAJALINO: nombre distinto. Mesa 40 en un puesto
    # de 4 mesas
    ("90000003", "90000003", "CC", "MARCO TULIO RENTERIA PALOMEQUE", "3101234511", None, "Hombre", None, 47,
     "VEREDA LA CONDOR FINCA EL RECREO", "LA CONDOR", "COLISEO BENITO ARIAS", 40, "Sí autoriza", "Verbal presencial",
     "Llamada", "Sí", "ana.campo", date(2026, 11, 2), None),
    # Sin cédula, con un planillero que no existe y la mesa escrita como texto
    (None, None, None, "ROSAURA DEL CARMEN BOHORQUEZ TAPIAS", "3101234521", None, "Mujer", None, 62,
     "CASERIO SAN MIGUEL DEL TIGRE CASA 4", "SAN MIGUEL DEL TIGRE", "I.E.R. SAN MIGUEL DEL TIGRE", "Mesa # 3",
     "Sí autoriza", "Formulario", "WhatsApp", "Sí", "pedro.inexistente", date(2026, 11, 3), None),
    # Cédula y repetición distintas (posible error de digitación) y un puesto ambiguo
    ("90000121", "90000112", "CC", "ABELARDO SEGUNDO MONTIEL CUESTA", "3101234531", None, "Hombre", date(1968, 8, 1), 58,
     "CALLE 52 # 45-10", "EL PRADO", "CABECERA MUNICIPAL", 5, "Sí autoriza", "Escrito", "Llamada, SMS", "Sí",
     "ana.campo", date(2026, 11, 3), None),
    # No autoriza
    ("90000131", "90000131", "CC", "CENOBIA ESTHER PACHECO ARRIETA", "3101234541", None, "Mujer", None, 55,
     "CALLE 49 # 47-03", "TRES DE OCTUBRE", None, None, "No autoriza", None, None, None, "ana.campo", date(2026, 11, 3),
     None),
    # Menor con tarjeta de identidad
    ("1012345678", "1012345678", "TI", "BRAYAN STIVEN OSPINO PACHECO", "3101234551", None, "Hombre", date(2012, 5, 20), 14,
     "CALLE 49 # 47-03", "TRES DE OCTUBRE", None, None, "Sí autoriza", "Escrito", "Llamada", "No", "ana.campo",
     date(2026, 11, 3), "Hijo de la anterior"),
]


# ───────── Muchas personas inventadas (mediciones, zonas, presupuestos) ─────────

_NOMBRES = ("ABIGAIL", "BALTAZAR", "CELMIRA", "DAMASO", "EDELMIRA", "FILOMENO", "GUMERCINDA", "HERMOGENES", "ISOLINA",
            "JACINTO", "LEOCADIA", "MARCELIANO", "NICASIA", "OBDULIO", "PRUDENCIA", "RIGOBERTO", "SATURNINA",
            "TELESFORO", "URSULINA", "VALERIANO")
_APELLIDOS = ("ARRIETA", "BOHORQUEZ", "CUESTA", "DUARTE", "ESPITIA", "FONSECA", "GALINDO", "HURTADO", "IBARGUEN",
              "JARAMILLO", "LOZANO", "MONTIEL", "NARVAEZ", "OSPINO", "PACHECO", "QUINTANA", "RENTERIA", "SALCEDO",
              "TAPIAS", "VILLAREAL")
_PUESTOS = (None, "IE LUIS EDUARDO DIAZ SECCION PRIMARIA", "CABECERA MUNICIPAL", "I.E.R. SAN MIGUEL DEL TIGRE")
CASCO = (-73.9112, 7.0062)  # centro del casco urbano (lon, lat)


def personas_inventadas(n: int, semilla: int = 0) -> list[dict]:
    """`n` personas inventadas con los campos de una ficha vieja, siempre las mismas para la misma semilla (0 a 99):
    nombre, cédula (2 de cada 3), teléfono (4 de cada 5), sexo, edad, dirección, puesto y mesa como texto,
    autorización y ubicación (3 de cada 4, a menos de 1 km del centro del casco urbano). Cédulas y teléfonos no se
    repiten entre personas ni entre semillas distintas."""
    rnd = random.Random(semilla)
    out = []
    for i in range(n):
        nombres = [rnd.choice(_NOMBRES)] + ([rnd.choice(_NOMBRES)] if rnd.random() < 0.5 else [])
        puesto = rnd.choice(_PUESTOS)
        ubicada = rnd.random() < 0.75
        out.append({
            "nombre": " ".join([*nombres, rnd.choice(_APELLIDOS), rnd.choice(_APELLIDOS)]),
            "cedula": str(70_000_000 + semilla * 1_000_000 + i) if i % 3 else None,
            "telefono": str(3_150_000_000 + semilla * 1_000_000 + i) if i % 5 else None,
            "sexo": rnd.choice(("F", "M", None)),
            "edad": rnd.choice((None, rnd.randint(18, 90), rnd.randint(18, 90))),
            "direccion": f"CALLE {rnd.randint(40, 60)} # {rnd.randint(40, 60)}-{rnd.randint(1, 99):02d}",
            "puesto_votacion": puesto, "mesa": f"Mesa # {rnd.randint(1, 12)}" if puesto else None,
            "consentimiento": rnd.choice(("pendiente", "pendiente", "si", "no")),
            "lat": round(CASCO[1] + rnd.uniform(-0.008, 0.008), 6) if ubicada else None,
            "lon": round(CASCO[0] + rnd.uniform(-0.008, 0.008), 6) if ubicada else None,
            "geo_precision": "direccion" if ubicada else None,
        })
    return out


def insertar_personas(db, datos: list[dict], fuente: str = "manual") -> list[int]:
    """Inserta las fichas con `bd.nueva_persona` (ids reservados de una vez, `completitud` y `punto` calculados) y
    devuelve sus ids, en el mismo orden."""
    from app import db as bd
    from app import modelo
    datos = list(datos)
    if not datos:
        return []
    primero = bd.siguiente_id(db, "personas", len(datos))
    docs = []
    for i, d in enumerate(datos):
        doc = bd.nueva_persona(db, {**d, "_id": primero + i}, fuente)
        if doc.get("punto") is None:
            doc["punto"] = modelo.punto(doc.get("lat"), doc.get("lon"))
        doc["completitud"] = bd.completitud(doc)
        docs.append(doc)
    db.personas.insert_many(docs)
    return [d["_id"] for d in docs]
