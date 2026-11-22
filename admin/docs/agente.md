# El asistente del panel

El panel tiene un **asistente**: un agente de IA que, una vez se ingresa, aparece en un botón flotante. Se le escribe
en español y responde con datos de la base: busca personas, resume los indicadores, revisa los pendientes, prepara
reuniones, muestra cosas en el mapa, abre vistas y fichas, presenta y explica la propuesta 2028–2031 (en la vista
**Presentación** o en un proyector) y propone cambios (una nota, un acercamiento, una ficha nueva…) que la persona
aprueba antes de que se guarden.

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
- **Al modelo le llega lo mínimo.** Cédulas y teléfonos enmascarados, nunca datos sensibles ni listas, y nada de quien
  no autorizó el tratamiento (ver [Privacidad](#privacidad-y-protección-de-datos-ley-1581-de-2012)).

## Qué puede hacer

Lo que se le ofrece depende del rol. Planilleros y consultores **no** lo tienen hasta que el administrador los habilita
en **Ajustes → Asistente**.

| Rol | Qué le puede pedir |
|---|---|
| Administrador y coordinador | Indicadores del tablero (también de una zona o con filtros), buscar y ver habitantes, fichas parecidas, reuniones (listar, ver, crear, agregar asistentes), pendientes de calidad (solicitudes por vencer, situaciones, conflictos, coincidencias, lugares sin punto), su trabajo y el de cada usuario, el equipo (lo que hizo cada usuario, alertas, asignación y el avance de cada zona, sin sesiones ni IP), barrios y veredas, catálogos, el mapa, la presentación de la propuesta y cualquier vista. Propone crear y editar fichas, notas, acercamientos, autorizaciones, ubicación y teléfonos. Con Mnemo, el administrador (y el coordinador, si se le permite): documentos, calendario, formularios y memoria |
| Planillero | Buscar y ver habitantes (en su zona y con su presupuesto diario), parecidas, sus reuniones y las abiertas al equipo, su trabajo y sus pendientes, barrios y veredas, catálogos, la presentación de la propuesta y sus vistas. Propone crear y editar fichas, notas, acercamientos (visita o reunión), autorizaciones, ubicación, teléfonos, reuniones y asistentes. Sin tablero, mapa ni equipo |
| Consultor | Su cola de llamadas y su trabajo, buscar por nombre (3 letras o más) o por un número completo de 10 dígitos, ver las fichas de las personas que tiene en curso y la presentación de la propuesta. Propone acercamientos (llamada, WhatsApp, SMS…), autorizaciones y teléfonos |

Nunca, para nadie: exportar o descargar, importar, unir o suprimir fichas, crear usuarios o cambiar claves y roles,
cambiar ajustes, ver los datos sensibles o las listas de origen, ni la cédula o el teléfono completos. Para eso está el
panel: el asistente lo explica y dice dónde hacerlo.

Las herramientas del panel (`app/agente/herramientas/`):

| Herramienta | Tipo | Quién | Qué hace |
|---|---|---|---|
| `buscar_personas`, `ver_persona` | lectura | todos | Habitantes (por nombre, por la cédula o el teléfono completos o con filtros) y fichas, con la proyección de cada rol |
| `personas_parecidas` | lectura | A, K, P | Posibles duplicados por nombre, cédula o teléfono (a quien no autorizó, solo por el nombre) |
| `crear_persona`, `editar_persona`, `agregar_nota`, `ubicar_persona` | escritura | A, K, P | Ficha nueva (avisa si hay parecidas), cambios con «antes → después», notas y ubicación |
| `registrar_acercamiento`, `registrar_autorizacion`, `agregar_telefono` | escritura | todos | Lo que la persona del equipo dicta: nunca inventa evidencias, autorizaciones ni números. Un «sí» va siempre con su medio y sus canales, y una solicitud de derechos con su tipo (y su plazo) |
| `indicadores`, `equipo` | lectura | A, K | Tablero compacto (sin listas ni sensibles, y sin contar a quien no autorizó) y el equipo: lo que hizo y administró cada usuario, alertas, asignación y el avance de cada zona (también sin contar a quien no autorizó) |
| `listar_reuniones`, `ver_reunion` | lectura | A, K, P | Agenda y asistentes |
| `crear_reunion`, `agregar_asistente` | escritura | A, K, P | Reunión nueva (con hora de inicio y de fin) y asistentes |
| `pendientes`, `mi_trabajo`, `buscar_lugar`, `catalogos` | lectura | todos | Insignias y colas, listas de trabajo, nomenclátor de barrios y veredas, catálogos no sensibles |
| `mapa` | interfaz | A, K | Vuela a un lugar, filtra, cambia capas y mapa base, resalta personas, abre una zona |
| `abrir_vista` | interfaz | todos | Abre una vista o una ficha que su rol puede ver |
| `presentacion` | interfaz | todos | La [presentación técnica](#la-presentación-técnica) de la propuesta 2028–2031 (lo que se construye, sin costos): el índice (capítulos, pasos, componentes e inmersiones), ir a un capítulo y paso (le vuelve lo que muestra ese paso para explicarlo: textos, cifras, especificaciones, referentes, sitio, plazos, metas y el modelo del atlas que muestra, todo entero y sin plata: nada se acorta, y un paso pesa a lo sumo 12 KB), siguiente y anterior, una o dos frases en pantalla, de hasta 220 caracteres (`explicar`, `quitar_explicacion`), los paneles sin cambiar de paso (`vista`: el panel de texto o solo la maqueta 3D, el índice, las fichas técnicas), lo que se ve sin cambiar de paso (`visual`: la cámara con su encuadre, su rumbo, su elevación y su acercamiento, a qué apunta y cómo viaja, la obra enfocada, su ficha técnica, hoy o con el proyecto, las piezas de la maqueta que se muestran, se ocultan o se aíslan y las partes que se les quitan, un modelo 3D del atlas y el tema, con la ficha de lo que muestra), que llene la ventana (`pantalla_completa`), qué muestra la [pantalla en off](#pantalla-en-off-y-agentes-por-mcp) (`estado`) y el [plan guiado](#el-plan-guiado-recorridos-narrados): `guion` (todo un capítulo para preparar la explicación, con las piezas de su maqueta), `recorrido` (el plan: de 1 a 12 pasos, cada uno con lo que se dice y lo que ocurre en pantalla mientras se dice, en una sola llamada) y `control_recorrido` (pausar, seguir, saltar, repetir, volver a empezar, detener); y `automatica` (enciende o apaga la [presentación automática](#presentación-automática): la pantalla en off recorre sola toda la presentación, muy resumida). Solo guarda esa pantalla: ningún dato de personas. Un agente externo la usa igual [por MCP](#pantalla-en-off-y-agentes-por-mcp) |

A = administrador, K = coordinador, P = planillero. Las de Mnemo (`mnemo_…`) se describen [más abajo](#conectar-con-mnemo).

De quien no autorizó el tratamiento, las herramientas solo dan quién es y su barrio o vereda. Una búsqueda con otros
filtros (o con un orden que no sea por nombre) o por un número, los indicadores, las cifras del mapa, los
asistentes de una reunión (la lista y los conteos), Mi trabajo, lo pendiente del trabajo, lo que cada usuario del
equipo hizo con las personas y las cifras del avance por zona no lo traen ni lo cuentan: cada filtro que casa, o la
resta de dos conteos, sería un dato suyo. Para saber quiénes no autorizaron, el asistente busca solo por esa
autorización (con su barrio o vereda, o su nombre, si hace falta). En el panel salen todos, como siempre.

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
  progreso en gris (qué está haciendo). Una conversación vacía muestra sugerencias para el rol.
- **Sabe dónde está.** Con cada mensaje viaja la vista abierta: la ruta, la ficha o la reunión que se está viendo, los
  filtros de la vista que están en la dirección (solo los que el asistente también puede usar), el encuadre del mapa y
  el capítulo y el paso de la presentación abierta (aquí o en el proyector; el nombre y el título los pone el servidor
  con el guion).
  Por eso «¿qué le falta a esta ficha?» funciona. Es solo una pista: las herramientas vuelven a leer todo con los
  permisos de la persona. Lo que no le corresponde no viaja aunque esté en la dirección (ver [Qué va al
  modelo](#privacidad-y-protección-de-datos-ley-1581-de-2012)): la consulta de la ruta (lo que va tras «?» o «#»), lo
  buscado en Habitantes con números o un correo (el asistente sabe que hay una búsqueda, no qué se buscó), la lista de
  origen, el liderazgo, el régimen de salud, una etiqueta sensible, la selección o el dibujo del mapa, ni el centro del
  mapa visto de cerca.
- **Aprobar.** Cuando el asistente propone escribir, aparece una tarjeta con lo que va a hacer y los valores exactos
  (al editar, «antes → después») y los botones **Aprobar** y **Rechazar**. Nada se guarda sin aprobar. Lo rechazado no
  lo vuelve a proponer salvo que se le pida, y escribir otro mensaje sin decidir cuenta como rechazo (si ese mensaje se
  detiene o falla antes de que el asistente lo atienda, las tarjetas siguen esperando su decisión). Lo aprobado queda
  en la auditoría a nombre de quien aprobó, como si lo hubiera hecho en el formulario. Si la ficha cambió entre la
  tarjeta y la aprobación (otra persona la editó), no escribe nada y lo avisa: la tarjeta guarda una huella de lo que
  mostró, nunca los valores. Un acercamiento marca el número que mostró su tarjeta, aunque haya cambiado de lugar en
  la ficha (si ya no se puede usar, no registra nada). Sobre quien no autorizó el tratamiento no propone cambios
  (salvo registrar su autorización), ni siquiera para el administrador, y si deja de autorizar entre la tarjeta y la
  aprobación, no escribe. La tarjeta muestra los valores enteros: lo que no cabe en ella (un dato de más de 4.000
  caracteres, más de 40 datos o algo que la herramienta tendría que recortar, como un documento largo de Mnemo) no se
  propone, y el asistente lo divide o lo acorta. Tampoco lo que no se vería como se va a escribir: un dato con
  caracteres invisibles o de control, o que cambian cómo se ve el resto del texto (como las marcas de dirección, el
  espacio de ancho cero o un selector de variante que no es parte de un emoji), sin asignar o de uso privado, o con
  muchos saltos de línea o espacios seguidos que esconderían el final. Un dato largo se lee entero desplazándolo dentro
  de su recuadro (una sombra marca que sigue y la tarjeta pide leerlo antes de aprobar); el panel nunca lo recorta, y
  si una tarjeta trajera más de lo que puede mostrar, no tiene **Aprobar**: solo se rechaza. Lo mismo lo que quedó
  esperando aprobación con una versión anterior del panel (que no mostraba los valores enteros): se rechaza y se le
  pide al asistente que lo vuelva a proponer. Una decisión que llega desde una pestaña que ya no está al día (otra
  pestaña aprobó y llegó otra propuesta) no decide nada: el asistente vuelve a traer la conversación, con lo que espera
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
  `/reuniones/45`). Las aprobaciones de Mnemo abren Mnemo en otra pestaña. Ningún otro enlace se vuelve clicable.
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
  capítulo pesa más de 34.000 bytes, primero sin las descripciones ni los referentes de las fichas y después sin la
  ayuda, que llega igual al ir al paso de la inmersión: hoy le pasa a Salud), al ir a un paso de inmersión y al abrir
  un modelo con `visual`.
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
  (`controles_maqueta`) y al ir a un paso sin modelo del atlas. Su ayuda solo va en `guion` (al ir a un paso llegan sin
  ella), así que es lo último que `guion` quita si el capítulo no cabe.
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
  seguir). Mientras suena,
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
- **Un agente por MCP.** En **Mi cuenta → Agentes por MCP**, **Crear clave** muestra la dirección del servidor MCP
  (`https://<su dominio>/panel/api/mcp`) y la clave, una sola vez. En el cliente MCP se configura como servidor remoto
  (Streamable HTTP) con la cabecera `Authorization: Bearer <clave>`; si el cliente solo acepta una dirección, la
  segunda que muestra Cuenta lleva la clave en `?clave=` (guárdela como un secreto). Por ejemplo, con Claude Code:

  ```bash
  claude mcp add --transport http yondo-presentacion https://<su dominio>/panel/api/mcp --header "Authorization: Bearer <clave>"
  ```

  El agente ve una sola herramienta, `presentacion`, con las mismas operaciones y las mismas reglas que el asistente:
  la frase en pantalla nunca lleva datos de habitantes, «@» ni números de 7 o más dígitos. Con esa clave no se lee ni
  se escribe ningún dato de personas.
- **La clave.** Una por persona: crear otra reemplaza la anterior y **Revocar la clave** la anula. En la base queda su
  SHA-256, nunca la clave. Deja de valer sola si la persona cambia su clave del panel (o el administrador cambia su
  credencial), si la desactivan, o si su cuenta queda pendiente (clave temporal o compromiso por aceptar). Crear y
  revocar quedan en la auditoría. El servidor rechaza las peticiones con una cabecera `Origin` que no es la del panel
  (un navegador no puede usarla desde otra página) y atiende hasta 120 por minuto por clave.
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
  1. la narración escrita a mano;
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

  Todo pasa las reglas de lo que se proyecta y nada habla de costos; un paso sin nada que decir se salta. Hoy son 52
  pasos en 9 capítulos (solo dos dicen su título, que ya es una frase) y la vuelta completa dura unos 10 minutos y
  medio: entre capítulo
  y capítulo no hay cierre ni espera de preguntas (eso es de los planes del asistente), solo un segundo y medio.
- **Escribir una narración a mano.** En `data/propuesta/general.json`, `tecnica.narracion` es
  `{capítulo: {id del paso: "frase"}}` (hasta 220 caracteres, sin costos); `python3 scripts/build_propuesta.py` la
  lleva al guion del asistente (queda en el paso como `narracion`) y manda sobre todo lo demás.
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
- Para la [voz clonada](#la-voz-clonada-de-mnemo) (opcional): una versión con `mnemo_speak` y `mnemo_list_voices` y el
  permiso `mnemo:voice`, un plan que incluya las voces clonadas, créditos y al menos una voz marcada **Disponible
  para apps conectadas**. Sin eso, el panel sigue con la voz del navegador.

**Variables** (todas opcionales; la conexión no es una variable):

| Variable | Valor |
|---|---|
| `MNEMO_MCP_URL` | La dirección MCP de Mnemo que Ajustes sugiere al conectar: `https://<su Mnemo>/mcp` (en local también `http://127.0.0.1` o `http://localhost`). Otra cosa se ignora con un aviso en el registro. No es secreta y no conecta nada por sí sola |
| `MNEMO_MODELO` | Qué modelo de la cuenta usa el asistente: `principal` (el que la cuenta tiene por defecto), `ligero` (su modelo rápido; si no tiene, el principal) o `<proveedor>/<modelo>` (uno concreto que la cuenta tenga). Vacía, el que la cuenta tenga por defecto. Otro valor se ignora con un aviso en el registro |
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

- Los datos sensibles (salud, etnia, discapacidad, condición de víctima), las listas de origen y quién es líder, ni
  las etiquetas o campos propios marcados como sensibles.
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
- La clave de Anthropic, los tokens de la conexión con Mnemo, las claves de los usuarios, las sesiones ni las IP.

**Retención.** Las conversaciones se guardan en MongoDB (`agente_conversaciones` y `agente_mensajes`) y se borran
solas a los días de **Ajustes** desde su último mensaje (30 por defecto). Bajar ese plazo acorta también las que ya
existen: las que ya lo pasaron se borran en cuanto MongoDB lo revisa (cada minuto). Su dueño las puede borrar antes.
El uso (`agente_uso`: mensajes, tokens y créditos por persona y día, sin contenido) se guarda 180 días.

**Supresión y revocatoria.** Cada conversación anota de qué personas recibió datos el modelo (y cuáles mostró una
tarjeta). Al **suprimir** a una persona, se borran enteras las conversaciones donde aparecía (y la reconciliación de
cada arranque repasa las que hayan quedado); si la supresión llega mientras el asistente la está leyendo, el turno
termina y esa conversación también se borra. Lo mismo cuando deja de autorizar (un «no» o una revocatoria, por el
panel, con «no contactar», por una importación o al unir su ficha con la de quien no autorizó): sus datos no siguen en
el historial que se le reenvía al modelo en cada ronda, aunque la conversación sea la que registró la revocatoria, y si
el «no» llega mientras el asistente la está leyendo (también entre las fichas que devuelve una escritura, como las
parecidas del alta), el turno termina y esa conversación se borra (para eso queda una hora en `agente_olvidos` quién
dejó de autorizar, sin ningún otro dato). Al cambiarle el rol o la zona a un usuario (también desde **Zonas**), o al
desactivarlo, se borran sus conversaciones.

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

Los datos de bases oficiales (como las del SISBÉN) siguen sirviendo solo para la finalidad con que se recogieron,
también a través del asistente.

## Límites y costos

**Modelo y esfuerzo con Mnemo.** El modelo es el que la cuenta de Mnemo tenga por defecto, o el de `MNEMO_MODELO`, y el
costo son créditos de Mnemo, según el plan de la cuenta (o su clave propia de un proveedor). `AGENTE_ESFUERZO` vale
también: `low` y `medium` pasan tal cual, y `high`, `xhigh` y `max` piden el razonamiento alto (un modelo sin
razonamiento lo ignora). Cada ronda escribe como mucho 16.000 tokens, y `agente_uso` guarda también los créditos que
informa Mnemo. El razonamiento del modelo no se muestra: con Mnemo son resúmenes internos, no notas para la persona.

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

**Topes.**

- Por persona y día, los mensajes de **Ajustes** (429 al pasarse): cuenta cada mensaje y cada aprobación o rechazo.
- Por turno: 12 rondas y 240 segundos; al llegar, termina la ronda en curso y avisa (se le puede pedir que siga).
  Ningún turno pasa de 10 minutos y cada ronda escribe como mucho 32.000 tokens (16.000 con Mnemo). Cada herramienta
  del panel tiene 60
  segundos; las de Mnemo, 80 las de lectura y 140 las de escritura (algunas gastan modelo en Mnemo), porque cortarlas
  antes las cancelaría a medias allá. En una ronda corren como mucho 8 herramientas (las demás vuelven al modelo sin
  hacerse) y en un turno el modelo recibe como mucho 200.000 caracteres de lo que leen: pasado eso, lo leído no se le
  pasa y responde con lo que tiene. Así una sola respuesta del modelo (por ejemplo, por una instrucción escondida en
  una nota) no vuelca la base. Las imágenes de Mnemo van como mucho dos por resultado y 8 MB por ronda (con Mnemo como
  modelo, 1,5 MB por ronda), y 20 (y 20 MB) por conversación: la conversación entera se reenvía en cada ronda.
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

## Configuración en Railway

En *Variables* del servicio que sirve el panel (el del sitio, en el servicio único):

El asistente no necesita ninguna variable: se conecta con Mnemo desde **Ajustes → Asistente**. Todas son opcionales:

| Variable | Valor |
|---|---|
| `MNEMO_MCP_URL` | La dirección MCP de Mnemo que se sugiere al conectar (ver [Conectar con Mnemo](#conectar-con-mnemo)) |
| `MNEMO_MODELO` | El modelo de la cuenta de Mnemo: `principal`, `ligero` o `<proveedor>/<modelo>`; vacía, el de la cuenta |
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
3. En la misma sección, revise quiénes lo usan, los topes y la retención.

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
- **No hay herramientas para lo delicado**: exportar, importar, unir, suprimir, usuarios y claves, ajustes, datos
  sensibles.
- **Escrituras.** Solo con aprobación, y con una clave de idempotencia por llamada: aprobar dos veces o reintentar no
  duplica nada. Una escritura del panel que no termina dentro del plazo de la herramienta sigue hasta el final (y
  guarda su respuesta para un reintento), y el asistente avisa que pudo quedar hecha en vez de proponerla de nuevo.
- **Lo que viene de la base o de Mnemo son datos, no instrucciones.** Las notas, los documentos y los formularios los
  escribe gente y pueden traer órdenes escondidas; el asistente no las sigue, y aunque lo hiciera no puede saltarse los
  permisos ni escribir sin aprobación.
- **La respuesta se pinta como texto**, nunca como HTML: solo enlaza rutas del panel y el origen de Mnemo, y las
  acciones que puede pedirle al navegador son una lista cerrada (abrir una ruta del panel, recargar la vista, refrescar
  las insignias, mover el mapa, manejar la presentación).
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
  `agente:estado`, que emite Ajustes al volver de Mnemo, al desconectar y al guardar los ajustes del asistente; si se
  abre sin modelo, también lo vuelve a pedir.

## Arquitectura

| Archivo | Qué hace |
|---|---|
| `app/api/agente.py` | Las rutas: `GET /api/agente/estado`, `GET /api/agente/conversaciones`, `GET` y `DELETE /api/agente/conversaciones/{id}`, `POST /api/agente/mensajes`, `POST /api/agente/confirmaciones`, `POST /api/agente/transcribir`, `GET /api/agente/voces` y `POST /api/agente/voz` |
| `app/api/agente_mnemo.py` | La conexión con Mnemo: `POST /api/agente/mnemo/conectar`, `POST /api/agente/mnemo/volver` y `DELETE /api/agente/mnemo` (solo el administrador) |
| `app/agente/bucle.py` | El turno: comprobaciones previas, candados, rondas con el modelo, ejecución de herramientas, aprobaciones y eventos NDJSON |
| `app/agente/proveedores.py` | De dónde sale el modelo: Mnemo si está conectado con `mnemo:model`; si no, Anthropic si hay clave. Queda fijo en cada conversación |
| `app/agente/modelo_mnemo.py` | El modelo de Mnemo: cada ronda por `mnemo_model_complete`, con el texto por partes |
| `app/agente/llm.py` | El modelo de Anthropic en modo directo: el cliente (se crea al primer uso) y la forma de cada petición |
| `app/agente/mnemo_conexion.py`, `app/agente/cifrado.py` | OAuth con Mnemo, los tokens cifrados y su renovación |
| `app/agente/sistema.py` | Las instrucciones del asistente (fijas por conversación) y el contexto de la vista de cada mensaje |
| `app/agente/conversaciones.py` | Conversaciones, mensajes (solo se agregan, nunca se editan) y uso diario en MongoDB |
| `app/agente/politica.py` | Quién lo usa y con qué: los ajustes con valores de respaldo |
| `app/agente/interno.py` | Las llamadas a la API del panel con la sesión de quien conversa |
| `app/agente/minimizar.py` | Lo mínimo de cada persona que llega al modelo |
| `app/agente/herramientas/` | `base.py` (contratos), `personas.py`, `gestion.py`, `interfaz.py` y `mnemo.py` |
| `app/agente/mnemo_cliente.py` | El cliente del servidor MCP de Mnemo |
| `app/agente/dictado.py` | Las preguntas por voz: el audio a `mnemo_transcribe`, con sus topes |
| `app/agente/adelanto.py` | La [respuesta inmediata](#la-respuesta-inmediata): sus mensajes, lo que se muestra (la marca «—», palabra por palabra, el tope), sus frases para decir, la carrera con la respuesta completa, el plazo y lo que se guarda |
| `app/agente/voz.py` | La [voz clonada de Mnemo](#la-voz-clonada-de-mnemo): el texto de cada pedido (el plan guardado, la frase firmada, la prueba), lo que se dice (`para_decir`, `hablable`), las frases de una respuesta (`Frases`), la firma, los topes, la caché, un solo vuelo y el flujo de `mnemo_speak` |
| `web/js/agente.js`, `web/css/agente.css` | El botón y el panel del asistente (también el recuadro de la respuesta inmediata y cuándo la sala la oye) |
| `web/js/agente-mapa.js` | El puente entre el asistente y la vista del mapa |
| `app/agente/guion.py`, `app/agente/propuesta_guion.json` | El guion de la presentación (lo que muestra cada paso, en texto plano): lo genera `scripts/build_propuesta.py` desde `web/data/propuesta.json` y va versionado dentro de `admin/` (también lo tiene el panel desplegado aparte) |
| `web/js/agente-presentacion.js` | El puente entre el asistente y la vista Presentación: la cola, la navegación a `/presentacion`, el validador de la acción y el canal con la ventana del proyector |
| `web/js/vistas/presentacion.js`, `web/css/presentacion.css` | La vista Presentación: el iframe de la propuesta, su barra, el modo proyector (`?pantalla=1`), la pantalla en off (`?off=1`) y la ventana llena |
| `web/js/propuesta/mando.js` (del sitio) | En la presentación: recibe las órdenes del panel (también `vista`), le avisa cada cambio de paso y pinta el subtítulo |
| `app/pantalla.py`, `app/api/pantalla.py` | La pantalla en off de cada persona (su estado, `GET /api/pantalla`), su clave MCP (`/api/pantalla/clave`), el recorrido narrado: guardarlo, colapsarlo, el avance (`POST /api/pantalla/progreso`), los controles (`POST /api/pantalla/recorrido/control`) y dónde va (`GET /api/pantalla/recorrido`), y el estado de la [presentación automática](#presentación-automática) (`POST /api/pantalla/auto` y `/auto/siguiente`) |
| `app/automatica.py` | La presentación automática por dentro: qué se dice en cada paso, el plan de cada capítulo y por dónde sigue (sin modelo: sale del guion) |
| `app/recorrido.py`, `app/proyectable.py` | El plan guiado por dentro (el recorrido: sus topes, la forma absoluta de la escena con `mover`, `animar` y `simular`, las frases, los tiempos, la validación contra el guion, también de los controles de la simulación) y las reglas de lo que se proyecta (también sin costos) |
| `web/js/reproductor.js`, `web/js/voz.js` | El reproductor del plan (el reloj de la explicación, la espera inicial, que deja terminar la respuesta inmediata, pausas, saltos, cierre; la referencia de cada frase en el plan y la precarga de la que sigue) y la voz del navegador |
| `web/js/voz-clonada.js` | La voz clonada en el navegador (pura, como `voz.js`): pide cada frase por su referencia, agenda el PCM con Web Audio, precarga, la memoria de la página y el respaldo con la voz del navegador |
| `web/js/voz-panel.js` | La voz de la ventana: una sola para la narración, las respuestas habladas y la prueba de Ajustes (con conteo de referencias), con `flujo('/api/agente/voz', …)` y el `voz` del estado; la narración manda, salvo ante la respuesta inmediata que suena (la marca y la cesión del plan en su espera) |
| `web/js/locutor.js` | Las respuestas habladas: dice en orden las frases firmadas del turno, primero las de la respuesta inmediata (su propia cola, que la respuesta espera), precarga la siguiente, se resincroniza con `frases_descartar` y `frases_ronda` y se calla |
| `web/js/agente-recorrido.js` | La tarjeta del plan en el chat y su barra fija |
| `app/api/mcp.py` | El servidor MCP de la presentación (`POST /api/mcp`): la herramienta `presentacion` para un agente externo |
| `web/js/vistas/cuenta.js` | Mi cuenta, con **Agentes por MCP**: la dirección del servidor y la clave |
| `web/js/api.js` (`flujo`) | Lee la respuesta NDJSON con el CSRF de la sesión |
| `app/api/ajustes.py`, `web/js/vistas/ajustes.js` | Los ajustes del asistente y, en la vista, la conexión con Mnemo (conectar, la vuelta y desconectar) y el bloque **Voz del asistente** (las voces de `GET /api/agente/voces`, `agente_voz` y **Probar voz**) |

**Un turno, paso a paso.**

1. El navegador manda `POST /api/agente/mensajes` con `{conversacion, texto, contexto}`.
2. Antes de abrir el flujo, el servidor responde con JSON normal lo que impide el turno: 503 `sin_configurar` (no hay
   modelo: ni Mnemo conectado con permiso para usar sus modelos ni clave de Anthropic) o `saturado` (ya hay 4 turnos
   en este proceso; trae `Retry-After`), 403 `agente_apagado` (su rol no está habilitado), 429 `volumen` (tope diario),
   409 `ocupada` (ya hay un turno suyo en curso: en el acto; solo si ese turno se está cerrando, como tras
   **Detener**, antes espera hasta 5 segundos a que suelte la conversación), `larga` (conversación demasiado larga) o
   `proveedor` (la
   conversación es de un modelo que ya no está: hay que empezar otra), y 404 si la conversación no es suya o no
   existe.
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
| `accion` | Una acción para el navegador: `navegar` (una ruta del panel), `recargar`, `insignias`, `mapa` (acciones del mapa) o `presentacion` (`op`: `ir` con `capitulo` y `paso` desde 1, `siguiente`, `anterior`, `explicar` o `quitar_explicacion`; `explicacion`, la frase para la pantalla, en todas salvo la última; `vista` con `panel`, `indice` o `fichas`; `visual` con `enfoque`, `camara`, `rumbo`, `elevacion`, `zoom`, `mirar`, `girar`, `comparar`, `detalle`, `inmersion`, `mostrar`, `ocultar`, `aislar`, `sin` o `tema`, y las acciones `mover`, `animar` y `simular`; `pantalla_completa` con `activar`; `recorrido` con el recorrido absoluto (cada escena: `capitulo`, `paso`, `panel`, `visual`, `resaltar`, `mover`, `animar`, `simular` (puede faltar), `frases` y `sostener_ms`); `control_recorrido` con `rid` y `accion`) o `recorrido` (la tarjeta del plan en el chat: `id`, `titulo`, `destino`, `duracion_ms`, `cierre`, `sugerencias` y por escena `narracion`, `donde` y `hace`) |
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
El texto de una ronda puede llegar en un solo trozo largo (con Mnemo, si el proveedor de la cuenta no responde por
partes): el widget lo pinta entero, con el mismo tope que `texto_ronda`.

**En MongoDB**: `agente_conversaciones` (dueño, título, proveedor del modelo con que empezó, instrucciones y
herramientas congeladas, personas vistas, lo pendiente de aprobar y lo que no se aprobó, las escrituras de Mnemo ya
mandadas, candado del turno y fecha de borrado), `agente_mensajes` (un documento por mensaje, con su número de orden),
`agente_uso` (mensajes, tokens y créditos por persona y día), `agente_olvidos` (quién dejó de autorizar en la última
hora: solo el número de la ficha y la hora) y, en `meta`, `mnemo_conexion` (la conexión con Mnemo, con los tokens
cifrados). Los índices TTL borran lo vencido.

## Probar en local

Sin Mnemo conectado ni `ANTHROPIC_API_KEY` el panel funciona igual: el administrador ve el botón con la explicación de
qué falta. Sin una voz clonada, el panel narra y lee con la voz del navegador. Las pruebas nunca llaman a Anthropic ni a Mnemo: el modelo de Anthropic va simulado con el SDK de verdad y
un transporte falso, y Mnemo con un servidor MCP y un OAuth falsos (`tests/ayudas_mcp.py`). Necesitan MongoDB, como las
demás:

```bash
cd admin
python -m pytest -q tests/test_agente_*.py tests/test_dictado*.py tests/test_voz_*.py
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
