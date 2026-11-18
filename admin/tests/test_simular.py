"""`simular`: el asistente y los agentes por MCP accionan los controles de adentro de los modelos del atlas (la magnitud
del simulador sísmico, hacerlo temblar, el piso, el 4D del BIM…) en un paso del plan y en la op `visual` suelta; sin un
modelo del atlas a la vista, los de la maqueta 3D (la hora, el día, las luces, el partido: test_simulaciones_maqueta.py
prueba el resto de ese camino).

El camino entero, sin navegador: el catálogo en el guion (`controles` de cada inmersión), la forma absoluta de la escena
(app/recorrido.py), la pantalla en off (app/pantalla.py: una acción que se hace una vez por versión), la herramienta
(por id o por nombre, tolerante, con avisos legibles) y, con Node, el puente (agente-presentacion.js), el mando
(web/js/propuesta/mando.js: `simular` en las órdenes `escena` y `visual`, con `parcial`) y el reproductor. La prueba en
Chromium contra el atlas real está en test_simulaciones_atlas.py (la de ATLAS) y en el banco de la verificación."""
from __future__ import annotations

import asyncio
import copy
import json
import re
import threading
import time
from pathlib import Path

import pytest

from app import pantalla, recorrido as rec
from app.agente import guion as guion_presentacion
from app.agente.herramientas import interfaz as hi
from app.agente.herramientas.base import ErrorHerramienta
from test_agente_presentacion import requiere_node
from test_pantalla_mcp import _Base, _hacer
from test_plan_guiado import MANDO_JS, NODE_MANDO, PUENTE_JS, REPRODUCTOR_JS, _node

G = guion_presentacion.cargar()
ADMIN = Path(__file__).resolve().parents[1]
UID = 7


def _abierta() -> _Base:
    db = _Base()
    pantalla.marcar_vista(db, UID)
    return db


def _plan(*pasos, titulo="La torre ante un sismo"):
    return {"op": "recorrido", "titulo": titulo, "pasos": list(pasos), "cierre": ["La torre sigue en servicio"]}


SISMO = {"capitulo": "salud", "paso": "torre_sismo", "dice": "Este es el simulador sísmico de la torre."}


# ───────────────────────────── El catálogo en el guion ─────────────────────────────

def test_el_guion_trae_los_controles_de_cada_inmersion_y_los_resuelve_por_id_o_por_nombre():
    sismo = {c["id"]: c for c in G.controles("torre_sismo")}
    assert {"calcular", "reproducir", "magnitud", "escenario", "instante", "cancelar"} <= set(sismo)
    assert sismo["magnitud"] == {**sismo["magnitud"], "tipo": "numero", "min": 4, "max": 8, "paso": 0.1}
    assert sismo["calcular"]["tipo"] == "accion" and sismo["reproducir"]["tipo"] == "si_no"
    assert any(o["id"] == "nido_2015" for o in sismo["escenario"]["opciones"]) and sismo["magnitud"].get("ayuda")
    # el mismo catálogo que copió build_propuesta.py (data/propuesta/simulaciones.json), en texto plano
    fuente = json.loads((ADMIN.parent / "data" / "propuesta" / "simulaciones.json").read_text(encoding="utf-8"))
    for i in G.inmersiones:
        assert [c["id"] for c in i["controles"]] == [c["id"] for c in fuente.get(i["id"], [])], i["id"]
    assert G.controles("torre_hoy") == [] and G.controles("relleno_parque") == [] and G.controles("marte") == []
    assert G.controles(None) == []
    # la maqueta 3D no es una inmersión: sus controles van aparte, por capítulo (el partido, solo en urbanismo)
    assert "maqueta" not in {i["id"] for i in G.inmersiones}
    assert [c["id"] for c in G.controles("maqueta", "urbanismo")] == ["hora", "reproducir_dia", "luces", "partido"]
    # (las luces, solo donde hay luminarias: vivienda y urbanismo)
    assert [c["id"] for c in G.controles("maqueta", "salud")] == ["hora", "reproducir_dia"]
    assert [c["id"] for c in G.controles("maqueta", "vivienda")] == ["hora", "reproducir_dia", "luces"]
    assert G.controles("maqueta", G.por_id("urbanismo")) == G.controles("maqueta", "urbanismo")
    assert G.controles("maqueta") == [] and all("capitulos" not in c for c in G.controles("maqueta", "urbanismo"))
    assert G.control("maqueta", "hora del dia", "salud")["id"] == "hora" and G.control("maqueta", "partido", "salud") is None
    assert G.nombre_modelo("maqueta") == "La maqueta 3D" and G.nombre_modelo("torre_sismo") == "Simulador sísmico"
    assert [o["id"] for o in G.control("maqueta", "hora", "salud")["opciones"]] == ["manana", "tarde", "atardecer", "noche"]
    # por id o por nombre (sin tildes ni mayúsculas), o por las palabras que lo distinguen; si no, None
    assert G.control("torre_sismo", "magnitud")["id"] == "magnitud"
    assert G.control("torre_sismo", "Magnitud de momento (Mw)")["id"] == "magnitud"
    assert G.control("torre_sismo", "hacer temblar la torre")["id"] == "reproducir"
    assert G.control("torre_sismo", "temblar")["id"] == "reproducir"
    assert G.control("torre_sismo", "explotar") is None and G.control("torre_hoy", "magnitud") is None
    assert G.inmersiones_del_capitulo(G.por_id("salud")) == ["torre_pisos", "torre_recorrido", "torre_sismo", "torre_bim"]
    assert G.inmersiones_del_capitulo(G.por_id("vivienda")) == []


def test_lo_que_lee_el_modelo_dice_que_controles_hay():
    # el índice: los ids; la op guion: los controles enteros de las inmersiones del capítulo (no las de otros)
    indice = {i["id"]: i for i in G.indice()["inmersiones"]}
    assert "magnitud" in indice["torre_sismo"]["controles"] and "controles" not in indice["torre_hoy"]
    leer = G.capitulo_para_leer(G.por_id("salud"))
    inm = {i["id"]: i for i in leer["inmersiones"]}
    assert [c["id"] for c in inm["torre_sismo"]["controles"]] == [c["id"] for c in G.controles("torre_sismo")]
    assert "controles" not in inm["torre_laboratorio"] and "controles" not in inm["torre"]   # no son pasos de Salud
    assert all("controles" not in i for i in G.capitulo_para_leer(G.por_id("vivienda"))["inmersiones"])
    assert "recortado" not in leer
    # muy justo, primero las fichas y después la ayuda de los controles
    chico = G.capitulo_para_leer(G.por_id("salud"), tope=20000)
    assert "ayuda" not in chico["inmersiones"][[i["id"] for i in chico["inmersiones"]].index("torre_sismo")]["controles"][0]
    assert "controles" in chico["recortado"]
    # ir a un paso de inmersión devuelve los controles de su modelo
    r = _hacer(_Base(), UID, {"op": "ir", "capitulo": "salud", "paso": "torre_sismo"}, por="asistente")
    assert [c["id"] for c in r.contenido["controles"]] == [c["id"] for c in G.controles("torre_sismo")]
    r = _hacer(_Base(), UID, {"op": "ir", "capitulo": "salud", "paso": 1}, por="asistente")
    assert "controles" not in r.contenido
    # sin un modelo del atlas, los de la maqueta 3D (sin su ayuda: está en guion), y en el índice y en guion por capítulo
    assert [c["id"] for c in r.contenido["controles_maqueta"]] == ["hora", "reproducir_dia"]
    assert all("ayuda" not in c for c in r.contenido["controles_maqueta"])
    r = _hacer(_Base(), UID, {"op": "ir", "capitulo": "urbanismo", "paso": "softbol"}, por="asistente")
    assert [c["id"] for c in r.contenido["controles_maqueta"]] == ["hora", "reproducir_dia", "luces", "partido"]
    assert "controles_maqueta" not in _hacer(_Base(), UID, {"op": "ir", "capitulo": "salud", "paso": "torre_sismo"},
                                             por="asistente").contenido
    assert {c["id"]: c.get("controles_maqueta") for c in G.indice()["capitulos"]}["urbanismo"][-1] == "partido"
    assert all(c.get("ayuda") for c in leer["controles_maqueta"])
    assert all("ayuda" not in c for c in chico["controles_maqueta"])


