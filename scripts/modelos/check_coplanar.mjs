// Control de calidad de los GLB: busca triángulos coplanares que se solapan (causa del parpadeo o
// "z-fighting") entre mallas o materiales distintos, y resume el costo de cada modelo (triángulos
// dibujados contando instancias, llamadas de dibujo y peso).
//
// Dos triángulos chocan si sus planos son paralelos (±2°), están a menos de --tol metros (1 cm por
// defecto) donde se solapan, el solape mide más de 4 cm² y 1 cm de ancho (los bordes que solo se tocan
// no cuentan) y ambos pueden verse a la vez: no cuentan las
// caras opuestas de materiales de una sola cara (la de atrás se descarta), las caras que miran hacia abajo
// apoyadas en el suelo (y < 5 cm) ni el par cubierta_actual reemplazada / capa adecuaciones, que la web nunca
// muestra juntas. Con color por vértice (COLOR_0), el mismo material con otro color cuenta como distinto.
//
// Uso: cd scripts/modelos && node check_coplanar.mjs [archivo.glb | carpeta ...] [--tol 0.01] [--max 12] [--mismo-material]
//      sin rutas revisa web/models/edificios/*.glb. Sale con código 1 si encuentra choques.
import { THREE, getIO } from './lib.mjs';
import { readdirSync, statSync } from 'node:fs';
import { join, resolve, basename } from 'node:path';
import { fileURLToPath } from 'node:url';

const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf(`--${k}`); return i >= 0 ? args[i + 1] : d; };
const TOL = +opt('tol', 0.01), MAX = +opt('max', 12), MISMO = args.includes('--mismo-material');
const COS = Math.cos((2 * Math.PI) / 180), MIN_AREA = 4e-4, MIN_WIDTH = 0.01, CELL = 2;
const paths = args.filter((a, i) => !a.startsWith('--') && !(i > 0 && ['--tol', '--max'].includes(args[i - 1])));
const HERE = fileURLToPath(new URL('.', import.meta.url));
const files = (paths.length ? paths : [join(HERE, '../../web/models/edificios')]).flatMap((p) => {
  const r = resolve(p);
  return statSync(r).isDirectory() ? readdirSync(r).filter((f) => f.endsWith('.glb')).sort().map((f) => join(r, f)) : [r];
});

// ---------- triángulos en coordenadas del modelo (con instancias GPU)
function collect(doc) {
  const owners = [], P = [], O = [], C = [];
  let drawCalls = 0, tris = 0;
  const visit = (node, parent, path, flags) => {
    const world = parent.clone().multiply(new THREE.Matrix4().fromArray(node.getMatrix()));
    const name = node.getName(), ex = node.getExtras() || {};
    const f = { ...flags };
    if (name === 'adecuaciones') f.adec = true;
    if (name === 'cubierta_actual' && ex.reemplazada) f.reemplazada = true;
    const p = `${path}/${name}`;
    const mesh = node.getMesh();
    if (mesh) {
      const inst = node.getExtension('EXT_mesh_gpu_instancing');
      let mats = [world];
      if (inst) {
        const T = inst.getAttribute('TRANSLATION'), R = inst.getAttribute('ROTATION'), S = inst.getAttribute('SCALE');
        const n = (T || R || S).getCount();
        mats = Array.from({ length: n }, (_, i) => {
          const t = T ? T.getElement(i, []) : [0, 0, 0], r = R ? R.getElement(i, []) : [0, 0, 0, 1], s = S ? S.getElement(i, []) : [1, 1, 1];
          return world.clone().multiply(new THREE.Matrix4().compose(new THREE.Vector3(...t), new THREE.Quaternion(...r), new THREE.Vector3(...s)));
        });
      }
      mesh.listPrimitives().forEach((prim, k) => {
        const pos = prim.getAttribute('POSITION'), idx = prim.getIndices(), mat = prim.getMaterial(), col = prim.getAttribute('COLOR_0');
        if (!pos) return;
        const oi = owners.length;
        owners.push({ path: p, prim: k, mat: mat?.getName() || '(sin material)', ds: !!mat?.getDoubleSided(), ...f });
        const a = pos.getArray(), ix = idx ? idx.getArray() : Array.from({ length: pos.getCount() }, (_, i) => i);
        drawCalls++; tris += (ix.length / 3) * mats.length;
        const v = new THREE.Vector3();
        for (const m of mats) {
          const w = new Float64Array(pos.getCount() * 3);
          for (let i = 0; i < pos.getCount(); i++) { v.set(a[3 * i], a[3 * i + 1], a[3 * i + 2]).applyMatrix4(m); w[3 * i] = v.x; w[3 * i + 1] = v.y; w[3 * i + 2] = v.z; }
          for (let t = 0; t < ix.length; t += 3) {
            for (const j of [ix[t], ix[t + 1], ix[t + 2]]) P.push(w[3 * j], w[3 * j + 1], w[3 * j + 2]);
            O.push(oi); C.push(col ? col.getElement(ix[t], []).slice(0, 3).map((x) => Math.round(x * 255)).join(',') : '');
          }
        }
      });
    }
    for (const c of node.listChildren()) visit(c, world, p, f);
  };
  for (const s of doc.getRoot().listScenes()) for (const n of s.listChildren()) visit(n, new THREE.Matrix4(), '', {});
  return { owners, P: Float64Array.from(P), O: Int32Array.from(O), C, drawCalls, tris };
}

