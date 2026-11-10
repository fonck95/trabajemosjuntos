"""Herramientas del asistente sobre personas (`app/agente/herramientas/personas.py`) y la minimización
(`app/agente/minimizar.py`): búsquedas por rol con alcance y proyección, nada de datos sensibles, listas, cédulas o
teléfonos completos, correos ni coordenadas en lo que llega al modelo, quien no autorizó, lecturas y presupuesto del
planillero, restricciones del consultor, escrituras con confirmación (que no escribe) e idempotencia (repetir el mismo
tool_use no duplica), errores de permiso y de conflicto, entradas raras y esquemas para la Messages API.

Las herramientas corren en el bucle de la aplicación (`ayudas_agente.correr`) y llaman a la API de verdad por ASGI con
la sesión de cada rol. Solo datos inventados; nunca se llama a Anthropic ni a Mnemo."""
from __future__ import annotations

import functools
import json
import re
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import ayudas_agente as aa
from ayudas_g3 import autorizada, contactable, coordinador, persona, recorrer, tomar
from conftest import insertar_personas
from app import modelo
from app.agente import herramientas, minimizar
from app.agente.herramientas import personas as hp
from app.agente.herramientas.base import Confirmacion, ErrorHerramienta, Resultado

H = {h.nombre: h for h in hp.HERRAMIENTAS}
MIAS = set(H)
LECTURAS = {"buscar_personas", "ver_persona", "personas_parecidas"}
DEL_CONSULTOR = {"buscar_personas", "ver_persona", "registrar_acercamiento", "registrar_autorizacion",
                 "agregar_telefono"}

# Lo que nunca llega al modelo, venga de donde venga (claves y valores de la ficha rica)
CLAVES_VEDADAS = {"sensibles", "sensibles_registrados", "sensibles_autorizados", "listas", "lider", "cedula",
                  "telefono", "telefono2", "correo", "lat", "lon", "punto", "origen", "procedencia", "historial",
                  "alternos", "fuentes", "cedula_origen", "cedulas_anteriores", "cedula_en_traspaso", "ficha",
                  "regimen_salud", "fecha_nacimiento", "coincidencias", "autorizacion", "avance", "creado_por",
                  "actualizado_por", "nombre_fon", "nombre_norm"}
CEDULA, CEDULA_VIEJA, TEL, TEL2, CORREO = "91000777", "91000111", "3009990011", "3104445566", "eustaquia@correo.co"
VALORES_VEDADOS = (CEDULA, CEDULA_VIEJA, TEL, TEL2, CORREO, "viejo@correo.co", "Lista Inventada", "Raizal",
                   "Pastafari", "0589300000099", "1986-03-14", "Subsidiado", "7.006123", "-73.911234",
                   "Líder comunitario", "partido inventado")


# ───────────────────────────── Ayudas ─────────────────────────────

def _ejecutar(cliente, ctx, nombre: str, entrada: dict):
    return aa.correr(cliente, aa.ejecutar, H[nombre], ctx, entrada)


def _confirmar(cliente, ctx, nombre: str, entrada: dict) -> Confirmacion:
    return aa.correr(cliente, aa.confirmar, H[nombre], ctx, entrada)


def _error(cliente, fn, *args) -> ErrorHerramienta:
    with pytest.raises(ErrorHerramienta) as e:
        aa.correr(cliente, fn, *args)
    return e.value


def _error_ejecutar(cliente, ctx, nombre, entrada) -> ErrorHerramienta:
    return _error(cliente, aa.ejecutar, H[nombre], ctx, entrada)


def _error_confirmar(cliente, ctx, nombre, entrada) -> ErrorHerramienta:
    return _error(cliente, aa.confirmar, H[nombre], ctx, entrada)


def sin_datos(x, *otros: str) -> None:
    """Ninguna clave vedada en todo el JSON y ningún valor de la ficha rica (ni cédulas, teléfonos o correos)."""
    for ruta, k, _ in recorrer(x):
        assert k not in CLAVES_VEDADAS, (ruta, k)
    texto = json.dumps(x, ensure_ascii=False, default=str)
    for v in (*VALORES_VEDADOS, *otros):
        assert v not in texto, v


def _modelo(r: Resultado):
    """Lo que de verdad ve el modelo: el texto del tool_result."""
    return json.loads(r.texto_para_modelo())


def _campos(db) -> None:
    """Dos campos propios: «religion» (sensible) y «talla» (no), como los crea Ajustes."""
    for i, (clave, sensible) in enumerate((("religion", True), ("talla", False)), 900):
        db.campos.update_one({"clave": clave}, {"$setOnInsert": {
            "_id": i, "clave": clave, "etiqueta": clave.capitalize(), "tipo": "texto", "opciones": [], "orden": i,
            "activo": True, "sensible": sensible}}, upsert=True)


def _rica(db, **extra) -> int:
    """Una ficha inventada con todo lo que el modelo no debe recibir (y alguna etiqueta y campo propio que sí)."""
    _campos(db)
    lider = db.etiquetas.find_one({"nombre": "Líder comunitario"})["_id"]
    vivienda = db.etiquetas.find_one({"nombre": "Vivienda"})["_id"]
    pid = persona(
        db, nombre="EUSTAQUIA INVENTADA RICA", cedula=CEDULA, telefono=TEL, tipo_documento="CC", correo=CORREO,
        cedula_origen="cedulas", cedulas_anteriores=[CEDULA_VIEJA], lider=True, listas=["Lista Inventada"],
        sensibles={"etnia": "Raizal"}, sensibles_autorizados=["etnia"], fuentes=["tramites", "cedulas"],
        origen=[{"fuente": "cedulas", "datos": {"partido": "partido inventado"}}],
        procedencia={"cedula": {"fuente": "cedulas", "ts": "2026-01-01T00:00:00+00:00", "uid": None}},
        alternos=[{"campo": "correo", "valor": "viejo@correo.co", "fuente": "cedulas", "ts": "2026-01-01",
                   "uid": None}],
        telefonos=[{"numero": TEL, "tipo": "celular", "fuentes": ["cedulas"], "estado": "confirmado",
                    "no_contactar": False},
                   {"numero": TEL2, "tipo": "celular", "fuentes": ["tramites"], "estado": "equivocado",
                    "no_contactar": False}],
        votacion={"puesto_id": None, "puesto_nombre": None, "puesto_texto": "ESCUELA INVENTADA", "mesa": 3,
                  "mesa_texto": None, "donde": "yondo", "eleccion": None, "estado": "por_confirmar",
                  "fuente": "cedulas"},
        lat=7.006123, lon=-73.911234, punto={"type": "Point", "coordinates": [-73.911234, 7.006123]},
        geo_precision="direccion", direccion="CALLE 50 # 48-21", ficha="0589300000099", fecha_nacimiento="1986-03-14",
        regimen_salud="Subsidiado", observaciones=f"Llamar al {TEL} o escribir a {CORREO}",
        notas=[{"id": "n1", "texto": f"Dictó su cédula {CEDULA} en la reunión", "autor": "admin", "autor_uid": 0,
                "creado_en": "2026-11-01T10:00:00+00:00", "reunion_id": None}],
        etiquetas=[lider, vivienda], extra={"religion": "Pastafari", "talla": "M"}, edad=40, **extra)
    autorizada(db, pid)
    return pid


def _conteos(db, pid: int) -> dict:
    p = db.personas.find_one({"_id": pid}) or {}
    return {"personas": db.personas.count_documents({}), "notas": len(p.get("notas") or []),
            "telefonos": len(p.get("telefonos") or []), "acercamientos": db.acercamientos.count_documents({}),
            "autorizaciones": db.autorizaciones.count_documents({}),
            "auditoria": db.auditoria.count_documents({"entidad": "persona"})}


# ───────────────────────────── Catálogo y esquemas ─────────────────────────────

def test_para_da_a_cada_rol_solo_sus_herramientas(sesion, como):
    app, db = sesion.app, sesion.app.state.db
    k = coordinador(app, db)
    p, c = como("planillero"), como("consultor")
    quienes = {"admin": aa.quien_de(app, 0), "coordinador": aa.quien_de(app, k.uid),
               "planillero": aa.quien_de(app, p.uid), "consultor": aa.quien_de(app, c.uid)}
    esperado = {"admin": MIAS, "coordinador": MIAS, "planillero": MIAS, "consultor": DEL_CONSULTOR}
    for rol, quien in quienes.items():
        nombres = [h.nombre for h in herramientas.para(quien, {"escritura": True}, app.state.cfg)]
        assert set(nombres) & MIAS == esperado[rol], rol
        assert len(nombres) == len(set(nombres)), rol
        # Sin escritura en Ajustes: solo las lecturas que su rol permite
        sin = {h.nombre for h in herramientas.para(quien, {"escritura": False}, app.state.cfg)} & MIAS
        assert sin == esperado[rol] & LECTURAS, rol
    # El orden de las fijas empieza por las de personas, en el orden de su módulo
    assert [h.nombre for h in herramientas.fijas()][:len(hp.HERRAMIENTAS)] == [h.nombre for h in hp.HERRAMIENTAS]


