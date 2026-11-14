// La tarjeta del recorrido narrado en el chat del asistente (agente.js) y la barra fija que lo sigue mientras suena.
//
// La acción `recorrido` del servidor trae lo que la persona necesita para seguirlo y manejarlo desde el chat: el
// título, dónde suena, la duración estimada, las escenas (dónde está cada una, lo que hace y su narración), el cierre y
// las sugerencias para seguir. El avance llega en vivo:
// * si suena en esta pestaña o en el proyector, del puente (`escucharRecorrido`: el reproductor de la vista o el canal
//   del proyector);
// * si suena en la pantalla en off (otro equipo), de GET /api/pantalla/recorrido cada SONDEO_MS mientras no termine.
// Los controles van adonde suena (el puente o POST /api/pantalla/recorrido/control). Al terminar ofrece volver a
// reproducirlo y las sugerencias como botones (al tocar una, se envía como mensaje de la persona).
//
// Seguridad: todo se valida con la forma exacta y se pinta con textContent (nada del modelo entra como HTML). La
// tarjeta no es aria-live: solo cambia aria-current de la escena en curso.
import { api } from './api.js';
import { MAX_CIERRE, MAX_ESCENAS, MAX_EXPLICACION, MAX_PUNTO, MAX_TITULO, TERMINALES, controlRecorrido,
  escucharRecorrido, proyectorVivo } from './agente-presentacion.js';

const SONDEO_MS = 1500;
const SONDEO_MAX_MS = 15 * 60 * 1000;
const RID = /^[0-9a-f]{12}$/;
// Lo que hace cada escena (`HACE` de la herramienta): el nombre y el ícono de ui.js
export const HACE = {
  paso: ['Cambia de paso', 'siguiente'], camara: ['Mueve la cámara', 'gps'], enfoque: ['Enfoca una obra', 'buscar'],
  ficha: ['Abre una ficha', 'info'], hoy: ['Muestra hoy', 'reloj'], proyecto: ['Muestra el proyecto', 'presentacion'],
  modelo: ['Abre un modelo del atlas', 'zona'], resaltar: ['Resalta', 'pin'], solo3d: ['Solo 3D', 'pantalla'],
  girar: ['Gira', 'repetir'],
};
const FASE = { preparando: 'Preparando', narrando: 'Narrando', sosteniendo: 'Mirando', cierre: 'En resumen', pausa: 'En pausa',
  fin: 'Terminó', detenido: 'Detenido', error: 'Detenido por un error', sin_avance: 'Preparando' };
const AVISO = { atlas: 'el modelo del atlas no cargó', resaltar: 'no encontró lo que resaltar', asiento: 'la imagen tardó en asentarse',
  voz: 'la voz no pudo hablar' };
const DONDE = { aqui: 'en esta pestaña', proyector: 'en el proyector', pantalla_off: 'en la pantalla en off' };

const cadena = (v, max) => typeof v === 'string' && v.trim() && [...v].length <= max && !/[\u0000-\u001f\u007f]/.test(v);

/** La acción `recorrido` con la forma exacta, copiada, o null. */
export function tarjetaValida(a) {
  if (!a || typeof a !== 'object' || Array.isArray(a) || a.tipo !== 'recorrido') return null;
  const claves = ['tipo', 'id', 'titulo', 'destino', 'duracion_ms', 'cierre', 'sugerencias', 'escenas'];
  if (Object.keys(a).some((k) => !claves.includes(k))) return null;
  if (typeof a.id !== 'string' || !RID.test(a.id) || !cadena(a.titulo, MAX_TITULO)) return null;
  if (a.destino !== 'vista' && a.destino !== 'pantalla_off') return null;
  if (!Number.isInteger(a.duracion_ms) || a.duracion_ms < 0 || a.duracion_ms > 600000) return null;
  let cierre = null;
  if (a.cierre != null) {
    if (!Array.isArray(a.cierre) || !a.cierre.length || a.cierre.length > 3 || !a.cierre.every((x) => cadena(x, MAX_PUNTO))) return null;
    if (a.cierre.reduce((s, x) => s + [...x].length, 0) > MAX_CIERRE) return null;
    cierre = [...a.cierre];
  }
  const sug = a.sugerencias ?? [];
  if (!Array.isArray(sug) || sug.length > 3 || !sug.every((x) => cadena(x, 60))) return null;
  if (!Array.isArray(a.escenas) || !a.escenas.length || a.escenas.length > MAX_ESCENAS) return null;
  const escenas = [];
  for (const e of a.escenas) {
    if (!e || typeof e !== 'object' || Array.isArray(e) || Object.keys(e).some((k) => !['narracion', 'donde', 'hace'].includes(k))) return null;
    if (!cadena(e.narracion, MAX_EXPLICACION) || !cadena(e.donde, 300)) return null;
    if (!Array.isArray(e.hace) || e.hace.length > 10 || !e.hace.every((h) => Object.prototype.hasOwnProperty.call(HACE, h))) return null;
    escenas.push({ narracion: e.narracion, donde: e.donde, hace: [...new Set(e.hace)] });
  }
  return { id: a.id, titulo: a.titulo, destino: a.destino, duracion_ms: a.duracion_ms, cierre, sugerencias: [...sug], escenas };
}

