"""Herramientas de gestión del asistente (`app/agente/herramientas/gestion.py`): qué se le ofrece a cada rol (A, K, P,
C), indicadores compactos sin listas, datos sensibles ni actividad, reuniones (listar, ver con asistentes minimizados,
crear y registrar asistentes: la tarjeta no escribe, aprobar escribe una sola vez), pendientes, mi trabajo (la cola sin
números), el equipo (sin sesiones ni teléfonos), el nomenclátor de lugares (homónimos y sugerencias), los catálogos
por rol, filtros fuera de la lista blanca y esquemas válidos para la Messages API.

Las herramientas corren en el bucle de la aplicación (`ayudas_agente.correr`) y llaman a la API de verdad por ASGI con
la sesión de cada rol. Solo datos inventados; nunca se llama a Anthropic ni a Mnemo."""
from __future__ import annotations

import json
import re
from datetime import timedelta

import pytest
from pydantic import ValidationError

import ayudas_agente as aa
from ayudas_g3 import autorizada, contactable, coordinador, persona, recorrer
from conftest import CASCO
from app import db as bd
from app import modelo
from app.agente import herramientas
from app.agente.herramientas import gestion as hg
from app.agente.herramientas import interfaz as hi
from app.agente.herramientas.base import Confirmacion, ErrorHerramienta, Resultado

H = {h.nombre: h for h in hg.HERRAMIENTAS + hi.HERRAMIENTAS}
MIAS = set(H)
LECTURAS = {"indicadores", "listar_reuniones", "ver_reunion", "pendientes", "mi_trabajo", "equipo", "buscar_lugar",
            "catalogos"}
ESCRITURAS = {"crear_reunion", "agregar_asistente"}
DEL_ROL = {
    "admin": MIAS, "coordinador": MIAS,
    "planillero": {"listar_reuniones", "ver_reunion", "crear_reunion", "agregar_asistente", "pendientes", "mi_trabajo",
                   "buscar_lugar", "catalogos", "abrir_vista"},
    "consultor": {"pendientes", "mi_trabajo", "buscar_lugar", "catalogos", "abrir_vista"},
}

# Lo que nunca llega al modelo, venga de donde venga
CLAVES_VEDADAS = {"sensibles", "listas", "lista", "lider", "lideres", "en_ambas_bases", "fuentes", "actividad",
                  "demografia", "origen", "regimen_salud", "cedula", "telefono", "telefono2", "correo", "lat", "lon",
                  "punto", "puntos", "sesiones", "ip", "clave_temporal", "intentos_recientes", "hash"}
CEDULA, TEL, TEL2, CORREO = "93000777", "3009990022", "3104445577", "crescencia@correo.co"
LAT_RICA, LON_RICA = 7.006321, -73.911432
VALORES_VEDADOS = (CEDULA, TEL, TEL2, CORREO, "Lista Inventada B3", "Raizal", "Subsidiado", "partido inventado",
                   str(LAT_RICA), str(LON_RICA), "Líder comunitario", "Discapacidad")
LON, LAT = CASCO
CUADRO = [[LON - 0.004, LAT - 0.004], [LON + 0.004, LAT - 0.004], [LON + 0.004, LAT + 0.004],
          [LON - 0.004, LAT + 0.004]]


# ───────────────────────────── Ayudas ─────────────────────────────

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


def _ej(cliente, ctx, nombre: str, entrada: dict) -> Resultado:
    return aa.correr(cliente, aa.ejecutar, H[nombre], ctx, entrada)


def _conf(cliente, ctx, nombre: str, entrada: dict) -> Confirmacion:
    return aa.correr(cliente, aa.confirmar, H[nombre], ctx, entrada)


def _falla(cliente, fn, *args) -> ErrorHerramienta:
    with pytest.raises(ErrorHerramienta) as e:
        aa.correr(cliente, fn, *args)
    return e.value


def _falla_ej(cliente, ctx, nombre, entrada) -> ErrorHerramienta:
    return _falla(cliente, aa.ejecutar, H[nombre], ctx, entrada)


def _falla_conf(cliente, ctx, nombre, entrada) -> ErrorHerramienta:
    return _falla(cliente, aa.confirmar, H[nombre], ctx, entrada)


def _modelo(r: Resultado):
    """Lo que de verdad ve el modelo: el texto del tool_result."""
    return json.loads(r.texto_para_modelo())


def sin_datos(x, *otros: str) -> None:
    """Ninguna clave vedada en todo el JSON y ningún valor de la ficha rica (ni cédulas, teléfonos ni coordenadas)."""
    for ruta, k, _ in recorrer(x):
        assert k not in CLAVES_VEDADAS, (ruta, k)
    texto = json.dumps(x, ensure_ascii=False, default=str)
    for v in (*VALORES_VEDADOS, *otros):
        assert v not in texto, v


def _lugar(db, nombre: str, tipo: str) -> int:
    return db.lugares.find_one({"nombre": nombre, "tipo": tipo})["_id"]


def _etiqueta(db, nombre: str) -> int:
    return db.etiquetas.find_one({"nombre": nombre})["_id"]


def _rica(db, **extra) -> int:
    """Una ficha inventada con todo lo que el modelo no debe recibir: listas, líder, datos sensibles, la base con
    cédula, teléfonos, correo, coordenadas, régimen de salud y etiquetas sensibles (y una que no lo es)."""
    pid = persona(
        db, nombre="CRESCENCIA INVENTADA RICA", cedula=CEDULA, telefono=TEL, telefono2=TEL2, tipo_documento="CC",
        correo=CORREO, lider=True, listas=["Lista Inventada B3"], sensibles={"etnia": "Raizal"},
        fuentes=["tramites", "cedulas"], origen=[{"fuente": "cedulas", "datos": {"partido": "partido inventado"}}],
        telefonos=[{"numero": TEL, "tipo": "celular", "fuentes": ["cedulas"], "estado": "confirmado",
                    "no_contactar": False},
                   {"numero": TEL2, "tipo": "celular", "fuentes": ["tramites"], "estado": "confirmado",
                    "no_contactar": False}],
        lat=LAT_RICA, lon=LON_RICA, punto={"type": "Point", "coordinates": [LON_RICA, LAT_RICA]},
        geo_precision="direccion", direccion="CALLE 50 # 48-21", regimen_salud="Subsidiado",
        observaciones=f"Llamar al {TEL}", edad=40, zona="urbana", lugar_id=_lugar(db, "TRES DE OCTUBRE", "barrio"),
        etiquetas=[_etiqueta(db, "Líder comunitario"), _etiqueta(db, "Discapacidad"), _etiqueta(db, "Vivienda")],
        **extra)
    autorizada(db, pid)
    return pid


