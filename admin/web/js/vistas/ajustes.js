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
// /api/agente/mnemo/volver, ya con la cookie de la sesión y el CSRF. Después (y al desconectar o guardar los ajustes
// del asistente) le avisa al asistente con el evento `agente:estado`: así deja de decir «no está conectado» sin
// recargar la página.
//
// La voz del asistente (docs/agente.md, «La voz clonada de Mnemo»): el bloque «Voz del asistente» elige con qué voz
// habla el panel (la del navegador o una voz clonada de la cuenta de Mnemo conectada, de GET /api/agente/voces, que solo
// se pide al administrador y con una conexión con permiso para usar las voces; sin elegir una, la automática: la que
// Mnemo ofrece a las apps), quién la hace sonar, si lee las respuestas y si narra la presentación automática; se guarda
// como `agente_voz` (PUT /api/ajustes, solo el administrador). Si la conexión no tiene el permiso de las voces, el
// bloque lo dice con un botón que vuelve a conectar (el mismo «Volver a conectar» del bloque de Mnemo). «Probar voz»
// dice la frase fija de prueba con la voz guardada (`{prueba: true}`, con la voz de la ventana: voz-panel.js) y muestra
// cuánto tardó la primera palabra en el navegador y en Mnemo. La voz clonada es un dato biométrico de su dueño: el
// bloque la marca como voz sintética y dice qué viaja a Mnemo.
//
// La respuesta inmediata (docs/agente.md, «La respuesta inmediata»): la casilla «Respuesta inmediata» del formulario
// del asistente (`agente_adelanto`, encendida por defecto; PUT /api/ajustes, solo el administrador) decide si cada
// pregunta recibe primero una o dos frases con la idea general mientras se prepara la respuesta o la presentación.
//
// Las planillas físicas por foto (`agente_planillas`: quiénes suben fotos y cuántas horas se guardan la foto y lo
// leído; ya no hay casilla de «otros formatos»: toda foto se describe y se transcribe toda hoja que liste personas, y
// un `otros_formatos` guardado de antes el servidor lo ignora) y los agentes externos por MCP (`agente_mcp`: quiénes
// crean claves con datos, si proponen cambios y los topes diarios por clave) son permisos: los guarda el administrador
// (PUT /api/ajustes) y el coordinador los ve en solo lectura. Guardar las planillas le avisa al asistente: quién puede
// adjuntar fotos sale de su estado (`adjuntos`). Las fotos las suben solo el administrador y los coordinadores; si el
// compromiso de confidencialidad vigente no deja fotografiar planillas (`compromiso_permite_fotos`), el bloque lo
// advierte y al administrador le ofrece pasar a la versión que lo permite (`compromiso_con_fotos`): cada persona lo
// acepta de nuevo en su siguiente petición, como con cualquier versión nueva.
//
// Los datos políticos (`agente_politicos`: tipo de persona, «Liderado por», listas, líderes y fuentes políticas) en el
// asistente y por MCP: dos casillas, encendidas por defecto, que guarda el administrador (el coordinador las ve en solo
// lectura). Cada rol los recibe solo como ya los ve en el panel.
import { api, puede } from '../api.js';
import { url } from '../base.js';
import { $, aviso, avisoError, confirmar, datosForm, dialogo, fecha, hayEscrito, html, montar, num } from '../ui.js';
import { tomarVoz } from '../voz-panel.js';

const TIPOS = { texto: 'Texto', numero: 'Número', si_no: 'Sí / No', opcion: 'Lista de opciones', fecha: 'Fecha' };
const GRUPOS = { necesidad: 'Necesidades', interes: 'Grupos e intereses', rol: 'Roles' };
const DIAS = [['semana', 'Lunes a viernes'], ['sabado', 'Sábado'], ['domingo', 'Domingo']];
const SOLO_ADMIN = html`<p class="sec ancho" style="margin:0">Solo el administrador cambia estos ajustes; usted los ve en solo lectura.</p>`;
// Los roles del asistente (agente.roles y agente_mensajes_diarios): clave, quiénes lo usan y de quién es el tope
const ROLES_AGENTE = [['admin', 'Administrador', 'administrador'], ['coordinador', 'Coordinadores', 'coordinador'],
  ['planillero', 'Planilleros', 'planillero'], ['consultor', 'Consultores', 'consultor']];
// Las planillas físicas por foto (`agente_planillas`) y los agentes externos por MCP (`agente_mcp`): los roles y los
// rangos que acepta el servidor (`politica.ROLES_PLANILLAS`, `RETENCION_HORAS`, `ROLES_MCP`, `LLAMADAS_DIARIAS_MCP` y
// `PERSONAS_DIARIAS_MCP`; una prueba compara los dos lados). Solo el administrador y los coordinadores: los
// planilleros y consultores nunca suben fotos de planillas ni tienen claves con datos
const ROLES_PLANILLAS = [['admin', 'Administrador'], ['coordinador', 'Coordinadores']];
const ROLES_MCP = [['admin', 'Administrador'], ['coordinador', 'Coordinadores']];
const RETENCION_HORAS = [1, 168];
const LLAMADAS_MCP = [10, 20000];
const PERSONAS_MCP = [10, 5000];

