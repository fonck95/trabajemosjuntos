// Modo «Simulador sísmico» de la vista de la torre (equipo D; especificación de integración, 8).
// Principio (8.1): todo lo que se mueve en pantalla es resultado del cálculo en ese paso de tiempo. El deslizador
// recorre los pasos calculados (Resultados.t); «Reproducir» solo avanza el índice con el reloj real; con
// prefers-reduced-motion no hay reproducción automática.
// El cálculo lo hace el motor del equipo A (web/js/sismo/): un trabajador de módulo (trabajador.js) o, si no hay Worker,
// si no responde «cargado» en 3 s o si falla antes de «listo», la misma lógica (motor.js) en el hilo principal cediendo
// cada ≈ 12 ms (7.5). Esta vista no duplica física: arma los mensajes, dibuja y explica.
// torre.js lo carga de forma perezosa y le pasa ctx (6.2 y 8.6): st, raiz, hud (torre.hud.sismo), panel
// (torre.panel.sismo), ficha (torre.ficha.modo), graficas (torre.sismo.graficas), datos { amenaza, inventario, urls },
// textos { limpio, esc, escH }, exterior.ocultar(on) y alSalir(). Solo escribe en esos contenedores.
// QA (8.7), sirviendo la raíz del repositorio para que existan los fixtures (scripts/fixtures/torre/):
//   «?qa=1&motor=simulado»   trabajador simulado del equipo A (trabajador_simulado.js) con sus resultados de prueba;
//   «?qa=1&estructura=min»   motor real (trabajador o respaldo) sobre el cubo de prueba estructura_min.json.
import { THREE, tokens, onTheme, engine, reducedMotion } from '../../core.js';
import { crearEstructura3D, CORTES_DC, ESTADOS_MURO } from './estructura3d.js';
import * as G from './graficas.js';

const g0 = 9.80665;
const NOMBRE_MOTOR = { trabajador: 'trabajador en segundo plano', hilo_principal: 'hilo principal (respaldo sin trabajador)', simulado: 'trabajador simulado (pruebas)' };
// texto de honestidad (8.5), obligatorio en la vista
export const HONESTIDAD = 'Modelo de prediseño (sin estudio de suelos ni diseño estructural firmado). Idealización estándar de ingeniería: diafragmas rígidos, pórticos planos, rótulas concentradas, núcleos como muros planos con aletas efectivas (su resistencia no cambia con la carga axial del sismo), sin interacción suelo-estructura, sin componente vertical, sin degradación de resistencia. Amortiguamiento del 5 % proporcional a la masa y a la rigidez inicial de la parte elástica de los elementos (las rótulas no amortiguan). Los colores comparan con la resistencia esperada y con el límite de ocupación inmediata de un hospital. El contexto sísmico (nido de Bucaramanga, fallas cercanas) está por confirmar con el Servicio Geológico Colombiano. Validado contra soluciones exactas y contra OpenSees (ver documento 14).';
const CAMPOS = {
  max: ['Máximo de los tres', 'el mayor de |M|/Mn esperado, |V|/Vn esperado y θp/θp de ocupación inmediata'],
  flexion: ['Flexión', '|M|/Mn esperado (momento contra la resistencia esperada a flexión)'],
  cortante: ['Cortante', '|V|/Vn esperado (cortante contra la resistencia esperada a cortante)'],
  rotacion: ['Rotación plástica', 'θp/θp de ocupación inmediata (IO, el límite de desempeño de un hospital)'],
};
const GOBIERNA = ['flexión', 'cortante', 'rotación plástica'];
const REGIMEN = { cortical: 'cortical', intraplaca_profunda: 'intraplaca profunda', transicion: 'transición', auto: 'automático' };
const EXAGERACIONES = [1, 2, 5, 10, 20, 50, 100, 200];
const ESTADO_MURO_TXT = { sin_dano: 'sin daño', leve: 'leve', moderado: 'moderado', extenso: 'extenso', colapso: 'colapso' };
const REGIMEN_EQ = { desliza: 'desliza', balancea: 'empieza a balancearse', frontera: 'frontera (desliza o se balancea)', anclado: 'anclado', estable: 'estable' };

