// Aguas: el acueducto del casco de punta a punta. Pozos y PTAP (40 L/s las 24 horas), impulsión de 12" al tanque elevado
// (350 m³; el depósito grande es el tanque de compensación de 2.135 m³) y bajada por gravedad al pueblo, donde la red solo
// recibe agua 9 horas al día (4:00 a 13:00). La propuesta:
// sectorizar la red con válvulas y macromedidores para pasar a 24 horas, micromedir, bajar pérdidas, telemetría y un
// módulo de ampliación de la PTAP hacia ~60 L/s. El flujo de partículas muestra el agua; en el diagnóstico la red parpadea
// (9 de 24 horas) y con la propuesta queda encendida.
import { THREE, gsap, mat } from '../../core.js';
import { CALLES, RED } from '../../data.js';
import { cinta, aLoLargo, largo, V } from '../geo3d.js';
import { matT } from '../texturas.js';
import { moduloPTAP } from '../piezas/plantas.js';
import { acopio, paralela, caja as bloque, cil, ubicar } from '../piezas/relleno.js';
import { sitios, trazado, caja } from './comun.js';

const SECTORES = [   // sectores hidráulicos de respaldo (los reemplazan los de geo.json)
  { id: 's1', nombre: 'Sector 1 · occidente', poligono: [[-640, -300], [-195, -300], [-195, 640], [-640, 640]] },
  { id: 's2', nombre: 'Sector 2 · centro sur', poligono: [[-195, -460], [330, -460], [330, 60], [-195, 60]] },
  { id: 's3', nombre: 'Sector 3 · centro norte', poligono: [[-195, 60], [330, 60], [330, 470], [-195, 470]] },
  { id: 's4', nombre: 'Sector 4 · oriente', poligono: [[330, -320], [760, -320], [760, 320], [330, 320]] },
  { id: 's5', nombre: 'Sector 5 · nororiente', poligono: [[330, 320], [760, 320], [760, 760], [330, 760]] },
];
const TONOS = ['#2a78d6', '#3fa7e0', '#1f5fb8', '#5cc1d6', '#2e8fc9', '#1d4f9a'];
// franja de servidumbre de la impulsión y la conducción: a cuántos metros del eje de la vía (que sigue el trazado) y ancho;
// ventosas cada VENTOSA m; el tramo que entra al casco (a menos de CASCO m del centro) va por las calles, sin franja
const FRANJA = { lado: 7, ancho: 5 }, VENTOSA = 300, CASCO = 650;
const po = (k) => ({ polygonOffset: true, polygonOffsetFactor: 0, polygonOffsetUnits: -k });
// cámara de válvula y macromedidor a ras del andén: marco de concreto con dos tapas de acero, gabinete azul del medidor
// con su pantalla y un mojón con la placa del sector. Marco local: x a lo largo de la calle
function camara() {
  return {
    concreto: [bloque(2.6, 0.12, 1.8)], acero: [bloque(1.1, 0.03, 1.4, -0.62, 0.12, 0), bloque(1.1, 0.03, 1.4, 0.62, 0.12, 0)],
    azul: [bloque(0.7, 1.3, 0.38, 1.85, 0, 0.55)], oscuro: [bloque(0.36, 0.26, 0.02, 1.85, 0.85, 0.75)],
    blanco: [cil(0.09, 1.1, -1.7, 0, 0.7, 8)], placa: [bloque(0.04, 0.3, 0.45, -1.7, 0.8, 0.7)],
  };
}
// ventosa: caja de concreto con la válvula de aire (tubo azul con tapa) y el mojón de señalización
function ventosa() {
  return { concreto: [bloque(1.2, 0.55, 1.2)], azul: [cil(0.1, 0.55, 0, 0.55, 0, 8), cil(0.2, 0.18, 0, 1.1, 0, 10)], blanco: [cil(0.07, 1.3, 0.9, 0, 0.9, 6)], placa: [bloque(0.03, 0.2, 0.3, 0.93, 1.0, 0.9)] };
}
// corte de dos segmentos (null si no se cortan)
function corte(a, b, c, d) {
  const r = [b[0] - a[0], b[1] - a[1]], q = [d[0] - c[0], d[1] - c[1]], den = r[0] * q[1] - r[1] * q[0];
  if (Math.abs(den) < 1e-9) return null;
  const t = ((c[0] - a[0]) * q[1] - (c[1] - a[1]) * q[0]) / den, u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den;
  return t >= 0 && t <= 1 && u >= 0 && u <= 1 ? [a[0] + t * r[0], a[1] + t * r[1], Math.atan2(r[1], r[0])] : null;
}

