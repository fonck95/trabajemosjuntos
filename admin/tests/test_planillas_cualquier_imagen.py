"""Cualquier foto se lee (docs/agente.md, «Planillas físicas por foto»): el lector (app/agente/lector_planillas.py)
siempre describe la imagen (`descripcion`, `datos_personales`) y transcribe las filas de toda hoja que liste personas
(ya sin el ajuste `agente_planillas.otros_formatos`, retirado); una foto sin filas queda «leida» con su descripción
(con el aviso «sin_filas» si es una hoja), y una cédula se sigue rechazando y borrando. La bandeja
(app/planillas.py, app/api/planillas.py) guarda la descripción cifrada, la muestra entera a A y K y enmascarada al
modelo (`minimizar.enmascarar_descripcion`), y cotejar o cargar una foto sin filas responde 422 `sin_filas`. Con un
proveedor del modelo falso (sin red) e imágenes inventadas. Solo datos inventados."""
import inspect
import json

import pytest

from app import planillas as pl
from app.agente import cifrado, minimizar, politica
from app.agente import lector_planillas as lp
from ayudas_g3 import coordinador
from ayudas_planillas import ProveedorFalso, encender, fila, jpeg, lectura_json, leer, subir

ANA = dict(cedula="90000101", cedula_repetida="90000101", nombre="ANA INVENTADA RUIZ", celular="3101234501",
           autorizacion="si", medio="escrito", canales="llamada", barrio="TRES DE OCTUBRE")
AFICHE = ("Foto de un afiche pegado en una pared: anuncia una jornada de vacunación de mascotas el 30/11/2026 en el "
          "parque principal.\n\nDice: «Informes al 310 123 4567 o a jornadas.yondo@correo-inventado.com»")


def _codigo(texto, **kw):
    with pytest.raises(lp.ErrorLectura) as e:
        lp.interpretar(texto, **kw)
    return e.value.codigo, e.value.borrar_foto


# ───────────────────────────── El lector ─────────────────────────────

def test_una_foto_cualquiera_se_describe_sin_filas():
    lec = lp.interpretar(lectura_json([], tipo="otro", visibles=0, descripcion=AFICHE, datos_personales=False))
    assert lec.tipo_formato == "otro" and lec.filas == [] and lec.filas_visibles == 0 and lec.aviso is None
    assert lec.descripcion == AFICHE and lec.datos_personales is False and not lec.incompleta
    # Sin `filas_visibles` ni `filas` (una foto que no lista personas): igual se lee
    sin_filas = json.loads(lectura_json([], tipo="otro", descripcion="Una foto de un río al atardecer."))
    del sin_filas["filas_visibles"], sin_filas["filas"]
    lec = lp.interpretar(json.dumps(sin_filas))
    assert lec.filas == [] and lec.filas_visibles == 0 and lec.descripcion == "Una foto de un río al atardecer."
    # `datos_personales`, solo con un true de verdad
    assert lp.interpretar(lectura_json([], tipo="otro", descripcion="x", datos_personales=True)).datos_personales
    assert not lp.interpretar(lectura_json([], tipo="otro", descripcion="x")).datos_personales
    crudo = json.loads(lectura_json([], tipo="otro", descripcion="x"))
    crudo["datos_personales"] = "true"
    assert lp.interpretar(json.dumps(crudo)).datos_personales is False


def test_una_hoja_sin_filas_leidas_lleva_el_aviso():
    for tipo in lp.HOJAS:
        lec = lp.interpretar(lectura_json([], tipo=tipo, visibles=12, descripcion="Una planilla borrosa."))
        assert lec.filas == [] and lec.aviso == "sin_filas" and lec.filas_visibles == 12, tipo
    assert lp.AVISOS["sin_filas"] and set(lp.HOJAS) == {"planilla_campo", "asistencia", "consulta_puesto"}
    # Con filas, sin aviso; un tipo desconocido cuenta como «otro»
    lec = lp.interpretar(lectura_json([fila(1, **ANA)], tipo="asistencia", descripcion="Lista de asistencia."))
    assert lec.aviso is None and lec.descripcion == "Lista de asistencia." and lec.filas[0]["n"] == 1
    lec = lp.interpretar(lectura_json([], tipo="factura", descripcion="Una factura."))
    assert lec.tipo_formato == "otro" and lec.aviso is None


