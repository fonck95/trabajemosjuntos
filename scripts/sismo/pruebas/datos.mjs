// Pruebas de datos y fixtures del motor sísmico (equipo A, ola 0). Sirven también de ejemplo de módulo de pruebas:
// cada uno exporta `pruebas`, una lista de { id, nombre, fn } (ver scripts/sismo/test_motor.mjs).
//   F1  los fixtures del Anexo A.3 y A.4 pasan validar_resultado.mjs
//   F2  data/sismo/amenaza.json es idéntico en números a la investigación y trae lo que pide el 7.3
//   F3  el validador detecta errores (no da todo por bueno)
//   F4  trabajador_simulado.js responde los mensajes del 7.5 con los fixtures
import { readFile } from 'node:fs/promises';
import { validarResultado, validarEstructura, validarSerie, dimensiones } from '../validar_resultado.mjs';
import { RAIZ, leerJSON, caso, comprobar } from './_util.mjs';

const FIX = 'scripts/fixtures/torre/';
const copia = (x) => JSON.parse(JSON.stringify(x));

function f1() {
  const est = leerJSON(FIX + 'estructura_min.json');
  const res = leerJSON(FIX + 'resultado_min.json');
  const serie = leerJSON(FIX + 'serie_elemento_min.json');
  const ve = validarEstructura(est);
  const vr = validarResultado(res, est, { tipado: false });
  const vs = validarSerie(serie, res, est);
  const peor = Math.max(...ve.theta.map((f) => Math.abs(f.error)));
  const d = dimensiones(est);
  const ultimo = res.rotulas.slice(-d.nE);
  return [
    caso('estructura_min.json', ve.errores.length, 0, ve.errores[0]),
    caso('theta_y = My·L_f/(6·EI_fis) en todas las vigas y columnas', peor, 0.01),
    caso('resultado_min.json', vr.errores.length, 0, vr.errores[0] ?? `nt = ${res.t.length}, N = ${d.N}, nE = ${d.nE}, nN = ${d.nN}, nP = ${d.nP}`),
    caso('serie_elemento_min.json', vs.errores.length, 0, vs.errores[0] ?? serie.elemento),
    comprobar('tamaños del Anexo A.4', res.t.length === 3 && d.N === 2 && d.nE === 24 && d.nN === 24 && d.nP === 4),
    comprobar('al menos una rótula que fluye en el último paso', ultimo.some((b) => b & 3), `${res.thp.elementos.length} elementos con θp`),
    comprobar('un equipo que desliza', res.equipos.some((q) => q.regimen === 'desliza' && q.desliza)),
    comprobar('un muro de mampostería con daño', res.muros_mamposteria.some((m) => !m.aislado && m.estado !== 'sin_dano'),
      res.muros_mamposteria.map((m) => `${m.id}: ${m.estado}`).join(', ')),
  ];
}

// --- F2: comparación de amenaza.json con la copia de la investigación --------------------------------------------
const AGREGADOS_7_3 = [
  'implementacion_de_referencia', 'implementacion_de_referencia_nota', 'seleccion_de_regimen.nota_motor',
  ...['id', 'fecha', 'magnitud_reportada', 'magnitud_estado', 'inconsistencia_epicentro', 'fuera_del_rango_del_control', 'uso_en_simulador', 'fuentes_repo']
    .map((k) => `escenarios_lejanos_sentidos[0].${k}`),
];

function hojas(x, ruta = '', out = new Map()) {
  if (Array.isArray(x)) {
    out.set(ruta + '#largo', x.length);
    x.forEach((v, i) => hojas(v, `${ruta}[${i}]`, out));
  } else if (x && typeof x === 'object') {
    out.set(ruta + '#claves', Object.keys(x).length);
    for (const [k, v] of Object.entries(x)) hojas(v, ruta ? `${ruta}.${k}` : k, out);
  } else out.set(ruta, x);
  return out;
}

function f2() {
  const fuente = leerJSON('data/sismo/fuentes_investigacion/amenaza.json');
  const destino = leerJSON('data/sismo/amenaza.json');
  const hf = hojas(fuente), hd = hojas(destino);
  let numeros = 0, otros = 0;
  const distintos = [];
  for (const [ruta, v] of hf) {
    if (ruta.endsWith('#claves')) continue;   // los objetos pueden ganar claves (las agregadas se revisan abajo)
    const w = hd.get(ruta);
    if (!hd.has(ruta) || typeof w !== typeof v || w !== v) distintos.push(ruta);
    else if (typeof v === 'number') numeros++;
    else otros++;
  }
  const agregadas = [...hd.keys()].filter((r) => !r.endsWith('#claves') && !r.endsWith('#largo') && !hf.has(r));
  const permitida = (r) => AGREGADOS_7_3.some((p) => r === p || r.startsWith(p + '[') || r.startsWith(p + '.'));
  const noPermitidas = agregadas.filter((r) => !permitida(r));
  const sismo = destino.escenarios_lejanos_sentidos.find((e) => e.id === 'terremoto_2026_08_10');
  const dist = sismo ? Object.values(sismo.distancia_a_yondo_km) : [];
  return [
    caso(`números de la investigación idénticos (${numeros} números y ${otros} textos, booleanos y nulos comparados)`, distintos.length, 0,
      distintos.length ? 'distintos: ' + distintos.slice(0, 5).join(', ') : undefined),
    caso('claves agregadas fuera de las del 7.3', noPermitidas.length, 0,
      noPermitidas.length ? noPermitidas.slice(0, 5).join(', ') : `${agregadas.length} hojas agregadas, todas del 7.3`),
    comprobar('implementacion_de_referencia = scripts/sismo/estocastico.py', destino.implementacion_de_referencia === 'scripts/sismo/estocastico.py'),
    comprobar('sismo del 10-ago-2026 con la inconsistencia del epicentro y sus dos distancias (≈ 342 y 313 km, fuera de 0-300 km)',
      sismo && /San José del Palmar/.test(sismo.inconsistencia_epicentro) && /Pereira/.test(sismo.inconsistencia_epicentro) &&
      dist.length === 2 && dist.every((d) => d > 300) && sismo.fuera_del_rango_del_control === true),
  ];
}

