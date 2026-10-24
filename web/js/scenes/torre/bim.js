// Modo «Modelo BIM» de la vista de la torre (equipo F; especificación de integración 17.5; D integra).
// El modelo federado de la torre (arquitectura, estructura, cimentación, equipamiento fijo y dotación, con su refuerzo) se
// arma en 3D desde web/data/torre_bim*.json (bim3d.js) y se explora con:
//  · el árbol por disciplina → nivel → clase → elemento, con contadores, buscador, y ver, aislar, ocultar o volver
//    transparente cada disciplina;
//  · la ficha del elemento: clase IFC4 y GlobalId, conjuntos de propiedades, cantidades, 5D (ítem del presupuesto y su
//    APU), 4D (fase del cronograma), norma y fuente, vínculo con el análisis sísmico, «Ver refuerzo» y la vista de corte;
//  · cortes horizontales por nivel y verticales por eje (A-D, 1-7) con tapa rayada;
//  · la cimentación con el terreno cortado o semitransparente, pilotes completos hasta su punta, dados, vigas de amarre,
//    contrapiso, fosos y cisternas, con cotas y cargas;
//  · el refuerzo del elemento o del eje elegido en 3D (bim_refuerzo.js) y su despiece en 2D (bim_despiece.js);
//  · los colores del último cálculo del simulador (D/C, rótulas y deriva), el 5D, el 4D, las interferencias y el IFC.
// torre.js lo carga de forma perezosa y le pasa ctx (6.2, 8.6 y su bloque «bim»): st, raiz, hud (torre.hud.bim), panel
// (torre.panel.bim), ficha (torre.ficha.modo), tarjeta (torre.bim) y tablas (torre.bim.tablas), datos { indice, leer,
// url }, textos { limpio, esc, escH }, exterior.ocultar(on), sismo.ultimo(), abrirModo(m) y alSalir(). Solo escribe en
// esos contenedores. Modelo de prefactibilidad: no reemplaza los diseños firmados.
import { THREE, tokens, onTheme, engine, reducedMotion } from '../../core.js';
import { crearModelo3D, crearTerreno, DISCIPLINAS, solidosDe } from './bim3d.js';
import { crearRefuerzo3D, crearBandas, FAMILIAS, familia, polilineas } from './bim_refuerzo.js';
import { despiece, tipoDespiece } from './bim_despiece.js';

export const AVISO = 'Modelo de prefactibilidad: no reemplaza los diseños firmados.';
const NOM_DISC = { ARQ: 'Arquitectura', EST: 'Estructura', CIM: 'Cimentación', FIJO: 'Equipamiento fijo', DOT: 'Dotación', REF: 'Refuerzo' };
const NIVEL_CORTO = { 'CIM-PIL': 'Pilotes', CIM: 'Cimentación', BT: 'Bloque técnico', EXT: 'Exteriores', P1: 'Piso 1', P2: 'Piso 2', P3: 'Piso 3', P4: 'Piso 4', CUB: 'Cubierta' };
// cortes horizontales: un plano a 1,20 m sobre cada piso (como una planta de arquitectura) y uno a −1,00 m en la cimentación
const CORTES_NIVEL = [['CIM', -1.0, 'Cimentación'], ['P1', 1.2, 'Piso 1'], ['P2', 5.7, 'Piso 2'], ['P3', 9.9, 'Piso 3'], ['P4', 14.1, 'Piso 4'], ['CUB', 18.3, 'Cubierta']];
const NIVELES_EJE = [['CIM', 'Cimentación'], ['P1', 'Piso 1'], ['P2', 'Piso 2'], ['P3', 'Piso 3'], ['P4', 'Piso 4'], ['CUB', 'Cubierta']];
const PESTANAS = [['modelo', 'Modelo'], ['cortes', 'Cortes'], ['cimentacion', 'Cimentación'], ['refuerzo', 'Refuerzo'], ['comportamiento', 'Comportamiento'], ['5d', '5D'], ['4d', '4D'], ['interferencias', 'Interferencias'], ['ifc', 'IFC']];
const PROP = {
  Reference: 'Referencia', LoadBearing: 'Portante', IsExternal: 'Exterior', StrengthClass: 'Resistencia del concreto', ConcreteCover: 'Recubrimiento (m)',
  FireRating: 'Resistencia al fuego', AcousticRating: 'Aislamiento acústico', GrossPlannedArea: 'Área planeada (m²)', PubliclyAccessible: 'Acceso del público',
  XDirectionLowerBarCount: 'Barras inferiores en x', YDirectionLowerBarCount: 'Barras inferiores en y', ModelLabel: 'Modelo', Manufacturer: 'Fabricante',
  ProductionYear: 'Año', IsTemporary: 'Provisional', NominalHeight: 'Altura nominal (m)', NominalWidth: 'Ancho nominal (m)', NominalLength: 'Largo nominal (m)',
  HandicapAccessible: 'Accesible', FireExit: 'Salida de emergencia', SelfClosing: 'Cierre automático', Status: 'Estado', ArticleNumber: 'Referencia comercial',
  NumberOfRiser: 'Contrahuellas', NumberOfTreads: 'Huellas', RiserHeight: 'Contrahuella (m)', TreadLength: 'Huella (m)', Category: 'Categoría',
  Slope: 'Pendiente', ReinforcementStrengthClass: 'Acero de refuerzo', HoopBarPitch: 'Separación de estribos (m)', XDirectionTieHoopBarPitch: 'Separación de ganchos en x (m)',
  XDirectionTieHoopCount: 'Ganchos en x', YDirectionTieHoopBarPitch: 'Separación de ganchos en y (m)', YDirectionTieHoopCount: 'Ganchos en y', Span: 'Luz (m)',
  StirrupBarPitch: 'Separación de estribos (m)', ServiceLifeDuration: 'Vida útil', ExtendToStructure: 'Llega a la estructura', VerticalBarPitch: 'Separación vertical (m)',
  HorizontalBarPitch: 'Separación horizontal (m)', BarAllocationType: 'Distribución de barras', LongOutsideTopBarPitch: 'Separación superior longitudinal (m)',
  ShortOutsideTopBarPitch: 'Separación superior en la dirección corta (m)',
};
const QTO = {
  Length: ['Longitud', 'm'], Width: ['Ancho', 'm'], Height: ['Altura', 'm'], Depth: ['Espesor', 'm'], CrossSectionArea: ['Área de la sección', 'm²'],
  OuterSurfaceArea: ['Superficie exterior', 'm²'], GrossVolume: ['Volumen bruto', 'm³'], NetVolume: ['Volumen neto', 'm³'], NetWeight: ['Peso', 'kg'],
  GrossArea: ['Área bruta', 'm²'], NetArea: ['Área neta', 'm²'], GrossSideArea: ['Área lateral bruta', 'm²'], NetSideArea: ['Área lateral neta', 'm²'],
  GrossFloorArea: ['Área bruta de piso', 'm²'], NetFloorArea: ['Área neta de piso', 'm²'], GrossPerimeter: ['Perímetro', 'm'], Area: ['Área', 'm²'],
};
const PSET = {
  ColumnCommon: 'columna', BeamCommon: 'viga', SlabCommon: 'losa', WallCommon: 'muro', PileCommon: 'pilote', FootingCommon: 'cimiento', DoorCommon: 'puerta',
  WindowCommon: 'ventana', SpaceCommon: 'espacio', CoveringCommon: 'acabado', StairCommon: 'escalera', StairFlightCommon: 'tramo de escalera',
  ConcreteElementGeneral: 'concreto', ReinforcementBarCountOfIndependentFooting: 'barras del cimiento', ManufacturerTypeInformation: 'fabricante y modelo',
  RampCommon: 'rampa', RoofCommon: 'cubierta', BuildingElementProxyCommon: 'elemento', ServiceLife: 'vida útil',
  ReinforcementBarPitchOfColumn: 'separación del refuerzo de la columna', ReinforcementBarPitchOfBeam: 'separación del refuerzo de la viga',
  ReinforcementBarPitchOfWall: 'separación del refuerzo del muro', ReinforcementBarPitchOfSlab: 'separación del refuerzo de la losa',
};
const nombrePset = (k) => { const b = k.replace(/^Pset_/, ''); return PSET[b] ? `Propiedades de ${PSET[b]}` : b.replace(/([a-z])([A-Z])/g, '$1 $2'); };
const n = (v, d = 2) => (Number.isFinite(+v) ? (+v).toLocaleString('es-CO', { minimumFractionDigits: d, maximumFractionDigits: d }) : '—');
const n0 = (v) => n(v, 0);
const cop = (v) => (Number.isFinite(+v) ? `$${(+v).toLocaleString('es-CO', { maximumFractionDigits: 0 })}` : '—');
const millones = (v) => (Number.isFinite(+v) ? `${+v < 0 ? '−' : ''}$${n(Math.abs(v) / 1e6, 1)} millones` : '—');
const conSigno = (t, v) => (+v > 0 ? `+${t}` : t);
const cota = (z) => `${z > 0.004 ? '+' : z < -0.004 ? '−' : '±'}${n(Math.abs(z), 2)}`;
const fechaTxt = (d) => new Date(`${d}T12:00:00`).toLocaleDateString('es-CO', { day: 'numeric', month: 'short', year: 'numeric' });
const DIA = 86400000;
const P3 = (x, y, z) => new THREE.Vector3(x, z, -y);   // proyecto → three

