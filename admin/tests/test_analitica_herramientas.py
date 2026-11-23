"""Las herramientas del asistente `analizar` y `diagnostico` (`app/agente/herramientas/analisis.py`): esquemas válidos
para la Messages API, solo A y K (y por MCP con el alcance «analitica»), lo que el modelo recibe (agregados, sin
personas ni datos vedados, los títulos de reuniones con `texto_libre`), el gráfico que arma el servidor (válido y sin
celdas ocultas) y los errores (lugar ambiguo, etiqueta sensible, filtros fuera de la lista, 403 de P y C).

Las herramientas corren en el bucle de la aplicación y llaman a la API de verdad por ASGI con la sesión de cada rol.
Solo datos inventados."""
from __future__ import annotations

import json
import re
from datetime import timedelta

import pytest
from pydantic import ValidationError

import ayudas_agente as aa
import ayudas_analitica as ya
from ayudas_g3 import coordinador, recorrer
from app import analitica as an
from app import modelo
from app.agente import grafico, herramientas
from app.agente.herramientas import analisis as ha
from app.agente.herramientas.base import ErrorHerramienta, Resultado
from conftest import crear_usuario

H = {h.nombre: h for h in ha.HERRAMIENTAS}
HOY = modelo.hoy_local()
PALABRAS_ESQUEMA = {"type", "properties", "required", "additionalProperties", "description", "enum", "items",
                    "minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems", "default", "anyOf"}
CLAVES_VEDADAS = {"sensibles", "listas", "lista", "lider", "lideres", "en_ambas_bases", "fuentes", "actividad",
                  "demografia", "origen", "regimen_salud", "cedula", "telefono", "telefono2", "correo", "lat", "lon",
                  "punto", "puntos_mapa", "sesiones", "ip", "nombre_norm", "direccion", "persona_id", "personas_ids"}


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


def _ej(sesion, ctx, nombre: str, entrada: dict) -> Resultado:
    return aa.correr(sesion, aa.ejecutar, H[nombre], ctx, entrada)


def _falla(sesion, ctx, nombre: str, entrada: dict) -> ErrorHerramienta:
    with pytest.raises(ErrorHerramienta) as e:
        aa.correr(sesion, aa.ejecutar, H[nombre], ctx, entrada)
    return e.value


def _modelo(r: Resultado):
    return json.loads(r.texto_para_modelo())


def _palabras(s, ruta=""):
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


def _sin_vedados(x, *valores: str) -> None:
    for ruta, k, _ in recorrer(x):
        assert k not in CLAVES_VEDADAS, (ruta, k)
    texto = json.dumps(x, ensure_ascii=False)
    for v in valores:
        assert v not in texto, v


# ───────────────────────────── Catálogo y esquemas ─────────────────────────────

def test_definiciones_son_json_schema_validos_para_la_messages_api():
    assert [h.nombre for h in ha.HERRAMIENTAS] == ["analizar", "diagnostico"]
    for h in ha.HERRAMIENTAS:
        d = h.definicion()
        assert set(d) == {"name", "description", "input_schema", "eager_input_streaming"}, h.nombre
        assert re.fullmatch(r"[a-z_]{3,64}", d["name"]) and d["eager_input_streaming"] is True
        assert 200 < len(d["description"]) < 1500, (h.nombre, len(d["description"]))
        assert re.match(r"^\w+(ando|endo|iendo)\b", h.etiqueta), h.etiqueta
        s = d["input_schema"]
        texto = json.dumps(s, ensure_ascii=False)
        assert "$ref" not in texto and "$defs" not in texto and '"title"' not in texto and "\\n" not in texto
        assert s["type"] == "object" and s["properties"], h.nombre
        for obj in _objetos(s):
            assert obj.get("additionalProperties") is False, h.nombre
            assert set(obj.get("required", [])) <= set(obj.get("properties", {})), h.nombre
        for ruta, k in _palabras(s):
            assert k in PALABRAS_ESQUEMA, (h.nombre, ruta, k)
        for nombre, prop in s["properties"].items():
            assert "type" in prop or "anyOf" in prop or "enum" in prop, (h.nombre, nombre)
        assert h.tipo == "lectura" and h.confirmar is None and h.permisos == ("analitica.ver",)
        assert h.mcp == "analitica" and h.alcance_mcp() == "analitica"
        json.loads(json.dumps(d))  # determinista y serializable (el bucle la congela por conversación)
    assert H["diagnostico"].plazo == 120.0 and H["analizar"].plazo is None
    # Los filtros nunca ofrecen búsqueda por texto, listas, líderes, salud, bases políticas, reunión ni creador
    filtros = H["analizar"].definicion()["input_schema"]["properties"]["filtros"]["properties"]
    assert not {"q", "lista", "lider", "tipo", "regimen_salud", "ids", "poligono", "mios", "reunion_id", "creado_por",
                "actualizado_por", "situacion", "ocupacion", "tratables"} & set(filtros)
    assert set(filtros["fuente"]["enum"]) == {"tramites", "reunion", "manual", "planilla"}
    assert "no" not in filtros["consentimiento"]["enum"]
    dims = H["analizar"].definicion()["input_schema"]["properties"]["dimensiones"]["items"]["enum"]
    assert not {"lider", "listas", "regimen_salud", "creado_por", "fuente_politica", "sensibles"} & set(dims)
    assert "diagnostico" not in H["analizar"].definicion()["input_schema"]["properties"]["tipo"]["enum"]


