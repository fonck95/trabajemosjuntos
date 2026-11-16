// Ambiente de la maqueta de la propuesta: el cielo, el sol, la luz del cielo, el entorno de los reflejos y la bruma, como
// una sola hora del día y no como colores del tema. Tema claro: tarde despejada (sol a 31°, cálido, sombras largas, cielo
// azul con cúmulos). Tema oscuro: atardecer (sol a 19°, naranja; horizonte encendido del lado del sol; las luminarias, los
// bolardos y las ventanas encendidos).
// · El cielo es un shader en el plano lejano: degradé del horizonte al cenit, halo y disco del sol y nubes de ruido fractal
//   proyectadas sobre un plano (más pequeñas y tenues hacia el horizonte, donde además se funden con la bruma).
// · El entorno de los materiales PBR (reflejos en vidrio, metal, agua y la luz difusa del cielo) se genera de ese mismo
//   cielo con PMREM, sin el disco del sol (la luz directa ya es el sol): lo que se refleja es lo que se ve.
// · La bruma tiene el color del horizonte: el borde del piso se disuelve en el cielo.
import { THREE, engine, tokens, onTheme } from '../core.js';

const VS = `varying vec3 vDir;
void main() {
  vDir = position;
  gl_Position = ( projectionMatrix * vec4( mat3( viewMatrix ) * position, 1.0 ) ).xyww;
}`;
const FS = `uniform vec3 uZen; uniform vec3 uHor; uniform vec3 uHorSol; uniform vec3 uSuelo; uniform vec3 uSol; uniform vec3 uSolCol;
uniform vec3 uNube; uniform vec3 uNubeSombra; uniform float uNubes; uniform float uDisco; uniform float uK;
varying vec3 vDir;
float h21( vec2 p ) { p = fract( p * vec2( 123.34, 456.21 ) ); p += dot( p, p + 45.32 ); return fract( p.x * p.y ); }
float vn( vec2 p ) { vec2 i = floor( p ), f = fract( p ), u = f * f * ( 3.0 - 2.0 * f );
  return mix( mix( h21( i ), h21( i + vec2( 1.0, 0.0 ) ), u.x ), mix( h21( i + vec2( 0.0, 1.0 ) ), h21( i + vec2( 1.0, 1.0 ) ), u.x ), u.y ); }
float fbm( vec2 p ) { float a = 0.5, s = 0.0; for ( int i = 0; i < 5; i ++ ) { s += a * vn( p ); p = p * 2.03 + vec2( 17.1, 9.3 ); a *= 0.5; } return s; }
void main() {
  vec3 d = normalize( vDir );
  float y = d.y, sd = max( dot( d, uSol ), 0.0 );
  vec2 hd = normalize( d.xz + 1e-5 ), hs = normalize( uSol.xz + 1e-5 );
  vec3 hor = mix( uHor, uHorSol, pow( max( dot( hd, hs ), 0.0 ), 3.0 ) * ( 1.0 - smoothstep( 0.0, 0.45, y ) ) );
  vec3 col = y >= 0.0 ? mix( hor, uZen, pow( clamp( y, 0.0, 1.0 ), 0.55 ) ) : mix( hor, uSuelo, clamp( - y * 6.0, 0.0, 1.0 ) );
  col += uSolCol * ( 0.16 * pow( sd, 6.0 ) + 0.45 * pow( sd, 48.0 ) );
  col += uSolCol * uDisco * smoothstep( 0.9993, 0.9997, sd ) * 6.0;
  if ( y > 0.0 && uNubes > 0.0 ) {
    vec2 p = d.xz / ( y + 0.09 ) * 1.25;
    float c = fbm( p + vec2( 5.2, 1.3 ) ) * 0.72 + fbm( p * 2.7 + vec2( 1.7, 9.2 ) ) * 0.28;
    float cob = smoothstep( 0.6 - 0.2 * uNubes, 0.86, c ) * smoothstep( 0.0, 0.14, y );
    float luz = smoothstep( 0.3, 0.85, fbm( p * 1.9 + hs * 0.9 + 3.0 ) );
    vec3 nube = mix( uNubeSombra, uNube, luz ) + uSolCol * 0.22 * pow( sd, 4.0 );
    col = mix( col, nube, cob * 0.93 );
  }
  gl_FragColor = vec4( col * uK, 1.0 );
  #include <colorspace_fragment>
  gl_FragColor.rgb += ( fract( sin( dot( gl_FragCoord.xy, vec2( 12.9898, 78.233 ) ) ) * 43758.5453 ) - 0.5 ) / 255.0;
}`;