def test_una_cedula_se_sigue_rechazando_y_borrando():
    texto = lectura_json([], tipo="documento_identidad", visibles=0, descripcion="Un documento de identidad.",
                         datos_personales=True)
    assert _codigo(texto) == ("documento_identidad", True)
    assert "cédulas" in lp.MENSAJES["documento_identidad"]


def test_sin_descripcion_ni_filas_no_se_leyo_nada():
    assert _codigo(lectura_json([], tipo="otro", visibles=0)) == ("respuesta", False)
    assert _codigo(lectura_json([], tipo="otro", visibles=0, descripcion="  ​ \n ")) == ("respuesta", False)
    assert _codigo(lectura_json([], descripcion="Algo", imagen_visible=False)) == ("sin_imagen", False)
    # Filas sin decir cuántas se ven: no se puede saber si las inventó
    sin_visibles = json.loads(lectura_json([fila(1, **ANA)], descripcion="Una planilla."))
    del sin_visibles["filas_visibles"]
    assert _codigo(json.dumps(sin_visibles)) == ("respuesta", False)


def test_la_descripcion_se_sanea():
    d = lp.descripcion_de
    assert d("Café con   leche\t y pan ") == "Café con leche y pan"  # NFC y espacios en uno
    assert d("uno\r\ndos\rtres cuatro") == "uno\ndos\ntres\ncuatro"
    assert d("a​b‮c\x00d\x07e") == "a b c d e"   # invisibles, bidi y de control: un espacio
    assert d("párrafo 1\n\n\n\n  párrafo 2  \n") == "párrafo 1\n\npárrafo 2"  # como mucho una línea en blanco
    assert d("x" * (lp.DESCRIPCION_MAX + 50)) == "x" * lp.DESCRIPCION_MAX
    for no in (None, 12, ["a"], {"a": 1}, True):
        assert d(no) == ""
    lec = lp.interpretar(lectura_json([], tipo="otro", descripcion="Línea 1‎\r\n\r\n\r\nLínea 2"))
    assert lec.descripcion == "Línea 1\n\nLínea 2"


def test_si_se_corta_la_descripcion_sobrevive():
    filas = [fila(n, nombre=f"PERSONA INVENTADA {n}", cedula=f"9100{n:04d}") for n in range(1, 6)]
    entero = lectura_json(filas, visibles=9, descripcion="Planilla de campo del 02/11/2026 con 9 filas.")
    # Cortada en la tercera fila: la descripción y las dos primeras filas
    lec = lp.interpretar(entero[:entero.index('"PERSONA INVENTADA 3"') + 4], "max_tokens")
    assert lec.incompleta and [f["n"] for f in lec.filas] == [1, 2] and lec.ultima_fila == 2
    assert lec.descripcion == "Planilla de campo del 02/11/2026 con 9 filas." and lec.aviso is None
    # Cortada antes de la primera fila (en las columnas): queda la descripción, sin filas e incompleta
    lec = lp.interpretar(entero[:entero.index('"columnas"') + 20], "max_tokens")
    assert lec.filas == [] and lec.incompleta and lec.ultima_fila is None and lec.aviso == "sin_filas"
    assert lec.descripcion.startswith("Planilla de campo")
    # Cortada dentro de la descripción: nada que salvar
    assert _codigo(entero[:entero.index("con 9 filas")], fin="max_tokens") == ("lectura_cortada", False)


def test_las_instrucciones_piden_la_descripcion_antes_de_las_filas():
    s = lp.instrucciones()
    ejemplo = s[s.index('{"imagen_visible"'):]
    orden = [ejemplo.index(f'"{k}"') for k in ("imagen_visible", "tipo_formato", "descripcion", "datos_personales",
                                                 "filas_visibles", "encabezado", "columnas", "filas")]
    assert orden == sorted(orden)  # `_rescatar` salva todo lo que va antes de "filas"
    for parte in ("cualquier tipo", "1500 caracteres", "nunca quién es alguien por su cara", "orientación sexual",
                  "religión u opinión política", "nunca la copias", "cítalas como texto escrito en la imagen",
                  '"datos_personales": true si la imagen muestra datos de personas identificables',
                  '"asistencia", "consulta_puesto" u "otro"', "no se repiten aquí"):
        assert parte in s, parte
    no_va = s.split("LO QUE NO SE TRANSCRIBE", 1)[1].split("PRIMERO CLASIFICA", 1)[0]
    assert '"descripcion"' in no_va  # lo sensible tampoco va en la descripción
    # Una foto de una persona ya no es un documento de identidad: se describe sin decir quién es
    doc = s[s.index('- "documento_identidad"'):s.index('- "otro"')]
    assert "foto de una persona" not in doc and "documento de identidad" in doc
    m = lp.mensaje("planilla_campo")
    assert "descríbela" in m and "cualquier imagen" in m and "transcribe sus filas" in m


