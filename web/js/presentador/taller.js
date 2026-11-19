// El taller del presentador (web/presentador.html): el personaje solo, de cerca, para verlo y probarlo. Se gira y se
// acerca con el ratón (OrbitControls), un clic lo hace señalar ese punto, las flechas lo hacen caminar y los botones
// disparan cada gesto, la entrada, la salida y el habla (la boca y el texto, como el subtítulo).
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { crearPersonaje } from './personaje.js';
import { crearAnimador, GESTOS_AGENTE } from './animador.js';
import { decirS } from './presentador.js';

// Los gestos que el asistente puede pedir en cada paso del plan, con su nombre para la persona (y el de cada uno en el
// plan, en el title del botón)
const NOMBRES = { saludar: 'Saludar', senalar: 'Señalar', presentar: 'Presentar', mostrar_panel: 'Mostrar el panel',
  mirar_maqueta: 'Mirar la maqueta', explicar: 'Explicar', destacar: 'Destacar', comparar: 'Comparar', enumerar: 'Enumerar',
  crecer: 'Crecer', grande: 'Grande', detalle: 'Detalle', construir: 'Construir', pensar: 'Pensar', preguntar: 'Preguntar',
  asentir: 'Asentir', negar: 'Negar', calmar: 'Calmar', aprobar: 'Aprobar', celebrar: 'Celebrar', aplaudir: 'Aplaudir',
  juntos: '¡Juntos!', corazon: 'Corazón', invitar: '¿Preguntas?', despedirse: 'Despedirse' };
const LIMITE_X = 2.4;

const caja = document.getElementById('escenario');
const reducido = matchMedia('(prefers-reduced-motion: reduce)').matches;
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, stencil: true });
renderer.setPixelRatio(Math.min(2, devicePixelRatio || 1));
caja.prepend(renderer.domElement);
renderer.domElement.setAttribute('aria-label', 'El presentador en 3D');
renderer.domElement.setAttribute('role', 'img');

const escena = new THREE.Scene();
escena.add(new THREE.HemisphereLight(0xffffff, 0x8a7a70, 1.15));
const luz = new THREE.DirectionalLight(0xffffff, 1.9);
luz.position.set(-2, 3, 4);
escena.add(luz);
// una luz suave de frente: la cara (su relieve, los pliegues de la sonrisa) se lee sin sombras duras
const relleno = new THREE.DirectionalLight(0xfff1e6, 0.7);
relleno.position.set(1.5, 0.6, 4);
escena.add(relleno);
// el piso: un disco con sombra suave al centro
const piso = (() => {
  const c = document.createElement('canvas');
  c.width = c.height = 256;
  const x = c.getContext('2d');
  const g = x.createRadialGradient(128, 128, 10, 128, 128, 128);
  g.addColorStop(0, 'rgba(0,0,0,0.28)');
  g.addColorStop(0.35, 'rgba(0,0,0,0.1)');
  g.addColorStop(1, 'rgba(0,0,0,0)');
  x.fillStyle = g;
  x.fillRect(0, 0, 256, 256);
  const t = new THREE.CanvasTexture(c);
  const m = new THREE.Mesh(new THREE.PlaneGeometry(1.6, 1.6), new THREE.MeshBasicMaterial({ map: t, transparent: true, depthWrite: false }));
  m.rotation.x = -Math.PI / 2;
  m.position.y = 0.002;
  return m;
})();
escena.add(piso);

const camara = new THREE.PerspectiveCamera(30, 1, 0.1, 60);
camara.position.set(0.5, 1.5, 5.4);
const controles = new OrbitControls(camara, renderer.domElement);
controles.target.set(0, 1.2, 0);
controles.enablePan = false;
controles.enableDamping = true;
controles.minDistance = 1.6;
controles.maxDistance = 11;
controles.maxPolarAngle = Math.PI * 0.53;
controles.update();

const personaje = crearPersonaje();
escena.add(personaje.grupo);
const anim = crearAnimador(personaje, { reducido });
anim.camara = camara;
anim.entrar(() => anim.gesto('saludar'));

function medir() {
  const w = caja.clientWidth || 1, h = caja.clientHeight || 1, dpr = renderer.getPixelRatio();
  renderer.setSize(w, h, false);
  camara.aspect = w / h;
  camara.updateProjectionMatrix();
  personaje.contorno.resolucion.value.set(w * dpr, h * dpr);
  personaje.contorno.grosor.value = 1.6 * dpr;
}
new ResizeObserver(medir).observe(caja);
medir();

let antes = 0;
renderer.setAnimationLoop((ahora) => {
  const dt = antes ? (ahora - antes) / 1000 : 1 / 60;
  antes = ahora;
  anim.actualizar(dt);
  piso.position.x = personaje.grupo.position.x;
  controles.target.x += (personaje.grupo.position.x - controles.target.x) * Math.min(1, dt * 3);
  controles.update();
  renderer.render(escena, camara);
});

