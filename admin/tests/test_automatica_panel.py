"""La presentación automática en el panel (la pantalla en off y el puente), con Node.

* El puente (admin/web/js/agente-presentacion.js): `estadoDePantalla` trae `auto` ({activa, capitulo, paso} o null; lo
  que no tiene la forma es null y el resto del estado vale igual) y deja pasar `recorrido.auto` solo cuando es `true`
  (el plan que armó la automática). La acción `recorrido` de la pestaña del chat no lleva esa clave.
* El reloj de la vista (`crearAutomatica` de vistas/presentacion.js), con un reloj de mentira: apagada no pide; al
  encenderla pide enseguida; con 204 (o un fallo) vuelve a pedir a los 5 s; con un plan en el reproductor no pide; a los
  1,5 s de terminar un plan automático, a los 5 s de uno del asistente (o de uno automático que no llegó a su final) y a
  los 45 s de otra orden suelta; manda lo último que pasó; una sola petición a la vez; apagada o soltada, nada más.
* Lo demás de la vista (el botón, el sondeo, la barra) necesita un navegador con la presentación cargada: aquí se
  comprueba por texto que está cableado (las rutas, el gesto de la voz, el plan sin la previa, quién avisa al reloj).
"""
import json
import re
import subprocess
from pathlib import Path

from test_agente_presentacion import requiere_node

ADMIN = Path(__file__).resolve().parents[1]
JS = ADMIN / "web" / "js"
PUENTE_JS = JS / "agente-presentacion.js"
VISTA_JS = JS / "vistas" / "presentacion.js"
CSS = ADMIN / "web" / "css" / "presentacion.css"


def _node(tmp_path: Path, guion: str, *args: str, timeout: int = 90) -> dict:
    (tmp_path / "prueba.mjs").write_text(guion, encoding="utf-8")
    p = subprocess.run(["node", str(tmp_path / "prueba.mjs"), *args], capture_output=True, text=True, timeout=timeout,
                       cwd=ADMIN)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout.strip().splitlines()[-1])


# ───────────────────────────── El puente: `auto` y `recorrido.auto` ─────────────────────────────

