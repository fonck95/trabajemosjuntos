"""El plan guiado de la presentación técnica (docs/agente.md, «El plan guiado»; por dentro, el recorrido narrado): el
asistente arma en una llamada un plan de pasos (lo que se dice + lo que ocurre en pantalla mientras se dice) y la página
que mira la sala lo ejecuta con su propio reloj, con la voz del navegador.

* El servidor: app/recorrido.py (las frases, los tiempos, la validación de la forma absoluta), la op `recorrido` de la
  herramienta `presentacion` (con la base en memoria de test_pantalla_mcp) y su composición TOLERANTE (lo opcional que
  no resuelve se descarta o se recorta con un aviso y el plan corre; lo que se proyecta no se relaja), el movimiento de
  cámara por omisión, los nombres de antes (`escenas`, `narracion`), el avance (uno final lo cierra), los controles,
  el colapso cuando el asistente pide otra cosa (solo si lo pedido vale, y avisando a la pestaña donde suena), la
  escena en curso como lo que se ve, cuándo el contexto deja de nombrarlo y la guarda con personas.
* El navegador, con Node: el reproductor (admin/web/js/reproductor.js) con un reloj falso, la voz (voz.js) con una
  síntesis falsa, los validadores del puente y la tarjeta del chat, con lo que de verdad arma el servidor.
* Que los topes, las listas y los tiempos sean los mismos en los cuatro lados, y las reglas de lo que se pinta.
"""
import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import ayudas_agente as aa
from fastapi import HTTPException

from app import pantalla, recorrido as rec
from app.agente import conversaciones as conv_db, guion as guion_presentacion, sistema
from app.agente.herramientas import interfaz as hi
from app.agente.herramientas.base import ErrorHerramienta
from app.api import pantalla as api_pantalla
from app.proyectable import texto_proyectable
from test_agente_presentacion import COSTOS, MONTOS, SEPARADORES, P, requiere_node
from test_pantalla_mcp import _Base, _hacer

ADMIN = Path(__file__).resolve().parents[1]
RAIZ = ADMIN.parent
JS = ADMIN / "web" / "js"
REPRODUCTOR_JS = JS / "reproductor.js"
VOZ_JS = JS / "voz.js"
PUENTE_JS = JS / "agente-presentacion.js"
TARJETA_JS = JS / "agente-recorrido.js"
MANDO_JS = RAIZ / "web" / "js" / "propuesta" / "mando.js"
G = guion_presentacion.cargar()

ENTRADA = {"op": "recorrido", "titulo": "La torre del hospital", "pasos": [
    {"capitulo": "salud", "paso": "torre", "camara": "oblicua",
     "dice": "Estamos junto al hospital Héctor Abad Gómez. Aquí se levanta la nueva torre de servicios."},
    {"inmersion": "torre_hoy", "dice": "Así está hoy el predio: las alas del antiguo Centro Vida, que se demuelen."},
    {"inmersion": "paso", "girar": True, "resaltar": {"leyenda": 1},
     "dice": "Con el proyecto, la torre de cuatro pisos queda a 5,3 m del hospital actual."},
    {"detalle": "torre", "girar": False, "resaltar": {"especificacion": "Estructura"},
     "dice": "Su estructura es dual en concreto, sobre 146 pilotes de 15 m."},
    {"paso": "torre_pisos", "resaltar": {"punto": 1}, "dice": "Por dentro, cada piso agrupa sus servicios."}],
    "cierre": {"puntos": ["Sigue atendiendo tras un sismo", "Cuatro pisos, 15 camas"]},
    "sugerencias": ["Ver el simulador sísmico"]}
# Un plan de ocho pasos que usa lo que da el plan guiado: la cámara que viaja (`mover`), su elevación y su acercamiento,
# a qué apunta (`mirar`), una pieza aislada, una parte quitada, piezas que se ocultan y la animación del paso
PLAN = {"op": "recorrido", "titulo": "La torre, pieza por pieza", "pasos": [
    {"capitulo": "salud", "paso": "torre", "camara": "oblicua", "mover": {"giro": 40},
     "dice": "Estamos junto al hospital Héctor Abad Gómez, donde se levanta la nueva torre."},
    {"comparar": "hoy", "dice": "Así está hoy el predio: las alas del antiguo Centro Vida."},
    {"comparar": "proyecto", "aislar": "torre", "animar": True, "dice": "Con el proyecto, la torre crece piso a piso."},
    {"sin": ["torre.cubierta"], "elevacion": 60, "zoom": 1.5, "dice": "Sin la cubierta se ven las losas de cada piso."},
    {"aislar": "nada", "sin": [], "mirar": "hospital_hoy", "ocultar": ["telesalud", "puestos"],
     "dice": "Al lado sigue funcionando el hospital de hoy."},
    {"dice": "La torre agrupa urgencias, cirugía y hospitalización."},
    {"detalle": "torre", "resaltar": {"especificacion": "Estructura"},
     "dice": "Su estructura es dual en concreto, sobre 146 pilotes de 15 m."},
    {"paso": "torre_pisos", "mover": {"giro": -60, "zoom": 1.4, "elevacion": 40}, "resaltar": {"punto": 1},
     "dice": "Por dentro, cada piso agrupa sus servicios."}],
    "cierre": {"puntos": ["Sigue atendiendo tras un sismo", "Cuatro pisos, 15 camas"]}}


def _armar(db=None, uid=7, entrada=ENTRADA, por="asistente"):
    db = db if db is not None else _Base()   # una base de pymongo no se puede usar como booleano
    return db, _hacer(db, uid, entrada, por=por)


# ───────────────────────────── El servidor ─────────────────────────────

def test_las_frases_no_se_cortan_en_una_sigla_y_son_tres_a_lo_sumo():
    assert rec.partir_frases("La E.S.E. Hospital atiende. Y crece.") == ["La E.S.E. Hospital atiende.", "Y crece."]
    assert rec.partir_frases("Según la Res. 1633 de 2025, sí. Otra.") == ["Según la Res. 1633 de 2025, sí.", "Otra."]
    assert rec.partir_frases("Una. Dos. Tres. Cuatro.") == ["Una.", "Dos.", "Tres. Cuatro."]
    assert rec.partir_frases("  Sin  punto final  ") == ["Sin punto final"]
    assert rec.lectura_ms("x") == 3200 and rec.lectura_ms("x" * 400) == 16000
    assert rec.lectura_ms("x" * 100) == 1500 + 62 * 100


def test_lo_proyectado_no_trae_costos_ni_datos_de_personas():
    """Costos como se escriben en Colombia (en mayúsculas o minúsculas, con «$» o sin él) y cédulas o teléfonos con
    separadores que no son los de siempre (el apóstrofo de los millones, los puntos de viñeta): las listas de
    test_agente_presentacion, que también compara los tres lados."""
    assert texto_proyectable("Cuatro pisos y 15 camas") == "Cuatro pisos y 15 camas"
    for malo in (*COSTOS, *MONTOS, *SEPARADORES, "Unos 30 millones de pesos", "Llame al 300 123 4567", "ana@correo.co",
                 "x" * 221):
        with pytest.raises(ValueError):
            texto_proyectable(malo)
    # Un monto se frena por lo que es (el mensaje lo dice), no como un número largo
    with pytest.raises(ValueError, match="no muestra costos"):
        texto_proyectable("Por habitante, $1.156.350")
    # «cop» y «pesos» como palabras sueltas, no dentro de otras; los dos puntos no unen dígitos (una escala)
    for bueno in ("La copa del árbol", "Los pesados", "Escopeta", "A escala 1:100.000", "Del 2028'31"):
        assert texto_proyectable(bueno) == bueno, bueno
    # La explicación suelta (op explicar, también en ir) sigue la misma regla: la presentación es siempre la técnica
    for entrada in ({"op": "explicar", "explicacion": "Cuesta $5.000"},
                    {"op": "ir", "capitulo": "salud", "explicacion": "Son 1,2 billones de pesos"}):
        with pytest.raises(Exception, match="costos"):
            hi.PresentacionEntrada.model_validate(entrada)


def test_el_recorrido_se_arma_absoluto_y_llega_a_la_pestana_y_a_la_tarjeta():
    db, r = _armar()
    assert [a["tipo"] + ":" + a.get("op", "") for a in r.acciones] == ["presentacion:recorrido", "recorrido:"]
    absoluto = r.acciones[0]["recorrido"]
    assert rec.validar(absoluto, G) == []
    assert set(absoluto) == {"id", "titulo", "escenas", "cierre"} and re.fullmatch(r"[0-9a-f]{12}", absoluto["id"])
    e1, e2, e3, e4, e5 = absoluto["escenas"]
    assert (e1["capitulo"], e1["paso"], e1["visual"]["camara"]) == ("salud", 3, "oblicua")
    assert e1["frases"] == ["Estamos junto al hospital Héctor Abad Gómez.", "Aquí se levanta la nueva torre de servicios."]
    # cada escena hereda lo de la anterior (el pliegue) y queda entera: la cámara sigue oblicua, el atlas se abre
    assert e2["visual"]["camara"] == "oblicua" and e2["visual"]["inmersion"] == "torre_hoy"
    assert e3["visual"]["girar"] is True and e3["resaltar"] == {"tipo": "leyenda", "n": 1}
    assert e4["visual"]["detalle"] == "torre" and e4["resaltar"]["tipo"] == "especificacion" and e4["resaltar"]["en"] == "ficha"
    assert e5["paso"] == 4 and e5["resaltar"] == {"tipo": "punto", "n": 1}
    assert all(set(e["visual"]) == set(rec.VISUAL) for e in absoluto["escenas"])
    # la forma absoluta de la escena, siempre con todas sus claves y en este orden (`mover`, `animar` y `simular` no son
    # estado)
    assert all(list(e) == ["capitulo", "paso", "panel", "visual", "resaltar", "mover", "animar", "simular", "frases",
                           "sostener_ms"] for e in absoluto["escenas"])
    assert all(list(e["visual"]) == list(rec.VISUAL) for e in absoluto["escenas"])
    assert [e["animar"] for e in absoluto["escenas"]] == [False] * 5 and e1["mover"] is None
    assert e1["sostener_ms"] == rec.SOSTENER_MS == 1300 and e2["sostener_ms"] == rec.SOSTENER_MIRAR_MS
    assert absoluto["cierre"] == {"puntos": ["Sigue atendiendo tras un sismo", "Cuatro pisos, 15 camas"]}
    # La tarjeta del chat: dónde, qué hace y la narración de cada escena; las sugerencias y la duración
    t = r.acciones[1]
    assert t["id"] == absoluto["id"] and t["destino"] == "vista" and t["sugerencias"] == ["Ver el simulador sísmico"]
    assert t["cierre"] == absoluto["cierre"]["puntos"] and t["duracion_ms"] == rec.duracion_ms(absoluto, G)
    assert t["escenas"][0]["hace"] == ["paso", "camara"] and "modelo" in t["escenas"][1]["hace"]
    assert all(set(x["hace"]) <= set(hi.HACE) for x in t["escenas"])
    # Al modelo, lo compacto y con sus palabras (un plan y sus pasos): qué se ve en cada paso, sin repetir lo que dijo
    assert r.contenido["plan"]["pasos"] == 5 and r.contenido["pasos"][0]["muestra"].startswith("Salud · paso 3")
    assert r.contenido["pasos"][1]["muestra"].startswith("el mismo paso · ") and "avisos" not in r.contenido
    assert set(r.contenido) == {"plan", "pasos", "nota"} and all(set(x) == {"n", "muestra"} for x in r.contenido["pasos"])
    assert "no la repita" in r.contenido["nota"] and "pregunta corta" in r.contenido["nota"]
    assert r.resumen.startswith("Plan «La torre del hospital» · 5 pasos · ≈")
    assert len(json.dumps(r.contenido, ensure_ascii=False)) < 2500
    # Queda guardado, con la última escena como base (lo que queda a la vista al terminar)
    d = db.pantallas.find_one({"_id": 7})
    assert d["recorrido"]["destino"] == "vista" and d["recorrido"]["cerrado"] is False
    assert (d["capitulo"], d["paso"]) == ("salud", 4)


