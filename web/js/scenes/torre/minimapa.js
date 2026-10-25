// Minimapa del recorrido de la torre en un <canvas> 2D (equipo C; especificación de integración, 6.6).
// Recintos del nivel con el color de su grupo de la Res. 1633 (o el de la capa encendida), el recinto actual resaltado y el
// caminante como flecha; un toque o clic lleva a la puerta del recinto tocado. Lleva aria-hidden: su alternativa accesible es
// la lista «Ir a…» del panel. Toma sus colores de tokens() y se redibuja con onTheme.
import { tokens, onTheme } from '../../core.js';

const ANCHO = 160, ALTO_MAX = 300, MARGEN = 8;
const css = (c) => `#${c.getHexString()}`;
const mezcla = (a, b, k) => `rgb(${[0, 1, 2].map((i) => Math.round(255 * (a[i] * (1 - k) + b[i] * k))).join(',')})`;
const rgb = (hex) => { const n = parseInt(String(hex || '#9aa0a6').slice(1), 16); return [(n >> 16) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255]; };

// op: { alTocar(x, y) } en coordenadas de planta
export function crearMinimapa(contenedor, { alTocar } = {}) {
  const canvas = document.createElement('canvas');
  canvas.className = 'reco-mapa';
  canvas.setAttribute('aria-hidden', 'true');
  canvas.title = 'Minimapa: toca un recinto para ir a su puerta';
  contenedor.append(canvas);
  const ctx = canvas.getContext('2d');
  let T = tokens(), estado = null, tf = null;
  const quitarTema = onTheme((t) => { T = t; dibujar(estado); });

  function ajustar(nivel) {
    const pts = (nivel.contorno?.length ? nivel.contorno : (nivel.recintos || []).flatMap((r) => r.poligono));
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const [x, y] of pts) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
    const s = Math.min((ANCHO - 2 * MARGEN) / (x1 - x0), (ALTO_MAX - 2 * MARGEN - 12) / (y1 - y0));
    const alto = Math.min(ALTO_MAX, Math.ceil((y1 - y0) * s + 2 * MARGEN + 12));
    const ox = (ANCHO - (x1 - x0) * s) / 2;
    return { x0, y0, y1, s, alto, ox, oy: MARGEN + 12, nivel: nivel.id };
  }
  const aPx = ([x, y]) => [tf.ox + (x - tf.x0) * tf.s, tf.oy + (tf.y1 - y) * tf.s];

  // e: { nivel, nombre, grupos, posicion: [x, y], rumbo_deg, recinto, colores: Map<id, THREE.Color> | null }
  function dibujar(e) {
    estado = e;
    if (!e?.nivel || canvas.hidden) return;
    if (!tf || tf.nivel !== e.nivel.id) {
      tf = ajustar(e.nivel);
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      canvas.width = Math.round(ANCHO * dpr); canvas.height = Math.round(tf.alto * dpr);
      canvas.style.width = `${ANCHO}px`; canvas.style.height = `${tf.alto}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    const sup = [T.surface.r, T.surface.g, T.surface.b];
    ctx.clearRect(0, 0, ANCHO, tf.alto);
    ctx.fillStyle = css(T.surface); ctx.globalAlpha = 0.92; ctx.fillRect(0, 0, ANCHO, tf.alto); ctx.globalAlpha = 1;
    ctx.lineWidth = 0.6; ctx.strokeStyle = css(T.line);
    for (const r of e.nivel.recintos || []) {
      ctx.beginPath();
      r.poligono.forEach((p, i) => { const [x, y] = aPx(p); if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y); });
      ctx.closePath();
      const capa = e.colores?.get?.(r.id);
      const base = capa ? [capa.r, capa.g, capa.b] : rgb(e.grupos?.[r.grupo_1633]?.color_hex);
      ctx.fillStyle = r.transitable === false ? css(T.line) : mezcla(base, sup, r.grupo_1633 === 'circulacion' ? 0.55 : 0.35);
      ctx.fill(); ctx.stroke();
    }
    if (e.recinto) {
      const r = (e.nivel.recintos || []).find((q) => q.id === e.recinto);
      if (r) {
        ctx.beginPath();
        r.poligono.forEach((p, i) => { const [x, y] = aPx(p); if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y); });
        ctx.closePath(); ctx.lineWidth = 2; ctx.strokeStyle = css(T.ink); ctx.stroke();
      }
    }
    // título del nivel
    ctx.fillStyle = css(T.ink); ctx.font = '600 10px "IBM Plex Mono", ui-monospace, monospace'; ctx.textBaseline = 'top';
    ctx.fillText(String(e.nombre || e.nivel.id).slice(0, 26), 6, 4);
    // caminante: flecha en el rumbo (antihorario desde el este; en pantalla y crece hacia abajo)
    if (e.posicion) {
      const [px, py] = aPx(e.posicion), a = ((e.rumbo_deg || 0) * Math.PI) / 180, c = Math.cos(a), s = -Math.sin(a);
      const P = (f, l) => [px + c * f - s * l, py + s * f + c * l];
      ctx.beginPath();
      [P(9, 0), P(-5, 5.5), P(-2, 0), P(-5, -5.5)].forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
      ctx.closePath();
      ctx.fillStyle = css(T.accent); ctx.strokeStyle = css(T.surface); ctx.lineWidth = 1.5; ctx.fill(); ctx.stroke();
    }
  }
  canvas.addEventListener('click', (ev) => {
    if (!tf || !alTocar) return;
    const r = canvas.getBoundingClientRect(), px = ev.clientX - r.left, py = ev.clientY - r.top;
    alTocar(tf.x0 + (px - tf.ox) / tf.s, tf.y1 - (py - tf.oy) / tf.s);
  });
  return {
    el: canvas,
    dibujar,
    mostrar(on) { canvas.hidden = !on; if (on) dibujar(estado); },
    visible: () => !canvas.hidden,
    dispose() { quitarTema(); canvas.remove(); },
  };
}
