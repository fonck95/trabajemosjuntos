// Ajustes (administrador y coordinador): política de contacto, aviso de privacidad, datos sensibles, presupuestos y
// sesiones, el asistente y su conexión con Mnemo, puestos de votación y elección vigente, campos propios, etiquetas y
// auditoría con filtros. Los ajustes que son permisos (política de contacto, presupuestos, sesiones y el asistente)
// solo los cambia el administrador: el coordinador los ve en solo lectura y el servidor se lo impide (403). Conectar y
// desconectar Mnemo también es solo del administrador (`agente.conectar`): el coordinador ve el estado.
//
// Conectar con Mnemo (docs/agente.md): POST /api/agente/mnemo/conectar da la dirección de autorización de Mnemo y el
// navegador va ahí con location.assign (la CSP del panel no deja mandar un formulario a otro sitio, y no se abren
// ventanas). El administrador inicia sesión en Mnemo, da permiso y Mnemo lo trae de vuelta a /ajustes?code=…&state=…
// (o error=…): esta vista quita eso de la dirección antes de cualquier espera y lo manda a POST
// /api/agente/mnemo/volver, ya con la cookie de la sesión y el CSRF.
import { api, puede } from '../api.js';
import { url } from '../base.js';
import { $, aviso, avisoError, confirmar, datosForm, dialogo, fecha, html, montar, num } from '../ui.js';

const TIPOS = { texto: 'Texto', numero: 'Número', si_no: 'Sí / No', opcion: 'Lista de opciones', fecha: 'Fecha' };
const GRUPOS = { necesidad: 'Necesidades', interes: 'Grupos e intereses', rol: 'Roles' };
const DIAS = [['semana', 'Lunes a viernes'], ['sabado', 'Sábado'], ['domingo', 'Domingo']];
const SOLO_ADMIN = html`<p class="sec ancho" style="margin:0">Solo el administrador cambia estos ajustes; usted los ve en solo lectura.</p>`;
// Los roles del asistente (agente.roles y agente_mensajes_diarios): clave, quiénes lo usan y de quién es el tope
const ROLES_AGENTE = [['admin', 'Administrador', 'administrador'], ['coordinador', 'Coordinadores', 'coordinador'],
  ['planillero', 'Planilleros', 'planillero'], ['consultor', 'Consultores', 'consultor']];

// Los permisos que puede dar una cuenta de Mnemo, como los ve el administrador (en la página de permisos de Mnemo salen
// con su propio texto). `mnemo:model` es el que deja al asistente usar los modelos de la cuenta
const PERMISOS_MNEMO = {
  'mnemo:model': 'Usar sus modelos de IA y sus créditos', 'mnemo:read': 'Leer su información',
  'mnemo:workspace.write': 'Crear y editar eventos, documentos y borradores de formularios',
  'mnemo:memory.write': 'Proponer recuerdos', 'mnemo:share': 'Pedirle compartir', 'mnemo:publish': 'Pedirle publicar',
  'mnemo:study.write': 'Crear y editar mazos', 'mnemo:business.write': 'Registrar ventas y productos',
  'mnemo:forms.responses': 'Leer las respuestas de sus formularios', 'mnemo:delete': 'Pedirle borrar',
};
// Por qué se cayó la conexión (`motivo` de la conexión)
const CAIDA_MNEMO = {
  revocada: 'Mnemo ya no la acepta: se revocó en Mnemo (Tu cuenta → Agentes conectados), venció por no usarse o la cuenta se desactivó.',
  clave: 'Cambió la clave del administrador del panel y la conexión guardada ya no se puede leer.',
  error: 'Mnemo respondió algo inesperado al renovarla.',
};
const SIN_PERMISO_MODELO = 'Mnemo se conectó sin permiso para usar sus modelos: vuelva a conectar y marque esa casilla '
  + '(«Usar tus modelos de IA y tus créditos»).';
// Lo que trae la vuelta de Mnemo a /ajustes (RFC 6749 y RFC 9207), con los topes de POST /api/agente/mnemo/volver
const VUELTA = [['state', 200], ['code', 2000], ['iss', 300], ['error', 100], ['error_description', 500]];
const LOOPBACK = ['127.0.0.1', 'localhost', '[::1]'];

/** La vuelta de Mnemo tras conectar (`/ajustes?code=…&state=…&iss=…`, o `error=…`): se lee de `q` y se quita de la
 * dirección en el acto, de forma síncrona: así el código no queda en el historial ni en una recarga, y el asistente no
 * lo manda al modelo como si fueran filtros. Devuelve lo que va a POST /api/agente/mnemo/volver (`{state, code?, iss?,
 * error?, error_description?}`), `{}` si llegó sin `state` (no sirve de nada) o null si no es una vuelta de Mnemo. */
export function tomarVuelta(q) {
  if (!q || !VUELTA.some(([k]) => q.has(k))) return null;
  const v = {};
  for (const [k, max] of VUELTA) {
    const x = q.get(k);
    if (x) v[k] = x.slice(0, max);
  }
  history.replaceState(history.state, '', url('/ajustes'));
  return v.state ? v : {};
}

/** La dirección de autorización que devolvió el panel, si se puede ir: https, o http a la máquina local (Mnemo en
 * local). Sin usuario ni clave. Si no, null: no se va a ninguna parte. */
