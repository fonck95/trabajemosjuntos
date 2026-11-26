"""La bandeja de planillas físicas por la API (app/api/planillas.py): subir una foto (validada, limpia, cifrada, con
topes y sin leer el cuerpo de quien no puede), leerla de fondo, verla (A y K completa o enmascarada como la recibe el
modelo; P y C, 403 en todo), la foto con sus cabeceras, fotos repetidas y ya cargadas, retención y auditoría. Con un
proveedor del modelo falso (sin red) e imágenes inventadas."""
import base64
import dataclasses
from datetime import datetime, timedelta, timezone

import pytest

from app import planillas as pl
from app.agente import cifrado
from ayudas_g3 import coordinador
from ayudas_planillas import (GPS_TEXTO, ProveedorFalso, abre, asgi, cabeceras_de, encender, esperar, fila, jpeg,
                              lectura_json, leer, png, subir)

ANA = dict(cedula="90000101", cedula_repetida="90000101", tipo_documento="CC", nombre="ANA INVENTADA RUIZ",
           celular="3101234501", sexo="F", fecha_nacimiento="14/03/1979", direccion="CALLE 50 # 48-21",
           barrio="TRES DE OCTUBRE", autorizacion="si", medio="escrito", canales="llamada, whatsapp", mayor_18="si",
           fecha="02/11/2026", observaciones="Vive con su hija Rosa")
NO = dict(cedula="90000131", nombre="CENOBIA INVENTADA PACHECO", celular="3101234541", direccion="CALLE 49 # 47-03",
          barrio="TRES DE OCTUBRE", autorizacion="no", observaciones="No quiere que la llamen")
MENOR = dict(cedula="1012345678", tipo_documento="TI", nombre="BRAYAN INVENTADO OSPINO", celular="3101234551",
             edad="14", mayor_18="no", autorizacion="si")


def _proveedor(*filas, **kw):
    return ProveedorFalso(lectura_json(list(filas) or [fila(1, **ANA), fila(2, **NO), fila(3, **MENOR)], **kw))


def test_subir_leer_y_guardar_cifrado(cliente, sesion, monkeypatch, cfg):
    p = _proveedor()
    encoladas = encender(monkeypatch, cliente.app, p)
    crudo = jpeg(comentario=b"COMENTARIO-SECRETO")
    r = subir(sesion, crudo, nota="Vereda La Cóndor, reunión del 2/11")
    assert r.status_code == 201, r.text
    d = r.json()
    assert set(d) == {"id", "estado", "bytes", "ancho", "alto", "expira"} and d["estado"] == "leyendo"
    assert pl.ID.fullmatch(d["id"]) and (d["ancho"], d["alto"]) == (1200, 900) and d["bytes"] < len(crudo)
    assert encoladas == [(d["id"], None)]
    leer(cliente, d["id"])
    db = cliente.app.state.db
    doc = db.planillas.find_one({"_id": d["id"]})
    assert doc["estado"] == "leida" and doc["lecturas"] == 1 and doc["proveedor"] == "anthropic"
    # Al reposo: la foto y las filas cifradas (nada legible en la base)
    assert isinstance(doc["foto"], bytes) and not doc["foto"].startswith(b"\xff\xd8")
    for secreto in (b"ANA INVENTADA", b"90000101", b"3101234501", b"CENOBIA"):
        assert secreto not in doc["foto"] and secreto not in doc["lectura"]
    foto = pl.foto_de(cliente.app.state.cfg, doc)
    assert foto.startswith(b"\xff\xd8") and b"Exif" not in foto and GPS_TEXTO not in foto and b"COMENTARIO" not in foto
    otra = dataclasses.replace(cliente.app.state.cfg, clave="otra-clave-del-panel-larga")
    assert pl.foto_de(otra, doc) is None and pl.lectura_de(otra, doc) is None
    falsa = {**doc, "_id": pl.nuevo_id()}  # lo cifrado de una planilla no abre en otra
    assert pl.foto_de(cliente.app.state.cfg, falsa) is None
    # Al modelo le llegó la foto limpia
    enviada = base64.b64decode(p.llamadas[0]["mensajes"][0]["content"][0]["source"]["data"])
    assert enviada == foto
    # Lo que ve A: valores completos; la fila «No autoriza» guarda solo nombre, cédula y barrio
    v = sesion.get(f"/api/planillas/{d['id']}").json()
    assert v["estado"] == "leida" and v["filas_visibles"] == 3 and v["columnas"] == list(pl.COLUMNAS)
    a, no, menor = v["filas"]
    assert a["valores"]["cedula"] == "90000101" and a["valores"]["observaciones"] == "Vive con su hija Rosa"
    assert a["estado"] == "pendiente"
    assert no["valores"] == {"nombre": "CENOBIA INVENTADA PACHECO", "cedula": "90000131", "barrio": "TRES DE OCTUBRE",
                             "autorizacion": "no"} and no["estado"] == "no_autoriza"
    lectura = pl.lectura_de(cliente.app.state.cfg, doc)
    assert "3101234541" not in str(lectura) and "No quiere" not in str(lectura)
    # Auditoría sin datos de personas; el uso, al día de quien subió la foto
    aud = list(db.auditoria.find({"accion": {"$in": ["subir_planilla", "leer_planilla"]}}))
    assert {x["accion"] for x in aud} == {"subir_planilla", "leer_planilla"}
    assert all(x["planilla"] == d["id"] for x in aud)
    assert not any(s in str(aud) for s in ("ANA", "90000101", "CENOBIA", "3101234501"))
    assert db.agente_uso.find_one({"uid": 0})["entrada"] == 1200