NODE_PUENTE = r"""// El estado de la pantalla en off con la presentación automática. Uso: node <guion> <agente-presentacion.js>
const [modulo] = process.argv.slice(2);
globalThis.document = { querySelector: () => null };
globalThis.location = { pathname: '/panel/presentacion', origin: 'https://panel.example' };
globalThis.addEventListener = () => {};
globalThis.BroadcastChannel = class { postMessage() {} close() {} };
const P = await import(modulo);
const r = {};
const V = { enfoque: null, camara: 'paso', rumbo: null, elevacion: null, zoom: null, mirar: null, girar: false, comparar: 'proyecto',
  detalle: null, inmersion: null, mostrar: [], ocultar: [], aislar: null, sin: [] };
const escena = (paso) => ({ capitulo: 'salud', paso, panel: true, visual: { ...V, mostrar: [], ocultar: [], sin: [] }, resaltar: null,
  mover: { giro: paso % 2 ? 14 : -14 }, animar: true, frases: [`Salud, paso ${paso}: lo esencial.`], sostener_ms: 1300 });
const plan = { id: 'abcdef123456', titulo: 'Salud', escenas: [escena(1), escena(2), escena(3)], cierre: null };
const base = { v: 7, capitulo: 'salud', paso: 3, explicacion: null, panel: true, indice: false, fichas: false, completa: false, orden_completa: 0 };
const E = (extra) => P.estadoDePantalla({ ...base, ...extra });

// `auto`: sin la clave (un servidor de antes) y en null es null; con la forma, sale copiada y solo con sus tres claves
r.sin_clave = E({}).auto;
r.en_null = E({ auto: null }).auto;
const dicha = { activa: true, capitulo: 'salud', paso: 3 };
const leida = E({ auto: dicha }).auto;
r.valida = leida;
r.copiada = leida !== dicha;
r.apagada = E({ auto: { activa: false, capitulo: 'portada', paso: 1 } }).auto;
r.con_de_mas = E({ auto: { activa: true, capitulo: 'aguas', paso: 60, rid: 'abcdef123456', vueltas: 2, nombre: 'Aguas', de: 5 } }).auto;
// lo que no tiene la forma: `auto` queda en null y el resto del estado sigue valiendo
const malas = [{ capitulo: 'salud', paso: 3 }, { activa: 'si', capitulo: 'salud', paso: 3 }, { activa: 1, capitulo: 'salud', paso: 3 },
  { activa: true, paso: 3 }, { activa: true, capitulo: 'Salud', paso: 3 }, { activa: true, capitulo: 7, paso: 3 }, { activa: true, capitulo: '', paso: 3 },
  { activa: true, capitulo: 'salud' }, { activa: true, capitulo: 'salud', paso: 0 }, { activa: true, capitulo: 'salud', paso: -1 },
  { activa: true, capitulo: 'salud', paso: 1.5 }, { activa: true, capitulo: 'salud', paso: '3' }, { activa: true, capitulo: 'salud', paso: null },
  [true, 'salud', 3], 'activa', 7, true];
r.malas = malas.map((auto) => { const e = E({ auto }); return e === null ? 'estado nulo' : e.auto; });
r.malas_siguen = malas.every((auto) => E({ auto })?.capitulo === 'salud');

// `recorrido.auto`: solo `true` pasa (la clave viaja solo cuando el plan es de la automática); lo demás del plan, igual
const conPlan = (extra) => E({ recorrido: { ...plan, edad_s: 2, ...extra }, auto: dicha }).recorrido;
r.plan_auto = conPlan({ auto: true })?.auto ?? null;
r.plan_auto_entero = (() => { const x = conPlan({ auto: true }); const { auto: _a, edad_s, ...resto } = x; return edad_s === 2 && JSON.stringify(resto) === JSON.stringify(plan); })();
r.plan_del_asistente = Object.keys(conPlan({})).sort();
r.auto_que_no_es_true = [false, 'true', 1, null, {}].map((auto) => 'auto' in conPlan({ auto }));
r.plan_malo_con_auto = E({ recorrido: { ...plan, escenas: [], edad_s: 2, auto: true } }).recorrido;
// su avance y su control llegan como los de cualquier plan
const sonando = E({ recorrido: { ...plan, edad_s: 9, auto: true }, auto: dicha, progreso: { rid: plan.id, n: 2, de: 3, fase: 'narrando', hace_s: 1 },
  control_recorrido: { rid: plan.id, accion: 'pausar', n: 1 } });
r.avance = [sonando.progreso, sonando.control_recorrido];
// La acción `recorrido` (la pestaña del chat, el proyector) no lleva la clave: el plan automático solo va a la pantalla en off
r.accion_con_auto = [P.recorridoValido({ ...plan, auto: true }), P.accionPresentacion({ tipo: 'presentacion', op: 'recorrido', recorrido: { ...plan, auto: true } })];
r.accion_sin_auto = !!P.recorridoValido(plan);
// y no cambia lo que se le manda a la presentación: encender o apagar la automática no es una orden
r.ordenes = [P.ordenesHacia(E({ auto: null }), E({ auto: dicha })), P.ordenesHacia(E({ auto: dicha }), E({ auto: { ...dicha, activa: false } }))];
console.log(JSON.stringify(r));
process.exit(0);
"""


@requiere_node
def test_el_puente_lee_auto_valido_e_invalido(tmp_path):
    r = _node(tmp_path, NODE_PUENTE, PUENTE_JS.as_uri())
    assert r["sin_clave"] is None and r["en_null"] is None
    assert r["valida"] == {"activa": True, "capitulo": "salud", "paso": 3} and r["copiada"] is True
    assert r["apagada"] == {"activa": False, "capitulo": "portada", "paso": 1}
    # lo que el servidor guarde de más (el plan en curso, las vueltas) no pasa a la vista
    assert r["con_de_mas"] == {"activa": True, "capitulo": "aguas", "paso": 60}
    assert r["malas"] == [None] * 17, r["malas"]
    assert r["malas_siguen"] is True


