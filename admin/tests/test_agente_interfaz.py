"""Herramientas de interfaz del asistente (`app/agente/herramientas/interfaz.py`): el Mapa 3D (`mapa`) y las vistas
del panel (`abrir_vista`).

Se prueba que las acciones para el navegador tienen exactamente la forma del contrato (§6 de docs/agente.md), que los
lugares se resuelven en el servidor (homónimos de «La Paz» y «San Miguel del Tigre», lugares sin punto, inexistentes
con sugerencias) y que lo ambiguo no mueve nada, que los filtros fuera de la lista blanca se rechazan, que las cifras
salen de `/api/mapa/puntos`, que los nombres y las coordenadas de las personas van solo al navegador (nunca al
modelo), los permisos por rol (el mapa solo para A y K; cada vista con el permiso de la tabla `RUTAS` de app.js) y un
turno completo por el bucle con la Messages API simulada. Solo datos inventados."""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import ValidationError

import ayudas_agente as aa
from ayudas_g3 import coordinador, persona, recorrer
from conftest import CASCO
from app.agente import herramientas
from app.agente.herramientas import interfaz as hi
from app.agente.herramientas.base import ErrorHerramienta, Resultado

H = {h.nombre: h for h in hi.HERRAMIENTAS}
WEB = Path(__file__).resolve().parents[1] / "web" / "js"
LON, LAT = CASCO
CUADRO = [[LON - 0.004, LAT - 0.004], [LON + 0.004, LAT - 0.004], [LON + 0.004, LAT + 0.004],
          [LON - 0.004, LAT + 0.004]]

# La forma de cada acción del navegador (§6): claves permitidas y valores válidos
CLAVES_ACCION = {"volar": {"tipo", "lugar", "lat", "lon", "zoom", "pitch", "bearing"},
                 "filtros": {"tipo", "valores", "reemplazar"}, "capas": {"tipo", "valores"}, "base": {"tipo", "base"},
                 "hexagono": {"tipo", "tamano"}, "recorrido": {"tipo", "nombre"}, "giro": {"tipo", "activo"},
                 "resaltar": {"tipo", "puntos", "color", "encuadrar", "sumar"}, "limpiar": {"tipo", "todo"},
                 "zona": {"tipo", "area_id", "lugar_id", "cerrar"}}
CAPAS = {"calor", "columnas", "puntos", "veredas", "reuniones", "edificios", "relieve", "areas"}


def _forma_del_contrato(accion: dict) -> None:
    """Una acción `{tipo: "mapa", acciones}` como la entrega el widget a `accionesMapa` (§6)."""
    assert set(accion) == {"tipo", "acciones"} and accion["tipo"] == "mapa"
    for a in accion["acciones"]:
        t = a["tipo"]
        assert set(a) <= CLAVES_ACCION[t], a
        if t == "volar":
            assert ("lugar" in a) != ("lat" in a), a
            if "lugar" in a:
                assert set(a["lugar"]) == {"id", "nombre", "tipo", "lat", "lon", "poligono"}
                assert isinstance(a["lugar"]["poligono"], bool) and isinstance(a["lugar"]["id"], int)
        elif t == "filtros":
            assert isinstance(a["reemplazar"], bool) and all(isinstance(v, str) for v in a["valores"].values())
            assert not {"poligono", "area_id", "ids", "mios", "q", "lista", "lider"} & set(a["valores"])
        elif t == "capas":
            assert a["valores"] and set(a["valores"]) <= CAPAS
            assert all(isinstance(v, bool) for v in a["valores"].values())
        elif t == "base":
            assert a["base"] in ("auto", "oscuro", "claro", "satelite")
        elif t == "hexagono":
            assert a["tamano"] in ("auto", "150", "400", "1000")
        elif t == "recorrido":
            assert a["nombre"] in ("municipio", "casco", "tigre")
        elif t == "resaltar":
            assert 0 < len(a["puntos"]) <= 500 and isinstance(a["encuadrar"], bool) and isinstance(a["sumar"], bool)
            for p in a["puntos"]:
                assert set(p) <= {"id", "lat", "lon", "etiqueta"} and {"lat", "lon"} <= set(p)
            assert "color" not in a or re.fullmatch(r"#[0-9a-fA-F]{6}", a["color"])
        elif t == "zona":
            assert sum(k in a for k in ("area_id", "lugar_id", "cerrar")) == 1


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


def _ej(cliente, ctx, nombre: str, entrada: dict) -> Resultado:
    r = aa.correr(cliente, aa.ejecutar, H[nombre], ctx, entrada)
    for a in r.acciones:
        if a["tipo"] == "mapa":
            _forma_del_contrato(a)
    return r