def test_problemas_revisa_los_controles():
    g = json.loads((ADMIN / "app" / "agente" / "propuesta_guion.json").read_text(encoding="utf-8"))
    assert guion_presentacion.problemas(g) == []
    malo = copy.deepcopy(g)
    sismo = next(i for i in malo["inmersiones"] if i["id"] == "torre_sismo")
    sismo["controles"] += [{"id": "magnitud", "nombre": "Otra", "tipo": "accion"}, {"id": "X", "tipo": "accion"},
                           {"id": "raro", "tipo": "deslizador"}, {"id": "n", "tipo": "numero", "min": 5, "max": 5},
                           {"id": "o", "tipo": "opcion", "opciones": [{"id": "a"}, {"id": "a"}]}]
    p = " | ".join(guion_presentacion.problemas(malo))
    for x in ("control repetido: magnitud", "'X'", "raro: el tipo", "n: un número lleva min y max", "o: las opciones"):
        assert x in p, x
    # derivar descarta lo que no es un control (build_propuesta.py ya lo avisó) y deja el texto plano
    d = guion_presentacion._controles([None, {"id": 3}, {"id": "a", "tipo": "x"},
                                       {"id": "b", "tipo": "numero", "nombre": "B uno", "min": 1, "max": 2, "unidad": "km",
                                        "opciones": [{"id": "z"}]},
                                       {"id": "c", "tipo": "opcion", "opciones": [{"id": "z"}, "w"], "min": 3}])
    assert d == [{"id": "b", "nombre": "B uno", "tipo": "numero", "min": 1, "max": 2, "unidad": "km"},
                 {"id": "c", "nombre": "c", "tipo": "opcion", "opciones": [{"id": "z", "nombre": "z"}]}]


# ───────────────────────────── La forma absoluta (app/recorrido.py) ─────────────────────────────

def test_la_forma_de_simular_y_su_validacion_contra_los_controles():
    s = G.controles("torre_sismo")
    assert rec.MAX_SIMULAR == 4
    assert rec.simular_problemas(None) == [] and rec.simular_problemas(None, []) == []
    bien = [{"control": "magnitud", "valor": 6.5}, {"control": "calcular"}, {"control": "reproducir", "valor": True},
            {"control": "escenario", "valor": "nido_2015"}]
    assert rec.simular_problemas(bien) == [] and rec.simular_problemas(bien, s) == []
    for malo in ([], [{}] * 5, "calcular", [{"control": "Magnitud"}], [{"control": "calcular", "otra": 1}],
                 [{"control": "magnitud", "valor": [1]}], [{"control": "magnitud", "valor": float("nan")}],
                 [{"control": "escenario", "valor": "Nido 2015"}]):
        assert rec.simular_problemas(malo), malo
    for malo, motivo in (([{"control": "magnitud", "valor": 9}], "va de 4 a 8"),
                         ([{"control": "magnitud"}], "le falta el valor"),
                         ([{"control": "calcular", "valor": True}], "es una acción"),
                         ([{"control": "reproducir", "valor": 1}], "verdadero o falso"),
                         ([{"control": "escenario", "valor": "marte"}], "no es una de sus opciones"),
                         ([{"control": "explotar"}], "no es un control del modelo")):
        assert motivo in " ".join(rec.simular_problemas(malo, s)), malo
    assert rec.simular_problemas([{"control": "calcular"}], [])   # sin un modelo con controles, ninguno vale


def test_la_escena_puede_traer_simular_o_no():
    db = _abierta()
    _hacer(db, UID, _plan(SISMO, {"simular": [{"control": "magnitud", "valor": 7}, "calcular"], "dice": "Subimos a siete."}),
           por="mcp")
    guardado = pantalla.recorrido_de(db.pantallas.find_one({"_id": UID}), G)
    e1, e2 = guardado["escenas"]
    assert e1["simular"] is None and e2["simular"] == [{"control": "magnitud", "valor": 7}, {"control": "calcular"}]
    plano = {k: guardado[k] for k in ("id", "titulo", "escenas", "cierre")}
    assert rec.validar(plano, G) == []
    # sin la clave (un plan de antes, la presentación automática), vale igual; `al_dia` la agrega en None
    sin = copy.deepcopy(plano)
    for e in sin["escenas"]:
        e.pop("simular")
    assert rec.validar(sin, G) == [] and all(e["simular"] is None for e in rec.al_dia(sin)["escenas"])
    # en un paso sin modelo del atlas, o con un control que no es de ese modelo, el plan no vale
    malo = copy.deepcopy(plano)
    malo["escenas"][1]["visual"]["inmersion"] = "maqueta"
    assert any("no es un control del modelo" in x for x in rec.validar(malo, G))
    malo = copy.deepcopy(plano)
    malo["escenas"][1]["simular"] = [{"control": "construir", "valor": True}]
    assert rec.validar(malo, G) and rec.validar(malo) == []   # sin guion, solo la forma
    malo["escenas"][1]["simular"] = [{"control": "c"}] * 5
    assert rec.validar(malo)
    # sin un modelo del atlas, contra la maqueta 3D del capítulo: el partido vale en urbanismo, no en salud
    maq = copy.deepcopy(plano)
    maq["escenas"][1].update(capitulo="urbanismo", paso=3, simular=[{"control": "hora", "valor": "noche"},
                                                                   {"control": "partido", "valor": True}])
    maq["escenas"][1]["visual"]["inmersion"] = None
    assert rec.validar(maq, G) == []
    maq["escenas"][1].update(capitulo="salud", paso=1)
    assert any("«partido» no es un control del modelo a la vista" in x for x in rec.validar(maq, G))
    maq["escenas"][1]["simular"] = [{"control": "hora", "valor": "amanecer"}]
    assert any("no es una de sus opciones" in x for x in rec.validar(maq, G))
    maq["escenas"][1]["simular"] = [{"control": "hora", "valor": "mañana"}]   # el id de la opción va sin eñe: manana
    assert any("no es un número, una opción ni verdadero o falso" in x for x in rec.validar(maq, G))
    # lo que queda de una escena: sin la simulación (ya pasó); y se sostiene más (hay algo que mirar)
    assert rec.estado_de_escena(e2)["simular"] is None
    assert e2["sostener_ms"] == rec.SOSTENER_MIRAR_MS