export function duracion(ms) {
  const s = Math.max(1, Math.round(ms / 1000));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60), r = s % 60;
  return r ? `${m} min ${r} s` : `${m} min`;
}

// ── La barra fija: sigue a la tarjeta que suena (la más nueva) ──
const tarjetasVivas = new Set();
const oyentesBarra = new Set();
function avisarBarra() {
  const viva = recorridoDelChat();
  for (const f of oyentesBarra) { try { f(viva); } catch { /* nada */ } }
}

/** La tarjeta cuyo recorrido suena (la más nueva), o null. */
export function recorridoDelChat() {
  let viva = null;
  for (const t of tarjetasVivas) {
    if (!t.el.isConnected && t.viejo()) tarjetasVivas.delete(t);   // la conversación se borró de la pantalla
    else if (t.sonando()) viva = t;
  }
  return viva;
}

/** La persona escribe en el chat: el recorrido que suena se pausa al terminar la frase (en la pantalla en off, en el
 * acto: el servidor no tiene pausa suave). */
export function pausaPorMensaje() {
  const t = recorridoDelChat();
  if (t && !t.pausado()) t.controlar('pausar', { suave: true, nota: 'En pausa mientras responde el asistente.' });
}

/**
 * La tarjeta del recorrido `a` (ya validado con `tarjetaValida`).
 * deps: {el, ico, alSugerencia(texto), reproducir(rid, desde) → bool (la vista o el proyector: el recorrido guardado)}
 */