def test_van_en_el_catalogo_entre_planillas_y_gestion_y_solo_para_a_y_k(sesion, como):
    app, db = sesion.app, sesion.app.state.db
    nombres = [h.nombre for h in herramientas.fijas()]
    assert nombres.index("analizar") < nombres.index("diagnostico") < nombres.index("indicadores")
    k = coordinador(app, db)
    quienes = {"admin": aa.quien_de(app, 0), "coordinador": aa.quien_de(app, k.uid),
               "planillero": aa.quien_de(app, como("planillero").uid),
               "consultor": aa.quien_de(app, como("consultor").uid)}
    for rol, quien in quienes.items():
        for escritura in (True, False):
            ofrecidas = {h.nombre for h in herramientas.para(quien, {"escritura": escritura}, app.state.cfg)}
            assert (set(H) <= ofrecidas) == (rol in ("admin", "coordinador")), (rol, escritura)
            assert not (set(H) & ofrecidas) or rol in ("admin", "coordinador")


@pytest.mark.parametrize("entrada", [
    {"tipo": "diagnostico"},
    {"tipo": "serie", "evento": "altas", "dimensiones": ["zona"]},
    {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"zona": "rural", "sexo": "F", "menor": False,
                                                           "con_cedula": True}},
    {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"lugar": "La Paz", "lugar_id": 3}},
    {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"tipo_lugar": "vereda"}},
    {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"lugar": "La Paz", "tipo_lugar": "vereda",
                                                           "zona": "rural", "sexo": "F", "menor": True}},
    {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"q": "ana"}},
    {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"edad_min": 18}},
    {"tipo": "tabla", "dimensiones": ["lider"]},
    {"tipo": "tabla", "dimensiones": ["sexo"], "personas": [1]},
])
def test_entradas_invalidas_se_rechazan_antes_de_llamar(entrada):
    with pytest.raises(ValidationError):
        H["analizar"].validar(entrada)


def test_diagnostico_valida_su_entrada():
    H["diagnostico"].validar({"fecha_meta": "2027-03-01", "meta_pct": 25, "filtros": {"zona": "rural"}})
    for mala in ({"tipo": "tabla"}, {"meta_pct": 0}, {"fecha_meta": "2027-02-30"}, {"filtros": {"lista": "x"}}):
        with pytest.raises(ValidationError):
            H["diagnostico"].validar(mala)


# ───────────────────────────── Ejecución ─────────────────────────────

@pytest.fixture
def base(sesion):
    db = sesion.app.state.db
    uids = [crear_usuario(db, "planillero")["_id"], crear_usuario(db, "consultor")["_id"]]
    ids = ya.base_variada(db, 150, 5, HOY, uids)
    db.personas.update_many({}, {"$set": {"listas": ["Lista Inventada B3"], "lider": True,
                                          "sensibles": {"etnia": "Raizal"}, "regimen_salud": "Subsidiado"}})
    return {"db": db, "ids": ids, "uids": uids}


def test_analizar_devuelve_lo_de_la_api_con_su_grafico_y_sin_personas(sesion, ctx_de, base):
    db = base["db"]
    numeros = [x[k] for x in db.personas.find({}, {"cedula": 1, "telefono": 1}) for k in ("cedula", "telefono")
               if x.get(k)]
    for cli in (sesion, coordinador(sesion.app, db)):
        ctx = ctx_de(cli)
        r = _ej(sesion, ctx, "analizar", {"tipo": "tabla", "dimensiones": ["sexo"],
                                          "metricas": ["personas", "pct", "pct_con_cedula"]})
        api = ya.consulta(sesion, tipo="tabla", dimensiones=["sexo"], metricas=["personas", "pct", "pct_con_cedula"])
        assert r.contenido == api and r.personas == set()
        assert r.resumen.startswith("Tabla por sexo") and len(r.acciones) == 1
        g = r.acciones[0]
        assert g["tipo"] == "grafico" and grafico.validar(g) == g and g["clase"] == "barras" and g["unidad"] == "%"
        _sin_vedados(_modelo(r), "Lista Inventada B3", "Raizal", "Subsidiado", *numeros)


