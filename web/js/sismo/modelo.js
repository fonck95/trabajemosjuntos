// Modelo estructural del motor sísmico: pseudotridimensional de Wilson y Dovey (1972), como TABS en su origen.
// Contrato de la torre (data/proyectos/torre_hospital/ESPECIFICACION_INTEGRACION.md), 7.4; data/sismo/ESQUEMA.md.
//
// - Diafragma rígido por nivel con 3 grados de libertad dinámicos en su centro de masa: ux, uy, rz.
// - Pórticos planos (y «pórticos» de muros, E1) con v y θ por nodo, condensados por complemento de Schur en cada
//   iteración: K̂ = K_dd − K_dc·K_cc⁻¹·K_cd. Cada pórtico se ensambla aparte, con K_cc en banda (los nodos se numeran
//   por nivel), y su factorización se reutiliza mientras ningún elemento del pórtico cambie de tangente.
// - Compatibilidad: un pórtico en x ubicado en y = c se mueve dx = ux − (c − yc)·rz; uno en y en x = c,
//   dy = uy + (c − xc)·rz (xc, yc: centro de masa del nivel).
// - Elemento de Giberson (vigas, columnas y muros): parte elástica de Timoshenko sobre la longitud flexible
//   L_f = L − di − dj (brazos rígidos, E2), carga del vano (E4), rigidez axial EA/L_f, y rótulas en los extremos
//   (solo en la base de los muros) con propiedades esperadas (E16) y la ley de histeresis.js. El momento de cada
//   extremo equilibra la parte elástica y su amortiguamiento: M = K_e·(e + a1·ė), e = θ − θ0 − θp (E8).
// - Resortes de mampostería (Tomaževič) sobre la deriva del entrepiso en su línea; aislados: sin rigidez (E5).
// - P-Delta lineal por nivel con el peso y el centro de masa de cada nivel de encima (E14).
// Módulo puro: sin DOM ni three; imports relativos con extensión.
import { factorLU, resolverLU, choleskyBanda, resolverBanda, jacobiSimetrico, inversa } from './algebra.js';
import {
  SIN_ROTULA, BILINEAL, CLOUGH, NE, NT, MAX_TRAMOS, RIGIDO, ENVOLVENTE,
  estadoInicial, intervaloRigido, tramos, actualizar, resolver2x2, respuestaMuro,
} from './histeresis.js';

/** Gravedad estándar (m/s²), la de ESQUEMA.md. */
export const G = 9.80665;
export const COLUMNA = 0, VIGA = 1, MURO = 2;
const TIPOS = { columna: COLUMNA, viga: VIGA, muro_concreto: MURO };
const NOMBRE_TIPO = ['columna', 'viga', 'muro_concreto'];

/** Error con código del 7.5: 'datos' | 'no_converge' | 'interno'. */
export class ErrorMotor extends Error {
  constructor(codigo, mensaje, detalle = null) {
    super(mensaje);
    this.name = 'ErrorMotor';
    this.codigo = codigo;
    this.detalle = detalle;
  }
}
const fallo = (mensaje, detalle) => { throw new ErrorMotor('datos', mensaje, detalle); };
const esNum = (x) => typeof x === 'number' && Number.isFinite(x);

// =================================================================================================================
// Armado
// =================================================================================================================
/**
 * Arma el modelo desde una estructura de data/sismo/<id>_estructura.json.
 * opciones: histeresis 'bilineal' | 'clough' (si falta, la de cada sección); noEstructurales 'aislados' (cada muro
 * como diga su campo `aislado`; si falta, trabaja, como en la versión 1 del esquema) | 'confinados' (todos los muros
 * trabajan: el escenario «sin aislar»); pDelta (si falta, `p_delta` de la estructura).
 */