# ───────────────────────────── La herramienta: el plan ─────────────────────────────

def test_el_plan_acciona_por_id_o_por_nombre_y_descarta_con_aviso_lo_que_no_vale():
    db = _abierta()
    r = _hacer(db, UID, _plan(
        SISMO,
        {"simular": [{"control": "Magnitud de momento (Mw)", "valor": "7,04"}, {"control": "calcular"}],
         "dice": "Subimos la magnitud a siete y calculamos."},
        {"simular": [{"control": "hacer temblar la torre"}, {"control": "explotar"},
                     {"control": "escenario", "valor": "Falla de Palestina"}, {"control": "profundidad", "valor": 900},
                     {"control": "suelo", "valor": 300}],
         "dice": "Así tiembla la torre."},
        {"simular": [{"control": "calcular", "valor": 3}, {"control": "reproducir", "valor": "no"},
                     {"control": "velocidad", "valor": "lenta"}, {"control": "exageracion", "valor": 5}],
         "dice": "En cámara lenta."},
        {"simular": [{"control": "magnitud"}, {"control": "reproducir", "valor": "tal vez"}, 7, {"control": "escenario", "valor": "marte"}],
         "dice": "Nada de esto vale."},
        {"capitulo": "salud", "paso": 1, "simular": ["calcular"], "dice": "Volvemos al comienzo."},
        {"inmersion": "torre_hoy", "simular": ["calcular"], "dice": "El predio hoy."},
        {"simular": "calcular", "inmersion": "torre_sismo", "dice": "Otra vez el simulador."},
    ), por="mcp")
    sc = pantalla.recorrido_de(db.pantallas.find_one({"_id": UID}), G)["escenas"]
    assert sc[1]["simular"] == [{"control": "magnitud", "valor": 7}, {"control": "calcular"}]
    # hasta 4 por paso; el que no existe se descarta; la profundidad se recorta a su rango; la opción, por su nombre
    assert sc[2]["simular"] == [{"control": "reproducir", "valor": True}, {"control": "escenario", "valor": "palestina"},
                                {"control": "profundidad", "valor": 200}]
    # una acción con valor se acciona igual; «no» es falso; la opción por su id o su número
    assert sc[3]["simular"] == [{"control": "calcular"}, {"control": "reproducir", "valor": False},
                                {"control": "velocidad", "valor": "lenta"}, {"control": "exageracion", "valor": "5"}]
    assert sc[4]["simular"] is None and sc[5]["simular"] is None and sc[6]["simular"] is None
    assert sc[7]["simular"] == [{"control": "calcular"}]   # (un solo control, como texto, también vale)
    avisos = " | ".join(r.contenido["avisos"])
    for x in ("Paso 3: simular lleva hasta 4 controles", "Paso 3: «Simulador sísmico» no tiene el control «explotar»",
              "controles: calcular, reproducir, magnitud", "Paso 3: simular «profundidad» 900 quedó en 200 (va de 5 a 200 km)",
              "Paso 4: simular «calcular» es una acción", "Paso 5: simular «magnitud» va con un número de 4 a 8",
              "Paso 5: simular «reproducir» va con true o false", "Paso 5: simular: «7» no es un {control, valor}",
              "Paso 5: simular «escenario» no tiene la opción «marte»", "Paso 6: simular acciona los controles del modelo del "
              "atlas abierto y ahí no hay uno", "Paso 7: «El predio hoy» no tiene controles que accionar"):
        assert x in avisos, x
    # lo que ve el modelo de cada paso
    muestra = [p["muestra"] for p in r.contenido["pasos"]]
    assert "acciona: Magnitud de momento (Mw) 7; Calcular el sismo" in muestra[1]
    assert "Escenario sísmico: Falla de Palestina (Mw 7,0); Profundidad del foco 200 km" in muestra[2]
    assert "acciona" not in muestra[4]


def test_el_esquema_y_los_textos_para_el_modelo_lo_nombran():
    s = hi._esquema_presentacion()
    sim = s["properties"]["simular"]
    assert sim["maxItems"] == rec.MAX_SIMULAR and sim["items"]["type"] == "object" and sim["items"]["required"] == ["control"]
    assert {r["type"] for r in sim["items"]["properties"]["valor"]["anyOf"]} == {"boolean", "number", "string"}
    assert s["properties"]["pasos"]["items"]["properties"]["simular"]["items"]["type"] == "object"
    assert len(json.dumps(s, ensure_ascii=False)) < 14000
    assert "simular [{control, valor}]" in hi.D_PRESENTACION and len(hi.D_PRESENTACION) < 1500
    assert "simular [{control, valor}]" in hi.NOTA_GUION
    from app.agente import sistema
    from types import SimpleNamespace
    t = sistema.texto(SimpleNamespace(uid=7, usuario="c", nombre="C", rol="coordinador"), list(hi.HERRAMIENTAS))
    assert "`simular`" in t and "`calcular`, que hace temblar la torre" in t and "cambiar un valor no recalcula" in t
    from app.api import mcp
    assert "sus controles con simular" in mcp.INSTRUCCIONES and len(mcp.D_MCP) < 1500
    # y que sin un modelo del atlas maneja la maqueta (la hora, el día, las luces, el partido), que vuelve a lo del paso
    assert "`reproducir_dia`" in t and "`partido`" in t and "«ponla de noche con las luces encendidas»" in t
    assert "controles_maqueta" in hi.NOTA_GUION and "vuelven a lo del paso" in hi.NOTA_GUION
    assert "la hora de la maqueta" in hi.D_PRESENTACION and "reproducir_dia" in mcp.INSTRUCCIONES
    assert "maqueta" in s["properties"]["simular"]["description"]
    assert "24 s" in hi.SIMULACION_MAQUETA and "vuelven a lo del paso" in hi.SIMULACION_MAQUETA


# ───────────────────────────── La herramienta: la op visual ─────────────────────────────

