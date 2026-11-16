// Simulaciones de la maqueta de la propuesta: lo que el agente (y la persona) reproduce con `simular` cuando no hay un
// modelo del atlas a la vista. Los controles tienen la misma forma que los del atlas (data/propuesta/simulaciones.json,
// clave «maqueta»: id, nombre, tipo accion | si_no | numero | opcion, opciones, ayuda y, si solo valen en unos
// capítulos, `capitulos`) y se accionan igual: uno por uno, en orden, y cada uno responde true o el motivo por el que no.
//  · hora: mañana, tarde, atardecer o noche (ambiente.js); queda fija hasta otra hora o hasta que se cambie el tema.
//  · reproducir_dia: sí recorre el día de la mañana a la noche (24 s, con el sol, el cielo, la luz y las luminarias
//    cambiando cuadro a cuadro); no lo pausa donde va.
//  · luces: sí enciende las luminarias de la maqueta (torres LED del estadio, postes, bolardos, LED de las pérgolas) con
//    sus charcos de luz en el piso; no las apaga. Sin pedirlas, siguen la hora (encendidas al atardecer y de noche).
//  · partido: sí reproduce una jugada en la Cancha de Sóftbol Casabe (lanzamiento, elevado, doble y relevo) que se repite;
//    no la detiene. Solo con la cancha a la vista.
// No guarda nada: el estado es el de la escena (la hora, las luces, el partido) y `estado()` lo lee.
export const DURACION_DIA = 24;   // segundos que tarda reproducir_dia de la mañana a la noche

/** El catálogo de controles de la maqueta (de propuesta.json) para el capítulo `cid` (los de `capitulos` que no lo incluyen, fuera). */
export function controlesMaqueta(datos, cid) {
  const todos = datos?.simulaciones?.maqueta || datos?.tecnica?.simulaciones_maqueta || [];
  return (Array.isArray(todos) ? todos : []).filter((c) => c && typeof c.id === 'string' && (!Array.isArray(c.capitulos) || c.capitulos.includes(cid)));
}

export function crearSimulacion({ escena, ctx3d }) {
  const amb = escena.ambiente;
  const visible = (o) => { for (let p = o; p; p = p.parent) if (!p.visible) return false; return !!o; };
  const partido = () => ctx3d.urbanismo?.simulaciones?.partido || null;
  const ACCIONES = {
    hora: (v) => (amb?.poner(v) ? true : `«${v}» no es una hora de la maqueta (mañana, tarde, atardecer o noche)`),
    reproducir_dia: (v) => {
      if (!amb) return 'la maqueta no tiene ambiente';
      if (v) amb.ciclo({ desde: 'manana', hasta: 'noche', duracion: DURACION_DIA }); else amb.pausar();
      return true;
    },
    luces: (v) => { escena.luces(!!v); return true; },
    partido: (v) => {
      const p = partido();
      if (!p) return 'la Cancha de Sóftbol Casabe todavía no está armada';
      if (v && !visible(p.pieza)) return 'la Cancha de Sóftbol Casabe no está a la vista (está en urbanismo)';
      p.jugar(!!v); escena.st.invalidate();
      return true;
    },
  };
  return {
    /** ¿Este control es de la maqueta? */
    tiene: (control) => Object.prototype.hasOwnProperty.call(ACCIONES, control),
    /** Acciona un control (la forma del valor ya la revisó mando.js): true o el motivo por el que no. Nunca lanza. */
    accionar(control, valor) {
      try { return ACCIONES[control] ? ACCIONES[control](valor) : `«${control}» no es un control de la maqueta`; } catch (e) { return String(e?.message || e) || 'no se pudo'; }
    },
    /** Lo que se ve de la simulación: { hora, dia (reproduciéndose), luces (true | false | null: según la hora), partido } */
    estado() {
      const l = escena.lucesEstado?.() || {};
      return { hora: amb?.hora() || null, dia: !!amb?.enCiclo(), luces: l.encendidas ?? null, partido: !!partido()?.activo() };
    },
  };
}
