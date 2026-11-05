// Tablero (7.10, administrador y coordinador): indicadores de la base única, demografía (sexo, pirámide con enlaces,
// demografía adicional), puestos y mesas, cobertura de cédula, completitud por campo, abordaje y autorización,
// distribución territorial y actividad. Las claves nuevas de 5.2 se leen con tolerancia: sin ellas, la tarjeta no sale.
import { api } from '../api.js';
import { apilada, barras, columnas, medidor, piramide, serieMensual } from '../graficos.js';
import { ESTADOS_ABORDAJE, ETIQUETAS_CAMPOS, RANGOS_EDAD, SENSIBLES, SEXOS, rangoAParams } from '../modelo.js';
import { fecha, html, icono, montar, num, pct, titulo } from '../ui.js';

const ACCIONES = {
  editar: 'editó', crear: 'creó', nota: 'anotó en', borrar_nota: 'borró una nota de', asistencia: 'registró asistencia de',
  quitar_asistencia: 'quitó la asistencia de', importar: 'importó datos', fusionar: 'unió fichas de', ubicar: 'ubicó en el mapa a',
  cruce_automatico: 'cruzó por nombre a', exportar: 'exportó la base', rechazar_coincidencia: 'descartó coincidencia de',
  suprimir: 'suprimió', georreferenciar: 'recalculó ubicaciones', telefono_agregar: 'agregó un número a',
  telefono_estado: 'marcó un número de', telefono_principal: 'cambió el número principal de', telefono_retirar: 'retiró un número de',
  autorizacion: 'registró la autorización de', acercamiento: 'registró un acercamiento con', anular_acercamiento: 'anuló un acercamiento con',
  actualizacion_atendida: 'actualizó los datos pendientes de', situacion: 'reportó la situación de', no_disponible: 'marcó un dato no disponible de',
  reportar_duplicado: 'reportó un duplicado de', solicitud_crear: 'registró una solicitud de', solicitud_editar: 'respondió una solicitud de',
  resolver_conflicto: 'resolvió un conflicto de cédula de', ver_sensibles: 'consultó datos sensibles de', crear_usuario: 'creó un usuario',
  editar_usuario: 'editó un usuario', restablecer_clave: 'restableció una clave', ajustes: 'cambió los ajustes',
  confirmar_autorizaciones: 'confirmó autorizaciones de una planilla', crear_area: 'dibujó una zona', editar_area: 'editó una zona',
  borrar_area: 'borró una zona', crear_puesto: 'creó un puesto', editar_puesto: 'editó un puesto',
};
const COLORES_SEXO = { F: 'var(--s2)', M: 'var(--s1)', N: 'var(--s7)', sin: 'var(--axis)' };
const DEMOGRAFIA = { estado_civil: 'Estado civil', nivel_educativo: 'Nivel educativo', situacion_laboral: 'Situación laboral', estrato: 'Estrato', tenencia_vivienda: 'Tenencia de la vivienda', regimen_salud: 'Régimen de salud' };

/** Conteos como lista [{etiqueta, valor}], vengan como objeto {valor: n} o como lista [{valor|clave|nombre, n}]. */
function items(x) {
  if (!x) return [];
  if (Array.isArray(x)) return x.map((i) => ({ clave: i.valor ?? i.clave ?? i.nombre ?? i.etiqueta ?? i.rango, etiqueta: String(i.etiqueta ?? i.valor ?? i.clave ?? i.nombre ?? i.rango ?? 'Sin dato'), valor: Number(i.n) || 0, texto: typeof i.n === 'string' ? i.n : undefined }));
  return Object.entries(x).map(([k, n]) => ({ clave: k, etiqueta: k === 'sin' || k === 'null' ? 'Sin dato' : k, valor: Number(n) || 0, texto: typeof n === 'string' ? n : undefined }));
}
const qs = (o) => new URLSearchParams(Object.entries(o).filter(([, v]) => v != null && v !== '')).toString();

