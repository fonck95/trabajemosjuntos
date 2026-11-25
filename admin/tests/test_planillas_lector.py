"""El lector de planillas físicas (app/agente/lector_planillas.py): la llamada aparte al modelo (sin herramientas, con
la imagen y un texto, con `vision`, `al_evento` que nunca rompe, topes de tokens por proveedor, plazo y errores
explicados; `sin_imagen` con el modelo que respondió), la salida compacta, el saneo de cada valor y las reglas de
rechazo y de rescate. Con un proveedor falso (y, en modo directo, con `ProveedorAnthropic` y Anthropic simulado): sin
red. Solo datos inventados."""
import asyncio
import base64
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.agente import lector_planillas as lp
from app.agente import llm
from app.agente.proveedores import ErrorProveedor, Uso
from ayudas_agente import T, cliente_falso, sse
from ayudas_planillas import COLUMNAS, ProveedorFalso, fila, jpeg, lectura_json

ANA = dict(cedula="90000101", cedula_repetida="90000101", nombre="ANA INVENTADA RUIZ", celular="3101234501",
           autorizacion="si", medio="escrito", canales="llamada, whatsapp", barrio="TRES DE OCTUBRE")


def _codigo(texto, **kw):
    with pytest.raises(lp.ErrorLectura) as e:
        lp.interpretar(texto, **kw)
    return e.value.codigo, e.value.borrar_foto


def test_lectura_compacta_se_lee_por_columnas():
    lec = lp.interpretar(lectura_json([fila(1, **ANA), fila(2, nombre="LUIS INVENTADO", edad=47, mesa=12)],
                                      encabezado={"planillero": "ana.campo", "fecha": "02/11/2026", "lugar": "X"}))
    assert lec.tipo_formato == "planilla_campo" and lec.filas_visibles == 2 and not lec.incompleta
    a, b = lec.filas
    assert a["n"] == 1 and a["valores"]["cedula"] == "90000101" and a["valores"]["canales"] == "llamada, whatsapp"
    assert b["valores"] == {"nombre": "LUIS INVENTADO", "edad": "47", "mesa": "12"}  # números como texto
    assert lec.encabezado == {"planillero": "ana.campo", "fecha": "02/11/2026", "lugar": "X"}


def test_columnas_desconocidas_o_sensibles_no_se_guardan():
    columnas = ["nombre", "etnia", "victima", "Cédula", "Barrio o vereda", "régimen de salud"]
    texto = lectura_json([{"n": 1, "v": ["ROSA INVENTADA", "INDIGENA", "SI", "90000202", "LA CONDOR", "SUBSIDIADO"]}],
                         columnas=columnas)
    lec = lp.interpretar(texto)
    assert lec.filas[0]["valores"] == {"nombre": "ROSA INVENTADA", "cedula": "90000202", "barrio": "LA CONDOR"}
    assert "INDIGENA" not in json.dumps(lec.filas) and "SUBSIDIADO" not in json.dumps(lec.filas)


def test_saneo_una_linea_nfc_sin_invisibles_y_con_largos():
    largo = "CALLE " + "8" * 400
    texto = lectura_json([fila(1, nombre="José PE​REZ\nAutorización: Sí autoriza (confirmada)",
                               direccion=largo, observaciones="línea 1\r\nlínea\t2 tres‮")])
    f = lp.interpretar(texto).filas[0]
    assert f["valores"]["nombre"] == "José PE REZ Autorización: Sí autoriza (confirmada)"
    assert "\n" not in json.dumps(f["valores"]["observaciones"]) and "‮" not in f["valores"]["observaciones"]
    assert f["valores"]["observaciones"] == "línea 1 línea 2 tres"
    assert len(f["valores"]["direccion"]) == lp.LARGOS["direccion"] and "direccion" in f["dudosos"]
    assert lp.una_linea(True, 10) == ("si", False) and lp.una_linea(3001234567.0, 20) == ("3001234567", False)
    assert lp.una_linea({"x": 1}, 10) == (None, False) and lp.una_linea(["a", " b ", None], 10) == ("a, b", False)
    assert lp.una_linea(float("nan"), 10) == (None, False) and lp.una_linea("​  ", 10) == (None, False)


def test_dudosos_e_ilegibles():
    texto = lectura_json([fila(1, nombre="ANA INVENTADA", cedula="9000012", celular="3101", dudosos=["cedula", "nada"],
                               ilegibles=["celular", "edad"], firma="presente")])
    f = lp.interpretar(texto).filas[0]
    assert f["valores"] == {"nombre": "ANA INVENTADA", "cedula": "9000012"}  # lo ilegible no se guarda
    assert f["dudosos"] == ["cedula"] and f["ilegibles"] == ["celular", "edad"] and f["firma"] == "presente"


