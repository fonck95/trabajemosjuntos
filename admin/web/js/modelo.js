// Catálogos y etiquetas de la ficha ampliada, iguales a los de app/modelo.py, y ayudas puras para la interfaz.
// Módulo puro, sin DOM ni importaciones: tests/test_contrato.py lo carga con Node.

// catalogos:inicio — copia exacta de CATALOGOS_WEB (app/modelo.py): tests/test_contrato.py las compara
export const CATALOGOS = {
  "SEXOS": {
    "F": "Mujer",
    "M": "Hombre",
    "N": "Prefiere no decir"
  },
  "TIPOS_DOCUMENTO": {
    "CC": "Cédula de ciudadanía",
    "TI": "Tarjeta de identidad",
    "CE": "Cédula de extranjería",
    "PPT": "Permiso por protección temporal",
    "PEP": "Permiso especial de permanencia",
    "PA": "Pasaporte"
  },
  "NIVELES": [
    "Ninguno",
    "Primaria",
    "Secundaria",
    "Técnico",
    "Tecnólogo",
    "Universitario",
    "Posgrado"
  ],
  "ESTADOS_CIVILES": [
    "Soltero(a)",
    "Casado(a)",
    "Unión libre",
    "Separado(a) o divorciado(a)",
    "Viudo(a)"
  ],
  "SITUACIONES_LABORALES": [
    "Empleado(a)",
    "Independiente",
    "Agricultor(a) o pescador(a)",
    "Desempleado(a)",
    "Estudiante",
    "Oficios del hogar",
    "Pensionado(a)",
    "Otra"
  ],
  "TENENCIAS": [
    "Propia",
    "Arriendo",
    "Familiar",
    "Posesión",
    "Otra"
  ],
  "REGIMENES_SALUD": [
    "Contributivo",
    "Subsidiado",
    "Especial",
    "Ninguno"
  ],
  "RANGOS_EDAD": [
    "<18",
    "18-24",
    "25-34",
    "35-44",
    "45-54",
    "55-64",
    "65+"
  ],
  "SENSIBLES": {
    "etnia": {
      "etiqueta": "Pertenencia étnica",
      "valores": [
        "Indígena",
        "Negro o afrocolombiano",
        "Raizal",
        "Palenquero",
        "Rrom",
        "Ninguno",
        "Prefiere no decir"
      ]
    },
    "discapacidad": {
      "etiqueta": "Discapacidad",
      "valores": [
        "Física",
        "Visual",
        "Auditiva",
        "Intelectual",
        "Psicosocial",
        "Múltiple",
        "Ninguna",
        "Prefiere no decir"
      ]
    },
    "victima": {
      "etiqueta": "Víctima del conflicto",
      "valores": [
        "Sí",
        "No",
        "Prefiere no decir"
      ]
    }
  },
  "NOMBRES_ROL": {
    "admin": "Administrador",
    "coordinador": "Coordinador",
    "planillero": "Planillero",
    "consultor": "Consultor"
  },
  "ESTADOS_AUTORIZACION": {
    "si": "Sí autoriza",
    "no": "No autoriza",
    "revocada": "Revocada",
    "pendiente": "Pendiente"
  },
  "MEDIOS_AUTORIZACION": {
    "escrito": "Escrito",
    "verbal_presencial": "Verbal presencial",
    "verbal_telefono": "Verbal por teléfono",
    "mensaje": "Mensaje (WhatsApp o SMS)",
    "formulario": "Formulario",
    "panel": "Registrado en el panel",
    "migrado": "Dato anterior",
    "declarado_planilla": "Declarado en planilla",
    "fusion": "Unión de fichas"
  },
  "MEDIOS_POR_ROL": {
    "planillero": [
      "escrito",
      "verbal_presencial",
      "formulario"
    ],
    "consultor": [
      "verbal_telefono",
      "mensaje"
    ]
  },
  "CANALES_AUTORIZACION": {
    "llamada": "Llamada",
    "whatsapp": "WhatsApp",
    "sms": "SMS",
    "correo": "Correo",
    "visita": "Visita",
    "grupos": "Listas o grupos de difusión"
  },
  "CANALES_IMPLICITOS": [
    "llamada",
    "whatsapp",
    "sms"
  ],
  "CANALES": {
    "llamada": "Llamada",
    "whatsapp": "WhatsApp",
    "sms": "SMS",
    "visita": "Visita",
    "reunion": "Reunión",
    "correo": "Correo",
    "otro": "Otro"
  },
  "RESULTADOS": {
    "contesto": {
      "etiqueta": "Contestó",
      "etiqueta_visita": "Atendió",
      "efectivo": true
    },
    "no_contesto": {
      "etiqueta": "No contestó",
      "etiqueta_visita": "No estaba",
      "efectivo": false
    },
    "buzon": {
      "etiqueta": "Buzón o mensaje dejado",
      "etiqueta_visita": "Buzón o mensaje dejado",
      "efectivo": false
    },
    "volver_llamar": {
      "etiqueta": "Pidió volver a llamar",
      "etiqueta_visita": "Pidió volver a visitar",
      "efectivo": true
    },
    "numero_equivocado": {
      "etiqueta": "Número equivocado",
      "etiqueta_visita": "Número equivocado",
      "efectivo": false
    },
    "numero_inexistente": {
      "etiqueta": "Número no existe",
      "etiqueta_visita": "Número no existe",
      "efectivo": false
    },
    "actualizo_datos": {
      "etiqueta": "Actualizó datos",
      "etiqueta_visita": "Actualizó datos",
      "efectivo": true
    },
    "pidio_informacion": {
      "etiqueta": "Pidió información",
      "etiqueta_visita": "Pidió información",
      "efectivo": true
    },
    "solicitud_derechos": {
      "etiqueta": "Pidió consultar, corregir o borrar sus datos",
      "etiqueta_visita": "Pidió consultar, corregir o borrar sus datos",
      "efectivo": true
    },
    "no_contactar": {
      "etiqueta": "Pidió no ser contactado",
      "etiqueta_visita": "Rechazó",
      "efectivo": true
    },
    "no_vive_aqui": {
      "etiqueta": "No vive aquí",
      "etiqueta_visita": "No vive aquí",
      "efectivo": false
    },
    "fallecio": {
      "etiqueta": "Falleció",
      "etiqueta_visita": "Falleció",
      "efectivo": false
    }
  },
  "SIN_EXITO": [
    "no_contesto",
    "buzon"
  ],
  "FRANJAS": {
    "manana": "Mañana",
    "tarde": "Tarde",
    "noche": "Noche"
  },
  "ESTADOS_ABORDAJE": {
    "sin_abordar": "Sin abordar",
    "intentado": "Intentado",
    "contactado": "Contactado",
    "no_contactar": "No contactar"
  },
  "SITUACIONES": {
    "activa": "Activa",
    "fallecida": "Fallecida",
    "no_reside": "Ya no vive en Yondó"
  },
  "MOTIVOS_ACTUALIZACION": {
    "pedido_consultor": "Pedido del consultor",
    "no_contesta": "No contesta",
    "sin_telefono_valido": "Sin teléfono válido",
    "direccion": "No vive en la dirección",
    "alta_consultor": "Alta pedida por un consultor",
    "administrador": "Pedido del administrador"
  },
  "CAMPOS_NO_DISPONIBLE": [
    "cedula",
    "telefono",
    "mesa",
    "puesto",
    "edad",
    "sexo"
  ],
  "MOTIVOS_NO_DISPONIBLE": {
    "no_la_dio": "No la dio",
    "no_tiene": "No lo tiene",
    "no_sabe": "No sabe"
  },
  "ESTADOS_TELEFONO": {
    "sin_verificar": "Sin verificar",
    "confirmado": "Confirmado",
    "no_usa": "Ya no lo usa",
    "equivocado": "Equivocado",
    "inexistente": "No existe",
    "retirado": "Retirado"
  },
  "USABLES": [
    "confirmado",
    "sin_verificar"
  ],
  "TIPOS_TELEFONO": {
    "celular": "Celular",
    "fijo": "Fijo"
  },
  "ESTADOS_VOTACION": {
    "verificado": "Verificado",
    "sin_verificar": "Sin verificar",
    "por_confirmar": "Por confirmar"
  },
  "DONDE_VOTA": {
    "yondo": "En Yondó",
    "otro_municipio": "En otro municipio",
    "no_inscrito": "No está inscrito"
  },
  "ETIQUETAS_CAMPOS": {
    "cedula": "Cédula",
    "telefono": "Teléfono",
    "sexo": "Sexo",
    "edad": "Edad",
    "direccion": "Dirección",
    "lugar": "Barrio o vereda",
    "ubicacion": "Ubicación",
    "puesto": "Puesto de votación",
    "mesa": "Mesa",
    "autorizacion": "Autorización",
    "correo": "Correo",
    "estado_civil": "Estado civil",
    "nivel_educativo": "Nivel educativo",
    "situacion_laboral": "Situación laboral",
    "ocupacion": "Ocupación",
    "personas_hogar": "Personas en el hogar",
    "jefe_hogar": "Jefe de hogar",
    "tenencia_vivienda": "Tenencia de la vivienda",
    "estrato": "Estrato",
    "regimen_salud": "Régimen de salud"
  },
  "CAMPOS_FALTAN": [
    "cedula",
    "telefono",
    "sexo",
    "edad",
    "lugar",
    "puesto",
    "mesa",
    "direccion",
    "autorizacion"
  ]
};
// catalogos:fin

