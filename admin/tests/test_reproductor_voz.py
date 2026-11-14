"""El reproductor del recorrido narrado (admin/web/js/reproductor.js) y su voz (voz.js), con Node: los casos que la
revisión del recorrido encontró y que test_recorrido.py no cubre.

* El reproductor, con un reloj falso y una voz que la prueba maneja a mano (cuándo empieza a sonar, cuándo termina y
  cómo): la persona que mueve la imagen con la pausa ya puesta hace volver la escena al seguir; un recorrido nuevo
  termina al que sonaba con «detenido» por «reemplazo» (el mismo recorrido otra vez, no) y un detener que todavía
  quitaba la narración no pisa al nuevo; una frase que empezó a sonar y falló no espera su lectura entera ni da aviso
  de voz; el resumen del cierre deja terminar la pausa suave del chat (con motivo «mensaje») y se repite tras una pausa
  dura; detener con la primera escena en vuelo la deja atrás (quitar_explicacion), y una pausa pedida al arrancar se
  mantiene mientras la primera escena se prepara.
* La voz, con una síntesis falsa: `partes` nunca deja una parte de más de PARTIR caracteres (tampoco con una «, »
  pegada a un extremo, sin comas, sin espacios o con lo que crece al decirse); `gesto()` la activa si la preferencia
  está encendida, y `soltar()` quita los oyentes de la ventana y de la síntesis y calla.
"""
import json
import subprocess
from pathlib import Path

from test_agente_presentacion import requiere_node

JS = Path(__file__).resolve().parents[1] / "web" / "js"
REPRODUCTOR_JS = JS / "reproductor.js"
VOZ_JS = JS / "voz.js"


def _terminal(avance: str) -> bool:
    return any(f"/{f}" in avance for f in ("detenido", "fin", "error"))


def _node(tmp_path: Path, guion: str, *args: str) -> dict:
    (tmp_path / "prueba.mjs").write_text(guion, encoding="utf-8")
    p = subprocess.run(["node", str(tmp_path / "prueba.mjs"), *args], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout.strip().splitlines()[-1])


