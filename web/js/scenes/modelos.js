// Visor de modelos profesionales (glTF 2.0 / GLB): arrastrar y soltar, iluminación física,
// métricas de costo en GPU y guía del pipeline para llevar modelos BIM/CAD al atlas.
import { THREE, Stage, engine, tokens, onTheme, fmtN, gsap, disposeObject, solidBox, conexionLabels } from '../core.js';
import { getLoader, loadModel, parseFile, fit, stats } from '../assets.js';

const GUIA = [
  { tag: 'Paso 1', titulo: 'Exporta a glTF binario', html: '<ul class="tight"><li><b>Revit:</b> complemento de exportación glTF o paso por IFC → Blender.</li><li><b>SketchUp / Rhino / ArchiCAD:</b> exportador glTF o FBX → Blender.</li><li><b>Blender:</b> Archivo → Exportar → glTF 2.0, formato <code>.glb</code>, con modificadores aplicados y +Y arriba.</li><li>Unidades en metros: el visor encuadra cualquier escala.</li></ul>' },
  { tag: 'Paso 2', titulo: 'Optimiza antes de publicar', html: '<p>Comprime geometría y texturas, une mallas por material e instancia lo repetido:</p><pre class="cmd">npx @gltf-transform/cli optimize \\\n  hospital.glb hospital_lod0.glb \\\n  --compress draco \\\n  --texture-compress ktx2\n\n# nivel de detalle bajo (25 % de triángulos)\nnpx @gltf-transform/cli simplify \\\n  hospital_lod0.glb hospital_lod1.glb \\\n  --ratio 0.25 --error 0.01</pre>' },
  { tag: 'Paso 3', titulo: 'Publícalo en el atlas', html: '<ol class="tight"><li>Copia el archivo a <code>web/models/</code>.</li><li>Agrégalo a <code>web/models/manifest.json</code> para que aparezca en este visor.</li><li>En una escena, cárgalo con <code>progressiveLOD([{url, distance: 0}, {url: lod1, distance: 85}])</code>: se ve primero el liviano y luego el detallado.</li><li>Objetivo para teléfonos: menos de 300.000 triángulos visibles y 50 llamadas de dibujo.</li></ol><p class="note">Los modelos del atlas se generan con <code>scripts/modelos/build_models.mjs</code>.</p>' },
];