def _falla(cliente, ctx, nombre: str, entrada: dict) -> ErrorHerramienta:
    with pytest.raises(ErrorHerramienta) as e:
        aa.correr(cliente, aa.ejecutar, H[nombre], ctx, entrada)
    return e.value


def _mapa(cliente, ctx, *acciones: dict) -> Resultado:
    return _ej(cliente, ctx, "mapa", {"acciones": list(acciones)})


def _navegador(r: Resultado) -> list[dict]:
    assert len(r.acciones) == 1 and r.acciones[0]["tipo"] == "mapa"
    return r.acciones[0]["acciones"]


def _lugar(db, nombre: str, tipo: str) -> dict:
    return db.lugares.find_one({"nombre": nombre, "tipo": tipo}, {"geom": 0})


def _sin_coordenadas_ni_nombres(r: Resultado, *nombres: str, coords=()) -> None:
    """Lo que ve el modelo no trae claves de coordenadas ni los nombres o coordenadas de las personas."""
    modelo = json.loads(r.texto_para_modelo())
    for ruta, k, _ in recorrer(modelo):
        if not ruta.endswith(".capas"):  # ahí «puntos» es la capa (prendida o apagada), no coordenadas
            assert k not in ("lat", "lon", "puntos", "etiqueta", "punto"), (ruta, k)
    texto = r.texto_para_modelo()
    for n in nombres:
        assert n not in texto, n
    for c in coords:
        assert str(c) not in texto, c


# ───────────────────────────── Permisos ─────────────────────────────

def test_el_mapa_es_solo_del_administrador_y_del_coordinador(sesion, como, ctx_de):
    app, db = sesion.app, sesion.app.state.db
    for cli in (como("planillero"), como("consultor")):
        quien = aa.quien_de(app, cli.uid)
        nombres = {h.nombre for h in herramientas.para(quien, {"escritura": True}, app.state.cfg)}
        assert "mapa" not in nombres and "abrir_vista" in nombres
        ctx = ctx_de(cli)
        e = _falla(sesion, ctx, "mapa", {"acciones": [{"tipo": "base", "base": "oscuro"}]})
        assert (e.estado, e.codigo) == (403, "permiso")
        with pytest.raises(ErrorHerramienta) as api:  # y la API del mapa también lo rechaza
            aa.correr(sesion, ctx.api.get, "/api/mapa/puntos")
        assert (api.value.estado, api.value.codigo) == (403, "permiso")
    k = coordinador(app, db)
    assert "mapa" in {h.nombre for h in herramientas.para(aa.quien_de(app, k.uid), {}, app.state.cfg)}
    r = _mapa(sesion, ctx_de(k), {"tipo": "recorrido", "nombre": "tigre"})
    assert _navegador(r) == [{"tipo": "recorrido", "nombre": "tigre"}] and r.resumen == \
        "Recorrido por San Miguel del Tigre"


# ───────────────────────────── Formas exactas ─────────────────────────────

