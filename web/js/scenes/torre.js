// Escena 3D y fichas de la torre de servicios de primer nivel de la E.S.E. Hospital Héctor Abad Gómez, sobre el sitio del
// antiguo Centro Vida (alas occidentales del predio, que se demuelen). Modos: "Hoy" (las alas), "Con la torre" (el modelo
// generado desde data/edificios/torre_hospital.json), "Pisos por servicio" (los cuatro pisos separados, cada servicio con su
// color de grupo de la Res. 1633 de 2025 y su área), "Laboratorio" (el piso 2 con mesones y analizadores), y los dos modos de
// la especificación de integración (data/proyectos/torre_hospital/ESPECIFICACION_INTEGRACION.md): "Recorrer por dentro"
// (módulo ./torre/recorrido.js, equipo C) y "Simulador sísmico" (./torre/sismo.js, equipo D). Abajo, las tarjetas de
// dotación para la habilitación (./torre/habilitacion.js, C) y de contraste con el proyecto tipo (./torre/contraste.js, E).
// Esos módulos se cargan solo al pedirlos; mientras no existan se usa ./torre/_relleno.js («en construcción»).
// Los datos del proyecto (programa, norma, dotación, laboratorio, presupuesto, APU, financiación y proyectos) vienen de
// data/proyectos/torre_hospital/ y se cargan aparte (data/torre.json) al abrir la vista; los de los modos nuevos
// (data/torre_*.json y data/sismo_*.json, que escribe scripts/build_data.py) al entrar a cada modo o al abrir cada tarjeta.
import { THREE, Stage, tokens, onTheme, mat, box, fmtN, fmtCOP, gsap, solidBox, engine } from '../core.js';
import { progressiveLOD } from '../assets.js';
import { EDIFICIOS } from '../data.js';
import { limpio, esc, escH } from './torre/textos.js';

const TEXTOS = { limpio, esc, escH };   // lo que reciben los módulos de C, D y E en ctx.textos (13.6)
// módulos de los modos y tarjetas nuevos. Si el del equipo dueño todavía no está (404) o no carga, se usa el relleno; un
// módulo que existe pero falla al evaluarse se avisa en la consola para que su equipo lo vea
const relleno = (e) => {
  if (!/Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module/i.test(String(e?.message || e))) console.warn('torre: módulo con errores; se usa el relleno', e);
  return import('./torre/_relleno.js');
};
const MODULOS = {
  recorrido: () => import('./torre/recorrido.js').catch(relleno),
  sismo: () => import('./torre/sismo.js').catch(relleno),
  habilitacion: () => import('./torre/habilitacion.js').catch(relleno),
  contraste: () => import('./torre/contraste.js').catch(relleno),
};
const NUEVOS = ['recorrido', 'sismo'];   // modos con módulo propio (6.8 y 8.6)
// obra nueva del GLB: el recorrido y el simulador la ocultan porque el GLB reparte entrepisos de 4,30 m que no coinciden con
// los niveles reales (1.2). Es el nodo «obra_nueva» entero (su suelo, letreros y equipos de cubierta van fundidos en una sola
// malla con el edificio) más los paneles solares y los equipos de la cubierta; quedan lo existente, el terreno y la conexión
const EDIFICIO_GLB = new Set(['obra_nueva', 'solar', 'equipos']);
// capa «Proyecto tipo» (9.2): placa de un piso con el área del puesto de salud tipo del DNP 2018 (320,6 m², dato del proyecto
// tipo, pág. 25), a la misma escala que la torre. Posición fija, centro en x = −46, y = 0 (marco de la especificación): al
// occidente del predio modelado, que llega hasta x ≈ −36. No se cruza con el hospital actual (al nororiente), la galería
// (y ≈ 29), el bloque técnico (y de −24,8 a −20,8) ni con los árboles, postes y parqueaderos del occidente (x ≥ −34). El ejemplo
// del contrato (x = −30) caía sobre el parqueadero y dos árboles
const AREA_TIPO = 320.6, TIPO_XY = [-46, 0];

// grupos de servicio con sus colores de señalización (Res. 1633 de 2025): rojo urgencias, naranja consulta, amarillo apoyo
// diagnóstico y terapéutico, azul internación, verde esterilización, violeta administración, café servicios generales
const GRUPOS = [
  [/urgenc|reanim|expansi/i, '#d62828', 'Urgencias'],
  [/hospitaliz|parto|interna|obst/i, '#2f6db3', 'Internación'],
  [/esteriliz/i, '#2a9d8f', 'Esterilización'],
  [/laborat|muestra|im[aá]gen|rayos|ecograf|farmac|citolog/i, '#e3a91c', 'Apoyo diagnóstico y terapéutico'],
  [/consulta|odonto|terap|telemed|telesal|psicol|nutri|vacun|promoci/i, '#f08a00', 'Consulta y ambulatorio'],
  [/vest[ií]bulo|admisi|coordin|administ|crisis/i, '#7b5ea7', 'Administración y acceso'],
  [/apoyo|t[eé]cnic|general|ducto/i, '#8d6e63', 'Servicios generales'],
];
const grupo = (n) => GRUPOS.find(([re]) => re.test(n)) || [null, '#9aa0a6', 'Otros'];
const XW = [-13.0, 3.1], XN = [3.1, 9.0];            // franja de servicios y franja del núcleo (marco de la especificación)
const YP = (piso) => (piso === 4 ? [-7.6, 22.4] : [-19.6, 22.4]);
const cop = (v) => (v == null || Number.isNaN(+v) ? '—' : fmtCOP(+v));