PALABRAS_ESQUEMA = {"type", "properties", "required", "additionalProperties", "description", "enum", "items",
                    "minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems", "default", "anyOf"}


def _palabras(s, ruta=""):
    """Toda palabra clave del esquema (sin entrar a los nombres de las propiedades)."""
    if isinstance(s, dict):
        for k, v in s.items():
            if k == "properties":
                for nombre, sub in v.items():
                    yield from _palabras(sub, f"{ruta}.{nombre}")
            else:
                yield ruta, k
                yield from _palabras(v, f"{ruta}.{k}")
    elif isinstance(s, list):
        for v in s:
            yield from _palabras(v, ruta)


def _objetos(s):
    if isinstance(s, dict):
        if s.get("type") == "object":
            yield s
        for v in s.values():
            yield from _objetos(v)
    elif isinstance(s, list):
        for v in s:
            yield from _objetos(v)


def test_definiciones_son_json_schema_validos_para_la_messages_api():
    assert len(H) == len(hp.HERRAMIENTAS) == 10
    for h in hp.HERRAMIENTAS:
        d = h.definicion()
        assert set(d) == {"name", "description", "input_schema", "eager_input_streaming"}, h.nombre
        assert re.fullmatch(r"[a-z_]{3,64}", d["name"]) and d["eager_input_streaming"] is True
        assert 200 < len(d["description"]) < 1500, h.nombre
        assert re.match(r"^\w+(ando|endo|iendo)\b", h.etiqueta), h.etiqueta  # en gerundio
        s = d["input_schema"]
        texto = json.dumps(s, ensure_ascii=False)
        assert "$ref" not in texto and "$defs" not in texto and '"title"' not in texto, h.nombre
        assert s["type"] == "object" and isinstance(s["properties"], dict) and s["properties"], h.nombre
        for obj in _objetos(s):  # todo objeto, también los anidados: cerrado y con sus obligatorias declaradas
            assert obj.get("additionalProperties") is False, h.nombre
            assert set(obj.get("required", [])) <= set(obj.get("properties", {})), h.nombre
        for ruta, k in _palabras(s):
            assert k in PALABRAS_ESQUEMA, (h.nombre, ruta, k)
        for nombre, prop in s["properties"].items():
            assert "type" in prop or "anyOf" in prop or "enum" in prop, (h.nombre, nombre)
        # Lo que pone `confirmar` (las huellas de la tarjeta) no se le ofrece al modelo
        assert "huellas" not in s["properties"] and "base" not in s["properties"], h.nombre
        assert (h.tipo == "escritura") == (h.confirmar is not None), h.nombre
        assert h.tipo == ("lectura" if h.nombre in LECTURAS else "escritura"), h.nombre


# ───────────────────────────── Lecturas por rol ─────────────────────────────

def test_administrador_y_coordinador_reciben_todo_minimizado(sesion):
    app, db = sesion.app, sesion.app.state.db
    pid = _rica(db)
    k = coordinador(app, db)
    for cli in (sesion, k):
        ctx = aa.contexto(app, cli)
        rapida = _ejecutar(sesion, ctx, "buscar_personas", {"q": "eustaquia"})
        assert rapida.contenido["tipo"] == "busqueda_rapida" and rapida.personas == {pid}
        fila = rapida.contenido["filas"][0]
        assert fila["cedula_ult3"] == "···777" and fila["telefono_mascara"] == "···0011" and fila["telefonos_n"] == 1
        lista = _ejecutar(sesion, ctx, "buscar_personas", {"q": "eustaquia", "filtros": {"consentimiento": "si",
                                                                                         "con_telefono": True}})
        assert lista.contenido["tipo"] == "lista" and lista.contenido["total"] == 1 and lista.personas == {pid}
        f = _ejecutar(sesion, ctx, "ver_persona", {"persona_id": pid})
        assert f.personas == {pid} and "EUSTAQUIA" in f.resumen and f"#{pid}" in f.resumen
        ficha = f.contenido
        assert ficha["cedula_ult3"] == "···777" and ficha["tiene_cedula"] and ficha["tiene_correo"] is True
        assert [t["numero"] for t in ficha["telefonos"]] == ["···0011", "···5566"]
        assert ficha["telefonos"][0] == {"numero": "···0011", "tipo": "celular", "estado": "confirmado",
                                         "whatsapp": None, "indice": 0, "principal": True}
        assert ficha["telefonos"][1]["indice"] is None  # el equivocado no se usa para contactar
        assert [e["nombre"] for e in ficha["etiquetas"]] == ["Vivienda"]  # «Líder comunitario» es sensible
        assert ficha["extra"] == {"talla": "M"}  # «religion» es un campo propio sensible
        assert ficha["votacion"] == {"puesto_texto": "ESCUELA INVENTADA", "mesa": 3, "donde": "yondo",
                                     "estado": "por_confirmar"}
        assert ficha["notas"][0]["texto"] == "Dictó su cédula ···777 en la reunión"
        assert "···011" in ficha["observaciones"] and "[correo]" in ficha["observaciones"]
        assert ficha["direccion"] == "CALLE 50 # 48-21" and ficha["edad_efectiva"] == 40
        for r in (rapida, lista, f):
            sin_datos(r.contenido)
            sin_datos(_modelo(r))
        # La API sí registró las lecturas (también las de A y K)
        assert db.lecturas.count_documents({"uid": getattr(cli, "uid", 0), "pid": pid, "ficha": True}) == 1
        aa.correr(sesion, ctx.api.cerrar)


def test_planillero_lista_su_zona_y_busca_en_toda_la_base(sesion, como):
    app, db = sesion.app, sesion.app.state.db
    l1, l2 = [x["_id"] for x in db.lugares.find({}, {"_id": 1}).sort("_id", 1).limit(2)]
    suyas = [persona(db, nombre=f"FILOMENA INVENTADA ZONA {i}", lugar_id=l1, telefono=f"31200000{i:02d}")
             for i in range(3)]
    ajena = persona(db, nombre="FILOMENA INVENTADA AJENA", lugar_id=l2, cedula="92000123")
    rica = _rica(db, lugar_id=l1)
    p = como("planillero", asignacion={"lugares": [l1], "areas": []})
    ctx = aa.contexto(app, p)
    lista = _ejecutar(sesion, ctx, "buscar_personas", {"q": "filomena", "orden": "nombre"})
    assert lista.contenido["total"] == 3 and {f["id"] for f in lista.contenido["filas"]} == set(suyas)
    assert lista.personas == set(suyas) and "zona" in lista.contenido["alcance"]
    assert all(f["telefono_mascara"] and f["telefono_mascara"].startswith("···") for f in lista.contenido["filas"])
    # Por filtros: solo su zona; la búsqueda rápida, en toda la base (como en la interfaz)
    todas = _ejecutar(sesion, ctx, "buscar_personas", {"filtros": {"tratables": True}, "por_pagina": 10})
    assert {f["id"] for f in todas.contenido["filas"]} == {*suyas, rica} and todas.contenido["paginas"] == 1
    rapida = _ejecutar(sesion, ctx, "buscar_personas", {"q": "FILOMENA INVENTADA"})
    assert ajena in rapida.personas and rapida.contenido["tipo"] == "busqueda_rapida"
    assert next(f for f in rapida.contenido["filas"] if f["id"] == ajena)["cedula_ult3"] == "···123"
    f = _ejecutar(sesion, ctx, "ver_persona", {"persona_id": rica})
    assert f.contenido["cedula_ult3"] == "···777" and "Líder comunitario" not in json.dumps(f.contenido)
    for r in (lista, todas, rapida, f):
        sin_datos(_modelo(r), "92000123")
    assert db.lecturas.count_documents({"uid": p.uid, "pid": rica, "ficha": True}) == 1
    assert db.lecturas.count_documents({"uid": p.uid}) == 5
    # Lo que su rol no filtra es un 403 de la API (codigo permiso), no una lista sin filtro
    for filtros in ({"menor": False}, {"creado_por": 0}):
        e = _error_ejecutar(sesion, ctx, "buscar_personas", {"filtros": filtros})
        assert e.codigo == "permiso" and e.estado == 403 and not e.fatal