def test_otros_formatos_ya_no_es_un_parametro():
    for f in (lp.leer, lp.interpretar, lp.instrucciones):
        assert "otros_formatos" not in inspect.signature(f).parameters, f.__name__
    assert not hasattr(lp, "SOLO_PLANILLA") and not hasattr(lp, "OTROS_FORMATOS") and "formato" not in lp.MENSAJES
    assert {"descripcion", "datos_personales", "aviso"} <= set(lp.Lectura.__dataclass_fields__)
    lec = lp.Lectura(tipo_formato="otro", filas_visibles=0, encabezado={}, filas=[])
    assert (lec.descripcion, lec.datos_personales, lec.aviso) == ("", False, None)


# ───────────────────────────── La descripción para el modelo ─────────────────────────────

@pytest.mark.parametrize("texto,queda", [
    ("Cédula 1.234.567 escrita a mano", "Cédula …567 escrita a mano"),
    ("Llamar al 310 123 4567 mañana", "Llamar al …567 mañana"),
    ("+57 310 123 4567", "+…567"),
    ("Documento 90-000-101", "Documento …101"),
    ("Código 12345 y 1234", "Código …345 y 1234"),          # 5 o más dígitos; 4, no
    ("Mesa 12, puesto 3 de 2026", "Mesa 12, puesto 3 de 2026"),
    ("Calle 50 # 48-21", "Calle 50 # 48-21"),
    ("3101234567/3209876543", "…567/…543"),
    ("Reunión del 02/11/2026, 2026-11-30 y 30-11-2026", "Reunión del 02/11/2026, 2026-11-30 y 30-11-2026"),
    ("Escribir a ana.ruiz3101234567@correo-inventado.com hoy", "Escribir a a…@correo-inventado.com hoy"),
    ("línea 1\n\nlínea 2 con 9000101", "línea 1\n\nlínea 2 con …101"),
    ("", ""),
])
def test_enmascarar_descripcion(texto, queda):
    assert minimizar.enmascarar_descripcion(texto) == queda


def test_enmascarar_descripcion_otros_valores():
    for no in (None, 3101234567, ["310 123 4567"]):
        assert minimizar.enmascarar_descripcion(no) == ""
    assert minimizar.DESCRIPCION_DIGITOS_MIN == 5 and minimizar.DESCRIPCION_MASCARA == "…"
    tapado = minimizar.enmascarar_descripcion(AFICHE)
    assert "4567" not in tapado.replace("…567", "") and "jornadas.yondo" not in tapado
    assert "j…@correo-inventado.com" in tapado and "30/11/2026" in tapado and "…567" in tapado


# ───────────────────────────── La bandeja y la API ─────────────────────────────

def _subir_y_leer(cliente, sesion, monkeypatch, texto: str, datos: bytes | None = None, **params) -> str:
    encender(monkeypatch, cliente.app, ProveedorFalso(texto))
    r = subir(sesion, datos or jpeg(), **params)
    assert r.status_code == 201, r.text
    leer(cliente, r.json()["id"])
    return r.json()["id"]


