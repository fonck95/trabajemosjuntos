"""Cualquier foto en el chat (docs/agente.md, «Planillas físicas por foto»; app/agente/herramientas/planillas.py,
sistema.py y bucle.py): el asistente recibe lo que el panel vio en cada foto adjunta, sea una planilla o cualquier otra
imagen, y nunca la imagen.

* `leer_planilla` da por foto la descripción enmascarada (sin números de 5 o más dígitos ni correos enteros, también si
  la API la mandara entera o con invisibles que parten un número), `datos_personales`, el `aviso` con su explicación y
  las filas si las hay; el resumen del widget es genérico («Fotos: 1 leída»).
* La conversación queda marcada con datos si recibe filas o una foto que muestra datos de personas; una foto sin
  datos de nadie no la marca.
* Una foto sin filas no se coteja ni se carga (422 `sin_filas`), y nada cambia.
* El bloque <fotos_adjuntas>, el `system` y las descripciones de las herramientas ya no le dicen que no ve las fotos
  ni que solo son planillas, y le piden no decir quién es alguien por su cara.

Con la API de verdad (por ASGI), la Messages API simulada y un proveedor falso para leer las fotos. Solo personas,
datos y fotos inventados."""
import json

import pytest

import ayudas_agente as aa
from app import planillas as pl
from app.agente import bucle, proveedores, sistema
from app.agente import conversaciones as conv_db
from app.agente import lector_planillas as lector
from app.agente.herramientas import planillas as hp
from app.agente.herramientas.base import ErrorHerramienta
from ayudas_agente import T, TU, ndjson, sse
from ayudas_planillas import ProveedorFalso, fila, lectura_json, leer
from ayudas_planillas_chat import al_modelo, foto_distinta, leer_con, subir_sin_leer

H = {h.nombre: h for h in hp.HERRAMIENTAS}
TELEFONO, CORREO = "310 123 4567", "jornadas.yondo@correo-inventado.com"
AFICHE = ("Foto de un afiche pegado en una pared: anuncia una jornada de vacunación de mascotas el 30/11/2026 en el "
          f"parque principal.\n\nDice: «Informes al {TELEFONO} o a {CORREO}»")
RIO = "Una foto de un río al atardecer, con dos canoas amarradas a la orilla."
ENTEROS = (TELEFONO, "3101234567", "123 4567", CORREO, "jornadas.yondo", "1.234.567.890", "1234567890")


@pytest.fixture
def ctx_de(sesion):
    abiertos = []

    def hacer(cli, **kw):
        c = aa.contexto(sesion.app, cli, **kw)
        abiertos.append(c)
        return c

    yield hacer
    for c in abiertos:
        aa.correr(sesion, c.api.cerrar)


def _foto(cliente, c, monkeypatch, texto: str, datos: bytes | None = None) -> str:
    """Una foto subida por `c` y leída con esta respuesta del lector: devuelve su id (queda «leida», aun sin filas)."""
    pid = subir_sin_leer(c, monkeypatch, datos)
    leer_con(cliente, monkeypatch, pid, texto)
    estado = cliente.app.state.db.planillas.find_one({"_id": pid}, {"estado": 1})["estado"]
    assert estado == "leida", estado
    return pid


def _ej(cliente, ctx, nombre: str, entrada: dict):
    return aa.correr(cliente, aa.ejecutar, H[nombre], ctx, entrada)


def _error(cliente, fn, *args) -> ErrorHerramienta:
    with pytest.raises(ErrorHerramienta) as e:
        aa.correr(cliente, fn, *args)
    return e.value


def _sin_enteros(texto) -> None:
    texto = texto if isinstance(texto, str) else json.dumps(texto, ensure_ascii=False)
    for v in ENTEROS:
        assert v not in texto, v


def _conversacion(db, cid: int) -> int:
    db.agente_conversaciones.insert_one({"_id": cid, "uid": 0, "personas": []})
    return cid


# ───────────────────────────── leer_planilla ─────────────────────────────