def test_presupuesto_del_planillero_termina_el_turno(sesion, como):
    app, db = sesion.app, sesion.app.state.db
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"presupuesto_diario": {"planillero": 3, "consultor": 300}}},
                       upsert=True)
    insertar_personas(db, [{"nombre": f"PRESUPUESTO INVENTADO {i}", "consentimiento": "pendiente"} for i in range(6)])
    p = como("planillero")
    ctx = aa.contexto(app, p)
    e = _error_ejecutar(sesion, ctx, "buscar_personas", {"q": "presupuesto", "orden": "nombre"})
    assert e.codigo == "volumen" and e.estado == 429 and e.fatal is True
    assert db.lecturas.count_documents({"uid": p.uid}) == 0  # las personas de esa respuesta no se sirvieron
    # Tras el primer rechazo del día ya no recibe listas, aunque pida menos
    e = _error_ejecutar(sesion, ctx, "buscar_personas", {"filtros": {"tratables": True}})
    assert e.codigo == "volumen" and e.fatal


def test_consultor_busca_por_nombre_o_numero_y_ve_solo_su_trabajo(sesion, como):
    app, db = sesion.app, sesion.app.state.db
    pid = _rica(db)
    c = como("consultor")
    ctx = aa.contexto(app, c)
    r = _ejecutar(sesion, ctx, "buscar_personas", {"q": "eustaquia"})
    assert r.contenido["filas"] == [{"id": pid, "nombre": "EUSTAQUIA INVENTADA RICA", "lugar": None,
                                     "abordaje_estado": "sin_abordar", "contactable": True}]
    assert r.personas == {pid}
    por_numero = _ejecutar(sesion, ctx, "buscar_personas", {"q": TEL})
    assert por_numero.personas == {pid} and db.auditoria.count_documents({"accion": "buscar_telefono"}) == 1
    corta = _ejecutar(sesion, ctx, "buscar_personas", {"q": "eu"})
    assert corta.contenido["total"] == 0 and "3 letras" in corta.contenido["aviso"]
    assert _error_ejecutar(sesion, ctx, "buscar_personas", {"q": "300999"}).codigo == "invalido"
    for entrada in ({"q": "eustaquia", "filtros": {"zona": "urbana"}}, {"q": "eustaquia", "orden": "nombre"},
                    {"q": "eustaquia", "pagina": 2}, {"filtros": {"tratables": True}}):
        e = _error_ejecutar(sesion, ctx, "buscar_personas", entrada)
        assert e.codigo == "permiso" and "nombre" in e.mensaje, entrada
    # La ficha, solo de las personas de su trabajo
    e = _error_ejecutar(sesion, ctx, "ver_persona", {"persona_id": pid})
    assert e.codigo == "permiso" and e.estado == 403
    tomar(c, pid)
    f = _ejecutar(sesion, ctx, "ver_persona", {"persona_id": pid}).contenido
    assert set(f) <= {"id", "nombre", "cedula_ult3", "rango_edad", "sexo", "telefonos", "lugar_nombre", "zona",
                      "puesto_nombre", "consentimiento", "consentimiento_canales", "contacto_habilitado", "abordaje",
                      "acercamientos", "acercamientos_n", "requiere_actualizacion", "situacion", "faltan", "en_curso",
                      "editables", "avisos", "tiene_cedula"}
    assert f["telefonos"] == [{"numero": "···0011", "tipo": "celular", "estado": "confirmado", "whatsapp": None,
                               "indice": 0, "principal": True}]
    assert set(f["en_curso"]) == {"hasta"}
    sin_datos(f)
    # Registra llamadas, no visitas; el número se elige por su índice y no vuelve al modelo
    e = _error_confirmar(sesion, ctx, "registrar_acercamiento", {"persona_id": pid, "canal": "visita",
                                                                 "resultado": "contesto"})
    assert e.codigo == "permiso"
    entrada = {"persona_id": pid, "canal": "llamada", "resultado": "contesto", "telefono_indice": 0,
               "confirma_numero": True, "nota": "Contestó bien"}
    tarjeta = _confirmar(sesion, ctx, "registrar_acercamiento", entrada)
    assert ("Número", "···0011") in tarjeta.detalle and db.acercamientos.count_documents({}) == 0
    hecho = _ejecutar(sesion, ctx, "registrar_acercamiento", entrada)
    assert hecho.contenido["registrado"] and hecho.contenido["abordaje"]["estado"] == "contactado"
    assert db.acercamientos.find_one({"persona_id": pid})["telefono"] == TEL
    sin_datos(_modelo(hecho))
    aa.correr(sesion, ctx.api.cerrar)


def test_quien_no_autorizo_sale_minimo_y_no_se_escribe(sesion, como):
    app, db = sesion.app, sesion.app.state.db
    pid = _rica(db)
    db.personas.update_one({"_id": pid}, {"$set": {"consentimiento": "no", "contacto_habilitado": False}})
    p = como("planillero")
    for cli in (sesion, p):
        ctx = aa.contexto(app, cli)
        f = _ejecutar(sesion, ctx, "ver_persona", {"persona_id": pid})
        assert set(f.contenido) == {"id", "nombre", "lugar", "consentimiento", "aviso"} and f.personas == {pid}
        assert f.contenido["consentimiento"] == "no" and "no autorizó" in f.resumen
        fila = _ejecutar(sesion, ctx, "buscar_personas", {"q": "eustaquia"}).contenido["filas"][0]
        assert set(fila) == {"id", "nombre", "lugar", "consentimiento", "aviso"}
        lista = _ejecutar(sesion, ctx, "buscar_personas", {"q": "eustaquia", "orden": "nombre"}).contenido["filas"]
        assert set(lista[0]) == {"id", "nombre", "lugar", "consentimiento", "aviso"}
        # Ni el administrador escribe por el asistente en su ficha; solo se registra su autorización
        for nombre, entrada in (("agregar_nota", {"persona_id": pid, "texto": "Nota inventada"}),
                                ("agregar_telefono", {"persona_id": pid, "numero": "3201112233"}),
                                ("editar_persona", {"persona_id": pid, "cambios": {"ocupacion": "Pescadora"}}),
                                ("ubicar_persona", {"persona_id": pid, "automatica": True})):
            e = _error_confirmar(sesion, ctx, nombre, entrada)
            assert e.codigo == "no_contactable" and e.detalle == {"motivo": "no_autorizo"}, nombre
    ctx = aa.contexto(app, p)
    entrada = {"persona_id": pid, "estado": "si", "medio": "escrito", "canales": ["llamada"],
               "evidencia": "Planilla inventada, folio 3", "mayor_declarado": True}
    tarjeta = _confirmar(sesion, ctx, "registrar_autorizacion", entrada)
    assert ("Autorización", "No autoriza → Sí autoriza") in tarjeta.detalle
    r = _ejecutar(sesion, ctx, "registrar_autorizacion", entrada)
    assert r.contenido["consentimiento"] == "si" and db.personas.find_one({"_id": pid})["consentimiento"] == "si"
    sin_datos(_modelo(r))


def test_parecidas_minimizadas(sesion, como):
    app, db = sesion.app, sesion.app.state.db
    pid = _rica(db)
    otra = persona(db, nombre="EUSTAQUIA INVENTADA RICAS", telefono=TEL, cedula="91000888")
    for cli in (sesion, como("planillero")):
        ctx = aa.contexto(app, cli)
        r = _ejecutar(sesion, ctx, "personas_parecidas", {"persona_id": pid})
        assert r.personas == {pid, otra} and [f["id"] for f in r.contenido["parecidas"]] == [otra]
        f = r.contenido["parecidas"][0]
        assert f["parecido"] >= 80 and f["tiene_cedula"] and f["cedula_distinta"] and f["cedula_ult3"] == "···888"
        alta = _ejecutar(sesion, ctx, "personas_parecidas", {"nombre": "Eustaquia Inventada Rica", "telefono": TEL})
        assert {x["id"] for x in alta.contenido["parecidas"]} == {pid, otra} and alta.personas == {pid, otra}
        sin_datos(_modelo(r), "91000888")
        sin_datos(_modelo(alta), "91000888")


# ───────────────────────────── Escrituras: confirmar no escribe; ejecutar escribe una vez ─────────────────────────────