def test_una_foto_cualquiera_queda_leida_con_su_descripcion(cliente, sesion, monkeypatch):
    db, cfg = cliente.app.state.db, cliente.app.state.cfg
    pid = _subir_y_leer(cliente, sesion, monkeypatch,
                        lectura_json([], tipo="otro", visibles=0, descripcion=AFICHE, datos_personales=False),
                        formato="otro")
    doc = db.planillas.find_one({"_id": pid})
    assert doc["estado"] == "leida" and doc["foto"] is not None and doc["error"] is None
    # Al reposo, cifrada como las filas; en claro, solo conteos y marcas
    assert b"vacunaci" not in doc["lectura"] and b"4567" not in doc["lectura"]
    assert doc["resumen"]["filas"] == 0 and doc["resumen"]["pendientes"] == 0 and doc["resumen"]["aviso"] is None
    assert doc["resumen"]["con_descripcion"] is True and "vacunaci" not in str(doc["resumen"])
    lectura = pl.lectura_de(cfg, doc)
    assert lectura["descripcion"] == AFICHE and lectura["filas"] == [] and lectura["aviso"] is None
    # Un teléfono y un correo en la descripción: trae datos de alguien, lo dijera o no el lector
    assert lectura["datos_personales"] is True
    # A y K: la descripción entera
    v = sesion.get(f"/api/planillas/{pid}").json()
    assert v["estado"] == "leida" and v["descripcion"] == AFICHE and v["filas"] == [] and v["aviso"] is None
    assert v["datos_personales"] is True and v["tipo_formato"] == "otro" and v["filas_visibles"] == 0
    assert v["puede_releer"] is True and v["con_descripcion"] is True
    # Como la recibe el modelo: enmascarada
    m = sesion.get(f"/api/planillas/{pid}?enmascarada=1").json()
    assert m["descripcion"] == minimizar.enmascarar_descripcion(AFICHE) and "4567" not in m["descripcion"].replace(
        "…567", "") and "jornadas.yondo@" not in m["descripcion"]
    assert m["datos_personales"] is True and m["filas"] == []
    # La bandeja: sin la descripción, con sus marcas
    (x,) = sesion.get("/api/planillas").json()["planillas"]
    assert x["filas"] == 0 and x["pendientes"] == 0 and x["con_descripcion"] is True and x["aviso"] is None
    assert x["datos_personales"] is True and "vacunaci" not in json.dumps(x)
    # Ni la auditoría ni la bandeja llevan el texto
    aud = db.auditoria.find_one({"accion": "leer_planilla", "planilla": pid})
    assert aud and "vacunaci" not in str(aud) and "4567" not in str(aud)


def test_cotejar_y_cargar_una_foto_sin_filas_responde_sin_filas(cliente, sesion, monkeypatch):
    db = cliente.app.state.db
    pid = _subir_y_leer(cliente, sesion, monkeypatch, lectura_json([], tipo="otro", descripcion="Un paisaje."))
    for ruta in ("simular", "cargar"):
        r = sesion.post(f"/api/planillas/{pid}/{ruta}", json={})
        assert r.status_code == 422 and r.json()["detail"]["codigo"] == "sin_filas", (ruta, r.text)
        assert r.json()["detail"]["mensaje"] == pl.FOTO_SIN_FILAS
    doc = db.planillas.find_one({"_id": pid})
    assert doc["estado"] == "leida" and doc["cargando"] is None and doc["foto"] is not None  # nada cambió
    assert db.importaciones.count_documents({}) == 0
    # Corregir: no hay filas; un PATCH vacío no rompe
    r = sesion.patch(f"/api/planillas/{pid}", json={"filas": [{"n": 1, "campo": "nombre", "valor": "X"}]})
    assert r.status_code == 422 and r.json()["detail"]["codigo"] == "fila"
    r = sesion.patch(f"/api/planillas/{pid}", json={})
    assert r.status_code == 200 and r.json()["descripcion"] == "Un paisaje." and r.json()["filas"] == []


def test_una_hoja_sin_filas_se_vuelve_a_leer(cliente, sesion, monkeypatch):
    p = ProveedorFalso(lectura_json([], tipo="planilla_campo", visibles=8, descripcion="Una planilla movida."),
                       lectura_json([fila(1, **ANA)], descripcion="Una planilla de campo con 1 fila."))
    encender(monkeypatch, cliente.app, p)
    pid = subir(sesion, jpeg()).json()["id"]
    leer(cliente, pid)
    v = sesion.get(f"/api/planillas/{pid}").json()
    assert v["estado"] == "leida" and v["aviso"] == "sin_filas" and v["filas"] == [] and v["puede_releer"] is True
    (x,) = sesion.get("/api/planillas").json()["planillas"]
    assert x["aviso"] == "sin_filas" and x["filas"] == 0
    assert sesion.post(f"/api/planillas/{pid}/leer", json={}).status_code == 202
    leer(cliente, pid)
    v = sesion.get(f"/api/planillas/{pid}").json()
    assert v["aviso"] is None and v["descripcion"] == "Una planilla de campo con 1 fila." and len(v["filas"]) == 1
    assert sesion.post(f"/api/planillas/{pid}/simular", json={}).json()["filas"][0]["estado"] == "nueva"