@requiere_node
def test_el_puente_marca_el_plan_de_la_automatica(tmp_path):
    r = _node(tmp_path, NODE_PUENTE, PUENTE_JS.as_uri())
    assert r["plan_auto"] is True and r["plan_auto_entero"] is True
    assert r["plan_del_asistente"] == ["cierre", "edad_s", "escenas", "id", "titulo"]
    assert r["auto_que_no_es_true"] == [False] * 5
    assert r["plan_malo_con_auto"] is None
    assert r["avance"] == [{"rid": "abcdef123456", "n": 2, "de": 3, "fase": "narrando", "hace_s": 1},
                           {"rid": "abcdef123456", "accion": "pausar", "n": 1}]
    assert r["accion_con_auto"] == [None, None] and r["accion_sin_auto"] is True
    assert r["ordenes"] == [[], []]


# ───────────────────────────── El reloj de la vista ─────────────────────────────

NODE_RELOJ = r"""// `crearAutomatica` con un reloj de mentira. Uso: node <guion> <vistas/presentacion.js>
globalThis.document = { querySelector: () => null };
globalThis.location = { pathname: '/panel/presentacion', origin: 'https://panel.example' };
globalThis.addEventListener = () => {};
globalThis.BroadcastChannel = class { postMessage() {} close() {} };
const V = await import(process.argv[2]);
const { crearAutomatica, ESPERA_AUTO_MS, ESPERA_TRAS_PLAN_MS, ESPERA_TRAS_ORDEN_MS, REINTENTO_AUTO_MS } = V;
function relojFalso() {
  let t = 0, id = 0; const cola = new Map();
  return { ahora: () => t, programar(f, ms) { const h = ++id; cola.set(h, { f, en: t + ms }); return h; }, cancelar(h) { cola.delete(h); },
    pendientes: () => cola.size,
    async avanzar(ms) { const fin = t + ms; for (;;) { await new Promise((r) => setImmediate(r)); let p = null;
      for (const [h, x] of cola) if (x.en <= fin && (!p || x.en < p[1].en)) p = [h, x]; if (!p) break; cola.delete(p[0]); t = p[1].en; p[1].f(); }
      t = fin; for (let i = 0; i < 5; i++) await new Promise((r) => setImmediate(r)); } };
}
// `respuestas`: lo que responde cada petición (true: 200, armó un plan; false: 204; 'falla'; una función que devuelve
// una promesa). Agotadas, 204
function armar(respuestas = []) {
  const reloj = relojFalso(), pedidos = [], armados = [], s = { ocupado: false };
  let k = 0;
  const A = crearAutomatica({ reloj, ocupado: () => s.ocupado, alArmar: () => armados.push(reloj.ahora()),
    pedir: () => { pedidos.push(reloj.ahora()); const x = respuestas[k++]; if (x === 'falla') return Promise.reject(new Error('sin conexión'));
      return typeof x === 'function' ? x() : Promise.resolve(x === true); } });
  return { reloj, pedidos, armados, s, A };
}
const out = { tiempos: [ESPERA_AUTO_MS, ESPERA_TRAS_PLAN_MS, ESPERA_TRAS_ORDEN_MS, REINTENTO_AUTO_MS], exports: Object.keys(V).sort() };

// 1. Apagada no pide nada, pase lo que pase
{
  const { reloj, pedidos, A } = armar();
  A.alTerminar({ auto: true, fase: 'fin' }); A.alOrden(); A.alTerminar({ auto: false, fase: 'fin' });
  await reloj.avanzar(120000);
  out.apagada = { pedidos, estado: A.estado(), relojes: reloj.pendientes() };
}

// 2. Al encenderla pide enseguida; con 204 vuelve a los 5 s; con 200 avisa (`alArmar`) y, con el plan ya en el
// reproductor, no pide más; a los 1,5 s de terminar ese plan (automático, hasta su final) pide el siguiente
{
  const { reloj, pedidos, armados, s, A } = armar([false, false, true, true]);
  A.fijar(true);
  A.fijar(true);   // el servidor lo repite en cada estado: no es encenderla otra vez
  const alEncender = A.estado();
  await reloj.avanzar(1);
  const enseguida = pedidos.slice();
  await reloj.avanzar(4998);
  const casi = pedidos.length;
  await reloj.avanzar(1);
  const alos5 = pedidos.slice();
  await reloj.avanzar(5000);
  const con200 = { pedidos: pedidos.slice(), armados: armados.slice() };
  s.ocupado = true;   // el plan llegó por el sondeo
  await reloj.avanzar(60000);
  const sonando = { pedidos: pedidos.length, estado: A.estado().activa };
  s.ocupado = false;
  const t = reloj.ahora();
  A.alTerminar({ auto: true, fase: 'fin' });
  await reloj.avanzar(ESPERA_AUTO_MS - 1);
  const antes = pedidos.length;
  await reloj.avanzar(1);
  out.encender = { alEncender, enseguida, casi, alos5, con200, sonando, antes, siguiente: pedidos.at(-1) - t, total: pedidos.length };
}

// 3. Lo que espera según lo que terminó: un plan del asistente, 5 s; uno automático que no llegó a su final (lo
// cortaron, falló), también 5 s; otra orden suelta, 45 s. (Se enciende con un plan ya sonando: no pide hasta que termina)
{
  const espera = async (evento) => {
    const { reloj, pedidos, s, A } = armar();
    s.ocupado = true;
    A.fijar(true);
    await reloj.avanzar(20000);
    s.ocupado = false;
    const t = reloj.ahora();
    evento(A);
    await reloj.avanzar(60000);
    return pedidos.map((x) => x - t);
  };
  out.esperas = {
    auto_fin: await espera((A) => A.alTerminar({ auto: true, fase: 'fin' })),
    plan_fin: await espera((A) => A.alTerminar({ auto: false, fase: 'fin' })),
    plan_detenido: await espera((A) => A.alTerminar({ auto: false, fase: 'detenido' })),
    auto_detenido: await espera((A) => A.alTerminar({ auto: true, fase: 'detenido' })),
    auto_error: await espera((A) => A.alTerminar({ auto: true, fase: 'error' })),
    orden: await espera((A) => A.alOrden()),
  };
}

// 4. Manda lo último que pasó: una orden suelta y, a los 10 s, un plan del asistente que termina → 5 s desde ese final;
// un plan automático que termina y, al segundo, una orden suelta → 45 s desde la orden
{
  const a = armar();
  a.s.ocupado = true;
  a.A.fijar(true);
  await a.reloj.avanzar(10000);
  a.s.ocupado = false;
  const t = a.reloj.ahora();
  a.A.alOrden();
  await a.reloj.avanzar(10000);
  a.A.alTerminar({ auto: false, fase: 'fin' });
  await a.reloj.avanzar(30000);
  const b = armar();
  b.s.ocupado = true;
  b.A.fijar(true);
  await b.reloj.avanzar(10000);
  b.s.ocupado = false;
  const u = b.reloj.ahora();
  b.A.alTerminar({ auto: true, fase: 'fin' });
  await b.reloj.avanzar(1000);
  b.A.alOrden();
  await b.reloj.avanzar(44999);
  const casi = b.pedidos.length;
  await b.reloj.avanzar(1);
  out.ultimo = { orden_y_plan: a.pedidos.map((x) => x - t), plan_y_orden: { casi, pedidos: b.pedidos.map((x) => x - u) } };
}

// 5. Una sola petición a la vez: mientras el servidor no responde, nada dispara otra; al responder (204) vuelve a los
// 5 s; y si entretanto llegó una orden suelta, vale su espera (la más larga)
{
  let responder = null;
  const lenta = () => new Promise((ok) => { responder = ok; });
  const a = armar([lenta, false]);
  a.A.fijar(true);
  await a.reloj.avanzar(1);
  const enVuelo = a.A.estado();
  a.A.alTerminar({ auto: true, fase: 'fin' });
  a.A.fijar(false); a.A.fijar(true);
  await a.reloj.avanzar(20000);
  const durante = a.pedidos.length;
  const t = a.reloj.ahora();
  responder(false);
  await a.reloj.avanzar(REINTENTO_AUTO_MS - 1);
  const casi = a.pedidos.length;
  await a.reloj.avanzar(1);
  const b = armar([lenta]);
  b.A.fijar(true);
  await b.reloj.avanzar(1000);
  b.A.alOrden();   // en t = 1000
  await b.reloj.avanzar(2000);
  responder(true);
  await b.reloj.avanzar(60000);
  out.una_a_la_vez = { enVuelo, durante, casi, despues: a.pedidos.map((x) => x - t).slice(1), con_orden: b.pedidos, armado_con_orden: b.armados };
}

// 6. Sin conexión (la petición falla) se vuelve a pedir a los 5 s, sin lanzar
{
  const { reloj, pedidos, armados, A } = armar(['falla', 'falla', true]);
  A.fijar(true);
  await reloj.avanzar(12000);
  out.falla = { pedidos, armados };
}

// 7. Apagarla deja de pedir (también con una espera pendiente); encenderla otra vez pide enseguida
{
  const { reloj, pedidos, A } = armar([false, false, false]);
  A.fijar(true);
  await reloj.avanzar(1);
  A.fijar(false);
  const estado = A.estado();
  await reloj.avanzar(60000);
  const apagada = pedidos.length;
  A.alOrden();   // lo que pase apagada no deja una espera para después
  await reloj.avanzar(3000);
  const t = reloj.ahora();
  A.fijar(true);
  await reloj.avanzar(1);
  out.apagar = { estado, apagada, relojes_apagada: apagada === pedidos.length - 1, otra_vez: pedidos.at(-1) - t, total: pedidos.length };
}

// 8. Con un plan en el reproductor al encenderla no pide; si ese plan se va sin avisar, vuelve a mirar y pide
{
  const a = armar([true]);
  a.s.ocupado = true;
  a.A.fijar(true);
  await a.reloj.avanzar(30000);
  const ocupada = a.pedidos.length;
  a.s.ocupado = false;
  const t = a.reloj.ahora();
  await a.reloj.avanzar(REINTENTO_AUTO_MS);
  out.ocupado = { ocupada, sin_aviso: a.pedidos.map((x) => x - t).every((x) => x >= 0 && x <= REINTENTO_AUTO_MS) && a.pedidos.length === 1 };
}

// 9. Soltada (la vista se cerró) no pide ni programa nada, ni con una respuesta que llega tarde
{
  let responder = null;
  const { reloj, pedidos, armados, A } = armar([() => new Promise((ok) => { responder = ok; })]);
  A.fijar(true);
  await reloj.avanzar(1);
  A.soltar();
  responder(true);
  A.alTerminar({ auto: true, fase: 'fin' }); A.alOrden(); A.fijar(false); A.fijar(true);
  await reloj.avanzar(120000);
  out.soltada = { pedidos: pedidos.length, armados, relojes: reloj.pendientes() };
}
console.log(JSON.stringify(out));
process.exit(0);
"""