export function direccionDeMnemo(d) {
  if (typeof d !== 'string' || d.length > 4000) return null;
  let u;
  try { u = new URL(d); } catch { return null; }
  if (u.username || u.password) return null;
  return u.protocol === 'https:' || (u.protocol === 'http:' && LOOPBACK.includes(u.hostname)) ? u.href : null;
}

const casilla = (nombre, marcada, texto) => html`<label class="interruptor ancho"><span>${texto}</span><input type="checkbox" name="${nombre}" ${marcada ? 'checked' : ''}></label>`;
const numero = (nombre, valor, texto, min, max) => html`<label class="campo"><span>${texto}</span><input type="number" name="${nombre}" value="${valor}" min="${min}" max="${max}" required></label>`;

function franja(clave, valor, texto) {
  const activa = Array.isArray(valor);
  return html`<div class="campo"><span>${texto}</span><div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
    <label style="display:flex;gap:4px;align-items:center"><input type="checkbox" data-dia="${clave}" ${activa ? 'checked' : ''}> Se contacta</label>
    <input class="entrada" type="time" data-desde="${clave}" value="${activa ? valor[0] : '08:00'}" style="width:auto">
    <input class="entrada" type="time" data-hasta="${clave}" value="${activa ? valor[1] : '17:00'}" style="width:auto"></div></div>`;
}

// Si el asistente está encendido y con qué modelo (el de las conversaciones nuevas: cada una sigue con el que empezó).
// Lo decide el servidor (`proveedor` de GET /api/agente/estado): Mnemo si está conectado con permiso para usar sus
// modelos; si no, la clave de Anthropic del servidor (modo directo), si la hay. `est` es el estado, o null si no
// respondió: entonces no se dice nada
function estadoAgente(est) {
  if (!est) return '';
  const sinModelo = est.motivo === 'sin_configurar' || est.proveedor === null;
  if (sinModelo) {
    return html`<div class="aviso-legal">El asistente está apagado: no tiene un modelo que usar. Se enciende cuando el administrador conecta Mnemo (aquí abajo) con permiso para usar sus modelos; estos ajustes rigen desde entonces.</div>`;
  }
  const rol = est.motivo === 'rol' ? ' Su rol no está entre quienes lo usan.' : '';
  const con = { mnemo: ' y usa los modelos de la cuenta de Mnemo conectada',
    anthropic: ' en modo directo: usa la clave de Anthropic del servidor, porque Mnemo no está conectado con permiso para usar sus modelos' }[est.proveedor] || '';
  return html`<p class="mnemo-rige">El asistente está encendido${con}.${rol}</p>`;
}

/** El bloque «Conexión con Mnemo» de la sección Asistente. `c` es `mnemo.conexion` de GET /api/agente/estado (la vista
 * de la conexión, sin secretos: {estado, motivo, url, cuenta, alcances, modelo, desde, url_sugerida}); `nota`, lo que
 * pasó al conectar o desconectar ({tipo: 'ok' | 'alerta' | 'error', texto}) o null. Los botones y la dirección son
 * solo para quien puede conectar (el administrador); el coordinador ve el estado. */
function bloqueMnemo(c, nota) {
  const admin = puede('agente.conectar');
  const estado = ['conectada', 'caida'].includes(c?.estado) ? c.estado : 'sin_conectar';
  const chip = { conectada: html`<span class="chip verde">Conectado</span>`, caida: html`<span class="chip rojo">Conexión caída</span>`,
    sin_conectar: html`<span class="chip borde">Sin conectar</span>` }[estado];
  const partes = [];
  if (estado === 'conectada') {
    const desde = c.desde ? ` desde ${fecha(c.desde, true)}` : '';
    partes.push(html`<p>Conectado como <b>${c.cuenta || 'una cuenta de Mnemo'}</b>${desde}.</p>`);
    if (c.url) partes.push(html`<p class="mnemo-dato">Dirección: ${c.url}</p>`);
    const orden = Object.keys(PERMISOS_MNEMO);
    const alcances = (Array.isArray(c.alcances) ? c.alcances : []).filter((a) => typeof a === 'string')
      .sort((a, b) => (orden.indexOf(a) + 1 || 99) - (orden.indexOf(b) + 1 || 99));
    if (alcances.length) {
      partes.push(html`<div class="chips" aria-label="Permisos que dio la cuenta">${alcances.map((a) => html`<span class="chip borde">${PERMISOS_MNEMO[a] || a}</span>`)}</div>`);
    }
    if (!c.modelo) partes.push(html`<p class="mnemo-nota alerta" role="alert">${SIN_PERMISO_MODELO}</p>`);
  } else if (estado === 'caida') {
    partes.push(html`<p>La conexión con Mnemo dejó de valer. ${CAIDA_MNEMO[c.motivo] || ''}</p>`);
    partes.push(html`<p>${admin ? 'Vuelva a conectar para que el asistente use otra vez los modelos de la cuenta.'
      : 'El administrador tiene que volver a conectarla.'}</p>`);
  } else {
    partes.push(html`<p>${admin
      ? 'El asistente usa los modelos y los créditos de una cuenta de Mnemo. Conéctela aquí: se inicia sesión en Mnemo, se da permiso y se vuelve a esta página; no hay que copiar claves.'
      : 'El asistente usa los modelos y los créditos de una cuenta de Mnemo, y la conecta el administrador.'}</p>`);
  }
  partes.push(html`<p class="mnemo-aviso">Todos los roles que usan el asistente gastan los modelos y los créditos de esa cuenta; los mensajes por día de cada rol (abajo) siguen valiendo. Con Mnemo conectado, lo que el asistente consulta de la base viaja a Mnemo y, de ahí, al proveedor de modelos que esa cuenta tenga elegido.</p>`);
  if (nota) partes.push(html`<p class="mnemo-nota resultado ${nota.tipo}" role="${nota.tipo === 'ok' ? 'status' : 'alert'}">${nota.texto}</p>`);
  let acciones;
  if (admin) {
    const dir = (estado !== 'sin_conectar' ? c.url : null) || c?.url_sugerida || '';
    acciones = html`<form id="f-mnemo" class="form" novalidate>
      <label class="campo ancho"><span>Dirección MCP de Mnemo</span><input name="url" type="url" inputmode="url" maxlength="300" value="${dir}" placeholder="https://…/mcp" autocomplete="off" spellcheck="false"></label>
      <div class="ancho mnemo-botones"><button class="btn primario" id="mnemo-conectar">${estado === 'sin_conectar' ? 'Conectar con Mnemo' : 'Volver a conectar'}</button>
        ${estado !== 'sin_conectar' ? html`<button type="button" class="btn peligro" id="mnemo-desconectar">Desconectar</button>` : ''}</div>
      <p class="ancho mnemo-ayuda">Se abre Mnemo: inicie sesión con la cuenta que va a poner los modelos, deje marcado «Usar tus modelos de IA y tus créditos» y pulse «Permitir». Mnemo lo trae de vuelta aquí. Cambiar la dirección y volver a conectar cambia de Mnemo.</p>
    </form>`;
  } else {
    acciones = html`<p class="mnemo-ayuda">Solo el administrador conecta o desconecta Mnemo.</p>`;
  }
  return html`<div class="mnemo-conexion" id="mnemo-conexion" data-estado="${estado}">
    <h3>Conexión con Mnemo ${chip}</h3>${partes}${acciones}</div>`;
}