def _escribe_una_vez(sesion, ctx, nombre: str, entrada: dict, pid: int, cambia: dict):
    """confirmar no toca la base; ejecutar cambia `cambia` (diferencias esperadas en `_conteos`) y repetirlo con el
    mismo tool_use no vuelve a escribir."""
    db = sesion.app.state.db
    antes = _conteos(db, pid)
    tarjeta = _confirmar(sesion, ctx, nombre, entrada)
    assert isinstance(tarjeta, Confirmacion) and tarjeta.detalle
    assert _conteos(db, pid) == antes, f"{nombre}: confirmar escribió"
    r1 = _ejecutar(sesion, ctx, nombre, entrada)
    despues = _conteos(db, pid)
    assert {k: despues[k] - antes[k] for k in despues if despues[k] != antes[k]} == cambia, nombre
    r2 = _ejecutar(sesion, ctx, nombre, entrada)
    assert _conteos(db, pid) == despues, f"{nombre}: repetir el mismo tool_use duplicó"
    for r in (r1, r2):
        assert isinstance(r, Resultado) and r.resumen and r.personas
        sin_datos(_modelo(r), *(v for v in entrada.values() if isinstance(v, str) and v.isdigit() and len(v) > 6))
    return tarjeta, r1, r2


def test_nota_telefono_acercamiento_y_autorizacion_son_idempotentes(sesion):
    app, db = sesion.app, sesion.app.state.db
    pid = _rica(db)
    db.reuniones.insert_one({"_id": 77, "titulo": "Reunión inventada", "fecha": "2026-11-01", "creado_por_uid": 0})
    ctx = aa.contexto(app, sesion, tool_use_id="toolu_nota_1")
    tarjeta, r, _ = _escribe_una_vez(sesion, ctx, "agregar_nota", {"persona_id": pid, "texto": "Pidió volver el lunes",
                                                                   "reunion_id": 77}, pid, {"notas": 1, "auditoria": 1})
    assert tarjeta.titulo == f"Agregar una nota a EUSTAQUIA INVENTADA RICA (#{pid})"
    assert ("Nota", "Pidió volver el lunes") in tarjeta.detalle and ("Reunión", "Reunión inventada (2026-11-01) #77") \
        in tarjeta.detalle
    assert r.contenido["guardada"] and r.contenido["persona"]["id"] == pid and r.acciones == [{"tipo": "recargar"}]

    ctx = aa.contexto(app, sesion, tool_use_id="toolu_tel_1")
    tarjeta, r, _ = _escribe_una_vez(sesion, ctx, "agregar_telefono", {"persona_id": pid, "numero": "320 111 2233",
                                                                       "whatsapp": True}, pid,
                                     {"telefonos": 1, "auditoria": 1})
    assert ("Número", "3201112233") in tarjeta.detalle and ("WhatsApp", "Sí") in tarjeta.detalle
    assert "···2233" in [t["numero"] for t in r.contenido["telefonos"]]
    sin_datos(_modelo(r), "3201112233")

    ctx = aa.contexto(app, sesion, tool_use_id="toolu_ac_1")
    entrada = {"persona_id": pid, "canal": "llamada", "resultado": "volver_llamar", "telefono_indice": 0,
               "proximo": modelo.hoy_local().isoformat(), "proximo_franja": "tarde"}
    tarjeta, r, r2 = _escribe_una_vez(sesion, ctx, "registrar_acercamiento", entrada, pid,
                                      {"acercamientos": 1, "auditoria": 1})
    assert tarjeta.titulo == f"Registrar un acercamiento con EUSTAQUIA INVENTADA RICA (#{pid})"
    assert ("Resultado", "Pidió volver a llamar") in tarjeta.detalle and ("Número", "···0011") in tarjeta.detalle
    assert r.contenido["acercamiento_id"] == r2.contenido["acercamiento_id"]  # la respuesta guardada
    assert {"tipo": "insignias"} in r.acciones

    ctx = aa.contexto(app, sesion, tool_use_id="toolu_aut_1")
    entrada = {"persona_id": pid, "estado": "revocada", "nota": "Lo pidió por teléfono"}
    tarjeta, r, _ = _escribe_una_vez(sesion, ctx, "registrar_autorizacion", entrada, pid,
                                     {"autorizaciones": 1, "auditoria": 1})
    assert ("Autorización", "Sí autoriza → Revocada") in tarjeta.detalle and "revocatoria" in tarjeta.aviso
    assert r.contenido["consentimiento"] == "no" and set(r.contenido["persona"]) == {"id", "nombre", "consentimiento"}


def test_repetir_una_escritura_que_cambia_el_estado_devuelve_la_respuesta_guardada(sesion, como):
    """La primera ejecución deja a la persona en «no autorizó»; la repetición del mismo tool_use no debe fallar por
    eso (la API devuelve la respuesta guardada) ni escribir otra vez."""
    app, db = sesion.app, sesion.app.state.db
    pid = contactable(db, "TEOFILA INVENTADA REPETIDA", "3158889900")
    p = como("planillero")
    ctx = aa.contexto(app, p, tool_use_id="toolu_no_1")
    _escribe_una_vez(sesion, ctx, "registrar_autorizacion", {"persona_id": pid, "estado": "no",
                                                             "nota": "Lo dijo en la visita"}, pid,
                     {"autorizaciones": 1, "auditoria": 1})
    assert db.personas.find_one({"_id": pid})["consentimiento"] == "no"
    otra = contactable(db, "TEOFILO INVENTADO REPETIDO", "3159990011")
    ctx = aa.contexto(app, sesion, tool_use_id="toolu_no_2")
    _escribe_una_vez(sesion, ctx, "registrar_acercamiento", {"persona_id": otra, "canal": "llamada",
                                                             "telefono_indice": 0, "resultado": "no_contactar",
                                                             "alcance": "persona"}, otra,
                     {"acercamientos": 1, "autorizaciones": 1, "auditoria": 2})
    assert db.personas.find_one({"_id": otra})["consentimiento"] == "no"


def test_ejecutar_repite_las_comprobaciones_de_la_entrada(sesion):
    """Aunque la ejecución llegue sin tarjeta (o cambien los catálogos entre las dos), lo que el asistente no hace
    tampoco se hace al ejecutar: una etiqueta sensible no se registra ni para el administrador."""
    app, db = sesion.app, sesion.app.state.db
    lider = db.etiquetas.find_one({"nombre": "Líder comunitario"})["_id"]
    n = db.personas.count_documents({})
    e = _error_ejecutar(sesion, aa.contexto(app, sesion), "crear_persona", {"nombre": "Ana Inventada Etiquetada",
                                                                            "etiquetas": [lider], "forzar": True})
    assert e.codigo == "permiso" and db.personas.count_documents({}) == n


def test_crear_persona_con_parecidas_y_forzar(sesion):
    app, db = sesion.app, sesion.app.state.db
    pid = _rica(db)
    ctx = aa.contexto(app, sesion, tool_use_id="toolu_crear_1")
    entrada = {"nombre": "Eustaquia Inventada Rica", "telefonos": [TEL], "sexo": "F"}
    n = db.personas.count_documents({})
    tarjeta = _confirmar(sesion, ctx, "crear_persona", entrada)
    assert tarjeta.titulo == "Crear la ficha de EUSTAQUIA INVENTADA RICA" and ("Teléfonos", TEL) in tarjeta.detalle
    assert ("Sexo", "Mujer") in tarjeta.detalle and "parecidas" in tarjeta.aviso
    assert db.personas.count_documents({}) == n  # la tarjeta no crea nada
    r = _ejecutar(sesion, ctx, "crear_persona", entrada)
    assert r.contenido["creada"] is False and r.contenido["codigo"] == "parecidas"
    assert "forzar" in r.contenido["mensaje"]
    assert [f["id"] for f in r.contenido["parecidas"]] == [pid] and r.personas == {pid}
    assert r.contenido["parecidas"][0]["cedula_ult3"] == "···777" and "No se creó" in r.resumen
    sin_datos(_modelo(r))
    assert db.personas.count_documents({}) == n
    # Con forzar (otra persona, ya revisado): se crea una sola vez aunque se repita el mismo tool_use
    ctx = aa.contexto(app, sesion, tool_use_id="toolu_crear_2")
    entrada = {**entrada, "forzar": True, "cedula": "92.000.555", "lugar_id": db.lugares.find_one()["_id"]}
    tarjeta = _confirmar(sesion, ctx, "crear_persona", entrada)
    assert ("Documento", "CC 92000555") in tarjeta.detalle and "aunque haya" in tarjeta.aviso
    r1 = _ejecutar(sesion, ctx, "crear_persona", entrada)
    r2 = _ejecutar(sesion, ctx, "crear_persona", entrada)
    nuevo = r1.contenido["persona"]["id"]
    assert r1.contenido["creada"] and r2.contenido["persona"]["id"] == nuevo and r1.personas == {nuevo}
    assert db.personas.count_documents({}) == n + 1 and db.personas.find_one({"_id": nuevo})["cedula"] == "92000555"
    sin_datos(_modelo(r1), "92000555")