def test_una_lista_de_asistencia_se_lee_y_se_carga(cliente, sesion, monkeypatch):
    """Sin el ajuste retirado: una lista de asistencia (u otra hoja con personas) se lee y se carga como la planilla
    de campo, también con un `otros_formatos: false` guardado de antes."""
    db = cliente.app.state.db
    texto = lectura_json([fila(1, **ANA)], tipo="asistencia", descripcion="Lista de asistencia del 02/11/2026.",
                         datos_personales=False)
    encender(monkeypatch, cliente.app, ProveedorFalso(texto))
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"agente_planillas.otros_formatos": False}})
    pid = subir(sesion, jpeg(), formato="asistencia").json()["id"]
    leer(cliente, pid)
    v = sesion.get(f"/api/planillas/{pid}").json()
    assert v["estado"] == "leida" and v["tipo_formato"] == "asistencia" and v["formato"] == "asistencia"
    assert v["descripcion"] == "Lista de asistencia del 02/11/2026." and v["datos_personales"] is False
    assert v["filas"][0]["valores"]["cedula"] == ANA["cedula"]
    c = sesion.post(f"/api/planillas/{pid}/cargar", json={})
    assert c.status_code == 200 and c.json()["filas"]["1"]["estado"] == "nueva"
    v = sesion.get(f"/api/planillas/{pid}").json()
    # Cargada entera: la foto y lo leído (también la descripción) se borran
    assert v["estado"] == "cargada" and v["descripcion"] is None and v["con_descripcion"] is False
    assert db.planillas.find_one({"_id": pid})["lectura"] is None


def test_la_descripcion_cortada_se_guarda_y_releer_desde_una_fila_la_conserva(cliente, sesion, monkeypatch):
    db, cfg = cliente.app.state.db, cliente.app.state.cfg
    filas = [fila(n, nombre=f"PERSONA INVENTADA {n}", cedula=f"9300{n:04d}") for n in range(1, 5)]
    entero = lectura_json(filas, visibles=4, descripcion="Planilla de campo con 4 filas.")
    cortado = entero[:entero.index('"PERSONA INVENTADA 3"') + 4]
    # La relectura desde la fila 3 no trae descripción: queda la de antes
    p = ProveedorFalso((cortado, "max_tokens"), lectura_json(filas[2:], visibles=4))
    encender(monkeypatch, cliente.app, p)
    pid = subir(sesion, jpeg()).json()["id"]
    leer(cliente, pid)
    v = sesion.get(f"/api/planillas/{pid}").json()
    assert v["incompleta"] is True and v["ultima_fila"] == 2 and v["descripcion"] == "Planilla de campo con 4 filas."
    assert sesion.post(f"/api/planillas/{pid}/leer", json={"desde_fila": 3}).status_code == 202
    leer(cliente, pid, desde_fila=3)
    v = sesion.get(f"/api/planillas/{pid}").json()
    assert [f["n"] for f in v["filas"]] == [1, 2, 3, 4] and v["descripcion"] == "Planilla de campo con 4 filas."
    assert pl.lectura_de(cfg, db.planillas.find_one({"_id": pid}))["aviso"] is None


def test_las_fotos_sin_filas_no_cuentan_como_pendientes(cliente, sesion, monkeypatch):
    from datetime import datetime, timezone
    encender(monkeypatch, cliente.app, ProveedorFalso())
    db = cliente.app.state.db
    k = coordinador(cliente.app, db)
    ahora = datetime.now(timezone.utc)
    db.planillas.insert_many([{"_id": pl.nuevo_id(), "uid": k.uid, "estado": "leida", "ts": ahora,
                               "resumen": {"filas": 0, "pendientes": 0}} for _ in range(pl.SIN_CARGAR_MAX)])
    assert subir(k, jpeg()).status_code == 201
    db.planillas.insert_many([{"_id": pl.nuevo_id(), "uid": k.uid, "estado": "leida", "ts": ahora,
                               "resumen": {"filas": 3, "pendientes": 3}} for _ in range(pl.SIN_CARGAR_MAX)])
    r = subir(k, jpeg(1250, 900))
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "pendientes"
    k.close()