@requiere_node
def test_el_reloj_de_la_automatica_pide_cuando_toca(tmp_path):
    r = _node(tmp_path, NODE_RELOJ, VISTA_JS.as_uri())
    # los tiempos del contrato
    assert r["tiempos"] == [1500, 5000, 45000, 5000]
    assert r["exports"] == ["ESPERA_AUTO_MS", "ESPERA_TRAS_ORDEN_MS", "ESPERA_TRAS_PLAN_MS", "REINTENTO_AUTO_MS",
                            "crearAutomatica", "vistaPresentacion"]
    assert r["apagada"] == {"pedidos": [], "estado": {"activa": False, "pidiendo": False, "en_ms": None}, "relojes": 0}
    e = r["encender"]
    assert e["alEncender"] == {"activa": True, "pidiendo": False, "en_ms": 0}
    assert e["enseguida"] == [0] and e["casi"] == 1 and e["alos5"] == [0, 5000], e
    # la tercera (200) avisa para adelantar el sondeo; con el plan sonando no se pide en un minuto
    assert e["con200"] == {"pedidos": [0, 5000, 10000], "armados": [10000]}, e
    assert e["sonando"] == {"pedidos": 3, "estado": True}
    assert e["antes"] == 3 and e["siguiente"] == 1500 and e["total"] == 4, e
    # cada espera, exacta (con el plan sonando no pidió nada antes), y después sigue sola (204: otra vez a los 5 s)
    x = r["esperas"]
    assert x["auto_fin"][0] == 1500 and x["plan_fin"][0] == 5000 and x["orden"][0] == 45000, x
    assert x["plan_detenido"][0] == 5000 and x["auto_detenido"][0] == 5000 and x["auto_error"][0] == 5000, x
    assert x["auto_fin"][:3] == [1500, 6500, 11500] and x["orden"] == [45000, 50000, 55000, 60000], x


