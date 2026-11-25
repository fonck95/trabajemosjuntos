"""El plan en flujo (app/agente/redactor.py; docs/agente.md, «El plan en flujo»; docs/velocidad.md): el panel escribe el
plan guiado y la pantalla lo empieza a narrar con su primer paso, mientras el resto se sigue escribiendo.

Sin MongoDB ni modelo: la base en memoria de test_pantalla_mcp.py y un redactor inventado que manda el plan en JSON
Lines a trozos, con esperas, como lo manda Mnemo. Solo datos inventados: la presentación es pública."""
import asyncio
import json
import time
from types import SimpleNamespace

import pytest

from app import pantalla
from app import recorrido as rec
from app.agente import redactor
from app.agente.herramientas import interfaz as hi
from app.agente.herramientas.base import ErrorHerramienta
from app.agente.proveedores import Respuesta, Uso
from test_pantalla_mcp import G, _Base

UID = 7

TITULO = {"titulo": "La torre del hospital"}
PASOS = [
    {"capitulo": "salud", "paso": "torre", "camara": "oblicua", "mover": {"giro": 40}, "gesto": "saludar",
     "dice": "Aquí ven el predio donde va la torre de servicios del hospital."},
    {"aislar": "torre", "sin": ["torre.cubierta"], "elevacion": 55, "dice": "Sin la cubierta se ven las losas de cada piso."},
    {"paso": "torre_pisos", "dice": "Cada piso tiene un servicio: urgencias abajo y hospitalización arriba."},
    {"paso": "telesalud", "camara": "aerea", "dice": "La telesalud conecta los puestos rurales con el hospital."},
]
CIERRE = {"cierre": {"puntos": ["Una torre de primer nivel", "Salud rural conectada"]},
          "sugerencias": ["Muéstrame el agua potable", "¿Cómo resiste un sismo?"]}


def _jsonl(*objetos) -> str:
    return "\n".join(json.dumps(o, ensure_ascii=False) for o in objetos) + "\n"


class Redactor:
    """Un proveedor que «escribe» `texto` a trozos de `trozo` caracteres, con `pausa` segundos entre ellos (como llegan
    los avisos de avance de Mnemo). Anota cuándo terminó y lo que se le pidió."""

    clave = "mnemo"

    def __init__(self, texto: str, trozo: int = 25, pausa: float = 0.01, falla: BaseException | None = None,
                 antes: float = 0.0):
        self.texto, self.trozo, self.pausa, self.falla, self.antes = texto, trozo, pausa, falla, antes
        self.pedidos: list[dict] = []
        self.fin: float | None = None
        self.cancelado = False

    async def generar(self, sistema, mensajes, herramientas, *, max_tokens, esfuerzo, al_evento, rapido=False,
                      vision=False):
        self.pedidos.append({"sistema": sistema, "mensajes": mensajes, "herramientas": herramientas,
                             "max_tokens": max_tokens, "rapido": rapido})
        try:
            await asyncio.sleep(self.antes)
            for i in range(0, len(self.texto), self.trozo):
                al_evento({"tipo": "texto", "texto": self.texto[i:i + self.trozo]})
                await asyncio.sleep(self.pausa)
        except asyncio.CancelledError:
            self.cancelado = True
            raise
        if self.falla is not None:
            raise self.falla
        self.fin = time.monotonic()
        return Respuesta(contenido=[{"type": "text", "text": self.texto}], fin="end_turn", modelo="prueba",
                         uso=Uso(entrada=100, salida=200))


def _ctx(db, proveedor):
    eventos: list[tuple[float, dict]] = []
    ctx = SimpleNamespace(db=db, quien=SimpleNamespace(uid=UID), proveedor=proveedor, conversacion_id=1,
                          emitir=lambda ev: eventos.append((time.monotonic(), ev)))
    return ctx, eventos


def _plan(**k):
    return hi.PresentacionEntrada.model_validate({"op": "plan", "capitulo": "salud",
                                                  "encargo": "La torre del hospital: dónde va y cómo es", **k})


def _acciones(eventos, tipo, op=None):
    return [(t, ev["accion"]) for t, ev in eventos if ev.get("tipo") == "accion" and ev["accion"].get("tipo") == tipo
            and (op is None or ev["accion"].get("op") == op)]


# ───────────────────────────── El lector del texto que llega ─────────────────────────────

