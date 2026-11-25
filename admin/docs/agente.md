# El asistente del panel

El panel tiene un **asistente**: un agente de IA que, una vez se ingresa, aparece en un botón flotante. Se le escribe
en español y responde con datos de la base: busca personas, resume los indicadores, hace [análisis
avanzados](#análisis-avanzados) con su gráfico en el chat (y un diagnóstico de qué priorizar), revisa los pendientes
y las colas de [calidad de datos](#registros-de-cada-persona-y-calidad-de-datos), lee las [planillas físicas que se
fotografían](#planillas-físicas-por-foto) y las coteja con la base, prepara reuniones, muestra cosas en el mapa, abre
vistas y fichas, presenta y explica la propuesta 2028–2031 (en la vista **Presentación** o en un proyector) y propone
cambios (una nota, un acercamiento, una ficha nueva, la carga de una planilla fotografiada, la unión de dos fichas
duplicadas…) que la persona aprueba antes de que se guarden. Un agente externo (Claude Desktop u otro cliente MCP)
también puede trabajar con los datos del panel con una [clave de datos](#agentes-por-mcp-con-datos): lo que propone
cambiar, la persona lo aprueba en el panel.

**Los modelos los pone Mnemo.** El administrador conecta el panel con su cuenta de Mnemo en **Ajustes → Asistente**:
inicia sesión en Mnemo, da permiso y vuelve. Nadie copia claves. Desde ahí el asistente usa los modelos y los créditos
de esa cuenta y, con la misma conexión, trabaja también en el espacio del administrador en Mnemo: documentos,
calendario, formularios y memoria (ver [Conectar con Mnemo](#conectar-con-mnemo)). Sin Mnemo, una clave de Anthropic
en el servidor sirve de [modo directo](#modo-directo-sin-mnemo).

Tres ideas lo resumen:

- **Usa la sesión de quien conversa.** Cada herramienta llama por dentro a la misma API del panel, con la cookie y el
  CSRF de esa persona: ve y hace exactamente lo que su rol permite en el panel, ni más ni menos.
- **Nada se escribe sin aprobación.** Toda escritura (en la base o en Mnemo) aparece como una tarjeta con los valores
  exactos y solo se ejecuta si la persona pulsa **Aprobar**.
- **Al modelo le llega lo mínimo.** Cédulas y teléfonos enmascarados, nunca datos sensibles (salud, etnia,
  discapacidad, víctima), los [datos políticos](#datos-políticos) solo como el panel se los muestra a cada rol y si el
  administrador no los apaga, y nada de quien no autorizó el tratamiento (ver
  [Privacidad](#privacidad-y-protección-de-datos-ley-1581-de-2012)). Con una
  excepción documentada: la foto de una planilla física la ve entera el modelo, pero solo en una llamada de lectura
  aparte, sin herramientas ni conversación; al asistente le llega lo leído, enmascarado ([La excepción de las fotos de
  planillas](#la-excepción-de-las-fotos-de-planillas)).

## Qué puede hacer

Lo que se le ofrece depende del rol. Planilleros y consultores **no** lo tienen hasta que el administrador los habilita
en **Ajustes → Asistente**.

| Rol | Qué le puede pedir |
|---|---|
| Administrador y coordinador | Indicadores del tablero (también de una zona o con filtros), [análisis avanzados](#análisis-avanzados) con su gráfico (tablas, series, embudo, cobertura por puesto y ritmo a una meta, barrios desatendidos, el equipo, horas que más contestan, intentos, calidad de captura, cambios entre periodos, efecto de las reuniones) y el **diagnóstico** de qué priorizar, buscar y ver habitantes, los [datos políticos](#datos-políticos) que ven en el panel (tipo de persona, «Liderado por», listas, la lista de líderes con sus conteos; filtros y análisis por tipo, líder o lista), si el administrador no los apaga, fichas parecidas, el historial de acercamientos y de autorizaciones de una persona, reuniones (listar, ver, crear, editar, agregar y quitar asistentes), pendientes y colas de calidad (coincidencias, conflictos de cédula, situaciones, solicitudes de los titulares sin decir de quién son, importaciones, lugares escritos sin reconocer), los puestos con el censo, su trabajo y el de cada usuario, el equipo (lo que hizo cada usuario, alertas, asignación y el avance de cada zona, sin sesiones ni IP), barrios y veredas, catálogos, el mapa, la presentación de la propuesta y cualquier vista. Lee las [planillas físicas por foto](#planillas-físicas-por-foto) y las coteja con la base. Propone crear y editar fichas, notas, acercamientos, autorizaciones, ubicación y teléfonos (y su estado), cargar planillas fotografiadas, unir o separar fichas duplicadas, resolver conflictos de cédula, reportar y confirmar situaciones, registrar y actualizar solicitudes de los titulares, reportar duplicados, marcar datos no disponibles, pedir la actualización de una ficha, anular acercamientos, agregar alias a un barrio o vereda, marcar o quitar el tipo de persona y asignar un líder. Con Mnemo, el administrador (y el coordinador, si se le permite): documentos, calendario, formularios y memoria |
| Planillero | Buscar y ver habitantes (en su zona y con su presupuesto diario), parecidas, el historial de acercamientos de una persona, sus reuniones y las abiertas al equipo, su trabajo y sus pendientes, los puestos, barrios y veredas, catálogos, la presentación de la propuesta y sus vistas. Propone crear y editar fichas, notas, acercamientos (visita o reunión), autorizaciones, ubicación, teléfonos (y su estado), reuniones (y editar las suyas), asistentes (agregar y quitar), reportar una situación o un duplicado, registrar una solicitud del titular, marcar un dato como no disponible, marcar la ficha como atendida y anular sus acercamientos de las últimas 24 horas. Con los [datos políticos](#datos-políticos) encendidos, ve el tipo y el «Liderado por» en la ficha de las personas de su zona o que registró y propone marcar un tipo o asignar un líder (solo suma: nunca quita ni filtra). Nunca las planillas por foto (son de administrador y coordinador). Sin tablero, análisis, mapa ni equipo |
| Consultor | Su cola de llamadas y su trabajo, buscar por nombre (3 letras o más) o por un número completo de 10 dígitos, ver las fichas de las personas que tiene en curso, su historial de acercamientos, los puestos (código y nombre) y la presentación de la propuesta. Propone acercamientos (llamada, WhatsApp, SMS…), autorizaciones, teléfonos y su estado (equivocado, WhatsApp, no contactar…), reportar una situación, registrar una solicitud del titular, marcar como no disponibles la cédula, el puesto o la mesa y anular sus acercamientos de las últimas 24 horas. Nada político |

Nunca, para nadie: exportar o descargar, suprimir datos (el derecho de supresión), crear usuarios o cambiar claves y
roles, cambiar ajustes, confirmar las autorizaciones declaradas en planilla, ver los datos sensibles (salud, etnia,
discapacidad, víctima, huellas) o un dato político que el panel no le muestra a su rol, deducir o adivinar la
afiliación política de alguien, ni ver la cédula o el teléfono completos. Para eso está el panel: el asistente lo
explica y dice dónde hacerlo.

Dos «nunca» cambiaron, solo para el administrador y el coordinador y siempre con la tarjeta y su aprobación:

- **Importar**, únicamente **planillas físicas fotografiadas** ([Planillas físicas por
  foto](#planillas-físicas-por-foto)): primero la vista previa fiel del importador (`cotejar_planilla`) y después la
  carga con la tarjeta que muestra cada fila entera. Los Excel se siguen subiendo en **Importar y exportar**.
- **Unir fichas**, únicamente **duplicados de la cola de Coincidencias**, con la vista previa de la ficha unida en la
  tarjeta (`resolver_coincidencias`). Unir no se deshace desde el asistente; dos cédulas distintas nunca se unen.

Las herramientas del panel (`app/agente/herramientas/`):

| Herramienta | Tipo | Quién | Qué hace |
|---|---|---|---|
| `buscar_personas`, `ver_persona` | lectura | todos | Habitantes (por nombre, por la cédula o el teléfono completos o con filtros) y fichas, con la proyección de cada rol: con los [datos políticos](#datos-políticos), también el tipo, el «Liderado por», las listas y las fuentes que el panel le muestra a ese rol, y A y K filtran por tipo, líder, lista y las bases de cédulas y general |
| `personas_parecidas` | lectura | A, K, P | Posibles duplicados por nombre, cédula o teléfono (a quien no autorizó, solo por el nombre) |
| `crear_persona`, `editar_persona`, `agregar_nota`, `ubicar_persona` | escritura | A, K, P | Ficha nueva (avisa si hay parecidas), cambios con «antes → después», notas y ubicación |
| `registrar_acercamiento`, `registrar_autorizacion`, `agregar_telefono` | escritura | todos | Lo que la persona del equipo dicta: nunca inventa evidencias, autorizaciones ni números. Un «sí» va siempre con su medio y sus canales, y una solicitud de derechos con su tipo (y su plazo) |
| `lideres` | lectura | A, K, P (con los [datos políticos](#datos-políticos) encendidos) | Sin `q` (A y K): los líderes y concejales con su tipo, cuántas personas trajo cada uno (`traidas`), cuántas son votantes y cuántas trae también otro líder, y cuántas personas tienen varios líderes, de a 30 (hasta 100), sin contar a quienes no autorizaron; los líderes que no autorizaron no salen. Con `q` (también P): el buscador del «Liderado por», por nombre (3 letras o más) o la cédula completa |
| `marcar_tipo` | escritura | A, K, P (con los datos políticos encendidos) | Marca concejal, líder o votante (`PATCH /api/personas/{id}`); A y K también quitan un tipo. P solo suma y solo en las personas de su zona o que registró. Nunca a quien no autorizó; marca solo lo que le dicen |
| `asignar_lider` | escritura | A, K, P (con los datos políticos encendidos) | Asigna el líder o concejal que trajo a una persona (`POST /api/personas/{id}/lideres`, hasta 10 por persona), con el id que da `lideres`. P solo en su zona; quitar un líder es de A y K, en el panel. Nunca a quien no autorizó ni un líder que no autorizó |
| `indicadores`, `equipo` | lectura | A, K | Tablero compacto (sin sensibles y sin contar a quien no autorizó; con los datos políticos, también los líderes, las personas en las dos bases, las 40 listas con más personas y el conteo por fuente) y el equipo: lo que hizo y administró cada usuario, alertas, asignación y el avance de cada zona (también sin contar a quien no autorizó) |
| `listar_reuniones`, `ver_reunion` | lectura | A, K, P | Agenda y asistentes |
| `crear_reunion`, `agregar_asistente` | escritura | A, K, P | Reunión nueva (con hora de inicio y de fin) y asistentes |
| `pendientes`, `mi_trabajo`, `buscar_lugar`, `catalogos` | lectura | todos | Insignias y colas, listas de trabajo, nomenclátor de barrios y veredas, catálogos no sensibles |
| `mapa` | interfaz | A, K | Vuela a un lugar, filtra, cambia capas y mapa base, resalta personas, abre una zona |
| `abrir_vista` | interfaz | todos | Abre una vista o una ficha que su rol puede ver |
| `presentacion` | interfaz | todos | La [presentación técnica](#la-presentación-técnica) de la propuesta 2028–2031 (lo que se construye, sin costos): el [plan en flujo](#el-plan-en-flujo) (`plan`: con el capítulo y un encargo, el panel escribe el plan y la sala lo oye desde su primer paso), el índice (capítulos, pasos, componentes e inmersiones), ir a un capítulo y paso (le vuelve lo que muestra ese paso para explicarlo: textos, cifras, especificaciones, referentes, sitio, plazos, metas y el modelo del atlas que muestra, todo entero y sin plata: nada se acorta, y un paso pesa a lo sumo 12 KB), siguiente y anterior, una o dos frases en pantalla, de hasta 220 caracteres (`explicar`, `quitar_explicacion`), los paneles sin cambiar de paso (`vista`: el panel de texto o solo la maqueta 3D, el índice, las fichas técnicas), lo que se ve sin cambiar de paso (`visual`: la cámara con su encuadre, su rumbo, su elevación y su acercamiento, a qué apunta y cómo viaja, la obra enfocada, su ficha técnica, hoy o con el proyecto, las piezas de la maqueta que se muestran, se ocultan o se aíslan y las partes que se les quitan, un modelo 3D del atlas y el tema, con la ficha de lo que muestra), que llene la ventana (`pantalla_completa`), qué muestra la [pantalla en off](#pantalla-en-off-y-agentes-por-mcp) (`estado`) y el [plan guiado](#el-plan-guiado-recorridos-narrados): `guion` (todo un capítulo para preparar la explicación, con las piezas de su maqueta), `recorrido` (el plan: de 1 a 12 pasos, cada uno con lo que se dice y lo que ocurre en pantalla mientras se dice, en una sola llamada) y `control_recorrido` (pausar, seguir, saltar, repetir, volver a empezar, detener); y `automatica` (enciende o apaga la [presentación automática](#presentación-automática): la pantalla en off recorre sola toda la presentación, muy resumida). Solo guarda esa pantalla: ningún dato de personas. Un agente externo la usa igual [por MCP](#pantalla-en-off-y-agentes-por-mcp) |

Los registros de cada persona (`fichas.py`) y las colas de **Calidad de datos** (`calidad.py`; ver [Registros de cada
persona y calidad de datos](#registros-de-cada-persona-y-calidad-de-datos)):

| Herramienta | Tipo | Quién | Qué hace |
|---|---|---|---|
| `historial_acercamientos` | lectura | todos | Todos los acercamientos de una persona, de a 50: fecha, canal, resultado, si fue efectivo, la nota enmascarada, si está anulado o salió de una reunión, el id, si es propio y si se puede anular. Nunca el teléfono marcado, lo dictado ni quién lo registró |
| `autorizaciones_de` | lectura | A, K | Los eventos de autorización de una persona: estado, medio, canales, fecha, si tiene evidencia y, en los de planilla, si están confirmados. Nunca las categorías sensibles autorizadas, la fila de la planilla, la evidencia escrita ni la nota |
| `reportar_situacion` | escritura | todos | Fallecida o ya no vive en Yondó: sale de las colas sin borrar nada, por confirmar |
| `registrar_solicitud` | escritura | todos | Una solicitud del titular (consulta, corrección, supresión, revocatoria, otro, registro) con su plazo legal. También de quien no autorizó: ejercer sus derechos no es tratar sus datos. Una igual del mismo usuario en el último día no se repite |
| `reportar_duplicado` | escritura | A, K, P | Dos fichas que parecen la misma persona, a la cola de Coincidencias (no une) |
| `marcar_no_disponible` | escritura | todos | Un dato que la persona no tiene, no sabe o no dio (C: solo cédula, puesto y mesa), o quitar la marca |
| `pedir_actualizacion` | escritura | A, K, P | Marcar la ficha como atendida; A y K también piden que la actualicen |
| `estado_telefono` | escritura | todos | Estado (confirmado, equivocado, inexistente, ya no lo usa), WhatsApp, no contactar, nota y principal (no C) de un número de la ficha, nombrado por su índice o su posición: el modelo nunca escribe el número |
| `anular_acercamiento` | escritura | todos | El autor durante 24 horas, A y K siempre; el de una asistencia se anula quitando al asistente |
| `editar_reunion` | escritura | A, K, P | Título, fecha, horas, lugar, sitio, tema, descripción y compromisos (P, solo las suyas; abrirla al equipo, A y K). Si alguien la cambió entre la tarjeta y la aprobación, no escribe |
| `quitar_asistente` | escritura | A, K, P | Quita a una persona de una reunión y anula el acercamiento de su asistencia |
| `coincidencias` | lectura | A, K | Grupos de posibles duplicados: nivel, motivos, fichas minimizadas, pares con las **claves** de sus señales (nunca su texto) y la ficha que se conservaría |
| `resolver_coincidencias` | escritura | A, K | Unir (con `conservar` y `excluir`) o separar hasta 5 grupos, con la vista previa de la ficha unida en la tarjeta (cédula, teléfonos y correo enmascarados). Si el grupo cambió entre la tarjeta y la aprobación, no une. Plazo de 160 s |
| `conflictos_cedula` | lectura | A, K | Conflictos de cédula con su motivo, la cédula enmascarada, las fichas, lo mínimo de la fila, la fuente (trámites, planilla y, con los datos políticos, las bases de cédulas y general; si no, «otra base») y las decisiones posibles |
| `resolver_conflicto` | escritura | A, K | Aplicar, descartar, corregir (con la cédula que dictan, nunca armada con las enmascaradas) o reportar como duplicado |
| `situaciones` | lectura | A, K | Personas reportadas como fallecidas o que se fueron, por confirmar (sin quien no autorizó) |
| `confirmar_situacion` | escritura | A, K | Confirmar o revertir una situación reportada |
| `solicitudes` | lectura | A, K | Tipo, canal, estado, plazo y vencimiento, con totales; nunca de quién es ni lo que pidió |
| `actualizar_solicitud` | escritura | A, K | Estado y respuesta de una solicitud: la tarjeta muestra de quién es; al modelo no le llega. Marcarla resuelta no suprime nada |
| `importaciones` | lectura | A, K | Las últimas importaciones de trámites y planillas con sus conteos y las autorizaciones por confirmar; las de la base con cédula y la general, con los datos políticos, con su tipo, archivo y conteos (líderes asignados y sin resolver, tipos marcados, registros por fuente); si no, sin archivo ni conteos |
| `puestos` | lectura | todos | Catálogo de puestos de la elección vigente con mesas y habilitados (C: solo código y nombre) |
| `lugares_sin_reconocer` | lectura | A, K | Lugares escritos sin barrio o vereda reconocido, con cuántas personas y hasta 3 lugares parecidos |
| `agregar_alias_lugar` | escritura | A, K | Un alias para un barrio o vereda (`POST /api/lugares/{lid}/alias`): reubica solo a las personas con ese lugar escrito. Plazo de 160 s |

Las [planillas físicas por foto](#planillas-físicas-por-foto) (`planillas.py`) y los [análisis
avanzados](#análisis-avanzados) (`analisis.py`):

| Herramienta | Tipo | Quién | Qué hace |
|---|---|---|---|
| `planillas` | lectura | A, K (`importar`, con su rol en `agente_planillas.roles`) | La bandeja de fotos de planillas: id, estado (leyendo, leida, fallida, rechazada, cargada), quién la subió y cuándo, filas, dudosas, pendientes y el error. Sin datos de personas. Ven toda la bandeja. Como mucho 40 |
| `leer_planilla` | lectura | A, K (`importar`, con su rol) | Lo que el panel leyó de 1 a 4 fotos, **enmascarado**: el encabezado y cada fila con la cédula y los teléfonos con sus últimos dígitos (ninguno de un menor), la edad en vez de la fecha de nacimiento, si hay observaciones (no su texto), lo dudoso y lo ilegible; de quien dijo «No autoriza», solo nombre y barrio. Espera hasta ~55 s a las que se están leyendo. Plazo de 80 s |
| `cotejar_planilla` | lectura | A, K (`importar`) | La vista previa fiel del importador, sin escribir: por fila, qué pasaría (ficha nueva, completa una que existe, igual, revoca su autorización, conflicto de cédula, por revisar, no autorizó, otra elección, sin nombre, ya cargada, no se carga), la ficha encontrada (minimizada) y lo que llenaría o es distinto (enmascarado). De las filas en «no», ninguna ficha. Plazo de 120 s |
| `cargar_planilla` | escritura | A, K (`importar`) | La carga con el importador real, como una planilla de campo: hasta 30 personas por tarjeta, cada una en una línea con sus valores enteros; `folio`, `capturado_por`, `correcciones` (nunca la autorización, el medio, los canales, «mayor de 18» ni las observaciones), `reemplazar` (sexo, edad, dirección o puesto; nunca la cédula) y `reunion_id`. Las filas en «no» van solas en otra tarjeta. Plazo de 170 s |
| `analizar` | lectura | A, K (`analitica.ver`) | Un análisis agregado (tabla, serie, embudo, cobertura, ritmo, brechas, equipo, calidad, anomalías, cohortes, franjas, intentos, captura, comparar, efecto de las reuniones) con su gráfico en el chat; con los datos políticos, también por tipo, líder o lista. Nunca personas (salvo los líderes con 10 o más personas que nombra una tabla por `lider`, que van en `Resultado.personas`; por MCP, solo con `lectura`): las cifras pequeñas salen «<5» |
| `diagnostico` | lectura | A, K (`analitica.ver`) | Los hallazgos de la base ordenados por urgencia, cada uno con su evidencia, por qué importa, la acción y, si se puede, el enlace a Habitantes con los filtros exactos. Plazo de 120 s |

A = administrador, K = coordinador, P = planillero, C = consultor. Las de Mnemo (`mnemo_…`) se describen [más
abajo](#conectar-con-mnemo). Qué sale por MCP lo dice [Agentes por MCP con datos](#agentes-por-mcp-con-datos): las
de planillas, `registrar_autorizacion`, `equipo`, `mi_trabajo` y las de interfaz, nunca.

De quien no autorizó el tratamiento, las herramientas solo dan quién es y su barrio o vereda. Una búsqueda con otros
filtros (o con un orden que no sea por nombre) o por un número, los indicadores, las cifras del mapa, los
asistentes de una reunión (la lista y los conteos), Mi trabajo, lo pendiente del trabajo, lo que cada usuario del
equipo hizo con las personas y las cifras del avance por zona no lo traen ni lo cuentan: cada filtro que casa, o la
resta de dos conteos, sería un dato suyo. Para saber quiénes no autorizaron, el asistente busca solo por esa
autorización (con su barrio o vereda, o su nombre, si hace falta). En el panel salen todos, como siempre. Las
herramientas de datos, calidad, planillas y análisis siguen la misma regla: su historial de acercamientos y sus
autorizaciones no se entregan (ni a A y K); un grupo de duplicados o un conflicto que la incluye sale solo con quién es
y se resuelve en el panel; las situaciones, los lugares sin reconocer y los análisis no la cuentan (registrar, llamar o
reunirse con ella no cambia ninguna cifra); de una fila de planilla que dice «No autoriza», o de alguien que ya está en
«no», llega solo su nombre y su barrio, y el cotejo no da su ficha. Sí se registra una solicitud sobre sus datos:
ejercer sus derechos no es tratarlos. Fuera de eso, de registrar su autorización y de cargar el «no» de una planilla
(que solo guarda la negativa), el asistente no escribe en su ficha. Tampoco aparece en nada político: un líder que no
autorizó no se nombra en el «Liderado por» de nadie, no sale en la lista de líderes ni en su buscador, no sirve de
filtro y no se asigna.

La búsqueda del asistente no es la de Habitantes: compara las palabras solo con el nombre, y un número solo entero (la
cédula o el teléfono completos, también escritos por grupos o con el +57). No busca por dirección ni por correo, ni
por una parte de un número: cada búsqueda que casa o no sería una respuesta sobre un dato que el modelo no ve (la
dirección o el correo de quien no autorizó, los dígitos enmascarados de una cédula o un teléfono), y unas cuantas
bastarían para reconstruirlo. Si unas palabras no encuentran a nadie, el resultado dice que solo se buscó en el nombre
(y cómo buscar por barrio o vereda): la dirección o el sitio escrito se buscan en Habitantes. El orden tampoco dice
nada: la búsqueda rápida va por nombre (no primero las fichas más completas) y el orden «lugar», que dentro del lugar
ordena por la dirección, deja fuera a quien no autorizó. Las parecidas, por lo mismo, traen a quien no autorizó solo
por un nombre muy parecido, nunca por la cédula o el teléfono; también las del alta (`crear_persona`): si una
coincide solo por un número, no se muestra, la ficha no se crea y el asistente pide revisarla en Habitantes antes de
proponer crearla igual. Una cédula que ya es de quien no autorizó tampoco dice de quién es. Lo pendiente da el tipo y
el plazo de las solicitudes de los titulares, no de quién es cada una. La API lo hace con `estricta=1` y los conteos
sin quien no autorizó con `tratables=1` (en reuniones, Mi trabajo, las insignias y Usuarios): la interfaz no los manda
y sigue igual.

### Datos políticos

El tipo de persona (concejal, líder, votante), el «Liderado por» (el líder o concejal que trajo a cada persona), las
listas de origen, la lista de líderes con sus conteos, los filtros por ellos y las bases políticas de importación (la
base con cédula y la base general) le llegan al asistente y a los agentes por MCP **exactamente como el panel se los
muestra a cada rol** (`app/acceso.py`, `proyeccion.tipo_visible`; `app/agente/minimizar.py` solo deja pasar lo que la
API ya le dio a ese rol):

| Rol | Qué recibe |
|---|---|
| Administrador y coordinador | Todo: el tipo, el «Liderado por» (id, nombre y tipo de cada líder; nunca quién lo asignó), las listas, las fuentes («cedulas», «general») y la cédula de origen; en la ficha de un líder, cuántas trajo (`traidas`). Filtran por `tipo` (concejal, lider, votante, sin_tipo), `lider_id`, `varios_lideres`, `sin_lider`, `lista` y las fuentes `cedulas`, `general` y `ambas` (en `buscar_personas`, `indicadores`, `mapa`, `abrir_vista` y `analizar`), ven la lista de líderes con sus conteos y marcan o quitan un tipo y asignan líderes |
| Planillero | El tipo y el «Liderado por» solo en la ficha de las personas de su zona o que registró, nunca en filas, búsquedas ni parecidas (sus `editables` traen los tipos que aún puede sumar). Solo suma: marca un tipo y asigna un líder (lo busca por nombre o cédula completa, sin conteos); nunca quita ni filtra por datos políticos |
| Consultor | Nada |

Lo encienden y lo apagan dos casillas de **Ajustes → Datos políticos en el asistente y por MCP**
(`agente_politicos.asistente` y `agente_politicos.mcp`, las dos encendidas por defecto; ver [Ajustes](#ajustes)).
Apagado para una vía, todo queda como antes por esa vía: nada político en filas, fichas, indicadores, calidad ni
analítica; los filtros políticos responden 403 `permiso` («Los datos políticos … no están habilitados en Ajustes para
esta vía (el asistente del panel o los agentes por MCP): el administrador los habilita») y `lideres`, `marcar_tipo` y
`asignar_lider` no se ofrecen. Por MCP manda `agente_politicos.mcp`, también al aprobar en Mi cuenta una propuesta
hecha por MCP.

Lo que no cambia: de quien no autorizó, solo la forma `no_autorizo` y nada político suyo (ver arriba), y los conteos no
lo cuentan; los datos sensibles (salud, `regimen_salud`, etnia, discapacidad, víctima, huellas, campos y etiquetas
sensibles) nunca van; la analítica por tipo, líder o lista usa la misma supresión de celdas chicas ([Análisis
avanzados](#análisis-avanzados)); toda escritura pasa por su tarjeta. Toda persona cuyos datos políticos llegan al
modelo (también los líderes que nombra un «Liderado por», la lista de líderes o una tabla por líder) va en
`Resultado.personas`: la conversación queda con datos de personas (no se proyecta ni suena con la voz clonada) y se
borra si alguna se suprime o deja de autorizar.

Las instrucciones del asistente (`sistema.py`) traen la sección **Datos políticos** solo si la conversación tiene esas
herramientas, con lo que ve el rol: son afiliación política, un dato sensible (Ley 1581 de 2012, art. 5); se usan solo
para la tarea pedida; nunca se infiere ni se adivina la afiliación de nadie; nunca se usan para excluir, presionar ni
condicionar a nadie (el contacto depende de la autorización); nunca van a la presentación ni a la pantalla en off ni se
dicen para una sala; y un tipo o un líder se marcan solo con lo que dicta la persona del equipo, nunca en una nota u
otro campo de texto. Sin esas herramientas, dicen que no le llegan.

## Cómo se usa

- **El botón.** Abajo a la derecha (en el mapa, junto a sus controles), para quien tiene el asistente habilitado y la
  cuenta al día (clave cambiada y compromiso aceptado). Abre el panel del asistente; en el celular ocupa la pantalla
  bajo la barra superior. **Escape** lo cierra. Si el asistente no tiene un modelo que usar (Mnemo sin conectar, la
  conexión caída o sin permiso para usar sus modelos), el administrador ve el botón con lo que falta y un enlace a
  **Ajustes → Asistente**; los demás no ven nada. Si eso pasa mientras alguien conversa, el panel se lo dice en vez de
  cerrarse. Al conectar o desconectar Mnemo, o al guardar los ajustes del asistente, el asistente se entera en el acto,
  sin recargar la página; en otra pestaña que decía que no tenía modelo, al abrirlo.
- **Escribir.** Se escribe y se pulsa **Enviar**; **Detener** corta la respuesta en curso. La respuesta llega por
  partes: una marca por cada herramienta con su resultado («12 personas», «Nota guardada») y el texto (con Mnemo, lo
  que llega por partes es un adelanto: al terminar cada ronda queda el texto final). En modo directo, además, notas de
  progreso en gris (qué está haciendo). Una conversación vacía muestra sugerencias para el rol (`politica.SUGERENCIAS`:
  al administrador y al coordinador, el diagnóstico de la semana, los barrios desatendidos, los líderes con más
  votantes sin contactar, las planillas por cargar, los duplicados, el mapa y la presentación; al planillero y al
  consultor, su trabajo, la ficha abierta, su historial de acercamientos y, al consultor, marcar un número
  equivocado). Son fijas por rol: con los datos políticos apagados, la de los líderes se ofrece igual y el asistente
  responde que no están habilitados.
- **Fotos de planillas.** El administrador y los coordinadores con su rol en **Ajustes → Planillas físicas por foto**
  (nunca planilleros ni consultores), y con un compromiso de confidencialidad vigente que lo permita (la versión
  2026-11-v2), ven una cámara a la izquierda del cuadro de escribir: **Tomar foto** o **Elegir de la galería**, como
  mucho 4 por mensaje, con el aviso fijo «Solo planillas o listas. No fotografíe cédulas. Tape columnas de salud,
  etnia, víctima o políticas. Borre la foto del teléfono.». Si una subida se rechaza por el rol, los ajustes o el
  compromiso (`permiso`, `planillas_apagado`, `compromiso_fotos`), el panel del chat vuelve a leer su estado y la
  cámara se oculta. Cada foto se prepara en el navegador, se sube a la bandeja del panel y el panel la empieza a leer
  de fondo mientras se escribe; el mensaje puede ir solo con fotos. El asistente revisa lo leído, pregunta lo dudoso, coteja y
  propone la carga en una tarjeta (ver [Planillas físicas por foto](#planillas-físicas-por-foto)).
- **Gráficos.** Cuando un análisis trae un gráfico, se dibuja debajo de la marca de esa herramienta (barras, columnas,
  una barra apilada o una serie en el tiempo), con su título, su unidad y su nota (por ejemplo, qué grupos se ocultaron
  por ser pocos). Al volver a abrir la conversación se ve en el mismo lugar.
- **Sabe dónde está.** Con cada mensaje viaja la vista abierta: la ruta, la ficha o la reunión que se está viendo, los
  filtros de la vista que están en la dirección (solo los que el asistente también puede usar), el encuadre del mapa y
  el capítulo y el paso de la presentación abierta (aquí o en el proyector; el nombre y el título los pone el servidor
  con el guion).
  Por eso «¿qué le falta a esta ficha?» funciona. Es solo una pista: las herramientas vuelven a leer todo con los
  permisos de la persona. Lo que no le corresponde no viaja aunque esté en la dirección (ver [Qué va al
  modelo](#privacidad-y-protección-de-datos-ley-1581-de-2012)): la consulta de la ruta (lo que va tras «?» o «#»), lo
  buscado en Habitantes con números o un correo (el asistente sabe que hay una búsqueda, no qué se buscó), la lista de
  origen, el liderazgo, el régimen de salud, una etiqueta sensible, la selección o el dibujo del mapa, ni el centro del
  mapa visto de cerca. Los filtros políticos no viajan en el contexto ni para A y K (el contexto no depende del rol ni
  del ajuste): el asistente los usa con sus herramientas.
- **Aprobar.** Cuando el asistente propone escribir, aparece una tarjeta con lo que va a hacer y los valores exactos (al
  editar, «antes → después») y los botones **Aprobar** y **Rechazar**. Nada se guarda sin aprobar. Lo rechazado no lo
  vuelve a proponer salvo que se le pida, y escribir otro mensaje sin decidir cuenta como rechazo (si ese mensaje se
  detiene o falla antes de que el asistente lo atienda, las tarjetas siguen esperando su decisión). Lo aprobado queda en
  la auditoría a nombre de quien aprobó, como si lo hubiera hecho en el formulario. Si la ficha cambió entre la tarjeta
  y la aprobación (otra persona la editó), no escribe nada y lo avisa: la tarjeta guarda una huella de lo que mostró,
  nunca los valores. Un acercamiento marca el número que mostró su tarjeta, aunque haya cambiado de lugar en la ficha
  (si ya no se puede usar, no registra nada). Sobre quien no autorizó el tratamiento no propone cambios (salvo registrar
  su autorización o una solicitud sobre sus datos), ni siquiera para el administrador, y si deja de autorizar entre la
  tarjeta y la aprobación, no escribe. La tarjeta muestra los valores enteros: lo que no cabe en ella (un dato de más de
  4.000 caracteres, más de 40 datos o algo que la herramienta tendría que recortar, como un documento largo de Mnemo) no
  se propone, y el asistente lo divide o lo acorta. Tampoco lo que no se vería como se va a escribir: un dato con
  caracteres invisibles o de control, o que cambian cómo se ve el resto del texto (como las marcas de dirección, el
  espacio de ancho cero o un selector de variante que no es parte de un emoji), sin asignar o de uso privado, o con
  muchos saltos de línea o espacios seguidos que esconderían el final. Un dato largo se lee entero desplazándolo dentro
  de su recuadro (una sombra marca que sigue y la tarjeta pide leerlo antes de aprobar); el panel nunca lo recorta, y si
  una tarjeta trajera más de lo que puede mostrar, no tiene **Aprobar**: solo se rechaza. Lo mismo lo que quedó
  esperando aprobación con una versión anterior del panel (que no mostraba los valores enteros): se rechaza y se le pide
  al asistente que lo vuelva a proponer. Una decisión que llega desde una pestaña que ya no está al día (otra pestaña
  aprobó y llegó otra propuesta) no decide nada: el asistente vuelve a traer la conversación, con lo que espera
  aprobación ahora.
- **El mapa** (administrador y coordinador). «Muéstrame en el mapa a las personas de La Paz sin cédula»: abre el mapa
  si hace falta, vuela al lugar, aplica los filtros y las capas y resalta los puntos. En el celular el panel se pliega
  para que se vea el cambio. Los nombres de las etiquetas del mapa los pone el navegador: al modelo solo le vuelve un
  resumen («1.234 personas, 980 ubicadas»). Los filtros que el asistente pone sin selector en el mapa se ven en el
  aviso **Filtros del asistente · Quitar**; la vereda a la que vuela queda marcada hasta que se le pide limpiar el
  mapa; y si se abre otra vista mientras el mapa carga, lo que esperaba aplicarse se descarta con un aviso. En un
  escritorio angosto, con el panel del asistente abierto, el panel izquierdo del mapa se pliega para que lo que muestra
  quede a la vista (vuelve con **Capas y filtros**).
- **La presentación** (todos los roles). «Preséntame la propuesta» o «muéstrame las viviendas nuevas»: el asistente abre
  la vista **Presentación** (la [presentación técnica](#la-presentación-técnica) de la propuesta 2028–2031,
  `web/propuesta.html?modo=tecnica`, dentro del panel) y, para explicar, arma un [plan guiado](#el-plan-guiado-recorridos-narrados):
  el chat muestra el plan entero y la pantalla lo ejecuta paso a paso, mostrando mientras explica, con lo que el guion
  de ese capítulo trae (textos, cifras, especificaciones, referentes, sitio, plazos, metas y lo que se ve en 3D, todo
  entero y sin plata: nada se acorta). «Acércate a la PTAR», «muéstrala como está hoy», «ábreme la ficha del
  matadero», «vista aérea con el norte arriba», «quítale la cubierta a la torre», «déjame ver solo el estadio»,
  «muéstrame la torre por dentro» o «el simulador sísmico»: con `visual` cambia lo que se ve sin cambiar de paso y le vuelve la ficha técnica de lo que muestra; en pantalla, si hace falta, pone una
  o dos frases cortas (hasta 220 caracteres) como subtítulo, que se quita al cambiar de paso. El subtítulo se ve siempre
  entero, sin recortes, del celular al proyector: en escritorio va abajo junto a la leyenda (o encima de ella, con todo
  el ancho, si al lado no le caben tres renglones); en el celular y la tableta en vertical, sobre la hoja inferior, que
  le cede el alto que haga falta; con el celular en horizontal, sobre la maqueta, abajo a la derecha del panel de la
  presentación (que conserva su alto, con el control a su pie). En el celular nunca tapa la franja donde la cámara
  encuadra la obra (al menos 90 px): si no cabe, su letra se achica y, en vertical, la hoja inferior cede más. Se vuelve
  a acomodar, con la letra más grande que cabe donde queda, al girar el celular, al ocultar o mostrar el panel («Solo
  3D») y al cambiar la altura de la hoja, sin esperar a que termine de moverse. Esa frase
  se proyecta ante otras personas: nunca lleva datos de habitantes, «@» (tampoco «＠» ni «﹫»), números de 7 o más
  dígitos, también escritos por grupos (con espacios, puntos, guiones, rayas, barras, paréntesis, el apóstrofo de los
  millones o lo que se escribe en su lugar, «71'234.567», «71´234.567», o un punto de viñeta), costos («$», «COP»,
  «pesos», «billones de», «billón de», «millones de pesos», en
  mayúsculas o minúsculas: la presentación que se maneja es la técnica, que no los muestra) ni caracteres que no se
  ven; sí un periodo («2028-2031», «2028–2031», «2028/2031»), una fecha que existe («15/11/2026», «2026-11-15») y un
  rango de cifras de menor a mayor («1.346–1.500 kWh»). «Siguiente» y «anterior» siguen desde el paso que dice el
  contexto. La barra de la vista muestra el capítulo y el paso, avanza y retrocede, pone la
  presentación a **Pantalla completa** (con el asistente a la vista: ver
  [Pantalla completa en la pestaña](#pantalla-completa-en-la-pestaña)) y la **Abre en otra pantalla**: una ventana del panel
  (`/presentacion?pantalla=1`) sin menú, para el proyector, que arranca en el capítulo, el paso y con la
  explicación de la pestaña del chat (el asistente también se abre ahí: ver
  [El asistente en la misma ventana](#el-asistente-en-la-misma-ventana)). Mientras esa ventana está abierta, manda ella: el asistente (y los botones de la
  vista) la manejan desde la pestaña del chat, que ya no cambia de vista; la barra de la vista muestra su paso y la
  presentación de la pestaña del chat la sigue, con la explicación que se ve allá, también cuando el paso cambia allá
  (el control remoto, el teclado), y lo que se haga en la de aquí va allá. Sigue respondiendo aunque quede detrás de la
  pestaña del chat (oculta, el navegador no le da cuadros: el paso cambia sin esperar sus animaciones), y una orden que
  espera en su fila detrás de otras no vence por ellas. Con dos ventanas de proyector (un doble clic en el enlace) manda
  la última que se abrió y la otra la sigue, así que cualquiera de las dos muestra lo mismo; si se cierra la que manda,
  vuelve a mandar la otra. Si la ventana se cierra sin avisar (o se cuelga), la siguiente orden se aplica en la pestaña
  del chat a los pocos segundos, sin esperar el plazo entero; y si se cierra con una orden en curso, esa orden también
  se aplica aquí (o en la otra ventana de proyector), no se pierde. En escritorio, con el asistente abierto, la
  presentación le deja su ancho (entre 901 y 1199 px el asistente se acopla más angosto en esta vista); en el celular el
  asistente se pliega al aplicar el cambio, y en horizontal la barra de la vista se oculta para dejarle el alto a la
  presentación. Sin el sitio público en el mismo servidor (el panel desplegado aparte sin `SITIO_URL`), la vista lo
  dice.
- **Cambios sin guardar.** Si la vista tiene cambios sin guardar (la ficha a medio editar, un formulario abierto), el
  asistente no la recarga, no abre otra, ni el mapa ni la presentación: lo dice en la conversación y, para abrir lo que
  pidió, ofrece **Abrir de todos modos** (lo que no se guardó se pierde). Las órdenes de la presentación de un mismo
  turno (ir a un paso y explicarlo) van en una sola nota, y su botón las aplica todas, en orden.
- **Enlaces.** Las personas y reuniones que nombra enlazan a su ficha dentro del panel (`/personas/123`,
  `/reuniones/45`); un hallazgo del diagnóstico, a Habitantes con sus filtros (`/personas?…`), y una planilla de la
  bandeja, a su revisión (`/importar?planilla=…`): solo rutas del panel que el rol puede abrir. Las aprobaciones de
  Mnemo abren Mnemo en otra pestaña. Ningún otro enlace se vuelve clicable.
- **Conversaciones.** **Nueva conversación** empieza otra; **Conversaciones** lista las 30 más recientes para abrirlas
  o borrarlas. Cada una es solo de su dueño: ni el administrador ve las de los demás. Se borran solas tras los días
  de **Ajustes** sin usarse. Una conversación muy larga deja de admitir mensajes: hay que empezar otra (también sale
  más barato). Cada conversación sigue con el modelo con que empezó (Mnemo o el modo directo): si ese ya no está, el
  asistente ofrece **Nueva conversación**. Si a un usuario le cambian el rol o la zona (en **Usuarios**, o en
  **Zonas** al asignarle o quitarle un área, redibujarla o borrarla), o lo desactivan, sus conversaciones se borran: lo
  que el asistente le mostró era de su rol o su zona de antes.
- **Tope diario.** El panel muestra cuántos mensajes quedan hoy. Al llegar al tope, se sigue al día siguiente (hora de
  Colombia). Aprobar o rechazar tarjetas también cuenta como un mensaje: el asistente vuelve a trabajar con lo
  decidido. Lo que queda pendiente al llegar al tope se puede aprobar al día siguiente.

### Preguntas por voz

En el cuadro de escribir hay un botón de micrófono, **Preguntar por voz**: no hace falta escribir.

- **Cómo se usa.** Un toque empieza y otro termina; **Escape** (o «Cancelar», junto al estado) cancela, también
  mientras se transcribe. Mientras escucha se ve el nivel del micrófono y «Escuchando…». El texto transcrito entra al
  cuadro y, si el cuadro estaba vacío, **se envía solo**; si ya había algo escrito, se agrega y no se envía. Tampoco
  se envía solo si hay acciones del asistente esperando aprobación (las dejaría sin aprobar): queda en el cuadro y
  Enter lo manda. Al empezar a escuchar, el plan que suena en esa pestaña se pausa (como al escribir), para que la
  narración no entre al micrófono. Salir de la página mientras escucha o transcribe (recargar, cerrar la pestaña,
  seguir un enlace) cancela, y lo pausado continúa; dejar oculta la pestaña mientras graba para el panel también
  cancela (si no, seguía grabando y lo enviaba solo). El estado se anuncia de forma discreta a los lectores de
  pantalla y nada de lo transcrito entra como HTML.
- **Grabar y transcribir en el servidor** (la vía de siempre). El navegador graba (`MediaRecorder`, opus) y corta
  solo: termina a los 1,6 s de silencio después de haber oído voz y a los 60 s como mucho, y descarta lo que dure
  menos de 0,4 s. Manda el audio crudo a `POST /api/agente/transcribir` (`audio/webm`, `audio/ogg`, `audio/mp4`,
  `audio/mpeg` o `audio/wav`, hasta 2 MB), con la sesión y el permiso del asistente. El servidor se lo pasa a Mnemo
  (`mnemo_transcribe`, en español) y responde `{texto, via: "mnemo"}`. No guarda ni registra el audio ni el texto
  (al registro solo van códigos). Cancelar mientras se transcribe corta la subida (la petición se aborta): el
  servidor lo nota, deja de esperar a Mnemo (cancela su llamada) y la persona puede volver a preguntar enseguida.
- **Errores** de la ruta, todos `{codigo, mensaje}`: 409 `sin_transcriptor` (no hay Mnemo conectado, la conexión no
  tiene el alcance o Mnemo no tiene un modelo que transcriba), 413 `grande`, 415 `tipo`, 422 `vacio` o `audio` (Mnemo
  no pudo leerla), 400 `cortada` (la subida se cortó a mitad: el celular perdió la señal o se cerró la pestaña; o la
  persona se fue mientras se transcribía, y esa respuesta ya no la lee nadie; sin traza en el registro), 400 `lenta`
  (la grabación no terminó de llegar en 30 s, o dejó de llegar durante 10 s: el servidor web esperaría para siempre
  un cuerpo estancado), 429 `frecuencia` y `volumen` (los topes de abajo), 402 `mnemo_creditos` y 502. El panel
  muestra el `mensaje` de cualquier código que no conoce: solo `sin_transcriptor` cambia de vía.
- **Topes** (cada transcripción gasta créditos de la cuenta de Mnemo conectada, y Mnemo atiende a lo sumo 4 llamadas a
  sus modelos a la vez por conexión, compartidas con el modelo del asistente):
  - una pregunta a la vez por persona, desde que empieza a llegar el audio hasta la respuesta (429 `frecuencia`, «su
    pregunta anterior»);
  - 20 por minuto por persona (429 `frecuencia`); un reintento rechazado por el tope anterior no cuenta;
  - como mucho el doble de los mensajes del día de la persona, y ninguna con sus mensajes del día ya gastados (429
    `volumen`: la pregunta no se podría enviar);
  - dos llamadas a Mnemo a la vez en todo el panel, solo mientras Mnemo transcribe (así el asistente sigue
    respondiendo). Mientras el audio llega no se ocupa ese cupo: una subida lenta o estancada no deja sin voz al
    resto. La tercera espera hasta 10 s a que se libere uno (transcribir tarda segundos) y después responde 429
    `frecuencia` («el panel está transcribiendo otras preguntas»).

  Todos son en memoria, por proceso. El tamaño no acota cuánto dura una grabación (quien graba elige la calidad, y
  Mnemo corta a los 10 minutos): lo que se acota es cuántas.
- **El reconocimiento del navegador** (`SpeechRecognition`, `es-CO`, con resultados parciales) se usa si el servidor
  no puede transcribir (`dictado` en falso, o un 409 `sin_transcriptor`) o el navegador no tiene `MediaRecorder`. El
  panel avisa que en esa vía transcribe el servicio del navegador. El 409 llega con la pregunta ya grabada, que el
  navegador no puede transcribir después, y **el micrófono no se reabre solo** (la persona ya terminó de hablar, no
  eligió esa vía, y lo que se dijera después en la sala se enviaría como pregunta): queda un aviso que pide tocar el
  micrófono y repetirla, y el toque siguiente va al navegador. Cuando el estado del panel vuelve a decir que
  transcribe (Mnemo se volvió a conectar), vuelve la vía del servidor.
- **Estados.** Inactivo, pidiendo el permiso del micrófono, escuchando, transcribiendo y error (sin permiso, sin
  micrófono, sin soporte, no se oyó nada o falló, con el mensaje del panel si trae uno).
- `GET /api/agente/estado` dice si esta instalación puede transcribir por Mnemo (`dictado`). `mnemo_transcribe` nunca
  es una herramienta para el modelo: solo la usa esa ruta (tampoco vuelve en una conversación guardada con un panel
  anterior o con `MNEMO_HERRAMIENTAS=*`: al rehacer sus herramientas se descartan esa y `mnemo_model_complete`).
- **Detalles que conviene saber.** Si en 10 segundos no se oye voz, termina con «No oí nada» y no transcribe (no gasta
  créditos en silencio). Cuando Mnemo dice que no puede transcribir, el servidor lo recuerda una hora y `dictado` sale
  en falso (una transcripción buena lo borra): así la pregunta siguiente va directo al reconocimiento del navegador.
  Con el audio se manda un vocabulario fijo de la propuesta (Yondó, PTAR, telesalud…) para que los nombres se
  escriban bien; no lleva datos de personas. Si el plan suena en la pantalla en off (también el automático), empezar
  a escuchar lo pausa allá y al terminar sigue; la pausa tarda hasta unos dos segundos en llegar. Una transcripción
  cancelada a mitad puede costarle créditos a la cuenta de Mnemo igual (el panel corta la llamada, pero Mnemo pudo
  haberla empezado). El panel solo deja usar el micrófono a sus propias páginas (`Permissions-Policy:
  microphone=(self)`); si un despliegue lo bloquea, el botón no se muestra.

### Respuestas habladas

Con la [voz clonada de Mnemo](#la-voz-clonada-de-mnemo) disponible (y **Leer en voz alta las respuestas del
asistente** encendido), el encabezado del asistente tiene un botón más, **Leer las respuestas en voz alta** (el ícono
de la voz): las respuestas se oyen con esa voz mientras el modelo escribe.

- **Cómo se usa.** Un toque lo enciende y otro lo apaga (`aria-pressed`); su título dice qué voz habla y que es una voz
  sintética. Queda encendido en esa pestaña (en `sessionStorage` `yj_agente`, con lo demás del asistente: nunca en
  `localStorage`, y se borra al cerrar sesión). El toque es además el gesto que el navegador pide para dejar sonar el
  audio de la ventana. Es la misma voz que la del botón **Voz** de la presentación: si la persona la apaga ahí (o con
  el interruptor de la tarjeta del chat), este botón se ve apagado y los mensajes no piden la respuesta hablada; un
  toque la vuelve a encender. Una pregunta **hecha por voz** (el micrófono) se responde hablada aunque el botón esté
  apagado. Mientras se lee, el mensaje que se oye lleva una raya del color del asistente al costado y el botón late.
- **Qué se dice.** Con el botón encendido (o la pregunta por voz), el mensaje lleva `contexto.voz: true` (y la
  aprobación de tarjetas, `voz: true`): el servidor le pide al modelo frases cortas, sin listas ni tablas, y arma las
  frases mientras el modelo escribe; cada una llega como el evento `frase`, firmada, y el navegador la pide a `POST
  /api/agente/voz` por su referencia (`{conversacion, texto, firma}`, tal como llegó: el navegador no puede pedirle a la
  voz otra cosa). Se dicen en orden, y mientras una suena la siguiente se precarga. Si el texto final de una ronda no
  es el que se venía leyendo (`frases_descartar`), lo que ya no vale se quita de la cola y la frase que sonaba se corta
  y se dice en su versión nueva; lo que ya se dijo entero no se repite (y si la versión nueva fue más corta, el
  servidor dice dónde empieza la ronda siguiente, `frases_ronda`, para que esa sí se oiga entera). Una conversación con
  datos de habitantes no se lee (el servidor no manda frases), ni una frase que repite lo que escribió la persona.
- **La sala oye.** Con una presentación abierta en esa ventana (la pestaña del chat, el proyector o la pantalla en
  off) o un proyector que maneja la pestaña, y su botón **Voz** encendido, el mensaje pide que se diga la
  [respuesta inmediata](#la-respuesta-inmediata) aunque este botón esté apagado (`contexto.voz_adelanto`): la sala
  está escuchando. Solo ella: la respuesta sigue escrita (sin frases ni el estilo hablado) y no gasta la voz clonada;
  para oírla también, este botón. El botón no se marca mientras suena lo de la sala (no es suyo). Aprobar una tarjeta
  no trae respuesta inmediata: para la sala no pide nada.
- **Se calla** al tocar el micrófono (en el acto, antes de pedir el permiso: la respuesta no entra a la grabación), al
  escribir en el cuadro, al enviar otro mensaje, con **Detener**, con **Escape** (la primera vez calla la voz; la
  segunda cierra el panel), al cerrar el panel, al cambiar o empezar otra conversación, al salir de la página y al
  apagar el botón. También cuando el turno pone un plan en la presentación: **la narración manda**. Mientras suena un
  plan en esa ventana o en el proyector (uno que no está en pausa), la respuesta espera hasta 20 s a que se pause:
  quien escribe en medio de un plan lo pausa al terminar la frase que suena (y quien pregunta por voz, en el acto), y
  entonces la respuesta se oye; si el plan sigue sonando, no se lee. Un plan que empieza (o sigue) calla la que se
  estaba leyendo (es la misma voz: `web/js/voz-panel.js`, una sola salida de audio por ventana). La excepción es la
  [respuesta inmediata](#la-respuesta-inmediata) que suena cuando llega un plan nuevo a esa ventana: el plan la espera.
  En el celular, el panel que se pliega para mostrar la vista calla la respuesta pero deja terminar la inmediata. Lo
  que se lee para la sala (ver «La sala oye») tampoco se calla al cerrar el panel: se cierra para ver la presentación
  entera y la sala la oye hasta el final (para callarla, **Escape** mientras suena, **Detener** o el micrófono).
- **Respaldo.** Si una frase no llega a tiempo con la voz clonada, se dice con la del navegador; si el panel responde
  que esa voz ya no está disponible (`sin_voz`, `voz_rol`), el resto de la sesión habla la del navegador y el asistente
  vuelve a leer su estado (el botón se va si el servidor ya no la ofrece).

### La respuesta inmediata

Preparar la respuesta completa toma tiempo: el modelo razona antes de escribir y, si arma un plan para la
presentación, escribirlo entero toma más. Para que nadie espere en silencio, con **Respuesta inmediata** encendido en
**Ajustes → Asistente** (`agente_adelanto`, encendido por defecto) cada pregunta recibe primero una respuesta corta, de
una a tres frases: reconoce la pregunta, da la idea general sin cifras ni datos que no estén ya en la conversación y
dice que el detalle viene enseguida («enseguida se lo muestro en la presentación», si hay una abierta y la pregunta
pide mostrar algo de la propuesta; si no, «enseguida le doy el detalle»). Va arriba de la respuesta de ese turno, y la
respuesta completa (o el plan) llega después, como siempre.

- **Cómo funciona.** Es otra petición al mismo modelo (`app/agente/adelanto.py`), a la par con la primera ronda de la
  respuesta completa, que no la espera: con sus propias instrucciones fijas (`sistema.SISTEMA_ADELANTO`), sin
  herramientas, sin razonar (o lo mínimo, con el esfuerzo `low`, si el modelo no deja apagarlo, como Claude Opus 5.5) y
  con un tope corto de tokens. Lee los últimos 8 mensajes de la conversación en texto plano (lo que escribió la persona
  y lo que respondió el asistente; sin herramientas, resultados, imágenes ni razonamiento) y el mensaje nuevo con el
  contexto de la vista. Con Mnemo va por `mnemo_model_complete` con `reasoning: "off"` y el mismo modelo; en modo
  directo, con el modelo de `AGENTE_MODELO_ADELANTO` si se eligió uno más rápido (por ejemplo `claude-haiku-5-5`), o
  con el del asistente.
- **Cuándo no aparece.** Si el mensaje es un saludo, una orden simple («siguiente», «pausa», «pantalla completa»…),
  una aprobación o algo que se responde en una frase, el modelo contesta solo «—» y no se muestra nada. Si la
  respuesta completa empieza a escribirse antes de que la inmediata muestre algo, la inmediata se cancela: no hace
  falta. Lo que ya empezó a mostrarse sigue hasta el final, como mucho 20 segundos (si se corta, termina en «…»), y el
  turno la espera antes de terminar. Aprobar o rechazar tarjetas nunca la pide. Si falla, no se ve nada, la respuesta
  completa sigue igual y al registro va solo el tipo del error.
- **Lo que muestra** va en texto plano (sin Markdown), palabra por palabra y como mucho 420 caracteres, cortados en el
  final de una frase. El modelo de la respuesta completa sabe que puede haber una (un renglón del contexto de la vista,
  `sistema.ADELANTO_EN_CURSO`, no de sus instrucciones fijas): no vuelve a saludar ni repite la idea general, salvo en
  lo que no lleva respuesta inmediata (un saludo, una orden simple, una aprobación, algo de una frase), donde responde
  como siempre (a un saludo, saluda).
- **Hablada.** Si el mensaje pidió la respuesta hablada (`contexto.voz`) o solo la inmediata hablada
  (`contexto.voz_adelanto`, la sala que oye una presentación: ver «Cuándo se oye»), sus frases llegan aparte (el evento
  `adelanto_frase`, numerado desde 0 aparte de `frase`) y firmadas igual, así que `POST /api/agente/voz` las acepta
  como las de la respuesta; las mismas reglas: nada en una conversación con datos de habitantes, ni lo que repite lo
  que escribió la persona, ni lo que no se dice ante una sala. Salen también sin la voz clonada: entonces las dice la
  voz del navegador.
- **En el chat** (`web/js/agente.js`). Aparece en cuanto llega su primer trozo, en un recuadro discreto arriba de la
  respuesta del turno (después de «Asistente:», antes de todo lo demás), con la etiqueta **Respuesta inmediata ·
  preparando el detalle…** mientras el turno sigue y **Respuesta inmediata** cuando termina. Entra como texto, nunca
  como HTML. Si termina sin mostrar nada (`vacio`), no queda nada. Al reabrir la conversación aparece igual, arriba de
  su respuesta (la parte `adelanto` del historial). Para los lectores de pantalla: la conversación está ocupada
  (`aria-busy`) mientras dura el turno y lo de adentro no se anuncia hasta que termina, así que la inmediata que no se
  dice en voz alta se anuncia una vez, en cuanto termina, en una región aparte (`#agente-adelanto-vivo`, fuera de la
  conversación); «· preparando el detalle…» va escondido para ellos, así la etiqueta no se vuelve a anunciar.
- **Cuándo se oye.** Como la [respuesta hablada](#respuestas-habladas): con **Leer las respuestas en voz alta**
  encendido o si la pregunta llegó por voz. Y además cuando la sala está oyendo: una presentación abierta en esa ventana
  (la pestaña del chat, el proyector o la pantalla en off) o un proyector que maneja la pestaña, con su botón **Voz**
  encendido. Entonces, si el botón del chat está apagado o no hay voz clonada, el mensaje pide solo la voz de la
  inmediata (`contexto.voz_adelanto`, aparte de `contexto.voz`): el servidor manda sus `adelanto_frase` y ninguna
  `frase` de la respuesta, que sigue escrita y no se lee (tampoco con la voz clonada; para oírla, **Leer las
  respuestas**).
  Sin la voz clonada que lee las respuestas, la inmediata se dice con la voz del navegador (sus frases van sin
  referencia: no se le pide nada a Mnemo); con ella, con la voz clonada. Aprobar tarjetas no la trae, así que para la
  sala no pide nada. Una pantalla en off de otro equipo no cuenta: la voz suena en la ventana del chat.
- **Va primero** (`web/js/locutor.js`). Sus frases tienen su propia cola: las de la respuesta que llegan mientras
  suena esperan a que se diga entera y termine (`adelanto_fin`; con `vacio`, siguen en el acto). El servidor manda ese
  `vacio` antes del primer texto de la respuesta si la inmediata no alcanzó a mostrar nada, así que sin ella la
  respuesta no espera. Si no se sabe nada de la inmediata en 8 s (no llega ni suena nada suyo), la respuesta deja de
  esperarla y lo que llegue tarde no se dice. Lo que calla la respuesta calla las dos: el micrófono, escribir,
  **Detener**, **Escape**, cerrar el panel (salvo lo que se lee para la sala, que termina: se cierra el chat para ver
  la presentación), otra conversación.
- **El plan la espera.** Si el turno pone un plan en la presentación de esa ventana mientras suena la inmediata, la
  respuesta se calla como siempre, pero la inmediata termina: la espera de 1,8 s antes del primer paso del plan se
  alarga hasta que termine, como mucho 15 s desde que llegó el plan (`ESPERA_ADELANTO_MS` de
  `web/js/reproductor.js`; una pausa no cuenta y **Siguiente** empieza ya). Mientras espera, el plan le cede la voz de
  la ventana (`web/js/voz-panel.js`: sus frases no lo esperan y su primera precarga no las calla); después de esa
  espera, la narración manda como siempre. Con un proyector abierto, o con un plan para la pantalla en off de otra
  ventana u otro equipo (allá no la pueden esperar), el plan la calla. La sala oye la idea general entera y después el
  plan.
- **Se guarda** con el turno (un mensaje `adelanto` de la conversación, que nunca se le reenvía al modelo y cuenta en
  su tope de 400 mensajes) y se ve al reabrir la conversación, arriba de la respuesta de su turno.
- **Costo.** Una llamada corta más al modelo por pregunta (ver [Límites y costos](#límites-y-costos)); no cuenta en el
  tope de mensajes por día. Se apaga en **Ajustes → Asistente** con la casilla **Respuesta inmediata** (del
  formulario del asistente: solo el administrador la cambia; el coordinador la ve en solo lectura).
- **Con Mnemo, solo si sobra.** Mnemo deja pocas llamadas al modelo a la vez para todo el panel, así que la respuesta
  inmediata va solo cuando el proceso no está atendiendo el turno de otra persona ni transcribiendo un dictado, y una a
  la vez (`adelanto.tomar_mnemo`): nunca le quita el cupo a una respuesta. Si no va, el modelo de la respuesta completa
  tampoco recibe el renglón que la anuncia. En modo directo va siempre.

## Planillas físicas por foto

Cuando una planilla de campo no se pudo llenar en el panel (sin señal, sin celular, en una vereda), el planillero
entrega el papel y el administrador o un coordinador le toma una foto y la sube a la **bandeja de planillas** del
panel (`app/planillas.py`, rutas en `app/api/planillas.py`). El panel la lee de fondo con una llamada aparte al
modelo, guarda la foto y lo leído cifrados y, con una persona del equipo, lo coteja con la base y lo carga como una
planilla de campo, con la foto como evidencia. El chat y la vista **Importar y exportar → Planillas por foto** usan
las mismas rutas, con la sesión de quien los usa: la vista sirve para revisar muchas hojas con la foto al lado; el
chat, para hacerlo conversando.

**Quién.**

| Qué | Quién |
|---|---|
| Subir fotos (la cámara del chat o la vista) | A y K (`importar`) con su rol en **Ajustes → Planillas físicas por foto** (`agente_planillas.roles`: los dos por defecto), un modelo conectado y un compromiso de confidencialidad vigente que lo permita (2026-11-v2) |
| Ver la bandeja, la foto y lo leído | A y K (`importar`): toda la bandeja y lo leído con los valores completos (como ven las fichas en el panel). Al modelo del chat, siempre enmascarado |
| Corregir celdas, descartar filas, volver a leer, borrar, cotejar y cargar | A y K (`importar`) |
| Confirmar las autorizaciones con el papel | A y K, en **Importar y exportar** (la ruta de siempre). El asistente no tiene herramienta para eso |

**Solo el administrador y los coordinadores.** Los planilleros nunca suben, leen, cotejan ni cargan planillas por foto
(ni los consultores): cada ruta `/api/planillas…` pide `importar` y les responde 403 `permiso` antes de leer el cuerpo,
digan lo que digan los ajustes guardados (`politica.ajustes_planillas` quita un «planillero» guardado de antes y
`PUT /api/ajustes` con él responde 422), y las cuatro herramientas del chat piden `importar`. El planillero que llenó
el papel queda como «Capturado por» (`capturado_por`) de lo cargado.

**El compromiso de confidencialidad.** Fotografiar planillas exige un compromiso que lo permita: la versión
**2026-11-v2** (`acceso.COMPROMISOS`, la de defecto en `compromiso_version`) cambia el punto 2 de la 2026-11-v1, que
decía «No los copiaré, exportaré, fotografiaré ni compartiré…», por «Usaré los datos solo para la finalidad informada
al titular. No los copiaré, exportaré ni compartiré, ni haré capturas de pantalla. Solo fotografiaré planillas físicas,
y únicamente para subirlas por el panel cuando mi rol lo permita (la cámara del asistente o Importar y exportar →
Planillas por foto); nunca cédulas ni otros documentos. Borraré la foto del teléfono después de subirla.» Los puntos
1, 3 y 4 no cambian. Una instalación que no guardó la versión a mano pasa sola a la nueva, y cada coordinador,
planillero y consultor la acepta de nuevo en su siguiente petición (403 `compromiso` → Mi cuenta). Si el compromiso
vigente no lo permite (`acceso.compromiso_permite_fotos`; por ejemplo, la 2026-11-v1 guardada a mano):

- `POST /api/planillas/fotos` responde 409 `compromiso_fotos` antes de leer el cuerpo: «El compromiso de
  confidencialidad vigente no permite fotografiar planillas: el administrador elige en Ajustes una versión que lo
  permita (2026-11-v2) y cada persona la acepta de nuevo.»
- `GET /api/agente/estado` trae `adjuntos: null` (el chat no ofrece la cámara) y `GET /api/ajustes`,
  `compromiso_permite_fotos: false` y `compromiso_con_fotos: "2026-11-v2"`.
- **Ajustes → Planillas físicas por foto** lo avisa y le ofrece al administrador **Usar el compromiso 2026-11-v2**
  (con una confirmación: todos lo aceptan de nuevo); **Importar y exportar → Planillas por foto** oculta la subida con
  el motivo.
- Lo ya subido se sigue revisando, cotejando y cargando: releer no es fotografiar.

**El flujo.**

1. **Subir** (`POST /api/planillas/fotos`): el navegador rehace la foto (derecha, reducida, JPEG nuevo sin EXIF ni
   GPS) y la sube cruda; el servidor la valida, le quita los metadatos, la guarda cifrada y la deja «leyendo».
2. **Leer de fondo** (`planillas.leer_foto` con `agente/lector_planillas.py`): una llamada aparte al modelo, sin
   herramientas ni historial, transcribe la hoja a JSON. Corre aunque el navegador se vaya (se bloquea la pantalla, se
   pierde la señal). Lo leído se sanea, se aplican las reglas de privacidad por fila y se guarda cifrado («leida»).
3. **Revisar**: el asistente lo lee enmascarado (`leer_planilla`) y pregunta lo dudoso; en la vista, A y K ven la foto
   al lado de la grilla con los valores completos, corrigen celdas (`PATCH`) y descartan filas.
4. **Cotejar** (`POST …/simular`): la vista previa fiel del importador, fila por fila, sin escribir nada.
5. **Cargar** (`POST …/cargar`): el importador real, como una planilla de campo (fuente «planilla», archivo «Foto de
   planilla física», el SHA-256 de la foto como evidencia y el folio del papel). Al cargar la hoja entera, la foto se
   borra (queda su SHA-256 en la importación) y de lo leído queda solo número de fila, estado y ficha.
6. **Confirmar las autorizaciones** con el papel en **Importar y exportar**
   (`POST /api/importaciones/{iid}/confirmar-autorizaciones`), A o K. Hasta entonces, todo «sí» leído de una foto
   queda **declarado en planilla**: vale para la ficha pero no habilita llamadas ni mensajes.

**En el chat.**

- La cámara del cuadro de escribir sube cada foto a la bandeja (de a una, con su miniatura en un canvas y los avisos
  «Foto pequeña», «Foto oscura» y «Foto movida o desenfocada», que no impiden mandarla; **Girar**, **Quitar** y
  **Reintentar** la subida) y el mensaje lleva solo sus ids (`adjuntos`, como mucho 4). Con una foto que no subió no se
  envía; si se envía mientras alguna todavía sube, sale sola cuando termina. **Reintentar** y **Nueva conversación**
  conservan las fotos, y la conversación muestra el chip «n fotos adjuntas» (al volver a abrirla, solo el chip: las
  imágenes nunca vuelven al navegador).
- **El modelo nunca recibe la imagen.** Después del contexto del panel le llega un bloque `<fotos_adjuntas>` con cada
  id y en qué va (leyendo, leída con cuántas filas y dudas, rechazada con su motivo, ya cargada…), leído al empezar el
  turno, y la indicación de usar `leer_planilla`. Un mensaje con solo fotos le llega como «(Envié fotos sin texto.)»
  (nunca un bloque de texto vacío, que la API rechaza) y se guarda con el texto vacío; la conversación que empieza así
  se titula «Fotos de planillas». En una conversación anterior, sin estas herramientas, el bloque dice que se revisen
  en la vista o en una conversación nueva.
- Antes de abrir el turno, el servidor comprueba que el rol sube fotos (403 `planillas_apagado`: solo A y K) y que
  cada foto es de quien escribe y sigue en la bandeja (422 `fotos`: una de otra persona responde igual que una que no
  existe). Nada se cuenta ni se reserva antes de eso.
- El asistente sigue el flujo **leer → preguntar lo dudoso → cotejar → cargar**. Lo que la persona confirma con el papel
  va en `correcciones` (nunca la autorización, el medio, los canales, «mayor de 18» ni las observaciones: el esquema no
  los admite). Carga primero las filas limpias (hasta 30 por tarjeta) y deja para el final, **en su propia tarjeta**,
  las filas en «no» (revocaria, no_autorizo, nueva_sin_autorizacion): mezclarlas da el error `separar`. Si alguna retira
  una autorización que ya se había dado, la tarjeta avisa que **esta conversación se borrará al cargarlas**, y se borra
  (toda conversación que anotó a quien deja de autorizar se borra, sin excepción); un «no» de alguien nuevo no la borra.
- **La tarjeta muestra los valores enteros a quien aprueba, nunca al modelo**: una línea por persona con los campos en
  un orden fijo (nombre · documento · celular · otro teléfono · sexo · nacimiento · edad · dirección · barrio · puesto y
  mesa · la autorización en una forma fija calculada por el servidor · canales · medio leído · mayor de 18 · planillero
  · fecha · observaciones · firma · «⚠ dudoso: …» · «⚠ ilegible: …» · «✎ corregido por el asistente: campo «antes» →
  «después»» · «✎ corregido en el panel: …» · lo que llena y lo distinto · el reemplazo), cada valor en una sola línea,
  y hasta 6 líneas fijas (planilla, evidencia, folio, capturado por, reunión, resumen). `Confirmacion.personas` son las
  fichas que la vista previa encontró en esas filas: si una pide la supresión o dice «no», la conversación se borra.
- **Lo aprobado es lo que se escribe.** Al aprobar: (1) las correcciones (`PATCH /api/planillas/{id}`, que no respeta la
  clave de idempotencia: se vuelve a leer y solo se mandan las celdas que todavía no tienen ese valor); (2) se vuelve a
  cotejar exactamente las filas de la tarjeta y se compara, fila por fila, la huella (HMAC) de lo que la tarjeta mostró:
  si algo cambió (alguien corrigió la planilla en la vista, la base cambió, o una corrección movió a quién corresponde
  la fila), **no se carga nada** (`cambiada`) y el asistente vuelve a cotejar; (3) la carga con el importador real
  (`POST …/cargar`, clave `agente.{cid}.{tool_use}.imp`: repetir la aprobación devuelve lo guardado); (4) los reemplazos
  que se pidieron (sexo, edad, dirección o puesto; solo si la fila completó la ficha de la tarjeta y la ficha no está en
  «no»; `PATCH /api/personas/{id}` en modo reemplazar, con lo de la ficha a datos alternos); (5) los asistentes de la
  reunión, sin quien quedó en «no» (clave `….as{persona}`). Al modelo le vuelve el número de importación, por fila el
  estado en pasado y la ficha (salvo las filas en «no»), el resumen en conteos, lo corregido y en qué quedó la planilla.
- La conversación queda **marcada con datos** (`conversaciones.marcar_datos`) en cuanto recibe filas de una planilla
  (muchas son de personas sin ficha, sin id que anotar): no se proyecta ante una sala y el turno deja de hablar con la
  voz clonada.

**En la vista Importar y exportar → Planillas por foto** (`web/js/vistas/importar.js`, `web/css/planillas.css`):

- **Subir**: «Tomar foto» (la cámara trasera) o «Elegir fotos» (hasta 10 por vez; en el computador también se
  arrastran), con el mismo aviso fijo del chat y lo que pasa con la foto (va al modelo solo para leerla, se guarda
  cifrada y se borra al cargar la hoja o a las `retencion_horas`). Cada foto se prepara de a una, como en el chat, y se
  sube con una nota opcional (y el formato, si `agente_planillas.otros_formatos` está encendido). Los topes del
  servidor detienen el resto de la tanda con su mensaje.
- **Bandeja**: cada foto con su estado (Leyendo… n filas, Por revisar, Carga parcial, Falló la lectura con su motivo,
  Rechazada, Cargada · importación #N), filas, dudas, vencimiento, nota y quién la subió; filtros (todas, por revisar,
  leyendo, con error, cargadas). Mientras alguna se lee, la bandeja se consulta sola cada 3 s (no con la pestaña
  oculta). «Volver a leer» en una que falló; borrar con confirmación.
- **Revisar** (A y K): al abrir una, la dirección queda `/importar?planilla=<id>` (sirve de enlace directo, también el
  que da el asistente). La foto se pide con la sesión y se dibuja en un canvas (zoom, arrastre y giro solo para verla)
  al lado de la grilla de las 20 columnas con los valores completos; lo dudoso, lo ilegible y lo corregido llevan un
  signo (?, ✕, ✓) además del color. Cada celda se corrige escribiendo (Enter baja, Escape devuelve lo leído) y
  «Guardar correcciones (n)» manda todo en un `PATCH`; si otra persona cambió la planilla (`cambiada`), se vuelve a
  traer con lo escrito encima. Una fila se descarta o se recupera.
- **Cotejar**: la vista previa por fila, con lo que llenaría, lo distinto entre la base y la planilla y el enlace a la
  ficha encontrada (en otra pestaña).
- **Cargar**: las filas elegidas (al abrir, las limpias y las «No autoriza»; una dudosa se elige sola al corregirla),
  el **folio** o dónde queda el papel (obligatorio en la vista: es lo que permite encontrar la hoja cuando la foto ya se
  borró) y «Capturado por» (la lista de planilleros; se propone quien subió la foto si es planillero, o el que nombra
  el encabezado). Un diálogo resume antes qué pasará y manda la carga con su `Idempotency-Key`.
- **Resultado**: la importación, personas nuevas, fichas completadas, lo que queda en Calidad de datos, cada fila con su
  ficha y **«Confirmar n con el papel»**, que abre la confirmación de autorizaciones de siempre.

**La lectura** (`app/agente/lector_planillas.py`).

- Una llamada aparte al proveedor del modelo de la conversación (Mnemo o Anthropic), con sus propias instrucciones, la
  imagen y un texto, **sin herramientas ni historial**: `max_tokens` 16.000 con Mnemo y 24.000 en modo directo,
  esfuerzo `medium`, 150 s por llamada y 270 s con un reintento. Con Mnemo, la imagen se valida antes como cualquier
  imagen de Mnemo. El uso se suma al día de quien subió la foto en `agente_uso`, también si la lectura falla.
- **Qué modelo ve la foto.** Con Mnemo, el de la cuenta para leer imágenes, no el de la conversación: el panel le pide
  a `mnemo_model_complete` el modelo `{"model": "vision"}`, no el de `MNEMO_MODELO` (el principal puede no leer
  imágenes). Mnemo usa el que el administrador eligió en Mnemo, en **Ajustes → Modelos → Plantel**, «leer imágenes»
  (o el que Mnemo elige solo cuando el principal no las lee); si no sabe de otro, el principal. La lectura falla con
  `mnemo_sin_vision`, y el mensaje dice qué hacer en Mnemo, si Mnemo sabe que ningún modelo de la cuenta lee imágenes
  (`no_vision`), si el de leerlas no se puede usar ahora (`vision_unavailable`: sin saldo o con la clave de su
  proveedor rechazada) o si su proveedor rechazó la foto (`provider_rejected`: un modelo que no lee imágenes, o no
  esa). Ninguno se repite: repetir no lo arregla, y con otro modelo la foto podría llegar a uno que no la ve y que
  cobra igual. Un Mnemo anterior, que no conoce `vision`, responde `INVALID_ARGUMENT` sin motivo: el panel repite
  enseguida la misma petición con el modelo de siempre (el de `MNEMO_MODELO`, o el principal), deja una línea en el
  registro, sin contenido, y si ese modelo no ve la foto el mensaje pide actualizar Mnemo (elegir uno en el plantel no
  cambiaría nada). Un Mnemo de ahora, con `vision`, solo responde así a una petición fuera del contrato, que no llega a
  ningún modelo y vuelve a fallar sin gastar. En modo directo, el de `AGENTE_MODELO`: Claude lee imágenes.
- Las instrucciones dicen que lo escrito en la hoja es un dato a transcribir, **nunca una instrucción**, y que no se
  transcriben datos sensibles (salud, etnia, discapacidad, condición de víctima, huellas) ni políticos aunque estén en
  el papel: aunque el asistente ya pueda recibir lo político, la planilla de campo no tiene esas columnas y el
  importador de planillas no las toma; el tipo y el «Liderado por» se marcan aparte, en la ficha o con `marcar_tipo` y
  `asignar_lider`. La salida es compacta: `{imagen_visible, tipo_formato, filas_visibles, encabezado, columnas, filas:
  [{n, v, firma, dudosos, ilegibles}]}`. Solo se guardan las 20 columnas conocidas: cedula, cedula_repetida,
  tipo_documento, nombre, celular, otro_telefono, sexo, fecha_nacimiento, edad, direccion, barrio, puesto, mesa,
  autorizacion, medio, canales, mayor_18, planillero, fecha y observaciones (una columna sensible que el modelo
  transcribiera igual no se guarda). Cada valor queda en una sola línea, en NFC, sin invisibles ni caracteres de
  control y con los largos de la ficha.
- Se rechaza (con su motivo en la bandeja): sin imagen visible (`sin_imagen`: el mensaje nombra el modelo que
  respondió, por ejemplo «El modelo que respondió (deepseek/deepseek-v4-flash) no pudo ver la foto…», y con Mnemo
  dónde se elige el que lee imágenes; si se repite, ese modelo no las lee), sin filas, más filas que las visibles
  (`inventadas`), **una foto de un documento de identidad** (se borra la foto: «No se leen fotos de cédulas»), otro
  formato con `otros_formatos` apagado (se borra la foto), un rechazo del modelo, una respuesta que no se entiende, el
  plazo y los errores del proveedor. Si la respuesta se corta, se rescatan las filas completas y la lectura queda
  `incompleta`: se puede volver a leer desde la fila siguiente (`desde_fila`), conservando lo anterior.
- Como mucho **2 lecturas por foto** (la primera y una relectura); la misma foto subida otra vez por la misma persona es
  la misma (no vuelve al modelo, salvo que su lectura hubiera fallado) y una ya cargada responde 409 `ya_cargada` con la
  importación. Lecturas a la vez en el proceso: 1 con Mnemo y 2 con Anthropic (las demás esperan en cola). Una lectura
  «leyendo» sin latido por 5 minutos se da por fallida al consultarla.

**Rutas** (errores `{"detail": {"codigo", "mensaje", …}}`; los ids son 32 hexadecimales al azar y uno de otra persona
responde 404 `no_existe`, igual que uno que no existe; todas piden `importar`, solo A y K, y comprueban el permiso
antes de leer el cuerpo: P y C reciben 403 `permiso`):

| Ruta | Permiso | Qué |
|---|---|---|
| `POST /api/planillas/fotos?nota=&formato=` | `importar` + rol en `agente_planillas.roles` + modelo + compromiso que lo permita | Cuerpo crudo `image/jpeg` o `image/png` (≤ 1,5 MB). 201 `{id, estado: "leyendo", bytes, ancho, alto, expira}` y la lectura de fondo encolada; 200 con `repetida: true` si es la misma foto de la misma persona; 409 `ya_cargada`, `pendientes`, `compromiso_fotos`; 403 `permiso`, `planillas_apagado`; 503 `sin_configurar`; 413, 415, 422 y 429 `frecuencia` |
| `GET /api/planillas?estado=` | `importar` | La bandeja, sin datos de personas: todas (las 100 más nuevas) |
| `GET /api/planillas/{id}?enmascarada=1` | `importar` | La planilla con su encabezado y sus filas completas (enmascaradas con `enmascarada=1`, como las pide el asistente) |
| `GET /api/planillas/{id}/foto` | `importar` | La foto limpia: `Content-Type` real, `nosniff`, `no-store`, `Content-Disposition: attachment`, `Cross-Origin-Resource-Policy: same-origin`. 404 `sin_foto` si ya se borró |
| `PATCH /api/planillas/{id}` | `importar` | `{filas?: [{n, campo, valor}], descartar?: [n], restaurar?: [n]}`: corrige celdas y descarta filas; las reglas de privacidad por fila se vuelven a aplicar |
| `POST /api/planillas/{id}/leer` | `importar` + rol + modelo | Volver a leer (`{desde_fila?}` si quedó incompleta). 409 `max_lecturas` |
| `DELETE /api/planillas/{id}` | `importar` | Borra la foto y lo leído |
| `POST /api/planillas/{id}/simular` | `importar` | La vista previa por fila: `{n, estado, persona_id, llenaria, distintos, motivo}`. No escribe; anota las lecturas de las fichas encontradas |
| `POST /api/planillas/{id}/cargar` | `importar`, idempotente | `{filas?, folio?, capturado_por?}` → `{importacion_id, resumen, filas: {n: {persona_id, estado, motivo}}}` |

**Estados.** De la foto: `leyendo`, `leida` (también tras una carga parcial), `fallida` (se puede volver a leer),
`rechazada` (una cédula u otro formato: sin foto) y `cargada`. De cada fila: `pendiente`, `no_autoriza`, `no_se_carga`,
`descartada` y `cargada`. Del cotejo: `nueva`, `nueva_sin_autorizacion`, `completaria`, `igual`, `revocaria` (la ficha
decía «sí» y el papel «no»), `conflicto_cedula`, `revision` (posible duplicado o digitación), `no_autorizo`,
`otra_eleccion` (su puesto guardado es de otra elección), `sin_nombre`, `ya_cargada` y `no_se_carga` (sin motivo ni
persona: nunca se dice que alguien pidió la supresión); al cargar, los mismos en pasado (completada, revocada…) y
`no_guardada` (la ficha cambió en el panel mientras tanto: la fila sigue pendiente).

La privacidad de las fotos (la excepción, el cifrado, la retención y lo que se guarda de cada fila) está en [La
excepción de las fotos de planillas](#la-excepción-de-las-fotos-de-planillas); los topes, en [Límites y
costos](#límites-y-costos).

## Análisis avanzados

El servidor calcula análisis agregados de la base, más allá de los indicadores del Tablero, y el asistente los pide
con dos herramientas de lectura, `analizar` y `diagnostico` (A y K, permiso `analitica.ver`). El motor está en
`app/analitica.py` y no usa el modelo: las cifras salen de MongoDB, ya protegidas, y el gráfico lo arma el servidor
(el modelo no escribe sus números). Por la clave MCP de alcance «analitica» llega lo mismo, sin el gráfico.

- `GET /api/analitica?consulta=<json>` corre un análisis: `consulta` es `tipo` y solo los parámetros de ese tipo (uno
  que no aplica es un error, no se ignora). Es una lectura: no escribe, no audita ni registra lecturas, porque solo da
  agregados. Una consulta inválida responde 422 `invalido` con los errores en `campos`; una etiqueta sensible, 403.
- `GET /api/analitica/catalogo` dice qué se admite: tipos y parámetros, dimensiones, métricas, eventos, filtros,
  límites y los puestos de la elección vigente.

| Tipo | Qué da | Parámetros (obligatorios en negrita) |
|---|---|---|
| `tabla` | Personas y métricas por 1 o 2 dimensiones | **dimensiones**, metricas, filtros |
| `serie` | Un evento por día, semana o mes, con tendencia (total, media, último frente al anterior, pendiente, proyección, mejor y peor periodo) | **evento**, granularidad, desglose, desde, hasta, filtros |
| `embudo` | Vigentes → teléfono usable → autorizaron → contacto habilitado → abordadas → contestaron → contacto útil → puesto y mesa → votación verificada; tasas, la mayor caída con su acción y los rechazos aparte | dimensiones (0 o 1), filtros |
| `cobertura` | Por puesto de la elección vigente: registrados frente a los habilitados del censo (total, mujeres, hombres), con mesa, verificados, estimación por mesa y lo que falta para la meta; sin puesto, otro municipio, no inscritos, puesto escrito sin catálogo y otra elección | meta_pct (30), filtros |
| `ritmo` | Por puesto: el ritmo semanal de personas nuevas, la cobertura proyectada a `fecha_meta`, si llega a la meta y cuántas por semana faltan | **fecha_meta**, meta_pct, semanas, filtros |
| `brechas` | Barrios y veredas de 10 o más personas, del más desatendido al más atendido, con un índice de atención de 0 a 100 | dias (30, 60, 90, 180 o 365), filtros |
| `equipo` | Por usuario: altas (las de planilla, para el planillero), actualizadas, campos completados, acercamientos, efectivos, contactos útiles, rechazos, tasa, % fuera de horario, reuniones y asistentes, frente a la mediana | desde, hasta, granularidad |
| `calidad` | Completitud, datos que faltan por campo, autorizaciones por confirmar, teléfonos equivocados, votación por confirmar, lugares y puestos sin reconocer, coincidencias, conflictos, solicitudes abiertas y vencidas, situaciones y lugares sin punto | dimensiones (zona), filtros |
| `anomalias` | Solo conteos: picos diarios por usuario, % fuera de horario, números en más de 3 fichas, posibles digitaciones, altas que se unieron como duplicadas, mesas con más registrados que la estimación, personas urbanas con puesto rural | desde, hasta |
| `cohortes` | Por mes de alta: % abordadas en 30 días, contactadas, con cédula, autorizadas y asistieron | desde, hasta, filtros |
| `franjas` | Tasa de contacto y de contacto útil por hora de Colombia, día y canal; dentro y fuera del horario de Ajustes | desde, hasta, desglose, filtros |
| `intentos` | Probabilidad de contacto en el intento 1, 2, 3…, y la recomendación de `max_intentos_sin_exito` y `dias_entre_intentos` frente a los de Ajustes | desde, hasta, filtros |
| `captura` | Por quien capturó (10 fichas o más): teléfonos equivocados, conflictos, sin autorización, completitud y duplicados unidos, frente a la mediana. Para capacitar, no para sancionar | desde, hasta |
| `comparar` | Entre un periodo y otro: qué grupo explica el cambio de altas, acercamientos, contacto útil o autorizaciones; en la tasa de contacto útil, efecto mezcla y efecto tasa | **metrica**, **dimensiones** (1), desde, hasta, referencia_desde, referencia_hasta, filtros |
| `reuniones_efecto` | En el barrio o la vereda de cada reunión: altas, autorizaciones y contactos útiles 4 semanas antes y 4 después, con la advertencia de que no prueba que la reunión lo causó | desde, hasta |
| `diagnostico` | Hallazgos ordenados por urgencia (la herramienta `diagnostico`) | filtros, fecha_meta, meta_pct |

- **Dimensiones** de personas: zona, lugar (los de menos de 10 personas se juntan en «Otros lugares»), lugar_tipo,
  sexo, rango_edad, menor, tipo_documento, estado_civil, nivel_educativo, situacion_laboral, tenencia_vivienda,
  estrato, jefe_hogar, personas_hogar, precision, puesto, mesa, votacion_estado, donde, consentimiento,
  consentimiento_medio, contacto_habilitado, abordaje_estado, ultimo_resultado, ultimo_canal, intentos, completitud,
  con_cedula, cedula_verificada, telefono_usable, varios_telefonos, requiere_actualizacion, etiqueta (no sensibles),
  asistencia, fuente (solo «tiene la fuente» trámites, reunión, panel o planilla, sin resto ni total), quien_capturo y
  mes_alta; con los [datos políticos](#datos-políticos), también tipo, lider y lista. De eventos (para comparar):
  canal, usuario, resultado, medio, campo, franja y dia_semana.
- **Definiciones**: «efectivo» es que contestó o atendió, aunque haya rechazado; «contacto útil», efectivo sin «no
  contactar» ni «pidió sus datos»; las altas del equipo no incluyen las importaciones de bases (van a «importación»), y
  las de una planilla van al planillero.
- **El diagnóstico** hace una sola lectura de la base (plazo de 120 s; unos 2 s con 16.000 personas) y revisa
  solicitudes vencidas, autorizaciones por confirmar, autorizadas que nadie ha llamado, «volver a llamar» vencidos, la
  mayor caída del embudo, cédula o puesto que faltan, puestos que no llegan a la meta, lugares desatendidos, caídas del
  contacto útil, horas y número de intentos, teléfonos equivocados por quien capturó, duplicados, lugares sin
  reconocer, anomalías, cohortes lentas y el efecto de las reuniones. Cada hallazgo trae `severidad` (alta, media,
  baja), `titulo`, `evidencia`, `por_que`, `accion` y, si se puede, un `enlace` a Habitantes (`/personas?…`) con su
  cifra: solo con filtros que Habitantes y `filtros.Filtros` entienden (`analitica.ENLAZABLES`), contada con esos mismos
  filtros y sin quienes no autorizaron. La `nota` del enlace dice en qué difiere la lista cuando no hay un filtro exacto
  (Habitantes sí muestra a quienes no autorizaron, para A y K).
- **El gráfico** (`app/agente/grafico.py`, `web/js/agente-graficos.js`): `{tipo: "grafico", clase: barras | columnas |
  apilada | serie, titulo, unidad, items: [{etiqueta, valor, texto?}], nota?}`, de 1 a 60 ítems, validado en el
  servidor y otra vez en el navegador, que lo dibuja con `web/js/graficos.js` (títulos y notas como texto, colores solo
  de la paleta). Va como acción `grafico` justo después del resultado de su herramienta y se guarda con ella: al
  repintar la conversación se ve en el mismo lugar. Los grupos ocultos no van, y la `nota` dice por qué; con `pocas` o
  `dispersas` no hay gráfico.

**Cómo se protegen las cifras.** La base son las personas de Habitantes (los mismos filtros), vigentes y tratables:
sin fallecidas, sin las que ya no viven en Yondó y **sin quienes no autorizaron**; los eventos (acercamientos,
autorizaciones, asistencias, altas) son solo de personas de esa base, sin anulados ni los automáticos de las reuniones.
Registrar, llamar o reunirse con alguien que dijo «no» no cambia ninguna salida de ningún tipo (una prueba lo
comprueba con todos).

- **Población chica**: con menos de 10 personas la respuesta es exactamente `{"pocas": true, "personas": "<10"}`.
- **Celdas**: una de 1 a 4 personas sale «<5»; para que no se deduzca restando de los totales, se ocultan otras
  («oculta») hasta que ninguna «<5» se pueda calcular exacta (`analitica.fijadas`: la tabla se trata como un flujo y
  una celda se deduce si y solo si no hay un ciclo por ella en la red residual). Si ni así se protege, el desglose no
  se publica (`{"dispersas": true, …}`). Con dos dimensiones solo van personas y su parte.
- **Porcentajes**: un % de un grupo sale si el grupo tiene 10 o más personas y su numerador y su complemento no quedan
  de 1 a 4, protegido junto con los demás grupos; si no, `null`.
- **Series**: pasan de día a semana y a mes mientras queden puntos de 1 a 4; las tendencias usan solo lo visible.
- **Lo del equipo** (equipo, franjas, intentos, captura, picos) no es de habitantes y sale completo, siempre sin lo
  hecho con quienes no autorizaron; una tasa con menos de 20 intentos sale `null` por poco confiable.
- **Nada sensible**: nunca régimen de salud ni etiquetas sensibles; las altas importadas de una base van a
  «importación», nunca al usuario que importó.
- **Lo político, solo con el ajuste**: las dimensiones `tipo`, `lider` y `lista`, los filtros `tipo`, `lider_id`,
  `varios_lideres` y `sin_lider` (solo `true`), `lista`, y `fuente` con `cedulas`, `general` o `ambas` solo los acepta
  `politicos` (A o K con `agente_politicos` encendido para la vía de la petición: «mcp» por la sesión interna de MCP, el
  asistente si no); si no, 403 `permiso` («Los datos políticos (tipo de persona, líderes, listas y las bases de cédulas
  y general) no están habilitados para esta vía en Ajustes, o su rol no los usa: la analítica no cuenta por ellos.»), y
  un `lider_id` que no se puede usar (no autorizó, no lidera o no existe), 422. Las tres dimensiones son una
  **partición** (cada persona en un solo grupo), así se aplica la misma supresión exacta («<5», «oculta», `dispersas`),
  se cruzan con otra dimensión y sirven para `pct` y el embudo: `tipo` es la combinación de sus tipos («Líder y
  votante», «Sin tipo»…); `lider`, su único líder nombrable, `varios_lideres`, `lider_sin_nombre` (solo líderes que no
  autorizaron o ya no están activos: nunca se nombran) o `sin_lider`; `lista`, su única lista, `varias_listas` o
  `sin_lista`. Líderes y listas de menos de 10 personas van juntos en «otros_lideres» y «otras_listas», como los
  lugares, y la tabla por líder trae su `nota`. `fuente` como **dimensión** sigue sin resto ni total y sin las bases
  políticas, también con el ajuste (con ellas, el resto dejaría deducir un grupo chico). El catálogo muestra lo político
  solo con `politicos`, y `fuentes_filtro`. Los líderes nombrados en una tabla van en `Resultado.personas` (por MCP,
  solo a una clave con `lectura`).
- **Filtros**: como mucho 3, de una lista blanca, con edad y completitud en múltiplos de 5 y los días sin contacto de
  una lista fija. Fuera: búsqueda, ids, polígono, régimen de salud, consentimiento «no», reunión, creador, actualizador
  y situación; los políticos, solo con el ajuste (arriba).
- **Límite conocido**: dos consultas con filtros distintos que se restan entre sí no se pueden proteger sin guardar
  estado; por eso los filtros son pocos y gruesos, y las instrucciones le piden al asistente no combinar consultas para
  deducir una cifra oculta.

Las instrucciones del asistente (`sistema.py`, solo si tiene estas herramientas) le piden usarlas antes de opinar
sobre números, no calcular ni inventar cifras, decir que una cifra oculta se oculta para proteger a las personas sin
intentar deducirla, no describir el gráfico punto por punto, presentar los hallazgos del diagnóstico en su orden con su
enlace, y recordar que comparar y el efecto de las reuniones son asociaciones, no causas, y que lo del equipo es para
organizar y capacitar, no para sancionar. Con los datos políticos, que por tipo, líder o lista se analiza con la misma
supresión y lo sensible nunca; sin ellos, que lo político no se analiza.

## Registros de cada persona y calidad de datos

El asistente no solo busca, crea y edita fichas: también lee los registros de cada persona (`fichas.py`) y atiende las
colas de **Calidad de datos** (`calidad.py`), con la API del panel y la sesión de quien conversa, y toda escritura con
la tarjeta y la aprobación (las herramientas están en [Qué puede hacer](#qué-puede-hacer)).

**Lo que llega al modelo.** Las rutas de Calidad traen de más para el panel (las fuentes reales, listas, la cédula,
los teléfonos y el correo completos, la fila importada entera, la descripción de cada solicitud). Cada herramienta
vuelve a hacer su lista blanca, y una prueba por herramienta busca en su salida listas, fuentes, la base general,
sensibles y `evidencia_fila` (lo político, con el ajuste apagado; encendido, solo lo de abajo):

- **Coincidencias**: de cada ficha, nombre, cédula y teléfono enmascarados (sin teléfono si es menor), si tiene correo
  o dirección, barrio o vereda, sexo, edad, completitud y cuántos trámites; de cada par, solo la **clave** de cada señal
  (`mismo_telefono`, `misma_fuente`, `sexo_distinto`…), nunca su texto (una dice «la base general»). Los avisos se
  cambian por textos fijos sin nombres.
- **Conflictos**: motivo, estado, fecha, cédula enmascarada, las personas con `minimizar.fila`, la fuente solo si es
  trámites o planilla (si no, «otra_base»; con los [datos políticos](#datos-políticos), la real), de la fila solo
  nombre, sexo, edad, lugar, cuántos teléfonos y el número de fila, y de las dos cédulas escritas en la planilla solo
  si coinciden.
- **Autorizaciones**: estado, medio, canales, fecha, si tiene evidencia y si está confirmada; nunca las categorías
  sensibles autorizadas, la fila de la planilla, la evidencia escrita, la nota ni quién la registró.
- **Acercamientos**: fecha, canal, resultado, si fue efectivo, la nota con `texto_libre` y el id; nunca el teléfono, lo
  dictado ni quién lo registró.
- **Solicitudes**: nunca la persona, su nombre, la descripción ni la respuesta (que alguien pidió suprimir sus datos es
  un dato suyo). La tarjeta de `actualizar_solicitud` sí la muestra a la persona del equipo y la anota en la
  conversación.
- **Importaciones**: nada de la base con cédula ni de la base general (ni el archivo ni los conteos: revelan el tamaño
  de una base política), salvo con los datos políticos encendidos: entonces salen con su tipo, su archivo y sus conteos
  (`lideres_asignados`, `lideres_sin_resolver`, `tipos_marcados`, `registros_por_fuente`).
- **Tarjetas**: anotan en `Confirmacion.personas` a toda persona que muestran (el par de un duplicado, los miembros de
  un grupo, las del conflicto, el titular de la solicitud): si alguna se suprime o dice «no», se borra la conversación
  (o la propuesta por MCP). La vista previa de una unión enmascara la cédula, los teléfonos y el correo.

**Una sola escritura.** Solo `POST /api/personas/{pid}/duplicado` respeta la `Idempotency-Key`; en las demás se vuelve a
leer y no se escribe lo que ya quedó como se pidió. Las huellas protegen lo que mostró la tarjeta: `estado_telefono`
guarda la del número (HMAC) y al aprobar lo busca en la ficha recién leída; `editar_reunion`, las de los valores de
antes (si alguien los cambió, 409 `cambiada`); `resolver_coincidencias`, la del estado de cada grupo y la ficha que se
conserva: si el grupo cambió, no se une, y sin tarjeta no se une nada.

**Alias de lugares.** `POST /api/lugares/{lid}/alias` `{alias}` (A y K): agrega con `$addToSet` (sin la carrera de leer,
cambiar y escribir la lista), audita `agregar_alias` solo si es nuevo, sube la versión de los catálogos y vuelve a
ubicar solo a las personas activas sin barrio o vereda cuyo lugar escrito contiene el alias, no a toda la base.
Idempotente; 409 `ambiguo` si ya es el nombre o un alias de otro lugar.

## La presentación técnica

La vista **Presentación**, la pantalla en off y los agentes por MCP muestran la **presentación técnica** de la propuesta
(`web/propuesta.html?modo=tecnica`): lo que se construye, dónde, cómo funciona y cómo se mide, **sin costos ni
financiación** (esos quedan en la propuesta para la gestión, `web/propuesta.html` sin `modo`, la del Home). **Solo
existe dentro del panel, con sesión**: la técnica se arma únicamente enmarcada (y el sitio solo deja que lo enmarque el
propio panel, `frame-ancestors`); abierta sola en el sitio público, con o sin `?modo=tecnica`, es la propuesta pública,
sin la capa visual ni el mando. Y solo la manejan quienes entraron: el asistente vive en el panel, la pantalla en off
pide la sesión (`presentacion.ver`) y un agente por MCP, la clave que la persona crea en **Mi cuenta**. Es la misma
maqueta 3D del territorio real, con lo que se agrega para presentar cada detalle visual y técnico:

- **Capítulos.** La portada técnica, los siete módulos y el **cronograma de obra** (cada componente con su barra de
  2027 a 2032, según el plazo de su ficha). Cada módulo con sus pasos sin el de financiación, las **inmersiones** en los
  modelos del atlas detrás del paso que dicen y un paso de **metas** (línea base y meta de cada indicador). Los arma
  `web/js/propuesta/tecnica.js` y el guion del asistente (`app/agente/guion.py`), con las mismas reglas; una prueba con
  Node los compara.
- **Sin plata.** De cada texto se quita lo que tiene plata (un paréntesis con «$», la frase que la lleve y, en una
  especificación, el tramo entre «·» o «;»); una cifra en pesos o en millones y una especificación de costo, valor,
  precio, subsidio, tope, presupuesto, financiación, crédito, aporte o tarifa no se muestran. El guion tampoco las trae.
- **El panel.** La hoja de especificaciones de cada obra, su proyecto tipo o referente, dónde y el plazo con su barra;
  el render del área en la portadilla y en el telón de cada módulo; las fichas técnicas para imprimir. Arriba a la
  derecha, la brújula y la escala (en pantalla grande) y el estado: **Con el proyecto** u **Hoy**.
- **Inmersiones.** Un modelo del atlas en una ventana sobre la maqueta (`atlas.html?escenario=1`, `web/js/escenario.js`):
  la torre del hospital en su sitio, el predio hoy, los pisos por servicio, el recorrido por dentro, el laboratorio, el
  simulador sísmico y el modelo BIM, y el relleno Las Américas hoy y con el parque ecotecnológico. El catálogo está en
  `data/propuesta/general.json` (`tecnica.inmersiones`) y build_propuesta.py revisa que cada modo exista en el atlas.
  En ese modo la torre se muestra sin sus paneles ni la conexión a la microrred de sedes: su energía viene de la granja
  solar centralizada. El modelo BIM todavía trae los paneles de su diseño (el ajuste está pendiente, `docs/16`).
- **`visual`** (la orden de `mando.js` y la operación de la herramienta), sin cambiar de paso y combinable en una sola
  llamada: `enfoque` (la cámara va a un componente: al paso que lo desarrolla, a sus sitios o trazados de `geo.json` o
  a la réplica de una sede, según el `enfoque` que build_propuesta.py le calcula a cada componente; `paso` vuelve),
  `detalle` (su ficha técnica a un lado; `cerrar`), `comparar` (`hoy`: el sitio como está, sin las capas del proyecto y
  con las casas y sedes de hoy, en el mismo encuadre; `proyecto`), `camara` (`paso`, `aerea`, `oblicua`, `rasante`,
  `cerca`, `lejos`), `rumbo` (desde dónde se mira, en grados desde el norte: 180 deja el norte arriba), `girar`,
  `inmersion` (un modelo del catálogo; `maqueta` lo cierra en un paso de inmersión; `paso`, lo del paso) y `tema`
  (`claro` u `oscuro`). Los componentes y las inmersiones se piden por id o por nombre y se resuelven contra el guion;
  lo que no existe (o un componente sin lugar en la maqueta, para `enfoque`) no mueve nada y vuelve con los candidatos.
- **La cámara libre y las piezas de la maqueta** (lo que suma el plan guiado, en `visual` y en cada paso de un plan):
  `elevacion` (grados sobre el horizonte, de 8 a 85) y `zoom` (de 0,3 a 3: 1 es el encuadre del paso; 2, el doble de
  cerca), que con valor mandan sobre lo que implique `camara` (los seis encuadres con nombre quedan como alias);
  `mirar` (a qué apunta la cámara **sin cambiar lo que se ve**: una pieza de la maqueta o un componente con lugar;
  `paso` vuelve); `mostrar` y `ocultar` (piezas de la maqueta que se ven además de las del paso, o que se ocultan
  aunque el paso las muestre: hasta 8 cada una), `aislar` (solo esa pieza: el resto del capítulo se apaga o queda en
  gris; `nada` lo quita) y `sin` (partes que se le quitan a una pieza, como `pieza.parte`: `torre.cubierta` deja ver las
  losas; `[]` las devuelve). Todo vuelve a lo del paso al cambiar de paso. Y tres **acciones que no son estado**:
  `mover` (`{giro, zoom, elevacion}`: la cámara gira esos grados alrededor de lo que mira y termina con ese
  acercamiento y esa elevación; en un plan dura lo que dura la frase, suelta dura unos segundos), `animar` (repite la
  animación propia del paso: la obra crece) y `simular` ([las simulaciones del atlas](#las-simulaciones-del-atlas) o,
  sin un modelo del atlas a la vista, [las de la maqueta](#las-simulaciones-de-la-maqueta)). La pantalla las hace una
  vez: no quedan guardadas como lo que se ve.
- **El catálogo de piezas** está en `data/propuesta/general.json` (`tecnica.maqueta`: por capítulo, cada pieza con su
  id, su nombre, las capas que enciende y las partes que se le pueden quitar; cuando la pieza es un componente del
  capítulo lleva su mismo id). build_propuesta.py lo copia a `web/data/propuesta.json` y lo revisa; la presentación lo
  lee de ahí y el guion del asistente (`app/agente/guion.py`) solo se queda con los ids y los nombres: el modelo conoce
  «la torre» y «su cubierta», no capas ni nodos. Se piden por id o por nombre (sin tildes ni mayúsculas).

### Pantalla completa en la pestaña

**Pantalla completa** en la barra de la vista hace que la presentación ocupe toda la pantalla, sin el menú ni las barras
del panel (ni la franja «Llamada sin registrar», que sigue pendiente y vuelve al salir), y el asistente sigue a la vista
y a mano. Antes la pantalla completa del navegador era solo la del marco de la presentación y el asistente quedaba
fuera; ahora el navegador la da con la página entera, y si no la da (el iPhone, un permiso) la presentación llena igual
la ventana.

- **Dónde va el asistente.** Su botón flota abajo a la izquierda (arriba a la derecha están las herramientas de la
  presentación y abajo al centro su control) y, a su lado, **Salir de pantalla completa**; en el celular, los dos en la
  barra de arriba de la presentación, junto a su marca. Tras 3 segundos sin mover el ratón ni tocar se atenúan, como en
  el proyector, y vuelven al moverlo o tocar.
- **El celular de lado.** Ahí la barra de la vista no se ve (le quitaba alto a la presentación) y el botón de pantalla
  completa de la presentación tampoco: **Pantalla completa** pasa a la barra de arriba del panel, como un ícono a la
  izquierda del botón del asistente. Un toque saca esa barra y la presentación ocupa toda la pantalla.
- **Abierto.** En escritorio es una columna a la derecha sobre el fondo negro de la presentación, que le deja su ancho,
  con «Salir de pantalla completa» encima; en el celular se superpone. Escribir, preguntar por voz y oír las respuestas
  y el plan narrado siguen igual.
- **Salir.** Con ese botón, saliendo de la del navegador o con Escape. Con la pantalla completa del navegador, Escape es
  del navegador y sale de una vez, aunque el chat esté abierto (la página no lo ve). Sin ella (llena por la orden del
  asistente, o porque el navegador no la dio), con el chat abierto el primer Escape es del chat (calla lo que se lee o
  lo cierra), también con el foco en la presentación, y el siguiente sale. El botón de pantalla completa de la propia
  presentación y su tecla F hacen lo mismo que el de la barra, o salen; si el navegador no la dio, salen en vez de
  pedirla otra vez. La F no hace nada con las fichas de la presentación abiertas (ahí ella tampoco la usa). Todo esto
  con el panel y el sitio en el mismo servidor; con el sitio aparte, su botón pone a pantalla completa solo el marco,
  como antes.
- **El asistente.** «Ponla en pantalla completa» llena la ventana igual; la pantalla completa del navegador, solo si la
  persona acaba de tocar la pantalla (sin eso el navegador la rechaza), y «quita la pantalla completa» sale de las dos.

### Las simulaciones del atlas

El asistente y los agentes por MCP también **manejan los controles de adentro de un modelo del atlas** abierto como
inmersión, como los maneja una persona: en el simulador sísmico, la magnitud, el escenario, la profundidad, la
distancia, el suelo, la escala, el instante, la velocidad, la exageración, qué colorea, los equipos sobre la losa…,
**Calcular**, **Hacer temblar la torre** (reproducir) y **Cancelar**; en «Pisos por servicio», el piso; en el
recorrido y el laboratorio, el nivel, subir y bajar, el mapa, el espectador y las capas; en el modelo BIM, la
herramienta, la vista, cada disciplina, los cortes, la cimentación, construir en 4D y su fecha; en la torre en su
sitio, el proyecto tipo. El parque no tiene controles. Nada que enseñe plata: el coloreado por presupuesto (5D) y la
pestaña de costos del BIM no están en el catálogo, `build_propuesta.py` avisa (y con `--estricto` falla) si un control
o una opción habla de costos, presupuesto o valor, y en el atlas enmarcado el BIM no escribe cifras en pesos.

- **El catálogo** está en `data/propuesta/simulaciones.json` (`{inmersión: [control…]}`): cada control con su `id`, su
  `nombre`, su `tipo` (`accion`, `numero`, `opcion` o `si_no`), el rango, el paso y la unidad de un número, las
  opciones (`{id, nombre}`) y una frase de `ayuda`. `scripts/build_propuesta.py` lo revisa (también que el atlas sepa
  accionar cada control) y lo copia a cada inmersión de `tecnica.inmersiones` como `controles`; `--estricto` lo lleva al
  guion del asistente (`app/agente/guion.py`: `Guion.controles` y `Guion.control`, por id o por nombre). El modelo los
  ve en `indice` (los ids), en `guion` (enteros, los de las inmersiones que muestran los pasos del capítulo; si el
  capítulo pesa demasiado, primero sin la ayuda de los controles de los modelos del atlas, después sin los
  referentes de las fichas y, solo si aún no cabe, sin sus descripciones: `recortado` dice qué se quitó), al ir a un paso de
  inmersión y al abrir un modelo con `visual`.
- **`simular`**: de 1 a 4 `{control, valor}` en orden (sin `valor` para una acción; en un número, uno de su rango; en
  una opción, su id o su nombre; en sí o no, `true` o `false`, y sin valor es sí). Va en un **paso del plan** (junto a
  `mover`, `animar` y `resaltar`) y en la op **`visual`** suelta. Es una acción, no estado: se aplica cuando llega,
  sobre el modelo que queda abierto en ese paso (el que abre `inmersion`, el que había o el del paso de inmersión; de
  otro capítulo que el de la pantalla, solo el que abre la misma orden). Cambiar un valor no recalcula, igual que en la
  página: el plan manda después `calcular`; al terminar un cálculo pedido la torre tiembla sola, también en un
  proyector con movimiento reducido (en el escenario lo pidió quien presenta), y la primera vez que se reproduce un
  resultado arranca desde el comienzo, no desde el pico. El primer cálculo, al entrar, no tiembla solo: ahí,
  `reproducir` con `true`.
- **Tolerante, con avisos legibles.** El servidor resuelve cada control por id o por nombre contra los del modelo que
  queda abierto; un número fuera de su rango se recorta y se ajusta a su paso («simular «profundidad» 900 quedó en 200
  (va de 5 a 200 km)»); un control que no existe, un valor que no sirve, un paso sin modelo del atlas o uno sin
  controles se descartan con su aviso y los controles que sí hay; de más de 4, quedan los primeros. La escena absoluta
  lleva `simular` (None o la lista exacta); una de antes, o de la presentación automática, no lo trae y vale igual. En
  la op `visual`, si la simulación era lo único y no queda nada, es un error con los controles del modelo.
- **En la pantalla.** La pantalla en off guarda la lista como `mover` (`pantalla.ACCIONES`: una vez por versión nueva,
  nunca al abrir o recargar). La API anota la última versión que le entregó a la pantalla (`entregada_v`; un latido,
  `?latido=1`, no cuenta): mientras la pantalla no reciba una orden con acciones, la siguiente las junta con las
  pendientes en vez de pisarlas (`simular` se suma detrás si el modelo no cambia y caben 4; si no caben, la orden
  espera hasta 3 s a que la pantalla pregunte), así dos llamadas seguidas o en paralelo por MCP se hacen las dos. Un
  cambio de paso, otra orden ya recibida o encender o apagar la automática las dejan en nada. Mientras corre un cálculo
  del sismo, «reproducir» y «instante» esperan su resultado; en el BIM, los controles esperan a que cargue el modelo 3D.
  La op `visual` suelta acepta además el `paso` de partida (el del contexto del panel), para saber qué modelo está
  abierto en la pestaña; con la pantalla en off o por MCP tiene que ser el de la pantalla. El puente (`agente-presentacion.js`) la valida en
  el plan, en la acción `visual` y en el estado de la pantalla en off; el reproductor la manda en la orden `escena`; la
  presentación (`mando.js`) la revisa y `visual.js` la pasa al marco del atlas con `__escenario.simular`
  (`web/js/escenario.js`), que acciona el control de la página como la persona y espera hasta 25 s a que aparezca o se
  habilite. Sin un sismo calculado ni un cálculo en curso (se canceló, o el de entrada falló) no espera en silencio:
  `reproducir` con `true` pulsa antes **Calcular** (responde en cuanto el cálculo arranca y el resultado tiembla solo
  al llegar) y el instante responde enseguida que hace falta calcular. La escena acciona cuando el modelo ya cargó y espera las respuestas a
  lo sumo 2 s: lo que el atlas rechaza en ese tiempo vuelve como descartado (el aviso `parcial`); lo que sigue
  esperando se acciona solo después. Si la escena se vuelve a aplicar (repetir, o seguir después de que la persona
  movió la imagen), la simulación se acciona otra vez. En la presentación, el simulador muestra en su barra el sismo
  puesto («Mw 7,0 · 150 km de profundidad · calculando 40 %»): la sala ve lo que cambió el asistente. Con una narración
  o una explicación a la vista, la ventana del modelo termina encima del subtítulo, que ya no tapa la barra de tiempo.

### Las simulaciones de la maqueta

Sin un modelo del atlas a la vista, **`simular` maneja la maqueta 3D**, con la misma forma, los mismos topes y la misma
tolerancia: la **hora del día** (`hora`: `manana`, `tarde`, `atardecer` o `noche`; el sol, el cielo, la luz y las
sombras, y al atardecer y de noche las ventanas y las luminarias que haya), **el día entero** (`reproducir_dia`:
`true` lleva el sol de la mañana a la noche en 24 s de reloj, aunque la pantalla dibuje pocos cuadros; `false` lo pausa
donde va y otro `true` sigue desde ahí), en Vivienda y Urbanismo (los capítulos con luminarias) **las luces** (`luces`:
las torres LED del estadio, los postes y los bolardos con su luz en el piso; sin pedirlas, siguen la hora) y, solo en
Urbanismo, **un partido** en la Cancha de Sóftbol Casabe (`partido`: lanzamiento, elevado, doble y relevo, que se
repite; solo con la cancha en el encuadre en que queda la cámara: no en la portadilla ni en el mirador, que la ocultan,
ni en las canchas cubiertas junto al CIC, que encuadran otra cosa).

- **El catálogo** es la clave reservada `maqueta` de `data/propuesta/simulaciones.json`, con la forma de los controles
  del atlas y, solo ahí, `capitulos` (en qué capítulos vale un control; sin la clave, en todos). `build_propuesta.py`
  lo revisa (también que `web/js/propuesta/simulacion.js` sepa accionar cada control y que las horas sean las de
  `ambiente.js`) y lo copia a `tecnica.simulaciones_maqueta`; el guion lo lleva aparte de las inmersiones (`maqueta`,
  «La maqueta 3D»: `Guion.controles("maqueta", capítulo)`). El modelo lo ve en `indice` y `guion` por capítulo
  (`controles_maqueta`) y al ir a un paso sin modelo del atlas.
- **Dónde acciona** (`recorrido.simulable_en`): en el modelo del atlas que queda abierto o, sin él, en la maqueta (un
  paso que se sabe, la maqueta pedida o un capítulo sin modelos del atlas). Si todo lo que se pide es de un modelo del
  atlas (`calcular`, `reproducir`), el aviso de siempre («ahí no hay uno») con lo que tiene la maqueta; el partido
  fuera de Urbanismo dice dónde está.
- **En la pantalla** la acciona `simulacion.js` (`visual.js` la usa cuando no hay una inmersión vigente), con la misma
  regla del valor que el atlas (`validar` de `escenario.js`). Lo que no se puede (el partido con la cancha oculta o
  fuera del encuadre) vuelve como descartado; el partido espera hasta 8 s a que se arme su capítulo. Como lo demás de
  `visual`, **vuelve a lo del paso al cambiar de paso** (un `ir` al mismo paso no la toca: la pantalla en off solo
  recibe de él lo visual que cambió; el botón del tema devuelve la hora, no las luces ni el partido): un plan la repite
  en el paso siguiente si debe seguir. El estado de la presentación trae lo que se ve en `visual.simulacion`
  (`{hora, dia, luces, partido}`).

### Cómo habla: la voz de la presentación

Lo que oye la sala (los pasos del plan, la explicación suelta, la respuesta inmediata, las respuestas habladas y lo que
el asistente responde sobre la propuesta) se le dice a la comunidad, no a ingenieros: tiene que entenderse a la
primera. Las reglas están en un solo lugar, `app/agente/lenguaje.py`, y van a todos los que escriben lo que se dice.

- **Sencillo y cercano**, como en una reunión del barrio o de la vereda: frases cortas, palabras de todos los días,
  una idea por frase. **Explica cada parte**: qué es, para qué sirve y a quién le sirve, antes que los detalles, con
  pocas cifras y las unidades dichas enteras (metros cuadrados, hectáreas, litros por segundo).
- **Sin siglas ni tecnicismos**: el nombre completo («la planta de tratamiento de aguas residuales», no «la PTAR») y lo
  que hace la cosa en vez de la palabra técnica («la torre aguanta un terremoto y sigue atendiendo», no «edificación
  indispensable del grupo de uso IV»). El guion trae siglas porque sale de documentos técnicos: por eso cada capítulo
  le llega al modelo con su glosario (`siglas`: el nombre completo y qué es cada una, de `lenguaje.SIGLAS`, solo las
  que trae ese capítulo; `ir` trae las del paso y las de lo que se puede pedir en él: las piezas y los controles). Una prueba (`tests/test_lenguaje.py`) falla si una sigla nueva del
  guion no está explicada en el glosario.
- **Con el léxico del candidato**: la primera persona del plural de la propuesta y la comunidad («le apostamos a…»,
  «que podamos…», «juntos»), un «¿sí?» de vez en cuando para ver si la sala va entendiendo, «el casco urbano»
  completo, «recursos económicos» y no «plata», «empleo» y no «trabajo» cuando se habla de puestos de empleo
  («trabajo de parto» y «¡Trabajemos juntos!» no cambian). Los nombres van como los conoce la gente y sin variantes
  (Yondó, el hospital Héctor Abad Gómez, la ruta chelera, la 15, la cancha de sóftbol, el parque principal, la Casa de
  la Cultura, la iglesia, el centro agroindustrial, la planta de tratamiento de aguas residuales, vivienda joven), solo
  donde el guion habla de ellos. No se nombran los puestos de salud, el malecón, el muelle flotante ni la pasarela:
  salieron de la propuesta (`lenguaje.RETIRADO`, que también va en `EN_CORTO`, así llega a los agentes por MCP).
- **Cambian las palabras, no los datos**: cifras, nombres y plazos siguen saliendo solo del guion, sin ideas, promesas
  ni datos nuevos, y nunca en primera persona del singular ni con citas del candidato (la voz puede ser la clonada).
- **Dónde va.** Enteras (`COMO_SE_EXPLICA`) en las instrucciones del redactor del [plan en flujo](#el-plan-en-flujo) y
  en las del asistente cuando tiene la presentación; en una frase (`EN_CORTO`) en la respuesta inmediata, las
  respuestas habladas, la nota de `guion` y de `ir`, la descripción de la herramienta y las instrucciones del servidor
  MCP. La [presentación automática](#presentación-automática), que no usa el modelo, dice frases escritas a mano con
  estas mismas reglas.

### El plan guiado (recorridos narrados)

Para explicar algo (una obra, un capítulo, «muéstrame el hospital»), el asistente no encadena órdenes sueltas ni lo
cuenta en el chat: **hace un plan primero y la pantalla lo ejecuta paso a paso, mostrando mientras explica**. Lee el
guion del capítulo (`guion`) y arma, en **una sola llamada** (`recorrido`), un plan de 6 a 10 **pasos** (12 a lo sumo).
Cada paso es **una frase** (`dice`: se proyecta en el subtítulo y se lee en voz alta; hasta 220 caracteres) y **lo que
ocurre en pantalla mientras se dice**: el paso del capítulo, la cámara (un encuadre con nombre, su rumbo, su elevación,
su acercamiento, a qué apunta y cómo viaja durante la frase), las piezas de la maqueta que se muestran, se ocultan o se
aíslan y las partes que se les quitan, la obra enfocada, su ficha, hoy o con el proyecto, un modelo del atlas, «Solo
3D», la animación del paso, los controles de la simulación del modelo del atlas (`simular`: la magnitud del simulador
sísmico, calcular, hacerlo temblar) y lo que se resalta (una cifra, un punto, una entrada de la leyenda, una
especificación o un componente). Al final, un cierre «En resumen» de uno a tres puntos y, en el chat, sugerencias para seguir. En el
chat el asistente escribe **antes** una línea que anuncia el plan y **después** solo una pregunta corta: la explicación
es la narración, no se repite.

Es el recorrido narrado de antes, que sigue (el reproductor, la tarjeta, la pantalla en off, el proyector, los
controles), con tres cambios. Hacia el modelo y la persona se llama «plan» y «pasos»; por dentro siguen `recorrido` y
`escenas` (y la herramienta todavía acepta `escenas` y `narracion`, los nombres de antes).

- **Mostrar mientras explica.** Antes la escena aplicaba todo, esperaba a que la imagen se asentara (de 2 a 4 segundos
  de movimiento mudo; hasta 10 con un modelo del atlas) y recién entonces narraba, con la imagen quieta. Ahora la
  narración aparece en el acto y la cámara, las piezas, la ficha y hoy o con el proyecto cambian **durante** la frase:
  la cámara viaja lo que dura la narración del paso. Lo único que se espera es la carga de un modelo del atlas. Y la
  imagen nunca queda quieta: un paso que no le pide nada a la cámara (el mismo paso del capítulo, el mismo encuadre y
  sin `mover`) recibe un movimiento suave (gira de 10 a 14 grados, alternando el sentido, y se acerca un poco); no
  dentro de un modelo del atlas ni con la cámara girando sola. La cámara **sigue desde donde la dejó el paso
  anterior** mientras ningún paso cambie la cámara pedida: un giro tras otro se suman, y el movimiento suave que viene
  después de un `mover` solo gira. La pausa también detiene el viaje de la cámara y al seguir lo retoma; detener lo
  corta. Los controles de la tarjeta valen desde «Plan listo»: «Siguiente» empieza ya y «Detener» evita que el
  primer paso se aplique.
- **Manipular la maqueta.** Además de los seis encuadres, el asistente maneja la elevación, el acercamiento, a qué
  apunta la cámara y su viaje (`mover`), y las piezas del [catálogo de la maqueta](#la-presentación-técnica) de cada
  capítulo: aislar una obra, mostrar u ocultar otras, quitarle partes («la torre sin la cubierta»), repetir la
  animación del paso.
- **Tolerante.** El servidor (`app/agente/herramientas/interfaz.py`, `_componer`) resuelve cada paso contra el guion
  heredando lo del anterior (los nombres e ids de pasos, componentes, piezas, partes e inmersiones, y lo que se
  resalta, contra lo que muestra ese paso) y deja el plan **absoluto**: cada escena trae lo visual completo (una que
  repite el capítulo sin decir el paso sigue en el mismo paso), su `mover`, su `animar` y su `simular`. Lo opcional que
  no resuelve (una pieza mal escrita, una parte que no existe, un componente sin lugar, un modelo que no está, un
  control de la simulación que no existe, un resaltado imposible, el capítulo o el paso de un paso que no es el primero, un valor sin la forma o una clave que no existe)
  **se descarta**, y un número fuera de su rango **se recorta**; cada cosa deja un aviso legible con el número del
  paso y los candidatos («Paso 3: la pieza «tore» no está en Salud (aislar); piezas: hospital_hoy, torre, telesalud,
  territorios») y el plan corre con lo demás. La presentación hace lo mismo con lo que le llega (el aviso `parcial`:
  «parte de lo pedido no se pudo mostrar»). Solo es un error, y entonces no se guarda nada: que el primer paso no
  tenga un capítulo que resuelva, que un texto no se pueda proyectar (con el número del paso), más de 12 pasos o un
  plan que pasa de la duración máxima.
- **Lo que se proyecta no se relaja.** Las frases, el título y el cierre siguen las reglas de la explicación: sin
  datos de personas, **sin costos**, sin «@» ni números de 7 o más dígitos. La duración estimada (la espera inicial,
  la lectura de cada frase, lo que se sostiene, el cierre) no pasa de 5 minutos.
- **Quién lleva el reloj.** Lo reproduce el panel (`web/js/reproductor.js`), no el modelo: en la pestaña del chat, en
  la ventana del proyector o en la pantalla en off, donde mire la sala. Un plan nuevo espera 1,8 segundos antes del
  primer paso (el chat muestra el plan entero: «Plan listo: empieza enseguida»), y más si en esa ventana suena la
  [respuesta inmediata](#la-respuesta-inmediata): hasta que termine, como mucho 15 segundos. Por cada paso manda a la
  presentación la orden `escena` con lo que durará su narración: la presentación cambia de paso sin telón, pinta la
  narración, empieza a mover la cámara y las piezas y responde enseguida. Después de un respiro, cada frase se ilumina
  en el subtítulo cuando empieza a sonar (o cuando aparece, sin voz) y se queda su tiempo de lectura; después la imagen
  se sostiene un momento (1,3 segundos; 2,7 si hay algo que mirar). El subtítulo dice el título del plan y en qué paso
  va (puntos, sin números).
- **La voz.** La del navegador (Web Speech, `web/js/voz.js`), en español (es-CO primero; después es-419, es-MX, es-US,
  es-ES), con las siglas y unidades dichas como se leen (NSR-10, m², «24 h»); o, si el administrador la eligió y el
  rol de la persona la usa, la [voz clonada de Mnemo](#la-voz-clonada-de-mnemo) (`web/js/voz-clonada.js`): pide cada
  frase por su referencia en el plan guardado (`{rid, n, frase}`, y el resumen `{rid, cierre: true}`), precarga la que
  sigue (y la primera durante la espera de un plan nuevo) y, si una no suena en 4 segundos, la dice con la del
  navegador sin que el reproductor se entere. Un plan escrito por un agente externo por MCP se narra siempre con la del
  navegador. El plan de la [presentación automática](#presentación-automática) usa la clonada solo si Ajustes lo deja
  (**Narrar también la presentación automática**); si no, va con la del navegador y el botón **Voz** y el avance dicen
  el estado de esa (sin voces en español, se lee en silencio, sin el aviso «la voz no pudo hablar»). El título del
  botón **Voz** dice cuál habla. **Encendida por omisión**; si la persona
  la apagó, esa preferencia se respeta (queda en ese navegador). El navegador solo deja hablar a una página que
  alguien tocó: en la pestaña del chat, enviar el mensaje ya es ese gesto; en el proyector o la pantalla en off, la
  activan tocar el panel de texto, una tecla, el control de la presentación o el botón **Voz** de esa ventana (tocar
  la maqueta 3D, también a través del subtítulo, es tomar la cámara: pausa el plan). La tarjeta del chat tiene un
  interruptor de voz para la vista de esa pestaña; si suena en otra ventana, dice dónde encenderla. Sin voz, sin voces
  en español o si falla, cada frase se lee en pantalla con el mismo ritmo.
- **Manejarlo.** La tarjeta del chat es el plan: «Plan · título», los pasos numerados (dónde, lo que hace cada uno y
  su frase), el paso en curso marcado y abierto con su frase resaltada mientras suena, el avance en vivo y los
  controles: Pausa/Continuar, Anterior, Siguiente, Repetir y Detener; al terminar, **Volver a reproducir** y las
  sugerencias como botones. Volver a reproducir (y `control_recorrido` reproducir del asistente) pasa por el
  servidor: lo registra con un id nuevo y la tarjeta sigue a ese; solo se puede con el último plan (con la
  [presentación automática](#presentación-automática) encendida, también con el último que ella reemplazó al
  seguir). Cada plan se guarda con la huella de los capítulos que recorre (`Guion.huella`): si uno cambió después
  (un paso nuevo corre los números, cambia un texto o una pieza), el plan ya no vale y no se vuelve a reproducir,
  porque sus frases hablarían de otro paso (`pantalla.huella_vigente`; los guardados antes de la huella valen si
  pasan `recorrido.validar`). Mientras suena,
  una barra fija arriba de la conversación lo deja a mano. En la presentación, las flechas, la barra espaciadora y los
  botones de su control pasan de paso, P pausa y Escape detiene. Si la persona mueve la maqueta o cambia de paso a
  mano, se pausa; al seguir, el paso vuelve. Si escribe en el chat, se pausa al terminar la frase. Cualquier otra
  orden de la presentación que valga lo detiene y la imagen queda donde iba, sin el movimiento ni la animación de ese
  paso, que no son estado (una orden que no vale, como un capítulo o un componente que no existe, vuelve con su error
  y la narración sigue). Si sonaba en la pestaña o el proyector, el servidor manda detenerlo allá también cuando la
  orden va a la pantalla en off, y lo mismo cuando el asistente arma otro plan que va a la pantalla en off; la tarjeta
  dice que se detuvo porque el asistente mostró otra cosa. Un plan nuevo en el mismo lugar reemplaza al que sonaba.
- **Dónde suena.** Sin pantalla en off abierta, en la vista Presentación de la pestaña del chat o, si hay una, en la
  ventana del proyector (la tarjeta sigue su avance por el canal del proyector). Si el proyector se abre a mitad del
  plan, este pasa allá desde el paso en curso; si se cierra, la tarjeta ofrece **Reanudar** desde ese paso (sigue en
  la pestaña con el mismo id, si todavía es el último plan y no se cerró, y si no suena otro). Con la pantalla en off
  abierta (y siempre por MCP), suena allá: la tarjeta pregunta por su avance y, si la pantalla deja de dar noticias
  (sonando, sin avances en un minuto; en pausa o no, si ya no pregunta por su estado), lo da por detenido. Una pausa
  larga se sigue preguntando, más despacio.
- **El avance.** El reproductor le avisa al servidor cada fase (`POST /api/pantalla/progreso`): el contexto del
  asistente («Plan «…» en la pestaña o el proyector: paso 3 de 8 del plan, narrando») y la op `estado` dicen por qué
  paso va, si está en pausa y los avisos (el modelo del atlas no cargó, no encontró lo que resaltar, parte de lo
  pedido no se pudo mostrar), y describen lo que muestra el paso en curso, de donde parte también la próxima orden.
  Así puede seguir desde ahí, controlarlo o responder sobre lo que la sala está viendo. Un avance final (terminó, se
  detuvo o falló) lo cierra en el servidor, con la imagen donde quedó; el traspaso de la pestaña al proyector no. Un
  avance de un plan que el servidor ya cerró o reemplazó responde 409 y la página lo detiene. El contexto lo nombra
  dos minutos después de terminar y deja de nombrarlo si en media hora no llega ningún avance ni control (la página
  que lo reproducía se cerró); en pausa con la pantalla en off abierta, lo sigue nombrando.
- **Lo que quedó guardado de antes.** Un recorrido guardado antes del plan guiado (sus escenas sin `mover`, `animar`
  ni `simular`, lo visual con siete partes) se lee con lo que le falta en lo del paso (`recorrido.al_dia`): se puede
  cerrar, reanudar y volver a reproducir.
- **Con personas en la conversación**, la presentación no proyecta texto (`explicar`, `ir` con explicación ni
  `recorrido`): responde `con_personas`. Se muestra en una conversación sin datos de habitantes.
- **El presentador.** Mientras el plan suena (y con una explicación suelta), una caricatura en 3D del candidato se
  para sobre el subtítulo y lo explica: saluda en el primer paso, señala lo que se resalta o presenta la obra, mueve
  la boca mientras la voz dice cada frase (la vista le avisa con `narracion {habla}` cuándo empieza y termina), escucha
  en pausa, cuenta con los dedos el resumen, abre los brazos en «¿Preguntas?», piensa mientras el asistente prepara y
  se despide al quitarse la narración. Cada paso del plan puede pedirle un gesto (`gesto`: saludar, senalar, presentar,
  mostrar_panel, mirar_maqueta, explicar, destacar, comparar, enumerar, crecer, grande, detalle, construir, pensar,
  preguntar, asentir, negar, calmar, aprobar, celebrar, aplaudir, juntos, corazon, invitar o despedirse; la lista, con
  lo que expresa cada uno, le llega al modelo con el guion). Uno que no existe se descarta con un aviso; sin `gesto`,
  el presentador elige solo con lo que el mando sabe de la escena. El botón **Presentador** de la barra (también en el proyector y en la pantalla en off) lo oculta o
  lo muestra en ese navegador. Detalles en [`docs/presentador.md`](../../docs/presentador.md).

### El plan en flujo

Armar un plan a mano era lo que más hacía esperar: el modelo pedía el guion del capítulo (una ronda), lo leía entero
(de 6.000 a 11.000 tokens), razonaba y escribía el plan completo dentro de la llamada `recorrido`, y con Mnemo esa
llamada no llega por partes: la sala esperaba en silencio de 40 segundos a más de un minuto antes del primer paso (el
diagnóstico, con medidas, en [`velocidad.md`](velocidad.md)). Con el **plan en flujo** la sala ve y oye el primer paso a
los pocos segundos y el resto se escribe mientras se narra (`app/agente/redactor.py`).

- **Cómo lo pide el asistente.** `presentacion` op `plan` con el `capitulo` y un `encargo` (qué mostrar y contar, de una
  a tres frases, con lo que pidió la persona) y, si es una pregunta puntual, `largo` `corto` (de 3 a 5 pasos; si no, de
  6 a 10; con la presentación automática encendida, corto por omisión). No pide el guion: no lo necesita, y la
  conversación no lo carga en las rondas siguientes. Antes de la llamada escribe la línea que anuncia el plan y
  después nada: el turno termina con el plan (`Resultado.termina_turno`), sin la ronda de la «pregunta corta», y la
  tarjeta trae las sugerencias. `guion` y `recorrido` siguen para un plan de varios capítulos y si `plan` falla.
- **Quién lo escribe.** El mismo proveedor de la conversación (Mnemo o el modo directo), en una petición aparte sin
  herramientas y sin razonar (o lo mínimo: `Proveedor.generar(..., rapido=True)`; en modo directo, con el modelo de
  `AGENTE_MODELO_ADELANTO` si se eligió uno), con instrucciones fijas y el guion del capítulo en el `system` (el mismo
  texto para el mismo capítulo: el proveedor lo saca de su caché la próxima vez) y el encargo en el mensaje. Escribe en
  **JSON Lines como texto**, que Mnemo sí manda a trozos: una línea con el título, una por paso (las mismas claves de un
  paso de `recorrido`) y una con el cierre y las sugerencias.
- **Cómo se publica.** `redactor.Lector` saca cada objeto en cuanto se cierra y `PlanEnFlujo` lo compone igual que
  `recorrido` (`_componer`, tolerante; `recorrido.validar`, que no se relaja). Con el primer paso que vale, el plan se
  guarda (`pantalla.guardar_recorrido` con `abierto`) y se publica con la píldora «preparando» apagada: la acción
  `presentacion` `recorrido` con `abierto` y la tarjeta del chat. Cada paso nuevo lo hace crecer
  (`pantalla.crecer_recorrido`, que sube la versión) y vuelve la misma acción con `sigue` (y la tarjeta con el mismo
  id). Al terminar va entera, con su cierre y sin `abierto`. Un paso que no se puede proyectar (con costos, «@», un
  número largo) se omite con un aviso y el plan sigue; lo que pasa de los pasos del largo (con dos de margen), de 12 o
  de la duración máxima, también.
- **En el navegador.** El reproductor (`web/js/reproductor.js`) recibe el plan `abierto` y lo hace crecer con
  `actualizar` (los pasos nuevos se agregan detrás; los que ya sonaban no se tocan). Si la narración llega al último
  paso antes que el siguiente, la imagen se queda y lo espera, hasta `ESPERA_MAS_MS` (45 s; una pausa no cuenta), y
  después cierra con lo que hay; **Siguiente** en el último paso también espera. La vista aplica `sigue` solo si ese
  plan suena ahí; la pantalla en off ve los pasos nuevos en su próxima pregunta al servidor, y el proyector los recibe
  por su canal, como cualquier acción. La tarjeta (`crecer`) suma los pasos, el cierre, las sugerencias y la duración,
  y dice «por ahora: el panel sigue escribiéndolo» mientras tanto. El avance de un plan en flujo puede contar menos
  pasos de los guardados (el navegador recibe los nuevos un momento después): el servidor lo acepta (`en_flujo`).
- **Si algo falla.** Si la redacción falla o no da un paso que valga en 60 s, no se guarda nada y la herramienta
  devuelve `plan_fallo`: el modelo arma el plan como antes. Si falla a mitad, el plan queda con lo que alcanzó (con un
  aviso). Si la persona lo detiene, otra orden cambia la pantalla o llega otro plan mientras se escribe, la redacción
  se corta en el acto (`crecer_recorrido` ya no encuentra el vigente): no se gasta en lo que nadie va a oír.
- **Solo del asistente.** Por MCP la op no se ofrece (no hay modelo del panel que escriba por el agente externo, ni
  créditos que gastarle): el agente arma su plan con `recorrido`, como siempre.
- **Costo.** Una petición más por plan (las instrucciones y el guion del capítulo de entrada, casi siempre desde la
  caché del proveedor; de salida, unos 1.000 a 2.500 tokens), que se suma al día de la persona en `agente_uso`. A
  cambio, el modelo principal ya no lee el guion ni escribe el plan entero, no razona sobre él y se ahorra la ronda
  final: en total suele salir más barato.

## Pantalla en off y agentes por MCP

La **pantalla en off** es la presentación de la propuesta para una sala: se abre en el proyector o en un televisor, no
tiene controles y **solo cambia cuando se le pide algo concreto a un agente**: al asistente del panel (desde otro equipo
o el celular) o a un agente externo por MCP (Claude, Mnemo u otro cliente MCP). Los dos usan la misma herramienta,
`presentacion`, y manejan la misma pantalla: la de la persona que los usa.

- **Abrirla.** En la vista **Presentación**, el botón **Pantalla en off** (o la dirección `/panel/presentacion?off=1`),
  en el navegador del proyector con la sesión de la persona. Arriba dice que no tiene controles y si está conectada;
  **Salir del modo en off** vuelve a la vista de siempre. El asistente se abre en esa misma ventana, al lado de la
  presentación ([El asistente en la misma ventana](#el-asistente-en-la-misma-ventana)), o se le habla desde otra.
- **Qué hace.** Pregunta cada segundo y medio por su estado (`GET /api/pantalla?v=`) y aplica solo lo que cambió: el
  capítulo y el paso, la explicación en pantalla, lo que se ve (el panel de texto o «Solo 3D», el índice, las fichas),
  lo visual de la presentación técnica (la cámara, a qué apunta, la obra enfocada, la ficha técnica, hoy o con el
  proyecto, las piezas de la maqueta que se muestran, se ocultan o se aíslan, las partes quitadas, el modelo del atlas
  y el tema; al cambiar de paso vuelve a lo del paso, salvo el tema), una vez el viaje de la cámara o la animación que
  pidió la última orden `visual` (no son estado: la orden siguiente los deja en nada) y la pantalla completa. La presentación queda inerte: ni clics ni teclado, y sin sus botones. Lo que se toque a mano en
  la vista del panel no la mueve.
- **Planes guiados.** Un [plan guiado](#el-plan-guiado-recorridos-narrados) con la pantalla en off abierta suena allá (con
  la voz de ese navegador, encendida por omisión; hace falta un gesto en esa ventana). La pantalla lo narra si llega a tiempo (menos de 90 s) y, si se recargó a
  mitad, sigue desde la escena donde iba; uno viejo no se narra: queda en su última escena. Si se abre mientras un
  recorrido suena en la pestaña o el proyector, muestra su escena en curso, sin narrarlo. Los controles (de la tarjeta
  del chat, del asistente o de un agente por MCP con `control_recorrido`) se aplican una vez cada uno. Por MCP,
  `recorrido` exige la pantalla en off abierta (si no, 409 `sin_pantalla`), el avance se sigue con `estado` y uno que el
  asistente armó en la pestaña del panel no se controla (409 `en_el_panel`: se maneja desde ahí).
- **Pantalla completa.** «Ponla en pantalla completa» hace que la presentación llene la ventana, sin el menú ni las
  barras del panel. Escape la devuelve en esa pantalla hasta la próxima orden. La pantalla completa del navegador (sin
  la barra de direcciones) es F11 en ese equipo, o el navegador en modo quiosco: un navegador no deja que una página la
  pida sin que alguien toque la pantalla.
- **El asistente del panel.** Mientras hay una pantalla en off abierta (preguntó en los últimos 10 segundos), su
  contexto dice qué muestra, «siguiente» y «anterior» van desde su paso y la pestaña del chat no cambia de vista (la
  persona puede estar escribiendo desde el celular). Sin pantalla abierta, todo es como antes: maneja la vista
  Presentación de la pestaña del chat, y lo que deja queda guardado para cuando se abra la pantalla.
- **Un agente por MCP.** En **Mi cuenta → Agentes por MCP**, **Crear clave** de la presentación muestra la dirección del
  servidor MCP (`https://<su dominio>/panel/api/mcp`) y la clave, una sola vez. En el cliente MCP se configura como
  servidor remoto (Streamable HTTP) con la cabecera `Authorization: Bearer <clave>`; si el cliente solo acepta una
  dirección, la segunda que muestra Cuenta lleva la clave en `?clave=` (guárdela como un secreto). Por ejemplo, con
  Claude Code:

  ```bash
  claude mcp add --transport http yondo-presentacion https://<su dominio>/panel/api/mcp --header "Authorization: Bearer <clave>"
  ```

  El agente ve una sola herramienta, `presentacion`, con las mismas operaciones y las mismas reglas que el asistente:
  la frase en pantalla nunca lleva datos de habitantes, «@» ni números de 7 o más dígitos. Con la clave de la
  presentación no se lee ni se escribe ningún dato de personas: eso es de la otra clave, la de datos (ver [Agentes por
  MCP con datos](#agentes-por-mcp-con-datos)), que nunca maneja la presentación.
- **La clave de la presentación.** Una por persona (aparte de la de datos): crear otra reemplaza solo la anterior de la
  presentación y **Revocar** la anula. En la base queda su SHA-256, nunca la clave. Deja de valer sola si la persona
  cambia su clave del panel (o el administrador cambia su credencial), si la desactivan, o si su cuenta queda pendiente
  (clave temporal o compromiso por aceptar). Crear y revocar quedan en la auditoría. El servidor rechaza las peticiones
  con una cabecera `Origin` que no es la del panel (un navegador no puede usarla desde otra página) y atiende hasta 120
  por minuto por clave.
- **El protocolo.** `POST /api/mcp`: Streamable HTTP sin estado, revisiones 2025-11-25, 2025-06-18, 2025-03-26 y
  2024-11-05, un mensaje JSON-RPC por petición y la respuesta en JSON (`initialize`, `ping`, `tools/list`,
  `tools/call`). `GET` y `DELETE` responden 405 (sin flujo SSE ni sesiones). Los errores de la herramienta vuelven como
  `isError`, para que el agente los corrija. La ruta no usa la sesión del panel, pero sí sus protecciones: el tope del
  cuerpo, los cupos del servicio único y el 503 mientras MongoDB no responde.

### El asistente en la misma ventana

En la pantalla en off (`/presentacion?off=1`) y en la ventana del proyector (`/presentacion?pantalla=1`) el asistente
se abre **ahí mismo**, al lado de la presentación, con todo lo que tiene en el panel: escribir, preguntar por voz, la
tarjeta del plan con su avance y sus controles y la franja de la presentación automática. No hace falta ir a otra
ventana para ver el plan.

- **Cerrado por omisión.** La ventana abre como siempre, con la presentación entera; solo se ve el botón del
  asistente. En la pantalla en off va en su barra de arriba, a la derecha (como en la vista normal). En el proyector,
  que no tiene barra, flota abajo a la izquierda (arriba a la derecha están las herramientas de la presentación), con
  los botones de la ventana a su lado; en la pantalla en off cuando llena la ventana, arriba a la derecha (ahí la
  presentación no tiene herramientas). Tras 3 segundos sin mover el ratón ni tocar se atenúa para no distraer a la
  sala, y vuelve a verse al mover el ratón o tocar. La pestaña del chat a pantalla completa hace lo mismo: ver
  [Pantalla completa en la pestaña](#pantalla-completa-en-la-pestaña).
- **Abierto.** En escritorio (desde 901 px) la presentación le deja libre su ancho, como en la vista normal: nada queda
  tapado y la maqueta 3D se reencuadra sola. En el celular se superpone, como siempre. Se cierra con su botón o con
  Escape (salvo mientras graba una pregunta por voz: ahí Escape cancela la grabación).
- **En tiempo real.** En la pantalla en off, los planes del asistente siguen yendo a la pantalla en off (el servidor no
  cambia) y los narra la vista de esa misma ventana; cuando llega el resultado de una orden de la presentación (un
  plan, un control o cualquier op que cambie lo que se ve), el chat le pide a la vista que pregunte por su estado en el
  acto, sin esperar el segundo y medio del sondeo. La tarjeta del plan recibe el avance de la vista de esa ventana en
  el acto (y no lo da por «sin respuesta» mientras sigan llegando); sus controles van al servidor, así valen también
  para otra pantalla en off abierta, y después piden la vuelta inmediata. El interruptor de voz de la tarjeta enciende
  o apaga la voz de esa misma ventana. En el proyector, el chat de esa ventana aplica todo en la vista de ahí; la
  pestaña del panel, si también está abierta, sigue viendo el avance por el canal del proyector.
- **El teclado del proyector sigue siendo de la presentación.** Al cerrar el chat el foco vuelve a la presentación (no
  al botón), y las flechas, AvPág, RePág y la barra espaciadora la mueven aunque el foco esté en otro lado; lo que se
  escribe en el chat no le llega. Si la persona ya escribe en el chat mientras la presentación carga, el foco no salta
  a la presentación.
- **La pantalla en off cuenta como abierta desde que se monta**, no desde que termina de cargar: un plan pedido en el
  chat de esa ventana en ese rato va igual a la pantalla en off. En el celular, cuando el plan empieza, el chat se
  pliega para que se vea la presentación.
- Los pasos que manejan una simulación (del atlas o de la maqueta) llevan en la tarjeta el chip «Maneja la simulación».
- Los enlaces **Abrir en otra pantalla** y **Pantalla en off** de la vista lo dicen en su descripción: ahí también se
  abre el asistente.

### Presentación automática

Con la presentación automática encendida, la pantalla en off **recorre sola toda la presentación**, capítulo por
capítulo, diciendo de cada paso una frase muy resumida, y al terminar la vuelta vuelve a empezar. No usa el modelo ni
cuesta nada: la narración sale del guion (`app/automatica.py`).

- **Encenderla y apagarla.** El botón **Automática** de la barra de la pantalla en off (ese clic es además el gesto
  que activa la voz), pedírselo al asistente («déjala en automático», «preséntala completa desde Salud»: `presentacion`
  op `automatica`, con `accion` `iniciar` o `detener` y, para empezar en otro capítulo, `capitulo`) o un agente por MCP
  con la misma op. El chat muestra una franja («Presentación automática encendida · empieza en Salud») con **Detener**.
  Por dentro, `POST /api/pantalla/auto` (`{accion, capitulo?}`, con el permiso `presentacion.ver`). Sin una pantalla en
  off abierta queda encendida y empieza cuando se abra una: solo corre allá.
- **Qué dice en cada paso** (`narracion_del_paso`), lo primero que sirva de:
  1. la narración escrita a mano (hoy cada paso tiene la suya, con la [voz de la
     presentación](#cómo-habla-la-voz-de-la-presentación): sencilla, sin siglas ni tecnicismos y con el léxico del
     candidato; lo que sigue es para un paso que no la traiga);
  2. en el paso de metas, su **primera meta**, resumida (`primera_meta`): el indicador, el dato de la línea base y la
     meta con su año, sin las fuentes ni las aclaraciones entre paréntesis («La primera meta: sedes rurales de salud
     habilitadas en el REPS, de 0 a 5 en 2031.»); si así no cabe, solo la meta. La frase de su texto («Cada meta parte
     de una línea base…») es la misma en los siete módulos;
  3. la primera frase del texto del paso (hasta unos 180 caracteres: una más larga se corta en su último punto y coma
     o dos puntos, donde termina una idea; nunca en una coma), salvo que hable de costos;
  4. si el título es solo un rótulo (menos de 50 caracteres: «Cinco piezas, una sola red»), una **frase corta** del
     paso (`frase_corta`, de 40 a 180 caracteres): la primera idea del texto que quepa, frase por frase y, en una
     larga, cada parte separada por punto y coma (con mayúscula y punto), y si ninguna, la primera cifra del paso con
     su leyenda;
  5. el título del paso (uno largo ya es una frase y se dice tal cual).

  Todo pasa las reglas de lo que se proyecta y nada habla de costos; un paso sin nada que decir se salta. Hoy son 55
  pasos en 9 capítulos, todos con su narración escrita a mano: entre capítulo y capítulo no hay cierre ni espera de
  preguntas (eso es de los planes del asistente), solo un segundo y medio.
- **Escribir una narración a mano.** En `data/propuesta/general.json`, `tecnica.narracion` es
  `{capítulo: {id del paso: "frase"}}` (hasta 220 caracteres, sin costos, con la voz de la presentación y solo con
  datos del paso); `python3 scripts/build_propuesta.py` la lleva al guion del asistente (queda en el paso como
  `narracion`) y manda sobre todo lo demás. `tests/test_lenguaje.py` revisa que cada paso tenga la suya, que no traiga
  siglas, «plata», «el casco» sin «urbano» ni lo que salió de la propuesta, y que sea de un paso que existe.
- **Cómo corre.** El servidor arma un [plan](#el-plan-guiado-recorridos-narrados) por capítulo
  (`plan_del_capitulo`): un paso del plan por cada paso del capítulo, con lo visual y la animación propios del paso
  y un movimiento suave de la cámara, sin cierre. La pantalla lo narra como cualquier otro (subtítulo y voz), sin la
  espera inicial, y cuando no narra nada pide el siguiente (`POST /api/pantalla/auto/siguiente`: 200 con el id del
  plan que armó o 204 si no había nada que hacer): al segundo y medio de terminar un plan automático, a los 5 segundos
  de terminar uno del asistente y a los 45 de otra orden suelta. No genera tarjeta en el chat.
- **Una pregunta la interrumpe.** Con ella encendida, el contexto del asistente dice por dónde va y que responda con
  un plan corto (3 a 5 pasos). Ese plan reemplaza al automático en la pantalla; cuando termina, la automática sigue
  en el paso que se estaba diciendo (si ya estaba en «¿Preguntas?», con el capítulo siguiente). Una orden suelta
  (`ir`, `visual`, `explicar`) también la interrumpe y después sigue desde ahí.
- **Pausar y detener.** `control_recorrido` funciona sobre el plan automático como sobre cualquiera: en pausa espera
  (no pide otro plan); `detener` además apaga la automática, lo mismo que detenerlo a propósito en esa pantalla (una
  tecla o un botón: los «detenido» con `motivo` `tecla` o `boton`). Salir de la vista en off (**Salir del modo en
  off**, otra vista del menú) no la apaga: suelta el plan y la automática queda encendida en ese paso; la próxima
  pantalla en off que se abra sigue desde ahí. Si la pantalla se recarga o se cierra a mitad, a los 30 segundos sin
  noticias el servidor da el plan por caído y arma otro desde ese paso. Un plan que termina en error se salta o se
  reintenta; al tercero seguido se apaga sola (la presentación no responde). Detener un plan del asistente no la
  apaga: cuando el asistente detiene el suyo, el resultado le dice que la automática sigue encendida y en qué paso
  retoma, para que no le diga a la persona que la sala quedó en silencio (si la persona lo quiere, se apaga con
  `automatica` `detener`).
- **Volver a reproducir una respuesta.** Cuando la automática sigue después de un plan del asistente, el servidor
  guarda ese plan (`recorrido_previo`): **Volver a reproducir** de su tarjeta (o `control_recorrido` `reproducir`
  con su id) lo trae con un id nuevo, la interrumpe y, al terminar, ella sigue desde su paso. Sirve hasta que llegue
  otro plan que no sea de la automática, como sin ella.
- **El estado** va con la pantalla (`pantallas`, clave `auto`): `{activa, capitulo, paso, rid, vueltas, fallas}`. `paso`
  es el que se está narrando o el próximo; `rid`, el id de su plan mientras suena. `GET /api/pantalla` lo trae como
  `auto: {activa, capitulo, paso}` (o `null` si nunca se encendió; encenderla o apagarla sube la versión) y su plan
  viaja con `auto: true`; `GET /api/pantalla/recorrido` trae el mismo `auto`. `estado` de la herramienta dice además
  cuántas vueltas lleva.

## Agentes por MCP con datos

Además de la presentación, un agente externo (Claude Desktop, Claude Code, ChatGPT u otro cliente MCP) puede trabajar
con **datos del panel** con una **clave de datos** de la persona: leer personas, ver la analítica o **proponer**
cambios. Nada se escribe sin que la persona lo apruebe en el panel, y lo que el agente lee **sale del panel hacia ese
cliente**: un tercero que la persona elige y por el que responde (Ley 1581 de 2012 y el compromiso de
confidencialidad). Mi cuenta lo dice antes de crear la clave.

**Dos claves por persona.**

| | Clave de la presentación | Clave de datos |
|---|---|---|
| Prefijo | `ypm_` | `ypd_` |
| Qué hace | Maneja la pantalla en off (`presentacion`). Ningún dato de personas | Lo de sus alcances: `lectura`, `analitica`, `escritura` (nunca la presentación) |
| Dónde va | `Authorization: Bearer` o `?clave=` | **Solo** `Authorization: Bearer` (con `?clave=`, 401: en una dirección quedaría en los registros de proxies y del borde) |
| Vence | No | A los **30 días** (`expira`, índice TTL; vencida no vale aunque siga en la base) |
| Quién | Todos los roles (`presentacion.ver`) | A y K, según **Ajustes → Agentes externos por MCP** (`agente_mcp.roles`; por defecto, solo el administrador) |
| Crear otra | Reemplaza solo la de la presentación | Reemplaza solo la de datos y **anula sus propuestas pendientes** |

Las dos se muestran una sola vez, al crearlas; en la base queda su SHA-256 y la huella de la sesión de ese momento:
cambiar la clave del panel (o la credencial del administrador), desactivar a la persona o dejar su cuenta pendiente
las anula. Se revocan por separado (`DELETE /api/pantalla/clave?tipo=presentacion|datos`; sin `tipo`, las dos), y
revocar la de datos anula sus propuestas pendientes. Crear y revocar quedan en la auditoría, con el tipo y los
alcances. Las claves guardadas antes (sin `tipo`) son de la presentación.

**Alcances.** Se comprueban al crear la clave **y otra vez en cada petición** (un cambio de rol o de Ajustes vale
desde la petición siguiente; lo que ya no vale se deja de ofrecer). Todos exigen el rol en `agente_mcp.roles` y
`agente.usar`:

| Alcance | Qué da | Quién |
|---|---|---|
| `lectura` | Personas una por una (búsqueda de a 10, fichas, reuniones, calidad…) | **Solo el administrador** (`exportar`): entregarle personas a un cliente externo es sacarlas del panel, como exportarlas |
| `analitica` | Cifras agregadas (`analizar`, `diagnostico`) con las celdas pequeñas ocultas, sin gráfico | A y K (`analitica.ver`) |
| `escritura` | Propuestas de cambio que la persona aprueba en Mi cuenta | A y K, con `agente.escritura` **y** `agente_mcp.escritura` |

Planilleros y consultores nunca tienen clave de datos.

**Herramientas por MCP.** Solo salen las del asistente **marcadas** una por una (`Herramienta.mcp`): una nueva no sale
por MCP hasta que alguien lo decide (una prueba fija los nombres exactos por alcance), y además lo que
`politica.ofrecida` le deja a la persona.

- **lectura:** `buscar_personas` (de a 10 por página), `ver_persona`, `personas_parecidas`, `listar_reuniones`,
  `ver_reunion`, `pendientes`, `catalogos`, `buscar_lugar`, `indicadores`, `historial_acercamientos`,
  `autorizaciones_de`, `coincidencias`, `conflictos_cedula`, `situaciones`, `solicitudes`, `importaciones`, `puestos`,
  `lugares_sin_reconocer` y `lideres`.
- **analitica:** `analizar` y `diagnostico`.
- **escritura:** `crear_persona`, `editar_persona`, `agregar_nota`, `registrar_acercamiento`, `ubicar_persona`,
  `agregar_telefono`, `crear_reunion`, `agregar_asistente`, `reportar_situacion`, `registrar_solicitud`,
  `reportar_duplicado`, `marcar_no_disponible`, `pedir_actualizacion`, `estado_telefono`, `anular_acercamiento`,
  `editar_reunion`, `quitar_asistente`, `resolver_coincidencias`, `resolver_conflicto`, `confirmar_situacion`,
  `actualizar_solicitud`, `agregar_alias_lugar`, `marcar_tipo` y `asignar_lider`. Cada una pide además
  `motivo_propuesta` (1 a 300 caracteres, una línea: por qué la propone; se ve en la tarjeta). Con `escritura`,
  también `estado_propuesta`, que solo existe por MCP.
- **Nunca por MCP:** `registrar_autorizacion`, `equipo`, `mi_trabajo`, las de interfaz (`mapa`, `abrir_vista`,
  `presentacion`: la presentación tiene su propia clave), las de Mnemo y las de planillas por foto.

**Qué le llega al agente.**

- Lo mismo que al modelo del chat: el resultado de la herramienta para el modelo (minimizado, recortado a 40.000
  caracteres), **nunca** las acciones (llevan coordenadas y nombres, y el gráfico) ni imágenes.
- **Sin quien no autorizó:** se quitan del resultado las filas de quien no autorizó (ni quién es ni su barrio) y queda
  cuántas se omitieron (`omitidas_no_autorizo`); su ficha, su historial o sus autorizaciones son un error que no la
  nombra, y los grupos de duplicados y conflictos que la incluyen no salen.
- **Supresión en curso:** si una persona del resultado se suprimió o dejó de autorizar mientras se leía, se descarta.
- **Datos políticos:** solo con `agente_politicos.mcp` encendido (lo está por defecto; ver [Datos
  políticos](#datos-políticos)), y como el panel se los muestra a la persona de la clave: el administrador, con
  `lectura`, el tipo, el «Liderado por», las listas, las fuentes y `lideres`; A y K, la analítica por tipo o lista y
  las propuestas `marcar_tipo` y `asignar_lider`. La tabla por `lider` nombra a cada líder (es entregar personas): por
  MCP solo con `lectura` (el administrador); sin ella responde 403 `permiso`. Apagado, `lideres`, `marcar_tipo` y
  `asignar_lider` no se ofrecen por MCP y nada político sale, aunque el asistente del panel sí los tenga
  (`agente_politicos.asistente`); tampoco el detalle de `estado_propuesta` de una propuesta hecha con el ajuste
  encendido. Al aprobar en Mi cuenta una propuesta hecha por MCP, se decide con el ajuste de MCP.
- **Una clave sin `lectura` (el coordinador) nunca recibe datos de personas:** al proponer le vuelve solo el id, la
  herramienta y dónde se aprueba; al consultar `estado_propuesta`, «hecha» sin el detalle.
- Cada herramienta corre con una **sesión interna** de la persona (`app/sesion_interna.py`: 5 minutos, `via: "mcp"`,
  cerrada al terminar, sin contar entre sus sesiones ni salir en Usuarios): la API aplica sus permisos, su alcance, la
  proyección por rol, las lecturas a su nombre y la auditoría, que marca `via: "mcp"`.

**Topes y registro**, por clave y por día (hora de Colombia), en MongoDB:

- Llamadas: `agente_mcp.llamadas_diarias` (2.000 por defecto, de 10 a 20.000); pasado el tope, `tope_llamadas`.
- Personas distintas entregadas: `agente_mcp.personas_diarias` (300 por defecto, de 10 a 5.000): una entrega que lo
  pasaría no se hace (`tope_personas`); las mismas personas otra vez sí.
- Además, 120 peticiones por minuto por clave y hasta 30 propuestas pendientes por clave.
- Cada llamada queda en `mcp_entregas` (clave, persona del equipo, día, herramienta, ids entregados; 90 días, como
  `lecturas`): ante un reclamo, a qué clave se le entregó quién. Cada entrega con personas va a la auditoría
  (`entrega_mcp`, con cuántas).

**Propuestas: el agente propone, la persona aprueba.**

1. El agente llama una herramienta de escritura con `motivo_propuesta`. El panel arma **la misma tarjeta del chat** y
   la guarda en `mcp_propuestas` (id al azar, persona, clave, motivo, IP, creada, **vence a las 48 h**, y las personas
   de la entrada y de la tarjeta). Al agente le vuelve `{estado: "pendiente", propuesta, herramienta, titulo, vence,
   aprobar_en, mensaje}`, con `aprobar_en` = `https://<su dominio>/panel/cuenta?propuesta=<id>` y el mensaje «NO está
   hecho: pídale a la persona que lo apruebe en … y, cuando diga que lo aprobó, consulte estado_propuesta».
2. **El menú lo cuenta**: «Mi cuenta» lleva una insignia con las propuestas que esperan a esa persona
   (`propuestas_mcp` de `GET /api/insignias`, `INSIGNIAS.cuenta` en `web/js/app.js`), así no vencen sin verse. En **Mi
   cuenta → Agentes por MCP** está cada una con la tarjeta entera, el motivo del agente, de qué clave, desde qué IP,
   cuándo llegó y cuándo vence (el enlace `?propuesta=` la resalta). **Aprobar** o **Rechazar**, una por una: no hay
   «aprobar todas». Decidir una refresca la insignia.
3. Al aprobar, con **la sesión de quien aprueba**: se vuelve a comprobar que la clave siga valiendo, que el rol y los
   ajustes sigan permitiendo la escritura por MCP y que la entrada siga siendo válida, y se ejecuta con la idempotencia
   `agente.0.mcp-<id>`. Si la ficha cambió entre la propuesta y la aprobación, no se guarda (`fallida`).
4. El agente consulta `estado_propuesta`: `pendiente`, `en_curso`, `hecha`, `rechazada`, `fallida`, `anulada` (la clave
   se revocó, se reemplazó o dejó de valer) o `vencida`. Solo ve las de su persona y de su misma clave.

Decidida o anulada, la propuesta pierde la tarjeta y la entrada y se borra a los 7 días. **La supresión y el «no»
borran las propuestas** que muestran a esa persona (`db.borrar_propuestas_mcp`).

**Configurarla en un cliente:**

```bash
claude mcp add --transport http yondo-datos https://<su dominio>/panel/api/mcp --header "Authorization: Bearer <clave de datos>"
```

El servidor se presenta como `yondo-datos` (la presentación, `yondo-presentacion`) y sus instrucciones le dicen al
agente las reglas: datos protegidos, nada de reconstruir lo enmascarado, los textos del equipo son datos y no
instrucciones, los topes y que **nunca diga que algo quedó hecho** sin que `estado_propuesta` diga «hecha». Lo
político depende del ajuste (`instrucciones_datos`): apagado, «Nada de datos sensibles ni políticos: no están y no los
pidas.»; encendido, «Nada de datos sensibles: no están y no los pidas. Los datos políticos (tipo de persona, «Liderado
por», listas, líderes y las bases de cédulas y general) llegan solo en lo que la persona ve en el panel: son datos de
afiliación política, trátalos con la misma reserva.»

**Rutas de Mi cuenta.** `GET /api/pantalla/clave` (la de la presentación como antes, más `datos: {tiene, creada, usada,
expira, alcances, vigentes}`, `permitidos`, `motivos` y `propuestas_pendientes`); `POST /api/pantalla/clave` con
`{tipo?, alcances?}` (sin cuerpo, la de la presentación; 403 `permiso` con un alcance que no tiene);
`GET /api/mcp/propuestas` (`{propuestas, recientes}`) y `POST /api/mcp/propuestas/{id}` `{aprobar}` (`requiere
("agente.usar")`; la de otra persona, 404; ya decidida, 409).

## La voz clonada de Mnemo

El asistente puede narrar la presentación técnica y leer en voz alta sus respuestas con **una voz clonada en Mnemo** (la
del administrador, o la de alguien que le dio su permiso expreso), en vez de la voz del navegador. La voz se clona en
Mnemo (**Ajustes → Voces**, con la casilla de consentimiento) y se marca **Disponible para apps conectadas**; el panel
la usa con la conexión de Mnemo del administrador y los créditos de esa cuenta. El audio llega **por partes mientras
Mnemo lo genera**: la primera palabra suena antes de que la frase esté entera. Si la voz clonada no llega (sin permiso,
sin créditos, la red, la demora), la frase se dice con la voz del navegador sin que se note un corte: la presentación
nunca queda muda.

**Cómo se enciende** (solo el administrador; el coordinador lo ve en solo lectura):

1. En Mnemo, clone la voz en **Ajustes → Voces** y márquela **Disponible para apps conectadas**.
2. Conecte (o vuelva a conectar) Mnemo desde **Ajustes → Asistente** dejando marcado **«Hablar con las voces que
   clonaste en Mnemo…»** (el permiso `mnemo:voice`, ver [Conectar con Mnemo](#conectar-con-mnemo)). Una conexión
   hecha antes de que existiera la voz clonada no tiene ese permiso (Mnemo solo lo da al conectar): el bloque **Voz
   del asistente** lo avisa con el botón **Volver a conectar para usar la voz**, que hace lo mismo que **Volver a
   conectar** del bloque de Mnemo.
3. Listo: sin elegir nada más, el asistente usa **la voz que Mnemo ofrece a las apps** (la automática: la más
   reciente que su dueño marcó para apps, `default_voice_id`). Para fijar otra, o cambiar quién la hace sonar y para
   qué, use **Ajustes → Asistente → Voz del asistente** (la lista sale de `GET /api/agente/voces`) y pulse **Guardar
   voz**. **Probar voz** dice una frase fija con la voz guardada (o la automática) y muestra cuánto tardó la primera
   palabra (en el navegador y en Mnemo). Para no usar la voz clonada, elija **Voz del navegador**.

| Ajuste (`agente_voz`) | Por defecto | Qué decide |
|---|---|---|
| `motor` | `mnemo` | `navegador` (Web Speech, como siempre) o `mnemo` (la voz clonada, si la conexión tiene `mnemo:voice`; si no, suena la del navegador) |
| `voz`, `nombre` | Automática | La voz de Mnemo (su id, de `GET /api/agente/voces`) y su nombre para mostrar. Vacía, la automática: la que Mnemo ofrece a las apps (`default_voice_id` de `mnemo_list_voices`); el panel le pregunta cuál es (no gasta créditos) y lo recuerda 5 minutos por conexión, también que no hay ninguna. Al elegirla, el servidor anota además la cuenta de Mnemo conectada (`cuenta`, una huella: los primeros 32 hexadecimales del SHA-256 del emisor y el `sub`; nunca la que mande el formulario). Si después se conecta otra cuenta, esa voz deja de valer hasta elegir otra |
| `roles` | Administrador y coordinadores | Quién hace sonar la voz clonada (habla con la voz y los créditos de la cuenta del administrador). Los demás roles oyen la del navegador. Las respuestas leídas en voz alta son texto del modelo, y quien pregunta lo puede encaminar: ponga aquí solo los roles en quienes confía para hablar con esa voz |
| `respuestas` | Sí | Si lee en voz alta las respuestas del asistente (cuando la persona lo enciende en el chat o pregunta por voz) |
| `automatica` | Sí | Si narra también la [presentación automática](#presentación-automática) (sale de la caché casi siempre: se repite) |

**Cómo funciona por dentro** (`app/agente/voz.py`).

- **El audio viaja dentro de MCP.** El panel llama a la herramienta `mnemo_speak` de Mnemo con `_meta.progressToken`
  y Mnemo manda el audio en sus avisos de progreso. Así el token de la conexión sigue yendo solo a la dirección MCP
  atada a él (nunca a otra ruta de Mnemo) y la clave del proveedor de voz no sale de Mnemo. Ninguna de las dos
  herramientas de la voz (`mnemo_speak`, `mnemo_list_voices`) es una herramienta del modelo, ni con
  `MNEMO_HERRAMIENTAS=*`: la voz clonada solo dice lo que el panel decidió decir.
- **Contrato con Mnemo.** `mnemo_list_voices` (entrada `{}`) devuelve `{voices: [{voice_id, name, language, engine,
  status: "ready"}], default_voice_id}`: solo las voces marcadas para apps y listas. `mnemo_speak` recibe
  `{voice_id, text (1 a 1000 caracteres), format: "pcm_s16le_24000", language: "es"}`; cada aviso de progreso trae en
  `message` un JSON: primero `{"type": "start", "format", "mime", "sample_rate", "channels", "mode"}` y después
  `{"type": "audio", "seq", "data": <base64 de un trozo>}` (unos 9.600 bytes: 200 ms de PCM de 16 bits, 24 kHz,
  mono). La salida final trae `first_audio_ms` (lo que tardó Mnemo en dar el primer audio) y, si no llegó nada por
  el avance, el audio entero en `audio`. Si Mnemo no pudo dar PCM, `format` dice cuál dio (`mp3`, `wav`) y el
  navegador decodifica la frase entera. Los errores de Mnemo (`{error: {code, …}}`): `NO_VOICE`, `PLAN_REQUIRED`,
  `CREDITS_EXHAUSTED`, `UNAVAILABLE` (`details.reason: "speech"`: la cuenta no tiene con qué generar la voz),
  `RATE_LIMITED`, `TIMEOUT`, `INVALID_ARGUMENT`, `INTERNAL`.
- **`POST /api/agente/voz`** (sesión, CSRF y permiso `presentacion.ver`) responde en flujo NDJSON, como el chat (el
  navegador la lee con `flujo()` de `api.js`). El cuerpo es **exactamente uno** de estos (tipos estrictos, sin claves
  de más; si no, 422):

  | Cuerpo | Qué se dice |
  |---|---|
  | `{"rid", "n", "frase"}` | La frase `frase` (desde 0) del paso `n` (desde 1) del plan `rid` (12 hexadecimales), tal como está guardado para esa persona: el de su pantalla (`pantalla.recorrido_de`) o, con la automática sonando, el último que ella reemplazó (`recorrido_previo`). Un plan que escribió una aplicación externa por MCP nunca: ver abajo |
  | `{"rid", "cierre": true}` | El cierre de ese plan: «En resumen. » y sus puntos unidos con «. », como lo dice `reproductor.js` |
  | `{"conversacion", "texto", "firma"}` | Una frase de una respuesta del asistente (hasta 400 caracteres), con la firma que le puso el servidor al emitirla en el evento `frase` del chat |
  | `{"prueba": true}` | Solo el administrador (`agente.conectar`): «Hola. Esta es la voz que usará el asistente para narrar la presentación y responder sus preguntas.» |

  Nunca un texto libre. Por eso **un plan escrito por MCP siempre se narra con la voz del navegador**: por MCP, quien
  tiene la presentación escribe a mano las frases y el cierre del plan, sin un modelo de por medio, así que no es texto
  que el sistema generó. El plan queda marcado al guardarlo (`externo`, también su copia al volver a reproducirlo desde
  el panel o tras la automática) y la ruta responde 409 `voz_apagada` a cada una de sus frases y a su cierre. Todo
  texto se revisa con las reglas de lo que se dice ante una sala (como lo proyectado: sin
  «@» ni números de 7 o más dígitos, mirados sin caracteres invisibles y en su forma NFKC) y se dice con la misma
  tabla de pronunciación que la voz del navegador (`para_decir`, el `paraDecir` de `web/js/voz.js`: «NSR-10», «m²»,
  «24 h»…; una prueba corre las dos tablas con las mismas frases).
- **Los eventos del flujo**, una línea JSON cada uno:

  | Evento | Qué lleva |
  |---|---|
  | `inicio` | `formato` (`pcm_s16le`; o `mp3`, `wav`… si Mnemo no pudo dar PCM), `muestreo` (24000), `canales` (1), `cache` (si salió de la caché) y `voz` (su nombre) |
  | `audio` | `datos`: un trozo en base64, el de Mnemo tal cual. Lo ya producido llega primero: una petición que se colgó tarde de una frase en camino no pierde nada |
  | `latido` | Cada 15 s sin otros eventos |
  | `fin` | `ms_primer_audio` (desde que el panel recibió la petición hasta el primer trozo), `ms_mnemo` (el `first_audio_ms` de Mnemo, o null) y `bytes`. Siempre el último si todo salió bien |
  | `error` | `codigo` y `mensaje`, si falla a mitad (el último) |

- **Lo que impide decirla sale antes del flujo**, como JSON `{codigo, mensaje}` (la ruta espera el primer aviso de
  Mnemo antes de abrir el flujo):

  | Estado y código | Cuándo | Qué hace el navegador |
  |---|---|---|
  | 409 `sin_voz` | El motor es `navegador`; la conexión no está, no tiene `mnemo:voice` o es de otra cuenta que la de la voz elegida; con la automática, Mnemo no ofrece ninguna voz a las apps; o Mnemo dice que no puede (la herramienta no está, `NO_VOICE`, `PLAN_REQUIRED`, `UNAVAILABLE`) | Sigue con la voz del navegador el resto de la sesión |
  | 403 `voz_rol` | Su rol no está en `agente_voz.roles` (o pide la prueba sin ser administrador) | Igual |
  | 409 `voz_apagada` | La voz no lee respuestas (`respuestas`), no narra la automática (`automatica`) o el plan lo escribió una aplicación externa por MCP | Esa frase con la del navegador |
  | 409 `plan_vencido` | El `rid` no es el plan vigente de esa persona (ni el que la automática reemplazó) | Esa frase con la del navegador |
  | 409 `con_personas` | La conversación ya trae datos de habitantes | Esa frase con la del navegador |
  | 404 `no_existe` | La conversación no es suya o ya no existe | Igual |
  | 422 `texto` | La frase no está en el plan, la firma no es de esa persona y esa conversación, o el texto no se dice ante una sala | Igual |
  | 402 `mnemo_creditos` | Se acabaron los créditos de la cuenta de Mnemo | Igual |
  | 429 `frecuencia`, `volumen` | Los topes de abajo (con `Retry-After`, salvo `volumen`) o el tope por minuto de Mnemo | Igual |
  | 502 `mnemo`, `mnemo_red` | Mnemo falló o no respondió | Igual |

  Cuando Mnemo dice que no puede (la herramienta no está, `NO_VOICE`, `PLAN_REQUIRED`, `UNAVAILABLE` con `reason:
  "speech"`), el panel lo recuerda una hora para esa conexión y esa voz: mientras tanto `GET /api/agente/estado`
  dice `voz.disponible: false`, el navegador ni lo intenta y la caché de la narración se vacía (lo mismo con la
  conexión vencida o revocada, y cuando `GET /api/agente/voces` ya no trae la voz elegida). Un acierto, elegir otra
  voz, volver a conectar o que `GET /api/agente/voces` la vuelva a traer lo olvidan. Con la automática, el «no» es de
  la automática, salvo `NO_VOICE` (esa voz dejó de estar para las apps): entonces el panel anota por 5 minutos que no
  hay automática y después le vuelve a preguntar a Mnemo cuál es (puede haber otra).
- **`GET /api/agente/estado`** trae `voz: {disponible, nombre, respuestas, automatica}`: `disponible` si esta persona
  puede hacer sonar la voz clonada ahora (motor `mnemo`, voz elegida con la cuenta conectada o la automática,
  conexión con `mnemo:voice`, su rol en `roles` y Mnemo no dijo hace poco que no; con la automática, mientras el
  panel no sabe cuál es, se ofrece y `nombre` llega en null); `respuestas` y `automatica`, los ajustes, solo si está
  disponible. **`GET /api/agente/voces`** (solo el administrador) trae `{voces: [{id, nombre, idioma, motor}],
  elegida, automatica, conexion: {voz, ofrece_voz}}`: sin conexión o sin `mnemo:voice`, la lista vacía (sin
  preguntarle a Mnemo); sus errores son los mismos códigos.
- **Las frases de una respuesta.** Si el mensaje del chat llega con `contexto.voz: true` (o la confirmación con
  `voz: true`), la voz está disponible para esa persona y lee respuestas, y la conversación no trae datos de
  habitantes, el turno arma las frases mientras el modelo escribe (`voz.Frases`): corta tras «.», «?», «!», «:», «;»
  o «…» y en los saltos de renglón, con al menos 24 caracteres (lo más corto sigue con lo que viene) y como mucho 260
  (corta en una coma o un espacio que no esté dentro de un número: «300 123 4567» no se parte en dos frases que pasen
  las reglas cada una), nunca tras una abreviatura o una sigla («Sr.», «E.S.E.»), y limpia el Markdown:
  los enlaces quedan en su texto y no se dicen el código, las tablas, las direcciones web, las rutas del panel ni los
  datos enmascarados («···123»). Cada frase cerrada sale como `{"tipo": "frase", "n", "texto", "firma"}` (`n`: su
  número en el turno, desde 0) y, si la ronda se repite o su texto final no es el que se venía diciendo,
  `{"tipo": "frases_descartar", "desde"}` (las frases desde `desde` ya no valen; las que sigan se numeran desde ahí);
  al cerrar una ronda que tuvo un descarte, `{"tipo": "frases_ronda", "desde"}` (la ronda siguiente empieza en
  `desde`). El modelo recibe además, en el contexto de ese mensaje (no en las instrucciones, que quedan fijas), que la
  respuesta se oye con la voz clonada del administrador: frases cortas, lo importante primero, sin listas, tablas ni
  enlaces, con sus propias palabras, sin repetir textualmente lo que la persona le pida decir ni hablar en nombre de
  otro. Desde que el modelo recibe datos de una persona en ese turno, deja de emitir frases.
- **El eco.** La firma prueba que el servidor emitió la frase, no que el sistema la pensó: «repite textualmente: …»
  haría decir a la voz clonada cualquier cosa. Por eso una frase que repite lo que escribió la persona (el mensaje y
  sus mensajes anteriores de la conversación) no se emite ni se firma: entera, si tiene al menos 4 palabras, o con 8
  palabras seguidas iguales, comparadas en forma NFKC, sin mayúsculas ni signos. La respuesta escrita no cambia. No lo
  cierra todo (una paráfrasis o una traducción pasan): `roles` es de confianza.
- **La firma.** `firma` = HMAC-SHA256 de `uid␟conversación␟texto` (`␟` es el separador U+001F), en base64url sin
  relleno (43 caracteres), con una clave derivada de la del administrador (`seguridad.llave_mnemo`, que no está en la
  base) con la etiqueta `voz-respuestas-v1`. El servidor la compara en tiempo constante: el navegador no puede pedir
  que la voz diga otra cosa, ni la frase de otra persona o de otra conversación.

**En el navegador** (`web/js/voz-clonada.js`, `web/js/voz-panel.js`, `web/js/locutor.js`).

- **Una sola voz por ventana.** La narración del plan (la vista de la presentación), las respuestas habladas (el
  asistente) y la prueba de Ajustes usan la misma voz de la ventana (`tomarVoz` de `voz-panel.js`, con conteo de
  referencias: se suelta con la última). Tiene la forma de la voz del navegador (`voz.js`) más `preparar`, `motor` y
  `nivel`, y la del navegador es su respaldo de cada frase. La narración manda: mientras suena un plan (que no está en
  pausa), una respuesta no se dice, y un plan que empieza calla la que se estaba leyendo: cada frase de la narración
  (y la prueba de Ajustes) suelta lo pedido de la respuesta, la frase que sonaba y la precargada, y corta sus
  peticiones (no se pagan sin oírse ni le quitan el lugar a la precarga de la narración). La excepción es la
  [respuesta inmediata](#la-respuesta-inmediata): el locutor marca mientras suena (`marcarAdelanto`), el plan nuevo la
  espera (`adelantoSonando`) y, en esa espera, le cede el turno (`ceder`): sus frases (las que llegan con `adelanto:
  true`) no esperan a ese plan y su primera precarga no las calla.
- **Solo si el estado lo ofrece.** El audio se pide recién cuando `GET /api/agente/estado` dice `voz.disponible` para
  esa persona (el asistente lo pasa al leer su estado; en una ventana sin asistente, la voz lo pide sola y lo vuelve a
  pedir con el aviso `agente:estado` de Ajustes). Si no, ni se crea el audio de la ventana ni se pide nada: habla la del
  navegador.
- **El audio.** Cada frase se pide con `flujo()` de `api.js` (sesión, CSRF, reingreso; sin una línea en 20 s se da por
  cortada) y el PCM se agenda con Web Audio a medida que llega: cada trozo empieza donde termina el anterior, con un
  colchón de 150 ms antes del primero (y otro si se quedó sin audio a mitad). La frase cuenta como empezada cuando suena
  de verdad (el subtítulo se ilumina entonces) y como dicha cuando terminó de sonar. MP3 o WAV (Mnemo sin PCM) se
  decodifican enteros. No hay `<audio>` ni `blob:`: la CSP del panel no cambia.
- **El respaldo.** Si en 4 s no hay audio sonando, o la petición falla antes de sonar (`plan_vencido`, `frecuencia`,
  `mnemo_red`…), esa frase se dice con la voz del navegador; la narración que llega tarde queda guardada para cuando
  se repita. `sin_voz` y `voz_rol` pasan a la voz del navegador el resto de la sesión (y se avisa `agente:estado`). Un
  flujo que ya sonó y se queda 8 s sin traer nada se corta: suena lo que llegó.
- **La precarga y la memoria.** Se piden como mucho 2 frases a la vez (las del servidor por persona: la que suena y la
  siguiente); la que se va a decir pasa delante y la precarga que ya no se quiere (se saltó a otro paso) deja el
  lugar. Una pausa no tira lo de la narración: al seguir, la frase suena al instante sin volver a pedirla. Lo de una
  respuesta o de la prueba se suelta al decirse o al callar. En la página quedan como mucho 8 frases y 24 MB, solo en
  memoria.
- **El gesto.** El audio de la ventana se crea y se reanuda en el gesto de la persona (un toque o una tecla, también
  sobre la presentación, el botón **Voz**, **Leer las respuestas en voz alta** o **Probar voz**), con un búfer mudo de
  una muestra (iOS lo pide). Si el navegador no deja reanudarlo (Safari, con el gesto dentro de un iframe de otro
  origen, o un iPad con el audio «interrumpido»), habla la del navegador y **no se le pide nada a Mnemo**: la frase se
  pide recién con el audio de la ventana andando (si no, se pagaría sin oírse).
- **Probar voz** usa la voz de la ventana con `{prueba: true}`, espera hasta 20 s el primer audio y nunca va con la del
  navegador (no es lo que se prueba): muestra «Primer audio en X ms en este navegador (Mnemo: Y ms)», desde el clic, y
  si salió de la caché del panel; o el mensaje del error.

**Topes** (en memoria, por proceso; la voz gasta créditos de la cuenta de Mnemo, por carácter):

- Por persona: 2 frases a la vez (la que suena y la siguiente, que el navegador precarga), 90 por minuto (429
  `frecuencia`) y 30.000 caracteres por día de lo que de verdad va a Mnemo (429 `volumen`: lo que sale de la caché o
  se cuelga de otra petición no cuenta).
- En el proceso: 3 llamadas a Mnemo a la vez; la cuarta espera hasta 10 s y después 429 `frecuencia` (Mnemo atiende
  hasta 4 voces a la vez por conexión, aparte de sus modelos). En el servicio único, la ruta tiene 6 cupos propios:
  no compite con el chat que se está leyendo en voz alta ni con la API.
- Una frase de Mnemo dura como mucho 125 s y se corta si pasan 30 s sin un trozo; el audio de una frase, hasta 10 MB.

**La caché y un solo vuelo.** El audio de la **narración** y de la **prueba** (texto público de la presentación, que
se repite: **Volver a reproducir**, una pausa, la automática en un televisor) queda en memoria: por
`sha256(voz␟formato␟texto dicho)`, hasta 48 MB (sale primero lo menos usado) y 12 horas; se vacía al cambiar de voz y
en cuanto Mnemo dice que la voz ya no se puede usar (la borraron, la desmarcaron para las apps, el plan no la incluye,
la conexión venció o se revocó, o `GET /api/agente/voces` ya no la trae), y mientras se recuerda ese «no» ni se lee.
Como la automática en un televisor puede vivir de la caché sin volver a llamar a Mnemo, una frase guardada solo se
sirve si Mnemo aceptó esa voz en los últimos 10 minutos; si no, antes se le pregunta si la sigue ofreciendo
(`mnemo_list_voices`, que no gasta créditos): si ya no, 409 `sin_voz` y la caché se vacía; si Mnemo no responde, sale
de la caché. Solo entra una frase que llegó entera. Las **respuestas nunca se guardan**: pueden hablar de personas. Dos peticiones
iguales a la vez (la precarga y la reproducción, o dos ventanas) comparten una sola llamada a Mnemo y reciben lo ya
producido y lo que viene; las de una respuesta solo se juntan con las de la misma persona. Si se van todas (el
navegador cerró, pasó a otra frase), la llamada a Mnemo se cancela; si la respuesta no empieza a leerse en 30 s, se
suelta igual.

**Qué va a la voz** (privacidad). A Mnemo solo va el texto de cada frase, ya pasado por la tabla de pronunciación: de
la narración, lo mismo que se proyecta (sale del guion, sin datos de personas); de una respuesta, lo que el asistente
escribió en una conversación **sin datos de habitantes** (una conversación que los trae, o que los recibe a mitad del
turno, ya no se lee con la voz clonada), y sin «@», números de 7 o más dígitos, código, enlaces ni datos enmascarados.
Mnemo no guarda el texto ni el audio (sí la muestra de la voz, que es de su dueño). En el panel nada se guarda en la
base ni se registra: ni el texto, ni el audio, ni la firma; al registro solo van códigos. La caché de la narración es
solo de memoria y no sobrevive a un reinicio. La voz clonada es un dato biométrico de su dueño: el panel la usa solo
con los roles que el administrador eligió, y Ajustes la marca como **voz sintética**.

## Ajustes

En **Ajustes → Asistente**. Arriba dice si el asistente está encendido y con qué modelo, y está la **Conexión con
Mnemo** (ver [Conectar con Mnemo](#conectar-con-mnemo)): solo el administrador la conecta o la desconecta; el coordinador
ve su estado (sin el nombre ni el correo de la cuenta, que son del administrador). Lo demás son ajustes de permisos:
solo los cambia el administrador; el coordinador los ve en solo lectura. Rigen desde el siguiente mensaje, sin
desplegar.

| Ajuste | Por defecto | Qué decide |
|---|---|---|
| Quiénes lo usan (`agente.roles`) | Administrador y coordinadores | Qué roles ven el asistente. Sin ningún rol marcado queda apagado para todos, también para el administrador |
| Proponer cambios en la base (`agente.escritura`) | Sí | Si se ofrecen las herramientas que escriben (siempre con aprobación). Apagado, el asistente solo consulta |
| Los coordinadores también usan las herramientas de Mnemo (`agente.mnemo_coordinadores`) | No | Si los coordinadores usan las herramientas de Mnemo (documentos, calendario, formularios y memoria), con la cuenta de Mnemo del administrador. Los modelos los usan todos los roles habilitados |
| Días que se guardan las conversaciones (`agente.retencion_dias`) | 30 | De 1 a 365, contados desde el último mensaje. Bajarlo acorta también las que ya existen |
| Mensajes por día (`agente_mensajes_diarios`) | 300 administrador, 150 coordinador, 40 planillero, 40 consultor | Mensajes por persona y día, de 1 a 5000 (cada aprobación o rechazo de tarjetas cuenta como uno). Para que un rol no lo use se lo quita de «Quiénes lo usan» |
| Respuesta inmediata (`agente_adelanto`) | Sí | Si cada pregunta recibe primero una respuesta corta, de una a tres frases, mientras se prepara la completa o la presentación (ver [La respuesta inmediata](#la-respuesta-inmediata)). Es una llamada corta más al modelo por pregunta: apagada, el asistente responde solo con la completa |
| Voz del asistente (`agente_voz`) | La del navegador; la clonada, para administrador y coordinadores, con respuestas y presentación automática | La voz con que narra la presentación y lee las respuestas: la del navegador o una voz clonada de la cuenta de Mnemo conectada, quién la hace sonar y para qué (ver [La voz clonada de Mnemo](#la-voz-clonada-de-mnemo)). Es el bloque **Voz del asistente**, marcado **Voz sintética**: la lista de voces solo se le pide a Mnemo para el administrador y con una conexión que tenga `mnemo:voice` (si no la tiene, el bloque dice que hay que volver a conectar dejando marcado «Hablar con las voces que clonaste en Mnemo…», o que ese Mnemo todavía no ofrece sus voces); el coordinador ve la voz elegida en solo lectura. **Probar voz** dice una frase fija con la voz guardada y muestra cuánto tardó la primera palabra |

Un planillero o consultor habilitado usa el asistente con lo mismo que tiene en el panel: su alcance, su presupuesto
diario de personas (lo que el asistente consulta cuenta) y su límite de búsquedas por minuto. El permiso que lo deja
entrar es `agente.usar` (`app/acceso.py`); el ajuste es el que lo enciende.

Debajo de «Asistente», tres secciones más, también de permisos (solo las cambia el administrador; el coordinador las
ve en solo lectura y el servidor le responde 403), cada una con su aviso legal:

| Ajuste | Por defecto | Qué decide |
|---|---|---|
| **Planillas físicas por foto** · Quiénes suben fotos (`agente_planillas.roles`) | Administrador y coordinadores | Cuál de los dos ve la cámara en el chat y sube fotos en Importar y exportar (además tiene que usar el asistente para hacerlo en el chat). Solo admite administrador y coordinador: nunca planilleros ni consultores (un `planillero` en el `PUT` responde 422, y uno guardado de antes se ignora). Sin ningún rol marcado, apagado. Además hace falta un compromiso de confidencialidad que deje fotografiar planillas (la 2026-11-v2, la de defecto): si no, la sección lo avisa y el administrador tiene **Usar el compromiso 2026-11-v2**. Ver [la excepción de las fotos](#la-excepción-de-las-fotos-de-planillas) |
| Horas que se guardan la foto y lo leído (`agente_planillas.retencion_horas`) | 24 | De 1 a 168. Al cargar la hoja entera la foto y lo leído se borran antes (queda el SHA-256 de la foto en la importación) |
| Leer también listas de asistencia y otros formatos (`agente_planillas.otros_formatos`) | No | Si además de la planilla de campo del panel se leen otros formatos, que pueden traer columnas sensibles. Apagado, una foto de otro formato se rechaza y se borra |
| **Agentes externos por MCP** · Quiénes crean claves de datos (`agente_mcp.roles`) | Administrador | Administrador o coordinadores. Leer personas por MCP es solo del administrador (puede exportar); el coordinador, analítica y propuestas |
| Proponer cambios en la base (`agente_mcp.escritura`) | Sí | Si una clave de datos puede proponer escrituras (cada propuesta espera la aprobación de la persona en Mi cuenta) |
| Llamadas por clave y día (`agente_mcp.llamadas_diarias`) | 2.000 | De 10 a 20.000 |
| Personas distintas por clave y día (`agente_mcp.personas_diarias`) | 300 | De 10 a 5.000 |
| **Datos políticos en el asistente y por MCP** · El asistente del panel (`agente_politicos.asistente`) | Sí | Si el asistente del panel consulta, filtra y propone cambiar los [datos políticos](#datos-políticos) (tipo de persona, «Liderado por», listas, líderes con sus conteos y las bases políticas de importación), cada rol solo lo que ve en el panel y cada cambio con su tarjeta |
| Los agentes externos por MCP (`agente_politicos.mcp`) | Sí | Si los agentes por MCP también los reciben, con la clave de datos de cada persona. Su aviso legal: «La orientación política es un dato sensible (Ley 1581 de 2012, art. 5). El asistente solo la muestra a los roles que ya la ven en el panel, pero lo que consulta viaja al proveedor del modelo y, por MCP, al agente de cada persona: terceros, posiblemente en el exterior. Quien no autorizó y los datos de salud, etnia, discapacidad o víctima nunca salen.» |

Guardar «Planillas físicas por foto» le avisa al asistente (`agente:estado`): quién ve la cámara sale de su estado
(`adjuntos` de `GET /api/agente/estado`, null si el rol o el compromiso no lo permiten) y cambia sin recargar la
página. `GET /api/ajustes` trae además `compromiso_permite_fotos` y `compromiso_con_fotos`. Los ajustes viven en `meta`
con los demás y los validan `politica.ajustes_planillas`, `politica.ajustes_mcp` y `politica.ajustes_politicos` (un
valor que no tiene la forma esperada toma el de defecto; `PUT /api/ajustes` acepta `{"agente_politicos": {"asistente":
bool, "mcp": bool}}`, booleanos estrictos y sin otras claves). Un cambio de `agente_politicos` vale desde el siguiente
mensaje o la siguiente llamada por MCP. Las instrucciones y las herramientas de una conversación ya abierta no cambian
(dicen lo que valía al crearla): apagarlo corta lo político desde el siguiente mensaje también en las conversaciones
abiertas, y encenderlo vale solo para las conversaciones nuevas (una creada con el ajuste apagado sigue sin recibirlo,
porque sus instrucciones no traen las reglas de lo político: `Contexto.politicos_conversacion`). La bienvenida no
sugiere preguntas políticas con el ajuste apagado ni de planillas por foto a quien no puede subirlas.

## Conectar con Mnemo

**Qué aporta.** Mnemo es el espacio de trabajo personal de la administración y, para el panel, quien pone los modelos.
Su herramienta `mnemo_model_complete` responde cada ronda del asistente con los modelos y los créditos de la cuenta
conectada (el permiso `mnemo:model`): el panel sigue corriendo sus propias herramientas con la sesión de quien
conversa, y Mnemo solo responde como modelo, sin guardar lo que se le envía ni lo que responde. Con la misma conexión,
el asistente puede buscar y leer los documentos del administrador, consultar el calendario y crear o mover eventos,
consultar formularios y guardar borradores, crear, cambiar y exportar documentos del lienzo, proponer recuerdos y pedir
que algo se comparta o se publique (eso lo aprueba el administrador en Mnemo, con un enlace que el asistente le da). Por
ejemplo: «agenda en mi calendario de Mnemo la reunión del jueves en San Miguel del Tigre» o «¿qué dice mi documento de
la estrategia de veredas?».

**Cómo se conecta.** Solo el administrador; el coordinador ve el estado.

1. En **Ajustes → Asistente → Conexión con Mnemo**, revise la **Dirección MCP de Mnemo** (`https://<su Mnemo>/mcp`).
   Viene sugerida por `MNEMO_MCP_URL` o por la última conexión; si no, escríbala (Mnemo la muestra en **Tu cuenta →
   Agentes conectados**).
2. Pulse **Conectar con Mnemo**. La misma pestaña va a Mnemo.
3. Inicie sesión en Mnemo con la cuenta que va a poner los modelos, revise los permisos y pulse **Permitir**. Deje
   marcado **«Usar tus modelos de IA y tus créditos»**: sin él, Mnemo conecta solo las herramientas y Ajustes avisa
   «Mnemo se conectó sin permiso para usar sus modelos: vuelva a conectar dejando marcado «Usar tus modelos de IA y
   tus créditos»». Mnemo trae marcados solo ese y «Leer tu información»: los de escritura (eventos y documentos,
   recuerdos, compartir, publicar) son para que las herramientas de Mnemo también escriban (siempre con la aprobación
   de la tarjeta); márquelos si lo quiere. Para la [voz clonada](#la-voz-clonada-de-mnemo), deje marcado también
   **«Hablar con las voces que clonaste en Mnemo…»** (`mnemo:voice`): sin él, el panel narra y lee con la voz del
   navegador, y Ajustes avisa que hay que volver a conectar dejándolo marcado. Un Mnemo sin actualizar no tiene la
   casilla de los modelos: con él, **Conectar con Mnemo** no va a Mnemo y avisa que hay que actualizarlo (ver «Lo que
   Mnemo necesita», más abajo).
4. Mnemo lo trae de vuelta a Ajustes, que muestra **Conectado como** la cuenta (nombre y correo), desde cuándo, la
   dirección y los permisos. Si canceló en Mnemo, lo dice y no conecta nada.

Lo que pide el panel, en este orden: `openid`, `profile` y `email` (solo para mostrar con qué cuenta se conectó),
`mnemo:model`, `mnemo:voice` (la voz clonada; solo si ese Mnemo lo anuncia en `scopes_supported`: uno anterior no
lo tiene y se conecta igual, sin la voz) y los permisos que necesitan las herramientas de Mnemo que ofrece (con la
lista por defecto, `mnemo:read`, `mnemo:workspace.write`, `mnemo:memory.write`, `mnemo:share` y `mnemo:publish`).
Nunca `mnemo:forms.responses`: las respuestas de los formularios son datos de otras personas y llegarían al modelo. Con
solo `mnemo:read`, las herramientas de Mnemo solo leen: lo demás responde que a la conexión le faltan permisos.

**Una sola conexión para todo el panel.** Todos los roles que usan el asistente gastan los modelos y los créditos de
esa cuenta, cada uno con su tope de mensajes por día. Las herramientas de Mnemo (documentos, calendario…) son otra
cosa: ver [quién las usa](#quién-usa-las-herramientas-de-mnemo).

**Volver a conectar y desconectar.** **Volver a conectar** repite el permiso: para marcar una casilla, tras una caída
o, con otra dirección, para cambiar de Mnemo. Con la misma cuenta, Mnemo actualiza la misma conexión (no queda otra
suelta). **Desconectar** pide confirmación, revoca la conexión en Mnemo y la borra del panel. Si Mnemo no confirma la
revocación, el panel la borra igual y lo avisa: revóquela en Mnemo, en **Tu cuenta → Agentes conectados**. Ahí también
se ve el registro de llamadas del panel y se puede revocar la conexión en cualquier momento: el asistente se queda sin
los modelos de Mnemo al instante.

| Estado en Ajustes | Qué pasó | Qué hacer |
|---|---|---|
| Sin conectar | Nunca se conectó, o se desconectó | **Conectar con Mnemo** |
| Conectado | Rige: el asistente usa esa cuenta | Nada |
| Conectado, con el aviso «sin permiso para usar sus modelos» | En Mnemo no quedó marcado «Usar tus modelos de IA y tus créditos», o esa versión de Mnemo todavía no lo tiene | **Volver a conectar** dejándolo marcado; si Mnemo no muestra esa casilla, actualizar Mnemo |
| Conectado, con el aviso «Este Mnemo todavía no ofrece…» | Solo en modo directo: Mnemo no está actualizado y se conectó solo para sus herramientas | Actualizar Mnemo y **Volver a conectar** |
| Conectado, con la voz clonada elegida y el aviso «sin permiso para usar sus voces» | En Mnemo no quedó marcado «Hablar con las voces que clonaste en Mnemo…», o la conexión es de antes de la voz clonada | **Volver a conectar** dejándolo marcado; si Mnemo no muestra esa casilla, actualizar Mnemo. Mientras tanto, la voz del navegador |
| Conexión caída: Mnemo ya no la acepta | Se revocó en Mnemo, venció (30 días sin usarse, o un año desde el último permiso) o la cuenta se desactivó | **Volver a conectar** |
| Conexión caída: cambió la clave del administrador | Cambiaron `ADMIN` o `password` y lo guardado ya no se puede descifrar | **Volver a conectar**; la conexión vieja puede seguir en Mnemo: revóquela ahí |
| Conexión caída: sus datos no coinciden con los cifrados | Alguien cambió en MongoDB la conexión guardada (por ejemplo, la dirección de Mnemo): el panel dejó de usarla sin mandar nada | Revisar quién puede escribir en la base y **Volver a conectar** |
| Conexión caída: Mnemo respondió algo inesperado | La renovación del acceso falló | **Volver a conectar** |

**Lo que Mnemo necesita.**

- El inicio de sesión para agentes (OAuth) activo: en el despliegue de Mnemo, `PUBLIC_BASE_URL` (su dirección
  pública). Sin ella, conectar responde «Mnemo no tiene OAuth: falta PUBLIC_BASE_URL en su despliegue.»
- Una versión con la herramienta `mnemo_model_complete` y el permiso «Usar tus modelos de IA y tus créditos» (lo
  anuncia en `/.well-known/oauth-authorization-server`, en `scopes_supported`). Con una anterior, **Conectar con
  Mnemo** no conecta nada y avisa «Este Mnemo todavía no ofrece «Usar tus modelos de IA y tus créditos»…: hay que
  actualizar Mnemo». Solo en [modo directo](#modo-directo-sin-mnemo) la conecta igual, para sus herramientas, y
  Ajustes avisa que ese Mnemo no ofrece sus modelos.
- Que la cuenta pueda responder: un plan que incluya el chat o una clave propia de un proveedor de modelos configurada
  en Mnemo, y créditos. Si no, el asistente lo dice al responder (sin plan, sin créditos o sin un modelo disponible).
- Para las [planillas físicas por foto](#planillas-físicas-por-foto): un modelo de la cuenta que lea imágenes. Si el
  principal no las lee, elíjalo en Mnemo, en **Ajustes → Modelos → Plantel**, «leer imágenes» (o use como principal
  uno que las lea), con una versión de Mnemo que acepte el modelo `vision` en `mnemo_model_complete`: con una
  anterior, la foto va al modelo de siempre, y si ese no la ve el mensaje pide actualizar Mnemo. Si no, la lectura
  falla con «Ningún modelo de la cuenta de Mnemo conectada lee imágenes…» (`mnemo_sin_vision`) o, si llegó a un modelo
  que no las lee, «El modelo que respondió (…) no pudo ver la foto…», con el nombre de ese modelo.
- Para la [voz clonada](#la-voz-clonada-de-mnemo) (opcional): una versión con `mnemo_speak` y `mnemo_list_voices` y el
  permiso `mnemo:voice`, un plan que incluya las voces clonadas, créditos y al menos una voz marcada **Disponible
  para apps conectadas**. Sin eso, el panel sigue con la voz del navegador.

**Variables** (todas opcionales; la conexión no es una variable):

| Variable | Valor |
|---|---|
| `MNEMO_MCP_URL` | La dirección MCP de Mnemo que Ajustes sugiere al conectar: `https://<su Mnemo>/mcp` (en local también `http://127.0.0.1` o `http://localhost`). Otra cosa se ignora con un aviso en el registro. No es secreta y no conecta nada por sí sola |
| `MNEMO_MODELO` | Qué modelo de la cuenta usa el asistente: `principal` (el que la cuenta tiene por defecto), `ligero` (su modelo rápido; si no tiene, el principal) o `<proveedor>/<modelo>` (uno concreto que la cuenta tenga). Vacía, el que la cuenta tenga por defecto. Otro valor se ignora con un aviso en el registro. No vale para leer las fotos de planillas: esas van al modelo de la cuenta para leer imágenes, salvo con un Mnemo anterior que no acepta ese modelo (ver [Planillas físicas por foto](#planillas-físicas-por-foto)) |
| `MNEMO_HERRAMIENTAS` | Vacía, la lista por defecto: `search`, `fetch`, `mnemo_get_briefing`, `mnemo_list_items`, `mnemo_view_image`, `mnemo_list_events`, `mnemo_create_event`, `mnemo_update_event`, `mnemo_query_forms`, `mnemo_save_form_draft`, `mnemo_create_document`, `mnemo_update_document`, `mnemo_export_document`, `mnemo_save_memory`, `mnemo_list_shared_with_me`, `mnemo_request_publish`, `mnemo_request_share`, `mnemo_check_approval` y `mnemo_get_job`. Se cambia por nombres separados por comas, o `*` para todas las que permita la conexión (las 30 pesan mucho en cada mensaje). Decide también qué permisos se piden al conectar |

`MNEMO_TOKEN` ya no se usa: si sigue definida, el panel la ignora y lo avisa en el registro. Bórrela de Railway y
revoque ese token personal en Mnemo.

### Quién usa las herramientas de Mnemo

La conexión es de la cuenta del administrador: quien usa las herramientas de Mnemo actúa *como el administrador* en sus
documentos, su calendario y su memoria, y Mnemo no distingue quién del panel pidió cada cosa. Por eso las usa el
administrador, los coordinadores solo si él lo permite en **Ajustes**, y planilleros y consultores nunca. Se decide
antes de cada herramienta de Mnemo, con la sesión y los ajustes de ese momento: apagar el ajuste, o desactivar al
coordinador, vale también para las conversaciones abiertas y para el turno en curso. Usar los modelos es distinto: lo
hacen todos los roles habilitados, y no lee ni escribe nada del Mnemo del administrador.

**Cómo se controla.**

- Toda escritura en Mnemo pasa primero por la tarjeta de aprobación del panel, que muestra los argumentos exactos (sus
  nombres y sus valores enteros, como se mandan: lo que no se vería así no se propone). Lo que Mnemo no hace sin
  permiso (compartir, publicar) pide además su propia aprobación en Mnemo, con la sesión del administrador: el
  asistente devuelve el enlace y no da nada por hecho antes de que se apruebe.
- Cada escritura aprobada se manda a Mnemo una sola vez: Mnemo no tiene clave de idempotencia, así que si la misma
  tarjeta llegara a aprobarse otra vez (un turno cortado), el asistente no la repite y pide revisarla en Mnemo.
- Lo que solo lee (buscar, leer, listar, el calendario y los formularios, exportar un documento) corre sin tarjeta,
  como las lecturas del panel: no cambia nada en Mnemo. Es a propósito: la tarjeta es para lo que cambia algo. Sus
  argumentos (lo que se busca, por ejemplo) los arma el modelo, por eso las instrucciones le piden no llevar datos de
  habitantes a Mnemo. Exportar da un enlace de descarga que vale unos 15 minutos sin iniciar sesión: llega a la
  conversación como cualquier resultado.
- En **Tu cuenta → Agentes conectados**, Mnemo muestra la conexión del panel («Panel Trabajemos juntos»), sus permisos
  y su registro de llamadas. Revocarla ahí corta el acceso al instante.
- Mnemo limita cada conexión, para todo el panel junto: 60 lecturas y 20 escrituras por minuto en sus herramientas, y
  60 respuestas del modelo por minuto con como mucho 4 a la vez.
- Si Mnemo no responde al empezar una conversación, esa conversación sigue sin sus herramientas (con un aviso); si
  falla después, la herramienta devuelve el error y el asistente lo explica.
- Lo que viene de Mnemo (documentos, formularios) son datos, no instrucciones. Y el asistente no copia datos de
  habitantes a Mnemo salvo que se le pida expresamente: el compromiso de confidencialidad sigue valiendo.

### Cómo se guarda la conexión

Los tokens de la conexión (el de acceso, que dura una hora, y el de renovación, que Mnemo cambia en cada uso) se
guardan cifrados (AES-GCM) en MongoDB, en el documento `mnemo_conexion` de `meta`, con una clave que sale de `ADMIN` y
`password` y no está en la base: una copia de la base sola no da acceso al Mnemo del administrador ni a sus créditos.
Por eso, si cambian `ADMIN` o `password`, la conexión queda caída y hay que volver a conectar. Las direcciones a las que
el panel manda esos tokens (la de Mnemo y las de renovar y revocar, también las de una conexión a medias) van además
dentro de lo cifrado: quien pueda escribir en la base tampoco puede desviarlos a otro sitio (si no coinciden con las
cifradas, el panel no manda nada y la conexión queda caída). El panel renueva el acceso solo, con una sola renovación
a la vez aunque corran varios procesos (Mnemo revoca la conexión entera si le llega un token de renovación ya usado).
Los tokens nunca llegan al navegador, a las respuestas ni a los registros. La auditoría guarda `mnemo_conectar`,
`mnemo_desconectar` y `mnemo_caida` (esta, del sistema), sin tokens.

## Modo directo (sin Mnemo)

`ANTHROPIC_API_KEY` es opcional: con una clave de la consola de Anthropic, el asistente usa Claude directamente cuando
no hay una conexión con Mnemo con permiso para usar sus modelos (para desarrollo, o como respaldo a propósito). Si hay
las dos, manda Mnemo. Cada conversación sigue con el modelo con que empezó: conectar Mnemo no cambia las que ya estaban
en modo directo, y si el de una conversación ya no está (se quitó la clave o se desconectó Mnemo), el asistente ofrece
empezar otra. Ajustes dice cuál rige.

## Privacidad y protección de datos (Ley 1581 de 2012)

El modelo corre fuera del panel: con Mnemo conectado, cada ronda va a Mnemo y Mnemo la pasa al proveedor de modelos
que esa cuenta tenga elegido (Mnemo no guarda lo que se envía ni lo que responde el modelo); en modo directo, va a
Anthropic. Todo lo que el asistente le manda sale del panel. Por eso se le manda lo mínimo, y siempre después de la
proyección por rol de la API (`app/agente/minimizar.py`).

**Qué va al modelo.**

- Lo que escribe la persona y el contexto de la vista (`app/agente/sistema.py`): la ruta (sin la consulta ni el
  fragmento, y solo si es una del panel), la entrada del menú que está abierta, el número de la ficha o la reunión
  abierta, los filtros de la dirección que el asistente también puede usar y el encuadre del mapa. Lo decide el
  servidor, mande lo que mande el navegador: la búsqueda de Habitantes va solo si no lleva números ni un correo (si
  no, el asistente sabe que hay una búsqueda, no qué se buscó), una etiqueta solo si existe y no es sensible, y del
  mapa va el zoom y, solo de lejos (zoom de 14 o menos), el centro con dos decimales (unos 1,1 km).
- El nombre y el rol de quien conversa, en las instrucciones del asistente.
- Lo que devuelven las herramientas, recortado: de cada habitante, lo necesario para la tarea (nombre, barrio o
  vereda, sexo y edad, si es menor, estudios, ocupación y hogar, puesto y mesa, autorización y abordaje, qué le falta
  a la ficha…), con la cédula y los teléfonos enmascarados («···123», «···2233») también para el administrador, y las
  notas, la dirección, las observaciones, el lugar escrito a mano (el que queda cuando el panel no reconoce el barrio
  o vereda, también en las filas de una búsqueda, una cola o una reunión) y los campos propios recortados y con los
  correos y los números de 7 o más dígitos tapados («···233»), también escritos por grupos, con espacios, guiones o
  puntos entre ellos («300 111 22 33», «604 - 832 12 34», «(604) 832 12 34», «71.234.567»). Las fechas, los periodos
  y las direcciones quedan como están («07 / 11 / 2026», «2018 - 2022», «calle 50 # 48 - 21»). Indicadores agregados
  y reuniones.
- Con Mnemo, lo que lee del espacio del administrador.
- Los [datos políticos](#datos-políticos), con `agente_politicos.asistente` encendido (por defecto): el tipo de
  persona, el «Liderado por», las listas, las fuentes y la lista de líderes, cada rol solo lo que ve en el panel (A y K,
  todo; P, el tipo y el «Liderado por» en las fichas de su zona o de quien registró; C, nada). Son afiliación política,
  un dato sensible (Ley 1581, art. 5): lo que se consulta viaja al proveedor del modelo como lo demás.
- De los [análisis](#análisis-avanzados), solo agregados ya protegidos: ninguna persona (salvo, con los datos
  políticos, los líderes de 10 o más personas que nombra una tabla por `lider`), las cifras de 1 a 4 como «<5» y otras
  ocultas para que no se deduzcan, nada de quien no autorizó, nada sensible y lo político (tipo, líder, lista) solo con
  el ajuste y con la misma supresión.
- De las [planillas por foto](#planillas-físicas-por-foto), el bloque `<fotos_adjuntas>` (ids y estado) y lo leído,
  **enmascarado**: cédula con sus 3 últimos dígitos y si coincide con su repetición, teléfonos con sus 4 últimos
  (ninguno de un menor), la edad en vez de la fecha de nacimiento, si hay observaciones (no su texto), los textos con
  `texto_libre`; de quien dijo «No autoriza» o ya está en «no», solo nombre y barrio; de quien pidió la supresión, solo
  que la fila no se carga. Del cotejo, las fichas encontradas con `minimizar.fila` y lo distinto enmascarado; de las
  filas en «no», ninguna ficha. La imagen nunca va al modelo de la conversación: va entera solo en la llamada de
  lectura aparte ([la excepción](#la-excepción-de-las-fotos-de-planillas)).
- De las colas de calidad y los registros de cada persona, lo de la lista blanca de cada herramienta ([Registros de cada
  persona y calidad de datos](#registros-de-cada-persona-y-calidad-de-datos)).
- Con la [respuesta inmediata](#la-respuesta-inmediata), una petición más al mismo proveedor con el texto de los
  últimos 8 mensajes de la conversación (sin resultados de herramientas) y el mensaje nuevo con su contexto: nada que
  no haya recibido ya.
- En cada ronda, las instrucciones del asistente, las herramientas que ofrece el panel y la conversación: con Mnemo, eso
  es lo que reciben Mnemo y su proveedor de modelos.

**Qué va a la voz.** Con la [voz clonada de Mnemo](#la-voz-clonada-de-mnemo), a Mnemo (y al proveedor de voz de esa
cuenta) va solo el texto de cada frase que se dice: la narración (lo mismo que se proyecta, sin datos de personas) y,
si la persona lo pide, las frases de las respuestas de una conversación sin datos de habitantes, sin «@», números de 7
o más dígitos, código, enlaces ni datos enmascarados. Ni Mnemo ni el panel guardan ese texto ni el audio; el panel solo
deja en memoria el audio de la narración, y al registro van solo códigos.

**Qué nunca va al modelo.**

- Los datos sensibles (salud, `regimen_salud`, etnia, discapacidad, condición de víctima, huellas) ni las etiquetas o
  campos propios marcados como sensibles, con el ajuste político encendido o apagado.
- Los datos políticos que el panel no le muestra al rol, y ninguno con `agente_politicos.asistente` apagado. Nada
  político de quien no autorizó: ni su tipo, ni como líder en el «Liderado por» de otra persona, en la lista de líderes
  o en una tabla por líder.
- La cédula y los teléfonos completos, el correo, el punto exacto, la fecha de nacimiento exacta, el número de ficha,
  los trámites, la procedencia y el historial de cada dato, ni quién registró qué.
- Del contexto de la vista: la consulta y el fragmento de la ruta (lo que va después de «?» o «#»: lo que sirve va,
  si va, como filtro), una ruta que no es del panel o un nombre de vista que no es del menú (lo que mande el
  navegador), lo buscado en Habitantes con números o un correo (se escribió en el panel, no al asistente), los
  filtros de lista de origen, liderazgo, régimen de salud o fuente de cédulas, una etiqueta sensible o que no existe
  (con la ficha abierta desde esa lista, diría un dato sensible de esa persona), la selección (`ids`) y el dibujo
  (`poligono`) del mapa, lo que no es un filtro (como lo que trae la vuelta de Mnemo) y el centro del mapa visto de
  cerca: al resaltar a una sola persona, el mapa se encuadra en ella y el centro sería su punto.
- De quien marcó **No autorizó**, nada más que quién es, que no autorizó y su barrio o vereda del nomenclátor, ni
  siquiera para el administrador. Nunca el lugar escrito a mano, que puede traer un número, una dirección o a quién
  preguntar: si la herramienta no puede comprobar que el lugar es un barrio o vereda del nomenclátor, va sin lugar.
  Las búsquedas, los conteos, el mapa, las reuniones y Mi trabajo tampoco dejan deducir nada más de esa persona (ver
  [Qué puede hacer](#qué-puede-hacer)). Para verla, se abre la ficha en el panel.
- En una búsqueda por número (la cédula o el teléfono completos), las filas van sin los dígitos enmascarados: no le
  suman nada a lo que se escribió, y si alguna vez casara una parte del número, juntarla con el final lo
  reconstruiría.
- De las solicitudes de los titulares, de quién es cada una, lo que pidió y lo que se le respondió (que alguien pidió
  suprimir sus datos es un dato suyo); de las coincidencias, el texto de sus señales (solo su clave); de los conflictos
  y las importaciones, las fuentes que no son trámites ni planilla (con los datos políticos apagados); de los
  acercamientos, el teléfono marcado y lo
  dictado; de las autorizaciones, las categorías sensibles autorizadas, la evidencia escrita y la fila de la planilla.
- De una planilla por foto: la imagen, la cédula y los teléfonos completos, la fecha de nacimiento exacta, el texto de
  las observaciones y por qué una fila no se carga.
- La clave de Anthropic, los tokens de la conexión con Mnemo, las claves de los usuarios, las claves MCP, las sesiones
  (también las internas de MCP) ni las IP.

**Agentes por MCP con datos.** Con una [clave de datos](#agentes-por-mcp-con-datos), lo que el agente lee sale del
panel hacia un cliente que la persona elige (Claude Desktop, ChatGPT…): un tercero fuera del contrato del panel. Por
eso leer personas es solo del administrador, la clave vence a los 30 días y solo viaja en la cabecera, cada entrega
queda registrada (`mcp_entregas`, `entrega_mcp`), hay topes diarios de llamadas y de personas, y por MCP no sale nada
de quien no autorizó. Los datos políticos salen por MCP solo con `agente_politicos.mcp` encendido, y como el panel se
los muestra a la persona de la clave. Antes de dar una clave de datos con `lectura`, revise con un abogado que el aviso
de privacidad cubra esa transmisión.

**Retención.** Las conversaciones se guardan en MongoDB (`agente_conversaciones` y `agente_mensajes`) y se borran
solas a los días de **Ajustes** desde su último mensaje (30 por defecto). Bajar ese plazo acorta también las que ya
existen: las que ya lo pasaron se borran en cuanto MongoDB lo revisa (cada minuto). Su dueño las puede borrar antes.
El uso (`agente_uso`: mensajes, tokens y créditos por persona y día, sin contenido) se guarda 180 días. Las fotos de
planillas y lo leído (`planillas`, cifrados) vencen a las `agente_planillas.retencion_horas` (24 por defecto) o se
borran al cargar la hoja entera; el registro de subidas que cuenta los topes (`planillas_subidas`: quién y cuándo), a
las 26 horas. Las propuestas por MCP (`mcp_propuestas`) vencen a las 48 horas y, decididas, pierden la tarjeta y se
borran a los 7 días; las claves de datos, a los 30 días; el registro de entregas por MCP (`mcp_entregas`: solo ids), a
los 90 días, como `lecturas`.

**Supresión y revocatoria.** Cada conversación anota de qué personas recibió datos el modelo (y cuáles mostró una
tarjeta). Al **suprimir** a una persona, se borran enteras las conversaciones donde aparecía (y la reconciliación de
cada arranque repasa las que hayan quedado); si la supresión llega mientras el asistente la está leyendo, el turno
termina y esa conversación también se borra. Lo mismo cuando deja de autorizar (un «no» o una revocatoria, por el
panel, con «no contactar», por una importación o al unir su ficha con la de quien no autorizó): sus datos no siguen en
el historial que se le reenvía al modelo en cada ronda, aunque la conversación sea la que registró la revocatoria, y si
el «no» llega mientras el asistente la está leyendo (también entre las fichas que devuelve una escritura, como las
parecidas del alta), el turno termina y esa conversación se borra (para eso queda una hora en `agente_olvidos` quién
dejó de autorizar, sin ningún otro dato). Al cambiarle el rol o la zona a un usuario (también desde **Zonas**), o al
desactivarlo, se borran sus conversaciones. La supresión y el «no» borran también las propuestas por MCP que muestran a
esa persona (`db.borrar_propuestas_mcp`). Al **suprimir**, sus filas en las planillas por foto (las que el cotejo o la
carga le asignaron, o las que casan con las huellas de su cédula o de su nombre con un teléfono) quedan marcadas y nunca
vuelven a salir, la próxima escritura las deja vacías en lo cifrado y la foto, que también la muestra, se borra
(`db.vaciar_planillas`); una lectura o una carga que estaba en curso no las vuelve a escribir. `mcp_entregas` y
`lecturas` se conservan (solo ids: dicen a quién se entregó, para responder un reclamo).

**Transferencia al proveedor del modelo.** Mandar datos personales a Mnemo y al proveedor de modelos de esa cuenta
(o a Anthropic, en modo directo), terceros posiblemente en el exterior, es una transmisión internacional de datos
(Ley 1581 de 2012, art. 26, y el contrato de transmisión del Decreto 1377 de 2013). Antes de encender el asistente para
el equipo con datos reales:

1. Revise con un abogado el **aviso de privacidad** y la **autorización**: deben informar esta finalidad y que
   proveedores tecnológicos, posiblemente en el exterior, procesan los datos, y lo que exijan las orientaciones de la
   SIC sobre inteligencia artificial y datos personales.
2. Revise los términos vigentes de Mnemo, del proveedor de modelos y, con la voz clonada, del proveedor de voz (fal.ai
   y el modelo de voz) que use la cuenta (cuánto guardan lo que reciben, dónde y para qué) y acepte o firme sus
   acuerdos de tratamiento de datos. En modo directo, los de Anthropic (a la
   fecha de este documento, sus términos comerciales dicen que no entrena modelos con los datos de la API).
3. Empiece con el administrador y los coordinadores (lo que viene por defecto) y habilite a planilleros y consultores
   después de la revisión y de explicarles qué se le puede pedir.
4. Las **fotos de planillas** son una transmisión más amplia (la imagen entera, no lo mínimo): antes de usarlas con
   datos reales, la revisión del aviso (ver [La excepción de las fotos de
   planillas](#la-excepción-de-las-fotos-de-planillas)). El compromiso de confidencialidad ya lo permite desde la
   versión 2026-11-v2, la de defecto. Las **claves de datos por MCP** sacan datos hacia el cliente que elige cada
   persona: el aviso también tiene que cubrirlo antes de dar una con `lectura`.
5. Los **datos políticos** (afiliación política, un dato sensible: Ley 1581, art. 5) van también a esos terceros con
   `agente_politicos` encendido (por defecto, en el asistente y por MCP): entran en la revisión del punto 1. Para que no
   salgan, se apaga en **Ajustes → Datos políticos en el asistente y por MCP**.

Los datos de bases oficiales (como las del SISBÉN) siguen sirviendo solo para la finalidad con que se recogieron,
también a través del asistente.

### La excepción de las fotos de planillas

El principio de «al modelo le llega lo mínimo» tiene **una excepción documentada**: la foto de una planilla física
(con nombres, cédulas, teléfonos, fechas de nacimiento, direcciones y firmas de las personas de la hoja) **va entera
al proveedor del modelo** (Mnemo y su proveedor, o Anthropic en modo directo), en una llamada de lectura aparte, sin
herramientas ni conversación, para transcribirla. Lo leído queda en el servidor y al modelo de la conversación le
llega enmascarado. Es lo que permite cargar lo que no se pudo hacer de forma digital, y por eso:

- **Revisión jurídica antes de encenderlo.** `agente_planillas` viene encendido para administrador y coordinadores en
  el código, pero no se debe usar con datos reales hasta que un abogado revise el aviso de privacidad y la
  autorización: tienen que informar que las imágenes completas de las planillas van a proveedores tecnológicos,
  posiblemente en el exterior (Ley 1581, art. 26; Decreto 1377 de 2013), además de lo que ya informan para el
  asistente (ver **Transferencia al proveedor del modelo**, arriba). Mientras tanto, apague la sección en
  **Ajustes**.
- **El compromiso de confidencialidad lo permite.** La versión 2026-11-v2 de `acceso.COMPROMISOS` (la de defecto en
  `compromiso_version`) deja fotografiar planillas físicas solo para subirlas por el panel (la cámara del asistente o
  Importar y exportar → Planillas por foto), nunca cédulas ni otros documentos, y pide borrar la foto del teléfono
  después de subirla; la 2026-11-v1 lo prohibía. Con un compromiso vigente que no lo permite, nadie sube fotos (409
  `compromiso_fotos`; ver [Planillas físicas por foto](#planillas-físicas-por-foto)).
- **Solo el administrador y los coordinadores.** Toman y suben las fotos solo A y K (`importar`); los planilleros
  entregan el papel y quedan como «Capturado por».
- **Solo lo que hace falta en la foto.** Por defecto solo se lee la planilla de campo del panel, que no tiene columnas
  sensibles (`otros_formatos` apagado). El aviso fijo junto a la cámara pide no fotografiar cédulas, tapar las
  columnas de salud, etnia, víctima o políticas y borrar la foto del teléfono (las políticas también: el lector no
  las transcribe, así que en la foto solo llegarían al proveedor, también con `agente_politicos` apagado; el tipo y el
  líder se marcan aparte, con el papel a la vista). Una foto de un documento de identidad se rechaza y se borra. Las
  instrucciones del lector prohíben transcribir datos sensibles (salud, etnia, discapacidad, condición de víctima,
  huellas) o políticos, y el servidor solo guarda las 20 columnas de la planilla: aun así, lo que está en la imagen
  **llega al proveedor**, que es por lo que hay que taparlo en el papel.
- **El teléfono de quien toma la foto.** Lo que se toma con la cámara o se elige de la galería queda en el teléfono (y
  en su copia en la nube, si la tiene), fuera del control del panel: el aviso pide borrarla. El navegador rehace la foto
  antes de subirla (derecha, reducida y como un JPEG nuevo: sin EXIF, GPS ni el modelo del teléfono), no la guarda en
  `localStorage`, `sessionStorage` ni IndexedDB y la muestra solo en un canvas (nunca en una dirección `blob:` o
  `.src`).
- **Lo que se guarda y cuánto.** La foto limpia (el servidor vuelve a quitar metadatos y lo que venga después del fin
  de la imagen) y lo leído se guardan **cifrados** con AES-GCM (`agente/cifrado.py`, `cifrar_bytes`), con una llave
  derivada de la credencial del administrador con una etiqueta propia (no está en la base) y atados a su planilla y a
  quien la subió: un respaldo de la base no los abre, y si cambian `ADMIN` o `password` ya no abren (se vuelve a
  subir). Todo vence a las `agente_planillas.retencion_horas` (24 por defecto, índice TTL) y, al cargar la hoja entera,
  la foto y lo leído se borran antes: queda en la importación el SHA-256 de la foto, el folio que escribió la persona
  (dónde queda el papel) y, por fila, solo número, estado y ficha.
- **Por fila, antes de guardar** (también tras cada corrección): de alguien que pidió la supresión (por las huellas de
  su cédula, o de su nombre con un teléfono, como el importador), nada: «no se carga», sin motivo; de «No autoriza»,
  solo número, nombre, cédula y barrio, y la negativa; de alguien que ya está en «no» por su cédula exacta, lo mismo.
- **Autorizaciones siempre declaradas.** Todo «sí» leído de una foto se guarda como `declarado_planilla` (el medio leído
  va a `datos.medio_leido`): no habilita llamadas ni mensajes hasta que A o K lo confirme con el papel en Importar y
  exportar. Un «sí» dudoso o ilegible cuenta como sin marcar; un «no» dudoso se trata como «no» (protege a quien quizá
  no autorizó; A o K lo corrigen con el papel a la vista). El asistente no puede confirmarlas ni corregir la
  autorización, el medio, los canales o «mayor de 18».
- **Inyección por la foto.** Lo escrito en la hoja es un dato: lo dicen las instrucciones del lector y las del
  asistente, cada valor se guarda en una sola línea sin caracteres invisibles, la tarjeta calcula la autorización en una
  forma fija y muestra aparte lo que el asistente corrigió, y aunque el modelo obedeciera algo escrito en el papel, no
  puede cargar sin la aprobación de la tarjeta.
- **Auditoría sin datos de personas**: `subir_planilla` (SHA-256, tamaño, formato), `leer_planilla` (número de lectura,
  filas, dudosas, proveedor o el error), `corregir_planilla`, `borrar_planilla`, `cargar_planilla` y la `importar` de
  siempre, con `entidad: "planilla"`.

## Límites y costos

**Modelo y esfuerzo con Mnemo.** El modelo es el que la cuenta de Mnemo tenga por defecto, o el de `MNEMO_MODELO` (la
foto de una planilla, el que la cuenta tenga para leer imágenes), y el costo son créditos de Mnemo, según el plan de la
cuenta (o su clave propia de un proveedor). `AGENTE_ESFUERZO` vale también: `low` y `medium` pasan tal cual, y `high`,
`xhigh` y `max` piden el razonamiento alto (un modelo sin razonamiento lo ignora). Cada ronda escribe como mucho 16.000
tokens, y `agente_uso` guarda también los créditos que informa Mnemo. El razonamiento del modelo no se muestra: con
Mnemo son resúmenes internos, no notas para la persona.

**Modelo y esfuerzo en modo directo.** Por defecto usa `claude-opus-5-5` (Claude Opus 5.5) con esfuerzo `medium`.
`AGENTE_MODELO` cambia el modelo (por ejemplo `claude-sonnet-5-5`, más barato y rápido, o `claude-fable-5-1`, el más
capaz y más caro) y `AGENTE_ESFUERZO` cuánto razona antes de responder: `low`, `medium`, `high`, `xhigh` o `max`. Más
esfuerzo es más razonamiento, más tokens, más espera y más costo; `medium` alcanza para el trabajo del panel. Con
Claude Opus 5.5, Claude Sonnet 5.5 y Claude Fable 5.1 el panel muestra notas de progreso; con esos y con Claude Opus 5,
si el modelo declina una petición, Anthropic la pasa a un modelo de respaldo (el panel lo avisa). Con otro modelo,
ninguna de las dos cosas, y el panel tampoco le pide razonamiento adaptativo ni esfuerzo (`AGENTE_ESFUERZO` no vale):
un modelo anterior, como Claude Haiku 4.5, rechaza los dos.

**Cómo se forma el costo.** Cada ronda (cada vez que el modelo responde o pide una herramienta) vuelve a mandar las
instrucciones, la lista de herramientas y la conversación entera. La parte repetida sale de la caché del proveedor del
modelo (dura unos minutos), que cobra una fracción: por eso las instrucciones y las herramientas se congelan al crear
la conversación. Una pregunta que necesita una herramienta son al menos dos rondas. Las conversaciones largas cuestan
más por mensaje: conviene empezar otra al cambiar de tema.

En modo directo, precios de lista en dólares por millón de tokens, a noviembre de 2026 (confírmelos en la página de
precios de Anthropic):

| Modelo | Entrada | Salida | Leído de la caché |
|---|---|---|---|
| `claude-opus-5-5` (por defecto) | 4 | 20 | 0,20 |
| `claude-sonnet-5-5` | 2 | 10 | 0,20 |
| `claude-fable-5-1` | 10 | 50 | 0,25 |

Escribir en la caché cuesta 1,25 veces la entrada. `agente_uso` guarda por persona y día los mensajes y los tokens de
entrada, salida, caché leída y caché escrita: con esos cuatro números y la tabla sale el gasto. La consola de Anthropic
muestra el gasto de la clave; ponga ahí un límite mensual.

**La voz clonada** gasta créditos de la cuenta de Mnemo por carácter dicho, según el motor de la voz (a noviembre de
2026, entre 0,025 y 0,10 US$ por cada 1.000 caracteres; MiniMax, el recomendado, 0,06; ver la documentación de voces
de Mnemo). La narración se repite y sale casi siempre
de la caché del panel (no gasta); las respuestas leídas en voz alta sí, frase por frase. Topes: 2 frases a la vez, 90
por minuto y 30.000 caracteres por día por persona, y 3 llamadas a Mnemo a la vez en el proceso (ver [La voz clonada
de Mnemo](#la-voz-clonada-de-mnemo)).

**El [plan en flujo](#el-plan-en-flujo)** es una petición más al modelo por plan, sin razonar, con el guion del capítulo
en el `system` (desde la caché del proveedor si el capítulo se presentó hace poco): de salida, de 1.000 a 2.500 tokens.
Se suma al día de la persona en `agente_uso`. Le ahorra al modelo principal leer el guion (de 6.000 a 11.000 tokens que
después viajaban en cada ronda de la conversación), razonar y escribir el plan, y la ronda final del turno.

**La [respuesta inmediata](#la-respuesta-inmediata)** es una petición más al modelo en cada mensaje (no en las
aprobaciones): de entrada, sus instrucciones (unos 400 tokens), los últimos 8 mensajes acotados a 1.500 caracteres
cada uno y el mensaje nuevo, sin caché; de salida, como mucho 300 tokens (con un modelo que no deja
apagar el razonamiento, como Claude Opus 5.5, 1.000 en total con lo poco que razone), y casi siempre una o dos frases.
Con Mnemo gasta créditos de la cuenta y ocupa unos segundos una de las llamadas al modelo a la vez de la conexión:
por eso con Mnemo solo va cuando el panel no está atendiendo otro turno ni transcribiendo un dictado (y una a la vez),
así nunca le quita el cupo a una respuesta. Lo que gastó se suma al día de la persona en `agente_uso` cuando la
petición termina (también cuando contesta «—»), pero no cuenta en el tope de mensajes. Una petición que se corta a
mitad (la respuesta completa llegó antes, el tope de lo que se muestra, el plazo o el fin del turno) no se suma, como
una ronda cortada con **Detener**, aunque Anthropic o Mnemo cobren lo que alcanzó a gastar: el gasto exacto está en la
consola de Anthropic o en Mnemo. Para ahorrarla, se apaga en **Ajustes → Asistente** o, en modo directo, se le pone
un modelo más barato en `AGENTE_MODELO_ADELANTO`.

**Las [fotos de planillas](#planillas-físicas-por-foto)** cuestan una petición más al modelo por foto (y por cada
relectura, como mucho una): la imagen (unos miles de tokens de entrada) y, de salida, el JSON compacto de las filas
(pocos miles de tokens; como mucho 16.000 con Mnemo y 24.000 en modo directo, con esfuerzo `medium`). Se suma al día
de quien subió la foto en `agente_uso`, también si la lectura falla, pero no cuenta en su tope de mensajes. La misma
foto subida otra vez no se vuelve a leer, y una lectura cortada se retoma desde la fila siguiente, no desde el
principio. Con Mnemo, cada lectura ocupa una de las llamadas al modelo a la vez de la conexión: por eso el proceso lee
de a una (de a dos con Anthropic) y las demás esperan en cola.

**Los [análisis](#análisis-avanzados)** no usan el modelo: los calcula el servidor (alrededor de 1 s cada uno y 2 s el
diagnóstico con 16.000 personas). Lo que cuesta es lo de siempre: la ronda que pide la herramienta y la que lee su
resultado (acotado a 40.000 caracteres).

**Topes.**

- Por persona y día, los mensajes de **Ajustes** (429 al pasarse): cuenta cada mensaje y cada aprobación o rechazo.
- Por turno: 12 rondas y 240 segundos; al llegar, termina la ronda en curso y avisa (se le puede pedir que siga). Ningún
  turno pasa de 10 minutos y cada ronda escribe como mucho 32.000 tokens (16.000 con Mnemo). Cada herramienta del panel
  tiene 60 segundos, salvo las que necesitan más (`Herramienta.plazo`, que vale también para armar su tarjeta):
  `leer_planilla` 80, `cotejar_planilla` y `diagnostico` 120, `resolver_coincidencias` y `agregar_alias_lugar` 160, y
  `cargar_planilla` y `presentacion` 170; las de Mnemo, 80 las de lectura y 140 las de escritura (algunas gastan modelo
  en Mnemo), porque cortarlas antes las cancelaría a medias allá. En una ronda corren como mucho 8 herramientas (las
  demás vuelven al modelo sin hacerse) y en un turno el modelo recibe como mucho 200.000 caracteres de lo que leen:
  pasado eso, lo leído no se le pasa y responde con lo que tiene. Así una sola respuesta del modelo (por ejemplo, por
  una instrucción escondida en una nota) no vuelca la base. Las imágenes de Mnemo van como mucho dos por resultado y 8
  MB por ronda (con Mnemo como modelo, 1,5 MB por ronda), y 20 (y 20 MB) por conversación: la conversación entera se
  reenvía en cada ronda.
- Con Mnemo como modelo, cada ronda tiene en Mnemo unos 170 segundos y cada petición como mucho 3,9 MB: si no cabe,
  las imágenes de los mensajes viejos se cambian por una marca y, si aún no cabe, hay que empezar otra conversación.
  Cuando Mnemo pide esperar (su tope por minuto), el panel reintenta solo, sin pasarse del tope del turno; si responde
  que la cuenta no tiene un modelo disponible (también cuando su proveedor falló un momento), repite la ronda una vez.
- Por conversación: con más de 300.000 tokens de entrada en su última ronda o 400 mensajes no admite más: hay que
  empezar otra (si pasa a mitad de un turno, termina con el error `larga`, que ofrece **Nueva conversación**). Una
  conversación que ya no cabe en el modelo (un 413) también se explica así.
- Un turno a la vez por persona y por conversación, y como mucho 4 a la vez por proceso del servidor («El asistente
  está atendiendo muchas conversaciones a la vez»). En el servicio único, los turnos tienen 4 cupos propios: no le
  quitan cupos a la API del panel. Cada mensaje o decisión pide su cupo con el cuerpo de la petición ya recibido
  (entero en 10 segundos, o 408): una conexión lenta no retiene cupos, y solo los retiene un turno de verdad. Un
  mensaje de quien ya tiene un turno en curso recibe 409 `ocupada` en el acto, sin retener un cupo; solo si ese turno se
  está cerrando (tras **Detener**) espera unos segundos a que suelte la conversación, y un mensaje por persona. El turno
  renueva su candado mientras corre: si el proceso se cae a mitad (un despliegue, una caída), la persona puede volver a
  usar el asistente en un minuto y medio.
- Análisis: como mucho 3 filtros, 40 grupos más «otros» y 12 columnas, series de 120 puntos (con más, la granularidad
  sube sola; el gráfico muestra los últimos 60), periodos de 731 días, `maxTimeMS` de 45 s en las lecturas grandes y una
  salida de 40.000 caracteres (`ajustar` recorta la lista más larga y lo dice con `recortado`).
- Por MCP, por clave y día: las llamadas y las personas distintas de **Ajustes → Agentes externos por MCP** (2.000 y
  300 por defecto), 120 peticiones por minuto y 30 propuestas pendientes (ver [Agentes por MCP con
  datos](#agentes-por-mcp-con-datos)).

Las planillas por foto:

| Qué | Cuánto | Dónde |
|---|---|---|
| Fotos por mensaje y por `leer_planilla` | 4 | `planillas.MAX_POR_MENSAJE`, `MensajeIn.adjuntos` |
| Foto subida | JPEG o PNG de 1,5 MB como mucho (la guardia corta a 1,5 MB + 64 KiB), lado mayor de 200 a 2.600 px y menor de 100 o más | `planillas.MAX_BYTES`, `LADO_MIN`, `LADO_MAX`, `seguridad.LIMITE_FOTO` |
| Lo que prepara el navegador | Lado mayor 2.576 px en modo directo y 2.000 con Mnemo, JPEG 0,8 (bajando hasta 0,5 y luego achicando si pasa del peso) | `adjuntos` de `GET /api/agente/estado` (`planillas.estado_adjuntos`) |
| Subidas por persona | 40 por hora y 150 por día (en `planillas_subidas`: borrar fotos no reinicia los topes) | `POR_HORA`, `POR_DIA` |
| Fotos sin cargar a la vez por persona | 30 (leyendo, leídas o fallidas: 409 `pendientes`) | `SIN_CARGAR_MAX` |
| Lecturas por foto | 2 | `LECTURAS_MAX` |
| Lecturas a la vez en el proceso | 1 con Mnemo, 2 con Anthropic | `A_LA_VEZ` |
| Plazo de la subida | 90 s en total y 20 s sin datos; 4 cupos propios en el servicio único (no le quitan cupos a la API) | `PLAZO_SUBIDA_S`, `servidor.CUPOS_SUBIDA` |
| Una lectura | 150 s por llamada, 270 s con un reintento; «leyendo» sin latido por 5 minutos se da por fallida | `lector_planillas`, `VIVA_S` |
| Espera de `leer_planilla` a las que se leen | ~55 s (sondeo cada 2 s), dentro de su plazo de 80 s | `ESPERA_S` |
| Lo leído por llamada de `leer_planilla` | 36.000 caracteres: las fotos que no caben vuelven sin filas; una hoja que ni sola cabe devuelve las primeras filas que caben, con `filas_omitidas` (cotejar y cargar siguen viendo todas) | `PRESUPUESTO` |
| Bandeja en `planillas` | Las 40 más nuevas | `BANDEJA_MAX` |
| Tarjeta de carga | 30 personas más hasta 6 líneas fijas; 30 correcciones | `TARJETA_PERSONAS`, `TARJETA_FIJAS`, `MAX_CORRECCIONES` |
| Nota y folio | 300 y 120 caracteres | `NOTA_MAX`, `FOLIO_MAX` |

## Configuración en Railway

En *Variables* del servicio que sirve el panel (el del sitio, en el servicio único):

El asistente no necesita ninguna variable: se conecta con Mnemo desde **Ajustes → Asistente**. Todas son opcionales:

| Variable | Valor |
|---|---|
| `MNEMO_MCP_URL` | La dirección MCP de Mnemo que se sugiere al conectar (ver [Conectar con Mnemo](#conectar-con-mnemo)) |
| `MNEMO_MODELO` | El modelo de la cuenta de Mnemo: `principal`, `ligero` o `<proveedor>/<modelo>`; vacía, el de la cuenta (las fotos de planillas, el de la cuenta para leer imágenes, salvo con un Mnemo anterior) |
| `MNEMO_HERRAMIENTAS` | Qué herramientas de Mnemo se ofrecen (y qué permisos se piden al conectar) |
| `ANTHROPIC_API_KEY` | El [modo directo](#modo-directo-sin-mnemo): una clave de la consola de Anthropic, que se usa solo sin Mnemo con permiso para usar sus modelos |
| `AGENTE_MODELO` | Solo en modo directo: `claude-opus-5-5` por defecto |
| `AGENTE_MODELO_ADELANTO` | Solo en modo directo: el modelo de la [respuesta inmediata](#la-respuesta-inmediata), uno rápido como `claude-haiku-5-5` o `claude-sonnet-5-5` (con ellos va sin razonar); vacía, el de `AGENTE_MODELO` |
| `AGENTE_ESFUERZO` | `medium` por defecto; `low`, `medium`, `high`, `xhigh` o `max` (otro valor usa `medium` y lo avisa en el registro). Vale con Mnemo y en modo directo |
| `SITIO_URL` | Solo con el panel desplegado aparte (Root Directory = `admin`): la dirección `https://…` del sitio público, de donde la vista **Presentación** toma la propuesta (y la CSP del panel la deja enmarcar). En el servicio único no hace falta. Para que la presentación acepte las órdenes de ese panel, el sitio se construye con `PANEL_URL` = la dirección del panel |

Pasos:

1. Si quiere, ponga `MNEMO_MCP_URL` en Railway con la dirección de su Mnemo, para no escribirla al conectar. Si
   todavía tiene `MNEMO_TOKEN`, bórrela.
2. Despliegue. Con la cuenta del administrador, en **Ajustes → Asistente**, pulse **Conectar con Mnemo**: inicie sesión
   en Mnemo, deje marcado «Usar tus modelos de IA y tus créditos» y pulse **Permitir**.
3. En la misma sección, revise quiénes lo usan, los topes y la retención. Las [planillas por
   foto](#planillas-físicas-por-foto) y los [agentes por MCP con datos](#agentes-por-mcp-con-datos) no necesitan
   variables: se encienden (o se apagan) en sus secciones de **Ajustes**, después de la revisión jurídica.

Para cortar el acceso: **Desconectar** en Ajustes, o revocar la conexión en Mnemo (**Tu cuenta → Agentes
conectados**). En modo directo, para rotar la clave: cree otra, cámbiela en Railway y revoque la vieja en la consola
(revocarla corta el modo directo al instante). Una clave de Anthropic nunca va en el repositorio ni en un archivo que
se suba.

## Seguridad

- **Las credenciales no salen del servidor.** Los tokens de Mnemo (cifrados en la base) y la clave de Anthropic (una
  variable de entorno, si se usa) no llegan al navegador, ni a las respuestas, ni a los registros (no aparecen en el
  `repr` de la configuración ni en los mensajes de error). El navegador solo habla con el panel: la CSP
  (`connect-src 'self'`) no lo deja llamar a Anthropic ni a Mnemo.
- **Conectar Mnemo** es OAuth 2.1 con PKCE (S256), registro dinámico del panel como cliente, el indicador de recurso
  y el `iss` de la vuelta. El navegador solo *navega* a Mnemo con `location.assign` (la CSP, `form-action 'self'`, no
  deja mandar formularios a otro sitio, y el panel no abre ventanas) y vuelve a `/ajustes?code=…&state=…&iss=…`. La
  página quita eso de la dirección antes de cualquier otra cosa (no queda en el historial y el asistente no lo manda
  al modelo: solo manda los filtros conocidos de cada vista) y lo manda a `POST /api/agente/mnemo/volver` con la
  sesión y el CSRF. El `state` está atado a la sesión que empezó a conectar, vence a los 10 minutos y sirve una sola
  vez, y el código lo canjea el servidor. La cookie de sesión (SameSite=Strict) no viaja en la navegación que vuelve
  de Mnemo, pero sí en las peticiones que hace la página después. Solo el administrador conecta, vuelve o desconecta
  (`agente.conectar`).
- **Las herramientas no tienen permisos propios.** Cada una llama a la API del panel por dentro del proceso
  (`app/agente/interno.py`, por ASGI, sin red) con la cookie, el CSRF y la IP de quien conversa. Así aplican solos los
  permisos de cada ruta, el alcance de planilleros y consultores, el presupuesto diario y el límite de frecuencia, las
  lecturas, la proyección por rol, el bloqueo de quien no autorizó, la idempotencia y la auditoría con su uid y su rol.
  Ofrecer una herramienta no autoriza nada: cada llamada se decide de nuevo, también si el rol o los ajustes cambiaron
  a mitad de la conversación. Si la sesión se cierra o vence, la siguiente herramienta falla y el turno termina. Las de
  Mnemo no pasan por la API del panel: antes de cada una, el turno vuelve a revisar la sesión (con una petición a la
  API) y los ajustes de ese momento.
- **No hay herramientas para lo delicado**: exportar, suprimir, usuarios y claves, ajustes, datos sensibles, confirmar
  autorizaciones. Importar y unir existen solo de una forma, para A y K y con la tarjeta: cargar una planilla
  fotografiada después de cotejarla (`cargar_planilla`, que vuelve a cotejar al aprobar y no carga si algo cambió) y
  unir duplicados de la cola con la vista previa (`resolver_coincidencias`, que no une si el grupo cambió).
- **Escrituras.** Solo con aprobación, y con una clave de idempotencia por llamada: aprobar dos veces o reintentar no
  duplica nada. Una escritura que llama varias rutas usa una subclave determinista por paso (`….imp`, `….as{persona}`),
  y las rutas que no respetan la clave (`PATCH`, `PUT`, `DELETE`) se vuelven a leer y no se repite lo hecho. Una
  escritura del panel que no termina dentro del plazo de la herramienta sigue hasta el final (y guarda su respuesta para
  un reintento), y el asistente avisa que pudo quedar hecha en vez de proponerla de nuevo.
- **Lo que viene de la base, de Mnemo o de una foto son datos, no instrucciones.** Las notas, las filas importadas, los
  lugares escritos, los documentos, los formularios y lo escrito en una planilla fotografiada los escribe gente y
  pueden traer órdenes escondidas; el asistente no las sigue, y aunque lo hiciera no puede saltarse los permisos ni
  escribir sin aprobación.
- **Las fotos.** La subida pide la sesión, el permiso `importar` (A y K), el rol en `agente_planillas.roles`, el
  modelo y un compromiso de confidencialidad que deje fotografiar planillas antes de leer un byte del cuerpo (P y C,
  403 `permiso` sin leerlo), con su propio límite en la guardia (`LIMITE_FOTO`), su plazo y sus cupos. Solo JPEG o
  PNG, con la firma igual al `Content-Type`; JPEG sin segmentos APPn ni COM (EXIF, GPS, miniaturas, comentarios), con
  un solo cuadro; PNG con una lista cerrada de fragmentos y cada CRC comprobado; los dos cortados en su fin (nada
  escondido después: archivos políglotas). Todas las rutas de planillas piden `importar`: la foto se sirve solo a A y
  K, con `nosniff`, `no-store`, `Content-Disposition: attachment` y `Cross-Origin-Resource-Policy: same-origin`; en un
  mensaje del chat solo se adjuntan las fotos propias, y una ajena responde igual que una que no existe.
- **MCP con datos.** La clave de datos solo viaja en `Authorization: Bearer` (con `?clave=`, 401), vence a los 30 días
  y se vuelve a comprobar en cada petición (rol, ajustes, `agente.usar`, alcances). Cada llamada corre con una sesión
  interna de la persona (`via: "mcp"`, en `app.state.db`, 5 minutos, cerrada al terminar aunque la herramienta falle)
  que nunca sale del proceso. Las propuestas se aprueban con la sesión real de quien aprueba, una por una; las de otra
  persona responden 404.
- **La respuesta se pinta como texto**, nunca como HTML: solo enlaza rutas del panel y el origen de Mnemo, y las
  acciones que puede pedirle al navegador son una lista cerrada (abrir una ruta del panel, recargar la vista, refrescar
  las insignias, mover el mapa, manejar la presentación, dibujar un gráfico). El gráfico se valida en el servidor
  (`grafico.validar`) y otra vez en el navegador con el mismo contrato, y se dibuja sin HTML: título y nota como texto,
  colores solo de la paleta.
- **La presentación** es pública y no toca la base: el modelo recibe el guion del paso (lo mismo que se ve). Va en un
  iframe sin `sandbox` (con él no cargaría sus módulos; el límite es la CSP del sitio, que solo corre sus propios
  scripts). La CSP del panel la deja enmarcar con `frame-src 'self'` (y el origen de `SITIO_URL`, si el panel vive
  aparte), y la del sitio solo deja que la enmarquen su origen y el del panel (`frame-ancestors`); el panel mismo sigue
  sin poder enmarcarse (`frame-ancestors 'none'`, `X-Frame-Options: DENY`). Panel y presentación hablan por
  `postMessage` con el origen exacto (nunca `'*'`) y cada lado acepta solo mensajes de la otra ventana y de su origen,
  con una forma estricta: órdenes de una lista, capítulos y pasos que existen, nada de claves de más. El subtítulo se
  pinta como texto y su frase se rechaza (en la herramienta, en el navegador y en la presentación, con las mismas
  reglas y sobre su forma NFKC) con caracteres que no se ven, «@», números de 7 o más dígitos, también por grupos, o
  costos; solo pasan un periodo, un rango de cifras de menor a mayor y una fecha que existe.
  El origen del panel que escribe `build_site.py` (de
  `PANEL_URL`) va como lo entrega el navegador, en minúsculas y sin «:443», y `mando.js` lo vuelve a normalizar: si
  no, la presentación diría «listo» y no aceptaría ninguna orden. El modo proyector se abre con un enlace (no con
  `window.open`) y habla con la pestaña del chat por `BroadcastChannel`, del mismo origen, con mensajes que también se
  validan: acusa recibo de cada orden en el acto, avisa al empezarla (el plazo de la respuesta corre desde ahí) y
  responde al terminarla; una ventana que no acusa, que deja de latir o que se despide con órdenes en curso se da por
  cerrada y esas órdenes se aplican en la pestaña del chat. Su estado trae la explicación que está a la vista, y solo
  manda la ventana de proyector abierta más recientemente.
- **El plan guiado (el recorrido narrado)** se valida entero en el servidor y otra vez en el navegador
  (`recorridoValido` del puente, `escena` de `mando.js`), con las reglas de la explicación y sin costos, y se pinta con
  nodos de texto. La tolerancia es solo para lo opcional de lo visual (una pieza, una parte, un valor): lo que se
  proyecta (las frases, el título, el cierre), el id, el avance y el paso siguen siendo todo o nada. El avance
  (`POST /api/pantalla/progreso`) y los controles (`POST /api/pantalla/recorrido/control`) piden la sesión, el permiso
  `presentacion.ver` y el CSRF, con la forma exacta (listas cerradas, sin claves de más) y solo para el recorrido
  vigente. Lo mismo las dos rutas de la presentación automática (`POST /api/pantalla/auto` y `/auto/siguiente`), cuyos
  planes no llevan texto de nadie: todo sale del guion y pasa las mismas reglas. Con la voz del navegador, una voz
  local no saca nada del equipo; una remota (la del fabricante del navegador) solo se usa si no hay ninguna local en
  español, y lo que dice es lo mismo que se proyecta o, de respaldo de la voz clonada, una frase de una respuesta
  hablada (de una conversación sin datos de habitantes, sin «@», números largos, enlaces ni datos enmascarados).
- **La voz clonada** (`POST /api/agente/voz`) solo dice lo que el panel generó: la narración se pide por referencia al
  plan guardado de esa persona (`rid`, paso, frase; si no es el vigente, 409; si lo escribió una aplicación externa
  por MCP, cuyas frases son texto libre de quien la usa, 409 y va con la voz del navegador), una frase de una
  respuesta con la firma HMAC que le puso el servidor al emitirla (atada a la persona, la conversación y el texto; se
  compara en tiempo constante) y la prueba es una frase fija del administrador. El navegador nunca manda un texto
  libre, y todo pasa las reglas de lo que se dice ante una sala. La piden la sesión, el CSRF, `presentacion.ver` y un
  rol de `agente_voz.roles` (la voz y los créditos son de la cuenta del administrador); las voces para elegir, solo el
  administrador. El audio llega dentro de MCP: el token de la conexión no va a otra dirección de Mnemo, y el
  navegador solo habla con el panel (la CSP no cambia: el PCM se reproduce con Web Audio).
- **El flujo.** `POST` con CSRF y respuesta en flujo NDJSON (una línea JSON por evento, con un latido cada 15 s), sin
  GZip en esas rutas (lo retendría hasta el final: los dos turnos del asistente y la voz clonada) y con cupos propios
  en el servicio único (4 para los turnos, 6 para la voz), que se piden con el cuerpo ya leído (con el plazo y el
  tope del ingreso).
- **Registros.** Solo el tipo de cada error: nunca lo que se escribió, lo que respondió el modelo ni datos de personas.
- **En el navegador** no queda nada de la conversación: solo `sessionStorage` `yj_agente` (si el panel estaba abierto,
  qué conversación y si se leen las respuestas en voz alta), que se borra al cerrar sesión. El audio de la voz clonada
  queda solo en la memoria de la página (como mucho 8 frases) y lo de una respuesta se suelta al decirse. El widget sabe qué vista está abierta por el evento `vista` que
  emite `app.js` al terminar de pintar cada una, y vuelve a pedir su estado (que guarda 5 minutos) con el evento
  `agente:estado`, que emite Ajustes al volver de Mnemo, al desconectar y al guardar los ajustes del asistente (y los de
  las planillas por foto); si se abre sin modelo, también lo vuelve a pedir. Las fotos de planillas viven solo en la
  memoria de la pestaña (nunca en `localStorage`, `sessionStorage` ni IndexedDB) mientras están en el cuadro o en un
  turno que se puede reintentar, se pintan en canvas y se sueltan al cerrar el panel, al quedar la cuenta pendiente o
  al dejar de usar el asistente; quitar una que no llegó en un mensaje la borra de la bandeja, salvo que la bandeja
  ya la tuviera (`repetida`), que nunca se borra desde el chat. La vista Planillas por
  foto pide la foto con `no-store`, la dibuja en un canvas y la suelta al cerrarla o salir (nunca en una dirección).

## Arquitectura

| Archivo | Qué hace |
|---|---|
| `app/api/agente.py` | Las rutas: `GET /api/agente/estado` (con `adjuntos`: si el rol sube fotos y con qué topes), `GET /api/agente/conversaciones`, `GET` y `DELETE /api/agente/conversaciones/{id}`, `POST /api/agente/mensajes` (`MensajeIn.adjuntos`: los ids de las fotos; el texto puede ir vacío con fotos), `POST /api/agente/confirmaciones`, `POST /api/agente/transcribir`, `GET /api/agente/voces` y `POST /api/agente/voz` |
| `app/api/agente_mnemo.py` | La conexión con Mnemo: `POST /api/agente/mnemo/conectar`, `POST /api/agente/mnemo/volver` y `DELETE /api/agente/mnemo` (solo el administrador) |
| `app/agente/bucle.py` | El turno: comprobaciones previas (también las fotos de un mensaje: `abrir_mensaje` con `adjuntos`, `_exigir_fotos`), candados, rondas con el modelo, ejecución de herramientas (con el plazo de cada una), aprobaciones, el gráfico de cada herramienta y eventos NDJSON |
| `app/agente/proveedores.py` | De dónde sale el modelo: Mnemo si está conectado con `mnemo:model`; si no, Anthropic si hay clave. Queda fijo en cada conversación |
| `app/agente/modelo_mnemo.py` | El modelo de Mnemo: cada ronda por `mnemo_model_complete`, con el texto por partes |
| `app/agente/llm.py` | El modelo de Anthropic en modo directo: el cliente (se crea al primer uso) y la forma de cada petición |
| `app/agente/mnemo_conexion.py`, `app/agente/cifrado.py` | OAuth con Mnemo, los tokens cifrados y su renovación; en `cifrado.py`, también la variante para bytes (`cifrar_bytes`, `descifrar_bytes`) de las fotos de planillas y lo leído |
| `app/agente/sistema.py` | Las instrucciones del asistente (fijas por conversación, con las secciones de cada grupo de herramientas solo si las tiene: `secciones`) y el contexto de la vista de cada mensaje |
| `app/agente/conversaciones.py` | Conversaciones, mensajes (solo se agregan, nunca se editan) y uso diario en MongoDB; `para_interfaz` (con las fotos de un mensaje y el gráfico de cada herramienta) y `marcar_datos` (una conversación con datos sin id, como las filas de una planilla) |
| `app/agente/politica.py` | Quién lo usa y con qué: los ajustes con valores de respaldo (también `agente_planillas` y `agente_mcp`), `ofrecida` y las sugerencias de la bienvenida (`SUGERENCIAS`) |
| `app/agente/interno.py` | Las llamadas a la API del panel con la sesión de quien conversa |
| `app/agente/minimizar.py` | Lo mínimo de cada persona que llega al modelo |
| `app/agente/herramientas/` | `base.py` (contratos: `Herramienta.mcp`, `plazo`, `disponible_ajustes`, `Confirmacion.personas`), `personas.py`, `fichas.py` (los registros de cada persona y las reuniones), `calidad.py` (las colas de Calidad y los catálogos), `planillas.py` (las planillas por foto y el bloque `<fotos_adjuntas>`), `analisis.py` (`analizar`, `diagnostico`), `gestion.py`, `interfaz.py` y `mnemo.py` |
| `app/agente/grafico.py`, `web/js/agente-graficos.js` | El contrato del gráfico del chat (`validar`: clases barras, columnas, apilada y serie, hasta 60 ítems) y su dibujo en el navegador (`pintarGrafico`, con `web/js/graficos.js`; agente.js lo carga con el primer gráfico) |
| `app/analitica.py`, `app/api/analitica.py` | Los [análisis avanzados](#análisis-avanzados): la validación (`Consulta`), la lectura compartida, la privacidad de las cifras (`proteger`, `fijadas`…), un análisis por tipo, el diagnóstico y el catálogo; `GET /api/analitica?consulta=` y `GET /api/analitica/catalogo` (`analitica.ver`) |
| `app/planillas.py`, `app/api/planillas.py` | La [bandeja de planillas por foto](#planillas-físicas-por-foto): validación y limpieza de la imagen, subida con sus topes, lectura de fondo (cupo, latido, uso), reglas de privacidad por fila, correcciones, vista previa y carga; `fotos_de` y `estado_adjuntos` para el chat; las rutas `/api/planillas…` |
| `app/agente/lector_planillas.py` | La lectura de una foto: las instrucciones, la llamada aparte al modelo (`leer`), la interpretación de la respuesta y el saneo |
| `app/pipeline/importar.py`, `app/pipeline/lectores.py` | `importar_registros` y `simular_registros` (la carga y la vista previa de una planilla por foto, con el mismo importador del Excel) y `registro_planilla` (la misma fila da el mismo registro en el Excel y en la foto) |
| `app/api/calidad.py` | (además de Calidad de datos) `POST /api/lugares/{lid}/alias`, el alias de un barrio o vereda con su reubicación acotada |
| `app/sesion_interna.py` | La sesión interna de cada llamada de un agente por MCP con datos (`via: "mcp"`, 5 minutos, cerrada siempre) |
| `app/agente/mnemo_cliente.py` | El cliente del servidor MCP de Mnemo |
| `app/agente/dictado.py` | Las preguntas por voz: el audio a `mnemo_transcribe`, con sus topes |
| `app/agente/redactor.py` | El [plan en flujo](#el-plan-en-flujo): las instrucciones de la redacción con el guion del capítulo, el lector de JSON Lines que llega a trozos (`Lector`), el plan que crece (`PlanEnFlujo`) y la op `plan` (`escribir`): guardar, crecer, publicar y cortar |
| `app/agente/adelanto.py` | La [respuesta inmediata](#la-respuesta-inmediata): sus mensajes, lo que se muestra (la marca «—», palabra por palabra, el tope), sus frases para decir, la carrera con la respuesta completa, el plazo y lo que se guarda |
| `app/agente/voz.py` | La [voz clonada de Mnemo](#la-voz-clonada-de-mnemo): el texto de cada pedido (el plan guardado, la frase firmada, la prueba), lo que se dice (`para_decir`, `hablable`), las frases de una respuesta (`Frases`), la firma, los topes, la caché, un solo vuelo y el flujo de `mnemo_speak` |
| `web/js/agente.js`, `web/css/agente.css` | El botón y el panel del asistente (también el recuadro de la respuesta inmediata y cuándo la sala la oye), la cámara y la galería del cuadro de escribir (preparar cada foto, subirla a la bandeja, borrarla al quitarla, mandar sus ids y conservarlas en «Reintentar» y «Nueva conversación») y dónde va cada gráfico |
| `web/js/agente-mapa.js` | El puente entre el asistente y la vista del mapa |
| `app/agente/guion.py`, `app/agente/propuesta_guion.json` | El guion de la presentación (lo que muestra cada paso, en texto plano): lo genera `scripts/build_propuesta.py` desde `web/data/propuesta.json` y va versionado dentro de `admin/` (también lo tiene el panel desplegado aparte) |
| `web/js/agente-presentacion.js` | El puente entre el asistente y la vista Presentación: la cola, la navegación a `/presentacion`, el validador de la acción y el canal con la ventana del proyector |
| `web/js/vistas/presentacion.js`, `web/css/presentacion.css` | La vista Presentación: el iframe de la propuesta, su barra, el modo proyector (`?pantalla=1`), la pantalla en off (`?off=1`) y la ventana llena |
| `web/js/propuesta/mando.js` (del sitio) | En la presentación: recibe las órdenes del panel (también `vista`), le avisa cada cambio de paso y pinta el subtítulo |
| `app/pantalla.py`, `app/api/pantalla.py` | La pantalla en off de cada persona (su estado, `GET /api/pantalla`), sus dos claves MCP (`/api/pantalla/clave`: la de la presentación y la de datos con sus alcances, `alcances_de_datos`, `anular_propuestas`), el recorrido narrado: guardarlo, colapsarlo, el avance (`POST /api/pantalla/progreso`), los controles (`POST /api/pantalla/recorrido/control`) y dónde va (`GET /api/pantalla/recorrido`), y el estado de la [presentación automática](#presentación-automática) (`POST /api/pantalla/auto` y `/auto/siguiente`) |
| `app/automatica.py` | La presentación automática por dentro: qué se dice en cada paso, el plan de cada capítulo y por dónde sigue (sin modelo: sale del guion) |
| `app/recorrido.py`, `app/proyectable.py` | El plan guiado por dentro (el recorrido: sus topes, la forma absoluta de la escena con `mover`, `animar` y `simular`, las frases, los tiempos, la validación contra el guion, también de los controles de la simulación) y las reglas de lo que se proyecta (también sin costos) |
| `web/js/reproductor.js`, `web/js/voz.js` | El reproductor del plan (el reloj de la explicación, la espera inicial, que deja terminar la respuesta inmediata, pausas, saltos, cierre; la referencia de cada frase en el plan y la precarga de la que sigue) y la voz del navegador |
| `web/js/voz-clonada.js` | La voz clonada en el navegador (pura, como `voz.js`): pide cada frase por su referencia, agenda el PCM con Web Audio, precarga, la memoria de la página y el respaldo con la voz del navegador |
| `web/js/voz-panel.js` | La voz de la ventana: una sola para la narración, las respuestas habladas y la prueba de Ajustes (con conteo de referencias), con `flujo('/api/agente/voz', …)` y el `voz` del estado; la narración manda, salvo ante la respuesta inmediata que suena (la marca y la cesión del plan en su espera) |
| `web/js/locutor.js` | Las respuestas habladas: dice en orden las frases firmadas del turno, primero las de la respuesta inmediata (su propia cola, que la respuesta espera), precarga la siguiente, se resincroniza con `frases_descartar` y `frases_ronda` y se calla |
| `web/js/agente-recorrido.js` | La tarjeta del plan en el chat y su barra fija |
| `app/api/mcp.py` | El servidor MCP (`POST /api/mcp`): el de la presentación (la herramienta `presentacion`) y el de [datos](#agentes-por-mcp-con-datos) (las herramientas por alcance, la sesión interna por llamada, sin quien no autorizó, los topes, las propuestas y `estado_propuesta`), y las rutas de Mi cuenta `GET /api/mcp/propuestas` y `POST /api/mcp/propuestas/{id}` |
| `web/js/vistas/cuenta.js` | Mi cuenta, con **Agentes por MCP**: la dirección del servidor, las dos claves (la de datos con sus alcances, el motivo de los que no se tienen y el aviso) y las propuestas con su tarjeta entera, **Aprobar** y **Rechazar** |
| `web/js/app.js` | (en el asistente) la insignia de «Mi cuenta» con las propuestas por MCP que esperan (`INSIGNIAS.cuenta`, `propuestas_mcp` de `/api/insignias`) |
| `web/js/vistas/importar.js`, `web/css/planillas.css` | La vista **Importar y exportar → Planillas por foto**: subir, la bandeja, la revisión con la foto al lado de la grilla, cotejar, cargar y confirmar las autorizaciones con el papel |
| `web/js/api.js` (`flujo`) | Lee la respuesta NDJSON con el CSRF de la sesión |
| `app/api/ajustes.py`, `web/js/vistas/ajustes.js` | Los ajustes del asistente y, en la vista, la conexión con Mnemo (conectar, la vuelta y desconectar), el bloque **Voz del asistente** (las voces de `GET /api/agente/voces`, `agente_voz` y **Probar voz**) y los formularios **Planillas físicas por foto** (`agente_planillas`) y **Agentes externos por MCP** (`agente_mcp`) |

**Un turno, paso a paso.**

1. El navegador manda `POST /api/agente/mensajes` con `{conversacion, texto, contexto}` y, si lleva fotos de
   planillas, `adjuntos` (sus ids en la bandeja, como mucho 4; el texto puede ir vacío).
2. Antes de abrir el flujo, el servidor responde con JSON normal lo que impide el turno: 503 `sin_configurar` (no hay
   modelo: ni Mnemo conectado con permiso para usar sus modelos ni clave de Anthropic) o `saturado` (ya hay 4 turnos en
   este proceso; trae `Retry-After`), 403 `agente_apagado` (su rol no está habilitado), 429 `volumen` (tope diario), 403
   `planillas_apagado` (su rol no sube fotos), 422 `fotos` (una foto no es suya o ya no está; se comprueba antes de
   contar o reservar nada), 409 `ocupada` (ya hay un turno suyo en curso: en el acto; solo si ese turno se está
   cerrando, como tras **Detener**, antes espera hasta 5 segundos a que suelte la conversación), `larga` (conversación
   demasiado larga) o `proveedor` (la conversación es de un modelo que ya no está: hay que empezar otra), y 404 si la
   conversación no es suya o no existe.
3. Abre el flujo y pide una ronda al modelo de la conversación (a Mnemo, con `mnemo_model_complete`, o a Anthropic) con
   las instrucciones y las herramientas congeladas, el historial y el mensaje nuevo precedido del contexto de la
   vista. Mientras llega, emite el texto por partes (y, con Anthropic, el progreso) y el inicio de cada herramienta.
   Una respuesta sin nada (pasa) queda solo para auditoría, con un aviso: reenviarla rompería la conversación.
4. Ejecuta las herramientas en orden, como mucho 8 por ronda: las de lectura y de interfaz en el acto (con la API
   interna; las de Mnemo, que no pasan por ella, vuelven a revisar antes la sesión y los ajustes); las de escritura
   quedan pendientes, emite una tarjeta por cada una (con los valores enteros, si se ven como se van a escribir) y
   termina con `fin` `confirmacion`.
5. Al aprobar o rechazar, `POST /api/agente/confirmaciones` con `{conversacion, decisiones: [{id, aprobar}]}` (y
   `voz: true` si la respuesta que sigue se lee en voz alta, como `contexto.voz` de un mensaje; cuenta
   en el tope diario; 409 `sin_pendientes` si alguna decisión es sobre algo que ya no está pendiente, o si aprueba lo
   que guardó una versión anterior del panel, que queda como rechazado) quita lo pendiente (y guarda lo que no se
   aprobó), ejecuta lo aprobado (con su clave de idempotencia), devuelve al modelo todos los resultados juntos y sigue
   el turno. Si el turno se corta a mitad, lo aprobado no vuelve a quedar aprobable (se haría dos veces): en el turno
   siguiente el modelo sabe que pudo hacerse y lo verifica antes de proponerlo otra vez, y lo rechazado le llega como
   rechazado.
6. Termina con `fin` y el uso del día.

**Eventos** (una línea JSON por evento, con `tipo`):

| Evento | Qué lleva |
|---|---|
| `inicio` | `conversacion`, `titulo`. Siempre el primero |
| `progreso`, `texto` | Trozos de una nota de progreso o de la respuesta |
| `texto_ronda` | `texto`: el texto final de la ronda en curso cuando no coincide con lo que llegó por partes (con Mnemo, los trozos son un adelanto). Reemplaza el de la ronda |
| `herramienta` | `id`, `nombre`, `etiqueta`, `estado` (`inicio`, `ok`, `error`, `pendiente`, `aprobada`, `rechazada`) y `resumen` |
| `accion` | Una acción para el navegador: `navegar` (una ruta del panel), `recargar`, `insignias`, `mapa` (acciones del mapa), `grafico` (el gráfico de un análisis, justo después del resultado de su herramienta: `clase`, `titulo`, `unidad`, `items`, `nota`; ver [Análisis avanzados](#análisis-avanzados)) o `presentacion` (`op`: `ir` con `capitulo` y `paso` desde 1, `siguiente`, `anterior`, `explicar` o `quitar_explicacion`; `explicacion`, la frase para la pantalla, en todas salvo la última; `vista` con `panel`, `indice` o `fichas`; `visual` con `enfoque`, `camara`, `rumbo`, `elevacion`, `zoom`, `mirar`, `girar`, `comparar`, `detalle`, `inmersion`, `mostrar`, `ocultar`, `aislar`, `sin` o `tema`, y las acciones `mover`, `animar` y `simular`; `pantalla_completa` con `activar`; `recorrido` con el recorrido absoluto (cada escena: `capitulo`, `paso`, `panel`, `visual`, `resaltar`, `mover`, `animar`, `simular` (puede faltar), `frases` y `sostener_ms`; el [plan en flujo](#el-plan-en-flujo) llega con `abierto` mientras se escribe y vuelve con `sigue` cada vez que crece); `control_recorrido` con `rid` y `accion`) o `recorrido` (la tarjeta del plan en el chat: `id`, `titulo`, `destino`, `duracion_ms`, `cierre`, `sugerencias`, `abierto` mientras el plan en flujo se escribe (vuelve con el mismo `id` cada vez que crece) y por escena `narracion`, `donde` y `hace`) |
| `confirmar` | La tarjeta de una escritura: `id`, `titulo`, `detalle` (pares etiqueta y valor, enteros: el widget no recorta nada, y si llegan más de 40 o uno de más de 4.000 caracteres no ofrece **Aprobar**) y `aviso`. Lo pendiente al abrir una conversación lleva lo mismo y, si lo guardó una versión anterior del panel, `vieja` (tampoco ofrece **Aprobar**) |
| `descartar` | La ronda se repite tras un error pasajero: se borra lo que se pintó de ella |
| `frase` | Solo si el mensaje pidió la respuesta hablada (`contexto.voz`) y la voz clonada lee respuestas para esa persona: `n` (desde 0 en el turno), `texto` y `firma`, una frase cerrada que el navegador pide a `POST /api/agente/voz` (ver [La voz clonada de Mnemo](#la-voz-clonada-de-mnemo)) |
| `frases_descartar` | `desde`: las frases desde ese número ya no valen (la ronda se repitió o su texto final cambió); las que sigan se numeran desde ahí |
| `frases_ronda` | `desde`: al cerrar una ronda que tuvo un `frases_descartar`, dónde empieza la siguiente (el navegador no repite lo ya dicho de la ronda rehecha, y lo de la siguiente sí lo dice) |
| `adelanto` | Solo en un mensaje con la [respuesta inmediata](#la-respuesta-inmediata) encendida: `texto`, el trozo siguiente de ella (texto plano, que siempre termina en una palabra entera; se agrega a lo anterior). Va arriba de la respuesta del turno |
| `adelanto_frase` | Si además el mensaje pidió la respuesta hablada (`contexto.voz`) o solo la inmediata hablada (`contexto.voz_adelanto`, sin `frase` de la respuesta): `n` (desde 0 en el turno, aparte de los de `frase`), `texto` y `firma`, como `frase` |
| `adelanto_fin` | La respuesta inmediata terminó: lo que se mostró queda. Con `vacio: true` no se mostró nada (no hacía falta, la respuesta completa llegó antes, o falló) y no queda nada. Uno por cada respuesta inmediata que se lanzó, antes de `fin` (un turno que falla antes de lanzarla no trae ninguno) |
| `aviso` | `texto` y `nivel` (`info` o `alerta`): un rechazo del modelo, el paso a un modelo de respaldo |
| `latido` | Cada 15 s sin otros eventos, para mantener viva la conexión |
| `error` | `mensaje` y `codigo` (ver abajo); siempre lo sigue `fin` |
| `fin` | `motivo` (`listo`, `confirmacion`, `pasos`, `rechazo` o `error`) y `limite` (`usados`, `maximo`). Siempre el último |

**Códigos que el widget trata aparte**, además de mostrar el mensaje (vengan antes del flujo o en un `error`):

| Código | Qué hace el widget |
|---|---|
| `proveedor`, `larga`, `borrada`, `no_existe` | Ofrece **Nueva conversación**: esta ya no sirve (si el mensaje no llegó, o si con `larga` quedó sin responder, la nueva lo trae escrito) |
| `llm_peticion` | Ofrece **Reintentar** y **Nueva conversación**: puede ser pasajero (con Mnemo, una sobrecarga del proveedor a mitad de la respuesta llega así) o no tener arreglo en esta conversación |
| `mnemo_sin_modelo` | Ofrece **Reintentar** y vuelve a leer el estado: puede ser pasajero (el proveedor de la cuenta se cayó un momento) |
| `mnemo_conexion`, `sin_configurar`, `agente_apagado` | Vuelve a leer el estado: si ya no hay modelo, al administrador le explica qué falta, con un enlace a Ajustes |
| `sin_pendientes` | Al decidir tarjetas: vuelve a traer la conversación (en vez del mensaje), con lo que espera aprobación ahora y una nota de por qué cambió |
| `mnemo_plan`, `mnemo_creditos`, `volumen`, `permiso` | Nada más |
| `sin_voz`, `voz_rol` (de `POST /api/agente/voz`, al leer una respuesta o narrar) | La voz de la ventana pasa a la del navegador el resto de la sesión y el asistente vuelve a leer su estado (si ya no se ofrece, se va **Leer las respuestas en voz alta**). Cualquier otro código de la voz (`con_personas`, `plan_vencido`, `frecuencia`…) solo cambia esa frase, que se dice con la del navegador |

Salvo `llm_peticion` y `mnemo_sin_modelo`, ninguno de esos ofrece **Reintentar**: repetir el mismo mensaje no lo
arregla. Los demás (la red, un plazo vencido, el modelo saturado o caído un momento) sí. Los de Mnemo como modelo:
`mnemo_conexion` (no hay conexión, se cayó o Mnemo la rechazó aun después de renovarla), `mnemo_plan` (el plan de la
cuenta no incluye el chat, o no incluye el modelo elegido en `MNEMO_MODELO`), `mnemo_creditos` (no quedan créditos),
`mnemo_sin_modelo` (la cuenta no tiene un modelo disponible ahora, o la conexión no tiene permiso para usar sus
modelos), `larga` (la conversación no cabe en la ventana del modelo) y `llm_peticion` (otro rechazo de la petición).
`mnemo_sin_vision` (ningún modelo de la cuenta lee imágenes, el de leerlas no se puede usar ahora o su proveedor
rechazó la foto) no llega en un turno: es el error de leer la foto de una planilla y queda en la bandeja, con su
mensaje (ver [Planillas físicas por foto](#planillas-físicas-por-foto)).
El texto de una ronda puede llegar en un solo trozo largo (con Mnemo, si el proveedor de la cuenta no responde por
partes): el widget lo pinta entero, con el mismo tope que `texto_ronda`.

**En MongoDB**: `agente_conversaciones` (dueño, título, proveedor del modelo con que empezó, instrucciones y
herramientas congeladas, personas vistas, lo pendiente de aprobar y lo que no se aprobó, las escrituras de Mnemo ya
mandadas, candado del turno y fecha de borrado), `agente_mensajes` (un documento por mensaje, con su número de orden),
`agente_uso` (mensajes, tokens y créditos por persona y día), `agente_olvidos` (quién dejó de autorizar en la última
hora: solo el número de la ficha y la hora) y, en `meta`, `mnemo_conexion` (la conexión con Mnemo, con los tokens
cifrados). Además, de las herramientas nuevas: `planillas` (la bandeja: la foto y lo leído cifrados, el estado y las
huellas de cada fila para la supresión; TTL en `expira`), `planillas_subidas` (quién subió y cuándo, para los topes:
26 horas), `importaciones.fotos_sha256` (las fotos ya cargadas), `claves_mcp` (las dos claves de cada persona: solo
su SHA-256; la de datos con TTL en `expira`), `mcp_propuestas` (48 horas; decididas, 7 días) y `mcp_entregas` (90
días). Los índices TTL borran lo vencido.

## Probar en local

Sin Mnemo conectado ni `ANTHROPIC_API_KEY` el panel funciona igual: el administrador ve el botón con la explicación de
qué falta. Sin una voz clonada, el panel narra y lee con la voz del navegador. Las pruebas nunca llaman a Anthropic ni a Mnemo: el modelo de Anthropic va simulado con el SDK de verdad y
un transporte falso, y Mnemo con un servidor MCP y un OAuth falsos (`tests/ayudas_mcp.py`). Necesitan MongoDB, como las
demás:

```bash
cd admin
python -m pytest -q tests/test_agente_*.py tests/test_dictado*.py tests/test_voz_*.py
python -m pytest -q tests/test_analitica_*.py tests/test_calidad_*.py tests/test_planillas_*.py tests/test_widget_*.py \
  tests/test_mcp_*.py tests/test_documentacion_*.py tests/test_politicos_*.py tests/test_ajustes_*politicos.py \
  tests/test_compromiso_fotos.py
```

`tests/ayudas_agente.py` trae lo necesario para escribir una: `encender(app, *respuestas)` pone una clave inventada y
la Messages API simulada; `sse(...)` arma una respuesta del modelo con bloques `T` (texto), `TH` (progreso) y `TU`
(una herramienta); `conectar_mnemo(app)` guarda una conexión con un Mnemo falso, cifrada como la deja Ajustes, y
`encender_mnemo(app, *respuestas)` además le pone el modelo de Mnemo guionizado (cada ronda, un `R(...)` con bloques
`T` y `TU`); `enviar` y `decidir` hacen un turno por la API y devuelven los eventos. `tests/test_agente_navegador.py`
conecta Mnemo de punta a punta en Chromium (Ajustes, la página de permisos de un Mnemo falso y la vuelta) y revisa que
el asistente se entere sin recargar la página. `tests/test_agente_presentacion.py` arma el sitio con `build_site.py` en
una carpeta temporal y, con el modelo simulado, lleva la presentación de verdad (en el iframe de la vista) a un paso y
le pone el subtítulo, en escritorio y en el celular; con Node prueba el puente, el proyector y el mando sin navegador.
Si cambia `data/propuesta/`, `python3 scripts/build_propuesta.py` regenera también el guion del asistente.
`tests/test_automatica.py` prueba la presentación automática sin MongoDB ni modelo (los planes del guion real, el
estado en una base en memoria, las rutas llamadas como funciones, la op `automatica` y el contexto).
`tests/test_voz_servidor.py` prueba la voz clonada en el servidor con un cliente de Mnemo falso que manda los avisos
de `mnemo_speak` a su ritmo (y una vez con el cliente MCP de verdad contra el Mnemo falso de `tests/ayudas_mcp.py`):
la narración por `rid`, la firma, las conversaciones con personas, los roles, los topes, la caché, un solo vuelo, la
cancelación cuando nadie escucha (con un ASGI crudo, para ver los trozos y la desconexión), los errores de Mnemo y
que nada vaya al registro. `tests/test_voz_frases.py` prueba `para_decir` (corre la tabla de `web/js/voz.js` con Node
y la compara con la de Python), las frases de una respuesta (también a trozos al azar: nunca se desdicen) y el turno
que las emite firmadas. `tests/test_agente_adelanto.py` prueba la respuesta inmediata: lo que se muestra (con un
proveedor inventado), el turno con dos guiones del modelo simulado (el de la respuesta completa y el de la inmediata,
con esperas atadas a los eventos del turno), la carrera, los fallos, lo que se guarda y el historial, el ajuste, sus
frases con la voz clonada y la petición `rapido` de los dos proveedores. `encender`, `encender_lento` y
`encender_mnemo` la dejan apagada (cada guion es el del modelo principal); `adelanto=True` la enciende. `tests/test_voz_clonada.py` prueba el navegador con Node: la voz clonada
(`web/js/voz-clonada.js`, con un AudioContext, un reloj y un servidor falsos: el PCM agendado y cuándo empieza y
termina, el respaldo con la voz del navegador, `sin_voz`, la precarga y los dos lugares, `callar`, un flujo estancado,
MP3, el gesto, la prueba de Ajustes), el locutor de las respuestas (y su cola de la respuesta inmediata: va primero, la
respuesta la espera, `vacio`, el plazo de 8 s, callar), la voz de la ventana (`voz-panel.js`, con `fetch` falso: una
sola, la narración manda, el flujo a `POST /api/agente/voz`, la marca de la inmediata y la cesión del plan), la
referencia y la precarga del reproductor y su espera a la inmediata (el tope de 15 s, la pausa, «Siguiente», un plan
que reemplaza a otro), y lo estático de agente.js, Ajustes y la presentación. `tests/test_voz_navegador.py` lee una
respuesta en Chromium (con las rutas del asistente y de la voz contestadas desde el navegador): el botón,
`contexto.voz`, las frases pedidas por su referencia, el audio que suena con Web Audio, Escape y sin violaciones de la
CSP. También la respuesta inmediata con el turno en flujo de verdad (un `fetch` que la prueba alimenta evento por
evento): el recuadro arriba en el acto, su voz antes que la de la respuesta, `vacio` y el historial; y, con la
presentación de verdad abierta (el sitio de `build_site.py`) y sin voz clonada, la sala la oye con la voz del
navegador (una síntesis falsa) y el plan que llega mientras suena empieza después de ella.
`test_conectar_mnemo_desde_ajustes` (en `tests/test_agente_navegador.py`) ve el bloque **Voz del asistente** con la voz
de un Mnemo falso.

Las herramientas nuevas tienen sus propias pruebas, con datos inventados (las imágenes se generan con Pillow en la
prueba; nunca se versionan fotos):

- **Análisis**: `tests/test_analitica_privacidad.py` (quien no autorizó no cambia ninguna salida, las bases políticas
  no se deducen, `pocas`, «<5» y la reconstrucción por fuerza bruta en unas 2.000 tablas), `test_analitica_motor.py`
  (las cifras exactas de cada tipo, los enlaces del diagnóstico iguales a lo que muestra Habitantes, el rendimiento) y
  `test_analitica_herramientas.py`, con las ayudas de `tests/ayudas_analitica.py`.
- **Registros y calidad**: `tests/test_calidad_esquemas.py`, `test_calidad_fichas.py`, `test_calidad_colas.py` y
  `test_calidad_alias.py` (las listas blancas de cada salida, quién recibe qué, la tarjeta que no escribe, aprobar dos
  veces, la ficha que cambió), con `tests/ayudas_calidad.py`.
- **Planillas por foto**: `tests/test_planillas_imagen.py`, `test_planillas_lector.py`, `test_planillas_importar.py`,
  `test_planillas_api.py`, `test_planillas_carga.py` y `test_planillas_fondo.py` (el servidor: la imagen, el lector con
  un proveedor falso, el importador, las rutas, la supresión y la Messages API simulada de punta a punta), con
  `tests/ayudas_planillas.py`; `test_planillas_herramientas.py` y `test_planillas_chat.py` (el chat: lo que el modelo
  nunca recibe entero, leer → cotejar → cargar), con `tests/ayudas_planillas_chat.py`; `test_planillas_vista.py` y
  `test_planillas_vista_web.py` (la vista en Chromium).
- **Widget**: `tests/test_widget_fotos.py`, `test_widget_graficos.py`, `test_widget_ajustes.py` y
  `test_widget_navegador.py` (Chromium: la cámara, la galería, los gráficos en vivo y al repintar).
- **MCP con datos**: `tests/test_mcp_datos.py` (los nombres exactos por alcance, quién tiene qué, la clave solo por la
  cabecera y su vencimiento, sin quien no autorizó, los topes, las propuestas y su aprobación) y
  `test_mcp_cuenta_web.py` (Mi cuenta en Chromium).
- **Datos políticos**: `tests/test_politicos_minimizar.py`, `test_politicos_herramientas.py`,
  `test_politicos_analitica.py` y `test_politicos_mcp.py` (cada rol recibe lo que ve en el panel, con el ajuste
  encendido y apagado, nada de quien no autorizó, lo sensible fuera, la supresión de la analítica, MCP),
  `test_ajustes_politicos.py` y `test_ajustes_web_politicos.py` (el ajuste `agente_politicos`, también en Chromium).
- **El compromiso y las fotos**: `tests/test_compromiso_fotos.py` (la versión 2026-11-v2, el 409 `compromiso_fotos`
  sin leer el cuerpo, la cámara que no se ofrece, el aviso de Ajustes, y que planilleros y consultores nunca usan las
  planillas por foto).
- **Instrucciones y documentación**: `tests/test_documentacion_sistema.py` (las secciones de `sistema.py` según las
  herramientas y las sugerencias de cada rol), `tests/test_documentacion_politicos.py` (la sección de los datos
  políticos según el ajuste y el rol) y `tests/test_documentacion_docs.py` (que este documento y el README nombren cada
  herramienta, ajuste y archivo nuevo, y que sus enlaces internos lleven a una sección que existe).

```python
from ayudas_agente import T, encender, enviar, sse


def test_un_turno_con_el_modelo_simulado(sesion):
    api = encender(sesion.app, sse(T("Hola. ¿En qué le ayudo?")))
    r, eventos = enviar(sesion, "Hola")
    assert eventos[0]["tipo"] == "inicio" and eventos[-1]["tipo"] == "fin"
    assert api.peticiones[0]["json"]["model"] == "claude-opus-5-5"  # lo que se le habría mandado a Anthropic
```

Dos pruebas corren contra un Mnemo de verdad levantado en local (su API con almacenes en memoria y, en vez de un
proveedor de modelos, uno con guion) y se saltan sin `MNEMO_E2E_DIR`, la carpeta de un checkout de Mnemo con
`npm ci` y `npm run build:shared` hechos: la del cliente MCP (`tests/test_agente_mnemo.py`) y la punta a punta en
Chromium (`tests/test_agente_navegador.py`, `test_punta_a_punta_con_mnemo_de_verdad`): conectar desde Ajustes en la
página de permisos de Mnemo, conversar con el modelo de Mnemo usando una herramienta del panel, volver a conectar sin
y con el permiso de los modelos y desconectar (la conexión queda revocada en Mnemo). Con `CAPTURAS_AGENTE=<carpeta>`
deja ahí sus capturas (`mnemo-*.png`):

```bash
MNEMO_E2E_DIR=/ruta/a/Mnemo CAPTURAS_AGENTE=/tmp/capturas python -m pytest -q tests/test_agente_navegador.py -k punta_a_punta
```

Para probarlo con un modelo real, arranque como siempre y conecte un Mnemo desde **Ajustes → Asistente**: el de
producción o uno local con `PUBLIC_BASE_URL` (en local el panel acepta `http://127.0.0.1` y `http://localhost`, por
ejemplo `MNEMO_MCP_URL=http://127.0.0.1:8080/mcp`). Para la voz clonada, ese Mnemo necesita una ruta de fal (la clave
compartida o la de la cuenta), un plan con las voces y una voz clonada marcada para apps; conecte dejando marcado
«Hablar con las voces…», elíjala en **Ajustes → Asistente → Voz del asistente** y pulse **Probar voz**. Para el modo directo, ponga una clave propia en `admin/.env`
(`ANTHROPIC_API_KEY=…`; Git ignora los `.env`).

```bash
uvicorn app.main:app --reload --no-access-log --no-server-header
```
