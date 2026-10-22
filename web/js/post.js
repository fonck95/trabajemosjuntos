// Posproceso de la calidad 'alta' (se carga solo cuando hace falta). Una sola cadena para todas las vistas:
//   1. RenderPass dibuja la escena en un render target con MSAA (bordes suaves) y textura de profundidad. El
//      render target trabaja como el lienzo: el mapeo de tonos de cada vista y el sRGB se aplican en los shaders
//      y las transparencias se mezclan igual que en el render directo (misma apariencia en todas las calidades).
//   2. Entre lo opaco y lo transparente se calcula la oclusión ambiental (GTAO) con la profundidad ya dibujada y
//      se multiplica sobre lo opaco. Así las líneas, los halos, los vidrios y las partículas se dibujan después,
//      limpios, y el fondo (CSS o cielo) no se oscurece: donde no hay geometría la profundidad es 1 y no hay AO.
//   3. Una pasada final copia el resultado al lienzo con alfa premultiplicado: el lienzo sigue transparente sobre el
//      fondo de la página.
// Respeta el renderizado bajo demanda: Engine llama a render() solo cuando hace falta un cuadro.
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';
import { GTAOPass } from 'three/addons/postprocessing/GTAOPass.js';

const _size = new THREE.Vector2();

// Copia al lienzo tal cual: el render target ya tiene lo que tendría el lienzo (colores en sRGB, alfa premultiplicado)
const SalidaShader = {
  name: 'SalidaShader',
  uniforms: { tDiffuse: { value: null } },
  vertexShader: 'varying vec2 vUv;\nvoid main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
  fragmentShader: 'uniform sampler2D tDiffuse;\nvarying vec2 vUv;\nvoid main() { gl_FragColor = texture2D(tDiffuse, vUv); }',
};

// GTAO de three r160 supone que la oclusión tiene la misma resolución que la profundidad. A media resolución cada
// píxel cae entre cuatro de la profundidad y la posición reconstruida se corre medio téxel: en vistas lejanas y
// rasantes aparecen bandas horizontales. Se centra la coordenada en el téxel de profundidad que se lee.
function centrarEnTexel(m) {
  m.vertexShader = m.vertexShader.replace('varying vec2 vUv;', 'varying vec2 vUvQ;').replace('vUv = uv;', 'vUvQ = uv;');
  m.fragmentShader = m.fragmentShader.replace('varying vec2 vUv;', 'varying vec2 vUvQ;\nvec2 vUv;')
    .replace('void main() {', 'void main() {\n\tvec2 tsz = vec2( textureSize( tDepth, 0 ) );\n\tvUv = ( floor( vUvQ * tsz ) + 0.5 ) / tsz;');
  m.needsUpdate = true;
}

