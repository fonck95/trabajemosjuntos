// Controles en primera persona del recorrido de la torre (equipo C; especificación de integración, 6.4).
// Teclado (un solo oyente keydown/keyup en window, con ev.code para que sirva con cualquier distribución), ratón (arrastrar
// para mirar; Pointer Lock opcional con el botón «Mirar con el ratón» o con doble clic, solo en escritorio y si el navegador
// lo permite), toque (arrastre para mirar y joystick virtual que avanza y gira, con botones de saltar, subir y bajar) y
// selección por clic corto. Espacio salta (y sube en el modo espectador, donde Shift baja, como en Minecraft).
// No mueve la cámara: entrega intenciones (avanzar, paso lateral, girar, mirar, subir o bajar, saltar) que el recorrido
// aplica en su cuadro.

const EDITABLE = new Set(['INPUT', 'TEXTAREA', 'SELECT']);
const MOVER = { KeyW: ['adelante', 1], ArrowUp: ['adelante', 1], KeyS: ['adelante', -1], ArrowDown: ['adelante', -1], KeyA: ['lado', -1], KeyD: ['lado', 1], ArrowLeft: ['giro', 1], ArrowRight: ['giro', -1] };
const ACCION = { KeyR: 'subir', PageUp: 'subir', KeyF: 'bajar', PageDown: 'bajar', KeyM: 'mapa', KeyI: 'panel', KeyV: 'espectador', KeyP: 'pantalla', Escape: 'esc' };
// con el foco en un control, Espacio y Enter son del control (activar un botón), no del caminante
const CONTROL = new Set(['BUTTON', 'A', 'SUMMARY', 'DETAILS']);
// teclas que solo actúan con el foco dentro del recuadro (6.4)
const SOLO_RECUADRO = new Set(['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'PageUp', 'PageDown']);
const SENS_RATON = 0.0042, SENS_TOQUE = 0.0065, SENS_BLOQUEO = 0.0024, RADIO_JOY = 42;

// op: { stage (elemento .stage), activo() → boolean, alSeleccionar({ clientX, clientY, centro }), alAccion(nombre),
//       contenedorJoystick (elemento del HUD donde va el joystick) }
export function crearControles({ stage, activo, alSeleccionar, alAccion, contenedorJoystick }) {
  const teclas = new Map();          // code → [eje, signo]
  let rapido = false, espacio = false, salto = false;
  const tactil = { arriba: false, abajo: false };
  const mirada = { yaw: 0, pitch: 0 };
  const joy = { x: 0, y: 0, id: null };
  let arrastre = null;               // { id, x, y, t, movido }
  const fino = matchMedia('(pointer: fine)'), grueso = matchMedia('(pointer: coarse)');
  const editable = (el) => !!el && (EDITABLE.has(el.tagName) || el.isContentEditable);
  const dentroRecuadro = () => stage.contains(document.activeElement);

  // ---- teclado
  function abajo(ev) {
    if (!activo() || ev.altKey || ev.ctrlKey || ev.metaKey || editable(ev.target)) return;
    if (SOLO_RECUADRO.has(ev.code) && !dentroRecuadro()) return;
    if (ev.code === 'Tab' && document.activeElement === stage && !ev.shiftKey) { if (alAccion('tab') !== false) ev.preventDefault(); return; }
    if (ev.code === 'ShiftLeft' || ev.code === 'ShiftRight') { rapido = true; return; }
    if (ev.code === 'Space') {
      if (CONTROL.has(ev.target?.tagName) || ev.target?.getAttribute?.('role') === 'button') return;
      ev.preventDefault();
      if (!ev.repeat) salto = true;
      espacio = true;
      return;
    }
    const m = MOVER[ev.code];
    if (m) { teclas.set(ev.code, m); ev.preventDefault(); return; }
    const a = ACCION[ev.code];
    if (a) {
      // Esc lo atiende siempre el recorrido (soltar el puntero o salir); los demás, sin repetición
      if (ev.repeat && a !== 'esc') { ev.preventDefault(); return; }
      if (alAccion(a) !== false) ev.preventDefault();
    }
  }
  function arriba(ev) {
    if (ev.code === 'ShiftLeft' || ev.code === 'ShiftRight') rapido = false;
    if (ev.code === 'Space') espacio = false;
    teclas.delete(ev.code);
  }
  const vaciar = () => { teclas.clear(); rapido = espacio = salto = false; tactil.arriba = tactil.abajo = false; joy.x = joy.y = 0; arrastre = null; };
  const alVisibilidad = () => { if (document.hidden) vaciar(); };

  // ---- ratón y toque sobre el lienzo
  const esLienzo = (t) => t && t.tagName === 'CANVAS';
  const tomado = () => document.pointerLockElement === stage;
  function pAbajo(ev) {
    if (!activo() || !esLienzo(ev.target)) return;
    if (ev.pointerType === 'mouse' && ev.button !== 0) return;
    // sin capturar el puntero en el recuadro: OrbitControls ya lo captura en el lienzo y necesita recibir su pointerup
    arrastre = { id: ev.pointerId, x: ev.clientX, y: ev.clientY, t: performance.now(), movido: 0, tipo: ev.pointerType };
  }
  function pMover(ev) {
    if (!activo()) return;
    if (tomado()) { mirada.yaw -= (ev.movementX || 0) * SENS_BLOQUEO; mirada.pitch -= (ev.movementY || 0) * SENS_BLOQUEO; return; }
    if (!arrastre || ev.pointerId !== arrastre.id) return;
    const dx = ev.clientX - arrastre.x, dy = ev.clientY - arrastre.y, k = arrastre.tipo === 'touch' ? SENS_TOQUE : SENS_RATON;
    arrastre.movido += Math.abs(dx) + Math.abs(dy);
    arrastre.x = ev.clientX; arrastre.y = ev.clientY;
    mirada.yaw -= dx * k; mirada.pitch -= dy * k;
  }
  function pArriba(ev) {
    if (tomado() && ev.button === 0 && activo() && esLienzo(ev.target)) { alSeleccionar({ clientX: ev.clientX, clientY: ev.clientY, centro: true }); return; }
    if (!arrastre || ev.pointerId !== arrastre.id) return;
    const a = arrastre;
    arrastre = null;
    // un clic selecciona solo si el puntero se movió menos de 5 px y duró menos de 300 ms (terminar un arrastre no)
    if (activo() && a.movido < 5 && performance.now() - a.t < 300) alSeleccionar({ clientX: ev.clientX, clientY: ev.clientY, centro: false });
  }
  const pCancelar = (ev) => { if (arrastre && ev.pointerId === arrastre.id) arrastre = null; };
  function dobleClic(ev) { if (activo() && esLienzo(ev.target) && fino.matches) tomarPuntero(); }
  const alBloqueo = () => { vaciar(); alAccion('puntero', tomado()); };

  // ---- Pointer Lock (puede estar bloqueado en un iframe o un Artifact: entonces sigue el arrastre); silencioso: sin aviso
  // si el navegador no lo da (al entrar en pantalla completa se intenta sin que la persona lo pida)
  function tomarPuntero({ silencioso = false } = {}) {
    if (!fino.matches || !stage.requestPointerLock || tomado()) return tomado();
    const fallo = () => { if (!silencioso) alAccion('puntero_bloqueado'); };
    try {
      const r = stage.requestPointerLock();
      if (r && typeof r.catch === 'function') r.catch(fallo);
      return true;
    } catch { fallo(); return false; }
  }
  const soltarPuntero = () => { if (tomado()) document.exitPointerLock?.(); };

  // ---- joystick táctil (6.4: abajo a la izquierda, 110 px; avanza y gira)
  const joyEl = document.createElement('div');
  joyEl.className = 'reco-joy';
  joyEl.setAttribute('aria-hidden', 'true');
  joyEl.innerHTML = '<span class="reco-joy-pomo"></span>';
  contenedorJoystick?.append(joyEl);
  const pomo = joyEl.firstElementChild;
  const ponerPomo = () => { pomo.style.transform = `translate(${joy.x * RADIO_JOY}px, ${-joy.y * RADIO_JOY}px)`; };
  function joyAbajo(ev) { joy.id = ev.pointerId; try { joyEl.setPointerCapture(ev.pointerId); } catch { /* */ } joyMover(ev); ev.preventDefault(); }
  function joyMover(ev) {
    if (joy.id !== ev.pointerId) return;
    const r = joyEl.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    let x = (ev.clientX - cx) / RADIO_JOY, y = -(ev.clientY - cy) / RADIO_JOY;
    const l = Math.hypot(x, y);
    if (l > 1) { x /= l; y /= l; }
    joy.x = Math.abs(x) < 0.12 ? 0 : x; joy.y = Math.abs(y) < 0.12 ? 0 : y;
    ponerPomo();
  }
  function joyArriba(ev) { if (joy.id !== ev.pointerId) return; joy.id = null; joy.x = joy.y = 0; ponerPomo(); }
  joyEl.addEventListener('pointerdown', joyAbajo);
  joyEl.addEventListener('pointermove', joyMover);
  joyEl.addEventListener('pointerup', joyArriba);
  joyEl.addEventListener('pointercancel', joyArriba);

  // ---- botones táctiles, a la derecha: pantalla completa y modo espectador (en pantallas angostas, donde la barra no
  // tiene lugar para ellos), saltar (en el espectador, subir) y bajar (solo en el espectador)
  const botones = document.createElement('div');
  botones.className = 'reco-saltos';
  botones.innerHTML = `<button type="button" class="reco-b-fs" aria-label="Pantalla completa" aria-pressed="false">⛶</button>
    <button type="button" class="reco-b-esp" aria-label="Modo espectador" aria-pressed="false">Vuelo</button>
    <button type="button" class="reco-b-sube" aria-label="Saltar">⤒</button><button type="button" class="reco-b-baja" aria-label="Bajar" hidden>⤓</button>`;
  contenedorJoystick?.append(botones);
  const bSube = botones.querySelector('.reco-b-sube'), bBaja = botones.querySelector('.reco-b-baja');
  const bFs = botones.querySelector('.reco-b-fs'), bEsp = botones.querySelector('.reco-b-esp');
  bFs.addEventListener('click', () => alAccion('pantalla'));
  bEsp.addEventListener('click', () => alAccion('espectador'));
  const tocar = (b, clave) => {
    const fin = (ev) => { tactil[clave] = false; try { b.releasePointerCapture(ev.pointerId); } catch { /* */ } };
    b.addEventListener('pointerdown', (ev) => { tactil[clave] = true; if (clave === 'arriba') salto = true; try { b.setPointerCapture(ev.pointerId); } catch { /* */ } ev.preventDefault(); });
    b.addEventListener('pointerup', fin);
    b.addEventListener('pointercancel', fin);
    b.addEventListener('contextmenu', (ev) => ev.preventDefault());
  };
  tocar(bSube, 'arriba');
  tocar(bBaja, 'abajo');

  window.addEventListener('keydown', abajo);
  window.addEventListener('keyup', arriba);
  window.addEventListener('blur', vaciar);
  document.addEventListener('visibilitychange', alVisibilidad);
  document.addEventListener('pointerlockchange', alBloqueo);
  stage.addEventListener('pointerdown', pAbajo);
  window.addEventListener('pointermove', pMover);
  window.addEventListener('pointerup', pArriba);
  window.addEventListener('pointercancel', pCancelar);
  stage.addEventListener('dblclick', dobleClic);

  return {
    // intención de este cuadro: ejes en [-1, 1], rapidez, Espacio (o el botón de subir) mantenido, Shift o el botón de bajar
    // mantenido, si se pidió un salto y la mirada acumulada (el salto y la mirada se consumen)
    leer() {
      let adelante = 0, lado = 0, giro = 0;
      for (const [eje, s] of teclas.values()) { if (eje === 'adelante') adelante += s; else if (eje === 'lado') lado += s; else giro += s; }
      adelante = Math.max(-1, Math.min(1, adelante + joy.y));
      giro = Math.max(-1, Math.min(1, giro - joy.x));
      const out = { adelante, lado: Math.max(-1, Math.min(1, lado)), giro, rapido, arriba: espacio || tactil.arriba, abajo: rapido || tactil.abajo, salto,
        dyaw: mirada.yaw, dpitch: mirada.pitch };
      mirada.yaw = 0; mirada.pitch = 0; salto = false;
      return out;
    },
    ocupado: () => teclas.size > 0 || espacio || tactil.arriba || tactil.abajo || joy.x !== 0 || joy.y !== 0 || mirada.yaw !== 0 || mirada.pitch !== 0,
    vaciar,
    tomarPuntero,
    soltarPuntero,
    tomado,
    tactil: () => grueso.matches,
    puedeBloquear: () => fino.matches && !!stage.requestPointerLock,
    mostrarJoystick(on) { joyEl.hidden = botones.hidden = !on; if (!on) { joy.x = joy.y = 0; joy.id = null; tactil.arriba = tactil.abajo = false; ponerPomo(); } },
    // en el espectador, el botón de saltar sube y aparece el de bajar
    modoEspectador(on) { bBaja.hidden = !on; bSube.setAttribute('aria-label', on ? 'Subir' : 'Saltar'); if (!on) tactil.abajo = false; },
    // estado de los botones de pantalla completa y espectador de la columna táctil
    marcar({ espectador, pantalla } = {}) {
      if (espectador != null) bEsp.setAttribute('aria-pressed', String(!!espectador));
      if (pantalla != null) bFs.setAttribute('aria-pressed', String(!!pantalla));
    },
    dispose() {
      soltarPuntero();
      window.removeEventListener('keydown', abajo);
      window.removeEventListener('keyup', arriba);
      window.removeEventListener('blur', vaciar);
      document.removeEventListener('visibilitychange', alVisibilidad);
      document.removeEventListener('pointerlockchange', alBloqueo);
      stage.removeEventListener('pointerdown', pAbajo);
      window.removeEventListener('pointermove', pMover);
      window.removeEventListener('pointerup', pArriba);
      window.removeEventListener('pointercancel', pCancelar);
      stage.removeEventListener('dblclick', dobleClic);
      joyEl.remove();
      botones.remove();
    },
  };
}
