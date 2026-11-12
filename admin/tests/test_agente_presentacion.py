"""El asistente presenta la propuesta 2028–2031: la herramienta `presentacion` (app/agente/herramientas/interfaz.py), el
guion (app/agente/guion.py y propuesta_guion.json), el puente del panel (web/js/agente-presentacion.js), la vista
/presentacion (web/js/vistas/presentacion.js) y el mando de la presentación (web/js/propuesta/mando.js del sitio).

* El guion versionado es el que sale de web/data/propuesta.json (si alguien cambia la propuesta sin regenerarlo, falla)
  y sus capítulos son los de `caps` en main.js, con sus nombres fijos y el paso «inicio» de un capítulo vacío. Cada
  paso trae lo que muestra (fuentes con nombre, qué financian y su requisito, a quién se pide, siguientes pasos, plazos,
  especificaciones y metas), y cada texto que la pantalla muestra llega ENTERO, igual que en web/data/propuesta.json.
* La herramienta: definición y esquema para la Messages API (sin `pattern` ni `format`), entradas inválidas (también
  explicaciones de más de 220 caracteres, con caracteres que no se ven, números largos escritos por grupos o «@», en su
  forma NFKC), que las cifras, los periodos y las fechas que existen sí pasan y que la herramienta, el puente y el mando
  deciden lo mismo con cada frase, el índice compacto, la forma exacta de cada acción del navegador, el destino de
  siguiente y anterior, los errores sin acciones (todo o nada), los roles (los cuatro) y que sin el guion no se ofrece.
  Un turno completo por el bucle con la Messages API simulada.
* El contexto del panel: el capítulo y el paso del navegador se validan contra el guion y el nombre y el título los pone
  el servidor.
* La CSP del panel (frame-src) y la del sitio (frame-ancestors con el origen del panel que escribe build_site.py).
* Con Node, sin navegador: el validador de la acción (`accionPresentacion`), el puente (cola, navegación, proyector por
  BroadcastChannel, el que se cerró sin avisar, el que se abre donde está la pestaña del chat y el que manda cuando su
  paso cambia allá, y mensajes del canal que no cumplen) y el mando (orígenes, también con mayúsculas o «:443», órdenes
  y datos que rechaza, subtítulo como texto).
* En Chromium, el panel de verdad con el sitio construido por build_site.py: el asistente (con su modelo simulado) manda
  `ir` y `explicar`, el iframe cambia de paso y muestra el subtítulo como texto, sin violaciones de CSP (tampoco dentro
  del iframe) y sin desborde, en 1400×900 (con el asistente abierto, el iframe le deja su ancho) y 390×844 (desde
  Habitantes: navega a la presentación y pliega el asistente). Y la explicación más larga (220 caracteres) se ve entera,
  sin tapar el panel, la leyenda ni el control, en 1400×900, 1024×768, 820×1180 y en el celular, en vertical (390×844,
  360×640, 320×568) y en horizontal (915×412, 844×390, 740×360, 667×375), donde tampoco tapa la franja en que la cámara
  encuadra la obra y el panel conserva su alto; entre 901 y 1199 px el asistente abierto no tapa la presentación; con
  cambios sin guardar, las órdenes de un turno dan un solo aviso cuyo botón las aplica todas; y la ventana del
  proyector y la pestaña del chat no se desfasan cuando el paso cambia en el proyector.
Solo datos inventados; nunca se llama a Anthropic ni a Mnemo.
"""
from __future__ import annotations

import dataclasses
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

import ayudas_agente as aa
from app import acceso, config, seguridad
from app.agente import bucle, guion, herramientas, sistema
from app.agente.herramientas import interfaz as hi
from app.agente.herramientas.base import ErrorHerramienta

ADMIN = Path(__file__).resolve().parents[1]
RAIZ = ADMIN.parent
JS = ADMIN / "web" / "js"
PROPUESTA_JSON = RAIZ / "web" / "data" / "propuesta.json"
MAIN_JS = RAIZ / "web" / "js" / "propuesta" / "main.js"
MANDO_JS = RAIZ / "web" / "js" / "propuesta" / "mando.js"
PUENTE_JS = JS / "agente-presentacion.js"
H = {h.nombre: h for h in hi.HERRAMIENTAS}
P = H["presentacion"]
G = guion.cargar()
AHORA = datetime(2026, 11, 9, 15, 0, tzinfo=timezone.utc)
PALABRAS_ESQUEMA = {"type", "properties", "required", "additionalProperties", "description", "enum", "items",
                    "minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems", "default", "anyOf"}


def _hay_node() -> bool:
    return bool(shutil.which("node"))


def _hay_playwright() -> bool:
    return _hay_node() and subprocess.run(
        ["node", "-e", "require(process.env.PLAYWRIGHT_MODULE || 'playwright')"], capture_output=True).returncode == 0


requiere_node = pytest.mark.skipif(not _hay_node() and not os.environ.get("CI"), reason="Sin Node")
requiere_navegador = pytest.mark.skipif(not _hay_playwright() and not os.environ.get("CI"),
                                        reason="Sin Node con Playwright (PLAYWRIGHT_MODULE o NODE_PATH)")


# ───────────────────────────── El guion ─────────────────────────────

@pytest.mark.skipif(not PROPUESTA_JSON.is_file(), reason="Sin web/data/propuesta.json (el panel desplegado aparte)")
def test_el_guion_versionado_es_el_que_sale_de_la_propuesta():
    """Si cambia data/propuesta/ y no se corre scripts/build_propuesta.py, el asistente explicaría otra cosa."""
    derivado = guion.derivar(json.loads(PROPUESTA_JSON.read_text(encoding="utf-8")))
    assert json.loads(guion.RUTA.read_text(encoding="utf-8")) == derivado, (
        "admin/app/agente/propuesta_guion.json está desfasado: corra python3 scripts/build_propuesta.py")
    assert guion.problemas(derivado) == []


@pytest.mark.skipif(not PROPUESTA_JSON.is_file(), reason="Sin web/data/propuesta.json")
def test_los_capitulos_son_los_de_main_js():
    """El orden, los ids y los nombres fijos de `caps` (main.js), los módulos en el orden de propuesta.json y el paso
    «inicio» de un capítulo sin pasos: el número de paso del asistente es el de la dirección de la presentación."""
    js = MAIN_JS.read_text(encoding="utf-8")
    bloque = js[js.index("const caps = ["):js.index("];", js.index("const caps = ["))]
    fijos = re.findall(r"\{ id: '(\w+)', nombre: '([^']+)', corto: '([^']+)', \.\.\.datos\.(\w+) \}", bloque)
    assert [(i, n, c) for i, n, c, _ in fijos] == [*guion.FIJOS_ANTES, *guion.FIJOS_DESPUES]
    assert all(i == d for i, _, _, d in fijos)
    assert bloque.index("'portada'") < bloque.index("...datos.modulos.map") < bloque.index("'financiacion'")
    assert "if (!c.pasos.length) c.pasos = [{ id: 'inicio', tipo: 'texto', titulo: c.nombre }]" in js
    datos = json.loads(PROPUESTA_JSON.read_text(encoding="utf-8"))
    esperados = ["portada", *[m["id"] for m in datos["modulos"]], "financiacion", "ruta", "pedidos"]
    assert [c["id"] for c in G.capitulos] == esperados
    for c in G.capitulos:
        fuente = next(m for m in datos["modulos"] if m["id"] == c["id"]) if c["id"] in esperados[1:-3] else \
            datos[c["id"]]
        pasos = [p for p in fuente.get("pasos") or [] if p] or [{"id": "inicio"}]
        assert [p["id"] for p in c["pasos"]] == [p["id"] for p in pasos], c["id"]
    # Lo de main.js que hace falta para el control remoto
    assert "import { montarMando } from './mando.js';" in js
    assert "montarMando({ caps, estado, ir, vecino, abrirIndice, reencuadrar });" in js
    assert "dispatchEvent(new CustomEvent('propuesta:paso'" in js
    assert re.search(r"function avanzar\(d\) \{\n  if \(tlTelon\?\.isActive\(\)\) \{ tlTelon\.progress\(1\); return; \}"
                     r"\n  const \[ci, pi\] = vecino\(estado\.ci, estado\.pi, d\);", js)


def test_los_textos_del_guion_son_planos_y_acotados():
    from app.agente.herramientas.base import MAX_CONTENIDO
    for c in G.capitulos:
        assert guion.ID.fullmatch(c["id"]) and 1 <= len(c["pasos"]) <= guion.MAX_PASOS
        for p in c["pasos"]:
            texto = json.dumps(p, ensure_ascii=False)
            assert not re.search(r"<[a-z/][^>]*>|\xa0|\U00002060|\xad", texto), (c["id"], p["id"])
            assert p["titulo"] and p["texto"], (c["id"], p["id"])
            # Lo que le llega al modelo de un paso, entero: muy por debajo de lo que la herramienta deja pasar
            assert guion.bytes_de(p) <= guion.MAX_BYTES_PASO <= MAX_CONTENIDO // 3, (c["id"], p["id"], guion.bytes_de(p))
    # Un paso que no cabe no se acorta: el guion no se puede usar y build_propuesta.py --estricto lo dice
    pesado = {"id": "a", "titulo": "A", "texto": "x" * guion.MAX_BYTES_PASO}
    assert guion.problemas({"capitulos": [{"id": "uno", "pasos": [pesado]}]}) == [
        f"uno/a: el paso pesa {guion.bytes_de(pesado)} bytes (el tope es {guion.MAX_BYTES_PASO})"]
    with pytest.raises(ValueError):
        guion.Guion.desde({"capitulos": [{"id": "uno", "pasos": [pesado]}]})


def _plano(v) -> str:
    """El texto como lo lee la persona en la pantalla, sin HTML ni espacios duros: lo que el guion debe traer entero.
    Se calcula aquí, sin `guion.plano`, para no comparar el guion consigo mismo."""
    import html as _html
    if not isinstance(v, str):
        return ""
    t = _html.unescape(re.sub(r"<[^>]*>", "", v))
    t = t.replace("\xa0", " ").replace("\u202f", " ").replace("\u2007", " ").replace("\u2060", "").replace("\xad", "")
    return " ".join(t.split())


def _en_pantalla(datos: dict, c: dict, p: dict) -> dict[str, list[str]]:
    """Los textos que muestra el paso `p` del capítulo `c` (`RENDER` de web/js/propuesta/main.js), por campo del
    guion, leídos de web/data/propuesta.json."""
    tipo = p.get("tipo") or "texto"
    x = next((k for k in c.get("componentes") or [] if k.get("id") == p.get("componente")), {}) \
        if tipo == "componente" else {}
    respaldo = {"portada": c.get("lema"), "portadilla": c.get("problema"), "componente": x.get("descripcion")}
    out: dict[str, list[str]] = {"texto": [_plano(p.get("texto") or respaldo.get(tipo))], "nota": [_plano(p.get("nota"))],
                                 "lista": [_plano(t) for t in p.get("lista") or []],
                                 "leyenda": [_plano(l.get("texto")) for l in p.get("leyenda") or []]}
    cifras = p.get("cifras") or (c.get("cifras") if tipo in ("portada", "portadilla") else None) or []
    out["cifras"] = [_plano(k.get(campo)) for k in cifras for campo in ("v", "l", "fuente")]
    if tipo == "portada":
        out["modulos"] = [_plano(m.get(campo)) for m in datos["modulos"] for campo in ("nombre", "lema")]
    elif tipo == "portadilla":
        out["propuesta"] = [_plano(c.get("propuesta"))]
        out["metas"] = [_plano(f"{m['indicador']}: {m.get('base') or '—'} → {m.get('meta') or '—'}")
                        for m in c.get("metas") or []]
    elif tipo == "componentes":
        out["componentes"] = [_plano(k.get(campo)) for k in c.get("componentes") or [] for campo in ("nombre", "resumen")]
    elif tipo == "componente":
        out["componente"] = [_plano(x.get(campo)) for campo in ("nombre", "resumen", "plazo", "ubicacion")]
        out["componente"] += [_plano(x.get("base_costo")) if x.get("costo") else ""]
        out["componente"] += [_plano(f"{k}: {v}") for k, v in x.get("especificaciones") or []]
        out["componente"] += [_plano(t.get("nombre")) for t in x.get("proyecto_tipo") or []]
    elif tipo == "comparacion":
        for lado in ("antes", "despues"):
            out[lado] = [" · ".join(t for t in (_plano((p.get(lado) or {}).get("titulo")),
                                                 _plano((p.get(lado) or {}).get("texto"))) if t)]
    elif tipo == "financiacion":
        g = c.get("gestion") or {}
        out["pedido"], out["madurez_nota"] = [_plano(g.get("pedido"))], [_plano(g.get("madurez_nota"))]
        out["a_quien"] = [_plano(t) for t in g.get("a_quien") or []]
        out["siguientes_pasos"] = [_plano(t) for t in g.get("pasos") or []]
        out["mezcla"] = [_plano(f.get("mecanismo")) for f in c.get("financiacion") or []]
        out["proyectos_tipo"] = [_plano(t.get("nombre")) for t in c.get("proyectos_tipo") or []]
    elif tipo == "fuentes":
        out["fuentes"] = [_plano(f.get(campo)) for f in c.get("fuentes") or []
                          for campo in ("nombre", "tipo", "que_financia", "requisito")]
    elif tipo == "ruta":
        out["hitos"] = [_plano(f"{h['fecha']}: {h['texto']}") for h in c.get("hitos") or []]
        out["fases"] = [_plano(f["nombre"]) for f in c.get("fases") or []]
    elif tipo == "pedidos":
        out["entidades"] = [_plano(e.get(campo)) for e in c.get("entidades") or [] for campo in ("entidad", "pedido")]
    return {k: [t for t in v if t] for k, v in out.items()}


def _capitulos_de(datos: dict) -> list[dict]:
    return [datos["portada"], *datos["modulos"], datos["financiacion"], datos["ruta"], datos["pedidos"]]


@pytest.mark.skipif(not PROPUESTA_JSON.is_file(), reason="Sin web/data/propuesta.json")
def test_el_guion_trae_enteros_los_textos_de_la_pantalla():
    """La herramienta le dice al modelo que el guion «es lo que muestra la presentación en ese paso» y que no invente:
    cada texto que la pantalla muestra (el texto del paso, la nota, la lista, las cifras con su rótulo y su fuente, lo
    que se pide, la madurez, a quién tocar, los siguientes pasos, cómo se accede a cada fuente, lo que financia cada una
    y su requisito, las especificaciones, la base del costo, dónde, el plazo, las metas, los hitos, la leyenda…) llega
    ENTERO, igual que en web/data/propuesta.json. Antes un tope de 3 KB por paso cortaba a media frase el texto de la
    financiación de saneamiento (de 457 a 89 caracteres), sus pedidos, los diez pedidos por entidad, la nota de los
    pedidos y 19 de los 20 textos de las fuentes, y la prueba lo aceptaba porque solo miraba el comienzo."""
    datos = json.loads(PROPUESTA_JSON.read_text(encoding="utf-8"))
    revisados = 0
    for cap, c in zip(_capitulos_de(datos), G.capitulos, strict=True):
        pasos = [p for p in cap.get("pasos") or [] if p] or [{"id": "inicio", "tipo": "texto", "titulo": c["nombre"]}]
        for p, g in zip(pasos, c["pasos"], strict=True):
            assert p["id"] == g["id"], (c["id"], p["id"])
            en_guion = set(_textos(g))
            for campo, textos in _en_pantalla(datos, cap, p).items():
                for t in textos:
                    revisados += 1
                    # La hoja de ruta pinta el nombre de cada fase sobre su barra; el guion le suma los años que abarca
                    entero = any(s.startswith(f"{t} (") for s in en_guion) if campo == "fases" else t in en_guion
                    assert entero, (c["id"], p["id"], campo, t)
            # El texto principal y la nota van en su campo, tal cual
            assert g["texto"] == _plano(p.get("texto") or {"portada": cap.get("lema"), "portadilla": cap.get("problema"),
                                                           "componente": next((k.get("descripcion") for k in
                                                                               cap.get("componentes") or []
                                                                               if k.get("id") == p.get("componente")),
                                                                              None)}.get(p.get("tipo"))), p["id"]
            assert g.get("nota", "") == _plano(p.get("nota")), p["id"]
            # Nada sale cortado: ningún texto del guion termina en «…» si no lo hace en la propuesta
            propios = {_plano(t) for t in _textos(cap)}
            assert not [t for t in en_guion if t.endswith("…") and t not in propios], (c["id"], p["id"])
    assert revisados > 1000, revisados

    def paso(cid, pid):
        ci = G.por_id(cid)
        return G.capitulos[ci]["pasos"][G.paso(ci, pid)]

    def modulo(mid):
        return next(m for m in datos["modulos"] if m["id"] == mid)

    # Los casos del verificador, uno por uno, con su largo entero (el texto de la financiación de saneamiento llegaba
    # con 89 caracteres; su pedido, con 93, y antes del tope de 3 KB, con 591 por el tope de 600 de cada texto)
    san = modulo("saneamiento")
    fin = next(p for p in san["pasos"] if p["id"] == "financiacion")
    f = paso("saneamiento", "financiacion")
    assert f["texto"] == _plano(fin["texto"]) and len(f["texto"]) == 457, len(f["texto"])
    assert "PTAR" in f["texto"] and "Res. 0467" in f["texto"] and "$1.747 M" in f["texto"]
    assert f["pedido"] == _plano(san["gestion"]["pedido"]) and len(f["pedido"]) == 681
    assert f["a_quien"] == [_plano(t) for t in san["gestion"]["a_quien"]] and len(f["a_quien"]) == 9
    assert f["siguientes_pasos"] == [_plano(t) for t in san["gestion"]["pasos"]] and len(f["siguientes_pasos"]) == 10
    relleno = next(p for p in san["pasos"] if p["id"] == "relleno_nuevo")
    comp = next(k for k in san["componentes"] if k["id"] == relleno["componente"])
    r = paso("saneamiento", "relleno_nuevo")
    assert r["texto"] == _plano(relleno.get("texto") or comp["descripcion"]) and len(r["texto"]) == 482
    assert r["componente"]["ubicacion"] == _plano(comp["ubicacion"]) and len(r["componente"]["ubicacion"]) == 611
    assert [k["l"] for k in r["cifras"]] == [_plano(k["l"]) for k in relleno["cifras"]]
    assert max(len(k["l"]) for k in r["cifras"]) == 108
    agro = paso("agroindustria", "financiacion")
    assert agro["pedido"] == _plano(modulo("agroindustria")["gestion"]["pedido"]) and len(agro["pedido"]) == 566
    assert agro["siguientes_pasos"] == [_plano(t) for t in modulo("agroindustria")["gestion"]["pasos"]]
    pedidos = G.capitulos[G.por_id("pedidos")]["pasos"][0]
    assert [e["pedido"] for e in pedidos["entidades"]] == [_plano(e["pedido"]) for e in datos["pedidos"]["entidades"]]
    assert len(pedidos["entidades"]) == 10 and pedidos["nota"] == _plano(datos["pedidos"]["pasos"][0]["nota"])
    assert len(pedidos["nota"]) == 370
    fuentes = paso("financiacion", "fuentes")["fuentes"]
    assert [(x["que_financia"], x["requisito"]) for x in fuentes] == [
        (_plano(x["que_financia"]), _plano(x["requisito"])) for x in datos["financiacion"]["fuentes"]]
    sgr = next(x for x in fuentes if x["nombre"].startswith("Sistema General de Regalías"))
    assert len(sgr["que_financia"]) == 264 and len(sgr["requisito"]) == 139