export function armarModelo(estructura, opciones = {}) {
  const est = estructura;
  if (!est || typeof est !== 'object' || !Array.isArray(est.bloques) || !est.bloques.length) fallo('estructura sin «bloques»');
  const op = {
    histeresis: opciones.histeresis ?? null,
    noEstructurales: opciones.noEstructurales ?? 'aislados',
    pDelta: opciones.pDelta ?? est.p_delta !== false,
  };
  if (op.histeresis !== null && op.histeresis !== 'bilineal' && op.histeresis !== 'clough') fallo(`histeresis «${op.histeresis}»: se espera bilineal o clough`);
  if (op.noEstructurales !== 'aislados' && op.noEstructurales !== 'confinados') fallo(`noEstructurales «${op.noEstructurales}»: se espera aislados o confinados`);
  const mats = est.materiales || {}, secs = est.secciones || {};

  // ---- niveles (diafragmas) -------------------------------------------------------------------------------------
  const niveles = [], bloques = [];
  for (const b of est.bloques) {
    if (!Array.isArray(b.niveles) || !b.niveles.length) fallo(`bloque ${b.id}: sin niveles`);
    const base = niveles.length;
    let zAnt = 0;
    b.niveles.forEach((nv, k) => {
      for (const c of ['z', 'masa_t', 'Jz_t_m2']) if (!esNum(nv[c])) fallo(`nivel ${nv.id}: falta «${c}»`);
      if (!(Array.isArray(nv.cm) && nv.cm.length === 2 && nv.cm.every(esNum))) fallo(`nivel ${nv.id}: «cm» debe ser [x, y]`);
      const h = esNum(nv.altura_entrepiso) ? nv.altura_entrepiso : nv.z - zAnt;
      if (!(h > 0)) fallo(`nivel ${nv.id}: altura de entrepiso ≤ 0`);
      if (!(nv.masa_t > 0 && nv.Jz_t_m2 > 0)) fallo(`nivel ${nv.id}: masa y Jz deben ser positivos`);
      const contorno = Array.isArray(nv.contorno) && nv.contorno.length >= 3 ? nv.contorno.map((q) => [q[0], q[1]]) : [[nv.cm[0], nv.cm[1]]];
      niveles.push({
        id: nv.id, bloque: b.id, ib: bloques.length, k: k + 1, g: base + k, abajo: k === 0 ? -1 : base + k - 1,
        z: nv.z, h, masa: nv.masa_t, Jz: nv.Jz_t_m2, xc: nv.cm[0], yc: nv.cm[1],
        peso: esNum(nv.peso_sismico_kN) ? nv.peso_sismico_kN : nv.masa_t * G, contorno, contornoPlano: Float64Array.from(contorno.flat()),
      });
      zAnt = nv.z;
    });
    bloques.push({ id: b.id, base, n: b.niveles.length });
  }
  const N = niveles.length, nd = 3 * N;
  const masa = new Float64Array(nd);
  niveles.forEach((nv, g) => { masa[3 * g] = masa[3 * g + 1] = nv.masa; masa[3 * g + 2] = nv.Jz; });

  // fila de compatibilidad: desplazamiento lateral de la línea (dir, c) en el nivel global g
  const fila = (dir, c, g) => {
    const nv = niveles[g];
    return dir === 0 ? { t: 3 * g, r: 3 * g + 2, coef: -(c - nv.yc) } : { t: 3 * g + 1, r: 3 * g + 2, coef: c - nv.xc };
  };

  // ---- pórticos, nodos y elementos -------------------------------------------------------------------------------
  const porticos = [], nodos = [], elems = [];
  const idsVistos = new Set();
  const unico = (id, que) => { if (idsVistos.has(id)) fallo(`id repetido: ${id} (${que})`); idsVistos.add(id); };
  let ncTot = 0;
  est.bloques.forEach((b, ib) => {
    const blq = bloques[ib];
    const zb = [0, ...b.niveles.map((n) => n.z)];
    for (const p of b.porticos || []) {
      unico(p.id, 'pórtico');
      const dir = p.direccion === 'x' ? 0 : p.direccion === 'y' ? 1 : fallo(`pórtico ${p.id}: dirección «${p.direccion}»`);
      if (!esNum(p.coordenada)) fallo(`pórtico ${p.id}: falta «coordenada»`);
      const c = p.coordenada;
      const ip = porticos.length;
      const apoyos = p.apoyos || {};
      const locales = new Map();
      const nodosP = [];
      for (const n of p.nodos || []) {
        unico(n.id, 'nodo');
        if (!esNum(n.s) || !Number.isInteger(n.nivel) || n.nivel < 0 || n.nivel > blq.n) fallo(`nodo ${n.id}: «s» o «nivel» inválidos`);
        const apoyo = apoyos[n.id] ?? null;
        if (apoyo !== null && apoyo !== 'empotrado' && apoyo !== 'articulado') fallo(`nodo ${n.id}: apoyo «${apoyo}»`);
        if (n.nivel === 0 && apoyo === null) fallo(`nodo ${n.id}: nodo de base sin apoyo`);
        const z = zb[n.nivel];
        const reg = {
          id: n.id, portico: p.id, ip, s: n.s, nivel: n.nivel, z, apoyo, carga: esNum(n.carga_kN) ? n.carga_kN : 0,
          xyz: dir === 0 ? [n.s, c, z] : [c, n.s, z], orden: nodosP.length, lat: -1, iv: -1, it: -1,
        };
        locales.set(n.id, reg);
        nodosP.push(reg);
      }
      // grados de libertad laterales del pórtico: un desplazamiento por nivel presente (≥ 1)
      const nivPres = [...new Set(nodosP.filter((n) => n.nivel > 0).map((n) => n.nivel))].sort((a, b2) => a - b2);
      const nl = nivPres.length;
      const latT = new Int32Array(nl), latR = new Int32Array(nl), latC = new Float64Array(nl), latG = new Int32Array(nl);
      nivPres.forEach((k, l) => {
        const g = blq.base + k - 1;
        const f = fila(dir, c, g);
        latT[l] = f.t; latR[l] = f.r; latC[l] = f.coef; latG[l] = g;
      });
      const latDe = new Map(nivPres.map((k, l) => [k, l]));
      // condensados: nodos libres ordenados por nivel y s (banda angosta)
      const libres = nodosP.filter((n) => n.apoyo !== 'empotrado').sort((a, b2) => a.nivel - b2.nivel || a.s - b2.s || a.orden - b2.orden);
      let nc = 0;
      for (const n of libres) {
        if (n.apoyo === null) n.iv = nl + nc++;
        n.it = nl + nc++;
      }
      const n = nl + nc;   // índice n = grado de libertad fijo (vale 0)
      for (const nd_ of nodosP) {
        nd_.lat = nd_.nivel > 0 ? latDe.get(nd_.nivel) : n;
        if (nd_.iv < 0) nd_.iv = n;
        if (nd_.it < 0) nd_.it = n;
      }
      const P = {
        id: p.id, bloque: b.id, ib, dir, c, nl, nc, n, offC: ncTot, latT, latR, latC, latG, niveles: nivPres,
        e0: elems.length, e1: 0, w: 0, nodos: nodosP,
      };
      // elementos
      for (const e of p.elementos || []) {
        unico(e.id, 'elemento');
        const tipo = TIPOS[e.tipo];
        if (tipo === undefined) fallo(`elemento ${e.id}: tipo «${e.tipo}»`);
        const ni = locales.get(e.i), nj = locales.get(e.j);
        if (!ni || !nj) fallo(`elemento ${e.id}: nodos fuera de su pórtico`);
        const sec = secs[e.seccion];
        if (!sec) fallo(`elemento ${e.id}: sección «${e.seccion}» no existe`);
        const mat = mats[sec.material];
        if (!mat) fallo(`sección ${e.seccion}: material «${sec.material}» no existe`);
        elems.push({ e, tipo, ni, nj, sec, mat, P, ib, blq });
      }
      P.e1 = elems.length;
      ncTot += nc;
      porticos.push(P);
      nodos.push(...nodosP);
    }
  });

  const nP = porticos.length, nE = elems.length, nN = nodos.length;
  if (!nE) fallo('la estructura no tiene elementos');

  // ---- arreglos de los elementos ---------------------------------------------------------------------------------
  const el = {
    tipo: new Int8Array(nE), port: new Int32Array(nE), piso: new Int32Array(nE), gPiso: new Int32Array(nE),
    dof: new Int32Array(6 * nE), A: new Float64Array(18 * nE),
    f11: new Float64Array(nE), f12: new Float64Array(nE), f22: new Float64Array(nE),
    k11: new Float64Array(nE), k12: new Float64Array(nE), k22: new Float64Array(nE), kax: new Float64Array(nE),
    th0: new Float64Array(2 * nE), Lf: new Float64Array(nE), L: new Float64Array(nE), w: new Float64Array(nE),
    EI: new Float64Array(nE),
    rmod: new Int8Array(2 * nE), sup: new Float64Array(2 * nE), inf: new Float64Array(2 * nE), H: new Float64Array(2 * nE),
    Mn: new Float64Array(nE), Vn: new Float64Array(nE), IO: new Float64Array(nE), LS: new Float64Array(nE), CP: new Float64Array(nE),
    conLimites: new Uint8Array(nE),
    id: new Array(nE), info: new Array(nE),
  };
  const Pg = new Float64Array(ncTot);
  const avisos = [];
  // base de cada muro de concreto: el elemento cuyo nodo i no es el nodo j de otro tramo del mismo muro (E1: la
  // rótula del muro va solo ahí; los tramos de encima son elásticos, como el diseño por capacidad de muros)
  const jMuro = new Set(elems.filter((x) => x.tipo === MURO).map((x) => x.nj.id));
  elems.forEach((x, ie) => {
    const { e, tipo, ni, nj, sec, mat, P } = x;
    const Ec = mat.Ec_MPa ?? mat.E_MPa ?? mat.Es_MPa;
    if (!esNum(Ec) || !(Ec > 0)) fallo(`material ${sec.material}: falta el módulo de elasticidad`);
    for (const c of ['A', 'I', 'factor_fisuracion']) if (!esNum(sec[c])) fallo(`sección ${e.seccion}: falta «${c}»`);
    const E = Ec * 1000;                                    // MPa → kPa (kN/m²)
    const nu = esNum(mat.nu) ? mat.nu : 0.2;
    const Gm = E / (2 * (1 + nu));                          // módulo de cortante isótropo
    const EI = E * sec.I * sec.factor_fisuracion;          // inercia fisurada (NSR-10 C.10; ESQUEMA.md)
    const invGAv = esNum(sec.Av) && sec.Av > 0 ? 1 / (Gm * sec.Av) : 0;   // Av ausente o infinita: sin deformación por cortante
    const [di, dj] = Array.isArray(e.brazo_rigido_m) ? e.brazo_rigido_m : [0, 0];
    let L;
    if (tipo === VIGA) {
      if (ni.nivel !== nj.nivel) fallo(`viga ${e.id}: extremos en niveles distintos`);
      L = nj.s - ni.s;
      if (!(L > 0)) fallo(`viga ${e.id}: el nodo j debe quedar a mayor s que el i`);
    } else {
      if (nj.nivel !== ni.nivel + 1) fallo(`${e.tipo} ${e.id}: j debe estar un nivel arriba de i`);
      if (Math.abs(ni.s - nj.s) > 1e-9) fallo(`${e.tipo} ${e.id}: no es vertical`);
      L = nj.z - ni.z;
    }
    const Lf = L - di - dj;
    if (!(Lf > 0)) fallo(`elemento ${e.id}: longitud flexible L − di − dj ≤ 0`);
    el.tipo[ie] = tipo; el.port[ie] = porticos.indexOf(P); el.L[ie] = L; el.Lf[ie] = Lf; el.EI[ie] = EI;
    const piso = tipo === VIGA ? ni.nivel : nj.nivel;
    el.piso[ie] = piso;
    el.gPiso[ie] = piso > 0 ? x.blq.base + piso - 1 : -1;
    el.id[ie] = e.id;

    // grados de libertad locales [dI, vI, θI, dJ, vJ, θJ] (índices del vector del pórtico; n = fijo)
    const d = el.dof, o6 = 6 * ie;
    d[o6] = ni.lat; d[o6 + 1] = ni.iv; d[o6 + 2] = ni.it; d[o6 + 3] = nj.lat; d[o6 + 4] = nj.iv; d[o6 + 5] = nj.it;
    // cinemática q = a·u (deformaciones básicas: giros de los extremos respecto a la cuerda y alargamiento)
    const A = el.A, o = 18 * ie, iL = 1 / Lf;
    if (tipo === VIGA) {
      // cuerda ψ = (v'_j − v'_i)/L_f con v'_i = vI + di·θI y v'_j = vJ − dj·θJ (extremos de la parte flexible)
      A.set([0, iL, 1 + di * iL, 0, -iL, dj * iL], o);
      A.set([0, iL, di * iL, 0, -iL, 1 + dj * iL], o + 6);
      A.set([0, 0, 0, 0, 0, 0], o + 12);             // los dos extremos están en el mismo diafragma: sin alargamiento
    } else {
      // cuerda ψ = −(d'_j − d'_i)/L_f con d'_i = dI − di·θI y d'_j = dJ + dj·θJ
      A.set([-iL, 0, 1 + di * iL, iL, 0, dj * iL], o);
      A.set([-iL, 0, di * iL, iL, 0, 1 + dj * iL], o + 6);
      A.set([0, -1, 0, 0, 1, 0], o + 12);
    }
    // flexibilidad de la parte elástica (Timoshenko): f_e = (L_f/(6EI))·[[2,−1],[−1,2]] + (1/(G·Av·L_f))·[[1,1],[1,1]]
    const sC = invGAv * iL;
    const f11 = Lf / (3 * EI) + sC, f12 = -Lf / (6 * EI) + sC;
    const det = f11 * f11 - f12 * f12;
    el.f11[ie] = f11; el.f12[ie] = f12; el.f22[ie] = f11;
    el.k11[ie] = f11 / det; el.k12[ie] = -f12 / det; el.k22[ie] = f11 / det;
    el.kax[ie] = tipo === VIGA ? 0 : (E * sec.A) / Lf;     // EA sobre la parte flexible (los brazos son rígidos)

    // carga del vano (E4): giros de la viga simplemente apoyada, θ0 = c·[−1, +1]. Con Timoshenko el giro de la
    // sección en el apoyo no tiene parte de cortante (trabajo virtual: ∫V_w·v_i dx = 0 porque v_i = 1/L_f es
    // constante y V_w es antisimétrico): c = w·L_f³/(24·EI), y los momentos de empotramiento quedan en w·L_f²/12.
    const wv = tipo === VIGA && esNum(e.w_gravedad_kN_m) ? e.w_gravedad_kN_m : 0;
    if (tipo !== VIGA && esNum(e.w_gravedad_kN_m) && e.w_gravedad_kN_m !== 0) avisos.push(`${e.id}: w_gravedad solo aplica a vigas; se ignora`);
    el.w[ie] = wv;
    const c0 = (wv * Lf ** 3) / (24 * EI);
    el.th0[2 * ie] = -c0; el.th0[2 * ie + 1] = c0;
    if (wv !== 0) {
      // reacciones de la parte flexible (w·L_f/2) y carga sobre los brazos, llevadas a los nudos
      const R = (wv * Lf) / 2;
      const sumar = (idx, val) => { if (idx < P.n) Pg[P.offC + idx - P.nl] += val; };
      sumar(ni.iv, -(R + wv * di)); sumar(ni.it, -(R * di + (wv * di * di) / 2));
      sumar(nj.iv, -(R + wv * dj)); sumar(nj.it, +(R * dj + (wv * dj * dj) / 2));
    }

    // rótulas con propiedades esperadas (E16), asimétricas en vigas y muros (E3)
    for (const c of ['My_kNm']) if (!esNum(sec[c])) fallo(`sección ${e.seccion}: falta «${c}»`);
    const conE = esNum(sec.My_e_kNm);
    const MyE = conE ? sec.My_e_kNm : sec.My_kNm;
    const Mpos = conE ? sec.My_e_pos_kNm ?? MyE : sec.My_pos_kNm ?? MyE;
    const Mneg = conE ? sec.My_e_neg_kNm ?? MyE : sec.My_neg_kNm ?? MyE;
    const alfa = esNum(sec.endurecimiento) && sec.endurecimiento > 0 ? sec.endurecimiento : 1e-4;
    let ke;
    if (tipo === MURO) {
      // muro en voladizo: k_e = EI_fis/lp, lp = 0,5·lw ≤ altura del piso (ASCE/SEI 41-17, por confirmar)
      const hPiso = x.blq && niveles[x.blq.base + nj.nivel - 1].h;
      const lp = esNum(sec.lp_m) ? sec.lp_m : Math.min(0.5 * sec.h, hPiso);
      if (!(lp > 0)) fallo(`sección ${e.seccion}: lp inválida`);
      ke = EI / lp;
    } else ke = (6 * EI) / Lf;                              // doble curvatura: M = 6EI·θ/L_f con giros iguales
    const modelo = (op.histeresis ?? sec.histeresis) === 'clough' ? CLOUGH : BILINEAL;
    const h2 = 2 * ie;
    if (tipo === VIGA) {
      // momento de extremo antihorario positivo: en i, M > 0 tracciona arriba (flexión negativa)
      el.sup[h2] = Mneg; el.inf[h2] = Mpos; el.sup[h2 + 1] = Mpos; el.inf[h2 + 1] = Mneg;
    } else if (tipo === MURO) {
      el.sup[h2] = Mpos; el.inf[h2] = Mneg; el.sup[h2 + 1] = Infinity; el.inf[h2 + 1] = Infinity;
    } else {
      el.sup[h2] = el.inf[h2] = el.sup[h2 + 1] = el.inf[h2 + 1] = MyE;
    }
    el.rmod[h2] = tipo === MURO && jMuro.has(ni.id) ? SIN_ROTULA : modelo;
    el.rmod[h2 + 1] = tipo === MURO ? SIN_ROTULA : modelo;
    el.H[h2] = el.H[h2 + 1] = alfa * ke;
    if (!(el.sup[h2] > 0 && el.inf[h2] > 0)) fallo(`sección ${e.seccion}: momentos de fluencia deben ser positivos`);

    el.Mn[ie] = esNum(sec.Mn_e_kNm) ? sec.Mn_e_kNm : esNum(sec.Mn_kNm) ? sec.Mn_kNm : MyE;
    el.Vn[ie] = esNum(sec.Vn_e_kN) ? sec.Vn_e_kN : esNum(sec.Vn_kN) ? sec.Vn_kN : Infinity;
    const conL = esNum(sec.theta_p_IO);
    el.conLimites[ie] = conL ? 1 : 0;
    el.IO[ie] = conL ? sec.theta_p_IO : esNum(sec.theta_p_cap) ? sec.theta_p_cap : Infinity;
    el.LS[ie] = esNum(sec.theta_p_LS) ? sec.theta_p_LS : Infinity;
    el.CP[ie] = esNum(sec.theta_p_CP) ? sec.theta_p_CP : Infinity;
    el.info[ie] = {
      id: e.id, tipo: NOMBRE_TIPO[tipo], portico: P.id, nivel: esNum(e.nivel) ? e.nivel : piso, fisico: e.fisico ?? e.id,
      i: e.i, j: e.j, xyz_i: ni.xyz, xyz_j: nj.xyz, seccion: e.seccion,
    };
  });
  // cargas puntuales en los nodos (hacia abajo)
  for (const n of nodos) {
    if (n.carga === 0) continue;
    const P = porticos[n.ip];
    if (n.iv < P.n) Pg[P.offC + n.iv - P.nl] -= n.carga;
  }
  // nodos libres sin elementos: K_cc singular
  const usados = new Set();
  elems.forEach((x) => { usados.add(x.ni.id); usados.add(x.nj.id); });
  for (const n of nodos) if (n.apoyo !== 'empotrado' && !usados.has(n.id)) fallo(`nodo ${n.id}: libre y sin elementos`);

  // ancho de banda de K_cc por pórtico
  for (const P of porticos) {
    let w = 0;
    for (let ie = P.e0; ie < P.e1; ie++) {
      const idx = [];
      for (let k = 0; k < 6; k++) { const a = el.dof[6 * ie + k]; if (a >= P.nl && a < P.n) idx.push(a - P.nl); }
      for (const a of idx) for (const b of idx) w = Math.max(w, Math.abs(a - b));
    }
    P.w = w;
  }

  // ---- mampostería -----------------------------------------------------------------------------------------------
  const muros = [];
  est.bloques.forEach((b, ib) => {
    for (const r of b.resortes || []) {
      if (r.tipo !== 'muro_mamposteria') continue;
      unico(r.id, 'resorte');
      const blq = bloques[ib];
      if (!Number.isInteger(r.nivel) || r.nivel < 1 || r.nivel > blq.n) fallo(`muro ${r.id}: nivel inválido`);
      const dir = r.direccion === 'x' ? 0 : r.direccion === 'y' ? 1 : fallo(`muro ${r.id}: dirección «${r.direccion}»`);
      const env = r.envolvente || {};
      for (const c of ['Vcr_kN', 'dcr_m', 'Vmax_kN', 'dmax_m', 'du_m', 'residual']) if (!esNum(env[c])) fallo(`muro ${r.id}: falta envolvente.${c}`);
      const g = blq.base + r.nivel - 1;
      const b2 = new Float64Array(nd);
      const f1 = fila(dir, r.coordenada, g);
      b2[f1.t] += 1; b2[f1.r] += f1.coef;
      if (niveles[g].abajo >= 0) { const f0 = fila(dir, r.coordenada, niveles[g].abajo); b2[f0.t] -= 1; b2[f0.r] -= f0.coef; }
      const aisladoArchivo = r.aislado ?? false;
      const ix = [], bv = [];
      for (let a = 0; a < nd; a++) if (b2[a] !== 0) { ix.push(a); bv.push(b2[a]); }
      muros.push({
        id: r.id, dir, c: r.coordenada, g, h: niveles[g].h, b: b2, ix: Int32Array.from(ix), bv: Float64Array.from(bv), env, estados: r.estados_de_dano || [],
        aislado: op.noEstructurales === 'confinados' ? false : aisladoArchivo, aisladoArchivo,
      });
    }
  });

  // ---- P-Delta por nivel (E14) -----------------------------------------------------------------------------------
  const Kpd = new Float64Array(nd * nd);
  if (op.pDelta) {
    for (const blq of bloques) {
      for (let k = 1; k <= blq.n; k++) {
        const gk = blq.base + k - 1, ga = k > 1 ? gk - 1 : -1;
        const hk = niveles[gk].h;
        for (let j = k; j <= blq.n; j++) {
          const nj = niveles[blq.base + j - 1];
          // deriva del entrepiso k medida en CM_j (compatibilidad de los dos diafragmas) y giro relativo
          const bx = new Float64Array(nd), by = new Float64Array(nd), br = new Float64Array(nd);
          bx[3 * gk] += 1; bx[3 * gk + 2] += -(nj.yc - niveles[gk].yc);
          by[3 * gk + 1] += 1; by[3 * gk + 2] += nj.xc - niveles[gk].xc;
          br[3 * gk + 2] += 1;
          if (ga >= 0) {
            bx[3 * ga] -= 1; bx[3 * ga + 2] -= -(nj.yc - niveles[ga].yc);
            by[3 * ga + 1] -= 1; by[3 * ga + 2] -= nj.xc - niveles[ga].xc;
            br[3 * ga + 2] -= 1;
          }
          // 4 columnas articuladas con W_j/4 en CM_j ± r_j (r_j² = Jz_j/m_j): −(W_j/h_k)·(bxᵀbx + byᵀby + r²·brᵀbr)
          const f = nj.peso / hk, r2 = nj.Jz / nj.masa;
          for (let a = 0; a < nd; a++) {
            if (bx[a] === 0 && by[a] === 0 && br[a] === 0) continue;
            for (let c = 0; c < nd; c++) Kpd[a * nd + c] -= f * (bx[a] * bx[c] + by[a] * by[c] + r2 * br[a] * br[c]);
          }
        }
      }
    }
  }

  // ---- cajas de trabajo por pórtico ------------------------------------------------------------------------------
  for (const P of porticos) {
    const { nl, nc, w } = P;
    P.uLoc = new Float64Array(P.n + 1);
    P.Floc = new Float64Array(P.n + 1);
    P.Kdd = new Float64Array(nl * nl);
    P.Kcd = new Float64Array(nc * nl);
    P.Kcc = new Float64Array(nc * (w + 1));
    P.X = new Float64Array(nc * nl);
    P.Khat = new Float64Array(nl * nl);
    P.y = new Float64Array(nc);
    P.col = new Float64Array(nc);
    P.sucio = true;
    P.fac = NaN;
    // entrepisos del pórtico: (índice lateral de arriba, de abajo o −1 si es el suelo, nivel global de arriba)
    const pres = new Set(P.niveles);
    const tieneBase = P.nodos.some((n) => n.nivel === 0);
    P.entrepisos = [];
    P.niveles.forEach((k, l) => {
      const abajo = k === 1 ? (tieneBase ? -1 : null) : pres.has(k - 1) ? P.niveles.indexOf(k - 1) : null;
      if (abajo !== null) P.entrepisos.push({ l, la: abajo, g: P.latG[l] });
    });
  }

  const mod = {
    est, op, niveles, bloques, N, nd, masa, porticos, nodos, nP, nE, nN, ncTot, el, Pg, muros, Kpd, avisos,
    indiceElemento: new Map(el.id.map((id, i) => [id, i])),
    _cache: {},
  };
  mod.nucleo = new Nucleo(mod);
  return mod;
}