def test_el_plan_usa_la_camara_las_piezas_y_las_partes():
    """Ocho pasos con lo que da el plan guiado: nada se descarta, cada cosa queda en su escena y lo que no se nombra
    sigue del paso anterior."""
    db, r = _armar(entrada=PLAN)
    assert "avisos" not in r.contenido, r.contenido.get("avisos")
    absoluto = r.acciones[0]["recorrido"]
    assert rec.validar(absoluto, G) == [] and len(absoluto["escenas"]) == 8
    e = absoluto["escenas"]
    v = [x["visual"] for x in e]
    assert e[0]["mover"] == {"giro": 40} and v[0]["camara"] == "oblicua"
    assert (v[2]["aislar"], e[2]["animar"], v[2]["comparar"]) == ("torre", True, "proyecto")
    assert (v[3]["aislar"], v[3]["sin"], v[3]["elevacion"], v[3]["zoom"]) == ("torre", ["torre.cubierta"], 60, 1.5)
    # «nada» quita el aislamiento, [] devuelve las partes; la elevación y el acercamiento siguen del paso anterior
    assert (v[4]["aislar"], v[4]["sin"], v[4]["mirar"], v[4]["ocultar"]) == (None, [], "hospital_hoy", ["telesalud", "puestos"])
    assert (v[4]["elevacion"], v[4]["zoom"], v[4]["camara"]) == (60, 1.5, "oblicua")
    assert v[6]["detalle"] == "torre" and e[6]["resaltar"] == {"tipo": "especificacion", "n": 4, "en": "ficha"}
    # al cambiar de paso del capítulo, lo visual vuelve a lo del paso; el viaje de la cámara es de esa escena
    assert v[7] == rec.VISUAL_INICIAL and e[7]["mover"] == {"giro": -60, "zoom": 1.4, "elevacion": 40}
    # las listas de una escena son suyas: ninguna comparte la lista con otra ni con VISUAL_INICIAL
    assert v[5]["ocultar"] == v[4]["ocultar"] and v[5]["ocultar"] is not v[4]["ocultar"]
    assert rec.VISUAL_INICIAL["ocultar"] == [] and rec.VISUAL_INICIAL["sin"] == [] and rec.VISUAL_INICIAL["mostrar"] == []
    # Los chips de la tarjeta: lo que hace cada paso, de la lista fija
    hace = [x["hace"] for x in r.acciones[1]["escenas"]]
    assert hace[0] == ["paso", "camara", "mover"] and hace[1] == ["hoy"]
    assert hace[2] == ["aislar", "proyecto", "animar"] and hace[3] == ["camara", "partes"]
    assert hace[4] == ["mirar", "capas"] and hace[5] == [] and hace[6] == ["ficha", "resaltar"]
    assert hace[7] == ["paso", "mover", "modelo", "resaltar"]
    assert all(set(x) <= set(hi.HACE) for x in hace)
    assert set(hi.HACE) >= {"capas", "aislar", "partes", "mover", "mirar", "animar"}
    # Al modelo: lo que se ve en cada paso, con los ids que usó
    m = [x["muestra"] for x in r.contenido["pasos"]]
    assert "la cámara gira 40°" in m[0] and "solo torre" in m[2] and "anima la obra" in m[2]
    assert "sin torre.cubierta" in m[3] and "a 60° sobre el horizonte" in m[3] and "zoom 1.5" in m[3]
    assert "la cámara apunta a hospital_hoy" in m[4] and "oculta telesalud, puestos" in m[4]
    assert "la cámara se mueve un poco sola" in m[5]
    # La base guardada (lo que queda al terminar) es la última escena, sin su movimiento: `mover` y `animar` no son estado
    d = db.pantallas.find_one({"_id": 7})
    assert (d["paso"], d["mover"], d["animar"], d["aislar"], d["sin"]) == (4, None, False, None, [])
    assert pantalla.recorrido_de(d, G)["escenas"] == e
    # Y al colapsar a mitad (otra orden), queda lo de la escena en curso, sin su `mover` ni su `animar`
    rid = absoluto["id"]
    assert _avance(db, 7, rid, 4, "narrando", de=8)
    est = _hacer(db, 7, {"op": "estado"}, por="asistente").contenido["pantalla"]
    assert (est["visual"]["aislar"], est["visual"]["sin"], est["visual"]["elevacion"]) == ("torre", ["torre.cubierta"], 60)
    assert "solo se ve «Torre nueva de cuatro pisos» (torre)" in est["muestra"] and "sin Cubierta y parasoles" in est["muestra"]
    _hacer(db, 7, {"op": "explicar", "explicacion": "Una frase."}, por="asistente")
    d = db.pantallas.find_one({"_id": 7})
    assert d["recorrido"]["cerrado"] is True and (d["aislar"], d["sin"], d["zoom"], d["mover"], d["animar"]) == (
        "torre", ["torre.cubierta"], 1.5, None, False)
    assert rec.estado_de_escena(e[2])["animar"] is False and rec.estado_de_escena(e[0])["mover"] is None


def test_lo_opcional_que_no_resuelve_se_descarta_con_un_aviso_y_el_plan_sigue():
    """Una pieza mal escrita, una parte que no existe, un componente sin lugar, un modelo que no está, un resaltado
    imposible, un paso o un capítulo que no existen después del primero, valores fuera de rango o sin la forma y claves
    que no son de un paso: nada de eso tumba el plan. Cada cosa deja un aviso con el número del paso y los candidatos."""
    db, r = _armar(entrada={"op": "recorrido", "titulo": "Un plan con errores", "pasos": [
        {"capitulo": "salud", "paso": "torre", "camara": "dron", "rumbo": 400, "dice": "Uno."},
        {"aislar": "tore", "mostrar": ["torre", "la luna"], "dice": "Dos."},
        {"aislar": "torre", "sin": ["torre.techo", "cubierta"], "elevacion": 95, "zoom": 9, "dice": "Tres."},
        {"enfoque": "hospital_hoy", "detalle": "quirofano", "inmersion": "otra_cosa", "dice": "Cuatro."}]})
    absoluto = r.acciones[0]["recorrido"]
    assert rec.validar(absoluto, G) == [] and len(absoluto["escenas"]) == 4
    v = [x["visual"] for x in absoluto["escenas"]]
    avisos = r.contenido["avisos"]
    de = lambda n: [a for a in avisos if a.startswith(f"Paso {n}: ")]   # noqa: E731
    # 1. Una cámara que no es de la lista se ignora; el rumbo da la vuelta
    assert (v[0]["camara"], v[0]["rumbo"]) == ("paso", 40) and len(de(1)) == 1 and "camara «dron»" in de(1)[0]
    assert "paso, aerea, oblicua, rasante, cerca, lejos" in de(1)[0]
    # 2. La pieza que no existe se descarta con los candidatos; la que sí, se muestra
    assert (v[1]["aislar"], v[1]["mostrar"]) == (None, ["torre"]) and len(de(2)) == 2
    assert "Paso 2: la pieza «tore» no está en Salud (aislar); piezas: hospital_hoy, torre, telesalud, puestos" in avisos
    assert any("«la luna»" in a and "(mostrar)" in a for a in de(2))
    # 3. La parte que no existe se descarta y la que llegó sin su pieza se resuelve con la aislada; lo demás se recorta
    assert (v[2]["aislar"], v[2]["sin"], v[2]["elevacion"], v[2]["zoom"]) == ("torre", ["torre.cubierta"], 85, 3)
    assert any("no tiene la parte «techo»" in a and "torre.cubierta, torre.equipos, torre.jardines" in a for a in de(3))
    assert any("elevacion 95 quedó en 85" in a for a in de(3)) and any("zoom 9 quedó en 3" in a for a in de(3))
    # 4. Una pieza que no es un componente con lugar: la cámara le apunta (mirar), y el aviso de que no se va a ver (la
    # torre sigue aislada). Ni la ficha ni el modelo que no existen
    assert (v[3]["enfoque"], v[3]["mirar"], v[3]["detalle"], v[3]["inmersion"]) == (None, "hospital_hoy", None, None)
    assert any("la cámara apunta a esa pieza (mirar)" in a for a in de(4))
    assert any("pero solo se ve «torre»" in a and "aislar: nada lo quita" in a for a in de(4))
    assert any("no tiene el componente «quirofano»" in a and "componentes: torre" in a for a in de(4))
    assert any("no hay un modelo del atlas «otra_cosa»" in a and "torre_hoy" in a for a in de(4))
    assert "no lo mande otra vez" in r.contenido["nota"]
    assert db.pantallas.find_one({"_id": 7})["recorrido"]["cerrado"] is False   # se guardó y se reproduce
    _, r = _armar(entrada={"op": "recorrido", "titulo": "Otro plan con errores", "pasos": [
        {"capitulo": "salud", "paso": "torre", "dice": "Uno."},
        {"capitulo": "no existe", "paso": 40, "resaltar": {"especificacion": "Cimientos"}, "dice": "Dos."},
        {"mover": {"giro": 900, "zoom": "cerca", "altura": 3}, "girar": "tal vez", "panel": "no", "color": "rojo",
         "sostener": 30, "resaltar": {"cifra": 1, "punto": 2}, "animar": "si", "dice": "Tres."}]})
    absoluto = r.acciones[0]["recorrido"]
    assert rec.validar(absoluto, G) == []
    e, avisos = absoluto["escenas"], r.contenido["avisos"]
    # Después del primero, un capítulo o un paso que no existen dejan el plan donde iba; el resaltado se pierde
    assert (e[1]["capitulo"], e[1]["paso"], e[1]["resaltar"]) == ("salud", 3, None)
    assert any("no tiene un capítulo «no existe»" in a and "Sigue en Salud" in a for a in de(2))
    assert any("no tiene el paso «40»: sigue en el mismo paso; pasos: " in a for a in de(2))
    assert any("no tiene la especificación «Cimientos»" in a and "No se resaltó nada" in a for a in de(2))
    # Un movimiento con partes que no valen: el giro se recorta, lo demás se descarta; las claves que no existen también
    assert e[2]["mover"] == {"giro": 360} and e[2]["animar"] is False and e[2]["panel"] is True and e[2]["resaltar"] is None
    assert e[2]["sostener_ms"] == rec.MAX_SOSTENER_MS and e[2]["visual"]["girar"] is False
    esperados = {"mover.giro 900 quedó en 360", "mover.zoom «cerca» no es un número", "«altura»", "girar «tal vez»",
                 "panel es true o false", "«color»", "sostener «30»", "resaltar lleva exactamente una",
                 "animar es true o false"}
    assert {x for a in de(3) for x in esperados if x in a} == esperados, de(3)
    # El paso del capítulo, escrito a su manera, se resuelve; a lo que la cámara no puede apuntar, con los candidatos
    _, r = _armar(entrada={"op": "recorrido", "titulo": "A su manera", "pasos": [
        {"capitulo": "Salud", "paso": "Torre Pisos", "mirar": "plaza", "dice": "Uno."},
        {"paso": "torre que sigue atendiendo", "aislar": "Torre nueva", "mirar": "el hospital de hoy", "dice": "Dos."}]})
    e, avisos = r.acciones[0]["recorrido"]["escenas"], r.contenido["avisos"]
    assert (e[0]["paso"], e[0]["visual"]["mirar"]) == (4, None) and len(de(1)) == 1
    assert "puede mirar: hospital_hoy, torre" in de(1)[0]
    assert (e[1]["paso"], e[1]["visual"]["aislar"], e[1]["visual"]["mirar"]) == (3, "torre", "hospital_hoy") and not de(2)
    # Los avisos llegan al modelo acotados: los primeros y cuántos más
    muchos = [{"capitulo": "salud", "paso": "torre", "dice": "Uno."},
              *({"aislar": f"pieza {i}", "mirar": "la luna", "dice": "Otro."} for i in range(11))]
    _, r = _armar(entrada={"op": "recorrido", "titulo": "Muchos avisos", "pasos": muchos, "cierre": ["Una idea"]})
    assert len(r.contenido["avisos"]) == hi.MAX_AVISOS + 1 and r.contenido["avisos"][-1].startswith("y ")


def test_la_op_guion_trae_la_maqueta_y_los_ejemplos_son_planes_que_corren():
    """Lo que el modelo lee antes de armar el plan (op `guion`): los pasos, las fichas, las piezas de la maqueta con sus
    partes y los modelos del atlas, con la nota que dice cómo se arma. Y los ejemplos que ve (el de la descripción de
    la herramienta y el de esa nota) son planes que la herramienta acepta tal cual, sin un solo aviso."""
    db = _Base()
    r = _hacer(db, 7, {"op": "guion", "capitulo": "Salud"}, por="asistente")
    assert r.acciones == [] and db.pantallas.find_one({"_id": 7}) is None   # leer no mueve ni guarda nada
    assert list(r.contenido) == ["capitulo", "pasos", "componentes", "maqueta", "inmersiones", "nota"]
    assert [x["id"] for x in r.contenido["maqueta"]] == ["hospital_hoy", "torre", "telesalud", "puestos"]
    assert [p["id"] for p in r.contenido["maqueta"][1]["partes"]] == ["cubierta", "equipos", "jardines"]
    # (con los controles de las simulaciones de sus modelos del atlas: el simulador sísmico, el BIM… por debajo del tope
    # de lo que recibe el modelo, MAX_CONTENIDO)
    assert r.contenido["nota"] == hi.NOTA_GUION and len(r.texto_para_modelo()) < 36000
    assert r.resumen == "Guion de Salud · 10 pasos, 5 componentes"
    nota = hi.NOTA_GUION
    for palabra in ("UN plan", "De 6 a 10 pasos (hasta 12)", "UNA frase hablada (dice)", "MIENTRAS se dice", "mover {giro, zoom, "
                    "elevacion}", "aislar", "sin «pieza.parte»", "se descarta con un aviso", "sin costos"):
        assert palabra in nota, palabra
    # El ejemplo de la nota (una entrada entera) y el de la descripción (sus pasos), con una frase de verdad
    ejemplo = json.loads(nota[nota.index('{"op":"recorrido"'):].replace("…", "Una frase."))
    pasos = hi.D_PRESENTACION[hi.D_PRESENTACION.index("Ejemplo de pasos: ") + len("Ejemplo de pasos: "):]
    pasos = json.loads(pasos[:pasos.index("]. control_recorrido") + 1].replace("…", "Una frase."))
    for entrada in (ejemplo, {"op": "recorrido", "titulo": "La torre", "pasos": pasos}):
        x = _hacer(_Base(), 7, entrada, por="asistente")
        assert "avisos" not in x.contenido, x.contenido.get("avisos")
        e = x.acciones[0]["recorrido"]["escenas"]
        assert (e[0]["capitulo"], e[0]["paso"], e[0]["visual"]["camara"], e[0]["mover"]) == ("salud", 3, "oblicua", {"giro": 40})
        assert (e[1]["visual"]["aislar"], e[1]["visual"]["sin"]) == ("torre", ["torre.cubierta"])
    assert len(hi.D_PRESENTACION) < 1500 and "en el panel de la persona o en su pantalla en off" in hi.D_PRESENTACION
    # Si de una lista nada existe, la lista queda como estaba (un nombre mal escrito no devuelve lo que ya se quitó)
    _, x = _armar(entrada={"op": "recorrido", "titulo": "Listas", "pasos": [
        {"capitulo": "salud", "paso": "torre", "sin": ["torre.cubierta"], "ocultar": ["telesalud"], "dice": "Uno."},
        {"sin": ["torre.techo"], "ocultar": ["marte"], "dice": "Dos."}, {"sin": [], "ocultar": [], "dice": "Tres."}]})
    v = [e["visual"] for e in x.acciones[0]["recorrido"]["escenas"]]
    assert (v[1]["sin"], v[1]["ocultar"]) == (["torre.cubierta"], ["telesalud"]) and (v[2]["sin"], v[2]["ocultar"]) == ([], [])
    assert len(x.contenido["avisos"]) == 2 and all(a.startswith("Paso 2: ") for a in x.contenido["avisos"])