def test_retencion_y_vencimiento(cliente, sesion, monkeypatch):
    encender(monkeypatch, cliente.app, _proveedor(), horas=5)
    d = subir(sesion, jpeg()).json()
    db = cliente.app.state.db
    doc = db.planillas.find_one({"_id": d["id"]})
    assert abs((doc["expira"] - doc["ts"]) - timedelta(hours=5)) < timedelta(seconds=1)
    indices = {i["name"]: i for i in db.planillas.list_indexes()}
    assert any(i.get("expireAfterSeconds") == 0 and list(i["key"]) == ["expira"] for i in indices.values())
    assert any(i.get("expireAfterSeconds") and list(i["key"]) == ["ts"] for i in db.planillas_subidas.list_indexes())
    assert any(list(i["key"]) == ["fotos_sha256"] for i in db.importaciones.list_indexes())


def test_la_lectura_corre_de_fondo_sola(cliente, sesion, monkeypatch):
    encender(monkeypatch, cliente.app, _proveedor(), de_fondo=True)
    d = subir(sesion, jpeg()).json()
    assert d["estado"] == "leyendo"
    v = esperar(sesion, d["id"])
    assert v["estado"] == "leida" and len(v["filas"]) == 3


def test_la_foto_con_su_tipo_y_sin_que_el_navegador_la_interprete(cliente, sesion, monkeypatch):
    encender(monkeypatch, cliente.app, _proveedor())
    d = subir(sesion, png(), "image/png").json()
    r = sesion.get(f"/api/planillas/{d['id']}/foto")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.headers["x-content-type-options"] == "nosniff" and "no-store" in r.headers["cache-control"]
    assert r.headers["content-disposition"].startswith("attachment")
    assert b"TEXTO-SECRETO" not in r.content and abre(r.content).size == (1000, 800)


