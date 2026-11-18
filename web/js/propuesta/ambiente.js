// Ambiente de la maqueta de la propuesta: el cielo, el sol, la luz del cielo, el entorno de los reflejos y la bruma, como
// una hora del día y no como colores del tema. Cuatro horas: mañana (sol bajo al oriente, luz fresca), tarde (sol a 31°,
// cálido, sombras largas, cielo azul con cúmulos), atardecer (sol a 19°, naranja; horizonte encendido del lado del sol) y
// noche (luna, estrellas, ventanas, luminarias y bolardos encendidos). Sin más, la hora sigue al tema: tarde en el claro y
// atardecer en el oscuro. La simulación de la maqueta (simulacion.js) la puede fijar o recorrer el día entero (ciclo).
// · El cielo es un shader en el plano lejano: degradé del horizonte al cenit, halo y disco del sol (de noche, la luna),
//   nubes de ruido fractal proyectadas sobre un plano (más pequeñas y tenues hacia el horizonte, donde además se funden con
//   la bruma) y, de noche, estrellas.
// · El entorno de los materiales PBR (reflejos en vidrio, metal, agua y la luz difusa del cielo) se genera de ese mismo
//   cielo con PMREM, sin el disco del sol (la luz directa ya es el sol): lo que se refleja es lo que se ve. Uno por hora.
// · La bruma tiene el color del horizonte: el borde del piso se disuelve en el cielo.
import { THREE, engine, tokens, onTheme } from '../core.js';

