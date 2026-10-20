// Simulación horaria (pasos de 15 min) de la microrred / comunidad energética pública de Yondó.
// Función pura: misma entrada, misma salida. La usan la escena 3D y scripts/verificar_sim.mjs.

export const STEPS = 96; // 24 h × 4
const DT = 0.25; // horas por paso

// Forma de irradiancia: campana solar 6:00–18:00 (Yondó, ~7° N, días de ~12 h todo el año).
const solarShape = (h) => (h <= 6 || h >= 18 ? 0 : Math.pow(Math.sin((Math.PI * (h - 6)) / 12), 1.3));
const SHAPE_INT = (() => { let s = 0; for (let i = 0; i < STEPS; i++) s += solarShape(i * DT + DT / 2) * DT; return s; })();

function profileAt(prof, h) {
  // perfil de 24 valores (pesos relativos por hora) → fracción de la energía diaria en esa hora
  const sum = prof.reduce((a, b) => a + b, 0);
  return prof[Math.floor(h) % 24] / sum;
}

export function simulate(M, { nubosidad = 0.3, isla = false, dr = true, domotica = true } = {}) {
  const P = M.parametros;
  const nodes = M.nodos;
  const fSun = (1 - 0.7 * nubosidad) / (1 - 0.7 * P.nubosidad_referencia);
  const bessKWh = M.bess.reduce((a, b) => a + b.kwh, 0);
  const bessKW = M.bess.reduce((a, b) => a + b.kw, 0);
  const gensetKW = M.genset.kw;
  const eff = Math.sqrt(P.eficiencia_ida_vuelta_bess);

  const demandOf = (n, h) => {
    let prof = M.perfiles[n.perfil];
    if (dr && n.perfil_dr) prof = M.perfiles[n.perfil_dr];
    if (domotica && n.perfil_domotica) prof = M.perfiles[n.perfil_domotica];
    let e = n.kwh_mes / 30;
    if (domotica) e *= 1 - (n.ahorro_domotica || 0);
    return e * profileAt(prof, h); // kWh en esa hora = kW medio
  };
  const pvOf = (n, h) => n.pv_kwp * P.rendimiento_kwh_kwp_dia * (solarShape(h) / SHAPE_INT) * fSun;

  const run = (soc0) => {
    let soc = soc0;
    const out = [];
    for (let i = 0; i < STEPS; i++) {
      const h = i * DT + DT / 2;
      const per = nodes.map((n) => {
        const on = !isla || n.isla;
        return { id: n.id, prioridad: n.prioridad, on, pv: on ? pvOf(n, h) : 0, dem: demandOf(n, h) };
      });
      const pv = per.reduce((a, p) => a + p.pv, 0);
      const demand = per.reduce((a, p) => a + p.dem, 0);
      let batt = 0, grid = 0, gen = 0, curtail = 0, served = 0;
      const socPct = soc / bessKWh;
      if (!isla) {
        per.forEach((p) => { p.served = p.dem; });
        served = demand;
        const net = demand - pv;
        if (net < 0) {
          const room = (P.soc_max * bessKWh - soc) / DT / eff;
          const ch = Math.min(-net, bessKW, Math.max(0, room));
          batt = -ch; soc += ch * eff * DT; grid = net + ch; // grid < 0 = exportación (excedentes AGPE)
        } else {
          const avail = Math.max(0, (soc - P.soc_reserva * bessKWh) / DT) * eff;
          const dis = Math.min(net, bessKW, avail);
          batt = dis; soc -= (dis / eff) * DT; grid = net - dis;
        }
      } else {
        // Isla: solo nodos con inversor híbrido. Se atiende por prioridad según el estado de la batería.
        per.forEach((p) => {
          const ok = p.on && (p.prioridad === 1 || (p.prioridad === 2 && socPct > P.isla_umbral_p2) || (p.prioridad === 3 && socPct > P.isla_umbral_p3));
          p.served = ok ? p.dem : 0;
        });
        served = per.reduce((a, p) => a + p.served, 0);
        let net = served - pv;
        if (net < 0) {
          const room = (P.soc_max * bessKWh - soc) / DT / eff;
          const ch = Math.min(-net, bessKW, Math.max(0, room));
          batt = -ch; soc += ch * eff * DT; curtail = -net - ch;
        } else {
          const avail = Math.max(0, (soc - P.soc_minimo_isla * bessKWh) / DT) * eff;
          const dis = Math.min(net, bessKW, avail);
          batt = dis; soc -= (dis / eff) * DT; net -= dis;
          if (net > 1e-6) {
            // la planta de respaldo cubre el faltante crítico; lo que no alcanza se raciona
            const crit = per.filter((p) => p.prioridad === 1).reduce((a, p) => a + p.served, 0);
            gen = Math.min(net, gensetKW, crit);
            const unmet = net - gen;
            if (unmet > 1e-6) {
              const rest = per.filter((p) => p.prioridad !== 1 && p.served > 0);
              let cut = unmet;
              for (const p of rest.sort((a, b) => b.prioridad - a.prioridad)) { const c = Math.min(cut, p.served); p.served -= c; cut -= c; }
              served -= unmet - cut;
            }
          }
        }
      }
      out.push({ h, pv, demand, served, batt, grid, gen, curtail, soc: soc / bessKWh, per });
    }
    return { out, socEnd: soc };
  };

  // Estado estable: tres días en modo normal para hallar el SOC de medianoche.
  let soc = P.soc_reserva * bessKWh;
  for (let k = 0; k < 3; k++) soc = run(soc).socEnd;
  if (isla) soc = Math.max(soc, P.soc_alerta_isla * bessKWh); // con alerta de tormenta/falla el EMS precarga
  const { out } = run(soc);

  const sum = (f) => out.reduce((a, s) => a + f(s), 0) * DT;
  const pvE = sum((s) => s.pv), demE = sum((s) => s.demand), servedE = sum((s) => s.served);
  const imp = sum((s) => Math.max(0, s.grid)), exp = sum((s) => Math.max(0, -s.grid));
  const genE = sum((s) => s.gen);
  const critDem = sum((s) => s.per.filter((p) => p.prioridad === 1).reduce((a, p) => a + p.dem, 0));
  const critSrv = sum((s) => s.per.filter((p) => p.prioridad === 1).reduce((a, p) => a + p.served, 0));
  const baseDem = nodes.reduce((a, n) => a + n.kwh_mes / 30, 0);
  // tarifa promedio ponderada: oficial EPM y ESPD para el acueducto
  const tarifa = nodes.reduce((a, n) => a + (n.kwh_mes / 30) * (n.tarifa || P.tarifa_oficial_cop_kwh), 0) / baseDem;
  const ahorroKWh = isla ? 0 : baseDem - imp; // energía que deja de comprarse frente a hoy (sin FV ni domótica)
  return {
    steps: out,
    resumen: {
      pv_kwh: pvE, demanda_kwh: demE, atendida_kwh: servedE, importada_kwh: imp, exportada_kwh: exp, planta_kwh: genE,
      autosuficiencia: isla ? servedE / demE : 1 - imp / demE,
      criticas_atendidas: critDem ? critSrv / critDem : 1,
      // compra evitada + excedentes acreditados 1:1 (AGPE ≤100 kW, CREG 174)
      ahorro_cop_dia: isla ? 0 : ahorroKWh * tarifa + exp * P.precio_excedentes_cop_kwh,
      tarifa_ponderada: tarifa,
      ingreso_excedentes_cop_dia: isla ? 0 : exp * P.precio_excedentes_cop_kwh,
      co2_evitado_kg_dia: isla ? 0 : (baseDem - imp + exp) * P.factor_emision_kgco2_kwh,
      diesel_litros: genE * P.diesel_l_kwh,
      base_kwh: baseDem,
    },
    bessKWh, bessKW,
  };
}
