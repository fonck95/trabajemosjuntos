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
