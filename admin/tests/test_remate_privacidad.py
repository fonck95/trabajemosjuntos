"""Remate de la privacidad del asistente tras la revisión de sus arreglos: lo que sale del panel hacia el modelo.

* El lugar escrito a mano (`lugar_texto`, que la API pone como `lugar` cuando la ficha no tiene un barrio o vereda del
  nomenclátor) pasa por las máscaras en las filas, y de quien no autorizó solo va su barrio o vereda del nomenclátor:
  en la búsqueda, las parecidas, la cola de llamadas, los asistentes de una reunión y la ficha.
* Las máscaras tapan también los teléfonos y las cédulas escritos con separadores espaciados o mezclados («604 - 832
  12 34», «300 – 111 – 22 33», dos espacios), sin tapar las direcciones, las fechas ni los periodos escritos igual.
* El contexto del panel: la ruta va sin la consulta ni el fragmento y solo si es una del panel; la vista, solo con los
  nombres del menú; y el filtro de etiqueta, solo si la etiqueta existe y no es sensible.

Cada prueba falla sin el arreglo y pasa con él, salvo las que cuidan que no se tape de más (direcciones, fechas y
periodos) y los casos de rutas que ya se descartaban (las que no empiezan por «/»). Solo datos inventados; nunca se
llama a Anthropic ni a Mnemo."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import ayudas_agente as aa
from ayudas_agente import T, encender, enviar, sse
from ayudas_g3 import autorizada, persona
from app import db as bd
from app.agente import conversaciones as conv_db
from app.agente import minimizar, sistema
from app.agente.herramientas import gestion as hg
from app.agente.herramientas import personas as hp

H = {h.nombre: h for h in hp.HERRAMIENTAS + hg.HERRAMIENTAS}
AHORA = datetime(2026, 11, 9, 15, 0, tzinfo=timezone.utc)
WEB = Path(__file__).resolve().parent.parent / "web" / "js"
TEL, CORREO = "3001112233", "luis.inventado@ejemplo.co"
# Un `lugar_texto` como los que deja una planilla: el sitio, un celular y un correo
LIBRE = f"FINCA EL PORVENIR KM 3, CEL 300 111 22 33, {CORREO}"
TAPADO = "FINCA EL PORVENIR KM 3, CEL ···233, [correo]"
VEREDA = "VEREDA INVENTADA DEL REMATE"
FORMA_NO_AUTORIZO = {"id", "nombre", "lugar", "consentimiento", "aviso"}


def _filtros(t: str) -> dict:
    """Los «Filtros de la URL» de un contexto del panel ({} si no hay)."""
    linea = next((x for x in t.split("\n") if x.startswith("Filtros de la URL: ")), None)
    return json.loads(linea.split(": ", 1)[1]) if linea else {}


# ───────────────────────────── 1. El lugar libre ─────────────────────────────

def test_el_lugar_de_las_filas_pasa_por_las_mascaras():
    """El `lugar` de una fila es el nombre del barrio o vereda o, sin él, el texto libre de la ficha: pasa por las
    máscaras como la dirección o las observaciones. Antes iba tal cual (con el celular y el correo)."""
    fila = {"id": 4, "nombre": "ANA INVENTADA", "consentimiento": "si", "lugar": LIBRE, "lugar_tipo": None}
    assert minimizar.fila(fila)["lugar"] == TAPADO
    assert minimizar.filas([fila])[0]["lugar"] == TAPADO
    assert minimizar.fila({**fila, "lugar": "LA PAZ", "lugar_tipo": "vereda"})["lugar"] == "LA PAZ"
    assert minimizar.fila({**fila, "lugar": None})["lugar"] is None


@pytest.mark.parametrize("d, lugares, esperado", [
    # Fila del administrador o del coordinador: `lugar_tipo` dice si `lugar` es del nomenclátor
    ({"lugar": VEREDA, "lugar_tipo": "vereda"}, None, VEREDA),
    ({"lugar": LIBRE, "lugar_tipo": None}, None, None),
    # Su ficha (administrador y coordinador): el barrio o vereda, nunca el texto libre
    ({"lugar_nombre": VEREDA, "lugar_tipo": "vereda", "lugar_texto": LIBRE}, None, VEREDA),
    ({"lugar_nombre": None, "lugar_tipo": None, "lugar_texto": LIBRE}, None, None),
    # Planillero y consultor: la API no dice si `lugar` es del nomenclátor; ante la duda, no va
    ({"cedula_ult3": "···567", "lugar": VEREDA, "abordaje": {"estado": "no_contactar"}}, None, None),
    ({"lugar": LIBRE}, None, None),
    # …salvo con los nombres del nomenclátor (`lugares_de`): el que es uno de ellos
    ({"lugar": VEREDA}, frozenset({VEREDA}), VEREDA),
    ({"lugar": LIBRE}, frozenset({VEREDA}), None),
    ({"lugar": f"{VEREDA} CEL {TEL}"}, frozenset({VEREDA}), None),
])
def test_de_quien_no_autorizo_va_solo_su_barrio_o_vereda_del_nomenclator(d, lugares, esperado):
    """De quien no autorizó al modelo le llega quién es y su barrio o vereda: el texto libre del lugar no lo es (y
    puede traer un número o una dirección). Antes `no_autorizo` mandaba `lugar_texto` entero."""
    d = {"id": 4, "nombre": "ANA INVENTADA", "consentimiento": "no", **d}
    for f in (minimizar.fila(d, lugares), minimizar.filas([d], lugares)[0],
              minimizar.ficha(d, minimizar.Sensibles(), lugares), minimizar.no_autorizo(d, lugares)):
        assert set(f) == FORMA_NO_AUTORIZO and f["lugar"] == esperado, f
        assert f["aviso"] == minimizar.AVISO_NO_AUTORIZO


def _lugar(db, nombre: str = VEREDA, tipo: str = "vereda") -> int:
    lid = bd.siguiente_id(db, "lugares")
    db.lugares.insert_one({"_id": lid, "nombre": nombre, "tipo": tipo, "zona": "rural", "lat": 6.95, "lon": -73.95,
                           "alias": [], "padre": None})
    return lid


@pytest.fixture
def gente(sesion):
    """SILVIA (autorizó, con un celular para la cola) y NICOLAS (no autorizó), sin barrio ni vereda reconocidos y con
    el texto libre; MARTA (no autorizó) en una vereda del nomenclátor y con un sitio escrito a mano."""
    db = sesion.app.state.db
    vereda = _lugar(db)
    silvia = persona(db, nombre="SILVIA SIAUTORIZO INVENTADA", lugar_id=None, lugar_texto=LIBRE,
                     telefono="3157770011")
    autorizada(db, silvia)
    nicolas = persona(db, nombre="NICOLAS NOAUTORIZO INVENTADO", consentimiento="no", lugar_id=None,
                      lugar_texto=LIBRE)
    marta = persona(db, nombre="MARTA NOAUTORIZO INVENTADA", consentimiento="no", lugar_id=vereda,
                    lugar_texto=f"FINCA LA ESPERANZA, CEL {TEL}")
    return SimpleNamespace(vereda=vereda, silvia=silvia, nicolas=nicolas, marta=marta)


def _ej(sesion, cli, nombre: str, entrada: dict, tid: str = "toolu_remate_priv"):
    ctx = aa.contexto(sesion.app, cli, tool_use_id=tid)
    try:
        return aa.correr(sesion, aa.ejecutar, H[nombre], ctx, entrada)
    finally:
        aa.correr(sesion, ctx.api.cerrar)


def _filas(r) -> dict[int, dict]:
    c = r.contenido
    filas = c.get("filas") or c.get("parecidas") or c.get("asistentes") or (c.get("cola") or {}).get("filas") or []
    return {f["id"]: f for f in filas}


def _sin_lo_libre(r, *ademas: str) -> None:
    """Lo que el modelo recibe de la herramienta no trae el celular ni el correo del lugar libre."""
    al_modelo = r.texto_para_modelo()
    for dato in (TEL, "300 111 22 33", "111 22 33", CORREO, *ademas):
        assert dato not in al_modelo, (dato, al_modelo)


def test_el_lugar_libre_no_llega_al_modelo_por_ningun_camino(sesion, como, gente):
    """De punta a punta por las herramientas: la búsqueda (rápida y con filtros), las parecidas, la cola del
    consultor, los asistentes de una reunión y la ficha. A SILVIA le llega el lugar con las máscaras; de NICOLAS y de
    MARTA, que no autorizaron, nada del texto libre (de MARTA, al administrador, su vereda)."""
    db = sesion.app.state.db
    p, c = como("planillero"), como("consultor")
    # La búsqueda rápida por el nombre, como el administrador y como el planillero
    for cli in (sesion, p):
        r = _ej(sesion, cli, "buscar_personas", {"q": "SILVIA SIAUTORIZO INVENTADA"})
        assert _filas(r)[gente.silvia]["lugar"] == TAPADO
        _sin_lo_libre(r)
        for pid, nombre in ((gente.nicolas, "NICOLAS NOAUTORIZO INVENTADO"),
                            (gente.marta, "MARTA NOAUTORIZO INVENTADA")):
            r = _ej(sesion, cli, "buscar_personas", {"q": nombre})
            fila = _filas(r)[pid]
            assert set(fila) <= FORMA_NO_AUTORIZO and fila["lugar"] in (None, VEREDA), fila
            _sin_lo_libre(r, "FINCA")
    # El administrador sabe que MARTA está en su vereda (su fila lo dice con `lugar_tipo`); de NICOLAS, nada
    r = _ej(sesion, sesion, "buscar_personas", {"filtros": {"consentimiento": "no"}})
    filas = _filas(r)
    assert filas[gente.marta]["lugar"] == VEREDA and filas[gente.nicolas]["lugar"] is None
    _sin_lo_libre(r, "FINCA")
    # La ficha de quien no autorizó: para el administrador, su vereda o nada; para el planillero, a lo sumo su vereda
    for cli in (sesion, p):
        for pid, esperado in ((gente.marta, VEREDA), (gente.nicolas, None)):
            r = _ej(sesion, cli, "ver_persona", {"persona_id": pid})
            assert set(r.contenido) == FORMA_NO_AUTORIZO
            assert r.contenido["lugar"] in ((esperado,) if cli is sesion else (None, esperado)), r.contenido
            _sin_lo_libre(r, "FINCA")
    # Las parecidas: por el nombre de quien no autorizó y por el de quien sí
    r = _ej(sesion, sesion, "personas_parecidas", {"nombre": "NICOLAS NOAUTORIZO INVENTADO"})
    assert _filas(r)[gente.nicolas]["lugar"] is None
    _sin_lo_libre(r, "FINCA")
    r = _ej(sesion, sesion, "personas_parecidas", {"nombre": "SILVIA SIAUTORIZO INVENTADA"})
    assert _filas(r)[gente.silvia]["lugar"] == TAPADO
    _sin_lo_libre(r)
    # La cola de llamadas del consultor
    r = _ej(sesion, c, "mi_trabajo", {"lista": "por_llamar"})
    assert _filas(r)[gente.silvia]["lugar"] == TAPADO
    _sin_lo_libre(r)
    # Los asistentes de una reunión
    rid = sesion.post("/api/reuniones", json={"titulo": "Reunión inventada del remate", "fecha": "2026-11-02"}).json()
    rid = rid["id"]
    assert sesion.post(f"/api/reuniones/{rid}/asistentes", json={"persona_id": gente.silvia}).status_code == 201
    r = _ej(sesion, sesion, "ver_reunion", {"reunion_id": rid, "asistentes": 10})
    assert _filas(r)[gente.silvia]["lugar"] == TAPADO
    _sin_lo_libre(r)
    # Los nombres del nomenclátor, para quien quiera reconocer el `lugar` de las filas de planilleros y consultores
    assert VEREDA in minimizar.lugares_de(db) and LIBRE not in minimizar.lugares_de(db)


# ───────────────────────────── 2. Las máscaras ─────────────────────────────

@pytest.mark.parametrize("texto, esperado", [
    ("Llamar al 300 - 111 - 2233", "Llamar al ···233"),
    ("cel 300 – 111 – 22 33", "cel ···233"),
    ("cel 300  111  2233", "cel ···233"),
    ("Tel 604 - 832 12 34", "Tel ···234"),
    ("tel (604) - 832 - 1234", "tel ···234"),
    ("+57 300 - 111 22 33", "···233"),
    ("CC 71 . 234 . 567", "CC ···567"),
    ("cédula 1 036 . 123 . 456", "cédula ···456"),
    ("300 -111- 22 33 y 310 444   55 66", "···233 y ···566"),
    ("el 07 / 11 / 2026, cel 300 - 111 - 2233", "el 07 / 11 / 2026, cel ···233"),
    ("el 2026 - 11 - 07: 604 - 832 12 34", "el 2026 - 11 - 07: ···234"),
])
def test_las_mascaras_tapan_numeros_con_separadores_espaciados_o_mezclados(texto, esperado):
    """Antes cada grupo quedaba con menos de 7 dígitos y no se tapaba, o se tapaba medio número («604 - ···234»)."""
    assert minimizar.texto_libre(texto) == esperado


@pytest.mark.parametrize("texto", [
    "calle 50 # 48 - 21", "Cra 7 # 12 - 45 apto 301", "Lote 3 - 4, manzana 12", "Tiene 3 hijos de 12 - 15 años",
    "Visita el 07 / 11 / 2026 a las 10:30", "Del 2026 - 11 - 07 al 2026 . 11 . 09",
    "el 7 . 11 . 2026 y el 7 - 11 - 2026", "Vivió en Bogotá 2018 - 2022 y 2023 – 2025", "Mesa 12 - 3, puesto 4 . 5",
])
def test_las_mascaras_dejan_direcciones_fechas_y_periodos_con_separadores_espaciados(texto):
    assert minimizar.texto_libre(texto) == texto


def test_dos_numeros_separados_por_una_barra_siguen_tapados_cada_uno():
    """Una barra con espacios separa dos números (no une sus grupos): cada uno se tapa por su lado, como antes."""
    assert minimizar.texto_libre("Tel: 300 - 111 22 33 / 310  444  55 66") == "Tel: ···233 / ···566"


# ───────────────────────────── 3. El contexto del panel ─────────────────────────────

def test_la_ruta_del_contexto_va_sin_consulta_ni_fragmento():
    """La ruta llegaba entera: con «?», la búsqueda por cédula o teléfono, la lista de origen y el liderazgo iban en
    «Vista abierta», aunque los mismos datos en `filtros` se descartaran."""
    t = sistema.contexto_del_panel({"ruta": f"/personas?q={TEL}&lista=Lista concejo Juana Inventada&lider=1#arriba",
                                    "vista": "personas"}, AHORA)
    assert "\nVista abierta: personas (/personas)\n" in t
    for dato in (TEL, "lista", "Juana", "lider", "arriba", "?", "#"):
        assert dato not in t, dato
    assert "Vista abierta: personas (/personas/12)" in sistema.contexto_del_panel(
        {"ruta": "/personas/12#notas", "vista": "personas"}, AHORA)
    assert "(/trabajo)" in sistema.contexto_del_panel({"ruta": "/trabajo?uid=7"}, AHORA)
    assert "Vista abierta: sin nombre (/)\n" in sistema.contexto_del_panel({"ruta": "/#mapa"}, AHORA)


@pytest.mark.parametrize("ruta", [
    "/api/personas", "/personas/12/sensibles", "/personas/abc", "/ruta-inventada", "//ejemplo.invalid/personas",
    "https://ejemplo.invalid/personas", f"/{TEL}", "/personas/12 CC 71234567", "personas", "/static/js/app.js",
    "/personas\n/12", f"?q={TEL}", f"#{TEL}", "/personas/" + "7" * 40, "",
])
def test_la_ruta_del_contexto_solo_vale_si_es_una_del_panel(ruta):
    t = sistema.contexto_del_panel({"ruta": ruta}, AHORA)
    assert "Vista abierta" not in t and "ejemplo" not in t and TEL not in t and "71234567" not in t, t


def test_la_vista_del_contexto_va_solo_con_los_nombres_del_menu():
    """La vista llegaba como texto libre (hasta 60 caracteres, también un número): ahora solo un nombre del menú."""
    t = sistema.contexto_del_panel({"ruta": "/personas", "vista": "CC 71234567"}, AHORA)
    assert "71234567" not in t and "CC" not in t and "Vista abierta: sin nombre (/personas)" in t
    for vista in ("Habitantes", "mnemo", "<b>panel</b>", "panel x", "personas\n", 7, None, ["panel"]):
        t = sistema.contexto_del_panel({"vista": vista}, AHORA)
        assert "Vista abierta" not in t, vista
    for vista in sistema.VISTAS_MENU:
        assert f"\nVista abierta: {vista}\n" in sistema.contexto_del_panel({"vista": vista}, AHORA)


def test_las_vistas_del_menu_son_las_de_app_js():
    """El widget manda la entrada marcada del menú (`data-nav`): las claves `nav` de la tabla de rutas de app.js."""
    texto = (WEB / "app.js").read_text(encoding="utf-8")
    assert sistema.VISTAS_MENU == set(re.findall(r"\bnav: '(\w+)'", texto))
    menu = re.search(r"const NAV = \[(.*?)\];", texto, re.S).group(1)
    assert sistema.VISTAS_MENU == set(re.findall(r"\['(\w+)', '", menu))


def test_el_filtro_de_etiqueta_va_solo_si_existe_y_no_es_sensible(sesion):
    db = sesion.app.state.db
    vivienda = db.etiquetas.find_one({"nombre": "Vivienda"})["_id"]
    lider = db.etiquetas.find_one({"nombre": "Líder comunitario"})["_id"]  # sensible por su nombre
    marcada = bd.siguiente_id(db, "etiquetas")
    db.etiquetas.insert_one({"_id": marcada, "nombre": "Etiqueta inventada sensible", "grupo": "Otras",
                             "sensible": True})
    validas = sistema.etiquetas_del_contexto(db)
    assert vivienda in validas and lider not in validas and marcada not in validas

    def etiqueta(valor, etiquetas):
        return _filtros(sistema.contexto_del_panel({"filtros": {"etiqueta": valor, "zona": "rural"}}, AHORA,
                                                   etiquetas)).get("etiqueta")

    assert etiqueta(str(vivienda), validas) == str(vivienda)
    for valor in (str(lider), str(marcada), "999999", "abc", f"{vivienda},{lider}", ""):
        assert etiqueta(valor, validas) is None, valor
    # Sin la lista de las que pueden ir (quien arma el contexto no la pasó), ninguna: ante la duda, no va
    assert etiqueta(str(vivienda), None) is None
    assert _filtros(sistema.contexto_del_panel({"filtros": {"etiqueta": str(vivienda)}}, AHORA)) == {}


def test_lo_que_recibe_y_guarda_el_modelo_no_lleva_la_consulta_la_vista_ni_la_etiqueta_sensible(sesion):
    """De punta a punta: la petición al modelo y el mensaje guardado (que se le reenvía en cada ronda)."""
    db = sesion.app.state.db
    lider = db.etiquetas.find_one({"nombre": "Líder comunitario"})["_id"]
    api = encender(sesion.app, sse(T("En la vista hay una búsqueda.")))
    contexto = {"ruta": f"/personas?q={TEL}&lista=Lista concejo Juana Inventada", "vista": "CC 71234567",
                "filtros": {"etiqueta": str(lider), "zona": "rural"}}
    r, ev = enviar(sesion, "¿Cuántas personas hay?", contexto=contexto)
    assert r.status_code == 200 and ev[-1]["motivo"] == "listo", ev
    enviado = json.dumps(api.peticiones[0]["json"]["messages"], ensure_ascii=False)
    guardado = json.dumps(list(db[conv_db.MENSAJES].find({}, {"_id": 0})), ensure_ascii=False, default=str)
    for texto in (enviado, guardado):
        assert "rural" in texto and "(/personas)" in texto and "¿Cuántas personas hay?" in texto
        for dato in (TEL, "Juana", "71234567", "etiqueta"):
            assert dato not in texto, dato