def test_cada_tipo_da_un_resultado_limpio_y_un_grafico_valido_sin_celdas_ocultas(sesion, ctx_de, base):
    ctx = ctx_de(sesion)
    entradas = [
        {"tipo": "tabla", "dimensiones": ["lugar"]}, {"tipo": "tabla", "dimensiones": ["rango_edad"]},
        {"tipo": "tabla", "dimensiones": ["zona", "sexo"]}, {"tipo": "serie", "evento": "altas"},
        {"tipo": "serie", "evento": "acercamientos", "desglose": "canal"}, {"tipo": "embudo"},
        {"tipo": "embudo", "dimensiones": ["zona"]}, {"tipo": "cobertura"}, {"tipo": "brechas"}, {"tipo": "equipo"},
        {"tipo": "calidad"}, {"tipo": "anomalias"}, {"tipo": "cohortes"},
        {"tipo": "ritmo", "fecha_meta": (HOY + timedelta(days=120)).isoformat()}, {"tipo": "franjas"},
        {"tipo": "intentos"}, {"tipo": "captura"},
        {"tipo": "comparar", "metrica": "acercamientos", "dimensiones": ["canal"]},
        {"tipo": "comparar", "metrica": "tasa_contacto_util", "dimensiones": ["usuario"]},
        {"tipo": "reuniones_efecto"}]
    con_grafico = 0
    for e in entradas:
        r = _ej(sesion, ctx, "analizar", e)
        assert r.personas == set() and r.resumen
        _sin_vedados(_modelo(r), "Lista Inventada B3", "Raizal", "Subsidiado")
        for a in r.acciones:
            assert a["tipo"] == "grafico" and grafico.validar(a) == a, e
            assert len(a["items"]) <= grafico.MAX_ITEMS
            assert all(isinstance(it["valor"], (int, float)) for it in a["items"])
            con_grafico += 1
        if e["tipo"] in ("tabla", "embudo", "cobertura", "calidad", "franjas", "intentos") and \
                e.get("dimensiones") != ["zona", "sexo"]:
            assert r.acciones, e
    assert con_grafico >= 12


def test_el_grafico_deja_fuera_las_celdas_ocultas_y_lo_dice(sesion, ctx_de):
    db = sesion.app.state.db
    ya.personas(db, [{"sexo": "F"} for _ in range(30)] + [{"sexo": "M"} for _ in range(20)] +
                [{"sexo": "N"} for _ in range(2)])
    r = _ej(sesion, ctx_de(sesion), "analizar", {"tipo": "tabla", "dimensiones": ["sexo"]})
    publicados = {f["valor"]: f["personas"] for f in r.contenido["filas"]}
    assert publicados["N"] == "<5" and list(publicados.values()).count(an.OCULTA) == 1
    g = r.acciones[0]
    assert len(g["items"]) == 1 and "ocultos por privacidad" in g["nota"]
    assert all(it["valor"] >= 5 for it in g["items"])


def test_con_pocas_personas_responde_pocas_y_sin_grafico(sesion, ctx_de):
    db = sesion.app.state.db
    ya.personas(db, [{"sexo": "F"} for _ in range(7)])
    r = _ej(sesion, ctx_de(sesion), "analizar", {"tipo": "embudo"})
    assert r.contenido["pocas"] is True and r.contenido["personas"] == "<10" and "menos de 10" in r.contenido["nota"]
    assert r.acciones == [] and r.resumen == "Menos de 10 personas: sin cifras"


def test_lugar_por_nombre_se_resuelve_y_el_ambiguo_pregunta(sesion, ctx_de):
    db = sesion.app.state.db
    vereda = db.lugares.find_one({"nombre": "LA PAZ", "tipo": "vereda"})["_id"]
    ya.personas(db, [{"lugar_id": vereda, "sexo": "F"} for _ in range(12)] + [{"sexo": "M"} for _ in range(20)])
    ctx = ctx_de(sesion)
    r = _ej(sesion, ctx, "analizar", {"tipo": "tabla", "dimensiones": ["sexo"],
                                      "filtros": {"lugar": "vereda La Paz"}})
    assert r.contenido["base"] == {"personas": 12}
    assert r.contenido["filtros"] == {"lugar_id": f"LA PAZ (vereda #{vereda})"}
    e = _falla(sesion, ctx, "analizar", {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"lugar": "La Paz"}})
    assert e.codigo == "ambiguo" and e.detalle["candidatos"]
    e = _falla(sesion, ctx, "analizar", {"tipo": "tabla", "dimensiones": ["sexo"],
                                         "filtros": {"lugar": "Lugar que no existe zzz"}})
    assert e.codigo == "no_existe"


