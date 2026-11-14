"""El recorrido narrado de la presentación técnica (docs/agente.md, «Recorridos narrados»): el asistente arma en una
llamada un recorrido de escenas (lo que se ve + lo que se dice) y la página que mira la sala lo reproduce con su propio
reloj, con la voz del navegador si la persona la encendió.

* El servidor: app/recorrido.py (las frases, los tiempos, la validación de todo o nada), la op `recorrido` de la
  herramienta `presentacion` (con la base en memoria de test_pantalla_mcp), el avance (uno final lo cierra), los
  controles, el colapso cuando el asistente pide otra cosa (solo si lo pedido vale, y avisando a la pestaña donde
  suena), la escena en curso como lo que se ve, cuándo el contexto deja de nombrarlo y la guarda con personas.
* El navegador, con Node: el reproductor (admin/web/js/reproductor.js) con un reloj falso, la voz (voz.js) con una
  síntesis falsa, los validadores del puente y la tarjeta del chat, con lo que de verdad arma el servidor.
* Que los topes y las listas sean los mismos en los cuatro lados, y las reglas de lo que se pinta.
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

ENTRADA = {"op": "recorrido", "titulo": "La torre del hospital", "escenas": [
    {"capitulo": "salud", "paso": "torre", "camara": "oblicua",
     "narracion": "Estamos junto al hospital Héctor Abad Gómez. Aquí se levanta la nueva torre de servicios."},
    {"inmersion": "torre_hoy", "narracion": "Así está hoy el predio: las alas del antiguo Centro Vida, que se demuelen."},
    {"inmersion": "paso", "girar": True, "resaltar": {"leyenda": 1},
     "narracion": "Con el proyecto, la torre de cuatro pisos queda a 5,3 m del hospital actual."},
    {"detalle": "torre", "girar": False, "resaltar": {"especificacion": "Estructura"},
     "narracion": "Su estructura es dual en concreto, sobre 146 pilotes de 15 m."},
    {"paso": "torre_pisos", "resaltar": {"punto": 1}, "narracion": "Por dentro, cada piso agrupa sus servicios."}],
    "cierre": {"puntos": ["Sigue atendiendo tras un sismo", "Cuatro pisos, 15 camas"]},
    "sugerencias": ["Ver el simulador sísmico"]}


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
    assert absoluto["cierre"] == {"puntos": ["Sigue atendiendo tras un sismo", "Cuatro pisos, 15 camas"]}
    # La tarjeta del chat: dónde, qué hace y la narración de cada escena; las sugerencias y la duración
    t = r.acciones[1]
    assert t["id"] == absoluto["id"] and t["destino"] == "vista" and t["sugerencias"] == ["Ver el simulador sísmico"]
    assert t["cierre"] == absoluto["cierre"]["puntos"] and t["duracion_ms"] == rec.duracion_ms(absoluto, G)
    assert t["escenas"][0]["hace"] == ["paso", "camara"] and "modelo" in t["escenas"][1]["hace"]
    assert all(set(x["hace"]) <= set(hi.HACE) for x in t["escenas"])
    # Al modelo, lo compacto: qué se ve en cada escena (sin repetir el recorrido entero)
    assert r.contenido["recorrido"]["escenas"] == 5 and r.contenido["escenas"][0]["muestra"].startswith("Salud · paso 3")
    assert len(json.dumps(r.contenido, ensure_ascii=False)) < 4000
    # Queda guardado, con la última escena como base (lo que queda a la vista al terminar)
    d = db.pantallas.find_one({"_id": 7})
    assert d["recorrido"]["destino"] == "vista" and d["recorrido"]["cerrado"] is False
    assert (d["capitulo"], d["paso"]) == ("salud", 4)


def test_todo_o_nada_con_el_numero_de_la_escena_que_falla():
    db = _Base()
    malos = [
        ({"op": "recorrido", "titulo": "Una prueba", "escenas": [
            {"capitulo": "salud", "paso": "torre", "narracion": "Hola.", "resaltar": {"especificacion": "Cimientos"}}]},
         "Escena 1"),
        ({"op": "recorrido", "titulo": "Una prueba", "escenas": [
            {"capitulo": "vivienda", "narracion": "Una."}, {"enfoque": "titulacion", "narracion": "Dos."}]}, "Escena 2"),
    ]
    for entrada, donde in malos:
        with pytest.raises(ErrorHerramienta) as e:
            _hacer(db, 7, entrada, por="asistente")
        assert str(e.value).startswith(donde)
    assert db.pantallas.find_one({"_id": 7}) is None   # nada se guardó
    with pytest.raises(Exception):
        _hacer(db, 7, {"op": "recorrido", "titulo": "Plata", "escenas": [{"capitulo": "salud", "narracion": "Cuesta $5 M"}]},
               por="asistente")
    with pytest.raises(Exception):
        _hacer(db, 7, {"op": "recorrido", "titulo": "Largo", "escenas": [
            {"capitulo": "salud", "narracion": "Una."}] * (rec.MAX_ESCENAS + 1)}, por="asistente")


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
    est = _hacer(db, 7, {"op": "estado"}, por="asistente").contenido["pantalla"]["recorrido"]
    assert est["escena"] == 2 and est["fase"] == "narrando" and est["avisos"] == [{"n": 2, "tipo": "atlas"}]
    assert "escena 2 de 5" in pantalla.describir_recorrido(pantalla.resumen_recorrido(db.pantallas.find_one({"_id": 7}), G))
    # Un control: va como acción a la pestaña (el recorrido suena allá)
    c = _hacer(db, 7, {"op": "control_recorrido", "accion": "pausar"}, por="asistente")
    assert c.acciones == [{"tipo": "presentacion", "op": "control_recorrido", "rid": rid, "accion": "pausar"}]
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
    assert est["muestra"].startswith("Salud (salud), paso 3") and est["recorrido"]["escena"] == 1
    # Una pantalla en off que se abre ahora muestra la escena 1 (el recorrido suena en la pestaña: no se lo lleva)
    e = pantalla.para_pantalla(pantalla.estado(d, G), d, G)
    assert (e["capitulo"], e["paso"], e["camara"], e["recorrido"]) == ("salud", 3, "oblicua", None)
    pantalla.marcar_vista(db, 7)
    assert sistema.pantalla_del_contexto(db, 7).startswith("Salud (salud), paso 3")
    assert "escena 1 de 2, narrando" in sistema.recorrido_del_contexto(db, 7)
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
    for nombre in ("RESPIRO_MS", "ENTRE_FRASES_MS", "CIERRE_SOSTENER_MS", "PREGUNTAS_MS"):
        assert _js_const(repro, nombre) == str(getattr(rec, nombre)), nombre
    assert "Math.min(16000, Math.max(3200, 1500 + 62 *" in repro   # lectura_ms
    tarjeta = TARJETA_JS.read_text(encoding="utf-8")
    assert set(re.findall(r"^  (\w+): \['", tarjeta, re.M)) | set(re.findall(r", (\w+): \['", tarjeta)) == set(hi.HACE)


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
const { crearReproductor, lecturaMs } = await import(process.argv[2]);
function relojFalso() {
  let t = 0, id = 0; const cola = new Map();
  return { ahora: () => t, programar(f, ms) { const h = ++id; cola.set(h, { f, en: t + ms }); return h; }, cancelar(h) { cola.delete(h); },
    async avanzar(ms) { const fin = t + ms; for (;;) { await new Promise((r) => setImmediate(r)); let p = null;
      for (const [h, x] of cola) if (x.en <= fin && (!p || x.en < p[1].en)) p = [h, x]; if (!p) break; cola.delete(p[0]); t = p[1].en; p[1].f(); }
      t = fin; for (let i = 0; i < 5; i++) await new Promise((r) => setImmediate(r)); } };
}
const V = { enfoque: null, camara: 'paso', rumbo: null, girar: false, comparar: 'proyecto', detalle: null, inmersion: null };
const esc = (paso, frases) => ({ capitulo: 'salud', paso, panel: true, visual: V, resaltar: null, frases, sostener_ms: 1100 });
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
console.log(JSON.stringify(out));
"""