// --- F3: el validador encuentra errores sembrados ----------------------------------------------------------------
function f3() {
  const est = leerJSON(FIX + 'estructura_min.json');
  const res = leerJSON(FIX + 'resultado_min.json');
  const serie = leerJSON(FIX + 'serie_elemento_min.json');
  const errores = (fn) => fn().errores.length;
  const casos = [];
  const sembrar = (nombre, fn) => { const n = errores(fn); casos.push(comprobar(nombre, n > 0, `${n} errores detectados`)); };
  sembrar('theta_y de V30x50 = 0,0039 (−1,16 %)', () => { const e = copia(est); e.secciones.V30x50.theta_y = 0.0039; return validarEstructura(e); });
  sembrar('columna que no es vertical', () => { const e = copia(est); e.bloques[0].porticos[0].nodos[2].s = 0.5; return validarEstructura(e); });
  sembrar('id de elemento repetido', () => { const e = copia(est); e.bloques[0].porticos[1].elementos[0].id = 'C-A1-1@X'; return validarEstructura(e); });
  sembrar('rotulas con un elemento de menos', () => { const r = copia(res); r.rotulas.pop(); return validarResultado(r, est); });
  sembrar('dc fuera de Uint8 (300)', () => { const r = copia(res); r.dc[0] = 300; r.dc_flexion[0] = 300; return validarResultado(r, est); });
  sembrar('energía que no cierra', () => { const r = copia(res); r.energia[6 * 2] *= 1.2; return validarResultado(r, est); });
  sembrar('envolvente u_max menor que la serie', () => { const r = copia(res); r.envolventes.u_max[3] = 0; return validarResultado(r, est); });
  sembrar('elemento que fluye sin thp', () => { const r = copia(res); const k = r.thp.elementos.length; r.thp.elementos.pop();
    r.thp.valores = r.thp.valores.filter((_, i) => Math.floor(i / 2) % k !== k - 1); return validarResultado(r, est); });
  sembrar('muro con estado que no corresponde a su deriva', () => { const r = copia(res); r.muros_mamposteria[0].estado = 'leve'; return validarResultado(r, est); });
  sembrar('equipo anclado sin fuerza de anclaje', () => { const r = copia(res); const q = r.equipos.find((x) => x.regimen === 'anclado'); q.fuerza_anclaje_kN = null; return validarResultado(r, est); });
  sembrar('arreglo tipado equivocado (u en Float64Array)', () => {
    const r = copia(res);
    for (const k of ['t', 'ag', 'a_abs', 'giros', 'v_nodos', 'derivas', 'derivas_vector', 'derivas_porticos_env', 'cortante_basal', 'energia']) r[k] = Float32Array.from(r[k]);
    for (const k of ['dc', 'dc_flexion', 'dc_cortante', 'dc_rotacion', 'rotulas']) r[k] = Uint8Array.from(r[k]);
    r.u = Float64Array.from(r.u);
    return validarResultado(r, est, { tipado: true });
  });
  sembrar('serie con dc que no coincide', () => { const s = copia(serie); s.dc[2] = 0.5; return validarSerie(s, res, est); });
  return casos;
}