@requiere_node
def test_el_reloj_de_la_automatica_no_se_pisa(tmp_path):
    r = _node(tmp_path, NODE_RELOJ, VISTA_JS.as_uri())
    u = r["ultimo"]
    assert u["orden_y_plan"][0] == 15000, u
    assert u["plan_y_orden"] == {"casi": 0, "pedidos": [46000]}, u
    v = r["una_a_la_vez"]
    assert v["enVuelo"] == {"activa": True, "pidiendo": True, "en_ms": None}
    assert v["durante"] == 1 and v["casi"] == 1 and v["despues"] == [5000], v
    # la orden suelta llegó en t = 1000 con la petición en vuelo: la siguiente sale a los 45 s de la orden, y el plan que
    # esa petición armó se avisa igual
    assert v["con_orden"][:2] == [0, 46000] and v["armado_con_orden"] == [3000], v
    assert r["falla"] == {"pedidos": [0, 5000, 10000], "armados": [10000]}
    a = r["apagar"]
    assert a["estado"] == {"activa": False, "pidiendo": False, "en_ms": None} and a["apagada"] == 1, a
    assert a["otra_vez"] == 0 and a["total"] == 2, a
    assert r["ocupado"] == {"ocupada": 0, "sin_aviso": True}
    assert r["soltada"] == {"pedidos": 1, "armados": [], "relojes": 0}