def test_crear_persona_reglas_del_planillero(sesion, como):
    app = sesion.app
    p = como("planillero")
    ctx = aa.contexto(app, p)
    for entrada in ({"nombre": "Menor Inventado De Prueba", "edad": 15},
                    {"nombre": "Menor Inventado De Prueba", "tipo_documento": "TI", "cedula": "1012345678"}):
        assert _error_confirmar(sesion, ctx, "crear_persona", entrada).codigo == "invalido"
    lider = app.state.db.etiquetas.find_one({"nombre": "Líder comunitario"})["_id"]
    e = _error_confirmar(sesion, ctx, "crear_persona", {"nombre": "Adulta Inventada Nueva", "etiquetas": [lider]})
    assert e.codigo == "permiso"
    assert _error_confirmar(sesion, ctx, "crear_persona", {"nombre": "Adulta Inventada Nueva",
                                                           "lugar_id": 999999}).codigo == "no_existe"
    app.state.db.reuniones.insert_one({"_id": 5, "titulo": "Ajena", "fecha": "2026-11-01", "creado_por_uid": 0})
    e = _error_confirmar(sesion, ctx, "crear_persona", {"nombre": "Adulta Inventada Nueva", "reunion_id": 5})
    assert e.codigo == "permiso" and e.estado == 403


def test_editar_persona_antes_y_despues_e_idempotencia(sesion):
    app, db = sesion.app, sesion.app.state.db
    pid = _rica(db)
    vivienda = db.etiquetas.find_one({"nombre": "Vivienda"})["_id"]
    empleo = db.etiquetas.find_one({"nombre": "Empleo"})["_id"]
    ctx = aa.contexto(app, sesion, tool_use_id="toolu_editar_1")
    entrada = {"persona_id": pid, "cambios": {"ocupacion": "Pescadora", "estrato": 2, "etiquetas_agregar": [empleo],
                                              "etiquetas_quitar": [vivienda]}}
    tarjeta, r, r2 = _escribe_una_vez(sesion, ctx, "editar_persona", entrada, pid, {"auditoria": 1})
    assert tarjeta.titulo == f"Editar la ficha de EUSTAQUIA INVENTADA RICA (#{pid})"
    assert ("Ocupación", "(vacío) → Pescadora") in tarjeta.detalle and ("Estrato", "(vacío) → 2") in tarjeta.detalle
    assert ("Necesidades e intereses", "+ Empleo") in tarjeta.detalle
    assert ("Necesidades e intereses", "− Vivienda") in tarjeta.detalle
    p = db.personas.find_one({"_id": pid})
    assert p["ocupacion"] == "Pescadora" and p["estrato"] == 2 and empleo in p["etiquetas"]
    assert vivienda not in p["etiquetas"] and db.etiquetas.find_one({"nombre": "Líder comunitario"})["_id"] in \
        p["etiquetas"]  # la sensible que el asistente no ve sigue ahí
    assert r.contenido["guardado"] and {c["campo"] for c in r.contenido["cambios"]} == {"ocupacion", "estrato",
                                                                                         "etiquetas"}
    assert r2.contenido.get("sin_cambios") is True
    # Completar no pisa lo que ya hay: lo dice la tarjeta y queda como alterno
    ctx = aa.contexto(app, sesion, tool_use_id="toolu_editar_2")
    tarjeta = _confirmar(sesion, ctx, "editar_persona", {"persona_id": pid, "cambios": {"ocupacion": "Agricultora"}})
    assert ("Ocupación", "Pescadora (se conserva; «Agricultora» queda como dato alterno)") in tarjeta.detalle
    # Reemplazar sí corrige; la cédula de antes no se repite completa en la tarjeta y el cambio exige motivo
    entrada = {"persona_id": pid, "modo": "reemplazar", "cambios": {"cedula": "91000778"}}
    assert _error_confirmar(sesion, ctx, "editar_persona", entrada).codigo == "invalido"
    tarjeta = _confirmar(sesion, ctx, "editar_persona", {**entrada, "motivo_cambio_cedula": "Error de digitación"})
    assert ("Cédula", "···777 → 91000778") in tarjeta.detalle and CEDULA not in json.dumps(tarjeta.para_interfaz())
    e = _error_confirmar(sesion, ctx, "editar_persona", {"persona_id": pid, "cambios": {"ocupacion": "pescadora"}})
    assert e.codigo == "sin_cambios"
    tarjeta = _confirmar(sesion, ctx, "editar_persona", {"persona_id": pid, "cambios": {"personas_hogar": 4}})
    assert ("Personas en el hogar", "(vacío) → 4") in tarjeta.detalle  # estaba vacío: sí hay cambio
    db.personas.update_one({"_id": pid}, {"$set": {"personas_hogar": 3}})
    e = _error_confirmar(sesion, ctx, "editar_persona", {"persona_id": pid, "cambios": {"personas_hogar": 4}})
    assert e.codigo == "sin_cambios" and "reemplazar" in e.mensaje


def test_editar_detecta_cambios_entre_la_tarjeta_y_la_aprobacion(sesion):
    app, db = sesion.app, sesion.app.state.db
    pid = _rica(db)
    ctx = aa.contexto(app, sesion, tool_use_id="toolu_cambiada")
    h = H["editar_persona"]
    args = h.validar({"persona_id": pid, "cambios": {"ocupacion": "Pescadora"}})
    aa.correr(sesion, h.confirmar, ctx, args)
    assert set(args.huellas) == {"ocupacion"} and re.fullmatch(r"[0-9a-f]{24}", args.huellas["ocupacion"])
    # Lo que guardaría el bucle para la aprobación conserva las huellas de la tarjeta (el modelo no las ve)
    guardado = h.validar(args.model_dump(mode="json"))
    db.personas.update_one({"_id": pid}, {"$set": {"ocupacion": "Agricultora"}})  # otra persona, entre tanto
    e = _error(sesion, h.ejecutar, ctx, guardado)
    assert e.codigo == "cambiada" and e.estado == 409 and e.detalle["campos"] == ["ocupacion"]
    assert e.detalle["valores_actuales"] == {"ocupacion": "Agricultora"}
    assert db.personas.find_one({"_id": pid})["ocupacion"] == "Agricultora"
    # Las huellas no dejan valores en la entrada guardada: ni la cédula de antes ni la dirección
    args = h.validar({"persona_id": pid, "modo": "reemplazar", "motivo_cambio_cedula": "Corrección inventada",
                      "cambios": {"cedula": "91000778", "direccion": "CALLE 51 # 1-1"}})
    aa.correr(sesion, h.confirmar, ctx, args)
    guardado = json.dumps(args.model_dump(mode="json"), ensure_ascii=False)
    assert set(args.huellas) == {"cedula", "direccion"} and CEDULA not in guardado and "48-21" not in guardado
    r = aa.correr(sesion, h.ejecutar, ctx, h.validar(json.loads(guardado)))
    assert r.contenido["guardado"] and db.personas.find_one({"_id": pid})["cedula"] == "91000778"
    # Repetir lo ya aplicado no es un conflicto (las huellas solo se miran en lo que todavía cambia)
    r = aa.correr(sesion, h.ejecutar, ctx, h.validar(json.loads(guardado)))
    assert r.contenido.get("sin_cambios") is True
    # Sin la base (si el bucle volviera a validar la entrada cruda) se compara con lo de ahora y completar no pisa
    r = _ejecutar(sesion, ctx, "editar_persona", {"persona_id": pid, "cambios": {"ocupacion": "Pescadora"}})
    assert r.contenido["guardado"] and db.personas.find_one({"_id": pid})["ocupacion"] == "Agricultora"
    assert any("alterno" in a for a in r.contenido["persona"]["avisos"])


def test_editar_compara_como_la_api(sesion):
    """Un número importado como 40.0 es el mismo 40 (no es un cambio); la cédula se valida con el tipo de documento
    de la ficha cuando la entrada no lo trae (un pasaporte lleva letras)."""
    app, db = sesion.app, sesion.app.state.db
    pid = persona(db, nombre="PETRONILA INVENTADA EXTRANJERA", tipo_documento="PA", edad=40.0, estrato=2)
    otra = persona(db, nombre="PETRONIO INVENTADO NACIONAL", tipo_documento="CC")
    ctx = aa.contexto(app, sesion)
    e = _error_confirmar(sesion, ctx, "editar_persona", {"persona_id": pid, "cambios": {"edad": 40, "estrato": 2}})
    assert e.codigo == "sin_cambios"
    tarjeta = _confirmar(sesion, ctx, "editar_persona", {"persona_id": pid, "cambios": {"cedula": "ab-12345"}})
    assert ("Cédula", "(vacío) → AB12345") in tarjeta.detalle
    e = _error_confirmar(sesion, ctx, "editar_persona", {"persona_id": otra, "cambios": {"cedula": "ab-12345"}})
    assert e.codigo == "invalido" and "solo lleva números" in e.mensaje  # sin perder las letras en silencio
    r = _ejecutar(sesion, ctx, "editar_persona", {"persona_id": pid, "cambios": {"cedula": "ab-12345"}})
    assert r.contenido["guardado"] and db.personas.find_one({"_id": pid})["cedula"] == "AB12345"