def test_visual_acciona_en_el_modelo_abierto_y_la_pantalla_lo_hace_una_vez():
    db = _abierta()
    _hacer(db, UID, {"op": "ir", "capitulo": "salud", "paso": "torre_sismo"})
    r = _hacer(db, UID, {"op": "visual", "simular": [{"control": "magnitud", "valor": 6.56}, "calcular"]})
    assert r.resumen == "La presentación muestra en «Simulador sísmico»: Magnitud de momento (Mw) 6,6; Calcular el sismo"
    assert r.contenido["simulacion"] == hi.SIMULACION and "avisos" not in r.contenido and r.acciones == []
    doc = db.pantallas.find_one({"_id": UID})
    e = pantalla.estado(doc, G)
    assert e["simular"] == [{"control": "magnitud", "valor": 6.6}, {"control": "calcular"}]
    assert pantalla.para_pantalla(e, doc, G)["simular"] == e["simular"]
    # ya recibida (la pantalla preguntó), cualquier otra orden la deja en nada (no se repite)
    assert pantalla.entregar(db, UID, None)["simular"] == e["simular"]
    _hacer(db, UID, {"op": "explicar", "explicacion": "La torre resiste."})
    assert pantalla.estado(db.pantallas.find_one({"_id": UID}), G)["simular"] is None
    # con la inmersión en la misma orden, contra la que abre; la que había no cuenta
    _hacer(db, UID, {"op": "ir", "capitulo": "salud", "paso": 1})
    r = _hacer(db, UID, {"op": "visual", "inmersion": "torre_bim", "simular": [{"control": "construir", "valor": True}]})
    assert pantalla.estado(db.pantallas.find_one({"_id": UID}), G)["simular"] == [{"control": "construir", "valor": True}]
    assert r.contenido["inmersion"]["id"] == "torre_bim" and any(c["id"] == "construir" for c in r.contenido["inmersion"]["controles"])
    # sin modelo del atlas a la vista: si era lo único, error con los candidatos; si no, aviso y lo demás se hace
    _hacer(db, UID, {"op": "ir", "capitulo": "salud", "paso": 1})
    with pytest.raises(ErrorHerramienta) as e:
        _hacer(db, UID, {"op": "visual", "simular": ["calcular"]})
    assert "ahí no hay uno" in str(e.value) and e.value.estado == 404
    r = _hacer(db, UID, {"op": "visual", "camara": "aerea", "simular": ["calcular"]})
    assert "ahí no hay uno" in r.contenido["avisos"][0]
    assert pantalla.estado(db.pantallas.find_one({"_id": UID}), G)["simular"] is None
    # el modelo abierto por un paso de inmersión de la pantalla: su error trae los controles
    _hacer(db, UID, {"op": "ir", "capitulo": "salud", "paso": "torre_sismo"})
    with pytest.raises(ErrorHerramienta) as e:
        _hacer(db, UID, {"op": "visual", "simular": [{"control": "explotar"}]})
    assert "controles" in e.value.detalle and "no tiene el control «explotar»" in str(e.value)
    # otras ops no la usan
    with pytest.raises(Exception):
        hi.PresentacionEntrada.model_validate({"op": "ir", "capitulo": "salud", "simular": ["calcular"]})
    # sin un modelo del atlas, en la maqueta 3D: la hora y las luces (por nombre, «de noche», «sí»)
    _hacer(db, UID, {"op": "ir", "capitulo": "vivienda", "paso": 3})
    r = _hacer(db, UID, {"op": "visual", "simular": [{"control": "Hora del día", "valor": "de noche"},
                                                      {"control": "luces", "valor": "sí"}]})
    assert r.resumen == "La presentación muestra en «La maqueta 3D»: Hora del día: Noche; Luces de la maqueta: sí"
    assert r.contenido["simulacion"] == hi.SIMULACION_MAQUETA and "avisos" not in r.contenido
    assert pantalla.estado(db.pantallas.find_one({"_id": UID}), G)["simular"] == [{"control": "hora", "valor": "noche"},
                                                                                {"control": "luces", "valor": True}]
    # cerrar el modelo del atlas en la misma orden también deja la maqueta
    _hacer(db, UID, {"op": "ir", "capitulo": "salud", "paso": "torre_sismo"})
    r = _hacer(db, UID, {"op": "visual", "inmersion": "maqueta", "simular": [{"control": "reproducir_dia", "valor": True}]})
    assert r.contenido["simulacion"] == hi.SIMULACION_MAQUETA and r.resumen.endswith("en «La maqueta 3D»: Reproducir el día: sí")


def test_visual_del_asistente_va_al_navegador_con_simular():
    db = _Base()   # sin pantalla en off: la acción va a la pestaña del asistente
    _hacer(db, UID, {"op": "ir", "capitulo": "salud", "paso": "torre_sismo"}, por="asistente")
    r = _hacer(db, UID, {"op": "visual", "simular": [{"control": "temblar", "valor": True}]}, por="asistente")
    assert r.acciones == [{"tipo": "presentacion", "op": "visual", "simular": [{"control": "reproducir", "valor": True}]}]
    # de otro capítulo que el de la pantalla, sin la inmersión en la orden: no sabe qué modelo hay
    r = _hacer(db, UID, {"op": "visual", "capitulo": "vivienda", "camara": "aerea", "simular": ["calcular"]}, por="asistente")
    assert "simular" not in r.acciones[-1] and "ahí no hay uno" in r.contenido["avisos"][0]


def test_visual_con_el_paso_de_la_pestana():
    """Lo que la persona toca a mano en la vista del panel no mueve la pantalla guardada: si pasó al paso del simulador,
    visual lo recibe en `paso` (el del contexto del panel) y acciona ahí, como ya hacía con el capítulo."""
    db = _Base()   # sin pantalla en off: la acción va a la pestaña del asistente
    _hacer(db, UID, {"op": "ir", "capitulo": "salud", "paso": 1}, por="asistente")
    pedido = [{"control": "magnitud", "valor": 7}, {"control": "calcular"}]
    # sin el paso se toma el guardado (el 1, sin modelo del atlas): no hay dónde accionar
    with pytest.raises(ErrorHerramienta) as e:
        _hacer(db, UID, {"op": "visual", "capitulo": "salud", "simular": pedido}, por="asistente")
    assert "ahí no hay uno (ábralo con inmersion, o diga capitulo y paso: los del contexto del panel)" in str(e.value)
    for paso in (6, "torre_sismo"):
        r = _hacer(db, UID, {"op": "visual", "capitulo": "salud", "paso": paso, "simular": pedido}, por="asistente")
        assert r.acciones == [{"tipo": "presentacion", "op": "visual", "simular": [{"control": "magnitud", "valor": 7},
                                                                                     {"control": "calcular"}]}], paso
        assert r.resumen.endswith("Magnitud de momento (Mw) 7; Calcular el sismo") and "avisos" not in r.contenido
    # sin el capítulo, el paso es del capítulo guardado; uno que no existe es un error con los pasos
    assert _hacer(db, UID, {"op": "visual", "paso": 6, "simular": ["calcular"]}, por="asistente").acciones
    with pytest.raises(ErrorHerramienta):
        _hacer(db, UID, {"op": "visual", "capitulo": "salud", "paso": 40, "simular": ["calcular"]}, por="asistente")
    # sin los dos, la nota pide capitulo y paso
    r = _hacer(db, UID, {"op": "visual", "camara": "aerea"}, por="asistente")
    assert "indique capitulo y paso" in r.contenido["nota"]
    assert "indique" not in _hacer(db, UID, {"op": "visual", "capitulo": "salud", "paso": 1, "camara": "aerea"},
                                   por="asistente").contenido["nota"]
    # con una pantalla en off, el paso tiene que ser el suyo (como el capítulo)
    db = _abierta()
    _hacer(db, UID, {"op": "ir", "capitulo": "salud", "paso": 1})
    with pytest.raises(ErrorHerramienta) as e:
        _hacer(db, UID, {"op": "visual", "capitulo": "salud", "paso": 6, "simular": ["calcular"]})
    assert e.value.estado == 409 and e.value.detalle["en_pantalla"] == {"capitulo": "salud", "paso": 1}
    _hacer(db, UID, {"op": "ir", "capitulo": "salud", "paso": "torre_sismo"})
    r = _hacer(db, UID, {"op": "visual", "capitulo": "salud", "paso": 6, "simular": ["calcular"]})
    assert pantalla.leer(db, UID)["simular"] == [{"control": "calcular"}] and r.acciones == []
    # otras ops siguen sin usarlo
    with pytest.raises(Exception):
        hi.PresentacionEntrada.model_validate({"op": "vista", "paso": 2, "panel": True})