def test_solo_falla_lo_que_no_se_puede_relajar():
    """El primer paso sin un capítulo que resuelva, un texto que no se puede proyectar (con el número del paso), más de
    doce pasos y un plan que pasa de la duración máxima. Nada se guarda."""
    db = _Base()
    uno = {"capitulo": "salud", "dice": "Una."}
    casos = [
        ([{"dice": "Sin capítulo."}], "Paso 1: el primer paso del plan dice su capitulo"),
        ([{"capitulo": "no existe", "dice": "Una."}], "Paso 1: La presentación no tiene un capítulo «no existe»"),
        ([uno, {"dice": "Cuesta $5 M"}], "Paso 2: La presentación técnica no muestra costos"),
        ([uno, uno, {"dice": "Llame al 300 123 4567"}], "Paso 3: La explicación se proyecta ante la sala"),
        ([uno, {"dice": "escriba a ana@correo.co"}], "Paso 2: "),
        ([uno, {"dice": "x" * 221}], "Paso 2: El texto para la pantalla pasa de 220 caracteres"),
        ([uno, {"camara": "aerea"}], "Paso 2: falta dice"),
        ([uno, {"dice": 7}], "Paso 2: dice tiene que ser un texto"),
        ([uno, {"dice": "Son 5 millones de pesos"}, uno, {"dice": "Vale $3"}], "Pasos 2, 4: La presentación técnica no muestra"),
    ]
    for pasos, comienzo in casos:
        with pytest.raises(ErrorHerramienta) as e:
            _hacer(db, 7, {"op": "recorrido", "titulo": "Una prueba", "pasos": pasos}, por="asistente")
        assert str(e.value).startswith(comienzo), str(e.value)
        assert e.value.codigo in ("invalido", "no_existe") and (e.value.detalle.get("paso") or e.value.detalle.get("pasos"))
    assert "No se guardó ni se mostró nada" in str(e.value) and e.value.detalle["pasos"] == [2, 4]
    # Más de doce pasos: la entrada lo dice en español
    with pytest.raises(Exception, match="hasta 12 pasos y llegaron 13"):
        _hacer(db, 7, {"op": "recorrido", "titulo": "Largo", "pasos": [uno] * (rec.MAX_ESCENAS + 1)}, por="asistente")
    # Doce pasos caben; con frases muy largas y la imagen sostenida al máximo, el plan pasa de la duración máxima
    largo = {"capitulo": "salud", "dice": ("Una frase larga que se lee despacio. " * 6)[:215], "sostener": 8}
    with pytest.raises(ErrorHerramienta, match="El plan dura unos"):
        _hacer(db, 7, {"op": "recorrido", "titulo": "Largo", "pasos": [largo] * 12}, por="asistente")
    # El título y el cierre también se proyectan
    for extra in ({"titulo": "Vale $5"}, {"cierre": {"puntos": ["Llame al 300 123 4567"]}}):
        with pytest.raises(Exception):
            _hacer(db, 7, {"op": "recorrido", "titulo": "Una prueba", "pasos": [uno], **extra}, por="asistente")
    assert db.pantallas.find_one({"_id": 7}) is None   # nada se guardó


def test_doce_pasos_y_los_nombres_de_antes():
    doce = [{"capitulo": "salud", "paso": "torre", "dice": "Uno."}, *({"dice": f"Paso {i}."} for i in range(2, 13))]
    db, r = _armar(entrada={"op": "recorrido", "titulo": "Doce pasos", "pasos": doce})
    absoluto = r.acciones[0]["recorrido"]
    assert rec.MAX_ESCENAS == 12 and len(absoluto["escenas"]) == 12 and rec.validar(absoluto, G) == []
    assert rec.bytes_de(absoluto) < rec.MAX_RECORRIDO_BYTES and rec.duracion_ms(absoluto, G) < rec.MAX_DURACION_MS
    assert _avance(db, 7, absoluto["id"], 12, "narrando", de=12)
    assert api_pantalla.ProgresoEntrada(rid=absoluto["id"], n=12, de=12, fase="narrando", voz="apagada", aviso="parcial")
    # Doce escenas llenas (lo visual con sus listas completas y dos frases largas) caben en el tope de bytes
    llena = {**absoluto["escenas"][0], "frases": ["x" * 109, "y" * 110], "mover": {"giro": -360, "zoom": 2.55, "elevacion": 85},
             "resaltar": {"tipo": "especificacion", "n": 4, "en": "ficha"},
             "visual": {**absoluto["escenas"][0]["visual"], "mostrar": ["hospital_hoy", "telesalud", "puestos", "torre"],
                        "ocultar": ["hospital_hoy", "telesalud", "puestos", "torre"], "aislar": "torre", "mirar": "torre",
                        "enfoque": "torre", "detalle": "torre", "inmersion": "torre_hoy", "rumbo": 359, "elevacion": 85,
                        "zoom": 2.55, "sin": ["torre.cubierta", "torre.equipos", "torre.jardines"]}}
    assert rec.validar({**absoluto, "escenas": [llena] * 12}, G) == []
    # `escenas` y `narracion` (los nombres de antes) arman lo mismo; los dos a la vez, no
    viejo = {"op": "recorrido", "titulo": ENTRADA["titulo"], "cierre": ENTRADA["cierre"], "escenas": [
        {**{k: v for k, v in x.items() if k != "dice"}, "narracion": x["dice"]} for x in ENTRADA["pasos"]]}
    _, a = _armar()
    _, b = _armar(entrada=viejo)
    assert a.acciones[0]["recorrido"]["escenas"] == b.acciones[0]["recorrido"]["escenas"] and "avisos" not in b.contenido
    with pytest.raises(Exception, match="pasos y escenas son lo mismo"):
        _hacer(_Base(), 7, {**viejo, "pasos": ENTRADA["pasos"]}, por="asistente")
    with pytest.raises(Exception, match="escriba el titulo y los pasos"):
        _hacer(_Base(), 7, {"op": "recorrido", "titulo": "Sin pasos"}, por="asistente")
    # El modelo solo ve los nombres nuevos (repetir el esquema del paso lo doblaría), con `dice` obligatorio
    s = hi._esquema_presentacion()
    paso = s["properties"]["pasos"]["items"]
    assert "escenas" not in s["properties"] and "narracion" not in paso["properties"] and paso["required"] == ["dice"]
    assert s["properties"]["pasos"]["maxItems"] == 12 and paso["additionalProperties"] is False
    assert {"elevacion", "zoom", "mirar", "mostrar", "ocultar", "aislar", "sin", "mover", "animar"} <= set(paso["properties"])
    assert paso["properties"]["elevacion"] == {**paso["properties"]["elevacion"], "minimum": 8, "maximum": 85}
    assert set(paso["properties"]["mover"]["properties"]) == {"giro", "zoom", "elevacion"}
    # Lo que el modelo escribe a su manera y se entiende sin aviso: una frase como `texto`, una pieza suelta, el cierre
    # como lista, el título que falta (queda el nombre del capítulo)
    _, c = _armar(entrada={"op": "recorrido", "pasos": [{"capitulo": "salud", "paso": 3, "narracion": "Una.",
                                                         "ocultar": "telesalud, puestos", "zoom": "1,5"}],
                           "cierre": ["Una idea", "Otra idea"]})
    x = c.acciones[0]["recorrido"]
    assert x["titulo"] == "Salud" and x["cierre"] == {"puntos": ["Una idea", "Otra idea"]} and "avisos" not in c.contenido
    assert (x["escenas"][0]["visual"]["ocultar"], x["escenas"][0]["visual"]["zoom"]) == (["telesalud", "puestos"], 1.5)
    _, c = _armar(entrada={"op": "recorrido", "titulo": "Otro", "pasos": [{"capitulo": "salud", "texto": "Una."}]})
    assert c.acciones[0]["recorrido"]["escenas"][0]["frases"] == ["Una."] and "«texto» se tomó como dice" in c.contenido["avisos"][0]


def test_un_paso_que_no_le_pide_nada_a_la_camara_recibe_un_movimiento_suave():
    """Que la imagen nunca quede quieta mientras se habla: sin cambio de encuadre y sin `mover`, la cámara gira unos
    grados (de 10 a 14, alternando el sentido) y, la primera vez sobre un encuadre, se acerca un poco; después sigue
    desde donde quedó y solo gira (con otro acercamiento reabriría el encuadre o se acumularía). También el primer
    paso, si no trae nada para la cámara. No dentro de un modelo del atlas, ni con la cámara girando sola, ni cuando
    el paso ya le pide algo a la cámara."""
    _, r = _armar(entrada={"op": "recorrido", "titulo": "La cámara", "pasos": [
        {"capitulo": "salud", "paso": "torre", "dice": "Uno."},
        {"dice": "Dos."}, {"comparar": "hoy", "dice": "Tres."}, {"aislar": "torre", "dice": "Cuatro."},
        {"camara": "cerca", "dice": "Cinco."}, {"camara": "cerca", "dice": "Seis."}, {"zoom": 2.9, "dice": "Siete."},
        {"dice": "Ocho."}, {"girar": True, "dice": "Nueve."}, {"girar": False, "inmersion": "torre_hoy", "dice": "Diez."},
        {"inmersion": "maqueta", "mover": {"elevacion": 70}, "dice": "Once."}, {"paso": "torre_pisos", "dice": "Doce."}]})
    e = r.acciones[0]["recorrido"]["escenas"]
    mover = [x["mover"] for x in e]
    assert mover[0] == {"giro": 10, "zoom": 1.06}                 # el primer paso llega a su encuadre y termina girando
    assert mover[1:4] == [{"giro": -12}, {"giro": 14}, {"giro": -10}]   # siguen desde ahí: solo giran
    assert mover[4] is None                                       # pidió un encuadre: la cámara ya viaja
    assert mover[5] == {"giro": 12, "zoom": 2.01}                 # el mismo encuadre otra vez: parte del acercamiento de «cerca»
    assert mover[6] is None and mover[7] == {"giro": -14, "zoom": 3}   # el acercamiento no pasa de su tope
    assert mover[8] is None and mover[9] is None                  # girando sola; dentro de un modelo del atlas
    assert mover[10] == {"elevacion": 70} and mover[11] is None   # el que pide el paso; otro paso del capítulo
    assert all(rec.mover_valido(m) for m in mover) and rec.validar(r.acciones[0]["recorrido"], G) == []
    # El movimiento por omisión no es un chip («Recorre con la cámara» es el que pide el modelo) y el modelo lo sabe
    hace = [x["hace"] for x in r.acciones[1]["escenas"]]
    assert "mover" not in hace[1] and hace[10] == ["mover"]
    assert "la cámara se mueve un poco sola" in r.contenido["pasos"][1]["muestra"]
    assert "termina a 70° sobre el horizonte" in r.contenido["pasos"][10]["muestra"]
    # Tres pasos seguidos que solo dejan a la cámara moverse sola: el aviso de que cada paso debería mostrar algo
    _, r = _armar(entrada={"op": "recorrido", "titulo": "Quieta", "pasos": [
        {"capitulo": "salud", "paso": "torre", "dice": "Uno."}, {"dice": "Dos."}, {"dice": "Tres."}],
        "cierre": {"puntos": ["Una idea"]}})
    assert r.contenido["avisos"] == [a for a in r.contenido["avisos"] if a.startswith("Pasos 1 a 3: la pantalla no muestra nada nuevo")]
    assert len(r.contenido["avisos"]) == 1


def test_la_validacion_del_recorrido_guardado():
    """`validar` (lo que lee la pantalla de la base, contra el guion vigente) con las formas nuevas, y un recorrido
    guardado antes del plan guiado, que se sigue pudiendo leer, cerrar y volver a reproducir."""
    db, r = _armar(entrada=PLAN)
    bueno = r.acciones[0]["recorrido"]
    copia = lambda: json.loads(json.dumps(bueno))   # noqa: E731

    def con(n, **cambios):
        x = copia()
        for k, valor in cambios.items():
            if k in rec.VISUAL:
                x["escenas"][n]["visual"][k] = valor
            else:
                x["escenas"][n][k] = valor
        return rec.validar(x, G)
    assert con(0) == []
    for cambios, parte in (
            ({"elevacion": 7}, "la elevación va de 8 a 85"), ({"elevacion": 60.5}, "la elevación"), ({"elevacion": True}, "la elevación"),
            ({"zoom": 3.01}, "el zoom va de 0,3 a 3"), ({"zoom": 1.234}, "el zoom"), ({"zoom": "2"}, "el zoom"),
            ({"mirar": "plaza"}, "mirar «plaza» no es una pieza ni un componente con lugar"), ({"mirar": 3}, "mirar no es un id"),
            ({"aislar": "telemetria"}, "aislar «telemetria» no es una pieza"),
            ({"mostrar": ["torre", "torre"]}, "mostrar no es una lista"), ({"mostrar": "torre"}, "mostrar no es una lista"),
            ({"ocultar": ["softbol"]}, "ocultar: «softbol» no es una pieza de la maqueta del capítulo"),
            ({"ocultar": ["torre"] * 9}, "ocultar no es una lista"),
            ({"sin": ["torre"]}, "sin no es una lista"), ({"sin": ["torre.techo"]}, "sin: «torre.techo» no es una parte"),
            ({"sin": ["softbol.cubierta"]}, "sin: «softbol.cubierta» no es una parte"),
            ({"mover": {}}, "mover no tiene la forma"), ({"mover": {"giro": 361}}, "mover"), ({"mover": {"giro": 1.5}}, "mover"),
            ({"mover": {"zoom": 0.2}}, "mover"), ({"mover": {"elevacion": 90}}, "mover"), ({"mover": {"altura": 3}}, "mover"),
            ({"mover": {"giro": None}}, "mover"), ({"mover": [40]}, "mover"), ({"animar": None}, "animar es verdadero o falso"),
            ({"animar": 1}, "animar")):
        assert any(parte in p for p in con(0, **cambios)), (cambios, con(0, **cambios))
    assert con(0, mirar="torre", zoom=0.3, elevacion=8, mover={"giro": -360, "zoom": 3, "elevacion": 85}, animar=True) == []
    assert con(0, mirar="telesalud") == []   # un componente con lugar en la maqueta también se puede mirar
    # Una escena sin `mover` o sin `animar`, o lo visual sin una de sus partes, no tiene la forma
    for quitar in ("mover", "animar"):
        x = copia()
        del x["escenas"][0][quitar]
        assert rec.validar(x, G) == ["escena 1: no tiene la forma"]
    x = copia()
    del x["escenas"][0]["visual"]["sin"]
    assert rec.validar(x, G) == ["escena 1: lo visual no tiene sus partes"]
    assert rec.validar({**bueno, "escenas": [bueno["escenas"][0]] * 13}, G) == ["el recorrido lleva de 1 a 12 escenas"]
    # Sin guion (la forma sola) también se revisan los rangos, no si las piezas existen
    assert rec.validar(con and {**copia(), "escenas": [{**bueno["escenas"][0], "visual": {
        **bueno["escenas"][0]["visual"], "aislar": "no_existe", "sin": ["a.b"]}}]}) == []
    # Uno guardado antes del plan guiado (siete partes, sin `mover` ni `animar`): se lee al día y se puede reproducir
    viejas = [{k: v for k, v in {**e, "visual": {k: e["visual"][k] for k in (
        "enfoque", "camara", "rumbo", "girar", "comparar", "detalle", "inmersion")}}.items() if k not in ("mover", "animar")}
        for e in _armar()[1].acciones[0]["recorrido"]["escenas"]]
    db.pantallas.update_one({"_id": 7}, {"$set": {"recorrido.escenas": viejas, "recorrido.id": "c" * 12}})
    leido = pantalla.recorrido_de(db.pantallas.find_one({"_id": 7}), G)
    assert leido and rec.validar({k: leido[k] for k in ("id", "titulo", "escenas", "cierre")}, G) == []
    assert all(e["mover"] is None and e["animar"] is False and set(e["visual"]) == set(rec.VISUAL) for e in leido["escenas"])
    assert _avance(db, 7, "c" * 12, 2, "fin", de=5)
    d = db.pantallas.find_one({"_id": 7})
    assert d["recorrido"]["cerrado"] is True and (d["inmersion"], d["mover"], d["animar"], d["sin"]) == ("torre_hoy", None, False, [])
    nuevo = pantalla.controlar(db, 7, G, "reproducir", "panel", rid="c" * 12)["recorrido"]
    assert nuevo["id"] != "c" * 12 and nuevo["escenas"] == leido["escenas"]


