// El presentador en la presentación (web/propuesta.html dentro del panel): el personaje de personaje.js, movido por
// animador.js, detrás del subtítulo como detrás de un atril, que explica lo que el asistente narra (docs/presentador.md).
//
// * Un <canvas> propio, transparente, dentro de #pres justo antes del panel: con el mismo z-index (8), el panel y la
//   ficha (después en el árbol) quedan encima de él; la leyenda, el HUD (7) y el atlas (6), debajo; el subtítulo (9),
//   encima. Sin eventos de puntero: no tapa nada que se toque. Su propio WebGLRenderer, chico, que solo dibuja mientras
//   el presentador está a la vista: la maqueta sigue dibujando bajo demanda, como siempre.
// * El encuadre es por PLANOS (vistas.js: entero, americano, medio): una ventana vertical del personaje y la altura a
//   la que lo corta el borde de arriba del subtítulo («el atril»). La cámara se calcula en cada cuadro con la escala (px
//   por unidad), el ancla del mundo (el corte) y dónde cae ese ancla en el lienzo; el tamaño del lienzo (`setSize`) solo
//   cambia con la vista o la ventana. Lo que queda debajo del corte no se ve nunca (clip-path: el subtítulo es vidrio).
// * La VISTA sale de lo que se explica (vistas.js `elegirVista`, con lo que trae `narrar`): señala lo resaltado del
//   panel, de la ficha o de la leyenda; presenta la obra de la maqueta; de anfitrión, de frente a la sala; entero con
//   «Solo 3D»; de cerca en el cierre; un busto en la pantalla chica. El LUGAR, a lo largo del subtítulo, el que menos tapa
//   (la obra, sus rótulos, lo resaltado) sin tapar nunca el panel, la ficha ni el atlas, a un brazo de lo que señala; se
//   queda donde está si sigue sirviendo y cambia a lo sumo una vez por escena. El cuerpo gira hacia lo que explica; la
//   cara, nunca más de la apertura (en 3/4, nunca de perfil).
// * Las TRANSICIONES (vistas.js `transicion`): gira en el lugar; cerca, camina detrás del subtítulo (en 3/4, el lienzo
//   y la cámara lo siguen); más lejos, o a otro plano y otro lugar, se agacha detrás del subtítulo, el lienzo salta y se
//   asoma ya orientado; al mismo lugar en otro plano, la cámara se acerca. Ningún gesto de brazos arranca mientras camina
//   o salta. Con el atlas a la vista (o la ficha en el celular, o el celular de lado) es un RÓTULO: la cara en un círculo
//   bajo el panel o acoplado al subtítulo (que le hace lugar: .pres.rotulo-acoplado), que aparece creciendo cuando él se
//   agachó y se encoge para que él vuelva a asomarse.
// * El tiempo de la escena: el gesto de entrada arranca con la primera frase (o a los 0.8 s), cuando ya está en su
//   lugar y, si señala, cuando lo resaltado apareció y dejó de moverse; se sostiene la primera frase y después queda la
//   mano baja hacia lo que explica (`indicar`) hasta la escena siguiente, mirando a la sala al empezar cada frase. En la
//   primera escena saluda antes (corto si ya hay un dato que señalar). El resumen del cierre lo cuenta con los dedos, un
//   dedo al empezar cada punto.
// * La LUZ sigue a la de la maqueta (el aviso `ambiente`: la hora y el lado del sol), en 0.6 s: de tarde desde el lado
//   del sol, al atardecer (el tema oscuro) más tibia, de noche más baja y con un contraluz frío; el rótulo, con la de
//   siempre. Lo que no recibe luz (los ojos, los dientes, las cejas) se tiñe en proporción. Lo pegado al corte se
//   oscurece un poco (la sombra del atril) y propuesta.html le pone un filo crema alrededor (el contorno de calcomanía).
//   El detalle de la cara (las cejas, los ojos) va según lo que mide la cabeza en la pantalla (personaje.js `nivel`).
// * Nunca queda a la vista sin el subtítulo: si el subtítulo se va (se quita la explicación, la hoja grande del celular
//   lo tapa) se agacha en el acto detrás de la línea donde estaba (después del cierre, despidiéndose) y, si vuelve, se
//   asoma de nuevo.
// * `mostrar(false)` (el botón «Presentador» del panel, `vista {presentador: false}`) lo oculta en el acto y lo deja
//   quieto hasta `mostrar(true)`.
// * prefers-reduced-motion: entra y sale sin animación, sin caminar, agacharse, acercarse ni saltar: cada cambio de
//   lugar o de plano se funde (la opacidad no es movimiento) y el cuerpo gira en el acto; el rótulo aparece sin escala.
// * Si el navegador no puede crear el contexto WebGL (o lo pierde), no hay presentador y nada más cambia.
// * Con ?qa en la dirección de la página: `window.__qaPresentador` (estado, cajas proyectadas, msCuadro) para medirlo.
import * as THREE from 'three';
import { crearPersonaje } from './personaje.js';
import { crearAnimador } from './animador.js';
import {
  PLANOS, CHICA_PX, HORIZONTAL_PX, elegirVista, medidas, rumboDe, cxDe, caja, union, objetivoDe, elegirLugar,
  transicion, tiemposCierre, apuntable, rotuloDe, posRotulo, yHombro as alturaHombro,
} from './vistas.js';

const FOV = 17;           // poca perspectiva: casi un dibujo plano
const TAN = Math.tan((FOV * Math.PI) / 360);
const DECIR_S = 0.058;     // lo que tarda en decirse un carácter sin voz (a unos 17 por segundo)
// lo más que tarda en agacharse y desaparecer: la animación dura 0.45 s (0.6 s con la despedida), pero con muy pocos
// cuadros por segundo (cada cuadro avanza a lo sumo 0.25 s) tardaría más, y nunca debe quedar a la vista sin el subtítulo
const FUERA_MS = 750;
const VIGILAR_MS = 80;     // agachado esperando que vuelva el subtítulo: cada cuánto lo mira (sin dibujar)
// Las transiciones
const FUNDIDO_MS = 150;    // con movimiento reducido: se funde, cambia y vuelve (propuesta.html: .presentador.fundido)
const CAMINAR_PX_S = 230;  // camina detrás del subtítulo a 230 px/s (si es más lejos, más rápido: nunca más de 1.1 s)
const CAMINAR_MAX_S = 1.1;
const ACERCAR_MS = 700;    // la cámara se acerca (o se aleja) a otro plano
const CRECE_S = 0.25, ENCOGE_S = 0.2;   // el círculo del rótulo aparece (de 0.6 a 1, con la opacidad) y se encoge
const TRANS_MAX_MS = 3000; // (una transición que no termina, sin cuadros, se da por hecha)
const ESPERA_TRANS_MS = 1200;   // el gesto de entrada espera a que termine la transición (como mucho 1.2 s)
const ASENTAR_SUB_S = 0.15;     // el subtítulo cambia de alto: el corte lo sigue en el acto y el cuerpo, en un momento
// El tiempo dentro de una escena
const LUGAR_MS = 150;      // el cambio de lugar arranca 150 ms después de narrar (o al llegar el encuadre de la obra)
const FRASE0_MS = 800;     // el gesto de entrada espera la primera frase; si no llega en 0.8 s, arranca igual
// lo resaltado: si a los 1.2 s de la escena no está (o a los 1.3 s de aplicar lo visual: el mando lo busca hasta 1 s
// después), sigue sin él; si está pero se mueve (el panel se desplaza hasta él), lo espera hasta 2 s más
const FOCO_MS = 1200, FOCO_APLICAR_MS = 1300, FOCO_QUIETO_MS = 2000;
const SOSTEN_MS = 2500;    // el primer gesto se sostiene la primera frase, al menos 2.5 s; después, la mano hacia el objetivo
const PULSO_MS = 900;      // el anillo de lo señalado late cuando llega el dedo (propuesta.html: .foco.senalado)
const MIRAR_MS = 1000;     // cada frase empieza mirando a la sala; después, un vistazo a lo que explica
const VISTAZO_MS = 800;
const SALUDO_S = 2.6, SALUDO_CORTO_S = 1.2;
const CAPITULO_MS = 600;   // el cambio de capítulo: mira el panel (que cambió de color y de contenido) antes del gesto
// los gestos que apuntan a algo (con `punto`): el brazo sigue al punto en cada cuadro
const APUNTAN = ['senalar', 'presentar', 'indicar'];
const acotar = (v, a, b) => Math.min(b, Math.max(a, v));
const mezclar = (a, b, u) => a + (b - a) * u;
const suave = (u) => { const t = acotar(u, 0, 1); return t * t * (3 - 2 * t); };

/** La duración de decir `texto` sin voz, en segundos. */
export const decirS = (texto) => Math.min(16, Math.max(1.2, [...String(texto || '')].length * DECIR_S));

// ── La luz: la de la maqueta ──
const LUZ_MS = 600;          // la luz nueva llega en 0.6 s (el «reproducir el día» la mueve con cada frase: no salta)
const TIBIO = 0xffd9b0, FRIO = 0x8fb0ff;
const HEX = /^#[0-9a-f]{6}$/i;
/**
 * Las luces del presentador para la luz de la maqueta `l` (visual.js `luz()`: {hora, luz, intensidad, cielo, piso,
 * hemi, oscuridad, sol, solFin}); sin aviso (el taller, una capa vieja), las de siempre. → {luz, luzI, lado, cielo,
 * suelo, hemiI, relleno, rellenoI, contraI} (colores THREE.Color; `lado` de −1, la luz desde la izquierda de la pantalla,
 * a 1, desde la derecha). Pura: se prueba con Node.
 * - El lado, el del sol donde termina el viaje de la cámara (`solFin`; si no, `sol`): x > 0 es el sol a la derecha de la
 *   pantalla, y la luz principal viene de ahí (las sombras de la maqueta y las de su cara caen hacia el mismo lado). El
 *   relleno, del otro lado.
 * - El color de la principal, mitad blanco y mitad el del sol (no ensucia el rojo de la polo); el cielo y el suelo de
 *   la hemisférica, un poco del cielo y la mitad del piso de la maqueta. Su intensidad sigue a la del sol, con un piso
 *   (de noche no queda a oscuras).
 * - `oscuridad` (0 de día, 0.5 al atardecer, 1 de noche, continua en el ciclo del día) mezcla sin saltos: el relleno se
 *   entibia hacia el atardecer; de noche la principal y la hemisférica bajan a 0.6, el relleno a 0.5 y entra un
 *   contraluz frío desde atrás (separa el pelo y los hombros del fondo oscuro, sin lavar la cara)
 */
