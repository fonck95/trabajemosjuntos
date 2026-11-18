// El presentador en la presentación (web/propuesta.html dentro del panel): el personaje de personaje.js, movido por
// animador.js, de pie sobre el subtítulo, que explica lo que el asistente narra (docs/presentador.md).
//
// * Un <canvas> propio, transparente, encima de la maqueta y debajo del subtítulo (z-index 8: los pies quedan detrás
//   del borde de arriba del subtítulo, como detrás de un atril), sin eventos de puntero: no tapa nada que se toque. Su
//   propio WebGLRenderer, chico, que solo dibuja mientras el presentador está a la vista: la maqueta sigue dibujando
//   bajo demanda, como siempre.
// * Dónde se para: en pantalla grande, en el extremo izquierdo del subtítulo (al lado del panel, al que señala); en la
//   chica, en el derecho y más chico. Sigue al subtítulo cuadro a cuadro (se mueve con «Solo 3D», con la hoja del
//   celular) y, si no hay subtítulo, se queda donde estaba.
// * Lo que hace con el recorrido narrado (mando.js le avisa cada cosa): sube detrás del subtítulo y saluda en la
//   primera escena; en cada escena señala lo que se resalta (el elemento .foco del panel, la leyenda o la ficha) o
//   presenta con la palma la obra en la maqueta; habla mientras suena cada frase (con la voz, de `habla: true` a
//   `habla: false`; sin voz, lo que tardaría en decirla); escucha en pausa; cuenta con los dedos los puntos del
//   resumen; abre los brazos en «¿Preguntas?»; piensa mientras el asistente prepara la explicación; y se despide y
//   baja cuando la narración se quita. Una explicación suelta (`explicar`) también la dice.
// * `mostrar(false)` (el botón «Presentador» del panel, `vista {presentador: false}`) lo oculta en el acto y lo deja
//   quieto hasta `mostrar(true)`.
// * prefers-reduced-motion: entra y sale sin animación, sin saltos ni vaivenes del cuerpo.
// * Si el navegador no puede crear el contexto WebGL (o lo pierde), no hay presentador y nada más cambia.
import * as THREE from 'three';
import { crearPersonaje } from './personaje.js';
import { crearAnimador } from './animador.js';

const FOV = 17;           // poca perspectiva: casi un dibujo plano
const HOLGURA = 1.1;      // lo que se ve de alto, por la altura del personaje (los brazos arriba caben)
const ASPECTO = 0.95;
const HUNDIDO = 0.05;      // la parte de abajo del lienzo que queda detrás del subtítulo (los pies)
const DECIR_S = 0.058;     // lo que tarda en decirse un carácter sin voz (a unos 17 por segundo)
const SALIR_TRAS_MS = 700; // un subtítulo que se quita y vuelve enseguida (un cambio de paso) no lo hace bajar
const FUERA_MS = 4000;     // lo más que tarda en despedirse y bajar

/** La duración de decir `texto` sin voz, en segundos. */
export const decirS = (texto) => Math.min(16, Math.max(1.2, [...String(texto || '')].length * DECIR_S));

