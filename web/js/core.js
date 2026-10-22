// Motor 3D del atlas. Un solo WebGLRenderer compartido entre todas las vistas: el lienzo se
// mueve a la vista activa, así no se multiplican contextos WebGL ni memoria de GPU.
// Optimizaciones: renderizado bajo demanda, pausa fuera de pantalla o con la pestaña oculta,
// resolución adaptativa según el tiempo de cuadro, sombras que se recalculan solo cuando algo
// cambia, geometrías compartidas e iluminación por entorno (PMREM) para modelos PBR.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

export { THREE, CSS2DObject };

export const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
export const gsap = window.gsap && !reducedMotion ? window.gsap : null;
// las animaciones siguen el reloj real: con el suavizado de GSAP, en equipos lentos (cuadros de 0,3–0,5 s) un vuelo
// de cámara de 1,5 s tardaba más de 20 s y la vista quedaba a medio camino
gsap?.ticker.lagSmoothing(0);

// Lee los tokens de color de la página para que el 3D siga el tema claro/oscuro.
export function tokens() {
  const cs = getComputedStyle(document.documentElement);
  const g = (n) => new THREE.Color(cs.getPropertyValue(n).trim() || '#888');
  return {
    bg: g('--bg'), surface: g('--surface'), ink: g('--ink'), muted: g('--muted'), line: g('--line'),
    ground: g('--ground'), water: g('--water'), wall: g('--wall'), roof: g('--roof'), accent: g('--accent'), sun: g('--sun'),
    s: [1, 2, 3, 4, 5, 6, 7, 8].map((i) => g(`--s${i}`)),
    good: g('--good'), warn: g('--warn'), bad: g('--bad'), data: g('--data'), power: g('--power'),
  };
}

const themeListeners = new Set();
export function onTheme(fn) { themeListeners.add(fn); return () => themeListeners.delete(fn); }
function fireTheme() { const t = tokens(); themeListeners.forEach((fn) => fn(t)); engine.active?.invalidate(true); }
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', fireTheme);
new MutationObserver(fireTheme).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

// ---------------------------------------------------------------- motor compartido
class Engine {
  constructor() { this.renderer = null; this.active = null; this.clock = new THREE.Clock(); }
  ensure() {
    if (this.renderer) return this.renderer;
    const r = new THREE.WebGLRenderer({ antialias: devicePixelRatio < 1.5, alpha: true, powerPreference: 'high-performance', stencil: false });
    r.outputColorSpace = THREE.SRGBColorSpace;
    r.shadowMap.enabled = true;
    r.shadowMap.type = THREE.PCFSoftShadowMap;
    r.shadowMap.autoUpdate = false; // se recalculan solo cuando algo cambia
    r.domElement.className = 'gl';
    this.maxDpr = Math.min(devicePixelRatio || 1, 2);
    this.minDpr = Math.min(1, this.maxDpr);
    this.dpr = this.maxDpr;
    r.setPixelRatio(this.dpr);
    const pmrem = new THREE.PMREMGenerator(r);
    this.env = pmrem.fromScene(new RoomEnvironment(r), 0.04).texture;
    pmrem.dispose();
    this.renderer = r;
    this.perf = { ema: 1 / 60, frames: 0, fps: 0, lastFpsT: performance.now(), lastChange: 0 };
    const loop = () => { this.frame(); this.raf = requestAnimationFrame(loop); };
    loop();
    return r;
  }
  attach(stage) {
    this.ensure();
    if (this.active && this.active !== stage) { this.active.controls.enabled = false; this.active.running = false; }
    stage.el.prepend(this.renderer.domElement);
    this.active = stage;
    stage.controls.enabled = true;
    this.renderer.toneMapping = stage.tone;
    this.renderer.toneMappingExposure = stage.exposure;
    stage.resize();
    stage.invalidate(true);
  }
  frame() {
    const s = this.active;
    const dt = Math.min(this.clock.getDelta(), 0.05);
    if (!s || !s.running || document.hidden || !s.inView) return;
    const t = this.clock.elapsedTime;
    let need = s.dirty;
    for (const fn of s.frameFns) if (fn(dt, t) !== false) need = true;
    if (s.controls.update()) need = true;
    if (!need) { this.perf.continuous = false; return; }
    if (s.dynamicShadows || s.shadowDirty) { this.renderer.shadowMap.needsUpdate = true; s.shadowDirty = false; }
    s.adaptDepth();
    this.renderer.render(s.scene, s.camera);
    s.labels.render(s.scene, s.camera);
    if (s.declutter) s.declutterLabels();
    s.dirty = false;
    this.measure(dt, s);
  }
  // Resolución adaptativa: baja el pixel ratio si los cuadros pasan de ~22 ms y lo recupera con holgura
  measure(dt, s) {
    const p = this.perf, now = performance.now();
    if (p.continuous) p.ema = p.ema * 0.92 + dt * 0.08;
    p.continuous = true;
    p.frames++;
    if (now - p.lastFpsT > 500) {
      p.fps = (p.frames * 1000) / (now - p.lastFpsT); p.frames = 0; p.lastFpsT = now;
      if (now - p.lastChange > 1500) {
        // tras dos bajadas deja de subir: alternar resoluciones se ve como un parpadeo
        if (p.ema > 1 / 45 && this.dpr > this.minDpr) { this.dpr = Math.max(this.minDpr, this.dpr - 0.25); this.applyDpr(s); p.lastChange = now; p.drops = (p.drops || 0) + 1; }
        else if (p.ema < 1 / 58 && this.dpr < this.maxDpr && (p.drops || 0) < 2 && now - p.lastChange > 10000) { this.dpr = Math.min(this.maxDpr, this.dpr + 0.25); this.applyDpr(s); p.lastChange = now; }
      }
      s.hud?.update(this);
    }
  }
  applyDpr(s) { this.renderer.setPixelRatio(this.dpr); s.resize(); }
  // Al cambiar el tamaño del lienzo el navegador lo borra: se vuelve a dibujar en el mismo cuadro para que no parpadee
  redraw(s) { if (this.active !== s || !s.running) return; s.adaptDepth(); this.renderer.render(s.scene, s.camera); s.labels.render(s.scene, s.camera); s.dirty = false; }
}
export const engine = new Engine();