export const { SEXOS, TIPOS_DOCUMENTO, NIVELES, ESTADOS_CIVILES, SITUACIONES_LABORALES, TENENCIAS, REGIMENES_SALUD,
  RANGOS_EDAD, SENSIBLES, NOMBRES_ROL, ESTADOS_AUTORIZACION, MEDIOS_AUTORIZACION, MEDIOS_POR_ROL,
  CANALES_AUTORIZACION, CANALES_IMPLICITOS, CANALES, RESULTADOS, SIN_EXITO, FRANJAS, ESTADOS_ABORDAJE, SITUACIONES,
  MOTIVOS_ACTUALIZACION, CAMPOS_NO_DISPONIBLE, MOTIVOS_NO_DISPONIBLE, ESTADOS_TELEFONO, USABLES, TIPOS_TELEFONO,
  ESTADOS_VOTACION, DONDE_VOTA, ETIQUETAS_CAMPOS, CAMPOS_FALTAN } = CATALOGOS;

/** Número para el enlace tel: (solo dígitos); a un fijo de 7 dígitos le antepone el indicativo 604. */
export const marcable = (n) => {
  const d = String(n ?? '').replace(/\D/g, '');
  return /^\d{7}$/.test(d) ? '604' + d : d;
};

/** ¿El número se puede usar para llamar o escribir? (estado sin verificar o confirmado y sin «no contactar») */
export const esUsable = (t) => USABLES.includes(t?.estado ?? 'sin_verificar') && t?.no_contactar !== true;

