// Catálogo 3D de equipos de la torre (equipo C; contrato de integración, secciones 5 y 16.5).
// Fábrica de modelos procedurales de bajo costo, hechos con cajas, cilindros y perfiles extruidos de three (sin texturas),
// para TODOS los «modelo3d» de la lista cerrada (Anexo C más los del 16.5) y una capa por piso para el recorrido y la vista
// sísmica: InstancedMesh por modelo, mallas fundidas con tabla de rangos para la selección, malla del recinto actual, malla
// fantasma del cierre de brechas y caja de resaltado.
//
// Convenciones (4.3 y 0): origen en el centro de la base; ancho en x local, fondo en y local, alto en z; la espalda (lo que
// va contra la pared o la cabecera) mira a −y local y el frente a +y local. Los modelos se arman en coordenadas de planta
// (x, y, z arriba) y al final pasan a three: (X, Y, Z) = (x, z, −y); un giro antihorario en planta θ es rotation.y = θ.
// Las medidas llegan del catálogo (dim_m); si el catálogo no trae un modelo, se usan las nominales del Anexo C y del 16.5.
// Un solo material opaco con colores por vértice para todo el equipo, uno transparente para vidrios y acrílicos y otro para
// las unidades fantasma (5.1). Las geometrías de cada pieza se normalizan antes de fundirlas (no indexadas, sin uv, con
// color y normales), así mergeGeometries nunca devuelve null.
import { THREE, onTheme, tokens } from './core.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

// ---------------------------------------------------------------- lista cerrada y medidas nominales
// [ancho, fondo, alto] en m, familia y montaje: Anexo C y 16.5 del contrato (estimación; las reemplaza el catálogo)
const NOMINAL = {
  cama_hospitalaria: [1, 2.2, 0.95, 'cama', 'piso'],
  cama_pediatrica: [0.9, 1.8, 1.1, 'cama', 'piso'],
  cuna_hospitalaria: [0.7, 1.3, 1.1, 'cama', 'piso'],
  cuna_acrilico: [0.5, 0.85, 0.95, 'cama', 'piso'],
  cuna_observacion: [0.65, 1.2, 1, 'cama', 'piso'],
  cama_partos: [0.95, 2.1, 1, 'cama', 'piso'],
  camilla_reanimacion: [0.75, 2.05, 0.95, 'camilla', 'piso'],
  camilla_observacion: [0.75, 2, 0.9, 'camilla', 'piso'],
  camilla_transporte: [0.7, 2, 0.95, 'camilla', 'piso'],
  camilla_procedimientos: [0.7, 1.95, 0.85, 'camilla', 'piso'],
  camilla_eda: [0.7, 1.9, 0.8, 'camilla', 'piso'],
  camilla_examen: [0.65, 1.85, 0.75, 'camilla', 'piso'],
  camilla_ginecologica: [0.65, 1.85, 0.85, 'camilla', 'piso'],
  camilla_ecografia: [0.7, 1.9, 0.7, 'camilla', 'piso'],
  camilla_terapia: [0.7, 1.9, 0.7, 'camilla', 'piso'],
  camilla_plegable: [0.6, 1.9, 0.6, 'camilla', 'piso'],
  sillon_reclinable: [0.75, 0.95, 1.1, 'asiento', 'piso'],
  sillon_toma_muestras: [0.7, 0.9, 1.2, 'asiento', 'piso'],
  silla_ruedas: [0.65, 1.05, 0.9, 'asiento', 'piso'],
  tandem_4: [2.3, 0.65, 0.8, 'asiento', 'piso'],
  silla_trabajo: [0.6, 0.6, 0.95, 'asiento', 'piso'],
  silla_laboratorio: [0.5, 0.5, 0.95, 'asiento', 'piso'],
  puesto_trabajo: [1.2, 1.6, 0.75, 'mueble', 'piso'],
  escritorio: [1.2, 0.6, 0.75, 'mueble', 'piso'],
  mueble_recepcion: [3, 0.8, 1.1, 'mueble', 'piso'],
  estacion_enfermeria: [3, 1.6, 1.1, 'mueble', 'piso'],
  meson: [1.5, 0.7, 0.9, 'mueble', 'piso'],
  mueble_bajo: [1.2, 0.6, 0.9, 'mueble', 'piso'],
  vitrina: [0.9, 0.4, 1.8, 'mueble', 'piso'],
  estanteria: [1, 0.45, 2, 'mueble', 'piso'],
  lockers_6: [0.9, 0.5, 1.8, 'mueble', 'piso'],
  gabinete_seguridad: [0.6, 0.5, 1.2, 'mueble', 'piso'],
  mesa_noche: [0.45, 0.45, 0.8, 'mueble', 'piso'],
  mesa_puente: [0.9, 0.45, 0.95, 'mueble', 'piso'],
  mesa_mayo: [0.5, 0.35, 1.1, 'mueble', 'piso'],
  mesa_auxiliar: [0.6, 0.45, 0.85, 'mueble', 'piso'],
  riel_cortina: [2.4, 0.05, 2.2, 'mueble', 'cielo'],
  escalerilla: [0.4, 0.5, 0.45, 'mueble', 'piso'],
  estiba: [1.2, 1, 0.15, 'mueble', 'piso'],
  canecas_residuos: [0.95, 0.35, 0.65, 'mueble', 'piso'],
  lavaojos_ducha: [0.6, 0.6, 2.2, 'mueble', 'piso'],
  barras_paralelas: [0.8, 3, 1, 'terapia', 'piso'],
  escalera_rehabilitacion: [0.9, 2.4, 1.4, 'terapia', 'piso'],
  banda_caminadora: [0.8, 2, 1.4, 'terapia', 'piso'],
  bicicleta_estatica: [0.55, 1.1, 1.3, 'terapia', 'piso'],
  espejo_postural: [0.9, 0.4, 1.9, 'terapia', 'piso'],
  kit_rehabilitacion: [1, 0.4, 1, 'terapia', 'piso'],
  compresero: [0.6, 0.45, 0.9, 'terapia', 'piso'],
  carro_paro: [0.75, 0.55, 1, 'carro', 'piso'],
  carro_curaciones: [0.6, 0.45, 0.9, 'carro', 'piso'],
  carro_medicamentos: [0.7, 0.5, 1, 'carro', 'piso'],
  carro_ropa: [0.8, 0.5, 1, 'carro', 'piso'],
  carro_cerrado: [0.9, 0.6, 1.2, 'carro', 'piso'],
  carro_equipo: [0.5, 0.5, 0.9, 'carro', 'piso'],
  atril: [0.55, 0.55, 2, 'carro', 'piso'],
  desfibrilador: [0.32, 0.27, 0.3, 'biomedico', 'sobre'],
  dea_gabinete: [0.4, 0.2, 0.45, 'biomedico', 'pared'],
  monitor_signos: [0.3, 0.18, 0.3, 'biomedico', 'pared'],
  electrocardiografo: [0.4, 0.35, 0.12, 'biomedico', 'sobre'],
  bomba_infusion: [0.15, 0.22, 0.25, 'biomedico', 'dentro'],
  ventilador_transporte: [0.3, 0.2, 0.3, 'biomedico', 'sobre'],
  aspirador_portatil: [0.35, 0.25, 0.35, 'biomedico', 'sobre'],
  toma_gases_pared: [0.1, 0.1, 0.25, 'biomedico', 'pared'],
  equipo_mesa: [0.3, 0.25, 0.15, 'biomedico', 'sobre'],
  estuche: [0.4, 0.25, 0.1, 'biomedico', 'dentro'],
  tabla_espinal: [0.45, 1.85, 0.06, 'biomedico', 'piso'],
  equipo_pared: [0.35, 0.1, 0.25, 'biomedico', 'pared'],
  lampara_rodable: [0.6, 0.6, 1.8, 'biomedico', 'piso'],
  lampara_cuello_cisne: [0.5, 0.5, 1.4, 'biomedico', 'piso'],
  lampara_cielitica: [0.7, 0.7, 1, 'biomedico', 'cielo'],
  bascula_pesabebes: [0.55, 0.35, 0.15, 'biomedico', 'sobre'],
  bascula_piso: [0.35, 0.35, 0.05, 'biomedico', 'piso'],
  infantometro: [0.3, 1, 0.15, 'biomedico', 'sobre'],
  servocuna: [1, 0.75, 1.8, 'neonatal', 'piso'],
  incubadora_neonatal: [1.1, 0.65, 1.45, 'neonatal', 'piso'],
  incubadora_transporte: [1.3, 0.6, 1.3, 'neonatal', 'piso'],
  fototerapia: [0.6, 0.6, 1.7, 'neonatal', 'piso'],
  monitor_fetal: [0.35, 0.3, 0.15, 'neonatal', 'sobre'],
  unidad_odontologica: [1.8, 2.2, 1.9, 'odontologia', 'piso'],
  compresor: [0.55, 0.45, 0.65, 'odontologia', 'piso'],
  rx_periapical: [0.4, 0.3, 0.6, 'odontologia', 'pared'],
  rayos_x_convencional: [4, 3, 2.2, 'imagenes', 'piso'],
  ecografo: [0.55, 0.85, 1.45, 'imagenes', 'piso'],
  proteccion_radiologica: [0.6, 0.3, 1.6, 'imagenes', 'pared'],
  monitor_escritorio: [0.55, 0.2, 0.45, 'tic', 'sobre'],
  computador_aio: [0.55, 0.2, 0.45, 'tic', 'sobre'],
  estacion_telemedicina: [1.2, 0.6, 1.3, 'tic', 'piso'],
  impresora: [0.4, 0.4, 0.3, 'tic', 'sobre'],
  rack: [0.6, 1, 2, 'tic', 'piso'],
  digiturno: [1.1, 0.1, 0.65, 'tic', 'pared'],
  microscopio: [0.25, 0.35, 0.45, 'laboratorio', 'sobre'],
  cabina_bioseguridad: [1.35, 0.8, 2.1, 'laboratorio', 'piso'],
  centrifuga_mesa: [0.45, 0.55, 0.35, 'laboratorio', 'sobre'],
  analizador_mesa: [0.6, 0.6, 0.6, 'laboratorio', 'sobre'],
  analizador_piso: [1.2, 0.8, 1.2, 'laboratorio', 'piso'],
  incubadora_lab: [0.6, 0.6, 0.8, 'laboratorio', 'piso'],
  ups: [0.25, 0.7, 0.5, 'laboratorio', 'piso'],
  nevera_vertical: [0.7, 0.75, 1.95, 'frio', 'piso'],
  nevera_media: [0.6, 0.65, 1.4, 'frio', 'piso'],
  nevera_bajo_meson: [0.6, 0.6, 0.85, 'frio', 'piso'],
  congelador_horizontal: [0.9, 0.65, 0.85, 'frio', 'piso'],
  refrigerador_vacunas: [1, 0.75, 0.95, 'frio', 'piso'],
  termo_vacunas: [0.35, 0.25, 0.35, 'frio', 'sobre'],
  caja_termica: [0.6, 0.45, 0.45, 'frio', 'piso'],
  autoclave_mesa: [0.45, 0.6, 0.4, 'esterilizacion', 'sobre'],
  autoclave_vertical: [0.6, 0.6, 1, 'esterilizacion', 'piso'],
  autoclave_central: [1, 1.4, 1.9, 'esterilizacion', 'piso'],
  lavadora_desinfectora: [0.65, 0.75, 1.85, 'esterilizacion', 'piso'],
  planta_electrica: [3.8, 1.4, 2, 'fijo', 'piso'],
  ups_central: [1.2, 0.9, 2, 'fijo', 'piso'],
  ascensor_cabina: [1.4, 2.4, 2.3, 'fijo', 'en_nucleo'],
  montacargas: [0.8, 0.8, 1, 'fijo', 'en_nucleo'],
  manifold_gases: [2.5, 0.5, 1.8, 'fijo', 'piso'],
  generador_psa: [2, 1.5, 2, 'fijo', 'piso'],
  equipo_presion: [1.5, 1, 1.2, 'fijo', 'piso'],
  tablero_sistema: [0.6, 0.25, 0.8, 'fijo', 'pared'],
  condensadora: [1, 0.8, 1.4, 'fijo', 'piso'],
  nevera_mortuoria: [2.3, 1, 1.6, 'fijo', 'piso'],
  lavamanos: [0.55, 0.45, 0.25, 'sanitario', 'pared'],
  lavamanos_quirurgico: [1.2, 0.55, 0.35, 'sanitario', 'pared'],
  inodoro: [0.4, 0.7, 0.8, 'sanitario', 'piso'],
  ducha: [0.9, 0.9, 2.1, 'sanitario', 'piso'],
  poceta_aseo: [0.6, 0.5, 0.6, 'sanitario', 'piso'],
  lavachatas: [0.55, 0.6, 1, 'sanitario', 'piso'],
  barra_apoyo: [0.8, 0.1, 0.05, 'sanitario', 'pared'],
  extintor: [0.25, 0.2, 0.6, 'seguridad', 'pared'],
  gabinete_incendio: [0.8, 0.25, 0.9, 'seguridad', 'pared'],
  senal_evacuacion: [0.35, 0.03, 0.18, 'seguridad', 'pared'],
  toma_gases_cabecera: [1.5, 0.12, 0.25, 'instalacion', 'pared'],
  llamado_enfermeria: [0.08, 0.04, 0.12, 'instalacion', 'pared'],
  transformador: [1.8, 1.4, 1.6, 'energia', 'piso'],
  tablero_electrico: [0.8, 0.4, 2, 'energia', 'piso'],
  banco_baterias: [1.2, 0.8, 2.1, 'energia', 'piso'],
  bomba_agua: [1, 0.6, 0.8, 'instalacion', 'piso'],
  tanque_agua: [2, 2, 1.8, 'instalacion', 'piso'],
  panel_solar_fila: [10, 2.3, 1.2, 'energia', 'piso'],
  caseta_cubierta: [5.5, 8.4, 3.3, 'exterior', 'piso'],
  baranda: [1, 0.05, 1.1, 'exterior', 'piso'],
  contenedor_residuos: [0.75, 0.6, 1.1, 'residuos', 'piso'],
  bascula_residuos: [0.8, 0.8, 0.1, 'residuos', 'piso'],
  ambulancia: [2, 5.4, 2.6, 'exterior', 'piso'],
  montacargas_muestras: [0.6, 0.6, 0.6, 'fijo', 'en_nucleo'],
  escalera_tramo: [1.2, 4.5, 2.1, 'fijo', 'piso'],
  reactivo_caja: [0.3, 0.2, 0.15, 'insumo', 'dentro'],
  frasco_reactivo: [0.08, 0.08, 0.15, 'insumo', 'dentro'],
  gradilla_tubos: [0.25, 0.1, 0.08, 'insumo', 'sobre'],
  pipeta_set: [0.3, 0.15, 0.3, 'insumo', 'sobre'],
};
// variantes con medidas propias (catálogo, «variantes»)
const VARIANTES = {
  camilla_plegable: { plegada: [0.6, 0.2, 1.9] },
  monitor_signos: { pedestal: [0.6, 0.6, 1.4] },
  proteccion_radiologica: { biombo: [0.8, 0.5, 1.9] },
  digiturno: { kiosco: [0.5, 0.5, 1.4] },
  centrifuga_mesa: { micro: [0.3, 0.35, 0.25] },
  meson: { poceta: null, inoxidable: null, gavetas: null, laboratorio: null },
  estanteria: { inoxidable: null },
  panel_solar_fila: { elevada: null },
  contenedor_residuos: { rojo: null, verde: null, negro: null, blanco: null, gris: null },
};

// Nombres para ciudadanos (fichas, QA). Las claves internas no se muestran en la web.
export const NOMBRES = {
  cama_hospitalaria: 'Cama hospitalaria', cama_pediatrica: 'Cama pediátrica', cuna_hospitalaria: 'Cuna hospitalaria', cuna_acrilico: 'Cuna de acrílico',
  cuna_observacion: 'Cuna de observación', cama_partos: 'Cama de partos', camilla_reanimacion: 'Camilla de reanimación', camilla_observacion: 'Camilla de observación',
  camilla_transporte: 'Camilla de transporte', camilla_procedimientos: 'Camilla de procedimientos', camilla_eda: 'Camilla para EDA', camilla_examen: 'Camilla de examen',
  camilla_ginecologica: 'Camilla ginecológica', camilla_ecografia: 'Camilla de ecografía', camilla_terapia: 'Camilla de terapia', camilla_plegable: 'Camilla plegable',
  sillon_reclinable: 'Sillón reclinable', sillon_toma_muestras: 'Sillón de toma de muestras', silla_ruedas: 'Silla de ruedas', tandem_4: 'Tándem de cuatro puestos',
  silla_trabajo: 'Silla de trabajo', silla_laboratorio: 'Silla de laboratorio', puesto_trabajo: 'Puesto de trabajo', escritorio: 'Escritorio',
  mueble_recepcion: 'Mueble de recepción', estacion_enfermeria: 'Estación de enfermería', meson: 'Mesón', mueble_bajo: 'Mueble bajo', vitrina: 'Vitrina',
  estanteria: 'Estantería', lockers_6: 'Lockers de seis puestos', gabinete_seguridad: 'Gabinete de seguridad', mesa_noche: 'Mesa de noche', mesa_puente: 'Mesa puente',
  mesa_mayo: 'Mesa de Mayo', mesa_auxiliar: 'Mesa auxiliar', riel_cortina: 'Riel con cortina', escalerilla: 'Escalerilla', estiba: 'Estiba',
  canecas_residuos: 'Canecas de residuos', lavaojos_ducha: 'Ducha y lavaojos', barras_paralelas: 'Barras paralelas', escalera_rehabilitacion: 'Escalera de rehabilitación',
  banda_caminadora: 'Banda caminadora', bicicleta_estatica: 'Bicicleta estática', espejo_postural: 'Espejo postural', kit_rehabilitacion: 'Kit de rehabilitación',
  compresero: 'Compresero', carro_paro: 'Carro de paro', carro_curaciones: 'Carro de curaciones', carro_medicamentos: 'Carro de medicamentos', carro_ropa: 'Carro de ropa',
  carro_cerrado: 'Carro cerrado', carro_equipo: 'Carro de equipo', atril: 'Atril', desfibrilador: 'Desfibrilador', dea_gabinete: 'Gabinete del DEA',
  monitor_signos: 'Monitor de signos vitales', electrocardiografo: 'Electrocardiógrafo', bomba_infusion: 'Bomba de infusión', ventilador_transporte: 'Ventilador de transporte',
  aspirador_portatil: 'Aspirador portátil', toma_gases_pared: 'Flujómetro de pared', equipo_mesa: 'Equipo de mesa', estuche: 'Estuche', tabla_espinal: 'Tabla espinal',
  equipo_pared: 'Equipo de pared', lampara_rodable: 'Lámpara rodable', lampara_cuello_cisne: 'Lámpara de cuello de cisne', lampara_cielitica: 'Lámpara cielítica',
  bascula_pesabebes: 'Báscula pesabebés', bascula_piso: 'Báscula de piso', infantometro: 'Infantómetro', servocuna: 'Servocuna', incubadora_neonatal: 'Incubadora neonatal',
  incubadora_transporte: 'Incubadora de transporte', fototerapia: 'Lámpara de fototerapia', monitor_fetal: 'Monitor fetal', unidad_odontologica: 'Unidad odontológica',
  compresor: 'Compresor', rx_periapical: 'Rayos X periapical', rayos_x_convencional: 'Rayos X convencional', ecografo: 'Ecógrafo',
  proteccion_radiologica: 'Protección radiológica', monitor_escritorio: 'Monitor de escritorio', computador_aio: 'Computador todo en uno',
  estacion_telemedicina: 'Estación de telemedicina', impresora: 'Impresora', rack: 'Rack de comunicaciones', digiturno: 'Digiturno', microscopio: 'Microscopio',
  cabina_bioseguridad: 'Cabina de bioseguridad', centrifuga_mesa: 'Centrífuga de mesa', analizador_mesa: 'Analizador de mesa', analizador_piso: 'Analizador de piso',
  incubadora_lab: 'Incubadora de laboratorio', ups: 'UPS', nevera_vertical: 'Nevera vertical', nevera_media: 'Nevera mediana', nevera_bajo_meson: 'Nevera bajo mesón',
  congelador_horizontal: 'Congelador horizontal', refrigerador_vacunas: 'Refrigerador de vacunas', termo_vacunas: 'Termo de vacunas', caja_termica: 'Caja térmica',
  autoclave_mesa: 'Autoclave de mesa', autoclave_vertical: 'Autoclave vertical', autoclave_central: 'Autoclave central', lavadora_desinfectora: 'Lavadora desinfectora',
  planta_electrica: 'Planta eléctrica', ups_central: 'UPS central', ascensor_cabina: 'Cabina de ascensor', montacargas: 'Montacargas', manifold_gases: 'Manifold de gases',
  generador_psa: 'Generador de oxígeno PSA', equipo_presion: 'Equipo de presión', tablero_sistema: 'Tablero de sistema', condensadora: 'Condensadora',
  nevera_mortuoria: 'Nevera mortuoria', lavamanos: 'Lavamanos', lavamanos_quirurgico: 'Lavamanos quirúrgico', inodoro: 'Inodoro', ducha: 'Ducha',
  poceta_aseo: 'Poceta de aseo', lavachatas: 'Lavachatas', barra_apoyo: 'Barra de apoyo', extintor: 'Extintor', gabinete_incendio: 'Gabinete contra incendio',
  senal_evacuacion: 'Señal de evacuación', toma_gases_cabecera: 'Panel de cabecera', llamado_enfermeria: 'Llamado de enfermería', transformador: 'Transformador',
  tablero_electrico: 'Tablero eléctrico', banco_baterias: 'Banco de baterías', bomba_agua: 'Bomba de agua', tanque_agua: 'Tanque de agua',
  panel_solar_fila: 'Fila de paneles solares', caseta_cubierta: 'Caseta de cubierta', baranda: 'Baranda', contenedor_residuos: 'Contenedor de residuos',
  bascula_residuos: 'Báscula de residuos', ambulancia: 'Ambulancia', montacargas_muestras: 'Montacargas de muestras', escalera_tramo: 'Tramo de escalera',
  reactivo_caja: 'Caja de reactivo', frasco_reactivo: 'Frasco de reactivo', gradilla_tubos: 'Gradilla con tubos', pipeta_set: 'Juego de pipetas',
};

// Set con los ids de la lista cerrada; un id fuera de él es un error (Anexo C: «equipos3d.js lanza error con un modelo desconocido»)
export const MODELOS = new Set(Object.keys(NOMINAL));
function exigirModelo(modelo) {
  if (MODELOS.has(modelo)) return;
  throw new Error(`equipos3d: modelo 3D desconocido «${modelo}». La lista cerrada (Anexo C y 16.5 del contrato) tiene ${MODELOS.size} modelos; `
    + 'hay que agregarlo al catálogo de equipos y a web/js/equipos3d.js antes de usarlo.');
}

// ---------------------------------------------------------------- paleta fija (5.1), en sRGB
const PALETA = {
  acero: '#b3bac0', aceroOsc: '#7c848b', aceroClaro: '#d3d8dc', blanco: '#eef0f1', crema: '#e4dfd3', porcelana: '#f6f6f2',
  tapiz: '#2f6690', tapizClaro: '#6d9cc6', tapizOsc: '#24496b', gris: '#8b939a', grisClaro: '#c9cdd0', grisOsc: '#4a5157', negro: '#23272b',
  pantalla: '#122130', pantallaLuz: '#2b5876', trazoVerde: '#37d67a', trazoAmarillo: '#f2c94c', trazoCian: '#56ccf2',
  oxigeno: '#2e8b57', vacio: '#e9ecec', aire: '#e2b51b', rojo: '#c62828', rojoOsc: '#8e1c1c', madera: '#a67c52', maderaClara: '#c9a77c',
  amarillo: '#e8b90f', naranja: '#e3741b', verdeSenal: '#1b8f3e', verde: '#3f8f4f', azul: '#2f6db5', azulMotor: '#2b5aa0', celeste: '#a8d1e7',
  rosado: '#efa3b4', lila: '#9b7fd1', luz: '#fff4cf', luzAzul: '#7fbaff', calor: '#ff8a3d', carton: '#c9a878', azulEsteril: '#82a9d6',
  resina: '#3a3f44', granito: '#d8d5ce', solar: '#1d2f4d', concreto: '#a3a39d', vidrioOsc: '#2a3540', cobre: '#b87333', cortina: '#8fbccb',
  cortinaOsc: '#77a6b6', estiba: '#3f6e9a', caucho: '#2d2f31', bronce: '#8d6e4a', grisVerde: '#6c7f6a', tablero: '#d6d7d2', agua: '#a9c9d6',
  // vidrios y acrílicos (van al material transparente)
  vidrio: '#cfe8f0', acrilico: '#e6f3f8', vidrioPlomo: '#7d9a99', espejo: '#c5dde6', humo: '#55616b',
};
const _colores = new Map();
function color(c) {
  let k = _colores.get(c);
  if (!k) { k = new THREE.Color(PALETA[c] || c); _colores.set(c, k); }
  return k;
}

// ---------------------------------------------------------------- constructor de piezas (coordenadas de planta)
// planta (x, y, z) → three (x, z, −y): una rotación propia (det = +1), así las caras no se invierten
const A_THREE = new THREE.Matrix4().set(1, 0, 0, 0, 0, 0, 1, 0, 0, -1, 0, 0, 0, 0, 0, 1);
const P_YZ = new THREE.Matrix4().set(0, 0, 1, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1);   // perfil lateral (u=y, v=z) extruido en +x
const P_XZ = new THREE.Matrix4().set(1, 0, 0, 0, 0, 0, -1, 0, 0, 1, 0, 0, 0, 0, 0, 1);  // perfil frontal (u=x, v=z) extruido en −y
const _v1 = new THREE.Vector3(), _v2 = new THREE.Vector3(), _q = new THREE.Quaternion(), _e = new THREE.Euler(), _uno = new THREE.Vector3(1, 1, 1);
const EJE_Y = new THREE.Vector3(0, 1, 0);

// deja una pieza lista para fundir: no indexada, solo position/normal/color, sin grupos (5.1)
function normalizarPieza(g, col) {
  let h = g.index ? g.toNonIndexed() : g;
  if (h !== g) g.dispose();
  for (const k of Object.keys(h.attributes)) if (k !== 'position' && k !== 'normal') h.deleteAttribute(k);
  h.morphAttributes = {};
  h.clearGroups();
  if (!h.attributes.normal) h.computeVertexNormals();
  const n = h.attributes.position.count, c = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) { c[3 * i] = col.r; c[3 * i + 1] = col.g; c[3 * i + 2] = col.b; }
  h.setAttribute('color', new THREE.BufferAttribute(c, 3));
  return h;
}

// Marco de referencia local: las piezas se describen en él (x a lo ancho, y hacia el frente, z arriba)
class Marco {
  constructor(pz, m) { this.pz = pz; this.m = m; }
  // sub-marco con origen [x, y, z] (en este marco) y giros: rx inclina (lleva +y hacia +z), rz gira en planta, ry alabea
  sub(origen = [0, 0, 0], rx = 0, rz = 0, ry = 0) {
    _e.set(rx, ry, rz, 'ZYX');
    const local = new THREE.Matrix4().compose(_v1.set(origen[0], origen[1], origen[2]), _q.setFromEuler(_e), _uno);
    return new Marco(this.pz, this.m.clone().multiply(local));
  }
  _pon(g, col, vid) { g.applyMatrix4(this.m); this.pz._agrega(g, col, vid); return this; }
  // caja por sus límites
  c(col, x0, x1, y0, y1, z0, z1, vid = false) {
    const sx = Math.max(Math.abs(x1 - x0), 0.002), sy = Math.max(Math.abs(y1 - y0), 0.002), sz = Math.max(Math.abs(z1 - z0), 0.002);
    const g = new THREE.BoxGeometry(sx, sy, sz);
    g.translate((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2);
    return this._pon(g, col, vid);
  }
  // cilindro vertical (eje z) de z0 a z1; rTop opcional (cono truncado)
  cv(col, x, y, z0, z1, r, seg = 8, rTop = r, vid = false) {
    const h = Math.max(Math.abs(z1 - z0), 0.002);
    const g = new THREE.CylinderGeometry(rTop, r, h, seg, 1);
    g.rotateX(Math.PI / 2);
    g.translate(x, y, Math.min(z0, z1) + h / 2);
    return this._pon(g, col, vid);
  }
  // cilindro entre dos puntos [x, y, z]; rB opcional (radio en b)
  cb(col, a, b, r, seg = 6, rB = r, vid = false) {
    _v1.set(b[0] - a[0], b[1] - a[1], b[2] - a[2]);
    const L = Math.max(_v1.length(), 0.002);
    const g = new THREE.CylinderGeometry(rB, r, L, seg, 1);
    _q.setFromUnitVectors(EJE_Y, _v1.normalize());
    g.applyQuaternion(_q);
    g.translate((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2);
    return this._pon(g, col, vid);
  }
  // esfera baja (48 triángulos)
  es(col, x, y, z, r, vid = false) {
    const g = new THREE.SphereGeometry(r, 8, 4);
    g.translate(x, y, z);
    return this._pon(g, col, vid);
  }
  // perfil extruido: 'yz' (lateral, u=y, v=z, de x=e0 a x=e1), 'xz' (frontal, u=x, v=z, de y=e0 a y=e1), 'xy' (planta, de z=e0 a z=e1)
  pf(col, pts, plano, e0, e1, vid = false, curva = 4) {
    const forma = new THREE.Shape(pts.map(([u, v]) => new THREE.Vector2(u, v)));
    const prof = Math.max(Math.abs(e1 - e0), 0.002);
    let g = new THREE.ExtrudeGeometry(forma, { depth: prof, bevelEnabled: false, curveSegments: curva, steps: 1 });
    if (plano === 'yz') { g.applyMatrix4(P_YZ); g.translate(Math.min(e0, e1), 0, 0); }
    else if (plano === 'xz') { g.applyMatrix4(P_XZ); g.translate(0, Math.max(e0, e1), 0); }
    else g.translate(0, 0, Math.min(e0, e1));
    g = g.index ? g.toNonIndexed() : g;
    g.deleteAttribute('uv');
    g.computeVertexNormals();   // 5.1: normales recalculadas en las extruidas
    return this._pon(g, col, vid);
  }
}

// Acumula las piezas de un modelo: opacas y transparentes por separado
class Piezas extends Marco {
  constructor(W, D, H, variante = null) {
    super(null, new THREE.Matrix4());
    this.pz = this;
    Object.assign(this, { W, D, H, w: W / 2, d: D / 2, v: variante, op: [], vi: [], n: 0 });
  }
  _agrega(g, col, vid) { (vid ? this.vi : this.op).push(normalizarPieza(g, color(col))); this.n++; }
  // fusiona y pasa a three; nunca devuelve null
  geom() {
    const funde = (lista) => {
      if (!lista.length) return null;
      const g = lista.length === 1 ? lista[0] : mergeGeometries(lista, false);
      if (!g) throw new Error('equipos3d: mergeGeometries devolvió null (piezas no compatibles)');
      if (lista.length > 1) lista.forEach((x) => x.dispose());
      g.applyMatrix4(A_THREE);
      return g;
    };
    let op = funde(this.op);
    const vi = funde(this.vi);
    if (!op) op = normalizarPieza(new THREE.BoxGeometry(0.002, 0.002, 0.002), color('gris')).applyMatrix4(A_THREE);
    op.userData = { piezas: this.n, triangulos: op.attributes.position.count / 3 + (vi ? vi.attributes.position.count / 3 : 0), vidrio: vi };
    return op;
  }
}

// ---------------------------------------------------------------- piezas comunes
const R2 = (a) => (a * Math.PI) / 180;
// ruedas de rodachina en las cuatro esquinas (rueda de 6 lados y vástago)
function ruedas(p, { dx = p.w - 0.06, dy = p.d - 0.06, r = 0.045, col = 'negro', vastago = true } = {}) {
  for (const sx of [-1, 1]) for (const sy of [-1, 1]) {
    const x = sx * dx, y = sy * dy;
    p.cb(col, [x - 0.014, y, r], [x + 0.014, y, r], r, 6);
    if (vastago) p.c('grisOsc', x - 0.012, x + 0.012, y - 0.012, y + 0.012, r * 1.6, r * 2 + 0.03);
  }
}
// cuatro patas de caja
function patas(p, x0, x1, y0, y1, z0, z1, s = 0.035, col = 'acero') {
  for (const x of [x0, x1 - s]) for (const y of [y0, y1 - s]) p.c(col, x, x + s, y, y + s, z0, z1);
}
// base de estrella de cinco brazos con rodachinas
function estrella(p, x, y, R, col = 'grisOsc', z = 0.05) {
  for (let k = 0; k < 5; k++) {
    const f = p.sub([x, y, 0], 0, R2(90 + k * 72));
    f.c(col, 0, R, -0.018, 0.018, z, z + 0.03);
    f.c('negro', R - 0.045, R - 0.005, -0.016, 0.016, 0, z);
  }
}
// pantalla con marco (en el marco f: frente hacia +y), con trazos de signos vitales si se pide
function pantalla(f, x0, x1, z0, z1, y = 0, { marco = 'grisOsc', fondo = 0.02, trazos = false, borde = 0.012, luz = 'pantalla' } = {}) {
  f.c(marco, x0, x1, y - fondo, y, z0, z1);
  f.c(luz, x0 + borde, x1 - borde, y, y + 0.002, z0 + borde, z1 - borde);
  if (trazos) {
    const h = z1 - z0 - 2 * borde, w = x1 - x0 - 2 * borde;
    ['trazoVerde', 'trazoAmarillo', 'trazoCian'].forEach((c, i) => {
      const z = z1 - borde - h * (0.25 + i * 0.25);
      f.c(c, x0 + borde + w * 0.06, x0 + borde + w * 0.7, y + 0.002, y + 0.004, z - 0.0025, z + 0.0025);
      if (i === 0) f.c(c, x0 + borde + w * 0.3, x0 + borde + w * 0.33, y + 0.002, y + 0.004, z - h * 0.06, z + h * 0.12);
      f.c(c, x0 + borde + w * 0.78, x0 + borde + w * 0.92, y + 0.002, y + 0.004, z - h * 0.05, z + h * 0.05);
    });
  }
}
// tabla inclinada desde una bisagra: largo L hacia −y (atras=true) o hacia +y, grosor t, ángulo phi (grados) hacia arriba
function tabla(p, col, x0, x1, yb, zb, L, t, phi, atras = true) {
  const f = p.sub([0, yb, zb], R2(atras ? -phi : phi));
  if (atras) f.c(col, x0, x1, -L, 0, 0, t); else f.c(col, x0, x1, 0, L, 0, t);
  return f;
}
// baranda lateral abierta: barras arriba y abajo, dos parales
function barandaLateral(p, x, y0, y1, z0, z1, col = 'blanco', e = 0.025) {
  p.c(col, x - e / 2, x + e / 2, y0, y1, z1 - 0.035, z1);
  p.c(col, x - e / 2, x + e / 2, y0, y1, z0, z0 + 0.025);
  p.c(col, x - e / 2, x + e / 2, y0, y0 + 0.03, z0, z1);
  p.c(col, x - e / 2, x + e / 2, y1 - 0.03, y1, z0, z1);
}
// frentes de cajones con manija (frente en +y = yf)
// (dir = −1: el frente mira a −y)
function cajones(p, x0, x1, yf, z0, z1, n, col = 'blanco', manija = 'acero', hueco = 0.006, dir = 1) {
  const h = (z1 - z0) / n;
  for (let i = 0; i < n; i++) {
    const a = z0 + i * h + hueco / 2, b = z0 + (i + 1) * h - hueco / 2;
    p.c(col, x0 + hueco, x1 - hueco, yf, yf + 0.012 * dir, a, b);
    const xm = (x0 + x1) / 2, wm = Math.min(0.12, (x1 - x0) * 0.35);
    p.c(manija, xm - wm / 2, xm + wm / 2, yf + 0.012 * dir, yf + 0.026 * dir, b - Math.min(0.035, h * 0.35), b - Math.min(0.02, h * 0.2));
  }
}
// silla sencilla (asiento, espaldar y cuatro patas); mira a +y del marco f
function sillaSimple(f, { ancho = 0.46, fondo = 0.44, zs = 0.45, alto = 0.82, col = 'tapiz', patasCol = 'negro' } = {}) {
  const w = ancho / 2, d = fondo / 2;
  patas(f, -w + 0.02, w - 0.02, -d + 0.02, d - 0.02, 0, zs - 0.03, 0.025, patasCol);
  f.c(col, -w, w, -d, d, zs - 0.04, zs);
  f.c(col, -w, w, -d - 0.02, -d + 0.02, zs, alto);
}
// cilindro de gas (cuerpo, hombro y válvula)
function cilindroGas(p, x, y, r, h, col = 'oxigeno', seg = 8) {
  p.cv(col, x, y, 0, h * 0.86, r, seg);
  p.cv(col, x, y, h * 0.86, h * 0.95, r, 6, r * 0.35);
  p.c('negro', x - r * 0.3, x + r * 0.3, y - r * 0.3, y + r * 0.3, h * 0.95, h);
}

// ---------------------------------------------------------------- LOD1 (≤ 4 cajas, ≤ 48 triángulos)
const L1 = {
  caja: (col) => (p) => { p.c(col, -p.w, p.w, -p.d, p.d, 0, p.H); },
  // cuerpo y frente de otro color (pantallas, puertas)
  frente: (col, colFrente, fz0 = 0.1, fz1 = 0.9) => (p) => {
    p.c(col, -p.w, p.w, -p.d, p.d - 0.01, 0, p.H);
    p.c(colFrente, -p.w * 0.85, p.w * 0.85, p.d - 0.01, p.d, p.H * fz0, p.H * fz1);
  },
  cama: (colColchon = 'tapiz', zc = 0.45) => (p) => {
    const z = Math.min(zc, p.H * 0.6);
    p.c('grisOsc', -p.w + 0.05, p.w - 0.05, -p.d + 0.08, p.d - 0.08, 0, z);
    p.c(colColchon, -p.w + 0.03, p.w - 0.03, -p.d + 0.06, p.d - 0.06, z, z + 0.16);
    p.c('blanco', -p.w, p.w, -p.d, -p.d + 0.05, z - 0.1, p.H);
    p.c('blanco', -p.w, p.w, p.d - 0.05, p.d, z - 0.1, Math.min(p.H, z + 0.32));
  },
  camilla: (colTop = 'tapiz', zt = 0.6) => (p) => {
    const z = Math.min(zt, p.H * 0.85);
    p.c('grisOsc', -p.w * 0.6, p.w * 0.6, -p.d * 0.8, p.d * 0.8, 0, z - 0.08);
    p.c(colTop, -p.w, p.w, -p.d * 0.45, p.d, z - 0.08, z);
    p.c(colTop, -p.w, p.w, -p.d, -p.d * 0.45, z - 0.08, Math.max(z, p.H * 0.92));
  },
  mesa: (colTop = 'madera', colBase = 'gris', t = 0.04) => (p) => {
    p.c(colBase, -p.w + 0.03, p.w - 0.03, -p.d + 0.03, p.d - 0.03, 0, p.H - t);
    p.c(colTop, -p.w, p.w, -p.d, p.d, p.H - t, p.H);
  },
  silla: (col = 'tapiz', zs = 0.45) => (p) => {
    p.c('negro', -0.04, 0.04, -0.04, 0.04, 0, zs - 0.05);
    p.c(col, -p.w + 0.05, p.w - 0.05, -p.d + 0.06, p.d - 0.04, zs - 0.05, zs);
    p.c(col, -p.w + 0.07, p.w - 0.07, -p.d, -p.d + 0.06, zs, p.H);
  },
  poste: (colBase = 'grisOsc', colCab = 'blanco', hc = 0.25) => (p) => {
    p.c(colBase, -p.w, p.w, -p.d, p.d, 0, 0.08);
    p.c('acero', -0.02, 0.02, -0.02, 0.02, 0.08, p.H - hc);
    p.c(colCab, -p.w * 0.6, p.w * 0.6, -p.d * 0.6, p.d * 0.6, p.H - hc, p.H);
  },
  vitrina: (col = 'blanco', colVid = 'vidrio') => (p) => {
    p.c(col, -p.w, p.w, -p.d, p.d - 0.03, 0, p.H);
    p.c(colVid, -p.w + 0.03, p.w - 0.03, p.d - 0.03, p.d, 0.1, p.H - 0.05, true);
  },
};

// ---------------------------------------------------------------- modelos
// Cada modelo: lod0(p) con el detalle que lo hace reconocible y lod1(p) con ≤ 4 cajas. p trae W, D, H (medidas reales),
// w = W/2, d = D/2 y v (variante). La espalda está en y = −d.
const DEF = {};
function def(id, lod0, lod1) {
  if (!MODELOS.has(id)) throw new Error(`equipos3d: definición de un modelo fuera de la lista cerrada: ${id}`);
  DEF[id] = { lod0, lod1 };
}

// ---- camas y cunas
function camaBase(p, { zp = 0.45, colColchon = 'tapiz', espaldar = 28, barandaAlta = 0, cabecero = true } = {}) {
  const { w, d, H } = p;
  ruedas(p, { r: 0.05, dx: w - 0.1, dy: d - 0.14 });
  p.c('grisOsc', -w + 0.12, w - 0.12, -d + 0.12, d - 0.12, 0.11, 0.17);
  for (const y of [-d * 0.5, d * 0.5]) p.c('gris', -0.11, 0.11, y - 0.07, y + 0.07, 0.17, zp - 0.02);
  p.c('acero', -w + 0.05, w - 0.05, -d + 0.08, d - 0.08, zp - 0.02, zp + 0.03);
  const zc = zp + 0.03, yb = -d * 0.22, L = yb + d - 0.1;
  p.c(colColchon, -w + 0.07, w - 0.07, yb, d - 0.1, zc, zc + 0.13);
  const f = tabla(p, colColchon, -w + 0.07, w - 0.07, yb, zc, L, 0.13, espaldar);
  f.c('blanco', -0.24, 0.24, -L + 0.06, -L + 0.4, 0.13, 0.2);
  if (cabecero) {
    p.c('blanco', -w + 0.02, w - 0.02, -d, -d + 0.045, zp - 0.12, H);
    p.c('tapizClaro', -w + 0.08, w - 0.08, -d + 0.045, -d + 0.05, H - 0.2, H - 0.08);
    p.c('blanco', -w + 0.02, w - 0.02, d - 0.045, d, zp - 0.12, Math.min(H, zp + 0.36));
  }
  const zr0 = zc + 0.06, zr1 = barandaAlta || Math.min(H - 0.02, zc + 0.36);
  for (const s of [-1, 1]) {
    barandaLateral(p, s * (w - 0.015), -d + 0.16, yb - 0.05, zr0, zr1);
    barandaLateral(p, s * (w - 0.015), yb + 0.08, d - 0.25, zr0, zr1);
  }
}
def('cama_hospitalaria', (p) => camaBase(p, { espaldar: 20 }), L1.cama('tapiz'));
def('cama_pediatrica', (p) => {
  const { w, d, H } = p, zp = 0.5;
  ruedas(p, { r: 0.05, dx: w - 0.1, dy: d - 0.12 });
  p.c('grisOsc', -w + 0.1, w - 0.1, -d + 0.1, d - 0.1, 0.11, 0.17);
  p.c('gris', -0.1, 0.1, -0.08, 0.08, 0.17, zp - 0.02);
  p.c('acero', -w + 0.04, w - 0.04, -d + 0.05, d - 0.05, zp - 0.02, zp + 0.03);
  p.c('tapizClaro', -w + 0.06, w - 0.06, -d + 0.07, d - 0.07, zp + 0.03, zp + 0.15);
  p.c('blanco', -0.2, 0.2, -d + 0.1, -d + 0.38, zp + 0.15, zp + 0.21);
  p.c('blanco', -w, w, -d, -d + 0.04, zp - 0.1, H);
  p.c('tapizClaro', -w + 0.08, w - 0.08, -d + 0.04, -d + 0.045, H - 0.22, H - 0.08);
  p.c('blanco', -w, w, d - 0.04, d, zp - 0.1, H - 0.05);
  for (const s of [-1, 1]) {
    const x = s * (w - 0.015);
    p.c('blanco', x - 0.014, x + 0.014, -d + 0.05, d - 0.05, H - 0.04, H);
    p.c('blanco', x - 0.014, x + 0.014, -d + 0.05, d - 0.05, zp + 0.06, zp + 0.09);
    for (let k = 1; k <= 5; k++) { const y = -d + 0.05 + (k * (p.D - 0.1)) / 6; p.c('blanco', x - 0.01, x + 0.01, y - 0.012, y + 0.012, zp + 0.09, H - 0.04); }
  }
}, L1.cama('tapizClaro', 0.5));
def('cuna_hospitalaria', (p) => {
  const { w, d, H } = p, zp = 0.62;
  ruedas(p, { r: 0.045, dx: w - 0.07, dy: d - 0.08 });
  p.c('grisOsc', -w + 0.07, w - 0.07, -d + 0.08, d - 0.08, 0.1, 0.16);
  p.c('gris', -0.08, 0.08, -0.08, 0.08, 0.16, zp - 0.03);
  for (const sx of [-1, 1]) for (const sy of [-1, 1]) p.c('blanco', sx * w - (sx > 0 ? 0.035 : 0), sx * w + (sx < 0 ? 0.035 : 0), sy * d - (sy > 0 ? 0.035 : 0), sy * d + (sy < 0 ? 0.035 : 0), zp - 0.08, H);
  p.c('acero', -w + 0.03, w - 0.03, -d + 0.03, d - 0.03, zp - 0.04, zp);
  p.c('celeste', -w + 0.04, w - 0.04, -d + 0.04, d - 0.04, zp, zp + 0.1);
  for (const sy of [-1, 1]) p.c('tapizClaro', -w + 0.035, w - 0.035, sy * (d - 0.015) - 0.01, sy * (d - 0.015) + 0.01, zp, H - 0.04);
  for (const s of [-1, 1]) {
    const x = s * (w - 0.015);
    p.c('blanco', x - 0.013, x + 0.013, -d + 0.035, d - 0.035, H - 0.035, H);
    p.c('blanco', x - 0.013, x + 0.013, -d + 0.035, d - 0.035, zp, zp + 0.03);
    for (let k = 1; k <= 5; k++) { const y = -d + (k * p.D) / 6; p.c('blanco', x - 0.009, x + 0.009, y - 0.01, y + 0.01, zp + 0.03, H - 0.035); }
  }
}, L1.cama('celeste', 0.6));
def('cuna_acrilico', (p) => {
  const { w, d, H } = p, zt = H - 0.3;
  ruedas(p, { r: 0.04, dx: w - 0.05, dy: d - 0.07 });
  for (const sy of [-1, 1]) {
    p.c('acero', -w + 0.03, w - 0.03, sy * (d - 0.07) - 0.015, sy * (d - 0.07) + 0.015, 0.09, 0.12);
    p.c('acero', -0.015, 0.015, sy * (d - 0.07) - 0.015, sy * (d - 0.07) + 0.015, 0.12, zt);
  }
  p.c('blanco', -w + 0.04, w - 0.04, -d + 0.08, d - 0.08, 0.28, 0.3);
  p.c('acero', -0.02, 0.02, -d + 0.07, d - 0.07, 0.12, 0.14);
  p.c('acero', -w + 0.02, w - 0.02, -d + 0.03, d - 0.03, zt - 0.02, zt);
  p.c('acrilico', -w + 0.03, w - 0.03, -d + 0.04, d - 0.04, zt, zt + 0.012, true);
  for (const s of [-1, 1]) {
    p.c('acrilico', s * (w - 0.03) - 0.006, s * (w - 0.03) + 0.006, -d + 0.04, d - 0.04, zt, H, true);
    p.c('acrilico', -w + 0.03, w - 0.03, s * (d - 0.04) - 0.006, s * (d - 0.04) + 0.006, zt, H, true);
  }
  p.c('celeste', -w + 0.045, w - 0.045, -d + 0.055, d - 0.055, zt + 0.012, zt + 0.05);
  p.c('blanco', -0.08, 0.08, -d + 0.07, -d + 0.2, zt + 0.05, zt + 0.08);
}, (p) => { p.c('acero', -p.w + 0.03, p.w - 0.03, -p.d + 0.05, p.d - 0.05, 0, p.H - 0.3); p.c('acrilico', -p.w, p.w, -p.d, p.d, p.H - 0.3, p.H, true); p.c('celeste', -p.w + 0.03, p.w - 0.03, -p.d + 0.04, p.d - 0.04, p.H - 0.3, p.H - 0.25); });
def('cuna_observacion', (p) => {
  const { w, d, H } = p, zp = H - 0.4;
  ruedas(p, { r: 0.045, dx: w - 0.06, dy: d - 0.08 });
  p.c('grisOsc', -w + 0.06, w - 0.06, -d + 0.08, d - 0.08, 0.1, 0.15);
  p.c('blanco', -w + 0.04, w - 0.04, -d + 0.06, d - 0.06, 0.15, zp - 0.03);
  cajones(p, -w + 0.1, w - 0.1, d - 0.06, zp - 0.25, zp - 0.05, 1, 'blanco');
  p.c('acero', -w, w, -d, d, zp - 0.03, zp);
  p.c('celeste', -w + 0.03, w - 0.03, -d + 0.03, d - 0.03, zp, zp + 0.08);
  for (const sx of [-1, 1]) for (const sy of [-1, 1]) p.c('acero', sx * (w - 0.02) - 0.015, sx * (w - 0.02) + 0.015, sy * (d - 0.02) - 0.015, sy * (d - 0.02) + 0.015, zp, H);
  for (const s of [-1, 1]) {
    p.c('acrilico', s * (w - 0.02) - 0.006, s * (w - 0.02) + 0.006, -d + 0.035, d - 0.035, zp + 0.02, H - 0.01, true);
    p.c('acrilico', -w + 0.035, w - 0.035, s * (d - 0.02) - 0.006, s * (d - 0.02) + 0.006, zp + 0.02, H - 0.01, true);
  }
}, (p) => { p.c('blanco', -p.w + 0.04, p.w - 0.04, -p.d + 0.06, p.d - 0.06, 0, p.H - 0.4); p.c('acrilico', -p.w, p.w, -p.d, p.d, p.H - 0.4, p.H, true); p.c('celeste', -p.w + 0.03, p.w - 0.03, -p.d + 0.03, p.d - 0.03, p.H - 0.4, p.H - 0.32); });
def('cama_partos', (p) => {
  const { w, d, H } = p, zs = H * 0.55;
  p.c('grisOsc', -w + 0.08, w - 0.08, -d + 0.15, d - 0.4, 0, 0.08);
  p.c('blanco', -w + 0.12, w - 0.12, -d + 0.2, d - 0.55, 0.08, zs - 0.08);
  p.c('tapizClaro', -w + 0.12, w - 0.12, d - 0.56, d - 0.55, 0.12, zs - 0.12);
  p.c('acero', -w + 0.05, w - 0.05, -d + 0.15, d * 0.4, zs - 0.08, zs - 0.04);
  p.c('tapiz', -w + 0.06, w - 0.06, -0.12, d * 0.4, zs - 0.04, zs + 0.09);
  const f = tabla(p, 'tapiz', -w + 0.06, w - 0.06, -0.12, zs - 0.04, 0.7, 0.12, 26);
  f.c('blanco', -0.22, 0.22, -0.66, -0.4, 0.12, 0.17);
  p.c('tapiz', -w + 0.18, w - 0.18, d * 0.4, d * 0.4 + 0.3, zs - 0.3, zs - 0.2);
  for (const s of [-1, 1]) {
    const x = s * (w - 0.16);
    p.c('acero', x - 0.018, x + 0.018, d - 0.38, d - 0.34, zs - 0.08, H - 0.12);
    const g = p.sub([x, d - 0.32, H - 0.12], R2(-20));
    g.c('tapiz', -0.07, 0.07, -0.04, 0.24, 0, 0.08);
    p.cb('acero', [s * (w - 0.02), -0.1, zs + 0.18], [s * (w - 0.02), d * 0.35, zs + 0.18], 0.016, 6);
    p.c('acero', s * (w - 0.02) - 0.015, s * (w - 0.02) + 0.015, -0.11, -0.08, zs - 0.06, zs + 0.18);
    p.c('acero', s * (w - 0.02) - 0.015, s * (w - 0.02) + 0.015, d * 0.35 - 0.03, d * 0.35, zs - 0.06, zs + 0.18);
  }
  p.c('pantalla', w - 0.11, w - 0.105, -d + 0.4, -d + 0.6, zs - 0.3, zs - 0.15);
}, L1.camilla('tapiz', 0.62));

// ---- camillas
function camillaBase(p, { zt = p.H - 0.3, col = 'tapiz', espaldar = 20, barandas = true, oxigeno = false, columnas = 2 } = {}) {
  const { w, d, H } = p;
  ruedas(p, { r: 0.06, dx: w - 0.08, dy: d - 0.18 });
  p.c('grisOsc', -w + 0.06, w - 0.06, -d + 0.12, d - 0.12, 0.13, 0.2);
  const ys = columnas === 2 ? [-d * 0.45, d * 0.45] : [0];
  for (const y of ys) p.cv('gris', 0, y, 0.2, zt - 0.06, 0.07, 8);
  p.c('acero', -w + 0.03, w - 0.03, -d + 0.05, d - 0.05, zt - 0.06, zt - 0.02);
  const yb = -d * 0.3, L = yb + d - 0.06;
  p.c(col, -w + 0.05, w - 0.05, yb, d - 0.06, zt - 0.02, zt + 0.07);
  tabla(p, col, -w + 0.05, w - 0.05, yb, zt - 0.02, L, 0.09, espaldar);
  if (barandas) for (const s of [-1, 1]) barandaLateral(p, s * (w - 0.012), -d + 0.4, d - 0.35, zt + 0.02, Math.min(H, zt + 0.3), 'acero', 0.02);
  for (const y of [-d + 0.02, d - 0.02]) p.cb('acero', [-w + 0.08, y, zt + 0.16], [w - 0.08, y, zt + 0.16], 0.014, 6);
  for (const y of [-d + 0.02, d - 0.02]) for (const s of [-1, 1]) p.c('acero', s * (w - 0.08) - 0.012, s * (w - 0.08) + 0.012, y - 0.012, y + 0.012, zt - 0.04, zt + 0.16);
  if (oxigeno) p.cb('oxigeno', [0.12, -d * 0.35, 0.3], [0.12, d * 0.25, 0.3], 0.075, 8);
}
def('camilla_reanimacion', (p) => { camillaBase(p, { oxigeno: true, espaldar: 16 }); p.cb('acero', [p.w - 0.05, -p.d + 0.05, p.H - 0.3], [p.w - 0.05, -p.d + 0.05, p.H], 0.012, 6); }, L1.camilla('tapiz', 0.65));
def('camilla_observacion', (p) => camillaBase(p, { col: 'tapizClaro', espaldar: 18 }), L1.camilla('tapizClaro', 0.6));
def('camilla_transporte', (p) => { camillaBase(p, { espaldar: 12, columnas: 2 }); for (const sx of [-1, 1]) for (const sy of [-1, 1]) p.cv('gris', sx * (p.w - 0.04), sy * (p.d - 0.05), 0.13, 0.2, 0.05, 6); p.cb('oxigeno', [-0.05, -p.d * 0.3, 0.3], [-0.05, p.d * 0.3, 0.3], 0.07, 8); }, L1.camilla('tapiz', 0.65));
def('camilla_procedimientos', (p) => {
  const { w, d, H } = p, zt = H - 0.05;
  p.c('grisOsc', -w + 0.08, w - 0.08, -d * 0.6, d * 0.6, 0, 0.06);
  p.c('blanco', -w * 0.55, w * 0.55, -d * 0.45, d * 0.45, 0.06, zt - 0.12);
  cajones(p, -w * 0.45, w * 0.45, d * 0.45, 0.25, 0.5, 2, 'blanco');
  p.c('acero', -w + 0.03, w - 0.03, -d + 0.03, d - 0.03, zt - 0.12, zt - 0.08);
  p.c('tapiz', -w + 0.03, w - 0.03, -d * 0.55, d - 0.03, zt - 0.08, zt);
  tabla(p, 'tapiz', -w + 0.08, w - 0.08, -d * 0.55, zt - 0.08, d * 0.45 - 0.03, 0.08, 5);
  for (const s of [-1, 1]) p.c('acero', s * (w - 0.01) - 0.01, s * (w - 0.01) + 0.01, -d * 0.3, d * 0.6, zt - 0.11, zt - 0.08);
}, L1.camilla('tapiz', 0.85));
def('camilla_eda', (p) => {
  const { w, d, H } = p, zt = H;
  patas(p, -w + 0.02, w - 0.02, -d + 0.02, d - 0.02, 0, zt - 0.08, 0.035, 'acero');
  p.c('acero', -w + 0.02, w - 0.02, -d + 0.02, d - 0.02, zt - 0.12, zt - 0.08);
  p.c('acero', -w + 0.04, w - 0.04, -d + 0.04, d - 0.04, 0.18, 0.2);
  p.c('tapiz', -w + 0.02, w - 0.02, -d + 0.02, d - 0.02, zt - 0.08, zt - 0.01);
  p.c('negro', -0.09, 0.09, -0.02, 0.16, zt - 0.01, zt);
  p.cv('celeste', 0, 0.07, 0.2, 0.42, 0.14, 10, 0.16);
  p.c('blanco', -0.2, 0.2, -d + 0.1, -d + 0.4, zt - 0.01, zt);
}, L1.camilla('tapiz', 0.8));
def('camilla_examen', (p) => {
  const { w, d, H } = p, zt = H - 0.08;
  patas(p, -w + 0.02, w - 0.02, -d + 0.05, d - 0.02, 0, zt - 0.1, 0.035, 'acero');
  p.c('madera', -w + 0.03, w - 0.03, -d + 0.06, d - 0.03, 0.2, 0.23);
  p.c('acero', -w + 0.02, w - 0.02, -d + 0.05, d - 0.02, zt - 0.12, zt - 0.09);
  p.c('tapiz', -w + 0.02, w - 0.02, -d * 0.3, d - 0.02, zt - 0.09, zt - 0.02);
  tabla(p, 'tapiz', -w + 0.02, w - 0.02, -d * 0.3, zt - 0.09, d * 0.7 - 0.08, 0.07, 10);
  p.c('blanco', -0.22, 0.22, -d * 0.3, d - 0.03, zt - 0.02, zt - 0.015);
  p.cb('blanco', [-w * 0.7, -d + 0.04, zt - 0.17], [w * 0.7, -d + 0.04, zt - 0.17], 0.045, 8);
  for (const s of [-1, 1]) p.c('acero', s * w * 0.75 - 0.01, s * w * 0.75 + 0.01, -d + 0.02, -d + 0.07, zt - 0.22, zt - 0.11);
}, L1.camilla('tapiz', 0.75));
def('camilla_ginecologica', (p) => {
  const { w, d, H } = p, zs = H * 0.72;
  p.c('blanco', -w + 0.04, w - 0.04, -d + 0.15, d * 0.35, 0, zs - 0.08);
  cajones(p, -w + 0.1, w - 0.1, d * 0.35, 0.08, zs - 0.12, 2, 'blanco');
  p.c('grisOsc', -w + 0.04, w - 0.04, -d + 0.15, d * 0.35, 0, 0.04);
  p.c('tapiz', -w + 0.04, w - 0.04, -0.1, d * 0.35, zs - 0.08, zs);
  tabla(p, 'tapiz', -w + 0.04, w - 0.04, -0.1, zs - 0.08, 0.6, 0.08, 24);
  p.c('blanco', -0.18, 0.18, d * 0.35, d * 0.35 + 0.2, 0.15, 0.2);
  for (const s of [-1, 1]) {
    const x = s * (w - 0.08);
    p.cb('acero', [x, d * 0.3, zs - 0.05], [x, d - 0.08, H - 0.05], 0.014, 6);
    p.c('negro', x - 0.04, x + 0.04, d - 0.12, d - 0.02, H - 0.08, H);
  }
}, L1.camilla('tapiz', 0.62));
def('camilla_ecografia', (p) => {
  const { w, d, H } = p, zt = H - 0.06;
  p.c('grisOsc', -w + 0.08, w - 0.08, -d * 0.55, d * 0.55, 0, 0.05);
  p.c('blanco', -w * 0.4, w * 0.4, -d * 0.35, d * 0.35, 0.05, zt - 0.12);
  p.c('acero', -w + 0.03, w - 0.03, -d + 0.03, d - 0.03, zt - 0.12, zt - 0.09);
  p.c('tapizClaro', -w + 0.02, w - 0.02, -d * 0.2, d - 0.02, zt - 0.09, zt - 0.01);
  tabla(p, 'tapizClaro', -w + 0.02, w - 0.02, -d * 0.2, zt - 0.09, d * 0.8 - 0.05, 0.08, 7);
  p.c('tapiz', w - 0.06, w - 0.02, -d * 0.2, d * 0.5, zt - 0.01, zt);
  p.c('tapiz', -w + 0.02, -w + 0.06, -d * 0.2, d * 0.5, zt - 0.01, zt);
}, L1.camilla('tapizClaro', 0.7));
def('camilla_terapia', (p) => {
  const { w, d, H } = p, zt = H;
  for (const y of [-d + 0.04, -0.02, d - 0.04]) for (const s of [-1, 1]) p.c('madera', s * (w - 0.04) - 0.025, s * (w - 0.04) + 0.025, y - 0.025, y + 0.025, 0, zt - 0.1);
  for (const y of [-d + 0.04, d - 0.04]) p.c('madera', -w + 0.04, w - 0.04, y - 0.02, y + 0.02, 0.15, 0.2);
  p.c('madera', -w + 0.02, w - 0.02, -d + 0.02, d - 0.02, zt - 0.11, zt - 0.08);
  p.c('tapiz', -w + 0.02, w - 0.02, -d + 0.02, -0.03, zt - 0.08, zt);
  p.c('tapiz', -w + 0.02, w - 0.02, -0.01, d - 0.02, zt - 0.08, zt);
  p.c('negro', -0.06, 0.06, -d + 0.08, -d + 0.2, zt, zt + 0.002);
}, L1.camilla('tapiz', 0.7));
def('camilla_plegable', (p) => {
  const { w, d, H } = p;
  if (p.v === 'plegada' || H > p.D) {
    p.c('tapiz', -w + 0.03, w - 0.03, -0.02, 0.02, 0.1, H - 0.05);
    for (const s of [-1, 1]) p.c('acero', s * (w - 0.015) - 0.015, s * (w - 0.015) + 0.015, -d + 0.02, d - 0.02, 0, H);
    for (const z of [0.25, H - 0.25]) p.c('acero', -w + 0.02, w - 0.02, -0.05, -0.03, z - 0.02, z + 0.02);
    return;
  }
  for (const y of [-d + 0.15, d - 0.15]) for (const s of [-1, 1]) {
    p.cb('acero', [s * (w - 0.03), y - 0.12, 0], [s * (w - 0.03), y + 0.12, H - 0.05], 0.013, 6);
    p.cb('acero', [s * (w - 0.03), y + 0.12, 0], [s * (w - 0.03), y - 0.12, H - 0.05], 0.013, 6);
  }
  for (const s of [-1, 1]) p.cb('acero', [s * (w - 0.02), -d, H - 0.04], [s * (w - 0.02), d, H - 0.04], 0.016, 6);
  p.c('tapiz', -w + 0.03, w - 0.03, -d + 0.02, d - 0.02, H - 0.05, H - 0.03);
}, (p) => { if (p.H > p.D) { p.c('tapiz', -p.w, p.w, -p.d, p.d, 0, p.H); return; } p.c('acero', -p.w + 0.03, p.w - 0.03, -p.d + 0.1, p.d - 0.1, 0, p.H - 0.06); p.c('tapiz', -p.w, p.w, -p.d, p.d, p.H - 0.06, p.H); });

// ---- asientos
def('sillon_reclinable', (p) => {
  const { w, d, H } = p;
  p.c('grisOsc', -w + 0.08, w - 0.08, -d + 0.1, d - 0.25, 0, 0.12);
  p.c('tapizOsc', -w + 0.1, w - 0.1, -d + 0.15, d - 0.25, 0.12, 0.38);
  p.c('tapiz', -w + 0.12, w - 0.12, -d + 0.25, d - 0.2, 0.38, 0.5);
  tabla(p, 'tapiz', -w + 0.12, w - 0.12, d - 0.2, 0.3, 0.18, 0.09, 25, false);
  const g = p.sub([0, -d + 0.25, 0.42], R2(-14));
  g.c('tapiz', -w + 0.12, w - 0.12, -0.16, 0, 0, H - 0.45);
  g.c('tapizClaro', -w + 0.18, w - 0.18, 0, 0.04, H - 0.68, H - 0.48);
  for (const s of [-1, 1]) p.c('tapizOsc', s * (w - 0.06) - 0.06, s * (w - 0.06) + 0.06, -d + 0.15, d - 0.28, 0.12, 0.65);
}, L1.silla('tapiz', 0.5));
def('sillon_toma_muestras', (p) => {
  const { w, d, H } = p;
  p.c('acero', -w + 0.1, w - 0.1, -d + 0.1, d - 0.15, 0, 0.05);
  p.c('acero', -0.04, 0.04, -0.1, 0, 0.05, 0.42);
  p.c('tapiz', -w + 0.12, w - 0.12, -d + 0.2, d - 0.18, 0.42, 0.55);
  const g = p.sub([0, -d + 0.2, 0.5], R2(-10));
  g.c('tapiz', -w + 0.13, w - 0.13, -0.12, 0, 0, H - 0.6);
  g.c('tapiz', -0.14, 0.14, -0.1, 0.02, H - 0.62, H - 0.5);
  for (const s of [-1, 1]) {
    const x = s * (w - 0.07);
    p.c('acero', x - 0.015, x + 0.015, -d + 0.25, -d + 0.28, 0.42, 0.66);
    const a = p.sub([x, -d + 0.22, 0.66], R2(8));
    a.c('tapiz', -0.06, 0.06, 0, d * 2 - 0.22, 0, 0.06);
    a.c('acero', -0.015, 0.015, 0.2, 0.23, -0.2, 0);
  }
}, L1.silla('tapiz', 0.55));
def('silla_ruedas', (p) => {
  const { w, d, H } = p, R = Math.min(0.3, H * 0.34), yr = -d + R + 0.04, zs = 0.5;
  for (const s of [-1, 1]) {
    const x = s * (w - 0.025);
    p.cb('negro', [x - 0.018, yr, R], [x + 0.018, yr, R], R, 14);
    p.cb('acero', [x - 0.022, yr, R], [x + 0.022, yr, R], 0.05, 6);
    p.cb('gris', [s * (w - 0.1), yr, R], [x - s * 0.02, yr, R], 0.012, 6);
    p.cb('negro', [s * (w - 0.12) - 0.012, d - 0.12, 0.075], [s * (w - 0.12) + 0.012, d - 0.12, 0.075], 0.075, 8);
    p.c('acero', s * (w - 0.12) - 0.012, s * (w - 0.12) + 0.012, d - 0.13, d - 0.11, 0.15, zs - 0.02);
    p.cb('acero', [s * (w - 0.1), -d + 0.1, zs], [s * (w - 0.1), d - 0.12, zs], 0.013, 6);
    p.cb('acero', [s * (w - 0.1), -d + 0.12, zs], [s * (w - 0.1), -d + 0.06, H], 0.013, 6);
    p.cb('negro', [s * (w - 0.1), -d + 0.06, H - 0.02], [s * (w - 0.1), -d, H - 0.02], 0.016, 6);
    p.c('negro', s * (w - 0.1) - 0.03, s * (w - 0.1) + 0.03, -d + 0.2, d - 0.35, 0.7, 0.73);
    p.cb('acero', [s * (w - 0.14), d - 0.18, zs], [s * 0.1, d - 0.04, 0.12], 0.012, 6);
    p.c('negro', s * 0.1 - 0.08, s * 0.1 + 0.08, d - 0.12, d, 0.1, 0.12);
  }
  p.c('tapiz', -w + 0.12, w - 0.12, -d + 0.12, d - 0.18, zs - 0.02, zs + 0.02);
  const g = p.sub([0, -d + 0.1, zs + 0.02], R2(-8));
  g.c('tapiz', -w + 0.12, w - 0.12, -0.02, 0.01, 0, H - zs - 0.12);
}, (p) => { p.c('negro', -p.w, -p.w + 0.05, -p.d, p.d * 0.2, 0, 0.6); p.c('negro', p.w - 0.05, p.w, -p.d, p.d * 0.2, 0, 0.6); p.c('tapiz', -p.w + 0.05, p.w - 0.05, -p.d + 0.05, p.d, 0.1, 0.5); p.c('tapiz', -p.w + 0.05, p.w - 0.05, -p.d, -p.d + 0.08, 0.5, p.H); });
def('tandem_4', (p) => {
  const { w, d, H } = p, n = Math.max(2, Math.round(p.W / 0.57)), paso = p.W / n;
  p.c('acero', -w + 0.03, w - 0.03, -0.08, -0.02, 0.36, 0.41);
  for (const x of [-w + 0.3, w - 0.3]) {
    p.c('acero', x - 0.025, x + 0.025, -0.07, -0.03, 0.02, 0.36);
    p.c('acero', x - 0.03, x + 0.03, -d + 0.05, d - 0.08, 0, 0.03);
  }
  for (let k = 0; k < n; k++) {
    const x = -w + paso * (k + 0.5);
    p.c('tapiz', x - paso / 2 + 0.035, x + paso / 2 - 0.035, -0.18, d - 0.03, 0.41, 0.46);
    const g = p.sub([x, -0.18, 0.46], R2(-12));
    g.c('tapiz', -paso / 2 + 0.045, paso / 2 - 0.045, -0.05, 0, 0, H - 0.47);
    if (k > 0) p.c('negro', x - paso / 2 - 0.02, x - paso / 2 + 0.02, -0.1, d - 0.12, 0.46, 0.62);
  }
}, (p) => { p.c('acero', -p.w + 0.2, p.w - 0.2, -0.1, 0, 0, 0.41); p.c('tapiz', -p.w, p.w, -0.2, p.d, 0.41, 0.46); p.c('tapiz', -p.w, p.w, -p.d, -0.15, 0.46, p.H); });
def('silla_trabajo', (p) => {
  const { w, d, H } = p, zs = 0.48;
  estrella(p, 0, 0, Math.min(w, d) - 0.02);
  p.cv('negro', 0, 0, 0.08, 0.2, 0.03, 8);
  p.cv('acero', 0, 0, 0.2, zs - 0.06, 0.02, 8);
  p.c('negro', -0.12, 0.12, -0.12, 0.12, zs - 0.07, zs - 0.05);
  p.c('tapiz', -w + 0.07, w - 0.07, -d + 0.08, d - 0.04, zs - 0.05, zs + 0.03);
  p.c('negro', -0.025, 0.025, -d + 0.04, -d + 0.07, zs - 0.05, zs + 0.2);
  const g = p.sub([0, -d + 0.07, zs + 0.15], R2(-8));
  g.c('tapiz', -w + 0.09, w - 0.09, -0.05, 0, 0, H - zs - 0.16);
  for (const s of [-1, 1]) {
    p.c('negro', s * (w - 0.08) - 0.012, s * (w - 0.08) + 0.012, -0.04, 0, zs - 0.05, zs + 0.2);
    p.c('negro', s * (w - 0.08) - 0.03, s * (w - 0.08) + 0.03, -0.12, 0.12, zs + 0.2, zs + 0.23);
  }
}, L1.silla('tapiz', 0.5));
def('silla_laboratorio', (p) => {
  const { w, d, H } = p, zs = 0.66;
  estrella(p, 0, 0, Math.min(w, d) - 0.01);
  p.cv('negro', 0, 0, 0.08, 0.3, 0.032, 8);
  p.cv('acero', 0, 0, 0.3, zs - 0.04, 0.02, 8);
  for (let k = 0; k < 5; k++) { const a = R2(90 + k * 72 + 36); p.cb('acero', [Math.cos(a) * 0.2, Math.sin(a) * 0.2, 0.32], [Math.cos(a + R2(72)) * 0.2, Math.sin(a + R2(72)) * 0.2, 0.32], 0.01, 4); }
  p.cv('tapiz', 0, 0, zs - 0.04, zs + 0.04, Math.min(w, d) - 0.05, 12);
  p.c('acero', -0.02, 0.02, -d + 0.06, -d + 0.09, zs + 0.04, H - 0.12);
  p.c('tapiz', -0.15, 0.15, -d + 0.04, -d + 0.09, H - 0.17, H);
}, L1.silla('tapiz', 0.68));

// ---- muebles
def('puesto_trabajo', (p) => {
  const { w, d, H } = p, fd = Math.min(0.6, p.D * 0.38);
  const yd0 = -fd / 2 + (p.D >= 1.5 ? -d + 0.5 + fd / 2 : 0), yd1 = yd0 + fd;
  p.c('madera', -w, w, yd0, yd1, H - 0.03, H);
  for (const s of [-1, 1]) p.c('gris', s * (w - 0.025) - 0.02, s * (w - 0.025) + 0.02, yd0 + 0.03, yd1 - 0.03, 0, H - 0.03);
  p.c('gris', -w + 0.05, w - 0.05, yd1 - 0.04, yd1 - 0.02, 0.3, H - 0.03);
  p.c('blanco', w - 0.45, w - 0.06, yd0 + 0.04, yd1 - 0.06, 0.1, H - 0.05);
  cajones(p, w - 0.45, w - 0.06, yd0 + 0.04, 0.1, H - 0.05, 3, 'blanco', 'acero', 0.006, -1);
  sillaSimple(p.sub([0, -d + 0.24, 0], 0, 0), { alto: H, zs: 0.45 });
  for (const x of [-Math.min(0.3, w - 0.23), Math.min(0.3, w - 0.23)]) sillaSimple(p.sub([x, d - 0.23, 0], 0, Math.PI), { alto: H, zs: 0.45, ancho: 0.44, fondo: 0.42 });
}, (p) => { const fd = Math.min(0.6, p.D * 0.38), y0 = -fd / 2 + (p.D >= 1.5 ? -p.d + 0.5 + fd / 2 : 0); p.c('madera', -p.w, p.w, y0, y0 + fd, p.H - 0.04, p.H); p.c('gris', -p.w + 0.05, p.w - 0.05, y0 + 0.05, y0 + fd - 0.05, 0, p.H - 0.04); p.c('tapiz', -0.22, 0.22, -p.d, -p.d + 0.45, 0, 0.45); p.c('tapiz', -0.52, 0.52, p.d - 0.45, p.d, 0, 0.45); });
def('escritorio', (p) => {
  const { w, d, H } = p;
  p.c('madera', -w, w, -d, d, H - 0.03, H);
  p.c('gris', -w + 0.01, -w + 0.04, -d + 0.02, d - 0.02, 0, H - 0.03);
  p.c('gris', w - 0.42, w - 0.01, -d + 0.02, d - 0.04, 0.03, H - 0.03);
  cajones(p, w - 0.42, w - 0.01, d - 0.04, 0.05, H - 0.04, 3, 'blanco');
  p.c('gris', -w + 0.04, w - 0.42, -d + 0.02, -d + 0.04, 0.3, H - 0.03);
}, L1.mesa('madera', 'gris'));
def('mueble_recepcion', (p) => {
  const { w, d, H } = p, za = 0.8, xa = w - Math.min(0.95, p.W * 0.3);
  p.c('madera', -w + 0.02, w - 0.02, -d + 0.02, d - 0.12, 0.72, 0.75);
  p.c('blanco', -w, xa, d - 0.06, d, 0.05, H - 0.04);
  p.c('blanco', xa, w, d - 0.06, d, 0.05, za - 0.04);
  p.c('negro', -w + 0.02, w - 0.02, d - 0.05, d - 0.01, 0, 0.05);
  p.c('madera', -w, xa, d - 0.3, d, H - 0.04, H);
  p.c('madera', xa, w, d - 0.3, d, za - 0.04, za);
  p.c('tapiz', -w + 0.02, xa - 0.02, d, d + 0.004, H * 0.45, H * 0.55);
  for (const x of [-w, w - 0.04]) p.c('blanco', x, x + 0.04, -d, d - 0.06, 0, H - 0.04);
  p.c('blanco', -w + 0.04, -w + 0.5, -d + 0.02, d - 0.15, 0.05, 0.72);
  cajones(p, -w + 0.06, -w + 0.48, -d + 0.02, 0.08, 0.7, 3, 'blanco', 'acero', 0.006, -1);
}, (p) => { p.c('madera', -p.w, p.w, -p.d, p.d - 0.1, 0.7, 0.75); p.c('blanco', -p.w, p.w, p.d - 0.1, p.d, 0, p.H); p.c('blanco', -p.w, -p.w + 0.05, -p.d, p.d, 0, 0.75); p.c('blanco', p.w - 0.05, p.w, -p.d, p.d, 0, 0.75); });
def('estacion_enfermeria', (p) => {
  // mostrador en U (frente alto hacia +y, retornos a los lados); con fondo ≥ 1,3 m, mueble de apoyo contra la espalda
  const { w, d, H } = p, fondo = p.D >= 1.3, y0 = fondo ? -d + 0.55 : -d + 0.05, ret = Math.min(0.6, (p.D - (fondo ? 0.55 : 0.05)) * 0.5);
  p.c('blanco', -w, w, d - 0.06, d, 0.05, H - 0.04);
  for (const s of [-1, 1]) p.c('blanco', s * w - (s > 0 ? 0.06 : 0), s * w + (s < 0 ? 0.06 : 0), y0, d - 0.06, 0.05, H - 0.04);
  p.c('negro', -w + 0.02, w - 0.02, d - 0.05, d - 0.01, 0, 0.05);
  p.c('madera', -w, w, d - 0.3, d, H - 0.04, H);
  for (const s of [-1, 1]) p.c('madera', s * w - (s > 0 ? 0.3 : 0), s * w + (s < 0 ? 0.3 : 0), y0, d - 0.3, H - 0.04, H);
  p.c('madera', -w + 0.06, w - 0.06, d - 0.06 - ret, d - 0.06, 0.72, 0.75);
  for (const s of [-1, 1]) p.c('madera', s * (w - 0.06) - (s > 0 ? ret : 0), s * (w - 0.06) + (s < 0 ? ret : 0), y0, d - 0.06 - ret, 0.72, 0.75);
  p.c('tapiz', -w + 0.03, w - 0.03, d, d + 0.004, H * 0.45, H * 0.55);
  if (!fondo) return;
  p.c('blanco', -w + 0.4, w - 0.4, -d, -d + 0.45, 0, 0.9);
  p.c('granito', -w + 0.4, w - 0.4, -d, -d + 0.47, 0.9, 0.93);
  for (let k = 0; k < 4; k++) { const x0 = -w + 0.4 + k * (p.W - 0.8) / 4; p.c('blanco', x0 + 0.01, x0 + (p.W - 0.8) / 4 - 0.01, -d + 0.45, -d + 0.46, 0.08, 0.86); }
}, (p) => {
  const y0 = p.D >= 1.3 ? -p.d + 0.55 : -p.d + 0.05;
  p.c('blanco', -p.w, p.w, p.d - 0.3, p.d, 0, p.H); p.c('blanco', -p.w, -p.w + 0.3, y0, p.d - 0.3, 0, p.H); p.c('blanco', p.w - 0.3, p.w, y0, p.d - 0.3, 0, p.H);
  if (p.D >= 1.3) p.c('blanco', -p.w + 0.4, p.w - 0.4, -p.d, -p.d + 0.47, 0, 0.93);
});
function mueble(p, { cuerpo = 'blanco', tapa = 'granito', frentes = 'puertas', zTapa = p.H - 0.04, lab = false } = {}) {
  const { w, d } = p;
  p.c('negro', -w + 0.02, w - 0.02, -d, d - 0.06, 0, 0.1);
  p.c(cuerpo, -w, w, -d, d - 0.03, 0.1, zTapa);
  p.c(tapa, -w, w, -d, d, zTapa, zTapa + 0.04);
  if (lab) p.c(tapa, -w, w, -d, -d + 0.02, zTapa + 0.04, zTapa + 0.14);
  if (frentes === 'gavetas') {
    const n = Math.max(1, Math.round(p.W / 0.5)), a = p.W / n;
    for (let k = 0; k < n; k++) cajones(p, -w + k * a, -w + (k + 1) * a, d - 0.03, 0.11, zTapa - 0.01, 3, cuerpo);
  } else {
    const n = Math.max(1, Math.round(p.W / 0.5)), a = p.W / n;
    cajones(p, -w, w, d - 0.03, zTapa - 0.16, zTapa - 0.01, 1, cuerpo);
    for (let k = 0; k < n; k++) {
      const x0 = -w + k * a + 0.004, x1 = -w + (k + 1) * a - 0.004;
      p.c(cuerpo, x0, x1, d - 0.03, d - 0.018, 0.11, zTapa - 0.17);
      const xm = k % 2 ? x0 + 0.04 : x1 - 0.04;
      p.c('acero', xm - 0.008, xm + 0.008, d - 0.018, d - 0.005, zTapa - 0.32, zTapa - 0.2);
    }
  }
}
def('meson', (p) => {
  const v = p.v;
  if (v === 'inoxidable') mueble(p, { cuerpo: 'acero', tapa: 'aceroClaro' });
  else if (v === 'laboratorio') mueble(p, { cuerpo: 'blanco', tapa: 'resina', lab: true });
  else if (v === 'gavetas') mueble(p, { frentes: 'gavetas' });
  else mueble(p, { cuerpo: v === 'poceta' ? 'blanco' : 'blanco', tapa: v === 'poceta' ? 'aceroClaro' : 'granito' });
  if (v === 'poceta') {
    const x = p.w * 0.35, zt = p.H;
    p.c('aceroOsc', x - 0.22, x + 0.22, -0.18, 0.2, zt - 0.001, zt + 0.003);
    p.c('agua', x - 0.19, x + 0.19, -0.15, 0.17, zt + 0.003, zt + 0.005);
    p.cv('acero', x, -p.d + 0.06, zt, zt + 0.28, 0.014, 6);
    p.cb('acero', [x, -p.d + 0.06, zt + 0.28], [x, -p.d + 0.22, zt + 0.24], 0.012, 6);
    for (const s of [-1, 1]) p.cv('acero', x + s * 0.07, -p.d + 0.06, zt, zt + 0.06, 0.016, 6);
  }
}, (p) => {
  const tapa = p.v === 'laboratorio' ? 'resina' : p.v === 'inoxidable' ? 'aceroClaro' : 'granito';
  p.c(p.v === 'inoxidable' ? 'acero' : 'blanco', -p.w, p.w, -p.d, p.d - 0.03, 0, p.H - 0.04); p.c(tapa, -p.w, p.w, -p.d, p.d, p.H - 0.04, p.H);
  if (p.v === 'poceta') p.c('aceroOsc', p.w * 0.35 - 0.2, p.w * 0.35 + 0.2, -0.16, 0.18, p.H, p.H + 0.004);
});
def('mueble_bajo', (p) => mueble(p, { tapa: 'grisClaro' }), (p) => { p.c('blanco', -p.w, p.w, -p.d, p.d - 0.03, 0, p.H - 0.03); p.c('grisClaro', -p.w, p.w, -p.d, p.d, p.H - 0.03, p.H); });
def('vitrina', (p) => {
  const { w, d, H } = p;
  p.c('blanco', -w, w, -d, -d + 0.02, 0, H);
  for (const s of [-1, 1]) p.c('blanco', s * w - (s > 0 ? 0.025 : 0), s * w + (s < 0 ? 0.025 : 0), -d, d, 0, H);
  p.c('blanco', -w, w, -d, d, H - 0.04, H);
  p.c('blanco', -w, w, -d, d, 0, 0.12);
  const zs = [0.12, 0.55, 0.98, 1.4].map((z) => (z * H) / 1.8);
  zs.slice(1).forEach((z) => p.c('vidrio', -w + 0.025, w - 0.025, -d + 0.02, d - 0.03, z, z + 0.008, true));
  zs.forEach((z, i) => { const c = ['acero', 'azulEsteril', 'blanco', 'acero'][i]; p.c(c, -w + 0.08, -0.05, -d + 0.06, d - 0.08, z + 0.008, z + 0.07); p.c('acero', 0.05, w - 0.08, -d + 0.08, d - 0.1, z + 0.008, z + 0.05); });
  p.c('blanco', -0.012, 0.012, d - 0.03, d - 0.005, 0.12, H - 0.04);
  p.c('vidrio', -w + 0.025, w - 0.025, d - 0.025, d - 0.015, 0.12, H - 0.04, true);
  for (const s of [-1, 1]) p.c('acero', s * 0.04 - 0.006, s * 0.04 + 0.006, d - 0.015, d, H * 0.45, H * 0.6);
}, L1.vitrina());
def('estanteria', (p) => {
  const { w, d, H } = p, inox = p.v === 'inoxidable';
  for (const sx of [-1, 1]) for (const sy of [-1, 1]) p.c(inox ? 'acero' : 'grisClaro', sx * w - (sx > 0 ? 0.03 : 0), sx * w + (sx < 0 ? 0.03 : 0), sy * d - (sy > 0 ? 0.03 : 0), sy * d + (sy < 0 ? 0.03 : 0), 0, H);
  const n = 5;
  for (let k = 0; k < n; k++) {
    const z = 0.12 + (k * (H - 0.16)) / (n - 1);
    p.c(inox ? 'acero' : 'grisClaro', -w, w, -d, d, z - 0.02, z);
    if (k < n - 1) {
      const items = inox ? ['azulEsteril', 'blanco', 'azulEsteril'] : [['carton', 'blanco', 'azul'], ['blanco', 'carton', 'carton'], ['azul', 'carton', 'blanco'], ['carton', 'carton', 'blanco']][k];
      const anchos = [0.3, 0.26, 0.28];
      let x = -w + 0.05;
      items.forEach((c, i) => { const a = anchos[i] * (p.W / 1.0); const h = [0.22, 0.16, 0.25][(i + k) % 3] * Math.min(1, (H - 0.16) / 4 / 0.45); p.c(c, x, x + a - 0.02, -d + 0.04, d - 0.05, z, z + h); x += a; });
    }
  }
}, (p) => { p.c(p.v === 'inoxidable' ? 'acero' : 'grisClaro', -p.w, p.w, -p.d, p.d, 0, 0.12); p.c('carton', -p.w + 0.04, p.w - 0.04, -p.d + 0.04, p.d - 0.04, 0.12, p.H - 0.04); p.c(p.v === 'inoxidable' ? 'acero' : 'grisClaro', -p.w, p.w, -p.d, p.d, p.H - 0.04, p.H); });
def('lockers_6', (p) => {
  const { w, d, H } = p;
  p.c('gris', -w, w, -d, d - 0.02, 0.08, H);
  p.c('grisOsc', -w + 0.02, w - 0.02, -d, d - 0.04, 0, 0.08);
  const cols = 2, filas = 3, a = p.W / cols, h = (H - 0.1) / filas;
  for (let i = 0; i < cols; i++) for (let j = 0; j < filas; j++) {
    const x0 = -w + i * a + 0.008, x1 = -w + (i + 1) * a - 0.008, z0 = 0.09 + j * h + 0.006, z1 = 0.09 + (j + 1) * h - 0.006;
    p.c('tapizClaro', x0, x1, d - 0.02, d - 0.006, z0, z1);
    p.c('grisOsc', x0 + 0.04, x1 - 0.04, d - 0.006, d - 0.003, z1 - 0.07, z1 - 0.04);
    p.c('acero', x1 - 0.06, x1 - 0.035, d - 0.006, d, (z0 + z1) / 2 - 0.03, (z0 + z1) / 2 + 0.03);
  }
}, L1.frente('gris', 'tapizClaro', 0.05, 0.98));
def('gabinete_seguridad', (p) => {
  const { w, d, H } = p;
  p.c('grisOsc', -w, w, -d, d - 0.02, 0.05, H);
  for (const sx of [-1, 1]) for (const sy of [-1, 1]) p.c('negro', sx * (w - 0.05) - 0.03, sx * (w - 0.05) + 0.03, sy * (d - 0.06) - 0.03, sy * (d - 0.06) + 0.03, 0, 0.05);
  p.c('gris', -w + 0.02, w - 0.02, d - 0.02, d - 0.008, 0.08, H - 0.03);
  p.c('negro', w - 0.17, w - 0.06, d - 0.008, d, H * 0.55, H * 0.72);
  p.c('trazoVerde', w - 0.15, w - 0.08, d - 0.008, d + 0.001, H * 0.68, H * 0.7);
  p.c('acero', w - 0.13, w - 0.1, d - 0.008, d + 0.01, H * 0.38, H * 0.52);
  p.c('amarillo', -w + 0.08, -w + 0.26, d - 0.008, d - 0.002, H * 0.8, H * 0.88);
}, L1.frente('grisOsc', 'gris', 0.06, 0.97));
def('mesa_noche', (p) => {
  const { w, d, H } = p;
  ruedas(p, { r: 0.03, dx: w - 0.05, dy: d - 0.05, vastago: false });
  p.c('blanco', -w, w, -d, d - 0.015, 0.06, H - 0.03);
  p.c('maderaClara', -w - 0.01, w + 0.01, -d - 0.01, d + 0.01, H - 0.03, H);
  cajones(p, -w, w, d - 0.015, H - 0.2, H - 0.04, 1, 'tapizClaro');
  p.c('grisOsc', -w + 0.03, w - 0.03, d - 0.016, d - 0.012, H - 0.4, H - 0.22);
  p.c('blanco', -w + 0.005, w - 0.005, d - 0.015, d - 0.003, 0.08, H - 0.42);
  p.c('acero', w - 0.08, w - 0.06, d - 0.003, d + 0.01, H - 0.55, H - 0.47);
}, L1.mesa('maderaClara', 'blanco', 0.03));
def('mesa_puente', (p) => {
  const { w, d, H } = p, xc = -w + 0.06;
  p.c('gris', -w + 0.02, w - 0.08, -d + 0.03, -d + 0.08, 0.03, 0.07);
  p.c('gris', xc - 0.03, xc + 0.03, -d + 0.03, d - 0.03, 0.03, 0.07);
  for (const [x, y] of [[-w + 0.04, -d + 0.05], [w - 0.1, -d + 0.05], [xc, d - 0.05]]) p.c('negro', x - 0.02, x + 0.02, y - 0.02, y + 0.02, 0, 0.03);
  p.c('gris', xc - 0.03, xc + 0.03, -0.03, 0.03, 0.07, H - 0.25);
  p.c('acero', xc - 0.022, xc + 0.022, -0.022, 0.022, H - 0.25, H - 0.04);
  p.c('acero', xc - 0.04, xc + 0.04, -0.08, 0.08, H - 0.06, H - 0.03);
  p.c('maderaClara', -w, w, -d, d, H - 0.03, H);
  p.c('blanco', -w, w, d - 0.015, d, H - 0.05, H - 0.03);
}, (p) => { p.c('gris', -p.w + 0.02, -p.w + 0.1, -p.d, p.d, 0, p.H - 0.03); p.c('gris', -p.w, p.w - 0.1, -p.d, -p.d + 0.08, 0, 0.07); p.c('maderaClara', -p.w, p.w, -p.d, p.d, p.H - 0.03, p.H); });
def('mesa_mayo', (p) => {
  const { w, d, H } = p, xc = -w + 0.05;
  for (const s of [-1, 1]) { p.c('acero', -w + 0.02, w - 0.06, s * (d - 0.03) - 0.015, s * (d - 0.03) + 0.015, 0.035, 0.06); p.c('negro', w - 0.08, w - 0.05, s * (d - 0.03) - 0.015, s * (d - 0.03) + 0.015, 0, 0.035); }
  p.c('acero', xc - 0.015, xc + 0.015, -d + 0.03, d - 0.03, 0.035, 0.06);
  p.cv('acero', xc, 0, 0.06, H - 0.06, 0.016, 8);
  p.cv('aceroOsc', xc, 0, H * 0.55, H * 0.6, 0.022, 8);
  p.c('acero', xc - 0.01, xc + 0.04, -0.02, 0.02, H - 0.08, H - 0.03);
  p.c('acero', -w, w, -d, d, H - 0.03, H - 0.022);
  for (const s of [-1, 1]) { p.c('acero', -w, w, s * d - (s > 0 ? 0.008 : 0), s * d + (s < 0 ? 0.008 : 0), H - 0.022, H); p.c('acero', s * w - (s > 0 ? 0.008 : 0), s * w + (s < 0 ? 0.008 : 0), -d, d, H - 0.022, H); }
  p.c('azulEsteril', -w + 0.04, w - 0.04, -d + 0.04, d - 0.04, H - 0.022, H - 0.018);
}, (p) => { p.c('acero', -p.w, p.w, -p.d, p.d, 0, 0.06); p.c('acero', -p.w + 0.03, -p.w + 0.08, -0.025, 0.025, 0.06, p.H - 0.03); p.c('acero', -p.w, p.w, -p.d, p.d, p.H - 0.03, p.H); });
def('mesa_auxiliar', (p) => {
  const { w, d, H } = p;
  ruedas(p, { r: 0.035, dx: w - 0.04, dy: d - 0.04, vastago: false });
  patas(p, -w + 0.01, w - 0.01, -d + 0.01, d - 0.01, 0.07, H, 0.025, 'acero');
  p.c('acero', -w, w, -d, d, H - 0.03, H - 0.015);
  p.c('acero', -w + 0.01, w - 0.01, -d + 0.01, d - 0.01, 0.2, 0.215);
  p.c('acero', -w, w, -d, -d + 0.01, H - 0.015, H);
  for (const s of [-1, 1]) p.c('acero', s * w - (s > 0 ? 0.01 : 0), s * w + (s < 0 ? 0.01 : 0), -d, d, H - 0.015, H);
  p.c('azulEsteril', -w + 0.06, 0, -d + 0.06, d - 0.08, H - 0.015, H - 0.005);
}, (p) => { p.c('acero', -p.w + 0.02, p.w - 0.02, -p.d + 0.02, p.d - 0.02, 0, 0.215); p.c('acero', -p.w + 0.02, -p.w + 0.05, -p.d + 0.02, p.d - 0.02, 0.215, p.H); p.c('acero', p.w - 0.05, p.w - 0.02, -p.d + 0.02, p.d - 0.02, 0.215, p.H); p.c('acero', -p.w, p.w, -p.d, p.d, p.H - 0.03, p.H); });
def('riel_cortina', (p) => {
  // riel a lo largo de todo el ancho y la cortina antifluido recogida contra un extremo (pliegues hondos), con sus
  // ganchos: abierta, como se deja entre una atención y otra; el largo del riel es el del cubículo
  const { w, H } = p, rec = Math.min(p.W, Math.max(0.35, p.W * 0.28)), n = Math.min(14, Math.max(3, Math.round(rec / 0.09))), a = rec / n;
  p.c('acero', -w, w, -0.012, 0.012, H - 0.03, H);
  for (const x of [-w + 0.01, w - 0.01]) p.c('acero', x - 0.01, x + 0.01, -0.012, 0.012, H - 0.06, H);
  for (let k = 0; k < n; k++) {
    const x = -w + a * k, off = (k % 2 ? 1 : -1) * 0.028;
    p.c(k % 2 ? 'cortina' : 'cortinaOsc', x, x + a * 0.9, off - 0.008, off + 0.008, 0, H - 0.08);
    p.c('acero', x + a * 0.3, x + a * 0.6, -0.006, 0.006, H - 0.08, H - 0.03);
  }
  for (let k = 0; k < 6; k++) { const x = -w + rec + (k + 0.5) * (p.W - rec) / 6; p.c('acero', x - 0.006, x + 0.006, -0.006, 0.006, H - 0.06, H - 0.03); }
}, (p) => { const rec = Math.min(p.W, Math.max(0.35, p.W * 0.28)); p.c('acero', -p.w, p.w, -0.012, 0.012, p.H - 0.03, p.H); p.c('cortina', -p.w, -p.w + rec, -0.036, 0.036, 0, p.H - 0.03); });
def('escalerilla', (p) => {
  const { w, d, H } = p, h1 = H * 0.48;
  for (const s of [-1, 1]) {
    const x = s * (w - 0.015);
    p.cb('acero', [x, d - 0.02, 0], [x, d - 0.02, h1], 0.012, 6);
    p.cb('acero', [x, -d + 0.02, 0], [x, -d + 0.02, H - 0.03], 0.012, 6);
    p.cb('acero', [x, 0.0, 0], [x, 0.0, H - 0.03], 0.012, 6);
    p.cb('acero', [x, -d + 0.02, 0.05], [x, d - 0.02, 0.05], 0.01, 6);
  }
  p.c('acero', -w, w, 0, d, h1 - 0.02, h1);
  p.c('caucho', -w + 0.02, w - 0.02, 0.02, d - 0.02, h1, h1 + 0.008);
  p.c('acero', -w, w, -d, 0.02, H - 0.03, H - 0.01);
  p.c('caucho', -w + 0.02, w - 0.02, -d + 0.02, 0.0, H - 0.01, H);
}, (p) => { p.c('acero', -p.w, p.w, 0, p.d, 0, p.H * 0.5); p.c('acero', -p.w, p.w, -p.d, 0, 0, p.H); });
def('estiba', (p) => {
  const { w, d, H } = p, n = 5;
  for (const x of [-w + 0.05, 0, w - 0.05]) p.c('estiba', x - 0.05, x + 0.05, -d, d, 0.02, H - 0.025);
  for (const y of [-d + 0.05, d - 0.05]) p.c('estiba', -w, w, y - 0.05, y + 0.05, 0, 0.02);
  for (let k = 0; k < n; k++) { const y = -d + ((k + 0.5) * p.D) / n; p.c('estiba', -w, w, y - p.D / n / 2 + 0.02, y + p.D / n / 2 - 0.02, H - 0.025, H); }
}, (p) => { p.c('estiba', -p.w, p.w, -p.d, p.d, p.H - 0.03, p.H); p.c('estiba', -p.w, p.w, -p.d, p.d, 0, 0.02); p.c('estiba', -0.05, 0.05, -p.d, p.d, 0.02, p.H - 0.03); });
def('canecas_residuos', (p) => {
  const { w, d, H } = p, wg = Math.min(0.18, p.W * 0.2), a = (p.W - wg) / 3;
  ['rojo', 'verde', 'negro'].forEach((c, i) => {
    const x0 = -w + i * a + 0.01, x1 = -w + (i + 1) * a - 0.01;
    p.c(c, x0 + 0.01, x1 - 0.01, -d + 0.02, d - 0.03, 0, H - 0.06);
    p.c(c === 'negro' ? 'grisOsc' : c === 'verde' ? 'verdeSenal' : 'rojoOsc', x0, x1, -d + 0.01, d - 0.02, H - 0.06, H - 0.02);
    p.c('negro', (x0 + x1) / 2 - 0.05, (x0 + x1) / 2 + 0.05, d - 0.03, d, 0.01, 0.04);
    p.c('blanco', (x0 + x1) / 2 - 0.04, (x0 + x1) / 2 + 0.04, d - 0.03, d - 0.028, H * 0.45, H * 0.6);
  });
  p.c('acero', w - wg, w, -d, -d + 0.03, 0, H * 0.8);
  p.c('rojo', w - wg + 0.02, w - 0.01, -d + 0.03, -d + 0.03 + wg * 0.9, H * 0.55, H * 0.8);
  p.c('amarillo', w - wg + 0.03, w - 0.02, -d + 0.04, -d + 0.02 + wg * 0.9, H * 0.8, H * 0.84);
}, (p) => { const a = p.W / 4; ['rojo', 'verde', 'negro'].forEach((c, i) => p.c(c, -p.w + i * a + 0.01, -p.w + (i + 1) * a - 0.01, -p.d, p.d, 0, p.H - 0.02)); p.c('rojo', p.w - a + 0.02, p.w, -p.d, 0, p.H * 0.55, p.H * 0.82); });
def('lavaojos_ducha', (p) => {
  const { w, d, H } = p, xp = -w + 0.08, yp = -d + 0.08;
  p.c('amarillo', xp - 0.1, xp + 0.1, yp - 0.07, yp + 0.1, 0, 0.02);
  p.cv('amarillo', xp, yp, 0, H - 0.03, 0.028, 8);
  p.cb('amarillo', [xp, yp, H - 0.05], [0, 0, H - 0.05], 0.022, 6);
  p.cv('verdeSenal', 0, 0, H - 0.2, H - 0.07, 0.15, 12, 0.04);
  p.cb('acero', [xp + 0.12, yp + 0.12, H - 0.06], [xp + 0.12, yp + 0.12, 1.55], 0.006, 4);
  p.c('verdeSenal', xp + 0.08, xp + 0.16, yp + 0.1, yp + 0.14, 1.5, 1.56);
  p.cb('amarillo', [xp, yp, 1.0], [0.05, 0.05, 1.0], 0.02, 6);
  p.cv('verdeSenal', 0.05, 0.05, 1.0, 1.08, 0.08, 12, 0.14);
  p.c('verdeSenal', 0.15, 0.25, 0.0, 0.12, 0.98, 1.0);
}, (p) => { p.c('amarillo', -p.w, -p.w + 0.16, -p.d, -p.d + 0.16, 0, p.H); p.c('verdeSenal', -0.15, 0.15, -0.15, 0.15, p.H - 0.2, p.H - 0.05); p.c('verdeSenal', -0.1, 0.2, -0.1, 0.2, 0.95, 1.08); });

// ---- terapia
def('barras_paralelas', (p) => {
  const { w, d, H } = p;
  p.c('madera', -w, w, -d, d, 0, 0.05);
  for (const s of [-1, 1]) {
    const x = s * (w - 0.08);
    p.cb('acero', [x, -d + 0.02, H - 0.03], [x, d - 0.02, H - 0.03], 0.02, 8);
    for (const y of [-d + 0.1, 0, d - 0.1]) { p.c('aceroOsc', x - 0.03, x + 0.03, y - 0.03, y + 0.03, 0.05, 0.12); p.cv('acero', x, y, 0.12, H - 0.04, 0.02, 6); }
  }
  p.c('caucho', -w + 0.15, w - 0.15, -d + 0.05, d - 0.05, 0.05, 0.055);
}, (p) => { p.c('madera', -p.w, p.w, -p.d, p.d, 0, 0.05); p.c('acero', -p.w + 0.05, -p.w + 0.1, -p.d, p.d, 0.05, p.H); p.c('acero', p.w - 0.1, p.w - 0.05, -p.d, p.d, 0.05, p.H); });
def('escalera_rehabilitacion', (p) => {
  const { w, d, H } = p, zP = Math.min(0.6, H * 0.45), n = 4, yP0 = -0.2, yP1 = 0.2;
  const huella = (d - yP1) / n;
  for (let k = 0; k < n; k++) {
    const z = (zP * (k + 1)) / (n + 0);
    p.c('madera', -w + 0.08, w - 0.08, yP1 + (n - 1 - k) * huella, yP1 + (n - k) * huella, 0, z);
    p.c('madera', -w + 0.08, w - 0.08, yP0 - (n - k) * huella, yP0 - (n - 1 - k) * huella, 0, z);
  }
  p.c('maderaClara', -w + 0.08, w - 0.08, yP0, yP1, 0, zP);
  for (const s of [-1, 1]) {
    const x = s * (w - 0.03);
    const hb = Math.min(0.85, H - zP - 0.03);
    for (const y of [-d + 0.05, yP0, yP1, d - 0.05]) p.cv('acero', x, y, 0, (Math.abs(y) < 0.3 ? zP : 0.05) + hb, 0.018, 6);
    p.cb('acero', [x, d - 0.05, 0.05 + hb], [x, yP1, zP + hb], 0.02, 6);
    p.cb('acero', [x, yP1, zP + hb], [x, yP0, zP + hb], 0.02, 6);
    p.cb('acero', [x, yP0, zP + hb], [x, -d + 0.05, 0.05 + hb], 0.02, 6);
  }
}, (p) => { const z = Math.min(0.6, p.H * 0.45); p.c('madera', -p.w + 0.08, p.w - 0.08, -0.6, 0.6, 0, z); p.c('madera', -p.w + 0.08, p.w - 0.08, -p.d, p.d, 0, z * 0.4); p.c('acero', -p.w, -p.w + 0.05, -p.d, p.d, z, p.H); p.c('acero', p.w - 0.05, p.w, -p.d, p.d, z, p.H); });
def('banda_caminadora', (p) => {
  const { w, d, H } = p;
  p.c('grisOsc', -w + 0.02, w - 0.02, -d + 0.15, d, 0, 0.17);
  p.c('negro', -w + 0.1, w - 0.1, -d + 0.2, d - 0.04, 0.17, 0.19);
  for (const s of [-1, 1]) p.c('gris', s * (w - 0.06) - 0.04, s * (w - 0.06) + 0.04, -d + 0.15, d, 0.17, 0.2);
  p.c('grisOsc', -w + 0.02, w - 0.02, -d, -d + 0.15, 0, 0.25);
  for (const s of [-1, 1]) {
    p.cb('gris', [s * (w - 0.06), -d + 0.12, 0.2], [s * (w - 0.06), -d + 0.05, H - 0.2], 0.03, 6);
    p.cb('acero', [s * (w - 0.06), -d + 0.1, H - 0.4], [s * (w - 0.06), -d + 0.6, H - 0.4], 0.016, 6);
  }
  const f = p.sub([0, -d + 0.14, H - 0.2], R2(25));
  f.c('gris', -w + 0.05, w - 0.05, -0.05, 0.12, 0, 0.18);
  f.c('pantalla', -0.15, 0.15, 0.12, 0.125, 0.04, 0.15);
  f.c('trazoCian', -0.12, -0.02, 0.125, 0.127, 0.1, 0.12);
}, (p) => { p.c('grisOsc', -p.w, p.w, -p.d, p.d, 0, 0.2); p.c('gris', -p.w + 0.03, -p.w + 0.08, -p.d, -p.d + 0.15, 0.2, p.H); p.c('gris', p.w - 0.08, p.w - 0.03, -p.d, -p.d + 0.15, 0.2, p.H); p.c('gris', -p.w, p.w, -p.d, -p.d + 0.2, p.H - 0.2, p.H); });
def('bicicleta_estatica', (p) => {
  const { w, d, H } = p;
  for (const y of [-d + 0.05, d - 0.05]) p.cb('grisOsc', [-w + 0.02, y, 0.03], [w - 0.02, y, 0.03], 0.03, 6);
  p.cb('gris', [0, d - 0.05, 0.05], [0, -d + 0.15, 0.62], 0.035, 6);
  p.cb('gris', [0, -d + 0.05, 0.05], [0, d * 0.2, 0.5], 0.03, 6);
  p.cb('grisOsc', [-0.03, -d + 0.2, 0.32], [0.03, -d + 0.2, 0.32], 0.2, 14);
  p.cb('acero', [-0.035, -d + 0.2, 0.32], [0.035, -d + 0.2, 0.32], 0.05, 8);
  p.cb('gris', [0, d * 0.2, 0.5], [0, d * 0.25, 0.85], 0.022, 6);
  p.c('negro', -0.09, 0.09, d * 0.25 - 0.06, d * 0.25 + 0.14, 0.85, 0.9);
  p.cb('gris', [0, -d + 0.15, 0.62], [0, -d + 0.1, H - 0.15], 0.025, 6);
  p.cb('negro', [-w + 0.05, -d + 0.08, H - 0.15], [w - 0.05, -d + 0.08, H - 0.15], 0.016, 6);
  const f = p.sub([0, -d + 0.1, H - 0.12], R2(30));
  f.c('gris', -0.1, 0.1, -0.02, 0.04, 0, 0.12);
  f.c('pantalla', -0.08, 0.08, 0.04, 0.042, 0.02, 0.1);
  for (const s of [-1, 1]) { p.cb('acero', [0, d * 0.05, 0.3], [s * 0.12, d * 0.05, 0.3], 0.012, 4); p.c('negro', s * 0.12 - 0.04 * (s < 0 ? 1 : 0), s * 0.12 + 0.04 * (s > 0 ? 1 : 0), d * 0.05 - 0.05, d * 0.05 + 0.05, 0.28, 0.32); }
}, (p) => { p.c('grisOsc', -p.w, p.w, -p.d, p.d, 0, 0.06); p.c('grisOsc', -0.05, 0.05, -p.d + 0.05, -p.d + 0.4, 0.06, 0.55); p.c('gris', -0.05, 0.05, -0.05, 0.2, 0.06, 0.9); p.c('gris', -p.w + 0.05, p.w - 0.05, -p.d, -p.d + 0.15, 0.9, p.H); });
def('espejo_postural', (p) => {
  const { w, d, H } = p;
  for (const s of [-1, 1]) {
    p.c('gris', s * (w - 0.05) - 0.03, s * (w - 0.05) + 0.03, -d, d, 0.04, 0.08);
    for (const sy of [-1, 1]) p.c('negro', s * (w - 0.05) - 0.02, s * (w - 0.05) + 0.02, sy * (d - 0.04) - 0.02, sy * (d - 0.04) + 0.02, 0, 0.04);
  }
  p.c('gris', -w, w, -0.03, 0.03, 0.08, H);
  p.c('espejo', -w + 0.03, w - 0.03, 0.03, 0.035, 0.12, H - 0.04);
  for (let k = 1; k < 4; k++) { const x = -w + (k * p.W) / 4; p.c('grisOsc', x - 0.003, x + 0.003, 0.035, 0.037, 0.12, H - 0.04); }
  for (let k = 1; k < 7; k++) { const z = 0.12 + (k * (H - 0.16)) / 7; p.c('grisOsc', -w + 0.03, w - 0.03, 0.035, 0.037, z - 0.003, z + 0.003); }
}, (p) => { p.c('gris', -p.w, p.w, -p.d, p.d, 0, 0.08); p.c('gris', -p.w, p.w, -0.03, 0.03, 0.08, p.H); p.c('espejo', -p.w + 0.03, p.w - 0.03, 0.03, 0.035, 0.12, p.H - 0.04); });
def('kit_rehabilitacion', (p) => {
  const { w, d, H } = p;
  for (const s of [-1, 1]) p.c('maderaClara', s * w - (s > 0 ? 0.025 : 0), s * w + (s < 0 ? 0.025 : 0), -d, d, 0, H);
  p.c('maderaClara', -w, w, -d, -d + 0.02, 0, H);
  for (const z of [0.05, H * 0.5, H - 0.02]) p.c('maderaClara', -w, w, -d, d, z - 0.02, z);
  p.es('rojo', -w + 0.18, 0.02, 0.05 + 0.15, 0.15);
  p.es('verde', -w + 0.48, 0.02, 0.05 + 0.13, 0.13);
  for (const x of [w - 0.3, w - 0.12]) { p.cb('grisOsc', [x - 0.06, 0, H * 0.5 + 0.035], [x + 0.06, 0, H * 0.5 + 0.035], 0.012, 6); for (const s of [-1, 1]) p.cv('azul', x + s * 0.06, 0, H * 0.5, H * 0.5 + 0.07, 0.035, 8); }
  p.cv('naranja', -w + 0.15, 0, H * 0.5, H * 0.5 + 0.15, 0.07, 8, 0.012);
  p.cb('amarillo', [-w + 0.3, 0.05, H * 0.5 + 0.02], [-w + 0.45, -0.05, H * 0.5 + 0.02], 0.02, 6);
  p.c('celeste', 0.0, w - 0.05, -d + 0.03, d - 0.04, 0.05, 0.12);
}, (p) => { p.c('maderaClara', -p.w, p.w, -p.d, p.d, 0, 0.05); p.c('maderaClara', -p.w, p.w, -p.d, -p.d + 0.03, 0.05, p.H); p.c('rojo', -p.w + 0.05, 0, -p.d + 0.05, p.d - 0.05, 0.05, 0.35); p.c('azul', 0.05, p.w - 0.05, -p.d + 0.05, p.d - 0.05, p.H * 0.5, p.H * 0.6); });
def('compresero', (p) => {
  const { w, d, H } = p;
  patas(p, -w + 0.04, w - 0.04, -d + 0.04, d - 0.04, 0, 0.25, 0.03, 'acero');
  p.c('acero', -w, w, -d, d, 0.25, H - 0.04);
  p.c('aceroClaro', -w - 0.005, w + 0.005, -d - 0.005, d + 0.005, H - 0.04, H);
  p.c('negro', -0.12, 0.12, d - 0.06, d - 0.03, H, H + 0.005);
  p.c('grisOsc', w - 0.2, w - 0.04, d, d + 0.005, H - 0.2, H - 0.1);
  p.cv('negro', w - 0.08, d + 0.005, H - 0.17, H - 0.13, 0.015, 6);
  p.c('acero', -w + 0.04, w - 0.04, -d + 0.04, d - 0.04, 0.06, 0.08);
}, (p) => { p.c('acero', -p.w + 0.04, p.w - 0.04, -p.d + 0.04, p.d - 0.04, 0, 0.25); p.c('acero', -p.w, p.w, -p.d, p.d, 0.25, p.H - 0.04); p.c('aceroClaro', -p.w, p.w, -p.d, p.d, p.H - 0.04, p.H); });

// ---- carros y atriles
def('carro_paro', (p) => {
  const { w, d, H } = p, xb = w - 0.1;
  ruedas(p, { r: 0.05, dx: xb - 0.06, dy: d - 0.08 });
  p.c('grisOsc', -xb, xb, -d + 0.02, d - 0.02, 0.12, 0.16);
  p.c('rojo', -xb, xb, -d + 0.02, d - 0.03, 0.16, H - 0.06);
  cajones(p, -xb, xb, d - 0.03, 0.18, H - 0.08, 5, 'rojo', 'blanco', 0.012);
  p.c('grisOsc', -xb - 0.01, xb + 0.01, -d, d, H - 0.06, H - 0.03);
  for (const s of [-1, 1]) p.c('grisOsc', s * xb - (s > 0 ? 0 : 0.01), s * xb + (s > 0 ? 0.01 : 0), -d, d, H - 0.03, H);
  p.c('grisOsc', -xb, xb, -d, -d + 0.01, H - 0.03, H);
  p.c('acero', -xb - 0.04, -xb, -d + 0.08, d - 0.08, H - 0.2, H - 0.17);
  p.cv('oxigeno', -xb - 0.05, -0.04, 0.2, 0.75, 0.045, 8);
  p.c('negro', -xb - 0.065, -xb - 0.035, -0.07, -0.01, 0.75, 0.8);
  p.c('negro', -xb + 0.05, xb - 0.05, -d, -d + 0.02, 0.25, H - 0.1);
  p.c('amarillo', xb, xb + 0.06, -0.12, 0.12, 0.5, 0.8);
}, (p) => { p.c('rojo', -p.w + 0.1, p.w - 0.1, -p.d, p.d, 0.12, p.H - 0.05); p.c('grisOsc', -p.w + 0.08, p.w - 0.08, -p.d, p.d, p.H - 0.05, p.H); p.c('grisOsc', -p.w + 0.12, p.w - 0.12, -p.d + 0.04, p.d - 0.04, 0, 0.12); p.c('oxigeno', -p.w, -p.w + 0.1, -0.08, 0.04, 0.2, 0.75); });
def('carro_curaciones', (p) => {
  const { w, d, H } = p;
  ruedas(p, { r: 0.04, dx: w - 0.04, dy: d - 0.04, vastago: false });
  patas(p, -w + 0.02, w - 0.02, -d + 0.02, d - 0.02, 0.08, H, 0.022, 'acero');
  for (const z of [0.2, 0.55, H - 0.02]) p.c('acero', -w + 0.01, w - 0.01, -d + 0.01, d - 0.01, z - 0.015, z);
  p.c('acero', -w + 0.01, w - 0.01, -d + 0.01, -d + 0.02, H - 0.02, H);
  p.cv('acero', w - 0.08, d - 0.1, 0.2, 0.42, 0.08, 10);
  p.c('azulEsteril', -w + 0.05, 0, -d + 0.05, d - 0.06, H - 0.02, H);
  p.c('blanco', -w + 0.06, -0.05, -d + 0.06, d - 0.1, 0.55, 0.65);
  p.c('azulEsteril', 0.0, w - 0.06, -d + 0.06, d - 0.08, 0.55, 0.6);
  p.c('carton', -w + 0.06, 0.1, -d + 0.06, d - 0.08, 0.2, 0.3);
}, (p) => { p.c('acero', -p.w, p.w, -p.d, p.d, 0, 0.2); p.c('acero', -p.w, -p.w + 0.03, -p.d, p.d, 0.2, p.H); p.c('acero', p.w - 0.03, p.w, -p.d, p.d, 0.2, p.H); p.c('acero', -p.w, p.w, -p.d, p.d, p.H - 0.03, p.H); });
def('carro_medicamentos', (p) => {
  const { w, d, H } = p, xb = w - 0.06;
  ruedas(p, { r: 0.045, dx: xb - 0.05, dy: d - 0.07 });
  p.c('grisOsc', -xb, xb, -d + 0.02, d - 0.02, 0.11, 0.15);
  p.c('blanco', -xb, xb, -d + 0.02, d - 0.03, 0.15, H - 0.05);
  const cols = 3, filas = 5, a = (2 * xb) / cols, h = (H - 0.26) / filas;
  for (let i = 0; i < cols; i++) for (let j = 0; j < filas; j++) {
    const x0 = -xb + i * a + 0.006, x1 = -xb + (i + 1) * a - 0.006, z0 = 0.17 + j * h + 0.005, z1 = 0.17 + (j + 1) * h - 0.005;
    p.c(['tapizClaro', 'celeste', 'tapizClaro', 'amarillo', 'tapizClaro'][j], x0, x1, d - 0.03, d - 0.016, z0, z1);
    p.c('blanco', (x0 + x1) / 2 - 0.02, (x0 + x1) / 2 + 0.02, d - 0.016, d - 0.008, z1 - 0.025, z1 - 0.012);
  }
  p.c('grisClaro', -w + 0.02, w - 0.02, -d, d, H - 0.05, H);
  p.cb('acero', [-xb - 0.03, -d + 0.08, H - 0.12], [-xb - 0.03, d - 0.08, H - 0.12], 0.012, 6);
  p.c('negro', xb - 0.1, xb - 0.02, d - 0.012, d, H - 0.12, H - 0.07);
}, L1.frente('blanco', 'tapizClaro', 0.17, 0.92));
def('carro_ropa', (p) => {
  const { w, d, H } = p;
  ruedas(p, { r: 0.045, dx: w - 0.05, dy: d - 0.05, vastago: false });
  patas(p, -w + 0.02, w - 0.02, -d + 0.02, d - 0.02, 0.09, H - 0.02, 0.022, 'acero');
  p.c('acero', -w + 0.01, w - 0.01, -d + 0.01, d - 0.01, 0.09, 0.11);
  p.c('celeste', -w + 0.04, w - 0.04, -d + 0.04, d - 0.04, 0.2, H - 0.06);
  for (const y of [-d + 0.015, d - 0.015]) p.c('acero', -w + 0.01, w - 0.01, y - 0.012, y + 0.012, H - 0.04, H - 0.015);
  for (const x of [-w + 0.015, w - 0.015]) p.c('acero', x - 0.012, x + 0.012, -d + 0.01, d - 0.01, H - 0.04, H - 0.015);
  p.c('tapizClaro', -w + 0.02, w - 0.02, -d + 0.02, d - 0.02, H - 0.015, H);
  p.c('blanco', -w + 0.08, w - 0.08, d - 0.042, d - 0.04, 0.4, 0.6);
}, (p) => { p.c('acero', -p.w, p.w, -p.d, p.d, 0, 0.11); p.c('celeste', -p.w + 0.03, p.w - 0.03, -p.d + 0.03, p.d - 0.03, 0.11, p.H - 0.02); p.c('tapizClaro', -p.w, p.w, -p.d, p.d, p.H - 0.02, p.H); });
def('carro_cerrado', (p) => {
  const { w, d, H } = p;
  ruedas(p, { r: 0.06, dx: w - 0.08, dy: d - 0.08 });
  p.c('acero', -w + 0.02, w - 0.02, -d + 0.02, d - 0.02, 0.15, H);
  p.c('grisOsc', -w, w, -d, d, 0.13, 0.17);
  for (const s of [-1, 1]) {
    p.c('aceroClaro', s > 0 ? 0.004 : -w + 0.04, s > 0 ? w - 0.04 : -0.004, d - 0.02, d - 0.008, 0.22, H - 0.06);
    p.c('negro', s * 0.03 - 0.01, s * 0.03 + 0.01, d - 0.008, d, H * 0.45, H * 0.65);
  }
  p.cb('acero', [-w + 0.02, -d, H - 0.18], [-w + 0.02, d, H - 0.18], 0.014, 6);
}, (p) => { p.c('acero', -p.w, p.w, -p.d, p.d, 0.12, p.H); p.c('grisOsc', -p.w + 0.08, p.w - 0.08, -p.d + 0.08, p.d - 0.08, 0, 0.12); p.c('aceroClaro', -p.w + 0.04, p.w - 0.04, p.d - 0.005, p.d + 0.004, 0.2, p.H - 0.06); });
def('carro_equipo', (p) => {
  const { w, d, H } = p;
  estrella(p, 0, 0, Math.min(w, d) - 0.01);
  p.cv('acero', 0, 0, 0.08, H - 0.04, 0.022, 8);
  p.c('grisClaro', -0.2, 0.2, -0.17, 0.17, H - 0.04, H);
  p.c('acero', -0.15, 0.15, -0.12, 0.12, 0.35, 0.37);
  for (const s of [-1, 1]) p.c('acero', s * 0.15 - 0.005, s * 0.15 + 0.005, -0.12, 0.12, 0.37, 0.45);
  p.c('acero', -0.15, 0.15, -0.125, -0.115, 0.37, 0.45);
  p.c('acero', -0.15, 0.15, 0.115, 0.125, 0.37, 0.45);
  p.cb('acero', [-0.2, 0.17, H - 0.02], [0.2, 0.17, H - 0.02], 0.01, 6);
}, (p) => { p.c('grisOsc', -p.w, p.w, -p.d, p.d, 0, 0.08); p.c('acero', -0.025, 0.025, -0.025, 0.025, 0.08, p.H - 0.04); p.c('grisClaro', -0.2, 0.2, -0.17, 0.17, p.H - 0.04, p.H); });
def('atril', (p) => {
  const { w, d, H } = p;
  estrella(p, 0, 0, Math.min(w, d) - 0.01, 'acero');
  p.cv('acero', 0, 0, 0.08, H - 0.02, 0.013, 8);
  p.cv('aceroOsc', 0, 0, H * 0.6, H * 0.62, 0.02, 8);
  for (let k = 0; k < 4; k++) {
    const a = R2(45 + k * 90), x = Math.cos(a) * 0.12, y = Math.sin(a) * 0.12;
    p.cb('acero', [0, 0, H - 0.04], [x, y, H - 0.04], 0.006, 4);
    p.cb('acero', [x, y, H - 0.04], [x, y, H - 0.08], 0.005, 4);
  }
  p.c('acrilico', 0.05, 0.15, 0.04, 0.1, H - 0.32, H - 0.1, true);
  p.c('blanco', 0.05, 0.15, 0.04, 0.1, H - 0.24, H - 0.12);
  p.cb('acrilico', [0.1, 0.07, H - 0.32], [0.02, 0.02, 1.2], 0.003, 4, 0.003, true);
}, L1.poste('acero', 'acrilico', 0.3));

// ---- biomédicos
def('desfibrilador', (p) => {
  // cuerpo con el tablero inclinado al frente (pantalla con trazos, perilla de energía), paletas arriba y asa
  const { w, d, H } = p, zf = H * 0.42, a = R2(28), L = H * 0.32;
  p.c('crema', -w, w, -d, d, 0, zf);
  p.c('crema', -w, w, -d, d - 0.012 - L * Math.sin(a), zf, H * 0.72);
  const f = p.sub([0, d - 0.006, zf], a);
  f.c('grisOsc', -w + 0.006, w - 0.006, -0.012, 0, 0, L);
  pantalla(f, -w + 0.02, w * 0.3, L * 0.12, L * 0.92, 0.0, { marco: 'negro', fondo: 0.003, trazos: true, borde: 0.006 });
  f.cb('amarillo', [w * 0.62, 0.0, L * 0.55], [w * 0.62, 0.016, L * 0.55], 0.026, 10);
  f.c('rojo', w * 0.45, w - 0.02, 0, 0.004, L * 0.1, L * 0.28);
  p.c('grisOsc', -w + 0.01, w - 0.01, d - 0.004, d, H * 0.06, zf - 0.02);
  for (const s of [-1, 1]) {
    p.c('grisOsc', s * w * 0.5 - 0.06, s * w * 0.5 + 0.06, -d + 0.02, -d + 0.14, H * 0.72, H * 0.82);
    p.c('amarillo', s * w * 0.5 - 0.05, s * w * 0.5 + 0.05, -d + 0.03, -d + 0.13, H * 0.82, H * 0.86);
  }
  p.cb('grisOsc', [-w + 0.04, -0.0, H * 0.95], [w - 0.04, 0.0, H * 0.95], 0.012, 6);
  for (const s of [-1, 1]) p.c('grisOsc', s * (w - 0.05) - 0.01, s * (w - 0.05) + 0.01, -0.01, 0.01, H * 0.72, H * 0.95);
}, L1.frente('crema', 'grisOsc', 0.0, 0.85));
def('dea_gabinete', (p) => {
  const { w, d, H } = p;
  p.c('blanco', -w, w, -d, d - 0.02, 0, H - 0.1);
  p.c('vidrio', -w + 0.02, w - 0.02, d - 0.02, d - 0.01, 0.02, H - 0.12, true);
  p.c('blanco', -w, w, d - 0.02, d, H - 0.13, H - 0.1);
  p.c('verdeSenal', -w, w, -d, d, H - 0.1, H);
  p.c('blanco', -0.03, 0.03, d, d + 0.002, H - 0.08, H - 0.02);
  p.c('blanco', -0.06, 0.06, d, d + 0.002, H - 0.058, H - 0.042);
  p.c('trazoVerde', -0.12, 0.12, -d + 0.03, d - 0.05, 0.05, 0.3);
  p.c('amarillo', -0.11, 0.11, d - 0.06, d - 0.05, 0.2, 0.28);
}, (p) => { p.c('blanco', -p.w, p.w, -p.d, p.d, 0, p.H - 0.1); p.c('verdeSenal', -p.w, p.w, -p.d, p.d, p.H - 0.1, p.H); });
function monitorCuerpo(f, W, D, H) {
  const w = W / 2, d = D / 2;
  f.c('crema', -w, w, -d + 0.04, d - 0.01, 0.02, H - 0.02);
  pantalla(f, -w + 0.012, w - 0.06, 0.04, H - 0.04, d - 0.01, { marco: 'grisOsc', fondo: 0.004, trazos: true, borde: 0.008 });
  f.c('grisOsc', w - 0.05, w - 0.012, d - 0.011, d - 0.006, 0.05, H - 0.06);
  f.cv('trazoVerde', w - 0.031, d - 0.006, H * 0.55, H * 0.57, 0.01, 6);
  f.c('grisOsc', -w * 0.6, w * 0.6, -d + 0.04, -d + 0.07, H - 0.02, H);
}
def('monitor_signos', (p) => {
  const { w, d, H } = p;
  if (p.v === 'pedestal' || H > 0.8) {
    estrella(p, 0, 0, Math.min(w, d) - 0.01);
    p.cv('acero', 0, 0, 0.08, H - 0.28, 0.018, 8);
    p.c('grisOsc', -0.12, 0.12, -0.08, 0.08, H * 0.6, H * 0.6 + 0.08);
    p.c('grisOsc', -0.06, 0.06, -0.05, 0.05, H - 0.3, H - 0.28);
    monitorCuerpo(p.sub([0, 0, H - 0.3]), 0.3, 0.18, 0.3);
    return;
  }
  p.c('gris', -0.05, 0.05, -d, -d + 0.04, H * 0.25, H * 0.75);
  monitorCuerpo(p, p.W, p.D, H);
}, (p) => { if (p.H > 0.8) { L1.poste('grisOsc', 'crema', 0.3)(p); return; } p.c('crema', -p.w, p.w, -p.d, p.d - 0.01, 0, p.H); p.c('pantalla', -p.w + 0.02, p.w - 0.05, p.d - 0.01, p.d, 0.04, p.H - 0.04); });
def('electrocardiografo', (p) => {
  const { w, d, H } = p;
  p.c('crema', -w, w, -d, d, 0, H * 0.55);
  p.c('grisOsc', -w + 0.03, w * 0.4, 0.02, d - 0.03, H * 0.55, H * 0.58);
  for (let i = 0; i < 4; i++) for (let j = 0; j < 3; j++) p.c(i === 3 && j === 0 ? 'trazoVerde' : 'gris', -w + 0.04 + i * 0.05, -w + 0.08 + i * 0.05, 0.03 + j * 0.04, 0.055 + j * 0.04, H * 0.58, H * 0.62);
  p.c('blanco', w * 0.45, w - 0.03, 0.02, d - 0.03, H * 0.55, H * 0.58);
  p.c('rosado', w * 0.5, w - 0.06, d - 0.05, d, H * 0.4, H * 0.55);
  const f = p.sub([0, -0.005, H * 0.55], R2(70));
  f.c('crema', -w + 0.03, w - 0.03, -0.01, 0.0, 0, 0.15);
  f.c('pantalla', -w + 0.045, w - 0.045, 0.0, 0.002, 0.015, 0.135);
  f.c('trazoVerde', -w + 0.06, w - 0.06, 0.002, 0.003, 0.095, 0.099);
  f.c('trazoVerde', -w + 0.06, w - 0.06, 0.002, 0.003, 0.06, 0.064);
}, L1.mesa('pantalla', 'crema', 0.02));
def('bomba_infusion', (p) => {
  const { w, d, H } = p;
  p.c('crema', -w, w, -d + 0.04, d - 0.008, 0, H - 0.02);
  p.c('grisOsc', -w * 0.4, w * 0.4, -d, -d + 0.04, H * 0.35, H * 0.7);
  p.cb('negro', [-w * 0.4 - 0.03, -d + 0.02, H * 0.52], [-w * 0.4, -d + 0.02, H * 0.52], 0.012, 6);
  p.c('pantalla', -w + 0.015, w - 0.015, d - 0.008, d, H * 0.62, H * 0.9);
  p.c('trazoVerde', -w + 0.025, 0, d, d + 0.001, H * 0.8, H * 0.84);
  p.c('grisClaro', -w + 0.015, w - 0.015, d - 0.008, d, H * 0.38, H * 0.58);
  for (let i = 0; i < 3; i++) p.c(i === 0 ? 'trazoVerde' : i === 1 ? 'rojo' : 'gris', -w + 0.02 + i * 0.04, -w + 0.05 + i * 0.04, d, d + 0.003, H * 0.42, H * 0.47);
  p.c('tapizClaro', -w + 0.015, w - 0.015, d - 0.008, d, H * 0.06, H * 0.34);
  p.cb('grisOsc', [-w + 0.02, 0, H - 0.01], [w - 0.02, 0, H - 0.01], 0.008, 6);
}, L1.frente('crema', 'pantalla', 0.6, 0.9));
def('ventilador_transporte', (p) => {
  const { w, d, H } = p;
  p.c('tapiz', -w, w, -d, d - 0.01, 0, H - 0.04);
  pantalla(p, -w + 0.02, w * 0.4, H * 0.25, H - 0.07, d - 0.01, { fondo: 0.004, trazos: true, borde: 0.008 });
  p.cb('grisClaro', [w * 0.7, d - 0.01, H * 0.6], [w * 0.7, d, H * 0.6], 0.03, 10);
  p.c('grisClaro', w * 0.5, w - 0.02, d - 0.01, d, H * 0.12, H * 0.22);
  p.cb('grisOsc', [-w + 0.03, 0, H - 0.02], [w - 0.03, 0, H - 0.02], 0.012, 6);
  for (const s of [-1, 1]) p.c('grisOsc', s * (w - 0.04) - 0.01, s * (w - 0.04) + 0.01, -0.01, 0.01, H - 0.04, H - 0.02);
  for (const z of [H * 0.3, H * 0.5]) p.cb('blanco', [w, -0.02, z], [w, -0.02, z], 0.012, 6);
  p.cb('acrilico', [w - 0.02, 0.03, H * 0.4], [w, 0.03, H * 0.4], 0.018, 8, 0.018, true);
}, L1.frente('tapiz', 'pantalla', 0.25, 0.85));
def('aspirador_portatil', (p) => {
  const { w, d, H } = p, hb = H * 0.48;
  p.c('crema', -w, w, -d, d, 0, hb);
  p.c('grisOsc', -w, w, -d, d, 0, 0.012);
  p.cv('acrilico', w * 0.35, 0, hb, H - 0.04, Math.min(0.075, d - 0.02), 10, Math.min(0.075, d - 0.02), true);
  p.cv('blanco', w * 0.35, 0, H - 0.04, H, Math.min(0.08, d - 0.015), 10);
  p.cv('amarillo', w * 0.35, 0, hb, hb + (H - hb) * 0.35, Math.min(0.07, d - 0.025), 10);
  p.cb('blanco', [-w * 0.5, d, hb * 0.6], [-w * 0.5, d, hb * 0.6], 0.04, 10);
  p.cb('grisOsc', [-w * 0.5, d - 0.005, hb * 0.6], [-w * 0.5, d + 0.002, hb * 0.6], 0.042, 10);
  p.c('grisOsc', -w * 0.75, -w * 0.15, -0.02, 0.02, hb, hb + 0.06);
  p.c('grisOsc', -w * 0.75, -w * 0.15, -0.02, 0.02, hb + 0.06, hb + 0.08);
  p.cb('acrilico', [w * 0.35, 0, H], [-w * 0.1, -d + 0.02, H - 0.02], 0.008, 4, 0.008, true);
}, (p) => { p.c('crema', -p.w, p.w, -p.d, p.d, 0, p.H * 0.48); p.c('acrilico', 0, p.w, -p.d + 0.03, p.d - 0.03, p.H * 0.48, p.H, true); p.c('grisOsc', -p.w * 0.7, -p.w * 0.2, -0.02, 0.02, p.H * 0.48, p.H * 0.65); });
def('toma_gases_pared', (p) => {
  const { w, d, H } = p;
  p.c('blanco', -w, w, -d, -d + 0.012, H * 0.6, H);
  p.cb('oxigeno', [0, -d + 0.012, H * 0.8], [0, -d + 0.04, H * 0.8], 0.018, 8);
  p.cv('acrilico', 0, -d + 0.05, H * 0.55, H * 0.95, 0.016, 8, 0.016, true);
  p.cv('oxigeno', 0, -d + 0.05, H * 0.95, H, 0.018, 8);
  p.cv('trazoVerde', 0, -d + 0.05, H * 0.7, H * 0.72, 0.008, 6);
  p.cv('acero', 0, -d + 0.05, H * 0.45, H * 0.55, 0.02, 8);
  p.cv('acrilico', 0, -d + 0.05, 0, H * 0.4, Math.min(0.045, d), 10, Math.min(0.045, d), true);
  p.cv('agua', 0, -d + 0.05, 0.002, H * 0.22, Math.min(0.04, d - 0.005), 10);
  p.cv('blanco', 0, -d + 0.05, H * 0.4, H * 0.45, Math.min(0.046, d), 10);
}, (p) => { p.c('blanco', -p.w, p.w, -p.d, -p.d + 0.012, p.H * 0.6, p.H); p.c('oxigeno', -0.02, 0.02, -p.d + 0.012, p.d - 0.02, p.H * 0.55, p.H); p.c('acrilico', -p.w + 0.01, p.w - 0.01, -p.d + 0.012, p.d, 0, p.H * 0.45, true); });
def('equipo_mesa', (p) => {
  const { w, d, H } = p, s = Math.min(1, H / 0.15);
  p.c('crema', -w, w, -d, d - 0.008, 0, H * 0.9);
  p.c('grisClaro', -w - 0.004, w + 0.004, -d - 0.004, d - 0.004, H * 0.88, H);
  p.c('grisOsc', -w + 0.01, w - 0.01, d - 0.008, d, H * 0.08, H * 0.82);
  p.c('pantalla', -w + 0.025, w * 0.15, d, d + 0.002, H * 0.35, H * 0.75);
  p.c('trazoCian', -w + 0.04, -w * 0.15, d + 0.002, d + 0.003, H * 0.55, H * 0.6);
  ['trazoVerde', 'amarillo', 'rojo'].forEach((c, i) => p.c(c, w * 0.3 + i * w * 0.18, w * 0.42 + i * w * 0.18, d, d + 0.006 * s, H * 0.55, H * 0.68));
  p.cb('grisClaro', [w * 0.55, d, H * 0.28], [w * 0.55, d + 0.012, H * 0.28], Math.min(0.025, H * 0.17), 10);
}, L1.frente('crema', 'grisOsc', 0.08, 0.85));
def('estuche', (p) => {
  const { w, d, H } = p;
  p.c('tapiz', -w, w, -d, d, 0, H * 0.55);
  p.c('tapizOsc', -w, w, -d, d, H * 0.55, H * 0.6);
  p.c('tapiz', -w, w, -d, d, H * 0.6, H);
  for (const s of [-1, 1]) p.c('acero', s * w * 0.6 - 0.02, s * w * 0.6 + 0.02, d, d + 0.008, H * 0.4, H * 0.75);
  p.c('negro', -0.06, 0.06, d, d + 0.015, H * 0.8, H * 0.95);
}, L1.caja('tapiz'));
def('tabla_espinal', (p) => {
  if (p.H > p.D) {
    // guardada de pie contra el muro: la cara con los agarraderos mira al frente
    const { w, d, H } = p, e = Math.min(0.06, p.D * 0.6);
    p.c('naranja', -w, w, -d, -d + e, 0, H);
    for (const s of [-1, 1]) for (let k = 0; k < 4; k++) { const z = 0.3 + (k * (H - 0.6)) / 3; p.c('negro', s * (w - 0.05) - 0.018, s * (w - 0.05) + 0.018, -d + e - 0.002, -d + e + 0.001, z - 0.06, z + 0.06); }
    for (const z of [H * 0.3, H * 0.55, H * 0.8]) p.c('negro', -w - 0.005, w + 0.005, -d + e, -d + e + 0.006, z - 0.025, z + 0.025);
    for (const s of [-1, 1]) p.c('rojo', s * 0.1 - 0.05, s * 0.1 + 0.05, -d + e, Math.min(d, -d + e + 0.05), H - 0.2, H - 0.04);
    return;
  }
  const { w, d, H } = p;
  p.c('naranja', -w, w, -d, d, 0, H);
  for (const s of [-1, 1]) for (let k = 0; k < 4; k++) { const y = -d + 0.3 + k * (p.D - 0.6) / 3; p.c('negro', s * (w - 0.05) - 0.018, s * (w - 0.05) + 0.018, y - 0.06, y + 0.06, H - 0.002, H + 0.001); }
  for (const y of [-d * 0.35, d * 0.15, d * 0.65]) p.c('negro', -w - 0.005, w + 0.005, y - 0.025, y + 0.025, H, H + 0.006);
  for (const s of [-1, 1]) p.c('rojo', s * 0.1 - 0.05, s * 0.1 + 0.05, -d + 0.04, -d + 0.2, H, H + 0.018);
}, (p) => { if (p.H > p.D) p.c('naranja', -p.w, p.w, -p.d, -p.d + Math.min(0.06, p.D * 0.6), 0, p.H); else p.c('naranja', -p.w, p.w, -p.d, p.d, 0, p.H); });
def('equipo_pared', (p) => {
  const { w, d, H } = p;
  p.c('blanco', -w, w, -d, -d + 0.015, 0, H);
  p.c('grisClaro', -w + 0.01, w - 0.01, -d + 0.015, -d + 0.035, H * 0.15, H * 0.45);
  for (const s of [-1, 1]) {
    const x = s * w * 0.62;
    const yh = d - Math.min(0.022, w * 0.13);
    p.cv('negro', x, yh, H * 0.22, H * 0.68, Math.min(0.016, w * 0.1), 8);
    p.cv('grisOsc', x, yh, H * 0.68, H * 0.82, Math.min(0.022, w * 0.13), 8, Math.min(0.012, w * 0.07));
    p.cb('negro', [x, yh, H * 0.22], [x, -d + 0.03, H * 0.1], 0.005, 4);
    p.c('grisClaro', x - 0.012, x + 0.012, -d + 0.015, yh, H * 0.5, H * 0.56);
  }
  p.cb('blanco', [0, -d + 0.015, H * 0.68], [0, d - 0.004, H * 0.68], Math.min(0.06, w * 0.3), 12);
  p.cb('negro', [0, d - 0.004, H * 0.68], [0, d - 0.002, H * 0.68], Math.min(0.055, w * 0.27), 12);
  p.c('rojo', -0.002, 0.002, d - 0.002, d, H * 0.62, H * 0.72);
}, (p) => { p.c('blanco', -p.w, p.w, -p.d, -p.d + 0.015, 0, p.H); p.c('negro', -p.w * 0.7, p.w * 0.7, -p.d + 0.015, p.d, p.H * 0.2, p.H * 0.8); });
function lamparaRodable(p, { cabeza = 'blanco', luz = 'luz', ancho = 0.12 } = {}) {
  const { w, d, H } = p;
  estrella(p, 0, 0, Math.min(w, d) - 0.01, 'grisClaro');
  p.cv('acero', 0, 0, 0.08, H - 0.45, 0.016, 8);
  p.cb('grisOsc', [0, 0, H - 0.45], [0, 0.12, H - 0.2], 0.012, 6);
  const f = p.sub([0, 0.12, H - 0.14], R2(-35));
  f.cv(cabeza, 0, 0, -0.04, 0.06, ancho, 12, ancho * 0.7);
  f.cv(luz, 0, 0, -0.045, -0.04, ancho * 0.9, 12);
}
def('lampara_rodable', (p) => lamparaRodable(p), L1.poste('grisClaro', 'blanco', 0.2));
def('lampara_cuello_cisne', (p) => {
  const { w, d, H } = p;
  estrella(p, 0, 0, Math.min(w, d) - 0.01, 'grisClaro');
  p.cv('acero', 0, 0, 0.08, H * 0.62, 0.014, 8);
  const pts = [[0, 0, H * 0.62], [0, 0.03, H * 0.8], [0, 0.1, H * 0.92], [0, 0.18, H * 0.96]];
  for (let i = 0; i < pts.length - 1; i++) p.cb('negro', pts[i], pts[i + 1], 0.01, 6);
  const f = p.sub([0, 0.2, H * 0.94], R2(-60));
  f.cv('blanco', 0, 0, -0.03, 0.05, 0.05, 10, 0.025);
  f.cv('luz', 0, 0, -0.034, -0.03, 0.045, 10);
}, L1.poste('grisClaro', 'blanco', 0.15));
def('lampara_cielitica', (p) => {
  const { w, d, H } = p, R = Math.min(w, d) - 0.01;
  p.cv('blanco', 0, 0, H - 0.03, H, 0.13, 12);
  p.cv('blanco', 0, 0, H * 0.62, H - 0.03, 0.03, 8);
  p.cb('blanco', [0, 0, H * 0.62], [R * 0.7, 0, H * 0.6], 0.028, 6);
  p.cb('grisClaro', [R * 0.7, 0, H * 0.6], [0.04, 0.0, 0.2], 0.024, 6);
  p.cv('blanco', 0, 0, 0.07, 0.2, R, 16, R * 0.35);
  p.cv('luz', 0, 0, 0.065, 0.07, R * 0.9, 16);
  p.cv('grisOsc', 0, 0, 0.0, 0.065, 0.025, 8);
}, (p) => { p.c('blanco', -0.03, 0.03, -0.03, 0.03, 0.2, p.H); p.c('blanco', -p.w, p.w, -p.d, p.d, 0.07, 0.2); p.c('luz', -p.w * 0.85, p.w * 0.85, -p.d * 0.85, p.d * 0.85, 0.065, 0.07); });
def('bascula_pesabebes', (p) => {
  const { w, d, H } = p;
  p.c('blanco', -w + 0.03, w - 0.03, -d + 0.03, d - 0.03, 0, H * 0.35);
  p.c('pantalla', w * 0.3, w - 0.06, d - 0.03, d - 0.026, H * 0.08, H * 0.3);
  p.c('trazoVerde', w * 0.35, w - 0.1, d - 0.026, d - 0.024, H * 0.15, H * 0.23);
  const pts = [];
  const n = 8;
  for (let i = 0; i <= n; i++) { const t = -1 + (2 * i) / n; pts.push([t * d, H * 0.35 + (H * 0.65) * t * t]); }
  for (let i = n; i >= 0; i--) { const t = -1 + (2 * i) / n; pts.push([t * (d - 0.012), H * 0.35 + 0.012 + (H * 0.65 - 0.012) * t * t]); }
  p.pf('celeste', pts, 'yz', -w, w);
}, (p) => { p.c('blanco', -p.w + 0.03, p.w - 0.03, -p.d + 0.03, p.d - 0.03, 0, p.H * 0.35); p.c('celeste', -p.w, p.w, -p.d, p.d, p.H * 0.35, p.H * 0.5); p.c('celeste', -p.w, p.w, -p.d, -p.d + 0.03, p.H * 0.5, p.H); p.c('celeste', -p.w, p.w, p.d - 0.03, p.d, p.H * 0.5, p.H); });
def('bascula_piso', (p) => {
  const { w, d, H } = p;
  p.c('grisClaro', -w, w, -d, d, 0, H * 0.7);
  p.c('negro', -w + 0.02, w - 0.02, -d + 0.02, d - 0.07, H * 0.7, H * 0.85);
  p.c('pantalla', -0.06, 0.06, d - 0.06, d - 0.02, H * 0.7, H);
  p.c('trazoVerde', -0.04, 0.04, d - 0.05, d - 0.03, H, H + 0.001);
}, L1.caja('grisClaro'));
def('infantometro', (p) => {
  const { w, d, H } = p;
  p.c('blanco', -w, w, -d, d, 0, 0.02);
  p.c('amarillo', w - 0.05, w - 0.01, -d + 0.03, d - 0.03, 0.02, 0.022);
  for (let k = 0; k < 10; k++) { const y = -d + 0.05 + (k * (p.D - 0.1)) / 9; p.c('negro', w - 0.05, w - 0.03, y - 0.002, y + 0.002, 0.022, 0.023); }
  p.c('tapizClaro', -w, w, -d, -d + 0.02, 0, H);
  p.c('tapizClaro', -w + 0.01, w - 0.01, d * 0.4, d * 0.4 + 0.02, 0.02, H * 0.85);
  p.c('tapiz', -0.03, 0.03, d * 0.4 + 0.02, d * 0.4 + 0.035, H * 0.6, H * 0.8);
}, (p) => { p.c('blanco', -p.w, p.w, -p.d, p.d, 0, 0.02); p.c('tapizClaro', -p.w, p.w, -p.d, -p.d + 0.02, 0, p.H); p.c('tapizClaro', -p.w, p.w, p.d * 0.4, p.d * 0.4 + 0.02, 0, p.H * 0.85); });

// ---- neonatal
def('servocuna', (p) => {
  const { w, d, H } = p, zb = H * 0.44;
  ruedas(p, { r: 0.05, dx: w - 0.12, dy: d - 0.1 });
  p.c('grisOsc', -w + 0.08, w - 0.08, -d + 0.06, d - 0.06, 0.11, 0.16);
  p.c('blanco', -w + 0.12, w - 0.12, -d + 0.1, d - 0.12, 0.16, zb - 0.04);
  cajones(p, -w + 0.15, w - 0.15, d - 0.12, zb - 0.3, zb - 0.06, 2, 'blanco');
  p.c('blanco', -w + 0.02, w - 0.02, -d + 0.08, d - 0.02, zb - 0.04, zb + 0.03);
  p.c('celeste', -w + 0.06, w - 0.06, -d + 0.12, d - 0.06, zb + 0.03, zb + 0.08);
  for (const s of [-1, 1]) {
    p.c('acrilico', s * (w - 0.03) - 0.005, s * (w - 0.03) + 0.005, -d + 0.1, d - 0.03, zb + 0.03, zb + 0.22, true);
    p.c('acrilico', -w + 0.03, w - 0.03, s > 0 ? d - 0.035 : -d + 0.095, s > 0 ? d - 0.025 : -d + 0.105, zb + 0.03, zb + 0.22, true);
  }
  p.c('blanco', -0.07, 0.07, -d, -d + 0.09, zb - 0.04, H - 0.1);
  pantalla(p, -0.14, 0.14, zb + 0.32, zb + 0.55, -d + 0.09, { fondo: 0.03, trazos: true, marco: 'blanco' });
  p.c('blanco', -0.22, 0.22, -d, d * 0.35, H - 0.16, H);
  p.c('calor', -0.18, 0.18, -d + 0.1, d * 0.3, H - 0.165, H - 0.16);
}, (p) => { p.c('blanco', -p.w + 0.1, p.w - 0.1, -p.d + 0.1, p.d - 0.1, 0, p.H * 0.44); p.c('celeste', -p.w, p.w, -p.d + 0.08, p.d, p.H * 0.44, p.H * 0.5); p.c('blanco', -0.07, 0.07, -p.d, -p.d + 0.09, p.H * 0.44, p.H); p.c('blanco', -0.22, 0.22, -p.d, p.d * 0.35, p.H - 0.16, p.H); });
def('incubadora_neonatal', (p) => {
  const { w, d, H } = p, zb = H * 0.6, zc = zb + 0.12, xm = w - 0.24;
  ruedas(p, { r: 0.05, dx: w - 0.12, dy: d - 0.08 });
  p.c('grisOsc', -w + 0.08, w - 0.08, -d + 0.06, d - 0.06, 0.11, 0.16);
  for (const s of [-1, 1]) p.c('blanco', s * (w - 0.18) - 0.04, s * (w - 0.18) + 0.04, -d + 0.12, d - 0.12, 0.16, zb);
  p.c('blanco', -w + 0.12, w - 0.12, -d + 0.1, d - 0.1, zb - 0.22, zb - 0.02);
  cajones(p, -w + 0.2, w - 0.2, d - 0.1, zb - 0.2, zb - 0.04, 1, 'blanco');
  p.c('blanco', -w + 0.02, w - 0.02, -d + 0.02, d - 0.02, zb, zc);
  p.c('grisClaro', xm, w - 0.02, -d + 0.03, d - 0.03, zc, zc + 0.25);
  pantalla(p, xm + 0.03, w - 0.04, zc + 0.04, zc + 0.2, d - 0.03, { fondo: 0.004, trazos: true, borde: 0.01 });
  p.c('celeste', -w + 0.06, xm - 0.03, -d + 0.06, d - 0.06, zc, zc + 0.04);
  const x0 = -w + 0.03, x1 = xm - 0.01, top = H - zc - 0.02;
  const pts = [[x0, 0], [x1, 0], [x1, top * 0.7]];
  for (let i = 1; i < 6; i++) { const a = (Math.PI * i) / 6; pts.push([(x0 + x1) / 2 + Math.cos(a) * (x1 - x0) / 2, top * 0.7 + Math.sin(a) * top * 0.3]); }
  pts.push([x0, top * 0.7]);
  p.sub([0, 0, zc]).pf('acrilico', pts, 'xz', -d + 0.04, d - 0.04, true);
  for (const x of [-0.22, 0.08]) {
    p.cb('grisClaro', [x, d - 0.04, zc + 0.15], [x, d - 0.032, zc + 0.15], 0.065, 12);
    p.cb('acrilico', [x, d - 0.032, zc + 0.15], [x, d - 0.03, zc + 0.15], 0.055, 12, 0.055, true);
  }
}, (p) => { p.c('blanco', -p.w + 0.1, p.w - 0.1, -p.d + 0.08, p.d - 0.08, 0, p.H * 0.6); p.c('blanco', -p.w, p.w, -p.d, p.d, p.H * 0.6, p.H * 0.6 + 0.12); p.c('acrilico', -p.w + 0.03, p.w - 0.24, -p.d + 0.04, p.d - 0.04, p.H * 0.6 + 0.12, p.H, true); p.c('grisClaro', p.w - 0.24, p.w, -p.d, p.d, p.H * 0.6 + 0.12, p.H * 0.6 + 0.37); });
def('incubadora_transporte', (p) => {
  const { w, d, H } = p, zd = H * 0.58, zm = zd + 0.16, xm = w - 0.32;
  ruedas(p, { r: 0.06, dx: w - 0.15, dy: d - 0.08 });
  for (const s of [-1, 1]) {
    p.c('acero', -w + 0.1, w - 0.1, s * (d - 0.08) - 0.02, s * (d - 0.08) + 0.02, 0.14, 0.18);
    p.cb('acero', [s * (w - 0.25), -d + 0.12, 0.18], [s * (w - 0.25), -d + 0.12, zd], 0.02, 6);
    p.cb('acero', [s * (w - 0.25), d - 0.12, 0.18], [s * (w - 0.25), d - 0.12, zd], 0.02, 6);
    p.cb('acero', [s * (w - 0.02), -d + 0.1, zd + 0.1], [s * (w - 0.02), d - 0.1, zd + 0.1], 0.016, 6);
    p.c('acero', s * (w - 0.02) - 0.012 - (s > 0 ? 0.06 : -0.0), s * (w - 0.02) + 0.012 + (s < 0 ? 0.06 : 0), -0.012, 0.012, zd, zd + 0.1);
  }
  for (const y of [-0.12, 0.12]) p.cb('oxigeno', [-w + 0.25, y, 0.32], [w - 0.35, y, 0.32], 0.07, 8);
  p.c('acero', -w + 0.08, w - 0.08, -d + 0.04, d - 0.04, zd - 0.03, zd);
  p.c('grisClaro', -w + 0.08, w - 0.08, -d + 0.04, d - 0.04, zd, zm);
  pantalla(p, xm + 0.03, w - 0.1, zd + 0.03, zm - 0.02, d - 0.04, { fondo: 0.004, trazos: true, borde: 0.008 });
  const pts = [];
  const r = d - 0.06, zt = H - zm;
  for (let i = 0; i <= 8; i++) { const a = (Math.PI * i) / 8; pts.push([Math.cos(a) * r, Math.min(zt, Math.sin(a) * zt)]); }
  p.sub([0, 0, zm]).pf('acrilico', pts, 'yz', -w + 0.1, xm, true);
  p.c('celeste', -w + 0.12, xm - 0.02, -r + 0.03, r - 0.03, zm, zm + 0.04);
}, (p) => { p.c('acero', -p.w + 0.1, p.w - 0.1, -p.d + 0.06, p.d - 0.06, 0, p.H * 0.58); p.c('grisClaro', -p.w + 0.08, p.w - 0.08, -p.d + 0.04, p.d - 0.04, p.H * 0.58, p.H * 0.58 + 0.16); p.c('acrilico', -p.w + 0.1, p.w - 0.32, -p.d + 0.06, p.d - 0.06, p.H * 0.58 + 0.16, p.H, true); });
def('fototerapia', (p) => {
  const { w, d, H } = p;
  estrella(p, 0, 0, Math.min(w, d) - 0.01, 'grisClaro');
  p.cv('acero', 0, 0, 0.08, H - 0.2, 0.02, 8);
  p.c('grisOsc', -0.04, 0.04, -0.04, 0.04, H - 0.24, H - 0.18);
  const f = p.sub([0, 0.05, H - 0.16], R2(-8));
  f.c('blanco', -0.25, 0.25, -0.18, 0.18, 0, 0.1);
  f.c('luzAzul', -0.22, 0.22, -0.15, 0.15, -0.006, 0);
  f.c('grisOsc', -0.08, 0.08, -0.02, 0.02, 0.1, 0.14);
  pantalla(f, 0.1, 0.22, 0.02, 0.08, 0.18, { fondo: 0.002, borde: 0.006 });
}, L1.poste('grisClaro', 'blanco', 0.2));
def('monitor_fetal', (p) => {
  const { w, d, H } = p;
  p.c('crema', -w, w, -d, d - 0.04, 0, H * 0.45);
  p.c('blanco', -w + 0.04, w - 0.04, d - 0.04, d, H * 0.25, H * 0.3);
  p.c('rosado', -w + 0.06, w - 0.06, d - 0.03, d, H * 0.3, H * 0.31);
  const f = p.sub([0, -0.01, H * 0.45], R2(60));
  f.c('crema', -w + 0.02, w - 0.02, -0.012, 0, 0, 0.14);
  pantalla(f, -w + 0.035, w - 0.035, 0.012, 0.13, 0.0, { fondo: 0.004, trazos: true, borde: 0.008 });
  p.cv('rosado', -w * 0.5, d - 0.08, H * 0.45, H * 0.65, 0.035, 10);
  p.cv('celeste', w * 0.5, d - 0.08, H * 0.45, H * 0.65, 0.035, 10);
}, L1.frente('crema', 'pantalla', 0.4, 1));

// ---- odontología
const PIEZAS_ODONTO = [[0.7, 1.9, 0.9, 0, 0], [0.3, 0.3, 1.9, -0.6, -0.8], [0.5, 0.4, 0.85, 0.65, 0.2], [0.3, 0.3, 0.9, -0.55, 0.2], [0.45, 0.45, 0.55, 0.65, 0.8]];
def('unidad_odontologica', (p) => {
  const sx = p.W / 1.8, sy = p.D / 2.2, sz = p.H / 1.9;
  const pz = PIEZAS_ODONTO.map(([a, b, c, x, y]) => ({ a: a * sx, b: b * sy, c: c * sz, x: x * sx, y: y * sy }));
  // sillón: base, columna, asiento, espaldar reclinado hacia −y, cabecera y piernera inclinada hacia +y
  const s = pz[0], sw = s.a / 2, f = p.sub([s.x, s.y, 0]);
  f.c('blanco', -0.25 * sx, 0.25 * sx, -0.45 * sy, 0.35 * sy, 0, 0.05);
  f.c('blanco', -0.15 * sx, 0.15 * sx, -0.15 * sy, 0.15 * sy, 0.05, 0.38 * sz);
  f.c('grisClaro', -sw + 0.06, sw - 0.06, -0.2 * sy, 0.25 * sy, 0.38 * sz, 0.42 * sz);
  f.c('tapiz', -sw + 0.04, sw - 0.04, -0.2 * sy, 0.25 * sy, 0.42 * sz, 0.52 * sz);
  const e = f.sub([0, -0.2 * sy, 0.47 * sz], R2(-62));
  e.c('tapiz', -sw + 0.06, sw - 0.06, -0.62 * sy, 0, 0, 0.1);
  e.c('tapiz', -0.13, 0.13, -0.85 * sy, -0.62 * sy, 0.01, 0.09);
  const pi = f.sub([0, 0.25 * sy, 0.47 * sz], R2(-18));
  pi.c('tapiz', -sw + 0.1, sw - 0.1, 0, 0.65 * sy, 0, 0.09);
  f.c('tapizOsc', sw - 0.06, sw, -0.15 * sy, 0.2 * sy, 0.55 * sz, 0.6 * sz);
  f.c('grisClaro', sw - 0.05, sw - 0.02, 0.0, 0.05, 0.42 * sz, 0.55 * sz);
  // lámpara en poste con brazo hacia la cabecera
  const l = pz[1];
  p.cv('blanco', l.x, l.y, 0, 0.04, l.a / 2, 12);
  p.cv('blanco', l.x, l.y, 0.04, l.c - 0.12, 0.035, 8);
  p.cb('blanco', [l.x, l.y, l.c - 0.12], [l.x + 0.35 * sx, l.y + 0.12 * sy, l.c - 0.05], 0.025, 6);
  p.cb('grisClaro', [l.x + 0.35 * sx, l.y + 0.12 * sy, l.c - 0.05], [s.x - 0.05, s.y - 0.5 * sy, l.c - 0.25], 0.02, 6);
  const lc = p.sub([s.x - 0.05, s.y - 0.5 * sy, l.c - 0.3], R2(-20));
  lc.c('blanco', -0.16, 0.16, -0.05, 0.05, 0, 0.09);
  lc.c('luz', -0.13, 0.13, -0.04, 0.04, -0.004, 0);
  // módulo de instrumentos con piezas de mano
  const m = pz[2], mw = m.a / 2, md = m.b / 2;
  p.c('blanco', m.x - 0.12, m.x + 0.12, m.y - 0.1, m.y + 0.1, 0, 0.05);
  p.cv('blanco', m.x, m.y, 0.05, m.c - 0.12, 0.035, 8);
  p.c('blanco', m.x - mw, m.x + mw, m.y - md, m.y + md, m.c - 0.12, m.c - 0.04);
  p.c('grisClaro', m.x - mw + 0.02, m.x + mw - 0.02, m.y - md + 0.02, m.y + md - 0.02, m.c - 0.04, m.c - 0.03);
  for (let k = 0; k < 4; k++) {
    const x = m.x - mw + 0.08 + k * (m.a - 0.16) / 3;
    p.cb(k === 3 ? 'amarillo' : 'grisOsc', [x, m.y + md - 0.02, m.c - 0.03], [x, m.y + md, m.c + 0.12 * sz], 0.012, 6);
    p.cb('negro', [x, m.y + md - 0.01, m.c - 0.12], [x, m.y + md - 0.02, m.c - 0.3], 0.006, 4);
  }
  pantalla(p, m.x - 0.08, m.x + 0.08, m.c - 0.115, m.c - 0.05, m.y + md, { fondo: 0.004, borde: 0.006 });
  // escupidera
  const c = pz[3];
  p.cv('blanco', c.x, c.y, 0, c.c * 0.8, 0.05, 8);
  p.cv('celeste', c.x, c.y, c.c * 0.8, c.c, c.a / 2 * 0.65, 12, c.a / 2);
  p.cv('agua', c.x, c.y, c.c - 0.002, c.c + 0.001, c.a / 2 * 0.8, 12);
  p.cb('acero', [c.x + 0.05, c.y - 0.05, c.c], [c.x + 0.02, c.y - 0.02, c.c + 0.08], 0.008, 4);
  // taburete del odontólogo
  const t = pz[4];
  estrella(p.sub([t.x, t.y, 0]), 0, 0, t.a / 2 - 0.01);
  p.cv('acero', t.x, t.y, 0.08, t.c - 0.06, 0.02, 8);
  p.cv('tapiz', t.x, t.y, t.c - 0.06, t.c, 0.19 * Math.min(sx, sy), 12);
}, (p) => {
  const sx = p.W / 1.8, sy = p.D / 2.2;
  p.c('tapiz', -0.35 * sx, 0.35 * sx, -0.95 * sy, 0.95 * sy, 0, 0.6);
  p.c('blanco', -0.72 * sx, -0.48 * sx, -0.92 * sy, -0.68 * sy, 0, p.H);
  p.c('blanco', 0.4 * sx, 0.9 * sx, 0.0, 0.4 * sy, 0, 0.85 * p.H / 1.9);
  p.c('tapiz', 0.45 * sx, 0.85 * sx, 0.6 * sy, 1.0 * sy, 0, 0.55 * p.H / 1.9);
});
def('compresor', (p) => {
  const { w, d, H } = p, R = Math.min(d - 0.02, H * 0.3);
  for (const sx of [-1, 1]) for (const sy of [-1, 1]) p.c('negro', sx * (w - 0.08) - 0.03, sx * (w - 0.08) + 0.03, sy * (R * 0.6) - 0.03, sy * (R * 0.6) + 0.03, 0, 0.04);
  p.cb('grisClaro', [-w + 0.02, 0, R + 0.04], [w - 0.02, 0, R + 0.04], R, 14);
  for (const x of [-w * 0.35, w * 0.35]) {
    p.cv('gris', x, 0, 2 * R + 0.02, H - 0.08, 0.07, 10);
    p.cv('acero', x, 0, H - 0.08, H - 0.04, 0.085, 10);
    p.c('grisOsc', x - 0.06, x + 0.06, -0.06, 0.06, H - 0.04, H);
  }
  p.cb('blanco', [0, R * 0.7, 2 * R + 0.06], [0, R * 0.7 + 0.03, 2 * R + 0.06], 0.035, 10);
  p.c('negro', w * 0.55, w - 0.02, -0.05, 0.05, 2 * R + 0.02, 2 * R + 0.1);
}, (p) => { const R = Math.min(p.d - 0.02, p.H * 0.3); p.c('grisClaro', -p.w, p.w, -R, R, 0, 2 * R + 0.06); p.c('gris', -p.w * 0.6, p.w * 0.6, -0.08, 0.08, 2 * R + 0.06, p.H); });
def('rx_periapical', (p) => {
  const { w, d, H } = p;
  p.c('blanco', -w, w, -d, -d + 0.05, H * 0.62, H);
  p.c('pantalla', -w * 0.6, w * 0.1, -d + 0.05, -d + 0.052, H * 0.8, H * 0.92);
  p.cb('blanco', [w * 0.3, -d + 0.05, H * 0.75], [w * 0.75, -d + 0.12, H * 0.82], 0.022, 6);
  p.cb('blanco', [w * 0.75, -d + 0.12, H * 0.82], [w * 0.2, d * 0.2, H * 0.72], 0.02, 6);
  p.cb('grisClaro', [w * 0.2, d * 0.2, H * 0.72], [0, d * 0.1, H * 0.48], 0.016, 6);
  p.c('crema', -0.09, 0.09, -0.07, 0.07, H * 0.06, H * 0.48);
  p.cb('crema', [0, 0.07, H * 0.2], [0, d, H * 0.15], 0.04, 10, 0.035);
  p.c('grisOsc', -0.09, 0.09, -0.071, 0.071, H * 0.3, H * 0.32);
}, (p) => { p.c('blanco', -p.w * 0.5, p.w * 0.5, -p.d, -p.d + 0.05, p.H * 0.62, p.H); p.c('crema', -0.09, 0.09, -0.07, p.d, p.H * 0.18, p.H * 0.48); p.c('blanco', -0.02, 0.02, -p.d + 0.05, 0, p.H * 0.48, p.H * 0.75); });

// ---- imágenes
const PIEZAS_RX = [[2.2, 0.8, 0.75, -0.4, 0.3], [0.5, 0.4, 2.2, -0.4, -0.6], [0.6, 0.45, 1.9, 1.6, -1.275]];
def('rayos_x_convencional', (p) => {
  const sx = p.W / 4, sy = p.D / 3, sz = p.H / 2.2;
  const [m, c, b] = PIEZAS_RX.map(([a, bb, cc, x, y]) => ({ a: a * sx, b: bb * sy, c: cc * sz, x: x * sx, y: y * sy }));
  // mesa con bucky
  p.c('grisOsc', m.x - 0.35, m.x + 0.35, m.y - 0.28, m.y + 0.28, 0, 0.04);
  p.c('crema', m.x - 0.3, m.x + 0.3, m.y - 0.24, m.y + 0.24, 0.04, m.c - 0.15);
  p.c('grisClaro', m.x - m.a / 2 + 0.05, m.x + m.a / 2 - 0.05, m.y - m.b / 2 + 0.06, m.y + m.b / 2 - 0.06, m.c - 0.15, m.c - 0.1);
  p.c('grisOsc', m.x - 0.25, m.x + 0.25, m.y - m.b / 2 + 0.1, m.y + m.b / 2 - 0.02, m.c - 0.12, m.c - 0.08);
  p.c('crema', m.x - m.a / 2, m.x + m.a / 2, m.y - m.b / 2, m.y + m.b / 2, m.c - 0.08, m.c - 0.03);
  p.c('tapizClaro', m.x - m.a / 2 + 0.05, m.x + m.a / 2 - 0.05, m.y - m.b / 2 + 0.05, m.y + m.b / 2 - 0.05, m.c - 0.03, m.c);
  p.c('negro', m.x - 0.15, m.x + 0.15, m.y + m.b / 2 - 0.02, m.y + m.b / 2, 0.0, 0.03);
  // columna portatubo sobre riel de piso
  p.c('acero', -p.W / 2 + 0.2, m.x + m.a / 2, c.y - 0.06, c.y + 0.06, 0, 0.03);
  p.c('acero', -p.W / 2 + 0.2, m.x + m.a / 2, c.y - 0.06, c.y + 0.06, p.H - 0.06, p.H - 0.03);
  p.c('crema', c.x - 0.14, c.x + 0.14, c.y - 0.14, c.y + 0.14, 0.03, c.c - 0.03);
  p.c('grisOsc', c.x - 0.18, c.x + 0.18, c.y - 0.12, c.y + 0.12, 0.03, 0.18);
  p.c('gris', c.x - 0.12, c.x + 0.12, c.y + 0.12, c.y + 0.22, c.c * 0.6, c.c * 0.6 + 0.24);
  p.c('crema', c.x - 0.06, c.x + 0.06, c.y + 0.14, m.y + 0.02, c.c * 0.6 + 0.08, c.c * 0.6 + 0.18);
  p.cb('blanco', [c.x - 0.22, m.y - 0.05, c.c * 0.6 + 0.22], [c.x + 0.22, m.y - 0.05, c.c * 0.6 + 0.22], 0.11, 12);
  p.c('grisOsc', c.x - 0.12, c.x + 0.12, m.y - 0.16, m.y + 0.06, c.c * 0.6 - 0.05, c.c * 0.6 + 0.1);
  p.c('luz', c.x - 0.08, c.x + 0.08, m.y - 0.13, m.y + 0.03, c.c * 0.6 - 0.055, c.c * 0.6 - 0.05);
  pantalla(p, c.x - 0.09, c.x + 0.09, c.c * 0.6 - 0.03, c.c * 0.6 + 0.08, m.y + 0.06, { fondo: 0.004, borde: 0.008 });
  // bucky mural
  p.c('grisOsc', b.x - b.a / 2, b.x + b.a / 2, b.y - b.b / 2, b.y + b.b / 2, 0, 0.03);
  p.c('gris', b.x - 0.08, b.x + 0.08, b.y - b.b / 2, b.y - b.b / 2 + 0.12, 0.03, b.c);
  p.c('crema', b.x - b.a / 2 + 0.02, b.x + b.a / 2 - 0.02, b.y - b.b / 2 + 0.12, b.y - b.b / 2 + 0.26, b.c * 0.55, b.c * 0.9);
  p.c('grisClaro', b.x - b.a / 2 + 0.06, b.x + b.a / 2 - 0.06, b.y - b.b / 2 + 0.26, b.y - b.b / 2 + 0.262, b.c * 0.58, b.c * 0.87);
  for (const s of [-1, 1]) p.cb('acero', [b.x + s * (b.a / 2), b.y - b.b / 2 + 0.2, b.c * 0.5], [b.x + s * (b.a / 2), b.y - b.b / 2 + 0.2, b.c * 0.95], 0.012, 6);
}, (p) => {
  const sx = p.W / 4, sy = p.D / 3, sz = p.H / 2.2;
  p.c('crema', (-0.4 - 1.1) * sx, (-0.4 + 1.1) * sx, (0.3 - 0.4) * sy, (0.3 + 0.4) * sy, 0, 0.75 * sz);
  p.c('crema', (-0.4 - 0.15) * sx, (-0.4 + 0.15) * sx, (-0.6 - 0.15) * sy, (-0.6 + 0.15) * sy, 0, p.H);
  p.c('blanco', (-0.4 - 0.2) * sx, (-0.4 + 0.2) * sx, (-0.6 + 0.15) * sy, (0.3 + 0.05) * sy, 1.2 * sz, 1.45 * sz);
  p.c('crema', (1.6 - 0.3) * sx, (1.6 + 0.3) * sx, (-1.5) * sy, (-1.05) * sy, 0, 1.9 * sz);
});
def('ecografo', (p) => {
  const { w, d, H } = p;
  ruedas(p, { r: 0.05, dx: w - 0.07, dy: d - 0.09 });
  p.c('grisClaro', -w + 0.03, w - 0.03, -d + 0.04, d - 0.04, 0.11, 0.24);
  p.c('blanco', -w + 0.08, w - 0.08, -d + 0.08, -d + 0.4, 0.24, 0.55);
  p.c('gris', -0.1, 0.1, -d + 0.15, -d + 0.32, 0.55, 0.82);
  const f = p.sub([0, -d + 0.15, 0.84], R2(-12));
  f.c('blanco', -w + 0.01, w - 0.01, -0.05, d * 2 - 0.25, 0, 0.06);
  f.c('grisClaro', -w + 0.06, w - 0.06, 0.08, d * 2 - 0.32, 0.06, 0.065);
  f.cv('negro', 0.0, d * 2 - 0.45, 0.06, 0.075, 0.025, 10);
  for (let i = 0; i < 3; i++) for (let j = 0; j < 2; j++) f.c(i === 1 && j === 0 ? 'trazoVerde' : 'grisOsc', -0.18 + i * 0.07, -0.13 + i * 0.07, 0.2 + j * 0.06, 0.24 + j * 0.06, 0.065, 0.07);
  f.c('pantalla', -0.14, 0.14, 0.0, 0.14, 0.065, 0.068);
  for (const s of [-1, 1]) {
    p.c('grisOsc', s * (w - 0.03) - 0.025, s * (w - 0.03) + 0.025, d - 0.3, d - 0.1, 0.62, 0.76);
    for (let k = 0; k < 2; k++) {
      const y = d - 0.26 + k * 0.1;
      p.cv(k ? 'gris' : 'blanco', s * (w - 0.02), y, 0.7, 0.86, 0.016, 6);
      p.cb('negro', [s * (w - 0.02), y, 0.7], [s * (w), y - 0.05, 0.3], 0.005, 4);
    }
  }
  p.cv('gris', 0, -d + 0.22, 0.9, H - 0.36, 0.025, 8);
  const g = p.sub([0, -d + 0.22, H - 0.36], R2(8));
  g.c('grisOsc', -w + 0.03, w - 0.03, -0.03, 0.0, 0, 0.36);
  g.c('pantalla', -w + 0.05, w - 0.05, 0.0, 0.002, 0.02, 0.34);
  g.cv('pantallaLuz', 0, 0.003, 0.08, 0.3, 0.13, 8, 0.02);
}, (p) => { p.c('grisClaro', -p.w, p.w, -p.d, p.d, 0, 0.24); p.c('blanco', -p.w + 0.08, p.w - 0.08, -p.d + 0.08, -p.d + 0.4, 0.24, 0.85); p.c('blanco', -p.w, p.w, -p.d + 0.1, p.d, 0.85, 0.92); p.c('grisOsc', -p.w + 0.03, p.w - 0.03, -p.d + 0.15, -p.d + 0.22, p.H - 0.4, p.H); });
def('proteccion_radiologica', (p) => {
  const { w, d, H } = p;
  if (p.v === 'biombo' || p.D > 0.4) {
    for (const s of [-1, 1]) {
      p.c('grisOsc', s * (w - 0.06) - 0.03, s * (w - 0.06) + 0.03, -d + 0.02, d - 0.02, 0.05, 0.09);
      for (const sy of [-1, 1]) p.cb('negro', [s * (w - 0.06) - 0.012, sy * (d - 0.06), 0.035], [s * (w - 0.06) + 0.012, sy * (d - 0.06), 0.035], 0.035, 6);
    }
    p.c('grisClaro', -w, w, -0.035, 0.035, 0.09, H * 0.66);
    p.c('grisClaro', -w, w, -0.035, 0.035, H * 0.92, H);
    for (const s of [-1, 1]) p.c('grisClaro', s > 0 ? w - 0.12 : -w, s > 0 ? w : -w + 0.12, -0.035, 0.035, H * 0.66, H * 0.92);
    p.c('vidrioPlomo', -w + 0.12, w - 0.12, -0.012, 0.012, H * 0.66, H * 0.92, true);
    p.c('amarillo', -0.08, 0.08, 0.035, 0.038, H * 0.45, H * 0.53);
    return;
  }
  p.c('acero', -w, w, -d, -d + 0.02, H - 0.15, H);
  const zs = H - 0.1;
  for (let k = 0; k < 4; k++) { const x = -w + 0.08 + (k * (p.W - 0.16)) / 3; p.cb('acero', [x, -d + 0.02, zs], [x, d - 0.02, zs], 0.008, 4); }
  const mandil = (x0, z0, z1, a) => [[x0 - a, z0], [x0 + a, z0], [x0 + a * 1.08, z1 - 0.25], [x0 + a * 0.6, z1], [x0 + a * 0.3, z1], [x0 + a * 0.2, z1 - 0.12], [x0 - a * 0.2, z1 - 0.12], [x0 - a * 0.3, z1], [x0 - a * 0.6, z1], [x0 - a * 1.08, z1 - 0.25]];
  const a = Math.min(w * 0.6, 0.2), dx = Math.max(0, w - a * 1.1);
  ['azul', 'verde', 'grisOsc'].forEach((c, i) => {
    const y = -d + 0.06 + i * (p.D - 0.12) / 2.2;
    p.pf(c, mandil((i - 1) * dx, 0.3 + i * 0.08, zs - 0.01 - i * 0.03, a), 'xz', y, y + 0.03);
  });
  for (const s of [-1, 1]) p.c('tapiz', s * (w - 0.08) - 0.06, s * (w - 0.08) + 0.06, d - 0.05, d - 0.01, H * 0.38, H * 0.48);
}, (p) => { if (p.D > 0.4) { p.c('grisClaro', -p.w, p.w, -0.035, 0.035, 0, p.H); p.c('grisOsc', -p.w, p.w, -p.d, p.d, 0, 0.09); return; } p.c('acero', -p.w, p.w, -p.d, -p.d + 0.02, p.H - 0.15, p.H); p.c('azul', -p.w + 0.05, p.w - 0.05, -p.d + 0.04, p.d - 0.04, 0.45, p.H - 0.1); });

// ---- TIC
def('monitor_escritorio', (p) => {
  const { w, d, H } = p;
  p.c('negro', -0.11, 0.11, -d + 0.01, d - 0.01, 0, 0.015);
  p.c('negro', -0.025, 0.025, -0.05, -0.02, 0.015, H * 0.45);
  pantalla(p, -w, w, H * 0.22, H, 0.0, { marco: 'negro', fondo: 0.025, borde: 0.012 });
  p.c('pantallaLuz', -w + 0.03, -w + 0.22, 0.002, 0.003, H * 0.55, H * 0.9);
  p.c('trazoCian', -w + 0.25, w - 0.04, 0.002, 0.003, H * 0.82, H * 0.86);
}, (p) => { p.c('negro', -0.11, 0.11, -p.d, p.d, 0, 0.015); p.c('negro', -0.025, 0.025, -0.05, -0.02, 0.015, p.H * 0.3); p.c('negro', -p.w, p.w, -0.025, 0.0, p.H * 0.22, p.H); p.c('pantalla', -p.w + 0.012, p.w - 0.012, 0, 0.002, p.H * 0.24, p.H - 0.012); });
def('computador_aio', (p) => {
  const { w, d, H } = p;
  p.c('acero', -0.12, 0.12, -d + 0.01, d - 0.03, 0, 0.012);
  const f = p.sub([0, -0.06, 0.012], R2(-10));
  f.c('acero', -0.04, 0.04, -0.012, 0, 0, H * 0.35);
  p.c('blanco', -w, w, -0.03, 0.0, H * 0.2, H * 0.32);
  pantalla(p, -w, w, H * 0.32, H, 0.0, { marco: 'negro', fondo: 0.03, borde: 0.01 });
  p.c('pantallaLuz', -w + 0.02, w - 0.02, 0.002, 0.003, H * 0.7, H * 0.95);
  p.c('grisClaro', -0.18, 0.18, 0.0, d - 0.005, 0.0, 0.012);
}, (p) => { p.c('acero', -0.12, 0.12, -p.d, p.d - 0.03, 0, 0.012); p.c('acero', -0.04, 0.04, -0.07, -0.05, 0.012, p.H * 0.3); p.c('blanco', -p.w, p.w, -0.03, 0, p.H * 0.2, p.H * 0.32); p.c('negro', -p.w, p.w, -0.03, 0, p.H * 0.32, p.H); });
def('estacion_telemedicina', (p) => {
  const { w, d, H } = p, zm = H * 0.58;
  ruedas(p, { r: 0.05, dx: w - 0.08, dy: d - 0.08 });
  p.c('blanco', -w + 0.03, w - 0.03, -d + 0.03, d - 0.03, 0.12, zm - 0.03);
  for (const s of [-1, 1]) p.c('blanco', s > 0 ? 0.004 : -w + 0.05, s > 0 ? w - 0.05 : -0.004, d - 0.03, d - 0.018, 0.16, zm - 0.06);
  p.c('grisClaro', -w, w, -d, d, zm - 0.03, zm);
  p.c('negro', -0.22, 0.22, 0.05, 0.22, zm, zm + 0.015);
  p.c('grisOsc', 0.26, 0.34, 0.08, 0.2, zm, zm + 0.012);
  p.c('acero', -0.04, 0.04, -d + 0.08, -d + 0.14, zm, zm + 0.08);
  pantalla(p, -w + 0.08, w - 0.08, zm + 0.06, H - 0.07, -d + 0.2, { marco: 'negro', fondo: 0.04, borde: 0.015 });
  p.c('pantallaLuz', -w + 0.12, -0.05, -d + 0.202, -d + 0.203, zm + 0.12, H - 0.12);
  p.c('pantallaLuz', 0.0, w - 0.12, -d + 0.202, -d + 0.203, zm + 0.2, H - 0.12);
  p.c('negro', -0.06, 0.06, -d + 0.15, -d + 0.21, H - 0.07, H - 0.02);
  p.cb('grisOsc', [0, -d + 0.21, H - 0.045], [0, -d + 0.23, H - 0.045], 0.018, 8);
}, (p) => { p.c('blanco', -p.w, p.w, -p.d, p.d, 0, p.H * 0.58); p.c('negro', -p.w + 0.08, p.w - 0.08, -p.d + 0.16, -p.d + 0.2, p.H * 0.58 + 0.06, p.H - 0.06); p.c('pantalla', -p.w + 0.1, p.w - 0.1, -p.d + 0.2, -p.d + 0.205, p.H * 0.58 + 0.08, p.H - 0.08); });
def('impresora', (p) => {
  const { w, d, H } = p;
  p.c('grisClaro', -w, w, -d, d - 0.03, 0.01, H - 0.02);
  p.c('blanco', -w + 0.005, w - 0.005, -d + 0.005, d - 0.035, H - 0.02, H);
  p.c('grisOsc', -w + 0.06, w - 0.06, -d + 0.08, d - 0.12, H - 0.02, H + 0.001);
  p.c('blanco', -w + 0.08, w - 0.08, -d + 0.12, d * 0.1, H + 0.001, H + 0.004);
  p.c('gris', -w + 0.02, w - 0.02, d - 0.03, d, 0.03, H * 0.35);
  p.c('negro', -w + 0.08, w - 0.08, d, d + 0.002, H * 0.28, H * 0.31);
  p.c('pantalla', w - 0.15, w - 0.03, d - 0.03, d - 0.02, H - 0.08, H - 0.03);
  for (const sx of [-1, 1]) for (const sy of [-1, 1]) p.c('negro', sx * (w - 0.04) - 0.02, sx * (w - 0.04) + 0.02, sy * (d - 0.05) - 0.02, sy * (d - 0.05) + 0.02, 0, 0.01);
}, L1.frente('grisClaro', 'gris', 0.05, 0.35));
def('rack', (p) => {
  const { w, d, H } = p;
  p.c('negro', -w, w, -d, d - 0.03, 0.05, H);
  p.c('grisOsc', -w + 0.02, w - 0.02, -d + 0.02, d - 0.02, 0, 0.05);
  const n = 7;
  for (let k = 0; k < n; k++) {
    const z = 0.2 + k * (H - 0.35) / n, h = (H - 0.35) / n * 0.7;
    p.c(k === 2 || k === 3 ? 'gris' : 'grisOsc', -w + 0.06, w - 0.06, d - 0.06, d - 0.035, z, z + h);
    p.c(k % 3 === 0 ? 'trazoCian' : 'trazoVerde', w - 0.14, w - 0.1, d - 0.035, d - 0.032, z + h * 0.4, z + h * 0.6);
    p.c('trazoVerde', w - 0.2, w - 0.17, d - 0.035, d - 0.032, z + h * 0.4, z + h * 0.6);
  }
  p.c('humo', -w + 0.02, w - 0.02, d - 0.02, d - 0.008, 0.06, H - 0.02, true);
  p.c('negro', w - 0.05, w - 0.02, d - 0.008, d, H * 0.45, H * 0.6);
  p.c('grisOsc', -w + 0.05, w - 0.05, -d + 0.05, d - 0.08, H - 0.002, H);
}, L1.frente('negro', 'grisOsc', 0.05, 0.98));
def('digiturno', (p) => {
  const { w, d, H } = p;
  if (p.v === 'kiosco' || H > 1) {
    p.c('grisOsc', -w + 0.03, w - 0.03, -d + 0.03, d - 0.03, 0, 0.03);
    p.c('blanco', -w * 0.55, w * 0.55, -d * 0.5, d * 0.5, 0.03, H - 0.4);
    p.c('negro', -0.08, 0.08, d * 0.5, d * 0.5 + 0.004, H - 0.6, H - 0.58);
    p.c('tapiz', -w * 0.55, w * 0.55, d * 0.5, d * 0.5 + 0.004, H * 0.2, H * 0.28);
    const f = p.sub([0, 0.06, H - 0.36], R2(30));
    f.c('blanco', -w + 0.03, w - 0.03, -d * 0.4, d * 0.4, 0, 0.3);
    pantalla(f, -w + 0.05, w - 0.05, 0.03, 0.28, d * 0.4, { fondo: 0.004, borde: 0.01 });
    f.c('pantallaLuz', -w + 0.08, w - 0.08, d * 0.4 + 0.002, d * 0.4 + 0.003, 0.17, 0.25);
    return;
  }
  p.c('gris', -0.15, 0.15, -d, -d + 0.03, H * 0.3, H * 0.7);
  pantalla(p, -w, w, 0, H, d, { marco: 'negro', fondo: p.D - 0.03, borde: 0.02 });
  for (let k = 0; k < 3; k++) {
    const z = H * (0.72 - k * 0.24);
    p.c('luz', -w + 0.08, -w + 0.08 + p.W * 0.25, d + 0.002, d + 0.003, z - H * 0.07, z + H * 0.07);
    p.c(k === 0 ? 'rojo' : 'blanco', w * 0.15, w - 0.08, d + 0.002, d + 0.003, z - H * 0.07, z + H * 0.07);
  }
}, (p) => { if (p.H > 1) { p.c('blanco', -p.w * 0.55, p.w * 0.55, -p.d * 0.5, p.d * 0.5, 0, p.H - 0.4); p.c('pantalla', -p.w, p.w, -p.d, p.d, p.H - 0.4, p.H); return; } p.c('negro', -p.w, p.w, -p.d, p.d - 0.002, 0, p.H); p.c('pantalla', -p.w + 0.02, p.w - 0.02, p.d - 0.002, p.d, 0.02, p.H - 0.02); });

// ---- laboratorio
def('microscopio', (p) => {
  const { w, d, H } = p;
  p.c('blanco', -w, w, -d, d - 0.03, 0, 0.05);
  p.c('luz', -0.025, 0.025, 0.0, 0.05, 0.05, 0.06);
  p.c('blanco', -0.045, 0.045, -d + 0.02, -d + 0.1, 0.05, H * 0.82);
  for (const s of [-1, 1]) p.cb('negro', [s * 0.045, -d + 0.06, 0.13], [s * 0.075, -d + 0.06, 0.13], 0.025, 10);
  p.c('negro', -0.075, 0.075, -0.07, 0.07, 0.18, 0.195);
  p.c('acero', -0.05, 0.05, -0.04, 0.0, 0.195, 0.2);
  p.cv('acero', 0, 0.0, H * 0.55, H * 0.62, 0.035, 10);
  for (let k = 0; k < 3; k++) { const a = R2(90 + k * 120); p.cv('acero', Math.cos(a) * 0.022, Math.sin(a) * 0.022, H * 0.47, H * 0.55, 0.008, 6); }
  p.c('blanco', -0.05, 0.05, -d + 0.04, 0.05, H * 0.62, H * 0.82);
  for (const s of [-1, 1]) p.cb('negro', [s * 0.022, 0.02, H * 0.8], [s * 0.03, 0.11, H], 0.011, 8);
}, (p) => { p.c('blanco', -p.w, p.w, -p.d, p.d, 0, 0.05); p.c('blanco', -0.045, 0.045, -p.d + 0.02, -p.d + 0.1, 0.05, p.H * 0.82); p.c('negro', -0.075, 0.075, -0.07, 0.07, 0.18, 0.2); p.c('blanco', -0.05, 0.05, -p.d + 0.04, 0.1, p.H * 0.62, p.H); });
def('cabina_bioseguridad', (p) => {
  const { w, d, H } = p, zb = H * 0.34, zt = H * 0.77;
  for (const sx of [-1, 1]) for (const sy of [-1, 1]) p.c('gris', sx * (w - 0.08) - 0.025, sx * (w - 0.08) + 0.025, sy * (d - 0.1) - 0.025, sy * (d - 0.1) + 0.025, 0, zb);
  for (const sy of [-1, 1]) p.c('gris', -w + 0.08, w - 0.08, sy * (d - 0.1) - 0.02, sy * (d - 0.1) + 0.02, 0.15, 0.19);
  p.c('blanco', -w, w, -d, d, zb, zb + 0.05);
  p.c('acero', -w + 0.06, w - 0.06, -d + 0.08, d - 0.1, zb + 0.05, zb + 0.07);
  p.c('negro', -w + 0.06, w - 0.06, d - 0.1, d - 0.06, zb + 0.05, zb + 0.075);
  for (const s of [-1, 1]) p.c('blanco', s * w - (s > 0 ? 0.06 : 0), s * w + (s < 0 ? 0.06 : 0), -d, d, zb, zt);
  p.c('aceroClaro', -w + 0.06, w - 0.06, -d, -d + 0.06, zb + 0.05, zt);
  p.c('blanco', -w + 0.06, w - 0.06, -d, d, zt, zt + 0.12);
  p.c('blanco', -w + 0.06, w - 0.06, d - 0.06, d, zt - 0.08, zt);
  p.c('luz', -w + 0.12, w - 0.12, -d + 0.1, d - 0.15, zt - 0.005, zt);
  const vf = p.sub([0, d - 0.04, zb + 0.28], R2(10));
  vf.c('vidrio', -w + 0.06, w - 0.06, -0.006, 0.006, 0, zt - zb - 0.36, true);
  vf.c('blanco', -w + 0.06, w - 0.06, -0.012, 0.012, -0.03, 0.0);
  pantalla(p, -0.2, 0.2, zt + 0.02, zt + 0.1, d, { fondo: 0.002, borde: 0.008 });
  for (let k = 0; k < 3; k++) p.c(k === 0 ? 'trazoVerde' : 'gris', 0.28 + k * 0.06, 0.32 + k * 0.06, d, d + 0.004, zt + 0.04, zt + 0.08);
  p.c('blanco', -w + 0.04, w - 0.04, -d + 0.03, d - 0.05, zt + 0.12, H - 0.04);
  p.c('grisClaro', -w + 0.12, w - 0.12, -d + 0.1, d - 0.12, H - 0.04, H);
  p.c('gris', -0.25, 0.25, -d + 0.15, d - 0.2, H - 0.002, H);
  p.cv('acero', -w + 0.2, -d + 0.07, zb + 0.07, zb + 0.18, 0.015, 6);
}, (p) => { const zb = p.H * 0.34; p.c('gris', -p.w + 0.05, p.w - 0.05, -p.d + 0.05, p.d - 0.05, 0, zb); p.c('blanco', -p.w, p.w, -p.d, p.d - 0.05, zb, p.H); p.c('vidrio', -p.w + 0.06, p.w - 0.06, p.d - 0.05, p.d, zb + 0.28, p.H * 0.72, true); p.c('acero', -p.w + 0.06, p.w - 0.06, p.d - 0.05, p.d, zb, zb + 0.28); });
def('centrifuga_mesa', (p) => {
  const { w, d, H } = p;
  if (p.v === 'micro' || p.W < 0.35) {
    const R = Math.min(w, d) - 0.01;
    p.cv('blanco', 0, -0.02, 0, H * 0.7, R, 14);
    p.cv('grisClaro', 0, -0.02, H * 0.7, H, R * 0.95, 14, R * 0.8);
    p.cv('humo', 0, -0.02, H - 0.002, H + 0.001, R * 0.5, 12, R * 0.5, true);
    p.c('grisOsc', -0.06, 0.06, d - 0.04, d, 0.02, H * 0.4);
    p.c('pantalla', -0.04, 0.04, d, d + 0.002, H * 0.2, H * 0.35);
    return;
  }
  p.c('blanco', -w, w, -d, d - 0.08, 0, H * 0.72);
  p.c('blanco', -w, w, d - 0.08, d - 0.02, 0, H * 0.25);
  const a = Math.atan2(0.08, H * 0.72), L = Math.hypot(0.08, H * 0.72), f = p.sub([0, d, 0.01], a);
  f.c('grisClaro', -w, w, -0.025, 0, 0, L - 0.01);
  pantalla(f, -w + 0.06, w * 0.2, L * 0.45, L * 0.85, 0.0, { fondo: 0.002, borde: 0.006 });
  for (let k = 0; k < 3; k++) f.c(k === 0 ? 'trazoVerde' : k === 1 ? 'rojo' : 'gris', w * 0.35 + k * 0.05, w * 0.35 + k * 0.05 + 0.035, 0, 0.004, L * 0.55, L * 0.7);
  p.c('blanco', -w, w, -d, d - 0.1, H * 0.72, H * 0.78);
  p.cv('grisClaro', 0, -0.03, H * 0.78, H, Math.min(w, d) * 0.85, 16, Math.min(w, d) * 0.75);
  p.cv('humo', 0, -0.03, H - 0.002, H + 0.001, Math.min(w, d) * 0.4, 12, Math.min(w, d) * 0.4, true);
}, (p) => { p.c('blanco', -p.w, p.w, -p.d, p.d - 0.05, 0, p.H * 0.78); p.c('grisClaro', -p.w * 0.8, p.w * 0.8, -p.d * 0.8, p.d * 0.6, p.H * 0.78, p.H); p.c('grisClaro', -p.w, p.w, p.d - 0.05, p.d, 0, p.H * 0.6); });
def('analizador_mesa', (p) => {
  const { w, d, H } = p, yb = d - Math.min(0.14, p.D * 0.24);
  p.c('blanco', -w, w, -d, yb, 0.0, H);
  p.c('grisClaro', -w + 0.02, w * 0.3, -d + 0.04, yb - 0.04, H, H + 0.004);
  p.c('gris', w * 0.1, w * 0.1 + 0.004, yb, yb + 0.002, H * 0.08, H * 0.92);
  p.c('trazoVerde', -w + 0.03, -w + 0.12, yb, yb + 0.002, H * 0.93, H * 0.95);
  const f = p.sub([w * 0.55, yb, H * 0.62], R2(-15));
  f.c('grisOsc', -w * 0.4, w * 0.4, 0, 0.02, 0, H * 0.32);
  f.c('pantalla', -w * 0.4 + 0.01, w * 0.4 - 0.01, 0.02, 0.022, 0.01, H * 0.32 - 0.01);
  f.c('pantallaLuz', -w * 0.35, 0, 0.022, 0.023, H * 0.18, H * 0.28);
  p.c('grisOsc', -w + 0.02, w - 0.02, yb, d, H * 0.08, H * 0.14);
  p.c('gris', -w + 0.02, w * 0.4, yb + 0.01, d - 0.01, H * 0.14, H * 0.16);
  const n = Math.max(3, Math.min(8, Math.round((w * 1.4) / 0.05))), caps = ['rojo', 'lila', 'azul', 'amarillo', 'verde', 'gris', 'rojo', 'lila'];
  for (let k = 0; k < n; k++) {
    const x = -w + 0.05 + (k * (w * 1.4 - 0.06)) / (n - 1), y = (yb + d) / 2, zt = H * 0.16 + Math.min(0.075, H * 0.18);
    p.cv('acrilico', x, y, H * 0.16, zt, 0.007, 6, 0.007, true);
    p.cv('rosado', x, y, H * 0.16, H * 0.16 + (zt - H * 0.16) * 0.5, 0.0065, 6);
    p.c(caps[k], x - 0.008, x + 0.008, y - 0.008, y + 0.008, zt, zt + 0.015);
  }
}, (p) => { const yb = p.d - Math.min(0.14, p.D * 0.24); p.c('blanco', -p.w, p.w, -p.d, yb, 0, p.H); p.c('grisOsc', -p.w, p.w, yb, p.d, 0, p.H * 0.16); p.c('pantalla', p.w * 0.15, p.w * 0.95, yb, yb + 0.01, p.H * 0.62, p.H * 0.92); });
def('analizador_piso', (p) => {
  const { w, d, H } = p, zd = H * 0.7;
  p.c('negro', -w + 0.03, w - 0.03, -d + 0.03, d - 0.05, 0, 0.06);
  p.c('blanco', -w, w, -d, d - 0.02, 0.06, zd);
  for (let k = 0; k < 3; k++) { const x0 = -w + k * p.W / 3; p.c('blanco', x0 + 0.006, x0 + p.W / 3 - 0.006, d - 0.02, d - 0.008, 0.1, zd - 0.06); p.c('acero', x0 + p.W / 3 - 0.06, x0 + p.W / 3 - 0.04, d - 0.008, d, zd * 0.5, zd * 0.7); }
  p.c('grisClaro', -w, w, -d, d, zd, zd + 0.04);
  const xr = -w * 0.35, R = Math.min(0.22, d - 0.12);
  p.cv('grisOsc', xr, -0.02, zd + 0.04, zd + 0.1, R, 16);
  for (let k = 0; k < 8; k++) { const a = (k * Math.PI) / 4; p.c(k % 2 ? 'blanco' : 'carton', xr + Math.cos(a) * R * 0.7 - 0.025, xr + Math.cos(a) * R * 0.7 + 0.025, -0.02 + Math.sin(a) * R * 0.7 - 0.025, -0.02 + Math.sin(a) * R * 0.7 + 0.025, zd + 0.1, zd + 0.16); }
  const xs = w * 0.15, Rs = Math.min(0.14, d - 0.2);
  p.cv('gris', xs, 0.05, zd + 0.04, zd + 0.08, Rs, 14);
  ['rojo', 'lila', 'azul', 'amarillo', 'rojo', 'lila', 'azul', 'verde'].forEach((c, k) => { const a = (k * Math.PI) / 4; p.c(c, xs + Math.cos(a) * Rs * 0.75 - 0.01, xs + Math.cos(a) * Rs * 0.75 + 0.01, 0.05 + Math.sin(a) * Rs * 0.75 - 0.01, 0.05 + Math.sin(a) * Rs * 0.75 + 0.01, zd + 0.08, zd + 0.14); });
  p.c('vidrio', -w + 0.03, w * 0.45, -d + 0.03, d - 0.03, zd + 0.22, zd + 0.24, true);
  for (const s of [-1, 1]) p.c('vidrio', -w + 0.03, w * 0.45, s * (d - 0.03) - 0.01, s * (d - 0.03) + 0.01, zd + 0.04, zd + 0.22, true);
  p.c('vidrio', -w + 0.02, -w + 0.04, -d + 0.03, d - 0.03, zd + 0.04, zd + 0.22, true);
  p.c('blanco', w * 0.5, w, -d, d, zd + 0.04, zd + 0.12);
  p.cb('gris', [w * 0.75, -d + 0.1, zd + 0.12], [w * 0.75, -d + 0.12, H - 0.25], 0.02, 6);
  const g = p.sub([w * 0.75, -d + 0.14, H - 0.25], R2(-12));
  g.c('negro', -0.17, 0.17, 0, 0.03, 0, 0.24);
  g.c('pantalla', -0.155, 0.155, 0.03, 0.032, 0.015, 0.225);
  g.c('pantallaLuz', -0.14, 0.0, 0.032, 0.033, 0.12, 0.2);
}, (p) => { const zd = p.H * 0.7; p.c('blanco', -p.w, p.w, -p.d, p.d, 0, zd + 0.04); p.c('vidrio', -p.w + 0.03, p.w * 0.45, -p.d + 0.03, p.d - 0.03, zd + 0.04, zd + 0.24, true); p.c('blanco', p.w * 0.5, p.w, -p.d, p.d, zd + 0.04, zd + 0.12); p.c('negro', p.w * 0.5, p.w, -p.d + 0.12, -p.d + 0.16, p.H - 0.25, p.H); });
def('incubadora_lab', (p) => {
  const { w, d, H } = p;
  for (const sx of [-1, 1]) for (const sy of [-1, 1]) p.c('negro', sx * (w - 0.06) - 0.025, sx * (w - 0.06) + 0.025, sy * (d - 0.06) - 0.025, sy * (d - 0.06) + 0.025, 0, 0.04);
  p.c('blanco', -w, w, -d, d - 0.03, 0.04, H);
  p.c('grisClaro', -w + 0.01, w - 0.01, d - 0.03, d - 0.015, 0.06, H - 0.14);
  p.c('vidrio', -w + 0.06, w - 0.1, d - 0.015, d - 0.01, 0.14, H - 0.22, true);
  p.c('acero', w - 0.07, w - 0.05, d - 0.015, d, H * 0.35, H * 0.6);
  p.c('gris', -w + 0.01, w - 0.01, d - 0.03, d - 0.02, H - 0.13, H - 0.01);
  p.c('pantalla', -w + 0.05, -w + 0.2, d - 0.02, d - 0.017, H - 0.1, H - 0.04);
  p.c('rojo', -w + 0.07, -w + 0.15, d - 0.017, d - 0.016, H - 0.08, H - 0.06);
}, L1.frente('blanco', 'grisClaro', 0.08, 0.82));
def('ups', (p) => {
  const { w, d, H } = p;
  p.c('negro', -w, w, -d, d - 0.01, 0.01, H);
  p.c('grisOsc', -w + 0.005, w - 0.005, d - 0.01, d, 0.03, H - 0.02);
  p.c('pantalla', -w * 0.6, w * 0.6, d, d + 0.002, H * 0.7, H * 0.85);
  p.c('trazoVerde', -w * 0.5, w * 0.1, d + 0.002, d + 0.003, H * 0.76, H * 0.79);
  p.cv('trazoVerde', 0, d, H * 0.55, H * 0.6, 0.008, 6);
  for (let k = 0; k < 4; k++) p.c('grisOsc', -w - 0.001, w + 0.001, -d + 0.1 + k * 0.08, -d + 0.13 + k * 0.08, H * 0.2, H * 0.8);
}, L1.frente('negro', 'grisOsc', 0.05, 0.95));

// ---- cadena de frío
function nevera(p, { estantes = 4, vidrio = true } = {}) {
  const { w, d, H } = p, zb = 0.08;
  p.c('grisOsc', -w + 0.02, w - 0.02, -d + 0.02, d - 0.05, 0, zb);
  p.c('negro', -w + 0.04, w - 0.04, d - 0.05, d - 0.04, 0.01, zb - 0.01);
  p.c('blanco', -w, w, -d, -d + 0.04, zb, H);
  for (const s of [-1, 1]) p.c('blanco', s * w - (s > 0 ? 0.04 : 0), s * w + (s < 0 ? 0.04 : 0), -d, d - 0.04, zb, H);
  p.c('blanco', -w, w, -d, d - 0.04, H - 0.12, H);
  p.c('blanco', -w, w, -d, d - 0.04, zb, zb + 0.05);
  p.c('pantalla', -w + 0.08, -w + 0.24, d - 0.04, d - 0.038, H - 0.09, H - 0.04);
  p.c('rojo', -w + 0.1, -w + 0.2, d - 0.038, d - 0.037, H - 0.075, H - 0.055);
  const za = zb + 0.05, zt = H - 0.12, paso = (zt - za) / estantes;
  const cajas = ['azul', 'blanco', 'carton', 'rojo', 'blanco', 'verde'];
  for (let k = 0; k < estantes; k++) {
    const z = za + k * paso;
    if (k > 0) p.c('grisClaro', -w + 0.04, w - 0.04, -d + 0.04, d - 0.1, z - 0.01, z);
    const h = Math.min(0.16, paso * 0.6);
    p.c(cajas[k % 6], -w + 0.07, -0.02, -d + 0.08, d - 0.14, z, z + h);
    p.c(cajas[(k + 2) % 6], 0.02, w - 0.07, -d + 0.08, d - 0.14, z, z + h * 0.7);
  }
  const yp = d - 0.04;
  if (vidrio) {
    p.c('blanco', -w, w, yp, d, zb, zb + 0.06);
    p.c('blanco', -w, w, yp, d, zt - 0.02, zt);
    for (const s of [-1, 1]) p.c('blanco', s * w - (s > 0 ? 0.06 : 0), s * w + (s < 0 ? 0.06 : 0), yp, d, zb + 0.06, zt - 0.02);
    p.c('vidrio', -w + 0.06, w - 0.06, yp + 0.015, yp + 0.025, zb + 0.06, zt - 0.02, true);
  } else p.c('blanco', -w + 0.005, w - 0.005, yp, d - 0.005, zb, zt);
  p.c('acero', w - 0.05, w - 0.03, d, d + 0.012, zb + (zt - zb) * 0.35, zb + (zt - zb) * 0.75);
}
def('nevera_vertical', (p) => nevera(p, { estantes: 5 }), L1.vitrina('blanco'));
def('nevera_media', (p) => nevera(p, { estantes: 4 }), L1.vitrina('blanco'));
def('nevera_bajo_meson', (p) => {
  const { w, d, H } = p;
  p.c('grisOsc', -w + 0.02, w - 0.02, -d + 0.02, d - 0.05, 0, 0.06);
  p.c('blanco', -w, w, -d, d - 0.03, 0.06, H);
  p.c('blanco', -w + 0.005, w - 0.005, d - 0.03, d - 0.012, 0.08, H - 0.1);
  p.c('acero', -w + 0.05, w - 0.05, d - 0.012, d, H - 0.16, H - 0.14);
  p.c('grisClaro', -w, w, d - 0.03, d - 0.02, H - 0.1, H);
  p.c('pantalla', w - 0.18, w - 0.05, d - 0.02, d - 0.018, H - 0.08, H - 0.03);
  p.c('rojo', w - 0.16, w - 0.08, d - 0.018, d - 0.017, H - 0.065, H - 0.045);
}, L1.frente('blanco', 'grisClaro', 0.88, 1));
def('congelador_horizontal', (p) => {
  const { w, d, H } = p, zt = H - 0.08;
  ruedas(p, { r: 0.03, dx: w - 0.05, dy: d - 0.05, vastago: false, col: 'grisOsc' });
  p.c('blanco', -w + 0.01, w - 0.01, -d + 0.01, d - 0.01, 0.06, zt);
  p.c('grisClaro', -w + 0.01, w - 0.01, -d + 0.01, d - 0.01, 0.06, 0.12);
  p.c('blanco', -w, w, -d, d, zt, H - 0.01);
  p.c('grisClaro', -w, w, -d, d, H - 0.01, H);
  p.c('gris', -0.15, 0.15, d, d, zt - 0.06, zt);
  p.c('grisOsc', -0.15, 0.15, d - 0.01, d, zt - 0.06, zt);
  p.c('grisOsc', w - 0.2, w - 0.05, d - 0.01, d, 0.15, 0.25);
  p.c('trazoVerde', w - 0.18, w - 0.14, d, d + 0.002, 0.2, 0.22);
  for (let k = 0; k < 5; k++) p.c('grisOsc', -w - 0.001, -w, -d + 0.1 + k * 0.08, -d + 0.13 + k * 0.08, 0.15, 0.35);
}, (p) => { p.c('blanco', -p.w, p.w, -p.d, p.d, 0, p.H - 0.08); p.c('grisClaro', -p.w, p.w, -p.d, p.d, p.H - 0.08, p.H); });
def('refrigerador_vacunas', (p) => {
  const { w, d, H } = p, zt = H - 0.1;
  p.c('gris', -w + 0.03, w - 0.03, -d + 0.03, d - 0.03, 0, 0.08);
  p.c('blanco', -w, w, -d, d, 0.08, zt);
  p.c('azul', -w - 0.002, w + 0.002, -d - 0.002, d + 0.002, zt - 0.2, zt - 0.14);
  p.c('grisClaro', -w, w, -d, d, zt, H);
  p.c('negro', -0.06, 0.06, d, d + 0.01, zt - 0.06, zt + 0.02);
  p.c('grisOsc', w * 0.3, w - 0.06, d, d + 0.008, zt - 0.12, zt - 0.03);
  p.c('pantalla', w * 0.35, w * 0.6, d + 0.008, d + 0.01, zt - 0.1, zt - 0.05);
  p.c('trazoVerde', w * 0.38, w * 0.55, d + 0.01, d + 0.011, zt - 0.085, zt - 0.07);
}, (p) => { p.c('blanco', -p.w, p.w, -p.d, p.d, 0, p.H - 0.1); p.c('azul', -p.w, p.w, -p.d, p.d, p.H - 0.3, p.H - 0.24); p.c('grisClaro', -p.w, p.w, -p.d, p.d, p.H - 0.1, p.H); });
def('termo_vacunas', (p) => {
  const { w, d, H } = p, zt = H * 0.72;
  p.c('azul', -w, w, -d, d, 0, zt);
  p.c('blanco', -w - 0.005, w + 0.005, -d - 0.005, d + 0.005, zt, zt + 0.05);
  p.c('negro', -0.04, 0.04, d + 0.005, d + 0.012, zt - 0.03, zt + 0.03);
  for (const s of [-1, 1]) p.c('negro', s * (w - 0.03) - 0.012, s * (w - 0.03) + 0.012, -0.012, 0.012, zt + 0.05, H - 0.02);
  p.c('negro', -w + 0.018, w - 0.018, -0.015, 0.015, H - 0.025, H);
}, (p) => { p.c('azul', -p.w, p.w, -p.d, p.d, 0, p.H * 0.72); p.c('blanco', -p.w, p.w, -p.d, p.d, p.H * 0.72, p.H * 0.86); p.c('negro', -p.w + 0.02, p.w - 0.02, -0.015, 0.015, p.H * 0.86, p.H); });
def('caja_termica', (p) => {
  const { w, d, H } = p, zt = H * 0.8;
  p.c('blanco', -w + 0.02, w - 0.02, -d, d, 0, zt);
  p.c('azul', -w + 0.01, w - 0.01, -d - 0.005, d + 0.005, zt, H);
  for (const s of [-1, 1]) p.c('gris', s * (w - 0.02) - 0.02, s * (w - 0.02) + 0.02, -0.08, 0.08, zt - 0.1, zt - 0.04);
  p.c('grisClaro', -0.08, 0.08, d, d + 0.003, 0.1, 0.16);
}, (p) => { p.c('blanco', -p.w, p.w, -p.d, p.d, 0, p.H * 0.8); p.c('azul', -p.w, p.w, -p.d, p.d, p.H * 0.8, p.H); });

// ---- esterilización
def('autoclave_mesa', (p) => {
  const { w, d, H } = p;
  for (const sx of [-1, 1]) for (const sy of [-1, 1]) p.c('negro', sx * (w - 0.05) - 0.02, sx * (w - 0.05) + 0.02, sy * (d - 0.06) - 0.02, sy * (d - 0.06) + 0.02, 0, 0.02);
  p.c('blanco', -w, w, -d, d - 0.02, 0.02, H);
  p.c('grisClaro', -w * 0.5, w * 0.5, -d + 0.05, -d + 0.25, H, H + 0.004);
  const xc = -w * 0.18, zc = H * 0.5, R = Math.min(w * 0.6, H * 0.38);
  p.cb('aceroClaro', [xc, d - 0.02, zc], [xc, d - 0.008, zc], R, 16);
  p.cb('acero', [xc, d - 0.008, zc], [xc, d + 0.004, zc], R * 0.85, 16);
  p.c('negro', xc + R * 0.4, xc + R * 0.9, d + 0.004, d + 0.018, zc - 0.015, zc + 0.015);
  p.c('grisOsc', w * 0.48, w - 0.02, d - 0.02, d, H * 0.15, H * 0.9);
  p.c('pantalla', w * 0.52, w - 0.05, d, d + 0.002, H * 0.6, H * 0.82);
  for (let k = 0; k < 3; k++) p.c(k === 0 ? 'trazoVerde' : 'gris', w * 0.52, w - 0.05, d, d + 0.004, H * (0.25 + k * 0.1), H * (0.31 + k * 0.1));
}, L1.frente('blanco', 'acero', 0.15, 0.85));
def('autoclave_vertical', (p) => {
  const { w, d, H } = p, R = Math.min(w, d) - 0.03;
  for (let k = 0; k < 3; k++) { const a = R2(90 + k * 120); p.c('grisOsc', Math.cos(a) * R * 0.75 - 0.02, Math.cos(a) * R * 0.75 + 0.02, Math.sin(a) * R * 0.75 - 0.02, Math.sin(a) * R * 0.75 + 0.02, 0, 0.06); }
  p.cv('aceroClaro', 0, -0.02, 0.06, H * 0.84, R, 16);
  p.cv('acero', 0, -0.02, H * 0.84, H * 0.9, R + 0.01, 16);
  p.cv('acero', 0, -0.02, H * 0.9, H * 0.95, R * 0.5, 12);
  p.cv('negro', 0, -0.02, H * 0.95, H * 0.97, R * 0.45, 12);
  for (let k = 0; k < 3; k++) p.sub([0, -0.02, 0], 0, R2(k * 60)).c('negro', -R * 0.45, R * 0.45, -0.008, 0.008, H * 0.97, H);
  p.cb('blanco', [0, R - 0.06, H * 0.92], [0, R - 0.06, H], 0.03, 8);
  p.c('blanco', -0.15, 0.15, d - 0.1, d, H * 0.45, H * 0.75);
  p.c('pantalla', -0.11, 0.05, d, d + 0.002, H * 0.6, H * 0.7);
  for (let k = 0; k < 2; k++) p.c(k ? 'rojo' : 'trazoVerde', 0.07 + k * 0.035, 0.095 + k * 0.035, d, d + 0.004, H * 0.62, H * 0.67);
  p.cb('acero', [R * 0.6, 0, 0.15], [w, 0.0, 0.15], 0.012, 6);
}, (p) => { const R = Math.min(p.w, p.d) - 0.03; p.c('aceroClaro', -R, R, -R, R, 0, p.H * 0.9); p.c('acero', -R * 0.5, R * 0.5, -R * 0.5, R * 0.5, p.H * 0.9, p.H); p.c('blanco', -0.15, 0.15, p.d - 0.1, p.d, p.H * 0.45, p.H * 0.75); });
def('autoclave_central', (p) => {
  const { w, d, H } = p;
  p.c('negro', -w + 0.02, w - 0.02, -d + 0.02, d - 0.02, 0, 0.06);
  p.c('acero', -w, w, -d + 0.03, d - 0.03, 0.06, H);
  p.c('grisClaro', -w, w, -0.12, 0.12, 0.06, H);
  for (const s of [-1, 1]) {
    const yf = s * (d - 0.03), sg = s;
    const door = (x0, x1, z0, z1, col, dy) => p.c(col, x0, x1, sg > 0 ? yf : yf - dy, sg > 0 ? yf + dy : yf, z0, z1);
    door(-w + 0.06, w - 0.3, 0.3, H - 0.25, 'aceroClaro', 0.02);
    door(-w + 0.12, w - 0.36, 0.36, H - 0.31, 'acero', 0.026);
    door(-w + 0.4, -w + 0.43, 0.8, 1.3, 'negro', 0.03);
    door(w - 0.25, w - 0.05, H - 0.65, H - 0.3, 'grisOsc', 0.02);
    door(w - 0.23, w - 0.07, H - 0.48, H - 0.33, 'pantalla', 0.022);
    door(w - 0.21, w - 0.12, H - 0.42, H - 0.39, 'trazoVerde', 0.023);
    door(w - 0.23, w - 0.07, H - 0.62, H - 0.52, 'gris', 0.022);
  }
  p.cb('gris', [-w + 0.15, -d + 0.2, H - 0.04], [-w + 0.15, d - 0.2, H - 0.04], 0.04, 8);
}, (p) => { p.c('acero', -p.w, p.w, -p.d, p.d, 0, p.H); p.c('grisClaro', -p.w, p.w, -0.12, 0.12, 0, p.H); p.c('aceroClaro', -p.w + 0.06, p.w - 0.3, p.d - 0.005, p.d + 0.01, 0.3, p.H - 0.25); p.c('aceroClaro', -p.w + 0.06, p.w - 0.3, -p.d - 0.01, -p.d + 0.005, 0.3, p.H - 0.25); });
def('lavadora_desinfectora', (p) => {
  const { w, d, H } = p, z0 = H * 0.2, z1 = H * 0.78;
  p.c('negro', -w + 0.02, w - 0.02, -d + 0.02, d - 0.04, 0, 0.05);
  p.c('acero', -w, w, -d, -d + 0.04, 0.05, H);
  for (const s of [-1, 1]) p.c('acero', s * w - (s > 0 ? 0.04 : 0), s * w + (s < 0 ? 0.04 : 0), -d, d - 0.02, 0.05, H);
  p.c('acero', -w, w, -d, d - 0.02, z1, H);
  p.c('acero', -w, w, -d, d - 0.02, 0.05, z0);
  p.c('grisOsc', -w + 0.04, w - 0.04, -d + 0.04, -d + 0.06, z0, z1);
  for (let k = 1; k <= 3; k++) {
    const z = z0 + (k * (z1 - z0)) / 4;
    p.c('aceroClaro', -w + 0.05, w - 0.05, -d + 0.08, d - 0.1, z - 0.01, z);
    p.c(k === 2 ? 'azulEsteril' : 'acero', -w + 0.1, w - 0.1, -d + 0.12, d - 0.16, z, z + 0.05);
  }
  p.c('aceroClaro', -w, w, d - 0.02, d, z0 - 0.02, z0);
  p.c('aceroClaro', -w, w, d - 0.02, d, z1, z1 + 0.02);
  for (const s of [-1, 1]) p.c('aceroClaro', s * w - (s > 0 ? 0.05 : 0), s * w + (s < 0 ? 0.05 : 0), d - 0.02, d, z0, z1);
  p.c('vidrio', -w + 0.05, w - 0.05, d - 0.015, d - 0.008, z0, z1, true);
  p.c('blanco', -w + 0.02, w - 0.02, d - 0.02, d, z1 + 0.04, H - 0.03);
  pantalla(p, -w + 0.06, w * 0.3, z1 + 0.08, H - 0.07, d, { fondo: 0.002, borde: 0.01 });
  p.c('trazoVerde', w * 0.45, w * 0.6, d, d + 0.004, z1 + 0.12, z1 + 0.18);
  p.c('acero', -w + 0.05, w - 0.05, d - 0.02, d - 0.008, 0.07, z0 - 0.04);
  p.c('negro', -0.08, 0.08, d - 0.008, d, z0 - 0.09, z0 - 0.06);
}, (p) => { p.c('acero', -p.w, p.w, -p.d, p.d - 0.02, 0, p.H); p.c('vidrio', -p.w + 0.05, p.w - 0.05, p.d - 0.02, p.d, p.H * 0.2, p.H * 0.78, true); p.c('blanco', -p.w, p.w, p.d - 0.02, p.d, p.H * 0.8, p.H); });

// ---- equipamiento fijo
def('planta_electrica', (p) => {
  const { w, d, H } = p, zc = H * 0.9;
  p.c('negro', -w, w, -d, d, 0, 0.3);
  p.c('grisVerde', -w + 0.05, w - 0.05, -d + 0.05, d - 0.05, 0.3, zc);
  p.c('grisVerde', -w + 0.02, w - 0.02, -d + 0.02, d - 0.02, zc, zc + 0.04);
  for (const s of [-1, 1]) {
    const y = s * (d - 0.05);
    const n = Math.max(1, Math.min(5, Math.floor((p.W - 0.6) / 0.75)));
    for (let k = 0; k < n; k++) {
      const x = -w + 0.35 + k * ((p.W - 0.7) / n), a = (p.W - 0.7) / n - 0.25;
      p.c('grisOsc', x, x + a, s > 0 ? y : y - 0.005, s > 0 ? y + 0.005 : y, 0.55, zc - 0.25);
      for (const z of [0.75, 1.0, 1.25].filter((z) => z < zc - 0.3)) p.c('negro', x, x + a, s > 0 ? y + 0.005 : y - 0.008, s > 0 ? y + 0.008 : y - 0.005, z, z + 0.03);
    }
  }
  p.c('negro', -w + 0.05, -w + 0.06, -d + 0.15, d - 0.15, 0.45, zc - 0.15);
  p.c('grisOsc', w - 0.06, w - 0.05, -d + 0.2, d - 0.2, 0.5, zc - 0.15);
  pantalla(p.sub([w - 0.05, 0, 0], 0, -Math.PI / 2), -0.2, 0.2, zc - 0.55, zc - 0.25, 0, { fondo: 0.004, borde: 0.02 });
  p.cb('grisOsc', [-w * 0.3, -0.2, zc + 0.04 + 0.07], [w * 0.3, -0.2, zc + 0.04 + 0.07], 0.07, 10);
  p.cv('negro', w * 0.3, -0.2, zc + 0.04, H, 0.05, 8);
  p.c('amarillo', -w + 0.4, -w + 0.6, d - 0.05, d - 0.045, zc - 0.25, zc - 0.1);
}, (p) => { p.c('negro', -p.w, p.w, -p.d, p.d, 0, 0.3); p.c('grisVerde', -p.w + 0.03, p.w - 0.03, -p.d + 0.03, p.d - 0.03, 0.3, p.H * 0.92); p.c('grisOsc', -p.w * 0.3, p.w * 0.3, -0.27, -0.13, p.H * 0.92, p.H); });
def('ups_central', (p) => {
  const { w, d, H } = p;
  p.c('grisOsc', -w, w, -d, d, 0, 0.08);
  for (const s of [-1, 1]) {
    const x0 = s > 0 ? 0.005 : -w, x1 = s > 0 ? w : -0.005;
    p.c('negro', x0, x1, -d, d - 0.02, 0.08, H);
    p.c('grisOsc', x0 + 0.01, x1 - 0.01, d - 0.02, d - 0.008, 0.1, H - 0.02);
    p.c('negro', x1 - 0.06, x1 - 0.04, d - 0.008, d, H * 0.45, H * 0.6);
    for (let k = 0; k < 4; k++) p.c('negro', x0 + 0.06, x1 - 0.1, d - 0.008, d - 0.004, 0.2 + k * 0.08, 0.23 + k * 0.08);
  }
  pantalla(p, -w + 0.12, -w + 0.4, H * 0.7, H * 0.8, d - 0.008, { fondo: 0.002, borde: 0.01 });
  for (let k = 0; k < 3; k++) p.c(['trazoVerde', 'trazoVerde', 'trazoAmarillo'][k], -w + 0.45 + k * 0.04, -w + 0.47 + k * 0.04, d - 0.008, d - 0.002, H * 0.76, H * 0.78);
}, L1.frente('negro', 'grisOsc', 0.05, 0.98));
def('ascensor_cabina', (p) => {
  const { w, d, H } = p, e = 0.04, zt = H - 0.05;
  p.c('gris', -w, w, -d, d, 0, 0.05);
  p.c('caucho', -w + e, w - e, -d + e, d - 0.1, 0.05, 0.052);
  p.c('acero', -w, w, -d, -d + e, 0.05, zt);
  for (const s of [-1, 1]) p.c('acero', s * w - (s > 0 ? e : 0), s * w + (s < 0 ? e : 0), -d, d - 0.06, 0.05, zt);
  p.c('blanco', -w, w, -d, d, zt, H);
  p.c('luz', -w + 0.2, w - 0.2, -d + 0.3, d - 0.4, zt - 0.006, zt);
  const vano = Math.min(1.1, p.W - 0.3), xv = vano / 2;
  for (const s of [-1, 1]) {
    p.c('aceroClaro', s * xv, s * w, d - 0.06, d, 0.05, zt);
    p.cb('acero', [s * (w - e - 0.04), -d + 0.25, 0.9], [s * (w - e - 0.04), d - 0.35, 0.9], 0.016, 6);
  }
  p.c('aceroClaro', -w, w, d - 0.06, d, H - 0.25, zt);
  p.cb('acero', [-w + 0.25, -d + e + 0.04, 0.9], [w - 0.25, -d + e + 0.04, 0.9], 0.016, 6);
  p.c('espejo', -w + 0.3, w - 0.3, -d + e, -d + e + 0.004, 0.95, zt - 0.2);
  p.c('negro', w - e - 0.004, w - e, d - 0.45, d - 0.25, 0.85, 1.4);
  for (let k = 0; k < 6; k++) p.cb('luz', [w - e - 0.006, d - 0.35, 0.95 + k * 0.07], [w - e - 0.012, d - 0.35, 0.95 + k * 0.07], 0.012, 8);
  p.c('pantalla', -0.15, 0.15, d - 0.06 - 0.002, d - 0.06, H - 0.2, H - 0.12);
}, (p) => { p.c('gris', -p.w, p.w, -p.d, p.d, 0, 0.05); p.c('acero', -p.w, p.w, -p.d, -p.d + 0.04, 0.05, p.H); p.c('acero', -p.w, -p.w + 0.04, -p.d, p.d, 0.05, p.H); p.c('acero', p.w - 0.04, p.w, -p.d, p.d, 0.05, p.H); });
function montacargas(p) {
  const { w, d, H } = p, e = 0.03;
  p.c('acero', -w, w, -d, d, 0, e);
  p.c('acero', -w, w, -d, d, H - e, H);
  p.c('acero', -w, w, -d, -d + e, e, H - e);
  for (const s of [-1, 1]) p.c('acero', s * w - (s > 0 ? e : 0), s * w + (s < 0 ? e : 0), -d, d, e, H - e);
  p.c('grisOsc', -w + e, w - e, -d + e, -d + e + 0.004, e, H - e);
  p.c('aceroClaro', -w + e, w - e, -d + e, d - 0.02, H * 0.5, H * 0.5 + 0.015);
  p.c('aceroClaro', -w + 0.01, w - 0.01, d - 0.015, d, H * 0.62, H - 0.01);
  p.c('negro', -0.06, 0.06, d, d + 0.012, H * 0.64, H * 0.67);
  p.c('carton', -w + 0.06, 0.0, -d + 0.08, d - 0.1, e, e + Math.min(0.15, H * 0.2));
  p.c('trazoVerde', w - 0.04, w - 0.02, d, d + 0.003, H * 0.55, H * 0.58);
}
def('montacargas', montacargas, (p) => { p.c('acero', -p.w, p.w, -p.d, p.d, 0, 0.03); p.c('acero', -p.w, p.w, -p.d, p.d, p.H - 0.03, p.H); p.c('acero', -p.w, p.w, -p.d, -p.d + 0.03, 0, p.H); p.c('aceroClaro', -p.w, p.w, p.d - 0.015, p.d, p.H * 0.62, p.H); });
def('manifold_gases', (p) => {
  const { w, d, H } = p, R = Math.min(0.115, (d - 0.05) * 0.6), hc = H * 0.82, yc = d - R - 0.02;
  p.c('blanco', -0.32, 0.32, -d, -d + 0.08, H * 0.45, H - 0.05);
  p.c('verdeSenal', -0.32, 0.32, -d + 0.08, -d + 0.082, H - 0.12, H - 0.06);
  for (const x of [-0.14, 0.14]) { p.cb('blanco', [x, -d + 0.08, H * 0.72], [x, -d + 0.1, H * 0.72], 0.05, 6); p.c('negro', x - 0.004, x + 0.004, -d + 0.1, -d + 0.104, H * 0.72, H * 0.72 + 0.04); }
  p.cb('cobre', [-w + 0.12, -d + 0.1, H * 0.88], [w - 0.12, -d + 0.1, H * 0.88], 0.016, 6);
  p.cb('cobre', [0, -d + 0.1, H * 0.88], [0, -d + 0.1, H - 0.02], 0.016, 6);
  const n = Math.max(1, Math.min(3, Math.floor((w - 0.38) / (2 * R + 0.04))));
  for (const s of [-1, 1]) for (let k = 0; k < n; k++) {
    const x = s * (0.38 + R + k * (2 * R + 0.04));
    cilindroGas(p, x, yc, R, hc, 'oxigeno', 6);
    p.cb('cobre', [x, yc, hc], [x, -d + 0.1, H * 0.88], 0.008, 3);
  }
  for (const s of [-1, 1]) p.c('negro', s * 0.36, s * (0.38 + n * (2 * R + 0.04)), yc + R - 0.01, yc + R + 0.005, hc * 0.6, hc * 0.63);
}, (p) => { p.c('blanco', -0.32, 0.32, -p.d, -p.d + 0.08, p.H * 0.45, p.H); p.c('oxigeno', -p.w + 0.1, -0.36, -p.d + 0.15, p.d - 0.02, 0, p.H * 0.85); p.c('oxigeno', 0.36, p.w - 0.1, -p.d + 0.15, p.d - 0.02, 0, p.H * 0.85); p.c('cobre', -p.w + 0.1, p.w - 0.1, -p.d + 0.08, -p.d + 0.12, p.H * 0.86, p.H * 0.9); });
def('generador_psa', (p) => {
  const { w, d, H } = p;
  p.c('grisOsc', -w, w, -d, d, 0, 0.1);
  for (const x of [-w + 0.3, -w + 0.75]) {
    p.cv('azul', x, -d + 0.35, 0.1, H - 0.3, 0.19, 10);
    p.cv('azul', x, -d + 0.35, H - 0.3, H - 0.18, 0.19, 10, 0.08);
    p.cb('acero', [x, -d + 0.35, H - 0.18], [x, -d + 0.35, H - 0.08], 0.03, 6);
  }
  p.cb('acero', [-w + 0.3, -d + 0.35, H - 0.08], [w - 0.4, -d + 0.35, H - 0.08], 0.025, 6);
  p.cv('oxigeno', w - 0.4, -d + 0.4, 0.1, H - 0.35, 0.3, 12);
  p.cv('oxigeno', w - 0.4, -d + 0.4, H - 0.35, H - 0.12, 0.3, 12, 0.08);
  p.cb('acero', [w - 0.4, -d + 0.4, H - 0.12], [w - 0.4, -d + 0.4, H - 0.08], 0.025, 6);
  p.c('blanco', -0.15, 0.55, d - 0.4, d - 0.05, 0.1, H * 0.85);
  pantalla(p, -0.08, 0.3, H * 0.55, H * 0.75, d - 0.05, { fondo: 0.002, borde: 0.012, trazos: true });
  for (let k = 0; k < 3; k++) p.c(['trazoVerde', 'rojo', 'trazoAmarillo'][k], 0.36 + k * 0.05, 0.39 + k * 0.05, d - 0.05, d - 0.045, H * 0.6, H * 0.63);
  p.c('grisClaro', -w + 0.05, -0.25, d - 0.6, d - 0.05, 0.1, 0.9);
  for (let k = 0; k < 4; k++) p.c('grisOsc', -w + 0.1, -0.3, d - 0.05, d - 0.045, 0.3 + k * 0.12, 0.34 + k * 0.12);
  p.c('verdeSenal', 0.0, 0.3, d - 0.05, d - 0.047, H * 0.78, H * 0.82);
}, (p) => { p.c('grisOsc', -p.w, p.w, -p.d, p.d, 0, 0.1); p.c('azul', -p.w + 0.1, -p.w + 0.95, -p.d + 0.15, -p.d + 0.55, 0.1, p.H - 0.1); p.c('oxigeno', p.w - 0.7, p.w - 0.1, -p.d + 0.1, -p.d + 0.7, 0.1, p.H - 0.1); p.c('blanco', -0.15, 0.55, p.d - 0.4, p.d - 0.05, 0.1, p.H * 0.85); });
def('equipo_presion', (p) => {
  const { w, d, H } = p;
  p.c('grisOsc', -w, w, -d, d, 0, 0.1);
  const xs = [-w * 0.3, w * 0.15, w * 0.6];
  p.cb('acero', [-w + 0.1, -d * 0.4, 0.28], [w - 0.05, -d * 0.4, 0.28], 0.055, 8);
  p.cb('acero', [-w + 0.1, d * 0.05, H * 0.72], [w - 0.05, d * 0.05, H * 0.72], 0.045, 8);
  for (const x of xs) {
    p.cv('acero', x, 0.1, 0.1, 0.55, 0.075, 8);
    p.cv('azulMotor', x, 0.1, 0.55, H * 0.82, 0.095, 10, 0.07);
    p.cb('acero', [x, 0.1, 0.28], [x, -d * 0.4, 0.28], 0.03, 4);
    p.cb('acero', [x, 0.1, 0.48], [x, d * 0.05, H * 0.72], 0.025, 4);
  }
  p.cv('rojo', -w + 0.22, -d + 0.25, 0.1, H * 0.75, 0.17, 10);
  p.cv('rojo', -w + 0.22, -d + 0.25, H * 0.75, H * 0.82, 0.17, 10, 0.06);
  p.c('tablero', w * 0.2, w - 0.05, -d + 0.02, -d + 0.22, H * 0.45, H);
  pantalla(p, w * 0.3, w * 0.6, H * 0.75, H * 0.9, -d + 0.22, { fondo: 0.002, borde: 0.01 });
  p.c('trazoVerde', w * 0.68, w * 0.74, -d + 0.22, -d + 0.225, H * 0.8, H * 0.84);
}, (p) => { p.c('grisOsc', -p.w, p.w, -p.d, p.d, 0, 0.1); p.c('azulMotor', -p.w * 0.45, p.w * 0.75, -0.02, 0.22, 0.1, p.H * 0.86); p.c('rojo', -p.w + 0.05, -p.w + 0.39, -p.d + 0.08, -p.d + 0.42, 0.1, p.H * 0.82); p.c('tablero', p.w * 0.2, p.w - 0.05, -p.d + 0.02, -p.d + 0.22, p.H * 0.45, p.H); });
def('tablero_sistema', (p) => {
  const { w, d, H } = p;
  p.c('tablero', -w, w, -d, d - 0.015, 0, H);
  p.c('tablero', -w + 0.01, w - 0.01, d - 0.015, d - 0.005, 0.01, H - 0.01);
  pantalla(p, -w + 0.06, w * 0.3, H * 0.6, H * 0.85, d - 0.005, { fondo: 0.002, borde: 0.01, trazos: true });
  ['trazoVerde', 'trazoVerde', 'trazoAmarillo', 'rojo'].forEach((c, k) => p.cb(c, [w * 0.45 + k * 0.04, d - 0.005, H * 0.75], [w * 0.45 + k * 0.04, d + 0.002, H * 0.75], 0.009, 6));
  p.c('negro', w - 0.08, w - 0.05, d - 0.005, d + 0.005, H * 0.4, H * 0.5);
  p.c('blanco', -w + 0.06, -w + 0.25, d - 0.005, d - 0.002, H * 0.15, H * 0.25);
}, L1.frente('tablero', 'pantalla', 0.6, 0.85));
def('condensadora', (p) => {
  const { w, d, H } = p;
  for (const s of [-1, 1]) p.c('grisOsc', -w + 0.03, w - 0.03, s * (d - 0.1) - 0.04, s * (d - 0.1) + 0.04, 0, 0.1);
  p.c('grisClaro', -w, w, -d, d - 0.02, 0.1, H);
  p.c('grisOsc', -w + 0.03, w - 0.03, -d - 0.003, -d, 0.15, H - 0.05);
  for (let k = 0; k < 6; k++) p.c('gris', -w - 0.003, -w, -d + 0.08 + k * 0.1, -d + 0.12 + k * 0.1, 0.15, H - 0.05);
  const R = Math.min(w - 0.06, (H - 0.2) / 4 - 0.02);
  for (const z of [0.1 + (H - 0.1) * 0.27, 0.1 + (H - 0.1) * 0.73]) {
    p.cb('grisOsc', [0, d - 0.02, z], [0, d, z], R, 16);
    p.cb('negro', [0, d - 0.021, z], [0, d + 0.004, z], R * 0.9, 16);
    p.cb('gris', [0, d, z], [0, d + 0.012, z], R * 0.18, 8);
    for (let k = 0; k < 3; k++) p.sub([0, d + 0.006, z], 0, 0, R2(k * 60)).c('gris', -R * 0.9, R * 0.9, -0.002, 0.002, -0.004, 0.004);
  }
  p.c('gris', w - 0.004, w, -d + 0.1, d - 0.2, H * 0.6, H * 0.85);
}, (p) => { p.c('grisOsc', -p.w, p.w, -p.d, p.d, 0, 0.1); p.c('grisClaro', -p.w, p.w, -p.d, p.d - 0.02, 0.1, p.H); p.c('negro', -p.w + 0.06, p.w - 0.06, p.d - 0.02, p.d, 0.15, p.H * 0.48); p.c('negro', -p.w + 0.06, p.w - 0.06, p.d - 0.02, p.d, p.H * 0.55, p.H - 0.05); });
def('nevera_mortuoria', (p) => {
  const { w, d, H } = p, zu = H - 0.18;
  for (const sx of [-1, 1]) for (const sy of [-1, 1]) p.c('acero', sx * (w - 0.06) - 0.03, sx * (w - 0.06) + 0.03, sy * (d - 0.06) - 0.03, sy * (d - 0.06) + 0.03, 0, 0.1);
  p.c('acero', -w, w, -d, d - 0.03, 0.1, zu);
  const cols = 2, filas = 2, a = p.W / cols, h = (zu - 0.14) / filas;
  for (let i = 0; i < cols; i++) for (let j = 0; j < filas; j++) {
    const x0 = -w + i * a + 0.02, x1 = -w + (i + 1) * a - 0.02, z0 = 0.12 + j * h + 0.01, z1 = 0.12 + (j + 1) * h - 0.01;
    p.c('aceroClaro', x0, x1, d - 0.03, d - 0.01, z0, z1);
    p.c('negro', x1 - 0.12, x1 - 0.04, d - 0.01, d, (z0 + z1) / 2 - 0.015, (z0 + z1) / 2 + 0.015);
    p.c('blanco', x0 + 0.05, x0 + 0.2, d - 0.01, d - 0.006, z1 - 0.1, z1 - 0.05);
  }
  p.c('grisClaro', -w + 0.1, w - 0.1, -d + 0.05, d - 0.15, zu, H);
  for (let k = 0; k < 6; k++) p.c('grisOsc', -w * 0.6 + k * 0.2 * w, -w * 0.6 + k * 0.2 * w + 0.1, d - 0.15, d - 0.145, zu + 0.03, H - 0.03);
  p.c('pantalla', w - 0.35, w - 0.15, d - 0.01, d - 0.006, zu - 0.08, zu - 0.03);
}, (p) => { p.c('acero', -p.w, p.w, -p.d, p.d, 0, p.H - 0.18); p.c('aceroClaro', -p.w + 0.02, p.w - 0.02, p.d - 0.01, p.d, 0.12, p.H - 0.2); p.c('grisClaro', -p.w + 0.1, p.w - 0.1, -p.d + 0.05, p.d - 0.15, p.H - 0.18, p.H); });

// ---- aparatos sanitarios (16.5)
function contornoRedondo(x0, x1, y0, y1, n = 6) {
  // rectángulo con el borde delantero (+y) en semielipse
  const cx = (x0 + x1) / 2, rx = (x1 - x0) / 2, yc = Math.max(y0, y1 - rx), ry = y1 - yc;
  const pts = [[x0, y0], [x1, y0], [x1, yc]];
  for (let i = 1; i < n; i++) { const a = (Math.PI * i) / n; pts.push([cx + Math.cos(a) * rx, yc + Math.sin(a) * ry]); }
  pts.push([x0, yc]);
  return pts;
}
function grifo(p, x, y, z, alto = 0.16, largo = 0.12, codo = false) {
  p.cv('acero', x, y, z, z + 0.03, 0.025, 8);
  p.cv('acero', x, y, z + 0.03, z + alto, 0.012, 6);
  p.cb('acero', [x, y, z + alto], [x, y + largo, z + alto - 0.04], 0.011, 6);
  if (codo) p.cb('acero', [x, y, z + 0.06], [x + 0.12, y + 0.05, z + 0.07], 0.007, 4);
  else p.cb('acero', [x, y, z + alto * 0.6], [x - 0.05, y, z + alto * 0.6 + 0.04], 0.008, 4);
}
def('lavamanos', (p) => {
  const { w, d, H } = p;
  p.pf('porcelana', contornoRedondo(-w, w, -d, d, 8), 'xy', H * 0.35, H);
  p.pf('porcelana', contornoRedondo(-w * 0.7, w * 0.7, -d, d * 0.6, 6), 'xy', 0, H * 0.35);
  p.pf('agua', contornoRedondo(-w + 0.05, w - 0.05, -d + 0.12, d - 0.04, 8), 'xy', H, H + 0.002);
  p.cv('negro', 0, 0.03, H + 0.002, H + 0.003, 0.018, 6);
  grifo(p, 0, -d + 0.05, H, 0.15, 0.1);
  p.c('blanco', w * 0.55, w * 0.95, -d, -d + 0.08, H + 0.05, H + 0.22);
}, (p) => { p.c('porcelana', -p.w, p.w, -p.d, p.d, p.H * 0.35, p.H); p.c('porcelana', -p.w * 0.6, p.w * 0.6, -p.d, p.d * 0.5, 0, p.H * 0.35); p.c('acero', -0.015, 0.015, -p.d + 0.03, -p.d + 0.15, p.H, p.H + 0.15); });
def('lavamanos_quirurgico', (p) => {
  const { w, d, H } = p, zb = H * 0.45;
  p.c('acero', -w, w, -d, d, H * 0.1, zb);
  p.c('acero', -w, w, -d, d, zb, H * 0.62);
  p.c('acero', -w, w, -d, -d + 0.03, H * 0.62, H);
  p.c('aceroOsc', -w + 0.04, w - 0.04, -d + 0.07, d - 0.04, H * 0.62, H * 0.625);
  p.c('agua', -w + 0.06, w - 0.06, -d + 0.09, d - 0.06, H * 0.625, H * 0.628);
  p.c('acero', -w, w, d - 0.02, d, H * 0.62, H * 0.67);
  for (const s of [-1, 1]) p.c('acero', s * w - (s > 0 ? 0.02 : 0), s * w + (s < 0 ? 0.02 : 0), -d, d, H * 0.62, H * 0.67);
  const n = Math.max(1, Math.min(3, Math.round(p.W / 0.45)));
  for (let k = 0; k < n; k++) { const x = -w + ((k + 0.5) * p.W) / n; grifo(p, x, -d + 0.05, H * 0.62, 0.32, 0.16, true); p.c('negro', x - 0.04, x + 0.04, d - 0.05, d, 0.0, 0.02); }
}, (p) => { p.c('acero', -p.w, p.w, -p.d, p.d, p.H * 0.1, p.H * 0.65); p.c('acero', -p.w, p.w, -p.d, -p.d + 0.03, p.H * 0.65, p.H); p.c('aceroOsc', -p.w + 0.04, p.w - 0.04, -p.d + 0.07, p.d - 0.04, p.H * 0.65, p.H * 0.66); });
def('inodoro', (p) => {
  const { w, d, H } = p, zb = Math.min(0.4, H * 0.5), yt = -d + Math.min(0.2, p.D * 0.28);
  p.pf('porcelana', contornoRedondo(-w * 0.55, w * 0.55, yt - 0.02, d - 0.08, 6), 'xy', 0, zb - 0.12);
  p.pf('porcelana', contornoRedondo(-w + 0.01, w - 0.01, yt, d, 8), 'xy', zb - 0.12, zb - 0.02);
  p.pf('blanco', contornoRedondo(-w, w, yt + 0.02, d + 0.005, 8), 'xy', zb - 0.02, zb + 0.01);
  p.pf('agua', contornoRedondo(-w + 0.06, w - 0.06, yt + 0.08, d - 0.06, 8), 'xy', zb + 0.01, zb + 0.012);
  p.c('porcelana', -w, w, -d, yt, zb - 0.05, H - 0.03);
  p.c('porcelana', -w - 0.005, w + 0.005, -d, yt + 0.005, H - 0.03, H);
  p.cv('acero', 0, (-d + yt) / 2, H, H + 0.006, 0.03, 8);
  p.c('blanco', -w + 0.01, w - 0.01, yt, yt + 0.04, zb + 0.01, zb + 0.06);
}, (p) => { const yt = -p.d + Math.min(0.2, p.D * 0.28); p.c('porcelana', -p.w * 0.6, p.w * 0.6, yt, p.d - 0.08, 0, 0.3); p.c('blanco', -p.w, p.w, yt, p.d, 0.3, 0.41); p.c('porcelana', -p.w, p.w, -p.d, yt, 0.35, p.H); });
def('ducha', (p) => {
  const { w, d, H } = p, xs = w * 0.4, yw = -d + 0.04;
  p.c('grisClaro', -w, w, -d, d, 0, 0.006);
  p.c('acero', -0.06, 0.06, -0.06, 0.06, 0.006, 0.009);
  p.cv('acero', xs, yw, 0.95, H - 0.12, 0.014, 6);
  p.cb('acero', [xs, yw, H - 0.12], [xs, yw + 0.3, H - 0.12], 0.012, 6);
  p.cv('acero', xs, yw + 0.3, H - 0.22, H - 0.12, 0.09, 12, 0.025);
  p.cv('negro', xs, yw + 0.3, H - 0.225, H - 0.22, 0.085, 12);
  p.c('acero', xs - 0.12, xs + 0.12, -d, -d + 0.03, 1.05, 1.17);
  p.cb('acero', [xs, -d + 0.03, 1.11], [xs, -d + 0.08, 1.11], 0.022, 8);
  p.cv('acero', -w * 0.3, yw, 1.1, 1.75, 0.01, 6);
  p.cb('acero', [-w * 0.3, yw, 1.7], [-w * 0.3, yw + 0.06, 1.68], 0.02, 8);
  p.cb('acero', [-w + 0.1, -d + 0.04, 0.8], [w - 0.15, -d + 0.04, 0.8], 0.017, 6);
  for (const x of [-w + 0.1, w - 0.15]) p.cb('acero', [x, -d, 0.8], [x, -d + 0.04, 0.8], 0.02, 6);
  p.c('blanco', -w + 0.05, -w + 0.45, -d, -d + 0.4, 0.44, 0.48);
  p.c('acero', -w + 0.03, w, d - 0.015, d, H - 0.03, H);
  p.c('acero', -w, -w + 0.015, -d, d, H - 0.03, H);
  for (let k = 0; k < 6; k++) p.c(k % 2 ? 'cortina' : 'cortinaOsc', -w + 0.03 + k * 0.05, -w + 0.08 + k * 0.05, d - 0.03 + (k % 2) * 0.015, d - 0.015 + (k % 2) * 0.015, 0.25, H - 0.05);
}, (p) => { p.c('grisClaro', -p.w, p.w, -p.d, p.d, 0, 0.006); p.c('acero', p.w * 0.4 - 0.02, p.w * 0.4 + 0.02, -p.d, -p.d + 0.04, 0.95, p.H); p.c('acero', p.w * 0.4 - 0.09, p.w * 0.4 + 0.09, -p.d + 0.25, -p.d + 0.43, p.H - 0.15, p.H - 0.1); p.c('cortina', -p.w, -p.w + 0.3, p.d - 0.03, p.d, 0.25, p.H); });
def('poceta_aseo', (p) => {
  const { w, d, H } = p, zb = Math.min(0.32, H * 0.55);
  p.c('porcelana', -w, w, -d, d, 0, zb);
  p.c('aceroOsc', -w + 0.06, w - 0.06, -d + 0.06, d - 0.06, zb - 0.002, zb + 0.001);
  p.c('agua', -w + 0.08, w - 0.08, -d + 0.08, d - 0.08, zb + 0.001, zb + 0.002);
  p.c('porcelana', -w, w, d - 0.05, d, zb, zb + 0.02);
  p.cb('acero', [-0.08, -d, H - 0.05], [-0.08, -d + 0.15, H - 0.08], 0.012, 6);
  p.cb('acero', [0.08, -d, H - 0.05], [0.08, -d + 0.15, H - 0.08], 0.012, 6);
  p.cb('acero', [-0.1, -d + 0.01, H - 0.05], [0.1, -d + 0.01, H - 0.05], 0.015, 6);
  p.cb('naranja', [0.08, -d + 0.15, H - 0.08], [w - 0.08, d - 0.1, zb + 0.02], 0.012, 6);
}, (p) => { const zb = Math.min(0.32, p.H * 0.55); p.c('porcelana', -p.w, p.w, -p.d, p.d, 0, zb); p.c('aceroOsc', -p.w + 0.06, p.w - 0.06, -p.d + 0.06, p.d - 0.06, zb, zb + 0.002); p.c('acero', -0.1, 0.1, -p.d, -p.d + 0.15, p.H - 0.08, p.H - 0.04); });
def('lavachatas', (p) => {
  const { w, d, H } = p;
  p.c('negro', -w + 0.02, w - 0.02, -d + 0.02, d - 0.04, 0, 0.05);
  p.c('acero', -w, w, -d, d - 0.02, 0.05, H);
  p.c('aceroClaro', -w + 0.03, w - 0.03, d - 0.02, d, H * 0.38, H * 0.85);
  p.c('acero', -w + 0.08, w - 0.08, d, d + 0.004, H * 0.45, H * 0.75);
  p.c('negro', -0.12, 0.12, d, d + 0.015, H * 0.8, H * 0.83);
  pantalla(p, -w + 0.06, w * 0.3, H * 0.88, H - 0.02, d, { fondo: 0.002, borde: 0.008 });
  p.c('trazoVerde', w * 0.45, w * 0.6, d, d + 0.004, H * 0.9, H * 0.94);
  p.c('negro', w - 0.15, w - 0.05, d - 0.02, d + 0.01, 0.05, 0.08);
}, L1.frente('acero', 'aceroClaro', 0.38, 0.85));
def('barra_apoyo', (p) => {
  const { w, d, H } = p, r = Math.min(0.018, H * 0.4), z = H / 2, yb = d - r - 0.002;
  p.cb('acero', [-w + 0.03, yb, z], [w - 0.03, yb, z], r, 8);
  for (const s of [-1, 1]) {
    p.cb('acero', [s * (w - 0.03), -d, z], [s * (w - 0.03), yb, z], r * 0.9, 8);
    p.cb('aceroClaro', [s * (w - 0.03), -d, z], [s * (w - 0.03), -d + 0.01, z], Math.min(0.035, H * 0.7), 10);
  }
}, (p) => { p.c('acero', -p.w + 0.01, p.w - 0.01, p.d - 0.04, p.d, 0, p.H); p.c('acero', -p.w + 0.01, -p.w + 0.05, -p.d, p.d - 0.04, 0, p.H); p.c('acero', p.w - 0.05, p.w - 0.01, -p.d, p.d - 0.04, 0, p.H); });

// ---- protección contra incendio y evacuación
def('extintor', (p) => {
  const { w, d, H } = p, R = Math.min(0.08, w - 0.02), yc = d - R - 0.01;
  p.c('grisOsc', -0.05, 0.05, -d, -d + 0.02, H * 0.55, H * 0.85);
  p.c('grisOsc', -0.05, 0.05, -d + 0.02, yc - R + 0.005, H * 0.7, H * 0.74);
  p.cv('rojo', 0, yc, 0, H * 0.78, R, 12);
  p.cv('rojo', 0, yc, H * 0.78, H * 0.84, R, 10, R * 0.4);
  p.cv('negro', 0, yc, H * 0.84, H * 0.9, R * 0.35, 8);
  p.c('negro', -0.012, 0.012, yc - 0.06, yc + 0.05, H * 0.9, H * 0.93);
  p.cb('negro', [0, yc - 0.06, H * 0.95], [0, yc + 0.05, H * 0.9], 0.008, 4);
  p.cb('negro', [R * 0.6, yc, H * 0.86], [R + 0.01, yc + 0.02, H * 0.3], 0.01, 6);
  p.cv('negro', R + 0.01, yc + 0.02, H * 0.22, H * 0.3, 0.014, 6, 0.01);
  p.c('blanco', -R * 0.7, R * 0.7, yc + R - 0.01, yc + R + 0.002, H * 0.35, H * 0.6);
  p.cv('grisClaro', -R * 0.4, yc - R * 0.3, H * 0.88, H * 0.9, 0.02, 8);
}, (p) => { const R = Math.min(0.08, p.w - 0.02); p.c('grisOsc', -0.05, 0.05, -p.d, -p.d + 0.02, p.H * 0.55, p.H * 0.85); p.c('rojo', -R, R, p.d - 2 * R - 0.01, p.d - 0.01, 0, p.H * 0.84); p.c('negro', -0.02, 0.02, p.d - R - 0.05, p.d - R + 0.04, p.H * 0.84, p.H); });
def('gabinete_incendio', (p) => {
  const { w, d, H } = p;
  p.c('rojo', -w, w, -d, d - 0.02, 0, H);
  p.c('blanco', -w + 0.03, w - 0.03, -d + 0.02, -d + 0.025, 0.03, H - 0.03);
  const R = Math.min(H * 0.32, w * 0.45);
  p.cb('rojoOsc', [-w * 0.35, -d + 0.03, H * 0.55], [-w * 0.35, d - 0.04, H * 0.55], R, 16);
  p.cb('blanco', [-w * 0.35, -d + 0.03, H * 0.55], [-w * 0.35, d - 0.06, H * 0.55], R * 0.92, 16);
  p.cb('rojoOsc', [-w * 0.35, -d + 0.03, H * 0.55], [-w * 0.35, d - 0.03, H * 0.55], R * 0.35, 10);
  p.cv('rojo', w * 0.55, -0.02, H * 0.08, H * 0.75, Math.min(0.06, d - 0.03), 10);
  p.cv('negro', w * 0.55, -0.02, H * 0.75, H * 0.82, 0.025, 8);
  p.cb('cobre', [w * 0.2, -d + 0.06, H * 0.2], [w * 0.2, -d + 0.06, H * 0.3], 0.03, 8);
  p.c('rojo', -w, w, d - 0.02, d, H - 0.03, H);
  p.c('rojo', -w, w, d - 0.02, d, 0, 0.03);
  for (const s of [-1, 1]) p.c('rojo', s * w - (s > 0 ? 0.03 : 0), s * w + (s < 0 ? 0.03 : 0), d - 0.02, d, 0.03, H - 0.03);
  p.c('vidrio', -w + 0.03, w - 0.03, d - 0.015, d - 0.008, 0.03, H - 0.03, true);
  p.c('blanco', -w * 0.5, w * 0.5, d - 0.008, d - 0.006, H * 0.88, H * 0.95);
  p.c('negro', w - 0.08, w - 0.05, d, d + 0.015, H * 0.45, H * 0.55);
}, (p) => { p.c('rojo', -p.w, p.w, -p.d, p.d - 0.01, 0, p.H); p.c('vidrio', -p.w + 0.03, p.w - 0.03, p.d - 0.01, p.d, 0.03, p.H - 0.03, true); p.c('blanco', -p.w * 0.7, 0, -p.d + 0.03, p.d - 0.05, p.H * 0.25, p.H * 0.85); });
def('senal_evacuacion', (p) => {
  const { w, d, H } = p, y = d;
  p.c('verdeSenal', -w, w, -d, d, 0, H);
  const f = (c, x0, x1, z0, z1) => p.c(c, x0 * w, x1 * w, y, y + 0.002, z0 * H, z1 * H);
  f('blanco', -0.92, -0.38, 0.12, 0.88);
  f('verdeSenal', -0.86, -0.44, 0.18, 0.82);
  p.sub([-0.62 * w, y + 0.002, 0.28 * H], 0, 0, R2(-25)).c('blanco', -0.05 * w, 0.05 * w, 0, 0.002, 0, 0.36 * H);
  p.c('blanco', -0.6 * w, -0.52 * w, y + 0.002, y + 0.004, 0.66 * H, 0.78 * H);
  p.sub([-0.68 * w, y + 0.002, 0.12 * H], 0, 0, R2(30)).c('blanco', -0.03 * w, 0.03 * w, 0, 0.002, 0, 0.2 * H);
  f('blanco', -0.2, 0.55, 0.42, 0.58);
  p.pf('blanco', [[0.5 * w, 0.25 * H], [0.88 * w, 0.5 * H], [0.5 * w, 0.75 * H]], 'xz', y, y + 0.002);
}, (p) => { p.c('verdeSenal', -p.w, p.w, -p.d, p.d, 0, p.H); p.c('blanco', -p.w * 0.2, p.w * 0.8, p.d, p.d + 0.002, p.H * 0.4, p.H * 0.6); });

// ---- instalaciones
def('toma_gases_cabecera', (p) => {
  const { w, d, H } = p;
  p.c('blanco', -w, w, -d, d - 0.02, 0, H);
  p.c('grisClaro', -w, w, d - 0.02, d, H * 0.82, H);
  p.c('luz', -w + 0.04, w - 0.04, d - 0.02, d, H * 0.86, H * 0.96);
  const tomas = [['oxigeno', -0.62], ['oxigeno', -0.52], ['vacio', -0.36], ['vacio', -0.26], ['aire', -0.1]];
  const esc = p.W / 1.5;
  for (const [c, x] of tomas) {
    p.cb(c, [x * esc, d - 0.02, H * 0.45], [x * esc, d, H * 0.45], 0.028, 10);
    p.cb('acero', [x * esc, d, H * 0.45], [x * esc, d + 0.012, H * 0.45], 0.014, 8);
  }
  for (let k = 0; k < 4; k++) { const x = (0.12 + k * 0.12) * esc; p.c(k < 2 ? 'naranja' : 'blanco', x - 0.035, x + 0.035, d - 0.02, d + 0.004, H * 0.25, H * 0.65); p.c('negro', x - 0.012, x + 0.012, d + 0.004, d + 0.005, H * 0.4, H * 0.5); }
  p.cb('rojo', [0.66 * esc, d - 0.02, H * 0.45], [0.66 * esc, d + 0.006, H * 0.45], 0.022, 10);
}, (p) => { p.c('blanco', -p.w, p.w, -p.d, p.d - 0.02, 0, p.H); p.c('oxigeno', -p.w * 0.85, -p.w * 0.6, p.d - 0.02, p.d, p.H * 0.3, p.H * 0.6); p.c('naranja', p.w * 0.15, p.w * 0.6, p.d - 0.02, p.d, p.H * 0.25, p.H * 0.65); p.c('luz', -p.w + 0.04, p.w - 0.04, p.d - 0.02, p.d, p.H * 0.82, p.H); });
def('llamado_enfermeria', (p) => {
  const { w, d, H } = p;
  p.c('blanco', -w, w, -d, d - 0.02, 0, H);
  p.cb('rojo', [0, d - 0.02, H * 0.6], [0, d, H * 0.6], Math.min(w, H) * 0.5, 10);
  p.cb('trazoAmarillo', [0, d - 0.02, H * 0.2], [0, d - 0.005, H * 0.2], Math.min(w, H) * 0.15, 6);
}, (p) => { p.c('blanco', -p.w, p.w, -p.d, p.d - 0.01, 0, p.H); p.c('rojo', -p.w * 0.5, p.w * 0.5, p.d - 0.01, p.d, p.H * 0.4, p.H * 0.8); });

// ---- energía
def('transformador', (p) => {
  const { w, d, H } = p, zt = H * 0.72;
  p.c('grisOsc', -w + 0.05, w - 0.05, -d + 0.05, d - 0.05, 0, 0.1);
  p.c('grisVerde', -w + 0.28, w - 0.28, -d + 0.22, d - 0.22, 0.1, zt);
  p.c('grisVerde', -w + 0.25, w - 0.25, -d + 0.2, d - 0.2, zt, zt + 0.06);
  for (const s of [-1, 1]) {
    for (let k = 0; k < 5; k++) { const x = -w + 0.35 + k * (p.W - 0.7) / 4; p.c('grisVerde', x - 0.012, x + 0.012, s > 0 ? d - 0.22 : -d + 0.02, s > 0 ? d - 0.02 : -d + 0.22, 0.15, zt - 0.05); }
    for (let k = 0; k < 3; k++) { const y = -d + 0.35 + k * (p.D - 0.7) / 2; p.c('grisVerde', s > 0 ? w - 0.28 : -w + 0.04, s > 0 ? w - 0.04 : -w + 0.28, y - 0.012, y + 0.012, 0.15, zt - 0.05); }
  }
  for (let k = 0; k < 3; k++) {
    const x = (k - 1) * 0.3;
    p.cv('bronce', x, -d * 0.35, zt + 0.06, H - 0.05, 0.05, 6, 0.035);
    p.cv('bronce', x, -d * 0.35, zt + 0.16, zt + 0.19, 0.075, 6);
    p.cv('acero', x, -d * 0.35, H - 0.05, H, 0.02, 6);
  }
  for (let k = 0; k < 3; k++) { const x = (k - 1) * 0.2; p.cv('negro', x, d * 0.35, zt + 0.06, zt + 0.22, 0.03, 6); }
  p.c('amarillo', -0.12, 0.12, d - 0.22, d - 0.215, zt - 0.3, zt - 0.12);
  p.c('blanco', 0.2, 0.45, d - 0.22, d - 0.215, zt - 0.3, zt - 0.15);
}, (p) => { p.c('grisOsc', -p.w + 0.05, p.w - 0.05, -p.d + 0.05, p.d - 0.05, 0, 0.1); p.c('grisVerde', -p.w + 0.04, p.w - 0.04, -p.d + 0.04, p.d - 0.04, 0.1, p.H * 0.72); p.c('bronce', -0.4, 0.4, -p.d * 0.35 - 0.05, -p.d * 0.35 + 0.05, p.H * 0.72, p.H); });
def('tablero_electrico', (p) => {
  const { w, d, H } = p;
  p.c('grisOsc', -w, w, -d, d, 0, 0.1);
  p.c('tablero', -w, w, -d, d - 0.02, 0.1, H);
  for (const s of [-1, 1]) {
    const x0 = s > 0 ? 0.004 : -w + 0.01, x1 = s > 0 ? w - 0.01 : -0.004;
    p.c('tablero', x0, x1, d - 0.02, d - 0.008, 0.12, H - 0.04);
    p.c('negro', s > 0 ? x0 + 0.03 : x1 - 0.05, s > 0 ? x0 + 0.05 : x1 - 0.03, d - 0.008, d + 0.01, H * 0.48, H * 0.56);
    for (let k = 0; k < 4; k++) p.c('grisOsc', x0 + 0.06, x1 - 0.06, d - 0.008, d - 0.006, 0.2 + k * 0.04, 0.22 + k * 0.04);
  }
  p.c('pantalla', -w + 0.08, -0.08, d - 0.008, d - 0.006, H * 0.75, H * 0.82);
  p.c('trazoVerde', -w + 0.1, -0.15, d - 0.006, d - 0.005, H * 0.78, H * 0.8);
  for (let k = 0; k < 3; k++) p.cb(['rojo', 'trazoVerde', 'trazoAmarillo'][k], [0.08 + k * 0.06, d - 0.008, H * 0.8], [0.08 + k * 0.06, d, H * 0.8], 0.014, 6);
  p.pf('amarillo', [[-0.06, H * 0.62], [0.06, H * 0.62], [0, H * 0.7]], 'xz', d - 0.008, d - 0.005);
  p.c('negro', -w, w, -d, d, H - 0.003, H);
}, L1.frente('tablero', 'tablero', 0.06, 0.98));
def('banco_baterias', (p) => {
  const { w, d, H } = p;
  p.c('grisOsc', -w, w, -d, d, 0, 0.08);
  for (const sx of [-1, 1]) for (const sy of [-1, 1]) p.c('negro', sx * w - (sx > 0 ? 0.05 : 0), sx * w + (sx < 0 ? 0.05 : 0), sy * d - (sy > 0 ? 0.05 : 0), sy * d + (sy < 0 ? 0.05 : 0), 0.08, H);
  p.c('negro', -w, w, -d, d, H - 0.06, H);
  p.c('negro', -w + 0.05, w - 0.05, -d, -d + 0.03, 0.08, H - 0.06);
  const cols = 2, filas = 6, a = (p.W - 0.1) / cols, h = (H - 0.2) / filas;
  for (let i = 0; i < cols; i++) for (let j = 0; j < filas; j++) {
    const x0 = -w + 0.05 + i * a + 0.01, x1 = -w + 0.05 + (i + 1) * a - 0.01, z0 = 0.1 + j * h + 0.01, z1 = 0.1 + (j + 1) * h - 0.01;
    p.c('grisClaro', x0, x1, -d + 0.05, d - 0.03, z0, z1);
    p.c(j === 5 && i === 1 ? 'trazoAmarillo' : 'trazoVerde', x1 - 0.06, x1 - 0.03, d - 0.03, d - 0.026, (z0 + z1) / 2 - 0.01, (z0 + z1) / 2 + 0.01);
  }
  p.c('negro', -w + 0.05, w - 0.05, d - 0.05, d - 0.03, 0.08, 0.1);
  p.c('naranja', -w + 0.08, w - 0.08, d - 0.02, d - 0.016, H - 0.05, H - 0.02);
}, (p) => { p.c('negro', -p.w, p.w, -p.d, p.d, 0, 0.08); p.c('negro', -p.w, p.w, -p.d, p.d - 0.03, 0.08, p.H); p.c('grisClaro', -p.w + 0.06, p.w - 0.06, p.d - 0.03, p.d, 0.1, p.H - 0.08); });
def('bomba_agua', (p) => {
  const { w, d, H } = p, zc = H * 0.42, R = Math.min(H * 0.32, d - 0.05);
  p.c('grisOsc', -w, w, -d + 0.05, d - 0.05, 0, 0.06);
  p.c('grisOsc', -w + 0.05, w - 0.05, -d * 0.4, d * 0.4, 0.06, zc - R);
  p.cb('azulMotor', [-w + 0.03, 0, zc], [0.05, 0, zc], R, 14);
  p.cb('negro', [-w + 0.01, 0, zc], [-w + 0.03, 0, zc], R * 0.8, 12);
  p.c('azulMotor', -w * 0.5 - 0.08, -w * 0.5 + 0.08, -0.07, 0.07, zc + R - 0.02, zc + R + 0.08);
  p.cb('azul', [0.05, 0, zc], [w * 0.55, 0, zc], R * 1.15, 14);
  p.cb('acero', [w * 0.55, 0, zc], [w - 0.02, 0, zc], R * 0.45, 10);
  p.cb('acero', [w - 0.03, 0, zc], [w, 0, zc], R * 0.65, 10);
  p.cb('acero', [w * 0.3, 0, zc + R], [w * 0.3, 0, H - 0.03], R * 0.38, 10);
  p.cb('acero', [w * 0.3, 0, H - 0.03], [w * 0.3, 0, H], R * 0.55, 10);
}, (p) => { const zc = p.H * 0.42, R = Math.min(p.H * 0.32, p.d - 0.05); p.c('grisOsc', -p.w, p.w, -p.d + 0.05, p.d - 0.05, 0, zc - R); p.c('azulMotor', -p.w + 0.03, 0.05, -R, R, zc - R, zc + R); p.c('azul', 0.05, p.w, -R, R, zc - R, zc + R); p.c('acero', p.w * 0.2, p.w * 0.4, -R * 0.4, R * 0.4, zc + R, p.H); });
def('tanque_agua', (p) => {
  const { w, d, H } = p, R = Math.min(w, d) - 0.02;
  p.c('concreto', -w, w, -d, d, 0, 0.12);
  p.cv('azul', 0, 0, 0.12, H - 0.15, R, 20);
  for (const z of [0.4, 0.8, 1.2].filter((z) => z < H - 0.3)) p.cv('azul', 0, 0, z, z + 0.04, R + 0.012, 20);
  p.cv('azul', 0, 0, H - 0.15, H - 0.05, R, 20, R * 0.4);
  p.cv('negro', 0, 0, H - 0.05, H, R * 0.35, 12);
  p.cb('acero', [R * 0.55, 0, H - 0.1], [R * 0.55, 0, H], 0.03, 6);
  p.cb('acero', [0, -R, 0.25], [0, -d, 0.25], 0.035, 8);
  p.cb('acero', [R * 0.7, -R * 0.7, H - 0.3], [w - 0.02, -d + 0.02, H - 0.3], 0.025, 6);
}, (p) => { const R = Math.min(p.w, p.d) - 0.02; p.c('concreto', -p.w, p.w, -p.d, p.d, 0, 0.12); p.c('azul', -R, R, -R * 0.7, R * 0.7, 0.12, p.H - 0.05); p.c('azul', -R * 0.7, R * 0.7, -R, R, 0.12, p.H - 0.05); p.c('negro', -R * 0.35, R * 0.35, -R * 0.35, R * 0.35, p.H - 0.05, p.H); });
// Fila de módulos: un plano con marco y juntas entre módulos (≤ 26 líneas). Módulos de 2,28 × 1,13 m: si la fila tiene
// ≈ 2,3 m de fondo van verticales (1,13 m a lo largo de la fila); si tiene ≈ 1,1 m, horizontales (2,28 m a lo largo).
// En el piso, inclinada unos 12° sobre patas; «elevada» (pérgola o marquesina), plana arriba con dos postes de 0,15 m en
// los extremos que bajan hasta el piso del nivel (la capa extiende el alto hasta el piso).
function filaSolar(p, lod) {
  const { w, d, H } = p, elevada = p.v === 'elevada';
  const zMax = H - 0.02, zMin = elevada ? Math.max(0, H - Math.min(0.1, H * 0.5)) : Math.max(0.25, zMax - Math.tan(R2(12)) * (p.D - 0.1));
  const L = Math.hypot(p.D - 0.1, zMax - zMin), ang = Math.atan2(zMax - zMin, p.D - 0.1);
  const g = p.sub([0, d - 0.05, zMin], -ang), t = elevada ? Math.min(0.035, (zMax - zMin) * 0.5) : 0.035;
  if (lod === 1) g.c('solar', -w, w, -L, 0, -t, 0);
  else {
    const modulo = p.D > 1.6 ? 1.135 : 2.28, n = Math.max(1, Math.round(p.W / modulo)), juntas = Math.min(n - 1, 26);
    g.c('aceroClaro', -w, w, -L, 0, -t, 0);
    g.c('solar', -w + 0.012, w - 0.012, -L + 0.012, -0.012, 0, 0.004);
    for (let k = 1; k <= juntas; k++) { const x = -w + (k * p.W) / (juntas + 1); g.c('aceroClaro', x - 0.01, x + 0.01, -L + 0.012, -0.012, 0.0, 0.006); }
    g.c('aceroClaro', -w + 0.012, w - 0.012, -L / 2 - 0.006, -L / 2 + 0.006, 0, 0.005);
  }
  if (elevada) {
    for (const s of [-1, 1]) p.c('acero', s * (w - 0.08) - 0.075, s * (w - 0.08) + 0.075, -0.075, 0.075, 0, zMin - t);
    if (lod === 0) for (const s of [-1, 1]) p.c('acero', -w, w, s * (d - 0.15) - 0.03, s * (d - 0.15) + 0.03, zMin - t - 0.08, zMin - t);
    return;
  }
  if (lod === 0) for (const s of [-0.75, -0.25]) g.c('acero', -w, w, s * L - 0.03, s * L + 0.03, -0.09, -0.035);
  const nPatas = lod === 1 ? 2 : Math.max(2, Math.min(6, Math.round(p.W / 3) + 1));
  const patasEn = [0.25, 0.75].map((f) => [d - 0.05 - f * (p.D - 0.1), zMin + f * (zMax - zMin) - 0.09]);
  if (lod === 1) { for (const [y, z] of patasEn) p.c('acero', -w + 0.05, w - 0.05, y - 0.025, y + 0.025, 0, z); return; }
  for (let k = 0; k < nPatas; k++) {
    const x = -w + 0.08 + (k * (p.W - 0.16)) / (nPatas - 1);
    for (const [y, z] of patasEn) p.c('acero', x - 0.025, x + 0.025, y - 0.025, y + 0.025, 0.06, z);
    p.c('concreto', x - 0.1, x + 0.1, patasEn[1][0] - 0.12, patasEn[0][0] + 0.12, 0, 0.06);
  }
}
def('panel_solar_fila', (p) => filaSolar(p, 0), (p) => filaSolar(p, 1));
def('caseta_cubierta', (p) => {
  const { H } = p, w = p.w - 0.15, d = p.d - 0.15, e = 0.15, zt = H - 0.2;
  p.c('concreto', -w, w, -d, d, 0, 0.1);
  for (const s of [-1, 1]) p.c('blanco', s * w - (s > 0 ? e : 0), s * w + (s < 0 ? e : 0), -d, d, 0.1, zt);
  p.c('blanco', -w + e, w - e, -d, -d + e, 0.1, zt);
  const xp = Math.min(0.5, w - 0.6), ap = 0.9;
  p.c('blanco', -w + e, xp - ap / 2, d - e, d, 0.1, zt);
  p.c('blanco', xp + ap / 2, w - e, d - e, d, 0.1, zt);
  p.c('blanco', xp - ap / 2, xp + ap / 2, d - e, d, 2.2, zt);
  p.c('grisOsc', xp - ap / 2, xp + ap / 2, d - e * 0.5 - 0.02, d - e * 0.5 + 0.02, 0.1, 2.2);
  p.c('acero', xp + ap / 2 - 0.12, xp + ap / 2 - 0.06, d - e * 0.5 + 0.02, d - e * 0.5 + 0.05, 1.0, 1.1);
  p.c('concreto', -p.w, p.w, -p.d, p.d, zt, H);
  for (let k = 0; k < 5; k++) p.c('grisOsc', -w + 0.6, -w + 1.6, d, d + 0.01, 1.6 + k * 0.12, 1.66 + k * 0.12);
  p.c('vidrioOsc', w - 1.7, w - 0.6, d, d + 0.01, 1.3, 2.1);
  p.c('amarillo', xp - 0.15, xp + 0.15, d, d + 0.012, 2.3, 2.5);
}, (p) => { p.c('blanco', -p.w + 0.15, p.w - 0.15, -p.d + 0.15, p.d - 0.15, 0, p.H - 0.2); p.c('concreto', -p.w, p.w, -p.d, p.d, p.H - 0.2, p.H); p.c('grisOsc', 0.05, 0.95, p.d - 0.15, p.d - 0.13, 0.1, 2.2); });
def('baranda', (p) => {
  const { w, H } = p, n = Math.max(2, Math.min(40, Math.ceil(p.W / 1.2) + 1));
  for (let k = 0; k < n; k++) { const x = -w + 0.025 + (k * (p.W - 0.05)) / (n - 1); p.c('acero', x - 0.025, x + 0.025, -0.025, 0.025, 0, H - 0.04); }
  p.cb('acero', [-w, 0, H - 0.025], [w, 0, H - 0.025], 0.025, 8);
  p.c('acero', -w, w, -0.008, 0.008, H * 0.5 - 0.015, H * 0.5 + 0.015);
  p.c('acero', -w, w, -0.008, 0.008, 0.02, 0.12);
}, (p) => { p.c('acero', -p.w, p.w, -0.025, 0.025, p.H - 0.05, p.H); p.c('acero', -p.w, p.w, -0.008, 0.008, p.H * 0.5 - 0.015, p.H * 0.5 + 0.015); p.c('acero', -p.w, -p.w + 0.05, -0.025, 0.025, 0, p.H - 0.05); p.c('acero', p.w - 0.05, p.w, -0.025, 0.025, 0, p.H - 0.05); });

// ---- residuos
const COLORES_RESIDUO = { rojo: ['rojo', 'rojoOsc'], verde: ['verde', 'verdeSenal'], negro: ['negro', 'grisOsc'], blanco: ['blanco', 'grisClaro'], gris: ['gris', 'grisOsc'] };
def('contenedor_residuos', (p) => {
  const { w, d, H } = p, [c, ct] = COLORES_RESIDUO[p.v] || COLORES_RESIDUO.rojo, R = 0.1;
  p.pf(c, [[-d + 0.06, R + 0.02], [d - 0.03, 0.06], [d - 0.02, H - 0.08], [-d + 0.04, H - 0.08]], 'yz', -w + 0.03, w - 0.03);
  p.c(ct, -w + 0.01, w - 0.01, -d, d, H - 0.08, H - 0.02);
  p.c(ct, -w + 0.01, w - 0.01, d - 0.04, d, H - 0.12, H - 0.06);
  p.cb(ct, [-w + 0.05, -d + 0.02, H - 0.04], [w - 0.05, -d + 0.02, H - 0.04], 0.022, 6);
  for (const s of [-1, 1]) { p.cb('negro', [s * (w - 0.04), -d + 0.12, R], [s * (w), -d + 0.12, R], R, 12); p.cb('gris', [s * (w - 0.002), -d + 0.12, R], [s * (w), -d + 0.12, R], R * 0.4, 8); }
  p.cb('acero', [-w + 0.04, -d + 0.12, R], [w - 0.04, -d + 0.12, R], 0.015, 6);
  for (const s of [-1, 1]) p.c(ct, s * (w * 0.5) - 0.05, s * (w * 0.5) + 0.05, d - 0.1, d - 0.03, 0, 0.07);
  p.c('blanco', -0.12, 0.12, d - 0.022, d - 0.018, H * 0.45, H * 0.65);
  p.pf(c === 'rojo' ? 'negro' : 'rojo', [[-0.06, H * 0.5], [0.06, H * 0.5], [0, H * 0.6]], 'xz', d - 0.018, d - 0.016);
}, (p) => { const [c, ct] = COLORES_RESIDUO[p.v] || COLORES_RESIDUO.rojo; p.c(c, -p.w + 0.03, p.w - 0.03, -p.d + 0.04, p.d - 0.03, 0.06, p.H - 0.08); p.c(ct, -p.w, p.w, -p.d, p.d, p.H - 0.08, p.H); p.c('negro', -p.w, p.w, -p.d + 0.02, -p.d + 0.22, 0, 0.2); });
def('bascula_residuos', (p) => {
  const { w, d, H } = p;
  p.c('grisOsc', -w, w, -d, d, 0, H * 0.6);
  p.c('acero', -w + 0.02, w - 0.02, -d + 0.02, d - 0.02, H * 0.6, H * 0.9);
  for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) p.c('aceroOsc', -w + 0.08 + i * (p.W - 0.16) / 3 - 0.03, -w + 0.08 + i * (p.W - 0.16) / 3 + 0.03, -d + 0.08 + j * (p.D - 0.16) / 3 - 0.008, -d + 0.08 + j * (p.D - 0.16) / 3 + 0.008, H * 0.9, H * 0.92);
  p.c('amarillo', -w, w, d - 0.03, d, H * 0.6, H * 0.9);
  p.c('blanco', w - 0.18, w - 0.04, -d + 0.04, -d + 0.14, H * 0.9, H);
  p.c('pantalla', w - 0.16, w - 0.06, -d + 0.06, -d + 0.12, H, H + 0.002);
}, (p) => { p.c('grisOsc', -p.w, p.w, -p.d, p.d, 0, p.H * 0.6); p.c('acero', -p.w + 0.02, p.w - 0.02, -p.d + 0.02, p.d - 0.02, p.H * 0.6, p.H * 0.9); p.c('blanco', p.w - 0.18, p.w - 0.04, -p.d + 0.04, -p.d + 0.14, p.H * 0.9, p.H); });

// ---- exteriores
def('ambulancia', (p) => {
  const { w, d, H } = p, sy = p.D / 5.4, sz = H / 2.6, R = 0.38 * sz;
  const perfil = [[-2.7, 0.45], [2.62, 0.45], [2.7, 0.55], [2.7, 0.95], [2.45, 1.08], [1.75, 1.22], [1.35, 2.05], [1.0, 2.12], [0.95, 2.55], [-2.68, 2.55], [-2.7, 2.5]].map(([y, z]) => [y * sy, z * sz]);
  p.pf('blanco', perfil, 'yz', -w + 0.04, w - 0.04);
  p.c('negro', -w + 0.06, w - 0.06, (2.62 - 0.02) * sy, d, 0.35 * sz, 0.62 * sz);
  p.c('grisOsc', -w + 0.04, w - 0.04, -d, -d + 0.08, 0.35 * sz, 0.55 * sz);
  const ws = p.sub([0, 1.75 * sy, 1.22 * sz], Math.atan2(0.4 * sy, 0.83 * sz));
  ws.c('vidrioOsc', -w + 0.12, w - 0.12, -0.01, 0.01, 0.02, Math.hypot(0.4 * sy, 0.83 * sz) - 0.04);
  for (const s of [-1, 1]) {
    const x = s * (w - 0.04), xo = s > 0 ? x : x - 0.006, x1 = s > 0 ? x + 0.006 : x;
    p.c('vidrioOsc', xo, x1, 1.05 * sy, 1.6 * sy, 1.35 * sz, 1.95 * sz);
    p.c('rojo', xo, x1, -2.7 * sy, 2.42 * sy, 1.0 * sz, 1.12 * sz);
    p.c('naranja', xo, x1, -2.7 * sy, 0.9 * sy, 2.2 * sz, 2.28 * sz);
    p.c('vidrioOsc', xo, x1, -1.2 * sy, -0.3 * sy, 1.55 * sz, 1.95 * sz);
    p.c('negro', s * (w - 0.04) - 0.04 * (s < 0), s * (w - 0.04) + 0.04 * (s > 0), 1.2 * sy, 1.3 * sy, 1.55 * sz, 1.75 * sz);
    for (const yr of [-1.65, 1.75]) {
      p.cb('negro', [s * (w - 0.3), yr * sy, R], [s * (w - 0.04), yr * sy, R], R, 10);
      p.cb('acero', [s * (w - 0.04), yr * sy, R], [s * (w - 0.035), yr * sy, R], R * 0.55, 6);
    }
    p.c('rojo', s * (w - 0.2) - 0.12, s * (w - 0.2) + 0.12, 0.85 * sy, 0.95 * sy, 2.45 * sz, 2.6 * sz);
    p.c('rojo', s * (w - 0.2) - 0.1, s * (w - 0.2) + 0.1, -2.7 * sy, -2.6 * sy, 2.42 * sz, 2.52 * sz);
  }
  p.c('blanco', -0.25, 0.25, 0.85 * sy, 0.95 * sy, 2.45 * sz, 2.6 * sz);
  p.c('grisOsc', -0.005, 0.005, -2.71 * sy, -2.69 * sy, 0.5 * sz, 2.45 * sz);
  p.c('rojo', -0.35, 0.35, -2.71 * sy, -2.7 * sy, 1.0 * sz, 1.12 * sz);
  p.c('vidrioOsc', -w + 0.2, -0.05, -2.715 * sy, -2.7 * sy, 1.55 * sz, 2.0 * sz);
  p.c('vidrioOsc', 0.05, w - 0.2, -2.715 * sy, -2.7 * sy, 1.55 * sz, 2.0 * sz);
  p.c('luz', -w + 0.12, -w + 0.4, 2.69 * sy, 2.7 * sy, 0.8 * sz, 0.9 * sz);
  p.c('luz', w - 0.4, w - 0.12, 2.69 * sy, 2.7 * sy, 0.8 * sz, 0.9 * sz);
}, (p) => { const sy = p.D / 5.4, sz = p.H / 2.6; p.c('blanco', -p.w + 0.04, p.w - 0.04, -p.d, 0.95 * sy, 0.4 * sz, p.H); p.c('blanco', -p.w + 0.04, p.w - 0.04, 0.95 * sy, p.d, 0.4 * sz, 1.9 * sz); p.c('negro', -p.w, p.w, -1.95 * sy, -1.35 * sy, 0, 0.6 * sz); p.c('negro', -p.w, p.w, 1.45 * sy, 2.05 * sy, 0, 0.6 * sz); });
def('montacargas_muestras', montacargas, (p) => { p.c('acero', -p.w, p.w, -p.d, p.d, 0, 0.03); p.c('acero', -p.w, p.w, -p.d, p.d, p.H - 0.03, p.H); p.c('acero', -p.w, p.w, -p.d, -p.d + 0.03, 0, p.H); p.c('aceroClaro', -p.w, p.w, p.d - 0.015, p.d, p.H * 0.62, p.H); });
def('escalera_tramo', (p) => {
  const { w, d, H } = p, n = Math.max(2, Math.min(18, Math.round(H / 0.175))), cont = H / n, huella = p.D / n;
  for (let k = 0; k < n; k++) {
    const y0 = -d + k * huella;
    p.c('concreto', -w, w, y0, d, k * cont, (k + 1) * cont);
    if (n <= 14) p.c('grisOsc', -w + 0.03, w - 0.03, y0, y0 + 0.04, (k + 1) * cont, (k + 1) * cont + 0.004);
  }
  for (const s of [-1, 1]) {
    const x = s * (w - 0.05);
    p.cb('acero', [x, -d, 0.9], [x, d, H + 0.9], 0.022, 6);
    for (const t of [0.05, 0.5, 0.95]) p.cb('acero', [x, -d + t * p.D, t * H], [x, -d + t * p.D, t * H + 0.9], 0.015, 4);
  }
}, (p) => { for (let k = 0; k < 4; k++) p.c('concreto', -p.w, p.w, -p.d + (k * p.D) / 4, p.d, (k * p.H) / 4, ((k + 1) * p.H) / 4); });

// ---- insumos e implementos visibles (16.2 y 16.5)
def('reactivo_caja', (p) => {
  const { w, d, H } = p;
  p.c('blanco', -w, w, -d, d, 0, H);
  p.c('azul', -w - 0.001, w + 0.001, -d - 0.001, d + 0.001, H * 0.62, H * 0.82);
  p.c('blanco', -w * 0.7, w * 0.2, d + 0.001, d + 0.002, H * 0.2, H * 0.5);
  p.c('rojo', w * 0.4, w * 0.8, d + 0.001, d + 0.002, H * 0.2, H * 0.35);
}, (p) => { p.c('blanco', -p.w, p.w, -p.d, p.d, 0, p.H * 0.62); p.c('azul', -p.w, p.w, -p.d, p.d, p.H * 0.62, p.H * 0.82); p.c('blanco', -p.w, p.w, -p.d, p.d, p.H * 0.82, p.H); });
def('frasco_reactivo', (p) => {
  const { w, d, H } = p, R = Math.min(w, d) - 0.002;
  p.cv('bronce', 0, 0, 0, H * 0.68, R, 8);
  p.cv('blanco', 0, 0, H * 0.25, H * 0.55, R + 0.001, 8);
  p.cv('bronce', 0, 0, H * 0.68, H * 0.78, R, 8, R * 0.45);
  p.cv('azul', 0, 0, H * 0.78, H, R * 0.5, 8);
}, (p) => { p.c('bronce', -p.w, p.w, -p.d, p.d, 0, p.H * 0.75); p.c('azul', -p.w * 0.5, p.w * 0.5, -p.d * 0.5, p.d * 0.5, p.H * 0.75, p.H); });
def('gradilla_tubos', (p) => {
  // gradilla con una fila de tubos (muestra hasta la mitad y tapa de color): ≈ 250 triángulos, porque va instanciada
  const { w, d, H } = p, n = Math.max(2, Math.min(7, Math.round(p.W / 0.035)));
  p.c('celeste', -w, w, -d, d, 0, 0.008);
  p.c('celeste', -w, w, -d, d, H * 0.45, H * 0.45 + 0.008);
  for (const s of [-1, 1]) p.c('celeste', s * w - (s > 0 ? 0.006 : 0), s * w + (s < 0 ? 0.006 : 0), -d, d, 0, H * 0.45);
  const caps = ['rojo', 'lila', 'azul', 'amarillo', 'verde', 'gris', 'rojo'];
  for (let k = 0; k < n; k++) {
    const x = -w + 0.02 + (k * (p.W - 0.04)) / (n - 1), R = Math.min(0.007, (p.W - 0.04) / (n - 1) / 2 - 0.001);
    p.cv(k % 3 === 0 ? 'rosado' : 'amarillo', x, 0, 0.008, H * 0.88, R, 6);
    p.c(caps[k], x - R * 1.2, x + R * 1.2, -R * 1.2, R * 1.2, H * 0.88, H);
  }
}, (p) => { p.c('celeste', -p.w, p.w, -p.d, p.d, 0, p.H * 0.45); p.c('rosado', -p.w + 0.01, p.w - 0.01, -0.008, 0.008, p.H * 0.45, p.H * 0.88); p.c('rojo', -p.w + 0.01, p.w - 0.01, -0.009, 0.009, p.H * 0.88, p.H); });
def('pipeta_set', (p) => {
  // soporte con micropipetas colgadas (cuerpo, empuñadura de color y punta): ≈ 330 triángulos
  const { w, d, H } = p, n = Math.max(1, Math.min(4, Math.round(p.W / 0.07)));
  p.c('blanco', -w, w, -d, d, 0, 0.02);
  p.c('blanco', -w + 0.02, w - 0.02, -d + 0.02, -d + 0.04, 0.02, H * 0.85);
  p.c('blanco', -w + 0.02, w - 0.02, -d + 0.02, -d + 0.07, H * 0.7, H * 0.74);
  for (let k = 0; k < n; k++) {
    const x = -w + 0.05 + (k * (p.W - 0.1)) / Math.max(1, n - 1);
    const c = ['azul', 'amarillo', 'rojo', 'verde'][k];
    p.cv('grisClaro', x, -d + 0.07, H * 0.25, H * 0.68, 0.012, 6);
    p.cv(c, x, -d + 0.07, H * 0.68, H, 0.014, 6, 0.008);
    p.cv('blanco', x, -d + 0.07, H * 0.08, H * 0.25, 0.002, 6, 0.008);
  }
}, (p) => { p.c('blanco', -p.w, p.w, -p.d, p.d, 0, 0.02); p.c('blanco', -p.w + 0.02, p.w - 0.02, -p.d + 0.02, -p.d + 0.04, 0.02, p.H * 0.85); p.c('grisClaro', -p.w + 0.03, p.w - 0.03, -p.d + 0.055, -p.d + 0.085, p.H * 0.1, p.H); });

// todos los modelos de la lista cerrada tienen su definición (se comprueba al cargar el módulo)
for (const id of MODELOS) if (!DEF[id]) throw new Error(`equipos3d: el modelo ${id} no tiene definición`);

// ---------------------------------------------------------------- geometrías
const LIMITE_LOD0 = 600, LIMITE_LOD0_GRANDE = 1500, LIMITE_LOD1 = 48;
const GRANDES = new Set(['rayos_x_convencional', 'unidad_odontologica', 'cabina_bioseguridad']);
// presupuesto de triángulos de cada modelo (5.1)
export function limiteTriangulos(modelo, lod) { return lod === 1 ? LIMITE_LOD1 : GRANDES.has(modelo) ? LIMITE_LOD0_GRANDE : LIMITE_LOD0; }

function medidas(modelo, dim) {
  const n = NOMINAL[modelo];
  if (Array.isArray(dim) && dim.length === 3 && dim.every((v) => Number.isFinite(+v) && +v > 0)) return dim.map(Number);
  return [n[0], n[1], n[2]];
}
function construir(modelo, dim, lod, variante) {
  const [W, D, H] = dim, p = new Piezas(W, D, H, variante || null), def = DEF[modelo];
  (lod === 1 ? def.lod1 : def.lod0)(p);
  return p.geom();
}

// Geometría de un modelo a sus medidas reales (m) y en el nivel de detalle pedido. Devuelve una BufferGeometry no indexada
// con position, normal y color (las partes opacas); los vidrios y acrílicos van aparte en geometry.userData.vidrio (o null)
// para el material transparente. userData también trae { piezas, triangulos }. Lanza error con un modelo desconocido.
// op.variante: «pedestal», «biombo», «kiosco», «micro», «plegada», «poceta», «inoxidable», «gavetas», «laboratorio»,
// «elevada» o el color de un contenedor de residuos.
export function geometria(modelo, dim, lod = 0, op = {}) {
  exigirModelo(modelo);
  const variante = op.variante ?? null;
  return construir(modelo, medidas(modelo, dim ?? (variante && VARIANTES[modelo]?.[variante]) ?? null), lod === 1 ? 1 : 0, variante);
}
// triángulos de un modelo (opacos más transparentes)
export function triangulos(modelo, dim, lod = 0, op = {}) {
  const g = geometria(modelo, dim, lod, op), n = g.userData.triangulos;
  g.userData.vidrio?.dispose(); g.dispose();
  return n;
}
// medidas nominales (Anexo C y 16.5) y familia de un modelo, para quien no tenga el catálogo a mano
export function nominal(modelo) { exigirModelo(modelo); const [a, b, c, f, m] = NOMINAL[modelo]; return { dim: [a, b, c], familia: f, montaje: m }; }

// caché de geometrías base que comparten las capas (no se liberan con la capa)
const CACHE = new Map();
function base(modelo, dim, variante, lod) {
  const k = `${modelo}|${variante || ''}|${dim.map((v) => v.toFixed(3)).join(',')}|${lod}`;
  let g = CACHE.get(k);
  if (!g) {
    if (CACHE.size > 800) { const [k0, g0] = CACHE.entries().next().value; CACHE.delete(k0); g0.userData.vidrio?.dispose(); g0.dispose(); }
    g = construir(modelo, dim, lod, variante);
    g.userData.clave = k;
    CACHE.set(k, g);
  }
  return g;
}

// ---------------------------------------------------------------- materiales (5.1)
// Uno opaco con colores por vértice, uno transparente para vidrios y acrílicos y uno para las unidades fantasma. Las
// InstancedMesh usan una copia del opaco que acepta un color de reemplazo por instancia (atributo «mezcla»: rgb y
// cuánto reemplaza): así colorear() reemplaza el color en vez de multiplicarlo, que es lo que haría setColorAt.
let MATS = null;
export function materiales() {
  if (MATS) return MATS;
  const opaco = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.7, metalness: 0.05 });
  const inst = opaco.clone();
  inst.onBeforeCompile = (sh) => {
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', '#include <common>\nattribute vec4 mezcla;\nvarying vec4 vMezcla;')
      .replace('#include <begin_vertex>', '#include <begin_vertex>\nvMezcla = mezcla;');
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', '#include <common>\nvarying vec4 vMezcla;')
      .replace('#include <color_fragment>', '#include <color_fragment>\ndiffuseColor.rgb = mix(diffuseColor.rgb, diffuse * vMezcla.rgb, vMezcla.a);');
  };
  inst.customProgramCacheKey = () => 'equipos3d-mezcla';
  // doble cara en una sola pasada: una llamada por malla transparente (three hace dos si no, una por cara)
  const vidrio = new THREE.MeshStandardMaterial({ vertexColors: true, transparent: true, opacity: 0.3, roughness: 0.12, metalness: 0, depthWrite: false, side: THREE.DoubleSide, forceSinglePass: true });
  const fantasma = new THREE.MeshStandardMaterial({ color: 0x6250d6, transparent: true, opacity: 0.35, depthWrite: false, roughness: 0.6, metalness: 0 });
  MATS = { opaco, inst, vidrio, fantasma };
  const tema = (t) => {
    if (!t) return;
    const oscuro = t.bg.r + t.bg.g + t.bg.b < 0.3;
    for (const m of [opaco, inst]) m.color.setScalar(oscuro ? 0.9 : 1);
    vidrio.opacity = oscuro ? 0.38 : 0.3;
    fantasma.color.copy(t.data);
  };
  try { tema(tokens()); } catch { /* sin documento */ }
  onTheme(tema);
  return MATS;
}

// ---------------------------------------------------------------- unidades
// (x, y, z) de planta, z sobre el piso terminado del nivel → three
export function aThree([x, y, z], nivel) { return new THREE.Vector3(+x || 0, (+(nivel?.z) || 0) + (+z || 0), -(+y || 0)); }

const COLUMNAS = ['id', 'linea_idx', 'piso', 'recinto', 'x', 'y', 'z', 'rot_z', 'apoyo_idx', 'dentro_de_idx', 'componente_de_idx', 'montaje', 'estado'];
// Lleva una UnidadWeb a un objeto. Acepta la fila compacta de torre_inventario.json (con op.lineas y, si cambia, op.columnas;
// op.extra es su entrada de unidades_extra: m3d, dim, var), un objeto con esos mismos nombres o la unidad del inventario de
// datos (posicion, rotacion_z, linea).
export function normalizarUnidad(u, { lineas = null, columnas = COLUMNAS, extra = null } = {}) {
  if (u == null) return null;
  let o = u;
  if (Array.isArray(u)) { o = {}; columnas.forEach((c, i) => { o[c] = u[i]; }); }
  const l = lineas && Number.isInteger(o.linea_idx) && o.linea_idx >= 0 ? lineas[o.linea_idx] : (o.linea && typeof o.linea === 'object' ? o.linea : null);
  const x = extra || o.extra || {};
  const pos = Array.isArray(o.posicion) ? o.posicion : [o.x, o.y, o.z];
  return {
    id: o.id, modelo: o.modelo3d ?? o.modelo ?? x.m3d ?? l?.modelo3d ?? null, variante: o.variante ?? x.var ?? l?.variante ?? null,
    dim: o.dim ?? o.dim_m ?? x.dim ?? l?.dim ?? l?.dim_m ?? null, x: +pos[0] || 0, y: +pos[1] || 0, z: +pos[2] || 0,
    rot: +(o.rot_z ?? o.rotacion_z ?? o.rot ?? 0) || 0, montaje: o.montaje ?? null, estado: o.estado ?? null, recinto: o.recinto ?? null, piso: o.piso ?? null,
  };
}
// Unidades de un nivel de torre_inventario.json (forma web, 10.1 y 10.2) ya normalizadas. nivel: 'EXT', 'P1'…'P4', 'BT', 'CUB'
// o el número de piso. parte: el archivo del nivel (torre_inventario_P2.json: unidades y unidades_extra) cuando el inventario
// viene partido; sin él se usan inventario.unidades.
export function unidadesDelPiso(inventario, nivel, parte = null) {
  const cols = inventario?.columnas_unidades || COLUMNAS, ip = cols.indexOf('piso');
  const clave = typeof nivel === 'number' || /^\d+$/.test(String(nivel)) ? `P${nivel}` : String(nivel);
  const tramo = inventario?.por_nivel?.[clave];
  const extra = { ...(inventario?.unidades_extra || {}), ...(parte?.unidades_extra || {}) };
  let filas, i0 = 0;
  if (parte?.unidades) { filas = parte.unidades; i0 = tramo ? tramo[0] : 0; }
  else if (tramo && inventario?.unidades?.length >= tramo[1]) { filas = inventario.unidades.slice(tramo[0], tramo[1]); i0 = tramo[0]; }
  else {
    const todas = inventario?.unidades || [], pisoDe = (f) => (Array.isArray(f) ? f[ip] : f.piso);
    const quiere = clave === 'EXT' ? null : /^P\d+$/.test(clave) ? +clave.slice(1) : clave;
    return todas.map((f, i) => [f, i]).filter(([f]) => String(pisoDe(f)) === String(quiere))
      .map(([f, i]) => normalizarUnidad(f, { lineas: inventario.lineas, columnas: cols, extra: extra[i] }));
  }
  return filas.map((f, k) => normalizarUnidad(f, { lineas: inventario?.lineas, columnas: cols, extra: extra[i0 + k] }));
}
function entradaCatalogo(catalogo, modelo) {
  const m = catalogo?.modelos && typeof catalogo.modelos === 'object' ? catalogo.modelos : catalogo;
  return (m && m[modelo]) || null;
}
function medidasUnidad(modelo, entrada, variante, dimUnidad) {
  if (Array.isArray(dimUnidad) && dimUnidad.length === 3 && dimUnidad.every((v) => +v > 0)) return dimUnidad.map(Number);
  const dv = variante && (entrada?.variantes?.[variante]?.dim_m || VARIANTES[modelo]?.[variante]);
  if (dv) return dv.map(Number);
  const dc = entrada?.dim || entrada?.dim_m;
  return medidas(modelo, dc);
}

// ---------------------------------------------------------------- mallas fundidas con tabla de rangos
const _m3 = new THREE.Matrix3();
class Fundida {
  // items: [{ geo, m: Matrix4, n: unidad }]
  constructor(items, material, nombre) {
    let nv = 0;
    for (const it of items) nv += it.geo.attributes.position.count;
    const pos = new Float32Array(nv * 3), nor = new Float32Array(nv * 3), col = new Float32Array(nv * 3);
    this.rangos = [];
    this.porUnidad = new Map();
    let o = 0;
    for (const it of items) {
      const P = it.geo.attributes.position.array, N = it.geo.attributes.normal.array, C = it.geo.attributes.color.array, e = it.m.elements;
      const ne = _m3.getNormalMatrix(it.m).elements, cnt = it.geo.attributes.position.count;
      for (let v = 0; v < cnt; v++) {
        const a = 3 * v, b = 3 * (o + v), x = P[a], y = P[a + 1], z = P[a + 2];
        pos[b] = e[0] * x + e[4] * y + e[8] * z + e[12];
        pos[b + 1] = e[1] * x + e[5] * y + e[9] * z + e[13];
        pos[b + 2] = e[2] * x + e[6] * y + e[10] * z + e[14];
        const nx = N[a], ny = N[a + 1], nz = N[a + 2];
        let qx = ne[0] * nx + ne[3] * ny + ne[6] * nz, qy = ne[1] * nx + ne[4] * ny + ne[7] * nz, qz = ne[2] * nx + ne[5] * ny + ne[8] * nz;
        const l = Math.hypot(qx, qy, qz) || 1;
        nor[b] = qx / l; nor[b + 1] = qy / l; nor[b + 2] = qz / l;
        col[b] = C[a]; col[b + 1] = C[a + 1]; col[b + 2] = C[a + 2];
      }
      const r = { v0: o, v1: o + cnt, n: it.n };
      this.rangos.push(r);
      this.porUnidad.set(it.n.i, r);
      o += cnt;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    g.setAttribute('normal', new THREE.BufferAttribute(nor, 3));
    g.setAttribute('color', new THREE.BufferAttribute(col, 3));
    g.computeBoundingSphere();
    this.geo = g;
    this.pos0 = pos.slice();
    this.col0 = col.slice();
    this.triangulos = nv / 3;
    this.mesh = new THREE.Mesh(g, material);
    this.mesh.name = nombre;
    this.mesh.frustumCulled = false;   // las posiciones cambian con desplazar()
    this.mesh.userData.fundida = this;
    this.sucia = false;
  }
  // unidad del triángulo faceIndex (búsqueda binaria en los rangos)
  unidad(faceIndex) {
    const v = faceIndex * 3, r = this.rangos;
    let a = 0, b = r.length - 1;
    while (a <= b) { const m = (a + b) >> 1; if (v < r[m].v0) b = m - 1; else if (v >= r[m].v1) a = m + 1; else return r[m].n; }
    return null;
  }
  // coloca el rango de la unidad: desplazado (dx, dy en planta) u oculto (colapsado en un punto)
  colocar(n, dx, dy, oculta) {
    const r = this.porUnidad.get(n.i);
    if (!r) return;
    const p = this.geo.attributes.position.array, p0 = this.pos0;
    for (let v = r.v0; v < r.v1; v++) {
      const b = 3 * v;
      if (oculta) { p[b] = p0[3 * r.v0]; p[b + 1] = p0[3 * r.v0 + 1]; p[b + 2] = p0[3 * r.v0 + 2]; }
      else { p[b] = p0[b] + dx; p[b + 1] = p0[b + 1]; p[b + 2] = p0[b + 2] - dy; }
    }
    this.geo.attributes.position.needsUpdate = true;
    this.sucia = true;
  }
  colorear(n, c) {
    const r = this.porUnidad.get(n.i);
    if (!r) return;
    const a = this.geo.attributes.color.array, a0 = this.col0;
    for (let v = r.v0; v < r.v1; v++) {
      const b = 3 * v;
      if (c) { a[b] = c.r; a[b + 1] = c.g; a[b + 2] = c.b; } else { a[b] = a0[b]; a[b + 1] = a0[b + 1]; a[b + 2] = a0[b + 2]; }
    }
    this.geo.attributes.color.needsUpdate = true;
  }
  limpiar() { if (this.sucia) { this.geo.computeBoundingSphere(); this.geo.boundingBox = null; this.sucia = false; } }
  dispose() { this.mesh.removeFromParent(); this.geo.dispose(); }
}

// ---------------------------------------------------------------- capa de equipos de un piso (5.1 a 5.3)
const _M = new THREE.Matrix4(), _cero = new THREE.Matrix4().makeScale(0, 0, 0);
function matrizUnidad(n, nz) {
  _e.set(0, n.rot, 0);
  return new THREE.Matrix4().compose(new THREE.Vector3(n.x, nz + n.z, -n.y), new THREE.Quaternion().setFromEuler(_e), _uno);
}
const MARGEN_RESALTE = 0.03;
const ARISTAS = [[0, 1], [1, 3], [3, 2], [2, 0], [4, 5], [5, 7], [7, 6], [6, 4], [0, 4], [1, 5], [2, 6], [3, 7]];

/** @typedef {{
 *   objeto: THREE.Group,
 *   pick(raycaster: THREE.Raycaster): { unidad: string, punto: THREE.Vector3, distancia: number } | null,
 *   resaltar(ids: string[] | null): void,                                             // null quita el resaltado
 *   colorear(ids: string[] | null, color: THREE.ColorRepresentation | null): void,   // reemplaza (no multiplica) el color; null restaura
 *   fantasma(on: boolean): void,                                                      // muestra u oculta la malla del cierre de brechas
 *   entrarRecinto(id: string | null): void,                                           // arma la malla del recinto actual (objetos pequeños y LOD0)
 *   desplazar(id: string, dx: number, dy: number): void,                              // m en planta, desde la posición de reposo
 *   centro(id: string): THREE.Vector3 | null,
 *   stats(): { llamadas: number, triangulos: number, instancias: number },
 *   unidades(): object[], recinto(): string | null,                                   // extras para QA y el recorrido
 *   dispose(): void
 * }} CapaEquipos */
// Capa de equipos de un piso. unidades: UnidadWeb[] de un piso (filas de torre_inventario.json con op.lineas, u objetos);
// catalogo: catalogo de torre_inventario.json (forma web) o catalogo_equipos.json; nivel: { z } del nivel.
// Opciones: calidad 'baja' | 'media' | 'alta'; minInstancias (≥ 4 unidades → InstancedMesh); ocultarDentro (no dibuja
// montaje 'dentro'); lineas y columnas (para leer filas compactas); maxLlamadas (llamadas de la capa, 30 por omisión, para
// que el piso quepa en 45 con la planta); maxTriangulos (tope de la capa en 'alta').
export function crearCapaEquipos(unidades, catalogo, nivel, {
  calidad = 'baja', minInstancias = 4, ocultarDentro = true, lineas = null, columnas = COLUMNAS, extra = null, desde = 0, maxLlamadas = 30, maxTriangulos = 150000,
} = {}) {
  const mats = materiales(), nz = +(nivel?.z) || 0;
  const objeto = new THREE.Group();
  objeto.name = 'equipos';
  const U = [], porId = new Map();
  (unidades || []).forEach((u, k) => {
    const n = normalizarUnidad(u, { lineas, columnas, extra: extra ? extra[desde + k] : null });
    if (!n || n.id == null || n.modelo == null || n.modelo === '') return;   // línea sin modelo 3D
    exigirModelo(n.modelo);
    const e = entradaCatalogo(catalogo, n.modelo), nom = NOMINAL[n.modelo];
    n.dim = medidasUnidad(n.modelo, e, n.variante, n.dim);
    // fila solar elevada colgada a su altura: los postes bajan hasta el piso del nivel (la caja va del piso al plano)
    if (n.modelo === 'panel_solar_fila' && n.variante === 'elevada' && n.z > n.dim[2]) { n.dim = [n.dim[0], n.dim[1], n.z + n.dim[2]]; n.z = 0; }
    n.familia = e?.f || e?.familia || nom[3];
    n.montaje = n.montaje || e?.mont || e?.montaje || nom[4];
    n.pequena = n.familia === 'insumo' || Math.max(...n.dim) < 0.3;
    n.fantasma = n.estado === 'cierre_brechas_propuesto';
    n.oculta = ocultarDentro && n.montaje === 'dentro';
    n.i = U.length;
    n.m0 = matrizUnidad(n, nz);
    n.off = [0, 0];
    n.color = null;
    n.ocultaPiso = false;
    U.push(n);
    porId.set(String(n.id), n);
  });
  const soloRecinto = (n) => n.pequena && (calidad === 'baja' || n.familia === 'insumo');
  const piso = U.filter((n) => !n.oculta && !n.fantasma && !soloRecinto(n));
  const lodPiso = calidad === 'alta' ? 0 : 1;
  for (const n of piso) n.lod = lodPiso;
  // 'alta': si el LOD0 de todo el piso no cabe, los modelos que más pesan pasan a LOD1 (el recinto actual sigue en LOD0)
  if (calidad === 'alta') {
    const pesos = new Map();
    for (const n of piso) { const k = n.modelo; const t = base(n.modelo, n.dim, n.variante, 0).userData.triangulos; pesos.set(k, (pesos.get(k) || 0) + t); }
    let total = [...pesos.values()].reduce((a, b) => a + b, 0);
    for (const [k, t] of [...pesos].sort((a, b) => b[1] - a[1])) {
      if (total <= maxTriangulos) break;
      let t1 = 0;
      for (const n of piso) if (n.modelo === k) { n.lod = 1; t1 += base(n.modelo, n.dim, n.variante, 1).userData.triangulos; }
      total += t1 - t;
    }
  }
  // grupos por modelo, variante, medidas y LOD
  const grupos = new Map();
  for (const n of piso) {
    const g = base(n.modelo, n.dim, n.variante, n.lod), k = g.userData.clave;
    if (!grupos.has(k)) grupos.set(k, { geo: g, unidades: [] });
    grupos.get(k).unidades.push(n);
  }
  const candidatos = calidad === 'baja' ? [] : [...grupos.values()].filter((g) => g.unidades.length >= minInstancias).sort((a, b) => b.unidades.length - a.unidades.length);
  const instanciados = candidatos.slice(0, Math.max(0, maxLlamadas - 6));
  const enInstancias = new Set(instanciados);
  // InstancedMesh por modelo (una llamada cada una)
  const ims = [];
  for (const g of instanciados) {
    const geo = g.geo.clone();
    geo.userData = {};
    const cnt = g.unidades.length;
    geo.setAttribute('mezcla', new THREE.InstancedBufferAttribute(new Float32Array(cnt * 4), 4));
    const im = new THREE.InstancedMesh(geo, mats.inst, cnt);
    im.name = `equipos:${g.unidades[0].modelo}`;
    // instanceColor en blanco desde el principio (5.3): un setColorAt de otro módulo no obliga a recompilar el programa
    im.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(cnt * 3).fill(1), 3);
    g.unidades.forEach((n, k) => { im.setMatrixAt(k, n.m0); n.inst = { im, k }; });
    im.instanceMatrix.needsUpdate = true;
    im.computeBoundingSphere();
    im.userData.unidades = g.unidades;
    im.userData.triangulos = geo.attributes.position.count / 3;
    ims.push(im);
    objeto.add(im);
  }
  // malla fundida opaca (el resto) y transparente (todos los vidrios del piso)
  const itemsOp = [], itemsVi = [];
  for (const [, g] of grupos) for (const n of g.unidades) {
    if (!enInstancias.has(g)) itemsOp.push({ geo: g.geo, m: n.m0, n });
    if (g.geo.userData.vidrio) itemsVi.push({ geo: g.geo.userData.vidrio, m: n.m0, n });
  }
  const fOp = itemsOp.length ? new Fundida(itemsOp, mats.opaco, 'equipos:fundida') : null;
  const fVi = itemsVi.length ? new Fundida(itemsVi, mats.vidrio, 'equipos:vidrios') : null;
  if (fOp) objeto.add(fOp.mesh);
  if (fVi) { fVi.mesh.renderOrder = 2; objeto.add(fVi.mesh); }
  for (const n of piso) { n.fOp = enInstancias.has(grupos.get(base(n.modelo, n.dim, n.variante, n.lod).userData.clave)) ? null : fOp; n.fVi = fVi; }
  // malla fantasma del cierre de brechas (siempre fundida y transparente; oculta hasta fantasma(true))
  const fantasmas = U.filter((n) => n.fantasma && !n.oculta);
  let fFa = null;
  if (fantasmas.length) {
    const items = [];
    for (const n of fantasmas) {
      const g = base(n.modelo, n.dim, n.variante, calidad === 'alta' ? 0 : 1);
      items.push({ geo: g, m: n.m0, n });
      if (g.userData.vidrio) items.push({ geo: g.userData.vidrio, m: n.m0, n: { ...n, i: -1 - n.i, real: n } });
    }
    fFa = new Fundida(items, mats.fantasma, 'equipos:fantasma');
    fFa.mesh.visible = false;
    fFa.mesh.renderOrder = 3;
    objeto.add(fFa.mesh);
    for (const n of fantasmas) n.fFa = fFa;
  }
  // malla del recinto actual (objetos pequeños e implementos; en 'media', el LOD0 de todo el recinto)
  let sala = { id: null, op: null, vi: null, unidades: [] };
  // caja de resaltado
  const matLinea = new THREE.LineBasicMaterial({ color: 0xe3141b, transparent: true, opacity: 0.95, depthTest: false });
  const lineas3 = new THREE.LineSegments(new THREE.BufferGeometry(), matLinea);
  lineas3.name = 'equipos:resaltado';
  lineas3.renderOrder = 10;
  lineas3.frustumCulled = false;
  lineas3.visible = false;
  objeto.add(lineas3);
  let resaltados = [];
  const quitarTema = onTheme((t) => { matLinea.color.copy(t.accent); });
  try { matLinea.color.copy(tokens().accent); } catch { /* sin documento */ }

  // ---- utilidades internas
  const sucias = new Set();
  let pendiente = false;
  const programar = () => {
    if (pendiente) return;
    pendiente = true;
    queueMicrotask(() => {
      pendiente = false;
      for (const s of sucias) { if (s.isInstancedMesh) s.computeBoundingSphere(); else s.limpiar?.(); }
      sucias.clear();
      if (resaltados.length) dibujarResaltado();
    });
  };
  const matrizActual = (n) => { _M.copy(n.m0); _M.elements[12] += n.off[0]; _M.elements[14] -= n.off[1]; return _M; };
  function colocar(n) {
    if (n.inst) {
      n.inst.im.setMatrixAt(n.inst.k, n.ocultaPiso ? _cero : matrizActual(n));
      n.inst.im.instanceMatrix.needsUpdate = true;
      sucias.add(n.inst.im);
    }
    for (const f of [n.fOp, n.fVi, n.fFa]) if (f) { f.colocar(n, n.off[0], n.off[1], f !== n.fFa && n.ocultaPiso); sucias.add(f); }
    if (n.fFa && n.fFa.porUnidad.has(-1 - n.i)) n.fFa.colocar({ i: -1 - n.i }, n.off[0], n.off[1], false);
    for (const f of [sala.op, sala.vi]) if (f && f.porUnidad.has(n.i)) { f.colocar(n, n.off[0], n.off[1], false); sucias.add(f); }
    programar();
  }
  function pintar(n) {
    if (n.inst) {
      const a = n.inst.im.geometry.attributes.mezcla, c = n.color;
      a.setXYZW(n.inst.k, c ? c.r : 0, c ? c.g : 0, c ? c.b : 0, c ? 1 : 0);
      a.needsUpdate = true;
    }
    for (const f of [n.fOp, n.fVi, sala.op, sala.vi]) if (f) f.colorear(n, n.color);
  }
  function dibujarResaltado() {
    const pts = [];
    for (const n of resaltados) {
      const [W, D, H] = n.dim, m = matrizActual(n), w = W / 2 + MARGEN_RESALTE, d = D / 2 + MARGEN_RESALTE;
      const c = [];
      for (const z of [-MARGEN_RESALTE, H + MARGEN_RESALTE]) for (const y of [-d, d]) for (const x of [-w, w]) c.push(new THREE.Vector3(x, z, -y).applyMatrix4(m));
      for (const [a, b] of ARISTAS) pts.push(c[a].x, c[a].y, c[a].z, c[b].x, c[b].y, c[b].z);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
    lineas3.geometry.dispose();
    lineas3.geometry = g;
    lineas3.visible = pts.length > 0;
  }
  function soltarSala() {
    const vieja = sala;
    sala = { id: null, op: null, vi: null, unidades: [] };
    for (const f of [vieja.op, vieja.vi]) f?.dispose();
    for (const n of vieja.unidades) if (n.ocultaPiso) { n.ocultaPiso = false; colocar(n); }
  }
  const unidadDe = (hit) => {
    const o = hit.object;
    if (o.isInstancedMesh) return o.userData.unidades?.[hit.instanceId] || null;
    const n = o.userData.fundida?.unidad(hit.faceIndex);
    return n ? (n.real || n) : null;
  };

  const capa = {
    objeto,
    pick(raycaster) {
      const objs = [...ims, fOp?.mesh, fVi?.mesh, sala.op?.mesh, sala.vi?.mesh, fFa?.mesh.visible ? fFa.mesh : null].filter((o) => o && o.visible);
      for (const f of [fOp, fVi, sala.op, sala.vi, fFa]) f?.limpiar();
      for (const im of ims) if (sucias.has(im)) im.computeBoundingSphere();
      objeto.updateMatrixWorld(true);
      for (const h of raycaster.intersectObjects(objs, false)) {
        const n = unidadDe(h);
        if (n && !(n.ocultaPiso && h.object !== sala.op?.mesh && h.object !== sala.vi?.mesh)) return { unidad: n.id, punto: h.point.clone(), distancia: h.distance };
      }
      return null;
    },
    resaltar(ids) {
      resaltados = (ids || []).map((id) => porId.get(String(id))).filter(Boolean);
      if (!resaltados.length) { lineas3.visible = false; return; }
      dibujarResaltado();
    },
    colorear(ids, color) {
      const c = color == null ? null : new THREE.Color(color);
      const lista = ids == null ? U : ids.map((id) => porId.get(String(id))).filter(Boolean);
      for (const n of lista) { n.color = c; pintar(n); }
    },
    fantasma(on) { if (fFa) fFa.mesh.visible = !!on; },
    entrarRecinto(id) {
      if (id != null && String(id) === String(sala.id)) return;
      soltarSala();
      if (id == null) return;
      const del = U.filter((n) => String(n.recinto) === String(id) && !n.oculta && !n.fantasma);
      const van = del.filter((n) => soloRecinto(n) || (calidad === 'media' && n.lod === 1) || (calidad === 'alta' && n.lod === 1));
      if (!van.length) { sala.id = id; return; }
      const itemsOp = [], itemsVi = [];
      for (const n of van) {
        const g = base(n.modelo, n.dim, n.variante, 0);
        itemsOp.push({ geo: g, m: matrizActual(n).clone(), n });
        if (g.userData.vidrio) itemsVi.push({ geo: g.userData.vidrio, m: matrizActual(n).clone(), n });
      }
      sala = { id, op: new Fundida(itemsOp, mats.opaco, 'equipos:recinto'), vi: itemsVi.length ? new Fundida(itemsVi, mats.vidrio, 'equipos:recinto-vidrios') : null, unidades: van };
      // las posiciones ya llevan el desplazamiento: la base de la malla del recinto es la posición sin desplazar
      for (const f of [sala.op, sala.vi]) if (f) { for (const n of van) if (f.porUnidad.has(n.i)) { const r = f.porUnidad.get(n.i); for (let v = r.v0; v < r.v1; v++) { f.pos0[3 * v] -= n.off[0]; f.pos0[3 * v + 2] += n.off[1]; } } }
      objeto.add(sala.op.mesh);
      if (sala.vi) { sala.vi.mesh.renderOrder = 2; objeto.add(sala.vi.mesh); }
      for (const n of van) {
        if (n.color) for (const f of [sala.op, sala.vi]) f?.colorear(n, n.color);
        if (piso.includes(n)) { n.ocultaPiso = true; colocar(n); }
      }
    },
    desplazar(id, dx, dy) {
      const n = porId.get(String(id));
      if (!n) return;
      n.off = [+dx || 0, +dy || 0];
      colocar(n);
    },
    centro(id) {
      const n = porId.get(String(id));
      if (!n) return null;
      return new THREE.Vector3(n.x + n.off[0], nz + n.z + n.dim[2] / 2, -(n.y + n.off[1]));
    },
    stats() {
      let llamadas = 0, triangulos = 0, instancias = 0;
      for (const im of ims) if (im.visible && im.count) { llamadas++; triangulos += im.userData.triangulos * im.count; instancias += im.count; }
      for (const f of [fOp, fVi, sala.op, sala.vi, fFa]) if (f && f.mesh.visible && f.mesh.parent && f.triangulos) { llamadas++; triangulos += f.triangulos; }
      if (lineas3.visible) llamadas++;
      return { llamadas, triangulos, instancias };
    },
    // extras para QA y para el recorrido
    unidades() { return U.map((n) => ({ id: n.id, modelo: n.modelo, variante: n.variante, dim: n.dim, recinto: n.recinto, montaje: n.montaje, dibujada: !n.oculta })); },
    recinto() { return sala.id; },
    dispose() {
      soltarSala();
      quitarTema();
      for (const im of ims) { im.removeFromParent(); im.geometry.dispose(); im.dispose?.(); }
      for (const f of [fOp, fVi, fFa]) f?.dispose();
      lineas3.geometry.dispose();
      matLinea.dispose();
      objeto.removeFromParent();
      ims.length = 0;
      U.length = 0;
      porId.clear();
    },
  };
  return capa;
}
