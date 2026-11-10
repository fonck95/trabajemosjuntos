"""Regresiones del cierre del asistente: lo que las dos revisiones del remate dejaron abierto y los pendientes que
quedaron entre dueños (docs/agente.md).

* El filtro de etiqueta de la vista llega al modelo si la etiqueta existe y no es sensible (antes no llegaba nunca).
* buscar_personas dice que `q` busca solo en el nombre cuando unas palabras no encuentran a nadie, y un número con
  letras («CARRERA 5») explica que la búsqueda no mira la dirección: antes respondía 0 sin avisar y el modelo
  concluía que no había nadie.
* equipo vuelve a dar lo que hizo cada usuario, los totales y el avance por lugar, sin contar a quien no autorizó el
  tratamiento de sus datos (`tratables=1` en Usuarios): ni lo que se hizo con esa persona ni ella cambian lo que recibe
  el modelo.
* La tarjeta de aprobación no ofrece datos con caracteres que el navegador pinta sin ancho: los selectores de
  variante fuera de un emoji, los de Mongolia, las vocales inherentes jemer, los sin asignar y los de uso privado. La
  de Mnemo muestra lo que se manda: ni cambia los caracteres de control por espacios ni recorta el nombre de un
  argumento.
* Lo pendiente que se guardó con una versión anterior del panel (la tarjeta cortaba cada valor a 500 caracteres sin
  marcarlo) no se aprueba: el widget no ofrece «Aprobar» y el servidor lo rechaza.
* De quien no autorizó, al planillero y al consultor les llega su barrio o vereda del nomenclátor.
* crear_persona y editar_persona no dicen de quién es la cédula de quien no autorizó, ni traen a quien no autorizó por
  coincidir en un número (las parecidas del alta).
* Si una de las parecidas que devuelve crear_persona deja de autorizar mientras la API las arma, la conversación se
  borra antes de que su fila llegue al modelo.
* Pendientes entre dueños: el tablero cuenta los asistentes de las reuniones recientes sin quien no autorizó cuando lo
  pide el asistente (`tratables`), y «Cómo se usa» dice lo que no viaja del contexto como «Privacidad».

Cada prueba falla sin su arreglo, salvo las que cuidan que el arreglo no se pase de la raya (lo dicen en su
docstring). La Messages API va simulada: nunca se llama a Anthropic ni a Mnemo. Solo datos inventados."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

import ayudas_agente as aa
from ayudas_agente import T, TU, decidir, encender, enviar, sse
from ayudas_g3 import autorizada, persona
from test_remate_herramientas import (CEDULA_MARTA, CEDULA_ROSA, FILA_NO_AUTORIZO, TEL_MARTA,  # noqa: F401
                                      _acercamiento, _ej, _ids, _vereda, _visto, ctx_de, gente)
from test_remate_nucleo import VISIBLES, _revocar, falsas  # noqa: F401 - `falsas` es un fixture

from app import acceso, modelo
from app import db as bd
from app.agente import bucle
from app.agente import conversaciones as conv_db
from app.agente.herramientas import mnemo as hm
from app.agente.herramientas.base import Confirmacion, ErrorHerramienta
from app.api import personas as api_personas
from test_agente_mapa import requiere_node

RAIZ = Path(__file__).resolve().parents[1]


def _contexto_enviado(api, i: int = -1) -> dict:
    """Los «Filtros de la URL» del contexto del panel del último mensaje de la petición `i` al modelo ({} si no hay)."""
    bloques = api.peticiones[i]["json"]["messages"][-1]["content"]
    texto = next(b["text"] for b in bloques if b.get("type") == "text" and "<contexto_del_panel>" in b["text"])
    linea = next((x for x in texto.split("\n") if x.startswith("Filtros de la URL: ")), None)
    return json.loads(linea.split(": ", 1)[1]) if linea else {}


# ───────────────────────────── 1. La etiqueta de la vista llega al modelo ─────────────────────────────

def test_la_etiqueta_de_la_vista_llega_al_modelo_si_existe_y_no_es_sensible(sesion):
    """Con Habitantes filtrado por Vivienda, «¿cuántas de estas están en la zona rural?» tiene que llegarle al modelo
    con la etiqueta: sin ella contesta sobre todas las personas de la zona rural. Una sensible (Líder comunitario) o
    una que no existe no van: con la ficha abierta desde esa lista dirían un dato sensible de esa persona."""
    db = sesion.app.state.db
    vivienda = db.etiquetas.find_one({"nombre": "Vivienda"})["_id"]
    lider = db.etiquetas.find_one({"nombre": "Líder comunitario"})["_id"]
    api = encender(sesion.app, sse(T("Son las de Vivienda.")), sse(T("Esa no la veo.")), sse(T("Tampoco.")))
    vista = {"ruta": "/personas", "vista": "personas"}
    r, ev = enviar(sesion, "¿Cuántas de estas están en la zona rural?",
                   contexto={**vista, "filtros": {"etiqueta": str(vivienda), "zona": "rural"}})
    assert r.status_code == 200 and ev[-1]["motivo"] == "listo", ev[-3:]
    assert _contexto_enviado(api) == {"etiqueta": str(vivienda), "zona": "rural"}
    cid = ev[0]["conversacion"]
    for etiqueta in (str(lider), "999999"):
        r, ev = enviar(sesion, "¿Y estas?", conversacion=cid,
                       contexto={**vista, "filtros": {"etiqueta": etiqueta, "zona": "rural"}})
        assert r.status_code == 200 and ev[-1]["motivo"] == "listo", ev[-3:]
        assert _contexto_enviado(api) == {"zona": "rural"}, etiqueta
    guardado = json.dumps(list(db[conv_db.MENSAJES].find({}, {"_id": 0})), ensure_ascii=False, default=str)
    assert f'"etiqueta": "{lider}"' not in guardado.replace('\\"', '"')


# ───────────────────────────── 2. buscar_personas dice que `q` busca solo en el nombre ─────────────────────────────

def test_buscar_por_palabras_que_no_son_de_un_nombre_dice_donde_busca(sesion, ctx_de):
    """El planillero en la calle pregunta por «los de la finca Los Almendros» o por «la carrera 5 # 10-20». La búsqueda
    del asistente mira solo el nombre: si las palabras no encuentran a nadie, el resultado lo dice (y cómo buscar por
    barrio o vereda), y un número con letras explica que la dirección no se busca. Antes respondía 0 sin más, y el
    modelo concluía que no había nadie, mientras Habitantes sí la mostraba."""
    db = sesion.app.state.db
    lugar = _vereda(db)
    rosa = persona(db, nombre="ROSA SIAUTORIZO INVENTADA", lugar_id=lugar, direccion="CARRERA 5 # 10-20",
                   direccion_norm="CARRERA 5 1020", lugar_texto="FINCA LOS ALMENDROS")
    autorizada(db, rosa)
    ctx = ctx_de(sesion)
    for entrada in ({"q": "LOS ALMENDROS"}, {"q": "FINCA ALMENDROS", "filtros": {"lugar_id": lugar}},
                    {"q": "ALMENDROS", "orden": "nombre"}):
        r = _ej(sesion, ctx, "buscar_personas", entrada)
        assert r.contenido["total"] == 0 and r.contenido["filas"] == [], entrada
        assert "solo en el nombre" in r.contenido["nota"] and "lugar_id" in r.contenido["nota"], entrada
    with pytest.raises(ErrorHerramienta) as e:
        _ej(sesion, ctx, "buscar_personas", {"q": "CARRERA 5"})
    assert e.value.codigo == "invalido" and "dirección" in e.value.mensaje
    # Por el nombre la encuentra, y entonces no hace falta la nota
    r = _ej(sesion, ctx, "buscar_personas", {"q": "ROSA SIAUTORIZO"})
    assert rosa in _ids(("ok", r.contenido)) and "nota" not in r.contenido


# ───────────────────────────── 3. equipo, sin contar a quien no autorizó ─────────────────────────────

def test_equipo_da_lo_que_hizo_cada_usuario_y_el_avance_sin_contar_a_quien_no_autorizo(sesion, como, ctx_de):
    """«¿Cómo va el equipo este mes?» y «¿cuántas fichas actualizó Juan?» vuelven a tener respuesta: por usuario, los
    bloques planillero y consultor, los totales que suman y, por vereda, las personas y sus porcentajes. Todo sin
    quienes no autorizaron (la API con `tratables=1`): que el equipo registre, vea, llame o ponga un teléfono equivocado
    a TERESA, que no autorizó, no cambia lo que recibe el modelo; en Usuarios del panel sí cuenta."""
    db, app = sesion.app.state.db, sesion.app
    lugar = _vereda(db)
    p = como("planillero", asignacion={"lugares": [lugar], "areas": []})
    c = como("consultor")
    qp = aa.quien_de(app, p.uid)

    def trabajo_con(pid: int) -> None:
        bd.auditar(db, qp, "crear", "persona", pid, {"nombre": "x"}, campos=["nombre"], completados=["cedula"])
        bd.auditar(db, qp, "asistencia", "persona", pid, {"reunion_id": 1})
        acceso.registrar_lecturas(db, qp, [pid], ficha=True)
        tel = {**modelo.telefono_nuevo("3209990000", "panel", agregado_por=p.uid), "estado": "equivocado"}
        db.personas.update_one({"_id": pid}, {"$push": {"telefonos": tel}})
        _acercamiento(db, c.uid, pid)

    rosa = persona(db, nombre="ROSA SIAUTORIZO INVENTADA", lugar_id=lugar, cedula="1023456789",
                   telefono="3104445566")
    autorizada(db, rosa)
    trabajo_con(rosa)
    ctx = ctx_de(sesion)
    antes = _visto(sesion, ctx, "equipo", {"avance": "lugar"})
    assert antes[0] == "ok", antes
    usuarios = {u["usuario"]: u for u in antes[1]["usuarios"]}
    plan, cons = usuarios[p.usuario]["planillero"], usuarios[c.usuario]["consultor"]
    assert (plan["creadas_netas"], plan["cedulas"], plan["asistencias"], plan["personas_vistas"]) == (1, 1, 1, 1)
    assert plan["calidad"]["telefonos_luego_equivocados"] == 1
    assert (cons["acercamientos"], cons["personas"], cons["contactadas"]) == (1, 1, 1)
    totales = antes[1]["totales"]
    assert (totales["creadas_netas"], totales["asistencias"], totales["acercamientos"]) == (1, 1, 1)
    fila = next(f for f in antes[1]["avance"]["filas"] if f["id"] == lugar)
    assert (fila["personas"], fila["pct_cedula"], fila["pct_telefono"]) == (1, 100, 100)
    assert p.usuario in fila["responsables"]
    # Lo mismo con TERESA, que no autorizó, en la misma vereda: el modelo recibe exactamente lo mismo
    teresa = persona(db, nombre="TERESA NOAUTORIZO INVENTADA", consentimiento="no", lugar_id=lugar,
                     cedula="71230001", telefono="3001230001")
    trabajo_con(teresa)
    assert _visto(sesion, ctx, "equipo", {"avance": "lugar"}) == antes
    # El panel cuenta a todos, como siempre
    panel = {u["usuario"]: u for u in sesion.get("/api/usuarios").json()}
    assert panel[p.usuario]["indicadores"]["planillero"]["creadas"] == 2
    assert panel[c.usuario]["indicadores"]["consultor"]["acercamientos"] == 2
    avance = next(f for f in sesion.get("/api/usuarios/avance").json()["filas"] if f["id"] == lugar)
    assert avance["personas"] == 2


# ───────────────────────────── 4. La tarjeta no ofrece lo que el navegador pinta sin ancho ───────────────────────────

OCULTO = "MARTA GOMEZ 3001112233 VIH"
VISIBLE = "Recordar la reunion del martes con la junta de accion comunal"


def _con_selectores(visible: str, oculto: str) -> str:
    """Cada byte de `oculto` como un selector de variante (VS1–VS256), hasta 4 tras cada letra de `visible`."""
    datos = oculto.encode()
    vs = "".join(chr(0xFE00 + b) if b < 16 else chr(0xE0100 + b - 16) for b in datos)
    return "".join(c + vs[i * 4:(i + 1) * 4] for i, c in enumerate(visible))


# Valores que Chromium pinta igual con y sin los caracteres del medio (rev-remate-priv/invisibles.mjs)
INVISIBLES = {
    "selectores de variante": _con_selectores(VISIBLE, OCULTO),
    "sin asignar ignorables": "Recordar la reunion" + "".join(chr(0xE01F0 + b) for b in OCULTO.encode()),
    "etiqueta sin asignar": "Hola" + "\U000e0000" * 50,
    "reservado de formato": "Hola⁥ mundo",
    "especiales sin asignar": "Hola￰￸ mundo",
    "vocales inherentes jemer": "Hola឴឵ mundo",
    "selector de Mongolia": "Hola᠋᠌᠍᠏ mundo",
    "selector tras una letra": "Hola️ mundo",
    "selector de texto tras una letra": "Hola︎ mundo",
    "dos selectores tras un emoji": "Te quiero ❤️️",
    "selector tras un dígito sin keycap": "Llamar al 3️00",
    "uso privado": "Hola mundo",
    "uso privado de los planos altos": "Hola\U000f0000 mundo",
}


@pytest.mark.parametrize("caso", sorted(INVISIBLES))
def test_la_tarjeta_no_ofrece_caracteres_que_se_pintan_sin_ancho(caso):
    """Antes `_se_ve_como_es` dejaba pasar los selectores de variante (hasta 4 por letra) y los sin asignar (sin
    tope): en una nota que se ve como VISIBLE iba escondido OCULTO, un byte por carácter."""
    with pytest.raises(ErrorHerramienta) as e:
        bucle._tarjeta(Confirmacion("Agregar una nota", [("Persona", "#1"), ("Nota", INVISIBLES[caso])]))
    assert e.value.codigo == "oculto" and not e.value.fatal


def test_los_emojis_con_su_selector_se_siguen_ofreciendo():
    """Cuida que el arreglo no se pase de la raya (pasa también sin él): un selector de variante justo después de un
    símbolo, o en un keycap, es parte del emoji y se ve."""
    emojis = ["Hecho ✔️", "©️ 2026", "#️⃣ Uno", "☀︎ de texto", "Listo \U0001f44d"]
    t = bucle._tarjeta(Confirmacion("Escribir", [(f"Dato {i}", v) for i, v in enumerate([*VISIBLES, *emojis])]))
    assert [v for _, v in t["detalle"]] == [*VISIBLES, *emojis]


def test_una_nota_con_datos_en_selectores_de_variante_no_se_propone(sesion, falsas):  # noqa: F811
    """De punta a punta: la nota que se ve como VISIBLE y lleva OCULTO en selectores de variante no llega a la tarjeta,
    y el modelo recibe el error `oculto`. Antes se proponía, se aprobaba y quedaba en la ficha."""
    db = sesion.app.state.db
    pid = persona(db, nombre="ANA INVENTADA DE PRUEBA", consentimiento="si")
    api = encender(sesion.app, sse(TU("toolu_inv", "nota_falsa", {"persona_id": pid,
                                                                  "texto": _con_selectores(VISIBLE, OCULTO)}),
                                   stop="tool_use"), sse(T("La escribo sin esos caracteres.")))
    _, ev = enviar(sesion, "Agrega la nota")
    assert not [e for e in ev if e["tipo"] == "confirmar"] and ev[-1]["motivo"] == "listo", ev[-3:]
    res = [b for b in api.peticiones[-1]["json"]["messages"][-1]["content"] if b.get("type") == "tool_result"]
    assert res[0]["is_error"] and json.loads(res[0]["content"])["error"]["codigo"] == "oculto"
    assert db[conv_db.CONVERSACIONES].find_one({"_id": ev[0]["conversacion"]})["pendiente"] is None
    assert falsas == []


# ───────────────────────────── 5. La tarjeta de Mnemo muestra lo que se manda ─────────────────────────────

MNEMO = {"name": "mnemo_save_memory", "title": "Guardar memoria", "annotations": {},
         "inputSchema": {"type": "object", "properties": {"content": {"type": "string"}}}}


def test_la_tarjeta_de_mnemo_no_cambia_los_controles_ni_recorta_los_nombres():
    """`mnemo._valor` cambiaba los caracteres de control por espacios solo en la tarjeta (a Mnemo iban con los
    controles), y el nombre de un argumento se recortaba a 80 caracteres en la tarjeta y se mandaba entero. Ahora la
    tarjeta lleva lo que se manda, y si eso no se ve como es (`oculto`) o no cabe (`no_cabe`), no se ofrece."""
    valor = "Reunión con la JAC el lunes\x1b[8m\x08\x7f\x0c fin"
    with pytest.raises(ErrorHerramienta) as e:
        bucle._tarjeta(hm.confirmacion(MNEMO, {"content": valor}))
    assert e.value.codigo == "oculto"
    assert hm._argumentos({"content": valor}, MNEMO["inputSchema"])["content"] == valor
    largo = "titulo_" + "x" * 90 + "_FIN_OCULTO"
    with pytest.raises(ErrorHerramienta) as e:
        bucle._tarjeta(hm.confirmacion(MNEMO, {"content": "hola", largo: "valor"}))
    assert e.value.codigo == "no_cabe"
    # Una etiqueta se pinta sin conservar los espacios: con dos seguidos, o con un salto, no se vería como es
    for clave in ("titulo  doble", "titulo\nsalto", " titulo"):
        with pytest.raises(ErrorHerramienta) as e:
            bucle._tarjeta(hm.confirmacion(MNEMO, {"content": "hola", clave: "valor"}))
        assert e.value.codigo == "oculto", repr(clave)
    # Lo que se ve como es va entero, también una etiqueta de 80 caracteres y un valor con saltos de línea
    clave80 = "c" * bucle.TARJETA_ETIQUETA
    t = bucle._tarjeta(hm.confirmacion(MNEMO, {"content": "Línea 1\nLínea 2", clave80: "x"}))
    assert t["detalle"] == [["content", "Línea 1\nLínea 2"], [clave80, "x"]]


# ───────────────────────────── 6. Lo pendiente de la versión anterior no se aprueba ─────────────────────────────

NOTA_LARGA = "Visita sin novedad. " * 25 + "OCULTO: llamar al 3001112233, tiene VIH"  # 539 caracteres


def _como_lo_guardaba_412c3a5(db, cid: int) -> None:
    """Lo pendiente como lo dejaba la versión en producción: cada valor cortado a 500 caracteres (`str(v)[:500]`) y
    sin la marca de que la tarjeta muestra los valores enteros."""
    c = db[conv_db.CONVERSACIONES].find_one({"_id": cid})
    pend = conv_db.de_json(c["pendiente"])
    for ll in pend["llamadas"]:
        t = ll["confirmacion"]
        ll["confirmacion"] = {"titulo": t["titulo"], "detalle": [[k, str(v)[:500]] for k, v in t["detalle"]][:30],
                              "aviso": t["aviso"]}
    db[conv_db.CONVERSACIONES].update_one({"_id": cid}, {"$set": {"pendiente": conv_db.a_json(pend)}})


def test_lo_pendiente_guardado_por_la_version_anterior_no_se_aprueba(sesion, falsas):  # noqa: F811
    """Tras desplegar, lo que quedó pendiente con la versión anterior se veía entero (el widget no sabe que llegó
    cortado) y aprobarlo escribía la entrada completa: el final de la nota que la tarjeta no mostraba. Ahora la
    conversación lo marca (`vieja`, el widget no ofrece «Aprobar») y aprobarlo responde 409 sin escribir nada: queda
    como rechazado y el modelo lo sabe en el mensaje siguiente."""
    db = sesion.app.state.db
    pid = persona(db, nombre="ANA INVENTADA DE PRUEBA", consentimiento="si")
    api = encender(sesion.app, sse(TU("toolu_v", "nota_falsa", {"persona_id": pid, "texto": NOTA_LARGA}),
                                   stop="tool_use"), sse(T("No se guardó: la vuelvo a proponer si quiere.")))
    _, ev = enviar(sesion, "Agrega la nota")
    cid = ev[0]["conversacion"]
    # La tarjeta nueva queda marcada al guardarse
    llamada = conv_db.pendiente_de(db[conv_db.CONVERSACIONES].find_one({"_id": cid}))["llamadas"][0]
    assert llamada["confirmacion"]["entera"] is True
    _como_lo_guardaba_412c3a5(db, cid)
    vista = sesion.get(f"/api/agente/conversaciones/{cid}").json()
    assert vista["pendientes"][0]["vieja"] is True
    r, _ = decidir(sesion, cid, toolu_v=True)
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "sin_pendientes", r.text
    assert "versión anterior" in r.json()["detail"]["mensaje"]
    assert falsas == [] and not db.personas.find_one({"_id": pid}).get("notas")
    conv = db[conv_db.CONVERSACIONES].find_one({"_id": cid})
    assert conv["pendiente"] is None and conv["rechazadas"] == ["toolu_v"] and conv["ocupada_hasta"] is None
    r, ev = enviar(sesion, "¿Qué pasó con la nota?", conversacion=cid)
    assert r.status_code == 200 and ev[-1]["motivo"] == "listo", ev[-3:]
    res = [b for b in api.peticiones[-1]["json"]["messages"][-1]["content"] if b.get("type") == "tool_result"]
    assert res == [{"type": "tool_result", "tool_use_id": "toolu_v", "content": bucle.RECHAZADA, "is_error": True}]


def test_lo_pendiente_de_la_version_anterior_se_puede_rechazar(sesion, falsas):  # noqa: F811
    """Cuida que el arreglo no se pase de la raya (pasa también sin él): rechazarlo sigue como siempre."""
    db = sesion.app.state.db
    pid = persona(db, nombre="ANA INVENTADA DE PRUEBA", consentimiento="si")
    encender(sesion.app, sse(TU("toolu_v", "nota_falsa", {"persona_id": pid, "texto": NOTA_LARGA}), stop="tool_use"),
             sse(T("Entendido, no la guardo.")))
    _, ev = enviar(sesion, "Agrega la nota")
    cid = ev[0]["conversacion"]
    _como_lo_guardaba_412c3a5(db, cid)
    r, ev = decidir(sesion, cid, toolu_v=False)
    assert r.status_code == 200 and ev[-1]["motivo"] == "listo", ev[-3:]
    assert ("rechazada", "Rechazada") in [(e["estado"], e.get("resumen")) for e in ev if e["tipo"] == "herramienta"]
    assert falsas == [] and db[conv_db.CONVERSACIONES].find_one({"_id": cid})["pendiente"] is None


@requiere_node
def test_el_widget_no_ofrece_aprobar_lo_pendiente_de_la_version_anterior():
    """`bloqueoTarjeta()` dice por qué una tarjeta no se puede aprobar: la vieja (que la conversación marca) no se
    aprueba aunque sus filas quepan; la que no cabe, tampoco; la de ahora, sí."""
    script = r"""