def test_simular_vacio_dice_que_falta():
    db = _abierta()
    _hacer(db, UID, {"op": "ir", "capitulo": "salud", "paso": "torre_sismo"})
    v = pantalla.leer(db, UID)["v"]
    with pytest.raises(ErrorHerramienta) as e:
        _hacer(db, UID, {"op": "visual", "simular": []})
    assert str(e.value).startswith("No quedó nada que mostrar: simular vino vacío: diga qué controles accionar")
    assert e.value.codigo == "no_existe" and any(c["id"] == "calcular" for c in e.value.detalle["controles"])
    assert pantalla.leer(db, UID)["v"] == v
    # con otra cosa que sí se hace, es un aviso
    r = _hacer(db, UID, {"op": "visual", "camara": "aerea", "simular": []})
    assert r.contenido["avisos"][0].startswith("simular vino vacío")


# ───────────────────────────── La pantalla en off: lo que todavía no recibió no se pisa ─────────────────────────────

def _sondeo(db, v=None):
    """La pantalla en off pregunta (GET /api/pantalla?v=, `pantalla.entregar`): lo que recibe, o None si nada cambió."""
    d = pantalla.entregar(db, UID, v)
    return None if d is None else pantalla.para_pantalla(pantalla.estado(d, G), d, G)


MW5, MW6, CALCULAR = {"control": "magnitud", "valor": 5}, {"control": "magnitud", "valor": 6}, {"control": "calcular"}


def test_dos_ordenes_antes_de_que_la_pantalla_pregunte_se_hacen_las_dos():
    """La pantalla pregunta cada 1,5 s y guarda solo las acciones de la última orden: una segunda orden que llega antes de
    la pregunta ya no pisa las de la primera (el modelo creería haberlas hecho). Se juntan, en orden, y la versión
    nueva las trae una vez; ya recibidas, cualquier orden las deja en nada."""
    db = _abierta()
    _hacer(db, UID, {"op": "ir", "capitulo": "salud", "paso": "torre_sismo"})
    v0 = _sondeo(db)["v"]
    a = _hacer(db, UID, {"op": "visual", "simular": [MW5]})
    b = _hacer(db, UID, {"op": "visual", "simular": ["calcular"]})
    assert a.resumen.endswith("Magnitud de momento (Mw) 5") and b.resumen.endswith("Calcular el sismo")
    x = _sondeo(db, v0)
    assert x["simular"] == [MW5, CALCULAR] and x["v"] == v0 + 2
    assert _sondeo(db, x["v"]) is None
    # ya recibidas: otra orden las deja en nada (la pantalla no las repite)
    _hacer(db, UID, {"op": "explicar", "explicacion": "La torre resiste."})
    y = _sondeo(db, x["v"])
    assert (y["simular"], y["explicacion"]) == (None, "La torre resiste.")
    # todavía no recibidas: una orden sin acciones las conserva, y las de varias se juntan (la animación, el viaje)
    _hacer(db, UID, {"op": "visual", "simular": [MW6], "mover": {"giro": 30}})
    _hacer(db, UID, {"op": "quitar_explicacion"})
    _hacer(db, UID, {"op": "visual", "camara": "aerea", "animar": True, "simular": ["calcular"]})
    z = _sondeo(db, y["v"])
    assert (z["simular"], z["mover"], z["animar"], z["camara"], z["explicacion"]) == (
        [MW6, CALCULAR], {"giro": 30}, True, "aerea", None)
    # cambiar de paso antes de que las reciba las deja: ya no tienen dónde hacerse
    _hacer(db, UID, {"op": "visual", "simular": [MW5], "animar": True})
    _hacer(db, UID, {"op": "ir", "capitulo": "salud", "paso": 5})
    w = _sondeo(db, z["v"])
    assert (w["paso"], w["simular"], w["animar"]) == (5, None, False)
    # abrir otro modelo deja las del anterior y hace las suyas
    _hacer(db, UID, {"op": "visual", "inmersion": "torre_sismo", "simular": [MW5]})
    _hacer(db, UID, {"op": "visual", "inmersion": "torre_bim", "simular": [{"control": "construir", "valor": True}]})
    assert _sondeo(db, w["v"])["simular"] == [{"control": "construir", "valor": True}]


def test_sin_pantalla_abierta_cada_orden_deja_solo_las_suyas():
    """La pantalla que se abre después no hace las acciones de antes: sin una abierta, como siempre, la última orden
    deja solo las suyas."""
    db = _Base()
    _hacer(db, UID, {"op": "ir", "capitulo": "salud", "paso": "torre_sismo"})
    _hacer(db, UID, {"op": "visual", "simular": [MW5]})
    _hacer(db, UID, {"op": "visual", "simular": ["calcular"]})
    assert pantalla.leer(db, UID)["simular"] == [CALCULAR]
    _hacer(db, UID, {"op": "explicar", "explicacion": "Una frase."})
    assert pantalla.leer(db, UID)["simular"] is None


def test_dos_ordenes_en_paralelo_de_un_agente_se_hacen_las_dos():
    """Un agente por MCP suele mandar dos llamadas a la vez: las dos leen la misma pantalla, pero la escritura solo vale
    sobre lo que se leyó, así que la segunda vuelve a leer y se suma a la primera."""
    db = _abierta()
    _hacer(db, UID, {"op": "ir", "capitulo": "salud", "paso": "torre_sismo"})
    v0 = _sondeo(db)["v"]

    async def a_la_vez():
        return await asyncio.gather(*(hi.presentacion_en_pantalla(db, UID, hi.PresentacionEntrada.model_validate(e), "mcp")
                                      for e in ({"op": "visual", "simular": [MW5]},
                                                {"op": "visual", "simular": ["calcular"]})))
    for _ in range(5):
        asyncio.run(a_la_vez())
        x = _sondeo(db, v0)
        assert sorted(map(json.dumps, x["simular"])) == sorted(map(json.dumps, [MW5, CALCULAR])), x["simular"]
        v0 = x["v"]