def test_solo_a_y_k_usan_la_bandeja_y_la_enmascarada_es_la_del_modelo(cliente, sesion, como, monkeypatch):
    encender(monkeypatch, cliente.app, _proveedor())  # con «planillero» guardado en los roles: no cuenta
    k = coordinador(cliente.app, cliente.app.state.db)
    d = subir(k, jpeg()).json()
    leer(cliente, d["id"])
    pid = d["id"]
    # K: enmascarada si la pide (como la recibe el modelo), completa si no
    v = k.get(f"/api/planillas/{pid}?enmascarada=1").json()
    a, no, menor = v["filas"]
    assert a["cedula"] == "···101" and a["cedula_coincide"] is True and a["celular"] == "···4501"
    assert "fecha_nacimiento" not in a and a["edad"] >= 40 and a["tiene_observaciones"] is True
    assert "observaciones" not in a and "Vive" not in str(v)
    assert no == {"n": 2, "nombre": "CENOBIA INVENTADA PACHECO", "lugar": "TRES DE OCTUBRE",
                  "consentimiento": "no", "aviso": no["aviso"], "estado": "no_autoriza"}
    assert "celular" not in menor and menor["menor"] is True
    assert k.get(f"/api/planillas/{pid}").json()["filas"][0]["valores"]["cedula"] == "90000101"
    assert k.get(f"/api/planillas/{pid}/foto").status_code == 200
    # P y C: 403 `permiso` en todas las rutas, también en la bandeja (ni se sabe si la planilla existe)
    for rol in ("planillero", "consultor"):
        c = como(rol)
        for r in (c.get("/api/planillas"), c.get(f"/api/planillas/{pid}"), c.get(f"/api/planillas/{pid}/foto"),
                  c.post(f"/api/planillas/{pid}/leer", json={}), c.delete(f"/api/planillas/{pid}"),
                  c.patch(f"/api/planillas/{pid}", json={}), c.post(f"/api/planillas/{pid}/simular", json={}),
                  c.post(f"/api/planillas/{pid}/cargar", json={}), subir(c, jpeg(1250, 900))):
            assert r.status_code == 403 and r.json()["detail"]["codigo"] == "permiso", (rol, r.text)
    # A la ve completa, con la de todos
    a = sesion.get(f"/api/planillas/{pid}").json()
    assert a["filas"][0]["valores"]["cedula"] == "90000101"
    assert sesion.get(f"/api/planillas/{pid}?enmascarada=1").json()["filas"][0]["cedula"] == "···101"
    assert [x["id"] for x in sesion.get("/api/planillas").json()["planillas"]] == [pid]
    assert sesion.get("/api/planillas/no-es-un-id").status_code == 404
    # K la borra
    assert k.delete(f"/api/planillas/{pid}").json() == {"borrada": True}
    assert sesion.get(f"/api/planillas/{pid}").status_code == 404
    assert cliente.app.state.db.auditoria.find_one({"accion": "borrar_planilla", "planilla": pid})
    k.close()


def test_la_bandeja_no_trae_datos_de_personas(cliente, sesion, monkeypatch):
    encender(monkeypatch, cliente.app, _proveedor())
    d = subir(sesion, jpeg(), nota="Llamar a 3101234501 por la hoja\nsegunda línea").json()
    leer(cliente, d["id"])
    (x,) = sesion.get("/api/planillas").json()["planillas"]
    assert x["id"] == d["id"] and x["estado"] == "leida" and x["filas"] == 3 and x["dudosas"] == 0
    assert x["subida_por"] == {"uid": 0, "usuario": "admin", "nombre": "admin"} and x["con_foto"] is True
    assert "3101234501" not in x["nota"] and "\n" not in x["nota"]
    texto = str(x)
    assert not any(s in texto for s in ("ANA", "90000101", "CENOBIA"))
    assert sesion.get("/api/planillas?estado=fallida").json() == {"planillas": []}


def test_la_misma_foto_es_la_misma_y_una_ya_cargada_no_se_sube(cliente, sesion, como, monkeypatch):
    p = _proveedor(fila(1, **ANA))
    encoladas = encender(monkeypatch, cliente.app, p)
    datos = jpeg()
    d = subir(sesion, datos).json()
    r = subir(sesion, datos)
    assert r.status_code == 200 and r.json()["id"] == d["id"] and r.json()["repetida"] is True
    assert len(encoladas) == 1  # no se paga otra lectura
    # Otra persona con la misma foto tiene la suya
    k = coordinador(cliente.app, cliente.app.state.db)
    assert subir(k, datos).json()["id"] != d["id"]
    k.close()
    leer(cliente, d["id"])
    c = sesion.post(f"/api/planillas/{d['id']}/cargar", json={})
    assert c.status_code == 200, c.text
    r = subir(sesion, datos)
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "ya_cargada"
    assert r.json()["detail"]["importacion_id"] == c.json()["importacion_id"]
    assert f"#{c.json()['importacion_id']}" in r.json()["detail"]["mensaje"]