export async function vistaPanel(el) {
  const d = await api.get('/api/indicadores');
  if (!el.isConnected) return;
  const k = d.kpi;
  const P = d.precision || {};
  const exactas = (P.direccion || 0) + (P.manual || 0);
  const aprox = (P.direccion_aprox || 0) + (P.barrio || 0) + (P.sector || 0);
  const rural = (P.vereda || 0) + (P.caserio || 0) + (P.centro_poblado || 0) + (P.corregimiento || 0);

  if (!k.personas) {
    montar(el, html`<div class="cabecera"><div><h1>Panel</h1><div class="sub">La base está vacía.</div></div></div>
      <div class="tarjeta vacio"><b>Empiece por importar los archivos</b>
      <p>Suba la base de trámites por vereda y la base unificada con cédula: el panel las cruza por nombre, normaliza las direcciones y ubica a cada habitante.</p>
      <a class="btn primario" href="/importar" data-ruta>${icono('importar')} Importar archivos</a></div>`);
    return;
  }
  // Denominador de cobertura: las vigentes (sin fallecidas ni quienes ya no viven en Yondó), si el servidor lo distingue
  const base = k.vigentes ?? (k.no_vigentes != null ? k.personas - k.no_vigentes : k.personas);
  const nuevos = k.con_puesto !== undefined;
  const rangos = (d.edades || []).some((f) => RANGOS_EDAD.includes(f.rango)) || !(d.edades || []).length
    ? RANGOS_EDAD : [...new Set(d.edades.map((f) => f.rango))].reverse();
  const enlacePiramide = (r, s) => `/personas?${qs({ sexo: s, ...rangoAParams(r) })}`;
  const sexos = d.sexo ? Object.entries({ F: d.sexo.F, M: d.sexo.M, N: d.sexo.N, sin: d.sexo.sin }).map(([s, n]) => ({ clave: s, etiqueta: s === 'sin' ? 'Sin dato' : SEXOS[s], valor: Number(n) || 0, color: COLORES_SEXO[s] })) : null;
  const puestos = (d.puestos || []).map((x) => ({ etiqueta: `${x.codigo ? x.codigo + ' · ' : ''}${titulo(x.nombre || '')}`, valor: x.n || 0, id: x.id, texto: `${num(x.n)}${x.con_mesa != null ? ` · ${num(x.con_mesa)} con mesa` : ''}` }));
  if (d.sin_puesto) puestos.push({ etiqueta: 'Sin puesto', valor: d.sin_puesto, id: 0, color: 'var(--axis)' });
  if (d.puesto_sin_catalogo) puestos.push({ etiqueta: 'Puesto sin verificar', valor: d.puesto_sin_catalogo, estado: 'por_confirmar', color: 'var(--s4)' });
  const completitud = (d.completitud_campos || []).map((c) => ({ etiqueta: c.etiqueta || ETIQUETAS_CAMPOS[c.campo] || c.campo, valor: base ? Math.round((c.con / base) * 100) : 0, texto: `${pct(c.con, base)} %`, campo: c.campo }));
  const cobertura = (d.cobertura_cedula || []).map((c) => ({ etiqueta: titulo(c.nombre || c.lugar || 'Sin lugar'), valor: c.sin_cedula ?? c.sin ?? c.n ?? 0, id: c.lugar_id ?? c.id }));
  const abordaje = d.abordaje && typeof d.abordaje === 'object' ? Object.keys(ESTADOS_ABORDAJE).map((e, i) => ({ etiqueta: ESTADOS_ABORDAJE[e], valor: Number(d.abordaje[e]) || 0, clave: e, color: ['var(--s4)', 'var(--s1)', 'var(--s3)', 'var(--crit)'][i] })) : null;
  const autorizacion = d.autorizacion && typeof d.autorizacion === 'object' ? [
    { etiqueta: 'Sí autoriza', valor: d.autorizacion.si || 0, clave: 'si', color: 'var(--s3)' },
    { etiqueta: 'Por confirmar (planilla)', valor: d.autorizacion.por_confirmar || 0, color: 'var(--s4)' },
    { etiqueta: 'Pendiente', valor: d.autorizacion.pendiente || 0, clave: 'pendiente', color: 'var(--axis)' },
    { etiqueta: 'No autoriza', valor: d.autorizacion.no || 0, clave: 'no', color: 'var(--crit)' },
  ] : null;

  montar(el, html`
    <div class="cabecera">
      <div><h1>Panel</h1><div class="sub">Base única de habitantes de Yondó · ${num(k.personas)} personas de ${num(k.hogares)} hogares con ficha</div></div>
      <div class="acciones">
        <a class="btn" href="/mapa" data-ruta>${icono('mapa')} Ver mapa 3D</a>
        <a class="btn primario" href="/reuniones" data-ruta>${icono('mas')} Nueva reunión</a>
      </div>
    </div>

    <div class="kpis">
      <a class="kpi acento" href="/personas" data-ruta><div class="t">Habitantes en la base</div><div class="v">${num(k.personas)}</div>
        <div class="d">${num(k.en_ambas_bases)} aparecen en las dos bases${k.no_vigentes ? ` · ${num(k.no_vigentes)} no vigentes` : ''}</div>${medidor(k.en_ambas_bases, k.personas)}</a>
      <a class="kpi" href="/personas?con_cedula=1" data-ruta><div class="t">Con cédula</div><div class="v">${pct(k.con_cedula, base)} %</div>
        <div class="d">${num(k.con_cedula)} identificadas${k.cedulas_verificadas != null ? ` · ${num(k.cedulas_verificadas)} verificadas` : ''}</div>${medidor(k.con_cedula, base)}</a>
      ${nuevos ? html`<a class="kpi" href="/personas?con_puesto=1" data-ruta><div class="t">Puesto y mesa</div><div class="v">${pct(k.con_puesto, base)} %</div>
        <div class="d">${num(k.con_puesto)} con puesto · ${num(k.con_mesa)} con mesa${k.votacion_por_confirmar ? ` · ${num(k.votacion_por_confirmar)} por confirmar` : ''}</div>${medidor(k.con_mesa, base)}</a>
        <a class="kpi" href="/personas?abordado=1" data-ruta><div class="t">Abordadas</div><div class="v">${pct(k.abordadas, base)} %</div>
        <div class="d">${num(k.abordadas)} abordadas · ${num(k.contactadas)} contactadas</div>${medidor(k.contactadas, base)}</a>
        <a class="kpi" href="/personas?con_telefono=1" data-ruta><div class="t">Teléfono usable</div><div class="v">${pct(k.con_telefono_usable, base)} %</div>
        <div class="d">${num(k.con_telefono_usable)} con número usable · ${num(k.con_varios_telefonos)} con varios</div>${medidor(k.con_telefono_usable, base)}</a>`
      : html`<a class="kpi" href="/personas?con_telefono=1" data-ruta><div class="t">Contactables</div><div class="v">${pct(k.con_telefono, k.personas)} %</div>
        <div class="d">${num(k.con_telefono)} con celular · ${num(k.con_correo)} con correo</div>${medidor(k.con_telefono, k.personas)}</a>`}
      <a class="kpi" href="/mapa" data-ruta><div class="t">Georreferenciadas</div><div class="v">${pct(k.ubicadas, k.personas)} %</div>
        <div class="d">${num(k.ubicadas_exactas)} con dirección exacta</div>${medidor(k.ubicadas, k.personas)}</a>
      <a class="kpi" href="/reuniones" data-ruta><div class="t">Alcanzadas en reuniones</div><div class="v">${num(k.alcanzadas)}</div>
        <div class="d">${num(k.reuniones)} reuniones · ${num(k.nuevas_en_reuniones)} personas nuevas</div>${medidor(k.alcanzadas, k.personas)}</a>
      <a class="kpi" href="/personas?orden=-completitud" data-ruta><div class="t">Completitud media del perfil</div><div class="v">${k.completitud_media} %</div>
        <div class="d">Sube con cada dato que se agrega</div>${medidor(k.completitud_media, 100)}</a>
      <a class="kpi ${k.pendientes_revision ? 'alerta' : ''}" href="/calidad" data-ruta><div class="t">Por revisar</div><div class="v">${num(k.pendientes_revision)}</div>
        <div class="d">personas con coincidencias por nombre · ${num(k.lugares_sin_punto)} lugares sin punto</div></a>
      <a class="kpi" href="/personas?consentimiento=si" data-ruta><div class="t">Autorización de datos</div><div class="v">${pct(k.consentimiento_si, base)} %</div>
        <div class="d">${num(k.consentimiento_si)} con autorización</div>${medidor(k.consentimiento_si, base)}</a>
      ${k.no_vigentes != null ? html`<a class="kpi" href="/personas?situacion=todas" data-ruta><div class="t">No vigentes</div><div class="v">${num(k.no_vigentes)}</div>
        <div class="d">Fallecidas o que ya no viven en Yondó: no cuentan en la cobertura</div></a>` : ''}
    </div>

    <div class="rejilla r-12">
      ${sexos ? html`<section class="tarjeta c-4">
        <header><h2>Sexo</h2><span class="nota">${num(base)} vigentes</span></header>
        ${apilada(sexos, { enlace: (p) => `/personas?sexo=${p.clave}` })}
        ${k.menores != null ? html`<p class="sec" style="margin-top:12px"><a href="/personas?menor=1" data-ruta>${num(k.menores)} menores de edad</a>${d.sin_edad != null ? ` · ${num(d.sin_edad)} sin edad` : ''}</p>` : ''}
      </section>` : ''}
      <section class="tarjeta ${sexos ? 'c-8' : 'c-4'}">
        <header><h2>Edad y sexo</h2><span class="nota">Toque una barra para ver a esas personas</span></header>
        ${piramide(d.edades || [], rangos, { enlace: enlacePiramide })}
      </section>
      ${puestos.length ? html`<section class="tarjeta c-6">
        <header><h2>Puestos de votación</h2><span class="nota">Personas por puesto</span></header>
        ${barras(puestos, { color: 'var(--s7)', enlace: (i) => (i.estado ? `/personas?votacion_estado=${i.estado}` : `/personas?puesto_id=${i.id}`) })}
      </section>` : ''}
      ${cobertura.length ? html`<section class="tarjeta c-6">
        <header><h2>Cobertura de cédula</h2><span class="nota">Lugares con más personas sin cédula</span></header>
        ${barras(cobertura, { color: 'var(--s4)', enlace: (i) => (i.id != null ? `/personas?${qs({ lugar_id: i.id, con_cedula: 0 })}` : null) })}
      </section>` : ''}
      ${completitud.length ? html`<section class="tarjeta c-6">
        <header><h2>Completitud por dato</h2><span class="nota">Toque para ver a quienes les falta</span></header>
        ${barras(completitud, { color: 'var(--s3)', unidad: 'tienen el dato', enlace: (i) => `/personas?sin_${i.campo}=1` })}
      </section>` : ''}
      ${abordaje || autorizacion ? html`<section class="tarjeta c-6">
        ${abordaje ? html`<header><h2>Abordaje</h2><span class="nota">Llamadas, mensajes, visitas y reuniones</span></header>
          ${apilada(abordaje, { enlace: (p) => `/personas?abordaje_estado=${p.clave}` })}` : ''}
        ${autorizacion ? html`<h2 class="sub-tarjeta">Autorización</h2>${apilada(autorizacion, { enlace: (p) => (p.clave ? `/personas?consentimiento=${p.clave}` : null) })}` : ''}
      </section>` : ''}
      ${d.demografia ? html`<section class="tarjeta c-12">
        <header><h2>Demografía adicional</h2><span class="nota">Donde se registró</span></header>
        <div class="rejilla r-12">${Object.entries(DEMOGRAFIA).filter(([c]) => items(d.demografia[c]).length).map(([c, t]) => html`<div class="c-4"><h3 class="sub-tarjeta">${t}</h3>
          ${barras(items(d.demografia[c]).sort((a, b) => b.valor - a.valor), { color: 'var(--s1)', enlace: (i) => (i.clave && i.clave !== 'sin' && i.clave !== 'null' ? `/personas?${qs({ [c]: i.clave })}` : null) })}</div>`)}</div>
      </section>` : ''}
      ${d.sensibles ? html`<section class="tarjeta c-12">
        <header><h2>Datos sensibles</h2><span class="nota">Solo de quien autorizó · celdas con menos de 5 personas no se muestran</span></header>
        <div class="rejilla r-12">${Object.entries(d.sensibles).map(([c, x]) => html`<div class="c-4"><h3 class="sub-tarjeta">${SENSIBLES[c]?.etiqueta || c}</h3>${barras(items(x), { color: 'var(--s5)' })}</div>`)}</div>
      </section>` : ''}

      <section class="tarjeta c-7">
        <header><h2>Dónde vive la gente</h2><span class="nota">Personas por barrio o vereda</span></header>
        ${barras((d.lugares || []).map((l) => ({ etiqueta: titulo(l.nombre) + (l.tipo !== 'barrio' ? ` (${String(l.tipo).replace('_', ' ')})` : ''), valor: l.n, id: l.id,
          color: l.zona === 'rural' ? 'var(--s3)' : 'var(--s1)' })), { total: k.personas, enlace: (i) => `/personas?lugar_id=${i.id}` })}
        <div class="leyenda"><span><i style="background:var(--s1)"></i>Casco urbano</span><span><i style="background:var(--s3)"></i>Rural</span></div>
      </section>
      <section class="tarjeta c-5">
        <header><h2>Calidad de la ubicación</h2><span class="nota">${num(k.personas)} personas</span></header>
        ${apilada([
          { etiqueta: 'Dirección exacta', valor: exactas, color: 'var(--s1)' },
          { etiqueta: 'Barrio o placa aproximada', valor: aprox, color: 'var(--s7)' },
          { etiqueta: 'Vereda o caserío', valor: rural, color: 'var(--s3)' },
          { etiqueta: 'Sin ubicar', valor: P.sin || 0, color: 'var(--axis)' },
        ])}
        <h2 class="sub-tarjeta">Zona</h2>
        ${apilada([
          { etiqueta: 'Casco urbano', valor: d.zonas?.urbana || 0, color: 'var(--s1)' },
          { etiqueta: 'Rural', valor: d.zonas?.rural || 0, color: 'var(--s3)' },
          { etiqueta: 'Sin dato', valor: d.zonas?.sin || 0, color: 'var(--axis)' },
        ])}
        <h2 class="sub-tarjeta">Completitud de los perfiles</h2>
        ${columnas(['0-24', '25-49', '50-74', '75-100'].map((r) => ({ etiqueta: r + ' %', valor: (d.completitud || []).find((c) => c.rango === r)?.n || 0 })))}
      </section>

      ${d.tramites_mes ? html`<section class="tarjeta c-8">
        <header><h2>Trámites por mes</h2><span class="nota">${num(k.tramites)} solicitudes en la base de trámites</span></header>
        ${serieMensual(d.tramites_mes, { color: 'var(--s7)' })}
        <div class="chips" style="margin-top:12px">${(d.tramites_tipo || []).map((t) => html`<span class="chip borde">${titulo(t.tipo || 'Sin tipo')} · <b>${num(t.n)}</b></span>`)}</div>
      </section>` : ''}
      <section class="tarjeta c-4">
        <header><h2>Necesidades registradas</h2><a class="nota" href="/ajustes" data-ruta>Editar catálogo</a></header>
        ${(d.necesidades || []).length ? barras(d.necesidades.map((n) => ({ etiqueta: n.nombre, valor: n.n, id: n.id, color: n.grupo === 'necesidad' ? 'var(--s2)' : 'var(--s7)' })),
          { enlace: (i) => `/personas?etiqueta=${i.id}` })
          : html`<div class="vacio"><b>Aún no hay necesidades</b>Se registran en la ficha de cada habitante o durante las reuniones.</div>`}
      </section>
      ${(d.listas || []).length ? html`<section class="tarjeta c-4">
        <header><h2>Listas de origen</h2><span class="nota">Base con cédula</span></header>
        ${barras(d.listas.map((l) => ({ etiqueta: l.lista, valor: l.n })), { color: 'var(--s4)', enlace: (i) => `/personas?lista=${encodeURIComponent(i.etiqueta)}` })}
      </section>` : ''}
      ${d.reuniones ? html`<section class="tarjeta c-4">
        <header><h2>Últimas reuniones</h2><a class="nota" href="/reuniones" data-ruta>Ver todas</a></header>
        ${d.reuniones.length ? html`<div class="lista-barras">${d.reuniones.map((r) => html`<a class="f" href="/reuniones/${r.id}" data-ruta><span>${r.titulo}</span><span class="sec">${fecha(r.fecha)}</span><span class="n">${num(r.n)}</span></a>`)}</div>`
          : html`<div class="vacio"><b>Sin reuniones</b><a href="/reuniones" data-ruta>Programe la primera</a></div>`}
        ${d.actividad ? html`<h2 class="sub-tarjeta">Actividad reciente</h2>
        <div class="actividad">
          ${d.actividad.map((a) => html`<div><b>${a.usuario || 'sistema'}</b> ${ACCIONES[a.accion] || String(a.accion || '').replace(/_/g, ' ')} ${a.entidad === 'persona' ? html`<a href="/personas/${a.entidad_id}" data-ruta>ficha ${a.entidad_id}</a>` : ''} <span class="sec">· ${fecha(a.ts, true)}</span></div>`)}
        </div>` : ''}
      </section>` : ''}
    </div>`);
}