// Los permisos que puede dar una cuenta de Mnemo, como los ve el administrador (en la página de permisos de Mnemo salen
// con su propio texto). `mnemo:model` es el que deja al asistente usar los modelos de la cuenta
const PERMISOS_MNEMO = {
  'mnemo:model': 'Usar sus modelos de IA y sus créditos',
  'mnemo:voice': 'Hablar con sus voces clonadas (narrar y leer respuestas)', 'mnemo:read': 'Leer su información',
  'mnemo:workspace.write': 'Crear y editar eventos, documentos y borradores de formularios',
  'mnemo:memory.write': 'Proponer recuerdos', 'mnemo:share': 'Pedirle compartir', 'mnemo:publish': 'Pedirle publicar',
  'mnemo:study.write': 'Crear y editar mazos', 'mnemo:business.write': 'Registrar ventas y productos',
  'mnemo:forms.responses': 'Leer las respuestas de sus formularios', 'mnemo:delete': 'Pedirle borrar',
};
// Por qué se cayó la conexión (`motivo` de la conexión)
const CAIDA_MNEMO = {
  revocada: 'Mnemo ya no la acepta: se revocó en Mnemo (Tu cuenta → Agentes conectados), venció por no usarse o la cuenta se desactivó.',
  clave: 'Cambió la clave del administrador del panel y la conexión guardada ya no se puede leer.',
  alterada: 'Sus datos en la base del panel no coinciden con los que se guardaron cifrados (o se guardó con una versión anterior del panel): por seguridad, el panel dejó de usarla.',
  error: 'Mnemo respondió algo inesperado al renovarla.',
};
// Conectada sin `mnemo:model`: en Mnemo no quedó marcado ese permiso, o ese Mnemo todavía no lo ofrece (uno sin
// actualizar no muestra la casilla: no se manda a marcarla sin más)
const SIN_PERMISO_MODELO = {
  admin: 'Mnemo se conectó sin permiso para usar sus modelos: vuelva a conectar dejando marcado «Usar tus modelos de IA y '
    + 'tus créditos». Si Mnemo no muestra esa casilla, hay que actualizar Mnemo.',
  otro: 'Mnemo se conectó sin permiso para usar sus modelos: el administrador tiene que volver a conectar dejando marcado '
    + '«Usar tus modelos de IA y tus créditos». Si Mnemo no muestra esa casilla, hay que actualizar Mnemo.',
};
// Conectada con un Mnemo que no ofrece ese permiso (`ofrece_modelo` false: uno sin actualizar; el panel lo conecta así
// solo en modo directo, para sus herramientas). No hay casilla que marcar
const NO_OFRECE_MODELO = 'Este Mnemo todavía no ofrece «Usar tus modelos de IA y tus créditos»: el asistente usa sus '
  + 'herramientas, pero no sus modelos. Para usarlos hay que actualizar Mnemo y volver a conectar.';
// El aviso al asistente (agente.js, EVENTO_ESTADO) de que su estado cambió: lo guarda unos minutos y, sin esto, seguiría
// diciendo que no está conectado hasta recargar la página
const EVENTO_ESTADO = 'agente:estado';
// La voz del asistente (`agente_voz`): con qué voz habla el panel
const MOTORES_VOZ = [['navegador', 'Voz del navegador'], ['mnemo', 'Voz clonada de Mnemo']];
// La casilla de la página de permisos de Mnemo que deja usar las voces (`mnemo:voice`)
const CASILLA_VOZ = '«Hablar con las voces que clonaste en Mnemo…»';
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

/** Le avisa al asistente que su estado cambió (se conectó o se desconectó Mnemo, se guardaron sus ajustes): lo vuelve a
 * pedir en el acto, también con el panel abierto. Sin el asistente montado no pasa nada: lo pedirá al montarse. */
function avisarAlAsistente() {
  window.dispatchEvent(new Event(EVENTO_ESTADO));
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
 * de la conexión, sin secretos: {estado, motivo, url, cuenta, alcances, modelo, ofrece_modelo, desde, url_sugerida};
 * al coordinador le llega sin `cuenta` ni `url_sugerida`); `nota`, lo que pasó al conectar o desconectar ({tipo: 'ok' |
 * 'alerta' | 'error', texto}) o null. Los botones y la dirección son solo para quien puede conectar (el
 * administrador); el coordinador ve el estado. */