def test_por_mcp_hace_falta_la_pantalla_en_off():
    db = _Base()
    with pytest.raises(ErrorHerramienta) as e:
        _hacer(db, 8, ENTRADA, por="mcp")
    assert e.value.codigo == "sin_pantalla" and e.value.estado == 409
    # Con la pantalla en off abierta, suena allá y no hay acciones para el navegador del agente
    pantalla.marcar_vista(db, 8)
    r = _hacer(db, 8, ENTRADA, por="mcp")
    assert r.acciones == [] and db.pantallas.find_one({"_id": 8})["recorrido"]["destino"] == "pantalla_off"
    e = pantalla.para_pantalla(pantalla.estado(db.pantallas.find_one({"_id": 8}), G), db.pantallas.find_one({"_id": 8}), G)
    assert e["recorrido"]["id"] == db.pantallas.find_one({"_id": 8})["recorrido"]["id"] and e["recorrido"]["edad_s"] >= 0


def test_avance_estado_control_y_colapso():
    db, r = _armar()
    rid = r.acciones[0]["recorrido"]["id"]
    assert pantalla.guardar_progreso(db, 7, {"rid": rid, "n": 2, "de": 5, "fase": "narrando", "frase": 0,
                                             "voz": "sin_voces", "aviso": "atlas"})
    assert not pantalla.guardar_progreso(db, 7, {"rid": "0" * 12, "n": 1, "de": 5, "fase": "narrando", "frase": 0,
                                                 "voz": "sin_voces"})
    est = _hacer(db, 7, {"op": "estado"}, por="asistente").contenido["pantalla"]["plan"]
    assert est["paso"] == 2 and est["de"] == 5 and est["fase"] == "narrando" and est["avisos"] == [{"n": 2, "tipo": "atlas"}]
    assert est["dice_en_curso"].startswith("Así está hoy el predio") and "paso 2 de 5 del plan, narrando" in est["muestra"]
    t = pantalla.describir_recorrido(pantalla.resumen_recorrido(db.pantallas.find_one({"_id": 7}), G))
    assert t.startswith("Plan «La torre del hospital» en la pestaña o el proyector: paso 2 de 5 del plan, narrando")
    assert t.endswith("avisos: paso 2, el modelo del atlas no cargó")
    # El aviso nuevo: parte de lo pedido no se pudo mostrar (la presentación lo descartó y siguió)
    assert pantalla.guardar_progreso(db, 7, {"rid": rid, "n": 2, "de": 5, "fase": "narrando", "frase": 0,
                                             "voz": "sin_voces", "aviso": "parcial"})
    assert "paso 2, parte de lo pedido no se pudo mostrar" in pantalla.describir_recorrido(
        pantalla.resumen_recorrido(db.pantallas.find_one({"_id": 7}), G))
    assert rec.AVISOS[-1] == "parcial" and set(pantalla.AVISO) == set(rec.AVISOS)
    # Un control: va como acción a la pestaña (el recorrido suena allá)
    c = _hacer(db, 7, {"op": "control_recorrido", "accion": "pausar"}, por="asistente")
    assert c.acciones == [{"tipo": "presentacion", "op": "control_recorrido", "rid": rid, "accion": "pausar"}]
    assert c.contenido["plan"] == {"id": rid, "titulo": "La torre del hospital", "paso": 2, "de": 5, "fase": "narrando"}
    assert c.resumen == "Pausé el plan «La torre del hospital»"
    # Otra orden lo colapsa: queda cerrado en la escena donde iba y lo pedido se aplica encima; a la pestaña, donde
    # suena, primero la orden de detenerlo
    v = _hacer(db, 7, {"op": "visual", "camara": "aerea"}, por="asistente")
    assert v.acciones[0] == {"tipo": "presentacion", "op": "control_recorrido", "rid": rid, "accion": "detener",
                             "motivo": "otra_orden"}
    assert v.acciones[1]["op"] == "visual" and len(v.acciones) == 2
    d = db.pantallas.find_one({"_id": 7})
    assert d["recorrido"]["cerrado"] is True and (d["paso"], d["inmersion"], d["camara"]) == (3, "torre_hoy", "aerea")
    # Cerrado, el último avance a medias se lee como detenido
    assert pantalla.resumen_recorrido(d, G)["fase"] == "detenido"
    assert not pantalla.guardar_progreso(db, 7, {"rid": rid, "n": 3, "de": 5, "fase": "narrando", "frase": 0,
                                                 "voz": "sin_voces"})
    with pytest.raises(ErrorHerramienta) as e:
        _hacer(db, 7, {"op": "control_recorrido", "accion": "pausar"}, por="asistente")
    assert e.value.codigo == "sin_recorrido"
    # «reproducir» lo vuelve a empezar con otro id, y con la tarjeta del nuevo (la del viejo sigue el avance de su id)
    db, r = _armar()
    viejo = r.acciones[0]["recorrido"]["id"]
    c = _hacer(db, 7, {"op": "control_recorrido", "accion": "reproducir"}, por="asistente")
    nuevo = c.acciones[0]["recorrido"]["id"]
    assert c.acciones[0]["op"] == "recorrido" and nuevo != viejo
    assert c.acciones[1] == {**r.acciones[1], "id": nuevo, "sugerencias": []}
    assert db.pantallas.find_one({"_id": 7})["recorrido"]["id"] == nuevo


def _avance(db, uid, rid, n, fase, de=5, **extra):
    return pantalla.guardar_progreso(db, uid, {"rid": rid, "n": n, "de": de, "fase": fase, "frase": 0,
                                               "voz": "sin_voces", **extra})


def test_un_capitulo_repetido_sin_paso_sigue_en_el_mismo_paso():
    """El modelo suele repetir el capítulo en cada escena: sin paso, sigue en el de la anterior (con lo visual que traía),
    y lo que resalta se valida contra ese paso. En otro capítulo sin paso, va al primero."""
    _, r = _armar(entrada={"op": "recorrido", "titulo": "La torre", "escenas": [
        {"capitulo": "salud", "paso": "torre", "inmersion": "torre_hoy", "narracion": "Así está hoy el predio."},
        {"capitulo": "Salud", "camara": "aerea", "resaltar": {"leyenda": 1}, "narracion": "Desde arriba se ve el predio."},
        {"capitulo": "aguas", "narracion": "Y el agua."}]})
    e1, e2, e3 = r.acciones[0]["recorrido"]["escenas"]
    assert (e1["capitulo"], e1["paso"]) == (e2["capitulo"], e2["paso"]) == ("salud", 3)
    assert e2["visual"]["inmersion"] == "torre_hoy" and e2["visual"]["camara"] == "aerea"
    assert e2["resaltar"] == {"tipo": "leyenda", "n": 1}
    assert (e3["capitulo"], e3["paso"], e3["visual"]) == ("aguas", 1, rec.VISUAL_INICIAL)


def test_una_orden_que_falla_no_corta_el_recorrido():
    """Lo que no existe no mueve nada: tampoco cierra el recorrido que suena (ni sube la versión de la pantalla)."""
    db = _Base()
    pantalla.marcar_vista(db, 7)
    _, r = _armar(db)
    rid = db.pantallas.find_one({"_id": 7})["recorrido"]["id"]
    assert r.acciones[-1]["destino"] == "pantalla_off" and _avance(db, 7, rid, 2, "narrando")
    v = db.pantallas.find_one({"_id": 7})["v"]
    for malo in ({"op": "visual", "enfoque": "no_existe_esto"}, {"op": "visual", "capitulo": "aguas", "camara": "aerea"},
                 {"op": "ir", "capitulo": "no existe"}, {"op": "ir", "capitulo": "salud", "paso": 40},
                 {"op": "visual", "inmersion": "otra_cosa"}, {"op": "siguiente", "capitulo": "salud", "paso": 11}):
        for por in ("asistente", "mcp"):
            with pytest.raises(ErrorHerramienta):
                _hacer(db, 7, malo, por=por)
    d = db.pantallas.find_one({"_id": 7})
    assert d["recorrido"]["cerrado"] is False and d["v"] == v and _avance(db, 7, rid, 2, "narrando", frase=1)
    # Lo que sí vale lo cierra, con lo pedido encima de la escena en curso (la pantalla en off se entera sola: sin
    # acción para el navegador)
    ok = _hacer(db, 7, {"op": "visual", "capitulo": "salud", "camara": "aerea"}, por="asistente")
    d = db.pantallas.find_one({"_id": 7})
    assert ok.acciones == [] and d["recorrido"]["cerrado"] is True and (d["paso"], d["camara"]) == (3, "aerea")
    assert d["inmersion"] == "torre_hoy"


def test_el_contexto_el_estado_y_las_ordenes_parten_de_la_escena_en_curso():
    """Mientras suena, la base guardada es la última escena, pero la sala ve la escena en curso: eso dicen el estado, el
    contexto del asistente y lo que recibe una pantalla en off que se abre a mitad, y de ahí parte la orden."""
    entrada = {"op": "recorrido", "titulo": "Dos capítulos", "escenas": [
        {"capitulo": "salud", "paso": "torre", "camara": "oblicua", "narracion": "La torre."},
        {"capitulo": "aguas", "paso": 2, "narracion": "El agua."}]}
    db, r = _armar(entrada=entrada)
    rid = r.acciones[0]["recorrido"]["id"]
    assert _avance(db, 7, rid, 1, "narrando", de=2)
    d = db.pantallas.find_one({"_id": 7})
    assert (d["capitulo"], d["paso"]) == ("aguas", 2)   # la base guardada: la que queda al terminar
    est = _hacer(db, 7, {"op": "estado"}, por="asistente").contenido["pantalla"]
    assert (est["capitulo"], est["paso"], est["visual"]["camara"]) == ("salud", 3, "oblicua")
    assert est["muestra"].startswith("Salud (salud), paso 3") and est["plan"]["paso"] == 1
    # Una pantalla en off que se abre ahora muestra la escena 1 (el recorrido suena en la pestaña: no se lo lleva)
    e = pantalla.para_pantalla(pantalla.estado(d, G), d, G)
    assert (e["capitulo"], e["paso"], e["camara"], e["recorrido"]) == ("salud", 3, "oblicua", None)
    pantalla.marcar_vista(db, 7)
    assert sistema.pantalla_del_contexto(db, 7).startswith("Salud (salud), paso 3")
    assert "paso 1 de 2 del plan, narrando" in sistema.recorrido_del_contexto(db, 7)
    # «siguiente» desde la pantalla parte de ahí, y visual con el capítulo de la escena en curso no da 409
    assert _hacer(db, 7, {"op": "visual", "capitulo": "salud", "girar": True}, por="mcp").contenido["capitulo"]["id"] == "salud"
    db, r = _armar(entrada=entrada)
    _avance(db, 7, r.acciones[0]["recorrido"]["id"], 1, "narrando", de=2)
    pantalla.marcar_vista(db, 7)
    s = _hacer(db, 7, {"op": "siguiente"}, por="asistente")
    assert (s.contenido["capitulo"]["id"], s.contenido["paso"]) == ("salud", 4)


def test_un_avance_final_cierra_el_recorrido_salvo_el_traspaso():
    db, r = _armar()
    rid = r.acciones[0]["recorrido"]["id"]
    escenas = r.acciones[0]["recorrido"]["escenas"]
    v = db.pantallas.find_one({"_id": 7})["v"]
    # El traspaso al proyector (y un reemplazo) no lo cierran: el mismo id sigue en otro lado
    for motivo in ("proyector", "reemplazo"):
        assert _avance(db, 7, rid, 2, "detenido", motivo=motivo)
        assert db.pantallas.find_one({"_id": 7})["recorrido"]["cerrado"] is False
    assert _avance(db, 7, rid, 2, "narrando") and db.pantallas.find_one({"_id": 7})["v"] == v
    # Un error en la escena 3: cerrado, con la base en esa escena y la versión arriba (la pantalla en off lo aplica)
    assert _avance(db, 7, rid, 3, "error", motivo="escena_fallida")
    d = db.pantallas.find_one({"_id": 7})
    assert d["recorrido"]["cerrado"] is True and d["v"] == v + 1
    assert {k: d[k] for k in rec.estado_de_escena(escenas[2])} == rec.estado_de_escena(escenas[2])
    assert pantalla.resumen_recorrido(d, G)["fase"] == "error"
    # Ya cerrado: el avance no es de nadie (la API responde 409) y los controles no lo toman por vivo
    assert not _avance(db, 7, rid, 3, "narrando")
    for por in ("asistente", "mcp"):
        with pytest.raises(ErrorHerramienta) as e:
            _hacer(db, 7, {"op": "control_recorrido", "accion": "anterior"}, por=por)
        assert e.value.codigo == "sin_recorrido"
    # «fin» y «detenido» por un botón también cierran
    for fase, n in (("fin", 5), ("detenido", 2)):
        db, r = _armar()
        rid = r.acciones[0]["recorrido"]["id"]
        assert _avance(db, 7, rid, n, fase, **({"motivo": "boton"} if fase == "detenido" else {}))
        d = db.pantallas.find_one({"_id": 7})
        assert d["recorrido"]["cerrado"] is True and d["paso"] == r.acciones[0]["recorrido"]["escenas"][n - 1]["paso"]
        assert pantalla.resumen_recorrido(d, G)["fase"] == fase