const sharedBox = new THREE.BoxGeometry(1, 1, 1);

// ---------------------------------------------------------------- escena de cada vista
export class Stage {
  constructor(el, { cam = [30, 26, 34], target = [0, 0, 0], fov = 40, minDist = 8, maxDist = 140, env = true, tone = 'none', exposure = 1, dynamicShadows = false, fit = 0.75, declutter = false } = {}) {
    // declutter: true (etiquetas .lbl-node) o la lista de clases que se pueden mover
    this.declutter = declutter === true ? ['lbl-node'] : declutter || null; this._labels = [];
    // fit: cuánto se aleja la cámara en pantallas angostas (1 = la escena conserva su ancho; 0,75 = término medio)
    this.fitExp = fit;
    this.nearMin = Math.min(0.05, minDist * 0.01);
    const r = engine.ensure();
    this.el = el;
    this.scene = new THREE.Scene();
    if (env) this.scene.environment = engine.env;
    this.tone = tone === 'aces' ? THREE.ACESFilmicToneMapping : THREE.NoToneMapping;
    this.exposure = exposure;
    this.dynamicShadows = dynamicShadows;
    this.camera = new THREE.PerspectiveCamera(fov, 1, 0.1, 1200);
    this.camera.position.set(...cam);
    this.labels = new CSS2DRenderer();
    this.labels.domElement.className = 'label-layer';
    el.appendChild(this.labels.domElement);
    this.controls = new OrbitControls(this.camera, r.domElement);
    this.controls.enabled = false;
    this.controls.target.set(...target);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.minDistance = minDist;
    this.controls.maxDistance = maxDist;
    this.controls.maxPolarAngle = Math.PI * 0.47;
    this.controls.addEventListener('change', () => this.invalidate());
    this.baseOffset = this.camera.position.clone().sub(this.controls.target);
    this.userMoved = false;
    // si la persona toma la cámara, los vuelos en curso se cancelan en vez de pelearle el control
    this.controls.addEventListener('start', () => { this.userMoved = true; this.stopFlight(); });
    this.frameFns = [];
    this.running = false;
    this.dirty = true;
    this.inView = true;
    this.hemi = new THREE.HemisphereLight(0xffffff, 0x445544, env ? 0.55 : 1.1);
    this.scene.add(this.hemi);
    this.sunLight = new THREE.DirectionalLight(0xffffff, env ? 1.35 : 1.6);
    this.sunLight.position.set(30, 50, 20);
    this.sunLight.castShadow = true;
    const ms = innerWidth < 720 ? 1024 : 2048;
    this.sunLight.shadow.mapSize.set(ms, ms);
    this.sunLight.shadow.bias = -0.0004;
    this.sunLight.shadow.normalBias = 0.02;
    const sc = this.sunLight.shadow.camera; sc.left = -50; sc.right = 50; sc.top = 50; sc.bottom = -50; sc.far = 180;
    this.scene.add(this.sunLight);
    this.ray = new THREE.Raycaster();
    this.pointer = new THREE.Vector2();
    this.pickables = [];
    this.hovered = null;
    new ResizeObserver(() => this.resize()).observe(el);
    new IntersectionObserver(([e]) => { this.inView = e.isIntersecting; if (this.inView) this.invalidate(); }).observe(el);
    r.domElement.addEventListener('pointermove', (e) => { if (this.isActive()) this._queueMove(e); });
    r.domElement.addEventListener('click', (e) => { if (this.isActive()) this._click(e); });
    this.hud = makeHud(el, this);
  }
  isActive() { return engine.active === this; }
  // Etiquetas sin encimarse: las fijas (.lbl-cx, .lbl-data, .lbl-alert) quedan donde están; las de nodo
  // (.lbl-node), de abajo hacia arriba en pantalla, suben lo justo para no chocar con las ya puestas.
  // Primero se leen todas las medidas y después se escribe: un solo cálculo de diseño por cuadro
  declutterLabels() {
    const W = this.el.clientWidth, H = this.el.clientHeight, v = new THREE.Vector3(), fixed = [], movers = [];
    for (const o of this._labels) {
      const e = o.element, c = e.classList;
      if (!e.isConnected || e.hidden || e.style.display === 'none') continue;
      // la etiqueta secundaria de una conexión (.lbl-cx.alt, el poste) sí se mueve para no tapar la del tablero
      const fijo = (c.contains('lbl-cx') && !c.contains('alt')) || c.contains('lbl-data') || c.contains('lbl-alert');
      if (!fijo && !c.contains('alt') && !this.declutter.some((k) => c.contains(k))) continue;
      o.getWorldPosition(v).project(this.camera);
      if (v.z > 1) continue;
      const r = { e, x: ((v.x + 1) / 2) * W, y: ((1 - v.y) / 2) * H, w: e.offsetWidth, h: e.offsetHeight };
      if (r.w) (fijo ? fixed : movers).push(r);
    }
    const placed = fixed;
    movers.sort((a, b) => b.y - a.y).forEach((r) => {
      let y = r.y;
      for (let k = 0; k < 12; k++) {
        const hit = placed.find((p) => Math.abs(p.x - r.x) < (p.w + r.w) / 2 + 4 && Math.abs(p.y - y) < (p.h + r.h) / 2 + 3);
        if (!hit) break;
        y = hit.y - (hit.h + r.h) / 2 - 3;
      }
      r.dy = y - r.y; placed.push({ ...r, y });
    });
    movers.forEach((r) => { r.e.style.marginTop = r.dy < -0.5 ? `${r.dy}px` : ''; });
  }
  // usa el tamaño real del contenedor: al montar la escena la cámara todavía no tiene su proporción final
  fitFactor() { const w = this.el.clientWidth, h = this.el.clientHeight, a = w && h ? w / h : this.camera.aspect || 1.5; return Math.max(1, Math.pow(1.5 / a, this.fitExp)); }
  // posición de cámara pensada para escritorio, alejada según el ancho del contenedor (para vuelos a vistas fijas)
  fitPos(pos, target) { const k = this.fitFactor(); return pos.map((v, i) => target[i] + (v - target[i]) * k); }
  // Plano cercano proporcional a la distancia: con near fijo de 0,1 m y la cámara a 1 km, la precisión de
  // profundidad cae a ~0,6 m y techos, paneles, ventanas y pisos titilan (z-fighting)
  adaptDepth() {
    const n = THREE.MathUtils.clamp(this.camera.position.distanceTo(this.controls.target) * 0.012, this.nearMin, 40);
    if (Math.abs(n - this.camera.near) > n * 0.08) { this.camera.near = n; this.camera.updateProjectionMatrix(); }
  }
  invalidate(shadows = false) { this.dirty = true; if (shadows) this.shadowDirty = true; }
  updateShadows() { this.shadowDirty = true; this.dirty = true; }
  resize() {
    const w = this.el.clientWidth, h = this.el.clientHeight;
    if (!w || !h) return;
    this.labels.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    // en pantallas angostas la cámara se aleja para que la escena quepa
    if (!this.userMoved && !this.flying) {
      const off = this.baseOffset.clone().multiplyScalar(this.fitFactor());
      this.controls.maxDistance = Math.max(this.controls.maxDistance, off.length() * 1.25);
      this.camera.position.copy(this.controls.target).add(off);
    }
    if (this.isActive()) { engine.renderer.setSize(w, h); engine.redraw(this); }
    this.invalidate();
  }
  label(html, cls = '', pos = [0, 0, 0], parent = this.scene) {
    const div = document.createElement('div');
    div.className = `lbl ${cls}`;
    div.innerHTML = html;
    const o = new CSS2DObject(div);
    o.position.set(...pos);
    parent.add(o);
    this._labels.push(o);
    return o;
  }
  // fn(dt, t) devuelve false cuando no necesita redibujar en ese cuadro
  onFrame(fn) { this.frameFns.push(fn); }
  start() { engine.attach(this); this.running = true; this.invalidate(true); }
  stop() { this.running = false; }
  // Vuelo de cámara con GSAP; sin GSAP (o con movimiento reducido) salta directo
  stopFlight() { if (!gsap) return; gsap.killTweensOf(this.camera.position); gsap.killTweensOf(this.controls.target); this._intro?.kill(); this.flying = false; }
  flyTo(pos, target = this.controls.target.toArray(), duration = 1.4) {
    const c = this.camera.position, tg = this.controls.target;
    if (!gsap) { c.set(...pos); tg.set(...target); this.baseOffset.copy(c).sub(tg).divideScalar(this.fitFactor()); this.invalidate(); return; }
    this.stopFlight();
    this.flying = true;
    gsap.to(c, { x: pos[0], y: pos[1], z: pos[2], duration, ease: 'power3.inOut', onUpdate: () => this.invalidate() });
    gsap.to(tg, { x: target[0], y: target[1], z: target[2], duration, ease: 'power3.inOut', onUpdate: () => this.invalidate(), onComplete: () => { this.flying = false; this.baseOffset.copy(c).sub(tg).divideScalar(this.fitFactor()); } });
  }
  // Vuela a encuadrar una caja: busca la distancia a la que sus 8 esquinas caben en pantalla con margen (sirve
  // igual para edificios alargados que para compactos, en pantallas anchas o angostas)
  frameBox(box, dir, { margin = 0.8, duration = 1.4, ty = 0.35 } = {}) {
    const size = box.getSize(new THREE.Vector3()), c = box.getCenter(new THREE.Vector3());
    const tgt = new THREE.Vector3(c.x, box.min.y + size.y * ty, c.z), d = dir.clone().normalize(), v = new THREE.Vector3();
    const cam = this.camera.clone(), pts = [];
    for (let i = 0; i < 8; i++) pts.push(new THREE.Vector3(i & 1 ? box.max.x : box.min.x, i & 2 ? box.max.y : box.min.y, i & 4 ? box.max.z : box.min.z));
    let D = Math.max(size.length() * 0.25, this.controls.minDistance);
    for (let k = 0; k < 90; k++, D *= 1.05) {
      cam.position.copy(tgt).addScaledVector(d, D); cam.lookAt(tgt); cam.updateMatrixWorld();
      if (pts.every((p) => { v.copy(p).project(cam); return v.z < 1 && Math.abs(v.x) < margin && Math.abs(v.y) < margin; })) break;
    }
    this.controls.maxDistance = Math.max(this.controls.maxDistance, D * 1.6);
    this.flyTo(cam.position.toArray(), tgt.toArray(), duration);
    return D;
  }
  // Primer plano de un punto con línea de vista libre: prueba rumbos alrededor del preferido (y dos elevaciones)
  // y descarta los que tapa algo visible de objs (muros, cubiertas, árboles); si todos están tapados, mira desde arriba
  closeUp(p, objs, pref, { dist = 12, elev = 28, duration = 1.3 } = {}) {
    const ray = new THREE.Raycaster(), base = Math.atan2(pref.z, pref.x), e0 = THREE.MathUtils.degToRad(elev), d = new THREE.Vector3();
    const shown = (o) => { for (; o; o = o.parent) if (!o.visible) return false; return true; };
    let best = null;
    busca: for (const el of [e0, e0 * 1.9]) for (const k of [0, 1, -1, 2, -2, 3, -3, 4]) {
      const a = base + (k * Math.PI) / 4;
      d.set(Math.cos(a) * Math.cos(el), Math.sin(el), Math.sin(a) * Math.cos(el));
      const cam = p.clone().addScaledVector(d, dist);
      ray.set(cam, d.clone().negate()); ray.far = dist - 1;
      if (!ray.intersectObjects(objs, true).some((h) => shown(h.object))) { best = cam; break busca; }
    }
    this.flyTo((best || p.clone().add(new THREE.Vector3(0.01, dist * 1.4, 0))).toArray(), p.toArray(), duration);
  }
  // Entrada de cámara: parte de más lejos y se acerca a la posición de reposo
  intro() {
    if (!gsap || this.introDone) return;
    this.introDone = true;
    if (this.flying) return; // la escena ya pidió su propio vuelo (por ejemplo, el visor al cargar un modelo)
    // la posición final se recalcula en cada cuadro con el encuadre vigente: si el contenedor cambia de tamaño
    // durante la entrada, la cámara termina igual donde debe
    const tg = this.controls.target, o = { u: 0 };
    this.flying = true;
    this._intro = gsap.to(o, { u: 1, duration: 1.6, ease: 'power3.inOut', onUpdate: () => {
      const k = 1 + 0.45 * (1 - o.u);
      this.camera.position.copy(tg).addScaledVector(this.baseOffset, this.fitFactor() * k); this.camera.position.y += 8 * (1 - o.u);
      this.invalidate();
    }, onComplete: () => { this.flying = false; }, onInterrupt: () => { this.flying = false; } });
  }
  // Congela matrices de objetos estáticos: three deja de recalcularlas en cada cuadro
  freeze(obj) { obj.traverse((o) => { o.updateMatrix(); o.matrixAutoUpdate = false; }); obj.updateMatrixWorld(true); }
  _queueMove(e) {
    this._lastMove = e;
    if (this._moveQueued) return;
    this._moveQueued = true;
    requestAnimationFrame(() => { this._moveQueued = false; this._move(this._lastMove); });
  }
  _hit(e) {
    const r = engine.renderer.domElement.getBoundingClientRect();
    this.pointer.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    this.ray.setFromCamera(this.pointer, this.camera);
    const hit = this.ray.intersectObjects(this.pickables, true)[0];
    if (!hit) return null;
    let o = hit.object;
    while (o && !o.userData.pick) o = o.parent;
    return o;
  }
  _move(e) {
    const o = this._hit(e);
    if (o !== this.hovered) {
      if (this.hovered?.userData.onLeave) this.hovered.userData.onLeave();
      this.hovered = o;
      if (o?.userData.onEnter) o.userData.onEnter();
      engine.renderer.domElement.style.cursor = o ? 'pointer' : '';
      this.invalidate();
    }
  }
  _click(e) { const o = this._hit(e); if (o?.userData.onPick) { o.userData.onPick(); this.invalidate(); } }
  pickable(obj, handlers) { obj.userData.pick = true; Object.assign(obj.userData, handlers); this.pickables.push(obj); }
}