def _reunion(cli, titulo: str, fecha: str, **extra) -> int:
    r = cli.post("/api/reuniones", json={"titulo": titulo, "fecha": fecha, **extra})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _quienes(sesion, como):
    app, db = sesion.app, sesion.app.state.db
    k = coordinador(app, db)
    p, c = como("planillero"), como("consultor")
    return {"admin": (sesion, aa.quien_de(app, 0)), "coordinador": (k, aa.quien_de(app, k.uid)),
            "planillero": (p, aa.quien_de(app, p.uid)), "consultor": (c, aa.quien_de(app, c.uid))}


# ───────────────────────────── Catálogo y esquemas ─────────────────────────────

def test_cada_rol_recibe_solo_las_herramientas_de_sus_permisos(sesion, como):
    cfg = sesion.app.state.cfg
    for rol, (_, quien) in _quienes(sesion, como).items():
        nombres = [h.nombre for h in herramientas.para(quien, {"escritura": True}, cfg)]
        assert set(nombres) & MIAS == DEL_ROL[rol], rol
        assert len(nombres) == len(set(nombres)), rol
        # Sin escritura en Ajustes no se ofrecen crear_reunion ni agregar_asistente
        sin = {h.nombre for h in herramientas.para(quien, {"escritura": False}, cfg)} & MIAS
        assert sin == DEL_ROL[rol] - ESCRITURAS, rol
    # El orden fijo: después de las de personas, primero las de gestión y al final las de interfaz
    fijas = [h.nombre for h in herramientas.fijas()]
    assert fijas[-len(MIAS):] == [h.nombre for h in hg.HERRAMIENTAS + hi.HERRAMIENTAS]


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
    assert len(H) == 12
    for h in hg.HERRAMIENTAS + hi.HERRAMIENTAS:
        d = h.definicion()
        assert set(d) == {"name", "description", "input_schema", "eager_input_streaming"}, h.nombre
        assert re.fullmatch(r"[a-z_]{3,64}", d["name"]) and d["eager_input_streaming"] is True
        assert 200 < len(d["description"]) < 1500, h.nombre
        assert re.match(r"^\w+(ando|endo|iendo)\b", h.etiqueta), h.etiqueta  # en gerundio
        s = d["input_schema"]
        texto = json.dumps(s, ensure_ascii=False)
        assert "$ref" not in texto and "$defs" not in texto and '"title"' not in texto and "\\n" not in texto
        assert s["type"] == "object" and isinstance(s["properties"], dict), h.nombre
        for obj in _objetos(s):  # todo objeto, también los anidados: cerrado y con sus obligatorias declaradas
            assert obj.get("additionalProperties") is False, h.nombre
            assert set(obj.get("required", [])) <= set(obj.get("properties", {})), h.nombre
        for ruta, k in _palabras(s):
            assert k in PALABRAS_ESQUEMA, (h.nombre, ruta, k)
        assert (h.tipo == "escritura") == (h.confirmar is not None) == (h.nombre in ESCRITURAS), h.nombre
        assert h.tipo == ("lectura" if h.nombre in LECTURAS else "escritura" if h.nombre in ESCRITURAS
                          else "interfaz"), h.nombre
    # Los filtros nunca ofrecen búsqueda por texto, listas, líderes, régimen de salud ni la base con cédula
    filtros = H["indicadores"].definicion()["input_schema"]["properties"]["filtros"]["properties"]
    assert not {"q", "lista", "lider", "regimen_salud", "ids", "poligono", "mios"} & set(filtros)
    assert "cedulas" not in filtros["fuente"]["enum"] and "ambas" not in filtros["fuente"]["enum"]


@pytest.mark.parametrize("filtros", [
    {"lista": "Lista A"}, {"lider": True}, {"q": "ana"}, {"q": "93000777"}, {"fuente": "cedulas"},
    {"fuente": "ambas"}, {"regimen_salud": "Subsidiado"}, {"ids": "1,2"}, {"poligono": "1,2;3,4;5,6"}, {"mios": True},
    {"zona": "marte"}, {"edad_min": 50, "edad_max": 20}, {"lugar": "La Paz", "lugar_id": 74}, {"tipo_lugar": "vereda"},
    {"sexo": "X"}, {"lugar_id": True}, {"estrato": 9}, {"faltan": ["dientes"]}, {"etiqueta": 0},
    {"requiere_actualizacion": True, "motivos_actualizacion": ["no_contesta"]}, {"sin_cedula": 1},
])
def test_filtros_fuera_de_la_lista_blanca_se_rechazan(filtros):
    with pytest.raises(ValidationError):
        H["indicadores"].validar({"filtros": filtros})


def test_filtros_se_traducen_a_los_parametros_de_la_api():
    f = hg.FiltrosBase.model_validate({"zona": "rural", "con_telefono": False, "tratables": True,
                                       "proximo_vencido": False, "faltan": ["cedula", "puesto_mesa", "cedula"],
                                       "motivos_actualizacion": ["no_contesta", "direccion"], "edad_min": 18})
    assert hg.params_de(f) == {"zona": "rural", "con_telefono": "0", "tratables": "1", "edad_min": "18",
                               "requiere_actualizacion": "no_contesta,direccion", "sin_cedula": "1",
                               "sin_puesto_mesa": "1"}
    assert hg.params_de(hg.FiltrosBase.model_validate({"requiere_actualizacion": False})) == {
        "requiere_actualizacion": "0"}
    assert hg.params_de(None) == {}


