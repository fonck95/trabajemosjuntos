// El presentador en la presentación (web/propuesta.html dentro del panel): el personaje de personaje.js, movido por
// animador.js, detrás del subtítulo como detrás de un atril, que explica lo que el asistente narra (docs/presentador.md).
//
// * Un <canvas> propio, transparente, dentro de #pres justo antes del panel: con el mismo z-index (8), el panel y la
//   ficha (después en el árbol) quedan encima de él; la leyenda, el HUD (7) y el atlas (6), debajo; el subtítulo (9),
//   encima. Sin eventos de puntero: no tapa nada que se toque. Su propio WebGLRenderer, chico, que solo dibuja mientras
//   el presentador está a la vista: la maqueta sigue dibujando bajo demanda, como siempre.
// * El encuadre es por PLANOS (entero, americano, medio): una ventana vertical del personaje y la altura a la que lo
//   corta el borde de arriba del subtítulo («el atril»). La cámara se calcula en cada cuadro con la escala (px por
//   unidad), el ancla del mundo (el corte) y dónde cae ese ancla en el lienzo; el tamaño del lienzo (`setSize`) solo
//   cambia con la vista o la ventana. Lo que queda debajo del corte no se ve nunca (clip-path: el subtítulo es vidrio).
// * Dónde se para (por ahora una sola vista): en pantalla grande, de la cadera para arriba (americano) en el extremo
//   izquierdo del subtítulo, al lado del panel; en la chica, de la cintura para arriba (busto), en el derecho. La `y`
//   sigue al subtítulo cuadro a cuadro (la hoja del celular, «Solo 3D»); la `x` no: se elige con cada escena (se queda
//   donde está si sigue sirviendo) y solo cambia si deja de servir.
// * Lo que hace con el recorrido narrado (mando.js le avisa cada cosa): sube detrás del subtítulo y saluda en la
//   primera escena; en cada escena señala lo que se resalta (el elemento .foco del panel, la leyenda o la ficha) o
//   presenta con la palma la obra en la maqueta; habla mientras suena cada frase (con la voz, de `habla: true` a
//   `habla: false`; sin voz, lo que tardaría en decirla); escucha en pausa; cuenta con los dedos los puntos del
//   resumen; abre los brazos en «¿Preguntas?»; piensa mientras el asistente prepara la explicación. Una explicación
//   suelta (`explicar`) también la dice.
// * Nunca queda a la vista sin el subtítulo: si el subtítulo se va (se quita la explicación, la hoja grande del celular
//   lo tapa) se agacha en el acto detrás de la línea donde estaba (después del cierre, despidiéndose) y, si vuelve, se
//   asoma de nuevo.
// * `mostrar(false)` (el botón «Presentador» del panel, `vista {presentador: false}`) lo oculta en el acto y lo deja
//   quieto hasta `mostrar(true)`.
// * prefers-reduced-motion: entra y sale sin animación, sin saltos ni vaivenes del cuerpo.
// * Si el navegador no puede crear el contexto WebGL (o lo pierde), no hay presentador y nada más cambia.
// * Con ?qa en la dirección de la página: `window.__qaPresentador` (estado, cajas proyectadas, msCuadro) para medirlo.
import * as THREE from 'three';
import { crearPersonaje } from './personaje.js';
import { crearAnimador } from './animador.js';

const FOV = 17;           // poca perspectiva: casi un dibujo plano
const TAN = Math.tan((FOV * Math.PI) / 360);
const DECIR_S = 0.058;     // lo que tarda en decirse un carácter sin voz (a unos 17 por segundo)
// lo más que tarda en agacharse y desaparecer: la animación dura 0.6 s, pero con muy pocos cuadros por segundo (cada
// cuadro avanza a lo sumo 0.25 s) tardaría más, y nunca debe quedar a la vista sin el subtítulo
const FUERA_MS = 750;
const VIGILAR_MS = 80;     // agachado esperando que vuelva el subtítulo: cada cuánto lo mira (sin dibujar)
const FUNDIDO_MS = 150;    // cambiar de lugar: se funde, se mueve y vuelve (propuesta.html: .presentador.fundido)