def test_etiqueta_sensible_y_errores_de_la_api_llegan_limpios(sesion, ctx_de):
    db = sesion.app.state.db
    ya.personas(db, [{} for _ in range(15)])
    ctx = ctx_de(sesion)
    sensible = db.etiquetas.find_one({"nombre": "Líder comunitario"})["_id"]
    e = _falla(sesion, ctx, "analizar", {"tipo": "tabla", "dimensiones": ["sexo"], "filtros": {"etiqueta": sensible}})
    assert (e.codigo, e.estado) == ("permiso", 403)
    e = _falla(sesion, ctx, "analizar", {"tipo": "ritmo", "fecha_meta": HOY.isoformat()})
    assert e.codigo == "invalido" and "posterior" in e.mensaje


@pytest.mark.parametrize("rol", ["planillero", "consultor"])
def test_planillero_y_consultor_reciben_403_si_igual_la_llaman(sesion, como, ctx_de, rol):
    cli = como(rol)
    for nombre, entrada in (("analizar", {"tipo": "tabla", "dimensiones": ["sexo"]}), ("diagnostico", {})):
        e = _falla(sesion, ctx_de(cli), nombre, entrada)
        assert (e.estado, e.codigo) == (403, "permiso"), nombre


def test_diagnostico_por_la_herramienta(sesion, ctx_de, base):
    db = base["db"]
    lid = ya.lugares(db, 1)[0]
    db.reuniones.insert_one({"_id": 700, "titulo": "Reunión del 3001234567 inventada", "lugar_id": lid,
                             "fecha": (HOY - timedelta(days=50)).isoformat()})
    r = _ej(sesion, ctx_de(sesion), "diagnostico", {"fecha_meta": (HOY + timedelta(days=90)).isoformat()})
    c = r.contenido
    assert c["tipo"] == "diagnostico" and c["hallazgos"] and r.personas == set()
    assert r.resumen.endswith(")") or "hallazgos" in r.resumen
    for h in c["hallazgos"]:
        assert h["accion"] and h["por_que"] and h["severidad"] in ("alta", "media", "baja")
        if "enlace" in h:
            assert h["enlace"]["ruta"].startswith(("/personas?", "/calidad", "/ajustes"))
    g = r.acciones[0]
    assert g["clase"] == "apilada" and grafico.validar(g) == g
    assert sum(it["valor"] for it in g["items"]) == len(c["hallazgos"])
    _sin_vedados(_modelo(r), "Lista Inventada B3", "Raizal", "Subsidiado")
    # El título de una reunión (texto que escribe una persona) llega con sus números enmascarados
    ef = _ej(sesion, ctx_de(sesion), "analizar", {"tipo": "reuniones_efecto"})
    texto = json.dumps(ef.contenido, ensure_ascii=False)
    assert "3001234567" not in texto and "···567" in texto, texto[texto.find("3001234567") - 300:][:600]


def test_diagnostico_con_filtros_los_dice_legibles(sesion, ctx_de, base):
    r = _ej(sesion, ctx_de(sesion), "diagnostico", {"filtros": {"zona": "rural"}})
    assert r.contenido["filtros"] == {"zona": "rural"}
    for h in r.contenido["hallazgos"]:
        if h.get("enlace", {}).get("ruta", "").startswith("/personas?"):
            assert "zona=rural" in h["enlace"]["ruta"]


def test_no_cuenta_a_quien_no_autorizo_por_la_herramienta(sesion, ctx_de, base):
    ctx = ctx_de(sesion)
    entrada = {"tipo": "tabla", "dimensiones": ["zona"], "metricas": ["personas", "pct", "pct_abordadas"]}
    antes = _ej(sesion, ctx, "analizar", entrada)
    nos = ya.personas(base["db"], [{"consentimiento": "no", "zona": "rural", "abordaje": {"n": 3, "efectivos": 1}}
                                   for _ in range(12)])
    for pid in nos:
        ya.acercamiento(base["db"], pid, base["uids"][1], dia=HOY)
    despues = _ej(sesion, ctx, "analizar", entrada)
    assert despues.contenido == antes.contenido and despues.acciones == antes.acciones
