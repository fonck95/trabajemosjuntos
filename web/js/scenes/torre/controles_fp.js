// Controles en primera persona del recorrido de la torre (equipo C; especificación de integración, 6.4).
// Teclado (un solo oyente keydown/keyup en window, con ev.code para que sirva con cualquier distribución), ratón (arrastrar
// para mirar; Pointer Lock opcional con el botón «Mirar con el ratón» o con doble clic, solo en escritorio y si el navegador
// lo permite), toque (arrastre para mirar y joystick virtual que avanza y gira) y selección por clic corto.
// No mueve la cámara: entrega intenciones (avanzar, paso lateral, girar, mirar) que el recorrido aplica en su cuadro.

const EDITABLE = new Set(['INPUT', 'TEXTAREA', 'SELECT']);
const MOVER = { KeyW: ['adelante', 1], ArrowUp: ['adelante', 1], KeyS: ['adelante', -1], ArrowDown: ['adelante', -1], KeyA: ['lado', -1], KeyD: ['lado', 1], ArrowLeft: ['giro', 1], ArrowRight: ['giro', -1] };
const ACCION = { KeyR: 'subir', PageUp: 'subir', KeyF: 'bajar', PageDown: 'bajar', KeyM: 'mapa', KeyI: 'panel', Escape: 'esc' };
// teclas que solo actúan con el foco dentro del recuadro (6.4)
const SOLO_RECUADRO = new Set(['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'PageUp', 'PageDown']);
const SENS_RATON = 0.0042, SENS_TOQUE = 0.0065, SENS_BLOQUEO = 0.0024, RADIO_JOY = 42;

// op: { stage (elemento .stage), activo() → boolean, alSeleccionar({ clientX, clientY, centro }), alAccion(nombre),
//       contenedorJoystick (elemento del HUD donde va el joystick) }
export function crearControles({ stage, activo, alSeleccionar, alAccion, contenedorJoystick }) {
  const teclas = new Map();          // code → [eje, signo]
  let rapido = false;
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
    teclas.delete(ev.code);
  }
  const vaciar = () => { teclas.clear(); rapido = false; joy.x = joy.y = 0; arrastre = null; };
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

  // ---- Pointer Lock (puede estar bloqueado en un iframe o un Artifact: entonces sigue el arrastre)
  function tomarPuntero() {
    if (!fino.matches || !stage.requestPointerLock) return false;
    try {
      const r = stage.requestPointerLock();
      if (r && typeof r.catch === 'function') r.catch(() => alAccion('puntero_bloqueado'));
      return true;
    } catch { alAccion('puntero_bloqueado'); return false; }
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
    // intención de este cuadro: ejes en [-1, 1], rapidez y la mirada acumulada (se consume)
    leer() {
      let adelante = 0, lado = 0, giro = 0;
      for (const [eje, s] of teclas.values()) { if (eje === 'adelante') adelante += s; else if (eje === 'lado') lado += s; else giro += s; }
      adelante = Math.max(-1, Math.min(1, adelante + joy.y));
      giro = Math.max(-1, Math.min(1, giro - joy.x));
      const out = { adelante, lado: Math.max(-1, Math.min(1, lado)), giro, rapido, dyaw: mirada.yaw, dpitch: mirada.pitch };
      mirada.yaw = 0; mirada.pitch = 0;
      return out;
    },
    ocupado: () => teclas.size > 0 || joy.x !== 0 || joy.y !== 0 || mirada.yaw !== 0 || mirada.pitch !== 0,
    vaciar,
    tomarPuntero,
    soltarPuntero,
    tomado,
    tactil: () => grueso.matches,
    puedeBloquear: () => fino.matches && !!stage.requestPointerLock,
    mostrarJoystick(on) { joyEl.hidden = !on; if (!on) { joy.x = joy.y = 0; joy.id = null; ponerPomo(); } },
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
    },
  };
}