const n = (v, d = 1) => (Number.isFinite(+v) ? (+v).toLocaleString('es-CO', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—');
const nv = (v, d = 2) => (Number.isFinite(+v) ? (+v).toLocaleString('es-CO', { maximumFractionDigits: d }) : '—');
const pct = (v, d = 2) => (Number.isFinite(+v) ? `${n(v * 100, d)} %` : '—');
const SUP = { '-': '⁻', 0: '⁰', 1: '¹', 2: '²', 3: '³', 4: '⁴', 5: '⁵', 6: '⁶', 7: '⁷', 8: '⁸', 9: '⁹' };
function cientifico(v, d = 2) {
  if (!Number.isFinite(v) || v === 0) return nv(v);
  const e = Math.floor(Math.log10(Math.abs(v))), m = v / 10 ** e;
  return `${n(m, d)} × 10${String(e).split('').map((c) => SUP[c]).join('')}`;
}
// número con el texto del tipo de dato
const ceder = () => new Promise((ok) => { const c = new MessageChannel(); c.port1.onmessage = () => { c.port1.close(); ok(); }; c.port2.postMessage(0); });

export async function montar(ctx) {
  const { st, panel, hud, ficha, graficas: cajaG, textos } = ctx;
  const { esc, escH, limpio } = textos;
  const qs = new URLSearchParams(location.search);
  const SIMULADO = qs.has('qa') && qs.get('motor') === 'simulado';
  const MIN = SIMULADO || (qs.has('qa') && qs.get('estructura') === 'min');
  const FIX = (f) => new URL(`../../../../scripts/fixtures/torre/${f}`, import.meta.url).href;
  const URL_TRABAJADOR = SIMULADO ? FIX('trabajador_simulado.js') : new URL('../../sismo/trabajador.js', import.meta.url).href;
  const URL_MOTOR = new URL('../../sismo/motor.js', import.meta.url).href;
  const URL_ESTRUCTURA = MIN ? FIX('estructura_min.json') : ctx.datos?.urls?.estructura || new URL('../../../data/sismo_torre_estructura.json', import.meta.url).href;
  const URL_AMENAZA = ctx.datos?.urls?.amenaza || new URL('../../../data/sismo_amenaza.json', import.meta.url).href;
  const leerJSON = (u) => fetch(u).then((r) => (r.ok ? r.json() : null)).catch(() => null);
  let amenaza = ctx.datos?.amenaza || null;
  if (!amenaza) amenaza = await leerJSON(URL_AMENAZA);
  let inventario = ctx.datos?.inventario || null;
  if (!inventario && SIMULADO) inventario = await leerJSON(FIX('inventario_min.json'));
  const CTRL = amenaza?.controles || {};
  const ESC = amenaza?.escenarios || [];
  const def = (k, d) => CTRL[k]?.defecto ?? d;

  // ================================================================ contenedores (se guardan fuera mientras no se usan)
  const tel = matchMedia('(max-width: 1080px)');   // la leyenda sobre el recuadro empieza cerrada en pantallas medianas y pequeñas
  const elPanel = document.createElement('div'); elPanel.className = 'sismo-panel';
  const elHud = document.createElement('div'); elHud.className = 'sismo-hud';
  const elG = document.createElement('div'); elG.className = 'sismo-graficas';
  const elFicha = document.createElement('div'); elFicha.className = 'sismo-ficha';
  const opt = (v, t, sel) => `<option value="${escH(v)}"${sel ? ' selected' : ''}>${t}</option>`;
  const rango = (k, etq, unidad, { min, max, paso, valor }, nota = '') => `<label class="sismo-rango"><span>${etq} <output data-o="${k}"></output>${unidad ? ` <small>${unidad}</small>` : ''}</span><input type="range" data-c="${k}" min="${min}" max="${max}" step="${paso}" value="${valor}">${nota}</label>`;
  const radio = (nombre, leyenda, ops) => `<fieldset class="sismo-op"><legend>${leyenda}</legend>${ops.map(([v, t, on]) => `<label><input type="radio" name="sismo-${nombre}" value="${v}"${on ? ' checked' : ''}> ${t}</label>`).join('')}</fieldset>`;
  const C = (k, d) => ({ min: CTRL[k]?.min ?? d[0], max: CTRL[k]?.max ?? d[1], paso: CTRL[k]?.paso ?? d[2], valor: def(k, d[3]) });
  elPanel.innerHTML = `<h3>Simulador sísmico</h3>
    <p class="note">Elige un sismo y calcula. El motor arma el movimiento del suelo con la física de la fuente, del camino y del suelo, y resuelve paso a paso cómo responde la estructura de la torre. Nada de lo que se mueve es animación: el deslizador recorre los pasos calculados.</p>
    <form class="ctl sismo-ctl" data-s="form" novalidate>
      <label>Escenario <select data-c="escenario">${ESC.map((e) => opt(e.id, esc(e.nombre), e.id === 'nido_2015')).join('')}${opt('personalizado', 'Personalizado', !ESC.length)}</select></label>
      <p class="note" data-o="escenario" aria-live="polite"></p>
      ${rango('Mw', 'Magnitud de momento <b>Mw</b>', '', C('Mw', [4, 8, 0.1, 6.2]))}
      <p class="note">Magnitud de momento Mw (la que reemplazó a la escala de Richter: la de Richter se satura por encima de 6,5 a 7). <span data-o="M0"></span></p>
      <details class="fold sismo-richter"><summary>¿Por qué no Richter?</summary><p class="note">${esc(amenaza?.magnitud?.explicacion_ciudadana || 'La escala de Richter se satura en los sismos grandes; la magnitud de momento Mw sale del tamaño de la ruptura y no se satura.')}</p></details>
      ${rango('h', 'Profundidad', 'km', C('profundidad_km', [5, 200, 1, 150]))}
      <p class="note">La profundidad cambia la distancia al foco y el tipo de sismo. <span data-o="tipo"></span></p>
      <label>Tipo de sismo <select data-c="regimen">${opt('auto', 'Automático (según la profundidad)', true)}${opt('cortical', 'Cortical')}${opt('intraplaca_profunda', 'Intraplaca profunda')}</select></label>
      <p class="note sismo-aviso" data-o="aviso-tipo" hidden></p>
      ${rango('d', 'Distancia epicentral', 'km', C('distancia_epicentral_km', [0, 300, 1, 92]))}
      <p class="note" data-o="rhip"></p>
      ${rango('vs30', 'Suelo: Vs30', 'm/s', C('vs30_m_s', [150, 760, 10, 270]), '<small class="note">Suelo D supuesto mientras no haya estudio geotécnico.</small>')}
      ${radio('escala', 'Escala del registro', [['1', '×1 (físico)', true], ['nsr10', 'Nivel de diseño NSR-10']])}
      <p class="note sismo-aviso" data-o="escala" hidden>Escenario hipotético: el registro se multiplica para que su espectro, entre 0,8 y 1,2 veces el período fundamental en cada dirección, iguale en promedio el espectro de diseño de Yondó con I = 1,5; no cambia la física de la fuente. <span data-o="factor"></span></p>
      <details class="fold"><summary>Más opciones del cálculo</summary><div class="ctl">
        <label>Semilla <input type="number" data-c="semilla" step="1" value="${def('semilla', 2028)}" inputmode="numeric"><small class="note">Misma semilla, mismo sismo, en cualquier dispositivo (el movimiento se arma siempre con pasos de 0,005 s).</small></label>
        ${rango('ang', 'Dirección de la componente 1', '°', { min: 0, max: 180, paso: 5, valor: 0 }, '<small class="note">Ángulo antihorario desde el este.</small>')}
        ${radio('muros', 'Muros no estructurales', [['aislados', 'Aislados de la estructura', true], ['confinados', 'Sin aislar (pegados a la estructura)']])}
        ${radio('histeresis', 'Comportamiento de las rótulas', [['bilineal', 'Bilineal', true], ['clough', 'Clough (rigidez que se degrada)']])}
        ${radio('calidad', 'Calidad del cálculo', [['normal', 'Normal: paso de 0,005 s', true], ['baja', 'Baja: paso de 0,01 s (más rápido)']])}
      </div></details>
      <div class="sismo-acciones"><button type="submit" class="btn" data-s="calcular">Calcular</button><button type="button" class="btn ghost" data-s="cancelar" hidden>Cancelar</button></div>
      <div class="sismo-estado"><p role="status" aria-live="polite" data-o="estado">Preparando el motor…</p><progress data-o="progreso" max="1" value="0" aria-label="Avance del cálculo" hidden></progress><p class="note" data-o="estado-det" aria-hidden="true" hidden></p></div>
      <ul class="tight note sismo-avisos" data-o="avisos"></ul>
    </form>
    <h4>Cómo se dibuja</h4>
    <div class="ctl">
      <label>Exageración de la deformada <select data-c="exag">${opt('auto', 'Automática', true)}${EXAGERACIONES.map((e) => opt(e, `×${e}`)).join('')}</select></label>
      <p class="note" data-o="exag"></p>
      <fieldset class="sismo-op"><legend>Colorear por</legend><div class="seg" role="group" aria-label="Colorear por">${Object.entries(CAMPOS).map(([k, [t]], i) => `<button type="button" data-campo="${k}" aria-pressed="${i === 0}">${t}</button>`).join('')}</div></fieldset>
      <p class="note" data-o="campo"></p>
      <label>Equipos de la dotación sobre la losa <select data-c="piso-eq">${opt('', 'Ninguno', true)}</select></label>
      <p class="note" data-o="piso-eq"></p>
    </div>
    <details class="fold"><summary>Qué es y qué no es este modelo</summary><p class="note">${HONESTIDAD}</p></details>`;
  elHud.innerHTML = `<div class="sismo-tiempo" role="group" aria-label="Tiempo del sismo calculado">
      <button type="button" data-s="play" aria-pressed="false" disabled>Reproducir</button>
      <input type="range" data-c="t" min="0" max="0" step="1" value="0" aria-label="Paso de tiempo calculado" disabled>
      <span class="sismo-t" data-o="t">sin cálculo</span>
      <span class="seg sismo-vel" role="group" aria-label="Velocidad de reproducción"><button type="button" data-vel="0.25" aria-pressed="false">0,25×</button><button type="button" data-vel="1" aria-pressed="true">1×</button></span>
    </div>
    <details class="sismo-ley"${tel.matches ? '' : ' open'}><summary>Colores</summary><div data-o="leyenda"></div></details>`;
  elG.innerHTML = `<p class="note" data-o="g-estado">Las gráficas aparecen cuando termina el cálculo.</p>
    <div class="sismo-rejilla">
      <div data-g="acel"></div><div data-g="espectros"></div><div data-g="derivas"></div><div data-g="cortante"></div><div data-g="energia"></div><div data-g="fourier"></div>
    </div>
    <h4 class="sismo-el-tit" data-o="el-titulo">Elemento seleccionado</h4>
    <label class="sismo-el-sel">Elegir otro elemento <select data-c="elemento"></select></label>
    <div class="sismo-rejilla"><div data-g="histeresis"></div><div data-g="momentos"></div><div data-g="fuerzas"></div></div>
    <h4>Variables del cálculo</h4>
    <div class="tbl-wrap" data-o="tabla"></div>
    <div data-o="equipos"></div>
    <p class="note sismo-honestidad">${HONESTIDAD}</p>`;
  const $ = (raiz, s) => raiz.querySelector(s);
  const ctl = (k) => elPanel.querySelector(`[data-c="${k}"]`) || elHud.querySelector(`[data-c="${k}"]`) || elG.querySelector(`[data-c="${k}"]`);
  const out = (k) => elPanel.querySelector(`[data-o="${k}"]`) || elHud.querySelector(`[data-o="${k}"]`) || elG.querySelector(`[data-o="${k}"]`);
  const radioV = (nombre) => elPanel.querySelector(`input[name="sismo-${nombre}"]:checked`)?.value;

  // ================================================================ controles del sismo (8.2)
  const esc0 = ESC.find((e) => e.id === 'nido_2015');
  if (esc0) { ctl('Mw').value = esc0.Mw; ctl('h').value = esc0.profundidad_km; ctl('d').value = esc0.distancia_epicentral_km; }
  function leerParams() {
    return {
      Mw: +ctl('Mw').value, profundidad_km: +ctl('h').value, distancia_epicentral_km: +ctl('d').value, vs30_m_s: +ctl('vs30').value,
      semilla: Math.trunc(+ctl('semilla').value || 0), regimen: ctl('regimen').value,
    };
  }
  function leerOpciones() {
    const calidad = radioV('calidad') || 'normal', esc = radioV('escala');
    return { dt_s: calidad === 'baja' ? 0.01 : 0.005, dt_salida_s: 0.02, angulo_deg: +ctl('ang').value, escala: esc === 'nsr10' ? 'nsr10' : 1, calidad };
  }
  let ultimoEscenario = null;
  const opcionesModelo = () => ({ histeresis: radioV('histeresis') || 'bilineal', noEstructurales: radioV('muros') || 'aislados' });
  function textosControles() {
    const p = leerParams();
    out('Mw').textContent = n(p.Mw, 1);
    out('h').textContent = nv(p.profundidad_km, 0);
    out('d').textContent = nv(p.distancia_epicentral_km, 0);
    out('vs30').textContent = nv(p.vs30_m_s, 0);
    out('ang').textContent = nv(+ctl('ang').value, 0);
    const M0 = 10 ** (1.5 * p.Mw + 16.05) * 1e-7;
    out('M0').innerHTML = `Momento sísmico M0 = ${cientifico(M0)} N·m; energía radiada ≈ ${cientifico(M0 / 2e4, 1)} J (estimación, M0/20.000).`;
    const h = p.profundidad_km, w = Math.min(1, Math.max(0, (h - 40) / 30));
    out('tipo').textContent = h <= 40 ? 'Tipo resultante: cortical (en la corteza).' : h >= 70 ? 'Tipo resultante: intraplaca profunda (dentro de la placa que se hunde).' : `Tipo resultante: transición entre corteza y placa (${nv(w * 100, 0)} % intraplaca y ${nv((1 - w) * 100, 0)} % cortical).`;
    const av = p.regimen === 'intraplaca_profunda' && h < 40 ? 'Forzaste un sismo intraplaca con menos de 40 km de profundidad: no hay evidencia de esa combinación aquí (escenario hipotético).'
      : p.regimen === 'cortical' && h > 60 ? 'Forzaste un sismo cortical a más de 60 km de profundidad: la corteza bajo el Magdalena Medio tiene del orden de 30 a 45 km (por confirmar); escenario hipotético.' : '';
    out('aviso-tipo').textContent = av; out('aviso-tipo').hidden = !av;
    out('rhip').textContent = `Distancia al foco (hipocentral): ${nv(Math.hypot(p.distancia_epicentral_km, h), 0)} km (cálculo propio: √(distancia² + profundidad²)).`;
    out('escala').hidden = radioV('escala') !== 'nsr10';
    const e = ESC.find((x) => x.id === ctl('escenario').value);
    const html = e ? `<b>${esc(e.nombre)}</b>: Mw ${n(e.Mw, 1)}, ${nv(e.profundidad_km, 0)} km de profundidad, a ${nv(e.distancia_epicentral_km, 0)} km. ${esc(e.justificacion || '')}${e.aviso ? ` <span class="pill">${esc(e.aviso)}</span>` : ''} <span class="pill">por confirmar</span>`
      : 'Combinación elegida a mano. Si queda fuera de la sismicidad conocida, el cálculo lo avisa.';
    // es una región viva: se reescribe solo si cambia (si no, el lector de pantalla la repite con cada flecha de un control)
    if (html !== ultimoEscenario) { ultimoEscenario = html; out('escenario').innerHTML = html; }
  }
  function aplicarEscenario(id) {
    const e = ESC.find((x) => x.id === id);
    if (!e) return;
    ctl('Mw').value = e.Mw; ctl('h').value = e.profundidad_km; ctl('d').value = e.distancia_epicentral_km; ctl('regimen').value = 'auto';
    textosControles();
  }
  ctl('escenario').addEventListener('change', () => aplicarEscenario(ctl('escenario').value));
  for (const k of ['Mw', 'h', 'd']) ctl(k).addEventListener('input', () => {
    const e = ESC.find((x) => +x.Mw === +ctl('Mw').value && +x.profundidad_km === +ctl('h').value && +x.distancia_epicentral_km === +ctl('d').value);
    ctl('escenario').value = e ? e.id : 'personalizado';
    textosControles();
  });
  elPanel.addEventListener('input', (e) => { if (e.target.matches('input, select')) textosControles(); });
  elPanel.addEventListener('change', (e) => { if (e.target.matches('input[type=radio]')) textosControles(); });
  textosControles();

  // ================================================================ motor: trabajador, simulado o respaldo (7.5)
  let motor = null, motorP = null, ultimoIniciar = null, listo = null, estructura = null;
  const msgIniciar = (id = 'torre') => ({ tipo: 'iniciar', v: 1, id, url_estructura: new URL(URL_ESTRUCTURA, location.href).href, url_amenaza: new URL(URL_AMENAZA, location.href).href, opciones: opcionesModelo() });
  // cliente de un trabajador de módulo: resuelve cuando llega «cargado» (3 s como máximo)
  function abrirTrabajador() {
    return new Promise((ok, mal) => {
      let w;
      try { w = new Worker(URL_TRABAJADOR, { type: 'module' }); } catch (e) { mal(e); return; }
      const fin = (e) => { clearTimeout(t); w.removeEventListener('message', alMsg); w.removeEventListener('error', alErr); if (e) { w.terminate(); mal(e); } else ok(w); };
      const t = setTimeout(() => fin(new Error('el trabajador no respondió en 3 s')), 3000);
      const alMsg = (ev) => { if (ev.data?.tipo === 'cargado') fin(); };
      const alErr = (ev) => { ev.preventDefault?.(); fin(new Error(ev.message || 'el trabajador no cargó')); };
      w.addEventListener('message', alMsg); w.addEventListener('error', alErr);
    });
  }
  function clienteTrabajador(w0, tipo) {
    let w = w0, nId = 0, pendientes = new Map(), vivo = null;
    const conectar = (w1) => {
      w = w1;
      w.addEventListener('message', (ev) => {
        const m = ev.data || {};
        const p = pendientes.get(m.id);
        if (!p) return;
        if (m.tipo === 'progreso') { p.progreso?.(m.fraccion, m.t_s); return; }
        pendientes.delete(m.id);
        if (m.tipo === 'error') p.mal(Object.assign(new Error(m.mensaje || 'error del motor'), { codigo: m.codigo, detalle: m.detalle }));
        else p.ok(m);
      });
      w.addEventListener('error', (ev) => { ev.preventDefault?.(); for (const p of pendientes.values()) p.mal(Object.assign(new Error(ev.message || 'falla del trabajador'), { codigo: 'interno' })); pendientes.clear(); });
    };
    conectar(w);
    const pedir = (msg, progreso) => new Promise((ok, mal) => { const id = `${msg.tipo}-${++nId}`; pendientes.set(id, { ok, mal, progreso }); w.postMessage({ ...msg, id }); });
    // después de cancelar (terminate) se abre otro trabajador y se repite «iniciar» antes del siguiente pedido
    const asegurar = async () => {
      if (w) return;
      vivo ??= (async () => { const w1 = await abrirTrabajador(); conectar(w1); await pedir(ultimoIniciar); })().finally(() => { vivo = null; });
      await vivo;
    };
    return {
      tipo,
      async iniciar(msg) { await asegurar(); ultimoIniciar = msg; return pedir(msg); },
      async movimiento(params) { await asegurar(); return pedir({ tipo: 'movimiento', params }); },
      async analizar(params, opciones, progreso) { await asegurar(); const r = await pedir({ tipo: 'analizar', params, opciones }, progreso); return r.resultados; },
      async serie(elemento) { await asegurar(); return pedir({ tipo: 'serie_elemento', elemento }); },
      cancelar() {
        if (!w) return;
        w.terminate(); w = null;
        for (const p of pendientes.values()) p.mal(Object.assign(new Error('cancelado'), { codigo: 'cancelado' }));
        pendientes.clear();
      },
      cerrar() { this.cancelar(); },
    };
  }
  // respaldo: la misma lógica del motor (motor.js) en este hilo, cediendo por tiempo
  async function clienteHilo() {
    const mod = await import(URL_MOTOR);
    const m = mod.crearMotor();
    let ac = null;
    const prog = (cb) => (a, b) => (a && typeof a === 'object' ? cb?.(a.fraccion, a.t_s) : cb?.(a, b));
    return {
      tipo: 'hilo_principal',
      async iniciar(msg) { ultimoIniciar = msg; const r = await m.iniciar(msg); return r?.listo || r; },
      async movimiento(params) { return m.movimiento(params); },
      async analizar(params, opciones, progreso) {
        ac = new AbortController();
        const r = await m.analizar(params, { ...opciones, presupuesto_ms: 12, ceder }, prog(progreso), ac.signal);
        if (ac.signal.aborted) throw Object.assign(new Error('cancelado'), { codigo: 'cancelado' });
        return r?.resultados || r;
      },
      async serie(elemento) { return m.serieElemento(elemento); },
      cancelar() { ac?.abort(); m.cancelar?.(); },
      cerrar() { this.cancelar(); },
    };
  }
  function obtenerMotor() {
    if (motorP) return motorP;
    motorP = (async () => {
      if (typeof Worker === 'function') {
        let c = null;
        try {
          const w = await abrirTrabajador();
          c = clienteTrabajador(w, SIMULADO ? 'simulado' : 'trabajador');
          listo = await c.iniciar(msgIniciar());
          return c;
        } catch (e) {
          // sin «cargado» en 3 s o con un error antes de «listo»: se cierra el trabajador y se usa el respaldo (7.5)
          c?.cerrar();
          console.info('Simulador sísmico: se usa el respaldo en el hilo principal.', e?.message || e);
        }
      }
      const h = await clienteHilo();
      listo = await h.iniciar(msgIniciar());
      return h;
    })();
    motorP.then((m) => { motor = m; }, () => { motorP = null; });
    return motorP;
  }
  ctx.motor = obtenerMotor;   // 8.6: el trabajador o, si falla, el respaldo de motor.js
  // el modelo se vuelve a armar si cambian la histéresis o los muros no estructurales
  let modeloArmado = JSON.stringify(opcionesModelo());
  async function asegurarModelo() {
    const m = await obtenerMotor();
    const ahora = JSON.stringify(opcionesModelo());
    if (ahora !== modeloArmado) { listo = await m.iniciar(msgIniciar()); modeloArmado = ahora; }
    if (!estructura) estructura = await leerJSON(URL_ESTRUCTURA);
    return m;
  }

  // ================================================================ la estructura en 3D
  let est3d = null, info = null, R = null, mov = null, resumen = null, paso = 0, escala = 1, campo = 'max', elegido = null, pisoEq = '';
  const eqPorUnidad = new Map();
  const rotulos = [];
  // etiquetas de deriva: un ancla sin tamaño (sismo-lbl) con la caja dentro, que se abre hacia la izquierda del punto
  // nacen ocultas: sin resultado no tienen deriva que mostrar (serían píldoras vacías); se ven con el primer actualizar()
  const etiqueta = (html, pos, padre) => { const o = st.label(html, 'sismo-lbl', pos, padre); rotulos.push(o); o.visible = dentro && !!R; return o; };
  function armarInfo(L, est) {
    const nodos = L.nodos, elementos = L.elementos, nN = nodos.length;
    const niveles = [], porticos = {}, muros = [], nivelNodo = new Int16Array(nN), secciones = est?.secciones || {};
    const porNodo = new Map();
    let off = 0;
    for (const b of est?.bloques || []) {
      (b.niveles || []).forEach((q) => niveles.push({ id: q.id, z: +q.z, cm: q.cm, contorno: q.contorno, h: +q.altura_entrepiso, bloque: b.id }));
      for (const p of b.porticos || []) { porticos[p.id] = { direccion: p.direccion, coordenada: p.coordenada }; (p.nodos || []).forEach((q) => porNodo.set(q.id, q.nivel ? off + q.nivel : 0)); }
      for (const r of b.resortes || []) {
        if (!Array.isArray(r.posicion) || r.posicion.length < 4) continue;
        const k = off + (+r.nivel || 1);
        muros.push({ id: r.id, a: [r.posicion[0], r.posicion[1]], b: [r.posicion[2], r.posicion[3]], k, h: +r.h || 0, hEntrepiso: niveles[k - 1]?.h || +r.h, aislado: !!r.aislado, estados: r.estados_de_dano || [] });
      }
      off += (b.niveles || []).length;
    }
    const NL = L.resumen?.niveles;
    if (!niveles.length || (NL && NL !== niveles.length) || nodos.some((q) => !porNodo.has(q.id))) {
      // sin el archivo de la estructura (o si no coincide): niveles por la cota de los nodos y contorno rectangular
      niveles.length = 0; muros.length = 0;
      const zs = [...new Set(nodos.map((q) => +q.xyz[2].toFixed(3)))].sort((a, b) => a - b).filter((z) => z > 0.01);
      const cm = Array.isArray(L.resumen?.cm?.[0]) ? L.resumen.cm : null;
      zs.forEach((z, k) => {
        const en = nodos.filter((q) => Math.abs(q.xyz[2] - z) < 0.01), xs = en.map((q) => q.xyz[0]), ys = en.map((q) => q.xyz[1]);
        const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
        niveles.push({ id: `N${k + 1}`, z, cm: cm?.[k] || (Array.isArray(L.resumen?.cm) && !cm ? L.resumen.cm : [(x0 + x1) / 2, (y0 + y1) / 2]), contorno: [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], h: z - (zs[k - 1] || 0) });
      });
      nodos.forEach((q, i) => { const k = zs.findIndex((z) => Math.abs(z - q.xyz[2]) < 0.01); nivelNodo[i] = k + 1; });
    } else nodos.forEach((q, i) => { nivelNodo[i] = porNodo.get(q.id); });
    return { elementos, nodos, niveles, nivelNodo, porticos, secciones, muros, elemSeccion: elementos.map((e) => e.seccion) };
  }
  function construir3D() {
    if (est3d) { st.scene.remove(est3d.grupo); quitarRotulos(); est3d.dispose(); est3d = null; }
    info = armarInfo(listo, estructura);
    est3d = crearEstructura3D(info, { tier: engine.tier, colores: tokens(), renderer: engine.renderer, etiqueta });
    const v = engine.renderer.getSize(new THREE.Vector2()); est3d.resolucion(v.x, v.y);
    if (dentro) { st.scene.add(est3d.grupo); rotulos.forEach((o) => { o.visible = !!R; }); }
    llenarElementos();
    pisosEquipos();
  }
  function quitarRotulos() {
    rotulos.forEach((o) => { o.element.remove(); o.parent?.remove(o); const k = st._labels.indexOf(o); if (k >= 0) st._labels.splice(k, 1); });
    rotulos.length = 0;
  }
  const NLv = () => (R ? R.u.length / R.t.length / 3 : info?.niveles.length || 0);
  const nivelSuperior = () => { let k = 0; (info?.niveles || []).forEach((q, j) => { if (q.z > info.niveles[k].z) k = j; }); return k; };
  function maxCubierta() {
    if (!R) return 0;
    const N = NLv(), k = nivelSuperior(), nt = R.t.length;
    let m = 0;
    for (let i = 0; i < nt; i++) { const o = (i * N + k) * 3; m = Math.max(m, Math.hypot(R.u[o], R.u[o + 1])); }
    return m;
  }
  function escalaAuto() {
    const m = maxCubierta();
    if (!(m > 0)) return 1;
    const bruto = 1.5 / m;
    return EXAGERACIONES.reduce((a, e) => (Math.abs(Math.log(e / bruto)) < Math.abs(Math.log(a / bruto)) ? e : a), 1);
  }
  function textoEscala() {
    const m = maxCubierta();
    const v = ctl('exag').value;
    escala = v === 'auto' ? escalaAuto() : +v;
    ctl('exag').options[0].textContent = `Automática (×${escala})`;
    out('exag').textContent = m > 0 ? `×${escala}: ${nv(m * 100, 2)} cm reales (el mayor desplazamiento de la cubierta) se dibujan como ${nv(m * escala, 2)} m. Con ×1 se ve a escala real.` : '';
  }

  // ================================================================ leyenda (8.3)
  function leyenda() {
    const [t, d] = CAMPOS[campo];
    const mez = 'color-mix(in srgb-linear, var(--good) 50%, var(--warn))';
    const muros = info?.muros?.length;
    out('leyenda').innerHTML = `<p><b>${t}:</b> ${d}.</p>
      <ul class="sismo-bins">
        <li><i style="background:var(--good)"></i>≤ ${n(CORTES_DC[0], 1)}</li><li><i style="background:${mez}"></i>${n(CORTES_DC[0], 1)} a ${n(CORTES_DC[1], 1)}</li>
        <li><i style="background:var(--warn)"></i>${n(CORTES_DC[1], 1)} a ${n(CORTES_DC[2], 1)}</li><li><i style="background:var(--bad)"></i>más de ${n(CORTES_DC[2], 1)}${campo === 'rotacion' ? ': superó IO' : ': supera la capacidad esperada'}</li>
      </ul>
      <p><i class="sismo-rot"></i>rótula que fluyó (tamaño: θp/θp de IO); anillo: superó <i class="sismo-an" style="--c:var(--warn)"></i>IO, <i class="sismo-an" style="--c:color-mix(in srgb-linear, var(--warn) 50%, var(--bad))"></i>LS o <i class="sismo-an" style="--c:var(--bad)"></i>CP</p>
      <p><i class="sismo-ln"></i>gris fino: estructura sin deformar · placas: losas (diafragma rígido de cada nivel) · <i class="sismo-sel"></i>violeta: el elemento elegido</p>
      ${muros ? '<p><i class="sismo-mm"></i>paneles: muros de mampostería, del color de su daño (verde sin daño a rojo colapso)</p>' : ''}
      <p>Exageración ×${escala}</p>`;
    out('campo').textContent = `La leyenda compara con ${d}: verde hasta la mitad de la capacidad; rojo, por encima.`;
  }

  // ================================================================ tiempo: deslizador y reproducción (8.1)
  let reproduciendo = false, t0 = 0, i0 = 0, velocidad = 1;
  const grafs = {};
  function irAPaso(i, desdeDeslizador = false) {
    if (!R) return;
    const nt = R.t.length;
    paso = Math.max(0, Math.min(nt - 1, i | 0));
    if (!desdeDeslizador) ctl('t').value = paso;
    const ax = R.ag[paso * 2], ay = R.ag[paso * 2 + 1], pga = Math.hypot(ax, ay) / g0;
    const tf = R.t[nt - 1];
    const txt = `t = ${n(R.t[paso], 2)} s de ${n(tf, tf < 10 ? 2 : 1)} · suelo ${n(pga, 3)} g`;
    out('t').textContent = txt;
    ctl('t').setAttribute('aria-valuetext', txt);
    est3d?.actualizar(paso, R, escala, campo);
    for (const g of Object.values(grafs)) g?.cursor?.(paso);
    fichaPaso();
    st.invalidate();
  }
  // «Reproducir» avanza el índice con el reloj real en su propio requestAnimationFrame: no depende de que el recuadro esté
  // a la vista (Engine.frame no corre las funciones de onFrame fuera de la pantalla) y así los cursores de las gráficas
  // siguen mientras la persona las lee abajo; al volver al recuadro el modelo está en el mismo paso
  let rafRep = 0;
  function bucleRep() {
    rafRep = 0;
    if (!reproduciendo || !R || !dentro) return;
    const dt = R.opciones?.dt_salida_s || (R.t[1] - R.t[0]) || 0.02, nt = R.t.length;
    const i = i0 + Math.floor(((performance.now() - t0) / 1000) * velocidad / dt);
    if (i >= nt - 1) { irAPaso(nt - 1); reproducir(false); return; }
    if (i !== paso) irAPaso(i);
    rafRep = requestAnimationFrame(bucleRep);
  }
  function reproducir(on) {
    reproduciendo = on && !!R && dentro;
    const b = $(elHud, '[data-s="play"]');
    b.setAttribute('aria-pressed', String(reproduciendo));
    b.textContent = reproduciendo ? 'Pausa' : 'Reproducir';
    if (reproduciendo) { if (paso >= R.t.length - 1) irAPaso(0); i0 = paso; t0 = performance.now(); if (!rafRep) rafRep = requestAnimationFrame(bucleRep); }
    else { cancelAnimationFrame(rafRep); rafRep = 0; st.updateShadows(); }
  }
  $(elHud, '[data-s="play"]').addEventListener('click', () => reproducir(!reproduciendo));
  ctl('t').addEventListener('input', () => { if (reproduciendo) reproducir(false); irAPaso(+ctl('t').value, true); });
  elHud.querySelectorAll('[data-vel]').forEach((b) => b.addEventListener('click', () => {
    velocidad = +b.dataset.vel;
    elHud.querySelectorAll('[data-vel]').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    if (reproduciendo) { i0 = paso; t0 = performance.now(); }
  }));
  ctl('exag').addEventListener('change', () => { textoEscala(); leyenda(); irAPaso(paso); });
  elPanel.querySelectorAll('[data-campo]').forEach((b) => b.addEventListener('click', () => {
    campo = b.dataset.campo;
    elPanel.querySelectorAll('[data-campo]').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    leyenda(); irAPaso(paso);
  }));

  // un solo cuadro por función (6.8): resolución de las líneas; false si no hay nada que redibujar (la reproducción
  // avanza en su propio bucle e invalida el cuadro con irAPaso)
  const _tam = new THREE.Vector2();
  let tamPrev = '';
  const enCuadro = () => {
    if (!dentro || !est3d) return false;
    engine.renderer.getSize(_tam);
    const k = `${_tam.x}x${_tam.y}`;
    if (k === tamPrev) return false;
    tamPrev = k; est3d.resolucion(_tam.x, _tam.y);
    return true;
  };
  st.onFrame(enCuadro);

  // ================================================================ selección de elementos (clic en el modelo o lista)
  const ray = new THREE.Raycaster(), ptr = new THREE.Vector2();
  let abajo = null;
  const lienzo = engine.renderer.domElement;
  const alBajar = (e) => { if (dentro && st.isActive()) abajo = { x: e.clientX, y: e.clientY, t: performance.now() }; };
  const alSubir = (e) => {
    if (!abajo || !dentro || !est3d || !st.isActive()) { abajo = null; return; }
    const d = Math.hypot(e.clientX - abajo.x, e.clientY - abajo.y), dt = performance.now() - abajo.t;
    abajo = null;
    if (d > 5 || dt > 400) return;   // terminar un arrastre no selecciona
    const r = lienzo.getBoundingClientRect();
    ptr.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ptr, st.camera);
    const id = est3d.pick(ray);
    if (id) elegir(id);
  };
  lienzo.addEventListener('pointerdown', alBajar);
  lienzo.addEventListener('pointerup', alSubir);
  const nombreElemento = (e) => {
    if (!e) return '';
    const tipo = e.tipo === 'muro_concreto' ? 'Muro' : e.tipo === 'viga' ? 'Viga' : 'Columna';
    const id = e.tipo === 'columna' && e.fisico ? e.fisico : e.id;
    return `${tipo} ${id} · ${e.tipo === 'viga' ? 'nivel' : 'piso'} ${e.nivel}`;
  };
  const elemPorId = () => new Map((listo?.elementos || []).map((e, k) => [e.id, k]));
  let mapaE = new Map();
  function llenarElementos() {
    mapaE = elemPorId();
    const s = ctl('elemento'), env = R?.envolventes?.dc_max;
    const vistos = new Set(), filas = [];
    (listo?.elementos || []).forEach((e, k) => {
      const clave = e.tipo === 'columna' && e.fisico ? e.fisico : e.id;
      if (vistos.has(clave)) { const f = filas.find((x) => x.clave === clave); if (f && env) f.dc = Math.max(f.dc, env[k]); return; }
      vistos.add(clave);
      filas.push({ clave, id: e.id, nombre: nombreElemento(e), dc: env ? env[k] : 0 });
    });
    filas.sort((a, b) => b.dc - a.dc || a.nombre.localeCompare(b.nombre, 'es', { numeric: true }));
    s.innerHTML = filas.map((f) => opt(f.id, `${escH(f.nombre)}${env ? ` · D/C máx. ${n(f.dc, 2)}` : ''}`, f.id === elegido)).join('');
  }
  ctl('elemento').addEventListener('change', () => elegir(ctl('elemento').value));
  let pedidoSerie = 0, seriesPendientes = false;
  async function elegir(id) {
    elegido = id;
    est3d?.seleccionar(id);
    if (ctl('elemento').value !== id) ctl('elemento').value = id;
    fichaElemento();
    st.invalidate();
    if (!R || !motor) return;
    const mio = ++pedidoSerie;
    const ids = est3d?.elementosDe(id) || [id];
    try {
      const series = await Promise.all(ids.map((x) => motor.serie(x)));
      if (mio !== pedidoSerie) return;
      if (!dentro) { seriesPendientes = true; return; }
      seriesPendientes = false;
      graficasElemento(ids, series);
    } catch (e) {
      if (e?.codigo === 'cancelado' || mio !== pedidoSerie) return;
      if (!dentro) { seriesPendientes = true; return; }
      // después de cancelar un cálculo el trabajador nuevo no guarda las series del anterior
      console.warn('Simulador sísmico: serie del elemento', e);
      for (const k of ['histeresis', 'momentos', 'fuerzas']) cerrarGraf(k);
      out('el-titulo').textContent = `${nombreElemento(listo.elementos[mapaE.get(id)])}: sus series en el tiempo no están disponibles (se pierden al cancelar un cálculo); vuelve a calcular para verlas.`;
    }
  }

  // ================================================================ ficha del elemento elegido (torre.ficha.modo)
  function fichaElemento() {
    const k = mapaE.get(elegido), e = listo?.elementos?.[k];
    if (!e) { elFicha.innerHTML = '<p class="note">Toca una columna, una viga o un muro en el modelo para ver sus esfuerzos.</p>'; return; }
    const sec = info?.secciones?.[e.seccion] || {}, E = R?.envolventes;
    const ids = est3d?.elementosDe(elegido) || [elegido];
    const filas = ids.map((id) => {
      const j = mapaE.get(id), el = listo.elementos[j];
      if (!E) return '';
      const thi = E.thp_max?.[j * 2], thj = E.thp_max?.[j * 2 + 1], tfi = E.t_primera_fluencia?.[j * 2], tfj = E.t_primera_fluencia?.[j * 2 + 1];
      return `<dt>Pórtico ${escH(el.portico)}</dt><dd>D/C máx. ${n(E.dc_max[j], 2)} (${GOBIERNA[E.gobierna?.[j]] || '—'}) a los ${n(E.t_dc_max?.[j], 2)} s</dd>
        <dt>Momento máx. i / j</dt><dd>${nv(E.Mi_max?.[j], 1)} / ${nv(E.Mj_max?.[j], 1)} kN·m</dd>
        <dt>Cortante máx.</dt><dd>${nv(E.V_max?.[j], 1)} kN${sec.Vn_e_kN ? ` (Vn esperado ${nv(sec.Vn_e_kN, 0)} kN)` : ''}</dd>
        <dt>Axial (tracción +)</dt><dd>${nv(E.N_min?.[j], 1)} a ${nv(E.N_max?.[j], 1)} kN</dd>
        <dt>θp máx. i / j</dt><dd>${G.sig(thi, 2)} / ${G.sig(thj, 2)} rad</dd>
        <dt>Primera fluencia</dt><dd>${tfi >= 0 || tfj >= 0 ? [tfi, tfj].map((v, q) => (v >= 0 ? `${q ? 'j' : 'i'}: ${n(v, 2)} s` : '')).filter(Boolean).join(' · ') : 'no fluyó'}</dd>`;
    }).join('');
    elFicha.innerHTML = `<h4>${escH(nombreElemento(e))}</h4>
      <dl class="kv">
        <dt>Sección</dt><dd>${escH(e.seccion || '—')}${sec.b && sec.h ? `: ${n(sec.b, 2)} × ${n(sec.h, 2)} m` : ''}</dd>
        ${sec.Mn_e_kNm ? `<dt>Mn esperado</dt><dd>${nv(sec.Mn_e_kNm, 0)} kN·m</dd>` : ''}
        ${sec.theta_p_IO ? `<dt>θp de IO / LS / CP</dt><dd>${G.sig(sec.theta_p_IO, 2)} / ${G.sig(sec.theta_p_LS, 2)} / ${G.sig(sec.theta_p_CP, 2)} rad</dd>` : ''}
        <dt>En este paso</dt><dd data-o="el-paso">—</dd>
        ${filas}
      </dl>
      <p class="note">Sus series en el tiempo y el lazo M–θp de sus rótulas están abajo, en «Lo que calculó el simulador».</p>`;
    fichaPaso();
  }
  function fichaPaso() {
    const o = elFicha.querySelector('[data-o="el-paso"]');
    if (!o || !R) return;
    const nE = listo.elementos.length;
    const ids = est3d?.elementosDe(elegido) || [elegido];
    o.textContent = ids.map((id) => { const j = mapaE.get(id); return `${listo.elementos[j].portico}: D/C ${n(R.dc[paso * nE + j] / 100, 2)}`; }).join(' · ') + ` (t = ${n(R.t[paso], 2)} s)`;
  }

  // ================================================================ gráficas (8.4)
  const desentrelazar = (a, paso2, k, nt) => { const o = new Float32Array(nt); for (let i = 0; i < nt; i++) o[i] = a[i * paso2 + k]; return o; };
  function cerrarGraf(k) { grafs[k]?.dispose?.(); grafs[k] = null; }
  const caja = (k) => elG.querySelector(`[data-g="${k}"]`);
  function graficasMovimiento() {
    if (!mov) return;
    const f = R?.factor_escala && R?.opciones?.escala === 'nsr10' ? R.factor_escala : (typeof R?.opciones?.escala === 'number' ? R.opciones.escala : 1);
    const T = mov.espectro?.T, m = (a) => (a && f !== 1 ? Float32Array.from(a, (v) => v * f) : a);
    const modos = listo?.modos?.periodos_s || [];
    cerrarGraf('espectros');
    grafs.espectros = G.espectros(caja('espectros'), {
      T, sa_x: m(mov.espectro?.Sa_x), sa_y: m(mov.espectro?.Sa_y),
      nsr10: { T: mov.nsr10?.T, con_I: mov.nsr10?.con_I, sin_I: mov.nsr10?.sin_I, umbral_dano: mov.nsr10?.umbral_dano },
      gmpe: (mov.gmpe || []).map((q) => ({ nombre: limpio(q.nombre), peso: q.peso, T: q.T, mediana: q.mediana_g, sigma: q.sigma_ln })),
      marcas: modos.slice(0, 3).map((Tm, k) => ({ T: Tm, etiqueta: `T${k + 1}` })), nombres: ['Este sismo, componente 1', 'Este sismo, componente 2'],
      nota: `Cuánto se aceleraría un oscilador de cada período con las componentes 1 y 2 de este sismo${f !== 1 ? ` (multiplicadas por ${n(f, 2)})` : ''}, contra el espectro de diseño de la NSR-10 para Yondó y las ecuaciones empíricas (GMPE) del tipo de sismo. Marcas: períodos de los tres primeros modos de la torre.`,
    });
    cerrarGraf('fourier');
    grafs.fourier = G.fourier(caja('fourier'), { f: mov.fourier?.f, A_x: mov.fourier?.A_x, A_y: mov.fourier?.A_y, objetivo: mov.fourier?.objetivo || mov.fourier?.A_objetivo || null });
  }
  function graficasResultado() {
    const nt = R.t.length, N = NLv();
    cerrarGraf('acel');
    grafs.acel = G.acelerograma(caja('acel'), { t: R.t, ax: desentrelazar(R.ag, 2, 0, nt), ay: desentrelazar(R.ag, 2, 1, nt) });
    const E = R.envolventes || {};
    const dmx = E.deriva_max ? desentrelazar(E.deriva_max, 2, 0, N) : null, dmy = E.deriva_max ? desentrelazar(E.deriva_max, 2, 1, N) : null;
    const mamp = (info?.muros || []).some((w) => !w.aislado) || radioV('muros') === 'confinados';
    cerrarGraf('derivas');
    grafs.derivas = G.derivas(caja('derivas'), {
      pisos: Array.from({ length: N }, (_, k) => `Entrepiso ${k + 1}`), x: dmx, y: dmy, vector: E.deriva_vector_max,
      paso: R.derivas_vector ? (i) => R.derivas_vector.subarray(i * N, i * N + N) : null,
      limite: estructura?.limites?.deriva ?? 0.01, umbral: estructura?.limites?.deriva_umbral_dano ?? 0.004, umbral_mamposteria: estructura?.limites?.deriva_umbral_dano_mamposteria ?? 0.002, mamposteria: mamp,
    });
    const Vs = +estructura?.diseno?.Vs_kN || 0, Rf = +estructura?.diseno?.R || 0;
    cerrarGraf('cortante');
    grafs.cortante = G.serieTiempo(caja('cortante'), {
      t: R.t, unidad: 'kN', titulo: 'Cortante en la base', aria: 'Cortante basal en x y en y contra el tiempo',
      nota: `Fuerza lateral que resisten los elementos del primer piso${Vs ? `, contra el cortante de diseño Vs = ${nv(Vs, 0)} kN y Vs/R = ${nv(Vs / (Rf || 1), 0)} kN (R = ${nv(Rf, 2)})` : ''}. La torsión está en la tabla.`,
      series: [{ nombre: 'Vx', y: desentrelazar(R.cortante_basal, 3, 0, nt) }, { nombre: 'Vy', y: desentrelazar(R.cortante_basal, 3, 1, nt) }],
      referencias: Vs ? [{ valor: Vs, etiqueta: 'Vs de diseño' }, ...(Rf ? [{ valor: Vs / Rf, etiqueta: 'Vs/R' }] : [])] : [], dec: 0,
    });
    const en = (k) => desentrelazar(R.energia, 6, k, nt);
    cerrarGraf('energia');
    grafs.energia = G.energia(caja('energia'), { t: R.t, entrada: en(0), cinetica: en(1), elastica: en(2), amortiguada: en(3), histeretica: en(4), pdelta: en(5) });
    graficasMovimiento();
  }
  function graficasElemento(ids, series) {
    const k0 = mapaE.get(ids[0]), e0 = listo.elementos[k0], sec = info?.secciones?.[e0.seccion] || {};
    out('el-titulo').textContent = `Elemento seleccionado: ${nombreElemento(e0)}`;
    const columna = e0.tipo !== 'viga';
    const ext = (q) => (columna ? (q ? 'cabeza' : 'pie') : `extremo ${q ? 'j' : 'i'}`);
    const lazos = [];
    series.forEach((s, q) => {
      const p = listo.elementos[mapaE.get(ids[q])].portico, pre = ids.length > 1 ? `${p}, ` : '';
      const xyz = listo.elementos[mapaE.get(ids[q])];
      const iAbajo = xyz.xyz_i[2] <= xyz.xyz_j[2];
      lazos.push({ nombre: `${pre}${ext(iAbajo ? 0 : 1)}`, theta: s.thp_i, M: s.Mi }, { nombre: `${pre}${ext(iAbajo ? 1 : 0)}`, theta: s.thp_j, M: s.Mj });
    });
    cerrarGraf('histeresis');
    grafs.histeresis = G.histeresis(caja('histeresis'), { lazos, My: sec.My_e_kNm || null, limites: { IO: sec.theta_p_IO, LS: sec.theta_p_LS, CP: sec.theta_p_CP } });
    const s0 = series[0];
    cerrarGraf('momentos');
    grafs.momentos = G.serieTiempo(caja('momentos'), { t: s0.t, unidad: 'kN·m', titulo: `Momentos en los extremos${ids.length > 1 ? ` (pórtico ${listo.elementos[k0].portico})` : ''}`, nota: 'Momentos antihorarios de los extremos i y j, desde el estado de gravedad.', series: [{ nombre: 'Mi', y: s0.Mi }, { nombre: 'Mj', y: s0.Mj }], dec: 1 });
    cerrarGraf('fuerzas');
    grafs.fuerzas = G.serieTiempo(caja('fuerzas'), { t: s0.t, unidad: 'kN', titulo: 'Cortante y fuerza axial', nota: 'Cortante del extremo más cargado y fuerza axial (tracción positiva).', series: [{ nombre: 'V', y: s0.V }, { nombre: 'N', y: s0.N }], dec: 1 });
    for (const k of ['histeresis', 'momentos', 'fuerzas']) grafs[k]?.cursor?.(paso);
  }

  // ================================================================ tabla de variables (8.4)
  function tabla() {
    if (!R) return;
    const meta = mov?.registro?.meta || {}, ix = mov?.registro?.intensidades?.x || {}, iy = mov?.registro?.intensidades?.y || {};
    const E = R.envolventes || {}, nt = R.t.length, N = NLv(), nE = listo.elementos.length;
    const modos = listo?.modos || {}, am = R.amortiguamiento || listo?.amortiguamiento || {};
    const filas = [];
    const fila = (v, valor, que) => filas.push(`<tr><td>${v}</td><td class="n" data-th="Valor">${valor}</td><td class="ancho" data-th="Qué es"><small class="note">${que}</small></td></tr>`);
    fila('Magnitud Mw', n(R.params?.Mw ?? leerParams().Mw, 1), 'Magnitud de momento elegida');
    fila('Momento sísmico M0', `${cientifico(meta.M0_N_m ?? 10 ** (1.5 * (R.params?.Mw ?? 6) + 16.05) * 1e-7)} N·m`, 'M0 = 10^(1,5·Mw + 16,05) dina·cm; cálculo propio');
    if (meta.f0_Hz != null) fila('Frecuencia de esquina f0', `${nv(meta.f0_Hz, 3)} Hz`, 'Fuente de Brune: por debajo de f0 el espectro crece; por encima es plano en aceleración');
    if (meta.delta_sigma_bar != null) fila('Caída de esfuerzos Δσ', `${nv(meta.delta_sigma_bar, 0)} bar`, 'Parámetro de la fuente del tipo de sismo (estudio de amenaza)');
    if (meta.Rhip_km != null) fila('Distancia al foco Rhip', `${nv(meta.Rhip_km, 1)} km`, 'Distancia hipocentral');
    if (meta.regimen) fila('Tipo de sismo', `${REGIMEN[meta.regimen] || esc(meta.regimen)}${meta.w_transicion != null && meta.w_transicion > 0 && meta.w_transicion < 1 ? ` (${nv(meta.w_transicion * 100, 0)} % intraplaca)` : ''}`, 'Según la profundidad (transición de 40 a 70 km) o forzado');
    if (meta.Q0 != null) fila('Atenuación Q(f)', `${nv(meta.Q0, 0)}·f^${nv(meta.eta, 2)}`, 'Calidad del camino: cuánto se pierde de energía al viajar');
    if (meta.kappa0_s != null) fila('κ0', `${nv(meta.kappa0_s, 3)} s`, 'Pérdida de altas frecuencias cerca del sitio');
    if (meta.Tgm_s != null) fila('Duración del movimiento fuerte Tgm', `${nv(meta.Tgm_s, 2)} s`, 'De la fuente y del camino');
    fila('Aceleración máxima del suelo PGA', `${nv(ix.pga_g, 3)} g · ${nv(iy.pga_g, 3)} g`, 'Componentes 1 y 2, en el registro completo (0,005 s)');
    if (ix.pgv_cm_s != null) fila('Velocidad máxima PGV', `${nv(ix.pgv_cm_s, 2)} · ${nv(iy.pgv_cm_s, 2)} cm/s`, 'Componentes 1 y 2');
    if (ix.arias_m_s != null) fila('Intensidad de Arias', `${G.sig(ix.arias_m_s, 3)} · ${G.sig(iy.arias_m_s, 3)} m/s`, 'Energía del movimiento por unidad de masa');
    if (ix.d595_s != null) fila('Duración D5-95', `${nv(ix.d595_s, 2)} · ${nv(iy.d595_s, 2)} s`, 'Tiempo en que se acumula del 5 % al 95 % de la intensidad de Arias');
    (modos.periodos_s || []).slice(0, 3).forEach((T, k) => {
      const mp = modos.masa_participativa || {};
      fila(`Período T${k + 1}`, `${nv(T, 3)} s`, `Masa que mueve: ${pct(mp.x?.[k], 0)} en x, ${pct(mp.y?.[k], 0)} en y, ${pct(mp.rz?.[k], 0)} en giro`);
    });
    if (am.periodos_ancla_s) fila('Amortiguamiento de Rayleigh', `ξ = 5 % en ${nv(am.periodos_ancla_s[0], 3)} s y ${nv(am.periodos_ancla_s[1], 3)} s`, `ξ efectivo de los modos: ${Array.from(am.xi_modos || []).slice(0, 12).map((x) => n(x * 100, 1)).join(' · ')} %`);
    if (R.opciones?.escala === 'nsr10') fila('Factor de escala NSR-10', `×${n(R.factor_escala, 3)}`, `Escenario hipotético; el ajuste del suelo dio ${R.iteraciones_escala ?? 0} vueltas`);
    fila('Paso de cálculo', `${nv(R.opciones?.dt_s, 3)} s`, R.opciones?.calidad === 'baja' ? 'calidad baja: paso de 0,01 s sobre el registro filtrado' : 'Newmark de aceleración promedio con Newton-Raphson; salida cada 0,02 s');
    if (E.deriva_vector_max) {
      let k = 0; for (let q = 1; q < N; q++) if (E.deriva_vector_max[q] > E.deriva_vector_max[k]) k = q;
      fila('Deriva vectorial máxima', pct(E.deriva_vector_max[k], 3), `Entrepiso ${k + 1}, en la esquina x = ${nv(E.punto_deriva_vector?.[k * 2], 1)} m, y = ${nv(E.punto_deriva_vector?.[k * 2 + 1], 1)} m, a los ${n(E.t_deriva_vector_max?.[k], 2)} s; límite 1 % (diseño) y 0,4 % (umbral de daño)`);
    }
    if (R.calidad_numerica) {
      const q = R.calidad_numerica;
      fila('Índice de estabilidad máximo', G.sig(q.indice_estabilidad_max, 3), 'P-Delta: peso de encima por deriva sobre cortante por altura (NSR-10 A.6.2.3); bajo 0,1 el efecto es pequeño');
      fila('Calidad numérica', `${nv(q.pasos, 0)} pasos · ${nv(q.no_convergidos, 0)} sin converger`, `${nv(q.iteraciones_promedio, 2)} iteraciones por paso; error del balance de energía ${G.sig((q.error_energia_max || 0) * 100, 2)} %`);
    }
    if (E.dc_max) {
      let k = 0; for (let q = 1; q < nE; q++) if (E.dc_max[q] > E.dc_max[k]) k = q;
      fila('Mayor demanda/capacidad', n(E.dc_max[k], 2), `${escH(nombreElemento(listo.elementos[k]))}, por ${GOBIERNA[E.gobierna?.[k]] || '—'}, a los ${n(E.t_dc_max?.[k], 2)} s`);
    }
    if (R.rotulas) {
      const fin = new Uint8Array(nE);
      for (let i = 0; i < nt; i++) for (let k = 0; k < nE; k++) fin[k] |= R.rotulas[i * nE + k];
      let fl = 0, io = 0, ls = 0, cp = 0, vn = 0;
      for (let k = 0; k < nE; k++) { const b = fin[k]; fl += (b & 1 ? 1 : 0) + (b & 2 ? 1 : 0); io += (b & 4 ? 1 : 0) + (b & 8 ? 1 : 0); ls += (b & 16 ? 1 : 0) + (b & 32 ? 1 : 0); cp += b & 64 ? 1 : 0; vn += b & 128 ? 1 : 0; }
      fila('Rótulas', `${fl} fluyeron`, `${io} superaron ocupación inmediata (IO), ${ls} seguridad de la vida (LS) y ${cp} elementos prevención del colapso (CP); ${vn} elementos superaron su cortante esperado`);
    }
    const Vb = R.cortante_basal;
    if (Vb) { let vx = 0, vy = 0, tz = 0; for (let i = 0; i < nt; i++) { vx = Math.max(vx, Math.abs(Vb[i * 3])); vy = Math.max(vy, Math.abs(Vb[i * 3 + 1])); tz = Math.max(tz, Math.abs(Vb[i * 3 + 2])); } fila('Cortante basal máximo', `${nv(vx, 0)} · ${nv(vy, 0)} kN`, `x · y; momento torsor máximo ${nv(tz, 0)} kN·m`); }
    if (R.muros_mamposteria?.length) {
      const c = {}; R.muros_mamposteria.forEach((m) => { c[m.estado] = (c[m.estado] || 0) + 1; });
      fila('Muros de mampostería', ESTADOS_MURO.filter((s) => c[s]).map((s) => `${c[s]} ${ESTADO_MURO_TXT[s]}`).join(' · '), 'Por el estado de daño que alcanzó cada uno con su deriva');
    }
    if (R.equipos?.length) {
      const d = R.equipos.filter((q) => q.desliza), b = R.equipos.filter((q) => q.inicia_balanceo), fr = R.equipos.filter((q) => q.regimen === 'frontera');
      fila('Equipos sin anclar', `${d.length} deslizan · ${b.length} empiezan a balancearse`, `${fr.length} en la frontera; deslizamiento máximo ${nv(Math.max(0, ...d.map((q) => q.deslizamiento_max_m)) * 100, 2)} cm; si se caen no se calcula`);
    }
    out('tabla').innerHTML = `<table class="fichas sismo-tabla"><thead><tr><th>Variable</th><th class="n">Valor</th><th>Qué es</th></tr></thead><tbody>${filas.join('')}</tbody></table>`;
  }
  // los equipos que más sufrieron primero: los que se balancean o quedan en la frontera, después los que deslizan (por lo
  // que deslizaron), los estables por su cociente de vuelco y al final los anclados por la fuerza en su anclaje
  const MAX_FILAS_EQ = 30;
  const gravedadEq = (q) => (q.regimen === 'anclado' ? 0 : q.regimen === 'frontera' ? 4 : q.inicia_balanceo || q.regimen === 'balancea' ? 3 : q.desliza ? 2 : 1);
  function listaEquipos() {
    const el = out('equipos');
    if (!R?.equipos?.length) { el.innerHTML = ''; return; }
    const nombre = (u) => { const l = eqPorUnidad.get(u); return l ? esc(l.nombre) : escH(u); };
    const pisoDe = new Map(unidades.map((q) => [q.unidad, q.piso]));
    const orden = [...R.equipos].sort((a, b) => gravedadEq(b) - gravedadEq(a) || (b.deslizamiento_max_m || 0) - (a.deslizamiento_max_m || 0) || (b.razon_vuelco || 0) - (a.razon_vuelco || 0) || (b.fuerza_anclaje_kN || 0) - (a.fuerza_anclaje_kN || 0));
    const c = { desliza: 0, balancea: 0, frontera: 0, anclado: 0, estable: 0 };
    for (const q of R.equipos) {
      if (q.regimen === 'anclado') c.anclado++;
      else if (q.regimen === 'frontera') c.frontera++;
      else if (q.inicia_balanceo || q.regimen === 'balancea') c.balancea++;
      else if (q.desliza) c.desliza++;
      else c.estable++;
    }
    const filas = orden.slice(0, MAX_FILAS_EQ);
    el.innerHTML = `<h4>Equipos de la dotación en el sismo</h4>
      <p class="note">${nv(R.equipos.length, 0)} equipos entraron al cálculo: ${nv(c.desliza, 0)} deslizan, ${nv(c.balancea, 0)} empiezan a balancearse, ${nv(c.frontera, 0)} quedan en la frontera (deslizan y se balancean), ${nv(c.estable, 0)} quedan quietos y ${nv(c.anclado, 0)} están anclados. Cada uno es un bloque rígido sobre su losa: si la fricción alcanza antes, desliza; si no, empieza a balancearse (si se vuelca no se calcula). Los anclados reportan la fuerza que debe resistir el anclaje, sin los factores de la NSR-10.${R.equipos.length > MAX_FILAS_EQ ? ` Aquí van los ${MAX_FILAS_EQ} que más sufrieron.` : ''}</p>
      <div class="tbl-wrap"><table class="fichas sismo-equipos"><thead><tr><th>Equipo</th><th>Dónde</th><th>Qué le pasó</th><th class="n">Aceleración máx.</th><th class="n">Deslizamiento</th><th class="n">Balanceo o anclaje</th></tr></thead><tbody>
      ${filas.map((q) => `<tr><td>${nombre(q.unidad)}</td><td data-th="Dónde">${pisoDe.has(q.unidad) ? nombrePiso(pisoDe.get(q.unidad)) : '—'}</td><td data-th="Qué le pasó"><span class="sismo-eq" style="--c:${colorEq(q, true)}"></span>${REGIMEN_EQ[q.regimen] || escH(q.regimen)}</td><td class="n" data-th="Aceleración máx.">${nv(q.a_max_m_s2 / g0, 3)} g</td><td class="n" data-th="Deslizamiento">${q.desliza ? `${nv(q.deslizamiento_max_m * 1000, 1)} mm` : '—'}</td><td class="n" data-th="Balanceo o anclaje">${q.fuerza_anclaje_kN != null ? `${nv(q.fuerza_anclaje_kN, 2)} kN` : q.razon_vuelco != null ? `${nv(q.razon_vuelco, 2)} de la que lo hace balancear` : '—'}</td></tr>`).join('')}
      </tbody></table></div>`;
  }

  // ================================================================ dotación sobre las losas (8.3)
  const colorEq = (q, css = false) => {
    // sin resultado (no entró al cálculo) con el color de las líneas; anclado en gris
    const k = !q ? 'line' : q.regimen === 'anclado' ? 'muted' : q.regimen === 'frontera' ? 's7' : q.inicia_balanceo || q.regimen === 'balancea' ? 'bad' : q.desliza ? 'warn' : 'good';
    if (css) return `var(--${k})`;
    const t = tokens(); return k === 's7' ? t.s[6] : t[k];
  };
  // unidades del inventario ubicado (10.2) que se pueden poner sobre una losa: las de la torre (pisos 1 a 4, bloque
  // técnico y cubierta), con dimensiones en el catálogo, que no van dentro de otra ni son componentes de otra
  const PISOS_EQ = new Set([1, 2, 3, 4, 'BT', 'CUB']);
  function unidadesInventario() {
    const I = inventario;
    if (!I?.unidades?.length) return [];
    const col = Object.fromEntries((I.columnas_unidades || []).map((c, k) => [c, k]));
    return I.unidades.map((u) => {
      const l = I.lineas?.[u[col.linea_idx]] || {}, c = I.catalogo?.[l.modelo3d] || {};
      eqPorUnidad.set(u[col.id], l);
      return { unidad: u[col.id], piso: u[col.piso], x: +u[col.x], y: +u[col.y], z: +u[col.z] || 0, rot: +u[col.rot_z] || 0, montaje: u[col.montaje], dentro: u[col.dentro_de_idx] >= 0, comp: u[col.componente_de_idx] >= 0, cat: c, linea: l };
    }).filter((q) => PISOS_EQ.has(q.piso) && Array.isArray(q.cat?.dim) && q.cat.dim.length >= 3 && Number.isFinite(q.x) && Number.isFinite(q.y) && !q.dentro && !q.comp && q.montaje !== 'dentro');
  }
  let unidades = [];
  // EquipoRiesgo (7.4): los equipos apoyados en el piso o sobre un mueble, con masa, centro de gravedad y fricción en el
  // catálogo; los anclados también van (el motor da la fuerza que debe resistir su anclaje). Solo los pisos que tiene
  // el modelo (piso p descansa en el nivel p − 1) y anclajes que el motor conoce (7.4)
  const ANCLAJES = new Set(['apoyado', 'ruedas_con_freno', 'ruedas_sin_freno', 'sobre', 'anclado', 'pared', 'cielo', 'en_nucleo']);
  const equiposRiesgo = () => {
    const NL = +listo?.resumen?.niveles || info?.niveles?.length || 0;
    return unidades.filter((q) => (q.montaje === 'piso' || q.montaje === 'sobre' || q.cat.mont === 'piso')
      && (typeof q.piso !== 'number' || q.piso <= NL + 1) && ANCLAJES.has(q.cat.anc || 'apoyado')
      && q.cat.masa > 0 && q.cat.hcg > 0 && q.cat.mu >= 0 && q.cat.dim[0] > 0 && q.cat.dim[1] > 0).map((q) => ({
      unidad: q.unidad, piso: q.piso, x: q.x, y: q.y, z_sobre_piso: q.z, anclaje: q.cat.anc || 'apoyado', masa_kg: q.cat.masa, h_cg_m: q.cat.hcg, mu: q.cat.mu,
      bx_m: q.cat.dim[0] / 2, by_m: q.cat.dim[1] / 2, rot_z: q.rot,
    }));
  };
  const nombrePiso = (p) => (p === 'BT' ? 'Bloque técnico' : p === 'CUB' ? 'Cubierta' : `Piso ${p}`);
  function pisosEquipos() {
    unidades = unidadesInventario();
    const s = ctl('piso-eq'), pisos = [...new Set(unidades.map((q) => q.piso))].sort((a, b) => String(a).localeCompare(String(b), 'es', { numeric: true }));
    s.innerHTML = opt('', 'Ninguno', !pisoEq) + pisos.map((p) => opt(p, nombrePiso(p), String(p) === String(pisoEq))).join('');
    s.disabled = !pisos.length;
    out('piso-eq').textContent = pisos.length ? 'Cada equipo va sobre la losa de su piso, se mueve con ella y se colorea por lo que le pasó en el cálculo: verde estable, amarillo desliza, rojo empieza a balancearse, violeta en la frontera (las dos cosas), gris anclado. El anillo alrededor de los que deslizan mide lo que deslizaron, a escala real (el cálculo da cuánto, no hacia dónde).' : 'El inventario ubicado de la dotación todavía no está publicado: cuando esté, aquí se podrán ver los equipos sobre su losa.';
  }
  // nivel (1…N; 0 = el suelo) sobre el que descansa una unidad: piso p → nivel p − 1; bloque técnico → suelo (es otra
  // estructura); cubierta → el nivel más alto cuyo contorno la contiene (la del piso 4 o la terraza del piso 3)
  function nivelDe(q) {
    const N = info.niveles.length;
    if (q.piso === 'BT') return 0;
    if (q.piso === 'CUB') {
      for (let k = N; k >= 1; k--) if (dentroDe(q.x, q.y, info.niveles[k - 1].contorno)) return k;
      return N;
    }
    return Math.min(N, Math.max(0, (+q.piso || 1) - 1));
  }
  function dentroDe(x, y, poli) {
    if (!poli || poli.length < 3) return false;
    let d = false;
    for (let i = 0, j = poli.length - 1; i < poli.length; j = i++) {
      const [xi, yi] = poli[i], [xj, yj] = poli[j];
      if ((yi > y) !== (yj > y) && x <= ((xj - xi) * (y - yi)) / (yj - yi) + xi + 1e-9) d = !d;
    }
    return d;
  }
  function ponerEquipos() {
    if (!est3d) return;
    if (pisoEq === '') { est3d.ponerEquipos([]); return; }
    const res = new Map((R?.equipos || []).map((q) => [q.unidad, q]));
    const lista = unidades.filter((q) => String(q.piso) === String(pisoEq) && q.montaje !== 'cielo' && q.cat.mont !== 'cielo').map((q) => {
      const k = nivelDe(q), z0 = k > 0 ? info.niveles[k - 1].z : 0, r = res.get(q.unidad);
      return { unidad: q.unidad, k, x: q.x, y: q.y, z: z0 + q.z, rot: q.rot, dim: q.cat.dim, color: colorEq(r), desliza_m: r?.desliza ? +r.deslizamiento_max_m || 0 : 0 };
    });
    est3d.ponerEquipos(lista);
    st.invalidate();
  }
  ctl('piso-eq').addEventListener('change', () => { pisoEq = ctl('piso-eq').value; ponerEquipos(); });

  // ================================================================ cálculo
  let turnoCalc = 0, calculando = null, primero = true;
  // El estado es una región viva: cambia solo con la fase («Preparando», «Armando el movimiento», «Calculando» por cuartos,
  // «Listo»), no con cada mensaje de avance del motor (≈ 4 por segundo), para no encolar anuncios en el lector de pantalla.
  // El avance fino va en la barra <progress> (que expone su valor) y en una línea que no se anuncia
  const estado = (t, { progreso = null, detalle = null } = {}) => {
    if (out('estado').textContent !== t) out('estado').textContent = t;
    const p = out('progreso'), d = out('estado-det');
    p.hidden = progreso == null;
    if (progreso != null) p.value = progreso;
    d.hidden = !detalle;
    d.textContent = detalle || '';
  };
  function botones(enCurso) {
    const bC = $(elPanel, '[data-s="calcular"]'), bX = $(elPanel, '[data-s="cancelar"]'), foco = document.activeElement;
    bC.hidden = enCurso;
    bX.hidden = !enCurso;
    // el foco pasa al botón que aparece cuando el que lo tenía se oculta (si no, cae en <body>); si estaba en otra parte
    // (un cálculo pedido al entrar al modo o desde la QA) no se mueve
    if (enCurso && foco === bC) bX.focus({ preventScroll: true });
    if (!enCurso && foco === bX) bC.focus({ preventScroll: true });
  }
  async function calcular(p) {
    if (typeof p === 'string') { ctl('escenario').value = p; aplicarEscenario(p); }
    else if (p && typeof p === 'object') {
      if (p.escenario) { ctl('escenario').value = p.escenario; aplicarEscenario(p.escenario); }
      if (p.Mw != null) ctl('Mw').value = p.Mw;
      if (p.profundidad_km != null) ctl('h').value = p.profundidad_km;
      if (p.distancia_epicentral_km != null) ctl('d').value = p.distancia_epicentral_km;
      if (p.vs30_m_s != null) ctl('vs30').value = p.vs30_m_s;
      if (p.semilla != null) ctl('semilla').value = p.semilla;
      if (p.regimen) ctl('regimen').value = p.regimen;
      if (p.angulo_deg != null) ctl('ang').value = p.angulo_deg;
      if (p.escala) elPanel.querySelector(`input[name="sismo-escala"][value="${p.escala === 'nsr10' ? 'nsr10' : '1'}"]`).checked = true;
      if (p.calidad) elPanel.querySelector(`input[name="sismo-calidad"][value="${p.calidad}"]`).checked = true;
      textosControles();
    }
    if (calculando) cancelar(false);
    const mio = ++turnoCalc, t0c = performance.now();
    const params = leerParams(), opciones = { ...leerOpciones(), equipos: [] };
    calculando = { mio };
    botones(true);
    out('avisos').innerHTML = '';
    reproducir(false);
    try {
      estado('Preparando el motor y el modelo de la torre…', { progreso: 0 });
      const m = await asegurarModelo();
      if (mio !== turnoCalc) return { cancelado: true };
      // el modelo 3D se arma aquí solo la primera vez (para que la torre se vea mientras se calcula); si cambió el modelo
      // (otra histéresis u otros muros), se rehace cuando llega el resultado nuevo: si este cálculo se cancela o falla,
      // sigue a la vista el resultado anterior con su modelo, coloreado y seleccionable
      if (!est3d) construir3D();
      opciones.equipos = equiposRiesgo();
      estado('Armando el movimiento del suelo…', { progreso: 0.02 });
      const mv = await m.movimiento(params);
      if (mio !== turnoCalc) return { cancelado: true };
      mov = mv;
      avisos(mv, opciones);
      estado('Calculando la respuesta de la estructura…', { progreso: 0.05 });
      const Rn = await m.analizar(params, opciones, (f, ts) => {
        if (mio !== turnoCalc) return;
        const q = Math.min(3, Math.floor((f || 0) * 4));
        estado(q ? `Calculando la respuesta de la estructura: más del ${q * 25} %` : 'Calculando la respuesta de la estructura…', { progreso: 0.05 + 0.95 * (f || 0), detalle: `${nv((f || 0) * 100, 0)} %${ts != null ? ` · t = ${n(ts, 1)} s del registro` : ''}` });
      });
      if (mio !== turnoCalc) return { cancelado: true };
      R = Rn;
      calculando = null;
      botones(false);
      const dur = performance.now() - t0c;
      return mostrarResultado(dur);
    } catch (e) {
      if (mio !== turnoCalc) return { cancelado: true };
      calculando = null;
      botones(false);
      if (e?.codigo === 'cancelado') { estado('Cálculo cancelado.'); return { cancelado: true }; }
      // el mensaje técnico va a la consola (puede citar archivos); en la vista, solo qué pasó
      const msg = e?.codigo === 'no_converge' ? 'El cálculo no convergió en algún paso (la estructura perdió estabilidad numérica). Prueba con otra semilla o con un sismo menor.'
        : e?.codigo === 'datos' ? 'El modelo estructural de la torre o el estudio de amenaza todavía no están publicados: cuando estén, el simulador calcula aquí.'
          : 'El motor de cálculo no respondió. Vuelve a intentarlo.';
      estado(msg);
      console.warn('Simulador sísmico:', e);
      return { error: e?.codigo || 'interno', mensaje: e?.message };
    }
  }
  // los avisos citan a veces la sección del estudio de amenaza («ver seleccion_de_regimen»): eso no se lee en la web
  const sinCita = (a) => String(a ?? '').replace(/\s*\((?:ver|véase)\s+[a-z0-9_.]+\)/gi, '').replace(/\s*\b(?:ver|véase)\s+[a-z0-9]+(?:_[a-z0-9]+)+\b\.?/gi, '');
  function avisos(mv, opciones) {
    const L = (mv?.registro?.avisos || []).map((a) => `<li>${esc(sinCita(a))}</li>`);
    if (opciones.calidad === 'baja') L.push('<li>calidad baja: paso de 0,01 s</li>');
    if (opciones.escala === 'nsr10') L.push('<li>Escala «nivel de diseño NSR-10»: escenario hipotético.</li>');
    out('avisos').innerHTML = L.join('');
  }
  function mostrarResultado(dur) {
    const nt = R.t.length;
    construirSiCambia();
    // las etiquetas de deriva nacieron ocultas si el modelo se armó antes del primer resultado: ya tienen qué mostrar
    if (dentro) rotulos.forEach((o) => { o.visible = true; });
    textoEscala();
    leyenda();
    ctl('t').max = nt - 1; ctl('t').disabled = false; $(elHud, '[data-s="play"]').disabled = false;
    // elemento por defecto: el de mayor demanda/capacidad
    const E = R.envolventes;
    let kmax = 0;
    if (E?.dc_max) for (let q = 1; q < E.dc_max.length; q++) if (E.dc_max[q] > E.dc_max[kmax]) kmax = q;
    llenarElementos();
    graficasResultado();
    tabla();
    listaEquipos();
    ponerEquipos();
    const fe = R.opciones?.escala === 'nsr10' && Number.isFinite(+R.factor_escala);
    out('factor').textContent = fe ? `En este cálculo el registro se multiplicó por ${n(R.factor_escala, 2)}; el ajuste del suelo dio ${nv(R.iteraciones_escala ?? 0, 0)} vueltas.` : '';
    out('g-estado').textContent = `Sismo de Mw ${n(R.params?.Mw, 1)} a ${nv(R.params?.distancia_epicentral_km, 0)} km y ${nv(R.params?.profundidad_km, 0)} km de profundidad · ${nt} pasos de ${n(R.opciones?.dt_salida_s || 0.02, 2)} s · motor: ${NOMBRE_MOTOR[motor?.tipo] || motor?.tipo}.`;
    // paso inicial: el de mayor desplazamiento de la cubierta (el más informativo); sin movimiento reducido, se reproduce
    const N = NLv(), k = nivelSuperior();
    let ipk = 0, mx = -1;
    for (let i = 0; i < nt; i++) { const o = (i * N + k) * 3, v = Math.hypot(R.u[o], R.u[o + 1]); if (v > mx) { mx = v; ipk = i; } }
    irAPaso(ipk);
    elegir(listo.elementos[kmax]?.id);
    estado(`Listo: ${nt} pasos calculados en ${n(dur / 1000, 1)} s (${NOMBRE_MOTOR[motor?.tipo] || motor?.tipo}).`);
    if (!reducedMotion && !primeraVezSinAuto && dentro) { irAPaso(0); reproducir(true); }
    resumen = {
      id: R.id, escenario: ctl('escenario').value, params: R.params, opciones: R.opciones, motor: motor?.tipo, nt, N, nE: listo.elementos.length,
      escala, duracion_ms: Math.round(dur), pga_g: mov?.registro?.intensidades?.x?.pga_g ?? null,
      deriva_vector_max: E?.deriva_vector_max ? Math.max(...E.deriva_vector_max) : null, dc_max: E?.dc_max ? Math.max(...E.dc_max) : null,
      rotulas: contarRotulas(), graficas: Object.values(grafs).filter(Boolean).length,
    };
    Object.defineProperty(resumen, 'resultados', { value: R, enumerable: false });
    // para la QA (13.4): centro de masa de la cubierta esperado en el paso i = cm + u × escala
    Object.defineProperty(resumen, 'cubiertaEsperada', { enumerable: false, value: (i) => { const o = (i * N + k) * 3, nvl = info.niveles[k]; return [nvl.cm[0] + escala * R.u[o], nvl.cm[1] + escala * R.u[o + 1], nvl.z]; } });
    return resumen;
  }
  // extremos de elemento que fluyeron alguna vez en el sismo (bits 1 y 2 de Resultados.rotulas)
  function contarRotulas() {
    if (!R?.rotulas) return null;
    const nE = listo.elementos.length, nt = R.t.length, b = new Uint8Array(nE);
    for (let i = 0; i < nt; i++) for (let k = 0; k < nE; k++) b[k] |= R.rotulas[i * nE + k];
    let c = 0; for (let k = 0; k < nE; k++) c += (b[k] & 1 ? 1 : 0) + (b[k] & 2 ? 1 : 0);
    return c;
  }
  let primeraVezSinAuto = false;
  function construirSiCambia() { if (!est3d || info?.elementos !== listo.elementos) construir3D(); }
  function cancelar(avisar = true) {
    if (!calculando) return;
    turnoCalc++;
    calculando = null;
    motor?.cancelar();
    botones(false);
    if (avisar) estado('Cálculo cancelado.');
  }
  $(elPanel, '[data-s="form"]').addEventListener('submit', (e) => { e.preventDefault(); calcular(); });
  $(elPanel, '[data-s="cancelar"]').addEventListener('click', () => { cancelar(true); $(elPanel, '[data-s="calcular"]').focus({ preventScroll: true }); });

  // ================================================================ tema (8.3: la leyenda se recolorea con onTheme)
  const sinTema = onTheme((t) => { est3d?.tema(t); if (pisoEq !== '') ponerEquipos(); st.invalidate(); });

  // ================================================================ entrar y salir (6.8 y 8.6)
  let dentro = false;
  const poner = (cont, el) => { cont.replaceChildren(el); cont.hidden = false; };
  const sacar = (cont) => { cont.replaceChildren(); cont.hidden = true; };
  // la persona giró o acercó la cámara (OrbitControls avisa «start» solo con el puntero o la rueda, no con frameBox)
  let camaraTocada = false;
  const alTocarCamara = () => { if (dentro) camaraTocada = true; };
  st.controls.addEventListener('start', alTocarCamara);
  function encuadrar() {
    if (!est3d || !dentro) return;
    // en el recuadro angosto del teléfono la torre llena más el ancho (la barra de tiempo y la leyenda van encima y abajo)
    const angosto = (st.el?.clientWidth || 800) < 560;
    st.frameBox(est3d.caja(2), new THREE.Vector3(-0.75, 0.5, 0.62), { margin: angosto ? 0.95 : 0.8, duration: 1.2, ty: angosto ? 0.42 : 0.35 });
  }
  return {
    entrar() {
      if (dentro) return;
      dentro = true;
      camaraTocada = false;
      ctx.exterior.ocultar(true);
      poner(panel, elPanel); poner(hud, elHud); poner(cajaG, elG); poner(ficha, elFicha);
      if (est3d) { st.scene.add(est3d.grupo); rotulos.forEach((o) => { o.visible = !!R; }); tamPrev = ''; }
      if (!elFicha.childNodes.length) fichaElemento();
      // un resultado que terminó mientras la persona estaba en otro modo: las series del elemento se piden ahora
      if (R && elegido && seriesPendientes) elegir(elegido);
      st.invalidate(true);
      if (est3d) encuadrar();
      if (!R && !calculando) {
        // la primera vez se corre el escenario por defecto (nido_2015) para que la vista nunca esté vacía (8.6)
        if (primero) { primero = false; primeraVezSinAuto = true; }
        const p = calcular().then((r) => { primeraVezSinAuto = false; return r; });
        // al terminar se encuadra la torre, salvo que la persona ya haya girado o acercado la cámara mientras calculaba
        p.then(() => { if (!camaraTocada) encuadrar(); });
        // mientras el motor se prepara, la cámara encuadra la torre en cuanto exista el modelo
        (async () => { try { await obtenerMotor(); if (!estructura) estructura = await leerJSON(URL_ESTRUCTURA); if (dentro && !est3d && listo) { construir3D(); if (!camaraTocada) encuadrar(); } } catch { /* el estado lo dice el cálculo */ } })();
      }
    },
    salir({ porUsuario = false } = {}) {
      if (!dentro) return;
      dentro = false;
      reproducir(false);
      // Con el trabajador, un cálculo en curso sigue fuera del hilo principal: al volver se ve su resultado (o su avance)
      // y las series de los elementos siguen disponibles. Con el respaldo en el hilo principal (o si el motor todavía no
      // está), se detiene para no quitarle tiempo al modo nuevo, y el estado lo dice (sin barra de avance congelada)
      if (calculando && !(motor && motor.tipo !== 'hilo_principal')) {
        cancelar(false);
        estado(R ? 'El cálculo se detuvo al salir del simulador; se muestra el resultado anterior.' : 'El cálculo se detuvo al salir del simulador. Pulsa «Calcular» para hacerlo.');
      }
      if (est3d) st.scene.remove(est3d.grupo);
      rotulos.forEach((o) => { o.visible = false; o.element.style.display = 'none'; });
      sacar(panel); sacar(hud); sacar(cajaG); sacar(ficha);
      ctx.exterior.ocultar(false);
      st.invalidate(true);
      if (porUsuario) ctx.alSalir?.();
    },
    alReanudar() { tamPrev = ''; st.invalidate(); },
    alDetener() { reproducir(false); },
    // ganchos de QA (8.7)
    calcular: (p) => calcular(p),
    ultimo: () => resumen,
    motor: () => (motor ? (motor.tipo === 'simulado' ? 'trabajador' : motor.tipo) : null),
    cubiertaDibujada(i) { if (!R || !est3d) return null; irAPaso(i); return est3d.posicionCubierta(paso); },
    dispose() {
      this.salir({ porUsuario: false });
      const k = st.frameFns.indexOf(enCuadro); if (k >= 0) st.frameFns.splice(k, 1);
      lienzo.removeEventListener('pointerdown', alBajar); lienzo.removeEventListener('pointerup', alSubir);
      st.controls.removeEventListener('start', alTocarCamara);
      sinTema();
      Object.keys(grafs).forEach(cerrarGraf);
      quitarRotulos();
      est3d?.dispose(); est3d = null;
      motor?.cerrar(); motor = null; motorP = null;
    },
  };
}
