// Diálogo de acercamiento (7.5): canal, número, resultado de un toque con «Deshacer», autorización y datos que dictó
// el titular. Lo usan la ficha, «Mi trabajo» y la franja de la llamada sin registrar.
import { api, ErrorApi, nuevaClave, sesion } from '../api.js';
import { olvidarLlamada, llamadaPendiente } from '../llamadas.js';
import {
  CANALES, CANALES_AUTORIZACION, ESTADOS_TELEFONO, FRANJAS, GRUPOS_RESULTADO, MEDIOS_AUTORIZACION, MEDIOS_POR_ROL,
  RESULTADOS, RESULTADOS_DE_NUMERO, RESULTADOS_RAPIDOS, TIPOS_TELEFONO, autorizacionDe, canalesPermitidos, enlaceWhatsapp,
  esCelular, etiquetaResultado, fueraDeHorario, hoyColombia, telefonosUsables,
} from '../modelo.js';
import { $, $$, aviso, avisoError, dialogo, html, icono, titulo } from '../ui.js';

const ICONO_CANAL = { llamada: 'telefono', whatsapp: 'whatsapp', sms: 'acercamiento', visita: 'hogar', correo: 'acercamiento', otro: 'puntos' };
const TELEFONICOS = ['llamada', 'whatsapp', 'sms'];
const NOTA_MAX = 1000;
// Resultados con contacto: ahí se pregunta por la autorización y por los datos que dictó
const CON_CONTACTO = ['contesto', 'volver_llamar', 'actualizo_datos', 'pidio_informacion'];

/** Mensajes de los 409 del registro (4.2): el servidor manda el código y el motivo. */
const MOTIVOS = {
  no_autorizo: 'La persona no autorizó el tratamiento de sus datos: no se le contacta.',
  menor: 'Es menor de edad: no entra en el trabajo de contacto.',
  edad_desconocida: 'No se sabe si es mayor de edad: complete su edad antes de contactarla.',
  reclamo: 'Tiene una solicitud de sus derechos en trámite.',
  situacion: 'Se reportó como fallecida o fuera del municipio.',
  pendiente: 'Su autorización está pendiente y la política no permite contactar a pendientes.',
  no_habilitado: 'La autorización viene de una planilla y el administrador todavía no la confirmó.',
  canal: 'Ese canal no está autorizado.',
};
export const mensajeNoContactable = (e) => MOTIVOS[e?.detalle?.motivo] || e?.message || 'No se puede contactar';

function guion(cat, p) {
  const resp = cat.aviso_privacidad?.responsable || 'el equipo';
  return `Buen día, ${titulo((p.nombre || '').split(' ')[0])}. Le habla ${sesion.nombre || sesion.usuario}, de ${resp}. ` +
    'Para llamarle o escribirle necesitamos su autorización para el tratamiento de sus datos. ' +
    '¿Nos autoriza a contactarle por llamada, WhatsApp o SMS? Puede revocarla cuando quiera.';
}