// Retícula del piso que se desvanece con la distancia: las líneas densas cerca del horizonte hacían moiré.
// n celdas por lado de 1 unidad; cada línea va en tramos para que la transparencia cambie a lo largo de ella
function reticula(color, n = 40) {
  const h = n / 2, pos = [], col = [], a = (x, z) => Math.max(0, 1 - Math.hypot(x, z) / h) ** 1.6;
  for (let i = 0; i <= n; i++) {
    const u = -h + i;
    for (let j = 0; j < n; j++) {
      const v0 = -h + j, v1 = v0 + 1;
      pos.push(u, 0, v0, u, 0, v1, v0, 0, u, v1, 0, u);
      col.push(1, 1, 1, a(u, v0), 1, 1, 1, a(u, v1), 1, 1, 1, a(v0, u), 1, 1, 1, a(v1, u));
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('color', new THREE.Float32BufferAttribute(col, 4));
  return new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color, vertexColors: true, transparent: true, opacity: 0.6, depthWrite: false }));
}
// nombre corto de cada sede para la lista: conserva la sede ("Luis Eduardo Díaz · sede Megacolegio") y corta lo demás
const CORTO = { relleno_parque: 'Relleno → parque ecotecnológico' };
const corto = (m) => CORTO[m.id] || m.nombre.replace(/^(E\.S\.E\.|I\.E\.)\s*/, '').replace(/\s+S\.A\.\s+E\.S\.P\.$/, '').replace(/\s*–\s*(sede\s)/i, ' · $1').split(/\s*[(,–—]/)[0].trim();

export function mount(root) {
  const el = root.querySelector('.stage');
  const st = new Stage(el, { cam: [9, 6, 12], target: [0, 1.5, 0], minDist: 0.5, maxDist: 400, tone: 'aces', exposure: 1.1 });
  st.controls.maxPolarAngle = Math.PI * 0.495;
  const T = tokens();
  const S = st.scene;
  // piso que solo recibe sombra + retícula sutil
  const catcher = new THREE.Mesh(new THREE.CircleGeometry(400, 64), new THREE.ShadowMaterial({ opacity: 0.22 }));
  catcher.rotation.x = -Math.PI / 2; catcher.receiveShadow = true; S.add(catcher);
  const grid = reticula(T.line); S.add(grid);
  st.freeze(catcher); st.freeze(grid);

  const q = (s) => root.querySelector(`[data-slot="${s}"]`);
  const estado = q('modelos.estado'), statsEl = q('modelos.stats');
  const ctl = { wire: root.querySelector('#md-wire'), shadow: root.querySelector('#md-shadow'), env: root.querySelector('#md-env'), rot: root.querySelector('#md-rot') };
  let current = null, currentIsFile = false, holder = new THREE.Group();
  S.add(holder);

  function setStats(info, s, nombre) {
    const r = engine.renderer.info.render;
    const ext = s.extensions.length ? s.extensions.map((e) => e.replace(/^(KHR_|EXT_)/, '')).join(', ') : 'ninguna';
    statsEl.innerHTML = `<dt>Modelo</dt><dd style="white-space:normal;overflow-wrap:anywhere;text-align:left;font-family:inherit">${nombre}</dd>
      <dt>Triángulos</dt><dd>${fmtN(s.tris)}</dd>
      <dt>Mallas</dt><dd>${fmtN(s.meshes)}${s.instanced ? ` · ${fmtN(s.instanced)} instancias GPU` : ''}</dd>
      <dt>Geometrías · materiales · texturas</dt><dd>${s.geometries} · ${s.materials} · ${s.textures}</dd>
      <dt>Memoria en GPU (estimada)</dt><dd>${s.gpuMB.toFixed(2)} MB</dd>
      <dt>Peso del archivo</dt><dd>${(info.bytes / 1024).toFixed(0)} KB</dd>
      <dt>Carga y decodificación</dt><dd>${info.ms.toFixed(0)} ms</dd>
      <dt>Extensiones</dt><dd style="white-space:normal;overflow-wrap:anywhere">${ext}</dd>
      <dt>Llamadas de dibujo (escena)</dt><dd data-calls>${r.calls}</dd>`;
    setTimeout(() => { const c = statsEl.querySelector('[data-calls]'); if (c) c.textContent = engine.renderer.info.render.calls; }, 400);
  }

  // Copia aislada: materiales propios para poder activar la malla sin tocar otras vistas
  function isolate(scene) {
    const c = scene.clone(true);
    c.traverse((o) => { if (o.isMesh) o.material = Array.isArray(o.material) ? o.material.map((m) => m.clone()) : o.material.clone(); });
    return c;
  }

  // puntos de la conexión que exporta el generador (tablero con medidor, gateway IoT, acometida de la red)
  let cxLabels = [];
  function show(info, nombre, m) {
    // CSS2DRenderer solo borra el elemento del objeto que se quita, no el de sus hijos
    cxLabels.forEach((l) => { l.element.remove(); l.removeFromParent(); }); cxLabels = [];
    if (current) { holder.remove(current); if (currentIsFile) disposeObject(current); else current.traverse((o) => { if (o.isMesh) (Array.isArray(o.material) ? o.material : [o.material]).forEach((m) => m.dispose()); }); }
    current = isolate(info.gltf.scene);
    holder.rotation.y = 0;
    holder.add(current);
    const size = fit(current);
    applyView();
    const R = Math.max(size.x, size.y, size.z);
    // la retícula se ajusta al modelo: celdas de un paso redondo (1, 2, 5, 10 m…) cerca de una décima de su tamaño
    const paso = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50].find((x) => x >= R / 10) || 100;
    grid.scale.setScalar(paso); grid.updateMatrix();
    const sc = st.sunLight.shadow.camera; sc.left = -R; sc.right = R; sc.top = R; sc.bottom = -R; sc.near = 0.1; sc.far = R * 6; sc.updateProjectionMatrix();
    st.sunLight.position.set(R * 0.9, R * 1.6, R * 0.7);
    st.controls.maxDistance = R * 8;
    // se encuadra lo que tiene volumen (edificios, tanques, árboles): los pisos planos del predio (parqueaderos,
    // zonas verdes) agrandan la caja sin aportar y dejaban el edificio diminuto
    // los edificios alargados se miran de costado para que el largo use el ancho de la pantalla
    const sb = solidBox(current), ss = sb.getSize(new THREE.Vector3());
    const dir = ss.z > ss.x * 1.4 ? new THREE.Vector3(1.7, 0.85, 0.55) : ss.x > ss.z * 1.4 ? new THREE.Vector3(0.55, 0.85, 1.7) : new THREE.Vector3(1.25, 0.8, 1.6);
    // en el teléfono (recuadro vertical) se mira un poco más desde arriba y con menos margen: el edificio sale más grande
    const angosto = el.clientWidth < 560;
    if (angosto) dir.y *= 1.5;
    st.frameBox(sb, dir, { margin: angosto ? 0.92 : 0.8, duration: 1.3 });
    if (gsap) gsap.from(current.scale, { x: 0.001, y: 0.001, z: 0.001, duration: 0.8, ease: 'back.out(1.4)', onUpdate: () => st.invalidate(true) });
    st.updateShadows();
    setStats(info, stats(current, info.gltf), nombre);
    cxLabels = conexionLabels(st, m?.conexion, current, (pos) => {
      // primer plano: afuera del edificio, frente al tablero
      const p = current.localToWorld(new THREE.Vector3(...pos)), c = solidBox(current).getCenter(new THREE.Vector3());
      const out = p.clone().sub(c).setY(0);
      if (out.lengthSq() < 0.01) out.set(0, 0, 1);
      p.y = Math.max(1, p.y - 1.4);
      st.closeUp(p, [current], out.normalize(), { dist: 12 });
    });
    // en el teléfono la etiqueta de la conexión va corta para no tapar el edificio (el detalle está al acercarse)
    if (angosto) cxLabels.forEach((l) => l.element.querySelectorAll('span').forEach((x) => { x.textContent = x.textContent.replace(' + medidor bidireccional', ' y medidor').replace(' → CCED', '').replace(/(Acometida|Poste) de la red \(EPM\)/, '$1 EPM'); }));
    applyLayer();
  }

  function applyView() {
    if (!current) return;
    current.traverse((o) => { if (o.isMesh) (Array.isArray(o.material) ? o.material : [o.material]).forEach((m) => { m.wireframe = ctl.wire.checked; }); o.castShadow = ctl.shadow.checked; });
    S.environment = ctl.env.checked ? engine.env : null;
    st.hemi.intensity = ctl.env.checked ? 0.55 : 1.1;
    st.updateShadows();
  }
  Object.values(ctl).forEach((c) => c.addEventListener('input', applyView));

  async function loadUrl(m) {
    estado.textContent = `Cargando ${m.titulo}…`;
    try {
      const info = await loadModel(m.archivo);
      currentIsFile = false;
      show(info, m.titulo, m);
      estado.textContent = `${m.titulo}: ${(m.bytes_sin_comprimir / 1024).toFixed(0)} KB sin comprimir → ${(m.bytes / 1024).toFixed(0)} KB con Draco.`;
    } catch (e) { estado.textContent = `No se pudo cargar el modelo: ${e.message}`; }
  }
  async function loadFile(file) {
    if (!/\.glb$/i.test(file.name)) { estado.textContent = 'Usa un archivo .glb (glTF binario). Un .gltf con archivos externos no se puede abrir desde aquí.'; return; }
    estado.textContent = `Leyendo ${file.name}…`;
    try {
      const info = await parseFile(file);
      currentIsFile = true;
      show(info, file.name);
      estado.textContent = `${file.name} cargado desde tu equipo.`;
      lista.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', 'false'));
    } catch (e) { estado.textContent = `No se pudo leer ${file.name}: ${e.message}`; }
  }

  // lista de modelos del atlas: réplicas de las sedes reales + modelos de componentes
  const lista = q('modelos.lista');
  const capas = document.createElement('div');
  capas.className = 'seg'; capas.style.marginTop = '8px'; capas.hidden = true; capas.setAttribute('role', 'group'); capas.setAttribute('aria-label', 'Capa');
  capas.innerHTML = '<button type="button" data-capa="hoy" aria-pressed="false">Hoy</button><button type="button" data-capa="proyecto" aria-pressed="true">Con el proyecto</button>';
  lista.after(capas);
  let proyecto = true;
  const applyLayer = () => {
    if (!current) return;
    let has = false;
    current.traverse((o) => {
      if (o.name === 'adecuaciones') { has = true; o.visible = proyecto; }
      if (o.name === 'cubierta_actual' && o.userData.reemplazada) o.visible = !proyecto;
      if (o.userData.demoler) o.visible = !proyecto;
    });
    capas.hidden = !has;
    cxLabels.forEach((l) => { l.visible = proyecto; });
    st.updateShadows();
  };
  capas.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => {
    proyecto = b.dataset.capa === 'proyecto';
    capas.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    applyLayer();
  }));
  const getJSON = (u) => fetch(new URL(u, import.meta.url)).then((r) => (r.ok ? r.json() : [])).catch(() => []);
  Promise.all([getJSON('../../models/edificios/manifest.json'), getJSON('../../models/manifest.json')]).then(([sedes, comp]) => {
    const man = [...sedes.map((m) => ({ ...m, titulo: m.nombre, corto: m.corto || corto(m) })), ...comp];
    if (!man.length) throw new Error('vacío');
    lista.innerHTML = man.map((m, i) => `<button type="button" data-i="${i}" aria-pressed="${i === 0}">${m.corto || m.titulo.replace('Hospital Héctor Abad Gómez', 'Hospital').replace(/\s*\(.*\)/, (x) => x.includes('bajo') ? ' · liviano' : ' · detallado')}</button>`).join('');
    lista.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => {
      lista.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
      loadUrl(man[+b.dataset.i]);
    }));
    loadUrl(man[0]);
  }).catch(() => { estado.textContent = 'No se encontró el catálogo de modelos; puedes cargar tu propio GLB.'; });

  // archivo local: botón y arrastrar y soltar
  root.querySelector('#md-file').addEventListener('change', (e) => { const f = e.target.files[0]; if (f) loadFile(f); e.target.value = ''; });
  const drop = q('modelos.drop');
  ['dragenter', 'dragover'].forEach((ev) => el.addEventListener(ev, (e) => { e.preventDefault(); drop.hidden = false; }));
  ['dragleave', 'drop'].forEach((ev) => el.addEventListener(ev, (e) => { e.preventDefault(); if (ev === 'dragleave' && el.contains(e.relatedTarget)) return; drop.hidden = true; }));
  el.addEventListener('drop', (e) => { const f = e.dataTransfer?.files?.[0]; if (f) loadFile(f); });

  // capacidades del navegador
  getLoader().then(({ caps }) => {
    const r = engine.renderer;
    const items = [
      [`Draco ${caps.draco === 'wasm' ? 'WebAssembly' : 'JavaScript'}`, caps.draco === 'wasm' ? 'on' : 'mid'],
      ['Meshopt', caps.meshopt ? 'on' : ''], ['Texturas KTX2', caps.ktx2 ? 'on' : ''],
      [`WebGL ${r.capabilities.isWebGL2 ? '2' : '1'}`, r.capabilities.isWebGL2 ? 'on' : 'mid'],
      [`Textura máx. ${r.capabilities.maxTextureSize}px`, 'on'], [`Anisotropía ×${r.capabilities.getMaxAnisotropy()}`, 'on'],
    ];
    q('modelos.caps').innerHTML = items.map(([t, c]) => `<span class="${c}">${t}</span>`).join('');
  });
  q('modelos.guia').innerHTML = GUIA.map((g) => `<div class="card"><p class="eyebrow">${g.tag}</p><h3>${g.titulo}</h3>${g.html}</div>`).join('');

  st.onFrame((dt) => {
    if (!ctl.rot.checked || !current || st.flying) return false;
    holder.rotation.y += dt * 0.25;
    st.shadowDirty = true;
    return true;
  });
  onTheme((t) => { grid.material.color.copy(t.line); });
  return st;
}