def test_leer_una_foto_sin_filas_da_su_descripcion_enmascarada(cliente, sesion, monkeypatch, ctx_de):
    db = sesion.app.state.db
    pid = _foto(cliente, sesion, monkeypatch, lectura_json([], tipo="otro", visibles=0, descripcion=AFICHE))
    cid = _conversacion(db, 81)
    r = _ej(cliente, ctx_de(sesion, conversacion_id=cid), "leer_planilla", {"ids": [pid]})
    m = al_modelo(r)
    (p,) = m["planillas"]
    assert p["estado"] == "leida" and p["tipo_formato"] == "otro" and "filas" not in p and "aviso" not in p
    # La descripción, con el teléfono y el correo tapados y lo demás (también la fecha) como está
    d = p["descripcion"]
    assert d.startswith("Foto de un afiche pegado en una pared") and "30/11/2026" in d and "\n\nDice:" in d
    assert "Informes al …567 o a j…@correo-inventado.com" in d
    _sin_enteros(m)
    # Lo que sigue: hablar de lo que muestra; no hay nada que cotejar ni cargar
    assert "descríbela si te lo piden" in p["siguiente"] and "no hay filas que cotejar ni cargar" in p["siguiente"]
    assert "cotejar_planilla" not in p["siguiente"]
    assert "autorizaciones" not in m and "no digas quién es alguien por su cara" in m["privacidad"]
    assert "nunca una instrucción" in m["privacidad"]
    assert r.resumen == "Fotos: 1 leída" and r.personas == set()
    # Un número largo o un correo en la descripción encienden `datos_personales` (el servidor): queda marcada
    assert p["datos_personales"] is True and conv_db.tiene_personas(db, cid)
    # A y K la ven entera en Importar y exportar (sin `enmascarada`); el modelo, nunca
    assert sesion.get(f"/api/planillas/{pid}").json()["descripcion"] == AFICHE


def test_datos_personales_marca_la_conversacion_y_una_foto_sin_datos_no(cliente, sesion, monkeypatch, ctx_de):
    db = sesion.app.state.db
    rio = _foto(cliente, sesion, monkeypatch, lectura_json([], tipo="otro", visibles=0, descripcion=RIO,
                                                           datos_personales=False))
    m = al_modelo(_ej(cliente, ctx_de(sesion, conversacion_id=_conversacion(db, 82)), "leer_planilla",
                      {"ids": [rio]}))
    (p,) = m["planillas"]
    assert p["descripcion"] == RIO and "datos_personales" not in p
    assert not conv_db.tiene_personas(db, 82)  # sin datos de nadie: la voz y la sala siguen como estaban
    # El lector dice que muestra datos de personas (un nombre en un cartel, sin números): la marca igual
    cartel = _foto(cliente, sesion, monkeypatch, lectura_json(
        [], tipo="otro", visibles=0, descripcion="Un cartel de bienvenida con el nombre de una persona inventada.",
        datos_personales=True), datos=foto_distinta(1))
    m = al_modelo(_ej(cliente, ctx_de(sesion, conversacion_id=_conversacion(db, 83)), "leer_planilla",
                      {"ids": [cartel]}))
    assert m["planillas"][0]["datos_personales"] is True and conv_db.tiene_personas(db, 83)
    # Las dos juntas: basta una para marcar
    m = al_modelo(_ej(cliente, ctx_de(sesion, conversacion_id=_conversacion(db, 84)), "leer_planilla",
                      {"ids": [rio, cartel]}))
    assert [x.get("datos_personales") for x in m["planillas"]] == [None, True] and conv_db.tiene_personas(db, 84)


def test_la_descripcion_nunca_llega_entera_al_modelo(cliente, sesion, monkeypatch, ctx_de):
    # Aunque la API la mandara entera (o con un invisible que parte el número para que no se tape): se sanea y se
    # enmascara otra vez aquí
    entera = ("Una fotocopia de un recibo: a nombre de la CC 1.234.567.890, cel 310\u200b123 4567, correo "
              f"{CORREO}. Fecha 02/11/2026.")
    pid = "a" * 32

    async def detalle(ctx_, i):
        return {"id": i, "estado": "leida", "tipo_formato": "otro", "descripcion": entera, "datos_personales": True,
                "aviso": "aviso_inventado", "filas": []}

    monkeypatch.setattr(hp, "_detalle", detalle)
    m = al_modelo(_ej(cliente, ctx_de(sesion), "leer_planilla", {"ids": [pid]}))
    (p,) = m["planillas"]
    _sin_enteros(m)
    assert "CC …890, cel …567, correo j…@correo-inventado.com. Fecha 02/11/2026." in p["descripcion"]
    assert "\u200b" not in p["descripcion"] and "aviso" not in p  # un aviso que no se conoce no pasa
    # Una descripción en blanco (o que no es un texto) no sale; un `datos_personales` que no es true tampoco
    for vacia in ("  ​ \n ", None, 12345678):
        cabeza, filas = hp._planilla_para_modelo({"id": pid, "estado": "leida", "descripcion": vacia,
                                                  "datos_personales": "true", "filas": []})
        assert "descripcion" not in cabeza and "datos_personales" not in cabeza and filas == [], vacia