export function lucesDe(l) {
  const c = (v) => new THREE.Color(v);
  const hoy = { luz: c(0xffffff), luzI: 1.9, lado: -1, cielo: c(0xffffff), suelo: c(0x8a7a70), hemiI: 1.15,
    relleno: c(0xfff1e6), rellenoI: 0.7, contraI: 0 };
  if (!l || typeof l !== 'object') return hoy;
  const num = (v, d) => (Number.isFinite(v) ? v : d);
  const de = (v, d) => (typeof v === 'string' && HEX.test(v) ? c(v) : d.clone());
  const k = acotar(num(l.intensidad, 2.7) / 2.7, 0.55, 1);
  const osc = acotar(num(l.oscuridad, { noche: 1, atardecer: 0.5 }[l.hora] ?? 0), 0, 1);
  const noche = acotar((osc - 0.5) / 0.5, 0, 1), tibio = acotar(osc / 0.5, 0, 1);
  const sol = Array.isArray(l.solFin) ? l.solFin : Array.isArray(l.sol) ? l.sol : null;
  const sx = num(sol?.[0], NaN);
  // (el sol casi de frente o de espaldas: la luz casi de arriba; sin saltos cuando el ciclo lo cruza)
  const lado = Number.isFinite(sx) ? acotar(sx / 0.25, -1, 1) : -1;
  const baja = 1 - 0.4 * noche;
  return {
    luz: c(0xffffff).lerp(de(l.luz, hoy.luz), 0.5), luzI: 1.9 * k * baja, lado,
    cielo: c(0xffffff).lerp(de(l.cielo, hoy.cielo), 0.35), suelo: c(0x8a7a70).lerp(de(l.piso, hoy.suelo), 0.5),
    hemiI: 1.15 * k * baja,
    relleno: hoy.relleno.lerp(c(TIBIO), tibio), rellenoI: 0.7 - 0.2 * noche, contraI: 0.8 * noche,
  };
}
/** Entre dos juegos de luces (u de 0 a 1), en `out` */
function mezclarLuces(a, b, u, out) {
  for (const k of ['luz', 'cielo', 'suelo', 'relleno']) out[k].copy(a[k]).lerp(b[k], u);
  for (const k of ['luzI', 'lado', 'hemiI', 'rellenoI', 'contraI']) out[k] = mezclar(a[k], b[k], u);
  return out;
}
const copiaLuces = (e) => mezclarLuces(e, e, 0, lucesDe(null));
const mismasLuces = (a, b) => ['luz', 'cielo', 'suelo', 'relleno'].every((k) => a[k].equals(b[k]))
  && ['luzI', 'lado', 'hemiI', 'rellenoI', 'contraI'].every((k) => Math.abs(a[k] - b[k]) < 1e-4);
/** Lo que recibe una superficie de frente a la cámara con las luces `e` (para teñir lo que no recibe luz: los ojos, los
 * dientes, las cejas). La rampa de tonos de los materiales va de la mitad a 1 según cuánto mira a cada luz */
function irradiancia(e, out = new THREE.Color()) {
  const mira = (x, y, z) => Math.max(0.35, 0.5 + 0.5 * z / Math.hypot(x, y, z));
  const frio = new THREE.Color(FRIO);
  out.setRGB(0, 0, 0);
  const suma = (col, f) => { out.r += col.r * f; out.g += col.g * f; out.b += col.b * f; };
  suma(e.luz, e.luzI * mira(2 * e.lado, 3, 4));
  suma(e.relleno, e.rellenoI * mira(-1.5 * e.lado, 0.6, 4));
  suma(frio, e.contraI * mira(-3 * e.lado, 2.5, -3));
  suma(e.cielo.clone().add(e.suelo).multiplyScalar(0.5), e.hemiI);
  return out;
}

