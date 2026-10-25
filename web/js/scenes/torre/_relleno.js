// Relleno «en construcción» de la vista de la torre (equipo D, ola 0 de la especificación de integración, 12.1).
// torre.js carga cada módulo nuevo de forma perezosa con import('./torre/recorrido.js').catch(() => import('./torre/_relleno.js'))
// (lo mismo con sismo.js, bim.js, habilitacion.js y contraste.js): mientras el equipo dueño no suba su módulo, la vista usa este,
// que tiene las mismas firmas (6.2, 8.6 y 9.2), no dibuja nada en 3D salvo la placa del proyecto tipo y solo escribe en los
// contenedores que recibe. Cuando llegue el módulo real, este archivo deja de cargarse sin tocar torre.js.
export const RELLENO = true;

const AVISOS = {
  recorrido: ['Recorrer por dentro', 'Aquí se podrá entrar a la torre y caminar por los cuatro pisos y el bloque técnico, ambiente por ambiente, con la dotación de cada uno ubicada en 3D y su ficha. Mientras tanto, el modelo muestra la torre por fuera.'],
  sismo: ['Simulador sísmico', 'Aquí se podrá elegir un sismo (magnitud Mw, profundidad, distancia y suelo) y ver, paso a paso, cómo se deforma la estructura de la torre y cuánto se esfuerza cada columna, viga y muro. Mientras tanto, el modelo muestra la torre por fuera.'],
  bim: ['Modelo BIM', 'Aquí se podrá recorrer el modelo BIM de la torre por disciplinas (arquitectura, estructura, cimentación, refuerzo, redes y dotación), con cortes, la cimentación y el refuerzo de cada elemento, cantidades y costo (5D), cronograma (4D) y la descarga del archivo IFC. Mientras tanto, el modelo muestra la torre por fuera.'],
};
const caja = (titulo, texto) => `<h3>${titulo}</h3><p><span class="pill">en construcción</span></p><p class="note">${texto}</p>`;

// recorrido (6.2), simulador (8.6) o modelo BIM (17.5): el modo se deduce del contenedor del panel que trae el contexto
export async function montar(ctx) {
  const tipo = (ctx.panel?.dataset.slot || '').match(/\.(sismo|bim)$/)?.[1] || 'recorrido';
  const [titulo, texto] = AVISOS[tipo];
  let dentro = false;
  const mostrar = (on) => {
    if (ctx.panel) { ctx.panel.innerHTML = on ? caja(titulo, texto) : ''; ctx.panel.hidden = !on; }
    if (ctx.graficas) ctx.graficas.innerHTML = on ? '<p class="note">Las gráficas del cálculo (acelerograma, espectros, derivas por piso, cortante basal y balance de energía) aparecerán aquí cuando el simulador esté listo.</p>' : '';
  };
  return {
    relleno: true,
    entrar() { dentro = true; mostrar(true); },
    salir({ porUsuario = false } = {}) { if (!dentro) return; dentro = false; mostrar(false); if (porUsuario) ctx.alSalir?.(); },
    irA() {},
    alReanudar() {},
    capa() {},
    estado: () => null,
    libre: () => null,
    dispose() { mostrar(false); },
  };
}

// tarjeta «Dotación para la habilitación» (6.2)
export function pintarHabilitacion(el) {
  if (!el) return;
  el.innerHTML = `<p><span class="pill">en construcción</span></p><p class="note">Aquí irá, servicio por servicio, lo que pide la Res. 3100 de 2019 en dotación e infraestructura, qué equipos de la torre lo cubren y dónde quedan en el recorrido 3D. Esta revisión no incluye talento humano, historia clínica ni interdependencia: no dirá si un servicio se puede habilitar.</p>`;
}

// tarjeta «Contraste con el proyecto tipo» (9.2): mientras llega, se conserva el resumen que ya pinta torre.js y se agrega el aviso
export function pintarContraste(el) {
  if (!el || el.querySelector('[data-relleno]')) return;
  el.insertAdjacentHTML('beforeend', '<p class="note" data-relleno><span class="pill">en construcción</span> La comparación ambiente por ambiente, el costo por m² y la dotación frente al proyecto tipo se publican aquí cuando terminen de verificarse.</p>');
}
export function coloresRecintos() { return new Map(); }

// placa de un piso con el área del puesto de salud tipo del DNP (320,6 m²: 17,9 m de lado), centrada en el origen; su forma
// real está en el PDF del DNP, que no se pudo abrir (9.2)
export function modeloTipo3D(THREE) {
  const g = new THREE.Group(), lado = Math.sqrt(320.6), alto = 3.2;
  const caja3 = new THREE.BoxGeometry(lado, alto, lado);
  const vol = new THREE.Mesh(caja3, new THREE.MeshStandardMaterial({ color: '#6b8fb3', roughness: 0.8, transparent: true, opacity: 0.35, depthWrite: false }));
  vol.position.y = alto / 2;
  const borde = new THREE.LineSegments(new THREE.EdgesGeometry(caja3), new THREE.LineBasicMaterial({ color: '#2f4f6f' }));
  borde.position.y = alto / 2;
  g.add(vol, borde);
  g.userData.alto = alto;
  return g;
}