import { readFileSync } from 'node:fs';
globalThis.document = { querySelector: () => null, documentElement: {} };
globalThis.MutationObserver = class { observe() {} };
globalThis.window = globalThis;
globalThis.addEventListener ||= () => {};
const m = await import('./web/js/agente.js');
const detalle = [['Nota', 'Visita sin novedad.']];
console.log(JSON.stringify([
  m.bloqueoTarjeta({ detalle, vieja: true }), m.bloqueoTarjeta({ detalle: [['Nota', 'x'.repeat(4001)]] }),
  m.bloqueoTarjeta({ detalle }), m.bloqueoTarjeta({ detalle, vieja: false })]));
"""
    r = subprocess.run(["node", "--input-type=module", "-e", script], cwd=RAIZ, capture_output=True, text=True,
                       timeout=30)
    assert r.returncode == 0, r.stderr[-2000:]
    vieja, no_cabe, nueva, explicita = json.loads(r.stdout)
    assert "versión anterior" in vieja and "más de lo que la tarjeta puede mostrar" in no_cabe
    assert nueva is None and explicita is None


# ───────────────────────────── 7. De quien no autorizó, su barrio o vereda también para P y C ─────────────────────────

def test_el_planillero_y_el_consultor_saben_la_vereda_de_quien_no_autorizo(sesion, como, ctx_de, gente):
    """Sus filas y su ficha no dicen si `lugar` es del nomenclátor o el texto libre, y sin los nombres del nomenclátor
    (`minimizar.lugares_de`) el lugar de quien no autorizó llegaba siempre vacío: con dos personas del mismo nombre, el
    planillero no sabía cuál era cuál."""
    db = sesion.app.state.db
    vereda = db.lugares.find_one({"_id": gente.lugar})["nombre"]
    p = como("planillero", asignacion={"lugares": [gente.lugar], "areas": []})
    c = como("consultor")
    for cli in (p, c):
        r = _ej(sesion, ctx_de(cli), "buscar_personas", {"q": "MARTA NOAUTORIZO"})
        fila = next(f for f in r.contenido["filas"] if f["id"] == gente.marta)
        assert set(fila) <= FILA_NO_AUTORIZO and fila["lugar"] == vereda, (cli.rol, fila)
    ctx = ctx_de(p)
    r = _ej(sesion, ctx, "buscar_personas", {"filtros": {"consentimiento": "no", "lugar_id": gente.lugar}})
    assert next(f for f in r.contenido["filas"] if f["id"] == gente.marta)["lugar"] == vereda
    r = _ej(sesion, ctx, "ver_persona", {"persona_id": gente.marta})
    assert set(r.contenido) == FILA_NO_AUTORIZO and r.contenido["lugar"] == vereda
    r = _ej(sesion, ctx, "personas_parecidas", {"nombre": "MARTA NOAUTORIZO INVENTADA"})
    assert next(f for f in r.contenido["parecidas"] if f["id"] == gente.marta)["lugar"] == vereda
    # Nunca el sitio escrito a mano: no es su barrio o vereda
    texto = json.dumps(r.contenido, ensure_ascii=False)
    assert "ESPERANZA" not in texto and "CALLE 49" not in texto


# ───────────────────────────── 8. El alta y la edición no dicen de quién es un número ─────────────────────────────

def test_la_cedula_de_quien_no_autorizo_no_dice_de_quien_es(sesion, ctx_de, gente):
    """Con la cédula de MARTA (no autorizó) y otro nombre, crear_persona respondía «ya pertenece a otra ficha activa
    (#id)»: con ver_persona, el modelo sabía que esa cédula es de MARTA. editar_persona, igual. Ahora no da el número
    de la ficha (que la persona del equipo la revise en Habitantes); de quien sí autorizó, sí."""
    db = sesion.app.state.db
    ctx = ctx_de(sesion)
    with pytest.raises(ErrorHerramienta) as e:
        _ej(sesion, ctx, "crear_persona", {"nombre": "PEDRO DISTINTO INVENTADO", "cedula": CEDULA_MARTA})
    assert e.value.codigo == "cedula_ocupada" and "Habitantes" in e.value.mensaje
    assert str(gente.marta) not in e.value.para_modelo() and not (e.value.detalle or {}).get("id")
    with pytest.raises(ErrorHerramienta) as e:
        _ej(sesion, ctx_de(sesion, "toolu_rosa"), "crear_persona", {"nombre": "PEDRO DISTINTO INVENTADO",
                                                                    "cedula": CEDULA_ROSA})
    assert e.value.codigo == "cedula_ocupada" and f"#{gente.rosa}" in e.value.para_modelo()
    juana = persona(db, nombre="JUANA EDITADA INVENTADA")
    autorizada(db, juana)
    with pytest.raises(ErrorHerramienta) as e:
        _ej(sesion, ctx_de(sesion, "toolu_editar"), "editar_persona",
            {"persona_id": juana, "cambios": {"cedula": CEDULA_MARTA}})
    assert e.value.codigo == "cedula_ocupada" and str(gente.marta) not in e.value.para_modelo()


def test_las_parecidas_del_alta_no_traen_por_un_numero_a_quien_no_autorizo(sesion, ctx_de, gente):
    """El 409 «parecidas» de crear_persona (la API sin `estricta`) traía a MARTA por su teléfono con un nombre que
    solo se le parece a medias: el modelo sabía que ese número es suyo. Ahora no sale, y el resultado dice que hay una
    coincidencia que el asistente no puede mostrar: la ficha no se crea (sería un duplicado de alguien que dijo que no)
    y la persona del equipo la revisa en Habitantes antes de proponer `forzar`."""
    db = sesion.app.state.db
    nombres = ["MARTA PEREZ", "MARTA LUCIA GOMEZ", "MARIA NOAUTORIZO", "MARTA INVENTADA", "MARTHA NOA INVENTADA",
               "MARTA NOAUTORIZO", "MARCO INVENTADO", "MARTINA AUTORIZO VENTADA"]
    elegido = next(n for n in nombres
                   if gente.marta in {c["_id"] for c, _ in api_personas._parecidas(db, n, [TEL_MARTA], None)}
                   and gente.marta not in {c["_id"] for c, _ in api_personas._parecidas(db, n, ["3209998877"], None)})
    r = _ej(sesion, ctx_de(sesion, "toolu_alta1"), "crear_persona", {"nombre": elegido, "telefonos": [TEL_MARTA]})
    c = r.contenido
    assert c["creada"] is False and gente.marta not in {f["id"] for f in c["parecidas"]}, c
    assert gente.marta not in r.personas and "Habitantes" in c["nota"] and "forzar" in c["nota"]
    assert TEL_MARTA not in r.texto_para_modelo() and "MARTA NOAUTORIZO" not in r.texto_para_modelo()
    # Con otro teléfono no hay coincidencia: se crea (y la nota no está)
    r = _ej(sesion, ctx_de(sesion, "toolu_alta2"), "crear_persona", {"nombre": elegido, "telefonos": ["3209998877"]})
    assert r.contenido["creada"] is True and "nota" not in r.contenido
    # Quien no autorizó y se llama casi igual sí sale (solo quién es): por el nombre, como en personas_parecidas
    r = _ej(sesion, ctx_de(sesion, "toolu_alta3"), "crear_persona", {"nombre": "MARTA NOAUTORIZO INVENTADA",
                                                                    "telefonos": [TEL_MARTA]})
    fila = next(f for f in r.contenido["parecidas"] if f["id"] == gente.marta)
    assert set(fila) <= FILA_NO_AUTORIZO


# ───────────────────────────── 9. La carrera de la revocatoria en lo que devuelve una escritura ──────────────────────

def test_quien_deja_de_autorizar_mientras_se_arman_las_parecidas_del_alta_no_llega_al_modelo(sesion, monkeypatch):
    """crear_persona devuelve en su 409 las filas de otras personas, que no estaban en la tarjeta. Si una deja de
    autorizar mientras la API las arma, la conversación no la tenía anotada (el «no» no la borró) y `_anotar` no la
    buscaba en `agente_olvidos`: su fila de cuando autorizaba llegaba al modelo y quedaba en el historial. Ahora la
    conversación se borra y el turno termina antes."""
    db = sesion.app.state.db
    rosa = persona(db, nombre="ROSA SIAUTORIZO INVENTADA", cedula="1023456789", telefono="3104445566",
                   direccion="CALLE 50 # 45-12")
    autorizada(db, rosa)
    original = api_personas.filas_parecidas

    def y_revoca(*args, **kwargs):
        filas = original(*args, **kwargs)
        _revocar(db, rosa, "panel")  # el «no» llega mientras la API arma las parecidas
        return filas

    monkeypatch.setattr(api_personas, "filas_parecidas", y_revoca)
    api = encender(sesion.app, sse(TU("toolu_c", "crear_persona", {"nombre": "ROSA SIAUTORIZO INVENTADA",
                                                                   "telefonos": ["3104445566"]}), stop="tool_use"),
                   sse(T("No debería llegar.")))
    _, ev = enviar(sesion, "Registra a Rosa")
    cid = ev[0]["conversacion"]
    assert any(e["tipo"] == "confirmar" for e in ev), ev[-4:]
    r, ev = decidir(sesion, cid, toolu_c=True)
    assert r.status_code == 200 and db.personas.find_one({"_id": rosa})["consentimiento"] == "no"
    assert ev[-2]["tipo"] == "error" and ev[-2]["codigo"] == "borrada", ev[-3:]
    assert len(api.peticiones) == 1 and db[conv_db.CONVERSACIONES].find_one({"_id": cid}) is None
    assert not db[conv_db.MENSAJES].find_one({"conversacion": cid})


# ───────────────────────────── Pendientes entre dueños ─────────────────────────────

def test_el_tablero_cuenta_los_asistentes_de_las_reuniones_recientes_sin_quien_no_autorizo(sesion, ctx_de, gente):
    """`/api/indicadores` con `tratables` (el asistente) cuenta los asistentes de las reuniones recientes sin quien no
    autorizó, como Reuniones: la herramienta indicadores ya no tiene que pedir además la lista de reuniones para
    reemplazarlos. Sin `tratables`, el tablero del panel los cuenta a todos, como siempre."""
    rid = sesion.post("/api/reuniones", json={"titulo": "Reunión inventada del cierre", "fecha": "2026-11-02"})
    rid = rid.json()["id"]
    for pid in (gente.rosa, gente.marta):
        assert sesion.post(f"/api/reuniones/{rid}/asistentes", json={"persona_id": pid}).status_code == 201

    def asistentes(params: dict) -> int:
        d = sesion.get("/api/indicadores", params=params).json()
        return next(x["n"] for x in d["reuniones"] if x["id"] == rid)

    assert asistentes({"tratables": 1}) == 1 and asistentes({}) == 2
    r = _ej(sesion, ctx_de(sesion), "indicadores", {})
    assert next(x for x in r.contenido["reuniones_recientes"] if x["id"] == rid)["asistentes"] == 1


def test_la_documentacion_dice_lo_que_no_viaja_del_contexto():
    """«Sabe dónde está» (Cómo se usa) nombra también la consulta de la ruta y una etiqueta sensible, como lo hace
    «Qué va al modelo» (Privacidad)."""
    texto = (RAIZ / "docs" / "agente.md").read_text(encoding="utf-8")
    punto = re.search(r"- \*\*Sabe dónde está\.\*\*(.*?)\n- \*\*", texto, re.S).group(1)
    assert "consulta de la ruta" in punto and "etiqueta sensible" in punto
