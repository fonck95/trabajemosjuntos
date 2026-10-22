// Escena 3D y fichas de la torre de servicios de primer nivel de la E.S.E. Hospital Héctor Abad Gómez, sobre el sitio del
// antiguo Centro Vida (alas occidentales del predio, que se demuelen). Modos: "Hoy" (las alas), "Con la torre" (el modelo
// generado desde data/edificios/torre_hospital.json), "Pisos por servicio" (los cuatro pisos separados, cada servicio con su
// color de grupo de la Res. 1633 de 2025 y su área) y "Laboratorio" (el piso 2 con mesones y analizadores).
// Los datos del proyecto (programa, norma, dotación, laboratorio, presupuesto, APU, financiación y proyectos) vienen de
// data/proyectos/torre_hospital/ y se cargan aparte (data/torre.json) al abrir la vista.
import { THREE, Stage, tokens, onTheme, mat, fmtN, fmtCOP, gsap, solidBox } from '../core.js';
import { progressiveLOD } from '../assets.js';
import { EDIFICIOS } from '../data.js';

// grupos de servicio con sus colores de señalización (Res. 1633 de 2025): rojo urgencias, naranja consulta, amarillo apoyo
// diagnóstico y terapéutico, azul internación, verde esterilización, violeta administración, café servicios generales
const GRUPOS = [
  [/urgenc|reanim|expansi/i, '#d62828', 'Urgencias'],
  [/hospitaliz|parto|interna|obst/i, '#2f6db3', 'Internación'],
  [/esteriliz/i, '#2a9d8f', 'Esterilización'],
  [/laborat|muestra|im[aá]gen|rayos|ecograf|farmac|citolog/i, '#e3a91c', 'Apoyo diagnóstico y terapéutico'],
  [/consulta|odonto|terap|telemed|telesal|psicol|nutri|vacun|promoci/i, '#f08a00', 'Consulta y ambulatorio'],
  [/vest[ií]bulo|admisi|coordin|administ|crisis/i, '#7b5ea7', 'Administración y acceso'],
  [/apoyo|t[eé]cnic|general|ducto/i, '#8d6e63', 'Servicios generales'],
];
const grupo = (n) => GRUPOS.find(([re]) => re.test(n)) || [null, '#9aa0a6', 'Otros'];
const XW = [-13.0, 3.1], XN = [3.1, 9.0];            // franja de servicios y franja del núcleo (marco de la especificación)
const YP = (piso) => (piso === 4 ? [-7.6, 22.4] : [-19.6, 22.4]);
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const cop = (v) => (v == null || Number.isNaN(+v) ? '—' : fmtCOP(+v));