/** Etiqueta de un resultado según el canal: «Atendió» en una visita, «Contestó» en una llamada. */
export function etiquetaResultado(resultado, canal) {
  const r = RESULTADOS[resultado];
  if (!r) return resultado;
  return canal === 'visita' || canal === 'reunion' ? r.etiqueta_visita : r.etiqueta;
}

// ───────── Ayudas de la interfaz de campo (G4). Puras: sin DOM; la hora solo si se pasa ─────────

const MESES_CORTOS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
const ZONA_MS = 5 * 3600 * 1000; // Colombia: UTC−5, sin horario de verano

/** Fecha de negocio «AAAA-MM-DD» en hora de Colombia (0.2.11). */
export const hoyColombia = (ahora = new Date()) => new Date(ahora.getTime() - ZONA_MS).toISOString().slice(0, 10);

/** Años cumplidos el día `hoy` por quien nació en `nacimiento` (las dos «AAAA-MM-DD»), como `edad_efectiva` de
 * app/modelo.py con fecha de nacimiento. null si la fecha no existe (1985-02-30) o es posterior a hoy. */
export function edadDesde(nacimiento, hoy = hoyColombia()) {
  const n = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(nacimiento ?? '').trim()), h = /^(\d{4})-(\d{2})-(\d{2})$/.exec(hoy);
  if (!n || !h) return null;
  const [a, m, d] = n.slice(1).map(Number), [ha, hm, hd] = h.slice(1).map(Number);
  const f = new Date(Date.UTC(a, m - 1, d));
  if (a < 1000 || f.getUTCFullYear() !== a || f.getUTCMonth() !== m - 1 || f.getUTCDate() !== d) return null;
  const e = ha - a - (hm < m || (hm === m && hd < d) ? 1 : 0);
  return e >= 0 ? e : null;
}