export function crearTarjetaRecorrido(a, { el, ico, alSugerencia, reproducir }) {
  let rid = a.id;
  let donde = a.destino === 'pantalla_off' ? 'pantalla_off' : (proyectorVivo() ? 'proyector' : 'aqui');
  let ultimo = null;        // el último avance
  let terminado = false;
  let quitar = () => {};
  let sondeo = 0;

  const art = el('article', 'agente-recorrido');
  art.dataset.destino = a.destino;
  const cab = el('header', 'rec-cab');
  const sello = el('span', 'rec-sello');
  sello.append(ico('presentacion'));
  const tit = el('div', 'rec-titulos');
  const h = el('h3', null, a.titulo);
  const meta = el('small', 'rec-meta');
  tit.append(el('span', 'rec-tipo', 'Recorrido narrado'), h, meta);
  cab.append(sello, tit);
  const avance = el('div', 'rec-avance');
  const barra = el('i');
  avance.append(barra);
  avance.setAttribute('aria-hidden', 'true');
  const estadoEl = el('p', 'rec-estado', 'Preparando la primera escena…');
  const lista = el('ol', 'rec-escenas');
  const items = a.escenas.map((e) => {
    const li = el('li', 'rec-escena');
    const chips = el('div', 'rec-chips');
    for (const k of e.hace) {
      const c = el('span', 'rec-chip');
      c.title = HACE[k][0];
      c.append(ico(HACE[k][1]), el('span', null, HACE[k][0]));
      chips.append(c);
    }
    const marca = el('span', 'rec-marca');
    marca.setAttribute('aria-hidden', 'true');
    li.append(marca, el('b', 'rec-donde', e.donde), el('p', 'rec-narracion', e.narracion), chips);
    lista.append(li);
    return li;
  });
  let liCierre = null;
  if (a.cierre) {
    liCierre = el('li', 'rec-escena rec-cierre');
    const pts = el('ul', 'rec-puntos');
    for (const x of a.cierre) pts.append(el('li', null, x));
    const marca = el('span', 'rec-marca');
    marca.setAttribute('aria-hidden', 'true');
    liCierre.append(marca, el('b', 'rec-donde', 'En resumen'), pts);
    lista.append(liCierre);
  }
  const notaEl = el('p', 'rec-nota');
  notaEl.hidden = true;

  const boton = (accion, etiqueta, icono, clase = 'btn chico') => {
    const b = el('button', clase);
    b.type = 'button';
    b.dataset.accion = accion;
    b.title = etiqueta;
    b.setAttribute('aria-label', etiqueta);
    b.append(ico(icono), el('span', null, etiqueta));
    return b;
  };
  const controles = el('div', 'rec-controles');
  const bPausa = boton('pausar', 'Pausa', 'pausa');
  const bAnt = boton('anterior', 'Anterior', 'anterior');
  const bSig = boton('siguiente', 'Siguiente', 'siguiente');
  const bRep = boton('repetir', 'Repetir', 'repetir');
  const bDet = boton('detener', 'Detener', 'detener');
  controles.append(bPausa, bAnt, bSig, bRep, bDet);
  controles.setAttribute('role', 'group');
  controles.setAttribute('aria-label', 'Controles del recorrido');
  const final = el('div', 'rec-final');
  final.hidden = true;
  const bOtra = boton('reproducir', 'Volver a reproducir', 'reproducir', 'btn chico primario');
  const bReanudar = boton('reanudar', 'Reanudar', 'reproducir', 'btn chico primario');
  bReanudar.hidden = true;
  final.append(bOtra, bReanudar);
  const sugerencias = el('div', 'rec-sugerencias');
  for (const s of a.sugerencias) {
    const b = el('button', 'btn chico rec-sugerencia', s);
    b.type = 'button';
    b.addEventListener('click', () => alSugerencia?.(s));
    sugerencias.append(b);
  }
  sugerencias.hidden = true;
  art.append(cab, avance, estadoEl, lista, notaEl, controles, final, sugerencias);

  function pintarMeta() {
    const partes = [`${a.escenas.length} ${a.escenas.length === 1 ? 'escena' : 'escenas'}`, `≈ ${duracion(a.duracion_ms)}`, DONDE[donde]];
    meta.textContent = partes.join(' · ');
  }
  pintarMeta();

  function nota(t) {
    notaEl.textContent = t || '';
    notaEl.hidden = !t;
  }

  function pintar(p) {
    ultimo = p;
    const de = a.escenas.length;
    const n = Math.min(Math.max(p.n || 1, 1), de);
    const fase = p.fase in FASE ? p.fase : 'preparando';
    const enCierre = fase === 'cierre' || (fase === 'pausa' && p.enCierre);
    const fin = fase === 'fin';
    items.forEach((li, i) => {
      const k = i + 1;
      const hecha = fin || k < n || (enCierre && k <= n);
      li.classList.toggle('hecha', hecha);
      const cur = !fin && !TERMINALES.includes(fase) && !enCierre && k === n;
      if (cur) { li.setAttribute('aria-current', 'step'); li.dataset.fase = fase; } else { li.removeAttribute('aria-current'); delete li.dataset.fase; }
    });
    if (liCierre) {
      liCierre.classList.toggle('hecha', fin);
      if (enCierre) liCierre.setAttribute('aria-current', 'step'); else liCierre.removeAttribute('aria-current');
    }
    if (p.aviso && AVISO[p.aviso]) marcarAviso(n, AVISO[p.aviso]);
    if (p.motivo === 'escena_fallida' && !TERMINALES.includes(fase)) marcarAviso(n, 'no se pudo mostrar');
    const total = de + 1;
    const hechas = fin ? total : enCierre ? de + 0.5 : (n - 1) + (fase === 'sosteniendo' ? 0.85 : fase === 'narrando' ? 0.5 : 0.15);
    barra.style.width = `${Math.round((hechas / total) * 100)}%`;
    terminado = TERMINALES.includes(fase);
    art.dataset.fase = fase;
    // lo que dice la línea de estado
    if (fin) estadoEl.textContent = `Terminó${p.t_ms ? ` · ${duracion(p.t_ms)}` : ''}`;
    else if (fase === 'detenido') estadoEl.textContent = p.motivo === 'reemplazo' ? 'Lo reemplazó otro recorrido' : `Detenido en la escena ${n}`;
    else if (fase === 'error') estadoEl.textContent = `Se detuvo por un error en la escena ${n}`;
    else if (enCierre) estadoEl.textContent = fase === 'pausa' ? 'En pausa · en el resumen' : 'En resumen';
    else estadoEl.textContent = `Escena ${n} de ${de} · ${FASE[fase]}`;
    // los botones
    const pausado = fase === 'pausa';
    bPausa.dataset.accion = pausado ? 'continuar' : 'pausar';
    bPausa.replaceChildren(ico(pausado ? 'reproducir' : 'pausa'), el('span', null, pausado ? 'Continuar' : 'Pausa'));
    bPausa.title = pausado ? 'Continuar' : 'Pausa';
    bPausa.setAttribute('aria-label', bPausa.title);
    controles.hidden = terminado;
    final.hidden = !terminado;
    sugerencias.hidden = !terminado || !a.sugerencias.length;
    const cortado = fase === 'detenido' && p.motivo === 'proyector';
    bReanudar.hidden = !cortado;
    if (cortado) {
      bReanudar.querySelector('span').textContent = `Reanudar desde la escena ${n}`;
      bReanudar.dataset.desde = String(n);
    }
    // las notas
    if (cortado) nota('Se detuvo: se cerró el proyector.');
    else if (fase === 'detenido' && p.motivo === 'otra_orden') nota('Se detuvo: el asistente mostró otra cosa.');
    else if (pausado && p.motivo === 'mensaje') nota('En pausa mientras responde el asistente.');
    else if (pausado && p.motivo === 'persona') nota('En pausa: movieron la imagen. Al continuar, la escena vuelve.');
    else if (!terminado && donde === 'proyector' && p.voz === 'sin_activar') nota('Toque la ventana del proyector para activar la voz.');
    else if (!terminado && donde === 'aqui' && p.voz === 'sin_activar') nota('Toque «Voz» en la barra de la presentación para oírla.');
    else if (!pausado) nota('');
    if (terminado) soltar();
    avisarBarra();
  }

  function marcarAviso(n, t) {
    const li = items[n - 1];
    if (!li || li.querySelector('.rec-aviso')) return;
    li.append(el('small', 'rec-aviso', t));
  }

  // ── De dónde llega el avance ──
  function escuchar() {
    quitar();
    if (a.destino === 'vista') {
      quitar = escucharRecorrido((p, de) => {
        if (p.rid !== rid) return;
        // el reproductor de aquí lo soltó para pasárselo al proyector que se abrió: sigue allá (lo dirá el proyector)
        if (de === 'aqui' && p.fase === 'detenido' && p.motivo === 'proyector') return;
        if (de === 'proyector' || de === 'aqui') { const antes = donde; donde = de; if (antes !== donde) pintarMeta(); }
        pintar({ ...p, enCierre: p.fase === 'cierre' || (p.fase === 'pausa' && ultimo?.fase === 'cierre') || (p.fase === 'pausa' && !!ultimo?.enCierre) });
      });
    } else {
      const hasta = Date.now() + SONDEO_MAX_MS;
      let parar = false;
      const vuelta = async () => {
        if (parar || !art.isConnected || Date.now() > hasta) return;
        let espera = SONDEO_MS;
        try {
          const r = await api.get('/api/pantalla/recorrido');
          const x = r?.recorrido;
          if (!x || x.id !== rid) {
            // otro recorrido lo reemplazó, o se cerró hace rato
            if (!terminado) pintar({ ...(ultimo || { n: 1 }), fase: 'detenido', motivo: x ? 'reemplazo' : ultimo?.motivo });
            return;
          }
          const fase = x.fase === 'sin_avance' ? 'preparando' : x.fase;
          const p = { rid, n: x.escena, de: x.de, fase: x.cerrado && !TERMINALES.includes(fase) ? 'detenido' : fase,
            frase: Number.isInteger(r.frase) ? r.frase : 0, voz: x.voz, motivo: x.motivo ?? undefined,
            enCierre: fase === 'cierre' || (fase === 'pausa' && !!ultimo?.enCierre) };
          for (const av of Array.isArray(r.avisos) ? r.avisos : []) {
            if (av && Number.isInteger(av.n) && Object.prototype.hasOwnProperty.call(AVISO, av.tipo)) marcarAviso(av.n, AVISO[av.tipo]);
          }
          pintar(p);
          if (TERMINALES.includes(p.fase)) return;
        } catch { espera = SONDEO_MS * 3; }
        sondeo = setTimeout(vuelta, espera);
      };
      quitar = () => { parar = true; clearTimeout(sondeo); };
      vuelta();
    }
  }

  function soltar() {
    if (a.destino === 'pantalla_off') { quitar(); quitar = () => {}; }
  }

  async function controlar(accion, { suave = false, nota: t = null } = {}) {
    if (terminado) return;
    try {
      if (a.destino === 'pantalla_off') {
        const r = await api.post('/api/pantalla/recorrido/control', { rid, accion });
        if (accion === 'reproducir' && r?.id && RID.test(r.id)) { rid = r.id; terminado = false; escuchar(); }
      } else {
        const r = await controlRecorrido(rid, accion, { suave });
        if (r && r.ok === false) throw new Error(r.error || 'No se pudo');
      }
      if (t) nota(t);
    } catch (e) {
      nota(`No se pudo: ${String(e?.message || 'la presentación no está abierta').slice(0, 140)}.`);
    }
  }

  controles.addEventListener('click', (e) => {
    const b = e.target.closest?.('button[data-accion]');
    if (b) controlar(b.dataset.accion);
  });
  bOtra.addEventListener('click', async () => {
    if (a.destino === 'pantalla_off') {
      try {
        const r = await api.post('/api/pantalla/recorrido/control', { rid, accion: 'reproducir' });
        if (r?.id && RID.test(r.id)) rid = r.id;
        terminado = false;
        ultimo = null;
        for (const li of art.querySelectorAll('.rec-aviso')) li.remove();
        pintar({ rid, n: 1, de: a.escenas.length, fase: 'preparando' });
        escuchar();
      } catch (e) { nota(`No se pudo: ${String(e?.message || 'sin conexión').slice(0, 140)}.`); }
      return;
    }
    for (const li of art.querySelectorAll('.rec-aviso')) li.remove();
    if (!reproducir?.(rid, 1)) nota('No se pudo volver a reproducir: el recorrido ya no está en este navegador.');
  });
  bReanudar.addEventListener('click', () => {
    const k = Number(bReanudar.dataset.desde) || 1;
    if (!reproducir?.(rid, k)) nota('No se pudo reanudar: el recorrido ya no está en este navegador.');
  });

  const t = {
    el: art,
    id: () => rid,
    titulo: a.titulo,
    sonando: () => art.isConnected && !terminado && !!ultimo,
    viejo: () => { if (art.isConnected) return false; quitar(); return true; },
    pausado: () => ultimo?.fase === 'pausa',
    avance: () => ultimo,
    controlar,
  };
  tarjetasVivas.add(t);
  escuchar();
  return t;
}