def test_el_contexto_deja_de_nombrar_un_recorrido_terminado_o_abandonado():
    ahora = datetime.now(timezone.utc)
    db, r = _armar()
    rid = r.acciones[0]["recorrido"]["id"]
    d = db.pantallas.find_one({"_id": 7})
    # Sin avance (nunca sonó): un rato sí, media hora después no
    assert pantalla.resumen_recorrido(d, G, ahora + timedelta(minutes=5))["fase"] == "sin_avance"
    assert pantalla.resumen_recorrido(d, G, ahora + timedelta(minutes=31)) is None
    # En pausa porque la persona escribió y después cerró la pestaña: lo nombra con la antigüedad, y luego no
    _avance(db, 7, rid, 2, "pausa", motivo="mensaje")
    d = db.pantallas.find_one({"_id": 7})
    x = pantalla.resumen_recorrido(d, G, ahora + timedelta(minutes=10, seconds=30))
    t = pantalla.describir_recorrido(x)
    assert "en pausa porque la persona escribió" in t and t.endswith("; el último avance llegó hace 10 min")
    assert pantalla.resumen_recorrido(d, G, ahora + timedelta(minutes=31)) is None
    assert "hace" not in pantalla.describir_recorrido(pantalla.resumen_recorrido(d, G, ahora))
    # Terminado: dos minutos
    _avance(db, 7, rid, 5, "fin")
    d = db.pantallas.find_one({"_id": 7})
    assert pantalla.resumen_recorrido(d, G, ahora + timedelta(minutes=1))["fase"] == "fin"
    assert pantalla.resumen_recorrido(d, G, ahora + timedelta(minutes=3)) is None
    # Un «detenido» que no lo cierra (el traspaso que nunca llegó al proyector) también es final para el contexto
    db, r = _armar()
    _avance(db, 7, r.acciones[0]["recorrido"]["id"], 2, "detenido", motivo="proyector")
    assert pantalla.resumen_recorrido(db.pantallas.find_one({"_id": 7}), G, ahora + timedelta(minutes=3)) is None


def test_lo_que_dejo_la_verificacion_del_plan_guiado():
    """Casos que la verificación adversaria del plan encontró: la cámara sigue desde donde la dejó el `mover` anterior,
    y varios descartes que pasaban sin aviso o tumbaban el plan."""
    pasos = lambda r: r.acciones[0]["recorrido"]["escenas"]   # noqa: E731
    # Después de un `mover` con acercamiento, el movimiento suave solo gira (no reabre el encuadre ni acumula zoom)
    _, r = _armar(entrada={"op": "recorrido", "titulo": "Sigue", "pasos": [
        {"capitulo": "salud", "paso": "torre", "camara": "oblicua", "mover": {"zoom": 2, "elevacion": 60}, "dice": "Uno."},
        {"sin": ["torre.cubierta"], "dice": "Dos."}, {"camara": "aerea", "dice": "Tres."}, {"dice": "Cuatro."}]})
    assert [e["mover"] for e in pasos(r)] == [{"zoom": 2, "elevacion": 60}, {"giro": 10}, None, {"giro": -12, "zoom": 1.06}]
    # «camara: paso» con su elevación y su acercamiento en el mismo paso: se respetan (como en la op visual)
    _, r = _armar(entrada={"op": "recorrido", "titulo": "Paso", "pasos": [
        {"capitulo": "salud", "paso": "torre", "camara": "aerea", "zoom": 2, "dice": "Uno."},
        {"camara": "paso", "elevacion": 50, "zoom": 1.5, "dice": "Dos."}]})
    v = pasos(r)[1]["visual"]
    assert (v["camara"], v["elevacion"], v["zoom"]) == ("paso", 50, 1.5) and "avisos" not in r.contenido
    # Un cierre con ideas de más se recorta; las sugerencias que no sirven se descartan (son solo para el chat)
    _, r = _armar(entrada={"op": "recorrido", "titulo": "Cierre", "pasos": [{"capitulo": "salud", "paso": "torre", "dice": "Uno."}],
                           "cierre": {"puntos": ["Idea una", "Idea dos", "Idea tres", "Idea cuatro"]},
                           "sugerencias": ["x", "s" * 70, "¿Y la telesalud?", "Cuesta $ 5"]})
    assert r.acciones[0]["recorrido"]["cierre"] == {"puntos": ["Idea una", "Idea dos", "Idea tres"]}
    assert r.acciones[1]["sugerencias"] == ["¿Y la telesalud?"]
    assert _armar(entrada={"op": "recorrido", "titulo": "Una", "pasos": [{"capitulo": "salud", "paso": "torre", "dice": "Uno."}],
                           "sugerencias": "Ver el laboratorio"})[1].acciones[1]["sugerencias"] == ["Ver el laboratorio"]
    # Una lista mal formada no vacía la que venía de antes, y lo dice
    _, r = _armar(entrada={"op": "recorrido", "titulo": "Lista", "pasos": [
        {"capitulo": "salud", "paso": "torre", "mostrar": ["telesalud"], "dice": "Uno."}, {"mostrar": {"a": 1}, "dice": "Dos."}]})
    assert pasos(r)[1]["visual"]["mostrar"] == ["telesalud"]
    assert any("Paso 2" in a and "mostrar" in a for a in r.contenido["avisos"]), r.contenido["avisos"]
    # La pieza aislada en un paso anterior que ahora se pide ocultar deja de estar aislada
    _, r = _armar(entrada={"op": "recorrido", "titulo": "Aislar", "pasos": [
        {"capitulo": "salud", "paso": "torre", "aislar": "torre", "dice": "Uno."}, {"ocultar": ["torre"], "dice": "Dos."}]})
    v = pasos(r)[1]["visual"]
    assert v["aislar"] is None and v["ocultar"] == ["torre"]
    # Los nombres parecidos: sin palabras vacías, y una palabra corta tiene que estar entera
    lista = [{"id": "torre", "nombre": "Torre nueva de cuatro pisos"}, {"id": "reduccion", "nombre": "Reducción de pérdidas"},
             {"id": "red", "nombre": "Red de telesalud"}]
    assert guion_presentacion.parecido(lista, "la torre")["id"] == "torre"
    assert guion_presentacion.parecido(lista, "red")["id"] == "red"
    assert guion_presentacion.parecido(lista[:2], "red") is None and guion_presentacion.parecido(lista, "de la") is None
    assert guion_presentacion.parecido(lista, "reduc")["id"] == "reduccion"
    # En la pantalla en off, `mover` y `animar` son de la orden `visual` que los trajo: otra orden los deja en nada
    db = _Base()
    _hacer(db, 7, {"op": "ir", "capitulo": "salud", "paso": "torre"})
    _hacer(db, 7, {"op": "visual", "mover": {"giro": 40}, "animar": True})
    d = db.pantallas.find_one({"_id": 7})
    assert d["mover"] == {"giro": 40} and d["animar"] is True
    _hacer(db, 7, {"op": "explicar", "explicacion": "Una frase."})
    d = db.pantallas.find_one({"_id": 7})
    assert d["mover"] is None and d["animar"] is False


def test_un_control_tras_una_pausa_larga_revive_el_recorrido():
    """En pausa más de media hora (una ronda de preguntas) y después «continuar»: el control cuenta como actividad. Si
    no, la tarjeta de la pantalla en off, que pregunta antes de que llegue el avance del televisor, lo daba por detenido
    mientras el televisor volvía a narrar."""
    ahora = datetime.now(timezone.utc)
    db = _Base()
    pantalla.marcar_vista(db, 7)
    _armar(db)
    rid = db.pantallas.find_one({"_id": 7})["recorrido"]["id"]
    _avance(db, 7, rid, 2, "pausa", motivo="mensaje")
    viejo = ahora - timedelta(minutes=31)
    db.pantallas.update_one({"_id": 7}, {"$set": {"progreso.en": viejo, "recorrido.creado": viejo, "actualizada": viejo}})
    # Con la pantalla en off abierta, una pausa no se abandona: la sala la tiene delante (y la tarjeta la sigue)
    assert pantalla.resumen_recorrido(db.pantallas.find_one({"_id": 7}), G)["fase"] == "pausa"
    quien = SimpleNamespace(uid=7)
    assert api_pantalla.ver_recorrido(db=db, quien=quien)["vigente"] == {"id": rid, "cerrado": False}
    # La pantalla se cerró hace rato: abandonado para el contexto, pero sigue siendo el vigente
    db.pantallas.update_one({"_id": 7}, {"$set": {"visto": ahora - timedelta(minutes=5)}})
    assert pantalla.resumen_recorrido(db.pantallas.find_one({"_id": 7}), G) is None
    x = api_pantalla.ver_recorrido(db=db, quien=quien)
    assert x["recorrido"] is None and x["vigente"] == {"id": rid, "cerrado": False}
    # Otra escritura de la pantalla (la pantalla completa no lo cierra) no lo revive para el modelo
    _hacer(db, 7, {"op": "pantalla_completa", "activar": True}, por="asistente")
    d = db.pantallas.find_one({"_id": 7})
    assert d["recorrido"]["cerrado"] is False and pantalla.resumen_recorrido(d, G) is None
    # Un control de ese recorrido sí
    pantalla.controlar(db, 7, G, "continuar", "panel", rid=rid)
    assert pantalla.resumen_recorrido(db.pantallas.find_one({"_id": 7}), G)["fase"] == "pausa"
    # Y uno cerrado deja de ser reanudable
    _hacer(db, 7, {"op": "ir", "capitulo": "aguas"}, por="asistente")
    assert api_pantalla.ver_recorrido(db=db, quien=quien)["vigente"] == {"id": rid, "cerrado": True}


def test_un_recorrido_para_la_pantalla_en_off_detiene_el_que_suena_en_la_pestana():
    """Sin pantalla en off, el recorrido suena en la pestaña; se abre la pantalla y el asistente arma otro: va a la
    pantalla y el de la pestaña se detiene allá (si no, las dos voces se pisaban, y uno en pausa no se enteraba nunca)."""
    db, r = _armar()
    viejo = r.acciones[0]["recorrido"]["id"]
    _avance(db, 7, viejo, 2, "pausa", motivo="mensaje")
    pantalla.marcar_vista(db, 7)
    assert api_pantalla.ver_recorrido(db=db, quien=SimpleNamespace(uid=7))["conectada"] is True
    b = _hacer(db, 7, ENTRADA, por="asistente")
    assert b.acciones[0] == {"tipo": "presentacion", "op": "control_recorrido", "rid": viejo, "accion": "detener",
                             "motivo": "otra_orden"}
    assert [a["tipo"] for a in b.acciones[1:]] == ["recorrido"] and b.acciones[1]["destino"] == "pantalla_off"
    # Uno que ya sonaba en la pantalla en off, no: le llega el nuevo
    c = _hacer(db, 7, ENTRADA, por="asistente")
    assert [a["tipo"] for a in c.acciones] == ["recorrido"]
    # Sin la pantalla, la tarjeta lo sabe (`conectada`): en pausa no hay otros avances que lo digan
    db.pantallas.update_one({"_id": 7}, {"$set": {"visto": datetime.now(timezone.utc) - timedelta(minutes=1)}})
    assert api_pantalla.ver_recorrido(db=db, quien=SimpleNamespace(uid=7))["conectada"] is False


def test_detener_no_cierra_el_recorrido_que_llego_entretanto():
    """Entre la lectura del control y su escritura llega otro recorrido: el «detener» iba para el anterior y el nuevo
    sigue abierto."""
    db, r = _armar()
    viejo = r.acciones[0]["recorrido"]["id"]
    escribir = db.pantallas.find_one_and_update
    llegado = []

    def con_carrera(filtro, cambios, **kw):
        if not llegado and (cambios.get("$set") or {}).get("control_recorrido"):
            llegado.append(True)
            pantalla.guardar_recorrido(db, 7, {**r.acciones[0]["recorrido"], "id": "b" * 12, "titulo": "Otro recorrido"},
                                       "vista", "asistente")
        return escribir(filtro, cambios, **kw)
    db.pantallas.find_one_and_update = con_carrera
    with pytest.raises(ValueError, match="sin_recorrido"):
        pantalla.controlar(db, 7, G, "detener", "panel", rid=viejo)
    d = db.pantallas.find_one({"_id": 7})
    assert llegado and d["recorrido"]["titulo"] == "Otro recorrido" and d["recorrido"]["cerrado"] is False
    # Y colapsar con el id del anterior tampoco lo toca
    assert pantalla.colapsar(db, 7, G, "panel", rid=viejo) is None
    assert db.pantallas.find_one({"_id": 7})["recorrido"]["cerrado"] is False