// =================================================================================================================
// Núcleo: evaluación de los elementos, ensamblaje por pórtico y condensación
// =================================================================================================================
/**
 * Estado de los elementos (comprometido y de prueba) y operaciones de una iteración de Newton. Lo usan la gravedad,
 * los modos y el integrador. Convención: uD (3N) son los desplazamientos del diafragma; uC (ncTot) los v y θ.
 */
export class Nucleo {
  constructor(mod) {
    this.mod = mod;
    const nE = mod.nE;
    this.st = new Float64Array(2 * nE * NE);     // rótulas, comprometido
    this.stP = new Float64Array(2 * nE * NE);    // rótulas, de prueba (se escribe al comprometer)
    this.e = new Float64Array(2 * nE);           // deformación elástica comprometida e = θ − θ0 − θp
    this.ed = new Float64Array(2 * nE);          // su velocidad (Newmark)
    this.dl = new Float64Array(nE);              // alargamiento comprometido
    this.dld = new Float64Array(nE);
    this.Q = new Float64Array(3 * nE);           // fuerzas comprometidas: Mi, Mj, N
    this.thp = new Float64Array(2 * nE);         // θp comprometido (copia de st para leer rápido)
    // de prueba
    this.Qt = new Float64Array(3 * nE);
    this.et = new Float64Array(2 * nE);
    this.dlt = new Float64Array(nE);
    this.thpT = new Float64Array(2 * nE);
    this.tipoT = new Int8Array(2 * nE);
    this.bT = new Float64Array(2 * nE);
    this.kt = new Float64Array(4 * nE);          // tangente: kt11, kt12, kt22, kax·fac
    this.sig = new Float64Array(2 * nE).fill(NaN);   // pendientes b con las que se factorizó el pórtico
    this.P1 = new Float64Array(MAX_TRAMOS * NT);
    this.P2 = new Float64Array(MAX_TRAMOS * NT);
    this.sal = new Float64Array(6);
    this.ri = new Float64Array(2);
    this.KfD = new Float64Array(mod.nd * mod.nd);    // Σ Tᵀ·K̂·T de los pórticos
    this.KfDvalida = false;
    // intervalo de M en el que cada rótula queda rígida desde su estado comprometido (cambia solo al comprometer)
    this.lo = new Float64Array(2 * nE);
    this.hi = new Float64Array(2 * nE);
    const el = mod.el;
    for (let h = 0; h < 2 * nE; h++) estadoInicial(el.sup[h], el.inf[h], this.st, h * NE);
    this._intervalos();
  }