# ───────────────────────────── indicadores ─────────────────────────────

def test_indicadores_compactos_sin_listas_sensibles_ni_actividad(sesion, ctx_de):
    app, db = sesion.app, sesion.app.state.db
    db.meta.update_one({"_id": "ajustes"}, {"$set": {"sensibles_activos": True}}, upsert=True)
    _rica(db)
    vereda = _lugar(db, "LA PAZ", "vereda")
    for i in range(3):
        persona(db, nombre=f"PERSONA INVENTADA DE LA VEREDA {i}", zona="rural", lugar_id=vereda, sexo="F")
    _reunion(sesion, "Reunión inventada del tablero", "2026-11-01")  # deja actividad en la auditoría
    crudo = sesion.get("/api/indicadores").json()
    assert {"listas", "sensibles", "actividad", "fuentes", "demografia"} <= set(crudo)  # la API sí los trae
    assert crudo["actividad"] and crudo["listas"] and crudo["kpi"]["lideres"] == 1
    for cli in (sesion, coordinador(app, db)):
        r = _ej(sesion, ctx_de(cli), "indicadores", {})
        c = r.contenido
        assert c["kpi"]["personas"] == 4 and c["alcance"] == "tablero" and c["filtros"] == {}
        assert not {"lideres", "en_ambas_bases"} & set(c["kpi"])
        for clave in ("listas", "sensibles", "actividad", "fuentes", "demografia", "edades", "tramites_mes", "mesas"):
            assert clave not in c, clave
        necesidades = {x["nombre"] for x in c["necesidades"]}
        assert "Vivienda" in necesidades and not necesidades & set(bd.ETIQUETAS_SENSIBLES)
        assert all(x["campo"] != "regimen_salud" for x in c["completitud_campos"])
        assert c["reuniones_recientes"][0]["titulo"] == "Reunión inventada del tablero"
        assert {x["nombre"] for x in c["lugares"]} == {"LA PAZ", "TRES DE OCTUBRE"}
        assert r.personas == set() and r.resumen == "4 personas" and r.acciones == []
        sin_datos(_modelo(r))
    # Con filtros: el lugar por nombre se resuelve en el servidor (el homónimo, con la palabra «vereda»)
    r = _ej(sesion, ctx_de(sesion), "indicadores", {"filtros": {"lugar": "vereda La Paz", "sexo": "F"}})
    assert r.contenido["kpi"]["personas"] == 3
    assert r.contenido["filtros"] == {"lugar_id": f"LA PAZ (vereda #{vereda})", "sexo": "F"}


def test_indicadores_de_una_zona_con_pocas_personas(sesion, ctx_de):
    db = sesion.app.state.db
    aid = sesion.post("/api/areas", json={"nombre": "Zona inventada", "poligono": CUADRO}).json()["id"]
    persona(db, nombre="PERSONA INVENTADA EN LA ZONA", lat=LAT, lon=LON)
    ctx = ctx_de(sesion)
    r = _ej(sesion, ctx, "indicadores", {"filtros": {"area_id": aid}, "alcance": "zona"})
    assert r.contenido["pocas"] is True and r.contenido["kpi"] == {"personas": "<10"}
    assert r.contenido["area"]["m2"] > 0 and r.resumen == "Zona con menos de 10 personas"
    e = _falla_ej(sesion, ctx, "indicadores", {"filtros": {"area_id": 9999}, "alcance": "zona"})
    assert e.estado == 404


def test_indicadores_y_equipo_no_son_del_planillero_ni_del_consultor(sesion, como, ctx_de):
    for cli in (como("planillero"), como("consultor")):
        quien = aa.quien_de(sesion.app, cli.uid)
        assert not {h.nombre for h in herramientas.para(quien, {}, sesion.app.state.cfg)} & {"indicadores", "equipo"}
        for nombre in ("indicadores", "equipo"):  # si igual se llaman, la API dice 403
            e = _falla_ej(sesion, ctx_de(cli), nombre, {})
            assert (e.estado, e.codigo) == (403, "permiso"), nombre


def test_filtros_con_etiqueta_sensible_o_lugar_dudoso(sesion, ctx_de):
    db = sesion.app.state.db
    ctx = ctx_de(sesion)
    e = _falla_ej(sesion, ctx, "indicadores", {"filtros": {"etiqueta": _etiqueta(db, "Líder comunitario")}})
    assert (e.codigo, e.estado) == ("permiso", 403)
    e = _falla_ej(sesion, ctx, "indicadores", {"filtros": {"etiqueta": 99999}})
    assert e.codigo == "no_existe"
    e = _falla_ej(sesion, ctx, "indicadores", {"filtros": {"lugar": "La Paz"}})
    assert e.codigo == "ambiguo" and "No se hizo nada" in e.mensaje
    assert {x["id"] for x in e.detalle["candidatos"]} == {_lugar(db, "LA PAZ", "barrio"),
                                                          _lugar(db, "LA PAZ", "vereda")}
    e = _falla_ej(sesion, ctx, "indicadores", {"filtros": {"lugar": "Las Margaritas"}})
    assert e.codigo == "no_existe" and e.detalle["sugerencias"]
    e = _falla_ej(sesion, ctx, "indicadores", {"filtros": {"lugar_id": 99999}})
    assert e.codigo == "no_existe"
    # lugar_id 0 = «sin barrio ni vereda»: no se busca en el nomenclátor
    r = _ej(sesion, ctx, "indicadores", {"filtros": {"lugar_id": 0}})
    assert r.contenido["filtros"] == {"lugar_id": "0"}


# ───────────────────────────── Reuniones ─────────────────────────────