export function crear(esc, datos) {
  const color = '--m-aguas';
  const pos = (id, def) => { const it = esc.edificios.get(id); return it ? [it.e.x, it.e.y] : def; };
  const ptap = pos('ptap', [-2265, 300]), tanque = pos('tanque_elevado', [-2356, 518]), capt = pos('captacion', [-2322, 249]);
  const ruta = (de, a) => { const t = RED?.arbol?.tramos?.find((x) => (x.de === de && x.a === a) || (x.de === a && x.a === de)); if (!t) return null; return t.de === de ? t.ruta : [...t.ruta].reverse(); };
  // impulsión PTAP → tanque (directa, indicativa: la ruta de la red del atlas da la vuelta por el casco) y bajada tanque →
  // casco (por la vía, hasta la entrada occidental junto al hospital)
  const imp = trazado(datos, 'aguas', 'impulsion')?.puntos || [ptap, tanque];
  const baja = trazado(datos, 'aguas', 'conduccion')?.puntos || [...(ruta('tanque_elevado', 'ptap') || [tanque, ptap]), ...(ruta('ptap', 'hospital') || [ptap, [-326, -121]]).slice(1)];

  const cSis = esc.capa('aguas.sistema'), cRed = esc.capa('aguas.red'), cSec = esc.capa('aguas.sectores'), cAmp = esc.capa('aguas.ampliacion');
  esc.flujo(imp.map(([x, y]) => [x, y, 3]), { color: '#3a8fe0', potencia: 0.75, max: 26, tam: 2.2, tubo: 0.6, padre: cSis });
  const fBaja = esc.flujo(baja.map(([x, y]) => [x, y, 3]), { color: '#3a8fe0', potencia: 0.9, max: 90, tam: 2.4, tubo: 0.7, padre: cSis });
  // franja de servidumbre en tierra a un lado de la vía, con ventosas cada 300 m y la tubería a la vista sobre pilas donde
  // la franja cruza un caño (en el casco la red va por las calles: ahí no hay franja)
  const Ms = {
    franja: matT('tierra', { color: '#d4c7a6', ...po(4) }), concreto: matT('concreto'), azul: mat(new THREE.Color('#1f5fb8'), { roughness: 0.4, metalness: 0.3 }),
    blanco: mat(new THREE.Color('#eeeeea'), { roughness: 0.5 }), placa: mat(new THREE.Color('#2a78d6'), { roughness: 0.5 }), acero: mat(new THREE.Color('#9aa3a9'), { roughness: 0.35, metalness: 0.7 }),
    oscuro: mat(new THREE.Color('#1d2226'), { roughness: 0.3, metalness: 0.4, emissive: new THREE.Color('#3fd17a'), emissiveIntensity: 0.6 }),
  };
  const As = acopio();
  [imp, baja].forEach((ruta) => {
    const fuera = []; let tramo = [];
    paralela(ruta, FRANJA.lado).forEach((p) => { if (Math.hypot(p[0], p[1]) > CASCO) tramo.push(p); else if (tramo.length) { fuera.push(tramo); tramo = []; } });
    if (tramo.length) fuera.push(tramo);
    fuera.filter((t) => t.length > 1 && largo(t) > 20).forEach((t) => {
      As.put('franja', cinta(t, FRANJA.ancho, 0.05));
      aLoLargo(t, VENTOSA, FRANJA.ancho / 2 - 0.9, VENTOSA / 2).forEach(([x, y, a]) => As.poner(ventosa(), x, y, a));
      for (let i = 1; i < t.length; i++) CALLES.canos.forEach((c) => { for (let j = 1; j < c.p.length; j++) { const k = corte(t[i - 1], t[i], c.p[j - 1], c.p[j]); if (!k) continue;
        const [x, y, a] = k;
        As.put('acero', ubicar(new THREE.CylinderGeometry(0.25, 0.25, 12, 10).rotateZ(Math.PI / 2).translate(0, 1.3, 0), x, y, a));
        [-4.5, 4.5].forEach((d) => As.put('concreto', ubicar(bloque(0.7, 1.05, 0.9, d, 0, 0), x, y, a)));
      } });
    });
  });
  As.volcar(cSis, Ms);
  const lbl = (html, p, h = 30, cls = 'lbl-p') => esc.etiqueta(html, { pos: [p[0], p[1], h], padre: cSis, color: `var(${color})`, cls });
  lbl('<b>Pozos profundos</b><small>captación</small>', capt, 16, 'lbl-p mini');
  lbl('<b>PTAP · 40 L/s</b><small>opera las 24 horas</small>', ptap, 24);
  lbl('<b>Tanque elevado</b><small>350 m³ · impulsión de 12"</small>', tanque, 46);
  const mid = baja[Math.floor(baja.length * 0.55)];
  lbl('<b>Conducción al casco</b><small>por gravedad</small>', mid, 18, 'lbl-p mini');

  // red de distribución del casco (las calles residenciales) para mostrar las horas de servicio
  const calles = CALLES.calles.filter((c) => ['residential', 'tertiary', 'secondary', 'unclassified'].includes(c.tipo) && c.p.some(([x, y]) => Math.hypot(x, y) < 1000));
  const matRed = new THREE.MeshBasicMaterial({ color: new THREE.Color('#3a8fe0'), transparent: true, opacity: 0.85, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -9, polygonOffsetUnits: -9 });
  calles.forEach((c) => cRed.add(new THREE.Mesh(cinta(c.p, 4.5, 0.14), matRed)));
  esc.tenir(matRed, color);
  // parpadeo: encendida 9 de cada 24 «horas» (el ciclo dura 6 s) durante el diagnóstico
  let parpadeo = false, reloj = 0;
  esc.st.onFrame((dt) => {
    if (!parpadeo || !cRed.visible) return false;
    reloj = (reloj + dt / 6) % 1;
    const on = reloj < 9 / 24;
    matRed.opacity = on ? 0.9 : 0.08; fBaja.set(on ? 0.9 : 0.05, 1);
    return true;
  });

  // sectores hidráulicos con su entrada (válvula + macromedidor)
  const sec = sitios(datos, 'aguas', 'sector');
  const lista = sec.length ? sec.map((s) => ({ id: s.id, nombre: s.nombre, poligono: s.poligono })) : SECTORES, rellenos = [];
  lista.forEach((s, i) => {
    // relleno tenue (no lava el pueblo) y borde grueso: el sector se lee por su contorno
    const m = new THREE.Mesh(new THREE.ShapeGeometry(new THREE.Shape(s.poligono.map(([x, y]) => new THREE.Vector2(x, y)))).rotateX(-Math.PI / 2).translate(0, 0.3, 0), new THREE.MeshBasicMaterial({ color: new THREE.Color(TONOS[i % TONOS.length]), transparent: true, opacity: 0.08, depthWrite: false, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -10, polygonOffsetUnits: -10 }));
    cSec.add(m); rellenos.push(m.material);
    esc.linea([...s.poligono, s.poligono[0]].map(([x, y]) => [x, y, 1.2]), { color: TONOS[i % TONOS.length], ancho: 4.5, padre: cSec });
    const cx = s.poligono.reduce((a, p) => a + p[0], 0) / s.poligono.length, cy = s.poligono.reduce((a, p) => a + p[1], 0) / s.poligono.length;
    esc.etiqueta(`<b>${s.nombre}</b>`, { pos: [cx, cy, 14], padre: cSec, color: TONOS[i % TONOS.length], cls: 'lbl-p mini' });
  });
  // válvula + macromedidor en la entrada de cada sector (y el de la entrada al casco): cámara a ras del andén y un pulso del
  // color de su sector que se abre en el piso, para que se lean de lejos
  const valvulas = sitios(datos, 'aguas', 'valvula'), macro = sitios(datos, 'aguas', 'macromedidor');
  const entradas = valvulas.length ? [...valvulas.map((v) => ({ p: [v.x, v.y], tono: TONOS[(Math.max(1, parseInt(String(v.id).replace(/\D/g, ''), 10) || 1) - 1) % TONOS.length] })), ...macro.map((v) => ({ p: [v.x, v.y], tono: '#1d4f9a' }))]
    : [[-200, -120], [-90, 60], [330, 60], [330, 330], [120, -300]].map((p, i) => ({ p, tono: TONOS[i % TONOS.length] }));
  const Av = acopio(), calleDe = (p) => { let mejor = Infinity, a = 0; CALLES.calles.forEach((c) => { for (let j = 1; j < c.p.length; j++) { const [q0, q1] = [c.p[j - 1], c.p[j]], dx = q1[0] - q0[0], dy = q1[1] - q0[1], t = Math.max(0, Math.min(1, ((p[0] - q0[0]) * dx + (p[1] - q0[1]) * dy) / (dx * dx + dy * dy || 1))), d = Math.hypot(p[0] - q0[0] - t * dx, p[1] - q0[1] - t * dy); if (d < mejor) { mejor = d; a = Math.atan2(dy, dx); } } }); return a; };
  const pulsos = [];
  entradas.forEach(({ p, tono }) => {
    Av.poner(camara(), p[0], p[1], calleDe(p));
    for (let k = 0; k < 2; k++) { const o = new THREE.Mesh(new THREE.RingGeometry(1, 1.18, 40).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({ color: new THREE.Color(tono), transparent: true, opacity: 0.7, depthWrite: false })); o.position.copy(V(p[0], p[1], 0.4 + k * 0.05)); o.userData.fase = k / 2; cSec.add(o); pulsos.push(o); }
    esc.etiqueta('', { pos: [p[0], p[1], 3], padre: cSec, cls: 'lbl-dot', color: '#1f5fb8' });
  });
  Av.volcar(cSec, Ms);
  esc.st.onFrame((dt, t) => { if (!cSec.visible || !pulsos.length) return false; pulsos.forEach((o) => { const u = ((t * 0.5) + o.userData.fase) % 1; o.scale.setScalar(3 + u * 13); o.material.opacity = 0.75 * (1 - u); }); return true; });
  esc.etiqueta('<b>Válvula + macromedidor</b><small>entrada de cada sector</small>', { pos: [...(valvulas[0] ? [valvulas[0].x, valvulas[0].y] : [-90, 60]), 40], padre: cSec, color: `var(${color})`, cls: 'lbl-p mini', ancla: [0.5, 1] });

  // módulo de ampliación de la PTAP, al lado de la planta actual
  const amp = sitio0(datos) || [ptap[0] + 62, ptap[1] - 18];
  const mod = moduloPTAP(amp[0], amp[1], 0); cAmp.add(mod);
  esc.etiqueta('<b>Ampliación de la PTAP</b><small>de 40 a ~60 L/s (horizonte 2044)</small>', { pos: [amp[0], amp[1], 20], padre: cAmp, color: `var(${color})` });
  esc.sincronizarEtiquetas();

  const inv = () => esc.st.invalidate();
  const entrada = baja[baja.length - 1];
  const vistaSistema = (duracion) => esc.encuadrar([capt, tanque, ptap, entrada, [capt[0] - 120, capt[1]]], { rumbo: 192, elev: 42, margen: 0.9, duracion });
  let tSis = 0;
  const parar = () => clearTimeout(tSis);
  // (con una narración en pantalla —esc.guiado— la cámara la lleva el plan: el módulo no la mueve por su cuenta)
  const recorrido = () => { parar(); tSis = setTimeout(() => { if (!esc.guiado && !esc.st.paseo && !esc.st.userMoved && cSis.visible && !cRed.visible && !cAmp.visible) vistaSistema(3.5); }, 3000); };
  const vistaPlanta = () => esc.encuadrar(caja([ptap, tanque, capt, amp], 70), { rumbo: 160, elev: 34, margen: 0.86 });
  const vistaCasco = () => esc.encuadrar(lista.flatMap((s) => s.poligono), { rumbo: 196, elev: 50, margen: 0.94 });
  return {
    completo: ['aguas.sistema'],
    salir: () => { parpadeo = false; parar(); },
    alCompleto: parar,
    // estados que una pieza del catálogo puede pedir (visual.js): la red como está hoy, con agua 9 de cada 24 horas
    efectos: { intermitente: (v) => { parpadeo = !!v; if (!v) { matRed.opacity = 0.85; fBaja.set(0.9, 1); inv(); } } },
    pasos: {
      portadilla: { capas: ['aguas.sistema', 'aguas.red'], antes: () => { parar(); parpadeo = true; }, vista: vistaCasco },
      sistema: { capas: ['aguas.sistema'], antes: () => { parpadeo = false; fBaja.set(0.9, 1); }, vista: vistaPlanta, animar: recorrido, alFinal: () => vistaSistema() },
      sectores: { capas: ['aguas.sistema', 'aguas.red', 'aguas.sectores'], antes: () => { parar(); parpadeo = false; matRed.opacity = 0.85; fBaja.set(0.9, 1); }, vista: vistaCasco, animar: () => { if (gsap) rellenos.forEach((m, i) => gsap.fromTo(m, { opacity: 0 }, { opacity: 0.08, duration: 0.6, delay: 0.5 + i * 0.12, onUpdate: inv })); } },
      ampliacion: { capas: ['aguas.sistema', 'aguas.ampliacion'], antes: () => { parar(); parpadeo = false; }, vista: vistaPlanta, animar: () => { if (gsap) gsap.fromTo(mod.scale, { y: 0.01 }, { y: 1, duration: 1.1, delay: 0.8, ease: 'back.out(1.4)', onUpdate: inv }); } },
      '*': { capas: ['aguas.sistema', 'aguas.red', 'aguas.sectores'], antes: () => { parar(); parpadeo = false; matRed.opacity = 0.85; }, vista: vistaCasco },
    },
  };
}
function sitio0(datos) { const s = (datos.geo?.aguas?.sitios || []).find((x) => x.id === 'ptap_ampliacion'); return s ? [s.x, s.y] : null; }
