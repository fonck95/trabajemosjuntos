"""Ayudas de las pruebas de las herramientas de datos y calidad del asistente (`app/agente/herramientas/fichas.py` y
`app/agente/herramientas/calidad.py`): el contexto de cada rol, correr la tarjeta y la ejecución como el bucle, la
lista de lo que nunca llega al modelo y una foto de la base para probar que la tarjeta no escribe. Solo datos
inventados."""
from __future__ import annotations

import json

import pytest

import ayudas_agente as aa
from ayudas_g3 import autorizada, coordinador, persona, recorrer
from app import db as bd
from app.agente import bucle
from app.agente.herramientas import calidad as hc
from app.agente.herramientas import fichas as hf
from app.agente.herramientas.base import Confirmacion, ErrorHerramienta, Resultado

H = {h.nombre: h for h in hf.HERRAMIENTAS + hc.HERRAMIENTAS}

# Datos inventados de una ficha «rica»: nada de esto puede llegar al modelo
CEDULA, TEL, TEL2, CORREO = "93000555", "3007770011", "3108880022", "anacleta@correo.co"
LISTA, PARTIDO, ETNIA = "Lista Inventada Q9", "partido inventado", "Raizal"
# Claves que nunca salen (además del texto de las señales y las fuentes políticas, que se buscan aparte)
CLAVES_VEDADAS = {"sensibles", "listas", "lista", "lider", "lideres", "votante", "concejal", "fuentes", "origen",
                  "procedencia", "regimen_salud", "cedula", "telefono", "telefono2", "correo", "lat", "lon", "punto",
                  "evidencia_fila", "evidencia", "evidencia_sha256", "datos_dictados", "uid", "clave_migracion",
                  "fecha_nacimiento", "direccion", "descripcion", "respuesta", "creado_por", "texto"}
VALORES_VEDADOS = (CEDULA, TEL, TEL2, CORREO, LISTA, PARTIDO, ETNIA, "base general", "la base con cédula")


def sin_datos(x, *otros: str, claves: set[str] | None = None) -> None:
    """Ninguna clave vedada en todo el JSON, ningún valor vedado y ninguna fuente política («general», «cedulas»)."""
    vedadas = CLAVES_VEDADAS if claves is None else claves
    for ruta, k, v in recorrer(x):
        assert k not in vedadas, (ruta, k)
        if k in ("fuente", "tipo"):
            vals = v if isinstance(v, list) else [v]
            assert "cedulas" not in vals and "general" not in vals, (ruta, k, v)
    texto = json.dumps(x, ensure_ascii=False, default=str)
    for v in (*VALORES_VEDADOS, *otros):
        assert v not in texto, v
    assert '"general"' not in texto and '"cedulas"' not in texto


def modelo(r: Resultado):
    """Lo que de verdad ve el modelo: el texto del tool_result."""
    return json.loads(r.texto_para_modelo())


@pytest.fixture
def ctx_de(sesion):
    """`ctx_de(cliente, **kw)`: el contexto de herramienta con la sesión de ese cliente; se cierra al terminar."""
    abiertos = []

    def hacer(cli, **kw):
        c = aa.contexto(sesion.app, cli, **kw)
        abiertos.append(c)
        return c

    yield hacer
    for c in abiertos:
        aa.correr(sesion, c.api.cerrar)


def leer(sesion, ctx, nombre: str, entrada: dict) -> Resultado:
    return aa.correr(sesion, aa.ejecutar, H[nombre], ctx, entrada)


def falla(sesion, fn, *args) -> ErrorHerramienta:
    with pytest.raises(ErrorHerramienta) as e:
        aa.correr(sesion, fn, *args)
    return e.value


def falla_leer(sesion, ctx, nombre: str, entrada: dict) -> ErrorHerramienta:
    return falla(sesion, aa.ejecutar, H[nombre], ctx, entrada)


def falla_tarjeta(sesion, ctx, nombre: str, entrada: dict) -> ErrorHerramienta:
    return falla(sesion, aa.confirmar, H[nombre], ctx, entrada)