/**
 * La barra fija arriba del registro del chat mientras un recorrido suena (aunque el turno haya terminado o la persona
 * suba en el historial): «● En la sala · escena 3 de 6 · Pausa · Detener».
 */
export function montarBarraRecorrido(antesDe, { el, ico }) {
  const b = el('div', 'agente-rec-barra');
  b.hidden = true;
  const punto = el('span', 'rec-punto');
  punto.setAttribute('aria-hidden', 'true');
  const txt = el('span', 'rec-barra-texto');
  const pausa = el('button', 'btn fantasma chico');
  pausa.type = 'button';
  const det = el('button', 'btn fantasma chico');
  det.type = 'button';
  det.append(ico('detener'), el('span', null, 'Detener'));
  b.append(punto, txt, pausa, det);
  antesDe.before(b);
  let actual = null;
  const pintar = (t) => {
    actual = t;
    b.hidden = !t;
    if (!t) return;
    const p = t.avance();
    const enPausa = p?.fase === 'pausa';
    b.dataset.fase = p?.fase || '';
    txt.textContent = `En la sala · ${t.titulo} · ${p?.fase === 'cierre' ? 'en resumen' : `escena ${p?.n || 1} de ${p?.de || 1}`}`;
    pausa.replaceChildren(ico(enPausa ? 'reproducir' : 'pausa'), el('span', null, enPausa ? 'Continuar' : 'Pausa'));
  };
  oyentesBarra.add(pintar);
  pausa.addEventListener('click', () => { if (actual) actual.controlar(actual.pausado() ? 'continuar' : 'pausar'); });
  det.addEventListener('click', () => { if (actual) actual.controlar('detener'); });
  return () => { oyentesBarra.delete(pintar); b.remove(); };
}