// ── Los gestos ──
const filaGestos = document.querySelector('[aria-label="Gestos"]');
const alLado = (lado, y = 2.3) => new THREE.Vector3(personaje.grupo.position.x + lado * 3, y, 1.5);
let enumerar = 0;
for (const nombre of GESTOS_AGENTE) {
  const b = document.createElement('button');
  b.type = 'button';
  b.textContent = NOMBRES[nombre] || nombre;
  b.title = `gesto: ${nombre}`;
  b.addEventListener('click', () => {
    clearInterval(enumerar);
    // los que van hacia algo: un lado de la escena (con el clic en la escena se elige el punto)
    if (nombre === 'senalar' || nombre === 'presentar') anim.gesto(nombre, { punto: alLado(Math.random() < 0.5 ? -1 : 1) });
    else if (nombre === 'mostrar_panel') anim.gesto('senalar', { punto: alLado(-1, 1.6) });
    else if (nombre === 'mirar_maqueta') anim.gesto(nombre, { punto: alLado(1, 1.2) });
    else if (nombre === 'enumerar') {
      // uno, dos, tres: como en un paso de tres frases
      let n = 1;
      anim.gesto('enumerar', { n, sostener: true });
      enumerar = setInterval(() => {
        n += 1;
        if (n > 3) { clearInterval(enumerar); anim.detenerGesto(); return; }
        anim.gesto('enumerar', { n, seguir: true });
      }, 1200);
    } else anim.gesto(nombre, { n: 3 });
  });
  filaGestos.append(b);
}

// ── Un clic en la escena: señala ese punto (sobre el plano que mira a la cámara, delante del personaje) ──
const rayo = new THREE.Raycaster();
let abajo = null;
renderer.domElement.addEventListener('pointerdown', (e) => { abajo = [e.clientX, e.clientY]; });
renderer.domElement.addEventListener('pointerup', (e) => {
  if (!abajo || Math.hypot(e.clientX - abajo[0], e.clientY - abajo[1]) > 5) { abajo = null; return; }
  abajo = null;
  const r = renderer.domElement.getBoundingClientRect();
  rayo.setFromCamera(new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), camara);
  const normal = camara.getWorldDirection(new THREE.Vector3()).negate();
  const centro = personaje.grupo.position.clone().add(new THREE.Vector3(0, 1.3, 0)).addScaledVector(normal, 0.6);
  const punto = rayo.ray.intersectPlane(new THREE.Plane().setFromNormalAndCoplanarPoint(normal, centro), new THREE.Vector3());
  if (punto) anim.gesto(e.shiftKey ? 'presentar' : 'senalar', { punto });
});

// ── Caminar ──
const caminar = (dx) => anim.caminarA(Math.max(-LIMITE_X, Math.min(LIMITE_X, anim.estado().x + dx)));
addEventListener('keydown', (e) => {
  if (e.target.closest?.('input')) return;
  if (e.key === 'ArrowLeft') { caminar(-0.6); e.preventDefault(); }
  if (e.key === 'ArrowRight') { caminar(0.6); e.preventDefault(); }
});
document.getElementById('izquierda').addEventListener('click', () => caminar(-0.9));
document.getElementById('derecha').addEventListener('click', () => caminar(0.9));
document.getElementById('centro').addEventListener('click', () => anim.caminarA(0));
document.getElementById('entrar').addEventListener('click', () => anim.entrar(() => anim.gesto('saludar')));
document.getElementById('salir').addEventListener('click', () => anim.gesto('despedirse', { alTerminar: () => anim.salir() }));

// ── Hablar ──
const boca = document.getElementById('mover-boca');
boca.addEventListener('click', () => {
  const v = boca.getAttribute('aria-pressed') !== 'true';
  boca.setAttribute('aria-pressed', String(v));
  if (v) anim.hablar(true); else anim.callar();
});
// «Decir»: mueve la boca por las sílabas del texto lo que tardaría en decirlo (con los golpes en sus palabras clave) y
// lo muestra abajo, como el subtítulo de la presentación (la voz de verdad es la del panel, en el recorrido narrado)
const leyenda = document.getElementById('dice');
let tLeyenda = 0;
document.getElementById('decir').addEventListener('click', () => {
  const texto = document.getElementById('texto').value.trim();
  if (!texto) return;
  const s = decirS(texto);
  anim.hablar(s, { texto });
  leyenda.textContent = texto;
  leyenda.hidden = false;
  clearTimeout(tLeyenda);
  tLeyenda = setTimeout(() => { leyenda.hidden = true; }, s * 1000 + 800);
});