function bloqueMnemo(c, nota) {
  const admin = puede('agente.conectar');
  const estado = ['conectada', 'caida'].includes(c?.estado) ? c.estado : 'sin_conectar';
  const chip = { conectada: html`<span class="chip verde">Conectado</span>`, caida: html`<span class="chip rojo">Conexión caída</span>`,
    sin_conectar: html`<span class="chip borde">Sin conectar</span>` }[estado];
  const partes = [];
  if (estado === 'conectada') {
    const desde = c.desde ? ` desde ${fecha(c.desde, true)}` : '';
    partes.push(html`<p>Conectado como <b>${c.cuenta || 'una cuenta de Mnemo'}</b>${desde}.</p>`);
    if (c.url) partes.push(html`<p>Dirección: ${c.url}</p>`);
    const orden = Object.keys(PERMISOS_MNEMO);
    const alcances = (Array.isArray(c.alcances) ? c.alcances : []).filter((a) => typeof a === 'string')
      .sort((a, b) => (orden.indexOf(a) + 1 || 99) - (orden.indexOf(b) + 1 || 99));
    if (alcances.length) {
      partes.push(html`<div class="chips" aria-label="Permisos que dio la cuenta">${alcances.map((a) => html`<span class="chip borde">${PERMISOS_MNEMO[a] || a}</span>`)}</div>`);
    }
    if (!c.modelo) {
      const sinModelo = c.ofrece_modelo === false ? NO_OFRECE_MODELO : SIN_PERMISO_MODELO[admin ? 'admin' : 'otro'];
      partes.push(html`<p class="mnemo-nota alerta" role="alert">${sinModelo}</p>`);
    }
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
      <p class="ancho mnemo-ayuda">Se abre Mnemo: inicie sesión con la cuenta que va a poner los modelos, deje marcado «Usar tus modelos de IA y tus créditos» (y, para la voz del asistente, ${CASILLA_VOZ}) y pulse «Permitir». Mnemo lo trae de vuelta aquí. Las casillas de escritura (eventos y documentos, recuerdos, compartir, publicar) son para que el asistente también trabaje en ese Mnemo, siempre con su aprobación: márquelas si lo quiere.${estado === 'sin_conectar' ? '' : ' Cambiar la dirección y volver a conectar cambia de Mnemo.'}</p>
    </form>`;
  } else {
    acciones = html`<p class="mnemo-ayuda">Solo el administrador conecta o desconecta Mnemo.</p>`;
  }
  return html`<div class="mnemo-conexion" id="mnemo-conexion" data-estado="${estado}">
    <h3>Conexión con Mnemo ${chip}</h3>${partes}${acciones}</div>`;
}

/** El bloque «Voz del asistente» de la sección Asistente. `av` es `agente_voz` de GET /api/ajustes ({motor, voz,
 * nombre, roles, respuestas, automatica}: sin `voz`, la automática, la que Mnemo ofrece a las apps); `lista`, lo que
 * respondió GET /api/agente/voces ({voces, elegida, automatica, conexion}),
 * `{error}` si falló, o null si no se pidió (no es el administrador, o la conexión con Mnemo no tiene `mnemo:voice`); `c`,
 * la conexión con Mnemo (`mnemo.conexion` del estado) o null. El coordinador lo ve en solo lectura y sin la lista de
 * voces (la voz es de la cuenta del administrador): solo la que está elegida. */
function bloqueVoz(av, lista, c, soloLectura) {
  const admin = puede('agente.conectar');
  const v = av && typeof av === 'object' ? av : {};
  const motor = v.motor === 'mnemo' ? 'mnemo' : 'navegador';
  const elegida = typeof v.voz === 'string' ? v.voz : '';
  const roles = new Set(Array.isArray(v.roles) ? v.roles : []);
  const voces = Array.isArray(lista?.voces) ? lista.voces.filter((x) => x && typeof x.id === 'string') : null;
  const conectada = c?.estado === 'conectada';
  const avisos = [];
  if (!conectada) {
    avisos.push(html`<p class="mnemo-nota alerta">${admin ? 'Para usar una voz clonada, conecte Mnemo (arriba). Mientras tanto el asistente habla con la voz del navegador.'
      : 'Para usar una voz clonada, el administrador conecta Mnemo. Mientras tanto el asistente habla con la voz del navegador.'}</p>`);
  } else if (c.voz !== true) {
    avisos.push(html`<p class="mnemo-nota alerta">${c.ofrece_voz === false
      ? 'El Mnemo conectado todavía no ofrece sus voces a otras aplicaciones: hay que actualizar Mnemo y volver a conectar.'
      : `La conexión con Mnemo no tiene permiso para usar sus voces (se conectó antes de que existiera, o sin esa casilla): ${admin ? 'vuelva' : 'el administrador tiene que volver'} a conectar dejando marcado ${CASILLA_VOZ}.`}</p>`);
    // El permiso solo lo da Mnemo al conectar: el botón hace lo mismo que «Volver a conectar» de arriba
    if (admin && c.ofrece_voz !== false && !soloLectura) {
      avisos.push(html`<div class="mnemo-botones"><button type="button" class="btn primario" id="voz-reconectar">Volver a conectar para usar la voz</button></div>`);
    }
  } else if (lista?.error) {
    avisos.push(html`<p class="mnemo-nota error">No se pudieron traer las voces de Mnemo: ${lista.error.message || 'intente de nuevo en un momento.'}</p>`);
  } else if (voces && !voces.length) {
    avisos.push(html`<p class="mnemo-nota alerta">La cuenta de Mnemo conectada no tiene voces listas para las apps: clone una en Mnemo (Ajustes → Voces) y márquela «Disponible para apps conectadas».</p>`);
  }
  const auto = lista && typeof lista.automatica?.id === 'string' ? lista.automatica : null;
  if (motor === 'navegador' && auto) {
    avisos.push(html`<p class="mnemo-nota alerta">Mnemo ya ofrece una voz clonada para las apps (${auto.nombre || 'sin nombre'}), pero el asistente habla con la voz del navegador: elija «Voz clonada de Mnemo» y pulse «Guardar voz».</p>`);
  }
  if (elegida && voces && !voces.some((x) => x.id === elegida)) {
    avisos.push(html`<p class="mnemo-nota alerta">La voz guardada ya no está disponible en esta cuenta de Mnemo (se borró, dejó de estar marcada para las apps o es de otra cuenta): elija otra.</p>`);
  }
  const opciones = (voces || []).map((x) => html`<option value="${x.id}" data-nombre="${x.nombre || ''}" ${x.id === elegida ? 'selected' : ''}>${x.nombre || x.id}${x.idioma ? ` · ${x.idioma}` : ''}</option>`);
  // La guardada que no vino en la lista (el coordinador no la pide; o ya no está en Mnemo) se ve igual
  if (elegida && !voces?.some((x) => x.id === elegida)) {
    opciones.unshift(html`<option value="${elegida}" data-nombre="${v.nombre || ''}" selected>${v.nombre || 'La voz guardada'}${voces ? ' (ya no está en Mnemo)' : ''}</option>`);
  }
  // Sin una elegida, la automática: la que Mnemo ofrece a las apps (la más reciente que su dueño marcó)
  const automatica = auto ? `Automática: ${auto.nombre || 'la que Mnemo ofrece a las apps'}`
    : voces ? 'Automática (Mnemo todavía no ofrece ninguna a las apps)' : 'Automática: la que Mnemo ofrece a las apps';
  const probar = admin && !soloLectura;
  const sinProbar = motor !== 'mnemo';
  return html`<div class="mnemo-conexion voz-asistente" id="voz-asistente">
    <h3>Voz del asistente <span class="chip ambar" title="La voz clonada imita la voz de una persona: no es ella la que habla">Voz sintética</span></h3>
    <p>Narra el plan guiado de la presentación y, si la persona lo enciende en el chat (o pregunta por voz), lee en voz alta las respuestas del asistente. La voz clonada la clona su dueño en Mnemo (Ajustes → Voces) y la marca «Disponible para apps conectadas»; sin elegir una aquí, el asistente usa sola la que Mnemo ofrece a las apps. Suena con los créditos de la cuenta de Mnemo conectada. Si una frase no llega a tiempo, se dice con la voz del navegador: la presentación nunca queda muda.</p>
    ${avisos}
    <form id="f-voz" class="form" novalidate>
      <label class="campo"><span>Con qué voz habla</span><select name="motor">${MOTORES_VOZ.map(([k, t]) => html`<option value="${k}" ${k === motor ? 'selected' : ''}>${t}</option>`)}</select></label>
      <label class="campo"><span>Voz clonada</span><select name="voz"><option value="">${automatica}</option>${opciones}</select></label>
      <div class="campo ancho"><span>Quiénes la hacen sonar (habla con la voz y los créditos de la cuenta de Mnemo del administrador; los demás oyen la del navegador)</span>
        <div class="chips">${ROLES_AGENTE.map(([k, t]) => html`<label class="chip opcion"><input type="checkbox" name="voz_rol_${k}" ${roles.has(k) ? 'checked' : ''}> ${t}</label>`)}</div></div>
      ${casilla('respuestas', v.respuestas !== false, 'Leer en voz alta las respuestas del asistente, cuando la persona lo enciende en el chat o pregunta por voz (solo en conversaciones sin datos de habitantes)')}
      ${casilla('automatica', v.automatica !== false, 'Narrar también la presentación automática de la pantalla en off (casi siempre sale de la caché del panel: se repite)')}
      <div class="aviso-legal ancho">La voz clonada es un dato biométrico de su dueño (Ley 1581 de 2012): úsela solo con su autorización expresa, con los roles que la necesitan, y diga ante la sala que es una voz sintética. A Mnemo solo va el texto de cada frase: la narración de la presentación (sin datos de personas) y, de las respuestas, las de conversaciones sin datos de habitantes, sin cédulas, teléfonos, correos ni enlaces. Ni Mnemo ni el panel guardan lo que se dice ni el audio.</div>
      ${soloLectura ? SOLO_ADMIN : html`<div class="ancho mnemo-botones"><button class="btn primario">Guardar voz</button>${probar ? html`<button type="button" class="btn" id="voz-probar" title="${sinProbar ? 'Guarde «Voz clonada de Mnemo» para probarla' : 'Dice una frase fija con la voz guardada y mide cuánto tarda la primera palabra'}" ${sinProbar ? 'disabled' : ''}>Probar voz</button>` : ''}</div>`}
      <p class="ancho mnemo-nota resultado" id="voz-resultado" role="status" hidden></p>
    </form></div>`;
}

export async function vistaAjustes(el, { q } = {}) {
  // Lo primero, antes de cualquier await: si es la vuelta de Mnemo, sale de la dirección
  const vuelta = tomarVuelta(q);
  let filtros = {};
  let notaMnemo = null; // lo que pasó al volver de Mnemo o al desconectar: se muestra en el próximo repintado
  let vozPrueba = null; // la voz de la ventana para «Probar voz» (voz-panel.js): se suelta al salir de Ajustes

  async function pintar() {
    const nota = notaMnemo;
    notaMnemo = null;
    // El estado del asistente es solo un aviso: si no responde, Ajustes se pinta igual
    const [cat, aud, aj, est] = await Promise.all([api.get('/api/catalogos'), api.get('/api/auditoria', filtros), api.get('/api/ajustes'),
      api.get('/api/agente/estado').catch(() => null)]);
    const puestos = await api.get('/api/puestos', { eleccion: aj.eleccion_vigente, todos: 1 });
    // Las voces clonadas de la cuenta conectada: solo al administrador y con permiso para usarlas (sin él la lista es
    // vacía y no se le pregunta a Mnemo). Si falla, el bloque lo dice y Ajustes se pinta igual
    const conexion = est?.mnemo?.conexion || null;
    const voces = puede('agente.conectar') && conexion?.estado === 'conectada' && conexion.voz === true
      ? await api.get('/api/agente/voces').catch((error) => ({ error })) : null;
    if (!el.isConnected) return;
    const av = aj.aviso_privacidad || {};
    const soloLectura = aj.puede_modificar_permisos === false;
    const ag = aj.agente || {};
    const rolesAgente = new Set(Array.isArray(ag.roles) ? ag.roles : []);
    const mensajes = aj.agente_mensajes_diarios || {};
    const pl = aj.agente_planillas || {};
    const rolesPlanillas = new Set(Array.isArray(pl.roles) ? pl.roles : []);
    const mc = aj.agente_mcp || {};
    const rolesMcp = new Set(Array.isArray(mc.roles) ? mc.roles : []);
    const po = aj.agente_politicos || {};
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
          <h2>Sesiones y límites</h2>
          <p class="sec">Sin tope de personas consultadas por día: planilleros y consultores consultan sin frenarse (cada consulta queda registrada).</p>
          <form id="f-limites" class="form" style="margin-top:12px">
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
            <p class="sec ancho" style="margin:0">Vigencia de la base: ${aj.vigencia_base ? fecha(aj.vigencia_base) : 'sin definir'}. Cambiar la versión del compromiso pide a coordinadores, planilleros y consultores aceptarlo de nuevo.</p>
            <div class="ancho"><button class="btn primario">Guardar</button></div>
          </form>
        </section>
        <section class="tarjeta c-12">
          <h2>Asistente</h2>
          <div class="asistente-cabeza">${estadoAgente(est)}${est?.mnemo?.conexion ? bloqueMnemo(est.mnemo.conexion, nota) : ''}${bloqueVoz(aj.agente_voz, voces, conexion, soloLectura)}</div>
          <form id="f-agente" class="form" style="margin-top:12px">
            <div class="campo ancho"><span>Quiénes lo usan (cada uno con los permisos, el alcance y el presupuesto diario de su rol)</span>
              <div class="chips">${ROLES_AGENTE.map(([k, t]) => html`<label class="chip opcion"><input type="checkbox" name="rol_${k}" ${rolesAgente.has(k) ? 'checked' : ''}> ${t}</label>`)}</div></div>
            ${casilla('escritura', ag.escritura !== false, 'Proponer cambios en la base (notas, acercamientos, fichas, reuniones…): cada uno se aprueba en una tarjeta antes de guardarse')}
            ${casilla('mnemo_coordinadores', ag.mnemo_coordinadores === true, 'Los coordinadores también usan las herramientas de Mnemo (documentos, calendario, formularios y memoria), con la cuenta de Mnemo del administrador: lo que hagan allá queda a nombre del administrador')}
            ${casilla('agente_adelanto', aj.agente_adelanto !== false, 'Respuesta inmediata: mientras prepara la respuesta o la presentación, el asistente adelanta en una o dos frases la idea general (una llamada corta más al modelo)')}
            ${numero('retencion_dias', ag.retencion_dias, 'Días que se guardan las conversaciones', 1, 365)}
            ${ROLES_AGENTE.map(([k, , t]) => numero(`mensajes_${k}`, mensajes[k], `Mensajes por día · ${t}`, 1, 5000))}
            <div class="aviso-legal ancho">Lo que el asistente consulta de la base viaja al proveedor del modelo: con Mnemo conectado, a Mnemo y, de ahí, al proveedor de modelos que esa cuenta tenga elegido; en modo directo, a Anthropic. Son terceros, posiblemente en el exterior: datos mínimos, cédulas y teléfonos enmascarados, nunca datos sensibles ni listas, y nada de quien no autorizó. Revise el aviso de privacidad y la autorización con un abogado antes de encenderlo para el equipo. Las conversaciones se borran solas a los días indicados desde su último mensaje; bajar el plazo acorta también las que ya existen.</div>
            ${soloLectura ? SOLO_ADMIN : html`<div class="ancho"><button class="btn primario">Guardar asistente</button></div>`}
          </form>
        </section>
        <section class="tarjeta c-6">
          <h2>Planillas físicas por foto</h2>
          <p class="sec">El administrador o un coordinador le toma una foto al papel en el chat del asistente o en Importar y exportar: el panel la lee, la coteja con la base y propone cargarla. Nada se guarda sin su aprobación, con el folio del papel. En el chat también puede adjuntar cualquier otra imagen: el panel la describe para que el asistente hable de ella. Los planilleros no suben fotos: el que llenó la planilla queda como «Capturado por».</p>
          <form id="f-planillas" class="form" style="margin-top:12px">
            ${aj.compromiso_permite_fotos === false ? html`<div class="aviso-legal ancho" id="pf-compromiso" role="alert">El compromiso de confidencialidad vigente (versión ${aj.compromiso_version}) prohíbe fotografiar los datos: con él nadie sube fotos de planillas. La versión ${aj.compromiso_con_fotos} lo permite solo para planillas físicas que se suben por el panel, nunca cédulas ni otros documentos, y pide borrar la foto del teléfono después de subirla. ${soloLectura ? 'Solo el administrador cambia la versión del compromiso.' : html`<button type="button" class="btn chico" id="compromiso-fotos" data-version="${aj.compromiso_con_fotos}">Usar el compromiso ${aj.compromiso_con_fotos}</button>`}</div>` : ''}
            <div class="campo ancho"><span>Quiénes suben fotos (además tienen que usar el asistente)</span>
              <div class="chips">${ROLES_PLANILLAS.map(([k, t]) => html`<label class="chip opcion"><input type="checkbox" name="planillas_rol_${k}" ${rolesPlanillas.has(k) ? 'checked' : ''}> ${t}</label>`)}</div></div>
            ${numero('retencion_horas', pl.retencion_horas, 'Horas que se guardan la foto y lo leído', RETENCION_HORAS[0], RETENCION_HORAS[1])}
            <div class="aviso-legal ancho">La foto entera, con cédulas, teléfonos y firmas de habitantes, viaja al proveedor del modelo para leerla: con Mnemo conectado, a Mnemo y al proveedor de modelos que esa cuenta tenga elegido; en modo directo, a Anthropic. Son terceros, posiblemente en el exterior: antes de encenderlo, revise con un abogado que el aviso de privacidad y la autorización cubran esa transmisión. Toda foto se describe y, de toda hoja que liste personas (la planilla de campo, una lista de asistencia u otra), se leen sus filas, nunca las columnas sensibles ni las políticas; al asistente le llega lo leído enmascarado, nunca la imagen. Las autorizaciones leídas de una foto quedan «declaradas en planilla» y no habilitan el contacto hasta que un administrador o un coordinador las confirme con el papel en Importar y exportar. Nunca se leen fotos de cédulas. La foto se borra al cargarla (queda su huella) o, si no, a las horas indicadas.</div>
            ${soloLectura ? SOLO_ADMIN : html`<div class="ancho"><button class="btn primario">Guardar planillas por foto</button></div>`}
          </form>
        </section>
        <section class="tarjeta c-6">
          <h2>Agentes externos por MCP</h2>
          <p class="sec">En Mi cuenta, cada persona con permiso crea una clave de datos para conectar su propio agente (por ejemplo, Claude Desktop): consulta, analiza o propone cambios con los permisos de esa persona. Cada cambio queda como propuesta hasta que ella lo aprueba en Mi cuenta.</p>
          <form id="f-mcp" class="form" style="margin-top:12px">
            <div class="campo ancho"><span>Quiénes crean claves con datos</span>
              <div class="chips">${ROLES_MCP.map(([k, t]) => html`<label class="chip opcion"><input type="checkbox" name="mcp_rol_${k}" ${rolesMcp.has(k) ? 'checked' : ''}> ${t}</label>`)}</div></div>
            ${casilla('mcp_escritura', mc.escritura !== false, 'Proponer cambios en la base: cada propuesta espera la aprobación de la persona en Mi cuenta antes de guardarse')}
            ${numero('llamadas_diarias', mc.llamadas_diarias, 'Llamadas por clave y día', LLAMADAS_MCP[0], LLAMADAS_MCP[1])}
            ${numero('personas_diarias', mc.personas_diarias, 'Personas distintas por clave y día', PERSONAS_MCP[0], PERSONAS_MCP[1])}
            <div class="aviso-legal ancho">Lo que consulta un agente por MCP sale del panel hacia ese agente y su proveedor de modelos: terceros que el panel no controla. Leer fichas de personas por MCP es solo del administrador (quien puede exportar); el coordinador, solo análisis y propuestas. Nunca salen datos sensibles, listas ni quien no autorizó. Las claves de datos vencen a los 30 días y se revocan en Mi cuenta; revocarla anula sus propuestas pendientes.</div>
            ${soloLectura ? SOLO_ADMIN : html`<div class="ancho"><button class="btn primario">Guardar agentes por MCP</button></div>`}
          </form>
        </section>
        <section class="tarjeta c-12">
          <h2>Datos políticos en el asistente y por MCP</h2>
          <p class="sec">El tipo de persona (líder, votante, concejal), «Liderado por», las listas, los líderes con sus conteos, los filtros por ellos y las fuentes políticas de importación. Cada rol los recibe solo como ya los ve en el panel: el administrador y los coordinadores, todo; el planillero, el tipo y el líder donde el panel se los muestra (y solo puede agregarlos); el consultor, nada.</p>
          <form id="f-politicos" class="form" style="margin-top:12px">
            ${casilla('politicos_asistente', po.asistente !== false, 'El asistente del panel los consulta, los filtra y propone cambiarlos (cada cambio se aprueba en una tarjeta)')}
            ${casilla('politicos_mcp', po.mcp !== false, 'Los agentes externos por MCP también los reciben, con la clave de datos de cada persona')}
            <div class="aviso-legal ancho">La orientación política es un dato sensible (Ley 1581 de 2012, art. 5). El asistente solo la muestra a los roles que ya la ven en el panel, pero lo que consulta viaja al proveedor del modelo y, por MCP, al agente de cada persona: terceros, posiblemente en el exterior. Quien no autorizó y los datos de salud, etnia, discapacidad o víctima nunca salen.</div>
            ${soloLectura ? SOLO_ADMIN : html`<div class="ancho"><button class="btn primario">Guardar datos políticos</button></div>`}
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
            <label class="campo"><span>Reunión (número)</span><input name="reunion_id" type="number" min="1" value="${filtros.reunion_id ?? ''}" title="Lo que se hizo en esa reunión"></label>
            <label class="campo"><span>Desde</span><input name="desde" type="date" value="${filtros.desde || ''}"></label>
            <label class="campo"><span>Hasta</span><input name="hasta" type="date" value="${filtros.hasta || ''}"></label>
            <div class="ancho"><button class="btn">Filtrar</button></div>
          </form>
          <div class="envoltura-tabla" style="max-height:420px;overflow:auto"><table class="tabla"><thead><tr><th>Cuándo</th><th>Usuario</th><th>Acción</th><th>Sobre</th><th>IP</th></tr></thead>
            <tbody>${aud.filas.map((a) => html`<tr style="cursor:default"><td>${fecha(a.ts, true)}</td><td>${a.usuario || 'sistema'}${a.rol && a.rol !== 'admin' ? html` <span class="sec">(${a.rol})</span>` : ''}</td><td>${(a.accion || '').replace(/_/g, ' ')}</td>
              <td>${a.entidad === 'persona' ? html`<a href="/personas/${a.entidad_id}" data-ruta>persona ${a.entidad_id}</a>` : a.entidad ? `${a.entidad} ${a.entidad_id ?? ''}` : ''}${(a.reuniones || []).map((r) => html` <a class="chip borde" href="/reuniones/${r}" data-ruta title="Hecho en la reunión ${r}">reunión ${r}</a>`)}</td><td class="sec">${a.ip || ''}</td></tr>`)}</tbody></table></div>
        </section>
        <section class="tarjeta c-12">
          <h2>Protección de datos personales</h2>
          <div class="aviso-legal">Esta base contiene datos personales y algunos sensibles (afiliación política, condición de víctima, salud). La Ley 1581 de 2012 exige autorización previa,
            expresa e informada del titular, informar la finalidad, y atender consultas, correcciones y supresiones. La autorización de cada ficha, las solicitudes de titulares
            en Calidad de datos y la opción «Suprimir datos» existen para eso. Los datos de bases oficiales (como las del SISBÉN) solo pueden usarse para la finalidad con la que se recogieron.</div>
        </section>
      </div>`);
    if (soloLectura) {  // el coordinador ve la política, los límites y el asistente, pero no los cambia
      for (const id of ['#f-politica', '#f-limites', '#f-agente', '#f-voz']) {
        for (const c of $(id, el).querySelectorAll('input, select, textarea')) c.disabled = true;
      }
      // (y las planillas por foto, los agentes por MCP y los datos políticos: también son permisos)
      for (const id of ['#f-planillas', '#f-mcp', '#f-politicos']) {
        for (const c of $(id, el).querySelectorAll('input, select, textarea')) c.disabled = true;
      }
      const dePermisos = new Set(aj.ajustes_de_permisos || []);  // datos sensibles y compromiso: también solo A
      for (const c of $('#f-otros', el).querySelectorAll('[name]')) if (dePermisos.has(c.name)) c.disabled = true;
    }
  }

  // `asistente`: lo guardado cambia el estado del asistente (si lo usa su rol, si propone cambios, cuántos mensajes le
  // quedan): se le avisa
  const guardar = async (cuerpo, texto, { asistente = false } = {}) => {
    await api.put('/api/ajustes', cuerpo);
    if (asistente) avisarAlAsistente();
    aviso(texto);
    await pintar();
  };

  // ── La conexión con Mnemo (solo el administrador; el servidor también lo exige) ──
  const fallo = (err, texto) => (err?.estado === 401 ? null : { tipo: 'error', texto: err?.message || texto });

  /** Deja en el bloque de Mnemo lo que pasó (o lo quita), sin repintar la vista: no se pierde la dirección escrita. */
  function anotarMnemo(nota) {
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
      // El asistente leyó su estado al cargar la página, mientras se canjeaba el código: el de antes de conectar
      avisarAlAsistente();
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
    // También si falló: el panel pudo borrar la conexión antes del error, y releer el estado no cuesta nada
    avisarAlAsistente();
    await pintar();
  }

  /** «Probar voz»: la frase fija con la voz clonada guardada (`{prueba: true}`), y cuánto tardó la primera palabra en
   * sonar aquí (desde el clic) y en Mnemo (lo que tardó en dar el primer audio). Sale de la voz de la ventana, que
   * calla lo que estuviera sonando; nunca de la del navegador (no es lo que se prueba). */
  function probarVoz(boton) {
    const res = $('#voz-resultado', el);
    const poner = (tipo, texto) => {
      if (!res?.isConnected) return;
      res.hidden = false;
      res.className = `ancho mnemo-nota resultado ${tipo}`;
      res.setAttribute('role', tipo === 'error' ? 'alert' : 'status');
      res.textContent = texto;
    };
    vozPrueba ||= tomarVoz('prueba');
    const t0 = performance.now();
    let primer = null, medida = null;
    boton.disabled = true;
    poner('info', 'Diciendo la frase de prueba con la voz clonada…');
    vozPrueba.decir('', {
      ref: { prueba: true },
      alEmpezar: () => { primer = Math.round(performance.now() - t0); poner('ok', `Primer audio en ${num(primer)} ms…`); },
      alFin: (d) => { medida = d; },
    }).then((r) => {
      if (boton.isConnected) boton.disabled = false;
      if (primer !== null) {
        const mnemo = Number.isInteger(medida?.ms_mnemo) ? `${num(medida.ms_mnemo)} ms` : 'sin dato';
        const cache = medida?.cache ? ' Salió de la caché del panel: ya se había dicho hace poco.' : '';
        const corte = r === 'dicha' ? '' : ' Se cortó antes de terminar.';
        poner(r === 'dicha' ? 'ok' : 'alerta', `Primer audio en ${num(primer)} ms en este navegador (Mnemo: ${mnemo}).${cache}${corte}`);
      } else if (r === 'cortada') {
        poner('alerta', 'Se interrumpió la prueba.');
      } else {
        poner('error', `No se pudo probar la voz: ${medida?.error?.mensaje || 'la voz clonada no respondió.'}`);
      }
    });
  }

  /** «Usar el compromiso …» (bloque de las planillas por foto, solo el administrador): pone como vigente la versión
   * del compromiso que deja fotografiar planillas físicas. Cada persona lo lee y lo acepta de nuevo en su siguiente
   * petición; el asistente vuelve a leer su estado (la cámara del chat depende del compromiso). */
  async function usarCompromisoConFotos(boton) {
    const version = boton.dataset.version;
    if (!version || !await confirmar(`¿Cambiar el compromiso de confidencialidad a la versión ${version}? Los coordinadores, `
      + 'planilleros y consultores tendrán que leerlo y aceptarlo de nuevo antes de seguir trabajando.', { si: 'Cambiar' })) return;
    boton.disabled = true;
    try {
      await guardar({ compromiso_version: version }, `Compromiso ${version} vigente: cada persona lo aceptará de nuevo`);
      avisarAlAsistente();
    } catch (err) {
      avisoError(err);
      if (boton.isConnected) boton.disabled = false;
    }
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
      pie: html`<button class="btn" data-cerrar>Cancelar</button><button class="btn primario" id="g">Guardar</button>`, sucio: hayEscrito });
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
        await guardar({ sesion: { horas_max: Number(v.horas_max), inactividad_min: Number(v.inactividad_min), max_por_usuario: Number(v.max_por_usuario) },
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
          retencion_dias: Number(v.retencion_dias) }, agente_adelanto: v.agente_adelanto === true,
        agente_mensajes_diarios: Object.fromEntries(ROLES_AGENTE.map(([k]) => [k, Number(v[`mensajes_${k}`])])) }, 'Asistente guardado',
        { asistente: true });
      } else if (f.id === 'f-voz') {
        const v = datosForm(f);
        const roles = ROLES_AGENTE.map(([k]) => k).filter((k) => v[`voz_rol_${k}`] === true);
        const motor = v.motor === 'mnemo' ? 'mnemo' : 'navegador';
        const voz = v.voz || '';   // sin una elegida, la automática: la que Mnemo ofrece a las apps
        // su nombre para mostrar, el que dio Mnemo (el servidor anota además con qué cuenta se eligió)
        const nombre = voz ? f.elements.voz.selectedOptions[0]?.dataset.nombre || '' : '';
        await guardar({ agente_voz: { motor, voz, ...(nombre ? { nombre } : {}), roles, respuestas: v.respuestas === true,
          automatica: v.automatica === true } }, 'Voz del asistente guardada', { asistente: true });
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
      } else if (f.id === 'f-planillas') {
        const v = datosForm(f);
        const roles = ROLES_PLANILLAS.map(([k]) => k).filter((k) => v[`planillas_rol_${k}`] === true);
        // Leer otros formatos ya no es un ajuste (se retiró: toda foto se describe y se transcribe toda hoja que liste
        // personas): el formulario manda solo los roles y la retención
        await guardar({ agente_planillas: { roles, retencion_horas: Number(v.retencion_horas) } },
          'Planillas por foto guardadas');
        // Quién puede adjuntar fotos en el chat sale del estado del asistente (`adjuntos`): que lo vuelva a pedir
        avisarAlAsistente();
      } else if (f.id === 'f-mcp') {
        const v = datosForm(f);
        const roles = ROLES_MCP.map(([k]) => k).filter((k) => v[`mcp_rol_${k}`] === true);
        await guardar({ agente_mcp: { roles, escritura: v.mcp_escritura === true,
          llamadas_diarias: Number(v.llamadas_diarias), personas_diarias: Number(v.personas_diarias) } },
        'Agentes por MCP guardados');
      } else if (f.id === 'f-politicos') {
        const v = datosForm(f);
        await guardar({ agente_politicos: { asistente: v.politicos_asistente === true, mcp: v.politicos_mcp === true } },
          'Datos políticos guardados');
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
    // (sin esperas antes: el clic es el gesto que deja sonar el audio de la ventana)
    const pv = e.target.closest('#voz-probar');
    if (pv) { probarVoz(pv); return; }
    const cf = e.target.closest('#compromiso-fotos');
    if (cf) { await usarCompromisoConFotos(cf); return; }
    // «Volver a conectar para usar la voz»: lo mismo que «Volver a conectar» del bloque de Mnemo (Mnemo pide el permiso)
    if (e.target.closest('#voz-reconectar')) { const f = $('#f-mnemo', el); if (f) await conectarMnemo(f); return; }
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
  // Al salir de Ajustes, la voz de «Probar voz» se devuelve (si era la última, la de la ventana se suelta)
  return () => { vozPrueba?.soltar(); vozPrueba = null; };
}