def test_lo_que_recibe_la_pestana_cuando_el_servidor_cierra_o_reproduce():
    # Con la pantalla en off abierta después (la orden ya no va a la pestaña), igual va la de detener el que suena allá
    db, r = _armar()
    rid = r.acciones[0]["recorrido"]["id"]
    pantalla.marcar_vista(db, 7)
    v = _hacer(db, 7, {"op": "visual", "camara": "oblicua"}, por="asistente")
    assert v.acciones == [{"tipo": "presentacion", "op": "control_recorrido", "rid": rid, "accion": "detener",
                          "motivo": "otra_orden"}]
    # «siguiente» sin punto de partida (lo calcula la pestaña): también lo cierra en el servidor
    db, r = _armar()
    rid = r.acciones[0]["recorrido"]["id"]
    s = _hacer(db, 7, {"op": "siguiente"}, por="asistente")
    assert [a.get("accion") or a["op"] for a in s.acciones] == ["detener", "siguiente"]
    assert db.pantallas.find_one({"_id": 7})["recorrido"]["cerrado"] is True
    # Sin recorrido sonando, nada de más; con uno de la pantalla en off, tampoco (le llega sin recorrido)
    assert [a["op"] for a in _hacer(db, 7, {"op": "ir", "capitulo": "aguas"}, por="asistente").acciones] == ["ir"]
    db = _Base()
    pantalla.marcar_vista(db, 7)
    _armar(db)
    assert _hacer(db, 7, {"op": "explicar", "explicacion": "Una frase."}, por="asistente").acciones == []
    assert db.pantallas.find_one({"_id": 7})["recorrido"]["cerrado"] is True
    # «reproducir» en la pantalla en off: la tarjeta del nuevo, sin acción de presentación
    db = _Base()
    pantalla.marcar_vista(db, 7)
    _, r = _armar(db)
    c = _hacer(db, 7, {"op": "control_recorrido", "accion": "reproducir"}, por="asistente")
    nuevo = db.pantallas.find_one({"_id": 7})["recorrido"]["id"]
    assert [a["tipo"] for a in c.acciones] == ["recorrido"] and c.acciones[0]["id"] == nuevo != r.acciones[0]["id"]
    assert c.acciones[0]["destino"] == "pantalla_off" and c.acciones[0]["escenas"] == r.acciones[0]["escenas"]


def test_la_api_cierra_con_el_avance_final_y_reproduce_uno_cerrado():
    """Las rutas del avance y de los controles, con la base en memoria (sin MongoDB)."""
    db, r = _armar()
    rid = r.acciones[0]["recorrido"]["id"]
    quien = SimpleNamespace(uid=7)

    def avance(**x):
        p = api_pantalla.ProgresoEntrada(**{"rid": rid, "n": 5, "de": 5, "fase": "fin", "voz": "apagada", **x})
        return api_pantalla.progreso(p, db=db, quien=quien)

    def control(rid_, accion):
        return api_pantalla.control_recorrido(api_pantalla.ControlEntrada(rid=rid_, accion=accion), db=db, quien=quien)

    assert avance().status_code == 204 and db.pantallas.find_one({"_id": 7})["recorrido"]["cerrado"] is True
    for x in ({"fase": "narrando"}, {"rid": "0" * 12, "fase": "narrando"}):
        with pytest.raises(HTTPException) as e:
            avance(**x)
        assert e.value.status_code == 409
    # Volver a reproducir el que terminó (el vigente, aunque cerrado): vuelve con otro id, abierto
    x = control(rid, "reproducir")
    assert x["id"] != rid and x["cerrado"] is False and x["fase"] == "sin_avance"
    assert db.pantallas.find_one({"_id": 7})["recorrido"]["id"] == x["id"]
    # El viejo ya no es el vigente: ni reproducir ni otro control
    for accion in ("reproducir", "pausar"):
        with pytest.raises(HTTPException) as e:
            control(rid, accion)
        assert e.value.status_code == 409
    # Detener el nuevo sin avance todavía: dice cuál detuvo
    y = control(x["id"], "detener")
    assert y["id"] == x["id"] and y["cerrado"] is True


@pytest.fixture
def ctx(sesion):
    c = aa.contexto(sesion.app, sesion)
    yield c
    aa.correr(sesion, c.api.cerrar)


def test_con_personas_en_la_conversacion_no_se_proyecta_texto(sesion, ctx):
    db = sesion.app.state.db
    db[conv_db.CONVERSACIONES].update_one({"_id": ctx.conversacion_id}, {"$set": {"personas": [5]}}, upsert=True)
    assert conv_db.tiene_personas(db, ctx.conversacion_id)
    for entrada in (ENTRADA, {"op": "explicar", "explicacion": "Una frase."},
                    {"op": "ir", "capitulo": "salud", "explicacion": "Una frase."}):
        with pytest.raises(ErrorHerramienta) as e:
            aa.correr(sesion, aa.ejecutar, P, ctx, entrada)
        assert e.value.codigo == "con_personas", entrada
    # Mover sin texto sí
    assert aa.correr(sesion, aa.ejecutar, P, ctx, {"op": "ir", "capitulo": "salud"}).acciones


def test_la_api_del_avance_y_los_controles(sesion):
    db = sesion.app.state.db
    assert sesion.post("/api/pantalla/progreso", json={"rid": "a" * 12, "n": 1, "de": 1, "fase": "narrando",
                                                       "voz": "apagada"}).status_code == 409
    assert sesion.get("/api/pantalla/recorrido").json()["recorrido"] is None
    _armar(db, uid=0)
    rid = db.pantallas.find_one({"_id": 0})["recorrido"]["id"]
    ok = {"rid": rid, "n": 2, "de": 5, "fase": "sosteniendo", "frase": 0, "voz": "activa", "t_ms": 1200}
    assert sesion.post("/api/pantalla/progreso", json=ok).status_code == 204
    for malo in ({**ok, "fase": "otra"}, {**ok, "n": 6}, {**ok, "extra": 1}, {**ok, "n": "2"}, {**ok, "rid": "X" * 12}):
        assert sesion.post("/api/pantalla/progreso", json=malo).status_code == 422, malo
    x = sesion.get("/api/pantalla/recorrido").json()["recorrido"]
    assert (x["id"], x["escena"], x["fase"], x["voz"]) == (rid, 2, "sosteniendo", "activa")
    r = sesion.post("/api/pantalla/recorrido/control", json={"rid": rid, "accion": "pausar"})
    assert r.status_code == 200 and r.json()["id"] == rid
    assert sesion.post("/api/pantalla/recorrido/control", json={"rid": "b" * 12, "accion": "pausar"}).status_code == 409
    assert sesion.post("/api/pantalla/recorrido/control", json={"rid": rid, "accion": "borrar"}).status_code == 422
    # La pantalla en off recibe el recorrido solo si es para ella (este es de la pestaña del chat)
    assert sesion.get("/api/pantalla").json()["recorrido"] is None


def test_sin_sesion_no_hay_avance(cliente):
    assert cliente.post("/api/pantalla/progreso", json={}).status_code in (401, 403)
    assert cliente.get("/api/pantalla/recorrido").status_code == 401


# ───────────────────────────── Los mismos topes en los cuatro lados ─────────────────────────────

def _js_const(js: str, nombre: str) -> str:
    m = re.search(rf"export const {nombre} = (.+?);\n", js, re.S)
    assert m, nombre
    return m.group(1)


def _lista(js: str, nombre: str) -> list:
    return json.loads(_js_const(js, nombre).replace("'", '"').replace("\n", " "))


def test_topes_y_listas_iguales_en_servidor_puente_mando_y_reproductor():
    puente, mando = PUENTE_JS.read_text(encoding="utf-8"), MANDO_JS.read_text(encoding="utf-8")
    repro = REPRODUCTOR_JS.read_text(encoding="utf-8")
    for nombre in ("MAX_TITULO", "MAX_FRASES", "MAX_ESCENAS", "MAX_PUNTO", "MAX_CIERRE"):
        valor = str(getattr(rec, nombre))
        assert _js_const(puente, nombre) == valor and _js_const(mando, nombre) == valor, nombre
    assert _js_const(puente, "MAX_SOSTENER_MS") == str(rec.MAX_SOSTENER_MS)
    assert json.loads(re.sub(r"(\w+):", r'"\1":', _js_const(puente, "RESALTAR"))) == rec.RESALTAR
    assert json.loads(re.sub(r"(\w+):", r'"\1":', _js_const(mando, "RESALTAR"))) == rec.RESALTAR
    for nombre in ("FASES", "TERMINALES", "VOCES", "MOTIVOS", "AVISOS"):
        assert _lista(puente, nombre) == list(getattr(rec, nombre)), nombre
    assert _lista(puente, "CONTROLES") == [c for c in rec.CONTROLES if c != "reproducir"]
    assert _lista(repro, "FASES") == list(rec.FASES) and _lista(repro, "TERMINALES") == list(rec.TERMINALES)
    # Doce pasos y el aviso `parcial`, en los cuatro lados (el servidor, el puente, el mando y el reproductor)
    assert rec.MAX_ESCENAS == 12 and _js_const(repro, "MAX_ESCENAS") == "12"
    assert _lista(mando, "AVISOS") == _lista(repro, "AVISOS") == list(rec.AVISOS) and rec.AVISOS[-1] == "parcial"
    # Los tiempos de la sección 6 del contrato, iguales en el reproductor y en el servidor (que estima con ellos)
    tiempos = {"PREVIA_MS": 1800, "RESPIRO_MS": 350, "ENTRE_FRASES_MS": 250, "SOSTENER_MS": 1300,
               "SOSTENER_MIRAR_MS": 2700, "CIERRE_SOSTENER_MS": 4000, "PREGUNTAS_MS": 12000}
    for nombre, valor in tiempos.items():
        assert getattr(rec, nombre) == valor and _js_const(repro, nombre) == str(valor), nombre
    assert rec.ASIENTO_MS == {"mismo": 0, "paso": 400, "capitulo": 600} and rec.ASIENTO_ATLAS_MS == 4000
    assert "Math.min(16000, Math.max(3200, 1500 + 62 *" in repro   # lectura_ms
    # (`narracionMs` del reproductor: el `ms` de la orden `escena`; `narracion_ms` aquí)
    assert rec.narracion_ms(["x" * 100, "y"]) == (1500 + 62 * 100) + 3200 + rec.ENTRE_FRASES_MS
    tarjeta = TARJETA_JS.read_text(encoding="utf-8")
    assert set(re.findall(r"^  (\w+): \['", tarjeta, re.M)) | set(re.findall(r", (\w+): \['", tarjeta)) == set(hi.HACE)


def _visual_js(js: str, nombre: str) -> list[str]:
    """Las claves de un objeto literal `const <nombre> = {...}` de un módulo (lo visual y lo que vale en cada paso)."""
    m = re.search(rf"const {nombre} = (?:Object\.freeze\()?\{{(.+?)\n?\}}\)?;", js, re.S)
    assert m, nombre
    return re.findall(r"(?:^|[{,\n])\s*(\w+):", re.sub(r"\([^()]*\)|\[[^\[\]]*\]|'[^']*'", "0", m.group(1)))


def test_las_cinco_copias_de_lo_visual():
    """La forma de lo visual está escrita cinco veces (y en `INICIAL` de visual.js), con las mismas claves en el mismo
    orden: mando.js, el puente, app/pantalla.py, app/recorrido.py y la herramienta. Y lo que vale en cada paso."""
    orden = ["enfoque", "camara", "rumbo", "elevacion", "zoom", "mirar", "girar", "comparar", "detalle", "inmersion",
             "mostrar", "ocultar", "aislar", "sin"]
    inicial = {"enfoque": None, "camara": "paso", "rumbo": None, "elevacion": None, "zoom": None, "mirar": None,
               "girar": False, "comparar": "proyecto", "detalle": None, "inmersion": None, "mostrar": [], "ocultar": [],
               "aislar": None, "sin": []}
    assert list(inicial) == orden
    # El servidor: el recorrido, la pantalla (con el tema, que no vuelve al cambiar de paso) y la herramienta
    assert list(rec.VISUAL) == orden and rec.VISUAL_INICIAL == inicial and list(rec.VISUAL_INICIAL) == orden
    assert pantalla.VISUAL_INICIAL == inicial and list(pantalla.VISUAL) == [*orden, "tema"]
    assert hi.PARTES_VISUAL == pantalla.VISUAL and hi.ACCIONES_VISUAL == pantalla.ACCIONES == ("mover", "animar", "simular")
    assert pantalla.CAMPOS == ("capitulo", "paso", "explicacion", "panel", "indice", "fichas", "completa",
                               "orden_completa", *orden, "tema", "mover", "animar", "simular")
    assert set(pantalla.VISUAL) | set(pantalla.ACCIONES) <= set(hi.PresentacionEntrada.model_fields)
    paso = hi.EscenaEntrada.model_fields
    assert set(orden) | {"mover", "animar", "simular", "resaltar", "dice", "capitulo", "paso", "panel", "sostener"} <= set(paso)
    assert rec.MOVER == ("giro", "zoom", "elevacion") == tuple(hi.MoverEntrada.model_fields)
    assert (rec.ELEVACION, rec.ZOOM, rec.GIRO, rec.MAX_LISTA) == ((8, 85), (0.3, 3), (-360, 360), 8)
    # El navegador: mando.js, el puente y visual.js
    mando, puente = MANDO_JS.read_text(encoding="utf-8"), PUENTE_JS.read_text(encoding="utf-8")
    visual = (RAIZ / "web" / "js" / "propuesta" / "visual.js").read_text(encoding="utf-8")
    for nombre, js in (("mando.js", mando), ("el puente", puente)):
        assert _visual_js(js, "VISUAL") == [*orden, "tema"], nombre
        assert _visual_js(js, "VISUAL_INICIAL") == orden, nombre
        assert _visual_js(js, "MOVER") == list(rec.MOVER), nombre
        assert "const MAX_LISTA = 8;" in js, nombre
    assert _visual_js(visual, "INICIAL") == orden
    # Lo que arma el servidor trae las catorce partes en ese orden (el puente las copia con sus mismas claves)
    _, r = _armar(entrada=PLAN)
    assert all(list(e["visual"]) == orden for e in r.acciones[0]["recorrido"]["escenas"])
    assert rec.visual_inicial() == inicial and rec.visual_inicial()["sin"] is not rec.VISUAL_INICIAL["sin"]


