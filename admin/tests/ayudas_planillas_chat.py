"""Ayudas de las pruebas de las planillas físicas en el chat (área B2): subir una foto inventada a la bandeja y dejarla
leída con un proveedor del modelo falso, sin tocar el proveedor del chat (que en las pruebas de turno completo es la
Messages API simulada de `ayudas_agente.encender`), y correr una escritura como la corre el bucle. Solo personas y
fotos inventadas."""
from __future__ import annotations

import json

from app import planillas as pl
from app.agente import bucle, proveedores
from ayudas_agente import correr
from ayudas_planillas import ProveedorFalso, jpeg, leer, lectura_json, subir


def roles_planillas(app, *roles: str) -> None:
    """Quiénes suben fotos (`agente_planillas.roles`)."""
    app.state.db.meta.update_one({"_id": "ajustes"}, {"$set": {"agente_planillas": {
        "roles": list(roles), "retencion_horas": 24, "otros_formatos": False}}}, upsert=True)


def subir_sin_leer(c, monkeypatch, datos: bytes | None = None) -> str:
    """Sube una foto con el cliente `c` y la deja «leyendo» (la lectura de fondo no se encola). Si la app no tiene
    modelo (sin `ayudas_agente.encender`), finge uno solo para la subida."""
    with monkeypatch.context() as m:
        m.setattr(pl, "programar", lambda *a, **k: None)
        if proveedores.clave_para_nueva(c.app.state.cfg, c.app.state.db) is None:
            m.setattr(proveedores, "clave_para_nueva", lambda cfg, db: "anthropic")
        r = subir(c, datos or jpeg())
    assert r.status_code == 201, r.text
    return r.json()["id"]


def leer_con(cliente, monkeypatch, pid: str, texto: str) -> None:
    """Corre la lectura de fondo de `pid` con un proveedor falso que responde `texto` (solo durante la lectura)."""
    falso = ProveedorFalso(texto)
    with monkeypatch.context() as m:
        m.setattr(proveedores, "para_nueva", lambda app_, cfg, db: falso)
        leer(cliente, pid)


def foto_leida(cliente, c, monkeypatch, filas: list[dict], *, datos: bytes | None = None, **kw) -> str:
    """Una planilla subida por `c` y leída con estas filas (`ayudas_planillas.fila`): devuelve su id."""
    pid = subir_sin_leer(c, monkeypatch, datos)
    leer_con(cliente, monkeypatch, pid, lectura_json(filas, **kw))
    estado = cliente.app.state.db.planillas.find_one({"_id": pid}, {"estado": 1})["estado"]
    assert estado == "leida", estado
    return pid


def foto_distinta(n: int) -> bytes:
    """Fotos inventadas distintas entre sí (otro SHA-256: la bandeja no las toma por repetidas)."""
    return jpeg(1200 + n, 900)


def tarjeta_y_ejecutar(cliente, h, ctx, entrada: dict):
    """Una escritura como la corre el bucle: valida, arma la tarjeta (`confirmar`, que también tiene que caber en la
    tarjeta del bucle), guarda la entrada que quedó (con sus huellas) y la ejecuta. Devuelve (tarjeta, resultado)."""
    a = h.validar(entrada)
    conf = correr(cliente, h.confirmar, ctx, a)
    tarjeta = bucle._tarjeta(conf)
    guardada = h.validar(bucle._entrada_pendiente(h, a, entrada))
    res = correr(cliente, h.ejecutar, ctx, guardada)
    return conf, tarjeta, guardada, res


def al_modelo(res) -> dict:
    """Lo que el modelo recibe de un resultado (el JSON recortado como lo manda el bucle)."""
    return json.loads(res.texto_para_modelo())
