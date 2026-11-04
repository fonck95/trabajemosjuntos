// Tablero: indicadores de la base única, cobertura, distribución territorial y actividad.
import { api } from '../api.js';
import { apilada, barras, columnas, medidor, piramide, serieMensual } from '../graficos.js';
import { fecha, html, icono, montar, num, pct, titulo } from '../ui.js';

const ACCIONES = {
  editar: 'editó', crear: 'creó', nota: 'anotó en', asistencia: 'registró asistencia de', importar: 'importó datos',
  fusionar: 'unió fichas de', ubicar: 'ubicó en el mapa a', cruce_automatico: 'cruzó por nombre a', exportar: 'exportó la base',
  rechazar_coincidencia: 'descartó coincidencia de', suprimir: 'suprimió', georreferenciar: 'recalculó ubicaciones',
};

export async function vistaPanel(el) {
  const d = await api.get('/api/indicadores');
  const k = d.kpi;
  const P = d.precision;
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
        <div class="d">${num(k.en_ambas_bases)} aparecen en las dos bases</div>${medidor(k.en_ambas_bases, k.personas)}</a>
      <a class="kpi" href="/personas?con_cedula=1" data-ruta><div class="t">Con cédula</div><div class="v">${pct(k.con_cedula, k.personas)} %</div>
        <div class="d">${num(k.con_cedula)} identificadas</div>${medidor(k.con_cedula, k.personas)}</a>
      <a class="kpi" href="/mapa" data-ruta><div class="t">Georreferenciadas</div><div class="v">${pct(k.ubicadas, k.personas)} %</div>
        <div class="d">${num(k.ubicadas_exactas)} con dirección exacta</div>${medidor(k.ubicadas, k.personas)}</a>
      <a class="kpi" href="/personas?con_telefono=1" data-ruta><div class="t">Contactables</div><div class="v">${pct(k.con_telefono, k.personas)} %</div>
        <div class="d">${num(k.con_telefono)} con celular · ${num(k.con_correo)} con correo</div>${medidor(k.con_telefono, k.personas)}</a>
      <a class="kpi" href="/reuniones" data-ruta><div class="t">Alcanzadas en reuniones</div><div class="v">${num(k.alcanzadas)}</div>
        <div class="d">${num(k.reuniones)} reuniones · ${num(k.nuevas_en_reuniones)} personas nuevas</div>${medidor(k.alcanzadas, k.personas)}</a>
      <a class="kpi" href="/personas?orden=-completitud" data-ruta><div class="t">Completitud media del perfil</div><div class="v">${k.completitud_media} %</div>
        <div class="d">Sube con cada dato que se agrega</div>${medidor(k.completitud_media, 100)}</a>
      <a class="kpi ${k.pendientes_revision ? 'alerta' : ''}" href="/calidad" data-ruta><div class="t">Por revisar</div><div class="v">${num(k.pendientes_revision)}</div>
        <div class="d">personas con coincidencias por nombre · ${num(k.lugares_sin_punto)} lugares sin punto</div></a>
      <a class="kpi" href="/personas?consentimiento=si" data-ruta><div class="t">Autorización de datos</div><div class="v">${pct(k.consentimiento_si, k.personas)} %</div>
        <div class="d">${num(k.consentimiento_si)} con autorización firmada</div>${medidor(k.consentimiento_si, k.personas)}</a>
    </div>

    <div class="rejilla r-12">
      <section class="tarjeta c-7">
        <header><h2>Dónde vive la gente</h2><span class="nota">Personas por barrio o vereda</span></header>
        ${barras(d.lugares.map((l) => ({ etiqueta: titulo(l.nombre) + (l.tipo !== 'barrio' ? ` (${l.tipo.replace('_', ' ')})` : ''), valor: l.n, id: l.id,
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
        <h2 style="margin:22px 0 12px;font-size:15px">Zona</h2>
        ${apilada([
          { etiqueta: 'Casco urbano', valor: d.zonas.urbana || 0, color: 'var(--s1)' },
          { etiqueta: 'Rural', valor: d.zonas.rural || 0, color: 'var(--s3)' },
          { etiqueta: 'Sin dato', valor: d.zonas.sin || 0, color: 'var(--axis)' },
        ])}
        <h2 style="margin:22px 0 12px;font-size:15px">Completitud de los perfiles</h2>
        ${columnas(['0-24', '25-49', '50-74', '75-100'].map((r) => ({ etiqueta: r + ' %', valor: d.completitud.find((c) => c.rango === r)?.n || 0 })))}
      </section>

      <section class="tarjeta c-8">
        <header><h2>Trámites por mes</h2><span class="nota">${num(k.tramites)} solicitudes en la base de trámites</span></header>
        ${serieMensual(d.tramites_mes, { color: 'var(--s7)' })}
        <div class="chips" style="margin-top:12px">${d.tramites_tipo.map((t) => html`<span class="chip borde">${titulo(t.tipo || 'Sin tipo')} · <b>${num(t.n)}</b></span>`)}</div>
      </section>
      <section class="tarjeta c-4">
        <header><h2>Edad y sexo</h2><span class="nota">Donde la fuente lo trae</span></header>
        ${piramide(d.edades)}
      </section>

      <section class="tarjeta c-4">
        <header><h2>Necesidades registradas</h2><a class="nota" href="/ajustes" data-ruta>Editar catálogo</a></header>
        ${d.necesidades.length ? barras(d.necesidades.map((n) => ({ etiqueta: n.nombre, valor: n.n, id: n.id, color: n.grupo === 'necesidad' ? 'var(--s2)' : 'var(--s7)' })),
          { enlace: (i) => `/personas?etiqueta=${i.id}` })
          : html`<div class="vacio"><b>Aún no hay necesidades</b>Se registran en la ficha de cada habitante o durante las reuniones.</div>`}
      </section>
      <section class="tarjeta c-4">
        <header><h2>Listas de origen</h2><span class="nota">Base con cédula</span></header>
        ${barras(d.listas.map((l) => ({ etiqueta: l.lista, valor: l.n })), { color: 'var(--s4)', enlace: (i) => `/personas?lista=${encodeURIComponent(i.etiqueta)}` })}
      </section>
      <section class="tarjeta c-4">
        <header><h2>Últimas reuniones</h2><a class="nota" href="/reuniones" data-ruta>Ver todas</a></header>
        ${d.reuniones.length ? html`<div class="lista-barras">${d.reuniones.map((r) => html`<a class="f" href="/reuniones/${r.id}" data-ruta><span>${r.titulo}</span><span class="sec">${fecha(r.fecha)}</span><span class="n">${num(r.n)}</span></a>`)}</div>`
          : html`<div class="vacio"><b>Sin reuniones</b><a href="/reuniones" data-ruta>Programe la primera</a></div>`}
        <h2 style="margin:20px 0 10px;font-size:15px">Actividad reciente</h2>
        <div style="display:flex;flex-direction:column;gap:6px;font-size:13px">
          ${d.actividad.map((a) => html`<div><b>${a.usuario || 'sistema'}</b> ${ACCIONES[a.accion] || a.accion} ${a.entidad === 'persona' ? html`<a href="/personas/${a.entidad_id}" data-ruta>ficha ${a.entidad_id}</a>` : ''} <span class="sec">· ${fecha(a.ts, true)}</span></div>`)}
        </div>
      </section>
    </div>`);
}