def test_lo_que_se_pinta_es_texto_y_la_voz_solo_vive_en_el_panel():
    for f in (REPRODUCTOR_JS, VOZ_JS, TARJETA_JS):
        t = f.read_text(encoding="utf-8")
        assert "innerHTML" not in t and "insertAdjacentHTML" not in t and "eval(" not in t, f.name
    # La síntesis de voz solo en voz.js (la presentación pública no habla)
    for f in [*(RAIZ / "web" / "js").rglob("*.js"), *JS.rglob("*.js")]:
        if f != VOZ_JS:
            assert "speechSynthesis" not in f.read_text(encoding="utf-8"), f
    vista = (JS / "vistas" / "presentacion.js").read_text(encoding="utf-8")
    assert "crearReproductor({" in vista and "crearVoz()" in vista and "/api/pantalla/progreso" in vista
    agente = (JS / "agente.js").read_text(encoding="utf-8")
    assert "else if (a.tipo === 'recorrido') tarjetaRecorrido(a);" in agente and "pausaPorMensaje();" in agente
    ci = (RAIZ / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "speechSynthesis" in ci


# ───────────────────────────── Con Node ─────────────────────────────

NODE_REPRODUCTOR = r"""
const { crearReproductor, lecturaMs, PREVIA_MS } = await import(process.argv[2]);
function relojFalso() {
  let t = 0, id = 0; const cola = new Map();
  return { ahora: () => t, programar(f, ms) { const h = ++id; cola.set(h, { f, en: t + ms }); return h; }, cancelar(h) { cola.delete(h); },
    async avanzar(ms) { const fin = t + ms; for (;;) { await new Promise((r) => setImmediate(r)); let p = null;
      for (const [h, x] of cola) if (x.en <= fin && (!p || x.en < p[1].en)) p = [h, x]; if (!p) break; cola.delete(p[0]); t = p[1].en; p[1].f(); }
      t = fin; for (let i = 0; i < 5; i++) await new Promise((r) => setImmediate(r)); } };
}
const V = { enfoque: null, camara: 'paso', rumbo: null, elevacion: null, zoom: null, mirar: null, girar: false, comparar: 'proyecto',
  detalle: null, inmersion: null, mostrar: [], ocultar: [], aislar: null, sin: [] };
const esc = (paso, frases) => ({ capitulo: 'salud', paso, panel: true, visual: V, resaltar: null, mover: null, animar: false, frases, sostener_ms: 1300 });
const R = { id: 'abcdef123456', titulo: 'Prueba', cierre: { puntos: ['Uno', 'Dos'] },
  escenas: [esc(1, ['Frase uno.', 'Frase dos.']), esc(2, ['Frase tres.']), esc(3, ['Frase cuatro.'])] };
const out = {};
const nombre = (o) => o.orden + (o.orden === 'escena' ? ':' + o.n : o.frase !== undefined ? ':f' + o.frase
  : o.pausa !== undefined ? ':p' + o.pausa : o.puntos !== undefined ? ':' + (o.puntos ? 'resumen' : 'preguntas') : '');
function armar({ respuesta = () => ({ ok: true }), voz } = {}) {
  const reloj = relojFalso(), ordenes = [], avances = [];
  const rep = crearReproductor({ reloj, ...(voz ? { voz } : {}), orden: async (o) => { ordenes.push(nombre(o)); return respuesta(o); },
    avisar: (p) => avances.push(`${p.n}/${p.fase}${p.frase ? ':' + p.frase : ''}${p.motivo ? '!' + p.motivo : ''}${p.aviso ? '?' + p.aviso : ''}`) });
  return { reloj, ordenes, avances, rep };
}

// 1. Sin voz, de punta a punta: escena, frases con su lectura, sostener, cierre y fin
{
  const { reloj, ordenes, avances, rep } = armar();
  const primera = rep.iniciar(R);
  await reloj.avanzar(10);
  out.primera = await primera;
  await reloj.avanzar(120000);
  out.completo = { ordenes, avances, estado: rep.estado(), activo: rep.activo() };
}
// 2. Pausa (repite la frase al seguir), siguiente, la persona movió la imagen (vuelve la escena), detener
{
  const { reloj, ordenes, avances, rep } = armar();
  rep.iniciar(R);
  await reloj.avanzar(4000);
  rep.pausar('boton');
  const enPausa = ordenes.length;
  await reloj.avanzar(30000);
  out.pausa_quieta = ordenes.length === enPausa + 1 && rep.estado().fase === 'pausa';
  rep.continuar();
  await reloj.avanzar(100);
  rep.siguiente();
  await reloj.avanzar(100);
  out.siguiente = rep.estado().n;
  rep.alPersona();
  await reloj.avanzar(100);
  rep.continuar();
  await reloj.avanzar(100);
  out.persona = ordenes.slice(-4);
  const d = rep.detener('boton');
  await reloj.avanzar(10);
  out.detenido = { ok: await d, estado: rep.estado().fase, ultima: ordenes.at(-1), avance: avances.at(-1), activo: rep.activo() };
}
// 3. Una escena que falla se salta; dos seguidas detienen; sin respuesta, también
{
  let k = 0;
  const { reloj, avances, rep } = armar({ respuesta: (o) => (o.orden === 'escena' && ++k === 1 ? { ok: false, error: 'x' } : { ok: true }) });
  rep.iniciar(R);
  await reloj.avanzar(3000);
  out.una_falla = avances.slice(0, 3);
  const b = armar({ respuesta: (o) => (o.orden === 'escena' ? { ok: false } : { ok: true }) });
  b.rep.iniciar(R);
  await b.reloj.avanzar(1000);
  out.dos_fallas = b.avances.at(-1);
  const c = armar({ respuesta: (o) => (o.orden === 'escena' ? { ok: false, sinRespuesta: true } : { ok: true }) });
  c.rep.iniciar(R);
  await c.reloj.avanzar(1000);
  out.sin_respuesta = c.avances.at(-1);
}
// 4. Con voz: la frase se ilumina cuando empieza a sonar; si la voz falla, la lectura y el aviso; la pausa suave entra
// al terminar la frase
{
  const dichas = [];
  let modo = 'bien';
  const reloj0 = relojFalso();
  const voz = { estado: () => 'activa', callar: () => { if (voz.cortar) voz.cortar('cortada'); },
    decir: (t, { alEmpezar } = {}) => new Promise((ok) => {
      voz.cortar = ok;
      if (modo === 'falla') { ok('fallo'); return; }
      setTimeout(() => { dichas.push(t); alEmpezar?.(); setTimeout(() => ok('dicha'), 5); }, 5);
    }) };
  const { reloj, ordenes, avances, rep } = armar({ voz });
  rep.iniciar(R);
  await reloj.avanzar(400);
  for (let i = 0; i < 20; i++) await new Promise((r) => setTimeout(r, 5));
  out.voz = { dichas: dichas.slice(), ordenes: ordenes.slice() };
  rep.pausar('mensaje', { suave: true });
  for (let i = 0; i < 20; i++) await new Promise((r) => setTimeout(r, 5));
  await reloj.avanzar(10);
  out.suave = rep.estado().fase;
  modo = 'falla';
  rep.continuar();
  rep.siguiente();
  await reloj.avanzar(500);
  for (let i = 0; i < 10; i++) await new Promise((r) => setTimeout(r, 5));
  out.voz_falla = avances.filter((x) => x.includes('?voz')).length >= 1;
  out.lectura = [lecturaMs('x'), lecturaMs('x'.repeat(400))];
}
// 5. El plan que arma el servidor, de punta a punta y con la espera de un plan nuevo: cada orden `escena` lleva lo que
// durará su narración (`ms`), el viaje de la cámara y la animación de esa escena, y no espera a que la imagen se asiente
{
  const plan = JSON.parse(await (await import('node:fs/promises')).readFile(process.argv[3], 'utf8'));
  const reloj = relojFalso(), escenas = [], fases = [];
  let fin = null;
  const rep = crearReproductor({ reloj,
    orden: async (o) => { if (o.orden === 'escena') escenas.push({ n: o.n, de: o.de, t: reloj.ahora(), ms: o.ms, mover: o.mover, animar: o.animar, visual: o.visual, claves: Object.keys(o).sort() }); return { ok: true }; },
    avisar: (p) => { if (!fases.length || fases.at(-1) !== `${p.n}/${p.fase}`) fases.push(`${p.n}/${p.fase}`); if (p.fase === 'fin') fin = reloj.ahora(); } });
  rep.iniciar(plan, { previa: PREVIA_MS });
  await reloj.avanzar(1000);
  out.en_previa = [rep.estado().fase, escenas.length];
  await reloj.avanzar(400000);
  out.plan = { escenas, fin, fases: fases.slice(0, 4), previa: PREVIA_MS };
}
console.log(JSON.stringify(out));
"""


@requiere_node
def test_el_reproductor_con_un_reloj_falso(tmp_path):
    plan = _armar(entrada=PLAN)[1].acciones[0]["recorrido"]
    (tmp_path / "plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "rep.mjs").write_text(NODE_REPRODUCTOR, encoding="utf-8")
    p = subprocess.run(["node", str(tmp_path / "rep.mjs"), REPRODUCTOR_JS.as_uri(), str(tmp_path / "plan.json")],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    r = json.loads(p.stdout.strip().splitlines()[-1])
    assert r["primera"] is True
    c = r["completo"]
    assert c["ordenes"] == ["escena:1", "narracion:f0", "narracion:f1", "escena:2", "narracion:f0", "escena:3",
                            "narracion:f0", "cierre:resumen", "cierre:preguntas", "quitar_explicacion"], c
    assert c["avances"][0] == "1/preparando" and c["avances"][-2:] == ["3/cierre", "3/fin"]
    assert "1/narrando:1" in c["avances"] and "2/sosteniendo" in c["avances"]
    assert c["estado"]["fase"] == "fin" and c["activo"] is False
    assert r["pausa_quieta"] is True and r["siguiente"] == 2
    assert r["persona"][-1] == "escena:2"   # la persona movió la imagen: al seguir, la escena vuelve
    assert r["detenido"] == {"ok": True, "estado": "detenido", "ultima": "quitar_explicacion", "avance": "2/detenido!boton",
                             "activo": False}
    assert r["una_falla"][:2] == ["1/preparando", "1/preparando!escena_fallida"] and r["una_falla"][2] == "2/preparando"
    assert r["dos_fallas"] == "2/error!escena_fallida" and r["sin_respuesta"] == "1/error!sin_respuesta"
    assert r["voz"]["dichas"][:1] == ["Frase uno."] and r["voz"]["ordenes"][:2] == ["escena:1", "narracion:f0"]
    assert r["suave"] == "pausa" and r["voz_falla"] is True and r["lectura"] == [3200, 16000]
    # El plan del servidor: espera PREVIA_MS (en «preparando», sin haber mandado nada) y después cada escena sale con
    # su `ms` (lo mismo que calcula el servidor), su `mover` y su `animar`, y con lo visual completo
    x = r["plan"]
    assert r["en_previa"] == ["preparando", 0] and x["previa"] == rec.PREVIA_MS and x["fases"][:2] == ["1/preparando", "1/narrando"]
    assert [e["n"] for e in x["escenas"]] == list(range(1, 9)) and x["escenas"][0]["t"] == rec.PREVIA_MS
    assert [e["ms"] for e in x["escenas"]] == [rec.narracion_ms(e["frases"]) for e in plan["escenas"]]
    assert [e["mover"] for e in x["escenas"]] == [e["mover"] for e in plan["escenas"]]
    assert [e["animar"] for e in x["escenas"]] == [e["animar"] for e in plan["escenas"]]
    assert [e["visual"] for e in x["escenas"]] == [e["visual"] for e in plan["escenas"]]
    assert x["escenas"][0]["claves"] == sorted(["orden", "rid", "n", "de", "titulo", "capitulo", "paso", "panel", "visual",
                                                "resaltar", "mover", "animar", "simular", "frases", "voz", "ms"])
    # Y dura lo que el servidor estima: sin lo que se le suma por el cambio de paso y la carga del atlas (aquí la
    # presentación responde en el acto) ni el margen del final, la cuenta es exacta
    corrido = rec.PREVIA_MS + sum(rec.RESPIRO_MS + rec.narracion_ms(e["frases"]) + e["sostener_ms"] for e in plan["escenas"]) \
        + rec.lectura_ms("En resumen. " + ". ".join(plan["cierre"]["puntos"])) + rec.CIERRE_SOSTENER_MS + rec.PREGUNTAS_MS
    assert abs(x["fin"] - corrido) <= 50, (x["fin"], corrido)
    estimado = rec.duracion_ms(plan, G)
    asientos = rec.ASIENTO_MS["capitulo"] + rec.ASIENTO_MS["paso"] + rec.ASIENTO_ATLAS_MS   # un capítulo, un paso, un modelo
    assert estimado == corrido + asientos + rec.FIN_MS


NODE_VOZ = r"""
const V = await import(process.argv[2]);
const out = {};
out.dice = ['3.369,6 m² en 4 pisos', 'NSR-10 y Res. 1633', '24 h y 47 %', '2028–2031', 'La E.S.E. tiene REPS', '15 m (prediseño)']
  .map(V.paraDecir);
out.partes = V.partes('a'.repeat(90) + ', ' + 'b'.repeat(90)).map((x) => x.length);
out.elige = V.elegirVoz([{ lang: 'en-US', name: 'A', localService: true }, { lang: 'es-ES', name: 'B', localService: true },
  { lang: 'es-MX', name: 'C', localService: true }, { lang: 'es-CO', name: 'D', localService: false }]).name;
out.sin_es = V.elegirVoz([{ lang: 'en-US', name: 'A' }]);
// Una síntesis falsa
const habladas = [];
class Locucion { constructor(t) { this.text = t; } }
const sintesis = { voces: [{ lang: 'es-CO', name: 'Colombia', localService: true }], getVoices() { return this.voces; },
  addEventListener() {}, cancel() { const u = this.actual; this.actual = null; u?.onerror?.({ error: 'interrupted' }); },
  speak(u) { if (!u.text) return; habladas.push(u.text); this.actual = u; setTimeout(() => { u.onstart?.(); if (this.modo !== 'colgada') setTimeout(() => { if (this.actual === u) { this.actual = null; u.onend?.(); } }, 5); }, 2); } };
const oyentes = {};
const ventana = { speechSynthesis: sintesis, SpeechSynthesisUtterance: Locucion, addEventListener: (n, f) => { oyentes[n] = f; } };
const almacen = { d: {}, getItem(k) { return this.d[k] ?? null; }, setItem(k, v) { this.d[k] = v; } };
const voz = V.crearVoz({ ventana, almacen });
out.inicial = voz.estado();
// con la preferencia guardada en apagada, se respeta
out.guardada_apagada = V.crearVoz({ ventana, almacen: { getItem: () => '0', setItem() {} } }).estado();
out.callada = await voz.decir('Nada');
voz.encender();
out.encendida = [voz.estado(), almacen.d.yj_voz];
let empezo = 0;
out.dicha = await voz.decir('Hola, 24 h', { alEmpezar: () => empezo++ });
out.empezo = empezo;
out.habladas = habladas.slice();
const p = voz.decir('Una frase larga');
setTimeout(() => voz.callar(), 1);
out.cortada = await p;
// otra ventana con la preferencia guardada: el primer gesto la activa
const voz2 = V.crearVoz({ ventana, almacen });
out.sin_activar = voz2.estado();
oyentes.pointerdown();
out.tras_gesto = voz2.estado();
// sin síntesis, o con el almacén bloqueado, no se rompe
out.sin_sintesis = V.crearVoz({ ventana: {}, almacen }).estado();
const roto = { getItem() { throw new Error('x'); }, setItem() { throw new Error('x'); } };
const voz3 = V.crearVoz({ ventana, almacen: roto });
voz3.encender();
out.almacen_roto = voz3.estado();
voz3.apagar();
out.apagada = voz3.estado();
console.log(JSON.stringify(out));
"""


@requiere_node
def test_la_voz_con_una_sintesis_falsa(tmp_path):
    (tmp_path / "voz.mjs").write_text(NODE_VOZ, encoding="utf-8")
    p = subprocess.run(["node", str(tmp_path / "voz.mjs"), VOZ_JS.as_uri()], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    r = json.loads(p.stdout.strip().splitlines()[-1])
    assert r["dice"] == ["3.369,6 metros cuadrados en 4 pisos", "ene ese erre diez y Resolución 1633",
                         "24 horas y 47 por ciento", "2028 a 2031", "La e ese e tiene reps", "15 metros (prediseño)"]
    assert len(r["partes"]) == 2 and all(n <= 160 for n in r["partes"])
    assert r["elige"] == "C" and r["sin_es"] is None   # la local más cercana a es-CO; la remota solo si no hay local
    # encendida por omisión (sin preferencia guardada), pero hace falta un gesto en esa ventana: mientras tanto no habla
    assert r["inicial"] == "sin_activar" and r["callada"] == "fallo" and r["guardada_apagada"] == "apagada"
    assert r["encendida"] == ["activa", "1"] and r["dicha"] == "dicha" and r["empezo"] == 1
    assert r["habladas"] == ["Hola, 24 horas"] and r["cortada"] == "cortada"
    assert r["sin_activar"] == "sin_activar" and r["tras_gesto"] == "activa"
    assert r["sin_sintesis"] == "sin_voces" and r["almacen_roto"] == "activa" and r["apagada"] == "apagada"


NODE_PUENTE = r"""
globalThis.document = { querySelector: () => null, documentElement: {} };
globalThis.MutationObserver = class { observe() {} };
globalThis.window = globalThis;
globalThis.addEventListener ||= () => {};
globalThis.location = { pathname: '/', origin: 'https://panel.example' };
const P = await import(process.argv[2]);
const T = await import(process.argv[3]);
const { recorrido, tarjeta, colapso, plan, tarjeta_plan, visuales, pantallas } = JSON.parse(await (await import('node:fs/promises')).readFile(process.argv[4], 'utf8'));
const out = {};
const copia = (x) => JSON.parse(JSON.stringify(x));
out.valido = JSON.stringify(P.recorridoValido(recorrido)) === JSON.stringify(recorrido);
const variantes = {
  plata: (r) => { r.escenas[0].frases[0] = 'Cuesta $5.000'; },
  extra: (r) => { r.escenas[0].otra = 1; },
  muchas: (r) => { r.escenas = Array(13).fill(r.escenas[0]); },
  mover: (r) => { r.escenas[0].mover = { giro: 400 }; },
  mover_vacio: (r) => { r.escenas[0].mover = {}; },
  animar: (r) => { r.escenas[0].animar = 'si'; },
  elevacion: (r) => { r.escenas[0].visual.elevacion = 90; },
  zoom: (r) => { r.escenas[0].visual.zoom = 3.5; },
  sin_forma: (r) => { r.escenas[0].visual.sin = ['torre']; },
  repetida: (r) => { r.escenas[0].visual.ocultar = ['torre', 'torre']; },
  aislar: (r) => { r.escenas[0].visual.aislar = 'Torre Nueva'; },
  nueve_piezas: (r) => { r.escenas[0].visual.mostrar = 'abcdefghi'.split(''); },
  resaltar: (r) => { r.escenas[0].resaltar = { tipo: 'cifra', n: 13 }; },
  larga: (r) => { r.escenas[0].frases = ['x'.repeat(110), 'y'.repeat(110)]; },
  visual: (r) => { r.escenas[0].visual.camara = 'drone'; },
  id: (r) => { r.id = 'ABC'; },
  telefono: (r) => { r.cierre = { puntos: ['Llame al 300 123 4567'] }; },
  sostener: (r) => { r.escenas[0].sostener_ms = 9000; },
};
out.malos = Object.fromEntries(Object.entries(variantes).map(([k, f]) => { const r = copia(recorrido); f(r); return [k, P.recorridoValido(r)]; }));
const a = (x) => P.accionPresentacion({ tipo: 'presentacion', ...x });
out.acciones = [
  !!a({ op: 'recorrido', recorrido }), !!a({ op: 'recorrido', recorrido, desde: 2 }), a({ op: 'recorrido', recorrido, desde: 9 }),
  a({ op: 'control_recorrido', rid: recorrido.id, accion: 'pausar', suave: true }), a({ op: 'control_recorrido', rid: recorrido.id, accion: 'siguiente', suave: true }),
  a({ op: 'control_recorrido', rid: recorrido.id, accion: 'reproducir' }), a({ op: 'preparando', activar: true }),
  a({ op: 'preparando' }), a({ op: 'ir', capitulo: 'salud', rid: recorrido.id }),
  // el detener del servidor cuando el asistente mostró otra cosa: el motivo, solo ese y solo con detener
  a(colapso), a({ ...colapso, accion: 'pausar' }), a({ ...colapso, motivo: 'boton' }),
];
const pr = { rid: recorrido.id, n: 2, de: 5, fase: 'narrando', frase: 1, voz: 'activa', t_ms: 10 };
out.progreso = [P.progresoValido(pr), P.progresoValido({ ...pr, n: 6 }), P.progresoValido({ ...pr, fase: 'x' }),
  P.progresoValido({ ...pr, extra: 1 }), P.progresoValido({ ...pr, motivo: 'persona', aviso: 'atlas' })];
const base = { v: 3, capitulo: 'salud', paso: 4, explicacion: null, panel: true, indice: false, fichas: false, completa: false, orden_completa: 0 };
const e = P.estadoDePantalla({ ...base, recorrido: { ...recorrido, edad_s: 4 }, control_recorrido: { rid: recorrido.id, accion: 'pausar', n: 2 },
  progreso: { rid: recorrido.id, n: 2, de: 5, fase: 'pausa', hace_s: 1 } });
out.pantalla = [e.recorrido?.edad_s, e.control_recorrido, e.progreso];
out.pantalla_mala = P.estadoDePantalla({ ...base, recorrido: { ...recorrido, escenas: [], edad_s: 1 } })?.recorrido;
out.estado = P.estadoValido({ capitulo: 'salud', paso: 2, total: 10, por: 'persona', recorrido: { rid: recorrido.id, n: 1, de: 5 } });
out.tarjeta_ok = !!T.tarjetaValida(tarjeta);
out.tarjeta_mala = [T.tarjetaValida({ ...tarjeta, destino: 'otra' }), T.tarjetaValida({ ...tarjeta, escenas: [{ ...tarjeta.escenas[0], hace: ['volar'] }] }),
  T.tarjetaValida({ ...tarjeta, titulo: 'a\u0000b' }), T.tarjetaValida({ ...tarjeta, extra: 1 })];
out.duracion = [T.duracion(45000), T.duracion(112000), T.duracion(120000)];
// El plan guiado, con lo que de verdad arma el servidor: el recorrido con `mover`, `animar` y las partes nuevas de lo
// visual pasa por el puente tal cual; doce escenas caben; la tarjeta con los chips nuevos; la acción `visual` con las
// claves nuevas y sus acciones; y el estado de la pantalla en off, con el movimiento que la pantalla hace una vez
out.plan_valido = JSON.stringify(P.recorridoValido(plan)) === JSON.stringify(plan);
out.doce = P.recorridoValido({ ...plan, escenas: Array(12).fill(plan.escenas[0]) })?.escenas.length;
out.tarjeta_plan = T.tarjetaValida(tarjeta_plan)?.escenas.map((e) => e.hace);
out.visuales = visuales.map((x) => JSON.stringify(P.accionPresentacion(x)) === JSON.stringify(x));
out.pantallas = pantallas.map((x) => { const e = P.estadoDePantalla(x); return e && [e.aislar, e.sin, e.elevacion, e.mover, e.animar]; });
out.hacia = [P.ordenesHacia(P.estadoDePantalla(pantallas[0]), P.estadoDePantalla(pantallas[1])),
  P.ordenesHacia(P.estadoDePantalla(pantallas[1]), P.estadoDePantalla(pantallas[2]))];
out.parcial = P.progresoValido({ ...pr, aviso: 'parcial' })?.aviso;
console.log(JSON.stringify(out));
"""


@requiere_node
def test_el_puente_y_la_tarjeta_validan_lo_que_arma_el_servidor(tmp_path):
    db, r = _armar()
    colapso = _hacer(db, 7, {"op": "visual", "camara": "oblicua"}, por="asistente").acciones[0]
    _, plan = _armar(entrada=PLAN)
    # La op `visual` con lo nuevo, a la pestaña (la acción) y a la pantalla en off (el estado que recibe)
    db2 = _Base()
    _hacer(db2, 9, {"op": "ir", "capitulo": "salud", "paso": "torre"}, por="asistente")
    visuales = [_hacer(db2, 9, x, por="asistente").acciones[-1] for x in (
        {"op": "visual", "capitulo": "salud", "aislar": "torre", "sin": ["torre.cubierta"], "elevacion": 60, "zoom": 1.5},
        {"op": "visual", "capitulo": "salud", "mover": {"giro": 90, "zoom": 2}, "animar": True},
        {"op": "visual", "capitulo": "salud", "mirar": "hospital_hoy", "ocultar": ["telesalud"], "aislar": "nada", "sin": []})]

    def en_off():
        d = db2.pantallas.find_one({"_id": 9})
        return pantalla.para_pantalla(pantalla.estado(d, G), d, G)
    pantallas = []
    for x in ({"op": "visual", "aislar": "torre", "sin": ["torre.cubierta"], "elevacion": 60},
              {"op": "visual", "mover": {"giro": 90, "zoom": 2}, "animar": True}, {"op": "visual", "girar": True}):
        _hacer(db2, 9, x, por="mcp")
        pantallas.append(en_off())
    datos = {"recorrido": r.acciones[0]["recorrido"], "tarjeta": r.acciones[1], "colapso": colapso,
             "plan": plan.acciones[0]["recorrido"], "tarjeta_plan": plan.acciones[1], "visuales": visuales,
             "pantallas": pantallas}
    (tmp_path / "datos.json").write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "puente.mjs").write_text(NODE_PUENTE, encoding="utf-8")
    p = subprocess.run(["node", str(tmp_path / "puente.mjs"), PUENTE_JS.as_uri(), TARJETA_JS.as_uri(),
                        str(tmp_path / "datos.json")], capture_output=True, text=True, timeout=60, cwd=ADMIN)
    assert p.returncode == 0, p.stderr
    o = json.loads(p.stdout.strip().splitlines()[-1])
    assert o["valido"] is True
    assert o["malos"] == {k: None for k in o["malos"]}
    rid = datos["recorrido"]["id"]
    assert o["acciones"] == [True, True, None,
                             {"tipo": "presentacion", "op": "control_recorrido", "rid": rid, "accion": "pausar", "suave": True},
                             None, None, {"tipo": "presentacion", "op": "preparando", "activar": True}, None, None,
                             colapso, None, None]
    assert colapso["motivo"] == "otra_orden" and colapso["rid"] == rid
    assert o["progreso"][0] == {"rid": rid, "n": 2, "de": 5, "fase": "narrando", "frase": 1, "voz": "activa", "t_ms": 10}
    assert o["progreso"][1:4] == [None, None, None] and o["progreso"][4]["motivo"] == "persona"
    assert o["pantalla"] == [4, {"rid": rid, "accion": "pausar", "n": 2}, {"rid": rid, "n": 2, "de": 5, "fase": "pausa", "hace_s": 1}]
    assert o["pantalla_mala"] is None
    assert o["estado"]["por"] == "persona" and o["estado"]["recorrido"] == {"rid": rid, "n": 1, "de": 5}
    assert o["tarjeta_ok"] is True and o["tarjeta_mala"] == [None, None, None, None]
    assert o["duracion"] == ["45 s", "1 min 52 s", "2 min"]
    # El plan guiado, de un lado al otro sin perder nada
    assert o["plan_valido"] is True and o["doce"] == 12 and o["parcial"] == "parcial"
    assert o["tarjeta_plan"] == [e["hace"] for e in plan.acciones[1]["escenas"]]
    assert visuales[0] == {"tipo": "presentacion", "op": "visual", "elevacion": 60, "zoom": 1.5, "aislar": "torre",
                           "sin": ["torre.cubierta"]}
    assert visuales[1] == {"tipo": "presentacion", "op": "visual", "mover": {"giro": 90, "zoom": 2}, "animar": True}
    assert visuales[2] == {"tipo": "presentacion", "op": "visual", "mirar": "hospital_hoy", "ocultar": ["telesalud"],
                           "aislar": None, "sin": []}
    assert o["visuales"] == [True, True, True]
    # La pantalla en off recibe lo visual y, una vez, el movimiento y la animación de la última orden `visual`: la
    # siguiente orden los deja en nada (no son estado)
    assert o["pantallas"] == [["torre", ["torre.cubierta"], 60, None, False],
                              ["torre", ["torre.cubierta"], 60, {"giro": 90, "zoom": 2}, True],
                              ["torre", ["torre.cubierta"], 60, None, False]]
    assert o["hacia"] == [[{"orden": "visual", "mover": {"giro": 90, "zoom": 2}, "animar": True}],
                          [{"orden": "visual", "girar": True}]]