/** «3 nov» de una fecha «AAAA-MM-DD…». */
export function diaCorto(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || '');
  return m ? `${Number(m[3])} ${MESES_CORTOS[Number(m[2]) - 1]}` : '';
}

/** Celular colombiano: 10 dígitos que empiezan por 3. WhatsApp y SMS solo se ofrecen para estos. */
export const esCelular = (n) => /^3\d{9}$/.test(String(n ?? '').replace(/\D/g, ''));

/** Los números usables de una ficha, en su orden (el primero es el principal). Su índice es el que va al servidor. */
export const telefonosUsables = (p) => (Array.isArray(p?.telefonos) ? p.telefonos.filter(esUsable)
  : [p?.telefono, p?.telefono2].filter(Boolean).map((numero) => ({ numero, estado: 'sin_verificar' })));

/** «···2233»: los últimos dígitos. */
export const enmascarar = (n, ult = 4) => {
  const d = String(n ?? '').replace(/\s/g, '');
  return d ? '···' + d.slice(-ult) : '';
};

/**
 * Texto y color del chip de abordaje (4.6): «Sin abordar» (ámbar), «Intentado ×2» (azul),
 * «Contactado · 3 nov · llamada · Luis» (verde) o «No contactar» (rojo).
 */
export function textoAbordaje(ab) {
  const estado = ab?.estado || 'sin_abordar';
  if (estado === 'no_contactar') return { clase: 'rojo', texto: ESTADOS_ABORDAJE.no_contactar };
  if (estado === 'contactado') {
    const partes = [ESTADOS_ABORDAJE.contactado, diaCorto(ab.ultimo_fecha), CANALES[ab.ultimo_canal]?.toLowerCase(), ab.ultimo_usuario];
    return { clase: 'verde', texto: partes.filter(Boolean).join(' · ') };
  }
  if (estado === 'intentado') return { clase: 'azul', texto: `${ESTADOS_ABORDAJE.intentado} ×${ab.n || 1}` };
  return { clase: 'ambar', texto: ESTADOS_ABORDAJE.sin_abordar };
}

/** La autorización de una ficha, venga como objeto `autorizacion` o en los campos `consentimiento_*`. */
export function autorizacionDe(p) {
  const a = p?.autorizacion && typeof p.autorizacion === 'object' && !Array.isArray(p.autorizacion) ? p.autorizacion : {};
  return {
    estado: a.estado ?? p?.consentimiento ?? 'pendiente',
    medio: a.medio ?? p?.consentimiento_medio ?? null,
    canales: a.canales ?? p?.consentimiento_canales ?? [],
    habilitado: a.contacto_habilitado ?? p?.contacto_habilitado ?? null,
    fecha: a.fecha ?? p?.consentimiento_fecha ?? null,
  };
}

const CANALES_TELEFONO = ['llamada', 'whatsapp', 'sms'];
/**
 * Canales que ofrece el diálogo de acercamiento (7.5): los que permiten la autorización y el rol. La fila de la cola
 * ya trae `canales_permitidos` y manda. El servidor decide de todos modos (409 `canal`).
 */