def test_las_acciones_tienen_la_forma_exacta_del_contrato(sesion, ctx_de):
    db = sesion.app.state.db
    v = _lugar(db, "LA PAZ", "vereda")
    for i in range(2):
        persona(db, nombre=f"RURAL INVENTADA {i}", zona="rural", sexo="F", lat=6.86 + i / 1000, lon=-74.14)
    r = _mapa(sesion, ctx_de(sesion),
              {"tipo": "volar", "lugar": "vereda La Paz", "zoom": 13, "pitch": 40},
              {"tipo": "filtros", "valores": {"zona": "rural", "sexo": "F", "con_telefono": False,
                                              "faltan": ["cedula"]}},
              {"tipo": "capas", "calor": True, "puntos": False},
              {"tipo": "base", "base": "satelite"},
              {"tipo": "hexagono", "tamano": 400},
              {"tipo": "recorrido", "nombre": "casco"},
              {"tipo": "giro", "activo": False},
              {"tipo": "limpiar"})
    assert _navegador(r) == [
        {"tipo": "volar", "lugar": {"id": v["_id"], "nombre": "LA PAZ", "tipo": "vereda", "lat": v["lat"],
                                    "lon": v["lon"], "poligono": True}, "zoom": 13, "pitch": 40},
        {"tipo": "filtros", "valores": {"zona": "rural", "sexo": "F", "con_telefono": "0", "sin_cedula": "1"},
         "reemplazar": True},
        {"tipo": "capas", "valores": {"calor": True, "puntos": False}},
        {"tipo": "base", "base": "satelite"},
        {"tipo": "hexagono", "tamano": "400"},
        {"tipo": "recorrido", "nombre": "casco"},
        {"tipo": "giro", "activo": False},
        {"tipo": "limpiar", "todo": False},
    ]
    aplicadas = r.contenido["aplicadas"]
    assert [a["tipo"] for a in aplicadas] == ["volar", "filtros", "capas", "base", "hexagono", "recorrido", "giro",
                                              "limpiar"]
    assert aplicadas[0]["lugar"]["id"] == v["_id"] and aplicadas[1]["personas"] == 2 and aplicadas[1]["ubicadas"] == 2
    assert r.personas == set() and r.resumen.startswith("Volé a La Paz")
    _sin_coordenadas_ni_nombres(r, "RURAL INVENTADA", coords=(v["lat"], 6.861))
    # Volar a un punto y un resalte de un lugar con color
    r = _mapa(sesion, ctx_de(sesion), {"tipo": "volar", "lat": 7.0, "lon": -73.9, "bearing": -20},
              {"tipo": "filtros", "valores": {}, "reemplazar": True},
              {"tipo": "resaltar", "lugar": "Tres de Octubre", "color": "#E3141B", "sumar": True})
    barrio = _lugar(db, "TRES DE OCTUBRE", "barrio")
    assert _navegador(r) == [
        {"tipo": "volar", "lat": 7.0, "lon": -73.9, "bearing": -20},
        {"tipo": "filtros", "valores": {}, "reemplazar": True},
        {"tipo": "resaltar", "puntos": [{"lat": barrio["lat"], "lon": barrio["lon"], "etiqueta": "TRES DE OCTUBRE"}],
         "color": "#E3141B", "encuadrar": True, "sumar": True},
    ]
    assert "Quité los filtros" in r.resumen


def test_las_cifras_salen_de_mapa_puntos(sesion, ctx_de):
    db = sesion.app.state.db
    vereda = _lugar(db, "LA PAZ", "vereda")["_id"]
    persona(db, nombre="RURAL UBICADA UNO", zona="rural", lugar_id=vereda, lat=6.861, lon=-74.141)
    persona(db, nombre="RURAL UBICADA DOS", zona="rural", lugar_id=vereda, lat=6.862, lon=-74.142)
    persona(db, nombre="RURAL SIN PUNTO", zona="rural", lugar_id=vereda)
    persona(db, nombre="URBANA INVENTADA", zona="urbana", lat=LAT, lon=LON)
    ctx = ctx_de(sesion)
    r = _mapa(sesion, ctx, {"tipo": "filtros", "valores": {"zona": "rural"}})
    a = r.contenido["aplicadas"][0]
    assert (a["personas"], a["ubicadas"]) == (3, 2) and "3 personas, 2 con ubicación" in r.resumen
    assert a["filtros"] == {"zona": "rural"} and "aviso" not in a
    # Ninguna con ubicación: se dice que no se verán (y cómo verlas)
    a = _mapa(sesion, ctx, {"tipo": "filtros", "valores": {"precision": "sin"}}).contenido["aplicadas"][0]
    assert (a["personas"], a["ubicadas"]) == (1, 0) and "Habitantes" in a["aviso"]
    # Sumados a los del mapa: el servidor no conoce los que ya tenía, y lo dice
    a = _mapa(sesion, ctx, {"tipo": "filtros", "valores": {"sexo": "F"}, "reemplazar": False}).contenido["aplicadas"][0]
    assert "nota" in a and r.personas == set()
    # Volar a un lugar cuenta sus personas con los filtros que reemplazan en la misma llamada
    r = _mapa(sesion, ctx, {"tipo": "filtros", "valores": {"precision": "ubicada"}},
              {"tipo": "volar", "lugar_id": vereda})
    v = r.contenido["aplicadas"][1]
    assert (v["personas_del_lugar"], v["ubicadas"]) == (2, 2)
    v = _mapa(sesion, ctx, {"tipo": "volar", "lugar_id": vereda}).contenido["aplicadas"][0]
    assert (v["personas_del_lugar"], v["ubicadas"]) == (3, 2)


# ───────────────────────────── Resaltar personas ─────────────────────────────