def test_subir_otra_vez_una_que_fallo_la_vuelve_a_leer(cliente, sesion, monkeypatch):
    p = ProveedorFalso(lectura_json([], visibles=2), lectura_json([fila(1, **ANA)]))
    encoladas = encender(monkeypatch, cliente.app, p)
    datos = jpeg()
    d = subir(sesion, datos).json()
    leer(cliente, d["id"])
    v = sesion.get(f"/api/planillas/{d['id']}").json()
    assert v["estado"] == "fallida" and v["error"]["codigo"] == "respuesta" and v["puede_releer"] is True
    r = subir(sesion, datos)
    assert r.status_code == 200 and r.json()["estado"] == "leyendo" and len(encoladas) == 2
    leer(cliente, d["id"])
    assert sesion.get(f"/api/planillas/{d['id']}").json()["estado"] == "leida"


def test_rechazo_antes_de_leer_el_cuerpo(cliente, sesion, como, monkeypatch):
    p = _proveedor()
    encender(monkeypatch, cliente.app, p, roles=("admin", "coordinador"))
    cuerpo = jpeg()
    partes = [cuerpo[i:i + 4000] for i in range(0, len(cuerpo), 4000)]
    app = cliente.app

    def mandar(c, ruta="/api/planillas/fotos", tipo="image/jpeg", largo=None, metodo="POST"):
        h = cabeceras_de(c, **{"content-type": tipo, "content-length": str(largo or len(cuerpo))})
        return asgi(app, metodo, ruta, h, partes)

    # Consultor y planillero (sin `importar`): 403 `permiso` sin leer nada; un coordinador sin el rol en
    # agente_planillas.roles, 403 `planillas_apagado`
    estado, leidas, resp = mandar(como("consultor"))
    assert (estado, leidas) == (403, 0) and b'"permiso"' in resp
    planillero = como("planillero")
    estado, leidas, resp = mandar(planillero)
    assert (estado, leidas) == (403, 0) and b'"permiso"' in resp
    app.state.db.meta.update_one({"_id": "ajustes"}, {"$set": {"agente_planillas.roles": ["admin"]}})
    k = coordinador(app, app.state.db)
    estado, leidas, resp = mandar(k)
    assert (estado, leidas) == (403, 0) and b'"planillas_apagado"' in resp
    k.close()
    # Tipo que no es foto, tamaño de más (por la guardia o por la ruta): sin leer nada
    estado, leidas, resp = mandar(sesion, tipo="text/html")
    assert (estado, leidas) == (415, 0) and b'"tipo"' in resp
    estado, leidas, resp = mandar(sesion, largo=pl.MAX_BYTES + 10)
    assert (estado, leidas) == (413, 0) and b'"pesada"' in resp
    estado, leidas, _ = mandar(sesion, largo=pl.MAX_BYTES * 3)
    assert (estado, leidas) == (413, 0)
    # Sin modelo conectado: 503 sin leer nada
    from app.agente import proveedores
    monkeypatch.setattr(proveedores, "clave_para_nueva", lambda cfg, db: None)
    estado, leidas, resp = mandar(sesion)
    assert (estado, leidas) == (503, 0) and b'"sin_configurar"' in resp
    # Todas las rutas: P recibe 403 sin que se lea su cuerpo, aunque un ajuste guardado lo nombre
    app.state.db.meta.update_one({"_id": "ajustes"}, {"$set": {"agente_planillas.roles": ["admin", "planillero"]}})
    pid = pl.nuevo_id()
    for metodo, ruta in (("PATCH", f"/api/planillas/{pid}"), ("POST", f"/api/planillas/{pid}/simular"),
                         ("POST", f"/api/planillas/{pid}/cargar"), ("POST", f"/api/planillas/{pid}/leer"),
                         ("POST", "/api/planillas/fotos")):
        tipo = "image/jpeg" if ruta.endswith("/fotos") else "application/json"
        estado, leidas, resp = mandar(planillero, ruta=ruta, tipo=tipo, metodo=metodo)
        assert (estado, leidas) == (403, 0) and b'"permiso"' in resp, (ruta, estado, leidas)