def test_listar_reuniones_por_rol_y_con_filtros(sesion, como, ctx_de):
    p = como("planillero")
    a1 = _reunion(sesion, "Reunión de vecinos del casco", "2026-10-01", tema="Vías")
    a2 = _reunion(sesion, "Jornada en la vereda", "2026-11-03", abierta_a_equipo=True)
    a3 = _reunion(sesion, "Reunión de la administración", "2026-11-05")
    propia = _reunion(p, "Visita del planillero", "2026-11-04")
    ctx = ctx_de(sesion)
    r = _ej(sesion, ctx, "listar_reuniones", {})
    assert [x["id"] for x in r.contenido["reuniones"]] == [a3, propia, a2, a1] and r.contenido["total"] == 4
    assert "ajenas" not in r.contenido and r.resumen == "4 reuniones"
    assert r.contenido["reuniones"][3] == {
        "id": a1, "titulo": "Reunión de vecinos del casco", "fecha": "2026-10-01", "hora": None, "tema": "Vías",
        "lugar": None, "asistentes": 0, "nuevos": 0, "abierta_a_equipo": False, "propia": True,
        "ruta": f"/reuniones/{a1}"}
    assert [x["id"] for x in _ej(sesion, ctx, "listar_reuniones", {"desde": "2026-11-01", "hasta": "2026-11-04"})
            .contenido["reuniones"]] == [propia, a2]
    assert [x["id"] for x in _ej(sesion, ctx, "listar_reuniones", {"q": "VEREDA"}).contenido["reuniones"]] == [a2]
    corta = _ej(sesion, ctx, "listar_reuniones", {"limite": 2}).contenido
    assert corta["mostradas"] == 2 and corta["total"] == 4 and "aviso" in corta
    # El planillero: las suyas y las abiertas al equipo; de las demás, solo cuántas son
    r = _ej(sesion, ctx_de(p), "listar_reuniones", {})
    assert {x["id"] for x in r.contenido["reuniones"]} == {propia, a2} and r.contenido["ajenas"] == 2
    assert [x["id"] for x in _ej(sesion, ctx_de(p), "listar_reuniones", {"solo_propias": True})
            .contenido["reuniones"]] == [propia]
    # El consultor no tiene reuniones: si igual llama, 403
    assert _falla_ej(sesion, ctx_de(como("consultor")), "listar_reuniones", {}).estado == 403
    for mala in ({"desde": "2026-13-01"}, {"desde": "2026-11-05", "hasta": "2026-11-01"}, {"limite": 0},
                 {"q": "x"}, {"pagina": 2}):
        with pytest.raises(ValidationError):
            H["listar_reuniones"].validar(mala)


def test_ver_reunion_con_asistentes_minimizados(sesion, como, ctx_de):
    db = sesion.app.state.db
    rica = _rica(db)
    no = persona(db, nombre="NICOLASA INVENTADA NO AUTORIZO", consentimiento="no", cedula="93000888",
                 telefono="3001231234")
    rid = _reunion(sesion, "Reunión con asistentes inventados", "2026-11-02", descripcion=f"Avisar al {TEL}",
                   compromisos="Arreglar la vía")
    for pid in (rica, no):
        r = sesion.post(f"/api/reuniones/{rid}/asistentes", json={"persona_id": pid, "rol": "Líder",
                                                                  "nota": f"Dio su número {TEL}"})
        assert r.status_code == 201, r.text
    ctx = ctx_de(sesion)
    r = _ej(sesion, ctx, "ver_reunion", {"reunion_id": rid})
    c = r.contenido
    assert c["asistentes_total"] == 2 and r.personas == {rica} and r.resumen == "2 asistentes"
    fila = next(f for f in c["asistentes"] if f["id"] == rica)
    assert fila["nombre"] == "CRESCENCIA INVENTADA RICA" and fila["cedula_ult3"] == "···777"
    # Quien no autorizó no se lista: que asistió a la reunión es un dato suyo
    assert [f["id"] for f in c["asistentes"]] == [rica] and "no se listan" in c["aviso"]
    assert c["descripcion"] == "Avisar al ···022" and c["compromisos"] == "Arreglar la vía"
    assert {x["nombre"] for x in c["necesidades"]} == {"Vivienda"}  # sin Discapacidad ni Líder comunitario
    sin_datos(_modelo(r), "93000888", "3001231234", "Líder")
    # Con asistentes=0: los datos básicos y los conteos, sin servir ni consultar a nadie
    r = _ej(sesion, ctx, "ver_reunion", {"reunion_id": rid, "asistentes": 0})
    assert r.contenido["asistentes"] == [] and r.contenido["asistentes_total"] == 2 and r.personas == set()
    assert r.contenido["titulo"] == "Reunión con asistentes inventados" and "descripcion" not in r.contenido
    assert _falla_ej(sesion, ctx, "ver_reunion", {"reunion_id": 9999}).codigo == "no_existe"
    assert _falla_ej(sesion, ctx, "ver_reunion", {"reunion_id": 9999, "asistentes": 0}).codigo == "no_existe"
    # El planillero no ve una reunión ajena cerrada: 403 de la API
    p = como("planillero")
    e = _falla_ej(sesion, ctx_de(p), "ver_reunion", {"reunion_id": rid})
    assert (e.estado, e.codigo) == (403, "permiso")
    # En una suya, el detalle registra como consultados a sus asistentes (su tope diario); los conteos, no
    suya = _reunion(p, "Reunión inventada del planillero", "2026-11-03")
    assert p.post(f"/api/reuniones/{suya}/asistentes", json={"persona_id": rica}).status_code == 201
    db.lecturas.delete_many({"uid": p.uid})
    r = _ej(sesion, ctx_de(p), "ver_reunion", {"reunion_id": suya, "asistentes": 0})
    assert r.contenido["asistentes_total"] == 1 and db.lecturas.count_documents({"uid": p.uid}) == 0
    r = _ej(sesion, ctx_de(p), "ver_reunion", {"reunion_id": suya})
    assert r.personas == {rica} and db.lecturas.count_documents({"uid": p.uid, "pid": rica}) == 1