export function mount(root) {
  const el = root.querySelector('.stage');
  const st = new Stage(el, { cam: [-78, 52, 70], target: [-2, 7, -2], fov: 36, minDist: 6, maxDist: 500, tone: 'aces', exposure: 1.05, fit: 0.85, declutter: ['lbl-node'] });
  const T = tokens(), S = st.scene;
  const sc = st.sunLight.shadow.camera; Object.assign(sc, { left: -90, right: 90, top: 90, bottom: -90, near: 1, far: 400 });
  st.sunLight.position.set(60, 120, 40); st.sunLight.shadow.mapSize.set(2048, 2048);
  const ground = new THREE.Mesh(new THREE.CircleGeometry(260, 64), mat(T.ground)); ground.rotation.x = -Math.PI / 2; ground.position.y = -0.06; ground.receiveShadow = true; S.add(ground); st.freeze(ground);

  // modelos: la torre (marco de su especificación) y el hospital actual como contexto, en su posición real relativa
  const TOR = EDIFICIOS.find((e) => e.id === 'torre_hospital'), HOS = EDIFICIOS.find((e) => e.id === 'hospital');
  const off = (e) => [(e.lon - TOR.lon) * 111320 * Math.cos((TOR.lat * Math.PI) / 180), (e.lat - TOR.lat) * 111320];
  let torre = null, modo = 'torre';
  const gTorre = new THREE.Group(); S.add(gTorre);
  if (TOR?.archivo) {
    torre = progressiveLOD([{ url: TOR.archivo, distance: 0 }, { url: TOR.archivo_lod1, distance: 420 }], () => { aplicar(false); st.updateShadows(); encuadre(); });
    gTorre.add(torre);
  }
  if (HOS?.archivo && TOR) {
    const [hx, hy] = off(HOS), g = new THREE.Group(); g.position.set(hx, 0, -hy); S.add(g);
    g.add(progressiveLOD([{ url: HOS.archivo, distance: 0 }, { url: HOS.archivo_lod1, distance: 300 }], (lod) => {
      // del hospital actual solo se ve el edificio (sus paneles y equipos son de otro proyecto)
      lod.traverse((o) => { if (o.name === 'adecuaciones') o.visible = false; });
      st.updateShadows();
    }));
  }
  const encuadre = () => { if (!torre) return; st.frameBox(solidBox(torre), new THREE.Vector3(-0.75, 0.55, 0.62), { margin: 0.78, duration: 1.4 }); };

  // pisos por servicio (se arman cuando llega data/torre.json)
  const gPisos = new THREE.Group(); gPisos.visible = false; S.add(gPisos);
  const pisos = [], zonas = [], labLab = [];
  let D = null, sep = 0, selPiso = null;

  function aplicar(anim = true) {
    if (torre) torre.traverse((o) => {
      if (o.userData.demoler) o.visible = modo === 'hoy';
      if (o.name === 'adecuaciones') o.visible = modo === 'torre';
    });
    const conPisos = modo === 'pisos' || modo === 'laboratorio';
    gPisos.visible = conPisos;
    etiquetas();
    zonas.forEach((z) => { const on = modo !== 'laboratorio' || z.lab; z.mesh.material.opacity = on ? 1 : 0.18; z.mesh.material.transparent = !on; z.mesh.material.depthWrite = on; });
    const meta = conPisos ? (modo === 'laboratorio' ? 2.2 : 1) : 0;
    if (gsap && anim) gsap.to({ v: sep }, { v: meta, duration: 1.1, ease: 'power3.inOut', onUpdate() { sep = this.targets()[0].v; apilar(); } });
    else { sep = meta; apilar(); }
    st.updateShadows();
  }
  // etiquetas: en «Pisos» el título de cada piso, los servicios grandes y todos los del piso elegido; en «Laboratorio», sus equipos
  function etiquetas() {
    const conPisos = modo === 'pisos' || modo === 'laboratorio';
    pisos.forEach((p) => { p.tit.visible = conPisos && (modo === 'pisos' || p.piso === 2); });
    zonas.forEach((z) => { z.label.visible = conPisos && (modo === 'pisos' ? z.m2 >= 90 || selPiso === z.piso : z.lab && z.piso === 2); });
    labLab.forEach((l) => { l.visible = modo === 'laboratorio'; });
    st.invalidate();
  }
  function apilar() {
    pisos.forEach((p, i) => { p.g.position.y = p.nivel + sep * 4.5 * i; });
    st.invalidate(true);
  }

  function armarPisos(prog) {
    const mPlaca = mat(new THREE.Color('#e9e8e3'), { roughness: 0.9 }), mNucleo = mat(new THREE.Color('#b9b7b1'), { roughness: 0.8 });
    (prog.resumen_por_piso || []).forEach((p) => {
      const piso = +p.piso, [y0, y1] = YP(piso), L = y1 - y0, g = new THREE.Group();
      const placa = new THREE.Mesh(new THREE.BoxGeometry(XN[1] - XW[0] + 1.2, 0.35, L + 1.2), mPlaca);
      placa.position.set((XW[0] + XN[1]) / 2, 0.175, -(y0 + y1) / 2); placa.castShadow = placa.receiveShadow = true; g.add(placa);
      const nuc = new THREE.Mesh(new THREE.BoxGeometry(XN[1] - XN[0], 2.6, L - 0.4), mNucleo);
      nuc.position.set((XN[0] + XN[1]) / 2, 0.35 + 1.3, -(y0 + y1) / 2); nuc.castShadow = true; g.add(nuc);
      // franjas de servicio de norte a sur, proporcionales a su área útil
      const serv = Object.entries(p.m2_util_por_servicio || {}).filter(([, v]) => v > 0);
      const tot = serv.reduce((a, [, v]) => a + v, 0) || 1;
      let y = y1;
      serv.forEach(([nombre, m2]) => {
        const l = (L * m2) / tot, [, col] = grupo(nombre), yc = y - l / 2;
        const m = new THREE.Mesh(new THREE.BoxGeometry(XW[1] - XW[0] - 0.3, 2.2, Math.max(0.6, l - 0.3)), mat(new THREE.Color(col), { roughness: 0.6 }));
        m.position.set((XW[0] + XW[1]) / 2, 0.35 + 1.1, -yc); m.castShadow = m.receiveShadow = true; g.add(m);
        const label = st.label(`<b>${esc(nombre)}</b><br><small>${fmtN(m2, 0)} m² útiles</small>`, 'lbl-node', [XW[0] - 0.5, 3.4, -yc], g);
        zonas.push({ mesh: m, piso, nombre, m2, label, lab: /laborat/i.test(nombre), y0: y - l, y1: y });
        y -= l;
      });
      const tit = st.label(`<b>Piso ${piso}</b><br><small>${fmtN(p.m2_construido, 0)} m² · entrepiso ${fmtN(p.altura_entrepiso_m, 1)} m</small>`, 'lbl-node', [XN[1] + 1, 2.4, -(y0 + y1) / 2], g);
      g.position.y = +p.nivel_piso_terminado_m || 0;
      gPisos.add(g);
      st.pickable(g, { onPick: () => fichaPiso(p) });
      pisos.push({ piso, g, tit, nivel: +p.nivel_piso_terminado_m || 0 });
    });
    armarLaboratorio();
    aplicar(false);
  }

  // mesones y equipos del laboratorio (piso 2), en la franja del laboratorio
  function armarLaboratorio() {
    const z = zonas.find((q) => q.lab && q.piso === 2), p2 = pisos.find((p) => p.piso === 2);
    if (!z || !p2 || !D?.laboratorio?.equipos?.length) return;
    const g = new THREE.Group(); p2.g.add(g);
    const mMeson = mat(new THREE.Color('#f4f4f2'), { roughness: 0.4 }), mEq = mat(new THREE.Color('#dfe3e6'), { roughness: 0.35, metalness: 0.1 });
    const mPant = mat(new THREE.Color('#1f2a33'), { roughness: 0.3, emissive: new THREE.Color('#2b6cb0'), emissiveIntensity: 0.25 });
    const x0 = XW[0] + 0.8, x1 = XW[1] - 0.8, len = z.y1 - z.y0 - 1.2;
    for (const xm of [x0 + 0.4, x1 - 0.4, (x0 + x1) / 2]) {
      const mz = new THREE.Mesh(new THREE.BoxGeometry(0.75, 0.9, len), mMeson); mz.position.set(xm, 0.35 + 2.2 + 0.45, -(z.y0 + z.y1) / 2); mz.castShadow = true; g.add(mz);
    }
    // un equipo por unidad, en orden de costo; los grandes de piso (neveras, cabinas) van aparte con su alto
    const eqs = [...D.laboratorio.equipos].sort((a, b) => (b.precio || 0) - (a.precio || 0));
    let k = 0;
    const slots = Math.max(1, Math.floor(len / 1.1)) * 3;
    eqs.forEach((e) => {
      for (let u = 0; u < Math.min(4, +e.cantidad || 1) && k < slots; u++, k++) {
        const fila = k % 3, pos = Math.floor(k / 3), xm = [x0 + 0.4, x1 - 0.4, (x0 + x1) / 2][fila], yz = z.y1 - 1.0 - pos * 1.1;
        const alto = /nevera|refriger|congel|cabina|incubad/i.test(e.nombre) ? 1.6 : /microsc|centr[ií]f|ba[nñ]o|pipet/i.test(e.nombre) ? 0.35 : 0.6;
        const caja = new THREE.Mesh(new THREE.BoxGeometry(0.62, alto, 0.7), mEq); caja.position.set(xm, 0.35 + 2.2 + 0.9 + alto / 2, -yz); caja.castShadow = true; g.add(caja);
        if (alto >= 0.6) { const pan = new THREE.Mesh(new THREE.BoxGeometry(0.02, 0.18, 0.28), mPant); pan.position.set(xm - 0.32, 0.35 + 2.2 + 0.9 + alto * 0.7, -yz); g.add(pan); }
        if (u === 0 && k < 18 && (e.precio || 0) > 20e6) {
          const l = st.label(`<b>${esc(e.nombre.split(/[,(]/)[0].split(' ').slice(0, 4).join(' '))}</b>${e.capacidad ? `<br><small>${esc(String(e.capacidad).slice(0, 40))}</small>` : ''}`, 'lbl-node', [xm, 0.35 + 2.2 + 0.9 + alto + 0.9, -yz], g);
          l.visible = false; labLab.push(l);
        }
      }
    });
  }

  // ---------------------------------------------------------------- fichas
  const q = (s) => root.querySelector(`[data-slot="torre.${s}"]`);
  const ficha = q('ficha');
  function fichaPiso(p) {
    selPiso = +p.piso; etiquetas();
    const amb = (D?.programa?.ambientes || []).filter((a) => String(a.piso) === String(p.piso));
    ficha.innerHTML = `<h4>Piso ${p.piso} · ${fmtN(p.m2_construido, 0)} m² construidos</h4>
      <p class="note">${esc(p.servicios)}</p>
      <details class="fold"><summary>Por qué va aquí</summary><p class="note">${esc(p.por_que)}</p></details>
      <div class="tbl-wrap"><table><thead><tr><th>Ambiente</th><th class="n">Cant.</th><th class="n">m²</th></tr></thead><tbody>
      ${amb.map((a) => `<tr><td><span class="dot" style="background:${grupo(a.servicio)[1]}"></span>${esc(a.nombre)}</td><td class="n">${fmtN(a.cantidad)}</td><td class="n">${fmtN(a.m2_total, 1)}</td></tr>`).join('')}
      </tbody></table></div>`;
    if (gsap) gsap.from(ficha, { opacity: 0, y: 8, duration: 0.3 });
  }

  const modeBtns = root.querySelectorAll('[data-modo-torre]');
  modeBtns.forEach((b) => b.addEventListener('click', () => {
    modo = b.dataset.modoTorre;
    modeBtns.forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    aplicar(true);
    if (modo === 'laboratorio') {
      const z = zonas.find((zz) => zz.lab && zz.piso === 2);
      if (z) setTimeout(() => st.closeUp(new THREE.Vector3((XW[0] + XW[1]) / 2, 4.5 + 2.2 * 4.5 + 3, -(z.y0 + z.y1) / 2), [], new THREE.Vector3(-1, 0, 0.3), { dist: 26, elev: 38 }), 350);
    } else if (modo === 'pisos') setTimeout(() => st.frameBox(new THREE.Box3(new THREE.Vector3(XW[0] - 8, 0, -24), new THREE.Vector3(XN[1] + 6, 32, 21)), new THREE.Vector3(-0.8, 0.45, 0.55), { margin: 0.85 }), 200);
    else encuadre();
  }));

  fetch(new URL('../../data/torre.json', import.meta.url)).then((r) => (r.ok ? r.json() : null)).then((d) => {
    if (!d) return;
    D = d;
    if (d.programa) armarPisos(d.programa);
    pintarFichas(d);
  }).catch((e) => console.warn('torre.json', e));

  function pintarFichas(d) {
    const pr = d.programa || {}, tot = pr.totales || {}, dot = d.dotacion?.totales_generales || {}, pres = d.presupuesto || {};
    const cap = (pr.capacidad_resultante?.tabla || []);
    const camas = cap.find((c) => /cama/i.test(c.recurso) && !/observ/i.test(c.recurso));
    const consult = cap.find((c) => /consultorios de consulta/i.test(c.recurso));
    const total = pres.totales?.total_torre ?? pres.totales?.total_cop_2026 ?? pres.total_cop_2026;
    q('tiles').innerHTML = `<div class="tile"><b>${fmtN(tot.m2_construido_torre || 0, 0)}</b><span>m² construidos en ${(pr.resumen_por_piso || []).length} pisos</span></div>
      <div class="tile"><b>${camas ? esc(camas.torre) : '—'}</b><span>camas${consult ? ` · ${esc(consult.torre)} consultorios` : ''}</span></div>
      <div class="tile"><b>${cop(dot.total_general_cop_2026)}</b><span>dotación y equipamiento</span></div>
      <div class="tile"><b>${total ? cop(total) : 'en cálculo'}</b><span>costo total del proyecto</span></div>`;
    // programa por piso
    q('pisos').innerHTML = `<p class="note">${esc(pr.resumen || '')}</p><table><thead><tr><th>Piso</th><th>Servicios</th><th class="n">m² útiles</th><th class="n">m² construidos</th></tr></thead><tbody>
      ${(pr.resumen_por_piso || []).map((p) => `<tr><td>${p.piso}</td><td>${esc(p.servicios)}</td><td class="n">${fmtN(p.m2_util, 0)}</td><td class="n">${fmtN(p.m2_construido, 0)}</td></tr>`).join('')}
      <tr><td></td><td><b>Total torre</b></td><td class="n">${fmtN(tot.m2_util_torre || 0, 0)}</td><td class="n"><b>${fmtN(tot.m2_construido_torre || 0, 0)}</b></td></tr></tbody></table>
      ${cap.length ? `<h4 style="margin-top:12px">Capacidad hoy y con la torre</h4><table><thead><tr><th>Recurso</th><th class="n">Hoy</th><th class="n">Torre</th></tr></thead><tbody>${cap.map((c) => `<tr><td>${esc(c.recurso)}</td><td class="n">${esc(c.actual)}</td><td class="n">${esc(c.torre)}</td></tr>`).join('')}</tbody></table>` : ''}
      <p class="note">${esc(pr.uso_del_edificio_actual?.resumen || (typeof pr.uso_del_edificio_actual === 'string' ? pr.uso_del_edificio_actual : ''))}</p>`;
    // norma
    const no = d.normas || {}, ch = no.checklist_485 || [];
    const estados = ch.reduce((a, c) => ((a[c.estado || 'pendiente'] = (a[c.estado || 'pendiente'] || 0) + 1), a), {});
    q('norma').innerHTML = `<p class="note">${esc(no.proyecto_en_breve?.tipologia_res_485 || '')}</p>
      <p>${Object.entries(estados).map(([k, v]) => `<span class="pill">${esc(k)}: ${v}</span>`).join(' ')} de ${ch.length} requisitos del concepto técnico de viabilidad.</p>
      <ol class="tight checklist">${ch.map((c) => `<li><b>${esc(c.numeral)}</b> ${esc(c.requisito)}<br><small class="note">${esc(c.documento_a_producir || '')}${c.responsable ? ` · ${esc(c.responsable)}` : ''}</small></li>`).join('')}</ol>
      <details class="fold"><summary>Normas que aplican (${(no.normas || []).length})</summary><ul class="tight">${(no.normas || []).map((n) => `<li>${n.url ? `<a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.numero)} de ${n.anio}</a>` : `${esc(n.numero)} de ${n.anio}`}: ${esc(String(n.objeto || '').slice(0, 220))}</li>`).join('')}</ul></details>`;
    // dotación
    const dd = d.dotacion || {};
    q('dotacion').innerHTML = `<p class="note">${esc(dd.resumen || '')}</p>
      <table><thead><tr><th>Servicio</th><th class="n">Piso</th><th class="n">Ítems</th><th class="n">Total</th></tr></thead><tbody>
      ${(dd.servicios || []).map((s) => `<tr><td><details class="fold"><summary>${esc(s.nombre)}</summary><ul class="tight">${(s.equipos || []).map((e) => `<li>${fmtN(e.cantidad)} × ${esc(e.nombre)}${e.total_cop_2026 ? ` — ${cop(e.total_cop_2026)}` : ''}${e.clase_riesgo ? ` <small class="note">(clase ${esc(e.clase_riesgo)})</small>` : ''}</li>`).join('')}</ul></details></td><td class="n">${esc(s.piso)}</td><td class="n">${fmtN(s.totales?.numero_de_items ?? (s.equipos || []).length)}</td><td class="n">${cop(s.totales?.total_cop_2026)}</td></tr>`).join('')}
      <tr><td>Equipamiento fijo e industrial (planta, ascensores, gases, aire, autoclave…)</td><td></td><td class="n">${(dd.equipamiento_fijo || []).length}</td><td class="n">${cop(dot.equipamiento_fijo_e_industrial_cop_2026)}</td></tr>
      <tr><td><b>Total dotación, mobiliario y equipamiento</b></td><td></td><td></td><td class="n"><b>${cop(dot.total_general_cop_2026)}</b></td></tr></tbody></table>
      ${dot.rango_total_general_cop_2026 ? `<p class="note">Rango: ${cop(dot.rango_total_general_cop_2026[0])} a ${cop(dot.rango_total_general_cop_2026[1])}. Sin posibles dobles conteos con la obra: ${cop(dot.total_general_sin_posible_doble_conteo_cop_2026)}.</p>` : ''}`;
    // laboratorio
    const la = d.laboratorio || {}, tm = la.totales_menu || {};
    const tr = (t) => (t ? ['urgencias', 'rutina', 'tamizaje'].map((k) => (t[k] ? `<small><b>${k}</b> ${esc(t[k])}</small>` : '')).filter(Boolean).join('<br>') : '');
    q('laboratorio').innerHTML = `<p class="note">${esc(la.resumen || '')}</p>
      <div class="tiles"><div class="tile"><b>${fmtN(tm.pruebas_en_sitio_mes || 0)}</b><span>pruebas al mes en sitio</span></div><div class="tile"><b>${(la.menu || []).length}</b><span>pruebas en el menú, con tiempos de respuesta</span></div></div>
      <details class="fold" open><summary>Menú de pruebas y tiempos de respuesta</summary><div class="tbl-wrap"><table><thead><tr><th>Prueba</th><th>Sección · equipo</th><th>Tiempo de respuesta</th><th class="n">Al mes</th></tr></thead><tbody>
      ${(la.menu || []).map((m) => `<tr><td>${esc(m.prueba)}</td><td><small>${esc(m.seccion)} · ${esc(m.equipo)}</small></td><td>${tr(m.tiempo_respuesta)}</td><td class="n">${fmtN(m.volumen_mes || 0)}</td></tr>`).join('')}
      </tbody></table></div></details>
      <details class="fold"><summary>Equipos del laboratorio (${(la.equipos || []).length})</summary><ul class="tight">${(la.equipos || []).map((e) => `<li>${fmtN(e.cantidad)} × ${esc(e.nombre)}${e.capacidad ? ` — ${esc(e.capacidad)}` : ''}${e.uso_pico_pct != null ? ` <small class="note">(uso en hora pico ${fmtN(e.uso_pico_pct, 0)} %)</small>` : ''}${e.modelo_de_compra ? ` <small class="note">· ${esc(e.modelo_de_compra)}</small>` : ''}</li>`).join('')}</ul></details>`;
    // proyecto tipo
    const pt = d.proyecto_tipo || {};
    q('tipo').innerHTML = `<p>${esc(pt.respuesta_corta || '')}</p>
      ${pt.seleccion?.por_que ? `<ul class="tight">${pt.seleccion.por_que.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}
      ${pt.estetica?.propuesta ? `<p class="note"><b>Estética:</b> ${esc(pt.estetica.propuesta)}</p>` : ''}
      <details class="fold"><summary>Proyectos tipo revisados (${(pt.proyectos_tipo || []).length})</summary><ul class="tight">${(pt.proyectos_tipo || []).map((p) => `<li>${p.url ? `<a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.nombre)}</a>` : esc(p.nombre)} <small class="note">${esc(p.fecha || '')}</small></li>`).join('')}</ul></details>`;
    pintarPresupuesto(d);
    // leyenda de grupos de servicio
    q('leyenda').innerHTML = GRUPOS.map(([, c, n]) => `<span><i style="background:${c}"></i>${n}</span>`).join('');
  }

  // presupuesto, APU, financiación y proyectos (si ya están calculados)
  function pintarPresupuesto(d) {
    const pres = d.presupuesto, apu = d.apu, fin = d.financiacion, pro = d.proyectos;
    const pend = '<p class="note">En cálculo: el presupuesto, los APU, la financiación y los proyectos se publican cuando terminen de verificarse.</p>';
    q('presupuesto').innerHTML = pres ? renderPresupuesto(pres) : pend;
    q('apu').innerHTML = apu ? renderAPU(apu) : pend;
    q('financiacion').innerHTML = fin ? renderFinanciacion(fin) : pend;
    q('proyectos').innerHTML = pro ? renderProyectos(pro) : pend;
    const sel = q('apu').querySelector('select');
    if (sel) sel.addEventListener('change', () => { q('apu').querySelector('[data-apu]').innerHTML = detalleAPU(apu.apus[+sel.value]); });
  }
  const num = (o, ...k) => { for (const x of k) if (o?.[x] != null && !Number.isNaN(+o[x])) return +o[x]; return null; };
  const nom = (o) => o?.nombre || o?.capitulo || o?.item || o?.descripcion || o?.insumo || o?.cuadrilla || '';
  const ETQ = { costo_directo_obra: 'Costo directo de la obra', valor_obra_con_aiu: 'Obra con AIU', indirectos_y_otros_componentes: 'Estudios, interventoría, dotación, laboratorio, TIC y contingencias', total_torre: 'Total de la torre', total_con_proyectos_complementarios: 'Con la adecuación del edificio actual y la ambulancia' };
  function renderPresupuesto(p) {
    const caps = p.capitulos || [], tots = caps.map((c) => num(c, 'subtotal_con_aiu', 'subtotal_costo_directo', 'total') ?? 0), max = Math.max(1, ...tots);
    const t = p.totales || {}, m2 = p.costo_m2 || {}, ig = p.indirectos_por_grupo || {};
    return `${p.resumen ? `<p class="note">${esc(p.resumen)}</p>` : ''}
      <p class="note">Capítulos con AIU; los ítems van a costo directo (cantidad × valor unitario) y cada uno dice de dónde sale su cantidad y su precio.</p>
      <div class="barras">${caps.map((c, i) => `<details class="fold"><summary><span class="bar-l">${esc(c.codigo ? `${c.codigo}. ` : '')}${esc(nom(c))}${c.peso_pct != null ? ` <small class="note">(${fmtN(c.peso_pct, 1)} %)</small>` : ''}</span><span class="bar"><i style="width:${(100 * tots[i]) / max}%"></i></span><span class="bar-v">${cop(tots[i])}</span></summary>
      ${c.nota ? `<p class="note">${esc(c.nota)}</p>` : ''}
      <div class="tbl-wrap"><table><thead><tr><th>Ítem</th><th>Und.</th><th class="n">Cantidad</th><th class="n">Valor unitario</th><th class="n">Total (costo directo)</th></tr></thead><tbody>
      ${(c.items || []).map((it) => `<tr><td>${esc(it.codigo ? `${it.codigo} ` : '')}${esc(nom(it))}${it.supuesto_cantidad ? `<br><small class="note">${esc(it.supuesto_cantidad)}</small>` : ''}</td><td>${esc(it.unidad || '')}</td><td class="n">${fmtN(num(it, 'cantidad') ?? 0, 2)}</td><td class="n">${cop(num(it, 'valor_unitario_costo_directo', 'valor_unitario', 'precio_unitario'))}</td><td class="n">${cop(num(it, 'total_costo_directo', 'total', 'valor_total'))}</td></tr>`).join('')}
      </tbody></table></div></details>`).join('')}</div>
      ${Object.keys(ig).length ? `<h4>Otros componentes del proyecto</h4><dl class="kv">${Object.entries(ig).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${cop(v)}</dd>`).join('')}</dl>` : ''}
      <dl class="kv" style="margin-top:10px">${Object.entries(ETQ).filter(([k]) => t[k] != null).map(([k, n]) => `<dt>${k === 'total_torre' ? `<b>${n}</b>` : n}</dt><dd>${k === 'total_torre' ? `<b>${cop(t[k])}</b>` : cop(t[k])}</dd>`).join('')}
        ${t.rango_total_torre ? `<dt>Rango del total</dt><dd>${cop(t.rango_total_torre[0])} a ${cop(t.rango_total_torre[1])}</dd>` : ''}
        ${m2.costo_total_por_m2_construido_total ? `<dt>Costo total por m² construido (${fmtN(m2.area_construida_total_m2, 1)} m²)</dt><dd>$${fmtN(m2.costo_total_por_m2_construido_total, 0)}</dd><dt>Obra con AIU por m² construido</dt><dd>$${fmtN(m2.valor_obra_por_m2_construido_total, 0)}</dd>${m2.obra_civil_sin_equipamiento_fijo_ni_solar_por_m2_total ? `<dt>Obra civil y redes por m² (sin equipos fijos ni solar)</dt><dd>$${fmtN(m2.obra_civil_sin_equipamiento_fijo_ni_solar_por_m2_total, 0)}</dd>` : ''}` : ''}</dl>
      ${m2.nota ? `<p class="note">${esc(m2.nota.replace(/'obra_civil[^']*'/, '«Obra civil y redes por m²»'))}</p>` : ''}
      ${(p.comparacion || []).length ? `<details class="fold"><summary>Comparación con proyectos hospitalarios contratados o viabilizados (${p.comparacion.length})</summary><div class="tbl-wrap"><table><thead><tr><th>Proyecto</th><th class="n">m²</th><th class="n">Valor por m² (2026)</th><th>Frente a la torre</th></tr></thead><tbody>${p.comparacion.map((x) => { const u = String(x.fuente || x.url || '').match(/https?:\/\/\S+/)?.[0]; return `<tr><td>${esc(x.proyecto || x.referencia || x.nombre || '')}<br><small class="note">${esc(x.incluye || '')}${u ? ` · <a href="${esc(u)}" target="_blank" rel="noopener">fuente</a>` : ''}</small></td><td class="n">${x.area_m2 ? fmtN(x.area_m2, 0) : '—'}</td><td class="n">${x.costo_m2_cop_2026 ? `$${fmtN(x.costo_m2_cop_2026, 0)}` : '—'}</td><td><small>${esc(x.relacion_con_la_torre || '')}</small></td></tr>`; }).join('')}</tbody></table></div></details>` : ''}`;
  }
  function renderAPU(a) {
    const L = a.apus || [];
    if (!L.length) return '';
    return `${a.resumen ? `<p class="note">${esc(a.resumen)}</p>` : ''}<label class="apu-sel">Ítem <select>${L.map((x, i) => `<option value="${i}">${esc(x.id || '')} · ${esc(nom(x))} (${esc(x.unidad || '')})</option>`).join('')}</select></label><div data-apu>${detalleAPU(L[0])}</div>`;
  }
  function detalleAPU(x) {
    const tabla = (titulo, filas, cols) => (filas?.length ? `<h4>${titulo}</h4><div class="tbl-wrap"><table><thead><tr>${cols.map((c) => `<th${c[2] ? ' class="n"' : ''}>${c[0]}</th>`).join('')}</tr></thead><tbody>${filas.map((r) => `<tr>${cols.map((c) => `<td${c[2] ? ' class="n"' : ''}>${c[1](r)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>` : '');
    const ai = x.aiu || {};
    return `<p class="note">${esc(x.descripcion || '')}</p>
      ${tabla('Materiales', x.materiales, [['Insumo', (r) => esc(r.insumo || nom(r))], ['Und.', (r) => esc(r.unidad || '')], ['Cant.', (r) => fmtN(r.cantidad ?? 0, 3), 1], ['Desp. %', (r) => fmtN(r.desperdicio_pct ?? 0, 0), 1], ['Precio', (r) => cop(r.precio_unitario), 1], ['Valor', (r) => cop(r.valor), 1]])}
      ${tabla('Equipo', x.equipo, [['Equipo', (r) => esc(r.descripcion || nom(r))], ['Tarifa', (r) => `${cop(r.tarifa)}/${esc(r.unidad_tarifa || '')}`, 1], ['Cant.', (r) => fmtN(r.cantidad ?? 0, 3), 1], ['Valor', (r) => cop(r.valor), 1]])}
      ${tabla('Mano de obra', x.mano_obra || x.mano_de_obra, [['Cuadrilla', (r) => `${esc(r.cuadrilla || '')}<br><small class="note">${esc(r.composicion || '')}</small>`], ['Jornal con prestaciones', (r) => cop(r.jornal_con_prestaciones), 1], ['Rendimiento/día', (r) => fmtN(r.rendimiento_unidades_por_dia ?? 0, 1), 1], ['Valor', (r) => cop(r.valor), 1]])}
      <dl class="kv" style="margin-top:8px">
        ${x.herramienta_menor?.valor != null ? `<dt>Herramienta menor (${fmtN(x.herramienta_menor.porcentaje_de_mano_de_obra || 0, 0)} % de la mano de obra)</dt><dd>${cop(x.herramienta_menor.valor)}</dd>` : ''}
        ${x.transporte?.valor != null ? `<dt>Transporte</dt><dd>${cop(x.transporte.valor)}</dd>` : ''}
        <dt><b>Costo directo</b></dt><dd><b>${cop(x.costo_directo)}</b></dd>
        ${ai.administracion != null ? `<dt>Administración (${fmtN(ai.administracion_pct, 0)} %) · imprevistos (${fmtN(ai.imprevistos_pct, 0)} %) · utilidad (${fmtN(ai.utilidad_pct, 0)} %) · IVA sobre utilidad</dt><dd>${cop((ai.administracion || 0) + (ai.imprevistos || 0) + (ai.utilidad || 0) + (ai.iva_sobre_utilidad || 0))}</dd>` : ''}
        <dt><b>Precio unitario con AIU</b></dt><dd><b>${cop(x.precio_unitario_con_aiu)}</b> / ${esc(x.unidad || '')}</dd></dl>
      ${x.comparacion?.lectura ? `<p class="note"><b>Contraste:</b> ${esc(x.comparacion.lectura)}</p>` : ''}${x.uso_en_presupuesto ? `<p class="note"><b>Uso:</b> ${esc(x.uso_en_presupuesto)}</p>` : ''}`;
  }
  const CORTO_F = { sgr_ad: 'SGR directas de Yondó', sgr_ipaz: 'SGR incentivo OCAD Paz', sgr_ail: 'SGR inversión local', sgr_air: 'SGR inversión regional', sgr_ctei: 'SGR ciencia y tecnología', pgn_minsalud: 'MinSalud (PGN)', gobernacion: 'Gobernación de Antioquia', oxi: 'Obras por Impuestos', fenoge: 'FENOGE', mintic: 'MinTIC', municipio: 'Municipio', ese: 'E.S.E.', credito: 'Crédito Findeter', ecopetrol: 'Ecopetrol', cooperacion: 'Cooperación' };
  function renderFinanciacion(f) {
    const L = f.fuentes || [], totM = Object.values(f.mezcla_escenario_base || {}).reduce((a, v) => a + (+v || 0), 0) || 1;
    const nombre = (id) => CORTO_F[id] || (L.find((x) => x.id === id)?.nombre || id).split(/[–(]/)[0].trim();
    // las siete fuentes más grandes con color propio; el resto se agrupa en gris para que la barra se pueda leer
    const orden = Object.entries(f.mezcla_escenario_base || {}).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
    const cols = ['var(--s1)', 'var(--s2)', 'var(--s3)', 'var(--s4)', 'var(--s5)', 'var(--s6)', 'var(--s7)'];
    const resto = orden.slice(cols.length), seg = orden.slice(0, cols.length).map(([k, v], i) => [nombre(k), v, cols[i]]);
    if (resto.length) seg.push([`Otras ${resto.length}: ${resto.map(([k]) => nombre(k)).join(', ')}`, resto.reduce((a, [, v]) => a + v, 0), 'var(--muted)']);
    return `${f.resumen ? `<p class="note">${esc(f.resumen)}</p>` : ''}
      <div class="mezcla">${seg.map(([n, v, c]) => `<i title="${esc(n)}: ${cop(v)}" style="flex:${v};background:${c}"></i>`).join('')}</div>
      <ul class="tight mezcla-ley">${seg.map(([n, v, c]) => `<li><span class="dot" style="background:${c}"></span>${esc(n)}: <b>${cop(v)}</b> (${fmtN((100 * v) / totM, 0)} %)</li>`).join('')}</ul>
      <div class="tbl-wrap"><table><thead><tr><th>Fuente</th><th>Rango posible</th><th class="n">Escenario base</th><th>Probabilidad</th></tr></thead><tbody>${L.map((x) => `<tr><td><details class="fold"><summary>${esc(x.nombre)}</summary><p class="note">${esc(x.requisitos || '')}</p>${x.momento ? `<p class="note"><b>Cuándo:</b> ${esc(x.momento)}</p>` : ''}${x.proyectos_que_financia ? `<p class="note"><b>Financia:</b> ${esc([].concat(x.proyectos_que_financia).join(', '))}</p>` : ''}</details></td><td>${Array.isArray(x.monto_posible_rango) ? `${cop(x.monto_posible_rango[0])} a ${cop(x.monto_posible_rango[1])}` : ''}</td><td class="n">${cop(x.monto_central_escenario_base)}</td><td><small>${esc(String(x.probabilidad || '').split('(')[0])}</small></td></tr>`).join('')}</tbody></table></div>
      ${f.escenario_sin_pgn_lectura ? `<p class="note"><b>Sin MinSalud:</b> ${esc(f.escenario_sin_pgn_lectura)}</p>` : ''}`;
  }
  function renderProyectos(p) {
    const L = p.proyectos || [];
    const fecha = (s) => { const m = String(s || '').match(/(20\d\d)(?:-(\d\d))?/); return m ? +m[1] + ((+m[2] || 1) - 1) / 12 : null; };
    const A0 = Math.min(2026, ...L.map((x) => Math.floor(fecha(x.inicio) ?? 2026))), A1 = Math.max(2030, ...L.map((x) => Math.floor(fecha(x.fin) ?? 2030))), N = A1 - A0 + 1;
    const anios = Array.from({ length: N }, (_, i) => A0 + i), pct = (t) => ((t - A0) / N) * 100;
    const fuente = (s) => { const t = String(s || '').split(';')[0].trim(); return t.length > 120 ? `${t.slice(0, 117)}…` : t; };
    const mga = p.agrupacion_recomendada_fichas_mga;
    return `${p.respuesta_corta ? `<p>${esc(p.respuesta_corta)}</p>` : ''}<div class="gantt"><div class="gantt-head"><span></span><span class="g-bar" style="background-size:${100 / N}% 100%">${anios.map((a) => `<b style="left:${pct(a)}%">${a}</b>`).join('')}</span></div>
      ${L.map((x) => { const a = fecha(x.inicio) ?? A0, b = Math.max(a + 0.08, (fecha(x.fin) ?? a + 0.5) + 1 / 12); return `<details class="fold gantt-row"><summary><span class="g-n"><b>${esc(x.id || x.orden)}</b> ${esc(nom(x))}<br><small class="note">${cop(num(x, 'valor'))} · ${esc(fuente(x.fuente_financiacion))}</small></span><span class="g-bar" style="background-size:${100 / N}% 100%"><i title="${esc(`${x.inicio} a ${x.fin}`)}" style="left:${pct(a)}%;width:${pct(b) - pct(a)}%"></i></span></summary><p class="note">${esc(x.objeto || '')}</p><p class="note">${x.entidad ? `<b>Presenta:</b> ${esc(x.entidad)}<br>` : ''}${x.tipo_concepto_485 ? `<b>Concepto técnico:</b> ${esc(x.tipo_concepto_485)}<br>` : ''}${x.mga ? `<b>MGA:</b> ${esc(typeof x.mga === 'string' ? x.mga : JSON.stringify(x.mga))}<br>` : ''}${(x.dependencias || []).length ? `<b>Requiere:</b> ${esc([].concat(x.dependencias).join('; '))}` : ''}</p></details>`; }).join('')}</div>
      ${mga ? `<p class="note"><b>Fichas MGA (${Array.isArray(mga) ? mga.length : ''}):</b> ${esc(Array.isArray(mga) ? mga.map((g) => [].concat(g).join(' + ')).join(' · ') : typeof mga === 'string' ? mga : String(mga.resumen || '').slice(0, 600))}</p>` : ''}`;
  }

  onTheme((t) => { ground.material.color.copy(t.ground); });
  return st;
}
