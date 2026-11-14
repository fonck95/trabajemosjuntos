// Lo que el asistente del panel y los agentes por MCP pueden cambiar de lo que se ve en la presentación técnica, sin
// cambiar de paso (la orden `visual` de mando.js; la herramienta `presentacion`, op `visual`):
// * camara: el encuadre del paso ('paso'), una vista aérea, oblicua o rasante, más cerca o más lejos; rumbo: desde
//   dónde se mira, en grados desde el norte (null, el del paso); girar: la cámara gira despacio alrededor de la obra.
// * enfoque: la cámara va a un componente del capítulo (el id de la propuesta): al paso que lo desarrolla, a sus sitios
//   o trazados de geo.json o a la réplica de una sede (`enfoque` de cada componente, que calcula build_propuesta.py).
// * comparar: 'hoy' deja el sitio como está (sin las capas del proyecto, con las casas y las sedes de hoy) en el mismo
//   encuadre; 'proyecto' lo devuelve. En una inmersión cambia el modo del atlas («Hoy»).
// * detalle: la ficha técnica de un componente en un panel lateral (lo que hace, especificaciones sin plata, referente
//   técnico, dónde y plazo).
// * inmersion: un modelo del atlas a pantalla completa (la torre por dentro, el simulador sísmico, el modelo BIM, el
//   parque del relleno), en un marco del mismo origen que habla con js/escenario.js. 'maqueta' la cierra en un paso de
//   inmersión; null, lo del paso.
// * tema: claro u oscuro (para el proyector), también en el atlas enmarcado.
// Todo vuelve a como lo dice el paso al cambiar de paso, salvo el tema. Las comprobaciones de forma (tipos, listas) las
// hace mando.js; aquí, las que dependen de lo que hay (el componente existe en el capítulo y tiene lugar en la maqueta,
// la inmersión está en el catálogo).
import { THREE, gsap, reducedMotion } from '../core.js';
import { sinPlata, especificacionTecnica, anios } from './tecnica.js';
import { caja } from './modulos/comun.js';

export const CAMARAS = ['paso', 'aerea', 'oblicua', 'rasante', 'cerca', 'lejos'];
// elevación (grados sobre el horizonte) y cuánto más grande queda la obra en la zona libre (el `margen` de encuadrar)
const PRESET = { paso: {}, aerea: { elev: 80 }, oblicua: { elev: 34 }, rasante: { elev: 11, k: 1.1 }, cerca: { k: 1.9 }, lejos: { k: 0.5 } };
export const INICIAL = Object.freeze({ enfoque: null, camara: 'paso', rumbo: null, girar: false, comparar: 'proyecto', detalle: null, inmersion: null });
const VUELTA_S = 70;   // segundos por vuelta con «girar»
const ESPERA_ATLAS_MS = 30000;