def test_resaltar_nombres_y_coordenadas_solo_al_navegador(sesion, ctx_de):
    db = sesion.app.state.db
    ubicadas = [persona(db, nombre=f"ROSENDA INVENTADA PUNTO {i}", lat=round(7.001 + i / 1000, 6),
                        lon=round(-73.901 - i / 1000, 6), cedula=f"9400012{i}") for i in range(3)]
    sin_punto = persona(db, nombre="ROSENDA INVENTADA SIN PUNTO")
    ctx = ctx_de(sesion)
    r = _mapa(sesion, ctx, {"tipo": "resaltar", "persona_ids": [*ubicadas, sin_punto, 999999, ubicadas[0]],
                            "color": "#e3141b"})
    assert _navegador(r) == [{"tipo": "resaltar", "puntos": [
        {"id": pid, "lat": round(7.001 + i / 1000, 6), "lon": round(-73.901 - i / 1000, 6),
         "etiqueta": f"ROSENDA INVENTADA PUNTO {i}"} for i, pid in enumerate(ubicadas)],
        "color": "#e3141b", "encuadrar": True, "sumar": False}]
    assert r.contenido["aplicadas"] == [{"tipo": "resaltar", "pedidas": 5, "resaltadas": 3,
                                         "sin_ubicacion": [sin_punto, 999999]}]
    assert r.personas == {*ubicadas, sin_punto, 999999} and r.resumen == "Resalté 3 de 5 (2 sin ubicación)"
    _sin_coordenadas_ni_nombres(r, "ROSENDA", "9400012", coords=(7.001, 7.002, -73.901, -73.902))
    # Sin etiquetas: solo los puntos, sumados a lo que ya había y sin mover la cámara
    r = _mapa(sesion, ctx, {"tipo": "resaltar", "persona_ids": ubicadas[:1], "etiquetas": False, "sumar": True,
                            "encuadrar": False})
    assert _navegador(r) == [{"tipo": "resaltar", "puntos": [{"id": ubicadas[0], "lat": 7.001, "lon": -73.901}],
                              "encuadrar": False, "sumar": True}]
    # Nadie con punto: no hay nada que resaltar y no se mueve nada
    e = _falla(sesion, ctx, "mapa", {"acciones": [{"tipo": "base", "base": "oscuro"},
                                                  {"tipo": "resaltar", "persona_ids": [sin_punto]}]})
    assert e.codigo == "sin_ubicacion" and e.detalle["accion"] == 2 and e.detalle["sin_ubicacion"] == [sin_punto]
    # Una vereda: se encuadra completa y su punto lleva el nombre
    v = _lugar(db, "LA PAZ", "vereda")
    r = _mapa(sesion, ctx, {"tipo": "resaltar", "lugar": "La Paz", "tipo_lugar": "vereda"})
    assert _navegador(r) == [
        {"tipo": "volar", "lugar": {"id": v["_id"], "nombre": "LA PAZ", "tipo": "vereda", "lat": v["lat"],
                                    "lon": v["lon"], "poligono": True}},
        {"tipo": "resaltar", "puntos": [{"lat": v["lat"], "lon": v["lon"], "etiqueta": "LA PAZ"}], "encuadrar": False,
         "sumar": False}]


# ───────────────────────────── Lugares: homónimos e inexistentes ─────────────────────────────

