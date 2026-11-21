// Salud: la torre de servicios de primer nivel junto al hospital Héctor Abad Gómez (el modelo digital del atlas, ahora
// sin paneles propios: su energía viene de la granja solar centralizada) con un rótulo por piso; la red de telemedicina,
// que sale de una antena en la cubierta de la torre hacia el centro de control de la alcaldía y hacia los
// microterritorios de los equipos básicos de salud, y los hogares de la cabecera que esos equipos visitan casa a casa.
// Los microterritorios rurales van en sus centros poblados (OpenStreetMap) como marcadores, sin edificio de salud; los
// que quedan más allá de la maqueta se señalan en su dirección con la distancia.
// Alrededor de las réplicas, el lote del hospital como se usará: plazoleta de adoquín con marquesina, bancas bajo los
// árboles, jardín con palmas y heliconias, tótem, pasillo cubierto entre la torre y la sede actual, la bahía de
// ambulancias en la entrada vehicular de la torre, el parqueadero y gente (pacientes y personal de bata blanca). Las
// coordenadas del lote salen de las réplicas (torre: 54 × 67 m; hospital: 90 × 89 m, centrados en sus puntos de data.js).
import { THREE, gsap, mat } from '../../core.js';
import { membrana, bancas, gente, carros, palmas, jardin, unir, azar, V } from '../geo3d.js';
import { matT } from '../texturas.js';
import { acopio, caja as bloque, cil, letrero } from '../piezas/relleno.js';
import { mastil, matMastil, MASTIL_CCED } from './tic.js';
import { sitios, caja } from './comun.js';

const ALCANCE = 11500;   // radio en el que se dibujan los microterritorios (el terreno de la maqueta llega a 16 km)
// el lote, en metros respecto al centro del hospital (x al oriente, y al norte): la plazoleta en la franja libre entre el
// hospital y el lindero sur, la bahía de ambulancias sobre la vía de la torre (al occidente), el parqueadero sobre el
// asfalto del hospital (al norte) y el pasillo cubierto en el andén oriental de la torre
const LOTE = {
  plaza: [[-2.8, -46.6], [41.8, -46.6], [41.8, -37.5], [-2.8, -37.5]], marquesina: [10.2, -41.8], tronco: [[-0.0, -46.0], [20.0, -45.0]],
  jardin: [[26.2, -46.2], [37.2, -46.2], [37.2, -42.6], [26.2, -42.6]], palmas: [[28.2, -39.6], [36.2, -39.6], [24.6, -46.4]], totem: [39.7, -45.6],
  ambulancias: [[-40.3, -7.7], [-40.3, -13.7]], parqueo: [[20.2, 33.8], [22.8, 33.8], [25.4, 33.8], [28.0, 33.8], [30.6, 33.8]],
  pasillo: [[-7.0, -36.2, -14.2], [-7.0, -9.2, 4.8]],
};
// la torre, en metros respecto a su punto de data.js (los volúmenes de data/edificios/torre_hospital.json): el cuerpo de
// 21,6 × 30 m centrado en `centro`, su fachada occidental en x = `oeste`, la mitad de cada piso a esa altura (pisos 1 a 3
// de 4,3 m; el 4 hasta 17,1 m) y la antena de telemedicina en la esquina noroccidental de la cubierta del piso 4
const TORRE = { centro: [-2.2, 7.4], oeste: -13.0, pisos: [2.2, 6.5, 10.8, 15.0], antena: [-9.0, 18.0], cubierta: 17.1, alto_antena: 7 };
// lo que hay en cada piso (docs/11, sección 4)
const PISOS = [
  ['Piso 1', 'urgencias · rayos X · muestras'],
  ['Piso 2', 'consulta · laboratorio · vacunación'],
  ['Piso 3', '15 camas · partos'],
  ['Piso 4', 'terapias · odontología · telemedicina'],
];
// ambulancia: furgón blanco con franja roja, cabina adelante, vidrios, luces en el techo (brillan: material sin luz) y ruedas
function ambulancia() {
  return {
    blanco: [bloque(4.2, 2.2, 2.1, -0.75, 0.45, 0), bloque(1.5, 1.35, 2.0, 2.1, 0.45, 0), new THREE.BoxGeometry(0.9, 0.6, 2.0).rotateZ(-0.6).translate(2.55, 1.85, 0)],
    rojo: [bloque(4.24, 0.28, 2.14, -0.75, 1.15, 0), bloque(1.54, 0.2, 2.04, 2.1, 1.2, 0), bloque(0.1, 0.55, 0.16, -2.86, 1.9, 0), bloque(0.1, 0.16, 0.55, -2.86, 2.09, 0)],
    vidrio: [bloque(0.06, 0.65, 1.8, 2.86, 1.25, 0), bloque(1.0, 0.55, 2.04, 2.1, 1.3, 0)],
    oscuro: [bloque(5.9, 0.3, 1.9, 0, 0.3, 0)], caucho: [[-1.9, 1.8].map((x) => [-0.95, 0.95].map((z) => new THREE.CylinderGeometry(0.4, 0.4, 0.3, 14).rotateX(Math.PI / 2).translate(x, 0.4, z)))].flat(2),
    baliza: [bloque(0.18, 0.14, 0.5, 1.15, 2.65, -0.55), bloque(0.18, 0.14, 0.5, 1.15, 2.65, 0.55)], azul: [bloque(0.18, 0.14, 0.4, 1.15, 2.65, 0)],
  };
}
// marcador de un microterritorio (icono a escala, unos 15 m de alto): base redonda y cabeza en el color del módulo sobre
// un poste blanco. No es un edificio: marca el centro poblado desde donde el equipo básico recorre las casas
function marcador() {
  return {
    base: [cil(3.6, 0.25, 0, 0, 0, 28)],
    poste: [cil(0.35, 10.6, 0, 0.25, 0, 10)],
    cabeza: [new THREE.SphereGeometry(2.6, 24, 16).translate(0, 12.6, 0)],
    anillo: [new THREE.TorusGeometry(2.62, 0.3, 8, 28).rotateX(Math.PI / 2).translate(0, 12.6, 0)],
  };
}

