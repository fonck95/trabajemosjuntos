// Simulaciones de la maqueta de la propuesta: lo que el agente (el asistente del panel o uno por MCP) acciona con
// `simular` cuando no hay un modelo del atlas a la vista (visual.js las manda aquí; con un modelo abierto van al atlas).
// El catálogo vive en data/propuesta/simulaciones.json, clave «maqueta», con la misma forma que los controles del atlas
// (id, nombre, tipo accion | si_no | numero | opcion, opciones, ayuda y, si solo valen en unos capítulos, `capitulos`);
// scripts/build_propuesta.py lo revisa contra ACCIONADORES (esta tabla) y lo copia a `tecnica.simulaciones_maqueta` de
// data/propuesta.json. Se accionan igual que los del atlas: uno por uno, en orden, con la misma regla para el valor
// (`validar` de js/escenario.js), y cada uno responde true o el motivo por el que no.
//  · hora: mañana, tarde, atardecer o noche (ambiente.js); queda fija hasta otra hora, hasta que se cambie de paso o de tema.
//  · reproducir_dia: sí recorre el día de la mañana a la noche (DURACION_DIA s, con el sol, el cielo, la luz y las
//    luminarias cambiando cuadro a cuadro); no lo pausa donde va, y otro sí sigue desde ahí.
//  · luces: sí enciende las luminarias de la maqueta (torres LED del estadio, postes, bolardos, LED de las pérgolas) con
//    sus charcos de luz en el piso; no las apaga. Sin pedirlas, siguen la hora (encendidas al atardecer y de noche). Solo
//    en los capítulos que las tienen a la vista (vivienda y urbanismo: `capitulos` en el catálogo).
//  · partido: sí reproduce una jugada en la Cancha de Sóftbol Casabe (lanzamiento, elevado, doble y relevo) que se repite;
//    no la detiene. Solo con la cancha a la vista (en urbanismo, menos la portadilla y el mirador) y en el encuadre en que
//    queda la cámara (`enEncuadre` de visual.js: no en las canchas cubiertas junto al CIC): si el capítulo todavía se
//    arma, se espera hasta ESPERA_MAQUETA_MS; armado, se sabe en el acto (main.js pone el paso apenas llega el módulo,
//    antes de la próxima vuelta del sondeo), así lo que no se puede vuelve como descartado dentro del tope de mando.js.
// Como lo demás que pide el agente, todo vuelve a lo del paso al cambiar de paso (`reiniciar`, que llama visual.alPaso).
// Un cambio de tema (el botón de la persona o `visual` con `tema`) solo devuelve la hora del tema (ambiente.js): las
// luces y el partido siguen como estaban.
// No guarda nada aparte: el estado es el de la escena (la hora, las luces, el partido) y `estado()` lo lee.
import { validar } from '../escenario.js';

export const DURACION_DIA = 24;           // segundos que tarda reproducir_dia de la mañana a la noche
export const ESPERA_MAQUETA_MS = 8000;    // lo que se espera a que el capítulo de la cancha termine de armarse
const SONDEO_MS = 120;

/** El catálogo de controles de la maqueta (`tecnica.simulaciones_maqueta` de propuesta.json) para el capítulo `cid`:
 * copias sin `capitulos` (los que no lo incluyen, fuera). */
export function controlesMaqueta(datos, cid) {
  const todos = datos?.tecnica?.simulaciones_maqueta;
  return (Array.isArray(todos) ? todos : [])
    .filter((c) => c && typeof c.id === 'string' && (!Array.isArray(c.capitulos) || c.capitulos.includes(cid)))
    .map(({ capitulos, ...c }) => JSON.parse(JSON.stringify(c)));
}