  _intervalos(h0 = 0, h1 = 2 * this.mod.nE) {
    const el = this.mod.el, ri = this.ri;
    for (let h = h0; h < h1; h++) {
      intervaloRigido(el.rmod[h], el.sup[h], el.inf[h], el.H[h], this.st, h * NE, ri);
      this.lo[h] = ri[0]; this.hi[h] = ri[1];
    }
  }

  /** Copia del estado comprometido de los elementos (para volver a él). */
  guardar() {
    return { st: this.st.slice(), e: this.e.slice(), ed: this.ed.slice(), dl: this.dl.slice(), dld: this.dld.slice(), Q: this.Q.slice(), thp: this.thp.slice() };
  }
  restaurar(s) {
    this.st.set(s.st); this.e.set(s.e); this.ed.set(s.ed); this.dl.set(s.dl); this.dld.set(s.dld); this.Q.set(s.Q); this.thp.set(s.thp);
    for (const P of this.mod.porticos) P.sucio = true;
    this.KfDvalida = false;
    this._intervalos();
  }

  /**
   * Estado de prueba de todos los elementos para (uD, uC). fac = 1 + a1·γ/(β·Δt) (1 en estática); dt = 0 en estática.
   * Deja las fuerzas internas en P.Floc de cada pórtico y marca los pórticos cuya tangente cambió.
   */
  evaluar(uD, uC, fac, a1, dt) {
    const mod = this.mod, el = mod.el;
    const dof = el.dof, A = el.A, th0 = el.th0;
    const st = this.st, Qt = this.Qt, et = this.et, dlt = this.dlt, thpT = this.thpT, tipoT = this.tipoT, bT = this.bT, kt = this.kt, sig = this.sig;
    const eN = this.e, edN = this.ed, dlN = this.dl, dldN = this.dld;
    const dinamico = dt > 0 && a1 > 0;
    const c1 = dt > 0 ? 2 / dt : 0;                 // γ/(β·Δt) con γ = 1/2, β = 1/4
    const P1 = this.P1, P2 = this.P2, sal = this.sal, lo = this.lo, hi = this.hi;
    const ifac = 1 / fac;
    for (const P of mod.porticos) {
      const uL = P.uLoc, FL = P.Floc, nl = P.nl, n = P.n;
      for (let l = 0; l < nl; l++) uL[l] = uD[P.latT[l]] + P.latC[l] * uD[P.latR[l]];
      for (let i = 0; i < P.nc; i++) uL[nl + i] = uC[P.offC + i];
      uL[n] = 0;
      FL.fill(0);
      let sucio = P.sucio || P.fac !== fac;
      for (let ie = P.e0; ie < P.e1; ie++) {
        const o6 = 6 * ie, o = 18 * ie, h0 = 2 * ie, h1 = h0 + 1;
        const u0 = uL[dof[o6]], u1 = uL[dof[o6 + 1]], u2 = uL[dof[o6 + 2]], u3 = uL[dof[o6 + 3]], u4 = uL[dof[o6 + 4]], u5 = uL[dof[o6 + 5]];
        const q0 = A[o] * u0 + A[o + 1] * u1 + A[o + 2] * u2 + A[o + 3] * u3 + A[o + 4] * u4 + A[o + 5] * u5;
        const q1 = A[o + 6] * u0 + A[o + 7] * u1 + A[o + 8] * u2 + A[o + 9] * u3 + A[o + 10] * u4 + A[o + 11] * u5;
        const q2 = A[o + 12] * u0 + A[o + 13] * u1 + A[o + 14] * u2 + A[o + 15] * u3 + A[o + 16] * u4 + A[o + 17] * u5;
        const t0 = q0 - th0[h0], t1 = q1 - th0[h1];
        const K11 = el.k11[ie], K12 = el.k12[ie], K22 = el.k22[ie], kax = el.kax[ie];
        // historia del amortiguamiento de la parte elástica: M = K̃·e + h con h = −a1·K_e·(c1·e_n + ė_n)
        let g0 = 0, g1 = 0, gax = 0;
        if (dinamico) {
          const z0 = c1 * eN[h0] + edN[h0], z1 = c1 * eN[h1] + edN[h1];
          g0 = -a1 * (K11 * z0 + K12 * z1);
          g1 = -a1 * (K12 * z0 + K22 * z1);
          gax = -a1 * kax * (c1 * dlN[ie] + dldN[ie]);
        }
        const k11 = fac * K11, k12 = fac * K12, k22 = fac * K22;
        const p0 = st[h0 * NE], p1 = st[h1 * NE];
        let M0 = k11 * (t0 - p0) + k12 * (t1 - p1) + g0;
        let M1 = k12 * (t0 - p0) + k22 * (t1 - p1) + g1;
        let tp0 = p0, tp1 = p1, b0 = 0, b1 = 0, ty0 = RIGIDO, ty1 = RIGIDO;
        if (M0 < lo[h0] || M0 > hi[h0] || M1 < lo[h1] || M1 > hi[h1]) {
          const m0 = el.rmod[h0], m1 = el.rmod[h1];
          // retorno al estado admisible: f̃·M + Φ(M) = θt + f̃·h, con f̃ = f_e/fac
          const f11 = el.f11[ie] * ifac, f12 = el.f12[ie] * ifac, f22 = el.f22[ie] * ifac;
          const r0 = t0 + f11 * g0 + f12 * g1, r1 = t1 + f12 * g0 + f22 * g1;
          const n0 = tramos(m0, el.sup[h0], el.inf[h0], el.H[h0], st, h0 * NE, P1);
          const n1 = tramos(m1, el.sup[h1], el.inf[h1], el.H[h1], st, h1 * NE, P2);
          const tol = 1e-11 * (Math.min(el.sup[h0], 1e12) + Math.min(el.inf[h0], 1e12) + 1);
          if (!resolver2x2(f11, f12, f22, r0, r1, P1, n0, P2, n1, M0, M1, tol, sal)) {
            throw new ErrorMotor('interno', `retorno sin solución en ${el.id[ie]}`, { elemento: el.id[ie] });
          }
          M0 = sal[0]; M1 = sal[1]; b0 = sal[2]; b1 = sal[3];
          const oa = sal[4] * NT, ob = sal[5] * NT;
          tp0 = P1[oa + 2] + P1[oa + 3] * M0; ty0 = P1[oa + 4];
          tp1 = P2[ob + 2] + P2[ob + 3] * M1; ty1 = P2[ob + 4];
        }
        const Nx = fac * kax * q2 + gax;
        Qt[3 * ie] = M0; Qt[3 * ie + 1] = M1; Qt[3 * ie + 2] = Nx;
        thpT[h0] = tp0; thpT[h1] = tp1; tipoT[h0] = ty0; tipoT[h1] = ty1; bT[h0] = b0; bT[h1] = b1;
        et[h0] = t0 - tp0; et[h1] = t1 - tp1; dlt[ie] = q2;
        // tangente consistente K_t = (f̃ + diag(b))⁻¹
        if (b0 === 0 && b1 === 0) { kt[4 * ie] = k11; kt[4 * ie + 1] = k12; kt[4 * ie + 2] = k22; }
        else {
          const a11 = el.f11[ie] * ifac + b0, a12 = el.f12[ie] * ifac, a22 = el.f22[ie] * ifac + b1;
          const dt2 = a11 * a22 - a12 * a12;
          kt[4 * ie] = a22 / dt2; kt[4 * ie + 1] = -a12 / dt2; kt[4 * ie + 2] = a11 / dt2;
        }
        kt[4 * ie + 3] = fac * kax;
        if (b0 !== sig[h0] || b1 !== sig[h1]) sucio = true;
        // fuerzas nodales aᵀ·Q (pasan al nudo a través de los brazos rígidos: M_nudo = M + V·d)
        for (let k = 0; k < 6; k++) FL[dof[o6 + k]] += A[o + k] * M0 + A[o + 6 + k] * M1 + A[o + 12 + k] * Nx;
      }
      P.sucio = sucio;
    }
  }