def test_cuerpo_de_mas_sin_largo_se_corta(cliente, sesion, monkeypatch):
    encender(monkeypatch, cliente.app, _proveedor())
    grande = b"\xff\xd8" + b"\x00" * (pl.MAX_BYTES + 100)
    partes = [grande[i:i + 65536] for i in range(0, len(grande), 65536)]
    h = cabeceras_de(sesion, **{"content-type": "image/jpeg", "transfer-encoding": "chunked"})
    estado, leidas, resp = asgi(cliente.app, "POST", "/api/planillas/fotos", h, partes)
    assert estado == 413 and b'"pesada"' in resp and leidas < len(partes) + 1


@pytest.mark.parametrize("datos,tipo,codigo,estado", [
    (b"", "image/jpeg", "vacia", 422),
    (b"GIF89a" + b"\x00" * 100, "image/jpeg", "tipo", 415),
    (jpeg(150, 150, exif=False), "image/jpeg", "dimensiones", 422),
    (jpeg(exif=False)[:5000], "image/jpeg", "imagen", 422),
    (jpeg(exif=False), "image/png", "tipo", 415),
    (jpeg(exif=False), "image/webp", "tipo", 415),
])
def test_fotos_que_no_se_aceptan(cliente, sesion, monkeypatch, datos, tipo, codigo, estado):
    encender(monkeypatch, cliente.app, _proveedor())
    r = subir(sesion, datos, tipo)
    assert r.status_code == estado and r.json()["detail"]["codigo"] == codigo, r.text
    assert cliente.app.state.db.planillas.count_documents({}) == 0


def test_cualquier_formato_de_la_lista_se_sube_siempre(cliente, sesion, monkeypatch):
    """El ajuste `otros_formatos` se retiró: los tres formatos se aceptan siempre, también con un `otros_formatos:
    false` guardado de antes; uno que no es de la lista, 422 `formato`."""
    encender(monkeypatch, cliente.app, _proveedor())
    cliente.app.state.db.meta.update_one({"_id": "ajustes"}, {"$set": {"agente_planillas.otros_formatos": False}})
    for i, formato in enumerate(("asistencia", "otro", "planilla_campo")):
        r = subir(sesion, jpeg(1200 + i, 900), formato=formato)
        assert r.status_code == 201, (formato, r.text)
    r = subir(sesion, jpeg(1300, 900), formato="cualquiera")
    assert r.status_code == 422 and r.json()["detail"]["codigo"] == "formato"


def test_topes_por_persona(cliente, como, monkeypatch):
    encender(monkeypatch, cliente.app, _proveedor())
    db = cliente.app.state.db
    p = coordinador(cliente.app, db)
    ahora = datetime.now(timezone.utc)
    db.planillas_subidas.insert_many([{"uid": p.uid, "ts": ahora - timedelta(minutes=5)} for _ in range(pl.POR_HORA)])
    r = subir(p, jpeg())
    assert r.status_code == 429 and r.json()["detail"]["codigo"] == "frecuencia" and r.headers["retry-after"]
    db.planillas_subidas.delete_many({})
    db.planillas_subidas.insert_many([{"uid": p.uid, "ts": ahora - timedelta(hours=3)} for _ in range(pl.POR_DIA)])
    assert subir(p, jpeg()).status_code == 429
    db.planillas_subidas.delete_many({})
    db.planillas.insert_many([{"_id": pl.nuevo_id(), "uid": p.uid, "estado": "leida", "ts": ahora}
                              for _ in range(pl.SIN_CARGAR_MAX)])
    r = subir(p, jpeg())
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "pendientes"
    # Borrar fotos no reinicia los topes de subidas
    db.planillas.delete_many({})
    for i in range(3):
        assert subir(p, jpeg(1200 + i, 900)).status_code == 201
    assert db.planillas_subidas.count_documents({"uid": p.uid}) == 3