NODE_REPRODUCTOR = r"""
const { crearReproductor, lecturaMs, ENTRE_FRASES_MS, RESPIRO_MS, CIERRE_SOSTENER_MS, TICK_MS } = await import(process.argv[2]);
function relojFalso() {
  let t = 0, id = 0; const cola = new Map();
  return { ahora: () => t, programar(f, ms) { const h = ++id; cola.set(h, { f, en: t + ms }); return h; }, cancelar(h) { cola.delete(h); },
    async avanzar(ms) { const fin = t + ms; for (;;) { await new Promise((r) => setImmediate(r)); let p = null;
      for (const [h, x] of cola) if (x.en <= fin && (!p || x.en < p[1].en)) p = [h, x]; if (!p) break; cola.delete(p[0]); t = p[1].en; p[1].f(); }
      t = fin; for (let i = 0; i < 5; i++) await new Promise((r) => setImmediate(r)); } };
}
// Una voz que la prueba maneja: cada `decir` queda pendiente hasta `empezar()` (suena) y `terminar(res)`; callar la corta
function vozManual() {
  const v = { dichos: [], pendiente: null, estado: () => 'activa',
    callar() { const p = v.pendiente; v.pendiente = null; p?.ok('cortada'); },
    decir(t, { alEmpezar } = {}) { return new Promise((ok) => { v.dichos.push(t); v.pendiente = { t, ok, alEmpezar }; }); },
    empezar() { v.pendiente?.alEmpezar?.(); },
    terminar(res = 'dicha') { const p = v.pendiente; v.pendiente = null; p?.ok(res); } };
  return v;
}
const V = { enfoque: null, camara: 'paso', rumbo: null, girar: false, comparar: 'proyecto', detalle: null, inmersion: null };
const esc = (paso, frases) => ({ capitulo: 'salud', paso, panel: true, visual: V, resaltar: null, frases, sostener_ms: 1100 });
const rec = (id, { cierre = { puntos: ['Uno', 'Dos'] }, escenas } = {}) => ({ id: id.repeat(12), titulo: 'Prueba', cierre,
  escenas: escenas || [esc(1, ['Frase uno.', 'Frase dos.']), esc(2, ['Frase tres.']), esc(3, ['Frase cuatro.'])] });
const nombre = (o) => o.orden + (o.orden === 'escena' ? ':' + o.n : o.frase !== undefined ? ':f' + o.frase
  : o.pausa !== undefined ? ':p' + o.pausa : o.puntos !== undefined ? ':' + (o.puntos ? 'resumen' : 'preguntas') : '');
// Cada avance: la primera letra del rid, la escena, la fase, la frase, el motivo y el aviso («a1/pausa!persona»)
function armar({ respuesta = () => ({ ok: true }), voz } = {}) {
  const reloj = relojFalso(), ordenes = [], avances = [];
  const rep = crearReproductor({ reloj, ...(voz ? { voz } : {}), orden: async (o) => { ordenes.push(nombre(o)); return respuesta(o, reloj); },
    avisar: (p) => avances.push(`${p.rid[0]}${p.n}/${p.fase}${p.frase ? ':' + p.frase : ''}${p.motivo ? '!' + p.motivo : ''}${p.aviso ? '?' + p.aviso : ''}`) });
  return { reloj, ordenes, avances, rep };
}
const out = {};

// 1. La persona mueve la imagen con la pausa ya puesta (un botón, el chat): al seguir, la escena vuelve
for (const [clave, pausar] of [['persona_boton', (rep) => rep.pausar('boton')],
                               ['persona_mensaje', (rep) => rep.control('pausar', { suave: true })]]) {
  const { reloj, ordenes, avances, rep } = armar();
  rep.iniciar(rec('a'));
  await reloj.avanzar(1000);
  pausar(rep);
  await reloj.avanzar(3000);   // la suave entra al terminar la frase en curso
  const motivo = avances.at(-1);
  const antes = ordenes.length;
  const devuelve = rep.alPersona();
  rep.alPersona();
  const avisos = avances.filter((x) => x.endsWith('!persona')).length;
  rep.continuar();
  await reloj.avanzar(100);
  out[clave] = { motivo, devuelve, avance: avances.filter((x) => x.includes('/pausa')).at(-1), avisos, ordenes: ordenes.slice(antes) };
}

// 2. Un recorrido nuevo reemplaza al que suena (narrando o en pausa): el viejo termina con «detenido» por «reemplazo»
for (const [clave, antes] of [['reemplazo', () => {}], ['reemplazo_en_pausa', (rep) => rep.pausar('boton')]]) {
  const { reloj, avances, rep } = armar();
  rep.iniciar(rec('a'));
  await reloj.avanzar(1000);
  antes(rep);
  const primera = rep.iniciar(rec('b'));
  await reloj.avanzar(1000);
  const deA = avances.filter((x) => x[0] === 'a'), deB = avances.filter((x) => x[0] === 'b');
  out[clave] = { ultimaDeA: deA.at(-1), aAntesQueB: avances.indexOf(deA.at(-1)) < avances.indexOf(deB[0]), primeraDeB: deB[0],
    primera: await primera, estado: rep.estado() };
}
// El mismo recorrido otra vez (desde otra escena): no hay nada que cerrar
{
  const { reloj, avances, rep } = armar();
  rep.iniciar(rec('a'));
  await reloj.avanzar(1000);
  rep.iniciar(rec('a'), { desde: 2 });
  await reloj.avanzar(100);
  out.mismo = { terminales: avances.filter((x) => /\/(detenido|fin|error)/.test(x)), estado: rep.estado() };
}
// La escena del viejo que responde después del reemplazo no resuelve la primera escena del nuevo (que tarda más)
{
  const respuesta = (o, reloj) => (o.orden === 'escena'
    ? new Promise((ok) => reloj.programar(() => ok({ ok: true }), o.rid[0] === 'a' ? 200 : 500)) : { ok: true });
  const { reloj, rep } = armar({ respuesta });
  let primera = null;
  rep.iniciar(rec('a'));
  await reloj.avanzar(10);
  rep.iniciar(rec('b')).then((x) => { primera = [x, reloj.ahora()]; });
  await reloj.avanzar(1000);
  out.primera_del_nuevo = primera;
}
// Un detener que todavía quitaba la narración cuando llegó el nuevo: no lo pisa (ni su fase ni su primera escena)
{
  const respuesta = (o, reloj) => (o.orden === 'quitar_explicacion'
    ? new Promise((ok) => reloj.programar(() => ok({ ok: true }), 200)) : { ok: true });
  const { reloj, avances, rep } = armar({ respuesta });
  rep.iniciar(rec('a'));
  await reloj.avanzar(1000);
  const d = rep.detener('boton');
  const primera = rep.iniciar(rec('b'));
  await reloj.avanzar(1000);
  out.detener_y_nuevo = { detener: await d, primera: await primera, estado: rep.estado(), activo: rep.activo(),
    deB: avances.filter((x) => x[0] === 'b'), ultimaDeA: avances.filter((x) => x[0] === 'a').at(-1) };
}

// 3. Una frase que empezó a sonar y falló (el vigía venció) no espera su lectura entera ni da aviso de voz; una que no
// llegó a sonar, sí
{
  const voz = vozManual();
  const { reloj, ordenes, avances, rep } = armar({ voz });
  rep.iniciar(rec('c', { cierre: null, escenas: [esc(1, ['Frase uno.', 'Frase dos.', 'Frase tres.'])] }));
  await reloj.avanzar(RESPIRO_MS + 50);
  const f = {};
  // la primera suena 20 s (más que su lectura) y el vigía la da por fallida: la siguiente sale tras la pausa entre frases
  voz.empezar();
  await reloj.avanzar(20000);
  voz.terminar('fallo');
  await reloj.avanzar(ENTRE_FRASES_MS + 10);
  f.tras_vigia = voz.dichos.length;
  // la segunda suena 1 s y falla: espera lo que le falta de su lectura (lecturaMs - 1 s), no la lectura entera
  voz.empezar();
  await reloj.avanzar(1000);
  voz.terminar('fallo');
  const falta = lecturaMs('Frase dos.') - 1000;
  await reloj.avanzar(falta - 100);
  f.antes_de_lo_que_falta = voz.dichos.length;
  await reloj.avanzar(100 + ENTRE_FRASES_MS + 10);
  f.tras_lo_que_falta = voz.dichos.length;
  f.avisos_tras_sonar = avances.filter((x) => x.includes('?voz')).length;
  // la tercera no llega a sonar: aviso de voz, se muestra y se queda su lectura entera
  voz.terminar('fallo');
  await reloj.avanzar(10);
  f.avisos_sin_sonar = avances.filter((x) => x.includes('?voz')).length;
  f.mostrada = ordenes.at(-1);
  await reloj.avanzar(lecturaMs('Frase tres.') - 200);
  f.leyendo = rep.estado().fase;
  await reloj.avanzar(400);
  f.despues = rep.estado().fase;
  out.empezo_y_fallo = f;
}

// 4. El resumen del cierre: la pausa suave del chat lo deja terminar (y entra con motivo «mensaje»); una pausa dura lo
// corta y al seguir se repite
async function hastaElResumen() {
  const voz = vozManual();
  const a = armar({ voz });
  a.rep.iniciar(rec('d', { escenas: [esc(1, ['Frase uno.'])] }));
  await a.reloj.avanzar(RESPIRO_MS + 50);
  voz.empezar();
  voz.terminar('dicha');
  await a.reloj.avanzar(1100 + 50);   // sostener_ms
  return { ...a, voz };
}
{
  const { reloj, ordenes, avances, rep, voz } = await hastaElResumen();
  const c = { dice: voz.pendiente?.t };
  voz.empezar();
  rep.control('pausar', { suave: true });
  await reloj.avanzar(500);
  c.sigue = { fase: rep.estado().fase, sonando: voz.pendiente?.t ?? null };
  voz.terminar('dicha');
  await reloj.avanzar(10);
  c.entra = avances.at(-1);
  rep.continuar();
  await reloj.avanzar(CIERRE_SOSTENER_MS + 100);
  c.preguntas = ordenes.at(-1);
  c.resumenes = voz.dichos.filter((t) => t.startsWith('En resumen')).length;
  out.cierre_suave = c;
}
{
  const { reloj, rep, voz } = await hastaElResumen();
  voz.empezar();
  rep.pausar('boton');
  await reloj.avanzar(1000);
  const enPausa = voz.dichos.filter((t) => t.startsWith('En resumen')).length;
  rep.continuar();
  await reloj.avanzar(TICK_MS + 50);
  out.cierre_dura = { enPausa, tras_seguir: voz.dichos.filter((t) => t.startsWith('En resumen')), sonando: !!voz.pendiente };
}
// Detener mientras la primera escena todavía se prepara (responde a los 300 o a los 3000): igual sale la orden que la
// deja atrás. Si no, al asentarse narraba y dejaba tomado el teclado de la presentación
for (const tarda of [300, 3000]) {
  const respuesta = (o, reloj) => (o.orden === 'escena'
    ? new Promise((ok) => reloj.programar(() => ok({ ok: true }), tarda)) : { ok: true });
  const { reloj, ordenes, avances, rep } = armar({ respuesta });
  rep.iniciar(rec('e'));
  await reloj.avanzar(100);
  const detuvo = rep.detener('boton');
  await reloj.avanzar(4000);
  out[`detener_preparando_${tarda}`] = { detuvo: await detuvo, ordenes, ultimo: avances.at(-1) };
}
// Una pausa pedida apenas arranca: la primera escena se prepara, pero queda en pausa (y al seguir, narra)
{
  const { reloj, ordenes, avances, rep } = armar();
  rep.iniciar(rec('f'));
  rep.pausar('boton');
  await reloj.avanzar(1000);
  const enPausa = { estado: rep.estado(), avances: avances.slice(), ordenes: ordenes.slice() };
  rep.continuar();
  await reloj.avanzar(RESPIRO_MS + 50);
  out.pausa_al_arrancar = { enPausa, tras_seguir: rep.estado().fase };
}
console.log(JSON.stringify(out));
"""


