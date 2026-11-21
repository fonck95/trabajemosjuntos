"""La respuesta hablada (app/agente/voz.py `Frases` y bucle.py) y lo que se dice: las frases que el turno arma a medida
que llega el texto del modelo (cortes, Markdown limpio, lo que no se dice ante una sala), cada una firmada para esa
persona y esa conversación, descartadas con la ronda (`frases_descartar`) y rehechas contra el texto final
(`texto_ronda`); el turno que solo las emite si el mensaje lo pidió, la voz está disponible para esa persona y la
conversación no trae datos de habitantes (y deja de emitirlas desde que el modelo recibe datos de una persona); el
renglón «Respuesta hablada» del contexto del panel; y la tabla de pronunciación de web/js/voz.js (`paraDecir`), la
misma en Python (`voz.para_decir`): una prueba las corre con las mismas frases en Node.

Las del turno usan MongoDB (se saltan sin él), el modelo falso (Anthropic simulado o el de Mnemo) y el MCP falso con
`mnemo_speak`. Solo datos inventados."""
import json
import random
import re
import subprocess
from pathlib import Path

import pytest

from ayudas_agente import ALCANCES_PANEL, TU, R, T, conectar_mnemo, encender, encender_mnemo, enviar, sse, tipos
from ayudas_g3 import persona
from app.agente import bucle, sistema, voz
from app.agente import conversaciones as conv_db
from test_agente_presentacion import requiere_node
from test_voz_servidor import AUDIO, VOZ_ID, _mnemo_que_habla, audio_de, eventos

ADMIN = Path(__file__).resolve().parents[1]
VOZ_JS = ADMIN / "web" / "js" / "voz.js"


# ───────────────────────────── `paraDecir`: la misma tabla en JavaScript y en Python ─────────────────────────────

FRASES_DECIR = [
    "La torre de 3.369,6 m² cumple la NSR-10 y la Res. 1633, con 146 pilotes de 15 m bajo la placa.",
    "Son 12 m³ de concreto, 3 km de vía y 1,5 ha de parque; abre 24 h al día.",
    "El 45 % de las viviendas, ≈ 300 familias, pasa de 2024–2027 → 2028—2031.",
    "La E.S.E. habilitada en el REPS, con TPR, BIM e IFC4.",
    "5m² y 7 m3, 10 hm, 3 mm, 4 h, 2h30, 100%", "Sin nada que cambiar.", "  espacios  raros y\tsaltos\n ",
    "1999 - 2001 y 1899-1900 y 20245-20266", "→ al comienzo y al final →", "≈≈ dos", "m² sin número",
    "El 5 % con espacio duro", "12 km/h y 3 ha.", "NSR-100 no es NSR-10.", "Res.Res. y E.S.E.E.S.E.",
    "١٢ m² con dígitos árabes", "2 ｍ² ancho completo", "", "La 5ª etapa: 3 m, 4 m², 5 m³.",
]


def test_para_decir_dice_lo_que_dice_el_navegador_y_nada_mas():
    assert voz.para_decir("La torre de 3.369,6 m² cumple la NSR-10.") == (
        "La torre de 3.369,6 metros cuadrados cumple la ene ese erre diez.")
    assert voz.para_decir(None) == "" and voz.para_decir(" \t ") == ""
    assert voz.para_decir("De 2028 – 2031, ≈ 45 %") == "De 2028 a 2031, unos 45 por ciento"