// Panel de rendimiento (cuadros por segundo, llamadas de dibujo, triángulos, memoria de GPU)
function makeHud(el, stage) {
  const btn = document.createElement('button');
  btn.type = 'button'; btn.className = 'hud-btn'; btn.textContent = 'Rendimiento'; btn.setAttribute('aria-pressed', 'false');
  const box = document.createElement('div');
  box.className = 'hud'; box.hidden = true;
  el.append(btn, box);
  btn.addEventListener('click', () => { box.hidden = !box.hidden; btn.setAttribute('aria-pressed', String(!box.hidden)); stage.invalidate(); });
  return {
    update(eng) {
      if (box.hidden) return;
      const i = eng.renderer.info;
      box.innerHTML = `<b>${eng.perf.fps.toFixed(0)}</b> fps · ${(eng.perf.ema * 1000).toFixed(1)} ms<br>resolución ×${eng.dpr.toFixed(2)}<br>${i.render.calls} llamadas · ${i.render.triangles.toLocaleString('es-CO')} triángulos<br>${i.memory.geometries} geometrías · ${i.memory.textures} texturas`;
    },
  };
}

// Libera geometrías, materiales y texturas de un objeto (evita fugas al cambiar modelos)
export function disposeObject(obj) {
  obj.traverse((o) => {
    if (o.geometry && o.geometry !== sharedBox) o.geometry.dispose();
    const ms = Array.isArray(o.material) ? o.material : o.material ? [o.material] : [];
    ms.forEach((m) => { Object.values(m).forEach((v) => { if (v && v.isTexture) v.dispose(); }); m.dispose(); });
  });
}