  /**
   * Factoriza los pórticos cuya tangente cambió (K_cc en banda, X = K_cc⁻¹·K_cd, K̂ = K_dd − K_dcᵀ·X) y devuelve
   * KfD = Σ Tᵀ·K̂·T (3N × 3N). Lanza si K_cc no es definida positiva (pórtico inestable con el diafragma fijo).
   */
  rigidezDiafragma(fac) {
    const mod = this.mod, el = mod.el, kt = this.kt, A = el.A, dof = el.dof, nd = mod.nd;
    let cambio = !this.KfDvalida;
    const B = new Float64Array(18), K6 = new Float64Array(36);
    for (const P of mod.porticos) {
      if (!P.sucio && P.fac === fac) continue;
      cambio = true;
      const { nl, nc, w, n } = P, s = w + 1;
      P.Kdd.fill(0); P.Kcd.fill(0); P.Kcc.fill(0);
      for (let ie = P.e0; ie < P.e1; ie++) {
        const o = 18 * ie, o6 = 6 * ie;
        const a11 = kt[4 * ie], a12 = kt[4 * ie + 1], a22 = kt[4 * ie + 2], ax = kt[4 * ie + 3];
        for (let k = 0; k < 6; k++) {
          B[k] = a11 * A[o + k] + a12 * A[o + 6 + k];
          B[6 + k] = a12 * A[o + k] + a22 * A[o + 6 + k];
          B[12 + k] = ax * A[o + 12 + k];
        }
        for (let a = 0; a < 6; a++) for (let b = 0; b < 6; b++) K6[6 * a + b] = A[o + a] * B[b] + A[o + 6 + a] * B[6 + b] + A[o + 12 + a] * B[12 + b];
        for (let a = 0; a < 6; a++) {
          const ia = dof[o6 + a];
          if (ia >= n) continue;
          for (let b = 0; b < 6; b++) {
            const ib = dof[o6 + b];
            if (ib >= n) continue;
            const k = K6[6 * a + b];
            if (k === 0) continue;
            if (ia < nl) { if (ib < nl) P.Kdd[ia * nl + ib] += k; }
            else if (ib < nl) P.Kcd[(ia - nl) * nl + ib] += k;
            else { const ca = ia - nl, cb = ib - nl; if (cb <= ca) P.Kcc[ca * s + (cb - ca + w)] += k; }
          }
        }
        this.sig[2 * ie] = this.bT[2 * ie]; this.sig[2 * ie + 1] = this.bT[2 * ie + 1];
      }
      if (nc > 0) {
        if (!choleskyBanda(P.Kcc, nc, w)) throw new ErrorMotor('interno', `pórtico ${P.id}: rigidez de los grados condensados no es definida positiva`, { portico: P.id });
        for (let j = 0; j < nl; j++) {
          const col = P.col;
          for (let i = 0; i < nc; i++) col[i] = P.Kcd[i * nl + j];
          resolverBanda(P.Kcc, nc, w, col);
          for (let i = 0; i < nc; i++) P.X[i * nl + j] = col[i];
        }
      }
      for (let a = 0; a < nl; a++) for (let b = 0; b < nl; b++) {
        let s2 = P.Kdd[a * nl + b];
        for (let i = 0; i < nc; i++) s2 -= P.Kcd[i * nl + a] * P.X[i * nl + b];
        P.Khat[a * nl + b] = s2;
      }
      P.sucio = false;
      P.fac = fac;
    }
    if (cambio) {
      const K = this.KfD;
      K.fill(0);
      for (const P of mod.porticos) {
        const nl = P.nl;
        for (let a = 0; a < nl; a++) {
          const ta = P.latT[a], ra = P.latR[a], ca = P.latC[a];
          for (let b = 0; b < nl; b++) {
            const k = P.Khat[a * nl + b];
            const tb = P.latT[b], rb = P.latR[b], cb = P.latC[b];
            K[ta * nd + tb] += k; K[ta * nd + rb] += k * cb; K[ra * nd + tb] += ca * k; K[ra * nd + rb] += ca * k * cb;
          }
        }
      }
      this.KfDvalida = true;
    }
    return this.KfD;
  }

  /** Fuerza interna de los pórticos en los gdl del diafragma: Fd += Σ Tᵀ·F_d. */
  fuerzaDiafragma(Fd) {
    for (const P of this.mod.porticos) {
      for (let l = 0; l < P.nl; l++) { const f = P.Floc[l]; Fd[P.latT[l]] += f; Fd[P.latR[l]] += P.latC[l] * f; }
    }
    return Fd;
  }

  /**
   * Residuo condensado de los pórticos: R̂ += Σ Tᵀ·(−F_d − K_dcᵀ·y) con y = K_cc⁻¹·R_c y R_c = λ·Pg − F_c (sin −F_d si
   * incluirF es false: el integrador ya lo restó al armar el residuo sin condensar). Guarda y en cada pórtico (para
   * recuperar Δu_c) y devuelve ‖R_c‖∞. Requiere rigidezDiafragma() antes.
   */
  residuoCondensado(Rd, lambda = 1, incluirF = true, omitir = 0) {
    const mod = this.mod, Pg = mod.Pg;
    let nR = 0;
    for (const P of mod.porticos) {
      const { nl, nc, w } = P, y = P.y;
      let nP = 0;
      for (let i = 0; i < nc; i++) {
        const r = lambda * Pg[P.offC + i] - P.Floc[nl + i];
        y[i] = r;
        const a = r < 0 ? -r : r;
        if (a > nP) nP = a;
      }
      if (nP > nR) nR = nP;
      // pórtico ya en equilibrio (residuo por debajo de `omitir`, una fracción de la tolerancia): su corrección
      // K_cc⁻¹·R_c es despreciable y no se calcula
      P.yCero = nP <= omitir;
      if (P.yCero) { if (incluirF) for (let l = 0; l < nl; l++) { const r = -P.Floc[l]; Rd[P.latT[l]] += r; Rd[P.latR[l]] += P.latC[l] * r; } continue; }
      if (nc > 0) resolverBanda(P.Kcc, nc, w, y);
      for (let l = 0; l < nl; l++) {
        let r = incluirF ? -P.Floc[l] : 0;
        for (let i = 0; i < nc; i++) r -= P.Kcd[i * nl + l] * y[i];
        Rd[P.latT[l]] += r; Rd[P.latR[l]] += P.latC[l] * r;
      }
    }
    return nR;
  }

