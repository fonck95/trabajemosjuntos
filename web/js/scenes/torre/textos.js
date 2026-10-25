// Textos para ciudadanos en la vista de la torre (equipo D; contrato 13.6 de la especificación de integración).
// Los datos citan archivos, carpetas y claves internas del proyecto («(programa.json)», «docs/06», «normas.json →
// parametros_diseno.areas_minimas_m2») que el lector no puede abrir: limpio() quita las citas entre paréntesis, nombra
// el resto en palabras, borra los tramos «→ clave» y traduce los niveles de verificación de los textos normativos.
// torre.js, el recorrido (C), el simulador (D) y el contraste (E) importan de aquí limpio, esc y escH: nadie copia
// estas reglas. Toda cadena que llegue a la web desde los datos pasa por esc() (texto) o escH() (atributos y enlaces).

// escapa lo mínimo para insertar texto en HTML (sin limpiar: para URL y atributos)
export const escH = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

// archivo citado (nombre sin extensión) → cómo se nombra en la web
export const FUENTES = {
  programa: 'el programa', normas: 'la revisión de normas', dotacion: 'la dotación', presupuesto: 'el presupuesto', laboratorio: 'el laboratorio',
  financiacion: 'la financiación', proyectos: 'los proyectos', microrred: 'la microrred', presupuesto_microrred: 'el presupuesto de la microrred',
  bienestar_anciano: 'el levantamiento del Centro Vida', hospital: 'el levantamiento del hospital',
  // dotación, habilitación y plantas (equipo B)
  inventario_dotacion: 'el inventario de dotación', torre_inventario: 'el inventario de dotación', catalogo_equipos: 'el catálogo de equipos',
  implementos: 'el listado de implementos', exigencias_3100: 'las exigencias de la Res. 3100', habilitacion: 'la matriz de cumplimiento en dotación e infraestructura',
  torre_habilitacion: 'la matriz de cumplimiento en dotación e infraestructura', normas_4725_1732: 'la revisión del Decreto 4725',
  reglas_ubicacion: 'las reglas de ubicación de la dotación', reglas_exigencias: 'las reglas de las exigencias', reglas_planta: 'las reglas de las plantas',
  torre_hospital: 'la especificación de la torre', torre_hospital_plantas: 'las plantas de la torre', torre_plantas: 'las plantas de la torre',
  torre_hospital_trazado: 'el trazado de las plantas', apu: 'los análisis de precios unitarios', mapa_codigo: 'el estudio',
  // proyecto tipo (equipo E)
  proyecto_tipo: 'la revisión de proyectos tipo', proyecto_tipo_contraste: 'el contraste con el proyecto tipo', torre_contraste: 'el contraste con el proyecto tipo',
  // simulación sísmica (equipo A)
  amenaza: 'el estudio de amenaza sísmica', sismo_amenaza: 'el estudio de amenaza sísmica', torre_hospital_estructura: 'el modelo estructural de la torre',
  sismo_torre_estructura: 'el modelo estructural de la torre', validacion_opensees: 'la validación con OpenSees',
  hospital2028: 'el estudio del hospital',
};
export const fuente = (k) => FUENTES[k] || (/^res3100/.test(k) ? 'la revisión de la Res. 3100' : 'el estudio');

// niveles de verificación de los textos normativos (4.2): ninguno se presenta como «verificado»
export const VERIFICACION = {
  literal_compilacion: 'texto de una compilación oficial; cotejar con el Diario Oficial',
  fragmento_normograma: 'texto de una compilación oficial; cotejar con el Diario Oficial',
  literal_confirmado: 'texto de una compilación oficial; cotejar con el Diario Oficial',
  contenido_compilacion: 'contenido de una compilación oficial; redacción por confirmar',
  contenido_confirmado_redaccion_por_confirmar: 'contenido de una compilación oficial; redacción por confirmar',
  fuente_secundaria: 'según guía secundaria; por confirmar',
  fragmento_fuente_secundaria: 'según guía secundaria; por confirmar',
  solo_fuente_secundaria: 'según guía secundaria; por confirmar',
  parafrasis_por_confirmar: 'paráfrasis; por confirmar',
  por_confirmar: 'por confirmar',
};
export const verificacion = (v) => VERIFICACION[v] || limpio(v);
const NIV = new RegExp(String.raw`'?\b(${Object.keys(VERIFICACION).sort((a, b) => b.length - a.length).join('|')})\b'?`, 'g');

