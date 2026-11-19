// Lo que el asistente del panel y los agentes por MCP pueden cambiar de lo que se ve en la presentación técnica, sin
// cambiar de paso (las órdenes `visual` y `escena` de mando.js; la herramienta `presentacion`):
// * camara: el encuadre del paso ('paso'), una vista aérea, oblicua o rasante, más cerca o más lejos (alias de una
//   elevación y un acercamiento fijos); rumbo: desde dónde se mira, en grados desde el norte (null, el del paso);
//   elevacion: grados sobre el horizonte (8–85); zoom: cuánto más cerca que el encuadre del paso (1 = igual, 2 = el doble
//   de cerca); con valor, elevación y zoom mandan sobre lo que implique `camara`. girar: la cámara gira despacio.
// * mirar: a qué apunta la cámara SIN cambiar lo que se ve: una pieza del catálogo o un componente con lugar.
// * enfoque: la cámara va a un componente del capítulo (el id de la propuesta): al paso que lo desarrolla (con sus capas),
//   a sus sitios o trazados de geo.json o a la réplica de una sede (`enfoque` de cada componente, build_propuesta.py).
// * comparar: 'hoy' deja el sitio como está (sin las capas del proyecto, con las casas y las sedes de hoy) en el mismo
//   encuadre; 'proyecto' lo devuelve. En una inmersión cambia el modo del atlas («Hoy»).
// * mostrar, ocultar, aislar y sin: las piezas de la maqueta (el catálogo `tecnica.maqueta` de propuesta.json, por
//   capítulo: capas de los módulos, grupos dentro de ellas, réplicas de sedes y partes que se les quitan). `mostrar`
//   enciende piezas además de las del paso; `ocultar` las apaga aunque el paso las muestre; `aislar` deja solo una (lo
//   demás del capítulo se apaga, o queda en gris translúcido si comparte capa con ella, y las cubiertas del pueblo pasan a
//   gris); `sin` quita partes («torre.cubierta» deja ver las losas). Todo va ENCIMA de lo del paso y se deshace solo.
// * detalle: la ficha técnica de un componente en un panel lateral (lo que hace, especificaciones sin plata, referente
//   técnico, dónde y plazo).
// * inmersion: un modelo del atlas a pantalla completa (la torre por dentro, el simulador sísmico, el modelo BIM, el
//   parque del relleno), en un marco del mismo origen que habla con js/escenario.js. 'maqueta' la cierra en un paso de
//   inmersión; null, lo del paso.
// * tema: claro u oscuro (para el proyector), también en el atlas enmarcado.
// Todo vuelve a como lo dice el paso al cambiar de paso, salvo el tema.
// Y tres acciones que no son estado: `mover` (la cámara gira, se acerca o cambia de elevación despacio, lo que dure la
// frase), `animar` (repite la animación propia del paso) y `simular` (acciona los controles del modelo a la vista: con un
// modelo del atlas abierto, los de adentro —la magnitud del simulador sísmico, hacerlo temblar, el piso, el 4D del BIM—
// con `__escenario.simular` de js/escenario.js, como los acciona la persona; sin él, los de la maqueta 3D —la hora del
// día, el día entero, las luces, el partido en la cancha— con simulacion.js, que también vuelven a lo del paso al
// cambiar de paso; lo que no se acepta vuelve como descartado). Con `ms`, `aplicar` cambia en el acto lo que se ve y lleva la
// cámara a su postura con un PASEO de esa duración (Stage.pasear de core.js: no es un vuelo, nada lo espera): así el
// asistente muestra MIENTRAS explica. Con una narración en pantalla (`guiado`) los módulos no mueven la cámara.
// Las comprobaciones de forma (tipos, listas) las hace mando.js; aquí, las que dependen de lo que hay (`depurar` quita lo
// que no existe en el capítulo y dice por qué; `validar` es la estricta de antes).
import { THREE, gsap, reducedMotion, solidBox } from '../core.js';
import { sinPlata, especificacionTecnica, anios } from './tecnica.js';
import { caja } from './modulos/comun.js';
import { crearSimulacion } from './simulacion.js';

export const CAMARAS = ['paso', 'aerea', 'oblicua', 'rasante', 'cerca', 'lejos'];
// elevación (grados sobre el horizonte) y cuánto más grande queda la obra en la zona libre (el `margen` de encuadrar)
const PRESET = { paso: {}, aerea: { elev: 80 }, oblicua: { elev: 34 }, rasante: { elev: 11, k: 1.1 }, cerca: { k: 1.9 }, lejos: { k: 0.5 } };
const LISTAS = ['mostrar', 'ocultar', 'sin'];
// lo visual de un paso recién puesto (las listas se copian al usarlo: `inicial`)
export const INICIAL = Object.freeze({ enfoque: null, camara: 'paso', rumbo: null, elevacion: null, zoom: null, mirar: null, girar: false, comparar: 'proyecto', detalle: null, inmersion: null, mostrar: [], ocultar: [], aislar: null, sin: [] });
const inicial = () => ({ ...INICIAL, mostrar: [], ocultar: [], sin: [] });
const ELEV = [8, 85], ZOOM = [0.3, 3];       // lo que admite la cámara (OrbitControls recorta por debajo de 7,2°)
const PASEO_MS = [1200, 20000], MOVER_MS = 6000;
const VUELTA_S = 70;   // segundos por vuelta con «girar»
const ESPERA_ATLAS_MS = 30000;