export function crearPresentador({ ventana = globalThis.window, documento = globalThis.document } = {}) {
  if (!ventana || !documento?.createElement) return null;
  const reducido = !!ventana.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches;
  const reloj = ventana.performance || globalThis.performance || Date;
  const ahora = () => reloj.now();
  const lienzo = documento.createElement('canvas');
  lienzo.className = 'presentador';
  lienzo.setAttribute('aria-hidden', 'true');
  lienzo.hidden = true;
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas: lienzo, alpha: true, antialias: true, stencil: true,
      powerPreference: 'low-power', premultipliedAlpha: true });
  } catch { return null; }
  // dentro de #pres, antes del panel: el panel y la ficha quedan encima (mismo z-index, después en el árbol)
  const antesDe = documento.querySelector?.('#pres > .panel');
  if (antesDe?.parentNode) antesDe.parentNode.insertBefore(lienzo, antesDe);
  else documento.body.append(lienzo);
  renderer.setClearColor(0x000000, 0);
  const escena = new THREE.Scene();
  // Las luces: las de siempre (la principal desde arriba a la izquierda, el cielo y el suelo, y un relleno suave de
  // frente, para que la cara —su relieve, los pliegues de la sonrisa— se lea sin sombras duras) hasta que la maqueta
  // avisa su luz (`ambiente`): entonces la siguen (lucesDe). El contraluz frío, solo de noche
  const hemi = new THREE.HemisphereLight(0xffffff, 0x8a7a70, 1.15);
  const luz = new THREE.DirectionalLight(0xffffff, 1.9);
  const relleno = new THREE.DirectionalLight(0xfff1e6, 0.7);
  const contraluz = new THREE.DirectionalLight(FRIO, 0);
  escena.add(hemi, luz, relleno, contraluz);
  // la cámara mira siempre de frente (−z, sin girar): solo se mueve, cuadro a cuadro (ver `colocar`)
  const camara = new THREE.PerspectiveCamera(FOV, 1, 0.1, 50);
  const personaje = crearPersonaje({ documento });
  const A = personaje.medidas.alto;
  escena.add(personaje.grupo);
  const anim = crearAnimador(personaje, { reducido });
  anim.camara = camara;
  personaje.grupo.visible = false;
  // la luz de ahora, adónde va y desde dónde (interpolada en LUZ_MS); lo que no recibe luz se tiñe en proporción
  const luces = lucesDe(null), irrHoy = irradiancia(luces), irr = new THREE.Color();
  let lucesHacia = copiaLuces(luces), lucesDesde = null, tLuces = 0;
  function ponerLuces(e) {
    luz.color.copy(e.luz); luz.intensity = e.luzI; luz.position.set(2 * e.lado, 3, 4);
    hemi.color.copy(e.cielo); hemi.groundColor.copy(e.suelo); hemi.intensity = e.hemiI;
    relleno.color.copy(e.relleno); relleno.intensity = e.rellenoI; relleno.position.set(-1.5 * e.lado, 0.6, 4);
    contraluz.intensity = e.contraI; contraluz.position.set(-3 * e.lado, 2.5, -3);
    if (personaje.tinte) {
      irradiancia(e, irr);
      personaje.tinte.value.setRGB(acotar(irr.r / irrHoy.r, 0, 1.1), acotar(irr.g / irrHoy.g, 0, 1.1), acotar(irr.b / irrHoy.b, 0, 1.1));
    }
  }
  ponerLuces(luces);
  // La sombra del atril: lo que queda pegado al corte (los 0.12 del mundo sobre el borde del subtítulo) se oscurece hasta
  // un 20 %, en degradé (sin línea): da profundidad detrás del subtítulo. Se agrega al sombreado de los materiales con
  // luz (la ropa, la piel, el pelo); `atril` es la altura del corte en el mundo (lejos abajo: sin sombra, el rótulo). La
  // cámara nunca gira, así que la altura del mundo es la de la cámara menos la del punto en la vista
  const atril = { value: -100 };
  const conAtril = new Set();
  personaje.grupo.traverse((o) => {
    const m = o.material;
    if (!o.isMesh || !m?.isMeshToonMaterial || conAtril.has(m)) return;
    conAtril.add(m);
    const previo = m.onBeforeCompile, clave = m.customProgramCacheKey();
    m.onBeforeCompile = (sh, r) => {
      previo.call(m, sh, r);
      sh.uniforms.corteAtril = atril;
      sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nuniform float corteAtril;')
        .replace('#include <opaque_fragment>', `outgoingLight *= 1.0 - 0.2 * (1.0 - smoothstep(corteAtril, corteAtril + 0.12, cameraPosition.y - vViewPosition.y));
        #include <opaque_fragment>`);
    };
    // (cada material con su programa: la nariz tiene su propio agregado)
    m.customProgramCacheKey = () => `${clave}|atril`;
  });
  /** La luz a la que va: la de la maqueta (el rótulo, que va en su círculo y no sobre la maqueta, con la de siempre).
   * Si se ve, llega en 0.6 s; si no (o `ya`), en el acto */
  function seguirLuz({ ya = false } = {}) {
    const hacia = lucesDe(esRotulo(planDestino()) ? null : avisos.ambiente);
    if (mismasLuces(hacia, lucesHacia) && !(ya && lucesDesde)) return;
    lucesHacia = hacia;
    if (!ya && seVe()) { lucesDesde = copiaLuces(luces); tLuces = ahora(); return; }
    lucesDesde = null;
    ponerLuces(mezclarLuces(hacia, hacia, 0, luces));
  }
  function avanzarLuces() {
    if (!lucesDesde) return;
    const u = suave((ahora() - tLuces) / LUZ_MS);
    ponerLuces(mezclarLuces(lucesDesde, lucesHacia, u, luces));
    if (u >= 1) lucesDesde = null;
  }

  let permitido = true;     // la preferencia del panel («Presentador»)
  let enEscena = false;     // lo quieren a la vista: una escena, el cierre, la píldora o una explicación (sin `quitar`)
  let arriba = false;       // subió (o está subiendo) y no se agachó
  let saliendo = false;     // agachándose (anim.salir)
  let saludoPendiente = null, ultimoCierre = false, pausado = false;
  let corriendo = false, cuadro = 0, antes = 0;
  let tFuera = 0, tVigilar = 0, tFundido = 0, tAcople = 0;
  let perdido = false;
  // la vista (lo que eligió vistas.js), su plan (el tamaño y el lienzo), el lugar y el lienzo
  let eleccion = null, plan = null;
  let W = 0, H = 0, dpr = 1, redimensiones = 0;
  let x = null, y = null, recorte = -2;     // el lienzo en la ventana (px) y lo que se le corta abajo (−1: nada)
  let escalaLienzo = 1;                      // (el rótulo: el lienzo se muestra achicado, con scale)
  let xCuerpo = null;                        // dónde está parado: la x del cuerpo en la ventana
  let cx = 0.5;                              // dónde va el cuerpo en el ancho del lienzo (0.5 de frente)
  // la transición en curso ({tipo, fase, t0, desde, hasta: {plan, x}, hecho}) y lo pedido mientras corría
  let trans = null, pendiente = null, ultimaTransicion = null, lugarPendiente = false, tRevisado = -Infinity;
  let ultimaAncla = null, anclaCuadro = null;
  // el círculo del rótulo: su escala y su opacidad (y la animación que las lleva)
  let circ = { k: 1, op: 1, anim: null };
  // el subtítulo cambió de alto: cuánto más abajo (px) se dibuja el cuerpo mientras lo alcanza
  let desfase = 0, subTopAntes = null;
  let acoplado = 0;          // el diámetro del rótulo acoplado al subtítulo (0: no lo está)
  let rastro = null;         // (con ?qa: lo de cada cuadro, para medir que nada salta)
  const tiempos = [];        // lo que tardó renderer.render en los últimos cuadros (sin los primeros: compila)
  let msCuadro = null, cuadros = 0;
  // lo último que avisó mando.js
  let ultimaEscena = null, ultimoEvento = null;
  const avisos = { encuadre: null, atlas: null, simulacion: null, ambiente: null };
  // la escena en curso: su programa (gesto de entrada, sostén), el objetivo (px), los cambios de lugar y sus esperas
  let prog = null, escenaN = 0, anterior = null;
  const saludados = new Set();   // los recorridos (rid) a los que ya saludó: la bienvenida es una sola
  let objetivoPx = null, cambiosLugar = 0, ultimoLugar = null;
  const esperas = new Set();
  const despues = (ms, f) => { const t = setTimeout(() => { esperas.delete(t); f(); }, ms); esperas.add(t); return t; };
  const cancelarEsperas = () => { for (const t of esperas) clearTimeout(t); esperas.clear(); };

  lienzo.addEventListener('webglcontextlost', (e) => { e.preventDefault(); perdido = true; detener(); lienzo.hidden = true; acoplar(0); });

  // ── La página ──
  let subEl = null, presEl = null;
  const subtitulo = () => (subEl?.isConnected ? subEl : (subEl = documento.querySelector('.subtitulo')));
  const pres = () => (presEl?.isConnected ? presEl : (presEl = documento.querySelector('#pres')));
  const VW = () => ventana.innerWidth || 800, VH = () => ventana.innerHeight || 600;
  /** La caja del subtítulo, solo si de verdad se ve (con .visible y su estilo a la vista: en el celular, con la hoja
   * grande, sigue con .visible pero oculto), o null. `op`: su opacidad (mientras aparece, < 1) */
  function ancla() {
    const s = subtitulo();
    if (!s?.classList?.contains('visible')) return null;
    const cs = ventana.getComputedStyle?.(s);
    if (cs && (cs.visibility !== 'visible' || Number(cs.opacity) <= 0.05)) return null;
    const r = s.getBoundingClientRect?.();
    return r && r.width > 0 ? { left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, height: r.height,
      op: cs ? Number(cs.opacity) : 1 } : null;
  }
  // sube (o se asoma) cuando el subtítulo terminó de aparecer (su fundido de 0.25 s): primero el atril, después él
  const llena = (a) => !!a && (reducido || !(a.op < 0.98));
  const visibleEl = (el) => {
    if (!el) return false;
    const cs = ventana.getComputedStyle?.(el);
    return !cs || (cs.display !== 'none' && cs.visibility !== 'hidden' && Number(cs.opacity) > 0.05);
  };
  const rect = (el) => (el ? caja(el.getBoundingClientRect?.()) : null);
  // la caja de ahora y la de cuando termine de llegar (sin el transform de su entrada: el panel que vuelve de «Solo 3D»
  // se desliza desde afuera), juntas: lo que no se tapa, ni ahora ni en un momento
  const rectFijo = (el) => {
    const r = rect(el);
    if (!el || !Number.isFinite(el.offsetWidth) || !el.offsetWidth) return r;
    return union([r, caja({ left: el.offsetLeft, top: el.offsetTop, right: el.offsetLeft + el.offsetWidth, bottom: el.offsetTop + el.offsetHeight })]);
  };
  /** Las cajas de lo que hay en la página (px de la ventana), para elegir el lugar y el objetivo: se leen una vez por
   * escena (y con el encuadre de la obra), no en cada cuadro */
  function leerCajas(a = ancla() || ultimaAncla) {
    const q = (s) => documento.querySelector(s);
    const cl = pres()?.classList;
    const c = { sub: a ? { x0: a.left, y0: a.top, x1: a.right, y1: a.bottom } : null };
    const panel = q('#pres > .panel') || q('.panel');
    if (panel && !cl?.contains('sin-panel')) c.panel = rectFijo(panel);
    c.ficha = rectFijo(q('.detalle:not([hidden])'));
    const ley = q('.leyenda3d');
    if (ley?.childElementCount && visibleEl(ley)) c.leyenda = rect(ley);
    const hud = q('.hud-tec');
    if (hud && visibleEl(hud)) c.hud = union([...hud.children].filter(visibleEl).map(rect));
    if (cl?.contains('con-inmersion')) c.marco = rect(q('.inmersion:not([hidden]) .inm-marco'));
    c.barra = rect(q('.barra'));
    c.control = rect(q('.control'));
    // la obra y sus rótulos donde quedarán (el encuadre de esta escena); antes de que llegue, los de la página son los
    // de la cámara de antes: no cuentan (salvo fuera de una escena: el cierre, la píldora, una explicación)
    const enc = avisos.encuadre;
    if (enc?.caja && prog && prog.tEncuadre !== null && (enc.n == null || enc.n === prog.d.n)) {
      c.obra = caja(enc.caja.obra);
      c.rotulos = (enc.caja.rotulos || []).map(caja).filter(Boolean);
    } else if (!prog || prog.evento !== 'narrar') {
      c.rotulos = [...documento.querySelectorAll('.lbl-p, .lbl-pin')].filter(visibleEl).map(rect).filter(Boolean);
    } else c.rotulos = [];
    c.foco = union([...documento.querySelectorAll('.foco')].map(rect));
    return c;
  }
  /** Lo que vistas.js necesita saber de la ventana y de la página */
  function contexto({ nuevo = false } = {}) {
    const vw = VW(), vh = VH(), chica = vw <= CHICA_PX;
    const cl = pres()?.classList;
    return { chica, VW: vw, VH: vh, horizontal: chica && vh < HORIZONTAL_PX, nuevo, reducido,
      dom: { conInmersion: !!cl?.contains('con-inmersion'), conDetalle: !!cl?.contains('con-detalle'), sinPanel: !!cl?.contains('sin-panel') },
      anterior };
  }

  // ── La vista, su tamaño y su lugar ──
  /** El plan de la vista `e` para esta ventana (vistas.js `medidas`, más la escala). El rótulo: dónde va (bajo el panel
   * o acoplado al subtítulo) y su tamaño, con lo que hay en la página */
  function planDe(e) {
    const ctx = contexto();
    const a = ancla() || ultimaAncla;
    let rotulo = null, panelX1 = null;
    if (e.vista === 'rotulo') {
      const c = leerCajas(a);
      rotulo = rotuloDe(ctx, c);
      panelX1 = c.panel?.x1 ?? null;
    }
    const m = medidas(e.vista, ctx, { cierre: !!e.cierre, subAlto: a?.height || 0, rotulo });
    return { ...m, s: m.p / A, chica: ctx.chica, VW: ctx.VW, VH: ctx.VH, panelX1 };
  }
  const mismoTamano = (a, b) => !!a && !!b && a.Wc === b.Wc && a.Hc === b.Hc && a.plano === b.plano && Math.abs(a.p - b.p) < 0.5
    && (a.modo || null) === (b.modo || null);
  const esRotulo = (pl = plan) => pl?.vista === 'rotulo';
  // el plan al que va (si una transición lo está llevando a otro)
  const planDestino = () => trans?.hasta?.plan || pendiente?.plan || plan;
  // cuánto se agacha para no verse detrás del subtítulo: que la cabeza (con el pelo y el contorno) quede bajo el corte
  const hondoDe = (pl = plan) => (pl && Number.isFinite(pl.yc) ? (1 - pl.yc) * A + 0.12 : 1.6);
  /** Pasar a otro plan (el tamaño del lienzo, el rótulo y el lugar que el subtítulo le hace) */
  function ponerPlan(np) {
    const eraRotulo = esRotulo(plan);
    plan = np;
    const rot = esRotulo(np);
    // (del círculo a la figura o al revés, la luz cambia en el acto: pasa mientras no se ve)
    if (rot !== eraRotulo) seguirLuz({ ya: true });
    lienzo.classList.toggle('rotulo', rot);
    if (!rot) { escalaLienzo = 1; lienzo.style.opacity = ''; lienzo.style.transition = ''; circ = { k: 1, op: 1, anim: null }; }
    acoplar(rot && np.modo === 'acoplado' && permitido && !perdido ? np.lado : 0);
    recorte = -2;
    if (corriendo) aplicarTamano();
  }
  /** El subtítulo le hace lugar al rótulo acoplado (propuesta.html: .pres.rotulo-acoplado y --pres-rotulo) */
  function acoplar(L) {
    clearTimeout(tAcople);
    const el = pres();
    if (!el || L === acoplado) return;
    acoplado = L;
    el.classList.toggle('rotulo-acoplado', L > 0);
    if (L > 0) el.style.setProperty('--pres-rotulo', `${L + 10}px`);
    else el.style.removeProperty('--pres-rotulo');
  }
  /** El único lugar que cambia el tamaño del lienzo (y su resolución y el grosor del contorno); acercándose a otro
   * plano, el mayor de los dos */
  function aplicarTamano(Wc = plan.Wc, Hc = plan.Hc) {
    const d = Math.min(ventana.devicePixelRatio || 1, Hc > 300 ? 1.5 : 2);
    // el mismo peso de línea en todas las vistas, también en el busto del celular (≈1.5 px CSS: con el filo crema de
    // propuesta.html se lee como un dibujo); el círculo chico (acoplado, el del celular), un poco menos
    personaje.contorno.grosor.value = (esRotulo() && plan.p < 160 ? 1.2 : 1.5) * d;
    if (Wc === W && Hc === H && d === dpr) return;
    W = Wc; H = Hc; dpr = d;
    renderer.setPixelRatio(dpr);
    renderer.setSize(W, H, false);
    lienzo.style.width = `${W}px`;
    lienzo.style.height = `${H}px`;
    camara.aspect = W / H;
    camara.updateProjectionMatrix();
    personaje.contorno.resolucion.value.set(W * dpr, H * dpr);
    redimensiones++;
  }
  // ¿Está a la vista de verdad (arriba y no subiendo desde abajo)? Si no, el lugar se elige sin histéresis
  const aLaVista = () => corriendo && !lienzo.hidden && arriba && !saliendo && !['entra', 'asoma'].includes(anim.estado().entrando)
    && (esRotulo() ? circ.op > 0.5 : personaje.cuerpo.position.y > -0.3);
  // ¿Se ve algo de él? (la cabeza arriba del corte, o el círculo) Si no, los cambios van en el acto
  function seVe() {
    if (!corriendo || lienzo.hidden || !personaje.grupo.visible || !plan) return false;
    if (esRotulo()) return circ.op > 0.05;
    return personaje.cuerpo.position.y > -(1 - plan.yc) * A + 0.03;
  }
  /**
   * Pasar a otro plan (otra vista de otro tamaño) o a otro lugar: con la transición que corresponde (vistas.js
   * `transicion`: girar, caminar, acercarse, saltar, el rótulo; con movimiento reducido, fundirse). Si no se ve, en el
   * acto. Mientras corre otra: si todavía no se ve lo nuevo (agachándose, el círculo que se encoge) va en su lugar; si
   * no, cuando termine
   */
  function cambiarA({ plan: np = null, x: nx = null } = {}) {
    const conX = Number.isFinite(nx);
    if (trans) {
      if (!trans.hecho) { if (np) trans.hasta.plan = np; if (conX) trans.hasta.x = nx; return; }
      pendiente = { plan: np || pendiente?.plan || null, x: conX ? nx : pendiente?.x ?? null };
      return;
    }
    const otroPlan = !!np && !mismoTamano(np, plan);
    // (otra vista del mismo tamaño: solo gira)
    if (np && !otroPlan) ponerPlan({ ...np, panelX1: np.panelX1 ?? plan?.panelX1 ?? null });
    const destino = { plan: otroPlan ? np : plan, x: conX ? nx : xCuerpo };
    const otroLugar = conX && Number.isFinite(xCuerpo) && Math.abs(nx - xCuerpo) >= 3 && !esRotulo(destino.plan);
    if (!otroPlan && !otroLugar) { if (conX && !esRotulo(destino.plan)) xCuerpo = nx; return; }
    const de = (pl, xx) => ({ vista: pl?.vista, plano: pl?.plano, p: pl?.p, x: xx, modo: pl?.modo });
    ultimaTransicion = transicion(de(plan, xCuerpo), de(destino.plan, destino.x), { reducido, p: plan?.p });
    if (!seVe()) { aplicarDestino(destino); return; }
    empezarTrans(ultimaTransicion, destino);
  }
  function aplicarDestino(d) {
    if (d.plan && d.plan !== plan) ponerPlan(d.plan);
    if (Number.isFinite(d.x) && !esRotulo()) xCuerpo = d.x;
  }
  /** Empieza la transición `tipo` hacia `destino` ({plan, x}); avanzarTrans() la lleva cuadro a cuadro */
  function empezarTrans(tipo, destino) {
    const tr = { tipo, t0: ahora(), hasta: destino, desde: { plan, x: xCuerpo }, hecho: false, fase: null };
    trans = tr;
    // el brazo que apuntaba desde el lugar de antes ya no apunta a nada: vuelve a la casa (al llegar vuelve a apuntar)
    if (tipo !== 'acercar' && tipo !== 'giro' && APUNTAN.includes(anim.estado().gesto)) {
      anim.detenerGesto();
      if (prog?.fase === 'gesto') prog.fase = 'espera';
      else if (prog?.fase === 'sosten') tr.reapuntar = true;
    }
    if (tipo === 'caminar') {
      // camina detrás del subtítulo en 3/4: el lienzo y la cámara lo siguen (xCuerpo sale de grupo.position.x)
      tr.hecho = true;
      tr.x0 = xCuerpo;
      anim.reubicar(0);
      const dist = destino.x - xCuerpo;
      const pxs = Math.max(CAMINAR_PX_S, Math.abs(dist) / CAMINAR_MAX_S);
      anim.caminarA(dist / plan.s, { velocidad: pxs / plan.s, rumbo: 0.6, zancada: 0.65 });
    } else if (tipo === 'acercar') {
      // la cámara va de un plano al otro (colocar lo mezcla); el lienzo, el mayor de los dos mientras dura
      tr.hecho = true;
      aplicarTamano(Math.max(plan.Wc, destino.plan.Wc), Math.max(plan.Hc, destino.plan.Hc));
    } else if (tipo === 'saltar' || (tipo === 'rotulo' && !esRotulo())) {
      // se agacha detrás del subtítulo; abajo, el lienzo salta (o pasa a ser el círculo) y se asoma
      tr.fase = 'baja';
      anim.mirarA(null);
      anim.agacharse(() => { if (trans === tr) tr.fase = 'cambia'; }, { hondo: hondoDe(plan) });
    } else if (tipo === 'rotulo') {
      // el círculo se encoge y él se asoma en el lugar nuevo
      tr.fase = 'encoge';
      circulo(0.6, 0, ENCOGE_S, () => { if (trans === tr) tr.fase = 'cambia'; });
    } else {
      // fundido (movimiento reducido, de un rótulo a otro): se funde, cambia y vuelve
      tr.fase = 'funde';
      lienzo.classList.add('fundido');
      clearTimeout(tFundido);
      tFundido = setTimeout(() => {
        if (trans !== tr) return;
        tr.hecho = true;
        aplicarDestino(tr.hasta);
        // ya en el lugar nuevo (el dibujo y el lienzo juntos) antes de volver a verse
        if (corriendo) { colocar(); orientar(undefined, undefined, { ya: true }); dibujar(); }
        lienzo.classList.remove('fundido');
        terminar();
      }, FUNDIDO_MS);
    }
  }
  /** Cada cuadro: la transición en curso (y el círculo del rótulo) */
  function avanzarTrans() {
    avanzarCirculo();
    const tr = trans;
    if (!tr) return;
    const t = ahora() - tr.t0;
    if (tr.tipo === 'caminar') {
      if (!anim.estado().caminando || t > TRANS_MAX_MS) { anim.reubicar(0); xCuerpo = tr.hasta.x; terminar(); }
    } else if (tr.tipo === 'acercar') {
      if (t >= ACERCAR_MS) { aplicarDestino(tr.hasta); aplicarTamano(); terminar(); }
    } else if (tr.fase === 'cambia') {
      // agachado (o el círculo ya chico): el lienzo salta al lugar nuevo, ya orientado, y aparece
      tr.hecho = true;
      const hondoAntes = hondoDe(plan);
      aplicarDestino(tr.hasta);
      colocar();
      orientar(undefined, undefined, { ya: true });
      if (esRotulo()) {
        anim.entrar(null, { instante: true });
        tr.fase = 'crece';
        circulo(1, 1, reducido ? FUNDIDO_MS / 1000 : CRECE_S, () => { if (trans === tr) terminar(); }, { k: reducido ? 1 : 0.6, op: 0 });
      } else {
        tr.fase = 'sube';
        anim.asomarse(() => { if (trans === tr) terminar(); }, { hondo: hondoDe(plan), desde: -Math.max(hondoAntes, hondoDe(plan)) });
      }
    } else if (t > TRANS_MAX_MS) terminarYa();
  }
  /** Terminó la transición: lo que quedó pendiente; si no, orientado hacia lo que explica (y apuntándolo otra vez) */
  function terminar() {
    const tr = trans;
    trans = null;
    if (pendiente) { const p = pendiente; pendiente = null; cambiarA(p); }
    if (trans) { trans.reapuntar = trans.reapuntar || tr?.reapuntar; return; }
    orientar();
    if (tr?.reapuntar && prog?.fase === 'sosten') { objetivoPx = puntoDe(prog.e, leerCajas(), { prever: true }); sostener(); }
  }
  /** La transición en curso, hecha en el acto (va a esconderse, o se escondió) */
  function terminarYa() {
    const tr = trans;
    if (!tr) return;
    clearTimeout(tFundido);
    lienzo.classList.remove('fundido');
    if (tr.tipo === 'caminar') { xCuerpo = tr.x0 + personaje.grupo.position.x * plan.s; anim.reubicar(0); }
    else aplicarDestino(tr.hasta);
    trans = null;
    if (pendiente) { aplicarDestino({ plan: pendiente.plan || plan, x: pendiente.x ?? xCuerpo }); pendiente = null; }
    if (corriendo) aplicarTamano();
  }
  /** El círculo del rótulo va a la escala `k` y la opacidad `op` en `dur` segundos (con movimiento reducido, sin
   * escala); `desde`: de dónde parte */
  function circulo(k, op, dur, al = null, desde = null) {
    if (desde) circ = { ...circ, k: reducido ? 1 : desde.k, op: desde.op };
    circ.anim = { k0: circ.k, k1: reducido ? 1 : k, o0: circ.op, o1: op, t0: ahora(), dur: Math.max(10, dur * 1000), al };
    // (la opacidad la lleva el cuadro: sin la transición de CSS, que la atrasaría)
    lienzo.style.transition = 'none';
  }
  function avanzarCirculo() {
    const a = circ.anim;
    if (!a) return;
    const u = acotar((ahora() - a.t0) / a.dur, 0, 1);
    // crece con un frenado suave; se encoge acelerando
    const e = a.k1 >= a.k0 ? 1 - (1 - u) ** 3 : u * u;
    circ.k = mezclar(a.k0, a.k1, e);
    circ.op = mezclar(a.o0, a.o1, Math.min(1, u * 1.6));
    if (u >= 1) {
      circ.anim = null;
      if (circ.op >= 0.999) { lienzo.style.opacity = ''; lienzo.style.transition = ''; }
      a.al?.();
    }
  }
  /** El punto al que apunta la vista (px), con las cajas `c`. Lo resaltado que todavía no apareció: el borde del panel,
   * de la ficha o de la leyenda a la altura del hombro (main.js lo trae a esa altura) */
  function puntoDe(e, c, { prever = false } = {}, m = planDestino()) {
    if (!e || !m) return null;
    const subTop = c.sub?.y0 ?? ultimaAncla?.top ?? VH() - 96;
    const yH = alturaHombro(subTop, Number.isFinite(m.yc) ? m : { p: m.p });
    const o = { yHombro: yH, VW: VW(), VH: VH() };
    let p = objetivoDe(e.objetivo, e.lado, c, o);
    if (!p && e.objetivo === 'foco' && prever) {
      if (e.lado === 'panel' && c.panel) p = { x: c.panel.x1 - 24, y: acotar(yH, c.panel.y0 + 40, c.panel.y1 - 40) };
      else if (e.lado === 'ficha' && c.ficha) p = { x: c.ficha.x0 + 24, y: acotar(yH, c.ficha.y0 + 60, c.ficha.y1 - 40) };
      else if (e.lado === 'leyenda' && c.leyenda) {
        const n = prog?.d?.resaltar?.n;
        const item = rect(documento.querySelector('.leyenda3d')?.children?.[n - 1]) || c.leyenda;
        p = { x: item.x0, y: acotar(yH, item.y0 + 4, item.y1 - 4) };
      } else if (e.lado === 'hoja' && c.panel) p = { x: (c.panel.x0 + c.panel.x1) / 2, y: c.panel.y0 + 60 };
    }
    return p;
  }
  /** Elegir (o revisar) el lugar de la escena con lo que hay en la página. Cuenta los cambios (a lo sumo uno). Con `np`
   * (otro plano), el lugar para ese plano, y van juntos en una sola transición */
  function decidirLugar(np = null) {
    if (!plan || !eleccion) return;
    const a = ancla();
    // sin el subtítulo a la vista (se está cambiando): lo decide colocar() en cuanto vuelva
    if (!a) { lugarPendiente = true; if (np) cambiarA({ plan: np }); return; }
    const c = leerCajas(a);
    // el rótulo: su lugar sale del panel y del subtítulo (bajo el panel o acoplado); otro modo o tamaño se funde
    if (eleccion.vista === 'rotulo') {
      cambiarA({ plan: planDe(eleccion) });
      previsto = puntoDe(eleccion, c, { prever: true });
      orientar(previsto);
      return;
    }
    const m = np || planDestino();
    const punto = puntoDe(eleccion, c, { prever: true }, m);
    const ctx = contexto();
    // oculto (o subiendo) elige sin histéresis: moverse no se ve (entre dos escenas el subtítulo se apaga un momento,
    // se agacha y se asoma ya en el lugar de la escena nueva, como quien salta detrás del atril)
    const visto = aLaVista() && !esRotulo();
    const r = elegirLugar(eleccion, m, ctx, c, { x: visto ? xCuerpo : null, cambios: cambiosLugar, ms: prog?.d?.ms }, { punto });
    if (!r) { if (np) cambiarA({ plan: np }); return; }
    ultimoLugar = r;
    previsto = punto;
    if (r.cambia && Number.isFinite(xCuerpo) && visto && Math.abs(r.x - xCuerpo) >= 3) cambiosLugar++;
    if (r.cambia || np) cambiarA({ plan: np, x: r.cambia ? r.x : null });
    orientar(punto, r.x);
  }
  /** El cuerpo hacia lo que explica (el rumbo de la vista); de frente si el gesto lo pide. Y el cuerpo en el lienzo.
   * `ya`: gira en el acto (agachado, antes de asomarse) */
  let frente = false, previsto = null;   // (lo que se espera señalar, antes de que aparezca)
  function orientar(punto = objetivoPx ?? previsto, desde = xCuerpo, { ya = false } = {}) {
    if (!eleccion) return;
    const dx = punto && Number.isFinite(desde) ? punto.x - desde : NaN;
    const r = rumboDe(eleccion.vista, dx, frente);
    anim.girar(r, { ya });
    anim.apertura = planDestino()?.apertura ?? 0.55;
    cx = cxDe(rumboDe(eleccion.vista, dx, false));
  }
  /** Pasar a la vista `e` (de elegirVista): el plan (si cambia el tamaño, con su lugar y su transición), el giro en el
   * acto y el lugar enseguida (`lugarYa`) o a los 150 ms (o al llegar el encuadre) */
  function ponerVista(e, { lugarYa = false } = {}) {
    eleccion = e;
    const np = planDe(e);
    frente = false;
    if (!plan) { ponerPlan(np); xCuerpo = null; }
    const otro = !mismoTamano(np, planDestino());
    const a = ancla();
    // otro plano: el lugar para ese plano, ya (una sola transición: acercarse, saltar o el rótulo)
    if (otro) decidirLugar(np);
    else if (np !== plan) cambiarA({ plan: np });
    // el giro, en el acto, hacia donde está lo que explica (con lo que se sabe ahora)
    if (a && Number.isFinite(xCuerpo)) orientar(puntoDe(e, leerCajas(a), { prever: true }));
    else orientar(null);
    if (otro && a) return;
    // sin el subtítulo a la vista todavía, lo elige colocar() en cuanto aparezca
    if (lugarYa || !Number.isFinite(xCuerpo) || !aLaVista()) { lugarPendiente = !ancla(); if (!lugarPendiente) decidirLugar(); }
    else despues(LUGAR_MS, () => { if (prog && !prog.lugarHecho) { prog.lugarHecho = true; decidirLugar(); } });
  }

  /** Cada cuadro: el plan (si cambió la ventana), el lugar (si dejó de servir), el lienzo pegado al borde de arriba
   * del subtítulo y la cámara que pone el corte justo en ese borde (o el círculo del rótulo en su lugar) */
  function colocar(dt = 0) {
    const vw = VW(), vh = VH();
    // otra ventana (o la primera vez): otra vista para ella y, en el acto, el lugar
    if (!plan || plan.VW !== vw || plan.VH !== vh) { cambioDeVentana(); }
    if (trans?.tipo !== 'acercar') aplicarTamano();
    const a = ancla();
    anclaCuadro = a;
    if (a) ultimaAncla = a;
    // sin subtítulo (agachándose) se queda en la última línea donde estaba; sin ninguno nunca, abajo de todo
    const r = a || ultimaAncla || { left: vw * 0.3, right: vw * 0.7, top: vh - 96, bottom: vh - 40, width: vw * 0.4, height: 56 };
    if (a && (xCuerpo === null || lugarPendiente)) { lugarPendiente = false; decidirLugar(); }
    // el subtítulo cambió y la cadera quedaría en el aire: se vuelve a elegir (cuenta como el cambio de la escena)
    // (a lo sumo dos veces por segundo: si ningún lugar sirve, no lee la página en cada cuadro)
    else if (a && !trans && !esRotulo() && Number.isFinite(xCuerpo) && ahora() - tRevisado > 500
      && (xCuerpo - plan.cadera < a.left + 8 || xCuerpo + plan.cadera > a.right - 8)) { tRevisado = ahora(); decidirLugar(); }
    if (esRotulo()) { colocarRotulo(r); return; }
    if (xCuerpo === null) xCuerpo = r.left + plan.margen;
    if (trans?.tipo === 'caminar') xCuerpo = trans.x0 + personaje.grupo.position.x * plan.s;
    // el plano de ahora (acercándose: entre el de antes y el nuevo, y la x también)
    let s = plan.s, yc = plan.yc, bajo = plan.bajo;
    if (trans?.tipo === 'acercar') {
      const u = suave((ahora() - trans.t0) / ACERCAR_MS), b = trans.hasta.plan;
      s = mezclar(plan.s, b.s, u);
      yc = mezclar(plan.yc, b.yc, u);
      bajo = mezclar(plan.bajo, b.bajo, u);
      if (Number.isFinite(trans.desde.x) && Number.isFinite(trans.hasta.x)) xCuerpo = mezclar(trans.desde.x, trans.hasta.x, u);
    }
    nivelCara(0.312 * A * s);
    // el subtítulo cambió de alto (otro texto): el corte lo sigue en el acto y el cuerpo lo alcanza en un momento, sin
    // saltar (se dibuja `desfase` px más abajo, que se va a 0)
    if (subTopAntes !== null && seVe()) desfase -= r.top - subTopAntes;
    else if (!seVe()) desfase = 0;
    subTopAntes = r.top;
    desfase = acotar(desfase * Math.exp(-Math.max(0, dt) / ASENTAR_SUB_S), -0.06 * plan.p, 0.6 * plan.p);
    if (Math.abs(desfase) < 0.2) desfase = 0;
    escalaLienzo = 1;
    // el lienzo dentro de la pantalla: se corre la cámara, no el cuerpo (el cuerpo entre el 25 y el 75 % del ancho)
    let left = Math.round(xCuerpo - cx * W);
    left = acotar(left, Math.min(0, vw - W), Math.max(0, vw - W));
    left = acotar(left, Math.round(xCuerpo - 0.75 * W), Math.round(xCuerpo - 0.25 * W));
    const cxPx = xCuerpo - left;
    const bajoPx = Math.round(bajo);
    const top = Math.ceil(r.top) + bajoPx - H;
    // la cámara: el corte (yc·A del mundo) cae en la fila H − bajo del lienzo y el cuerpo en la columna cxPx
    const h = H / s;
    const yb = yc * A - bajoPx / s + desfase / s;
    atril.value = yc * A + desfase / s;   // (la sombra del atril, sobre el corte)
    camara.position.set(personaje.grupo.position.x - (cxPx - W / 2) / s, yb + h / 2, h / 2 / TAN);
    camara.updateMatrixWorld();
    x = left; y = top;
    ponerTransform(`translate(${x}px, ${y}px)`);
    // lo que queda bajo el corte no se ve: el subtítulo es vidrio y se vería a través
    if (bajoPx !== recorte) { recorte = bajoPx; lienzo.style.clipPath = `inset(0 0 ${recorte}px 0)`; }
  }
  // El detalle de la cara para lo que mide la cabeza en la pantalla (personaje.js `cara.nivel`: con la cabeza chica, las
  // cejas, las pestañas y los ojos más marcados). Cambia con la vista; acercándose, cuadro a cuadro (no salta). Solo hace
  // algo cuando cambia el px
  let pxCabeza = null, nivel = 0;
  function nivelCara(px) {
    const r = Math.round(px);
    if (!Number.isFinite(r) || r === pxCabeza) return;
    pxCabeza = r;
    try { nivel = personaje.cara.nivel?.(r) ?? 0; } catch { nivel = 0; }
  }
  // el transform del lienzo, solo cuando cambia
  let trTexto = '';
  const ponerTransform = (t) => { if (t !== trTexto) { trTexto = t; lienzo.style.transform = t; } };
  /** El rótulo: el círculo en su lugar (bajo el panel o acoplado al subtítulo), con la cabeza y los hombros adentro. El
   * lienzo se dibuja a su tamaño y se muestra a la medida del subtítulo de ahora y de su animación (scale) */
  function colocarRotulo(r) {
    const pos = posRotulo(plan, { x0: r.left, y0: r.top, x1: r.right, y1: r.bottom }, plan.panelX1);
    const L = pos?.L ?? W;
    const cxV = pos ? pos.x0 + L / 2 : r.left + L / 2, cyV = pos ? pos.y0 + L / 2 : r.top - L / 2;
    xCuerpo = cxV;
    escalaLienzo = (L / W) * circ.k;
    nivelCara(0.312 * plan.p * (L / W));
    atril.value = -100;   // (en el círculo no hay atril)
    const left = Math.round(cxV - W / 2), top = Math.round(cyV - H / 2);
    const P = PLANOS.primer, h = H / plan.s;
    camara.position.set(personaje.grupo.position.x, ((P.yb + P.ya) / 2) * A, h / 2 / TAN);
    camara.updateMatrixWorld();
    const e = Math.round(escalaLienzo * 1000) / 1000;
    x = left; y = top;
    ponerTransform(`translate(${left}px, ${top}px) scale(${e})`);
    if (recorte !== -1) { recorte = -1; lienzo.style.clipPath = 'none'; }
    const op = circ.anim || circ.op < 0.999 ? String(Math.round(circ.op * 1000) / 1000) : '';
    if (lienzo.style.opacity !== op) lienzo.style.opacity = op;
  }
  /** La ventana cambió de tamaño (o es la primera vez): la vista para la ventana nueva, en su lugar preferido */
  function cambioDeVentana() {
    const antes = eleccion;
    const e = ultimoEvento ? elegirVista({ ...(ultimaEscena || {}), evento: ultimoEvento }, contexto()) : eleccion || elegirVista({ evento: 'explicar' }, contexto());
    e.saludoPrimero = false;
    eleccion = e;
    trans = null;
    pendiente = null;
    clearTimeout(tFundido);
    lienzo.classList.remove('fundido');
    anim.reubicar(0);
    ponerPlan(planDe(eleccion));
    xCuerpo = null;
    if (prog) {
      prog.lugarHecho = true;
      prog.e = e;
      // otra vista (la pantalla pasó a chica o a grande): el sostén hacia lo que explica, en el cuadro siguiente
      if (antes && (antes.vista !== e.vista || antes.lado !== e.lado) && (prog.fase === 'sosten' || prog.fase === 'gesto')) {
        despues(0, () => { objetivoPx = puntoDe(e, leerCajas(), { prever: true }); sostener(); });
      }
    }
  }

  /** Un punto de la pantalla (px de la ventana) en el mundo del presentador: sobre el plano z = 0.6, delante de él. */
  let ultimoMundo = null;   // (el último punto del mundo al que se apuntó: estado().apunta lo proyecta, para medirlo)
  // del lienzo (px del lienzo) a la ventana, y al revés (el rótulo se muestra con una escala, desde su centro)
  const aVentana = (u, v) => ({ x: x + W / 2 + (u - W / 2) * escalaLienzo, y: y + H / 2 + (v - H / 2) * escalaLienzo });
  const aLienzo = (px, py) => ({ u: W / 2 + (px - x - W / 2) / escalaLienzo, v: H / 2 + (py - y - H / 2) / escalaLienzo });
  function alMundo(px, py) {
    const { u, v } = aLienzo(px, py);
    const ndc = new THREE.Vector3((u / W) * 2 - 1, -(v / H) * 2 + 1, 0.5).unproject(camara);
    const d = ndc.sub(camara.position).normalize();
    const t = (0.6 - camara.position.z) / d.z;
    return (ultimoMundo = camara.position.clone().addScaledVector(d, t));
  }
  function centroDe(el) {
    const r = el?.getBoundingClientRect?.();
    return r && r.width > 0 ? { x: r.left + r.width / 2, y: r.top + r.height / 2 } : null;
  }

  // ── Lo que se ve de él, proyectado en la ventana (solo cuando se pide: estado().cajas, estado().punta) ──
  const mvp = new THREE.Matrix4(), vtx = new THREE.Vector3();
  function cajaDe(obj) {
    if (x === null || !W || !personaje.grupo.visible) return null;
    personaje.grupo.updateMatrixWorld(true);
    camara.updateMatrixWorld();
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    obj.traverseVisible((o) => {
      // (el casco del contorno es la misma geometría: no suma nada)
      if (!o.isMesh || !o.geometry?.attributes?.position || (o.parent?.isMesh && o.parent.geometry === o.geometry)) return;
      mvp.multiplyMatrices(camara.projectionMatrix, camara.matrixWorldInverse).multiply(o.matrixWorld);
      const pos = o.geometry.attributes.position;
      for (let i = 0; i < pos.count; i++) {
        vtx.fromBufferAttribute(pos, i).applyMatrix4(mvp);
        const { x: px, y: py } = aVentana(((vtx.x + 1) / 2) * W, ((1 - vtx.y) / 2) * H);
        if (px < x0) x0 = px; if (px > x1) x1 = px; if (py < y0) y0 = py; if (py > y1) y1 = py;
      }
    });
    if (!(x1 > x0)) return null;
    // lo que de verdad se ve: dentro del lienzo y arriba del corte
    const v0 = aVentana(0, 0), v1 = aVentana(W, H - Math.max(0, recorte));
    const c = [Math.max(x0, v0.x), Math.max(y0, v0.y), Math.min(x1, v1.x), Math.min(y1, v1.y)];
    if (c[2] <= c[0] || c[3] <= c[1]) return null;
    const [a, b, d, e] = c.map(Math.round);
    return { x0: a, y0: b, x1: d, y1: e, ancho: d - a, alto: e - b };
  }
  /** La punta del índice de la mano que apunta (la del lado del objetivo) y su hombro, en px de la ventana */
  function puntaPx() {
    if (x === null || !W || !personaje.grupo.visible || !objetivoPx || !Number.isFinite(xCuerpo)) return null;
    const l = objetivoPx.x < xCuerpo ? 'D' : 'I';
    personaje.grupo.updateMatrixWorld(true);
    camara.updateMatrixWorld();
    const pp = (v) => { v.project(camara); const w = aVentana(((v.x + 1) / 2) * W, ((1 - v.y) / 2) * H); return { x: Math.round(w.x), y: Math.round(w.y) }; };
    const t = pp(personaje.manos[l].dedos[0][1].localToWorld(new THREE.Vector3(0, -0.044, 0)));
    const h = pp(new THREE.Vector3().setFromMatrixPosition(personaje.huesos[`hombro${l}`].matrixWorld));
    return { ...t, lado: l, hombro: h };
  }

  // ── El cuadro ──
  function dibujar() {
    const t0 = reloj.now();
    renderer.render(escena, camara);
    const ms = reloj.now() - t0;
    // media móvil de los últimos 30 cuadros; los 3 primeros no cuentan (compilan los sombreadores)
    if (++cuadros > 3) {
      tiempos.push(ms);
      if (tiempos.length > 30) tiempos.shift();
      msCuadro = tiempos.reduce((a, b) => a + b, 0) / tiempos.length;
    }
  }
  function bucle(ms) {
    cuadro = 0;
    if (!corriendo) return;
    const dt = antes ? (ms - antes) / 1000 : 1 / 60;
    antes = ms;
    anim.actualizar(dt);
    avanzarTrans();
    colocar(dt);
    avanzarLuces();
    // el subtítulo se fue (o ya no lo quieren): se agacha; volvió (y terminó de aparecer) mientras se agachaba: se asoma
    if (arriba && (!enEscena || !anclaCuadro)) agachar({ despedida: !enEscena && ultimoCierre });
    else if (!arriba && enEscena && llena(anclaCuadro) && permitido) subir();
    avanzar();
    dibujar();
    if (rastro) anotar(ms);
    if (!personaje.grupo.visible && !saliendo) { esconder(); return; }
    cuadro = ventana.requestAnimationFrame(bucle);
  }
  // (con ?qa) lo de cada cuadro: dónde se ve la cabeza (px de la ventana; null si está bajo el corte), el lienzo y la
  // transición, para medir que nada salta
  const vCab = new THREE.Vector3();
  function anotar(ms) {
    let cab = null;
    if (personaje.grupo.visible && x !== null && W) {
      vCab.setFromMatrixPosition(personaje.huesos.cabeza.matrixWorld).project(camara);
      const w = aVentana(((vCab.x + 1) / 2) * W, ((1 - vCab.y) / 2) * H);
      const corteY = aVentana(0, H - Math.max(0, recorte)).y;
      cab = { x: Math.round(w.x * 10) / 10, y: Math.round(w.y * 10) / 10, oculta: w.y > corteY - 2 };
    }
    rastro.push({ t: Math.round(ms), cab, lienzo: [x, y, W, H], esc: Math.round(escalaLienzo * 1000) / 1000, op: circ.op,
      trans: trans ? `${trans.tipo}${trans.fase ? `:${trans.fase}` : ''}` : null, y: Math.round(personaje.cuerpo.position.y * 100) / 100,
      vista: plan?.vista ?? null, desfase: Math.round(desfase), gesto: anim.estado().gesto, fase: prog?.fase ?? null });
    if (rastro.length > 4000) rastro.shift();
  }
  function arrancar() {
    if (corriendo || perdido) return;
    corriendo = true;
    antes = 0;
    lienzo.hidden = false;
    colocar();
    cuadro = ventana.requestAnimationFrame(bucle);
  }
  function detener() {
    corriendo = false;
    if (cuadro) ventana.cancelAnimationFrame(cuadro);
    cuadro = 0;
  }

  // ── Subir y bajar ──
  /** Sube desde detrás del subtítulo (que ya terminó de aparecer): agachado, desde abajo; si se estaba agachando, se
   * asoma desde donde está; el rótulo, creciendo. En la primera escena saluda, 0.3 s antes de terminar de subir */
  function subir() {
    clearTimeout(tVigilar);
    clearTimeout(tFuera);
    tVigilar = 0;
    const saludo = saludoPendiente;
    saludoPendiente = null;
    const oculto = lienzo.hidden || !corriendo || !personaje.grupo.visible;
    arriba = true;
    saliendo = false;
    if (trans && trans.tipo !== 'acercar') terminarYa();
    // (vuelve sin despedirse)
    if (anim.estado().gesto === 'despedirse') anim.detenerGesto();
    acoplar(esRotulo() && plan.modo === 'acoplado' ? plan.lado : 0);
    let saludado = false;
    const alSaludar = () => {
      if (!saludo || saludado) return;
      saludado = true;
      const p = prog;
      frente = true;
      orientar();
      // con el brazo del lado que tiene más lugar (que la mano no pase por encima del panel)
      const c = leerCajas();
      const izq = Number.isFinite(xCuerpo) ? xCuerpo - (c.panel?.x1 ?? 0) : Infinity;
      const der = Number.isFinite(xCuerpo) ? (c.ficha?.x0 ?? VW()) - xCuerpo : Infinity;
      anim.gesto('saludar', { dur: saludo.dur, lado: izq < der ? 'I' : 'D', alTerminar: () => { if (p) p.saludado = true; } });
      // (si el gesto lo corta otro, igual cuenta como saludado a su tiempo)
      despues(saludo.dur * 1000 + 50, () => { if (p) p.saludado = true; });
    };
    if (esRotulo()) {
      anim.entrar(null, { instante: true });
      // (desde chico y transparente; si se estaba encogiendo, desde donde está)
      circulo(1, 1, reducido ? FUNDIDO_MS / 1000 : CRECE_S, null, oculto ? { k: 0.6, op: 0 } : null);
      alSaludar();
    } else if (!oculto && personaje.cuerpo.position.y < -0.005) {
      anim.asomarse(alSaludar, { hondo: hondoDe(plan), casi: [0.3, alSaludar] });
    } else {
      anim.entrar(alSaludar, { hondo: hondoDe(plan), casi: [0.3, alSaludar] });
    }
    arrancar();
  }
  /** Se agacha en el acto detrás de la línea donde estaba el subtítulo (el rótulo se encoge); después del cierre,
   * despidiéndose: un asentimiento de «gracias» y la mano que saluda mientras baja */
  function agachar({ despedida = false } = {}) {
    if (!arriba) return;
    arriba = false;
    saliendo = true;
    cancelarEsperas();
    anim.callar();
    anim.mirarA(null);
    // lo que iba a cambiar queda hecho (se está yendo); acercándose, sigue (es solo la cámara)
    if (trans && trans.tipo !== 'acercar') terminarYa();
    if (esRotulo()) {
      anim.detenerGesto();
      circulo(0.6, 0, reducido ? FUNDIDO_MS / 1000 : ENCOGE_S, () => { if (!arriba) { saliendo = false; personaje.grupo.visible = false; } });
    } else {
      const chau = despedida && !reducido;
      if (chau) anim.gesto('despedirse', { dur: 1.1, entra: 0.2 });
      else anim.detenerGesto();
      const hondo = Math.max(hondoDe(plan), trans?.tipo === 'acercar' ? hondoDe(trans.hasta.plan) : 0);
      anim.salir(() => { saliendo = false; }, { hondo, gracias: chau });
    }
    // con muy pocos cuadros por segundo (o la pestaña oculta) tardaría más: se va igual
    clearTimeout(tFuera);
    tFuera = setTimeout(() => { if (!arriba && saliendo) esconder(); }, FUERA_MS);
  }
  /** Sin dibujar: el lienzo oculto y el bucle quieto. Si todavía lo quieren, espera a que vuelva el subtítulo */
  function esconder() {
    clearTimeout(tFuera);
    arriba = false;
    saliendo = false;
    terminarYa();
    anim.callar();
    anim.detenerGesto();
    personaje.grupo.visible = false;
    detener();
    lienzo.hidden = true;
    lienzo.classList.remove('fundido');
    circ = { k: 1, op: 1, anim: null };
    lienzo.style.opacity = '';
    lienzo.style.transition = '';
    desfase = 0;
    subTopAntes = null;
    // la escena vuelve a empezar si se asoma de nuevo (el gesto de entrada otra vez)
    if (prog && (prog.fase === 'gesto' || prog.fase === 'sosten')) prog.fase = 'espera';
    if (enEscena) vigilar();
    // ya no lo quieren: el subtítulo deja de hacerle lugar cuando terminó de irse (no se reacomoda mientras se apaga)
    else { clearTimeout(tAcople); tAcople = setTimeout(() => { if (!arriba && !enEscena) acoplar(0); }, 300); }
  }
  function vigilar() {
    clearTimeout(tVigilar);
    tVigilar = setTimeout(() => {
      tVigilar = 0;
      if (!enEscena || !permitido || perdido || arriba) return;
      if (llena(ancla())) subir(); else vigilar();
    }, VIGILAR_MS);
  }
  /** Lo quieren a la vista: si no está arriba, sube (en cuanto el subtítulo se vea). Devuelve si sube recién */
  function aparecer() {
    if (!permitido || perdido) return false;
    enEscena = true;
    if (arriba) { arrancar(); return false; }
    if (llena(ancla())) subir(); else if (saliendo && corriendo) { /* (el bucle lo asoma cuando el subtítulo vuelva) */ } else vigilar();
    return true;
  }
  /** Ya no lo quieren (se quitó el subtítulo): se agacha en el acto, salvo que en este mismo momento llegue otra cosa
   * (la píldora que se apaga y la explicación que la reemplaza) */
  function retirar() {
    clearTimeout(tVigilar);
    anim.callar();
    enEscena = false;
    setTimeout(() => { if (!enEscena && arriba) agachar({ despedida: ultimoCierre }); }, 0);
  }
  function ocultarYa() {
    enEscena = false;
    cancelarEsperas();
    clearTimeout(tVigilar);
    esconder();
    acoplar(0);
  }

  // ── La escena: el gesto de entrada y el sostén ──
  /** Lo de la escena anterior que no sigue: sus esperas, su mirada, lo que señalaba */
  function limpiarEscena() {
    cancelarEsperas();
    anim.mirarA(null);
    objetivoPx = null;
    previsto = null;
    for (const f of documento.querySelectorAll?.('.foco.senalado') || []) f.classList.remove('senalado');
  }
  /** Una vista nueva para la escena (o el cierre, la píldora, la explicación): su programa empieza a correr */
  function empezar(d, e, { evento = 'narrar', nuevo = false } = {}) {
    escenaN++;
    cambiosLugar = 0;
    prog = { n: escenaN, d: d || {}, e, evento, t0: ahora(), fase: 'espera',
      frase0: null, tEncuadre: null, foco: null, tFoco: null, iguales: 0, lugarHecho: false, saludado: false, finFrase0: null };
    // la bienvenida, una vez por recorrido (si se agacha entre escenas y vuelve a subir, no saluda de nuevo)
    if (e.saludoPrimero && d?.rid && saludados.has(d.rid)) { e.saludoPrimero = false; if (d.gesto === 'saludar') e.gesto = 'saludar'; }
    if (e.saludoPrimero && nuevo && d?.rid) saludados.add(d.rid);
    saludoPendiente = e.saludoPrimero && nuevo ? { dur: reducido ? 1 : e.saludoCorto ? SALUDO_CORTO_S : SALUDO_S } : null;
    if (saludoPendiente) prog.fase = 'saludo';
    // lo que apuntaba la escena anterior, si esta apunta a otra cosa (u otro lado), se suelta
    if (APUNTAN.includes(anim.estado().gesto) && (anterior?.objetivo !== e.objetivo || anterior?.lado !== e.lado)) anim.detenerGesto();
    anterior = { capitulo: d?.capitulo, paso: d?.paso, visual: d?.visual, vista: e.vista, lado: e.lado, objetivo: e.objetivo };
    ponerVista(e, { lugarYa: nuevo });
  }
  // lo resaltado (la unión de los .foco), si dejó de moverse (el panel terminó de desplazarse): 2 cuadros iguales
  function focoQuieto() {
    const c = union([...documento.querySelectorAll('.foco')].map(rect));
    if (!c) { prog.foco = null; prog.iguales = 0; return null; }
    const f = prog.foco;
    const t = ahora();
    if (prog.tFoco === null) prog.tFoco = t;
    const igual = f && Math.abs(f.x0 - c.x0) < 1 && Math.abs(f.y0 - c.y0) < 1 && Math.abs(f.y1 - c.y1) < 1;
    prog.iguales = igual ? prog.iguales + 1 : 0;
    if (!igual) prog.tQuieto = t;
    prog.foco = c;
    // quieto dos cuadros, o uno si pasaron 100 ms (con pocos cuadros por segundo); si no se queda quieto, a los 2 s de
    // aparecer señala donde esté
    return prog.iguales >= 2 || (prog.iguales >= 1 && t - prog.tQuieto >= 100) || t - prog.tFoco > FOCO_QUIETO_MS ? c : null;
  }
  /** Cada cuadro: el programa de la escena (espera la primera frase, el lugar y lo resaltado; el gesto; el sostén) */
  function avanzar() {
    const p = prog;
    if (!p || !arriba || saliendo || !eleccion || pausado) return;
    if (anim.estado().entrando) return;
    const t = ahora() - p.t0;
    if (p.fase === 'saludo') {
      if (!p.saludado) return;
      p.fase = 'espera';
      frente = false;
      orientar();
    }
    if (p.fase === 'espera') {
      // ningún gesto de brazos mientras camina, salta o se funde (como mucho 1.2 s)
      if (trans && ahora() - trans.t0 < ESPERA_TRANS_MS) return;
      // el cambio de capítulo: mira el panel un momento antes del gesto
      if (p.e.transicionCapitulo && !p.tCapitulo) {
        p.tCapitulo = ahora();
        const c = leerCajas();
        const pt = c.panel ? { x: (c.panel.x0 + c.panel.x1) / 2, y: c.panel.y0 + 120 } : null;
        if (pt && x !== null) { colocar(); anim.mirarA(alMundo(pt.x, pt.y)); despues(CAPITULO_MS, () => anim.mirarA(null)); }
        return;
      }
      if (p.tCapitulo && ahora() - p.tCapitulo < CAPITULO_MS) return;
      if (p.frase0 === null && t < FRASE0_MS) return;
      if (p.e.objetivo === 'foco') {
        const f = focoQuieto();
        if (!f) {
          // sin lo resaltado a los 1.2 s de la escena (y a los 1.3 s de aplicar lo visual): sigue sin él
          const plazo = Math.max(FOCO_MS, p.tEncuadre !== null ? p.tEncuadre - p.t0 + FOCO_APLICAR_MS : t < 2500 ? Infinity : 0);
          if (p.tFoco === null && t > plazo) sinResaltado();
          return;
        }
      }
      gestoDeEntrada();
      return;
    }
    if (p.fase === 'gesto' && ahora() >= p.tSosten) sostener();
    if (p.fase === 'cierre') contarPuntos();
  }
  /** Lo resaltado no apareció: la regla siguiente, sin él */
  function sinResaltado() {
    const p = prog;
    p.d = { ...p.d, resaltar: null, senal: false };
    const e = elegirVista({ ...p.d, evento: 'narrar' }, contexto());
    e.saludoPrimero = false;
    p.e = e;
    anterior = { ...anterior, vista: e.vista, lado: e.lado, objetivo: e.objetivo };
    p.sinFoco = true;
    ponerVista(e, { lugarYa: true });
  }
  /** El gesto de entrada de la vista, hacia su objetivo */
  function gestoDeEntrada() {
    const p = prog, e = p.e;
    p.fase = 'gesto';
    colocar();
    const c = leerCajas();
    let punto = puntoDe(e, c, { prever: true });
    // señalando: la punta del dedo nunca baja del corte (se apunta un poco más arriba lo justo)
    if (punto && e.vista === 'senala' && c.sub) punto = apuntable(xCuerpo, punto, { p: plan.p, subTop: c.sub.y0, yc: plan.yc, rumbo: anim.estado().rumboBase });
    objetivoPx = punto;
    const g = gestoDe(e);
    frente = !!e.frente && !APUNTAN.includes(g);
    orientar(punto);
    const opciones = {};
    if (punto && APUNTAN.includes(g)) opciones.punto = alMundo(punto.x, punto.y);
    if (g === 'enumerar') { opciones.n = 1; opciones.sostener = true; }
    // el índice se sostiene la primera frase (al menos 2.5 s); los demás, lo que duran
    const sostenido = g === 'senalar' || g === 'presentar';
    if (sostenido) opciones.sostener = true;
    const dur = g ? anim.gesto(g, opciones) : 0;
    const fin = p.finFrase0 ?? (p.frase0 !== null ? p.frase0 + decirS(p.d.textos?.[0]) * 1000 : null);
    p.tSosten = ahora() + (sostenido ? acotar((fin ?? 0) - ahora(), SOSTEN_MS, 6000) : g === 'enumerar' ? Infinity : Math.max(0, (Number.isFinite(dur) ? dur : 0) * 1000 - 350));
    // el dedo llega: lo señalado late; la cabeza vuelve a la sala al rato (la mano sigue)
    if (g === 'senalar' && e.objetivo === 'foco') despues(450, pulso);
    if (APUNTAN.includes(g) && e.objetivo !== 'obra') despues(MIRAR_MS, () => { if (prog === p && p.fase === 'gesto') anim.mirarSala((p.tSosten - ahora()) / 1000 + 0.2); });
    if (e.vista === 'rotulo' && punto) { anim.mirarA(alMundo(punto.x, punto.y)); }
    if (e.lado === 'hoja' && punto) { anim.mirarA(alMundo(punto.x, punto.y)); }
  }
  /** El gesto que hace la vista al empezar: el que pidió el asistente (adaptado a lo que apunta) o el de la vista */
  function gestoDe(e) {
    const g = e.gesto;
    if (e.vista === 'rotulo') return null;   // (el rótulo es la cara: los brazos quedan en la casa)
    if (e.objetivo === 'foco') {
      if (e.lado === 'hoja') return g || 'destacar';
      if (!g || g === 'senalar' || g === 'mostrar_panel') return 'senalar';
      return g;
    }
    if (e.objetivo === 'bloque') return g === 'mostrar_panel' ? 'presentar' : g || 'presentar';
    if (e.objetivo === 'obra' || e.objetivo === 'ficha') return g === 'mirar_maqueta' ? 'indicar' : g || 'presentar';
    return g;
  }
  /** El anillo de lo señalado late (0.9 s) cuando llega el dedo */
  function pulso() {
    const focos = [...(documento.querySelectorAll?.('.foco') || [])];
    for (const f of focos) { f.classList.remove('senalado'); void f.offsetWidth; f.classList.add('senalado'); }
    despues(PULSO_MS, () => { for (const f of focos) f.classList.remove('senalado'); });
  }
  /** El sostén hasta la escena siguiente: la mano baja hacia lo que explica (indicar), mirando a la sala (o a la obra
   * si la presenta); el anfitrión, en la casa (la de hablar si habla) */
  function sostener() {
    const p = prog;
    if (!p) return;
    p.fase = 'sosten';
    frente = false;
    const e = p.e;
    const punto = objetivoPx;
    orientar(punto);
    // el anfitrión, el rótulo y el busto que mira la hoja: a la casa (la de hablar si habla); enumerar sigue con sus dedos
    if (!punto || e.objetivo === 'sala' || e.vista === 'anfitrion' || e.vista === 'rotulo' || e.lado === 'hoja' || anim.estado().gesto === 'enumerar') {
      if (anim.estado().gesto !== 'enumerar') anim.detenerGesto();
      return;
    }
    colocar();
    // la mano baja un poco más que el dedo: lo que está abajo del hombro se apunta con más margen sobre el corte
    const c = e.vista === 'senala' ? leerCajas() : null;
    const pt = c?.sub ? apuntable(xCuerpo, punto, { p: plan.p, subTop: c.sub.y0, yc: plan.yc, rumbo: anim.estado().rumboBase, margen: 30 }) : punto;
    // presentando la obra la mira (mientras la cámara viaja); lo demás, la sala
    anim.gesto('indicar', { punto: alMundo(pt.x, pt.y), sostener: true, mirar: e.objetivo === 'obra' });
  }
  /** Cada frase: la sala al empezar y, después, un vistazo a lo que explica */
  function alEmpezarFrase(k) {
    const p = prog;
    if (!p || p.fase === 'cierre') return;
    if (k === 0) { p.frase0 = ahora(); return; }
    if (p.fase !== 'sosten' || !objetivoPx) return;
    anim.mirarSala(MIRAR_MS / 1000);
    if (p.e.objetivo !== 'obra' && p.e.objetivo !== 'ficha') {
      despues(MIRAR_MS, () => {
        if (prog !== p || x === null) return;
        colocar();
        anim.mirarA(alMundo(objetivoPx.x, objetivoPx.y));
        despues(VISTAZO_MS, () => { if (prog === p) anim.mirarA(null); });
      });
    }
  }

  // ── El cierre: un dedo al empezar cada punto ──
  function contarPuntos() {
    const p = prog, cz = p.cierre;
    if (!cz || cz.t0 === null) return;
    const t = (ahora() - cz.t0) / 1000 * cz.escala;
    while (cz.k < cz.inicios.length && t >= cz.inicios[cz.k]) {
      cz.k++;
      if (cz.k === 1) anim.gesto('contar', { n: 1, sostener: true });
      else anim.gesto('contar', { n: Math.min(3, cz.k), seguir: true });
    }
    // el último se sostiene hasta que termina de hablar
    if (!cz.voz && t > cz.total + 0.6 && anim.estado().gesto === 'contar') { anim.detenerGesto(); p.fase = 'listo'; }
  }

  /** Lo que está haciendo (para el taller, las pruebas y las herramientas con ?qa). `cajas` (lo que se ve de él y de
   * su cabeza, en px de la ventana) y `punta` (la del índice que apunta) se calculan solo si se leen */
  function estado() {
    const r = (v) => (v === null || v === undefined ? null : Math.round(v * 1000) / 1000);
    const a = anim.estado();
    return {
      ...a, enEscena, permitido, corriendo, arriba, saliendo, cuerpoY: r(personaje.cuerpo.position.y),
      lienzo: { x, y, W, H },
      vista: eleccion?.vista ?? null, plano: plan?.plano ?? null, lado: eleccion?.lado ?? null, regla: eleccion?.regla ?? null,
      gestoVista: eleccion?.gesto ?? null, fase: prog?.fase ?? null, frente,
      lugar: xCuerpo === null ? null : { x: Math.round(xCuerpo), cambios: cambiosLugar, razon: ultimoLugar?.razon ?? null,
        costo: ultimoLugar?.costo ?? null, hacia: previsto ? { x: Math.round(previsto.x), y: Math.round(previsto.y) } : null },
      escala: r(plan?.s), pxAlto: r(plan?.p), cx,
      objetivo: objetivoPx ? { x: Math.round(objetivoPx.x), y: Math.round(objetivoPx.y) } : null,
      transicion: ultimaTransicion, fundiendo: trans?.tipo === 'fundido',
      trans: trans ? { tipo: trans.tipo, fase: trans.fase, ms: Math.round(ahora() - trans.t0) } : null,
      circulo: esRotulo() ? { k: Math.round(circ.k * 1000) / 1000, op: Math.round(circ.op * 1000) / 1000, modo: plan.modo, lado: plan.lado } : null,
      acoplado, desfase: Math.round(desfase), recorte, dpr,
      ancla: ultimaAncla ? { left: Math.round(ultimaAncla.left), top: Math.round(ultimaAncla.top), right: Math.round(ultimaAncla.right) } : null,
      redimensiones, msCuadro: r(msCuadro), cuadros,
      // la luz (la de la maqueta, si avisó) y el detalle de la cara
      luz: { lado: r(luces.lado), luz: `#${luces.luz.getHexString()}`, luzI: r(luces.luzI), hemiI: r(luces.hemiI),
        relleno: `#${luces.relleno.getHexString()}`, rellenoI: r(luces.rellenoI), contraI: r(luces.contraI),
        tinte: personaje.tinte ? `#${personaje.tinte.value.getHexString()}` : null, cambiando: !!lucesDesde },
      detalle: { pxCabeza, nivel: r(nivel) },
      escena: ultimaEscena ? { n: ultimaEscena.n ?? null, tipo: ultimaEscena.tipo ?? null, cambio: ultimaEscena.cambio ?? null } : null,
      avisos: Object.keys(avisos).filter((k) => avisos[k] !== null),
      prog: prog ? { t: Math.round(ahora() - prog.t0), frase0: prog.frase0 === null ? null : Math.round(prog.frase0 - prog.t0),
        encuadre: prog.tEncuadre === null ? null : Math.round(prog.tEncuadre - prog.t0), iguales: prog.iguales, sinFoco: !!prog.sinFoco,
        sosten: prog.tSosten ? Math.round(prog.tSosten - prog.t0) : null, dedos: prog.cierre?.k ?? null } : null,
      get cajas() { return { figura: cajaDe(personaje.grupo), cabeza: cajaDe(personaje.craneo) }; },
      get punta() { return puntaPx(); },
      get apunta() {
        if (!ultimoMundo || x === null) return null;
        camara.updateMatrixWorld();
        const v = ultimoMundo.clone().project(camara);
        const w = aVentana(((v.x + 1) / 2) * W, ((1 - v.y) / 2) * H);
        return { x: Math.round(w.x), y: Math.round(w.y) };
      },
    };
  }

  /** Una vista para un evento que no es una escena (el cierre, la píldora, la explicación) */
  function evento(ev, d = null) {
    ultimoEvento = ev;
    limpiarEscena();
    pausado = false;
    const nuevo = !arriba && permitido && !perdido;
    const e = elegirVista({ ...(d || {}), evento: ev }, contexto({ nuevo }));
    empezar(d || ultimaEscena || {}, e, { evento: ev, nuevo });
    prog.fase = 'listo';
    aparecer();
    return { nuevo, e };
  }

  // ── Lo que le avisa mando.js ──
  const api = {
    /** Una escena del recorrido (la n): elige la vista con lo que se explica (docs/presentador.md), se ubica, se
     * orienta y arma el gesto de entrada, que arranca con la primera frase */
    narrar(d = {}) {
      if (!permitido) return;
      d = d || {};
      ultimaEscena = d;
      ultimoEvento = 'narrar';
      ultimoCierre = false;
      limpiarEscena();
      pausado = false;
      if (anim.estado().gesto === 'enumerar' || anim.estado().gesto === 'escuchar') anim.detenerGesto();
      const nuevo = !arriba && !perdido;
      const e = elegirVista({ ...d, evento: 'narrar' }, contexto({ nuevo }));
      empezar(d, e, { nuevo });
      aparecer();
    },
    /** Empieza la frase k: con voz habla hasta `habla(false)`; sin voz, lo que tardaría en decirla */
    frase(k, { voz = false, texto = '' } = {}) {
      if (!permitido || !enEscena) return;
      pausado = false;
      if (anim.estado().gesto === 'escuchar') { anim.detenerGesto(); despues(400, () => { if (prog?.fase === 'sosten') sostener(); }); }
      // `enumerar`: un dedo más con cada frase
      if (k > 0 && anim.estado().gesto === 'enumerar') anim.gesto('enumerar', { n: Math.min(3, k + 1), seguir: true });
      alEmpezarFrase(k);
      if (prog && k === 0 && !voz) prog.finFrase0 = ahora() + decirS(texto) * 1000;
      anim.hablar(voz ? true : decirS(texto));
    },
    /** La voz empieza (true) o termina (false) de decir algo */
    habla(v) {
      if (!permitido || !enEscena) return;
      if (v) anim.hablar(true); else anim.callar();
      const cz = prog?.cierre;
      if (cz?.voz) {
        if (v && cz.t0 === null) cz.t0 = ahora();
        if (!v && cz.t0 !== null) { despues(600, () => { if (anim.estado().gesto === 'contar') anim.detenerGesto(); }); }
      }
      if (prog && !v && prog.frase0 !== null && prog.finFrase0 === null) prog.finFrase0 = ahora();
    },
    pausa(v) {
      if (!permitido || !enEscena) return;
      pausado = !!v;
      if (v) {
        anim.callar();
        frente = true;
        orientar();
        anim.gesto('escuchar', { sostener: true });
      } else {
        frente = false;
        orientar();
        if (anim.estado().gesto === 'escuchar') {
          anim.detenerGesto();
          if (prog?.fase === 'sosten') despues(400, sostener);
        }
      }
    },
    /** El cierre: con puntos, «En resumen» (los cuenta con los dedos, uno al empezar cada punto); sin ellos,
     * «¿Preguntas?» (invita y después espera, asintiendo) */
    cierre(puntos, { voz = false } = {}) {
      if (!permitido) return;
      const con = Array.isArray(puntos) && puntos.length > 0;
      evento(con ? 'cierre' : 'preguntas');
      ultimoCierre = true;
      if (con) {
        const { inicios, total } = tiemposCierre(puntos);
        prog.cierre = { inicios, total, k: 0, voz, escala: 1, t0: voz ? null : ahora() };
        prog.fase = 'cierre';
        if (!voz) anim.hablar(decirS(`En resumen. ${puntos.join('. ')}`));
        else despues(FRASE0_MS * 2, () => { const cz = prog?.cierre; if (cz && cz.t0 === null) cz.t0 = ahora(); });
      } else {
        anim.callar();
        anim.gesto('invitar', { sostener: true });
        // a los 4.5 s pasa a la casa, esperando; asiente cada tanto
        const p = prog;
        despues(4500, () => {
          if (prog !== p) return;
          if (anim.estado().gesto === 'invitar') anim.detenerGesto();
          const asentir = () => { if (prog !== p) return; if (!anim.estado().gesto) anim.gesto('asentir'); despues(3500, asentir); };
          despues(1200, asentir);
        });
      }
    },
    /** El asistente prepara la explicación (la píldora): piensa */
    preparando(v) {
      if (!permitido) return;
      if (v) { ultimoCierre = false; evento('preparando'); anim.gesto('pensar', { sostener: true }); }
      else if (anim.estado().gesto === 'pensar') { anim.detenerGesto(); retirar(); }
    },
    /** Una explicación suelta (sin recorrido) en el subtítulo */
    explicar(texto) {
      if (!permitido) return;
      ultimoCierre = false;
      const { nuevo } = evento('explicar');
      // (recién sube: cuando termina de subir, después de que el subtítulo aparece)
      despues(nuevo ? 1100 : 0, () => { anim.gesto('explicar'); anim.hablar(decirS(texto)); });
    },
    /** El subtítulo se quitó: se agacha detrás de él (después del cierre, despidiéndose) */
    quitar() { retirar(); },
    /** La preferencia del panel: false lo oculta en el acto */
    mostrar(v) {
      permitido = v !== false;
      if (!permitido) ocultarYa();
      else if (subtitulo()?.classList.contains('visible')) aparecer();
    },
    // Los avisos de lo que pasa en la escena (mando.js)
    /** Dónde quedará la obra encuadrada y sus rótulos: el lugar se vuelve a puntuar (si todavía no cambió) */
    encuadre(c) {
      avisos.encuadre = c ?? null;
      const p = prog;
      if (!p || !c || (c.n != null && p.d.n != null && c.n !== p.d.n)) return;
      if (p.tEncuadre === null) p.tEncuadre = ahora();
      if (!p.lugarHecho && arriba) { p.lugarHecho = true; decidirLugar(); }
      else if (p.fase === 'espera' && cambiosLugar === 0) decidirLugar();
    },
    atlas(a) { avisos.atlas = a ?? null; },
    simulacion(s) { avisos.simulacion = s ?? null; },
    /** La luz de la maqueta (la hora y el lado del sol): la suya la sigue, en 0.6 s */
    ambiente(l) { avisos.ambiente = l ?? null; seguirLuz(); },
    /** Dónde queda la mano que señala ({lado, y}) para que el panel lleve lo resaltado a esa altura; null: ninguna */
    alturaMano() {
      if (!eleccion || eleccion.vista !== 'senala' || !plan || plan.chica) return null;
      if (eleccion.lado !== 'panel' && eleccion.lado !== 'ficha') return null;
      const top = (ancla() || ultimaAncla)?.top;
      return Number.isFinite(top) ? { lado: eleccion.lado, y: Math.round(alturaHombro(top, plan)) } : null;
    },
    // para el taller y las pruebas
    gesto: (nombre, o) => anim.gesto(nombre, o),
    senalarA(objetivo, { presentar = false, gesto = null } = {}) {
      const p = objetivo && typeof objetivo.x === 'number' ? objetivo : centroDe(objetivo);
      if (!p || W === 0) return false;
      colocar();
      anim.gesto(gesto || (presentar ? 'presentar' : 'senalar'), { punto: alMundo(p.x, p.y), dur: 3 });
      return true;
    },
    estado,
    soltar() {
      ocultarYa();
      clearTimeout(tVigilar);
      clearTimeout(tFundido);
      clearTimeout(tAcople);
      observador?.disconnect();
      ventana.removeEventListener?.('resize', alCambiarVentana);
      lienzo.remove();
      personaje.liberar();
      renderer.dispose();
      if (ventana.__qaPresentador === api) delete ventana.__qaPresentador;
    },
  };

  // «Solo 3D», la ficha o el atlas que se abren o se cierran fuera de una escena: se vuelve a elegir la vista con lo
  // último que se explicó (sin gesto de entrada: el sostén hacia lo nuevo)
  let tReelegir = 0;
  function reelegir() {
    clearTimeout(tReelegir);
    tReelegir = setTimeout(() => {
      if (!prog || !arriba || !ultimoEvento || ahora() - prog.t0 < 1500) return;
      const e = elegirVista({ ...(ultimaEscena || {}), evento: ultimoEvento }, contexto());
      if (e.vista === eleccion?.vista && e.lado === eleccion?.lado) return;
      e.saludoPrimero = false;
      prog.e = e;
      ponerVista(e, { lugarYa: true });
      if (prog.fase === 'sosten' || prog.fase === 'gesto') { objetivoPx = puntoDe(e, leerCajas()); sostener(); }
    }, 150);
  }
  let observador = null;
  try {
    const el = pres();
    if (el && typeof ventana.MutationObserver === 'function') {
      let antesClases = el.className;
      observador = new ventana.MutationObserver(() => {
        const ahoraClases = el.className;
        const mira = (k) => antesClases.includes(k) !== ahoraClases.includes(k);
        if (mira('sin-panel') || mira('con-detalle') || mira('con-inmersion')) reelegir();
        antesClases = ahoraClases;
      });
      observador.observe(el, { attributes: true, attributeFilter: ['class'] });
    }
  } catch { observador = null; }
  // la ventana cambió de tamaño: el plan nuevo lo toma colocar() en el cuadro siguiente; acá, solo volver a elegir
  function alCambiarVentana() { if (prog) reelegir(); }
  ventana.addEventListener?.('resize', alCambiarVentana);

  // las herramientas de verificación (como __qaPropuesta en escena.js): solo con ?qa en la dirección
  try {
    if (new URLSearchParams(ventana.location?.search || '').has('qa')) {
      ventana.__qaPresentador = api;
      // rastrear(true) empieza a anotar cada cuadro; rastrear(false) devuelve lo anotado y deja de anotar
      api.rastrear = (on) => { if (on) { rastro = []; return true; } const r = rastro; rastro = null; return r; };
    }
  } catch { /* nada */ }
  return api;
}