def test_el_lector_entrega_cada_objeto_en_cuanto_se_cierra():
    texto = '```json\n{"titulo": "Un {plan} con \\"comillas\\""}\n{"dice": "uno",\n "paso": 2}\nruido\n{"dice": "dos"}'
    lector, vistos = redactor.Lector(), []
    for i in range(0, len(texto), 3):
        vistos += lector.agregar(texto[i:i + 3])
    assert vistos == [{"titulo": 'Un {plan} con "comillas"'}, {"dice": "uno", "paso": 2}, {"dice": "dos"}]
    # el texto final de la ronda: lo que falta, o lo que no se había entregado si cambió
    assert lector.reemplazar(texto + '\n{"cierre": {"puntos": ["a b c"]}}') == [{"cierre": {"puntos": ["a b c"]}}]
    otro = redactor.Lector()
    otro.agregar('{"dice": "uno"}\n{"dice": "do')
    assert otro.reemplazar('{"dice": "uno"}\n{"dice": "dos"}\n{"dice": "tres"}') == [{"dice": "dos"}, {"dice": "tres"}]
    # un objeto roto no tumba lo demás
    assert redactor.Lector().agregar('{"dice": 1,}\n{"dice": "ok"}') == [{"dice": "ok"}]


# ───────────────────────────── El plan en flujo ─────────────────────────────

def test_la_sala_ve_el_primer_paso_antes_de_que_el_plan_este_escrito():
    db = _Base()
    prov = Redactor(_jsonl(TITULO, *PASOS, CIERRE), trozo=20, pausa=0.01)
    ctx, eventos = _ctx(db, prov)
    res = asyncio.run(redactor.escribir(ctx, _plan(), G))

    # La redacción: sin herramientas, rápida, con el guion del capítulo en el system (el mismo para el mismo capítulo)
    pedido = prov.pedidos[0]
    assert pedido["rapido"] is True and pedido["herramientas"] == []
    assert pedido["sistema"] == redactor.sistema_de(G, G.por_id("salud")) and '"torre_sismo"' in pedido["sistema"]
    assert "La torre del hospital: dónde va" in pedido["mensajes"][0]["content"][0]["text"]

    # La presentación recibe el plan con su primer paso, ANTES de que la redacción termine, y después crece
    pres = _acciones(eventos, "presentacion", "recorrido")
    assert [len(a["recorrido"]["escenas"]) for _, a in pres] == [1, 2, 3, 4, 4]
    assert pres[0][0] < prov.fin, "el primer paso tiene que salir mientras se escribe el resto"
    assert "sigue" not in pres[0][1] and all(a.get("sigue") is True for _, a in pres[1:])
    assert all(a.get("abierto") is True for _, a in pres[:-1]) and "abierto" not in pres[-1][1]
    assert len({a["recorrido"]["id"] for _, a in pres}) == 1
    final = pres[-1][1]["recorrido"]
    assert final["titulo"] == "La torre del hospital" and final["cierre"] == {"puntos": CIERRE["cierre"]["puntos"]}
    assert not rec.validar(final, G)
    # los pasos que ya sonaban no cambian al crecer
    assert pres[1][1]["recorrido"]["escenas"][0] == final["escenas"][0]
    # la píldora «preparando» antes del primer paso, y la tarjeta del chat con el mismo id, que crece igual
    assert _acciones(eventos, "presentacion", "preparando")[0][0] <= pres[0][0]
    tarjetas = [a for _, a in _acciones(eventos, "recorrido")]
    assert [len(t["escenas"]) for t in tarjetas] == [1, 2, 3, 4, 4] and tarjetas[-1]["sugerencias"] == CIERRE["sugerencias"]
    assert all(t["id"] == final["id"] for t in tarjetas) and "abierto" not in tarjetas[-1]

    # Guardado entero, ya cerrado de escribir, y el turno termina sin otra ronda
    doc = pantalla.leer(db, UID)
    r = pantalla.recorrido_de(doc, G)
    assert r["escenas"] == final["escenas"] and r["en_flujo"] and not r["abierto"] and not r["cerrado"]
    assert res.termina_turno is True and res.contenido["plan"]["en_flujo"] is True
    assert res.contenido["plan"]["pasos"] == 4 and res.contenido["sugerencias"] == CIERRE["sugerencias"]
    assert db.agente_uso.docs, "lo que gastó la redacción se suma al día de la persona"