@pytest.mark.skipif(not PROPUESTA_JSON.is_file(), reason="Sin web/data/propuesta.json")
def test_el_guion_trae_lo_que_muestra_cada_paso():
    """Lo que antes faltaba del todo: las fuentes de financiación con su nombre, qué financian y su requisito, a quién
    se pide, los siguientes pasos, cómo se accede a cada fuente en cada módulo, los proyectos tipo, los plazos (antes se
    cortaban en 80 caracteres y perdían el año de la obra), las especificaciones, la base del costo, las fuentes de cada
    componente y las metas del módulo."""
    datos = json.loads(PROPUESTA_JSON.read_text(encoding="utf-8"))
    fuentes = {f["id"]: f for f in datos["financiacion"]["fuentes"]}
    fin = G.capitulos[G.por_id("financiacion")]
    paso = next(p for p in fin["pasos"] if p["tipo"] == "fuentes")
    assert [f["nombre"] for f in paso["fuentes"]] == [f["nombre"] for f in datos["financiacion"]["fuentes"]]
    assert all(f.get("que_financia") and f.get("requisito") and f.get("tipo") for f in paso["fuentes"]), paso
    for m in datos["modulos"]:
        c = G.capitulos[G.por_id(m["id"])]
        g = m["gestion"]
        f = next(p for p in c["pasos"] if p["tipo"] == "financiacion")
        assert f["a_quien"] == [_plano(t) for t in g["a_quien"]], m["id"]
        assert f["siguientes_pasos"] == [_plano(t) for t in g["pasos"]], m["id"]
        assert f["madurez"] == g["madurez"] and f["madurez_nota"] and f["pedido"] and f["mezcla"], m["id"]
        assert [x.get("mecanismo", "") for x in f["mezcla"]] == [_plano(x.get("mecanismo")) for x in m["financiacion"]]
        assert f.get("proyectos_tipo", []) == [_plano(t["nombre"]) for t in m.get("proyectos_tipo") or []], m["id"]
        portadilla = next(p for p in c["pasos"] if p["tipo"] == "portadilla")
        assert len(portadilla["metas"]) == len(m["metas"]), m["id"]
        assert portadilla["metas"][0].startswith(_plano(m["metas"][0]["indicador"]) + ": "), m["id"]
        for p in c["pasos"]:
            if p["tipo"] != "componente":
                continue
            x = next(k for k in m["componentes"] if _plano(k["nombre"]) == p["componente"]["nombre"])
            comp = p["componente"]
            assert comp.get("plazo", "") == _plano(x.get("plazo")), (m["id"], p["id"])
            assert comp.get("base_costo", "") == _plano(x.get("base_costo")), (m["id"], p["id"])
            assert comp["fuentes"] == [fuentes[i].get("corto") or fuentes[i]["nombre"] for i in x["fuentes"]], p["id"]
            assert comp["especificaciones"] == [_plano(f"{k}: {v}") for k, v in x["especificaciones"]], p["id"]
    # El plazo que se cortaba justo antes del año de la obra
    cano = G.capitulos[G.por_id("urbanismo")]["pasos"][G.paso(G.por_id("urbanismo"), "cano")]
    assert "obra en 2031" in cano["componente"]["plazo"]
    # Los pedidos, entidad por entidad, con los módulos que mueve cada uno
    pedidos = G.capitulos[G.por_id("pedidos")]["pasos"][0]
    assert [e["entidad"] for e in pedidos["entidades"]] == [_plano(e["entidad"]) for e in datos["pedidos"]["entidades"]]
    assert all(e.get("modulos") and e.get("pedido") for e in pedidos["entidades"])
    # El índice sigue compacto: solo ids, nombres y títulos
    assert len(json.dumps(G.indice(), ensure_ascii=False).encode("utf-8")) < 6000


def test_rangos_como_los_muestra_la_presentacion():
    """`fmtRango`, `fmtM` y `aprox` de main.js (comprobados a mano contra el navegador con los costos de la propuesta)."""
    assert guion.rango(54_321, 100_400) == "$54 – 100 mil M"
    assert guion.rango(77_000, 77_000) == "≈ $77,0 mil M"
    assert guion.rango(300, 850) == "$300 – 850 M"
    assert guion.rango(1_150_000, 1_400_000) == "$1,2 – 1,4 billones"
    assert guion.rango_de({"min": 2816.0, "central": 8444.4, "max": 14072.7}) == "$2,8 – 14 mil M"
    assert guion.rango_de({"central": 500}) == "≈ $500 M" and guion.rango_de(None) == ""
    assert guion.millones(999.5) == "$1.000 M" and guion.millones(2_500_000) == "$2,5 billones"
    assert guion.aproximado(116_294) == "≈ $120,0 mil M" and guion.aproximado(True) == ""
    assert guion.plano("<b>300</b>\xa0viviendas en 2028–\U00002060" + "2031  y más") == "300 viviendas en 2028–2031 y más"
    # Nunca acorta: lo que se ve en pantalla llega entero al modelo (el peso del paso lo mira `problemas`)
    assert guion.plano("palabra " * 2000) == ("palabra " * 2000).strip()


def test_buscar_capitulo_y_paso():
    assert G.capitulos[G.buscar("vivienda").indice]["id"] == "vivienda"
    assert G.capitulos[G.buscar("Cómo se FINANCIA").indice]["id"] == "financiacion"
    assert G.capitulos[G.buscar("financiación").indice]["id"] == "financiacion"
    assert G.capitulos[G.buscar("agua").indice]["id"] == "aguas"
    assert G.capitulos[G.buscar("hoja de ruta").indice]["id"] == "ruta"
    r = G.buscar("sa")  # salud y saneamiento
    assert r.indice is None and {G.capitulos[i]["id"] for i in r.candidatos} == {"salud", "saneamiento"}
    assert G.buscar("marte") == guion.Resolucion(None) and G.buscar("¿?") == guion.Resolucion(None)
    vi = G.por_id("vivienda")
    assert G.paso(vi, None) == 0 and G.paso(vi, 3) == 2 and G.paso(vi, "3") == 2 and G.paso(vi, "nuevas") == 2
    assert G.paso(vi, 0) is None and G.paso(vi, 99) is None and G.paso(vi, "noexiste") is None
    assert G.paso(vi, True) is None


def test_cargar_con_cache_y_archivo_danado(tmp_path):
    ruta = tmp_path / "guion.json"
    assert guion.cargar(ruta) is None
    ruta.write_text(guion.RUTA.read_text(encoding="utf-8"), encoding="utf-8")
    a = guion.cargar(ruta)
    assert a is guion.cargar(ruta) and len(a) == len(G)  # sin cambios, la misma (caché por fecha y tamaño)
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    datos["capitulos"] = datos["capitulos"][:2]
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    assert len(guion.cargar(ruta)) == 2
    ruta.write_text("{roto", encoding="utf-8")
    with pytest.raises(ValueError):
        guion.cargar(ruta)
    datos["capitulos"][0]["id"] = "Con Mayúsculas"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    with pytest.raises(ValueError):
        guion.cargar(ruta)


# ───────────────────────────── La herramienta ─────────────────────────────

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


def test_definicion_y_esquema():
    d = P.definicion()
    assert set(d) == {"name", "description", "input_schema", "eager_input_streaming"}
    assert d["name"] == "presentacion" and 200 < len(d["description"]) < 1500
    assert P.tipo == "interfaz" and P.permisos == ("presentacion.ver",) and P.confirmar is None
    assert re.match(r"^\w+(ando|endo|iendo)\b", P.etiqueta)
    s = d["input_schema"]
    texto = json.dumps(s, ensure_ascii=False)
    assert "$ref" not in texto and "$defs" not in texto and '"title"' not in texto and "\\n" not in texto
    assert s["additionalProperties"] is False and s["required"] == ["op"]
    assert {k for _, k in _palabras(s)} <= PALABRAS_ESQUEMA  # sin pattern ni format
    assert s["properties"]["op"]["enum"] == list(hi.OPS_PRESENTACION)
    assert s["properties"]["paso"]["anyOf"] == [{"maximum": 60, "minimum": 1, "type": "integer"},
                                                {"maxLength": 40, "minLength": 1, "type": "string"}]
    assert s["properties"]["explicacion"]["maxLength"] == hi.MAX_EXPLICACION == 220
    assert "220" in s["properties"]["explicacion"]["description"] and "220" in d["description"]
    # Al final de las de interfaz: el orden fijo de `fijas()` (las conversaciones congelan la lista)
    assert [h.nombre for h in herramientas.fijas()][-1] == "presentacion"


# Fechas que existen, con barra, guion o punto (como `minimizar._FECHAS`, que tampoco las enmascara): suman 8 dígitos y
# antes se frenaban como si fueran cédulas, con un mensaje que no decía qué hacer (las del verificador, tal cual)
FECHAS = ("La radicación vence el 15/11/2026.", "Reunión el 07/03/2028 en el salón", "Firmado el 2026/11/07",
          "Corte al 31/12/2027", "Del 15 / 11 / 2026", "Se radica el 2026-11-15", "El 15.11.2026 y el 2028-02-29",
          "Del 15/11/2026 al 31/12/2027, 300 viviendas")
FECHAS_QUE_NO = ("Vence el 31/02/2026", "Vence el 11/15/2026", "En 2027-02-29", "Del 15/11/1850",
                 "El 15/11/2026 300 123 4567", "El 15/11/2026/3001234567", "Al 15/11-2026")
# Un monto en pesos con su signo y sus puntos de miles (el guion trae «$1.156.350» por habitante); sin el signo, sin los
# puntos o con otro número pegado, no
MONTOS = ("Por habitante, $1.156.350", "Son $ 1.156.350,50 al mes")
MONTOS_QUE_NO = ("Son 1.156.350 por habitante", "Al $3001234567", "Al $300 123 4567", "Son $1.156.350 300 viviendas")


@pytest.mark.parametrize("entrada", [
    {}, {"op": "borrar"}, {"op": "ir"}, {"op": "ir", "paso": 2}, {"op": "ir", "capitulo": "vivienda", "paso": True},
    {"op": "ir", "capitulo": "vivienda", "paso": 0}, {"op": "ir", "capitulo": "vivienda", "paso": 61},
    {"op": "ir", "capitulo": "vivienda", "paso": "Nuevas Casas"}, {"op": "ir", "capitulo": "v"},
    {"op": "ir", "capitulo": "vivienda", "ruta": "/x"}, {"op": "indice", "capitulo": "vivienda"},
    {"op": "indice", "explicacion": "Hola"}, {"op": "quitar_explicacion", "explicacion": "Hola"},
    {"op": "explicar"}, {"op": "explicar", "explicacion": "Hola", "capitulo": "vivienda"},
    {"op": "explicar", "explicacion": "   "}, {"op": "explicar", "explicacion": "x" * 221},
    {"op": "explicar", "explicacion": "Al revés \U0000202eodot"}, {"op": "explicar", "explicacion": "Campana \u0007"},
    {"op": "explicar", "explicacion": "Sin\U0000200bancho"}, {"op": "explicar", "explicacion": "Privado \U0000e000"},
    {"op": "explicar", "explicacion": "Llame al 3001234567"}, {"op": "explicar", "explicacion": "CC 71.234.567"},
    {"op": "explicar", "explicacion": "Teléfono 300 123 4567"}, {"op": "explicar", "explicacion": "escriba a ana@correo.co"},
    {"op": "explicar", "explicacion": "a\U00000301\U00000301\U00000301"}, {"op": "siguiente", "capitulo": "vivienda"},
    # Números por grupos con los separadores de siempre, «@» de ancho completo o pequeña, dígitos de compatibilidad
    *({"op": "explicar", "explicacion": t} for t in (
        "Llame a Ana al 300 - 123 - 4567", "Al 300 – 123 – 4567", "Al 300–123–4567", "Al 300\u2010123\u20104567",
        "Al 300\u2011123\u20114567", "Al 300/123/4567", "Al (604) 832 12 34", "Cédula de Ana: 1,023,456,789",
        "Código 71_234_567", "ana.perez\uff20gmail.com", "ana.perez\ufe6bgmail.com",
        "Al \u00b3\u2070\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077", "Al \uff13\uff10\uff10\uff11\uff12\uff13\uff14\uff15\uff16\uff17",
        "BPIN 2022003050034", "Periodo al revés 2031-2028", "En 2028 300 viviendas", "CC 71.234-567",
        # Lo que parece una fecha y no lo es (no existe, mes y día al revés, fuera de 1900–2099), o un número pegado a
        # una fecha de verdad: se mira como cualquier número. Lo mismo con lo que parece un monto en pesos
        *FECHAS_QUE_NO, *MONTOS_QUE_NO)),
    {"op": "anterior", "paso": 2}, ["ir"], "ir",
])
def test_entradas_invalidas(entrada):
    with pytest.raises(ValidationError):
        P.validar(entrada)


def test_entradas_validas_y_normalizadas():
    e = P.validar({"op": "explicar", "explicacion": "  Dos   espacios\ny un salto  "})
    assert e.explicacion == "Dos espacios y un salto"
    assert P.validar({"op": "explicar", "explicacion": "Inversión de $106.271 M en 2028–2031 ❤"}).explicacion
    # Periodos con guion, raya o barra, rangos de cifras de la propuesta y «m²» (se devuelve sin NFKC: no pasa a «m2»)
    for t in ("La propuesta 2028-2031 tiene siete módulos.", "Fases 2026-2027 y 2028-2031.", "Del 2028/2031",
              "En 2028 – 2031", "Cuesta $116.294 – 210.000 M", "Rango 1.346–1.500 kWh/kWp", "Desde 2018 (3.383)",
              "En 2028, 300 viviendas", "Casas de 50 m² en 2028–2031", "x" * 220, *FECHAS, *MONTOS):
        assert P.validar({"op": "explicar", "explicacion": t}).explicacion == t, t
    # El error dice qué hacer (también con una fecha que no existe: cómo se escribe una)
    with pytest.raises(ValidationError) as e:
        P.validar({"op": "explicar", "explicacion": "Llame al 300 - 123 - 4567"})
    msg = str(e.value)
    assert "7 o más dígitos" in msg and "«2028–2031»" in msg and "$106.271 M" in msg and "chat" in msg
    with pytest.raises(ValidationError) as e:
        P.validar({"op": "explicar", "explicacion": "Vence el 31/02/2026"})
    assert "«15/11/2026»" in str(e.value) and "«2026-11-15»" in str(e.value) and "existan" in str(e.value)
    with pytest.raises(ValidationError) as e:
        P.validar({"op": "explicar", "explicacion": "ana\uff20correo.co"})
    assert "«@»" in str(e.value) and "chat" in str(e.value)
    with pytest.raises(ValidationError):  # el selector de variante (U+FE0F) es de los que no se ven
        P.validar({"op": "explicar", "explicacion": "Con cariño ❤\U0000fe0f"})
    assert P.validar({"op": "ir", "capitulo": "Vivienda", "paso": "nuevas"}).paso == "nuevas"
    assert P.validar({"op": "ir", "capitulo": "vivienda", "paso": 3}).paso == 3
    assert P.validar({"op": "siguiente"}).capitulo is None