@requiere_node
def test_el_reproductor_con_un_reloj_falso(tmp_path):
    (tmp_path / "rep.mjs").write_text(NODE_REPRODUCTOR, encoding="utf-8")
    p = subprocess.run(["node", str(tmp_path / "rep.mjs"), REPRODUCTOR_JS.as_uri()], capture_output=True, text=True,
                       timeout=60)
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
    assert r["inicial"] == "apagada" and r["callada"] == "fallo"
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
const { recorrido, tarjeta, colapso } = JSON.parse(await (await import('node:fs/promises')).readFile(process.argv[4], 'utf8'));
const out = {};
const copia = (x) => JSON.parse(JSON.stringify(x));
out.valido = JSON.stringify(P.recorridoValido(recorrido)) === JSON.stringify(recorrido);
const variantes = {
  plata: (r) => { r.escenas[0].frases[0] = 'Cuesta $5.000'; },
  extra: (r) => { r.escenas[0].otra = 1; },
  muchas: (r) => { r.escenas = Array(9).fill(r.escenas[0]); },
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
console.log(JSON.stringify(out));
"""


@requiere_node
def test_el_puente_y_la_tarjeta_validan_lo_que_arma_el_servidor(tmp_path):
    db, r = _armar()
    colapso = _hacer(db, 7, {"op": "visual", "camara": "oblicua"}, por="asistente").acciones[0]
    datos = {"recorrido": r.acciones[0]["recorrido"], "tarjeta": r.acciones[1], "colapso": colapso}
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