// ---------- geometría
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const norm = (a) => { const l = Math.hypot(...a) || 1; return [a[0] / l, a[1] / l, a[2] / l]; };
function clip(poly, A) { // Sutherland–Hodgman contra el triángulo convexo A (antihorario)
  let out = poly;
  for (let i = 0; i < 3 && out.length; i++) {
    const p = A[i], q = A[(i + 1) % 3], inp = out; out = [];
    const side = (r) => (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]);
    for (let j = 0; j < inp.length; j++) {
      const r = inp[j], s = inp[(j + 1) % inp.length], sr = side(r), ss = side(s);
      if (sr >= 0) out.push(r);
      if ((sr >= 0) !== (ss >= 0)) { const t = sr / (sr - ss); out.push([r[0] + t * (s[0] - r[0]), r[1] + t * (s[1] - r[1])]); }
    }
  }
  return out;
}
const area2 = (p) => { let s = 0; for (let i = 0; i < p.length; i++) { const a = p[i], b = p[(i + 1) % p.length]; s += a[0] * b[1] - b[0] * a[1]; } return s / 2; };

function check(file, doc) {
  const { owners, P, O, C, drawCalls, tris } = collect(doc);
  const N = O.length, V = (t, k) => [P[9 * t + 3 * k], P[9 * t + 3 * k + 1], P[9 * t + 3 * k + 2]];
  const nrm = new Float64Array(3 * N), dd = new Float64Array(N), box = new Float64Array(6 * N), ok = new Uint8Array(N);
  for (let t = 0; t < N; t++) {
    const a = V(t, 0), b = V(t, 1), c = V(t, 2), cr = cross(sub(b, a), sub(c, a)), l = Math.hypot(...cr);
    if (l < 1e-8) continue; // degenerado
    if (cr[1] / l < -0.99 && Math.max(a[1], b[1], c[1]) < 0.05) continue; // cara inferior apoyada en el suelo
    ok[t] = 1; nrm.set([cr[0] / l, cr[1] / l, cr[2] / l], 3 * t); dd[t] = (cr[0] * a[0] + cr[1] * a[1] + cr[2] * a[2]) / l;
    for (let k = 0; k < 3; k++) { box[6 * t + k] = Math.min(a[k], b[k], c[k]) - TOL; box[6 * t + 3 + k] = Math.max(a[k], b[k], c[k]) + TOL; }
  }
  // rejilla espacial de 2 m
  const K = 8192, H = K / 2, key = (x, y, z) => ((x + H) * K + (y + H)) * K + (z + H), cells = new Map();
  for (let t = 0; t < N; t++) {
    if (!ok[t]) continue;
    const lo = [0, 1, 2].map((k) => Math.floor(box[6 * t + k] / CELL)), hi = [0, 1, 2].map((k) => Math.floor(box[6 * t + 3 + k] / CELL));
    for (let x = lo[0]; x <= hi[0]; x++) for (let y = lo[1]; y <= hi[1]; y++) for (let z = lo[2]; z <= hi[2]; z++) {
      const kk = key(x, y, z); let l = cells.get(kk); if (!l) cells.set(kk, (l = [])); l.push(t);
    }
  }
  const pairs = new Map();
  for (const [kk, list] of cells) {
    if (list.length < 2) continue;
    for (let i = 0; i < list.length; i++) {
      const A = list[i], oa = owners[O[A]], nA = [nrm[3 * A], nrm[3 * A + 1], nrm[3 * A + 2]];
      for (let j = i + 1; j < list.length; j++) {
        const B = list[j]; if (O[A] === O[B] && C[A] === C[B]) continue;
        const ob = owners[O[B]];
        if (!MISMO && oa.mat === ob.mat && C[A] === C[B]) continue;
        if ((oa.reemplazada && ob.adec) || (ob.reemplazada && oa.adec)) continue;
        const nB = [nrm[3 * B], nrm[3 * B + 1], nrm[3 * B + 2]], c = dot(nA, nB);
        if (Math.abs(c) < COS) continue;
        if (c < 0 && !oa.ds && !ob.ds) continue;
        let inter = true; const mn = [];
        for (let k = 0; k < 3; k++) { const lo = Math.max(box[6 * A + k], box[6 * B + k]), hi = Math.min(box[6 * A + 3 + k], box[6 * B + 3 + k]); if (lo > hi) { inter = false; break; } mn.push(lo); }
        if (!inter || key(...mn.map((x) => Math.floor(x / CELL))) !== kk) continue; // el par se evalúa una sola vez
        // proyección al plano de A y recorte
        const a0 = V(A, 0), u = norm(sub(V(A, 1), a0)), w = cross(nA, u);
        const to2 = (p) => { const d = sub(p, a0); return [dot(d, u), dot(d, w)]; };
        const TA = [0, 1, 2].map((k) => to2(V(A, k))); if (area2(TA) < 0) TA.reverse();
        const ov = clip([0, 1, 2].map((k) => to2(V(B, k))), TA);
        if (ov.length < 3) continue;
        const ar = Math.abs(area2(ov)); if (ar < MIN_AREA) continue;
        let per = 0; for (let k = 0; k < ov.length; k++) per += Math.hypot(ov[k][0] - ov[(k + 1) % ov.length][0], ov[k][1] - ov[(k + 1) % ov.length][1]);
        if ((2 * ar) / per < MIN_WIDTH) continue; // tira más angosta que 1 cm: bordes que se tocan
        let far = 0;
        for (const [x, y] of ov) { const X = [a0[0] + u[0] * x + w[0] * y, a0[1] + u[1] * x + w[1] * y, a0[2] + u[2] * x + w[2] * y]; far = Math.max(far, Math.abs((dd[B] - dot(nB, X)) / c)); }
        if (far > TOL) continue;
        const tag = (o, c) => `${o.path} [${o.mat}${c ? ` rgb(${c})` : ''}]`;
        const pk = [tag(oa, C[A]), tag(ob, C[B])].sort().join('  ×  ');
        const e = pairs.get(pk) || { n: 0, area: 0, at: null, sep: 0 };
        e.n++; e.area += ar; e.sep = Math.max(e.sep, far); if (!e.at) { const q = [a0[0] + u[0] * ov[0][0] + w[0] * ov[0][1], a0[1] + u[1] * ov[0][0] + w[1] * ov[0][1], a0[2] + u[2] * ov[0][0] + w[2] * ov[0][1]]; e.at = q.map((x) => +x.toFixed(2)); e.nrm = nA.map((x) => +x.toFixed(2)); if (process.env.TRI) e.tri = [A, B].map((t) => [0, 1, 2].map((k) => V(t, k).map((x) => +x.toFixed(3)).join(' ')).join(' | ')); }
        pairs.set(pk, e);
      }
    }
  }
  return { pairs, drawCalls, tris: Math.round(tris), owners: owners.length };
}