@requiere_node
def test_el_reproductor_pausa_reemplazo_voz_que_falla_y_cierre(tmp_path):
    r = _node(tmp_path, NODE_REPRODUCTOR, REPRODUCTOR_JS.as_uri())
    # La persona movió la imagen con la pausa puesta: el motivo pasa a «persona» (una vez) y al seguir vuelve la escena
    b = r["persona_boton"]
    assert b["motivo"] == "a1/pausa!boton" and b["devuelve"] is True and b["avisos"] == 1
    assert b["avance"] == "a1/pausa!persona"
    assert b["ordenes"][:1] == ["escena:1"] and "narracion:pfalse" not in b["ordenes"], b
    # La pausa suave del chat entra al terminar la frase, con motivo «mensaje»; con la persona, igual vuelve
    m = r["persona_mensaje"]
    assert m["motivo"] == "a1/pausa!mensaje" and m["avance"] == "a1/pausa!persona" and m["ordenes"][:1] == ["escena:1"]
    # Reemplazo: el viejo termina con «detenido» por «reemplazo», antes de que el nuevo arranque
    for clave in ("reemplazo", "reemplazo_en_pausa"):
        x = r[clave]
        assert x["ultimaDeA"] == "a1/detenido!reemplazo" and x["aAntesQueB"] is True, (clave, x)
        assert x["primeraDeB"] == "b1/preparando" and x["primera"] is True and x["estado"]["rid"] == "b" * 12
        assert x["estado"]["fase"] == "narrando" and x["estado"]["pausado"] is False
    # El mismo recorrido otra vez: sin terminal, sigue desde la escena pedida
    assert r["mismo"]["terminales"] == [] and r["mismo"]["estado"]["n"] == 2
    # La escena vieja que responde tarde no da por fallida la primera del nuevo: esta resuelve cuando se ve (a los 510)
    assert r["primera_del_nuevo"] == [True, 510]
    # El detener que quitaba la narración no pisa al nuevo
    d = r["detener_y_nuevo"]
    assert d["detener"] is False and d["primera"] is True and d["activo"] is True and d["estado"]["rid"] == "b" * 12
    assert d["ultimaDeA"] == "a1/detenido!reemplazo"
    assert not any(_terminal(x) for x in d["deB"]), d
    # La frase que sonó y falló: sin aviso de voz y sin esperar la lectura entera; la que no sonó, con las dos cosas
    f = r["empezo_y_fallo"]
    assert f["tras_vigia"] == 2 and f["antes_de_lo_que_falta"] == 2 and f["tras_lo_que_falta"] == 3, f
    assert f["avisos_tras_sonar"] == 0 and f["avisos_sin_sonar"] == 1 and f["mostrada"] == "narracion:f2"
    assert f["leyendo"] == "narrando" and f["despues"] == "sosteniendo"
    # El resumen del cierre con la pausa suave: sigue sonando, la pausa entra al terminar y no se repite
    c = r["cierre_suave"]
    assert c["dice"] == "En resumen. Uno. Dos" and c["sigue"] == {"fase": "cierre", "sonando": "En resumen. Uno. Dos"}
    assert c["entra"] == "d1/pausa!mensaje" and c["preguntas"] == "cierre:preguntas" and c["resumenes"] == 1
    # Con una pausa dura se corta y al seguir se dice otra vez desde el comienzo
    assert r["cierre_dura"] == {"enPausa": 1, "tras_seguir": ["En resumen. Uno. Dos"] * 2, "sonando": True}
    # Detener con la primera escena en vuelo: después del detenido, la orden que la deja atrás
    for tarda in (300, 3000):
        x = r[f"detener_preparando_{tarda}"]
        assert x["detuvo"] is True and x["ultimo"] == "e1/detenido!boton", (tarda, x)
        assert x["ordenes"] == ["escena:1", "quitar_explicacion"], (tarda, x)
    # La pausa pedida al arrancar no se pierde cuando la primera escena empieza a prepararse
    p = r["pausa_al_arrancar"]
    assert p["enPausa"]["estado"]["fase"] == "pausa" and p["enPausa"]["estado"]["pausado"] is True, p
    assert "f1/preparando" not in p["enPausa"]["avances"][1:], p
    assert p["enPausa"]["ordenes"][:2] == ["escena:1", "narracion:ptrue"], p
    assert p["tras_seguir"] == "narrando", p