// Los planos: la ventana del personaje que se ve [yb, ya] y la altura del corte yc (el borde de arriba del subtítulo),
// en fracciones de su alto; `ancho`, el del lienzo por pxAlto (lo que mediría el personaje entero en la pantalla).
// Lo que queda bajo el corte (yc − yb) está en el lienzo pero no se ve (clip-path).
const PLANOS = {
  entero: { yb: 0, ya: 1.1, yc: 0.05, ancho: 1.05 },        // los pies apenas detrás del subtítulo
  americano: { yb: 0.26, ya: 1.1, yc: 0.37, ancho: 1.1 },   // de la cadera para arriba: el subtítulo es el atril
  medio: { yb: 0.4, ya: 1.08, yc: 0.46, ancho: 1.2 },       // de la cintura para arriba
};
const acotar = (v, a, b) => Math.min(b, Math.max(a, v));

/** La duración de decir `texto` sin voz, en segundos. */
export const decirS = (texto) => Math.min(16, Math.max(1.2, [...String(texto || '')].length * DECIR_S));

export function crearPresentador({ ventana = globalThis.window, documento = globalThis.document } = {}) {
  if (!ventana || !documento?.createElement) return null;
  const reducido = !!ventana.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches;
  const reloj = ventana.performance || globalThis.performance || Date;
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
  escena.add(new THREE.HemisphereLight(0xffffff, 0x8a7a70, 1.15));
  const luz = new THREE.DirectionalLight(0xffffff, 1.9);
  luz.position.set(-2, 3, 4);
  escena.add(luz);
  // una luz suave de frente: la cara (su relieve, los pliegues de la sonrisa) se lee sin sombras duras
  const relleno = new THREE.DirectionalLight(0xfff1e6, 0.7);
  relleno.position.set(1.5, 0.6, 4);
  escena.add(relleno);
  // la cámara mira siempre de frente (−z, sin girar): solo se mueve, cuadro a cuadro (ver `colocar`)
  const camara = new THREE.PerspectiveCamera(FOV, 1, 0.1, 50);
  const personaje = crearPersonaje({ documento });
  const A = personaje.medidas.alto;
  escena.add(personaje.grupo);
  const anim = crearAnimador(personaje, { reducido });
  anim.camara = camara;
  personaje.grupo.visible = false;

  let permitido = true;     // la preferencia del panel («Presentador»)
  let enEscena = false;     // lo quieren a la vista: una escena, el cierre, la píldora o una explicación (sin `quitar`)
  let arriba = false;       // subió (o está subiendo) y no se agachó
  let saliendo = false;     // agachándose (anim.salir)
  let saludoPendiente = false, ultimoCierre = false;
  let corriendo = false, cuadro = 0, antes = 0;
  let tSenal = 0, tFuera = 0, tVigilar = 0, tFundido = 0;
  let perdido = false;
  // el plan (la vista y su tamaño), el lugar y el lienzo
  let plan = null;
  let W = 0, H = 0, dpr = 1, redimensiones = 0;
  let x = null, y = null, recorte = -1;     // el lienzo en la ventana (px) y lo que se le corta abajo
  let xCuerpo = null;                        // dónde está parado: la x del cuerpo en la ventana
  let relugar = true, fundiendo = false, destinoX = null, recienSubido = false;
  let ultimaAncla = null, anclaCuadro = null;
  const tiempos = [];        // lo que tardó renderer.render en los últimos cuadros (sin los primeros: compila)
  let msCuadro = null, cuadros = 0;
  // lo último que avisó mando.js (las etapas siguientes lo usan para elegir la vista)
  let ultimaEscena = null;
  const avisos = { encuadre: null, atlas: null, simulacion: null, ambiente: null };

  lienzo.addEventListener('webglcontextlost', (e) => { e.preventDefault(); perdido = true; detener(); lienzo.hidden = true; });

  // ── Dónde va ──
  let subEl = null;
  const subtitulo = () => (subEl?.isConnected ? subEl : (subEl = documento.querySelector('.subtitulo')));
  /** La caja del subtítulo, solo si de verdad se ve (con .visible y su estilo a la vista: en el celular, con la hoja
   * grande, sigue con .visible pero oculto), o null */
  function ancla() {
    const s = subtitulo();
    if (!s?.classList?.contains('visible')) return null;
    const cs = ventana.getComputedStyle?.(s);
    if (cs && (cs.visibility !== 'visible' || Number(cs.opacity) <= 0.05)) return null;
    const r = s.getBoundingClientRect?.();
    return r && r.width > 0 ? { left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width } : null;
  }
  /** La vista y su tamaño para esta ventana. Por ahora una sola: el anfitrión (americano) en la pantalla grande y el
   * busto (medio) en la chica */
  function planear() {
    const VW = ventana.innerWidth || 800, VH = ventana.innerHeight || 600;
    const chica = VW <= 1080;
    const vista = chica ? 'busto' : 'anfitrion', plano = chica ? 'medio' : 'americano';
    const P = PLANOS[plano];
    const p = chica ? acotar(VH * 0.26, 150, 240) : acotar(VH * 0.36, 220, 400);
    return {
      vista, plano, lado: 'sala', regla: 'provisional', chica, VW, VH, p, s: p / A, yc: P.yc,
      Wc: Math.round(chica ? Math.min(P.ancho * p, 0.7 * VW) : P.ancho * p),
      Hc: Math.round((P.ya - P.yb) * p),
      bajo: Math.round((P.yc - P.yb) * p),      // lo que queda detrás del subtítulo
      alto: (P.ya - P.yc) * p,                  // lo que se ve, arriba del corte
      margen: (chica ? 0.26 : 0.2) * p,         // del borde del subtítulo al cuerpo
      cadera: (chica ? 0.15 : 0.12) * p,        // medio ancho del cuerpo en el corte: tiene que quedar sobre el subtítulo
      huella: (chica ? 0.3 : 0.22) * p,         // medio ancho de lo que tapa
    };
  }
  /** El único lugar que cambia el tamaño del lienzo (y su resolución y el grosor del contorno) */
  function aplicarTamano() {
    const d = Math.min(ventana.devicePixelRatio || 1, plan.Hc > 300 ? 1.5 : 2);
    if (plan.Wc === W && plan.Hc === H && d === dpr) return;
    W = plan.Wc; H = plan.Hc; dpr = d;
    renderer.setPixelRatio(dpr);
    renderer.setSize(W, H, false);
    lienzo.style.width = `${W}px`;
    lienzo.style.height = `${H}px`;
    camara.aspect = W / H;
    camara.updateProjectionMatrix();
    personaje.contorno.resolucion.value.set(W * dpr, H * dpr);
    personaje.contorno.grosor.value = (plan.chica ? 1.1 : 1.5) * dpr;
    redimensiones++;
  }
  // ¿Sirve `px` para pararse con el subtítulo `r`? La cadera sobre el subtítulo (si no, se verían las piernas cortadas
  // en el aire)
  const sirve = (px, r) => px - plan.cadera >= r.left + 8 && px + plan.cadera <= r.right - 8;
  const preferido = (r) => (plan.chica ? r.right - plan.margen : r.left + plan.margen);
  /** El lugar para esta escena: el de ahora si sigue sirviendo y no tapa el panel ni la ficha (no va y viene con cada
   * subtítulo); si no, el preferido */
  function elegirLugar(r) {
    if (xCuerpo === null) return preferido(r);
    const cajas = [];
    const panel = documento.querySelector('.panel');
    if (panel && !documento.querySelector('#pres')?.classList.contains('sin-panel')) cajas.push(panel.getBoundingClientRect());
    const ficha = documento.querySelector('.detalle:not([hidden])');
    if (ficha) cajas.push(ficha.getBoundingClientRect());
    const x0 = xCuerpo - plan.huella, x1 = xCuerpo + plan.huella, y0 = r.top - plan.alto, y1 = r.top;
    const tapa = cajas.some((b) => b.width > 0 && b.left < x1 && b.right > x0 && b.top < y1 && b.bottom > y0);
    return sirve(xCuerpo, r) && !tapa ? xCuerpo : preferido(r);
  }
  /** Ir a otro lugar. Si está a la vista: se funde, se mueve y vuelve (provisional: la etapa de las transiciones lo
   * hace caminar o saltar); si está oculto o subiendo desde abajo, en el acto */
  function moverA(nx) {
    if (fundiendo) { destinoX = nx; return; }
    const aLaVista = corriendo && !lienzo.hidden && arriba && !recienSubido && anim.estado().entrando !== 'entra';
    if (xCuerpo === null || !aLaVista || Math.abs(nx - xCuerpo) < 3) { xCuerpo = nx; return; }
    fundiendo = true;
    destinoX = nx;
    lienzo.classList.add('fundido');
    tFundido = setTimeout(() => {
      fundiendo = false;
      xCuerpo = destinoX;
      // ya en el lugar nuevo (el dibujo y el lienzo juntos) antes de volver a verse
      if (corriendo) { colocar(); dibujar(); }
      lienzo.classList.remove('fundido');
    }, FUNDIDO_MS);
  }
  /** Cada cuadro: el plan (si cambió la ventana), el lugar (con cada escena o si dejó de servir), el lienzo pegado al
   * borde de arriba del subtítulo y la cámara que pone el corte justo en ese borde */
  function colocar() {
    const VW = ventana.innerWidth || 800, VH = ventana.innerHeight || 600;
    // otra ventana (o la primera vez): otro plan y, en el acto, el lugar preferido para él
    if (!plan || plan.VW !== VW || plan.VH !== VH) { plan = planear(); relugar = true; xCuerpo = null; }
    aplicarTamano();
    const a = ancla();
    anclaCuadro = a;
    if (a) ultimaAncla = a;
    // sin subtítulo (agachándose) se queda en la última línea donde estaba; sin ninguno nunca, abajo de todo
    const r = a || ultimaAncla || { left: VW * 0.3, right: VW * 0.7, top: VH - 96, bottom: VH - 40, width: VW * 0.4 };
    if (a && (relugar || xCuerpo === null)) { relugar = false; moverA(elegirLugar(a)); }
    else if (a && !fundiendo && !sirve(xCuerpo, a)) moverA(preferido(a));   // el subtítulo cambió y lo dejó afuera
    if (xCuerpo === null) xCuerpo = preferido(r);
    // el lienzo dentro de la pantalla: se corre la cámara, no el cuerpo (el cuerpo entre el 25 y el 75 % del ancho)
    let left = Math.round(xCuerpo - W / 2);
    left = acotar(left, Math.min(0, VW - W), Math.max(0, VW - W));
    left = acotar(left, Math.round(xCuerpo - 0.75 * W), Math.round(xCuerpo - 0.25 * W));
    const cxPx = xCuerpo - left;
    const top = Math.ceil(r.top) + plan.bajo - H;
    // la cámara: el corte (yc·A del mundo) cae en la fila H − bajo del lienzo y el cuerpo en la columna cxPx
    const s = plan.s, h = H / s;
    const yb = plan.yc * A - plan.bajo / s;
    camara.position.set(personaje.grupo.position.x - (cxPx - W / 2) / s, yb + h / 2, h / 2 / TAN);
    camara.updateMatrixWorld();
    if (left !== x || top !== y) { x = left; y = top; lienzo.style.transform = `translate(${x}px, ${y}px)`; }
    // lo que queda bajo el corte no se ve: el subtítulo es vidrio y se vería a través
    if (plan.bajo !== recorte) { recorte = plan.bajo; lienzo.style.clipPath = `inset(0 0 ${recorte}px 0)`; }
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

  // ── Lo que se ve de él, proyectado en la ventana (solo cuando se pide: estado().cajas) ──
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
        const px = x + ((vtx.x + 1) / 2) * W, py = y + ((1 - vtx.y) / 2) * H;
        if (px < x0) x0 = px; if (px > x1) x1 = px; if (py < y0) y0 = py; if (py > y1) y1 = py;
      }
    });
    if (!(x1 > x0)) return null;
    // lo que de verdad se ve: dentro del lienzo y arriba del corte
    const c = [Math.max(x0, x), Math.max(y0, y), Math.min(x1, x + W), Math.min(y1, y + H - Math.max(0, recorte))];
    if (c[2] <= c[0] || c[3] <= c[1]) return null;
    const [a, b, d, e] = c.map(Math.round);
    return { x0: a, y0: b, x1: d, y1: e, ancho: d - a, alto: e - b };
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
  function bucle(ahora) {
    cuadro = 0;
    if (!corriendo) return;
    const dt = antes ? (ahora - antes) / 1000 : 1 / 60;
    antes = ahora;
    anim.actualizar(dt);
    colocar();
    // el subtítulo se fue (o ya no lo quieren): se agacha; volvió mientras se agachaba: se asoma
    if (arriba && (!enEscena || !anclaCuadro)) agachar({ despedida: !enEscena && ultimoCierre });
    else if (!arriba && enEscena && anclaCuadro && permitido) subir();
    dibujar();
    recienSubido = false;
    if (!personaje.grupo.visible && !saliendo) { esconder(); return; }
    cuadro = ventana.requestAnimationFrame(bucle);
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
  /** Sube desde detrás del subtítulo (que está a la vista) */
  function subir() {
    clearTimeout(tVigilar);
    clearTimeout(tFuera);
    tVigilar = 0;
    const saludo = saludoPendiente;
    saludoPendiente = false;
    arriba = true;
    saliendo = false;
    recienSubido = true;   // el lugar de esta escena se toma en el acto, sin fundirse
    anim.entrar(() => { if (saludo) anim.gesto('saludar'); });
    arrancar();
  }
  /** Se agacha en el acto detrás de la línea donde estaba el subtítulo; después del cierre, despidiéndose */
  function agachar({ despedida = false } = {}) {
    if (!arriba) return;
    arriba = false;
    saliendo = true;
    clearTimeout(tSenal);
    anim.callar();
    if (despedida && !reducido) anim.gesto('despedirse', { dur: 1.2 });
    else anim.detenerGesto();
    anim.salir(() => { saliendo = false; });
    // con muy pocos cuadros por segundo (o la pestaña oculta) tardaría más: se va igual
    clearTimeout(tFuera);
    tFuera = setTimeout(() => { if (!arriba && saliendo) esconder(); }, FUERA_MS);
  }
  /** Sin dibujar: el lienzo oculto y el bucle quieto. Si todavía lo quieren, espera a que vuelva el subtítulo */
  function esconder() {
    clearTimeout(tFuera);
    clearTimeout(tFundido);
    arriba = false;
    saliendo = false;
    fundiendo = false;
    anim.callar();
    anim.detenerGesto();
    personaje.grupo.visible = false;
    detener();
    lienzo.hidden = true;
    lienzo.classList.remove('fundido');
    if (enEscena) vigilar();
  }
  function vigilar() {
    clearTimeout(tVigilar);
    tVigilar = setTimeout(() => {
      tVigilar = 0;
      if (!enEscena || !permitido || perdido || arriba) return;
      if (ancla()) subir(); else vigilar();
    }, VIGILAR_MS);
  }
  /** Lo quieren a la vista: si no está arriba, sube (en cuanto el subtítulo se vea). Devuelve si sube recién */
  function aparecer({ saludo = false } = {}) {
    if (!permitido || perdido) return false;
    enEscena = true;
    relugar = true;
    if (arriba) { arrancar(); return false; }
    saludoPendiente = saludo;
    if (ancla()) subir(); else vigilar();
    return true;
  }
  /** Ya no lo quieren (se quitó el subtítulo): se agacha en el acto, salvo que en este mismo momento llegue otra cosa
   * (la píldora que se apaga y la explicación que la reemplaza) */
  function retirar() {
    clearTimeout(tSenal);
    clearTimeout(tVigilar);
    anim.callar();
    enEscena = false;
    setTimeout(() => { if (!enEscena && arriba) agachar({ despedida: ultimoCierre }); }, 0);
  }
  function ocultarYa() {
    enEscena = false;
    clearTimeout(tSenal);
    clearTimeout(tVigilar);
    esconder();
  }

  function senalarA(objetivo, { presentar = false, gesto = null } = {}) {
    const p = objetivo && typeof objetivo.x === 'number' ? objetivo : centroDe(objetivo);
    if (!p || W === 0) return false;
    colocar();
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

  /** Lo que está haciendo (para el taller, las pruebas y las herramientas con ?qa). `cajas` (lo que se ve de él y de
   * su cabeza, en px de la ventana) se calcula solo si se lee */
  function estado() {
    const r = (v) => (v === null || v === undefined ? null : Math.round(v * 1000) / 1000);
    return {
      ...anim.estado(), enEscena, permitido, corriendo, arriba, saliendo, cuerpoY: r(personaje.cuerpo.position.y),
      lienzo: { x, y, W, H },
      vista: plan?.vista ?? null, plano: plan?.plano ?? null, lado: plan?.lado ?? null, regla: plan?.regla ?? null,
      lugar: xCuerpo === null ? null : { x: Math.round(xCuerpo) }, escala: r(plan?.s), pxAlto: r(plan?.p),
      objetivo: null, punta: null, recorte, dpr,
      ancla: ultimaAncla ? { left: Math.round(ultimaAncla.left), top: Math.round(ultimaAncla.top), right: Math.round(ultimaAncla.right) } : null,
      redimensiones, msCuadro: r(msCuadro), cuadros,
      escena: ultimaEscena ? { n: ultimaEscena.n ?? null, tipo: ultimaEscena.tipo ?? null, cambio: ultimaEscena.cambio ?? null } : null,
      avisos: Object.keys(avisos).filter((k) => avisos[k] !== null),
      get cajas() { return { figura: cajaDe(personaje.grupo), cabeza: cajaDe(personaje.craneo) }; },
    };
  }

  // ── Lo que le avisa mando.js ──
  const api = {
    /** Una escena del recorrido (la n): `senal` si resalta algo, `obra` si la cámara va a una obra o a un modelo. Trae
     * además lo que se explica (docs/presentador.md): se guarda para elegir la vista */
    narrar(d = {}) {
      const { n = 1, senal = false, obra = false, gesto = null, frases = 1 } = d || {};
      if (!permitido) return;
      ultimaEscena = d;
      ultimoCierre = false;
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
      ultimoCierre = true;
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
      if (v) { ultimoCierre = false; aparecer(); anim.gesto('pensar', { sostener: true }); }
      else if (anim.estado().gesto === 'pensar') { anim.detenerGesto(); retirar(); }
    },
    /** Una explicación suelta (sin recorrido) en el subtítulo */
    explicar(texto) {
      if (!permitido) return;
      ultimoCierre = false;
      const nuevo = aparecer();
      clearTimeout(tSenal);
      tSenal = setTimeout(() => { anim.gesto('explicar'); anim.hablar(decirS(texto)); }, nuevo ? 850 : 0);
    },
    /** El subtítulo se quitó: se agacha detrás de él (después del cierre, despidiéndose) */
    quitar() { retirar(); },
    /** La preferencia del panel: false lo oculta en el acto */
    mostrar(v) {
      permitido = v !== false;
      if (!permitido) ocultarYa();
      else if (subtitulo()?.classList.contains('visible')) aparecer();
    },
    // Los avisos de lo que pasa en la escena (mando.js): por ahora solo se guardan (las vistas los usan después)
    encuadre(c) { avisos.encuadre = c ?? null; },
    atlas(a) { avisos.atlas = a ?? null; },
    simulacion(s) { avisos.simulacion = s ?? null; },
    ambiente(l) { avisos.ambiente = l ?? null; },
    /** Dónde queda la mano que señala ({lado, y}) para que el panel lleve lo resaltado a esa altura; null: ninguna */
    alturaMano: () => null,
    // para el taller y las pruebas
    gesto: (nombre, o) => anim.gesto(nombre, o),
    senalarA,
    estado,
    soltar() {
      ocultarYa();
      clearTimeout(tVigilar);
      lienzo.remove();
      personaje.liberar();
      renderer.dispose();
      if (ventana.__qaPresentador === api) delete ventana.__qaPresentador;
    },
  };
  // las herramientas de verificación (como __qaPropuesta en escena.js): solo con ?qa en la dirección
  try { if (new URLSearchParams(ventana.location?.search || '').has('qa')) ventana.__qaPresentador = api; } catch { /* nada */ }
  return api;
}
