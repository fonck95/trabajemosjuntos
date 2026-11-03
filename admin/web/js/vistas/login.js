// Ingreso del administrador, con un campo de puntos animado de fondo (la población que se va a mapear).
import { api } from '../api.js';
import { $, html, montar } from '../ui.js';

export function vistaLogin(raiz, { configurado, alEntrar }) {
  montar(raiz, html`
    <div class="login">
      <section class="lienzo" aria-hidden="true">
        <canvas id="fondo"></canvas>
        <h1>Trabajemos<br><em>juntos</em><br>por Yondó</h1>
        <p>Base única de habitantes: cruzada, georreferenciada y enriquecida reunión a reunión.</p>
      </section>
      <section class="caja">
        <form id="f-login" autocomplete="on" novalidate>
          <h2>Panel de administración</h2>
          ${configurado ? '' : html`<div class="aviso-legal">El servidor no tiene credenciales. Defina las variables <b>ADMIN</b> y <b>password</b> y reinicie.</div>`}
          <label class="campo"><span>Usuario</span><input name="usuario" autocomplete="username" required autofocus></label>
          <label class="campo"><span>Clave</span><input name="clave" type="password" autocomplete="current-password" required></label>
          <div class="error" id="error" role="alert"></div>
          <button class="btn primario" type="submit" style="min-height:44px">Ingresar</button>
          <p class="legal">Acceso restringido. Contiene datos personales protegidos por la Ley 1581 de 2012; cada consulta y cambio queda registrado.</p>
        </form>
      </section>
    </div>`);
  const f = $('#f-login');
  f.addEventListener('submit', async (e) => {
    e.preventDefault();
    const boton = f.querySelector('button');
    boton.disabled = true;
    $('#error').textContent = '';
    try {
      const d = await api.post('/api/login', { usuario: f.usuario.value, clave: f.clave.value });
      parar();
      alEntrar(d);
    } catch (err) {
      $('#error').textContent = err.message;
      f.clave.value = '';
      f.clave.focus();
    } finally {
      boton.disabled = false;
    }
  });
  const parar = animar($('#fondo'));
}

function animar(canvas) {
  const ctx = canvas.getContext('2d');
  const reducir = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let w, h, puntos, raf;
  const dpr = Math.min(devicePixelRatio || 1, 2);
  function medir() {
    w = canvas.clientWidth; h = canvas.clientHeight;
    canvas.width = w * dpr; canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    // Puntos agrupados en "barrios" que laten como un mapa de calor
    const centros = Array.from({ length: 9 }, () => [Math.random() * w, Math.random() * h * 0.75, 30 + Math.random() * 90]);
    puntos = Array.from({ length: Math.round((w * h) / 900) }, () => {
      const c = centros[(Math.random() * centros.length) | 0];
      const a = Math.random() * Math.PI * 2, r = Math.abs((Math.random() + Math.random() - 1) * c[2] * 1.6);
      return { x: c[0] + Math.cos(a) * r, y: c[1] + Math.sin(a) * r, f: Math.random() * Math.PI * 2 };
    });
  }
  function cuadro(t) {
    ctx.clearRect(0, 0, w, h);
    for (const p of puntos) {
      const b = 0.25 + 0.75 * (0.5 + 0.5 * Math.sin(t / 900 + p.f));
      ctx.fillStyle = `rgba(227, 20, 27, ${0.12 + b * 0.5})`;
      ctx.beginPath(); ctx.arc(p.x, p.y, 1.2 + b * 1.4, 0, 7); ctx.fill();
    }
    if (!reducir) raf = requestAnimationFrame(cuadro);
  }
  medir();
  cuadro(0);
  addEventListener('resize', medir);
  return () => { cancelAnimationFrame(raf); removeEventListener('resize', medir); };
}