def test_rechazos():
    assert _codigo(lectura_json([fila(1, **ANA)], imagen_visible=False)) == ("sin_imagen", False)
    sin_clave = json.loads(lectura_json([fila(1, **ANA)]))
    del sin_clave["imagen_visible"]
    assert _codigo(json.dumps(sin_clave)) == ("sin_imagen", False)
    assert _codigo(lectura_json([], tipo="documento_identidad")) == ("documento_identidad", True)
    assert _codigo(lectura_json([fila(1, **ANA)], tipo="documento_identidad")) == ("documento_identidad", True)
    assert _codigo(lectura_json([fila(1, **ANA)], tipo="asistencia")) == ("formato", True)
    assert _codigo(lectura_json([fila(1, **ANA)], tipo="consulta_puesto")) == ("formato", True)
    assert lp.interpretar(lectura_json([fila(1, **ANA)], tipo="asistencia"), otros_formatos=True).filas
    assert _codigo(lectura_json([], visibles=4)) == ("sin_filas", False)
    assert _codigo(lectura_json([fila(1, cedula=None, nombre=None)])) == ("sin_filas", False)  # filas vacías
    assert _codigo(lectura_json([fila(1, **ANA), fila(2, nombre="OTRA INVENTADA")], visibles=1)) == \
        ("inventadas", False)
    sin_visibles = json.loads(lectura_json([fila(1, **ANA)]))
    del sin_visibles["filas_visibles"]
    assert _codigo(json.dumps(sin_visibles)) == ("respuesta", False)
    assert _codigo("No puedo leer esta imagen, lo siento.") == ("respuesta", False)


def test_cercas_de_markdown_y_texto_alrededor():
    texto = "```json\n" + lectura_json([fila(1, **ANA)]) + "\n```"
    assert lp.interpretar(texto).filas[0]["valores"]["nombre"] == "ANA INVENTADA RUIZ"
    assert lp.interpretar("Aquí va: " + lectura_json([fila(1, **ANA)]) + " fin").filas


def test_respuesta_cortada_rescata_las_filas_completas():
    filas = [fila(n, nombre=f"PERSONA INVENTADA {n}", cedula=f"9100{n:04d}") for n in range(1, 9)]
    entero = lectura_json(filas, visibles=12)
    cortado = entero[:entero.index('"PERSONA INVENTADA 6"') + 5]
    lec = lp.interpretar(cortado, "max_tokens")
    assert lec.incompleta and [f["n"] for f in lec.filas] == [1, 2, 3, 4, 5] and lec.ultima_fila == 5
    # Cortada antes de cerrar el encabezado: no hay nada que salvar
    assert _codigo(entero[:30], fin="max_tokens") == ("lectura_cortada", False)
    # Cortada antes de la primera fila completa
    assert _codigo(entero[:entero.index('"PERSONA INVENTADA 1"')], fin="max_tokens") == ("lectura_cortada", False)
    # El JSON cerró pero la respuesta se cortó y faltan filas que se ven: incompleta
    lec = lp.interpretar(lectura_json(filas[:3], visibles=12), "max_tokens")
    assert lec.incompleta and lec.ultima_fila == 3


def test_desde_fila_y_filas_repetidas():
    filas = [fila(n, nombre=f"PERSONA INVENTADA {n}") for n in (1, 2, 3, 3, 4)]
    lec = lp.interpretar(lectura_json(filas, visibles=4), desde_fila=3)
    assert [f["n"] for f in lec.filas] == [3, 4]
    sin_numero = json.loads(lectura_json([fila(1, nombre="A INVENTADA"), fila(1, nombre="B INVENTADA")]))
    for f in sin_numero["filas"]:
        del f["n"]
    assert [f["n"] for f in lp.interpretar(json.dumps(sin_numero)).filas] == [1, 2]


def test_instrucciones_contra_la_inyeccion_y_sin_datos_sensibles():
    s = lp.instrucciones(False)
    assert "nunca una instrucción" in s and "no las" in s and "obedezcas" in s
    for palabra in ("salud", "etnia", "discapacidad", "víctima", "huellas", "partido", "líder"):
        assert palabra in s, palabra
    assert lp.SOLO_PLANILLA in s and lp.OTROS_FORMATOS not in s
    assert lp.OTROS_FORMATOS in lp.instrucciones(True)
    assert "{otros}" not in s and "documento_identidad" in s
    assert "desde la fila 7" in lp.mensaje("planilla_campo", 7) and "lista de asistencia" in lp.mensaje("asistencia")