# ───────────────────────────── La vista, por texto ─────────────────────────────

def test_la_vista_cablea_el_boton_el_sondeo_y_la_barra():
    """La vista en modo en off necesita un navegador con la presentación cargada (un iframe, postMessage, la maqueta 3D):
    lo que hace con el reloj se comprueba por texto. De punta a punta se probó en Chromium contra una API simulada."""
    vista = VISTA_JS.read_text(encoding="utf-8")
    # el botón: solo en la barra del modo en off, con su estado y su texto; apagado hasta que la presentación cargó
    barra_off = vista[vista.index('aria-label="Pantalla en off"'):vista.index('pres-off-aviso')]
    boton = re.search(r'<button type="button" class="btn pres-auto" id="pres-auto"[^>]*>.*?</button>', barra_off)
    assert boton and 'aria-pressed="false"' in boton[0] and "<span>Presentación automática</span>" in boton[0]
    assert 'aria-label="Presentación automática"' in boton[0] and " disabled>" in boton[0]
    assert vista.count('id="pres-auto"') == 1
    assert "botonAuto.setAttribute('aria-pressed', String(activa));" in vista
    assert "if (botonAuto) botonAuto.disabled = false;" in vista
    # el clic: el gesto que deja hablar a la voz, y enciende o apaga en el servidor
    clic = vista[vista.index("botonAuto.addEventListener('click'"):vista.index("limpiezas.push(() => clearTimeout(tAvisoAuto));")]
    assert clic.index("voz.gesto();") < clic.index("api.post('/api/pantalla/auto'")
    assert "api.post('/api/pantalla/auto', { accion: encender ? 'iniciar' : 'detener' })" in clic
    assert "const encender = !auto?.activa;" in clic and "autoRespondida(r?.auto)" in clic
    # al apagarla su plan se calla ya
    assert "if (!auto?.activa && rep.activo() && rep.recorrido()?.id === ridAuto) rep.detener('otra_orden')" in clic
    # el reloj: pide el siguiente (200 con cuerpo: armó uno; 204: nada), solo con el reproductor sin plan
    assert "const r = await api.post('/api/pantalla/auto/siguiente'); return !!r && typeof r === 'object';" in vista
    assert "ocupado: () => rep.activo()," in vista and "alArmar: () => adelantarSondeo?.()," in vista
    assert "const automatica = off ? crearAutomatica({" in vista and "limpiezas.push(() => automatica?.soltar());" in vista
    # quién le avisa: el estado del servidor (antes de mirar el plan), el final de cada plan y la orden suelta
    sondeo = vista[vista.index("async function seguirAlServidor()"):]
    assert sondeo.index("alAuto(e.auto);") < sondeo.index("await recorridoDeLaPantalla(e);")
    assert "automatica?.fijar(!!a?.activa);" in vista
    assert "automatica.alTerminar({ auto: pr.rid === ridAuto, fase: pr.fase });" in vista
    assert "if (ordenes.length && aplicado) automatica.alOrden();" in sondeo
    # el plan de la automática: se reconoce por `auto`, no espera la previa y esa clave no llega al reproductor
    assert "const esAuto = x.auto === true;" in vista and "if (esAuto) {\n        ridAuto = x.id;" in vista
    assert "const { edad_s: _edad, auto: _auto, ...r } = x;" in vista
    assert "previa: nuevo && !pr && !esAuto }" in vista
    # con ella encendida no queda callado un plan que el servidor da por sonando: el suyo se retoma siempre; el del
    # asistente, con un avance de hace menos de VIGENCIA_RECORRIDO_S (apagada, como antes: REANUDAR_S)
    assert "const reanudar = !sigue ? REANUDAR_S : esAuto ? Infinity : VIGENCIA_RECORRIDO_S;" in vista
    assert "(pr.fase === 'pausa' || pr.hace_s < reanudar) ? pr.n : 0;" in vista
    assert "else if (x.edad_s < VIGENCIA_RECORRIDO_S || (sigue && esAuto)) desde = 1;" in vista
    # la barra: «Presentación automática · Salud · paso 3 de 10»
    assert "`Presentación automática · ${sigue ? 'sigue en ' : ''}${nombre} · paso ${paso}${c?.total >= paso ? ` de ${c.total}` : ''}`" in vista
    assert "rep.recorrido().id === ridAuto" in vista
    # la pantalla sigue diciendo que está conectada (lo espera la prueba del modo en off con el servidor de verdad)
    assert "'Conectada' : 'Conectada: asistente y agentes por MCP'" in vista
    # nada del servidor entra como HTML: los textos de la barra van por textContent
    assert "innerHTML" not in vista
    css = CSS.read_text(encoding="utf-8")
    assert '.pres-auto[aria-pressed="true"]' in css and ".presentacion.en-off[data-auto] .pres-donde" in css