// Material estándar mate; las escenas usan pocos materiales para que el tema se pueda reaplicar.
export function mat(color, opts = {}) {
  return new THREE.MeshStandardMaterial({ color, roughness: 0.82, metalness: 0.04, ...opts });
}

// Caja con geometría compartida: una sola geometría en GPU para todas las cajas de la escena
export function box(w, h, d, material, x = 0, y = 0, z = 0) {
  const m = new THREE.Mesh(sharedBox, material);
  m.scale.set(w, h, d);
  m.position.set(x, y + h / 2, z);
  m.castShadow = true; m.receiveShadow = true;
  return m;
}

// Arreglo solar con instancias GPU; proporción de módulo real (1,134 × 2,278 m) a escala 0,84.
// Inclinación de 10° (latitud de Yondó ~7° N) hacia el sur.
export const PANEL = { w: 0.95, l: 1.9, scale: 0.95 / 1.134 };
export function solarArray(cols, rows, material, frameMat, tilt = 0.17) {
  const g = new THREE.Group();
  const geo = new THREE.BoxGeometry(PANEL.w, 0.05, PANEL.l);
  const inst = new THREE.InstancedMesh(geo, material, cols * rows);
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion().setFromEuler(new THREE.Euler(tilt, 0, 0));
  const pitch = PANEL.l * Math.cos(tilt) + 0.12;
  let i = 0;
  for (let c = 0; c < cols; c++) for (let r = 0; r < rows; r++) {
    m4.compose(new THREE.Vector3(c * 1.02 - (cols - 1) * 0.51, 0.25, r * pitch - ((rows - 1) * pitch) / 2), q, new THREE.Vector3(1, 1, 1));
    inst.setMatrixAt(i++, m4);
  }
  inst.castShadow = true;
  inst.userData.solar = true;
  g.add(inst);
  if (frameMat) {
    const leg = new THREE.Mesh(new THREE.BoxGeometry(cols * 1.02, 0.2, 0.08), frameMat);
    leg.position.y = 0.1; g.add(leg);
  }
  return g;
}

