# La velocidad del asistente con la presentación

Por qué la sala esperaba tanto cuando se le pedía al asistente explicar algo de la propuesta («explícanos la torre del
hospital»), qué se cambió y qué queda por hacer. El detalle de cómo funciona lo nuevo está en
[`agente.md`, «El plan en flujo»](agente.md#el-plan-en-flujo).

**En corto:** el primer paso narrado pasa de llegar en **un minuto o más** a llegar en **unos 15 a 20 segundos** desde
que la persona envía el mensaje, y el turno termina antes. La respuesta inmediata sigue cubriendo los primeros segundos.

## Dónde se iba el tiempo

Un pedido como «explícanos la torre del hospital», con los modelos de Mnemo, hacía tres rondas en fila con el modelo,
y la sala no veía nada del plan hasta el final de la segunda:

| | Qué pasaba | Qué tenía que esperar la sala |
|---|---|---|
| Ronda 1 | El modelo razona, escribe la línea que anuncia el plan y pide `presentacion` op `guion` | El primer token, el razonamiento y la llamada |
| Herramienta | El guion del capítulo vuelve al modelo (tabla de abajo) | Nada (es local) |
| Ronda 2 | El modelo lee el guion entero, razona con esfuerzo `medium` y escribe el plan completo dentro de la llamada `recorrido` (de 1.500 a 3.000 tokens) | **Todo**: con Mnemo, `mnemo_model_complete` solo manda el texto a trozos; los `tool_use` llegan enteros al final (`apps/api/src/agent-api/catalog/model.ts` en Mnemo) |
| Herramienta | El plan se valida, se guarda y empieza (con la espera de 1,8 s antes del primer paso) | La espera previa |
| Ronda 3 | El modelo escribe «solo una pregunta corta» | No bloquea la sala, pero el turno sigue ocupado y reenvía la conversación entera |

Lo que lee el modelo en la ronda 2, medido sobre el guion de hoy (`guion.capitulo_para_leer`, con los gestos y la nota,
como lo devuelve la op `guion`; tokens estimados a 3,3 caracteres por token):

| Capítulo | Pasos | Caracteres | ≈ Tokens |
|---|---|---|---|
| Portada | 2 | 9.261 | 2.800 |
| Vivienda | 6 | 21.251 | 6.400 |
| Urbanismo | 8 | 24.130 | 7.300 |
| Agroindustria | 5 | 28.737 | 8.700 |
| Salud | 10 | 35.957 | 10.900 |
| Aguas | 5 | 22.555 | 6.800 |
| Saneamiento | 8 | 34.549 | 10.500 |
| TIC | 7 | 21.046 | 6.400 |
| Hoja de ruta | 1 | 10.637 | 3.200 |

Y el esquema de la herramienta `presentacion` pesa unos 14.100 caracteres (≈ 4.300 tokens): va en cada ronda.

Las cuatro causas, de la que más pesa a la que menos:

1. **El plan no llega por partes.** Va dentro de una llamada a herramienta, y Mnemo no reenvía los trozos de una
   llamada (sus adaptadores sí los reciben del proveedor: `tool_use_delta` en `llm/anthropic.adapter.ts` y
   `llm/openai.adapter.ts`, pero `model.ts` solo manda los `text_delta`). Así que la sala espera el plan entero.
2. **Razonar antes de una salida larga y estructurada.** Con el esfuerzo `medium`, el modelo piensa antes de escribir
   el plan: miles de tokens de razonamiento que no se ven, antes que los del plan.
3. **Tres rondas en fila**, cada una con su primer token y reenviando la conversación entera.
4. **El guion se queda en la conversación.** Cada capítulo explicado agrega de 6.000 a 11.000 tokens que viajan en
   todas las rondas siguientes: cada respuesta posterior arranca más lento (y cuesta más).

Una estimación de la línea de tiempo de antes, con supuestos razonables para un modelo grande (primer token en 3 a 4 s,
unos 55 tokens de salida por segundo, de 1.500 a 3.000 tokens de razonamiento en la ronda 2): de **65 a 95 s** hasta
el primer paso narrado. No se pudo medir contra Mnemo de verdad desde aquí (sin una conexión ni créditos), así que son
estimaciones: el registro de producción (`agente_uso` guarda los tokens de cada ronda) permite confirmarlas.

## Lo que cambió: el plan en flujo

La idea: **que la sala empiece a ver y a oír el plan con su primer paso, mientras el resto se escribe**, y aprovechar
que Mnemo sí manda el TEXTO a trozos.

1. El modelo del asistente ya no pide el guion ni escribe el plan: llama `presentacion` op `plan` con el capítulo y un
   encargo corto («la torre: dónde va, cómo está hoy, qué se construye y cómo resiste un sismo»). Son unas decenas de
   tokens, y el guion no entra a la conversación.
2. El panel le pide la redacción al mismo proveedor en una petición aparte (`app/agente/redactor.py`): sin
   herramientas y sin razonar, con las instrucciones y el guion del capítulo en el `system` (el mismo texto para el
   mismo capítulo, así Mnemo lo marca como cacheable y la próxima vez lo lee de la caché del proveedor). El plan llega
   como texto en **JSON Lines**: una línea por paso.
3. Cada línea que se cierra se compone y se valida igual que antes y se publica en el acto: el primer paso abre el
   plan en la pantalla y en la tarjeta del chat, y cada uno de los siguientes lo hace crecer. El reproductor del
   navegador agrega los pasos nuevos sin cortar lo que suena y, si alcanza al redactor (no pasa: ver abajo), espera.
4. Cuando el plan está entero, el turno termina: no hay ronda final, y la tarjeta trae las sugerencias para seguir.

Medido con el código real (el redactor, el lector, la composición, el guardado y la publicación) y un modelo simulado a
2,5 s del primer token y 55 tokens por segundo, con un plan de 8 pasos de la torre del hospital: **el primer paso sale
a los 4 o 5 s de empezar la redacción**, cada paso siguiente aproximadamente un segundo después, y el plan queda entero
a los 13 s. Su narración dura unos 108 s: la sala nunca alcanza al redactor.

La línea de tiempo nueva, con los mismos supuestos: ronda 1 (primer token, un razonamiento corto y la llamada `plan`)
de 8 a 12 s, la redacción hasta el primer paso de 4 a 5 s y la espera previa de 1,8 s: **de 14 a 19 s** hasta el
primer paso narrado, contra 65 a 95 s antes.

Otros efectos:

- **El turno se libera antes**: termina cuando el plan está escrito (sin la ronda 3), así la persona puede volver a
  escribir antes y la conexión con Mnemo (que atiende pocas llamadas a la vez para todo el panel) queda libre.
- **Las respuestas siguientes son más rápidas y baratas**: la conversación ya no carga el guion de cada capítulo.
- **Nada se relaja**: las frases pasan las mismas reglas de lo que se proyecta (sin costos, sin datos de personas, sin
  «@» ni números largos); lo que no vale se omite con un aviso. Si la redacción falla antes del primer paso, el modelo
  arma el plan como antes (`guion` y `recorrido`); si la persona lo detiene mientras se escribe, la redacción se
  corta y no se gasta en lo que nadie va a oír.

Lo prueban `tests/test_plan_en_flujo.py` (el lector, el plan que crece con un modelo que escribe a trozos, lo que se
omite, la detención a mitad, los fallos, el tope de pasos, el avance que cuenta menos pasos, el turno que termina con el
plan y, con Node, el reproductor que espera, el puente y la tarjeta que crece).

## Lo que queda por hacer

Ordenado por lo que le ganaría a la espera, con dónde tocar:

1. **Que Mnemo mande por partes también las llamadas a herramientas** (en el repositorio de Mnemo,
   `apps/api/src/agent-api/catalog/model.ts`): reenviar `tool_use_start` y `tool_use_delta`, que sus adaptadores ya
   reciben, como avisos de avance con un `_meta` propio, solo si la app lo pide (para no cambiarles nada a las demás).
   Así cualquier app conectada vería antes qué herramienta va a usar el modelo, y un plan escrito con `recorrido`
   (por un agente externo por MCP, o el de varios capítulos) también podría empezar antes.
2. **Un modelo rápido para el redactor** (`ligero` de la cuenta de Mnemo, o `claude-sonnet-5-5` en modo directo): el
   plan sale de un guion y un encargo, y un modelo rápido escribe de 2 a 3 veces más tokens por segundo. Hace falta que
   `ProveedorMnemo.generar` acepte el modelo de una petición; conviene compararlo con unos cuantos planes reales antes
   de dejarlo por omisión.
3. **Calentar antes de que pregunten**: al abrir la vista Presentación (o al empezar a dictar una pregunta), una
   petición mínima con el `system` del redactor para el capítulo abierto deja el guion en la caché del proveedor (y la
   conexión con Mnemo abierta). Ahorra 1 o 2 s del primer token del primer plan.
4. **La voz clonada del primer paso**: el servidor puede pedirle a Mnemo el audio de la primera frase en cuanto publica
   el primer paso (hoy el navegador la precarga en la espera de 1,8 s, que casi siempre alcanza).
5. **Planes que ya se dijeron**: los pedidos se repiten en una campaña («preséntanos Salud»). Guardar el plan de cada
   capítulo para un encargo igual (y el audio de sus frases) lo haría instantáneo la segunda vez.
6. **Las llamadas a la vez con Mnemo**: Mnemo atiende pocas llamadas al modelo a la vez por conexión, compartidas por
   todo el panel; con varias personas usando el asistente en un evento, una ronda puede esperar su turno (el panel
   reintenta de 2 a 5 s). Si se vuelve un cuello de botella, el tope se revisa del lado de Mnemo.