// cita de archivo: «data/edificios/hospital.json», «fuentes_investigacion/res3100_apoyo_diagnostico.json#servicios[0]»
const JS = String.raw`(?:[\w-]+\/)*([\w*-]+)\.(?:json|csv)(?:#[\w.\[\]-]*)?`;
const JSN = String.raw`(?:[\w-]+\/)*[\w*-]+\.(?:json|csv)(?:#[\w.\[\]-]*)?`;
// clave interna después de una flecha: «→ parametros_diseno.areas_minimas_m2», «→ escenarios», «→ equipos[3]»
const CLAVE = String.raw`[A-Za-z0-9]+(?:[_.][A-Za-z0-9]+)*(?:\[\d+\])*`;

// las URL quedan intactas (los enlaces van aparte, con escH); solo se limpia el texto entre ellas
export const limpio = (s) => String(s ?? '').split(/(https?:\/\/[^\s)]+)/).map((t, i) => (i % 2 ? t : limpiar(t, i === 0))).join('');
const limpiar = (s, inicio) => s
  .replace(new RegExp(String.raw`(${JSN})(?:\s*→\s*${CLAVE})+`, 'g'), '$1')                   // «normas.json → clave» → «normas.json»
  .replace(/\s*→\s*[a-z0-9]+(?:_[a-z0-9]+)+(?:[.[][\w.\]]*)?/g, '')                          // tramos «→ clave_interna» sueltos
  .replace(/\bbess_hospital\b/g, 'baterías del hospital')
  .replace(/\s*Verificación V\d+(?: \([^)]*\))?:.*?\.(?=\s|$)/g, '')                          // notas internas de revisión
  .replace(new RegExp(String.raw`\s*\((?:ver\s+)?${JS}(?:,\s*[^()]*)?\)`, 'gi'), '')       // «(programa.json)», «(programa.json, demoliciones)»
  .replace(new RegExp(String.raw`[;,]\s*${JS}(?:,\s*[^();]*)?(?=\))`, 'g'), '')             // «(…; programa.json, implantación)», «(…, normas.json)»
  .replace(new RegExp(String.raw`\(${JS}:\s*`, 'g'), '(')                                     // «(normas.json: se adopta…)»
  .replace(new RegExp(String.raw`^${JS}:\s*(.)`), (m, k, c) => (inicio ? c.toUpperCase() : c))  // «programa.json: 2 × 5 m³ en cubierta»
  .replace(new RegExp(String.raw`^${JS},\s*`), (m, k) => (inicio ? `Según ${fuente(k)}, ` : `${fuente(k)}, `))
  .replace(new RegExp(JS, 'g'), (m, k) => fuente(k))
  .replace(/\s*\((?:ver\s+)?docs\/[\w/.-]+\)/gi, '').replace(/\s*Ver docs\/[\w/.-]+\.?/g, '')
  .replace(/docs\/0?6\b/g, 'el estudio de financiación').replace(/docs\/[\w/.-]+/g, 'el estudio')
  .replace(/\s*\((?:ver\s+)?scripts\/[\w/.-]+\)/gi, '').replace(/(?<![\w/.])(?:scripts|web\/js)\/[\w/.-]+/g, 'los cálculos del atlas')   // guiones del repositorio
  .replace(/(?<![\w/.])(?:web\/)?data\/(?:[\w.*-]+\/?|\{[^}]*\})*/g, 'los datos del atlas').replace(/\bfuentes_investigacion\/?/g, 'las investigaciones de base')
  .replace(NIV, (m, k) => VERIFICACION[k])
  .replace(/,?\s*\b[a-z]+(?:_[a-z0-9]+)+(?:\.[a-z0-9_]+)+(?:\[\d+\])*/g, '')                // rutas de claves «escalamiento_a_torre.orden…»
  .replace(/'([a-z]+(?:_[a-z]+)+)'/g, (m, k) => `«${k.replace(/_/g, ' ')}»`)
  .replace(/\bde el\b/g, 'del').replace(/\ba el\b/g, 'al')
  .replace(/\bm2\b/g, 'm²').replace(/\bm3\b/g, 'm³')
  .replace(/\b(\d+)\.(\d{1,2}) veces\b/g, '$1,$2 veces');                                     // «1.04 veces» → «1,04 veces»

export const esc = (s) => escH(limpio(s));   // para textos; los enlaces van con escH