// Partículas que viajan por una curva: la densidad y la velocidad codifican la potencia.
const flowGeo = new THREE.SphereGeometry(1, 10, 8);
export class Flow {
  constructor(scene, curve, color, { max = 26, size = 0.16, tube = 0.05 } = {}) {
    this.curve = curve;
    this.max = max;
    this.size = size;
    this.mesh = new THREE.InstancedMesh(flowGeo, new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.95 }), max);
    this.mesh.frustumCulled = false;
    scene.add(this.mesh);
    this.offsets = Array.from({ length: max }, (_, i) => i / max);
    this.power = 0; this.dir = 1; this.phase = 0;
    this.tube = new THREE.Mesh(new THREE.TubeGeometry(curve, 48, tube, 6, false), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.28 }));
    scene.add(this.tube);
    this._m = new THREE.Matrix4(); this._p = new THREE.Vector3(); this._zero = new THREE.Matrix4().makeScale(0, 0, 0);
    this._s = new THREE.Vector3(size, size, size); this._q = new THREE.Quaternion();
  }
  set(power, dir) { this.power = power; this.dir = dir; }
  setColor(c) { this.mesh.material.color.set(c); this.tube.material.color.set(c); }
  visible(v) { this.mesh.visible = v; this.tube.visible = v; }
  // devuelve false si no hay partículas activas (no hace falta redibujar por este flujo)
  update(dt) {
    const n = this.mesh.visible ? Math.round(Math.min(1, this.power) * this.max) : 0;
    if (n === 0 && this._lastN === 0) return false;
    this._lastN = n;
    this.phase = (this.phase + dt * (0.12 + 0.35 * Math.min(1, this.power)) * (reducedMotion ? 0.3 : 1)) % 1;
    for (let i = 0; i < this.max; i++) {
      if (i >= n) { this.mesh.setMatrixAt(i, this._zero); continue; }
      let t = (this.offsets[i] + this.phase) % 1;
      if (this.dir < 0) t = 1 - t;
      this.curve.getPointAt(t, this._p);
      this._m.compose(this._p, this._q, this._s);
      this.mesh.setMatrixAt(i, this._m);
    }
    this.mesh.instanceMatrix.needsUpdate = true;
    return true;
  }
}

