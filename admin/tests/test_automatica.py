"""La presentación automática (app/automatica.py y la clave `auto` de app/pantalla.py): la pantalla en off recorre sola
toda la presentación técnica, un plan por capítulo con una frase muy resumida por paso; un plan del asistente la
interrumpe y, cuando termina, sigue donde iba.

Sin MongoDB ni modelo: los planes salen del guion real, el estado vive en la base en memoria de test_pantalla_mcp.py
(`_Base`) y las rutas de app/api/pantalla.py se llaman como funciones (con la base y la persona en la mano). Solo datos
inventados: la presentación es pública y la pantalla no guarda datos de personas."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app import acceso, automatica, pantalla
from app import recorrido as rec
from app.agente import bucle, sistema
from app.agente import guion as guion_presentacion
from app.agente.herramientas import interfaz as hi
from app.agente.herramientas.base import ErrorHerramienta
from app.api import mcp
from app.api import pantalla as api
from app.proyectable import texto_proyectable
from test_pantalla_mcp import _Base

G = guion_presentacion.cargar()
UID = 7
QUIEN = acceso.Quien(uid=UID, usuario="c7", nombre="Coordinadora de prueba", rol="coordinador",
                     permisos=acceso.PERMISOS["coordinador"])
PORTADA, SALUD, ULTIMO = G.capitulos[0], G.capitulos[G.por_id("salud")], G.capitulos[-1]
TORRE = {"op": "recorrido", "titulo": "La torre del hospital", "pasos": [
    {"capitulo": "salud", "paso": "torre", "camara": "oblicua", "dice": "Aquí va la torre nueva."},
    {"aislar": "torre", "dice": "Son cuatro pisos."},
    {"detalle": "torre", "dice": "Y esta es su ficha."}], "cierre": {"puntos": ["Cuatro pisos", "Sigue atendiendo"]}}


def _hacer(db, entrada, por="asistente"):
    return asyncio.run(hi.presentacion_en_pantalla(db, UID, hi.PresentacionEntrada.model_validate(entrada), por))


def _doc(db):
    return db.pantallas.find_one({"_id": UID})


def _auto(db):
    return pantalla.auto_de(_doc(db), G)


def _abierta() -> _Base:
    """Una base con una pantalla en off abierta (acaba de preguntar por su estado)."""
    db = _Base()
    pantalla.marcar_vista(db, UID)
    return db


def _avance(db, fase, n=1, **extra) -> bool:
    """Un avance del plan guardado, como lo manda la pantalla que lo narra."""
    r = _doc(db)["recorrido"]
    return pantalla.guardar_progreso(db, UID, {"rid": r["id"], "n": n, "de": len(r["escenas"]), "fase": fase,
                                               "frase": 0, "voz": "activa", **extra}, G)


def _narracion(esc) -> str:
    return " ".join(esc["frases"])


# ───────────────────────────── Qué se dice y el plan de cada capítulo ─────────────────────────────

def test_cada_capitulo_da_un_plan_valido_y_muy_resumido():
    total = 0
    for ci, c in enumerate(G.capitulos):
        plan = automatica.plan_del_capitulo(G, ci)
        assert rec.validar(plan, G) == [], c["id"]
        assert plan["titulo"] == c["nombre"] and plan["cierre"] is None and rec.ID.fullmatch(plan["id"])
        # un paso del plan por cada paso del capítulo, en orden: el guion real no tiene ninguno sin nada que decir
        assert [e["paso"] for e in plan["escenas"]] == list(range(1, len(c["pasos"]) + 1))
        suaves = 0
        for e in plan["escenas"]:
            texto = _narracion(e)
            assert texto_proyectable(texto, rec.MAX_NARRACION) == texto, (c["id"], e["paso"])
            # ninguna escrita a mano todavía: la primera frase del paso (o su título), que no pasa del tope con su holgura
            assert 10 <= len(texto) <= automatica.MAX_AUTO + automatica.HOLGURA <= rec.MAX_NARRACION, texto
            assert texto.endswith((".", "!", "?", "…")), texto
            assert (e["capitulo"], e["panel"], e["animar"], e["resaltar"]) == (c["id"], True, True, None)
            assert e["visual"] == rec.VISUAL_INICIAL   # lo visual del paso: nada pedido encima
            if c["pasos"][e["paso"] - 1]["tipo"] == "inmersion":
                assert e["mover"] is None and e["sostener_ms"] == rec.SOSTENER_MIRAR_MS   # dentro de un modelo del atlas
            else:   # el movimiento suave del plan guiado, alternando el sentido
                assert e["mover"] == rec.mover_suave(suaves) and (e["mover"]["giro"] > 0) == (suaves % 2 == 0)
                assert e["mover"]["zoom"] == 1.06 and abs(e["mover"]["giro"]) in rec.GIROS_SUAVES
                suaves += 1
        assert rec.duracion_ms(plan, G) <= rec.MAX_DURACION_MS
        total += len(plan["escenas"])
    assert total == G.total_pasos()
    # dos planes del mismo capítulo son dos recorridos distintos (cada uno con su id)
    assert automatica.plan_del_capitulo(G, 0)["id"] != automatica.plan_del_capitulo(G, 0)["id"]
    # la vuelta completa: un cuarto de hora o menos, y no menos que decir cada paso en tres segundos
    vuelta = automatica.duracion_de_la_vuelta_ms(G)
    assert 3000 * G.total_pasos() < vuelta < 16 * 60 * 1000


def test_el_plan_puede_empezar_a_mitad_del_capitulo():
    ci = G.por_id("salud")
    plan = automatica.plan_del_capitulo(G, ci, 4)
    assert [e["paso"] for e in plan["escenas"]] == list(range(4, len(SALUD["pasos"]) + 1)) and rec.validar(plan, G) == []
    assert automatica.plan_del_capitulo(G, ci, len(SALUD["pasos"]))["escenas"][0]["paso"] == len(SALUD["pasos"])
    assert automatica.plan_del_capitulo(G, ci, len(SALUD["pasos"]) + 1) is None
    assert automatica.plan_del_capitulo(G, ci, 0)["escenas"][0]["paso"] == 1   # un «desde» raro: desde el primero


def test_la_narracion_real_es_la_primera_frase_cortada_donde_termina_una_idea():
    def dice(capitulo, paso):
        ci = G.por_id(capitulo)
        return automatica.narracion_del_paso(G, ci, G.paso(ci, paso))
    # la primera frase, entera
    assert dice("portada", "territorio") == "Yondó queda frente a Barrancabermeja, al otro lado del Magdalena."
    assert dice("aguas", "sistema") == ("El agua sale de los pozos, se potabiliza, sube por impulsión al tanque de "
                                        "compensación y baja por gravedad al casco.")
    # una sigla con puntos o una abreviatura no la parte («Res. 1633 de 2025»)
    assert dice("salud", "torre_pisos").endswith("de la Res. 1633 de 2025.")
    # muy larga: hasta el último punto y coma o dos puntos que quepa, con su punto final
    assert dice("vivienda", "portadilla").endswith("sobre todo de madera o tabla.")
    assert dice("urbanismo", "componentes") == ("Las seis piezas se presentan al nivel central como un solo proyecto por "
                                                "etapas que funcionan solas.")
    # sin dónde cortarla (lo que cabe antes del punto y coma pasa de 180), y el título es solo un rótulo: la primera
    # idea corta del texto (la parte que sigue al punto y coma), con mayúscula y punto
    assert dice("salud", "portadilla") == "Los 5 puestos rurales están abandonados o en mal estado, sin habilitar."
    # la frase que habla de la plata no se narra, y el título es un rótulo: la otra idea de la misma frase
    assert "costo" in SALUD["pasos"][1]["texto"]
    assert dice("salud", "componentes") == ("La telesalud, los EBS, los puestos y las ambulancias llevan la atención a "
                                            "la zona rural, donde vive el 47 % de la población.")
    # un título que ya es una frase se dice tal cual (no se busca otra)
    assert dice("saneamiento", "residuos") == "Menos basura a la celda: ECA y compostaje en el mismo predio."
    # el paso de metas nombra la primera meta de su módulo, resumida (su texto es el mismo en los siete)
    assert dice("salud", "metas") == "La primera meta: sedes rurales de salud habilitadas en el REPS, de 0 a 5 en 2031."
    assert dice("aguas", "metas") == ("La primera meta: horas de servicio al día en la red urbana, de 9 h a 24 h en el "
                                      "sector piloto en 2029 y en todo el casco en 2030.")
    metas = [dice(c["id"], "metas") for c in G.capitulos if any(p["id"] == "metas" for p in c["pasos"])]
    assert len(metas) == 7 and len(set(metas)) == 7 and all(m.startswith("La primera meta") for m in metas)
    assert not any("Cada meta parte" in m or "→" in m or "(" in m for m in metas)
    # si el guion trae una escrita a mano, es esa la que se dice (hoy ninguna: la prueba la cuida cuando se escriba)
    for ci, c in enumerate(G.capitulos):
        for pi, p in enumerate(c["pasos"]):
            if p.get("narracion"):
                assert automatica.narracion_del_paso(G, ci, pi) == p["narracion"], (c["id"], p["id"])


LARGA = ("La planta nueva trata cincuenta litros por segundo con un reactor y un filtro; el agua tratada pasa por una "
         "laguna de pulimento y vuelve al caño más abajo del pueblo, sin bombeo, y los lodos se secan en lechos "
         "cubiertos antes de salir del predio hacia el relleno.")
SOLO_COMAS = ("En el predio van la celda de la primera fase, dos lagunas de lixiviados, la portería con báscula, una "
              "estación de clasificación, una planta de compostaje al norte de la celda, la vía interna, el cerramiento "
              "vivo y la franja de aislamiento que pide la licencia ambiental del sitio.")
DATOS = {
    "portada": {"titulo": "La propuesta"},
    "modulos": [{"id": "agua", "nombre": "Agua", "pasos": [
        {"id": "corto", "tipo": "texto", "titulo": "El agua llega", "texto": "El agua sale del pozo. Luego baja al casco."},
        {"id": "largo", "tipo": "texto", "titulo": "Una planta nueva", "texto": LARGA},
        {"id": "comas", "tipo": "texto", "titulo": "Lo que va en el predio", "texto": SOLO_COMAS},
        {"id": "plata", "tipo": "texto", "titulo": "La planta, primero", "texto": "La planta se lleva el 80 % del presupuesto."},
        {"id": "correo", "tipo": "texto", "titulo": "Escriba a agua@ejemplo.co", "texto": "Escriba a agua@ejemplo.co para saber más."},
        {"id": "mudo", "tipo": "texto", "titulo": "Solo el título", "texto": ""},
        {"id": "a_mano", "tipo": "texto", "titulo": "Con narración", "texto": "Un texto que no se dice."},
        {"id": "a_mano_mala", "tipo": "texto", "titulo": "Con una narración que no pasa", "texto": "Esto sí se dice."}]}],
    "tecnica": {"portada": {"texto": "Cada obra en su sitio. Y lo demás."},
                "narracion": {"portada": {"inicio": "Bienvenidos: esta es la <b>propuesta</b>, obra por obra."},
                              "agua": {"a_mano": "Esta frase la escribió alguien. Y esta también.",
                                       "a_mano_mala": "Llame al 300 123 4567.", "no_existe": "Nadie la dice."},
                              "marte": {"x": "Tampoco."}}}}


def test_la_narracion_escrita_a_mano_la_primera_frase_o_el_titulo():
    derivado = guion_presentacion.derivar(DATOS)
    g = guion_presentacion.Guion.desde(derivado)
    agua = g.por_id("agua")
    pasos = {p["id"]: p for p in g.capitulos[agua]["pasos"]}
    # el mecanismo: `tecnica.narracion[capítulo][paso]` queda en el paso, en texto plano; sin ella, el paso no la trae
    assert g.capitulos[0]["pasos"][0]["narracion"] == "Bienvenidos: esta es la propuesta, obra por obra."
    assert pasos["a_mano"]["narracion"] == "Esta frase la escribió alguien. Y esta también."
    assert "narracion" not in pasos["corto"] and "narracion" not in g.capitulos[-1]["pasos"][0]
    assert "narracion" not in guion_presentacion.derivar({**DATOS, "tecnica": {"narracion": "no es un objeto"}})["capitulos"][1]["pasos"][0]

    def dice(paso):
        return automatica.narracion_del_paso(g, agua, g.paso(agua, paso))
    assert automatica.narracion_del_paso(g, 0, 0) == "Bienvenidos: esta es la propuesta, obra por obra."
    assert dice("a_mano") == "Esta frase la escribió alguien. Y esta también."   # hasta el tope de cualquier narración
    assert dice("a_mano_mala") == "Esto sí se dice."   # la escrita a mano no pasa las reglas: la primera frase del texto
    assert dice("corto") == "El agua sale del pozo."
    assert dice("largo") == "La planta nueva trata cincuenta litros por segundo con un reactor y un filtro."
    assert len(SOLO_COMAS) > automatica.MAX_AUTO + automatica.HOLGURA and dice("comas") == "Lo que va en el predio."
    assert dice("plata") == "La planta, primero."
    assert dice("correo") is None   # ni la frase ni el título se pueden proyectar: ese paso se salta
    assert dice("mudo") == "Solo el título."
    plan = automatica.plan_del_capitulo(g, agua)
    assert rec.validar(plan, g) == [] and [e["paso"] for e in plan["escenas"]] == [1, 2, 3, 4, 6, 7, 8]
    assert plan["escenas"][5]["frases"] == ["Esta frase la escribió alguien.", "Y esta también."]
    # el último capítulo (el cronograma, sin texto) dice su título
    assert _narracion(automatica.plan_del_capitulo(g, len(g) - 1)["escenas"][0]) == "Cronograma de obra."


def test_la_primera_meta_resumida():
    def meta(*metas):
        return automatica.primera_meta({"metas": list(metas)})
    assert meta("Camas de hospitalización: 9 (REPS, 2022) → 15 en la torre (2031)") == \
        "La primera meta: camas de hospitalización, de 9 a 15 en la torre en 2031."
    # de la línea base, solo el dato; una sigla al empezar no pasa a minúscula; sin línea base, solo la meta
    assert meta("PSMV vigente aprobado por Corantioquia: Vencido; aprobado en 2014 (2026) → PSMV nuevo aprobado (2028)") \
        == "La primera meta: PSMV vigente aprobado por Corantioquia, de vencido a PSMV nuevo aprobado en 2028."
    assert meta("Laboratorio clínico: — → propio, 24 horas (2031)") == \
        "La primera meta, laboratorio clínico: propio, 24 horas en 2031."
    # muy larga con la línea base: solo la meta
    larga = "Algo: " + "una línea base muy larga " * 8 + "(2026) → 5 (2031)"
    assert meta(larga) == "La primera meta, algo: 5 en 2031."
    # solo la primera: si no se puede decir (sin meta, de costos, con una «@», sin flecha), nada (se sigue con el texto)
    for mala in ("Ahorro: — → —", "Inversión del módulo: 0 → 5 (2031)", "Escriba a a@b.co: 0 → 1 (2031)",
                 "Sin flecha: 0 (2026)", "X: 1 → 2 → 3", None, 7):
        assert meta(mala, "Camas: 9 (2022) → 15 (2031)") == "", mala
    assert automatica.primera_meta({}) == automatica.primera_meta({"metas": "x"}) == automatica.primera_meta({"metas": []}) == ""


def test_la_frase_corta_de_un_paso_con_titulo_breve():
    corta = automatica.frase_corta
    texto = ("Una frase demasiado larga " * 9 + "para decirla sola; la segunda parte sí cabe y se dice como frase. "
             "Otra frase.")
    assert corta({"texto": texto}) == "La segunda parte sí cabe y se dice como frase."
    # nunca partida dentro de un paréntesis; lo que habla de costos o es muy corto no sirve: la primera cifra
    assert corta({"texto": "Corta. Lleva el 80 % del costo del módulo y se paga en dos años sin falta.",
                  "cifras": [{"v": "3.763 t", "l": "de residuos dispuestos en 2024, unas 10,3 t por día"}]}) == \
        "3.763 t de residuos dispuestos en 2024, unas 10,3 t por día."
    assert corta({"texto": "Solo (una parte; dentro) del paréntesis " + "y sigue " * 30 + "hasta el final."}) == ""
    assert corta({"cifras": [{"v": True, "l": "no es un valor"}, "no es una cifra"]}) == corta({}) == ""
    # en la narración: solo si el título es un rótulo (corto); uno que ya es una frase se dice tal cual
    derivado = guion_presentacion.derivar({**DATOS, "modulos": [{"id": "agua", "nombre": "Agua", "pasos": [
        {"id": "rotulo", "tipo": "texto", "titulo": "Un solo pozo", "texto": SOLO_COMAS + " El pozo da agua a todo el "
                                                                                          "casco urbano, día y noche."},
        {"id": "frase", "tipo": "texto", "titulo": "Lo que va en el predio de la planta, de norte a sur, junto al caño",
         "texto": SOLO_COMAS + " El pozo da agua a todo el casco urbano, día y noche."}]}]})
    g = guion_presentacion.Guion.desde(derivado)
    agua = g.por_id("agua")
    assert automatica.narracion_del_paso(g, agua, 0) == "El pozo da agua a todo el casco urbano, día y noche."
    assert automatica.narracion_del_paso(g, agua, 1) == "Lo que va en el predio de la planta, de norte a sur, junto al caño."


def test_resumir():
    assert automatica.resumir("") == "" and automatica.resumir(None) == "" and automatica.resumir("   ") == ""
    assert automatica.resumir("Una. Dos. Tres.") == "Una."
    justa = "a" * 199 + "."
    assert automatica.resumir(justa + " Otra.") == justa   # hasta el tope y su holgura, entera
    # más larga: el último punto y coma o dos puntos que deje hasta 180; no los de una hora ni dentro de un paréntesis
    larga = "Abre de 4:00 a 13:00 " + "y sigue " * 8 + "(con dos turnos; uno de noche) todo el año; " + "luego cierra " * 12 + "y ya."
    assert automatica.resumir(larga) == "Abre de 4:00 a 13:00 " + "y sigue " * 8 + "(con dos turnos; uno de noche) todo el año."
    assert automatica.resumir("Corta: " + "y sigue " * 30 + "hasta el final.") == ""   # lo que quedaría es muy poco
    assert automatica.resumir(SOLO_COMAS) == ""


def test_la_posicion_sigue_al_capitulo_siguiente_y_da_la_vuelta():
    n = len(PORTADA["pasos"])
    assert automatica.posicion(G, "portada", 1) == ("portada", 1, 0) and automatica.posicion(G, "portada", n) == ("portada", n, 0)
    assert automatica.posicion(G, "portada", n + 1) == (G.capitulos[1]["id"], 1, 0)
    assert automatica.posicion(G, ULTIMO["id"], len(ULTIMO["pasos"]) + 1) == ("portada", 1, 1)
    # lo que no vale (el guion cambió, alguien tocó la base): el primer paso de ese capítulo o de la presentación
    assert automatica.posicion(G, "marte", 4) == ("portada", 1, 0) and automatica.posicion(G, None, None) == ("portada", 1, 0)
    for paso in (0, -3, True, "2", None, 2.0):
        assert automatica.posicion(G, "salud", paso) == ("salud", 1, 0)
    # el plan que sigue: el del capítulo desde ese paso o, si ya no queda nada, el del siguiente
    plan, vueltas = automatica.plan_desde(G, 0, 2)
    assert (plan["titulo"], plan["escenas"][0]["paso"], vueltas) == ("Portada", 2, 0)
    plan, vueltas = automatica.plan_desde(G, len(G) - 1, len(ULTIMO["pasos"]) + 1)
    assert (plan["titulo"], plan["escenas"][0]["paso"], vueltas) == ("Portada", 1, 1)


# ───────────────────────────── Encender, seguir y apagar ─────────────────────────────

def test_iniciar_sin_pantalla_abierta_espera_y_con_pantalla_arma_el_primer_plan():
    db = _Base()
    assert pantalla.auto_de(None, G) is None and pantalla.auto_para_pantalla(None, G) is None
    assert pantalla.auto_para_persona(None, G) == {"activa": False, "capitulo": "portada", "nombre": "Portada", "paso": 1,
                                                   "de": len(PORTADA["pasos"])}
    # Sin pantalla en off abierta: queda encendida, sin plan
    d = pantalla.iniciar_auto(db, UID, G, "panel")
    assert d["auto"] == {"activa": True, "capitulo": "portada", "paso": 1, "rid": None, "vueltas": 0, "fallas": 0}
    assert (d["v"], d["por"]) == (1, "panel") and "recorrido" not in d
    assert _auto(db) == d["auto"] and pantalla.auto_para_pantalla(d, G) == {"activa": True, "capitulo": "portada", "paso": 1}
    # la pantalla se abre y pide el siguiente: ahí empieza
    pantalla.marcar_vista(db, UID)
    plan = pantalla.siguiente_auto(db, UID, G)
    assert plan["titulo"] == "Portada" and plan["auto"] is True and plan["destino"] == "pantalla_off"
    # Con la pantalla abierta: arma y guarda ya el primer plan, del capítulo que se diga
    db = _abierta()
    d = pantalla.iniciar_auto(db, UID, G, "asistente", G.por_id("salud"))
    r = d["recorrido"]
    assert (r["titulo"], r["destino"], r["cerrado"], r["auto"], d["por"]) == ("Salud", "pantalla_off", False, True, "auto")
    assert d["auto"] == {"activa": True, "capitulo": "salud", "paso": 1, "rid": r["id"], "vueltas": 0, "fallas": 0}
    assert d["v"] == 2 and d["progreso"] is None and d["control_recorrido"] is None
    assert len(r["escenas"]) == len(SALUD["pasos"]) and pantalla.recorrido_de(d, G)["auto"] is True
    # la base guardada es su última escena (la que queda al terminar), como con cualquier plan
    assert (d["capitulo"], d["paso"]) == ("salud", len(SALUD["pasos"]))
    # encenderla otra vez la devuelve al comienzo, con otro plan
    d2 = pantalla.iniciar_auto(db, UID, G, "panel")
    assert d2["auto"]["capitulo"] == "portada" and d2["auto"]["rid"] == d2["recorrido"]["id"] != r["id"]
    for por in ("auto", "nadie"):
        with pytest.raises(ValueError):
            pantalla.iniciar_auto(db, UID, G, por)
    # el plan automático solo lo guarda la automática: `guardar_recorrido` no acepta ese origen
    with pytest.raises(ValueError):
        pantalla.guardar_recorrido(db, UID, automatica.plan_del_capitulo(G, 0), "pantalla_off", "auto")


def test_siguiente_solo_cuando_no_suena_un_plan():
    db = _abierta()
    assert pantalla.siguiente_auto(db, UID, G) is None   # nunca se encendió
    pantalla.iniciar_auto(db, UID, G, "panel")
    primero = _doc(db)["recorrido"]["id"]
    assert pantalla.plan_sonando(_doc(db), G) is True
    assert pantalla.siguiente_auto(db, UID, G) is None   # recién armado: la pantalla lo va a narrar
    assert _avance(db, "narrando", 1) and pantalla.siguiente_auto(db, UID, G) is None
    assert _doc(db)["recorrido"]["id"] == primero
    # en pausa no hace nada, por mucho que pase
    assert _avance(db, "pausa", 1, motivo="boton")
    despues = datetime.now(timezone.utc) + timedelta(seconds=pantalla.SIN_NOTICIAS_AUTO_S + 5)
    pantalla.marcar_vista(db, UID)
    assert pantalla.siguiente_auto(db, UID, G) is None
    assert _avance(db, "narrando", 2) and _auto(db)["paso"] == 2
    # sin noticias de su plan (la pantalla se recargó a mitad): lo da por caído y arma otro desde el paso que se decía
    assert pantalla.siguiente_auto(db, UID, G, ahora=despues - timedelta(seconds=10)) is None
    plan = pantalla.siguiente_auto(db, UID, G, ahora=despues)
    assert plan["id"] != primero and plan["titulo"] == "Portada" and plan["escenas"][0]["paso"] == 2
    assert _auto(db)["rid"] == plan["id"]
    # algo cambió entre la lectura y la escritura (llegó un plan o una orden): no pisa nada
    viejo = _doc(db)
    assert pantalla._armar_auto(db, UID, G, viejo, si={"v": viejo["v"] - 1}) is None and _doc(db)["recorrido"]["id"] == plan["id"]
    # apagada, tampoco
    pantalla.detener_auto(db, UID, G, "panel")
    assert pantalla.siguiente_auto(db, UID, G) is None and pantalla.plan_sonando(_doc(db), G) is False


def test_el_avance_mueve_la_posicion_y_fin_pasa_al_capitulo_siguiente():
    db = _abierta()
    pantalla.iniciar_auto(db, UID, G, "panel")
    rid = _doc(db)["recorrido"]["id"]
    v = _doc(db)["v"]
    assert _avance(db, "preparando", 1) and _auto(db)["paso"] == 1
    assert _avance(db, "narrando", 2) and (_auto(db)["capitulo"], _auto(db)["paso"], _auto(db)["rid"]) == ("portada", 2, rid)
    assert _avance(db, "sosteniendo", 2) and _auto(db)["paso"] == 2
    assert _doc(db)["v"] == v   # un avance no sube la versión: la pantalla no tiene nada nuevo que aplicar
    # «¿Preguntas?»: ya se dijo todo el capítulo; si alguien pregunta ahora, después sigue con el capítulo siguiente
    assert _avance(db, "cierre", 2)
    siguiente = G.capitulos[1]
    assert (_auto(db)["capitulo"], _auto(db)["paso"], _auto(db)["rid"], _auto(db)["vueltas"]) == (siguiente["id"], 1, rid, 0)
    assert _avance(db, "pausa", 2, motivo="boton") and _auto(db)["capitulo"] == siguiente["id"]   # en pausa se queda
    assert _avance(db, "fin", 2)
    d = _doc(db)
    assert d["auto"] == {"activa": True, "capitulo": siguiente["id"], "paso": 1, "rid": None, "vueltas": 0, "fallas": 0}
    assert d["recorrido"]["cerrado"] is True and d["v"] == v + 1 and (d["capitulo"], d["paso"]) == ("portada", 2)
    assert not _avance(db, "narrando", 1)   # ya cerrado: la API responde 409
    # la pantalla pide el siguiente: el capítulo que sigue, desde su primer paso
    plan = pantalla.siguiente_auto(db, UID, G)
    assert (plan["titulo"], plan["escenas"][0]["paso"], plan["auto"]) == (siguiente["nombre"], 1, True)
    # Toda la vuelta: capítulo por capítulo y, después del último, otra vez el primero, con una vuelta más
    db = _abierta()
    pantalla.iniciar_auto(db, UID, G, "panel")
    vistos = []
    for _ in range(len(G) + 1):
        r = _doc(db)["recorrido"]
        vistos.append(r["titulo"])
        assert _avance(db, "narrando", len(r["escenas"])) and _avance(db, "fin", len(r["escenas"]))
        assert pantalla.siguiente_auto(db, UID, G)["auto"] is True
    assert vistos == [c["nombre"] for c in G.capitulos] + ["Portada"]
    assert (_auto(db)["capitulo"], _auto(db)["vueltas"]) == (G.capitulos[1]["id"], 1)
    # Sin el guion a la mano el avance guarda el paso que sigue tal cual, y al leerlo es el del capítulo siguiente
    db = _abierta()
    pantalla.iniciar_auto(db, UID, G, "panel", len(G) - 1)
    r = _doc(db)["recorrido"]
    assert pantalla.guardar_progreso(db, UID, {"rid": r["id"], "n": 1, "de": 1, "fase": "fin", "frase": 0, "voz": "apagada"})
    assert _doc(db)["auto"]["paso"] == len(ULTIMO["pasos"]) + 1
    assert (_auto(db)["capitulo"], _auto(db)["paso"], _auto(db)["vueltas"]) == ("portada", 1, 1)
    assert pantalla.siguiente_auto(db, UID, G)["titulo"] == "Portada" and _doc(db)["auto"]["vueltas"] == 1


def test_un_plan_del_asistente_la_interrumpe_y_despues_sigue_donde_iba():
    db = _abierta()
    pantalla.iniciar_auto(db, UID, G, "panel", G.por_id("salud"))
    automatico = _doc(db)["recorrido"]["id"]
    assert _avance(db, "narrando", 4)
    # La persona pregunta y el asistente arma un plan corto: suena en la pantalla en off y suelta al automático
    x = _hacer(db, TORRE)
    d = _doc(db)
    assert d["recorrido"]["titulo"] == "La torre del hospital" and d["recorrido"]["auto"] is False and d["por"] == "asistente"
    assert d["auto"] == {"activa": True, "capitulo": "salud", "paso": 4, "rid": None, "vueltas": 0, "fallas": 0}
    assert [a["tipo"] for a in x.acciones] == ["recorrido"] and x.acciones[0]["destino"] == "pantalla_off"
    assert "sigue sola en Salud, paso 4 de 10" in x.contenido["automatica"]
    # el avance tardío del automático ya no es de nadie, y mientras suena el plan del asistente no se arma otro
    assert pantalla.guardar_progreso(db, UID, {"rid": automatico, "n": 5, "de": len(SALUD["pasos"]), "fase": "narrando",
                                               "frase": 0, "voz": "activa"}, G) is False
    assert pantalla.siguiente_auto(db, UID, G) is None
    assert _avance(db, "narrando", 2) and _avance(db, "cierre", 3)
    assert (_auto(db)["capitulo"], _auto(db)["paso"]) == ("salud", 4)   # el avance de otro plan no mueve su posición
    assert pantalla.siguiente_auto(db, UID, G) is None
    assert _avance(db, "fin", 3) and _auto(db)["rid"] is None
    # Terminó: la pantalla pide el siguiente y retoma en el paso que se estaba diciendo
    plan = pantalla.siguiente_auto(db, UID, G)
    assert plan["titulo"] == "Salud" and [e["paso"] for e in plan["escenas"]] == list(range(4, len(SALUD["pasos"]) + 1))
    assert _auto(db) == {"activa": True, "capitulo": "salud", "paso": 4, "rid": plan["id"], "vueltas": 0, "fallas": 0}
    # Por MCP, igual
    assert _avance(db, "narrando", 2) and _auto(db)["paso"] == 5
    assert _hacer(db, TORRE, por="mcp").acciones == []
    assert (_doc(db)["auto"]["rid"], _auto(db)["paso"], _doc(db)["por"]) == (None, 5, "mcp")
    assert _avance(db, "fin", 3) and pantalla.siguiente_auto(db, UID, G)["escenas"][0]["paso"] == 5
    # Una orden suelta (ir, visual, explicar) también lo cierra: sigue encendida y con su posición
    assert _avance(db, "narrando", 2) and _auto(db)["paso"] == 6
    _hacer(db, {"op": "visual", "camara": "aerea"})
    d = _doc(db)
    assert d["recorrido"]["cerrado"] is True and d["auto"]["activa"] is True and d["auto"]["rid"] is None
    assert (d["capitulo"], d["paso"], d["camara"]) == ("salud", 6, "aerea") and _auto(db)["paso"] == 6
    assert pantalla.siguiente_auto(db, UID, G)["escenas"][0]["paso"] == 6


def test_detener_y_el_control_detener_la_apagan_y_pausar_no():
    db = _abierta()
    assert pantalla.detener_auto(db, UID, G, "panel") is not None and _auto(db) is None   # nunca se encendió: nada
    pantalla.iniciar_auto(db, UID, G, "panel", G.por_id("vivienda"))
    assert _avance(db, "narrando", 3)
    v = _doc(db)["v"]
    # Pausar no la apaga
    res = pantalla.controlar(db, UID, G, "pausar", "panel")
    assert res["doc"]["control_recorrido"]["accion"] == "pausar"
    assert (_auto(db)["activa"], _auto(db)["rid"], _auto(db)["paso"]) == (True, res["recorrido"]["id"], 3)
    assert _avance(db, "pausa", 3, motivo="boton") and pantalla.siguiente_auto(db, UID, G) is None
    # «Reproducir» lo vuelve a empezar y sigue siendo el plan automático
    nuevo = pantalla.controlar(db, UID, G, "reproducir", "asistente")["recorrido"]
    assert nuevo["auto"] is True and nuevo["id"] != res["recorrido"]["id"]
    assert (_auto(db)["rid"], _auto(db)["capitulo"], _auto(db)["paso"]) == (nuevo["id"], "vivienda", 1)
    # Detener: se apaga, su plan se cierra con la escena en curso como base y la posición se queda
    assert _avance(db, "narrando", 2)
    d = pantalla.detener_auto(db, UID, G, "asistente")
    assert d["auto"] == {"activa": False, "capitulo": "vivienda", "paso": 2, "rid": None, "vueltas": 0, "fallas": 0}
    assert d["recorrido"]["cerrado"] is True and (d["capitulo"], d["paso"]) == ("vivienda", 2) and d["v"] > v
    assert pantalla.siguiente_auto(db, UID, G) is None
    assert pantalla.detener_auto(db, UID, G, "panel")["v"] == d["v"]   # ya apagada: nada cambia
    with pytest.raises(ValueError):
        pantalla.detener_auto(db, UID, G, "auto")
    # El control «detener» sobre el plan automático (del asistente, de un agente o del panel) también la apaga
    pantalla.iniciar_auto(db, UID, G, "panel")
    res = pantalla.controlar(db, UID, G, "detener", "mcp")
    assert res["recorrido"]["cerrado"] is True and res["doc"]["auto"]["activa"] is False and res["doc"]["auto"]["rid"] is None
    assert pantalla.siguiente_auto(db, UID, G) is None
    # …pero sobre un plan del asistente no: la automática sigue encendida y después continúa
    pantalla.iniciar_auto(db, UID, G, "panel")
    _hacer(db, TORRE)
    pantalla.controlar(db, UID, G, "detener", "asistente")
    assert _auto(db)["activa"] is True and pantalla.siguiente_auto(db, UID, G)["titulo"] == "Portada"
    # La pantalla lo detiene (una tecla en esa pantalla): se apaga. Un traspaso o un reemplazo, no
    assert _avance(db, "detenido", 1, motivo="reemplazo") and _auto(db)["activa"] is True and _auto(db)["rid"]
    assert _avance(db, "detenido", 1, motivo="tecla")
    assert _doc(db)["auto"]["activa"] is False and _doc(db)["auto"]["rid"] is None and _doc(db)["recorrido"]["cerrado"] is True
    # El botón de esa pantalla, igual
    pantalla.iniciar_auto(db, UID, G, "panel")
    assert _avance(db, "detenido", 1, motivo="boton") and _doc(db)["auto"]["activa"] is False
    assert pantalla.DETIENEN_AUTO == ("tecla", "boton") and set(pantalla.DETIENEN_AUTO) <= set(rec.MOTIVOS)


def test_encenderla_o_apagarla_no_repite_la_simulacion_de_la_ultima_orden():
    """Encender o apagar la automática sube la versión: la simulación (y el viaje de la cámara, la animación) de la última
    orden `visual` queda en nada, o la pantalla en off, que ya la hizo, la haría otra vez con la versión nueva."""
    db = _abierta()
    _hacer(db, {"op": "automatica", "accion": "iniciar"}, por="mcp")
    _hacer(db, {"op": "visual", "inmersion": "torre_sismo", "mover": {"giro": 30},
                "simular": [{"control": "magnitud", "valor": 7.5}, {"control": "calcular"}]}, por="mcp")
    x = api.estado_pantalla(v=None, db=db, quien=QUIEN)   # la pantalla la recibe y la hace
    assert x["simular"] == [{"control": "magnitud", "valor": 7.5}, {"control": "calcular"}] and x["mover"] == {"giro": 30}
    # el botón «Presentación automática» de la pantalla la apaga: la versión nueva ya no trae la simulación
    assert api.presentacion_automatica(api.AutoEntrada(accion="detener"), db=db, quien=QUIEN)["auto"]["activa"] is False
    y = api.estado_pantalla(v=x["v"], db=db, quien=QUIEN)
    assert y["v"] > x["v"] and (y["simular"], y["mover"], y["animar"]) == (None, None, False)
    # encenderla tampoco (su primera escritura, antes de armar el plan: sin pantalla abierta no lo arma, y se ve sola)
    db = _Base()
    _hacer(db, {"op": "ir", "capitulo": "salud", "paso": "torre_sismo"}, por="mcp")
    _hacer(db, {"op": "visual", "simular": [{"control": "calcular"}], "animar": True}, por="mcp")
    assert _doc(db)["simular"] == [{"control": "calcular"}]
    d = pantalla.iniciar_auto(db, UID, G, "panel")
    assert (d["simular"], d["mover"], d["animar"]) == (None, None, False) and _auto(db)["activa"] is True


def test_salir_de_la_vista_en_off_no_la_apaga():
    # La vista en off se desmonta (salir del modo en off, ir a otra vista del panel): detiene su reproductor con
    # «otra_orden». Eso suelta el plan, pero la automática sigue encendida en ese paso y retoma desde ahí
    db = _abierta()
    pantalla.iniciar_auto(db, UID, G, "panel", G.por_id("vivienda"))
    assert _avance(db, "narrando", 2)
    assert _avance(db, "detenido", 2, motivo="otra_orden")
    d = _doc(db)
    assert d["recorrido"]["cerrado"] is True and (d["capitulo"], d["paso"]) == ("vivienda", 2)
    assert _auto(db) == {"activa": True, "capitulo": "vivienda", "paso": 2, "rid": None, "vueltas": 0, "fallas": 0}
    plan = pantalla.siguiente_auto(db, UID, G)
    assert plan["titulo"] == "Vivienda" and plan["escenas"][0]["paso"] == 2
    # cualquier otro motivo que no sea una tecla o un botón de esa pantalla, tampoco
    for motivo in ("sin_respuesta", "persona", None):
        extra = {"motivo": motivo} if motivo else {}
        assert _avance(db, "detenido", 1, **extra) and _auto(db)["activa"] is True, motivo
        assert pantalla.siguiente_auto(db, UID, G) is not None


def test_detener_su_plan_con_la_automatica_encendida_le_dice_al_modelo_que_sigue():
    db = _abierta()
    pantalla.iniciar_auto(db, UID, G, "panel", G.por_id("salud"))
    assert _avance(db, "narrando", 3)
    _hacer(db, TORRE)
    assert _avance(db, "narrando", 1)
    x = _hacer(db, {"op": "control_recorrido", "accion": "detener"})
    assert x.contenido["plan"]["fase"] == "detenido" and _auto(db)["activa"] is True
    assert x.contenido["automatica"] == ("La presentación automática sigue encendida: en unos segundos retoma sola en "
                                         "Salud, paso 3 de 10. Si la persona quiere silencio, apáguela con op "
                                         "automatica (accion detener).")
    # «pausar» no lo dice, ni «detener» con la automática apagada
    _hacer(db, TORRE)
    assert "automatica" not in _hacer(db, {"op": "control_recorrido", "accion": "pausar"}).contenido
    pantalla.detener_auto(db, UID, G, "panel")
    _hacer(db, TORRE)
    assert "automatica" not in _hacer(db, {"op": "control_recorrido", "accion": "detener"}).contenido
    # Sin una pantalla en off abierta (el plan sonó en la pestaña): retoma cuando se abra una
    db = _Base()
    pantalla.iniciar_auto(db, UID, G, "panel")
    _hacer(db, TORRE)
    x = _hacer(db, {"op": "control_recorrido", "accion": "detener"})
    assert "retoma sola cuando se abra una pantalla en off, en Portada, paso 1 de 2" in x.contenido["automatica"]


def test_volver_a_reproducir_la_respuesta_con_la_automatica_encendida():
    db = _abierta()
    pantalla.iniciar_auto(db, UID, G, "panel")
    assert _avance(db, "narrando", 2)
    _hacer(db, TORRE)
    rid = _doc(db)["recorrido"]["id"]
    assert _avance(db, "fin", 3)

    def reproducir(r):
        return api.control_recorrido(api.ControlEntrada(rid=r, accion="reproducir"), db=db, quien=QUIEN)
    # A los 5 s la pantalla pide el siguiente: el plan automático reemplaza al del asistente, que queda guardado
    plan = pantalla.siguiente_auto(db, UID, G)
    assert plan["titulo"] == "Portada" and _doc(db)["recorrido_previo"]["id"] == rid
    # «Volver a reproducir» de su tarjeta lo trae con un id nuevo: interrumpe a la automática, que sigue en su paso
    x = reproducir(rid)
    assert x["titulo"] == "La torre del hospital" and x["id"] != rid and x["cerrado"] is False
    d = _doc(db)
    assert d["recorrido"]["auto"] is False and d["recorrido"]["destino"] == "pantalla_off" and d["por"] == "panel"
    assert _auto(db) == {"activa": True, "capitulo": "portada", "paso": 2, "rid": None, "vueltas": 0, "fallas": 0}
    # el id viejo ya no: la tarjeta sigue al nuevo (y ese, cuando la automática vuelva a seguir, sigue sirviendo)
    with pytest.raises(HTTPException) as e:
        reproducir(rid)
    assert e.value.status_code == 409
    nuevo = x["id"]
    assert _avance(db, "fin", 3) and pantalla.siguiente_auto(db, UID, G) is not None
    assert reproducir(nuevo)["titulo"] == "La torre del hospital"
    # Llega otro plan que no es de la automática: el anterior ya no se puede volver a reproducir
    otro = _doc(db)["recorrido"]["id"]
    _hacer(db, {**TORRE, "titulo": "Otra respuesta"})
    assert _avance(db, "fin", 3) and pantalla.siguiente_auto(db, UID, G) is not None
    with pytest.raises(HTTPException):
        reproducir(otro)
    # Con la automática apagada después, el último del asistente sigue sirviendo
    previo = _doc(db)["recorrido_previo"]["id"]
    pantalla.detener_auto(db, UID, G, "panel")
    assert reproducir(previo)["titulo"] == "Otra respuesta" and _auto(db)["activa"] is False


def test_un_error_no_la_apaga_pero_tres_seguidos_si():
    db = _abierta()
    pantalla.iniciar_auto(db, UID, G, "panel", G.por_id("aguas"))
    # la presentación no respondió: suelta el plan y lo intenta otra vez desde el mismo paso
    assert _avance(db, "narrando", 2) and _avance(db, "error", 2, motivo="sin_respuesta")
    assert _doc(db)["auto"] == {"activa": True, "capitulo": "aguas", "paso": 2, "rid": None, "vueltas": 0, "fallas": 1}
    assert pantalla.siguiente_auto(db, UID, G)["escenas"][0]["paso"] == 2
    # un paso que no se pudo mostrar se salta
    assert _avance(db, "error", 1, motivo="escena_fallida")
    assert (_auto(db)["paso"], _auto(db)["fallas"], _auto(db)["activa"]) == (3, 2, True)
    # volvió a narrar: los errores de antes ya no cuentan
    assert pantalla.siguiente_auto(db, UID, G)["escenas"][0]["paso"] == 3
    assert _avance(db, "narrando", 1) and _auto(db)["fallas"] == 0
    # tres planes seguidos que terminan en error: no insiste sobre una presentación que no responde
    for n in range(1, pantalla.MAX_FALLAS_AUTO + 1):
        assert _auto(db)["activa"] is True
        assert _avance(db, "error", 1, motivo="sin_respuesta") and _auto(db)["fallas"] == n
        if n < pantalla.MAX_FALLAS_AUTO:
            assert pantalla.siguiente_auto(db, UID, G) is not None
    assert _auto(db)["activa"] is False and pantalla.siguiente_auto(db, UID, G) is None
    # el último paso del capítulo que falla: sigue con el capítulo siguiente
    pantalla.iniciar_auto(db, UID, G, "panel", len(G) - 1)
    assert _avance(db, "error", 1, motivo="escena_fallida")
    assert (_auto(db)["capitulo"], _auto(db)["paso"], _auto(db)["vueltas"], _auto(db)["fallas"]) == ("portada", 1, 1, 1)


def test_el_estado_guardado_se_lee_con_tolerancia():
    assert pantalla.auto_de({"auto": None}, G) is None and pantalla.auto_de({"auto": {"rid": None}}, G) is None
    assert pantalla.auto_de({"auto": {"activa": "si", "capitulo": "salud", "paso": 2}}, G) is None
    # un capítulo o un paso que ya no existen, y números raros
    a = pantalla.auto_de({"auto": {"activa": True, "capitulo": "marte", "paso": 9, "rid": "x", "vueltas": -2, "fallas": 99}}, G)
    assert a == {"activa": True, "capitulo": "portada", "paso": 1, "rid": None, "vueltas": 0, "fallas": 0}
    # `rid` solo vale si el recorrido guardado es ese y sigue abierto
    plan = automatica.plan_del_capitulo(G, 0)
    base = {"activa": True, "capitulo": "portada", "paso": 1, "rid": plan["id"], "vueltas": 3, "fallas": 1}
    abierto = {"auto": base, "recorrido": {**plan, "destino": "pantalla_off", "cerrado": False, "auto": True}}
    assert pantalla.auto_de(abierto, G) == base
    assert pantalla.auto_de({**abierto, "recorrido": {**abierto["recorrido"], "cerrado": True}}, G)["rid"] is None
    assert pantalla.auto_de({**abierto, "recorrido": {**abierto["recorrido"], "id": "0" * 12}}, G)["rid"] is None
    assert pantalla.auto_de({**abierto, "auto": {**base, "activa": False}}, G)["rid"] is None
    # un plan de antes de la automática (sin la marca) no es automático
    assert pantalla.recorrido_de({"recorrido": {**plan, "destino": "vista", "cerrado": False}}, G)["auto"] is False
    # un plan del asistente no deja un `auto` a medias en una pantalla que nunca la encendió
    db = _Base()
    _hacer(db, TORRE)
    assert "auto" not in _doc(db)
    _hacer(db, {"op": "ir", "capitulo": "aguas"})
    assert "auto" not in _doc(db)


# ───────────────────────────── Lo que recibe la pantalla y las rutas ─────────────────────────────

def test_la_pantalla_recibe_auto_y_su_plan_con_auto_true():
    db = _Base()
    x = api.estado_pantalla(v=None, db=db, quien=QUIEN)   # la pantalla en off pregunta: queda como abierta
    assert x["auto"] is None and x["recorrido"] is None and x["v"] == 0
    assert api.estado_pantalla(v=0, db=db, quien=QUIEN).status_code == 204
    assert api.ver_recorrido(db=db, quien=QUIEN)["auto"] is None
    assert api.siguiente_automatico(db=db, quien=QUIEN).status_code == 204   # apagada: nada que hacer
    # El botón «Automática» de la pantalla: la enciende y, como está abierta, el primer plan ya está armado
    r = api.presentacion_automatica(api.AutoEntrada(accion="iniciar"), db=db, quien=QUIEN)
    assert r == {"auto": {"activa": True, "capitulo": "portada", "nombre": "Portada", "paso": 1, "de": len(PORTADA["pasos"])}}
    x = api.estado_pantalla(v=0, db=db, quien=QUIEN)
    assert x["auto"] == {"activa": True, "capitulo": "portada", "paso": 1} and x["v"] == 2
    plan = x["recorrido"]
    assert plan["auto"] is True and plan["titulo"] == "Portada" and plan["cierre"] is None and plan["edad_s"] == 0
    assert set(plan) == {"id", "titulo", "escenas", "cierre", "edad_s", "auto"} and len(plan["escenas"]) == len(PORTADA["pasos"])
    assert api.estado_pantalla(v=2, db=db, quien=QUIEN).status_code == 204
    assert api.siguiente_automatico(db=db, quien=QUIEN).status_code == 204   # suena su plan
    # El avance sube por la ruta de siempre y lleva la posición
    def avance(fase, n, rid=plan["id"], de=len(plan["escenas"])):
        return api.progreso(api.ProgresoEntrada(rid=rid, n=n, de=de, fase=fase, voz="activa"), db=db, quien=QUIEN)
    assert avance("narrando", 2).status_code == 204
    assert api.ver_recorrido(db=db, quien=QUIEN)["auto"] == {"activa": True, "capitulo": "portada", "paso": 2}
    assert avance("fin", 2).status_code == 204
    x = api.estado_pantalla(v=2, db=db, quien=QUIEN)
    assert x["recorrido"] is None and x["auto"] == {"activa": True, "capitulo": G.capitulos[1]["id"], "paso": 1}
    # Terminó: la pantalla pide el siguiente y le llega con `auto: true`
    r = api.siguiente_automatico(db=db, quien=QUIEN)
    x = api.estado_pantalla(v=x["v"], db=db, quien=QUIEN)
    assert r == {"id": x["recorrido"]["id"]} and x["recorrido"]["auto"] is True
    assert x["recorrido"]["titulo"] == G.capitulos[1]["nombre"] and x["progreso"] is None
    with pytest.raises(HTTPException) as e:   # el avance del plan anterior ya no vale
        avance("narrando", 1)
    assert e.value.status_code == 409
    # Un plan del asistente llega sin la marca: la pantalla espera a que termine para pedir otro
    _hacer(db, TORRE)
    x = api.estado_pantalla(v=x["v"], db=db, quien=QUIEN)
    assert "auto" not in x["recorrido"] and x["recorrido"]["titulo"] == "La torre del hospital"
    assert x["auto"] == {"activa": True, "capitulo": G.capitulos[1]["id"], "paso": 1}
    assert api.siguiente_automatico(db=db, quien=QUIEN).status_code == 204
    # Apagarla sube la versión: la pantalla se entera en su próxima pregunta
    assert api.presentacion_automatica(api.AutoEntrada(accion="detener"), db=db, quien=QUIEN)["auto"]["activa"] is False
    y = api.estado_pantalla(v=x["v"], db=db, quien=QUIEN)
    assert y["v"] == x["v"] + 1 and y["auto"]["activa"] is False and y["recorrido"]["titulo"] == "La torre del hospital"
    # Desde un capítulo; uno que no existe, 422; y la entrada, con su forma exacta
    r = api.presentacion_automatica(api.AutoEntrada(accion="iniciar", capitulo="aguas"), db=db, quien=QUIEN)
    assert (r["auto"]["capitulo"], r["auto"]["nombre"], r["auto"]["paso"]) == ("aguas", "Aguas", 1)
    assert api.estado_pantalla(v=None, db=db, quien=QUIEN)["recorrido"]["titulo"] == "Aguas"
    with pytest.raises(HTTPException) as e:
        api.presentacion_automatica(api.AutoEntrada(accion="iniciar", capitulo="marte"), db=db, quien=QUIEN)
    assert e.value.status_code == 422
    for mala in ({"accion": "pausar"}, {}, {"accion": "iniciar", "capitulo": "Salud"}, {"accion": "iniciar", "paso": 2}):
        with pytest.raises(ValidationError):
            api.AutoEntrada.model_validate(mala)
    # las tres rutas piden el permiso de la presentación
    rutas = {r.path: r for r in api.r.routes}
    for ruta in ("/api/pantalla/auto", "/api/pantalla/auto/siguiente"):
        assert rutas[ruta].methods == {"POST"} and "presentacion.ver" in rutas[ruta].dependant.dependencies[-1].call.permisos


# ───────────────────────────── La herramienta: el asistente y un agente por MCP ─────────────────────────────

def test_la_op_automatica_del_asistente_y_su_accion_para_el_chat():
    # Sin pantalla en off abierta: queda encendida y lo dice
    db = _Base()
    x = _hacer(db, {"op": "automatica", "accion": "iniciar"})
    accion = {"tipo": "automatica", "activa": True, "capitulo": "portada", "nombre": "Portada", "paso": 1,
              "de": len(PORTADA["pasos"])}
    assert x.acciones == [accion] and x.resumen == "Presentación automática encendida · empieza en Portada"
    assert x.contenido["automatica"] == {k: v for k, v in accion.items() if k != "tipo"}
    assert x.contenido["pantalla_en_off_abierta"] is False and x.contenido["nota"] == hi.NOTA_AUTOMATICA_SIN_PANTALLA
    assert x.contenido["recorre"]["capitulos"] == len(G) and x.contenido["recorre"]["pasos"] == G.total_pasos()
    assert 5 <= x.contenido["recorre"]["vuelta_completa_min"] <= 16
    assert "recorrido" not in _doc(db) and _doc(db)["por"] == "asistente"
    # Con la pantalla abierta y desde un capítulo (por su nombre): el primer plan ya suena allá; el chat no lo narra
    db = _abierta()
    x = _hacer(db, {"op": "automatica", "accion": "iniciar", "capitulo": "Salud"})
    assert x.acciones == [{"tipo": "automatica", "activa": True, "capitulo": "salud", "nombre": "Salud", "paso": 1,
                           "de": len(SALUD["pasos"])}]
    assert x.contenido["nota"] == hi.NOTA_AUTOMATICA and "plan CORTO" in hi.NOTA_AUTOMATICA and "3 a 5 pasos" in hi.NOTA_AUTOMATICA
    assert _doc(db)["recorrido"]["titulo"] == "Salud" and _doc(db)["recorrido"]["auto"] is True
    # `estado` dice por dónde va, y que ese plan es el automático
    assert _avance(db, "narrando", 3)
    e = _hacer(db, {"op": "estado"}).contenido["pantalla"]
    assert e["automatica"] == {"activa": True, "capitulo": "salud", "nombre": "Salud", "paso": 3, "de": len(SALUD["pasos"]),
                               "vueltas": 0}
    assert e["plan"]["automatico"] is True and e["plan"]["paso"] == 3 and e["cambiada_por"] == "la presentación automática"
    # El control «detener» del asistente sobre el plan automático la apaga y se lo dice al chat
    x = _hacer(db, {"op": "control_recorrido", "accion": "detener"})
    assert x.acciones == [{"tipo": "automatica", "activa": False, "capitulo": "salud", "nombre": "Salud", "paso": 3,
                           "de": len(SALUD["pasos"])}]
    assert "quedó apagada" in x.contenido["automatica"] and _auto(db)["activa"] is False
    # Apagarla; y apagarla cuando no estaba encendida
    _hacer(db, {"op": "automatica", "accion": "iniciar"})
    x = _hacer(db, {"op": "automatica", "accion": "detener"})
    assert x.acciones == [{**accion, "activa": False}] and x.resumen == "Presentación automática apagada"
    assert x.contenido["nota"] == hi.NOTA_AUTOMATICA_APAGADA and _doc(db)["recorrido"]["cerrado"] is True
    x = _hacer(db, {"op": "automatica", "accion": "detener"})
    assert x.contenido["nota"] == "La presentación automática no estaba encendida." and x.acciones[0]["activa"] is False
    # Si sonaba un plan en la pestaña del chat y se enciende con la pantalla abierta, lo detiene allá
    db = _Base()
    en_la_pestana = _hacer(db, TORRE).acciones[0]["recorrido"]["id"]
    assert _doc(db)["recorrido"]["destino"] == "vista"
    pantalla.marcar_vista(db, UID)
    x = _hacer(db, {"op": "automatica", "accion": "iniciar"})
    assert x.acciones[0] == {"tipo": "presentacion", "op": "control_recorrido", "rid": en_la_pestana, "accion": "detener",
                             "motivo": "otra_orden"}
    assert x.acciones[1]["tipo"] == "automatica" and _doc(db)["recorrido"]["auto"] is True
    # «Reproducir» sobre el plan automático no pone una tarjeta en el chat
    assert _hacer(db, {"op": "control_recorrido", "accion": "reproducir"}).acciones == []
    assert _doc(db)["recorrido"]["auto"] is True and _auto(db)["rid"] == _doc(db)["recorrido"]["id"]
    # No escribe nada para la sala: también corre en una conversación que ya trae datos de habitantes
    assert "automatica" not in hi.PROYECTAN_TEXTO


def test_la_op_automatica_por_mcp():
    db = _abierta()
    x = _hacer(db, {"op": "automatica", "accion": "iniciar", "capitulo": "aguas"}, por="mcp")
    assert x.acciones == [] and x.contenido["automatica"]["capitulo"] == "aguas" and x.contenido["nota"] == hi.NOTA_AUTOMATICA
    assert _doc(db)["recorrido"]["titulo"] == "Aguas" and _doc(db)["auto"]["activa"] is True
    res = asyncio.run(mcp.llamar(db, UID, "presentacion", {"op": "automatica", "accion": "detener"}))
    assert res["isError"] is False and res["structuredContent"]["automatica"]["activa"] is False
    assert res["structuredContent"]["resumen"] == "Presentación automática apagada" and _auto(db)["activa"] is False
    # Sin pantalla abierta no es un error (como ir y visual, queda guardado): empieza cuando se abra
    db = _Base()
    res = asyncio.run(mcp.llamar(db, UID, "presentacion", {"op": "automatica", "accion": "iniciar"}))
    assert res["isError"] is False and res["structuredContent"]["nota"] == hi.NOTA_AUTOMATICA_SIN_PANTALLA
    # el plan automático se controla por MCP como cualquier otro de la pantalla en off
    pantalla.marcar_vista(db, UID)
    assert pantalla.siguiente_auto(db, UID, G) is not None
    res = asyncio.run(mcp.llamar(db, UID, "presentacion", {"op": "control_recorrido", "accion": "pausar"}))
    assert res["isError"] is False and _auto(db)["activa"] is True
    res = asyncio.run(mcp.llamar(db, UID, "presentacion", {"op": "control_recorrido", "accion": "detener"}))
    assert res["isError"] is False and _auto(db)["activa"] is False and "quedó apagada" in res["structuredContent"]["automatica"]
    # la entrada mala vuelve como un error que el agente puede leer
    res = asyncio.run(mcp.llamar(db, UID, "presentacion", {"op": "automatica"}))
    assert res["isError"] is True and "Para automatica, diga la accion: iniciar" in res["content"][0]["text"]
    assert "automatica" in mcp.INSTRUCCIONES and "muy resumida" in mcp.INSTRUCCIONES and "automatica" in mcp.D_MCP


def test_la_entrada_de_la_op_automatica():
    V = hi.PresentacionEntrada.model_validate
    assert V({"op": "automatica", "accion": "iniciar"}).accion == "iniciar"
    assert V({"op": "automatica", "accion": "iniciar", "capitulo": "salud"}).capitulo == "salud"
    for mala, dice in (({"op": "automatica"}, "Para automatica, diga la accion"),
                       ({"op": "automatica", "accion": "pausar"}, "Para automatica, diga la accion"),
                       ({"op": "automatica", "accion": "encender"}, "accion"),
                       ({"op": "automatica", "accion": "iniciar", "paso": 2}, "no usa: paso"),
                       ({"op": "automatica", "accion": "iniciar", "titulo": "La vuelta"}, "no usa: titulo"),
                       ({"op": "automatica", "accion": "iniciar", "camara": "aerea"}, "no usa: camara"),
                       ({"op": "control_recorrido", "accion": "iniciar"}, "Para control_recorrido, diga la accion"),
                       ({"op": "ir", "capitulo": "salud", "accion": "iniciar"}, "no usa: accion")):
        with pytest.raises(ValidationError) as e:
            V(mala)
        assert dice in str(e.value), mala
    # un capítulo que no existe no enciende nada, y para detener no va capítulo
    db = _abierta()
    with pytest.raises(ErrorHerramienta) as e:
        _hacer(db, {"op": "automatica", "accion": "iniciar", "capitulo": "marte"})
    assert e.value.codigo == "no_existe" and _auto(db) is None
    with pytest.raises(ErrorHerramienta):
        _hacer(db, {"op": "automatica", "accion": "detener", "capitulo": "salud"})
    # El esquema y los textos para el modelo
    s = hi._esquema_presentacion()
    assert "automatica" in s["properties"]["op"]["enum"] and "automatica:" in s["properties"]["op"]["description"]
    assert s["properties"]["accion"]["enum"] == [*rec.CONTROLES, "iniciar"]
    assert "automatica: iniciar o detener" in s["properties"]["accion"]["description"]
    assert "automatica (accion iniciar o detener)" in hi.D_PRESENTACION and "muy resumida" in hi.D_PRESENTACION
    assert len(hi.D_PRESENTACION) < 1500 and len(mcp.D_MCP) < 1500
    t = sistema.texto(QUIEN, list(hi.HERRAMIENTAS))
    for parte in ("op `automatica` con `accion` iniciar", "recorre sola toda la presentación, muy resumida",
                  "se apaga con `accion` detener", "una pregunta la interrumpe", "un plan CORTO (de 3 a 5 `pasos`",
                  "sigue sola donde iba"):
        assert parte in t, parte
    assert "automatica" not in sistema.texto(QUIEN, [h for h in hi.HERRAMIENTAS if h.nombre != "presentacion"])


@pytest.mark.skipif("automatica" not in bucle.ACCIONES, reason=(
    "Falta «automatica» en bucle.ACCIONES (app/agente/bucle.py): sin eso el bucle descarta la acción del chat"))
def test_la_accion_del_chat_pasa_el_filtro_del_bucle():
    accion = _hacer(_Base(), {"op": "automatica", "accion": "iniciar"}).acciones[0]
    assert bucle._acciones([accion]) == [accion]


# ───────────────────────────── El contexto del asistente ─────────────────────────────

def test_el_contexto_del_asistente_con_la_automatica_encendida():
    db = _Base()
    assert sistema.recorrido_del_contexto(db, UID) == ""
    # Encendida sin pantalla abierta
    pantalla.iniciar_auto(db, UID, G, "asistente")
    t = sistema.recorrido_del_contexto(db, UID)
    assert t.startswith("Presentación automática encendida, pero no hay una pantalla en off abierta: empieza sola (en "
                        "Portada (portada), paso 1 de ") and "\n" not in t
    # Con la pantalla abierta y su plan sonando: un solo renglón, que no lo nombra como un plan del asistente
    db = _abierta()
    pantalla.iniciar_auto(db, UID, G, "asistente", G.por_id("salud"))
    assert _avance(db, "narrando", 3)
    t = sistema.recorrido_del_contexto(db, UID)
    assert "\n" not in t and "Plan «" not in t
    assert t.startswith("Presentación automática encendida: la pantalla en off recorre sola toda la presentación, muy "
                        "resumida; va en Salud (salud), paso 3 de 10; voz: activa. ")
    assert "respóndele con un plan CORTO (recorrido de 3 a 5 pasos): la interrumpe y, cuando termina, sigue sola" in t
    assert "No la detengas ni la reinicies si no te lo piden (op automatica)" in t
    bloque = sistema.contexto_del_panel({}, datetime.now(timezone.utc), recorrido=t)
    assert t in bloque and bloque.endswith("</contexto_del_panel>")
    assert _avance(db, "pausa", 3, motivo="boton")
    assert "paso 3 de 10, en pausa; voz: activa" in sistema.recorrido_del_contexto(db, UID)
    # Un plan del asistente la interrumpe: el plan en un renglón y la automática, en espera, en otro
    _hacer(db, TORRE)
    assert _avance(db, "narrando", 2)
    plan, auto = sistema.recorrido_del_contexto(db, UID).split("\n")
    assert plan.startswith("Plan «La torre del hospital» en la pantalla en off: paso 2 de 3 del plan, narrando")
    assert auto.startswith("Presentación automática encendida, en espera mientras termina ese plan: después sigue sola en "
                           "Salud (salud), paso 3 de 10. ")
    # Terminó ese plan: se nombra un rato como terminado, y la automática dice dónde sigue
    assert _avance(db, "fin", 3)
    plan, auto = sistema.recorrido_del_contexto(db, UID).split("\n")
    assert "terminado" in plan and "va en Salud (salud), paso 3 de 10" in auto
    # Entre un capítulo y el siguiente el plan automático que terminó no se nombra como un plan
    assert pantalla.siguiente_auto(db, UID, G) is not None
    r = _doc(db)["recorrido"]
    assert _avance(db, "fin", len(r["escenas"]))
    t = sistema.recorrido_del_contexto(db, UID)
    assert "Plan «" not in t and f"va en {G.capitulos[G.por_id('salud') + 1]['nombre']}" in t
    # Apagada: nada
    pantalla.detener_auto(db, UID, G, "asistente")
    assert sistema.recorrido_del_contexto(db, UID) == "" and pantalla.describir_auto(_doc(db), G) == ""


# ───────────────────────────── Con MongoDB: las rutas de punta a punta ─────────────────────────────

def test_las_rutas_de_la_automatica_con_la_base_de_verdad(sesion):
    assert sesion.get("/api/pantalla").json()["auto"] is None   # la pantalla en off pregunta: queda como abierta
    r = sesion.post("/api/pantalla/auto", json={"accion": "iniciar", "capitulo": "salud"})
    assert r.status_code == 200
    assert r.json() == {"auto": {"activa": True, "capitulo": "salud", "nombre": "Salud", "paso": 1, "de": len(SALUD["pasos"])}}
    e = sesion.get("/api/pantalla").json()
    plan = e["recorrido"]
    assert plan["auto"] is True and plan["titulo"] == "Salud" and e["auto"] == {"activa": True, "capitulo": "salud", "paso": 1}
    assert sesion.post("/api/pantalla/auto/siguiente").status_code == 204   # suena su plan
    avance = {"rid": plan["id"], "n": 4, "de": len(plan["escenas"]), "fase": "narrando", "voz": "activa"}
    assert sesion.post("/api/pantalla/progreso", json=avance).status_code == 204
    assert sesion.get("/api/pantalla/recorrido").json()["auto"] == {"activa": True, "capitulo": "salud", "paso": 4}
    # un plan del asistente lo suelta y, al terminar, sigue en el paso que se decía
    db = sesion.app.state.db
    asyncio.run(hi.presentacion_en_pantalla(db, 0, hi.PresentacionEntrada.model_validate(TORRE), "asistente"))
    d = db.pantallas.find_one({"_id": 0})
    assert d["auto"] == {"activa": True, "capitulo": "salud", "paso": 4, "rid": None, "vueltas": 0, "fallas": 0}
    assert sesion.post("/api/pantalla/auto/siguiente").status_code == 204
    fin = {"rid": d["recorrido"]["id"], "n": 3, "de": 3, "fase": "fin", "voz": "activa"}
    assert sesion.post("/api/pantalla/progreso", json=fin).status_code == 204
    r = sesion.post("/api/pantalla/auto/siguiente")
    e = sesion.get("/api/pantalla").json()
    assert r.status_code == 200 and r.json() == {"id": e["recorrido"]["id"]}
    assert e["recorrido"]["auto"] is True and e["recorrido"]["escenas"][0]["paso"] == 4
    # el control «detener» sobre su plan la apaga; apagarla otra vez no cambia nada
    r = sesion.post("/api/pantalla/recorrido/control", json={"rid": e["recorrido"]["id"], "accion": "detener"})
    assert r.status_code == 200 and db.pantallas.find_one({"_id": 0})["auto"]["activa"] is False
    assert sesion.post("/api/pantalla/auto", json={"accion": "detener"}).json()["auto"]["activa"] is False
    e = sesion.get("/api/pantalla").json()
    assert e["recorrido"] is None and e["auto"] == {"activa": False, "capitulo": "salud", "paso": 4}
    assert sesion.post("/api/pantalla/auto", json={"accion": "iniciar", "capitulo": "marte"}).status_code == 422
    assert sesion.post("/api/pantalla/auto", json={"accion": "otra"}).status_code == 422


def test_sin_sesion_no_hay_presentacion_automatica(cliente):
    assert cliente.post("/api/pantalla/auto", json={"accion": "iniciar"}).status_code in (401, 403)
    assert cliente.post("/api/pantalla/auto/siguiente").status_code in (401, 403)