def test_homonimos_e_inexistentes_no_mueven_nada(sesion, ctx_de):
    db = sesion.app.state.db
    barrio, vereda = _lugar(db, "LA PAZ", "barrio"), _lugar(db, "LA PAZ", "vereda")
    tigre = {t: _lugar(db, "SAN MIGUEL DEL TIGRE", t) for t in ("centro_poblado", "vereda", "corregimiento")}
    ctx = ctx_de(sesion)
    # «La Paz» es un barrio del casco y una vereda: vuelve con los candidatos y no se aplica nada (tampoco los filtros)
    e = _falla(sesion, ctx, "mapa", {"acciones": [{"tipo": "filtros", "valores": {"zona": "rural"}},
                                                  {"tipo": "volar", "lugar": "La Paz"}]})
    assert e.codigo == "ambiguo" and e.detalle["accion"] == 2 and e.mensaje.startswith("Acción 2 (volar):")
    assert {c["id"]: c["tipo"] for c in e.detalle["candidatos"]} == {barrio["_id"]: "barrio", vereda["_id"]: "vereda"}
    assert all(set(c) == {"id", "nombre", "tipo", "zona", "padre", "tiene_punto", "tiene_poligono"}
               for c in e.detalle["candidatos"])
    # Con el tipo (o la palabra «vereda») ya no hay duda
    for accion in ({"tipo": "volar", "lugar": "La Paz", "tipo_lugar": "vereda"},
                   {"tipo": "volar", "lugar": "vereda la paz"}, {"tipo": "volar", "lugar_id": vereda["_id"]}):
        assert _navegador(_mapa(sesion, ctx, accion))[0]["lugar"]["id"] == vereda["_id"]
    # «San Miguel del Tigre»: el mismo sitio en tres niveles; vuela al más preciso y le cuenta al modelo los otros
    r = _mapa(sesion, ctx, {"tipo": "volar", "lugar": "San Miguel del Tigre"})
    lugar = _navegador(r)[0]["lugar"]
    assert (lugar["id"], lugar["tipo"], lugar["poligono"]) == (tigre["centro_poblado"]["_id"], "centro_poblado", False)
    assert {x["id"] for x in r.contenido["aplicadas"][0]["mismo_nombre"]} == {tigre["vereda"]["_id"],
                                                                              tigre["corregimiento"]["_id"]}
    for texto, t in (("vereda San Miguel del Tigre", "vereda"),
                     ("corregimiento san miguel del tigre", "corregimiento")):
        lugar = _navegador(_mapa(sesion, ctx, {"tipo": "volar", "lugar": texto}))[0]["lugar"]
        assert (lugar["id"], lugar["poligono"]) == (tigre[t]["_id"], True)
    r = _mapa(sesion, ctx, {"tipo": "volar", "lugar": "san migel del tigre"})  # con un error de escritura
    assert r.contenido["aplicadas"][0]["entendido_como"] == "SAN MIGUEL DEL TIGRE"
    # El barrio La Paz no tiene punto ni polígono: no se puede mostrar
    e = _falla(sesion, ctx, "mapa", {"acciones": [{"tipo": "volar", "lugar": "barrio La Paz"}]})
    assert e.codigo == "sin_ubicacion" and e.detalle["lugar"]["id"] == barrio["_id"]
    # Un lugar que no existe: sugerencias del nomenclátor
    e = _falla(sesion, ctx, "mapa", {"acciones": [{"tipo": "volar", "lugar": "Las Margaritas"}]})
    assert e.codigo == "no_existe" and e.detalle["sugerencias"] and e.detalle["accion"] == 1
    assert _falla(sesion, ctx, "mapa", {"acciones": [{"tipo": "volar", "lugar_id": 999999}]}).codigo == "no_existe"


@pytest.mark.parametrize("accion", [
    {"tipo": "filtros", "valores": {"lista": "Lista A"}}, {"tipo": "filtros", "valores": {"q": "ana"}},
    {"tipo": "filtros", "valores": {"fuente": "cedulas"}}, {"tipo": "filtros", "valores": {"regimen_salud": "Ninguno"}},
    {"tipo": "filtros", "valores": {"ids": "1,2"}}, {"tipo": "filtros", "valores": {"area_id": 1}},
    {"tipo": "filtros", "valores": {"poligono": "1,2;3,4;5,6"}}, {"tipo": "filtros", "valores": {"mios": True}},
    {"tipo": "filtros", "valores": {"lider": True}}, {"tipo": "filtros", "valores": {"zona": "marte"}},
    {"tipo": "filtros", "valores": {"sexo": "F"}, "reemplazar": "a veces"},
    {"tipo": "volar"}, {"tipo": "volar", "lugar": "La Paz", "lat": 7.0, "lon": -73.9},
    {"tipo": "volar", "lat": 4.61, "lon": -74.08}, {"tipo": "volar", "lat": 7.0},
    {"tipo": "volar", "lugar_id": 74, "zoom": 25}, {"tipo": "volar", "lugar_id": 74, "pitch": 85},
    {"tipo": "volar", "lugar": "La Paz", "url": "https://ejemplo.invalid"}, {"tipo": "volar", "tipo_lugar": "vereda"},
    {"tipo": "capas"}, {"tipo": "capas", "satelite": True}, {"tipo": "capas", "calor": "quizás"},
    {"tipo": "base", "base": "calles"}, {"tipo": "hexagono", "tamano": 300}, {"tipo": "recorrido", "nombre": "bogota"},
    {"tipo": "giro"}, {"tipo": "resaltar"}, {"tipo": "resaltar", "persona_ids": [1], "color": "rojo"},
    {"tipo": "resaltar", "persona_ids": list(range(1, 502))}, {"tipo": "resaltar", "persona_ids": [True]},
    {"tipo": "resaltar", "persona_ids": []}, {"tipo": "resaltar", "puntos": [{"lat": 7.0, "lon": -73.9}]},
    {"tipo": "zona"}, {"tipo": "zona", "area_id": 1, "cerrar": True}, {"tipo": "teletransportar"}, {},
])
def test_acciones_y_filtros_invalidos_se_rechazan(accion):
    with pytest.raises(ValidationError):
        H["mapa"].validar({"acciones": [accion]})