const VS = `varying vec3 vDir;
void main() {
  vDir = position;
  gl_Position = ( projectionMatrix * vec4( mat3( viewMatrix ) * position, 1.0 ) ).xyww;
}`;
const FS = `uniform vec3 uZen; uniform vec3 uHor; uniform vec3 uHorSol; uniform vec3 uSuelo; uniform vec3 uSol; uniform vec3 uSolCol;
uniform vec3 uNube; uniform vec3 uNubeSombra; uniform float uNubes; uniform float uDisco; uniform float uK; uniform float uEstrellas;
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
  if ( uEstrellas > 0.0 && y > 0.02 ) {
    // estrellas: una celda de ~0,4° por estrella posible, con brillo y tamaño al azar; se apagan hacia el horizonte
    vec2 sc = vec2( atan( d.z, d.x ), asin( y ) ) * 140.0, ce = floor( sc ), fr = fract( sc ) - 0.5;
    float h = h21( ce ), on = step( 0.985, h ), b = h21( ce + 7.1 );
    col += vec3( 0.85, 0.9, 1.0 ) * on * smoothstep( 0.32, 0.0, length( fr ) ) * ( 0.4 + 1.6 * b * b ) * uEstrellas * smoothstep( 0.02, 0.25, y );
  }
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

// Las cuatro horas del día, en el orden del ciclo. sol: dirección hacia el sol (x al oriente, y arriba, z al sur; de noche,
// la luna); los colores, en sRGB. encendido: ventanas y luminarias (0 apagadas, 1 encendidas); oscuridad: cuánto se notan
// los charcos de luz de las luminarias en el piso (0 de día, 1 de noche)
export const ORDEN_HORAS = ['manana', 'tarde', 'atardecer', 'noche'];
const HORAS = {
  manana: {
    sol: [480, 215, 70], zen: '#4683c9', hor: '#dce8ef', horSol: '#ffe9cc', suelo: '#7f8b72', solCol: '#fff3df', nube: '#ffffff', nubeSombra: '#bcc8d6', nubes: 0.45,
    niebla: '#d8e3ea', luz: '#fff1de', intensidad: 2.4, cielo: '#d6e4ff', piso: '#78765c', hemi: 0.46, entorno: 0.44, exposicion: 1, encendido: 0, oscuridad: 0, estrellas: 0, disco: 1,
  },
  tarde: {
    sol: [430, 300, 250], zen: '#3a74bd', hor: '#d4e2ec', horSol: '#f1e5cf', suelo: '#7d8a70', solCol: '#fff0d4', nube: '#ffffff', nubeSombra: '#b4c0cf', nubes: 0.55,
    niebla: '#cfdbe4', luz: '#ffe8c6', intensidad: 2.7, cielo: '#cfe0ff', piso: '#7a7458', hemi: 0.42, entorno: 0.42, exposicion: 1, encendido: 0, oscuridad: 0, estrellas: 0, disco: 1,
  },
  atardecer: {
    sol: [430, 175, 250], zen: '#26406e', hor: '#e6a982', horSol: '#ffb067', suelo: '#463e35', solCol: '#ffb57a', nube: '#f7b48e', nubeSombra: '#6a5b74', nubes: 0.6,
    niebla: '#b09489', luz: '#ffbd88', intensidad: 2.5, cielo: '#8d9fd0', piso: '#4a3f33', hemi: 0.58, entorno: 0.5, exposicion: 1.12, encendido: 1, oscuridad: 0.5, estrellas: 0, disco: 1,
  },
  noche: {
    sol: [-260, 420, -180], zen: '#060c1f', hor: '#1c2946', horSol: '#26355a', suelo: '#0c0e13', solCol: '#c9d6ff', nube: '#36425f', nubeSombra: '#121827', nubes: 0.3,
    niebla: '#172036', luz: '#a9bce6', intensidad: 0.62, cielo: '#5a6ea8', piso: '#26262c', hemi: 0.55, entorno: 0.2, exposicion: 1.3, encendido: 1, oscuridad: 1, estrellas: 1, disco: 0.45,
  },
};
export const HORAS_NOMBRES = { manana: 'mañana', tarde: 'tarde', atardecer: 'atardecer', noche: 'noche' };
const COLORES = ['zen', 'hor', 'horSol', 'suelo', 'solCol', 'nube', 'nubeSombra', 'niebla', 'luz', 'cielo', 'piso'];
const NUMEROS = ['nubes', 'intensidad', 'hemi', 'entorno', 'exposicion', 'encendido', 'oscuridad', 'estrellas', 'disco'];
// una hora intermedia entre a y b (k de 0 a 1): colores en lineal, números y la dirección del sol interpolados
function mezcla(a, b, k) {
  const out = { sol: new THREE.Vector3(...a.sol).normalize().lerp(new THREE.Vector3(...b.sol).normalize(), k).normalize().toArray() };
  COLORES.forEach((c) => { out[c] = new THREE.Color(a[c]).lerp(new THREE.Color(b[c]), k); });
  NUMEROS.forEach((n) => { out[n] = a[n] + (b[n] - a[n]) * k; });
  return out;
}
const geoCielo = new THREE.SphereGeometry(1, 48, 24);
function materialCielo() {
  const u = {};
  ['uZen', 'uHor', 'uHorSol', 'uSuelo', 'uSolCol', 'uNube', 'uNubeSombra'].forEach((k) => { u[k] = { value: new THREE.Color() }; });
  Object.assign(u, { uSol: { value: new THREE.Vector3(0, 1, 0) }, uNubes: { value: 0.5 }, uDisco: { value: 1 }, uK: { value: 1 }, uEstrellas: { value: 0 } });
  return new THREE.ShaderMaterial({ uniforms: u, vertexShader: VS, fragmentShader: FS, side: THREE.BackSide, depthWrite: false, fog: false });
}
function ponerHora(m, h) {
  const u = m.uniforms;
  [['uZen', 'zen'], ['uHor', 'hor'], ['uHorSol', 'horSol'], ['uSuelo', 'suelo'], ['uSolCol', 'solCol'], ['uNube', 'nube'], ['uNubeSombra', 'nubeSombra']].forEach(([k, c]) => u[k].value.set(h[c]));
  u.uSol.value.set(...h.sol).normalize(); u.uNubes.value = h.nubes; u.uEstrellas.value = h.estrellas; u.uDisco.value = h.disco;
}
// entorno PMREM del mismo cielo, sin el disco del sol ni las estrellas y atenuado (la luz directa la pone el sol); uno por
// hora, en caché
const entornos = new Map();
function entorno(nombre) {
  if (entornos.has(nombre)) return entornos.get(nombre);
  const r = engine.renderer, esc = new THREE.Scene(), m = materialCielo(), h = HORAS[nombre];
  ponerHora(m, h); m.uniforms.uDisco.value = 0; m.uniforms.uEstrellas.value = 0; m.uniforms.uK.value = h.entorno;
  esc.add(new THREE.Mesh(geoCielo, m));
  const pm = new THREE.PMREMGenerator(r), rt = pm.fromScene(esc, 0, 0.1, 10);
  pm.dispose(); m.dispose();
  entornos.set(nombre, rt.texture);
  return rt.texture;
}
export const horaDelTema = () => { const t = tokens(); return 0.2126 * t.bg.r + 0.7152 * t.bg.g + 0.0722 * t.bg.b < 0.2 ? 'atardecer' : 'tarde'; };

// Durante el ciclo, el mapa de sombras (4096²) se vuelve a calcular cada SOMBRAS_CICLO_S, no en cada cuadro: el sol se
// mueve despacio y, sin GPU o en un proyector modesto, recalcularlo cuadro a cuadro tira los cuadros por segundo
const SOMBRAS_CICLO_S = 0.25;

/**
 * Pone el ambiente en el Stage de la propuesta. sol: el Vector3 que la escena suma al objetivo de la cámara para ubicar
 * la luz (se reescribe con la dirección de la hora). alCambiar(H, nombre, sombras): avisa la hora nueva (para encender
 * ventanas y luces; durante el ciclo, en cada cuadro, con la hora intermedia y el nombre de la más cercana; `sombras`
 * dice si en ese cuadro se recalculan las sombras).
 * Devuelve { hora(), datos(), horas (ORDEN_HORAS), aplicar(nombre), poner(nombre|null), ciclo(opciones), reanudar(),
 * pausar(), enCiclo(), fijada() }.
 */
export function ambiente(st, { sol, alCambiar } = {}) {
  if (!st.sky) { st.sky = new THREE.Mesh(geoCielo, null); Object.assign(st.sky, { name: 'cielo', frustumCulled: false, renderOrder: 1e9 }); st.scene.add(st.sky); }
  st.sky.geometry = geoCielo;
  st.sky.material?.dispose?.();
  st.sky.material = materialCielo();
  const L = st.sunLight;
  let nombre = null, H = null, fija = null, ciclo = null, pausado = null, version = 0;
  const niebla = new THREE.Color();
  // El velo de los bordes de la maqueta (.escena::after en propuesta.html: hace legibles el panel y las barras) es del
  // color del tema. Con una hora más oscura que la del tema (la noche con el tema claro) se tiñe del horizonte de la hora
  // en esa medida (--velo-hora y --velo-k en el lienzo; propuesta.html los mezcla en --velo): los bordes no quedan blancos
  // alrededor de una maqueta de noche. Se toca el estilo solo cuando la medida cambia de a 5 % (no en cada cuadro del ciclo)
  let oscTema = null, veloK = -1;
  function velo(h) {
    const el = st.el;
    if (!el?.style) return;
    if (oscTema == null) oscTema = HORAS[horaDelTema()].oscuridad;
    const k = Math.round(Math.min(1, Math.max(0, (h.oscuridad - oscTema) / Math.max(0.05, 1 - oscTema))) * 20) * 5;
    if (k === veloK) return;
    veloK = k;
    if (!k) { el.style.removeProperty('--velo-hora'); el.style.removeProperty('--velo-k'); return; }
    el.style.setProperty('--velo-hora', `#${new THREE.Color(h.niebla).getHexString()}`);
    el.style.setProperty('--velo-k', `${k}%`);
  }
  function aplicarH(h, n, sombras = true) {
    nombre = n; H = h; version++;
    ponerHora(st.sky.material, h);
    const d = new THREE.Vector3(...h.sol), lejos = sol ? sol.length() || 600 : 600;
    if (sol) sol.copy(d.normalize().multiplyScalar(lejos));
    L.color.set(h.luz); L.intensity = h.intensidad;
    st.hemi.color.set(h.cielo); st.hemi.groundColor.set(h.piso); st.hemi.intensity = h.hemi;
    st.scene.environment = entorno(n);
    niebla.set(h.niebla);
    st.exposure = h.exposicion;
    if (engine.active === st) engine.renderer.toneMappingExposure = h.exposicion;
    st._atmK = null;   // la bruma se vuelve a poner en el próximo cuadro
    velo(h);
    alCambiar?.(h, n, sombras);
    if (sombras) st.updateShadows();
  }
  /** Una hora fija (sin ciclo): la pedida, la fijada o la del tema. */
  function aplicar(n = fija || horaDelTema()) { aplicarH(HORAS[n] || HORAS.tarde, HORAS[n] ? n : 'tarde'); }
  /** Fija la hora (null: vuelve a la del tema) y corta el ciclo. */
  function poner(n) {
    if (n != null && !HORAS[n]) return false;
    pausar(); fija = n; aplicar();
    return true;
  }
  // El día entero (o un tramo) en `duracion` segundos: de la hora `desde` (por omisión, la que se ve) hasta `hasta`, con el
  // sol, el cielo, la luz y las luces interpolados cuadro a cuadro. Al terminar queda fijada la última hora. Devuelve una
  // promesa que se cumple al terminar (true) o al cortarse (false). `t` (de 0 a 1): por dónde empieza (reanudar). Avanza
  // con el reloj, no con los cuadros (el dt de cada cuadro tiene un tope de 0,05 s): en un proyector que dibuja pocos
  // cuadros por segundo el día dura lo mismo, a saltos más largos
  function hacerCiclo({ desde = nombre, hasta = 'noche', duracion = 24, t = 0 } = {}) {
    pausar();
    let i0 = ORDEN_HORAS.indexOf(desde), i1 = ORDEN_HORAS.indexOf(hasta);
    if (i0 < 0) i0 = 0;
    if (i1 < 0) i1 = ORDEN_HORAS.length - 1;
    if (i1 <= i0) i0 = 0;   // ya es de noche (o más tarde que «hasta»): vuelve a empezar desde la mañana
    const tramos = i1 - i0, dur = Math.max(2, duracion);
    let fin;
    const promesa = new Promise((ok) => { fin = ok; });
    const t0 = Math.min(0.999, Math.max(0, +t || 0)), inicio = performance.now();
    const c = { t: t0, vivo: true, fin, sombra: -Infinity, opciones: { desde: ORDEN_HORAS[i0], hasta: ORDEN_HORAS[i1], duracion: dur } };
    ciclo = c;
    const paso = () => {
      // terminado o cortado, se quita de la lista de cada cuadro (después del cuadro: no se toca la lista mientras se recorre)
      if (!c.vivo) { setTimeout(() => { const j = st.frameFns.indexOf(paso); if (j >= 0) st.frameFns.splice(j, 1); }, 0); return false; }
      const ahora = performance.now();
      c.t = Math.min(1, t0 + (ahora - inicio) / 1000 / dur);
      const k = i0 + c.t * tramos, i = Math.min(Math.floor(k), i1 - 1), f = k - i;
      const n = ORDEN_HORAS[f < 0.5 ? i : i + 1];
      const sombras = ahora - c.sombra >= SOMBRAS_CICLO_S * 1000;
      if (sombras) c.sombra = ahora;
      aplicarH(mezcla(HORAS[ORDEN_HORAS[i]], HORAS[ORDEN_HORAS[i + 1]], Math.min(1, f)), n, sombras);
      if (c.t >= 1) { c.vivo = false; if (ciclo === c) ciclo = null; fija = ORDEN_HORAS[i1]; aplicar(); fin(true); }
      return true;
    };
    st.onFrame(paso);
    return promesa;
  }
  // corta el ciclo donde va (queda la hora intermedia a la vista) y anota por dónde iba, para reanudarlo
  function pausar() {
    if (!ciclo) return;
    const c = ciclo;
    c.vivo = false; ciclo = null;
    pausado = { ...c.opciones, t: c.t, H };
    st.updateShadows();
    c.fin(false);
  }
  /** Sigue el ciclo pausado desde donde quedó, si nada cambió la hora desde entonces; si no, null. */
  function reanudar() {
    const p = pausado;
    pausado = null;
    if (!p || p.H !== H || ciclo) return null;
    const { H: _h, ...opciones } = p;
    return hacerCiclo(opciones);
  }
  // reemplaza el de core.js en esta vista: la bruma con el color del horizonte de la hora, no el del tema
  st._atmosfera = function () {
    const f = this.scene.fog;
    if (f && this.fogCfg) { const far = this.camera.far; f.near = this.fogCfg.near ?? far * 0.6; f.far = this.fogCfg.far ?? far; }
    const post = engine.usePost(), key = `${version}|${post}`;
    if (!f || key === this._atmK) return;
    this._atmK = key;
    // three mezcla la bruma con el color ya codificado en sRGB y, al dibujar en un render target (posproceso), le pasa el
    // color en lineal: se le entrega ya codificado para que el horizonte sea el mismo en todas las calidades
    f.color.copy(niebla); if (post) f.color.convertLinearToSRGB();
  };
  // el botón del tema es de la persona: deja de lado la hora fijada y el ciclo, y vuelve a la del tema (las luces y el
  // partido que pidió el agente siguen como estaban: simulacion.js). El velo vuelve a medir la hora del tema
  onTheme(() => { pausar(); fija = null; oscTema = null; veloK = -1; aplicar(); });
  aplicar();
  return { hora: () => nombre, datos: () => H, horas: ORDEN_HORAS, aplicar, poner, ciclo: hacerCiclo, reanudar, pausar,
    enCiclo: () => !!ciclo, fijada: () => fija };
}