  /**
   * Predicción de los condensados al empezar un paso: Δc = −X·(T·Δu_d) con la X de la última factorización. Un
   * pórtico que sigue elástico queda así en equilibrio (K_cc·Δc + K_cd·Δd = 0, también con el amortiguamiento
   * proporcional de su parte elástica) y su solución en banda se omite en la iteración.
   */
  predecirCondensados(duD, uC) {
    for (const P of this.mod.porticos) {
      const { nl, nc } = P;
      if (!(P.fac === P.fac)) continue;                  // pórtico sin factorizar todavía
      for (let i = 0; i < nc; i++) {
        let v = 0;
        for (let l = 0; l < nl; l++) v -= P.X[i * nl + l] * (duD[P.latT[l]] + P.latC[l] * duD[P.latR[l]]);
        uC[P.offC + i] += v;
      }
    }
  }

  /** Δu_c de cada pórtico: Δc = y − X·(T·Δu_d). Devuelve ‖Δu_c‖∞. */
  recuperar(duD, duC) {
    let m = 0;
    for (const P of this.mod.porticos) {
      const { nl, nc } = P;
      const yc = P.yCero;
      for (let i = 0; i < nc; i++) {
        let v = yc ? 0 : P.y[i];
        for (let l = 0; l < nl; l++) v -= P.X[i * nl + l] * (duD[P.latT[l]] + P.latC[l] * duD[P.latR[l]]);
        duC[P.offC + i] = v;
        const a = v < 0 ? -v : v;
        if (a > m) m = a;
      }
    }
    return m;
  }

  /**
   * Compromete el estado de prueba. dt = 0 en estática. Devuelve los incrementos de energía del paso por la regla del
   * trapecio: { hist: Σ ∫M dθp, amort: Σ ∫(a1·K_e·ė)ᵀ de + ∫(a1·kax·δ̇) dδ }. Si se da Dd (3N), deja ahí la fuerza de
   * amortiguamiento de los elementos en los gdl del diafragma (la usa el predictor del integrador).
   */
  comprometer(dt, a1, Dd = null) {
    const mod = this.mod, el = mod.el, nE = mod.nE, A = el.A, dof = el.dof;
    if (Dd) Dd.fill(0);
    const st = this.st, Q = this.Q, Qt = this.Qt, e = this.e, ed = this.ed, dl = this.dl, dld = this.dld;
    const c1 = dt > 0 ? 2 / dt : 0;
    let hist = 0, amort = 0;
    for (let ie = 0; ie < nE; ie++) {
      const h0 = 2 * ie, h1 = h0 + 1;
      const K11 = el.k11[ie], K12 = el.k12[ie], K22 = el.k22[ie], kax = el.kax[ie];
      // rótulas
      hist += (this.thpT[h0] - st[h0 * NE]) * (Qt[3 * ie] + Q[3 * ie]) * 0.5 + (this.thpT[h1] - st[h1 * NE]) * (Qt[3 * ie + 1] + Q[3 * ie + 1]) * 0.5;
      const cambia = this.thpT[h0] !== st[h0 * NE] || this.thpT[h1] !== st[h1 * NE] || el.rmod[h0] === CLOUGH || el.rmod[h1] === CLOUGH;
      actualizar(el.rmod[h0], st, h0 * NE, Qt[3 * ie], this.thpT[h0], this.tipoT[h0], st, h0 * NE);
      actualizar(el.rmod[h1], st, h1 * NE, Qt[3 * ie + 1], this.thpT[h1], this.tipoT[h1], st, h1 * NE);
      if (cambia) this._intervalos(h0, h1 + 1);
      this.thp[h0] = this.thpT[h0]; this.thp[h1] = this.thpT[h1];
      // parte elástica y su amortiguamiento (Newmark: ė_{n+1} = (2/Δt)·(e_{n+1} − e_n) − ė_n)
      const e0 = this.et[h0], e1 = this.et[h1], d2 = this.dlt[ie];
      let ed0 = 0, ed1 = 0, dd = 0;
      if (dt > 0) {
        ed0 = c1 * (e0 - e[h0]) - ed[h0]; ed1 = c1 * (e1 - e[h1]) - ed[h1]; dd = c1 * (d2 - dl[ie]) - dld[ie];
        if (a1 > 0) {
          const D0n = a1 * (K11 * ed[h0] + K12 * ed[h1]), D1n = a1 * (K12 * ed[h0] + K22 * ed[h1]);
          const D0 = a1 * (K11 * ed0 + K12 * ed1), D1 = a1 * (K12 * ed0 + K22 * ed1), Dax = a1 * kax * dd;
          amort += (e0 - e[h0]) * (D0n + D0) * 0.5 + (e1 - e[h1]) * (D1n + D1) * 0.5 + (d2 - dl[ie]) * a1 * kax * (dld[ie] + dd) * 0.5;
          if (Dd && el.tipo[ie] !== VIGA) {
            // solo los gdl laterales (k = 0 en i y k = 3 en j): las vigas no tienen componente lateral
            const P = mod.porticos[el.port[ie]], o = 18 * ie;
            const li = dof[6 * ie], lj = dof[6 * ie + 3];
            if (li < P.nl) { const f = A[o] * D0 + A[o + 6] * D1 + A[o + 12] * Dax; Dd[P.latT[li]] += f; Dd[P.latR[li]] += P.latC[li] * f; }
            if (lj < P.nl) { const f = A[o + 3] * D0 + A[o + 9] * D1 + A[o + 15] * Dax; Dd[P.latT[lj]] += f; Dd[P.latR[lj]] += P.latC[lj] * f; }
          }
        }
      }
      e[h0] = e0; e[h1] = e1; ed[h0] = ed0; ed[h1] = ed1; dl[ie] = d2; dld[ie] = dd;
      Q[3 * ie] = Qt[3 * ie]; Q[3 * ie + 1] = Qt[3 * ie + 1]; Q[3 * ie + 2] = Qt[3 * ie + 2];
    }
    return { hist, amort };
  }

  /** Energía de deformación de la parte elástica: Σ ½·eᵀK_e·e + ½·kax·δ² (estado comprometido). */
  energiaElastica() {
    const el = this.mod.el, e = this.e, dl = this.dl;
    let E = 0;
    for (let ie = 0; ie < this.mod.nE; ie++) {
      const a = e[2 * ie], b = e[2 * ie + 1];
      E += 0.5 * (el.k11[ie] * a * a + 2 * el.k12[ie] * a * b + el.k22[ie] * b * b) + 0.5 * el.kax[ie] * dl[ie] * dl[ie];
    }
    return E;
  }
}

// =================================================================================================================
// Mampostería sobre el diafragma
// =================================================================================================================
/** Estado de prueba de los muros para uD: fuerza, tangente y deriva; suma Fd += F·b y, si K, K += k·b·bᵀ. */
export function evaluarMuros(mod, uD, dmax, sal, Fd, K) {
  const nd = mod.nd, tmp = sal.tmp, muros = mod.muros;
  for (let i = 0; i < muros.length; i++) {
    const m = muros[i], ix = m.ix, bv = m.bv, nz = ix.length;
    let D = 0;
    for (let a = 0; a < nz; a++) D += bv[a] * uD[ix[a]];
    respuestaMuro(m.env, m.aislado, D, dmax[i], tmp);
    const F = tmp[0], k = tmp[1];
    sal.F[i] = F; sal.k[i] = k; sal.dmax[i] = tmp[2]; sal.D[i] = D;
    if (F !== 0 && Fd) for (let a = 0; a < nz; a++) Fd[ix[a]] += F * bv[a];
    if (k !== 0 && K) for (let a = 0; a < nz; a++) for (let c = 0; c < nz; c++) K[ix[a] * nd + ix[c]] += k * bv[a] * bv[c];
  }
}

export function cajaMuros(mod) {
  const n = mod.muros.length;
  return { F: new Float64Array(n), k: new Float64Array(n), dmax: new Float64Array(n), D: new Float64Array(n), tmp: new Float64Array(3) };
}

// =================================================================================================================
// Gravedad
// =================================================================================================================
/**
 * Análisis estático no lineal de gravedad (E4): w_gravedad de las vigas y carga_kN de los nodos en 5 incrementos
 * iguales con Newton-Raphson completo (P-Delta y mampostería incluidos). El dinámico parte de este estado.
 * → EstadoInicial { uD, uC, nucleo (copia del estado de los elementos), dmaxMuros, FmMuros, Q, iteraciones }
 */