/** Bloque de autorización del diálogo: guion, aviso por WhatsApp, «Respondió SÍ» y los datos del evento. */
function bloqueAutorizacion(cat, p, { primero, rol, numero }) {
  const medios = rol === 'admin' || rol === 'coordinador' ? Object.keys(MEDIOS_AUTORIZACION).filter((m) => !['migrado', 'declarado_planilla', 'fusion'].includes(m))
    : MEDIOS_POR_ROL[rol] || [];
  const aviso = cat.aviso_privacidad?.texto || '';
  return html`<details class="bloque-autorizacion" id="b-aut" ${primero ? 'open' : ''}>
    <summary>Autorización del titular <span class="chip ambar">Pendiente</span></summary>
    ${primero ? html`<p class="guion">${guion(cat, p)}</p>` : ''}
    ${aviso ? html`<details class="aviso-privacidad"><summary>Aviso de privacidad (versión ${cat.aviso_privacidad?.version || ''})</summary><p>${aviso}</p></details>` : ''}
    <div class="fila-botones">
      ${numero && esCelular(numero) && aviso ? html`<a class="btn chico" href="${enlaceWhatsapp(numero, aviso)}" target="_blank" rel="noopener noreferrer">${icono('whatsapp')} Enviar aviso por WhatsApp</a>` : ''}
      <button type="button" class="btn chico" data-respondio>Respondió SÍ</button>
    </div>
    <div class="segmentado" role="group" aria-label="Respuesta" data-grupo="aut_estado">
      <button type="button" data-v="" aria-pressed="true">Sin respuesta</button><button type="button" data-v="si" aria-pressed="false">Sí autoriza</button><button type="button" data-v="no" aria-pressed="false">No autoriza</button>
    </div>
    <div class="form" data-si hidden>
      <label class="campo"><span>Medio</span><select name="aut_medio">${medios.map((m) => html`<option value="${m}">${MEDIOS_AUTORIZACION[m] || m}</option>`)}</select></label>
      <div class="campo ancho"><span>Canales autorizados</span><div class="chips">${Object.entries(CANALES_AUTORIZACION).map(([k, t]) => html`<label class="chip opcion"><input type="checkbox" name="aut_canal" value="${k}" ${TELEFONICOS.includes(k) ? 'checked' : ''}> ${t}</label>`)}</div></div>
      <label class="campo ancho"><span>Evidencia</span><input name="aut_evidencia" maxlength="300" placeholder="Respondió SÍ al aviso por WhatsApp, 04/11 15:10"></label>
      <label class="casilla ancho"><input type="checkbox" name="aut_mayor"> Declara ser mayor de 18 años</label>
    </div>
  </details>`;
}

/** Datos que dictó el titular (solo el consultor y solo lo que falta: cédula, puesto y mesa). */
function bloqueDictados(cat, faltan) {
  const campos = ['cedula', 'puesto', 'mesa'].filter((c) => faltan.includes(c));
  if (!campos.length) return '';
  const puestos = cat.puestos || [];
  return html`<details class="bloque-dictados"><summary>Datos que dictó</summary><div class="form">
    ${campos.includes('cedula') ? html`<label class="campo"><span>Cédula</span><input name="d_cedula" inputmode="numeric" autocomplete="off" maxlength="15"></label>
      <label class="campo"><span>Repita la cédula</span><input name="d_cedula_confirmacion" inputmode="numeric" autocomplete="off" maxlength="15"></label>` : ''}
    ${campos.includes('puesto') ? html`<label class="campo"><span>Puesto de votación</span><select name="d_puesto_id"><option value="">—</option>${puestos.map((x) => html`<option value="${x.id}">${x.codigo ? x.codigo + ' · ' : ''}${titulo(x.nombre)}</option>`)}</select></label>` : ''}
    ${campos.includes('mesa') ? html`<label class="campo"><span>Mesa</span><input name="d_mesa" type="number" min="1" max="99" inputmode="numeric"></label>` : ''}
  </div></details>`;
}

/** Barra «Deshacer» de 10 s después de un registro de un toque: anula el acercamiento (4.3). */
function ofrecerDeshacer(aid, texto, alDeshacer) {
  document.getElementById('barra-deshacer')?.remove();
  const b = document.createElement('div');
  b.id = 'barra-deshacer';
  b.className = 'barra-deshacer';
  b.setAttribute('role', 'status');
  b.innerHTML = String(html`<span>${texto}</span><button class="btn chico" data-deshacer>Deshacer</button>`);
  document.body.append(b);
  const quitar = setTimeout(() => b.remove(), 10000);
  b.querySelector('[data-deshacer]').addEventListener('click', async (e) => {
    e.currentTarget.disabled = true;
    try {
      const ficha = await api.post(`/api/acercamientos/${aid}/anular`, { motivo: 'Deshacer (registro de un toque)' });
      clearTimeout(quitar);
      b.remove();
      aviso('Registro anulado');
      alDeshacer?.(ficha && typeof ficha === 'object' ? ficha : null);
    } catch (err) { avisoError(err); e.currentTarget.disabled = false; }
  });
}