def _textos(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from _textos(x)
    elif isinstance(v, list):
        for x in v:
            yield from _textos(x)


# Lo único del guion que la explicación no deja pasar: los códigos de proyecto (BPIN, PDET), el de un lote, el numeral
# de una norma («RAC 14, num. 14.3.4.2.7.2») y el de un proceso de SECOP («CO1.NTC.9080794», la fuente de una cifra)
CODIGO = re.compile(r"\d{10,}|\d{3}-\d{3}-\d{3}-\d{5}|\d+(?:\.\d){5,}")


def test_la_explicacion_deja_las_cifras_del_guion_y_frena_los_codigos():
    """El modelo copia las cifras del guion en la explicación: los montos («$106.271 M», «$1,2 – 1,4 billones», y en
    pesos con sus puntos de miles, «$1.156.350» por habitante), los rangos («1.346–1.500»), los periodos y los años entre
    paréntesis pasan; solo se frenan los códigos. Con el guion entero (antes se cortaba a 3 KB por paso)."""
    import unicodedata
    textos = list(_textos([c["pasos"] for c in G.capitulos]))
    frenados = {(t, hi.numero_largo(" ".join(unicodedata.normalize("NFKC", t).split()))) for t in textos}
    frenados = {(t, x) for t, x in frenados if x}
    assert frenados and all(CODIGO.fullmatch(x) or f"CO1.NTC.{x}" in t for t, x in frenados), frenados
    assert any("$1.156.350" in t for t in textos)
    assert P.validar({"op": "explicar", "explicacion": "Por habitante, $1.156.350 en 2028"}).explicacion
    cifras = {x for c in G.capitulos for p in c["pasos"] for x in _cifras_de(p)}
    assert len(cifras) > 100
    for x in cifras:
        assert P.validar({"op": "explicar", "explicacion": f"Son {x} en 2028–2031."}).explicacion, x


def _cifras_de(p: dict):
    """Las cifras de un paso: los valores de `cifras` y los montos, costos e inversiones (todo lo que lleva «$»)."""
    for c in p.get("cifras") or []:
        yield c["v"]
    for t in _textos(p):
        yield from re.findall(r"≈? ?\$[\d.,]+(?: – [\d.,]+)?(?: mil M| M| billones)?", t)


@pytest.fixture
def ctx(sesion):
    c = aa.contexto(sesion.app, sesion)
    yield c
    aa.correr(sesion, c.api.cerrar)


def _ej(sesion, ctx, entrada):
    return aa.correr(sesion, aa.ejecutar, P, ctx, entrada)


def _falla(sesion, ctx, entrada) -> ErrorHerramienta:
    with pytest.raises(ErrorHerramienta) as e:
        _ej(sesion, ctx, entrada)
    return e.value


def test_indice_compacto_y_sin_acciones(sesion, ctx):
    r = _ej(sesion, ctx, {"op": "indice"})
    assert r.acciones == [] and r.personas == set()
    assert [c["id"] for c in r.contenido["capitulos"]] == [c["id"] for c in G.capitulos]
    assert r.contenido["total_pasos"] == G.total_pasos()
    assert r.contenido["capitulos"][1]["pasos"] == [p["titulo"] for p in G.capitulos[1]["pasos"]]
    assert len(r.texto_para_modelo()) < 6000


def test_ir_devuelve_el_paso_y_una_accion_exacta(sesion, ctx):
    r = _ej(sesion, ctx, {"op": "ir", "capitulo": "vivienda", "paso": 3})
    assert r.acciones == [{"tipo": "presentacion", "op": "ir", "capitulo": "vivienda", "paso": 3}]
    vi = G.capitulos[G.por_id("vivienda")]
    assert r.contenido["guion"] == vi["pasos"][2] and r.contenido["paso"] == 3 and r.contenido["de"] == len(vi["pasos"])
    assert r.contenido["posicion"] == f"Paso 3 de {len(vi['pasos'])} del capítulo Vivienda"
    assert r.resumen == f"Mostré Vivienda · paso 3 de {len(vi['pasos'])}" and r.personas == set()
    # Por nombre y por id del paso, con la explicación (normalizada) para la pantalla
    r = _ej(sesion, ctx, {"op": "ir", "capitulo": "Cómo se financia", "paso": "fuentes",
                          "explicacion": "Diez  fuentes, una por una."})
    assert r.acciones == [{"tipo": "presentacion", "op": "ir", "capitulo": "financiacion", "paso": 2,
                           "explicacion": "Diez fuentes, una por una."}]
    # Sin paso, el primero
    assert _ej(sesion, ctx, {"op": "ir", "capitulo": "pedidos"}).acciones[0]["paso"] == 1


def test_siguiente_y_anterior_calculan_el_destino(sesion, ctx):
    vi = G.capitulos[G.por_id("vivienda")]
    n = len(vi["pasos"])
    r = _ej(sesion, ctx, {"op": "siguiente", "capitulo": "vivienda", "paso": n})
    assert r.acciones == [{"tipo": "presentacion", "op": "ir", "capitulo": "urbanismo", "paso": 1}]
    assert r.contenido["guion"] == G.capitulos[G.por_id("urbanismo")]["pasos"][0] and "aviso" not in r.contenido
    r = _ej(sesion, ctx, {"op": "anterior", "capitulo": "vivienda", "paso": 1})
    portada = G.capitulos[0]
    assert r.acciones == [{"tipo": "presentacion", "op": "ir", "capitulo": "portada", "paso": len(portada["pasos"])}]
    r = _ej(sesion, ctx, {"op": "siguiente", "capitulo": "vivienda", "paso": "nuevas"})
    assert r.acciones[0]["paso"] == 4
    # En los extremos se queda, y lo dice
    ultimo = G.capitulos[-1]
    r = _ej(sesion, ctx, {"op": "siguiente", "capitulo": "pedidos", "paso": len(ultimo["pasos"])})
    assert r.acciones[0] == {"tipo": "presentacion", "op": "ir", "capitulo": "pedidos", "paso": len(ultimo["pasos"])}
    assert "último" in r.contenido["aviso"]
    assert "primer" in _ej(sesion, ctx, {"op": "anterior", "capitulo": "portada", "paso": 1}).contenido["aviso"]
    # Sin el punto de partida, lo calcula la presentación
    r = _ej(sesion, ctx, {"op": "siguiente"})
    assert r.acciones == [{"tipo": "presentacion", "op": "siguiente"}] and "guion" not in r.contenido
    r = _ej(sesion, ctx, {"op": "anterior", "explicacion": "Volvemos un paso."})
    assert r.acciones == [{"tipo": "presentacion", "op": "anterior", "explicacion": "Volvemos un paso."}]


def test_explicar_y_quitar(sesion, ctx):
    r = _ej(sesion, ctx, {"op": "explicar", "explicacion": "Aquí van las 300 viviendas nuevas."})
    assert r.acciones == [{"tipo": "presentacion", "op": "explicar", "explicacion": "Aquí van las 300 viviendas nuevas."}]
    assert r.contenido["en_pantalla"] == "Aquí van las 300 viviendas nuevas."
    assert _ej(sesion, ctx, {"op": "quitar_explicacion"}).acciones == [{"tipo": "presentacion",
                                                                         "op": "quitar_explicacion"}]


def test_errores_sin_mover_nada(sesion, ctx):
    e = _falla(sesion, ctx, {"op": "ir", "capitulo": "marte"})
    assert e.codigo == "no_existe" and [c["id"] for c in e.detalle["capitulos"]] == [c["id"] for c in G.capitulos]
    e = _falla(sesion, ctx, {"op": "ir", "capitulo": "sa", "paso": 1})
    assert e.codigo == "ambiguo" and {c["id"] for c in e.detalle["candidatos"]} == {"salud", "saneamiento"}
    e = _falla(sesion, ctx, {"op": "ir", "capitulo": "vivienda", "paso": 40})
    assert e.codigo == "invalido" and e.detalle["pasos"] == len(G.capitulos[G.por_id("vivienda")]["pasos"])
    assert "nuevas" in e.detalle["ids"]
    assert _falla(sesion, ctx, {"op": "siguiente", "capitulo": "vivienda", "paso": "noexiste"}).codigo == "invalido"
    assert _falla(sesion, ctx, {"op": "anterior", "capitulo": "marte", "paso": 1}).codigo == "no_existe"


def test_sin_guion_no_se_ofrece_ni_corre(sesion, ctx, monkeypatch):
    quien = aa.quien_de(sesion.app, 0)
    assert "presentacion" in {h.nombre for h in herramientas.para(quien, {}, sesion.app.state.cfg)}
    monkeypatch.setattr(guion, "RUTA", guion.RUTA.with_name("no_existe.json"))
    assert "presentacion" not in {h.nombre for h in herramientas.para(quien, {}, sesion.app.state.cfg)}
    monkeypatch.setattr(guion, "cargar", lambda: None)
    assert _falla(sesion, ctx, {"op": "indice"}).codigo == "no_existe"

    def roto():
        raise ValueError("dañado")
    monkeypatch.setattr(guion, "cargar", roto)
    assert _falla(sesion, ctx, {"op": "ir", "capitulo": "vivienda"}).codigo == "no_existe"


def test_los_cuatro_roles_y_el_permiso(sesion, como, ctx):
    assert {"presentacion.ver"} <= acceso.PERMISOS["planillero"] & acceso.PERMISOS["consultor"]
    for rol in ("planillero", "consultor"):
        cli = como(rol)
        quien = aa.quien_de(sesion.app, cli.uid)
        assert quien.puede("presentacion.ver")
        assert "presentacion" in {h.nombre for h in herramientas.para(quien, {"escritura": False}, sesion.app.state.cfg)}
        c = aa.contexto(sesion.app, cli)
        try:
            assert aa.correr(sesion, aa.ejecutar, P, c, {"op": "ir", "capitulo": "salud"}).acciones[0]["capitulo"] == "salud"
        finally:
            aa.correr(sesion, c.api.cerrar)
    sin = dataclasses.replace(ctx, quien=acceso.Quien(uid=9, usuario="x", rol="jefe", permisos=frozenset({"cuenta"})))
    e = _falla(sesion, sin, {"op": "indice"})
    assert (e.estado, e.codigo) == (403, "permiso")
    # abrir_vista también la abre (con el mismo permiso que la ruta de app.js)
    r = aa.correr(sesion, aa.ejecutar, H["abrir_vista"], ctx, {"vista": "presentacion"})
    assert r.acciones == [{"tipo": "navegar", "ruta": "/presentacion"}]


# ───────────────────────────── El sistema, el contexto y el bucle ─────────────────────────────

def test_sistema_explica_cuando_usarla():
    quien = acceso.Quien(uid=5, usuario="p5", nombre="Pepa", rol="planillero", permisos=acceso.PERMISOS["planillero"])
    t = sistema.texto(quien, [P])
    assert "`presentacion`" in t and "frase corta" in t and "nunca lleva datos de habitantes" in t
    assert "`presentacion`" not in sistema.texto(quien, [H["abrir_vista"]])
    assert "presentacion" in sistema.VISTAS_MENU and "presentacion" in bucle.ACCIONES


def test_contexto_de_la_presentacion_se_valida_contra_el_guion():
    vi = G.capitulos[G.por_id("vivienda")]
    t = sistema.contexto_del_panel({"ruta": "/presentacion", "vista": "presentacion",
                                    "presentacion": {"capitulo": "vivienda", "paso": 3}}, AHORA, guion=G)
    assert f"\nPresentación abierta: Vivienda (vivienda), paso 3 de {len(vi['pasos'])}: {vi['pasos'][2]['titulo']}\n" in t
    assert "Vista abierta: presentacion (/presentacion)" in t
    for malo in ({"capitulo": "vivienda", "paso": True}, {"capitulo": "vivienda", "paso": 0},
                 {"capitulo": "vivienda", "paso": 99}, {"capitulo": "vivienda", "paso": "3"},
                 {"capitulo": "marte", "paso": 1}, {"capitulo": "<b>vivienda</b>", "paso": 1},
                 {"capitulo": "x" * 41, "paso": 1}, {"capitulo": 7, "paso": 1}, "vivienda/3", ["vivienda", 3], None):
        assert "Presentación" not in sistema.contexto_del_panel({"presentacion": malo}, AHORA, guion=G), malo
    # Sin el guion (no está en este servidor), la línea no va
    assert "Presentación" not in sistema.contexto_del_panel(
        {"presentacion": {"capitulo": "vivienda", "paso": 3}}, AHORA)
    assert sistema.guion_del_contexto().capitulos == G.capitulos


def test_turno_completo_la_presentacion_llega_al_navegador_y_el_paso_al_modelo(sesion):
    explicacion = "Las 300 viviendas nuevas van en dos lotes del casco urbano."
    falsa = aa.encender(sesion.app,
                        aa.sse(aa.TU("toolu_pres1", "presentacion", {"op": "ir", "capitulo": "vivienda", "paso": 3,
                                                                     "explicacion": explicacion}), stop="tool_use"),
                        aa.sse(aa.T("Listo: está en Vivienda, el paso de las viviendas nuevas.")))
    r, ev = aa.enviar(sesion, "Muéstrame las viviendas nuevas de la propuesta", contexto={
        "ruta": "/presentacion", "vista": "presentacion", "presentacion": {"capitulo": "portada", "paso": 1}})
    assert r.status_code == 200, r.text
    assert [e["accion"] for e in ev if e["tipo"] == "accion"] == [
        {"tipo": "presentacion", "op": "ir", "capitulo": "vivienda", "paso": 3, "explicacion": explicacion}]
    assert [(e["nombre"], e["estado"]) for e in ev if e["tipo"] == "herramienta"] == [("presentacion", "inicio"),
                                                                                    ("presentacion", "ok")]
    assert ev[-1]["tipo"] == "fin" and ev[-1]["motivo"] == "listo"
    primera, segunda = falsa.peticiones[0]["json"], falsa.peticiones[1]["json"]
    # El sistema dice cuándo usarla y el contexto, dónde está la presentación (con el título del guion)
    sistema_txt = json.dumps(primera["system"], ensure_ascii=False)
    assert "`presentacion`" in sistema_txt
    usuario = json.dumps(primera["messages"][-1], ensure_ascii=False)
    assert "Presentación abierta: Portada (portada), paso 1 de" in usuario
    assert "presentacion" in {t["name"] for t in primera["tools"]}
    # Al modelo le vuelve lo que muestra el paso de destino
    resultado = json.dumps(segunda["messages"][-1], ensure_ascii=False)
    assert "toolu_pres1" in resultado and "300 viviendas en dos lotes reales" in resultado
    assert "Paso 3 de" in resultado and "Lote 1" in resultado


# ───────────────────────────── CSP y despliegue ─────────────────────────────

def test_csp_del_panel_deja_el_iframe_de_la_presentacion():
    assert "frame-src 'self'" in seguridad.CSP and "frame-ancestors 'none'" in seguridad.CSP
    assert seguridad.politica_panel("") == seguridad.CSP
    con = seguridad.politica_panel("https://sitio.example")
    assert "frame-src 'self' https://sitio.example;" in con and con.count("frame-src") == 1
    assert con.replace(" https://sitio.example", "") == seguridad.CSP


@pytest.mark.parametrize("valor, esperado", [
    ("", ""), ("https://sitio.example", "https://sitio.example"), ("https://sitio.example/", "https://sitio.example"),
    ("https://sitio.example:8443/yondo/", "https://sitio.example:8443/yondo"), ("http://127.0.0.1:8000", "http://127.0.0.1:8000"),
    ("http://sitio.example", ""), ("https://sitio.example/a;b", ""), ("https://usuario@sitio.example", ""),
    ("https://sitio.example/x?y=1", ""), ("https://sitio.example/ x", ""), ("javascript:alert(1)", ""),
    ("https://sitio.example'; script-src *", ""),
])
def test_sitio_url(valor, esperado, monkeypatch):
    assert config._url_sitio(valor) == esperado
    if esperado:
        c = dataclasses.replace(config.Config("a", "b", "u", "d", 1, False, 1), sitio_url=esperado)
        assert c.origen_sitio == re.match(r"https?://[^/]+", esperado).group(0)


def test_el_panel_manda_su_csp_con_el_sitio_y_lo_dice_en_yo(cliente, cfg):
    r = cliente.get("/")
    assert r.headers["content-security-policy"] == seguridad.CSP
    assert cliente.post("/api/login", json={"usuario": cfg.usuario, "clave": cfg.clave}).json()["sitio_url"] is None
    cliente.app.state.cfg = dataclasses.replace(cfg, sitio_url="https://sitio.example/yondo")
    r = cliente.get("/")
    assert "frame-src 'self' https://sitio.example;" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "DENY"
    assert cliente.get("/api/yo").json()["sitio_url"] == "https://sitio.example/yondo"


def test_frame_ancestors_del_sitio_con_el_panel_aparte(tmp_path):
    import servidor
    sitio = tmp_path / "site"
    sitio.mkdir()
    (sitio / "index.html").write_text("<!doctype html><title>Inicio</title>", encoding="utf-8")
    pagina = sitio / "propuesta.html"
    assert servidor.politica_sitio(sitio).endswith("frame-ancestors 'self'")
    for meta, esperado in (("https://panel.example", "frame-ancestors 'self' https://panel.example"),
                           ("https://panel.example:8443", "frame-ancestors 'self' https://panel.example:8443"),
                           ("http://panel.example", "frame-ancestors 'self'"),
                           ("https://panel.example/ruta", "frame-ancestors 'self'"),
                           ("https://panel.example *", "frame-ancestors 'self'")):
        pagina.write_text(f'<!doctype html><meta charset="utf-8">\n<meta name="panel-origen" content="{meta}">',
                          encoding="utf-8")
        assert servidor.politica_sitio(sitio).endswith(esperado), meta


def _build_site(monkeypatch):
    for v in ("SITE_URL", "RAILWAY_PUBLIC_DOMAIN", "PANEL_URL"):
        monkeypatch.delenv(v, raising=False)
    spec = importlib.util.spec_from_file_location("build_site", RAIZ / "scripts" / "build_site.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_build_site_escribe_el_origen_del_panel_en_la_presentacion(tmp_path, monkeypatch):
    m = _build_site(monkeypatch)
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<!doctype html><html><body><!-- ingreso-equipo --></body></html>", encoding="utf-8")
    (web / "propuesta.html").write_text('<!doctype html><html><head><meta charset="utf-8"></head><body></body></html>',
                                        encoding="utf-8")
    # Con mayúsculas o «:443», el origen como lo entrega el navegador en e.origin (si no, mando.js no aceptaría ninguna
    # orden del panel aunque la presentación le dijera «listo»)
    for panel, meta in (("https://panel.example/", "https://panel.example"), ("https://panel.example:8443/x", "https://panel.example:8443"),
                        ("https://Panel.Yondo.co", "https://panel.yondo.co"), ("https://panel.yondo.co:443/x", "https://panel.yondo.co"),
                        ("https://PANEL.example:8443/Ruta", "https://panel.example:8443"), ("https://panel.example:99999", None),
                        ("/panel/", None), ("", None), ("http://panel.example", None)):
        monkeypatch.setenv("PANEL_URL", panel)
        m.construir(web, tmp_path / "site")
        p = (tmp_path / "site" / "propuesta.html").read_text(encoding="utf-8")
        if meta:
            assert f'<meta charset="utf-8">\n<meta name="panel-origen" content="{meta}">' in p, panel
        else:
            assert "panel-origen" not in p, panel


def _codigo(texto: str) -> str:
    """El código sin las líneas de comentario."""
    return "\n".join("" if l.lstrip().startswith(("//", "*", "/*")) else l for l in texto.splitlines())


def test_la_presentacion_no_numera_ni_pinta_html_en_el_subtitulo():
    """La regla del CI («la presentación no numera los capítulos») también para mando.js, y el subtítulo es texto."""
    for f in (MAIN_JS, MANDO_JS, RAIZ / "web/js/propuesta/modulos/ruta.js"):
        t = f.read_text(encoding="utf-8")
        assert not re.search(r"padStart\(2, ?.0.\)|class=\"num\"|\$\{c\.n\}|\$\{i \+ 1\}\.", t), f.name
    mando = MANDO_JS.read_text(encoding="utf-8")
    codigo = _codigo(mando)
    assert "innerHTML" not in codigo and "texto.textContent = t;" in codigo
    assert codigo.count("postMessage(") == 1 and "padre.postMessage({ canal: CANAL, v: VERSION, ...msj }, o)" in codigo
    assert "'*'" not in codigo and '"*"' not in codigo
    html = (RAIZ / "web" / "propuesta.html").read_text(encoding="utf-8")
    assert '<div class="subtitulo" role="status" aria-live="polite"><p></p></div>' in html
    assert re.search(r"@media print \{[^}]*\.subtitulo \{ display: none !important; \}", html) or \
        re.search(r"\.leyenda3d, \.subtitulo \{ display: none !important; \}", html)
    assert re.search(r"prefers-reduced-motion: reduce\) \{[^\n]*\.subtitulo", html)
    # La hoja de ruta deja de girar con el aviso de cada paso (mostrar usa replaceState: no hay hashchange)
    ruta = (RAIZ / "web/js/propuesta/modulos/ruta.js").read_text(encoding="utf-8")
    assert "hashchange" not in _codigo(ruta) and "addEventListener('propuesta:paso'" in ruta


def test_constantes_iguales_en_los_tres_lados():
    puente, mando = PUENTE_JS.read_text(encoding="utf-8"), MANDO_JS.read_text(encoding="utf-8")
    for js in (puente, mando):
        assert re.search(r"export const MAX_EXPLICACION = (\d+);", js).group(1) == str(hi.MAX_EXPLICACION)
        assert "export const CANAL = 'yondo-presentacion';" in js and "export const VERSION = 1;" in js
    # El validador vive en el puente y agente.js lo reexporta (lo usan el asistente y el proyector)
    agente = (JS / "agente.js").read_text(encoding="utf-8")
    assert "export { accionPresentacion };" in agente and "else if (a.tipo === 'presentacion') presentacion(a);" in agente
    assert "presentacion: pasoPresentacion()," in agente
    vista = (JS / "vistas" / "presentacion.js").read_text(encoding="utf-8")
    assert "window.open" not in _codigo(vista) and 'target="_blank" rel="noopener"' in vista
    assert not re.search(r"<iframe[^>]*sandbox", vista) and 'allow="fullscreen"' in vista
    assert "postMessage({ canal: CANAL, v: VERSION, id, ...o }, d.origen)" in vista
    assert "e.source !== iframe.contentWindow || e.origin !== d.origen" in vista


# ───────────────────────────── Con Node ─────────────────────────────

NODE_ACCION = r"""
globalThis.document = { querySelector: () => null, documentElement: {} };
globalThis.MutationObserver = class { observe() {} };
globalThis.window = globalThis;
globalThis.addEventListener ||= () => {};
globalThis.location = { pathname: '/', origin: 'https://panel.example' };
const m = await import('./web/js/agente.js');
console.log(JSON.stringify(JSON.parse(process.argv[1]).map((a) => m.accionPresentacion(a))));
"""

ACCIONES = [
    ({"tipo": "presentacion", "op": "ir", "capitulo": "vivienda", "paso": 3},
     {"tipo": "presentacion", "op": "ir", "capitulo": "vivienda", "paso": 3}),
    ({"tipo": "presentacion", "op": "ir", "capitulo": "vivienda", "explicacion": " Dos  espacios "},
     {"tipo": "presentacion", "op": "ir", "capitulo": "vivienda", "explicacion": "Dos espacios"}),
    ({"tipo": "presentacion", "op": "siguiente"}, {"tipo": "presentacion", "op": "siguiente"}),
    ({"tipo": "presentacion", "op": "anterior", "explicacion": "Atrás"},
     {"tipo": "presentacion", "op": "anterior", "explicacion": "Atrás"}),
    ({"tipo": "presentacion", "op": "explicar", "explicacion": "<b>Texto</b> visible"},
     {"tipo": "presentacion", "op": "explicar", "explicacion": "<b>Texto</b> visible"}),
    ({"tipo": "presentacion", "op": "quitar_explicacion"}, {"tipo": "presentacion", "op": "quitar_explicacion"}),
    # Lo demás no se aplica
    ({"tipo": "presentacion", "op": "indice"}, None), ({"tipo": "presentacion", "op": "constructor"}, None),
    ({"tipo": "presentacion", "op": "__proto__"}, None), ({"tipo": "mapa", "op": "ir", "capitulo": "vivienda"}, None),
    ({"tipo": "presentacion", "op": "ir"}, None), ({"tipo": "presentacion", "op": "ir", "capitulo": "Vivienda"}, None),
    ({"tipo": "presentacion", "op": "ir", "capitulo": "../x"}, None),
    ({"tipo": "presentacion", "op": "ir", "capitulo": "vivienda", "paso": 0}, None),
    ({"tipo": "presentacion", "op": "ir", "capitulo": "vivienda", "paso": 61}, None),
    ({"tipo": "presentacion", "op": "ir", "capitulo": "vivienda", "paso": 2.5}, None),
    ({"tipo": "presentacion", "op": "ir", "capitulo": "vivienda", "paso": "3"}, None),
    ({"tipo": "presentacion", "op": "ir", "capitulo": "vivienda", "paso": True}, None),
    ({"tipo": "presentacion", "op": "siguiente", "capitulo": "vivienda"}, None),
    ({"tipo": "presentacion", "op": "ir", "capitulo": "vivienda", "ruta": "/x"}, None),
    ({"tipo": "presentacion", "op": "explicar"}, None),
    ({"tipo": "presentacion", "op": "explicar", "explicacion": ""}, None),
    ({"tipo": "presentacion", "op": "explicar", "explicacion": "x" * 220},
     {"tipo": "presentacion", "op": "explicar", "explicacion": "x" * 220}),
    ({"tipo": "presentacion", "op": "explicar", "explicacion": "x" * 221}, None),
    ({"tipo": "presentacion", "op": "explicar", "explicacion": "Al 300 - 123 - 4567"}, None),
    ({"tipo": "presentacion", "op": "explicar", "explicacion": "ana\uff20correo.co"}, None),
    ({"tipo": "presentacion", "op": "explicar", "explicacion": "Del 2028-2031"},
     {"tipo": "presentacion", "op": "explicar", "explicacion": "Del 2028-2031"}),
    ({"tipo": "presentacion", "op": "explicar", "explicacion": "Al revés \U0000202eodot"}, None),
    ({"tipo": "presentacion", "op": "explicar", "explicacion": "Dos\nrenglones"}, None),
    ({"tipo": "presentacion", "op": "explicar", "explicacion": "Sin\U0000200bancho"}, None),
    ({"tipo": "presentacion", "op": "explicar", "explicacion": "Llame al 300 123 4567"}, None),
    ({"tipo": "presentacion", "op": "explicar", "explicacion": "ana@correo.co"}, None),
    ({"tipo": "presentacion", "op": "explicar", "explicacion": 7}, None),
    ({"tipo": "presentacion", "op": "quitar_explicacion", "explicacion": "x"}, None),
    (["presentacion"], None), ("presentacion", None), (None, None),
]


@requiere_node
def test_accion_presentacion_con_node():
    r = subprocess.run(["node", "--input-type=module", "-e", NODE_ACCION, json.dumps([a for a, _ in ACCIONES])],
                       cwd=ADMIN, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    salida = json.loads(r.stdout.strip().splitlines()[-1])
    for (entrada, esperado), obtenido in zip(ACCIONES, salida, strict=True):
        assert obtenido == esperado, entrada


NODE_TEXTOS = r"""// Las frases por el puente y por el mando. Uso: node <guion> <url del puente> <url del mando> <pares.json>
import { readFileSync } from 'node:fs';
const [puente, mando, archivo] = process.argv.slice(2);
globalThis.document = { querySelector: () => null };
globalThis.location = { pathname: '/', origin: 'https://panel.example' };
const P = await import(puente), M = await import(mando);
const puenteDe = (t) => P.accionPresentacion({ tipo: 'presentacion', op: 'explicar', explicacion: t })?.explicacion ?? null;
// Por cada frase, lo que deciden el puente y el mando con ella y con lo que la herramienta devolvió (si la aceptó)
const pares = JSON.parse(readFileSync(archivo, 'utf-8'));
console.log(JSON.stringify(pares.map(([t, e]) => [puenteDe(t), M.textoVisible(t), e === null ? null : puenteDe(e),
  e === null ? null : M.textoVisible(e)])));
"""

FRASES = [
    "Hola", "  Dos   espacios  ", "x" * 220, "x" * 221, "Llame a Ana al 300 - 123 - 4567", "Al 300 – 123 – 4567",
    "Al 300–123–4567", "Al 300\u2010123\u20104567", "Al 300\u2011123\u20114567", "Al 300\u2212123\u22124567",
    "Al 300/123/4567", "Al 300 / 123 / 4567", "Al (604) 832 12 34", "Al 300(123)4567", "Cédula: 1,023,456,789",
    "Código 71_234_567", "CC 71.234.567", "CC 71.234-567", "Al 3001234567", "Al 300 123 4567", "ana@correo.co",
    "ana.perez\uff20gmail.com", "ana.perez\ufe6bgmail.com",
    "Al \u00b3\u2070\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077",
    "Al \uff13\uff10\uff10\uff11\uff12\uff13\uff14\uff15\uff16\uff17",
    "Al \u0663\u0660\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667", "BPIN 2022003050034", "La propuesta 2028-2031",
    "Fases 2026-2027 y 2028-2031.", "Del 2028/2031", "En 2028 – 2031", "Al revés 2031-2028", "En 2028 300 viviendas",
    "En 2028, 300 viviendas", "En 2031. 300 familias", "Desde 2018 (3.383)", "Cuesta $116.294 – 210.000 M",
    "Rango 1.346–1.500 kWh", "Casas de 50 m² en 2028–2031", "Inversión de $106.271 M en 2028–2031 ❤", "Con cariño ❤\ufe0f",
    "Al revés \u202eodot", "a\u0301\u0301\u0301", "Dos\nrenglones", "Sin\u200bancho", *FECHAS, *FECHAS_QUE_NO,
    *MONTOS, *MONTOS_QUE_NO,
]


@requiere_node
def test_las_reglas_de_la_explicacion_son_las_mismas_en_los_tres_lados(tmp_path):
    """La herramienta, el puente del panel y el mando de la presentación deciden lo mismo con cada frase (también con
    las cifras del guion): lo que la herramienta frena, los dos lados del navegador también, y lo que la herramienta
    devuelve (ya con los espacios en uno) lo muestran tal cual. Si no, el subtítulo fallaría sin decir por qué, o un
    número llegaría a la sala."""
    frases = FRASES + sorted({f"Son {x} en 2028–2031." for c in G.capitulos for p in c["pasos"] for x in _cifras_de(p)})

    def servidor(t):
        try:
            return P.validar({"op": "explicar", "explicacion": t}).explicacion
        except ValidationError:
            return None
    esperado = [servidor(t) for t in frases]
    assert esperado[:4] == ["Hola", "Dos espacios", "x" * 220, None]
    # Las fechas que existen y los montos en pesos pasan tal cual (y entonces también en el puente y en el mando); lo que
    # solo se les parece, no
    assert [servidor(t) for t in FECHAS + MONTOS] == list(FECHAS + MONTOS)
    assert not any(map(servidor, FECHAS_QUE_NO + MONTOS_QUE_NO))
    assert sum(e is None for e in esperado) >= 25 and sum(e is not None for e in esperado) > 100
    (tmp_path / "pares.json").write_text(json.dumps(list(zip(frases, esperado))), encoding="utf-8")
    (tmp_path / "textos.mjs").write_text(NODE_TEXTOS, encoding="utf-8")
    r = subprocess.run(["node", str(tmp_path / "textos.mjs"), PUENTE_JS.as_uri(), MANDO_JS.as_uri(),
                        str(tmp_path / "pares.json")], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    salida = json.loads(r.stdout.strip().splitlines()[-1])
    for t, e, (puente, mando, puente_e, mando_e) in zip(frases, esperado, salida, strict=True):
        if e is None:
            assert puente is None and mando is None, (t, puente, mando)
        else:
            assert puente_e == mando_e == e, (t, e, puente_e, mando_e)
            # Tal como la escribió el modelo, también (salvo el salto de renglón: la herramienta lo junta en un espacio
            # y el navegador no lo acepta, pero nunca le llega)
            assert puente == mando == (None if "\n" in t else e), (t, puente, mando)


GUION_PUENTE = r"""// El puente de la presentación sin navegador. Uso: node <guion> <url del módulo>
const [modulo] = process.argv.slice(2);
const oyentes = {};
globalThis.document = { querySelector: () => null };
globalThis.location = { pathname: '/panel/personas', origin: 'https://panel.example' };
globalThis.addEventListener = (tipo, f) => { (oyentes[tipo] ||= []).push(f); };
const vista = (detail) => (oyentes.vista || []).forEach((f) => f({ detail }));
// BroadcastChannel entre «pestañas» (dos instancias del módulo): copia estructurada y entrega en otra vuelta del bucle
const canales = new Set();
const crudos = [];
globalThis.BroadcastChannel = class {
  constructor(n) { this.n = n; canales.add(this); }
  postMessage(d) { const c = structuredClone(d); if (!this.prueba) crudos.push(c); for (const x of canales) if (x !== this && x.n === this.n) setTimeout(() => x.onmessage?.({ data: structuredClone(c) }), 1); }
  close() { canales.delete(this); }
};
const A = await import(modulo + '?pestana=chat');
const dormir = (ms) => new Promise((ok) => setTimeout(ok, ms));
const navegadas = [];
const navegar = (ruta) => { navegadas.push(ruta); location.pathname = ruta; };
const mensaje = (p) => p.then(() => 'resolvió', (e) => e.message);
const r = { exports: Object.keys(A).sort() };
const ir = (capitulo, paso) => ({ tipo: 'presentacion', op: 'ir', capitulo, paso });

// 1. Sin la vista: encola y navega una sola vez
const p1 = A.accionesPresentacion([ir('vivienda', 3)], { navegar });
const p2 = A.accionesPresentacion({ tipo: 'presentacion', op: 'explicar', explicacion: 'Hola' }, { navegar });
r.navegadas = navegadas.slice();
r.en_cola = A.accionesEnCola();
r.lista_antes = A.presentacionLista();
r.estado_sin_vista = A.estadoPresentacion();

// 2. Al registrarse, la cola sale en orden y después lo directo
const aplicadas = [];
let lanza = false;
const estado = { capitulo: 'vivienda', paso: 3, total: 6, nombre: 'Vivienda', titulo: 'Paso\u0007 tres', explicacion: true, sobra: 1 };
const control = {
  aplicar: async (l) => { aplicadas.push(l.map((a) => a.op)); await dormir(5); return l.map((a) => ({ op: a.op, ok: true })); },
  estado: () => { if (lanza) throw new Error('roto'); return estado; },
};
r.registro_invalido = typeof A.registrarPresentacion({ aplicar: 1 });
let quitar = A.registrarPresentacion(control);
const p3 = A.accionesPresentacion([{ tipo: 'presentacion', op: 'siguiente' }]);
r.resultados = await Promise.all([p1, p2, p3]);
r.aplicadas = aplicadas.slice();
r.estado = A.estadoPresentacion();
lanza = true;
r.estado_que_lanza = A.estadoPresentacion();
lanza = false;
r.proyector_sin_nadie = A.proyectorVivo();

// 3. Se quita la vista antes de aplicar
const p4 = A.accionesPresentacion([ir('salud', 1)]);
quitar();
r.cerrada = await mensaje(p4);

// 4. El plazo vence sin navegar; otra vista rechaza en el acto; la vista sin sitio rechaza con su motivo
location.pathname = '/presentacion';
navegadas.length = 0;
r.vencida = await mensaje(A.accionesPresentacion([ir('salud', 1)], { navegar, espera: 30 }));
r.no_navego_en_la_vista = navegadas.length === 0;
location.pathname = '/panel/personas';
const p5 = A.accionesPresentacion([ir('salud', 1)], { navegar });
vista({ ruta: '/presentacion', ok: true });
r.en_cola_tras_abrir = A.accionesEnCola();
location.pathname = '/panel/reuniones';
vista({ ruta: '/reuniones', ok: true });
r.otra_vista = await mensaje(p5);
const p6 = A.accionesPresentacion([ir('salud', 1)], { navegar });
A.presentacionNoDisponible('La presentación no está en este servidor');
r.sin_sitio = await mensaje(p6);

// 5. El proyector: otra «pestaña» se registra como proyector y se anuncia; esta le manda las órdenes y no navega
const B = await import(modulo + '?pestana=proyector');
const enProyector = [];
const estadoB = { capitulo: 'aguas', paso: 2, total: 5, nombre: 'Aguas', titulo: 'Así funciona hoy', explicacion: false };
const quitarB = B.registrarPresentacion({ proyector: true, estado: () => estadoB,
  aplicar: async (l) => { enProyector.push(l.map((a) => a.op)); return l.map((a) => ({ op: a.op, ok: a.capitulo !== 'marte' })); } });
await dormir(30);
r.proyector_vivo = A.proyectorVivo();
r.el_proyector_no_se_ve_a_si_mismo = B.proyectorVivo();
navegadas.length = 0;
location.pathname = '/panel/personas';
r.al_proyector = await A.accionesPresentacion([ir('aguas', 2), { tipo: 'presentacion', op: 'ir', capitulo: 'Mal' }, ir('marte', 1)], { navegar });
r.en_proyector = enProyector.slice();
r.navego_con_proyector = navegadas.slice();
r.estado_del_proyector = A.estadoPresentacion();
// Mensajes del canal que no cumplen: se ignoran
const raro = new BroadcastChannel('yondo-presentacion');
raro.prueba = true;   // lo que manda la prueba no cuenta en `crudos`
for (const m of [{ canal: 'otro', v: 1, tipo: 'proyector', id: 'aaaaaaaaaaaa' }, { canal: 'yondo-presentacion', v: 2, tipo: 'proyector', id: 'bbbbbbbbbbbb' },
  { canal: 'yondo-presentacion', v: 1, tipo: 'proyector', id: 'X' }, { canal: 'yondo-presentacion', v: 1, tipo: 'hecho', para: 'nadie', nro: 1 },
  { canal: 'yondo-presentacion', v: 1, tipo: 'ordenes', de: 'cccccccccccc', nro: 1, acciones: [] }]) raro.postMessage(m);
await dormir(20);
r.raros_sin_efecto = enProyector.length === 1;
// 6. El proyector se cierra: avisa y la otra pestaña deja de mandarle
quitarB();
await dormir(20);
r.tras_adios = A.proyectorVivo();
// 7. Un proyector que se cerró sin avisar (el «adios» no llegó): no acusa recibo, se da por cerrado y la orden se aplica
// en esta pestaña, que abre la vista, sin esperar el plazo de la respuesta
raro.postMessage({ canal: 'yondo-presentacion', v: 1, tipo: 'proyector', id: 'dddddddddddd', estado: null });
await dormir(20);
r.fantasma_vivo = A.proyectorVivo();
navegadas.length = 0;
location.pathname = '/panel/personas';
const aplicadasA = [];
const estadoA = { capitulo: 'vivienda', paso: 3, total: 6, nombre: 'Vivienda', titulo: 'Tres', explicacion: false };
const controlA = { estado: () => estadoA,
  aplicar: async (l) => { aplicadasA.push(l.map((a) => `${a.op}:${a.capitulo || ''}`)); return l.map((a) => ({ op: a.op, ok: true })); } };
let quitarA = null;
const t0 = Date.now();
r.sin_acuse = await A.accionesPresentacion([ir('pedidos', 1)], { navegar: (ruta) => { navegar(ruta); quitarA = A.registrarPresentacion(controlA); } });
r.sin_acuse_ms = Date.now() - t0;
r.sin_acuse_navego = navegadas.slice();
r.fantasma_tras = A.proyectorVivo();
r.aplicadas_aqui = aplicadasA.slice();
// 8. Un proyector recién abierto arranca en el capítulo y el paso de la vista de esta pestaña, con su explicación
await A.accionesPresentacion([{ tipo: 'presentacion', op: 'explicar', explicacion: 'Lo que dice la pantalla' }]);
estadoA.explicacion = true;
const C = await import(modulo + '?pestana=proyector2');
const enC = [];
const quitarC = C.registrarPresentacion({ proyector: true, estado: () => estadoB,
  aplicar: async (l) => { enC.push(l); return l.map((a) => ({ op: a.op, ok: true })); } });
await dormir(40);
r.sincronizado = enC.slice();
// Sin explicación en pantalla, solo el paso; y al que ya estaba (sus latidos no son de recién abierto) no se le manda más
estadoA.explicacion = false;
const E = await import(modulo + '?pestana=proyector3');
const enE = [];
const quitarE = E.registrarPresentacion({ proyector: true, estado: () => estadoB,
  aplicar: async (l) => { enE.push(l); return l.map((a) => ({ op: a.op, ok: true })); } });
await dormir(40);
r.sincronizado_sin_explicacion = enE.slice();
r.latidos_no_sincronizan = enC.length === 1;
quitarC(); quitarE(); quitarA?.();
await dormir(20);
// 9. El proyector manda (el caso del verificador): la vista de aquí en Vivienda 3 con una explicación, el proyector se
// abre en ese paso, «Siguiente» deja las dos en el 4; el paso cambia allá con el teclado (el 5) y la vista de aquí y su
// barra lo siguen; «Siguiente» de aquí deja las dos en el 6. Una presentación de mentira que se mueve como mando.js
const caps = { portada: 1, vivienda: 6, salud: 4 };
const orden = Object.keys(caps);
const mover = (e, a) => {
  const antes = `${e.capitulo}/${e.paso}`;
  if (a.op === 'ir') { e.capitulo = a.capitulo; e.paso = a.paso || 1; }
  else if (a.op === 'siguiente' || a.op === 'anterior') {
    let ci = orden.indexOf(e.capitulo), p = e.paso + (a.op === 'siguiente' ? 1 : -1);
    if (p > caps[orden[ci]]) { if (ci < orden.length - 1) { ci++; p = 1; } else p = caps[orden[ci]]; }
    if (p < 1) { if (ci > 0) { ci--; p = caps[orden[ci]]; } else p = 1; }
    e.capitulo = orden[ci]; e.paso = p;
  }
  e.total = caps[e.capitulo];
  if (a.explicacion) { e.explicacion = true; e.texto = a.explicacion; }
  else if (a.op === 'quitar_explicacion' || `${e.capitulo}/${e.paso}` !== antes) { e.explicacion = false; e.texto = null; }
};
const presentacion = (e, registro, avisar) => ({ estado: () => ({ ...e, texto: undefined }),
  aplicar: async (l) => { registro.push(l.map((a) => `${a.op}:${a.capitulo || ''}${a.paso || ''}:${a.explicacion || ''}`));
    await dormir(3); for (const a of l) mover(e, a); avisar?.(); return l.map((a) => ({ op: a.op, ok: true })); } });
const hasta = async (f) => { const fin = Date.now() + 5000; while (!f() && Date.now() < fin) await dormir(5); return f(); };
const donde = (e) => `${e.capitulo}/${e.paso}${e.explicacion ? `+${e.texto}` : ''}`;
const estadoL = { capitulo: 'portada', paso: 1, total: 1, nombre: 'Aquí', titulo: 'T', explicacion: false, texto: null };
const enL = [], barra = [];
const quitarL = A.registrarPresentacion({ ...presentacion(estadoL, enL),
  cambio: () => { const e = A.estadoPresentacion(); barra.push(e ? `${e.capitulo}/${e.paso}` : null); } });
await A.accionesPresentacion([{ tipo: 'presentacion', op: 'ir', capitulo: 'vivienda', paso: 3, explicacion: 'Las casas nuevas' }]);
const P9 = await import(modulo + '?pestana=proyector4');
const estadoP = { capitulo: 'portada', paso: 1, total: 1, nombre: 'Allá', titulo: 'T', explicacion: false, texto: null };
const enP = [];
const quitarP = P9.registrarPresentacion({ proyector: true, ...presentacion(estadoP, enP, () => P9.avisarEstado()) });
const r9 = r.proyector_manda = {};
r9.abre = await hasta(() => donde(estadoP) === 'vivienda/3+Las casas nuevas') && donde(estadoP);
await dormir(30);
r9.aqui_no_fue_a_la_portada = !enL.flat().some((x) => x.startsWith('ir:portada'));
// «Siguiente» de los botones de aquí: la orden va solo al proyector, la vista de aquí lo sigue con un `ir`
enL.length = 0;
r9.siguiente = await A.accionesPresentacion([{ tipo: 'presentacion', op: 'siguiente' }]);
r9.tras_siguiente = await hasta(() => donde(estadoL) === 'vivienda/4') && [donde(estadoP), donde(estadoL)];
r9.aqui_sin_relativas = enL.slice();
// El teclado (o el control remoto) en la ventana del proyector: allá pasa al 5 sin que esta pestaña mande nada
enL.length = 0;
barra.length = 0;
mover(estadoP, { op: 'siguiente' });
P9.avisarEstado();
r9.tras_teclado = await hasta(() => donde(estadoL) === 'vivienda/5') && [donde(estadoP), donde(estadoL)];
r9.estado_tras_teclado = A.estadoPresentacion();
r9.barra_tras_teclado = barra.at(-1);
r9.aqui_tras_teclado = enL.slice();
// Y «Siguiente» de aquí otra vez: las dos en el 6
r9.siguiente_2 = await A.accionesPresentacion([{ tipo: 'presentacion', op: 'siguiente' }]);
r9.tras_siguiente_2 = await hasta(() => donde(estadoL) === 'vivienda/6') && [donde(estadoP), donde(estadoL)];
r9.barra_tras_siguiente_2 = barra.at(-1);
// La explicación que manda esta pestaña también se ve aquí; la que se pierde allá al cambiar de paso, también aquí
await A.accionesPresentacion([{ tipo: 'presentacion', op: 'explicar', explicacion: 'Otra frase' }]);
r9.explicada = await hasta(() => donde(estadoL) === 'vivienda/6+Otra frase') && [donde(estadoP), donde(estadoL)];
mover(estadoP, { op: 'siguiente' });
P9.avisarEstado();
r9.otro_capitulo = await hasta(() => donde(estadoL) === 'salud/1') && [donde(estadoP), donde(estadoL)];
// La persona usa la presentación de aquí (su control, su teclado, su índice): el proyector va adonde ella la llevó, con
// una orden absoluta (si no, la de aquí volvería al paso del proyector con su latido siguiente)
enP.length = 0;
mover(estadoL, { op: 'anterior' });
A.avisarEstado();
r9.aqui_lleva = await hasta(() => donde(estadoP) === 'vivienda/6') && [donde(estadoP), donde(estadoL)];
r9.al_proyector_absoluta = enP.slice();
await dormir(30);
r9.sigue_junta = [donde(estadoP), donde(estadoL)];
// Lo que el proyector dice de antes (su latido o la respuesta a una orden anterior) se cruza con lo que se le lleva: la
// vista de aquí no vuelve al paso viejo para después ir otra vez al nuevo (saltaba, y en un equipo lento eran segundos)
enL.length = 0;
mover(estadoL, { op: 'anterior' });
A.avisarEstado();
P9.avisarEstado();   // todavía en el 6: aplica la orden unos milisegundos después
r9.cruce = await hasta(() => donde(estadoP) === 'vivienda/5') && [donde(estadoP), donde(estadoL)];
await dormir(30);
r9.cruce_sin_vuelta = enL.slice();
r9.cruce_junta = [donde(estadoP), donde(estadoL)];
// El proyector se cierra: la barra vuelve a la vista de aquí, que quedó en su paso
quitarP();
r9.tras_cerrar = await hasta(() => !A.proyectorVivo()) && A.estadoPresentacion();
r9.barra_tras_cerrar = barra.at(-1);
quitarL();
r.tipos_del_canal = [...new Set(crudos.map((m) => m.tipo))].sort();
r.nadie_manda_a_todos = crudos.every((m) => m.canal === 'yondo-presentacion' && m.v === 1);
console.log(JSON.stringify(r));
"""


@requiere_node
def test_puente_cola_navegacion_y_proyector(tmp_path):
    (tmp_path / "puente.mjs").write_text(GUION_PUENTE, encoding="utf-8")
    p = subprocess.run(["node", str(tmp_path / "puente.mjs"), PUENTE_JS.as_uri()], capture_output=True, text=True,
                       timeout=60)
    assert p.returncode == 0, p.stderr
    r = json.loads(p.stdout.strip().splitlines()[-1])
    assert r["exports"] == ["CANAL", "MAX_EXPLICACION", "VERSION", "accionPresentacion", "accionesEnCola",
                            "accionesPresentacion", "avisarEstado", "estadoPresentacion", "estadoValido",
                            "presentacionLista", "presentacionNoDisponible", "proyectorVivo", "registrarPresentacion"]
    assert r["navegadas"] == ["/presentacion"] and r["en_cola"] == 2 and r["lista_antes"] is False
    assert r["estado_sin_vista"] is None and r["registro_invalido"] == "function"
    assert r["aplicadas"] == [["ir"], ["explicar"], ["siguiente"]]
    assert r["resultados"] == [[{"op": "ir", "ok": True}], [{"op": "explicar", "ok": True}],
                               [{"op": "siguiente", "ok": True}]]
    # El estado sale limpio (sin claves de más ni caracteres de control) y nunca lanza
    assert r["estado"] == {"capitulo": "vivienda", "paso": 3, "total": 6, "nombre": "Vivienda", "titulo": "Paso  tres",
                           "explicacion": True}
    assert r["estado_que_lanza"] is None and r["proyector_sin_nadie"] is False
    assert r["cerrada"] == "La presentación se cerró antes de aplicar el cambio"
    assert r["vencida"] == "La presentación no terminó de cargar" and r["no_navego_en_la_vista"] is True
    assert r["en_cola_tras_abrir"] == 1
    assert r["otra_vista"] == "Se abrió otra vista antes de que la presentación terminara de cargar"
    assert r["sin_sitio"] == "La presentación no está en este servidor"
    # Proyector: recibe las órdenes válidas, la mal formada vuelve como error sin aplicarse y no se navega
    assert r["proyector_vivo"] is True and r["el_proyector_no_se_ve_a_si_mismo"] is False
    assert r["al_proyector"] == [{"op": "ir", "ok": True}, {"op": "ir", "ok": False, "error": "Acción no válida"},
                                 {"op": "ir", "ok": False}]
    assert r["en_proyector"] == [["ir", "ir"]] and r["navego_con_proyector"] == []
    assert r["estado_del_proyector"] == {"capitulo": "aguas", "paso": 2, "total": 5, "nombre": "Aguas",
                                         "titulo": "Así funciona hoy", "explicacion": False}
    assert r["raros_sin_efecto"] is True and r["tras_adios"] is False
    # El proyector que se cerró sin avisar: en unos segundos (no los 15 del plazo de la respuesta) la orden se aplica aquí,
    # una sola vez, abriendo la vista
    assert r["fantasma_vivo"] is True and r["fantasma_tras"] is False
    assert r["sin_acuse"] == [{"op": "ir", "ok": True}] and r["aplicadas_aqui"] == [["ir:pedidos"]], r
    assert r["sin_acuse_navego"] == ["/presentacion"] and 2000 <= r["sin_acuse_ms"] < 6000, r["sin_acuse_ms"]
    # El proyector recién abierto arranca donde está la pestaña del chat (y con su explicación)
    assert r["sincronizado"] == [[{"tipo": "presentacion", "op": "ir", "capitulo": "vivienda", "paso": 3,
                                   "explicacion": "Lo que dice la pantalla"}]]
    assert r["sincronizado_sin_explicacion"] == [[{"tipo": "presentacion", "op": "ir", "capitulo": "vivienda", "paso": 3}]]
    assert r["latidos_no_sincronizan"] is True
    # El proyector manda: el paso que cambia allá (el teclado, el control remoto) lo sigue la vista de aquí y su barra, y
    # los botones de aquí le mandan la orden solo a él (la vista de aquí no repite la relativa: va con un `ir` al paso
    # que él dice). Antes el iframe de aquí se quedaba en el 4, la barra decía «Paso 4» y el proyector estaba en el 5
    v = r["proyector_manda"]
    assert v["abre"] == "vivienda/3+Las casas nuevas" and v["aqui_no_fue_a_la_portada"] is True, v
    assert v["siguiente"] == [{"op": "siguiente", "ok": True}], v
    assert v["tras_siguiente"] == ["vivienda/4", "vivienda/4"] and v["aqui_sin_relativas"] == [["ir:vivienda4:"]], v
    assert v["tras_teclado"] == ["vivienda/5", "vivienda/5"] and v["aqui_tras_teclado"] == [["ir:vivienda5:"]], v
    assert v["estado_tras_teclado"]["paso"] == 5 and v["barra_tras_teclado"] == "vivienda/5", v
    assert v["tras_siguiente_2"] == ["vivienda/6", "vivienda/6"] and v["barra_tras_siguiente_2"] == "vivienda/6", v
    assert v["explicada"] == ["vivienda/6+Otra frase", "vivienda/6+Otra frase"], v
    assert v["otro_capitulo"] == ["salud/1", "salud/1"], v
    # Y al revés: lo que la persona hace en la presentación de aquí va al proyector como un `ir`
    assert v["aqui_lleva"] == ["vivienda/6", "vivienda/6"] and v["al_proyector_absoluta"] == [["ir:vivienda6:"]], v
    assert v["sigue_junta"] == ["vivienda/6", "vivienda/6"], v
    # El estado viejo del proyector que se cruza con lo que se le lleva no hace volver atrás a la vista de aquí
    assert v["cruce"] == ["vivienda/5", "vivienda/5"] and v["cruce_sin_vuelta"] == [], v
    assert v["cruce_junta"] == ["vivienda/5", "vivienda/5"], v
    assert v["tras_cerrar"]["capitulo"] == "vivienda" and v["barra_tras_cerrar"] == "vivienda/5", v
    assert r["tipos_del_canal"] == ["adios", "hecho", "ordenes", "proyector", "quien", "recibido"]
    assert r["nadie_manda_a_todos"] is True


GUION_MANDO = r"""// El mando de la presentación sin navegador: ventana, documento y marco padre falsos. Uso: node <guion> <url de mando.js>
const [modulo] = process.argv.slice(2);
const M = await import(modulo);
const clases = () => { const s = new Set(); return { add: (c) => s.add(c), remove: (c) => s.delete(c), contains: (c) => s.has(c), toggle: (c, v) => (v ? s.add(c) : s.delete(c)) }; };
function armar({ propio = 'https://sitio.example', panel = 'https://panel.example', enIframe = true } = {}) {
  const oyentes = {};
  const enviados = [];
  const padre = { postMessage: (m, o) => enviados.push([structuredClone(m), o]) };
  const ventana = { location: { origin: propio }, addEventListener: (t, f) => { (oyentes[t] ||= []).push(f); },
    matchMedia: () => ({ matches: false }), innerWidth: 1400 };
  ventana.parent = enIframe ? padre : ventana;
  const p = { textContent: '' };
  const sub = { classList: clases(), querySelector: () => p, getBoundingClientRect: () => ({ height: 40 }) };
  const pres = { classList: clases(), style: { setProperty: () => {}, removeProperty: () => {} } };
  const enlaces = [{ target: '', rel: '' }];
  const documento = {
    querySelector: (s) => ({ '#pres': pres, '.subtitulo': sub, '.leyenda3d': { childElementCount: 0 }, '.panel': null,
      'meta[name="panel-origen"]': panel ? { content: panel } : null })[s] ?? null,
    querySelectorAll: (s) => (s === '.barra a[href]' ? enlaces : []),
  };
  const caps = [{ id: 'portada', nombre: 'Portada', pasos: [{ titulo: 'Inicio' }, { titulo: 'Territorio' }] },
    { id: 'vivienda', nombre: 'Vivienda', pasos: [{ titulo: 'Uno' }, { titulo: 'Dos\xa0casas' }, { titulo: 'Tres' }] }];
  const estado = { ci: -1, pi: -1 };
  const idas = [];
  const paso = () => (oyentes['propuesta:paso'] || []).forEach((f) => f({}));
  const ir = async (ci, pi) => { idas.push([ci, pi]); estado.ci = ci; estado.pi = pi; paso(); };
  const vecino = (ci, pi, d) => { pi += d; if (pi >= caps[ci].pasos.length) { if (ci < caps.length - 1) { ci++; pi = 0; } else pi = caps[ci].pasos.length - 1; } if (pi < 0) { if (ci > 0) { ci--; pi = caps[ci].pasos.length - 1; } else pi = 0; } return [ci, pi]; };
  let indice = 0, reencuadres = 0;
  const mando = M.montarMando({ caps, estado, ir, vecino, abrirIndice: () => { indice++; }, reencuadrar: () => { reencuadres++; }, ventana, documento });
  const mensaje = async (data, { origen = 'https://panel.example', fuente = padre } = {}) => {
    const antes = enviados.length;
    for (const f of oyentes.message || []) f({ data, origin: origen, source: fuente });
    await new Promise((ok) => setTimeout(ok, 5));
    return enviados.slice(antes);
  };
  return { mando, oyentes, enviados, padre, sub, p, estado, idas, ir, mensaje, enlaces, indice: () => indice, reencuadres: () => reencuadres };
}
const r = {};
const O = (orden, extra = {}) => ({ canal: 'yondo-presentacion', v: 1, orden, ...extra });
// Sin iframe no escucha nada; sin un origen permitido tampoco
const solo = armar({ enIframe: false });
r.solo = { mando: solo.mando, oyentes: Object.keys(solo.oyentes) };
r.sin_origen = armar({ propio: 'null', panel: 'http://panel.example' }).mando;
r.origenes = [...M.origenesPermitidos({ location: { origin: 'https://s.example' } }, { querySelector: () => ({ content: 'https://p.example' }) })];
r.origenes_malos = [...M.origenesPermitidos({ location: { origin: 'null' } }, { querySelector: () => ({ content: 'javascript:x' }) })];
// El origen del panel con mayúsculas o «:443» queda como lo entrega el navegador en e.origin
r.origenes_normalizados = ['https://Panel.Example', 'https://panel.example:443', 'HTTPS://PANEL.EXAMPLE:8443', 'https://panel.example:99999']
  .map((content) => [...M.origenesPermitidos({ location: { origin: 'null' } }, { querySelector: () => ({ content }) })]);
const mayus = armar({ panel: 'https://Panel.Example:443' });
await mayus.ir(0, 0);
r.con_mayusculas = (await mayus.mensaje(O('estado', { id: 3 }), { origen: 'https://panel.example' })).map(([m, o]) => [m.tipo, m.id, o]);
const t = armar();
r.enlaces = t.enlaces;
// El primer paso: avisa «listo» a los dos orígenes permitidos (el navegador solo se lo entrega al del marco padre)
await t.ir(0, 0);
r.listo = t.enviados.map(([m, o]) => [m.tipo, o, m.capitulo, m.paso, m.total, m.titulo]);
// Mensajes que se ignoran (ni responden): otra ventana, otro origen, «null», otro canal u otra versión, no objeto
r.ignorados = [
  await t.mensaje(O('estado'), { fuente: {} }), await t.mensaje(O('estado'), { origen: 'https://malo.example' }),
  await t.mensaje(O('estado'), { origen: 'null' }), await t.mensaje({ ...O('estado'), canal: 'otro' }),
  await t.mensaje({ ...O('estado'), v: 2 }), await t.mensaje(['estado']), await t.mensaje('estado'),
].map((x) => x.length);
// Órdenes válidas
const a = await t.mensaje(O('ir', { capitulo: 'vivienda', paso: 2, id: 7 }));
r.ir = a.map(([m, o]) => [m.tipo, o, m.id ?? null, m.capitulo, m.paso, m.titulo]);
r.idas = t.idas.slice();
r.indice_cerrado = t.indice();
const b = await t.mensaje(O('avanzar', { d: 1, id: 8, explicacion: '  El tercer   paso.  ' }));
r.avanzar = b.filter(([m]) => m.id === 8).map(([m]) => [m.tipo, m.capitulo, m.paso, m.explicacion]);
r.subtitulo = [t.sub.classList.contains('visible'), t.p.textContent];
await t.mensaje(O('ir', { capitulo: 'portada', id: 9 }));
r.cambio_de_paso_quita_el_subtitulo = !t.sub.classList.contains('visible');
const c = await t.mensaje(O('explicar', { explicacion: '<img src=x onerror="window.__xss=1"> como texto', id: 10 }));
r.explicar = [c.map(([m]) => m.tipo), t.sub.classList.contains('visible'), t.p.textContent];
await t.mensaje(O('quitar_explicacion', { id: 11 }));
r.quitada = t.sub.classList.contains('visible');
// Órdenes que no mueven nada: responden error con su id
const idasAntes = t.idas.length;
const malas = [O('borrar'), O('constructor'), O('__proto__'), O('ir', { capitulo: 'marte' }), O('ir', { capitulo: 'Vivienda' }),
  O('ir', { capitulo: 'vivienda', paso: 9 }), O('ir', { capitulo: 'vivienda', paso: true }), O('ir', { capitulo: 'vivienda', paso: '2' }),
  O('ir', { capitulo: 'vivienda', ruta: '/x' }), O('avanzar', { d: 2 }), O('avanzar', {}), O('explicar'),
  O('explicar', { explicacion: 'Al revés \u{202e}odot' }), O('explicar', { explicacion: 'Llame al 3001234567' }),
  O('explicar', { explicacion: 'ana@correo.co' }), O('explicar', { explicacion: 'x'.repeat(221) }),
  O('explicar', { explicacion: 'Al 300 - 123 - 4567' }), O('explicar', { explicacion: 'ana\uff20correo.co' }),
  O('explicar', { explicacion: { toString: 'x' } }), O('quitar_explicacion', { explicacion: 'x' }), O(7)];
r.malas = [];
for (const [i, m] of malas.entries()) {
  const res = await t.mensaje({ ...m, id: 100 + i });
  r.malas.push(res.map(([x, o]) => [x.tipo, x.id, o, typeof x.error === 'string' && x.error.length > 0]));
}
r.malas_no_mueven = t.idas.length === idasAntes && !t.sub.classList.contains('visible');
r.estado_orden = (await t.mensaje(O('estado', { id: 'no es un número' }))).map(([m]) => [m.tipo, 'id' in m]);
r.texto = ['Hola  mundo ', ' ', '\u0000x', 'Teléfono 300 123 4567', 'Año 2028–2031, $106.271 M', 'a@b', 'ok ❤', 'ok ❤\u{fe0f}'].map((x) => M.textoVisible(x));
console.log(JSON.stringify(r));
"""


@requiere_node
def test_mando_de_la_presentacion_con_node(tmp_path):
    (tmp_path / "mando.mjs").write_text(GUION_MANDO, encoding="utf-8")
    p = subprocess.run(["node", str(tmp_path / "mando.mjs"), MANDO_JS.as_uri()], capture_output=True, text=True,
                       timeout=60)
    assert p.returncode == 0, p.stderr
    r = json.loads(p.stdout.strip().splitlines()[-1])
    assert r["solo"] == {"mando": None, "oyentes": []} and r["sin_origen"] is None
    assert r["origenes"] == ["https://s.example", "https://p.example"] and r["origenes_malos"] == []
    assert r["origenes_normalizados"] == [["https://panel.example"], ["https://panel.example"],
                                          ["https://panel.example:8443"], []]
    # Con la meta «https://Panel.Example:443», la orden del panel (e.origin = https://panel.example) sí se atiende
    assert r["con_mayusculas"] == [["estado", 3, "https://panel.example"]]
    assert r["enlaces"] == [{"target": "_blank", "rel": "noopener"}]
    assert r["listo"] == [["listo", "https://sitio.example", "portada", 1, 2, "Inicio"],
                          ["listo", "https://panel.example", "portada", 1, 2, "Inicio"]]
    assert r["ignorados"] == [0] * 7
    # La respuesta va solo al origen que mandó la orden, con su id; el aviso del paso también va ahí
    assert r["ir"] == [["estado", "https://panel.example", None, "vivienda", 2, "Dos casas"],
                       ["estado", "https://panel.example", 7, "vivienda", 2, "Dos casas"]]
    assert r["idas"] == [[0, 0], [1, 1]] and r["indice_cerrado"] == 1
    assert r["avanzar"] == [["estado", "vivienda", 3, True]]
    assert r["subtitulo"] == [True, "El tercer paso."] and r["cambio_de_paso_quita_el_subtitulo"] is True
    assert r["explicar"] == [["estado"], True, '<img src=x onerror="window.__xss=1"> como texto']
    assert r["quitada"] is False
    for i, res in enumerate(r["malas"]):
        assert res == [["error", 100 + i, "https://panel.example", True]], (i, res)
    assert r["malas_no_mueven"] is True
    assert r["estado_orden"] == [["estado", False]]
    assert r["texto"] == ["Hola mundo", None, None, None, "Año 2028–2031, $106.271 M", None, "ok ❤", None]


# ───────────────────────────── En Chromium ─────────────────────────────

@pytest.fixture
def panel_con_sitio(cfg, tmp_path, monkeypatch):
    """El servidor único de verdad (uvicorn, el panel en /panel) con el sitio que arma build_site.py en una carpeta
    temporal: la presentación real, con su CSP. Devuelve (base del panel, app del panel)."""
    from conftest import MONGO, URI
    if not MONGO:
        pytest.skip("No hay MongoDB para las pruebas con navegador")
    if not PROPUESTA_JSON.is_file():
        pytest.skip("Sin web/data/propuesta.json")
    import pymongo
    import uvicorn

    import servidor
    _build_site(monkeypatch).construir(RAIZ / "web", tmp_path / "site")
    app = servidor.crear_servidor(cfg, tmp_path / "site")
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    srv = uvicorn.Server(uvicorn.Config(app, http="h11", lifespan="on", log_level="warning", access_log=False,
                                        server_header=False, timeout_graceful_shutdown=2))
    hilo = threading.Thread(target=srv.run, kwargs={"sockets": [sock]}, daemon=True)
    hilo.start()
    try:
        fin = time.time() + 20
        while time.time() < fin and not (srv.started and app.state.panel is not None
                                         and getattr(app.state.panel.state, "listo", False)):
            time.sleep(0.05)
        assert srv.started and app.state.panel is not None, "el servidor no arrancó"
        yield f"http://127.0.0.1:{sock.getsockname()[1]}/panel", app.state.panel
    finally:
        srv.should_exit = True
        hilo.join(15)
        sock.close()
        with pymongo.MongoClient(URI) as m:
            m.drop_database(cfg.mongodb_db)


EXPLICACION = "Las <b>300 viviendas</b> nuevas van en dos lotes del casco urbano."
EXPLICACION_2 = "La torre del hospital y los puestos de salud rurales."

GUION_NAVEGADOR = r"""// El asistente presenta la propuesta en Chromium. Uso: node <guion> <base del panel> <usuario> <clave> <datos> <capturas>
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const [base, usuario, clave, datos, capturas] = process.argv.slice(2);
const D = JSON.parse(datos);
const origen = new URL(base).origin;
const pref = new URL(base).pathname.replace(/\/+$/, '');
const espera = { timeout: 90000 };
const salida = { csp: [], errores: [], consola: [], cortadas: [] };

async function contexto(nav, opciones) {
  const ctx = await nav.newContext(opciones);
  // Aquí no hay internet: las letras de Google se cortan; cualquier otra cosa de fuera se anota
  await ctx.route((u) => u.origin !== origen, (r) => {
    if (!/^https:\/\/fonts\.(googleapis|gstatic)\.com\//.test(r.request().url())) salida.cortadas.push(r.request().url().slice(0, 120));
    return r.abort();
  });
  // En todos los marcos (también el iframe de la presentación)
  await ctx.exposeBinding('__csp', (_, v) => salida.csp.push(v));
  await ctx.addInitScript(() => {
    addEventListener('securitypolicyviolation', (e) => window.__csp(`${location.pathname} ${e.effectiveDirective} ${e.blockedURI}`), true);
  });
  const page = await ctx.newPage();
  page.on('pageerror', (e) => salida.errores.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error' && !/^Failed to load resource/.test(m.text())) salida.consola.push(m.text().slice(0, 300)); });
  return { ctx, page };
}

async function entrar(page, ruta) {
  await page.goto(base + '/', { waitUntil: 'domcontentloaded' });
  await page.fill('#f-login [name=usuario]', usuario);
  await page.fill('#f-login [name=clave]', clave);
  await page.click('#f-login button[type=submit]');
  await page.waitForSelector('#app #vista > .vista', espera);
  await page.waitForSelector('#agente-boton:not([hidden])', espera);
  if (ruta !== '/') { await page.goto(base + ruta, { waitUntil: 'domcontentloaded' }); await page.waitForSelector('#app #vista > .vista', espera); }
  await page.evaluate(async () => { window.__P = await import(new URL('agente-presentacion.js', document.querySelector('script[type=module]').src).href); });
}

async function enviar(page, texto) {
  if (await page.locator('#agente-panel').isHidden()) await page.click('#agente-boton');
  await page.fill('#agente-texto', texto);
  await page.press('#agente-texto', 'Enter');
  await page.waitForFunction(() => document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);
}

const marco = (page) => page.frames().find((f) => /\/propuesta(#|$)/.test(f.url()));
async function enLaPresentacion(page, hash, explicacion) {
  await page.waitForFunction(() => !!document.querySelector('#pres-iframe'), null, espera);
  let f = null;
  const fin = Date.now() + 90000;
  while (!(f = marco(page)) && Date.now() < fin) await page.waitForTimeout(200);
  await f.waitForFunction(([h, t]) => location.hash === h && (t === null
    ? !document.querySelector('.subtitulo').classList.contains('visible')
    : document.querySelector('.subtitulo.visible p')?.textContent === t), [hash, explicacion], espera);
  await page.waitForTimeout(2500);   // el telón y el encuadre del paso
  const dentro = await f.evaluate(() => {
    const caja = (s) => { const e = document.querySelector(s); if (!e) return null; const b = e.getBoundingClientRect(); return b.width ? { l: b.left, t: b.top, r: b.right, b: b.bottom } : null; };
    const p = document.querySelector('.subtitulo p');
    return { hash: location.hash, texto: p.textContent, hijos: p.children.length, xss: !!window.__xss,
      sub: caja('.subtitulo.visible'), leyenda: document.querySelector('.leyenda3d').childElementCount ? caja('.leyenda3d') : null,
      panel: caja('.panel'), control: caja('.control'), w: innerWidth, h: innerHeight,
      desborde: document.scrollingElement.scrollWidth > innerWidth };
  });
  const fuera = await page.evaluate(() => {
    const caja = (s) => { const e = document.querySelector(s); if (!e || e.hidden) return null; const b = e.getBoundingClientRect(); return b.width ? { l: b.left, r: b.right } : null; };
    return { ruta: location.pathname, desborde: document.scrollingElement.scrollWidth > innerWidth, barra: document.querySelector('#pres-paso')?.textContent,
      iframe: caja('#pres-iframe'), asistente: caja('#agente-panel'), estado: window.__P.estadoPresentacion() };
  });
  return { dentro, fuera };
}

(async () => {
  const nav = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  try {
    // Escritorio: en la vista Presentación, el asistente va a Vivienda con su explicación y luego explica otra cosa
    {
      const { ctx, page } = await contexto(nav, { viewport: { width: 1400, height: 900 } });
      await entrar(page, '/presentacion');
      await page.waitForFunction(() => window.__P.presentacionLista(), null, espera);
      await enviar(page, 'Muéstrame las viviendas nuevas');
      // Con el asistente cerrado, la presentación tiene todo el ancho (su diseño de pantalla grande)
      await page.click('#agente-cerrar');
      salida.escritorio_ir = await enLaPresentacion(page, '#vivienda/3', D.explicacion);
      salida.escritorio_ir.ancho = await marco(page).evaluate(() => innerWidth);
      await page.screenshot({ path: `${capturas}/presentacion-escritorio.png` });
      await enviar(page, 'Ahora ve a salud');
      salida.escritorio_salud = await enLaPresentacion(page, '#salud/2', D.explicacion_2);
      await page.screenshot({ path: `${capturas}/presentacion-escritorio-asistente.png` });
      salida.escritorio_notas = await page.evaluate(() => [...document.querySelectorAll('.agente-nota')].map((n) => n.textContent));
      await ctx.close();
    }
    // Celular: desde Habitantes, la acción abre la presentación, pliega el asistente y aplica al quedar lista
    {
      const { ctx, page } = await contexto(nav, { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
      await entrar(page, '/personas');
      await enviar(page, 'Presenta la parte de salud');
      salida.celular = await enLaPresentacion(page, '#salud/2', D.explicacion_2);
      salida.celular.plegado = await page.evaluate(() => document.querySelector('#agente-panel').hidden);
      await page.screenshot({ path: `${capturas}/presentacion-celular.png` });
      await ctx.close();
    }
  } finally {
    await nav.close();
  }
  console.log(JSON.stringify(salida));
})().catch((e) => { console.error(e); process.exit(1); });
"""


def _sin_choque(a: dict, b: dict | None) -> bool:
    return b is None or a["r"] <= b["l"] or b["r"] <= a["l"] or a["b"] <= b["t"] or b["b"] <= a["t"]


@requiere_navegador
def test_el_asistente_maneja_la_presentacion_en_chromium(panel_con_sitio, cfg, tmp_path):
    base, panel = panel_con_sitio
    aa.encender(panel,
                aa.sse(aa.TU("toolu_p1", "presentacion", {"op": "ir", "capitulo": "vivienda", "paso": 3,
                                                          "explicacion": EXPLICACION}), stop="tool_use"),
                aa.sse(aa.T("Listo: las viviendas nuevas.")),
                aa.sse(aa.TU("toolu_p2", "presentacion", {"op": "ir", "capitulo": "salud", "paso": 2,
                                                          "explicacion": EXPLICACION_2}), stop="tool_use"),
                aa.sse(aa.T("Listo: salud.")),
                aa.sse(aa.TU("toolu_p3", "presentacion", {"op": "ir", "capitulo": "salud", "paso": 2,
                                                          "explicacion": EXPLICACION_2}), stop="tool_use"),
                aa.sse(aa.T("Listo: salud, en el celular.")))
    (tmp_path / "presentacion.cjs").write_text(GUION_NAVEGADOR, encoding="utf-8")
    capturas = os.environ.get("CAPTURAS_AGENTE") or str(tmp_path)
    datos = json.dumps({"explicacion": EXPLICACION, "explicacion_2": EXPLICACION_2})
    r = subprocess.run(["node", str(tmp_path / "presentacion.cjs"), base, cfg.usuario, cfg.clave, datos, capturas],
                       capture_output=True, text=True, timeout=400)
    assert r.returncode == 0, (r.stdout[-3000:], r.stderr[-3000:])
    s = json.loads(r.stdout.strip().splitlines()[-1])
    assert s["csp"] == [] and s["errores"] == [] and s["consola"] == [], (s["csp"], s["errores"], s["consola"])
    assert s["cortadas"] == [], s["cortadas"]
    for nombre in ("escritorio_ir", "escritorio_salud", "celular"):
        d, f = s[nombre]["dentro"], s[nombre]["fuera"]
        # El subtítulo es texto: las etiquetas se ven tal cual y no corre nada
        assert d["hijos"] == 0 and not d["xss"], nombre
        assert not d["desborde"] and not f["desborde"], nombre
        assert f["ruta"] == "/panel/presentacion" and f["estado"]["capitulo"] == d["hash"][1:].split("/")[0], nombre
        # No tapa la leyenda, el panel ni el control de la presentación, y queda dentro de la pantalla
        assert d["sub"] and 0 <= d["sub"]["l"] and d["sub"]["r"] <= d["w"] and d["sub"]["b"] <= d["h"], (nombre, d)
        for otro in ("leyenda", "panel", "control"):
            assert _sin_choque(d["sub"], d[otro]), (nombre, otro, d)
    assert s["escritorio_ir"]["dentro"]["texto"] == EXPLICACION
    assert s["escritorio_ir"]["fuera"]["barra"].startswith("Paso 3 de")
    # En pantalla grande, a la derecha del panel de la presentación y junto a la leyenda
    d = s["escritorio_ir"]["dentro"]
    assert s["escritorio_ir"]["ancho"] > 1080 and d["sub"]["l"] > d["panel"]["r"], d
    # Con el asistente abierto en pantalla ancha, el iframe le deja su ancho
    f = s["escritorio_salud"]["fuera"]
    assert f["asistente"] and f["iframe"]["r"] <= f["asistente"]["l"], f
    assert not [n for n in s["escritorio_notas"] if "no aplicó" in n], s["escritorio_notas"]
    # En el celular el asistente se plegó para que se vea la presentación entera, sobre la hoja inferior
    c = s["celular"]["dentro"]
    assert s["celular"]["plegado"] is True and c["sub"]["b"] <= c["panel"]["t"], c


# La explicación más larga que acepta la herramienta (220 caracteres): tiene que verse entera en cualquier pantalla
LARGA = ("Las trescientas viviendas van en dos lotes del casco urbano: doscientas de interés prioritario en diez bloques "
         "junto al colegio y cien casas de dos pisos en el borde occidental (Lote 2), con su parque y su salón comunal.")
CORTA = "Una frase corta para la sala."

GUION_PANTALLAS = r"""// La explicación entera en cada pantalla, el asistente entre 901 y 1199 px y los cambios sin guardar. Uso: node <guion>
// <base del panel> <usuario> <clave> <datos> <capturas>
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const [base, usuario, clave, datos, capturas] = process.argv.slice(2);
const D = JSON.parse(datos);
const origen = new URL(base).origin;
const pref = new URL(base).pathname.replace(/\/+$/, '');
const espera = { timeout: 90000 };
const salida = { casos: {}, csp: [], errores: [] };

async function contexto(nav, opciones) {
  const ctx = await nav.newContext(opciones);
  await ctx.route((u) => u.origin !== origen, (r) => r.abort());   // sin internet: la letra de respaldo
  await ctx.exposeBinding('__csp', (_, v) => salida.csp.push(v));
  await ctx.addInitScript(() => {
    addEventListener('securitypolicyviolation', (e) => window.__csp(`${location.pathname} ${e.effectiveDirective} ${e.blockedURI}`), true);
  });
  const page = await ctx.newPage();
  page.on('pageerror', (e) => salida.errores.push(String(e)));
  return { ctx, page };
}

async function entrar(page, ruta) {
  await page.goto(base + '/', { waitUntil: 'domcontentloaded' });
  await page.fill('#f-login [name=usuario]', usuario);
  await page.fill('#f-login [name=clave]', clave);
  await page.click('#f-login button[type=submit]');
  await page.waitForSelector('#app #vista > .vista', espera);
  await page.waitForSelector('#agente-boton:not([hidden])', espera);
  await page.goto(base + ruta, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#app #vista > .vista', espera);
  await page.evaluate(async () => { window.__P = await import(new URL('agente-presentacion.js', document.querySelector('script[type=module]').src).href); });
}

const marco = (page) => page.frames().find((f) => /\/propuesta(#|$)/.test(f.url()));

// Se mide con el diseño quieto, no tras un tiempo fijo: las letras cargadas (o fallidas) y las cajas que importan sin
// moverse ni transiciones en curso durante varios cuadros seguidos, en el panel y en la presentación
async function quieto(f) {
  await f.evaluate(() => new Promise((ok) => {
    const sel = ['.subtitulo', '.subtitulo p', '.panel', '.leyenda3d', '.control', '.barra', '.riel', '.telon .banda', '#pres-iframe', '#agente-panel'];
    let antes = '', iguales = 0;
    const fin = Date.now() + 30000;
    const cuadro = () => {
      const els = sel.map((s) => document.querySelector(s));
      const anima = els.some((e) => e?.getAnimations?.().length);
      const telon = document.querySelector('.telon');
      const ahora = els.map((e) => { const b = e?.getBoundingClientRect(); return b ? [b.left, b.top, b.width, b.height].map(Math.round).join(',') : '-'; }).join('|')
        + (telon ? `|${getComputedStyle(telon).opacity}${getComputedStyle(telon).visibility}` : '');
      iguales = !anima && ahora === antes ? iguales + 1 : 0;
      antes = ahora;
      if (iguales >= 15 || Date.now() > fin) ok(); else requestAnimationFrame(cuadro);
    };
    document.fonts.ready.then(() => requestAnimationFrame(cuadro));
  }));
}

async function enPresentacion(page, hash, texto) {
  await page.waitForFunction(() => !!document.querySelector('#pres-iframe'), null, espera);
  let f = null;
  const fin = Date.now() + 90000;
  while (!(f = marco(page)) && Date.now() < fin) await page.waitForTimeout(200);
  await f.waitForFunction(([h, t]) => location.hash === h && document.querySelector('.subtitulo.visible p')?.textContent === t,
    [hash, texto], espera);
  await quieto(f);
  await quieto(page);
  return f;
}

// En la presentación: el subtítulo, lo que no debe tapar y la franja donde escena.js encuadra la obra (`zonaPx`, con
// las mismas reglas: debajo de la barra y de la leyenda de arriba, encima del control y del subtítulo, a la derecha del
// panel de lado, y nunca menos de 90 px de alto)
const medirDentro = (f) => f.evaluate(() => {
  const caja = (e) => { if (!e || getComputedStyle(e).display === 'none') return null; const b = e.getBoundingClientRect(); return b.width && b.height ? { l: b.left, t: b.top, r: b.right, b: b.bottom } : null; };
  const pres = document.querySelector('#pres'), sub = document.querySelector('.subtitulo'), p = sub.querySelector('p');
  const ley = document.querySelector('.leyenda3d'), cs = getComputedStyle(p);
  const panel = pres.classList.contains('sin-panel') ? null : caja(document.querySelector('.panel'));
  const W = innerWidth, H = innerHeight;
  let x0 = 0, x1 = W, y0 = 0, y1 = H;
  const bl = ley.childElementCount ? ley.getBoundingClientRect() : null;
  if (bl?.height && bl.top > H / 2) y1 = Math.min(y1, bl.top - 8); else if (bl?.height) y0 = Math.max(y0, bl.bottom + 6);
  const bar = document.querySelector('.barra').getBoundingClientRect(), ctl = document.querySelector('.control').getBoundingClientRect();
  y0 = Math.max(y0, bar.bottom + 6); y1 = Math.min(y1, ctl.top - 6);
  if (panel) { if (panel.r - panel.l < W * 0.7) x0 = Math.max(x0, panel.r + 16); else y1 = Math.min(y1, panel.t - 8); }
  const riel = caja(document.querySelector('.riel'));
  if (riel && riel.r - riel.l > W * 0.7) y0 = Math.max(y0, riel.b + 4);
  const s = caja(sub);
  if (s) y1 = Math.min(y1, s.t - 8);
  if (x1 - x0 < W * 0.25) { x0 = 0; x1 = W; }
  const libre = y1 - y0;   // el alto que le queda a la obra antes de que escena.js lo estire a 90 (tapando lo de abajo)
  if (y1 - y0 < 90) y1 = Math.min(H, y0 + 90);
  return { w: W, h: H, texto: p.textContent, visible: sub.classList.contains('visible') && getComputedStyle(sub).visibility === 'visible',
    clamp: cs.webkitLineClamp || 'none', corte: cs.overflow === 'hidden' && p.scrollHeight > p.clientHeight + 1,
    renglones: Math.round(p.getBoundingClientRect().height / parseFloat(cs.lineHeight)), letra: parseFloat(cs.fontSize), libre,
    sub: s, panel, leyenda: bl?.height ? caja(ley) : null, control: caja(document.querySelector('.control')),
    marca: caja(document.querySelector('.marca')), herr: caja(document.querySelector('.herr')),
    riel: riel && riel.r - riel.l > 0 ? riel : null, zona: { l: x0, t: y0, r: x1, b: y1 },
    desborde: document.scrollingElement.scrollWidth > W };
});
const medirFuera = (page) => page.evaluate(() => {
  const caja = (s) => { const e = document.querySelector(s); if (!e || e.hidden) return null; const b = e.getBoundingClientRect(); return b.width ? { l: b.left, t: b.top, r: b.right, b: b.bottom } : null; };
  const cab = document.querySelector('#agente-panel .agente-cab');
  return { iframe: caja('#pres-iframe'), asistente: caja('#agente-panel'), desborde: document.scrollingElement.scrollWidth > innerWidth,
    cab_desborda: !!cab && cab.offsetParent !== null && cab.scrollWidth > cab.clientWidth + 1,
    botones_cab: [...document.querySelectorAll('#agente-panel .agente-cab button')].filter((b) => b.offsetParent).map((b) => { const r = b.getBoundingClientRect(); const p = cab.getBoundingClientRect(); return r.left >= p.left - 1 && r.right <= p.right + 1; }) };
});

const PANTALLAS = [
  ['1400x900', { viewport: { width: 1400, height: 900 } }],
  ['1024x768', { viewport: { width: 1024, height: 768 } }],
  ['820x1180', { viewport: { width: 820, height: 1180 }, isMobile: true, hasTouch: true }],
  ['390x844', { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }],
  ['360x640', { viewport: { width: 360, height: 640 }, isMobile: true, hasTouch: true }],
  ['320x568', { viewport: { width: 320, height: 568 }, isMobile: true, hasTouch: true }],
  ['915x412', { viewport: { width: 915, height: 412 }, isMobile: true, hasTouch: true }],
  ['844x390', { viewport: { width: 844, height: 390 }, isMobile: true, hasTouch: true }],
  ['740x360', { viewport: { width: 740, height: 360 }, isMobile: true, hasTouch: true }],
  ['667x375', { viewport: { width: 667, height: 375 }, isMobile: true, hasTouch: true }],
];

(async () => {
  const nav = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  try {
    for (const [nombre, opciones] of PANTALLAS) {
      const { ctx, page } = await contexto(nav, opciones);
      await entrar(page, '/presentacion');
      await page.waitForFunction(() => window.__P.presentacionLista(), null, espera).catch(async (e) => {
        // Para que un fallo diga dónde quedó: en qué pantalla, qué dice la barra de la vista y en qué va el iframe
        const vista = await page.evaluate(() => ({ barra: document.querySelector('#pres-paso')?.textContent,
          iframe: !!document.querySelector('#pres-iframe') })).catch(() => null);
        const f = marco(page);
        const dentro = f ? await f.evaluate(() => ({ hash: location.hash, listo: document.readyState,
          paso: document.querySelector('.panel h2')?.textContent || null })).catch((x) => String(x)) : null;
        throw new Error(`${nombre}: la presentación no quedó lista (${e.message.split('\n')[0]}): ${JSON.stringify({ vista, dentro, errores: salida.errores.slice(-5) })}`);
      });
      const caso = salida.casos[nombre] = {};
      caso.resultado = await page.evaluate((t) => window.__P.accionesPresentacion([{ tipo: 'presentacion', op: 'ir', capitulo: 'vivienda', paso: 3, explicacion: t }]), D.larga);
      let f = await enPresentacion(page, '#vivienda/3', D.larga);
      caso.dentro = await medirDentro(f);
      caso.fuera = await medirFuera(page);
      await page.screenshot({ path: `${capturas}/explicacion-${nombre}.png` });
      // Entre 901 y 1199 px, también con el asistente abierto: el iframe le deja su ancho y la explicación sigue entera
      if (nombre === '1024x768') {
        await page.click('#agente-boton');
        await page.waitForSelector('#agente-panel:not([hidden])', espera);
        f = await enPresentacion(page, '#vivienda/3', D.larga);
        caso.abierto = { dentro: await medirDentro(f), fuera: await medirFuera(page) };
        await page.screenshot({ path: `${capturas}/explicacion-${nombre}-asistente.png` });
      }
      await ctx.close();
    }
    // 1180×820 (una tableta en horizontal) con el asistente abierto
    {
      const { ctx, page } = await contexto(nav, { viewport: { width: 1180, height: 820 } });
      await entrar(page, '/presentacion');
      await page.waitForFunction(() => window.__P.presentacionLista(), null, espera);
      await page.click('#agente-boton');
      await page.waitForSelector('#agente-panel:not([hidden])', espera);
      await page.evaluate((t) => window.__P.accionesPresentacion([{ tipo: 'presentacion', op: 'ir', capitulo: 'vivienda', paso: 3, explicacion: t }]), D.larga);
      const f = await enPresentacion(page, '#vivienda/3', D.larga);
      salida.casos['1180x820'] = { abierto: { dentro: await medirDentro(f), fuera: await medirFuera(page) } };
      await ctx.close();
    }
    // Con cambios sin guardar, dos órdenes en un turno (ir y explicar): un solo aviso, y su botón aplica las dos
    {
      const { ctx, page } = await contexto(nav, { viewport: { width: 1400, height: 900 } });
      await entrar(page, '/personas');
      await page.evaluate(async () => { const a = await import(new URL('api.js', document.querySelector('script[type=module]').src).href); window.__sucio = true; a.registrarPendiente(() => window.__sucio); });
      if (await page.locator('#agente-panel').isHidden()) await page.click('#agente-boton');
      await page.fill('#agente-texto', 'Muestra la vivienda y explícala');
      await page.press('#agente-texto', 'Enter');
      await page.waitForFunction(() => document.querySelector('#agente-panel').dataset.estado === 'listo', null, espera);
      const sucio = salida.sucio = {};
      sucio.ruta = await page.evaluate(() => location.pathname);
      sucio.notas = await page.evaluate(() => [...document.querySelectorAll('.agente-nota')].map((n) => n.textContent).filter((t) => t.includes('cambios sin guardar')));
      sucio.botones = await page.locator('.agente-nota button', { hasText: 'Abrir de todos modos' }).count();
      await page.locator('.agente-nota button', { hasText: 'Abrir de todos modos' }).first().click();
      const f = await enPresentacion(page, '#vivienda/2', D.corta);
      sucio.despues = { ruta: await page.evaluate(() => location.pathname), hash: await f.evaluate(() => location.hash),
        texto: await f.evaluate(() => document.querySelector('.subtitulo.visible p')?.textContent || null),
        botones: await page.locator('.agente-nota button', { hasText: 'Abrir de todos modos' }).count(),
        fallas: await page.evaluate(() => [...document.querySelectorAll('.agente-nota')].map((n) => n.textContent).filter((t) => t.includes('no aplicó'))) };
      await ctx.close();
    }
  } finally {
    await nav.close();
  }
  console.log(JSON.stringify(salida));
})().catch((e) => { console.error(e); process.exit(1); });
"""


@requiere_navegador
def test_la_explicacion_se_ve_entera_en_cada_pantalla(panel_con_sitio, cfg, tmp_path):
    """La explicación más larga (220 caracteres) se ve entera (sin recorte de renglones) y dentro de la pantalla, sin
    tapar el panel de la presentación, su leyenda, su control ni su barra, en escritorio, tableta, celular y celular en
    horizontal. En el celular, en vertical (390×844, 360×640, 320×568) y en horizontal (915×412, 844×390, 740×360,
    667×375), además, sin tapar la franja donde la cámara encuadra la obra, y el panel conserva su alto: de lado, al
    menos 140 px (antes, con la explicación, quedaba en 2 px a 915×412); la hoja de abajo, al menos 56. Entre 901 y
    1199 px el asistente abierto no tapa la presentación. Y con cambios sin guardar, el `ir` y el `explicar` de un mismo
    turno dan un solo aviso cuyo «Abrir de todos modos» aplica los dos, en orden. Con la letra de respaldo que haya (en
    el CI, DejaVu Sans, más ancha): las medidas se toman con el diseño quieto."""
    base, panel = panel_con_sitio
    aa.encender(panel,
                aa.sse(aa.TU("toolu_s1", "presentacion", {"op": "ir", "capitulo": "vivienda", "paso": 2}),
                       aa.TU("toolu_s2", "presentacion", {"op": "explicar", "explicacion": CORTA}), stop="tool_use"),
                aa.sse(aa.T("Listo.")))
    assert len(LARGA) == hi.MAX_EXPLICACION and P.validar({"op": "explicar", "explicacion": LARGA}).explicacion == LARGA
    (tmp_path / "pantallas.cjs").write_text(GUION_PANTALLAS, encoding="utf-8")
    capturas = os.environ.get("CAPTURAS_AGENTE") or str(tmp_path)
    r = subprocess.run(["node", str(tmp_path / "pantallas.cjs"), base, cfg.usuario, cfg.clave,
                        json.dumps({"larga": LARGA, "corta": CORTA}), capturas], capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, (r.stdout[-3000:], r.stderr[-3000:])
    s = json.loads(r.stdout.strip().splitlines()[-1])
    assert s["csp"] == [] and s["errores"] == [], (s["csp"], s["errores"])
    medidas = [(n, c["dentro"]) for n, c in s["casos"].items() if "dentro" in c]
    medidas += [(f"{n} con el asistente", c["abierto"]["dentro"]) for n, c in s["casos"].items() if "abierto" in c]
    assert len(medidas) == 12
    for nombre, d in medidas:
        assert d["visible"] and d["texto"] == LARGA, nombre
        # Entera: sin recorte de renglones y con toda la caja dentro de la pantalla
        assert d["clamp"] in ("none", "") and not d["corte"], (nombre, d)
        assert d["sub"] and 0 <= d["sub"]["l"] and d["sub"]["r"] <= d["w"] and 0 <= d["sub"]["t"] and d["sub"]["b"] <= d["h"], (nombre, d)
        assert not d["desborde"], nombre
        for otro in ("panel", "leyenda", "control", "marca", "herr", "riel"):
            assert _sin_choque(d["sub"], d[otro]), (nombre, otro, d)
        # Y nada de lo que la rodea se pisa: la leyenda (de lado, en la barra) ni el control al pie del panel
        for a, b in (("leyenda", "marca"), ("leyenda", "herr"), ("panel", "control")):
            assert d[a] is None or _sin_choque(d[a], d[b]), (nombre, a, b, d)
    # El celular, en vertical y en horizontal: el subtítulo no tapa la franja donde la cámara encuadra la obra que
    # explica (al menos 90 px sin estirarla por debajo de él, que es lo que hace escena.js si le queda menos), y el panel
    # de la presentación conserva un alto útil. La letra puede achicarse, pero no por debajo de lo que se lee
    problemas = []
    for nombre, minimo in (("390x844", 96), ("360x640", 96), ("320x568", 56), ("915x412", 140), ("844x390", 140),
                           ("740x360", 140), ("667x375", 140)):
        d = s["casos"][nombre]["dentro"]
        if not _sin_choque(d["sub"], d["zona"]) or d["libre"] < 90:
            problemas.append((nombre, "tapa la franja de la obra", {"sub": d["sub"], "zona": d["zona"], "libre": d["libre"]}))
        if d["zona"]["r"] - d["zona"]["l"] < d["w"] * 0.4:
            problemas.append((nombre, "franja angosta", d["zona"]))
        if d["panel"]["b"] - d["panel"]["t"] < minimo:
            problemas.append((nombre, f"panel de menos de {minimo} px", d["panel"]))
        if d["letra"] < 10.5:
            problemas.append((nombre, "letra de menos de 10,5 px", d["letra"]))
    assert not problemas, problemas
    for nombre, c in s["casos"].items():
        if "resultado" in c:
            assert c["resultado"] == [{"op": "ir", "ok": True}], (nombre, c["resultado"])
    # En pantalla grande, a la derecha del panel y a lo sumo tres renglones al lado de la leyenda: si no, encima de ella
    d = s["casos"]["1400x900"]["dentro"]
    assert d["sub"]["l"] > d["panel"]["r"], d
    assert d["renglones"] <= 3 or d["leyenda"] is None or d["sub"]["b"] <= d["leyenda"]["t"], d
    # Entre 901 y 1199 px, con el asistente abierto, el iframe le deja su ancho; el asistente cabe entero
    for nombre in ("1024x768", "1180x820"):
        f = s["casos"][nombre]["abierto"]["fuera"]
        assert f["asistente"] and f["iframe"]["r"] <= f["asistente"]["l"], (nombre, f)
        assert f["iframe"]["r"] - f["iframe"]["l"] >= 320 and not f["desborde"], (nombre, f)
        assert not f["cab_desborda"] and f["botones_cab"] and all(f["botones_cab"]), (nombre, f)
    # Con cambios sin guardar: un solo aviso con un solo botón; al tocarlo, el paso y su explicación
    v = s["sucio"]
    assert v["ruta"] == "/panel/personas" and len(v["notas"]) == 1 and v["botones"] == 1, v
    assert v["despues"]["ruta"] == "/panel/presentacion" and v["despues"]["hash"] == "#vivienda/2", v
    assert v["despues"]["texto"] == CORTA and v["despues"]["botones"] == 0 and v["despues"]["fallas"] == [], v


# ───────────────────────────── El proyector y la pestaña del chat ─────────────────────────────

GUION_PROYECTOR = r"""// La ventana del proyector y la pestaña del chat no se desfasan. Uso: node <guion> <base del panel> <usuario> <clave>
// <datos>
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const [base, usuario, clave, datos] = process.argv.slice(2);
const D = JSON.parse(datos);
const origen = new URL(base).origin;
const pref = new URL(base).pathname.replace(/\/+$/, '');
const espera = { timeout: 90000 };
const salida = { pasos: {}, errores: [], csp: [] };
const marco = (page) => page.frames().find((f) => /\/propuesta(#|$)/.test(f.url()));

async function enPaso(page, hash, texto) {
  await page.waitForFunction(() => !!document.querySelector('#pres-iframe'), null, espera);
  let f = null;
  const fin = Date.now() + 90000;
  while (!(f = marco(page)) && Date.now() < fin) await page.waitForTimeout(100);
  await f.waitForFunction(([h, t]) => location.hash === h && (t === null
    ? !document.querySelector('.subtitulo').classList.contains('visible')
    : document.querySelector('.subtitulo.visible p')?.textContent === t), [hash, texto], espera);
}

// Lo que ve cada pantalla y lo que dice la barra de la pestaña del chat
async function foto(A, B) {
  const dentro = (page) => marco(page).evaluate(() => ({ hash: location.hash,
    sub: document.querySelector('.subtitulo').classList.contains('visible') ? document.querySelector('.subtitulo p').textContent : null }));
  return { chat: await dentro(A), proyector: await dentro(B),
    barra: await A.evaluate(() => document.querySelector('#pres-paso').textContent),
    estado: await A.evaluate(() => window.__P.estadoPresentacion()),
    aviso: await A.evaluate(() => !document.querySelector('#pres-remoto').hidden) };
}

// Las dos pantallas en `hash` y la barra del chat diciendo ese paso: se espera a que pase (sin tiempos fijos), con un
// tope; si no pasa, la foto dice dónde quedó cada una
async function ambos(A, B, hash) {
  const paso = hash.split('/')[1];
  const tope = { timeout: 60000 };
  await Promise.all([
    marco(B).waitForFunction((h) => location.hash === h, hash, tope),
    marco(A).waitForFunction((h) => location.hash === h, hash, tope),
    A.waitForFunction((p) => document.querySelector('#pres-paso').textContent.startsWith(`Paso ${p} de`), paso, tope),
  ]).catch(() => {});
  return foto(A, B);
}

(async () => {
  const nav = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  try {
    const ctx = await nav.newContext({ viewport: { width: 1400, height: 900 } });
    await ctx.route((u) => u.origin !== origen, (r) => r.abort());
    await ctx.exposeBinding('__csp', (_, v) => salida.csp.push(v));
    await ctx.addInitScript(() => {
      addEventListener('securitypolicyviolation', (e) => window.__csp(`${location.pathname} ${e.effectiveDirective} ${e.blockedURI}`), true);
    });
    ctx.on('page', (p) => p.on('pageerror', (e) => salida.errores.push(String(e))));
    const A = await ctx.newPage();
    await A.goto(base + '/', { waitUntil: 'domcontentloaded' });
    await A.fill('#f-login [name=usuario]', usuario);
    await A.fill('#f-login [name=clave]', clave);
    await A.click('#f-login button[type=submit]');
    await A.waitForSelector('#app #vista > .vista', espera);
    await A.goto(base + '/presentacion', { waitUntil: 'domcontentloaded' });
    await A.waitForSelector('#app #vista > .vista', espera);
    await A.evaluate(async (p) => { window.__P = await import(p + '/static/js/agente-presentacion.js'); }, pref);
    await A.waitForFunction(() => window.__P.presentacionLista(), null, espera);
    // La vista del chat en Vivienda 3 con una explicación; «Abrir en otra pantalla» abre el proyector en ese paso
    await A.evaluate((t) => window.__P.accionesPresentacion([{ tipo: 'presentacion', op: 'ir', capitulo: 'vivienda', paso: 3, explicacion: t }]), D.explicacion);
    await enPaso(A, '#vivienda/3', D.explicacion);
    const [B] = await Promise.all([ctx.waitForEvent('page'), A.click('#pres-otra')]);
    await enPaso(B, '#vivienda/3', D.explicacion);
    await A.waitForFunction(() => window.__P.proyectorVivo() && !document.querySelector('#pres-remoto').hidden, null, espera);
    salida.pasos.abre = await foto(A, B);
    // «Siguiente» en la pestaña del chat. Como hace una persona, la ventana que se usa pasa al frente: Chromium frena la
    // que queda detrás (sus cuadros bajan a unos dos por segundo y cada paso de la presentación tarda segundos en ella)
    await A.bringToFront();
    await A.click('#pres-siguiente');
    salida.pasos.siguiente = await ambos(A, B, '#vivienda/4');
    // El paso cambia en la ventana del proyector (el control remoto manda PageDown; la vista enfoca el iframe para eso)
    await B.bringToFront();
    await B.evaluate(() => document.querySelector('#pres-iframe').focus());
    await B.keyboard.press('PageDown');
    salida.pasos.teclado = await ambos(A, B, '#vivienda/5');
    // Y otra vez «Siguiente» en la pestaña del chat: las dos al 6
    await A.bringToFront();
    await A.click('#pres-siguiente');
    salida.pasos.siguiente_2 = await ambos(A, B, '#vivienda/6');
    // Y al revés: lo que se hace en la presentación de la pestaña del chat (aquí, su teclado) va al proyector
    await A.bringToFront();
    await A.evaluate(() => document.querySelector('#pres-iframe').focus());
    await A.keyboard.press('PageUp');
    salida.pasos.aqui = await ambos(A, B, '#vivienda/5');
    await ctx.close();
  } finally {
    await nav.close();
  }
  console.log(JSON.stringify(salida));
})().catch((e) => { console.error(e); process.exit(1); });
"""


@requiere_navegador
def test_el_proyector_y_la_pestana_del_chat_no_se_desfasan(panel_con_sitio, cfg, tmp_path):
    """El caso del verificador, en Chromium con el panel y la presentación de verdad: la vista del chat en Vivienda 3 con
    una explicación; «Abrir en otra pantalla» abre el proyector en ese paso, con la explicación, y «Siguiente» deja las
    dos en el 4. Entonces el paso cambia en la ventana del proyector (PageDown, lo que manda un control remoto): el
    proyector pasa al 5 y la pestaña del chat lo refleja, en su iframe, en su barra y en el estado que le llega al
    asistente. Y «Siguiente» en el chat lleva a las dos al 6. Antes el iframe del chat se quedaba en el 4 con la barra
    en «Paso 4 de 6» y, con «Siguiente», el proyector iba al 6 y el chat al 5: no se reencontraban nunca. Y al revés: lo
    que se hace en la presentación de la pestaña del chat (PageUp) también va al proyector."""
    base, _ = panel_con_sitio
    (tmp_path / "proyector.cjs").write_text(GUION_PROYECTOR, encoding="utf-8")
    r = subprocess.run(["node", str(tmp_path / "proyector.cjs"), base, cfg.usuario, cfg.clave,
                        json.dumps({"explicacion": EXPLICACION})], capture_output=True, text=True, timeout=400)
    assert r.returncode == 0, (r.stdout[-3000:], r.stderr[-3000:])
    s = json.loads(r.stdout.strip().splitlines()[-1])
    assert s["csp"] == [] and s["errores"] == [], (s["csp"], s["errores"])
    p = s["pasos"]
    assert p["abre"]["chat"] == p["abre"]["proyector"] == {"hash": "#vivienda/3", "sub": EXPLICACION}, p["abre"]
    assert p["abre"]["aviso"] is True and p["abre"]["barra"].startswith("Paso 3 de 6"), p["abre"]
    for nombre, paso in (("siguiente", 4), ("teclado", 5), ("siguiente_2", 6), ("aqui", 5)):
        f = p[nombre]
        # Las dos pantallas en el mismo paso (sin la explicación del 3, que se quita al cambiar de paso), y la barra y el
        # estado del chat diciendo el paso que ve la sala
        assert f["chat"] == f["proyector"] == {"hash": f"#vivienda/{paso}", "sub": None}, (nombre, f)
        assert f["barra"].startswith(f"Paso {paso} de 6"), (nombre, f)
        assert f["estado"]["capitulo"] == "vivienda" and f["estado"]["paso"] == paso, (nombre, f)


# ───────────────────────────── Una presentación que no avisa `listo` ─────────────────────────────

PROPUESTA_MUDA = """<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Muda</title></head><body>
<div id="pres"><h2>Portada</h2></div>
<script>
// No manda `listo` (como si se hubiera perdido, o como si hubiera llegado antes de que el panel escuchara): solo
// contesta cuando le preguntan en qué paso está
addEventListener('message', (e) => {
  if (e.source !== parent || e.origin !== location.origin) return;
  const m = e.data;
  if (!m || m.canal !== 'yondo-presentacion' || m.v !== 1 || m.orden !== 'estado') return;
  window.__preguntas = (window.__preguntas || 0) + 1;
  parent.postMessage({ canal: 'yondo-presentacion', v: 1, tipo: 'estado', capitulo: 'portada', paso: 1, total: 1,
    nombre: 'Portada', titulo: 'Yondó 2028–2031', explicacion: false }, e.origin);
});
</script></body></html>"""

GUION_MUDA = r"""// La vista queda lista con la respuesta a «estado», sin `listo`. Uso: node <guion> <base del panel> <usuario> <clave>
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const [base, usuario, clave] = process.argv.slice(2);
const pref = new URL(base).pathname.replace(/\/+$/, '');
(async () => {
  const nav = await chromium.launch();
  const salida = { csp: [], errores: [] };
  try {
    const ctx = await nav.newContext({ viewport: { width: 1280, height: 800 } });
    await ctx.route((u) => u.origin !== new URL(base).origin, (r) => r.abort());
    await ctx.exposeBinding('__csp', (_, v) => salida.csp.push(v));
    await ctx.addInitScript(() => { addEventListener('securitypolicyviolation', (e) => window.__csp(`${location.pathname} ${e.effectiveDirective}`), true); });
    const page = await ctx.newPage();
    page.on('pageerror', (e) => salida.errores.push(String(e)));
    await page.goto(base + '/', { waitUntil: 'domcontentloaded' });
    await page.fill('#f-login [name=usuario]', usuario);
    await page.fill('#f-login [name=clave]', clave);
    await page.click('#f-login button[type=submit]');
    await page.waitForSelector('#app #vista > .vista', { timeout: 30000 });
    await page.goto(base + '/presentacion', { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('#pres-iframe', { timeout: 30000 });
    await page.evaluate(async () => { window.__P = await import(new URL('agente-presentacion.js', document.querySelector('script[type=module]').src).href); });
    const t0 = Date.now();
    salida.lista = await page.waitForFunction(() => window.__P.presentacionLista(), null, { timeout: 20000 }).then(() => true, () => false);
    salida.segundos = (Date.now() - t0) / 1000;
    salida.barra = await page.textContent('#pres-paso');
    salida.siguiente_activo = await page.isEnabled('#pres-siguiente');
    const f = page.frames().find((x) => /\/propuesta(#|$)/.test(x.url()));
    salida.preguntas = f ? await f.evaluate(() => window.__preguntas || 0) : null;
    await ctx.close();
  } finally {
    await nav.close();
  }
  console.log(JSON.stringify(salida));
})().catch((e) => { console.error(e); process.exit(1); });
"""


@requiere_navegador
def test_la_vista_queda_lista_aunque_no_llegue_el_listo(cfg, tmp_path):
    """Si el `listo` de la presentación se pierde (salió antes de que la vista escuchara) o tarda más que el plazo, la
    vista no se rinde: le pregunta su estado al cargar y cada poco, y con la respuesta queda lista; el plazo solo avisa
    que tarda y deja el iframe (antes lo quitaba, y en un equipo lento la presentación no se podía usar sin recargar)."""
    from conftest import MONGO, URI
    if not MONGO:
        pytest.skip("No hay MongoDB para las pruebas con navegador")
    import pymongo
    import uvicorn

    import servidor
    sitio = tmp_path / "site"
    sitio.mkdir()
    (sitio / "index.html").write_text("<!doctype html><title>Inicio</title>INICIO", encoding="utf-8")
    (sitio / "propuesta.html").write_text(PROPUESTA_MUDA, encoding="utf-8")
    app = servidor.crear_servidor(cfg, sitio)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    srv = uvicorn.Server(uvicorn.Config(app, http="h11", lifespan="on", log_level="warning", access_log=False,
                                        server_header=False, timeout_graceful_shutdown=2))
    hilo = threading.Thread(target=srv.run, kwargs={"sockets": [sock]}, daemon=True)
    hilo.start()
    try:
        fin = time.time() + 20
        while time.time() < fin and not (srv.started and app.state.panel is not None
                                         and getattr(app.state.panel.state, "listo", False)):
            time.sleep(0.05)
        assert srv.started and app.state.panel is not None, "el servidor no arrancó"
        (tmp_path / "muda.cjs").write_text(GUION_MUDA, encoding="utf-8")
        base = f"http://127.0.0.1:{sock.getsockname()[1]}/panel"
        r = subprocess.run(["node", str(tmp_path / "muda.cjs"), base, cfg.usuario, cfg.clave],
                           capture_output=True, text=True, timeout=180)
        assert r.returncode == 0, (r.stdout[-3000:], r.stderr[-3000:])
        s = json.loads(r.stdout.strip().splitlines()[-1])
        assert s["csp"] == [] and s["errores"] == [], s
        assert s["lista"] and s["preguntas"] >= 1, s
        assert s["barra"].startswith("Paso 1 de 1") and s["siguiente_activo"], s
    finally:
        srv.should_exit = True
        hilo.join(15)
        sock.close()
        with pymongo.MongoClient(URI) as m:
            m.drop_database(cfg.mongodb_db)