def test_editar_reglas_del_planillero(sesion, como):
    app, db = sesion.app, sesion.app.state.db
    pid = _rica(db)
    p = como("planillero")
    ctx = aa.contexto(app, p)
    e = _error_confirmar(sesion, ctx, "editar_persona", {"persona_id": pid, "modo": "reemplazar",
                                                         "cambios": {"cedula": "91000999"},
                                                         "motivo_cambio_cedula": "Corrección"})
    assert e.codigo == "permiso" and e.detalle == {"campo": "cedula"}
    # Dictar la misma cédula no es cambiarla: no hay permiso que pedir, solo nada que guardar
    e = _error_confirmar(sesion, ctx, "editar_persona", {"persona_id": pid, "cambios": {"cedula": CEDULA}})
    assert e.codigo == "sin_cambios"
    r = _ejecutar(sesion, ctx, "editar_persona", {"persona_id": pid, "cambios": {"nivel_educativo": "Secundaria"}})
    assert r.contenido["guardado"] and db.personas.find_one({"_id": pid})["nivel_educativo"] == "Secundaria"
    sin_datos(_modelo(r))


def test_ubicar_persona_en_lugar_punto_o_automatica(sesion):
    app, db = sesion.app, sesion.app.state.db
    pid = _rica(db)
    lugar = db.lugares.find_one({}, sort=[("_id", -1)])
    ctx = aa.contexto(app, sesion, tool_use_id="toolu_ubicar_1")
    tarjeta, r, _ = _escribe_una_vez(sesion, ctx, "ubicar_persona", {"persona_id": pid, "lugar_id": lugar["_id"]},
                                     pid, {"auditoria": 1})
    assert tarjeta.titulo == f"Ubicar a EUSTAQUIA INVENTADA RICA (#{pid})"
    assert ("Barrio o vereda", f"(sin barrio ni vereda) → {lugar['nombre']} ({lugar['tipo']})") in tarjeta.detalle
    assert db.personas.find_one({"_id": pid})["lugar_id"] == lugar["_id"] and r.contenido["persona"]["lugar_nombre"]
    e = _error_confirmar(sesion, ctx, "ubicar_persona", {"persona_id": pid, "lugar_id": lugar["_id"]})
    assert e.codigo == "sin_cambios"
    ctx = aa.contexto(app, sesion, tool_use_id="toolu_ubicar_2")
    tarjeta, r, _ = _escribe_una_vez(sesion, ctx, "ubicar_persona", {"persona_id": pid, "lat": 7.01, "lon": -73.92},
                                     pid, {"auditoria": 1})
    assert ("Punto en el mapa", "7.010000, -73.920000") in tarjeta.detalle
    p = db.personas.find_one({"_id": pid})
    assert (p["lat"], p["lon"], p["geo_manual"]) == (7.01, -73.92, "punto")
    sin_datos(_modelo(r), "7.01", "-73.92")
    ctx = aa.contexto(app, sesion, tool_use_id="toolu_ubicar_3")
    _escribe_una_vez(sesion, ctx, "ubicar_persona", {"persona_id": pid, "automatica": True}, pid, {"auditoria": 1})
    assert not db.personas.find_one({"_id": pid})["geo_manual"]
    # Si otra persona cambia el barrio entre la tarjeta y la aprobación, no se pisa
    otro, tercero = [x["_id"] for x in db.lugares.find({"_id": {"$ne": lugar["_id"]}}, {"_id": 1}).limit(2)]
    h = H["ubicar_persona"]
    args = h.validar({"persona_id": pid, "lugar_id": otro})
    aa.correr(sesion, h.confirmar, ctx, args)
    db.personas.update_one({"_id": pid}, {"$set": {"lugar_id": tercero}})
    e = _error(sesion, h.ejecutar, ctx, h.validar(args.model_dump(mode="json")))
    assert e.codigo == "cambiada" and e.detalle["campos"] == ["lugar_id"]
    assert db.personas.find_one({"_id": pid})["lugar_id"] == tercero


def test_autorizacion_reglas_por_rol(sesion, como):
    app, db = sesion.app, sesion.app.state.db
    pid = persona(db, nombre="TEODOSIA INVENTADA PENDIENTE", telefono="3156667788")
    p, c = como("planillero"), como("consultor")
    ctx = aa.contexto(app, p)
    n = db.autorizaciones.count_documents({})
    e = _error_confirmar(sesion, ctx, "registrar_autorizacion", {"persona_id": pid, "estado": "si",
                                                                 "medio": "escrito", "canales": ["llamada"]})
    assert e.codigo == "invalido" and "evidencia" in e.mensaje and "mayor" in e.mensaje
    assert _error_confirmar(sesion, ctx, "registrar_autorizacion", {"persona_id": pid,
                                                                    "estado": "pendiente"}).codigo == "permiso"
    e = _error_confirmar(sesion, ctx, "registrar_autorizacion", {
        "persona_id": pid, "estado": "si", "medio": "verbal_telefono", "canales": ["llamada"], "evidencia": "Llamada",
        "mayor_declarado": True})
    assert e.codigo == "invalido" and "escrito" in e.mensaje  # el medio del consultor no es del planillero
    assert db.autorizaciones.count_documents({}) == n
    cid = contactable(db, "TEODORO INVENTADO CONSULTADO", "3157778899")
    tomar(c, cid)
    ctx = aa.contexto(app, c)
    entrada = {"persona_id": cid, "estado": "si", "medio": "verbal_telefono", "canales": ["llamada", "whatsapp"],
               "evidencia": "Llamada del 7 de noviembre", "mayor_declarado": True}
    tarjeta = _confirmar(sesion, ctx, "registrar_autorizacion", entrada)
    assert ("Canales", "Llamada, WhatsApp") in tarjeta.detalle and ("Declara ser mayor de 18 años", "Sí") \
        in tarjeta.detalle and "Ley 1581" in tarjeta.aviso
    r = _ejecutar(sesion, ctx, "registrar_autorizacion", entrada)
    assert r.contenido["registrada"] and db.autorizaciones.count_documents({"persona_id": cid}) == 1


def test_errores_de_la_api_llegan_limpios_al_modelo(sesion):
    app, db = sesion.app, sesion.app.state.db
    pid = _rica(db)
    otra = persona(db, nombre="OTRA PERSONA INVENTADA", cedula="93000444")
    ctx = aa.contexto(app, sesion)
    # La cédula de otra ficha: el 409 de la API trae su nombre y su lugar; al modelo solo le llega el id
    e = _error_ejecutar(sesion, ctx, "editar_persona", {"persona_id": otra, "modo": "reemplazar",
                                                        "cambios": {"cedula": CEDULA},
                                                        "motivo_cambio_cedula": "Prueba inventada"})
    assert e.codigo == "cedula_ocupada" and e.detalle == {"id": pid} and "EUSTAQUIA" not in e.para_modelo()
    assert CEDULA not in e.para_modelo()
    assert _error_ejecutar(sesion, ctx, "ver_persona", {"persona_id": 987654}).codigo == "no_existe"
    db.personas.update_one({"_id": otra}, {"$set": {"fusionada_en": pid}})
    e = _error_ejecutar(sesion, ctx, "ver_persona", {"persona_id": otra})
    assert e.codigo == "unida" and e.detalle == {"id": pid} and f"#{pid}" in e.mensaje
    # Un 409 «cambiada» de verdad (la base no coincide): para A trae la cédula completa; al modelo, enmascarada
    e = _error(sesion, functools.partial(hp._pedir, ctx, "PATCH", f"/api/personas/{pid}", cuerpo={
        "ocupacion": "Pesca", "base": {"ocupacion": "Otra", "cedula": "11111111"}}))
    assert e.codigo == "cambiada" and e.estado == 409 and set(e.detalle["campos"]) == {"ocupacion", "cedula"}
    assert e.detalle["valores_actuales"] == {"ocupacion": None, "cedula": "···777"} and CEDULA not in e.para_modelo()
    # Lo que trae un 409 «cambiada» o de parecidas, sin datos completos
    crudo = ErrorHerramienta("x", "cambiada", estado=409, detalle={
        "campos": ["cedula", "telefono", "correo", "ocupacion"],
        "valores_actuales": {"cedula": CEDULA, "telefono": TEL, "correo": CORREO, "ocupacion": f"Pesca {TEL}"}})
    limpio = hp._seguro(crudo)
    assert limpio.detalle["valores_actuales"] == {"cedula": "···777", "telefono": "···0011", "correo": "(oculto)",
                                                  "ocupacion": "Pesca ···011"}
    assert not any(v in limpio.para_modelo() for v in (CEDULA, TEL, CORREO))
    limpio = hp._seguro(ErrorHerramienta("Ya hay personas parecidas", "parecidas", estado=409,
                                         detalle={"parecidas": [{"id": 1, "cedula": CEDULA, "telefono": TEL}]}))
    assert limpio.detalle == {"n": 1}
    fatal = hp._seguro(ErrorHerramienta("tope", "volumen", estado=429, fatal=True))
    assert fatal.fatal and fatal.codigo == "volumen"


