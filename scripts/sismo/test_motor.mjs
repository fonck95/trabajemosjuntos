// Pruebas del motor sísmico (contrato de integración de la torre, 7.8; data/sismo/ESQUEMA.md, «Pruebas»).
//
// Uso:
//   node scripts/sismo/test_motor.mjs                 # todas; código 1 si alguna falla o si falta alguna de T1-T22
//   node scripts/sismo/test_motor.mjs --parcial       # igual, pero las pruebas del contrato que faltan no hacen fallar
//   node scripts/sismo/test_motor.mjs --solo T7,F2    # solo esas (implica --parcial)
//   node scripts/sismo/test_motor.mjs --lista         # qué prueba está en qué módulo, sin correrlas
//
// Las pruebas viven en scripts/sismo/pruebas/*.mjs (desviación acordada del contrato: un archivo por módulo del
// motor, para que varios equipos las escriban en paralelo sin tocar el mismo archivo). Cada módulo exporta
//   export const pruebas = [{ id: 'T7', nombre: 'Ciclo cuasiestático de una rótula', fn: () => resultado }];
// `fn` puede ser async y devuelve un caso o una lista de casos { caso?, error, tolerancia, ok?, detalle? }
// (si falta `ok`, pasa cuando error ≤ tolerancia); si lanza una excepción, la prueba falla con su mensaje.
// Los archivos que empiezan por «_» son ayudantes (pruebas/_util.mjs) y no se cargan como pruebas.
// Sin dependencias: solo Node (≥ 18).

import { readdirSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { join, dirname } from 'node:path';

const CONTRATO = ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8', 'T9', 'T10', 'T11', 'T12', 'T13', 'T14', 'T15', 'T15b', 'T15c',
  'T16', 'T17', 'T18', 'T19', 'T20', 'T21', 'T22'];
// Dónde se espera cada una (12.1 del contrato: quién la escribe con qué módulo del motor)
const MODULO_SUGERIDO = {
  'integrador.mjs': ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T12', 'T21'],
  'modelo.mjs': ['T8', 'T9', 'T10', 'T11', 'T22'],
  'movimiento.mjs': ['T13', 'T14', 'T15', 'T15b', 'T15c', 'T16', 'T19', 'T20'],
  'motor.mjs': ['T17'],
  'estructura.mjs': ['T18'],
};

const args = process.argv.slice(2);
const iSolo = args.indexOf('--solo');
const solo = iSolo >= 0 ? new Set((args[iSolo + 1] || '').split(',').filter(Boolean)) : null;
const parcial = args.includes('--parcial') || !!solo;
const soloLista = args.includes('--lista');

const dirPruebas = join(dirname(fileURLToPath(import.meta.url)), 'pruebas');
const archivos = readdirSync(dirPruebas).filter((f) => f.endsWith('.mjs') && !f.startsWith('_')).sort();

const fmt = (x) => {
  if (typeof x !== 'number') return String(x);
  if (x === 0) return '0';
  const a = Math.abs(x);
  return a >= 1e-3 && a < 1e4 ? String(Number(x.toPrecision(4))) : x.toExponential(2);
};

let fallas = 0;
const estado = new Map();   // id → 'ok' | 'falla'
const origen = new Map();   // id → archivo
const pruebas = [];
for (const f of archivos) {
  let mod;
  try {
    mod = await import(pathToFileURL(join(dirPruebas, f)).href);
  } catch (e) {
    console.log(`✗ ${f}: no se pudo cargar el módulo (${e.message})`);
    fallas++;
    continue;
  }
  const lista = mod.pruebas ?? mod.default;
  if (!Array.isArray(lista)) {
    console.log(`✗ ${f}: no exporta \`pruebas\` (lista de { id, nombre, fn })`);
    fallas++;
    continue;
  }
  for (const p of lista) {
    if (!p || typeof p.id !== 'string' || typeof p.fn !== 'function') {
      console.log(`✗ ${f}: prueba mal formada (${JSON.stringify(p?.id)})`);
      fallas++;
      continue;
    }
    if (origen.has(p.id)) {
      console.log(`✗ ${p.id} está en ${origen.get(p.id)} y en ${f}`);
      fallas++;
      continue;
    }
    origen.set(p.id, f);
    pruebas.push({ ...p, archivo: f });
  }
}

