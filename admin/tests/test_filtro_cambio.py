"""Filtro por fecha de creación o modificación (`cambio_tipo`, `cambio_desde`, `cambio_hasta`, `api/filtros.py`): en el
directorio y en la exportación a Excel, con las columnas «Creada el» y «Última actualización». «Modificada» cuenta
`actualizado_en` y cualquier cambio que quedó en la auditoría ese día (no las lecturas); los días son de Colombia."""
import io

import openpyxl
import pytest

from app.api import filtros as F
from conftest import insertar_personas

# 2026-11-20 en Colombia: de 05:00 UTC del 20 a 05:00 UTC del 21
DIA = "2026-11-20"
DENTRO = "2026-11-20T15:00:00+00:00"
NOCHE = "2026-11-21T03:30:00+00:00"      # 22:30 del 20 en Colombia: todavía es el 20
ANTES = "2026-11-19T12:00:00+00:00"
DESPUES = "2026-11-21T06:00:00+00:00"    # 01:00 del 21 en Colombia


@pytest.fixture
def fichas(sesion):
    db = sesion.app.state.db
    nueva, editada, auditada, leida, vieja, noche = insertar_personas(db, [
        {"nombre": "CASIMIRA INVENTADA NUEVA", "consentimiento": "si"},
        {"nombre": "CASIMIRA INVENTADA EDITADA", "consentimiento": "si"},
        {"nombre": "CASIMIRA INVENTADA AUDITADA", "consentimiento": "si"},
        {"nombre": "CASIMIRA INVENTADA LEIDA", "consentimiento": "si"},
        {"nombre": "CASIMIRA INVENTADA VIEJA", "consentimiento": "si"},
        {"nombre": "CASIMIRA INVENTADA NOCHE", "consentimiento": "si"},
    ])
    fechas = {nueva: (DENTRO, DENTRO), editada: (ANTES, DENTRO), auditada: (ANTES, ANTES), leida: (ANTES, ANTES),
              vieja: (ANTES, DESPUES), noche: (NOCHE, NOCHE)}
    for pid, (creado, actualizado) in fechas.items():
        db.personas.update_one({"_id": pid}, {"$set": {"creado_en": creado, "actualizado_en": actualizado}})
    # Un acercamiento ese día (no toca `actualizado_en`) y una lectura de datos sensibles (no es un cambio)
    db.auditoria.insert_many([
        {"ts": DENTRO, "usuario": "admin", "accion": "acercamiento", "entidad": "persona", "entidad_id": auditada},
        {"ts": DENTRO, "usuario": "admin", "accion": "ver_sensibles", "entidad": "persona", "entidad_id": leida},
    ])
    return {"nueva": nueva, "editada": editada, "auditada": auditada, "leida": leida, "vieja": vieja, "noche": noche}


def _ids(sesion, **params):
    r = sesion.get("/api/personas", params={"q": "CASIMIRA", "por_pagina": 100, **params})
    assert r.status_code == 200, r.text
    return {f["id"] for f in r.json()["filas"]}


def test_un_dia_creadas_o_modificadas(sesion, fichas):
    f = fichas
    assert _ids(sesion, cambio_desde=DIA, cambio_hasta=DIA) == {f["nueva"], f["editada"], f["auditada"], f["noche"]}
    assert _ids(sesion, cambio_tipo="creado", cambio_desde=DIA, cambio_hasta=DIA) == {f["nueva"], f["noche"]}
    assert _ids(sesion, cambio_tipo="actualizado", cambio_desde=DIA, cambio_hasta=DIA) == {
        f["nueva"], f["editada"], f["auditada"], f["noche"]}


def test_rangos_abiertos_y_fechas_invalidas(sesion, fichas):
    f = fichas
    # Solo «hasta»: desde siempre (la vieja se creó antes, pero se modificó después); solo «desde»: hasta hoy
    assert f["vieja"] in _ids(sesion, cambio_hasta=DIA)
    assert f["vieja"] not in _ids(sesion, cambio_tipo="actualizado", cambio_hasta=DIA)
    assert f["vieja"] in _ids(sesion, cambio_desde="2026-11-21")
    assert sesion.get("/api/personas", params={"cambio_desde": "20-11-2026"}).status_code == 422
    assert sesion.get("/api/personas", params={"cambio_desde": "2026-11-21", "cambio_hasta": DIA}).status_code == 422


def test_rango_en_utc():
    assert F.rango_cambio(DIA, DIA) == ("2026-11-20T05:00:00+00:00", "2026-11-21T05:00:00+00:00")


def test_exportar_un_dia_con_las_fechas(sesion, fichas):
    f = fichas
    r = sesion.get("/api/exportar.xlsx", params={"q": "CASIMIRA", "cambio_desde": DIA, "cambio_hasta": DIA})
    assert r.status_code == 200, r.text
    filas = list(openpyxl.load_workbook(io.BytesIO(r.content)).active.iter_rows(values_only=True))
    cab, filas = list(filas[0]), [dict(zip(filas[0], x)) for x in filas[1:]]
    assert "Creada el" in cab and "Última actualización" in cab
    assert {x["ID"] for x in filas} == {f["nueva"], f["editada"], f["auditada"], f["noche"]}
    noche = next(x for x in filas if x["ID"] == f["noche"])
    assert noche["Creada el"] == "2026-11-20 22:30"
    # La auditoría de la exportación lleva el rango
    a = sesion.app.state.db.auditoria.find_one({"accion": "exportar"}, sort=[("_id", -1)])
    assert DIA in a["detalle"]


def test_vedado_para_planilleros(como, fichas):
    p = como("planillero")
    assert p.get("/api/personas", params={"cambio_desde": DIA}).status_code == 403
    assert {"cambio_tipo", "cambio_desde", "cambio_hasta"} <= set(F.VEDADOS)


def test_la_fusion_lleva_el_cambio_a_la_ficha_que_queda(sesion, fichas):
    db = sesion.app.state.db
    f = fichas
    # Una ficha unida a «vieja» con un cambio ese día: el cambio aparece en la ficha que queda
    unida = insertar_personas(db, [{"nombre": "CASIMIRA INVENTADA UNIDA"}])[0]
    db.personas.update_one({"_id": unida}, {"$set": {"fusionada_en": f["vieja"], "creado_en": ANTES,
                                                    "actualizado_en": ANTES}})
    db.auditoria.insert_one({"ts": DENTRO, "usuario": "admin", "accion": "editar", "entidad": "persona",
                             "entidad_id": unida})
    ids = _ids(sesion, cambio_tipo="actualizado", cambio_desde=DIA, cambio_hasta=DIA)
    assert f["vieja"] in ids and unida not in ids