export async function vistaAjustes(el, { q } = {}) {
  // Lo primero, antes de cualquier await: si es la vuelta de Mnemo, sale de la dirección
  const vuelta = tomarVuelta(q);
  let filtros = {};
  let notaMnemo = null; // lo que pasó al conectar o desconectar Mnemo, hasta la próxima acción

  async function pintar() {
    // El estado del asistente es solo un aviso: si no responde, Ajustes se pinta igual
    const [cat, aud, aj, est] = await Promise.all([api.get('/api/catalogos'), api.get('/api/auditoria', filtros), api.get('/api/ajustes'),
      api.get('/api/agente/estado').catch(() => null)]);
    const puestos = await api.get('/api/puestos', { eleccion: aj.eleccion_vigente, todos: 1 });
    if (!el.isConnected) return;
    const av = aj.aviso_privacidad || {};
    const soloLectura = aj.puede_modificar_permisos === false;
    const ag = aj.agente || {};
    const rolesAgente = new Set(Array.isArray(ag.roles) ? ag.roles : []);
    const mensajes = aj.agente_mensajes_diarios || {};
    montar(el, html`
      <div class="cabecera"><div><h1>Ajustes</h1><div class="sub">Reglas de contacto, privacidad y catálogos. Cada cambio queda en la auditoría.</div></div></div>
      <div class="rejilla r-12">
        <section class="tarjeta c-6">
          <h2>Política de contacto</h2>
          <form id="f-politica" class="form" style="margin-top:12px">
            ${casilla('contactar_pendientes', aj.contactar_pendientes, 'Llamar también a quien tiene la autorización pendiente, para pedirla')}
            <div class="aviso-legal ancho">Riesgo legal: contactar sin autorización previa lo asume el Responsable (Circular 002/2026 de la SIC, instr. 5). Aun encendido, nunca alcanza a quien solo viene de la base de trámites, recogida para otra finalidad (Ley 1581, art. 4 b).</div>
            ${numero('dias_entre_intentos', aj.dias_entre_intentos, 'Días entre intentos', 1, 60)}
            ${numero('max_intentos_sin_exito', aj.max_intentos_sin_exito, 'Máximo de intentos sin respuesta', 1, 20)}
            ${casilla('seguimiento_activo', aj.seguimiento_activo, 'Lista de seguimiento a quienes ya contestaron')}
            ${numero('dias_seguimiento', aj.dias_seguimiento, 'Días para el seguimiento', 7, 365)}
            ${DIAS.map(([k, t]) => franja(k, aj.horario?.[k], t))}
            <p class="sec ancho" style="margin:0">Fuera del horario el registro no se bloquea: queda marcado y se avisa (Ley 2300 de 2023).</p>
            ${soloLectura ? SOLO_ADMIN : html`<div class="ancho"><button class="btn primario">Guardar política</button></div>`}
          </form>
        </section>
        <section class="tarjeta c-6">
          <h2>Aviso de privacidad y Responsable</h2>
          <form id="f-aviso" class="form" style="margin-top:12px">
            <label class="campo"><span>Versión del aviso</span><input name="version" value="${av.version || ''}" maxlength="40" required></label>
            <label class="campo"><span>Responsable del tratamiento</span><input name="responsable" value="${av.responsable || ''}" maxlength="200"></label>
            <label class="campo"><span>Contacto</span><input name="contacto" value="${av.contacto || ''}" maxlength="200"></label>
            <label class="campo"><span>Canal para ejercer los derechos</span><input name="canal_derechos" value="${av.canal_derechos || ''}" maxlength="200"></label>
            <label class="campo ancho"><span>Texto del aviso (va en la hoja «Aviso» de la planilla)</span><textarea name="texto" maxlength="8000" style="min-height:140px">${av.texto || ''}</textarea></label>
            <div class="ancho"><button class="btn primario">Guardar aviso</button></div>
          </form>
        </section>
        <section class="tarjeta c-6">
          <h2>Presupuestos y sesiones</h2>
          <form id="f-limites" class="form" style="margin-top:12px">
            ${numero('presupuesto_planillero', aj.presupuesto_diario?.planillero, 'Personas por día · planillero', 10, 100000)}
            ${numero('presupuesto_consultor', aj.presupuesto_diario?.consultor, 'Personas por día · consultor', 10, 100000)}
            ${numero('horas_max', aj.sesion?.horas_max, 'Horas máximas de una sesión', 1, 24)}
            ${numero('inactividad_min', aj.sesion?.inactividad_min, 'Minutos de inactividad', 5, 600)}
            ${numero('max_por_usuario', aj.sesion?.max_por_usuario, 'Dispositivos por usuario', 1, 10)}
            ${numero('tope_cedulas_dictadas', aj.tope_cedulas_dictadas, 'Cédulas dictadas por consultor y día', 0, 500)}
            ${soloLectura ? SOLO_ADMIN : html`<div class="ancho"><button class="btn primario">Guardar límites</button></div>`}
          </form>
        </section>
        <section class="tarjeta c-6">
          <h2>Datos sensibles y compromiso</h2>
          <form id="f-otros" class="form" style="margin-top:12px">
            ${casilla('sensibles_activos', aj.sensibles_activos, 'Recoger datos sensibles (etnia, discapacidad, víctima), solo con autorización explícita por categoría')}
            ${numero('dias_reintento_dato', aj.dias_reintento_dato, 'Días antes de volver a pedir un dato que no dieron', 7, 730)}
            <label class="campo"><span>Versión del compromiso de confidencialidad</span><input name="compromiso_version" value="${aj.compromiso_version || ''}" maxlength="40" required></label>
            <label class="campo ancho"><span>Enlace para consultar el puesto (Registraduría; verifíquelo antes de usarlo)</span><input name="enlace_consulta_puesto" type="url" value="${aj.enlace_consulta_puesto || ''}" maxlength="300" placeholder="https://…"></label>
            <p class="sec ancho" style="margin:0">Vigencia de la base: ${aj.vigencia_base ? fecha(aj.vigencia_base) : 'sin definir'}. Cambiar la versión del compromiso pide a planilleros y consultores aceptarlo de nuevo.</p>
            <div class="ancho"><button class="btn primario">Guardar</button></div>
          </form>
        </section>
        <section class="tarjeta c-12">
          <h2>Asistente</h2>
          <div class="asistente-cabeza">${estadoAgente(est)}${est?.mnemo?.conexion ? bloqueMnemo(est.mnemo.conexion, notaMnemo) : ''}</div>
          <form id="f-agente" class="form" style="margin-top:12px">
            <div class="campo ancho"><span>Quiénes lo usan (cada uno con los permisos, el alcance y el presupuesto diario de su rol)</span>
              <div class="chips">${ROLES_AGENTE.map(([k, t]) => html`<label class="chip opcion"><input type="checkbox" name="rol_${k}" ${rolesAgente.has(k) ? 'checked' : ''}> ${t}</label>`)}</div></div>
            ${casilla('escritura', ag.escritura !== false, 'Proponer cambios en la base (notas, acercamientos, fichas, reuniones…): cada uno se aprueba en una tarjeta antes de guardarse')}
            ${casilla('mnemo_coordinadores', ag.mnemo_coordinadores === true, 'Los coordinadores también usan las herramientas de Mnemo (documentos, calendario, formularios y memoria), con la cuenta de Mnemo del administrador: lo que hagan allá queda a nombre del administrador')}
            ${numero('retencion_dias', ag.retencion_dias, 'Días que se guardan las conversaciones', 1, 365)}
            ${ROLES_AGENTE.map(([k, , t]) => numero(`mensajes_${k}`, mensajes[k], `Mensajes por día · ${t}`, 1, 5000))}
            <div class="aviso-legal ancho">Lo que el asistente consulta de la base viaja al proveedor del modelo: con Mnemo conectado, a Mnemo y, de ahí, al proveedor de modelos que esa cuenta tenga elegido; en modo directo, a Anthropic. Son terceros, posiblemente en el exterior: datos mínimos, cédulas y teléfonos enmascarados, nunca datos sensibles ni listas, y nada de quien no autorizó. Revise el aviso de privacidad y la autorización con un abogado antes de encenderlo para el equipo. Las conversaciones se borran solas a los días indicados desde su último mensaje; bajar el plazo acorta también las que ya existen.</div>
            ${soloLectura ? SOLO_ADMIN : html`<div class="ancho"><button class="btn primario">Guardar asistente</button></div>`}
          </form>
        </section>
        <section class="tarjeta c-12">
          <header style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap"><h2>Puestos de votación</h2>
            <label class="campo" style="min-width:220px"><span>Elección vigente</span><select id="eleccion">${(aj.elecciones || []).map((x) => html`<option value="${x}" ${x === aj.eleccion_vigente ? 'selected' : ''}>${x}</option>`)}</select></label></header>
          <p class="sec">Catálogo DIVIPOL de la elección vigente. Las votaciones de otra elección quedan «por confirmar» sin reescribirse. Para una elección nueva, cree sus puestos y luego cámbiela aquí.</p>
          <div class="envoltura-tabla"><table class="tabla"><thead><tr><th>Código</th><th>Puesto</th><th>Zona</th><th class="num">Mesas</th><th class="num">Habilitados</th><th>Otros nombres</th><th>Estado</th><th></th></tr></thead>
            <tbody>${puestos.map((p) => html`<tr style="cursor:default"><td>${p.codigo}</td><td><b>${p.nombre}</b>${p.coord_dudosa ? html` <span class="chip ambar">coordenada dudosa</span>` : ''}</td>
              <td>${p.area || ''}</td><td class="num">${num(p.mesas)}</td><td class="num">${num(p.habilitados?.total)}</td>
              <td class="sec">${(p.alias || []).join(', ')}${(p.alias_ambiguos || []).length ? html`<div>Ambiguos: ${p.alias_ambiguos.join(', ')}</div>` : ''}</td>
              <td>${p.activo === false ? html`<span class="chip">Inactivo</span>` : html`<span class="chip verde">Activo</span>`}</td>
              <td><button class="btn chico" data-puesto="${p.id}">Editar</button></td></tr>`)}</tbody></table></div>
          <p style="margin-top:10px"><button class="btn chico" id="nuevo-puesto">Nuevo puesto</button></p>
        </section>
        <section class="tarjeta c-6">
          <h2>Campos propios del perfil</h2>
          <p class="sec">Por ejemplo: «¿Tiene acueducto?», «Cultivo principal», «Tipo de vivienda». Aparecen en cada ficha y en la exportación.</p>
          <form id="f-campo" class="form" style="margin:12px 0">
            <label class="campo"><span>Nombre del campo</span><input name="etiqueta" required minlength="2" maxlength="60"></label>
            <label class="campo"><span>Tipo</span><select name="tipo">${Object.entries(TIPOS).map(([k, t]) => html`<option value="${k}">${t}</option>`)}</select></label>
            <label class="campo ancho"><span>Opciones (si es lista, separadas por coma)</span><input name="opciones" placeholder="Propia, Arrendada, Familiar"></label>
            ${casilla('sensible', false, 'Dato sensible (solo lo ve el administrador)')}
            <div class="ancho"><button class="btn primario">Agregar campo</button></div>
          </form>
          <div class="envoltura-tabla"><table class="tabla"><thead><tr><th>Campo</th><th>Tipo</th><th>Estado</th><th></th></tr></thead><tbody>
            ${cat.campos.length ? cat.campos.map((c) => html`<tr style="cursor:default"><td><b>${c.etiqueta}</b>${c.sensible ? html` <span class="chip ambar">Sensible</span>` : ''}${(c.opciones || []).length ? html`<div class="sec">${c.opciones.join(' · ')}</div>` : ''}</td>
              <td>${TIPOS[c.tipo]}</td><td>${c.activo ? html`<span class="chip verde">Activo</span>` : html`<span class="chip">Oculto</span>`}</td>
              <td><button class="btn chico" data-campo="${c.id}" data-activo="${c.activo ? 0 : 1}">${c.activo ? 'Ocultar' : 'Mostrar'}</button></td></tr>`)
              : html`<tr><td colspan="4" class="sec">Aún no hay campos propios.</td></tr>`}
          </tbody></table></div>
        </section>
        <section class="tarjeta c-6">
          <h2>Necesidades, grupos y roles</h2>
          <form id="f-et" style="display:flex;gap:8px;margin:12px 0;flex-wrap:wrap;align-items:center">
            <input class="entrada" name="nombre" placeholder="Nueva etiqueta" required minlength="2" style="flex:1 1 180px">
            <select class="entrada" name="grupo" style="width:auto">${Object.entries(GRUPOS).map(([k, t]) => html`<option value="${k}">${t}</option>`)}</select>
            <label style="display:flex;gap:4px;align-items:center"><input type="checkbox" name="sensible"> Sensible</label>
            <button class="btn primario">Agregar</button>
          </form>
          <p class="sec" style="margin-top:0">Las sensibles (salud, víctima, liderazgo…) solo las ve el administrador.</p>
          ${Object.entries(GRUPOS).map(([g, t]) => html`<h3 style="font-size:13px;margin:16px 0 8px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em">${t}</h3>
            <div class="chips">${cat.etiquetas.filter((e) => e.grupo === g).map((e) => html`<span class="chip ${e.sensible ? 'ambar' : 'borde'}">${e.nombre} · ${num(e.n)} <button class="btn fantasma chico" style="padding:0 4px" data-borrar-et="${e.id}" aria-label="Borrar ${e.nombre}">✕</button></span>`)}</div>`)}
        </section>
        <section class="tarjeta c-12">
          <header><h2>Auditoría</h2><span class="nota">${num(aud.total)} acciones registradas (las 100 más recientes del filtro)</span></header>
          <form id="f-aud" class="form" style="margin:12px 0">
            <label class="campo"><span>Acción</span><input name="accion" value="${filtros.accion || ''}" placeholder="editar, importar, ingreso…"></label>
            <label class="campo"><span>Usuario (uid)</span><input name="uid" type="number" min="0" value="${filtros.uid ?? ''}"></label>
            <label class="campo"><span>Desde</span><input name="desde" type="date" value="${filtros.desde || ''}"></label>
            <label class="campo"><span>Hasta</span><input name="hasta" type="date" value="${filtros.hasta || ''}"></label>
            <div class="ancho"><button class="btn">Filtrar</button></div>
          </form>
          <div class="envoltura-tabla" style="max-height:420px;overflow:auto"><table class="tabla"><thead><tr><th>Cuándo</th><th>Usuario</th><th>Acción</th><th>Sobre</th><th>IP</th></tr></thead>
            <tbody>${aud.filas.map((a) => html`<tr style="cursor:default"><td>${fecha(a.ts, true)}</td><td>${a.usuario || 'sistema'}${a.rol && a.rol !== 'admin' ? html` <span class="sec">(${a.rol})</span>` : ''}</td><td>${(a.accion || '').replace(/_/g, ' ')}</td>
              <td>${a.entidad === 'persona' ? html`<a href="/personas/${a.entidad_id}" data-ruta>persona ${a.entidad_id}</a>` : a.entidad ? `${a.entidad} ${a.entidad_id ?? ''}` : ''}</td><td class="sec">${a.ip || ''}</td></tr>`)}</tbody></table></div>
        </section>
        <section class="tarjeta c-12">
          <h2>Protección de datos personales</h2>
          <div class="aviso-legal">Esta base contiene datos personales y algunos sensibles (afiliación política, condición de víctima, salud). La Ley 1581 de 2012 exige autorización previa,
            expresa e informada del titular, informar la finalidad, y atender consultas, correcciones y supresiones. La autorización de cada ficha, las solicitudes de titulares
            en Calidad de datos y la opción «Suprimir datos» existen para eso. Los datos de bases oficiales (como las del SISBÉN) solo pueden usarse para la finalidad con la que se recogieron.</div>
        </section>
      </div>`);
    if (soloLectura) {  // el coordinador ve la política, los límites y el asistente, pero no los cambia
      for (const id of ['#f-politica', '#f-limites', '#f-agente']) {
        for (const c of $(id, el).querySelectorAll('input, select, textarea')) c.disabled = true;
      }
      const dePermisos = new Set(aj.ajustes_de_permisos || []);  // datos sensibles y compromiso: también solo A
      for (const c of $('#f-otros', el).querySelectorAll('[name]')) if (dePermisos.has(c.name)) c.disabled = true;
    }
  }

  const guardar = async (cuerpo, texto) => {
    await api.put('/api/ajustes', cuerpo);
    aviso(texto);
    await pintar();
  };

  // ── La conexión con Mnemo (solo el administrador; el servidor también lo exige) ──
  const fallo = (err, texto) => (err?.estado === 401 ? null : { tipo: 'error', texto: err?.message || texto });

  /** Deja en el bloque de Mnemo lo que pasó (o lo quita), sin repintar la vista: no se pierde la dirección escrita. */
  function anotarMnemo(nota) {
    notaMnemo = nota;
    const bloque = $('#mnemo-conexion', el);
    bloque?.querySelector('.mnemo-nota.resultado')?.remove();
    const form = bloque?.querySelector('#f-mnemo');
    if (!nota || !form) return;
    const p = document.createElement('p');
    p.className = `mnemo-nota resultado ${nota.tipo}`;
    p.setAttribute('role', nota.tipo === 'ok' ? 'status' : 'alert');
    p.textContent = nota.texto;
    form.before(p);
  }

  /** La vuelta de Mnemo, ya fuera de la dirección: el panel canjea el código con la sesión de quien empezó a conectar. */
  async function volverDeMnemo(v) {
    if (!puede('agente.conectar')) return;
    if (!v.state) {
      notaMnemo = { tipo: 'error', texto: 'La respuesta de Mnemo llegó incompleta: no se conectó nada. Vuelva a conectar.' };
      return;
    }
    montar(el, html`<div class="cargando" role="status">Terminando de conectar con Mnemo…</div>`);
    try {
      const c = await api.post('/api/agente/mnemo/volver', v);
      // Lo demás (la cuenta, los permisos y si falta el de los modelos) lo dice el bloque
      if (c?.estado === 'conectada') aviso('Mnemo quedó conectado');
    } catch (err) {
      notaMnemo = fallo(err, 'No se pudo terminar de conectar con Mnemo.');
      avisoError(err, 8000);
    }
  }

  /** «Conectar con Mnemo» / «Volver a conectar»: el panel prepara la autorización y el navegador va a Mnemo. */
  async function conectarMnemo(f) {
    const boton = $('#mnemo-conectar', f);
    const etiqueta = boton.textContent;
    const dir = (f.elements.url?.value || '').trim();
    boton.disabled = true;
    try {
      const r = await api.post('/api/agente/mnemo/conectar', dir ? { url: dir } : {});
      const destino = direccionDeMnemo(r?.autorizar);
      if (!destino) throw new Error('El panel devolvió una dirección de Mnemo que no es segura: no se abrió.');
      boton.textContent = 'Abriendo Mnemo…';
      // Si se vuelve con «Atrás» y el navegador restaura esta página tal cual, el botón sirve otra vez
      addEventListener('pageshow', () => { boton.disabled = false; boton.textContent = etiqueta; }, { once: true });
      location.assign(destino);
    } catch (err) {
      boton.disabled = false;
      anotarMnemo(fallo(err, 'No se pudo conectar con Mnemo.'));
      avisoError(err, 8000);
    }
  }

  /** «Desconectar», con confirmación: el panel revoca la conexión en Mnemo y la olvida. */
  async function desconectarMnemo(boton) {
    const si = await confirmar('¿Desconectar Mnemo? El asistente deja de usar los modelos y las herramientas de esa cuenta '
      + 'hasta que se vuelva a conectar, y la conexión se revoca en Mnemo.', { si: 'Desconectar', peligro: true });
    if (!si) return;
    const caida = $('#mnemo-conexion', el)?.dataset.estado === 'caida';
    boton.disabled = true;
    try {
      const r = await api.del('/api/agente/mnemo');
      if (r?.revocada === false) {
        notaMnemo = { tipo: 'alerta', texto: 'El panel ya no usa la conexión, pero Mnemo no confirmó que la revocó: revóquela en '
          + 'Mnemo, en Tu cuenta → Agentes conectados.' };
      } else if (r?.revocada == null && caida) {
        notaMnemo = { tipo: 'alerta', texto: 'El panel ya no guarda la conexión. Si todavía aparece en Mnemo (Tu cuenta → '
          + 'Agentes conectados), revóquela ahí.' };
      } else {
        notaMnemo = null;
      }
      aviso(r?.revocada ? 'Mnemo quedó desconectado y la conexión, revocada en Mnemo' : 'Mnemo quedó desconectado');
    } catch (err) {
      notaMnemo = fallo(err, 'No se pudo desconectar Mnemo.');
      avisoError(err);
    }
    await pintar();
  }

  function horario(f) {
    const h = {};
    for (const [k] of DIAS) {
      const activo = $(`[data-dia="${k}"]`, f).checked;
      h[k] = activo ? [$(`[data-desde="${k}"]`, f).value, $(`[data-hasta="${k}"]`, f).value] : false;
    }
    return h;
  }

  function editarPuesto(p) {
    const nuevo = !p;
    p = p || { codigo: '', nombre: '', mesas: 1, alias: [], alias_ambiguos: [], area: 'rural', activo: true, habilitados: { mujeres: 0, hombres: 0 } };
    const { el: d, cerrar } = dialogo({ titulo: nuevo ? 'Nuevo puesto de votación' : `Puesto ${p.codigo}`,
      cuerpo: html`<form class="form" id="f-puesto">
        ${nuevo ? html`<label class="campo"><span>Elección</span><input name="eleccion" value="${$('#eleccion', el)?.value || ''}" pattern="[0-9]{4}-[a-z0-9-]{3,40}" required></label>
          <label class="campo"><span>Código (zona-puesto)</span><input name="codigo" pattern="[0-9]{2}-[0-9]{2}" placeholder="99-65" required></label>` : ''}
        <label class="campo ancho"><span>Nombre</span><input name="nombre" value="${p.nombre}" minlength="3" maxlength="120" required></label>
        <label class="campo"><span>Mesas</span><input name="mesas" type="number" min="1" max="300" value="${p.mesas}" required></label>
        <label class="campo"><span>Zona</span><select name="area"><option value="cabecera" ${p.area === 'cabecera' ? 'selected' : ''}>Cabecera</option><option value="rural" ${p.area !== 'cabecera' ? 'selected' : ''}>Rural</option></select></label>
        <label class="campo"><span>Mujeres habilitadas</span><input name="mujeres" type="number" min="0" value="${p.habilitados?.mujeres ?? 0}"></label>
        <label class="campo"><span>Hombres habilitados</span><input name="hombres" type="number" min="0" value="${p.habilitados?.hombres ?? 0}"></label>
        <label class="campo ancho"><span>Otros nombres (uno por línea)</span><textarea name="alias">${(p.alias || []).join('\n')}</textarea></label>
        <label class="campo ancho"><span>Nombres ambiguos (no se reconocen solos)</span><textarea name="alias_ambiguos">${(p.alias_ambiguos || []).join('\n')}</textarea></label>
        ${casilla('activo', p.activo !== false, 'Activo')}</form>`,
      pie: html`<button class="btn" data-cerrar>Cancelar</button><button class="btn primario" id="g">Guardar</button>` });
    $('#g', d).onclick = async () => {
      const f = $('#f-puesto', d);
      if (!f.reportValidity()) return;
      const v = datosForm(f);
      const lineas = (s) => String(s || '').split('\n').map((x) => x.trim()).filter(Boolean);
      const cuerpo = { nombre: v.nombre, mesas: Number(v.mesas), area: v.area, alias: lineas(v.alias), alias_ambiguos: lineas(v.alias_ambiguos),
        activo: f.activo.checked, habilitados: { mujeres: Number(v.mujeres || 0), hombres: Number(v.hombres || 0) } };
      try {
        if (nuevo) await api.post('/api/puestos', { ...cuerpo, eleccion: v.eleccion, codigo: v.codigo });
        else await api.patch(`/api/puestos/${p.id}`, cuerpo);
        cerrar(); aviso('Puesto guardado'); await pintar();
      } catch (err) { avisoError(err); }
    };
  }

  el.addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = e.target;
    try {
      if (f.id === 'f-politica') {
        const v = datosForm(f);
        await guardar({ contactar_pendientes: f.contactar_pendientes.checked, seguimiento_activo: f.seguimiento_activo.checked,
          dias_entre_intentos: Number(v.dias_entre_intentos), max_intentos_sin_exito: Number(v.max_intentos_sin_exito),
          dias_seguimiento: Number(v.dias_seguimiento), horario: horario(f) }, 'Política de contacto guardada');
      } else if (f.id === 'f-aviso') {
        // Un campo vacío se guarda vacío (null no cambiaría nada)
        await guardar({ aviso_privacidad: Object.fromEntries(Object.entries(datosForm(f)).map(([k, v]) => [k, v ?? ''])) }, 'Aviso guardado');
      } else if (f.id === 'f-limites') {
        const v = datosForm(f);
        await guardar({ presupuesto_diario: { planillero: Number(v.presupuesto_planillero), consultor: Number(v.presupuesto_consultor) },
          sesion: { horas_max: Number(v.horas_max), inactividad_min: Number(v.inactividad_min), max_por_usuario: Number(v.max_por_usuario) },
          tope_cedulas_dictadas: Number(v.tope_cedulas_dictadas) }, 'Límites guardados');
      } else if (f.id === 'f-otros') {
        const v = datosForm(f);
        await guardar({ sensibles_activos: f.sensibles_activos.checked, dias_reintento_dato: Number(v.dias_reintento_dato),
          compromiso_version: v.compromiso_version,
          ...(v.enlace_consulta_puesto ? { enlace_consulta_puesto: v.enlace_consulta_puesto } : {}) }, 'Ajustes guardados');
      } else if (f.id === 'f-agente') {
        const v = datosForm(f);
        const roles = ROLES_AGENTE.map(([k]) => k).filter((k) => v[`rol_${k}`] === true);
        // Quitarse a sí mismo lo apaga también para el administrador: que sea a propósito
        if (!roles.includes('admin') && !await confirmar(roles.length
          ? 'Sin el administrador marcado, a usted tampoco le aparecerá el asistente. ¿Guardar así?'
          : 'Sin ningún rol marcado, el asistente queda apagado para todos, también para usted. ¿Guardar así?', { si: 'Guardar' })) return;
        await guardar({ agente: { roles, escritura: v.escritura === true, mnemo_coordinadores: v.mnemo_coordinadores === true,
          retencion_dias: Number(v.retencion_dias) },
        agente_mensajes_diarios: Object.fromEntries(ROLES_AGENTE.map(([k]) => [k, Number(v[`mensajes_${k}`])])) }, 'Asistente guardado');
      } else if (f.id === 'f-campo') {
        await api.post('/api/campos', { etiqueta: f.etiqueta.value, tipo: f.tipo.value, sensible: f.sensible.checked,
          opciones: f.opciones.value.split(',').map((s) => s.trim()).filter(Boolean) });
        aviso('Campo agregado'); await pintar();
      } else if (f.id === 'f-et') {
        await api.post('/api/etiquetas', { nombre: f.nombre.value, grupo: f.grupo.value, sensible: f.sensible.checked });
        aviso('Etiqueta agregada'); await pintar();
      } else if (f.id === 'f-aud') {
        const v = datosForm(f);
        filtros = Object.fromEntries(Object.entries(v).filter(([, x]) => x !== '' && x != null));
        await pintar();
      } else if (f.id === 'f-mnemo') {
        await conectarMnemo(f);
      }
    } catch (err) { avisoError(err); }
  });
  el.addEventListener('change', async (e) => {
    if (e.target.id !== 'eleccion') return;
    const nueva = e.target.value;
    if (!await confirmar(`¿Cambiar la elección vigente a ${nueva}? Las votaciones de otra elección quedarán «por confirmar».`, { si: 'Cambiar' })) { await pintar(); return; }
    try { await guardar({ eleccion_vigente: nueva }, 'Elección vigente cambiada'); } catch (err) { avisoError(err); await pintar(); }
  });
  el.addEventListener('click', async (e) => {
    const c = e.target.closest('[data-campo]');
    if (c) { await api.patch(`/api/campos/${c.dataset.campo}`, { activo: c.dataset.activo === '1' }); pintar(); return; }
    const p = e.target.closest('[data-puesto]');
    if (p) {
      const lista = await api.get('/api/puestos', { eleccion: $('#eleccion', el)?.value, todos: 1 });
      editarPuesto(lista.find((x) => String(x.id) === p.dataset.puesto));
      return;
    }
    if (e.target.closest('#nuevo-puesto')) { editarPuesto(null); return; }
    const d = e.target.closest('#mnemo-desconectar');
    if (d) { await desconectarMnemo(d); return; }
    const b = e.target.closest('[data-borrar-et]');
    if (b && await confirmar('¿Borrar esta etiqueta? Se quitará de todas las personas.', { si: 'Borrar', peligro: true })) {
      await api.del(`/api/etiquetas/${b.dataset.borrarEt}`); pintar();
    }
  });
  if (vuelta) await volverDeMnemo(vuelta);
  await pintar();
}