def test_crear_reunion_la_tarjeta_no_escribe_y_aprobar_escribe_una_vez(sesion, como, ctx_de):
    db = sesion.app.state.db
    vereda = _lugar(db, "LA PAZ", "vereda")
    ctx = ctx_de(sesion, tool_use_id="toolu_reunion1")
    entrada = {"titulo": "Asamblea inventada de la vereda", "fecha": "2026-11-20", "hora": "9:30",
               "lugar": "vereda la paz", "sitio": "Escuela de la vereda", "tema": "Agua potable"}

    def conteo():
        return (db.reuniones.count_documents({}),
                db.auditoria.count_documents({"entidad": "reunion", "accion": "crear"}))

    antes = conteo()
    conf = _conf(sesion, ctx, "crear_reunion", entrada)
    assert isinstance(conf, Confirmacion) and conf.titulo == "Crear una reunión" and conf.aviso
    d = dict(conf.detalle)
    assert d["Título"] == entrada["titulo"] and d["Hora"] == "09:30" and d["Sitio"] == "Escuela de la vereda"
    assert d["Barrio o vereda"] == f"LA PAZ (vereda #{vereda})" and d["Fecha"] == "viernes 20 de noviembre de 2026"
    assert d["Abierta al equipo"] == "No"
    assert conteo() == antes  # la tarjeta no escribe
    r = _ej(sesion, ctx, "crear_reunion", entrada)
    rid = r.contenido["reunion"]["id"]
    x = db.reuniones.find_one({"_id": rid})
    assert (x["lugar_id"], x["lugar_texto"], x["hora"], x["tema"]) == (vereda, "Escuela de la vereda", "09:30",
                                                                       "Agua potable")
    assert x["lat"] is not None and x["creado_por_uid"] == 0 and x["abierta_a_equipo"] is False
    assert r.contenido["ya_existia"] is False and r.acciones == [{"tipo": "recargar"}]
    assert r.contenido["reunion"]["ruta"] == f"/reuniones/{rid}" and conteo() == (antes[0] + 1, antes[1] + 1)
    # El mismo tool_use otra vez (un reintento): no se crea otra
    r2 = _ej(sesion, ctx, "crear_reunion", entrada)
    assert r2.contenido["ya_existia"] is True and r2.contenido["reunion"]["id"] == rid
    assert conteo() == (antes[0] + 1, antes[1] + 1)
    # Y una tarjeta nueva para la misma reunión avisa que ya existe
    e = _falla_conf(sesion, ctx_de(sesion, tool_use_id="toolu_reunion2"), "crear_reunion", entrada)
    assert e.codigo == "duplicada" and e.detalle == {"id": rid, "ruta": f"/reuniones/{rid}"}
    # Un lugar ambiguo vuelve con los candidatos, sin tarjeta
    e = _falla_conf(sesion, ctx, "crear_reunion", {**entrada, "titulo": "Otra reunión inventada", "lugar": "La Paz"})
    assert e.codigo == "ambiguo" and len(e.detalle["candidatos"]) == 2
    # El planillero crea las suyas, pero no las abre al equipo
    p = como("planillero")
    e = _falla_conf(sesion, ctx_de(p), "crear_reunion", {"titulo": "Reunión de campo", "fecha": "2026-11-21",
                                                         "abierta_a_equipo": True})
    assert e.codigo == "permiso"
    r = _ej(sesion, ctx_de(p, tool_use_id="toolu_p1"), "crear_reunion", {"titulo": "Reunión de campo",
                                                                         "fecha": "2026-11-21"})
    assert db.reuniones.find_one({"_id": r.contenido["reunion"]["id"]})["creado_por_uid"] == p.uid
    assert "Abierta al equipo" not in dict(_conf(sesion, ctx_de(p), "crear_reunion", {
        "titulo": "Otra de campo", "fecha": "2026-11-22"}).detalle)
    # El consultor no crea reuniones: 403 de la API
    e = _falla_ej(sesion, ctx_de(como("consultor")), "crear_reunion", {"titulo": "No va", "fecha": "2026-11-22"})
    assert e.estado == 403
    for mala in ({"titulo": "ab", "fecha": "2026-11-20"}, {"titulo": "Bien", "fecha": "2026-02-30"},
                 {"titulo": "Bien", "fecha": "20/11/2026"}, {"titulo": "Bien", "fecha": "2026-11-20", "hora": "25:00"},
                 {"titulo": "Bien", "fecha": "2026-11-20", "lugar": "La Paz", "lugar_id": 3},
                 {"titulo": "Bien", "fecha": "2026-11-20", "lat": 7.0}, {"titulo": "1234", "fecha": "2026-11-20"}):
        with pytest.raises(ValidationError):
            H["crear_reunion"].validar(mala)