export function crearPresentador({ ventana = globalThis.window, documento = globalThis.document } = {}) {
  if (!ventana || !documento?.createElement) return null;
  const reducido = !!ventana.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches;
  const lienzo = documento.createElement('canvas');
  lienzo.className = 'presentador';
  lienzo.setAttribute('aria-hidden', 'true');
  lienzo.hidden = true;
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas: lienzo, alpha: true, antialias: true, stencil: true,
      powerPreference: 'low-power', premultipliedAlpha: true });
  } catch { return null; }
  documento.body.append(lienzo);
  renderer.setClearColor(0x000000, 0);
  const escena = new THREE.Scene();
  escena.add(new THREE.HemisphereLight(0xffffff, 0x8a7a70, 1.15));
  const luz = new THREE.DirectionalLight(0xffffff, 1.9);
  luz.position.set(-2, 3, 4);
  escena.add(luz);
  // una luz suave de frente: la cara (su relieve, los pliegues de la sonrisa) se lee sin sombras duras
  const relleno = new THREE.DirectionalLight(0xfff1e6, 0.7);
  relleno.position.set(1.5, 0.6, 4);
  escena.add(relleno);
  const camara = new THREE.PerspectiveCamera(FOV, ASPECTO, 0.1, 50);
  const personaje = crearPersonaje({ documento });
  escena.add(personaje.grupo);
  // el encuadre: los pies abajo del lienzo y lo que mide, con su holgura, a lo alto
  const altoVista = personaje.medidas.alto * HOLGURA;
  camara.position.set(0, altoVista / 2, altoVista / 2 / Math.tan((FOV * Math.PI) / 360));
  camara.lookAt(0, altoVista / 2, 0);
  const anim = crearAnimador(personaje, { reducido });
  anim.camara = camara;
  personaje.grupo.visible = false;

  let permitido = true;     // la preferencia del panel («Presentador»)
  let enEscena = false;     // subió (o está subiendo) y no se fue
  let saliendo = false;
  let corriendo = false, cuadro = 0, antes = 0;
  let tSalir = 0, tSenal = 0;
  let W = 0, H = 0, x = null, y = null, dpr = 1;
  let perdido = false;

  lienzo.addEventListener('webglcontextlost', (e) => { e.preventDefault(); perdido = true; detener(); lienzo.hidden = true; });

  // ── Dónde va ──
  const chica = () => (ventana.innerWidth || 0) <= 1080;
  function ancla() {
    const sub = documento.querySelector('.subtitulo.visible');
    const r = sub?.getBoundingClientRect?.();
    return r && r.width > 0 ? r : null;
  }
  let ultimaAncla = null;
  function colocar(inmediato = false) {
    const VW = ventana.innerWidth || 800, VH = ventana.innerHeight || 600;
    const h = Math.round(chica() ? Math.min(150, Math.max(96, VH * 0.17)) : Math.min(330, Math.max(170, VH * 0.3)));
    const w = Math.round(h * ASPECTO);
    const r = ancla() || ultimaAncla;
    if (r) ultimaAncla = r;
    let cx, abajo;
    if (r) {
      cx = chica() ? r.right - w * 0.2 : r.left + w * 0.2;
      abajo = r.top + h * HUNDIDO;
    } else {
      cx = chica() ? VW - w * 0.4 : VW * 0.42;
      abajo = VH - 96;
    }
    cx = Math.min(VW - w * 0.28, Math.max(w * 0.28, cx));
    const tx = cx - w / 2, ty = abajo - h;
    if (x === null || inmediato) { x = tx; y = ty; }
    else { x += (tx - x) * 0.18; y += (ty - y) * 0.18; }
    if (w !== W || h !== H || dpr !== Math.min(2, ventana.devicePixelRatio || 1)) {
      W = w; H = h;
      dpr = Math.min(2, ventana.devicePixelRatio || 1);
      renderer.setPixelRatio(dpr);
      renderer.setSize(W, H, false);
      lienzo.style.width = `${W}px`;
      lienzo.style.height = `${H}px`;
      camara.aspect = W / H;
      camara.updateProjectionMatrix();
      personaje.contorno.resolucion.value.set(W * dpr, H * dpr);
      personaje.contorno.grosor.value = (chica() ? 1.1 : 1.5) * dpr;
    }
    lienzo.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
  }

  /** Un punto de la pantalla (px de la ventana) en el mundo del presentador: sobre el plano z = 0.6, delante de él. */
  function alMundo(px, py) {
    const ndc = new THREE.Vector3(((px - x) / W) * 2 - 1, -((py - y) / H) * 2 + 1, 0.5).unproject(camara);
    const d = ndc.sub(camara.position).normalize();
    const t = (0.6 - camara.position.z) / d.z;
    return camara.position.clone().addScaledVector(d, t);
  }
  /** El centro de la maqueta a la vista: lo que queda entre el panel (si está), la barra y el subtítulo */
  function centroMaqueta() {
    const VW = ventana.innerWidth || 800, VH = ventana.innerHeight || 600;
    let x0 = 0;
    const panel = documento.querySelector('.panel'), pres = documento.querySelector('#pres');
    if (panel && !pres?.classList.contains('sin-panel')) {
      const p = panel.getBoundingClientRect();
      if (p.width < VW * 0.7) x0 = p.right;
    }
    const barra = documento.querySelector('.barra')?.getBoundingClientRect();
    const r = ancla();
    return { x: (x0 + VW) / 2, y: ((barra?.bottom || 0) + (r?.top || VH)) / 2 };
  }
  function centroDe(el) {
    const r = el?.getBoundingClientRect?.();
    return r && r.width > 0 ? { x: r.left + r.width / 2, y: r.top + r.height / 2 } : null;
  }

  // ── El cuadro ──
  function bucle(ahora) {
    cuadro = 0;
    if (!corriendo) return;
    const dt = antes ? (ahora - antes) / 1000 : 1 / 60;
    antes = ahora;
    anim.actualizar(dt);
    colocar();
    renderer.render(escena, camara);
    if (!personaje.grupo.visible && !saliendo) { detener(); lienzo.hidden = true; return; }
    cuadro = ventana.requestAnimationFrame(bucle);
  }
  function arrancar() {
    if (corriendo || perdido) return;
    corriendo = true;
    antes = 0;
    lienzo.hidden = false;
    colocar(true);
    cuadro = ventana.requestAnimationFrame(bucle);
  }
  function detener() {
    corriendo = false;
    if (cuadro) ventana.cancelAnimationFrame(cuadro);
    cuadro = 0;
  }

  // ── Lo básico ──
  function aparecer({ saludo = false } = {}) {
    clearTimeout(tSalir);
    if (!permitido || perdido) return false;
    if (!enEscena || saliendo) {
      enEscena = true;
      saliendo = false;
      arrancar();
      anim.entrar(() => { if (saludo) anim.gesto('saludar'); });
      if (saludo && reducido) anim.gesto('saludar');
      return true;
    }
    arrancar();
    return false;
  }
  function retirar({ ya = false } = {}) {
    clearTimeout(tSalir);
    clearTimeout(tSenal);
    anim.callar();
    if (!enEscena) return;
    const irse = () => {
      if (!enEscena) return;
      enEscena = false;
      saliendo = true;
      const bajar = () => anim.salir(() => { saliendo = false; });
      if (reducido || ya) { anim.detenerGesto(); bajar(); } else anim.gesto('despedirse', { alTerminar: () => { if (saliendo) bajar(); } });
      // con muy pocos cuadros por segundo (o la pestaña oculta) la despedida puede no terminar: se va igual
      tSalir = setTimeout(() => { if (!enEscena && saliendo) ocultarYa(); }, FUERA_MS);
    };
    if (ya) irse(); else tSalir = setTimeout(irse, SALIR_TRAS_MS);
  }
  function ocultarYa() {
    clearTimeout(tSalir);
    clearTimeout(tSenal);
    enEscena = false;
    saliendo = false;
    anim.callar();
    anim.detenerGesto();
    personaje.grupo.visible = false;
    detener();
    lienzo.hidden = true;
  }
  function senalarA(objetivo, { presentar = false, gesto = null } = {}) {
    const p = objetivo && typeof objetivo.x === 'number' ? objetivo : centroDe(objetivo);
    if (!p || W === 0) return false;
    colocar(true);
    anim.gesto(gesto || (presentar ? 'presentar' : 'senalar'), { punto: alMundo(p.x, p.y), dur: 3 });
    return true;
  }
  /** El centro del panel de la presentación (su texto y sus cifras), o null si está oculto («Solo 3D») */
  function centroPanel() {
    const panel = documento.querySelector('.panel'), pres = documento.querySelector('#pres');
    if (!panel || pres?.classList.contains('sin-panel')) return null;
    const r = panel.getBoundingClientRect();
    return r.width > 0 ? { x: r.left + r.width * 0.6, y: r.top + Math.min(r.height, 420) * 0.45 } : null;
  }
  let enumerando = 0;   // `enumerar`: cuántas frases tiene el paso (un dedo por cada una)
  /** El gesto que pidió el asistente para el paso (`GESTOS` de app/recorrido.py) */
  function hacerGesto(nombre, { senal = false, frases = 1 } = {}) {
    enumerando = 0;
    const foco = documento.querySelector('.foco');
    if (nombre === 'senalar') return (senal && foco && senalarA(foco)) || senalarA(centroMaqueta());
    if (nombre === 'presentar') return senalarA(centroMaqueta(), { presentar: true });
    if (nombre === 'mostrar_panel') {
      const enPanel = foco && documento.querySelector('.panel')?.contains(foco) ? foco : null;
      return (enPanel && senalarA(enPanel)) || senalarA(centroPanel() || centroMaqueta());
    }
    if (nombre === 'mirar_maqueta') return senalarA(centroMaqueta(), { gesto: 'mirar_maqueta' });
    if (nombre === 'enumerar') { enumerando = Math.max(1, Math.min(3, frases)); return anim.gesto('enumerar', { n: 1, sostener: true }); }
    return anim.gesto(nombre);
  }

  // ── Lo que le avisa mando.js ──
  return {
    /** Una escena del recorrido (la n): `senal` si resalta algo, `obra` si la cámara va a una obra o a un modelo */
    narrar({ n = 1, senal = false, obra = false, gesto = null, frases = 1 } = {}) {
      if (!permitido) return;
      if (anim.estado().gesto === 'enumerar') anim.detenerGesto();
      enumerando = 0;
      const nuevo = aparecer({ saludo: n === 1 && (!gesto || gesto === 'saludar') });
      clearTimeout(tSenal);
      // el gesto que pidió el asistente (si es saludar al subir, ya lo hace la entrada)
      if (gesto) {
        if (gesto === 'saludar' && nuevo) return;
        tSenal = setTimeout(() => hacerGesto(gesto, { senal, frases }), nuevo ? 950 : 450);
        return;
      }
      if (n === 1 && nuevo) return;
      // el resaltado aparece (y el panel se desplaza hasta él) un momento después de la escena
      tSenal = setTimeout(() => {
        const foco = senal ? documento.querySelector('.foco') : null;
        if (foco && senalarA(foco)) return;
        if (obra || senal || n % 2 === 0) senalarA(centroMaqueta(), { presentar: true });
        else anim.gesto('explicar');
      }, nuevo ? 950 : 450);
    },
    /** Empieza la frase k: con voz habla hasta `habla(false)`; sin voz, lo que tardaría en decirla */
    frase(k, { voz = false, texto = '' } = {}) {
      if (!permitido || !enEscena) return;
      if (anim.estado().gesto === 'escuchar') anim.detenerGesto();
      // `enumerar`: un dedo más con cada frase
      if (enumerando && k > 0 && anim.estado().gesto === 'enumerar') anim.gesto('enumerar', { n: Math.min(3, k + 1), seguir: true });
      anim.hablar(voz ? true : decirS(texto));
    },
    /** La voz empieza (true) o termina (false) de decir algo */
    habla(v) {
      if (!permitido || !enEscena) return;
      if (v) anim.hablar(true); else anim.callar();
    },
    pausa(v) {
      if (!permitido || !enEscena) return;
      if (v) { anim.callar(); anim.gesto('escuchar', { sostener: true }); }
      else if (anim.estado().gesto === 'escuchar') anim.detenerGesto();
    },
    /** El cierre: con puntos, «En resumen» (los cuenta con los dedos); sin ellos, «¿Preguntas?» */
    cierre(puntos, { voz = false } = {}) {
      if (!permitido) return;
      aparecer();
      clearTimeout(tSenal);
      if (Array.isArray(puntos) && puntos.length) {
        anim.gesto('contar', { n: puntos.length });
        if (!voz) anim.hablar(decirS(`En resumen. ${puntos.join('. ')}`));
      } else {
        anim.callar();
        anim.gesto('invitar', { sostener: true });
      }
    },
    /** El asistente prepara la explicación (la píldora): piensa */
    preparando(v) {
      if (!permitido) return;
      if (v) { aparecer(); anim.gesto('pensar', { sostener: true }); }
      else if (anim.estado().gesto === 'pensar') { anim.detenerGesto(); retirar(); }
    },
    /** Una explicación suelta (sin recorrido) en el subtítulo */
    explicar(texto) {
      if (!permitido) return;
      const nuevo = aparecer();
      clearTimeout(tSenal);
      tSenal = setTimeout(() => { anim.gesto('explicar'); anim.hablar(decirS(texto)); }, nuevo ? 850 : 0);
    },
    /** El subtítulo se quitó: se despide y baja (si no vuelve enseguida) */
    quitar() { retirar(); },
    /** La preferencia del panel: false lo oculta en el acto */
    mostrar(v) {
      permitido = v !== false;
      if (!permitido) ocultarYa();
      else if (documento.querySelector('.subtitulo.visible')) aparecer();
    },
    // para el taller y las pruebas
    gesto: (nombre, o) => anim.gesto(nombre, o),
    senalarA,
    estado: () => ({ ...anim.estado(), enEscena, permitido, corriendo, lienzo: { x, y, W, H } }),
    soltar() {
      ocultarYa();
      lienzo.remove();
      personaje.liberar();
      renderer.dispose();
    },
  };
}