# ───────────────────────────── Por el bucle de verdad ─────────────────────────────

def test_de_punta_a_punta_por_el_bucle(sesion):
    """Con el bucle del núcleo y la Messages API simulada: lo que vuelve al modelo va minimizado, la escritura espera
    la tarjeta, se ejecuta una vez al aprobarla y la conversación recuerda a la persona (supresión)."""
    if not hasattr(aa, "encender"):
        pytest.skip("el núcleo del asistente todavía no está")
    db = sesion.app.state.db
    pid = _rica(db)
    api = aa.encender(sesion.app,
                      aa.sse(aa.TU("toolu_v", "ver_persona", {"persona_id": pid}), stop="tool_use"),
                      aa.sse(aa.TU("toolu_e", "editar_persona", {"persona_id": pid,
                                                                 "cambios": {"ocupacion": "Pescadora"}}),
                             stop="tool_use"))
    r, ev = aa.enviar(sesion, "Ponga que Eustaquia es pescadora")
    assert r.status_code == 200, r.text
    resultado = api.peticiones[1]["json"]["messages"][-1]["content"][0]
    assert resultado["tool_use_id"] == "toolu_v" and not resultado.get("is_error"), resultado
    ficha = json.loads(resultado["content"])
    assert ficha["id"] == pid and ficha["cedula_ult3"] == "···777"
    sin_datos(ficha)
    conf = next(e for e in ev if e["tipo"] == "confirmar")
    assert conf["titulo"] == f"Editar la ficha de EUSTAQUIA INVENTADA RICA (#{pid})"
    assert ["Ocupación", "(vacío) → Pescadora"] in conf["detalle"] and ev[-1]["motivo"] == "confirmacion"
    assert db.personas.find_one({"_id": pid}).get("ocupacion") is None  # nada se escribe sin aprobar
    cid = ev[0]["conversacion"]
    api.agregar(aa.sse(aa.T("Listo: quedó como pescadora.")))
    r, ev = aa.decidir(sesion, cid, toolu_e=True)
    assert r.status_code == 200 and ev[-1]["motivo"] == "listo", r.text
    assert db.personas.find_one({"_id": pid})["ocupacion"] == "Pescadora"
    assert db.auditoria.count_documents({"accion": "editar", "entidad_id": pid}) == 1
    resultado = api.peticiones[2]["json"]["messages"][-1]["content"][0]
    assert resultado["tool_use_id"] == "toolu_e" and json.loads(resultado["content"])["guardado"] is True
    assert pid in db.agente_conversaciones.find_one({"_id": cid})["personas"]


# ───────────────────────────── Entradas raras ─────────────────────────────

@pytest.mark.parametrize("nombre, entrada", [
    ("ver_persona", None), ("ver_persona", []), ("ver_persona", "12"), ("ver_persona", {}),
    ("ver_persona", {"persona_id": True}), ("ver_persona", {"persona_id": 0}), ("ver_persona", {"persona_id": "doce"}),
    ("ver_persona", {"persona_id": 1.5}), ("ver_persona", {"persona_id": 3, "id": 3}),
    ("buscar_personas", {"q": "x" * 121}), ("buscar_personas", {"filtro": {"zona": "urbana"}}),
    ("buscar_personas", {"por_pagina": 5}), ("buscar_personas", {"por_pagina": 200}),
    ("buscar_personas", {"pagina": 0}),
    ("buscar_personas", {"orden": "edad"}), ("buscar_personas", {"filtros": {"zona": "marte"}}),
    ("buscar_personas", {"filtros": {"lider": 1}}), ("buscar_personas", {"filtros": {"lista": "Lista A"}}),
    ("buscar_personas", {"filtros": {"poligono": "1,2;3,4;5,6"}}), ("buscar_personas", {"filtros": {"ids": "1,2"}}),
    ("buscar_personas", {"filtros": {"fuente": "cedulas"}}), ("buscar_personas", {"filtros": {"edad_min": 200}}),
    ("buscar_personas", {"filtros": {"edad_min": 60, "edad_max": 20}}),
    ("buscar_personas", {"filtros": {"faltan": ["nada"]}}), ("buscar_personas", {"filtros": {"etiqueta": True}}),
    ("buscar_personas", {"filtros": {"regimen_salud": "Subsidiado"}}),
    ("personas_parecidas", {}), ("personas_parecidas", {"persona_id": 3, "nombre": "Ana Inventada"}),
    ("personas_parecidas", {"nombre": "a b"}),
    ("crear_persona", {}), ("crear_persona", {"nombre": "ab"}), ("crear_persona", {"nombre": "123 456"}),
    ("crear_persona", {"nombre": "Ana Inventada", "cedula": "abc"}),
    ("crear_persona", {"nombre": "Ana Inventada", "cedula": "CC 71234567"}),
    ("editar_persona", {"persona_id": 3, "cambios": {"cedula": "12"}}),
    ("editar_persona", {"persona_id": 3, "cambios": {"cedula": "71234567; DROP"}}),
    ("crear_persona", {"nombre": "Ana Inventada", "tipo_documento": "CC"}),
    ("crear_persona", {"nombre": "Ana Inventada", "telefonos": ["123"]}),
    ("crear_persona", {"nombre": "Ana Inventada", "telefonos": ["3001112233 3004445566"]}),
    ("crear_persona", {"nombre": "Ana Inventada", "fecha_nacimiento": "1990-02-30"}),
    ("crear_persona", {"nombre": "Ana Inventada", "fecha_nacimiento": "2999-01-01"}),
    ("crear_persona", {"nombre": "Ana Inventada", "fecha_nacimiento": "14/03/1986"}),
    ("crear_persona", {"nombre": "Ana Inventada", "correo": "ana@correo.co"}),
    ("crear_persona", {"nombre": "Ana Inventada", "sexo": "X"}), ("crear_persona", {"nombre": "Ana Inventada",
                                                                                   "edad": 130}),
    ("editar_persona", {"persona_id": 3, "cambios": {}}),
    ("editar_persona", {"persona_id": 3, "cambios": {"sensibles": {"etnia": "Raizal"}}}),
    ("editar_persona", {"persona_id": 3, "cambios": {"lider": True}}),
    ("editar_persona", {"persona_id": 3, "cambios": {"consentimiento": "si"}}),
    ("editar_persona", {"persona_id": 3, "cambios": {"telefono": "3001112233"}}),
    ("editar_persona", {"persona_id": 3, "cambios": {"ocupacion": ""}}),
    ("editar_persona", {"persona_id": 3, "cambios": {"estado_civil": "Casado"}}),
    ("editar_persona", {"persona_id": 3, "cambios": {"puesto_id": 2, "puesto_texto": "Escuela"}}),
    ("editar_persona", {"persona_id": 3, "cambios": {"etiquetas_agregar": [2], "etiquetas_quitar": [2]}}),
    ("editar_persona", {"persona_id": 3, "cambios": {"municipio": "Puerto Berrío", "donde": "yondo"}}),
    ("editar_persona", {"persona_id": 3, "modo": "pisar", "cambios": {"ocupacion": "Pesca"}}),
    ("editar_persona", {"persona_id": 3, "cambios": {"ocupacion": "Pesca"}, "base": {"ocupacion": "x"}}),
    ("editar_persona", {"persona_id": 3, "cambios": {"ocupacion": "Pesca"}, "huellas": {"ocupacion": "zz"}}),
    ("editar_persona", {"persona_id": 3, "cambios": {"ocupacion": "Pesca"}, "huellas": {"listas": "a" * 24}}),
    ("agregar_nota", {"persona_id": 3, "texto": ""}), ("agregar_nota", {"persona_id": 3, "texto": "x" * 2001}),
    ("registrar_acercamiento", {"persona_id": 3, "canal": "llamada", "resultado": "contesto"}),
    ("registrar_acercamiento", {"persona_id": 3, "canal": "paloma", "resultado": "contesto"}),
    ("registrar_acercamiento", {"persona_id": 3, "canal": "visita", "resultado": "votara"}),
    ("registrar_acercamiento", {"persona_id": 3, "canal": "visita", "resultado": "no_contactar"}),
    ("registrar_acercamiento", {"persona_id": 3, "canal": "visita", "resultado": "contesto", "alcance": "persona"}),
    ("registrar_acercamiento", {"persona_id": 3, "canal": "visita", "resultado": "contesto",
                                "proximo": "2099-01-01"}),
    ("registrar_acercamiento", {"persona_id": 3, "canal": "visita", "resultado": "volver_llamar",
                                "proximo": "2000-01-01"}),
    ("registrar_acercamiento", {"persona_id": 3, "canal": "visita", "resultado": "numero_equivocado"}),
    ("registrar_acercamiento", {"persona_id": 3, "canal": "llamada", "resultado": "contesto", "telefono_indice": -1}),
    ("registrar_autorizacion", {"persona_id": 3, "estado": "talvez"}),
    ("registrar_autorizacion", {"persona_id": 3, "estado": "no", "canales": ["llamada"]}),
    ("registrar_autorizacion", {"persona_id": 3, "estado": "si", "medio": "panel"}),
    ("registrar_autorizacion", {"persona_id": 3, "estado": "si", "canales": ["telepatia"]}),
    ("registrar_autorizacion", {"persona_id": 3, "estado": "si", "sensibles": ["etnia"]}),
    ("ubicar_persona", {"persona_id": 3}), ("ubicar_persona", {"persona_id": 3, "lat": 7.0}),
    ("ubicar_persona", {"persona_id": 3, "lugar_id": 4, "lat": 7.0, "lon": -73.9}),
    ("ubicar_persona", {"persona_id": 3, "lat": 4.6, "lon": -74.1}),
    ("ubicar_persona", {"persona_id": 3, "lat": float("nan"), "lon": -73.9}),
    ("ubicar_persona", {"persona_id": 3, "automatica": True, "huellas": {"cedula": "a" * 24}}),
    ("agregar_telefono", {"persona_id": 3, "numero": "12345"}),
    ("agregar_telefono", {"persona_id": 3, "numero": "1111111111"}),
    ("agregar_telefono", {"persona_id": 3, "numero": "3001112233", "confirmado": True}),
])
def test_entradas_raras_no_validan(nombre, entrada):
    with pytest.raises(ValidationError):
        H[nombre].validar(entrada)