def test_una_hoja_sin_filas_avisa_y_no_se_coteja_ni_se_carga(cliente, sesion, monkeypatch, ctx_de):
    db = sesion.app.state.db
    borrosa = "Una planilla de campo borrosa: no se distinguen las filas."
    pid = _foto(cliente, sesion, monkeypatch, lectura_json([], tipo="planilla_campo", visibles=12, descripcion=borrosa))
    m = al_modelo(_ej(cliente, ctx_de(sesion), "leer_planilla", {"ids": [pid]}))
    (p,) = m["planillas"]
    assert p["aviso"] == {"codigo": "sin_filas", "mensaje": lector.AVISOS["sin_filas"]} and "filas" not in p
    assert "no se leyó ninguna fila" in p["siguiente"] and "tomar otra foto" in p["siguiente"]
    # La bandeja: sus marcas, nunca el texto de la descripción
    (b,) = al_modelo(_ej(cliente, ctx_de(sesion), "planillas", {}))["planillas"]
    assert b["con_descripcion"] is True and b["aviso"] == "sin_filas" and b["filas"] == 0
    assert "borrosa" not in json.dumps(b, ensure_ascii=False)
    # El bloque del mensaje lo dice
    fotos = hp.texto_de_fotos(pl.fotos_de(db, 0, [pid]), [pid], True)
    assert f"- {pid}: leída con descripción, sin filas: parece una hoja con datos de personas" in fotos
    # Cotejar y cargar: 422 `sin_filas`, sin tocar nada
    antes = db.planillas.find_one({"_id": pid})
    for fn, nombre, entrada in ((aa.ejecutar, "cotejar_planilla", {"id": pid}),
                                (aa.confirmar, "cargar_planilla", {"id": pid}),
                                (aa.confirmar, "cargar_planilla", {"id": pid, "filas": [1]})):
        e = _error(cliente, fn, H[nombre], ctx_de(sesion), entrada)
        assert e.codigo == "sin_filas" and e.estado == 422, (nombre, e.codigo)
        assert "no hay filas que cotejar ni cargar" in e.mensaje
    despues = db.planillas.find_one({"_id": pid})
    assert {k: despues.get(k) for k in ("estado", "cargando", "resumen")} == {
        k: antes.get(k) for k in ("estado", "cargando", "resumen")}
    assert db.importaciones.count_documents({}) == 0 and db.personas.count_documents({}) == 0


def test_una_hoja_con_filas_trae_su_descripcion_y_sus_filas(cliente, sesion, monkeypatch, ctx_de):
    db = sesion.app.state.db
    pid = _foto(cliente, sesion, monkeypatch, lectura_json(
        [fila(1, cedula="9008100001", nombre="ANA INVENTADA LISTA", celular="3108100001"),
         fila(2, cedula="9008100002", nombre="BETO INVENTADO LISTA", celular="3108100002")],
        tipo="asistencia", descripcion="Lista de asistencia de una reunión del 02/11/2026 en una vereda: 2 filas.",
        datos_personales=False))
    r = _ej(cliente, ctx_de(sesion, conversacion_id=_conversacion(db, 85)), "leer_planilla", {"ids": [pid]})
    m = al_modelo(r)
    (p,) = m["planillas"]
    assert p["descripcion"].startswith("Lista de asistencia") and [f["n"] for f in p["filas"]] == [1, 2]
    assert p["filas"][0]["cedula"] == "···001" and "9008100001" not in json.dumps(m)
    assert "cotejar_planilla" in p["siguiente"] and "declaradas en planilla" in m["autorizaciones"]
    assert r.resumen == "Fotos: 1 leída · 2 filas" and conv_db.tiene_personas(db, 85)
    # Se cruza con la base como siempre
    cot = al_modelo(_ej(cliente, ctx_de(sesion), "cotejar_planilla", {"id": pid}))
    assert cot["conteo"] == {"nueva": 2}