const esc = (t) => String(t ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

export function crearVisual({ escena, datos, caps, estado, ctx3d, pres, pasar3D, capasVisibles, colorDe }) {
  const vis = { ...INICIAL, tema: null };
  const tec = datos.tecnica || {};
  const catalogo = new Map((tec.inmersiones || []).map((i) => [i.id, i]));
  const st = escena.st;
  const cap = () => caps[estado.ci], paso = () => cap()?.pasos[estado.pi];
  const comp = (id) => (cap()?.componentes || []).find((x) => x.id === id) || null;
  const avisar = () => dispatchEvent(new CustomEvent('propuesta:visual', { detail: estadoVisual() }));

  // ---------------------------------------------------------------- encuadres con la cámara pedida
  // Todos los encuadres de los módulos pasan por aquí: se guarda el último (para repetirlo con otra cámara) y se le
  // aplican el preset y el rumbo vigentes
  let ultimo = null;
  const encuadrar0 = escena.encuadrar;
  escena.encuadrar = (obj, opts = {}) => {
    ultimo = { obj, opts };
    const p = PRESET[vis.camara] || {};
    return encuadrar0(obj, { ...opts, ...(vis.rumbo != null ? { rumbo: vis.rumbo } : {}), ...(p.elev != null ? { elev: p.elev } : {}),
      margen: Math.min(2.4, (opts.margen ?? 0.86) * (p.k ?? 1)) });
  };
  const reencuadrar = () => { if (ultimo) escena.encuadrar(ultimo.obj, { ...ultimo.opts, duracion: 1.4 }); };

  // girar: la cámara da la vuelta a lo que mira, sin perder la distancia ni la altura; la persona que arrastra la detiene
  const eje = new THREE.Vector3(0, 1, 0), off = new THREE.Vector3();
  st.onFrame((dt) => {
    if (!vis.girar || st.flying || !st.running) return false;
    off.copy(st.camera.position).sub(st.controls.target).applyAxisAngle(eje, (-2 * Math.PI * Math.min(dt, 0.1)) / VUELTA_S);
    st.camera.position.copy(st.controls.target).add(off);
    st.camera.lookAt(st.controls.target);
    return true;
  });
  // la persona tomó la cámara: deja de girar y se avisa como suyo (un recorrido que suena se pausa, mando.js)
  st.controls.addEventListener('start', () => {
    vis.girar = false;
    dispatchEvent(new CustomEvent('propuesta:visual', { detail: { ...estadoVisual(), por: 'persona' } }));
  });

  // ---------------------------------------------------------------- brújula, escala y estado (pantallas grandes)
  const hud = document.createElement('div');
  hud.className = 'hud-tec';
  hud.setAttribute('aria-hidden', 'true');
  hud.innerHTML = `<div class="hud-chips"><span class="chip-estado"><i></i><b>Con el proyecto</b></span><span class="chip-enfoque" hidden><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="7" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="2" fill="currentColor"/></svg><b></b></span></div>
    <div class="hud-instr"><div class="escala"><i></i><span>—</span></div><svg class="brujula" viewBox="0 0 48 48"><circle cx="24" cy="24" r="22" class="aro"/><g class="aguja"><path d="M24 6 29 24H19z" class="n"/><path d="M24 42 19 24h10z" class="s"/><text x="24" y="17.5" text-anchor="middle">N</text></g></svg></div>`;
  pres.append(hud);
  const aguja = hud.querySelector('.aguja'), escala = hud.querySelector('.escala'), escalaI = escala.querySelector('i'), escalaT = escala.querySelector('span');
  const chipEstado = hud.querySelector('.chip-estado'), chipEnfoque = hud.querySelector('.chip-enfoque');
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
  }

  // ---------------------------------------------------------------- enfoque
  function puntosDe(c, e) {
    const g = datos.geo?.[c.id] || {}, pts = [];
    for (const id of e.sitios || []) { const s = (g.sitios || []).find((x) => x.id === id); if (s?.poligono) pts.push(...s.poligono); else if (s) pts.push([s.x, s.y]); }
    for (const id of e.trazados || []) { const t = (g.trazados || []).find((x) => x.id === id); if (t?.puntos) pts.push(...t.puntos); }
    return pts;
  }
  function enfocar(id) {
    const c = cap(), p = paso();
    if (!id) { pasar3D(c, p); return; }
    const x = comp(id), e = x?.enfoque, m = ctx3d[c.id];
    if (e?.paso) { const q = c.pasos.find((k) => k.id === e.paso); if (q) { pasar3D(c, q); return; } }
    // sus sitios, sus trazados o la réplica de una sede, con las capas principales del módulo
    escena.verCapas([...new Set([...(m?.siempre || []), ...capasVisibles(), ...(m?.completo || [])])]);
    escena.soloEtiquetas(null);
    const cajas = (e?.edificios || []).map((k) => escena.cajaEdificio(k)).filter(Boolean);
    const pts = puntosDe(c, e || {});
    if (cajas.length) { const b = cajas.reduce((a, k) => a.union(k), cajas[0].clone()); escena.encuadrar(b, { rumbo: 160, elev: 32, margen: 0.6, minDist: 30, apartar: true }); }
    else if (pts.length) escena.encuadrar(caja(pts, 25), { rumbo: 200, elev: 40, margen: 0.66, minDist: 40, apartar: true });
  }

  // ---------------------------------------------------------------- hoy / con el proyecto
  function prefijo(m) {
    for (const d of Object.values(m?.pasos || {})) { const k = (d?.capas || [])[0]; if (k) return k.split('.')[0]; }
    return (m?.completo || [])[0]?.split('.')[0] || null;
  }
  function comparar(cual) {
    const c = cap(), m = ctx3d[c.id];
    if (inm.abierta) { irAtlas(cual === 'hoy' ? 'hoy' : inm.actual?.modo).catch(() => {}); return; }
    if (cual === 'hoy') {
      const pre = prefijo(m);
      m?.salir?.();
      escena.verCapas([...escena.capas.keys()].filter((k) => pre && k === `${pre}.hoy`));
      escena.soloEtiquetas(null);
      escena.zonasHoy.forEach((z) => escena.verHoy(z.id, true));
      st.invalidate(true);
    } else if (vis.enfoque) enfocar(vis.enfoque);
    else pasar3D(c, paso());
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
  function verDetalle(id) {
    const c = cap(), x = id ? comp(id) : null;
    if (!x) { if (!det.hidden) { det.hidden = true; pres.classList.remove('con-detalle'); setTimeout(reencuadrarSiQuieto, 60); if (inm.abierta) ubicarInmersion(); } return; }
    det.style.setProperty('--mc', colorDe(c.id));
    det.innerHTML = fichaHTML(c, x);
    const abria = det.hidden;
    det.hidden = false;
    pres.classList.add('con-detalle');
    if (abria && gsap && !reducedMotion) gsap.fromTo(det, { x: 40, opacity: 0 }, { x: 0, opacity: 1, duration: 0.45, ease: 'power3.out' });
    if (abria) setTimeout(reencuadrarSiQuieto, 60);
    if (inm.abierta) ubicarInmersion();
  }
  // la ficha le quita ancho a la maqueta: se vuelve a encuadrar lo que se miraba (si la persona no movió la cámara)
  const reencuadrarSiQuieto = () => { if (!st.userMoved) reencuadrar(); };

  // ---------------------------------------------------------------- inmersión en un modelo del atlas
  const inm = { abierta: false, actual: null, marco: null, puente: null, fallo: false };
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
  async function aplicarInmersion() {
    const id = inmersionVigente();
    if (!id) { cerrarInmersion(); return; }
    if (inm.actual?.id === id && inm.abierta) return;
    await abrirInmersion(id);
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

  // ---------------------------------------------------------------- lo que pide la orden `visual`
  /** Aplica `cambios` (solo las claves que trae; las formas ya las revisó mando.js). Devuelve null o el error. */
  async function aplicar(cambios) {
    const c = cap();
    if (!c) return 'La presentación todavía no muestra ningún paso';
    for (const k of ['enfoque', 'detalle']) {
      const id = cambios[k];
      if (id == null) continue;
      const x = comp(id);
      if (!x) return `El capítulo ${c.nombre} no tiene el componente «${id}»`;
      if (k === 'enfoque' && !x.enfoque) return `«${x.nombre}» no tiene un lugar propio en la maqueta`;
    }
    if (cambios.inmersion != null && cambios.inmersion !== 'maqueta' && !catalogo.has(cambios.inmersion)) return 'La presentación no tiene esa inmersión';
    const antes = { ...vis };
    Object.assign(vis, cambios);
    if (cambios.tema && cambios.tema !== antes.tema) ponerTema(cambios.tema);
    const camara = (cambios.camara !== undefined && cambios.camara !== antes.camara) || (cambios.rumbo !== undefined && cambios.rumbo !== antes.rumbo);
    if (cambios.enfoque !== undefined && cambios.enfoque !== antes.enfoque) enfocar(vis.enfoque);
    else if (cambios.comparar !== undefined && cambios.comparar !== antes.comparar) comparar(vis.comparar);
    else if (camara) reencuadrar();
    if (cambios.enfoque !== undefined && cambios.enfoque !== antes.enfoque && vis.comparar === 'hoy') comparar('hoy');
    if (cambios.detalle !== undefined) verDetalle(vis.detalle);
    // el modelo del atlas tarda en cargar la primera vez: no se espera (la orden responde enseguida) y, si no carga, la
    // ventana lo dice
    if (cambios.inmersion !== undefined) aplicarInmersion().catch(fallaAtlas);
    pintarHud();
    avisar();
    return null;
  }

  function estadoVisual() {
    return { enfoque: vis.enfoque, camara: vis.camara, rumbo: vis.rumbo, girar: vis.girar, comparar: vis.comparar, detalle: vis.detalle,
      inmersion: vis.inmersion, tema: vis.tema, abierta: inm.abierta ? inm.actual?.id ?? null : null };
  }

  /** Al cambiar de paso: todo vuelve a lo del paso (menos el tema); un paso de inmersión abre la suya. */
  function alPaso() {
    Object.assign(vis, INICIAL);
    verDetalle(null);
    pintarHud();
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
  /** ¿Se puede aplicar `v` (lo visual de una escena) en el capítulo `ci`? null, o el error (mando.js valida la escena
   * entera antes de mover nada: el componente está en ese capítulo, con lugar en la maqueta para el enfoque, y la
   * inmersión en el catálogo). */
  function validar(v, ci) {
    const c = caps[ci], comps = new Map((c?.componentes || []).map((x) => [x.id, x]));
    for (const k of ['enfoque', 'detalle']) {
      if (v[k] == null) continue;
      const x = comps.get(v[k]);
      if (!x) return `El capítulo ${c?.nombre || ''} no tiene el componente «${v[k]}»`;
      if (k === 'enfoque' && !x.enfoque) return `«${x.nombre}» no tiene un lugar propio en la maqueta`;
    }
    if (v.inmersion != null && v.inmersion !== 'maqueta' && !catalogo.has(v.inmersion)) return 'La presentación no tiene esa inmersión';
    return null;
  }
  // un modelo del atlas pedido que todavía carga (la escena espera a que esté antes de narrar)
  const cargando = () => inm.abierta && !capaInm.classList.contains('lista') && !inm.fallo;

  return { aplicar, estado: estadoVisual, alPaso, validar, cargando, reencuadrar: () => { if (vis.enfoque || vis.camara !== 'paso' || vis.rumbo != null) { reencuadrar(); return true; } return false; },
    abrirDetalle: (id) => aplicar({ detalle: id, ...(comp(id)?.enfoque ? { enfoque: id } : {}) }) };
}