def test_cuantas_acciones_y_etiquetas_sensibles(sesion, ctx_de):
    for acciones in ([], [{"tipo": "limpiar"}] * 9):
        with pytest.raises(ValidationError):
            H["mapa"].validar({"acciones": acciones})
    with pytest.raises(ValidationError):
        H["mapa"].validar({"acciones": [{"tipo": "limpiar"}], "extra": 1})
    assert len(H["mapa"].validar({"acciones": [{"tipo": "limpiar"}] * 8}).acciones) == 8
    db = sesion.app.state.db
    lider = db.etiquetas.find_one({"nombre": "Líder comunitario"})["_id"]
    e = _falla(sesion, ctx_de(sesion), "mapa", {"acciones": [{"tipo": "filtros", "valores": {"etiqueta": lider}}]})
    assert e.codigo == "permiso" and e.detalle["accion"] == 1


# ───────────────────────────── Zona ─────────────────────────────

def test_zona_de_un_area_o_de_una_vereda(sesion, ctx_de):
    db = sesion.app.state.db
    aid = sesion.post("/api/areas", json={"nombre": "Zona inventada del mapa", "poligono": CUADRO}).json()["id"]
    persona(db, nombre="DENTRO DE LA ZONA", lat=LAT, lon=LON)
    persona(db, nombre="FUERA DE LA ZONA", lat=6.86, lon=-74.14)
    ctx = ctx_de(sesion)
    r = _mapa(sesion, ctx, {"tipo": "zona", "area_id": aid})
    assert _navegador(r) == [{"tipo": "zona", "area_id": aid}]
    z = r.contenido["aplicadas"][0]
    assert z["area"] == {"id": aid, "nombre": "Zona inventada del mapa"} and z["personas_dentro"] == 1
    e = _falla(sesion, ctx, "mapa", {"acciones": [{"tipo": "zona", "area_id": 9999}]})
    assert e.codigo == "no_existe" and e.detalle["areas"] == [{"id": aid, "nombre": "Zona inventada del mapa"}]
    v = _lugar(db, "LA PAZ", "vereda")
    assert _navegador(_mapa(sesion, ctx, {"tipo": "zona", "lugar": "vereda La Paz"})) == [
        {"tipo": "zona", "lugar_id": v["_id"]}]
    # Del mismo sitio en varios niveles se abre el que tiene polígono (la vereda, no el centro poblado)
    tigre = _lugar(db, "SAN MIGUEL DEL TIGRE", "vereda")
    assert _navegador(_mapa(sesion, ctx, {"tipo": "zona", "lugar": "San Miguel del Tigre"})) == [
        {"tipo": "zona", "lugar_id": tigre["_id"]}]
    # Un lugar sin polígono no se abre como zona
    barrio = _lugar(db, "TRES DE OCTUBRE", "barrio")
    e = _falla(sesion, ctx, "mapa", {"acciones": [{"tipo": "zona", "lugar_id": barrio["_id"]}]})
    assert e.codigo == "invalido"
    assert _navegador(_mapa(sesion, ctx, {"tipo": "zona", "cerrar": True})) == [{"tipo": "zona", "cerrar": True}]


# ───────────────────────────── abrir_vista ─────────────────────────────

def _navegar(r: Resultado) -> str:
    assert len(r.acciones) == 1 and set(r.acciones[0]) == {"tipo", "ruta"} and r.acciones[0]["tipo"] == "navegar"
    assert r.contenido["ruta"] == r.acciones[0]["ruta"]
    return r.acciones[0]["ruta"]


def _partes(ruta: str) -> tuple[str, dict]:
    u = urlsplit(ruta)
    return u.path, {k: v[0] for k, v in parse_qs(u.query).items()}