export function gravedad(mod, { incrementos = 5, tolerancia = 1e-6, max_iter = 30 } = {}) {
  if (mod._cache.gravedad) return mod._cache.gravedad;
  const { nd, ncTot } = mod, nuc = mod.nucleo;
  const uD = new Float64Array(nd), uC = new Float64Array(ncTot);
  const duD = new Float64Array(nd), duC = new Float64Array(ncTot), Rd = new Float64Array(nd), Fd = new Float64Array(nd);
  const K = new Float64Array(nd * nd), piv = new Int32Array(nd), tmp = new Float64Array(nd);
  const mur = cajaMuros(mod), dmax = new Float64Array(mod.muros.length);
  let iterTot = 0;
  let PgMax = 0;
  for (const x of mod.Pg) PgMax = Math.max(PgMax, Math.abs(x));
  for (let inc = 1; inc <= incrementos; inc++) {
    const lambda = inc / incrementos;
    let conv = false;
    for (let it = 1; it <= max_iter; it++) {
      iterTot++;
      nuc.evaluar(uD, uC, 1, 0, 0);
      K.set(nuc.rigidezDiafragma(1));
      // residuo sin condensar en el diafragma (no hay cargas laterales): R_d = −F_pórticos − F_mampostería − K_PΔ·u
      Fd.fill(0);
      nuc.fuerzaDiafragma(Fd);
      evaluarMuros(mod, uD, dmax, mur, Fd, K);
      let nR = 0;
      for (let a = 0; a < nd; a++) {
        let s = 0;
        for (let c = 0; c < nd; c++) { s += mod.Kpd[a * nd + c] * uD[c]; K[a * nd + c] += mod.Kpd[a * nd + c]; }
        Rd[a] = -Fd[a] - s;
        nR = Math.max(nR, Math.abs(Rd[a]));
      }
      // condensado: R̂_d = R_d − K_dc·K_cc⁻¹·R_c, con R_c = λ·Pg − F_c en los v y θ de los pórticos
      nR = Math.max(nR, nuc.residuoCondensado(Rd, lambda, false));
      if (!factorLU(K, nd, piv)) throw new ErrorMotor('datos', 'la estructura es inestable ante las cargas de gravedad (rigidez lateral singular)');
      resolverLU(K, nd, piv, Rd, duD, tmp);
      const mC = nuc.recuperar(duD, duC);
      let mD = 0;
      for (let a = 0; a < nd; a++) mD = Math.max(mD, Math.abs(duD[a]));
      if (nR <= tolerancia * Math.max(lambda * PgMax, 1) && Math.max(mD, mC) <= 1e-9) { conv = true; break; }
      for (let a = 0; a < nd; a++) uD[a] += duD[a];
      for (let a = 0; a < ncTot; a++) uC[a] += duC[a];
    }
    if (!conv) throw new ErrorMotor('no_converge', `la gravedad no convergió en el incremento ${inc}`);
    nuc.comprometer(0, 0);
    dmax.set(mur.dmax);
  }
  // fuerzas finales (estado comprometido) y mampostería
  nuc.evaluar(uD, uC, 1, 0, 0);
  evaluarMuros(mod, uD, dmax, mur, null, null);
  const elementos = nuc.guardar();
  const momentos = new Float64Array(2 * mod.nE), axiales = new Float64Array(mod.nE);
  for (let ie = 0; ie < mod.nE; ie++) { momentos[2 * ie] = elementos.Q[3 * ie]; momentos[2 * ie + 1] = elementos.Q[3 * ie + 1]; axiales[ie] = elementos.Q[3 * ie + 2]; }
  // EstadoInicial del 7.4: desplazamientos u_g (diafragma uD y condensados uC), momentos de extremo (Mi, Mj) y axiales
  const g = {
    uD, uC, u_g: uD, momentos, axiales, elementos, dmaxMuros: dmax.slice(), FmMuros: mur.F.slice(), DMuros: mur.D.slice(), iteraciones: iterTot,
  };
  mod._cache.gravedad = g;
  return g;
}


// =================================================================================================================
// Rigidez lateral, P-Delta, modos y amortiguamiento
// =================================================================================================================
/**
 * Rigidez lateral condensada (3N × 3N) de los pórticos y la mampostería, sin P-Delta, con la tangente del estado
 * dado (por defecto, el de gravedad: la rigidez inicial). estado: { uD, uC } opcional.
 * conMuros = false deja solo los pórticos (la parte que amortigua con a1).
 */
export function rigidezLateral(mod, estado, { conMuros = true } = {}) {
  const g = gravedad(mod);
  const nuc = mod.nucleo;
  const s = estado ?? g;
  nuc.evaluar(s.uD, s.uC, 1, 0, 0);
  const K = Float64Array.from(nuc.rigidezDiafragma(1));
  if (conMuros) evaluarMuros(mod, s.uD, g.dmaxMuros, cajaMuros(mod), null, K);
  return K;
}

/** K_PΔ del 7.4 (3N × 3N, constante; copia). */
export function rigidezPDelta(mod) {
  return Float64Array.from(mod.Kpd);
}

/**
 * Modos con la rigidez inicial (pórticos + mampostería + K_PΔ) y la masa del diafragma: K·φ = ω²·M·φ, resuelto como
 * M^(−½)·K·M^(−½) simétrica (Jacobi). Formas normalizadas con φᵀMφ = 1 y la componente de mayor valor absoluto
 * positiva. Masa participativa Γ²/M_total en x, y y rz (Γ = φᵀ·M·ι). T1x y T1y: períodos de mayor masa
 * participativa en x y en y.
 */
export function modos(mod, n = 12) {
  const clave = `modos${n}`;
  if (mod._cache[clave]) return mod._cache[clave];
  const nd = mod.nd, m = mod.masa;
  const K = rigidezLateral(mod);
  for (let i = 0; i < nd * nd; i++) K[i] += mod.Kpd[i];
  const r = modosDe(K, m, nd, Math.min(n, nd));
  mod._cache[clave] = r;
  return r;
}

/** Modos de (K, M diagonal) — también para las pruebas con matrices armadas a mano. */
export function modosDe(K, m, nd, n = nd) {
  const S = new Float64Array(nd * nd);
  for (let a = 0; a < nd; a++) for (let c = 0; c < nd; c++) S[a * nd + c] = (0.5 * (K[a * nd + c] + K[c * nd + a])) / Math.sqrt(m[a] * m[c]);
  const { valores, vectores } = jacobiSimetrico(S, nd);
  const orden = [...valores.keys()].sort((a, b) => valores[a] - valores[b]);
  if (valores[orden[0]] <= 0) throw new ErrorMotor('datos', 'la rigidez lateral inicial no es definida positiva (inestable por P-Delta o mal armada)');
  const periodos = [], omega = [], formas = [];
  const part = { x: [], y: [], rz: [] }, fact = { x: [], y: [], rz: [] };
  let Mx = 0, My = 0, Mr = 0;
  for (let a = 0; a < nd; a += 3) { Mx += m[a]; My += m[a + 1]; Mr += m[a + 2]; }
  for (let r = 0; r < n; r++) {
    const c = orden[r];
    const phi = new Float64Array(nd);
    let k = 0;
    for (let a = 0; a < nd; a++) { phi[a] = vectores[a * nd + c] / Math.sqrt(m[a]); if (Math.abs(phi[a]) > Math.abs(phi[k])) k = a; }
    if (phi[k] < 0) for (let a = 0; a < nd; a++) phi[a] = -phi[a];
    const w = Math.sqrt(valores[c]);
    omega.push(w); periodos.push((2 * Math.PI) / w); formas.push(phi);
    let gx = 0, gy = 0, gr = 0;
    for (let a = 0; a < nd; a += 3) { gx += m[a] * phi[a]; gy += m[a + 1] * phi[a + 1]; gr += m[a + 2] * phi[a + 2]; }
    fact.x.push(gx); fact.y.push(gy); fact.rz.push(gr);
    part.x.push((gx * gx) / Mx); part.y.push((gy * gy) / My); part.rz.push((gr * gr) / Mr);
  }
  const imax = (v) => v.reduce((b, x, i) => (x > v[b] ? i : b), 0);
  return { periodos_s: periodos, omega, formas, masa_participativa: part, factores: fact, T1x: periodos[imax(part.x)], T1y: periodos[imax(part.y)] };
}

/**
 * Amortiguamiento de Rayleigh de la parte elástica (E8), C = a0·M + a1·K_el: K_el es la rigidez condensada de la parte
 * elástica de los elementos, sin P-Delta y sin la mampostería (que no lleva amortiguamiento de Rayleigh, Charney 2008).
 *
 * Anclas (Ti, Tj):
 * - Las `periodos_ancla_s` del archivo describen el modelo con los muros de mampostería como dice el archivo (aislados
 *   o no, campo `aislado`). Solo valen si el modelo analizado tiene esos mismos muros: con `noEstructurales:
 *   'confinados'` y algún muro que en el archivo está aislado, el sistema dinámico es otro (en la torre, T1 baja de
 *   0,456 a 0,285 s) y el motor aplica la regla automática sobre los modos del modelo analizado (corrección al
 *   contrato, ESQUEMA.md «Amortiguamiento»).
 * - Regla automática (E8): Ti = T1 y Tj = el menor entre el período con el que la masa participativa acumulada llega a
 *   ≥ 90 % en x y en y y 0,2·T1.
 *
 * a0 y a1: ξ exacto en las dos anclas. Para el modo r (φ normalizado a la masa), ξ_r = (a0 + a1·k_r)/(2ω_r), con
 * k_r = φ_rᵀ·K_el·φ_r. La fórmula de siempre, a0 = 2ξωiωj/(ωi + ωj) y a1 = 2ξ/(ωi + ωj), supone k_r = ω_r², es decir,
 * que todo lo que da rigidez amortigua. No es así cuando la mampostería trabaja (en la torre «sin aislar» aporta ≈ 60 %
 * de la rigidez inicial y con la fórmula de siempre ξ1 quedaba en 3,2-4,6 %). Con ρ(ω) = k/ω² (fracción de la rigidez
 * modal que amortigua; ≈ 1 sin mampostería, un poco más de 1 por P-Delta), imponer ξ en ωi y ωj da el sistema 2 × 2
 *   a0 + a1·ρi·ωi² = 2ξ·ωi,   a0 + a1·ρj·ωj² = 2ξ·ωj
 *   → a1 = 2ξ·(ωj − ωi)/(ρj·ωj² − ρi·ωi²),   a0 = 2ξ·ωi − a1·ρi·ωi²
 * (con ρ = 1 vuelve a la fórmula de siempre). ρ en un ancla que no cae en un modo (0,2·T1) se interpola linealmente en
 * ln ω entre los dos modos vecinos (fuera de su rango, el del modo extremo).
 * ξ efectivo de los primeros min(12, 3N) modos: ξ_r = φ_rᵀ(a0·M + a1·K_el)φ_r/(2ω_r).
 */