const esc = (t) => String(t ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

export function crearVisual({ escena, datos, caps, estado, ctx3d, pres, pasar3D, colorDe }) {
  const vis = { ...inicial(), tema: null };
  const tec = datos.tecnica || {};
  const catalogo = new Map((tec.inmersiones || []).map((i) => [i.id, i]));
  const st = escena.st;
  const cap = () => caps[estado.ci], paso = () => cap()?.pasos[estado.pi];
  const compDe = (c, id) => (c?.componentes || []).find((x) => x.id === id) || null;
  const comp = (id) => compDe(cap(), id);
  const avisar = () => dispatchEvent(new CustomEvent('propuesta:visual', { detail: estadoVisual() }));
  const entre = (v, [a, b]) => Math.min(b, Math.max(a, v));
  // el catálogo de piezas de cada capítulo (`tecnica.maqueta`): id de pieza → { id, nombre, capas, grupos?, replica?, efecto?, partes? }
  const maqueta = tec.maqueta && typeof tec.maqueta === 'object' ? tec.maqueta : {};
  const mapas = new Map();
  const piezasDe = (c) => {
    if (!c) return new Map();
    if (!mapas.has(c.id)) mapas.set(c.id, new Map((Array.isArray(maqueta[c.id]) ? maqueta[c.id] : []).filter((x) => x && typeof x.id === 'string').map((x) => [x.id, { ...x, capas: Array.isArray(x.capas) ? x.capas : [] }])));
    return mapas.get(c.id);
  };
  const parteDe = (x, id) => (x?.partes || []).find((k) => k.id === id) || null;
  // las simulaciones de la maqueta 3D (la hora, el día, las luces, el partido): `simular` sin un modelo del atlas abierto
  const sim = crearSimulacion({ escena, ctx3d, datos, caps, estado, enEncuadre });

  // ¿Queda `obj` (una pieza de la maqueta) en el encuadre? Se mira desde donde queda la cámara: la postura del último
  // encuadre (el del paso, con lo que pide lo visual: cámara, enfoque, mirar, el final de un `mover`) aunque la cámara
  // todavía vaya de camino (el vuelo o el paseo de una escena), o donde la dejó la persona. Su caja, proyectada, tiene
  // que caer en la zona libre (sin el panel, la ficha ni el subtítulo) con al menos ENCUADRE_MIN del ancho y del alto
  // de esa zona, y con la mitad de la caja dentro (o llenándola, si la cámara está encima). Así el partido no se da por
  // jugado en un paso que encuadra otra obra (las canchas cubiertas junto al CIC)
  const ENCUADRE_MIN = 0.06;
  function enEncuadre(obj) {
    if (!obj?.isObject3D) return true;
    const caja = new THREE.Box3().setFromObject(obj);
    if (caja.isEmpty()) return false;
    const cam = st.camera.clone(), v = new THREE.Vector3();
    cam.far = 1e7;
    const p = !st.userMoved && ultimo ? escena.postura(ultimo.obj, opcionesDe(ultimo.opts)) : null;
    if (p) { cam.position.fromArray(p.pos); cam.lookAt(v.fromArray(p.tgt)); }
    cam.updateMatrixWorld(); cam.updateProjectionMatrix();
    const b = [Infinity, -Infinity, Infinity, -Infinity];
    for (let i = 0; i < 8; i++) {
      v.set(i & 1 ? caja.max.x : caja.min.x, i & 2 ? caja.max.y : caja.min.y, i & 4 ? caja.max.z : caja.min.z)
        .applyMatrix4(cam.matrixWorldInverse);
      if (v.z > -cam.near) continue;   // detrás de la cámara: solo cuenta lo que tiene delante
      v.applyMatrix4(cam.projectionMatrix);
      b[0] = Math.min(b[0], v.x); b[1] = Math.max(b[1], v.x); b[2] = Math.min(b[2], v.y); b[3] = Math.max(b[3], v.y);
    }
    if (!(b[1] > b[0] && b[3] > b[2])) return false;
    const z = escena.zona(), zw = z.x1 - z.x0, zh = z.y1 - z.y0;
    const iw = Math.max(0, Math.min(b[1], z.x1) - Math.max(b[0], z.x0)), ih = Math.max(0, Math.min(b[3], z.y1) - Math.max(b[2], z.y0));
    if (iw < zw * ENCUADRE_MIN || ih < zh * ENCUADRE_MIN) return false;
    return (iw * ih) / ((b[1] - b[0]) * (b[3] - b[2])) >= 0.5 || (iw >= zw * 0.5 && ih >= zh * 0.5);
  }

  // ---------------------------------------------------------------- encuadres con la cámara pedida
  // Todos los encuadres de los módulos pasan por aquí: se guarda el último (para repetirlo con otra cámara o para llevar
  // la cámara hasta él con un paseo) y se le aplican el rumbo, la elevación y el acercamiento vigentes. «En seco»
  // (enSeco) o con `vuelo: false` solo queda anotado, con lo que los rótulos esquivan: la cámara no se mueve
  // Además se guarda aparte lo que encuadró el paso al llegar (`delPaso`): mientras se siga en él no se vuelve a medir
  // (sus piezas pueden estar a medio crecer, y la caja saldría sin ellas), salvo que haya llegado el modelo de una sede
  let ultimo = null, seco = 0, delPaso = null, interno = 0;
  const pasoAnotado = (clave) => delPaso?.clave === clave && delPaso.n === escena.cargados();
  // con cuáles terminó el último `mover` ({ rumbo, elev, zoom }): un reencuadre (cambio de tamaño, la ficha) lo conserva
  let movido = null;
  const encuadrar0 = escena.encuadrar;
  function opcionesDe(opts, fin = movido) {
    const p = PRESET[vis.camara] || {};
    const rumbo = fin?.rumbo ?? vis.rumbo, elev = fin?.elev ?? vis.elevacion ?? p.elev, k = entre(fin?.zoom ?? vis.zoom ?? p.k ?? 1, ZOOM);
    // más cerca que el paso, el piso de la distancia baja en la misma proporción (una caseta no se ve a 60 m)
    return { ...opts, ...(rumbo != null ? { rumbo: ((rumbo % 360) + 360) % 360 } : {}), ...(elev != null ? { elev: entre(elev, ELEV) } : {}),
      margen: Math.min(3, (opts.margen ?? 0.86) * k), ...(k > 1 ? { minDist: Math.max(12, (opts.minDist ?? 60) / k) } : {}) };
  }
  escena.encuadrar = (obj, opts = {}) => {
    const { vuelo, ...resto } = opts;
    ultimo = { obj, opts: resto };
    if (!interno) delPaso = { clave: claveActual(), n: escena.cargados(), obj, opts: resto };   // lo pidió el paso (o su módulo, más tarde)
    return encuadrar0(obj, { ...opcionesDe(resto), ...(seco || vuelo === false ? { vuelo: false } : {}) });
  };
  /** Corre `fn` (la vista de un paso) sin mover la cámara: solo queda anotado qué encuadra. */
  function enSeco(fn) { seco++; try { return fn?.(); } finally { seco--; } }
  // lo mismo para los encuadres que arma este archivo (mirar, un componente sin paso, repetir el último): no son «lo del paso»
  function propio(fn) { interno++; try { return fn(); } finally { interno--; } }
  // volar: va al último encuadre con la cámara vigente (un vuelo corto, que corta el paseo en curso). Si la cámara ya
  // está ahí (enfocar el componente del paso que se mira, volver de «hoy»), no: un vuelo a ninguna parte solo haría
  // esperar a quien espera que la imagen se asiente
  const pos = new THREE.Vector3(), tgt = new THREE.Vector3();
  const volar = () => {
    if (!ultimo) return;
    const p = st.flying || st.paseo ? null : encuadrar0(ultimo.obj, { ...opcionesDe(ultimo.opts), vuelo: false });
    if (p && st.camera.position.distanceTo(pos.fromArray(p.pos)) < p.D * 0.01 && st.controls.target.distanceTo(tgt.fromArray(p.tgt)) < p.D * 0.01) { st.userMoved = false; return; }
    propio(() => escena.encuadrar(ultimo.obj, { ...ultimo.opts, duracion: 1.4 }));
  };
  // reencuadrar: lo mismo cuando nadie lo pidió (cambió la zona libre: el tamaño del marco, la ficha, «Solo 3D»).
  // Durante un paseo no se vuela: queda pendiente para cuando llegue
  let pendiente = false;
  const reencuadrar = () => { if (st.paseo) pendiente = true; else volar(); };
  const hayCamara = () => !!(vis.enfoque || vis.camara !== 'paso' || vis.rumbo != null || vis.elevacion != null || vis.zoom != null || vis.mirar || movido);

  // dónde está la cámara: rumbo (desde dónde mira, grados desde el norte), elevación y distancia a lo que mira
  const off = new THREE.Vector3();
  function postura() {
    off.copy(st.camera.position).sub(st.controls.target);
    const d = off.length() || 1;
    return { rumbo: (THREE.MathUtils.radToDeg(Math.atan2(off.x, -off.z)) + 360) % 360, elev: THREE.MathUtils.radToDeg(Math.asin(entre(off.y / d, [-1, 1]))), dist: d };
  }
  /** Lleva la cámara, con un paseo de `ms`, a la postura que piden el paso y lo visual. `mover` dice cómo termina: el
   * giro se suma al rumbo (al de llegada o, con `desdeAqui`, al que tiene la cámara) y `zoom` y `elevacion` son los
   * finales. Con el atlas abierto (la maqueta está detrás, parada) la deja ya en su sitio. Si ya está ahí y no hay giro,
   * no hay paseo (un paseo a ninguna parte solo le quitaría el turno a `girar`); y con `girar` pedido el viaje dura a
   * lo sumo 2,5 s, para que el giro ocupe el resto de la frase. Devuelve si la movió. */
  function viajar(ms, mover = null, { desdeAqui = false } = {}) {
    if (!ultimo) return false;
    const aqui = postura(), base = opcionesDe(ultimo.opts, null), giro = Number.isFinite(mover?.giro) ? mover.giro : null;
    const rumbo0 = desdeAqui ? aqui.rumbo : base.rumbo ?? 200;
    // desde aquí, lo que `mover` no dice se queda como está: la altura que tiene la cámara y el acercamiento del último movimiento
    const fin = { rumbo: rumbo0 + (giro ?? 0), elev: mover?.elevacion ?? (desdeAqui ? aqui.elev : null), zoom: mover?.zoom ?? (desdeAqui ? movido?.zoom ?? null : null) };
    const p = encuadrar0(ultimo.obj, { ...opcionesDe(ultimo.opts, fin), vuelo: false });
    if (!p) return false;
    movido = mover || desdeAqui ? fin : null;
    pendiente = false;
    st.userMoved = false;
    const llego = !st.flying && !st.paseo && st.camera.position.distanceTo(pos.fromArray(p.pos)) < p.D * 0.005 && st.controls.target.distanceTo(tgt.fromArray(p.tgt)) < p.D * 0.005;
    if (llego && !giro) return false;
    const dur = inmersionVigente() ? 0 : vis.girar ? Math.min(ms, 2500) : ms;
    st.pasear({ target: p.tgt, pivote: p.centro, rumbo: desdeAqui ? null : rumbo0, giro, elev: p.elev, dist: p.D },
      { duracion: dur / 1000, alTerminar: (completo) => { if (completo && pendiente) reencuadrar(); pendiente = false; } });
    return true;
  }
  /** Solo el movimiento, desde la postura actual: gira `giro` grados alrededor de lo que mira y termina con ese `zoom` y
   * esa `elevacion`, en `ms` milisegundos. No es estado: no queda en `estado()`. */
  function mover(m, ms = MOVER_MS) {
    if (!m || typeof m !== 'object') return false;
    const dur = entre(Number.isFinite(ms) && ms > 0 ? ms : MOVER_MS, PASEO_MS);
    if (ultimo && !st.userMoved) return viajar(dur, m, { desdeAqui: true });
    // la persona dejó la cámara en otro sitio (o todavía no hay encuadre): gira y cambia de altura alrededor de lo que mira
    st.pasear({ giro: Number.isFinite(m.giro) ? m.giro : null, elev: m.elevacion != null ? entre(m.elevacion, ELEV) : null }, { duracion: dur / 1000 });
    return true;
  }

  // girar: la cámara da la vuelta a lo que mira, sin perder la distancia ni la altura; la persona que arrastra la detiene.
  // Avanza con el reloj, no con los cuadros (en un equipo lento giraba veinte veces más despacio): lo que pasó desde el
  // cuadro anterior, hasta 1 s (tras una pausa —la pestaña oculta, el atlas abierto, un vuelo— no da un salto)
  const eje = new THREE.Vector3(0, 1, 0), radio = new THREE.Vector3();
  let tGiro = 0;
  st.onFrame(() => {
    const ahora = performance.now(), quieta = !vis.girar || st.flying || st.paseo || !st.running;
    const dt = tGiro ? Math.min((ahora - tGiro) / 1000, 1) : 0;
    tGiro = quieta ? 0 : ahora;
    if (quieta) return false;
    radio.copy(st.camera.position).sub(st.controls.target).applyAxisAngle(eje, (-2 * Math.PI * dt) / VUELTA_S);
    st.camera.position.copy(st.controls.target).add(radio);
    st.camera.lookAt(st.controls.target);
    st.baseOffset.copy(radio).divideScalar(st.fitFactor());   // un cambio de tamaño del marco no la devuelve a donde empezó
    return true;
  });
  // la persona tomó la cámara: deja de girar y se avisa como suyo (un recorrido que suena se pausa, mando.js). El paseo
  // en curso ya lo cortó core.js (stopFlight)
  st.controls.addEventListener('start', () => {
    vis.girar = false;
    dispatchEvent(new CustomEvent('propuesta:visual', { detail: { ...estadoVisual(), por: 'persona' } }));
  });

  // ---------------------------------------------------------------- brújula, escala y estado (pantallas grandes)
  const hud = document.createElement('div');
  hud.className = 'hud-tec';
  hud.setAttribute('aria-hidden', 'true');
  hud.innerHTML = `<div class="hud-chips"><span class="chip-estado"><i></i><b>Con el proyecto</b></span><span class="chip-enfoque" hidden><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="7" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="2" fill="currentColor"/></svg><b></b></span><span class="chip-pieza chip-solo" hidden><em>Solo</em><b></b></span><span class="chip-pieza chip-sin" hidden><em>Sin</em><b></b></span><span class="chip-pieza chip-mas" hidden><em>Además</em><b></b></span></div>
    <div class="hud-instr"><div class="escala"><i></i><span>—</span></div><svg class="brujula" viewBox="0 0 48 48"><circle cx="24" cy="24" r="22" class="aro"/><g class="aguja"><path d="M24 6 29 24H19z" class="n"/><path d="M24 42 19 24h10z" class="s"/><text x="24" y="17.5" text-anchor="middle">N</text></g></svg></div>`;
  pres.append(hud);
  const aguja = hud.querySelector('.aguja'), escala = hud.querySelector('.escala'), escalaI = escala.querySelector('i'), escalaT = escala.querySelector('span');
  const chipEstado = hud.querySelector('.chip-estado'), chipEnfoque = hud.querySelector('.chip-enfoque');
  const chipSolo = hud.querySelector('.chip-solo'), chipSin = hud.querySelector('.chip-sin'), chipMas = hud.querySelector('.chip-mas');
  // el nombre de una pieza o de una parte, en corto (sin lo que va después de «:» o «(»)
  const corto = (t) => String(t || '').split(/[:(]/)[0].trim();
  const lista = (ns) => (ns.length > 2 ? `${ns.slice(0, 2).join(', ')} y ${ns.length - 2} más` : ns.join(' y '));
  const chip = (el, texto) => { el.hidden = !texto; if (texto) { el.querySelector('b').textContent = texto; el.title = texto; } };
  let rumboHud = null, escalaHud = null, anchoHud = null;
  const v = new THREE.Vector3();
  st.onFrame(() => {
    v.copy(st.controls.target).sub(st.camera.position);
    const r = Math.round(THREE.MathUtils.radToDeg(Math.atan2(v.x, -v.z)));
    if (r !== rumboHud) { rumboHud = r; aguja.setAttribute('transform', `rotate(${-r} 24 24)`); }
    // metros por píxel a la distancia del objetivo (aproximada en una vista oblicua): una barra de 1, 2 o 5 × 10ⁿ m
    const H = st.el.clientHeight || 1, mpp = (2 * v.length() * Math.tan(THREE.MathUtils.degToRad(st.camera.fov / 2))) / H;
    let L = 1; while (L / mpp < 56) L *= L.toString().startsWith('2') ? 2.5 : 2;
    const w = Math.round(L / mpp);
    if (L !== escalaHud) { escalaHud = L; escalaT.textContent = L >= 1000 ? `${(L / 1000).toLocaleString('es-CO')} km` : `${L} m`; }
    if (w !== anchoHud && Number.isFinite(w)) { anchoHud = w; escalaI.style.width = `${w}px`; }
    return false;
  });
  function pintarHud() {
    pres.classList.toggle('vis-hoy', vis.comparar === 'hoy');
    chipEstado.querySelector('b').textContent = vis.comparar === 'hoy' ? 'Hoy: como está el sitio' : 'Con el proyecto';
    const x = vis.enfoque ? comp(vis.enfoque) : null;
    chipEnfoque.hidden = !x;
    if (x) chipEnfoque.querySelector('b').textContent = x.nombre;
    // lo que el asistente dejó solo, quitó o añadió en la maqueta: la sala sabe que lo que ve no es todo el paso
    const P = piezasDe(cap()), nombre = (id) => corto(P.get(id)?.nombre);
    const quitadas = vis.sin.map((s) => { const [a, b] = s.split('.'); return corto(parteDe(P.get(a), b)?.nombre).toLowerCase(); });
    chip(chipSolo, vis.aislar ? nombre(vis.aislar) : '');
    chip(chipSin, lista([...(vis.aislar ? [] : vis.ocultar.map(nombre)), ...quitadas].filter(Boolean)));
    chip(chipMas, vis.aislar ? '' : lista(vis.mostrar.filter((id) => !vis.ocultar.includes(id)).map(nombre).filter(Boolean)));
  }

  // ---------------------------------------------------------------- a dónde mira: el paso, el enfoque o `mirar`
  function puntosDe(c, e) {
    const g = datos.geo?.[c.id] || {}, pts = [];
    for (const id of e.sitios || []) { const s = (g.sitios || []).find((x) => x.id === id); if (s?.poligono) pts.push(...s.poligono); else if (s) pts.push([s.x, s.y]); }
    for (const id of e.trazados || []) { const t = (g.trazados || []).find((x) => x.id === id); if (t?.puntos) pts.push(...t.puntos); }
    return pts;
  }
  const defDe = (c, p) => { const m = ctx3d[c.id]; return m?.pasos?.[p?.id] || m?.pasos?.['*'] || {}; };
  const vistaDe = (c, p) => defDe(c, p).vista || ctx3d[c.id]?.vista;
  // el paso cuyas capas se muestran: el que desarrolla el componente enfocado o, si no, el vigente
  function pasoCapas(c = cap()) {
    const e = vis.enfoque ? compDe(c, vis.enfoque)?.enfoque : null;
    return (e?.paso && c.pasos.find((k) => k.id === e.paso)) || paso();
  }
  // el encuadre de un componente sin paso propio: sus sedes o sus sitios y trazados
  function lugarEnfoque(c, e) {
    const cajas = (e?.edificios || []).map((k) => escena.cajaEdificio(k)).filter(Boolean);
    if (cajas.length) return { obj: cajas.reduce((a, k) => a.union(k), cajas[0].clone()), opts: { rumbo: 160, elev: 32, margen: 0.6, minDist: 30, apartar: true } };
    const pts = puntosDe(c, e || {});
    return pts.length ? { obj: caja(pts, 25), opts: { rumbo: 200, elev: 40, margen: 0.66, minDist: 40, apartar: true } } : null;
  }
  // la caja de unos objetos de la maqueta (los grupos de una pieza o sus capas), o null si no tienen nada
  function cajaDe(objs) {
    const b = new THREE.Box3();
    objs.forEach((o) => { const k = solidBox(o, 0.2); if (!k.isEmpty()) b.union(k); });
    return b.isEmpty() || !Number.isFinite(b.min.x + b.max.x + b.min.z + b.max.z) ? null : b;
  }
  const gruposEn = (capasIds, nombres) => { const out = []; for (const id of capasIds) escena.capas.get(id)?.traverse((o) => { if (o.name && nombres.includes(o.name)) out.push(o); }); return out; };
  // qué encuadra `mirar`: los grupos de una pieza (una nave del parque), la vista del paso que desarrolla el componente,
  // la réplica de la pieza, los sitios del componente o, si no, las capas de la pieza. Con el ángulo del paso vigente
  function lugarDe(c, id, angulo = {}) {
    const x = piezasDe(c).get(id) || null, e = compDe(c, id)?.enfoque || null;
    const deCaja = (b, margen, minDist) => (b ? { obj: b, opts: { rumbo: angulo.rumbo ?? 200, elev: angulo.elev ?? 38, margen, minDist, apartar: true } } : null);
    if (x?.grupos) { const l = deCaja(cajaDe(gruposEn(x.capas, x.grupos)), 0.6, 30); if (l) return l; }
    if (e?.paso && pasoAnotado(`${c.id}/${e.paso}`)) return { obj: delPaso.obj, opts: delPaso.opts };
    const vista = e?.paso ? ctx3d[c.id]?.pasos?.[e.paso]?.vista : null;
    if (vista) { const antes = ultimo; propio(() => enSeco(vista)); const l = ultimo; ultimo = antes; if (l && l !== antes) return l; }
    if (x?.replica) { const l = deCaja(escena.cajaEdificio(x.replica.id), 0.7, 30); if (l) return l; }
    if (e) { const l = lugarEnfoque(c, e); if (l) return l; }
    return x ? deCaja(cajaDe(x.capas.map((k) => escena.capas.get(k)).filter(Boolean)), 0.8, 40) : null;
  }
  const claveActual = () => { const c = cap(); return c ? `${c.id}/${pasoCapas(c)?.id}` : ''; };
  /** Deja anotado (en seco) lo que hay que encuadrar según lo vigente: lo de `mirar`, el lugar del componente enfocado o
   * la vista del paso (la que anotó al llegar; si el enfoque llevó a otro paso, la de ese). */
  function fijarBase() {
    const c = cap();
    if (!c) return;
    if (pasoAnotado(claveActual())) ultimo = { obj: delPaso.obj, opts: delPaso.opts };
    else enSeco(vistaDe(c, pasoCapas(c)));
    const anotar = (l) => { if (l) propio(() => enSeco(() => escena.encuadrar(l.obj, l.opts))); };
    const e = vis.enfoque ? compDe(c, vis.enfoque)?.enfoque : null;
    if (e && !e.paso) anotar(lugarEnfoque(c, e));
    if (vis.mirar) anotar(lugarDe(c, vis.mirar, ultimo?.opts));
  }

  // ---------------------------------------------------------------- lo que se ve: el paso y, encima, lo pedido
  /** Vuelve a poner lo 3D con lo vigente (enfoque, hoy/proyecto, piezas y partes), sin mover la cámara. */
  function pintar({ animar = false } = {}) {
    const c = cap();
    if (c) pasar3D(c, pasoCapas(c), { camara: false, animar });
  }
  function prefijo(m) {
    for (const d of Object.values(m?.pasos || {})) { const k = (d?.capas || [])[0]; if (k) return k.split('.')[0]; }
    return (m?.completo || [])[0]?.split('.')[0] || null;
  }
  /** Lo que pasar3D (main.js) debe mostrar en vez de las capas `ids` del paso y de su filtro de rótulos `etiquetas`, o
   * null si lo visual no cambia nada. */
  function ajustar(c, ids, etiquetas) {
    const P = piezasDe(c), m = ctx3d[c.id];
    let veo = ids, et = etiquetas, toca = false;
    // un componente sin paso propio (sus sitios, sus trazados o una sede): además, las capas principales del módulo
    const e = vis.enfoque ? compDe(c, vis.enfoque)?.enfoque : null;
    if (e && !e.paso) { veo = [...new Set([...veo, ...(m?.completo || [])])]; et = null; toca = true; }
    // hoy: solo la capa «hoy» del capítulo, si la tiene
    if (vis.comparar === 'hoy') { const pre = prefijo(m); veo = [...escena.capas.keys()].filter((k) => pre && k === `${pre}.hoy`); et = null; toca = true; }
    const a = P.get(vis.aislar);
    if (a) return { ids: [...a.capas], etiquetas: [...a.capas] };
    if (vis.mostrar.length || vis.ocultar.length) {
      const capasDe = (l) => l.flatMap((id) => P.get(id)?.capas || []);
      // una pieza que es solo parte de sus capas (una nave del parque) no apaga la capa: se ocultan sus grupos (efectos)
      const mas = capasDe(vis.mostrar), menos = new Set(capasDe(vis.ocultar.filter((id) => !P.get(id)?.grupos)));
      veo = [...new Set([...veo, ...mas])].filter((k) => !menos.has(k));
      if (et) et = [...new Set([...et, ...mas])];   // el filtro de rótulos deja ver lo que se añade
      toca = true;
    }
    return toca ? { ids: veo, etiquetas: et } : null;
  }
  // lo que `efectos` tocó encima del estado del paso (réplicas, casas de hoy, gris, estados de los módulos), para devolverlo
  let foto = null;
  /** Después de `antes` del paso (pasar3D): el estado de las réplicas, las partes quitadas, los grupos ocultos o
   * atenuados, el gris del contexto y los estados de los módulos que pide lo visual. */
  function efectos(c) {
    const hoy = vis.comparar === 'hoy';
    if (!hoy && !vis.aislar && !vis.mostrar.length && !vis.ocultar.length && !vis.sin.length) return;
    const P = piezasDe(c), m = ctx3d[c.id], a = P.get(vis.aislar) || null;
    foto = { replicas: new Map([...escena.edificios.keys()].map((id) => [id, escena.modoDe(id)])), hoy: escena.zonasHoy.map((z) => [z.id, z.grupo.visible]), gris: escena.enGris(), estados: [], m };
    const delModulo = (k, v) => { if (!m?.efectos?.[k]) return; m.efectos[k](v); if (v) foto.estados.push(k); };
    if (hoy) {
      // el sitio como está: los módulos dejan su estado de hoy (réplicas, gris, parpadeo) y vuelven las casas de los lotes
      Object.values(ctx3d).forEach((x) => x?.salir?.());
      escena.zonasHoy.forEach((z) => escena.verHoy(z.id, true));
    }
    for (const x of P.values()) {
      const oculta = a ? a !== x : vis.ocultar.includes(x.id), pedida = a ? a === x : vis.mostrar.includes(x.id) && !oculta;
      const q = oculta ? [] : vis.sin.map((s) => s.split('.')).filter(([k]) => k === x.id).map(([, k]) => parteDe(x, k)).filter(Boolean);
      // la réplica de la pieza: como hoy si la pieza se oculta; con el proyecto si se pidió; y sin las partes quitadas
      if (x.replica && escena.edificios.has(x.replica.id) && !(oculta && a?.replica?.id === x.replica.id)) {
        const nodos = q.flatMap((k) => k.nodos || []);
        if (oculta) escena.modoEdificio(x.replica.id, 'hoy', []);
        else if (pedida || nodos.length) escena.modoEdificio(x.replica.id, pedida ? 'proyecto' : escena.modoDe(x.replica.id).capa, [...(x.replica.sin || []), ...nodos]);
      }
      if (x.efecto && (pedida || oculta) && !(oculta && a?.efecto === x.efecto)) delModulo(x.efecto, pedida);
      if (oculta) { if (x.grupos && !a) escena.verGrupos(x.capas, x.grupos, false); continue; }
      q.forEach((k) => { if (k.grupos) escena.verGrupos(x.capas, k.grupos, false); });
    }
    if (a) { if (a.grupos) escena.atenuarHermanos(a.capas, a.grupos); escena.contextoGris(true); }
    // los módulos acomodan lo suyo a las capas que quedaron (el lote de la cancha no queda vacío: vuelven sus casas)
    Object.values(ctx3d).forEach((x) => x?.alAjustar?.());
    st.invalidate(true);
  }
  /** Devuelve lo que `efectos` tocó: lo llama pasar3D ANTES de que el módulo ponga el estado del paso que sigue. */
  function deshacer() {
    if (!foto) return;
    const f = foto;
    foto = null;
    f.estados.forEach((k) => f.m?.efectos?.[k]?.(false));
    escena.restaurarGrupos();
    f.replicas.forEach((modo, id) => { const ahora = escena.modoDe(id); if (modo && (ahora.capa !== modo.capa || ahora.sin.join() !== modo.sin.join())) escena.modoEdificio(id, modo.capa, modo.sin); });
    f.hoy.forEach(([id, v]) => escena.verHoy(id, v));
    escena.contextoGris(f.gris);
  }

  // ---------------------------------------------------------------- ficha técnica (detalle)
  const det = document.createElement('aside');
  det.className = 'detalle';
  det.hidden = true;
  det.setAttribute('aria-label', 'Ficha técnica');
  pres.append(det);
  function fichaHTML(c, x) {
    const specs = (x.especificaciones || []).map(especificacionTecnica).filter(Boolean);
    const tipos = (x.proyecto_tipo || []).map((t) => sinPlata(t.nombre)).filter(Boolean);
    const plazo = sinPlata(x.plazo), a = anios(plazo);
    const barra = a ? (() => { const x0 = 2027, n = 6, l = ((Math.max(x0, a[0]) - x0) / n) * 100, w = ((Math.min(x0 + n, a[1] + 1) - Math.max(x0, a[0])) / n) * 100; return `<div class="det-plazo"><div class="anios">${[2027, 2028, 2029, 2030, 2031, 2032].map((y) => `<span>${y}</span>`).join('')}</div><i style="left:${l}%;width:${w}%"></i></div>`; })() : '';
    return `<div class="det-cab"><p class="ceja"><span>Ficha técnica</span> · ${esc(c.nombre)}</p><h3>${esc(x.nombre)}</h3>${x.resumen ? `<p class="det-res">${sinPlata(x.resumen)}</p>` : ''}
        <button type="button" class="det-cerrar" data-accion="cerrar-detalle" aria-label="Cerrar la ficha técnica">×</button></div>
      <div class="det-cuerpo">
        ${x.descripcion ? `<p>${sinPlata(x.descripcion)}</p>` : ''}
        ${specs.length ? `<h4>Especificaciones</h4><dl class="hoja">${specs.map(([k, val]) => `<dt>${esc(k)}</dt><dd>${esc(val)}</dd>`).join('')}</dl>` : ''}
        ${tipos.length ? `<h4>Proyecto tipo y referentes</h4><ul class="referentes">${tipos.map((t) => `<li>${esc(t)}</li>`).join('')}</ul>` : ''}
        ${x.ubicacion ? `<h4>Dónde</h4><p>${sinPlata(x.ubicacion)}</p>` : ''}
        ${plazo ? `<h4>Plazo</h4><p>${esc(plazo)}</p>${barra}` : ''}
        <p class="det-lugar ${x.enfoque ? 'si' : ''}">${x.enfoque ? 'Tiene lugar propio en la maqueta 3D' : 'Sin lugar propio en la maqueta: se describe aquí'}</p>
      </div>`;
  }
  // reencuadre: false cuando quien la abre o la cierra ya va a mover la cámara (o cambia de paso: el paso nuevo encuadra)
  function verDetalle(id, { reencuadre = true } = {}) {
    const c = cap(), x = id ? comp(id) : null;
    if (!x) { if (!det.hidden) { det.hidden = true; pres.classList.remove('con-detalle'); if (reencuadre) setTimeout(reencuadrarSiQuieto, 60); if (inm.abierta) ubicarInmersion(); } return; }
    det.style.setProperty('--mc', colorDe(c.id));
    det.innerHTML = fichaHTML(c, x);
    const abria = det.hidden;
    det.hidden = false;
    pres.classList.add('con-detalle');
    if (abria && gsap && !reducedMotion) gsap.fromTo(det, { x: 40, opacity: 0 }, { x: 0, opacity: 1, duration: 0.45, ease: 'power3.out' });
    if (abria && reencuadre) setTimeout(reencuadrarSiQuieto, 60);
    if (inm.abierta) ubicarInmersion();
  }
  // la ficha le quita ancho a la maqueta: se vuelve a encuadrar lo que se miraba (si la persona no movió la cámara; con
  // un paseo en curso, cuando llegue)
  const reencuadrarSiQuieto = () => { if (!st.userMoved) reencuadrar(); };

  // ---------------------------------------------------------------- inmersión en un modelo del atlas
  // `abriendo`: la promesa del último aplicarInmersion (la simulación espera a que el modelo pedido esté)
  const inm = { abierta: false, actual: null, marco: null, puente: null, fallo: false, abriendo: Promise.resolve() };
  const capaInm = document.createElement('div');
  capaInm.className = 'inmersion';
  capaInm.hidden = true;
  capaInm.innerHTML = `<div class="inm-rotulo"><span class="inm-ceja">Modelo 3D del atlas</span><b></b><span class="inm-txt"></span>
      <button type="button" class="inm-cerrar" data-accion="cerrar-inmersion">Volver a la maqueta</button></div>
    <div class="inm-marco"><p class="inm-cargando">Cargando el modelo del atlas…</p></div>`;
  pres.append(capaInm);
  const marcoEl = capaInm.querySelector('.inm-marco');
  // la ventana va en lo que dejan libre el panel (a la izquierda) y la ficha técnica (a la derecha) en pantalla grande
  function ubicarInmersion() {
    const grande = innerWidth > 1080, r = document.querySelector('.panel')?.getBoundingClientRect();
    const izq = grande && !pres.classList.contains('sin-panel') && r && r.width < innerWidth * 0.7 ? r.right + 16 : grande ? 96 : 10;
    const der = grande && !det.hidden ? innerWidth - det.getBoundingClientRect().left + 12 : grande ? 16 : 10;
    capaInm.style.setProperty('--inm-x0', `${Math.round(izq)}px`);
    capaInm.style.setProperty('--inm-x1', `${Math.round(der)}px`);
  }
  addEventListener('resize', () => { if (inm.abierta) ubicarInmersion(); });
  new MutationObserver(() => { if (inm.abierta) setTimeout(ubicarInmersion, 470); }).observe(pres, { attributes: true, attributeFilter: ['class'] });
  function puente() {
    if (inm.puente) return inm.puente;
    const f = document.createElement('iframe');
    f.title = 'Modelo 3D del atlas';
    f.src = new URL(`atlas.html?escenario=1#${inm.actual?.vista || 'torre'}`, location.href).href;
    f.setAttribute('referrerpolicy', 'no-referrer');
    f.tabIndex = -1;
    marcoEl.append(f);
    inm.marco = f;
    inm.puente = new Promise((listo, mal) => {
      const t0 = performance.now();
      const mirar = () => {
        let p = null;
        try { p = f.contentWindow?.__escenario; } catch { p = null; }
        if (p) { listo(p); return; }
        if (performance.now() - t0 > ESPERA_ATLAS_MS) { inm.puente = null; f.remove(); mal(new Error('El atlas no cargó')); return; }
        setTimeout(mirar, 120);
      };
      mirar();
    });
    return inm.puente;
  }
  function fallaAtlas() {
    inm.fallo = true;
    const t = capaInm.querySelector('.inm-cargando');
    if (t) t.textContent = 'No se pudo cargar el modelo del atlas';
  }
  async function irAtlas(modo) {
    const i = inm.actual;
    if (!i) return;
    const p = await puente();
    await p.ir({ vista: i.vista, modo: modo || i.modo, tema: temaActual() });
    capaInm.classList.add('lista');
  }
  async function abrirInmersion(id) {
    const i = catalogo.get(id);
    if (!i) return;
    inm.actual = i;
    capaInm.style.setProperty('--mc', colorDe(cap().id));
    capaInm.querySelector('.inm-rotulo b').textContent = i.nombre || '';
    const txt = capaInm.querySelector('.inm-txt');
    txt.textContent = i.texto || '';
    txt.title = i.texto || '';
    if (!inm.abierta) {
      inm.abierta = true;
      capaInm.hidden = false;
      capaInm.querySelector('.inm-cargando').textContent = 'Cargando el modelo del atlas…';
      inm.fallo = false;
      pres.classList.add('con-inmersion');
      ubicarInmersion();
      st.stop();
      if (gsap && !reducedMotion) gsap.fromTo(capaInm, { opacity: 0 }, { opacity: 1, duration: 0.5, ease: 'power2.out' });
    }
    await irAtlas(vis.comparar === 'hoy' ? 'hoy' : i.modo);
  }
  function cerrarInmersion() {
    if (!inm.abierta) return;
    inm.abierta = false;
    inm.actual = null;
    capaInm.hidden = true;
    capaInm.classList.remove('lista');
    pres.classList.remove('con-inmersion');
    st.start();
    st.invalidate(true);
  }
  // la inmersión que corresponde: la pedida, la del paso (un paso de inmersión) o ninguna ('maqueta' la cierra)
  function inmersionVigente() {
    if (vis.inmersion === 'maqueta') return null;
    if (vis.inmersion) return vis.inmersion;
    const p = paso();
    return p?.tipo === 'inmersion' ? p.inmersion : null;
  }
  function aplicarInmersion() {
    const id = inmersionVigente();
    inm.abriendo = !id ? Promise.resolve(cerrarInmersion())
      : inm.actual?.id === id && inm.abierta ? inm.abriendo.catch(() => {}) : abrirInmersion(id);
    return inm.abriendo;
  }

  // ---------------------------------------------------------------- la simulación del modelo a la vista
  /** Acciona en el modelo a la vista los controles de `lista` ([{ control, valor? }], la forma ya revisada por mando.js),
   * en orden. Con un modelo del atlas abierto, con `__escenario.simular` (js/escenario.js: como los acciona la persona;
   * un control que todavía no está o está deshabilitado lo espera), después de que termine de abrirse el modelo pedido;
   * sin él, en la maqueta 3D (simulacion.js: la hora, el día, las luces, el partido). Devuelve lo que no se pudo,
   * [{ clave, valor, motivo }], a más tardar en `tope` ms: lo que todavía espera entonces (Reproducir hasta que termine
   * el primer cálculo, el partido mientras carga el capítulo) sigue solo y no se cuenta. Nunca lanza. */
  async function simular(lista, { tope = 2000 } = {}) {
    if (!Array.isArray(lista) || !lista.length) return [];
    const fuera = (x, motivo) => ({ clave: `simular.${x?.control ?? ''}`.slice(0, 40), valor: x?.valor, motivo });
    const pedida = inmersionVigente();
    const vence = new Promise((ok) => { const t = setTimeout(() => ok(undefined), tope); t?.unref?.(); });
    if (!pedida) {
      // la maqueta: todos en el acto y en orden (el partido puede esperar a que su capítulo termine de armarse)
      const res = lista.map((x) => sim.accionar(x.control, x.valor));
      const hechos = await Promise.all(res.map((r) => Promise.race([Promise.resolve(r), vence])));
      return hechos.map((r, i) => (r === true || r === undefined ? null : fuera(lista[i], typeof r === 'string' && r ? r : 'la maqueta no pudo accionarlo')))
        .filter(Boolean);
    }
    const todo = (async () => {
      try { await inm.abriendo; } catch { /* el modelo no cargó: lo dice abajo */ }
      if (inmersionVigente() !== pedida || !inm.abierta || inm.actual?.id !== pedida) {
        return lista.map(() => 'se cambió de modelo antes de accionarlo');
      }
      let p;
      try { p = await puente(); } catch { return lista.map(() => 'el modelo del atlas no cargó'); }
      if (typeof p.simular !== 'function') return lista.map(() => 'este atlas no acciona simulaciones');
      // todas seguidas: escenario.js las encadena en orden, detrás del ir() que abrió el modelo
      return lista.map((x) => Promise.resolve().then(() => p.simular(x.control, x.valor)).catch((e) => String(e?.message || e)));
    })();
    const res = await Promise.race([todo, vence]);
    if (!Array.isArray(res)) return [];   // venció antes de que el modelo estuviera: sigue solo
    const hechos = await Promise.all(res.map((r) => Promise.race([Promise.resolve(r), vence])));
    return hechos.map((r, i) => (r === true || r === undefined ? null : fuera(lista[i], typeof r === 'string' && r ? r : 'el atlas no pudo accionarlo')))
      .filter(Boolean);
  }

  // ---------------------------------------------------------------- tema
  const temaActual = () => {
    const t = document.documentElement.dataset.theme;
    return t ? (t === 'dark' ? 'oscuro' : 'claro') : matchMedia('(prefers-color-scheme: dark)').matches ? 'oscuro' : 'claro';
  };
  function ponerTema(t) {
    document.documentElement.dataset.theme = t === 'oscuro' ? 'dark' : 'light';
    inm.puente?.then((p) => p.tema(t)).catch(() => {});
  }

  // ---------------------------------------------------------------- lo que piden las órdenes `visual` y `escena`
  const igual = (a, b) => (Array.isArray(a) || Array.isArray(b) ? JSON.stringify(a) === JSON.stringify(b) : a === b);
  /** Quita de `v` (lo visual, parcial o completo, con la forma ya revisada) lo que no existe en el capítulo `ci`: piezas
   * y partes desconocidas, un componente que no está o no tiene lugar, una inmersión fuera del catálogo. Devuelve
   * { visual, descartadas: [{ clave, valor, motivo }] }. Nunca lanza: lo opcional que no vale no tumba el paso del plan. */
  function depurar(v, ci) {
    const out = { ...(v && typeof v === 'object' ? v : {}) }, descartadas = [];
    try {
      const c = caps[ci], P = piezasDe(c), donde = c?.nombre || 'este capítulo';
      const fuera = (clave, valor, motivo) => descartadas.push({ clave, valor, motivo });
      for (const k of ['enfoque', 'detalle']) {
        if (out[k] == null) continue;
        const x = compDe(c, out[k]);
        if (!x) { fuera(k, out[k], `${donde} no tiene el componente «${out[k]}»`); out[k] = null; }
        else if (k === 'enfoque' && !x.enfoque) { fuera(k, out[k], `«${x.nombre}» no tiene un lugar propio en la maqueta`); out[k] = null; }
      }
      if (out.inmersion != null && out.inmersion !== 'maqueta' && !catalogo.has(out.inmersion)) { fuera('inmersion', out.inmersion, 'la presentación no tiene esa inmersión'); out.inmersion = null; }
      if (out.mirar != null && !P.has(out.mirar) && !compDe(c, out.mirar)?.enfoque) { fuera('mirar', out.mirar, `«${out.mirar}» no es una pieza de ${donde} ni un componente con lugar en la maqueta`); out.mirar = null; }
      if (out.aislar != null && !P.has(out.aislar)) { fuera('aislar', out.aislar, `${donde} no tiene la pieza «${out.aislar}»`); out.aislar = null; }
      for (const k of ['mostrar', 'ocultar']) {
        if (out[k] === undefined) continue;
        const ids = Array.isArray(out[k]) ? out[k] : [];
        if (!Array.isArray(out[k])) fuera(k, out[k], 'no es una lista de piezas');
        out[k] = [...new Set(ids)].filter((id) => { if (P.has(id)) return true; fuera(k, id, `${donde} no tiene la pieza «${id}»`); return false; });
      }
      if (out.sin !== undefined) {
        const ids = Array.isArray(out.sin) ? out.sin : [];
        if (!Array.isArray(out.sin)) fuera('sin', out.sin, 'no es una lista de partes');
        out.sin = [...new Set(ids)].filter((s) => {
          const [a, b] = String(s).split('.'), x = P.get(a);
          if (x && parteDe(x, b)) return true;
          fuera('sin', s, x ? `«${corto(x.nombre)}» no tiene la parte «${b}»` : `${donde} no tiene la pieza «${a}»`);
          return false;
        });
      }
    } catch (e) { console.warn('visual.depurar', e); }
    return { visual: out, descartadas };
  }

  /** Aplica `cambios` (solo las claves que trae; las formas ya las revisó mando.js). Devuelve null o el error.
   * opciones: `ms` (> 0, se recorta a 1,2–20 s): lo que cambia de lo que se ve cambia EN EL ACTO y la cámara viaja con un
   * paseo de esa duración a la postura que resulta del paso y lo visual (siempre: aunque nada haya cambiado); sin `ms`,
   * un vuelo corto si cambió a dónde mira. `mover` ({ giro, zoom, elevacion }): cómo termina ese viaje (sin `ms`, dura
   * 6 s). `animar: true` repite la animación del paso. Las piezas y partes que no existen en el capítulo se ignoran
   * (`depurar` dice cuáles); un componente o una inmersión que no existen siguen siendo un error, como antes. */
  async function aplicar(cambios, { ms = 0, mover: mov = null, animar } = {}) {
    const c = cap();
    if (!c) return 'La presentación todavía no muestra ningún paso';
    cambios = { ...(cambios || {}) };
    for (const k of ['enfoque', 'detalle']) {
      const id = cambios[k];
      if (id == null) continue;
      const x = comp(id);
      if (!x) return `El capítulo ${c.nombre} no tiene el componente «${id}»`;
      if (k === 'enfoque' && !x.enfoque) return `«${x.nombre}» no tiene un lugar propio en la maqueta`;
    }
    if (cambios.inmersion != null && cambios.inmersion !== 'maqueta' && !catalogo.has(cambios.inmersion)) return 'La presentación no tiene esa inmersión';
    const limpio = depurar(cambios, estado.ci).visual;
    for (const k of Object.keys(cambios)) if (k !== 'tema' && !(k in INICIAL)) delete limpio[k];
    for (const k of LISTAS) if (limpio[k] !== undefined) limpio[k] = [...limpio[k]];
    const antes = { ...vis };
    Object.assign(vis, limpio);
    const cambio = (k) => limpio[k] !== undefined && !igual(vis[k], antes[k]);
    if (cambio('tema') && vis.tema) ponerTema(vis.tema);
    if (mov && typeof mov !== 'object') mov = null;
    const dur = Number.isFinite(ms) && ms > 0 ? entre(ms, PASEO_MS) : mov ? MOVER_MS : 0;
    const enf = cambio('enfoque'), comparo = cambio('comparar');
    const piezas = cambio('mostrar') || cambio('ocultar') || cambio('aislar') || cambio('sin');
    const camara = enf || cambio('camara') || cambio('rumbo') || cambio('elevacion') || cambio('zoom') || cambio('mirar');
    // la animación: la que se pide o, como siempre, la del paso que desarrolla el componente al que se va con un vuelo
    const otroPaso = enf && pasoCapas(c) !== paso();
    const conAnimacion = animar === true || (animar === undefined && !dur && otroPaso);
    // 1) qué hay que encuadrar (antes de que arranque una animación: las piezas a medio crecer miden menos). Si esta
    // orden no cambia la cámara pedida y la anterior la dejó en otro sitio con `mover`, el viaje SIGUE desde ahí: cada
    // paso de un plan parte del anterior (si volviera a la base, un giro repetido no movería nada y el movimiento suave
    // por omisión desharía el viaje anterior mientras se dice otra frase). La persona que tomó la cámara lo reinicia
    const sigue = !!dur && !camara && !!movido && !st.userMoved;
    if ((camara || dur) && !sigue) { movido = null; fijarBase(); }
    // 2) lo que se ve, en el acto y sin vuelo: capas, piezas, partes, hoy/proyecto y el estado de los módulos
    if (comparo && inm.abierta) irAtlas(vis.comparar === 'hoy' ? 'hoy' : inm.actual?.modo).catch(() => {});
    if (enf || comparo || piezas || conAnimacion) pintar({ animar: conAnimacion });
    // 3) la ficha, antes de calcular a dónde va la cámara: le quita ancho a la zona libre
    if (limpio.detalle !== undefined) verDetalle(vis.detalle, { reencuadre: !(camara || dur) });
    // 4) la cámara: un paseo de lo que dura la frase o, sin `ms`, un vuelo corto si cambió a dónde mira
    if (dur) viajar(dur, mov, { desdeAqui: sigue });
    else if (camara) { pendiente = false; volar(); }
    // el modelo del atlas tarda en cargar la primera vez: no se espera (la orden responde enseguida) y, si no carga, la
    // ventana lo dice
    if (limpio.inmersion !== undefined) aplicarInmersion().catch(fallaAtlas);
    pintarHud();
    avisar();
    return null;
  }

  /** Con una narración en pantalla (un plan guiado) los módulos no mueven la cámara por su cuenta: la lleva el plan. */
  function guiado(activo) { escena.guiado = !!activo; if (!activo && st.paseo) st.stopFlight(); }
  /** La pausa del plan también detiene el viaje de la cámara, y al seguir lo retoma: si no, la imagen terminaba sola el
   * movimiento del paso y lo que faltaba de la frase se decía sobre la imagen quieta. */
  function pausar(v) { const t = st.paseo; if (!t) return; if (v) t.pause(); else t.resume(); }

  function estadoVisual() {
    return { enfoque: vis.enfoque, camara: vis.camara, rumbo: vis.rumbo, elevacion: vis.elevacion, zoom: vis.zoom, mirar: vis.mirar, girar: vis.girar,
      comparar: vis.comparar, detalle: vis.detalle, inmersion: vis.inmersion, mostrar: [...vis.mostrar], ocultar: [...vis.ocultar], aislar: vis.aislar,
      sin: [...vis.sin], tema: vis.tema, abierta: inm.abierta ? inm.actual?.id ?? null : null,
      // lo que acciona `simular` en la maqueta 3D (no es estado del paso: es lo que se ve ahora)
      simulacion: sim.estado() };
  }

  /** Al cambiar de paso: todo vuelve a lo del paso (menos el tema); un paso de inmersión abre la suya. La ficha se cierra
   * sin reencuadrar (antes lanzaba un vuelo a la vista vieja, que el paso nuevo cortaba) y lo que se había mostrado,
   * ocultado o quitado lo deshace pasar3D antes de poner el paso nuevo. La simulación de la maqueta (la hora, las luces,
   * el partido) también vuelve a lo del paso. */
  function alPaso() {
    Object.assign(vis, INICIAL);
    for (const k of LISTAS) vis[k] = [];
    movido = null; pendiente = false;
    verDetalle(null, { reencuadre: false });
    pintarHud();
    sim.reiniciar();
    aplicarInmersion().catch(fallaAtlas);
  }

  // clics de la persona (cuando la presentación tiene controles): cerrar la ficha, volver a la maqueta, «Hoy | Con el
  // proyecto» en la barra
  document.addEventListener('click', (e) => {
    const a = e.target.closest('[data-accion]')?.dataset.accion;
    if (a === 'cerrar-detalle') aplicar({ detalle: null });
    else if (a === 'cerrar-inmersion') aplicar({ inmersion: 'maqueta' });
    else if (e.target.closest('.chip-estado')) aplicar({ comparar: vis.comparar === 'hoy' ? 'proyecto' : 'hoy' });
  });

  pintarHud();
  /** ¿Se puede aplicar `v` (lo visual de una escena) en el capítulo `ci`? null, o el error. Es la comprobación estricta
   * (el componente está en ese capítulo, con lugar en la maqueta para el enfoque; la inmersión, en el catálogo; las piezas
   * y las partes, en el catálogo del capítulo): quien quiera seguir con lo que sí vale usa `depurar`. */
  function validar(v, ci) {
    const c = caps[ci], comps = new Map((c?.componentes || []).map((x) => [x.id, x]));
    for (const k of ['enfoque', 'detalle']) {
      if (v[k] == null) continue;
      const x = comps.get(v[k]);
      if (!x) return `El capítulo ${c?.nombre || ''} no tiene el componente «${v[k]}»`;
      if (k === 'enfoque' && !x.enfoque) return `«${x.nombre}» no tiene un lugar propio en la maqueta`;
    }
    if (v.inmersion != null && v.inmersion !== 'maqueta' && !catalogo.has(v.inmersion)) return 'La presentación no tiene esa inmersión';
    const d = depurar(v, ci).descartadas[0];
    return d ? d.motivo.charAt(0).toUpperCase() + d.motivo.slice(1) : null;
  }
  // un modelo del atlas pedido que todavía carga (la escena espera a que esté antes de narrar)
  const cargando = () => inm.abierta && !capaInm.classList.contains('lista') && !inm.fallo;

  // ---------------------------------------------------------------- lo que el presentador sabe de la escena
  // (web/js/presentador/: mando.js se lo pasa con los avisos `encuadre` y `ambiente`, docs/presentador.md)
  /** La cámara donde termina el viaje: la postura del último encuadre con lo vigente (la cámara pedida, el final del
   * último `mover`, la misma cuenta de `enEncuadre`), o null si no hay encuadre que valga (la persona tomó la cámara,
   * todavía no hay ninguno o un modelo del atlas tapa la maqueta). */
  function camaraFinal() {
    if (st.userMoved || !ultimo || inmersionVigente()) return null;
    const p = escena.postura(ultimo.obj, opcionesDe(ultimo.opts));
    if (!p?.pts?.length) return null;
    const cam = st.camera.clone();
    cam.far = 1e7;
    cam.updateProjectionMatrix();
    cam.position.fromArray(p.pos);
    cam.lookAt(new THREE.Vector3().fromArray(p.tgt));
    cam.updateMatrixWorld();
    return { cam, p };
  }
  const redondo = (x) => Math.round(x);
  /** Dónde quedan, cuando la cámara llegue, la obra encuadrada y sus rótulos, en px de la ventana:
   * { obra: {x0, y0, x1, y1} | null, rotulos: [{x0, y0, x1, y1}] }, o null (ver `camaraFinal`). La obra es la caja de
   * los puntos de la postura proyectados con la cámara final (lo que queda delante de ella), recortada a la pantalla.
   * Los rótulos (.lbl-p y .lbl-pin a la vista) se ponen un momento donde los dejará esa cámara y se reparten como allí
   * (el reparto de escena.js: los que el panel taparía se corren, los que caen fuera se ocultan), se miden y vuelven a
   * su lugar con la cámara de ahora, sin que se pinte nada en el medio: cuentan el ancla de cada uno, su reparto y los
   * que todavía no se ven porque la cámara está lejos. Se llama una vez por escena (mando.js, tras `aplicar`). */
  function cajaObra() {
    const f = camaraFinal();
    if (!f) return null;
    const r = st.el.getBoundingClientRect();
    if (!r.width || !r.height) return null;
    const { cam, p } = f, v = new THREE.Vector3();
    const recortar = (x0, y0, x1, y1) => {
      const c = [Math.max(x0, r.left), Math.max(y0, r.top), Math.min(x1, r.right), Math.min(y1, r.bottom)].map(redondo);
      return c[2] > c[0] && c[3] > c[1] ? { x0: c[0], y0: c[1], x1: c[2], y1: c[3] } : null;
    };
    const b = [Infinity, -Infinity, Infinity, -Infinity];
    for (const q of p.pts) {
      v.copy(q).applyMatrix4(cam.matrixWorldInverse);
      if (v.z > -cam.near) continue;   // detrás de la cámara
      v.applyMatrix4(cam.projectionMatrix);
      const x = r.left + ((v.x + 1) / 2) * r.width, y = r.top + ((1 - v.y) / 2) * r.height;
      b[0] = Math.min(b[0], x); b[1] = Math.max(b[1], x); b[2] = Math.min(b[2], y); b[3] = Math.max(b[3], y);
    }
    const obra = b[1] > b[0] ? recortar(b[0], b[2], b[1], b[3]) : null;
    const rotulos = [];
    // (la cámara de la escena, un momento en la postura final: el reparto proyecta con ella; durante un paseo se rehace
    // a lo sumo cuatro veces por segundo, y aquí tiene que correr en el acto)
    const c0 = st.camera, pos0 = c0.position.clone(), q0 = c0.quaternion.clone(), t0 = st._tReparto;
    const poner = () => {
      c0.updateMatrixWorld();
      st.labels.render(st.scene, c0);
      st._tReparto = 0;
      if (st.declutter && typeof st.declutterLabels === 'function') st.declutterLabels();
    };
    try {
      c0.position.copy(cam.position);
      c0.quaternion.copy(cam.quaternion);
      poner();
      for (const o of st._labels) {
        const e = o.element;
        if (!o.visible || !e?.isConnected || e.style.display === 'none' || e.classList.contains('fuera')) continue;
        if (!e.classList.contains('lbl-p') && !e.classList.contains('lbl-pin')) continue;
        const k = e.getBoundingClientRect();
        if (!k.width || !k.height || getComputedStyle(e).visibility === 'hidden') continue;
        const c = recortar(k.left, k.top, k.right, k.bottom);
        if (c) rotulos.push(c);
      }
    } catch (e) { console.warn('visual.cajaObra', e); }
    finally {
      c0.position.copy(pos0);
      c0.quaternion.copy(q0);
      try { poner(); } catch { /* el cuadro siguiente los vuelve a poner */ }
      st._tReparto = t0;
    }
    return { obra, rotulos };
  }
  /** La luz de la maqueta (ambiente.js), para que el presentador la siga: { hora, luz, intensidad, cielo, piso, hemi,
   * oscuridad, sol: [x, y, z], solFin }. `hora` es la que se ve (en el ciclo del día, la más cercana; los números y los
   * colores son los de la hora intermedia); los colores, '#rrggbb'; `sol`, la dirección hacia el sol en el espacio de la
   * cámara de ahora (x > 0: el sol está a la derecha de la pantalla) y `solFin`, en el de la cámara donde termina el
   * viaje (la misma si no hay viaje que valga). null sin ambiente. */
  const dirSol = new THREE.Vector3();
  function luz() {
    const a = escena.ambiente, h = a?.datos?.();
    if (!h || !Array.isArray(h.sol)) return null;
    const color = (c) => `#${new THREE.Color(c).getHexString()}`;
    const r3 = (x) => Math.round(x * 1000) / 1000;
    const enCamara = (cam) => dirSol.fromArray(h.sol).normalize().transformDirection(cam.matrixWorldInverse).toArray().map(r3);
    st.camera.updateMatrixWorld();
    const sol = enCamara(st.camera), fin = camaraFinal();
    return { hora: a.hora?.() ?? null, luz: color(h.luz), intensidad: r3(h.intensidad), cielo: color(h.cielo), piso: color(h.piso),
      hemi: r3(h.hemi), oscuridad: r3(h.oscuridad ?? 0), sol, solFin: fin ? enCamara(fin.cam) : sol };
  }

  return { aplicar, mover, simular, guiado, pausar, depurar, estado: estadoVisual, alPaso, validar, cargando,
    // para el presentador: la obra y sus rótulos donde terminan, la luz de la maqueta y el modo de una inmersión
    // (torre, pisos, recorrido, sismo, bim, parque, hoy, laboratorio)
    cajaObra, luz, modoDe: (id) => catalogo.get(id)?.modo ?? null,
    // los controles de la simulación de la maqueta en el capítulo a la vista
    controlesMaqueta: () => sim.controles(),
    // para pasar3D (main.js): lo que el asistente muestra, oculta o aísla encima del paso, y la vista del paso sin vuelo
    ajustar, efectos, deshacer, enSeco,
    // repite el encuadre pedido (cámara, enfoque, mirar o el final del último movimiento); false si no hay ninguno
    // (main.js vuelve entonces a medir la vista del paso: cambió el tamaño de la pantalla)
    reencuadrar: () => { if (st.paseo || hayCamara()) { reencuadrar(); return true; } return false; },
    // vuelve al encuadre vigente tal como quedó anotado (la persona había movido la cámara); un paseo en curso ya va a él
    restaurar: () => { if (!st.paseo) { fijarBase(); volar(); } },
    abrirDetalle: (id) => aplicar({ detalle: id, ...(comp(id)?.enfoque ? { enfoque: id } : {}) }) };
}