def test_una_supresion_tambien_oculta_la_descripcion(cliente, sesion, monkeypatch):
    db, cfg = cliente.app.state.db, cliente.app.state.cfg
    texto = lectura_json([fila(1, **ANA), fila(2, nombre="LUIS INVENTADO", cedula="90000102")],
                         descripcion="Planilla de La Cóndor que llevó ANA INVENTADA RUIZ.", datos_personales=True)
    pid = _subir_y_leer(cliente, sesion, monkeypatch, texto)
    assert "ANA INVENTADA" in sesion.get(f"/api/planillas/{pid}").json()["descripcion"]
    # Lo que deja `db.vaciar_planillas` al suprimir a quien estaba en la fila 1
    db.planillas.update_one({"_id": pid}, {"$set": {"foto": None}, "$addToSet": {"filas_suprimidas": 1}})
    v = sesion.get(f"/api/planillas/{pid}").json()
    assert v["descripcion"] is None and v["con_descripcion"] is False and "ANA INVENTADA" not in json.dumps(v)
    # La próxima escritura deja lo cifrado sin ella
    assert sesion.patch(f"/api/planillas/{pid}", json={}).status_code == 200
    doc = db.planillas.find_one({"_id": pid})
    claro = cifrado.descifrar_bytes(pl.llave(cfg), doc["lectura"], f"planilla|lectura|{pid}|0")
    assert b"ANA INVENTADA" not in claro and doc["resumen"]["con_descripcion"] is False


def test_la_foto_de_una_cedula_con_descripcion_se_borra(cliente, sesion, monkeypatch):
    pid = _subir_y_leer(cliente, sesion, monkeypatch, lectura_json(
        [], tipo="documento_identidad", visibles=0, descripcion="Un documento de identidad.", datos_personales=True))
    v = sesion.get(f"/api/planillas/{pid}").json()
    assert v["estado"] == "rechazada" and v["error"]["codigo"] == "documento_identidad" and v["con_foto"] is False
    assert v["descripcion"] is None and v["aviso"] is None and v["con_descripcion"] is False
    assert cliente.app.state.db.planillas.find_one({"_id": pid})["lectura"] is None


# ───────────────────────────── El ajuste retirado ─────────────────────────────

def test_otros_formatos_se_retiro_y_un_valor_guardado_se_ignora(cliente, sesion, monkeypatch):
    from app import modelo
    from app.api import ajustes as api_ajustes
    assert politica.PLANILLAS_POR_DEFECTO == {"roles": ["admin", "coordinador"], "retencion_horas": 24}
    assert modelo.AJUSTES_POR_DEFECTO["agente_planillas"] == politica.PLANILLAS_POR_DEFECTO
    assert set(api_ajustes.PlanillasAgente.model_fields) == {"roles", "retencion_horas"}
    assert politica.ajustes_planillas({"agente_planillas": {"retencion_horas": 5, "otros_formatos": True}}) == {
        "roles": ["admin", "coordinador"], "retencion_horas": 5}
    db = cliente.app.state.db
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"agente_planillas": {
        "roles": ["admin", "coordinador"], "retencion_horas": 24, "otros_formatos": True}}}, upsert=True)
    a = sesion.get("/api/ajustes").json()
    assert a["agente_planillas"] == {"roles": ["admin", "coordinador"], "retencion_horas": 24}
    # Un formulario de antes lo manda (también con otro tipo): se acepta y no se guarda
    for valor in (True, False, None, "si"):
        r = sesion.put("/api/ajustes", json={"agente_planillas": {"retencion_horas": 30, "otros_formatos": valor}})
        assert r.status_code == 200, (valor, r.text)
        assert r.json()["agente_planillas"] == {"roles": ["admin", "coordinador"], "retencion_horas": 30}
    assert "otros_formatos" not in db.meta.find_one({"_id": "ajustes"})["agente_planillas"]
    assert sesion.put("/api/ajustes", json={"agente_planillas": {"otra": 1}}).status_code == 422
    # El coordinador que reenvía lo que ve con el `otros_formatos` de antes no cambia nada: no es un 403
    k = coordinador(cliente.app, db)
    r = k.put("/api/ajustes", json={"agente_planillas": {"roles": ["admin", "coordinador"], "retencion_horas": 30,
                                                         "otros_formatos": True}})
    assert r.status_code == 200, r.text
    k.close()
