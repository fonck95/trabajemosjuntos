// Genera los modelos GLB del atlas y los optimiza como se haría con modelos profesionales:
// geometría agrupada por material, instancias GPU (EXT_mesh_gpu_instancing) para elementos
// repetidos, deduplicación, soldado de vértices, compresión Draco y textura PNG para el detalle
// fino (celdas solares) en vez de geometría. Salida: web/models/*.glb + manifest.json
//
// Uso: cd scripts/modelos && npm install && npm run build
import { THREE, Part, Builder, baseMaterials as materials, pvMesh, pvArray, bessPart, writeGLB } from './lib.mjs';
import { writeFileSync } from 'node:fs';

const OUT = new URL('../../web/models/', import.meta.url);

// ---------- hospital (misma huella que la escena: bloque de 18 × 10 m, dos pisos)
function buildHospital(detail) {
  const b = new Builder(detail ? 'hospital_lod0' : 'hospital_lod1');
  materials(b);
  const root = b.node('E.S.E. Hospital Héctor Abad Gómez', null);
  const pv = pvMesh(b);
  const p = new Part();
  // plataforma y bloque de hospitalización
  p.box('concreto_oscuro', 46, 0.15, 30, 0, 0, 2);
  p.box('concreto', 18, 6, 10, 0, 0.15, 0);
  p.box('concreto_oscuro', 18.3, 0.25, 10.3, 0, 3.05, 0);
  p.box('cubierta', 18, 0.3, 10, 0, 6.15, 0);
  for (const [w, d, x, z] of [[18.3, 0.2, 0, 5.05], [18.3, 0.2, 0, -5.05], [0.2, 10.3, 9.05, 0], [0.2, 10.3, -9.05, 0]]) p.box('concreto', w, 0.7, d, x, 6.15, z);
  // ventanas: vidrio + marcos de aluminio en fachadas norte y sur
  const win = (cx, y, z, nz, w = 1.5, h = 1.3) => {
    p.box('vidrio', w, h, 0.06, cx, y, z + nz * 0.01);
    if (detail) {
      const f = 0.07, zz = z + nz * 0.05;
      p.box('aluminio', w + f * 2, f, 0.1, cx, y - f, zz).box('aluminio', w + f * 2, f, 0.1, cx, y + h, zz);
      p.box('aluminio', f, h, 0.1, cx - w / 2 - f / 2, y, zz).box('aluminio', f, h, 0.1, cx + w / 2 + f / 2, y, zz);
      p.box('aluminio', f * 0.6, h, 0.08, cx, y, zz);
      p.box('concreto_oscuro', w + 0.3, 0.08, 0.35, cx, y - 0.12, z + nz * 0.15);
    }
  };
  for (let i = 0; i < 8; i++) for (const y of [1.1, 4.0]) { win(-7.7 + i * 2.2, y, 5, 1); win(-7.7 + i * 2.2, y, -5, -1); }
  if (!detail) { p.box('vidrio', 17, 1.3, 0.06, 0, 1.1, 5.01).box('vidrio', 17, 1.3, 0.06, 0, 4.0, 5.01); }
  // acceso principal con marquesina y letrero
  p.box('concreto', 6, 0.3, 3, 0, 3.0, 6.5);
  for (const x of [-2.6, 2.6]) p.cyl('aluminio', 0.12, 3.0, x, 0, 7.8, 12);
  p.box('vidrio', 3.2, 2.6, 0.08, 0, 0.15, 5.05);
  p.box('blanco', 2.2, 1.6, 0.12, 0, 6.6, 5.1);
  p.box('rojo', 0.35, 1.2, 0.08, -0.55, 6.8, 5.18).box('rojo', 0.35, 1.2, 0.08, 0.55, 6.8, 5.18).box('rojo', 0.75, 0.3, 0.08, 0, 7.25, 5.18);
  // urgencias con bahía de ambulancias
  p.box('concreto', 8, 3.6, 7, 13, 0.15, 1.5).box('cubierta', 8, 0.25, 7, 13, 3.75, 1.5);
  p.box('rojo', 8.02, 0.35, 7.02, 13, 3.1, 1.5);
  p.box('concreto', 6, 0.3, 4, 13, 3.3, 7);
  if (detail) for (const x of [10.5, 15.5]) p.cyl('aluminio', 0.12, 3.3, x, 0, 8.6, 12);
  for (let i = 0; i < 3; i++) win(10.5 + i * 2.4, 1.3, 5.0, 1, 1.4, 1.1);
  // consulta externa y servicios
  p.box('concreto', 9, 3.6, 7, -13.5, 0.15, -1).box('cubierta', 9, 0.25, 7, -13.5, 3.75, -1);
  for (let i = 0; i < 3; i++) win(-16.5 + i * 3, 1.3, 2.5, 1, 1.6, 1.1);
  p.box('concreto', 6, 3, 5, 4, 0.15, -9).box('cubierta', 6, 0.2, 5, 4, 3.15, -9);
  if (detail) for (let i = 0; i < 8; i++) p.box('aluminio', 4.5, 0.05, 0.12, 4, 0.8 + i * 0.25, -11.55);
  // equipos de cubierta
  if (detail) for (const [x, z] of [[-6, -3], [-3, -3], [5, -3], [8, -3]]) {
    p.box('aluminio', 1.6, 1.0, 1.2, x, 6.45, z);
    p.cyl('acero', 0.45, 0.06, x, 7.45, z, 24);
  }
  // marquesina del parqueadero: estructura de acero
  const cpZ = 14.5;
  for (const x of [-8, -2.7, 2.7, 8]) { p.cyl('acero', 0.12, 2.6, x, 0.15, cpZ - 2, 10); p.cyl('acero', 0.12, 3.1, x, 0.15, cpZ + 2, 10); }
  p.box('acero', 18, 0.15, 0.2, 0, 2.75, cpZ - 2).box('acero', 18, 0.15, 0.2, 0, 3.25, cpZ + 2);
  // planta de respaldo y mástil de conectividad
  p.box('generador', 3.4, 2.1, 1.9, -12, 0.15, -8).box('acero', 0.3, 1.3, 0.3, -10.8, 2.25, -8);
  p.cyl('acero', 0.12, 10, 8.5, 6.45, -3.5, 10);
  if (detail) { p.add('aluminio', new THREE.SphereGeometry(0.9, 24, 12, 0, Math.PI * 2, 0, Math.PI / 2.4), [8.5, 15.5, -3.5], [-Math.PI / 2.4, 0, 0]); }
  b.node('edificio', b.partMesh('edificio', p), [0, 0, 0], [0, 0, 0], [1, 1, 1], root);
  // baterías: contenedor de 20 pies
  b.node('BESS_400kWh', b.partMesh('contenedor_bess', bessPart(detail)), [-12, 0.15, 9], [0, 0, 0], [1.25, 1, 1], root);
  // solar: cubierta (60 kWp) + marquesina (40 kWp) con módulos de 550 Wp
  if (detail) {
    const roofPV = b.node('solar_cubierta', null, [0, 0, 0], [0, 0, 0], [1, 1, 1], root);
    pvArray(b, pv, roofPV, 14, 4, [0, 6.75, 0.2]);
    pvArray(b, pv, roofPV, 6, 3, [13, 4.15, 1.2]);
    const cp = b.node('solar_marquesina', null, [0, 0, 0], [0, 0, 0], [1, 1, 1], root);
    pvArray(b, pv, cp, 16, 2, [0, 3.35, cpZ], 0.12);
  } else {
    const low = new Part().box('celdas', 16, 0.08, 8.5, 0, 6.75, 0.2).box('celdas', 18, 0.08, 4.6, 0, 3.3, cpZ);
    b.node('solar_simplificada', b.partMesh('solar_simplificada', low), [0, 0, 0], [0, 0, 0], [1, 1, 1], root);
  }
  return b;
}