def test_la_foto_de_una_cedula_no_se_lee_y_se_borra(cliente, sesion, monkeypatch):
    encender(monkeypatch, cliente.app, ProveedorFalso(lectura_json([], tipo="documento_identidad", visibles=0)))
    d = subir(sesion, jpeg()).json()
    leer(cliente, d["id"])
    v = sesion.get(f"/api/planillas/{d['id']}").json()
    assert v["estado"] == "rechazada" and v["error"]["codigo"] == "documento_identidad"
    assert "cédulas" in v["error"]["mensaje"] and v["con_foto"] is False and v["puede_releer"] is False
    assert cliente.app.state.db.planillas.find_one({"_id": d["id"]})["foto"] is None
    r = sesion.get(f"/api/planillas/{d['id']}/foto")
    assert r.status_code == 404 and r.json()["detail"]["codigo"] == "sin_foto"
    assert sesion.post(f"/api/planillas/{d['id']}/leer", json={}).json()["detail"]["codigo"] == "sin_foto"


def test_una_lectura_sin_latido_se_da_por_fallida(cliente, sesion, monkeypatch):
    encender(monkeypatch, cliente.app, _proveedor())
    d = subir(sesion, jpeg()).json()
    db = cliente.app.state.db
    db.planillas.update_one({"_id": d["id"]}, {"$set": {"latido": datetime.now(timezone.utc) - timedelta(minutes=6)}})
    v = sesion.get(f"/api/planillas/{d['id']}").json()
    assert v["estado"] == "fallida" and v["error"]["codigo"] == "interrumpida" and v["puede_releer"] is True
    # La lectura que llegue tarde no la pisa
    leer(cliente, d["id"])
    assert db.planillas.find_one({"_id": d["id"]})["estado"] == "fallida"


def test_errores_del_modelo_quedan_en_la_planilla(cliente, sesion, monkeypatch):
    encender(monkeypatch, cliente.app, ProveedorFalso(RuntimeError("caído"), lectura_json([], imagen_visible=False)))
    a = subir(sesion, jpeg()).json()
    leer(cliente, a["id"])
    v = sesion.get(f"/api/planillas/{a['id']}").json()
    assert v["estado"] == "fallida" and v["error"]["codigo"] == "llm_falso"
    b = subir(sesion, jpeg(1300, 900)).json()
    leer(cliente, b["id"])
    v = sesion.get(f"/api/planillas/{b['id']}").json()
    assert v["error"]["codigo"] == "sin_imagen" and "no pudo ver la foto" in v["error"]["mensaje"]
    from app.agente import proveedores
    monkeypatch.setattr(proveedores, "para_nueva", lambda app, cfg, db: None)
    c = subir(sesion, jpeg(1400, 900)).json()
    leer(cliente, c["id"])
    assert sesion.get(f"/api/planillas/{c['id']}").json()["error"]["codigo"] == "sin_configurar"


def test_cupo_por_proceso():
    import asyncio
    orden: list = []

    async def una(n):
        async with pl._cupo(None, "x", "mnemo"):
            orden.append(("entra", n))
            await asyncio.sleep(0.05)
            orden.append(("sale", n))

    async def todas():
        await asyncio.gather(una(1), una(2))

    asyncio.run(todas())
    assert orden[1][0] == "sale"  # con Mnemo, de a una
    assert pl.A_LA_VEZ == {"mnemo": 1, "anthropic": 2} and pl._ocupados.get("mnemo") == 0


def test_para_el_chat(cliente, sesion, como, monkeypatch):
    encender(monkeypatch, cliente.app, _proveedor())
    d = subir(sesion, jpeg()).json()
    p = coordinador(cliente.app, cliente.app.state.db)
    otra = subir(p, jpeg(1250, 900)).json()
    p.close()
    db = cliente.app.state.db
    fotos = pl.fotos_de(db, 0, [otra["id"], d["id"], "no-es-id", d["id"]])
    assert [f["id"] for f in fotos] == [d["id"]] and fotos[0]["estado"] == "leyendo" and fotos[0]["con_foto"]
    assert pl.estado_adjuntos(None) is None
    assert pl.estado_adjuntos("mnemo") == {"max_por_mensaje": 4, "lado_max": 2000, "calidad": 0.8,
                                           "max_bytes": 1_500_000}
    assert pl.estado_adjuntos("anthropic")["lado_max"] == 2576
    assert cifrado.MAX_BYTES >= pl.MAX_BYTES