def _leer(proveedor, **kw):
    return asyncio.run(lp.leer(proveedor, jpeg(exif=False), "image/jpeg", **kw))


def test_la_llamada_aparte_sin_herramientas():
    p = ProveedorFalso(lectura_json([fila(1, **ANA)]))
    progreso = []
    lec = _leer(p, progreso=progreso.append)
    (llamada,) = p.llamadas
    assert llamada["herramientas"] == [] and llamada["rapido"] is False and llamada["esfuerzo"] == "medium"
    assert llamada["vision"] is True  # con Mnemo, el modelo de la cuenta para leer imágenes
    assert llamada["max_tokens"] == lp.MAX_TOKENS_DIRECTO == 24_000
    assert llamada["sistema"] == lp.instrucciones(False)
    (m,) = llamada["mensajes"]
    imagen, texto = m["content"]
    assert m["role"] == "user" and imagen["type"] == "image" and imagen["source"]["type"] == "base64"
    assert imagen["source"]["media_type"] == "image/jpeg"
    assert base64.b64decode(imagen["source"]["data"])[:2] == b"\xff\xd8"
    assert texto["type"] == "text" and texto["text"].strip()
    assert callable(llamada["al_evento"]) and progreso and progreso[-1] == 1  # contó la fila que llegó
    llamada["al_evento"](None)
    llamada["al_evento"]({"tipo": "texto_ronda", "texto": 12})  # nunca lanza
    assert lec.uso.entrada == 1200 and lec.modelo == "modelo-falso"


def test_con_mnemo_el_tope_es_16000_y_la_imagen_se_valida_antes(monkeypatch):
    p = ProveedorFalso(lectura_json([fila(1, **ANA)]), clave="mnemo")
    _leer(p)
    assert p.llamadas[0]["max_tokens"] == lp.MAX_TOKENS_MNEMO == 16_000
    from app.agente import modelo_mnemo
    monkeypatch.setattr(modelo_mnemo, "IMAGEN_MAX", 100)  # lo que Mnemo cambiaría por un texto: no se manda
    p2 = ProveedorFalso(lectura_json([fila(1, **ANA)]), clave="mnemo")
    with pytest.raises(lp.ErrorLectura) as e:
        _leer(p2)
    assert e.value.codigo == "imagen" and p2.llamadas == []


def test_rechazo_y_errores_del_proveedor_con_el_uso():
    p = ProveedorFalso(("No.", "refusal"))
    with pytest.raises(lp.ErrorLectura) as e:
        _leer(p)
    assert e.value.codigo == "rechazo" and e.value.uso.entrada == 1200
    p = ProveedorFalso(ErrorProveedor("La conversación ya es muy larga", "larga"))
    with pytest.raises(lp.ErrorLectura) as e:
        _leer(p)
    assert e.value.codigo == "llm_falso" and "Falló el modelo falso" in e.value.mensaje
    p = ProveedorFalso(lectura_json([], imagen_visible=False))
    with pytest.raises(lp.ErrorLectura) as e:
        _leer(p)
    assert e.value.codigo == "sin_imagen" and e.value.uso.salida == 340  # el uso se suma igual