export function mount(root) {
  const el = root.querySelector('.stage');
  const st = new Stage(el, { cam: [-78, 52, 70], target: [-2, 7, -2], fov: 36, minDist: 6, maxDist: 500, tone: 'aces', exposure: 1.05, fit: 0.85, declutter: ['lbl-node', 'lbl-room'] });
  const T = tokens(), S = st.scene;
  const sc = st.sunLight.shadow.camera; Object.assign(sc, { left: -90, right: 90, top: 90, bottom: -90, near: 1, far: 400 });
  st.sunLight.position.set(60, 120, 40); st.sunLight.shadow.mapSize.set(2048, 2048);
  const ground = new THREE.Mesh(new THREE.CircleGeometry(260, 64), mat(T.ground)); ground.rotation.x = -Math.PI / 2; ground.position.y = -0.06; ground.receiveShadow = true; S.add(ground); st.freeze(ground);

  // modelos: la torre (marco de su especificación) y el hospital actual como contexto, en su posición real relativa
  const TOR = EDIFICIOS.find((e) => e.id === 'torre_hospital'), HOS = EDIFICIOS.find((e) => e.id === 'hospital');
  const off = (e) => [(e.lon - TOR.lon) * 111320 * Math.cos((TOR.lat * Math.PI) / 180), (e.lat - TOR.lat) * 111320];
  let torre = null, modo = 'torre', gHosp = null;
  // estado de los modos nuevos: modo montado y en curso, selección del Stage guardada mientras dura, piezas ocultas del
  // exterior (null, 'parcial' en el simulador o 'total' en el recorrido) y turno del último cambio de modo pedido
  let activo = null, guardados = null, exterior = null, turno = 0, tEncuadre = 0, tSep = null, capaTipo = false;
  const instancias = {}, cargando = {}, modulos = {};
  const nuevo = () => NUEVOS.includes(modo);
  const gTorre = new THREE.Group(); S.add(gTorre);
  if (TOR?.archivo) {
    torre = progressiveLOD([{ url: TOR.archivo, distance: 0 }, { url: TOR.archivo_lod1, distance: 420 }], () => { aplicar(false); st.updateShadows(); encuadre(); });
    gTorre.add(torre);
  }
  if (HOS?.archivo && TOR) {
    const [hx, hy] = off(HOS), g = new THREE.Group(); g.position.set(hx, 0, -hy); S.add(g); gHosp = g;
    g.add(progressiveLOD([{ url: HOS.archivo, distance: 0 }, { url: HOS.archivo_lod1, distance: 300 }], (lod) => {
      // del hospital actual solo se ve el edificio (sus paneles y equipos son de otro proyecto)
      lod.traverse((o) => { if (o.name === 'adecuaciones') o.visible = false; });
      arboles();
      st.updateShadows();
    }));
  }
  // en el recorrido y el simulador la cámara es del modo: ni la carga del GLB ni la capa del proyecto tipo la mueven (6.8);
  // solo con el relleno «en construcción», que no maneja la cámara, se encuadra la torre por fuera (forzar)
  const encuadre = (forzar = false) => {
    if (!torre || (nuevo() && !forzar)) return;
    const caja = solidBox(torre);
    if (capaTipo && modo === 'torre' && gTipo.children.length) caja.union(new THREE.Box3().setFromObject(gTipo));
    st.frameBox(caja, new THREE.Vector3(-0.75, 0.55, 0.62), { margin: 0.78, duration: 1.4 });
  };
  const gTipo = new THREE.Group(); gTipo.position.set(TIPO_XY[0], 0, -TIPO_XY[1]); gTipo.visible = false; S.add(gTipo);
  let lblTipo = null;

  // pisos por servicio (se arman cuando llega data/torre.json)
  const gPisos = new THREE.Group(); gPisos.visible = false; S.add(gPisos);
  const pisos = [], zonas = [], labLab = [];
  let D = null, sep = 0, selPiso = null;
  // la leyenda de colores por servicio solo aplica a «Pisos por servicio»: en los demás modos el modelo no tiene esos colores
  const leyenda = root.querySelector('[data-slot="torre.leyenda"]');
  if (leyenda) leyenda.hidden = true;
  const angosto = () => el.clientWidth < 560;

  function aplicar(anim = true) {
    // el recorrido y el simulador parten de «Con la torre»; cada uno oculta lo suyo con ctx.exterior.ocultar
    if (torre) torre.traverse((o) => {
      if (o.userData.demoler) o.visible = modo === 'hoy';
      if (o.name === 'adecuaciones') o.visible = modo === 'torre' || nuevo();
      if (EDIFICIO_GLB.has(o.name)) o.visible = !exterior;
      if (o.name === 'conexion') o.visible = exterior !== 'total';   // la acometida llega al hospital, que el recorrido oculta
    });
    if (gHosp) gHosp.visible = exterior !== 'total';
    gTipo.visible = capaTipo && modo === 'torre';
    if (lblTipo) lblTipo.visible = gTipo.visible;
    if (capas) capas.hidden = modo !== 'torre';
    if (leyenda) leyenda.hidden = modo !== 'pisos';
    const conPisos = modo === 'pisos' || modo === 'laboratorio';
    gPisos.visible = conPisos;
    pisos.forEach((p) => { p.g.visible = modo !== 'laboratorio' || p.piso <= 2; });   // en «Laboratorio» los pisos 3 y 4 tapaban la vista
    arboles();
    etiquetas();
    zonas.forEach((z) => { const on = modo !== 'laboratorio' || z.lab; z.mesh.material.opacity = on ? 1 : 0.18; z.mesh.material.transparent = !on; z.mesh.material.depthWrite = on; });
    const meta = conPisos ? (modo === 'laboratorio' ? 2.2 : 1) : 0;
    tSep?.kill(); tSep = null;
    if (gsap && anim) tSep = gsap.to({ v: sep }, { v: meta, duration: 1.1, ease: 'power3.inOut', onUpdate() { sep = this.targets()[0].v; apilar(); } });
    else { sep = meta; apilar(); }
    st.updateShadows();
  }
  // con los pisos abiertos los árboles de los dos modelos se ocultan: tapaban los servicios del primer piso
  function arboles() { const v = modo !== 'pisos' && modo !== 'laboratorio' && exterior !== 'total'; S.traverse((o) => { if (/arboles$/.test(o.name)) o.visible = v; }); }
  // etiquetas: en «Pisos» el título de cada piso, los servicios grandes y todos los del piso elegido; en «Laboratorio», sus
  // salas y equipos. En el teléfono no caben: en «Pisos» van los títulos y, al tocar un piso, solo su título y sus servicios
  // de 20 m² o más (el resto está en la ficha del piso); en «Laboratorio», solo los nombres de las salas analíticas (los
  // equipos están en la tarjeta del laboratorio)
  function etiquetas() {
    const conPisos = modo === 'pisos' || modo === 'laboratorio', tel = angosto();
    pisos.forEach((p) => { p.tit.visible = conPisos && (modo === 'pisos' ? !tel || selPiso == null || selPiso === p.piso : p.piso === 2 && !tel); });
    zonas.forEach((z) => { z.label.visible = conPisos && (modo === 'pisos' ? (tel ? selPiso === z.piso && z.m2 >= 20 : z.m2 >= 90 || selPiso === z.piso) : z.lab && z.piso === 2 && !tel); });
    labLab.forEach((l) => { l.visible = modo === 'laboratorio' && (!tel || (l.element.classList.contains('lbl-room') && l.userData.fila === 0)); });
    st.invalidate();
  }
  function apilar() {
    pisos.forEach((p, i) => { p.g.position.y = p.nivel + sep * 4.5 * i; });
    st.invalidate(true);
  }

  function armarPisos(prog) {
    const mPlaca = mat(new THREE.Color('#e9e8e3'), { roughness: 0.9 }), mNucleo = mat(new THREE.Color('#b9b7b1'), { roughness: 0.8 });
    (prog.resumen_por_piso || []).forEach((p) => {
      const piso = +p.piso, [y0, y1] = YP(piso), L = y1 - y0, g = new THREE.Group();
      const placa = new THREE.Mesh(new THREE.BoxGeometry(XN[1] - XW[0] + 1.2, 0.35, L + 1.2), mPlaca);
      placa.position.set((XW[0] + XN[1]) / 2, 0.175, -(y0 + y1) / 2); placa.castShadow = placa.receiveShadow = true; g.add(placa);
      const nuc = new THREE.Mesh(new THREE.BoxGeometry(XN[1] - XN[0], 2.6, L - 0.4), mNucleo);
      nuc.position.set((XN[0] + XN[1]) / 2, 0.35 + 1.3, -(y0 + y1) / 2); nuc.castShadow = true; g.add(nuc);
      // franjas de servicio de norte a sur, proporcionales a su área útil
      const serv = Object.entries(p.m2_util_por_servicio || {}).filter(([, v]) => v > 0);
      const tot = serv.reduce((a, [, v]) => a + v, 0) || 1;
      let y = y1;
      serv.forEach(([nombre, m2]) => {
        const l = (L * m2) / tot, [, col] = grupo(nombre), yc = y - l / 2;
        const m = new THREE.Mesh(new THREE.BoxGeometry(XW[1] - XW[0] - 0.3, 2.2, Math.max(0.6, l - 0.3)), mat(new THREE.Color(col), { roughness: 0.6 }));
        m.position.set((XW[0] + XW[1]) / 2, 0.35 + 1.1, -yc); m.castShadow = m.receiveShadow = true; g.add(m);
        const label = st.label(`<b>${esc(nombre)}</b><br><small>${fmtN(m2, 0)} m² útiles</small>`, 'lbl-node', [XW[0] - 0.5, 3.4, -yc], g);
        zonas.push({ mesh: m, piso, nombre, m2, label, lab: /laborat/i.test(nombre), y0: y - l, y1: y });
        y -= l;
      });
      const tit = st.label(`<b>Piso ${piso}</b><br><small>${fmtN(p.m2_construido, 0)} m² · entrepiso ${fmtN(p.altura_entrepiso_m, 1)} m</small>`, 'lbl-node', [XN[1] + 1, 2.4, -(y0 + y1) / 2], g);
      g.position.y = +p.nivel_piso_terminado_m || 0;
      gPisos.add(g);
      st.pickable(g, { onPick: () => fichaPiso(p) });
      pisos.push({ piso, g, tit, nivel: +p.nivel_piso_terminado_m || 0 });
    });
    armarLaboratorio();
    aplicar(false);
  }

  const corto = (t, n) => { t = t.trim(); return t.length <= n ? t : `${t.slice(0, t.lastIndexOf(' ', n - 1))}…`; };
  // Laboratorio del piso 2 en planta de corte: sus salas (laboratorio.areas) a escala de su área, con muros bajos,
  // mesones con tope de resina y cada analizador en la sala que le corresponde; neveras, cabina de bioseguridad,
  // autoclave, centrífugas y microscopios salen de las condiciones de cada sala
  function armarLaboratorio() {
    const z = zonas.find((q) => q.lab && q.piso === 2), p2 = pisos.find((p) => p.piso === 2);
    const secs = (D?.laboratorio?.areas || []).filter((a) => +a.piso === 2 && /^Laboratorio:/.test(a.seccion)).map((a) => ({ n: a.seccion.replace(/^Laboratorio:\s*/, ''), m2: +a.area_m2 || 0 }));
    if (!z || !p2 || !secs.length) return;
    const g = new THREE.Group(); p2.g.add(g);
    const c = (h) => new THREE.Color(h);
    const M = {
      pisoA: mat(c('#e3eef2'), { roughness: 0.7 }), pisoB: mat(c('#ecebe6'), { roughness: 0.8 }), muro: mat(c('#fbfbf9'), { roughness: 0.85 }),
      meson: mat(c('#f1f2f0'), { roughness: 0.5 }), tope: mat(c('#2f3a40'), { roughness: 0.35 }), eq: mat(c('#e4e7ea'), { roughness: 0.35, metalness: 0.08 }),
      tapa: mat(c('#b9c2c8'), { roughness: 0.3, metalness: 0.2 }), pant: mat(c('#1d2731'), { roughness: 0.3, emissive: c('#2b6cb0'), emissiveIntensity: 0.3 }),
      vidrio: mat(c('#bfe3f0'), { roughness: 0.05, transparent: true, opacity: 0.45, depthWrite: false }), acero: mat(c('#c9ced2'), { roughness: 0.25, metalness: 0.65 }),
      oscuro: mat(c('#3a4148'), { roughness: 0.6 }), asiento: mat(c('#2c5d8a'), { roughness: 0.6 }),
    };
    const Y = 0.35 + 2.2, H = 1.0;   // cara superior de la franja (piso del laboratorio en esta vista) y alto del muro de corte
    // dos crujías: las salas analíticas al norte y las de apoyo al sur, cada una con el fondo proporcional a su área
    const analit = /recepci|centrifug|hematol|qu[ií]mica|inmunol|microbiol|uroan/i;
    const filas = [secs.filter((s) => analit.test(s.n)), secs.filter((s) => !analit.test(s.n))].filter((f) => f.length);
    const X0 = XW[0] + 0.15, X1 = XW[1] - 0.15, V0 = z.y0 + 0.15, V1 = z.y1 - 0.15, tot = secs.reduce((a, s) => a + s.m2, 0) || 1;
    const salas = [];
    let v = V1;
    filas.forEach((f, fi) => {
      const m2f = f.reduce((a, s) => a + s.m2, 0), d = ((V1 - V0) * m2f) / tot;
      let x = X0;
      f.forEach((s) => { const w = ((X1 - X0) * s.m2) / m2f; salas.push({ ...s, x0: x, x1: x + w, v0: v - d, v1: v, fila: fi, mesa: [], piso: [] }); x += w; });
      v -= d;
    });
    const muro = (xa, va, xb, vb) => {
      const L = Math.hypot(xb - xa, vb - va), m = box(xb !== xa ? L + 0.1 : 0.1, H, xb !== xa ? 0.1 : L + 0.1, M.muro, (xa + xb) / 2, Y, -(va + vb) / 2);
      g.add(m);
    };
    salas.forEach((s) => {
      const p = box(s.x1 - s.x0, 0.02, s.v1 - s.v0, s.fila === 0 ? M.pisoA : M.pisoB, (s.x0 + s.x1) / 2, Y + 0.005, -(s.v0 + s.v1) / 2); p.castShadow = false; g.add(p);
      if (s.x0 > X0 + 0.01) muro(s.x0, s.v0, s.x0, s.v1);
    });
    muro(X0, V0, X1, V0); muro(X0, V1, X1, V1); muro(X0, V0, X0, V1); muro(X1, V0, X1, V1);
    for (let i = 1; i < filas.length; i++) { const b = salas.find((s) => s.fila === i); muro(X0, b.v1, X1, b.v1); }

    // cada analizador a su sala; lo que no encaje va a química
    const sala = (re) => salas.find((s) => re.test(s.n)) || salas.find((s) => /qu[ií]mica/i.test(s.n)) || salas[0];
    const destino = (n) => (/hematol|coagul/i.test(n) ? /hematol/i : /GeneXpert|r[aá]pida/i.test(n) ? /inmunol/i : /orina|sediment/i.test(n) ? /uroan/i
      : /hemocult|antibiog|identific/i.test(n) ? /microbiol/i : /gases/i.test(n) ? /recepci/i : /qu[ií]mica/i);
    [...(D.laboratorio.equipos || [])].sort((a, b) => (b.precio || 0) - (a.precio || 0)).forEach((e) => {
      const s = sala(destino(e.nombre)), n = e.nombre;
      for (let u = 0; u < Math.min(3, +e.cantidad || 1); u++) {
        const it = { e: u === 0 ? e : null, tipo: /hemocult/i.test(n) ? 'hemocultivos' : /GeneXpert/i.test(n) ? 'genexpert' : /gases/i.test(n) ? 'portatil' : 'analizador',
          w: /5 partes|qu[ií]mica|inmunoens|orina/i.test(n) ? 0.95 : /identific/i.test(n) ? 0.65 : 0.55 };
        (it.tipo === 'hemocultivos' ? s.piso : s.mesa).push(it);
      }
    });
    const fijo = (re, lista, it) => { const s = salas.find((q) => re.test(q.n)); if (s) s[lista].push(it); };
    fijo(/centrifug/i, 'mesa', { tipo: 'centrifuga', w: 0.5 }); fijo(/centrifug/i, 'mesa', { tipo: 'centrifuga', w: 0.5 });
    fijo(/hematol/i, 'mesa', { tipo: 'microscopio', w: 0.45 }); fijo(/microbiol/i, 'piso', { tipo: 'cabina', w: 1.3 });
    fijo(/microbiol/i, 'mesa', { tipo: 'microscopio', w: 0.45 }); fijo(/uroan/i, 'mesa', { tipo: 'microscopio', w: 0.45 });
    fijo(/uroan/i, 'mesa', { tipo: 'poceta', w: 0.6 }); fijo(/lavado/i, 'piso', { tipo: 'autoclave', w: 0.75 }); fijo(/lavado/i, 'mesa', { tipo: 'poceta', w: 0.6 });
    fijo(/neveras/i, 'piso', { tipo: 'nevera', w: 0.75 }); fijo(/neveras/i, 'piso', { tipo: 'nevera', w: 0.75 });
    fijo(/dep[oó]sito/i, 'piso', { tipo: 'estante', w: 1.0 }); fijo(/dep[oó]sito/i, 'piso', { tipo: 'estante', w: 1.0 });
    fijo(/oficina/i, 'mesa', { tipo: 'monitor', w: 0.6 }); fijo(/vestidor/i, 'piso', { tipo: 'lockers', w: 1.2 }); fijo(/recepci/i, 'mesa', { tipo: 'monitor', w: 0.6 });

    // piezas (frente hacia +z local; se giran según el muro en que se apoyan)
    const pieza = {
      analizador(w) { const q = new THREE.Group(), h = w > 0.8 ? 0.7 : 0.45, d = w > 0.8 ? 0.7 : 0.5; q.add(box(w, h, d, M.eq), box(w * 0.94, 0.06, d * 0.94, M.tapa, 0, h), box(0.24, 0.17, 0.02, M.pant, w / 2 - 0.18, h * 0.55, d / 2 + 0.01), box(Math.min(0.36, w * 0.5), 0.05, 0.14, M.oscuro, -w / 2 + 0.24, 0.1, d / 2 + 0.07)); return [q, h + 0.06]; },
      genexpert(w) { const q = new THREE.Group(); q.add(box(w, 0.36, 0.5, M.eq)); for (let i = 0; i < 4; i++) q.add(box(0.09, 0.2, 0.02, M.oscuro, -w / 2 + 0.1 + i * 0.12, 0.08, 0.26)); return [q, 0.36]; },
      portatil() { const q = new THREE.Group(); q.add(box(0.28, 0.2, 0.3, M.eq), box(0.18, 0.1, 0.02, M.pant, 0, 0.08, 0.16)); return [q, 0.2]; },
      hemocultivos() { const q = new THREE.Group(); q.add(box(0.7, 1.3, 0.7, M.eq), box(0.62, 0.9, 0.02, M.tapa, 0, 0.3, 0.36), box(0.24, 0.17, 0.02, M.pant, 0.12, 1.05, 0.36)); return [q, 1.3]; },
      cabina() { const q = new THREE.Group(); q.add(box(1.3, 0.75, 0.75, M.acero), box(1.3, 1.05, 0.75, M.eq, 0, 0.75), box(1.18, 0.55, 0.02, M.vidrio, 0, 0.95, 0.38), box(1.3, 0.28, 0.75, M.tapa, 0, 1.8)); return [q, 2.08]; },
      nevera() { const q = new THREE.Group(); q.add(box(0.7, 1.9, 0.7, M.eq), box(0.6, 1.6, 0.02, M.vidrio, 0, 0.2, 0.36), box(0.03, 0.5, 0.04, M.acero, 0.25, 0.8, 0.39)); return [q, 1.9]; },
      autoclave() { const q = new THREE.Group(); q.add(box(0.7, 1.0, 0.7, M.acero)); const t = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.22, 0.05, 28), M.tapa); t.rotation.x = Math.PI / 2; t.position.set(0, 0.62, 0.37); q.add(t); return [q, 1.0]; },
      estante(w) { const q = new THREE.Group(); [-1, 1].forEach((sx) => [-1, 1].forEach((sz) => q.add(box(0.04, 1.9, 0.04, M.acero, (sx * (w - 0.04)) / 2, 0, (sz * 0.41) / 2)))); for (let i = 0; i < 5; i++) q.add(box(w, 0.025, 0.45, M.acero, 0, 0.12 + i * 0.42)); return [q, 1.9]; },
      lockers(w) { const q = new THREE.Group(); q.add(box(w, 1.8, 0.45, M.tapa)); for (let i = 1; i < 4; i++) q.add(box(0.01, 1.7, 0.01, M.oscuro, -w / 2 + (i * w) / 4, 0.05, 0.23)); return [q, 1.8]; },
      centrifuga() { const q = new THREE.Group(), cu = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.21, 0.3, 28), M.eq), ta = new THREE.Mesh(new THREE.CylinderGeometry(0.17, 0.17, 0.03, 28), M.tapa); cu.position.y = 0.15; ta.position.y = 0.31; q.add(cu, ta); return [q, 0.33]; },
      microscopio() { const q = new THREE.Group(); q.add(box(0.2, 0.04, 0.26, M.oscuro), box(0.05, 0.32, 0.06, M.oscuro, 0, 0.04, -0.09), box(0.12, 0.08, 0.2, M.eq, 0, 0.3, -0.02), box(0.14, 0.02, 0.14, M.acero, 0, 0.14, 0.03)); return [q, 0.38]; },
      poceta(w) { const q = new THREE.Group(); q.add(box(w * 0.75, 0.012, 0.42, M.acero, 0, 0)); const l = new THREE.Mesh(new THREE.CylinderGeometry(0.015, 0.015, 0.28, 10), M.acero); l.position.set(0, 0.14, -0.24); q.add(l); return [q, 0.28]; },
      monitor() { const q = new THREE.Group(); q.add(box(0.5, 0.3, 0.03, M.pant, 0, 0.12, -0.1), box(0.06, 0.12, 0.06, M.oscuro, 0, 0, -0.12), box(0.4, 0.02, 0.14, M.oscuro, 0, 0, 0.12)); return [q, 0.42]; },
    };
    const silla = (x, zz) => { const t = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.18, 0.06, 18), M.asiento), p = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.025, 0.55, 8), M.acero); t.position.set(x, Y + 0.6, zz); p.position.set(x, Y + 0.3, zz); t.castShadow = true; g.add(t, p); };
    const MESA = 0.9, FONDO = 0.7;
    salas.forEach((s) => {
      // se apoyan contra el muro exterior de la crujía; el frente mira al centro del laboratorio
      const vMuro = s.fila === 0 ? s.v1 : s.v0, dir = s.fila === 0 ? 1 : -1, zMuro = -vMuro;
      const zFila = zMuro + dir * (0.05 + FONDO / 2);
      let xr = s.x1 - 0.1;
      s.piso.forEach((it) => {
        const [o, h] = pieza[it.tipo](it.w); o.position.set(xr - it.w / 2, Y, zMuro + dir * 0.45); if (dir < 0) o.rotation.y = Math.PI;
        o.traverse((m) => { if (m.isMesh) m.castShadow = true; }); g.add(o); xr -= it.w + 0.1;
        if (it.e) etiquetaEq(it.e, xr + it.w / 2 + 0.1, Y + h + 0.6, zMuro + dir * 0.45);
      });
      const L = xr - (s.x0 + 0.1);
      if (!s.mesa.length || L < 0.6) return;
      // mesón: mueble bajo y tope de resina; si no cabe todo en uno, un segundo mesón contra el muro de enfrente
      const cupo = (largo) => { let a = 0, k = 0; while (k < s.mesa.length && a + s.mesa[k].w + 0.15 <= largo) a += s.mesa[k++].w + 0.15; return k; };
      const n1 = Math.max(1, cupo(L)), tramos = [[s.mesa.slice(0, n1), zFila, dir, s.x0 + 0.1, xr]];
      if (n1 < s.mesa.length && s.v1 - s.v0 > 2.4) tramos.push([s.mesa.slice(n1), -(s.fila === 0 ? s.v0 : s.v1) - dir * (0.05 + FONDO / 2), -dir, s.x0 + 0.1, s.x1 - 0.1]);
      tramos.forEach(([items, zc, dd, xa, xb]) => {
        g.add(box(xb - xa, MESA - 0.05, FONDO - 0.04, M.meson, (xa + xb) / 2, Y, zc), box(xb - xa + 0.02, 0.05, FONDO + 0.02, M.tope, (xa + xb) / 2, Y + MESA - 0.05, zc));
        const usado = items.reduce((a, it) => a + it.w, 0), gap = Math.max(0.12, (xb - xa - usado) / (items.length + 1));
        let x = xa + gap;
        items.forEach((it) => {
          const [o, h] = pieza[it.tipo](it.w); o.position.set(x + it.w / 2, Y + MESA, zc); if (dd < 0) o.rotation.y = Math.PI;
          o.traverse((m) => { if (m.isMesh) m.castShadow = true; }); g.add(o);
          if (it.tipo === 'microscopio' || it.tipo === 'monitor') silla(x + it.w / 2, zc + dd * (FONDO / 2 + 0.35));
          if (it.e) etiquetaEq(it.e, x + it.w / 2, Y + MESA + h + 0.55, zc);
          x += it.w + gap;
        });
      });
    });
    // nombre de cada sala, sobre su piso
    salas.forEach((s) => {
      const l = st.label(esc(corto(s.n.split(/[,(]/)[0].replace(/\s+y\s+.*$/, '').replace(/^Lavado.*$/i, 'Lavado y autoclave'), 34)), 'lbl-room', [(s.x0 + s.x1) / 2, Y + 0.25, -(s.v0 + s.v1) / 2], g);
      l.visible = false; l.userData.fila = s.fila; labLab.push(l);
    });
    function etiquetaEq(e, x, y, zz) {
      if ((e.precio || 0) < 30e6) return;
      const l = st.label(`<b>${esc(corto(e.nombre.split('(')[0].replace(/\s+(con|por)\s.*$/, ''), 40))}</b>${e.capacidad ? `<br><small>${esc(corto(String(e.capacidad).split(';')[0], 44))}</small>` : ''}`, 'lbl-node', [x, y, zz], g);
      l.visible = false; labLab.push(l);
    }
  }

  // ---------------------------------------------------------------- fichas
  const q = (s) => root.querySelector(`[data-slot="torre.${s}"]`);
  // la ficha de siempre escribe en su propio contenedor: torre.ficha.modo es de los modos nuevos (10.3)
  const ficha = q('ficha.base'), nota0 = ficha.innerHTML;
  function fichaPiso(p) {
    selPiso = +p.piso; etiquetas();
    const amb = (D?.programa?.ambientes || []).filter((a) => String(a.piso) === String(p.piso));
    ficha.innerHTML = `<h4>Piso ${p.piso} · ${fmtN(p.m2_construido, 0)} m² construidos</h4>
      <p class="note">${esc(p.servicios)}</p>
      <details class="fold"><summary>Por qué va aquí</summary><p class="note">${esc(p.por_que)}</p></details>
      <div class="tbl-wrap"><table><thead><tr><th>Ambiente</th><th class="n">Cant.</th><th class="n">m²</th></tr></thead><tbody>
      ${amb.map((a) => `<tr><td><span class="dot" style="background:${grupo(a.servicio)[1]}"></span>${esc(a.nombre)}</td><td class="n">${fmtN(a.cantidad)}</td><td class="n">${fmtN(a.m2_total, 1)}</td></tr>`).join('')}
      </tbody></table></div>`;
    if (gsap) gsap.from(ficha, { opacity: 0, y: 8, duration: 0.3 });
  }

  const modeBtns = root.querySelectorAll('[data-modo-torre]');
  modeBtns.forEach((b) => b.addEventListener('click', () => cambiarModo(b.dataset.modoTorre)));

  // ---------------------------------------------------------------- modos nuevos (6.8, 8.6 y 10.3)
  const capas = q('capas'), fichaModo = q('ficha.modo'), tarjetaSismo = q('sismo'), pistaEl = el.querySelector('.stage-hint'), pista0 = pistaEl?.textContent;
  const PISTAS = {
    recorrido: 'W A S D o flechas para caminar · arrastra para mirar · R y F cambian de piso · Esc para salir',
    sismo: 'Elige un sismo en el panel y calcula · el deslizador recorre los pasos calculados · toca un elemento para ver sus esfuerzos',
    relleno: 'Arrastra para girar · este modo está en construcción',
    cargando: 'Cargando el modo…',
  };
  const pista = () => { if (pistaEl) pistaEl.textContent = !nuevo() ? pista0 : !modulos[modo] ? PISTAS.cargando : modulos[modo].RELLENO ? PISTAS.relleno : PISTAS[modo]; };
  // una tarjeta de la carpeta se ve solo si alguno de sus contenedores está a la vista (los modos muestran u ocultan los suyos)
  const vigilar = (card) => {
    if (!card) return;
    const f = () => { const v = [...card.children].every((c) => c.hidden); if (card.hidden !== v) card.hidden = v; };
    new MutationObserver(f).observe(card, { subtree: true, attributes: true, attributeFilter: ['hidden'] });
    f();
  };
  vigilar(q('panel')); vigilar(q('ficha'));
  // datos de los modos nuevos: se piden al entrar; si el archivo todavía no se publicó, el modo recibe null
  const pedidos = {};
  const pedir = (f) => fetch(new URL(`../../data/${f}`, import.meta.url)).then((r) => { if (!r.ok) throw new Error(f); return r.json(); });
  // build_data.py parte por tamaño los archivos que pasan su límite (10.1: planta por nivel, inventario por nivel y matriz por
  // grupos de servicios): el principal trae «partes» {archivos}; cada parte trae trozos de listas (se concatenan en orden) y de
  // diccionarios (se suman). Se juntan aquí, así cada modo recibe el mismo esquema que con un solo archivo; si falta una parte,
  // el modo recibe null como si el archivo no se hubiera publicado.
  async function juntarPartes(o) {
    if (!o?.partes?.archivos) return o;
    const { partes, ...todo } = o;
    for (const t of await Promise.all(partes.archivos.map(pedir))) {
      for (const [k, v] of Object.entries(t)) {
        if (Array.isArray(v)) todo[k] = (todo[k] || []).concat(v);
        else if (v && typeof v === 'object') todo[k] = Object.assign(todo[k] || {}, v);
        else todo[k] = v;
      }
    }
    return todo;
  }
  const leer = (f) => (pedidos[f] ??= pedir(f).then(juntarPartes).catch(() => null));
  const urlDatos = (f) => new URL(`../../data/${f}`, import.meta.url).href;
  // colores del contraste para la capa del recorrido: E los calcula por recinto y C los recibe ya como THREE.Color (9.2)
  async function coloresContraste(plantas) {
    const mod = await MODULOS.contraste();
    if (mod.RELLENO || !plantas) return null;
    const c = await leer('torre_contraste.json');
    if (!c) return null;
    return new Map([...mod.coloresRecintos(c, plantas)].map(([id, v]) => [id, new THREE.Color(v.color_hex)]));
  }
  async function datosModo(m) {
    if (m === 'recorrido') {
      const [plantas, inventario, habilitacion] = await Promise.all(['torre_plantas.json', 'torre_inventario.json', 'torre_habilitacion.json'].map(leer));
      return { plantas, inventario, habilitacion, coloresContraste: await coloresContraste(plantas) };
    }
    // el simulador pasa al trabajador las URL absolutas (7.5); la amenaza y el inventario los usa la vista (8.2 y 8.3)
    const [amenaza, inventario] = await Promise.all(['sismo_amenaza.json', 'torre_inventario.json'].map(leer));
    return { amenaza, inventario, urls: { estructura: urlDatos('sismo_torre_estructura.json'), amenaza: urlDatos('sismo_amenaza.json') } };
  }
  // contexto de cada modo (6.2 y 8.6): solo sus contenedores; el exterior se oculta entero en el recorrido y en parte en el
  // simulador (el edificio del GLB; quedan el hospital, el terreno y los árboles)
  function ctxModo(m, datos) {
    const ctx = {
      st, raiz: root, hud: q(`hud.${m}`), panel: q(`panel.${m}`), ficha: fichaModo, datos, textos: TEXTOS,
      exterior: { ocultar(on) { const v = on ? (m === 'sismo' ? 'parcial' : 'total') : null; if (v === exterior) return; exterior = v; aplicar(false); } },
      alSalir: () => { if (activo?.nombre === m) { activo = null; vaciarFichaModo(); cambiarModo('torre'); } },
    };
    // el simulador crea su trabajador (o el respaldo de web/js/sismo/motor.js) desde sismo.js (7.5): ctx.motor se agrega allí
    if (m === 'sismo') ctx.graficas = q('sismo.graficas');
    return ctx;
  }
  // monta cada modo una sola vez por vista; dos pedidos seguidos comparten la misma carga
  function montarModo(m) {
    if (instancias[m]) return Promise.resolve(instancias[m]);
    return (cargando[m] ??= (async () => {
      const mod = await MODULOS[m]();
      modulos[m] = mod;
      const obj = await mod.montar(ctxModo(m, mod.RELLENO ? {} : await datosModo(m)));
      instancias[m] = obj;
      return obj;
    })().catch((e) => { console.error(`torre: no se pudo montar el modo «${m}»`, e); cargando[m] = null; return null; }));
  }
  const vaciarFichaModo = () => { fichaModo.innerHTML = ''; fichaModo.hidden = true; };
  // Cambio de modo. El modo que sale deja sus contenedores vacíos; uno pedido mientras otro carga gana (turno), así un
  // cambio en medio de una carga, un cálculo o un vuelo de cámara no deja contenidos ni cámaras cruzados (13.4)
  async function cambiarModo(m, op) {
    if (![...modeBtns].some((b) => b.dataset.modoTorre === m)) return;
    const mio = ++turno;
    clearTimeout(tEncuadre);
    if (activo && activo.nombre === m) { if (op) activo.obj.irA?.(op); return; }
    if (activo) { const a = activo; activo = null; a.obj.salir({ porUsuario: false }); vaciarFichaModo(); }
    const venia = nuevo();
    modo = m;
    modeBtns.forEach((x) => x.setAttribute('aria-pressed', String(x.dataset.modoTorre === m)));
    if (nuevo()) {
      // paso 1 del 6.8: sin vuelos ni encuadres pendientes y sin selección del Stage (el Raycaster no mira visible)
      st.stopFlight();
      if (!guardados) { guardados = st.pickables.splice(0); st.hovered = null; }
      ficha.hidden = true;
      if (tarjetaSismo) tarjetaSismo.hidden = m !== 'sismo';
      aplicar(false);
      pista();
      const obj = await montarModo(m);
      if (mio !== turno) return;
      if (!obj) { cambiarModo('torre'); return; }
      activo = { nombre: m, obj };
      pista();
      if (obj.relleno) encuadre(true);
      obj.entrar(op);
      st.invalidate(true);
      return;
    }
    // modos de siempre: vuelve la selección, la ficha con su nota original y el encuadre de cada uno
    if (guardados) { st.pickables.push(...guardados); guardados = null; }
    exterior = null;   // por si un modo salió sin devolver lo que ocultó
    if (tarjetaSismo) tarjetaSismo.hidden = true;
    if (venia) { ficha.innerHTML = nota0; selPiso = null; }
    ficha.hidden = false;
    pista();
    aplicar(true);
    if (modo === 'laboratorio') {
      const z = zonas.find((zz) => zz.lab && zz.piso === 2);
      // se encuadra la caja del laboratorio con el piso 2 ya separado (sep = 2,2): frameBox se aleja lo necesario según el
      // ancho del recuadro (a 22 m fijos, en el teléfono las etiquetas de los equipos se salían por los dos lados)
      if (z) {
        const i2 = pisos.findIndex((p) => p.piso === 2), y = (pisos[i2]?.nivel ?? 4.5) + 2.2 * 4.5 * i2 + 0.35 + 2.2;
        const caja = new THREE.Box3(new THREE.Vector3(XW[0] - 1, y, -z.y1 - 1), new THREE.Vector3(XW[1] + 1, y + 3, -z.y0 + 1));
        // en el teléfono se mira desde el occidente y casi desde arriba: el lado largo del laboratorio queda a lo alto
        const tel = angosto(), dir = tel ? new THREE.Vector3(-0.4, 0.9, 0.1) : new THREE.Vector3(-0.27, 0.74, 0.61);
        tEncuadre = setTimeout(() => st.frameBox(caja, dir, { margin: tel ? 0.95 : 0.72, ty: 0.3 }), 350);
      }
    } else if (modo === 'pisos') tEncuadre = setTimeout(() => st.frameBox(new THREE.Box3(new THREE.Vector3(XW[0] - 8, 0, -24), new THREE.Vector3(XN[1] + 6, 32, 21)), new THREE.Vector3(-0.8, 0.45, 0.55), { margin: 0.85 }), 200);
    else encuadre();
  }
  // Engine.attach vuelve a activar los controles cada vez que la vista arranca (core.js): el modo en curso repite su ajuste
  // (6.8, paso 4). alDetener es opcional: el recorrido vacía allí sus teclas oprimidas (6.4)
  const start0 = st.start.bind(st), stop0 = st.stop.bind(st);
  st.start = () => { start0(); activo?.obj.alReanudar?.(); };
  st.stop = () => { stop0(); activo?.obj.alDetener?.(); };

  // capa «Proyecto tipo» en «Con la torre» (9.2): el modelo lo da E (o el relleno); D lo pone en su sitio con su etiqueta
  let tipoListo = null;
  const armarTipo = () => (tipoListo ??= (async () => {
    const mod = await MODULOS.contraste();
    const c = mod.RELLENO ? null : await leer('torre_contraste.json');
    const g = mod.modeloTipo3D(THREE, c);
    gTipo.add(g);
    const alto = new THREE.Box3().setFromObject(g).max.y || 3, m2 = +D?.programa?.totales?.m2_construido_torre || 0;
    const texto = g.userData.etiqueta || `<b>Área equivalente del puesto tipo DNP 2018</b><br><small>${fmtN(AREA_TIPO, 1)} m², 1 piso${m2 ? ` · la torre es ${fmtN(m2 / AREA_TIPO, 1)} veces` : ''}</small>`;
    lblTipo = st.label(texto, 'lbl-node', [0, alto + 1.2, 0], gTipo);
    st.updateShadows();
  })().catch((e) => { console.error('torre: capa del proyecto tipo', e); tipoListo = null; }));
  const btnTipo = root.querySelector('[data-capa-torre="tipo"]');
  btnTipo?.addEventListener('click', async () => {
    capaTipo = !capaTipo;
    btnTipo.setAttribute('aria-pressed', String(capaTipo));
    if (capaTipo) await armarTipo();
    aplicar(false);
    if (modo === 'torre') encuadre();
  });

  // tarjetas de abajo (habilitación de C y contraste de E): se cargan al acercarse a la pantalla
  const verEn3D = (destino) => { cambiarModo('recorrido', destino); el.scrollIntoView({ behavior: gsap ? 'smooth' : 'auto', block: 'center' }); };
  function tarjetasPerezosas() {
    const abrir = new Map([
      [q('habilitacion'), async (slot) => {
        const mod = await MODULOS.habilitacion();
        const [hab, inv] = mod.RELLENO ? [null, null] : await Promise.all([leer('torre_habilitacion.json'), leer('torre_inventario.json')]);
        mod.pintarHabilitacion(slot, hab, inv, { verEn3D, textos: TEXTOS });
      }],
      [q('tipo'), async (slot) => {
        const mod = await MODULOS.contraste();
        const c = mod.RELLENO ? null : await leer('torre_contraste.json');
        if (c || mod.RELLENO) mod.pintarContraste(slot, c, { verEn3D, textos: TEXTOS });
      }],
    ].filter(([slot]) => slot));
    const io = new IntersectionObserver((es) => es.forEach((e) => {
      if (!e.isIntersecting) return;
      io.unobserve(e.target);
      abrir.get(e.target)?.(e.target).catch((err) => console.error('torre: tarjeta', err));
    }), { rootMargin: '300px 0px' });
    abrir.forEach((f, slot) => io.observe(slot));
  }

  fetch(new URL('../../data/torre.json', import.meta.url)).then((r) => (r.ok ? r.json() : null)).then((d) => {
    if (!d) return;
    D = d;
    if (d.programa) armarPisos(d.programa);
    pintarFichas(d);
    tarjetasPerezosas();
  }).catch((e) => console.warn('torre.json', e));

  function pintarFichas(d) {
    const pr = d.programa || {}, tot = pr.totales || {}, dot = d.dotacion?.totales_generales || {}, pres = d.presupuesto || {};
    const cap = (pr.capacidad_resultante?.tabla || []);
    const camas = cap.find((c) => /cama/i.test(c.recurso) && !/observ/i.test(c.recurso));
    const consult = cap.find((c) => /consultorios de consulta/i.test(c.recurso));
    const total = pres.totales?.total_torre ?? pres.totales?.total_cop_2026 ?? pres.total_cop_2026;
    q('tiles').innerHTML = `<div class="tile"><b>${fmtN(tot.m2_construido_torre || 0, 0)}</b><span>m² construidos en ${(pr.resumen_por_piso || []).length} pisos</span></div>
      <div class="tile"><b>${camas ? esc(camas.torre) : '—'}</b><span>camas${consult ? ` · ${esc(consult.torre)} consultorios` : ''}</span></div>
      <div class="tile"><b>${cop(dot.total_general_sin_posible_doble_conteo_cop_2026 ?? dot.total_general_cop_2026)}</b><span>dotación y equipamiento, sin repetir lo que ya va en la obra</span></div>
      <div class="tile"><b>${total ? cop(total) : 'en cálculo'}</b><span>costo total del proyecto</span></div>`;
    // programa por piso
    q('pisos').innerHTML = `<p class="note">${esc(pr.resumen || '')}</p><table><thead><tr><th>Piso y servicios</th><th class="n">m² útiles</th><th class="n">m² construidos</th></tr></thead><tbody>
      ${(pr.resumen_por_piso || []).map((p) => `<tr><td><b>Piso ${p.piso}</b><br>${esc(p.servicios)}</td><td class="n">${fmtN(p.m2_util, 0)}</td><td class="n">${fmtN(p.m2_construido, 0)}</td></tr>`).join('')}
      <tr><td><b>Total torre</b></td><td class="n">${fmtN(tot.m2_util_torre || 0, 0)}</td><td class="n"><b>${fmtN(tot.m2_construido_torre || 0, 0)}</b></td></tr></tbody></table>
      ${cap.length ? `<h4 style="margin-top:12px">Capacidad hoy y con la torre</h4><table><thead><tr><th>Recurso</th><th class="n">Hoy</th><th class="n">Torre</th></tr></thead><tbody>${cap.map((c) => `<tr><td>${esc(c.recurso)}</td><td class="n">${esc(c.actual)}</td><td class="n">${esc(c.torre)}</td></tr>`).join('')}</tbody></table>` : ''}
      <p class="note">${esc(pr.uso_del_edificio_actual?.resumen || (typeof pr.uso_del_edificio_actual === 'string' ? pr.uso_del_edificio_actual : ''))}</p>`;
    // norma
    const no = d.normas || {}, ch = no.checklist_485 || [];
    const estados = ch.reduce((a, c) => ((a[c.estado || 'pendiente'] = (a[c.estado || 'pendiente'] || 0) + 1), a), {});
    q('norma').innerHTML = `<p class="note">${esc(no.proyecto_en_breve?.tipologia_res_485 || '')}</p>
      <p>${Object.entries(estados).map(([k, v]) => `<span class="pill">${esc(k)}: ${v}</span>`).join(' ')} de ${ch.length} requisitos del concepto técnico de viabilidad.</p>
      <ol class="tight checklist">${ch.map((c) => `<li><b>${esc(c.numeral)}</b> ${esc(c.requisito)}<br><small class="note">${esc(c.documento_a_producir || '')}${c.responsable ? ` · ${esc(c.responsable)}` : ''}</small></li>`).join('')}</ol>
      <details class="fold"><summary>Normas que aplican (${(no.normas || []).length})</summary><ul class="tight">${(no.normas || []).map((n) => `<li>${n.url ? `<a href="${escH(n.url)}" target="_blank" rel="noopener">${esc(n.numero)} de ${n.anio}</a>` : `${esc(n.numero)} de ${n.anio}`}: ${esc(String(n.objeto || '').slice(0, 220))}</li>`).join('')}</ul></details>`;
    // dotación
    const dd = d.dotacion || {};
    q('dotacion').innerHTML = `<p class="note">${esc(dd.resumen || '')}</p>
      <table><thead><tr><th>Servicio</th><th class="n">Ítems</th><th class="n">Total</th></tr></thead><tbody>
      ${(dd.servicios || []).map((s) => `<tr><td><details class="fold"><summary>${esc(s.nombre)}</summary><ul class="tight">${(s.equipos || []).map((e) => `<li>${fmtN(e.cantidad)} × ${esc(e.nombre)}${e.total_cop_2026 ? ` — ${cop(e.total_cop_2026)}` : ''}${e.clase_riesgo ? ` <small class="note">(clase ${esc(e.clase_riesgo)})</small>` : ''}</li>`).join('')}</ul></details>${s.piso != null ? `<small class="note">${String(s.piso) === '0' ? 'Toda la torre' : `${/\by\b|,/.test(String(s.piso).replace(/\(.*?\)/g, '')) ? 'Pisos' : 'Piso'} ${esc(s.piso)}`}</small>` : ''}</td><td class="n">${fmtN(s.totales?.numero_de_items ?? (s.equipos || []).length)}</td><td class="n">${cop(s.totales?.total_cop_2026)}</td></tr>`).join('')}
      <tr><td>Equipamiento fijo e industrial (planta, ascensores, gases, aire, autoclave…)</td><td class="n">${(dd.equipamiento_fijo || []).length}</td><td class="n">${cop(dot.equipamiento_fijo_e_industrial_cop_2026)}</td></tr>
      <tr><td><b>Total dotación, mobiliario y equipamiento</b>${dot.total_general_sin_posible_doble_conteo_cop_2026 ? `<br><small class="note">incluye ${cop(dot.total_general_cop_2026 - dot.total_general_sin_posible_doble_conteo_cop_2026)} de equipos que pueden estar ya en la obra</small>` : ''}</td><td></td><td class="n"><b>${cop(dot.total_general_cop_2026)}</b></td></tr></tbody></table>
      ${dot.rango_total_general_cop_2026 ? `<p class="note">Rango: ${cop(dot.rango_total_general_cop_2026[0])} a ${cop(dot.rango_total_general_cop_2026[1])}. Sin posibles dobles conteos con la obra: ${cop(dot.total_general_sin_posible_doble_conteo_cop_2026)}.</p>` : ''}`;
    // laboratorio
    const la = d.laboratorio || {}, tm = la.totales_menu || {};
    const tr = (t) => (t ? ['urgencias', 'rutina', 'tamizaje'].map((k) => (t[k] ? `<small><b>${k}</b> ${esc(t[k])}</small>` : '')).filter(Boolean).join('<br>') : '');
    q('laboratorio').innerHTML = `<p class="note">${esc(la.resumen || '')}</p>
      <div class="tiles"><div class="tile"><b>${fmtN(tm.pruebas_en_sitio_mes || 0)}</b><span>pruebas al mes en sitio</span></div><div class="tile"><b>${(la.menu || []).length}</b><span>pruebas en el menú, con tiempos de respuesta</span></div></div>
      <details class="fold"><summary>Menú de pruebas y tiempos de respuesta (${(la.menu || []).length})</summary><div class="tbl-wrap"><table><thead><tr><th>Prueba</th><th>Tiempo de respuesta</th><th class="n">Al mes</th></tr></thead><tbody>
      ${(la.menu || []).map((m) => `<tr><td>${esc(m.prueba)}<br><small class="note">${esc(m.seccion)} · ${esc(m.equipo)}</small></td><td>${tr(m.tiempo_respuesta)}</td><td class="n">${fmtN(m.volumen_mes || 0)}</td></tr>`).join('')}
      </tbody></table></div></details>
      <details class="fold"><summary>Equipos del laboratorio (${(la.equipos || []).length})</summary><ul class="tight">${(la.equipos || []).map((e) => `<li>${fmtN(e.cantidad)} × ${esc(e.nombre)}${e.capacidad ? ` — ${esc(e.capacidad)}` : ''}${e.uso_pico_pct != null ? ` <small class="note">(uso en hora pico ${fmtN(e.uso_pico_pct, 0)} %)</small>` : ''}${e.modelo_de_compra ? ` <small class="note">· ${esc(e.modelo_de_compra)}</small>` : ''}</li>`).join('')}</ul></details>`;
    // proyecto tipo
    const pt = d.proyecto_tipo || {};
    q('tipo').innerHTML = `<p>${esc(pt.respuesta_corta || '')}</p>
      ${pt.seleccion?.por_que ? `<ul class="tight">${pt.seleccion.por_que.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}
      ${pt.estetica?.propuesta ? `<p class="note"><b>Estética:</b> ${esc(pt.estetica.propuesta)}</p>` : ''}
      <details class="fold"><summary>Proyectos tipo revisados (${(pt.proyectos_tipo || []).length})</summary><ul class="tight">${(pt.proyectos_tipo || []).map((p) => `<li>${p.url ? `<a href="${escH(p.url)}" target="_blank" rel="noopener">${esc(p.nombre)}</a>` : esc(p.nombre)} <small class="note">${esc(p.fecha || '')}</small></li>`).join('')}</ul></details>`;
    pintarPresupuesto(d);
    // leyenda de grupos de servicio
    q('leyenda').innerHTML = GRUPOS.map(([, c, n]) => `<span><i style="background:${c}"></i>${n}</span>`).join('');
  }

  // presupuesto, APU, financiación y proyectos (si ya están calculados)
  function pintarPresupuesto(d) {
    const pres = d.presupuesto, apu = d.apu, fin = d.financiacion, pro = d.proyectos;
    const pend = '<p class="note">En cálculo: el presupuesto, los APU, la financiación y los proyectos se publican cuando terminen de verificarse.</p>';
    q('presupuesto').innerHTML = pres ? renderPresupuesto(pres) : pend;
    q('apu').innerHTML = apu ? renderAPU(apu) : pend;
    q('financiacion').innerHTML = fin ? renderFinanciacion(fin) : pend;
    q('proyectos').innerHTML = pro ? renderProyectos(pro) : pend;
    const sel = q('apu').querySelector('select');
    if (sel) sel.addEventListener('change', () => { q('apu').querySelector('[data-apu]').innerHTML = detalleAPU(apu.apus[+sel.value]); });
  }
  const num = (o, ...k) => { for (const x of k) if (o?.[x] != null && !Number.isNaN(+o[x])) return +o[x]; return null; };
  const nom = (o) => o?.nombre || o?.capitulo || o?.item || o?.descripcion || o?.insumo || o?.cuadrilla || '';
  const ETQ = { costo_directo_obra: 'Costo directo de la obra', valor_obra_con_aiu: 'Obra con AIU', indirectos_y_otros_componentes: 'Estudios, interventoría, dotación, laboratorio, TIC y contingencias', total_torre: 'Total de la torre', total_con_proyectos_complementarios: 'Con la adecuación del edificio actual y la ambulancia' };
  function renderPresupuesto(p) {
    const caps = p.capitulos || [], tots = caps.map((c) => num(c, 'subtotal_con_aiu', 'subtotal_costo_directo', 'total') ?? 0), max = Math.max(1, ...tots);
    const t = p.totales || {}, m2 = p.costo_m2 || {}, ig = p.indirectos_por_grupo || {};
    return `${p.resumen ? `<p class="note">${esc(p.resumen)}</p>` : ''}
      <p class="note">Capítulos con AIU; los ítems van a costo directo (cantidad × valor unitario) y cada uno dice de dónde sale su cantidad y su precio.</p>
      <div class="barras">${caps.map((c, i) => `<details class="fold"><summary><span class="bar-l">${esc(c.codigo ? `${c.codigo}. ` : '')}${esc(nom(c))}${c.peso_pct != null ? ` <small class="note">(${fmtN(c.peso_pct, 1)} %)</small>` : ''}</span><span class="bar"><i style="width:${(100 * tots[i]) / max}%"></i></span><span class="bar-v">${cop(tots[i])}</span></summary>
      ${c.nota ? `<p class="note">${esc(c.nota)}</p>` : ''}
      <div class="tbl-wrap"><table class="fichas"><thead><tr><th>Ítem</th><th>Und.</th><th class="n">Cantidad</th><th class="n">Valor unitario</th><th class="n">Total (costo directo)</th></tr></thead><tbody>
      ${(c.items || []).map((it) => `<tr><td>${esc(it.codigo ? `${it.codigo} ` : '')}${esc(nom(it))}${it.supuesto_cantidad ? `<br><small class="note">${esc(it.supuesto_cantidad)}</small>` : ''}</td><td class="sin-ficha">${esc(it.unidad || '')}</td><td class="n" data-th="Cantidad${it.unidad ? ` (${esc(it.unidad)})` : ''}">${fmtN(num(it, 'cantidad') ?? 0, 2)}</td><td class="n" data-th="Valor unitario">${cop(num(it, 'valor_unitario_costo_directo', 'valor_unitario', 'precio_unitario'))}</td><td class="n" data-th="Total">${cop(num(it, 'total_costo_directo', 'total', 'valor_total'))}</td></tr>`).join('')}
      </tbody></table></div></details>`).join('')}</div>
      ${Object.keys(ig).length ? `<h4>Otros componentes del proyecto</h4><dl class="kv">${Object.entries(ig).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${cop(v)}</dd>`).join('')}</dl>` : ''}
      <dl class="kv" style="margin-top:10px">${Object.entries(ETQ).filter(([k]) => t[k] != null).map(([k, n]) => `<dt>${k === 'total_torre' ? `<b>${n}</b>` : n}</dt><dd>${k === 'total_torre' ? `<b>${cop(t[k])}</b>` : cop(t[k])}</dd>`).join('')}
        ${t.rango_total_torre ? `<dt>Rango del total</dt><dd>${cop(t.rango_total_torre[0])}<br>a ${cop(t.rango_total_torre[1])}</dd>` : ''}
        ${m2.costo_total_por_m2_construido_total ? `<dt>Costo total por m² construido (${fmtN(m2.area_construida_total_m2, 1)} m²${m2.area_construida_torre_m2 ? `: la torre con el bloque técnico, el cuarto de residuos y las casetas de cubierta` : ''})</dt><dd>$${fmtN(m2.costo_total_por_m2_construido_total, 0)}</dd><dt>Obra con AIU por m² construido</dt><dd>$${fmtN(m2.valor_obra_por_m2_construido_total, 0)}</dd>${m2.obra_civil_sin_equipamiento_fijo_ni_solar_por_m2_total ? `<dt>Obra civil y redes por m² (sin equipos fijos ni solar)</dt><dd>$${fmtN(m2.obra_civil_sin_equipamiento_fijo_ni_solar_por_m2_total, 0)}</dd>` : ''}` : ''}</dl>
      ${m2.nota ? `<p class="note">${esc(m2.nota.replace(/'obra_civil[^']*'/, '«Obra civil y redes por m²»'))}</p>` : ''}
      ${(p.comparacion || []).length ? `<details class="fold"><summary>Comparación con proyectos hospitalarios contratados o viabilizados (${p.comparacion.length})</summary><div class="tbl-wrap"><table class="fichas"><thead><tr><th>Proyecto</th><th class="n">m²</th><th class="n">Valor por m² (2026)</th><th>Frente a la torre</th></tr></thead><tbody>${p.comparacion.map((x) => { const u = String(x.fuente || x.url || '').match(/https?:\/\/\S+/)?.[0]; return `<tr><td>${esc(x.proyecto || x.referencia || x.nombre || '')}<br><small class="note">${esc(x.incluye || '')}${u ? ` · <a href="${escH(u)}" target="_blank" rel="noopener">fuente</a>` : ''}</small></td><td class="n" data-th="m²">${x.area_m2 ? fmtN(x.area_m2, 0) : '—'}</td><td class="n" data-th="Valor por m² (2026)">${x.costo_m2_cop_2026 ? `$${fmtN(x.costo_m2_cop_2026, 0)}` : '—'}</td><td class="ancho" data-th="Frente a la torre"><small>${esc(x.relacion_con_la_torre || '')}</small></td></tr>`; }).join('')}</tbody></table></div></details>` : ''}`;
  }
  function renderAPU(a) {
    const L = a.apus || [];
    if (!L.length) return '';
    return `${a.resumen ? `<p class="note">${esc(a.resumen)}</p>` : ''}<label class="apu-sel">Ítem <select>${L.map((x, i) => `<option value="${i}">${esc(x.id || '')} · ${esc(nom(x))} (${esc(x.unidad || '')})</option>`).join('')}</select></label><div data-apu>${detalleAPU(L[0])}</div>`;
  }
  function detalleAPU(x) {
    // cada columna: [encabezado, celda, es cifra, rótulo en el teléfono (texto o función de la fila; null = la celda se oculta)]
    const tabla = (titulo, filas, cols) => (filas?.length ? `<h4>${titulo}</h4><div class="tbl-wrap"><table class="fichas"><thead><tr>${cols.map((c) => `<th${c[2] ? ' class="n"' : ''}>${c[0]}</th>`).join('')}</tr></thead><tbody>${filas.map((r) => `<tr>${cols.map((c, j) => {
      const th = c.length > 3 ? (typeof c[3] === 'function' ? c[3](r) : c[3]) : c[0], cls = [c[2] ? 'n' : '', th === null ? 'sin-ficha' : ''].filter(Boolean).join(' ');
      return `<td${cls ? ` class="${cls}"` : ''}${j && th ? ` data-th="${escH(th)}"` : ''}>${c[1](r)}</td>`;
    }).join('')}</tr>`).join('')}</tbody></table></div>` : '');
    const ai = x.aiu || {};
    return `<p class="note">${esc(x.descripcion || '')}</p>
      ${tabla('Materiales', x.materiales, [['Insumo', (r) => esc(r.insumo || nom(r))], ['Und.', (r) => esc(r.unidad || ''), 0, null], ['Cant.', (r) => fmtN(r.cantidad ?? 0, 3), 1, (r) => `Cant.${r.unidad ? ` (${limpio(r.unidad)})` : ''}`], ['Desp. %', (r) => fmtN(r.desperdicio_pct ?? 0, 0), 1], ['Precio', (r) => cop(r.precio_unitario), 1], ['Valor', (r) => cop(r.valor), 1]])}
      ${tabla('Equipo', x.equipo, [['Equipo', (r) => esc(r.descripcion || nom(r))], ['Tarifa', (r) => `${cop(r.tarifa)}/${esc(r.unidad_tarifa || '')}`, 1], ['Cant.', (r) => fmtN(r.cantidad ?? 0, 3), 1], ['Valor', (r) => cop(r.valor), 1]])}
      ${tabla('Mano de obra', x.mano_obra || x.mano_de_obra, [['Cuadrilla', (r) => `${esc(r.cuadrilla || '')}<br><small class="note">${esc(r.composicion || '')}</small>`], ['Jornal con prestaciones', (r) => cop(r.jornal_con_prestaciones), 1], ['Rendimiento/día', (r) => fmtN(r.rendimiento_unidades_por_dia ?? 0, 1), 1], ['Valor', (r) => cop(r.valor), 1]])}
      <dl class="kv" style="margin-top:8px">
        ${x.herramienta_menor?.valor != null ? `<dt>Herramienta menor (${fmtN(x.herramienta_menor.porcentaje_de_mano_de_obra || 0, 0)} % de la mano de obra)</dt><dd>${cop(x.herramienta_menor.valor)}</dd>` : ''}
        ${x.transporte?.valor != null ? `<dt>Transporte</dt><dd>${cop(x.transporte.valor)}</dd>` : ''}
        <dt><b>Costo directo</b></dt><dd><b>${cop(x.costo_directo)}</b></dd>
        ${ai.administracion != null ? `<dt>Administración (${fmtN(ai.administracion_pct, 0)} %) · imprevistos (${fmtN(ai.imprevistos_pct, 0)} %) · utilidad (${fmtN(ai.utilidad_pct, 0)} %) · IVA sobre utilidad</dt><dd>${cop((ai.administracion || 0) + (ai.imprevistos || 0) + (ai.utilidad || 0) + (ai.iva_sobre_utilidad || 0))}</dd>` : ''}
        <dt><b>Precio unitario con AIU</b></dt><dd><b>${cop(x.precio_unitario_con_aiu)}</b> / ${esc(x.unidad || '')}</dd></dl>
      ${x.comparacion?.lectura ? `<p class="note"><b>Contraste:</b> ${esc(x.comparacion.lectura)}</p>` : ''}${x.uso_en_presupuesto ? `<p class="note"><b>Uso:</b> ${esc(x.uso_en_presupuesto)}</p>` : ''}`;
  }
  const CORTO_F = { sgr_ad: 'SGR directas de Yondó', sgr_ipaz: 'SGR incentivo OCAD Paz', sgr_ail: 'SGR inversión local', sgr_air: 'SGR inversión regional', sgr_ctei: 'SGR ciencia y tecnología', pgn_minsalud: 'MinSalud (PGN)', gobernacion: 'Gobernación de Antioquia', oxi: 'Obras por Impuestos', fenoge: 'FENOGE', mintic: 'MinTIC', municipio: 'Municipio', ese: 'E.S.E.', credito: 'Crédito Findeter', ecopetrol: 'Ecopetrol', cooperacion: 'Cooperación' };
  function renderFinanciacion(f) {
    const L = f.fuentes || [], totM = Object.values(f.mezcla_escenario_base || {}).reduce((a, v) => a + (+v || 0), 0) || 1;
    const nombre = (id) => CORTO_F[id] || (L.find((x) => x.id === id)?.nombre || id).split(/[–(]/)[0].trim();
    // las siete fuentes más grandes con color propio; el resto se agrupa en gris para que la barra se pueda leer
    const orden = Object.entries(f.mezcla_escenario_base || {}).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
    const cols = ['var(--s1)', 'var(--s2)', 'var(--s3)', 'var(--s4)', 'var(--s5)', 'var(--s6)', 'var(--s7)'];
    const resto = orden.slice(cols.length), seg = orden.slice(0, cols.length).map(([k, v], i) => [nombre(k), v, cols[i]]);
    if (resto.length) seg.push([`Otras ${resto.length}: ${resto.map(([k]) => nombre(k)).join(', ')}`, resto.reduce((a, [, v]) => a + v, 0), 'var(--muted)']);
    return `${f.resumen ? `<p class="note">${esc(f.resumen)}</p>` : ''}
      <div class="mezcla">${seg.map(([n, v, c]) => `<i title="${esc(n)}: ${cop(v)}" style="flex:${v};background:${c}"></i>`).join('')}</div>
      <ul class="tight mezcla-ley">${seg.map(([n, v, c]) => `<li><span class="dot" style="background:${c}"></span>${esc(n)}: <b>${cop(v)}</b> (${fmtN((100 * v) / totM, 0)} %)</li>`).join('')}</ul>
      ${f.escenario_probable_docs06 ? `<p class="note"><b>Con los montos más probables</b> (MinSalud ${cop(f.escenario_probable_docs06.montos?.pgn_minsalud)}, Obras por Impuestos ${cop(f.escenario_probable_docs06.montos?.oxi)}, sin crédito) se reúnen ${cop(f.escenario_probable_docs06.suma)}: faltan <b>${cop(f.escenario_probable_docs06.brecha_frente_a_la_torre)}</b>.</p>` : ''}
      ${matriz(f.matriz_escenario_base_por_proyecto, nombre)}
      <div class="tbl-wrap"><table><thead><tr><th>Fuente</th><th class="n">Escenario base</th></tr></thead><tbody>${L.map((x) => `<tr><td><details class="fold"><summary>${esc(x.nombre)}</summary><p class="note">${esc(x.requisitos || '')}</p>${x.momento ? `<p class="note"><b>Cuándo:</b> ${esc(x.momento)}</p>` : ''}${x.proyectos_que_financia ? `<p class="note"><b>Financia:</b> ${esc([].concat(x.proyectos_que_financia).join(', '))}</p>` : ''}</details>${x.probabilidad ? `<small class="note">Probabilidad: ${esc(String(x.probabilidad).split('(')[0].trim())}</small>` : ''}</td><td class="n">${cop(x.monto_central_escenario_base)}${Array.isArray(x.monto_posible_rango) ? `<br><small class="note" style="white-space:normal">entre ${cop(x.monto_posible_rango[0])} y\u00a0${cop(x.monto_posible_rango[1])}</small>` : ''}</td></tr>`).join('')}</tbody></table></div>
      ${f.escenario_sin_pgn_lectura ? `<p class="note"><b>Sin MinSalud:</b> ${esc(f.escenario_sin_pgn_lectura)}</p>` : ''}`;
  }
  // quién paga cada proyecto en el escenario base (cada fuente se usa una sola vez)
  function matriz(m, nombre) {
    if (!m?.asignacion) return '';
    const P = D?.proyectos?.proyectos || [], nomP = (id) => nom(P.find((x) => x.id === id) || {}) || id;
    const filas = Object.entries(m.asignacion).sort(([a], [b]) => a.localeCompare(b, 'es', { numeric: true }));
    return `<details class="fold"><summary>Quién paga cada proyecto (escenario base)</summary><div class="tbl-wrap"><table><thead><tr><th>Proyecto</th><th>Fuentes</th><th class="n">Total</th></tr></thead><tbody>${filas.map(([id, fu]) => `<tr><td><b>${esc(id)}</b> <small>${esc(corto(nomP(id), 60))}</small></td><td><small>${Object.entries(fu).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${esc(nombre(k))} ${cop(v)}`).join(' · ')}</small></td><td class="n">${cop(m.suma_por_proyecto?.[id] ?? Object.values(fu).reduce((a, v) => a + v, 0))}</td></tr>`).join('')}</tbody></table></div>${m.metodo ? `<p class="note">${esc(m.metodo)}</p>` : ''}</details>`;
  }
  function renderProyectos(p) {
    const L = p.proyectos || [];
    const fecha = (s) => { const m = String(s || '').match(/(20\d\d)(?:-(\d\d))?/); return m ? +m[1] + ((+m[2] || 1) - 1) / 12 : null; };
    const A0 = Math.min(2026, ...L.map((x) => Math.floor(fecha(x.inicio) ?? 2026))), A1 = Math.max(2030, ...L.map((x) => Math.floor(fecha(x.fin) ?? 2030))), N = A1 - A0 + 1;
    const anios = Array.from({ length: N }, (_, i) => A0 + i), pct = (t) => ((t - A0) / N) * 100;
    const fuente = (s) => corto(String(s || '').split(';')[0], 120);
    const mga = p.agrupacion_recomendada_fichas_mga;
    return `${p.respuesta_corta ? `<p>${esc(p.respuesta_corta)}</p>` : ''}<div class="gantt"><div class="gantt-head"><span></span><span class="g-bar" style="background-size:${100 / N}% 100%">${anios.map((a) => `<b style="left:${pct(a)}%">${a}</b>`).join('')}</span></div>
      ${L.map((x) => { const a = fecha(x.inicio) ?? A0, b = Math.max(a + 0.08, (fecha(x.fin) ?? a + 0.5) + 1 / 12); return `<details class="fold gantt-row"><summary><span class="g-n"><b>${esc(x.id || x.orden)}</b> ${esc(nom(x))}<br><small class="note">${cop(num(x, 'valor'))} · ${esc(fuente(x.fuente_financiacion))}</small></span><span class="g-bar" style="background-size:${100 / N}% 100%"><i title="${esc(`${x.inicio} a ${x.fin}`)}" style="left:${pct(a)}%;width:${pct(b) - pct(a)}%"></i></span></summary><p class="note">${esc(x.objeto || '')}</p><p class="note">${x.entidad ? `<b>Presenta:</b> ${esc(x.entidad)}<br>` : ''}${x.tipo_concepto_485 ? `<b>Concepto técnico:</b> ${esc(x.tipo_concepto_485)}<br>` : ''}${x.mga ? `<b>MGA:</b> ${esc(typeof x.mga === 'string' ? x.mga : JSON.stringify(x.mga))}<br>` : ''}${(x.dependencias || []).length ? `<b>Requiere:</b> ${esc([].concat(x.dependencias).join('; '))}` : ''}</p></details>`; }).join('')}</div>
      ${mga ? `<p class="note"><b>Fichas MGA (${Array.isArray(mga) ? mga.length : ''}):</b> ${esc(Array.isArray(mga) ? mga.map((g) => [].concat(g).join(' + ')).join(' · ') : typeof mga === 'string' ? mga : String(mga.resumen || '').slice(0, 600))}</p>` : ''}`;
  }

  // ganchos de QA (8.7): solo con «?qa» en la consulta de la URL (index.html?qa=1#torre)
  if (new URLSearchParams(location.search).has('qa')) {
    const sim = () => instancias.sismo, rec = () => instancias.recorrido;
    window.__torreQA = {
      modo: (m, op) => (m === undefined ? modo : cambiarModo(m, op)),
      stats() { st.invalidate(); engine.redraw(st); const r = engine.renderer.info.render; return { llamadas: r.calls, triangulos: r.triangles }; },
      recorrido: {
        irA: async (d) => { if (modo !== 'recorrido') await cambiarModo('recorrido', d); else rec()?.irA(d); },
        estado: () => rec()?.estado?.() ?? null,
        libre: (x, y) => rec()?.libre?.(x, y) ?? null,
      },
      sismo: {
        calcular: async (p) => { if (modo !== 'sismo') await cambiarModo('sismo'); return (await sim()?.calcular?.(p)) ?? null; },
        ultimo: () => sim()?.ultimo?.() ?? null,
        motor: () => sim()?.motor?.() ?? null,
        cubiertaDibujada: (i) => sim()?.cubiertaDibujada?.(i) ?? null,
      },
      // para la QA de integración: qué modos usan el relleno, si llegaron los datos de la vista y qué oculta el exterior
      relleno: (m) => (m in modulos ? !!modulos[m].RELLENO : null),
      listo: () => !!D,
      datos: (f) => leer(f),   // un archivo de web/data tal como lo recibe cada modo (con las partes ya juntas)
      exterior: () => exterior,
    };
  }

  onTheme((t) => { ground.material.color.copy(t.ground); });
  return st;
}