export function crear(esc, datos) {
  const color = '--m-salud';
  const torre = esc.edificios.get('torre_hospital'), hosp = esc.edificios.get('hospital');
  const pT = torre ? [torre.e.x, torre.e.y] : [-342, -137], pH = hosp ? [hosp.e.x, hosp.e.y] : [-326, -121];
  const cRed = esc.capa('salud.red'), cTorre = esc.capa('salud.torre'), cTer = esc.capa('salud.territorios'), cHoy = esc.capa('salud.hoy');
  const alc = esc.edificios.get('alcaldia'), pA = alc ? [alc.e.x, alc.e.y] : [104, -199];
  const enLote = ([dx, dy]) => [pH[0] + dx, pH[1] + dy];
  const enTorre = ([dx, dy]) => [pT[0] + dx, pT[1] + dy];
  const arco = (a, b, alto, h0 = 12, h1 = 12) => { const pts = []; for (let i = 0; i <= 40; i++) { const t = i / 40; pts.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, h0 + (h1 - h0) * t + alto * 4 * t * (1 - t)]); } return pts; };
  const M = {
    ...matMastil(), adoquin: matT('adoquin', { color: '#ece5d8', polygonOffset: true, polygonOffsetFactor: 0, polygonOffsetUnits: -4 }), concreto: matT('concreto'),
    zinc: matT('zinc', { color: '#d5dade' }), oscuro: mat(new THREE.Color('#2a2e32'), { roughness: 0.5, metalness: 0.45 }),
    blanco: mat(new THREE.Color('#f6f6f2'), { roughness: 0.35, metalness: 0.1 }), rojo: mat(new THREE.Color('#d1262c'), { roughness: 0.45 }), azul: new THREE.MeshBasicMaterial({ color: 0x2f7bff, toneMapped: false }),
    vidrio: mat(new THREE.Color('#2d3b45'), { roughness: 0.06, metalness: 0.75 }), caucho: mat(new THREE.Color('#1b1c1e'), { roughness: 0.85 }),
    poste: mat(new THREE.Color('#f6f6f2'), { roughness: 0.4 }), cabeza: esc.tenir(mat(new THREE.Color('#d1262c'), { roughness: 0.35 }), color),
    base: esc.tenir(mat(new THREE.Color('#d1262c'), { roughness: 0.6 }), color), anillo: mat(new THREE.Color('#ffffff'), { roughness: 0.3 }),
  };
  M.baliza = new THREE.MeshBasicMaterial({ color: 0xff3b30, toneMapped: false });
  const halo = (p, h, padre, tinte, fase) => { const o = new THREE.Mesh(new THREE.RingGeometry(1, 1.12, 48).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.6, depthWrite: false })); o.position.copy(V(p[0], p[1], h)); o.userData.fase = fase; esc.tenir(o.material, tinte); padre.add(o); return o; };

  // telemedicina: una antena en la cubierta de la torre (el centro de telemedicina está en el piso 4) y el mástil del
  // centro de control de la alcaldía; el enlace entre sus antenas es un tubo que brilla, con los datos que viajan por él y
  // un halo que late en la cubierta y en la base del mástil
  const pAnt = enTorre(TORRE.antena), hAnt = TORRE.cubierta + TORRE.alto_antena - 0.7;
  const pMc = [pA[0] + MASTIL_CCED.off[0], pA[1] + MASTIL_CCED.off[1]], hM = MASTIL_CCED.alto - 1;
  const Am = acopio(); Am.poner(mastil(TORRE.alto_antena), ...pAnt, 0, TORRE.cubierta); Am.poner(mastil(MASTIL_CCED.alto), ...pMc); Am.volcar(cRed, M);
  const enlace = arco(pAnt, pMc, 60, hAnt, hM);
  const tubo = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(enlace.map(([x, y, h]) => V(x, y, h))), 80, 1.1, 8, false), new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.8, depthWrite: false, toneMapped: false }));
  esc.tenir(tubo.material, '--data'); cRed.add(tubo);
  esc.linea(enlace, { color: '--data', ancho: 3, punteada: true, guion: 10, padre: cRed });
  esc.flujo(enlace, { color: '#a99cff', potencia: 0.8, max: 16, tam: 2.0, tubo: 0.01, padre: cRed });
  const halos = [[pAnt, TORRE.cubierta + 0.6], [pMc, 0.5]].flatMap(([p, h]) => [0, 1].map((k) => halo(p, h + k * 0.05, cRed, '--data', k / 2)));
  esc.etiqueta('<b>Centro de control de la alcaldía</b><small>recibe el enlace de la torre</small>', { pos: [pA[0], pA[1], 22], padre: cRed, color: 'var(--data)', cls: 'lbl-p mini', ancla: [0, 0.5] });
  esc.etiqueta('<b>Centro de telemedicina</b><small>piso 4 de la torre · especialistas por convenio</small>', { pos: [pAnt[0], pAnt[1], hAnt + 4], padre: cRed, color: `var(${color})`, ancla: [0.5, 1] });

  // microterritorios rurales de los equipos básicos: los de geo.json (OpenStreetMap); si no hay, tres direcciones
  // genéricas. Cada uno es un marcador con un halo que late; los dos crecen con la distancia de la cámara (a 30 km un
  // marcador de 9 m no se vería). De la antena de la torre sale un enlace de telemedicina hacia cada uno
  const gp = sitios(datos, 'salud', 'microterritorio');
  const micro = (gp.length ? gp : [{ nombre: 'Veredas del norte', x: -900, y: 2600 }, { nombre: 'Veredas del occidente', x: -2600, y: 400 }, { nombre: 'Veredas del sur', x: -1500, y: -2600 }])
    .map((s) => { const d = Math.hypot(s.x, s.y), lejos = d > ALCANCE, k = lejos ? ALCANCE / d : 1; return { ...s, p: [s.x * k, s.y * k], lejos, km: s.distancia_km ?? Math.round(d / 100) / 10 }; });
  // (iconos: sin sombra, que de lejos serían manchas de cientos de metros)
  const marcas = Object.entries(marcador()).map(([k, gs]) => { const im = new THREE.InstancedMesh(unir(gs), M[k], micro.length); im.frustumCulled = false; cTer.add(im); return im; });
  const halosM = [], rotulos = [];
  micro.forEach((s) => {
    esc.linea(arco(pAnt, s.p, Math.min(900, 180 + Math.hypot(s.p[0] - pT[0], s.p[1] - pT[1]) * 0.06), hAnt, 12), { color: '--data', ancho: 2.5, punteada: true, guion: 14, opacidad: 0.9, padre: cRed });
    for (let k = 0; k < 2; k++) halosM.push(halo(s.p, 1 + k * 0.1, cTer, color, k / 2));
    const uso = s.uso || 'equipo básico de salud · telemedicina en casa';
    rotulos.push(esc.etiqueta(`<b>${s.nombre}</b><small>${s.lejos ? `a ${String(s.km).replace('.', ',')} km → · ` : ''}${uso}</small>`, { pos: [s.p[0], s.p[1], 140], padre: cTer, color: `var(${color})`, cls: 'lbl-p mini', ancla: [0.5, 1] }));
  });

  // los 2 microterritorios urbanos: hogares de la cabecera que los equipos visitan casa a casa (una muestra ilustrativa de
  // casas reales, repartidas por el casco), con un halo que late sobre cada cubierta y el recorrido desde el hospital
  const hogares = [], discos = [], halosC = [];
  const listoHogares = (esc.listoHuellas || Promise.resolve()).then(() => {
    const r = azar(23), elegidas = [];
    (esc.huellas || []).filter((h) => { const d = Math.hypot(h.cx - pH[0], h.cy - pH[1]); return !h.zona && h.area > 45 && h.area < 220 && d > 70 && d < 520; })
      .map((h) => ({ h, k: r() })).sort((a, b) => a.k - b.k)
      .forEach(({ h }) => { if (elegidas.length < 22 && elegidas.every((e) => Math.hypot(e.cx - h.cx, e.cy - h.cy) > 85)) elegidas.push(h); });
    if (!elegidas.length) return;
    elegidas.forEach((h, i) => {
      const p = [h.cx, h.cy], alto = (h.h || 3) + 0.6;
      hogares.push(p);
      const disco = new THREE.Mesh(new THREE.CircleGeometry(2.2, 24).rotateX(-Math.PI / 2), new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.9, depthWrite: false, toneMapped: false }));
      disco.position.copy(V(p[0], p[1], alto)); esc.tenir(disco.material, color); cTer.add(disco); discos.push(disco);
      for (let k = 0; k < 2; k++) halosC.push(halo(p, alto + k * 0.05, cTer, color, (k / 2 + i * 0.13) % 1));
      if (i % 3 === 0) esc.linea(arco(pH, p, 24 + Math.hypot(p[0] - pH[0], p[1] - pH[1]) * 0.04, 6, alto + 1), { color, ancho: 2, punteada: true, guion: 8, opacidad: 0.85, padre: cTer });
    });
    const c = [hogares.reduce((a, q) => a + q[0], 0) / hogares.length, hogares.reduce((a, q) => a + q[1], 0) / hogares.length];
    esc.etiqueta('<b>Cabecera · 2 microterritorios urbanos</b><small>equipos básicos de salud · visitas casa a casa</small>', { pos: [c[0], c[1], 60], padre: cTer, color: `var(${color})`, cls: 'lbl-p mini', ancla: [0.5, 1] });
    esc.sincronizarEtiquetas(); esc.st.invalidate();
  });

  // escala de cada marcador según la distancia de la cámara (y el rótulo encima de él); los halos se abren con ella. Los
  // hogares de la cabecera también crecen un poco con ella, para que se lean en la vista de todo el casco
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), esc3 = new THREE.Vector3(), pos = new THREE.Vector3();
  const escalas = micro.map(() => 1);
  esc.st.onFrame((dt, t) => {
    let n = false;
    if (cRed.visible) { halos.forEach((o) => { const u = ((t * 0.45) + o.userData.fase) % 1; o.scale.setScalar(4 + u * 30); o.material.opacity = 0.6 * (1 - u); }); n = true; }
    if (!cTer.visible) return n;
    const cam = esc.st.camera.position, kc = THREE.MathUtils.clamp(cam.distanceTo(pos.copy(V(pH[0], pH[1]))) / 450, 1, 6);
    discos.forEach((o) => o.scale.setScalar(kc));
    halosC.forEach((o) => { const u = ((t * 0.4) + o.userData.fase) % 1; o.scale.setScalar(kc * (2.5 + u * 9)); o.material.opacity = 0.7 * (1 - u); });
    micro.forEach((s, i) => {
      pos.copy(V(s.p[0], s.p[1])); const k = THREE.MathUtils.clamp(cam.distanceTo(pos) / 380, 1, 80);
      if (Math.abs(k - escalas[i]) > escalas[i] * 0.02 || !marcas[0].userData.listo) {
        escalas[i] = k;
        m4.compose(pos, q, esc3.set(k, k, k)); marcas.forEach((im) => { im.setMatrixAt(i, m4); im.instanceMatrix.needsUpdate = true; });
        rotulos[i].position.y = Math.max(140, 15.5 * k + 30);
      }
      [halosM[i * 2], halosM[i * 2 + 1]].forEach((o) => { const u = ((t * 0.4) + o.userData.fase) % 1; o.scale.setScalar(k * (10 + u * 26)); o.material.opacity = 0.65 * (1 - u); });
    });
    marcas[0].userData.listo = true;
    return true;
  });

  // huella de la torre en el color del módulo (la réplica es blanca: así se lee la muestra de la leyenda)
  esc.alCargarEdificio?.('torre_hospital', () => {
    const b = esc.cajaEdificio('torre_hospital'); if (!b) return;
    const r = [[b.min.x - 2, -b.max.z - 2], [b.max.x + 2, -b.max.z - 2], [b.max.x + 2, -b.min.z + 2], [b.min.x - 2, -b.min.z + 2]];
    const m = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.35, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -4, polygonOffsetUnits: -4 });
    esc.tenir(m, color);
    const area = new THREE.Mesh(new THREE.ShapeGeometry(new THREE.Shape(r.map(([x, y]) => new THREE.Vector2(x, y)))).rotateX(-Math.PI / 2).translate(0, 0.25, 0), m);
    cTorre.add(area);
    esc.linea([...r, r[0]].map(([x, y]) => [x, y, 0.4]), { color, ancho: 3, padre: cTorre });
    esc.st.invalidate();
  });
  // el lote: plazoleta, marquesina, bancas, jardín, palmas, tótem, pasillo cubierto, ambulancias, parqueadero y gente
  const lote = new THREE.Group(); lote.name = 'lote'; cTorre.add(lote);
  const Al = acopio();
  Al.put('adoquin', new THREE.ShapeGeometry(new THREE.Shape(LOTE.plaza.map(enLote).map(([x, y]) => new THREE.Vector2(x, y)))).rotateX(-Math.PI / 2).translate(0, 0.06, 0));
  LOTE.pasillo.forEach(([dx, y0, y1]) => {
    const [x, ya] = enLote([dx, y0]), yb = pH[1] + y1, L = yb - ya;
    // cubierta volada desde la fachada oriental de la torre, canal y columnas del lado de afuera
    Al.put('zinc', bloque(4.4, 0.1, L, x + 2.0, 3.1, -(ya + L / 2)));
    Al.put('oscuro', bloque(0.12, 0.25, L, x + 4.1, 2.95, -(ya + L / 2)));
    for (let s = 0; s <= L; s += 4) Al.put('oscuro', cil(0.07, 3.1, x + 3.6, 0, -(ya + s), 8));
  });
  LOTE.ambulancias.forEach((d) => Al.poner(ambulancia(), ...enLote(d), Math.PI / 2));
  Al.volcar(lote, M);
  lote.add(membrana(...enLote(LOTE.marquesina), 9, 5, 3.4, 0, { flecha: 0.7, m: matT('membrana', { color: '#f4f1ea' }), mastil: M.oscuro }));
  const [mx, my] = enLote(LOTE.marquesina), [t0x, t0y] = enLote(LOTE.tronco[0]), [t1x, t1y] = enLote(LOTE.tronco[1]);
  const bz = [[mx - 2.3, my - 0.6, 0], [mx + 2.3, my - 0.6, 0], [t0x + 2.4, t0y + 2.4, Math.PI], [t1x - 0.4, t1y + 3.2, Math.PI]];
  lote.add(bancas(bz));
  lote.add(jardin(LOTE.jardin.map(enLote), { densidad: 0.9, semilla: 12, tipos: ['heliconia', 'cordyline', 'helecho', 'heliconia'] }));
  lote.add(palmas(LOTE.palmas.map(enLote), { alto: 8, semilla: 14 }));
  lote.add(carros(LOTE.parqueo.map((d, i) => [...enLote(d), i % 2 ? -Math.PI / 2 : Math.PI / 2]), { semilla: 15 }));
  const tot = letrero([['HOSPITAL', 0.9], ['Héctor Abad Gómez', 1.0], ['Yondó · urgencias 24 horas', 0.6]], { w: 3.2, h: 2.4, alto: 0.6, fondo: '#f4f2ec', tinta: '#2a2e32', acento: '#c81e2a' });
  tot.position.copy(V(...enLote(LOTE.totem))); tot.rotation.y = -Math.PI / 2; lote.add(tot);
  // gente: pacientes y acompañantes sentados bajo la marquesina y en las bancas, personal de bata blanca en la plazoleta y
  // en el pasillo, y quien entra o sale
  const bata = { camisa: '#f6f6f2', pantalon: '#e9eef2' }, verdeQx = { camisa: '#5fa8a0', pantalon: '#5fa8a0' };
  lote.add(gente(bz.flatMap(([x, y, a], i) => (i < 2 ? [-0.45, 0.45] : [0.4]).map((d) => Object.assign([x + Math.cos(a) * d, y + Math.sin(a) * d, a], { h: 0.06 }))), { sentado: true, semilla: 16 }));
  const [px, py] = enLote([-5, -30]);
  lote.add(gente([[mx - 5, my + 1.8, 0.4, bata], [mx - 4.2, my + 2.4, 3.6], [mx + 6, my + 2, 1.2], [mx + 13, my - 1, 2.8, bata], [mx + 14, my - 1.6, 0.2, verdeQx], [px + 0.4, py, Math.PI / 2, bata], [px - 0.6, py - 6, -Math.PI / 2], [px, py + 9, Math.PI / 2, verdeQx], [mx - 9.5, my - 2.5, 0.8], [mx - 8.7, my - 2.9, 0.6]].map((p) => Object.assign(p, { h: 0.06 })), { semilla: 17 }));
  const lTorre = esc.etiqueta('<b>Torre de servicios de primer nivel</b><small>urgencias · partos · 15 camas · laboratorio 24 horas</small>', { pos: [pT[0], pT[1], 36], padre: cTorre, color: `var(${color})`, ancla: [0.5, 1] });
  const lHosp = esc.etiqueta('<b>Hospital Héctor Abad Gómez</b><small>sede actual: administración y apoyo</small>', { pos: [pH[0] + 30, pH[1] + 25, 14], padre: cTorre, color: `var(${color})`, cls: 'lbl-p mini', ancla: [0, 0.5] });
  // un rótulo por piso, contra la fachada occidental de la torre (la de urgencias); cada paso dice cuáles se ven
  const [xO, yC] = [pT[0] + TORRE.oeste, pT[1] + TORRE.centro[1]];
  const lPisos = PISOS.map(([n, que], i) => esc.etiqueta(`<b>${n}</b><small>${que}</small>`, { pos: [xO, yC, TORRE.pisos[i]], padre: cTorre, color: `var(${color})`, cls: 'lbl-p mini', ancla: [1, 0.5] }));
  // portadilla: el hospital de hoy, la única sede pública habilitada
  esc.etiqueta('<b>Hospital Héctor Abad Gómez</b><small>única sede pública habilitada · edificio de 1989</small>', { pos: [pH[0], pH[1], 16], padre: cHoy, color: `var(${color})`, cls: 'lbl-p mini', ancla: [0.5, 1] });
  // qué rótulos de la torre se ven en cada paso: el de la torre, el del hospital actual y los de los pisos pedidos
  const rotulosTorre = ({ torre: vT = true, hospital: vH = true, pisos = [] } = {}) => {
    lTorre.userData.ver = vT; lHosp.userData.ver = vH;
    lPisos.forEach((l, i) => { l.userData.ver = pisos.includes(i + 1); });
    esc.sincronizarEtiquetas();
  };
  rotulosTorre();

  // la torre es la réplica del atlas en modo «proyecto», sin sus paneles ni la conexión de la microrred de sedes
  const verTorre = (v) => esc.modoEdificio('torre_hospital', v ? 'proyecto' : 'hoy', ['solar', 'conexion']);
  const crecerTorre = () => {
    if (!gsap || !torre?.lod) return;
    torre.lod.traverse((o) => { if (o.name === 'obra_nueva') gsap.fromTo(o.scale, { y: 0.02 }, { y: 1, duration: 1.6, delay: 0.7, ease: 'power3.out', onUpdate: () => esc.st.invalidate(), onComplete: () => esc.st.updateShadows() }); });
  };
  const cajaHosp = () => { const b = esc.cajaEdificio('torre_hospital'); const c = esc.cajaEdificio('hospital'); if (b && c) b.union(c); return b || caja([pT, pH], 60); };
  const vistaTorre = () => esc.encuadrar(cajaHosp(), { rumbo: 150, elev: 30, margen: 0.8 });
  // telemedicina: el casco con el enlace al centro de control; los arcos a las veredas salen del cuadro
  const vistaTele = () => esc.encuadrar(caja([pH, pA, pT], 170), { rumbo: 200, elev: 48, margen: 0.85 });
  // salud preventiva: la torre y los hogares de la cabecera que se visitan casa a casa
  const vistaPrev = () => esc.encuadrar(hogares.length ? caja([pH, ...hogares], 20) : caja([pH], 480), { rumbo: 200, elev: 56, margen: 0.94 });
  const vistaTerritorios = () => esc.encuadrar([...micro.map((s) => s.p), pH], { rumbo: 200, elev: 56, margen: 0.86 });
  // si el paso de salud preventiva llega antes que las casas, se vuelve a encuadrar cuando estén (solo si sigue ahí)
  let enPrev = false;
  listoHogares.then(() => { if (enPrev && hogares.length && !esc.guiado && !esc.st.userMoved) vistaPrev(); });
  const paso = (opts, mas = {}) => () => { enPrev = !!mas.prev; verTorre(mas.torre !== false); rotulosTorre(opts); };
  return {
    completo: ['salud.torre'],
    pasos: {
      portadilla: { capas: ['salud.hoy'], antes: paso({}, { torre: false }), vista: () => esc.encuadrar(caja([pH, pT], 140), { rumbo: 165, elev: 38, margen: 0.9 }) },
      componentes: { capas: ['salud.torre', 'salud.red', 'salud.territorios'], antes: paso({}), vista: vistaTerritorios, etiquetas: ['salud.territorios'] },
      torre: { capas: ['salud.torre'], antes: paso({ pisos: [1, 2, 3, 4] }), vista: vistaTorre, animar: crecerTorre },
      preventiva: { capas: ['salud.torre', 'salud.territorios'], antes: paso({ torre: false, hospital: false, pisos: [2] }, { prev: true }), vista: vistaPrev, etiquetas: ['salud.torre', 'salud.territorios'] },
      telesalud: { capas: ['salud.red', 'salud.torre'], antes: paso({ torre: false, hospital: false }), vista: vistaTele, etiquetas: ['salud.red', 'salud.torre'] },
      equipos: { capas: ['salud.territorios', 'salud.red'], antes: paso({}), vista: vistaTerritorios, etiquetas: ['salud.territorios'] },
      '*': { capas: ['salud.torre'], antes: paso({}), vista: vistaTorre },
    },
    salir: () => { enPrev = false; verTorre(false); },
    alCompleto: () => { enPrev = false; verTorre(true); rotulosTorre(); },
  };
}