def test_un_paso_que_no_se_puede_proyectar_se_omite_y_el_plan_sigue():
    db = _Base()
    malo = {"dice": "Cuesta $ 37.137 millones de pesos."}
    prov = Redactor(_jsonl(TITULO, PASOS[0], malo, PASOS[1], CIERRE))
    ctx, eventos = _ctx(db, prov)
    res = asyncio.run(redactor.escribir(ctx, _plan(), G))
    final = _acciones(eventos, "presentacion", "recorrido")[-1][1]["recorrido"]
    assert len(final["escenas"]) == 2 and all("$" not in " ".join(e["frases"]) for e in final["escenas"])
    assert any(a.startswith("Paso 2:") for a in res.contenido["avisos"])


def test_si_la_persona_lo_detiene_mientras_se_escribe_la_redaccion_se_corta():
    db = _Base()
    prov = Redactor(_jsonl(TITULO, *PASOS, CIERRE), trozo=10, pausa=0.02)
    ctx, eventos = _ctx(db, prov)

    async def correr():
        tarea = asyncio.ensure_future(redactor.escribir(ctx, _plan(), G))
        while not _acciones(eventos, "presentacion", "recorrido"):
            await asyncio.sleep(0.005)
        rid = _acciones(eventos, "presentacion", "recorrido")[0][1]["recorrido"]["id"]
        assert pantalla.colapsar(db, UID, G, "asistente", rid) is not None   # «Detener» (u otra orden)
        return await tarea

    res = asyncio.run(correr())
    assert prov.cancelado and prov.fin is None
    assert res.termina_turno is False and "se detuvo mientras se escribía" in res.contenido["nota"]
    assert pantalla.recorrido_de(pantalla.leer(db, UID), G)["cerrado"] is True


def test_si_la_redaccion_falla_antes_del_primer_paso_el_modelo_lo_arma_como_antes():
    db = _Base()
    ctx, eventos = _ctx(db, Redactor(_jsonl(TITULO), falla=RuntimeError("caído")))
    with pytest.raises(ErrorHerramienta) as e:
        asyncio.run(redactor.escribir(ctx, _plan(), G))
    assert e.value.codigo == "plan_fallo" and "guion" in e.value.mensaje and "recorrido" in e.value.mensaje
    assert pantalla.leer(db, UID) is None, "sin un paso que valga no se guarda nada"
    # la píldora se apaga
    assert _acciones(eventos, "presentacion", "preparando")[-1][1]["activar"] is False


def test_si_falla_a_mitad_queda_con_lo_que_alcanzo():
    db = _Base()
    ctx, eventos = _ctx(db, Redactor(_jsonl(TITULO, *PASOS[:2]), falla=RuntimeError("corte")))
    res = asyncio.run(redactor.escribir(ctx, _plan(), G))
    r = pantalla.recorrido_de(pantalla.leer(db, UID), G)
    assert len(r["escenas"]) == 2 and not r["abierto"]
    assert "se cortó a mitad" in res.contenido["avisos"][0]


def test_corto_y_el_tope_de_pasos():
    db = _Base()
    muchos = [PASOS[0]] + [{"dice": f"Otra mirada a la torre, número {i}."} for i in range(1, 15)]
    ctx, eventos = _ctx(db, Redactor(_jsonl(TITULO, *muchos, CIERRE), trozo=200, pausa=0))
    res = asyncio.run(redactor.escribir(ctx, _plan(largo="corto"), G))
    assert res.contenido["plan"]["pasos"] == 7   # corto: de 3 a 5, con dos de margen
    assert any("se omitieron" in a for a in res.contenido["avisos"])
    assert "De 3 a 5 pasos" in ctx.proveedor.pedidos[0]["mensajes"][0]["content"][0]["text"]


def test_el_avance_de_un_plan_en_flujo_puede_contar_menos_pasos():
    db = _Base()
    ctx, _ = _ctx(db, Redactor(_jsonl(TITULO, *PASOS, CIERRE)))
    asyncio.run(redactor.escribir(ctx, _plan(), G))
    r = pantalla.recorrido_de(pantalla.leer(db, UID), G)
    # el navegador todavía no recibió los dos últimos: su avance vale igual
    assert pantalla.guardar_progreso(db, UID, {"rid": r["id"], "n": 1, "de": 2, "fase": "narrando", "frase": 0,
                                               "voz": "activa"}, G)
    assert not pantalla.guardar_progreso(db, UID, {"rid": r["id"], "n": 1, "de": 9, "fase": "narrando", "frase": 0,
                                                   "voz": "activa"}, G)