// El acercamiento nuevo: el que no estaba antes en la lista de la ficha (o el que el servidor nombre)
function idNuevo(antes, despues) {
  if (despues?.acercamiento_id) return despues.acercamiento_id;
  if (despues?.acercamiento?.id) return despues.acercamiento.id;
  const viejos = new Set((antes?.acercamientos || []).map((a) => a.id));
  return (despues?.acercamientos || []).find((a) => !viejos.has(a.id) && !a.anulado)?.id ?? null;
}

/**
 * Abre el diálogo para la persona `p` (la ficha que recibe el rol). `canal` e `indice` (del número usable) vienen
 * prellenados desde Llamar o WhatsApp. Resuelve con la ficha actualizada, o null si se cancela.
 * Opciones: `resultado` preelegido, `pedirActualizacion`, y `alDeshacer(ficha)` si se anula un registro de un toque.
 */
export async function dialogoAcercamiento(p, { canal = null, indice = null, resultado: inicial = null, pedirActualizacion = false, alDeshacer = null } = {}) {
  const cat = await api.catalogos();
  const rol = sesion.rol;
  const usables = telefonosUsables(p);
  const permitidos = canalesPermitidos(p, rol, { conPendientes: !!cat.politica?.contactar_pendientes });
  if (!permitidos.length) {
    aviso(rol === 'consultor' ? 'No hay un canal autorizado ni un número usable para esta persona' : 'No hay canales para registrar', 'error', 6000);
    return null;
  }
  let elegido = permitidos.includes(canal) ? canal : permitidos[0];
  const aut = autorizacionDe(p);
  const pendiente = aut.estado === 'pendiente' && rol !== 'planillero';
  const autPrimero = pendiente && !!cat.politica?.contactar_pendientes;
  const faltan = Array.isArray(p.faltan) ? p.faltan : [];
  const ab = p.abordaje || {};
  const yaHoy = ab.ultimo_fecha === hoyColombia() && ab.ultimo_uid != null && ab.ultimo_uid !== sesion.uid && ab.estado === 'contactado';
  let clave = nuevaClave(); // la misma en cada reintento: el servidor no lo registra dos veces
  const idx = Number.isInteger(indice) && indice >= 0 && indice < usables.length ? indice : 0;

  const { el, cerrar, listo } = dialogo({
    titulo: `Registrar · ${titulo(p.nombre || '')}`,
    cuerpo: html`<form class="acercamiento" id="f-acerc" novalidate>
      <div class="avisos-acercamiento" id="avisos-acerc">
        ${yaHoy ? html`<p class="aviso-legal">Ya fue contactado hoy por ${ab.ultimo_usuario || 'otra persona del equipo'}.</p>` : ''}
      </div>
      ${autPrimero ? bloqueAutorizacion(cat, p, { primero: true, rol, numero: usables[idx]?.numero }) : ''}
      <div class="campo"><span>Canal</span><div class="segmentado canales" role="group" aria-label="Canal" data-grupo="canal">
        ${permitidos.map((c) => html`<button type="button" data-v="${c}" aria-pressed="${c === elegido}">${icono(ICONO_CANAL[c] || 'acercamiento')}<span>${CANALES[c] || c}</span></button>`)}
      </div></div>
      <label class="campo" id="c-numero"><span>Número</span><select name="telefono_indice">
        ${usables.map((t, i) => html`<option value="${i}" ${i === idx ? 'selected' : ''}>${t.numero}${t.tipo ? ' · ' + (TIPOS_TELEFONO[t.tipo] || t.tipo) : ''}${t.estado ? ' · ' + (ESTADOS_TELEFONO[t.estado] || t.estado) : ''}</option>`)}
      </select></label>
      <div class="rejilla-resultados" id="resultados">
        ${GRUPOS_RESULTADO.map(([t, claves]) => html`<div class="grupo-resultados"><h3>${t}</h3><div class="botones-resultado">
          ${claves.map((k) => html`<button type="button" class="resultado-btn ${RESULTADOS_RAPIDOS.includes(k) ? 'rapido' : ''}" data-resultado="${k}" aria-pressed="false">${etiquetaResultado(k, elegido)}</button>`)}
        </div></div>`)}
        <p class="sec ayuda-rapido">«No contestó», «Buzón» y los de número se guardan con un toque.</p>
      </div>
      <div id="detalle" class="detalle-resultado" hidden>
        <div data-para="contesto"><label class="casilla"><input type="checkbox" name="confirma_numero" checked> El titular confirmó que el número es suyo</label></div>
        <div data-para="volver_llamar" class="form">
          <label class="campo"><span>¿Cuándo?</span><input type="date" name="proximo" min="${hoyColombia()}"></label>
          <label class="campo"><span>Franja</span><select name="proximo_franja"><option value="">—</option>${Object.entries(FRANJAS).map(([k, t]) => html`<option value="${k}">${t}</option>`)}</select></label>
        </div>
        <div data-para="actualizo_datos"><label class="casilla"><input type="checkbox" name="pedir_actualizacion" ${pedirActualizacion ? 'checked' : ''}> Pedir actualización de datos (un planillero la visita)</label></div>
        <div data-para="no_contactar" class="segmentado" role="group" aria-label="Alcance" data-grupo="alcance">
          <button type="button" data-v="numero" aria-pressed="true">Solo este número</button><button type="button" data-v="persona" aria-pressed="false">No contactarla más</button>
        </div>
        <div data-para="no_vive_aqui"><label class="casilla"><input type="checkbox" name="se_fue_del_municipio"> Se fue del municipio</label></div>
        <div data-para="fallecio"><p class="sec">Queda reportada sin confirmar; el administrador la confirma o la revierte. Sale de las colas.</p></div>
        <div data-para="solicitud_derechos"><p class="sec">Escriba en la nota qué pidió (consultar, corregir o borrar sus datos): queda como solicitud con plazo legal.</p></div>
        ${!autPrimero && pendiente ? html`<div data-para="${CON_CONTACTO.join(' ')}">${bloqueAutorizacion(cat, p, { primero: false, rol, numero: usables[idx]?.numero })}</div>` : ''}
        ${rol === 'consultor' ? html`<div data-para="${CON_CONTACTO.join(' ')}">${bloqueDictados(cat, faltan)}</div>` : ''}
        <label class="campo"><span>Nota <small id="cuenta-nota">0 / ${NOTA_MAX}</small></span>
          <textarea name="nota" maxlength="${NOTA_MAX}" rows="3"></textarea>
          <small class="nota-sensibles">No anote salud, política, religión ni otros datos sensibles.</small></label>
      </div>
    </form>`,
    pie: html`<button class="btn" data-cerrar>Cancelar</button><button class="btn primario" id="guardar-acerc" hidden>Guardar</button>`,
    alAbrir: (d) => d.classList.add('dialogo-acercamiento'),
  });
  const form = $('#f-acerc', el);
  const boton = $('#guardar-acerc', el);
  let resultado = null, enCurso = false, terminado = null;

  const grupo = (g) => $(`[data-grupo="${g}"] [aria-pressed="true"]`, form)?.dataset.v ?? null;
  function pintarAvisos() {
    const fuera = TELEFONICOS.includes(elegido) && fueraDeHorario(cat.politica?.horario);
    let a = $('#aviso-horario', form);
    if (fuera && !a) {
      a = document.createElement('p');
      a.id = 'aviso-horario';
      a.className = 'aviso-legal';
      a.textContent = 'Fuera de horario de contacto: puede registrarlo, pero queda marcado.';
      $('#avisos-acerc', form).append(a);
    } else if (!fuera) a?.remove();
  }
  function pintarCanal() {
    const tel = TELEFONICOS.includes(elegido);
    $('#c-numero', form).hidden = !tel || !usables.length;
    for (const b of $$('[data-resultado]', form)) {
      const k = b.dataset.resultado;
      b.textContent = etiquetaResultado(k, elegido);
      b.hidden = !tel && RESULTADOS_DE_NUMERO.includes(k);
    }
    pintarAvisos();
  }
  function pintarDetalle() {
    const det = $('#detalle', form);
    det.hidden = !resultado || RESULTADOS_RAPIDOS.includes(resultado);
    for (const x of $$('[data-para]', det)) x.hidden = !x.dataset.para.split(' ').includes(resultado);
    // «El número es suyo» solo con un número de por medio
    const conf = $('[data-para="contesto"]', det);
    if (conf) conf.hidden = conf.hidden || !TELEFONICOS.includes(elegido);
    boton.hidden = det.hidden;
    for (const b of $$('[data-resultado]', form)) b.setAttribute('aria-pressed', b.dataset.resultado === resultado);
  }

  form.addEventListener('click', (e) => {
    const seg = e.target.closest('[data-grupo] > button');
    if (seg) {
      for (const b of seg.parentElement.children) b.setAttribute('aria-pressed', b === seg);
      const g = seg.parentElement.dataset.grupo;
      if (g === 'canal') { elegido = seg.dataset.v; pintarCanal(); pintarDetalle(); }
      if (g === 'aut_estado') for (const s of $$('[data-si]', form)) s.hidden = seg.dataset.v !== 'si';
      return;
    }
    if (e.target.closest('[data-respondio]')) {
      const d = new Date();
      const hora = `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
      const bloque = e.target.closest('.bloque-autorizacion');
      $('[data-v="si"]', bloque)?.click();
      const ev = $('[name="aut_evidencia"]', bloque);
      if (ev) ev.value = `Respondió SÍ ${elegido === 'whatsapp' ? 'al aviso por WhatsApp' : elegido === 'llamada' ? 'en la llamada' : ''}, ${hora}`.replace(' ,', ',');
      const medio = $('[name="aut_medio"]', bloque);
      if (medio && rol === 'consultor') medio.value = elegido === 'llamada' ? 'verbal_telefono' : 'mensaje';
      return;
    }
    const r = e.target.closest('[data-resultado]');
    if (r) {
      resultado = r.dataset.resultado;
      if (RESULTADOS_RAPIDOS.includes(resultado)) { pintarDetalle(); guardar(); return; }
      pintarDetalle();
      $('#detalle', form).scrollIntoView({ block: 'nearest' });
    }
  });
  form.addEventListener('input', (e) => {
    if (e.target.name === 'nota') $('#cuenta-nota', form).textContent = `${e.target.value.length} / ${NOTA_MAX}`;
  });
  form.addEventListener('change', (e) => { if (e.target.name === 'telefono_indice') pintarAvisos(); });

  function cuerpo() {
    const f = form.elements;
    const c = { canal: elegido, resultado };
    if (TELEFONICOS.includes(elegido) && usables.length) c.telefono_indice = Number(f.telefono_indice.value || 0);
    const nota = f.nota.value.trim();
    if (nota) c.nota = nota;
    if (resultado === 'contesto' && TELEFONICOS.includes(elegido)) c.confirma_numero = f.confirma_numero.checked;
    if (resultado === 'volver_llamar') { c.proximo = f.proximo.value || null; c.proximo_franja = f.proximo_franja.value || null; }
    if (resultado === 'actualizo_datos') c.pedir_actualizacion = f.pedir_actualizacion.checked;
    if (resultado === 'no_contactar') c.alcance = grupo('alcance') || 'numero';
    if (resultado === 'no_vive_aqui') c.se_fue_del_municipio = f.se_fue_del_municipio.checked;
    // Autorización: el bloque visible (primero, o dentro del detalle de un resultado con contacto)
    const bloque = [...$$('.bloque-autorizacion', form)].find((b) => !b.closest('[hidden]'));
    const est = bloque && $('[data-grupo="aut_estado"] [aria-pressed="true"]', bloque)?.dataset.v;
    if (est && CON_CONTACTO.includes(resultado)) {
      c.autorizacion = { estado: est };
      if (est === 'si') {
        c.autorizacion.medio = $('[name="aut_medio"]', bloque).value;
        c.autorizacion.canales = $$('[name="aut_canal"]:checked', bloque).map((x) => x.value);
        c.autorizacion.evidencia = $('[name="aut_evidencia"]', bloque).value.trim() || null;
        c.autorizacion.mayor_declarado = $('[name="aut_mayor"]', bloque).checked;
      }
    }
    const dict = {};
    if (CON_CONTACTO.includes(resultado) && rol === 'consultor') {
      const v = (n) => f[n]?.value.trim() || '';
      if (v('d_cedula')) { dict.cedula = v('d_cedula'); dict.cedula_confirmacion = v('d_cedula_confirmacion'); }
      if (v('d_puesto_id')) dict.puesto_id = Number(v('d_puesto_id'));
      if (v('d_mesa')) dict.mesa = Number(v('d_mesa'));
    }
    if (Object.keys(dict).length) c.datos_dictados = dict;
    return c;
  }

  function validar(c) {
    if (c.autorizacion?.estado === 'si' && rol !== 'admin' && rol !== 'coordinador') {
      if (!c.autorizacion.canales.length) return 'Marque al menos un canal autorizado';
      if (!c.autorizacion.evidencia) return 'Escriba la evidencia de la autorización (o toque «Respondió SÍ»)';
      if (!c.autorizacion.mayor_declarado) return 'Para registrar la autorización debe declarar ser mayor de 18 años';
    }
    if (c.datos_dictados?.cedula && c.datos_dictados.cedula !== c.datos_dictados.cedula_confirmacion) return 'Las dos cédulas no coinciden';
    if (c.resultado === 'solicitud_derechos' && !c.nota) return 'Escriba qué pidió el titular';
    if (c.resultado === 'actualizo_datos' && c.pedir_actualizacion && !c.nota) return 'Escriba qué hay que actualizar';
    return null;
  }

  async function guardar() {
    if (enCurso || !resultado) return;
    const c = cuerpo();
    const error = validar(c);
    if (error) { aviso(error, 'error', 5000); return; }
    enCurso = true;
    boton.disabled = true;
    for (const b of $$('[data-resultado]', form)) b.disabled = true;
    try {
      const ficha = await api.post(`/api/personas/${p.id}/acercamientos`, c, { clave });
      const nueva = ficha && typeof ficha === 'object' ? ficha : null;
      const l = llamadaPendiente();
      if (l && l.pid === p.id) olvidarLlamada();
      for (const a of nueva?.avisos || []) aviso(typeof a === 'string' ? a : a.mensaje || '', 'ok', 6000);
      terminado = nueva || { ...p };
      cerrar(terminado);
      const texto = `${etiquetaResultado(resultado, elegido)} · registrado`;
      if (RESULTADOS_RAPIDOS.includes(resultado)) {
        const aid = idNuevo(p, nueva);
        if (aid != null) ofrecerDeshacer(aid, texto, alDeshacer);
        else aviso(texto);
      } else aviso(texto);
    } catch (e) {
      // Un 4xx no registró nada: lo que se envíe después es otro intento, con otra clave
      if (e instanceof ErrorApi && e.estado >= 400 && e.estado < 500 && e.codigo !== 'en_proceso') clave = nuevaClave();
      if (e instanceof ErrorApi && e.codigo === 'no_contactable') aviso(mensajeNoContactable(e), 'error', 8000);
      else if (e instanceof ErrorApi && e.codigo === 'en_proceso') aviso('El registro anterior todavía se está guardando: espere un momento', 'error', 5000);
      else avisoError(e);
      if (RESULTADOS_RAPIDOS.includes(resultado)) { resultado = null; pintarDetalle(); }
    } finally {
      enCurso = false;
      boton.disabled = false;
      for (const b of $$('[data-resultado]', form)) b.disabled = false;
    }
  }
  boton.addEventListener('click', guardar);
  form.addEventListener('submit', (e) => { e.preventDefault(); guardar(); });

  pintarCanal();
  if (inicial && RESULTADOS[inicial]) {
    resultado = inicial;
    pintarDetalle();
  }
  const v = await listo;
  return v || terminado || null;
}