function buildBESS() {
  const b = new Builder('contenedor_bess'); materials(b);
  b.node('Contenedor BESS 20 pies', b.partMesh('contenedor_bess', bessPart(true)));
  return b;
}
function buildPV() {
  const b = new Builder('modulo_fv'); materials(b);
  b.node('Módulo FV 550 Wp', pvMesh(b));
  return b;
}

// ---------- optimización y escritura
const manifest = [];
const jobs = [
  ['hospital_lod0', () => buildHospital(true), 'Hospital Héctor Abad Gómez (detalle completo)'],
  ['hospital_lod1', () => buildHospital(false), 'Hospital Héctor Abad Gómez (nivel de detalle bajo)'],
  ['contenedor_bess', buildBESS, 'Contenedor de baterías LFP de 20 pies'],
  ['modulo_fv', buildPV, 'Módulo fotovoltaico de 550 Wp'],
];
for (const [name, fn, title] of jobs) {
  const m = await writeGLB(fn(), OUT, name);
  manifest.push({ id: name, titulo: title, archivo: `models/${name}.glb`, ...m });
  console.log(`${name}: ${(m.bytes_sin_comprimir / 1024).toFixed(0)} KB → ${(m.bytes / 1024).toFixed(0)} KB · ${m.triangulos_fuente} triángulos fuente · ${m.extensiones.join(', ')}`);
}
writeFileSync(new URL('manifest.json', OUT), JSON.stringify(manifest, null, 1));
