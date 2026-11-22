"""La voz de la presentación (app/agente/lenguaje.py): cómo le habla el asistente a la sala (sencillo y cercano, con el
léxico del candidato, sin siglas ni tecnicismos y explicando cada parte), el glosario de las siglas del guion y la
narración escrita a mano de la presentación automática.

Sin MongoDB ni modelo: el guion real y textos inventados."""
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import automatica
from app import recorrido as rec
from app.agente import guion as guion_presentacion
from app.agente import lenguaje, redactor, sistema
from app.agente.herramientas import interfaz as hi
from app.api import mcp
from app.proyectable import texto_proyectable

G = guion_presentacion.cargar()
RAIZ = Path(__file__).resolve().parents[2]
GENERAL_JSON = RAIZ / "data" / "propuesta" / "general.json"
SIGLA = re.compile(r"(?<![\w.])[A-ZÁÉÍÓÚÑ]{2,}[0-9]*(?:-[0-9]+)?(?![\w])")


def _textos(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from _textos(x)
    elif isinstance(v, list):
        for x in v:
            yield from _textos(x)


# ───────────────────────────── Las reglas de la voz ─────────────────────────────

def test_la_voz_trae_el_lexico_del_candidato_y_lo_que_se_retiro():
    v = lenguaje.COMO_SE_EXPLICA
    for x in ("le apostamos", "podamos", "juntos", "¿sí?", "«El casco urbano», completo", "«recursos económicos», "
              "nunca «plata»", "«empleo», no «trabajo»", "«¡Trabajemos juntos!» no se tocan", "Sin siglas",
              "Sin tecnicismos", "Explica cada parte: qué es, para qué sirve y a quién le sirve",
              "el hospital Héctor Abad Gómez", "puestos de salud, malecón, muelle flotante ni pasarela"):
        assert x in v, x
    for nombre in lenguaje.NOMBRES:
        assert nombre in v, nombre
    # cambian las palabras, no los datos: nada de inventar ni de hablar a nombre del candidato
    assert "cifras, nombres y plazos solo del guion" in v and "Nada de «yo»" in v
    assert "sin siglas" in lenguaje.EN_CORTO and "«recursos económicos», nunca «plata»" in lenguaje.EN_CORTO


def test_la_voz_va_en_todo_lo_que_oye_la_sala():
    # el redactor del plan en flujo y el asistente del panel con la presentación: las reglas enteras
    assert lenguaje.COMO_SE_EXPLICA in redactor.INSTRUCCIONES
    assert redactor.INSTRUCCIONES.rstrip().endswith("El guion del capítulo, lo único que sabes de él:")
    P = next(h for h in hi.HERRAMIENTAS if h.nombre == "presentacion")
    quien = SimpleNamespace(uid=7, usuario="c", nombre="C", rol="coordinador")
    assert lenguaje.COMO_SE_EXPLICA in sistema.texto(quien, [P])
    assert lenguaje.COMO_SE_EXPLICA not in sistema.texto(quien, [h for h in hi.HERRAMIENTAS if h.nombre != "presentacion"])
    # lo que no tiene lugar para más, en una frase: la respuesta inmediata, las respuestas habladas, el guion, el paso
    # y los agentes por MCP
    for donde in (sistema.SISTEMA_ADELANTO, sistema.RESPUESTA_HABLADA, hi.NOTA_GUION, mcp.INSTRUCCIONES):
        assert lenguaje.EN_CORTO in donde
    assert "UNA frase sencilla y sin siglas" in hi.D_PRESENTACION and "sencilla y sin siglas" in hi.D_PRESENTACION_ASISTENTE


# ───────────────────────────── El glosario ─────────────────────────────

def test_toda_sigla_del_guion_tiene_su_explicacion():
    """La que llegue con una propuesta nueva hay que explicarla en `SIGLAS` (o, si no es una sigla, decirlo en
    `NO_SON_SIGLAS`): si no, el modelo la diría como viene."""
    crudo = json.loads(guion_presentacion.RUTA.read_text(encoding="utf-8"))
    vistas = {m.group(0) for t in _textos(crudo) for m in SIGLA.finditer(t)}
    sin_explicar = sorted(vistas - set(lenguaje.SIGLAS) - lenguaje.NO_SON_SIGLAS)
    assert sin_explicar == [], sin_explicar
    for s, d in lenguaje.SIGLAS.items():
        assert d and d == d.strip() and "plata" not in d, s


def test_siglas_en_busca_solo_las_que_aparecen():
    assert lenguaje.siglas_en("La PTAR central y la NSR-10.") == {"PTAR": lenguaje.SIGLAS["PTAR"],
                                                                  "NSR-10": lenguaje.SIGLAS["NSR-10"]}
    assert lenguaje.siglas_en("PTARX, aptar, la ptar") == {}
    # una unidad, solo detrás de un número; «km²» no es «km»
    assert set(lenguaje.siglas_en("Un lote de 5 ha; hay agua; 1.895 km² y 2,3 km")) == {"ha", "km", "km²"}
    assert lenguaje.siglas_en("No hay nada que explicar") == {}
    # en objetos y listas, como el guion de un capítulo o un paso; en el orden del glosario
    assert list(lenguaje.siglas_en({"a": ["Con el BIM", {"b": "la PTAP"}], "n": 3})) == ["PTAP", "BIM"]
    assert lenguaje.siglas_en(None) == {}


def test_el_redactor_y_el_guion_llevan_las_siglas_del_capitulo():
    salud = G.por_id("salud")
    s = redactor.sistema_de(G, salud)
    guion = json.loads(s[len(redactor.INSTRUCCIONES):])
    assert guion["siglas"] == lenguaje.siglas_en(G.capitulo_para_leer(salud))
    assert guion["siglas"]["NSR-10"] == lenguaje.SIGLAS["NSR-10"] and "TPR" in guion["siglas"]
    # el mismo texto para el mismo capítulo (la caché del proveedor)
    assert redactor.sistema_de(G, salud) == s


# ───────────────────────────── Lo que se dice ya escrito ─────────────────────────────

def test_problemas_de_voz():
    assert lenguaje.problemas_de_voz("Aquí va la planta de tratamiento de aguas residuales del casco urbano.") == []
    assert lenguaje.problemas_de_voz("La plaza con las letras YONDÓ y el Sisbén IV.") == []
    assert lenguaje.problemas_de_voz("La PTAR del casco.") == ["sigla «PTAR»", "«casco» sin «urbano»"]
    assert lenguaje.problemas_de_voz("Según la Res. 1633 de 2025.") == ["abreviatura «Res.»"]
    assert lenguaje.problemas_de_voz("Sin plata no hay malecón.") == ["«malecón» salió de la propuesta",
                                                                      "«plata» en vez de «recursos económicos»"]
    assert lenguaje.problemas_de_voz("Los puestos de salud rurales.") == ["«puestos de salud» salió de la propuesta"]
    # el mirador quedó sin muelle flotante ni pasarela (PR de la vivienda de 300 apartamentos), y eso llega también
    # en la frase corta, la que leen los agentes por MCP y la respuesta inmediata
    assert lenguaje.problemas_de_voz("Al mirador le quitamos el muelle flotante.") == ["«muelle flotante» salió de la propuesta"]
    assert all(x in lenguaje.EN_CORTO for x in lenguaje.RETIRADO_DICHO)
    assert lenguaje.problemas_de_voz(None) == []


def test_cada_paso_tiene_su_narracion_escrita_con_la_voz():
    """La presentación automática no tiene modelo que aplique las reglas: dice la narración escrita a mano de cada
    paso (`tecnica.narracion` de general.json), que cumple la voz y lo que se proyecta, y es lo que dice."""
    for ci, c in enumerate(G.capitulos):
        for pi, p in enumerate(c["pasos"]):
            t = p.get("narracion")
            assert t, (c["id"], p["id"])
            assert lenguaje.problemas_de_voz(t) == [], (c["id"], p["id"], lenguaje.problemas_de_voz(t))
            assert texto_proyectable(t, rec.MAX_NARRACION) == t and 1 <= len(rec.partir_frases(t)) <= rec.MAX_FRASES
            assert automatica.narracion_del_paso(G, ci, pi) == t


@pytest.mark.skipif(not GENERAL_JSON.is_file(), reason="Sin data/propuesta/general.json (el panel desplegado aparte)")
def test_la_narracion_de_general_json_es_de_pasos_que_existen():
    narracion = json.loads(GENERAL_JSON.read_text(encoding="utf-8"))["tecnica"]["narracion"]
    pasos = {c["id"]: {p["id"] for p in c["pasos"]} for c in G.capitulos}
    for cid, del_capitulo in narracion.items():
        assert cid in pasos, cid
        assert set(del_capitulo) <= pasos[cid], (cid, sorted(set(del_capitulo) - pasos[cid]))