def test_agregar_asistente_la_tarjeta_no_escribe_y_aprobar_escribe_una_vez(sesion, como, ctx_de):
    db = sesion.app.state.db
    rid = _reunion(sesion, "Reunión inventada de asistentes", "2026-11-02")
    pid = persona(db, nombre="TEODOMIRA INVENTADA ASISTENTE", cedula="93000999", telefono="3105556677")
    ctx = ctx_de(sesion, tool_use_id="toolu_asistente1")
    entrada = {"reunion_id": rid, "persona_id": pid, "rol": "Vecina"}

    def conteo():
        return (len(db.personas.find_one({"_id": pid}).get("asistencias") or []),
                db.acercamientos.count_documents({"persona_id": pid}),
                db.auditoria.count_documents({"accion": "asistencia", "entidad_id": pid}))

    conf = _conf(sesion, ctx, "agregar_asistente", entrada)
    d = dict(conf.detalle)
    assert conf.titulo == "Registrar un asistente" and d["Persona"] == f"TEODOMIRA INVENTADA ASISTENTE (#{pid})"
    assert d["Reunión"] == f"Reunión inventada de asistentes (lunes 2 de noviembre de 2026) #{rid}"
    assert d["Rol en la reunión"] == "Vecina" and "acercamiento" in conf.aviso
    assert conteo() == (0, 0, 0)  # la tarjeta no escribe
    r = _ej(sesion, ctx, "agregar_asistente", entrada)
    assert conteo() == (1, 1, 1) and r.personas == {pid} and r.acciones == [{"tipo": "recargar"}]
    assert r.contenido["persona"]["nombre"] == "TEODOMIRA INVENTADA ASISTENTE"
    assert r.contenido["reunion"]["asistentes_total"] == 1
    sin_datos(_modelo(r), "93000999", "3105556677")
    # El mismo tool_use otra vez: la API devuelve lo guardado (Idempotency-Key) y no escribe de nuevo
    _ej(sesion, ctx, "agregar_asistente", entrada)
    assert conteo() == (1, 1, 1)
    # Una tarjeta nueva para la misma persona: ya está registrada (con rol o nota nuevos, solo los actualiza)
    otro = ctx_de(sesion, tool_use_id="toolu_asistente2")
    assert _falla_conf(sesion, otro, "agregar_asistente", {"reunion_id": rid, "persona_id": pid}).codigo == \
        "ya_registrada"
    assert _conf(sesion, otro, "agregar_asistente", {"reunion_id": rid, "persona_id": pid, "nota": "Llegó tarde"}
                 ).titulo == "Actualizar un asistente"
    # De quien no autorizó, el asistente no registra nada (ni para el administrador), tampoco al aprobar
    no = persona(db, nombre="NICANORA INVENTADA NO AUTORIZO", consentimiento="no")
    assert _falla_conf(sesion, ctx, "agregar_asistente", {"reunion_id": rid, "persona_id": no}).codigo == \
        "no_contactable"
    assert _falla_ej(sesion, ctx, "agregar_asistente", {"reunion_id": rid, "persona_id": no}).codigo == \
        "no_contactable"
    assert len(db.personas.find_one({"_id": no}).get("asistencias") or []) == 0
    # Una reunión que no existe o que el planillero no ve
    assert _falla_conf(sesion, ctx, "agregar_asistente", {"reunion_id": 9999, "persona_id": pid}).codigo == \
        "no_existe"
    p = ctx_de(como("planillero"), tool_use_id="toolu_asistente3")
    assert _falla_conf(sesion, p, "agregar_asistente", {"reunion_id": rid, "persona_id": pid}).codigo == "no_existe"
    assert _falla_ej(sesion, p, "agregar_asistente", {"reunion_id": rid, "persona_id": pid}).estado == 403
    assert _falla_conf(sesion, ctx, "agregar_asistente", {"reunion_id": rid, "persona_id": 999999}).codigo == \
        "no_existe"
    for mala in ({"reunion_id": rid}, {"reunion_id": True, "persona_id": pid},
                 {"reunion_id": rid, "persona_id": pid, "rol": "x" * 61}):
        with pytest.raises(ValidationError):
            H["agregar_asistente"].validar(mala)


# ───────────────────────────── pendientes ─────────────────────────────

def test_pendientes_por_rol_en_conteos(sesion, como, ctx_de):
    db = sesion.app.state.db
    hoy = modelo.hoy_local()
    persona(db, nombre="ANACLETA INVENTADA SIN PUNTO", lugar_id=_lugar(db, "LA PAZ", "barrio"))
    pid = persona(db, nombre="SOLICITANTE INVENTADA", telefono="3107778899")
    ids = []
    for tipo in ("correccion", "consulta", "supresion"):
        r = sesion.post("/api/solicitudes", json={"persona_id": pid, "tipo": tipo, "canal": "teléfono",
                                                  "descripcion": "Corrijan mi teléfono 3107778899"})
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    db.solicitudes.update_one({"_id": ids[0]}, {"$set": {"vence": (hoy - timedelta(days=2)).isoformat()}})
    db.solicitudes.update_one({"_id": ids[1]}, {"$set": {"vence": (hoy + timedelta(days=1)).isoformat()}})
    db.personas.update_one({"_id": pid}, {"$set": {"requiere_actualizacion": {"motivo": "administrador"}}})
    for cli in (sesion, coordinador(sesion.app, db)):
        r = _ej(sesion, ctx_de(cli), "pendientes", {})
        c = r.contenido
        assert c["trabajo"]["n"] == 1 and c["trabajo"]["ruta"] == "/trabajo"
        s = c["calidad"]["solicitudes"]
        assert (s["abiertas"], s["vencidas"], s["por_vencer_3_dias"]) == (3, 1, 1)
        assert s["por_tipo"] == {"correccion": 1, "consulta": 1, "supresion": 1}
        assert [x["id"] for x in s["proximas"]][:2] == [ids[0], ids[1]] and s["proximas"][0]["vencida"] is True
        assert c["calidad"]["lugares_sin_punto"]["lugares"] == 1
        assert c["calidad"]["lugares_sin_punto"]["principales"][0]["nombre"] == "LA PAZ"
        assert "lugares_sin_reconocer" in c["calidad"] and r.personas == {pid}
        assert r.resumen.startswith("Solicitudes: 3 (1 vencidas)")
        sin_datos(_modelo(r), "3107778899", "SOLICITANTE", "Corrijan")
    # Planillero y consultor: solo lo de su trabajo
    for cli in (como("planillero"), como("consultor")):
        r = _ej(sesion, ctx_de(cli), "pendientes", {})
        assert set(r.contenido) == {"trabajo"} and r.personas == set()
    assert H["pendientes"].validar({}) is not None
    with pytest.raises(ValidationError):
        H["pendientes"].validar({"todo": True})


# ───────────────────────────── mi_trabajo ─────────────────────────────