/** `enEncuadre(pieza)`: ¿la pieza queda en el encuadre de la cámara? (visual.js; sin ella, basta con que esté visible) */
export function crearSimulacion({ escena, ctx3d, datos, caps, estado, enEncuadre = null }) {
  const amb = escena.ambiente;
  const visible = (o) => { for (let p = o; p; p = p.parent) if (!p.visible) return false; return !!o; };
  const partido = () => ctx3d?.urbanismo?.simulaciones?.partido || null;
  const cap = () => caps?.[estado?.ci] || null;
  // sube con cada reinicio (cambio de paso): lo que todavía espera (el partido mientras carga el capítulo) se abandona
  let turno = 0;
  // ¿se tocó algo desde el último reinicio? (si no, no hay nada que devolver)
  let tocado = false;
  // (scripts/build_propuesta.py lee sus claves, a 4 espacios, hasta el `};` a 2 que la cierra)
  const ACCIONADORES = {
    hora: (v) => (amb?.poner(v) ? true : `«${v}» no es una hora de la maqueta (${(amb?.horas || []).join(', ')})`),
    reproducir_dia: (v) => {
      if (!amb) return 'la maqueta no tiene la hora del día';
      if (!v) { amb.pausar(); return true; }
      // sí: el día en curso sigue; uno pausado (y nada cambió la hora desde entonces) sigue desde ahí; si no, de la mañana
      if (!amb.enCiclo() && !amb.reanudar?.()) amb.ciclo({ desde: amb.horas?.[0] || 'manana', hasta: 'noche', duracion: DURACION_DIA });
      return true;
    },
    luces: (v) => { escena.luces(v); return true; },
    partido: (v) => {
      if (!v) { partido()?.jugar(false); escena.st.invalidate(); return true; }
      // con el capítulo armado, en el acto; si no, cuando se arme (o se abandona si mientras tanto se cambia de paso)
      const jugar = () => {
        const p = partido();
        if (!p) return null;
        if (!visible(p.pieza)) return 'la Cancha de Sóftbol Casabe no está a la vista (en urbanismo, menos la portadilla y el mirador)';
        // a la vista pero lejos del encuadre (las canchas cubiertas junto al CIC, o la cámara llevada a otra obra): nadie
        // vería la jugada, y el partido redibujaría la escena en cada cuadro para nada
        if (enEncuadre && !enEncuadre(p.pieza)) return 'la Cancha de Sóftbol Casabe no queda en el encuadre (vaya al paso softbol o enfóquela)';
        p.jugar(true); escena.st.invalidate();
        return true;
      };
      const ya = jugar();
      if (ya !== null) return ya;
      const mio = turno, t0 = performance.now();
      return new Promise((listo) => {
        const mirar = () => {
          if (mio !== turno) { listo('se cambió de paso antes de accionarlo'); return; }
          const r = jugar();
          if (r !== null) { listo(r); return; }
          if (performance.now() - t0 >= ESPERA_MAQUETA_MS) { listo('la Cancha de Sóftbol Casabe todavía no está armada'); return; }
          setTimeout(mirar, SONDEO_MS);
        };
        setTimeout(mirar, SONDEO_MS);
      });
    },
  };
  const controles = () => controlesMaqueta(datos, cap()?.id);
  return {
    /** Los controles de la maqueta en el capítulo a la vista (copias, sin `capitulos`). */
    controles,
    /** Acciona un control (la forma ya la revisó mando.js; el valor se revisa aquí con la regla del atlas): true, el
     * motivo por el que no, o una promesa de eso (el partido, mientras carga el capítulo). Nunca lanza. */
    accionar(control, valor) {
      try {
        const lista = controles();
        const c = lista.find((x) => x.id === control);
        if (!c) {
          return `«${control}» no es un control de la maqueta en ${cap()?.nombre || 'este capítulo'}; tiene: ${lista.map((x) => x.id).join(', ') || 'ninguno'}`;
        }
        const r = validar(c, valor);
        if (r.error) return r.error;
        const hacer = ACCIONADORES[c.id];
        if (!hacer) return `la maqueta no sabe accionar «${c.nombre}»`;
        tocado = true;
        const res = hacer(r.v);
        return res && typeof res.then === 'function' ? res.catch((e) => String(e?.message || e) || 'no se pudo') : res;
      } catch (e) { return String(e?.message || e) || 'no se pudo'; }
    },
    /** Todo vuelve a lo del paso (al cambiar de paso: visual.alPaso): la hora del tema, las luces según la hora y el
     * partido quieto. Lo que esperaba se abandona. Un `ir` al paso que ya está no la llama: la pantalla en off no se
     * entera de ese `ir` (solo de lo visual que cambió) y las dos pantallas mostrarían otra cosa. */
    reiniciar() {
      turno++;
      if (!tocado) return;
      tocado = false;
      try {
        amb?.poner(null);
        escena.luces?.(null);
        partido()?.jugar(false);
        escena.st?.invalidate(true);
      } catch { /* la escena sin ambiente: nada que devolver */ }
    },
    /** Lo que se ve de la simulación: { hora, dia (reproduciéndose), luces (true | false | null: según la hora), partido } */
    estado() {
      const l = escena.lucesEstado?.() || {};
      return { hora: amb?.hora() || null, dia: !!amb?.enCiclo(), luces: l.encendidas ?? null, partido: !!partido()?.activo() };
    },
  };
}