def test_entradas_validas_se_normalizan():
    a = H["buscar_personas"].validar({"q": "  zoila  ", "filtros": {"faltan": ["cedula", "cedula", "puesto_mesa"],
                                                                     "tratables": True, "con_cedula": False,
                                                                     "motivo_actualizacion": "direccion",
                                                                     "requiere_actualizacion": True}})
    assert a.q == "zoila"
    assert hp.params_filtros(a.filtros) == {"tratables": 1, "con_cedula": 0, "sin_cedula": 1, "sin_puesto_mesa": 1,
                                            "requiere_actualizacion": "direccion"}
    assert hp._busca_lista(a) and not hp._busca_lista(H["buscar_personas"].validar({"q": "zoila"}))
    c = H["crear_persona"].validar({"nombre": "Ana Inventada", "cedula": "71.234.567", "telefonos": ["+57 300 111 2233",
                                                                                                   "3001112233"]})
    assert c.cedula == "71234567" and c.telefonos == ["3001112233"]
    assert H["agregar_telefono"].validar({"persona_id": "3", "numero": "(604) 700 1234"}).numero == "6047001234"
    assert H["crear_persona"].validar({"nombre": "Ana Inventada", "tipo_documento": "PA",
                                       "cedula": "ab-12345"}).cedula == "AB12345"
    e = H["editar_persona"].validar({"persona_id": 3, "cambios": {"jefe_hogar": False}})
    assert hp.cambios_de(e.cambios) == {"jefe_hogar": False}


def test_clave_de_idempotencia():
    ctx = SimpleNamespace(conversacion_id=12, tool_use_id="toolu_01AbC")
    assert hp._clave(ctx) == "agente.12.toolu_01AbC"
    assert hp._clave(SimpleNamespace(conversacion_id=12, tool_use_id="")) is None  # sin tool_use: sin clave
    rara = hp._clave(SimpleNamespace(conversacion_id=7, tool_use_id="toolu/ñ?" + "x" * 200))
    assert re.fullmatch(r"[A-Za-z0-9_.:-]{8,100}", rara)


# ───────────────────────────── minimizar ─────────────────────────────

def test_minimizar_filas_de_cada_rol_sin_agregar_nada():
    fila_a = {"id": 4, "nombre": "ANA INVENTADA", "cedula": CEDULA, "telefono": TEL, "lider": True,
              "fuentes": ["cedulas"], "consentimiento": "si", "menor": False, "lugar": "EL PRADO",
              "abordaje": {"estado": "contactado", "n": 2, "ultimo_uid": 9, "ultimo_usuario": "consultor9"},
              "requiere_actualizacion": {"motivo": "direccion", "nota": f"Llamar al {TEL}", "usuario": "admin"},
              "situacion": {"estado": "activa", "reportado_por": {"uid": 3}}}
    f = minimizar.fila(fila_a)
    assert f == {"id": 4, "nombre": "ANA INVENTADA", "consentimiento": "si", "menor": False, "lugar": "EL PRADO",
                 "cedula_ult3": "···777", "telefono_mascara": "···0011",
                 "abordaje": {"estado": "contactado", "n": 2}, "requiere_actualizacion": {"motivo": "direccion"},
                 "situacion": {"estado": "activa"}}
    assert minimizar.fila({**fila_a, "menor": True})["telefono_mascara"] is None
    # La del consultor no gana campos (no trae cédula ni teléfono: no hay qué enmascarar)
    fila_c = {"id": 4, "nombre": "ANA INVENTADA", "lugar": None, "abordaje_estado": "sin_abordar", "contactable": True}
    assert minimizar.fila(fila_c) == fila_c
    # La de la cola: el índice y los canales, sin el número
    cola = {"id": 4, "nombre": "ANA", "telefono_indice": 0, "telefono": TEL, "whatsapp": True,
            "canales_permitidos": ["llamada"], "consentimiento": "si"}
    assert minimizar.fila(cola) == {"id": 4, "nombre": "ANA", "telefono_indice": 0, "whatsapp": True,
                                    "canales_permitidos": ["llamada"], "consentimiento": "si",
                                    "telefono_mascara": "···0011"}
    # Las filas del administrador traen `lugar_tipo`: de quien no autorizó va su barrio o vereda (sin él, ningún lugar)
    assert minimizar.fila({**fila_a, "consentimiento": "no", "lugar_tipo": "barrio"}) == {
        "id": 4, "nombre": "ANA INVENTADA", "lugar": "EL PRADO", "consentimiento": "no",
        "aviso": minimizar.AVISO_NO_AUTORIZO}
    assert minimizar.filas([fila_c, None, "x"]) == [fila_c] and minimizar.ids_de([fila_c, {"id": True}]) == {4}
    # Sin `Sensibles` la ficha sale sin etiquetas ni campos propios (ante la duda, no se manda)
    d = minimizar.ficha({"id": 4, "nombre": "ANA", "etiquetas": [{"id": 1, "nombre": "JAC"}], "extra": {"x": "y"}})
    assert d == {"id": 4, "nombre": "ANA"}
    assert minimizar.ficha(None) == {} and minimizar.fila([]) == {}


def test_minimizar_textos_libres():
    t = minimizar.texto_libre(f"Llamar al {TEL} o al 300 999 0011; cédula 71.234.000 y {CEDULA}; el 2026-11-07 o "
                              f"07/11/2026; correo {CORREO}; calle 50 # 48-21")
    assert TEL not in t and "300 999 0011" not in t and "71.234.000" not in t and CEDULA not in t and CORREO not in t
    assert "2026-11-07" in t and "07/11/2026" in t and "calle 50 # 48-21" in t and "[correo]" in t
    assert minimizar.texto_libre("x" * 400).endswith("…") and len(minimizar.texto_libre("x" * 400)) == 301
    assert minimizar.texto_libre(None) is None and minimizar.texto_libre(5) == 5