// Etiquetas de la conexión de una sede. Tablero con medidor bidireccional, gateway IoT y acometida quedan en el
// mismo punto de la fachada (a 1–3 m): van en una sola etiqueta; el poste de la red, aparte cuando queda lejos.
// onClick recibe el punto (en el marco del modelo) para acercar la cámara.
export function conexionLabels(st, cn, parent, onClick) {
  if (!cn?.tablero) return [];
  const [tx, ty, tz] = cn.tablero, lejos = cn.red && Math.hypot(cn.red[0] - tx, cn.red[2] - tz) > 5;
  const make = (html, pos, cls = '') => {
    const l = st.label(html, `lbl-cx${cls}`, pos, parent);
    if (onClick) { Object.assign(l.element.style, { pointerEvents: 'auto', cursor: 'zoom-in' }); l.element.title = 'Acercar a la conexión'; l.element.addEventListener('click', () => onClick(pos)); }
    return l;
  };
  const out = [make(`<span class="pw">Tablero + medidor bidireccional</span><span class="dt">Gateway IoT → CCED</span>${cn.red && !lejos ? '<span class="pw">Acometida de la red (EPM)</span>' : ''}`, [tx, ty + 2.4, tz])];
  if (lejos) out.push(make('<span class="pw">Poste de la red (EPM)</span>', [cn.red[0], cn.red[1] + 1.5, cn.red[2]], ' alt'));
  return out;
}