def test_abrir_vista_rutas_por_rol(sesion, como, ctx_de):
    db = sesion.app.state.db
    vereda = _lugar(db, "LA PAZ", "vereda")["_id"]
    aid = sesion.post("/api/areas", json={"nombre": "Zona inventada", "poligono": CUADRO}).json()["id"]
    ctx = ctx_de(sesion)
    casos = [
        ({"vista": "panel"}, "/", {}), ({"vista": "mapa"}, "/mapa", {}), ({"vista": "habitantes"}, "/personas", {}),
        ({"vista": "ficha", "id": 12}, "/personas/12", {}), ({"vista": "reuniones"}, "/reuniones", {}),
        ({"vista": "reunion", "id": 5}, "/reuniones/5", {}), ({"vista": "calidad"}, "/calidad", {}),
        ({"vista": "calidad", "pestana": "solicitudes"}, "/calidad", {"p": "solicitudes"}),
        ({"vista": "trabajo"}, "/trabajo", {}), ({"vista": "trabajo", "uid": 7}, "/trabajo", {"uid": "7"}),
        ({"vista": "trabajo", "uid": 0}, "/trabajo", {}), ({"vista": "usuarios"}, "/usuarios", {}),
        ({"vista": "usuarios", "id": 3}, "/usuarios/3", {}), ({"vista": "ajustes"}, "/ajustes", {}),
        ({"vista": "importar"}, "/importar", {}), ({"vista": "cuenta"}, "/cuenta", {}),
        ({"vista": "habitantes", "filtros": {"zona": "rural", "faltan": ["cedula"], "consentimiento": "si"},
          "q": "ana maria", "orden": "-completitud"}, "/personas",
         {"zona": "rural", "sin_cedula": "1", "consentimiento": "si", "q": "ana maria", "orden": "-completitud"}),
        ({"vista": "habitantes", "ids": [3, 1, 3], "area_id": aid}, "/personas", {"ids": "3,1", "area_id": str(aid)}),
        ({"vista": "mapa", "filtros": {"lugar": "vereda La Paz", "precision": "ubicada"}}, "/mapa",
         {"lugar_id": str(vereda), "precision": "ubicada"}),
        ({"vista": "mapa", "area_id": aid}, "/mapa", {"area_id": str(aid)}),
    ]
    for entrada, camino, query in casos:
        r = _ej(sesion, ctx, "abrir_vista", entrada)
        assert _partes(_navegar(r)) == (camino, query), entrada
        assert r.resumen.startswith("Abrí ") and r.personas == set()
    # El planillero: sin panel ni mapa ni usuarios; Habitantes sin los filtros vedados para su rol
    p = ctx_de(como("planillero", asignacion={"lugares": [], "areas": []}))
    for vista in ("panel", "mapa", "usuarios", "ajustes", "importar", "calidad"):
        e = _falla(sesion, p, "abrir_vista", {"vista": vista})
        assert (e.codigo, e.estado) == ("permiso", 403), vista
    assert "Mi trabajo" in _falla(sesion, p, "abrir_vista", {"vista": "panel"}).mensaje
    assert _partes(_navegar(_ej(sesion, p, "abrir_vista", {"vista": "habitantes", "filtros": {"zona": "rural"}}))) == (
        "/personas", {"zona": "rural"})
    for entrada in ({"vista": "habitantes", "filtros": {"creado_por": 3}}, {"vista": "habitantes", "ids": [1]},
                    {"vista": "habitantes", "filtros": {"menor": True}}, {"vista": "habitantes", "area_id": aid},
                    {"vista": "trabajo", "uid": 7}):
        assert _falla(sesion, p, "abrir_vista", entrada).codigo == "permiso", entrada
    assert _navegar(_ej(sesion, p, "abrir_vista", {"vista": "ficha", "id": 9})) == "/personas/9"
    # El consultor: no lista Habitantes ni ve reuniones; sí su trabajo y las fichas de su trabajo
    c = ctx_de(como("consultor"))
    for vista in ("habitantes", "reuniones"):
        assert _falla(sesion, c, "abrir_vista", {"vista": vista}).codigo == "permiso", vista
    assert _navegar(_ej(sesion, c, "abrir_vista", {"vista": "trabajo"})) == "/trabajo"
    # Lo que Habitantes no lee de su URL no se manda
    e = _falla(sesion, ctx, "abrir_vista", {"vista": "habitantes", "filtros": {"tratables": True}})
    assert e.codigo == "invalido" and "tratables" in e.mensaje
    # Lugares dudosos en los filtros: candidatos, sin navegar
    assert _falla(sesion, ctx, "abrir_vista", {"vista": "mapa", "filtros": {"lugar": "La Paz"}}).codigo == "ambiguo"