export async function montar(ctx) {
  const { st, panel, hud, ficha, textos } = ctx;
  const { esc, escH } = textos;
  const IDX = ctx.datos?.indice || null;
  const leer = ctx.datos?.leer || (() => Promise.resolve(null));
  const qs = new URLSearchParams(location.search);
  const telefono = () => (st.el?.clientWidth || 800) < 560;

  // ================================================================ contenedores
  const elPanel = document.createElement('div'); elPanel.className = 'bim-panel';
  const elHud = document.createElement('div'); elHud.className = 'bim-hud';
  const elFicha = document.createElement('div'); elFicha.className = 'bim-ficha';
  const elTablas = document.createElement('div'); elTablas.className = 'bim-tablas';
  const $ = (r, s) => r.querySelector(s);
  const $$ = (r, s) => [...r.querySelectorAll(s)];
  const tab = (id) => $(elPanel, `[data-pest="${id}"]`);

  if (!IDX) {
    elPanel.innerHTML = `<h3>Modelo BIM</h3><p class="note">El modelo BIM de la torre todavía no está publicado: cuando lo esté, aquí se podrá recorrer por disciplinas, cortar, ver la cimentación y el refuerzo, y descargar el IFC.</p><p class="note bim-aviso">${AVISO}</p>`;
  } else {
    elPanel.innerHTML = `<h3>Modelo BIM</h3>
      <p class="note">${esc(IDX.nombre)}, en IFC4: ${n0(IDX.totales?.elementos)} elementos y ${n0(IDX.totales?.barras)} barras de refuerzo (${n0(IDX.totales?.acero_kg)} kg): arquitectura, estructura, cimentación, equipamiento fijo y dotación. <span class="bim-tipo">Cálculo propio sobre el anteproyecto y el prediseño estructural.</span></p>
      <p class="note bim-aviso">${AVISO}</p>
      <div class="seg wrap-seg bim-pestanas" role="tablist" aria-label="Herramientas del modelo BIM">${PESTANAS.map(([id, t], i) => `<button type="button" role="tab" data-p="${id}" aria-selected="${i === 0}" aria-pressed="${i === 0}">${t}</button>`).join('')}</div>
      <p class="bim-estado" data-b="estado" aria-live="polite"></p>
      ${PESTANAS.map(([id], i) => `<div class="bim-pest" role="tabpanel" data-pest="${id}"${i ? ' hidden' : ''}></div>`).join('')}`;
  }
  elHud.innerHTML = `<div class="bim-chip" data-b="chip" hidden></div><details class="bim-ley" data-b="ley" hidden><summary>Leyenda</summary><div data-b="ley-c"></div></details>
    <div class="bim-acc" data-b="acc"></div>
    <div class="bim-4d" data-b="barra4d" hidden><button type="button" data-b="play4d">Construir</button><input type="range" data-b="r4d" min="0" max="1000" step="1" value="1000" aria-label="Fecha del cronograma"><span class="bim-4d-t" data-b="t4d"></span></div>`;
  elFicha.innerHTML = '<p class="note">Toca un elemento del modelo (o búscalo en el árbol) para ver su clase IFC, sus propiedades, cantidades, costo, fase de obra, norma y refuerzo.</p>';
  const estado = (t) => { const o = $(elPanel, '[data-b="estado"]'); if (o) o.textContent = t || ''; };

  // ================================================================ datos del modelo (los nueve niveles)
  let L = [], porId = new Map(), m3d = null, terreno = null, cargado = null, cajaTotal = null;
  const NIV = (IDX?.niveles || []).map((q) => q.id);
  const fases = new Map((IDX?.cuatro_d?.fases || []).map((f) => [f.id, f]));
  const items = new Map((IDX?.cinco_d?.comparacion || []).map((c) => [String(c.item), c]));
  // capítulo del presupuesto en palabras: los numerados con su nombre; los otros componentes, con la descripción de su ítem
  const nombreCapitulo = (k) => IDX?.cinco_d?.capitulos?.[k] || String(items.get(k)?.descripcion || k).split(/[:(]/)[0].trim();
  async function cargar() {
    if (!IDX) return false;
    estado('Cargando el modelo: 0 de 9 niveles…');
    let k = 0;
    const archivos = IDX.archivos?.elementos || {};
    const D = await Promise.all(NIV.map((nv) => (archivos[nv] ? leer(archivos[nv]).then((d) => { estado(`Cargando el modelo: ${++k} de ${NIV.length} niveles…`); return d; }) : null)));
    D.forEach((d, i) => {
      if (!d) return;
      for (const e of d.elementos) { porId.set(e.id, L.length); L.push({ e, nivel: NIV[i], ficha: d.fichas?.[e.ficha] || null, psets: d.psets?.[e.psets] || null }); }
    });
    if (!L.length) { estado('No se pudo leer el modelo.'); return false; }
    m3d = crearModelo3D(L, { tier: engine.tier });
    m3d.tema(tokens());
    ref3d = crearRefuerzo3D(m3d.planos, { radial: telefono() ? 6 : 8 });
    grupo.add(ref3d.grupo);
    grupo.add(m3d.grupo);
    cajaTotal = m3d.caja(L.map((_, i) => i).filter((i) => L[i].e.clase !== 'IfcSpace' && !/^(EXT|CIM-PIL)$/.test(L[i].nivel)));
    // hueco del terreno: la huella de la cimentación con 2 m de holgura
    const cim = L.map((x, i) => i).filter((i) => L[i].e.disciplina === 'CIM');
    const bc = cim.reduce((b, i) => { const c = m3d.cajaProyecto(i); return [Math.min(b[0], c[0]), Math.min(b[1], c[1]), Math.min(b[2], c[2]), Math.max(b[3], c[3]), Math.max(b[4], c[4])]; }, [Infinity, Infinity, Infinity, -Infinity, -Infinity]);
    terreno = crearTerreno(st, { hueco: [bc[0] - 2, bc[1] - 2, bc[3] + 2, bc[4] + 2], fondo: Math.floor(bc[2] - 1.5) });
    grupo.add(terreno.grupo);
    construirArbol();
    aplicar();
    estado('');
    return true;
  }
  const grupo = new THREE.Group(); grupo.name = 'bim';
  const el = (gi) => L[gi]?.e;
  const giDe = (id) => porId.get(id);

  // ================================================================ estado de la vista
  const S = {
    pest: 'modelo', vista: 'modelo', sel: -1, ocultos: new Set(), aislados: null, claseOff: new Set(), nivelOff: new Set(), espacios: false,
    modosUsuario: Object.fromEntries(DISCIPLINAS.map((d) => [d, 'normal'])), corte: null, fecha: null, colores: null, refuerzo: null, terreno: 'opaco',
  };
  const modosVista = () => {
    const v = S.vista, M = { ...S.modosUsuario };
    if (v === 'cimentacion') Object.assign(M, { ARQ: 'oculta', FIJO: 'oculta', DOT: 'oculta', EST: 'transparente', CIM: 'normal' });
    if (v === 'refuerzo') Object.assign(M, { ARQ: 'oculta', FIJO: 'oculta', DOT: 'oculta', EST: 'transparente', CIM: 'transparente' });
    if (v === 'comportamiento') Object.assign(M, { ARQ: 'oculta', FIJO: 'oculta', DOT: 'oculta', EST: 'normal', CIM: 'normal' });
    return M;
  };
  function filtro(gi) {
    const x = L[gi], e = x.e;
    if (S.aislados && !S.aislados.has(gi)) return false;
    if (S.ocultos.has(gi)) return false;
    if (e.clase === 'IfcSpace' && !S.espacios) return false;
    if (S.claseOff.has(`${e.disciplina}|${x.nivel}|${e.clase}`) || S.claseOff.has(`${e.disciplina}|*|${e.clase}`)) return false;
    if (S.nivelOff.has(x.nivel)) return false;
    if (S.fecha != null) { const f = fases.get(e.fase); if (f && Date.parse(`${f.inicio}T00:00:00`) > S.fecha) return false; }
    if (S.refuerzo?.ocultar?.has(gi)) return false;
    if (S.vista === 'cimentacion' && S.velo?.has(gi)) return false;
    if (S.vista === 'refuerzo' && S.refuerzo?.cerca && !S.refuerzo.cerca.has(gi) && !S.aislados) return false;
    if (S.vista === 'cimentacion' && e.disciplina === 'EST' && x.nivel !== 'P1') return false;
    return true;
  }
  function aplicar() {
    if (!m3d) return;
    const M = modosVista();
    for (const d of DISCIPLINAS) if (m3d.modoDisc[d] !== M[d]) m3d.disciplina(d, M[d]);
    m3d.aplicarVisibles(filtro);
    // 4D: lo que está en obra en la fecha elegida va en el color de aviso
    m3d.E.sinFase();
    if (S.fecha != null) L.forEach((x, gi) => { const f = fases.get(x.e.fase); if (f && Date.parse(`${f.inicio}T00:00:00`) <= S.fecha && Date.parse(`${f.fin}T23:59:59`) >= S.fecha) m3d.E.fase(gi, true); });
    m3d.subir();
    st.invalidate(true);
    contadores();
  }

  // ================================================================ etiquetas sobre el 3D (se quitan al salir o al cambiar de vista)
  const etiquetas = new Set();
  const gEtq = new THREE.Group(); gEtq.name = 'bim_etiquetas'; grupo.add(gEtq);
  function etq(html, pos, cls = 'lbl-node bim-lbl') { const o = st.label(html, cls, [pos.x, pos.y, pos.z], gEtq); etiquetas.add(o); return o; }
  function quitarEtiquetas(filtroE = () => true) {
    for (const o of [...etiquetas]) {
      if (!filtroE(o)) continue;
      o.element.remove(); o.parent?.remove(o); etiquetas.delete(o);
      const k = st._labels.indexOf(o); if (k >= 0) st._labels.splice(k, 1);
    }
  }

  // ================================================================ selección (clic en el modelo, en el árbol o en una lista)
  function seleccionar(gi, { volar = false, ficha: conFicha = true } = {}) {
    if (!m3d) return;
    if (S.sel >= 0) m3d.E.sel(S.sel, 0);
    S.sel = gi ?? -1;
    if (S.sel >= 0) { m3d.E.sel(S.sel, 255); m3d.resaltar(gisDe(S.sel)); } else m3d.resaltar(null);
    m3d.subir();
    if (conFicha) fichaElemento();
    if (volar && S.sel >= 0) encuadrar(m3d.caja(gisDe(S.sel)), { margen: 0.55 });
    st.invalidate();
    marcarArbol();
  }
  // un conjunto (escalera, foso) se elige con sus partes; una parte se elige sola
  const gisDe = (gi) => { const e = el(gi); return e?.partes?.length ? e.partes.map(giDe).filter((q) => q != null) : [gi]; };
  function encuadrar(caja, { margen = 0.8, dir = null } = {}) {
    if (!caja || caja.isEmpty()) return;
    const d = dir || new THREE.Vector3(-0.75, 0.55, 0.62);
    const ang = telefono();
    st.frameBox(caja, d, { margin: ang ? Math.min(0.95, margen + 0.12) : margen, duration: reducedMotion ? 0 : 1.1, ty: 0.45 });
  }
  // clic sin arrastre: barra (en la vista de refuerzo) o elemento
  const ray = new THREE.Raycaster(), ptr = new THREE.Vector2(), lienzo = engine.renderer.domElement;
  let abajo = null, dentro = false;
  const alBajar = (e) => { if (dentro && st.isActive()) abajo = { x: e.clientX, y: e.clientY, t: performance.now() }; };
  const alSubir = (e) => {
    if (!abajo || !dentro || !m3d || !st.isActive()) { abajo = null; return; }
    const d = Math.hypot(e.clientX - abajo.x, e.clientY - abajo.y), dt = performance.now() - abajo.t;
    abajo = null;
    if (d > 6 || dt > 500) return;
    const r = lienzo.getBoundingClientRect();
    ptr.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ptr, st.camera);
    if (S.refuerzo) { const b = ref3d?.pick(ray); if (b) { fichaJuego(b.juego); return; } }
    const h = m3d.pick(ray);
    if (h) seleccionar(h.gi);
  };
  lienzo.addEventListener('pointerdown', alBajar);
  lienzo.addEventListener('pointerup', alSubir);

  // ================================================================ ficha del elemento
  const kvFila = (k, v) => (v == null || v === '' ? '' : `<dt>${k}</dt><dd>${v}</dd>`);
  const valorProp = (v) => (typeof v === 'boolean' ? (v ? 'sí' : 'no') : typeof v === 'number' ? n(v, Math.abs(v) < 10 && v % 1 ? 3 : v % 1 ? 2 : 0) : esc(v));
  function fichaElemento() {
    if (S.sel < 0) { elFicha.innerHTML = '<p class="note">Toca un elemento del modelo (o búscalo en el árbol) para ver sus propiedades.</p>'; return; }
    const x = L[S.sel], e = x.e, fi = x.ficha || {}, f = fases.get(e.fase), host = hostDe(S.sel);
    const padre = e.parte_de ? giDe(e.parte_de) : null;
    const costo = (e.costo || []).map((c) => {
      const it = items.get(String(c.item));
      return `<li><b>Ítem ${esc(c.item)}</b> ${esc(it?.descripcion || '')}<br><small>${c.cantidad != null ? `${n(c.cantidad, 2)} ${esc(it?.unidad || '')} × ` : ''}${cop(c.valor_unitario)}${c.valor != null ? ` = <b>${cop(c.valor)}</b>` : ''}${it?.apu ? ` · análisis de precio ${esc(it.apu)}` : ''}${c.nota ? ` · ${esc(c.nota)}` : ''}</small></li>`;
    }).join('');
    const qto = Object.entries(e.qto || {}).map(([k, v]) => `<details class="fold"><summary>Cantidades <small class="note">(${esc(k)})</small></summary><dl class="kv">${Object.entries(v).map(([q, val]) => kvFila(QTO[q] ? `${QTO[q][0]} (${QTO[q][1]})` : esc(q), valorProp(val))).join('')}</dl></details>`).join('');
    const ps = Object.entries(x.psets || {}).map(([k, v]) => `<details class="fold"><summary>${esc(nombrePset(k))} <small class="note">(${esc(k)})</small></summary><dl class="kv">${Object.entries(v).map(([q, val]) => kvFila(esc(PROP[q] || q), valorProp(val))).join('')}</dl></details>`).join('');
    const an = e.analisis || {};
    let anal = '';
    if (an.elementos?.length) {
      const dc = S.colores?.porGi?.get(S.sel);
      anal = `<p class="note">${an.elementos.length > 1 ? 'Entra al simulador sísmico en sus dos direcciones (pórticos en x y en y).' : 'Entra al simulador sísmico como elemento de su pórtico.'}${dc != null ? ` En el último cálculo del simulador llegó a <b>D/C = ${n(dc, 2)}</b> (cálculo propio).` : ''}</p>`;
    } else if (an.capacidad_kN) {
      anal = `<dl class="kv">${kvFila('Capacidad admisible', `${n0(an.capacidad_kN.Qadm)} kN`)}${kvFila('Capacidad con sismo', `${n0(an.capacidad_kN.Qsismo)} kN`)}${kvFila('Reacción máxima con sismo', `${n0(an.reaccion_max_kN?.sismo)} kN`)}${kvFila('Reacción mínima con sismo', `${n0(an.reaccion_min_kN?.sismo)} kN`)}</dl><p class="note">Estimación del prediseño con parámetros típicos de suelo aluvial: la fija el estudio geotécnico.</p>`;
    } else if (an.cargas_servicio_kN) {
      const c = Object.values(an.cargas_servicio_kN)[0] || {}, R = an.reacciones_pilote_kN || {};
      anal = `<dl class="kv">${kvFila('Carga muerta de servicio', `${n0(c.D_kN)} kN`)}${kvFila('Carga viva', `${n0(c.L_kN)} kN`)}${R.sismo ? kvFila('Reacción por pilote con sismo', `${n0(R.sismo.min)} a ${n0(R.sismo.max)} kN`) : ''}${R.capacidad ? kvFila('Con la capacidad de la columna', `${n0(R.capacidad.min)} a ${n0(R.capacidad.max)} kN`) : ''}</dl><p class="note">Cálculo propio del prediseño (la base del modelo sísmico está empotrada en la cara superior del dado).</p>`;
    } else if (an.nota) anal = `<p class="note">${esc(an.nota)}</p>`;
    const conRef = host != null;
    elFicha.innerHTML = `<h4>${esc(e.nombre)}</h4>
      <p class="bim-id"><span class="pill">${esc(e.clase)}${e.tipo_predefinido ? ` · ${esc(e.tipo_predefinido)}` : ''}</span> <span class="pill">${esc(NOM_DISC[e.disciplina] || e.disciplina)}</span> <span class="pill">${esc(NIVEL_CORTO[x.nivel] || x.nivel)}</span></p>
      <dl class="kv">${kvFila('Código', esc(e.id))}${kvFila('GlobalId (IFC)', `<code>${escH(e.guid)}</code>`)}${kvFila('Material', esc(IDX.materiales?.[e.material]?.nombre || e.material || ''))}${padre != null ? kvFila('Parte de', `<button type="button" class="bim-link" data-ir="${escH(e.parte_de)}">${esc(el(padre).nombre)}</button>`) : ''}${e.refuerzo_texto ? kvFila('Refuerzo', esc(e.refuerzo_texto)) : ''}</dl>${e.parrillas_dibujadas ? `<p class="note bim-nota-parrilla">${esc(notaParrillas(e))} <span class="bim-tipo">(cálculo propio)</span></p>` : ''}
      <div class="bim-acciones">${conRef ? '<button type="button" class="btn" data-acc="ref">Ver refuerzo</button>' : ''}${/IfcColumn|IfcBeam|IfcSlab|IfcWall|IfcFooting|IfcPile|IfcStair/.test(e.clase) ? '<button type="button" class="btn ghost" data-acc="corte">Vista de corte</button>' : ''}${an.elementos?.length ? '<button type="button" class="btn ghost" data-acc="sismo">Abrir en el simulador</button>' : ''}<button type="button" class="btn ghost" data-acc="aislar">${S.aislados ? 'Mostrar todo' : 'Aislar'}</button><button type="button" class="btn ghost" data-acc="ocultar">Ocultar</button></div>
      <div data-b="despiece"></div>
      ${fi.TipoDato || fi.Fuente || fi.Norma ? `<h5>Norma, fuente y tipo de dato</h5><dl class="kv">${kvFila('Tipo de dato', esc(fi.TipoDato))}${kvFila('Fuente', esc(fi.Fuente))}${kvFila('Norma', esc(fi.Norma))}${kvFila('Numeral', esc(fi.Numeral))}</dl>${fi.Nota ? `<p class="note">${esc(fi.Nota)}</p>` : ''}` : ''}
      ${costo ? `<h5>Costo (5D)</h5><ul class="tight bim-costo">${costo}</ul><p class="note">Cantidad del modelo × valor unitario del presupuesto (pesos de 2026; cálculo propio con precios estimados).</p>` : ''}
      ${f ? `<h5>Fase de obra (4D)</h5><p class="note"><b>${esc(f.nombre)}</b><br>${fechaTxt(f.inicio)} a ${fechaTxt(f.fin)} · etapa ${f.etapa}: ${esc(f.etapa_nombre)} <span class="bim-tipo">(estimación con el cronograma del proyecto)</span></p>` : ''}
      ${anal ? `<h5>Análisis estructural</h5>${anal}` : ''}
      ${qto}${ps}`;
    if (S.refuerzo && S.refuerzo.hosts?.includes(host)) pintarDespiece();
  }
  elFicha.addEventListener('click', (ev) => {
    const b = ev.target.closest('button');
    if (!b) return;
    if (b.dataset.ir) { const gi = giDe(b.dataset.ir); if (gi != null) seleccionar(gi, { volar: true }); return; }
    const a = b.dataset.acc;
    if (a === 'ref') verRefuerzo(L[S.sel].e.id);
    else if (a === 'corte') corteElemento(L[S.sel].e.id);
    else if (a === 'sismo') ctx.abrirModo?.('sismo');
    else if (a === 'aislar') { S.aislados = S.aislados ? null : new Set(gisDe(S.sel)); aplicar(); fichaElemento(); if (S.aislados) encuadrar(m3d.caja([...S.aislados]), { margen: 0.6 }); }
    else if (a === 'ocultar') { for (const g of gisDe(S.sel)) S.ocultos.add(g); const s = S.sel; seleccionar(-1); aplicar(); estado(`Se ocultó «${L[s].e.nombre}». «Mostrar todo» en la pestaña Modelo lo devuelve.`); }
  });
  function fichaJuego(j) {
    const d = $(elFicha, '[data-b="juego"]') || (() => { const q = document.createElement('div'); q.dataset.b = 'juego'; q.className = 'bim-juego'; elFicha.prepend(q); return q; })();
    d.innerHTML = `<h5>Barra elegida</h5><p><b>${esc(j.etiqueta)}</b> · ${esc(j.tipo)}</p><dl class="kv">${kvFila('Diámetro', `N.º ${j.num} (${n(j.db_mm, 1)} mm)`)}${kvFila('Barras del juego', n0(j.n))}${kvFila('Largo de cada una', `${n(j.largo_m, 2)} m`)}${kvFila('Peso del juego', `${n(j.kg, 1)} kg`)}${j.zona ? kvFila('Zona', esc(j.zona)) : ''}${j.ganchos ? kvFila('Ganchos', esc(j.ganchos)) : ''}${kvFila('GlobalId (IFC)', `<code>${escH(j.guid)}</code>`)}</dl>${j.nota ? `<p class="note">${esc(j.nota)}</p>` : ''}`;
  }

  // ================================================================ refuerzo: del elemento o del eje
  let ref3d = null;   // se crea con el modelo (comparte sus planos de corte)
  const refs = new Map();   // nivel → { formas, porHost }
  async function cargarRef(nivel) {
    if (refs.has(nivel)) return refs.get(nivel);
    const f = IDX?.archivos?.refuerzo?.[nivel];
    const p = (f ? leer(f) : Promise.resolve(null)).then((d) => {
      if (!d) return null;
      const porHost = new Map();
      for (const j of d.juegos) { if (!porHost.has(j.host)) porHost.set(j.host, []); porHost.get(j.host).push(j); }
      return { formas: d.formas, porHost };
    });
    refs.set(nivel, p);
    return p;
  }
  // anfitrión del refuerzo de un elemento: él mismo o el conjunto del que es parte (escaleras, fosos)
  function hostDe(gi) {
    const e = el(gi);
    if (!e) return null;
    if (e.refuerzo) return e.id;
    if (e.parte_de) { const p = el(giDe(e.parte_de)); if (p?.refuerzo) return p.id; }
    return null;
  }
  let bandas = null, fant = null, barrasInfo = null;
  function limpiarRefuerzo() {
    ref3d?.limpiar();
    if (bandas) { grupo.remove(bandas); bandas.userData.dispose(); bandas = null; }
    if (fant) { grupo.remove(fant); fant.userData.dispose(); fant = null; }
    quitarEtiquetas((o) => o.userData.bim === 'ref');
    S.refuerzo = null; barrasInfo = null;
  }
  // columna de abajo y de arriba (para ver los traslapos): C-B2-2 → C-B2-1 y C-B2-3
  const vecinaColumna = (id, d) => { const m = id.match(/^(C-[A-D]\d-)(\d)$/); return m ? `${m[1]}${+m[2] + d}` : null; };
  async function verRefuerzo(hosts, { eje = null, resaltar = null, volar = true, conCorte = null, dir = null } = {}) {
    if (!m3d) await cargado;
    hosts = [].concat(hosts).map((h) => hostDe(giDe(h)) || h).filter((h, i, a) => h && a.indexOf(h) === i && giDe(h) != null);
    if (!hosts.length) return null;
    exclusivo('refuerzo');
    limpiarRefuerzo();
    if (!conCorte) { if (S.corte?.elemento) quitarCorte(); S.aislados = null; }
    const conjuntos = [], unico = hosts.length === 1;
    for (const h of hosts) {
      const R = await cargarRef(L[giDe(h)].nivel);
      let js = R?.porHost.get(h);
      // en una viga, las barras corridas del pórtico se reparten entre sus tramos: se suman las de los otros tramos que
      // pasan por este (son parte de su armado; allí se ven también sus empalmes)
      if (unico && R && /IfcBeam|IfcFooting/.test(L[giDe(h)].e.clase) && /^V[XYC]-/.test(h)) js = [...(js || []), ...corridasQuePasan(h, R)];
      if (js?.length) conjuntos.push({ juegos: js, formas: R.formas, host: h });
    }
    // contexto de una columna: las longitudinales de la de abajo y la de arriba, en gris (el traslapo se ve donde se cruzan)
    if (unico && /^C-[A-D]\d-\d$/.test(hosts[0])) {
      for (const d of [-1, 1]) {
        const v = vecinaColumna(hosts[0], d), gv = v && giDe(v);
        if (gv == null) continue;
        const R = await cargarRef(L[gv].nivel), js = R?.porHost.get(v)?.filter((j) => familia(j.rol) === 'longitudinal');
        if (js?.length) conjuntos.push({ juegos: js, formas: R.formas, tono: 'apagado', host: v });
      }
    }
    const ghost = hosts.flatMap((h) => gisDe(giDe(h)));
    // contexto: solo la estructura a menos de 2,5 m de lo elegido (transparente); el resto se oculta para leer el armado
    const cb = ghost.map((g) => m3d.cajaProyecto(g)).reduce((a, b) => [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.min(a[2], b[2]), Math.max(a[3], b[3]), Math.max(a[4], b[4]), Math.max(a[5], b[5])]);
    const cerca = new Set();
    const conLosas = hosts.some((h) => /IfcSlab|IfcStair/.test(L[giDe(h)].e.clase));
    L.forEach((x, gi) => { if (!conLosas && x.e.clase === 'IfcSlab' && x.e.disciplina === 'EST') return; const b = m3d.cajaProyecto(gi); if (b[0] <= cb[3] + 2.5 && b[3] >= cb[0] - 2.5 && b[1] <= cb[4] + 2.5 && b[4] >= cb[1] - 2.5 && b[2] <= cb[5] + 1 && b[5] >= cb[2] - 1) cerca.add(gi); });
    S.refuerzo = { hosts, eje, ocultar: new Set(ghost), conjuntos, cerca, resaltar };
    S.vista = 'refuerzo';
    const bajoTierra = hosts.some((h) => /^CIM/.test(L[giDe(h)].nivel));
    S.terreno = bajoTierra ? 'semi' : 'opaco'; terreno.poner(S.terreno);
    barrasInfo = ref3d.mostrar(conjuntos, { resaltar });
    fant = m3d.fantasma(ghost, { opacidad: 0.14 }); grupo.add(fant);
    // zonas del armado y etiquetas (solo con un elemento: con un eje entero serían demasiadas)
    if (unico) zonasYEtiquetas(hosts[0], conjuntos.filter((c) => c.tono !== 'apagado'), { llamadas: !conCorte });
    aplicar();
    if (conCorte) cortar(conCorte, { conTapa: (gi) => S.refuerzo?.ocultar.has(gi), volar: false });
    if (volar && !conCorte) {
      const caja = m3d.caja(ghost).expandByScalar(0.6);
      if (!unico && barrasInfo?.cajaPropia && !barrasInfo.cajaPropia.isEmpty()) caja.union(barrasInfo.cajaPropia);
      const vertical = unico && /IfcColumn|IfcPile|IfcWall/.test(L[giDe(hosts[0])].e.clase);
      encuadrar(caja, { margen: unico ? 0.8 : 0.85, dir: conCorte ? dirCorte(conCorte) : dir || (vertical ? new THREE.Vector3(-0.8, 0.3, 0.52) : null) });
    }
    if (unico) { const gi = giDe(hosts[0]); if (S.sel !== gi && !L[S.sel]?.e?.parte_de) seleccionar(gi, { ficha: true }); else fichaElemento(); pintarDespiece(); }
    leyendaRefuerzo();
    chip(unico ? `Refuerzo de ${L[giDe(hosts[0])].e.nombre}` : `Refuerzo del eje ${eje?.eje} · ${NIVEL_CORTO[eje?.nivel] || ''}`);
    accionesHud();
    pintarPestRefuerzo();
    st.invalidate(true);
    return { hosts, ...resumenRef() };
  }
  function corridasQuePasan(h, R) {
    const gi = giDe(h), b = m3d.cajaProyecto(gi), enX = b[3] - b[0] >= b[4] - b[1], k = enX ? 0 : 1;
    const pre = h.replace(/-[A-D0-9]{2}(-\d+)?$/, ''), suf = (h.match(/-\d+$/) || [''])[0], out = [];
    for (const [hh, js] of R.porHost) {
      if (hh === h || !hh.startsWith(`${pre}-`) || (suf && !hh.endsWith(suf))) continue;
      for (const j of js) {
        if (!/corrida/.test(j.rol)) continue;
        const pl = polilineas(j, R.formas)[0] || [];
        const a = Math.min(...pl.map((q) => q[k])), c = Math.max(...pl.map((q) => q[k]));
        if (a < b[k + 3] - 0.3 && c > b[k] + 0.3) out.push(j);   // se traslapa con el tramo (los empalmes también)
      }
    }
    return out;
  }
  const resumenRef = () => ({ barras: barrasInfo?.barras || 0, kg: Math.round(barrasInfo?.kg || 0), tramos: barrasInfo?.tramos || 0 });
  function zonasYEtiquetas(h, conjuntos, { llamadas = true } = {}) {
    const gi = giDe(h), e = L[gi].e, c = m3d.cajaProyecto(gi), t = tipoDespiece(e), B = [];
    const txt = `${e.refuerzo_texto || ''}`;
    const numTxt = (re) => { const m = txt.match(re); return m ? +m[1].replace(',', '.') : null; };
    const [x0, y0, z0, x1, y1, z1] = c;
    if (e.clase === 'IfcColumn' && t === 'vertical') {
      const lo = numTxt(/lo = ([\d,]+) m/), zs = sofito(gi);
      if (lo) { B.push({ min: [x0 - 0.03, y0 - 0.03, z0], max: [x1 + 0.03, y1 + 0.03, z0 + lo], color: '#2471a3' }); B.push({ min: [x0 - 0.03, y0 - 0.03, zs - lo], max: [x1 + 0.03, y1 + 0.03, zs], color: '#2471a3' }); }
      const p = P3(x1 + 0.1, y0, z0 + (lo || 0.6) / 2);
      if (lo) if (llamadas) etqRef(`<b>Zona confinada lo = ${n(lo)} m</b><br><small>abajo y arriba de la luz libre</small>`, p);
    } else if (e.clase === 'IfcPile') {
      for (const cj of conjuntos) for (const j of cj.juegos) if (j.param?.tramos) {
        const tr = [...j.param.tramos].sort((a, b) => b.z1 - a.z1)[0];
        B.push({ min: [x0 - 0.05, y0 - 0.05, tr.z0], max: [x1 + 0.05, y1 + 0.05, tr.z1], color: '#2471a3' });
        if (llamadas) etqRef(`<b>Cabeza confinada: ${n(tr.z1 - tr.z0)} m</b><br><small>espiral c/${n(tr.paso, 3)}</small>`, P3(x1 + 0.1, y0, (tr.z0 + tr.z1) / 2));
      }
      if (llamadas) etqRef(`<b>Punta a ${cota(z0)} m</b><br><small>pilote de ${n(z1 - z0)} m</small>`, P3(x1 + 0.1, y0, z0 + 0.3));
    } else if (t === 'viga') {
      const h2 = numTxt(/2h = ([\d,]+) m/), enX = x1 - x0 >= y1 - y0;
      if (h2) {
        B.push(enX ? { min: [x0, y0 - 0.03, z0 - 0.03], max: [x0 + h2, y1 + 0.03, z1 + 0.03], color: '#2471a3' } : { min: [x0 - 0.03, y0, z0 - 0.03], max: [x1 + 0.03, y0 + h2, z1 + 0.03], color: '#2471a3' });
        B.push(enX ? { min: [x1 - h2, y0 - 0.03, z0 - 0.03], max: [x1, y1 + 0.03, z1 + 0.03], color: '#2471a3' } : { min: [x0 - 0.03, y1 - h2, z0 - 0.03], max: [x1 + 0.03, y1, z1 + 0.03], color: '#2471a3' });
        if (llamadas) etqRef(`<b>2h = ${n(h2)} m</b><br><small>estribos cerrados en los extremos</small>`, P3(enX ? x0 + h2 / 2 : x1, enX ? y0 : y0 + h2 / 2, z0 - 0.15));
      }
    }
    // una llamada por grupo de barras (etiqueta del despiece), repartidas a lo largo del elemento para que no se encimen:
    // cada una señala el punto de su grupo más cercano a su lugar en el reparto
    const grupos = new Map(), max = !llamadas ? 0 : telefono() ? 2 : 6;
    // primero las longitudinales y los estribos (en el teléfono caben solo esas dos)
    const PRIO = { longitudinal: 0, transversal: 1, mallas: 2, bastones: 3, ganchos: 4 };
    const todos = conjuntos.flatMap((cj) => cj.juegos.map((j) => ({ j, cj }))).sort((a, b) => PRIO[familia(a.j.rol)] - PRIO[familia(b.j.rol)]);
    for (const { j, cj } of todos) {
      const k = `${familia(j.rol)}|${j.etiqueta}`;
      if (!grupos.has(k) && grupos.size < max) grupos.set(k, { j, pls: [] });
      if (grupos.has(k) && grupos.get(k).pls.length < 40) grupos.get(k).pls.push(...polilineas(j, cj.formas).slice(0, 8));
    }
    const eje = t === 'vertical' || (t === 'muro' && false) ? 2 : (x1 - x0 >= y1 - y0 ? 0 : 1), a0 = c[eje], a1 = c[eje + 3];
    [...grupos.values()].forEach((g, i, arr) => {
      const meta = a0 + ((i + 0.5) / arr.length) * (a1 - a0);
      // el punto más cercano sobre los tramos de las barras (no solo sus vértices: una barra corrida tiene los extremos lejos,
      // fuera del cuadro)
      let mejor = null, dm = Infinity;
      for (const pl of g.pls) {
        for (let k = 0; k < pl.length; k++) {
          const q0 = pl[k], q1 = pl[k + 1] || q0, L = q1[eje] - q0[eje];
          const t = Math.abs(L) < 1e-9 ? 0 : Math.min(1, Math.max(0, (meta - q0[eje]) / L));
          const q = [0, 1, 2].map((i) => q0[i] + t * (q1[i] - q0[i])), d = Math.abs(q[eje] - meta);
          if (d < dm - 1e-9) { dm = d; mejor = q; }
        }
      }
      // en el teléfono, la etiqueta corta («E N.º 4 c/0,15»; la dirección «(x)»/«(y)» se queda): la completa está en el despiece de la ficha
      const txt = telefono() ? g.j.etiqueta.replace(/ de \d+ ramas/, '').replace(/\s+(en lo|en 2h|en los|en la mitad|por nervio|cerca)\b.*$/, '').replace(/\s*\((?![xy]\))[^)]*\)$/, '') : g.j.etiqueta;
      if (mejor) etqRef(`<i class="bim-fam" style="background:${FAMILIAS.find((f) => f.id === familia(g.j.rol)).color}"></i>${esc(txt)}`, P3(mejor[0], mejor[1], mejor[2]));
    });
    if (B.length) { bandas = crearBandas(B, m3d.planos); grupo.add(bandas); }
  }
  // llamada: un ancla sin tamaño en el punto y la caja a su derecha, unida por una línea (no tapa la barra que señala)
  function etqRef(html, p) { const o = etq(`<span class="lbl-node bim-lbl bim-llamada">${html}</span>`, p, 'bim-ancla'); o.userData.bim = 'ref'; return o; }
  // fondo de las vigas que llegan a la cabeza de una columna (para la zona confinada de arriba)
  function sofito(gi) {
    const c = m3d.cajaProyecto(gi);
    let zs = c[5];
    L.forEach((x, k) => {
      if (x.e.clase !== 'IfcBeam') return;
      const b = m3d.cajaProyecto(k);
      if (Math.abs(b[5] - c[5]) < 0.02 && b[0] <= c[3] + 0.05 && b[3] >= c[0] - 0.05 && b[1] <= c[4] + 0.05 && b[4] >= c[1] - 0.05) zs = Math.min(zs, b[2]);
    });
    return zs;
  }
  function pintarDespiece() {
    const caja = $(elFicha, '[data-b="despiece"]');
    if (!caja || !S.refuerzo || S.refuerzo.hosts.length !== 1) return;
    const h = S.refuerzo.hosts[0], gi = giDe(h), e = L[gi].e, cj = S.refuerzo.conjuntos.find((c) => c.host === h && c.tono !== 'apagado');
    if (!cj) { caja.innerHTML = ''; return; }
    const partes = gisDe(gi), sols = partes.flatMap((q) => solidosDe(L[q].e.geometria));
    const c0 = partes.map((q) => m3d.cajaProyecto(q)).reduce((a, b) => [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.min(a[2], b[2]), Math.max(a[3], b[3]), Math.max(a[4], b[4]), Math.max(a[5], b[5])]);
    let tramo = null;
    if (tipoDespiece(e) === 'escalera') {
      const f = partes.map((q) => L[q].e).find((p) => p.clase === 'IfcStairFlight' && p.geometria?.tipo === 'perfil');
      if (f) { const g = f.geometria, cb = m3d.cajaProyecto(giDe(f.id)); tramo = { u: g.u, centro: [(cb[0] + cb[3]) / 2, (cb[1] + cb[4]) / 2], ancho: Math.abs(g.u[1]) > 0.9 ? cb[3] - cb[0] : cb[4] - cb[1] }; }
    }
    const ancho = Math.max(260, Math.min(560, (caja.clientWidth || elFicha.clientWidth || 320) - 4));
    // en una columna, las longitudinales de la de abajo y la de arriba (en gris) para ver los traslapos también en 2D
    const contexto = S.refuerzo.conjuntos.filter((c) => c.tono === 'apagado');
    caja.innerHTML = `<h5>Despiece del elemento <span class="bim-tipo">(esquema a escala; cálculo propio con el despiece del prediseño)</span></h5>${despiece(e, { caja: c0, sols, juegos: cj.juegos, formas: cj.formas, opc: { zSofito: e.clase === 'IfcColumn' ? sofito(gi) : null, tramo, contexto, notaDibujo: notaParrillas(e) }, ancho })}`;
  }
  // parrillas de un dado: lo dibujado frente al prediseño (las barras que caben en el ancho útil y su área de acero)
  function notaParrillas(e) {
    const P = e.parrillas_dibujadas;
    if (!P) return '';
    return Object.entries(P).sort().map(([k, q]) => {
      const eje = k.slice(-1), falta = q.As_req_mm2 ? 100 * (1 - q.As_dibujada_mm2 / q.As_req_mm2) : 0;
      const sep = Math.abs(q.s_dibujada_m - q.s_A_m) > 5e-4 ? `el prediseño pide N.º ${q.num} c/${n(q.s_A_m, 3)}${q.n_A ? ` (${q.n_A} barras)` : ''}; en el ancho útil entre las patas de la otra dirección caben ${q.n_dibujadas} y el dibujo las reparte a ${n(q.s_dibujada_m, 3)} m` : `${q.n_dibujadas} N.º ${q.num} c/${n(q.s_A_m, 3)}`;
      return `Parrilla inferior en ${eje}: ${sep}; ${n0(q.As_dibujada_mm2)} mm² frente a ${n0(q.As_req_mm2)} mm² requeridos${falta > 0.05 ? ` (faltan ${n(falta, 1)} %: lo revisa el prediseño)` : ''}.`;
    }).join(' ');
  }
  function leyendaRefuerzo() {
    ley(`<p class="bim-ley-t">Refuerzo (acero de 420 MPa)</p><ul class="bim-ley-l">${FAMILIAS.map((f) => `<li><i style="background:${f.color}"></i>${f.nombre}</li>`).join('')}<li><i class="bim-zona"></i>Zonas: confinamiento, 2h y cabeza del pilote</li>${S.refuerzo?.conjuntos.some((c) => c.tono === 'apagado') ? '<li><i style="background:#9a9a95"></i>Barras de la columna de abajo y de arriba (traslapos)</li>' : ''}${S.refuerzo?.resaltar?.size ? '<li><i style="background:#e02ad8"></i>Barras del hallazgo</li>' : ''}</ul><p class="bim-ley-n">Concreto transparente. Diámetros reales.</p>`);
  }
  // ejes y su refuerzo: los elementos con refuerzo cuyo eje cae sobre la línea (columnas, vigas, muros, dados, pilotes…)
  function hostsDelEje(eje, nivel) {
    const ex = IDX.ejes?.x?.find((q) => q.id === eje), ey = IDX.ejes?.y?.find((q) => q.id === eje);
    if (!ex && !ey) return [];
    const enX = !!ex, c = ex ? ex.x : ey.y, niveles = nivel === 'CIM' ? ['CIM', 'CIM-PIL'] : [nivel];
    const dados = new Set(), out = [];
    L.forEach((x, gi) => {
      const e = x.e;
      if (!e.refuerzo || !niveles.includes(x.nivel) || e.clase === 'IfcSlab' || e.clase === 'IfcStair' || e.clase === 'IfcElementAssembly' || e.clase === 'IfcPile') return;
      const b = m3d.cajaProyecto(gi), a0 = enX ? b[0] : b[1], a1 = enX ? b[3] : b[4], l0 = enX ? b[4] - b[1] : b[3] - b[0], t0 = a1 - a0;
      if (!(a0 - 0.05 <= c && a1 + 0.05 >= c)) return;
      // los elementos alargados deben ir a lo largo del eje (no atravesarlo)
      if ((e.clase === 'IfcBeam' || e.tipo_predefinido === 'FOOTING_BEAM' || e.clase === 'IfcWall') && l0 < t0) return;
      out.push(e.id);
      if (e.tipo_predefinido === 'PILE_CAP') dados.add(e.id);
    });
    if (niveles.includes('CIM-PIL')) L.forEach((x) => { if (x.e.clase === 'IfcPile' && dados.has(x.e.grupo)) out.push(x.e.id); });
    return out;
  }
  async function refuerzoEje(eje, nivel) {
    const hs = hostsDelEje(eje, nivel);
    if (!hs.length) { estado(`El eje ${eje} no tiene elementos con refuerzo en ${NIVEL_CORTO[nivel] || nivel}.`); return null; }
    estado(`Refuerzo del eje ${eje} en ${NIVEL_CORTO[nivel] || nivel}: ${hs.length} elementos. Toca una barra para ver su juego, o un elemento para su ficha.`);
    seleccionar(-1);
    const ex = IDX.ejes.x.find((q) => q.id === eje);
    return verRefuerzo(hs, { eje: { eje, nivel }, dir: ex ? new THREE.Vector3(-1, 0.32, 0.12) : new THREE.Vector3(0.12, 0.32, 1) });
  }
  function salirRefuerzo() {
    limpiarRefuerzo();
    if (S.terreno !== 'opaco') { S.terreno = 'opaco'; terreno.poner('opaco'); }
    if (S.vista === 'refuerzo') S.vista = 'modelo';
    if (S.corte?.elemento) quitarCorte();
    aplicar(); ley(null); chip(null); accionesHud(); pintarPestRefuerzo();
    if (S.sel >= 0) fichaElemento();
  }

  // ================================================================ cortes
  function dirCorte(cfg) {
    if (cfg.tipo === 'h') return new THREE.Vector3(-0.32, 0.9, 0.42);
    if (cfg.tipo === 'x') return new THREE.Vector3(cfg.lado < 0 ? 1 : -1, 0.3, 0.14);
    return new THREE.Vector3(0.14, 0.3, cfg.lado < 0 ? -1 : 1);
  }
  function cortar(cfg, { conTapa = null, volar = true, titulo = '' } = {}) {
    if (!m3d) return;
    if (cfg && !cfg.elemento) {
      dejarCimentacion();
      if (S.refuerzo) { S.aislados = null; limpiarRefuerzo(); S.vista = 'modelo'; if (S.terreno !== 'opaco') { S.terreno = 'opaco'; terreno.poner('opaco'); } ley(null); if (S.sel >= 0) fichaElemento(); pintarPestRefuerzo(); }
      aplicar();   // la visibilidad de la vista que queda, antes de calcular la tapa
    }
    S.corte = cfg;
    m3d.cortar(cfg, conTapa);
    ref3d?.cortar(S.refuerzo ? cfg : null);
    st.invalidate(true);
    if (cfg && volar) {
      const caja = cajaTotal.clone();
      if (cfg.tipo === 'h') { caja.max.y = Math.min(caja.max.y, cfg.c + 0.5); caja.min.y = Math.max(caja.min.y, cfg.c - 4.5); }
      encuadrar(caja, { margen: 0.8, dir: dirCorte(cfg) });
    }
    chip(cfg ? titulo || chipCorte(cfg) : null);
    accionesHud();
    pintarPestCortes();
  }
  const chipCorte = (c) => (c.tipo === 'h' ? `Corte horizontal a la cota ${cota(c.c)} m` : `Corte vertical por el eje ${c.eje || ''}`);
  function cortarNivel(id) {
    const c = CORTES_NIVEL.find((q) => q[0] === id);
    if (!c) return;
    cortar({ tipo: 'h', c: c[1], nivel: id }, { titulo: `Corte horizontal: ${c[2]} (cota ${cota(c[1])} m)` });
  }
  function cortarEje(id, lado = 1) {
    const ex = IDX.ejes?.x?.find((q) => q.id === id), ey = IDX.ejes?.y?.find((q) => q.id === id);
    if (!ex && !ey) return;
    cortar(ex ? { tipo: 'x', c: ex.x + 0.001, lado, eje: id } : { tipo: 'y', c: ey.y + 0.001, lado, eje: id }, { titulo: `Corte vertical por el eje ${id}` });
  }
  function quitarCorte() { cortar(null); }
  // vista de corte de un elemento: el elemento solo (y su refuerzo), cortado por su sección
  async function corteElemento(id) {
    const gi = giDe(id);
    if (gi == null) return null;
    const e = el(gi), b = m3d.cajaProyecto(gi), t = tipoDespiece(e), enX = b[3] - b[0] >= b[4] - b[1];
    const cfg = t === 'vertical' ? { tipo: 'h', c: e.clase === 'IfcPile' ? b[5] - 1.0 : b[2] + 0.3 * (b[5] - b[2]) }
      : t === 'viga' ? (enX ? { tipo: 'x', c: b[0] + 0.37 * (b[3] - b[0]), lado: 1 } : { tipo: 'y', c: b[1] + 0.37 * (b[4] - b[1]), lado: 1 })
        : t === 'muro' ? { tipo: 'h', c: b[2] + 0.4 * (b[5] - b[2]) } : { tipo: 'y', c: (b[1] + b[4]) / 2 + 0.013, lado: 1 };
    cfg.elemento = id;
    S.aislados = new Set(gisDe(gi));
    const h = hostDe(gi);
    if (h) await verRefuerzo(h, { conCorte: cfg });
    else { aplicar(); cortar(cfg, { volar: false }); }
    // la cámara mira la cara cortada: se encuadra solo la parte que queda del elemento
    const caja = m3d.caja([...S.aislados]).expandByScalar(0.35);
    if (cfg.tipo === 'h') caja.max.y = cfg.c + 0.05;
    else if (cfg.tipo === 'x') caja.min.x = cfg.c - 0.05;
    else caja.max.z = -cfg.c + 0.05;
    encuadrar(caja, { margen: 0.85, dir: dirCorte(cfg) });
    chip(`Vista de corte: ${e.nombre}`);
    return { corte: cfg, ...resumenRef() };
  }

  // ================================================================ cimentación
  // en la cimentación, el contrapiso y las tapas de las cisternas se ven transparentes: tapaban los dados y los pilotes
  let fantCim = null;
  function quitarFantCim() { if (fantCim) { grupo.remove(fantCim); fantCim.userData.dispose(); fantCim = null; } }
  function cimentacion(on = true, terr = 'cortado') {
    if (!m3d) return;
    quitarFantCim();
    if (!on) { dejarCimentacion(); terreno.poner('opaco'); S.terreno = 'opaco'; aplicar(); return; }
    exclusivo('cimentacion');
    S.vista = 'cimentacion';
    S.terreno = terr; terreno.poner(terr);
    const velo = L.map((x, i) => i).filter((i) => L[i].e.disciplina === 'CIM' && L[i].e.clase === 'IfcSlab' && /BASESLAB|ROOF/.test(L[i].e.tipo_predefinido || ''));
    S.velo = new Set(velo);
    fantCim = m3d.fantasma(velo, { opacidad: 0.22 }); grupo.add(fantCim);
    aplicar();
    etiquetasCimentacion();
    const cim = L.map((x, i) => i).filter((i) => L[i].e.disciplina === 'CIM');
    encuadrar(m3d.caja(cim), { margen: 0.8, dir: new THREE.Vector3(-0.7, 0.36, 0.62) });
    chip('Cimentación: pilotes, dados, vigas de amarre, contrapiso, fosos y cisternas');
    ley(`<p class="bim-ley-t">Cimentación (prediseño)</p><ul class="bim-ley-l"><li><i style="background:#8c8174"></i>Pilotes preexcavados</li><li><i style="background:#9a9184"></i>Dados, losas de pilotes y vigas de amarre</li><li><i style="background:#c9c4b9"></i>Contrapiso y losas</li><li><i style="background:#a0988b"></i>Fosos y cisternas</li><li><i style="background:#9c7b55"></i>Suelo (excavación de muestra)</li></ul><p class="bim-ley-n">Cotas en metros desde el piso 1 (±0,00). Capacidades: estimación hasta el estudio geotécnico.</p>`);
    pintarPestCimentacion();
  }
  function etiquetasCimentacion() {
    quitarEtiquetas((o) => o.userData.bim === 'cim');
    const add = (html, p) => { const o = etq(html, p, 'lbl-node bim-lbl'); o.userData.bim = 'cim'; };
    const tel = telefono();
    const pilotes = L.filter((x) => x.e.clase === 'IfcPile'), dados = L.filter((x) => x.e.tipo_predefinido === 'PILE_CAP');
    // el dado más cargado y uno de sus pilotes; la viga de amarre, el contrapiso, el foso y las cisternas
    const carga = (x) => Object.values(x.e.analisis?.cargas_servicio_kN || {}).reduce((s, c) => s + (c.D_kN || 0) + (c.L_kN || 0), 0);
    const dmax = [...dados].filter((x) => /^D-/.test(x.e.id)).sort((a, b) => carga(b) - carga(a))[0];
    if (dmax) {
      const b = m3d.cajaProyecto(giDe(dmax.e.id)), q = dmax.e.qto?.Qto_FootingBaseQuantities || {};
      add(`<b>Dado ${esc(dmax.e.id)}: ${n(q.Length)} × ${n(q.Width)} × ${n(q.Height)} m</b><br><small>${esc((dmax.e.nombre.match(/con (\d+) pilotes/) || [])[0] || '')} · carga de servicio ${n0(carga(dmax))} kN (D + L, cálculo propio)</small>`, P3((b[0] + b[3]) / 2, b[1], b[5]));
      const pil = pilotes.find((x) => x.e.grupo === dmax.e.id) || pilotes[0];
      if (pil) {
        const g = pil.e.geometria, an = pil.e.analisis || {};
        add(`<b>Pilote Ø ${n(2 * g.radio)} m × ${n(g.z1 - g.z0)} m</b><br><small>punta a ${cota(g.z0)} m · reacción con sismo hasta ${n0(an.reaccion_max_kN?.sismo)} kN; capacidad con sismo ${n0(an.capacidad_kN?.Qsismo)} kN (estimación)</small>`, P3(g.centro[0], g.centro[1], g.z0));
      }
    }
    // regla de cotas en la esquina suroccidental de la cimentación
    const cim = L.map((x, i) => i).filter((i) => L[i].e.disciplina === 'CIM'), bb = m3d.caja(cim);
    const xr = bb.min.x - 1.2, yr = -bb.max.z - 1.2, zp = Math.min(...pilotes.map((x) => x.e.geometria.z0));
    add(`<b>±0,00</b> piso 1`, P3(xr, yr, 0));
    add(`<b>${cota(zp)} m</b> punta de los pilotes`, P3(xr, yr, zp));
    if (!tel) {
      add(`<b>−1,00 m</b> nivel freático estimado`, P3(xr, yr, -1.0));
      const vc = L.find((x) => x.e.tipo_predefinido === 'FOOTING_BEAM');
      if (vc) { const b = m3d.cajaProyecto(giDe(vc.e.id)); add(`<b>Viga de amarre ${n(vc.e.qto?.Qto_FootingBaseQuantities?.Width)} × ${n(vc.e.qto?.Qto_FootingBaseQuantities?.Height)} m</b><br><small>${esc((vc.e.analisis?.une || []).join(' con '))}; NSR-10 C.15.13</small>`, P3((b[0] + b[3]) / 2, (b[1] + b[4]) / 2, b[5])); }
      for (const x of L.filter((q) => q.e.clase === 'IfcElementAssembly' && !/montacargas/i.test(q.e.nombre))) {
        const b = m3d.caja(gisDe(giDe(x.e.id)));
        add(`<b>${esc(x.e.nombre)}</b>`, new THREE.Vector3((b.min.x + b.max.x) / 2, b.max.y + 0.3, (b.min.z + b.max.z) / 2));
      }
    }
    // la regla misma: una línea con marcas
    const pts = [P3(xr, yr, 0), P3(xr, yr, zp)];
    for (const z of [0, -1, -1.5, -5, -10, -15, zp]) pts.push(P3(xr - 0.25, yr, z), P3(xr + 0.25, yr, z));
    const g = new THREE.BufferGeometry().setFromPoints(pts), lr = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: '#f4f1ea', depthTest: false, transparent: true }));
    lr.name = 'bim_regla'; lr.userData.bim = 'cim'; lr.renderOrder = 6;
    reglaCim?.removeFromParent(); reglaCim?.geometry.dispose(); reglaCim = lr; gEtq.add(lr);
  }
  let reglaCim = null;
  // las vistas de cimentación, refuerzo, comportamiento, 5D, 4D e interferencia se excluyen: al entrar a una se sale de las
  // otras (los cortes por nivel o eje se pueden combinar con el modelo, el 5D, el 4D y el comportamiento)
  function exclusivo(n) {
    if (n !== 'cimentacion') dejarCimentacion();
    if (n !== 'refuerzo' && S.refuerzo) {
      S.aislados = null; limpiarRefuerzo();
      if (S.corte?.elemento) quitarCorte();
      if (S.terreno !== 'opaco') { S.terreno = 'opaco'; terreno.poner('opaco'); }
      if (S.vista === 'refuerzo') S.vista = 'modelo';
      ley(null); pintarPestRefuerzo();
    }
    if (n !== 'comportamiento' && n !== '5d' && (S.colores || S.color5d)) quitarComportamiento(false);
    if (n !== '4d' && S.fecha != null) { pararPlay(); S.fecha = null; S.avance = null; $(elHud, '[data-b="barra4d"]').hidden = true; }
    if (n !== 'int') {
      marcaInt?.removeFromParent(); quitarEtiquetas((o) => o.userData.bim === 'int');
      if (fantInt) { quitarFantInt(); S.aislados = null; if (S.terreno !== 'opaco' && n !== 'cimentacion') { S.terreno = 'opaco'; terreno.poner('opaco'); } }
    }
  }
  function dejarCimentacion() {
    if (S.vista !== 'cimentacion') return;
    quitarFantCim(); S.velo = null; S.vista = 'modelo';
    quitarEtiquetas((o) => o.userData.bim === 'cim');
    reglaCim?.removeFromParent(); reglaCim?.geometry.dispose(); reglaCim = null;
    if (S.terreno !== 'opaco') { S.terreno = 'opaco'; terreno.poner('opaco'); }
    ley(null); chip(null);
  }

  // ================================================================ comportamiento: colores del último cálculo del simulador
  let rotulas = null;
  async function comportamiento(campo = 'dc', { volar = true } = {}) {
    if (!m3d) await cargado;
    const res = ctx.sismo?.ultimo?.() || null, R = res?.resultados;
    exclusivo('comportamiento');
    quitarComportamiento(false);
    if (!R) { pintarPestComportamiento(); return { ok: false, motivo: 'sin_calculo' }; }
    const estr = await leer('sismo_torre_estructura.json');
    if (!estr) { estado('No se pudo leer el modelo estructural del simulador.'); return { ok: false, motivo: 'sin_estructura' }; }
    const ids = [], xyz = new Map(), niveles = [];
    for (const b of estr.bloques || []) {
      (b.niveles || []).forEach((q) => niveles.push(q));
      for (const p of b.porticos || []) { for (const q of p.nodos || []) xyz.set(q.id, q.xyz); for (const e of p.elementos || []) ids.push(e); }
    }
    if (ids.length !== res.nE) { estado('El último cálculo usó otro modelo estructural: vuelve a calcular en el simulador.'); return { ok: false, motivo: 'otro_modelo' }; }
    const { paletaDC, binDC, CORTES_DC } = await import('./estructura3d.js');
    const k = new Map(ids.map((e, i) => [e.id, i])), E = R.envolventes, nE = ids.length, nt = R.t.length;
    const pal = paletaDC(tokens()), gris = new THREE.Color('#d6d6d2');
    const porGi = new Map();
    // rótulas: el O lógico de todos los pasos (bits del 7.6)
    const bits = new Uint8Array(nE);
    for (let i = 0; i < nt; i++) for (let q = 0; q < nE; q++) bits[q] |= R.rotulas[i * nE + q];
    let conColor = 0;
    m3d.E.sinColor();
    L.forEach((x, gi) => {
      const e = x.e;
      if (e.disciplina !== 'EST' && e.disciplina !== 'CIM') return;
      const ks = (e.analisis?.elementos || []).map((id) => k.get(id)).filter((q) => q != null);
      if (!ks.length) { m3d.E.colorSRGB(gi, gris, 230); return; }
      const vs = ks.map((q) => E.dc_max[q]);
      const v = vs.length === 2 && e.clase === 'IfcColumn' ? (vs[0] ** 1.5 + vs[1] ** 1.5) ** (1 / 1.5) : Math.max(...vs);
      const fluyo = ks.some((q) => bits[q] & 3);
      porGi.set(gi, v);
      m3d.E.colorSRGB(gi, campo === 'rotulas' ? (fluyo ? pal[3] : gris) : pal[binDC(v)], 255);
      conColor++;
    });
    // esferas en los extremos que fluyeron (tamaño fijo; color por el nivel de desempeño superado)
    const marcas = [];
    ids.forEach((e, q) => {
      for (const [bit, extremo, io, ls] of [[1, 0, 4, 16], [2, 1, 8, 32]]) {
        if (!(bits[q] & bit)) continue;
        const a = xyz.get(e.i), b = xyz.get(e.j);
        if (!a || !b) continue;
        const s = extremo ? 0.9 : 0.1, p = [a[0] + s * (b[0] - a[0]), a[1] + s * (b[1] - a[1]), a[2] + s * (b[2] - a[2])];
        marcas.push({ p, nivel: bits[q] & 64 ? 3 : bits[q] & ls ? 2 : bits[q] & io ? 1 : 0 });
      }
    });
    if (marcas.length) {
      const geo = new THREE.SphereGeometry(0.22, 12, 8), mat = new THREE.MeshBasicMaterial({ depthTest: true });
      rotulas = new THREE.InstancedMesh(geo, mat, marcas.length); rotulas.name = 'bim_rotulas';
      const m = new THREE.Matrix4(), cc = [new THREE.Color('#1d1d1b'), tokens().warn, tokens().bad, new THREE.Color('#7a0010')];
      marcas.forEach((r, i) => { m.makeTranslation(r.p[0], r.p[2], -r.p[1]); rotulas.setMatrixAt(i, m); rotulas.setColorAt(i, cc[r.nivel]); });
      rotulas.renderOrder = 6; grupo.add(rotulas);
    }
    // deriva por entrepiso (vectorial, en el vértice donde ocurre)
    const lim = estr.limites?.deriva ?? 0.01, der = E.deriva_vector_max ? [...E.deriva_vector_max] : [];
    quitarEtiquetas((o) => o.userData.bim === 'sis');
    der.forEach((d, i) => {
      const nv = niveles[i], pt = E.punto_deriva_vector ? [E.punto_deriva_vector[2 * i], E.punto_deriva_vector[2 * i + 1]] : nv?.cm;
      if (!nv || !pt) return;
      const o = etq(`<b>Entrepiso ${i + 1}: deriva ${n(100 * d, 2)} %</b><br><small>límite NSR-10: ${n(100 * lim, 1)} % (${n((100 * d) / lim, 0)} % del límite)</small>`, P3(pt[0], pt[1], nv.z), 'lbl-node bim-lbl');
      o.userData.bim = 'sis';
    });
    const top = [...porGi.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8);
    S.colores = { campo, porGi, res, rotulas: marcas.length, deriva: der, lim, top, conColor, CORTES_DC };
    S.vista = 'comportamiento';
    limpiarRefuerzo();
    aplicar();
    leyendaComportamiento(pal, CORTES_DC);
    const disenio = res.opciones?.escala === 'nsr10' ? ', escalado al sismo de diseño' : '';
    chip(`Último cálculo del simulador: Mw ${n(res.params?.Mw, 1)} a ${n0(res.params?.distancia_epicentral_km)} km${disenio} (${campo === 'rotulas' ? 'rótulas' : 'demanda/capacidad'})`);
    if (volar) encuadrar(m3d.caja(L.map((x, i) => i).filter((i) => L[i].e.disciplina === 'EST')).expandByScalar(1), { margen: 0.8 });
    pintarPestComportamiento();
    if (S.sel >= 0) fichaElemento();
    return { ok: true, coloreados: conColor, rotulas: marcas.length, dc_max: top[0]?.[1] ?? null, deriva_max: der.length ? Math.max(...der) : null };
  }
  function quitarComportamiento(repintar = true) {
    if (rotulas) { grupo.remove(rotulas); rotulas.geometry.dispose(); rotulas.material.dispose(); rotulas = null; }
    quitarEtiquetas((o) => o.userData.bim === 'sis');
    if (S.colores || S.color5d) m3d?.E.sinColor();
    S.colores = null; S.color5d = null;
    if (S.vista === 'comportamiento') S.vista = 'modelo';
    if (repintar) { aplicar(); ley(null); chip(null); pintarPestComportamiento(); }
  }
  function leyendaComportamiento(pal, C) {
    const hex = (c) => `#${c.getHexString()}`;
    const bins = [`≤ ${n(C[0], 1)}`, `${n(C[0], 1)} a ${n(C[1], 1)}`, `${n(C[1], 1)} a ${n(C[2], 1)}`, `> ${n(C[2], 1)}`];
    ley(`<p class="bim-ley-t">${S.colores?.campo === 'rotulas' ? 'Elementos con rótulas' : 'Demanda / capacidad máxima del sismo'}</p><ul class="bim-ley-l">${S.colores?.campo === 'rotulas' ? `<li><i style="background:${hex(pal[3])}"></i>fluyó en algún extremo</li>` : pal.map((c, i) => `<li><i style="background:${hex(c)}"></i>${bins[i]}</li>`).join('')}<li><i style="background:#d6d6d2"></i>sin análisis (losas y cimentación)</li><li><i class="bim-esfera"></i>rótula (negra: fluencia; naranja y roja: pasó los límites de desempeño)</li></ul><p class="bim-ley-n">Cálculo propio del simulador. En columnas, D/C combina sus dos direcciones (Bresler, α = 1,5; estimación).</p>`);
  }

  // ================================================================ 5D: color por capítulo del presupuesto
  const PAL5D = ['#8c6d4f', '#7d8a96', '#c46a3a', '#5b8fc7', '#b9a04a', '#7a5ea7', '#3f8f6b', '#c94f6d', '#4fa3a5', '#9c6b3f', '#6c7a3a', '#a14646', '#2f6db3', '#e3a91c'];
  function color5D(on = true) {
    if (!m3d) return null;
    exclusivo('5d');
    quitarComportamiento(false);
    if (!on) { S.color5d = null; aplicar(); ley(null); chip(null); return null; }
    const caps = new Map();
    L.forEach((x, gi) => {
      const it = x.e.costo?.find((c) => c.valor);
      if (!it) return;
      const cap = String(it.item).includes('.') ? String(it.item).split('.')[0] : String(it.item);
      if (!caps.has(cap)) caps.set(cap, { valor: 0, gis: [] });
      const c = caps.get(cap); c.valor += +it.valor || 0; c.gis.push(gi);
    });
    const orden = [...caps.entries()].sort((a, b) => b[1].valor - a[1].valor), col = new THREE.Color();
    m3d.E.sinColor();
    orden.forEach(([, c], i) => { col.set(PAL5D[i % PAL5D.length]); c.gis.forEach((gi) => m3d.E.colorSRGB(gi, col, 255)); });
    S.color5d = orden;
    aplicar();
    const nombre = (k) => esc(nombreCapitulo(k));
    ley(`<p class="bim-ley-t">Capítulo del presupuesto (valor del modelo)</p><ul class="bim-ley-l">${orden.slice(0, 12).map(([k, c], i) => `<li><i style="background:${PAL5D[i % PAL5D.length]}"></i>${/^\d+$/.test(k) ? `${k}. ` : ''}${nombre(k)}: ${millones(c.valor)}</li>`).join('')}</ul><p class="bim-ley-n">Cantidad del modelo × valor unitario del presupuesto (cálculo propio; precios estimados de 2026). El acero de refuerzo va aparte.</p>`);
    chip('Modelo coloreado por capítulo del presupuesto (5D)');
    return orden.length;
  }

  // ================================================================ 4D
  const F4 = [...fases.values()].sort((a, b) => a.inicio.localeCompare(b.inicio));
  const t0_4d = F4.length ? Date.parse(`${F4[0].inicio}T00:00:00`) : 0, t1_4d = F4.length ? Math.max(...F4.map((f) => Date.parse(`${f.fin}T23:59:59`))) : 0;
  let reproduciendo = null;
  function fecha4D(t) {
    if (t != null) exclusivo('4d');
    if (t == null) { S.fecha = null; aplicar(); $(elHud, '[data-b="barra4d"]').hidden = true; chip(null); return null; }
    S.fecha = Math.max(t0_4d, Math.min(t1_4d, t));
    aplicar();
    const r = $(elHud, '[data-b="r4d"]'); r.value = String(Math.round((1000 * (S.fecha - t0_4d)) / (t1_4d - t0_4d || 1)));
    r.max = '1000';
    const enObra = F4.filter((f) => Date.parse(`${f.inicio}T00:00:00`) <= S.fecha && Date.parse(`${f.fin}T23:59:59`) >= S.fecha);
    const d = new Date(S.fecha).toISOString().slice(0, 10);
    // avance: valor de los elementos terminados y la parte proporcional de los que están en obra
    let tot = 0, hecho = 0;
    L.forEach((x) => {
      const f = fases.get(x.e.fase), v = (x.e.costo || []).reduce((s, c) => s + (+c.valor || 0), 0);
      if (!f || !v) return;
      tot += v;
      const a = Date.parse(`${f.inicio}T00:00:00`), b = Date.parse(`${f.fin}T23:59:59`);
      hecho += v * Math.max(0, Math.min(1, (S.fecha - a) / (b - a || 1)));
    });
    $(elHud, '[data-b="t4d"]').textContent = `${fechaTxt(d)} · ${enObra.length ? enObra.map((f) => f.nombre.split(':')[0]).slice(0, 2).join(' · ') : 'sin frentes de obra'} · avance ${n((100 * hecho) / (tot || 1), 0)} %`;
    S.avance = { fecha: d, enObra: enObra.map((f) => f.id), pct: (100 * hecho) / (tot || 1), hecho, tot };
    $(elHud, '[data-b="barra4d"]').hidden = false;
    pintarPest4D();
    return S.avance;
  }
  $(elHud, '[data-b="r4d"]').addEventListener('input', (e) => { pararPlay(); fecha4D(t0_4d + ((+e.target.value) / 1000) * (t1_4d - t0_4d)); });
  $(elHud, '[data-b="play4d"]').addEventListener('click', () => { if (reproduciendo) { pararPlay(); return; } play4D(); });
  function play4D() {
    if (reducedMotion) { fecha4D(t1_4d); return; }
    let t = S.fecha == null || S.fecha >= t1_4d ? t0_4d : S.fecha, prev = performance.now();
    const paso = (now) => {
      t += ((now - prev) / 1000) * ((t1_4d - t0_4d) / 14); prev = now;
      fecha4D(Math.min(t, t1_4d));
      if (t < t1_4d && reproduciendo) reproduciendo = requestAnimationFrame(paso); else pararPlay();
    };
    reproduciendo = requestAnimationFrame(paso);
    $(elHud, '[data-b="play4d"]').textContent = 'Pausa';
  }
  function pararPlay() { if (reproduciendo) cancelAnimationFrame(reproduciendo); reproduciendo = null; $(elHud, '[data-b="play4d"]').textContent = 'Construir'; }

  // ================================================================ interferencias
  let INT = null, marcaInt = null, fantInt = null;
  const RESP = { A: 'prediseño estructural', B: 'arquitectura y dotación', F: 'modelo BIM' };
  const responsable = (r) => String(r || '').split(/\s+y\s+/).map((q) => RESP[q.trim()] || q).join(' y ');
  function quitarFantInt() { if (fantInt) { grupo.remove(fantInt); fantInt.userData.dispose(); fantInt = null; } }
  async function interferencias() { INT ??= await leer('torre_bim_interferencias.json'); return INT; }
  async function irAInterferencia(id) {
    const I = await interferencias();
    const x = I?.interferencias.find((q) => q.id === id);
    if (!x || !m3d) return null;
    exclusivo('int');
    marcaInt?.removeFromParent();
    const p = x.posicion ? P3(...x.posicion) : null;
    const gis = (x.elementos || []).map(giDe).filter((q) => q != null);
    const hostsB = [...new Set((x.barras || []).map((b) => b.match(/^R-(.+)-\d+$/)?.[1]).filter(Boolean))];
    quitarFantInt();
    if (hostsB.length) await verRefuerzo(hostsB.slice(0, 3), { resaltar: new Set(x.barras), volar: false });
    else if (gis.length) {
      // los elementos del hallazgo solos y, alrededor (a 3 m), la estructura y los muros en transparente para ubicarse
      S.vista = 'modelo';
      S.aislados = new Set(gis.flatMap(gisDe));
      const c = x.posicion || [0, 0, 0], cerca = [];
      L.forEach((q, gi) => { if (S.aislados.has(gi) || /IfcSpace|IfcCovering/.test(q.e.clase)) return; const b = m3d.cajaProyecto(gi); if (b[0] <= c[0] + 3 && b[3] >= c[0] - 3 && b[1] <= c[1] + 3 && b[4] >= c[1] - 3 && b[2] <= c[2] + 2 && b[5] >= c[2] - 2) cerca.push(gi); });
      fantInt = m3d.fantasma(cerca.slice(0, 400), { opacidad: 0.1 }); grupo.add(fantInt);
      if (c[2] < -0.05) { S.terreno = 'semi'; terreno.poner('semi'); }
      aplicar();
    }
    if (gis.length) seleccionar(gis[0], { ficha: true });
    if (p) {
      marcaInt = new THREE.Mesh(new THREE.SphereGeometry(0.12, 16, 10), new THREE.MeshBasicMaterial({ color: tokens().accent, depthTest: false, transparent: true, opacity: 0.9 }));
      marcaInt.position.copy(p); marcaInt.renderOrder = 9; marcaInt.name = 'bim_marca'; grupo.add(marcaInt);
      quitarEtiquetas((o) => o.userData.bim === 'int');
      const o = etq(`<b>${esc(x.id)} · ${esc(x.categoria)}</b><br><small>${esc(x.severidad)} · a cargo de: ${esc(responsable(x.responsable))}</small>`, p, 'lbl-node bim-lbl'); o.userData.bim = 'int';
      const caja = new THREE.Box3().setFromCenterAndSize(p, new THREE.Vector3(3.2, 3.2, 3.2));
      if (gis.length) caja.union(m3d.caja(gis.slice(0, 2)));
      encuadrar(caja, { margen: 0.7 });
    }
    chip(`Interferencia ${x.id}: ${x.categoria}`);
    return { id: x.id, elementos: gis.length, barras: (x.barras || []).length };
  }

  // ================================================================ árbol, buscador y disciplinas
  // LOD: el objetivo del plan BIM y, aparte, lo que el modelo es hoy (con sus interferencias duras pendientes)
  const lodTxt = (d) => { const q = IDX.disciplinas?.[d]; return q?.lod_objetivo ? `<br><span class="bim-lod">LOD objetivo (plan BIM): ${esc(q.lod_objetivo)} · hoy: ${esc(q.estado_actual || '')}</span>` : ''; };
  function loinTabla() {
    const ds = [...DISCIPLINAS, 'REF'].filter((d) => IDX.disciplinas?.[d]?.loin);
    if (!ds.length) return '';
    const lista = (xs, k) => `<ul class="tight">${xs.map((q) => `<li>${esc(q[k])} <span class="bim-tipo">(${esc(q.tipo_dato)})</span></li>`).join('')}</ul>`;
    return `<details class="fold bim-loin"><summary>Nivel de información necesario (LOIN) por disciplina</summary>${IDX.nota_lod ? `<p class="note">${esc(IDX.nota_lod)}</p>` : ''}${ds.map((d) => { const L_ = IDX.disciplinas[d].loin; return `<h5>${NOM_DISC[d]}</h5><dl class="kv"><dt>Geometría</dt><dd>${esc(L_.geometria.detalle)} <span class="bim-tipo">(${esc(L_.geometria.tipo_dato)})</span></dd><dt>Información</dt><dd>${lista(L_.informacion, 'dato')}</dd><dt>Documentación</dt><dd>${lista(L_.documentacion, 'documento')}</dd></dl>`; }).join('')}</details>`;
  }
  function construirArbol() {
    const p = tab('modelo');
    if (!p) return;
    const arb = IDX.arbol || {};
    p.innerHTML = `<h4>Vistas</h4><div class="seg wrap-seg bim-vistas" role="group" aria-label="Vistas rápidas">
        <button type="button" data-v="todo" aria-pressed="true">Todo</button><button type="button" data-v="estructura" aria-pressed="false">Estructura</button><button type="button" data-v="arquitectura" aria-pressed="false">Arquitectura</button><button type="button" data-v="dotacion" aria-pressed="false">Dotación y equipos</button></div>
      <h4>Disciplinas</h4>
      <ul class="bim-disc">${DISCIPLINAS.map((d) => `<li data-d="${d}"><div class="bim-d-cab"><b>${NOM_DISC[d]}</b> <span class="bim-n" data-cuenta="${d}">${n0(IDX.disciplinas?.[d]?.elementos)}</span></div><small class="note">${esc(IDX.disciplinas?.[d]?.contenido || '')}${lodTxt(d)}</small><div class="seg bim-modo" role="group" aria-label="Cómo se ve ${NOM_DISC[d]}">${[['normal', 'Ver'], ['transparente', 'Transparente'], ['oculta', 'Ocultar']].map(([m, t]) => `<button type="button" data-m="${m}" aria-pressed="${m === 'normal'}">${t}</button>`).join('')}<button type="button" data-m="aislar" aria-pressed="false" title="Muestra solo esta disciplina">Aislar</button></div></li>`).join('')}
      <li><div class="bim-d-cab"><b>${NOM_DISC.REF}</b> <span class="bim-n">${n0(IDX.totales?.juegos_de_barras)} juegos</span></div><small class="note">${esc(IDX.disciplinas?.REF?.contenido || '')}: se ve por elemento o por eje, en la pestaña Refuerzo${lodTxt('REF')}</small></li></ul>
      ${loinTabla()}
      <label class="bim-check"><input type="checkbox" data-b="espacios"> Mostrar los espacios (recintos) como volúmenes</label>
      <p><button type="button" class="btn ghost" data-b="todo">Mostrar todo</button></p>
      <h4>Buscar</h4>
      <input type="search" class="bim-buscar" data-b="buscar" placeholder="Código, nombre, clase IFC o GlobalId" aria-label="Buscar en el modelo">
      <ul class="bim-res" data-b="res"></ul>
      <h4>Árbol del modelo</h4>
      <p class="note">Disciplina → nivel → clase IFC → elemento. Los números cuentan los elementos.</p>
      <div class="bim-arbol">${Object.entries(arb).map(([d, niv]) => `<details class="fold" data-ad="${d}"><summary><b>${NOM_DISC[d] || d}</b> <span class="bim-n">${n0(Object.values(niv).reduce((s, c) => s + Object.values(c).reduce((a, b) => a + b, 0), 0))}</span></summary>
        ${Object.entries(niv).map(([nv, cls]) => `<details class="fold" data-an="${nv}"><summary>${esc(NIVEL_CORTO[nv] || nv)} <span class="bim-n">${n0(Object.values(cls).reduce((a, b) => a + b, 0))}</span></summary>
          ${Object.entries(cls).map(([c, k]) => `<details class="fold bim-clase" data-ac="${d}|${nv}|${c}"><summary>${esc(IDX.clases?.[c] || c)} <small class="note">${esc(c)}</small> <span class="bim-n">${n0(k)}</span>${d !== 'REF' ? `<label class="bim-ojo" title="Ver u ocultar esta clase en este nivel"><input type="checkbox" checked data-clase="${escH(`${d}|${nv}|${c}`)}"> ver</label>` : ''}</summary><ul class="bim-els"></ul></details>`).join('')}</details>`).join('')}</details>`).join('')}</div>`;
    p.addEventListener('click', (ev) => {
      const b = ev.target.closest('button');
      if (!b) return;
      if (b.dataset.v) vistaRapida(b.dataset.v);
      else if (b.dataset.m) { const d = b.closest('li[data-d]').dataset.d; modoDisciplina(d, b.dataset.m); }
      else if (b.dataset.b === 'todo') mostrarTodo();
      else if (b.dataset.el) { const gi = giDe(b.dataset.el); if (gi != null) seleccionar(gi, { volar: true }); }
      else if (b.dataset.host) verRefuerzo(b.dataset.host);
    });
    p.addEventListener('change', (ev) => {
      const t = ev.target;
      if (t.dataset.clase) { if (t.checked) S.claseOff.delete(t.dataset.clase); else S.claseOff.add(t.dataset.clase); aplicar(); }
      if (t.dataset.b === 'espacios') { S.espacios = t.checked; aplicar(); }
    });
    // los elementos de una clase se listan al abrirla
    p.addEventListener('toggle', (ev) => {
      const d = ev.target;
      if (!d.open || !d.dataset.ac || d.dataset.lleno) return;
      d.dataset.lleno = '1';
      const [disc, nv, c] = d.dataset.ac.split('|'), ul = $(d, '.bim-els');
      if (disc === 'REF') {
        const hosts = new Map();
        L.forEach((x) => { if (x.e.refuerzo && x.nivel === nv) hosts.set(x.e.id, x.e); });
        ul.innerHTML = [...hosts.values()].slice(0, 400).map((e) => `<li><button type="button" data-host="${escH(e.id)}">${esc(e.id)}</button> <small class="note">${n0(e.refuerzo.barras)} barras · ${n0(e.refuerzo.kg)} kg</small></li>`).join('');
      } else {
        ul.innerHTML = L.map((x, gi) => [x, gi]).filter(([x]) => x.e.disciplina === disc && x.nivel === nv && x.e.clase === c).slice(0, 600).map(([x]) => `<li><button type="button" data-el="${escH(x.e.id)}">${esc(x.e.nombre)}</button> <small class="note">${esc(x.e.id)}</small></li>`).join('');
      }
      marcarArbol();
    }, true);
    const inp = $(p, '[data-b="buscar"]');
    let tb = 0;
    inp.addEventListener('input', () => { clearTimeout(tb); tb = setTimeout(() => buscar(inp.value), 160); });
  }
  function buscar(q) {
    const ul = $(tab('modelo'), '[data-b="res"]');
    q = q.trim().toLowerCase();
    if (q.length < 2) { ul.innerHTML = ''; return []; }
    const R = [];
    for (const x of L) {
      const e = x.e;
      if (e.id.toLowerCase().includes(q) || e.nombre.toLowerCase().includes(q) || e.clase.toLowerCase().includes(q) || e.guid === q || (IDX.clases?.[e.clase] || '').toLowerCase().includes(q)) R.push(x);
      if (R.length >= 40) break;
    }
    ul.innerHTML = R.length ? R.map((x) => `<li><button type="button" data-el="${escH(x.e.id)}">${esc(x.e.nombre)}</button> <small class="note">${esc(x.e.id)} · ${esc(NIVEL_CORTO[x.nivel] || x.nivel)}</small></li>`).join('') : '<li class="note">Nada coincide.</li>';
    return R.map((x) => x.e.id);
  }
  function marcarArbol() { $$(elPanel, '.bim-els button[data-el]').forEach((b) => b.setAttribute('aria-current', String(S.sel >= 0 && b.dataset.el === L[S.sel].e.id))); }
  function contadores() {
    if (!m3d) return;
    const c = Object.fromEntries(DISCIPLINAS.map((d) => [d, 0]));
    for (let gi = 0; gi < L.length; gi++) if (m3d.E.esVisible(gi)) c[L[gi].e.disciplina]++;
    for (const d of DISCIPLINAS) { const o = $(elPanel, `[data-cuenta="${d}"]`); if (o) o.textContent = `${n0(c[d])} de ${n0(IDX.disciplinas?.[d]?.elementos)} a la vista`; }
    $$(elPanel, '.bim-disc li[data-d]').forEach((tr) => { const m = S.modosUsuario[tr.dataset.d]; $$(tr, 'button[data-m]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.m === m || (b.dataset.m === 'aislar' && tr.dataset.aislada === '1')))); });
  }
  function modoDisciplina(d, m) {
    if (m === 'aislar') {
      const ya = $(elPanel, `li[data-d="${d}"]`).dataset.aislada === '1';
      $$(elPanel, '.bim-disc li[data-d]').forEach((tr) => { tr.dataset.aislada = ''; });
      for (const q of DISCIPLINAS) S.modosUsuario[q] = ya || q === d ? 'normal' : 'oculta';
      if (!ya) $(elPanel, `li[data-d="${d}"]`).dataset.aislada = '1';
    } else { S.modosUsuario[d] = m; $$(elPanel, '.bim-disc li[data-d]').forEach((tr) => { tr.dataset.aislada = ''; }); }
    if (S.vista !== 'modelo') { exclusivo('modelo'); S.vista = 'modelo'; }
    aplicar();
  }
  function vistaRapida(v) {
    const M = { todo: { ARQ: 'normal', EST: 'normal', CIM: 'normal', FIJO: 'normal', DOT: 'normal' }, estructura: { ARQ: 'oculta', EST: 'normal', CIM: 'normal', FIJO: 'oculta', DOT: 'oculta' },
      arquitectura: { ARQ: 'normal', EST: 'normal', CIM: 'oculta', FIJO: 'oculta', DOT: 'oculta' }, dotacion: { ARQ: 'transparente', EST: 'transparente', CIM: 'oculta', FIJO: 'normal', DOT: 'normal' } }[v];
    if (!M) return;
    Object.assign(S.modosUsuario, M);
    $$(elPanel, '.bim-vistas button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.v === v)));
    $$(elPanel, '.bim-disc li[data-d]').forEach((tr) => { tr.dataset.aislada = ''; });
    exclusivo('modelo');
    S.vista = 'modelo';
    aplicar(); chip(null);
    encuadrar(cajaTotal, { margen: 0.8 });
  }
  function mostrarTodo() {
    S.ocultos.clear(); S.aislados = null; S.claseOff.clear(); S.nivelOff.clear();
    $$(elPanel, 'input[data-clase]').forEach((i) => { i.checked = true; });
    vistaRapida('todo');
    if (S.sel >= 0) fichaElemento();
  }

  // ================================================================ pestañas
  function pestana(id) {
    if (!tab(id)) return;
    S.pest = id;
    $$(elPanel, '.bim-pestanas button').forEach((b) => { const on = b.dataset.p === id; b.setAttribute('aria-selected', String(on)); b.setAttribute('aria-pressed', String(on)); });
    $$(elPanel, '[data-pest]').forEach((p) => { p.hidden = p.dataset.pest !== id; });
    if (id === 'cortes') pintarPestCortes();
    if (id === 'cimentacion') pintarPestCimentacion();
    if (id === 'refuerzo') pintarPestRefuerzo();
    if (id === 'comportamiento') pintarPestComportamiento();
    if (id === '5d') pintarPest5D();
    if (id === '4d') { pintarPest4D(); if (S.fecha == null) fecha4D(t1_4d); }
    if (id === 'interferencias') pintarPestInterferencias();
    if (id === 'ifc') pintarPestIFC();
    if (id !== '4d' && S.fecha != null) { pararPlay(); fecha4D(null); }
  }
  $(elPanel, '.bim-pestanas')?.addEventListener('click', (ev) => { const b = ev.target.closest('button[data-p]'); if (b) pestana(b.dataset.p); });
  function pintarPestCortes() {
    const p = tab('cortes');
    if (!p) return;
    const c = S.corte;
    p.innerHTML = `<p class="note">Un plano corta el modelo y la sección se rellena con su rayado: concreto en gris, mampostería en rojizo y lo demás en gris claro.</p>
      <h4>Horizontal, por nivel</h4><div class="seg wrap-seg" role="group" aria-label="Corte horizontal">${CORTES_NIVEL.map(([id, z, t]) => `<button type="button" data-cn="${id}" aria-pressed="${c?.nivel === id}">${t} <small>${cota(z)}</small></button>`).join('')}</div>
      <h4>Vertical, por eje</h4><div class="seg wrap-seg" role="group" aria-label="Corte por eje">${[...(IDX.ejes?.x || []), ...(IDX.ejes?.y || [])].map((q) => `<button type="button" data-ce="${q.id}" aria-pressed="${c?.eje === q.id}">Eje ${q.id}</button>`).join('')}</div>
      <p class="bim-fila">${c && c.tipo !== 'h' ? '<button type="button" class="btn ghost" data-b="lado">Ver el otro lado</button>' : ''}${c ? '<button type="button" class="btn ghost" data-b="sincorte">Quitar el corte</button>' : ''}</p>
      <p class="note">Los ejes A a D van de occidente a oriente y del 1 al 7 de sur a norte (retícula de 7,20 m, múltiplo del módulo de 1,20 m). Para ver la sección de un solo elemento, elígelo y pulsa «Vista de corte» en su ficha.</p>`;
    p.onclick = (ev) => {
      const b = ev.target.closest('button');
      if (!b) return;
      if (b.dataset.cn) cortarNivel(b.dataset.cn);
      else if (b.dataset.ce) cortarEje(b.dataset.ce);
      else if (b.dataset.b === 'lado' && S.corte) cortarEje(S.corte.eje, -(S.corte.lado || 1));
      else if (b.dataset.b === 'sincorte') { if (S.corte?.elemento) { S.aislados = null; salirRefuerzo(); } quitarCorte(); aplicar(); }
    };
  }
  function pintarPestCimentacion() {
    const p = tab('cimentacion');
    if (!p) return;
    const C = IDX.cantidades?.frente_a_A || [], f = (t) => C.find((q) => q.tipo === t);
    const pil = L.filter((x) => x.e.clase === 'IfcPile'), largo = pil.reduce((s, x) => s + (x.e.geometria.z1 - x.e.geometria.z0), 0);
    const dad = L.filter((x) => x.e.tipo_predefinido === 'PILE_CAP').length, vc = L.filter((x) => x.e.tipo_predefinido === 'FOOTING_BEAM').length;
    const on = S.vista === 'cimentacion';
    p.innerHTML = `<p class="note">Pilotes preexcavados de concreto bajo dados y losas de pilotes, vigas de amarre en las dos direcciones, contrapiso, fosos de ascensores y cisternas. <span class="bim-tipo">Prediseño: estimación hasta el estudio geotécnico.</span></p>
      <p class="bim-fila"><button type="button" class="btn${on ? ' ghost' : ''}" data-b="cim">${on ? 'Volver al modelo' : 'Ver la cimentación'}</button></p>
      <h4>Terreno</h4><div class="seg wrap-seg" role="group" aria-label="Terreno">${[['cortado', 'Cortado'], ['semi', 'Semitransparente'], ['opaco', 'Opaco']].map(([m, t]) => `<button type="button" data-t="${m}" aria-pressed="${S.terreno === m}">${t}</button>`).join('')}</div>
      <dl class="kv bim-kv">${kvFila('Pilotes', `${n0(pil.length)} · ${n0(largo)} m en total`)}${kvFila('Dados y losas de pilotes', `${n0(dad)} dados`)}${kvFila('Vigas de amarre', n0(vc))}
      ${f('pilotes') ? kvFila('Concreto de pilotes', `${n(f('pilotes').bim_m3, 1)} m³`) : ''}${f('dados_y_losas_de_pilotes') ? kvFila('Concreto de dados y losas', `${n(f('dados_y_losas_de_pilotes').bim_m3, 1)} m³`) : ''}
      ${kvFila('Concreto de la cimentación', `${n(IDX.cantidades?.por_disciplina?.CIM?.concreto_m3, 1)} m³`)}${kvFila('Acero de la cimentación', `${n0(IDX.cantidades?.por_disciplina?.CIM?.acero_kg)} kg`)}</dl>
      <p class="note">Cálculo propio con la geometría del modelo. En el simulador la base queda empotrada en la cara superior de los dados (sin interacción suelo-estructura).</p>
      <h4>Dados más cargados</h4><ul class="bim-lista">${L.filter((x) => x.e.tipo_predefinido === 'PILE_CAP').map((x) => [x, Object.values(x.e.analisis?.cargas_servicio_kN || {}).reduce((s, c) => s + (c.D_kN || 0) + (c.L_kN || 0), 0)]).sort((a, b) => b[1] - a[1]).slice(0, 6).map(([x, c]) => `<li><button type="button" class="bim-link" data-el="${escH(x.e.id)}">${esc(x.e.nombre)}</button><small class="note"> · ${n0(c)} kN de servicio</small></li>`).join('')}</ul>`;
    p.onclick = (ev) => {
      const b = ev.target.closest('button');
      if (!b) return;
      if (b.dataset.b === 'cim') { if (S.vista === 'cimentacion') { cimentacion(false); encuadrar(cajaTotal); } else cimentacion(true, S.terreno === 'opaco' ? 'cortado' : S.terreno); pintarPestCimentacion(); }
      else if (b.dataset.t) { S.terreno = b.dataset.t; terreno.poner(b.dataset.t); pintarPestCimentacion(); }
      else if (b.dataset.el) { const gi = giDe(b.dataset.el); if (gi != null) seleccionar(gi, { volar: true }); }
    };
  }
  const MUESTRAS = [['C-B2-2', 'Una columna'], ['VX-2-BC-2', 'Una viga'], ['D-B2', 'Un dado'], ['PIL-D-B2-1', 'Un pilote'], ['MY-N6-2', 'Un muro'], ['LN1-AB-12', 'Una losa'], ['ESC-N-2', 'Una escalera'], ['VC-2-BC', 'Una viga de amarre']];
  function pintarPestRefuerzo() {
    const p = tab('refuerzo');
    if (!p) return;
    const r = S.refuerzo, ej = r?.eje;
    p.innerHTML = `<p class="note">El armado de cada elemento con su geometría real: barras longitudinales, estribos y ganchos, zonas confinadas, traslapos, canastas de pilotes y parrillas de dados. Se dibuja solo lo elegido, con el concreto transparente. <span class="bim-tipo">Despiece del prediseño (cálculo propio; NSR-10 con capacidad moderada de disipación de energía).</span></p>
      <h4>Un elemento</h4><p class="note">Toca una columna, viga, losa, muro, escalera, pilote, dado o viga de amarre y pulsa «Ver refuerzo» en su ficha, o elige un ejemplo:</p>
      <div class="bim-botones">${MUESTRAS.filter(([id]) => giDe(id) != null).map(([id, t]) => `<button type="button" class="btn ghost" data-host="${escH(id)}" aria-pressed="${r?.hosts?.[0] === id && r.hosts.length === 1}">${t}</button>`).join('')}</div>
      <h4>Refuerzo del eje</h4><div class="bim-eje"><label>Eje <select data-b="eje">${[...(IDX.ejes?.x || []), ...(IDX.ejes?.y || [])].map((q) => `<option value="${q.id}"${ej?.eje === q.id ? ' selected' : ''}>${q.id}</option>`).join('')}</select></label>
      <label>Nivel <select data-b="nivel">${NIVELES_EJE.map(([id, t]) => `<option value="${id}"${(ej?.nivel || 'P2') === id ? ' selected' : ''}>${t}</option>`).join('')}</select></label><button type="button" class="btn" data-b="vereje">Ver el eje</button></div>
      ${r ? `<p class="bim-stat"><b>${n0(barrasInfo?.barras)}</b> barras · <b>${n0(barrasInfo?.kg)}</b> kg · ${n0(r.hosts.length)} elemento${r.hosts.length > 1 ? 's' : ''}</p><p class="bim-fila"><button type="button" class="btn ghost" data-b="salirref">Volver al modelo</button></p>` : ''}`;
    p.onclick = (ev) => {
      const b = ev.target.closest('button');
      if (!b) return;
      if (b.dataset.host) verRefuerzo(b.dataset.host);
      else if (b.dataset.b === 'vereje') refuerzoEje($(p, '[data-b="eje"]').value, $(p, '[data-b="nivel"]').value);
      else if (b.dataset.b === 'salirref') { S.aislados = null; salirRefuerzo(); encuadrar(cajaTotal); }
    };
  }
  function pintarPestComportamiento() {
    const p = tab('comportamiento');
    if (!p) return;
    const res = ctx.sismo?.ultimo?.() || null, C = S.colores;
    if (!res) {
      p.innerHTML = `<p class="note">Aquí la estructura se pinta con el último cálculo del simulador sísmico de esta visita: demanda contra capacidad de cada columna, viga y muro, las rótulas que se formaron y la deriva de cada entrepiso.</p><p class="note">Todavía no hay un cálculo en esta sesión.</p><p class="bim-fila"><button type="button" class="btn" data-b="abrir">Abrir el simulador sísmico</button></p>`;
    } else {
      const fe = res.opciones?.escala === 'nsr10' && Number.isFinite(+res.resultados?.factor_escala) ? +res.resultados.factor_escala : null;
      p.innerHTML = `<p class="note">Último cálculo: sismo de Mw ${n(res.params?.Mw, 1)} a ${n0(res.params?.distancia_epicentral_km)} km y ${n0(res.params?.profundidad_km)} km de profundidad${res.pga_g != null ? `, aceleración máxima del suelo de ${n(res.pga_g * (fe || 1), 2)} g` : ''}${fe ? ` (registro multiplicado por ${n(fe, 2)} para llevarlo al nivel de diseño de la NSR-10: escenario hipotético)` : ''}. <span class="bim-tipo">Cálculo propio del simulador.</span></p>
        <div class="seg wrap-seg" role="group" aria-label="Qué colorear">${[['dc', 'Demanda/capacidad'], ['rotulas', 'Rótulas']].map(([k, t]) => `<button type="button" data-c="${k}" aria-pressed="${C?.campo === k}">${t}</button>`).join('')}</div>
        ${C ? `<dl class="kv bim-kv">${kvFila('Elementos coloreados', n0(C.conColor))}${kvFila('Mayor D/C', n(C.top[0]?.[1], 2))}${kvFila('Extremos con rótula', n0(C.rotulas))}${kvFila('Deriva máxima', `${n(100 * Math.max(0, ...C.deriva), 2)} % (límite ${n(100 * C.lim, 1)} %)`)}</dl>
          <h4>Elementos más exigidos</h4><ul class="bim-lista">${C.top.map(([gi, v]) => `<li><button type="button" class="bim-link" data-el="${escH(L[gi].e.id)}">${esc(L[gi].e.nombre)}</button><small class="note"> · D/C ${n(v, 2)}</small></li>`).join('')}</ul>
          <p class="bim-fila"><button type="button" class="btn ghost" data-b="quitar">Quitar los colores</button><button type="button" class="btn ghost" data-b="abrir">Abrir el simulador</button></p>` : '<p class="bim-fila"><button type="button" class="btn" data-c="dc">Colorear la estructura</button><button type="button" class="btn ghost" data-b="abrir">Abrir el simulador</button></p>'}
        <p class="note">El modelo sísmico empotra la base en la cara superior de los dados; las losas y la cimentación no son elementos del análisis (van en gris). Modelo de prediseño: no reemplaza el diseño estructural firmado.</p>`;
    }
    p.onclick = (ev) => {
      const b = ev.target.closest('button');
      if (!b) return;
      if (b.dataset.c) comportamiento(b.dataset.c);
      else if (b.dataset.b === 'abrir') ctx.abrirModo?.('sismo');
      else if (b.dataset.b === 'quitar') quitarComportamiento();
      else if (b.dataset.el) { const gi = giDe(b.dataset.el); if (gi != null) seleccionar(gi, { volar: true }); }
    };
  }
  function pintarPest5D() {
    const p = tab('5d');
    if (!p) return;
    const C = IDX.cinco_d || {}, comp = C.comparacion || [];
    const bim = comp.reduce((s, c) => s + (+c.bim_valor || 0), 0), pres = comp.reduce((s, c) => s + (+c.presupuesto_valor || 0), 0);
    p.innerHTML = `<p class="note">Cada elemento lleva el ítem del presupuesto que lo paga y su análisis de precio unitario: el modelo mide las cantidades y las multiplica por el valor unitario del presupuesto. <span class="bim-tipo">Cálculo propio; precios del presupuesto de 2026 (estimación).</span></p>
      <dl class="kv bim-kv">${kvFila('Ítems comparados', n0(comp.length))}${kvFila('Valor con las cantidades del modelo', millones(bim))}${kvFila('Valor de esos ítems en el presupuesto', millones(pres))}${kvFila('Diferencia', `${millones(bim - pres)} (${n((100 * (bim - pres)) / (pres || 1), 1)} %)`)}</dl>
      <p class="bim-fila"><button type="button" class="btn${S.color5d ? ' ghost' : ''}" data-b="c5d">${S.color5d ? 'Quitar los colores' : 'Colorear por capítulo'}</button></p>
      <p class="note">Las tablas por disciplina y capítulo, y la comparación ítem por ítem con el presupuesto, están en la tarjeta «Cantidades y costo del modelo», debajo del 3D.</p>`;
    p.onclick = (ev) => { const b = ev.target.closest('button'); if (b?.dataset.b === 'c5d') { color5D(!S.color5d); pintarPest5D(); } };
  }
  function pintarPest4D() {
    const p = tab('4d');
    if (!p) return;
    const av = S.avance;
    p.innerHTML = `<p class="note">El deslizador (sobre el 3D) recorre el cronograma: cimentación, estructura piso a piso, cerramientos, acabados, redes y equipamiento fijo, y dotación. Lo que está en obra en esa fecha va en amarillo; lo que todavía no empieza no se ve. <span class="bim-tipo">Estimación: fases repartidas dentro de las etapas del cronograma del proyecto.</span></p>
      ${av ? `<p class="bim-stat">${fechaTxt(av.fecha)} · avance del valor de los elementos: <b>${n(av.pct, 0)} %</b></p>` : ''}
      <ol class="bim-fases">${F4.map((f) => `<li${av?.enObra.includes(f.id) ? ' class="on"' : ''}><button type="button" class="bim-link" data-f="${f.id}">${esc(f.nombre)}</button><br><small class="note">${fechaTxt(f.inicio)} a ${fechaTxt(f.fin)} · ${esc(NOM_DISC[f.disciplina] || f.disciplina)}</small></li>`).join('')}</ol>`;
    p.onclick = (ev) => { const b = ev.target.closest('button[data-f]'); if (!b) return; pararPlay(); const f = fases.get(b.dataset.f); fecha4D(Date.parse(`${f.fin}T12:00:00`)); };
  }
  let filtroInt = { sev: 'dura', cat: '', resp: '' }, maxInt = 40;
  async function pintarPestInterferencias() {
    const p = tab('interferencias');
    if (!p) return;
    const res = IDX.interferencias?.resumen;
    p.innerHTML = `<p class="note">Revisión automática del modelo: elementos y barras que chocan, recubrimientos, separación libre entre barras, apoyos de la cimentación y coherencia entre arquitectura y estructura. <span class="bim-tipo">Cálculo propio sobre el modelo de prefactibilidad.</span></p>
      ${res ? `<dl class="kv bim-kv">${kvFila('Hallazgos', n0(res.total))}${kvFila('Duros (hay que corregirlos antes del diseño definitivo)', n0(Object.values(res.por_categoria).reduce((s, c) => s + c.dura, 0)))}${kvFila('Medios (se resuelven en el detallado)', n0(Object.values(res.por_categoria).reduce((s, c) => s + c.media, 0)))}${kvFila('Leves (dentro de las tolerancias)', n0(Object.values(res.por_categoria).reduce((s, c) => s + c.leve, 0)))}</dl>` : ''}
      <div class="bim-filtros"><label>Severidad <select data-fi="sev"><option value="">todas</option>${['dura', 'media', 'leve'].map((s) => `<option${filtroInt.sev === s ? ' selected' : ''}>${s}</option>`).join('')}</select></label>
      <label>Categoría <select data-fi="cat"><option value="">todas</option>${Object.keys(res?.por_categoria || {}).map((c) => `<option${filtroInt.cat === c ? ' selected' : ''}>${esc(c)}</option>`).join('')}</select></label>
      <label>A cargo de <select data-fi="resp"><option value="">todos</option>${Object.keys(res?.por_responsable || {}).map((c) => `<option value="${escH(c)}"${filtroInt.resp === c ? ' selected' : ''}>${esc(responsable(c))}</option>`).join('')}</select></label></div>
      <ul class="bim-int" data-b="lint"><li class="note">Cargando…</li></ul><p data-b="mas"></p>
`;
    $$(p, 'select[data-fi]').forEach((s) => s.addEventListener('change', () => { filtroInt[s.dataset.fi] = s.value; maxInt = 40; listaInt(); }));
    p.onclick = (ev) => {
      const b = ev.target.closest('button');
      if (!b) return;
      if (b.dataset.int) irAInterferencia(b.dataset.int);
      if (b.dataset.b === 'mas') { maxInt += 60; listaInt(); }
    };
    await listaInt();
  }
  async function listaInt() {
    const p = tab('interferencias'), I = await interferencias(), ul = $(p, '[data-b="lint"]');
    if (!I) { ul.innerHTML = '<li class="note">No se pudo leer la lista de interferencias.</li>'; return; }
    const F = I.interferencias.filter((x) => (!filtroInt.sev || x.severidad === filtroInt.sev) && (!filtroInt.cat || x.categoria === filtroInt.cat) && (!filtroInt.resp || x.responsable === filtroInt.resp));
    ul.innerHTML = F.slice(0, maxInt).map((x) => `<li><div class="bim-int-c"><span class="pill bim-sev-${x.severidad}">${esc(x.severidad)}</span> <b>${esc(x.categoria)}</b> <small class="note">${esc(x.id)} · ${esc(NIVEL_CORTO[x.nivel] || x.nivel || '')} · a cargo de: ${esc(responsable(x.responsable))}</small></div><p>${esc(x.descripcion)}</p>${x.propuesta ? `<p class="note"><b>Propuesta:</b> ${esc(x.propuesta)}</p>` : ''}${x.posicion ? `<button type="button" class="bim-ir" data-int="${escH(x.id)}">Ir a</button>` : ''}</li>`).join('') || '<li class="note">Ningún hallazgo con esos filtros.</li>';
    $(p, '[data-b="mas"]').innerHTML = F.length > maxInt ? `<button type="button" class="btn ghost" data-b="mas">Ver ${n0(Math.min(60, F.length - maxInt))} más (de ${n0(F.length)})</button>` : `<small class="note">${n0(F.length)} hallazgos</small>`;
  }
  function pintarPestIFC() {
    const p = tab('ifc');
    if (!p) return;
    const V = IDX.validacion_ifc, G = IDX.georreferenciacion || {};
    p.innerHTML = `<p class="note">El modelo se publica en IFC4, el formato abierto de BIM (ISO 16739), para abrirlo en cualquier programa o visor IFC. ${AVISO}</p>
      <ul class="bim-ifc">${(IDX.ifc || []).map((f) => `<li><a class="bim-descarga" href="${escH(new URL(`../../../${f.url}`, import.meta.url).href)}" download="${escH(f.archivo)}" data-ifc="${escH(f.archivo)}">${/refuerzo/.test(f.archivo) ? 'Descargar el refuerzo' : 'Descargar el modelo'} (IFC4, ${n(f.mb, 1)} MB)</a><br><small class="note">${esc(f.contenido)} · archivo <code>${escH(f.archivo)}</code></small></li>`).join('')}</ul>
      ${V ? `<h4>Validación</h4><p class="note">Revisado con ${esc(V.herramienta)}: <b>${esc(V.resultado)}</b> (${n0(V.errores)} errores de esquema, con las reglas del esquema).</p>
      <dl class="kv bim-kv">${V.archivos.map((a) => kvFila(/refuerzo/.test(a.archivo) ? 'Refuerzo' : 'Modelo', `${n0(a.entidades)} entidades · ${n0(a.globalid?.unicos)} GlobalId únicos`)).join('')}</dl>
      ${V.archivos.some((a) => a.plantillas_ifc4 || a.cuatro_d || a.cinco_d) ? `<p class="note">${V.archivos.map((a) => {
        const P = a.plantillas_ifc4, T = a.cuatro_d, C = a.cinco_d, q = [];
        if (P) q.push(`${n0(P.propiedades_revisadas)} propiedades de ${n0(P.conjuntos_revisados)} conjuntos comparadas con las plantillas de IFC4 (${P.problemas ? `${n0(P.problemas)} con problemas` : 'todas conformes'})`);
        if (T) q.push(`${n0(T.con_salidas)} de ${n0(T.tareas)} tareas del cronograma con sus elementos asignados`);
        if (C) q.push(`${n0(C.en_el_presupuesto_ifc)} partidas del presupuesto con su valor (${millones(C.total_ifc)}, cálculo propio)`);
        return `<b>${/refuerzo/.test(a.archivo) ? 'Refuerzo' : 'Modelo'}:</b> ${q.join('; ')}.`;
      }).join(' ')}</p>` : ''}
      ${V.archivos[0]?.concreto ? `<p class="note">Concreto medido en el IFC: ${n(V.archivos[0].concreto.qto_m3, 2)} m³ en las cantidades y ${n(V.archivos[0].concreto.geometria_ifcopenshell_m3, 2)} m³ en la geometría, frente a ${n(V.archivos[0].concreto.json_m3, 2)} m³ del modelo (cálculo propio).</p>` : ''}` : ''}
      <h4>Georreferenciación</h4><dl class="kv bim-kv">${kvFila('Sistema', esc(`${G.crs || ''} (${G.crs_nombre || ''})`))}${kvFila('Este del ±0,00', `${n(G.este_m, 2)} m`)}${kvFila('Norte del ±0,00', `${n(G.norte_m, 2)} m`)}${kvFila('Altura', `${n0(G.altura_ortometrica_m)} m sobre el nivel del mar (estimación)`)}</dl>
      <p class="note">${esc(String(G.nota || '').replace(/del ancla del contrato \(sección 0\)/, 'del punto de referencia del proyecto (±0,00)').replace(/;? ?ver la validación del IFC\)/, ')'))}</p>`;
  }

  // ================================================================ tarjeta de abajo: cantidades y costo (5D)
  function pintarTablas() {
    if (!IDX) { elTablas.innerHTML = ''; return; }
    const C = IDX.cinco_d || {}, PD = C.por_disciplina_y_capitulo || {}, caps = [...new Set(Object.values(PD).flatMap((o) => Object.keys(o)))].sort((a, b) => (/^\d+$/.test(a) && /^\d+$/.test(b) ? +a - +b : a.localeCompare(b)));
    const disc = Object.keys(PD), tot = (d) => Object.values(PD[d] || {}).reduce((s, v) => s + v, 0);
    const nomCap = (k) => esc(nombreCapitulo(k));
    const comp = [...(C.comparacion || [])].sort((a, b) => Math.abs(b.efecto_cop || 0) - Math.abs(a.efecto_cop || 0));
    const filaC = (c) => `<tr><td>${esc(c.item)} ${esc(c.descripcion)}${c.nota ? `<br><small class="note">${esc(c.nota)}</small>` : ''}</td><td class="n" data-th="Presupuesto">${n(c.presupuesto_cantidad, 1)} ${esc(c.unidad)}<br><small>${millones(c.presupuesto_valor)}</small></td><td class="n" data-th="Modelo">${n(c.bim_cantidad, 1)} ${esc(c.unidad)}<br><small>${millones(c.bim_valor)}</small></td><td class="n" data-th="Diferencia">${c.diferencia_pct != null ? conSigno(`${n(c.diferencia_pct, 0).replace('-', '−')} %`, c.diferencia_pct) : '—'}<br><small>${conSigno(millones(c.efecto_cop), c.efecto_cop)}</small></td><td data-th=""><button type="button" class="bim-ir" data-item="${escH(c.item)}">Ver en 3D</button></td></tr>`;
    const FA = IDX.cantidades?.frente_a_A || [];
    elTablas.innerHTML = `<p class="note">${AVISO} Cifras: cantidades medidas en el modelo (cálculo propio) × valores unitarios del presupuesto de obra (pesos de 2026; estimación). Donde el modelo y el presupuesto difieren, la diferencia queda como pendiente con su efecto en pesos: el presupuesto no se edita aquí.</p>
      <h4>Valor del modelo por disciplina y capítulo</h4>
      <div class="tbl-wrap"><table class="bim-t5d"><thead><tr><th>Capítulo</th>${disc.map((d) => `<th class="n">${NOM_DISC[d] || d}</th>`).join('')}</tr></thead><tbody>
      ${caps.map((k) => `<tr><td>${/^\d+$/.test(k) ? `${k}. ` : ''}${nomCap(k)}</td>${disc.map((d) => `<td class="n" data-th="${NOM_DISC[d] || d}">${PD[d]?.[k] ? millones(PD[d][k]) : ''}</td>`).join('')}</tr>`).join('')}
      <tr><td><b>Total</b></td>${disc.map((d) => `<td class="n" data-th="${NOM_DISC[d] || d}"><b>${millones(tot(d))}</b></td>`).join('')}</tr></tbody></table></div>
      <h4>Ítem por ítem frente al presupuesto</h4>
      <div class="tbl-wrap"><table class="fichas bim-comp"><thead><tr><th>Ítem</th><th class="n">Presupuesto</th><th class="n">Modelo</th><th class="n">Diferencia</th><th></th></tr></thead><tbody>${comp.slice(0, 12).map(filaC).join('')}</tbody></table></div>
      ${comp.length > 12 ? `<details class="fold"><summary>Los otros ${comp.length - 12} ítems</summary><div class="tbl-wrap"><table class="fichas bim-comp"><tbody>${comp.slice(12).map(filaC).join('')}</tbody></table></div></details>` : ''}
      ${FA.length ? `<h4>Concreto y acero del modelo frente al prediseño</h4><div class="tbl-wrap"><table class="fichas"><thead><tr><th>Tipo</th><th class="n">Concreto (m³)</th><th class="n">Acero (kg)</th></tr></thead><tbody>${FA.map((q) => `<tr><td>${esc(q.tipo.replace(/_/g, ' '))}</td><td class="n" data-th="Concreto (m³)">${n(q.bim_m3, 1)}<br><small>prediseño ${n(q.A_m3, 1)}</small></td><td class="n" data-th="Acero (kg)">${n0(q.bim_kg)}<br><small>prediseño ${n0(q.A_kg)}</small></td></tr>`).join('')}</tbody></table></div><p class="note">${esc(IDX.cantidades?.nota || '')}</p>` : ''}`;
  }
  elTablas.addEventListener('click', (ev) => {
    const b = ev.target.closest('button[data-item]');
    if (!b || !m3d) return;
    const gis = L.map((x, gi) => [x, gi]).filter(([x]) => (x.e.costo || []).some((c) => String(c.item) === b.dataset.item)).map(([, gi]) => gi);
    if (!gis.length) { estado('Ese ítem no tiene elementos dibujados (va en el refuerzo o es global).'); return; }
    limpiarRefuerzo(); S.vista = 'modelo';
    S.aislados = new Set(gis);
    aplicar();
    encuadrar(m3d.caja(gis), { margen: 0.75 });
    chip(`Ítem ${b.dataset.item}: ${gis.length} elementos (pulsa «Mostrar todo» en la pestaña Modelo para volver)`);
    st.el.scrollIntoView({ behavior: reducedMotion ? 'auto' : 'smooth', block: 'center' });
  });

  // ================================================================ ¿se ve? (QA): un rayo de la cámara al centro del elemento (o a 0,2 m de
  // su punta, en los pilotes); lo tapan los elementos opacos del modelo que estén a la vista y el suelo del sitio donde no
  // esté recortado (hueco de la excavación) ni transparente
  const arribaVisible = (q) => { for (let x = q; x; x = x.parent) if (!x.visible) return false; return true; };
  function seVe(id, { punta = false, fantasma = false } = {}) {
    const gi = giDe(id);
    if (gi == null || !m3d) return null;
    if (!m3d.E.esVisible(gi) && !fantasma) return { ve: false, tapa: 'oculto' };
    const c = m3d.cajaProyecto(gi), obj = P3((c[0] + c[3]) / 2, (c[1] + c[4]) / 2, punta ? c[2] + 0.2 : (c[2] + c[5]) / 2);
    st.camera.updateMatrixWorld();
    const o = st.camera.position.clone(), d = obj.clone().sub(o), dist = d.length();
    const r = new THREE.Raycaster(o, d.normalize(), 0, dist), M = modosVista();
    for (const h of r.intersectObjects(Object.values(m3d.mallas).filter((m) => m.visible), false)) {
      const g = h.object.geometry.attributes.eid.getX(h.face.a);
      if (g === gi) break;
      if (!m3d.E.esVisible(g) || M[m3d.disciplinaDe(g)] === 'transparente' || L[g].e.clase === 'IfcSpace') continue;
      if (m3d.plano() && m3d.plano().distanceToPoint(h.point) < 0) continue;
      return { ve: false, tapa: L[g].e.id, suelo: false };
    }
    for (const h of r.intersectObjects((terreno?.mallas() || []).filter(arribaVisible), false)) {
      const mt = [].concat(h.object.material)[0];
      if (mt?.transparent && mt.opacity < 0.5) continue;
      if (terreno.enHueco(h.point)) continue;
      return { ve: false, tapa: h.object.name || 'suelo', suelo: true };
    }
    return { ve: true, suelo: false };
  }
  // el suelo del sitio a la vista y si lleva la copia del modo (recorte o transparencia)
  const sueloQA = () => (terreno?.mallas() || []).filter(arribaVisible).map((o) => {
    const mt = [].concat(o.material)[0] || {};
    return { nombre: o.name, copia: terreno.esCopia(o.material), recorte: (mt.clippingPlanes || []).length, opacidad: mt.opacity, transparente: !!mt.transparent };
  });

  // ================================================================ sobre el recuadro: rótulo, leyenda y atajos
  function chip(t) { const c = $(elHud, '[data-b="chip"]'); c.textContent = t || ''; c.hidden = !t; }
  function ley(html) { const d = $(elHud, '[data-b="ley"]'); if (!html) { d.hidden = true; return; } $(d, '[data-b="ley-c"]').innerHTML = html; d.hidden = false; d.open = !telefono(); }
  function accionesHud() {
    const a = $(elHud, '[data-b="acc"]'), B = [];
    if (S.refuerzo) B.push('<button type="button" data-h="salirref">Volver al modelo</button>');
    if (S.corte) B.push('<button type="button" data-h="sincorte">Quitar el corte</button>');
    a.innerHTML = B.join('');
  }
  elHud.addEventListener('click', (ev) => {
    const b = ev.target.closest('button[data-h]');
    if (!b) return;
    if (b.dataset.h === 'salirref') { S.aislados = null; salirRefuerzo(); encuadrar(cajaTotal); }
    if (b.dataset.h === 'sincorte') { if (S.corte?.elemento) { S.aislados = null; salirRefuerzo(); } quitarCorte(); aplicar(); }
  });

  // ================================================================ tema
  const sinTema = onTheme((t) => {
    m3d?.tema(t);
    if (S.colores) comportamiento(S.colores.campo, { volar: false });
    if (marcaInt) marcaInt.material.color.copy(t.accent);
    st.invalidate();
  });

  // ================================================================ entrar y salir (6.8)
  const poner = (cont, e) => { if (!cont) return; cont.replaceChildren(e); cont.hidden = false; };
  const sacar = (cont) => { if (!cont) return; cont.replaceChildren(); cont.hidden = true; };
  let clip0 = false, polar0 = null, primero = true;
  // los árboles del sitio y la acometida eléctrica tapaban el modelo: se ocultan mientras dura el modo. torre.js los vuelve a
  // mostrar cuando carga un nivel de detalle de los modelos del sitio, así que se revisa cada 20 cuadros; al salir, torre.js
  // les devuelve su visibilidad con el resto del exterior
  const tapados = new Set();
  let kCuadro = 0;
  const _v = new THREE.Vector3();
  // llamadas del refuerzo en dos columnas: las anclas de la izquierda llevan su caja a la izquierda de todas ellas y las de la
  // derecha a la derecha; en cada columna las cajas se apilan en el orden vertical de sus anclas, así que las líneas no se
  // cruzan ni pasan por encima de otra caja. Si una columna no cabe en el recuadro (teléfono), la caja entra al recuadro y
  // se pone debajo de su ancla, con la línea hasta su borde de arriba
  function despejarLlamadas() {
    const W = st.el.clientWidth || 1, H = st.el.clientHeight || 1, Q = [], M = 6, D = 22, G = 4;
    for (const o of etiquetas) {
      if (!o.element.classList.contains('bim-ancla') || !o.parent || o.element.style.display === 'none') continue;
      o.getWorldPosition(_v).project(st.camera);
      if (_v.z > 1) continue;
      const box = o.element.firstElementChild;
      if (!box) continue;
      if (!o.userData.w) { o.userData.w = box.offsetWidth; o.userData.h = box.offsetHeight; }
      const w = o.userData.w, h = o.userData.h;
      if (!w) continue;
      const x = ((_v.x + 1) / 2) * W, y = ((1 - _v.y) / 2) * H;
      // ancla fuera del recuadro (la barra sigue más allá de lo que se ve): la llamada no se muestra
      const fuera = x < 4 || x > W - 4 || y < 4 || y > H - 4;
      if (o.element.classList.contains('fuera') !== fuera) o.element.classList.toggle('fuera', fuera);
      if (!fuera) Q.push({ o, x, y, w, h });
    }
    if (!Q.length) return;
    Q.sort((a, b) => a.x - b.x || a.y - b.y);
    // lo que ya ocupa el recuadro (título, leyenda, botones): las cajas no se meten debajo
    const rs = st.el.getBoundingClientRect(), tapas = [];
    for (const e of [...elHud.querySelectorAll('[data-b="chip"], [data-b="ley"], [data-b="acc"] > *, [data-b="barra4d"]'), ...st.el.querySelectorAll('.hud-btn, .hud')]) {
      if (e.hidden || !e.offsetParent) continue;
      const r = e.getBoundingClientRect();
      if (r.width && r.height) tapas.push({ x0: r.left - rs.left, x1: r.right - rs.left, y0: r.top - rs.top, y1: r.bottom - rs.top });
    }
    // corre la caja (hacia abajo, s = 1, o hacia arriba, s = -1) hasta que no quede debajo de nada de eso
    const libre = (x0, x1, top, h, s) => {
      for (let k = 0; k < 8; k++) {
        const t = tapas.find((r) => x0 < r.x1 + G && x1 > r.x0 - G && top < r.y1 + G && top + h > r.y0 - G);
        if (!t) break;
        top = s > 0 ? t.y1 + G : t.y0 - G - h;
      }
      return top;
    };
    // borde de la columna (el de la derecha de las cajas en la izquierda, el de la izquierda en la derecha) y cuántas cajas
    // quedarían encima de su propia ancla
    const columna = (L, izq) => {
      if (!L.length) return { c: 0, tapan: 0 };
      const wm = Math.max(...L.map((q) => q.w));
      const c = izq ? Math.max(Math.min(...L.map((q) => q.x)) - D, M + wm) : Math.min(Math.max(...L.map((q) => q.x)) + D, W - M - wm);
      return { c, tapan: L.filter((q) => (izq ? c > q.x - 8 : c < q.x + 8)).length };
    };
    const n = Q.length;
    let k = 0, mejor = Infinity;
    for (let i = 0; i <= n; i++) {
      const coste = 1000 * (columna(Q.slice(0, i), true).tapan + columna(Q.slice(i), false).tapan) + Math.abs(i - n / 2) + (i === 0 || i === n ? 0.25 : 0);
      if (coste < mejor) { mejor = coste; k = i; }
    }
    for (const [L, izq] of [[Q.slice(0, k), true], [Q.slice(k), false]]) {
      if (!L.length) continue;
      const { c } = columna(L, izq);
      for (const q of L) {
        q.tapa = izq ? c > q.x - 8 : c < q.x + 8;
        q.ideal = q.tapa ? q.y + 12 : q.y - 11;
      }
      L.sort((a, b) => a.ideal - b.ideal || a.x - b.x);
      // apilar hacia abajo desde la altura ideal de cada una y, si la última se sale, devolver hacia arriba
      const tops = [], bx = (q) => (izq ? [c - q.w, c] : [c, c + q.w]);
      L.forEach((q, i) => { tops[i] = libre(...bx(q), Math.max(q.ideal, i ? tops[i - 1] + L[i - 1].h + G : M), q.h, 1); });
      for (let i = L.length - 1; i >= 0; i--) {
        const tope = (i < L.length - 1 ? tops[i + 1] - G : H - M) - L[i].h;
        if (tops[i] > tope) tops[i] = libre(...bx(L[i]), tope, L[i].h, -1);
        tops[i] = Math.max(M, tops[i]);
      }
      L.forEach((q, i) => {
        const el_ = q.o.element, t = tops[i];
        const dx = Math.round(izq ? q.x - c : c - q.x), dy = Math.round(t - (q.y - 11));
        // fin de la línea: el borde de la caja a la altura de su primer renglón o, si la caja queda bajo el ancla, su borde de arriba
        const x0 = izq ? c - q.w : c, x1 = izq ? c : c + q.w;
        const lx = q.tapa ? Math.min(Math.max(q.x, x0 + 8), x1 - 8) - q.x : (izq ? x1 : x0) - q.x, ly = q.tapa ? t - q.y : t + 11 - q.y;
        if (el_.classList.contains('izq') !== izq) el_.classList.toggle('izq', izq);
        const clave = `${dx},${dy},${Math.round(lx)},${Math.round(ly)}`;
        if (el_.dataset.dxy !== clave) {
          el_.dataset.dxy = clave;
          el_.style.setProperty('--dx', `${dx}px`);
          el_.style.setProperty('--dy', `${dy}px`);
          el_.style.setProperty('--l', `${Math.hypot(lx, ly).toFixed(1)}px`);
          el_.style.setProperty('--a', `${((Math.atan2(ly, lx) * 180) / Math.PI).toFixed(1)}deg`);
        }
      });
    }
  }
  const enCuadro = () => {
    if (!dentro) return false;
    despejarLlamadas();
    if (kCuadro++ % 20) return false;
    let cambio = false;
    st.scene.traverse((o) => { if ((/arboles$/.test(o.name) || o.name === 'conexion') && o.visible) { o.visible = false; tapados.add(o); cambio = true; } });
    return cambio;
  };
  st.onFrame(enCuadro);
  cargado = cargar().catch((e) => { console.error('Modelo BIM:', e); estado('No se pudo armar el modelo.'); return false; });
  pintarTablas();
  return {
    async entrar(op) {
      if (dentro) return;
      dentro = true;
      ctx.exterior?.ocultar(true);
      poner(panel, elPanel); poner(hud, elHud); poner(ficha, elFicha);
      if (ctx.tarjeta) { ctx.tarjeta.hidden = false; poner(ctx.tablas, elTablas); }
      clip0 = engine.renderer.localClippingEnabled; engine.renderer.localClippingEnabled = true;
      polar0 = st.controls.maxPolarAngle;
      st.scene.add(grupo);
      st.invalidate(true);
      const ok = await cargado;
      if (!dentro) return;
      if (ok) {
        if (S.vista === 'cimentacion') terreno.poner(S.terreno);
        aplicar();
        if (primero) { primero = false; encuadrar(cajaTotal, { margen: 0.82 }); }
        if (op) this.irA(op);
      }
    },
    salir({ porUsuario = false } = {}) {
      if (!dentro) return;
      dentro = false;
      pararPlay();
      st.scene.remove(grupo);
      terreno?.restaurar();
      for (const o of etiquetas) { o.element.style.display = 'none'; }
      engine.renderer.localClippingEnabled = clip0;
      tapados.forEach((o) => { o.visible = true; }); tapados.clear();
      if (polar0 != null) st.controls.maxPolarAngle = polar0;
      sacar(panel); sacar(hud); sacar(ficha);
      if (ctx.tarjeta) { ctx.tarjeta.hidden = true; sacar(ctx.tablas); }
      ctx.exterior?.ocultar(false);
      st.invalidate(true);
      if (porUsuario) ctx.alSalir?.();
    },
    // «Ir a» desde otro modo o tarjeta: { elemento } o { refuerzo } o { interferencia }
    irA(op) {
      if (!op || !m3d) return;
      if (op.refuerzo) verRefuerzo(op.refuerzo);
      else if (op.interferencia) irAInterferencia(op.interferencia);
      else if (op.elemento) { const gi = giDe(op.elemento); if (gi != null) seleccionar(gi, { volar: true }); }
    },
    alReanudar() { st.invalidate(true); },
    alDetener() { pararPlay(); },
    dispose() {
      this.salir({ porUsuario: false });
      lienzo.removeEventListener('pointerdown', alBajar); lienzo.removeEventListener('pointerup', alSubir);
      const k = st.frameFns.indexOf(enCuadro); if (k >= 0) st.frameFns.splice(k, 1);
      sinTema();
      quitarEtiquetas();
      limpiarRefuerzo();
      ref3d?.dispose();
      m3d?.dispose(); terreno?.dispose();
    },
    // ganchos de QA (y de los botones de la vista: hacen lo mismo)
    listo: () => cargado,
    estado: () => ({
      cargado: !!m3d, elementos: L.length, vista: S.vista, pestana: S.pest, corte: S.corte ? { ...S.corte } : null, terreno: terreno?.modo() ?? null,
      seleccion: S.sel >= 0 ? L[S.sel].e.id : null, visibles: m3d ? L.reduce((s, _, gi) => s + (m3d.E.esVisible(gi) ? 1 : 0), 0) : 0,
      refuerzo: S.refuerzo ? { hosts: [...S.refuerzo.hosts], eje: S.refuerzo.eje, ...resumenRef(), instancias: ref3d?.tramos() ?? 0 } : null,
      tapa: m3d?.tapa() ? m3d.tapa().geometry.attributes.position.count / 3 : 0, colores: S.colores ? { campo: S.colores.campo, coloreados: S.colores.conColor, rotulas: S.colores.rotulas, dc_max: S.colores.top[0]?.[1] ?? null } : null,
      avance: S.avance && S.fecha != null ? { ...S.avance } : null, etiquetas: [...etiquetas].filter((o) => o.parent && o.element.style.display !== 'none').length,
      triangulos: m3d ? m3d.triangulos() : 0, despiece: !!$(elFicha, '.bd svg'), ficha: $(elFicha, 'h4')?.textContent || null,
      seccionesBarras: ref3d?.secciones() ?? 0, aislados: S.aislados ? S.aislados.size : 0, leyenda: !$(elHud, '[data-b="ley"]').hidden, rotulo: $(elHud, '[data-b="chip"]').hidden ? null : $(elHud, '[data-b="chip"]').textContent,
    }),
    seleccionar: (id) => { const gi = giDe(id); if (gi == null) return false; seleccionar(gi, { volar: true }); return true; },
    pestana, verRefuerzo, refuerzoEje, salirRefuerzo, cortarNivel, cortarEje, quitarCorte, corteElemento, cimentacion, comportamiento, quitarComportamiento,
    color5D, fecha4D: (iso) => fecha4D(iso == null ? null : Date.parse(`${iso}T12:00:00`)), irAInterferencia, buscar, modoDisciplina, mostrarTodo, vistaRapida,
    depurar: () => (qs.has('qa') ? { m3d, grupo, st, ref3d, renderer: engine.renderer } : null),
    seVe: (id, op) => seVe(id, op || {}), suelo: () => sueloQA(),
    urlIFC: () => (IDX?.ifc || []).map((f) => new URL(`../../../${f.url}`, import.meta.url).href),
    bloquePorClick: (x, y) => { const r = lienzo.getBoundingClientRect(); ptr.set(((x - r.left) / r.width) * 2 - 1, -((y - r.top) / r.height) * 2 + 1); ray.setFromCamera(ptr, st.camera); const h = m3d?.pick(ray); return h ? L[h.gi].e.id : null; },
    proyectar: (id) => { const gi = giDe(id); if (gi == null) return null; const b = m3d.caja(gisDe(gi)), c = b.getCenter(new THREE.Vector3()).project(st.camera), r = lienzo.getBoundingClientRect(); return [r.left + ((c.x + 1) / 2) * r.width, r.top + ((1 - c.y) / 2) * r.height]; },
  };
}