def test_la_escritura_solo_vale_sobre_lo_que_se_leyo(monkeypatch):
    db = _abierta()
    _hacer(db, UID, {"op": "ir", "capitulo": "salud", "paso": "torre_sismo"})
    v0 = _sondeo(db)["v"]
    viejo = pantalla.leer(db, UID)
    orden = {**pantalla.ACCIONES_INICIALES, "simular": [CALCULAR]}
    pantalla.guardar(db, UID, {**pantalla.ACCIONES_INICIALES, "simular": [MW5]}, "mcp")   # otra orden, entretanto
    monkeypatch.setattr(pantalla, "leer", lambda *a: copy.deepcopy(viejo))
    assert pantalla.guardar_orden(db, UID, orden, "mcp") is None   # leyó antes que la otra: no la pisa
    monkeypatch.undo()
    assert pantalla.guardar_orden(db, UID, orden, "mcp")["simular"] == [MW5, CALCULAR]
    assert _sondeo(db, v0)["simular"] == [MW5, CALCULAR]
    # (las reglas de juntar: dos viajes de la cámara o más de MAX_SIMULAR controles no caben)
    doc = {"inmersion": None}
    junta = lambda p, c: pantalla.juntar_acciones(doc, p, {**pantalla.ACCIONES_INICIALES, **c})   # noqa: E731
    assert junta({"mover": {"giro": 30}}, {"mover": {"giro": -30}}) is None
    assert junta({"simular": [MW5] * 3}, {"simular": [CALCULAR] * 2}) is None
    assert junta({"simular": [MW5] * 3}, {"simular": [CALCULAR]})["simular"] == [MW5] * 3 + [CALCULAR]
    assert junta({"mover": {"giro": 30}, "animar": True}, {}) == {"mover": {"giro": 30}, "animar": True, "simular": None}
    assert junta({"simular": [MW5]}, {"inmersion": "torre_bim"})["simular"] is None


def test_lo_que_no_cabe_espera_a_que_la_pantalla_lo_reciba(monkeypatch):
    """Dos viajes de la cámara (o más de MAX_SIMULAR controles) no se pueden juntar: la orden espera a que la pantalla
    reciba los de antes, hasta ESPERA_ENTREGA_S; si la pantalla no pregunta, quedan los suyos."""
    monkeypatch.setattr(hi, "ESPERA_ENTREGA_S", 0.6)
    db = _abierta()
    _hacer(db, UID, {"op": "ir", "capitulo": "salud", "paso": "torre"})
    v = _sondeo(db)["v"]
    _hacer(db, UID, {"op": "visual", "mover": {"giro": 30}})
    recibido = []
    pregunta = threading.Timer(0.25, lambda: recibido.append(_sondeo(db, v)))
    pregunta.start()
    t0 = time.monotonic()
    _hacer(db, UID, {"op": "visual", "mover": {"giro": -30}})
    pregunta.join()
    assert 0.2 < time.monotonic() - t0 < 0.6 + 0.4
    assert recibido[0]["mover"] == {"giro": 30}
    assert _sondeo(db, recibido[0]["v"])["mover"] == {"giro": -30}   # después, el segundo: los dos, una vez cada uno
    # sin pregunta: espera y quedan los suyos (la pantalla no está respondiendo)
    v = pantalla.leer(db, UID)["v"]
    _hacer(db, UID, {"op": "visual", "mover": {"giro": 10}})
    t0 = time.monotonic()
    _hacer(db, UID, {"op": "visual", "mover": {"giro": 20}})
    assert time.monotonic() - t0 >= 0.6
    assert _sondeo(db, v)["mover"] == {"giro": 20}


def test_la_pantalla_recibe_cada_accion_una_vez_aunque_una_orden_llegue_mientras_pregunta(monkeypatch):
    """Si entre que la pregunta lee y marca la versión entregada llega una orden que junta sus acciones con las de esa
    versión, la marca no vale y se entrega la versión nueva: la primera acción no llega dos veces."""
    db = _abierta()
    _hacer(db, UID, {"op": "ir", "capitulo": "salud", "paso": "torre_sismo"})
    x = _sondeo(db)
    _hacer(db, UID, {"op": "visual", "simular": [MW5]})
    marcar = pantalla.marcar_vista

    def marcar_y_otra_orden(db_, uid):
        doc = marcar(db_, uid)
        assert pantalla.guardar_orden(db_, uid, {**pantalla.ACCIONES_INICIALES, "simular": [CALCULAR]}, "mcp")
        return doc
    monkeypatch.setattr(pantalla, "marcar_vista", marcar_y_otra_orden)
    y = _sondeo(db, x["v"])
    monkeypatch.undo()
    assert (y["v"], y["simular"]) == (x["v"] + 2, [MW5, CALCULAR])
    assert pantalla.leer(db, UID)["entregada_v"] == y["v"] and _sondeo(db, y["v"]) is None
    # la API responde 204 con la versión que ya tiene, y la deja entregada
    from app import acceso
    from app.api import pantalla as api
    quien = acceso.Quien(uid=UID, usuario="c7", nombre="Coordinadora de prueba", rol="coordinador",
                         permisos=acceso.PERMISOS["coordinador"])
    _hacer(db, UID, {"op": "visual", "simular": [MW6]})
    # un latido (la pantalla mientras carga) solo la marca abierta: no le entrega nada ni deja la orden como entregada
    antes = pantalla.leer(db, UID)
    assert api.estado_pantalla(v=-1, latido=True, db=db, quien=quien).status_code == 204
    assert pantalla.leer(db, UID).get("entregada_v") == antes.get("entregada_v") < antes["v"]
    assert api.estado_pantalla(v=y["v"], latido=False, db=db, quien=quien)["simular"] == [MW6]
    assert api.estado_pantalla(v=y["v"] + 1, latido=False, db=db, quien=quien).status_code == 204


def test_la_tarjeta_dice_que_el_paso_maneja_la_simulacion():
    """`simular` en los `hace` de un paso que acciona una simulación (el chip de la tarjeta del chat)."""
    db = _Base()
    r = _hacer(db, UID, _plan(SISMO, {"simular": [{"control": "magnitud", "valor": 7}, "calcular"],
                                      "dice": "Subimos la magnitud a siete y calculamos."},
                              {"camara": "aerea", "dice": "Desde arriba se ve la torre entera."},
                              {"inmersion": "torre_hoy", "simular": ["calcular"], "dice": "El predio hoy."}), por="asistente")
    hace = [e["hace"] for a in r.acciones if a["tipo"] == "recorrido" for e in a["escenas"]]
    assert hace[0] == ["paso", "modelo"] and hace[1] == ["simular"] and "simular" not in hace[2]
    assert "simular" not in hace[3]   # (en el predio hoy no hay controles: no acciona nada)
    assert hi.HACE["simular"] == "maneja la simulación"