def test_mi_trabajo_listas_y_cola_sin_numeros(sesion, como, ctx_de):
    db = sesion.app.state.db
    tels = [f"31599900{i:02d}" for i in range(3)]
    pids = [contactable(db, f"CONTACTABLE INVENTADA {i}", t) for i, t in enumerate(tels)]
    c = como("consultor")
    r = _ej(sesion, ctx_de(c), "mi_trabajo", {"lista": "por_llamar"})
    cola = r.contenido["cola"]
    assert cola["total"] == 3 and {f["id"] for f in cola["filas"]} == set(pids) and r.personas == set(pids)
    for f in cola["filas"]:
        assert "telefono_mascara" not in f and f["telefono_indice"] == 0 and f["canales_permitidos"]
    # «Seguimiento» solo aparece con el ajuste encendido (apagado por defecto)
    assert {x["clave"] for x in r.contenido["listas_de_trabajo"]} == {"por_llamar", "volver_a_llamar", "mis_hoy"}
    assert r.contenido["rol"] == "consultor" and "cola: 3 personas" in r.resumen
    sin_datos(_modelo(r), *tels, *[f"···{t[-4:]}" for t in tels])
    # Las lecturas de la cola cuentan para el tope del consultor (las registra la API)
    assert db.lecturas.count_documents({"uid": c.uid}) == 3
    # El planillero: sus listas (con la ruta a Habitantes) y sin cola
    p = como("planillero")
    r = _ej(sesion, ctx_de(p), "mi_trabajo", {})
    listas = {x["clave"]: x for x in r.contenido["listas_de_trabajo"]}
    assert "sin_cedula" in listas and listas["sin_cedula"]["ruta"].startswith("/personas?")
    assert "cola" not in r.contenido and r.personas == set()
    assert _falla_ej(sesion, ctx_de(p), "mi_trabajo", {"lista": "por_llamar"}).codigo == "permiso"
    assert _falla_ej(sesion, ctx_de(p), "mi_trabajo", {"uid": c.uid}).estado == 403
    # El administrador ve las listas de otro usuario, pero no su cola
    r = _ej(sesion, ctx_de(sesion), "mi_trabajo", {"uid": p.uid})
    assert r.contenido["rol"] == "planillero"
    assert _falla_ej(sesion, ctx_de(sesion), "mi_trabajo", {"uid": p.uid, "lista": "por_llamar"}).codigo == "invalido"
    with pytest.raises(ValidationError):
        H["mi_trabajo"].validar({"lista": "todas"})


# ───────────────────────────── equipo ─────────────────────────────

def test_equipo_sin_sesiones_ip_ni_telefonos(sesion, como, ctx_de):
    app, db = sesion.app, sesion.app.state.db
    lugar = _lugar(db, "TRES DE OCTUBRE", "barrio")
    p = como("planillero", telefono="3201112233", asignacion={"lugares": [lugar], "areas": []})
    c = como("consultor")
    pid = persona(db, nombre="FICHA INVENTADA DEL EQUIPO", lugar_id=lugar, cedula="93001234")
    bd.auditar(db, aa.quien_de(app, p.uid), "crear", "persona", pid, {"nombre": "x"})
    for cli in (sesion, coordinador(app, db)):
        r = _ej(sesion, ctx_de(cli), "equipo", {"avance": "lugar"})
        usuarios = {u["usuario"]: u for u in r.contenido["usuarios"]}
        assert usuarios[p.usuario]["planillero"]["creadas_netas"] == 1 and "consultor" in usuarios[c.usuario]
        assert usuarios[p.usuario]["asignacion"] == {"lugares": 1, "areas": 0}
        assert r.contenido["totales"]["planilleros_activos"] == 1 and r.contenido["totales"]["creadas_netas"] == 1
        fila = next(f for f in r.contenido["avance"]["filas"] if f["id"] == lugar)
        assert fila["personas"] == 1 and fila["pct_cedula"] == 100 and p.usuario in fila["responsables"]
        texto = r.texto_para_modelo()
        assert "3201112233" not in texto and "ultimo_ingreso" not in texto
        sin_datos(_modelo(r))
    r = _ej(sesion, ctx_de(sesion), "equipo", {"rol": "consultor"})
    assert {u["rol"] for u in r.contenido["usuarios"]} == {"consultor"}
    for mala in ({"desde": "2026-11-05", "hasta": "2026-11-01"}, {"rol": "admin"}, {"avance": "vereda"}):
        with pytest.raises(ValidationError):
            H["equipo"].validar(mala)


# ───────────────────────────── buscar_lugar ─────────────────────────────

def test_buscar_lugar_homonimos_errores_de_escritura_y_sugerencias(sesion, como, ctx_de):
    db = sesion.app.state.db
    barrio, vereda = _lugar(db, "LA PAZ", "barrio"), _lugar(db, "LA PAZ", "vereda")
    tigre = {t: _lugar(db, "SAN MIGUEL DEL TIGRE", t) for t in ("centro_poblado", "vereda", "corregimiento")}
    for cli in (sesion, como("planillero"), como("consultor")):  # el nomenclátor es de todos los roles
        ctx = ctx_de(cli)
        r = _ej(sesion, ctx, "buscar_lugar", {"texto": "La Paz"})
        assert r.contenido["resultado"] == "ambiguo" and "sugerido" not in r.contenido
        assert {x["id"]: x["tipo"] for x in r.contenido["lugares"]} == {barrio: "barrio", vereda: "vereda"}
        assert r.resumen == "2 lugares con ese nombre" and "pregunte" in r.contenido["nota"]
        r = _ej(sesion, ctx, "buscar_lugar", {"texto": "barrio La Paz"})
        assert r.contenido["resultado"] == "unico" and r.contenido["sugerido"] == barrio
        assert r.contenido["lugares"] == [{"id": barrio, "nombre": "LA PAZ", "tipo": "barrio", "zona": "urbana",
                                           "padre": "YONDO", "tiene_punto": False, "tiene_poligono": False}]
        assert _ej(sesion, ctx, "buscar_lugar", {"texto": "La Paz", "tipo": "vereda"}).contenido["sugerido"] == vereda
        r = _ej(sesion, ctx, "buscar_lugar", {"texto": "San Miguel del Tigre"})
        assert r.contenido["resultado"] == "mismo_sitio" and r.contenido["sugerido"] == tigre["centro_poblado"]
        assert [x["id"] for x in r.contenido["lugares"]] == [tigre["centro_poblado"], tigre["vereda"],
                                                             tigre["corregimiento"]]
        r = _ej(sesion, ctx, "buscar_lugar", {"texto": "san migel del tigre"})
        assert r.contenido["parecido"] is True and r.contenido["sugerido"] == tigre["centro_poblado"]
        assert _ej(sesion, ctx, "buscar_lugar", {"texto": "corregimiento San Miguel del Tigre"}
                   ).contenido["sugerido"] == tigre["corregimiento"]
        assert _ej(sesion, ctx, "buscar_lugar", {"texto": "la vereda san miguel del tigre"}
                   ).contenido["sugerido"] == tigre["vereda"]
        assert _ej(sesion, ctx, "buscar_lugar", {"texto": "3 de octubre"}).contenido["lugares"][0]["nombre"] == \
            "TRES DE OCTUBRE"
        assert _ej(sesion, ctx, "buscar_lugar", {"texto": "Casabe"}).contenido["lugares"][0]["nombre"] == "YONDO"
        r = _ej(sesion, ctx, "buscar_lugar", {"texto": "Las Margaritas", "limite": 3})
        assert r.contenido["resultado"] == "ninguno" and 1 <= len(r.contenido["sugerencias"]) <= 3
        assert "lugares" not in r.contenido and "Calidad de datos" in r.contenido["nota"]
        r = _ej(sesion, ctx, "buscar_lugar", {"texto": "barrio San Miguel del Tigre"})  # existe, pero no como barrio
        assert r.contenido["resultado"] == "ninguno" and len(r.contenido["sugerencias"]) == 3
        for x in recorrer(r.contenido):
            assert x[1] not in ("lat", "lon")  # el modelo no necesita las coordenadas
    for mala in ({"texto": "x"}, {"texto": "La Paz", "tipo": "municipio"}, {"texto": "La Paz", "limite": 50}):
        with pytest.raises(ValidationError):
            H["buscar_lugar"].validar(mala)