export class Post {
  constructor(renderer) {
    this.renderer = renderer;
    this.w = 0; this.h = 0; this.pr = 0;
    this.extra = 0; // llamadas de dibujo del posproceso en el último cuadro (no cuentan como de la escena)
    const rt = new THREE.WebGLRenderTarget(1, 1, { type: THREE.UnsignedByteType, internalFormat: 'RGBA8', samples: 4, depthTexture: new THREE.DepthTexture(1, 1), colorSpace: THREE.SRGBColorSpace });
    rt.texture.name = 'Post.escena';
    this.composer = new EffectComposer(renderer, rt);
    this.scenePass = new RenderPass(new THREE.Scene(), new THREE.PerspectiveCamera());
    this.output = new ShaderPass(SalidaShader);
    // sin intercambio de búferes: RenderPass escribe siempre en el mismo render target (con MSAA y profundidad) y
    // la salida lo lee; el segundo búfer del compositor nunca se usa y no ocupa memoria de GPU
    this.output.needsSwap = false;
    const out = this.output, render = out.render.bind(out);
    out.render = (...a) => { const c = renderer.info.render.calls; render(...a); this.extra += renderer.info.render.calls - c; };
    this.composer.addPass(this.scenePass);
    this.composer.addPass(this.output);
    this.beauty = this.composer.readBuffer;
    // En three r160 un render target marcado como de XR se trata como el lienzo: los materiales aplican el tono
    // (ACES u otro) y la codificación sRGB, y la mezcla de transparencias ocurre en el espacio de la pantalla. Con 8
    // bits por canal (RGBA8, sin conversión sRGB del hardware) los valores se recortan a 1 igual que en el lienzo.
    // Así las opacidades con que se diseñaron halos, huellas y vidrios se ven igual que en el render directo; en un
    // render target lineal de media precisión quedarían más pálidas. (No se usa para XR.)
    this.beauty.isXRRenderTarget = true;
    this.beauty.texture.colorSpace = THREE.SRGBColorSpace;
    this.beauty.texture.internalFormat = 'RGBA8';

    // GTAO con normales reconstruidas desde la profundidad de la escena: no hace falta otra pasada de geometría
    // (las llamadas de dibujo de la escena no se duplican)
    this.gtao = new GTAOPass(new THREE.Scene(), new THREE.PerspectiveCamera(), 1, 1);
    this.gtao.setGBuffer(this.beauty.depthTexture);
    centrarEnTexel(this.gtao.gtaoMaterial); centrarEnTexel(this.gtao.pdMaterial);
    // 32 muestras (5 direcciones) y un filtro amplio: sin el grano de las normales reconstruidas;
    // la oclusión se multiplica sobre colores ya codificados en sRGB: el exponente bajo equivale a ~1,3 en lineal
    this.gtao.updateGtaoMaterial({ samples: 32, distanceExponent: 1.4, distanceFallOff: 1, scale: 0.6 });
    this.gtao.updatePdMaterial({ lumaPhi: 10, normalPhi: 1, radius: 10, rings: 2, samples: 24 });

    // Centinela: la primera pieza de la lista de transparentes (renderOrder muy bajo). Su onBeforeRender corre
    // cuando lo opaco ya está dibujado y antes de cualquier transparencia: ahí se calcula y aplica la oclusión.
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array(9), 3));
    this.sentinel = new THREE.Mesh(g, new THREE.MeshBasicMaterial({ transparent: true, depthTest: false, depthWrite: false, colorWrite: false }));
    Object.assign(this.sentinel, { name: 'post-oclusion', frustumCulled: false, renderOrder: -1e9 });
    this.sentinel.onBeforeRender = (r, scene, camera) => this._oclusion(r, camera);
    this._vacia = new THREE.Scene();
    // radio = distancia de la cámara × k (acotado por la escala de la vista); grosor: profundidad que cuenta como
    // oclusor, en radios; intensidad por omisión (las vistas la pueden cambiar con la opción ao)
    this.ao = { on: true, intensity: 1, base: 1, grosor: 2, k: 0.04 };
    this._escena = null; this._n = 0;
  }

  // Tamaño y pixel ratio del lienzo compartido; al cambiar se reubica todo en el mismo cuadro (sin cuadro en blanco)
  _sync() {
    const r = this.renderer, pr = r.getPixelRatio();
    r.getSize(_size);
    if (_size.x === this.w && _size.y === this.h && pr === this.pr) return;
    this.w = _size.x; this.h = _size.y; this.pr = pr;
    // en pantallas densas 2 muestras bastan (los píxeles ya son pequeños) y la memoria se mantiene razonable
    const samples = pr > 1.5 ? 2 : 4;
    if (this.beauty.samples !== samples) { this.beauty.samples = samples; this.beauty.dispose(); }
    this.composer.setPixelRatio(pr);
    this.composer.setSize(this.w, this.h);
    // en pantallas densas la oclusión se calcula a media resolución (un cuarto del costo; cada téxel sigue siendo un
    // píxel CSS). Con pixel ratio 1 va a resolución completa: a media, las aristas entre muro y piso dejan puntos claros
    const k = pr > 1.25 ? 0.5 : 1, aw = Math.max(1, Math.round(this.w * pr * k)), ah = Math.max(1, Math.round(this.h * pr * k));
    const g = this.gtao;
    g.gtaoRenderTarget.setSize(aw, ah); g.pdRenderTarget.setSize(aw, ah);
    g.gtaoMaterial.uniforms.resolution.value.set(aw, ah); g.pdMaterial.uniforms.resolution.value.set(aw, ah);
  }

  // Parámetros de oclusión de la vista: radio en unidades del mundo, proporcional a la distancia de la cámara
  // (detalle fino de cerca, contacto amplio de lejos) y acotado por la escala de la escena
  _params(s) {
    const a = s.aoCfg, on = a !== false;
    this.ao.on = on;
    if (!on) return;
    const d = s.camera.position.distanceTo(s.controls.target);
    const max = a.radius ?? s.aoMax, r = THREE.MathUtils.clamp(d * this.ao.k, max * 0.15, max);
    const u = this.gtao.gtaoMaterial.uniforms;
    u.radius.value = r; u.thickness.value = r * this.ao.grosor;
    this.gtao.pdMaterial.uniforms.depthPhi.value = r * 0.8;
    this.ao.intensity = a.intensity ?? this.ao.base;
  }

  // Las líneas (Line, LineSegments, Line2) y los puntos van con las transparencias, después de la oclusión: así no
  // dejan un halo oscuro alrededor ni quedan sucios. Si alguna es opaca se marca transparente (con opacidad 1 se ve
  // igual). Se revisa al cambiar de escena y cada tanto, porque las escenas agregan objetos al cargar modelos.
  _lineas(scene) {
    if (scene === this._escena && ++this._n % 90) return;
    this._escena = scene; this._n = 0;
    scene.traverse((o) => {
      if (!(o.isLine || o.isPoints || o.isLine2 || o.isLineSegments2 || o.isSprite)) return;
      for (const m of Array.isArray(o.material) ? o.material : [o.material]) if (m && !m.transparent) m.transparent = true;
    });
  }

  render(s) {
    this._sync();
    this._params(s);
    const scene = s.scene;
    if (this.ao.on) this._lineas(scene);
    this.scenePass.scene = scene; this.scenePass.camera = s.camera;
    if (this.ao.on) { if (this.sentinel.parent !== scene) scene.add(this.sentinel); } else this.detach();
    const info = this.renderer.info.render;
    this.extra = 0; this._activo = true;
    try { this.composer.render(); } finally { this._activo = false; }
    // el panel de rendimiento muestra las llamadas de la escena; las del posproceso se informan aparte
    info.calls -= this.extra; info.triangles -= this.extra;
  }

  // la escena deja de usar el posproceso (otra calidad u otra vista)
  detach() { if (this.sentinel.parent) this.sentinel.removeFromParent(); }

  _oclusion(r, camera) {
    if (!this._activo) return;
    const info = r.info.render, c0 = info.calls, rt = this.beauty, g = this.gtao;
    // 1. resuelve el MSAA (color y profundidad) sin dibujar nada: GTAO lee la profundidad de lo opaco
    r.render(this._vacia, camera);
    // 2. oclusión y filtro de ruido (Poisson), a la resolución del render target de GTAO
    const u = g.gtaoMaterial.uniforms;
    u.cameraNear.value = camera.near; u.cameraFar.value = camera.far;
    u.cameraProjectionMatrix.value.copy(camera.projectionMatrix);
    u.cameraProjectionMatrixInverse.value.copy(camera.projectionMatrixInverse);
    u.cameraWorldMatrix.value.copy(camera.matrixWorld);
    g.renderPass(r, g.gtaoMaterial, g.gtaoRenderTarget, 0xffffff, 1);
    g.pdMaterial.uniforms.cameraProjectionMatrixInverse.value.copy(camera.projectionMatrixInverse);
    g.renderPass(r, g.pdMaterial, g.pdRenderTarget, 0xffffff, 1);
    // 3. se multiplica sobre lo opaco ya dibujado (el alfa no cambia: el fondo vacío sigue transparente)
    g.blendMaterial.uniforms.intensity.value = this.ao.intensity;
    g.blendMaterial.uniforms.tDiffuse.value = g.pdRenderTarget.texture;
    g.renderPass(r, g.blendMaterial, rt);
    // la escena sigue con las transparencias sobre el mismo render target (conserva la profundidad de lo opaco)
    r.setRenderTarget(rt);
    this.extra += info.calls - c0 + 1; // +1: el propio centinela (un triángulo vacío, sin color ni profundidad)
  }

  dispose() { this.detach(); this.composer.dispose(); this.gtao.dispose(); this.output.dispose(); this.beauty.dispose(); }
}