def test_la_pantalla_corrige_una_simulacion_guardada_que_no_vale():
    base = {"capitulo": "salud", "paso": 6}
    assert G.capitulos[G.por_id("salud")]["pasos"][5]["id"] == "torre_sismo"
    assert pantalla.estado({**base, "simular": [{"control": "calcular"}]}, G)["simular"] == [{"control": "calcular"}]
    for malo in ([{"control": "explotar"}], [{"control": "magnitud", "valor": 99}], "calcular", [], [{"control": "c"}] * 5):
        assert pantalla.estado({**base, "simular": malo}, G)["simular"] is None, malo
    assert pantalla.estado({"capitulo": "salud", "paso": 1, "simular": [{"control": "calcular"}]}, G)["simular"] is None
    assert pantalla.estado({"capitulo": "salud", "paso": 1, "inmersion": "torre_sismo", "simular": [{"control": "calcular"}]},
                           G)["simular"] == [{"control": "calcular"}]
    # sin un modelo del atlas, contra la maqueta del capítulo: el partido vale en la cancha, no en salud
    partido = [{"control": "partido", "valor": True}]
    assert pantalla.estado({"capitulo": "urbanismo", "paso": 3, "simular": partido}, G)["simular"] == partido
    assert pantalla.estado({"capitulo": "salud", "paso": 1, "simular": partido}, G)["simular"] is None
    hora = [{"control": "hora", "valor": "noche"}]
    assert pantalla.estado({"capitulo": "salud", "paso": 1, "simular": hora}, G)["simular"] == hora
    assert pantalla.estado({**base, "simular": hora}, G)["simular"] is None   # (en el simulador sísmico, no)


def test_los_topes_son_los_mismos_en_el_servidor_y_en_el_navegador():
    def const(ruta: Path, nombre: str) -> str:
        m = re.search(rf"^(?:export )?const {nombre} = (\d+);", ruta.read_text(encoding="utf-8"), re.M)
        return m.group(1) if m else ""
    assert const(MANDO_JS, "MAX_SIMULAR") == const(PUENTE_JS, "MAX_SIMULAR") == str(rec.MAX_SIMULAR)
    assert rec.TIPOS_CONTROL == guion_presentacion.TIPOS_CONTROL
    escenario = (ADMIN.parent / "web" / "js" / "escenario.js").read_text(encoding="utf-8")
    assert all(f"c.tipo === '{t}'" in escenario for t in rec.TIPOS_CONTROL)
    # la maqueta: la misma palabra en el servidor y en el navegador, y la misma regla del valor (validar de escenario.js)
    assert rec.MAQUETA == guion_presentacion.MAQUETA == "maqueta"
    visual = (ADMIN.parent / "web" / "js" / "propuesta" / "visual.js").read_text(encoding="utf-8")
    assert "vis.inmersion === 'maqueta'" in visual and "import { crearSimulacion } from './simulacion.js';" in visual
    assert "export function validar(c, valor)" in escenario


# ───────────────────────────── El navegador (Node) ─────────────────────────────

NODE_PUENTE_SIMULAR = r"""// El puente con `simular`. Uso: node <guion> <agente-presentacion.js>
const [modulo] = process.argv.slice(2);
globalThis.document = { querySelector: () => null };
globalThis.location = { pathname: '/panel/presentacion', origin: 'https://panel.example' };
globalThis.addEventListener = () => {};
globalThis.BroadcastChannel = class { postMessage() {} close() {} };
const P = await import(modulo);
const r = {};
const S = [{ control: 'magnitud', valor: 6.5 }, { control: 'calcular' }];
const V = (extra) => P.accionPresentacion({ tipo: 'presentacion', op: 'visual', ...extra });
r.visual = V({ simular: S });
r.visual_copia = r.visual && r.visual.simular !== S && r.visual.simular[0] !== S[0];
r.visual_malas = [[], [{ control: 'Magnitud' }], [{ control: 'x', otra: 1 }], [{ control: 'x', valor: [1] }], 'calcular',
  Array(5).fill({ control: 'c' }), [{ control: 'x', valor: 'Nido 2015' }], [{ control: 'x', valor: Infinity }]].map((s) => V({ simular: s }));
r.visual_null = V({ camara: 'aerea', simular: null });
r.visual_solo_null = V({ simular: null });
r.otra_op = P.accionPresentacion({ tipo: 'presentacion', op: 'ir', capitulo: 'salud', simular: S });
const V0 = { enfoque: null, camara: 'paso', rumbo: null, elevacion: null, zoom: null, mirar: null, girar: false, comparar: 'proyecto',
  detalle: null, inmersion: null, mostrar: [], ocultar: [], aislar: null, sin: [] };
const esc = (extra) => ({ capitulo: 'salud', paso: 6, panel: true, visual: { ...V0 }, resaltar: null, mover: null, animar: false,
  frases: ['Así tiembla.'], sostener_ms: 2700, ...extra });
const plan = (escenas) => P.recorridoValido({ id: 'abcdef123456', titulo: 'El sismo', escenas, cierre: null });
r.plan = plan([esc({ simular: S }), esc({ simular: null }), esc({})]);
r.plan_malo = plan([esc({ simular: [{ control: 'Magnitud' }] })]);
// el estado de la pantalla en off: una vez por versión nueva, nunca al abrir
const base = { v: 3, capitulo: 'salud', paso: 6, explicacion: null, panel: true, indice: false, fichas: false, completa: false,
  orden_completa: 0, ...V0, tema: null, mover: null, animar: false };
const e1 = P.estadoDePantalla({ ...base, simular: S });
const e0 = P.estadoDePantalla({ ...base, v: 2, simular: null });
r.estado = e1?.simular;
r.estado_malo = P.estadoDePantalla({ ...base, simular: [{ control: 'x', valor: {} }] });
r.estado_sin = P.estadoDePantalla(base)?.simular;
r.al_abrir = P.ordenesHacia(null, e1).filter((o) => o.simular);
r.version_nueva = P.ordenesHacia(e0, e1);
r.misma_version = P.ordenesHacia(e1, e1);
console.log(JSON.stringify(r));
"""


@requiere_node
def test_el_puente_valida_simular_en_la_accion_el_plan_y_la_pantalla(tmp_path):
    r = _node(tmp_path, NODE_PUENTE_SIMULAR, PUENTE_JS.as_uri())
    s = [{"control": "magnitud", "valor": 6.5}, {"control": "calcular"}]
    assert r["visual"] == {"tipo": "presentacion", "op": "visual", "simular": s} and r["visual_copia"] is True
    assert r["visual_malas"] == [None] * 8
    assert r["visual_null"] == {"tipo": "presentacion", "op": "visual", "camara": "aerea", "simular": None}
    assert r["visual_solo_null"] is None and r["otra_op"] is None
    assert [e.get("simular", "falta") for e in r["plan"]["escenas"]] == [s, None, "falta"]
    assert r["plan_malo"] is None
    assert r["estado"] == s and r["estado_malo"] is None and r["estado_sin"] is None
    assert r["al_abrir"] == []
    assert r["version_nueva"] == [{"orden": "visual", "simular": s}] and r["misma_version"] == []