def tarjeta(sesion, ctx, nombre: str, entrada: dict):
    """Como el bucle: valida, arma la tarjeta y guarda la entrada tal como quedó (con las huellas que le puso
    `confirmar`). Devuelve (tarjeta, entrada guardada ya validada)."""
    h = H[nombre]
    a = h.validar(entrada)
    conf = aa.correr(sesion, h.confirmar, ctx, a)
    assert isinstance(conf, Confirmacion) and conf.titulo and conf.detalle
    bucle._tarjeta(conf)  # cabe en la tarjeta y se ve como es
    return conf, h.validar(bucle._entrada_pendiente(h, a, entrada))


def ejecutar(sesion, ctx, nombre: str, guardada) -> Resultado:
    return aa.correr(sesion, H[nombre].ejecutar, ctx, guardada)


def falla_ejecutar(sesion, ctx, nombre: str, guardada) -> ErrorHerramienta:
    return falla(sesion, H[nombre].ejecutar, ctx, guardada)


COLECCIONES = ("personas", "coincidencias", "conflictos_cedula", "solicitudes", "acercamientos", "autorizaciones",
               "reuniones", "lugares", "auditoria", "importaciones")


def foto(db) -> str:
    """Todo lo que una escritura podría cambiar (no las lecturas registradas ni las sesiones)."""
    return json.dumps({c: list(db[c].find({}, sort=[("_id", 1)])) for c in COLECCIONES}, default=str,
                      sort_keys=True)


def escribe_una_vez(sesion, ctx, nombre: str, entrada: dict, cambia):
    """La tarjeta no escribe nada; aprobar escribe (`cambia(db)` lo comprueba); aprobar otra vez (el mismo `tool_use`,
    un reintento) no vuelve a escribir. Devuelve (tarjeta, primer resultado, segundo resultado)."""
    db = sesion.app.state.db
    antes = foto(db)
    conf, guardada = tarjeta(sesion, ctx, nombre, entrada)
    assert foto(db) == antes, f"{nombre}: la tarjeta escribió"
    r1 = ejecutar(sesion, ctx, nombre, guardada)
    despues = foto(db)
    assert despues != antes, f"{nombre}: no escribió"
    cambia(db)
    r2 = ejecutar(sesion, ctx, nombre, guardada)
    assert foto(db) == despues, f"{nombre}: repetir la aprobación volvió a escribir"
    for r in (r1, r2):
        assert isinstance(r, Resultado) and r.resumen
        sin_datos(modelo(r))
    return conf, r1, r2


def rica(db, **extra) -> int:
    """Una ficha inventada con todo lo que el modelo no debe recibir (listas, líder, datos sensibles, las bases
    políticas, la cédula y los teléfonos completos, el correo, coordenadas), autorizada."""
    campos = dict(
        nombre="ANACLETA INVENTADA RICA", cedula=CEDULA, telefono=TEL, telefono2=TEL2, tipo_documento="CC",
        correo=CORREO, lider=True, listas=[LISTA], sensibles={"etnia": ETNIA}, fuentes=["tramites", "general"],
        origen=[{"fuente": "general", "datos": {"partido": PARTIDO}}],
        telefonos=[{"numero": TEL, "tipo": "celular", "fuentes": ["general"], "estado": "confirmado",
                    "no_contactar": False},
                   {"numero": TEL2, "tipo": "celular", "fuentes": ["tramites"], "estado": "confirmado",
                    "no_contactar": False}],
        lat=7.0011, lon=-73.9122, direccion="CALLE 50 # 48-21", regimen_salud="Subsidiado", edad=40, sexo="F",
        observaciones=f"Llamar al {TEL}")
    campos.update(extra)
    pid = persona(db, **campos)
    autorizada(db, pid)
    return pid


def roles(sesion, como) -> dict:
    """{rol: (cliente, quien)} para A, K, P y C."""
    app, db = sesion.app, sesion.app.state.db
    k = coordinador(app, db)
    p, c = como("planillero"), como("consultor")
    return {"admin": (sesion, aa.quien_de(app, 0)), "coordinador": (k, aa.quien_de(app, k.uid)),
            "planillero": (p, aa.quien_de(app, p.uid)), "consultor": (c, aa.quien_de(app, c.uid))}


def coincidencia(db, a: int, b: int, **extra) -> int:
    """Un par pendiente de la cola de coincidencias."""
    cid = bd.siguiente_id(db, "coincidencias")
    db.coincidencias.insert_one({"_id": cid, "persona_id": a, "candidato_id": b, "puntaje": 0.93,
                                 "estado": "pendiente", "motivo": "nombre_telefono", "detalle": {}, **extra})
    return cid