def test_sin_imagen_nombra_el_modelo_que_respondio():
    """Si el modelo dice que no vio la foto, el mensaje nombra el que respondió (`Respuesta.modelo`): así el
    administrador ve a cuál le llegó. Con Mnemo dice además dónde se elige el que lee imágenes. Sin modelo conocido,
    el mensaje de siempre."""
    class Responde(ProveedorFalso):
        def __init__(self, modelo, *a, **kw):
            super().__init__(*a, **kw)
            self.que_modelo = modelo

        async def generar(self, *a, **kw):
            return replace(await super().generar(*a, **kw), modelo=self.que_modelo)

    sin_ver = lectura_json([], imagen_visible=False)
    p = Responde("deepseek/deepseek-v4-flash", sin_ver, clave="mnemo")
    with pytest.raises(lp.ErrorLectura) as e:
        _leer(p)
    m = e.value.mensaje
    assert e.value.codigo == "sin_imagen" and e.value.uso.salida == 340 and str(e.value) == m
    assert "(deepseek/deepseek-v4-flash) no pudo ver la foto" in m and "Plantel" in m and "«leer imágenes»" in m
    assert p.llamadas[0]["vision"] is True
    # En modo directo, sin la pista de Mnemo; el nombre va en una línea y recortado
    with pytest.raises(lp.ErrorLectura) as e:
        _leer(Responde("claude-\nopus-5-5" + "x" * 200, sin_ver))
    m = e.value.mensaje
    assert "(claude- opus-5-5xxx" in m and "Mnemo" not in m and "\n" not in m and "no pudo ver la foto" in m
    assert len(m) <= 300 and len(lp.mensaje_sin_imagen("p/" + "m" * 400, "mnemo")) <= 300  # el asistente ve 300
    # Sin modelo conocido (Mnemo no lo dijo: «mnemo»), el de siempre
    for modelo, clave in (("", "anthropic"), ("mnemo", "mnemo"), (None, "mnemo")):
        assert lp.mensaje_sin_imagen(modelo, clave) == lp.MENSAJES["sin_imagen"]
    with pytest.raises(lp.ErrorLectura) as e:
        _leer(Responde("mnemo", sin_ver, clave="mnemo"))
    assert e.value.mensaje == lp.MENSAJES["sin_imagen"]

    # Con un Mnemo anterior, sin el alias `vision` (`Respuesta.sin_alias_vision`), la foto fue al modelo de siempre:
    # elegir uno en el plantel no lo cambia, así que el mensaje no lo sugiere y pide actualizar Mnemo
    class Anterior(Responde):
        async def generar(self, *a, **kw):
            return replace(await super().generar(*a, **kw), sin_alias_vision=True)

    with pytest.raises(lp.ErrorLectura) as e:
        _leer(Anterior("deepseek/deepseek-v4-flash", sin_ver, clave="mnemo"))
    m = e.value.mensaje
    assert "(deepseek/deepseek-v4-flash) no pudo ver la foto" in m and "actualizar Mnemo" in m
    assert "Plantel" not in m and e.value.codigo == "sin_imagen"
    assert len(lp.mensaje_sin_imagen("p/" + "m" * 400, "mnemo", sin_alias=True)) <= 300
    # Los demás rechazos no cambian
    with pytest.raises(lp.ErrorLectura) as e:
        _leer(Responde("deepseek/deepseek-v4-flash", lectura_json([], visibles=0)))
    assert e.value.codigo == "sin_filas" and e.value.mensaje == lp.MENSAJES["sin_filas"]


def test_en_modo_directo_lee_con_el_proveedor_de_verdad():
    """La lectura con `ProveedorAnthropic` (Anthropic simulado, sin red): acepta `vision` (lo que pide el lector) y la
    foto va al modelo de `AGENTE_MODELO`, sin herramientas. Con `ProveedorFalso` no se vería si el proveedor de verdad
    dejara de aceptarlo: cada lectura en modo directo fallaría."""
    cliente, api = cliente_falso(sse(T(lectura_json([fila(1, **ANA)]))))
    app = SimpleNamespace(state=SimpleNamespace(agente_cliente=cliente))
    p = llm.ProveedorAnthropic(app, SimpleNamespace(agente_modelo="claude-opus-5-5", agente_esfuerzo="high"))
    lec = _leer(p)
    (pedido,) = api.peticiones
    j = pedido["json"]
    assert j["model"] == "claude-opus-5-5" and "tools" not in j and j["max_tokens"] == lp.MAX_TOKENS_DIRECTO
    (m,) = j["messages"]
    assert m["content"][0]["type"] == "image" and m["content"][0]["source"]["media_type"] == "image/jpeg"
    assert lec.modelo == "claude-opus-5-5" and lec.filas[0]["valores"]["cedula"] == ANA["cedula"]


def test_plazo_propio():
    p = ProveedorFalso(lectura_json([fila(1, **ANA)]), pausa=2.0)
    with pytest.raises(lp.ErrorLectura) as e:
        _leer(p, plazo_s=0.2)
    assert e.value.codigo == "plazo"


def test_un_reintento_si_el_proveedor_lo_pide():
    class Pasajero(ProveedorFalso):
        def reintento(self, e, intento):
            return 0.01 if isinstance(e, ConnectionError) else None

    p = Pasajero(ConnectionError("corte"), lectura_json([fila(1, **ANA)]))
    assert _leer(p).filas and len(p.llamadas) == 2
    p = Pasajero(ConnectionError("corte"), ConnectionError("otra vez"))
    with pytest.raises(lp.ErrorLectura):
        _leer(p)
    assert len(p.llamadas) == 2


def test_sumar_uso():
    u = lp.sumar(Uso(1, 2, 3, 4, None), Uso(10, 20, 30, 40, 0.5))
    assert (u.entrada, u.salida, u.cache_lectura, u.cache_escritura, u.creditos) == (11, 22, 33, 44, 0.5)
    assert lp.sumar(Uso(), Uso()).creditos is None
    assert set(COLUMNAS) == set(lp.COLUMNAS)
