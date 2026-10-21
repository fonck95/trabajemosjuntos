// Carga de modelos glTF/GLB profesionales: Draco, Meshopt y KTX2, con detección de WebAssembly,
// caché por URL, niveles de detalle progresivos, auto-encuadre y métricas de costo en GPU.
import { THREE, engine } from './core.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { KTX2Loader } from 'three/addons/loaders/KTX2Loader.js';

const base = new URL('../', import.meta.url);
const cache = new Map();
let loaderPromise = null;

// Algunos entornos bloquean la compilación de WebAssembly: entonces Draco usa su decodificador JS
export function wasmAllowed() {
  try { new WebAssembly.Module(Uint8Array.of(0, 97, 115, 109, 1, 0, 0, 0)); return true; } catch { return false; }
}

export function getLoader() {
  if (loaderPromise) return loaderPromise;
  loaderPromise = (async () => {
    const renderer = engine.ensure();
    const wasm = typeof WebAssembly === 'object' && wasmAllowed();
    const loader = new GLTFLoader();
    const draco = new DRACOLoader().setDecoderPath(new URL('vendor/draco/', base).href).setDecoderConfig({ type: wasm ? 'wasm' : 'js' }).setWorkerLimit(2);
    loader.setDRACOLoader(draco);
    const caps = { draco: wasm ? 'wasm' : 'js', ktx2: false, meshopt: false };
    if (wasm) {
      try {
        const ktx2 = new KTX2Loader().setTranscoderPath(new URL('vendor/basis/', base).href).detectSupport(renderer);
        loader.setKTX2Loader(ktx2);
        caps.ktx2 = true;
      } catch (e) { console.warn('KTX2 no disponible', e); }
      try {
        const { MeshoptDecoder } = await import('three/addons/libs/meshopt_decoder.module.js');
        await MeshoptDecoder.ready;
        loader.setMeshoptDecoder(MeshoptDecoder);
        caps.meshopt = true;
      } catch (e) { console.warn('Meshopt no disponible', e); }
    }
    return { loader, caps };
  })();
  return loaderPromise;
}

function prepare(root) {
  const maxAniso = engine.renderer.capabilities.getMaxAnisotropy();
  root.traverse((o) => {
    if (o.isMesh) {
      o.castShadow = true; o.receiveShadow = true;
      const ms = Array.isArray(o.material) ? o.material : [o.material];
      ms.forEach((m) => { ['map', 'normalMap', 'roughnessMap', 'metalnessMap', 'aoMap', 'emissiveMap'].forEach((k) => { if (m[k]) m[k].anisotropy = Math.min(8, maxAniso); }); });
    }
  });
  return root;
}

// Descarga el binario. Algunos hospedajes no sirven .glb: entonces se usa la copia
// "<archivo>.glb.json" con el binario en base64. Se valida la firma "glTF" del encabezado.
async function fetchGLB(abs) {
  const res = await fetch(abs).catch(() => null);
  if (res && res.ok) {
    const buf = await res.arrayBuffer();
    if (buf.byteLength > 12 && new DataView(buf).getUint32(0, true) === 0x46546c67) return buf;
  }
  const alt = await fetch(`${abs}.json`);
  if (!alt.ok) throw new Error(`No se pudo descargar ${abs.split('/').pop()} (${alt.status})`);
  const { glb } = await alt.json();
  const bin = atob(glb), u8 = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
  return u8.buffer;
}

// Carga (una sola vez por URL) y devuelve { gltf, ms, bytes }
export async function loadModel(url) {
  const abs = new URL(url, base).href;
  if (!cache.has(abs)) {
    cache.set(abs, (async () => {
      const { loader } = await getLoader();
      const t0 = performance.now();
      const buf = await fetchGLB(abs);
      const gltf = await loader.parseAsync(buf, abs.replace(/[^/]*$/, ''));
      prepare(gltf.scene);
      return { gltf, ms: performance.now() - t0, bytes: buf.byteLength };
    })());
  }
  return cache.get(abs);
}