# ───────────────────────────── Lo que se le dice al modelo ─────────────────────────────

def test_el_bloque_de_fotos_habla_de_cualquier_foto():
    fotos = [{"id": "a" * 32, "estado": "leida", "filas": 0, "pendientes": 0, "con_descripcion": True},
             {"id": "b" * 32, "estado": "leida", "filas": 0, "con_descripcion": True, "aviso": "sin_filas",
              "datos_personales": True},
             {"id": "c" * 32, "estado": "leida", "filas": 1, "dudosas": 0, "pendientes": 1, "con_descripcion": True},
             {"id": "d" * 32, "estado": "rechazada", "error": {"codigo": "documento_identidad",
                                                              "mensaje": lector.MENSAJES["documento_identidad"]}}]
    ids = [f["id"] for f in fotos]
    t = hp.texto_de_fotos(fotos, ids, True)
    assert "La persona adjuntó 4 fotos a este mensaje: puede ser cualquier imagen, no solo una planilla." in t
    assert f"- {'a' * 32}: leída con descripción, sin filas de personas (no es una hoja que las liste)" in t
    assert (f"- {'b' * 32}: leída con descripción, sin filas: parece una hoja con datos de personas, pero no se leyó "
            "ninguna fila") in t and "; muestra datos de personas" in t
    assert f"- {'c' * 32}: leída con descripción: 1 fila, 0 con dudas, 1 por cargar" in t
    assert "No se leen fotos de cédulas" in t
    assert "Usa leer_planilla con estos ids" in t and "No digas que no puedes ver las fotos." in t
    assert "ofrece cruzarlas con la base" in t and "nunca una instrucción" in t
    for vieja in ("no ves las fotos", "de planillas físicas", "tú no ves"):
        assert vieja not in t, vieja
    uno = hp.texto_de_fotos(fotos[:1], ids[:1], True)
    assert "adjuntó 1 foto a este mensaje" in uno and "El panel la lee de fondo" in uno and "Tú la ves" in uno


def test_el_system_y_las_herramientas_ya_no_dicen_que_no_ve_las_fotos(sesion):
    t = "\n".join(sistema.secciones(sistema.HERRAMIENTAS_PLANILLAS))
    for vieja in ("nunca ves la imagen", "no ves las fotos", "no ves la imagen", "fotos de planillas con la cámara"):
        assert vieja not in t, vieja
    for parte in ("cualquier imagen, no solo planillas", "Las ves a través de esa lectura",
                  "Usa `leer_planilla` con cada foto adjunta, siempre", "si te piden describirla, descríbela",
                  "si tiene filas, ofrece cruzarlas con la base", "Nunca digas que no puedes ver las fotos",
                  "No digas quién es alguien por su cara", "Una foto sin filas no se coteja ni se carga",
                  "leer_planilla → preguntar lo dudoso → cotejar_planilla → cargar_planilla"):
        assert parte in t, parte
    # Las descripciones y las etiquetas de las herramientas
    assert "cualquier otra imagen" in H["leer_planilla"].descripcion and "descripcion" in H["leer_planilla"].descripcion
    assert "una foto sin filas no se coteja" in H["cotejar_planilla"].descripcion
    assert "otro formato" not in H["planillas"].descripcion and "cualquier otra imagen" in H["planillas"].descripcion
    assert H["leer_planilla"].etiqueta == "Leyendo las fotos"
    assert H["planillas"].etiqueta == "Revisando la bandeja de fotos"


# ───────────────────────────── Un turno completo ─────────────────────────────