const io = await getIO();
let total = 0;
console.log(`tolerancia ${TOL * 100} cm · solape mínimo ${MIN_AREA * 1e4} cm²${MISMO ? ' · incluye pares del mismo material' : ''}`);
for (const f of files) {
  const doc = await io.read(f), bytes = statSync(f).size;
  const r = check(f, doc), list = [...r.pairs].sort((a, b) => b[1].area - a[1].area);
  total += list.length;
  console.log(`${basename(f).padEnd(24)} ${String(r.tris).padStart(7)} triángulos · ${String(r.drawCalls).padStart(3)} llamadas · ${(bytes / 1024).toFixed(0).padStart(5)} KB · ${list.length ? `${list.length} pares coplanares` : 'sin coplanares'}`);
  for (const [k, e] of list.slice(0, MAX)) console.log(`   ${e.area.toFixed(2).padStart(8)} m² · ${String(e.n).padStart(4)} triángulos · sep ≤ ${(e.sep * 100).toFixed(1)} cm · en ${e.at.join(', ')} n ${e.nrm.join(',')} · ${k}`);
  if (process.env.TRI) for (const [, e] of list.slice(0, MAX)) console.log('      A: ' + e.tri[0] + '\n      B: ' + e.tri[1]);
  if (list.length > MAX) console.log(`   … y ${list.length - MAX} pares más`);
}
process.exit(total ? 1 : 0);