# ───────────────────────────── catalogos ─────────────────────────────

def test_catalogos_por_rol_sin_lo_sensible(sesion, como, ctx_de):
    db = sesion.app.state.db
    for i, (clave, sensible) in enumerate((("religion", True), ("talla", False)), 900):
        db.campos.insert_one({"_id": i, "clave": clave, "etiqueta": clave.capitalize(), "tipo": "texto",
                              "opciones": [], "orden": i, "activo": True, "sensible": sensible})
    _rica(db)  # con una lista de origen: no sale en los catálogos
    sensibles = set(bd.ETIQUETAS_SENSIBLES)
    for cli in (sesion, coordinador(sesion.app, db)):
        r = _ej(sesion, ctx_de(cli), "catalogos", {})
        c = r.contenido
        nombres = {e["nombre"] for e in c["etiquetas"]}
        assert "Vivienda" in nombres and not nombres & sensibles
        assert [x["clave"] for x in c["campos_propios"]] == ["talla"]
        assert set(c["valores"]["medios_autorizacion"]) == set(hg.MEDIOS_ADMIN)
        assert set(c["valores"]["canales_acercamiento"]) == set(modelo.CANALES)
        assert not {"listas", "usuarios", "lugares", "aviso_privacidad"} & set(c)
        assert "regimenes_salud" not in c["valores"] and "Lista Inventada B3" not in r.texto_para_modelo()
    p = _ej(sesion, ctx_de(como("planillero")), "catalogos", {}).contenido
    assert not {e["nombre"] for e in p["etiquetas"]} & sensibles and p["campos_propios"] == [
        {"clave": "talla", "etiqueta": "Talla", "tipo": "texto", "opciones": []}]
    assert set(p["valores"]["canales_acercamiento"]) == {"visita", "reunion"}
    assert list(p["valores"]["medios_autorizacion"]) == modelo.MEDIOS_POR_ROL["planillero"]
    consultor = _ej(sesion, ctx_de(como("consultor")), "catalogos", {}).contenido
    assert consultor["etiquetas"] == [] and consultor["campos_propios"] == []
    assert not {"visita", "reunion"} & set(consultor["valores"]["canales_acercamiento"])
    assert list(consultor["valores"]["medios_autorizacion"]) == modelo.MEDIOS_POR_ROL["consultor"]
    solo = _ej(sesion, ctx_de(sesion), "catalogos", {"secciones": ["valores"]}).contenido
    assert set(solo) == {"valores", "nota"}
    with pytest.raises(ValidationError):
        H["catalogos"].validar({"secciones": ["listas"]})


# ───────────────────────────── Un turno completo por el bucle ─────────────────────────────

def test_turno_completo_registrar_un_asistente_espera_la_aprobacion_y_escribe_una_vez(sesion):
    db = sesion.app.state.db
    rid = _reunion(sesion, "Reunión inventada del turno", "2026-11-02")
    pid = persona(db, nombre="FILOMENA INVENTADA DEL TURNO", cedula="93005555")
    aa.encender(sesion.app, aa.sse(aa.TU("toolu_asis", "agregar_asistente", {"reunion_id": rid, "persona_id": pid}),
                                   stop="tool_use"),
                aa.sse(aa.T("Listo: quedó registrada.")))
    r, ev = aa.enviar(sesion, "Registra a Filomena en la reunión")
    assert r.status_code == 200, r.text
    cid = ev[0]["conversacion"]
    assert [e["estado"] for e in ev if e["tipo"] == "herramienta"] == ["inicio", "pendiente"]
    conf = next(e for e in ev if e["tipo"] == "confirmar")
    assert conf["nombre"] == "agregar_asistente" and conf["titulo"] == "Registrar un asistente"
    assert ["Persona", f"FILOMENA INVENTADA DEL TURNO (#{pid})"] in conf["detalle"]
    assert ev[-1]["motivo"] == "confirmacion" and not db.personas.find_one({"_id": pid}).get("asistencias")
    assert pid in db.agente_conversaciones.find_one({"_id": cid})["personas"]
    r, ev = aa.decidir(sesion, cid, toolu_asis=True)
    assert r.status_code == 200, r.text
    assert [(e["estado"], e.get("resumen")) for e in ev if e["tipo"] == "herramienta"] == [
        ("aprobada", None), ("ok", "Asistente registrado")]
    assert {"tipo": "accion", "accion": {"tipo": "recargar"}} in ev and ev[-1]["motivo"] == "listo"
    assert len(db.personas.find_one({"_id": pid})["asistencias"]) == 1
    assert db.auditoria.count_documents({"accion": "asistencia", "entidad_id": pid}) == 1
    assert db.idempotencia.count_documents({"_id": {"$regex": f"agente\\.{cid}\\.toolu_asis$"}}) == 1