// Modelo desde un archivo local (arrastrar y soltar). No se cachea.
export async function parseFile(file) {
  const { loader } = await getLoader();
  const t0 = performance.now();
  const buf = await file.arrayBuffer();
  const gltf = await loader.parseAsync(buf, '');
  prepare(gltf.scene);
  return { gltf, ms: performance.now() - t0, bytes: buf.byteLength };
}

// Copia ligera: comparte geometrías y materiales con el original
export const instantiate = (gltf) => gltf.scene.clone(true);

// Nivel de detalle progresivo: muestra primero el modelo liviano y cambia al detallado al cargar.
// levels: [{ url, distance }] del más detallado (distance 0) al más simple.
export function progressiveLOD(levels, onReady) {
  const lod = new THREE.LOD();
  const order = [...levels].sort((a, b) => b.distance - a.distance);
  order.reduce((p, lv) => p.then(async () => {
    const { gltf } = await loadModel(lv.url);
    // histéresis del 15 %: cerca del umbral no salta de un nivel a otro con cada movimiento
    lod.addLevel(instantiate(gltf), lv.distance, lv.distance ? 0.15 : 0);
    onReady?.(lod, lv);
  }), Promise.resolve()).catch((e) => console.warn('LOD', e));
  return lod;
}

// Malla instanciada a partir de un modelo GLB (cada primitiva → un InstancedMesh con las mismas matrices)
export function instancedFromModel(gltf, matrices, scale = 1) {
  const g = new THREE.Group();
  const s = new THREE.Matrix4().makeScale(scale, scale, scale);
  gltf.scene.updateMatrixWorld(true);
  gltf.scene.traverse((o) => {
    if (!o.isMesh) return;
    const im = new THREE.InstancedMesh(o.geometry, o.material, matrices.length);
    const local = o.matrixWorld.clone();
    matrices.forEach((m, i) => im.setMatrixAt(i, m.clone().multiply(s).multiply(local)));
    im.castShadow = true; im.receiveShadow = true;
    im.computeBoundingSphere();
    g.add(im);
  });
  return g;
}

// Centra el modelo sobre el piso y devuelve su tamaño para encuadrar la cámara
export function fit(object, targetSize) {
  const box = new THREE.Box3().setFromObject(object);
  const size = box.getSize(new THREE.Vector3()), center = box.getCenter(new THREE.Vector3());
  const k = targetSize ? targetSize / Math.max(size.x, size.y, size.z) : 1;
  object.scale.multiplyScalar(k);
  object.position.sub(new THREE.Vector3(center.x * k, box.min.y * k, center.z * k));
  return size.multiplyScalar(k);
}

// Métricas del modelo: lo que cuesta en GPU
export function stats(object, gltf) {
  let meshes = 0, tris = 0;
  const instGroups = new Map(); // un objeto con varias primitivas instanciadas cuenta una vez
  const geos = new Set(), mats = new Set(), texs = new Set();
  object.traverse((o) => {
    if (!o.isMesh) return;
    meshes++;
    const g = o.geometry; geos.add(g);
    const n = g.index ? g.index.count / 3 : g.attributes.position.count / 3;
    const k = o.isInstancedMesh ? o.count : 1;
    if (o.isInstancedMesh) instGroups.set(o.parent, o.count);
    tris += n * k;
    (Array.isArray(o.material) ? o.material : [o.material]).forEach((m) => { mats.add(m); Object.values(m).forEach((v) => { if (v && v.isTexture) texs.add(v); }); });
  });
  const instanced = [...instGroups.values()].reduce((a, b) => a + b, 0);
  let gpu = 0;
  geos.forEach((g) => { Object.values(g.attributes).forEach((a) => { gpu += a.array.byteLength; }); if (g.index) gpu += g.index.array.byteLength; });
  texs.forEach((t) => { const im = t.image; if (im && im.width) gpu += im.width * im.height * 4 * 1.33; });
  const ext = gltf?.parser?.json?.extensionsUsed || [];
  return { meshes, tris: Math.round(tris), instanced, geometries: geos.size, materials: mats.size, textures: texs.size, gpuMB: gpu / 1048576, extensions: ext };
}
