// Verifica la simulación de la microrred en los cuatro escenarios principales.
// Uso: node scripts/verificar_sim.mjs
import { readFileSync } from 'node:fs';
import { simulate } from '../web/js/sim.js';
const M = JSON.parse(readFileSync(new URL('../data/microrred.json', import.meta.url)));
const casos = [
  ['Hoy (sin FV ni gestión)', { nubosidad: 0.3, dr: false, domotica: false }, true],
  ['Red normal + DR + domótica', { nubosidad: 0.3 }],
  ['Día nublado', { nubosidad: 0.8 }],
  ['Falla de red 24 h (isla)', { nubosidad: 0.3, isla: true }],
  ['Falla de red 24 h nublado', { nubosidad: 0.8, isla: true }],
];
for (const [nombre, op, sinFV] of casos) {
  const m = sinFV ? { ...M, nodos: M.nodos.map((n) => ({ ...n, pv_kwp: 0 })), bess: M.bess.map((b) => ({ ...b, kwh: 1e-6, kw: 0 })) } : M;
  const r = simulate(m, op).resumen;
  const f = (v) => Math.round(v).toLocaleString('es-CO');
  console.log(`\n${nombre}`);
  console.log(`  FV ${f(r.pv_kwh)} kWh | demanda ${f(r.demanda_kwh)} | atendida ${f(r.atendida_kwh)} | red +${f(r.importada_kwh)} / -${f(r.exportada_kwh)} | planta ${f(r.planta_kwh)} kWh`);
  console.log(`  autosuficiencia ${(r.autosuficiencia * 100).toFixed(1)}% | críticas ${(r.criticas_atendidas * 100).toFixed(1)}% | ahorro COP/día ${f(r.ahorro_cop_dia)} | CO2 evitado ${f(r.co2_evitado_kg_dia)} kg/día`);
}