if (soloLista) {
  for (const p of pruebas) console.log(`${p.id.padEnd(5)} ${p.archivo.padEnd(16)} ${p.nombre ?? ''}`);
  const faltan = CONTRATO.filter((id) => !origen.has(id));
  if (faltan.length) {
    console.log(`\nSin escribir (${faltan.length}):`);
    for (const [arch, ids] of Object.entries(MODULO_SUGERIDO)) {
      const f = ids.filter((id) => faltan.includes(id));
      if (f.length) console.log(`  pruebas/${arch}: ${f.join(', ')}`);
    }
  }
  process.exit(0);
}

const orden = (id) => {
  const i = CONTRATO.indexOf(id);
  return i >= 0 ? [0, i] : [1, id];
};
pruebas.sort((a, b) => {
  const [ga, ia] = orden(a.id), [gb, ib] = orden(b.id);
  return ga - gb || (ia < ib ? -1 : ia > ib ? 1 : 0);
});

for (const p of pruebas) {
  if (solo && !solo.has(p.id)) continue;
  const t0 = performance.now();
  let casos, excepcion = null;
  try {
    const r = await p.fn();
    casos = r === undefined ? [{ ok: true }] : Array.isArray(r) ? r : [r];
  } catch (e) {
    excepcion = e;
  }
  const ms = performance.now() - t0;
  if (excepcion) {
    console.log(`✗ ${p.id.padEnd(5)} ${p.nombre} — excepción: ${excepcion.message}  [${p.archivo}]`);
    if (process.env.DEPURAR) console.log(excepcion.stack);
    estado.set(p.id, 'falla');
    fallas++;
    continue;
  }
  const evaluados = casos.map((c) => ({ ...c, ok: c.ok ?? (typeof c.error === 'number' && typeof c.tolerancia === 'number' && c.error <= c.tolerancia) }));
  const ok = evaluados.every((c) => c.ok);
  estado.set(p.id, ok ? 'ok' : 'falla');
  if (!ok) fallas++;
  console.log(`${ok ? '✓' : '✗'} ${p.id.padEnd(5)} ${p.nombre}  (${ms.toFixed(0)} ms)  [${p.archivo}]`);
  for (const c of evaluados) {
    const partes = [];
    if (c.caso) partes.push(c.caso);
    if (c.error !== undefined) partes.push(`error ${fmt(c.error)}${c.tolerancia !== undefined ? ` (tolerancia ${fmt(c.tolerancia)})` : ''}`);
    if (c.detalle) partes.push(c.detalle);
    if (partes.length) console.log(`      ${c.ok ? '·' : '✗'} ${partes.join(' · ')}`);
  }
}

// Resumen del contrato (T1-T22, con T15b y T15c)
const faltan = CONTRATO.filter((id) => !origen.has(id));
const linea = CONTRATO.map((id) => {
  const s = estado.get(id);
  return `${id} ${s === 'ok' ? 'ok' : s === 'falla' ? 'FALLA' : origen.has(id) ? '—' : 'pendiente'}`;
});
console.log('\nContrato 7.8: ' + linea.join(' · '));
const corridas = [...estado.values()];
console.log(`${corridas.filter((s) => s === 'ok').length} pruebas en verde, ${corridas.filter((s) => s === 'falla').length} con fallas, ` +
  `${faltan.length} del contrato sin escribir${faltan.length && parcial ? ' (no cuentan: --parcial)' : ''}.`);
if (faltan.length && !parcial) {
  console.log('Faltan pruebas del contrato: ' + faltan.join(', ') + ' (ver --lista).');
}
process.exit(fallas || (faltan.length && !parcial) ? 1 : 0);
