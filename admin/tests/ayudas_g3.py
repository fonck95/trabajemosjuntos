"""Ayudas de las pruebas del grupo 3 (personas, proyección, acercamientos, colas, filtros y tablero). Solo datos
inventados."""
from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import CLAVE_USUARIO, crear_usuario, insertar_personas

# Claves y valores que P y C nunca reciben (3.8, 9.5), salvo `TIPO_Y_LIDERES` en la ficha de P
VEDADAS = {"sensibles", "listas", "lider", "votante", "concejal", "historial", "origen", "procedencia",
           "cedulas_anteriores", "partido", "mesa_testigo", "cedula_en_traspaso", "lideres", "lideres_n", "traidas",
           "intervenciones", "lideres_quitados", "reubicada_por"}
# Lo único de VEDADAS que P sí recibe: el tipo de persona y el «Liderado por», en la raíz de la ficha de una persona de
# su zona o que registró (`proyeccion.tipo_visible`). Nunca en filas, búsquedas, parecidas ni reuniones, nunca para C
TIPO_Y_LIDERES = frozenset({"lider", "votante", "concejal", "lideres"})
# Cada líder del «Liderado por» en la ficha de P: sin quién lo asignó (el usuario de otro miembro del equipo)
CLAVES_LIDER_P = {"id", "nombre", "tipo", "marcado", "asignado_en"}


def persona(db, **campos) -> int:
    """Una ficha inventada (con `bd.nueva_persona`) y su id. Sin cédula, es «adulta conocida» por `tipo_documento`."""
    datos = {"nombre": "PERSONA INVENTADA DE PRUEBA", "consentimiento": "pendiente", **campos}
    pid = insertar_personas(db, [datos])[0]
    if campos:  # tal cual, aunque `nueva_persona` derive o normalice algo
        db.personas.update_one({"_id": pid}, {"$set": campos})
    return pid


def autorizada(db, pid: int, canales=("llamada", "whatsapp", "sms"), **extra) -> None:
    """Deja la ficha con un «sí» que habilita el contacto (los campos derivados de 1.6) y adulta conocida."""
    db.personas.update_one({"_id": pid}, {"$set": {"consentimiento": "si", "contacto_habilitado": True,
                                                   "consentimiento_canales": list(canales), "mayor_declarado": True,
                                                   "tipo_documento": "CC", **extra}})


def contactable(db, nombre: str, telefono: str, **extra) -> int:
    pid = persona(db, nombre=nombre, telefono=telefono, cedula=extra.pop("cedula", None), **extra)
    autorizada(db, pid)
    return pid


def coordinador(app, db) -> TestClient:
    """Un coordinador ingresado (el `crear_usuario` de conftest solo crea P y C: se pasa a coordinador en la base)."""
    u = crear_usuario(db, "planillero")
    nombre = f"coordinador{u['_id']}"
    db.usuarios.update_one({"_id": u["_id"]}, {"$set": {"rol": "coordinador", "usuario": nombre}})
    c = TestClient(app)
    r = c.post("/api/login", json={"usuario": nombre, "clave": CLAVE_USUARIO})
    assert r.status_code == 200, r.text
    c.headers["X-CSRF-Token"] = r.json()["csrf"]
    c.uid, c.usuario = u["_id"], nombre
    return c


def recorrer(x, ruta=""):
    """(ruta, clave, valor) de todo el JSON, de forma recursiva."""
    if isinstance(x, dict):
        for k, v in x.items():
            yield ruta, k, v
            yield from recorrer(v, f"{ruta}.{k}")
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from recorrer(v, f"{ruta}[{i}]")


def sin_vedados(x, contexto="", permitidas=frozenset()):
    """Ninguna clave vedada y los valores «cedulas» y «general» (bases políticas) en ninguna `fuente` o `fuentes`.
    `permitidas`: claves vedadas que sí pueden ir en la raíz de `x` (nunca más adentro)."""
    for ruta, k, v in recorrer(x):
        assert k not in VEDADAS or (ruta == "" and k in permitidas), (contexto, ruta, k)
        if k in ("fuente", "fuentes", "cedula_origen"):
            vals = v if isinstance(v, list) else [v]
            assert "cedulas" not in vals and "general" not in vals, (contexto, ruta, k, v)


def sin_vedados_p(x, contexto=""):
    """Una respuesta para P: lo de `sin_vedados`, salvo el tipo y el «Liderado por» en la raíz (la ficha de una persona
    de su zona o que registró), con sus líderes sin `asignado_por`. Sirve también para filas y listas: en ellas el tipo
    nunca va en la raíz."""
    sin_vedados(x, contexto, permitidas=TIPO_Y_LIDERES)
    if isinstance(x, dict):
        for l in x.get("lideres") or []:
            assert set(l) <= CLAVES_LIDER_P, (contexto, l)


def puesto(db, _id: int, nombre: str, codigo: str, mesas: int | None = 5, **extra) -> dict:
    from app import modelo
    doc = {"_id": _id, "eleccion": modelo.leer_ajustes(db)["eleccion_vigente"], "codigo": codigo, "nombre": nombre,
           "alias": [], "alias_ambiguos": [], "mesas": mesas, "activo": True, **extra}
    db.puestos.insert_one(doc)
    return doc


def tomar(c, pid: int):
    r = c.post(f"/api/trabajo/tomar/{pid}")
    assert r.status_code == 200, r.text
    return r.json()