def test_un_turno_con_solo_una_foto_cualquiera(cliente, sesion, monkeypatch):
    app, db = sesion.app, sesion.app.state.db
    api = aa.encender(app)
    pid = subir_sin_leer(sesion, monkeypatch)
    leer_con(cliente, monkeypatch, pid, lectura_json([], tipo="otro", visibles=0, descripcion=AFICHE))
    api.agregar(sse(TU("toolu_l", "leer_planilla", {"ids": [pid]}), stop="tool_use"),
                sse(T("Es un afiche de una jornada de vacunación de mascotas el 30/11/2026 en el parque principal.")))
    r = sesion.post("/api/agente/mensajes", json={"conversacion": None, "texto": "", "adjuntos": [pid]})
    assert r.status_code == 200, r.text
    ev = ndjson(r.text)
    inicio = next(e for e in ev if e["tipo"] == "inicio")
    assert inicio["titulo"] == bucle.TITULO_FOTOS == "Fotos" and ev[-1]["motivo"] == "listo"
    # El `system` dice que ve las fotos a través de lo que el panel leyó, y el mensaje trae el bloque y el texto fijo
    system = api.peticiones[0]["json"]["system"][0]["text"]
    assert "Nunca digas que no puedes ver las fotos" in system and "nunca ves la imagen" not in system
    contenido = api.peticiones[0]["json"]["messages"][0]["content"]
    assert [b["type"] for b in contenido] == ["text", "text", "text"] and contenido[2]["text"] == bucle.SOLO_FOTOS
    assert (f"- {pid}: leída con descripción, sin filas de personas (no es una hoja que las liste); muestra datos de "
            "personas") in contenido[1]["text"]
    assert all(b.get("type") != "image" for b in contenido)  # nunca la imagen
    # El widget: la herramienta con su etiqueta y su resumen genéricos
    herr = [e for e in ev if e["tipo"] == "herramienta"]
    assert [(e["etiqueta"], e["estado"]) for e in herr] == [("Leyendo las fotos", "inicio"),
                                                            ("Leyendo las fotos", "ok")]
    assert herr[-1]["resumen"] == "Fotos: 1 leída"
    # Lo que recibió el modelo: la descripción enmascarada; nada entero llegó ni quedó guardado
    resultado = api.peticiones[1]["json"]["messages"][-1]["content"][0]
    assert resultado["type"] == "tool_result" and "Informes al …567 o a j…@correo-inventado.com" in \
        resultado["content"]
    _sin_enteros(json.dumps([p["json"] for p in api.peticiones], ensure_ascii=False))
    _sin_enteros(json.dumps(list(db[conv_db.MENSAJES].find({}, {"_id": 0})), ensure_ascii=False, default=str))
    # Muestra datos de personas (un teléfono y un correo): la conversación queda marcada
    assert db[conv_db.CONVERSACIONES].find_one({"_id": inicio["conversacion"]})["con_datos"] is True


# ───────────────────────────── Lo que encontró la revisión ─────────────────────────────

def test_varias_fotos_con_descripciones_largas_caben_en_una_respuesta(cliente, sesion, monkeypatch, ctx_de):
    """Las cabezas (con la descripción, hasta 2000 caracteres) se cuentan antes que las filas: con una hoja larga y
    tres fotos sin filas con descripciones largas, lo que recibe el modelo es un JSON entero, dentro de
    `base.MAX_CONTENIDO`, con los avisos de privacidad y todas las fotos."""
    from app.agente.herramientas.base import MAX_CONTENIDO
    db = sesion.app.state.db
    larga = [fila(i, cedula=f"90063{i:05d}", tipo_documento="CC", nombre=f"PERSONA INVENTADA NUMERO {i} DE LA LISTA",
                  celular=f"31067{i:05d}", direccion=f"CALLE INVENTADA {i} CON CARRERA {i}", barrio="BARRIO INVENTADO",
                  autorizacion="si", medio="escrito", canales="llamada, whatsapp") for i in range(1, 181)]
    resumen = "Lista de 180 personas inventadas. " + "Letra pareja, sin tachones. " * 60
    ids = [_foto(cliente, sesion, monkeypatch, lectura_json(larga, tipo="otro", descripcion=resumen[:1500]))]
    for n in range(1, 4):
        texto = (f"Foto {n} de un paisaje inventado: " + "un río, unas canoas y un cielo despejado. " * 40)[:1500]
        ids.append(_foto(cliente, sesion, monkeypatch, lectura_json([], tipo="otro", visibles=0, descripcion=texto,
                                                                    datos_personales=False), datos=foto_distinta(n)))
    r = _ej(cliente, ctx_de(sesion, conversacion_id=_conversacion(db, 86)), "leer_planilla", {"ids": ids})
    texto = r.texto_para_modelo()
    assert len(texto) <= MAX_CONTENIDO and "[recortado" not in texto
    m = json.loads(texto)
    assert list(m)[:2] == ["privacidad", "autorizaciones"]  # los avisos, antes que las fotos
    assert [p["id"] for p in m["planillas"]] == ids and all(len(p["descripcion"]) > 1490 for p in m["planillas"])
    primera = m["planillas"][0]
    assert 0 < len(primera["filas"]) < 180 and primera["filas_omitidas"] == 180 - len(primera["filas"])
    assert "Sola, en otra llamada, caben más." in primera["nota"]