// Las dos horas del día. sol: dirección hacia el sol (x al oriente, y arriba, z al sur); los colores, en sRGB
const HORAS = {
  tarde: {
    sol: [430, 300, 250], zen: '#3a74bd', hor: '#d4e2ec', horSol: '#f1e5cf', suelo: '#7d8a70', solCol: '#fff0d4', nube: '#ffffff', nubeSombra: '#b4c0cf', nubes: 0.55,
    niebla: '#cfdbe4', luz: '#ffe8c6', intensidad: 2.7, cielo: '#cfe0ff', piso: '#7a7458', hemi: 0.42, entorno: 0.42, exposicion: 1, encendido: 0,
  },
  atardecer: {
    sol: [430, 175, 250], zen: '#26406e', hor: '#e6a982', horSol: '#ffb067', suelo: '#463e35', solCol: '#ffb57a', nube: '#f7b48e', nubeSombra: '#6a5b74', nubes: 0.6,
    niebla: '#b09489', luz: '#ffbd88', intensidad: 2.5, cielo: '#8d9fd0', piso: '#4a3f33', hemi: 0.58, entorno: 0.5, exposicion: 1.12, encendido: 1,
  },
};
const geoCielo = new THREE.SphereGeometry(1, 48, 24);
function materialCielo() {
  const u = {};
  ['uZen', 'uHor', 'uHorSol', 'uSuelo', 'uSolCol', 'uNube', 'uNubeSombra'].forEach((k) => { u[k] = { value: new THREE.Color() }; });
  Object.assign(u, { uSol: { value: new THREE.Vector3(0, 1, 0) }, uNubes: { value: 0.5 }, uDisco: { value: 1 }, uK: { value: 1 } });
  return new THREE.ShaderMaterial({ uniforms: u, vertexShader: VS, fragmentShader: FS, side: THREE.BackSide, depthWrite: false, fog: false });
}
function ponerHora(m, h) {
  const u = m.uniforms;
  [['uZen', 'zen'], ['uHor', 'hor'], ['uHorSol', 'horSol'], ['uSuelo', 'suelo'], ['uSolCol', 'solCol'], ['uNube', 'nube'], ['uNubeSombra', 'nubeSombra']].forEach(([k, c]) => u[k].value.set(h[c]));
  u.uSol.value.set(...h.sol).normalize(); u.uNubes.value = h.nubes;
}
// entorno PMREM del mismo cielo, sin el disco del sol y atenuado (la luz directa la pone el sol); uno por hora, en caché
const entornos = new Map();
function entorno(nombre) {
  if (entornos.has(nombre)) return entornos.get(nombre);
  const r = engine.renderer, esc = new THREE.Scene(), m = materialCielo(), h = HORAS[nombre];
  ponerHora(m, h); m.uniforms.uDisco.value = 0; m.uniforms.uK.value = h.entorno;
  esc.add(new THREE.Mesh(geoCielo, m));
  const pm = new THREE.PMREMGenerator(r), rt = pm.fromScene(esc, 0, 0.1, 10);
  pm.dispose(); m.dispose();
  entornos.set(nombre, rt.texture);
  return rt.texture;
}
export const horaDelTema = () => { const t = tokens(); return 0.2126 * t.bg.r + 0.7152 * t.bg.g + 0.0722 * t.bg.b < 0.2 ? 'atardecer' : 'tarde'; };

/**
 * Pone el ambiente en el Stage de la propuesta. sol: el Vector3 que la escena suma al objetivo de la cámara para ubicar
 * la luz (se reescribe con la dirección de la hora). alCambiar(h): avisa la hora nueva (para encender ventanas y luces).
 * Devuelve { hora(), aplicar(nombre) }.
 */
export function ambiente(st, { sol, alCambiar } = {}) {
  if (!st.sky) { st.sky = new THREE.Mesh(geoCielo, null); Object.assign(st.sky, { name: 'cielo', frustumCulled: false, renderOrder: 1e9 }); st.scene.add(st.sky); }
  st.sky.geometry = geoCielo;
  st.sky.material?.dispose?.();
  st.sky.material = materialCielo();
  const L = st.sunLight;
  let nombre = null, H = null;
  const niebla = new THREE.Color();
  function aplicar(n = horaDelTema()) {
    nombre = n; H = HORAS[n];
    ponerHora(st.sky.material, H);
    const d = new THREE.Vector3(...H.sol), lejos = sol ? sol.length() || 600 : 600;
    if (sol) sol.copy(d.normalize().multiplyScalar(lejos));
    L.color.set(H.luz); L.intensity = H.intensidad;
    st.hemi.color.set(H.cielo); st.hemi.groundColor.set(H.piso); st.hemi.intensity = H.hemi;
    st.scene.environment = entorno(n);
    niebla.set(H.niebla);
    st.exposure = H.exposicion;
    if (engine.active === st) engine.renderer.toneMappingExposure = H.exposicion;
    st._atmK = null;   // la bruma se vuelve a poner en el próximo cuadro
    alCambiar?.(H, n);
    st.updateShadows();
  }
  // reemplaza el de core.js en esta vista: la bruma con el color del horizonte de la hora, no el del tema
  st._atmosfera = function () {
    const f = this.scene.fog;
    if (f && this.fogCfg) { const far = this.camera.far; f.near = this.fogCfg.near ?? far * 0.6; f.far = this.fogCfg.far ?? far; }
    const post = engine.usePost(), key = `${nombre}|${post}`;
    if (!f || key === this._atmK) return;
    this._atmK = key;
    // three mezcla la bruma con el color ya codificado en sRGB y, al dibujar en un render target (posproceso), le pasa el
    // color en lineal: se le entrega ya codificado para que el horizonte sea el mismo en todas las calidades
    f.color.copy(niebla); if (post) f.color.convertLinearToSRGB();
  };
  onTheme(() => aplicar());
  aplicar();
  return { hora: () => nombre, datos: () => H, aplicar };
}