NODE_VOZ = r"""
const V = await import(process.argv[2]);
const out = {};
// partes: ninguna pasa de PARTIR y juntas son la frase (sin contar los espacios del corte)
const largos = {
  coma_al_comienzo: 'En Yondó, ' + 'el hospital atiende a toda la gente del municipio '.repeat(4).trim() + '.',
  con_lo_que_se_dice: V.paraDecir('La torre de 3.369,6 m² cumple la NSR-10 y la Res. 1633, con 146 pilotes de 15 m bajo la '
    + 'losa, 24 h de servicio y el 47 % del área para urgencias y consulta externa, en el predio del Centro Vida que se '
    + 'demuele entre 2028–2031 sin cerrar el hospital'),
  muy_larga: 'Primero, ' + 'una idea que se alarga bastante, '.repeat(12) + 'y el final.',
  sin_comas: 'palabra '.repeat(45).trim(),
  sin_espacios: 'x'.repeat(330),
  una_coma_al_medio: 'a'.repeat(90) + ', ' + 'b'.repeat(90),
};
const sinEspacios = (x) => x.replace(/\s+/g, '');
out.partes = Object.fromEntries(Object.entries(largos).map(([k, t]) => {
  const p = V.partes(t);
  return [k, { largo: [...t].length, partes: p.map((x) => [...x].length), juntas: sinEspacios(p.join('')) === sinEspacios(t) }];
}));
out.coma = V.partes(largos.una_coma_al_medio)[0].at(-1);
out.corta = V.partes('Hola, qué tal');
out.PARTIR = V.PARTIR;

// Una síntesis falsa que registra y quita oyentes (la ventana y `voiceschanged`)
const habladas = [];
class Locucion { constructor(t) { this.text = t; } }
const oyentes = (o) => { o.oy = {}; o.addEventListener = (n, f) => { (o.oy[n] ||= new Set()).add(f); };
  o.removeEventListener = (n, f) => { o.oy[n]?.delete(f); }; return o; };
const sintesis = oyentes({ voces: [], getVoices() { return this.voces; },
  cancel() { const u = this.actual; this.actual = null; u?.onerror?.({ error: 'interrupted' }); },
  speak(u) { if (!u.text) return; habladas.push(u.text); this.actual = u; setTimeout(() => { u.onstart?.(); if (this.modo !== 'colgada') setTimeout(() => { if (this.actual === u) { this.actual = null; u.onend?.(); } }, 5); }, 2); } });
const ventana = oyentes({ speechSynthesis: sintesis, SpeechSynthesisUtterance: Locucion });
const almacen = { d: { yj_voz: '1' }, getItem(k) { return this.d[k] ?? null; }, setItem(k, v) { this.d[k] = v; } };
const cuantos = (o, n) => o.oy[n]?.size || 0;

// gesto(): con la preferencia guardada la activa; apagada, no
const voz = V.crearVoz({ ventana, almacen });
out.oyentes = [cuantos(ventana, 'pointerdown'), cuantos(ventana, 'keydown'), cuantos(sintesis, 'voiceschanged')];
out.sin_activar = voz.estado();
voz.gesto();
out.tras_gesto = voz.estado();
sintesis.voces = [{ lang: 'es-CO', name: 'Colombia', localService: true }];
for (const f of sintesis.oy.voiceschanged) f();
// una frase larga se dice en partes de PARTIR como mucho
await voz.decir(largos.con_lo_que_se_dice);
out.habladas = habladas.map((x) => [...x].length);
const apagada = V.crearVoz({ ventana, almacen: { getItem: () => '0', setItem() {} } });
apagada.gesto();
out.gesto_apagada = apagada.estado();
apagada.soltar();
// soltar(): quita los oyentes de la ventana y de la síntesis, y corta lo que suena
sintesis.modo = 'colgada';
const p = voz.decir('Una frase que no termina');
await new Promise((r) => setTimeout(r, 10));
voz.soltar();
out.soltada = await p;
voz.soltar();   // dos veces no rompe
out.tras_soltar = [cuantos(ventana, 'pointerdown'), cuantos(ventana, 'keydown'), cuantos(sintesis, 'voiceschanged')];
console.log(JSON.stringify(out));
"""