export function canalesPermitidos(p, rol, { conPendientes = false } = {}) {
  if (rol === 'planillero') return ['visita'];
  const aut = autorizacionDe(p);
  let tel = [];
  if (Array.isArray(p?.canales_permitidos)) tel = p.canales_permitidos.filter((c) => CANALES_TELEFONO.includes(c));
  else if (aut.estado === 'si') tel = CANALES_TELEFONO.filter((c) => (aut.canales || []).includes(c));
  else if (aut.estado === 'pendiente' && (conPendientes || rol !== 'consultor')) tel = [...CANALES_TELEFONO];
  const usables = telefonosUsables(p);
  if (!usables.length) tel = [];
  if (!usables.some((t) => esCelular(t.numero))) tel = tel.filter((c) => c === 'llamada');
  if (rol === 'consultor') return tel;
  // Administrador y coordinador: además la visita, el correo (si lo autorizó) y «otro»
  const otros = ['visita'];
  if (p?.correo && aut.estado !== 'no' && (aut.estado !== 'si' || (aut.canales || []).includes('correo'))) otros.push('correo');
  return [...tel, ...otros, 'otro'];
}

/** Parámetros de Habitantes para un rango de edad: «25-34» → {edad_min: 25, edad_max: 34}. */
export function rangoAParams(r) {
  if (r === '<18') return { edad_max: 17 };
  const mas = /^(\d+)\+$/.exec(r || '');
  if (mas) return { edad_min: Number(mas[1]) };
  const m = /^(\d+)-(\d+)$/.exec(r || '');
  return m ? { edad_min: Number(m[1]), edad_max: Number(m[2]) } : {};
}

/** ¿`ahora` cae fuera de `horario` ({semana: [ini, fin], sabado: […], domingo: false | […]}) en hora de Colombia? */
export function fueraDeHorario(horario, ahora = new Date()) {
  if (!horario) return false;
  const co = new Date(ahora.getTime() - ZONA_MS);
  const dia = co.getUTCDay();
  const franja = dia === 0 ? horario.domingo : dia === 6 ? horario.sabado : horario.semana;
  if (!Array.isArray(franja) || franja.length < 2) return true;
  const hhmm = `${String(co.getUTCHours()).padStart(2, '0')}:${String(co.getUTCMinutes()).padStart(2, '0')}`;
  return hhmm < franja[0] || hhmm >= franja[1];
}

/** Enlace de WhatsApp a un celular colombiano, con un texto opcional. */
export const enlaceWhatsapp = (n, texto = '') => {
  const d = String(n ?? '').replace(/\D/g, '');
  return `https://wa.me/57${d.slice(-10)}${texto ? '?text=' + encodeURIComponent(texto) : ''}`;
};

/** Resultados que se guardan con un toque (7.5). Los de número solo existen si hubo un número. */
export const RESULTADOS_RAPIDOS = ['no_contesto', 'buzon', 'numero_equivocado', 'numero_inexistente'];
export const RESULTADOS_DE_NUMERO = ['numero_equivocado', 'numero_inexistente'];
/** Grupos de la rejilla de resultados. */
export const GRUPOS_RESULTADO = [
  ['Sin contacto', ['no_contesto', 'buzon', 'numero_equivocado', 'numero_inexistente', 'no_vive_aqui', 'fallecio']],
  ['Hubo contacto', ['contesto', 'volver_llamar', 'actualizo_datos', 'pidio_informacion', 'solicitud_derechos', 'no_contactar']],
];

/** Paso «Más datos» de «Completar» (7.3): [campo, etiqueta, opciones]; cada opción es un chip de un toque. */
export const MAS_DATOS = [
  ['estado_civil', 'Estado civil', ESTADOS_CIVILES],
  ['nivel_educativo', 'Nivel educativo', NIVELES],
  ['situacion_laboral', 'Situación laboral', SITUACIONES_LABORALES],
  ['estrato', 'Estrato', ['0', '1', '2', '3', '4', '5', '6']],
  ['regimen_salud', 'Régimen de salud', REGIMENES_SALUD],
  ['jefe_hogar', 'Jefe de hogar', ['Sí', 'No']],
  ['tenencia_vivienda', 'Tenencia de la vivienda', TENENCIAS],
  ['personas_hogar', 'Personas en el hogar', ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10']],
];