@pytest.mark.parametrize("entrada", [
    {"vista": "ficha"}, {"vista": "reunion"}, {"vista": "panel", "id": 3}, {"vista": "reuniones", "filtros": {}},
    {"vista": "reuniones", "q": "ana"}, {"vista": "mapa", "q": "ana"}, {"vista": "mapa", "ids": [1]},
    {"vista": "calidad", "pestana": "otra"}, {"vista": "habitantes", "pestana": "solicitudes"},
    {"vista": "exportar"}, {"vista": "habitantes", "orden": "edad"}, {"vista": "habitantes", "filtros": {"lista": "A"}},
    {"vista": "habitantes", "ruta": "https://ejemplo.invalid"}, {"vista": "ficha", "id": True},
    {"vista": "habitantes", "ids": list(range(1, 502))}, {"vista": "trabajo", "id": 3},
])
def test_abrir_vista_rechaza_entradas_invalidas(entrada):
    with pytest.raises(ValidationError):
        H["abrir_vista"].validar(entrada)


def _rutas_de_app_js() -> list[tuple[str, str]]:
    """(expresión de la ruta, permiso) de la tabla `RUTAS` de web/js/app.js, como expresiones de Python."""
    texto = (WEB / "app.js").read_text(encoding="utf-8")
    inicio = texto.index("const RUTAS = [")
    bloque = texto[inicio:texto.index("];", inicio)]
    filas = re.findall(r"\{ re: /(.+?)/, nav: '\w+', permiso: '([\w.]+)'", bloque)
    assert len(filas) >= 13
    return [(alt.replace("\\/", "/"), permiso) for patron, permiso in filas for alt in patron.split("|")]


def test_las_rutas_y_permisos_de_abrir_vista_son_los_de_app_js():
    rutas = _rutas_de_app_js()
    for clave, v in hi.VISTAS.items():
        ruta = v.ruta.replace("{id}", "12")
        assert [p for patron, p in rutas if re.fullmatch(patron, ruta)] == [v.permiso], clave
    assert [p for patron, p in rutas if re.fullmatch(patron, "/usuarios/3")] == ["usuarios.gestionar"]
    # La copia de las rutas en Python es la tabla de app.js (sin «/panel», que es la misma vista que «/»)
    assert set(hi.RUTAS_PANEL) == {patron for patron, _ in rutas if patron != "^/panel$"}


def test_los_filtros_de_habitantes_son_los_que_lee_personas_js():
    texto = (WEB / "vistas" / "personas.js").read_text(encoding="utf-8")
    cuerpo = re.search(r"const FILTROS = \[(.*?)\];", texto, re.S).group(1)
    base, sin = cuerpo.split("...", 1)
    claves = set(re.findall(r"'(\w+)'", base)) | {f"sin_{c}" for c in re.findall(r"'(\w+)'", sin)}
    assert hi.DE_HABITANTES == claves


# ───────────────────────────── Un turno completo por el bucle ─────────────────────────────

def test_turno_completo_el_mapa_llega_al_navegador_y_al_modelo_solo_el_resumen(sesion):
    db = sesion.app.state.db
    pid = persona(db, nombre="EVARISTA INVENTADA DEL MAPA", lat=7.0071, lon=-73.9081)
    falsa = aa.encender(sesion.app,
                        aa.sse(aa.TU("toolu_mapa1", "mapa", {"acciones": [{"tipo": "resaltar", "persona_ids": [pid]}]}),
                               stop="tool_use"),
                        aa.sse(aa.T("Listo: quedó resaltada en el mapa.")))
    r, ev = aa.enviar(sesion, "Resalta en el mapa a la persona de la ficha abierta")
    assert r.status_code == 200, r.text
    assert [e["accion"] for e in ev if e["tipo"] == "accion"] == [{"tipo": "mapa", "acciones": [
        {"tipo": "resaltar", "puntos": [{"id": pid, "lat": 7.0071, "lon": -73.9081,
                                         "etiqueta": "EVARISTA INVENTADA DEL MAPA"}],
         "encuadrar": True, "sumar": False}]}]
    assert [e["estado"] for e in ev if e["tipo"] == "herramienta"] == ["inicio", "ok"]
    assert ev[-1] == {"tipo": "fin", "motivo": "listo", **({"limite": ev[-1]["limite"]} if "limite" in ev[-1] else {})}
    # Lo que volvió al modelo (la segunda petición): el resumen, sin el nombre ni las coordenadas
    resultado = json.dumps(falsa.peticiones[1]["json"]["messages"][-1], ensure_ascii=False)
    assert "tool_result" in resultado and "toolu_mapa1" in resultado
    assert "EVARISTA" not in resultado and "7.0071" not in resultado and "-73.9081" not in resultado
    # La conversación recuerda a quién se resaltó (para borrarla si se suprime)
    conv = db.agente_conversaciones.find_one({})
    assert pid in (conv or {}).get("personas", [])
