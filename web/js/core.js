// Motor común de las escenas 3D: renderer, cámara, controles, etiquetas, tema y selección.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';

export { THREE, CSS2DObject };

export const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

// Lee los tokens de color de la página para que el 3D siga el tema claro/oscuro.
export function tokens() {
  const cs = getComputedStyle(document.documentElement);
  const g = (n) => new THREE.Color(cs.getPropertyValue(n).trim() || '#888');
  return {
    bg: g('--bg'), surface: g('--surface'), ink: g('--ink'), muted: g('--muted'), line: g('--line'),
    ground: g('--ground'), water: g('--water'), wall: g('--wall'), roof: g('--roof'), accent: g('--accent'), sun: g('--sun'),
    s: [1, 2, 3, 4, 5, 6, 7, 8].map((i) => g(`--s${i}`)),
    good: g('--good'), warn: g('--warn'), bad: g('--bad'), data: g('--data'),
  };
}

const themeListeners = new Set();
export function onTheme(fn) { themeListeners.add(fn); return () => themeListeners.delete(fn); }
function fireTheme() { const t = tokens(); themeListeners.forEach((fn) => fn(t)); }
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', fireTheme);
new MutationObserver(fireTheme).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

export class Stage {
  constructor(el, { cam = [30, 26, 34], target = [0, 0, 0], fov = 40, minDist = 8, maxDist = 140 } = {}) {
    this.el = el;
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(fov, 1, 0.1, 1000);
    this.camera.position.set(...cam);
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    el.appendChild(this.renderer.domElement);
    this.labels = new CSS2DRenderer();
    this.labels.domElement.className = 'label-layer';
    el.appendChild(this.labels.domElement);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.target.set(...target);
    this.controls.enableDamping = true;
    this.controls.minDistance = minDist;
    this.controls.maxDistance = maxDist;
    this.controls.maxPolarAngle = Math.PI * 0.47;
    this.baseOffset = this.camera.position.clone().sub(this.controls.target);
    this.userMoved = false;
    this.controls.addEventListener('start', () => { this.userMoved = true; });
    this.clock = new THREE.Clock();
    this.frameFns = [];
    this.running = false;
    this.hemi = new THREE.HemisphereLight(0xffffff, 0x445544, 1.1);
    this.scene.add(this.hemi);
    this.sunLight = new THREE.DirectionalLight(0xffffff, 1.6);
    this.sunLight.position.set(30, 50, 20);
    this.sunLight.castShadow = true;
    this.sunLight.shadow.mapSize.set(2048, 2048);
    const sc = this.sunLight.shadow.camera; sc.left = -50; sc.right = 50; sc.top = 50; sc.bottom = -50; sc.far = 160;
    this.scene.add(this.sunLight);
    this.ray = new THREE.Raycaster();
    this.pointer = new THREE.Vector2();
    this.pickables = [];
    this.hovered = null;
    new ResizeObserver(() => this.resize()).observe(el);
    this.resize();
    this.renderer.domElement.addEventListener('pointermove', (e) => this._move(e));
    this.renderer.domElement.addEventListener('click', (e) => this._click(e));
  }
  resize() {
    const w = this.el.clientWidth, h = this.el.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h);
    this.labels.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    // en pantallas angostas la cámara se aleja para que la escena quepa
    if (!this.userMoved) this.camera.position.copy(this.controls.target).add(this.baseOffset.clone().multiplyScalar(Math.max(1, Math.pow(1.5 / this.camera.aspect, 0.75))));
  }
  label(html, cls = '', pos = [0, 0, 0], parent = this.scene) {
    const div = document.createElement('div');
    div.className = `lbl ${cls}`;
    div.innerHTML = html;
    const o = new CSS2DObject(div);
    o.position.set(...pos);
    parent.add(o);
    return o;
  }
  onFrame(fn) { this.frameFns.push(fn); }
  start() {
    if (this.running) return;
    this.running = true;
    this.clock.getDelta();
    const loop = () => {
      if (!this.running) return;
      const dt = Math.min(this.clock.getDelta(), 0.05);
      const t = this.clock.elapsedTime;
      this.frameFns.forEach((fn) => fn(dt, t));
      this.controls.update();
      this.renderer.render(this.scene, this.camera);
      this.labels.render(this.scene, this.camera);
      this.raf = requestAnimationFrame(loop);
    };
    loop();
  }
  stop() { this.running = false; cancelAnimationFrame(this.raf); }
  _hit(e) {
    const r = this.renderer.domElement.getBoundingClientRect();
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
      this.renderer.domElement.style.cursor = o ? 'pointer' : '';
    }
  }
  _click(e) { const o = this._hit(e); if (o?.userData.onPick) o.userData.onPick(); }
  pickable(obj, handlers) { obj.userData.pick = true; Object.assign(obj.userData, handlers); this.pickables.push(obj); }
}