@requiere_node
def test_la_voz_parte_bien_se_activa_con_un_gesto_y_se_suelta(tmp_path):
    r = _node(tmp_path, NODE_VOZ, VOZ_JS.as_uri())
    tope = r["PARTIR"]
    for nombre, x in r["partes"].items():
        assert x["largo"] > tope and len(x["partes"]) >= 2, (nombre, x)
        assert all(0 < n <= tope for n in x["partes"]) and x["juntas"] is True, (nombre, x)
    # la «, » pegada al comienzo no deja la otra parte casi tan larga como la frase
    assert r["partes"]["coma_al_comienzo"]["largo"] <= 2 * tope
    assert len(r["partes"]["coma_al_comienzo"]["partes"]) == 2
    # con lo que se dice (m², NSR-10, %…) la frase crece y se parte igual
    assert r["partes"]["con_lo_que_se_dice"]["largo"] > 220
    # con la coma cerca de la mitad, se corta ahí; una frase corta va entera
    assert r["partes"]["una_coma_al_medio"]["partes"] == [91, 90] and r["coma"] == ","
    assert r["corta"] == ["Hola, qué tal"]
    # gesto y soltar
    assert r["oyentes"] == [1, 1, 1]
    assert r["sin_activar"] == "sin_activar" and r["tras_gesto"] == "activa" and r["gesto_apagada"] == "apagada"
    assert len(r["habladas"]) >= 2 and all(n <= tope for n in r["habladas"])
    assert r["soltada"] == "cortada" and r["tras_soltar"] == [0, 0, 0]