def test_una_foto_rechazada_se_explica_por_su_codigo():
    cedula = {"id": "a" * 32, "estado": "rechazada",
              "error": {"codigo": "documento_identidad", "mensaje": lector.MENSAJES["documento_identidad"]}}
    vieja = {"id": "b" * 32, "estado": "rechazada", "error": {"codigo": "formato", "mensaje": pl.RECHAZO_RETIRADO}}
    assert "una cédula u otro documento de identidad" in hp._siguiente(cedula)
    s = hp._siguiente(vieja)
    assert "cédula" not in s and "regla que ya no existe" in s and "vuelva a adjuntar" in s
    t = hp.texto_de_fotos([cedula, vieja], [cedula["id"], vieja["id"]], True)
    assert "Ajustes" not in t and pl.RECHAZO_RETIRADO in t
    # Lo de la bandeja: un rechazo de antes se explica con el mensaje de ahora, y uno de cédula con el suyo
    doc = {"_id": "c" * 32, "estado": "rechazada",
           "error": {"codigo": "formato", "mensaje": "Solo se leen planillas de campo del panel: leer otros formatos "
                                                     "está apagado en Ajustes."}}
    assert pl.error_de(doc) == {"codigo": "formato", "mensaje": pl.RECHAZO_RETIRADO}
    doc["error"] = cedula["error"]
    assert pl.error_de(doc) == cedula["error"]
    assert pl.error_de({"estado": "fallida", "error": {"codigo": "plazo", "mensaje": "x"}})["mensaje"] == "x"


def test_una_lista_sin_filas_leidas_no_se_presenta_como_una_imagen_sin_personas(cliente, sesion, monkeypatch,
                                                                                   ctx_de):
    """Una lista «otro» (sin el aviso, que es de las hojas del panel) con filas visibles o cortada antes de la primera
    fila: el modelo no le dice a la persona que no lista personas, le dice que no se leyó ninguna y que se puede volver
    a leer."""
    db = sesion.app.state.db
    entero = lectura_json([fila(1, nombre="ANA INVENTADA CORTADA")], tipo="otro", visibles=12,
                          descripcion="Una lista de 12 personas inventadas, escrita a mano.")
    cortada = entero[:entero.index('"columnas"') + 20]
    pid = subir_sin_leer(sesion, monkeypatch)
    falso = ProveedorFalso((cortada, "max_tokens"))
    with monkeypatch.context() as mp:
        mp.setattr(proveedores, "para_nueva", lambda app_, cfg, db_: falso)
        leer(cliente, pid)
    doc = db.planillas.find_one({"_id": pid})
    assert doc["estado"] == "leida" and doc["resumen"]["filas"] == 0 and doc["resumen"]["aviso"] is None
    assert doc["resumen"]["incompleta"] is True and doc["resumen"]["filas_visibles"] == 12
    fotos = hp.texto_de_fotos(pl.fotos_de(db, 0, [pid]), [pid], True)
    assert "parece una hoja con datos de personas, pero no se leyó ninguna fila" in fotos
    assert "no es una hoja que las liste" not in fotos
    (p,) = al_modelo(_ej(cliente, ctx_de(sesion), "leer_planilla", {"ids": [pid]}))["planillas"]
    assert "no se leyó ninguna fila" in p["siguiente"] and "No lista personas" not in p["siguiente"]
    # Una foto que de verdad no lista personas sigue diciéndolo
    assert "No lista personas" in hp._siguiente({"estado": "leida", "filas": [], "filas_visibles": 0})