// Material estándar mate; las escenas usan pocos materiales para que el tema se pueda reaplicar.
export function mat(color, opts = {}) {
  return new THREE.MeshStandardMaterial({ color, roughness: 0.82, metalness: 0.04, ...opts });
}

export function box(w, h, d, material, x = 0, y = 0, z = 0) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), material);
  m.position.set(x, y + h / 2, z);
  m.castShadow = true; m.receiveShadow = true;
  return m;
}

// Panel solar: losa fina inclinada 10° (latitud de Yondó ~7° N) orientada al sur.
export function solarArray(cols, rows, material, frameMat, tilt = 0.17) {
  const g = new THREE.Group();
  const geo = new THREE.BoxGeometry(0.95, 0.05, 1.6);
  const inst = new THREE.InstancedMesh(geo, material, cols * rows);
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion().setFromEuler(new THREE.Euler(tilt, 0, 0));
  let i = 0;
  for (let c = 0; c < cols; c++) for (let r = 0; r < rows; r++) {
    m4.compose(new THREE.Vector3(c * 1.02 - (cols - 1) * 0.51, 0.25, r * 1.7 - (rows - 1) * 0.85), q, new THREE.Vector3(1, 1, 1));
    inst.setMatrixAt(i++, m4);
  }
  inst.castShadow = true;
  g.add(inst);
  if (frameMat) {
    const leg = new THREE.Mesh(new THREE.BoxGeometry(cols * 1.02, 0.2, 0.08), frameMat);
    leg.position.y = 0.1; g.add(leg);
  }
  return g;
}

// Partículas que viajan por una curva: la densidad y la velocidad codifican la potencia.
export class Flow {
  constructor(scene, curve, color, { max = 26, size = 0.16 } = {}) {
    this.curve = curve;
    this.max = max;
    this.mesh = new THREE.InstancedMesh(new THREE.SphereGeometry(size, 10, 8), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.95 }), max);
    this.mesh.frustumCulled = false;
    scene.add(this.mesh);
    this.offsets = Array.from({ length: max }, (_, i) => i / max);
    this.power = 0; this.dir = 1; this.phase = 0;
    this.tube = new THREE.Mesh(new THREE.TubeGeometry(curve, 48, 0.05, 6, false), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.28 }));
    scene.add(this.tube);
    this._m = new THREE.Matrix4(); this._p = new THREE.Vector3(); this._zero = new THREE.Matrix4().makeScale(0, 0, 0);
  }
  set(power, dir) { this.power = power; this.dir = dir; }
  setColor(c) { this.mesh.material.color.set(c); this.tube.material.color.set(c); }
  visible(v) { this.mesh.visible = v; this.tube.visible = v; }
  update(dt) {
    const n = Math.round(Math.min(1, this.power) * this.max);
    this.phase = (this.phase + dt * (0.12 + 0.35 * Math.min(1, this.power)) * (reducedMotion ? 0.3 : 1)) % 1;
    for (let i = 0; i < this.max; i++) {
      if (i >= n) { this.mesh.setMatrixAt(i, this._zero); continue; }
      let t = (this.offsets[i] + this.phase) % 1;
      if (this.dir < 0) t = 1 - t;
      this.curve.getPointAt(t, this._p);
      this._m.makeTranslation(this._p.x, this._p.y, this._p.z);
      this.mesh.setMatrixAt(i, this._m);
    }
    this.mesh.instanceMatrix.needsUpdate = true;
  }
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