def test_la_op_plan_es_solo_del_asistente():
    db = _Base()
    with pytest.raises(ErrorHerramienta) as e:
        asyncio.run(hi.presentacion_en_pantalla(db, UID, _plan(), "mcp"))
    assert e.value.codigo == "sin_redactor"
    with pytest.raises(ErrorHerramienta):
        asyncio.run(redactor.escribir(SimpleNamespace(proveedor=None, emitir=None), _plan(), G))


# ───────────────────────────── En el navegador: el reproductor y un plan que crece ─────────────────────────────

WEB = __import__("pathlib").Path(__file__).resolve().parents[1] / "web"

NODE_CRECE = r"""// El reproductor con un plan en flujo y un reloj de mentira. Uso: node <prueba> <reproductor.js>
const R = await import(process.argv[2]);
const { crearReproductor, ESPERA_MAS_MS, PREVIA_MS } = R;
function relojFalso() {
  let t = 0, id = 0; const cola = new Map();
  return { ahora: () => t, programar(f, ms) { const h = ++id; cola.set(h, { f, en: t + ms }); return h; }, cancelar(h) { cola.delete(h); },
    async avanzar(ms) { const fin = t + ms; for (;;) { await new Promise((r) => setImmediate(r)); let p = null;
      for (const [h, x] of cola) if (x.en <= fin && (!p || x.en < p[1].en)) p = [h, x]; if (!p) break; cola.delete(p[0]); t = p[1].en; p[1].f(); }
      t = fin; for (let i = 0; i < 5; i++) await new Promise((r) => setImmediate(r)); } };
}
const V = { enfoque: null, camara: 'paso', rumbo: null, elevacion: null, zoom: null, mirar: null, girar: false, comparar: 'proyecto',
  detalle: null, inmersion: null, mostrar: [], ocultar: [], aislar: null, sin: [] };
const esc = (paso, frase) => ({ capitulo: 'salud', paso, panel: true, visual: V, resaltar: null, mover: null, animar: false, frases: [frase], sostener_ms: 1300 });
const plan = (escenas, cierre = null) => ({ id: 'a'.repeat(12), titulo: 'En flujo', cierre, escenas });
const nombre = (o) => o.orden + (o.orden === 'escena' ? ':' + o.n : o.orden === 'cierre' ? (o.puntos ? ':puntos' : ':fin') : '');
function armar() {
  const reloj = relojFalso(), ordenes = [], avances = [];
  const rep = crearReproductor({ reloj, orden: async (o) => { ordenes.push(nombre(o)); return { ok: true }; },
    avisar: (p) => avances.push(`${p.n}/${p.de}/${p.fase}`) });
  return { reloj, ordenes, avances, rep };
}
const out = {};
// 1. Empieza con un paso; al terminarlo espera el siguiente (no cierra); crece, sigue, y cierra cuando llega entero
{
  const { reloj, ordenes, rep } = armar();
  const e1 = esc(3, 'Aquí ven el predio de la torre.'), e2 = esc(4, 'Cada piso tiene un servicio.');
  rep.iniciar(plan([e1]), { previa: PREVIA_MS, abierto: true });
  await reloj.avanzar(PREVIA_MS + 20000);
  out.espera = { ordenes: ordenes.slice(), activo: rep.activo(), abierto: rep.abierto(), estado: rep.estado() };
  out.otro_id = rep.actualizar({ ...plan([e1, e2]), id: 'b'.repeat(12) }, { abierto: true });
  out.crece = rep.actualizar(plan([e1, e2]), { abierto: true });
  await reloj.avanzar(300);   // (lo espera de a TICK_MS: empieza en el tic siguiente)
  out.tras_crecer = ordenes.slice();
  out.de = rep.estado().de;
  rep.actualizar(plan([e1, e2], { puntos: ['Una torre nueva'] }), { abierto: false });
  await reloj.avanzar(60000);
  out.final = { ordenes: ordenes.slice(), fase: rep.estado().fase, abierto: rep.abierto() };
}
// 2. Si nunca llega el siguiente, a los ESPERA_MAS_MS cierra con lo que hay; «siguiente» en el último paso espera
{
  const { reloj, ordenes, rep } = armar();
  rep.iniciar(plan([esc(3, 'Solo un paso.')]), { abierto: true });
  await reloj.avanzar(15000);
  out.siguiente = rep.siguiente();
  await reloj.avanzar(1);
  out.tras_siguiente = { ordenes: ordenes.slice(), activo: rep.activo() };
  await reloj.avanzar(ESPERA_MAS_MS + 30000);
  out.vencido = { ordenes: ordenes.slice(), fase: rep.estado().fase };
}
// 3. Un plan entero (sin `abierto`) es como siempre: actualizar no lo reabre si ya terminó
{
  const { reloj, rep } = armar();
  rep.iniciar(plan([esc(3, 'Uno.')]));
  await reloj.avanzar(40000);
  out.terminado = { fase: rep.estado().fase, actualizar: rep.actualizar(plan([esc(3, 'Uno.'), esc(4, 'Dos.')]), { abierto: true }) };
}
console.log(JSON.stringify(out));
"""