// --- F4: el trabajador simulado, manejado desde Node ----------------------------------------------------------------
async function f4() {
  const est = leerJSON(FIX + 'estructura_min.json');
  const serieArchivo = leerJSON(FIX + 'serie_elemento_min.json');
  const dim = dimensiones(est);
  const recibidos = [];
  const selfFalso = { postMessage: (m, transferir) => recibidos.push({ m, transferir: transferir || [] }), onmessage: null };
  const selfAntes = globalThis.self, fetchAntes = globalThis.fetch;
  globalThis.self = selfFalso;
  globalThis.fetch = async (url) => {
    const u = new URL(url);
    if (u.protocol !== 'file:') return fetchAntes(url);
    try {
      const texto = await readFile(u, 'utf8');
      return { ok: true, status: 200, json: async () => JSON.parse(texto) };
    } catch {
      return { ok: false, status: 404, json: async () => null };
    }
  };
  const casos = [];
  try {
    await import(new URL(FIX + 'trabajador_simulado.js', RAIZ).href + '?f4=' + Date.now());
    casos.push(comprobar('cargado al evaluar el módulo', recibidos[0]?.m.tipo === 'cargado'));
    const enviar = async (msg) => { recibidos.length = 0; await selfFalso.onmessage({ data: msg }); return recibidos.map((r) => r.m); };

    let r = await enviar({ tipo: 'analizar', id: 1, params: {}, opciones: {} });
    casos.push(comprobar('analizar antes de iniciar → error de datos', r[0]?.tipo === 'error' && r[0].codigo === 'datos'));

    r = await enviar({ tipo: 'iniciar', v: 1, id: 2, url_estructura: 'http://ejemplo/x.json', url_amenaza: 'http://ejemplo/a.json', opciones: {} });
    const listo = r[0];
    const ok = listo?.tipo === 'listo' && listo.id === 2 && listo.elementos.length === dim.nE && listo.nodos.length === dim.nN &&
      listo.elementos.every((e, i) => e.id === dim.elementos[i].id) && listo.resumen.niveles === dim.N;
    casos.push(comprobar('listo con los elementos y nodos de estructura_min.json', ok,
      listo ? `T1 = ${listo.modos.periodos_s[0]} s, ${listo.modos.periodos_s.length} modos, ξ = ${listo.amortiguamiento.xi_modos.map((x) => x.toFixed(3)).join('/')}` : ''));

    r = await enviar({ tipo: 'movimiento', id: 3, params: {} });
    const mv = r[0];
    casos.push(comprobar('movimiento con registro Float32Array a 0,005 s y transferido', mv?.tipo === 'movimiento' && mv.registro.ax instanceof Float32Array &&
      mv.registro.dt === 0.005 && mv.registro.ax.length === mv.registro.n && recibidos[0].transferir.length > 0));

    r = await enviar({ tipo: 'analizar', id: 4, params: {}, opciones: {}, simular: { retardo_ms: 0 } });
    const prog = r.filter((m) => m.tipo === 'progreso');
    const fin = r.find((m) => m.tipo === 'resultado');
    casos.push(comprobar('progreso y resultado', prog.length >= 1 && fin && fin.id === 4, `${prog.length} mensajes de progreso`));
    if (fin) {
      const v = validarResultado(fin.resultados, est, { tipado: true });
      casos.push(caso('resultado tipado (Float32/Uint8/Int16/Int32) pasa validar_resultado', v.errores.length, 0, v.errores[0]));
      casos.push(comprobar('búferes transferidos', recibidos.find((x) => x.m.tipo === 'resultado').transferir.length >= 20));
    }

    r = await enviar({ tipo: 'serie_elemento', id: 5, elemento: 'C-A1-1@X' });
    const s1 = r[0];
    casos.push(comprobar('serie_elemento de C-A1-1@X igual a serie_elemento_min.json', s1?.tipo === 'serie_elemento' &&
      ['Mi', 'Mj', 'V', 'N', 'thp_i', 'thp_j', 'dc'].every((k) => s1[k] instanceof Float32Array && s1[k].every((x, i) => x === Math.fround(serieArchivo[k][i])))));
    r = await enviar({ tipo: 'serie_elemento', id: 6, elemento: 'VY-B-12-2' });
    if (fin && r[0]?.tipo === 'serie_elemento') {
      const resJson = leerJSON(FIX + 'resultado_min.json');
      const v = validarSerie({ ...r[0], t: [...r[0].t] }, resJson, est);
      casos.push(caso('serie_elemento de otro elemento coherente con el resultado', v.errores.length, 0, v.errores[0] ?? 'VY-B-12-2'));
    } else casos.push(comprobar('serie_elemento de otro elemento', false, JSON.stringify(r[0])));

    r = await enviar({ tipo: 'serie_elemento', id: 7, elemento: 'NO-EXISTE' });
    casos.push(comprobar('elemento desconocido → error de datos', r[0]?.tipo === 'error' && r[0].codigo === 'datos'));
    r = await enviar({ tipo: 'analizar', id: 8, params: {}, opciones: {}, simular: { retardo_ms: 0, error: 'no_converge' } });
    casos.push(comprobar('error simulado no_converge', r.at(-1)?.tipo === 'error' && r.at(-1).codigo === 'no_converge'));
  } finally {
    if (selfAntes === undefined) delete globalThis.self; else globalThis.self = selfAntes;
    globalThis.fetch = fetchAntes;
  }
  return casos;
}

export const pruebas = [
  { id: 'F1', nombre: 'Fixtures del Anexo A.3 y A.4 pasan validar_resultado', fn: f1 },
  { id: 'F2', nombre: 'amenaza.json idéntico en números a la investigación (7.3)', fn: f2 },
  { id: 'F3', nombre: 'El validador detecta errores sembrados', fn: f3 },
  { id: 'F4', nombre: 'trabajador_simulado.js responde los mensajes del 7.5', fn: f4 },
];