export function amortiguamiento(mod) {
  if (mod._cache.amortiguamiento) return mod._cache.amortiguamiento;
  const am = mod.est.amortiguamiento || {};
  const xi = esNum(am.xi) ? am.xi : 0.05;
  const nd = mod.nd;
  const md = modos(mod, nd);
  const T = md.periodos_s;
  const KC = rigidezLateral(mod, undefined, { conMuros: false });
  // k_r = φ_rᵀ·K_el·φ_r de todos los modos (φᵀMφ = 1)
  const k = new Float64Array(nd);
  for (let r = 0; r < nd; r++) {
    const phi = md.formas[r];
    let c = 0;
    for (let a = 0; a < nd; a++) {
      let s = 0;
      for (let b = 0; b < nd; b++) s += KC[a * nd + b] * phi[b];
      c += phi[a] * s;
    }
    k[r] = c;
  }
  const murosCambiados = mod.muros.some((m) => m.aislado !== m.aisladoArchivo);
  let Ti, Tj, regla;
  if (Array.isArray(am.periodos_ancla_s) && am.periodos_ancla_s.length === 2 && !murosCambiados) {
    [Ti, Tj] = am.periodos_ancla_s; regla = 'periodos_ancla_s de la estructura';
  } else if (Array.isArray(am.modos) && am.modos.length === 2 && !murosCambiados) {
    Ti = T[am.modos[0] - 1]; Tj = T[am.modos[1] - 1]; regla = `modos ${am.modos.join(' y ')} de la estructura (forma anterior a E8)`;
  } else {
    let cx = 0, cy = 0, r90 = T.length - 1;
    for (let r = 0; r < T.length; r++) {
      cx += md.masa_participativa.x[r]; cy += md.masa_participativa.y[r];
      if (cx >= 0.9 && cy >= 0.9) { r90 = r; break; }
    }
    Ti = T[0]; Tj = Math.min(T[r90], 0.2 * T[0]);
    regla = `E8: Ti = T1; Tj = mín(T del modo ${r90 + 1}, con ≥ 90 % de masa en x y en y; 0,2·T1)` +
      (murosCambiados ? ' (con los muros de mampostería del escenario, no los del archivo: las anclas del archivo no valen)' : '');
  }
  // ρ(ω) = k/ω², interpolada en ln ω entre modos (ω crece con r)
  const rho = (w) => {
    const om = md.omega, n = om.length;
    if (w <= om[0]) return k[0] / (om[0] * om[0]);
    if (w >= om[n - 1]) return k[n - 1] / (om[n - 1] * om[n - 1]);
    let r = 1;
    while (om[r] < w) r++;
    const p0 = k[r - 1] / (om[r - 1] * om[r - 1]), p1 = k[r] / (om[r] * om[r]);
    const t = om[r] > om[r - 1] ? Math.log(w / om[r - 1]) / Math.log(om[r] / om[r - 1]) : 0;
    return p0 + t * (p1 - p0);
  };
  const wi = (2 * Math.PI) / Ti, wj = (2 * Math.PI) / Tj;
  const ri = rho(wi), rj = rho(wj);
  const a1 = (2 * xi * (wj - wi)) / (rj * wj * wj - ri * wi * wi);
  const a0 = 2 * xi * wi - a1 * ri * wi * wi;
  if (!(a0 >= 0 && a1 >= 0)) throw new ErrorMotor('interno', `amortiguamiento: a0 = ${a0}, a1 = ${a1} con las anclas ${Ti} y ${Tj} s`);
  const nx = Math.min(12, nd);
  const xi_modos = new Float64Array(nx);
  for (let r = 0; r < nx; r++) xi_modos[r] = (a0 + a1 * k[r]) / (2 * md.omega[r]);
  const r = { a0, a1, periodos_ancla_s: [Ti, Tj], xi_modos, xi, regla, rho_anclas: [ri, rj] };
  mod._cache.amortiguamiento = r;
  return r;
}

// =================================================================================================================
// Resumen, información para la vista y geometría
// =================================================================================================================
/**
 * Centro de rigidez del nivel k: punto donde una fuerza lateral aplicada solo en ese nivel no lo hace girar
 * (flexibilidad elástica condensada, sin P-Delta): y = yc + F[rz, ux]/F[rz, rz], x = xc − F[rz, uy]/F[rz, rz].
 */
export function centroRigidez(mod) {
  const nd = mod.nd;
  const F = inversa(rigidezLateral(mod), nd);
  const cr = [], exc = [];
  mod.niveles.forEach((nv, g) => {
    const b = 3 * g, frr = F[(b + 2) * nd + b + 2];
    const y = nv.yc + F[(b + 2) * nd + b] / frr;
    const x = nv.xc - F[(b + 2) * nd + b + 1] / frr;
    cr.push([x, y]); exc.push([x - nv.xc, y - nv.yc]);
  });
  return { centro_rigidez: cr, excentricidad: exc };
}

export function resumenModelo(mod) {
  const masa = mod.niveles.reduce((s, n) => s + n.masa, 0);
  const peso = mod.niveles.reduce((s, n) => s + n.peso, 0);
  const cm = [0, 1].map((c) => mod.niveles.reduce((s, n) => s + n.masa * (c ? n.yc : n.xc), 0) / masa);
  const { centro_rigidez, excentricidad } = centroRigidez(mod);
  return {
    niveles: mod.N, porticos: mod.nP, nodos: mod.nN, elementos: mod.nE, gdl_dinamicos: mod.nd, gdl_condensados: mod.ncTot,
    masa_total_t: masa, peso_kN: peso, cm, centro_rigidez, excentricidad,
    sistema: mod.est.sistema_estructural ?? mod.est.sistema?.tipo ?? null,
    sistema_detalle: mod.est.sistema ?? null,
    muros_mamposteria: mod.muros.length, p_delta: mod.op.pDelta,
    histeresis: mod.op.histeresis ?? 'la de cada sección', no_estructurales: mod.op.noEstructurales,
  };
}

/** Elementos para la vista: [{ id, tipo, portico, nivel, fisico, i, j, xyz_i, xyz_j, seccion }] en el orden del archivo. */
export function infoElementos(mod) {
  return mod.el.info.map((x) => ({ ...x, xyz_i: [...x.xyz_i], xyz_j: [...x.xyz_j] }));
}

/** Nodos para la vista: [{ id, portico, xyz }] en el orden del archivo. */
export function infoNodos(mod) {
  return mod.nodos.map((n) => ({ id: n.id, portico: n.portico, xyz: [...n.xyz] }));
}

/** Desplazamiento (x, y) de un punto (x, y) en el diafragma g (g = −1: el suelo, 0). */
export function puntoDiafragma(mod, u, g, x, y, out) {
  if (g < 0) { out[0] = 0; out[1] = 0; return out; }
  const nv = mod.niveles[g];
  out[0] = u[3 * g] - (y - nv.yc) * u[3 * g + 2];
  out[1] = u[3 * g + 1] + (x - nv.xc) * u[3 * g + 2];
  return out;
}

/**
 * Deriva vectorial (E9; NSR-10 A.6.3.1): en cada vértice (x, y) del contorno del nivel de arriba de cada entrepiso,
 *   Δ = √(Δx² + Δy²)/h,  Δx = [ux − (y − yc)·rz]_arriba − [ux − (y − yc)·rz]_abajo,  Δy = [uy + (x − xc)·rz]_arriba − …
 * con la cinemática de diafragma rígido de los dos niveles (el de abajo, con su propio centro de masa; el suelo no se
 * mueve). Escribe en `deriva` (N) el máximo por entrepiso y en `punto` (2N) el vértice donde ocurre (el primero en el
 * orden del contorno si hay empate). Lo usan el integrador en cada Δt y la prueba T22.
 */
export function derivaVectorial(mod, u, deriva, punto) {
  const niveles = mod.niveles;
  for (let g = 0; g < niveles.length; g++) {
    const nv = niveles[g], b = 3 * g, ab = nv.abajo, nb = ab >= 0 ? niveles[ab] : null, bb = 3 * ab;
    const ct = nv.contornoPlano;
    let m = -1, px = 0, py = 0;
    for (let q = 0; q < ct.length; q += 2) {
      const x = ct[q], y = ct[q + 1];
      let dx = u[b] - (y - nv.yc) * u[b + 2], dy = u[b + 1] + (x - nv.xc) * u[b + 2];
      if (nb) { dx -= u[bb] - (y - nb.yc) * u[bb + 2]; dy -= u[bb + 1] + (x - nb.xc) * u[bb + 2]; }
      const d = Math.sqrt(dx * dx + dy * dy) / nv.h;
      if (d > m) { m = d; px = x; py = y; }
    }
    deriva[g] = m; punto[2 * g] = px; punto[2 * g + 1] = py;
  }
  return deriva;
}