NODE_MANDO_SIMULAR = NODE_MANDO.split("const r = {};")[0].replace("  if (capa === 'nueva') {", """  if (capa === 'nueva') {
    // como la de visual.js: lo que no se pudo, [{clave, valor, motivo}], a más tardar en `tope`
    visual.simular = async (lista, o) => { log.push(['simular', structuredClone(lista), o ?? null]);
      return lista.filter((x) => x.control === 'explotar').map((x) => ({ clave: `simular.${x.control}`, valor: x.valor,
        motivo: 'el modelo no tiene ese control' })); };""", 1) + r"""
const r = {};
// la orden `visual` con solo la simulación: no toca lo visual, acciona y responde
{
  const a = armar();
  const res = await a.pedir('visual', { id: 1, simular: [{ control: 'magnitud', valor: 6.5 }, { control: 'calcular' }] });
  r.solo = { tipo: res?.tipo, aviso: res?.aviso ?? null, log: a.log.filter((l) => ['aplicar', 'simular', 'mover'].includes(l[0])) };
  a.log.length = 0;
  const p = await a.pedir('visual', { id: 2, camara: 'aerea', simular: [{ control: 'explotar' }, { control: 'Mala!' }, { control: 'calcular' }] });
  r.parcial = { tipo: p?.tipo, aviso: p?.aviso, descartadas: p?.descartadas, log: a.log.filter((l) => ['aplicar', 'simular'].includes(l[0])).map((l) => l[0]),
    simulados: a.log.find((l) => l[0] === 'simular')?.[1] };
  a.log.length = 0;
  const e = await a.pedir('visual', { id: 3, simular: [{ control: 'explotar' }] });
  r.error = { tipo: e?.tipo, error: e?.error };
  const n = await a.pedir('visual', { id: 4, simular: 'calcular' });
  r.sin_forma = { tipo: n?.tipo, error: n?.error };
  const m = await a.pedir('visual', { id: 5, simular: Array(5).fill({ control: 'calcular' }) });
  r.cinco = { tipo: m?.tipo, aviso: m?.aviso, descartadas: m?.descartadas, simulados: a.log.filter((l) => l[0] === 'simular').at(-1)?.[1].length };
}
// la escena: acciona después de lo visual, y lo que el atlas no acepta es `parcial`
{
  const a = armar();
  const E = (extra = {}) => ({ rid: 'abcdef123456', n: 1, de: 2, titulo: 'El sismo', capitulo: 'salud', paso: 1, panel: true, visual: null,
    resaltar: null, mover: null, animar: false, frases: ['Así tiembla.'], voz: false, ms: 3200, ...extra });
  const res = await a.pedir('escena', { id: 1, ...E({ simular: [{ control: 'magnitud', valor: 7 }, { control: 'calcular' }] }) });
  r.escena = { tipo: res?.tipo, aviso: res?.aviso ?? null, orden: a.log.filter((l) => ['aplicar', 'simular'].includes(l[0])).map((l) => l[0]),
    simulados: a.log.find((l) => l[0] === 'simular')?.[1], tope: a.log.find((l) => l[0] === 'simular')?.[2] };
  a.log.length = 0;
  const p = await a.pedir('escena', { id: 2, ...E({ n: 2, simular: [{ control: 'explotar' }] }) });
  r.escena_parcial = { tipo: p?.tipo, aviso: p?.aviso, descartadas: p?.descartadas };
  a.log.length = 0;
  const s = await a.pedir('escena', { id: 3, ...E({ n: 2, simular: null }) });
  r.escena_sin = { tipo: s?.tipo, aviso: s?.aviso ?? null, simulo: a.log.some((l) => l[0] === 'simular') };
}
// una capa de antes (sin `simular`): lo descarta con su porqué
{
  const a = armar({ capa: 'vieja' });
  const res = await a.pedir('visual', { id: 1, camara: 'aerea', simular: [{ control: 'calcular' }] });
  r.capa_vieja = { tipo: res?.tipo, aviso: res?.aviso, descartadas: res?.descartadas };
}
console.log(JSON.stringify(r));
"""


@requiere_node
def test_el_mando_acciona_simular_en_visual_y_en_la_escena(tmp_path):
    r = _node(tmp_path, NODE_MANDO_SIMULAR, MANDO_JS.as_uri())
    s = [{"control": "magnitud", "valor": 6.5}, {"control": "calcular"}]
    assert r["solo"] == {"tipo": "estado", "aviso": None, "log": [["simular", s, {"tope": 2000}]]}, r["solo"]
    p = r["parcial"]
    assert p["tipo"] == "estado" and p["aviso"] == "parcial" and p["log"] == ["aplicar", "simular"], p
    assert p["simulados"] == [{"control": "explotar"}, {"control": "calcular"}]
    assert {d["clave"] for d in p["descartadas"]} == {"simular", "simular.explotar"}, p
    assert r["error"]["tipo"] == "error" and "el modelo no tiene ese control" in r["error"]["error"], r["error"]
    assert r["sin_forma"]["tipo"] == "error" and "simular" in r["sin_forma"]["error"], r["sin_forma"]
    c = r["cinco"]
    assert c["tipo"] == "estado" and c["aviso"] == "parcial" and c["simulados"] == 4 and len(c["descartadas"]) == 1, c
    e = r["escena"]
    assert e["tipo"] == "estado" and e["aviso"] is None and e["orden"] == ["aplicar", "simular"], e
    assert e["simulados"] == [{"control": "magnitud", "valor": 7}, {"control": "calcular"}] and e["tope"] == {"tope": 2000}
    assert r["escena_parcial"]["aviso"] == "parcial" and r["escena_parcial"]["descartadas"][0]["clave"] == "simular.explotar"
    assert r["escena_sin"] == {"tipo": "estado", "aviso": None, "simulo": False}
    v = r["capa_vieja"]
    assert v["tipo"] == "estado" and v["aviso"] == "parcial" and "no acciona simulaciones" in v["descartadas"][0]["motivo"], v


def test_el_reproductor_manda_la_simulacion_de_la_escena():
    # (la prueba con un reloj falso de test_recorrido.py ya compara las claves de la orden `escena`, `simular` incluida)
    js = REPRODUCTOR_JS.read_text(encoding="utf-8")
    assert "simular: esc.simular ?? null" in js
    vista = (ADMIN / "web" / "js" / "vistas" / "presentacion.js").read_text(encoding="utf-8")
    # la vista pasa la acción `visual` del puente tal cual a mando.js (simular incluido)
    assert "if (k !== 'tipo' && k !== 'op') o[k] = v;" in vista