// Caja de las mallas con volumen (más de minH de alto): deja por fuera pisos planos como parqueaderos y zonas verdes
export function solidBox(obj, minH = 0.6) {
  const box = new THREE.Box3(), bb = new THREE.Box3();
  obj.updateMatrixWorld(true);
  obj.traverse((o) => {
    if (!o.isMesh) return;
    if (o.isInstancedMesh) { o.computeBoundingBox(); bb.copy(o.boundingBox); } else { if (!o.geometry.boundingBox) o.geometry.computeBoundingBox(); bb.copy(o.geometry.boundingBox); }
    bb.applyMatrix4(o.matrixWorld);
    if (bb.max.y - bb.min.y > minH) box.union(bb);
  });
  return box.isEmpty() ? box.setFromObject(obj) : box;
}

export function arc(a, b, lift = 3) {
  const A = new THREE.Vector3(...a), B = new THREE.Vector3(...b);
  const M = A.clone().lerp(B, 0.5); M.y += lift;
  return new THREE.QuadraticBezierCurve3(A, M, B);
}

export const fmtCOP = (v) => {
  const a = Math.abs(v);
  if (a >= 1e12) return `$${(v / 1e12).toLocaleString('es-CO', { maximumFractionDigits: 2 })} billones`;
  if (a >= 1e9) return `$${(v / 1e9).toLocaleString('es-CO', { maximumFractionDigits: 1 })} mil M`;
  if (a >= 1e6) return `$${(v / 1e6).toLocaleString('es-CO', { maximumFractionDigits: 0 })} M`;
  return `$${Math.round(v).toLocaleString('es-CO')}`;
};
export const fmtN = (v, d = 0) => Number(v).toLocaleString('es-CO', { maximumFractionDigits: d, minimumFractionDigits: d });

// Anima la primera cifra de un texto (formato es-CO) de 0 a su valor
export function countUp(el, duration = 1.1) {
  if (!gsap || !el) return;
  const txt = el.textContent, m = txt.match(/\d[\d.]*(,\d+)?/);
  if (!m) return;
  const dec = m[1] ? m[1].length - 1 : 0;
  const target = parseFloat(m[0].replace(/\./g, '').replace(',', '.'));
  const o = { v: 0 };
  gsap.to(o, { v: target, duration, ease: 'power2.out', onUpdate: () => { el.textContent = txt.replace(m[0], o.v.toLocaleString('es-CO', { minimumFractionDigits: dec, maximumFractionDigits: dec })); } });
}