@requiere_node
def test_la_tabla_de_paradecir_es_la_misma_en_javascript_y_en_python(tmp_path):
    guion = ("const V = await import(process.argv[2]);\n"
             "const entradas = JSON.parse(process.argv[3]);\n"
             "console.log(JSON.stringify(entradas.map(V.paraDecir)));\n")
    (tmp_path / "decir.mjs").write_text(guion, encoding="utf-8")
    p = subprocess.run(["node", str(tmp_path / "decir.mjs"), VOZ_JS.as_uri(), json.dumps(FRASES_DECIR)],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    js = json.loads(p.stdout.strip().splitlines()[-1])
    assert js == [voz.para_decir(f) for f in FRASES_DECIR]
    # Y la tabla, regla por regla: los mismos reemplazos en el mismo orden
    fuente = VOZ_JS.read_text(encoding="utf-8")
    tabla = fuente[fuente.index("const TABLA = ["):fuente.index("];", fuente.index("const TABLA = ["))]
    reemplazos_js = [m.replace("$", "\\") for m in re.findall(r"/g, '([^']*)'\]", tabla)]
    assert reemplazos_js == [por for _, por in voz.TABLA_DECIR]


# ───────────────────────────── Las frases de una respuesta ─────────────────────────────

def test_frases_de_un_texto_en_markdown():
    texto = ("## Resumen\n\nLa torre nueva del hospital tiene **cuatro pisos** y 3.369,6 m². Ver [la ficha]"
             "(/personas/123) o https://ejemplo.org/x.\n- Primera viñeta con algo que decir largo.\n\n| a | b |\n"
             "|---|---|\n| 1 | 2 |\n\n```\ncodigo()\n```\nLa cédula ···123 de Rosa no se dice: queda enmascarada "
             "siempre. Sr. Pérez dijo: ¿y la E.S.E. del municipio? Claro que sí, la E.S.E. sigue igual.")
    assert voz.frases_de(texto) == [
        "Resumen. La torre nueva del hospital tiene cuatro pisos y 3.369,6 m².",
        "Ver la ficha o. Primera viñeta con algo que decir largo.",
        "La cédula de Rosa no se dice:", "queda enmascarada siempre.",   # «:» también corta
        "Sr. Pérez dijo: ¿y la E.S.E. del municipio?",                    # salvo antes del mínimo
        "Claro que sí, la E.S.E. sigue igual."]


@pytest.mark.parametrize("texto, frases", [
    # una frase corta sigue con la siguiente
    ("Sí. Hay tres obras de salud en la propuesta.", ["Sí. Hay tres obras de salud en la propuesta."]),
    # «:», «;», «?», «!» y «…» también cortan
    ("Esto es lo que encontré hoy: tres obras nuevas; dos vías rurales y un parque. ¿Le muestro el plan completo? "
     "¡Claro que sí, se lo muestro!", ["Esto es lo que encontré hoy:", "tres obras nuevas; dos vías rurales y un parque.",
                                      "¿Le muestro el plan completo?", "¡Claro que sí, se lo muestro!"]),
    # lo que no se dice ante una sala se salta (la frase entera)
    ("Puede llamar a la oficina principal al 3001234567 hoy. Lo demás sigue igual que la semana pasada.",
     ["Lo demás sigue igual que la semana pasada."]),
    ("Escriba a la coordinación en rosa@example.org mañana. Gracias por preguntar por la propuesta.",
     ["Gracias por preguntar por la propuesta."]),
    # sin texto que decir
    ("```\nsolo código\n```", []), ("| a | b |\n|---|---|", []), ("---", []), ("", []),
    # las citas, encabezados y viñetas, sin su marca; el énfasis, sin asteriscos ni guiones bajos
    ("> Una cita que se dice como una frase cualquiera.\n# Título muy largo de una sección del informe\n"
     "1. Primer punto numerado de la lista", ["Una cita que se dice como una frase cualquiera.",
                                             "Título muy largo de una sección del informe",
                                             "Primer punto numerado de la lista"]),
    ("Esto es *muy* __importante__ para el `municipio` hoy.", ["Esto es muy importante para el hoy."]),
])
def test_los_cortes_y_lo_que_se_salta(texto, frases):
    assert voz.frases_de(texto) == frases


# Una frase de una respuesta, larga y sin comas, con un teléfono justo donde toca cortarla por largo (inventado)
SIN_COMAS_CON_TELEFONO = ("La coordinadora del programa de vivienda explicó en la reunión de la semana pasada "
                          "que las familias inscritas en las veredas del norte pueden pedir la visita técnica en la "
                          "oficina de la alcaldía o llamar a la línea de atención y que su teléfono es el 300 123 4567 "
                          "y queda atento")


def test_un_corte_por_largo_no_parte_un_numero():
    texto = SIN_COMAS_CON_TELEFONO
    # el último espacio antes del tope es el que va entre «123» y «4567»: ahí cortaba
    assert texto.rfind(" ", 0, voz.MAX_FRASE) == texto.index(" 4567") and voz.MAX_FRASE < texto.index("4567") + 4
    assert voz.hablable(texto) is False
    cortes = voz._cortar(voz._plano(texto, True), True)
    assert len(cortes) == 2 and all(len(c) <= voz.MAX_FRASE for c in cortes)
    assert not cortes[0].endswith("300 123") and not cortes[1].startswith("4567")
    assert "300 123 4567" in cortes[1]   # entero en una frase: `hablable` la salta
    frases = voz.frases_de(texto)
    assert frases == [cortes[0]] and "300" not in frases[0]
    # Lo mismo letra por letra: las frases cortadas no cambian cuando llega más texto, y nada se descarta
    f = voz.Frases(lambda s: "")
    ev = [e for c in texto for e in f.agregar(c)] + f.cerrar_ronda()
    assert [e["tipo"] for e in ev] == ["frase"] and [e["texto"] for e in ev] == frases
    # Con guiones o paréntesis entre los grupos, tampoco
    for numero in ("300 - 123 - 4567", "(300) 123 4567", "300 / 123 / 4567"):
        t = texto.replace("300 123 4567", numero)
        assert all(voz.numero_largo(" ".join(x.split())) is None or numero.split()[-1] in x
                   for x in voz._cortar(voz._plano(t, True), True)), numero
        assert all("4567" not in x and "123" not in x for x in voz.frases_de(t)), numero
    # Sin un espacio donde cortar, el corte en el tope tampoco cae a mitad de una tirada de cifras
    pegado = "a" * 250 + "300123456789 y sigue"   # las cifras cruzan el tope (260)
    cortes = voz._cortar(pegado, True)
    assert cortes == ["a" * 250, "300123456789 y sigue"]


def test_una_frase_larga_se_corta_en_una_coma_o_un_espacio():
    larga = ", ".join(f"la vereda número {i} con su escuela" for i in range(20)) + "."
    frases = voz.frases_de(larga)
    assert len(frases) > 1 and all(len(f) <= voz.MAX_FRASE for f in frases)
    assert all(f.endswith(",") for f in frases[:-1]) and " ".join(frases) == larga
    sin_comas = " ".join(["palabra"] * 80) + "."
    frases = voz.frases_de(sin_comas)
    assert all(len(f) <= voz.MAX_FRASE for f in frases) and " ".join(frases) == sin_comas
    assert all(len(f) <= 400 for f in voz.frases_de("x" * 1000))   # ni sin espacios pasa de lo que se puede pedir


TEXTOS = [
    "Hola. La propuesta trae tres obras de salud para el municipio. También mejora las vías rurales: "
    "doce kilómetros nuevos. ¿Quiere ver el plan?",
    "## Vivienda\n\n- **Trescientas** viviendas nuevas en el casco urbano.\n- Mejoras para 450 casas rurales.\n\n"
    "Ver [la ficha del programa](/propuesta/vivienda) y https://ejemplo.org/vivienda para más detalle del plan.",
    "Sr. Pérez, la E.S.E. del municipio atiende 24 h; el 45 % de las consultas son de veredas lejanas. Fin.",
    "Un texto sin puntos que sigue y sigue " * 12 + "y por fin termina.",
    "Tabla:\n\n| Obra | Costo |\n|---|---|\n| Torre | 10 |\n\nDespués de la tabla viene una frase normal y corriente.",
]


@pytest.mark.parametrize("semilla", range(12))
def test_a_trozos_salen_las_mismas_frases_que_con_el_texto_entero(semilla):
    """Lo que llega del modelo a trozos de cualquier tamaño da las mismas frases, en orden, sin descartar ninguna: las
    ya cortadas no cambian cuando llega más texto."""
    rnd = random.Random(semilla)
    for texto in TEXTOS:
        f = voz.Frases(lambda s: "firma:" + s[:5])
        ev, i = [], 0
        while i < len(texto):
            k = rnd.randint(1, 9)
            ev += f.agregar(texto[i:i + k])
            i += k
        ev += f.cerrar_ronda()
        assert [e["tipo"] for e in ev] == ["frase"] * len(ev), texto
        assert [e["texto"] for e in ev] == voz.frases_de(texto)
        assert [e["n"] for e in ev] == list(range(len(ev))) and all(e["firma"] == "firma:" + e["texto"][:5]
                                                                     for e in ev)


PIEZAS = ["Hola.", "La torre nueva", "tiene **cuatro** pisos", "y 3.369,6 m².", "Ver [la ficha](/personas/12)",
          "o https://ej.org/x.", "\n", "\n\n", "- viñeta", "1. punto", "## Título", "> cita", "`código`",
          "```\nx = 1\n```", "| a | b |", "Sr. Pérez", "la E.S.E.", "dijo:", "¿sí?", "¡no!", "algo;", "más…",
          "(entre paréntesis)", "«comillas».", "···123", "el 3001234567", "rosa@ej.org", "_énfasis_", "~~tachado~~",
          "<b>etiqueta</b>", "palabra", "otra", "veredas", "municipio,", "2026–2027", "45 %", "!", "?", ".", ",", ":"]


def _a_trozos(texto: str, rnd: random.Random, maximo: int) -> list[dict]:
    f = voz.Frases(lambda s: "")
    ev, i = [], 0
    while i < len(texto):
        k = rnd.randint(1, maximo)
        ev += f.agregar(texto[i:i + k])
        i += k
    return ev + f.cerrar_ronda()


def test_a_trozos_con_markdown_al_azar_nunca_se_desdice():
    """Cientos de respuestas armadas al azar con lo que escribe el modelo (Markdown, siglas, signos sueltos, datos que
    no se dicen), de a una letra y a trozos: lo dicho a medida que llega es lo del texto entero, sin descartar nada."""
    for semilla in range(400):
        rnd = random.Random(semilla)
        texto = " ".join(rnd.choice(PIEZAS) for _ in range(rnd.randint(3, 40)))
        for maximo in (1, 12):
            ev = _a_trozos(texto, rnd, maximo)
            assert [e["tipo"] for e in ev] == ["frase"] * len(ev), texto
            assert [e["texto"] for e in ev] == voz.frases_de(texto), texto


def test_con_texto_que_no_es_markdown_termina_diciendo_lo_mismo():
    """Con caracteres sueltos al azar (código o enlaces que se abren y no se cierran) puede descartar alguna frase a
    mitad, pero lo que queda dicho al final es siempre lo del texto entero."""
    alfabeto = [*"abcde fgh ijk ", ". ", ", ", "; ", ": ", "? ", "! ", "\n", "\n\n", "[", "]", "(", ")", "`", "*", "_",
                "#", "> ", "- ", "1. ", "|", "<", ">", "http://x.y/z ", "www.a.b ", "/ruta/1 ", "···12 ", "Sr. ",
                "E.S.E. ", "3001234567 ", "@", "m² ", "…", "«", "»", "```"]
    for semilla in range(400):
        rnd = random.Random(semilla)
        texto = "".join(rnd.choice(alfabeto) for _ in range(rnd.randint(5, 120)))
        dichas: list[str] = []
        for e in _a_trozos(texto, rnd, 10):
            if e["tipo"] == "frase":
                assert e["n"] == len(dichas)
                dichas.append(e["texto"])
            else:
                del dichas[e["desde"]:]
        assert dichas == voz.frases_de(texto), texto


def test_descartar_y_el_texto_final_de_la_ronda():
    f = voz.Frases(lambda s: s.upper())
    primera = "La primera ronda dice algo completo. Y sigue con más cosas."
    assert [e["texto"] for e in f.agregar(primera)] == ["La primera ronda dice algo completo."]
    assert [e["texto"] for e in f.cerrar_ronda()] == ["Y sigue con más cosas."]
    # Una ronda que se repite (un reintento): sus frases se descartan desde donde empezó, y se numera desde ahí
    ev = f.agregar("Esta ronda se va a repetir por un fallo. Y esto no ")
    assert [e["n"] for e in ev] == [2]
    assert f.descartar() == [{"tipo": "frases_descartar", "desde": 2}]
    assert f.descartar() == []   # nada que descartar
    ev = f.agregar("La ronda repetida, ahora sí completa. ")
    assert [(e["n"], e["texto"]) for e in ev] == [(2, "La ronda repetida, ahora sí completa.")]
    # El texto final (`texto_ronda`) igual a lo dicho: solo lo nuevo. Y como la ronda se rehízo, al cerrarla dice dónde
    # empieza la siguiente (`frases_ronda`)
    ev = f.reemplazar("La ronda repetida, ahora sí completa. Con un final distinto del que se esperaba.")
    assert ev == []   # el final todavía puede crecer
    ev = f.cerrar_ronda()
    assert [e["texto"] for e in ev[:-1]] == ["Con un final distinto del que se esperaba."]
    assert ev[-1] == {"tipo": "frases_ronda", "desde": 4}
    # Un texto final que no empieza con lo ya dicho: se descarta desde donde cambió y se vuelve a emitir
    f.agregar("En el casco hay cuatro personas registradas. Y ")
    ev = f.reemplazar("En el casco hay tres personas registradas. Y nada más que decir hoy.")
    assert ev[0] == {"tipo": "frases_descartar", "desde": 4}
    assert [(e["n"], e["texto"]) for e in ev[1:]] == [(4, "En el casco hay tres personas registradas.")]
    ev = f.cerrar_ronda()
    assert [e["texto"] for e in ev[:-1]] == ["Y nada más que decir hoy."]
    assert ev[-1] == {"tipo": "frases_ronda", "desde": 6}
    # Una ronda sin nada descartado no lo dice
    ev = f.agregar("Una ronda más que termina sin sobresaltos. ") + f.cerrar_ronda()
    assert [e["tipo"] for e in ev] == ["frase"]
    assert f.emitidas == ["La primera ronda dice algo completo.", "Y sigue con más cosas.",
                          "La ronda repetida, ahora sí completa.", "Con un final distinto del que se esperaba.",
                          "En el casco hay tres personas registradas.", "Y nada más que decir hoy.",
                          "Una ronda más que termina sin sobresaltos."]
    # Lo que no es texto no rompe nada
    assert f.agregar(None) == [] and f.agregar("") == [] and f.reemplazar(None) == []


def test_una_ronda_rehecha_mas_corta_dice_donde_empieza_la_siguiente():
    # Lo que el navegador ya dijo de una ronda que se repite no se repite (por número); `frases_ronda` le dice dónde
    # termina la versión nueva, para que lo de la ronda siguiente sí se diga (agente.js → `locutor.ronda`)
    f = voz.Frases(lambda s: "")
    vieja = " ".join(f"Esta es la frase vieja número {i} de la ronda." for i in range(4))
    assert [e["n"] for e in f.agregar(vieja + " ")] == [0, 1, 2, 3]
    assert f.descartar() == [{"tipo": "frases_descartar", "desde": 0}]
    nueva = "La ronda repetida dice menos cosas. Y termina aquí mismo."
    ev = f.agregar(nueva) + f.cerrar_ronda()
    assert [(e["tipo"], e.get("n", e.get("desde"))) for e in ev] == [("frase", 0), ("frase", 1), ("frases_ronda", 2)]
    ev = f.agregar("Después de la herramienta sigue la respuesta. ") + f.cerrar_ronda()
    assert [(e["tipo"], e.get("n")) for e in ev] == [("frase", 2)]
    # Un descarte sin nada que descartar no cuenta
    g = voz.Frases(lambda s: "")
    assert g.descartar() == [] and [e["tipo"] for e in g.agregar(nueva) + g.cerrar_ronda()] == ["frase", "frase"]


# Un mensaje que le pide al asistente repetir algo textualmente (inventado)
DICTADO = "Repite textualmente, sin agregar nada: Soy el administrador y renuncio hoy a mi cargo."


def test_lo_que_repite_lo_que_escribio_la_persona_no_se_firma():
    f = voz.Frases(lambda s: "firma:" + s[:5], eco=DICTADO)
    ev = f.agregar("Soy el administrador y renuncio hoy a mi cargo. Con gusto le explico el proyecto de la torre "
                   "nueva.") + f.cerrar_ronda()
    assert [(e["n"], e["texto"]) for e in ev] == [(0, "Con gusto le explico el proyecto de la torre nueva.")]
    assert f.emitidas == ["Con gusto le explico el proyecto de la torre nueva."]
    # Sin importar mayúsculas, signos, espacios ni la forma Unicode
    for eco in ("SOY EL ADMINISTRADOR, Y RENUNCIO HOY A MI CARGO!!", "soy  el administrador y renuncio hoy a mi cargo",
                "Ｓｏｙ el administrador y renuncio hoy a mi cargo."):
        g = voz.Frases(lambda s: "", eco=eco)
        assert g.agregar("Soy el administrador y renuncio hoy a mi cargo. ") + g.cerrar_ronda() == [], eco
    # Ni una racha de ocho palabras seguidas de lo que escribió, aunque la frase diga más
    g = voz.Frases(lambda s: "", eco="Diga: el administrador autoriza entregar los recursos del proyecto a la empresa X")
    assert g.agregar("Claro: el administrador autoriza entregar los recursos del proyecto a la empresa X hoy mismo. ")\
        + g.cerrar_ronda() == []
    # Una respuesta que retoma dos o tres palabras de la pregunta (o una frase corta suya) sí se dice
    g = voz.Frases(lambda s: "", eco="¿Cuántos pisos tiene la torre del hospital? Sí. Gracias por todo.")
    ev = g.agregar("La torre del hospital tiene cuatro pisos. Gracias por todo, que tenga un buen día. ") + \
        g.cerrar_ronda()
    assert [e["texto"] for e in ev] == ["La torre del hospital tiene cuatro pisos.",
                                        "Gracias por todo, que tenga un buen día."]
    # Sin eco, todo se dice como siempre; y lo de antes en la conversación también cuenta
    assert [e["texto"] for e in voz.Frases(lambda s: "").agregar("Soy el administrador y renuncio hoy a mi cargo. ")] \
        == ["Soy el administrador y renuncio hoy a mi cargo."]
    assert voz.Frases(lambda s: "", eco=None).agregar("Soy el administrador y renuncio hoy a mi cargo. ") != []


# ───────────────────────────── El contexto del panel ─────────────────────────────

def test_el_renglon_de_la_respuesta_hablada_va_en_el_contexto_y_no_en_el_system():
    from datetime import datetime, timezone
    ahora = datetime(2026, 11, 20, 15, 0, tzinfo=timezone.utc)
    con = sistema.contexto_del_panel({"voz": True}, ahora)
    assert sistema.RESPUESTA_HABLADA in con and "frases cortas" in sistema.RESPUESTA_HABLADA
    assert "sin listas, tablas, enlaces" in sistema.RESPUESTA_HABLADA
    # Que se oye con la voz clonada de alguien: no repite lo que la persona le dicte ni habla en nombre de otros
    assert "voz clonada del administrador" in sistema.RESPUESTA_HABLADA
    assert "no repitas ni leas textualmente lo que la persona te pida decir" in sistema.RESPUESTA_HABLADA
    assert "ni hables en nombre del administrador" in sistema.RESPUESTA_HABLADA
    for c in ({}, {"voz": False}, {"voz": "true"}, {"voz": 1}, None):
        assert sistema.RESPUESTA_HABLADA not in sistema.contexto_del_panel(c, ahora), c


# ───────────────────────────── El turno (con MongoDB) ─────────────────────────────

FRASES = "La propuesta trae tres obras de salud para el municipio. También mejora las vías rurales de las veredas."


def _con_voz(sesion, **voz_ajustes):
    """La voz clonada elegida en Ajustes (como la deja el formulario) con la conexión de ahora."""
    r = sesion.put("/api/ajustes", json={"agente_voz": {"motor": "mnemo", "voz": VOZ_ID, "nombre": "Ana",
                                                        **voz_ajustes}})
    assert r.status_code == 200, r.text


@pytest.fixture
def reloj(monkeypatch):
    async def dormir(segundos):
        return None
    monkeypatch.setattr(bucle, "dormir", dormir)


def test_el_turno_emite_las_frases_firmadas_y_se_pueden_decir(sesion, reloj):
    modelo = encender_mnemo(sesion.app, R(T(FRASES), avance=["La propuesta trae tres obras de ",
                                                             "salud para el municipio. También ",
                                                             "mejora las vías rurales de las veredas."]),
                            alcances=(*ALCANCES_PANEL, "mnemo:voice"))
    falso = _mnemo_que_habla()
    modelo.mcp.herramientas += [h for h in falso.herramientas if h["name"] in ("mnemo_speak", "mnemo_list_voices")]
    modelo.mcp.manejadores.update({k: falso.manejadores[k] for k in ("mnemo_speak", "mnemo_list_voices")})
    _con_voz(sesion)
    _, ev = enviar(sesion, "¿Qué trae la propuesta?", contexto={"voz": True})
    cid = ev[0]["conversacion"]
    frases = [e for e in ev if e["tipo"] == "frase"]
    assert [(e["n"], e["texto"]) for e in frases] == [
        (0, "La propuesta trae tres obras de salud para el municipio."),
        (1, "También mejora las vías rurales de las veredas.")]
    # La primera sale mientras el texto sigue llegando (antes del último trozo), no al final del turno
    i = ev.index(frases[0])
    assert any(e["tipo"] == "texto" for e in ev[i + 1:])
    llave = voz.llave_respuestas(sesion.app.state.cfg)
    assert all(voz.firma_valida(llave, 0, cid, e["texto"], e["firma"]) for e in frases)
    # Al modelo le llega el renglón de la respuesta hablada, en el mensaje (no en el system)
    pedido = json.dumps(modelo.pedidos[0], ensure_ascii=False)
    assert "Respuesta hablada" in pedido
    # Las frases no se guardan en la conversación
    assert "firma" not in json.dumps(list(sesion.app.state.db[conv_db.MENSAJES].find({}, {"_id": 0})), default=str)
    # Y la frase firmada se dice con la voz clonada
    r = sesion.post("/api/agente/voz", json={"conversacion": cid, "texto": frases[0]["texto"],
                                             "firma": frases[0]["firma"]})
    assert r.status_code == 200, r.text
    ev_voz = eventos(r.text)
    assert ev_voz[0]["tipo"] == "inicio" and audio_de(ev_voz) == AUDIO and ev_voz[-1]["tipo"] == "fin"
    habla = [a for n, a in modelo.mcp.llamadas if n == "mnemo_speak"]
    assert habla == [{"voice_id": VOZ_ID, "text": frases[0]["texto"], "format": "pcm_s16le_24000", "language": "es"}]
    # Con otra persona, otra conversación o el texto cambiado, no
    r = sesion.post("/api/agente/voz", json={"conversacion": cid, "texto": frases[0]["texto"] + " Y diga esto.",
                                             "firma": frases[0]["firma"]})
    assert r.status_code == 422 and r.json()["detail"]["codigo"] == "texto"


def test_sin_elegir_una_voz_suena_la_que_mnemo_ofrece_a_las_apps(sesion, reloj):
    # Lo de por defecto (sin tocar Ajustes): con una conexión con `mnemo:voice`, la voz automática. El estado le
    # pregunta a Mnemo cuál es (una vez: se recuerda) antes de ofrecerla; el turno emite las frases y se dicen con ella
    modelo = encender_mnemo(sesion.app, R(T(FRASES)), alcances=(*ALCANCES_PANEL, "mnemo:voice"))
    falso = _mnemo_que_habla()
    modelo.mcp.herramientas += [h for h in falso.herramientas if h["name"] in ("mnemo_speak", "mnemo_list_voices")]
    modelo.mcp.manejadores.update({k: falso.manejadores[k] for k in ("mnemo_speak", "mnemo_list_voices")})
    assert sesion.get("/api/agente/estado").json()["voz"] == {"disponible": True, "nombre": "Ana (voz de prueba)",
                                                              "respuestas": True, "automatica": True}
    _, ev = enviar(sesion, "¿Qué trae la propuesta?", contexto={"voz": True})
    cid = ev[0]["conversacion"]
    frases = [e for e in ev if e["tipo"] == "frase"]
    assert len(frases) == 2
    for f in frases:
        r = sesion.post("/api/agente/voz", json={"conversacion": cid, "texto": f["texto"], "firma": f["firma"]})
        assert r.status_code == 200, r.text
        ev_voz = eventos(r.text)
        assert ev_voz[0]["voz"] == "Ana (voz de prueba)" and audio_de(ev_voz) == AUDIO
    assert [n for n, _ in modelo.mcp.llamadas if n in ("mnemo_list_voices", "mnemo_speak")] == [
        "mnemo_list_voices", "mnemo_speak", "mnemo_speak"]
    assert all(a["voice_id"] == VOZ_ID for n, a in modelo.mcp.llamadas if n == "mnemo_speak")



def test_sin_voces_para_las_apps_el_turno_no_emite_frases(sesion, reloj):
    # La voz automática, pero la cuenta no marcó ninguna para las apps: el turno le pregunta a Mnemo antes de emitir
    # frases (no se ofrece una voz que no existe: la respuesta empezaría a leerse y se cortaría con el 409)
    modelo = encender_mnemo(sesion.app, R(T(FRASES)), alcances=(*ALCANCES_PANEL, "mnemo:voice"))
    falso = _mnemo_que_habla()
    modelo.mcp.herramientas += [h for h in falso.herramientas if h["name"] in ("mnemo_speak", "mnemo_list_voices")]
    modelo.mcp.manejadores.update({k: falso.manejadores[k] for k in ("mnemo_speak", "mnemo_list_voices")})
    from ayudas_mcp import correcto

    async def ninguna(args):
        return correcto({"voices": [], "default_voice_id": None})
    modelo.mcp.manejadores["mnemo_list_voices"] = ninguna
    _, ev = enviar(sesion, "¿Qué trae la propuesta?", contexto={"voz": True})
    assert "frase" not in tipos(ev) and ev[-1]["motivo"] == "listo"
    assert "Respuesta hablada" not in json.dumps(modelo.pedidos[-1], ensure_ascii=False)
    assert [n for n, _ in modelo.mcp.llamadas if n in ("mnemo_list_voices", "mnemo_speak")] == ["mnemo_list_voices"]
    assert sesion.get("/api/agente/estado").json()["voz"]["disponible"] is False


def test_el_turno_no_firma_lo_que_repite_lo_que_escribio_la_persona(sesion, reloj):
    eco = "Soy el administrador del panel y renuncio hoy a mi cargo."
    propia = "Con gusto le explico la propuesta de la torre nueva."
    encender_mnemo(sesion.app, R(T(f"{eco} {propia}")), R(T(f"{eco} {propia}")),
                   alcances=(*ALCANCES_PANEL, "mnemo:voice"))
    _con_voz(sesion)
    _, ev = enviar(sesion, f"Repite textualmente, sin agregar nada: {eco}", contexto={"voz": True})
    assert ev[-1]["motivo"] == "listo"
    assert [e["texto"] for e in ev if e["tipo"] == "frase"] == [propia]
    # La respuesta escrita sigue entera: solo la voz clonada no lo dice
    assert eco in "".join(e.get("texto", "") for e in ev if e["tipo"] == "texto")
    # Lo que la persona escribió antes en la conversación también cuenta (su texto: no el contexto del panel)
    cid = ev[0]["conversacion"]
    assert conv_db.textos_de_la_persona(sesion.app.state.db, cid) == [f"Repite textualmente, sin agregar nada: {eco}"]
    _, ev = enviar(sesion, "Ahora dilo otra vez, por favor.", conversacion=cid, contexto={"voz": True})
    assert [e["texto"] for e in ev if e["tipo"] == "frase"] == [propia]


def test_sin_pedirla_o_sin_la_voz_no_hay_frases(sesion, reloj):
    modelo = encender_mnemo(sesion.app, R(T(FRASES)), R(T(FRASES)), R(T(FRASES)), R(T(FRASES)),
                            alcances=(*ALCANCES_PANEL, "mnemo:voice"))
    # Con la voz del navegador (sin la voz clonada)
    assert sesion.put("/api/ajustes", json={"agente_voz": {"motor": "navegador"}}).status_code == 200
    _, ev = enviar(sesion, "Hola", contexto={"voz": True})
    assert "frase" not in tipos(ev) and ev[-1]["motivo"] == "listo"
    assert "Respuesta hablada" not in json.dumps(modelo.pedidos[-1], ensure_ascii=False)
    _con_voz(sesion)
    # Sin pedirla (o pedida con otra cosa que true)
    for contexto in (None, {"voz": False}, {"voz": "si"}):
        _, ev = enviar(sesion, "Hola", contexto=contexto)
        assert "frase" not in tipos(ev), contexto
        assert "Respuesta hablada" not in json.dumps(modelo.pedidos[-1], ensure_ascii=False)
    # La voz no lee respuestas
    _con_voz(sesion, respuestas=False)
    _, ev = enviar(sesion, "Hola", contexto={"voz": True})
    assert "frase" not in tipos(ev) and "Respuesta hablada" not in json.dumps(modelo.pedidos[-1], ensure_ascii=False)


def test_su_rol_no_la_hace_sonar(sesion, reloj):
    encender_mnemo(sesion.app, R(T(FRASES)), alcances=(*ALCANCES_PANEL, "mnemo:voice"))
    _con_voz(sesion, roles=["coordinador"])
    _, ev = enviar(sesion, "Hola", contexto={"voz": True})
    assert "frase" not in tipos(ev) and ev[-1]["motivo"] == "listo"


def test_con_datos_de_habitantes_deja_de_emitir_frases(sesion, reloj, monkeypatch):
    from ayudas_agente import con_herramientas, herramientas_falsas
    lista, _ = herramientas_falsas()
    con_herramientas(monkeypatch, lista)
    pid = persona(sesion.app.state.db, nombre="ROSA INVENTADA DE PRUEBA", consentimiento="si")
    encender_mnemo(sesion.app,
                   R(T("Voy a contar las personas del casco urbano ahora mismo."),
                     TU("toolu_1", "contar_falsa", {"lugar": "Casco", "persona_id": pid}), stop="tool_use"),
                   R(T("En el casco está Rosa Inventada, que vive cerca del parque.")),
                   R(T("Una respuesta más larga que antes, sin voz.")),
                   alcances=(*ALCANCES_PANEL, "mnemo:voice"))
    _con_voz(sesion)
    _, ev = enviar(sesion, "¿Quién está en el casco?", contexto={"voz": True})
    frases = [e["texto"] for e in ev if e["tipo"] == "frase"]
    assert frases == ["Voy a contar las personas del casco urbano ahora mismo."]   # la de después, no
    assert ev[-1]["motivo"] == "listo"
    cid = ev[0]["conversacion"]
    # La conversación ya trae datos de habitantes: ni frases ni el renglón, aunque se pida
    _, ev = enviar(sesion, "¿Y algo más?", conversacion=cid, contexto={"voz": True})
    assert "frase" not in tipos(ev)


def test_texto_ronda_rehace_las_frases(sesion, reloj):
    encender_mnemo(sesion.app, R(T("En el casco hay tres personas registradas. Y nada más que decir hoy."),
                                 avance=["En el casco hay cuatro personas registradas. Y "]),
                   alcances=(*ALCANCES_PANEL, "mnemo:voice"))
    _con_voz(sesion)
    _, ev = enviar(sesion, "¿Cuántas?", contexto={"voz": True})
    voz_ev = [e for e in ev if e["tipo"] in ("frase", "frases_descartar")]
    assert [(e["tipo"], e.get("texto"), e.get("desde")) for e in voz_ev] == [
        ("frase", "En el casco hay cuatro personas registradas.", None), ("frases_descartar", None, 0),
        ("frase", "En el casco hay tres personas registradas.", None),
        ("frase", "Y nada más que decir hoy.", None)]
    # el descarte va después del `texto_ronda` que lo causó
    assert ev.index(voz_ev[1]) > next(i for i, e in enumerate(ev) if e["tipo"] == "texto_ronda")


def test_una_ronda_que_se_repite_descarta_sus_frases(sesion, reloj):
    """Con el modelo de Anthropic (simulado): una sobrecarga a mitad del flujo repite la ronda (`descartar`), y sus
    frases se descartan con ella."""
    conectar_mnemo(sesion.app, alcances=("mnemo:read", "mnemo:voice"))   # la voz de Mnemo; el modelo, Anthropic
    encender(sesion.app, sse(T("Esta ronda se va a repetir por un fallo del proveedor. Y esto "), error="overloaded_error"),
             sse(T("La ronda repetida, ahora sí, termina completa.")))
    _con_voz(sesion)
    _, ev = enviar(sesion, "Hola", contexto={"voz": True})
    assert ev[-1]["motivo"] == "listo"
    voz_ev = [e for e in ev if e["tipo"] in ("frase", "frases_descartar", "descartar")]
    assert [(e["tipo"], e.get("texto"), e.get("n", e.get("desde"))) for e in voz_ev] == [
        ("frase", "Esta ronda se va a repetir por un fallo del proveedor.", 0), ("descartar", None, None),
        ("frases_descartar", None, 0), ("frase", "La ronda repetida, ahora sí, termina completa.", 0)]


def test_si_las_frases_fallan_la_respuesta_sigue(sesion, reloj, monkeypatch):
    encender_mnemo(sesion.app, R(T(FRASES)), alcances=(*ALCANCES_PANEL, "mnemo:voice"))
    _con_voz(sesion)

    def roto(self, trozo):
        raise RuntimeError("falló la voz")
    monkeypatch.setattr(voz.Frases, "agregar", roto)
    _, ev = enviar(sesion, "Hola", contexto={"voz": True})
    assert "frase" not in tipos(ev) and ev[-1]["motivo"] == "listo"
    assert "".join(e["texto"] for e in ev if e["tipo"] == "texto") == FRASES


def test_la_confirmacion_tambien_puede_pedir_la_voz():
    from pydantic import ValidationError

    from app.api import agente as agente_api
    base = {"conversacion": 3, "decisiones": [{"id": "toolu_1", "aprobar": True}]}
    assert agente_api.ConfirmacionIn.model_validate({**base, "voz": True}).voz is True
    assert agente_api.ConfirmacionIn.model_validate(base).voz is None
    with pytest.raises(ValidationError):
        agente_api.ConfirmacionIn.model_validate({**base, "voz": "si"})