def test_el_reproductor_espera_el_paso_que_se_esta_escribiendo(tmp_path):
    (tmp_path / "prueba.mjs").write_text(NODE_CRECE, encoding="utf-8")
    p = __import__("subprocess").run(["node", str(tmp_path / "prueba.mjs"), (WEB / "js" / "reproductor.js").as_uri()],
                                     capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    o = json.loads(p.stdout)
    # con un solo paso y abierto: lo narra y se queda esperando (sin el cierre), activo
    assert o["espera"]["ordenes"] == ["escena:1", "narracion"] and o["espera"]["activo"] and o["espera"]["abierto"]
    assert o["otro_id"] is False and o["crece"] is True
    # el paso nuevo empieza en cuanto llega
    assert o["tras_crecer"][-1] == "escena:2" and o["de"] == 2
    # entero: cierra como siempre, con su resumen
    assert o["final"]["ordenes"] == ["escena:1", "narracion", "escena:2", "narracion", "cierre:puntos", "cierre:fin",
                                     "quitar_explicacion"]
    assert o["final"]["fase"] == "fin" and o["final"]["abierto"] is False
    # «siguiente» en el último paso de un plan abierto espera (no cierra); vencida la espera, cierra con lo que hay
    assert o["siguiente"] is True and o["tras_siguiente"]["activo"] and "cierre:fin" not in o["tras_siguiente"]["ordenes"]
    assert o["vencido"]["ordenes"] == ["escena:1", "narracion", "cierre:fin", "quitar_explicacion"]
    assert o["vencido"]["fase"] == "fin"
    assert o["terminado"] == {"fase": "fin", "actualizar": False}


NODE_FORMAS = r"""// El puente y la tarjeta con el plan en flujo. Uso: node <prueba> <agente-presentacion.js> <agente-recorrido.js>
globalThis.document = { querySelector: () => null, documentElement: { dataset: {} } };
const P = await import(process.argv[2]);
const T = await import(process.argv[3]);
const V = { enfoque: null, camara: 'paso', rumbo: null, elevacion: null, zoom: null, mirar: null, girar: false, comparar: 'proyecto',
  detalle: null, inmersion: null, mostrar: [], ocultar: [], aislar: null, sin: [] };
const r = { id: 'a'.repeat(12), titulo: 'En flujo', cierre: null, escenas: [{ capitulo: 'salud', paso: 3, panel: true, visual: V,
  resaltar: null, mover: null, animar: false, frases: ['Aquí ven el predio.'], sostener_ms: 1300 }] };
const acc = (x) => P.accionPresentacion({ tipo: 'presentacion', op: 'recorrido', recorrido: r, ...x });
const tarjeta = (x) => T.tarjetaValida({ tipo: 'recorrido', id: r.id, titulo: 'En flujo', destino: 'vista', duracion_ms: 20000,
  cierre: null, sugerencias: [], escenas: [{ narracion: 'Aquí ven el predio.', donde: 'Salud · paso 3', hace: ['paso'] }], ...x });
console.log(JSON.stringify({
  abierto: acc({ abierto: true }), sigue: acc({ sigue: true, abierto: true }), entero: acc({ sigue: true }),
  malos: [acc({ abierto: false }), acc({ sigue: 'si' }), acc({ sigue: true, desde: 1 })],
  ajeno: P.accionPresentacion({ tipo: 'presentacion', op: 'ir', capitulo: 'salud', paso: 1, sigue: true }),
  tarjeta: tarjeta({ abierto: true })?.abierto, tarjeta_entera: tarjeta({})?.abierto, tarjeta_mala: tarjeta({ abierto: 1 }),
}));
"""


def test_el_puente_y_la_tarjeta_aceptan_el_plan_en_flujo_con_su_forma_exacta(tmp_path):
    (tmp_path / "prueba.mjs").write_text(NODE_FORMAS, encoding="utf-8")
    p = __import__("subprocess").run(["node", str(tmp_path / "prueba.mjs"), (WEB / "js" / "agente-presentacion.js").as_uri(),
                                      (WEB / "js" / "agente-recorrido.js").as_uri()], capture_output=True, text=True,
                                     timeout=60)
    assert p.returncode == 0, p.stderr
    o = json.loads(p.stdout)
    assert o["abierto"]["abierto"] is True and "sigue" not in o["abierto"]
    assert o["sigue"]["sigue"] is True and o["sigue"]["abierto"] is True
    assert o["entero"]["sigue"] is True and "abierto" not in o["entero"]
    assert o["malos"] == [None, None, None] and o["ajeno"] is None
    assert o["tarjeta"] is True and o["tarjeta_entera"] is False and o["tarjeta_mala"] is None


def test_la_tarjeta_del_chat_crece_con_el_plan(tmp_path):
    from test_recorrido_panel import NODE_TARJETA, PUENTE_JS, TARJETA_JS
    prueba = NODE_TARJETA[:NODE_TARJETA.index("// La API: cada llamada")] + r"""
Nodo.prototype.insertBefore = function (x, antes) { x.remove?.(); x.padre = this; const i = this.hijos.indexOf(antes);
  this.hijos.splice(i < 0 ? this.hijos.length : i, 0, x); };
const T = await import(tarjetaJs);
const paso = (n) => ({ narracion: `Paso número ${n} del plan.`, donde: `Salud · paso ${n}`, hace: ['paso'] });
const a = (escenas, extra = {}) => ({ tipo: 'recorrido', id: '7171717171ab', titulo: 'En flujo', destino: 'vista', duracion_ms: 20000,
  cierre: null, sugerencias: [], escenas, ...extra });
const t = T.crearTarjetaRecorrido(T.tarjetaValida(a([paso(1)], { abierto: true })), { el, ico, alSugerencia: () => {},
  guardado: () => false, reproducir: () => false });
CUERPO.append(t.el);
const foto = () => ({ pasos: t.el.querySelectorAll('.rec-narracion').map((n) => n.textContent),
  cierre: t.el.querySelectorAll('.rec-puntos').length, ultimo: t.el.querySelector('.rec-escenas').hijos.at(-1).className,
  meta: t.el.querySelector('.rec-meta').textContent, sugerencias: t.el.querySelectorAll('.rec-sugerencia').map((b) => b.textContent) });
const r = { abierta: foto(), es_ella: T.tarjetaDe('7171717171ab') === t, otra: T.tarjetaDe('0000000000ab') };
r.crece = t.crecer(T.tarjetaValida(a([paso(1), paso(2)], { abierto: true })));
r.media = foto();
t.crecer(T.tarjetaValida(a([paso(1), paso(2), paso(3)], { cierre: ['Una idea'], sugerencias: ['Muéstrame el agua'], duracion_ms: 45000 })));
r.entera = foto();
r.ajena = t.crecer(T.tarjetaValida({ ...a([paso(1)]), id: '0000000000ab' }));
console.log(JSON.stringify(r));
process.exit(0);
"""
    (tmp_path / "prueba.mjs").write_text(prueba, encoding="utf-8")
    p = __import__("subprocess").run(["node", str(tmp_path / "prueba.mjs"), PUENTE_JS.as_uri(), TARJETA_JS.as_uri()],
                                     capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    o = json.loads(p.stdout)
    assert o["abierta"]["pasos"] == ["Paso número 1 del plan."] and "sigue escribiéndolo" in o["abierta"]["meta"]
    assert o["es_ella"] is True and o["otra"] is None and o["crece"] is True
    assert len(o["media"]["pasos"]) == 2 and o["media"]["cierre"] == 0
    # entera: tres pasos, el cierre al final, las sugerencias y la duración nueva
    assert len(o["entera"]["pasos"]) == 3 and o["entera"]["cierre"] == 1 and "rec-cierre" in o["entera"]["ultimo"]
    assert o["entera"]["sugerencias"] == ["Muéstrame el agua"] and "sigue escribiéndolo" not in o["entera"]["meta"]
    assert "3 pasos" in o["entera"]["meta"] and o["ajena"] is False


# ───────────────────────────── El turno termina con el plan ─────────────────────────────

def _turno(herramientas):
    """Un `bucle.Turno` con lo justo para `_cerrar_ronda` (sin base ni API: lo que guarda queda en `guardado`)."""
    from app.agente import bucle
    t = bucle.Turno.__new__(bucle.Turno)
    t.db, t.cid, t.tokens, t.servido = _Base(), 1, 0, 0
    t.imagenes_conv = t.imagenes_n = t.imagenes_ronda = 0
    t.herramientas = {h.nombre: h for h in herramientas}
    t.permitidas = set(t.herramientas)
    t.proveedor = SimpleNamespace(tope_imagenes=10**9)
    t.quien = SimpleNamespace(uid=UID)
    t.termina_turno = False
    t.guardado, t.eventos = [], []
    t.emitir = t.eventos.append

    async def guardar(rol, contenido=None, **_):
        t.guardado.append((rol, contenido))
    t._guardar = guardar
    t._frases = lambda *a: None
    t._contexto = lambda tid, h=None: SimpleNamespace(tool_use_id=tid)
    t.graficos = {}
    return t


def _herramienta(nombre, res=None, error=None):
    from pydantic import BaseModel

    from app.agente.herramientas.base import Herramienta, Resultado

    class Libre(BaseModel):
        pass

    async def ejecutar(ctx, args):
        if error:
            raise ErrorHerramienta(error, "invalido")
        return res or Resultado({"ok": True}, "Listo")
    return Herramienta(nombre, "prueba", Libre, "interfaz", (), "Probando", ejecutar)


def _ronda(*usos):
    from app.agente.proveedores import Respuesta
    return Respuesta(contenido=[{"type": "text", "text": "Les muestro la torre."},
                                *[{"type": "tool_use", "id": f"t{i}", "name": n, "input": {}} for i, n in enumerate(usos)]],
                     fin="tool_use", modelo="prueba")


def test_el_turno_termina_sin_otra_ronda_cuando_el_plan_ya_sono():
    from app.agente.herramientas.base import Resultado
    plan = _herramienta("presentacion", Resultado({"plan": {}}, "Plan «La torre» · 4 pasos", termina_turno=True))
    t = _turno([plan, _herramienta("otra"), _herramienta("falla", error="no")])
    historial = [{"role": "user", "content": [{"type": "text", "text": "Explícanos la torre"}]}]
    assert asyncio.run(t._cerrar_ronda(_ronda("presentacion"), historial, [])) == "listo"
    # el resultado queda guardado (el modelo lo lee con el mensaje siguiente)
    assert [r for r, _ in t.guardado] == ["assistant", "user"] and historial[-1]["role"] == "user"
    # con otra herramienta que sale bien, también; si una falla, el modelo tiene que verlo: otra ronda
    assert asyncio.run(_turno([plan, _herramienta("otra")])._cerrar_ronda(_ronda("presentacion", "otra"), [], [])) == "listo"
    assert asyncio.run(_turno([plan, _herramienta("falla", error="no")])._cerrar_ronda(
        _ronda("presentacion", "falla"), [], [])) is None
    # sin el plan, como siempre: otra ronda
    assert asyncio.run(_turno([_herramienta("otra")])._cerrar_ronda(_ronda("otra"), [], [])) is None


def test_en_modo_directo_el_system_del_redactor_va_a_la_cache():
    """El `system` del plan en flujo (las instrucciones y el guion de un capítulo) se repite cada vez que se presenta
    ese capítulo: en modo directo va marcado para la caché; el de la respuesta inmediata, corto, no."""
    from app.agente import llm
    sistema = redactor.sistema_de(G, G.por_id("salud"))
    assert len(sistema) >= llm.SISTEMA_CACHEABLE > len("Instrucciones de la respuesta inmediata" * 20)
    assert llm.sistema_para_peticion(sistema)[0]["cache_control"] == {"type": "ephemeral"}
